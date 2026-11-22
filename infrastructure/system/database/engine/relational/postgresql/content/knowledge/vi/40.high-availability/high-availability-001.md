# Phân biệt sao chép, sao lưu và tính sẵn sàng cao trong PostgreSQL

Sao chép (replication), sao lưu (backup) và tính sẵn sàng cao (High Availability - HA) đều giúp hệ thống PostgreSQL tiếp tục hoạt động hoặc phục hồi khi có sự cố, nhưng chúng giải quyết những vấn đề khác nhau.

- **Replication** duy trì một hoặc nhiều bản sao dữ liệu bằng cách truyền các thay đổi từ nguồn sang node khác. Nó giúp có bản sao cập nhật để đọc, chuyển vai trò hoặc phục hồi node.
- **Backup** tạo bản lưu có thể dùng để khôi phục dữ liệu về trạng thái trước đó. Backup cần được giữ độc lập với lỗi đang xảy ra và phải được kiểm tra bằng restore.
- **High Availability** là kiến trúc và quy trình giúp dịch vụ tiếp tục phục vụ khi một thành phần gặp lỗi. HA bao gồm replication trong nhiều thiết kế, nhưng còn cần phát hiện lỗi, quyết định failover, fencing, chuyển traffic, kiểm tra sau chuyển đổi và quy trình vận hành.

Một standby được replicate liên tục có thể nhận cả lệnh DELETE nhầm từ primary. Vì vậy replication không thay thế backup. Một bản backup tốt có thể khôi phục dữ liệu sau lỗi logic nhưng cần thời gian restore, nên backup một mình không bảo đảm dịch vụ tiếp tục trong vài giây. Một cụm HA có thể chuyển sang standby nhanh, nhưng nếu tất cả bản sao và backup cùng nằm trong một failure domain thì một sự cố vùng hoặc thao tác phá hủy có thể làm mất tất cả.

```text
Replication:
Primary -- WAL / logical changes --> Replica
              |                       |
              +---- giữ bản sao cập nhật
                    cho đọc / failover

Backup:
Database -- base backup / dump / snapshot --> Backup repository
                                                |
                                                +--> restore / PITR

High Availability:
Health checks --> Failure decision --> Fence old primary
                                      --> Promote standby
                                      --> Route clients
                                      --> Verify service

Phòng thủ nhiều lớp:
Replication + HA + Backup + Restore drills
```

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Tính sẵn sàng cao**, với đề tài **“Phân biệt sao chép, sao lưu và tính sẵn sàng cao”**. Trọng tâm là hiểu mục tiêu, giới hạn và cách phối hợp ba cơ chế trong một thiết kế PostgreSQL có thể vận hành và phục hồi được.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt replication, backup, durability, recoverability và high availability.
2. Giải thích vì sao replication không phải backup.
3. Giải thích vì sao backup không tự tạo HA.
4. Nhận biết HA là một kiến trúc gồm công nghệ, quy trình và vận hành.
5. Phân biệt physical replication và logical replication.
6. Phân biệt asynchronous và synchronous replication.
7. Hiểu vai trò của WAL, WAL sender, WAL receiver và standby replay.
8. Giải thích cách lỗi logic được truyền qua replicas.
9. Phân biệt base backup, logical dump, storage snapshot và WAL archive.
10. Mô tả Point-in-Time Recovery (PITR).
11. Định nghĩa Recovery Point Objective (RPO) và Recovery Time Objective (RTO).
12. Phân biệt failover và switchover.
13. Giải thích failure detection, leader election, quorum và fencing.
14. Nhận biết split brain và cách ngăn hai primary cùng nhận ghi.
15. Hiểu vai trò của load balancer, DNS, virtual IP và connection pool khi chuyển primary.
16. Thiết kế replication topology cho một primary và nhiều standby.
17. Phân biệt HA trong một vùng với disaster recovery liên vùng.
18. Thiết kế backup repository độc lập, có retention và khả năng chống xóa.
19. Lập lịch backup/WAL archive theo RPO và RTO.
20. Xác định failure domains của database, storage, network, control plane và con người.
21. Thiết kế monitoring cho replication lag, backup freshness, archive health và failover.
22. Xây dựng runbook failover, restore, PITR và disaster recovery.
23. Kiểm thử backup bằng restore drills và đo thời gian thực tế.
24. Đánh giá trade-off giữa durability, availability, latency, chi phí và độ phức tạp.

**Phạm vi:** PostgreSQL hiện đại, bao gồm physical streaming replication, logical replication, base backup, WAL archiving và các khái niệm HA. Chi tiết tham số/cột statistics view có thể thay đổi theo major version và nền tảng triển khai. Ví dụ cấu hình trong bài là mẫu học tập, cần điều chỉnh theo topology, security policy và phiên bản thực tế.

---

## 2. Bốn khái niệm nền tảng cần tách biệt

### 2.1. Availability - tính sẵn sàng

Availability trả lời câu hỏi: **người dùng có thể sử dụng dịch vụ khi một thành phần gặp lỗi hay không?**

Một hệ thống có HA thường có node dự phòng, cơ chế phát hiện lỗi và cách chuyển traffic. Mục tiêu là giảm thời gian dịch vụ không hoạt động.

### 2.2. Durability - tính bền vững

Durability trả lời câu hỏi: **một transaction đã được xác nhận commit có còn tồn tại sau sự cố hay không?**

Trong PostgreSQL, WAL flush, fsync, synchronous_commit và storage semantics ảnh hưởng durability. Synchronous replication có thể bổ sung bảo vệ trước mất primary nếu commit được xác nhận sau khi standby phù hợp đã flush WAL.

### 2.3. Recoverability - khả năng khôi phục

Recoverability trả lời câu hỏi: **có thể khôi phục dữ liệu về trạng thái đúng sau lỗi hoặc mất dữ liệu hay không?**

Base backup, WAL archive, PITR, backup retention và restore testing là những thành phần quan trọng.

### 2.4. Replication - duy trì bản sao

Replication trả lời câu hỏi: **làm thế nào để một node khác nhận được các thay đổi từ nguồn?**

Replication có thể hỗ trợ availability, read scaling, migration và data distribution. Nhưng một bản sao liên tục cập nhật không nhất thiết lưu lại lịch sử trước lỗi.

### 2.5. Các mục tiêu liên quan nhưng không đồng nhất

| Khái niệm | Câu hỏi chính | Cơ chế thường dùng |
| --- | --- | --- |
| Availability | Dịch vụ còn truy cập được không? | HA manager, standby, failover, routing |
| Durability | Commit đã xác nhận có bền vững không? | WAL flush, fsync, synchronous replication |
| Recoverability | Có thể khôi phục dữ liệu đúng không? | Backup, WAL archive, PITR |
| Replication | Node khác có bản sao cập nhật không? | Physical/logical replication |
| Consistency | Các quan sát dữ liệu có tuân theo quy tắc không? | Transaction isolation, replication semantics, application design |

Một thiết kế tốt phải xác định rõ từng mục tiêu. Không dùng một chỉ số như replication lag để tuyên bố toàn hệ thống có backup tốt hoặc HA tốt.

---

## 3. Replication trong PostgreSQL

Replication duy trì bản sao của dữ liệu trên node hoặc hệ thống khác. PostgreSQL có các cơ chế replication với mục tiêu và semantics khác nhau.

### 3.1. Physical streaming replication

Physical standby nhận WAL từ primary và replay các thay đổi ở mức vật lý. Standby có cấu trúc database tương ứng với primary và thường ở chế độ read-only khi đang recovery.

Luồng khái niệm:

```text
Application
    |
    v
Primary PostgreSQL
    |
    +--> WAL records
            |
            v
        WAL sender
            |
            v
        Network
            |
            v
        WAL receiver
            |
            v
        Standby pg_wal
            |
            v
        Startup / replay
            |
            v
        Standby data pages
```

Physical replication thường được dùng cho HA và read replicas vì standby có thể được promote thành primary khi đủ điều kiện.

### 3.2. Logical replication

Logical replication chuyển các thay đổi logic của selected tables/publications tới subscriber. Nó phù hợp cho một số trường hợp phân phối dữ liệu, đồng bộ tập con tables hoặc migration giữa các hệ thống tương thích.

Logical replication không tương đương physical standby:
- Có thể chọn objects được publish.
- Schema và indexes cần được quản lý theo quy trình.
- Không tự sao chép mọi đối tượng cluster như roles và tablespaces theo cùng cách physical backup.
- Sequence state và một số DDL cần được xử lý riêng.
- Subscriber có thể có layout khác source.

### 3.3. Replication không phải versioned backup

