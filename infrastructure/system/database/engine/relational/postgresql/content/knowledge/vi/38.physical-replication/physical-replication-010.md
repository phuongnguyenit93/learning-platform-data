# Write lag, flush lag, replay lag và cách đo độ trễ trong PostgreSQL

## 1. Vì sao cần đo replication lag theo nhiều giai đoạn?

Trong PostgreSQL physical streaming replication, primary gửi WAL tới standby. Standby nhận WAL, ghi WAL vào storage, flush WAL bền vững rồi replay các record để cập nhật data pages và trạng thái transaction. Các bước này diễn ra liên tục, nhưng không nhất thiết hoàn tất cùng một thời điểm.

Một dashboard chỉ hiển thị “replication lag = 10 giây” thường chưa đủ để tìm nguyên nhân. Standby có thể chậm vì network, tốc độ ghi storage, flush latency, replay workload, recovery conflicts hoặc vì primary tạo WAL nhanh hơn standby xử lý.

PostgreSQL cung cấp các vị trí LSN và các chỉ số thời gian để quan sát từng giai đoạn:

- **Write lag:** độ trễ tới khi standby báo đã ghi WAL.
- **Flush lag:** độ trễ tới khi standby báo đã flush WAL.
- **Replay lag:** độ trễ tới khi standby báo đã replay WAL.
- **LSN/byte lag:** khoảng cách vị trí WAL giữa các giai đoạn.
- **Rate/backlog trend:** tốc độ tạo WAL, tốc độ replay và xu hướng backlog tăng hay giảm.

```text
PRIMARY
  WAL generated
       |
       v
  sent_lsn
       |
       | network / sender queue
       v
STANDBY
  write_lsn       <- WAL đã được ghi
       |
       | storage flush
       v
  flush_lsn       <- WAL đã flush
       |
       | recovery / replay
       v
  replay_lsn      <- WAL đã áp dụng
       |
       v
  Data pages / visible state
```

**Không có một con số lag duy nhất giải thích mọi vấn đề.** Cần đọc write, flush và replay cùng LSN backlog, trạng thái kết nối, workload và chế độ đồng bộ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả đường đi WAL từ primary tới standby.
2. Phân biệt sent, write, flush và replay LSN.
3. Giải thích ý nghĩa của write_lag, flush_lag và replay_lag.
4. Phân biệt time lag với byte lag và replication backlog.
5. Đo từng queue bằng pg_wal_lsn_diff.
6. Đo WAL generation rate và replay rate theo thời gian.
7. Ước lượng thời gian catch-up khi standby có thể xử lý backlog.
8. Đọc pg_stat_replication, pg_stat_wal_receiver và pg_stat_activity.
9. Phân biệt replication lag với archive lag và replication slot retention.
10. Hiểu synchronous replication và synchronous_commit.
11. Nhận diện replay delay có chủ ý và recovery conflicts.
12. Xây dashboard, alert và runbook điều tra lag.
13. Đo lag bằng transaction markers khi cần bằng chứng nghiệp vụ.
14. Tránh diễn giải sai các giá trị NULL hoặc timestamp cũ khi hệ thống idle.

---

## 2. Các giai đoạn của physical streaming replication

Một WAL record được tạo trên primary trước khi nó có thể được gửi tới standby. WAL sender truyền dữ liệu qua replication connection. WAL receiver trên standby tiếp nhận dữ liệu và ghi vào WAL storage. Sau đó recovery process replay WAL để cập nhật trạng thái database.

| Giai đoạn | Vị trí thường quan sát | Ý nghĩa |
|---|---|---|
| WAL generation | pg_current_wal_lsn() trên primary | WAL đã được ghi tới vị trí hiện tại |
| WAL sent | sent_lsn | Vị trí WAL cuối đã gửi trên connection |
| WAL written | write_lsn | Vị trí standby báo đã ghi WAL |
| WAL flushed | flush_lsn | Vị trí standby báo đã flush WAL |
| WAL replayed | replay_lsn | Vị trí standby đã replay WAL |

Các LSN này tạo thành một chuỗi vị trí để phân tích backlog. Tên cột và một số chi tiết quan sát có thể khác theo PostgreSQL major version; kiểm tra view trên server thực tế.

### 2.1. Sent không đồng nghĩa written

Primary có thể đã gửi một đoạn WAL nhưng standby chưa xác nhận đã ghi xuống file. Khoảng cách giữa sent_lsn và write_lsn gợi ý dữ liệu đang nằm trong đường truyền/receiver buffer hoặc chưa được xác nhận ghi.

### 2.2. Written không đồng nghĩa flushed

WAL có thể đã được ghi vào filesystem nhưng chưa được xác nhận flush bền vững. Khoảng cách giữa write_lsn và flush_lsn phản ánh phần chờ flush.

### 2.3. Flushed không đồng nghĩa replayed

WAL có thể đã bền vững trên standby nhưng recovery chưa áp dụng hết. Khoảng cách giữa flush_lsn và replay_lsn là backlog ở giai đoạn replay.

### 2.4. Replay không đồng nghĩa mọi query thấy cùng một thời điểm

Standby query có thể đọc snapshot nhất quán tại thời điểm transaction bắt đầu. Một query đang chạy không tự chuyển snapshot sang dữ liệu vừa replay sau khi query bắt đầu.

## 3. LSN là gì?

LSN (Log Sequence Number) là vị trí trong WAL stream. PostgreSQL thường hiển thị LSN dạng:

```text
0/16B6C50
```

LSN không phải timestamp, transaction ID hay row ID. Có thể dùng pg_wal_lsn_diff để tính khoảng cách byte giữa hai vị trí WAL.

Ví dụ:

```sql
SELECT pg_wal_lsn_diff('0/2000100', '0/2000000') AS bytes_between;
```

Kết quả là khoảng cách tính theo byte giữa hai LSN.

### 3.1. So sánh LSN cùng lịch sử WAL

LSN chỉ có ý nghĩa trong context của cùng cluster/WAL history. Sau promotion, timeline có thể thay đổi. Không lấy LSN từ hai cluster độc lập rồi trừ cho nhau như thể chúng là một chuỗi chung.

### 3.2. LSN tăng không có nghĩa row count tăng

WAL còn chứa index changes, page images, catalog changes, full-page writes và nhiều hoạt động nội bộ. Lượng WAL không bằng số bytes dữ liệu nghiệp vụ.

### 3.3. LSN diff là backlog byte, không phải thời gian

100 MB lag có thể tương ứng vài giây trên storage nhanh hoặc nhiều phút trên standby chậm. Muốn ước lượng thời gian cần đo throughput và WAL generation rate.

## 4. Write lag là gì?

write_lag trong pg_stat_replication biểu diễn khoảng thời gian từ lúc primary flush WAL gần đây tới khi primary nhận thông báo standby đã ghi WAL tương ứng.

Nó giúp trả lời: **WAL tới standby và được ghi tới mức nào nhanh chóng?**

Một write lag cao có thể liên quan:
- Network latency hoặc packet loss.
- Standby receiver/OS scheduling.
- Storage write queue.
- CPU pressure.
- WAL sender/receiver congestion.
- Standby bị quá tải bởi workload khác.

### 4.1. Write lag không chỉ là network latency

Metric bao gồm đường đi từ primary tới standby và quá trình standby ghi/acknowledge. Không kết luận network chậm chỉ từ write_lag.

### 4.2. Write lag thấp nhưng flush lag cao

Điều này gợi ý standby ghi được WAL nhưng flush xuống storage chậm. Kiểm tra disk latency, fsync, storage queue và write cache guarantees.

### 4.3. Write lag thấp nhưng replay lag cao

WAL đã được truyền và ghi tương đối nhanh, nhưng standby chưa replay kịp. Điều tra replay throughput, query workload và recovery conflicts.

## 5. Flush lag là gì?

flush_lag biểu diễn khoảng thời gian từ lúc primary flush WAL gần đây tới khi primary nhận thông báo standby đã flush WAL tương ứng.

Flush là mốc quan trọng cho durability của WAL trên standby. Với synchronous replication và synchronous_commit = on, commit có thể chờ standby flush WAL theo semantics PostgreSQL.

Flush lag cao có thể do:
- Storage latency cao.
- fsync chậm.
- WAL receiver flush bị chậm.
- Disk contention từ query/backup/checkpoint.
- Filesystem hoặc cloud volume bị throttling.
- I/O queue tăng.

### 5.1. Flush lag không phải thời gian mất dữ liệu chính xác

