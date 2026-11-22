# pg_restore, lựa chọn đối tượng và phục hồi song song trong PostgreSQL

`pg_restore` là công cụ phục hồi logical backup được tạo bởi `pg_dump` ở các định dạng archive: custom, directory và tar. Công cụ đọc table of contents (TOC), tạo lại schema objects, nạp dữ liệu và có thể điều phối nhiều restore jobs cùng lúc. Nhờ TOC, người vận hành có thể chọn object, chia restore thành nhiều section hoặc thay đổi thứ tự thực thi.

Một lần restore không chỉ là chạy một lệnh. Cần chuẩn bị database đích, roles, extensions, tablespaces, quyền truy cập và dependency giữa các object. Với database lớn, cần cân bằng số worker với CPU, I/O, WAL, connection limit và replication lag.

Các quyết định quan trọng:

- Chọn đúng công cụ theo format: psql cho plain SQL, pg_restore cho archive.
- Chọn phạm vi object dựa trên dependency, không chỉ tên table.
- Dùng parallel restore khi archive và workload phù hợp.
- Kiểm soát lỗi, transaction, lock và các thao tác DROP.
- Xác minh database sau khi restore bằng catalog, dữ liệu và smoke tests.

~~~mermaid
flowchart TD
    A["Nhận backup"] --> B{"Định dạng?"}
    B -->|"Plain SQL"| C["psql"]
    B -->|"Custom / Directory / Tar"| D["pg_restore"]
    D --> E["Đọc TOC"]
    E --> F["Chọn toàn bộ hoặc object/section"]
    F --> G["Chuẩn bị database và dependencies"]
    G --> H{"Có thể parallel?"}
    H -->|"Custom hoặc Directory"| I["pg_restore -j N"]
    H -->|"Tar hoặc cần single transaction"| J["Restore tuần tự"]
    C --> K["Nạp SQL script"]
    I --> L["Kiểm tra lỗi và kết quả"]
    J --> L
    K --> L
    L --> M["Smoke tests và bàn giao"]
~~~

Bài học thuộc chương **Khôi phục**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ đi từ cấu trúc archive và TOC tới selective restore, parallel jobs, xử lý lỗi, quyền sở hữu, theo dõi tiến trình và quy trình khôi phục có thể lặp lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của pg_restore trong logical backup workflow.
2. Phân biệt pg_restore với psql.
3. Nhận diện archive custom, directory và tar.
4. Đọc TOC bằng pg_restore -l.
5. Chọn object bằng --use-list, --schema, --table và các option liên quan.
6. Hiểu vì sao selective restore có thể thiếu dependencies.
7. Phân chia restore theo pre-data, data và post-data.
8. Chuẩn bị database đích và global dependencies.
9. Kiểm soát owner, ACL, role và tablespace.
10. Dùng --clean, --if-exists và --create đúng phạm vi.
11. Hiểu --exit-on-error và --single-transaction.
12. Chọn số parallel jobs phù hợp với tài nguyên.
13. Phân biệt parallel restore với parallel dump.
14. Hiểu vì sao tar không hỗ trợ parallel restore.
15. Theo dõi restore bằng progress views, pg_stat_activity và logs.
16. Khôi phục sau khi một phần restore thất bại.
17. Kiểm tra sequence, constraints, indexes và large objects.
18. Lập kế hoạch kiểm thử, RTO và bảo mật dữ liệu phục hồi.

## 2. pg_restore làm gì?

pg_restore đọc archive do pg_dump tạo ở custom, directory hoặc tar format. Archive có metadata mô tả các thành phần như:

- Schema definitions.
- Table data.
- Sequences và sequence values.
- Indexes.
- Constraints.
- Triggers và rules.
- Functions, procedures, types.
- Views và materialized views.
- Large objects.
- Ownership và ACL metadata, nếu dump có chứa.

pg_restore có thể tạo SQL commands từ archive hoặc kết nối trực tiếp tới database đích để thực thi các commands đó.

### Hai cách sử dụng chính

Xuất SQL script để review:

~~~bash
pg_restore --file=restore.sql appdb.dump
~~~

Kết nối và restore trực tiếp:

~~~bash
pg_restore --dbname=appdb_restore appdb.dump
~~~

Khi xuất ra script bằng --file, có thể mở và review nội dung trước khi chạy. Khi restore trực tiếp bằng --dbname, pg_restore thực hiện các lệnh trên database đích.

### pg_restore không đọc plain SQL dump

Nếu file được tạo bằng:

~~~bash
pg_dump -Fp -d appdb -f appdb.sql
~~~

thì restore bằng:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f appdb.sql
~~~

Không đưa file plain SQL vào pg_restore. Việc đổi phần mở rộng của file không thay đổi định dạng thực tế.

## 3. Những định dạng pg_restore hỗ trợ

| Định dạng | Dấu hiệu | Công cụ restore | Parallel restore |
| --- | --- | --- | --- |
| Plain | SQL text | psql | Không |
| Custom | PostgreSQL archive một file | pg_restore | Có |
| Directory | Thư mục archive có TOC và data files | pg_restore | Có |
| Tar | TAR archive | pg_restore | Không |

### Custom

Custom format thường được chọn bằng:

~~~bash
pg_dump -Fc -d appdb -f appdb.dump
~~~

Đây là một archive file, có TOC, hỗ trợ chọn object và parallel restore.

### Directory

Directory format:

~~~bash
pg_dump -Fd -d appdb -f appdb_dir
~~~

Thư mục archive chứa TOC và các file dữ liệu. Có thể dump và restore song song.

### Tar

Tar format:

~~~bash
pg_dump -Ft -d appdb -f appdb.tar
~~~

pg_restore có thể đọc TOC và chọn object trong tar archive, nhưng không hỗ trợ parallel restore với định dạng này.

### Tại sao format ảnh hưởng tới restore?

Custom và directory lưu archive entries theo cấu trúc cho phép pg_restore điều phối công việc và mở nhiều worker. Plain là một chuỗi SQL commands; tar không có cơ chế parallel restore mà pg_restore hỗ trợ. Vì vậy phải chọn format từ bước backup theo nhu cầu phục hồi, không thể đổi format bằng cách đổi tên file.

## 4. Kiểm tra phiên bản công cụ

Trước khi restore:

~~~bash
pg_restore --version
psql --version
pg_dump --version
~~~

Nên dùng client tools tương thích với phiên bản server đích. Các archive và option có thể thay đổi theo major version.

Quy tắc vận hành quan trọng:

- Client pg_restore cũ có thể không hiểu archive được tạo bởi pg_dump mới hơn.
- Restore lên cùng major version hoặc major version mới hơn thường là hướng triển khai phổ biến.
- Restore ngược về major version cũ không được bảo đảm.
- Extension, collation, data type và server-side features cũng có thể khác giữa các version.

Đọc release notes và thử restore trên môi trường staging tương thích trước khi chuyển production.

## 5. Tạo database đích

Với restore đầy đủ, cách dễ kiểm soát là tạo database trống từ template0:

~~~bash
createdb -T template0 appdb_restore
~~~

Hoặc dùng SQL:

