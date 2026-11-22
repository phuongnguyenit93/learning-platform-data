# Kiểm tra mất kết nối, bắt kịp WAL và khởi tạo lại standby trong PostgreSQL

Physical streaming replication giúp một PostgreSQL standby nhận WAL từ primary và replay các thay đổi để duy trì bản sao vật lý của cluster. Khi kết nối bị gián đoạn, standby có thể tiếp tục từ vị trí WAL đã nhận nếu các segments còn được giữ trên primary hoặc có trong WAL archive. Nếu WAL cần thiết đã bị recycle, hoặc standby đã đi sang một timeline khác, việc kết nối lại đơn thuần không đủ: cần đánh giá khả năng lấy WAL từ archive, dùng pg_rewind khi hai nhánh đã phân kỳ, hoặc tạo lại standby bằng một base backup mới.

Quá trình xử lý cần trả lời ba câu hỏi theo thứ tự:

1. **Kết nối có hoạt động không?** Primary có WAL sender, standby có WAL receiver, xác thực và mạng có thông suốt không?
2. **Standby còn thiếu WAL nào và WAL đó còn ở đâu?** Phân biệt WAL đã gửi, đã ghi, đã flush và đã replay; kiểm tra primary retention, replication slot và archive.
3. **Standby còn cùng lịch sử WAL không?** Nếu cùng timeline và WAL còn đủ, có thể bắt kịp. Nếu thiếu WAL hoặc timeline đã phân kỳ, chọn cách phục hồi phù hợp.

```text
Primary
  |  WAL sender
  |---------------------------> Standby
                                WAL receiver
                                    |
                                    v
                              pg_wal trên standby
                                    |
                                    v
                              Startup / redo
                                    |
                                    v
                              Replay vào data pages

Kết nối mất:
  1. Chẩn đoán mạng, auth, process và cấu hình
  2. Tìm WAL còn thiếu trong primary hoặc archive
  3. Nếu cùng timeline và đủ WAL: reconnect + catch-up
  4. Nếu divergence: pg_rewind (đủ điều kiện)
  5. Nếu WAL thiếu hoặc rewind không phù hợp: base backup mới
```

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Sao chép vật lý**, với đề tài **“Kiểm tra mất kết nối, bắt kịp WAL và khởi tạo lại standby”**. Nội dung bao gồm chẩn đoán replication, đọc LSN, xử lý retention, reconnect, catch-up, phân biệt lỗi WAL với timeline divergence, reinitialize standby, kiểm chứng và runbook vận hành.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò WAL sender và WAL receiver trong physical streaming replication.
2. Nhận biết các trạng thái streaming, catchup và mất kết nối.
3. Kiểm tra replication từ primary bằng pg_stat_replication.
4. Kiểm tra WAL receiver từ standby bằng pg_stat_wal_receiver.
5. Phân biệt sent, write, flush và replay LSN.
6. Đo khoảng WAL còn thiếu bằng pg_wal_lsn_diff khi hai vị trí cùng lịch sử.
7. Phân biệt network lag, receive lag và replay lag.
8. Nhận biết trường hợp standby đã nhận WAL nhưng chưa replay.
9. Điều tra lỗi DNS, routing, firewall, TLS, pg_hba.conf và replication credentials.
10. Kiểm tra primary_conninfo, replication role, max_wal_senders và replication slots.
11. Giải thích wal_keep_size và giới hạn của nó.
12. Hiểu cách replication slot giữ WAL và nguy cơ đầy disk.
13. Nhận biết slot đã mất khả năng bắt kịp do WAL bị recycle.
14. Sử dụng WAL archive và restore_command để cung cấp segments còn thiếu.
15. Hiểu các tham số timeout và retry liên quan WAL streaming.
16. Xác định standby có còn cùng timeline với primary hay không.
17. Phân biệt reconnect/catch-up với timeline rewind.
18. Nêu điều kiện và giới hạn của pg_rewind.
19. Khởi tạo lại standby bằng pg_basebackup theo quy trình an toàn.
20. Cấu hình replication slot và connection sau khi rebuild.
21. Theo dõi quá trình bắt kịp cho tới khi replay ổn định.
22. Kiểm tra tính nhất quán ở mức dữ liệu và ứng dụng.
23. Thiết kế retention, capacity alerts và backup để giảm rủi ro reinitialize.
24. Lập runbook xử lý standby offline, WAL gap, divergence và rebuild.

**Phạm vi:** PostgreSQL hiện đại, đặc biệt PostgreSQL 12 trở lên. Tên cột của một số system views và khả năng của các tham số/công cụ có thể thay đổi theo major version. Các lệnh có tác động tới data directory hoặc vai trò server chỉ nên chạy theo runbook trên đúng node.

---

## 2. Physical streaming replication hoạt động thế nào?

Trong physical replication, primary gửi WAL stream tới standby. Standby lưu WAL nhận được vào vùng WAL của mình rồi startup process replay records để cập nhật các data pages.

### 2.1. Trên primary

- Transaction ghi tạo WAL records.
- WAL được ghi và flush theo durability policy.
- WAL sender process gửi WAL tới standby đang kết nối.
- Replication slot, wal_keep_size và archive policy có thể ảnh hưởng thời gian WAL còn sẵn.

### 2.2. Trên standby

- WAL receiver kết nối tới primary qua replication protocol.
- WAL receiver nhận và ghi WAL vào pg_wal.
- Startup process replay WAL vào data pages.
- Standby có thể phục vụ read-only queries nếu hot_standby được bật.

### 2.3. Nhận WAL khác với replay WAL

Standby có thể đã nhận và flush một WAL segment nhưng chưa replay tới cuối segment. Trong trường hợp đó, WAL đã nằm trên standby nhưng các thay đổi tương ứng chưa nhất thiết visible cho query.

### 2.4. Physical standby không chạy lại SQL

Standby replay WAL records ở mức storage/internal operations. Nó không thực thi lại câu UPDATE hoặc INSERT gốc từ ứng dụng.

### 2.5. Một primary có thể có nhiều standby

Primary có thể gửi WAL tới nhiều standby trực tiếp. Một standby cũng có thể đóng vai trò upstream cho standby khác trong cascading replication.

### 2.6. Streaming replication không thay backup

Một thao tác DELETE nhầm hoặc lỗi logic được replicate sang standby. Base backup và WAL archive vẫn cần để phục hồi về trước thời điểm lỗi.

---

## 3. Những thành phần cần kiểm tra khi mất kết nối

Khi standby không còn theo kịp, vấn đề có thể nằm ở nhiều tầng:

| Thành phần | Vai trò | Triệu chứng khi lỗi |
| --- | --- | --- |
| Primary PostgreSQL | Tạo và phục vụ WAL | Server down, không tạo WAL sender |
| WAL sender | Gửi WAL tới standby | Không có session replication |
| Network | Chuyển WAL stream | Timeout, reset, packet loss |
| DNS/routing | Tìm và đi tới primary | Không phân giải được host, route sai |
| Firewall/security group | Cho phép TCP connection | Connection refused/timeout |
| TLS | Bảo vệ kết nối | Certificate/hostname/CA errors |
| pg_hba.conf | Xác thực replication connection | No pg_hba.conf entry, authentication failed |
| Replication role | Cho phép replication login | Permission denied |
| WAL receiver | Nhận stream trên standby | Không có receiver hoặc receiver reconnect liên tục |
| Replication slot | Giữ WAL cần cho consumer | WAL retained, disk tăng hoặc slot bị invalid |
| WAL archive | Cung cấp segments cũ | Restore command lỗi, missing segment |
| Standby storage | Ghi WAL và data pages | I/O chậm, disk full, filesystem read-only |
| Startup/replay | Áp dụng WAL | Receive tiến nhưng replay chậm |
| Timeline history | Chọn đúng nhánh WAL | Standby không follow nhánh sau promotion |

Không kết luận replication hỏng chỉ từ một chỉ số lag. Cần đọc trạng thái primary, standby và log của cả hai phía.

---

## 4. Kiểm tra nhanh trạng thái trên primary

### 4.1. Liệt kê standby đang kết nối

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
    reply_time
