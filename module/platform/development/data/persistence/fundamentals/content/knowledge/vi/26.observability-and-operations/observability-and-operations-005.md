# Đo độ trễ nhân bản và tình trạng sao lưu

Một database PostgreSQL có thể đang trả lời truy vấn bình thường, các standby đều ở trạng thái **streaming**, nhưng hệ thống vẫn đối mặt với nguy cơ mất dữ liệu. Replica có thể nhận WAL chậm, chưa **replay** những transaction mới; bản sao lưu gần nhất có thể đã cũ, thiếu WAL để khôi phục tới mốc cần thiết, hoặc chưa từng được thử restore. Ngược lại, một standby tạm thời có độ trễ cao không đồng nghĩa bản backup đang hỏng.

Trong tầng persistence Java, **quan sát và vận hành** cần tách hai câu hỏi:

1. **Replication lag:** dữ liệu đã được primary xác nhận đang đến các replica nhanh và đầy đủ đến mức nào? Có thể đọc từ replica với độ mới yêu cầu không? Khi failover, có rủi ro mất những transaction nào?
2. **Backup health:** hiện có **điểm phục hồi độc lập và sử dụng được** hay không? Backup mới nhất được tạo khi nào, WAL archive có liên tục không, có kiểm tra tính toàn vẹn và **thử phục hồi** không?

Bài học thuộc chương **Quan sát và vận hành** trong mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Trọng tâm là các phép đo, truy vấn PostgreSQL, chỉ báo cảnh báo, kiểm tra sao lưu và runbook sự cố phục vụ ứng dụng Java. Nội dung liên hệ với giao dịch, tính bền vững, ranh giới persistence, xử lý lỗi kết nối, bảo mật và hiệu năng. SQL minh họa theo PostgreSQL với **physical streaming replication**, trừ khi có ghi rõ trường hợp khác; tính năng và cột giám sát có thể khác theo phiên bản DBMS.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **WAL generation**, **send**, **write**, **flush** và **replay** trên standby.
2. Đo **độ trễ nhân bản theo byte/LSN**, khoảng thời gian báo cáo lag và độ mới dữ liệu trên standby.
3. Giải thích vì sao **write_lag/flush_lag/replay_lag**, **last replay timestamp** hoặc **trạng thái streaming** không tự nói lên toàn bộ RPO.
4. Kiểm tra primary và standby bằng **pg_stat_replication**, **pg_stat_wal_receiver**, **pg_replication_slots** và thông tin recovery.
5. Phân biệt **backup job success**, **base backup**, **WAL archiving**, **PITR** và **restore verification**.
6. Dùng **pg_stat_archiver**, lịch sử backup job, backup manifest, danh sách WAL và diễn tập restore để đánh giá khả năng phục hồi.
7. Đặt dashboard, SLI/SLO, cảnh báo và runbook theo mức rủi ro dữ liệu thực, không dựa trên một ngưỡng tùy ý.
8. Thiết kế phép đo từ Java/JDBC không tạo thêm tải nguy hiểm, rò credential hay làm chậm API nghiệp vụ.
9. Giải thích mối quan hệ giữa replication lag, **RPO**, **RTO**, failover và hành vi read-your-writes.

## 2. Từ vựng và ranh giới cần phân biệt

| Khái niệm | Ý nghĩa | Điều không được suy ra |
|---|---|---|
| **WAL (Write-Ahead Log)** | Nhật ký thay đổi phục vụ crash recovery và replication của PostgreSQL | Không phải bản sao lưu độc lập, không thay thế base backup |
| **Primary** | Node nhận ghi theo kiến trúc replication đang dùng | Mọi replica đã nhận/applied toàn bộ COMMIT của primary |
| **Standby/replica** | Node nhận và phát lại WAL để có bản sao dữ liệu | Mọi SELECT trên standby đều thấy dữ liệu mới nhất |
| **LSN (Log Sequence Number)** | Vị trí trong luồng WAL, thường hiển thị dạng HEX/HEX | Timestamp hoặc số transaction trực tiếp |
| **Receive lag** | Mức WAL còn chưa đến standby theo một mốc đo | Đồng nghĩa với replay lag |
| **Write/flush/replay progress** | Mốc standby đã ghi, flush bền vững hoặc áp dụng WAL | Ba mốc có thể dùng thay thế cho nhau |
| **Backup freshness** | Thời gian từ mốc backup được xác nhận tới hiện tại | Backup đó khôi phục được |
| **Archive freshness/continuity** | WAL cần cho PITR có được lưu liên tục và truy xuất được | Một counter archive tăng là mọi WAL đều an toàn |
| **RPO** | Mức mất dữ liệu tối đa có thể chấp nhận, đo theo thời gian hoặc lượng dữ liệu | Luôn bằng giá trị replay_lag đang thấy |
| **RTO** | Thời gian tối đa chấp nhận để khôi phục dịch vụ | Bằng thời gian thực thi một lệnh restore lý thuyết |

**Replication là cơ chế tạo bản sao và duy trì đồng bộ theo thiết kế; backup là khả năng phục hồi từ một bản lưu được quản lý riêng**. Replica thường xuyên phản ánh cả các thay đổi hợp lệ **lẫn thao tác xóa nhầm đã commit**; vì vậy replica không tự thay thế backup có retention và điểm phục hồi.

### 2.1. Vì sao không gộp thành một đèn “DB healthy”?

Một hệ thống có thể đồng thời ở các trạng thái:

- API ghi trên primary vẫn ổn.
- Standby A nhận WAL bình thường nhưng **replay chậm** vì tài nguyên hoặc xung đột với truy vấn đọc.
- Standby B đã ngắt kết nối, không xuất hiện trong danh sách replica đang kết nối.
- Base backup cuối cách đây 18 giờ, tuy nhiên một số WAL archive gần đây thất bại.
- Backup job gần nhất báo **SUCCESS** nhưng chưa ai thử phục hồi trên môi trường độc lập.

Đánh giá an toàn cần **nhiều bằng chứng tương quan**, không chỉ tình trạng một TCP connection hay một job thành công.

## 3. Dòng dữ liệu của physical streaming replication

Một transaction ghi vào PostgreSQL primary tạo các WAL records phù hợp. Standby có thể nhận WAL qua streaming hoặc khôi phục WAL từ archive theo cấu hình, sau đó **replay** WAL để phản ánh thay đổi ở bản sao.

~~~text
Ứng dụng Java / JDBC
         |
         | INSERT/UPDATE/COMMIT
         v
   PostgreSQL Primary
         |
         +-- WAL generated/current LSN
         |
         +-- WAL sender -----------------------+
                                              |
                                      Network/WAL stream
                                              |
                                              v
                                    Standby WAL receiver
                                              |
                                      received / written
                                              |
                                         WAL flushed
                                              |
                                        WAL replayed
                                              |
                                      SELECT trên standby
~~~

Các mốc tiến độ có ý nghĩa khác nhau:

1. **Primary current WAL position:** mốc WAL sinh ra tại primary theo hàm lấy mẫu.
2. **sent_lsn:** primary đã gửi tới đâu cho standby theo tiến trình WAL sender.
3. **write_lsn:** standby báo đã ghi WAL tới đâu trong hệ thống nhận.
4. **flush_lsn:** standby báo đã flush WAL tới đâu.
5. **replay_lsn:** standby báo đã phát lại WAL tới đâu, liên quan tới trạng thái mà các truy vấn trên standby có thể nhìn thấy.

Mốc **receive** và **replay** có thể cách nhau xa: mạng truyền nhanh không có nghĩa node đọc đã áp dụng thay đổi nhanh. Ngược lại, một replica apply WAL nhanh nhưng mạng đứt vẫn ngày càng lạc hậu so với primary.

### 3.1. Physical replica và logical replica không giống nhau

Với physical streaming replication, các chỉ số như **sent_lsn**, **write_lsn**, **flush_lsn**, **replay_lsn** của WAL sender là cơ sở quan sát. Trong logical replication, **publication/subscription**, logical replication slots và apply workers có cơ chế, view và định nghĩa tiến độ riêng.

Các công thức chênh lệch LSN trong bài có mục đích minh họa **physical standby**. Không được tự áp dụng chúng cho mọi hệ thống CDC, logical subscriber hoặc broker offset nếu không hiểu mô hình.

### 3.2. Replica đã chạy không đồng nghĩa đã bắt kịp

Một standby có thể trả lời:

~~~sql
SELECT pg_is_in_recovery();
~~~

Giá trị **true** cho biết instance đang ở chế độ recovery/standby. Nó **không chứng minh** standby đang kết nối streaming, không xác nhận đã áp dụng transaction mới nhất và không nói gì về backup. Cần thêm quan sát tiến độ, kết nối và trạng thái cluster.

## 4. Đo replication lag từ phía primary

Trong PostgreSQL physical streaming replication, view **pg_stat_replication** trên primary mô tả những tiến trình WAL sender đang hoạt động cùng các mốc và báo cáo từ standby.

### 4.1. Truy vấn tổng quan

~~~sql
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
FROM pg_stat_replication
ORDER BY application_name;
~~~

