# Phục hồi vào môi trường cách ly trước khi thay thế hệ thống

Khi PostgreSQL gặp sự cố, restore backup thẳng vào vị trí production rồi lập tức mở traffic có thể khiến một sự cố dữ liệu trở thành sự cố dịch vụ lớn hơn. Bản backup có thể sai thời điểm, WAL chain có thể thiếu, roles/extensions có thể chưa sẵn sàng, hoặc dữ liệu đã phục hồi có thể chứa chính thao tác xóa nhầm mà đội vận hành đang cố khắc phục. Với lỗi logic, việc thay thế primary trước khi hiểu recovery point còn có thể làm mất các giao dịch hợp lệ được ghi sau thời điểm cần phục hồi.

Một quy trình an toàn là **phục hồi vào môi trường cách ly (isolated recovery environment), kiểm tra và xác nhận dữ liệu, sau đó mới quyết định trích xuất dữ liệu hay thay thế hệ thống đang chạy**. Môi trường cách ly cho phép DBA dựng bản sao từ logical dump hoặc physical backup, replay WAL tới recovery target, kiểm tra schema và business invariants, so sánh với nguồn còn hoạt động, và diễn tập cutover mà không để ứng dụng hoặc người dùng ghi nhầm vào cluster đang phục hồi.

Cách làm này đặc biệt quan trọng khi xử lý xóa nhầm, corruption logic, ransomware, migration, nâng cấp major version hoặc diễn tập DR. Mục tiêu là giữ rõ ranh giới giữa **khôi phục kỹ thuật**, **xác minh dữ liệu**, **quyết định thay thế**, và **chuyển traffic**. Mỗi giai đoạn có tiêu chí hoàn thành, người chịu trách nhiệm và bằng chứng riêng.

Bài học thuộc chương **Khôi phục** của module **Database Engine Relational PostgreSQL**. Nội dung tập trung vào quy trình restore vào môi trường độc lập trước khi thay thế hệ thống, từ chuẩn bị artifacts tới validation, promotion, cutover và quay lại trạng thái bảo vệ bình thường.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao cần restore vào môi trường cách ly trước khi thay primary.
- Phân biệt restore thử nghiệm, isolated recovery, selective data recovery và production cutover.
- Chọn logical dump, physical base backup, WAL/PITR hoặc standby phù hợp.
- Chuẩn bị PostgreSQL version, extensions, roles, tablespaces, keys và cấu hình cần thiết.
- Cô lập network, credentials, DNS, application clients và external side effects.
- Restore logical database bằng pg_restore/psql vào target mới.
- Restore physical backup và replay WAL tới recovery target.
- Dùng recovery pause để kiểm tra trước khi promote khi chiến lược PITR hỗ trợ.
- Xác minh schema, constraints, indexes, sequences, grants, RLS và dữ liệu nghiệp vụ.
- Xử lý recovery point khi lỗi logic và reconcile dữ liệu với production còn hoạt động.
- Lập kế hoạch fencing, write freeze, promotion và cutover để tránh split-brain.
- Đo RPO/RTO, diễn tập runbook và ghi lại bằng chứng phục hồi.
- Bảo vệ dữ liệu nhạy cảm trong bản restore và dọn môi trường cách ly sau khi hoàn tất.

## 2. Vì sao phải restore vào môi trường cách ly?

Một backup thành công chỉ chứng minh công cụ đã tạo artifact theo cơ chế của nó. Nó chưa chứng minh artifact đúng thời điểm, đủ dependencies, restore được, hay dữ liệu bên trong đáp ứng yêu cầu nghiệp vụ.

### 2.1. Tránh thay production bằng recovery point sai

Khi phục hồi PITR, chọn nhầm timestamp hoặc timeline có thể đưa database về trước một loạt giao dịch hợp lệ. Restore ở môi trường riêng cho phép kiểm tra trạng thái trước khi thay đổi endpoint production.

### 2.2. Phát hiện lỗi backup sớm

Backup có thể thiếu WAL segment, manifest, tablespace, extension hoặc encryption key. Nếu chỉ phát hiện sau khi production đã bị thay thế, thời gian gián đoạn và mức độ rủi ro sẽ tăng.

### 2.3. Cho phép điều tra lỗi logic

Khi một người dùng xóa nhầm bảng, thường không cần rollback cả production về trước thao tác đó. Có thể restore một bản PITR cô lập, trích bảng/rows cần cứu và merge vào hệ thống hiện tại sau khi kiểm tra dependencies.

### 2.4. Ngăn ứng dụng ghi vào database chưa xác minh

Một cluster mới khởi động có thể accept connections nhưng dữ liệu chưa đúng. Nếu app tự động kết nối qua DNS/service discovery, nó có thể phát sinh giao dịch trên recovery copy trước khi DBA xác nhận.

### 2.5. Giữ production hiện tại làm nguồn đối chiếu

Nếu primary vẫn còn hoạt động và không bị compromise, có thể so sánh các giao dịch sau recovery point, xác định phần nào cần giữ, phần nào cần phục hồi và cách merge.

## 3. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Kết quả mong đợi |
|---|---|---|
| Backup verification | Kiểm tra artifact/manifest/checksum | Biết backup có vẻ đầy đủ và đọc được |
| Restore test | Khôi phục vào môi trường thử nghiệm | Chứng minh quy trình restore chạy được |
| Isolated recovery | Phục hồi trong môi trường được cô lập | Có database để điều tra/xác minh an toàn |
| PITR | Replay WAL tới recovery target | Database ở một thời điểm đã chọn |
| Selective recovery | Trích một phần dữ liệu/objects | Lấy lại phần cần cứu |
| Promotion | Kết thúc recovery/standby và cho phép ghi | Cluster trở thành primary có thể ghi |
| Cutover | Chuyển ứng dụng/traffic sang target | Hệ thống mới phục vụ người dùng |
| DR declaration | Quyết định kích hoạt quy trình thảm họa | Incident được điều hành theo runbook |

### 3.1. Restore test không đồng nghĩa cutover

Một restore test có thể chạy trong subnet không có ứng dụng production. Nó không thay DNS, không promote hệ thống chính và không mở traffic.

### 3.2. Isolated recovery có thể chỉ để đọc

Trong một số tình huống, mục tiêu là xem dữ liệu trước lỗi và trích một vài records. Cluster có thể được giữ trong recovery pause hoặc chỉ cho phép read-only access.

### 3.3. Cutover là quyết định vận hành

Chỉ promote/cutover sau khi xác nhận recovery point, dữ liệu, dependencies, quyền truy cập, khả năng ghi và phương án tránh split-brain.

### 3.4. Production replacement và selective merge khác nhau

Nếu lỗi logic ảnh hưởng một bảng, restore cả cluster rồi thay primary có thể không phù hợp. Selective merge thường giữ production hiện tại và đưa phần dữ liệu cần cứu vào theo transaction có kiểm soát.

## 4. Mô hình môi trường cách ly

Một thiết kế phổ biến có primary production, backup storage và một recovery target độc lập.

~~~text
                   Production environment
                 +-------------------------+
Application ---->| Current PostgreSQL      |
                 +------------+------------+
                              |
                       Base backup / dump
                              |
                              v
                 +-------------------------+
                 | Backup + WAL repository |
                 | offsite / immutable     |
                 +------------+------------+
                              |
                         restore copy
                              |
                              v
                  Isolated recovery network
                 +--------------------------+
                 | Recovery PostgreSQL      |
                 | separate data directory  |
                 | separate port/endpoint   |
                 +------------+-------------+
                              |
                       validation / extract
                              |
                     approved decision only
                              |
                  +-----------+-----------+
                  |                       |
             Selective merge          DR cutover
                  |                       |
                  v                       v
             Current primary       Recovered primary
~~~

### 4.1. Tách biệt network

Recovery instance nên nằm trong subnet/VLAN/security group riêng, chỉ mở kết nối từ bastion hoặc recovery operator. Chặn application subnets, public ingress và các đường tự động discovery.

### 4.2. Tách credentials

Dùng role riêng cho recovery. Không tái sử dụng application credential có quyền ghi production. Secrets và KMS access cần sẵn sàng nhưng có audit.

### 4.3. Tách storage và data directory

Không restore đè lên PGDATA của primary đang chạy. Dùng host/VM/container/volume riêng và đường dẫn rõ ràng.

### 4.4. Tách endpoint và DNS

Recovery cluster có hostname/port riêng. Không dùng production DNS alias cho đến khi có cutover plan được phê duyệt.

### 4.5. External side effects

Chặn email, payment gateway, webhook, message consumers, scheduled jobs, ETL writers và background workers. Một recovery copy có thể chứa jobs sẽ chạy lại nếu ứng dụng kết nối.

## 5. Các kiểu cách ly theo mục tiêu

| Mục tiêu | Mức cách ly gợi ý | Quyền ghi |
|---|---|---|
| Kiểm tra backup định kỳ | Lab/test network | Chỉ operator |
| Điều tra xóa nhầm | Recovery subnet, không app clients | Read-only hoặc controlled writes |
| Trích bảng/rows | Isolated DB + export path kiểm soát | Operator theo transaction |
| Diễn tập DR | DR account/region độc lập | Chỉ runbook/automation |
| Chuẩn bị cutover | Candidate environment, traffic vẫn đóng | Write test được kiểm soát |
| Thay primary thật | Cutover network sau fencing | Mở ghi sau phê duyệt |

### 5.1. Cách ly theo network

Không có route từ ứng dụng production tới recovery instance. Cách này giảm nguy cơ app kết nối nhầm.

### 5.2. Cách ly theo identity

Chỉ recovery role được truy cập. Dùng IAM/DB roles độc lập, MFA/break-glass theo policy và audit logs.

