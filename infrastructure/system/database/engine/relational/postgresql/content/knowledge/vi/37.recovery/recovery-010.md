# Đo RPO, RTO thực tế và cập nhật quy trình khôi phục PostgreSQL

## 1. Vì sao phải đo khả năng khôi phục?

Một hệ thống có thể báo “backup thành công” mỗi ngày, có WAL archive, standby và dashboard màu xanh nhưng vẫn mất nhiều giờ để phục hồi khi sự cố thật xảy ra. Một base backup có thể bị thiếu WAL, object storage có thể không truy cập được, encryption key có thể thất lạc, tablespace có thể chưa được chuẩn bị, hoặc runbook có thể dùng lệnh của PostgreSQL major version khác.

Khả năng khôi phục phải được chứng minh bằng phép đo và diễn tập. Hai chỉ số quan trọng nhất là:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa mà tổ chức chấp nhận mất khi xảy ra sự cố, thường biểu diễn bằng thời gian.
- **RTO (Recovery Time Objective):** khoảng thời gian tối đa mà tổ chức chấp nhận để khôi phục dịch vụ về trạng thái sử dụng được.

RPO và RTO là mục tiêu nghiệp vụ. Giá trị thực tế chỉ có thể xác định khi quan sát backup, WAL, replication, hạ tầng, quy trình và kết quả restore/failover.

```text
Sự cố xảy ra
     |
     +---- RPO ----> Điểm dữ liệu cuối cùng có thể phục hồi
     |
     +---- RTO ------------------------------+
                                             |
                                             v
                                  Dịch vụ hoạt động trở lại
                                  và đã được xác minh
```

Một quy trình tốt phải trả lời được:

1. Khi sự cố xảy ra, dữ liệu mới nhất nào thực sự còn phục hồi được?
2. Bao nhiêu dữ liệu đã mất so với những transaction được xác nhận thành công?
3. Mất bao lâu để phát hiện, quyết định, provision, restore/replay, xác minh và mở dịch vụ?
4. Kết quả có đạt mục tiêu RPO/RTO đã cam kết không?
5. Nếu không đạt, cần thay đổi kiến trúc, cấu hình, tài nguyên hay quy trình nào?

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt RPO, RTO, MTD/MTTR, recovery point và backup freshness.
2. Xác định mốc bắt đầu/kết thúc khi đo RPO và RTO.
3. Tính RPO thực tế từ dữ liệu đã xác nhận commit và dữ liệu sau recovery.
4. Đo RTO theo từng giai đoạn thay vì chỉ lấy thời gian chạy lệnh restore.
5. Phân biệt failover sang standby với PITR từ base backup và WAL archive.
6. Đọc replication lag, archive status, WAL LSN và recovery logs.
7. Thiết kế transaction marker để chứng minh điểm dữ liệu phục hồi.
8. Tổ chức restore drill và failover drill an toàn.
9. Đánh giá backup integrity, WAL continuity, timeline, keys và tablespaces.
10. Kiểm tra dữ liệu và ứng dụng sau recovery.
11. Xây dựng RPO/RTO theo từng failure scenario.
12. Cập nhật runbook, ownership, escalation và bằng chứng sau mỗi lần diễn tập.
13. Đưa kết quả đo vào capacity planning và cải tiến liên tục.

---

## 2. RPO và RTO: hai mục tiêu khác nhau

RPO và RTO thường được ghi cạnh nhau nhưng đo hai loại tổn thất khác nhau.

| Chỉ số | Câu hỏi | Đơn vị thường dùng |
|---|---|---|
| RPO | Có thể mất tối đa bao nhiêu dữ liệu? | Giây/phút/giờ hoặc số transaction |
| RTO | Có thể gián đoạn dịch vụ tối đa bao lâu? | Giây/phút/giờ |
| Actual RPO | Sự cố/diễn tập vừa rồi thực tế mất bao nhiêu dữ liệu? | Thời gian hoặc transaction |
| Actual RTO | Từ mốc bắt đầu tới lúc dịch vụ dùng được mất bao lâu? | Thời gian |
| Backup age | Base backup gần nhất cách hiện tại bao lâu? | Thời gian |
| Archive lag | WAL mới nhất chưa được archive cách hiện tại bao lâu? | Thời gian/LSN |
| Replication lag | Standby chậm hơn primary bao nhiêu theo metric được chọn? | Byte/thời gian/LSN |

### 2.1. Ví dụ mục tiêu

Một dịch vụ đặt:

- RPO mục tiêu: tối đa 5 phút dữ liệu.
- RTO mục tiêu: tối đa 60 phút gián đoạn.

Điều đó có nghĩa trong failure scenario đã định nghĩa, tổ chức chấp nhận mất tối đa lượng dữ liệu tương ứng 5 phút và phải đưa dịch vụ trở lại trạng thái sử dụng được trong 60 phút.

Đây là cam kết cần được kiểm chứng, không phải kết quả tự động đạt được chỉ vì đặt archive_timeout thành 5 phút hoặc backup chạy mỗi đêm.

### 2.2. RPO bằng 0 có nghĩa gì?

RPO = 0 có nghĩa không mất các transaction đã được xác nhận thành công trong failure model đã cam kết. Điều này cần kiến trúc và semantics durability phù hợp, chẳng hạn synchronous replication với điều kiện xác nhận WAL bền vững trên standby thích hợp.

Không nên hứa RPO = 0 cho mọi loại thảm họa chỉ dựa trên việc có một standby. Mất đồng thời primary, standby, region hoặc storage domain có thể nằm ngoài failure model ban đầu.

### 2.3. RTO không phải thời gian chạy pg_restore/pg_basebackup

RTO bao gồm toàn bộ thời gian cần để dịch vụ khôi phục: phát hiện, ra quyết định, cấp hạ tầng, restore files, replay WAL, kiểm tra, cutover và mở traffic. Một lệnh restore chạy xong không có nghĩa dịch vụ đã sẵn sàng.

## 3. Định nghĩa mốc thời gian trước khi đo

Không có cách đo nhất quán nếu mỗi lần diễn tập lại chọn một mốc khác nhau.

### 3.1. Mốc đo RPO

Với một sự cố vật lý, có thể định nghĩa:

- T_failure: thời điểm failure làm hệ thống không còn phục vụ ghi nhận transaction như bình thường.
- T_last_recoverable: thời điểm của transaction cuối cùng được xác nhận và có mặt trong database đã phục hồi.

Khi đó:

```text
Actual RPO = T_failure - T_last_recoverable
```

Trong môi trường có ledger transaction sequence, nên đo thêm số transaction đã được xác nhận trên hệ thống cũ nhưng không có trên hệ thống phục hồi. Cách đo theo transaction ID/sequence có thể chính xác hơn timestamp nếu đồng hồ hoặc commit timestamps không đủ tin cậy.

### 3.2. Mốc đo RTO

Tổ chức phải định nghĩa chính thức:

- T_start: thời điểm incident bắt đầu hoặc thời điểm incident được tuyên bố.
- T_service_restored: thời điểm dịch vụ đáp ứng các tiêu chí đã thống nhất.

```text
Actual RTO = T_service_restored - T_start
```

Không đổi T_start giữa các báo cáo để làm RTO trông ngắn hơn. Nếu muốn tách thời gian detection và response, ghi các mốc con nhưng giữ một định nghĩa RTO chính thức.

### 3.3. Khi nào dịch vụ được coi là restored?

Cần có tiêu chí kiểm chứng, ví dụ:

- PostgreSQL đã recovery tới đúng target/timeline.
- Ứng dụng kết nối được bằng credentials production.
- Các thao tác đọc cốt lõi thành công.
- Các thao tác ghi cốt lõi thành công nếu dịch vụ cần ghi.
- Data invariants/critical tables đạt kiểm tra.
- Connection pool, background workers và dependencies hoạt động.
- Traffic đã được route tới đúng primary.
- Error rate và latency nằm trong giới hạn cho phép.

Nếu database start được nhưng ứng dụng chưa kết nối, RTO dịch vụ chưa kết thúc.

## 4. Phân biệt mục tiêu với kết quả thực tế

Một báo cáo recovery nên có cả target và actual.

| Chỉ số | Mục tiêu | Kết quả diễn tập | Đạt? |
|---|---:|---:|---|
| RPO | 5 phút | 2 phút 10 giây | Có |
| RTO | 60 phút | 74 phút | Không |
| Restore verification | 100% critical checks | 98% | Không |
| WAL continuity | Không thiếu segment | Đầy đủ | Có |

Số liệu chỉ là ví dụ minh họa. Một kết quả RPO đạt nhưng RTO không đạt vẫn là một lần diễn tập không đạt toàn bộ yêu cầu.

### 4.1. Không báo cáo chỉ một con số tốt nhất

Một lần restore thành công trong 20 phút không chứng minh mọi lần đều đạt 20 phút. Ghi nhiều lần thử, điều kiện môi trường, kích thước backup và percentile.

### 4.2. Phân biệt planned RTO và observed RTO

- Planned RTO: mục tiêu hoặc dự báo từ thiết kế.
- Observed RTO: kết quả đo từ drill/sự cố.
- Worst observed: lần tệ nhất trong tập thử.
- P95: percentile 95 nếu số mẫu đủ và phương pháp thống kê phù hợp.

Không gọi một estimate là actual.

## 5. RPO phụ thuộc vào failure scenario

RPO của một kiến trúc không nhất thiết giống nhau cho mọi loại sự cố.

