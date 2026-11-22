# RPO, RTO và lựa chọn chiến lược sao lưu

Một hệ thống PostgreSQL có thể tạo backup thành công mỗi ngày nhưng vẫn không đáp ứng nhu cầu khôi phục của doanh nghiệp. Nếu sự cố xảy ra lúc 16:00 và bản backup gần nhất là 01:00, doanh nghiệp có thể mất gần 15 giờ dữ liệu. Nếu restore database mất 8 giờ trong khi dịch vụ chỉ được phép gián đoạn 30 phút, chiến lược đó cũng không đạt yêu cầu dù file backup hoàn toàn nguyên vẹn.

Hai chỉ tiêu giúp biến yêu cầu khôi phục thành con số có thể thiết kế và đo lường là **RPO (Recovery Point Objective)** và **RTO (Recovery Time Objective)**. RPO xác định mức mất dữ liệu theo thời gian có thể chấp nhận; RTO xác định thời gian tối đa để khôi phục dịch vụ về trạng thái hoạt động được. Chúng là yêu cầu nghiệp vụ, từ đó mới chọn tần suất backup, WAL archiving, replication, standby, storage, quy trình restore và nguồn lực vận hành.

Không có một loại backup phù hợp cho mọi hệ thống. Logical dump thuận tiện cho migration và phục hồi chọn lọc; physical base backup kết hợp WAL hỗ trợ phục hồi toàn cluster và PITR; replication giúp tăng availability nhưng không thay thế backup lịch sử; offsite/immutable copies bảo vệ trước mất hoặc bị xóa cả môi trường nguồn. Chiến lược tốt thường phối hợp nhiều lớp, kiểm tra theo kịch bản sự cố và diễn tập định kỳ.

Bài học thuộc chương **Sao lưu** của module **Database Engine Relational PostgreSQL**. Nội dung tập trung vào cách xác định RPO/RTO, đánh đổi giữa chi phí và mức bảo vệ, lựa chọn chiến lược backup/HA/DR, và xây dựng quy trình khôi phục có thể kiểm chứng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Định nghĩa RPO, RTO và phân biệt chúng với thời gian backup, retention và availability.
- Tính RPO/RTO từ timeline của một sự cố.
- Xác định yêu cầu theo mức độ quan trọng của dữ liệu và dịch vụ.
- Phân biệt backup logic, backup vật lý, WAL/PITR, snapshots, replication và standby.
- Chọn chiến lược phù hợp với database nhỏ/lớn, write rate, downtime và chi phí.
- Hiểu trade-off của synchronous/asynchronous replication và RPO gần zero.
- Thiết kế retention, offsite copies, immutability, encryption và quyền truy cập.
- Đánh giá backup window, restore throughput, network, disk và dependency của ứng dụng.
- Xây dựng DR runbook, recovery tiers và phương án cutover.
- Đo RPO/RTO thực tế bằng restore drills và diễn tập thảm họa.
- Phân biệt RPO/RTO theo từng kịch bản: lỗi host, xóa nhầm, corruption, mất region và ransomware.

## 2. RPO là gì?

**RPO — Recovery Point Objective** là lượng dữ liệu tối đa mà tổ chức chấp nhận mất khi có sự cố, thường được biểu diễn dưới dạng khoảng thời gian tính lùi từ thời điểm sự cố tới trạng thái dữ liệu có thể phục hồi.

Ví dụ, RPO 15 phút nghĩa là khi xảy ra sự cố, doanh nghiệp chấp nhận trạng thái database được phục hồi có thể cũ tối đa khoảng 15 phút so với điểm dữ liệu ngay trước sự cố, theo cách đo đã thống nhất.

### 2.1. RPO là yêu cầu về dữ liệu

RPO trả lời câu hỏi: **“Chúng ta có thể chấp nhận mất bao nhiêu dữ liệu đã được ghi nhận trước sự cố?”**

Nó không trả lời trực tiếp database cần bao lâu để start, hay ứng dụng cần bao lâu để hoạt động trở lại.

### 2.2. RPO bằng zero

RPO = 0 thường được hiểu là không chấp nhận mất bất kỳ transaction nào đã được xác nhận commit theo định nghĩa failure model. Đây là yêu cầu khó và cần kiến trúc đồng bộ/acknowledgement phù hợp; không thể suy ra chỉ từ việc có standby hoặc WAL archive.

Cần nêu rõ RPO 0 đối với loại sự cố nào: mất một node, mất một availability zone, mất cả region hay lỗi logic/ứng dụng. Một thiết kế có thể đạt mục tiêu với một số failure modes nhưng không đạt với các failure modes khác.

### 2.3. RPO không phải tần suất chạy backup

Backup mỗi 15 phút không tự động chứng minh RPO 15 phút. Job có thể chạy trễ, thất bại, file chưa được upload bền vững, encryption key không truy cập được hoặc restore không hoạt động.

Ngược lại, một chiến lược physical base backup hằng ngày kết hợp WAL archiving liên tục có thể đạt RPO thấp hơn nhiều so với khoảng cách giữa hai base backups, nếu WAL được lưu đầy đủ và có thể replay.

### 2.4. RPO thực tế cần đo

Với WAL archiving, hãy đo độ trễ từ khi WAL segment được đóng/đưa vào archive tới khi nó có mặt bền vững ở nơi phục hồi có thể truy cập. Với replication, hãy đo commit acknowledgement và replication lag theo failure mode. Với logical dump, điểm phục hồi thường là snapshot nhất quán của lần dump.

### 2.5. RPO phụ thuộc kịch bản

- Mất một primary node: standby có thể phục hồi tới dữ liệu đã replay/acknowledged.
- Xóa nhầm bảng: cần một recovery point trước thao tác xóa, thường qua PITR hoặc backup logic.
- Mất cả region: cần bản backup/WAL ở region khác.
- Ransomware xóa backup: cần immutable/offline copies có thể truy cập bằng identity độc lập.

## 3. RTO là gì?

**RTO — Recovery Time Objective** là khoảng thời gian tối đa tổ chức chấp nhận để khôi phục dịch vụ sau sự cố về mức hoạt động đã định nghĩa.

RTO không chỉ là thời gian PostgreSQL process khởi động. Nó có thể bao gồm phát hiện sự cố, quyết định phục hồi, provision hạ tầng, tải backup, giải mã, restore, replay WAL, xác minh dữ liệu, khởi động ứng dụng, chuyển traffic và kiểm tra nghiệp vụ.

### 3.1. RTO là yêu cầu về thời gian

RTO trả lời câu hỏi: **“Dịch vụ được phép ngừng hoạt động tối đa bao lâu trước khi phải trở lại trạng thái đáp ứng yêu cầu?”**

Phải định nghĩa trạng thái “hoạt động”: chỉ đọc được, đọc/ghi đầy đủ, hay toàn bộ tính năng và tích hợp bên ngoài đã sẵn sàng.

### 3.2. Database start không đồng nghĩa service restored

PostgreSQL có thể accept connections nhưng ứng dụng vẫn lỗi vì thiếu roles, extension, secrets, DNS, TLS certificates, migrations, queue consumers hoặc external services.

### 3.3. RTO phải tính cả phát hiện và quyết định

Nếu monitor phát hiện sự cố sau 20 phút và người vận hành cần 30 phút để xác định backup phù hợp, phần thời gian đó đã tiêu tốn RTO trước khi restore bắt đầu.

### 3.4. RTO đo được khác RTO trên tài liệu

Một runbook dự kiến restore 30 phút nhưng chưa từng thử không phải bằng chứng. Hãy đo từ lúc bắt đầu sự cố giả lập tới lúc business checks thành công.

### 3.5. RTO theo cấp độ dịch vụ

Một API thanh toán có thể cần RTO 15 phút; một báo cáo nội bộ có thể chấp nhận 8 giờ. Đừng đặt một RTO chung cho mọi database nếu mức độ ảnh hưởng khác nhau.

## 4. Phân biệt RPO và RTO

| Thuộc tính | RPO | RTO |
|---|---|---|
| Tên đầy đủ | Recovery Point Objective | Recovery Time Objective |
| Tập trung vào | Điểm dữ liệu có thể phục hồi | Thời gian khôi phục dịch vụ |
| Đơn vị phổ biến | Phút/giờ | Phút/giờ |
| Câu hỏi | Mất bao nhiêu dữ liệu? | Dừng bao lâu? |
| Tác động thiết kế | Backup frequency, WAL, replication durability | Restore speed, standby, automation, capacity |
| Bằng chứng | Recovery point/time thực tế | Restore duration và service readiness |
| Ví dụ | Tối đa mất 5 phút dữ liệu | Khôi phục trong 45 phút |

### 4.1. Hai chỉ tiêu độc lập

Có thể có RPO rất thấp nhưng RTO dài nếu phải restore một cluster lớn từ backup. Cũng có thể RTO thấp nhờ standby nhưng RPO cao nếu standby lag hoặc dữ liệu chưa được replay.

### 4.2. Không dùng một chỉ tiêu thay cho chỉ tiêu kia

Tăng số lần backup có thể giảm khoảng dữ liệu mất nhưng không nhất thiết làm restore nhanh. Thêm standby có thể giảm thời gian failover nhưng không tạo ra lịch sử đủ dài để quay lại trước lệnh DELETE nhầm.

### 4.3. Một phương án phải đạt cả hai

Khi business yêu cầu RPO 5 phút và RTO 30 phút, phương án chỉ có daily pg_dump không đáp ứng chỉ vì file dump nhỏ hoặc job hoàn thành nhanh.

## 5. Timeline ví dụ: tính RPO và RTO

Giả sử:

~~~text
01:00  Logical dump hoàn tất, snapshot nhất quán tại 01:00
12:00  Backup tiếp theo chưa chạy
14:00  Sự cố làm database không còn truy cập được
17:00  Restore dump vào cluster mới hoàn tất
17:20  Ứng dụng vượt qua business checks và nhận traffic
~~~

- RPO thực tế: khoảng 13 giờ (từ 01:00 tới 14:00).
- RTO thực tế: 3 giờ 20 phút (từ 14:00 tới 17:20).

Nếu yêu cầu là RPO tối đa 15 phút và RTO tối đa 1 giờ, chiến lược trên không đạt cả hai.

### 5.1. Vì sao lấy thời điểm service ready?

Database restore xong lúc 17:00 nhưng ứng dụng chỉ sẵn sàng lúc 17:20. Nếu mục tiêu là khôi phục dịch vụ end-to-end, RTO kết thúc ở 17:20.

### 5.2. Snapshot time khác file completion time

Nếu pg_dump bắt đầu lúc 01:00 và hoàn tất 01:40, snapshot logic không nhất thiết đại diện trạng thái 01:40. Metadata backup cần ghi nhận đúng recovery point semantics.

### 5.3. Mốc thời gian cần timezone rõ

Trong hệ thống đa region, ghi timestamp có timezone/UTC và thống nhất clock source. Không dùng “14:00” nếu không biết là timezone nào.

## 6. RPO/RTO, MTD và availability

Một số khái niệm liên quan:

- **MTD/MAO (Maximum Tolerable Downtime/Maximum Acceptable Outage):** thời gian gián đoạn tối đa mà business chịu được trước khi hậu quả vượt ngưỡng chấp nhận.
- **WRT (Work Recovery Time):** thời gian khôi phục các công việc/tác vụ còn tồn đọng sau khi hệ thống đã trở lại.
- **Availability/SLA/SLO:** tỷ lệ hoặc mục tiêu thời gian dịch vụ sẵn sàng trong một khoảng quan sát.

### 6.1. RTO phải nhỏ hơn giới hạn downtime business

Nếu business chỉ chịu được 2 giờ downtime, RTO 4 giờ không phù hợp. Thực tế nên có buffer cho bất định, không thiết kế sát mép tuyệt đối.