~~~sql
CREATE DATABASE appdb_restore
    WITH TEMPLATE template0
    ENCODING 'UTF8';
~~~

Tên encoding, locale, collation và database options phải phù hợp với nguồn và ứng dụng. Không mặc định UTF8 hoặc locale của mọi hệ thống đều giống nhau.

### Vì sao thường dùng template0?

template0 là template sạch hơn cho việc tạo database có encoding/locale được chỉ định. template1 có thể chứa các objects do administrator thêm vào; các objects đó có thể gây xung đột với archive.

### Restore vào database hiện có

Có thể restore vào database đã tồn tại, nhưng phải xử lý:

- Object cùng tên.
- Schema/table đã có.
- Constraints và indexes trùng.
- Dữ liệu đã tồn tại.
- Owner/ACL khác nhau.
- Dependencies không đồng nhất.

Với bài toán thay thế toàn bộ database, thường dễ kiểm soát hơn nếu restore sang database mới, xác minh rồi chuyển ứng dụng theo kế hoạch cutover.

## 6. Kết nối và cú pháp cơ bản

Cú pháp tổng quát:

~~~bash
pg_restore [options] [archive-file-or-directory]
~~~

Ví dụ:

~~~bash
pg_restore \
  -h db.example.internal \
  -p 5432 \
  -U restore_user \
  -d appdb_restore \
  --verbose \
  --exit-on-error \
  appdb.dump
~~~

Các option kết nối thường dùng:

| Option | Ý nghĩa |
| --- | --- |
| -h | Host |
| -p | Port |
| -U | User |
| -d / --dbname | Database kết nối để restore |
| -W | Yêu cầu prompt password |
| -v / --verbose | In chi tiết tiến trình |
| -e / --exit-on-error | Dừng khi có lỗi |
| -j / --jobs | Số restore workers |
| -f / --file | Xuất SQL script thay vì kết nối database |

Không đặt password trực tiếp trong command line hoặc script dùng chung. Dùng .pgpass, service file hoặc secret manager theo policy của môi trường.

## 7. Đọc Table of Contents

Archive có TOC (table of contents) liệt kê các object và data entries.

Xem danh sách:

~~~bash
pg_restore --list appdb.dump
~~~

Lưu ra file:

~~~bash
pg_restore --list appdb.dump > appdb.list
~~~

TOC thường có thông tin:

- Dump ID.
- Catalog identifiers.
- Object type.
- Schema.
- Object name.
- Owner hoặc metadata liên quan.

Ví dụ rút gọn minh họa:

~~~text
;
; Archive created at ...
;     dbname: appdb
;     TOC Entries: ...
;
... TABLE public customers ...
... TABLE DATA public customers ...
... SEQUENCE public customers_id_seq ...
... INDEX public customers_pkey ...
... CONSTRAINT public customers customers_pkey ...
... TABLE public orders ...
... TABLE DATA public orders ...
... INDEX public orders_customer_id_idx ...
~~~

Nội dung và cách hiển thị cụ thể phụ thuộc phiên bản và archive. Hãy xem output thật từ archive của mình.

### TOC dùng để làm gì?

- Xác nhận archive có metadata đọc được.
- Tìm object cần restore.
- Tạo danh sách object được phép restore.
- Bỏ qua object không cần trong môi trường test.
- Phân tích dependency và thứ tự restore.
- Lưu lại kế hoạch phục hồi có thể review.

pg_restore --list chỉ đọc TOC; lệnh thành công không chứng minh mọi data payload đều đầy đủ hoặc restore sẽ thành công.

## 8. Chọn object bằng TOC list

Tạo list:

~~~bash
pg_restore -l appdb.dump > appdb.list
~~~

Mở file và comment hoặc loại bỏ các dòng không muốn restore theo cú pháp list. Sau đó dùng:

~~~bash
pg_restore -L appdb.list -d appdb_restore appdb.dump
~~~

-L là dạng ngắn của --use-list. pg_restore dùng các entries trong file list theo thứ tự xuất hiện ở đó.

### Ví dụ chọn một số object

Giả sử archive có:

- Table customers và data.
- Table orders và data.
- Indexes.
- Functions.
- Views.

Nếu chỉ muốn restore customers, có thể giữ entries liên quan customers trong TOC. Nhưng phải xem các dependencies như type, sequence, function hoặc schema có cần thiết hay không.

### Vì sao cần cẩn thận?

Một object có thể phụ thuộc object khác. Nếu bỏ table nhưng giữ view tham chiếu table, view creation sẽ thất bại. Nếu giữ table data nhưng bỏ type/function cần thiết, restore có thể lỗi.

TOC list cho phép chọn entry, nhưng không tự giải quyết mọi dependency graph. Test trong database tạm trước khi áp dụng.

## 9. Lựa chọn theo schema

Restore một schema:

~~~bash
pg_restore -n sales -d appdb_restore appdb.dump
~~~

Hoặc:

~~~bash
pg_restore --schema=sales --dbname=appdb_restore appdb.dump
~~~

Có thể loại trừ schema:

~~~bash
pg_restore -N audit -d appdb_restore appdb.dump
~~~

-n/--schema chọn object trong schema được chỉ định. -N/--exclude-schema loại schema khỏi phạm vi restore.

Lưu ý:

- Schema name/pattern có quy tắc matching; dùng quote phù hợp.
- Schema được chọn không tự đảm bảo tất cả object bên ngoài schema phụ thuộc vào nó đều được restore.
- Extension và global roles vẫn cần chuẩn bị riêng.
- Một số object database-wide không thuộc schema có thể không được chọn.

## 10. Lựa chọn theo table

Restore table:

~~~bash
pg_restore -t orders -n sales -d appdb_restore appdb.dump
~~~

Có thể chọn nhiều table:

~~~bash
pg_restore \
  -n sales \
  -t customers \
  -t orders \
  -d appdb_restore \
  appdb.dump
~~~

Loại trừ table:

~~~bash
pg_restore -T audit_log -n public -d appdb_restore appdb.dump
~~~

-t/--table chọn table theo pattern. -T/--exclude-table loại table phù hợp pattern.

### Table selection có giới hạn

Chọn một table không đồng nghĩa pg_restore tự động restore toàn bộ object phụ thuộc. Đặc biệt cần xem:

- Schema và custom types.
- Sequence/identity.
- Indexes.
- Constraints.
- Triggers.
- Functions được gọi bởi defaults/triggers.
- Views/materialized views.
- Foreign keys tới table khác.

Tùy archive, option và object type, cần xem TOC thực tế. Đừng giả định -t là một gói dependency hoàn chỉnh.

## 11. Chọn loại object

pg_restore cung cấp các option chọn loại object trong archive, ví dụ:

| Option | Mục tiêu |
| --- | --- |
| -I / --index | Chọn index |
| -P / --function | Chọn function |
| -n / --schema | Chọn schema |
| -t / --table | Chọn table |
| -N / --exclude-schema | Loại schema |
| -T / --exclude-table | Loại table |

Tên option ngắn có thể trùng chữ với option ở ngữ cảnh khác; luôn đọc pg_restore --help của client đang dùng. Một số object type có option riêng, và hỗ trợ pattern thay đổi theo version.