| Failure scenario | Recovery path thường gặp | RPO phụ thuộc |
|---|---|---|
| Primary process crash | Crash recovery tại chỗ | WAL đã ghi bền vững và storage |
| Mất primary host | Promote standby hoặc restore backup | Sync/async replication, archive |
| Mất storage/cluster | Restore base backup + WAL | Base backup, archive continuity |
| Xóa nhầm dữ liệu | PITR tới trước transaction phá hoại | WAL archive và target selection |
| Corruption lan vào backup | Backup khác/immutable copy | Backup isolation và verification |
| Mất region | Cross-region standby/backup | Replication/archive cross-region lag |
| Mất replication link | Primary tiếp tục ghi hoặc bị giới hạn | Slot/WAL retention và topology |
| Ransomware/credential compromise | Clean-room restore | Immutable backup, keys và clean environment |

### 5.1. RPO của failover

Với failover, so sánh transaction cuối cùng được xác nhận trên primary cũ với transaction cuối cùng có trên standby được promote.

### 5.2. RPO của PITR

Với PITR, cần chọn một target trước sự kiện gây hỏng dữ liệu. RPO dữ liệu hợp lệ bị mất là khoảng từ last known-good commit tới recovery point được chọn; không phải thời gian từ lúc DBA phát hiện sự cố nếu corruption đã xảy ra trước đó.

### 5.3. RPO của backup định kỳ

Backup hằng ngày không nhất thiết có RPO 24 giờ nếu WAL được archive liên tục và đầy đủ. Base backup cadence ảnh hưởng lớn tới thời gian restore và lượng WAL phải replay; archive gap mới có thể làm mất khả năng phục hồi tới thời điểm gần nhất.

## 6. RTO phụ thuộc vào toàn bộ recovery path

RTO thường gồm các giai đoạn:

```text
Detect incident
      |
      v
Declare / decide recovery path
      |
      v
Fence old primary / prepare target
      |
      v
Provision compute and storage
      |
      v
Restore base backup or promote standby
      |
      v
Replay WAL / reach recovery point
      |
      v
Validate database and application
      |
      v
Cut over traffic
      |
      v
Observe service health
```

Một số giai đoạn có thể chạy song song, ví dụ provision network và xác minh backup metadata. Khi tính RTO tổng, dùng timeline thực tế và critical path; không cộng máy móc mọi duration nếu các công việc chồng lấp.

### 6.1. Restore throughput

Thời gian copy phụ thuộc:
- Kích thước backup.
- Throughput storage/network.
- Compression/encryption.
- Số files và metadata overhead.
- Parallelism của công cụ.
- Tablespace mapping.
- Thời gian provision host.

### 6.2. WAL replay throughput

WAL replay phụ thuộc:
- Lượng WAL cần replay.
- I/O random/sequential và storage latency.
- CPU, compression và checksums.
- Số lượng indexes/relations thay đổi.
- Recovery conflicts nếu dùng standby.
- Các thiết lập và giới hạn của môi trường restore.

### 6.3. Validation và cutover cũng tốn thời gian

Kiểm tra schema, critical row counts, application smoke tests, sequence values, permissions, DNS, load balancer và connection pools có thể chiếm phần đáng kể RTO.

## 7. Sự khác nhau giữa failover và PITR

### 7.1. Failover sang standby

Dùng standby đã nhận WAL để trở thành primary mới. Thường nhanh hơn restore full backup vì data files đã có sẵn và standby đã replay phần lớn WAL.

RPO phụ thuộc replication mode, standby state, acknowledged commits và thời điểm promotion.

### 7.2. PITR từ base backup

Tạo một data directory từ base backup rồi replay WAL tới target. Đây là đường phục hồi hữu ích khi:
- Mất toàn bộ cluster.
- Cần quay về trước thao tác phá hoại.
- Standby đã nhận cả thay đổi lỗi.
- Cần dựng một bản copy cô lập để trích xuất dữ liệu.

RTO thường dài hơn vì phải provision, transfer/restore và replay.

### 7.3. Logical restore

pg_dump/pg_restore hữu ích cho object-level recovery/migration, nhưng restore lượng dữ liệu lớn có thể chậm hơn physical restore. Đo riêng loại backup này.

### 7.4. Không dùng một drill để đại diện mọi đường

Một failover drill nhanh không chứng minh PITR hoạt động. Một PITR drill thành công không chứng minh failover không split-brain. Mỗi failure scenario cần bài thử tương ứng.

## 8. Đo RPO với transaction marker

Một cách thực tế là tạo một marker transaction định kỳ, sau khi commit thành công ghi nhận marker đó vào một hệ thống witness độc lập.

Ví dụ bảng trong database:

```sql
CREATE SCHEMA IF NOT EXISTS dr_test;

CREATE TABLE dr_test.recovery_marker (
    marker_id uuid PRIMARY KEY,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    sequence_no bigint NOT NULL,
    note text
);
```

Một test agent thực hiện:
1. Sinh marker_id duy nhất.
2. Ghi transaction marker vào PostgreSQL.
3. COMMIT.
4. Chỉ sau khi server xác nhận COMMIT thành công, ghi marker_id, sequence_no và thời điểm vào external witness/monitoring system.
5. Sau failover/restore, truy vấn marker cuối cùng có trong database.
6. So sánh với witness ledger.

### 8.1. Vì sao cần witness độc lập?

Nếu chỉ nhìn marker trong database đã phục hồi, ta không biết marker mới nhất nào đã được xác nhận trước sự cố. External witness lưu lại những commit mà test agent đã nhận acknowledgment.

### 8.2. Witness cũng cần durability

Nếu external witness nằm cùng failure domain với database, một sự cố có thể xóa cả hai. Dùng hệ thống logging/monitoring độc lập phù hợp và đảm bảo event được ghi bền vững.

### 8.3. Không ghi witness trước COMMIT

Nếu ghi marker vào witness trước khi transaction commit, phép đo có thể báo một transaction “đã được xác nhận” dù database chưa commit. Ghi witness sau khi nhận thành công COMMIT.

### 8.4. Marker không thay transaction ledger của ứng dụng

Marker đo recovery path và WAL/replication behavior. Nó không chứng minh mọi bảng nghiệp vụ, sequence hay transaction pattern đều nhất quán. Cần kiểm tra application data riêng.

## 9. Tính RPO theo timestamp và transaction sequence

Ví dụ external witness:

```text
10:00:00.000 marker 1001 COMMIT acknowledged
10:00:05.000 marker 1002 COMMIT acknowledged
10:00:10.000 marker 1003 COMMIT acknowledged
10:00:15.000 marker 1004 COMMIT acknowledged
10:00:20.000 primary failure
```

Sau recovery, marker mới nhất là 1002. Khi đó:
- Last acknowledged marker: 1004.
- Last recoverable marker: 1002.
- Lost acknowledged markers: 1003 và 1004.
- Time gap gần đúng: 10 giây từ marker 1002 tới failure, theo cách định nghĩa ví dụ.

### 9.1. Tính theo transaction

```sql
SELECT
    max(sequence_no) AS last_recovered_sequence,
    max(committed_at) AS last_recovered_marker_time
FROM dr_test.recovery_marker;
```

So sánh sequence với external witness để tính số marker đã mất. Nếu marker cadence là 5 giây, số marker mất không tương đương chính xác số transaction business mất; đây là phép đo định kỳ, không phải audit đầy đủ.

### 9.2. Timestamp cần đồng bộ

Dùng NTP/chrony hoặc dịch vụ time synchronization phù hợp cho host/database/witness. Lưu timestamp UTC và ghi rõ timezone khi hiển thị. Sai lệch đồng hồ có thể làm RPO time-based sai.

### 9.3. Dùng monotonic clock cho duration

Để đo thời lượng trong một process, dùng monotonic clock của hệ điều hành/test harness thay vì trừ wall-clock timestamps có thể bị điều chỉnh. Ghi cả wall-clock event time và elapsed duration.

## 10. Đo RPO khi failover replication

Trên primary, có thể quan sát trạng thái standby qua pg_stat_replication:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Ý nghĩa khái quát:
- sent_lsn: WAL đã gửi tới standby.
- write_lsn: WAL standby đã ghi.
- flush_lsn: WAL standby đã flush theo protocol.
- replay_lsn: WAL standby đã replay.
- sync_state: trạng thái synchronous/asynchronous theo cấu hình.

### 10.1. LSN lag theo byte

Có thể so sánh current LSN với standby LSN:

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS replay_lag_bytes
FROM pg_stat_replication;
```

Đây là chênh lệch LSN tại thời điểm query. Nó không trực tiếp cho biết thời gian mất dữ liệu khi failover, và có thể thay đổi ngay sau snapshot.

### 10.2. Lag intervals có giới hạn

write_lag/flush_lag/replay_lag là các chỉ báo độ trễ theo mẫu gần đây trong điều kiện phù hợp; chúng không phải cam kết standby sẽ mất đúng lượng thời gian đó khi primary crash. Khi hệ thống idle, các giá trị có thể NULL hoặc không phản ánh backlog hiện tại.

### 10.3. Đo trên standby

Có thể xem:

```sql
SELECT
    pg_last_wal_receive_lsn() AS last_received_lsn,
    pg_last_wal_replay_lsn() AS last_replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

last_replayed_commit_time có thể cũ dù standby đang đồng bộ nếu primary không có transaction mới. Không dùng timestamp đơn lẻ làm cảnh báo lag cho workload idle.