### 6.2. WRT có thể kéo dài sau RTO

Ứng dụng có thể nhận traffic lại nhưng backlog event, reconciliation hoặc báo cáo chưa hoàn tất. Cần xác định WRT nếu business yêu cầu xử lý hết tồn đọng.

### 6.3. Availability không đo mức mất dữ liệu

Một hệ thống có uptime 99,99% vẫn có thể mất dữ liệu đã commit nếu durability/backup không phù hợp.

### 6.4. Backup không tự nâng availability

Backup phục vụ recovery sau sự cố; nó không tự cung cấp failover tức thời như một standby được vận hành đúng.

### 6.5. HA và DR có thể bổ trợ nhau

HA giảm downtime cho các lỗi node/instance; DR bảo vệ khi sự cố vượt phạm vi HA, như mất region, corruption hoặc xóa nhầm lan sang replicas.

## 7. Xác định RPO/RTO từ yêu cầu nghiệp vụ

Không nên bắt đầu bằng việc chọn công cụ backup. Bắt đầu bằng cách xác định hậu quả nếu mất dữ liệu hoặc dịch vụ dừng.

### 7.1. Phân loại dữ liệu và dịch vụ

Ví dụ:

| Nhóm | Ví dụ | Mức ảnh hưởng |
|---|---|---|
| Tier 0 | Ledger, payment authorization | Rất cao |
| Tier 1 | Đơn hàng, inventory | Cao |
| Tier 2 | CRM, workflow nội bộ | Trung bình |
| Tier 3 | Analytics, dữ liệu có thể tái tạo | Thấp hơn |

Tên tier chỉ là ví dụ; tổ chức cần định nghĩa theo nghiệp vụ và quy định thực tế.

### 7.2. Xác định mức mất dữ liệu chấp nhận được

Với ledger, một transaction đã báo thành công nhưng bị mất có thể gây chênh lệch tài chính. Với cache hoặc bảng tổng hợp có thể tái tạo, RPO vài giờ có thể chấp nhận.

### 7.3. Xác định thời gian gián đoạn

Tính chi phí downtime theo doanh thu, SLA, trải nghiệm khách hàng, nghĩa vụ pháp lý và phụ thuộc của các dịch vụ khác.

### 7.4. Xác định failure modes

Mất disk, crash host, lỗi storage, mất availability zone, mất region, lỗi operator, application bug, corruption và ransomware cần các lớp bảo vệ khác nhau.

### 7.5. Có chủ sở hữu business phê duyệt

DBA/engineer có thể giải thích trade-offs, nhưng RPO/RTO là quyết định kinh doanh. Phải ghi lại người chịu trách nhiệm phê duyệt và ngày xem xét lại.

## 8. RPO/RTO theo từng failure mode

| Failure mode | RPO cần xem | RTO cần xem | Chiến lược liên quan |
|---|---|---|---|
| PostgreSQL process crash | Thường rất thấp nhờ WAL recovery | Restart/recovery time | WAL, storage durability |
| Mất primary host | Standby lag/acknowledged commits | Failover/provision | HA, streaming replication |
| Mất một disk | Backup/replica durability | Rebuild/restore | Redundancy, physical backup |
| Xóa nhầm bảng | Mốc trước thao tác sai | PITR + extract data | Base backup + WAL |
| Lỗi application ghi sai | Mốc trước corruption | Clone/PITR/reconcile | Backup history |
| Mất region | Offsite copy/WAL replication | Cross-region restore | DR site, remote storage |
| Ransomware | Immutable point an toàn | Rebuild sạch và restore | Immutable/offline backups |
| Hỏng logic trong dữ liệu | Recovery point trước lỗi | Data repair/copy back | PITR, logical exports |

### 8.1. HA không giải quyết mọi failure modes

Nếu lệnh DROP TABLE được replay trên standby, standby cũng mất bảng. Cần backup/PITR để quay về trước thao tác sai.

### 8.2. PITR không tự giải quyết lỗi hệ điều hành/hạ tầng

Cần host, storage, network, PostgreSQL binaries, extensions, keys và runbook để thực hiện recovery.

### 8.3. Offsite backup không tự có RTO thấp

Tải nhiều terabytes qua WAN có thể mất nhiều giờ. Muốn RTO thấp cần kiểm tra restore bandwidth, compute capacity và khả năng dựng hạ tầng dự phòng.

### 8.4. Một sự cố có thể kích hoạt nhiều failure modes

Ví dụ ransomware xóa primary và cả backup credentials. Thiết kế phải xem blast radius và quyền xóa, không chỉ khoảng cách địa lý.



## 9. Logical backup: pg_dump và pg_dumpall

Logical backup biểu diễn schema và dữ liệu bằng các đối tượng SQL/logical representation. Với PostgreSQL, công cụ phổ biến là `pg_dump` cho một database và `pg_dumpall` cho databases cùng global objects theo options.

### 9.1. Ưu điểm

- Dễ chọn database/schema/table hoặc schema-only/data-only.
- Phù hợp migration và chuyển major version khi objects/extensions tương thích.
- Có thể restore vào database mới, chọn objects từ custom archive.
- Dễ lấy dữ liệu một phần để phục hồi bảng bị xóa nhầm.
- Ít gắn với physical data directory hơn backup vật lý.

### 9.2. Giới hạn

- Restore lớn có thể chậm vì phải tạo objects, nạp rows, build indexes/constraints.
- Dump một database không tự bao gồm mọi global roles/tablespaces.
- Dump không chứa WAL history để replay các giao dịch sau snapshot.
- Không tự sao lưu file cấu hình server, extension binaries, secrets hoặc dữ liệu hệ thống ngoài PostgreSQL.
- Một lần pg_dumpall qua nhiều databases không phải một snapshot MVCC nguyên tử xuyên toàn cluster.

### 9.3. Plain SQL và archive formats

`pg_dump -F p` tạo plain SQL, thường restore bằng psql. Custom (`-F c`), directory (`-F d`) và tar (`-F t`) restore bằng pg_restore với khả năng chọn objects tùy format.

### 9.4. Khi nào logical backup phù hợp?

Database nhỏ/vừa, RPO theo snapshot chấp nhận được, migration, clone test, phục hồi chọn lọc hoặc môi trường không yêu cầu PITR gần thời điểm sự cố.

### 9.5. Không đánh giá logical backup chỉ theo dung lượng

Một custom dump 50 GB có thể mất nhiều giờ để restore vì index build, constraints, I/O và concurrency. Đo restore throughput thực tế bằng data size và schema tương đương production.

## 10. Physical backup và base backup

Physical backup giữ database cluster ở mức file/page theo cơ chế backup phù hợp với PostgreSQL. Công cụ cơ bản là `pg_basebackup`; các giải pháp chuyên dụng có thể quản lý full/incremental/differential backups và catalog.

### 10.1. Ưu điểm

- Phù hợp khôi phục toàn cluster lớn.
- Có thể kết hợp WAL archive để PITR.
- Restore thường tránh phải tái tạo toàn bộ logical objects và build mọi index từ đầu.
- Phù hợp với chiến lược disaster recovery và standby bootstrap.

### 10.2. Giới hạn

- Gắn với PostgreSQL major version và physical format tương thích.
- Thường phục hồi toàn cluster, không chọn một table trực tiếp.
- Cần storage đủ lớn, permissions, tablespaces và cấu hình recovery.
- Muốn PITR phải giữ chuỗi WAL cần thiết.
- Không tự khôi phục các dịch vụ ngoài PostgreSQL như DNS, application secrets hay object storage.

### 10.3. Base backup không tự là PITR vô hạn

Một base backup có thể kèm WAL đủ để khởi động tới trạng thái nhất quán của backup. Để phục hồi tới mốc muộn hơn, cần WAL archive liên tục từ điểm backup tới target.

### 10.4. Lịch base backup

Full base backup mỗi ngày/tuần có thể kết hợp WAL archiving. Tần suất ảnh hưởng thời gian restore, storage consumption và số WAL phải replay; cần đo RTO.

### 10.5. Physical backup phải restore được

Không coi việc copy data directory khi PostgreSQL đang chạy là backup an toàn. Dùng backup protocol hoặc snapshot strategy bảo đảm tính nhất quán, bao gồm tablespaces và WAL theo yêu cầu.

## 11. WAL archiving và Point-in-Time Recovery

WAL ghi lại thay đổi cần thiết để PostgreSQL phục hồi và replication. Khi lưu WAL segments ở nơi độc lập, có thể replay sau khi restore base backup để đưa cluster tới một recovery target.

~~~text
Base backup B0
     |
     +-- WAL segment 0001
     +-- WAL segment 0002
     +-- WAL segment 0003
     +-- WAL segment 0004
     |
     v
Recovery target (time / LSN / transaction)
~~~

### 11.1. RPO thấp với WAL

Base backup có thể diễn ra mỗi ngày, nhưng nếu WAL archive được chuyển bền vững liên tục, recovery point có thể gần thời điểm sự cố hơn nhiều so với daily dump.

### 11.2. Archive lag là RPO exposure

Nếu WAL chưa được archive khi region mất, transaction gần nhất có thể chưa có trong remote recovery set. Monitor `pg_stat_archiver`, archive failures, WAL backlog và thời điểm WAL cuối đã đến storage an toàn.

### 11.3. WAL chain phải đầy đủ

Thiếu một segment cần thiết có thể ngăn replay tới target. Cần quản lý timeline, segment naming, retention và integrity.

### 11.4. Chọn recovery target

PostgreSQL có thể phục hồi tới thời điểm, transaction ID/LSN hoặc named restore point theo các cơ chế/phiên bản phù hợp. Timestamp phải có timezone rõ ràng và semantics inclusive/exclusive phải được hiểu.

### 11.5. PITR phục hồi trạng thái cluster

PITR không phải lệnh undo một row. Với lỗi logic, thường dựng cluster phụ tại thời điểm trước lỗi, lấy dữ liệu cần cứu rồi merge vào hệ thống hiện tại.

## 12. Replication và standby: giảm RTO nhưng không thay backup

Streaming replication gửi WAL từ primary tới standby để standby replay changes. Nếu primary gặp sự cố, standby có thể được promote để tiếp tục phục vụ.

### 12.1. Asynchronous replication

Primary có thể xác nhận commit trước khi standby nhận/replay WAL. Failover ngay sau commit có thể làm mất một số transaction đã được xác nhận trên primary nhưng chưa có trên standby.

- Ưu điểm: thường giảm độ trễ commit và ít phụ thuộc mạng standby.
- Rủi ro: replication lag tạo RPO khác zero.
- Cần đo: write/flush/replay lag, vị trí LSN và failure timing.

### 12.2. Synchronous replication

Primary có thể chờ acknowledgement từ standby theo `synchronous_commit`/synchronous standby configuration. Điều này có thể giảm nguy cơ mất các transactions đã được xác nhận trong failure model phù hợp.

- Ưu điểm: durability mạnh hơn khi standby đáp ứng yêu cầu acknowledgement.
- Chi phí: latency commit phụ thuộc mạng và standby.
- Rủi ro: standby/network outage có thể làm writes chậm hoặc chờ theo policy.
- Phải hiểu mức acknowledgement: remote write, remote flush hay remote apply có semantics khác nhau.

### 12.3. Synchronous không tự giải quyết mọi sự cố

Nếu commit chỉ chờ remote write/flush mà standby chưa apply, RTO và trạng thái sau failover cần hiểu theo đúng acknowledgement mode. Nếu lỗi logic đã commit, standby cũng có thể replay lỗi đó.

### 12.4. Standby không phải lịch sử backup