Đây là chỉ số thời gian giữa các mốc WAL gần đây, không trực tiếp đo transaction cuối cùng sẽ mất khi primary chết. Actual RPO cần xác minh acknowledged transactions và standby được promote.

### 5.2. Flush lag cao trong synchronous replication

Nếu transaction đang chờ flush trên standby, commit latency của ứng dụng có thể tăng. Xem synchronous_commit, synchronous_standby_names, sync_state và wait events.

### 5.3. Flush lag thấp không chứng minh replay đã theo kịp

Standby có thể đã flush WAL bền vững nhưng replay vẫn còn backlog. Kiểm tra replay_lsn và replay lag riêng.

## 6. Replay lag là gì?

replay_lag biểu diễn khoảng thời gian từ lúc primary flush WAL gần đây tới khi primary nhận thông báo standby đã replay WAL tương ứng.

Replay là bước recovery áp dụng WAL để cập nhật database state trên standby. Nó có thể chậm dù network và flush đều tốt.

Nguyên nhân thường gặp:
- WAL generation rate cao hơn replay capacity.
- Storage đọc/ghi chậm.
- CPU thiếu.
- Query workload trên standby cạnh tranh tài nguyên.
- Recovery conflict với long-running read queries.
- recovery_min_apply_delay được cấu hình có chủ ý.
- Checkpoint/recovery I/O.
- Một batch transaction lớn hoặc index build tạo nhiều WAL.

### 6.1. Replay lag không phải queue duration chính xác

Đây là thời gian của các WAL changes gần đây được xác nhận replay. Không diễn giải như “standby còn đúng 30 giây mới catch up”.

### 6.2. Standby idle có thể có replay lag NULL

Khi không có WAL mới, không có mẫu giao dịch gần đây để tính một số lag intervals. NULL không tự có nghĩa standby hỏng.

### 6.3. Replay timestamp cũ có thể chỉ vì primary idle

pg_last_xact_replay_timestamp() là thời điểm transaction cuối cùng được replay trong recovery. Nếu primary không có transaction mới, timestamp này không đổi dù standby đã theo kịp.

## 7. Các time lag fields trong pg_stat_replication

Trên primary:

```sql
SELECT
    application_name,
    state,
    sync_state,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_stat_replication
ORDER BY application_name;
```

Các field:
- write_lag: thời gian tới acknowledgment ghi WAL.
- flush_lag: thời gian tới acknowledgment flush WAL.
- replay_lag: thời gian tới acknowledgment replay WAL.
- reply_time: thời điểm primary nhận phản hồi gần nhất từ standby.

### 7.1. Chúng được đo trên primary

pg_stat_replication là view phía primary, mỗi row đại diện một WAL sender connection tới standby. Nếu query view trên standby mà không có rows thì đó là hành vi bình thường.

### 7.2. NULL không phải zero

Nếu lag field là NULL, không tự thay bằng 0 khi diễn giải. Ghi rõ “không có mẫu/không có giá trị” và xem state, LSN positions, reply time và workload.

### 7.3. Các lag fields không phải ETA

PostgreSQL mô tả các time lag fields như độ trễ của các transaction gần đây trước khi đồng bộ. Chúng không dự báo thời gian standby cần để catch up sau khi primary ngừng ghi.

### 7.4. Không dùng một field làm health check duy nhất

Một standby có thể state = streaming nhưng replay backlog đang tăng. Ngược lại lag time có thể NULL trong lúc idle mà standby hoàn toàn khỏe.

## 8. Đo byte lag bằng LSN trên primary

Query tổng hợp:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        sent_lsn
    ) AS not_yet_sent_bytes,
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
    ) AS flushed_not_replayed_bytes,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS total_replay_backlog_bytes
FROM pg_stat_replication
ORDER BY application_name;
```

### 8.1. Cách đọc

- not_yet_sent_bytes: WAL primary đã ghi nhưng chưa được gửi theo connection.
- sent_not_written_bytes: WAL đã gửi nhưng standby chưa xác nhận ghi.
- written_not_flushed_bytes: WAL đã ghi nhưng chưa xác nhận flush.
- flushed_not_replayed_bytes: WAL đã flush nhưng chưa xác nhận replay.
- total_replay_backlog_bytes: khoảng cách từ WAL hiện tại trên primary tới replay position của standby.

Đây là các khoảng cách LSN tại thời điểm quan sát, không phải dung lượng chính xác của từng buffer hoặc file queue nội bộ.

### 8.2. Lưu ý về snapshot

Các stats và LSN positions có thể cập nhật ở những thời điểm hơi khác nhau. Một số giá trị có thể lệch nhẹ giữa các mẫu; hãy nhìn xu hướng thay vì kết luận từ một snapshot đơn lẻ.

### 8.3. Không cộng mọi queue một cách máy móc

Các đoạn là những phần của cùng một WAL span theo thứ tự. total_replay_backlog_bytes đã bao gồm các giai đoạn trước replay. Không cộng nó thêm với các queue thành phần.

## 9. Đo LSN positions trên standby

Trên standby, có thể xem:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS last_receive_lsn,
    pg_last_wal_replay_lsn() AS last_replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_transaction_time;
```

- pg_last_wal_receive_lsn() cho biết vị trí WAL cuối đã nhận và đồng bộ xuống disk theo semantics của function.
- pg_last_wal_replay_lsn() cho biết vị trí WAL cuối đã replay.
- pg_last_xact_replay_timestamp() cho biết timestamp transaction cuối cùng được replay trong recovery.

### 9.1. Receive và replay khác nhau

Nếu receive LSN tiến nhanh nhưng replay LSN đứng yên, standby đang nhận WAL nhưng recovery chưa theo kịp hoặc đang bị chặn.

### 9.2. Chạy cùng thời điểm với primary

Để tính end-to-end lag theo bytes, so sánh primary current LSN với standby replay LSN trong cùng sampling window, đồng thời ghi timestamp/server identity.

### 9.3. pg_is_in_recovery()

Function này giúp xác định server đang ở recovery/standby mode. Sau promotion, nó trả trạng thái khác; dashboard phải nhận diện role thay vì tiếp tục áp công thức standby.

## 10. pg_stat_replication: view quan trọng trên primary

View này cung cấp trạng thái WAL sender/standby:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state,
    sync_priority,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_stat_replication;
```

### 10.1. Các cột nhận diện connection

- pid: process WAL sender.
- application_name: tên standby/client khai báo.
- client_addr: địa chỉ client nếu có.
- state: trạng thái replication.
- sync_state: vai trò synchronous/asynchronous hiện tại.

### 10.2. Nhiều standby cần xem từng row

Một primary có thể gửi WAL tới nhiều standby. Một standby khỏe không có nghĩa mọi standby đều khỏe. Theo dõi từng application_name và client_addr.

### 10.3. State streaming

state = 'streaming' cho biết connection đang streaming WAL. Nó không tự chứng minh lag thấp, replay nhanh hay synchronous policy đạt yêu cầu.

### 10.4. Quyền xem stats

Một số thông tin có thể bị giới hạn nếu role không có quyền xem stats đầy đủ. Dùng role monitoring phù hợp, ví dụ pg_monitor theo chính sách bảo mật.

## 11. pg_stat_wal_receiver: view trên standby

Trên standby, view pg_stat_wal_receiver cho biết trạng thái WAL receiver.

Ví dụ:

```sql
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
```

Các cột cụ thể có thể thay đổi theo version. Kiểm tra view trên server thực tế trước khi chuẩn hóa query monitoring lâu dài.

### 11.1. status

Khi streaming bình thường, status thường hiển thị streaming. Không có row có thể nghĩa là standby không dùng streaming connection tại thời điểm query hoặc đang ở một trạng thái recovery khác.

### 11.2. last_msg_receipt_time

Thời điểm standby nhận message gần nhất từ sender. Nếu cũ bất thường trong lúc primary có write workload, cần kiểm tra network, sender, receiver và connection.

### 11.3. latest_end_lsn

Vị trí WAL cuối mà receiver biết sender đã thông báo. Đây là tín hiệu hữu ích nhưng vẫn cần so với receive/replay positions và primary current LSN.

### 11.4. Không nhầm receiver với replay process

WAL receiver nhận dữ liệu; recovery process replay dữ liệu. Một receiver streaming không đảm bảo replay đang tiến triển.

## 12. Phân biệt lag với archive lag

Streaming replication và WAL archiving là hai đường riêng.

| Tín hiệu | View/công cụ | Đường dữ liệu |
|---|---|---|
| Streaming replication lag | pg_stat_replication | Primary → standby |
| WAL receive/replay | pg_stat_wal_receiver, recovery functions | Receiver/recovery trên standby |
| Archive success/failure | pg_stat_archiver | Primary → archive repository |
| Archive freshness | Archive inventory/logs | WAL segments → backup storage |
| Slot retention | pg_replication_slots | WAL giữ lại cho consumer |

### 12.1. Standby có thể theo kịp nhưng archive bị lỗi

Streaming WAL vẫn đến standby, trong khi archive command thất bại. PITR archive chain có thể bị đứt dù failover standby vẫn có vẻ tốt.

### 12.2. Archive có thể khỏe nhưng standby lag

WAL archive có thể lưu segment nhanh, nhưng network/receiver/replay standby bị chậm.

### 12.3. Theo dõi hai mục tiêu riêng

- Standby lag: khả năng phục vụ read/failover.
- Archive lag: khả năng PITR/backup recovery.

Không gộp hai metrics thành một trạng thái replication.

## 13. Phân biệt lag với replication slot retention

Replication slot giữ WAL cần cho consumer. Nó có thể làm pg_wal tăng, nhưng không tự nói standby đang replay chậm bao nhiêu.

Kiểm tra:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    xmin,
    catalog_xmin
FROM pg_replication_slots
ORDER BY slot_name;
```

