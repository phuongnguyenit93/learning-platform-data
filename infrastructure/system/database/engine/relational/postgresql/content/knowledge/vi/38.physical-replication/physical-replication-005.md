# Replication slot, giữ WAL và nguy cơ đầy đĩa trong PostgreSQL

Physical replication slot giúp PostgreSQL giữ lại những WAL segments mà một standby có thể vẫn cần để tiếp tục streaming replication. Cơ chế này bảo vệ standby khỏi việc primary recycle WAL quá sớm khi replica bị ngắt kết nối hoặc replay chậm.

Đổi lại, slot có thể giữ WAL lâu hơn dự kiến. Nếu standby dừng, mất mạng, không theo kịp primary hoặc bị bỏ quên, primary vẫn phải giữ các WAL segments cần thiết cho slot. Khi nhiều WAL được tạo ra, thư mục `pg_wal` có thể tăng đến mức chiếm hết dung lượng filesystem.

Bài **“Replication slot, giữ WAL và nguy cơ đầy đĩa”**, thuộc chương **Sao chép vật lý** của module **Database Engine Relational PostgreSQL**, giải thích:

- Physical replication slot và vai trò của `restart_lsn`.
- Vì sao slot inactive vẫn giữ WAL.
- Khác biệt giữa slot retention, `wal_keep_size`, `max_wal_size` và WAL archiving.
- Cách ước lượng lượng WAL cần giữ và giám sát dung lượng.
- `max_slot_wal_keep_size`, slot invalidation và phương án khôi phục standby.
- Quy trình tạo, sử dụng, kiểm tra và xóa slot an toàn.
- Cách xử lý sự cố `pg_wal` tăng nhanh hoặc filesystem sắp đầy.

> **Nguyên tắc:** replication slot là một điểm giữ WAL trên primary, không phải nơi lưu trữ WAL riêng. Slot giúp standby không bị hụt WAL khi reconnect, nhưng một slot không được tiêu thụ có thể khiến primary giữ WAL vô hạn nếu không có giới hạn phù hợp.

---

## 1. Replication slot là gì?

**Replication slot** là trạng thái bền vững do PostgreSQL quản lý để bảo vệ những tài nguyên replication consumer vẫn cần.

Với physical replication, slot giữ WAL cần thiết để một physical standby tiếp tục nhận/replay WAL sau khi bị gián đoạn.

Slot được lưu trong trạng thái của cluster và vẫn tồn tại sau khi replication connection ngắt. Vì vậy, slot có thể tiếp tục giữ WAL ngay cả khi không có standby nào đang kết nối.

### 1.1. Slot không chứa bản sao WAL

Replication slot không phải một thư mục archive riêng và không lưu bản sao WAL của chính nó. Nó lưu tiến độ/horizon để PostgreSQL biết WAL segments nào chưa được phép recycle.

WAL vẫn nằm trong thư mục `pg_wal` của primary. Slot chỉ ảnh hưởng đến quyết định giữ hay tái sử dụng những segments đó.

### 1.2. Slot giúp giải quyết vấn đề gì?

Giả sử primary tạo WAL liên tục, nhưng standby mất mạng trong 20 phút.

- Không có slot: primary có thể recycle các WAL segments cũ theo retention settings. Khi standby quay lại, một segment nó cần có thể đã không còn.
- Có physical slot: primary giữ lại WAL từ vị trí slot còn cần. Standby có thể tiếp tục streaming nếu WAL cần thiết vẫn còn và dung lượng primary đủ.

Slot tăng khả năng standby reconnect mà không phải tạo lại base backup.

## 2. Physical replication slot và logical replication slot

PostgreSQL có hai loại slot phổ biến:

| Loại slot | Consumer | Tài nguyên chính có thể giữ |
|---|---|---|
| Physical | Physical standby/replication client | WAL segments từ restart LSN |
| Logical | Logical decoding/CDC consumer | WAL, transaction horizon và catalog horizon theo trạng thái slot |

Bài này tập trung vào **physical replication slot** trong physical streaming replication.

Logical slot có thêm các khái niệm như `catalog_xmin` và tiến độ logical decoding. Không suy diễn mọi chi tiết logical slot sang physical slot.

## 3. Luồng WAL trong physical replication

Một transaction ghi dữ liệu trên primary tạo WAL. WAL sender chuyển WAL cho standby; standby nhận WAL, ghi vào WAL files của nó và startup/recovery process replay để cập nhật data pages.

~~~text
Ứng dụng ghi dữ liệu
        |
        v
Primary tạo WAL
        |
        v
WAL sender
        |
        | streaming replication
        v
Standby WAL receiver
        |
        v
WAL files trên standby
        |
        v
Startup process replay WAL
        |
        v
Standby data state tiến lên
~~~

Physical replication slot nằm ở phía primary và giữ WAL mà standby có thể cần. Nó không làm standby replay nhanh hơn; nó chỉ bảo đảm primary không loại bỏ WAL quá sớm trong phạm vi retention policy.

## 4. LSN và restart_lsn

**LSN (Log Sequence Number)** là vị trí trong WAL stream.

Trường quan trọng nhất khi phân tích physical slot là `restart_lsn`:

- Nó biểu thị WAL position cũ nhất mà slot có thể còn cần.
- Primary phải giữ WAL segments cần thiết bắt đầu từ vị trí này.
- Khi standby tiến triển và primary nhận được feedback phù hợp, restart LSN có thể tiến lên.
- Nếu standby ngừng tiêu thụ WAL, restart LSN có thể đứng yên trong khi primary tiếp tục tạo WAL.

`restart_lsn` không phải replay LSN hiện tại của standby. Hai giá trị phục vụ hai mục đích khác nhau.

### 4.1. restart_lsn và replay_lsn

| Giá trị | Nơi quan sát | Ý nghĩa |
|---|---|---|
| `restart_lsn` | `pg_replication_slots` trên primary | WAL cũ nhất slot còn có thể cần |
| `pg_last_wal_receive_lsn()` | Standby | WAL gần nhất đã nhận qua streaming |
| `pg_last_wal_replay_lsn()` | Standby | WAL gần nhất đã replay |
| `flush_lsn` | `pg_stat_replication` trên primary | Vị trí WAL standby đã flush theo feedback |

Không lấy `restart_lsn` thay cho replay progress. Slot có thể giữ một đoạn WAL cũ hơn replay position do quy tắc restart/retention của replication.

## 5. Vì sao slot giữ WAL?

WAL được ghi theo segment files. Khi một segment cũ không còn cần thiết, PostgreSQL có thể recycle hoặc remove nó theo checkpoint, archive và replication retention rules.

Nếu một replication slot còn cần WAL trong segment, PostgreSQL không thể recycle segment đó chỉ vì standby đang offline.

~~~text
WAL segments:
[0001] [0002] [0003] [0004] [0005] [0006]
   ^                       ^
   |                       |
restart_lsn             current WAL

Slot cần các segments từ vị trí restart_lsn trở đi.
Primary tiếp tục tạo WAL và giữ các segments còn cần.
~~~

Khi standby xác nhận tiến độ và slot restart LSN tiến lên, những WAL segments cũ hơn có thể trở thành ứng viên recycle nếu không có cơ chế khác cũng cần chúng.

### 5.1. Slot retention không có nghĩa giữ mọi WAL mãi mãi

Một slot khỏe mạnh thường tiến triển theo consumer. Khi tiến độ được cập nhật, WAL cũ được giải phóng dần theo checkpoint và các retention rules khác.

Rủi ro xuất hiện khi slot không tiến triển trong thời gian dài.

## 6. Inactive slot vẫn giữ WAL