### 10.4. Xác minh sau promotion

Sau khi promote, so sánh marker sequence trên primary mới với witness ledger. Đó là phép đo thực tế của acknowledged data loss trong drill.

## 11. Synchronous replication và cam kết RPO

Synchronous replication có thể giảm RPO cho các transaction được xác nhận sau khi WAL đạt standby theo mức đồng bộ cấu hình.

Các khái niệm cần phân biệt:

- synchronous_standby_names: xác định standby nào tham gia xác nhận đồng bộ.
- synchronous_commit: mức chờ trước khi xác nhận commit.
- remote_write: chờ standby ghi WAL tới hệ điều hành, không đồng nghĩa durable flush.
- on: với synchronous replication, chờ standby flush WAL bền vững theo semantics PostgreSQL.
- remote_apply: chờ standby replay WAL, hữu ích khi cần đọc ngay trên standby sau commit.

### 11.1. RPO = 0 chỉ trong failure model đã xác định

Nếu transaction commit acknowledgment chờ standby durable flush và standby đó được chọn đúng để promote, có thể bảo vệ các acknowledged commits trước một số failure scenarios. Nhưng điều này không bao gồm mọi sự cố đồng thời, cấu hình sai, forced promotion sang standby khác hoặc mất cả failure domain.

### 11.2. Synchronous replication có trade-off

- Commit latency tăng theo network/standby flush.
- Standby/network failure có thể làm transaction chờ hoặc bị ảnh hưởng theo cấu hình.
- Cần thiết kế quorum/standby availability.
- Phải xác minh promotion policy thực tế.

### 11.3. Không chỉ kiểm tra setting

Một dòng synchronous_commit = on không chứng minh cluster có synchronous standby hoạt động. Đọc pg_stat_replication, synchronous_standby_names, sync_state và thực hiện failover drill.

## 12. Đo archive freshness và WAL continuity

Nếu dùng WAL archive cho PITR, theo dõi pg_stat_archiver:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

### 12.1. Archive age

```sql
SELECT
    now() - last_archived_time AS age_since_last_archive,
    archived_count,
    failed_count,
    last_archived_wal,
    last_failed_wal
FROM pg_stat_archiver;
```

Đây chỉ là thời gian từ lần archive thành công gần nhất. Nếu không có writes hoặc segment chưa switch, giá trị cũ không tự chứng minh mất WAL.

### 12.2. Archive continuity quan trọng hơn last success

Một archive có segment mới nhất vừa được upload nhưng thiếu một segment ở giữa vẫn không phục hồi liên tục được tới target. Kiểm tra inventory, archive logs và khả năng restore thực tế.

### 12.3. Timeline history

Giữ các .history files liên quan. Nếu failover tạo timeline mới, cần history file để recovery chọn đúng nhánh WAL.

### 12.4. Archive storage availability

Đo:
- Upload success/failure.
- Oldest unarchived WAL.
- Object storage latency.
- Capacity/quota.
- Checksum verification.
- Credential expiry.
- Replication slot retention.

## 13. Base backup age ảnh hưởng gì?

Base backup cadence thường ảnh hưởng:
- Thời gian cần copy/restore.
- Lượng WAL phải replay sau base backup.
- Storage cost.
- Cửa sổ retention.
- Khả năng chọn một base backup còn nguyên vẹn.

Base backup mỗi 24 giờ không nhất thiết tạo RPO 24 giờ nếu WAL được archive liên tục và đủ segment. Nhưng backup cũ hơn có thể làm replay lâu hơn, ảnh hưởng RTO.

### 13.1. Đo restore duration theo tuổi backup

Thực hiện restore test với:
- Base backup mới nhất.
- Một backup ở giữa retention window.
- Backup cũ nhất còn được giữ.

Mục tiêu là hiểu worst-case RTO trong chính sách retention, không chỉ đường restore nhanh nhất.

### 13.2. Backup mới nhất không luôn tốt nhất

Backup mới nhất có thể hỏng, thiếu WAL, ở storage chậm hoặc thuộc timeline không phù hợp. Cần chọn backup hợp lệ theo metadata/verification.

### 13.3. Incremental backup chain

Nếu dùng incremental backups, restore time còn phụ thuộc combine/parent chain. Đo toàn bộ chain, không chỉ thời gian tải incremental mới nhất.

## 14. Xây RPO/RTO matrix theo dịch vụ

Không phải mọi database đều có cùng mức quan trọng.

Ví dụ policy minh họa:

| Tier | Ví dụ workload | RPO mục tiêu | RTO mục tiêu |
|---|---|---:|---:|
| Tier 0 | Ledger/payment core | 0–1 phút theo failure model | 15 phút |
| Tier 1 | Customer/order OLTP | 5 phút | 60 phút |
| Tier 2 | Internal reporting | 1 giờ | 4 giờ |
| Tier 3 | Historical analytics | 24 giờ | 24–48 giờ |

Các con số phải do business owner/engineering/operations thống nhất, không sao chép trực tiếp.

### 14.1. Xếp hạng theo business impact

Cân nhắc:
- Mất dữ liệu ảnh hưởng pháp lý/tài chính?
- Dịch vụ có thể chạy read-only tạm thời?
- Có workaround thủ công?
- Mất bao lâu trước khi ảnh hưởng khách hàng?
- Có phụ thuộc hệ thống downstream?

### 14.2. Một cluster có thể chứa nhiều tier

Nếu database chứa nhiều workloads, cần quyết định recovery unit. Một database restore có thể ảnh hưởng mọi schema; không thể giả định từng bảng có RTO độc lập nếu cùng nằm trong cluster.

### 14.3. Mục tiêu phải có owner

Mỗi RPO/RTO phải có business owner và technical owner. DBA không nên tự cam kết một RTO mà hạ tầng, ứng dụng và networking không thể đáp ứng.

## 15. Lập kế hoạch đo RTO theo từng giai đoạn

Một bảng event log cho drill:

| Giai đoạn | Mốc ghi nhận | Ví dụ duration |
|---|---|---:|
| Detect | Alert/incident start | 3 phút |
| Declare | Incident commander quyết định | 4 phút |
| Fence | Chặn old primary/split-brain | 2 phút |
| Provision | Host/storage/network | 8 phút |
| Restore | Copy/prepare base backup | 18 phút |
| Replay | Replay WAL tới target | 12 phút |
| Validate | DB + application checks | 10 phút |
| Cutover | DNS/route/pool | 5 phút |
| Observe | Smoke/health confirmation | 5 phút |

Tổng ví dụ 67 phút nếu các bước nối tiếp. Nếu có bước song song, tính theo critical path thực tế.

### 15.1. Dùng timestamp có cấu trúc

Ghi event ID, step name, start time, end time, elapsed duration, actor và evidence link.

### 15.2. Tách thời gian chờ quyết định

Incident có thể mất 20 phút để xác định có restore hay không. Đây là phần RTO thực tế và cần cải thiện bằng decision tree/ownership rõ ràng.

### 15.3. Tách technical restore và service recovery

Có thể ghi:
- Database available time.
- Application read-ready time.
- Application write-ready time.
- Full service restored time.

Chọn mốc cuối làm RTO chính nếu business yêu cầu service hoàn chỉnh.

### 15.4. Đo cả manual và automated time

Nếu một bước phụ thuộc người trực đăng nhập, phê duyệt hoặc tìm credential, ghi thời gian đó. Không bỏ qua human latency.

## 16. Thiết kế restore drill an toàn

Restore drill nên chạy trong môi trường cô lập, không ảnh hưởng production traffic.

Một drill vật lý/PITR:
1. Chọn backup ID và recovery target.
2. Xác minh backup manifest/checksum.
3. Provision host/storage.
4. Tải và restore base backup.
5. Cấu hình tablespaces/permissions.
6. Cấu hình restore_command và recovery target.
7. Tạo recovery.signal nếu cần.
8. Start PostgreSQL và theo dõi replay.
9. Pause/promote theo test design.
10. Chạy data/application checks.
11. Ghi RPO/RTO.
12. Dọn test environment theo policy.

### 16.1. Drill phải dùng artifact thật

Dùng backup repository và WAL archive thực tế, không dùng một bộ file đặc biệt được chuẩn bị sẵn chỉ cho demo.

### 16.2. Không restore đè production

Dùng network/port/hostname riêng. Tắt application jobs, outbound integrations và scheduled workers có thể gửi email, thanh toán hoặc tạo side effects.

### 16.3. Test cả đường thất bại

Có thể tạo các tình huống:
- Archive object thiếu.
- Manifest checksum mismatch.
- Tablespace mount không có.
- Encryption key không truy cập được.
- Recovery target nằm sau WAL cuối cùng.
- Timeline history thiếu.
- Disk không đủ.
- Credentials hết hạn.

Mục tiêu là xác định điểm hỏng và thời gian phát hiện.

## 17. Failover drill khác restore drill

Failover drill kiểm tra:
- Standby có đủ WAL.
- Synchronous/async state.
- Promotion procedure.
- Fencing old primary.
- DNS/load balancer/connection routing.
- Repointing replicas.
- Application retry behavior.
- Split-brain prevention.

### 17.1. Không chỉ chạy pg_promote()

Một lệnh promotion thành công không chứng minh dịch vụ đã failover. Cần xác nhận old primary không tiếp tục nhận writes, new primary đúng timeline, ứng dụng kết nối và replication topology được tái lập.

### 17.2. Fencing