### 5.3. Cách ly theo side effects

Nếu cần chạy ứng dụng để test, cấu hình sandbox endpoints cho email/payment/webhook và tắt consumers/schedulers. Không để test phát sinh hành động thật.

### 5.4. Cách ly theo dữ liệu

Nếu môi trường dành cho developer/test, phải xem masking/anonymization. Bản restore từ production vẫn là production data và phải chịu chính sách bảo vệ tương đương.

### 5.5. Cách ly không đồng nghĩa bỏ monitoring

Cần giám sát disk, CPU, restore progress, logs và network; chỉ giới hạn các clients được phép kết nối.

## 6. Chọn recovery source

Trước khi restore, xác định nguồn dữ liệu nào phù hợp với failure mode và RPO.

### 6.1. Logical dump

Dùng pg_dump/pg_dumpall khi cần database/schema/table objects ở snapshot. Phù hợp selective restore, migration và các database nhỏ/vừa.

### 6.2. Physical base backup

Dùng base backup để khôi phục toàn cluster vật lý. Kết hợp WAL archive nếu cần replay tới mốc sau base backup.

### 6.3. PITR

Chọn base backup hợp lệ và WAL chain/timeline đầy đủ, sau đó cấu hình recovery target. Đây là lựa chọn quan trọng khi cần quay lại trước một thao tác sai.

### 6.4. Standby hoặc replica

Có thể clone từ standby hoặc promote standby cho HA, nhưng cần đánh giá lag, timeline và logical corruption. Standby không thay lịch sử backup.

### 6.5. Managed service snapshot

Có thể restore snapshot/PITR sang instance mới theo cơ chế provider. Kiểm tra region, version, parameter group, extension, IAM, quota và restore behavior cụ thể.

## 7. Thu thập thông tin trước khi restore

Một recovery ticket/runbook nên ghi các thông tin tối thiểu:

- Incident ID và người điều hành.
- Failure mode: host/disk/region, xóa nhầm, corruption, ransomware hay diễn tập.
- Thời điểm sự cố và timezone.
- RPO/RTO đã phê duyệt.
- PostgreSQL version, platform và extension inventory.
- Backup ID, loại backup, snapshot/LSN/time và checksum/manifest.
- WAL segment range, timeline history và archive location.
- Tablespaces và storage paths.
- Roles, ownership, grants, RLS và secrets/key references.
- Database size, WAL volume, expected restore duration.
- Recovery target và lý do chọn.
- Network/identity isolation controls.
- Validation criteria và người có quyền phê duyệt.

### 7.1. Ghi recovery point rõ ràng

Đừng ghi “backup hôm qua”. Ghi backup identifier, timestamp UTC, timezone, LSN/timeline nếu có và WAL coverage.

### 7.2. Xác nhận artifact tồn tại ở nơi DR

Một bản backup ở cùng storage account/region với primary có thể không còn khả dụng trong disaster. Dùng identity và network của DR để kiểm tra.

### 7.3. Kiểm tra checksum/manifest

Nếu công cụ cung cấp manifest/checksum, xác minh trước khi tải/restore. Checksum chỉ chứng minh bytes phù hợp, không chứng minh business correctness.

### 7.4. Kiểm tra encryption key

Thử quyền truy cập key bằng DR identity. Không chờ tới khi restore xong mới phát hiện key bị thiếu/quyền bị thu hồi.

### 7.5. Kiểm tra version và extension

Cần biết PostgreSQL major version, tool version và extension binaries/versions. Physical restore thường cần môi trường tương thích với cluster backup.

## 8. Chuẩn bị target PostgreSQL

Target phải đủ khả năng nhận dữ liệu và chạy workload cần xác minh.

### 8.1. PostgreSQL major version

Với physical restore, dùng major version tương thích với base backup. Không dùng physical backup của một major version như thể là data directory cho major version khác. Logical migration có thể đi giữa major versions khi objects/extensions tương thích.

### 8.2. Minor version và binaries

Dùng bản minor release phù hợp theo chính sách hỗ trợ và compatibility. Chuẩn bị binaries, shared libraries, locale/collation dependencies và extension packages.

### 8.3. Extensions

Liệt kê extensions đã cài trong database và cài package tương ứng trước khi restore/khởi động. SQL extension metadata không thay thế shared library trên host.

### 8.4. Locale, encoding và collation

Logical database creation cần encoding/locale phù hợp. Collation provider/version khác có thể ảnh hưởng sort order, indexes và query behavior.

### 8.5. Capacity

Dự trù data files, indexes, TOAST, WAL replay, temporary files, logs và headroom. Restore target không nên đầy disk ở giữa quá trình.

## 9. Chuẩn bị roles, tablespaces và cấu hình

Logical dump và physical backup có phạm vi metadata khác nhau.

### 9.1. Global objects

Một pg_dump cho một database không bao gồm toàn bộ cluster-level roles và tablespaces. Có thể dùng pg_dumpall với tùy chọn globals-only để lưu global objects theo quy trình.

### 9.2. Roles và ownership

Xác minh login roles, memberships, role attributes, grants, default privileges và ownership. Không cấp superuser cho application roles chỉ để làm restore dễ hơn.

### 9.3. Password verifiers và secrets

Nếu phục hồi role definitions, xử lý password verifiers theo chính sách. Secrets bên ngoài database cần được cấp qua secret manager, không ghi vào script hoặc log.

### 9.4. Tablespaces

Physical backup có thể tham chiếu tablespace locations. Target phải chuẩn bị paths/permissions hoặc mapping phù hợp; không restore vào path không tồn tại.

### 9.5. Server configuration

Lưu/khôi phục có kiểm soát các setting cần thiết như memory, WAL, archive, authentication, TLS, logging và connection limits. Không sao chép nguyên config production nếu nó chứa paths, credentials hoặc network bindings không phù hợp môi trường cách ly.



## 10. Restore logical backup vào database mới

Logical restore tạo objects và nạp dữ liệu vào database target. Nên dùng database/cluster mới trong recovery environment, giữ endpoint riêng và không cho ứng dụng production kết nối.

### 10.1. Kiểm tra dump trước khi restore

Với custom archive:

~~~bash
pg_restore --list appdb.dump
~~~

Danh sách TOC giúp xác nhận archive đọc được và xem objects có trong backup. Với plain SQL, kiểm tra file/header và dùng môi trường thử nghiệm để chạy psql.

### 10.2. Khôi phục global objects khi cần

Một quy trình có thể tạo globals riêng:

~~~bash
pg_dumpall --globals-only --file=globals.sql
~~~

Chỉ restore globals vào target mới sau khi kiểm tra roles/tablespaces. Nếu target đã có roles trùng tên, cần xử lý conflict theo kế hoạch; không chạy mù quáng lên cluster đang dùng.

### 10.3. Tạo database rỗng

~~~bash
createdb --template=template0 --encoding=UTF8 recovery_app
~~~

Ví dụ này dùng UTF8; nếu production dùng locale/collation cụ thể, tạo database với cùng yêu cầu phù hợp nền tảng. Cú pháp locale khác nhau theo OS và PostgreSQL version.

### 10.4. Restore custom archive

~~~bash
pg_restore --verbose --exit-on-error --dbname=recovery_app appdb.dump
~~~

Nếu cần khôi phục ownership, roles và grants, phải chuẩn bị global objects/roles trước và không dùng tùy chọn bỏ owner một cách vô thức.

### 10.5. Restore plain SQL

~~~bash
psql -X --set ON_ERROR_STOP=on --dbname=recovery_app --file=appdb.sql
~~~

Tùy chọn ON_ERROR_STOP làm psql dừng khi gặp lỗi SQL thay vì tiếp tục âm thầm qua các objects thất bại.

## 11. Logical restore: parallelism và object selection

### 11.1. Parallel restore

Custom và directory archives có thể hỗ trợ parallel restore:

~~~bash
pg_restore --jobs=4 --exit-on-error --dbname=recovery_app appdb.dump
~~~

Chọn số jobs theo CPU, storage throughput, memory và database size. Tăng jobs không luôn làm restore nhanh hơn; nhiều index builds đồng thời có thể bão hòa disk.

### 11.2. Directory format

Directory format chia archive thành nhiều files và phù hợp parallel dump/restore theo công cụ. Phải copy toàn bộ directory và giữ nguyên cấu trúc.

### 11.3. Chỉ restore schema

~~~bash
pg_restore --schema-only --dbname=recovery_app appdb.dump
~~~

Có ích để kiểm tra DDL, nhưng không chứng minh data có thể phục hồi.

### 11.4. Chỉ restore data

~~~bash
pg_restore --data-only --dbname=recovery_app appdb.dump
~~~

Target phải có schema phù hợp; constraints, triggers và ordering có thể ảnh hưởng quá trình nạp.

### 11.5. Chọn một table

~~~bash
pg_restore --table=public.orders --dbname=recovery_app appdb.dump
~~~

Selective restore có thể thiếu dependencies như types, sequences, functions, referenced tables, grants hoặc extension objects. Thường an toàn hơn khi restore vào một database tạm đầy đủ rồi trích dữ liệu cần cứu.

## 12. Logical restore: ownership, grants và constraints

### 12.1. --no-owner

Tùy chọn `--no-owner` bỏ lệnh thay đổi ownership trong archive và tạo objects dưới role restore. Dùng khi target không có role gốc hoặc muốn map ownership có chủ đích.

### 12.2. --no-acl

Tùy chọn `--no-acl` bỏ lệnh GRANT/REVOKE trong archive. Chỉ dùng khi grants sẽ được thiết lập lại bằng policy riêng; nếu không, quyền sau restore có thể khác production.

### 12.3. --clean

