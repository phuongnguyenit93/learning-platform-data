# Cascading replication và phân phối tải

Streaming replication vật lý của PostgreSQL thường được mô tả bằng mô hình primary gửi WAL trực tiếp tới một hoặc nhiều standby. Khi số lượng standby, khoảng cách địa lý hoặc nhu cầu phân phối read traffic tăng lên, một primary có thể phải phục vụ quá nhiều kết nối replication và truyền WAL qua cùng một đường mạng. **Cascading replication** cho phép một standby tiếp tục gửi WAL mà nó đã nhận được tới các standby khác, tạo thành topology dạng cây. Cách này phân tán kết nối và băng thông WAL, đồng thời có thể đặt các read replicas gần nhóm ứng dụng hoặc khu vực cần đọc dữ liệu.

Cascading replication và phân phối tải đọc có liên quan nhưng là hai việc khác nhau. Cascading replication phân phối **luồng WAL** giữa các máy chủ. Việc phân phối **truy vấn SELECT** cần application routing, connection proxy hoặc middleware phù hợp; PostgreSQL không tự động chia mọi truy vấn đọc sang các standby chỉ vì chúng tồn tại. Một standby còn có thể làm relay WAL, phục vụ read-only queries, hoặc làm cả hai, tùy cấu hình và capacity.

Một topology nhiều tầng tạo ra thêm trade-offs: mỗi hop có thể tăng replay lag, upstream standby trở thành điểm phụ thuộc của downstream, slots có thể giữ WAL làm đầy disk, truy vấn dài trên hot standby có thể xung đột với WAL replay, và failover cần reparenting/fencing có chủ đích. Thiết kế tốt phải xem cả luồng WAL, luồng query, failure domains, consistency requirements và cách vận hành từng node.

Bài học thuộc chương **Sao chép vật lý** của module **Database Engine Relational PostgreSQL**. Nội dung tập trung vào cascading physical streaming replication, cách phân phối read workload trên hot standbys, quan sát lag/conflicts, quản lý WAL retention và xử lý sự cố topology.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cascading replication và vai trò của standby relay.
- Vẽ topology primary → standby → downstream standbys.
- Phân biệt WAL fan-out với read query load balancing.
- Xác định node nào gửi WAL và node nào nhận WAL trong từng hop.
- Cấu hình các tham số và quyền cần thiết cho physical streaming replication.
- Hiểu vai trò của primary_conninfo, application_name, replication slots và WAL retention.
- Ước lượng số sender connections và capacity cần trên mỗi node.
- Theo dõi write/flush/replay lag và hiểu giới hạn của các statistics views.
- Phân phối read traffic theo lag, latency, capacity và consistency requirement.
- Xử lý hot standby conflicts, hot_standby_feedback và truy vấn dài.
- Thiết kế failover, reparenting, fencing và rebuild downstream nodes.
- Đánh giá synchronous/asynchronous replication theo từng hop.
- Thực hành cấu hình và quan sát cascading topology trong lab.

## 2. Physical streaming replication hoạt động thế nào?

PostgreSQL ghi các thay đổi cần phục hồi vào Write-Ahead Log (WAL). Một physical standby nhận WAL records, lưu vào WAL files và replay chúng để dựng trạng thái dữ liệu giống upstream.

~~~text
Application writes
       |
       v
Primary PostgreSQL
       |
       | WAL sender / replication protocol
       v
Standby PostgreSQL
       |
       +--> WAL receiver writes WAL
       |
       +--> Startup process replays WAL
~~~

### 2.1. WAL sender

Trên node gửi, một backend WAL sender phục vụ kết nối replication và gửi WAL cho client. Primary có thể có nhiều WAL senders, tùy max_wal_senders và số kết nối cần thiết.

### 2.2. WAL receiver

Trên standby, WAL receiver kết nối tới upstream bằng primary_conninfo, nhận WAL và ghi vào local WAL area. Nó báo trạng thái nhận/replay theo cơ chế replication protocol.

### 2.3. Replay process

Startup process replay WAL để cập nhật data pages và catalog. WAL đã được nhận (write/flush) có thể chưa được replay; vì vậy receive position và replay position là hai tín hiệu khác nhau.

### 2.4. Standby read-only

Khi hot standby được bật và recovery state cho phép, client có thể kết nối để chạy read-only queries trong lúc WAL tiếp tục được replay. Không thể chạy DML thông thường trên hot standby.

### 2.5. Physical replication là block-level stream

Physical streaming replication truyền WAL để duy trì physical cluster state, không phải một tập lệnh SQL logical. Nó có version/architecture compatibility requirements khác logical replication.

## 3. Cascading replication là gì?

Trong cascading replication, một standby nhận WAL từ upstream rồi đóng vai trò WAL sender cho một hoặc nhiều downstream standbys.

~~~text
                  +------------------+
                  | Primary P        |
                  +--------+---------+
                           |
                         WAL
                           |
                  +--------v---------+
                  | Standby A        |
                  | receiver + sender|
                  +---+-----------+--+
                      |           |
                    WAL         WAL
                      |           |
              +-------v--+    +---v----------+
              | Standby B|    | Standby C    |
              +----------+    +--------------+
~~~

### 3.1. Standby vừa nhận vừa gửi WAL

Standby A có WAL receiver để nhận từ P và WAL sender để phục vụ B/C. Nó relay WAL mà nó đã nhận và có sẵn trên local storage.

### 3.2. Downstream kết nối với upstream gần nhất

Standby B có thể cấu hình primary_conninfo trỏ tới A thay vì P. Tương tự C có thể kết nối tới A.

### 3.3. Primary không phải gửi trực tiếp cho mọi standby

Nếu P chỉ gửi tới A, A phân phối WAL tới B và C. Điều này giảm số kết nối trực tiếp và network fan-out trên P, nhưng A phải gánh thêm sender/network/disk workload.

### 3.4. Cascading không tự tạo query routing

B và C chỉ nhận WAL theo topology. Muốn application đọc từ B/C, cần cấu hình router/proxy hoặc logic trong ứng dụng.

### 3.5. Cascading không phải multi-primary

Physical standbys vẫn là replicas read-only trong recovery. Writes được thực hiện trên primary được chỉ định; không có cơ chế tự merge writes độc lập từ nhiều nodes.

## 4. Topology dạng cây và các hop

Một physical standby thông thường có một upstream cho WAL streaming tại một thời điểm. Cascading topology vì thế thường được mô hình hóa thành cây có một nguồn authoritative.

~~~text
                         P
                    /    |    \
                   A     D     E
                 /   \
                B     C
               /
              F
~~~

### 4.1. Direct standby

A, D và E kết nối trực tiếp tới P. Chúng là direct downstream của P.

### 4.2. Cascaded standby

B/C kết nối tới A; F kết nối tới B. Chúng không tạo replication connection trực tiếp tới P trong topology hiện tại.

### 4.3. Mỗi hop có receive và replay progress riêng

B có thể đã nhận WAL từ A nhưng replay chậm. A có thể nhận WAL từ P nhanh nhưng gửi xuống B chậm. Cần theo dõi từng hop để biết lag phát sinh ở đâu.

### 4.4. Không tạo vòng lặp

Một topology hợp lệ phải tránh đường WAL quay lại node đã nằm phía upstream. Không thiết kế cycle như P→A→B→P.

### 4.5. Một node có thể có nhiều downstream

Số lượng downstream phụ thuộc max_wal_senders, connection budget, network bandwidth, CPU và khả năng đọc WAL trên sender. Không có một con số phù hợp cho mọi hệ thống.

## 5. Vì sao dùng cascading replication?

Cascading hữu ích khi muốn phân tán WAL delivery, đặt replicas gần workload đọc hoặc chia topology theo region/rack.

### 5.1. Giảm connection fan-out trên primary

Primary có thể gửi WAL tới một số relay standbys, thay vì trực tiếp phục vụ hàng chục/hàng trăm replicas.

### 5.2. Phân phối WAL theo địa lý

Một standby ở region trung gian có thể nhận WAL từ primary và relay tới các replicas trong cùng region hoặc mạng riêng.

### 5.3. Giảm egress/network pressure

Primary có thể chỉ cần gửi một luồng tới relay. Relay chịu trách nhiệm fan-out; tổng bytes vẫn phải truyền qua mạng, nhưng tải được đặt ở vị trí khác.

### 5.4. Phân nhóm read replicas

Một relay gần cụm analytics có thể cấp WAL cho nhiều read replicas của nhóm đó, trong khi một relay khác phục vụ ứng dụng ở khu vực khác.

### 5.5. Tăng khả năng mở rộng topology

Khi số lượng replicas tăng, cây replication giúp tổ chức kết nối và failure domains rõ ràng hơn. Đổi lại, relay trở thành dependency của descendants.

## 6. Những giới hạn của cascading

Cascading không làm biến mất chi phí replication; nó thay đổi nơi chi phí xuất hiện.

### 6.1. Thêm một hop có thể tăng lag

WAL phải được nhận từ P, có sẵn trên A, rồi được gửi tới B và replay. Mỗi giai đoạn có queue/network/disk latency riêng.