Với selective restore phức tạp, TOC list thường minh bạch hơn việc ghép nhiều pattern.

## 12. Restore theo section

Archive được chia thành các section logic:

- **pre-data**: các định nghĩa cần có trước khi nạp dữ liệu, như schema, types và table definitions.
- **data**: table data và large objects.
- **post-data**: nhiều indexes, triggers, rules và constraints được tạo sau khi nạp dữ liệu.

Ví dụ:

~~~bash
pg_restore --section=pre-data -d appdb_restore appdb.dump
pg_restore --section=data -d appdb_restore appdb.dump
pg_restore --section=post-data -d appdb_restore appdb.dump
~~~

### Khi nào chia section?

- Nạp data lớn trước, tạo indexes sau.
- Điều tra lỗi ở một giai đoạn.
- Thiết kế workflow nhiều bước.
- Tách quyền hoặc maintenance window theo giai đoạn.
- Theo dõi thời gian schema build, data load và index build riêng.

### Không chạy các section tùy tiện song song

Post-data phụ thuộc pre-data và data. Chạy post-data trước khi table tồn tại hoặc trước khi dữ liệu được nạp có thể thất bại hoặc tạo workload không cần thiết.

Nếu restore theo section, giữ thứ tự và kiểm tra exit code của từng bước.

## 13. Chỉ schema hoặc chỉ data

Schema-only:

~~~bash
pg_restore --schema-only -d appdb_restore appdb.dump
~~~

Data-only:

~~~bash
pg_restore --data-only -d appdb_restore appdb.dump
~~~

Schema-only phù hợp khi muốn tạo object definitions trước. Data-only phù hợp khi schema đã được triển khai và kiểm tra.

Nhưng data-only yêu cầu:

- Table và column tương thích.
- Types và functions cần thiết có sẵn.
- Sequence/identity phù hợp.
- Constraints/triggers đã được lên kế hoạch.
- Target có encoding/collation tương thích.

Không nạp data vào schema khác cấu trúc rồi kỳ vọng pg_restore tự chuyển đổi dữ liệu.

## 14. Restore song song: nguyên lý

Với archive custom hoặc directory, có thể dùng -j:

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

pg_restore mở nhiều connections tới database đích và điều phối các archive entries có thể chạy đồng thời.

Các công việc có thể được song song hóa tùy dependency, ví dụ:

- Nạp dữ liệu của các table độc lập.
- Tạo indexes cho các relation độc lập.
- Các archive items không có dependency ordering conflict.

Một số bước vẫn phải tuần tự vì phụ thuộc object hoặc metadata.

### Parallel restore không chia một table thành nhiều phần tùy ý

-j 4 không có nghĩa một table lớn được chia thành bốn phần để bốn worker cùng nạp. Parallelism chủ yếu hoạt động giữa các archive items có thể chạy độc lập. Một table lớn đơn lẻ có thể vẫn là một công việc chiếm một worker.

Điều này giải thích vì sao database có nhiều bảng độc lập có thể hưởng lợi rõ rệt, trong khi database chỉ có một bảng khổng lồ không nhất thiết tăng tốc tương ứng.

## 15. Định dạng nào hỗ trợ parallel restore?

| Format | Parallel restore | Lý do vận hành |
| --- | --- | --- |
| Custom | Có | Archive hỗ trợ pg_restore phân phối entries |
| Directory | Có | TOC và data files có thể được đọc bởi nhiều workers |
| Tar | Không | Không hỗ trợ chế độ parallel restore |
| Plain | Không qua pg_restore | Restore bằng psql script |

Ví dụ custom:

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

Ví dụ directory:

~~~bash
pg_restore -j 4 -d appdb_restore appdb_dir
~~~

Không dùng -j với tar hoặc plain để kỳ vọng parallel restore.

## 16. Chọn số jobs

Số jobs là số worker/connections tối đa pg_restore dùng cho parallel restore. Chọn giá trị dựa trên tài nguyên target, không chỉ số core CPU.

Cân nhắc:

- CPU available.
- Disk throughput và IOPS.
- Storage latency.
- Memory và shared buffers.
- Connection limits.
- Index build concurrency.
- WAL generation.
- Physical replica replay rate.
- Workload ứng dụng khác đang chạy.

Bắt đầu từ số nhỏ rồi benchmark. Ví dụ có thể thử 2–4 jobs trên staging, đo rồi điều chỉnh. Đây là điểm khởi đầu minh họa, không phải mặc định production.

### Khi tăng jobs có thể không nhanh hơn?

- Disk đã đạt giới hạn throughput.
- CPU đã bão hòa.
- WAL replay ở replica không theo kịp.
- Target có ít table độc lập.
- Index builds cạnh tranh cùng storage.
- Lock contention tăng.
- Network hoặc backup source chậm.

Tăng jobs có thể làm restore lâu hơn nếu worker tranh chấp cùng tài nguyên.

## 17. Parallel restore và số kết nối

Mỗi worker cần một connection tới database đích. Ngoài các workers còn có connection quản trị, monitoring và ứng dụng.

Trước khi chạy:

- Kiểm tra max_connections.
- Tính connection pool đang sử dụng.
- Dành headroom cho administrator/monitoring.
- Kiểm tra connection limits theo role/database.
- Tránh để restore làm cạn connection slots.

Nếu có connection proxy/pooler, xác minh mode hoạt động có tương thích với restore nhiều sessions và các lệnh session-level của pg_restore.

## 18. Parallel restore và single transaction

Có hai lựa chọn restore quan trọng:

### Parallel jobs

~~~bash
pg_restore -j 4 -d appdb_restore appdb.dump
~~~

Nhiều workers chạy song song. Không thể gom toàn bộ operation thành một transaction duy nhất.

### Single transaction

~~~bash
pg_restore --single-transaction --exit-on-error -d appdb_restore appdb.dump
~~~

--single-transaction/-1 gom các lệnh restore vào một transaction. Nếu có lỗi và transaction rollback, các thay đổi trong transaction không được commit một phần.

Đánh đổi:

- Không tương thích với -j parallel jobs.
- Transaction lớn có thể giữ lock và resources lâu.
- Có thể tăng thời gian rollback.
- Một số command không chạy được trong transaction block.
- Các lệnh tạo/xóa database không phù hợp với single transaction.

Chỉ dùng single transaction khi archive và target operation tương thích, đồng thời có lý do rõ ràng cần all-or-nothing.

## 19. Xử lý lỗi: exit-on-error

Mặc định pg_restore có thể tiếp tục một số công việc sau khi gặp lỗi, rồi báo tổng kết. Điều này có thể hữu ích khi muốn thu thập nhiều lỗi trong một lần chạy, nhưng database có thể ở trạng thái restore dở dang.

Dùng:

~~~bash
pg_restore --exit-on-error -d appdb_restore appdb.dump
~~~

--exit-on-error yêu cầu dừng khi có lỗi đầu tiên. Trong automation production, thường nên dùng để pipeline nhận biết restore thất bại sớm và không đánh dấu database là sẵn sàng.