FROM pg_catalog.pg_stat_replication;
```

View này hiển thị các standby kết nối trực tiếp tới primary hiện tại. Nó không tự liệt kê toàn bộ các standby ở phía sau một cascading standby.

### 4.2. Ý nghĩa state

Các state thường gặp gồm:

- startup: standby đang thiết lập replication connection.
- catchup: standby đang bắt kịp WAL trước khi vào streaming state.
- streaming: WAL đang được gửi liên tục.
- backup: connection đang phục vụ một số hoạt động backup.
- stopping: WAL sender đang dừng.

State và tập giá trị có thể thay đổi theo version. Xem tài liệu major version của cluster.

### 4.3. Không có row trong pg_stat_replication

Không có row thường có nghĩa primary không có standby connection trực tiếp đang hoạt động tại thời điểm query. Điều đó không tự chứng minh data directory standby bị hỏng.

Kiểm tra thêm:

- Standby có đang chạy không?
- WAL receiver có đang thử reconnect không?
- primary_conninfo có đúng host/port/user không?
- Network và TLS có thông không?
- Replication role có quyền LOGIN/REPLICATION không?
- pg_hba.conf có rule phù hợp không?
- Primary có đủ max_wal_senders không?
- Logs có lỗi authentication, timeout hoặc missing WAL không?

### 4.4. Kiểm tra WAL sender processes

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

### 4.5. Đếm connection replication

```sql
SELECT count(*) AS active_standby_connections
FROM pg_catalog.pg_stat_replication;
```

Đối chiếu với số standby dự kiến. Nếu có cascading topology, phải kiểm tra mỗi upstream tương ứng.

---

## 5. Kiểm tra trạng thái trên standby

### 5.1. Server có đang recovery không?

```sql
SELECT pg_is_in_recovery();
```

- true: server đang ở recovery, thường là standby hoặc archive recovery.
- false: server không còn ở recovery và có thể đang hoạt động như primary.

Không promote một server chỉ vì WAL receiver mất kết nối. Mất kết nối không phải bằng chứng primary đã chết.

### 5.2. Kiểm tra WAL receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

View này cung cấp trạng thái receiver, sender host/port, slot name, LSN và thời gian nhận message tùy version. Trên standby đang streaming, thường có một row.

Nếu không có row, receiver có thể chưa khởi động, đã dừng hoặc chưa thiết lập được connection. Hãy đọc logs và cấu hình.

### 5.3. Kiểm tra receive/replay LSN

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

- receive_lsn: vị trí WAL cuối cùng được nhận và đồng bộ vào storage qua streaming.
- replay_lsn: vị trí WAL cuối cùng được replay.
- last_replay_time: thời điểm transaction cuối cùng được replay.

Các hàm có thể trả NULL khi chưa có WAL nhận/replay phù hợp trong session recovery hiện tại.

### 5.4. Receive LSN tiến nhưng replay LSN đứng

Standby đã nhận WAL nhưng startup/replay không theo kịp. Điều tra:

- CPU và I/O standby.
- Disk latency và free space.
- Recovery conflicts do read queries.
- Replay có bị pause không.
- recovery_min_apply_delay có được cấu hình có chủ đích không.
- PostgreSQL logs có lỗi page/WAL không.

### 5.5. Cả receive và replay LSN đều đứng

Có thể receiver mất connection, primary không tạo WAL mới, network bị lỗi hoặc receiver đang chờ archive/retry. Đối chiếu primary LSN và WAL receiver status.

### 5.6. Timestamp replay cũ không tự chứng minh lỗi

Nếu primary không có transaction mới, last_replay_time có thể cũ dù standby đã đồng bộ hoàn toàn. Dùng LSN và workload activity cùng lúc để đánh giá.

---

## 6. Phân biệt sent, write, flush và replay

Trên primary, các LSN trong pg_stat_replication biểu diễn các giai đoạn khác nhau:

| Trường | Ý nghĩa |
| --- | --- |
| sent_lsn | Vị trí WAL primary đã gửi tới standby |
| write_lsn | Vị trí standby báo đã ghi WAL |
| flush_lsn | Vị trí standby báo đã flush WAL tới storage |
| replay_lsn | Vị trí standby đã replay WAL |

Luồng:

```text
Primary WAL position
        |
        v
     sent_lsn
        |
        v
     write_lsn
        |
        v
     flush_lsn
        |
        v
     replay_lsn
```

### 6.1. Sent lag

Nếu primary current LSN tiến nhanh hơn sent_lsn, WAL sender/network path có thể chưa gửi hết dữ liệu.

### 6.2. Write lag

Nếu sent_lsn tiến nhưng write_lsn chậm, standby có thể nhận/ghi chậm hoặc network có vấn đề.

### 6.3. Flush lag

Nếu write_lsn tiến nhưng flush_lsn chậm, standby storage flush có thể là bottleneck.

### 6.4. Replay lag

Nếu flush_lsn tiến nhưng replay_lsn chậm, standby đã lưu WAL nhưng chưa apply kịp.

### 6.5. Không suy ra nguyên nhân chỉ từ một khoảng cách

Các khoảng cách LSN giúp định vị giai đoạn chậm. Cần kết hợp logs, OS metrics, query load và disk latency để xác định nguyên nhân.

---

## 7. Đo WAL bytes còn thiếu

Trên primary, có thể so current WAL LSN với các vị trí standby:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        sent_lsn
    ) AS unsent_bytes,
    pg_wal_lsn_diff(
        sent_lsn,
        write_lsn
    ) AS sent_not_written_bytes,
    pg_wal_lsn_diff(
        write_lsn,
        flush_lsn
    ) AS written_not_flushed_bytes,
    pg_wal_lsn_diff(
        flush_lsn,
        replay_lsn
    ) AS flushed_not_replayed_bytes
FROM pg_catalog.pg_stat_replication;
```

Các phép trừ này chỉ có ý nghĩa khi các LSN cùng cluster và cùng lịch sử WAL phù hợp. Sau failover hoặc timeline divergence, không so LSN của hai nhánh như thể chúng là một stream duy nhất.

### 7.1. Đo tổng khoảng cách tới replay

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind_replay
FROM pg_catalog.pg_stat_replication;
```

### 7.2. LSN distance là bytes, không phải seconds

Nếu primary sinh 100 MB WAL mỗi phút, 500 MB backlog có ý nghĩa khác với workload chỉ sinh 1 MB mỗi phút. Muốn ước tính thời gian catch-up cần đo WAL generation rate và replay throughput.

### 7.3. LSN không thay timeline ID

Ghi nhận TLI cùng với LSN. Sau promotion, một LSN tương tự có thể thuộc nhánh WAL khác.

---

## 8. Lag columns và giới hạn diễn giải

pg_stat_replication có thể cung cấp write_lag, flush_lag và replay_lag trên các phiên bản hiện đại.

```sql
SELECT
    application_name,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_catalog.pg_stat_replication;
```

### 8.1. Lag là thời gian phản hồi gần đây

Các trường lag ước tính thời gian từ lúc WAL record được flush trên primary tới khi standby báo nhận/flush/replay vị trí tương ứng. Chúng phản ánh các giao dịch gần đây và không phải dự báo đầy đủ thời gian bắt kịp backlog.

### 8.2. Có thể NULL khi idle

Nếu primary không có WAL activity gần đây, các lag fields có thể NULL. NULL không tự động có nghĩa standby lỗi.

### 8.3. Không cộng các lag fields như một con số độc lập

Write, flush và replay lag có mối quan hệ và semantics riêng. Dùng LSN gap để xem backlog hiện tại, lag time để hiểu độ trễ gần đây.

### 8.4. Monitoring cần cả bytes và thời gian

Theo dõi:
- WAL bytes behind.
- Receive/replay LSN movement.
- Last message receipt.
- Last replay transaction timestamp.
- WAL generation rate.
- Standby disk/CPU.
- Connection state và logs.

---

## 9. Chẩn đoán lỗi network và connection

### 9.1. Kiểm tra host và port

Từ standby, kiểm tra DNS, route và khả năng mở TCP connection tới primary port (mặc định thường là 5432). Dùng công cụ mạng được phép trong môi trường của bạn, ví dụ Test-NetConnection trên Windows hoặc nc/psql trên Linux.

### 9.2. Kiểm tra primary đang listen

```sql
SHOW listen_addresses;
SHOW port;
```

Primary phải lắng nghe trên interface mà standby có thể truy cập. Thay đổi một số setting cần restart.

### 9.3. Kiểm tra firewall và security group

Cho phép kết nối TCP từ địa chỉ standby tới primary. Tránh mở replication port ra toàn Internet; giới hạn theo subnet/host và policy mạng.

### 9.4. Kiểm tra DNS và địa chỉ

Nếu primary_conninfo dùng hostname, xác minh standby phân giải đúng địa chỉ hiện tại. Sau failover, endpoint DNS/proxy cần trỏ tới primary mới.

### 9.5. Kiểm tra TLS

Nếu dùng SSL/TLS, xác minh CA, certificate, hostname và sslmode. verify-full kiểm tra cả chain và hostname; certificate mismatch có thể khiến connection thất bại sau đổi endpoint.

### 9.6. Kiểm tra connection limits

Đối chiếu max_wal_senders với số standby, backup streams và các replication clients cần connection. Nếu không đủ WAL sender slots, standby mới có thể không kết nối được.

### 9.7. Kiểm tra timeout và network stability

Firewall idle timeout, NAT, packet loss hoặc connection tracking có thể ngắt stream dài. Xem wal_sender_timeout, wal_receiver_timeout, TCP keepalive và network logs. Không giảm timeout quá thấp chỉ để phát hiện lỗi nhanh hơn nếu mạng có latency bình thường cao.

---

## 10. Xác thực replication

### 10.1. Replication role

Replication user cần LOGIN và quyền REPLICATION, hoặc quyền tương ứng qua role/managed service policy.

Ví dụ tạo role trong lab:

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-a-secret';
```

Không dùng password minh họa trong production. Quản lý credential bằng secret store hoặc passfile phù hợp.

### 10.2. pg_hba.conf

Một rule ví dụ giới hạn replication từ subnet standby:

```conf
hostssl replication replicator 10.20.30.0/24 scram-sha-256
```

Cú pháp authentication phải phù hợp PostgreSQL version và policy. Sau chỉnh sửa, reload cấu hình và kiểm tra logs.

### 10.3. Xác minh pg_hba_file_rules

```sql
SELECT *
FROM pg_catalog.pg_hba_file_rules;
```

View này giúp phát hiện lỗi parse và kiểm tra rule đã được đọc. Nó không thay thế việc kiểm tra kết nối thật từ standby.

### 10.4. Kiểm tra quyền role

```sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication
FROM pg_catalog.pg_roles
WHERE rolname = 'replicator';
```

### 10.5. Không ghi password vào log/chat

Không paste password hoặc connection string chứa secret vào ticket công khai. Có thể dùng passfile và quyền file hạn chế trên OS.

---

## 11. Kiểm tra primary_conninfo trên standby

Standby dùng primary_conninfo để biết cách kết nối upstream.

Ví dụ cấu hình:

```conf
primary_conninfo = 'host=db-primary.example.internal port=5432 user=replicator application_name=standby_a sslmode=verify-full'
```

### 11.1. Các trường cần kiểm tra

- host: DNS name/IP của primary hiện tại.
- port: port PostgreSQL.
- user: replication role.
- application_name: tên hiển thị trên primary.
- sslmode và certificate settings nếu dùng TLS.
- passfile: vị trí credentials nếu cần.

### 11.2. Không hard-code secret

Tránh đặt password trong file config có quyền đọc rộng. Dùng passfile/secret management và bảo vệ file bằng filesystem permissions.

### 11.3. Cấu hình có thể ở nhiều nơi

primary_conninfo có thể đến từ postgresql.conf, included config hoặc postgresql.auto.conf được tạo bởi công cụ như pg_basebackup -R. Xem nguồn hiệu lực:

```sql
SELECT
    name,
    setting,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'primary_conninfo',
    'primary_slot_name',
    'restore_command',
    'recovery_target_timeline'
);
```

Trên một số phiên bản, một số trường sourcefile/sourceline có thể NULL do quyền hoặc nguồn cấu hình.

### 11.4. Sau failover