Phải có cách ngăn old primary tiếp tục ghi sau khi new primary được promote. Có thể cần cloud/VM/storage/network fencing theo kiến trúc. Đây là phần quan trọng để tránh split-brain.

### 17.3. Đo data loss thực tế

Dùng transaction markers/witness ledger và so sánh acknowledged commits. Không dùng mỗi replay lag interval làm actual RPO.

### 17.4. Đo time to write-ready

Một endpoint health check trả 200 không đủ. Thực hiện một transaction test có kiểm soát và xác minh commit/read-back trên primary mới.

## 18. Kiểm tra dữ liệu sau recovery

PostgreSQL khởi động thành công không có nghĩa dữ liệu nghiệp vụ hoàn toàn đúng với mục tiêu phục hồi.

Các lớp kiểm tra:

### 18.1. Cluster-level

- Server version/cluster identity.
- Recovery target và timeline.
- Database list.
- Roles/tablespaces/extensions.
- WAL recovery logs.
- Replication/archive state.

### 18.2. Database-level

- Schema/tables tồn tại.
- Critical row counts hoặc aggregate totals.
- Constraints và indexes hợp lệ.
- Sequences/identity values.
- Permissions/ownership.
- Large objects và TOAST-backed values.
- Expected migration/schema version.

### 18.3. Application-level

- Authentication.
- Read/write paths.
- Critical API operations.
- Background workers.
- Message queues/outbox.
- External storage dependencies.
- Payment/notification integrations ở chế độ test hoặc đã được kiểm soát.

### 18.4. Business invariants

Ví dụ:
- Tổng debit/credit cân bằng.
- Mỗi order có trạng thái hợp lệ.
- Không có payment duplicate.
- Foreign key/business reference còn đúng.
- Event sequence không bị lặp hoặc bỏ qua ngoài policy.

### 18.5. Không chỉ dựa vào COUNT(*)

Row count bằng nhau không chứng minh nội dung đúng. Dùng checksums/aggregates/semantic invariants cho các bảng trọng yếu.

## 19. Kiểm tra sequences và identity sau PITR

Sau khi restore tới một thời điểm, sequence state cũng thuộc dữ liệu phục hồi. Nếu ứng dụng tiếp tục ghi, cần kiểm tra giá trị next sequence phù hợp và không trùng key đã tồn tại.

Có thể xem sequence state bằng catalog/sequence functions phù hợp với version. Không tự đặt sequence về MAX(id)+1 trên mọi bảng mà không hiểu cache, ownership, partitioning và concurrent writes.

### 19.1. Sequence có thể có gaps

Sequence values không transactional như row updates; rollback có thể để lại gaps. Không yêu cầu sequence liên tục trừ khi business design thực sự cần điều đó.

### 19.2. PITR và external systems

Nếu database quay về trước một payment nhưng payment gateway đã xử lý giao dịch, cần reconciliation với external system. PITR không rollback các side effects ngoài database.

### 19.3. Outbox/inbox patterns

Nếu ứng dụng dùng outbox, event delivery và consumer idempotency phải được kiểm tra sau recovery để tránh gửi lại hoặc bỏ sót side effects.

## 20. Cập nhật quy trình khôi phục sau mỗi drill

Runbook là tài liệu vận hành sống. Sau mỗi lần diễn tập hoặc sự cố, cần cập nhật:

- Phiên bản PostgreSQL và công cụ backup/restore.
- Recovery scenario và decision tree.
- RPO/RTO target và actual.
- Backup ID/WAL range/timeline đã dùng.
- Commands/options chính xác.
- Hostnames/ports/storage mappings.
- Credentials/secret retrieval path, không ghi secret vào tài liệu.
- Tablespace paths và capacity.
- Network/firewall/DNS/load balancer steps.
- Validation queries và application smoke tests.
- Owner/approver/escalation contacts.
- Known limitations và failure modes.
- Ngày diễn tập tiếp theo.

### 20.1. Version control

Lưu runbook trong source control hoặc hệ thống tài liệu có revision history, review và quyền truy cập phù hợp.

### 20.2. Không lưu mật khẩu trong runbook

Ghi nơi lấy secret, role cần dùng và quy trình cấp quyền. Secret phải nằm trong secret manager/vault phù hợp.

### 20.3. Gắn evidence vào từng bước

Mỗi bước có:
- Expected result.
- Actual result.
- Log/metric/query output reference.
- Failure condition.
- Escalation path.

### 20.4. Đặt ngày hết hạn review

Runbook không được coi là đúng mãi mãi. Sau major upgrade, đổi storage, đổi cloud region, thay DNS hoặc thay backup tooling phải review lại.

## 21. Recovery decision tree

```text
Incident declared
      |
      v
Is primary healthy and data logically valid?
      |
      +-- Yes -> repair/restart or crash recovery
      |
      +-- No
           |
           v
Can a trusted standby be promoted safely?
           |
           +-- Yes -> fence old primary -> promote -> validate
           |
           +-- No
                |
                v
Is there a verified base backup + continuous WAL?
                |
                +-- Yes -> restore + replay to selected target
                |
                +-- No
                     |
                     v
              Find alternate backup/replica
              and declare actual RPO limitations
```

### 21.1. Logical corruption

Nếu primary vẫn hoạt động nhưng một transaction đã phá dữ liệu, không vội promote standby nếu standby đã replay transaction lỗi. PITR sang target trước corruption thường phù hợp hơn.

### 21.2. Physical loss

Nếu primary host/storage mất, standby khỏe có thể cho RTO thấp hơn restore full backup. Nhưng cần fencing và xác nhận replication state.

### 21.3. Không có WAL đầy đủ

Chọn backup/replica khác có thể phục hồi, xác định last recoverable point và thông báo actual RPO. Không khẳng định PITR tới thời điểm không có WAL.

## 22. Cập nhật RPO/RTO khi kiến trúc thay đổi

Các thay đổi có thể làm số đo cũ mất hiệu lực:
- Database tăng kích thước.
- WAL generation rate tăng.
- Thêm indexes/TOAST-heavy columns.
- Chuyển storage class/region.
- Đổi compression/encryption.
- Đổi sync/async replication.
- Thay số standby hoặc quorum.
- Đổi backup cadence/retention.
- Thay công cụ restore.
- Thêm partition hoặc tablespace.
- Thay đổi application dependencies.

Sau mỗi thay đổi lớn, chạy benchmark/drill đại diện và cập nhật target feasibility.

### 22.1. Dự báo tăng trưởng

RTO hiện đạt 40 phút với 1 TB chưa chắc đạt khi database tăng lên 3 TB. Đo throughput và replay rate để dự báo, sau đó xác nhận bằng test.

### 22.2. WAL generation burst

Bulk load, index build, batch update hoặc full-page writes có thể làm WAL generation tăng đột biến. Archive bandwidth phải chịu được peak, không chỉ average.

### 22.3. Thay đổi sync replication

Thay synchronous_standby_names hoặc synchronous_commit có thể thay đổi commit latency và durability assumptions. Cập nhật failure model/RPO và diễn tập lại.

## 23. RPO/RTO và backup frequency

Backup frequency thường tác động trực tiếp tới restore chain:

- Base backup thường xuyên hơn: ít WAL phải replay, nhưng nhiều storage/network/backup load.
- Base backup thưa hơn: giảm backup load, nhưng restore có thể cần replay nhiều WAL hơn.
- WAL archive liên tục: hỗ trợ PITR giữa hai base backups.
- Archive gap: có thể làm recovery dừng trước target.

```text
Backup A
   |
   +-- WAL 1 -- WAL 2 -- WAL 3 -- WAL 4 -- Backup B
                                  |
                                  +-- PITR target
```

### 23.1. Không dùng backup interval làm actual RPO

Nếu WAL archive liên tục và bền vững, actual recoverable point có thể gần failure time hơn base backup timestamp.

### 23.2. Backup frequency có thể cải thiện RTO

Base backup mới hơn giảm lượng WAL cần replay, nhưng phải đo vì transfer, restore và manifest verification vẫn có chi phí.

### 23.3. Chọn interval từ restore tests

Thử các base backup age khác nhau và so sánh total restore time, storage cost, backup load. Chọn interval theo RTO và capacity.

## 24. RPO/RTO và archive_timeout

archive_timeout có thể giúp archive segment mới thường xuyên hơn trong workload ít ghi, nhưng không bảo đảm RPO bằng đúng giá trị cấu hình.

RPO thực tế còn phụ thuộc:
- Segment có được switch và archive không.
- Archive command thành công không.
- File có bền vững ở failure domain khác không.
- Có segment nào thiếu giữa chuỗi không.
- Backup chain và timeline có hợp lệ không.
- Commit nào đã được acknowledged trước sự cố.

Một archive_timeout 5 phút không cứu được một archive command thất bại 2 giờ.

## 25. RPO/RTO và replication lag

Replication lag có thể đo theo:
- LSN bytes.
- Write/flush/replay positions.
- Time interval metrics.
- Transaction marker sequence.
- External witness.

Không dùng một con số duy nhất làm đại diện cho tất cả.

### 25.1. Byte lag không phải time lag

100 MB WAL có thể tương ứng vài giây hoặc nhiều phút tùy workload. WAL generation rate thay đổi.

### 25.2. Replay lag không phải acknowledged data loss

Một standby có thể đang replay chậm nhưng đã nhận/flush WAL. Khi promote, khả năng mất dữ liệu phụ thuộc promotion semantics và WAL được giữ, không chỉ replay lag.