### Luôn kiểm tra exit code

Không chỉ dựa vào dòng cuối log. Script orchestration cần kiểm tra process exit status và ghi lại stderr/stdout.

Nếu lệnh restore fail:

1. Ghi lại lỗi đầu tiên và các lỗi phụ.
2. Xác định phase/object thất bại.
3. Kiểm tra database đích đã thay đổi đến đâu.
4. Chọn retry, restore lại database sạch hoặc selective recovery.
5. Không mở traffic tới database chưa qua validation.

## 20. Clean trước khi restore

Option:

~~~bash
pg_restore --clean --if-exists -d appdb_restore appdb.dump
~~~

- --clean yêu cầu drop các objects trước khi tạo lại.
- --if-exists thêm IF EXISTS cho các lệnh drop khi phù hợp.

Nếu database có dữ liệu đang dùng, clean có thể xóa objects và dữ liệu hiện có. Xác nhận đúng target và scope trước khi chạy.

### Clean không làm database trở thành hoàn toàn mới

Nó drop các objects có trong archive theo phạm vi restore. Những objects không có trong archive có thể vẫn tồn tại. Nếu mục tiêu là database sạch, tạo database mới từ template0 thường dễ kiểm soát hơn.

### Clean và dependency

pg_restore sắp xếp các lệnh drop/create theo TOC/dependency. Nếu list đã bị chỉnh sửa hoặc target có dependencies khác, drop có thể lỗi. Kiểm tra log và không dùng --clean như cách chữa lỗi duplicate object mà chưa hiểu trạng thái đích.

## 21. Tạo database từ archive với --create

Có thể yêu cầu pg_restore tạo database được ghi trong archive:

~~~bash
pg_restore --create --dbname=postgres appdb.dump
~~~

--dbname=postgres là database ban đầu mà pg_restore kết nối để chạy lệnh tạo database. Khi dùng --create, database đích được tạo theo tên metadata trong archive và pg_restore kết nối tới database đó để restore.

### Đổi tên database đích

Nếu muốn restore archive vào tên mới, workflow thường rõ ràng hơn:

1. Tạo database mới bằng createdb/template0.
2. Restore archive vào database mới bằng --dbname, không dùng --create.

Ví dụ:

~~~bash
createdb -T template0 appdb_recovered
pg_restore --dbname=appdb_recovered --exit-on-error appdb.dump
~~~

Đừng hiểu --dbname=appdb_recovered kết hợp --create là luôn đổi tên archive database; --create sử dụng tên database được ghi trong archive.

## 22. Owner và ACL

Archive có thể chứa ownership và ACL metadata.

Khi target không có các role nguồn, có thể bỏ owner/ACL:

~~~bash
pg_restore --no-owner --no-acl -d appdb_restore appdb.dump
~~~

- --no-owner: không phát các lệnh đặt owner như trong archive.
- --no-acl: không restore GRANT/REVOKE được lưu trong archive.

Có thể dùng:

~~~bash
pg_restore --role=app_owner -d appdb_restore appdb.dump
~~~

--role yêu cầu pg_restore thực hiện SET ROLE sau khi kết nối, nếu user kết nối có quyền phù hợp.

### Bỏ owner không tạo role

Nếu cần giữ ownership và grants nguyên vẹn, hãy tạo global roles/memberships trước khi restore. pg_restore không tự tạo các role toàn cluster từ database archive.

Global objects có thể được backup bằng:

~~~bash
pg_dumpall --globals-only > globals.sql
~~~

Script globals có thể chứa role attributes, memberships và tablespaces. Bảo vệ file này như dữ liệu quản trị nhạy cảm.

## 23. Tablespaces và extension

### Tablespaces

Archive có thể tham chiếu tablespace của nguồn. Target phải có tablespace phù hợp hoặc dùng:

~~~bash
pg_restore --no-tablespaces -d appdb_restore appdb.dump
~~~

Option này bỏ các lệnh gán tablespace trong archive để objects dùng tablespace mặc định của target theo semantics restore.

### Extensions

Archive có thể chứa lệnh CREATE EXTENSION nhưng không đóng gói binary extension của server.

Trước khi restore:

- Cài package/extension tương thích trên host target.
- Kiểm tra version extension.
- Kiểm tra shared libraries và control files.
- Xác định extension có cần upgrade sau restore hay không.
- Xem quyền tạo extension và policy bảo mật.

Một extension không có trên target có thể khiến restore thất bại ở bước tạo object phụ thuộc.

## 24. Large objects và sequence

### Large objects

Archive có thể chứa large objects được pg_dump xuất. Nếu ứng dụng sử dụng Large Object API, hãy xác minh số lượng và quyền truy cập sau restore. Đừng nhầm large objects với bytea/TOAST columns.

### Sequences

pg_restore phục hồi sequence definitions và dữ liệu sequence theo archive. Sau restore cần xác minh:

- Sequence tồn tại.
- Ownership/identity dependency đúng.
- Giá trị hiện tại phù hợp dữ liệu table.
- Insert mới không va chạm khóa hiện có.

Không reset sequence theo MAX(id) một cách máy móc nếu sequence có increment, cycle, cache hoặc semantics riêng.

## 25. Restore dữ liệu và triggers

Data-only restore có thể tương tác với triggers/constraints trên target. Có option:

~~~bash
pg_restore --disable-triggers --data-only -d appdb_restore appdb.dump
~~~

Option này tắt triggers trong lúc nạp dữ liệu và bật lại sau đó theo cơ chế pg_restore. Nó yêu cầu quyền cao (thường superuser) và chỉ dùng khi hiểu rõ tác động.

Không tắt triggers chỉ để restore nhanh hơn nếu triggers duy trì business invariants, audit data hoặc integrity. Nếu có lỗi giữa quá trình, kiểm tra trạng thái triggers và constraint trước khi mở ứng dụng.

Thông thường, restore archive đầy đủ theo dependency order là lựa chọn an toàn hơn. pg_restore có thể tạo schema trước, nạp data và tạo nhiều indexes/constraints ở post-data.

## 26. Chọn restore vào script hay database

Xuất SQL script:

~~~bash
pg_restore --file=restore.sql appdb.dump
~~~

Review hoặc lưu script, sau đó chạy:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f restore.sql
~~~

Ưu điểm:

- Review SQL trước khi chạy.
- Có thể chỉnh sửa theo môi trường.
- Có thể lưu output như artifact migration.
- Dễ quan sát chính xác câu lệnh.

Hạn chế:

- Script có thể rất lớn.
- Mất khả năng parallel restore của pg_restore.
- Chọn object/ordering phải chuẩn bị trước khi xuất hoặc chỉnh script.
- Cần psql để chạy.

Khi cần parallel restore, kết nối pg_restore trực tiếp bằng --dbname.

## 27. Dùng TOC list để bỏ qua một object

Ví dụ workflow:

~~~bash
pg_restore -l appdb.dump > appdb.list
~~~

Mở appdb.list, comment các entries không muốn restore theo cú pháp list, sau đó:

~~~bash
pg_restore -L appdb.list --exit-on-error -d appdb_restore appdb.dump
~~~