Standby thường phản ánh trạng thái mới nhất mà nó replay. Nếu primary bị xóa nhầm dữ liệu, thay đổi đó cũng được replicate. Nếu ứng dụng ghi dữ liệu sai, replica thường cũng nhận dữ liệu sai.

### 3.4. Replication không giữ lịch sử vô hạn

WAL được giữ theo retention needs, checkpoint/recycling, archive và replication slots. Một standby offline lâu có thể không còn lấy được WAL từ primary.

### 3.5. Replication có thể phục vụ nhiều mục tiêu

- HA: promote standby khi primary mất.
- Read scaling: chuyển một số read-only queries sang replicas.
- Disaster recovery: giữ bản sao ở site khác.
- Migration: chuyển dữ liệu tới cluster mới.
- Analytics: đồng bộ dữ liệu tới hệ thống đọc riêng.

Một replica chỉ phục vụ tốt mục tiêu đã được thiết kế và kiểm thử. Read replica không tự động là DR site nếu nó cùng failure domain với primary.

---

## 4. Asynchronous và synchronous replication

### 4.1. Asynchronous replication

Primary không phải chờ standby xác nhận WAL trước khi trả COMMIT. Điều này giúp giảm commit latency và không buộc transaction chờ mạng/standby.

Đổi lại, primary có thể xác nhận một transaction mà standby chưa nhận hoặc chưa flush WAL. Nếu primary mất đột ngột và standby được promote, một số commit gần nhất có thể không có trên standby.

### 4.2. Synchronous replication

Với synchronous replication, primary chờ một hoặc nhiều standby xác nhận theo policy trước khi trả COMMIT. Mức chờ phụ thuộc synchronous_commit và synchronous_standby_names.

Các mức thường gặp của synchronous_commit:

| Giá trị | Ý nghĩa khái quát |
| --- | --- |
| off | Không đợi local WAL flush cho từng commit |
| local | Đợi local WAL flush, không đợi standby |
| on | Đợi local flush và remote acknowledgement theo sync policy |
| remote_write | Đợi standby ghi WAL tới OS |
| remote_flush | Đợi standby flush WAL |
| remote_apply | Đợi standby replay WAL |

Cần đọc tài liệu major version và cấu hình thực tế để hiểu chính xác semantics của sync standbys và quorum.

### 4.3. Synchronous replication không phải backup

Nếu một transaction DELETE nhầm được commit và xác nhận đồng bộ, standby cũng nhận DELETE. Synchronous replication có thể bảo vệ commit khỏi mất primary, nhưng không cung cấp lịch sử trước thao tác sai.

### 4.4. Availability trade-off

Nếu primary không thể liên lạc với synchronous standby cần thiết, commit có thể bị chờ. Đây là trade-off giữa durability và khả năng tiếp tục ghi khi mất node/network.

### 4.5. Quorum synchronous replication

PostgreSQL có thể cấu hình synchronous_standby_names theo FIRST/ANY và số standby cần xác nhận. Quorum giúp chọn một tập node phù hợp, nhưng thiết kế phải tính failure domains và node được phép promote.

### 4.6. Không mặc định synchronous = RPO bằng 0

RPO phụ thuộc node nào được chọn khi failover, standby đã xác nhận theo semantics nào, storage có flush đúng không, fencing và HA orchestration có hoạt động đúng không. Phải kiểm thử failure scenarios.

---

## 5. Backup là gì?

Backup là bản lưu dữ liệu được giữ để phục hồi sau lỗi. Một backup tốt có thể được khôi phục ngay cả khi primary và replicas bị mất hoặc dữ liệu bị thay đổi sai.

### 5.1. Mục đích

- Khôi phục sau lỗi logic hoặc thao tác nhầm.
- Khôi phục sau mất storage hoặc data directory.
- Khôi phục sau ransomware/xóa nhầm khi bản backup còn độc lập.
- Khôi phục về một thời điểm trước khi dữ liệu bị hỏng.
- Dựng lại standby hoặc cluster mới.
- Hỗ trợ kiểm toán và retention theo yêu cầu.

### 5.2. Backup không nhất thiết giữ dịch vụ hoạt động

Restore có thể mất nhiều phút hoặc nhiều giờ. Backup đảm bảo khả năng phục hồi dữ liệu theo quy trình, không tự chuyển traffic sang node khác.

### 5.3. Backup phải độc lập với nguồn

Nếu backup chỉ nằm trên cùng disk, cùng storage account hoặc cùng quyền xóa với primary, một sự cố lớn có thể xóa cả hai.

### 5.4. Backup cần được kiểm thử

File backup tồn tại không chứng minh nó restore được. Phải kiểm tra integrity, WAL continuity, startup và dữ liệu ứng dụng sau restore.

---

## 6. Các loại backup thường dùng với PostgreSQL

### 6.1. Physical base backup

Base backup là bản sao vật lý nhất quán của PostgreSQL cluster. Có thể tạo bằng pg_basebackup hoặc công cụ backup tương thích.

Đặc điểm:
- Sao chép data files và metadata cần thiết.
- Phù hợp cho physical restore và PITR.
- Phải kết hợp WAL cần thiết để hoàn tất consistency và replay tới target.
- Phải tương thích major version/format và các điều kiện platform.

Ví dụ:

```bash
pg_basebackup \
  -h db-primary \
  -U backup_user \
  -D /backup/base-2026-11-14 \
  -X stream \
  -P
```

Đây là ví dụ minh họa. Chọn quyền, slot, compression, tablespace mapping, WAL method và destination theo chính sách backup.

### 6.2. Logical backup bằng pg_dump

pg_dump tạo logical dump của một database, thường ở custom hoặc directory format. pg_dumpall có thể xuất thêm global objects theo cách phù hợp.

Ví dụ:

```bash
pg_dump -Fc -d appdb -f appdb.dump
pg_restore -d appdb_restore appdb.dump
```

Logical backup hữu ích cho:
- Khôi phục một database hoặc objects.
- Chuyển dữ liệu giữa một số phiên bản tương thích.
- Di chuyển schema/data.
- Phục hồi chọn lọc.

Logical dump không phải physical backup của toàn bộ cluster và không thay thế continuous WAL archive cho PITR vật lý.

### 6.3. Storage snapshots

Snapshot của volume/block storage có thể hỗ trợ backup nhanh, nhưng phải được phối hợp để bảo đảm tính nhất quán PostgreSQL. Cần hiểu crash-consistent, filesystem-consistent và application-consistent snapshots.

Một snapshot tùy tiện khi database đang ghi có thể không tương đương một base backup hợp lệ nếu không có cơ chế phối hợp phù hợp.

### 6.4. Continuous WAL archiving

WAL archive giữ các segments đã hoàn tất ở repository riêng. Khi kết hợp với base backup, nó hỗ trợ PITR và phục hồi tới thời điểm/LSN phù hợp.

### 6.5. Backup vật lý và logical có mục tiêu khác nhau

| Tiêu chí | Physical base backup | Logical dump |
| --- | --- | --- |
| Phạm vi | Cluster/database files vật lý theo công cụ | Database/objects được dump |
| Restore | Phục hồi data directory/cluster | Tạo objects và nạp SQL/data |
| PITR vật lý liên tục | Kết hợp WAL archive | Không thay thế physical WAL PITR |
| Chọn lọc objects | Hạn chế hơn | Linh hoạt hơn |
| Tốc độ restore | Thường nhanh với cluster lớn nếu storage tốt | Có thể lâu do recreate/load/index |
| Dùng dựng physical standby | Phù hợp | Không trực tiếp |
| Khác major version | Cần tương thích physical format | Có thể hỗ trợ migration tùy version/features |

---

## 7. Base backup và WAL archive tạo nên PITR

PITR (Point-in-Time Recovery) cho phép khôi phục database tới một thời điểm trước khi sự cố xảy ra.

```text
Base backup tại T0
       |
       v
Restore data directory
       |
       v
Replay WAL archive liên tục
       |
       +---- WAL transaction 1
       +---- WAL transaction 2
       +---- WAL transaction 3
       |
       v
Dừng tại recovery target T1
       |
       v
Kiểm tra dữ liệu
       |
       v
Promote nếu cần tiếp tục nhận ghi
```

### 7.1. Vì sao cần base backup?

WAL mô tả thay đổi từ một trạng thái database đã có. Nó không thay thế một bản nền đầy đủ để dựng cluster từ đầu.

### 7.2. Vì sao cần WAL liên tục?

Nếu thiếu một segment bắt buộc trên đường từ base backup tới recovery target, PostgreSQL có thể không replay tiếp được.

### 7.3. Recovery target

Có thể chọn target theo thời gian, LSN, transaction ID hoặc named restore point, tùy phiên bản và cấu hình.

### 7.4. PITR không phải failover nhanh