### 25.3. Synchronous state cần được xác minh

Nếu RPO dựa vào synchronous replication, kiểm tra standby nào được coi là synchronous tại thời điểm failure. Một standby không thuộc quorum có thể không chứa mọi acknowledged commit.

## 26. Đo archive và replication bằng LSN

Trên primary:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_insert_lsn() AS current_insert_lsn;
```

Trên primary có thể xem replica positions:

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
        replay_lsn
    ) AS replay_lag_bytes
FROM pg_stat_replication;
```

Trên standby:

```sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 26.1. LSN phải được so sánh cùng cluster/timeline

Không lấy LSN từ hai cluster khác nhau rồi coi chênh lệch là replication lag. Sau promotion, timeline thay đổi và cần xét history.

### 26.2. Chụp metrics theo thời gian

Một lần query không cho biết xu hướng. Lưu samples với timestamp, server identity và timeline để phân tích.

### 26.3. Version compatibility

Một số functions/view fields khác nhau theo version. Dùng pg_catalog/pg_settings và tài liệu đúng server version trước khi đưa query vào monitoring lâu dài.

## 27. Đo RTO trong clean-room recovery

Clean-room recovery là phục hồi trong môi trường tách biệt, nơi không phụ thuộc vào host/credentials/storage của production đã bị sự cố.

Đo các thành phần:
1. Tạo/khởi tạo môi trường.
2. Lấy credentials và encryption keys.
3. Download base backup.
4. Verify manifest/checksums.
5. Restore data/tablespaces.
6. Lấy WAL archive.
7. Replay tới target.
8. Start và kiểm tra PostgreSQL.
9. Chạy application validation.
10. Route traffic hoặc cung cấp dữ liệu cho ứng dụng.

### 27.1. Test mất quyền production

Một DR drill tốt cần chứng minh backup team vẫn có thể truy cập repository và keys khi production identity provider hoặc primary account gặp sự cố, theo threat model đã định nghĩa.

### 27.2. Test offsite copy

Không chỉ test bản backup nằm gần primary. Chọn bản ở failure domain khác để đo RTO thực tế khi mất region/site.

### 27.3. Test capacity thật

Restore 2 TB trên máy 8 vCPU/SSD không đại diện cho restore 2 TB trên máy DR nhỏ hơn. Dùng đúng class hoặc ghi rõ chênh lệch.

## 28. Tối ưu RTO có mục tiêu

Nếu RTO không đạt, chia bottleneck trước khi mua thêm hạ tầng.

| Bottleneck | Biện pháp có thể thử |
|---|---|
| Provision lâu | IaC, pre-created network, quota reservation |
| Download backup chậm | Storage gần DR, parallel transfer, throughput budget |
| Restore file chậm | Fast storage, parallelism phù hợp, file layout |
| WAL replay lâu | Base backup mới hơn, tăng restore capacity, đo replay throughput |
| Validation lâu | Automated checks và test data contracts |
| DNS/cutover lâu | TTL/runbook/automation được kiểm thử |
| Credentials thiếu | DR secret access path và escrow |
| Human decision chậm | Decision tree, owner và escalation rõ |
| Replication rebuild lâu | Standby topology và WAL retention plan |

### 28.1. Không tối ưu một bước rồi bỏ qua critical path

Nếu download backup chiếm 80% RTO, tối ưu SQL validation thêm 20% không làm RTO giảm nhiều.

### 28.2. Warm standby

Standby được provision và replay liên tục có thể giảm RTO, đổi lại chi phí compute/storage/network và yêu cầu fencing/failover discipline.

### 28.3. Backup restore parallelism

Tăng parallel jobs có thể cải thiện throughput nếu storage/CPU còn headroom. Quá nhiều workers có thể gây contention; đo trên dữ liệu đại diện.

## 29. Tối ưu RPO có mục tiêu

Nếu actual RPO không đạt:
- Sửa archive failures và missing WAL trước.
- Giảm archive upload latency.
- Tăng durability/failure-domain independence.
- Xem xét streaming replication.
- Xem xét synchronous replication cho tier cần RPO rất thấp.
- Điều chỉnh archive_timeout khi phù hợp.
- Giữ đủ WAL và timeline history.
- Theo dõi replication slots và archive backlog.
- Dùng transaction markers/witness để xác nhận.

### 29.1. Không chỉ giảm archive_timeout

Nếu upload object mất 10 phút hoặc bị retry 30 phút, archive_timeout 1 phút không giúp RPO thực tế.

### 29.2. Không tăng WAL retention vô hạn

Giữ WAL lâu hơn cần storage và capacity. Retention phải gắn với backup catalog/recovery window và slot consumers.

### 29.3. Sync replication không thay backup

Synchronous standby có thể nhận transaction lỗi hoặc bị xóa nhầm. PITR/backup vẫn cần thiết để phục hồi logical corruption và disaster scenarios khác.

## 30. Định nghĩa thành công của từng loại drill

| Drill | Thành công khi |
|---|---|
| Backup verification | Manifest/checksums và metadata hợp lệ |
| Base restore | Server start và đạt consistency |
| PITR | Dừng đúng target/timeline, dữ liệu trước sự kiện đúng |
| Standby failover | Promote đúng node, old primary được fence, app write-ready |
| Regional DR | Restore/failover trong failure domain khác, dependencies đầy đủ |
| Application recovery | Critical read/write flows và invariants đạt |
| Ransomware recovery | Dùng clean immutable copy/keys, môi trường sạch |
| Runbook tabletop | Người tham gia quyết định đúng, biết owner/escalation |

### 30.1. Backup verification chưa phải restore drill

pg_verifybackup kiểm tra base backup theo manifest/checksums. Nó không chứng minh archive WAL đầy đủ hay application hoạt động.

### 30.2. Tabletop chưa phải technical drill

Tabletop xác minh quyết định và vai trò, không đo throughput restore/replay.

### 30.3. Failover drill chưa phải PITR drill

Mỗi loại kiểm tra một đường phục hồi khác nhau. Lập lịch cho từng loại theo risk.

## 31. Lịch diễn tập mẫu

Một lịch tham khảo cần điều chỉnh theo tier/risk:

| Tần suất | Bài kiểm tra | Mục tiêu |
|---|---|---|
| Hằng ngày | Backup/archiver health, capacity, replication | Phát hiện lỗi sớm |
| Hằng tuần | Verify manifest và inventory WAL | Xác nhận artifacts có thể kiểm tra |
| Hằng tháng | Restore một base backup + WAL tới target | Đo physical restore và replay |
| Hằng quý | Failover/standby promotion drill | Đo failover RPO/RTO và fencing |
| Hằng quý/nửa năm | Regional/clean-room recovery | Kiểm tra offsite, keys và dependencies |
| Sau thay đổi lớn | Drill liên quan | Xác nhận runbook/assumptions mới |

### 31.1. Chọn sample có tính đại diện

Không chỉ restore database nhỏ nhất. Luân phiên bảng/cluster lớn, partitioned, TOAST-heavy và workload có WAL rate cao.

### 31.2. Diễn tập ngoài giờ không thay thế kiểm tra ban ngày

Có thể cần kiểm tra readiness và access path trong giờ làm việc, nhưng failure injection cần guardrails và phê duyệt theo change policy.

### 31.3. Đừng để drill chỉ chạy khi có audit

Một backup có thể hỏng ngay sau lần kiểm tra. Duy trì cadence và automated alerts.

## 32. Đo bằng percentile và xu hướng

Với nhiều drill, lưu:
- Actual RPO.
- Actual RTO.
- Restore duration.
- WAL replay duration.
- Validation duration.
- Transfer throughput.
- WAL generation rate.
- Error/retry counts.

Báo cáo:
- Median.
- P95 khi có đủ sample.
- Maximum observed.
- Trend theo dung lượng và workload.
- Kết quả theo scenario/region/backup age.

### 32.1. Không gộp các scenario khác nhau

PITR từ base backup và failover standby có phân bố RTO khác nhau. Báo cáo riêng theo scenario.

### 32.2. Số mẫu nhỏ có thể gây hiểu lầm

Ba lần drill không đủ để khẳng định P95 ổn định. Ghi sample count và điều kiện test.

### 32.3. Đo cả biến động

Nếu RTO trung bình 45 phút nhưng có lần 3 giờ vì credential outage, tail risk quan trọng hơn average.

## 33. Evidence record cho mỗi drill

Một record tối thiểu:

```text
drill_id:
scenario:
service_tier:
database_cluster:
postgres_major_version:
source_backup_id:
source_backup_timestamp:
timeline:
recovery_target:
incident_start_utc:
last_acknowledged_marker:
last_recovered_marker:
actual_rpo:
actual_rto:
provision_duration:
backup_transfer_duration:
restore_duration:
wal_replay_duration:
validation_duration:
cutover_duration:
backup_verification:
wal_continuity:
application_checks:
data_invariants:
issues:
owner:
reviewer:
runbook_revision:
follow_up_actions:
next_test_date:
```

### 33.1. Ghi rõ điều kiện môi trường

Bao gồm instance size, storage class, network path, region, compression và concurrency. Nếu không, không thể so sánh hai lần drill.

### 33.2. Không ghi secrets hoặc dữ liệu nhạy cảm không cần thiết

Evidence nên chứa identifiers/log references đã được kiểm soát, không chứa password, private keys hay payload nghiệp vụ đầy đủ.

### 33.3. Liên kết evidence với runbook revision

Nếu một lần drill dùng runbook revision cũ, phải ghi rõ để biết procedure hiện tại đã được thử chưa.

## 34. Quy trình cập nhật runbook

Sau mỗi drill/sự cố:

1. So sánh actual RPO/RTO với target.
2. Xác định giai đoạn hoặc assumption gây chậm/mất dữ liệu.
3. Phân loại nguyên nhân: architecture, configuration, capacity, tooling, access, decision hoặc human process.
4. Tạo corrective action có owner và deadline.
5. Cập nhật command/config examples theo server version.
6. Cập nhật decision tree, validation queries và escalation.
7. Review với DBA, application owner, infrastructure/security và business owner phù hợp.
8. Merge/publish revision theo quy trình quản lý tài liệu.
9. Chạy lại phần drill bị lỗi.
10. Ghi ngày review tiếp theo.

### 34.1. Cập nhật phải cụ thể

Không ghi “tối ưu restore”. Ghi ví dụ: “Tăng network throughput DR từ X lên Y; mục tiêu giảm backup transfer từ 42 xuống 25 phút; owner là Platform; xác minh trong drill ngày ...”.

### 34.2. Runbook phải có version

Ghi version PostgreSQL, pg_basebackup/restore tool, extension và operating environment. Cú pháp recovery có thể thay đổi giữa major versions.

### 34.3. Giữ lịch sử thay đổi

Không ghi đè kết quả drill cũ. Revision history giúp hiểu vì sao procedure thay đổi và cải thiện có thực sự hiệu quả không.

## 35. Ownership và escalation

Recovery thường cần nhiều nhóm:

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander | Tuyên bố incident, điều phối quyết định và timeline |
| DBA | Chọn recovery path, quản lý PostgreSQL/WAL/recovery |
| Infrastructure | Provision compute, storage, network |
| Security | Credentials, keys, clean-room controls |
| Application owner | Smoke tests và business invariants |
| Network/DNS | Routing, fencing và endpoint changes |
| Business owner | Chấp nhận RPO/data loss và quyết định cutover |
| Communications | Cập nhật trạng thái tới stakeholders |

### 35.1. Một người có thể giữ nhiều vai trò

Với nhóm nhỏ, một người có thể đảm nhiệm nhiều trách nhiệm. Tuy nhiên runbook vẫn phải ghi rõ ai quyết định và ai thực hiện.

### 35.2. Không để quyền phê duyệt làm tắc RTO

Xác định trước quyền quyết định promotion, restore target, data loss acceptance và traffic cutover. Không chờ tìm người có quyền giữa incident.

### 35.3. Access path phải được test

DBA có thể biết lệnh nhưng không có credential khi identity provider production gặp sự cố. Kiểm tra break-glass access theo policy.

## 36. Kiểm soát rủi ro khi diễn tập

Drill có thể gây tác động nếu chọn sai môi trường hoặc vô tình kết nối production.

Trước khi thử:
- Chọn environment và scope.
- Xác nhận không có route production traffic.
- Tắt jobs/integrations có side effects.
- Dùng test credentials.
- Đặt resource quotas.
- Xác định stop conditions.
- Có người quan sát và escalation.
- Xác nhận cleanup plan.

### 36.1. Production failover test

Nếu cần diễn tập trên production, dùng change management, blast radius nhỏ, rollback/fencing plan, stakeholder approval và giám sát. Không giả lập mất primary bằng cách kill server tùy tiện.

### 36.2. Chaos testing

Fault injection chỉ nên thực hiện trong môi trường được thiết kế cho nó. Bắt đầu bằng tabletop/restore sandbox, sau đó tăng độ thực tế theo năng lực kiểm soát.

### 36.3. Dừng drill khi guardrail bị vượt

Ví dụ: application latency vượt ngưỡng, replication lag vượt limit, storage gần đầy hoặc có nguy cơ split-brain. Ghi lại lý do dừng; đó cũng là một kết quả hữu ích.

## 37. Các lỗi khi đo RPO/RTO

### Lỗi 1 — Gọi backup interval là RPO

Backup chạy mỗi 24 giờ không nhất thiết là RPO 24 giờ nếu WAL archive liên tục.

### Lỗi 2 — Gọi archive_timeout là RPO

Đây chỉ là một tham số WAL switching, không chứng minh archive thành công hay continuity.

### Lỗi 3 — Gọi replication lag là actual RPO

Lag metric không trực tiếp cho biết acknowledged transactions đã mất sau promotion.

### Lỗi 4 — Đo RTO chỉ bằng restore command duration

Bỏ qua detection, decision, provisioning, validation và cutover.

### Lỗi 5 — Không định nghĩa start/end

Mỗi báo cáo dùng mốc khác nhau sẽ không thể so sánh.

### Lỗi 6 — Đồng hồ không đồng bộ

Timestamp giữa primary, standby, witness và test agent có thể lệch.

### Lỗi 7 — Không dùng external witness

Không biết marker cuối cùng nào đã được xác nhận trước sự cố.

### Lỗi 8 — Chỉ kiểm tra database start

Ứng dụng có thể không kết nối, không ghi được hoặc dữ liệu sai.

### Lỗi 9 — Không test WAL archive thật

Restore drill dùng dữ liệu mẫu không chứng minh production archive liên tục.

### Lỗi 10 — Chỉ test failover, không test PITR

Standby có thể chứa cả transaction phá hoại; PITR vẫn cần thiết.

### Lỗi 11 — Không test mất region/keys

Restore tại cùng site không chứng minh DR cross-region/clean-room.

### Lỗi 12 — Không ghi backup ID và timeline

Không thể tái lập đường phục hồi.

### Lỗi 13 — Không đo worst-case

Average tốt có thể che một lần restore cực chậm do thiếu credential hoặc archive object.

### Lỗi 14 — Không cập nhật runbook

Drill phát hiện lỗi nhưng procedure vẫn giữ lệnh cũ.

### Lỗi 15 — Không có owner cho corrective action

Các vấn đề được ghi nhận nhưng không được sửa.

### Lỗi 16 — Không xác minh external side effects

PITR có thể quay database về trước payment/email/event đã phát ra ngoài.

### Lỗi 17 — Đo marker cadence quá thưa

Marker mỗi 30 phút không đủ độ phân giải để xác minh RPO 5 phút.

### Lỗi 18 — Marker transaction không cùng durability path

Test marker phải đi qua cùng database/commit/replication path như workload cần đo.

### Lỗi 19 — Chỉ đo một kích thước database

RTO thay đổi theo size, WAL rate, index/TOAST và storage.

### Lỗi 20 — Không kiểm tra recovery target timezone/timeline

Có thể phục hồi đúng kỹ thuật nhưng sai điểm dữ liệu.

## 38. Ví dụ: đánh giá một hệ thống RPO 5 phút, RTO 60 phút

Giả sử mục tiêu:
- RPO <= 5 phút.
- RTO <= 60 phút.

Một restore drill cho kết quả:
- Incident start: 02:00:00 UTC.
- Last acknowledged marker: 02:00:00 UTC.
- Last recovered marker: 01:58:30 UTC.
- Service write-ready: 03:04:00 UTC.

Khi đó:
- Actual RPO = 1 phút 30 giây.
- Actual RTO = 64 phút.

RPO đạt, RTO không đạt.

### 38.1. Phân tích thời gian

| Giai đoạn | Duration |
|---|---:|
| Detect/declare | 8 phút |
| Provision | 10 phút |
| Restore base backup | 20 phút |
| WAL replay | 12 phút |
| Validation | 9 phút |
| Cutover | 5 phút |
| Tổng | 64 phút |

### 38.2. Chọn cải tiến

Nếu restore backup chiếm phần lớn thời gian, có thể:
- Tăng backup frequency nếu storage/cost cho phép.
- Dùng storage throughput cao hơn ở DR.
- Tối ưu parallel restore.
- Giữ warm standby cho tier yêu cầu RTO thấp.
- Tự động hóa provisioning và validation.

Không nên giảm archive_timeout để giải quyết RTO nếu RPO đã đạt và bottleneck là restore/replay.

### 38.3. Đo lại sau cải tiến

Thực hiện cùng scenario, cùng dataset size, cùng environment class và cùng định nghĩa mốc thời gian để so sánh công bằng.

## 39. Ví dụ: RTO đạt nhưng RPO không đạt

Giả sử:
- RPO target 5 phút.
- RTO target 60 phút.
- Failover standby hoàn tất trong 12 phút.
- Last acknowledged marker trên primary cũ là 10:30.
- Marker cuối trên standby promoted là 10:18.

Actual RPO xấp xỉ 12 phút; RTO 12 phút.

RTO đạt nhưng RPO không đạt. Cần điều tra:
- Async replication lag.
- Network throughput/interruption.
- Standby replay/flush position.
- Promotion chọn đúng standby chưa.
- Transaction acknowledgment semantics.
- Synchronous replication có phù hợp với tier này không?

Không kết luận “failover nhanh nên thành công”.

## 40. Ví dụ: PITR sau logical corruption

Một transaction xóa nhầm 200.000 rows lúc 14:00. Nhóm vận hành phát hiện lúc 14:20.

Các bước:
1. Ngừng job gây xóa và hạn chế writes liên quan.
2. Xác định transaction/time/LSN phá hoại.
3. Chọn recovery target ngay trước transaction đó.
4. Restore base backup và replay WAL tới target.
5. Kiểm tra rows đã được khôi phục.
6. Đánh giá các legitimate writes sau target.
7. Trích xuất/merge dữ liệu cần thiết hoặc cutover theo quyết định business.
8. Đo RTO tới khi ứng dụng hoạt động đúng.

Trong scenario này, thời điểm phát hiện 14:20 không phải mốc duy nhất để chọn target. Phải tìm thời điểm corruption thực sự xảy ra. Các transaction hợp lệ sau target có thể bị mất và cần reconciliation.

## 41. Cập nhật dashboard và alert

Dashboard RPO/RTO nên tách các tín hiệu:

### Backup health
- Last successful base backup.
- Backup duration/size.
- Manifest verification.
- Backup age.
- Restore drill result.

### WAL archive health
- Last archived WAL/time.
- Failed archive count delta.
- Archive backlog/oldest pending.
- WAL generation rate.
- Archive storage capacity.
- Timeline history inventory.

### Replication health
- Synchronous state.
- Sent/write/flush/replay LSN.
- Byte lag/time lag.
- Slot retained WAL.
- Standby availability.

### Recovery readiness
- Last successful PITR drill.
- Last failover drill.
- Actual RPO/RTO trend.
- Encryption key access test.
- Tablespace/host readiness.
- Runbook revision and owner.

### 41.1. Alert theo hành động

Mỗi alert cần nêu:
- Severity.
- Resource/cluster.
- Trigger và duration.
- RPO/RTO impact có thể có.
- Query/log/evidence.
- Runbook link.
- Owner/escalation.

### 41.2. Tránh alert noise

Dùng persistence/hysteresis cho các metric dao động, nhưng không trì hoãn cảnh báo critical như WAL archive failure kéo dài, disk gần đầy hoặc XID wraparound risk.

### 41.3. Dashboard không thay drill

Dashboard xanh chỉ chứng minh metric đang trong ngưỡng. Restore drill mới kiểm tra end-to-end.

## 42. Đánh giá khả năng đạt mục tiêu theo scenario

Một bảng report:

| Scenario | RPO target | RPO actual | RTO target | RTO actual | Status |
|---|---:|---:|---:|---:|---|
| Primary host loss | 1 phút | 20 giây | 15 phút | 12 phút | Đạt |
| Region loss | 5 phút | 4 phút | 60 phút | 82 phút | RTO chưa đạt |
| Logical corruption | 5 phút | 3 phút | 120 phút | 105 phút | Đạt |
| Backup repository loss | 15 phút | 18 phút | 4 giờ | 5 giờ | Chưa đạt |

Đây là số liệu minh họa. Luôn ghi date, sample count, backup age, data size và test environment.

### 42.1. Không gộp status thành một màu

RPO đạt và RTO không đạt là hai kết quả khác nhau. Ghi rõ metric nào fail và owner của corrective action.

### 42.2. Đặt ưu tiên sửa

Ưu tiên theo:
- Business impact.
- Khoảng cách so với target.
- Xác suất scenario.
- Khả năng cải thiện.
- Chi phí và risk của thay đổi.

## 43. Template báo cáo drill

```text
DRILL REPORT
============