Có thể dùng cùng parallel jobs nếu archive và các options hỗ trợ:

~~~bash
pg_restore -j 4 -L appdb.list -d appdb_restore --exit-on-error appdb.dump
~~~

### Giữ file list như một artifact

Nên lưu:

- Archive filename/checksum.
- File TOC gốc.
- File TOC đã chỉnh.
- Người review và lý do loại object.
- Command restore.
- Target database/version.
- Kết quả restore/validation.

Như vậy selective restore có thể được tái hiện khi cần.

## 28. Restore một table từ archive

Ví dụ:

~~~bash
pg_restore \
  --table=orders \
  --schema=sales \
  --dbname=appdb_restore \
  --exit-on-error \
  appdb.dump
~~~

Sau đó xác minh:

~~~sql
SELECT count(*) FROM sales.orders;
SELECT * FROM sales.orders ORDER BY order_id DESC LIMIT 5;
~~~

Cần kiểm tra thêm sequence, indexes, constraints và foreign keys. Nếu table phụ thuộc type/function ở schema khác, chuẩn bị chúng trước hoặc điều chỉnh TOC list.

### Chuyển dữ liệu giữa hai database

Có thể dùng archive chọn lọc để phục hồi table vào database khác, nhưng pg_restore không tự map schema/data sang cấu trúc khác. Nếu column types hoặc table definition khác nhau, dùng migration/ETL hoặc staging table và INSERT...SELECT có kiểm soát.

## 29. Restore theo schema và data phase

Một quy trình nhiều phase:

~~~bash
pg_restore --section=pre-data --exit-on-error -d appdb_restore appdb.dump
pg_restore --section=data --exit-on-error -d appdb_restore appdb.dump
pg_restore --section=post-data --exit-on-error -d appdb_restore appdb.dump
~~~

Lợi ích:

- Biết rõ thời gian tạo schema.
- Theo dõi riêng data loading.
- Tạo indexes/constraints sau khi data đã nạp.
- Dễ khoanh vùng lỗi.

Nhược điểm:

- Phải giữ đúng thứ tự.
- Mỗi lệnh có thể cần kiểm tra exit code riêng.
- Nếu phase giữa thất bại, target ở trạng thái chưa hoàn chỉnh.
- Không nên cho ứng dụng sử dụng database giữa các phase.

## 30. Parallel restore có hỗ trợ TOC list không?

Có thể kết hợp archive list với -j trong các định dạng và version hỗ trợ:

~~~bash
pg_restore -j 4 -L appdb.list -d appdb_restore appdb.dump
~~~

pg_restore vẫn phải tôn trọng dependency ordering. Việc chỉnh list sai thứ tự có thể khiến object cần thiết chưa tồn tại khi một worker bắt đầu công việc.

Không dùng list để đảo tùy tiện các object phụ thuộc. Nếu cần thứ tự đặc biệt, hiểu dependency và thử trên staging.

## 31. Theo dõi tiến trình restore

### pg_stat_activity

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE datname = 'appdb_restore'
ORDER BY query_start;
~~~

Có thể thấy nhiều sessions do pg_restore mở khi chạy parallel. Các query và wait events giúp nhận diện worker đang COPY, CREATE INDEX hoặc chờ tài nguyên.

### Progress của CREATE INDEX

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index
ORDER BY pid;
~~~

Index creation có thể chiếm phần lớn thời gian restore ở database nhiều indexes.

### Progress của COPY

Một số PostgreSQL versions cung cấp pg_stat_progress_copy để theo dõi lệnh COPY:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    command,
    type,
    bytes_processed,
    bytes_total,
    tuples_processed
FROM pg_stat_progress_copy
ORDER BY pid;
~~~

Cột và khả năng hiển thị phụ thuộc version và loại COPY. pg_restore có thể dùng cơ chế nạp dữ liệu khác nhau tùy archive/target options; không phải mọi giai đoạn restore đều xuất hiện ở view này.

### Không suy ETA từ một counter

Một counter có thể đứng yên trong lúc worker chờ lock, index build, WAL flush hoặc dependency. Hãy kết hợp phase, wait events, logs, disk/CPU metrics và số lượng archive entries còn lại.

## 32. Theo dõi lock và transaction

Restore có thể chờ lock hoặc bị DDL khác cản trở. Xem:

~~~sql
SELECT
    a.pid,
    a.state,
    a.xact_start,
    a.query_start,
    a.wait_event_type,
    a.wait_event,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_stat_activity AS a
LEFT JOIN pg_locks AS l
    ON l.pid = a.pid
WHERE a.datname = 'appdb_restore'
ORDER BY a.query_start;
~~~

Đặc biệt theo dõi:

- DDL hoặc maintenance khác trên target.
- Long-running transactions.
- Lock waits.
- Connection slots.
- Sessions từ application nếu database đã được mở sớm.

Một restore database mới thường nên chạy trong môi trường không có ứng dụng ghi đồng thời.

## 33. Tối ưu tốc độ restore

Các biện pháp thường cân nhắc:

1. Chọn custom/directory archive nếu cần parallel restore.
2. Dùng -j vừa với CPU và storage.
3. Tạo database đích trống và chuẩn bị dependencies trước.
4. Dùng pre-data/data/post-data nếu workflow cần kiểm soát phase.
5. Đánh giá index build và constraints.
6. Theo dõi WAL generation và replica replay.
7. Tránh workload ứng dụng cạnh tranh.
8. Đặt target storage phù hợp.
9. Kiểm tra connection budget.
10. Chạy ANALYZE sau bulk restore khi cần.

Không vô hiệu hóa constraints/triggers hoặc giảm durability settings tùy tiện. Mọi thay đổi durability có thể làm tăng rủi ro mất dữ liệu nếu server gặp sự cố trước khi restore hoàn tất và được bảo vệ đúng cách.

## 34. Restore và WAL/replication

Restore tạo nhiều thay đổi trên target và có thể sinh WAL lớn.

Với primary có physical standby:

- Replica phải replay WAL.
- Replication lag có thể tăng.
- WAL archive/replication slots có thể giữ nhiều WAL.
- Disk primary và replica có thể tăng nhanh.
- Standby query latency có thể thay đổi.

Trước restore lớn, kiểm tra:

- WAL filesystem headroom.
- Archive command/backup pipeline.
- Replication slot status.
- Replica replay rate.
- Disk throughput.
- Retention policy.

Không đánh dấu database phục hồi là sẵn sàng nếu replica hoặc backup pipeline chưa ổn định theo yêu cầu vận hành.

## 35. Khi restore thất bại giữa chừng

Mặc định restore có thể đã commit một phần công việc trước khi gặp lỗi. Nếu không dùng single transaction, database có thể chứa một số tables, data và indexes đã được tạo.

Cách xử lý:

1. Giữ lại log và exit code.
2. Xác định object/phase thất bại.
3. Kiểm tra database state và catalog.
4. Xác định có thể retry object riêng hay nên xóa database đích và restore lại.
5. Kiểm tra dependencies trước khi chạy lại.
6. Chạy validation đầy đủ trước khi mở traffic.