### 13.1. restart_lsn

Vị trí WAL cũ nhất mà slot có thể còn cần. Slot giữ WAL từ vị trí này để consumer có thể tiếp tục.

### 13.2. Slot inactive

Slot inactive có thể vẫn giữ WAL. Kiểm tra owner/consumer trước khi xóa hoặc invalidate.

### 13.3. Ước lượng WAL retention distance

```sql
SELECT
    slot_name,
    active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS retained_wal_distance_bytes
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
```

Đây là khoảng cách LSN, không phải chính xác số bytes đang chiếm trên filesystem. WAL segments được quản lý/recycle theo segment boundaries và có thể còn được giữ vì các lý do khác.

### 13.4. Không xóa slot để chữa lag theo phản xạ

Xóa slot có thể khiến standby/CDC consumer mất khả năng tiếp tục từ vị trí cũ. Đánh giá khả năng resync và recovery trước.

## 14. Time lag và byte lag trả lời câu hỏi khác nhau

| Metric | Trả lời câu hỏi | Hạn chế |
|---|---|---|
| write_lag | WAL write acknowledgment gần đây trễ bao lâu? | Không phải catch-up ETA |
| flush_lag | WAL flush acknowledgment gần đây trễ bao lâu? | Không trực tiếp là actual RPO |
| replay_lag | WAL replay acknowledgment gần đây trễ bao lâu? | Không phải thời gian còn lại |
| LSN byte gap | Standby cách primary bao nhiêu WAL bytes? | Không cho biết tốc độ |
| Backlog growth rate | Lag đang tăng hay giảm? | Cần nhiều samples |
| Replay throughput | Standby áp dụng WAL nhanh bao nhiêu? | Phụ thuộc workload và thời gian đo |
| Marker gap | Commit marker nào bị thiếu? | Chỉ đại diện cadence/transaction path được test |

### 14.1. Khi nào ưu tiên byte lag?

Khi cần biết lượng WAL còn chờ, đánh giá storage/network capacity hoặc dự báo replay work.

### 14.2. Khi nào ưu tiên time lag?

Khi cần theo dõi độ trễ của các commit gần đây hoặc một mục tiêu nghiệp vụ được định nghĩa theo thời gian.

### 14.3. Khi nào cần transaction marker?

Khi cần bằng chứng gần với actual acknowledged data loss, đặc biệt trong failover drill hoặc RPO validation.

## 15. Đo queue theo từng chặng

Một query có thể tính các khoảng cách:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS sent_to_write_bytes,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS write_to_flush_bytes,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS flush_to_replay_bytes
FROM pg_stat_replication;
```

### 15.1. Sent-to-write lớn

Điều tra:
- Network throughput/latency.
- Receiver CPU.
- Standby scheduling.
- WAL receiver process state.
- Network retransmits/packet loss.

### 15.2. Write-to-flush lớn

Điều tra:
- Storage latency.
- fsync latency.
- IOPS/throughput throttling.
- Disk queue depth.
- Filesystem/cache behavior.

### 15.3. Flush-to-replay lớn

Điều tra:
- Replay process CPU/I/O.
- Recovery conflicts.
- Query load trên standby.
- recovery_min_apply_delay.
- Batch transactions hoặc WAL bursts.

### 15.4. Không chỉ nhìn queue lớn nhất

Một queue lớn có thể là hậu quả của queue upstream. Kiểm tra tốc độ từng stage và xu hướng trước khi kết luận bottleneck.

## 16. Đo WAL generation rate

Trên primary, lấy LSN ở hai thời điểm:

```sql
SELECT
    clock_timestamp() AS sampled_at,
    pg_current_wal_lsn() AS current_lsn;
```

Lưu sample bên ngoài hoặc trong monitoring. Với hai samples:

```text
WAL generation rate
  = diff(current_lsn_2, current_lsn_1)
    / elapsed_seconds
```

Đơn vị là bytes/second nếu pg_wal_lsn_diff trả bytes.

### 16.1. Workload thay đổi theo thời gian

Một hệ thống có thể tạo 2 MB/s vào giờ thấp điểm và 100 MB/s trong batch window. Dùng average dài hạn có thể che peak cần capacity.

### 16.2. WAL generation không phải data growth

WAL bao gồm index/page changes, full-page images, catalog operations và các hoạt động khác. WAL rate không bằng lượng row mới.

### 16.3. Đo theo window phù hợp

Dùng nhiều cửa sổ: ngắn để phát hiện burst, dài để thấy trend và capacity baseline.

## 17. Đo replay rate

Trên primary, lấy replay_lsn từ pg_stat_replication theo chu kỳ; hoặc trên standby lấy pg_last_wal_replay_lsn().

```text
Replay rate
  = diff(replay_lsn_2, replay_lsn_1)
    / elapsed_seconds
```

### 17.1. Replay rate phải đo cùng timeline

Sau promotion/timeline change, không nối các samples thuộc hai WAL histories khác nhau mà không xử lý timeline transition.

### 17.2. Replay rate bằng 0

Có thể standby không nhận WAL mới, đang idle, đang bị pause hoặc recovery không tiến triển. Kết hợp receiver status, primary write activity và logs.

### 17.3. Replay rate không ổn định

Một transaction lớn, index build hoặc checkpoint có thể làm replay throughput dao động. Dùng rolling window và nhiều samples.

## 18. Backlog tăng hay giảm?

Giả sử:
- WAL generation rate = 20 MB/s.
- Replay rate = 25 MB/s.
- Replay backlog = 1.000 MB.

Nếu hai tốc độ duy trì gần như ổn định, backlog giảm khoảng 5 MB/s.

Nếu:
- WAL generation rate = 30 MB/s.
- Replay rate = 25 MB/s.

Backlog tăng khoảng 5 MB/s. Standby không thể catch up khi primary tiếp tục tạo WAL nhanh hơn khả năng replay.

### 18.1. Net catch-up rate

```text
net catch-up rate = replay rate - WAL generation rate
```

Nếu kết quả dương, backlog có thể giảm. Nếu bằng 0 hoặc âm, standby không thu hẹp backlog trong điều kiện workload hiện tại.

### 18.2. Ước lượng ETA

```text
estimated catch-up time
  = backlog bytes / net catch-up rate
```

Chỉ dùng khi net catch-up rate dương và workload tương đối ổn định. Đây là estimate, không phải cam kết.

### 18.3. Ví dụ

Backlog 900 MB, replay 60 MB/s, WAL generation 30 MB/s:

- Net catch-up rate = 30 MB/s.
- ETA gần đúng = 900 / 30 = 30 giây.

Nếu replay rate giảm còn 25 MB/s trong khi generation 30 MB/s, ETA không có ý nghĩa vì backlog đang tăng.

### 18.4. Đừng dự báo bằng một sample

Tính rate qua nhiều intervals và xem rolling average. Một spike ngắn có thể làm ETA thay đổi mạnh.

## 19. Đo trên standby bằng pg_stat_wal_receiver

Query mẫu:

```sql
SELECT
    status,
    received_tli,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    now() - last_msg_receipt_time AS message_age