`--clean` yêu cầu pg_restore drop objects trước khi tạo lại. Với isolated target rỗng, thường không cần. Nếu dùng trên database có dữ liệu, có thể xóa objects ngoài dự kiến.

### 12.4. --if-exists

Có thể kết hợp với clean để tránh lỗi khi object chưa tồn tại, nhưng nó không biến restore destructive thành thao tác an toàn. Phải xác định target và scope trước.

### 12.5. Constraint validation

Sau restore, xác nhận constraints tồn tại và valid. Không kết luận thành công chỉ vì command exit code 0 nếu logs có warnings hoặc objects bị skip theo options.

## 13. Phục hồi chọn lọc từ database cách ly

Khi lỗi logic chỉ ảnh hưởng một phần dữ liệu, recovery copy có thể dùng làm nguồn để merge.

### 13.1. Không rollback toàn production ngay

Production có thể đã nhận giao dịch hợp lệ sau lỗi. Thay toàn database bằng PITR cũ sẽ làm mất những giao dịch đó.

### 13.2. Restore vào database tạm

Restore logical dump hoặc PITR cluster vào môi trường riêng. Đặt tên database rõ như recovery_before_delete, không trùng tên ứng dụng.

### 13.3. Trích bảng hoặc rows

Có thể dùng COPY/psql, FDW, dump table hoặc query qua connection riêng để lấy dữ liệu. Giữ extraction artifacts có checksum và audit.

### 13.4. Xem dependencies

Rows có thể tham chiếu foreign keys, sequences, lookup tables, audit history hoặc object storage keys. Cần xác định thứ tự và tính đầy đủ.

### 13.5. Merge bằng transaction có kiểm soát

Dùng staging table, unique keys, conflict rules và transaction boundaries rõ. Kiểm tra số rows trước/sau, duplicate handling và business invariants.

## 14. Chuẩn bị physical restore

Physical restore dựng lại cluster từ base backup. Đây là lựa chọn phổ biến cho PITR và phục hồi database lớn.

### 14.1. Chọn base backup

Chọn một backup hợp lệ có thể replay tới recovery target. Ghi lại backup ID, PostgreSQL version, timeline, start/end LSN và tablespaces.

### 14.2. Xác minh WAL chain

Đảm bảo WAL segments từ base backup tới target có mặt, cùng timeline history files cần thiết. Thiếu segment có thể làm recovery dừng trước target.

### 14.3. Chuẩn bị data directory riêng

Tạo directory/volume trống, đúng owner/permissions và đủ dung lượng. Không restore đè vào data directory của primary đang chạy.

### 14.4. Tablespaces

Khôi phục tablespaces vào paths phù hợp với target. Nếu dùng mapping/relocation, kiểm tra symbolic links và permissions theo công cụ backup.

### 14.5. WAL directory và archive access

Chuẩn bị nơi lưu WAL hiện tại, quyền đọc archive và credentials/network để recovery server lấy được WAL. Tránh để recovery server có quyền xóa archive source.

## 15. Restore physical base backup

Một ví dụ lấy base backup từ server nguồn vào target riêng:

~~~bash
pg_basebackup \
  --host=primary.example.internal \
  --username=replicator \
  --pgdata=/srv/recovery/pgdata \
  --format=plain \
  --wal-method=stream \
  --progress
~~~

Đây là ví dụ minh họa cho lúc nguồn còn truy cập được. Trong disaster, thường restore từ backup repository bằng công cụ/catalog đã chọn.

### 15.1. Quyền replication

Role dùng pg_basebackup cần quyền phù hợp và pg_hba.conf cho phép kết nối. Dùng credential ngắn hạn/secret manager theo policy.

### 15.2. Không lấy backup từ primary bị nghi compromise

Nếu failure mode là ransomware hoặc unauthorized access, chỉ dùng artifacts từ backup domain đã xác minh sạch.

### 15.3. --wal-method=stream

Streaming WAL trong lúc base backup giúp lấy WAL cần thiết cho tính nhất quán của backup theo cơ chế pg_basebackup. Nó không thay thế archive WAL cần cho PITR sau thời điểm backup.

### 15.4. --write-recovery-conf / -R

Tùy chọn này tạo cấu hình để instance chạy như standby và kết nối upstream. Nếu mục tiêu là PITR archive recovery độc lập, đừng dùng -R một cách máy móc; kiểm tra recovery mode và signal files.

### 15.5. Xác minh backup hoàn tất

Kiểm tra exit code, logs, backup manifest và dung lượng files. Nếu công cụ cung cấp verify operation, chạy trước khi khởi động target.

## 16. PITR: cấu hình archive recovery

Trên PostgreSQL 12 trở lên, recovery settings được đặt trong cấu hình PostgreSQL (ví dụ postgresql.conf hoặc postgresql.auto.conf) và dùng signal file để bắt đầu recovery. File recovery.conf cũ không còn là cách cấu hình trên các phiên bản mới.

Ví dụ cấu hình cho isolated target:

~~~conf
restore_command = 'cp /mnt/pg-archive/%f %p'
recovery_target_time = '2026-11-14 09:42:00+07'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

Đường dẫn và command phụ thuộc OS, storage backend và backup tool. Command phải trả exit status phù hợp khi WAL file chưa có/không tồn tại, và không được ghi đè sai đích.

### 16.1. recovery.signal

Tạo file rỗng `recovery.signal` trong data directory để yêu cầu PostgreSQL thực hiện archive recovery. Không tạo nhầm `standby.signal` nếu mục tiêu là PITR độc lập thay vì chạy standby streaming.

### 16.2. restore_command

PostgreSQL gọi command với placeholders như `%f` (tên file cần lấy) và `%p` (đích cần đặt). Backup tool có thể dùng command wrapper riêng để tải từ object storage/decrypt.

### 16.3. recovery_target_time

Timestamp cần timezone rõ. Chọn target trước transaction gây lỗi, dựa trên audit/application logs và semantics của transaction commit.

### 16.4. recovery_target_timeline

`latest` yêu cầu chọn timeline mới nhất có sẵn trong archive. Với tình huống cần phục hồi một nhánh cụ thể, xác định timeline đúng và giữ history files.

### 16.5. recovery_target_action=pause

Khi đạt target, server tạm dừng recovery thay vì tự promote. Có thể kết nối để kiểm tra trạng thái read-only trong recovery trước khi quyết định promote.

## 17. Các recovery target và semantics

PostgreSQL hỗ trợ nhiều cách chỉ định target, tùy version và recovery configuration:

- `recovery_target_time`: timestamp.
- `recovery_target_lsn`: log sequence number.
- `recovery_target_xid`: transaction ID.
- `recovery_target_name`: named restore point.
- `recovery_target_timeline`: timeline cần theo.

### 17.1. Timestamp phải được đối chiếu với logs

Clock skew, timezone và transaction commit timing có thể làm target không đúng như mong đợi. Dùng UTC hoặc timezone offset rõ ràng.

### 17.2. Inclusive/exclusive

`recovery_target_inclusive` điều khiển việc target transaction/record có được bao gồm hay không trong một số recovery target. Đọc semantics của loại target và PostgreSQL version trước khi chọn.

### 17.3. Named restore point

Có thể tạo named restore point trước thao tác rủi ro bằng SQL phù hợp, sau đó phục hồi tới tên đó nếu WAL archive có chứa record tương ứng. Restore point không giúp nếu WAL segment chưa được bảo vệ.

### 17.4. Target quá sớm

Có thể bỏ mất giao dịch hợp lệ cần giữ. Restore vào môi trường cách ly cho phép kiểm tra và trích dữ liệu trước khi quyết định thay primary.

### 17.5. Target quá muộn

Có thể đã replay transaction gây corruption/xóa nhầm. Dựng lại từ cùng base backup với target sớm hơn hoặc dùng một recovery chain khác phù hợp.

## 18. Khởi động và theo dõi PITR recovery

Sau khi cấu hình target và signal file, khởi động PostgreSQL bằng service/pg_ctl phù hợp. Theo dõi server log và trạng thái recovery.

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

### 18.1. pg_is_in_recovery

Trả true khi server còn trong recovery/standby state. Đây là tín hiệu quan trọng trước promotion.

### 18.2. Replay LSN và timestamp

Giúp quan sát tiến trình replay, nhưng timestamp cuối cùng có thể cũ khi không có transactions mới. Không dùng một giá trị đơn lẻ làm bằng chứng mọi WAL đã replay.

### 18.3. Server log

Tìm thông báo bắt đầu archive recovery, WAL file requested/received, target reached và recovery paused. Lỗi restore_command thường xuất hiện trong log.

### 18.4. Khi WAL thiếu

Recovery có thể tiếp tục thử lấy segment hoặc dừng khi không còn WAL cần thiết. Kiểm tra archive path, credentials, timeline history và command output.

### 18.5. Không mở traffic production

Trong giai đoạn này, chỉ recovery operators được kết nối. Không cho application pool hoặc background jobs tự động dùng endpoint.



## 19. Giữ PITR ở trạng thái pause để xác minh

Khi recovery target được chạm tới và `recovery_target_action` là `pause`, PostgreSQL dừng replay tại mốc đó. Cluster vẫn ở recovery state, nên các kết nối được phép có thể đọc dữ liệu nhưng không thực hiện ghi thông thường.

### 19.1. Xác nhận recovery đã pause

~~~sql
SELECT pg_is_in_recovery();
SELECT pg_last_wal_replay_lsn();
SELECT pg_last_xact_replay_timestamp();
~~~

Đối chiếu output với log có thông báo recovery target reached/paused. Không chỉ dựa vào việc server accept connection.

### 19.2. Đọc dữ liệu trong recovery