Replication thường duy trì gần trạng thái hiện tại. Nó không tự lưu các phiên bản cũ đủ lâu để phục hồi trước DELETE/UPDATE sai.

### 12.5. Delayed standby có thể là lớp bổ sung

Một standby cố ý replay chậm có thể tạo cửa sổ để nhận biết một số lỗi logic trước khi nó được áp dụng. Tuy nhiên, nó không thay backup offsite/immutable và cần quản lý lag, storage, failover policy riêng.

## 13. High availability, disaster recovery và backup

| Cơ chế | Mục tiêu chính | Bảo vệ tốt trước | Không tự giải quyết |
|---|---|---|---|
| Local redundancy | Hạn chế mất component | Một disk/device failure | Mất host/region, logical deletion |
| Streaming standby | HA/failover | Primary node failure | Corruption/xóa nhầm được replay |
| Cross-zone standby | HA trong một vùng địa lý | Zone failure | Region-wide loss, ransomware |
| Cross-region replica | DR/HA địa lý | Region failure theo topology | Logical corruption lan sang replica |
| Logical dump | Rebuild objects/data | Mất database tới snapshot | PITR sau snapshot |
| Base backup + WAL | Physical recovery/PITR | Mất cluster, lỗi logic trước target | Dependencies ngoài DB |
| Immutable/offline backup | Chống xóa/sửa backup | Ransomware/operator deletion | RTO thấp nếu restore chậm |

### 13.1. HA tập trung vào continuity

Mục tiêu là giữ service chạy hoặc phục hồi nhanh khi một component/node hỏng.

### 13.2. DR tập trung vào sự cố vượt phạm vi HA

Mục tiêu là dựng lại dịch vụ ở nơi khác khi mất hạ tầng hoặc một failure mode ảnh hưởng cả primary và replicas.

### 13.3. Backup tập trung vào khả năng quay lại recovery point

Backup cần giữ các trạng thái lịch sử và có thể phục hồi độc lập. Replica hiện tại không thay lịch sử đó.

### 13.4. Một hệ thống production thường cần cả ba

HA cho node failure, backup/PITR cho logical errors, offsite/immutable copies cho region/ransomware. RPO/RTO phải xác định theo từng failure mode.

## 14. Snapshots của storage/cloud

Storage snapshots có thể tạo điểm khôi phục nhanh nếu được phối hợp để bảo đảm PostgreSQL consistency.

### 14.1. Crash-consistent snapshots

Một snapshot crash-consistent mô phỏng trạng thái storage sau mất điện; PostgreSQL có thể cần WAL để crash recovery. Phải bảo đảm các volumes chứa PGDATA, tablespaces và WAL được snapshot đồng bộ theo hướng dẫn nền tảng.

### 14.2. Application-consistent snapshots

Có thể dùng cơ chế phối hợp/checkpoint/quiesce phù hợp để tạo snapshot có consistency semantics rõ. Không tự giả định snapshot của một volume là đủ.

### 14.3. Snapshot cùng storage account chưa chắc là offsite

Nếu account/region/identity bị compromise hoặc xóa, snapshots có thể bị mất cùng primary. Cần copy/replicate sang security boundary khác.

### 14.4. Snapshot không thay PITR

Snapshot cho một số điểm thời gian. Muốn phục hồi giữa các snapshots, cần WAL hoặc một cơ chế log tương ứng.

### 14.5. Snapshot retention

Quản lý lifecycle để không xóa snapshot đang được restore chain/retention policy cần tới. Thử restore từ snapshot, không chỉ kiểm tra snapshot metadata.

## 15. Managed PostgreSQL backups

Các dịch vụ PostgreSQL managed thường cung cấp automated backups, snapshots, retention và point-in-time restore theo mức dịch vụ.

### 15.1. Ưu điểm

Provider có thể tự động hóa backup schedule, WAL retention, storage redundancy, PITR, encryption và quy trình provision.

### 15.2. Không giả định mọi provider giống nhau

Giới hạn PITR window, RPO, RTO, cross-region copy, restore target, export formats và retention phụ thuộc provider/tier/region.

### 15.3. Restore time có thể khác nhau

Một managed restore có thể tạo instance mới và cần thời gian provision/restore; không đồng nghĩa bấm nút là database sẵn sàng tức thì.

### 15.4. Quota và operational dependencies

Kiểm tra quota instances/storage/IP, KMS/key availability, IAM permissions, network, parameter groups, extensions và khả năng kết nối ứng dụng.

### 15.5. Cần kiểm tra khả năng thoát provider

Logical exports và tài liệu restore độc lập có thể hữu ích khi cần migration hoặc contingency plan. Đừng để mọi bản sao và encryption keys phụ thuộc duy nhất một account mà không đánh giá blast radius.

## 16. Backup strategy theo quy mô database

| Đặc điểm | Chiến lược tham khảo | Rủi ro cần đo |
|---|---|---|
| Database nhỏ, ít writes | pg_dump định kỳ + offsite copy | Restore duration, snapshot age |
| Database vừa, RPO thấp | Base backup + WAL archive | Archive lag, replay time |
| Database lớn, RTO thấp | Physical backup, standby, automated provisioning | Restore throughput, failover, cost |
| Database nhiều TB | Backup tool hỗ trợ parallel/incremental + WAL | Chain complexity, network/disk bandwidth |
| Multi-tenant | Per-database/schema strategy + cluster-level recovery | Cross-tenant scope, roles, consistency |
| Time-series | Physical backup/WAL + partition lifecycle | Retention, partition DDL, replay |
| Critical ledger | Synchronous durability phù hợp + PITR + immutable backups | Commit semantics, independent recovery |

### 16.1. Database nhỏ không có nghĩa RTO nhỏ tự động

Một database 5 GB có thể restore chậm nếu network, disk, indexes hoặc extension setup kém.

### 16.2. Database lớn cần throughput thực tế

Với 4 TB data và effective restore throughput 200 MB/s, thời gian truyền lý tưởng đã nhiều giờ; còn phải tính decompression, WAL replay, index build, provisioning và validation.

### 16.3. Tối ưu RTO có thể cần standby

Nếu RTO thấp hơn thời gian physical restore, standby/HA có thể cần thiết. Nhưng vẫn duy trì backup/PITR để xử lý lỗi logic và disaster.

### 16.4. Tối ưu RPO có thể cần WAL/replication

Daily logical dumps không phù hợp yêu cầu RPO vài phút. Cần continuous WAL archiving và/hoặc replication durability theo failure model.

### 16.5. Chi phí tăng nhanh ở mức RPO/RTO nghiêm ngặt

Synchronous replicas, cross-region storage, immutable retention, standby capacity và restore drills đều có chi phí. Business cần phê duyệt mức bảo vệ tương xứng giá trị dữ liệu.


## 17. Chọn tần suất backup từ RPO

Nếu chỉ có snapshot backups, khoảng cách giữa các recovery points là một yếu tố lớn quyết định RPO tối đa có thể xảy ra.

### 17.1. Backup mỗi 24 giờ

Nếu chỉ có daily backup và sự cố xảy ra ngay trước lần kế tiếp, có thể mất gần 24 giờ dữ liệu. RPO worst-case xấp xỉ chu kỳ backup, chưa tính job failure/lag.

### 17.2. Backup mỗi giờ

Về lý thuyết, khoảng cách recovery points giảm còn gần một giờ, nhưng job phải hoàn tất, file phải bền vững và restore phải khả dụng.

### 17.3. WAL archiving liên tục

Kết hợp base backups định kỳ với WAL archive giúp tạo recovery points dày hơn. RPO thực tế chịu ảnh hưởng bởi archive delay và tính đầy đủ của WAL chain.

### 17.4. Replication

Standby có thể giảm RPO khi WAL được truyền/acknowledged phù hợp. Với asynchronous replication, có thể mất transactions chưa tới standby khi primary mất đột ngột.

### 17.5. Đặt ngưỡng alert nhỏ hơn RPO

Nếu RPO tối đa 15 phút, đừng đợi archive lag chạm 15 phút mới cảnh báo. Cần buffer để người vận hành xử lý trước khi vượt mục tiêu.

## 18. Chọn kiến trúc từ RTO

RTO phụ thuộc chủ yếu vào đường phục hồi và tốc độ thực thi các bước.

### 18.1. Restore từ logical dump

Thời gian có thể bao gồm tạo schema, load data, build indexes, validate constraints, restore permissions và chạy checks. Database lớn có thể restore lâu.

### 18.2. Restore từ physical backup

Có thể nhanh hơn logical rebuild, nhưng vẫn phụ thuộc tải dữ liệu, giải nén, replay WAL, storage throughput và provision.

### 18.3. Warm standby

Standby đã provision và replay WAL thường giúp failover nhanh hơn dựng mới từ backup. Phải có automation, health checks và quy trình promote/cutover.

### 18.4. Hot standby

Có thể phục vụ read traffic và sẵn sàng promote theo thiết kế. Cần monitor replay lag, conflicts, replication slots và capacity.

### 18.5. Pilot light / warm site / hot site

- **Pilot light:** giữ một phần hạ tầng tối thiểu, scale khi sự cố; chi phí thấp hơn nhưng provision/scale làm tăng RTO.
- **Warm site:** môi trường DR đã có phần lớn components, cần đồng bộ/cutover; cân bằng chi phí và RTO.
- **Hot site:** hạ tầng sẵn sàng gần như đầy đủ, có thể chuyển traffic nhanh hơn; chi phí vận hành cao.

Các thuật ngữ này mô tả mức sẵn sàng của môi trường DR, không phải loại PostgreSQL backup.

## 19. Đo restore throughput và ước lượng RTO

Giả sử database có 2 TB physical data. Restore throughput hiệu dụng là 250 MB/s:

~~~text
2 TB ≈ 2.000.000 MB (ước lượng thập phân)
transfer time ≈ 2.000.000 / 250
              ≈ 8.000 seconds
              ≈ 2 giờ 13 phút
~~~

Đây mới là thời gian truyền lý tưởng.

### 19.1. Những phần thời gian còn lại

- Provision compute/storage/network.
- Cấp credentials, certificates và encryption keys.
- Tải backup từ remote storage.
- Decrypt/decompress.
- Restore base backup hoặc logical objects.
- Replay WAL tới target.
- Build indexes/constraints nếu logical restore.
- Run ANALYZE/maintenance cần thiết.
- Kiểm tra dữ liệu và ứng dụng.
- Update DNS/endpoints và connection pools.
- Mở traffic và theo dõi.

### 19.2. Throughput phải đo ở điều kiện tương tự

Storage cùng region, cross-region bandwidth, compression ratio, concurrent workload và disk IOPS có thể làm throughput thay đổi lớn.

### 19.3. Restore có thể bottleneck ở CPU

Decompression, checksum, encryption và index builds có thể giới hạn CPU trước khi network/storage đạt max throughput.

### 19.4. WAL replay cũng cần thời gian

Nếu phải replay hàng giờ WAL sau base backup, RTO phụ thuộc write rate, WAL volume, CPU và storage random I/O.

### 19.5. Không dùng phép chia size/bandwidth làm cam kết

Đó chỉ là lower-bound estimate. RTO chính thức cần lấy từ restore drills có đo end-to-end.

## 20. Retention policy và số recovery points

Retention quyết định bạn có thể quay lại thời điểm nào trong quá khứ.

### 20.1. Retention ngắn

Giảm storage cost nhưng giảm khả năng phục hồi khi corruption/ransomware được phát hiện muộn.

### 20.2. Retention dài

Tăng khả năng quay lại trước lỗi phát hiện trễ, nhưng cần thêm storage, metadata, catalog và key lifecycle.

### 20.3. Retention phải xét WAL