### 6.2. Relay có thể thành bottleneck

A vừa replay WAL vừa gửi cho nhiều downstream, đồng thời có thể phục vụ SELECT. CPU, disk I/O và network có thể bị tranh chấp.

### 6.3. Upstream relay là dependency

Nếu A ngừng hoạt động, B/C mất nguồn WAL cho tới khi được reparent hoặc A trở lại. Primary P vẫn có thể khỏe mạnh nhưng descendants vẫn bị lag.

### 6.4. WAL retention phức tạp hơn

Mỗi upstream phải giữ WAL đủ lâu cho downstream reconnect. Slot không được quản lý có thể giữ WAL quá nhiều và làm đầy disk.

### 6.5. Không bảo vệ khỏi logical corruption

Nếu P replay một transaction sai nghiệp vụ, các tầng cascading cũng có thể nhận/replay thay đổi đó. Backup/PITR vẫn cần thiết.

## 7. Cascading replication và read load balancing

Hai mục tiêu này thường được triển khai cùng nhau nhưng phải thiết kế riêng.

| Khía cạnh | Cascading replication | Read load balancing |
|---|---|---|
| Phân phối gì? | WAL stream | SQL read queries |
| Thành phần chính | WAL sender/receiver, standby | App router, proxy, pooler |
| Mục tiêu | Mở rộng WAL fan-out | Chia tải đọc |
| Đo lường | Receive/replay LSN, sender state | Query latency, QPS, CPU, cache hit |
| Failure mode | Upstream relay mất kết nối | Router chọn replica lỗi/lag |
| Consistency | Replay order của WAL | Query có thể đọc state trễ |

### 7.1. Một standby có thể chỉ làm relay

Node A có thể không nhận application queries; nó chỉ relay WAL cho B/C. Khi đó cần capacity ưu tiên cho WAL receiving/replay/sending.

### 7.2. Một standby có thể vừa relay vừa phục vụ đọc

Node A có thể được router đưa vào read pool, nhưng query load có thể cạnh tranh với WAL sender/receiver và replay.

### 7.3. Downstream có thể phục vụ nhóm đọc riêng

B/C có thể nằm gần các application regions, có policy connection và capacity riêng. Chúng thường có lag lớn hơn upstream trực tiếp.

### 7.4. Không route writes tới hot standby

Writes phải đi tới primary. Nếu proxy gửi DML tới standby, PostgreSQL sẽ từ chối vì recovery/read-only state.

### 7.5. Không route mọi SELECT sang replica một cách mù quáng

Các truy vấn cần read-after-write, transaction consistency hoặc dữ liệu mới nhất có thể phải đọc primary hoặc chờ replica replay tới LSN cần thiết.

## 8. Vai trò của từng node

Trước khi cấu hình, ghi rõ vai trò và owner của mỗi node.

| Node | Vai trò | Upstream | Downstream | App reads |
|---|---|---|---|---|
| P | Primary | — | A, D | Reads/writes chính |
| A | Relay + optional read | P | B, C | Tùy capacity |
| B | Read replica | A | F | Read group B |
| C | Read replica | A | — | Read group C |
| D | Direct standby | P | — | DR/read group D |

### 8.1. Primary

Chịu writes, tạo WAL và phục vụ direct replication clients.

### 8.2. Relay standby

Nhận/replay WAL, phục vụ downstream sender connections và có thể phục vụ read-only workload nếu capacity cho phép.

### 8.3. Leaf standby

Nhận WAL từ relay và thường phục vụ query traffic của một application group/region.

### 8.4. DR standby

Có thể nằm trong topology riêng để hỗ trợ failover hoặc DR. Không để routing read workload làm mất capacity cần cho recovery.

### 8.5. Role phải được ghi trong inventory

Tên host không đủ để biết topology. Ghi upstream, downstream, region, purpose, slot, connection budget và failover owner.

## 9. Các tham số nền tảng trên primary

Cấu hình chính xác tùy PostgreSQL version và tải. Các tham số thường cần xem gồm:

~~~conf
wal_level = replica
max_wal_senders = 16
max_replication_slots = 16
wal_keep_size = '2GB'
~~~

Đây là giá trị minh họa, không phải tuning recommendation.

### 9.1. wal_level

replica cung cấp WAL cần cho physical replication và archive recovery. logical bao gồm thêm thông tin phục vụ logical decoding nhưng có chi phí riêng; không cần bật chỉ vì dùng cascading physical replication.

### 9.2. max_wal_senders

Đặt đủ cho direct standbys, cascading relays, backup tools và các replication connections khác, có headroom khi reconnect/failover.

### 9.3. max_replication_slots

Đặt đủ slot cho các consumers cần giữ WAL. Slot có thể giữ WAL khi downstream ngắt kết nối; capacity phải tính cả retention risk.

### 9.4. wal_keep_size

Giữ tối thiểu một lượng WAL để standby reconnect sau gián đoạn ngắn. Nó không phải giới hạn retention tuyệt đối và không thay slot/archive trong mọi topology.

### 9.5. Thay đổi cần restart hay reload?

Một số parameters như wal_level, max_wal_senders và max_replication_slots có yêu cầu restart theo context/version. Xem pg_settings.context và pending_restart trước khi change.

## 10. Cấu hình relay standby để gửi WAL

Một relay standby cần nhận WAL từ upstream và có khả năng phục vụ replication connections cho downstream.

~~~conf
# Trên standby relay
hot_standby = on
max_wal_senders = 8
max_replication_slots = 8
wal_keep_size = '2GB'
~~~

### 10.1. max_wal_senders trên standby

Node relay cũng chạy WAL sender processes cho downstream. Đừng chỉ cấu hình max_wal_senders trên primary.

### 10.2. hot_standby

Bật hot standby nếu node cần phục vụ read-only queries trong recovery. Đây là yêu cầu cho query access; chức năng relay WAL và khả năng nhận downstream replication cũng cần kiểm tra theo phiên bản/cấu hình.

### 10.3. max_replication_slots trên relay

Nếu downstream dùng physical replication slots trên relay, cần đủ slot capacity ở relay và quản lý retention trên chính node đó.

### 10.4. Disk local

Relay cần đủ WAL disk để replay và giữ segments cho downstream. WAL retention trên relay có thể khác retention trên primary.

### 10.5. Resource isolation

Nếu relay cũng phục vụ reads, đặt connection limits, workload priorities và monitoring để read spikes không làm WAL distribution trễ.

## 11. Cấu hình downstream standby

Downstream trỏ tới relay bằng primary_conninfo, không nhất thiết trỏ tới primary gốc.

~~~conf
primary_conninfo = 'host=standby-a.example.internal port=5432 user=replicator application_name=standby-b sslmode=verify-full'
primary_slot_name = 'standby_b_slot'
~~~

Các giá trị host, role, certificate và slot chỉ minh họa.

### 11.1. primary_conninfo

Chỉ định upstream replication server, user và connection parameters. Giữ password trong cơ chế secrets/permissions phù hợp thay vì hard-code plaintext trong file chia sẻ.

### 11.2. application_name

Tên này xuất hiện trong thống kê replication của upstream, giúp nhận diện downstream và đối chiếu với topology inventory.

### 11.3. primary_slot_name

Nếu dùng replication slot, standby yêu cầu upstream giữ WAL cho slot đó. Slot phải tồn tại trên đúng upstream node và được giám sát.

### 11.4. standby.signal

Trên PostgreSQL 12 trở lên, file standby.signal đánh dấu data directory chạy standby mode. Physical backup/restore tooling có thể tạo file này hoặc cấu hình tương đương.

### 11.5. restore_command

Có thể cấu hình restore_command để lấy WAL từ archive khi streaming chưa có segment cần thiết hoặc khi dùng archive-based recovery. Cần bảo đảm archive chain/timeline đúng.

## 12. Replication role và pg_hba.conf

Mỗi sender cần cho phép downstream kết nối replication. Với cascading, cấu hình quyền trên relay cũng quan trọng như trên primary.

### 12.1. Tạo role replication

~~~sql
CREATE ROLE replicator
WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
~~~

Ví dụ chỉ dành cho lab; production nên dùng secret management, TLS và rotation policy.

### 12.2. pg_hba.conf trên primary

~~~conf
hostssl replication replicator 10.20.0.0/16 scram-sha-256
~~~

### 12.3. pg_hba.conf trên relay

Relay cũng cần rule cho downstream subnet/hosts:

~~~conf
hostssl replication replicator 10.30.0.0/16 scram-sha-256
~~~

### 12.4. Hạn chế source addresses

Chỉ cho phép downstream nodes dự kiến. Tránh rule rộng như toàn Internet hoặc mọi IPv4 addresses.

### 12.5. Reload và kiểm tra

Sau khi sửa HBA, reload cấu hình và kiểm tra connection. Dùng pg_hba_file_rules để phát hiện parse errors khi view này có sẵn.

## 13. Physical replication slot và WAL retention