Dùng SELECT để kiểm tra schema, rows và business invariants. Nếu cần export dữ liệu, dùng logical dump/COPY hoặc công cụ đọc phù hợp với trạng thái read-only.

### 19.3. Không chạy DDL/DML trong recovery pause

Không thể tạo bảng staging, sửa sequence hoặc chạy ANALYZE theo cách ghi trên cluster đang ở recovery. Nếu cần các thao tác đó, tạo một bản clone từ recovery point hoặc promote isolated copy sau khi quyết định.

### 19.4. Resume hay promote?

Nếu cần tiếp tục replay qua target, có thể resume recovery theo quy trình phù hợp. Nếu target đã được xác nhận và cần biến cluster thành primary, promote sẽ kết thúc recovery tại recovery point hiện tại và bắt đầu timeline mới.

### 19.5. Không promote chỉ để “xem thử”

Promotion là một bước thay đổi trạng thái quan trọng. Có thể tạo timeline mới và khiến quy trình quay lại recovery point khác phức tạp hơn. Trước tiên dùng read-only inspection.

## 20. Validation: xác minh cấu trúc database

Dữ liệu đúng thời điểm nhưng thiếu objects hoặc quyền vẫn có thể làm ứng dụng không hoạt động.

### 20.1. Kiểm tra databases

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size,
    datallowconn,
    datistemplate
FROM pg_database
ORDER BY datname;
~~~

So sánh danh sách databases và dung lượng với backup catalog/expected inventory.

### 20.2. Kiểm tra schemas và tables

~~~sql
SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

### 20.3. Kiểm tra extensions

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Xác minh extension binaries tương ứng đã có trên host, không chỉ metadata trong database.

### 20.4. Kiểm tra constraints

~~~sql
SELECT
    conrelid::regclass AS relation,
    conname,
    contype,
    convalidated
FROM pg_constraint
WHERE NOT convalidated
ORDER BY 1, 2;
~~~

Các constraints chưa validated cần được giải thích. Không bỏ qua chỉ vì bảng có rows.

### 20.5. Kiểm tra indexes

~~~sql
SELECT
    indrelid::regclass AS table_name,
    indexrelid::regclass AS index_name,
    indisready,
    indisvalid
FROM pg_index
WHERE NOT indisready OR NOT indisvalid
ORDER BY 1, 2;
~~~

Một index không valid có thể làm query plan/constraint behavior khác dự kiến.

## 21. Validation: roles, grants và security policies

### 21.1. Roles và attributes

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication
FROM pg_roles
ORDER BY rolname;
~~~

Kiểm tra roles cần thiết và quyền của chúng. Không bật superuser cho app chỉ để sửa lỗi permission sau restore.

### 21.2. Role memberships

~~~sql
SELECT
    member.rolname AS member_role,
    parent.rolname AS granted_role,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS member ON member.oid = m.member
JOIN pg_roles AS parent ON parent.oid = m.roleid
ORDER BY 1, 2;
~~~

### 21.3. Table privileges

~~~sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3, 4;
~~~

### 21.4. Row-level security

Kiểm tra bảng có RLS bật/force:

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND (c.relrowsecurity OR c.relforcerowsecurity)
ORDER BY 1, 2;
~~~

Policies cũng cần được kiểm tra và xác nhận role ứng dụng vẫn nhìn thấy đúng rows.

### 21.5. Authentication và HBA

Kiểm tra pg_hba.conf, TLS certificates, `password_encryption`, `listen_addresses`, firewall và secrets. Không mở rộng access chỉ để test nhanh.

## 22. Validation: sequences, identity và dữ liệu nghiệp vụ

### 22.1. Kiểm tra sequences

Logical dump thường lưu trạng thái sequences, nhưng phải xác minh sau restore, đặc biệt khi data-only restore hoặc import explicit IDs.

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
    last_value
FROM pg_sequences
ORDER BY schemaname, sequencename;
~~~

Quyền đọc sequence và cột khả dụng có thể phụ thuộc version/privileges.

### 22.2. Tránh nextval trùng primary key

So sánh sequence state với giá trị khóa lớn nhất theo từng table/sequence. Nếu cần setval, làm trong một clone có thể ghi hoặc sau promotion của isolated copy, không trên cluster đang recovery pause.

### 22.3. Kiểm tra row counts có chọn lọc

~~~sql
SELECT count(*) FROM public.orders;
SELECT count(*) FROM public.order_items;
SELECT count(*) FROM public.payments;
~~~

Exact counts trên bảng lớn có thể tốn thời gian. Chọn các bảng trọng yếu và kết hợp aggregate/checksums hoặc metadata phù hợp.

### 22.4. Business invariants

Ví dụ: tổng payment theo ngày, số orders theo trạng thái, không có order item mồ côi, balance ledger cân bằng, foreign keys hợp lệ, số lượng tenant và thời điểm giao dịch cuối.

### 22.5. So sánh dữ liệu có ý nghĩa

Không chỉ so sánh tổng row count. Hai bản có cùng số rows vẫn có thể khác nội dung. Dùng aggregates, checksums theo partition/key range hoặc truy vấn nghiệp vụ đã được xác định.

## 23. Validation: dữ liệu và thời điểm phục hồi

### 23.1. Xác nhận recovery target

Đối chiếu target timestamp/LSN/restore point với incident timeline và logs. Ghi lại target thực tế mà PostgreSQL dừng.

### 23.2. Kiểm tra giao dịch cuối cùng

Dùng các bảng audit/event hoặc transaction markers để xác định giao dịch gần cuối đã được phục hồi. Không dùng `pg_last_xact_replay_timestamp()` một mình vì có thể cũ khi workload im lặng.

### 23.3. Xác nhận giao dịch gây lỗi không xuất hiện

Nếu phục hồi trước một DELETE nhầm, xác nhận rows cần cứu còn tồn tại và thao tác gây lỗi chưa được replay.

### 23.4. Kiểm tra dữ liệu sau recovery point

Với selective recovery, liệt kê các giao dịch hợp lệ sau mốc PITR trên production và quy tắc merge chúng. Tránh ghi đè chúng bằng dữ liệu cũ.

### 23.5. Lưu evidence

Ghi recovery point, LSN/timeline, query results, checksums, business owner approval và thời gian kiểm tra. Tránh lưu PII/secret không cần thiết vào ticket.

## 24. Validation: ứng dụng và dependencies

Database không hoạt động độc lập. Một bản restore có thể đúng nhưng ứng dụng vẫn không sẵn sàng.

### 24.1. Smoke tests

Chạy các truy vấn đọc quan trọng, authentication, health checks, transaction mẫu và các workflow nghiệp vụ trong môi trường sandbox.

### 24.2. External integrations

Dùng sandbox credentials cho payment/email/SMS/webhook. Tắt consumer/scheduler hoặc định tuyến sang mock endpoints để tránh side effects thật.

### 24.3. Connection pools

Kiểm tra hostname, port, TLS, DNS TTL, pool size, retry policy và secret rotation. Không cho pool production kết nối trước cutover.

### 24.4. Application version

Xác nhận schema/migration version tương thích với binary ứng dụng. Không chạy migration tự động lên recovery copy nếu mục tiêu là bảo toàn trạng thái tại recovery point.

### 24.5. Scheduled jobs

Tắt cron jobs, background workers, ETL writers, notification jobs và event consumers cho đến khi môi trường được phê duyệt. Các jobs có thể chạy ngay khi app boot.

## 25. Kiểm tra consistency trước khi quyết định thay thế

Một checklist xác minh nên kết hợp kỹ thuật và nghiệp vụ:

| Nhóm | Câu hỏi cần trả lời |
|---|---|
| Recovery point | Có đúng mốc trước/sau sự cố không? |
| WAL chain | Đã replay đủ tới target, đúng timeline? |
| Schema | Tables, views, functions, triggers, extensions đủ? |
| Integrity | Constraints/indexes hợp lệ? |
| Security | Roles, grants, RLS, TLS đúng? |
| Data | Rows/aggregates/business invariants đạt? |
| Application | Smoke tests thành công? |
| Dependencies | Queues, object storage, keys, DNS sẵn sàng? |
| Capacity | CPU/RAM/disk/network đủ cho production load? |
| Ownership | DBA và business owner đã xác nhận? |

### 25.1. Tách tiêu chí pass/fail

Một tiêu chí trọng yếu không đạt thì chưa nên cutover. Ghi rõ lỗi nào có thể chấp nhận, lỗi nào chặn phục hồi và ai có quyền chấp nhận rủi ro.

### 25.2. Không tự sửa dữ liệu để làm test pass

Nếu một invariant fail, điều tra nguyên nhân. Sửa trên recovery copy có thể làm mất bằng chứng về trạng thái backup; giữ bản nguyên trạng và tạo working clone nếu cần thử repair.

### 25.3. Giữ bản phục hồi nguyên trạng

Với incident điều tra hoặc pháp lý, lưu một bản forensic/read-only và checksum. Thực hiện thử nghiệm sửa chữa trên clone thứ hai.

### 25.4. Ghi rõ confidence

Phân biệt đã xác minh bằng query, suy ra từ log, hoặc chưa kiểm chứng. Không mô tả một backup là “đã đảm bảo” chỉ vì một vài bảng có count đúng.

### 25.5. Business sign-off

DBA xác nhận kỹ thuật; owner nghiệp vụ xác nhận dữ liệu và quy tắc hoạt động. Cutover cần người có thẩm quyền theo incident/change process.


## 26. Promotion: khi nào recovery copy được phép ghi?

Một PITR cluster đang pause thường chỉ phục vụ read-only inspection. Promotion kết thúc recovery và làm cluster có thể nhận writes. Đây là ranh giới quan trọng giữa kiểm tra và vận hành như primary.