Nếu primary đổi host/port, standby cần kết nối tới primary mới. Cập nhật connection theo HA endpoint hoặc automation đã được thiết kế; không chỉ thay hostname mà bỏ qua timeline divergence.

---

## 12. Kiểm tra WAL sender và replication capacity

### 12.1. max_wal_senders

Giới hạn số WAL sender processes đồng thời. Phải tính standby trực tiếp, backup streams và các consumers cần replication connection.

```sql
SHOW max_wal_senders;
```

### 12.2. max_replication_slots

Giới hạn replication slots. Mỗi standby có slot riêng cần được tính trong capacity plan.

```sql
SHOW max_replication_slots;
```

### 12.3. max_connections

Replication connections không đơn giản là các ứng dụng SQL connection thông thường; kiểm tra riêng WAL sender capacity và giới hạn dịch vụ/managed platform.

### 12.4. Logs khi hết capacity

Logs có thể chỉ ra không tạo được WAL sender hoặc không còn slot. Tăng giới hạn cần đánh giá process/memory overhead và thường yêu cầu restart với một số tham số.

### 12.5. Đừng nhầm hết capacity với WAL bị mất

Nếu primary không cấp được WAL sender, standby có thể reconnect sau khi capacity được khắc phục. Điều đó khác với trường hợp WAL segment đã bị recycle.

---

## 13. Replication slots giữ WAL như thế nào?

Replication slot ghi nhận vị trí consumer còn cần. Với physical slot, primary giữ các WAL segments cần cho standby từ restart_lsn trở đi.

### 13.1. Liệt kê slots

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

Dùng SELECT * khi khám phá schema để tránh lỗi do cột khác nhau giữa major versions. Trong monitoring lâu dài, chọn rõ các cột có trên phiên bản triển khai.

### 13.2. Các trường quan trọng

- slot_name: tên slot.
- slot_type: physical hoặc logical.
- active: slot hiện có consumer đang dùng không.
- restart_lsn: WAL sớm nhất consumer còn cần.
- confirmed_flush_lsn: thường có ý nghĩa với logical slot.
- wal_status/safe_wal_size: trạng thái retention trên các phiên bản hỗ trợ.

### 13.3. Slot inactive

Nếu standby mất kết nối, physical slot có thể trở thành inactive nhưng vẫn giữ WAL. Điều này giúp standby bắt kịp khi quay lại, miễn là storage còn đủ và retention policy không làm slot mất hiệu lực.

### 13.4. Slot có thể giữ WAL rất lâu

Một standby offline nhiều ngày có thể làm pg_wal tăng đáng kể nếu slot giữ toàn bộ WAL cần thiết.

### 13.5. max_slot_wal_keep_size

Tham số này giới hạn lượng WAL được giữ cho replication slots trên các phiên bản hỗ trợ. Khi giới hạn bị vượt, những segments cần thiết có thể bị recycle và slot không còn usable để bắt kịp.

### 13.6. Không unlimited một cách vô thức

Giá trị không giới hạn có thể bảo vệ slot khỏi bị mất WAL nhưng làm đầy filesystem. Chọn giới hạn dựa trên disk capacity, WAL generation peak và thời gian standby có thể offline.

### 13.7. Không drop slot chỉ để giảm disk usage

Drop slot có thể làm standby mất WAL cần thiết. Trước khi drop, xác định owner, consumer, backup/recovery dependency và kế hoạch reinitialize.

---

## 14. wal_keep_size và giới hạn retention

wal_keep_size yêu cầu primary giữ tối thiểu một lượng WAL gần đây để standby có cơ hội reconnect sau gián đoạn ngắn.

```sql
SHOW wal_keep_size;
```

### 14.1. Đây không phải retention guarantee dài hạn

Nếu standby offline lâu hơn lượng WAL được giữ, primary có thể recycle segment cũ. Standby khi quay lại sẽ thiếu WAL.

### 14.2. Không thay thế replication slot

wal_keep_size không theo dõi chính xác vị trí consumer như replication slot. Nó là một mức giữ WAL tối thiểu, không phải bảo đảm mỗi standby có đủ lịch sử.

### 14.3. Không thay thế archive

WAL archive là nguồn lưu trữ segments ngoài pg_wal để hỗ trợ phục hồi dài hơn và PITR. wal_keep_size không phải archive repository.

### 14.4. Dung lượng cần dựa trên WAL generation rate

Ước lượng sơ bộ:

```text
WAL retention cần thiết
  ≈ WAL generation rate × thời gian standby có thể offline
    + headroom cho workload burst
```

Đây chỉ là sizing estimate. Cần đo peak WAL rate, thời gian gián đoạn thực tế và các consumers khác.

### 14.5. Đừng dựa vào max_wal_size để bảo vệ standby

max_wal_size là mục tiêu kích hoạt checkpoint pressure, không phải hard cap hay cam kết giữ WAL cho standby.

---

## 15. WAL archiving như nguồn catch-up

Khi standby không còn tìm được segment trong pg_wal của primary, archive có thể cung cấp segment cũ.

### 15.1. Trên primary

Cấu hình archive mode và archive command/library phù hợp:

```conf
archive_mode = on
archive_command = 'archive-helper %p %f'
```

archive-helper là placeholder. Command chỉ được trả success sau khi file đã được lưu an toàn theo contract của archive system.

### 15.2. Trên standby

Cấu hình restore_command để lấy WAL segment từ archive:

```conf
restore_command = 'restore-helper %f %p'
```

restore-helper là placeholder cho script/tool đọc archive và đặt file đúng path.

### 15.3. Cơ chế kết hợp archive và streaming

Trong standby recovery, PostgreSQL có thể lấy WAL từ archive và streaming replication. Khi streaming bị gián đoạn, nó có thể tiếp tục thử archive/reconnect theo recovery loop. Chi tiết thứ tự retry và log message phụ thuộc version/configuration.

### 15.4. Archive phải có đủ segment liên tục

Một archive có nhiều file nhưng thiếu đúng segment cần thiết vẫn không giúp standby bắt kịp.

### 15.5. History files cũng cần có

Sau promotion, standby có thể cần timeline history files để follow nhánh mới.

### 15.6. Archive integrity

Dùng checksum/manifest, immutable storage và monitoring. Không báo archive success trước khi dữ liệu đã được lưu bền vững.

---

## 16. Chẩn đoán thông báo WAL missing

Một log thường gặp có nội dung tương tự:

```text
requested WAL segment ... has already been removed
```

Điều này thường cho biết standby yêu cầu một WAL segment mà primary hiện tại không còn cung cấp từ pg_wal.

### 16.1. Kiểm tra slot

- Standby có dùng primary_slot_name không?
- Slot có tồn tại trên primary không?
- Slot có active/inactive?
- restart_lsn còn giữ được segment cần thiết?
- Slot có bị invalidated vì retention limit không?

### 16.2. Kiểm tra archive

- Segment có tồn tại trong archive không?
- restore_command có trả file đúng không?
- Archive có đúng timeline prefix không?
- File có bị corrupt hoặc bị xóa do retention không?

### 16.3. Kiểm tra timeline

- Primary hiện tại có được promote từ standby không?
- Standby còn theo timeline cũ không?
- History file có tồn tại?
- Recovery target timeline có phù hợp?

### 16.4. Quyết định

- Cùng timeline, WAL còn trong archive: để standby tiếp tục recovery/catch-up.
- Cùng timeline, WAL thiếu ở primary nhưng archive đầy đủ: cung cấp archive và kiểm tra restore_command.
- Cùng timeline, WAL mất ở cả primary lẫn archive: tạo lại standby từ base backup.
- Timeline đã phân kỳ: đánh giá pg_rewind; nếu không đủ điều kiện thì base backup mới.

### 16.5. Không copy một segment bất kỳ vào pg_wal

WAL phải thuộc đúng system identifier, timeline, segment sequence và checksum. Copy file sai có thể khiến recovery thất bại hoặc tạo thêm vấn đề.

---

## 17. Kiểm tra timeline trước khi catch-up

Sau failover, standby có thể vẫn trỏ về primary cũ hoặc timeline cũ.

### 17.1. Dấu hiệu divergence

- Primary mới đã được promote và có timeline ID cao hơn.
- Standby báo WAL segment không có trên timeline hiện tại.
- Logs đề cập timeline history hoặc timeline switch.
- Standby có thể cần WAL của nhánh mới từ fork point.

### 17.2. Kiểm tra history file

Đọc timeline history file trong archive hoặc pg_wal để xác định timeline cha và fork LSN. Không chỉnh sửa file.

### 17.3. recovery_target_timeline

Trong cấu hình standby, recovery_target_timeline = 'latest' thường cho phép theo timeline mới nhất có thể tìm thấy. Kiểm tra version, archive và history files trước khi dựa vào thiết lập này.

### 17.4. Cùng timeline và khác timeline là hai trường hợp khác nhau

Mất connection không tự làm timeline phân kỳ. Nếu standby chỉ chậm trên cùng nhánh và WAL còn đủ, reconnect là đủ. Nếu một nhánh đã được promote và nhánh kia có writes riêng, cần rewind hoặc rebuild.

### 17.5. LSN tương tự không chứng minh cùng lịch sử

Ghi cả TLI và LSN khi so sánh hai node. Không kết luận standby bắt kịp chỉ vì các con số LSN trông gần nhau.

---

## 18. Reconnect và catch-up khi WAL còn đủ

Đây là trường hợp dễ xử lý nhất: standby mất mạng một thời gian nhưng primary vẫn giữ các WAL segments cần thiết, hoặc archive cung cấp đầy đủ segments.

### 18.1. Khôi phục network/authentication

Sửa DNS, firewall, TLS, pg_hba.conf, credentials hoặc connection endpoint.

### 18.2. Xác nhận primary_conninfo

Đảm bảo standby kết nối đúng primary hiện tại và application_name/slot name đúng.

### 18.3. Kiểm tra receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

Khi streaming hoạt động, receiver thường hiển thị trạng thái streaming và LSN tiến dần.