Replication slot giúp upstream biết một consumer còn cần WAL từ vị trí nào. Trong cascading topology, cần hiểu slot nằm trên node nào và bảo vệ filesystem của node đó.

### 13.1. Slot thuộc về upstream trực tiếp

Nếu B kết nối tới A, slot của B (nếu dùng) được quản lý trên A. Nó không tự động là slot trên P.

### 13.2. Slot ngăn WAL cần thiết bị recycle

Khi B bị disconnect, slot có thể giữ WAL trên A cho tới khi B quay lại hoặc slot bị xử lý. Điều này giúp tránh phải rebuild standby sau một outage ngắn.

### 13.3. Slot có thể làm đầy disk

Nếu consumer mất kết nối lâu, retained WAL có thể tăng liên tục. Theo dõi pg_replication_slots, pg_wal disk usage và giới hạn retention phù hợp version.

### 13.4. max_slot_wal_keep_size

Tham số này có thể giới hạn WAL giữ bởi replication slots trong các phiên bản hỗ trợ. Khi vượt giới hạn, slot có thể mất khả năng tiếp tục streaming và standby phải lấy lại WAL từ archive hoặc được reseed.

### 13.5. Slot không thay archive

Slot phục vụ consumer cụ thể trên upstream; WAL archive độc lập cung cấp recovery path và có thể hỗ trợ rebuild. Cần cả hai nếu yêu cầu durability/DR cần đến.

## 14. WAL retention khi có nhiều tầng

Mỗi hop có retention boundary riêng.

~~~text
P --slot A--> A --slot B--> B
                     |
                     +--slot C--> C
~~~

### 14.1. P giữ WAL cho A

Nếu A ngắt kết nối, slot A trên P có thể giữ WAL mà A chưa nhận.

### 14.2. A giữ WAL cho B/C

A phải giữ các segments mà B/C cần. Slot B/C nằm trên A và có thể làm WAL của A tăng.

### 14.3. Retention không cộng đơn giản theo số tầng

Mỗi node có WAL generation/retention state riêng. Disk planning phải đo WAL volume và outage duration trên từng sender.

### 14.4. Archive có thể cứu một số gap

Nếu downstream có restore_command và archive đầy đủ, nó có thể lấy segments từ archive khi streaming upstream không còn giữ chúng, theo timeline/recovery configuration.

### 14.5. Theo dõi slot inactive

Slot inactive lâu ngày cần owner và expiry/recovery plan. Không drop slot chỉ để giải phóng disk nếu chưa xác định consumer và khả năng rebuild.

## 15. max_wal_senders và connection budgeting

Một sender có giới hạn số replication connections đồng thời. Cascading phân tán các connections nhưng không làm tổng số connections biến mất.

### 15.1. Tính theo từng sender

Với topology P→A,D,E và A→B,C, P cần sender slots cho A/D/E; A cần slots cho B/C, cộng backup/maintenance connections phù hợp.

### 15.2. Dự trù reconnect/failover

Giữ headroom cho standby reconnect, basebackup và thao tác rebuild. Nếu max_wal_senders vừa khít với số clients bình thường, failover có thể không đủ slot.

### 15.3. max_connections không thay max_wal_senders

Replication connections được quản lý bằng các parameters riêng. Tăng max_connections không giải quyết thiếu WAL sender slots.

### 15.4. Mỗi node cần budget riêng

Relay vừa có app read sessions, background jobs và replication senders. Tính max_connections, pool size, WAL senders, workers và OS limits cùng nhau.

### 15.5. Đừng tăng mọi giới hạn vô hạn

Mỗi process/connection tiêu thụ memory, file descriptors và CPU. Đo peak concurrency trước khi tăng.

## 16. Monitoring trên primary và relay

pg_stat_replication hiển thị các WAL sender connections trực tiếp từ node đang query. Trên P, view cho thấy A/D/E; trên A, view cho thấy B/C.

~~~sql
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
FROM pg_stat_replication
ORDER BY application_name;
~~~

### 16.1. View không hiển thị toàn cây từ một node

Query trên P không tự liệt kê B/C nếu chúng kết nối tới A. Muốn biết trạng thái B/C, query pg_stat_replication trên A hoặc thu thập metrics từ từng node.

### 16.2. sent_lsn

Vị trí WAL sender đã gửi tới client theo view/state. Dùng cùng write/flush/replay positions để hiểu giai đoạn lag.

### 16.3. write_lsn và flush_lsn

Giúp phân biệt WAL đã được nhận/ghi và WAL đã flush bền vững trên standby theo trạng thái báo cáo.

### 16.4. replay_lsn

Cho biết tiến độ WAL đã được replay. Read queries trên standby nhìn thấy trạng thái tới mức replay phù hợp, không chỉ tới receive position.

### 16.5. Lag intervals có thể NULL

Các lag time columns là estimates và có thể NULL khi idle hoặc không có sample thích hợp. Dùng LSN deltas, timestamps và application metrics bổ sung.

## 17. Monitoring trên standby receiver

Trên standby, pg_stat_wal_receiver mô tả kết nối receiver hiện tại.

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time,
    slot_name,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
~~~

### 17.1. sender_host

Giúp xác nhận standby đang nhận WAL từ upstream dự kiến. Sau reparenting, đây là một bằng chứng hữu ích.

### 17.2. written và flushed positions

Phân biệt WAL đã ghi vào local buffers/files với WAL đã flush. Đối chiếu với sender-side stats khi điều tra network/disk lag.

### 17.3. last message times

Nếu message receipt time cũ, kiểm tra upstream availability, network, authentication, timeout và receiver logs.

### 17.4. slot_name

Xác nhận slot đang dùng nếu có. Nếu NULL, standby có thể không dùng slot và phụ thuộc wal_keep_size/archive retention.

### 17.5. Một snapshot không đủ

Thu thập samples theo thời gian để phân biệt transient pause với backlog đang tăng.

## 18. Đo lag theo LSN

Lag theo bytes có thể tính gần đúng bằng hiệu giữa current WAL LSN ở upstream và replay LSN trên downstream phù hợp.

~~~sql
-- Trên upstream
SELECT pg_current_wal_lsn() AS current_lsn;

-- Trên standby
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn;
~~~

### 18.1. Receive lag

So sánh upstream send/current position với receive position để đánh giá network/receiver path.

### 18.2. Replay lag

So sánh receive position với replay position để đánh giá apply backlog. Nếu receive nhanh nhưng replay chậm, có thể là CPU, disk, conflicts hoặc replay workload.

### 18.3. LSN difference

pg_wal_lsn_diff(lsn1, lsn2) trả chênh lệch bytes giữa hai LSN. So sánh chỉ có ý nghĩa khi các LSN thuộc đúng replication timeline/stream.

### 18.4. Byte lag không bằng thời gian lag

Ở write rate cao, 1 GB WAL có thể đại diện vài giây; ở write rate thấp, cùng 1 GB có thể đại diện nhiều giờ. Cần kết hợp WAL generation rate và timestamps.

### 18.5. Cumulative lag qua cascade

Nếu P→A lag 2 giây và A→B lag 3 giây, B có thể trễ hơn P khoảng 5 giây hoặc khác tùy thời điểm/queue; không cộng các snapshot rời rạc như một phép đo chính xác.

## 19. Theo dõi topology trên nhiều nodes

Vì các views là local, cần thu thập thông tin từng node và ghép thành topology inventory.

### 19.1. Inventory tĩnh

Lưu node ID, role, upstream host, downstream list, region, availability zone, replication slot, application_name và owner.

### 19.2. Inventory động

Lấy sender/receiver state từ từng node, xác minh kết nối thực tế khớp topology dự kiến.

### 19.3. Detect reparenting

Sau failover, sender_host trên receiver có thể thay đổi. Alert nếu upstream không nằm trong approved topology.

### 19.4. Correlate LSN

Lưu current/replay LSN và timestamps cho từng hop cùng sample time. Dùng UTC để so sánh cross-region.

### 19.5. Không suy node khỏe chỉ vì TCP connect được

Replication protocol, WAL availability, timeline compatibility và replay progress mới chứng minh stream đang hoạt động.

## 20. Capacity planning cho relay nodes

Relay là một điểm trung gian có thể chịu đồng thời WAL receive, replay, WAL send và read workload.

### 20.1. Network ingress

A nhận WAL từ P. Ingress phải theo kịp peak WAL generation của P, cộng burst/reconnect behavior.

### 20.2. Network egress

A gửi WAL tới B/C. Tổng egress phụ thuộc số downstream và cách các streams được truyền.

### 20.3. Disk I/O

A ghi WAL nhận được, replay data pages và đọc WAL để gửi downstream. Disk latency cao có thể ảnh hưởng cả replay và sender throughput.

### 20.4. CPU

WAL processing, checksums, encryption, compression ở tầng transport/tooling và read queries đều tiêu thụ CPU.

### 20.5. Headroom và isolation

Đừng cấp toàn bộ capacity cho read traffic. Giữ headroom cho WAL replay, catch-up sau outage và backup operations.

## 21. Phân phối read traffic trên hot standbys