FROM pg_stat_wal_receiver;
```

### 19.1. Message age

Nếu primary có WAL activity mà last message receipt đã cũ, kiểm tra connection, network và receiver. Nếu primary idle, message age phải được diễn giải cùng heartbeat/status behavior.

### 19.2. Received timeline

received_tli giúp biết timeline mà receiver đang xử lý. Khi failover, kiểm tra timeline history và primary connection để xác nhận standby đang theo đúng nhánh.

### 19.3. Kết hợp với replay position

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS receive_to_replay_bytes;
```

Query chỉ phù hợp khi các positions có giá trị và server đang ở recovery context. Nếu NULL, xem receiver state và role.

## 20. Đọc wait events để xác định bottleneck

pg_stat_activity cung cấp wait event của backend, gồm WAL sender/receiver và các process liên quan.

Ví dụ:

```sql
SELECT
    pid,
    backend_type,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - backend_start AS backend_age
FROM pg_stat_activity
WHERE backend_type ILIKE '%wal%'
   OR application_name ILIKE '%standby%';
```

Các wait event names phụ thuộc version. Có thể thấy WAL sender chờ dữ liệu mới, chờ socket/network hoặc receiver chờ WAL. Không kết luận chỉ từ tên wait event; tương quan với LSN/rates và OS metrics.

### 20.1. Network bottleneck

Xem interface throughput, retransmits, packet loss, RTT, firewall/NAT idle timeout và connection resets.

### 20.2. Storage bottleneck

Xem latency read/write/fsync, IOPS, throughput limit, queue depth, disk saturation và cloud volume throttling.

### 20.3. CPU bottleneck

Replay và checksum/decompression có thể dùng CPU. So sánh CPU utilization, run queue, process-level usage và replay rate.

## 21. Synchronous replication và ý nghĩa của lag

Synchronous replication có thể khiến commit trên primary chờ standby xác nhận WAL ở mức được cấu hình.

Các thành phần chính:
- synchronous_standby_names: xác định standby tham gia đồng bộ.
- synchronous_commit: mức acknowledgment mà transaction chờ.
- sync_state: trạng thái synchronous của từng standby.

### 21.1. synchronous_commit = local

Commit chờ local WAL flush theo semantics, không chờ remote standby.

### 21.2. synchronous_commit = remote_write

Commit chờ standby xác nhận WAL đã được ghi tới hệ điều hành; không đồng nghĩa durable flush vào storage.

### 21.3. synchronous_commit = on

Với synchronous replication, commit chờ standby flush WAL bền vững theo semantics PostgreSQL.

### 21.4. synchronous_commit = remote_apply

Commit chờ standby replay WAL, hữu ích nếu ứng dụng cần đọc dữ liệu mới ngay trên standby sau commit, đổi lại latency có thể cao hơn.

### 21.5. synchronous_standby_names

Nếu không có synchronous standby phù hợp, commit behavior có thể bị ảnh hưởng theo cấu hình. Kiểm tra state thực tế, không chỉ đọc config file.

## 22. Đọc sync_state và sync_priority

Query:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY sync_priority, application_name;
```

Một số trạng thái phổ biến trong sync_state gồm:
- async: standby đang asynchronous.
- potential: standby có thể trở thành synchronous theo cấu hình/availability.
- sync: standby đang là synchronous.
- quorum: standby tham gia quorum synchronous replication.

Tên/trạng thái chi tiết phụ thuộc cấu hình và PostgreSQL version.

### 22.1. Quorum synchronous

Khi cấu hình quorum, transaction có thể chỉ cần đủ số standby xác nhận. Không giả định mọi standby trong danh sách đều phải flush trước khi commit.

### 22.2. Một standby sync không có nghĩa mọi replica đều sync

Theo dõi từng row và xác định standby nào thực sự được chọn để đáp ứng commit durability.

### 22.3. Promotion policy

Sau failover, node được promote phải phù hợp với durability guarantees đã cam kết. Một standby async không tự trở thành bản sao không mất dữ liệu chỉ vì nó còn kết nối.

## 23. Replay delay có chủ ý

Một standby có thể được cấu hình trì hoãn replay bằng recovery_min_apply_delay. Đây là tính năng hữu ích cho một số mục tiêu bảo vệ trước thao tác xóa nhầm, nhưng nó tạo replay lag có chủ ý.

### 23.1. Delay khác backlog ngoài ý muốn

Nếu configured delay là 10 phút, replay lag không nên được alert như lỗi catch-up thông thường nếu policy yêu cầu delay đó. Dashboard phải biết standby role/purpose.

### 23.2. Receive vẫn có thể gần primary

Một delayed standby có thể nhận và flush WAL nhanh nhưng chờ trước khi replay. Khi đó receive/flush position gần primary, replay position lùi theo delay.

### 23.3. Delayed standby không thay backup

Nếu primary và archive gặp cùng failure hoặc standby bị promote nhầm, delay không thay thế backup/WAL retention.

## 24. Recovery conflicts trên standby

Standby phục vụ read-only queries trong khi replay WAL. Một số replay operations có thể xung đột với query đang chạy.

Các tham số liên quan:
- max_standby_streaming_delay.
- max_standby_archive_delay.
- hot_standby_feedback.

### 24.1. max_standby_streaming_delay

Tham số này điều khiển thời gian standby có thể trì hoãn replay do conflicts với query khi nhận WAL từ streaming replication. Giá trị lớn có thể giúp query đọc hoàn tất nhưng làm replay lag tăng.

### 24.2. Query bị cancel

Nếu replay cần tiếp tục và conflict không thể chờ thêm, PostgreSQL có thể cancel query trên standby. Xem logs và pg_stat_database_conflicts.

### 24.3. hot_standby_feedback

Có thể gửi feedback về xmin để giảm một số query cancellations do vacuum conflicts, nhưng có thể giữ dead tuples trên primary và làm tăng bloat.

### 24.4. Cân bằng read workload và replay freshness

Standby phục vụ analytics dài có thể cần policy khác standby dành cho failover. Không áp một cấu hình cho mọi replica.

## 25. WAL sender/receiver timeouts và kết nối

Các setting thường liên quan:
- wal_sender_timeout.
- wal_receiver_timeout.
- wal_receiver_status_interval.
- max_wal_senders.
- primary_conninfo.

### 25.1. Timeout quá thấp

Network jitter hoặc storage pause ngắn có thể làm connection bị đóng thường xuyên. Đánh giá timeout với network behavior thực tế.

### 25.2. Timeout quá cao

Phát hiện connection failure có thể chậm hơn. RTO failover và alert detection có thể bị ảnh hưởng.

### 25.3. Receiver status interval

Standby gửi status updates theo interval. Thay đổi interval có thể ảnh hưởng tần suất primary nhận acknowledgment/feedback; không đồng nghĩa replay tự nhanh hơn.

### 25.4. Kiểm tra kết nối và authentication

Xem logs của cả hai phía, SSL/certificate, pg_hba, DNS, firewall, port, password/role và replication slot.

## 26. WAL retention và lag

Standby bị lag cần WAL segments cũ hơn. Primary phải giữ đủ WAL để standby tiếp tục.

Các cơ chế liên quan:
- Physical replication slot.
- wal_keep_size.
- max_slot_wal_keep_size trên version hỗ trợ.
- WAL archive.
- max_wal_size và checkpoint/recycle behavior.

### 26.1. Replication slot

Slot giữ WAL từ restart_lsn cần cho consumer. Nó giúp standby reconnect sau gián đoạn ngắn nhưng có thể làm disk usage tăng.

### 26.2. wal_keep_size

Giữ một lượng WAL tối thiểu cho standby không dùng slot theo cơ chế cấu hình. Nó không thay thế archive lâu dài và không bảo đảm giữ WAL vô hạn.

### 26.3. max_slot_wal_keep_size

Có thể giới hạn WAL giữ bởi slots trên các version hỗ trợ. Khi vượt giới hạn, slot có thể không còn usable và standby/consumer cần reinitialize hoặc resync.

### 26.4. max_wal_size không phải quota cứng

Đừng giả định pg_wal luôn bị chặn ở max_wal_size. Slot retention, archive failure và checkpoint behavior có thể khiến WAL directory vượt mức.

## 27. Đo WAL retained distance theo slot

Query:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS distance_from_current_bytes
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY distance_from_current_bytes DESC;
```

### 27.1. Đây không phải filesystem usage