PITR cần restore base backup và replay WAL. Nó thường chậm hơn promote một standby đã sẵn sàng, nhưng cho phép quay về trước lỗi logic.

### 7.5. Sau PITR và promotion

Khi bản restore được promote và nhận ghi mới, PostgreSQL tạo timeline mới. Archive policy phải giữ timeline history và WAL của nhánh mới.

---

## 8. Vì sao replication không thay thế backup?

Đây là khác biệt quan trọng nhất cần ghi nhớ.

### 8.1. Lỗi logic được replicate

Ví dụ:

```sql
DELETE FROM orders;
COMMIT;
```

Nếu câu lệnh chạy trên primary, WAL mô tả thay đổi sẽ được gửi tới physical standby. Standby replay thay đổi và cũng mất các rows đó.

### 8.2. DROP TABLE cũng được replicate

Replication duy trì thay đổi của database, bao gồm nhiều thao tác phá hủy dữ liệu được commit hợp lệ. Nó không biết người dùng có định chạy lệnh đó hay không.

### 8.3. Ransomware hoặc credential compromise

Nếu kẻ tấn công có quyền ghi database hoặc xóa backup qua cùng credentials, thay đổi có thể lan sang replicas và backup repository nếu hệ thống không tách quyền/failure domain.

### 8.4. Corruption có thể lan theo WAL

Một số lỗi logic hoặc thay đổi sai có thể được replicate. Corruption vật lý không phải lúc nào cũng lan giống nhau, nhưng không được coi replica là bản backup đã kiểm chứng.

### 8.5. Replica không giữ lịch sử trước lỗi

Nếu không có delayed standby, WAL archive và backup, replica thường không có cách tự quay lại trước transaction lỗi.

### 8.6. Delayed standby chỉ là lớp hỗ trợ

Một standby cố ý trì hoãn replay có thể tạo khoảng thời gian để phát hiện lỗi logic, nhưng vẫn không thay backup độc lập. Nó có thể bị mất cùng site, storage hoặc credentials.

---

## 9. Vì sao backup không thay thế replication?

Backup bảo vệ dữ liệu có thể phục hồi, nhưng không tự tạo một node online sẵn sàng nhận traffic.

### 9.1. Restore cần thời gian

Restore base backup, replay WAL, khởi động PostgreSQL, kiểm tra dữ liệu và chuyển ứng dụng có thể vượt RTO nếu hệ thống cần phục vụ gần như liên tục.

### 9.2. Backup thường không phục vụ read traffic

Backup file không phải một PostgreSQL server đang chạy. Muốn phục vụ query cần restore thành cluster và kiểm tra.

### 9.3. Backup có thể cũ hơn primary

Nếu backup gần nhất cách hiện tại vài giờ, restore chỉ tới điểm đó nếu không có WAL archive liên tục. Replication có thể cung cấp bản sao gần hiện tại hơn.

### 9.4. Backup và replication bổ sung cho nhau

Replication giúp có node sẵn sàng; backup giúp quay lại một trạng thái lịch sử và phục hồi khi replicas cũng bị ảnh hưởng.

---

## 10. High Availability là gì?

HA là thiết kế hệ thống để giảm downtime khi một hoặc nhiều thành phần gặp sự cố.

HA không chỉ là bật streaming replication. Một kiến trúc HA cần:

- Redundant database nodes.
- Failure detection.
- Quy tắc xác định node được quyền làm primary.
- Fencing node cũ.
- Promotion/leader transition.
- Chuyển traffic và cập nhật endpoint.
- Kiểm tra sau failover.
- Rejoin/rebuild các replicas.
- Monitoring, alerting và runbook.
- Backup và DR để xử lý sự cố vượt khả năng HA.

### 10.1. HA là end-to-end

Database có thể promote thành công nhưng ứng dụng vẫn downtime nếu connection pool giữ kết nối cũ, DNS chưa cập nhật, secrets không truy cập được hoặc load balancer không chuyển endpoint.

### 10.2. HA có thể tự động hoặc thủ công

HA manager có thể tự phát hiện và promote. Một hệ thống khác có thể yêu cầu operator phê duyệt failover. Tự động không luôn tốt hơn; cần đánh giá nguy cơ false positive và split brain.

### 10.3. HA không đảm bảo không mất dữ liệu

Nếu replication asynchronous, standby có thể thiếu WAL mới nhất. HA thường giảm downtime; RPO phụ thuộc replication policy và node được chọn.

### 10.4. HA không thay backup

Nếu lỗi logic được commit, HA có thể chuyển sang replica chứa cùng lỗi. Backup/PITR mới giúp quay lại trước lỗi.

---

## 11. Các thành phần trong kiến trúc PostgreSQL HA

### 11.1. Primary

Node nhận writes từ ứng dụng và tạo WAL.

### 11.2. Standby

Node nhận WAL và replay. Có thể trở thành primary qua promotion.

### 11.3. HA manager

Theo dõi node health, replication state, quyết định failover và điều phối vai trò. Có thể là công cụ như Patroni, repmgr, pg_auto_failover hoặc giải pháp do cloud provider quản lý. Cách hoạt động và giới hạn phụ thuộc công cụ.

### 11.4. DCS/quorum store

Một số HA managers dùng distributed configuration store hoặc consensus system để lưu leader state và điều phối quyền primary. Quorum giúp giảm khả năng nhiều node tự nhận leader khi network partition.

### 11.5. Fencing

Fencing ngăn primary cũ tiếp tục nhận writes sau khi node mới được promote. Có thể dùng power fencing, cloud API, storage lease hoặc network isolation phù hợp.

### 11.6. Load balancer / service endpoint

Đưa ứng dụng tới primary hiện tại hoặc tách read/write endpoints. Có thể dùng proxy, service discovery, DNS hoặc virtual IP.

### 11.7. Monitoring

Theo dõi database, host, network, replication lag, WAL retention, backup status, storage và ứng dụng.

### 11.8. Backup repository

Lưu base backups, WAL archives, logical dumps và metadata độc lập với database nodes.

---

## 12. Failover và switchover

### 12.1. Failover

Failover là chuyển vai trò primary sang standby do primary cũ gặp sự cố hoặc không còn an toàn để phục vụ.

Quy trình khái quát:

1. Phát hiện primary không khỏe.
2. Xác định có thể liên lạc/fence primary cũ không.
3. Chọn standby đủ điều kiện.
4. Promote standby.
5. Chuyển endpoint/traffic.
6. Xác minh writes và dữ liệu.
7. Rebuild hoặc rewind các node cũ.

### 12.2. Switchover

Switchover là chuyển vai trò có kế hoạch khi primary cũ vẫn hoạt động.

Quy trình thường gồm:
- Ngừng nhận writes mới.
- Chờ transaction đang chạy hoàn tất.
- Đợi standby replay tới vị trí cần thiết.
- Chuyển vai trò và promote standby.
- Chuyển traffic.
- Đưa node cũ về standby.

### 12.3. So sánh

| Tiêu chí | Failover | Switchover |
| --- | --- | --- |
| Kích hoạt | Sự cố/primary không an toàn | Bảo trì hoặc chuyển đổi có kế hoạch |
| Primary cũ | Có thể không truy cập được | Thường còn hoạt động |
| Khả năng đợi replay | Bị giới hạn bởi sự cố | Có thể phối hợp đợi |
| Data loss | Có thể xảy ra với async replication | Có thể giảm rất thấp nếu đồng bộ đúng |
| Downtime | Phụ thuộc detection/promotion/routing | Có thể kiểm soát theo lịch |
| Rejoin node cũ | Có thể cần rewind/rebuild | Có thể cấu hình lại làm standby |

### 12.4. Promotion không phải toàn bộ failover

Promote thành công chỉ chuyển database role. Ứng dụng, proxy, DNS, monitoring và các standby khác vẫn cần được cập nhật.

---

## 13. Failure detection và nguy cơ false positive

### 13.1. Health check

Health check có thể kiểm tra process, SQL query, WAL progress, disk, network hoặc khả năng ghi. Một TCP port mở không chứng minh database sẵn sàng nhận writes.

### 13.2. Network partition

Primary có thể vẫn hoạt động nhưng monitor/standby không liên lạc được. Nếu standby được promote trong khi primary cũ vẫn nhận writes, split brain xảy ra.

### 13.3. Detection timeout

Timeout quá ngắn dễ gây false failover do network jitter hoặc tải cao. Timeout quá dài làm downtime kéo dài. Chọn theo failure model và SLA.

### 13.4. Quorum

Một hệ thống HA cần đủ bằng chứng/quorum để quyết định node nào là leader. Không để mỗi node tự quyết định mình là primary chỉ dựa trên việc mất kết nối tới node khác.