### 26.1. Điều kiện trước promotion

- Recovery target và timeline đã được xác nhận.
- WAL chain không có lỗi chưa giải quyết.
- Schema, roles, constraints, indexes và business checks đạt.
- Network vẫn cô lập, không có production app clients.
- Đã lưu evidence và có quyết định của người chịu trách nhiệm.
- Đã xác định đây là bản sẽ dùng để thay hệ thống hay chỉ là working copy.

### 26.2. Promote bằng pg_ctl

~~~bash
pg_ctl promote --pgdata=/srv/recovery/pgdata
~~~

Đường dẫn chỉ là ví dụ. Dùng service manager/orchestration phù hợp với host thực tế.

### 26.3. Promote bằng SQL

Trên các phiên bản hỗ trợ, có thể dùng:

~~~sql
SELECT pg_promote();
~~~

Hàm trả kết quả promotion được yêu cầu/thực hiện theo semantics của version; kiểm tra log và trạng thái sau lệnh.

### 26.4. Xác minh sau promotion

~~~sql
SELECT pg_is_in_recovery();
~~~

Kết quả false cho biết server không còn ở recovery. Kiểm tra logs, timeline history, write access và trạng thái cluster trước khi mở traffic.

### 26.5. Promotion tạo nhánh timeline mới

Sau khi promote, cluster có thể ghi trên timeline mới. Giữ lại WAL/history và metadata cần thiết cho backup mới, standby rebuild và audit.

## 27. Không promote khi mục tiêu chỉ là trích xuất dữ liệu

Với lỗi logic trên production còn hoạt động, thường chỉ cần đọc từ recovery copy.

### 27.1. Giữ recovery copy read-only

Nếu PITR đang pause, dùng SELECT/export để lấy dữ liệu. Không cần chuyển nó thành primary chỉ để trích một bảng.

### 27.2. Dùng staging target riêng

Nếu cần chuẩn hóa hoặc biến đổi dữ liệu, copy sang database staging có thể ghi. Giữ bản PITR gốc nguyên trạng để đối chiếu.

### 27.3. Trích xuất bằng COPY

~~~sql
COPY (
    SELECT order_id, customer_id, total, created_at
    FROM public.orders
    WHERE created_at < TIMESTAMPTZ '2026-11-14 09:42:00+07'
) TO STDOUT WITH (FORMAT csv, HEADER true);
~~~

Ví dụ minh họa; chọn filter/columns theo nghiệp vụ và không xuất PII ngoài phạm vi cần thiết.

### 27.4. Trích bằng pg_dump table

Có thể dùng pg_dump với lựa chọn table/schema phù hợp từ recovery copy nếu cần một logical artifact. Kiểm tra dependencies trước khi restore phần đó vào production.

### 27.5. So sánh trước khi merge

Dùng primary hiện tại làm nguồn đối chiếu nếu nó còn đáng tin cậy. Xác định keys bị xóa, rows thay đổi, foreign keys và các giao dịch phát sinh sau recovery point.

## 28. Quy trình selective merge vào production

Selective merge là đưa phần dữ liệu cần phục hồi từ isolated environment vào database đang chạy, giữ lại các giao dịch hợp lệ khác.

### 28.1. Xác định tập dữ liệu cần cứu

Tạo danh sách primary keys, time ranges, tenants hoặc business objects. Tránh dùng một câu INSERT tổng quát nếu không hiểu dependency graph.

### 28.2. Nạp vào staging schema

~~~sql
CREATE SCHEMA recovery_staging;
~~~

Nạp dữ liệu đã trích vào staging table, kiểm tra types, encoding, constraints và duplicate keys.

### 28.3. So sánh conflicts

~~~sql
SELECT r.order_id
FROM recovery_staging.orders AS r
JOIN public.orders AS p USING (order_id);
~~~

Rows trùng key cần quyết định: giữ production hiện tại, thay thế, merge columns hay bỏ qua.

### 28.4. Merge trong transaction có giới hạn

~~~sql
BEGIN;

INSERT INTO public.orders (order_id, customer_id, total, created_at)
SELECT order_id, customer_id, total, created_at
FROM recovery_staging.orders
ON CONFLICT (order_id) DO NOTHING;

COMMIT;
~~~

Đây chỉ là ví dụ cho trường hợp insert missing rows. Không dùng DO NOTHING như quy tắc chung nếu cần khôi phục updates hoặc các dependent rows.

### 28.5. Reconcile dependent systems

Nếu orders phát sinh payment, shipment, email hoặc events, cần idempotency/reconciliation. Khôi phục row database không tự khôi phục side effect bên ngoài.

## 29. Cutover: thay hệ thống bằng recovery target

Chỉ thực hiện khi quyết định là thay primary hoặc chuyển workload sang DR site.

### 29.1. Declare cutover

Incident/change owner xác nhận recovery target, validation results, RPO/RTO impact và thời điểm mở traffic.

### 29.2. Fence old primary

Ngăn primary cũ nhận writes bằng cách dừng service, chặn network, revoke app routing hoặc cơ chế fencing phù hợp. Không để hai primary cùng nhận writes.

### 29.3. Freeze writes và drain clients

Tạm dừng application writes, background workers và scheduled jobs theo runbook. Chờ transaction đang chạy kết thúc hoặc xử lý có chủ đích.

### 29.4. Final recovery point

Nếu cần giữ các commits cuối trước cutover, bảo đảm WAL cuối đã được archive/replay hoặc có một quy trình đồng bộ cuối. Ghi rõ phần dữ liệu có thể mất theo RPO.

### 29.5. Promote và chuyển traffic

Promote recovery target, kiểm tra writable state, cập nhật service discovery/DNS/connection strings, refresh pools và mở traffic theo từng bước.

## 30. Tránh split-brain khi thay primary

Split-brain xảy ra khi hai instances cùng được coi là primary và nhận writes độc lập.

### 30.1. Fencing phải có bằng chứng

Không chỉ đổi DNS. Client cũ có thể giữ DNS cache, connection pool hoặc endpoint IP. Fencing phải ngăn writes tới primary cũ ở network/service/storage level phù hợp.

### 30.2. Dừng writers

Tắt application writers, cron, queue consumers, ETL và admin jobs. Một client nền bị bỏ sót có thể tiếp tục ghi vào primary cũ.

### 30.3. Kiểm tra replication topology

Sau failover, standby cũ có thể cần reconfigure/reseed. Không để node cũ tự reconnect theo topology đã lỗi thời.

### 30.4. Không mở traffic đồng thời

Mở từng nhóm clients và kiểm tra error rate, write path, replication và business metrics trước khi mở toàn bộ.

### 30.5. Ghi lại timeline/LSN mới

Sau promotion, ghi timeline, LSN, recovery target và thời điểm cutover. Đây là cơ sở cho backup chain mới và standby provisioning.

## 31. Xử lý primary cũ sau cutover

Primary cũ không tự động trở thành standby hợp lệ chỉ vì đổi connection string.

### 31.1. Giữ node cũ fenced

Giữ node cũ không nhận writes cho tới khi quyết định rejoin/rebuild. Bảo toàn logs và evidence nếu cần điều tra.

### 31.2. Xác định timeline divergence

Primary cũ có thể chứa các transactions không có trên recovered primary hoặc ngược lại. Không tự copy data directory qua lại.

### 31.3. pg_rewind hoặc fresh base backup

Trong một số điều kiện, pg_rewind có thể đưa node cũ theo timeline mới nếu prerequisites như data checksums hoặc wal_log_hints và WAL cần thiết đáp ứng yêu cầu. Nếu không, tạo lại standby từ base backup mới.

### 31.4. Không giả định rewind luôn khả dụng

Kiểm tra version compatibility, WAL retention, timeline history, checksums/wal_log_hints và tài liệu pg_rewind. Khi không chắc, rebuild từ base backup là đường rõ ràng hơn.

### 31.5. Recreate replication slots/configuration

Thiết lập lại slots, primary_conninfo, synchronous standby policy, archive_command và monitoring. Xác nhận standby replay bắt kịp trước khi tuyên bố HA đã phục hồi.

## 32. Rollback và kế hoạch quay lại

Rollback sau cutover phức tạp hơn việc đổi DNS nếu primary mới đã nhận writes.

### 32.1. Trước khi mở writes

Nếu recovery target chưa nhận writes và cutover thất bại, có thể giữ nguyên primary cũ (nếu nó vẫn an toàn) và hủy chuyển traffic theo kế hoạch.

### 32.2. Sau khi primary mới nhận writes

Không đơn giản chuyển traffic về primary cũ vì nó thiếu giao dịch mới. Cần một quy trình forward-recovery/replication/reconciliation để tránh mất writes.

### 32.3. Quy tắc một writer

Tại mọi thời điểm chỉ có một authoritative writer cho dữ liệu nghiệp vụ. Nếu dùng multi-primary, cần một thiết kế consistency riêng; không phải mặc định của failover PostgreSQL.

### 32.4. Rollback decision window

Xác định thời điểm cuối có thể quay lại mà không phải reconcile writes. Sau thời điểm đó, chỉ dùng recovery plan có xử lý dữ liệu phát sinh.

### 32.5. Ghi rõ rollback owner

Incident commander, DBA và application owner cần biết ai có quyền dừng cutover và ai quyết định tiếp tục forward recovery.

## 33. Bảo vệ dữ liệu trong môi trường cách ly

Bản restore thường chứa dữ liệu production, kể cả PII, secrets hoặc password verifiers.

### 33.1. Áp dụng cùng mức phân loại dữ liệu

Không coi recovery host là sandbox vô hại. Mã hóa storage/network, giới hạn users và audit access.

### 33.2. Masking cho developer/test