Trường `active` trong `pg_replication_slots` cho biết slot hiện có replication process sử dụng hay không.

- `active = true`: có process đang dùng slot.
- `active = false`: hiện không có process sử dụng slot.

**Inactive không có nghĩa slot đã bị xóa hoặc không còn giữ WAL.**

Một standby có thể disconnect vì maintenance hoặc network outage. Slot cần tiếp tục tồn tại để standby reconnect. Vì vậy PostgreSQL giữ state của slot và WAL cần thiết, dù active=false.

### 6.1. Slot inactive lâu ngày là dấu hiệu cần điều tra

Các nguyên nhân:

- Standby bị tắt nhiều ngày.
- Replica bị mất kết nối do network/firewall.
- Standby server đã bị decommission nhưng slot còn lại.
- Standby không thể replay vì thiếu disk hoặc lỗi recovery.
- Slot được tạo thử nghiệm nhưng không dùng nữa.
- Failover khiến consumer cũ không quay lại primary ban đầu.

Không drop slot chỉ dựa trên active=false. Trước hết xác định consumer và kế hoạch reconnect/rebuild.

## 7. Điều gì xảy ra khi không có replication slot?

Nếu standby dùng streaming replication nhưng không có slot, primary không có một per-consumer retention point bền vững tương đương để giữ WAL cho standby.

Primary có thể vẫn giữ một lượng WAL tối thiểu qua `wal_keep_size`, nhưng nếu standby offline lâu hơn khoảng WAL đó, nó có thể cần WAL đã bị recycle.

Khi đó standby không thể tiếp tục từ vị trí cũ bằng streaming WAL hiện có. Nếu archive có đủ WAL, nó có thể lấy phần thiếu từ archive; nếu không, cần rebuild/reseed standby.

## 8. So sánh các cơ chế giữ WAL

Các cấu hình sau có liên quan nhưng không thay thế lẫn nhau:

| Cơ chế | Mục đích | Phạm vi |
|---|---|---|
| Physical replication slot | Giữ WAL cần cho một consumer cụ thể | Per-slot |
| `wal_keep_size` | Giữ tối thiểu một lượng WAL cho standby | Mức chung |
| `max_wal_size` | Ngưỡng WAL hướng dẫn checkpoint | Checkpoint policy |
| WAL archiving | Lưu WAL segments vào archive | Archive retention |
| Backup/recovery workflow | Bảo vệ khả năng phục hồi | Backup policy |

### 8.1. wal_keep_size không phải max_slot_wal_keep_size

`wal_keep_size` giữ một lượng WAL tối thiểu để hỗ trợ standby. Nó không giới hạn lượng WAL mà một replication slot inactive có thể giữ.

`max_slot_wal_keep_size` đặt giới hạn cho lượng WAL mà replication slots được phép giữ qua checkpoint policy.

### 8.2. max_wal_size không phải giới hạn dung lượng pg_wal

`max_wal_size` là ngưỡng mềm dùng để điều khiển checkpoint. Replication slots, WAL archiving backlog, `wal_keep_size` và các nhu cầu khác có thể khiến `pg_wal` lớn hơn giá trị này.

Đừng đặt `max_wal_size` rồi coi đó là bảo đảm thư mục pg_wal không thể vượt quá dung lượng đã định.

## 9. max_slot_wal_keep_size

Tham số:

~~~sql
SHOW max_slot_wal_keep_size;
~~~

`max_slot_wal_keep_size` giới hạn lượng WAL mà replication slots được phép giữ, tính bằng MB.

- Giá trị mặc định `-1` nghĩa là không giới hạn.
- Giá trị hữu hạn giúp hạn chế slot giữ WAL quá nhiều.
- Giới hạn được kiểm tra trong quan hệ với checkpoint; không nên coi đây là bộ giới hạn byte chính xác tức thời.
- Khi WAL cần cho slot đã bị recycle do giới hạn, slot có thể bị invalidated và consumer không còn tiếp tục từ slot đó.

Ví dụ cấu hình minh họa:

~~~text
max_slot_wal_keep_size = 20GB
~~~

Giá trị phải được chọn dựa trên tốc độ sinh WAL, thời gian standby có thể offline, thời gian catch-up và dung lượng filesystem. Không dùng 20GB như một mặc định chung.

## 10. Trade-off của giới hạn slot

| Chính sách | Lợi ích | Rủi ro |
|---|---|---|
| Không giới hạn (`-1`) | Standby có thời gian reconnect dài hơn nếu storage còn đủ | Slot bỏ quên có thể làm đầy disk |
| Giới hạn thấp | Bảo vệ dung lượng primary | Slot có thể mất WAL cần thiết nhanh |
| Giới hạn cao | Có thêm thời gian cho outage/catch-up | Cần dành nhiều dung lượng hơn |
| Không dùng slot | Ít nguy cơ slot giữ WAL vô hạn | Standby có thể hụt WAL khi offline |

Một giới hạn tốt cân bằng **khả năng phục hồi standby** với **an toàn dung lượng primary**.

### 10.1. Giới hạn không thay thế monitoring

Ngay cả khi có max_slot_wal_keep_size, vẫn cần alert trước khi slot chạm ngưỡng. Khi slot đã lost, việc tăng giới hạn sau đó không tự khôi phục WAL segments đã bị recycle.

## 11. wal_keep_size

~~~sql
SHOW wal_keep_size;
~~~

`wal_keep_size` chỉ định lượng WAL tối thiểu mà primary giữ lại cho standby, theo MB.

Trong các PostgreSQL versions cũ, tham số tương ứng là `wal_keep_segments`, tính theo số segments. Kiểm tra đúng setting theo major version.

`wal_keep_size` có thể hỗ trợ standby không dùng slot hoặc làm lớp retention bổ sung. Nó không phải cơ chế xác nhận standby đã nhận WAL.

## 12. max_wal_size và checkpoint

~~~sql
SHOW max_wal_size;
SHOW checkpoint_timeout;
SHOW checkpoint_completion_target;
~~~

`max_wal_size` điều khiển thời điểm PostgreSQL thường cần checkpoint sớm hơn khi WAL generation lớn. Checkpoint ghi dirty pages và cập nhật recovery point.

Một slot giữ WAL cũ có thể ngăn segment được recycle dù checkpoint đã chạy. Vì vậy:

- Checkpoint hoàn tất không có nghĩa mọi WAL segments cũ đều được xóa.
- Tăng max_wal_size không giải quyết một slot bị ghim lâu.
- Giảm max_wal_size không buộc PostgreSQL xóa WAL mà slot còn cần.

## 13. WAL archiving cũng có thể giữ WAL

Nếu `archive_mode` bật và `archive_command` liên tục thất bại, PostgreSQL giữ WAL cần archive thay vì recycle bình thường.

Vì vậy, `pg_wal` tăng không nhất thiết do replication slot.

Kiểm tra cả:

- Slot retention.
- Standby lag.
- WAL archive failures.
- wal_keep_size.
- Backup/recovery processes.
- Disk usage và checkpoint activity.

### 13.1. pg_stat_archiver

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

Nếu `failed_count` tăng hoặc `last_failed_time` liên tục cập nhật, kiểm tra archive destination, permissions, network và archive command logs.

## 14. Xem danh sách replication slots

Trên primary:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    xmin,
    catalog_xmin
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Đối với physical slot, các trường cần quan sát nhất cho WAL retention là `slot_name`, `slot_type`, `active` và `restart_lsn`.

Một số trường như `xmin`/`catalog_xmin` liên quan tuple/catalog retention và có thể NULL hoặc không có ý nghĩa với physical slot trong nhiều tình huống.

### 14.1. Không giả định view có cùng columns ở mọi version