- **application_name:** định danh kết nối/standby theo cấu hình; cần đặt tên rõ và không tiết lộ dữ liệu nhạy cảm.
- **state:** trạng thái WAL sender, ví dụ streaming.
- **sync_state:** vai trò đồng bộ theo cấu hình, có thể là async, sync, potential hoặc quorum trong ngữ cảnh phù hợp.
- **LSN fields:** mốc đã gửi, ghi, flush, replay.
- **write_lag/flush_lag/replay_lag:** khoảng thời gian được primary báo cho các công đoạn xác nhận; không phải đồng hồ đếm thời gian chắc chắn mọi dữ liệu đã chậm bấy nhiêu.

**View chỉ liệt kê các WAL sender đang tồn tại.** Nếu standby B bị mất kết nối hoàn toàn, B có thể **biến mất khỏi view**; truy vấn trả về một hàng “healthy” cho standby A không chứng minh toàn bộ các replica dự kiến đều khỏe. Dashboard cần biết **danh sách replica phải có** từ cấu hình điều phối/service discovery và cảnh báo khi thiếu.

### 4.2. Đo chênh lệch LSN tính theo byte

Hàm **pg_wal_lsn_diff(lsn1, lsn2)** tính chênh lệch WAL giữa hai LSN. Ví dụ trên **primary**:

~~~sql
SELECT
    application_name,
    state,
    pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)
        AS unsent_wal_bytes,
    pg_wal_lsn_diff(sent_lsn, write_lsn)
        AS in_transit_or_not_written_bytes,
    pg_wal_lsn_diff(write_lsn, flush_lsn)
        AS written_not_flushed_bytes,
    pg_wal_lsn_diff(flush_lsn, replay_lsn)
        AS flushed_not_replayed_bytes,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)
        AS total_replay_gap_bytes
FROM pg_stat_replication
ORDER BY application_name;
~~~

**Lưu ý quan trọng về tính diễn giải:**

- Chênh lệch LSN là **byte WAL**, không phải số byte dữ liệu chưa copy, số row hoặc số transaction.
- **pg_current_wal_lsn()** và thông tin trong view không nhất thiết là một snapshot tiến độ nguyên tử. Nhiều tiến trình cập nhật số liệu đồng thời; chênh lệch nhỏ có thể dao động, thậm chí dấu âm tạm thời trong một số phép lấy mẫu. Không dùng một lần đọc để ra quyết định failover.
- Nếu một LSN là **NULL**, phép tính tương ứng có thể NULL. **NULL là thiếu dữ liệu đo**, không phải zero lag.
- WAL sinh ra có thể tăng rất nhanh; **100 MB lag** không mang cùng ý nghĩa trên hệ ghi 1 MB/s và hệ ghi 1 GB/s.
- Một standby không còn WAL sender sẽ **không có dòng để đo**, nên phải có kiểm tra membership riêng.

Công thức phân rã giúp xác định nút thắt sơ bộ:

~~~text
Primary current LSN
    |
    +-- chưa gửi            [current - sent]
    +-- gửi nhưng chưa ghi [sent - write]
    +-- ghi chưa flush      [write - flush]
    +-- flush chưa replay   [flush - replay]
    |
    v
Standby replay LSN
~~~

Đây là mô hình chẩn đoán các mốc được báo cáo, **không xác định chắc nguyên nhân** chỉ từ một phép trừ. Network, disk, CPU, conflict/lock, tải truy vấn và cơ chế reporting đều ảnh hưởng.

### 4.3. Chỉ số lag theo thời gian không phải backlog có thể quy đổi chắc chắn

Ví dụ:

~~~sql
SELECT
    application_name,
    ROUND(
        EXTRACT(EPOCH FROM write_lag) * 1000
    ) AS write_lag_ms,
    ROUND(
        EXTRACT(EPOCH FROM flush_lag) * 1000
    ) AS flush_lag_ms,
    ROUND(
        EXTRACT(EPOCH FROM replay_lag) * 1000
    ) AS replay_lag_ms
FROM pg_stat_replication;
~~~

Các cột lag dạng interval phản ánh **thời gian gần đây được ghi nhận cho WAL tới các mốc**, phục vụ quan sát chi phí xác nhận và health. Chúng **không phải** phép đo chính xác “replica đang chậm bao nhiêu giây so với dữ liệu hiện tại” trong mọi tình huống; khi ít ghi hoặc idle chúng có thể bằng NULL.

Đừng tính RPO chắc chắn bằng cách lấy **replay_lag_ms** tại một thời điểm rồi tuyên bố sẽ mất đúng số mili giây đó khi failover.

### 4.4. Synchronous replication và synchronous_commit

PostgreSQL có những mức **synchronous_commit** như on, remote_write, remote_apply và các lựa chọn khác tùy cấu hình. Kết quả COMMIT có thể chờ local WAL flush, remote write/flush/apply theo cấu hình và replica đồng bộ sẵn có.

- **Đồng bộ** có thể giảm một số cửa sổ mất dữ liệu cho transaction được xác nhận, nhưng tăng latency và có thể ảnh hưởng availability khi standby bắt buộc mất liên lạc.
- **Bất đồng bộ** thường không chặn COMMIT chờ replica, nên nếu failover sang standby còn trễ, có thể thiếu transaction đã được primary xác nhận.
- **Synchronous standby** không có nghĩa mọi replica đều mới nhất hoặc việc đọc qua bất kỳ replica nào cũng nhất quán tuyệt đối.
- Cần xem **sync_state**, cấu hình synchronous_standby_names, failover procedure và mức commit thực tế.

Không đưa ra bảo đảm RPO = 0 cho toàn hệ thống chỉ từ nhãn “synchronous” khi chưa xác minh giao thức, topology, transaction mode, durability và lựa chọn node sau failover.

## 5. Đo trạng thái ngay trên standby

Việc quan sát trên primary giúp so sánh các LSN, còn trên standby giúp kiểm tra **WAL receiver** và **mốc đã replay cục bộ**, kể cả khi cần chẩn đoán một kết nối đang có vấn đề.

### 5.1. WAL receiver còn hoạt động không?

Trên standby:

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time,
    slot_name
FROM pg_stat_wal_receiver;
~~~

View **pg_stat_wal_receiver** cho thông tin WAL receiver hiện tại. Trong một số tình huống không có receiver đang chạy, view có thể không có dòng. Standby có thể vẫn ở recovery và replay WAL từ archive theo cấu hình, nên việc thiếu WAL receiver không tự động đồng nghĩa database đã mất khả năng phục hồi; cần xem **nguồn WAL đang dùng** và trạng thái cluster.

Tránh truy vấn/log **conninfo** không cần thiết vào hệ giám sát rộng quyền vì có thể chứa thông tin kết nối cần bảo vệ.

### 5.2. Nhận và replay LSN trên standby

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS received_not_replayed_bytes,
    pg_last_xact_replay_timestamp() AS last_replayed_xact_at;
~~~

Đây là truy vấn **trên standby**, không phải truy vấn để so sánh với mốc current LSN của primary trong cùng session.

- **pg_last_wal_receive_lsn()** trả mốc WAL cuối đã nhận qua streaming; trong trạng thái chỉ đọc archive hoặc chưa kết nối, cần diễn giải theo cơ chế nhận WAL thực tế.
- **pg_last_wal_replay_lsn()** cho biết mốc WAL đã replay trên standby.
- **Chênh lệch receive - replay** cho biết backlog áp dụng cục bộ theo các mốc đó; **không đo WAL primary chưa gửi tới**.
- **pg_last_xact_replay_timestamp()** là timestamp của transaction commit/abort gần nhất được replay theo cơ chế PostgreSQL, không phải timestamp “standby đang khỏe” hoặc độ trễ mạng.

### 5.3. Vì sao công thức now() - last replay timestamp dễ gây báo động giả?

Nhiều dashboard dùng:

~~~sql
SELECT
    now() - pg_last_xact_replay_timestamp()
        AS time_since_last_replayed_transaction;
~~~

Nếu primary **không có giao dịch mới trong 2 giờ**, standby có thể đã bắt kịp hoàn toàn nhưng timestamp transaction cuối vẫn từ 2 giờ trước. Giá trị trên vẫn lớn, **không phải chắc chắn replica đang trễ 2 giờ**.

Ngược lại, khi hệ có nhiều transaction và một số đang ghi, chỉ số có thể cho một tín hiệu tham khảo về độ mới, nhưng còn phụ thuộc clock giữa các node, loại transaction và cách dữ liệu được phát lại.

**Cách đọc đúng:** kết hợp timestamp này với primary WAL position, receive/replay LSN, tốc độ ghi WAL, replica membership và các phép đo chủ động nếu business cần giới hạn stale data bằng giây.

### 5.4. Health probe có chủ đích cho read freshness

Nếu một nghiệp vụ đòi **read-your-writes**, có thể tạo một **replication heartbeat row** được primary cập nhật định kỳ kèm số sequence/timestamp và đọc trên standby, hoặc dùng cơ chế token/LSN do nền tảng cung cấp.

Ví dụ ý tưởng:

~~~text
Monitor/primary:
    ghi heartbeat(sequence = 1024, committed_at = T1)
Standby:
    đọc sequence đang nhìn thấy
Monitor:
    đối chiếu với sequence mới nhất đã commit ở primary
    báo trạng thái nếu quá mốc cho phép
~~~