Nếu dùng clone cho kiểm thử không production, mask/anonymize dữ liệu theo policy trước khi cấp quyền cho developer hoặc vendor.

### 33.3. Không dùng production credentials

Tạo recovery identities riêng, credentials có thời hạn, không cho app identity quyền truy cập backup repository hoặc xóa backup.

### 33.4. Kiểm soát export

CSV/dump trích từ recovery copy có thể dễ bị copy ra laptop hoặc bucket cá nhân. Đặt destination được phê duyệt, encryption và retention.

### 33.5. Dọn dẹp sau incident

Sau khi xác nhận evidence được giữ đúng retention, xóa recovery copies, temporary dumps, keys/session credentials và storage theo quy trình an toàn. Không xóa forensic copy đang có legal hold.

## 34. RPO/RTO trong isolated restore

Isolated recovery giúp đo thời gian thực tế và điểm dữ liệu có thể khôi phục.

### 34.1. RPO

Ghi recovery target đã đạt, WAL cuối có thể replay và trạng thái remote archive. RPO tính từ thời điểm sự cố tới recovery point thực sự sẵn sàng.

### 34.2. RTO

Tính từ incident declaration theo quy ước tới khi application/service sẵn sàng sau cutover. Bao gồm provision, retrieve, restore, replay, validation và routing.

### 34.3. Restore test và production RTO

Một lab restore có thể đo kỹ thuật nhưng không gồm incident approvals hoặc DNS change thật. Ghi rõ phạm vi thời gian đã đo.

### 34.4. Parallelism

Có thể provision host, kiểm tra keys và chuẩn bị DNS song song với backup retrieval nếu runbook cho phép. Không giả định song song nếu có dependency.

### 34.5. Buffer

Thiết kế target có buffer cho archive lag, cold storage retrieval, peak network, index build và business validation.



## 35. Lab: logical restore vào database cách ly

Lab này minh họa phục hồi một custom dump vào database mới. Chạy trong môi trường thử nghiệm với quyền phù hợp.

### 35.1. Tạo logical dump

~~~bash
pg_dump --format=custom --file=appdb.dump --dbname=appdb
~~~

Lệnh tạo snapshot logic của database. Đảm bảo file được lưu ở nơi có dung lượng và quyền phù hợp.

### 35.2. Kiểm tra archive list

~~~bash
pg_restore --list appdb.dump
~~~

Ghi nhận objects có trong archive và xác minh file có thể đọc.

### 35.3. Tạo target database riêng

~~~bash
createdb --template=template0 recovery_app
~~~

Nếu cần locale/encoding cụ thể, tạo database với options tương ứng production.

### 35.4. Restore

~~~bash
pg_restore --verbose --exit-on-error --dbname=recovery_app appdb.dump
~~~

Đợi command hoàn tất và lưu log. Không cho ứng dụng kết nối vào recovery_app.

### 35.5. Xác minh cơ bản

~~~sql
SELECT current_database();
SELECT count(*) FROM public.orders;
SELECT count(*) FROM public.customers;
SELECT extname, extversion FROM pg_extension ORDER BY extname;
~~~

So sánh kết quả với expected inventory và business checks đã chuẩn bị.

## 36. Lab: restore logical dump với roles và ownership

### 36.1. Tạo globals-only backup

~~~bash
pg_dumpall --globals-only --file=globals.sql
~~~

File có thể chứa role definitions và tablespaces. Bảo vệ như dữ liệu nhạy cảm và kiểm tra trước khi restore.

### 36.2. Xem nội dung trước khi chạy

Đọc SQL để hiểu roles, tablespaces, ownership và grants sẽ được tạo. Không áp dụng file globals không rõ nguồn vào cluster có dữ liệu.

### 36.3. Restore globals vào cluster lab mới

~~~bash
psql -X --set ON_ERROR_STOP=on --dbname=postgres --file=globals.sql
~~~

Nếu target đã có roles, xử lý conflict theo kế hoạch. Một cluster lab rỗng giúp giảm xung đột.

### 36.4. Restore database archive

~~~bash
pg_restore --exit-on-error --dbname=recovery_app appdb.dump
~~~

### 36.5. Kiểm tra quyền thực tế

Kết nối bằng role ứng dụng thử nghiệm và chạy các queries/workflows được phép. Không dùng superuser để xác nhận quyền ứng dụng.

## 37. Lab: dựng physical PITR vào data directory riêng

Lab này yêu cầu base backup và WAL archive hợp lệ. Các đường dẫn là ví dụ; không chạy trên production data directory.

### 37.1. Chuẩn bị data directory

Tạo volume/directory riêng cho recovery host, kiểm tra owner, permissions và disk space. Giải nén/restore base backup bằng công cụ đã tạo artifact.

### 37.2. Cấu hình archive retrieval

~~~conf
restore_command = 'cp /mnt/pg-archive/%f %p'
recovery_target_time = '2026-11-14 09:42:00+07'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

Thay command bằng wrapper của backup tool/object storage nếu cần. Command phải trả kết quả đúng khi file không có và không được đọc nhầm archive.

### 37.3. Tạo recovery.signal

Tạo file rỗng `recovery.signal` trong PGDATA của bản phục hồi trên PostgreSQL 12 trở lên. Không tạo signal file trong data directory của production.

### 37.4. Khởi động target

~~~bash
pg_ctl start --pgdata=/srv/recovery/pgdata --log=/srv/recovery/recovery.log
~~~

Theo dõi log để biết recovery đã bắt đầu, lấy WAL và đạt target.

### 37.5. Xác nhận pause

~~~sql
SELECT pg_is_in_recovery();
SELECT pg_last_wal_replay_lsn();
SELECT pg_last_xact_replay_timestamp();
~~~

Kết nối chỉ từ recovery network. Xác nhận log báo target reached/paused và kiểm tra dữ liệu cần thiết.

## 38. Lab: điều tra xóa nhầm bằng recovery copy

Giả sử một bảng orders bị xóa nhầm lúc 10:15. Production hiện tại vẫn nhận các giao dịch hợp lệ.

### 38.1. Chọn target trước thao tác sai

Chọn thời điểm trước commit DELETE, có buffer nhỏ nếu clock/log uncertainty. Ghi rõ timezone và recovery target.

### 38.2. Restore PITR vào isolated cluster

Dùng base backup + WAL tới target. Giữ recovery pause để query/export.

### 38.3. Xác minh rows

~~~sql
SELECT count(*) FROM public.orders;
SELECT min(created_at), max(created_at) FROM public.orders;
SELECT status, count(*) FROM public.orders GROUP BY status;
~~~

Đối chiếu với audit records và các business invariants.

### 38.4. Export phần cần cứu

Dùng COPY hoặc dump table vào staging artifact đã được phê duyệt. Không xuất tất cả columns nếu chỉ cần một tập nhỏ.

### 38.5. Merge vào production hiện tại

Nạp vào staging schema, so sánh conflicts, xử lý foreign keys và transaction events, rồi merge bằng transaction có kiểm soát. Không thay toàn primary bằng bản PITR cũ khi production đã có writes hợp lệ sau 10:15.

## 39. Lab: diễn tập cutover trong mạng cô lập

### 39.1. Chuẩn bị candidate instance

Restore một backup vào host recovery, cấu hình endpoint riêng và firewall chỉ cho operator.

### 39.2. Kiểm tra không có application clients

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY application_name, pid;
~~~

Xác minh chỉ có connections dự kiến. Query view này không thay thế network firewall.

### 39.3. Chạy smoke tests

Kiểm tra authentication, đọc dữ liệu trọng yếu và transaction mẫu trên bản clone có thể ghi. Nếu cluster vẫn recovery pause, chỉ chạy read checks.

### 39.4. Diễn tập fencing

Trong lab, mô phỏng việc chặn primary cũ và đổi endpoint. Xác nhận clients cũ không thể ghi vào node cũ.

### 39.5. Đo thời gian

Ghi provision, retrieve, restore, replay, validation, promotion và routing durations. So sánh với RTO target và tạo action items.

## 40. Runbook: isolated restore trước khi thay thế

Một runbook thực tế có thể theo trình tự:

1. Declare incident/drill và ghi T0, timezone, failure mode.
2. Xác nhận primary còn tin cậy và có thể giữ làm nguồn đối chiếu không.
3. Chọn recovery point theo RPO và business impact.
4. Xác minh backup artifact, manifest, WAL chain, timeline và encryption keys.
5. Provision recovery host/network/storage riêng.
6. Chuẩn bị PostgreSQL binaries, extensions, locale, roles và tablespaces.
7. Restore logical hoặc physical backup vào target riêng.
8. Nếu PITR, replay WAL tới target và pause recovery.
9. Xác minh schema, data, constraints, indexes, sequences, grants và RLS.
10. Chạy business invariants và application smoke tests trong sandbox.
11. Quyết định selective merge hay thay primary.
12. Nếu cutover, freeze writes, fence old primary, promote target và chuyển traffic.
13. Xác nhận application health và business transactions.
14. Rebuild standby/backup chain trên timeline mới.
15. Ghi RPO/RTO thực tế, evidence và post-incident actions.
16. Bảo vệ hoặc dọn recovery artifacts theo retention/legal hold.

### 40.1. Người chịu trách nhiệm

Ghi rõ incident commander, DBA/recovery lead, application owner, network/security owner và business approver. Một bước không có owner dễ bị bỏ qua khi áp lực thời gian cao.

### 40.2. Tiêu chí dừng

Nếu WAL thiếu, target không rõ, integrity checks fail, keys không truy cập được hoặc fencing chưa sẵn sàng, dừng cutover và escalate theo incident process.

### 40.3. Quyền quyết định

DBA xác nhận kỹ thuật; business owner chấp nhận dữ liệu có thể mất; incident commander điều phối; người được ủy quyền quyết định mở traffic.