### 13.5. Operator decision

Trong hệ thống ít node hoặc không có consensus manager, failover thủ công cần runbook và người có thẩm quyền xác nhận trạng thái primary cũ.

---

## 14. Fencing và split brain

Split brain là tình huống hai node cùng hoạt động như primary và nhận writes độc lập.

### 14.1. Vì sao nguy hiểm?

Hai node tạo WAL trên các nhánh khác nhau. PostgreSQL không tự merge hai lịch sử. Ứng dụng có thể ghi hai kết quả mâu thuẫn.

### 14.2. Timeline không ngăn split brain

Timeline giúp phân biệt các nhánh WAL sau khi divergence xảy ra. Nó không tự khóa node cũ.

### 14.3. Fencing trước promotion

Trước khi promote standby, cần bảo đảm primary cũ không thể nhận writes. Fencing có thể thực hiện ở lớp hạ tầng, storage, network hoặc HA manager.

### 14.4. Không chỉ dựa vào ping

Một node không phản hồi ping có thể vẫn chạy database và phục vụ ứng dụng. Cần tín hiệu độc lập và fencing đáng tin cậy.

### 14.5. Sau khi split brain xảy ra

- Ngừng/fence node không authoritative.
- Bảo toàn data directories/logs của cả hai nhánh.
- Chọn một nhánh làm nguồn chính theo policy.
- Rewind/rebuild node cần rejoin.
- Trích xuất và reconcile dữ liệu chỉ tồn tại ở nhánh cũ nếu nghiệp vụ cần.
- Điều tra HA control plane và fencing failure.

---

## 15. RPO và RTO

RPO và RTO giúp biến mục tiêu phục hồi thành tiêu chí thiết kế có thể đo.

### 15.1. RPO - Recovery Point Objective

RPO là lượng dữ liệu tối đa doanh nghiệp chấp nhận mất khi xảy ra sự cố, thường biểu diễn bằng khoảng thời gian.

Ví dụ:
- RPO 0: mục tiêu không mất transaction đã xác nhận theo semantics được cam kết.
- RPO 5 phút: chấp nhận phục hồi tới điểm cách sự cố tối đa 5 phút.
- RPO 24 giờ: backup mỗi ngày có thể là một phần của kế hoạch, nhưng WAL/archive frequency còn quyết định khả năng đạt mục tiêu.

RPO thực tế phụ thuộc backup/WAL archive, replication mode, storage và failure scenario.

### 15.2. RTO - Recovery Time Objective

RTO là thời gian mục tiêu để dịch vụ trở lại mức hoạt động được chấp nhận.

Ví dụ:
- RTO 1 phút: cần standby sẵn sàng và failover/routing rất nhanh.
- RTO 30 phút: có thể restore nhanh từ backup trong một số hệ thống, nhưng cần đo thực tế.
- RTO 8 giờ: có thể chấp nhận quy trình DR thủ công lâu hơn.

### 15.3. RPO/RTO không tự được bảo đảm bởi setting

Bật archive_mode không chứng minh RPO đạt 5 phút. Có standby không chứng minh RTO đạt 1 phút. Cần đo trong restore/failover drills.

### 15.4. Ví dụ ma trận

| Cơ chế | RPO thường ảnh hưởng | RTO thường ảnh hưởng |
| --- | --- | --- |
| Async replication | Có thể mất WAL chưa tới standby | Promote nhanh nếu standby sẵn sàng |
| Sync replication | Có thể bảo vệ commit theo sync policy | Có thể tăng commit wait khi mất standby |
| Base backup | Điểm dữ liệu của backup | Thời gian restore/copy |
| WAL archive | Khoảng trống giữa các WAL đã archive | Replay time tới target |
| PITR | Có thể chọn điểm gần lỗi nếu WAL đủ | Restore + replay có thể lâu |
| HA manager | Không tự quyết định dữ liệu đã bền vững | Giảm detection/promotion/routing time |
| Restore drill | Xác minh RPO có thể đạt | Đo RTO thực tế |

---

## 16. Failure domains và vị trí đặt replicas/backups

Một failure domain là phạm vi các thành phần có thể cùng bị ảnh hưởng bởi một sự cố.

### 16.1. Process failure

PostgreSQL process hoặc OS service dừng. Standby khác trên cùng host không giúp nếu host không còn hoạt động.

### 16.2. Host failure

Máy vật lý/VM bị lỗi. Replicas trên host khác có thể tiếp tục.

### 16.3. Storage failure

Disk/volume bị hỏng hoặc filesystem không truy cập được. Replicas trên volume độc lập giúp giảm rủi ro.

### 16.4. Rack/zone failure

Mất điện, mạng hoặc hạ tầng trong một rack/availability zone. Replica ở zone khác giúp HA/DR tốt hơn.

### 16.5. Region failure

Mất toàn bộ region hoặc control plane. Replica và backup ở region khác có thể cần thiết.

### 16.6. Credential/control-plane failure

Một tài khoản quản trị bị chiếm quyền có thể xóa primary, replicas và backup nếu tất cả dùng cùng credentials/permissions. Tách quyền, MFA, immutable backup và audit logs.

### 16.7. Human/logic failure

Lệnh DELETE/DROP nhầm, migration lỗi, application bug hoặc dữ liệu sai có thể replicate. Backup lịch sử giúp quay lại.

### 16.8. Đặt backup cùng nơi với primary

Một bản backup trên cùng volume không bảo vệ trước mất volume. Một archive bucket cùng quyền xóa và cùng account có thể bị xóa cùng database.

---

## 17. Kiến trúc cơ bản: primary và standby cùng vùng

```text
Application
    |
    v
Write endpoint
    |
    v
Primary (Zone A)
    |
    | Physical streaming replication
    v
Standby (Zone B)

Backup job
    |
    +--> Base backup repository
    +--> WAL archive repository
```

### 17.1. Lợi ích

- Chuyển primary khi host/zone gặp lỗi.
- Standby có thể phục vụ read-only workload.
- Replication lag thường thấp hơn so với liên vùng xa.

### 17.2. Giới hạn

- Một sự cố region vẫn có thể ảnh hưởng cả hai zone.
- Lỗi logic được replicate.
- Backup repository vẫn cần độc lập.
- HA manager, routing và fencing vẫn cần thiết.

### 17.3. Async hay sync?

Sync có thể giảm data loss nhưng tăng commit latency và phụ thuộc standby/network. Async giảm latency nhưng có thể mất một lượng WAL khi failover.

### 17.4. Nhiều standby

Có thể có một synchronous standby cho durability và một hoặc nhiều asynchronous standbys cho read/DR. Cần xác định node nào được phép promote và policy chọn node.

---

## 18. Kiến trúc HA kết hợp DR liên vùng

```text
                  Region A
             +----------------+
Application -> HA endpoint
             | Primary        |
             | Standby A2     |
             +-------+--------+
                     |
                     | WAL replication / archive
                     v
                  Region B
             +----------------+
             | DR standby     |
             | Backup copy    |
             | WAL archive    |
             +----------------+

Backup repository độc lập:
  - Base backups
  - WAL archives
  - Immutable/offsite copy
  - Restore metadata
```

### 18.1. HA trong vùng

Standby cùng vùng hoặc zone khác có thể xử lý host/zone failures với latency thấp.

### 18.2. DR liên vùng

Replica ở region khác hỗ trợ sự cố region. Network latency cao có thể khiến async replication phù hợp hơn, tùy RPO.

### 18.3. Backup offsite

Backup phải có failure domain độc lập, credentials tách biệt và retention đủ dài.

### 18.4. Failover liên vùng cần runbook riêng

Cần kiểm tra network partition, DNS/routing, data lag, archive state, fencing primary region cũ và khả năng quay lại region ban đầu.

### 18.5. Failback không đơn giản là đổi DNS về cũ

Sau DR promotion, timeline mới đã hình thành. Primary cũ phải được rewind/rebuild và rejoin như standby trước khi cân nhắc chuyển vai trò trở lại.

---

## 19. Backup retention và bảo vệ khỏi lỗi logic

### 19.1. Retention window

Giữ backup đủ lâu để phát hiện lỗi chậm. Nếu lỗi logic chỉ được phát hiện sau 10 ngày nhưng backup/WAL retention chỉ có 3 ngày, có thể không còn target phục hồi phù hợp.

### 19.2. Base backup cadence

Backup thường xuyên hơn giảm lượng WAL phải replay và có thể giảm RTO, nhưng tăng storage, network và backup processing cost.

### 19.3. WAL archive cadence

WAL segments thường được archive khi hoàn tất; archive_timeout có thể giúp tạo segment archive trong workload ít ghi. Thiết lập cần cân bằng freshness và overhead.