Một heartbeat thành công giúp đánh giá đường cập nhật → replay → đọc, nhưng cần phân biệt thời gian của đồng hồ khác nhau và lịch heartbeat. Đừng coi heartbeat trễ do chính job monitor bị dừng là bằng chứng database hỏng. Nó cũng không thay thế WAL lag metrics cho những hệ thống có nhiều shard/replica.

## 6. “Backup thành công” có nghĩa chính xác là gì?

**Backup** là một bản lưu được tạo theo quy trình có thể dùng làm điểm bắt đầu khôi phục. Nhưng phải phân biệt các mức kết luận:

| Cấp độ | Bằng chứng | Chưa chứng minh được |
|---|---|---|
| **Job đã chạy** | Scheduler đã kích hoạt tiến trình | Đã tạo file hoặc backup đã đủ dữ liệu |
| **Job báo thành công** | Exit code, manifest/result của công cụ | File không hỏng và có thể khôi phục |
| **Artifact tồn tại** | Kho lưu chứa các đối tượng mong đợi | Artifact không bị thiếu một phần hoặc hỏng |
| **Xác minh integrity** | Kiểm manifest, checksum, kích thước, WAL cần thiết | Database thực sự khởi động/khôi phục được |
| **Restore test thành công** | Khởi động DB độc lập từ backup và WAL, kiểm tra truy vấn | Mọi tình huống production đều được phục hồi trong RTO |
| **Restore drill đạt RPO/RTO** | Đo được mốc phục hồi và thời gian khôi phục end-to-end | Tương lai không thể xảy ra sự cố khác; vẫn cần giám sát liên tục |

**Một job kết thúc với exit code 0 không phải bằng chứng đầy đủ về khả năng khôi phục.** Cần kiểm tra artifact, điều kiện WAL, và quan trọng nhất là thực hiện restore có kiểm soát trên hệ thống độc lập.

### 6.1. Các kiểu backup chính

| Loại | Nội dung/ứng dụng | Điểm cần chú ý |
|---|---|---|
| **Physical base backup** | Bản sao nhất quán của database cluster PostgreSQL tại một giai đoạn, có yêu cầu WAL để khôi phục | Kết hợp WAL để phục hồi và PITR; phiên bản/kiến trúc lưu trữ có ràng buộc |
| **Continuous WAL archiving** | Lưu các đoạn WAL cần thiết ngoài primary | Phải liên tục, đầy đủ và tồn tại từ mốc base backup tới target recovery |
| **Logical backup (pg_dump)** | Dump một database, schema/objects/dữ liệu logic theo phạm vi lệnh | Không phải bản thay thế trực tiếp cho physical PITR; globals/roles cần xử lý riêng |
| **Snapshot storage** | Snapshot volume/disk theo cơ chế nền tảng | Cần bảo đảm consistency trên các volume và WAL, có quy trình restore được hỗ trợ |
| **Backup bằng công cụ chuyên biệt** | Quản lý full/incremental, retention, compression, encryption, repository | Hành vi verify/restore và tính nhất quán phụ thuộc công cụ/version |

**Replica không phải backup theo nghĩa đủ để phục hồi nhiều kiểu sự cố.** Lệnh DELETE nhầm được commit có thể được replay lên replica, và tham nhũng logic cũng có thể lan. Backup cần mốc thời gian, cách ly quyền và retention thích hợp.

### 6.2. Base backup và WAL archive bổ sung nhau

~~~text
   Base backup B0
       |
       +-- WAL segment 1
       +-- WAL segment 2
       +-- WAL segment 3
       +-- WAL segment 4 -> target recovery time
       |
       v
  Restore B0 + replay đủ WAL tới target
~~~

Để thực hiện **point-in-time recovery (PITR)**, phải có một base backup hợp lệ và chuỗi WAL cần thiết từ mốc backup đó tới mục tiêu khôi phục; nếu thiếu một đoạn bắt buộc, khả năng tới đúng target có thể bị mất.

Một base backup được xác minh integrity **không chứng minh PITR tới hiện tại** khi WAL archive gần đây bị gián đoạn.

### 6.3. WAL lưu tại primary không phải archive độc lập

Nếu WAL chỉ tồn tại trong thư mục **pg_wal** của primary, khi mất toàn bộ máy/volume, các WAL cần cho PITR có thể mất theo. WAL archive nên được bảo vệ ở miền lỗi độc lập theo mục tiêu phục hồi của tổ chức, kèm kiểm soát quyền và mã hóa phù hợp.

Một replication slot có thể khiến WAL được giữ lại ở primary cho standby/consumer, nhưng **slot không thay thế WAL archive hay backup repository**.

## 7. Quan sát WAL archiving bằng PostgreSQL

### 7.1. Xác định cơ chế archiving đã bật

Một số cấu hình cần kiểm tra theo hạ tầng được triển khai:

~~~sql
SELECT name, setting
FROM pg_settings
WHERE name IN (
    'archive_mode',
    'wal_level',
    'archive_timeout'
)
ORDER BY name;
~~~

**archive_mode = on** cho biết chế độ archive được bật theo cơ chế cấu hình PostgreSQL, nhưng không xác nhận từng segment đã được chuyển đến kho lưu độc lập thành công.

Tránh đưa trực tiếp giá trị **archive_command** vào dashboard/log rộng quyền: tùy triển khai, câu lệnh hoặc script được cấu hình có thể bộc lộ thông tin endpoint hay secret. Hãy ghi nhận trạng thái từ công cụ archive, không xuất cấu hình nhạy cảm cho người xem không cần thiết.

### 7.2. pg_stat_archiver

Trên PostgreSQL primary có sử dụng WAL archiving theo cơ chế này:

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

**Cách diễn giải:**

- **archived_count:** số segment được PostgreSQL ghi nhận archive thành công kể từ lần reset thống kê tương ứng.
- **last_archived_wal/last_archived_time:** đoạn WAL và thời điểm được ghi nhận gần nhất.
- **failed_count/last_failed_wal/last_failed_time:** số và thời điểm lỗi được ghi nhận theo logic của archiver; không được giả định mọi lỗi ngoài công cụ đều hiện lên ở đây.
- **stats_reset:** mốc giúp phân biệt counter bắt đầu lại do reset thay vì thay đổi thật.

**Không đọc last_archived_time cũ như một dấu hiệu lỗi chắc chắn nếu database không sinh đủ WAL để có đoạn archive mới.** WAL segment thường được đưa đi archive theo cơ chế segment completion/switch và các cấu hình liên quan. Mức WAL không đổi hoặc rất ít ghi có thể khiến timestamp lâu không thay đổi mà khả năng archive vẫn bình thường.

Ngược lại, **archived_count tăng** cũng không tự chứng minh object đã được lưu đủ lâu, không bị xóa bởi retention lỗi, không bị hỏng hoặc có thể giải mã/restore.

### 7.3. Tính tốc độ archiving phải dùng chênh lệch counter

Nếu archived_count từ 10.000 tăng lên 10.120 trong 10 phút, có thể suy ra đã ghi nhận 120 segment archive thành công trong khoảng đó, **miễn counter không reset trong lúc đo**. Không được dùng giá trị archived_count tuyệt đối như “120 WAL/giây”.

Giả sử **failed_count** tăng, cần xem log archive job, đích object store, quyền, network, quota và trạng thái **archive_command/archive_library** theo deployment. Dữ liệu thống kê và log bổ sung cho nhau.

### 7.4. Độ mới của WAL archive không hoàn toàn là độ mới của bản backup

Một hệ có base backup đã cũ nhưng WAL archive mới liên tục có thể vẫn hỗ trợ PITR từ base backup đó, nếu retention/đầy đủ WAL hợp lệ. Một hệ có base backup rất mới nhưng thiếu WAL cần thiết có thể **không khôi phục được** đến một số mốc.

**Độ mới của base backup**, **tính liên tục của WAL** và **điểm restore đã thử thành công** phải là ba phần thông tin riêng.

## 8. Replication slot và nguy cơ giữ WAL quá lâu

Một physical replication slot có thể giữ WAL cần cho một standby chưa nhận kịp. Điều này tránh việc primary xóa WAL quá sớm trong phạm vi cấu hình, nhưng nếu standby ngừng lâu, lượng WAL giữ lại có thể tăng đáng kể.

### 8.1. Kiểm tra slot

Trên primary:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    CASE
        WHEN restart_lsn IS NOT NULL
        THEN pg_wal_lsn_diff(
            pg_current_wal_lsn(), restart_lsn)
        ELSE NULL
    END AS retained_wal_bytes
FROM pg_replication_slots
ORDER BY slot_name;
~~~

- **active = false:** slot hiện không có consumer sử dụng tại mốc quan sát; cần kiểm tra đây là downtime mong đợi hay consumer bị mất.
- **restart_lsn:** vị trí WAL cũ nhất còn cần giữ theo slot.
- **retained_wal_bytes:** ước lượng khoảng cách LSN, **không phải số byte vật lý chính xác đang nằm trong pg_wal**.
- Với logical replication slots, còn có metadata như **confirmed_flush_lsn**; không dùng công thức của physical replay như thể chúng cùng semantics.

Khi slot giữ nhiều WAL, primary có thể cạn disk. Một số phiên bản PostgreSQL có cấu hình và trạng thái như **max_slot_wal_keep_size**, **wal_status** và **safe_wal_size** để quan sát nguy cơ mất WAL cần thiết; hãy đọc theo phiên bản đang dùng.