Drill ID:
Date:
Service / Database:
Scenario:
PostgreSQL version:
Runbook revision:
Backup ID:
Timeline:
Recovery target:

OBJECTIVES
----------
RPO target:
RTO target:
Validation criteria:

OBSERVED DATA
-------------
Incident start UTC:
Last acknowledged transaction marker:
Last recovered transaction marker:
Actual RPO:
Service restored UTC:
Actual RTO:

TIMING
------
Detection:
Decision:
Fencing:
Provision:
Backup transfer:
Restore:
WAL replay:
Validation:
Cutover:
Observation:

RESULTS
-------
Backup manifest:
WAL continuity:
Database checks:
Application checks:
Business invariants:
Replication/archive reconfigured:

GAPS
----
RPO gap:
RTO gap:
Technical blockers:
Process blockers:

ACTIONS
-------
Action:
Owner:
Due date:
Verification drill:
Runbook revision:
Next test:
```

## 44. Template cập nhật runbook

Một thay đổi runbook nên ghi:

| Trường | Nội dung |
|---|---|
| Revision | Phiên bản tài liệu |
| Changed at | Thời điểm cập nhật |
| Reason | Drill/incident/change nào dẫn tới sửa |
| Scenario | Failure scenario được cập nhật |
| Previous behavior | Kết quả/giới hạn cũ |
| New procedure | Bước hoặc command mới |
| Preconditions | Version, role, storage, network |
| Expected result | Điều kiện hoàn thành |
| Stop condition | Khi nào phải dừng/escalate |
| Verification | Query, logs, application checks |
| Owner | Người chịu trách nhiệm |
| Reviewer | Người review |
| Drill evidence | Link tới kết quả test |
| Next review | Ngày kiểm tra tiếp theo |

Không ghi secret, password hoặc private key vào runbook.

## 45. Bài tập thực hành có đáp án

### Bài 1. RPO là gì?

**Đáp án:** Lượng dữ liệu tối đa tổ chức chấp nhận mất trong failure scenario đã định nghĩa, thường đo bằng thời gian hoặc transaction count.

### Bài 2. RTO là gì?

**Đáp án:** Thời gian tối đa chấp nhận để khôi phục dịch vụ về trạng thái sử dụng được.

### Bài 3. Backup chạy mỗi 24 giờ có nghĩa RPO luôn là 24 giờ?

**Đáp án:** Không. Nếu WAL archive liên tục và đầy đủ, recovery point có thể gần failure time hơn base backup.

### Bài 4. archive_timeout = 5 phút có bảo đảm RPO 5 phút?

**Đáp án:** Không. Còn phụ thuộc segment switch, archive success, durability và WAL continuity.

### Bài 5. RTO có phải thời gian chạy pg_basebackup?

**Đáp án:** Không. RTO gồm detection, decision, provision, restore/replay, validation và cutover.

### Bài 6. Công thức actual RPO theo timestamp?

**Đáp án:** T_failure trừ T_last_recoverable_commit, theo định nghĩa mốc đã thống nhất.

### Bài 7. Công thức actual RTO?

**Đáp án:** T_service_restored trừ T_start.

### Bài 8. Khi nào dịch vụ được coi là restored?

**Đáp án:** Khi database và ứng dụng đạt tiêu chí đọc/ghi, validation và routing đã thống nhất.

### Bài 9. Vì sao cần external transaction witness?

**Đáp án:** Để biết những commit nào đã được xác nhận trước sự cố và so sánh với marker còn lại sau recovery.

### Bài 10. Có nên ghi witness trước COMMIT?

**Đáp án:** Không. Chỉ ghi sau khi database xác nhận commit thành công.

### Bài 11. Marker mỗi 30 phút có phù hợp kiểm tra RPO 5 phút?

**Đáp án:** Không. Cadence quá thưa, không đủ độ phân giải.

### Bài 12. Vì sao phải đồng bộ clock?

**Đáp án:** Để so sánh timestamp giữa primary, standby, witness và test agent chính xác hơn.

### Bài 13. Nên dùng monotonic clock để làm gì?

**Đáp án:** Đo elapsed duration không bị ảnh hưởng bởi thay đổi wall clock.

### Bài 14. RPO của failover đo bằng gì tốt hơn một lag interval?

**Đáp án:** So sánh acknowledged transaction markers trên primary cũ với markers có trên standby promoted.

### Bài 15. replay_lag là actual RPO?

**Đáp án:** Không. Nó là một lag metric, không trực tiếp cho biết acknowledged commits bị mất khi promotion.

### Bài 16. pg_stat_replication cung cấp những LSN nào?

**Đáp án:** sent_lsn, write_lsn, flush_lsn và replay_lsn cùng các trạng thái liên quan.

### Bài 17. Byte lag có trực tiếp bằng thời gian lag?

**Đáp án:** Không. Cần biết WAL generation rate và workload.

### Bài 18. Synchronous replication có thể giảm RPO không?

**Đáp án:** Có, khi commit acknowledgment chờ standby đạt durability level phù hợp và promotion chọn đúng standby trong failure model.

### Bài 19. remote_write và on có giống nhau?

**Đáp án:** Không. remote_write chờ standby ghi WAL tới OS; on với synchronous replication chờ flush WAL bền vững theo semantics PostgreSQL.

### Bài 20. RPO = 0 có áp dụng mọi loại thảm họa?

**Đáp án:** Không. Chỉ cam kết trong failure model và durability assumptions đã xác định.

### Bài 21. Failover drill có chứng minh PITR hoạt động?

**Đáp án:** Không. PITR cần restore base backup và replay WAL tới target; phải test riêng.

### Bài 22. PITR có phù hợp khi standby đã nhận transaction xóa nhầm?

**Đáp án:** Thường có. Restore tới target trước transaction phá hoại.

### Bài 23. Tại sao phải fence old primary?

**Đáp án:** Ngăn old primary tiếp tục nhận writes sau promotion, tránh split-brain.

### Bài 24. Database start được có nghĩa RTO kết thúc?

**Đáp án:** Không. Ứng dụng phải đạt tiêu chí read/write và validation.

### Bài 25. Một restore drill cần dùng backup nào?

**Đáp án:** Backup thật trong repository và WAL archive production theo quy trình, trên môi trường cô lập.

### Bài 26. pg_verifybackup có thay restore drill?

**Đáp án:** Không. Nó kiểm tra manifest/checksums, không chứng minh end-to-end recovery và application.

### Bài 27. Vì sao cần test offsite backup?

**Đáp án:** Để chứng minh khả năng phục hồi khi mất failure domain chính.

### Bài 28. RPO trong logical corruption nên chọn target thế nào?

**Đáp án:** Xác định transaction/thời điểm corruption và phục hồi tới điểm last known-good trước nó; tính legitimate writes sau target cần reconciliation.

### Bài 29. Vì sao PITR không rollback external payment?

**Đáp án:** WAL chỉ phục hồi PostgreSQL; side effects ở hệ thống ngoài database cần reconciliation riêng.

### Bài 30. RTO gồm những giai đoạn nào?

**Đáp án:** Detection, decision, fencing, provisioning, restore, WAL replay, validation, cutover và service observation theo định nghĩa tổ chức.

### Bài 31. Vì sao cần đo P95 RTO?

**Đáp án:** Average có thể che các lần restore chậm; percentile giúp hiểu tail behavior khi đủ sample.

### Bài 32. Có nên gộp RPO và RTO thành một status?

**Đáp án:** Không. Một metric có thể đạt trong khi metric kia không đạt.

### Bài 33. Base backup cadence ảnh hưởng RPO hay RTO?

**Đáp án:** Chủ yếu ảnh hưởng lượng WAL phải replay và RTO; RPO còn phụ thuộc WAL archive/replication continuity.

### Bài 34. Archive mới nhất thành công có chứng minh WAL liên tục?

**Đáp án:** Không. Có thể thiếu segment ở giữa; cần kiểm tra inventory và restore.

### Bài 35. Timeline history file có vai trò gì?

**Đáp án:** Mô tả quan hệ giữa timeline branches để recovery chọn đúng nhánh WAL.

### Bài 36. Một RTO 60 phút cần owner nào?

**Đáp án:** DBA, infrastructure, application, security, network và business decision owners tùy service.

### Bài 37. Runbook có nên chứa password?

**Đáp án:** Không. Chỉ ghi secret retrieval path và role cần dùng.

### Bài 38. Sau mỗi drill cần cập nhật gì?

**Đáp án:** Actual RPO/RTO, evidence, bottleneck, commands, preconditions, validation, ownership, corrective actions và revision.

### Bài 39. Khi nào cần chạy drill lại?

**Đáp án:** Theo cadence/risk và sau thay đổi lớn về version, storage, topology, backup tooling, keys hoặc application dependencies.

### Bài 40. Warm standby giúp gì?

**Đáp án:** Có thể giảm RTO vì data đã được restore/replay sẵn; đổi lại chi phí và yêu cầu failover/fencing.

### Bài 41. RTO có thể được cải thiện bằng base backup thường xuyên hơn?

**Đáp án:** Có thể giảm lượng WAL replay, nhưng cần đo tổng transfer/restore cost và backup load.

### Bài 42. Nếu RPO không đạt nhưng RTO đạt, cần ưu tiên gì?

**Đáp án:** Điều tra archive/replication durability, WAL continuity và promotion selection; không chỉ tối ưu tốc độ restore.

### Bài 43. Nếu RPO đạt nhưng RTO không đạt?

**Đáp án:** Phân tích critical path: provision, transfer, restore, replay, validation, cutover; tối ưu bottleneck lớn nhất.

### Bài 44. Tại sao phải test keys trong clean-room DR?

**Đáp án:** Backup mã hóa nhưng không lấy được key thì không thể restore.

### Bài 45. Chỉ test database row counts đã đủ?

**Đáp án:** Không. Cần constraints, sequences, application smoke tests và business invariants.

### Bài 46. Marker cuối cùng có thể đại diện mọi transaction business?

**Đáp án:** Không hoàn toàn. Marker đo recovery path; cần external ledger và data validation cho các luồng nghiệp vụ quan trọng.

### Bài 47. RPO/RTO có phải con số cố định mãi mãi?

**Đáp án:** Không. Dataset size, WAL rate, topology, storage và dependencies thay đổi nên phải đo lại.

### Bài 48. Một lần diễn tập bị dừng do storage vượt guardrail có phải thất bại vô ích?

**Đáp án:** Không. Đó là evidence về capacity/operational risk; ghi lại điều kiện dừng và corrective action.

### Bài 49. Tại sao phải ghi runbook revision trong drill report?

**Đáp án:** Để biết procedure nào đã được thử và xác nhận phiên bản hiện tại có được kiểm chứng hay chưa.

### Bài 50. Điều kiện để tuyên bố đạt RPO/RTO?

**Đáp án:** Có mục tiêu/scenario rõ, phép đo đáng tin, restore/failover được kiểm chứng, actual values nằm trong ngưỡng và evidence được lưu lại.

## 46. Checklist đo RPO/RTO và cập nhật quy trình

| Giai đoạn | Việc cần xác nhận |
|---|---|
| Trước drill | Scenario, scope và failure model rõ ràng |
| Trước drill | RPO/RTO target và start/end definitions được thống nhất |
| Trước drill | Backup ID, WAL range, timeline và keys có sẵn |
| Trước drill | External witness/transaction markers hoạt động |
| Trước drill | Clock synchronization và UTC logging |
| Trước drill | Environment cô lập, không route production |
| Trong drill | Detection/decision/provision timestamps được ghi |
| Trong drill | Restore/replay/failover progress được ghi |
| Trong drill | Old primary được fence nếu promote |
| Trong drill | Guardrails và stop conditions được theo dõi |
| Sau drill | Last acknowledged/recovered marker được so sánh |
| Sau drill | Actual RPO được tính theo định nghĩa |
| Sau drill | Service-ready timestamp được xác nhận |
| Sau drill | Actual RTO được tính theo định nghĩa |
| Sau drill | Data/business/application checks hoàn tất |
| Sau drill | RPO và RTO được đánh giá riêng |
| Sau drill | Bottlenecks và assumptions được ghi |
| Sau drill | Corrective action có owner/deadline |
| Sau drill | Runbook revision được cập nhật |
| Sau drill | Ngày drill tiếp theo được đặt |

## 47. Tài liệu PostgreSQL chính thức

- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html) — base backup, WAL archive và PITR.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — tạo physical base backup.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html) — kiểm tra backup manifest.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — replication, archiver, activity và progress views.
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION) — WAL streaming và standby.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) — durability/acknowledgment semantics.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — WAL settings và archive timeout.
- [Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET) — recovery targets và PITR.
- [pg_stat_replication](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW) — sender/standby LSN positions.
- [pg_stat_archiver](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ARCHIVER-VIEW) — archive success/failure statistics.
- [pg_create_restore_point](https://www.postgresql.org/docs/current/functions-admin.html) — tạo named restore point.

Các views, fields, recovery options và replication semantics có thể thay đổi theo PostgreSQL major version. Khi triển khai runbook, xác minh server_version, pg_settings và tài liệu đúng phiên bản đang chạy.

## 48. Tổng kết: đo, diễn tập, cập nhật và đo lại

```text
Đặt business objectives
       |
       v