Nếu giữ base backup 30 ngày nhưng WAL chain chỉ còn 2 ngày, PITR trong phần lớn 30 ngày có thể không khả dụng. Phải giữ đúng WAL cần thiết cho những base backups/recovery targets được cam kết.

### 20.4. Recovery point không phải backup file đơn lẻ

Một recovery point vật lý có thể phụ thuộc base backup, WAL segments, timeline history, configuration và metadata. Quản lý retention theo chain.

### 20.5. Phân tầng storage

Backup mới cần truy cập nhanh; backup cũ có thể chuyển sang cold/archive storage nếu thời gian retrieval vẫn đáp ứng mục tiêu recovery của kịch bản tương ứng.

## 21. Quy tắc 3-2-1 và biến thể 3-2-1-1-0

Quy tắc 3-2-1 là một cách ghi nhớ phổ biến:

- **3 copies:** giữ ít nhất ba bản dữ liệu (tính cả bản chính theo cách tổ chức quy định).
- **2 media/storage domains:** dùng ít nhất hai loại hoặc miền lưu trữ độc lập.
- **1 offsite:** có ít nhất một bản ở địa điểm khác với hệ thống chính.

Biến thể 3-2-1-1-0 thường bổ sung:

- **1 immutable/offline copy:** có một bản bất biến hoặc offline để giảm nguy cơ bị sửa/xóa cùng primary.
- **0 errors:** kiểm tra backup định kỳ, với mục tiêu không có lỗi chưa phát hiện.

### 21.1. Đây là nguyên tắc thiết kế, không phải chứng nhận

Không phải mọi workload đều cần cùng số lượng bản sao, nhưng phải có threat model giải thích vì sao số lượng/vị trí/quyền lưu trữ đáp ứng rủi ro.

### 21.2. Hai bản sao cùng account có thể cùng blast radius

Nếu một compromised identity có quyền xóa cả hai, chúng không độc lập về bảo mật dù nằm trên hai bucket.

### 21.3. Offsite cần thực sự tách biệt

Có thể là region khác, account/subscription khác, storage service độc lập hoặc backup vault có protection policy. Đánh giá cả quyền admin và key management.

### 21.4. Immutable cần test lifecycle

Object lock/retention lock có thể bảo vệ khỏi delete trong thời gian nhất định; cần biết ai có thể rút ngắn policy, thay đổi retention hoặc xóa account.

### 21.5. “0 errors” cần restore drills

Checksum và manifest giúp phát hiện corruption, nhưng restore test mới chứng minh có thể sử dụng backup.

## 22. Bảo vệ backup: encryption, identity và secrets

Backup thường chứa gần như toàn bộ dữ liệu nhạy cảm của database. Quyền truy cập backup có thể tương đương quyền đọc database.

### 22.1. Encryption at rest và in transit

Dùng encryption theo policy của tổ chức cho object storage, disks, backup transfer và các file dump. Kết nối truyền dữ liệu cần TLS phù hợp.

### 22.2. Key management

Backup mã hóa chỉ hữu ích nếu encryption key còn truy cập được khi disaster. Tách key recovery procedures và bảo vệ key material độc lập với account/region chính.

### 22.3. IAM tách biệt

Phân tách identities có quyền tạo backup, đọc/restore backup, xóa backup và quản lý retention/key. Không để application runtime identity có quyền xóa immutable backups.

### 22.4. Audit access

Ghi nhận ai tạo, đọc, copy, restore, thay retention hoặc xóa backup. Cảnh báo các hành vi bất thường như tải toàn bộ backup ngoài giờ.

### 22.5. Secrets trong dump

Logical dump có thể chứa password verifiers, tokens hoặc PII nằm trong tables; physical backup có thể chứa toàn bộ cluster data. Cả hai cần được bảo vệ như production data.

## 23. Retention và backup catalog

Một chiến lược backup cần biết mỗi artifact thuộc backup chain nào và có thể restore tới đâu.

### 23.1. Metadata nên ghi

- Backup ID và scope (database/cluster).
- Logical/physical/incremental type.
- PostgreSQL major/minor version và tool version.
- Thời gian bắt đầu/kết thúc job.
- Snapshot/consistent point hoặc LSN.
- WAL segment/timeline coverage.
- Storage URI và region/account.
- Encryption key reference (không ghi key).
- Checksum/manifest.
- Retention expiry và chain dependencies.
- Restore test gần nhất, kết quả và thời gian.

### 23.2. Không dùng file modified time thay recovery point

File có thể hoàn tất sau snapshot một khoảng dài. Recovery point phải lấy theo semantics của backup tool.

### 23.3. Catalog cũng cần backup

Nếu backup catalog mất, người vận hành có thể không biết thứ tự restore, dependencies hoặc encryption key reference. Lưu metadata ở một miền bảo vệ độc lập.

### 23.4. Backup chain cần dependency-aware cleanup

Không xóa full/base backup khi incremental backups hoặc WAL recovery points còn phụ thuộc.

### 23.5. Kiểm tra inventory

Định kỳ xác nhận số recovery points thực sự tồn tại, retention policy đang áp dụng và có thể đọc từ disaster recovery identity.

## 24. Lựa chọn chiến lược theo mức RPO/RTO

Bảng dưới là định hướng, không phải SLA mặc định. Kết quả thực tế phụ thuộc workload, provider, hạ tầng và diễn tập.

| Yêu cầu minh họa | Chiến lược thường cân nhắc | Điều kiện cần |
|---|---|---|
| RPO 24 giờ, RTO 1 ngày | Logical dump hằng ngày + offsite | Restore test đủ nhanh |
| RPO 1 giờ, RTO 4 giờ | Frequent logical/physical backups + WAL theo nhu cầu | Restore throughput và retention |
| RPO 15 phút, RTO 1 giờ | Base backup + continuous WAL archive; có thể thêm standby | WAL archive lag nhỏ, automation |
| RPO vài phút, RTO 15 phút | Synchronous/near-sync standby + PITR backups | Network durability, failover drills |
| RPO gần 0, RTO vài phút | HA synchronous architecture + independent backups | Failure model chặt, cross-site design, operational readiness |
| Mất region, RTO vài giờ | Cross-region backups/WAL và DR site | Capacity, keys, network, runbook |
| Xóa nhầm dữ liệu | PITR + isolated recovery environment | WAL chain, target selection, data merge |

### 24.1. Không suy RPO từ replication mode duy nhất

Cần hiểu `synchronous_commit`, `synchronous_standby_names`, quorum/priority behavior, standby state và failure mode. Một cấu hình synchronous không tự bảo vệ trước mọi mất mát.

### 24.2. Không suy RTO từ standby tồn tại

Standby có thể down, lag, thiếu capacity hoặc failover cần quyết định thủ công. Đo thời gian promote, routing và application readiness.

### 24.3. RPO/RTO nên được chia theo service tier

Một hệ thống có thể có primary transactional database ở tier cao và analytics database ở tier thấp. Chiến lược tương ứng sẽ khác.

## 25. Ma trận lựa chọn: logical, physical, WAL, replica và immutable

| Tiêu chí | Logical dump | Physical base backup | WAL archive/PITR | Standby/replica | Immutable copy |
|---|---|---|---|---|---|
| Khôi phục objects/data | Có | Có | Replay trên base | Replay state | Tùy bản sao |
| Chọn một bảng | Thuận tiện hơn | Không trực tiếp | Không trực tiếp | Không trực tiếp | Không trực tiếp |
| PITR | Không đơn lẻ | Cần WAL | Có cùng base backup | Không phải mục tiêu chính | Bảo vệ artifacts |
| RTO thấp | Có thể chậm với DB lớn | Tùy throughput | Phụ thuộc replay | Thường tốt hơn | Không tự nhanh |
| Chuyển major version | Thường thuận tiện | Không dùng trực tiếp | Gắn với physical chain | Gắn topology/version | Tùy nội dung |
| Chống logical corruption | Có recovery snapshot | Có nếu target trước lỗi | Có thể PITR | Thường replay lỗi | Bảo vệ backup |
| Chống mất region | Cần offsite | Cần offsite | Cần archive offsite | Cross-region nếu có | Cần độc lập region |
| Chống ransomware | Cần immutable copy | Cần immutable copy | WAL cũng cần bảo vệ | Replica có thể bị ảnh hưởng | Mục tiêu chính |

## 26. Lựa chọn chiến lược cho PostgreSQL production

Một kiến trúc tham khảo cho database quan trọng có thể có:

~~~text
                         PostgreSQL Primary
                                 |
                    +------------+------------+
                    |                         |
                    v                         v
             Synchronous/async          WAL archive
                 Standby               remote storage
                    |                         |
                    v                         v
                HA failover              PITR recovery
                                              |
Primary/cluster -- base backup ---------------+
       |
       +-- logical dumps for selected objects/migration
       |
       +-- immutable/offsite backup copy
       |
       +-- backup catalog, keys, runbooks
~~~

### 26.1. Standby cho node failure

Giảm RTO trong những sự cố phù hợp; cần monitor replication lag và promotion readiness.

### 26.2. Base backup + WAL cho PITR

Tạo khả năng phục hồi toàn cluster tới target đã chọn; phải giữ đầy đủ WAL và timeline history.

### 26.3. Logical dump cho selective restore/migration

Có thể thuận tiện để lấy một bảng hoặc chuyển objects sang môi trường mới. Không thay thế physical DR khi database lớn.

### 26.4. Immutable/offsite cho blast radius lớn

Giảm nguy cơ backup bị xóa hoặc mã hóa cùng primary. Cần identity/key độc lập và restore access đã thử.

### 26.5. Configuration và application dependencies

Lưu parameter settings, HBA/TLS configuration, extension inventory, secrets references, DNS/routing và deployment artifacts theo policy. Không nhét plaintext secrets vào runbook.


## 27. RPO/RTO calculation: snapshot-only strategy

Nếu chỉ có snapshot backups, khoảng cách giữa các recovery points là một yếu tố lớn quyết định RPO tối đa có thể xảy ra.

### 27.1. Backup mỗi 24 giờ

Nếu chỉ có daily backup và sự cố xảy ra ngay trước lần kế tiếp, có thể mất gần 24 giờ dữ liệu. RPO worst-case xấp xỉ chu kỳ backup, chưa tính job failure/lag.

### 27.2. Backup mỗi giờ

Về lý thuyết, khoảng cách recovery points giảm còn gần một giờ, nhưng job phải hoàn tất, file phải bền vững và restore phải khả dụng.

### 27.3. WAL archiving liên tục

Kết hợp base backups định kỳ với WAL archive giúp tạo recovery points dày hơn. RPO thực tế chịu ảnh hưởng bởi archive delay và tính đầy đủ của WAL chain.

### 27.4. Replication

Standby có thể giảm RPO khi WAL được truyền/acknowledged phù hợp. Với asynchronous replication, có thể mất transactions chưa tới standby khi primary mất đột ngột.

### 27.5. Đặt ngưỡng alert nhỏ hơn RPO

Nếu RPO tối đa 15 phút, đừng đợi archive lag chạm 15 phút mới cảnh báo. Cần buffer để người vận hành xử lý trước khi vượt mục tiêu.

## 28. RPO với WAL archive và replication

Với physical base backup và WAL archive, recovery point có thể nằm gần thời điểm sự cố nếu WAL cuối đã được lưu bền vững và chain đầy đủ.

### 28.1. Đo archive delay

Có thể quan sát trạng thái archiver qua view phù hợp:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Các cột và hành vi phụ thuộc phiên bản. View này là một tín hiệu; để tính RPO chính xác cần biết WAL segment nào đã được remote storage xác nhận bền vững.

### 28.2. Archive command thành công là gì?