**Không tự xóa replication slot đang có consumer** chỉ để giải phóng disk. Làm vậy có thể khiến standby/CDC consumer cần rebuild/reinitialize hoặc mất khả năng bắt kịp theo cơ chế hiện tại. Phải xác minh chủ sở hữu slot và phương án khôi phục.

### 8.2. Phân biệt hai tình huống

**Replica replay chậm nhưng đã nhận WAL:** receiver tiến lên, replay_lsn chậm, áp lực apply/recovery hoặc xung đột đọc có thể đáng nghi.

**Replica ngắt kết nối, slot giữ WAL:** WAL không đến standby, restart_lsn cũ, retained WAL tăng; cần điều tra network, kết nối, standby health và dung lượng primary.

Một dashboard chỉ hiển thị replay lag bytes không đủ cho nguy cơ **primary đầy disk vì replication slot**.

## 9. Đánh giá trạng thái base backup job

PostgreSQL có view cho biết tiến độ của base backup **đang thực hiện**, nhưng không cung cấp sẵn một sổ lịch sử đầy đủ cho mọi backup job từ mọi công cụ.

### 9.1. Base backup đang chạy

Trên các phiên bản có view **pg_stat_progress_basebackup**:

~~~sql
SELECT
    pid,
    phase,
    backup_total,
    backup_streamed,
    tablespaces_total,
    tablespaces_streamed
FROM pg_stat_progress_basebackup;
~~~

View này cung cấp tiến độ cho những tiến trình base backup hiện tại. Nếu không có dòng, có thể **không có base backup đang chạy**; không có nghĩa backup định kỳ đã thất bại. Nếu có dòng, nó cũng không chứng minh backup sau đó sẽ hoàn tất hoặc restore được.

### 9.2. Công cụ/job phải lưu metadata lịch sử

Nên duy trì một **backup inventory** ngoài DB cần được bảo vệ, với các thông tin:

| Thuộc tính | Ý nghĩa |
|---|---|
| **backup_id** | ID duy nhất và có thể đối chiếu artifact |
| **database_cluster_id** | Đúng cluster/instance nguồn |
| **backup_type** | Physical full/incremental hoặc logical |
| **started_at/completed_at** | Thời gian bắt đầu và kết thúc theo UTC |
| **job_status** | Running, success, failed, cancelled |
| **artifact_location** | Kho lưu đã được kiểm soát quyền |
| **manifest/checksum status** | Đã xác minh byte/manifest chưa |
| **WAL range/restore chain** | Những WAL nào cần để phục hồi từ backup |
| **encryption/key status** | Có thể giải mã và ai có quyền truy cập |
| **last_restore_test_at** | Khi nào đã thử khôi phục |
| **last_restore_test_result** | Restore thành công và kiểm tra nghiệp vụ ra sao |
| **actual_restore_point** | Mốc dữ liệu đã thực sự phục hồi được trong test |
| **retention_expires_at** | Khi nào bản backup có thể bị xóa theo policy |

Một bản ghi **SUCCESS** chỉ có ý nghĩa nếu được ghi sau khi công cụ xác nhận artifact đã đóng/đồng bộ tới đích theo hợp đồng của nó. Cần kiểm tra trường hợp backup job bị kill giữa chừng hoặc file chỉ upload một phần, kể cả khi dashboard trước đó đã ghi “started”.

### 9.3. Mô hình kiểm tra ở ba tầng

~~~text
Scheduler / Backup controller
       |
       +--> Job có hoàn tất không?
       |
       v
Backup repository
       |
       +--> Artifact và WAL cần thiết còn đủ không?
       +--> Manifest/checksum có hợp lệ không?
       |
       v
Isolated restore environment
       |
       +--> PostgreSQL khởi động sau recovery không?
       +--> Chạy được truy vấn kiểm tra/invariant không?
       +--> Mất bao lâu, phục hồi tới mốc nào?
       |
       v
Kết luận backup có đáp ứng RPO/RTO mục tiêu?
~~~

Cấp kiểm tra sau thường cho bằng chứng mạnh hơn cấp trước. Không được chỉ kiểm tra file tồn tại rồi đánh dấu “RESTORE_VERIFIED”.

## 10. pg_basebackup, pg_verifybackup và giới hạn của kiểm manifest

Một ví dụ minh họa cách tạo **physical base backup** trên môi trường thực hành do bạn sở hữu:

~~~text
pg_basebackup \
  --host=<db-host> \
  --port=5432 \
  --username=<replication-user> \
  --pgdata=<empty-backup-directory> \
  --format=plain \
  --wal-method=stream \
  --progress
~~~

Đây là **lệnh minh họa cú pháp**, không phải lệnh được thực thi trong bài. Các chỗ đặt trong dấu góc phải được thay bằng giá trị thật; trên Windows, ký tự nối dòng và cách quote shell khác POSIX. Thực tế cần role có quyền phù hợp, network/TLS, vùng đĩa trống và cơ chế quản lý secret an toàn.

**--wal-method=stream** giúp lấy WAL cần thiết trong thời gian tạo base backup theo cơ chế của pg_basebackup; nó **không tự bảo đảm PITR tới mọi thời điểm sau khi backup hoàn tất**. Muốn phục hồi về sau, cần lưu chuỗi WAL theo chiến lược continuous archiving được kiểm soát.

### 10.1. Xác minh bằng pg_verifybackup

Với base backup định dạng/phạm vi được công cụ hỗ trợ và có manifest:

~~~text
pg_verifybackup <path-to-base-backup>
~~~

**pg_verifybackup** kiểm tra nội dung dựa trên manifest và một số kiểm tra WAL phù hợp với công cụ. Kết quả kiểm tra tốt giúp phát hiện file bị thiếu, khác checksum hoặc lỗi khác trong phạm vi hỗ trợ.

Nhưng nó **không thay thế việc boot PostgreSQL từ backup và chạy truy vấn**, cũng không chứng minh đầy đủ retention WAL tới target PITR tương lai. Cần dùng phiên bản/công cụ tương thích và đọc lỗi verify thay vì chỉ nhìn exit status của một shell script trung gian.

### 10.2. Logical backup với pg_dump

Một ví dụ logical backup:

~~~text
pg_dump \
  --dbname=<database-connection-string> \
  --format=custom \
  --file=<backup-archive.dump>
~~~

Với định dạng custom, có thể dùng **pg_restore --list** để xem nội dung archive, nhưng **xem được mục lục không chứng minh mọi đối tượng/record có thể restore đúng**. Kiểm thử cần tạo database riêng, dùng pg_restore, kiểm tra schema, quyền, dữ liệu và tính nhất quán nghiệp vụ.

**pg_dump không phải physical base backup cho PITR bằng WAL**, và dump một database không tự bao gồm toàn bộ các global objects như roles/tablespaces của toàn cluster. Nếu hệ thống yêu cầu, phải có kế hoạch backup/restore các thành phần cấu hình và global metadata tương ứng.

## 11. PITR và tính liên tục WAL

**Point-in-time recovery (PITR)** sử dụng base backup và WAL để tiến tới một mốc thời gian hoặc vị trí phục hồi được hỗ trợ. Một thiết kế PITR đáng tin phải trả lời:

1. Base backup nào là nguồn bắt đầu?
2. Các WAL segment cần thiết từ backup tới target nằm ở đâu?
3. Chúng có được lưu đủ, không bị lỗi tên, checksum, quyền hoặc retention không?
4. Kho lưu và khóa giải mã có thể truy cập khi primary/database region hỏng không?
5. Đã diễn tập khởi động database phục hồi từ chuỗi này chưa?
6. Mốc phục hồi thực tế có đạt mục tiêu nghiệp vụ không?

### 11.1. Ví dụ chuỗi WAL bị đứt

~~~text
Base backup B0
       |
       +-- WAL 001: có
       +-- WAL 002: có
       +-- WAL 003: MẤT
       +-- WAL 004: có
       +-- WAL 005: có
       |
       +-- Muốn PITR tới WAL 005
           nhưng chuỗi cần thiết bị đứt ở 003.
~~~

Nếu đoạn WAL 003 cần cho đường replay nhưng không có bản thay thế hợp lệ, không thể kết luận “có WAL 005 nghĩa là khôi phục tới 005 được”. Kiểm tra continuity và restore test là bắt buộc.

### 11.2. Backup mới không tự bù cho retention sai

Một base backup B1 mới hơn có thể giảm lượng WAL cần dùng cho một số target sau B1, nhưng không khôi phục được mọi target **trước B1**. Quy tắc retention cần bảo vệ **tập các base backup và WAL chain** đáp ứng cửa sổ phục hồi đã cam kết, không xóa WAL chỉ dựa vào tuổi file một cách tùy tiện.

### 11.3. Đừng kết luận từ thống kê archiver đơn lẻ

Ngay cả khi **failed_count = 0**, vẫn phải xem: archive thực tế được kiểm tra ở kho đích chưa, có WAL nào thiếu không, job backup đã kết thúc chưa và restore test đạt không. Số lỗi bằng 0 có thể chỉ nghĩa là không có lỗi được bộ đếm ấy ghi nhận trong thời gian thống kê.

## 12. RPO và RTO: từ mục tiêu đến bằng chứng