Khoảng cách LSN không tính chính xác segment rounding, WAL files được giữ vì slot khác hoặc các nguyên nhân nội bộ khác. Dùng để xếp hạng slot có retention distance lớn.

### 27.2. Slot không active cần owner

Tìm consumer, standby hoặc backup job sở hữu slot. Không drop chỉ vì active = false.

### 27.3. Alert theo tốc độ tăng và disk headroom

Một slot retained 2 GB có thể bình thường trong cluster lớn; 2 GB tăng thêm mỗi phút trên disk còn 5 GB là nguy hiểm. Cần cả trend và capacity.

## 28. Đo replication lag bằng transaction marker

Khi cần biết commit nghiệp vụ nào có mặt trên standby, tạo marker định kỳ:

```sql
CREATE SCHEMA IF NOT EXISTS replication_test;

CREATE TABLE replication_test.marker (
    sequence_no bigint PRIMARY KEY,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

Test agent ghi marker, commit, rồi ghi acknowledgment vào external witness sau khi nhận COMMIT thành công.

Trên primary/standby:

```sql
SELECT
    max(sequence_no) AS latest_marker,
    max(committed_at) AS latest_marker_time
FROM replication_test.marker;
```

So sánh sequence mới nhất trên hai node và witness ledger.

### 28.1. Marker cadence

Marker mỗi giây cho độ phân giải cao hơn marker mỗi phút nhưng tạo thêm writes/WAL. Chọn cadence phù hợp với RPO target và chi phí.

### 28.2. Witness phải độc lập

Nếu witness nằm trong cùng database hoặc cùng failure domain, nó không chứng minh được acknowledged data đã mất.

### 28.3. Ghi witness sau commit

Không ghi marker vào witness trước khi database xác nhận COMMIT. Nếu không, phép đo có thể ghi nhận transaction chưa được commit.

### 28.4. Marker không phải full correctness test

Marker đo replication path. Nó không chứng minh mọi bảng/index/sequence/business invariant đều đã đồng bộ đúng.

## 29. Đo thời gian bằng pg_last_xact_replay_timestamp

Trên standby:

```sql
SELECT
    pg_last_xact_replay_timestamp() AS last_replayed_xact,
    clock_timestamp()
      - pg_last_xact_replay_timestamp() AS age_since_last_replayed_xact;
```

Đây là tuổi của transaction cuối cùng được replay, không phải thời gian standby chắc chắn đang lag.

### 29.1. Primary không có writes

Nếu không có transaction mới, timestamp cũ dần dù standby đã theo kịp. Có thể gây false alert.

### 29.2. Primary có writes liên tục

Trong workload liên tục, timestamp này có thể giúp nhận diện replay freshness, nhưng vẫn nên so với primary commit/marker time và LSN positions.

### 29.3. Đồng hồ phải đồng bộ

Nếu so timestamp giữa host khác nhau, cần đồng bộ clocks. Dùng UTC và ghi clock source/offset nếu đo RPO.

## 30. Đo lag theo từng standby

Không gộp nhiều standby thành một số duy nhất. Ví dụ dashboard query:

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
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS replay_backlog_bytes,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_stat_replication
ORDER BY application_name;
```

### 30.1. Standby cho failover

Ưu tiên replay freshness, flush durability, connectivity và promotion readiness.

### 30.2. Standby cho reporting

Có thể chấp nhận replay lag cao hơn nếu query workload được cách ly và business freshness target cho phép.

### 30.3. Delayed standby

Alert phải xét configured apply delay. Không so trực tiếp với failover standby.

### 30.4. Quorum standby

Xác định node nào tham gia quorum và node nào chỉ async. Dashboard cần phân biệt durability role.

## 31. Xây dashboard lag hữu ích

Một dashboard có thể có các panel:

1. WAL generation rate trên primary.
2. Sent/write/flush/replay LSN positions theo standby.
3. Byte gaps cho từng queue.
4. write_lag, flush_lag, replay_lag.
5. reply_time age và connection state.
6. pg_stat_wal_receiver status/last message.
7. Replay rate và backlog slope.
8. Replication slot retained distance.
9. WAL directory disk usage.
10. Archive success/failure và archive freshness.
11. Standby query latency/conflicts.
12. Synchronous standby state.

### 31.1. Labels phải ổn định

Dùng cluster, primary, standby/application_name, region, role và timeline. Không chỉ dùng PID vì PID thay đổi khi restart.

### 31.2. Phân biệt NULL với 0

NULL lag có nghĩa không có sample/value trong ngữ cảnh đó. 0 có nghĩa metric đo được và bằng 0. Dashboard không nên tự biến NULL thành 0 mà không ghi chú.

### 31.3. Có panel theo thời gian

Một snapshot không cho thấy backlog đang tăng hay giảm. Dùng time series để thấy slope và correlation với workload.

## 32. Thiết kế alert theo mục tiêu

Không dùng một threshold chung cho mọi standby. Ví dụ policy minh họa:

| Alert | Trigger mẫu | Ý nghĩa |
|---|---|---|
| Connection down | State không streaming quá ngưỡng | WAL không được truyền liên tục |
| Send backlog | current_lsn - sent_lsn tăng kéo dài | Sender/network path |
| Write lag | sent_lsn - write_lsn tăng | Receiver/write path |
| Flush lag | write_lsn - flush_lsn tăng | Storage flush path |
| Replay lag | flush_lsn - replay_lsn tăng | Recovery/apply path |
| Backlog growth | Generation rate > replay rate kéo dài | Standby không catch up |
| Slot retention | Retained WAL tăng gần disk budget | Nguy cơ pg_wal đầy |
| Archive failure | Failed count delta tăng | PITR archive risk |
| Sync degradation | Synchronous standby không còn phù hợp | Commit durability/latency risk |

### 32.1. Dùng duration/persistence

Một spike vài giây có thể bình thường. Alert sau khi vượt threshold trong thời gian phù hợp, trừ sự cố critical như connection down kéo dài hoặc disk gần đầy.

### 32.2. Alert phải gắn failure scenario

Lag 30 giây có thể chấp nhận cho reporting replica nhưng không phù hợp cho failover tier cần RPO 5 giây.

### 32.3. Đặt warning và critical

Warning cho xu hướng xấu; critical khi RPO budget, disk headroom hoặc failover readiness sắp vượt giới hạn.

## 33. Runbook: standby replay lag tăng

1. Xác định standby nào và workload/role của nó.
2. Kiểm tra pg_stat_replication.state, sync_state, reply_time.
3. Đo sent/write/flush/replay LSN gaps.
4. Trên standby, kiểm tra pg_stat_wal_receiver.
5. Tính WAL generation rate và replay rate qua nhiều samples.
6. Kiểm tra recovery conflicts và pg_stat_database_conflicts.
7. Kiểm tra CPU, storage latency, IOPS và network.
8. Kiểm tra recovery_min_apply_delay.
9. Kiểm tra query/reporting workload trên standby.
10. Xem logs của primary/standby.
11. Xác định lag đang giảm, ổn định hay tăng.
12. Nếu standby không còn đủ WAL, đánh giá reinitialize/resync.
13. Cập nhật RPO/failover readiness nếu standby không thể được promote an toàn.

### 33.1. Không restart standby ngay lập tức

Restart có thể không sửa được bottleneck và làm gián đoạn receiver/replay. Thu thập evidence trước.

### 33.2. Không promote một standby lag lớn chỉ vì primary down

Đánh giá last received/flushed/replayed WAL và acknowledged transaction evidence. Business owner phải hiểu actual data loss nếu chọn node đó.

### 33.3. Nếu replay bị delay có chủ ý

Xác nhận policy và target delay. Có thể cần chọn một standby khác cho failover.

## 34. Runbook: write/flush lag cao

### Write lag cao

- Kiểm tra network RTT, packet loss, retransmits.
- Kiểm tra sender/receiver CPU.
- Kiểm tra connection resets.
- Kiểm tra throughput và receiver scheduling.
- Kiểm tra WAL burst từ batch workload.

### Flush lag cao

- Kiểm tra disk latency và fsync.
- Kiểm tra IOPS/throughput throttling.
- Kiểm tra volume queue depth.
- Kiểm tra backup/checkpoint contention.
- So sánh các standby có storage class khác nhau.

### 34.1. So sánh nhiều standby

Nếu chỉ một standby flush chậm, vấn đề có thể nằm ở host/storage đó. Nếu tất cả standby cùng chậm, xem primary sender/network hoặc WAL burst chung.