`pg_replication_slots` được bổ sung columns theo PostgreSQL versions. Dùng:

~~~text
\d+ pg_replication_slots
~~~

trong psql để xem schema thực tế trước khi viết monitoring query dùng fields mới.

## 15. Ước lượng WAL mà một slot đang giữ

Trên primary, có thể ước lượng khoảng cách từ current WAL position đến restart LSN:

~~~sql
SELECT
    slot_name,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS estimated_retained_wal
FROM pg_replication_slots
WHERE slot_type = 'physical'
  AND restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    restart_lsn
) DESC;
~~~

Đây là **ước lượng khoảng cách WAL**, không phải phép đo chính xác số bytes độc quyền của từng slot.

Nhiều slots có thể cùng giữ các segments; các cơ chế khác cũng có thể yêu cầu cùng WAL. Tổng các ước lượng theo slot có thể đếm trùng.

## 16. Quan sát slot status trên PostgreSQL hỗ trợ wal_status

Các PostgreSQL versions có hỗ trợ thêm có thể cung cấp:

- `wal_status`: trạng thái WAL retention của slot.
- `safe_wal_size`: lượng WAL có thể được tạo thêm trước khi slot có nguy cơ vượt giới hạn.

Ví dụ trên server có các columns này:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
WHERE slot_type = 'physical';
~~~

Các giá trị `wal_status` thường gặp:

| Status | Ý nghĩa khái quát |
|---|---|
| `reserved` | WAL cần cho slot vẫn nằm trong phạm vi được giữ |
| `extended` | WAL được giữ vượt ngưỡng thông thường do retention requirements |
| `unreserved` | WAL cần thiết không còn được bảo đảm giữ qua checkpoint tiếp theo |
| `lost` | Slot không còn usable vì WAL cần thiết đã mất |

Chi tiết và availability tùy version. Không chạy query này trên server cũ nếu view chưa có columns tương ứng.

## 17. safe_wal_size

`safe_wal_size` hữu ích khi `max_slot_wal_keep_size` được cấu hình hữu hạn.

Nó cho biết lượng WAL còn có thể được tạo trước khi slot có nguy cơ bị invalidated theo giới hạn. Khi giá trị giảm về thấp, primary có thể sắp vượt ngưỡng giữ WAL cho slot.

Một alert có thể dựa trên:

- safe_wal_size thấp.
- wal_status chuyển sang unreserved.
- retained WAL tăng liên tục.
- slot inactive lâu.
- filesystem free space thấp.

Nếu max_slot_wal_keep_size không giới hạn hoặc server không thể tính giá trị, safe_wal_size có thể NULL.

## 18. Tính WAL generation rate

Có thể lấy WAL bytes từ `pg_stat_wal` trên các phiên bản hỗ trợ:

~~~sql
SELECT
    wal_bytes,
    stats_reset
FROM pg_stat_wal;
~~~

Lấy hai mẫu cách nhau một khoảng thời gian:

~~~text
WAL rate = (wal_bytes mới - wal_bytes cũ) / số giây
~~~

Ví dụ:

- Mẫu đầu: 120 GB.
- Mẫu sau 10 phút: 126 GB.
- WAL generated: 6 GB.
- Rate trung bình: 0,6 GB/phút.

Đây chỉ là ví dụ tính toán. Workload có thể có burst và tốc độ thay đổi theo giờ.

### 18.1. Không dùng counter sau reset như một mẫu liên tục

`pg_stat_wal.stats_reset` cho biết thời điểm statistics reset. Nếu counter reset giữa hai mẫu, phép trừ sẽ sai. Theo dõi reset timestamp cùng với counter.

## 19. Ước lượng dung lượng cần giữ

Một công thức planning đơn giản:

~~~text
Required WAL budget
    ≈ peak WAL generation rate
      × maximum tolerated standby outage
      + catch-up allowance
      + safety margin
~~~

Ví dụ minh họa:

- Peak WAL rate: 0,6 GB/phút.
- Standby outage cần chịu được: 30 phút.
- Catch-up/operational buffer: 10 GB.
- Safety margin: 25%.

WAL cơ bản trong outage:

~~~text
0,6 GB/phút × 30 phút = 18 GB
~~~

Cộng catch-up allowance rồi nhân safety margin:

~~~text
(18 GB + 10 GB) × 1,25 = 35 GB
~~~

Có thể bắt đầu đánh giá giới hạn quanh 35 GB trong ví dụ này, nhưng cần cộng thêm WAL retention từ archive backlog, các slots khác, wal_keep_size, checkpoint behavior và các yếu tố storage.

### 19.1. Dùng peak rate thay vì chỉ average rate

Một workload batch có thể sinh WAL gấp nhiều lần mức trung bình. Nếu chỉ tính average, slot có thể vượt giới hạn trong một đợt bulk load hoặc index build.

## 20. Catch-up capacity cũng quan trọng

Khi standby reconnect, nó phải đọc WAL cũ và đồng thời primary vẫn tiếp tục tạo WAL mới.

Nếu standby replay nhanh hơn WAL generation rate, lag sẽ giảm. Nếu tốc độ replay thấp hơn hoặc xấp xỉ tốc độ tạo WAL, standby có thể không bao giờ catch up.

Một budget hợp lý phải xét:

- Thời gian outage.
- Peak WAL generation.
- Network throughput.
- Standby disk read/write throughput.
- Replay CPU.
- Query load trên standby.
- WAL rate tiếp tục phát sinh trong quá trình catch-up.

Slot đủ dung lượng để giữ WAL không có nghĩa standby chắc chắn bắt kịp kịp thời.

## 21. Quan sát streaming replication trên primary

~~~sql
SELECT
    pid,
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

View này chỉ hiển thị các WAL sender connections hiện có. Một slot inactive không xuất hiện như một connection ở đây.

Dùng `application_name` để liên kết replication connection với standby cụ thể.

## 22. Quan sát receive/replay trên standby

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
~~~

Và:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

- Receive LSN cho biết WAL đã nhận.
- Replay LSN cho biết WAL đã áp dụng.
- Khoảng cách giữa chúng có thể phản ánh replay backlog.
- Nếu walreceiver không có row, standby có thể chưa kết nối streaming hoặc đang lấy WAL từ archive.

Timestamp replay có thể cũ khi primary không có transaction mới. So sánh LSN và primary state trước khi kết luận standby bị lag.

## 23. Đo dung lượng thư mục pg_wal

Trên filesystem, kiểm tra dung lượng thực tế của thư mục `pg_wal` bằng công cụ hệ điều hành và giám sát volume.

Có thể quan sát danh sách WAL files qua SQL trên các versions hỗ trợ:

~~~sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)::bigint) AS wal_directory_size
FROM pg_ls_waldir();
~~~

Function `pg_ls_waldir()` cần quyền phù hợp. Kết quả là ảnh chụp thư mục tại thời điểm query.

### 23.1. Đo filesystem vẫn là nguồn chính cho disk capacity

SQL function không thay thế filesystem metrics. Cần theo dõi tổng dung lượng volume, dung lượng còn trống, inode/file count nếu platform có khái niệm inode, I/O latency và disk quota/container ephemeral storage.

## 24. Một query monitoring tổng hợp

Trên primary, dùng query cơ bản tương thích rộng:

~~~sql
SELECT
    s.slot_name,
    s.slot_type,
    s.active,
    s.active_pid,
    s.restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            s.restart_lsn
        )::bigint
    ) AS estimated_wal_distance
FROM pg_replication_slots AS s
WHERE s.slot_type = 'physical'
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    s.restart_lsn
) DESC NULLS LAST;
~~~