**RPO (Recovery Point Objective)** là lượng dữ liệu tối đa tổ chức chấp nhận mất khi phải phục hồi sau sự cố. **RTO (Recovery Time Objective)** là thời gian mục tiêu để phục hồi dịch vụ tới mức được yêu cầu.

Ví dụ nghiệp vụ đặt:

- **RPO mục tiêu: 5 phút.**
- **RTO mục tiêu: 30 phút.**

Điều đó không nghĩa cứ tạo backup mỗi 5 phút là đáp ứng đủ. Nếu backup chưa kiểm tra, WAL cần thiết không đủ hoặc restore mất 4 giờ, mục tiêu không đạt.

### 12.1. RPO thực tế có thể bị giới hạn bởi nhiều nguồn

Đối với một đường khôi phục từ backup:

~~~text
Mốc cuối cùng có thể phục hồi được
      |
      +-- Phụ thuộc base backup hợp lệ
      +-- Phụ thuộc chuỗi WAL được bảo quản đầy đủ
      +-- Phụ thuộc khả năng giải mã / restore
      |
      v
So với thời điểm xảy ra sự cố -> dữ liệu có nguy cơ mất
~~~

Đối với failover sang async replica, rủi ro lại phụ thuộc replica được chọn **đã nhận/flush/replay tới đâu**, cách failover xử lý WAL của primary cũ và bảo đảm commit của topology. Một **replay gap** đáng kể có thể ảnh hưởng read freshness trước failover, nhưng không được tự quy đổi thành số transaction đã mất.

### 12.2. RTO phải đo end-to-end

RTO có thể bao gồm:

1. Phát hiện sự cố và kích hoạt quy trình.
2. Xác định/thu hồi quyền truy cập hạ tầng thay thế.
3. Tải và giải mã backup.
4. Restore base backup và replay WAL.
5. Khởi động DB, kiểm tra dữ liệu và schema.
6. Chuyển connection/router/DNS hoặc cấu hình ứng dụng Java.
7. Xác minh request nghiệp vụ đọc/ghi an toàn.
8. Xử lý backlog và dọn các trạng thái không nhất quán được biết.

**Không lấy riêng thời gian pg_restore hoặc pg_basebackup làm RTO của dịch vụ.** Cần đo trong diễn tập phục hồi có thao tác nghiệp vụ cuối.

## 13. Thu thập chỉ số bằng Java/JDBC mà không làm chậm API

Ứng dụng Java có thể đọc thông tin replication qua JDBC, nhưng **không nên truy vấn các view giám sát trong mỗi HTTP request**. Nên có một monitoring worker riêng, lịch lấy mẫu hợp lý, timeout, giới hạn kết nối và quyền đọc tối thiểu.

### 13.1. Mẫu Java theo dõi replica từ primary

Ví dụ Java 17:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class PostgresReplicationMonitor {
    private final DataSource primaryDataSource;

    public PostgresReplicationMonitor(DataSource primaryDataSource) {
        this.primaryDataSource = primaryDataSource;
    }

    public record ReplicaSample(
            String applicationName,
            String state,
            String syncState,
            BigDecimal replayGapBytes,
            BigDecimal reportedReplayLagMillis) {}

    public List<ReplicaSample> sample() throws SQLException {
        String sql = """
            SELECT
                application_name,
                state,
                sync_state,
                pg_wal_lsn_diff(
                    pg_current_wal_lsn(), replay_lsn
                ) AS replay_gap_bytes,
                EXTRACT(EPOCH FROM replay_lag) * 1000
                    AS reported_replay_lag_ms
            FROM pg_stat_replication
            ORDER BY application_name
            """;

        List<ReplicaSample> samples = new ArrayList<>();

        try (Connection connection =
                     primaryDataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setQueryTimeout(3);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    samples.add(new ReplicaSample(
                        rows.getString("application_name"),
                        rows.getString("state"),
                        rows.getString("sync_state"),
                        rows.getBigDecimal("replay_gap_bytes"),
                        rows.getBigDecimal("reported_replay_lag_ms")));
                }
            }
        }

        return List.copyOf(samples);
    }
}
~~~

**Giới hạn quan trọng:**

- Mẫu đọc từ **primary**, lấy các WAL sender **đang hiện diện**, không tự biết danh sách tất cả replica dự kiến.
- **BigDecimal có thể NULL** khi thiếu LSN hoặc interval; không ép NULL thành zero.
- Danh sách rỗng không phải bằng chứng tất cả replica đã bắt kịp.
- **reportedReplayLagMillis** là chỉ số thời gian PostgreSQL báo, không phải phép đo chắc chắn độ cũ của dữ liệu end-to-end.
- **statement.setQueryTimeout(3)** giới hạn statement theo driver/DBMS; cần thêm deadline cho pool acquisition, network/socket và nhịp monitor.
- Không tự quyết định promote hoặc failover dựa trên một giá trị replayGapBytes; điều phối HA phải theo cơ chế leader/quorum/fencing của nền tảng.

Các quyền để xem đủ thông tin giám sát phụ thuộc role/PostgreSQL version. Cấu hình monitoring role riêng với quyền cần thiết, không để API dùng superuser và không ghi credential vào metric/log.

### 13.2. So sánh với danh sách replica dự kiến

Nếu topology yêu cầu standby A, B và C nhưng view chỉ thấy A/B, monitoring phải báo **C missing**. Không tính trung bình hai dòng còn lại rồi kết luận mọi replica đều khỏe.

Một tên application_name có thể không đủ duy nhất trong topology phức tạp; cần nguồn inventory đáng tin hoặc ID replica đã quy định, đặc biệt khi cluster đang reshard/reconfigure.

### 13.3. Không chuyển thiếu metric thành zero

~~~text
replay_gap_bytes = 0
    -> Đo được khoảng cách bằng 0 tại thời điểm lấy mẫu.

replay_gap_bytes = NULL / absent
    -> Không có giá trị hợp lệ để kết luận.

expected_replica_missing = true
    -> Replica theo topology không xuất hiện.

monitor_scrape_failed = true
    -> Phép đo không thực hiện được, chưa rõ tình trạng cụm.
~~~

Một exporter viết mọi lỗi thành giá trị 0 có thể biến **mất quan sát** thành **đèn xanh giả**. Theo dõi cả last successful scrape timestamp.

## 14. Dashboard: quan sát đồng thời replication và backup

Một dashboard phục vụ vận hành cần ít nhất bốn lớp.

### 14.1. Lớp topology

| Hiển thị | Mục đích |
|---|---|
| Expected/observed replicas | Có thiếu node không |
| Role primary/standby | Topology đang ở trạng thái nào |
| WAL sender và receiver state | Đường streaming còn hoạt động không |
| sync_state | Replica nào có vai trò trong cam kết đồng bộ |
| Last successful scrape | Dữ liệu quan sát còn mới không |
| Read routing policy | Replica nào đang phục vụ yêu cầu cần freshness |

Trạng thái **streaming** phải được hiển thị cùng LSN gap và health, không được dùng độc lập làm toàn bộ kiểm tra.

### 14.2. Lớp tiến độ dữ liệu

- Primary current WAL position và tốc độ sinh WAL.
- **Unsent bytes**, **write gap**, **flush gap**, **replay gap** theo replica.
- **write_lag/flush_lag/replay_lag** khi có giá trị, gắn nhãn rõ là chỉ số báo cáo theo thời gian chứ không phải freshness tuyệt đối.
- Phép đo read freshness chủ động khi nghiệp vụ đặt hạn mức stale data.
- Tốc độ gap tăng/giảm, thời gian đang backlog và thời gian bắt kịp.
- CPU, disk I/O, network và số long-running queries gây conflict trên standby.

Gap WAL tăng khi primary có đợt ghi lớn khác với tình trạng replay LSN đứng yên nhiều phút. Cần nhìn cả **mức backlog và tốc độ tiến lên**.

### 14.3. Lớp backup/WAL

| Hiển thị | Cần trả lời |
|---|---|
| Last successful base backup ID/time | Bản mới nhất được hoàn tất khi nào |
| Last failed/cancelled backup | Có lỗi job theo lịch không |
| Artifact verification status | Manifest và integrity đã được kiểm chưa |
| WAL archive success/failure | Archiver hoạt động như thế nào |
| WAL continuity/retention | Có đủ chuỗi cần cho PITR không |
| Slot retained WAL bytes | WAL có đang chiếm đĩa primary quá nhiều không |
| Backup repository free space | Kho đích có nguy cơ đầy không |
| Key/credential health | Restore có khả năng truy xuất và giải mã không |
| Last successful restore drill | Đã thử restore khi nào |
| Restore duration/point | Đạt RTO/RPO theo bài diễn tập không |

### 14.4. Lớp ảnh hưởng nghiệp vụ

Theo dõi tỷ lệ read từ replica không đạt freshness, latency API p95/p99, commit timeout và **unknown commit outcome**, tốc độ transaction, ảnh hưởng của backup tới I/O, và tính đúng của dữ liệu được kiểm tra sau restore.

Dashboard cần giúp người vận hành xác định **phạm vi ảnh hưởng**, không chỉ hiển thị nhiều biểu đồ kỹ thuật.

## 15. SLI, SLO và thiết kế cảnh báo