Hot standby có thể phục vụ SELECT để giảm tải primary, nhưng read routing cần awareness về lag và query semantics.

### 21.1. Application-level routing

Ứng dụng có thể dùng hai connection pools: write pool trỏ primary, read pool trỏ tới replicas được chọn. Cách này cho phép quyết định theo endpoint/consistency.

### 21.2. Proxy hoặc middleware

Một proxy có thể health-check replicas và phân phối connections/queries theo policy. Kiểm tra proxy có hiểu transaction boundaries và read/write classification hay chỉ route ở mức connection.

### 21.3. PgBouncer

PgBouncer tập trung vào connection pooling. Bản thân PgBouncer không tự động phân tích mọi SQL để tách SELECT sang replica và writes sang primary; thường cần database/user routing hoặc app logic.

### 21.4. Pgpool-II và query routing

Một số middleware như Pgpool-II hỗ trợ load balancing reads theo cấu hình. Cần hiểu behavior với transactions, prepared statements, temp tables, functions và session state.

### 21.5. Không coi mọi SELECT là an toàn để route

SELECT có thể gọi function có side effects/volatile behavior, phụ thuộc transaction state hoặc cần read-your-writes. Chỉ route theo semantics thực tế của ứng dụng.

## 22. Read-after-write consistency

Khi app ghi vào primary rồi đọc ngay trên standby, standby có thể chưa replay commit đó.

### 22.1. Eventual consistency

Read replica thường phản ánh dữ liệu sau một độ trễ. Ứng dụng cần chấp nhận stale reads cho các use cases phù hợp.

### 22.2. Read-your-writes

Sau một write, request cần đọc dữ liệu mới có thể tiếp tục dùng primary trong một khoảng thời gian hoặc chờ standby replay tới LSN của transaction.

### 22.3. LSN token

Ứng dụng có thể lấy một LSN sau commit trên primary và truyền yêu cầu consistency tới router. Router chờ replica replay LSN đạt/qua mốc cần thiết hoặc fallback sang primary.

### 22.4. Transaction consistency

Không chia các statements của một transaction qua nhiều servers. Một transaction cần cùng database session/transaction context.

### 22.5. Monotonic reads

Nếu một user được route qua các replicas có lag khác nhau, họ có thể thấy dữ liệu mới rồi lại thấy dữ liệu cũ hơn. Sticky routing hoặc LSN-aware selection có thể giúp.

## 23. Chọn replica cho mỗi truy vấn

Replica selection có thể dựa trên health, lag, latency, capacity và region.

### 23.1. Health

Replica phải accept connections, ở trạng thái recovery phù hợp, không quá tải và có WAL receiver hoạt động theo policy.

### 23.2. Lag threshold

Loại replica có replay lag vượt giới hạn use case. Không dùng một threshold duy nhất cho tất cả endpoints.

### 23.3. Query latency

Một replica gần ứng dụng có network latency thấp nhưng có thể thiếu CPU/cache. Đo end-to-end query latency thay vì chỉ ping.

### 23.4. Weighted routing

Có thể gán weights theo CPU/memory/storage capacity và số connections tối đa. Recompute khi node degraded.

### 23.5. Fallback

Nếu tất cả read replicas không đủ freshness hoặc unhealthy, router cần policy: fallback primary, trả lỗi/retry hay phục vụ stale data. Business semantics quyết định.


## 24. Hot standby conflicts với WAL replay

Read queries trên standby có thể giữ snapshot hoặc lock trong khi recovery cần áp dụng WAL. Nếu hai hoạt động xung đột, PostgreSQL phải chọn giữa tiếp tục query và giữ replay tiến lên.

### 24.1. Cleanup conflict

VACUUM trên upstream có thể cleanup tuple versions mà một query dài trên standby vẫn cần đọc. Khi WAL record được replay, standby có thể phải cancel query để áp dụng thay đổi.

### 24.2. Lock conflict

DDL hoặc lock record từ upstream có thể xung đột với query/lock đang tồn tại trên standby. Recovery có thể chờ trong giới hạn cấu hình rồi cancel query.

### 24.3. Buffer pin conflict

Một query giữ buffer pin lâu có thể làm recovery chờ thao tác cần thay đổi page đó.

### 24.4. Theo dõi conflict counters

~~~sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_stat_database_conflicts
ORDER BY datname;
~~~

Các counters cho biết số lần query bị cancel do recovery conflicts theo database, không phải mọi loại lỗi query.

### 24.5. Đánh đổi giữa freshness và query continuity

Nếu recovery bị trì hoãn quá lâu, standby lag tăng. Nếu query bị cancel thường xuyên, read workload kém ổn định. Chọn policy theo use case và đo cả hai.

## 25. max_standby_streaming_delay và max_standby_archive_delay

Các tham số này điều khiển thời gian recovery có thể chờ khi WAL replay xung đột với standby queries.

### 25.1. max_standby_streaming_delay

Giới hạn tổng thời gian có thể trì hoãn replay do conflicts với WAL nhận qua streaming trong khoảng xử lý tương ứng. Đây không phải giới hạn thời gian chạy riêng cho từng query.

### 25.2. max_standby_archive_delay

Điều khiển thời gian chờ khi replay WAL lấy từ archive gặp conflict. Archive recovery có thể có behavior khác streaming.

### 25.3. Giá trị thấp

Recovery ưu tiên tiến lên nhanh hơn; query dài có thể bị cancel sớm. Phù hợp khi freshness/replication lag quan trọng hơn read query continuity.

### 25.4. Giá trị cao

Cho query thêm thời gian hoàn tất nhưng có thể tăng replay lag. Nếu downstream tiếp tục nhận WAL, backlog có thể tăng.

### 25.5. Không dùng giá trị vô hạn tùy tiện

Một query analytics có thể kéo dài nhiều giờ. Nếu để recovery chờ vô hạn, standby có thể trở nên quá cũ để đáp ứng failover/read consistency requirements.

## 26. hot_standby_feedback và bloat trên upstream

hot_standby_feedback cho phép standby gửi thông tin về snapshot horizon tới upstream để giảm cleanup conflicts.

### 26.1. Mục tiêu

Upstream có thể giữ lại một số tuple versions mà standby queries còn cần, giảm việc cancel queries do cleanup conflict.

### 26.2. Trade-off

Giữ dead tuples lâu hơn có thể làm tăng bloat trên upstream. Một query dài trên standby có thể ảnh hưởng vacuum cleanup của node gửi.

### 26.3. Trong cascading topology

Feedback và cleanup horizon cần được hiểu theo từng replication hop và PostgreSQL version. Không giả định bật trên leaf sẽ tự động truyền đúng semantics xuyên toàn cây tới primary trong mọi topology.

### 26.4. Theo dõi xmin horizon

Kiểm tra backend_xmin, replication slot xmin và vacuum progress trên các upstream nodes. Tìm session/standby đang giữ snapshot cũ.

### 26.5. Chọn theo workload

Read replicas phục vụ query ngắn có thể không cần feedback. Replica phục vụ analytics dài có thể cần policy khác, hoặc tách workload sang replica riêng để giới hạn tác động.

## 27. Delayed standby và cascading

Một standby có thể được cấu hình cố ý trì hoãn replay để tạo thời gian phát hiện một số lỗi logic.

### 27.1. recovery_min_apply_delay

Tham số recovery_min_apply_delay yêu cầu standby chờ một khoảng thời gian trước khi replay commit records theo semantics của PostgreSQL. Nó không phải một backup lịch sử đầy đủ.

### 27.2. Dùng làm cửa sổ phát hiện

Nếu thao tác DROP nhầm được replay trên primary, delayed standby có thể chưa áp dụng ngay. Operator có thời gian phát hiện và dừng/điều tra theo runbook.

### 27.3. Không bảo vệ mọi dạng corruption

Một lỗi được phát hiện muộn hơn delay window vẫn có thể đã replay. Delayed standby không thay base backup, WAL archive và PITR.

### 27.4. Tác động tới downstream

Nếu delayed standby làm upstream cho downstream nodes, các downstream cũng nhận state từ một relay có replay delay. Lag có thể cộng thêm theo tầng.

### 27.5. Không dùng delayed replica cho read freshness nghiêm ngặt

Một node cố ý chậm không phù hợp endpoint yêu cầu dữ liệu mới nhất. Đặt nó vào pool riêng hoặc chỉ dùng cho recovery/forensic purpose.

## 28. Synchronous và asynchronous replication qua từng hop

Streaming replication mặc định thường là asynchronous. Synchronous replication có thể được cấu hình để sender chờ acknowledgement từ synchronous standby theo semantics của từng connection.

### 28.1. Async replication

Primary không chờ standby flush/apply WAL trước khi trả commit response theo policy async. Điều này thường giảm commit latency nhưng có thể mất một số giao dịch chưa được truyền bền vững khi primary gặp sự cố.

### 28.2. Sync replication

Primary có thể chờ remote acknowledgement theo synchronous_commit và synchronous_standby_names. Chế độ chờ cụ thể (remote write, flush hoặc apply) ảnh hưởng durability và latency.