Đây là query giám sát read-only. Kết quả cần được đối chiếu với pg_wal directory size, archive status và standby lag.

## 25. Tạo physical replication slot

Có thể tạo slot thủ công:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
~~~

Tên slot phải duy nhất trong cluster. Physical slot được tạo trên primary.

Sau khi tạo, slot có thể giữ WAL ngay cả khi standby chưa kết nối. Vì vậy cần gắn owner, mục đích và lifecycle cho slot ngay lúc tạo.

### 25.1. Đừng tạo slot thử nghiệm rồi quên

Một slot thử nghiệm không có consumer có thể giữ WAL. Dùng tên có quy ước, ghi nhận standby tương ứng và xóa slot khi chắc chắn không còn cần.

## 26. Dùng slot với pg_basebackup

Có thể sử dụng slot khi tạo base backup để WAL cần trong quá trình backup không bị primary recycle quá sớm.

Nếu slot đã được tạo trước:

~~~bash
pg_basebackup -h primary.example -D /var/lib/postgresql/standby -U replicator -X stream -R -S standby_a
~~~

Hoặc yêu cầu pg_basebackup tạo slot:

~~~bash
pg_basebackup -h primary.example -D /var/lib/postgresql/standby -U replicator -X stream -R -C -S standby_a
~~~

- `-R` tạo cấu hình recovery/standby phù hợp cho bản backup.
- `-S` chỉ định replication slot.
- `-C` yêu cầu tạo slot nếu chưa có.

Cần xác minh syntax với pg_basebackup version đang dùng. Role cần quyền replication và primary phải có đủ max_replication_slots/max_wal_senders.

### 26.1. Tên slot trong standby configuration

Khi standby dùng physical slot, cấu hình `primary_slot_name` phải trỏ đúng slot:

~~~text
primary_slot_name = 'standby_a'
~~~

`pg_basebackup -R` có thể ghi cấu hình liên quan theo option/version. Kiểm tra file cấu hình thực tế sau backup.

## 27. max_replication_slots và max_wal_senders

~~~sql
SHOW max_replication_slots;
SHOW max_wal_senders;
~~~

- `max_replication_slots` giới hạn số slots có thể được cấu hình.
- `max_wal_senders` giới hạn số WAL sender processes có thể phục vụ replication connections và một số WAL streaming tasks.

Đặt capacity đủ cho standbys, backup jobs và các consumers được thiết kế. Thay đổi một số setting cần restart PostgreSQL; kiểm tra context của setting trên version thực tế.

Tăng số slot tối đa không tự tạo slots và cũng không giới hạn dung lượng WAL mỗi slot.

## 28. Slot tồn tại sau khi standby disconnect

Khi standby disconnect:

- Replication connection kết thúc.
- Slot vẫn tồn tại.
- `active` chuyển thành false nếu không có consumer khác.
- `restart_lsn` có thể đứng yên.
- Primary tiếp tục tạo WAL.
- WAL segments cần thiết cho slot vẫn được giữ trong phạm vi retention policy.

Đây là tính năng quan trọng cho reconnect, nhưng cũng là nguyên nhân phổ biến của WAL growth.

## 29. Khi slot bị invalidated

Nếu giới hạn WAL slot được cấu hình và slot cần nhiều WAL hơn giới hạn, PostgreSQL có thể recycle WAL cũ cần cho slot tại checkpoint. Slot có thể chuyển sang trạng thái `lost` trên các versions cung cấp `wal_status`.

Khi slot mất WAL cần thiết:

- Standby không thể tiếp tục từ điểm cũ qua streaming WAL.
- Tăng max_slot_wal_keep_size sau đó không khôi phục những segment đã mất.
- Consumer cần một nguồn WAL thay thế đầy đủ hoặc phải được reseed/rebuild.

### 29.1. Có thể phục hồi từ archive không?

Nếu WAL archive có **đầy đủ và liên tục** các segments mà standby còn cần, standby có thể lấy phần thiếu từ archive qua restore_command, rồi tiếp tục streaming khi phù hợp.

Nếu archive thiếu bất kỳ segment bắt buộc nào, phải tạo lại standby từ base backup hợp lệ.

## 30. Phân biệt slot lost và standby chỉ đang disconnected

| Tình trạng | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Slot inactive, WAL còn được giữ | Consumer đang offline nhưng slot có thể vẫn dùng được | Khôi phục connection và theo dõi catch-up |
| Slot unreserved | WAL cần thiết không còn được bảo đảm qua checkpoint tiếp theo | Khẩn trương khôi phục consumer hoặc bổ sung retention/capacity |
| Slot lost | WAL cần thiết đã bị loại bỏ | Archive recovery nếu đủ WAL, nếu không reseed standby |
| Slot active nhưng replay lag cao | Consumer có kết nối nhưng không theo kịp | Điều tra network, disk, replay CPU và query load |

Trạng thái cụ thể phụ thuộc version. Không chỉ nhìn active để quyết định slot có dùng được hay không.

## 31. Drop physical replication slot an toàn

Khi slot không còn cần:

1. Xác định standby/consumer owner.
2. Xác nhận standby đã bị decommission hoặc đã chuyển sang slot khác.
3. Dừng/disconnect consumer nếu còn active.
4. Kiểm tra không có automation sẽ reconnect bằng slot cũ.
5. Drop slot.
6. Theo dõi WAL recycling sau checkpoint và dung lượng filesystem.

Lệnh:

~~~sql
SELECT pg_drop_replication_slot('standby_a');
~~~

PostgreSQL không cho drop một slot đang active. Dừng consumer đúng cách trước.

### 31.1. Drop slot giải phóng WAL ngay lập tức?

Drop slot loại bỏ retention requirement của slot. Các WAL files vẫn có thể cần bởi checkpoint, archive, wal_keep_size hoặc slot khác; filesystem không nhất thiết giảm dung lượng ngay tại thời điểm lệnh chạy.

## 32. Advance slot là thao tác đặc biệt

PostgreSQL có function quản trị `pg_replication_slot_advance` trên các versions hỗ trợ để di chuyển vị trí slot tiến lên.

Advance physical slot có thể làm WAL cũ không còn được giữ cho consumer. Nếu standby vẫn cần đoạn WAL đã bỏ qua, nó sẽ không thể tiếp tục bình thường từ vị trí cũ.

Không dùng advance như thao tác dọn disk thường lệ. Chỉ thực hiện khi đã xác định consumer có thể bỏ qua đoạn WAL đó hoặc sẽ được reseed/rebuild từ nguồn phù hợp.

## 33. Xử lý khi pg_wal tăng nhanh

Khi filesystem chứa `pg_wal` tăng nhanh:

1. Xác định tốc độ tăng và free space.
2. Xem danh sách physical/logical slots.
3. Tìm slot có restart_lsn cũ nhất.
4. Kiểm tra active/inactive và owner.
5. Kiểm tra standby receive/flush/replay lag.
6. Kiểm tra archive failures.
7. Kiểm tra wal_keep_size và slot WAL limit.
8. Kiểm tra backup/replication processes khác.
9. Đánh giá WAL generation workload.
10. Chọn cách giải phóng retention requirement an toàn.

Không bắt đầu bằng việc xóa file trong pg_wal.

## 34. Kịch bản: standby offline lâu ngày

Triệu chứng:

- Slot physical có active=false.
- restart_lsn không thay đổi.
- Primary tạo WAL đều đặn.
- Ước lượng WAL distance tăng.
- pg_wal filesystem tăng dung lượng.

Cách xử lý:

- Xác định standby còn cần phục hồi không.
- Nếu cần, khôi phục network/storage và cho standby reconnect.
- Kiểm tra slot chưa lost và WAL cần thiết còn đủ.
- Theo dõi standby catch-up rate.
- Nếu standby đã bỏ, drop slot sau khi xác nhận.
- Nếu WAL cần thiết đã mất, dùng archive đầy đủ hoặc rebuild.

## 35. Kịch bản: archive command lỗi đồng thời slot inactive

Có thể có hai nguyên nhân cùng giữ WAL:

- Slot giữ WAL từ restart_lsn.
- Archiver thất bại nên WAL segments chưa được archive không thể recycle.

Sửa riêng slot chưa chắc giải phóng toàn bộ WAL. Sửa archive command cũng chưa đủ nếu slot vẫn cần segments cũ.

Theo dõi cả `pg_replication_slots` và `pg_stat_archiver`. Sau khi khôi phục, kiểm tra filesystem growth rate và checkpoint behavior.

## 36. Kịch bản: standby active nhưng vẫn lag

Nếu `active=true` mà lag tiếp tục tăng:

- Kiểm tra network throughput và packet loss.
- Kiểm tra standby disk write latency.
- Kiểm tra replay CPU và I/O.
- Kiểm tra query load trên hot standby.
- Xem recovery conflicts.
- So sánh sent/write/flush/replay LSN.
- Kiểm tra primary WAL generation rate.

Slot không giải quyết vấn đề consumer xử lý chậm. Nó chỉ giữ WAL trong khoảng storage cho phép.

## 37. Khi primary gần hết dung lượng

Ưu tiên hành động theo mức độ an toàn:

**Bước 1 — Xác định nguyên nhân.** Đo filesystem, slot retention, archive backlog, WAL generation rate và disk budget.

**Bước 2 — Tăng capacity nếu có thể.** Mở rộng volume là cách giảm áp lực tức thời mà không làm mất WAL cần thiết.

**Bước 3 — Khôi phục consumer/archive.** Cho standby hoặc archiver tiếp tục tiến triển để WAL cũ trở thành eligible for recycle.

**Bước 4 — Dọn slot thực sự không còn dùng.** Chỉ drop sau khi xác nhận owner và kế hoạch rebuild/retire.

**Bước 5 — Giảm WAL generation nếu cần.** Tạm dừng/bố trí lại batch hoặc workload ghi lớn nếu phù hợp nghiệp vụ.

Không xóa thủ công WAL segments, không drop mọi slot theo kiểu hàng loạt và không tắt fsync để xử lý disk pressure.

## 38. Vì sao xóa WAL file thủ công rất nguy hiểm?

PostgreSQL dùng WAL cho crash recovery, streaming replication, archive recovery/PITR và một số backup/recovery workflows.

Xóa một segment mà primary hoặc consumer còn cần có thể khiến database không khởi động được sau crash, standby không tiếp tục được hoặc PITR bị đứt chuỗi WAL.

WAL lifecycle phải được PostgreSQL quản lý thông qua checkpoint, archive và replication slot APIs. Không xóa file trực tiếp trong pg_wal.

## 39. Disk full ảnh hưởng primary thế nào?

Khi filesystem chứa data directory hoặc pg_wal hết chỗ:

- PostgreSQL có thể không ghi được WAL mới.
- Transaction writes/commits có thể thất bại.
- Checkpoint hoặc archive operations có thể lỗi.
- Server có thể gặp PANIC hoặc dừng nhận writes tùy vị trí I/O thất bại.
- Restart/recovery có thể khó khăn nếu không còn dung lượng làm việc.
- Archive/replication backlog có thể tiếp tục xấu đi.

Đừng đợi filesystem đạt 100% mới alert. Đặt cảnh báo theo free bytes và tốc độ tăng để có thời gian xử lý.

## 40. Monitoring: những tín hiệu nên alert

| Metric | Vì sao quan trọng |
|---|---|
| pg_wal filesystem used/free | Phát hiện disk pressure |
| WAL generation rate | Dự báo thời gian đến giới hạn |
| Slot inactive duration | Phát hiện consumer bị bỏ quên |
| Slot restart_lsn distance | Ước lượng WAL đang bị giữ |
| Slot wal_status | Phát hiện unreserved/lost |
| safe_wal_size | Ước lượng khoảng an toàn còn lại |
| Standby flush/replay lag | Phát hiện consumer không theo kịp |
| Archive failed_count | Phát hiện WAL archive backlog |
| Disk I/O latency | Phát hiện nguyên nhân catch-up chậm |
| Checkpoint activity | Hiểu thời điểm WAL có thể được recycle |

### 40.1. Alert theo dự báo, không chỉ theo phần trăm

Nếu WAL tăng 2 GB mỗi phút và filesystem còn 20 GB, thời gian còn lại có thể chỉ khoảng 10 phút trước khi chạm giới hạn lý thuyết. Cần tính safety margin, burst và các file khác cùng volume.

Một alert hữu ích ước lượng:

~~~text
Time to disk full
    ≈ available disk bytes / net growth bytes per second
~~~

Đây là dự báo gần đúng; growth rate có thể đổi nhanh.

## 41. Ví dụ query cảnh báo slot inactive và retention

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS estimated_wal_distance
FROM pg_replication_slots
WHERE slot_type = 'physical'
  AND NOT active
  AND restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(),
    restart_lsn
) DESC;
~~~

Đây là danh sách cần điều tra, không phải danh sách để tự động drop.

Một slot inactive vài phút có thể là maintenance bình thường. Cần alert theo thời lượng, owner, WAL distance và disk budget.

## 42. Xác định slot owner

Tên slot nên phản ánh standby/consumer. Ví dụ:

| Slot name | Consumer | Owner | Mục đích |
|---|---|---|---|
| `standby_hcm_01` | Standby HCM 01 | DBA on-call | Physical HA |
| `standby_dr_01` | Standby DR | DR team | Disaster recovery |
| `backup_stream_01` | Backup job | Backup service | WAL streaming trong backup |

Duy trì inventory gồm slot name/type, primary/standby pair, application name, owner/team, creation date, retention budget, last active time và retirement procedure.

Không để slot production không rõ chủ sở hữu.

## 43. Lab: tạo physical slot và quan sát

Chỉ thực hiện trên primary lab.

Tạo slot:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('lab_standby_slot');
~~~

Quan sát:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_replication_slots
WHERE slot_name = 'lab_standby_slot';
~~~

Slot có thể inactive ngay sau khi tạo. Nó vẫn tồn tại và có thể bắt đầu giữ WAL cần thiết.

Trong lab, tạo một lượng WAL bằng thao tác ghi dữ liệu lặp lại có kiểm soát, sau đó xem restart_lsn và khoảng cách tới current WAL position.

## 44. Lab: quan sát slot giữ WAL khi standby disconnect

Với primary/standby lab đã cấu hình slot:

1. Xác nhận standby đang streaming.
2. Kiểm tra slot active và restart_lsn.
3. Dừng standby một cách có kiểm soát.
4. Ghi dữ liệu trên primary để sinh WAL.
5. Quan sát slot chuyển inactive.
6. So sánh current WAL LSN với restart_lsn.
7. Khởi động standby lại.
8. Quan sát standby nhận/replay WAL và slot tiến triển.

Mục tiêu là thấy slot tồn tại khi consumer disconnect và retention distance tăng trong thời gian offline.

## 45. Lab: max_slot_wal_keep_size trong môi trường cô lập

Trên một PostgreSQL lab riêng:

1. Cấu hình max_slot_wal_keep_size với một giá trị nhỏ phù hợp lab.
2. Tạo physical slot.
3. Để consumer offline.
4. Tạo WAL đủ lớn để tiến gần giới hạn.
5. Theo dõi wal_status/safe_wal_size nếu version hỗ trợ.
6. Quan sát slot state qua checkpoint.