### 19.4. Immutable backups

Dùng object lock/immutability hoặc repository không cho phép cùng credentials xóa/ghi đè bản backup trong retention window, nếu yêu cầu bảo vệ ransomware.

### 19.5. Credential separation

Backup operator, database admin và application user nên có quyền riêng. Không dùng một credential có thể vừa xóa database vừa xóa mọi backup.

### 19.6. Logical exports bổ sung

Logical dump định kỳ có thể hữu ích cho object-level recovery và migration. Nó bổ sung cho physical backup chứ không tự thay thế.

### 19.7. Backup catalog

Lưu metadata về:
- Backup start/end time.
- PostgreSQL version.
- System identifier.
- Timeline.
- WAL start/stop LSN.
- Tablespaces.
- Encryption/key references.
- Checksum/manifest.
- Retention expiry.
- Restore test result.

---

## 20. Backup consistency và kiểm chứng restore

### 20.1. Backup thành công không đủ

Một tool có thể báo backup complete nhưng archive bị thiếu WAL, quyền file sai hoặc restore target không khởi động.

### 20.2. Kiểm tra integrity

Dùng checksum/manifest hoặc công cụ backup hỗ trợ để xác minh các file không bị hỏng trong quá trình lưu/truyền.

### 20.3. Restore vào môi trường cô lập

Không restore thử trực tiếp lên production. Dùng data directory/VM/cluster riêng và ngăn kết nối nhầm tới production.

### 20.4. Kiểm tra PostgreSQL startup

Đọc logs, xác nhận recovery hoàn tất và không có missing WAL/page errors.

### 20.5. Kiểm tra dữ liệu nghiệp vụ

Đếm rows quan trọng, kiểm tra totals, foreign-key consistency và business invariants. Một server start được chưa đủ chứng minh dữ liệu đúng.

### 20.6. Application smoke tests

Chạy truy vấn và thao tác đọc phù hợp. Không để restore test gửi email/thanh toán hoặc trigger side effects thật.

### 20.7. Đo RTO

Tính từ lúc bắt đầu sự cố/restore theo định nghĩa vận hành tới lúc dịch vụ đạt mức sẵn sàng. Bao gồm copy, replay, validation, routing và application warm-up.

### 20.8. Đo RPO

Xác định timestamp/LSN mới nhất có thể khôi phục và so với thời điểm sự cố. Ghi lại bằng chứng.

---

## 21. HA không chỉ là database failover

Một số hệ thống database đã promote thành công nhưng ứng dụng vẫn không hoạt động.

### 21.1. Connection pool

Connection pool có thể giữ connections tới primary cũ. Cần phát hiện connection failure, reconnect và xác minh write endpoint mới.

### 21.2. DNS cache

Client có thể cache DNS lâu hơn TTL. Đổi DNS không đồng nghĩa mọi client lập tức dùng endpoint mới.

### 21.3. Load balancer/proxy

Proxy cần biết node nào là primary. Nếu health check chỉ kiểm tra TCP, nó có thể route writes tới standby read-only.

### 21.4. Read/write routing

Tách read endpoint và write endpoint rõ ràng. Không cho ứng dụng ghi nhầm vào read replica.

### 21.5. Secrets và certificates

Primary mới cần truy cập secrets, TLS certificates, KMS và network policies tương ứng.

### 21.6. Background jobs

Worker/cron jobs có thể chạy trên nhiều nodes sau failover. Cần bảo đảm job có leader lock/idempotency để không chạy trùng.

### 21.7. External systems

HA database không tự bảo vệ message queues, object storage, payment services hoặc cache. Cần đánh giá dependency của toàn ứng dụng.

---

## 22. Read replicas và read scaling

Replica có thể nhận một phần read workload để giảm tải primary.

### 22.1. Đọc dữ liệu trễ

Asynchronous standby có thể lag. Query ngay sau khi ghi vào primary có thể chưa thấy row trên standby.

### 22.2. Read-after-write

Nếu ứng dụng yêu cầu đọc ngay dữ liệu vừa ghi, route query tới primary hoặc dùng cơ chế đồng bộ phù hợp. remote_apply có thể hỗ trợ semantics cụ thể nhưng tăng latency.

### 22.3. Không phải mọi query phù hợp

Query nặng trên standby có thể conflict với WAL replay, làm tăng replay lag hoặc bị cancel. Cân bằng reporting workload và replication freshness.

### 22.4. Replica không tăng write capacity

Physical standby không nhận writes độc lập. Muốn scale writes cần kiến trúc khác và xử lý consistency/sharding ở tầng ứng dụng.

### 22.5. Read scaling không đồng nghĩa HA

Có nhiều read replicas nhưng không có failover, fencing và routing policy vẫn chưa phải HA hoàn chỉnh.

---

## 23. Backup, replication và HA trong các failure scenarios

| Sự cố | Replication giúp gì? | Backup giúp gì? | HA giúp gì? |
| --- | --- | --- | --- |
| Primary process crash | Standby còn bản sao | Restore nếu cần | Detect và promote |
| Host mất điện | Replica ở host khác | Khôi phục khi cần | Chuyển endpoint |
| Primary disk hỏng | Standby có thể phục vụ | Restore cluster từ backup | Failover và rebuild |
| Zone outage | Replica ở zone khác | Backup ngoài zone | Orchestrate chuyển node |
| Region outage | DR replica nếu có | Offsite backup | DR failover |
| DELETE nhầm | Thường replicate lỗi | PITR về trước DELETE | Không tự sửa dữ liệu |
| DROP DATABASE | Có thể replicate thay đổi | Restore từ backup | Có thể chuyển sang replica nhưng lỗi vẫn còn |
| Ransomware/xóa backup | Có thể bị ảnh hưởng cùng credentials | Immutable/offsite backup | Failover không đủ |
| WAL archive mất | Replica online có thể còn | Backup còn lại có thể restore hạn chế | Không tự khôi phục WAL |
| Standby disk hỏng | Primary vẫn phục vụ | Rebuild standby | Giữ service nếu primary khỏe |
| Primary và standby cùng zone mất | Không còn bản sao cùng zone | Offsite backup/DR replica | DR plan |
| Hai primary cùng nhận ghi | Hai nhánh diverge | Backup hỗ trợ phục hồi | Fencing/quorum phải ngăn |
| Application bug ghi sai | Sai lệch lan sang replicas | PITR/backup | HA không loại bỏ lỗi |
| Credential bị chiếm | Attacker có thể ghi/xóa | Tách quyền/immutable backup | Control plane cần bảo vệ |

### 23.1. Một cơ chế không giải quyết mọi failure modes

Thiết kế cần map từng sự cố với biện pháp phòng ngừa, phát hiện và phục hồi.

### 23.2. Failure mode có thể kết hợp

Ví dụ region outage đồng thời với lỗi credentials hoặc backup repository. Test một node crash không đủ đại diện cho mọi DR scenario.

---

## 24. Một số công cụ và lựa chọn triển khai

### 24.1. Native PostgreSQL

PostgreSQL cung cấp:
- Physical streaming replication.
- Synchronous replication.
- Replication slots.
- WAL archiving.
- Base backup qua pg_basebackup.
- Recovery/PITR.
- Promotion và các system views.

Native PostgreSQL cung cấp primitives; tổ chức cần thiết kế orchestration, fencing, routing và backup management.

### 24.2. Patroni

Patroni là một giải pháp quản lý HA cho PostgreSQL, thường dùng DCS để điều phối leader/lease và failover. Cần triển khai DCS, fencing/role checks, routing và backup riêng.

### 24.3. repmgr

repmgr cung cấp công cụ quản lý/giám sát replication và hỗ trợ failover/switchover theo cấu hình. Cần kiểm thử topology và các hành vi failure.

### 24.4. pg_auto_failover

pg_auto_failover điều phối PostgreSQL nodes qua monitor và state machine. Thiết kế vẫn cần hiểu quorum, network và backup.

### 24.5. Managed PostgreSQL

Cloud provider có thể cung cấp HA, backup và PITR tích hợp. Cần đọc SLA, failover behavior, backup retention, region limitations, export/restore options và quyền truy cập.

### 24.6. Không chọn tool chỉ theo tên HA

So sánh:
- Failure detection.
- Consensus/quorum.
- Fencing.
- Promotion safety.
- Synchronous replication support.
- Rejoin/rewind.
- Backup/PITR integration.
- Monitoring và audit.
- Upgrade/maintenance.
- Operational complexity và support.

---

## 25. Thiết kế một chiến lược phối hợp ba lớp

Một thiết kế thường có ba lớp bổ sung:

### 25.1. Lớp replication