Cơ chế archive phải chỉ báo success sau khi WAL segment được lưu đầy đủ theo durability policy. Nếu script chỉ copy vào local temp rồi trả success trước remote upload, server có thể coi segment đã archive dù DR copy chưa sẵn sàng.

### 28.3. WAL segment chưa đầy có thể chưa archive

WAL archiving thường xử lý segments theo cơ chế segment completion/timeout; `archive_timeout` có thể giúp tạo archive segments thường xuyên hơn trong workload thấp, nhưng không thay durability confirmation.

### 28.4. RPO theo remote durability

Nếu remote object storage xác nhận một WAL segment sau 4 phút và sự cố xảy ra ngay trước segment kế tiếp được archive, RPO có thể lớn hơn 4 phút tùy write pattern, WAL generation và archive behavior. Phải đo trên timeline thật.

### 28.5. Replication lag đo nhiều giai đoạn

Write, flush và replay LSN khác nhau. Một transaction được standby nhận nhưng chưa replay không có nghĩa read queries trên standby đã nhìn thấy nó; promotion/recovery behavior cần hiểu theo replication mode.

## 29. RTO calculation: chia nhỏ các giai đoạn

Một RTO end-to-end có thể được mô hình hóa:

~~~text
T_RTO =
  T_detect
+ T_decide
+ T_provision
+ T_retrieve
+ T_restore
+ T_replay
+ T_validate
+ T_cutover
~~~

Không phải mọi bước đều tuần tự. Một số có thể song song, nhưng hãy chỉ tính song song khi runbook và tooling thực sự hỗ trợ.

### 29.1. T_detect

Thời gian từ khi sự cố bắt đầu tới khi monitoring/on-call nhận biết.

### 29.2. T_decide

Thời gian xác định scope, failure mode, recovery point và người có quyền phê duyệt.

### 29.3. T_provision

Tạo compute, storage, network, security groups, DNS và database runtime.

### 29.4. T_retrieve

Tải backup, WAL, config và dependencies từ nơi lưu trữ. Cold storage retrieval có thể kéo dài.

### 29.5. T_restore và T_replay

Logical restore, physical restore và WAL replay có bottlenecks khác nhau. Đo riêng từng bước.

### 29.6. T_validate và T_cutover

Chạy integrity/business checks, mở kết nối ứng dụng, chuyển traffic và xác nhận health. Không cắt phần này chỉ để báo RTO thấp hơn.

## 30. DR runbook: từ sự cố tới phục hồi

Một runbook có thể chia thành các giai đoạn:

### Giai đoạn A — Detect và declare

- Xác nhận sự cố thật và phạm vi ảnh hưởng.
- Xác định primary còn an toàn để ghi hay cần fence.
- Chỉ định incident commander và technical recovery lead.
- Ghi thời điểm bắt đầu, timezone và failure mode.
- Thông báo các bên liên quan theo incident policy.

### Giai đoạn B — Chọn recovery point

- Đối chiếu RPO đã phê duyệt.
- Xác định backup ID/base backup phù hợp.
- Kiểm tra WAL chain/timeline nếu PITR.
- Chọn target trước logical corruption nếu cần.
- Xác nhận remote copies, encryption keys và catalog truy cập được.

### Giai đoạn C — Dựng môi trường

- Provision PostgreSQL version tương thích.
- Chuẩn bị data directory/tablespaces và permissions.
- Cài extension binaries và cấu hình.
- Cô lập network để tránh ứng dụng ghi vào cluster chưa được xác nhận.
- Tải/giải mã backup và WAL.

### Giai đoạn D — Restore và recover

- Logical: tạo database đích, restore globals/objects/data theo runbook.
- Physical: restore base backup, cấu hình WAL retrieval và recovery target.
- Kiểm tra errors, logs, progress và resource usage.
- Không promote/cutover khi chưa xác định recovery target và trạng thái cluster.

### Giai đoạn E — Validate

- Kiểm tra schema, constraints, indexes và sequences.
- Kiểm tra row counts, business invariants và các aggregate quan trọng.
- Kiểm tra roles, ownership, grants, RLS và extensions.
- Chạy smoke tests read/write trong môi trường cô lập.
- Xác nhận external dependencies và integration state.

### Giai đoạn F — Cutover

- Fence/disable old primary nếu cần để tránh split-brain.
- Cập nhật DNS/service discovery/endpoints.
- Refresh connection pools và credentials.
- Mở traffic theo từng bước, theo dõi error rate và replication.
- Ghi lại recovered point và dữ liệu có thể bị mất theo RPO.

### Giai đoạn G — Rebuild protection

- Thiết lập lại backup schedule và WAL archiving.
- Recreate standby/replication slots theo runbook.
- Kiểm tra archive retention và offsite copy.
- Theo dõi cho tới khi HA/backup protection trở lại mức yêu cầu.
- Thực hiện post-incident review và cập nhật runbook.

## 31. Recovery point selection và logical errors

Khi lỗi là một thao tác hợp lệ về SQL nhưng sai nghiệp vụ (ví dụ DELETE nhầm), recovery point cần nằm trước commit gây lỗi.

### 31.1. Xác định thời điểm sai

Dùng audit log, application logs, transaction/event metadata và người vận hành để khoanh vùng thời điểm. Đồng bộ clock là điều kiện quan trọng.

### 31.2. Dựng bản phục hồi song song

Restore PITR vào cluster cô lập, không rollback toàn bộ production ngay nếu production vẫn nhận giao dịch hợp lệ sau lỗi.

### 31.3. Trích phần cần cứu

Copy bảng/rows/relations cần thiết, kiểm tra foreign keys và các giao dịch phát sinh sau recovery point.

### 31.4. Reconcile với hiện tại

Cần quy tắc xử lý conflict: row nào đã được sửa hợp lệ sau lỗi, transaction nào đã phát message, payment nào đã được xử lý bên ngoài.

### 31.5. Không mở hai primary cùng ghi

Cluster PITR phụ phải được fence/cô lập cho tới khi hoàn tất extraction hoặc có một kế hoạch cutover rõ.

## 32. RPO/RTO cho nhiều database và dịch vụ liên quan

Một ứng dụng có thể dùng nhiều PostgreSQL databases, queue, object storage, cache và payment services.

### 32.1. Snapshot một database không phải snapshot toàn hệ thống

Hai databases có thể có logical dumps tại các thời điểm khác nhau. Nếu transaction nghiệp vụ trải qua cả hai, restored state có thể không đồng nhất.

### 32.2. External systems cần recovery policy riêng

Message broker, object storage, search index và payment provider có backup/retention/consistency model khác PostgreSQL.

### 32.3. Transactional outbox và idempotency

Các pattern như transactional outbox giúp liên kết database commit với event publishing theo cách có thể retry/reconcile. Chúng không tự tạo distributed snapshot nhưng hỗ trợ recovery semantics.

### 32.4. Recovery ordering

Runbook cần biết service nào khôi phục trước, queue nào pause, consumer nào replay, và cách tránh xử lý trùng events.

### 32.5. Một RPO chung có thể gây hiểu nhầm

Định nghĩa RPO cho database, event log và external financial state; sau đó xác định business consistency objective cho toàn workflow.

## 33. Cost model: RPO/RTO càng nghiêm ngặt, chi phí càng cao

Chi phí backup/DR gồm nhiều phần:

- Storage của full/incremental backups và WAL.
- Cross-region replication/egress/network.
- Standby compute và storage luôn chạy.
- Immutable retention và backup vault.
- Encryption/KMS và identity administration.
- Monitoring, catalog và orchestration.
- Nhân lực trực, diễn tập và post-incident recovery.
- Dung lượng dự phòng cho restore/rebuild.

### 33.1. Storage cost

Retention dài và nhiều copies làm storage tăng. Compression/deduplication có thể giảm cost nhưng thêm CPU hoặc dependency.

### 33.2. Standby cost

Hot standby có thể tốn compute gần bằng primary. Warm/pilot-light giảm chi phí nhưng tăng provisioning time/RTO.

### 33.3. Network cost

Cross-region WAL/backup replication có thể tạo egress và bandwidth costs. Cần đo write volume và peak bursts.

### 33.4. Operational cost

Một kiến trúc nhiều công cụ backup có thể giảm RTO nhưng tăng complexity. Nếu không ai có thể vận hành khi incident, thiết kế không đạt mục tiêu.

### 33.5. Business impact cost

So sánh chi phí bảo vệ với tổn thất kỳ vọng khi downtime/mất dữ liệu. RPO/RTO là quyết định đầu tư, không chỉ setting kỹ thuật.

## 34. Recovery tiers và ưu tiên phục hồi

Khi disaster ảnh hưởng nhiều hệ thống, không thể phục hồi tất cả cùng lúc. Cần thứ tự ưu tiên.

| Tier | Mục tiêu | Ví dụ minh họa |
|---|---|---|
| Tier 0 | Nền tảng cần cho recovery | Identity, network, key vault, DNS |
| Tier 1 | Dịch vụ giao dịch thiết yếu | Payment/order ledger |
| Tier 2 | Dịch vụ vận hành phụ thuộc | Inventory, customer workflow |
| Tier 3 | Báo cáo và analytics | Warehouse, dashboards |
| Tier 4 | Dữ liệu có thể tái tạo | Cache, derived indexes |

### 34.1. Dependencies quyết định thứ tự

Không thể khôi phục application database nếu key management, network hoặc identity provider chưa sẵn sàng.

### 34.2. Recovery capacity phải chia sẻ

Nhiều databases cùng restore có thể cạnh tranh disk/network. Runbook phải xác định parallelism và thứ tự.

### 34.3. Tier thấp vẫn có RPO/RTO

Một hệ thống analytics có thể chấp nhận RPO 24 giờ/RTO 1 ngày, nhưng phải ghi rõ thay vì mặc định không cần backup.

### 34.4. Business owner phê duyệt thứ tự

Thứ tự phục hồi có thể khác theo thời điểm, mùa cao điểm hoặc regulatory obligations. Cần diễn tập cùng các team liên quan.

### 34.5. Recovery tiers phải được kiểm tra

Không chỉ có tài liệu: phải thử dựng identity/network, key access và database theo đúng thứ tự.


## 35. Restore drills và diễn tập

Một restore drill là lần thực hành khôi phục từ artifacts thực tế theo runbook, nhằm đo khả năng phục hồi và phát hiện gaps trước khi có sự cố thật.

### 35.1. Tabletop exercise

Các bên đi qua một kịch bản trên giấy: ai declare incident, ai chọn recovery point, ai phê duyệt cutover, dependencies nào phải sẵn sàng. Đây là bước tốt để kiểm tra quyết định và liên lạc nhưng không chứng minh restore kỹ thuật.

### 35.2. Technical restore test

Khôi phục backup vào môi trường cô lập, chạy PostgreSQL, kiểm tra schema/rows/permissions và ứng dụng. Đây là bằng chứng trực tiếp hơn về recoverability.

### 35.3. PITR drill

Chọn một mốc thời gian, restore base backup, replay WAL tới target, xác minh dữ liệu trước/sau target và ghi lại thời gian. Cần thực hiện cả khi dùng managed service có nút PITR.

### 35.4. Region-loss exercise

Giả lập primary region không thể truy cập. Chỉ dùng remote copies, identities, keys và network được thiết kế cho DR. Không lấy file từ primary region trong lúc test rồi tuyên bố cross-region recovery đã chứng minh.

### 35.5. Ransomware/immutable exercise

Kiểm tra người vận hành có thể truy cập backup bằng identity sạch, retention lock có hiệu lực và encryption key có thể phục hồi sau khi production credentials bị vô hiệu hóa.

### 35.6. Lịch diễn tập

Tần suất phụ thuộc criticality và tốc độ thay đổi hệ thống. Cần diễn tập sau thay đổi lớn của PostgreSQL version, backup tooling, storage, network, IAM hoặc application dependencies.