Định nghĩa scenario + RPO/RTO
       |
       v
Chuẩn bị backup, WAL, standby, keys
       |
       v
Chạy restore/failover drill
       |
       v
Đo acknowledged data vs recovered data
       |
       v
Đo thời gian tới service-ready
       |
       v
Kiểm tra dữ liệu và ứng dụng
       |
       v
So sánh actual với target
       |
       v
Sửa kiến trúc / capacity / runbook
       |
       v
Diễn tập lại
```

Những nguyên tắc cần nhớ:

1. **RPO đo lượng dữ liệu có thể mất; RTO đo thời gian dịch vụ gián đoạn.** Hai mục tiêu phải được định nghĩa riêng.
2. **Actual RPO cần so sánh acknowledged commits với dữ liệu đã phục hồi.** Lag metric đơn lẻ không đủ.
3. **Actual RTO phải kết thúc khi dịch vụ đạt tiêu chí sử dụng được.** Database start chỉ là một giai đoạn.
4. **Mỗi failure scenario có recovery path khác nhau.** Failover, PITR, regional DR và logical corruption phải được test riêng.
5. **Transaction marker cần external witness bền vững.** Ghi witness sau COMMIT và dùng clock được đồng bộ.
6. **Base backup cadence chủ yếu ảnh hưởng restore/replay time.** WAL continuity quyết định khả năng PITR tới các thời điểm giữa các backup.
7. **Synchronous replication chỉ bảo vệ theo failure model và acknowledgment semantics.** Không tự động bảo đảm RPO = 0 trong mọi thảm họa.
8. **Restore drill phải dùng backup/archive thật.** Verify manifest không thay thế end-to-end restore.
9. **Validation gồm database, application và business invariants.** Không chỉ kiểm tra process đã start.
10. **RTO cần đo theo critical path.** Provision, transfer, replay, validation và cutover đều có thể là bottleneck.
11. **Runbook phải có version, owner và evidence.** Mỗi drill cần dẫn tới corrective actions cụ thể.
12. **Kiến trúc thay đổi thì mục tiêu phải được đo lại.** Dataset, WAL rate, storage, topology và dependencies đều ảnh hưởng kết quả.

**Một câu để nhớ:** *RPO/RTO chỉ có ý nghĩa khi được đo trên một failure scenario rõ ràng, bằng dữ liệu và mốc thời gian có thể kiểm chứng; mỗi lần diễn tập phải tạo ra bằng chứng và một quy trình khôi phục tốt hơn.*