- Primary và ít nhất một standby.
- Xác định physical hay logical.
- Chọn async/sync theo RPO và latency.
- Replication slots/retention phù hợp.
- Theo dõi WAL receive/flush/replay.

### 25.2. Lớp HA

- Health checks.
- Leader/quorum policy.
- Fencing.
- Promotion.
- Write endpoint routing.
- Rejoin/rebuild.
- Runbook và diễn tập.

### 25.3. Lớp backup/DR

- Base backup định kỳ.
- WAL archive liên tục.
- Logical dump bổ sung khi cần.
- Offsite/immutable copies.
- Retention theo RPO/tuân thủ.
- Restore drills và đo RTO/RPO.

### 25.4. Sơ đồ phối hợp

```text
                    Application
                        |
                  Write endpoint
                        |
                        v
                 HA-managed primary
                    /        \
                   / WAL      \ WAL
                  v            v
            Standby A       Standby B
             (sync)          (async / DR)

Primary / standby backup source
              |
              +---- Base backup ------> Backup repository
              |
              +---- WAL archive ------> Offsite immutable storage
                                            |
                                            v
                                      PITR / DR restore

HA manager:
  health + quorum + fencing + promotion + routing
```

### 25.5. Tách failure domains

Đặt ít nhất một bản backup ngoài host/zone/region của primary, và tách quyền xóa backup khỏi quyền quản trị database.

### 25.6. Đừng để một node làm mọi vai trò

Một standby có thể vừa là HA candidate vừa là backup source, nhưng cần giới hạn backup load và không để lỗi cùng node làm mất mọi lớp bảo vệ.

---

## 26. Ví dụ thiết kế theo yêu cầu RPO/RTO

### 26.1. Hệ thống nghiệp vụ nhỏ

Yêu cầu:
- RPO 15 phút.
- RTO 2 giờ.
- Workload vừa phải.
- Có thể chấp nhận DR thủ công.

Thiết kế có thể gồm:
- Base backup định kỳ.
- WAL archive liên tục tới object storage.
- Một asynchronous standby nếu cần giảm thời gian phục hồi.
- Restore drill hàng quý.
- Alert archive lag và backup age.

Cần đo restore time thực tế; không mặc định RPO đạt 15 phút chỉ vì có lịch backup.

### 26.2. Ứng dụng giao dịch quan trọng trong một region

Yêu cầu:
- RPO rất thấp.
- RTO vài phút.
- Không muốn mất commit đã xác nhận khi một host hỏng.

Thiết kế có thể gồm:
- Primary và synchronous standby ở failure domains khác nhau.
- HA manager với quorum/fencing.
- Write endpoint có failover.
- Base backup/WAL archive độc lập.
- Test node failure và network partition.
- Theo dõi commit latency, sync state và replay.

### 26.3. Dịch vụ đa vùng

Yêu cầu:
- Chịu được mất region.
- RPO vài phút.
- RTO dưới một giờ.
- Region DR có thể nhận traffic sau quy trình chuyển đổi.

Thiết kế có thể gồm:
- HA local trong region chính.
- Async physical standby ở region DR.
- WAL archive và base backup offsite.
- DR runbook, fencing region cũ, DNS/traffic switch.
- Test network partition và region outage.
- Kế hoạch failback qua rewind/rebuild.

### 26.4. Không sao chép một cấu hình cho mọi hệ thống

Cần cân nhắc latency giữa zones, throughput, data size, backup window, compliance, chi phí storage và năng lực vận hành.

---

## 27. Monitoring cho replication, backup và HA

### 27.1. Replication monitoring