## 36. Đo lường và ghi nhận kết quả drill

Ghi lại một timeline có thể so sánh giữa các lần:

| Mốc | Thời điểm | Ý nghĩa |
|---|---|---|
| T0 | Incident declared | Bắt đầu RTO theo quy ước |
| T1 | Recovery decision | Đã chọn chiến lược/target |
| T2 | Infrastructure ready | Compute/network/storage sẵn sàng |
| T3 | Backup accessible | Artifact/key tải được |
| T4 | Database recovered | PostgreSQL đạt recovery target |
| T5 | Validation passed | Checks dữ liệu và quyền đạt |
| T6 | Application ready | Smoke tests end-to-end đạt |
| T7 | Traffic cutover | Dịch vụ mở lại theo policy |

### 36.1. RTO đo tới mốc nào?

Nếu định nghĩa service-ready tại T6, RTO = T6 - T0. Nếu business yêu cầu traffic mở lại tại T7, dùng T7 - T0. Chốt semantics trước khi đo.

### 36.2. RPO đo từ recovery point

Ghi rõ snapshot time hoặc transaction/LSN boundary phục hồi được, so với mốc dữ liệu ngay trước sự cố giả lập.

### 36.3. Không bỏ qua dữ liệu chưa reconcile

Database có thể mở được nhưng outbox/queue/payment state chưa đồng nhất. Ghi nhận recovery point và business data gap.

### 36.4. Lưu logs và evidence

Giữ command logs, backup IDs, manifest/checksums, version info, durations, errors và kết quả business checks. Không đưa credentials/PII vào evidence.

### 36.5. Mỗi drill phải tạo hành động cải tiến

Ví dụ tăng bandwidth, chuẩn bị extension packages, sửa IAM, bổ sung DNS steps hoặc cập nhật runbook. Lần drill tiếp theo xác nhận hành động đã có tác dụng.

## 37. Ví dụ chiến lược theo service tier

### 37.1. Tier 1 — Order/payment database

- RPO rất thấp theo failure mode đã định nghĩa.
- RTO ngắn, có standby/failover automation.
- Base backups và WAL archive độc lập.
- Immutable/offsite retention.
- Restore/PITR drills thường xuyên.
- Audit, key recovery và role dependencies được ghi lại.

### 37.2. Tier 2 — Inventory/workflow

- Có thể chấp nhận RPO 15–60 phút tùy nghiệp vụ.
- Base backup + WAL hoặc managed PITR.
- Warm standby nếu RTO yêu cầu.
- Cross-region copy theo mức rủi ro.
- Kiểm tra reconciliation với order/payment services.

### 37.3. Tier 3 — Analytics

- RPO vài giờ hoặc một ngày nếu dữ liệu có thể tái tạo.
- Logical/physical backups theo size và restore time.
- Rebuild pipeline và source retention có thể là một phần DR.
- RTO dài hơn có thể giảm standby costs.

### 37.4. Tier 4 — Cache/derived data

- Có thể rebuild từ source of truth.
- Cần lưu configuration/schema và pipeline artifacts.
- Xác định thời gian rebuild và capacity thay vì chỉ nói cache không cần backup.

### 37.5. Không gán tier chỉ theo kích thước database

Một database nhỏ chứa payment ledger có thể critical hơn warehouse nhiều terabytes.

## 38. Lab: tính RPO từ lịch backup

Giả sử một database chỉ có logical dumps, lịch backup và sự cố như sau:

~~~text
01:00  Dump A snapshot hoàn tất
07:00  Dump B snapshot hoàn tất
13:00  Dump C bắt đầu, nhưng chưa upload xong
14:30  Sự cố mất host và storage nguồn
~~~

### 38.1. Chọn recovery point

Nếu Dump A và B đều nằm ở offsite storage và restore được, Dump B là recovery point gần nhất. Dump C chưa upload xong không được tính.

### 38.2. Tính RPO

~~~text
RPO = 14:30 - 07:00
    = 7 giờ 30 phút
~~~

### 38.3. So với yêu cầu

Nếu business yêu cầu RPO tối đa 1 giờ, chiến lược snapshot-only này không đạt.

### 38.4. Cải thiện

Có thể tăng tần suất logical/physical backups, hoặc dùng base backup + continuous WAL archiving. Lựa chọn phụ thuộc database size và RTO.

### 38.5. Tính worst-case, không chỉ ngày thuận lợi

Đưa backup job failures, upload delay và retention gaps vào mô hình.

## 39. Lab: tính RTO end-to-end

Giả sử restore drill đo được:

| Công đoạn | Thời gian |
|---|---:|
| Detect/declare | 5 phút |
| Chọn recovery point | 10 phút |
| Provision hạ tầng | 15 phút |
| Tải/giải mã backup | 20 phút |
| Restore + WAL replay | 35 phút |
| Validation | 15 phút |
| Cutover/smoke tests | 10 phút |

~~~text
RTO = 5 + 10 + 15 + 20 + 35 + 15 + 10
    = 110 phút
    = 1 giờ 50 phút
~~~

### 39.1. So với target

Nếu RTO objective là 1 giờ, quy trình hiện tại không đạt.

### 39.2. Tìm bottleneck

Restore + WAL replay mất 35 phút và retrieval mất 20 phút; provision và quyết định cũng chiếm thời gian. Có thể tối ưu pre-provisioned standby, network throughput, parallel restore hoặc automation.

### 39.3. Không bỏ validation

Rút validation từ 15 phút xuống 0 không phải tối ưu hợp lý nếu làm tăng nguy cơ mở traffic trên dữ liệu lỗi.

### 39.4. Đo nhiều lần

Thời gian phụ thuộc cache, storage load, network và database size. Dùng percentile/điều kiện peak để thiết kế buffer.

### 39.5. Cập nhật RTO đã công bố

Nếu chưa thể cải thiện đủ, phải báo business rằng RTO thực tế cao hơn mục tiêu và có quyết định chấp nhận rủi ro hoặc đầu tư.

## 40. Lab: thiết kế chiến lược cho ba workload

### Bài toán A — Blog database

- 30 GB, writes vừa phải.
- Business chấp nhận RPO 24 giờ.
- RTO 8 giờ.
- Có thể rebuild một số dữ liệu từ CMS exports.

Một chiến lược logical dump hằng ngày, offsite copy và restore test có thể phù hợp nếu thời gian restore đo được nằm trong RTO. Có thể bổ sung physical backup khi cần giảm restore time.

### Bài toán B — E-commerce orders

- 2 TB, writes liên tục.
- RPO 5 phút.
- RTO 45 phút.
- Có lỗi logic/xóa nhầm cần PITR.

Cần xem base backup + WAL archive với remote durability và archive lag được monitor; standby phù hợp để giảm RTO; immutable offsite copies bảo vệ backup; PITR drills và selective data recovery runbook.

### Bài toán C — Analytics warehouse

- 8 TB, dữ liệu tái tạo từ event lake.
- RPO 24 giờ.
- RTO 24 giờ.
- Storage cost quan trọng.

Có thể ưu tiên backup theo chu kỳ và rebuild pipeline, logical/physical tùy thời gian restore. Cần kiểm tra event source retention, compute capacity và RTO thực tế.

### 40.1. Không có một đáp án duy nhất

Các chiến lược là gợi ý để phân tích. Business impact, regulatory obligations, provider capabilities và restore drills quyết định phương án cuối.

### 40.2. Bài tập mở rộng

Thêm failure mode mất cả region hoặc ransomware và xem mỗi chiến lược có thay đổi không.


## 41. Các lỗi thường gặp khi thiết kế RPO/RTO

1. Đặt RPO bằng tần suất backup mà không đo job completion/remote durability.
2. Đặt RTO bằng thời gian PostgreSQL start mà bỏ qua application readiness.
3. Chỉ thử restore trên cùng host/storage với primary.
4. Có standby nhưng không có backup lịch sử/PITR.
5. Có WAL archive nhưng không kiểm tra WAL chain/timeline.
6. Giữ base backups nhưng xóa WAL cần thiết cho recovery points.
7. Backup mã hóa nhưng không diễn tập key recovery.
8. Có offsite copy nhưng IAM cho phép primary identity xóa cả bản offsite.
9. Chọn RPO 0 mà không định nghĩa failure model/commit acknowledgement.
10. Chọn synchronous replication nhưng không đánh giá network partition và availability trade-offs.
11. Ước lượng RTO bằng dung lượng chia bandwidth mà không tính replay/validation.
12. Không tính thời gian incident declaration và decision.
13. Không có người chịu trách nhiệm và quyền cutover.
14. Không khôi phục roles/extensions/configuration/dependencies.
15. Không có kế hoạch xử lý external services và queues.
16. Chỉ restore toàn database, không thử selective recovery.
17. Không ghi nhận recovery point/timeline/timezone.
18. Không kiểm tra backup retention và catalog.
19. Không diễn tập sau thay đổi version/hạ tầng.
20. Dùng một RPO/RTO chung cho mọi database dù business impact khác nhau.

## 42. Bài tập thực hành

### Bài 1 — Định nghĩa RPO

RPO 30 phút có nghĩa gì?

**Đáp án:** Tổ chức chấp nhận phục hồi dữ liệu cũ tối đa khoảng 30 phút so với thời điểm sự cố, theo failure model và cách đo đã định nghĩa.

### Bài 2 — Định nghĩa RTO

RTO 2 giờ có nghĩa gì?

**Đáp án:** Dịch vụ phải trở lại trạng thái hoạt động đã định nghĩa trong tối đa 2 giờ kể từ mốc bắt đầu sự cố theo quy ước.

### Bài 3 — Snapshot-only

Backup hoàn tất lúc 02:00, sự cố lúc 11:00, không có recovery point mới hơn. RPO?

**Đáp án:** Khoảng 9 giờ.

### Bài 4 — Backup job đang chạy

Job bắt đầu trước sự cố nhưng chưa hoàn tất/upload bền vững. Có được tính là recovery point không?

**Đáp án:** Không, trừ khi quy trình chứng minh artifact nhất quán và truy cập được.

### Bài 5 — RTO timeline

Sự cố 09:00, application smoke test thành công 11:15. RTO end-to-end theo service-ready là bao nhiêu?

**Đáp án:** 2 giờ 15 phút.

### Bài 6 — Logical dump

pg_dump đơn lẻ có phục hồi tới thời điểm sau snapshot không?

**Đáp án:** Không; cần lịch sử WAL/nguồn khác cho những thay đổi sau snapshot.

### Bài 7 — Physical backup

Base backup cần gì để PITR tới mốc muộn hơn?

**Gợi ý:** Chuỗi WAL đầy đủ và recovery configuration/target.

### Bài 8 — Standby

Standby có thay backup lịch sử không?

**Đáp án:** Không.

### Bài 9 — Asynchronous replication

Rủi ro RPO khi primary mất ngay sau commit là gì?

**Gợi ý:** Transaction có thể chưa tới/flush/replay trên standby.

### Bài 10 — Synchronous replication

Synchronous replication có thể đánh đổi điều gì?

**Gợi ý:** Commit latency và availability khi standby/network không đáp ứng acknowledgement.

### Bài 11 — RPO 0

Có thể tuyên bố RPO 0 chỉ vì cấu hình synchronous standby không?

**Đáp án:** Không; phải xác định acknowledgement semantics và failure model.

### Bài 12 — RTO và standby

Vì sao standby thường giúp RTO ngắn hơn restore từ backup?

**Gợi ý:** Nó đã được provision và replay gần trạng thái hiện tại.

### Bài 13 — Logical corruption

Tại sao standby không bảo vệ chắc chắn khỏi DROP TABLE nhầm?

**Đáp án:** Thay đổi có thể được replay sang standby.