### 34.2. Không tăng workers replay để sửa flush

Replay workers không giải quyết storage flush bottleneck. Chọn hành động theo queue thực sự tăng.

## 35. Runbook: replication connection bị gián đoạn

Kiểm tra:
- pg_stat_replication có row không.
- pg_stat_wal_receiver có status streaming không.
- Primary/standby logs.
- DNS, routing, firewall, TLS/certificates.
- Replication user/password và pg_hba.conf.
- WAL sender capacity.
- Replication slot validity.
- Standby có đủ WAL hay phải fetch từ archive.

### 35.1. Slot invalidated

Nếu slot không còn usable vì WAL đã bị recycle/giới hạn retention, standby có thể cần base backup mới hoặc phương án resync. Không tự tạo slot mới rồi giả định gap được lấp.

### 35.2. Archive fallback

Nếu standby được cấu hình restore_command, nó có thể lấy WAL từ archive trong recovery theo workflow phù hợp. Xác minh archive continuity.

### 35.3. Connection restored chưa đồng nghĩa caught up

Sau khi streaming kết nối lại, theo dõi replay backlog và catch-up rate tới khi đạt mục tiêu.

## 36. Replay conflicts và reporting workload

Một standby phục vụ query dài có thể gây xung đột với WAL replay. pg_stat_database_conflicts giúp theo dõi số conflict theo database.

Ví dụ:

```sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_stat_database_conflicts
ORDER BY datname;
```

Các counter là tích lũy từ stats reset. Xem delta theo thời gian thay vì chỉ giá trị tuyệt đối.

### 36.1. max_standby_streaming_delay

Giá trị lớn hơn có thể cho query thêm thời gian, nhưng replay có thể bị trì hoãn lâu hơn. Chọn theo freshness SLO của standby.

### 36.2. hot_standby_feedback

Có thể giảm conflict cancellation do cleanup nhưng làm primary giữ dead tuples lâu hơn. Theo dõi bloat/cleanup horizon.

### 36.3. Tách standby theo workload

Nếu reporting queries dài gây lag cho failover standby, cân nhắc replica riêng hoặc giới hạn workload.

## 37. Tác động của transaction lớn và WAL burst

Một transaction lớn có thể tạo lượng WAL lớn, khiến:
- Sender queue tăng.
- Network throughput đạt trần.
- Standby flush chậm.
- Replay backlog tăng.
- Catch-up kéo dài sau khi transaction kết thúc.

Các nguồn burst khác:
- Bulk load.
- CREATE INDEX.
- Batch UPDATE/DELETE.
- Partition maintenance.
- Full-page images sau checkpoint.
- Một số thao tác DDL.

### 37.1. Không chỉ xem average WAL rate

Theo dõi peak rate và burst duration. Hệ thống có thể đạt average nhưng vẫn không chịu được batch window.

### 37.2. Chia batch khi phù hợp

Một số batch updates có thể chia thành transactions nhỏ hơn để giảm peak pressure và lock duration, nhưng cần cân nhắc transaction semantics/overhead.

### 37.3. Đặt lịch backup và batch

Backup đọc nhiều storage, batch tạo WAL; chạy đồng thời có thể làm cả primary và standby chậm. Lập lịch theo measured capacity.

## 38. Tuning có mục tiêu

| Bottleneck | Hướng điều tra/điều chỉnh |
|---|---|
| Network | Throughput, RTT, packet loss, NIC, route |
| WAL sender | CPU, sender count, socket waits, WAL burst |
| Standby write | Receiver CPU, filesystem write, storage |
| Standby flush | fsync latency, disk IOPS/throughput |
| Replay | CPU, read/write I/O, conflicts, apply delay |
| Query contention | Workload isolation, max_standby delays, feedback |
| Retention | Slot, wal_keep_size, archive, disk capacity |
| Connection churn | Timeout, network, authentication, monitoring |

### 38.1. Không tăng mọi setting cùng lúc

Thay một nhóm có giả thuyết, đo trước/sau và giữ rollback path. Nếu thay nhiều setting, khó xác định yếu tố tạo cải thiện.

### 38.2. max_wal_senders

Đảm bảo đủ sender capacity cho standby/backup clients. Tăng quá mức không tự làm network hoặc replay nhanh hơn.

### 38.3. wal_compression

Tham số này liên quan nén full-page images trong WAL records ở những trường hợp phù hợp; không phải compression của toàn bộ streaming connection. Kiểm tra version và CPU trade-off.

### 38.4. Không tune theo một snapshot

Lấy baseline qua giờ cao điểm, batch và idle periods. Xác nhận thay đổi không làm xấu commit latency hoặc storage.

## 39. Replication lag và synchronous commit latency

Với synchronous replication, ứng dụng có thể cảm nhận độ trễ thông qua thời gian COMMIT.

Theo dõi:
- Transaction commit latency.
- synchronous_commit.
- synchronous_standby_names.
- sync_state.
- write_lag/flush_lag/replay_lag.
- Network RTT và standby storage latency.

### 39.1. remote_write

Có thể giảm latency so với chờ durable flush, nhưng durability guarantee khác on.

### 39.2. on

Chờ standby flush WAL. Đây là lựa chọn phổ biến khi cần synchronous durability tới standby.

### 39.3. remote_apply

Chờ standby replay. Có thể hữu ích cho read-after-write trên standby nhưng làm commit phụ thuộc replay throughput.

### 39.4. Không đổi synchronous_commit để che lag

Hạ durability level có thể giảm commit latency nhưng thay đổi RPO/failure guarantees. Cần business/architecture review và test.

## 40. Replication lag và read-after-write consistency

Ứng dụng đọc từ standby có thể chưa thấy transaction vừa commit trên primary nếu standby chưa replay tới WAL tương ứng.

Các cách thiết kế:
- Đọc transaction-sensitive requests từ primary.
- Chờ standby replay tới LSN token của transaction cần đọc.
- Dùng synchronous_commit = remote_apply khi yêu cầu/chi phí phù hợp.
- Route session tới primary trong cửa sổ cần read-after-write.
- Dùng consistency token trong application layer.

### 40.1. Wait for LSN

Ứng dụng có thể lấy LSN sau commit từ primary rồi chờ standby replay tới vị trí đó bằng cơ chế phù hợp như pg_wait_for_replay_lsn trên standby ở version hỗ trợ.

Ví dụ trên standby:

```sql
SELECT pg_last_wal_replay_lsn();
```

So sánh với target LSN mà application đã nhận từ primary. Function wait có thể có tên/availability theo version; kiểm tra tài liệu.

### 40.2. Không dùng sleep cố định

pg_sleep(1) không bảo đảm replay đã tới target. Chờ theo LSN/consistency token tốt hơn.

### 40.3. Read scaling có trade-off

Đọc từ standby giảm tải primary nhưng có thể trả dữ liệu stale. Đưa freshness requirement vào routing policy.

## 41. Monitoring freshness cho standby idle

Nếu primary không tạo WAL, lag time fields có thể NULL và last replay transaction timestamp có thể cũ. Cần phân biệt idle với disconnected.

Có thể dùng:
- WAL sender connection state.
- reply_time.
- pg_stat_wal_receiver.last_msg_receipt_time.
- Primary heartbeat/marker transaction có kiểm soát.
- Network health.
- Slot/receiver state.

### 41.1. Heartbeat marker

Một transaction nhỏ định kỳ có thể tạo tín hiệu freshness, nhưng nó tạo WAL và phải được tính vào workload.

### 41.2. Không tạo heartbeat quá thường xuyên

Chọn cadence đủ đáp ứng mục tiêu và không gây writes không cần thiết.

### 41.3. Connection state vẫn cần kiểm tra

Nếu không có WAL activity nhưng receiver connection đã mất, hệ thống vẫn có thể đang degraded dù lag bytes không tăng.

## 42. Multi-standby topology

Trong hệ thống có nhiều standby:
- Một node có thể synchronous.
- Một node có thể async ở region khác.
- Một node có thể delayed.
- Một node phục vụ reporting.
- Một node là cascading standby.

Dashboard phải ghi rõ role/purpose và nguồn WAL.

### 42.1. Cascading replication

Standby có thể gửi WAL tới standby khác. Lag ở node downstream gồm upstream receive/replay và downstream send/receive/replay.

### 42.2. Không so sánh trực tiếp tất cả LSN như cùng một hop

Ghi topology và timeline. Xác định mỗi node nhận WAL từ đâu.