### Có thể chạy lại pg_restore không?

Có thể chạy lại một số object nếu hiểu rõ trạng thái và chọn TOC phù hợp. Nhưng chạy lại toàn archive vào database đã có objects thường gây duplicate-object errors hoặc xung đột dữ liệu.

Với môi trường phục hồi hoàn chỉnh, thường an toàn hơn khi tạo database đích mới và restore lại từ đầu nếu thời gian/tài nguyên cho phép.

### Không coi rerun là resume tự động

pg_restore không phải hệ thống checkpoint/resume toàn bộ restore theo từng row. Dùng TOC list để tiếp tục có chọn lọc cần người vận hành xác định những entries đã thành công và dependencies còn lại.

## 36. Xử lý duplicate objects

Lỗi thường gặp:

- Schema đã tồn tại.
- Table đã tồn tại.
- Index/constraint trùng.
- Function signature trùng.
- Role hoặc extension thiếu/khác.

Các hướng:

- Restore vào database mới.
- Dùng --clean --if-exists nếu chủ đích thay object.
- Chọn TOC entries phù hợp.
- Chuẩn bị dependency trước.
- Kiểm tra xem object hiện có có được ứng dụng sử dụng hay không.

Không xóa object bằng tay để làm lệnh restore qua lỗi khi chưa hiểu dependency và ownership.

## 37. Restore và quyền truy cập

User kết nối cần quyền phù hợp để tạo schema/table/index, nạp dữ liệu và đặt owner/ACL. Một số operations cần superuser hoặc quyền đặc biệt.

Nếu restore không giữ owner/ACL:

~~~bash
pg_restore --no-owner --no-acl --role=app_owner -d appdb_restore appdb.dump
~~~

Sau đó xác minh quyền:

~~~sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
ORDER BY table_name, grantee, privilege_type;
~~~

Đây là một góc nhìn về table grants; cần kiểm tra schema privileges, sequence privileges, function execute privileges và default privileges theo policy ứng dụng.

## 38. Restore và security labels/comments

Archive có thể chứa comments và security labels tùy object và option dump. Target phải hỗ trợ provider tương ứng cho security labels. Nếu provider không tồn tại, restore có thể lỗi.

Không bỏ qua security labels hoặc comments chỉ để lệnh thành công mà không xác định chúng có ý nghĩa compliance/audit hay không.

Kiểm tra TOC và log khi có lỗi ở các object metadata đặc biệt.

## 39. Restore trên server có locale/collation khác

Database dump không tự làm cho target có cùng OS locale, collation provider hoặc collation version.

Khác biệt có thể ảnh hưởng:

- Sort order.
- Unique index semantics.
- Text comparison.
- Query result ordering.
- Index validity/need for rebuild theo tình huống.
- Application behavior.

Trước restore production, xác nhận encoding, locale, collation provider/version và extension dependencies. Sau restore, kiểm tra cảnh báo collation version mismatch và xử lý theo hướng dẫn PostgreSQL tương ứng.

## 40. Kiểm tra database sau restore

Không dừng ở exit code. Cần xác minh nhiều lớp.

### Object inventory

~~~sql
SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

### Table row estimates

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
~~~

Đây là estimates, không phải row counts chính xác. Chọn các bảng quan trọng để đối chiếu bằng truy vấn phù hợp.

### Constraints

~~~sql
SELECT
    conname,
    contype,
    convalidated,
    conrelid::regclass AS table_name
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY conrelid::regclass::text, conname;
~~~

### Index validity

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    indisvalid,
    indisready,
    indislive
FROM pg_index
WHERE NOT indisvalid OR NOT indisready OR NOT indislive;
~~~

### Sequence

Kiểm tra các sequence/identity quan trọng và thử insert trong môi trường test theo cách an toàn. Không chạy INSERT thử trên production trước khi xác định tác động.

## 41. Smoke test và kiểm tra nghiệp vụ

Các bước sau restore nên gồm:

- Kết nối bằng application role.
- Đọc các bảng trọng yếu.
- Xác minh row counts hoặc aggregates quan trọng.
- Kiểm tra unique/foreign key constraints.
- Kiểm tra views/functions/procedures.
- Kiểm tra sequence/identity.
- Kiểm tra triggers.
- Kiểm tra large objects.
- Kiểm tra grants và schema privileges.
- Chạy query đại diện và đo latency.
- Xác nhận application health checks.

Một database có đầy đủ tables nhưng thiếu quyền hoặc extension vẫn có thể khiến ứng dụng không hoạt động.

## 42. Chuyển ứng dụng sang database đã restore

Nếu restore vào database mới, cutover nên có kế hoạch:

1. Restore và validate database đích.
2. Đồng bộ các thay đổi cuối cùng nếu workflow cần.
3. Chặn ghi hoặc chuyển ứng dụng theo quy trình migration.
4. Cập nhật connection string/secret/service discovery.
5. Mở traffic theo từng bước.
6. Theo dõi errors, latency và connection pool.
7. Giữ database cũ theo retention/rollback policy.
8. Chỉ xóa database cũ sau khi xác nhận và hết thời gian rollback.

Không xóa database nguồn ngay sau khi restore thành công. Giữ khả năng quay lại theo policy và xác định rõ điểm không thể rollback.

## 43. Restore selective trong incident

Khi chỉ một table bị mất hoặc hỏng, có thể restore table từ archive vào database tạm:

1. Tạo database recovery riêng.
2. Restore schema/dependencies cần thiết.
3. Restore table/data vào database tạm.
4. Xác minh rows và constraints.
5. So sánh dữ liệu với production hiện tại.
6. Chuyển dữ liệu có chọn lọc bằng INSERT/UPDATE có transaction.
7. Đối chiếu sequence và foreign keys.
8. Ghi audit về dữ liệu đã phục hồi.

Không restore đè trực tiếp table production khi chưa biết trạng thái các rows hiện tại và tác động của triggers/foreign keys.

## 44. Plain SQL restore khác archive restore ở đâu?

| Tác vụ | Plain SQL | Custom/Directory/Tar |
| --- | --- | --- |
| Công cụ | psql | pg_restore |
| Xem nội dung | Text editor | pg_restore -l hoặc pg_restore -f |
| Chọn object | Chọn lúc dump hoặc sửa script cẩn thận | TOC và options |
| Parallel restore | Không | Custom/Directory |
| Section restore | Không có archive TOC; cần script riêng | Có |
| Exit on error | psql ON_ERROR_STOP | pg_restore --exit-on-error |
| Single transaction | psql -1 nếu script tương thích | pg_restore --single-transaction |
| Dependency ordering | Theo thứ tự script | TOC/dependency scheduler |

Nếu quy trình cần restore linh hoạt, custom/directory archive thường phù hợp hơn plain script.

## 45. Ví dụ workflow hoàn chỉnh: custom archive

Tạo database đích:

~~~bash
createdb -T template0 appdb_recovered
~~~

Restore:

~~~bash
pg_restore \
  --dbname=appdb_recovered \
  --exit-on-error \
  --verbose \
  appdb.dump
~~~

Nếu cần bỏ owner/ACL:

~~~bash
pg_restore \
  --dbname=appdb_recovered \
  --no-owner \
  --no-acl \
  --exit-on-error \
  appdb.dump
~~~

Sau đó kiểm tra:

~~~sql
SELECT current_database();
SELECT count(*) FROM public.orders;
~~~

Đối chiếu các invariants nghiệp vụ và kiểm tra roles/extensions/constraints trước cutover.

## 46. Ví dụ workflow hoàn chỉnh: parallel restore

Chuẩn bị database:

~~~bash
createdb -T template0 appdb_recovered
~~~

Restore:

~~~bash
pg_restore \
  --jobs=4 \
  --dbname=appdb_recovered \
  --exit-on-error \
  --verbose \
  appdb.dump
~~~

Trong khi chạy, theo dõi:

- pg_stat_activity.
- pg_stat_progress_create_index.
- pg_stat_progress_copy nếu phù hợp version/operation.
- CPU, I/O, memory.
- WAL rate và replica lag.
- Disk free space.
- Server logs.

Sau khi hoàn tất, kiểm tra catalog, row counts, constraints và application smoke tests.

## 47. Ví dụ workflow selective restore với TOC

~~~bash
pg_restore --list appdb.dump > appdb.list
~~~

Review và chỉnh appdb.list, sau đó:

~~~bash
createdb -T template0 recovery_subset
pg_restore \
  --use-list=appdb.list \
  --dbname=recovery_subset \
  --exit-on-error \
  appdb.dump
~~~

Nếu archive custom/directory và dependencies phù hợp, có thể thêm:

~~~bash
pg_restore -j 4 -L appdb.list -d recovery_subset --exit-on-error appdb.dump
~~~

Ghi nhận entries đã loại và kiểm tra database subset có đủ object phục vụ mục tiêu incident/test hay không.

## 48. Những sai lầm thường gặp

1. **Dùng pg_restore cho plain SQL**, trong khi plain script phải được nạp bằng psql.
2. **Dùng tar với -j**, dù tar không hỗ trợ parallel restore.
3. **Nghĩ -j chia một table lớn thành nhiều worker**, trong khi parallelism chủ yếu giữa các archive items độc lập.
4. **Tăng jobs mà không tính connection budget**, làm cạn max_connections.
5. **Tăng jobs trên storage đã bão hòa**, khiến restore chậm hơn.
6. **Dùng -t và giả định dependencies tự được restore**, dẫn tới thiếu type/function/schema.
7. **Chỉnh TOC list mà không xem dependency**, gây lỗi ở object phía sau.
8. **Restore post-data trước data**, khiến indexes/constraints thiếu object hoặc dữ liệu.
9. **Dùng --clean trên database đang phục vụ**, có thể xóa dữ liệu hiện tại.
10. **Dùng --create nhưng hiểu nhầm --dbname là tên database mới**, dẫn tới tạo sai target.
11. **Bỏ owner/ACL mà không tái tạo quyền**, làm ứng dụng mất quyền truy cập.
12. **Không chuẩn bị roles/global objects**, khiến owner/GRANT thất bại.
13. **Không cài extension trên target**, khiến object phụ thuộc không tạo được.
14. **Không chuẩn bị tablespaces**, khiến restore lỗi hoặc dùng storage sai.
15. **Bật --single-transaction cùng -j**, không được hỗ trợ.
16. **Dùng --single-transaction với command không chạy trong transaction**, làm restore thất bại.
17. **Không bật --exit-on-error trong automation**, rồi đánh dấu database sẵn sàng dù có lỗi.
18. **Rerun toàn archive vào database restore dở**, tạo duplicate objects và xung đột.
19. **Coi pg_restore -l là kiểm tra backup đầy đủ**, trong khi chỉ xác nhận TOC đọc được.
20. **Không theo dõi WAL/replication lag**, làm replica tụt lại.
21. **Không xác minh sequence/identity**, gây duplicate key khi ứng dụng ghi tiếp.
22. **Không kiểm tra constraints/index validity**, để database ở trạng thái thiếu integrity.
23. **Không kiểm tra locale/collation/extension version**, gây khác biệt hành vi.
24. **Mở traffic trước smoke test**, khiến lỗi restore trở thành lỗi production.
25. **Xóa database cũ ngay sau cutover**, mất đường rollback.
26. **Dùng --disable-triggers mà không hiểu business logic**, có thể bỏ qua integrity/audit behavior.
27. **Dùng selective restore vào production trực tiếp**, không qua staging và đối chiếu dữ liệu.
28. **Không kiểm tra quyền của user restore**, khiến lỗi phát sinh giữa chừng.

## 49. Bài tập thực hành có đáp án

### Bài 1. pg_restore dùng để làm gì?

**Đáp án:** Đọc archive custom, directory hoặc tar do pg_dump tạo để phục hồi schema/data vào database hoặc xuất SQL script.

### Bài 2. Plain SQL dump restore bằng gì?

**Đáp án:** psql, không phải pg_restore.

### Bài 3. Xem TOC archive bằng lệnh nào?

~~~bash
pg_restore -l appdb.dump
~~~

**Đáp án:** Liệt kê các archive entries.

### Bài 4. Chọn TOC list khi restore?

~~~bash
pg_restore -L appdb.list -d appdb_restore appdb.dump
~~~

**Đáp án:** Chỉ restore entries có trong list theo thứ tự list.

### Bài 5. Định dạng nào hỗ trợ parallel restore?

**Đáp án:** Custom và directory.

### Bài 6. Tar có hỗ trợ parallel restore không?

**Đáp án:** Không.

### Bài 7. Parallel restore dùng option nào?

**Đáp án:** -j hoặc --jobs.

### Bài 8. -j 4 có nghĩa gì?

**Đáp án:** Tối đa bốn restore workers/connections được điều phối; không bảo đảm mọi thời điểm có bốn jobs chạy.

### Bài 9. Vì sao một table khổng lồ không nhất thiết được tăng tốc gấp bốn?

**Đáp án:** Parallelism chủ yếu giữa archive items độc lập; một table data item có thể vẫn là một công việc.

### Bài 10. Restore một schema?

~~~bash
pg_restore -n sales -d appdb_restore appdb.dump
~~~

**Đáp án:** Chọn object trong schema sales theo pattern matching.

### Bài 11. Restore một table?

~~~bash
pg_restore -t orders -n sales -d appdb_restore appdb.dump
~~~

**Đáp án:** Chọn table orders; phải kiểm tra các dependencies riêng.

### Bài 12. Chia archive thành ba section nào?

**Đáp án:** pre-data, data và post-data.

### Bài 13. Vì sao post-data thường chạy sau data?

**Đáp án:** Nhiều indexes, triggers và constraints cần table/data đã tồn tại.

### Bài 14. --exit-on-error có tác dụng gì?

**Đáp án:** Dừng restore khi gặp lỗi đầu tiên.

### Bài 15. --single-transaction có lợi ích gì?

**Đáp án:** Gom các lệnh tương thích vào một transaction để rollback toàn bộ nếu có lỗi.

### Bài 16. Có thể dùng --single-transaction với -j không?