### 28.3. Mỗi hop có acknowledgement semantics riêng

Nếu topology có P→A→B, việc P chờ A không tự động chứng minh B đã replay transaction. Nếu cần durability ở nhiều tầng, phải thiết kế và xác minh synchronous relationships/acknowledgement ở từng hop.

### 28.4. Cascading không tự động tạo end-to-end synchronous guarantee

Không suy ra RPO 0 cho toàn cây chỉ từ một cấu hình synchronous ở primary. Xác định node được chọn làm synchronous standby, mức acknowledgement và failure domain được bảo vệ.

### 28.5. Network partition và availability

Nếu primary cần synchronous standby nhưng standby/network không đáp ứng, writes có thể chờ theo cấu hình. Cần chính sách quorum/failover và business decision cho availability trade-off.

## 29. Failover của relay standby

Nếu relay A gặp sự cố, downstream B/C có thể mất WAL source dù primary P vẫn hoạt động.

### 29.1. Phát hiện sự cố

Theo dõi receiver/sender health, heartbeat, replay lag, disk, host health và network. Phân biệt A down với một downstream đơn lẻ mất kết nối.

### 29.2. Giữ A fenced nếu nghi lỗi dữ liệu

Nếu A bị corruption hoặc compromise, không tự động cho downstream tiếp tục tin A. Chọn upstream sạch đã được xác minh.

### 29.3. Reparent downstream

B/C có thể được cấu hình lại để nhận WAL từ P hoặc một relay khác nếu timeline/WAL positions phù hợp. Cần đảm bảo upstream mới có đủ WAL để downstream bắt kịp.

### 29.4. WAL gap

Nếu upstream mới không còn giữ segment cần thiết, downstream có thể lấy từ archive nếu cấu hình hỗ trợ và archive chain đầy đủ; nếu không, cần reseed từ base backup.

### 29.5. Thứ tự recovery

Ưu tiên khôi phục WAL path cho node critical và downstream phục vụ production reads. Ghi rõ thứ tự và capacity để tránh mọi nodes cùng tải base backup gây nghẽn.

## 30. Failover của primary và timeline change

Khi primary P mất, một standby được promote thành primary mới. Cascading descendants cần được chuyển theo timeline mới.

### 30.1. Chọn node promote

Chọn standby có dữ liệu mới nhất phù hợp policy, health tốt và đủ capacity. Đối chiếu received/flushed/replayed LSN và synchronous acknowledgement state.

### 30.2. Fence primary cũ

Đảm bảo primary cũ không tiếp tục nhận writes. DNS change đơn lẻ không đủ để loại bỏ stale clients hoặc connections.

### 30.3. Timeline history

Promotion tạo timeline mới. Các standbys cần timeline history/WAL phù hợp để theo nhánh mới; không giả định mọi node tự chuyển upstream đúng cách.

### 30.4. Reparent direct và cascaded standbys

Cập nhật primary_conninfo trên relay/direct standbys theo topology mới. Sau đó xác nhận downstream vẫn nhận WAL qua relay mới.

### 30.5. Rewind hoặc reseed

Nếu node cũ đã diverge, có thể cần pg_rewind khi prerequisites/WAL đủ; nếu không, rebuild standby từ base backup mới. Không copy data directory thủ công giữa hai nhánh.

## 31. Reparenting: chuyển downstream sang upstream khác

Reparenting là thay đổi nguồn WAL của standby. Đây là thay đổi topology, không chỉ sửa hostname.

### 31.1. Kiểm tra compatibility

Xác nhận target upstream cùng lineage/timeline có thể phục vụ WAL mà downstream cần. Nếu target ở timeline khác hoặc thiếu WAL, cần recovery/reseed strategy.

### 31.2. Sửa primary_conninfo

Cập nhật upstream host/port/user/TLS parameters bằng cơ chế cấu hình phù hợp. Giữ thông tin credentials trong secret management.

### 31.3. Cập nhật slot

Tạo/kiểm tra slot trên upstream mới nếu downstream sử dụng slot. Không để primary_slot_name trỏ tới slot chỉ tồn tại trên node cũ.

### 31.4. Xác nhận receiver

Kiểm tra pg_stat_wal_receiver sender_host/slot_name và log để chắc chắn node đang kết nối đúng upstream.

### 31.5. Xác nhận sender

Trên upstream mới, kiểm tra pg_stat_replication để thấy downstream, state và replay progress. Cập nhật topology inventory.

## 32. Failback sau khi relay hoặc primary cũ trở lại

Node cũ quay lại không có nghĩa nó tự động trở thành upstream hợp lệ.

### 32.1. Không tự động giành lại primary role

Tránh failback chỉ vì node cũ khỏe lại. Cần xác nhận authoritative primary, timeline và data divergence.

### 32.2. Node cũ có thể trở thành standby

Dùng pg_rewind nếu đủ điều kiện, hoặc reseed từ base backup của primary mới. Giữ node cũ fenced cho tới khi hoàn tất.

### 32.3. Downstream topology

Có thể giữ relay mới làm upstream hoặc chuyển descendants về relay cũ sau khi nó bắt kịp. Quyết định dựa trên capacity, region và failure domain.

### 32.4. Thay đổi từng nhóm

Reparent một nhóm downstream, theo dõi lag/health rồi tiếp tục. Tránh thay đổi đồng loạt mà không có rollback path.

### 32.5. Ghi nhận topology cuối

Cập nhật inventory, alerts, backup schedules, slot owners, routing policy và runbooks sau failback.

## 33. Network và latency planning

Cascading thường được dùng để phân phối WAL qua mạng, vì vậy network design là một phần của database architecture.

### 33.1. Bandwidth theo WAL generation

Đo WAL bytes/sec theo giờ cao điểm và burst. Mỗi hop phải có throughput đủ lớn để truyền stream và catch up sau outage.

### 33.2. Network RTT

RTT ảnh hưởng replication feedback/acknowledgement và sync commit latency. Async replication vẫn chịu throughput/latency của network trong catch-up.

### 33.3. Cross-region egress

Một relay trong region đích có thể giảm số kết nối xuyên region từ primary, nhưng relay phải có đủ egress tới các downstream trong region đó.

### 33.4. Packet loss và reconnect

Packet loss, firewall idle timeout và NAT behavior có thể làm replication disconnect. Kiểm tra TCP keepalive, wal_sender_timeout và network devices.

### 33.5. TLS overhead

TLS bảo vệ WAL stream trên network không tin cậy, nhưng tiêu thụ CPU. Dùng certificate validation phù hợp và theo dõi handshake/reconnect failures.

## 34. Storage và WAL disk planning

Mỗi sender cần đủ storage để giữ WAL theo retention policy và outage tolerance.

### 34.1. WAL generation rate

Ước lượng bytes WAL mỗi giây trong peak period. Dùng pg_stat_wal hoặc metrics của backup/monitoring tool theo version.

### 34.2. Outage window

Nếu downstream có thể mất kết nối 2 giờ, tính lượng WAL cần giữ trong khoảng đó cộng buffer và burst.

### 34.3. Replication slot retention

Slot có thể giữ WAL lâu hơn dự kiến. Cảnh báo theo retained_wal/slot age và filesystem free space.

### 34.4. wal_keep_size không phải giới hạn disk cứng

Tham số này giữ tối thiểu lượng WAL nhất định cho standby; replication slot/archive có thể khiến WAL giữ nhiều hơn. Theo dõi thực tế.

### 34.5. Disk full là incident nghiêm trọng

Nếu pg_wal đầy, PostgreSQL có thể ngừng hoạt động hoặc không thể tiếp tục ghi. Có runbook xử lý slot, archive, storage và downstream trước khi tới ngưỡng nguy hiểm.

## 35. Backup và cascading topology

Replication hỗ trợ availability, nhưng backup vẫn là đường phục hồi độc lập.

### 35.1. Backup từ primary

Backup từ primary có thể tạo thêm I/O/network load và cần tránh giờ cao điểm. Phù hợp khi primary đủ headroom.

### 35.2. Backup từ standby

Một số công cụ hỗ trợ lấy base backup từ standby. Điều này có thể giảm load trên primary nhưng làm tăng I/O trên relay/standby và cần xem tool/version limitations.

### 35.3. WAL archive độc lập

Giữ WAL archive ở storage tách biệt với nodes. Nếu relay bị mất, archive có thể giúp downstream recover/reseed theo chain phù hợp.

### 35.4. Backup catalog

Ghi node nguồn, timeline, LSN, backup ID, WAL coverage và version. Với cascading, biết backup được lấy từ node nào rất quan trọng.

### 35.5. Restore drill

Thử restore độc lập khỏi topology hiện tại. Không kết luận DR đạt chỉ vì replicas đang streaming.

## 36. Phân phối workload ngoài SELECT

Standby có thể offload một số công việc read-mostly, nhưng workload phải tương thích với recovery mode.

### 36.1. Analytics/reporting

Các query tổng hợp dài có thể dùng replica riêng, tránh ảnh hưởng primary. Tuy nhiên, chúng có thể tạo hot standby conflicts và lag.