### 40.4. Ghi nhận mọi thay đổi

Lưu commands, timestamps, recovery target, promotion event, DNS changes và approvals. Không ghi passwords/tokens vào log.

### 40.5. Kết thúc incident chưa phải kết thúc recovery

Cần khôi phục backup/standby protection, kiểm tra archive lag, xác nhận monitoring và đóng các temporary access.

## 41. Troubleshooting: restore không bắt đầu

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| pg_restore không đọc archive | File hỏng/format sai | pg_restore --list, checksum, tool version |
| Permission denied | File/dir owner hoặc IAM | OS permissions, storage identity |
| Database creation fail | Locale/encoding/template mismatch | createdb options, locale packages |
| Role already exists | Globals conflict | Review globals SQL, role mapping |
| Extension missing | Shared library chưa cài | Package/version/extension inventory |
| Tablespace path missing | Target path chưa tạo | Tablespace mapping/permissions |
| Disk full | Capacity estimate thiếu | Free space, temp/index/WAL growth |
| TLS/auth failure | HBA/cert/secret mismatch | Recovery-only credentials and TLS config |

### 41.1. Không restore lại liên tục mà không đọc lỗi

Giữ logs và xác định lỗi xảy ra ở archive read, database create, object restore hay runtime startup. Sửa đúng dependency rồi chạy lại trên target sạch.

### 41.2. Target database có thể đã bị tạo dở

Nếu restore thất bại giữa chừng, quyết định dọn target theo runbook. Không dùng clean/drop trên database không đúng scope.

### 41.3. Tool versions

pg_dump/pg_restore có compatibility rules theo server versions. Kiểm tra client version, archive format và target server trước.

## 42. Troubleshooting: PITR không đạt target

### 42.1. WAL segment không tìm thấy

Kiểm tra archive path, file name, permissions, object lifecycle, credentials và restore_command output.

### 42.2. Timeline history thiếu

Nếu target nằm trên timeline mới, cần timeline history files và WAL segments tương ứng. Không chỉ copy các WAL filenames mà không kiểm tra chain.

### 42.3. Recovery dừng sớm

Có thể target không nằm trong WAL archive, archive bị thiếu hoặc target timestamp nằm sau WAL cuối. Đối chiếu log và LSN.

### 42.4. Recovery đi quá target

Kiểm tra recovery target settings, signal file, config source và version. Đảm bảo không có cấu hình cũ/khác override.

### 42.5. Timezone không đúng

Timestamp không có offset có thể được hiểu theo timezone server. Ghi offset/UTC rõ ràng và kiểm tra incident clock.

## 43. Troubleshooting: database phục hồi nhưng ứng dụng lỗi

- Roles/memberships không đủ.
- Grants/default privileges bị thiếu hoặc bị bỏ do no-acl.
- RLS policy làm app không thấy rows.
- Extension binary/version không tương thích.
- Collation/locale thay đổi khiến indexes/query behavior khác.
- Sequence/identity state không đồng bộ.
- Schema version không khớp app binary.
- TLS/HBA/DNS/network chưa đúng.
- Secrets hoặc KMS key chưa được cấp.
- Queue, object storage hoặc external services chưa được phục hồi.
- Scheduled jobs/consumers chạy nhầm trong môi trường cách ly.
- Connection pool giữ endpoint cũ hoặc retry không phù hợp.

### 43.1. Đọc log của cả hai phía

PostgreSQL log cho biết lỗi server/auth/SQL; application log cho biết query/connection/workflow. Correlate bằng timestamp/request ID phù hợp.

### 43.2. Không mở rộng quyền tùy tiện

Lỗi permission cần xác định role/object/grant cụ thể. Tránh grant ALL hoặc SUPERUSER để làm smoke test pass.

### 43.3. Không chạy migration tự động khi chưa xác nhận target

Migration có thể làm thay đổi recovery copy và phá khả năng so sánh với recovery point. Chạy trên clone hoặc theo migration plan có kiểm soát.

## 44. Các hiểu lầm thường gặp

1. **“Backup tạo thành công nghĩa là restore được.”** Sai; cần restore test và validation.
2. **“Có thể restore đè lên production rồi kiểm tra sau.”** Sai; có thể làm mất trạng thái hiện tại và tăng downtime.
3. **“Database start là service đã phục hồi.”** Sai; còn roles, network, application và business checks.
4. **“Standby thay thế backup.”** Sai; lỗi logic có thể được replay.
5. **“PITR chỉ cần base backup.”** Sai; cần WAL chain và timeline phù hợp.
6. **“Một pg_dump có global roles.”** Sai; globals cần quy trình riêng.
7. **“pg_dumpall tạo snapshot nguyên tử toàn cluster.”** Sai; các databases không có một snapshot MVCC chung.
8. **“Recovery pause có thể ghi dữ liệu.”** Sai; server còn trong recovery state.
9. **“Promote chỉ là mở port.”** Sai; promotion kết thúc recovery và tạo timeline mới.
10. **“Đổi DNS đủ để fence primary cũ.”** Sai; clients cũ có thể giữ connections/endpoints.
11. **“Có thể rollback bằng cách đổi DNS về primary cũ sau khi new primary nhận writes.”** Sai; cần reconcile/forward recovery.
12. **“Một table restore luôn độc lập.”** Sai; có sequences, types, functions, foreign keys và grants.
13. **“Checksum đúng chứng minh dữ liệu nghiệp vụ đúng.”** Sai; checksum chứng minh bytes, không chứng minh business semantics.
14. **“Count(*) đúng nghĩa là data đúng.”** Sai; cùng count vẫn có thể khác rows.
15. **“Recovery copy không chứa dữ liệu nhạy cảm.”** Sai; nó thường chứa production data.
16. **“Có thể dùng production credentials để test.”** Sai; làm tăng blast radius và side effects.
17. **“Chỉ cần tắt app web.”** Sai; workers, cron, ETL và consumers cũng có thể ghi.
18. **“pg_rewind luôn đồng bộ được primary cũ.”** Sai; có prerequisites và WAL requirements.
19. **“Restore xong có thể bỏ backup monitoring.”** Sai; phải thiết lập lại protection trên timeline mới.
20. **“Một lần tabletop chứng minh DR.”** Sai; cần technical restore/cutover drills.

## 45. Bài tập thực hành

### Bài 1 — Isolated recovery

Vì sao nên restore vào môi trường cách ly trước khi thay production?

**Gợi ý:** Xác minh recovery point, artifacts, dependencies và dữ liệu trước khi mở traffic.

### Bài 2 — Selective recovery

Production vẫn chạy sau khi một bảng bị xóa nhầm. Vì sao không nên thay toàn primary bằng PITR cũ?

**Đáp án:** Sẽ mất các giao dịch hợp lệ phát sinh sau recovery point.

### Bài 3 — Logical dump

Lệnh nào xem table of contents của custom archive?

**Đáp án:** `pg_restore --list`.

### Bài 4 — Restore database

Lệnh nào restore custom archive vào database đã tạo?

**Gợi ý:** pg_restore với --dbname và archive file.

### Bài 5 — Globals

Công cụ nào xuất global objects như roles?

**Đáp án:** `pg_dumpall --globals-only`.

### Bài 6 — Physical backup

Công cụ PostgreSQL cơ bản nào tạo base backup qua replication protocol?

**Đáp án:** `pg_basebackup`.

### Bài 7 — Recovery signal

Trên PostgreSQL 12+, file nào kích hoạt archive recovery?

**Đáp án:** `recovery.signal`.

### Bài 8 — Standby signal

File nào dùng để khởi động standby mode?

**Đáp án:** `standby.signal`.

### Bài 9 — Restore command

Hai placeholder phổ biến trong restore_command là gì?

**Đáp án:** `%f` cho tên WAL file và `%p` cho destination path.

### Bài 10 — Recovery target

Tham số nào chọn timestamp PITR?

**Đáp án:** `recovery_target_time`.

### Bài 11 — Pause

Vì sao đặt recovery_target_action=pause trong isolated validation?

**Gợi ý:** Dừng tại target để đọc/kiểm tra trước khi promote.

### Bài 12 — Recovery state

Function nào cho biết server còn trong recovery?

**Đáp án:** `pg_is_in_recovery()`.

### Bài 13 — Promotion

Lệnh nào promote isolated recovery server qua pg_ctl?

**Đáp án:** `pg_ctl promote`.

### Bài 14 — Timeline

Vì sao cần lưu timeline history sau promotion?

**Gợi ý:** WAL recovery/standby rebuild cần biết nhánh timeline.

### Bài 15 — Extension

Vì sao có CREATE EXTENSION trong dump nhưng restore vẫn có thể fail?

**Đáp án:** Shared library/package tương ứng có thể chưa cài trên target.

### Bài 16 — Roles

Tại sao pg_dump một database không đủ để phục hồi mọi roles?

**Gợi ý:** Roles là global objects ở cấp cluster.

### Bài 17 — Ownership

Tùy chọn nào bỏ ownership commands khi pg_restore?

**Đáp án:** `--no-owner`.

### Bài 18 — Grants

Tùy chọn nào bỏ ACL/GRANT trong pg_restore?

**Đáp án:** `--no-acl`.

### Bài 19 — Constraints

Catalog nào chứa constraint validation state?

**Đáp án:** `pg_constraint`, cột `convalidated`.

### Bài 20 — Index validity

Catalog nào xem indisvalid/indisready?

**Đáp án:** `pg_index`.

### Bài 21 — RLS

Vì sao phải kiểm tra row-level security sau restore?

**Gợi ý:** Policy có thể làm app role nhìn thấy tập rows khác mong đợi.