**SLI** là phép đo, **SLO** là mục tiêu của phép đo, **alert** là điều kiện cần phản ứng.

### 15.1. SLI phù hợp từng mục tiêu

| SLI | Ý nghĩa | Cần ngữ cảnh |
|---|---|---|
| Replicas available / expected | Đủ số replica dự kiến không | Maintenance/topology change |
| Replay gap bytes | Backlog WAL mỗi replica | WAL generation rate |
| Active replica freshness seconds | Read có đủ mới không | Nhịp heartbeat, clock và monitor |
| Archive failure delta | Có lỗi archive mới không | Counter reset và log |
| WAL archive continuity | Chuỗi WAL có đầy đủ không | Backup repository inventory |
| Last successful backup age | Tuổi của bản backup hoàn tất | Chu kỳ backup cam kết |
| Backup verification age | Bao lâu chưa verify | Từng backup class |
| Last restore drill age | Bao lâu chưa thử restore | Chính sách phục hồi |
| Restored point gap | Trong drill phục hồi đến đâu | Target timeline và dữ liệu đối chiếu |

Tên metric trong bảng là đề xuất, **không phải metric mặc định** của mọi exporter.

### 15.2. Quy tắc cảnh báo minh họa

Giả sử nghiệp vụ cho phép read stale tối đa 30 giây, đồng thời yêu cầu base backup thành công mỗi 24 giờ. Ví dụ ban đầu để **hiệu chỉnh bằng dữ liệu thực**:

- **Warning** khi active replica có freshness vượt 15 giây liên tục 5 phút.
- **Critical** khi active replica có freshness vượt 30 giây liên tục 2 phút trên luồng đọc cần dữ liệu mới.
- **Critical** khi replica bắt buộc biến mất hoặc monitoring không có dữ liệu mới trong cửa sổ đã định.
- **Warning** khi backup job theo lịch bị lỗi hoặc quá thời gian hoàn tất.
- **Critical** khi tuổi bản backup đủ điều kiện vượt chu kỳ cộng biên độ được phê duyệt, hoặc WAL chain không còn đáp ứng RPO.
- **Critical** khi restore drill gần nhất thất bại hay thời gian restore đo được vượt RTO.
- **Critical** khi WAL do slot giữ có nguy cơ làm primary đầy đĩa trước thời gian phản ứng an toàn.

Các giá trị **15 giây, 30 giây, 24 giờ** hoàn toàn là giả định; không sao chép vào production khi chưa xác minh hợp đồng nghiệp vụ, tốc độ WAL và độ ổn định của monitor.

### 15.3. Cảnh báo theo xu hướng và tác động

Nếu chỉ biết “lag > 1 GiB”, còn thiếu:

1. Lag có tăng liên tục không?
2. Primary có phát sinh WAL đột biến do batch job dự kiến không?
3. Standby replay_lsn có tiến lên không?
4. Slot có làm primary gần hết dung lượng không?
5. Replica đó có phục vụ API cần consistency mạnh không?
6. Có maintenance window đã được thông báo không?

Nếu metric bị thiếu do exporter ngừng, cần báo **monitoring unknown/stale** riêng, không coi mất mẫu là đạt ngưỡng khỏe.

## 16. Runbook khi replication lag tăng

### Bước 1 — Xác định tác động nghiệp vụ

- Standby nào đang nhận traffic đọc?
- API nào yêu cầu read-your-writes hoặc freshness nghiêm ngặt?
- Primary vẫn commit bình thường không?
- Các replica khác có cùng vấn đề không?
- Có migration, backup, ETL, batch hoặc maintenance vừa bắt đầu không?

### Bước 2 — Xác minh phép đo

- Metric có mới và query trên đúng node không?
- So sánh primary **pg_stat_replication** với standby **pg_stat_wal_receiver** và replay LSN.
- Có replica dự kiến nào không xuất hiện trên primary không?
- Primary WAL generation rate có tăng mạnh không?

### Bước 3 — Khoanh vùng pipeline

| Quan sát | Hướng điều tra |
|---|---|
| Current LSN - sent_lsn tăng | WAL sender, bandwidth, tốc độ sinh WAL |
| sent_lsn - write_lsn tăng | Network, receiver/write path, báo cáo tiến độ |
| write_lsn - flush_lsn tăng | Standby disk flush/I/O |
| flush_lsn - replay_lsn tăng | Replay/apply bottleneck, query conflict, CPU/disk |
| WAL sender biến mất | Connection, server process, network, topology |
| Slot active=false, restart_lsn cũ | Consumer ngừng, nguy cơ giữ WAL |
| replay_lsn vẫn tiến nhưng gap tăng | Primary sinh WAL nhanh hơn tốc độ replay |
| Last replay timestamp cũ, WAL gap gần 0 | Có thể primary idle, không phải replica trễ |

Đây là bảng **hướng khoanh vùng**, không xác định chắc nguyên nhân. Xem thêm logs, wait events, disk/network metrics và các thay đổi gần đây.

### Bước 4 — Bảo vệ tính đúng và khả năng sẵn sàng

Nếu một replica quá stale so với yêu cầu, cân nhắc tạm **ngừng route những read cần dữ liệu mới** tới replica đó và chuyển có kiểm soát sang primary khi capacity cho phép. Không đưa toàn bộ traffic về primary đột ngột mà không tính tải.

**Không promote standby chỉ vì lag tăng.** Với asynchronous replication, standby chưa bắt kịp có thể thiếu transaction đã được primary xác nhận; failover phải theo quy trình quorum/leader/fencing được phê duyệt.

### Bước 5 — Xử lý và xác minh phục hồi

Kiểm tra network packet loss/bandwidth, disk space, I/O, WAL receiver, CPU/memory, long-running query trên standby, ETL ghi nhiều WAL, replication slot và khả năng phải reinitialize standby.

Sau thay đổi, xác minh **replay LSN tiến lên, gap giảm, read freshness đạt mục tiêu và không phát sinh nguy cơ disk/WAL mới**. Ghi nhận thời gian ảnh hưởng, phạm vi API và bằng chứng để hậu kiểm.

## 17. Runbook khi backup hoặc WAL archive gặp vấn đề

### 17.1. Phân loại nguồn lỗi

1. **Scheduler:** job không chạy, bị vô hiệu hoặc quá lịch.
2. **Nguồn:** DB không cho kết nối, replication privilege/TLS lỗi, I/O quá tải.
3. **Đích:** repository/object store hết quota, mất network, lỗi credentials/keys.
4. **Artifact:** file thiếu, manifest không hợp lệ hoặc chưa upload hoàn tất.
5. **WAL chain:** mất một đoạn bắt buộc hoặc retention xóa sai.
6. **Restore:** file có nhưng database khởi động/khôi phục không được.
7. **Quan sát:** monitor hỏng khiến trạng thái thực chưa biết.

### 17.2. Không xóa WAL hoặc backup tùy tiện

Khi primary gần đầy vì WAL, **không xóa file WAL bằng tay** hoặc drop replication slot có consumer mà chưa hiểu hậu quả. Điều tra pg_replication_slots, archive status, network và retention, rồi thực hiện theo runbook đã được thử nghiệm.

**Không xóa backup cũ chỉ vì thấy backup mới xuất hiện**. Bản mới phải hoàn thành, được verify, cùng WAL chain cần thiết và nằm trong retention policy phù hợp.

### 17.3. Chọn mức sự cố theo khả năng phục hồi

Một backup job thất bại nhưng vẫn còn base backup hợp lệ, đủ WAL chain và nằm trong RPO có thể chưa làm mất khả năng recovery ngay. Ngược lại, nếu **không còn chuỗi phục hồi đáp ứng mục tiêu**, phải nâng mức cảnh báo dù primary vẫn hoạt động.

Sau khắc phục, kiểm tra backup mới, archive continuity, manifest và thực hiện restore test theo mức rủi ro, không chỉ tắt cảnh báo trên dashboard.

## 18. Diễn tập restore: bằng chứng quan trọng nhất về backup

Một **restore drill** là phép thử có kế hoạch để khôi phục từ backup trong môi trường **độc lập với production**, sau đó xác minh database và ứng dụng có thể hoạt động tại mốc phục hồi mong muốn. Đây là phép đo thực tiễn nhất cho **RTO thực tế** và một phần quan trọng để đánh giá **RPO đạt được**.

### 18.1. Quy trình diễn tập tối thiểu

1. **Chọn kịch bản:** mất toàn bộ primary, vô tình DELETE dữ liệu, mất region, backup repository có một file lỗi, hoặc phải phục hồi về thời điểm trước một migration sai.
2. **Chọn backup cụ thể:** ghi backup_id, cluster nguồn, thời điểm, loại backup, manifest, WAL chain và nguồn lưu.
3. **Chuẩn bị môi trường cô lập:** không sử dụng volume hay endpoint có thể ghi đè production. Tách DNS, credentials, network, storage và những consumer tự động của ứng dụng.
4. **Xác minh đầu vào:** backup đã hoàn tất, manifest/checksum hợp lệ trong phạm vi công cụ, có khóa giải mã và đủ WAL cho mục tiêu được chọn.
5. **Restore:** khôi phục physical base backup và replay WAL tới target, hoặc restore logical backup theo hợp đồng của loại backup.
6. **Khởi động DB và kiểm tra trạng thái:** xác nhận instance ở trạng thái mong muốn, không có lỗi recovery nghiêm trọng.
7. **Kiểm tra dữ liệu:** so sánh số lượng và khóa nghiệp vụ ở một số tập dữ liệu mẫu, kiểm tra ràng buộc, các transaction kỳ vọng ở/ngoài mốc.
8. **Kiểm tra ứng dụng:** chạy smoke test của Java persistence trên database được restore; đảm bảo repository, migrations và quyền đọc/ghi vận hành.
9. **Đo thời gian thực:** ghi thời gian phát hiện/kích hoạt, tải artifact, replay, khởi động, chuyển route thử nghiệm và khi API khả dụng.
10. **Ghi báo cáo:** mốc phục hồi thật, lượng dữ liệu không có so với target, RTO đã đo, lỗi, thiếu quyền, backlog và hành động khắc phục.