### Bài 14 — Immutable copy

Immutable backup bảo vệ trước rủi ro gì?

**Gợi ý:** Xóa/sửa backup bởi attacker hoặc operator trong retention period.

### Bài 15 — Offsite

Hai bucket trong cùng account/region có thể có cùng blast radius không?

**Đáp án:** Có.

### Bài 16 — Encryption key

Backup encrypted nhưng key không còn truy cập được có recoverable không?

**Đáp án:** Không.

### Bài 17 — Retention

Giữ base backup 30 ngày nhưng WAL chỉ 2 ngày có thể làm mất khả năng gì?

**Đáp án:** PITR tới phần lớn recovery targets trong 30 ngày.

### Bài 18 — Archive lag

Vì sao archive lag ảnh hưởng RPO?

**Gợi ý:** WAL gần nhất chưa có bản sao bền vững ở nơi DR.

### Bài 19 — RTO calculation

Restore data 1 giờ, WAL replay 20 phút, validation 15 phút, cutover 10 phút; chưa tính detect/provision. Tổng tối thiểu?

**Đáp án:** 1 giờ 45 phút, chưa tính các bước còn thiếu.

### Bài 20 — Throughput

Một database 1 TB restore ở 100 MB/s. Thời gian truyền lý tưởng theo TB thập phân?

**Đáp án:** Khoảng 10.000 giây, tức 2 giờ 46 phút 40 giây; thực tế còn các overhead khác.

### Bài 21 — MTD

MTD 4 giờ và RTO 6 giờ có phù hợp không?

**Đáp án:** Không; RTO vượt thời gian downtime tối đa business chấp nhận.

### Bài 22 — WRT

Database và ứng dụng đã chạy nhưng backlog events cần thêm 2 giờ để xử lý. Khái niệm thời gian này là gì?

**Đáp án:** Work Recovery Time (WRT), theo định nghĩa vận hành đã chọn.

### Bài 23 — Tiering

Vì sao analytics warehouse có thể có RPO/RTO khác payment ledger?

**Gợi ý:** Business impact và khả năng tái tạo dữ liệu khác nhau.

### Bài 24 — Cross-region DR

Offsite backup ở region khác nhưng thiếu KMS key access. Điều gì xảy ra?

**Đáp án:** Có thể không giải mã/restore được.

### Bài 25 — Backup catalog

Vì sao cần bảo vệ backup catalog?

**Gợi ý:** Nó ghi scope, version, recovery point, chain, key references và vị trí artifacts.

### Bài 26 — Restore drill

Tabletop exercise có chứng minh backup restore thành công không?

**Đáp án:** Không; cần technical restore test.

### Bài 27 — PITR drill

Cần kiểm tra những gì ngoài việc PostgreSQL start?

**Gợi ý:** Target/timezone, WAL chain, schema/data, business invariants và application.

### Bài 28 — Failure modes

Mất host và xóa nhầm bảng cần chiến lược giống hệt nhau không?

**Đáp án:** Không; host loss có thể failover, logical deletion cần lịch sử/PITR.

### Bài 29 — Multi-database consistency

Vì sao dump hai databases ở hai thời điểm có thể không nhất quán nghiệp vụ?

**Gợi ý:** Không có distributed snapshot chung.

### Bài 30 — Recovery order

Tại sao key vault/network/identity có thể cần phục hồi trước PostgreSQL?

**Gợi ý:** Chúng là dependencies để provision, decrypt và kết nối.

### Bài 31 — Immutable identity

Vì sao backup delete permission nên tách khỏi application identity?

**Gợi ý:** Giảm blast radius khi application credentials bị compromise.

### Bài 32 — WAL archive success

Archive command nên báo success khi nào?

**Gợi ý:** Khi segment được lưu đầy đủ theo durability contract, không chỉ copy vào local temporary path.

### Bài 33 — Synchronous semantics

Remote write, remote flush và remote apply có giống nhau không?

**Đáp án:** Không; chúng xác nhận các giai đoạn khác nhau.

### Bài 34 — RPO theo event

Nếu database phục hồi nhưng message queue chưa replay events, có thể có consistency gap không?

**Đáp án:** Có; cần reconcile và idempotency.

### Bài 35 — Chi phí

Yếu tố nào làm RTO thấp thường tăng chi phí?

**Gợi ý:** Standby capacity, cross-region infrastructure, automation, network và diễn tập.

### Bài 36 — Backup schedule

Nếu backup mỗi 6 giờ, worst-case RPO snapshot-only có thể gần bao nhiêu?

**Đáp án:** Gần 6 giờ cộng các job delays/failures nếu recovery point gần nhất không sẵn sàng.

### Bài 37 — Service-ready

Vì sao RTO không kết thúc ngay khi database accept connection?

**Gợi ý:** Còn validation, application startup, routing và smoke tests.

### Bài 38 — Ransomware

Nếu attacker có quyền xóa primary và backup bucket, lớp bảo vệ nào cần xem?

**Gợi ý:** Immutable/offline copy, separate account/identity, key recovery.

### Bài 39 — Business approval

Ai nên phê duyệt RPO/RTO?

**Gợi ý:** Business/service owner với input từ engineering/operations/risk.

### Bài 40 — Thiết kế tổng hợp

Một PostgreSQL database 3 TB, write rate cao, yêu cầu RPO 5 phút, RTO 30 phút, cần chống mất region và xóa nhầm dữ liệu. Đề xuất các lớp bảo vệ và cách chứng minh.

**Gợi ý:** Physical base backups, continuous WAL archive offsite với lag alert, standby phù hợp để giảm RTO, immutable backup copy, IAM/key separation, PITR runbook và isolated restore, cross-region capacity, business validation, restore drills đo RPO/RTO và reconciliation cho external events.

## 43. Checklist xác định và phê duyệt RPO/RTO

### 43.1. Yêu cầu nghiệp vụ

- [ ] Service/database owner đã xác định?
- [ ] Đã mô tả business impact khi mất dữ liệu/downtime?
- [ ] RPO có con số và failure model rõ?
- [ ] RTO có định nghĩa service-ready rõ?
- [ ] MTD/MAO và WRT có được xem xét?
- [ ] External dependencies đã được liệt kê?
- [ ] Người có thẩm quyền đã phê duyệt?

### 43.2. Chiến lược backup/HA/DR

- [ ] Logical/physical strategy phù hợp database size?
- [ ] Base backup và WAL archive đủ cho PITR nếu cần?
- [ ] Replication mode đáp ứng durability/RPO theo failure mode?
- [ ] Standby capacity đáp ứng RTO?
- [ ] Có offsite/cross-region copy?
- [ ] Có immutable/offline copy theo threat model?
- [ ] Backup catalog và configuration được bảo vệ?
- [ ] Retention giữ đủ base/WAL chain?

### 43.3. Bảo mật và khả năng truy cập

- [ ] Encryption at rest/in transit?
- [ ] Key recovery được thử?
- [ ] IAM backup/restore/delete tách biệt?
- [ ] Immutable retention policy không bị primary identity xóa?
- [ ] Audit logs được lưu?
- [ ] Disaster recovery identity có thể truy cập artifacts?

### 43.4. RTO và capacity

- [ ] Restore throughput được đo?
- [ ] Network/storage/compute capacity đủ?
- [ ] Provisioning có automation?
- [ ] WAL replay/index build/validation time đã tính?
- [ ] DNS, secrets, TLS, extensions và app dependencies sẵn sàng?
- [ ] Connection pools và cutover procedure đã thử?

### 43.5. Diễn tập

- [ ] Logical restore drill?
- [ ] Physical restore/PITR drill?
- [ ] Failover/standby drill?
- [ ] Cross-region restore?
- [ ] Immutable/ransomware recovery exercise?
- [ ] Đã ghi RPO/RTO thực tế và action items?
- [ ] Diễn tập lại sau thay đổi lớn?

## 44. Bảng tra cứu nhanh

| Khái niệm | Ý nghĩa |
|---|---|
| RPO | Mức mất dữ liệu theo thời gian tối đa chấp nhận |
| RTO | Thời gian tối đa để service trở lại trạng thái xác định |
| MTD/MAO | Downtime tối đa business chịu được |
| WRT | Thời gian xử lý công việc tồn đọng sau restore |
| Availability | Mức độ dịch vụ sẵn sàng trong khoảng đo |
| Logical dump | Schema/data ở mức SQL |
| Physical backup | Bản sao cluster ở mức file/page |
| Base backup | Baseline vật lý để recovery |
| WAL archive | Chuỗi WAL lưu để replay |
| PITR | Phục hồi tới recovery target |
| Async replication | Primary không chờ standby acknowledgement đầy đủ trước commit response theo cấu hình |
| Sync replication | Commit có thể chờ standby acknowledgement theo mode |
| Standby | Server nhận/replay WAL để HA/DR/read-only |
| HA | Duy trì continuity khi một số lỗi xảy ra |
| DR | Khôi phục sau thảm họa vượt phạm vi HA |
| Offsite | Bản sao ở miền/địa điểm độc lập |
| Immutable | Bản sao không thể bị sửa/xóa trong retention policy |
| 3-2-1-1-0 | Nguyên tắc nhiều bản sao, miền lưu trữ, offsite, immutable, verify |
| Restore drill | Diễn tập khôi phục thực tế |
| Recovery point | Trạng thái dữ liệu có thể phục hồi |
| Archive lag | Độ trễ WAL được lưu ở nơi archive |
| Replay lag | Độ trễ standby apply WAL |
| Backup catalog | Metadata và dependencies của backup |
| Recovery tier | Mức ưu tiên phục hồi service |
| Cutover | Chuyển traffic sang môi trường đã phục hồi |

## 45. Kết luận

**RPO và RTO là hai yêu cầu khác nhau nhưng phải được thiết kế cùng nhau.** RPO giới hạn lượng dữ liệu có thể mất; RTO giới hạn thời gian dịch vụ được phép gián đoạn. Một hệ thống có backup hằng ngày có thể có RPO gần 24 giờ; một hệ thống có standby có thể phục hồi nhanh hơn nhưng vẫn không bảo vệ khỏi thao tác sai được replay. Không có một công cụ đơn lẻ nào giải quyết tất cả failure modes.

Với PostgreSQL, logical dump phù hợp cho migration và phục hồi objects/data ở snapshot; physical base backup kết hợp WAL archive hỗ trợ phục hồi cluster và PITR; replication/standby giúp giảm RTO cho các sự cố phù hợp; offsite và immutable copies bảo vệ trước mất region hoặc xóa phá hoại. Retention, encryption keys, IAM, extension/configuration dependencies và external systems đều phải nằm trong kế hoạch.

**RPO/RTO chỉ có giá trị khi được đo bằng recovery drills.** Hãy tính từ recovery point thực sự truy cập được và thời điểm service-ready, bao gồm detect, decision, provision, retrieve, restore, replay, validation và cutover. Ghi nhận kết quả, so với mục tiêu, sửa bottlenecks và diễn tập lại sau những thay đổi lớn.

Nguyên tắc cuối cùng: **xác định failure modes và business impact trước, chọn các lớp backup/HA/DR để đạt RPO/RTO, bảo vệ artifacts và keys độc lập, rồi chứng minh bằng restore test rằng dữ liệu và dịch vụ có thể quay lại đúng thời gian đã cam kết.**


## 27. RPO calculation với snapshot-only strategy

Nếu chỉ có snapshot backups, khoảng cách giữa các recovery points là yếu tố lớn quyết định RPO tối đa có thể xảy ra.

### 27.1. Backup mỗi 24 giờ

Nếu chỉ có daily backup và sự cố xảy ra ngay trước lần kế tiếp, có thể mất gần 24 giờ dữ liệu. RPO worst-case xấp xỉ chu kỳ backup, chưa tính job failure hoặc upload lag.