### Bài 22 — Sequences

Vì sao sequence state có thể cần xác minh sau data-only restore?

**Gợi ý:** Explicit IDs/import có thể làm sequence value không theo kịp max key.

### Bài 23 — Business invariants

Nêu hai ví dụ kiểm tra ngoài row count.

**Gợi ý:** Ledger balance, tổng payment, order status counts, foreign-key orphan checks.

### Bài 24 — Side effects

Khi chạy ứng dụng trên recovery copy cần chặn những gì?

**Đáp án:** Payment/email/webhook, scheduled jobs, ETL writers, queue consumers và các external side effects khác.

### Bài 25 — Split-brain

Tại sao đổi DNS chưa chắc fence primary cũ?

**Gợi ý:** Client cache/connection pools có thể tiếp tục dùng endpoint cũ.

### Bài 26 — Cutover

Thứ tự quan trọng nào trước khi mở writes trên recovered primary?

**Gợi ý:** Freeze/drain writes, fence old primary, promote target, chuyển endpoint, mở traffic.

### Bài 27 — Primary cũ

Sau timeline divergence, có thể làm gì với old primary?

**Gợi ý:** pg_rewind nếu đủ prerequisites; nếu không, reseed từ base backup mới.

### Bài 28 — Rollback

Sau khi recovered primary nhận writes, vì sao không thể đơn giản quay về old primary?

**Đáp án:** Old primary thiếu writes mới; cần forward recovery/reconciliation.

### Bài 29 — Recovery data privacy

Vì sao recovery copy phải được bảo vệ như production?

**Đáp án:** Nó chứa cùng dữ liệu nhạy cảm và có thể có credentials/verifiers/PII.

### Bài 30 — Restore evidence

Những metadata nào nên ghi cho recovery point?

**Gợi ý:** Backup ID, timestamp/timezone, LSN, timeline, WAL coverage, checksum và target.

### Bài 31 — PITR failure

Nếu WAL segment thiếu, cần kiểm tra những gì?

**Gợi ý:** Archive path, permissions, restore_command, object retention, timeline history.

### Bài 32 — RTO

Những giai đoạn nào cần tính ngoài restore command?

**Gợi ý:** Detect, decision, provision, retrieve, replay, validation, cutover.

### Bài 33 — Recovery pause

Có thể chạy CREATE TABLE trên cluster đang recovery pause không?

**Đáp án:** Không; tạo bản clone có thể ghi hoặc promote isolated copy khi đã quyết định.

### Bài 34 — Selective merge

Vì sao nên nạp dữ liệu phục hồi vào staging schema trước?

**Gợi ý:** So sánh conflicts, validate và xác định merge rules trước khi thay đổi production.

### Bài 35 — Global consistency

Vì sao nhiều pg_dump databases không đảm bảo một snapshot chung?

**Đáp án:** Mỗi database dump có snapshot riêng; không có distributed transaction snapshot xuyên databases.

### Bài 36 — Managed restore

Ngoài backup snapshot, cần kiểm tra dependencies nào?

**Gợi ý:** KMS, IAM, quota, parameter group, extensions, network và DNS.

### Bài 37 — Cutover approval

Ai xác nhận kỹ thuật và ai xác nhận nghiệp vụ?

**Gợi ý:** DBA/recovery lead xác nhận kỹ thuật; business/service owner xác nhận dữ liệu và hành vi.

### Bài 38 — Forensic copy

Vì sao nên giữ bản phục hồi nguyên trạng khi điều tra?

**Đáp án:** Bảo toàn evidence và có thể tái kiểm tra; sửa chữa trên clone khác.

### Bài 39 — DR drill

Một tabletop exercise có đủ chứng minh cutover không?

**Đáp án:** Không; cần technical restore và cutover drill trong môi trường phù hợp.

### Bài 40 — Thiết kế tổng hợp

Một hệ thống PostgreSQL 2 TB bị xóa nhầm dữ liệu lúc 10:15, production còn nhận giao dịch mới, RPO mục tiêu 5 phút và RTO 45 phút. Hãy đề xuất quy trình.

**Gợi ý:** Fence thao tác gây lỗi, chọn PITR target trước 10:15, restore base backup + WAL vào isolated cluster, pause tại target, xác minh rows/business invariants, export phần cần cứu, merge qua staging với conflict rules vào production hiện tại. Chỉ thay primary nếu production không còn tin cậy; khi đó freeze writes, fence old primary, promote, cutover và rebuild standby. Đo RPO/RTO từ artifacts/restore drill.

## 46. Checklist trước khi bắt đầu isolated restore

- [ ] Incident/drill ID và failure mode được ghi?
- [ ] Recovery point và timezone/LSN đã xác định?
- [ ] Backup artifacts/checksum/manifest có thể đọc?
- [ ] WAL chain và timeline history đủ nếu PITR?
- [ ] Encryption keys truy cập được bằng DR identity?
- [ ] PostgreSQL version/extensions tương thích?
- [ ] Tablespaces/locale/encoding/permissions sẵn sàng?
- [ ] Recovery host/data directory/volume riêng?
- [ ] Network và firewall cô lập?
- [ ] Không có application credentials/clients tự kết nối?
- [ ] External side effects/jobs/consumers bị chặn?
- [ ] Disk/CPU/RAM/network đủ headroom?
- [ ] Validation criteria và owners đã xác định?

## 47. Checklist validation trước promotion/cutover

- [ ] Recovery target và timeline đúng?
- [ ] WAL replay đạt target, logs không còn lỗi?
- [ ] Database/schema/tables đủ?
- [ ] Extensions và shared libraries đúng?
- [ ] Constraints/indexes valid?
- [ ] Sequences/identity state phù hợp?
- [ ] Roles/memberships/grants/default privileges đúng?
- [ ] RLS policies và authentication được xác nhận?
- [ ] Business invariants đạt?
- [ ] Application smoke tests đạt trên sandbox?
- [ ] External integrations dùng sandbox/no-op?
- [ ] Capacity đáp ứng production load?
- [ ] DBA và business owner sign-off?
- [ ] Fencing và cutover plan sẵn sàng?

## 48. Checklist cutover

- [ ] Incident commander declare cutover?
- [ ] Application writes/jobs/consumers đã pause?
- [ ] Primary cũ đã fence và không nhận writes?
- [ ] Final recovery point/WAL đã được xác nhận?
- [ ] Recovery target đã promote đúng?
- [ ] New timeline/LSN được ghi nhận?
- [ ] DNS/endpoints/service discovery được cập nhật?
- [ ] Connection pools được refresh?
- [ ] Traffic mở theo từng bước?
- [ ] Error rate/latency/business transactions được monitor?
- [ ] Standby/backup/WAL archive protection được thiết lập lại?
- [ ] Old primary được giữ fenced tới khi rejoin/rebuild hoàn tất?

## 49. Bảng tra cứu nhanh

| Thành phần | Vai trò |
|---|---|
| Isolated recovery | Phục hồi ở môi trường không nhận production traffic |
| Logical restore | Tạo objects/nạp data từ dump |
| Physical restore | Dựng cluster từ base backup |
| WAL archive | Cung cấp log để replay |
| PITR | Phục hồi tới recovery target |
| recovery.signal | Bắt đầu archive recovery trên PostgreSQL 12+ |
| standby.signal | Bắt đầu standby mode |
| restore_command | Lấy WAL archive file |
| recovery_target_time | Chọn timestamp recovery |
| recovery_target_timeline | Chọn timeline |
| recovery_target_action=pause | Dừng replay tại target để kiểm tra |
| pg_is_in_recovery() | Kiểm tra recovery state |
| pg_promote() | Promote server |
| pg_restore | Restore logical archive |
| pg_dumpall --globals-only | Export global objects |
| pg_constraint | Constraint metadata |
| pg_index | Index validity metadata |
| pg_roles | Role attributes |
| pg_auth_members | Role membership |
| pg_stat_activity | Session visibility |
| pg_locks | Lock monitoring |
| Fencing | Ngăn primary cũ nhận writes |
| Cutover | Chuyển traffic sang recovered primary |
| Selective merge | Đưa phần dữ liệu cần cứu vào production |
| pg_rewind | Đồng bộ node theo timeline mới khi đủ điều kiện |
| Recovery drill | Diễn tập restore/validation/cutover |

## 50. Kết luận

**Phục hồi vào môi trường cách ly là bước kiểm soát quan trọng trước khi thay thế hệ thống PostgreSQL.** Nó tạo không gian để xác minh backup, chọn recovery point, replay WAL, kiểm tra schema/quyền/dữ liệu và chạy business checks mà không làm production kết nối nhầm vào cluster chưa được xác nhận.

Với logical backup, restore vào database mới và kiểm tra dependencies/ownership/grants. Với physical backup và PITR, dựng data directory riêng, cung cấp WAL archive, cấu hình recovery target và có thể pause tại target để đọc/xác minh trước promotion. Khi chỉ cần cứu một phần dữ liệu, giữ recovery copy read-only và merge qua staging với conflict rules; không rollback toàn production nếu các giao dịch hợp lệ sau recovery point cần được giữ.

Nếu phải thay primary, quy trình cần freeze writes, fence primary cũ, xác nhận target, promote recovery cluster, chuyển endpoints, mở traffic có kiểm soát và rebuild standby/backup protection trên timeline mới. Đổi DNS đơn lẻ không ngăn split-brain, và rollback sau khi primary mới nhận writes cần xử lý các giao dịch đã phát sinh.

Nguyên tắc vận hành: **restore trước, xác minh trong isolation, quyết định selective merge hay replacement, rồi mới promote/cutover**. Đo RPO/RTO bằng diễn tập thực tế, giữ evidence và bảo vệ recovery copies như production data.