### 18.2. Tại sao phải cô lập tuyệt đối môi trường restore?

Nếu restored PostgreSQL vô tình dùng cùng endpoint/message broker với production, một scheduled job hoặc outbox dispatcher có thể **gửi lại email, thanh toán hoặc sự kiện** dựa trên dữ liệu cũ. Diễn tập phục hồi phải được cấu hình không gây side effect ra hệ ngoài.

Các cuộc thử nghiệm còn có thể chứa dữ liệu nhạy cảm từ backup. Chỉ người được cấp quyền mới truy cập môi trường; dùng encryption, audit, retention và cleanup theo chính sách. Không đưa raw production backup vào laptop cá nhân hoặc hệ không kiểm soát.

### 18.3. Kiểm tra logic “đến đúng thời điểm” thay vì chỉ DB khởi động

Giả sử giao dịch hợp lệ A commit trước mốc PITR và một DELETE nhầm B commit sau mốc ấy. Phép thử cần xác minh:

- Các bản ghi A đã có sau restore.
- Các thay đổi B không xuất hiện nếu target đã được chọn đúng và WAL replay dừng đúng mốc.
- Những transaction từ lúc target đến thời điểm xảy ra sự cố có thể bị mất theo quyết định phục hồi và đã được nghiệp vụ chấp nhận hoặc có kế hoạch đối soát.
- Các side effect bên ngoài như message, email hoặc thanh toán không tự đảo ngược khi restore DB về thời điểm cũ.

Không chỉ đếm số row toàn hệ thống: count bằng nhau vẫn có thể có nội dung sai, thiếu khóa hoặc trạng thái nghiệp vụ mâu thuẫn.

### 18.4. Kiểm tra restore là sự kiện có hạn sử dụng

Một lần restore thành công sáu tháng trước không chứng minh backup hôm nay còn restore được sau khi đổi PostgreSQL version, storage, khóa mã hóa, đường network, replication topology hoặc chính sách retention.

Nên đặt lịch restore drill định kỳ và sau những thay đổi lớn về backup tool, mã hóa, quyền, schema hoặc hạ tầng. Tần suất phụ thuộc mức nghiêm trọng/RPO/RTO được doanh nghiệp phê duyệt.

### 18.5. Báo cáo restore drill nên ghi gì?

| Trường | Nội dung mẫu |
|---|---|
| Drill ID | restore-test-2026-11 |
| Nguồn backup | backup ID và cluster ID |
| Target recovery | Mốc thời gian/LSN được yêu cầu |
| Actual recovered point | Mốc dữ liệu xác minh được |
| Start/end | Thời gian thực tế |
| Measured RTO | Bao gồm những công đoạn nào |
| Achieved RPO | Khoảng dữ liệu mất trong kịch bản |
| Integrity checks | Manifest, WAL chain, application invariants |
| Errors and workarounds | Lỗi quyền, khóa, timeout, mismatch |
| Result | PASS / FAIL / PARTIAL và bằng chứng |
| Owner/next review | Người duyệt và hành động tiếp theo |

Không khai “PASS” chỉ vì lệnh restore trả exit code 0 mà chưa chạy kiểm tra dữ liệu và API.

## 19. Quy tắc quan sát cho Java persistence và an toàn vận hành

### 19.1. Tránh gây thêm lỗi khi giám sát

- Không thực thi các query chẩn đoán nặng trên **mỗi request**.
- Dùng connection/monitor job với giới hạn tài nguyên riêng khi phù hợp.
- Đặt timeout và giới hạn retry của exporter, tránh reconnect storm khi DB đang lỗi.
- Theo dõi **monitor failure** và tuổi phép đo, không báo green khi thiếu dữ liệu.
- Không làm readiness của toàn API phụ thuộc vào một backup repository đang chậm nếu ứng dụng vẫn có thể phục vụ an toàn theo hợp đồng. Thay vào đó phải hiển thị mức rủi ro recovery và điều kiện dừng ghi khi chính sách yêu cầu.

### 19.2. Đọc từ standby và read-your-writes

Nếu ứng dụng vừa commit một đơn trên primary rồi đọc ngay từ standby bất đồng bộ, nó có thể chưa thấy đơn ấy. Không được dựa vào **status = streaming** để mặc định read-your-writes được bảo đảm.

Các lựa chọn tùy kiến trúc:

- Route những truy vấn cần trạng thái mới ngay về primary.
- Dùng token/LSN/session consistency hoặc đợi standby bắt kịp nếu nền tảng và deadline hỗ trợ.
- Đánh dấu endpoint chấp nhận stale reads rõ ràng.
- Khi replica quá stale, dừng route một phần traffic có yêu cầu nghiêm ngặt.
- Khi COMMIT có kết quả chưa rõ, dùng operation ID và đối soát trên nguồn có thẩm quyền thay vì đọc một replica trễ rồi kết luận transaction thất bại.

### 19.3. Backup/monitoring là dữ liệu nhạy cảm

Backup có thể chứa toàn bộ dữ liệu production. Cần:

- Mã hóa khi truyền và lưu, quản lý khóa và kiểm thử khả năng giải mã.
- Tách quyền tạo backup, xem backup, restore và xóa backup theo nguyên tắc tối thiểu quyền.
- Giới hạn thông tin host/port/conninfo, slot name và path trong log công khai.
- Có audit trail cho việc tải, restore, thay retention hoặc xóa backup.
- Bảo vệ danh sách artifact và credentials khỏi việc một tài khoản runtime bình thường có thể xóa cả nguồn lẫn backup.
- Kiểm tra chính sách dữ liệu cá nhân và thời gian lưu bản backup, nhất là khi thực hiện restore drill.

Không dùng backup chứa dữ liệu thật làm fixture test bình thường mà chưa áp dụng các biện pháp phê duyệt và bảo vệ cần thiết.

### 19.4. Một kế hoạch failover phải nối với khả năng backup

Failover giúp dịch vụ tiếp tục chạy trên replica hợp lệ nhưng **không thay thế backup/restore**. Khi cả primary và replica cùng bị lỗi logic, DELETE nhầm hoặc ransomware ảnh hưởng nhiều node, cần nguồn dữ liệu độc lập để phục hồi. Ngược lại, backup có thể phục hồi dữ liệu nhưng không nhất thiết đáp ứng RTO khi cần chuyển dịch vụ trong vài giây.

**High availability và disaster recovery là hai mục tiêu bổ sung**, với phép đo và diễn tập khác nhau.

## 20. Các kịch bản sự cố để phân tích

| Tình huống | Dấu hiệu | Kết luận nên tránh | Hành động phù hợp |
|---|---|---|---|
| Primary ghi ít suốt 3 giờ | Last replay timestamp đã 3 giờ | “Replica trễ 3 giờ” | So LSN gap và heartbeat |
| Standby B mất mạng | B biến mất khỏi pg_stat_replication | “Mọi replica đã bắt kịp” | So expected membership, kiểm tra receiver/node |
| Replay gap tăng nhưng receive vẫn tiến | Receive LSN tiến, replay LSN chậm | “Chỉ lỗi network” | Kiểm tra apply/recovery, I/O, query conflict |
| Backup job success nhưng restore lỗi | Artifact tồn tại, drill thất bại | “Backup vẫn healthy” | Đánh dấu restoreability không đạt, sửa chain/permission |
| pg_stat_archiver failed_count = 0 | Không thấy lỗi counter | “WAL archive chắc đầy đủ” | Kiểm kho đích, continuity, restore |
| Last archived time cũ, primary idle | Không có WAL segment mới đáng kể | “Archive chắc chắn chết” | Kiểm WAL activity và archive job |
| Replication slot giữ nhiều WAL | restart_lsn cũ, disk gần đầy | “Xóa slot là xong” | Tìm consumer, retention policy và phương án rebuild |
| Có base backup mới, WAL giữa bị thiếu | Backup age nhỏ | “PITR tới hiện tại được” | Verify WAL chain theo target |
| Async standby bị lag khi primary hỏng | Replay lạc hậu | “Failover không mất dữ liệu” | Đánh giá WAL/LSN, chọn recovery path |
| Backup restore trong 8 phút nhưng API cần 45 phút | Restore command nhanh | “RTO = 8 phút” | Đo hết quá trình dịch vụ khả dụng |
| Metric exporter mất kết nối | Không có mẫu mới | “Lag = 0” | Báo monitoring stale/unknown |
| Java COMMIT timeout | Client không nhận phản hồi | “Transaction chắc chưa commit” | Idempotency và đối soát |