Không thực hiện trên production. Khi slot mất WAL cần thiết, standby lab có thể phải được rebuild.

### 45.1. Lab phải có disk budget

Dù đang thử giới hạn nhỏ, vẫn đặt giới hạn filesystem cho VM/container. Không tạo workload vô hạn để ép đầy ổ.

## 46. Lab: kiểm tra archive backlog

Trong lab có archive_command:

1. Ghi nhận pg_stat_archiver.
2. Tạm làm archive destination không khả dụng.
3. Sinh WAL.
4. Quan sát failed_count và pg_wal growth.
5. Khôi phục destination.
6. Xác nhận archiver tiến triển và WAL có thể được recycle khi các retention requirements khác cũng được giải phóng.

Không xóa WAL files để làm lab “sạch”.

## 47. Phục hồi standby khi slot lost

Nếu slot lost:

**Trường hợp A — Archive có đủ WAL**

- Giữ nguyên standby.
- Xác minh chuỗi archive liên tục từ vị trí standby cần.
- Cấu hình restore_command phù hợp.
- Cho standby lấy WAL bị thiếu từ archive.
- Sau đó xác nhận streaming replication có thể tiếp tục.

**Trường hợp B — Archive không đủ WAL**

- Standby không thể redo qua gap.
- Tạo base backup mới từ primary phù hợp.
- Rebuild data directory standby theo quy trình.
- Tạo/sử dụng slot mới.
- Xác nhận replication và monitoring sau rebuild.

Không cố ép standby tiếp tục bằng cách sửa restart_lsn hoặc tạo file WAL giả.

## 48. Rebuild standby và slot lifecycle

Một quy trình rebuild:

1. Xác định primary hiện tại và timeline.
2. Xác nhận standby cũ không còn là primary/không nhận writes.
3. Lưu logs/diagnostics cần thiết.
4. Chuẩn bị data directory standby mới.
5. Tạo slot mới hoặc xác minh slot cũ có thể dùng.
6. Chạy pg_basebackup với slot và cấu hình recovery.
7. Khởi động standby.
8. Kiểm tra pg_is_in_recovery và WAL receiver.
9. Xác minh replay LSN tiến.
10. Xóa slot cũ chỉ sau khi xác nhận không consumer nào cần.

Rebuild có thể tốn thời gian, network và disk; lên kế hoạch capacity trước.

## 49. Failover và replication slots

Physical slot được lưu trên primary tạo ra nó. Không nên mặc định rằng khi promote một standby thành primary, mọi slots trên primary cũ sẽ tự xuất hiện và tiếp tục chính xác trên node mới.

Các PostgreSQL versions mới có thêm khả năng đồng bộ failover slots trong những topology/cấu hình nhất định, nhưng đây là tính năng version-specific cần cấu hình và kiểm chứng riêng.

Sau failover:

- Xác định primary mới.
- Kiểm tra slot inventory trên primary mới.
- Xác minh standby còn lại có slot phù hợp.
- Nếu không có state slot hợp lệ, dùng archive hoặc reseed/rebuild theo playbook.
- Không để consumer tiếp tục kết nối nhầm primary cũ.

## 50. Physical slot và hot_standby_feedback

`hot_standby_feedback` là cơ chế standby gửi snapshot horizon về primary để giảm recovery conflicts. Nó liên quan đến tuple retention/cleanup horizon, không đồng nghĩa với WAL retention qua restart_lsn.

~~~sql
SHOW hot_standby_feedback;
~~~

Một standby có thể vừa sử dụng physical slot để giữ WAL, vừa bật hot_standby_feedback để giảm query cancellation. Khi đó có hai tác động cần giám sát riêng:

- Slot giữ WAL segments.
- Feedback có thể giữ dead tuples trên primary.

Không gộp hai rủi ro này thành một metric disk duy nhất.

## 51. Các tham số và view cần nhớ

| Thành phần | Vai trò |
|---|---|
| `max_replication_slots` | Số slot tối đa |
| `max_wal_senders` | Số WAL sender processes tối đa |
| `max_slot_wal_keep_size` | Giới hạn WAL giữ bởi replication slots |
| `wal_keep_size` | WAL retention tối thiểu |
| `max_wal_size` | Ngưỡng checkpoint mềm |
| `archive_mode` | Bật WAL archiving |
| `archive_command` | Lưu WAL segment vào archive |
| `pg_replication_slots` | Slot inventory và restart LSN |
| `pg_stat_replication` | WAL sender/standby progress |
| `pg_stat_wal_receiver` | WAL receiver state trên standby |
| `pg_stat_archiver` | Archive success/failure statistics |
| `pg_stat_wal` | WAL generation/write/sync statistics |

Tham số cần reload hay restart phụ thuộc setting context. Kiểm tra `pg_settings.context` và tài liệu đúng major version trước khi thay đổi.

## 52. Troubleshooting: pg_wal tăng dù max_wal_size thấp

Nguyên nhân có thể:

- Replication slot giữ WAL cũ.
- Archive command thất bại.
- wal_keep_size giữ thêm WAL.
- Standby không tiến triển.
- Checkpoint không hoàn tất hoặc workload tạo WAL cao.
- Một consumer/backup workflow còn cần WAL.

Cách điều tra:

1. Xem pg_replication_slots.
2. Tính WAL distance theo restart_lsn.
3. Xem pg_stat_archiver.
4. Kiểm tra filesystem và WAL rate.
5. Xem checkpoint/replication activity.
6. Xác định retention requirement nào đang giữ segments.

Không giả định max_wal_size là hard cap.

## 53. Troubleshooting: slot active nhưng restart_lsn không tiến

Kiểm tra:

- Standby có nhận WAL không?
- Flush LSN có tiến không?
- Replication connection có wait events?
- Network có gián đoạn?
- Standby có disk full/read-only filesystem?
- Slot có thực sự được connection đó sử dụng?
- Consumer có đang bị pause hoặc replay backlog?

So sánh primary sent/write/flush/replay LSN với standby receive/replay LSN. Active chỉ nói process đang dùng slot, không bảo đảm tiến độ đang tốt.

## 54. Troubleshooting: slot inactive nhưng không rõ owner

Không drop ngay.

- Xem tên slot và naming convention.
- Tìm inventory/config của standbys.
- Kiểm tra application_name/replication connection history trong logs.
- Đối chiếu owner team theo quy trình vận hành.
- Kiểm tra backup/DR workflow.
- Xác nhận slot không còn được cấu hình trong primary_slot_name.

Nếu chưa xác định owner, đánh dấu cần điều tra và đo retention impact; không xóa dựa trên suy đoán.

## 55. Troubleshooting: slot lost sau checkpoint

Nếu `wal_status` là lost:

- Slot không còn bảo đảm cung cấp WAL cần thiết.
- Kiểm tra archive có đủ segment gap không.
- Nếu đủ, thử phục hồi standby qua archive theo quy trình.
- Nếu thiếu, rebuild standby.
- Tăng/điều chỉnh budget cho lần sau.
- Alert trước khi safe_wal_size cạn.

Không advance slot hoặc tạo slot mới rồi cho standby cũ dùng tiếp mà chưa có một base state/WAL continuity phù hợp.

## 56. Best practices