### 42.3. Failover path

Nếu standby A là upstream của standby B, promote A có thể ảnh hưởng B. Runbook cần chỉ rõ cách reparent/reconfigure.

## 43. Cập nhật RPO/RTO từ lag metrics

Lag metrics hỗ trợ vận hành nhưng không thay thế đo actual RPO/RTO.

Để cập nhật:
1. Định nghĩa failure scenario.
2. Ghi primary current LSN và standby sent/write/flush/replay positions.
3. Ghi sync_state và synchronous_commit.
4. Ghi transaction marker đã acknowledged.
5. Thực hiện failover drill theo policy.
6. So sánh marker cuối trên primary cũ với promoted standby.
7. Tính actual RPO.
8. Đo thời gian từ incident start tới application write-ready.
9. Tính actual RTO.
10. Cập nhật runbook và target feasibility.

### 43.1. Lag trước sự cố không phải actual loss

Một standby replay lag 10 MB có thể flush đủ WAL để không mất acknowledged commits nếu promotion/recovery path dùng đúng WAL. Ngược lại, lag time nhỏ không chứng minh mọi transaction đã durable.

### 43.2. Ghi rõ failure model

Primary process crash, host loss, storage loss và region loss có durability assumptions khác nhau.

### 43.3. Evidence phải có timeline

Ghi timeline ID, LSN, marker sequence và timestamps để tái dựng kết quả.

## 44. Các lỗi phổ biến khi đo replication lag

### Lỗi 1 — Gộp write, flush và replay thành một số

Mất khả năng xác định bottleneck.

### Lỗi 2 — Xem write_lag là network latency

Metric còn gồm standby write/acknowledgment path.

### Lỗi 3 — Xem flush_lag là actual RPO

Actual RPO phải đo acknowledged commits so với recovered data.

### Lỗi 4 — Xem replay_lag là catch-up ETA

Đây là delay của WAL gần đây, không phải thời gian còn lại.

### Lỗi 5 — NULL đồng nghĩa lag bằng 0

NULL có thể nghĩa không có sample hoặc không có WAL activity gần đây.

### Lỗi 6 — Timestamp replay cũ đồng nghĩa standby hỏng

Primary có thể đang idle.

### Lỗi 7 — Byte lag đồng nghĩa time lag

Cần WAL rate/replay rate để chuyển đổi.

### Lỗi 8 — state = streaming đồng nghĩa khỏe

Connection streaming vẫn có thể có backlog lớn.

### Lỗi 9 — Standby nhận WAL đồng nghĩa replay đã xong

Receiver và recovery là hai process/giai đoạn khác nhau.

### Lỗi 10 — Archive lag đồng nghĩa streaming lag

Hai đường truyền riêng.

### Lỗi 11 — Slot retained distance là disk usage chính xác

Đây chỉ là LSN distance estimate.

### Lỗi 12 — Xóa slot inactive mà không kiểm tra owner

Có thể làm consumer phải resync.

### Lỗi 13 — Tăng max_wal_size để sửa replay lag

Tham số này không làm replay nhanh hơn.

### Lỗi 14 — Tăng max_wal_senders để sửa network

Sender capacity không thay network bandwidth.

### Lỗi 15 — Tăng max_standby_streaming_delay mà không xét freshness

Query có thể ít bị cancel hơn nhưng replay lag tăng.

### Lỗi 16 — Bật hot_standby_feedback mà không theo dõi primary bloat

Có thể giữ dead tuples lâu hơn trên primary.

### Lỗi 17 — Đo chỉ một standby

Các standby có role/storage/network khác nhau.

### Lỗi 18 — Không ghi timeline

Sau promotion, LSN comparison có thể sai ngữ cảnh.

### Lỗi 19 — Đo một snapshot duy nhất

Không biết backlog tăng hay giảm.

### Lỗi 20 — Không kiểm tra transaction marker

Không có bằng chứng business-level về dữ liệu được xác nhận và dữ liệu phục hồi.

## 45. Bài tập thực hành có đáp án

### Bài 1. Write lag là gì?

**Đáp án:** Thời gian từ lúc primary flush WAL gần đây tới khi nhận acknowledgment standby đã ghi WAL tương ứng.

### Bài 2. Flush lag là gì?

**Đáp án:** Thời gian tới khi primary nhận acknowledgment standby đã flush WAL tương ứng.

### Bài 3. Replay lag là gì?

**Đáp án:** Thời gian tới khi primary nhận acknowledgment standby đã replay WAL tương ứng.

### Bài 4. Write lag cao chứng minh network chậm?

**Đáp án:** Không. Cần xem cả network, receiver, CPU và standby write path.

### Bài 5. Write lag thấp, flush lag cao gợi ý gì?

**Đáp án:** WAL đã ghi nhưng flush storage chậm; kiểm tra disk/fsync latency.

### Bài 6. Flush lag thấp, replay lag cao gợi ý gì?

**Đáp án:** WAL đã flush nhưng recovery chưa replay kịp; kiểm tra replay throughput/conflicts.

### Bài 7. Sent LSN khác replay LSN thế nào?

**Đáp án:** Sent là vị trí WAL đã gửi; replay là vị trí standby đã áp dụng WAL.

### Bài 8. LSN là timestamp?

**Đáp án:** Không. LSN là vị trí trong WAL stream.

### Bài 9. Dùng function nào tính khoảng cách byte giữa hai LSN?

**Đáp án:** pg_wal_lsn_diff.

### Bài 10. pg_stat_replication chạy ở đâu?

**Đáp án:** Trên primary/WAL sender server; mỗi row thường đại diện một connected standby.

### Bài 11. pg_stat_wal_receiver chạy ở đâu?

**Đáp án:** Trên standby đang nhận WAL qua streaming replication.

### Bài 12. state = streaming có chứng minh replay không lag?

**Đáp án:** Không. Phải xem LSN positions, replay backlog và rates.

### Bài 13. NULL replay_lag có nghĩa gì?

**Đáp án:** Có thể không có mẫu WAL gần đây để tính; không tự động có nghĩa zero hoặc failure.

### Bài 14. pg_last_xact_replay_timestamp() cũ có thể do đâu?

**Đáp án:** Primary không có transaction mới; timestamp không đổi khi standby idle.

### Bài 15. Byte lag có trực tiếp bằng seconds?

**Đáp án:** Không. Cần biết WAL generation và replay rates.

### Bài 16. Công thức WAL generation rate?

**Đáp án:** Chênh LSN current giữa hai samples chia elapsed seconds.

### Bài 17. Công thức replay rate?

**Đáp án:** Chênh replay LSN giữa hai samples chia elapsed seconds.

### Bài 18. Replay rate 40 MB/s, WAL generation 25 MB/s; net catch-up rate?

**Đáp án:** 15 MB/s, nếu tốc độ duy trì ổn định.

### Bài 19. Backlog 600 MB, net catch-up 20 MB/s; ETA gần đúng?

**Đáp án:** 30 giây, chỉ là estimate theo điều kiện ổn định.

### Bài 20. Replay rate thấp hơn generation rate có catch up không?

**Đáp án:** Không trong điều kiện đó; backlog sẽ tăng.

### Bài 21. write_lag có phải ETA?

**Đáp án:** Không. Nó biểu diễn độ trễ acknowledgment của WAL gần đây.

### Bài 22. flush_lag có phải actual RPO?

**Đáp án:** Không. Actual RPO cần so acknowledged commits với recovered data.

### Bài 23. Archive lag và streaming lag giống nhau?

**Đáp án:** Không. Một đường lưu WAL archive, một đường gửi WAL tới standby.

### Bài 24. Slot inactive có thể giữ WAL?

**Đáp án:** Có. Slot có thể giữ restart_lsn/xmin và làm tài nguyên tăng.

### Bài 25. restart_lsn dùng để làm gì?

**Đáp án:** Chỉ vị trí WAL cũ nhất mà replication slot có thể còn cần.

### Bài 26. LSN distance tới restart_lsn có phải disk usage chính xác?

**Đáp án:** Không. Nó là khoảng cách WAL, không tính mọi segment/retention factor.

### Bài 27. Synchronous commit on chờ điều gì?

**Đáp án:** Với synchronous replication, chờ standby flush WAL bền vững theo semantics PostgreSQL.

### Bài 28. remote_write có tương đương durable flush?

**Đáp án:** Không. Nó chờ standby ghi WAL tới OS, không đồng nghĩa durable flush.

### Bài 29. remote_apply khác on thế nào?