### 18.4. Kiểm tra primary

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
```

### 18.5. Theo dõi LSN tiến triển

Lấy nhiều snapshot theo thời gian. Nếu sent/write/flush/replay LSN tăng đều, standby đang bắt kịp.

### 18.6. So sánh backlog và throughput

Đo bytes behind qua nhiều khoảng thời gian. Nếu replay throughput lớn hơn WAL generation rate, backlog sẽ giảm. Nếu primary tạo WAL nhanh hơn standby replay, lag có thể tiếp tục tăng dù receiver đang connected.

### 18.7. Không cần base backup nếu WAL còn liên tục

Nếu standby cùng timeline và có đầy đủ WAL cần thiết, PostgreSQL tự replay phần còn thiếu. Rebuild trong trường hợp này sẽ tiêu tốn băng thông và I/O không cần thiết.

---

## 19. Tại sao standby nhận WAL nhưng replay chậm?

Receive lag và replay lag cần cách xử lý khác nhau.

### 19.1. Storage latency

WAL receiver có thể nhận bytes nhưng flush chậm do disk latency, throughput hoặc filesystem pressure.

### 19.2. Replay CPU

WAL replay cần CPU để xử lý records và cập nhật pages/indexes. Standby CPU bận có thể làm replay chậm.

### 19.3. Read query conflicts

Read-only queries trên hot standby có thể xung đột với WAL replay, ví dụ query đang giữ snapshot cần thiết cho cleanup. PostgreSQL có thể delay replay hoặc cancel query theo standby delay settings.

### 19.4. max_standby_streaming_delay

Tham số này điều khiển mức thời gian standby có thể trì hoãn replay để chờ conflicting queries trước khi cancel query. Tăng nó có thể bảo vệ report query nhưng làm replay lag tăng.

### 19.5. hot_standby_feedback

Có thể gửi feedback để primary tránh vacuum loại bỏ row versions cần cho standby queries, nhưng có thể gây bloat trên primary. Đây không phải một cách chung để tăng replay throughput.

### 19.6. recovery_min_apply_delay

Nếu cấu hình khác 0, standby cố ý trì hoãn apply WAL. Đây có thể là thiết kế delayed standby để bảo vệ khỏi một số lỗi logic; không xem lag đó là lỗi network.

### 19.7. Replay paused

Kiểm tra:

```sql
SELECT pg_is_wal_replay_paused();
```

Nếu đang pause, xác minh lý do trước khi resume:

```sql
SELECT pg_wal_replay_resume();
```

Không resume một cách máy móc nếu pause là một phần của PITR/DR procedure đang chờ kiểm tra.

---

## 20. Timeout và retry settings

Một số tham số ảnh hưởng khả năng phát hiện và khôi phục connection:

| Setting | Vai trò | Lưu ý |
| --- | --- | --- |
| wal_sender_timeout | Primary phát hiện WAL sender connection bị im lặng | Quá thấp có thể disconnect mạng latency cao |
| wal_receiver_timeout | Standby phát hiện không nhận message từ upstream | Đánh giá cùng network timeout |
| wal_retrieve_retry_interval | Khoảng retry khi không lấy được WAL trong recovery | Ảnh hưởng retry cadence |
| wal_receiver_status_interval | Chu kỳ standby gửi status updates | Ảnh hưởng mức độ thường xuyên primary nhận progress |
| tcp_keepalives_idle | Thời gian idle trước TCP keepalive | Phụ thuộc OS |
| tcp_keepalives_interval | Khoảng giữa probes | Phụ thuộc OS |
| tcp_keepalives_count | Số probes trước khi connection được xem là chết | Phụ thuộc OS |

Xem cấu hình PostgreSQL:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name IN (
    'wal_sender_timeout',
    'wal_receiver_timeout',
    'wal_retrieve_retry_interval',
    'wal_receiver_status_interval',
    'primary_conninfo',
    'primary_slot_name',
    'wal_keep_size',
    'max_slot_wal_keep_size'
)
ORDER BY name;
```

Một số OS keepalive settings không hiển thị đầy đủ trong PostgreSQL trên mọi nền tảng. Không chỉnh timeout chỉ để che lỗi network; cần xác định latency, idle timeout và failure detection requirement.

---

## 21. Khi nào cần pg_rewind?

pg_rewind phù hợp khi target và source từng thuộc cùng một cluster, nhưng đã diverge sau một điểm chung, thường do primary cũ và primary mới cùng tạo WAL trên các timeline khác nhau.

### 21.1. Reconnect không giải quyết divergence

Nếu target đã ghi WAL riêng sau fork point, nó không thể chỉ nhận WAL của source rồi tiếp tục như thể chưa có nhánh riêng.

### 21.2. pg_rewind xác định điểm chung

Công cụ tìm common timeline history/fork point, xác định blocks đã thay đổi trên source và cập nhật target để theo source.

### 21.3. Trường hợp thường dùng

- Primary cũ quay lại sau failover.
- Standby bị promote nhầm rồi muốn đưa nó về nhánh authoritative.
- Một cluster PITR được promote và cần rejoin vào topology khác.

### 21.4. Không dùng pg_rewind cho mọi WAL gap

Nếu standby chỉ mất WAL do offline quá lâu nhưng vẫn cùng timeline, archive hoặc base backup mới là lựa chọn phù hợp tùy WAL availability. pg_rewind dành cho divergence, không phải công cụ chung để tải lại WAL bị thiếu.

---

## 22. Điều kiện tiên quyết của pg_rewind

Trước khi chạy, xác nhận toàn bộ các điều kiện phù hợp với PostgreSQL version:

1. Source và target có cùng system identifier/cluster ancestry trước điểm phân nhánh.
2. Target PostgreSQL đã được shutdown cleanly.
3. Data checksums được bật từ khi cluster được initdb, hoặc wal_log_hints đã được bật trên target từ trước khi divergence xảy ra.
4. full_page_writes được bật theo yêu cầu của pg_rewind.
5. WAL cần thiết từ điểm phân nhánh có sẵn trong target pg_wal hoặc lấy được từ archive.
6. Có quyền truy cập source theo phương thức được chọn.
7. Có đủ disk space và quyền OS trên target.
8. Có snapshot/backup target nếu cần bảo toàn dữ liệu để điều tra.
9. Công cụ pg_rewind tương thích với major version của cluster.

### 22.1. Data checksums

Có thể kiểm tra trạng thái bằng công cụ phù hợp, ví dụ pg_controldata. Checksums phải được bật khi tạo cluster hoặc theo quy trình chuyển đổi riêng được PostgreSQL hỗ trợ.

### 22.2. wal_log_hints

Nếu không bật data checksums, wal_log_hints có thể đáp ứng yêu cầu phát hiện hint-bit changes cho rewind, nhưng phải được bật trước khi các thay đổi cần theo dõi xảy ra. Bật sau khi divergence không thể tái tạo WAL đã thiếu.

### 22.3. full_page_writes

Cần bật để đảm bảo WAL có thông tin page cần thiết cho quá trình rewind/recovery theo yêu cầu của công cụ.

### 22.4. Target phải shutdown cleanly

Không chạy pg_rewind lên data directory của server đang hoạt động. Dừng target đúng cách và xác nhận process không còn dùng directory.

### 22.5. WAL từ fork point

Nếu WAL cần thiết không còn trong target pg_wal, có thể dùng restore-target-wal option để lấy từ archive nếu restore_command được cấu hình đúng. Nếu không có WAL, rewind có thể không thực hiện được.

---

## 23. Chạy pg_rewind

Ví dụ sử dụng source server:

```bash
pg_rewind \
  --target-pgdata=/data/old-standby \
  --source-server="host=new-primary port=5432 dbname=postgres user=rewind_user"
```

Thay path, connection string, user và quyền bằng giá trị của môi trường thực tế.

### 23.1. Source server

Source là cluster authoritative mà target cần theo. Source server thường phải chạy và user kết nối cần quyền phù hợp để pg_rewind đọc dữ liệu/control information.

### 23.2. Target data directory

Target là data directory đã dừng cleanly và cần được rewind. Xác nhận đúng đường dẫn trước khi chạy vì công cụ sẽ thay đổi nội dung target.

### 23.3. Lấy WAL từ archive

Nếu cần dùng WAL archive và target đã có restore_command:

```bash
pg_rewind \
  --target-pgdata=/data/old-standby \
  --source-server="host=new-primary port=5432 dbname=postgres user=rewind_user" \
  --restore-target-wal
```

Tùy chọn và cú pháp phải kiểm tra theo pg_rewind binary của major version.

### 23.4. Ghi cấu hình standby sau rewind

Trên phiên bản hỗ trợ, --write-recovery-conf (hoặc -R) có thể tạo cấu hình recovery/standby cần thiết, gồm signal file và connection settings. Review file được tạo trước khi khởi động.

### 23.5. Rewind xong chưa có nghĩa standby đã catch up

Sau khi rewind, target có thể cần crash recovery/replay WAL rồi mới stream tiếp. Theo dõi logs và receiver/replay LSN.

### 23.6. Nếu pg_rewind thất bại

Không lặp lại liên tục khi chưa hiểu lỗi. Bảo toàn logs, kiểm tra preconditions, WAL availability, system identifier, permissions và target state. Nếu không thể rewind, tạo standby mới từ base backup.

---

## 24. Khởi tạo lại standby bằng pg_basebackup

Khi WAL cần thiết không còn, timeline divergence không thể rewind, hoặc data directory bị hỏng, cách rõ ràng là tạo standby mới từ base backup của primary authoritative.

### 24.1. Khi nào nên rebuild?

- WAL segment cần thiết mất cả trên primary lẫn archive.
- Replication slot đã invalidated và không còn đủ WAL.
- Target và source không đáp ứng điều kiện pg_rewind.
- Target data directory bị corruption hoặc không đáng tin cậy.
- Muốn thay thế một standby cũ bằng bản clone mới.
- Rewind thất bại và không có cách cung cấp WAL thiếu.

### 24.2. Chuẩn bị trước khi backup

1. Xác nhận đúng primary authoritative.
2. Xác nhận target standby đã dừng.
3. Bảo toàn/snapshot data directory cũ nếu cần điều tra.
4. Chọn data directory đích mới hoặc rỗng.
5. Kiểm tra replication role và pg_hba.conf.
6. Kiểm tra dung lượng disk, network throughput và tablespace paths.
7. Chọn replication slot và WAL streaming method.
8. Kiểm tra backup retention và archive policy.

### 24.3. Tạo replication role nếu chưa có