- Mỗi physical slot phải có consumer và owner rõ ràng.
- Đặt max_slot_wal_keep_size dựa trên peak WAL rate và outage objective.
- Theo dõi restart_lsn distance và slot inactivity.
- Theo dõi pg_wal filesystem free space độc lập.
- Theo dõi archive failures.
- Đảm bảo archive có đủ WAL để phục hồi khi slot bị invalidated.
- Dùng pg_basebackup/physical backup đúng quy trình.
- Kiểm tra slot inventory sau failover.
- Xóa slot chỉ sau khi consumer được retire hoặc chuyển đổi.
- Không xóa WAL files thủ công.
- Thử nghiệm slot loss/rebuild trong lab.
- Đo thời gian standby catch-up và rebuild để lập RTO.

## 57. Checklist khi vận hành replication slot

**Trước khi tạo**

1. Slot phục vụ standby nào?
2. Primary/standby timeline và versions tương thích?
3. max_replication_slots còn capacity?
4. Disk budget đủ cho outage/catch-up?
5. WAL archive có hoạt động?
6. Có owner và alert?

**Trong khi hoạt động**

7. Slot active đúng lúc?
8. restart_lsn có tiến?
9. WAL distance có nằm trong budget?
10. safe_wal_size/wal_status có cảnh báo?
11. Standby flush/replay lag có giảm?
12. pg_wal free space có đủ?
13. Archive failed_count có tăng?

**Khi standby offline**

14. Outage có nằm trong retention objective?
15. WAL generation rate có tăng đột biến?
16. Slot có gần giới hạn?
17. Có thể mở rộng storage hoặc khôi phục consumer?
18. Slot còn usable sau checkpoint?

**Khi retire/rebuild**

19. Owner xác nhận consumer không còn dùng slot?
20. Standby đã chuyển slot hoặc được rebuild?
21. Có archive/WAL path thay thế?
22. Drop slot có thể giải phóng retention requirement?
23. Đã kiểm tra sau checkpoint và theo dõi filesystem?

## 58. Bài tập thực hành

### Bài 1 — Replication slot

Replication slot là gì?

**Gợi ý:** state bền vững để giữ tài nguyên cần cho consumer.

### Bài 2 — Physical slot

Physical slot bảo vệ điều gì cho standby?

**Gợi ý:** WAL segments cần để tiếp tục streaming.

### Bài 3 — restart_lsn

restart_lsn biểu thị gì?

**Gợi ý:** WAL position cũ nhất slot còn có thể cần.

### Bài 4 — Inactive slot

Slot active=false có còn giữ WAL không?

**Gợi ý:** có, slot vẫn tồn tại.

### Bài 5 — Slot vs connection

Replication slot có biến mất khi connection disconnect không?

**Gợi ý:** không.

### Bài 6 — Physical vs logical

Nêu khác biệt tài nguyên chính giữa hai loại slot.

**Gợi ý:** physical giữ WAL; logical còn có transaction/catalog horizons.

### Bài 7 — wal_keep_size

Tham số này làm gì?

**Gợi ý:** giữ tối thiểu một lượng WAL cho standby.

### Bài 8 — max_slot_wal_keep_size

Tham số này giới hạn gì?

**Gợi ý:** WAL retention do replication slots.

### Bài 9 — max_wal_size

Có phải hard cap của pg_wal không?

**Gợi ý:** không, là checkpoint threshold mềm.

### Bài 10 — Archive backlog

archive_command thất bại có thể làm gì?

**Gợi ý:** WAL chưa archive tiếp tục được giữ, pg_wal tăng.

### Bài 11 — WAL rate

Cách tính WAL generation rate từ pg_stat_wal?

**Gợi ý:** delta wal_bytes chia delta time.

### Bài 12 — Retention budget

Nêu các yếu tố trong công thức sizing slot.

**Gợi ý:** peak WAL rate, outage, catch-up, safety margin.

### Bài 13 — Catch-up

Vì sao giữ đủ WAL chưa bảo đảm standby bắt kịp?

**Gợi ý:** replay throughput phải lớn hơn WAL generation rate.

### Bài 14 — pg_replication_slots

View này quan sát những gì?

**Gợi ý:** slot name/type/active/restart_lsn/status.

### Bài 15 — pg_stat_replication

View này có hiển thị slot inactive như connection không?

**Gợi ý:** không, chỉ các WAL sender connections hiện có.

### Bài 16 — Receive vs replay

Phân biệt receive LSN và replay LSN.

**Gợi ý:** WAL nhận được vs WAL đã áp dụng.

### Bài 17 — wal_status

lost có ý nghĩa gì?

**Gợi ý:** WAL cần thiết đã bị mất, slot không còn usable.

### Bài 18 — safe_wal_size

Nó giúp dự báo điều gì?

**Gợi ý:** dung lượng WAL còn có thể sinh trước khi slot có nguy cơ invalidation.

### Bài 19 — Tạo slot

Viết SQL tạo physical replication slot.

**Gợi ý:** pg_create_physical_replication_slot.

### Bài 20 — Drop slot

Viết SQL xóa slot đã xác nhận không còn dùng.

**Gợi ý:** pg_drop_replication_slot.

### Bài 21 — Active drop

Có thể drop slot đang active không?

**Gợi ý:** cần dừng/disconnect consumer trước.

### Bài 22 — pg_basebackup

Option -S chỉ định gì?

**Gợi ý:** replication slot.

### Bài 23 — pg_basebackup -C

Option này làm gì khi dùng với -S?

**Gợi ý:** yêu cầu tạo slot nếu chưa có.

### Bài 24 — primary_slot_name

Standby setting này dùng để làm gì?

**Gợi ý:** chọn physical slot trên primary.

### Bài 25 — max_replication_slots

Tăng setting này có tự giới hạn WAL retention không?

**Gợi ý:** không, chỉ tăng số slot capacity.

### Bài 26 — Disk usage

Function SQL nào liệt kê WAL directory trên versions hỗ trợ?

**Gợi ý:** pg_ls_waldir.

### Bài 27 — WAL distance

Viết expression tính bytes từ current WAL LSN tới restart_lsn.

**Gợi ý:** pg_wal_lsn_diff.

### Bài 28 — Slot inactive lâu

Nêu ba nguyên nhân thường gặp.

**Gợi ý:** standby offline, decommission, network failure.

### Bài 29 — Slot invalidation

Tăng max_slot_wal_keep_size sau khi slot lost có khôi phục WAL không?

**Gợi ý:** không.

### Bài 30 — Archive fallback

Khi slot lost, điều kiện nào cho phép standby lấy WAL từ archive?

**Gợi ý:** archive có đủ WAL liên tục từ vị trí cần.

### Bài 31 — Rebuild

Khi archive thiếu WAL cần thiết, hướng xử lý là gì?

**Gợi ý:** tạo base backup/reseed standby.

### Bài 32 — Disk full

Vì sao không xóa pg_wal files bằng filesystem command?

**Gợi ý:** phá crash recovery/replication/PITR.

### Bài 33 — max_wal_size

Vì sao pg_wal có thể vượt max_wal_size?

**Gợi ý:** slots, archiver, wal_keep_size và retention khác.

### Bài 34 — WAL generation burst

Vì sao sizing theo average rate có thể nguy hiểm?

**Gợi ý:** bulk workload có peak cao.

### Bài 35 — Slot owner

Vì sao cần inventory owner cho từng slot?

**Gợi ý:** tránh drop nhầm hoặc bỏ quên retention.

### Bài 36 — Failover

Slot trên primary cũ có tự xuất hiện trên primary mới không?

**Gợi ý:** không mặc định; phụ thuộc version/cấu hình failover slot.

### Bài 37 — hot_standby_feedback

Nó giữ loại tài nguyên nào khác WAL retention?

**Gợi ý:** tuple versions/cleanup horizon.

### Bài 38 — Monitoring

Nêu ít nhất năm metrics để alert.

**Gợi ý:** disk free, WAL rate, inactive duration, restart distance, safe_wal_size, archive failures, replay lag.