**Đáp án:** remote_apply chờ standby replay WAL, còn on chờ flush WAL.

### Bài 30. sync_state giúp gì?

**Đáp án:** Cho biết standby đang async, potential, sync hoặc quorum theo cấu hình/version.

### Bài 31. recovery_min_apply_delay có thể làm gì?

**Đáp án:** Tạo replay delay có chủ ý trên standby.

### Bài 32. Vì sao reporting query có thể làm replay chậm?

**Đáp án:** Recovery conflict có thể buộc replay chờ hoặc cancel query tùy cấu hình.

### Bài 33. hot_standby_feedback có trade-off gì?

**Đáp án:** Có thể giảm query cancellations nhưng giữ dead tuples lâu hơn trên primary.

### Bài 34. max_wal_size là giới hạn cứng của pg_wal?

**Đáp án:** Không. Slot retention/archive failures có thể làm WAL usage vượt mức.

### Bài 35. Tại sao không tăng max_wal_senders để sửa replay lag?

**Đáp án:** Sender count không làm recovery process replay nhanh hơn.

### Bài 36. pg_stat_database_conflicts cho biết gì?

**Đáp án:** Counters về recovery conflicts trên standby, cần xem delta theo thời gian.

### Bài 37. Khi standby nhận WAL nhanh nhưng replay đứng, kiểm tra gì?

**Đáp án:** Replay process, conflicts, apply delay, CPU/I/O và query workload.

### Bài 38. Khi sent-to-write gap tăng, kiểm tra gì?

**Đáp án:** Network, receiver, CPU và write path.

### Bài 39. Khi write-to-flush gap tăng, kiểm tra gì?

**Đáp án:** Storage latency, fsync, IOPS và disk queue.

### Bài 40. Khi flush-to-replay gap tăng, kiểm tra gì?

**Đáp án:** Replay throughput, recovery conflicts, apply delay và standby workload.

### Bài 41. Vì sao phải theo dõi từng standby riêng?

**Đáp án:** Mỗi node có role, storage, network và sync policy khác nhau.

### Bài 42. Standby có thể streaming nhưng vẫn không phù hợp để promote?

**Đáp án:** Có. Nó có thể lag lớn hoặc không có acknowledged commits cần thiết.

### Bài 43. Làm sao đo acknowledged data loss trong failover drill?

**Đáp án:** Dùng transaction markers đã ghi external witness sau COMMIT và so với marker trên promoted standby.

### Bài 44. Vì sao marker witness phải độc lập?

**Đáp án:** Để không mất cùng database trong failure domain.

### Bài 45. Heartbeat marker quá thường xuyên có tác động gì?

**Đáp án:** Tạo thêm writes/WAL và có thể làm thay đổi workload.

### Bài 46. Vì sao cần ghi timeline khi so LSN?

**Đáp án:** Promotion tạo nhánh WAL history mới; cần biết LSN thuộc timeline nào.

### Bài 47. Một lần đo lag có đủ để xác định trend?

**Đáp án:** Không. Cần samples theo thời gian để tính backlog slope và rates.

### Bài 48. Replay lag tăng trong giờ batch nhưng giảm sau batch; xử lý thế nào?

**Đáp án:** Đo peak WAL rate, replay capacity và catch-up time; điều chỉnh batch/standby capacity nếu vi phạm freshness target.

### Bài 49. RPO/RTO có thể suy ra hoàn toàn từ lag fields?

**Đáp án:** Không. Cần failover/PITR drills và đo actual acknowledged transactions cùng service-ready time.

### Bài 50. Một dashboard replication lag tốt cần có gì?

**Đáp án:** LSN positions, byte gaps, time lags, generation/replay rates, connection state, receiver status, slot retention, archive health và role/timeline.

## 46. Checklist điều tra replication lag

| Giai đoạn | Câu hỏi |
|---|---|
| Nhận diện | Primary và standby nào đang được đo? |
| Nhận diện | Standby phục vụ failover, reporting, delayed hay quorum? |
| Connection | state có streaming không? |
| Connection | reply_time và receiver last message có mới không? |
| Sender | current_lsn - sent_lsn có tăng? |
| Receiver/write | sent_lsn - write_lsn có tăng? |
| Flush | write_lsn - flush_lsn có tăng? |
| Replay | flush_lsn - replay_lsn có tăng? |
| Time | write_lag/flush_lag/replay_lag là NULL hay có giá trị? |
| Trend | Backlog đang tăng, ổn định hay giảm? |
| Rate | WAL generation rate so với replay rate? |
| Storage | IOPS, fsync latency, throughput có bão hòa? |
| Network | RTT, packet loss, retransmits, throughput? |
| Replay | Recovery conflicts hoặc apply delay? |
| Retention | Slot giữ WAL bao nhiêu LSN distance? |
| Archive | WAL archive có failures/gaps không? |
| Durability | Standby nào thực sự synchronous? |
| Application | Commit latency/read freshness có bị ảnh hưởng? |
| Recovery | Standby có đủ WAL và an toàn để promote? |
| Sau xử lý | Lag có giảm theo trend và đạt SLO? |
| Evidence | LSN, timeline, marker và timestamps đã lưu? |

## 47. Tài liệu PostgreSQL chính thức

- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_replication, pg_stat_wal_receiver, activity và replication statistics.
- [Warm Standby / Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — physical streaming replication và standby behavior.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — synchronous_commit và acknowledgment levels.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — sender, receiver, slots và replication settings.
- [Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET) — recovery delay/settings.
- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html) — read-only standby, conflicts và feedback.
- [System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html) — LSN/recovery functions.
- [pg_stat_replication](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW) — sender/standby positions and lag fields.
- [pg_stat_wal_receiver](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-WAL-RECEIVER-VIEW) — receiver status and LSN positions.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — retained WAL and slot status.
- [pg_stat_database_conflicts](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-DATABASE-CONFLICTS-VIEW) — recovery conflict counters.

Các view columns, wait events và replication settings có thể thay đổi theo PostgreSQL major version. Trước khi đưa query vào production monitoring, kiểm tra server_version, pg_settings, view definitions và tài liệu đúng phiên bản đang chạy.

## 48. Tổng kết: đo đúng từng chặng, tìm đúng bottleneck

```text
Primary WAL generation
        |
        v
   sent_lsn
        |
        v
   write_lsn       -> write path
        |
        v
   flush_lsn       -> durable storage path
        |
        v
   replay_lsn      -> recovery/apply path
        |
        v
   Standby visible state

Time lag: write_lag / flush_lag / replay_lag
Byte lag:  LSN differences
Trend:     WAL generation rate vs replay rate
Proof:     transaction markers + failover drill
```

Những nguyên tắc cần nhớ:

1. **Write, flush và replay là ba mốc khác nhau.** Đọc từng metric để xác định queue nằm ở đâu.
2. **LSN gap đo khoảng cách WAL theo byte.** Nó không tự chuyển thành thời gian.
3. **Time lag fields mô tả độ trễ của WAL gần đây.** Chúng không phải catch-up ETA hoặc actual RPO.
4. **NULL không đồng nghĩa zero.** Khi primary idle, lag time có thể không có mẫu mới.
5. **Receiver nhận WAL, recovery replay WAL.** Hai process có thể tiến triển với tốc độ khác nhau.
6. **WAL generation rate phải được so với replay rate.** Backlog chỉ giảm khi replay throughput vượt WAL incoming rate.
7. **Archive lag, streaming lag và slot retention là ba vấn đề riêng.** Dashboard phải theo dõi riêng.
8. **Synchronous commit thay đổi durability và commit latency.** Hiểu remote_write, on và remote_apply trước khi tune.
9. **Recovery conflicts và apply delay có thể làm replay chậm có chủ ý.** Xét role của standby trước khi alert.
10. **Không promote chỉ vì standby đang streaming.** Xác minh LSN, timeline, acknowledged commits và fencing.
11. **Transaction markers cung cấp bằng chứng nghiệp vụ tốt hơn một lag field đơn lẻ.** Dùng external witness trong drill.
12. **Đo xu hướng và giữ evidence.** Một snapshot không cho biết standby có đang catch up hay không.

**Một câu để nhớ:** *Replication lag chỉ được chẩn đoán đúng khi biết WAL đang chờ ở bước gửi, ghi, flush hay replay; hãy đo LSN, tốc độ và transaction evidence cùng nhau trước khi kết luận standby có đủ mới để phục vụ đọc hoặc failover.*