### 27.2. Backup mỗi giờ

Về lý thuyết, khoảng cách recovery points giảm còn gần một giờ, nhưng job phải hoàn tất, file phải bền vững và restore phải khả dụng.

### 27.3. Job bắt đầu không phải recovery point

Backup job đang chạy hoặc file mới tạo một phần không phải recovery point hợp lệ.

### 27.4. Upload xong mới có thể truy cập ở DR

Nếu file chỉ nằm trong primary region, nó có thể không còn khả dụng sau mất region. Cần xác định thời điểm bản sao remote đã bền vững và có thể đọc.

### 27.5. Tính worst-case, không chỉ ngày thuận lợi

Với snapshots mỗi 6 giờ, worst-case RPO có thể gần 6 giờ, cộng job delay/failure và thời gian remote copy nếu recovery point chưa sẵn sàng. Nếu một job thất bại mà không được phát hiện, khoảng cách có thể tăng gấp đôi hoặc hơn.

## 28. RPO với WAL archive và replication

Với physical base backup và WAL archive, recovery point có thể nằm gần thời điểm sự cố nếu WAL cuối đã được lưu bền vững và chain đầy đủ.

### 28.1. Đo archive delay

Có thể quan sát trạng thái archiver qua view phù hợp:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Các cột và hành vi phụ thuộc phiên bản. View này là một tín hiệu; để tính RPO chính xác cần biết WAL segment nào đã được remote storage xác nhận bền vững.

### 28.2. Archive command thành công là gì?

Cơ chế archive phải chỉ báo success sau khi WAL segment được lưu đầy đủ theo durability policy. Nếu script chỉ copy vào local temp rồi trả success trước remote upload, server có thể coi segment đã archive dù DR copy chưa sẵn sàng.

### 28.3. WAL segment chưa đầy có thể chưa archive

WAL archiving thường xử lý segments theo cơ chế segment completion/timeout; `archive_timeout` có thể giúp tạo archive segments thường xuyên hơn trong workload thấp, nhưng không thay durability confirmation.

### 28.4. RPO theo remote durability

Nếu remote object storage xác nhận một WAL segment sau 4 phút và sự cố xảy ra ngay trước segment kế tiếp được archive, RPO có thể lớn hơn 4 phút tùy write pattern, WAL generation và archive behavior. Phải đo trên timeline thật.

### 28.5. Replication lag đo nhiều giai đoạn

Write, flush và replay LSN khác nhau. Một transaction được standby nhận nhưng chưa replay không có nghĩa read queries trên standby đã nhìn thấy nó; promotion/recovery behavior cần hiểu theo replication mode.

## 29. RTO calculation: chia nhỏ các giai đoạn

Một RTO end-to-end có thể được mô hình hóa:

~~~text
T_RTO =
  T_detect
+ T_decide
+ T_provision
+ T_retrieve
+ T_restore
+ T_replay
+ T_validate
+ T_cutover
~~~

Không phải mọi bước đều tuần tự. Một số có thể song song, nhưng chỉ tính song song khi runbook và tooling thực sự hỗ trợ.

### 29.1. T_detect

Thời gian từ khi sự cố bắt đầu tới khi monitoring/on-call nhận biết.

### 29.2. T_decide

Thời gian xác định scope, failure mode, recovery point và người có quyền phê duyệt.

### 29.3. T_provision

Tạo compute, storage, network, security groups, DNS và database runtime.

### 29.4. T_retrieve

Tải backup, WAL, config và dependencies từ nơi lưu trữ. Cold storage retrieval có thể kéo dài.

### 29.5. T_restore và T_replay

Logical restore, physical restore và WAL replay có bottlenecks khác nhau. Đo riêng từng bước.

### 29.6. T_validate và T_cutover

Chạy integrity/business checks, mở kết nối ứng dụng, chuyển traffic và xác nhận health. Không cắt phần này chỉ để báo RTO thấp hơn.

## 30. DR runbook: từ sự cố tới phục hồi

Một runbook có thể chia thành các giai đoạn:

### Giai đoạn A — Detect và declare

- Xác nhận sự cố thật và phạm vi ảnh hưởng.
- Xác định primary còn an toàn để ghi hay cần fence.
- Chỉ định incident commander và technical recovery lead.
- Ghi thời điểm bắt đầu, timezone và failure mode.
- Thông báo các bên liên quan theo incident policy.

### Giai đoạn B — Chọn recovery point

- Đối chiếu RPO đã phê duyệt.
- Xác định backup ID/base backup phù hợp.
- Kiểm tra WAL chain/timeline nếu PITR.
- Chọn target trước logical corruption nếu cần.
- Xác nhận remote copies, encryption keys và catalog truy cập được.

### Giai đoạn C — Dựng môi trường

- Provision PostgreSQL version tương thích.
- Chuẩn bị data directory/tablespaces và permissions.
- Cài extension binaries và cấu hình.
- Cô lập network để tránh ứng dụng ghi vào cluster chưa được xác nhận.
- Tải/giải mã backup và WAL.

### Giai đoạn D — Restore và recover

- Logical: tạo database đích, restore globals/objects/data theo runbook.
- Physical: restore base backup, cấu hình WAL retrieval và recovery target.
- Kiểm tra errors, logs, progress và resource usage.
- Không promote/cutover khi chưa xác định recovery target và trạng thái cluster.

### Giai đoạn E — Validate

- Kiểm tra schema, constraints, indexes và sequences.
- Kiểm tra row counts, business invariants và các aggregate quan trọng.
- Kiểm tra roles, ownership, grants, RLS và extensions.
- Chạy smoke tests read/write trong môi trường cô lập.
- Xác nhận external dependencies và integration state.

### Giai đoạn F — Cutover

- Fence/disable old primary nếu cần để tránh split-brain.
- Cập nhật DNS/service discovery/endpoints.
- Refresh connection pools và credentials.
- Mở traffic theo từng bước, theo dõi error rate và replication.
- Ghi lại recovered point và dữ liệu có thể bị mất theo RPO.

### Giai đoạn G — Rebuild protection

- Thiết lập lại backup schedule và WAL archiving.
- Recreate standby/replication slots theo runbook.
- Kiểm tra archive retention và offsite copy.
- Theo dõi cho tới khi HA/backup protection trở lại mức yêu cầu.
- Thực hiện post-incident review và cập nhật runbook.

## 31. Recovery point selection và logical errors

Khi lỗi là một thao tác hợp lệ về SQL nhưng sai nghiệp vụ (ví dụ DELETE nhầm), recovery point cần nằm trước commit gây lỗi.

### 31.1. Xác định thời điểm sai

Dùng audit log, application logs, transaction/event metadata và người vận hành để khoanh vùng thời điểm. Đồng bộ clock là điều kiện quan trọng.

### 31.2. Dựng bản phục hồi song song

Restore PITR vào cluster cô lập, không rollback toàn bộ production ngay nếu production vẫn nhận giao dịch hợp lệ sau lỗi.

### 31.3. Trích phần cần cứu

Copy bảng/rows/relations cần thiết, kiểm tra foreign keys và các giao dịch phát sinh sau recovery point.

### 31.4. Reconcile với hiện tại

Cần quy tắc xử lý conflict: row nào đã được sửa hợp lệ sau lỗi, transaction nào đã phát message, payment nào đã được xử lý bên ngoài.

### 31.5. Không mở hai primary cùng ghi

Cluster PITR phụ phải được fence/cô lập cho tới khi hoàn tất extraction hoặc có một kế hoạch cutover rõ.

## 32. RPO/RTO cho nhiều database và dịch vụ liên quan

Một ứng dụng có thể dùng nhiều PostgreSQL databases, queue, object storage, cache và payment services.

### 32.1. Snapshot một database không phải snapshot toàn hệ thống

Hai databases có thể có logical dumps tại các thời điểm khác nhau. Nếu transaction nghiệp vụ trải qua cả hai, restored state có thể không đồng nhất.

### 32.2. External systems cần recovery policy riêng

Message broker, object storage, search index và payment provider có backup/retention/consistency model khác PostgreSQL.

### 32.3. Transactional outbox và idempotency

Các pattern như transactional outbox giúp liên kết database commit với event publishing theo cách có thể retry/reconcile. Chúng không tự tạo distributed snapshot nhưng hỗ trợ recovery semantics.

### 32.4. Recovery ordering

Runbook cần biết service nào khôi phục trước, queue nào pause, consumer nào replay, và cách tránh xử lý trùng events.

### 32.5. Một RPO chung có thể gây hiểu nhầm

Định nghĩa RPO cho database, event log và external financial state; sau đó xác định business consistency objective cho toàn workflow.

## 33. Cost model: RPO/RTO càng nghiêm ngặt, chi phí càng cao

Chi phí backup/DR gồm nhiều phần:

- Storage của full/incremental backups và WAL.
- Cross-region replication/egress/network.
- Standby compute và storage luôn chạy.
- Immutable retention và backup vault.
- Encryption/KMS và identity administration.
- Monitoring, catalog và orchestration.
- Nhân lực trực, diễn tập và post-incident recovery.
- Dung lượng dự phòng cho restore/rebuild.

### 33.1. Storage cost

Retention dài và nhiều copies làm storage tăng. Compression/deduplication có thể giảm cost nhưng thêm CPU hoặc dependency.

### 33.2. Standby cost

Hot standby có thể tốn compute gần bằng primary. Warm/pilot-light giảm chi phí nhưng tăng provisioning time/RTO.

### 33.3. Network cost

Cross-region WAL/backup replication có thể tạo egress và bandwidth costs. Cần đo write volume và peak bursts.

### 33.4. Operational cost

Một kiến trúc nhiều công cụ backup có thể giảm RTO nhưng tăng complexity. Nếu không ai có thể vận hành khi incident, thiết kế không đạt mục tiêu.

### 33.5. Business impact cost

So sánh chi phí bảo vệ với tổn thất kỳ vọng khi downtime/mất dữ liệu. RPO/RTO là quyết định đầu tư, không chỉ setting kỹ thuật.

## 34. Recovery tiers và ưu tiên phục hồi

Khi disaster ảnh hưởng nhiều hệ thống, không thể phục hồi tất cả cùng lúc. Cần thứ tự ưu tiên.

| Tier | Mục tiêu | Ví dụ minh họa |
|---|---|---|
| Tier 0 | Nền tảng cần cho recovery | Identity, network, key vault, DNS |
| Tier 1 | Dịch vụ giao dịch thiết yếu | Payment/order ledger |
| Tier 2 | Dịch vụ vận hành phụ thuộc | Inventory, customer workflow |
| Tier 3 | Báo cáo và analytics | Warehouse, dashboards |
| Tier 4 | Dữ liệu có thể tái tạo | Cache, derived indexes |

### 34.1. Dependencies quyết định thứ tự

Không thể khôi phục application database nếu key management, network hoặc identity provider chưa sẵn sàng.

### 34.2. Recovery capacity phải chia sẻ

Nhiều databases cùng restore có thể cạnh tranh disk/network. Runbook phải xác định parallelism và thứ tự.

### 34.3. Tier thấp vẫn có RPO/RTO

Một hệ thống analytics có thể chấp nhận RPO 24 giờ/RTO 1 ngày, nhưng phải ghi rõ thay vì mặc định không cần backup.

### 34.4. Business owner phê duyệt thứ tự

Thứ tự phục hồi có thể khác theo thời điểm, mùa cao điểm hoặc regulatory obligations. Cần diễn tập cùng các team liên quan.

### 34.5. Recovery tiers phải được kiểm tra

Không chỉ có tài liệu: phải thử dựng identity/network, key access và database theo đúng thứ tự.