### 36.2. Backup/exports

Logical exports từ standby có thể giảm load primary trong một số trường hợp. Kiểm tra snapshot semantics, version, connection load và replica lag.

### 36.3. Search indexing/ETL

Job đọc incremental data có thể chạy trên replica nếu chấp nhận consistency/lag. Consumer cần checkpoint/idempotency và xử lý replica switch.

### 36.4. Read-only BI

Tách BI replicas khỏi user-facing read replicas giúp kiểm soát query duration và resource contention.

### 36.5. Không chạy write-side maintenance trên standby

DDL/DML thông thường không thể thực hiện trên hot standby. Các thao tác schema phải đi qua primary và được replay.

## 37. Security cho cascading replication

Mỗi hop là một kết nối có quyền đọc WAL của cluster.

### 37.1. Replication role tối thiểu

Role cần LOGIN và REPLICATION, không cần SUPERUSER chỉ để stream WAL.

### 37.2. Network segmentation

Chỉ mở port database giữa các upstream/downstream nodes và monitoring/bastion cần thiết.

### 37.3. TLS và certificate validation

Dùng TLS theo policy, xác minh server identity và quản lý certificate rotation. Tránh sslmode permissive trên network không tin cậy.

### 37.4. Secret rotation

Mỗi downstream cần cập nhật credential theo lịch. Kiểm tra reconnect sau rotation để tránh đứt replication.

### 37.5. Audit và access

Theo dõi replication connections, role usage, configuration changes và slot operations. Không cho read application roles quyền replication.

## 38. Monitoring và alerting theo mục tiêu

Không nên chỉ alert khi một standby disconnect. Cần alert theo mức độ tác động đến RPO, RTO và read freshness.

| Metric | Alert khi | Tác động |
|---|---|---|
| Receiver disconnected | Vượt thời gian reconnect cho phép | WAL stream ngừng |
| Replay lag | Vượt freshness SLO | Read stale/failover risk |
| Sender slots | Gần max_wal_senders | Không nhận thêm downstream |
| Slot retained WAL | Tăng nhanh/disk thấp | Disk exhaustion |
| WAL archive lag | Vượt RPO buffer | Recovery point bị lùi |
| Hot standby conflicts | Tăng đột biến | Read query cancellations |
| Relay CPU/disk/network | Saturation kéo dài | Fan-out bottleneck |
| Query latency | Vượt read SLO | User impact |
| Timeline mismatch | Node ở nhánh không mong muốn | Replication không thể tiếp tục |
| Fencing state | Primary cũ còn reachable/writable | Split-brain risk |

### 38.1. Alert theo từng hop

Mỗi sender/receiver pair cần metrics riêng. Một dashboard chỉ hiển thị P→A có thể bỏ qua B/C đang lag nặng.

### 38.2. Alert theo trend

Một lag tăng liên tục nguy hiểm hơn một spike ngắn. Theo dõi rate-of-change, duration và WAL generation.

### 38.3. Alert theo business freshness

Nếu dashboard báo cáo chấp nhận lag 5 phút còn user profile chỉ chấp nhận 1 giây, dùng thresholds riêng.

### 38.4. Alert disk trước khi hết chỗ

Kết hợp filesystem free space, WAL retained bytes, slot inactivity và growth rate để có thời gian xử lý.

### 38.5. Kiểm tra alert path

Alert phải tới đúng on-call và có runbook; metric không được theo dõi bởi người vận hành không thể hành động.

## 39. Troubleshooting: downstream không kết nối relay

### 39.1. Kiểm tra receiver state

Xem pg_stat_wal_receiver và PostgreSQL logs trên downstream để biết connection/authentication/streaming state.

### 39.2. Kiểm tra sender trên relay

Xem pg_stat_replication trên relay. Nếu không có row, kiểm tra HBA, network, max_wal_senders và replication role.

### 39.3. Kiểm tra primary_conninfo

Xác minh host, port, user, application_name, TLS mode và secret. Tránh để endpoint trỏ tới primary cũ.

### 39.4. Kiểm tra slot

Nếu primary_slot_name được cấu hình, xác nhận slot tồn tại trên đúng relay và chưa bị invalidated/lost WAL.

### 39.5. Kiểm tra timeline/WAL availability

Downstream cần WAL liên tục trên đúng timeline hoặc có archive recovery phù hợp. Nếu thiếu segment, cần archive restore hoặc reseed.

## 40. Troubleshooting: replica lag tăng dần

### 40.1. Phân biệt receive lag và replay lag

Nếu receive lag tăng, xem network/upstream sender/receiver throughput. Nếu replay lag tăng, xem disk/CPU/conflicts và query workload.

### 40.2. Relay egress saturation

Một relay có nhiều downstream có thể không gửi kịp WAL. Đo network egress và số sender sessions.

### 40.3. Disk latency

Replay và WAL reads cần disk throughput/latency phù hợp. Kiểm tra IOPS, queue depth và storage saturation.

### 40.4. Hot standby queries

Query dài có thể làm recovery chờ/cancel theo conflict policy. Xem pg_stat_database_conflicts và active queries.

### 40.5. WAL burst

Bulk load, index build hoặc batch updates có thể tạo WAL burst. Đánh giá catch-up capacity và peak, không chỉ average write rate.

## 41. Troubleshooting: read pool trả dữ liệu cũ

### 41.1. Xác định replica được chọn

Ghi host/application_name, upstream chain và replay LSN khi query chạy.

### 41.2. Kiểm tra consistency requirement

Có phải request cần read-after-write? Nếu có, route primary hoặc chờ LSN token.

### 41.3. Kiểm tra routing policy

Proxy có thể chọn replica healthy về TCP nhưng lag quá mức. Thêm health/lag checks và fallback behavior.

### 41.4. Sticky sessions

Nếu user cần monotonic reads, giữ họ trên cùng replica hoặc đảm bảo replica được chọn có replay position không lùi so với token trước.

### 41.5. Không che lỗi bằng retry vô hạn

Nếu replica không catch up, trả degraded response/fallback theo policy và alert. Retry không giới hạn có thể làm tăng load.

## 42. Lab: thiết kế topology primary → relay → leaves

Lab nên chạy trên các VM/container PostgreSQL cô lập, cùng major version và network riêng. Không dùng production credentials/data.

~~~text
Primary P
   |
   v
Relay A
  / \
 v   v
B   C
~~~

### 42.1. Chuẩn bị node

Tạo bốn data directories/instances với ports và storage riêng. Ghi host/port, role, upstream và downstream.

### 42.2. Cấu hình primary

Đặt wal_level phù hợp, max_wal_senders và max_replication_slots đủ cho A cùng lab connections. Tạo replication role và HBA rule giới hạn source.

### 42.3. Tạo standby A

Dùng pg_basebackup từ P, cấu hình primary_conninfo tới P và khởi động A ở standby mode. Xác nhận pg_stat_wal_receiver trên A.

### 42.4. Cấu hình A làm sender

Đặt max_wal_senders trên A, tạo HBA rule cho B/C và xác nhận network route. Nếu dùng slots, tạo slots trên A.

### 42.5. Tạo B/C

Lấy base backup từ một nguồn tương thích theo lab procedure, cấu hình primary_conninfo trỏ tới A và start B/C. Kiểm tra sender state trên A và receiver state trên B/C.

## 43. Lab: quan sát WAL qua từng hop

### 43.1. Tạo write workload trên P