Ví dụ lab:

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-a-secret';
```

Trong production dùng secret management và không đưa password vào logs.

### 24.4. Rule pg_hba.conf

```conf
hostssl replication replicator 10.20.30.0/24 scram-sha-256
```

Rule chỉ là ví dụ. Thay subnet, auth method và TLS theo security policy.

### 24.5. Cấu hình primary

Các setting thường cần kiểm tra:

```conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
hot_standby = on
```

Giá trị là ví dụ, không phải cấu hình khuyến nghị cho mọi cluster. wal_level phải phù hợp topology; một số tham số cần restart.

### 24.6. Base backup cơ bản

Ví dụ:

```bash
pg_basebackup \
  -h new-primary \
  -p 5432 \
  -U replicator \
  -D /data/standby-new \
  -R \
  -X stream \
  -P
```

-R ghi cấu hình cần thiết để tiếp tục như standby trên phiên bản hỗ trợ. -X stream stream WAL trong khi backup. -P hiển thị tiến độ.

### 24.7. Dùng replication slot

Nếu slot đã tồn tại và được dành cho standby:

```bash
pg_basebackup \
  -h new-primary \
  -p 5432 \
  -U replicator \
  -D /data/standby-new \
  -R \
  -X stream \
  -S standby_a_slot \
  -P
```

Nếu cần tạo slot mới qua pg_basebackup và phiên bản hỗ trợ:

```bash
pg_basebackup \
  -h new-primary \
  -p 5432 \
  -U replicator \
  -D /data/standby-new \
  -R \
  -X stream \
  -C \
  -S standby_a_slot \
  -P
```

Không dùng -C nếu slot cùng tên đã tồn tại. Chỉ một consumer nên sở hữu slot đó theo thiết kế.

### 24.8. Vì sao dùng -X stream?

WAL được stream song song trong lúc base backup, giúp backup có đủ WAL cần thiết để trở thành một bản sao nhất quán. Cần tính số WAL sender connections và bandwidth cho hoạt động này.

### 24.9. Data directory phải đúng điều kiện

Đích thường phải rỗng hoặc được chuẩn bị theo quy trình tool. Không để pg_basebackup ghi đè data directory của một instance đang chạy. Kiểm tra tablespace mapping và quyền sở hữu file.

### 24.10. Major version

Physical base backup phải tương thích major version và platform/format của cluster. Không dùng pg_basebackup để thực hiện major version upgrade; dùng quy trình upgrade được hỗ trợ.

---

## 25. Cấu hình standby sau pg_basebackup

Sau khi base backup hoàn tất, kiểm tra cấu hình được sinh ra.

### 25.1. standby.signal

Với PostgreSQL 12 trở lên, standby mode thường được kích hoạt bằng standby.signal. pg_basebackup -R có thể tạo file này.

### 25.2. primary_conninfo

Kiểm tra endpoint, replication user, application_name, TLS và passfile. Không để standby trỏ về primary cũ.

### 25.3. primary_slot_name

Nếu dùng physical replication slot, cấu hình standby dùng đúng slot đã được tạo/dành riêng.

### 25.4. restore_command

Nếu archive là nguồn dự phòng cho WAL catch-up, cấu hình restore_command đúng và test quyền truy cập archive.

### 25.5. recovery_target_timeline

Với standby cần theo timeline mới sau failover, xác nhận recovery_target_timeline phù hợp; latest thường là lựa chọn để follow nhánh mới nhất, nhưng cần archive/history files đầy đủ.

### 25.6. Kiểm tra postgresql.auto.conf

pg_basebackup -R có thể ghi cấu hình vào postgresql.auto.conf. Xem precedence giữa file chính, include files và auto.conf trước khi sửa.

### 25.7. Bảo vệ credential

Dùng passfile hoặc secret store. Đặt filesystem permissions hạn chế để chỉ OS account của PostgreSQL có thể đọc.

---

## 26. Khởi động standby và xác nhận bắt đầu streaming

### 26.1. Khởi động instance

Dùng service manager hoặc pg_ctl theo deployment. Kiểm tra logs ngay sau start.

### 26.2. Kiểm tra recovery state

```sql
SELECT pg_is_in_recovery();
```

Kỳ vọng true.

### 26.3. Kiểm tra WAL receiver

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

Khi receiver kết nối, xác nhận sender host, status, slot name và LSN fields phù hợp.

### 26.4. Kiểm tra primary

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
```

Xác nhận standby mới xuất hiện với application_name đúng.

### 26.5. Kiểm tra logs

Tìm các thông báo bắt đầu streaming, nhận WAL, bắt kịp và lỗi kết nối. Nếu receiver reconnect liên tục, xác định nguyên nhân thay vì chỉ restart instance nhiều lần.

---

## 27. Theo dõi quá trình catch-up sau reconnect/rebuild

Một standby vừa kết nối lại có thể cần replay lượng WAL lớn.

### 27.1. Lấy snapshot định kỳ

Trên primary:

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind
FROM pg_catalog.pg_stat_replication;
```

### 27.2. Theo dõi tốc độ giảm backlog

Lấy nhiều snapshot có timestamp. Nếu bytes_behind giảm, standby đang catch up. Nếu tăng, primary đang sinh WAL nhanh hơn standby xử lý hoặc có bottleneck.

### 27.3. Tách receive và replay

Nếu write/flush LSN gần sent LSN nhưng replay LSN cách xa, tập trung vào replay/storage/query conflicts. Nếu sent LSN cách xa current LSN, tập trung WAL sender/network.

### 27.4. Không yêu cầu lag bằng 0 khi workload liên tục

Trong hệ thống ghi liên tục, standby có thể luôn có một độ trễ nhỏ. Tiêu chí ổn định phải dựa vào SLO/RPO và trend, không nhất thiết là mọi snapshot đều bằng 0.

### 27.5. Xác nhận replay không bị pause

```sql
SELECT pg_is_wal_replay_paused();
```

### 27.6. Đo last replay time cẩn thận

Nếu primary không tạo transaction, timestamp replay có thể không thay đổi. Đánh giá cùng LSN movement và WAL generation.

---

## 28. Xử lý disk pressure trong khi standby offline

### 28.1. Vì sao pg_wal tăng?

- Physical slot giữ WAL cho standby offline.
- Archive command thất bại.
- Một logical slot khác giữ WAL.
- Workload tạo WAL nhanh.
- Standby/consumer không tiến vị trí restart_lsn.
- Nhiều backup/replication consumers cùng yêu cầu WAL.

### 28.2. Kiểm tra dung lượng

Dùng OS monitoring để xem filesystem chứa pg_wal, tốc độ tăng và free space. PostgreSQL không cung cấp một hard cap đơn giản bảo đảm thư mục này không vượt mức.

### 28.3. Kiểm tra slot retention

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

Đối chiếu restart_lsn, active và các retention fields có trên version.

### 28.4. Kiểm tra archiver

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

Failed count tăng liên tục là dấu hiệu cần kiểm tra archive destination, permissions, network và command logs.

### 28.5. Không xóa WAL bằng tay

Không xóa file trong pg_wal để giải phóng disk. Điều đó có thể làm primary không thể crash recover hoặc khiến các standby/backup mất WAL bắt buộc.

### 28.6. Xử lý theo nguyên nhân

- Tăng storage capacity nếu cần khẩn cấp.
- Khôi phục archive destination.
- Xác định consumer giữ slot và thời gian cần catch-up.
- Nếu slot không còn cần, xử lý theo runbook sau khi xác nhận owner/dependency.
- Rebuild standby nếu WAL đã mất.
- Điều tiết workload nếu WAL generation đang vượt khả năng lưu trữ.

---

## 29. Replication slot bị invalidated

Nếu slot cần WAL cũ hơn mức retention cho phép và segments đã bị recycle, standby có thể không dùng slot đó để catch up.

### 29.1. Dấu hiệu

Tùy version, pg_replication_slots có thể báo wal_status không còn usable hoặc trạng thái tương ứng. Logs có thể chỉ ra requested WAL segment đã bị removed.

### 29.2. Slot không thể tạo lại lịch sử đã mất

Tạo slot mới không khôi phục các WAL segments đã bị xóa. Slot mới chỉ giữ WAL từ vị trí hiện tại trở đi.

### 29.3. Đánh giá archive

Nếu archive có đầy đủ WAL từ vị trí standby cần, standby có thể phục hồi qua archive và sau đó tiếp tục streaming.

### 29.4. Nếu archive cũng thiếu

Tạo base backup mới. Không cố gắng làm standby nhận một WAL stream không liên tục.

### 29.5. Tạo slot cho standby mới

Khi rebuild, tạo slot mới hoặc dùng slot hiện hữu đã được kiểm tra. Đặt retention limit/capacity alerts để tránh lặp lại.

---

## 30. Chọn giữa reconnect, archive, pg_rewind và base backup

| Tình trạng | Cách xử lý thường phù hợp | Điều kiện chính |
| --- | --- | --- |
| Network gián đoạn ngắn, WAL còn trên primary | Reconnect/streaming catch-up | Cùng timeline, WAL còn đủ |
| WAL đã recycle trên primary nhưng archive đủ | Archive recovery rồi streaming | restore_command và archive continuity |
| Standby offline lâu, slot giữ WAL | Reconnect và catch-up | Slot còn hợp lệ, disk đủ |
| Slot mất WAL nhưng archive đủ | Restore WAL từ archive | Đúng timeline và segment liên tục |
| WAL thiếu cả primary lẫn archive, cùng timeline | Base backup mới | Source primary ổn định |
| Standby ở nhánh cũ sau promotion | pg_rewind hoặc base backup | Timeline divergence |
| pg_rewind không đủ preconditions | Base backup mới | Cùng source cluster, quyền và capacity |
| Data directory corrupt | Reinitialize từ backup | Base backup đáng tin |
| Hai primary cùng ghi | Fence, bảo toàn dữ liệu, chọn authoritative branch rồi rewind/rebuild | HA incident procedure |

### 30.1. Reconnect là lựa chọn đầu tiên khi cùng lịch sử

Nếu WAL còn đủ, để PostgreSQL tự reconnect và replay. Không rebuild chỉ vì receiver từng mất connection.

### 30.2. Archive cứu được WAL đã rời pg_wal

Archive chỉ giúp khi segment còn tồn tại và liên tục. Không thể tạo lại segment đã mất.

### 30.3. pg_rewind dành cho divergence

Rewind không thay thế base backup cho trường hợp WAL gap thông thường hoặc data directory corruption.

### 30.4. Base backup là cách tạo lại bản sao vật lý

Khi không thể tiếp tục lịch sử WAL hiện tại, một base backup mới tạo điểm xuất phát nhất quán.

---

## 31. Cấu hình replication tham khảo cho lab

Các ví dụ sau chỉ minh họa thành phần chính; cần điều chỉnh cho môi trường thực tế.

### 31.1. Primary

```conf
listen_addresses = '*'
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = '1GB'
archive_mode = on
archive_command = 'archive-helper %p %f'
```

Không dùng listen_addresses='*' nếu không có network controls phù hợp. wal_keep_size là ví dụ sizing, không phải giá trị chung.

### 31.2. Replication role và pg_hba

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-a-secret';
```