Trên primary:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication;
```

Theo dõi state, LSN gap, lag trend và sync_state. Một số columns phụ thuộc version.

### 27.2. Standby monitoring

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 27.3. Slot monitoring

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

Theo dõi inactive duration, restart_lsn, wal_status và retained WAL khi có columns phù hợp.

### 27.4. Archive monitoring

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

Theo dõi archived_count, failed_count, last_archived_time và last_failed_time. Cần kết hợp inventory/checksum từ repository.

### 27.5. Backup freshness

Theo dõi:
- Thời điểm base backup thành công gần nhất.
- Thời gian backup hoàn tất.
- WAL start/stop LSN.
- Archive continuity tới hiện tại.
- Repository free space.
- Backup checksum/verification.
- Restore test gần nhất.

### 27.6. HA monitoring

Theo dõi:
- Leader hiện tại.
- Quorum/DCS health.
- Fencing status.
- Failover events.
- Promotion duration.
- Write endpoint target.
- Replica rejoin status.
- Application connection errors.

### 27.7. Alert theo mục tiêu

Ví dụ:
- Backup age vượt ngưỡng RPO.
- Archive gap xuất hiện.
- Standby lag vượt policy.
- Không còn synchronous standby cần thiết.
- Slot retention gần giới hạn.
- WAL filesystem sắp đầy.
- HA manager mất quorum.
- Failover xảy ra nhưng traffic chưa chuyển.
- Restore drill quá hạn.

---

## 28. Runbook failover ở mức khái niệm

### 28.1. Xác nhận primary failure

Dùng nhiều tín hiệu độc lập: database health, host health, storage, network và ứng dụng. Phân biệt process crash với network partition.

### 28.2. Xác định node có thể promote

Kiểm tra standby state, timeline, receive/flush/replay LSN, sync status và WAL archive. Đánh giá data loss có thể xảy ra.

### 28.3. Fence primary cũ

Bảo đảm node cũ không còn nhận writes. Dùng HA manager/quorum và hạ tầng fencing.

### 28.4. Promote standby

Thực hiện qua HA manager hoặc runbook đã kiểm thử. Xác nhận pg_is_in_recovery() trả false và primary mới có thể ghi.

### 28.5. Chuyển traffic

Cập nhật proxy/service discovery/DNS hoặc endpoint. Làm mới connection pools và background workers.

### 28.6. Xác minh nghiệp vụ

Chạy smoke tests và kiểm tra transaction quan trọng. Theo dõi commit errors, latency và application logs.

### 28.7. Rejoin các node cũ

Dùng pg_rewind khi đủ điều kiện hoặc base backup mới. Không khởi động primary cũ như primary thứ hai.

### 28.8. Ghi incident

Lưu timeline ID, LSN, fork point, node được promote, fencing evidence, RPO thực tế, downtime và phương pháp rejoin.

---

## 29. Runbook restore và PITR

### 29.1. Xác định thời điểm lỗi

Tìm timestamp, transaction, restore point hoặc LSN trước khi dữ liệu bị hỏng.

### 29.2. Chọn base backup

Chọn backup còn hợp lệ, đúng cluster/version và có WAL path tới recovery target.

### 29.3. Kiểm tra archive continuity

Xác minh WAL segments và timeline history files cần thiết tồn tại, có checksum đúng và truy cập được.

### 29.4. Restore vào môi trường riêng

Không overwrite primary đang chạy. Khôi phục base backup vào data directory/host riêng.

### 29.5. Cấu hình recovery

Dùng restore_command, recovery_target_time/LSN/name và recovery_target_timeline phù hợp. Với PostgreSQL 12+, archive recovery thường dùng recovery.signal.

### 29.6. Pause và kiểm tra

Có thể cấu hình recovery_target_action=pause để xác minh dữ liệu trước khi promote.

### 29.7. Promote và chuyển ứng dụng

Chỉ promote khi đã quyết định nhánh dữ liệu đúng. Promotion tạo timeline mới; cần cập nhật archive/standby topology.

### 29.8. Lưu bản gốc để điều tra

Giữ data directory/backup của trạng thái lỗi theo retention policy nếu cần phân tích root cause.

---

## 30. Disaster recovery và failback

### 30.1. DR là khôi phục dịch vụ sau sự cố lớn

DR thường bao gồm region outage, mất storage/site hoặc sự cố bảo mật. Nó có thể dùng standby DR hoặc restore từ backup.

### 30.2. DR failover

Nếu promote DR standby, xác định WAL đã nhận/replay và chấp nhận RPO. Fence region cũ trước khi mở writes ở region DR.

### 30.3. Backup restore DR

Nếu không có standby usable, restore base backup và replay WAL archive. RTO phụ thuộc data size, network, storage và replay volume.

### 30.4. Failback

Khi site cũ trở lại:
- Không tự động nhận ghi.
- Rewind/rebuild thành standby từ primary hiện tại.
- Chờ catch-up và kiểm tra.
- Lên kế hoạch switchover có kiểm soát nếu muốn chuyển về site ban đầu.

### 30.5. DR drill

Thực hiện diễn tập theo lịch. Một runbook chưa từng chạy có thể thiếu quyền, network rules, DNS, KMS access hoặc capacity.

---

## 31. Các sai lầm thiết kế phổ biến

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Xem standby là backup | Lỗi logic lan sang standby | Có base backup + WAL archive |
| Chỉ có backup, không có standby | Restore lâu khi primary mất | Thêm HA/replica nếu RTO yêu cầu |
| Bật replication nhưng không có failover | Node dự phòng không được chuyển vai trò an toàn | HA manager/runbook/fencing |
| Bật auto-failover không có fencing | Split brain | Quorum và fencing độc lập |
| Tất cả nodes cùng zone | Zone outage làm mất HA | Phân bố failure domains |
| Backup cùng volume với primary | Mất cùng lúc | Offsite/independent repository |
| Backup dùng cùng quyền xóa | Credential compromise xóa cả backup | Tách credentials/immutability |
| Không test restore | Backup hỏng không được phát hiện | Restore drills |
| Chỉ đo backup job success | Không biết WAL continuity/restore | Kiểm tra restore end-to-end |
| Async replication nhưng tuyên bố RPO 0 | Có thể mất WAL cuối | Sync policy hoặc sửa RPO |
| Sync replication không xét availability | Commit bị block khi standby mất | Thiết kế quorum/failure policy |
| Không giám sát slot retention | pg_wal đầy | Slot/disk alerts |
| Không giám sát archive | PITR chain bị đứt | Archive continuity alerts |
| Chỉ đổi DNS khi failover | Client cache/connection pool còn endpoint cũ | Proxy/service discovery/reconnect |
| Không có kế hoạch rejoin | Primary cũ diverged | pg_rewind/rebuild runbook |
| Không tách DR khỏi HA | Region failure không có đường phục hồi | DR site và offsite backup |
| Không tính backup restore bandwidth | RTO vượt mục tiêu | Capacity/restore testing |
| Không có inventory dependencies | Restore thiếu KMS/extensions/secrets | Backup catalog/runbook |
| Không test lỗi logic | Không biết cách PITR | Diễn tập restore trước sự cố |
| Không đo RPO/RTO | SLA chỉ là giả định | Ghi bằng chứng từ drills |

---

## 32. Lab 1: quan sát replication và backup khác nhau

Lab cần một PostgreSQL primary và standby riêng.

### 32.1. Tạo bảng thử trên primary

```sql
CREATE TABLE IF NOT EXISTS public.ha_backup_lab (
    id BIGINT PRIMARY KEY,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO public.ha_backup_lab(id, note)
VALUES (1, 'before-backup')
ON CONFLICT (id) DO UPDATE
SET note = EXCLUDED.note;
```

### 32.2. Chờ standby replay

Kiểm tra trên standby:

```sql
SELECT *
FROM public.ha_backup_lab
WHERE id = 1;
```

### 32.3. Tạo logical dump

```bash
pg_dump -Fc -d appdb -f ha_backup_lab.dump
```

Chạy từ host có quyền và connection phù hợp. Lệnh minh họa dump toàn database appdb.

### 32.4. Thực hiện lỗi logic trong lab

```sql
DELETE FROM public.ha_backup_lab
WHERE id = 1;
```

Chờ standby replay và quan sát row cũng biến mất trên standby.

### 32.5. Restore dump vào database riêng

Tạo database đích và dùng pg_restore. Xác nhận row trước DELETE vẫn có trong backup.

### 32.6. Kết luận

Replica phản ánh trạng thái mới của primary; backup giữ trạng thái tại thời điểm backup. Hai cơ chế phục vụ hai mục tiêu khác nhau.

---

## 33. Lab 2: quan sát RPO và replication mode

Lab cần primary và standby, synchronous replication được cấu hình phù hợp nếu muốn thử sync behavior.

### 33.1. Ghi lại replication state

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

### 33.2. Ghi transaction test

```sql
INSERT INTO public.ha_backup_lab(id, note)
VALUES (2, 'commit-test');
```

Ghi thời điểm commit và quan sát LSN.

### 33.3. So sánh async và sync trong lab

Thay đổi cấu hình theo runbook lab, không thay đổi production. Đo commit latency và standby flush/replay progress.

### 33.4. Mô phỏng failover

Chỉ khi đã fencing primary trong lab, promote standby. Xác nhận row commit-test có trên node được promote.

### 33.5. Diễn giải

Async có thể có commit chưa tới standby; sync remote flush có thể bảo vệ commit được xác nhận theo policy nếu đúng standby được promote. Không suy diễn từ một lần thử thành guarantee cho mọi failure scenario.

---

## 34. Lab 3: backup và PITR

### 34.1. Bật WAL archiving

Cấu hình archive_mode và archive_command trên lab primary. Xác minh archive destination.

### 34.2. Tạo base backup

Dùng pg_basebackup hoặc công cụ backup tương thích. Ghi metadata và timeline.

### 34.3. Tạo restore point

```sql
SELECT pg_create_restore_point('before_lab_delete');
```

Lưu LSN/time.

### 34.4. Ghi dữ liệu sau restore point

```sql
INSERT INTO public.ha_backup_lab(id, note)
VALUES (3, 'after-restore-point');
```

### 34.5. Restore bản sao riêng

Dùng base backup và WAL archive để phục hồi tới restore point, với recovery.signal/recovery settings theo phiên bản.

### 34.6. Xác minh

Row trước target có mặt; row sau target không xuất hiện nếu recovery dừng trước nó.

### 34.7. Đo thời gian

Ghi thời gian copy base backup, replay WAL, validation và thời điểm ứng dụng sẵn sàng. Từ đó ước lượng RTO thực tế.

---

## 35. Lab 4: failover và routing

Lab cần HA manager hoặc môi trường hai node có quy trình promotion được kiểm soát.

### 35.1. Ghi trạng thái ban đầu

Lưu primary identity, standby state, sync_state, LSN, endpoint và ứng dụng health.

### 35.2. Thử health check

Mô phỏng primary process failure hoặc network partition trong lab. Quan sát HA manager có phân biệt được hai tình huống không.

### 35.3. Fencing

Xác minh primary cũ không còn nhận writes trước khi promotion.

### 35.4. Promote standby

Dùng HA manager hoặc runbook. Xác nhận pg_is_in_recovery() false.

### 35.5. Chuyển traffic

Đổi write endpoint/proxy/service discovery. Xác minh client mới có thể kết nối và ghi.

### 35.6. Rejoin node cũ

Dùng pg_rewind nếu đủ điều kiện hoặc base backup mới. Xác nhận nó trở lại standby.

### 35.7. Đo downtime

Ghi thời gian detection, fencing, promotion, routing và application recovery. Không chỉ đo thời gian pg_promote.

---

## 36. Lab 5: backup failure domain

### 36.1. Vẽ topology

Đánh dấu host, zone, region, storage account, credentials và backup repository.

### 36.2. Xác định điểm chung

Hỏi: nếu mất zone A, account cloud, KMS key hoặc admin credentials thì primary, replica và backup nào còn truy cập được?

### 36.3. Kiểm tra quyền

Xác minh database admin có thể xóa backup không, backup service có quyền xóa database không và immutable retention có được áp dụng không.

### 36.4. Thử restore offsite

Dùng môi trường cô lập để lấy base backup/WAL từ offsite repository và restore.

### 36.5. Ghi RTO/RPO

Đo thời gian download, restore, replay và validation. Ghi mọi dependency thiếu như credentials, extensions, certificates hoặc network access.

---

## 37. Bài tập thực hành

### Bài 1 — Định nghĩa

Phân biệt replication, backup và HA bằng một câu hỏi vận hành cho mỗi cơ chế.

### Bài 2 — Replication không phải backup

Giải thích vì sao DELETE nhầm trên primary cũng xuất hiện trên physical standby.

### Bài 3 — Backup không phải HA

Vì sao một base backup tốt không giúp ứng dụng tiếp tục ghi ngay khi primary crash?

### Bài 4 — HA không phải backup

Nêu cách lỗi logic có thể lan qua một cụm HA và cách phục hồi về trước lỗi.

### Bài 5 — Durability và recoverability

Phân biệt hai mục tiêu này và nêu cơ chế PostgreSQL liên quan.

### Bài 6 — Physical replication

Vẽ WAL sender/receiver và startup replay path.

### Bài 7 — Logical replication

So sánh logical và physical replication về phạm vi, schema, DDL và cluster objects.

### Bài 8 — Async replication

Giải thích trường hợp primary xác nhận COMMIT nhưng standby chưa nhận WAL.

### Bài 9 — Sync replication

So sánh remote_write, remote_flush và remote_apply. Nêu latency trade-off.

### Bài 10 — Synchronous availability

Điều gì có thể xảy ra với commit khi synchronous standby mất kết nối?

### Bài 11 — Base backup

Nêu mục tiêu và thành phần của một physical base backup.

### Bài 12 — Logical dump

Khi nào pg_dump phù hợp hơn base backup? Vì sao nó không thay thế physical PITR?

### Bài 13 — WAL archive

Giải thích vì sao cần WAL archive để PITR từ base backup tới recovery target.

### Bài 14 — Restore drill

Thiết kế test restore một backup và kiểm tra dữ liệu ứng dụng.

### Bài 15 — RPO

Một doanh nghiệp chấp nhận mất tối đa 5 phút dữ liệu. Những cấu hình và metrics nào cần xem xét?

### Bài 16 — RTO

Một dịch vụ cần hoạt động lại trong 2 phút. Vì sao restore từ backup có thể không đủ?

### Bài 17 — Failure domains

Vẽ failure domains của primary, standby, storage, zone và backup repository.

### Bài 18 — Failover

Mô tả trình tự phát hiện primary failure, fencing, promotion và routing.

### Bài 19 — Switchover

Giải thích vì sao switchover có kế hoạch thường dễ giảm data loss hơn failover bất ngờ.

### Bài 20 — Split brain

Mô tả network partition khiến hai primary cùng nhận ghi và vai trò fencing.

### Bài 21 — HA manager

Một HA manager cần lưu trạng thái gì và phối hợp những hành động nào?

### Bài 22 — Quorum

Giải thích vì sao quorum giúp giảm nguy cơ hai node cùng được chọn làm leader.

### Bài 23 — Connection routing

Sau promotion, vì sao đổi DNS có thể chưa đủ để ứng dụng chuyển sang primary mới?

### Bài 24 — Read replicas

Một query đọc ngay sau write không thấy row trên standby. Giải thích replication lag và lựa chọn routing.

### Bài 25 — DR region

Thiết kế một standby async ở region khác và nêu các bước fencing/route khi region chính mất.

### Bài 26 — Backup immutability

Đề xuất cách tách quyền xóa backup khỏi database administrator.

### Bài 27 — Backup retention

Lỗi logic chỉ được phát hiện sau 12 ngày. Backup/WAL retention cần đáp ứng điều gì?

### Bài 28 — Ransomware

Vì sao replicas có thể bị ảnh hưởng cùng primary? Đề xuất backup isolation và credential separation.

### Bài 29 — Monitoring

Thiết kế dashboard phân biệt replication lag, archive lag, backup freshness và HA manager health.

### Bài 30 — Sự cố disk

Primary disk hỏng nhưng standby khỏe. Mô tả failover và cách tạo standby mới sau đó.

### Bài 31 — Sự cố logic

Một migration DROP nhầm bảng đã replicate. Lập quy trình PITR để phục hồi bảng mà không làm mất các writes hợp lệ sau đó.

### Bài 32 — Synchronous standby down

Đánh giá trade-off giữa chờ commit, đổi sync policy và availability. Nêu rủi ro của mỗi quyết định.

### Bài 33 — Multi-zone

Thiết kế primary, synchronous standby và asynchronous DR standby với các failure domains riêng.

### Bài 34 — Restore capacity

Một base backup 4 TB cần restore trong 45 phút. Tính throughput trung bình cần có và nêu những phần thời gian khác cần đo.

### Bài 35 — Backup source trên standby

Nêu lợi ích và rủi ro khi lấy base backup từ standby thay vì primary.

### Bài 36 — HA không có backup

Đánh giá rủi ro của một hệ thống có ba replicas nhưng không có base backup/WAL archive.

### Bài 37 — Backup không có HA

Đánh giá rủi ro của một hệ thống backup tốt nhưng chỉ có một primary và RTO 1 phút.

### Bài 38 — Failback

Sau DR promotion, mô tả cách đưa site cũ trở lại làm standby rồi switchover có kế hoạch.

### Bài 39 — Kiểm thử

Thiết kế lịch quarterly DR drill bao gồm host failure, network partition, lỗi logic và mất region.

### Bài 40 — Thiết kế end-to-end

Một hệ thống order processing cần RPO dưới 1 phút, RTO dưới 5 phút, PITR 14 ngày và DR liên vùng. Đề xuất replication topology, synchronous/asynchronous policy, HA manager, fencing, backup repository, WAL archive, monitoring, failover/failback và restore drills. Phân tích trade-off về latency, availability, chi phí và độ phức tạp.

---

## 38. Checklist thiết kế và vận hành

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Replication phục vụ mục tiêu gì? | HA/read scaling/DR/migration |
| Physical hay logical? | Scope và semantics |
| Async hay sync? | RPO/latency |
| Standby ở failure domain khác? | Host/zone/region |
| Có WAL sender/receiver monitoring? | Replication views |
| Receive/flush/replay lag? | LSN and time metrics |
| Replication slots có capacity? | Slot retention |
| WAL archive liên tục? | Archive inventory/checksum |
| Base backup gần nhất? | Backup catalog |
| Backup có restore test? | Restore evidence |
| PITR target có thể đạt? | WAL continuity |
| Backup độc lập với primary? | Failure domain |
| Backup immutable? | Delete/write protection |
| Credentials có tách biệt? | Least privilege |
| RPO đã được định nghĩa? | Business requirement |
| RTO đã được định nghĩa? | Business requirement |
| RPO có được đo? | Latest recoverable point |
| RTO có được đo? | Restore/failover drill |
| HA manager có quorum? | Leader state |
| Fencing có hoạt động? | Old primary isolation |
| Failover đã test? | Promotion/routing |
| Switchover đã test? | Planned transition |
| Write endpoint tự cập nhật? | Proxy/DNS/service discovery |
| Connection pools reconnect? | Application behavior |
| Background jobs tránh chạy trùng? | Leader lock/idempotency |
| Primary cũ rejoin thế nào? | pg_rewind/base backup |
| DR region có đủ secrets/KMS? | Dependencies |
| Restore capacity đủ? | Network/storage throughput |
| Archive retention đủ dài? | Backup dependency |
| Monitoring có alert theo trend? | Capacity and freshness |
| Incident runbook được cập nhật? | Ownership/escalation |
| DR drill có lịch? | Evidence |
| Data validation sau restore? | Business invariants |
| Có kế hoạch failback? | Rejoin and switchover |

## Kết luận

Replication, backup và High Availability là ba lớp bảo vệ có quan hệ với nhau nhưng không thể thay thế lẫn nhau.

Những nguyên tắc cần nhớ:

1. **Replication giữ bản sao cập nhật.** Nó hỗ trợ read scaling, HA và DR, nhưng thường cũng truyền các thay đổi sai hoặc thao tác xóa nhầm.
2. **Backup giữ trạng thái có thể khôi phục.** Base backup kết hợp WAL archive hỗ trợ PITR; logical dump bổ sung khả năng phục hồi object-level và migration.
3. **HA giữ dịch vụ tiếp tục hoạt động.** Nó cần standby, failure detection, quorum, fencing, promotion, routing, monitoring và runbook.
4. **Synchronous replication có thể giảm RPO.** Đổi lại commit có thể tăng latency hoặc bị chờ khi standby/network không sẵn sàng.
5. **Asynchronous replication có thể mất WAL gần nhất khi failover.** Phải công bố và kiểm thử RPO thực tế.
6. **Backup phải ở failure domain độc lập.** Tách storage, credentials và quyền xóa; dùng immutable/offsite copies khi yêu cầu.
7. **PITR cần base backup và WAL liên tục.** Archive thiếu một segment bắt buộc có thể làm recovery dừng trước target.
8. **Failover cần fencing.** Không promote standby chỉ vì primary không phản hồi; network partition có thể tạo split brain.
9. **Ứng dụng là một phần của HA.** Connection pool, DNS, proxy, background jobs và secrets đều phải hoạt động sau promotion.
10. **RPO/RTO phải được đo.** Backup age, WAL lag, restore time và failover time cần có bằng chứng từ diễn tập.
11. **DR cần failure domain riêng.** Replica ở zone khác không tự bảo vệ trước mất toàn region hoặc credential compromise.
12. **Restore drills chứng minh backup có thể dùng.** Kiểm tra startup, dữ liệu nghiệp vụ, ứng dụng và thời gian phục hồi định kỳ.

Một hệ thống PostgreSQL bền vững kết hợp bản sao cập nhật để chuyển đổi nhanh, backup độc lập để quay lại trạng thái đúng và cơ chế HA để phát hiện sự cố, chuyển vai trò an toàn rồi đưa ứng dụng trở lại phục vụ. Chỉ khi ba lớp này được thiết kế theo cùng mục tiêu RPO/RTO và được kiểm thử trong các failure scenarios thực tế, tổ chức mới có thể tin cậy vào khả năng sẵn sàng và phục hồi của dịch vụ.