~~~sql
CREATE TABLE public.replication_lab (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO public.replication_lab(payload)
SELECT repeat('x', 200)
FROM generate_series(1, 10000);
~~~

### 43.2. Kiểm tra P→A

Trên P, xem pg_stat_replication và xác định application_name của A. Ghi sent/write/flush/replay LSN.

### 43.3. Kiểm tra A→B/C

Trên A, query pg_stat_replication và ghi các positions của B/C. Không tìm B/C trong view trên P nếu chúng kết nối trực tiếp tới A.

### 43.4. Kiểm tra receiver

Trên B/C, query pg_stat_wal_receiver để xác nhận sender_host là A.

### 43.5. So sánh replay

Chạy SELECT trên từng standby để xác nhận rows đã replay. Ghi timestamps và LSN samples cùng thời điểm.

## 44. Lab: phân phối read queries

### 44.1. Tạo read-only endpoints

Cấu hình một endpoint primary/write và endpoints read cho B/C. Không dùng chung connection string khiến ứng dụng không biết node nào đang phục vụ.

### 44.2. Kiểm tra node thực tế

~~~sql
SELECT
    inet_server_addr(),
    inet_server_port(),
    pg_is_in_recovery();
~~~

Ứng dụng/test client có thể log endpoint để xác nhận query được route tới đúng standby.

### 44.3. Kiểm tra read-only

Thử SELECT trên standby. DML phải bị từ chối trong recovery state; không dùng DML để kiểm tra read pool trên production.

### 44.4. Thử read-after-write

Ghi row trên P rồi đọc ngay trên B. Quan sát có thể chưa thấy row nếu B chưa replay commit. Lặp lại sau khi replay LSN bắt kịp.

### 44.5. Fallback

Giả lập B vượt lag threshold và kiểm tra router chọn C hoặc primary theo policy. Ghi lại latency và consistency behavior.

## 45. Lab: hot standby conflicts

Chỉ dùng lab có dữ liệu thử nghiệm và query duration kiểm soát được.

### 45.1. Tạo workload trên primary

Tạo bảng, nạp rows và chạy UPDATE/DELETE trên P để tạo WAL có cleanup-related records.

### 45.2. Chạy query dài trên standby

Trên B, mở transaction đọc snapshot và giữ query có chủ đích trong thời gian ngắn. Quan sát conflict behavior khi upstream cleanup được replay.

### 45.3. Theo dõi conflicts

Query pg_stat_database_conflicts trước/sau. Ghi counter thay đổi và logs liên quan.

### 45.4. Thử thay đổi delay

Trong lab, thay max_standby_streaming_delay và lặp lại workload. Quan sát trade-off query cancellation và replay lag.

### 45.5. Thử hot_standby_feedback

Bật/tắt trong lab, theo dõi conflicts và vacuum behavior upstream. Không dùng một bài lab nhỏ để suy ra mức bloat production.

## 46. Lab: failover và reparenting

Lab này cần topology cô lập và dữ liệu có thể tạo lại.

### 46.1. Ghi baseline

Lưu timeline/LSN, sender/receiver state, upstream names và slot inventory của P/A/B/C.

### 46.2. Mô phỏng relay outage

Dừng A trong lab. Quan sát B/C receiver disconnect và replay positions ngừng tăng.

### 46.3. Reparent leaf

Cấu hình B/C kết nối tới P hoặc relay thay thế nếu WAL/timeline compatibility cho phép. Kiểm tra slot trên upstream mới.

### 46.4. Xác nhận catch-up

Trên upstream mới, kiểm tra pg_stat_replication; trên B/C kiểm tra pg_stat_wal_receiver. Chờ replay LSN bắt kịp theo workload.

### 46.5. Mô phỏng primary failover

Promote một standby theo runbook lab, fence P cũ, reparent relay/leaf nodes và xác nhận timeline. Không chạy promotion thử trên cluster production.

## 47. Các hiểu lầm thường gặp

1. **“Cascading replication tự động load balance SELECT.”** Sai; nó relay WAL, query routing cần lớp riêng.
2. **“Một primary vẫn phải gửi trực tiếp tới mọi leaf.”** Sai; leaf có thể nhận từ relay.
3. **“Relay chỉ cần cấu hình primary.”** Sai; relay cần sender capacity/HBA/slots cho downstream.
4. **“pg_stat_replication trên primary hiển thị toàn cây.”** Sai; view hiển thị direct sender connections của node đang query.
5. **“WAL receive LSN bằng replay LSN.”** Sai; standby có thể nhận WAL nhưng chưa replay.
6. **“Một hop không tăng lag.”** Sai; network, disk và replay queue mỗi hop đều có thể tăng lag.
7. **“Replication slot không có chi phí.”** Sai; slot có thể giữ WAL và làm đầy disk.
8. **“wal_keep_size là giới hạn WAL tuyệt đối.”** Sai; slot/archive có thể giữ thêm WAL.
9. **“hot_standby_feedback không ảnh hưởng primary.”** Sai; có thể trì hoãn cleanup và tăng bloat.
10. **“Tăng max_standby_streaming_delay luôn tốt.”** Sai; query ít bị cancel nhưng replay lag có thể tăng.
11. **“Mọi SELECT đều có thể route sang standby.”** Sai; read-after-write, volatile functions và transaction semantics cần xét.
12. **“Synchronous trên primary đảm bảo mọi leaf đã replay.”** Sai; acknowledgement semantics theo từng relationship.
13. **“Standby khỏe về TCP là replication khỏe.”** Sai; cần receiver/sender state, WAL continuity và replay progress.
14. **“Primary failover không ảnh hưởng cascading leaves.”** Sai; descendants có thể cần reparenting/timeline handling.
15. **“Đổi DNS là fencing.”** Sai; stale connections có thể tiếp tục ghi vào primary cũ.
16. **“Standby thay backup/PITR.”** Sai; logical corruption có thể được replay qua mọi tầng.
17. **“Một relay càng nhiều downstream càng tốt.”** Sai; sender, disk, CPU và egress có giới hạn.
18. **“Read replicas không cần capacity cho catch-up.”** Sai; sau outage chúng cần băng thông để replay backlog.
19. **“Lag bytes chuyển trực tiếp thành lag time.”** Sai; cần biết WAL generation rate.
20. **“Có thể reparent sang bất kỳ standby nào.”** Sai; cần timeline/WAL compatibility.
21. **“pg_rewind luôn cứu được node cũ.”** Sai; cần prerequisites và WAL đủ.
22. **“Bật hot_standby_feedback trên leaf chắc chắn truyền horizon xuyên cây.”** Không được giả định; kiểm tra semantics/version từng hop.
23. **“Replica đọc được nghĩa là đã replay hết.”** Sai; query có thể đọc state cũ.
24. **“Backup từ standby không tạo load.”** Sai; backup vẫn dùng CPU, disk và network.
25. **“Cascading là multi-primary.”** Sai; physical standby vẫn là recovery/read-only node.

## 48. Bài tập thực hành

### Bài 1 — Định nghĩa

Cascading replication là gì?

**Đáp án:** Một standby nhận WAL từ upstream và tiếp tục gửi WAL tới downstream standbys.

### Bài 2 — Topology

Trong P→A→B, node nào là upstream trực tiếp của B?

**Đáp án:** A.

### Bài 3 — WAL fan-out

Cascading phân phối thành phần nào?

**Đáp án:** WAL stream.

### Bài 4 — Query routing

PostgreSQL có tự động route mọi SELECT tới hot standbys không?

**Đáp án:** Không; cần application/proxy/middleware routing.

### Bài 5 — Sender

View nào trên node gửi hiển thị direct replication clients?

**Đáp án:** pg_stat_replication.

### Bài 6 — Receiver

View nào trên standby hiển thị WAL receiver state?

**Đáp án:** pg_stat_wal_receiver.

### Bài 7 — Relay config

Parameter nào giới hạn WAL sender processes trên relay?

**Đáp án:** max_wal_senders.

### Bài 8 — WAL level

wal_level nào thường đủ cho physical replication?

**Đáp án:** replica.

### Bài 9 — Downstream upstream

Parameter nào chỉ định upstream connection?

**Đáp án:** primary_conninfo.

### Bài 10 — Application name

application_name giúp ích gì?

**Gợi ý:** Nhận diện standby trong sender statistics.

### Bài 11 — Slot location

Nếu B stream từ A, replication slot của B được quản lý ở đâu?

**Đáp án:** Trên A.

### Bài 12 — Slot risk

Vì sao slot inactive lâu ngày nguy hiểm?

**Đáp án:** Nó có thể giữ WAL và làm đầy disk.

### Bài 13 — wal_keep_size

wal_keep_size có phải giới hạn tuyệt đối cho WAL retention?

**Đáp án:** Không.

### Bài 14 — Lag

Receive LSN và replay LSN khác nhau thế nào?

**Đáp án:** Receive là WAL đã nhận/ghi; replay là WAL đã được áp dụng vào standby state.

### Bài 15 — Local stats

Vì sao query pg_stat_replication trên P không thấy B nếu B kết nối A?

**Đáp án:** View chỉ hiển thị sender connections trực tiếp trên node được query.

### Bài 16 — Read-only

Có thể INSERT trên hot standby không?

**Đáp án:** Không.

### Bài 17 — Read-after-write

Vì sao vừa INSERT trên P có thể chưa SELECT thấy row trên B?

**Gợi ý:** B chưa replay commit WAL.

### Bài 18 — LSN token

Ứng dụng dùng LSN token để làm gì?

**Gợi ý:** Chờ replica replay tới mốc commit cần đọc.

### Bài 19 — PgBouncer

PgBouncer có tự động phân tích SQL để chia SELECT sang replica không?

**Đáp án:** Không; chủ yếu là connection pooling.

### Bài 20 — Hot standby conflict

Cleanup conflict có thể khiến điều gì xảy ra?

**Đáp án:** Query trên standby có thể bị cancel để WAL replay tiếp tục.

### Bài 21 — max_standby_streaming_delay

Đây có phải giới hạn thời gian chạy của mỗi query?

**Đáp án:** Không; nó giới hạn thời gian recovery delay do conflicts trong khoảng xử lý.

### Bài 22 — hot_standby_feedback

Lợi ích và chi phí chính là gì?

**Đáp án:** Giảm query cancellations nhưng có thể tăng bloat upstream.

### Bài 23 — Delayed standby

recovery_min_apply_delay giúp gì?

**Gợi ý:** Tạo cửa sổ trì hoãn replay để phát hiện một số lỗi logic.

### Bài 24 — Synchronous replication

Có thể suy RPO zero cho toàn cascading tree từ sync primary→relay không?

**Đáp án:** Không; phải xác định acknowledgement ở từng hop.

### Bài 25 — Relay outage

Nếu A ngừng hoạt động trong P→A→B, B bị ảnh hưởng thế nào?

**Đáp án:** B mất WAL source cho tới khi A trở lại hoặc B được reparent.

### Bài 26 — Reparent

Trước khi đổi B từ A sang P, cần kiểm tra gì?

**Gợi ý:** Timeline, WAL availability, slot, credentials và upstream capacity.

### Bài 27 — Timeline

Promotion tạo ra điều gì quan trọng với downstream?

**Đáp án:** Timeline mới; downstream phải theo nhánh WAL tương thích.

### Bài 28 — Fencing

Vì sao phải fence primary cũ trước khi mở writes ở primary mới?

**Đáp án:** Tránh split-brain và divergent writes.

### Bài 29 — Disk planning

Nếu WAL generation 20 MB/s và cần giữ outage window 30 phút, lượng WAL tối thiểu lý tưởng là bao nhiêu trước buffer?

**Đáp án:** 20 × 60 × 30 = 36.000 MB, khoảng 36 GB thập phân.

### Bài 30 — Capacity

Một relay gửi WAL cho 20 downstream và phục vụ analytics. Cần đo những gì?

**Gợi ý:** Sender count, network egress, disk latency, CPU, replay lag, read query latency và headroom.

### Bài 31 — Read routing

Một query cần dữ liệu mới nhất ngay sau write nên route đi đâu?

**Đáp án:** Primary hoặc replica đã xác nhận replay tới required LSN.

### Bài 32 — Monotonic reads

Vì sao routing user luân phiên giữa replicas có lag khác nhau có thể thấy dữ liệu lùi?

**Gợi ý:** Replica sau có thể replay ít WAL hơn replica trước.

### Bài 33 — Backup

Cascading replication có thay WAL archive/PITR không?

**Đáp án:** Không.

### Bài 34 — Backup từ standby

Lợi ích và trade-off là gì?

**Gợi ý:** Giảm load primary nhưng tăng load trên standby và phụ thuộc tool/version.

### Bài 35 — Monitoring

Metric nào giúp phát hiện query cancellations do recovery conflict?

**Đáp án:** pg_stat_database_conflicts.

### Bài 36 — Receiver identity

Sau reparenting, field nào giúp xác nhận upstream mới?

**Đáp án:** sender_host trong pg_stat_wal_receiver.

### Bài 37 — Leaf lag

Vì sao lag của leaf có thể cao hơn relay?

**Gợi ý:** Thêm network hop, sender queue, receiver/replay backlog.

### Bài 38 — Slot loss

Nếu slot vượt max_slot_wal_keep_size và mất WAL cần thiết, cần làm gì?

**Gợi ý:** Dùng archive nếu có WAL đầy đủ; nếu không reseed standby.

### Bài 39 — Failback

Primary cũ trở lại sau promotion có thể tự nhận lại role primary không?

**Đáp án:** Không; cần fencing, timeline reconciliation, pg_rewind hoặc reseed và kế hoạch failback.

### Bài 40 — Thiết kế tổng hợp

Thiết kế topology cho một primary ở region A, relay ở region B và bốn read replicas trong region B/C. Yêu cầu read freshness 5 giây, RTO primary failure 2 phút, đồng thời có analytics query dài.

**Gợi ý:** Chọn direct relay(s) theo failure domain/capacity, phân nhóm downstream, đặt analytics trên replica riêng, monitor từng hop/LSN, read router có lag-aware selection và fallback, policy query conflicts/hot_standby_feedback riêng, sync semantics rõ nếu cần durability, backup/PITR độc lập, fencing/reparent automation và restore/failover drills.

## 49. Checklist thiết kế và vận hành

### 49.1. Topology

- [ ] Đã vẽ primary, relay, leaves và direct connections?
- [ ] Không có replication cycle?
- [ ] Mỗi node có owner và purpose rõ?
- [ ] Failure domains/regions đã được xác định?
- [ ] Có upstream thay thế và reparent plan?

### 49.2. WAL và connections

- [ ] wal_level phù hợp?
- [ ] max_wal_senders đủ trên primary và relay?
- [ ] max_replication_slots đủ?
- [ ] WAL retention có headroom cho outage window?
- [ ] Slot owners và inactive slot alerts?
- [ ] WAL archive độc lập và PITR được kiểm tra?

### 49.3. Read routing

- [ ] Write pool luôn tới primary?
- [ ] Read pool chỉ chọn healthy replicas?
- [ ] Lag threshold theo use case?
- [ ] Read-after-write/monotonic reads được xử lý?
- [ ] Long analytics queries có replica riêng?
- [ ] Fallback behavior được xác định?

### 49.4. Conflicts và capacity

- [ ] hot_standby và conflict metrics được theo dõi?
- [ ] max_standby delays phù hợp?
- [ ] hot_standby_feedback có trade-off bloat?
- [ ] Relay đủ network ingress/egress?
- [ ] Disk/CPU đủ cho WAL replay và reads?
- [ ] Có headroom cho catch-up và basebackup?

### 49.5. Failover và security

- [ ] Sender/receiver metrics được thu thập từng hop?
- [ ] Timeline/reparent procedure đã thử?
- [ ] Old primary fencing có bằng chứng?
- [ ] Replication roles tối thiểu và TLS?
- [ ] Secret rotation đã thử?
- [ ] Backup/restore/failover drills có lịch?

## 50. Bảng tra cứu nhanh

| Thành phần | Vai trò |
|---|---|
| Cascading replication | Standby relay WAL cho downstream |
| Primary | Node authoritative nhận writes |
| Relay standby | Nhận và gửi WAL |
| Leaf standby | Downstream read replica |
| WAL sender | Gửi WAL qua replication protocol |
| WAL receiver | Nhận WAL từ upstream |
| Replay LSN | WAL đã áp dụng trên standby |
| pg_stat_replication | Sender connections trực tiếp |
| pg_stat_wal_receiver | Receiver connection trên standby |
| pg_stat_database_conflicts | Query cancellations do recovery conflicts |
| primary_conninfo | Cấu hình upstream connection |
| primary_slot_name | Slot downstream yêu cầu trên upstream |
| max_wal_senders | Giới hạn WAL sender processes |
| max_replication_slots | Số replication slots |
| wal_keep_size | Mức WAL tối thiểu cần giữ |
| max_slot_wal_keep_size | Giới hạn WAL retained bởi slots theo version |
| hot_standby | Read-only queries trong recovery |
| hot_standby_feedback | Gửi snapshot horizon để giảm cleanup conflicts |
| max_standby_streaming_delay | Giới hạn replay delay do streaming conflicts |
| recovery_min_apply_delay | Cố ý trì hoãn replay |
| Read load balancing | Phân phối SQL reads qua app/proxy |
| Read-after-write | Đảm bảo request đọc thấy commit của nó |
| LSN token | Mốc replay cần đạt trước khi đọc |
| Reparenting | Chuyển downstream sang upstream khác |
| Fencing | Ngăn primary cũ tiếp tục nhận writes |
| Timeline | Nhánh lịch sử WAL sau recovery/promotion |
| pg_rewind | Đồng bộ node diverged khi đủ điều kiện |
| WAL archive | Recovery path độc lập cho WAL |
| Reseed | Tạo lại standby từ base backup |

## 51. Kết luận

**Cascading replication phân phối WAL theo topology nhiều tầng; read load balancing phân phối truy vấn SELECT theo policy của ứng dụng hoặc middleware.** Một standby có thể làm relay, phục vụ reads hoặc đảm nhiệm cả hai, nhưng mỗi vai trò đều tiêu thụ network, CPU, disk và connection capacity. Topology cây giúp giảm fan-out trực tiếp trên primary và đặt replicas gần workload, đổi lại relay trở thành dependency của downstream và mỗi hop có thể làm tăng lag.

Muốn vận hành ổn định, hãy cấu hình sender/receiver, HBA, replication roles, slots và WAL retention trên từng node. Theo dõi pg_stat_replication tại từng sender, pg_stat_wal_receiver trên từng standby, replay LSN, conflict counters, slot retention và disk headroom. Đối với read routing, phân biệt eventual consistency với read-after-write, chọn replica theo lag/capacity và có fallback rõ ràng. Query dài trên hot standby cần policy conflict phù hợp; hot_standby_feedback có thể giảm cancellations nhưng làm upstream giữ dead tuples lâu hơn.

Khi relay hoặc primary fail, descendants cần reparent theo timeline/WAL compatibility; promotion phải đi cùng fencing để tránh split-brain. Cascading không thay backup/PITR và không bảo vệ khỏi logical corruption được replay. Thiết kế cần được kiểm chứng bằng lab, failover drills, restore tests và monitoring từng hop.

Nguyên tắc vận hành: **thiết kế WAL topology, read routing, consistency, capacity và failover như các phần liên quan nhưng có tiêu chí riêng; đo lag trên từng hop, bảo vệ WAL/backup độc lập và diễn tập reparenting trước khi cần dùng trong sự cố.**