```conf
hostssl replication replicator 10.20.30.0/24 scram-sha-256
```

### 31.3. Standby

```conf
primary_conninfo = 'host=db-primary port=5432 user=replicator application_name=standby_a sslmode=verify-full'
primary_slot_name = 'standby_a_slot'
restore_command = 'restore-helper %f %p'
recovery_target_timeline = 'latest'
```

Standby mode trên PostgreSQL 12+ cần standby.signal. pg_basebackup -R có thể tạo signal file và cấu hình recovery cần thiết.

### 31.4. Slot

Tạo physical replication slot trên primary:

```sql
SELECT *
FROM pg_catalog.pg_create_physical_replication_slot('standby_a_slot');
```

Kiểm tra slot đã tồn tại trước khi tạo. Không tạo nhiều slot trùng vai trò.

### 31.5. Cấu hình có restart requirement

Các tham số như wal_level, max_wal_senders và max_replication_slots thường cần restart khi thay đổi. Kiểm tra pg_settings.context và pending_restart.

---

## 32. Lab 1: kiểm tra replication health

Lab cần một primary và một standby trong môi trường riêng.

### 32.1. Trên primary

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication;
```

Ghi lại trạng thái.

### 32.2. Trên standby

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 32.3. Tạo workload nhỏ

Trên primary:

```sql
CREATE TABLE IF NOT EXISTS public.replication_lab (
    id BIGINT PRIMARY KEY,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO public.replication_lab(id, message)
VALUES (1, 'replication-check')
ON CONFLICT (id) DO UPDATE
SET message = EXCLUDED.message,
    created_at = clock_timestamp();
```

### 32.4. Xác minh trên standby

Chờ replay và query row. Standby phải thấy thay đổi sau khi WAL được apply.

### 32.5. Tính bytes behind

Trên primary:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_behind
FROM pg_catalog.pg_stat_replication;
```

### 32.6. Quan sát nhiều lần

Lặp lại snapshot sau vài giây. Ghi nhận bytes_behind tăng hay giảm cùng workload.

---

## 33. Lab 2: mô phỏng mất kết nối ngắn

Chỉ thực hiện trong lab, không cắt network production.

### 33.1. Ghi baseline

Lưu sent/write/flush/replay LSN và slot state trước khi ngắt.

### 33.2. Tạm dừng network hoặc standby

Dùng cơ chế lab để làm standby mất kết nối trong thời gian ngắn. Không xóa data directory và không xóa WAL.

### 33.3. Quan sát primary

Kiểm tra row biến mất khỏi pg_stat_replication và slot active state thay đổi.

### 33.4. Quan sát standby

Kiểm tra logs có thông báo mất connection/retry. WAL receiver có thể biến mất khỏi view trong thời gian disconnected.

### 33.5. Khôi phục network

Cho standby kết nối lại với cùng primary và cùng timeline.

### 33.6. Xác minh catch-up

Xem receiver state, primary replication row và LSN movement. Standby phải replay phần WAL còn thiếu.

### 33.7. Kết luận

Nếu WAL vẫn được giữ, không cần base backup. Ghi lại thời gian offline tối đa mà cấu hình hiện tại có thể chịu được.

---

## 34. Lab 3: kiểm tra replication slot retention

Chỉ dùng lab cluster có disk capacity phù hợp.

### 34.1. Tạo physical slot

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_lab_slot');
```

### 34.2. Kiểm tra slot

```sql
SELECT *
FROM pg_replication_slots
WHERE slot_name = 'standby_lab_slot';
```

### 34.3. Ngắt standby và tạo WAL

Trong lab, tạm dừng standby rồi tạo workload ghi trên primary. Không tạo workload lớn hơn khả năng disk.

### 34.4. Theo dõi retained WAL

Kiểm tra restart_lsn và WAL disk usage. Khi slot inactive, primary vẫn có thể giữ segments cần cho slot.

### 34.5. Kết nối lại

Khôi phục standby và quan sát receiver bắt kịp nếu các WAL segments vẫn còn.

### 34.6. Dọn lab

Chỉ drop slot sau khi xác nhận standby không còn dùng nó và lab đã kết thúc:

```sql
SELECT pg_drop_replication_slot('standby_lab_slot');
```

Không dùng lệnh này trên slot production đang phục vụ standby.

---

## 35. Lab 4: archive-assisted catch-up

Lab cần WAL archiving được cấu hình đúng trên primary và restore_command trên standby.

### 35.1. Xác nhận archive

```sql
SELECT *
FROM pg_stat_archiver;
```

### 35.2. Tạo WAL

```sql
INSERT INTO public.replication_lab(id, message)
VALUES (2, 'archive-catchup')
ON CONFLICT (id) DO UPDATE
SET message = EXCLUDED.message;
```

### 35.3. Switch WAL trong lab

```sql
SELECT pg_switch_wal();
```

Lệnh này chỉ dùng trong lab/maintenance phù hợp; không ép switch liên tục trong production.

### 35.4. Kiểm tra archive file

Xác minh WAL segment có tên đầy đủ, đúng timeline và checksum/size phù hợp trong archive destination.

### 35.5. Kiểm tra restore_command

Trên standby, xác nhận command có thể lấy file theo tên được yêu cầu và trả đúng exit status khi file không tồn tại.

### 35.6. Thử khôi phục

Thực hiện bài test bằng một standby lab được cô lập, quan sát logs cho biết WAL lấy từ archive/streaming. Không xóa WAL production để buộc archive recovery.

---

## 36. Lab 5: rebuild standby bằng pg_basebackup

Bài này tạo một standby mới trong môi trường riêng. Không ghi đè data directory của node đang chạy.

### 36.1. Xác nhận primary

Trên primary, xác nhận role và replication capacity. Kiểm tra replication user và pg_hba.

### 36.2. Tạo slot

```sql
SELECT pg_create_physical_replication_slot('standby_rebuild_slot');
```

Nếu slot đã tồn tại, kiểm tra owner/state thay vì tạo lại.

### 36.3. Tạo base backup

```bash
pg_basebackup \
  -h db-primary \
  -U replicator \
  -D /data/standby-rebuilt \
  -R \
  -X stream \
  -S standby_rebuild_slot \
  -P
```

### 36.4. Kiểm tra file

Xác nhận data directory có cấu trúc PostgreSQL, standby.signal và cấu hình connection/slot phù hợp. Kiểm tra tablespaces nếu có.

### 36.5. Khởi động standby

Start bằng service manager/pg_ctl theo lab. Đọc logs và kiểm tra pg_is_in_recovery().

### 36.6. Kiểm tra receiver và primary

Dùng pg_stat_wal_receiver ở standby và pg_stat_replication ở primary.

### 36.7. Xác minh dữ liệu

Query bảng replication_lab trên standby sau replay. So sánh các row/checksums nghiệp vụ đã chọn.

### 36.8. Kết thúc

Ghi thời gian backup, dung lượng truyền, thời gian catch-up và trạng thái slot. Dọn lab theo quy trình riêng.

---

## 37. Lab 6: pg_rewind sau timeline divergence

Lab này cần hai data directories có cùng ancestry và một kịch bản promotion đã được kiểm soát. Không thực hiện trên production.

### 37.1. Chuẩn bị trước divergence

Bật data checksums khi initdb hoặc bật wal_log_hints từ trước. Bảo đảm full_page_writes bật. Cấu hình archive để giữ WAL.

### 37.2. Tạo standby

Dùng pg_basebackup tạo standby và xác nhận streaming.

### 37.3. Promotion trong lab

Fencing primary cũ trong lab rồi promote standby. Tạo một số WAL mới trên primary mới.

### 37.4. Primary cũ

Giữ data directory primary cũ để minh họa divergence. Không cho node đó nhận writes thêm.

### 37.5. Shutdown cleanly target

Dừng primary cũ theo clean shutdown và xác nhận không còn process sử dụng data directory.

### 37.6. Chạy pg_rewind

Dùng source-server trỏ tới primary mới và target-pgdata trỏ tới data directory cũ. Dùng restore-target-wal nếu cần WAL từ archive.

### 37.7. Cấu hình standby

Dùng write-recovery-conf nếu phiên bản hỗ trợ, hoặc cấu hình connection/signal file theo runbook.

### 37.8. Khởi động và xác minh

Kiểm tra pg_is_in_recovery(), WAL receiver, timeline và replay LSN. Xác minh dữ liệu sau promotion xuất hiện trên standby rejoined.

### 37.9. Nếu điều kiện không đủ

Ghi rõ lỗi, bảo toàn data directory và tạo lại standby từ base backup. Không sửa WAL hay control files bằng tay.

---

## 38. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Không có pg_stat_replication row nghĩa standby hỏng | Chỉ cho biết không có connection trực tiếp tại thời điểm query |
| Receiver connected nghĩa standby đã bắt kịp | Có thể vẫn còn receive/replay backlog |
| Receive LSN bằng replay LSN là mọi thứ ổn | Cần so với primary và timeline, đồng thời kiểm tra workload |
| write_lag là toàn bộ thời gian catch-up | Nó phản ánh lag gần đây, không dự báo backlog |
| last_replay_timestamp cũ nghĩa standby hỏng | Có thể primary không có transaction mới |
| wal_keep_size giữ WAL vô hạn | Chỉ là mức giữ tối thiểu |
| max_wal_size là hard disk cap | Không; slots/archive có thể giữ thêm WAL |
| Slot inactive có thể xóa ngay | Slot có thể giữ WAL cần cho standby |
| Tạo slot mới khôi phục WAL đã mất | Slot không tạo lại segment cũ |
| Archive bật nghĩa standby luôn bắt kịp | Cần WAL continuity và restore_command hoạt động |
| Mất network luôn cần pg_basebackup | Nếu WAL còn đủ, reconnect là đủ |
| Mọi WAL gap đều dùng pg_rewind | Rewind dành cho timeline divergence |
| pg_rewind là cách thay base backup cho mọi trường hợp | Nó có preconditions và cần WAL từ fork point |
| pg_rewind chạy được khi target đang hoạt động | Target phải được shutdown theo yêu cầu |
| Có thể bật wal_log_hints sau sự cố rồi rewind | Cần được bật trước khi divergence |
| Synchronous replication loại bỏ mọi data loss | Cần đúng standby, quorum, fencing và failover policy |
| Standby được promote thì primary cũ tự theo nó | Primary cũ cần rewind hoặc rebuild |
| Chỉ đổi primary_conninfo là đủ sau failover | Có thể còn timeline divergence |
| Copy WAL file thủ công luôn an toàn | Phải đúng system identifier, TLI, sequence và integrity |
| Restart receiver nhiều lần chữa mọi lỗi | Cần tìm nguyên nhân network, auth, retention hoặc replay |
| Rebuild standby không ảnh hưởng primary | Có thể tạo network, disk và WAL load lớn |
| Base backup từ major version khác luôn dùng được | Physical format phải tương thích major version |
| WAL replay chậm luôn do network | Có thể do storage, CPU, conflicts hoặc apply delay |
| Tăng max_standby_streaming_delay luôn tốt | Có thể làm replay lag tăng |
| hot_standby_feedback giải quyết mọi replay lag | Có thể gây bloat trên primary |
| Hai node có LSN gần nhau là cùng nhánh | Cần xác nhận timeline |
| pg_stat_replication hiển thị toàn bộ cascading tree | Chỉ hiển thị standby kết nối trực tiếp |
| Drop slot là cách chuẩn để giảm disk | Có thể làm standby mất WAL cần thiết |
| Xóa file trong pg_wal để giải phóng disk | Có thể phá recovery |
| Promotion là thao tác chỉ đổi config | Nó kết thúc recovery và tạo nhánh WAL mới |
| Archive history file không cần thiết | Cần để theo timeline ancestry |
| Standby replay paused nghĩa network lỗi | Có thể là pause chủ động hoặc recovery target |
| Backup thành công đảm bảo rebuild thành công | Cần restore test và xác minh dữ liệu |

---

## 39. Runbook: standby mất kết nối

Một runbook production nên theo trình tự có thể kiểm chứng.

### 39.1. Ghi nhận

- Timestamp sự cố.
- Primary/standby hostname và cluster identifier.
- Timeline ID nếu biết.
- LSN primary cuối cùng.
- Receive/replay LSN cuối cùng trên standby.
- Replication slot và archive state.
- PostgreSQL logs ở cả hai node.

### 39.2. Xác định phạm vi

Kiểm tra primary còn phục vụ ứng dụng không, các standby khác có kết nối không và lỗi có tập trung vào một network segment hay không.

### 39.3. Kiểm tra receiver/sender

- Standby: pg_stat_wal_receiver.
- Primary: pg_stat_replication.
- Logs: authentication, timeout, missing WAL, timeline mismatch.

### 39.4. Kiểm tra network/auth

DNS, route, TCP port, firewall, TLS, pg_hba, replication role và connection string.

### 39.5. Kiểm tra WAL retention

Slot, restart_lsn, max_slot_wal_keep_size, wal_keep_size, archive continuity và disk usage.

### 39.6. Chọn recovery path

- Cùng timeline, WAL còn đủ: reconnect.
- WAL ở archive: restore qua archive.
- Diverged timeline, rewind đủ điều kiện: pg_rewind.
- WAL mất hoặc rewind không phù hợp: pg_basebackup.

### 39.7. Theo dõi catch-up

Đo sent/write/flush/replay LSN, bytes behind, WAL rate, disk latency và receiver state.

### 39.8. Xác minh

Kiểm tra row mẫu, số liệu nghiệp vụ, application smoke tests và replication stability.

### 39.9. Kết thúc incident

Ghi root cause, thời gian gián đoạn, data loss nếu có, phương pháp phục hồi, backup reference và thay đổi cần thực hiện.

---

## 40. Thiết kế monitoring và alerting

Một hệ thống replication production nên có alert cho các trạng thái và trend quan trọng.

### 40.1. Connection state

Alert khi standby dự kiến không xuất hiện trong pg_stat_replication quá thời gian cho phép.

### 40.2. Receiver health

Alert khi pg_stat_wal_receiver không có row hoặc last message receipt quá cũ trong lúc primary đang tạo WAL.

### 40.3. WAL backlog

Theo dõi bytes behind theo sent/write/flush/replay LSN. Dùng ngưỡng theo workload/SLO thay vì một ngưỡng cố định cho mọi cluster.

### 40.4. Catch-up rate

Đo backlog reduction rate. Nếu backlog không giảm trong khi workload hoạt động, standby không catch up.

### 40.5. Slot retention

Alert theo retained WAL bytes, slot inactive duration, wal_status và safe_wal_size khi version hỗ trợ.

### 40.6. Disk capacity

Alert theo free space, growth rate và estimated time to full cho filesystem pg_wal và archive.

### 40.7. Archive health

Theo dõi pg_stat_archiver, archive failures, last archived time và continuity checks.

### 40.8. Timeline events

Ghi nhận promotion, TLI mới, history file mới và rejoin operations. Alert nếu standby theo timeline cũ quá lâu sau failover.

### 40.9. Replay conflicts

Theo dõi recovery conflicts, canceled standby queries và apply delay nếu workload đọc trên standby.

### 40.10. Không alert chỉ dựa vào timestamp replay

Khi primary idle, timestamp có thể không đổi. Kết hợp LSN, workload activity và receiver messages.

---

## 41. Sizing retention và catch-up capacity

### 41.1. Ước lượng WAL generation

Lấy delta wal_bytes trong pg_stat_wal theo khoảng thời gian:

```sql
SELECT
    wal_bytes,
    stats_reset
FROM pg_catalog.pg_stat_wal;
```

Lấy snapshot theo thời gian để tính bytes/second hoặc bytes/minute. Counter có thể reset nên cần kiểm tra stats_reset.

### 41.2. Ước lượng thời gian offline

Xác định thời gian standby có thể mất kết nối trong kịch bản bảo trì/sự cố.

### 41.3. Ước lượng WAL cần giữ

WAL rate peak × outage window + headroom. Cộng thêm các consumer khác và retention requirements.

### 41.4. Catch-up throughput

Standby phải replay nhanh hơn WAL generation rate trong một khoảng thời gian thì backlog mới giảm. Nếu không, tăng tài nguyên/điều chỉnh workload hoặc chấp nhận rebuild.

### 41.5. Disk headroom

Slot retention có thể giữ WAL vượt max_wal_size. Disk sizing cần bao gồm peak WAL, archive backlog, slot backlog và thời gian xử lý sự cố.

### 41.6. Capacity là một phần của RPO/RTO

Nếu WAL bị recycle trước khi standby quay lại, thời gian phục hồi tăng đáng kể vì phải tạo base backup. Retention policy ảnh hưởng trực tiếp RTO.

---

## 42. Bảo mật và quyền vận hành

### 42.1. Replication user tối thiểu

Dùng role chuyên biệt có LOGIN/REPLICATION, không dùng superuser cho streaming replication thông thường.

### 42.2. Network allowlist

Giới hạn replication connections theo subnet/host, TLS và firewall rules.

### 42.3. Secret handling

Không ghi password vào logs, scripts được commit hoặc ticket. Dùng passfile/secret store và rotation.

### 42.4. Quyền data directory

Chỉ OS account PostgreSQL và công cụ quản trị được cấp quyền cần thiết. Không để nhiều người dùng ghi vào data directory.

### 42.5. pg_rewind/base backup permissions

Các công cụ này có thể đọc/ghi nhiều dữ liệu. Chỉ người vận hành được ủy quyền chạy và phải xác minh target path/source trước khi thực hiện.

### 42.6. Archive security

WAL archive có thể chứa dữ liệu đủ để tái tạo thay đổi. Bảo vệ quyền đọc, encryption at rest, retention và immutable copies.

---

## 43. Bài tập thực hành

### Bài 1 — Replication architecture

Vẽ luồng WAL từ primary tới standby, nêu vai trò WAL sender, WAL receiver và startup process.

### Bài 2 — Sent/write/flush/replay

Phân biệt bốn LSN trong pg_stat_replication và nêu cách xác định giai đoạn chậm.

### Bài 3 — Receiver status

Viết truy vấn xem pg_stat_wal_receiver và giải thích vì sao view có thể không có row.

### Bài 4 — Receive vs replay

Standby receive LSN tiến nhưng replay LSN đứng. Liệt kê các nguyên nhân cần điều tra.

### Bài 5 — LSN distance

Dùng pg_wal_lsn_diff tính bytes behind. Vì sao cần xác nhận cùng timeline?

### Bài 6 — Lag time

Giải thích write_lag/flush_lag/replay_lag và vì sao chúng có thể NULL khi idle.

### Bài 7 — Network

Lập danh sách kiểm tra DNS, routing, firewall, port và TLS khi receiver không kết nối.

### Bài 8 — Authentication

Viết replication role và pg_hba rule phù hợp. Giải thích quyền REPLICATION và SCRAM/TLS.

### Bài 9 — primary_conninfo

Nêu các trường cần có và cách bảo vệ credentials.

### Bài 10 — WAL sender capacity

Vì sao cần tính max_wal_senders cho standby và backup streams?

### Bài 11 — Replication slot

Giải thích restart_lsn và tại sao slot inactive có thể làm pg_wal tăng.

### Bài 12 — wal_keep_size

Vì sao wal_keep_size không bảo đảm WAL vô hạn cho standby?

### Bài 13 — max_slot_wal_keep_size

Mô tả trade-off giữa giữ WAL vô hạn và giới hạn retention.

### Bài 14 — Archive catch-up

Thiết kế restore_command để lấy WAL từ archive và nêu điều kiện archive success.

### Bài 15 — Missing WAL

Standby log requested WAL segment has already been removed. Lập thứ tự điều tra slot, archive, timeline và disk.

### Bài 16 — Reconnect

Standby mất kết nối 10 phút, WAL vẫn còn. Mô tả quy trình reconnect và kiểm tra catch-up.

### Bài 17 — Replay bottleneck

Flush LSN gần sent LSN nhưng replay LSN chậm. Đề xuất điều tra CPU, disk, query conflicts và replay pause.

### Bài 18 — Replay delay

Một standby có recovery_min_apply_delay. Vì sao last replay timestamp cũ không nhất thiết là lỗi?

### Bài 19 — Timeline divergence

Primary mới được promote nhưng standby vẫn theo timeline cũ. Vì sao chỉ đổi primary_conninfo có thể chưa đủ?

### Bài 20 — pg_rewind

Giải thích mục đích của pg_rewind và vì sao nó chỉ dành cho hai nhánh có ancestry chung.

### Bài 21 — Rewind prerequisites

Liệt kê yêu cầu clean shutdown, checksums/wal_log_hints, full_page_writes và WAL từ fork point.

### Bài 22 — Rewind command

Viết ví dụ pg_rewind với source-server và target-pgdata. Nêu rủi ro của target path.

### Bài 23 — Rewind archive

Khi nào dùng restore-target-wal? Điều kiện nào cần có trên target?

### Bài 24 — Base backup

Viết lệnh pg_basebackup dùng -R, -X stream và replication slot. Giải thích -C và -S.

### Bài 25 — Rebuild decision

Đưa ra tiêu chí chọn pg_rewind hay pg_basebackup trong bốn tình huống WAL gap, divergence, corruption và missing archive.

### Bài 26 — Rejoin verification

Sau rebuild, viết các truy vấn xác nhận pg_is_in_recovery, receiver, primary replication state và replay progress.

### Bài 27 — Slot invalidation

Một slot đã mất WAL cần thiết. Vì sao tạo slot mới không khôi phục được segments cũ?

### Bài 28 — Disk pressure

Filesystem pg_wal còn 5%. Viết runbook xử lý archive backlog, slot retention và workload spike.

### Bài 29 — Monitoring

Thiết kế dashboard có connection status, receive/replay LSN, bytes behind, slot retention, archive failures và disk time-to-full.

### Bài 30 — Catch-up throughput

WAL generation 20 MB/s, standby replay 15 MB/s. Backlog sẽ thay đổi ra sao? Đề xuất cách điều tra và xử lý.

### Bài 31 — Synchronous replication

Một synchronous standby mất connection. Hành vi commit có thể thay đổi thế nào tùy synchronous_commit và quorum configuration?

### Bài 32 — Failover

Primary không phản hồi nhưng có thể đang bị network partition. Vì sao phải fence trước khi promote?

### Bài 33 — Cascading replication

Một cascading standby bị mất upstream. Nêu các node và WAL paths cần kiểm tra.

### Bài 34 — Archive retention

Thiết kế retention cho primary tạo 100 GB WAL/ngày và standby có thể offline 8 giờ. Những headroom và consumer nào cần tính?

### Bài 35 — Base backup load

Một pg_basebackup làm tăng latency primary. Đề xuất cách giới hạn/tổ chức backup và đo tác động.

### Bài 36 — Restore drill

Thiết kế test tạo standby mới từ base backup, bắt kịp WAL archive và xác minh dữ liệu ứng dụng.

### Bài 37 — Version compatibility

Một query pg_replication_slots dùng cột safe_wal_size lỗi trên PostgreSQL cũ. Xây dựng cách khám phá schema và viết query tương thích.

### Bài 38 — Logs

Nêu các nhóm log messages giúp phân biệt network timeout, authentication failure, missing WAL và timeline mismatch.

### Bài 39 — Security

Thiết kế replication user, TLS, pg_hba allowlist, passfile và quyền data directory.

### Bài 40 — End-to-end operations

Một hệ thống có một primary, ba standby ở hai vùng, WAL archive 7 ngày, một logical consumer và RPO 1 phút. Thiết kế slot policy, WAL retention, catch-up, rewind/rebuild, alerting, failover fencing và restore drills. Phân tích trade-off RPO/RTO, disk, network và latency.

---

## 44. Checklist vận hành mất kết nối và khởi tạo lại standby

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| Primary đang hoạt động? | Health, logs, pg_is_in_recovery |
| Standby đang recovery? | pg_is_in_recovery |
| Có WAL sender connection? | pg_stat_replication |
| WAL receiver có row? | pg_stat_wal_receiver |
| State là streaming/catchup? | Replication state |
| Host/port đúng? | primary_conninfo |
| DNS/routing hoạt động? | Network diagnostics |
| Firewall cho phép? | TCP allowlist |
| TLS hợp lệ? | CA/hostname/certificate |
| pg_hba rule đúng? | pg_hba_file_rules |
| Replication role hợp lệ? | LOGIN/REPLICATION |
| Đủ WAL sender capacity? | max_wal_senders |
| Slot tồn tại? | pg_replication_slots |
| Slot active/inactive? | active |
| restart_lsn còn cần? | Retention analysis |
| Slot có bị invalidated? | wal_status/version fields |
| wal_keep_size phù hợp? | Offline window |
| max_slot_wal_keep_size phù hợp? | Disk vs retention |
| Archive mode hoạt động? | pg_stat_archiver |
| WAL archive liên tục? | Manifest/checksum |
| restore_command chạy được? | Test fetch |
| Timeline có khớp? | TLI + history files |
| recovery_target_timeline phù hợp? | latest/current/specific |
| Receive LSN tiến? | pg_last_wal_receive_lsn |
| Replay LSN tiến? | pg_last_wal_replay_lsn |
| Replay có pause? | pg_is_wal_replay_paused |
| Disk/CPU đủ? | OS metrics |
| Read query conflicts? | Standby conflict stats/logs |
| WAL generation rate? | pg_stat_wal delta |
| Backlog có giảm? | Time-series LSN gap |
| Có thể reconnect/catch-up? | WAL còn đủ |
| Có cần pg_rewind? | Timeline divergence + prerequisites |
| Target shutdown cleanly? | pg_rewind precondition |
| Checksums hoặc wal_log_hints? | Được bật trước divergence |
| full_page_writes bật? | Rewind requirement |
| WAL từ fork point đủ? | Local/archive |
| Có snapshot trước rewind? | Recovery safety |
| Nếu rewind không được, có base backup? | Rebuild plan |
| Data directory đích an toàn? | Rỗng/đúng target |
| pg_basebackup -R/-X/-S phù hợp? | Backup plan |
| Slot mới được quản lý? | Ownership/retention |
| Standby signal/config đúng? | standby.signal/conninfo |
| Rebuild có cùng major version? | Compatibility |
| Rejoin hoàn tất? | Receiver/replay state |
| Dữ liệu ứng dụng đúng? | Smoke tests |
| Archive/slot disk còn headroom? | Capacity alerts |
| Incident có root cause? | Logs/timeline/LSN |

## Kết luận

Xử lý standby mất kết nối trong PostgreSQL cần phân biệt rõ lỗi kết nối, WAL retention và timeline divergence. Khi standby vẫn ở cùng lịch sử và WAL còn đầy đủ, khôi phục connection để nó tự catch up là đủ. Khi WAL đã rời pg_wal nhưng archive còn liên tục, restore_command có thể cung cấp các segments thiếu. Khi standby đã đi sang nhánh khác, pg_rewind có thể đưa nó về nhánh authoritative nếu đáp ứng đầy đủ điều kiện. Nếu WAL bắt buộc đã mất, data directory hỏng hoặc rewind không phù hợp, cần tạo lại standby từ base backup.

Những nguyên tắc cần nhớ:

1. **Kiểm tra cả hai đầu replication.** pg_stat_replication trên primary và pg_stat_wal_receiver trên standby cho biết trạng thái connection ở hai phía.
2. **Phân biệt sent, write, flush và replay.** Chúng chỉ ra WAL đang chậm ở khâu gửi, ghi, flush hay apply.
3. **Dùng LSN để đo backlog, kèm timeline.** LSN distance là bytes; không dùng LSN của hai nhánh divergent như cùng một stream.
4. **Lag time không phải catch-up ETA.** Đo bytes behind, WAL generation rate và replay throughput theo thời gian.
5. **Replication slot giữ WAL nhưng tiêu thụ disk.** Slot inactive có thể làm pg_wal tăng; cần giới hạn và cảnh báo.
6. **wal_keep_size không thay archive hoặc slot.** Nó chỉ duy trì một lượng WAL tối thiểu cho reconnect.
7. **Archive cần liên tục và đúng timeline.** Một segment hoặc history file bị thiếu có thể chặn recovery.
8. **Reconnect khi WAL còn đủ.** Không tạo lại standby chỉ vì có một lần network disconnect.
9. **pg_rewind dành cho timeline divergence.** Kiểm tra clean shutdown, checksums hoặc wal_log_hints, full_page_writes và WAL từ fork point.
10. **pg_basebackup tạo bản sao vật lý mới.** Dùng khi WAL không còn, target hỏng hoặc rewind không đáp ứng điều kiện.
11. **Rebuild phải được kiểm chứng.** Kiểm tra receiver, replay LSN, timeline, slot, dữ liệu mẫu và ứng dụng.
12. **Không xóa WAL thủ công.** Xử lý archive, slot, capacity và rebuild theo runbook.
13. **Fencing trước promotion.** Mất kết nối không chứng minh primary đã chết; tránh split brain.
14. **Restore drills chứng minh khả năng phục hồi.** Kiểm thử cả archive catch-up, rewind và base backup trên môi trường riêng.

Một standby khỏe mạnh không chỉ có connection state là streaming. Nó phải nhận đúng WAL, flush và replay tiến triển, theo đúng timeline, còn đủ WAL retention để vượt qua gián đoạn dự kiến và có phương án reinitialize đã được kiểm thử khi không thể bắt kịp lịch sử hiện tại.