**Đáp án:** Không. Parallel jobs không tương thích với single transaction mode.

### Bài 17. --clean làm gì?

**Đáp án:** Drop các objects trong phạm vi restore trước khi tạo lại; có thể xóa dữ liệu hiện có.

### Bài 18. --if-exists có vai trò gì?

**Đáp án:** Thêm IF EXISTS cho các lệnh drop khi phù hợp, giảm lỗi khi object chưa tồn tại.

### Bài 19. --create kết hợp --dbname có nghĩa gì?

**Đáp án:** --dbname là database kết nối ban đầu; --create yêu cầu tạo database theo tên metadata trong archive.

### Bài 20. Muốn restore sang tên database mới nên làm gì?

**Đáp án:** Tạo database mới trước rồi restore vào bằng --dbname, không dùng --create.

### Bài 21. --no-owner và --no-acl khác nhau?

**Đáp án:** --no-owner bỏ lệnh đặt owner; --no-acl bỏ GRANT/REVOKE.

### Bài 22. pg_restore có tự tạo roles toàn cluster không?

**Đáp án:** Không. Dùng pg_dumpall --globals-only hoặc tạo roles riêng trước restore.

### Bài 23. --no-tablespaces dùng để làm gì?

**Đáp án:** Bỏ các lệnh gán tablespace từ archive để target dùng tablespace mặc định phù hợp.

### Bài 24. Vì sao cần cài extension trên target?

**Đáp án:** Archive lưu declaration, không đóng gói binary extension/server package.

### Bài 25. Vì sao restore thất bại có thể để lại database dở dang?

**Đáp án:** Nếu không dùng single transaction, các bước trước lỗi có thể đã commit.

### Bài 26. Có thể rerun toàn archive ngay sau lỗi không?

**Đáp án:** Không nên. Kiểm tra trạng thái object; thường tạo database mới và restore lại sạch sẽ dễ kiểm soát hơn.

### Bài 27. pg_stat_progress_create_index dùng để làm gì?

**Đáp án:** Theo dõi phase và progress của index build trong quá trình restore khi operation được view hỗ trợ.

### Bài 28. Vì sao phải theo dõi WAL và replica lag?

**Đáp án:** Restore tạo nhiều thay đổi/WAL; standby cần replay và có thể tụt lại.

### Bài 29. Kiểm tra index invalid ở đâu?

**Đáp án:** Catalog pg_index với các cột indisvalid, indisready và indislive.

### Bài 30. Điều kiện nào trước khi mở traffic sau restore?

**Đáp án:** Restore không có lỗi chưa xử lý; object, data, constraints, sequences, permissions, extensions và smoke tests đều đạt; replication/monitoring theo yêu cầu ổn định.

## 50. Checklist vận hành restore

- [ ] Xác định archive format và dùng đúng công cụ.
- [ ] Kiểm tra version pg_restore và target PostgreSQL.
- [ ] Đọc TOC trước selective restore.
- [ ] Chọn database đích và template/encoding/locale phù hợp.
- [ ] Chuẩn bị roles, memberships và tablespaces.
- [ ] Cài extension packages cần thiết.
- [ ] Xác định giữ hay bỏ owner/ACL.
- [ ] Kiểm tra dependencies của schema/table/object đã chọn.
- [ ] Giữ đúng thứ tự pre-data, data, post-data nếu chia phase.
- [ ] Chọn jobs theo CPU, disk, WAL và connection budget.
- [ ] Không dùng parallel restore với tar/plain.
- [ ] Không kết hợp --single-transaction với -j.
- [ ] Chỉ dùng --clean khi đã xác nhận phạm vi xóa.
- [ ] Hiểu ý nghĩa --create và --dbname.
- [ ] Dùng --exit-on-error cho automation cần dừng sớm.
- [ ] Lưu log và exit code.
- [ ] Theo dõi pg_stat_activity và progress views.
- [ ] Theo dõi lock waits, disk, WAL và replication lag.
- [ ] Kiểm tra trạng thái sau lỗi/cancel trước khi retry.
- [ ] Xác minh index validity, constraints và sequences.
- [ ] Kiểm tra large objects, extensions và ACL.
- [ ] Chạy smoke tests bằng application role.
- [ ] Đo RTO và so với mục tiêu.
- [ ] Giữ database cũ theo rollback/retention policy.
- [ ] Chỉ mở traffic sau khi validation hoàn tất.

## 51. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — options, archive restore, TOC list, parallel jobs và selective restore.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — archive formats, dump scope và compression.
- [psql](https://www.postgresql.org/docs/current/app-psql.html) — chạy plain SQL scripts và ON_ERROR_STOP.
- [pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html) — global objects và role backup.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — logical và physical backup.
- [SQL Dump](https://www.postgresql.org/docs/current/backup-dump.html) — quy trình dump/restore.
- [CREATE DATABASE](https://www.postgresql.org/docs/current/sql-createdatabase.html) — tạo database, template, encoding và locale.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — roles, memberships và privileges.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — quyền truy cập database objects.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — extension trên target.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) — storage placement.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity và thống kê.
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html) — progress views của COPY và CREATE INDEX.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html) — locale/collation behavior.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — phục hồi vật lý theo WAL.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Options, progress columns, parallel restore restrictions và một số hành vi có thể thay đổi theo major version; kiểm tra tài liệu cùng phiên bản client/server trước khi chạy production.

## 52. Tổng kết

**pg_restore phục hồi archive logic với khả năng chọn object, kiểm soát thứ tự và chạy nhiều jobs.** Kết quả an toàn phụ thuộc vào việc chọn đúng format, chuẩn bị dependencies, kiểm soát lỗi và xác minh database sau restore.

1. **Plain SQL dùng psql; custom, directory và tar dùng pg_restore.**
2. **Custom và directory hỗ trợ parallel restore; tar không hỗ trợ.**
3. **Parallel jobs chạy trên các archive items có thể độc lập**, không tự chia một table lớn thành nhiều phần.
4. **TOC và --use-list giúp chọn object**, nhưng người vận hành phải hiểu dependency.
5. **pre-data, data và post-data cần đúng thứ tự** khi restore theo section.
6. **--clean và --create có thể tác động mạnh tới database đích**, phải xác nhận target và phạm vi.
7. **--single-transaction không kết hợp với parallel jobs** và không phù hợp mọi command.
8. **Owner, ACL, roles, extension và tablespaces cần được chuẩn bị** để restore đúng security/storage model.
9. **Restore thất bại có thể để lại trạng thái một phần.** Kiểm tra catalog và cân nhắc restore lại vào database sạch.
10. **Theo dõi CPU, I/O, connection, WAL và replica lag** khi restore lớn.
11. **Kiểm tra sequence, constraints, index validity, permissions và smoke tests** trước khi mở traffic.
12. **Test restore định kỳ và đo RTO** để chứng minh backup có thể dùng khi sự cố.

Một quy trình khôi phục hoàn chỉnh phải chứng minh được database sau restore có đủ dữ liệu, đúng quyền, đúng dependencies và hoạt động được với ứng dụng trong thời gian mục tiêu.