### Bài 39 — Incident response

Primary gần đầy disk do inactive slot. Nêu thứ tự xử lý.

**Gợi ý:** xác định nguyên nhân/owner, mở rộng capacity, khôi phục consumer hoặc retire slot an toàn, không xóa file.

### Bài 40 — Thiết kế retention

Một primary tạo 0,5 GB WAL/phút, cần chịu outage 40 phút, catch-up buffer 8 GB và safety margin 20%. Tính budget minh họa.

**Gợi ý:** (0,5 × 40 + 8) × 1,2 = 33,6 GB.

## 59. Câu hỏi thường gặp

### Replication slot có lưu WAL riêng không?

Không. Nó lưu state/horizon để PostgreSQL giữ các WAL segments trong pg_wal khi còn cần.

### Slot inactive có tự bị xóa không?

Thông thường không. Slot tồn tại cho tới khi được drop hoặc bị xử lý theo cơ chế/version-specific policy.

### Vì sao pg_wal tăng dù không có standby đang kết nối?

Một slot inactive có thể giữ WAL từ restart_lsn cũ. Archive failure hoặc wal_keep_size cũng có thể giữ WAL.

### max_wal_size có giới hạn pg_wal tuyệt đối không?

Không. Đây là ngưỡng checkpoint mềm; replication slots và archive backlog có thể khiến thư mục lớn hơn.

### wal_keep_size có thay thế replication slot không?

Không. Nó giữ tối thiểu một lượng WAL chung; slot cung cấp retention state riêng cho consumer.

### max_slot_wal_keep_size có an toàn tuyệt đối cho disk không?

Không. Nó giúp giới hạn slot retention theo checkpoint policy, nhưng archive backlog và các yếu tố khác vẫn có thể giữ WAL. Cần theo dõi filesystem.

### Nếu slot lost thì tăng giới hạn có cứu được không?

Không. WAL segments đã recycle không tự xuất hiện lại. Dùng archive đầy đủ hoặc rebuild standby.

### Có thể drop slot inactive để giải phóng disk không?

Chỉ sau khi xác nhận consumer không còn cần nó. Drop slot có thể làm standby mất khả năng tiếp tục từ WAL position cũ.

### Drop slot có làm pg_wal nhỏ ngay không?

Không nhất thiết. WAL còn có thể cần cho archive, checkpoint, wal_keep_size hoặc slots khác. Recycle xảy ra theo PostgreSQL lifecycle.

### Có nên advance slot khi disk gần đầy?

Không như một biện pháp chữa cháy chung. Advance có thể bỏ qua WAL mà standby cần; chỉ dùng khi có kế hoạch consumer rõ ràng.

### Làm sao biết slot nào giữ nhiều WAL nhất?

So sánh current WAL LSN với restart_lsn qua pg_wal_lsn_diff; kết quả là ước lượng WAL distance, không phải dung lượng độc quyền chính xác.

### Physical slot có giữ dead tuples như logical slot không?

Mục tiêu chính của physical slot là giữ WAL. Tuple retention do hot_standby_feedback và các xmin horizons là một vấn đề khác cần theo dõi riêng.

### Có thể chỉ dùng WAL archive mà không dùng physical slot không?

Có thể trong một số topology nếu standby có thể lấy mọi WAL cần từ archive và retention/restore command được thiết kế phù hợp. Cần đảm bảo archive liên tục và đủ capacity.

### Khi nào phải rebuild standby?

Khi standby thiếu WAL cần thiết và không có archive đầy đủ để lấp gap, cần tạo lại standby từ base backup phù hợp.

## 60. Tổng kết

Các lệnh quan sát quan trọng:

~~~sql
-- Slot inventory trên primary.
SELECT
    slot_name,
    slot_type,
    active,
    active_pid,
    restart_lsn
FROM pg_replication_slots;

-- Ước lượng WAL distance theo physical slot.
SELECT
    slot_name,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS wal_distance
FROM pg_replication_slots
WHERE slot_type = 'physical'
  AND restart_lsn IS NOT NULL;

-- Primary replication connections.
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;

-- Standby receive/replay.
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();

-- Archive status.
SELECT * FROM pg_stat_archiver;

-- WAL generation statistics.
SELECT wal_bytes, stats_reset
FROM pg_stat_wal;

-- Relevant settings.
SHOW max_replication_slots;
SHOW max_wal_senders;
SHOW max_slot_wal_keep_size;
SHOW wal_keep_size;
SHOW max_wal_size;
SHOW archive_mode;
SHOW archive_command;
~~~

Những nguyên tắc cần nhớ:

1. **Physical replication slot giữ WAL mà standby có thể còn cần**, dựa trên restart_lsn.
2. Slot là state retention, không phải bản sao WAL độc lập.
3. Slot inactive vẫn tồn tại và có thể giữ WAL.
4. restart_lsn khác receive/replay/flush LSN.
5. max_slot_wal_keep_size giới hạn WAL retention do slots theo checkpoint policy.
6. wal_keep_size giữ WAL tối thiểu; max_wal_size là checkpoint threshold mềm, không phải hard cap.
7. Archive failure cũng có thể làm pg_wal tăng.
8. Dùng pg_replication_slots, pg_stat_replication, pg_stat_archiver, pg_stat_wal và filesystem metrics để tìm nguyên nhân.
9. Ước lượng retention budget bằng peak WAL rate × outage time, cộng catch-up và safety margin.
10. Catch-up capacity phải lớn hơn WAL generation rate để lag giảm.
11. safe_wal_size/wal_status hữu ích trên các versions hỗ trợ.
12. Slot lost không được khôi phục chỉ bằng cách tăng giới hạn sau đó.
13. Nếu archive đủ WAL, standby có thể phục hồi phần thiếu; nếu không, rebuild từ base backup.
14. Drop slot chỉ sau khi xác nhận consumer đã retire/chuyển đổi.
15. Advance slot có thể khiến standby bỏ lỡ WAL; không dùng như dọn disk thông thường.
16. Không xóa WAL files thủ công.
17. Theo dõi disk free space, WAL growth rate và time-to-full trước khi filesystem cạn.
18. Kiểm tra slot inventory sau failover; không mặc định slot tự chuyển sang primary mới.
19. Tách riêng WAL retention với tuple retention do hot_standby_feedback.
20. Restore/rebuild tests chứng minh standby có thể phục hồi theo kế hoạch.

Sơ đồ xử lý:

~~~text
pg_wal tăng nhanh / disk pressure
              |
              v
     Kiểm tra filesystem + WAL rate
              |
              v
     Kiểm tra pg_replication_slots
              |
              +--> Slot inactive / restart_lsn cũ?
              |          |
              |          v
              |     Xác định owner/consumer
              |          |
              |          +--> Consumer còn cần?
              |          |       |
              |          |       v
              |          |   Khôi phục standby
              |          |
              |          +--> Đã retire?
              |                  |
              |                  v
              |              Drop slot an toàn
              |
              +--> Kiểm tra archive failures
              |
              +--> Kiểm tra wal_keep_size / checkpoint
              |
              v
       Theo dõi WAL recycling và free space
~~~

**Kết luận:** Replication slot giúp physical standby có thể tiếp tục từ WAL đã giữ khi mất kết nối, nhưng slot inactive hoặc consumer chậm có thể làm primary giữ WAL cho tới khi filesystem cạn. Vận hành an toàn cần **đặt giới hạn slot phù hợp, đo WAL generation rate, theo dõi restart_lsn và safe_wal_size, giám sát archive cùng disk capacity, và có playbook rebuild standby khi WAL đã mất**. Không xóa thủ công các WAL files để giải phóng dung lượng.