Bảng trên nhằm giúp **không nhầm triệu chứng với kết luận**. Sự cố thực cần kết hợp WAL, backup repository, logs, quyền và bằng chứng ứng dụng.

## 21. Những hiểu nhầm phổ biến

1. **“Streaming là đủ, replica chắc mới nhất.”** Streaming chỉ phản ánh kết nối/trạng thái truyền; còn phải so mốc replay và yêu cầu read freshness.
2. **“write_lag = replay_lag.”** Các giai đoạn ghi, flush và áp dụng WAL khác nhau.
3. **“replay_lag luôn bằng tuổi dữ liệu trên standby.”** Interval báo cáo không phải freshness bảo đảm trong mọi điều kiện, đặc biệt khi primary idle.
4. **“now() - pg_last_xact_replay_timestamp() chính là replication lag.”** Chỉ số này có thể rất lớn khi không có transaction mới.
5. **“LSN gap 10 MB nghĩa là mất 10 MB dữ liệu nghiệp vụ.”** Byte WAL không tương đương số byte dữ liệu hay số transaction.
6. **“Không có dòng pg_stat_replication nghĩa là không có lag.”** Replica đã mất kết nối có thể không có WAL sender để hiển thị.
7. **“Replica là backup.”** Xóa nhầm cũng được nhân bản và replica không cung cấp lịch sử PITR tự thân.
8. **“archived_count tăng nghĩa là restore được.”** Còn cần artifact integrity, WAL continuity và restore test.
9. **“failed_count = 0 nghĩa là không có bất kỳ lỗi archive nào.”** Đó chỉ là phạm vi bộ đếm trong một thời gian thống kê; không thay thế logs và kiểm tra kho.
10. **“Base backup mới nhất luôn khôi phục tới thời điểm bất kỳ.”** PITR phụ thuộc WAL chain và target.
11. **“pg_verifybackup PASS chứng minh RTO đạt.”** Cần thực hiện restore và đo thời gian dịch vụ sẵn sàng.
12. **“RPO của backup chính là replay_lag của standby.”** Đây là hai recovery path với cơ chế và giới hạn khác nhau.
13. **“Đồng bộ nghĩa mọi replica đều có dữ liệu mới.”** Phụ thuộc cấu hình quorum/sync_commit và replica được chọn.
14. **“Slot giữ WAL giúp sao lưu an toàn.”** Slot phục vụ consumer replication; có thể gây áp lực disk và không thay thế archive.
15. **“Số đo thiếu thì điền 0 để dashboard trông ổn.”** Thiếu dữ liệu phải là UNKNOWN/stale.
16. **“Có backup nên không cần thử restore.”** Không kiểm tra được mốc, quyền và khả năng khởi động thực tế.
17. **“Failover giải quyết mọi loại mất dữ liệu.”** Failover có thể mang lỗi logic sang node khác; cần backup độc lập.
18. **“Monitoring role cần superuser.”** Cần phân quyền đủ để đọc các view cần thiết, không cấp rộng chỉ vì tiện.
19. **“Restore thành công về mặt database là xong.”** Còn cần schema, app connectivity, dữ liệu, giao dịch ngoài DB và thời gian phục vụ.
20. **“Chỉ cần một ngưỡng lag cho mọi dịch vụ.”** Ngưỡng phải gắn với workload, RPO, read consistency và cách đo.

## 22. Bài tập tự kiểm tra

### Bài 1 — Streaming nhưng chưa replay

Primary báo trạng thái **streaming**, trong khi sent_lsn và flush_lsn tiến nhanh nhưng replay_lsn gần như đứng yên. Có thể kết luận gì và cần kiểm tra gì?

*Gợi ý:* đường truyền và flush vẫn tiến, replay/apply là nơi cần điều tra: I/O, recovery conflict, query dài và tài nguyên standby. Không đồng nhất streaming với freshness.

### Bài 2 — Mất replica khỏi view

Hệ thống phải có ba standby, nhưng pg_stat_replication chỉ trả hai dòng đều có replay gap nhỏ. Dashboard có thể xanh toàn cụm không?

*Gợi ý:* không. Replica thứ ba có thể mất kết nối; phải so với expected membership.

### Bài 3 — Timestamp replay rất cũ

Primary không có transaction ghi mới trong 90 phút. Standby báo last transaction replay timestamp 90 phút trước, nhưng LSN gap là 0. Có thể nói replica trễ 90 phút không?

*Gợi ý:* không. Timestamp cũ có thể do không có transaction mới; dùng LSN/heartbeat và trạng thái cluster.

### Bài 4 — WAL gap và RPO

Primary current LSN hơn standby replay_lsn 500 MiB. Có thể khẳng định sẽ mất chính xác 500 MiB dữ liệu nghiệp vụ nếu failover không?

*Gợi ý:* không. Đây là byte WAL, không phải byte dữ liệu đã commit hoặc sự mất mát chắc chắn. Phải xét WAL durability, replica được chọn và failover protocol.

### Bài 5 — Base backup mới, archive thiếu

Backup B0 hoàn tất sáng nay, nhưng kho WAL thiếu một segment cần thiết cho target PITR chiều nay. Kết luận nào đúng?

*Gợi ý:* bản backup mới không bảo đảm phục hồi tới target. Cần continuity và restore test.

### Bài 6 — Backup job thành công nhưng restore thất bại

Scheduler và backup tool đều báo SUCCESS, kiểm tra khôi phục trên môi trường độc lập lại không mở database được. Tình trạng backup có được đánh dấu fully verified không?

*Gợi ý:* không. Trạng thái job success khác restoreability. Cần đánh dấu restore drill FAILED và điều tra.

### Bài 7 — Retained WAL tăng

Replica ngừng 24 giờ, slot active=false, retained WAL bytes tăng nhanh và primary còn ít dung lượng. Có nên lập tức xóa slot?

*Gợi ý:* không. Xác minh consumer, ảnh hưởng replication/CDC, phương án rebuild và quy trình xử lý disk/retention.

### Bài 8 — RPO/RTO

Một ứng dụng đặt RPO 5 phút và RTO 30 phút. Drill phục hồi được dữ liệu ở mốc cách sự cố 2 phút nhưng mất 70 phút mới phục vụ lại HTTP. Đạt tiêu chí nào?

*Gợi ý:* đạt mục tiêu RPO trong kịch bản đã thử, không đạt RTO. Cần đo end-to-end.

### Bài 9 — pg_stat_archiver không báo lỗi

failed_count không tăng, nhưng object store backup repository đang thiếu WAL segment. Có được coi archiving an toàn không?

*Gợi ý:* không. Counter DB chỉ một lớp quan sát; phải kiểm kho đích/continuity và khả năng restore.

### Bài 10 — Read-your-writes

Ứng dụng Java ghi đơn lên primary, COMMIT thành công rồi đọc ngay trên async standby và thấy không có đơn. Có nên gửi lại INSERT bằng operation ID mới?

*Gợi ý:* không. Có thể replica stale; route đọc consistency phù hợp, giữ operation ID ổn định và đối soát.

### Bài 11 — Phép đo không lấy được

Monitoring worker JDBC timeout khi truy vấn primary. Exporter dự định gán replay lag = 0 để tránh báo đỏ. Điều gì sai?

*Gợi ý:* mất dữ liệu quan sát không tương đương replica khỏe. Đánh dấu scrape failed/stale, không giả zero.

### Bài 12 — Backup và quyền truy cập

Một restore drill yêu cầu dùng bản backup production có PII trên máy laptop cá nhân để “thử nhanh”. Có nên làm không?

*Gợi ý:* không nếu chưa có môi trường/biện pháp được phê duyệt. Cần test cô lập có mã hóa, quyền, audit và cleanup.

## 23. Tóm tắt và áp dụng

**Đo replication lag** là đo các mốc WAL từ primary qua **sent → write → flush → replay**, so sánh LSN theo byte và hiểu đúng ý nghĩa những chỉ số thời gian báo cáo. Luôn phân biệt **node không xuất hiện**, **metric bị thiếu**, **replica vẫn nhận nhưng replay chậm** và **primary không có giao dịch mới**. Đối với luồng Java cần read-your-writes, chỉ dùng replica khi chiến lược nhất quán đáp ứng được mức độ mới của dữ liệu.

**Đo tình trạng sao lưu** không dừng ở lịch chạy hoặc exit code của job. Phải theo dõi base backup hoàn tất, manifest/checksum, **WAL archive liên tục**, quyền truy cập, retention và quan trọng nhất là **diễn tập restore độc lập**. Chỉ một backup có thể phục hồi dữ liệu đúng mốc, trong thời gian mục tiêu, mới tạo bằng chứng đáng tin cho RPO/RTO của hệ thống.

Trong vận hành persistence, kết hợp các lớp đo với dashboard, cảnh báo có ngưỡng theo nghiệp vụ, runbook và kiểm thử sự cố. **Replica không thay backup; backup không thay HA; số đo tốt không thay được một lần phục hồi đã kiểm chứng.** Hiểu các ranh giới này giúp ứng dụng Java duy trì dữ liệu bền vững, đọc nhất quán theo hợp đồng và phục hồi có kiểm soát trước sự cố thực tế.
