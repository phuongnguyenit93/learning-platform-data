# Recovery target theo thời gian, LSN hoặc restore point trong PostgreSQL

## 1. Recovery target là gì?

Point-in-Time Recovery (PITR) cho phép PostgreSQL khôi phục một cluster từ physical base backup rồi phát lại Write-Ahead Log (WAL) đến một điểm được chọn trong lịch sử. Recovery target xác định nơi quá trình replay WAL phải dừng.

PostgreSQL hỗ trợ ba cách chỉ định điểm dừng thường dùng:

- **Theo thời gian:** đặt recovery_target_time bằng timestamp.
- **Theo LSN:** đặt recovery_target_lsn bằng vị trí trong WAL.
- **Theo restore point:** đặt recovery_target_name bằng tên marker đã được ghi vào WAL bởi pg_create_restore_point().

Ba cách này mô tả cùng một mục tiêu ở các góc nhìn khác nhau. Timestamp dễ hiểu với người vận hành; LSN là vị trí WAL cụ thể; restore point là marker có tên được tạo trước một hoạt động quan trọng.

Recovery target không phải một bản backup. Nó chỉ cho PostgreSQL biết cần dừng replay ở đâu. Để PITR thành công, vẫn cần base backup hợp lệ, WAL liên tục và restore configuration đúng.

```text
             Physical base backup
                      |
                      v
               Restore PGDATA
                      |
                      v
             Read archived WAL
                      |
                      v
              Replay WAL records
                      |
                      v
             Recovery target reached?
                 /           \
               No             Yes
               |               |
               v               v
          Replay next       Apply target action
          WAL segment       pause / promote / shutdown
                               |
                               v
                        Validate recovered data
                               |
                               v
                         Promote / cut over
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của recovery target trong PITR.
2. Phân biệt recovery target theo timestamp, LSN và restore point.
3. Hiểu giới hạn của recovery theo thời gian và transaction commit timestamps.
4. Đọc và ghi LSN theo định dạng PostgreSQL.
5. Tạo named restore point bằng pg_create_restore_point().
6. Lưu marker và LSN để sử dụng trong incident recovery.
7. Hiểu recovery_target_inclusive.
8. Chọn recovery_target_action phù hợp với quy trình xác minh.
9. Chọn timeline khi khôi phục từ backup có lịch sử failover.
10. Cấu hình restore_command và WAL archive.
11. Sử dụng recovery.signal trên PostgreSQL 12 trở lên.
12. Phân biệt archive recovery với standby mode.
13. Thực hiện recovery vào thời điểm trước một thao tác lỗi.
14. Kiểm tra recovery progress và điểm replay cuối cùng.
15. Phân biệt last replay timestamp với recovery target thực tế.
16. Điều tra target không đạt được do thiếu WAL hoặc sai timeline.
17. Lập quy trình PITR trong môi trường tách biệt.
18. Bảo vệ base backup, WAL archive và restore point metadata.
19. Kiểm tra khả năng khôi phục bằng restore drills.
20. Xây runbook lựa chọn và xác minh recovery target.

## 3. PITR cần base backup và WAL liên tục

### 3.1. Base backup tạo điểm bắt đầu

Base backup là bản sao vật lý của PostgreSQL cluster được tạo bằng phương pháp hỗ trợ, ví dụ pg_basebackup hoặc một công cụ physical backup tương thích. Khi restore, PostgreSQL có data files làm nền tảng để bắt đầu recovery.

Base backup không chứa mọi thay đổi phát sinh sau thời điểm backup kết thúc. Những thay đổi đó được ghi trong WAL.

### 3.2. WAL đưa cluster tiến đến recovery target

WAL chứa các records mô tả thay đổi cần thiết để PostgreSQL khôi phục trạng thái database. Trong archive recovery, PostgreSQL lấy WAL từ archive bằng restore_command và replay theo thứ tự.

Muốn phục hồi đến target, cần có đủ WAL từ điểm cần thiết của base backup đến vị trí chứa target.

### 3.3. Một segment bị thiếu có thể phá PITR

Nếu WAL archive bị thiếu một segment cần thiết, PostgreSQL không thể replay vượt qua khoảng trống đó. Một recovery target nằm sau segment bị thiếu có thể không đạt được.

Monitoring cần theo dõi:

- Archive command failures.
- WAL segments chưa được upload.
- Archive backlog.
- Segment bị thiếu hoặc checksum không khớp.
- Retention có xóa WAL còn cần cho base backup hay không.
- Timeline history files có được lưu đầy đủ hay không.

### 3.4. Base backup và WAL phải thuộc cùng lịch sử

Không ghép tùy tiện một base backup với WAL từ cluster khác, timeline không liên quan hoặc repository không có metadata phù hợp. Cần biết backup identity, timeline, WAL start/end và tool version.

### 3.5. Recovery target chỉ có ý nghĩa trong archive recovery

Các cấu hình recovery_target_* được dùng khi PostgreSQL đang thực hiện archive recovery. Trên PostgreSQL 12 trở lên, file recovery.signal yêu cầu server bắt đầu archive recovery. File standby.signal phục vụ standby mode liên tục và có semantics khác.

Không cấu hình một target PITR rồi giả định standby sẽ tự dừng theo target đó trong mọi chế độ.

## 4. Ba loại recovery target

### 4.1. Target theo thời gian

recovery_target_time chọn mốc bằng timestamp.

Ví dụ:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_time = '2026-11-14 10:32:00+07'
recovery_target_action = 'pause'
```

Timestamp có timezone rõ ràng giúp tránh nhầm lẫn giữa UTC, giờ địa phương và timezone của máy chủ.

### 4.2. Target theo LSN

recovery_target_lsn chọn một vị trí WAL cụ thể:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_lsn = '0/16B6C50'
recovery_target_action = 'pause'
```

LSN biểu diễn vị trí trong WAL, không phải timestamp. Nó phù hợp khi một hệ thống khác đã ghi nhận chính xác vị trí WAL liên quan đến sự kiện cần phục hồi.

### 4.3. Target theo restore point

recovery_target_name chọn một named restore point:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_name = 'before_release_2026_11_14'
recovery_target_action = 'pause'
```

Tên này phải khớp với marker đã được tạo trước đó và marker phải có trong WAL archive cần replay.

### 4.4. Chỉ chọn một target chính

Các recovery target chính gồm time, XID, LSN và name. Không cấu hình nhiều target chính với kỳ vọng PostgreSQL sẽ chọn target gần nhất hoặc kết hợp chúng. Chọn một tiêu chí cho mỗi lần recovery; recovery_target_timeline và recovery_target_action là các thiết lập bổ sung có mục đích riêng.

### 4.5. So sánh nhanh

| Tiêu chí | Time | LSN | Restore point |
| --- | --- | --- | --- |
| Cách chỉ định | Timestamp | WAL location | Tên marker |
| Dễ hiểu với người vận hành | Cao | Trung bình/thấp | Cao |
| Cần ghi nhận trước sự cố | Không bắt buộc, nhưng cần timestamp chính xác | Thường cần LSN từ logs/metrics | Có, phải tạo marker |
| Độ chính xác | Theo transaction commit time trong WAL | Theo WAL position | Theo marker trong WAL |
| Dùng tốt khi | Biết thời điểm lỗi | Biết vị trí WAL | Có mốc trước/sau thay đổi |
| Rủi ro thường gặp | Sai timezone/commit boundary | Nhầm LSN hoặc timeline | Marker chưa được archive hoặc tên trùng |

## 5. Recovery target theo thời gian

### 5.1. Timestamp cần timezone rõ ràng

Nên dùng timestamp ISO 8601 có UTC offset:

```conf
recovery_target_time = '2026-11-14 10:32:00+07'
```

Có thể dùng UTC:

```conf
recovery_target_time = '2026-11-14 03:32:00+00'
```

Hai giá trị trên đại diện cùng một thời điểm. Không dựa vào timezone mặc định của shell, laptop hoặc người trực sự cố.

### 5.2. Recovery không dừng ở một nanosecond tùy ý

PostgreSQL replay WAL theo records và transaction boundaries. Recovery theo time dừng khi gặp transaction commit record có timestamp đáp ứng target theo semantics của recovery_target_time và recovery_target_inclusive.

Vì thế target time không có nghĩa mọi thay đổi vật lý được chụp chính xác tại từng microsecond của đồng hồ. Nó chọn trạng thái transaction phù hợp với commit records trong WAL.

### 5.3. Chọn trước hay sau một transaction

Giả sử một transaction lỗi commit lúc 10:32:04. Bạn muốn phục hồi trạng thái trước transaction đó. Có thể đặt target ngay trước thời điểm commit và dùng semantics loại trừ phù hợp. Tuy nhiên, phải xác minh timestamp thực tế của commit trong logs/audit và thử trên một cluster tạm.

Không lấy thời điểm người dùng nhấn nút trong UI làm commit timestamp của database. Request có thể vào queue, retry, chạy nhiều transactions hoặc commit muộn hơn.

### 5.4. recovery_target_inclusive

recovery_target_inclusive điều khiển việc transaction tại recovery boundary được bao gồm hay loại trừ đối với các target áp dụng như time, XID và LSN.

- true: dừng sau target theo semantics bao gồm transaction tại boundary.
- false: dừng trước transaction tại boundary theo semantics loại trừ.

Mặc định thường là true. Khi mục tiêu là quay về trước transaction lỗi, cần xác định rõ boundary và kiểm tra kết quả. Không chỉ đổi giá trị theo cảm tính.

Ví dụ:

```conf
recovery_target_time = '2026-11-14 10:32:04+07'
recovery_target_inclusive = false
recovery_target_action = 'pause'
```

Đây là cấu hình minh họa. Chọn timestamp và inclusive flag sau khi đã xác định commit record cần loại trừ.

### 5.5. Transaction commit timestamp có thể không trùng log ứng dụng

Ứng dụng thường ghi request time, event time hoặc thời gian bắt đầu xử lý. PostgreSQL recovery target theo thời gian dựa trên timestamp commit trong WAL. Clock skew, timezone, queueing và transaction duration có thể tạo độ lệch.

Khi cần độ chính xác cao, dùng audit records, database logs, LSN marker hoặc restore point có chủ đích.

### 5.6. Khi nào time target phù hợp?

- Sự cố được ghi nhận với timestamp đáng tin cậy.
- Có log commit hoặc audit time rõ.
- Không có LSN/restore point đã ghi lại.
- Cần khôi phục theo mốc thời gian business dễ diễn giải.

## 6. LSN là gì?

LSN (Log Sequence Number) là địa chỉ trong WAL. PostgreSQL biểu diễn LSN dưới dạng hai số hexadecimal cách nhau bởi dấu /.

Ví dụ:

```text
0/16B6C50
2/AF002D8
17/4A000120
```

LSN tăng theo WAL position, nhưng không phải đồng hồ và không nên tự diễn giải thành thời gian.

### 6.1. LSN không phải transaction ID

Transaction ID (XID) xác định transaction trong cơ chế MVCC. LSN xác định vị trí WAL. Một transaction có nhiều WAL records; LSN và XID có quan hệ qua WAL contents nhưng là hai không gian định danh khác nhau.

### 6.2. Xem WAL LSN hiện tại trên primary

```sql
SELECT
    pg_current_wal_lsn() AS current_wal_lsn,
    pg_current_wal_insert_lsn() AS current_insert_lsn,
    pg_current_wal_flush_lsn() AS current_flush_lsn;
```

Các hàm cụ thể phụ thuộc phiên bản và trạng thái server. Các giá trị này mô tả vị trí WAL tại thời điểm gọi; chúng không tự động chỉ ra transaction business nào cần rollback.

### 6.3. Xem replay LSN trên standby/recovery server

```sql
SELECT
    pg_is_in_recovery() AS is_in_recovery,
    pg_last_wal_replay_lsn() AS last_replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_commit_time;
```

pg_last_wal_replay_lsn() cho biết vị trí replay cuối cùng được báo cáo. pg_last_xact_replay_timestamp() cho biết thời gian commit của transaction replay gần nhất, không phải đồng hồ hiện tại và không nhất thiết bằng recovery target.

### 6.4. So sánh hai LSN

Có thể dùng pg_wal_lsn_diff() để tính khoảng cách byte giữa hai LSN:

```sql
SELECT pg_wal_lsn_diff('0/16B6C50', '0/16B6000') AS wal_bytes;
```

Hàm này hữu ích để phân tích khoảng cách WAL, không phải thời lượng giữa hai sự kiện.

### 6.5. Vì sao LSN target chính xác?

LSN có thể chỉ định một vị trí WAL cụ thể, hữu ích khi một marker hoặc hệ thống audit đã lưu đúng WAL location. Nó tránh phụ thuộc vào cách chuyển đổi timezone/timestamp.

Tuy vậy, chọn LSN sai vẫn có thể đưa database đến trạng thái không mong muốn. Cần biết LSN thuộc cluster/timeline nào và sự kiện nào đã xảy ra trước/sau vị trí đó.

## 7. Ghi nhận LSN cho một sự kiện quan trọng

### 7.1. Dùng restore point để tạo marker có LSN

Một cách thuận tiện là tạo restore point trước thao tác quan trọng:

```sql
SELECT pg_create_restore_point(
    'before_release_2026_11_14'
) AS restore_lsn;
```

Hàm trả về LSN của restore point trong WAL. Lưu cả tên marker và LSN vào change ticket hoặc backup catalog.

### 7.2. Đặt marker trước thay đổi

Ví dụ trước một migration có rủi ro:

1. Xác nhận WAL archiving hoạt động.
2. Tạo restore point với tên duy nhất.
3. Ghi lại LSN trả về và timestamp.
4. Chờ WAL segment chứa marker được archive và xác minh artifact.
5. Thực hiện migration.
6. Nếu migration gây lỗi logic, restore base backup rồi replay đến marker trước migration.

### 7.3. Quyền thực thi

pg_create_restore_point() là thao tác quản trị nhạy cảm và cần quyền phù hợp, thường là superuser. Không cấp quyền superuser cho role ứng dụng chỉ để tạo marker.

### 7.4. Marker phải tồn tại trong WAL archive

Ghi restore point vào WAL không đồng nghĩa archive segment đã được upload xong. Chỉ coi marker có thể dùng để PITR khi WAL segment chứa marker và các segment trước đó cần thiết đã được lưu, kiểm tra và còn trong retention.

Có thể dùng pg_switch_wal() để yêu cầu chuyển sang WAL segment mới khi phù hợp, sau đó xác minh archive. Việc switch không thay cho kiểm tra archive success.

### 7.5. Tên restore point nên duy nhất

Dùng tên thể hiện hệ thống, sự kiện và thời điểm, ví dụ:

```text
before_schema_migration_20261114_103000
before_bulk_import_orders_20261114_153000
before_release_payments_v42_20261114
```

Không tái sử dụng một tên chung như before_release liên tục. Khi tên bị trùng, recovery có thể gặp marker cùng tên ở vị trí khác trong WAL history và dừng ở marker đầu tiên phù hợp.

## 8. Recovery target theo restore point

### 8.1. Tạo restore point

```sql
SELECT pg_create_restore_point('before_bad_migration') AS restore_lsn;
```

Lưu kết quả LSN, timestamp, database/cluster identity và ticket của thay đổi.

### 8.2. Cấu hình target name

Trong môi trường restore:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_name = 'before_bad_migration'
recovery_target_action = 'pause'
```

### 8.3. Marker là một WAL record có tên

Restore point không phải table, row hoặc SQL savepoint. Nó là marker trong WAL. Khi recovery replay tới marker được chọn, PostgreSQL có thể dừng theo recovery_target_name.

### 8.4. Savepoint SQL không phải restore point

SAVEPOINT trong một transaction SQL chỉ hỗ trợ rollback một phần transaction đang chạy. Nó không tạo marker PITR lâu dài và không thể thay thế pg_create_restore_point().

### 8.5. Restore point không thay base backup

Marker chỉ xác định điểm dừng trong WAL. Nếu base backup và WAL archive cần thiết đã bị xóa, marker không thể tự tái tạo cluster.

### 8.6. Lưu metadata ngoài database

Ghi restore point name và returned LSN ra hệ thống độc lập: change management, backup catalog hoặc incident log. Nếu database bị mất hoàn toàn, không thể dựa vào một bảng trong chính database đó để tìm marker.

## 9. Chọn recovery target phù hợp

### 9.1. Khi biết chính xác thời gian

Dùng recovery_target_time khi audit/logs cho biết commit time đáng tin cậy. Ghi rõ timezone và cân nhắc inclusive semantics.

### 9.2. Khi đã ghi nhận LSN

Dùng recovery_target_lsn khi change ticket, restore point metadata hoặc hệ thống theo dõi WAL đã ghi LSN cụ thể.

### 9.3. Khi chuẩn bị một thay đổi rủi ro

Tạo restore point trước thay đổi, sau đó dùng recovery_target_name. Đây là cách dễ truyền đạt cho người trực sự cố vì tên marker gắn với hoạt động cụ thể.

### 9.4. Khi chỉ biết XID

PostgreSQL còn có recovery_target_xid. Có thể hữu ích khi đã xác định transaction ID của commit cần làm boundary. Tuy nhiên XID có semantics wraparound và không phải business ID; cần xác minh transaction đúng cluster/timeline.

### 9.5. Bảng quyết định

| Thông tin đang có | Target nên cân nhắc | Việc phải xác minh |
| --- | --- | --- |
| Timestamp commit từ database log | recovery_target_time | Timezone, commit boundary, inclusive |
| LSN chính xác từ WAL/audit | recovery_target_lsn | Cluster, timeline, WAL range |
| Marker trước migration đã tạo | recovery_target_name | Marker archived, name duy nhất |
| XID của transaction lỗi | recovery_target_xid | Đúng transaction và boundary |
| Chỉ biết khoảng thời gian | Time target trên cluster tạm | Kiểm tra dữ liệu thực tế trước cutover |

### 9.6. Không chọn target bằng phỏng đoán

Nếu chỉ biết “lỗi xảy ra khoảng 10 giờ”, restore nhiều bản thử nghiệm quanh khoảng đó trong môi trường tạm, kiểm tra business state và thu hẹp target. Không đưa một target ước lượng vào production ngay.

## 10. recovery_target_action: dừng, pause hay promote

Khi recovery target đạt được, PostgreSQL cần biết hành động tiếp theo.

### 10.1. pause

```conf
recovery_target_action = 'pause'
```

Pause dừng WAL replay tại recovery target để DBA có thể kiểm tra trạng thái trước khi quyết định tiếp tục. Nếu hot_standby được bật và phiên bản hỗ trợ, có thể kết nối read-only để kiểm tra dữ liệu trong khi recovery đang pause.

Đây thường là lựa chọn tốt cho restore drill và incident recovery cần xác minh business data trước khi mở ghi.

### 10.2. promote

```conf
recovery_target_action = 'promote'
```

Promote kết thúc recovery tại target và đưa server sang trạng thái primary có thể nhận writes. Chỉ dùng tự động khi target đã được xác định, kiểm thử và quy trình cutover cho phép.

Một khi đã promote và bắt đầu ghi dữ liệu mới, việc quay lại cùng nhánh recovery cũ cần quy trình riêng. Không promote trước khi hoàn tất validation.

### 10.3. shutdown

```conf
recovery_target_action = 'shutdown'
```

Shutdown dừng server khi target đạt được. Nó hữu ích trong một số quy trình cần giữ trạng thái phục hồi ở target rồi kiểm tra offline. Cần hiểu cách restart và recovery configuration của version đang dùng.

### 10.4. Mặc định và khả năng

Giá trị mặc định thường là pause. Hành vi và điều kiện hỗ trợ có thể phụ thuộc major version và hot_standby. Kiểm tra tài liệu của đúng phiên bản trước khi dựa vào action trong automation.

### 10.5. Phân biệt pause với promote

- Pause: recovery vẫn đang diễn ra về mặt trạng thái; WAL replay tạm ngừng tại target.
- Promote: kết thúc recovery và tạo primary mới.
- Shutdown: dừng server sau khi đạt target.

Không nhầm pause với một server primary đã sẵn sàng nhận writes.

## 11. recovery_target_timeline và timeline history

### 11.1. Timeline là gì?

Khi một PostgreSQL standby được promote, cluster tạo một timeline mới. Timeline ID giúp phân biệt các nhánh lịch sử WAL sau những lần promote/failover.

Một hệ thống có nhiều lần failover có thể có nhiều timeline files trong WAL archive.

### 11.2. Vì sao recovery phải chọn timeline?

Một base backup được tạo trên timeline cũ có thể có nhiều nhánh WAL về sau. Recovery cần biết nhánh nào là lịch sử muốn theo.

### 11.3. latest

```conf
recovery_target_timeline = 'latest'
```

latest yêu cầu PostgreSQL chọn timeline mới nhất có thể tìm thấy trong archive theo quy tắc của nó. Đây là lựa chọn thường dùng khi muốn theo nhánh lịch sử mới nhất.

### 11.4. current

```conf
recovery_target_timeline = 'current'
```

current giới hạn recovery theo timeline mà base backup đang thuộc về. Dùng khi cần giữ nguyên nhánh của backup và không theo một nhánh mới hơn.

### 11.5. Timeline ID cụ thể

Có thể chỉ định timeline ID cụ thể dưới dạng số, nếu biết nhánh cần khôi phục. Cần lưu timeline metadata trong backup catalog và xác minh history files.

### 11.6. Timeline history file

PostgreSQL sử dụng timeline history files để biết nhánh mới bắt đầu từ đâu. Archive phải bảo vệ các file history cùng WAL segments. Thiếu history file có thể làm recovery không tìm được đúng nhánh.

### 11.7. latest không phải lúc nào cũng đúng

Nếu archive chứa nhánh mới hơn do một failover khác, latest có thể chọn nhánh không phải mục tiêu của incident. Khi điều tra lịch sử phức tạp, xác định timeline từ base backup và history files trước khi chọn.

## 12. Cấu hình PITR trên PostgreSQL 12 trở lên

PostgreSQL 12 trở lên dùng signal files để điều khiển recovery.

### 12.1. Chuẩn bị base backup

Restore base backup vào data directory mới, tách biệt với cluster production hiện hành. Đảm bảo tablespaces được restore/mapping đúng.

### 12.2. Cấu hình restore_command

Ví dụ minh họa:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
```

- %f: tên file cần lấy từ archive.
- %p: đường dẫn đích mà PostgreSQL yêu cầu ghi file.

Command thực tế phụ thuộc công cụ archive. Nó phải trả success khi file đã được cung cấp đầy đủ và trả trạng thái phù hợp khi file không có. Không để command trả success cho một file tải dở hoặc sai nội dung.

### 12.3. Cấu hình target

Ví dụ target time:

```conf
recovery_target_time = '2026-11-14 10:32:00+07'
recovery_target_inclusive = false
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

Với target LSN hoặc restore point, thay target chính tương ứng và không giữ đồng thời target time.

### 12.4. Tạo recovery.signal

Tạo file rỗng recovery.signal trong PGDATA để yêu cầu archive recovery:

```bash
touch "$PGDATA/recovery.signal"
```

Trên Windows, tạo file rỗng trong data directory bằng công cụ filesystem phù hợp. Đảm bảo đường dẫn đúng cluster được restore.

### 12.5. Khởi động và theo dõi logs

Khởi động PostgreSQL bằng service/pg_ctl phù hợp. Theo dõi log để biết:

- Recovery bắt đầu.
- WAL segment được lấy từ archive.
- Timeline được chọn.
- Target được nhận diện.
- Recovery target reached.
- Action pause/promote/shutdown được thực hiện.
- Lỗi archive hoặc WAL gap.

### 12.6. Không sửa PGDATA production để thử target

Thử nghiệm PITR trên bản restore tách biệt. Việc sửa recovery settings hoặc tạo signal file trong data directory đang phục vụ production có thể làm thay đổi hành vi khởi động/recovery của cluster.

## 13. Cấu hình trên PostgreSQL 11 trở xuống

Các phiên bản trước PostgreSQL 12 sử dụng cơ chế recovery.conf cho archive recovery. Các cấu hình target và restore_command được đặt trong file này theo cú pháp của version tương ứng.

Không copy cấu hình recovery.signal của PostgreSQL 12+ vào runbook cho PostgreSQL 11 trở xuống.

Khi vận hành nhiều major versions, duy trì các runbooks riêng và kiểm tra:

- Recovery file semantics.
- Tên/phiên bản backup API.
- Recovery target settings.
- restore_command syntax.
- Timeline behavior.
- Các hàm giám sát WAL có sẵn.

Không dựa vào một cấu hình duy nhất cho mọi major versions.

## 14. Thực hành tạo restore point trước migration

Giả sử bạn chuẩn bị một migration có rủi ro trên database lab.

### 14.1. Xác nhận archive hoạt động

Kiểm tra:

```sql
SHOW archive_mode;
SHOW archive_command;
```

Cần kiểm tra cả archive logs/metrics và sự tồn tại của WAL segments ở archive. Giá trị config không chứng minh upload thành công.

### 14.2. Tạo marker

```sql
SELECT pg_create_restore_point(
    'before_lab_migration_20261114_103000'
) AS restore_lsn;
```

Ghi lại LSN trả về trong change record.

### 14.3. Chờ marker được archive

Xác minh WAL segment chứa marker đã được publish lên archive storage và có thể đọc lại. Có thể yêu cầu WAL switch khi phù hợp, sau đó chờ archive hoàn tất.

### 14.4. Thực hiện thay đổi lab

```sql
CREATE TABLE IF NOT EXISTS recovery_lab_marker (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    note text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO recovery_lab_marker (note)
VALUES ('change after restore point');
```

Trong production, migration cần ticket, backup verification và change procedure riêng.

### 14.5. Restore tới marker

Restore một base backup phù hợp vào cluster tạm, cấu hình:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_name = 'before_lab_migration_20261114_103000'
recovery_target_action = 'pause'
```

Sau recovery, kiểm tra table/row được tạo sau marker có xuất hiện hay không. Kết quả mong đợi là những thay đổi commit sau marker chưa được replay.

### 14.6. Xác minh target

Kiểm tra logs và các hàm trạng thái recovery. Đừng chỉ suy ra đã dừng đúng điểm từ việc server khởi động thành công.

## 15. Kiểm tra trạng thái recovery

### 15.1. Có đang ở recovery không?

```sql
SELECT pg_is_in_recovery();
```

- true: server vẫn đang ở recovery/standby state.
- false: server đã kết thúc recovery và đang hoạt động như primary.

### 15.2. Replay LSN

```sql
SELECT
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
```

Replay LSN là thông tin quan trọng để đối chiếu target LSN. Timestamp transaction cuối cùng có thể cũ hơn thời gian hiện tại và không phải đồng hồ của recovery process.

### 15.3. Replay pause state

Các phiên bản hỗ trợ có thể cung cấp hàm trạng thái replay pause. Kiểm tra tài liệu major version và dùng các hàm pg_wal_replay_pause()/pg_wal_replay_resume() phù hợp khi cần điều khiển replay.

Không gọi resume một cách tùy tiện sau khi đã đạt target; replay tiếp tục có thể đi qua điểm cần giữ lại.

### 15.4. Logs là nguồn bằng chứng quan trọng

Tìm thông báo recovery target reached và action tương ứng. Ghi lại timeline, target setting, replay position và thời gian recovery hoàn tất vào incident report.

### 15.5. Kiểm tra dữ liệu ứng dụng

Chạy các truy vấn read-only xác minh business state: row counts, IDs, timestamps, aggregates, constraints và records liên quan đến sự cố. Một target kỹ thuật đúng chưa chắc là target nghiệp vụ đúng.

## 16. Quy trình PITR khi transaction lỗi đã commit

Giả sử ứng dụng đã commit một transaction xóa nhầm dữ liệu. Mục tiêu là phục hồi trạng thái ngay trước transaction đó.

### Bước 1. Ngăn lỗi tiếp tục lan rộng

Tạm dừng job/consumer hoặc chức năng đang tạo ra thay đổi lỗi nếu cần. Lưu logs, request IDs, transaction timestamps và audit records.

### Bước 2. Xác định recovery boundary

Tìm:

- Commit timestamp từ database logs/audit.
- XID nếu đã được ghi nhận.
- LSN nếu có WAL/audit marker.
- Restore point được tạo trước operation.
- Timeline mà primary đang sử dụng khi sự kiện xảy ra.

### Bước 3. Chọn base backup

Chọn base backup có thể replay WAL liên tục tới recovery target. Kiểm tra manifest, checksum, version và tablespace mapping.

### Bước 4. Xác minh WAL archive

Xác minh mọi WAL segment cần thiết và timeline history files có sẵn. Kiểm tra archive gaps và retention.

### Bước 5. Restore vào môi trường tách biệt

Tạo data directory/volume mới, restore base backup và cấu hình restore_command. Đặt đúng recovery target và action pause.

### Bước 6. Khởi động recovery

Theo dõi logs, xác nhận server đang replay đúng timeline và đã đạt target.

### Bước 7. Kiểm tra dữ liệu

So sánh dữ liệu với audit/event logs. Xác định transaction lỗi đã bị loại khỏi recovered state và các transactions hợp lệ khác có được giữ đúng không.

### Bước 8. Quyết định cách đưa dữ liệu trở lại

Các lựa chọn:

- Promote recovered cluster và chuyển traffic sang cluster mới.
- Dump/copy objects cần thiết từ recovered cluster về production.
- Dùng logical reconciliation để giữ các writes hợp lệ phát sinh sau recovery target.

Lựa chọn phụ thuộc thời gian downtime, writes mới và business consistency. Không tự động thay production data directory khi chưa có cutover plan.

### Bước 9. Bảo toàn evidence

Giữ cluster restore, logs, target settings, WAL metadata và checksum trong thời gian incident review cần thiết.

### Bước 10. Cập nhật runbook

Ghi lại thời gian phát hiện, target đã chọn, RPO/RTO thực tế, blockers, sai lệch và bài học.

## 17. Vì sao recovery target không đạt được?

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Recovery dừng trước target | Archive hết WAL hoặc segment bị thiếu | Archive catalog, logs, WAL gaps |
| Không tìm thấy restore point | Marker chưa được archive hoặc name sai | Restore point metadata, segment chứa marker |
| Target time không khớp | Sai timezone/commit timestamp | Log timezone, audit, clock sync |
| Target LSN không đạt | LSN sai cluster/timeline hoặc nằm sau WAL có sẵn | Backup manifest, timeline, archive range |
| Recovery chọn nhánh khác | recovery_target_timeline không phù hợp | History files và failover records |
| Restore command thất bại | Credential, network, path hoặc object missing | Command logs, storage access |
| Server promote quá sớm | Action/config không như dự kiến | Effective recovery settings và logs |
| Recovery lặp lại sau restart | Signal/recovery configuration còn hiệu lực | recovery.signal, service config, logs |
| Server không start | Base backup thiếu file hoặc mapping sai | pg_verifybackup, tablespaces, permissions |
| Dữ liệu không đúng business state | Target chọn theo request time thay vì commit boundary | Audit, commit timestamp, restore trial |

### 17.1. WAL archive có thể kết thúc trước target

Nếu PostgreSQL đã đọc hết WAL có sẵn mà target vẫn ở phía trước, target không đạt được. Cần xác minh archive có đầy đủ hay không và liệu target có thực sự nằm trong lịch sử của backup/timeline đã chọn.

### 17.2. Sai timeline

Một LSN hoặc restore point chỉ có ý nghĩa trong WAL history cụ thể. Nếu chọn timeline không đúng, marker có thể không tồn tại trong nhánh đang replay.

### 17.3. Sai tên marker

Restore point name phải khớp chính xác. Tránh tên trùng và lưu metadata khi tạo marker.

### 17.4. Archive command trả lỗi

PostgreSQL cần lấy đúng WAL file vào đúng destination path. Nếu command không tìm thấy file, trả success sai hoặc copy thiếu bytes, recovery có thể chờ hoặc thất bại.

### 17.5. Recovery target đã bị bỏ qua do config

Đọc log startup và effective configuration. Kiểm tra đúng một target chính được đặt, file signal phù hợp và cluster thực sự đang ở archive recovery.

## 18. Lưu ý về timezone và đồng bộ đồng hồ

### 18.1. Đồng hồ ứng dụng và database

Ứng dụng có thể ghi event timestamp trước khi transaction commit. Database commit time và request time khác nhau. Khi incident, phân biệt các timestamp này.

### 18.2. UTC và local time

Lưu timestamps trong logs theo UTC hoặc kèm offset. Khi nhập target, chuyển đổi một lần và kiểm tra lại bằng một timezone-aware tool.

### 18.3. Clock skew

Nếu server, application nodes và monitoring systems không đồng bộ NTP, timestamp correlation có thể sai. Đưa clock synchronization vào operational baseline.

### 18.4. DST

Một số timezone có daylight saving time. Timestamp local không có offset có thể mơ hồ vào thời điểm chuyển DST. Dùng UTC hoặc explicit offset.

### 18.5. Ghi lại cả UTC và local time

Incident ticket nên ghi:

- Event timestamp gốc.
- Source system và timezone.
- UTC conversion.
- PostgreSQL commit timestamp nếu có.
- Recovery target string đã dùng.
- Target inclusive/exclusive.

## 19. Restore point trong quy trình release và migration

### 19.1. Trước schema migration

Tạo marker trước khi chạy migration có thể drop/transform columns hoặc rewrite data. Nếu cần quay lại, dùng base backup và WAL archive để replay tới marker.

### 19.2. Trước bulk import

Marker giúp xác định trạng thái trước batch import. Nếu import sai, restore tới marker trong cluster tạm để trích dữ liệu/đối chiếu.

### 19.3. Trước thao tác quản trị

Các hoạt động như data cleanup, role changes hoặc batch maintenance có thể cần marker nếu impact lớn và không có rollback logic đơn giản.

### 19.4. Không tạo marker thay cho change control

Restore point không bảo đảm thao tác có thể rollback tức thì. PITR cần thời gian restore/replay, validation và cutover. Vẫn cần staging, transaction design, backup verification và rollback plan.

### 19.5. Đừng tạo quá nhiều marker vô nghĩa

Restore point records chiếm WAL và archive metadata. Tạo marker cho các sự kiện có ý nghĩa; đặt naming convention và retention cho manifest.

## 20. PITR và timeline sau failover

### 20.1. Promotion tạo nhánh lịch sử

Khi standby được promote, PostgreSQL bắt đầu timeline mới. WAL sau promotion thuộc nhánh mới.

### 20.2. Base backup trước failover

Base backup có thể được tạo trên timeline cũ nhưng recovery target nằm trên timeline mới. Cần timeline history file và WAL chain từ đúng nhánh.

### 20.3. latest

recovery_target_timeline = 'latest' hữu ích khi muốn theo timeline mới nhất được tìm thấy trong archive. Nhưng trong incident có nhiều failovers, latest có thể không phải nhánh business cần phục hồi.

### 20.4. Chọn timeline ID cụ thể

Nếu backup catalog lưu timeline ID và history files, có thể chỉ định ID cần khôi phục. Xác minh target có tồn tại trên timeline đó.

### 20.5. Không trộn WAL từ hai primary độc lập

Hai cluster được fork hoặc khởi tạo độc lập không chia sẻ cùng một WAL history chỉ vì cùng database name. Xác định system identifier, timeline và backup provenance.

## 21. Recovery target và transaction boundaries

### 21.1. Transaction là đơn vị commit

PostgreSQL không để một transaction commit một nửa trong recovery. WAL replay và transaction status bảo đảm transaction được phục hồi theo semantics của commit/abort.

### 21.2. Target giữa một transaction

Nếu target rơi vào giữa các WAL records của một transaction, recovery vẫn phải tôn trọng transaction commit/abort semantics. Không coi target LSN tùy ý là cách cắt một transaction thành hai nửa có thể nhìn thấy.

### 21.3. Inclusive boundary

Dùng recovery_target_inclusive để kiểm soát phía nào của target boundary được giữ cho các target có hỗ trợ. Kiểm tra thực tế bằng logs và business queries.

### 21.4. Một transaction có nhiều statements

Một transaction có thể thực hiện nhiều statements rồi commit một lần. PITR theo commit boundary sẽ đưa toàn bộ transaction vào hoặc loại nó theo semantics, không khôi phục riêng một statement giữa transaction.

### 21.5. Subtransactions và savepoints

Savepoints không phải recovery targets. Subtransaction rollback/commit được quản lý bên trong transaction; PITR target vẫn làm việc theo WAL recovery semantics.

## 22. LSN target và công cụ giám sát replication

LSN thường xuất hiện trong replication monitoring. Một số cột và hàm:

| Hàm/cột | Ý nghĩa |
| --- | --- |
| pg_current_wal_lsn() | WAL write location hiện tại trên primary |
| pg_current_wal_insert_lsn() | WAL insert location hiện tại |
| pg_current_wal_flush_lsn() | WAL flush location |
| pg_last_wal_receive_lsn() | LSN cuối nhận được trên standby |
| pg_last_wal_replay_lsn() | LSN cuối replay trên standby |
| sent_lsn | WAL location đã gửi theo replication stats |
| write_lsn | WAL location đã được standby ghi |
| flush_lsn | WAL location đã flush |
| replay_lsn | WAL location đã replay |

Tên cột/hàm có thể khác ở các PostgreSQL versions cũ. Kiểm tra catalog/view của major version đang chạy.

### 22.1. LSN nhận và replay khác nhau

Standby có thể đã nhận WAL nhưng chưa replay hết. receive_lsn cao hơn replay_lsn là trạng thái có thể xảy ra. Nếu dùng LSN target, phải hiểu target so với vị trí replay, không chỉ vị trí receive.

### 22.2. LSN không phải thời gian

Không dùng pg_wal_lsn_diff() để suy ra trực tiếp “bao nhiêu phút”. WAL generation rate thay đổi theo workload.

### 22.3. Dùng LSN marker trong change records

Nếu một migration ticket lưu restore point LSN, DBA có thể dùng chính marker đó để cấu hình target hoặc đối chiếu replay. Đây là cách kết nối change management với recovery.

## 23. Bảo vệ recovery metadata

### 23.1. Backup catalog

Lưu các thông tin:

- Backup ID và base backup location.
- PostgreSQL version và system identifier.
- Timeline ID và history files.
- WAL start/end và archive locations.
- Restore point names/LSNs.
- Recovery target đã dùng.
- restore_command version/config reference.
- Tablespace mapping.
- Checksum/manifest.
- Encryption key reference.

### 23.2. Lưu metadata ngoài cluster

Không chỉ lưu restore point name trong một table thuộc database đang được bảo vệ. Khi cluster bị mất, metadata đó cũng có thể mất.

### 23.3. Bảo vệ WAL archive

WAL archive phải có access controls, immutable retention hoặc cơ chế bảo vệ tương đương. Nếu attacker có thể xóa cả base backup và WAL archive, PITR sẽ thất bại.

### 23.4. Kiểm tra quyền restore

Backup operator cần đọc archive và giải mã backup. Kiểm tra credential/key access trong restore drill, không chờ incident mới phát hiện key đã hết hạn.

## 24. Restore drill cho từng loại target

### 24.1. Time target drill

1. Chọn base backup và WAL archive.
2. Chọn một commit timestamp đã biết trong lab.
3. Restore vào cluster tạm.
4. Cấu hình recovery_target_time với timezone rõ.
5. Thử inclusive/exclusive theo tình huống.
6. Xác minh row/transaction ở hai phía boundary.
7. Lưu logs và replay LSN.

### 24.2. LSN target drill

1. Tạo restore point hoặc ghi một LSN có chủ đích.
2. Lưu LSN vào manifest.
3. Xác minh WAL segment chứa LSN đã archive.
4. Restore base backup vào cluster tạm.
5. Cấu hình recovery_target_lsn.
6. So sánh pg_last_wal_replay_lsn() và logs với target.
7. Kiểm tra business state.

### 24.3. Named restore point drill

1. Gọi pg_create_restore_point() trước thay đổi lab.
2. Lưu name và returned LSN.
3. Xác nhận WAL segment chứa marker đã archive.
4. Tạo một thay đổi commit sau marker.
5. PITR bằng recovery_target_name.
6. Kiểm tra thay đổi sau marker không có trong recovered state.
7. Ghi restore report.

### 24.4. Drill phải kiểm tra cả failure path

Thử một lần với WAL segment bị thiếu trong môi trường lab để xác nhận alert và logs dễ hiểu. Không xóa WAL production để mô phỏng lỗi.

## 25. Ví dụ cấu hình theo ba mục tiêu

### 25.1. Dừng trước thời điểm lỗi

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_time = '2026-11-14 10:32:04+07'
recovery_target_inclusive = false
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

Dùng khi đã xác định commit timestamp và muốn loại trừ transaction tại boundary theo semantics của version.

### 25.2. Dừng tại LSN đã ghi trong change ticket

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_lsn = '0/16B6C50'
recovery_target_action = 'pause'
recovery_target_timeline = 'current'
```

Dùng khi LSN đã được xác minh thuộc đúng backup/timeline. Chọn current chỉ khi cần giới hạn theo timeline của base backup.

### 25.3. Dừng tại restore point trước migration

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_name = 'before_schema_migration_20261114_103000'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

Dùng khi marker được tạo và WAL đã archive trước khi migration bắt đầu.

### 25.4. Các ví dụ là cấu hình thay thế

Không đặt cả ba target chính trong cùng recovery configuration. Mỗi ví dụ là một lần restore riêng với một target được chọn.

## 26. Checklist xử lý sự cố PITR

### Trước khi restore

- Xác định database/cluster và system identifier.
- Xác định sự cố, commit time, XID, LSN hoặc restore point.
- Chọn base backup gần nhất phù hợp.
- Xác minh WAL liên tục.
- Xác minh timeline history.
- Xác minh tablespaces và configuration.
- Xác minh encryption key/credentials.
- Chuẩn bị target environment tách biệt.

### Trong khi restore

- Dùng đúng PostgreSQL major version.
- Restore đầy đủ physical files.
- Đặt restore_command.
- Chọn đúng một recovery target chính.
- Đặt timezone/LSN/name chính xác.
- Tạo recovery.signal trên PostgreSQL 12+.
- Theo dõi recovery logs.
- Xác minh target reached và action.

### Sau khi đạt target

- Kiểm tra pg_is_in_recovery().
- Kiểm tra replay LSN.
- Đọc log recovery target.
- Chạy business queries.
- Kiểm tra roles/extensions/constraints.
- Xác định promotion/copy-back/cutover plan.
- Ghi lại RPO/RTO thực tế.
- Bảo toàn evidence và cập nhật runbook.

## 27. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Recovery target là một loại backup | Nó là điểm dừng của WAL replay |
| Có base backup là đủ PITR | Cần WAL liên tục tới target |
| Timestamp target dừng ở đúng microsecond | Recovery tuân theo transaction/WAL boundaries |
| Timestamp từ application luôn là commit time | Request/event time có thể khác commit time |
| LSN là XID | LSN là WAL position; XID định danh transaction |
| LSN có thể đổi trực tiếp thành timestamp | Không có phép đổi đơn giản, ổn định theo workload |
| Restore point là SQL SAVEPOINT | Restore point là marker trong WAL |
| Ghi marker nghĩa WAL đã archive | Phải xác minh segment đã được publish |
| Tên restore point có thể tái sử dụng tùy ý | Tên duy nhất giúp tránh dừng ở marker khác |
| Có thể đặt time, LSN và name cùng lúc | Chọn một target chính cho mỗi recovery |
| recovery_target_inclusive không quan trọng | Nó quyết định boundary inclusion cho target áp dụng |
| Pause nghĩa server đã primary | Server vẫn ở recovery và không nhận writes bình thường |
| Promote giống pause | Promote kết thúc recovery |
| latest timeline luôn đúng | Phải xác minh nhánh lịch sử cần dùng |
| WAL receive LSN bằng replay LSN | Standby có thể nhận trước rồi replay sau |
| pg_last_xact_replay_timestamp là current time | Nó là commit timestamp cuối cùng được replay |
| Restore point không cần base backup | Marker không thay base backup |
| Standby mode và archive recovery là một | Signal files và semantics khác nhau |
| Recovery target đạt là ứng dụng đã sẵn sàng | Cần validate business state và cutover |
| Có thể PITR một table trực tiếp | Recovery target áp dụng cho cluster; table recovery thường cần cluster tạm |
| WAL thiếu một segment vẫn có thể replay bình thường | Gap có thể làm PITR không thể đi qua |
| Chỉ cần archive WAL, không cần history file | Timeline history cũng có thể cần |
| Chọn target theo giờ máy cá nhân | Dùng timestamp có timezone và commit evidence |
| Resume sau pause luôn an toàn | Replay có thể đi qua target đã chọn |
| Lệnh restore thành công chứng minh target đúng | Phải xác minh logs, replay LSN và dữ liệu |

## 28. Bài tập thực hành có đáp án

Các bài tập giả định bạn có PostgreSQL lab, base backup và WAL archive riêng. Không thử PITR bằng cách thay recovery settings trên cluster production đang phục vụ ứng dụng.

### Bài 1. Recovery target là gì?

**Đáp án:** Điểm mà PostgreSQL dừng replay WAL trong archive recovery.

### Bài 2. Ba recovery target chính trong bài là gì?

**Đáp án:** recovery_target_time, recovery_target_lsn và recovery_target_name.

### Bài 3. PITR cần những thành phần nào?

**Đáp án:** Base backup hợp lệ, WAL liên tục tới target, restore configuration và target chính xác.

### Bài 4. Setting chọn timestamp?

**Đáp án:** recovery_target_time.

### Bài 5. Setting chọn LSN?

**Đáp án:** recovery_target_lsn.

### Bài 6. Setting chọn named restore point?

**Đáp án:** recovery_target_name.

### Bài 7. LSN là gì?

**Đáp án:** Vị trí trong Write-Ahead Log.

### Bài 8. LSN thường có định dạng nào?

**Đáp án:** Hai số hexadecimal cách nhau bởi dấu /, ví dụ 0/16B6C50.

### Bài 9. LSN và XID có giống nhau?

**Đáp án:** Không. LSN là WAL location; XID là transaction identifier.

### Bài 10. Hàm xem WAL LSN hiện tại trên primary?

**Đáp án:** pg_current_wal_lsn().

### Bài 11. Hàm xem replay LSN trên recovery server?

**Đáp án:** pg_last_wal_replay_lsn().

### Bài 12. pg_last_xact_replay_timestamp() cho biết gì?

**Đáp án:** Timestamp commit của transaction gần nhất được replay, không phải current time.

### Bài 13. Hàm tính khoảng cách byte giữa hai LSN?

**Đáp án:** pg_wal_lsn_diff().

### Bài 14. Restore point được tạo bằng hàm nào?

**Đáp án:** pg_create_restore_point(name).

### Bài 15. Restore point trả về gì?

**Đáp án:** LSN của marker được ghi vào WAL.

### Bài 16. Nên tạo restore point khi nào?

**Đáp án:** Trước migration, bulk operation hoặc thay đổi rủi ro cần một recovery boundary rõ.

### Bài 17. Tên restore point có nên duy nhất?

**Đáp án:** Có. Tên duy nhất giúp tránh nhầm marker trong WAL history.

### Bài 18. Restore point có thay base backup không?

**Đáp án:** Không. Nó chỉ là marker trong WAL.

### Bài 19. Vì sao cần xác minh WAL segment chứa marker đã archive?

**Đáp án:** Marker chưa được archive thì môi trường restore có thể chưa replay tới được nó.

### Bài 20. SAVEPOINT SQL có phải restore point PITR?

**Đáp án:** Không. SAVEPOINT chỉ hỗ trợ rollback trong transaction hiện tại.

### Bài 21. Timestamp target cần timezone không?

**Đáp án:** Nên có explicit UTC offset để tránh nhầm timezone.

### Bài 22. Recovery target time có dừng ở microsecond tùy ý không?

**Đáp án:** Không. WAL replay tuân theo commit records và transaction boundaries.

### Bài 23. Application request time luôn bằng commit time?

**Đáp án:** Không. Queueing, execution và transaction duration tạo độ lệch.

### Bài 24. recovery_target_inclusive điều khiển gì?

**Đáp án:** Quyết định transaction tại recovery boundary được bao gồm hay loại trừ cho các target áp dụng.

### Bài 25. Giá trị mặc định thường gặp của recovery_target_inclusive?

**Đáp án:** true.

### Bài 26. Nếu muốn loại trừ transaction tại time boundary, cần xem setting nào?

**Đáp án:** recovery_target_inclusive = false, cùng target timestamp đã xác minh.

### Bài 27. Setting action nào dừng replay để kiểm tra?

**Đáp án:** recovery_target_action = 'pause'.

### Bài 28. Promote làm gì?

**Đáp án:** Kết thúc recovery và đưa server thành primary mới có thể nhận writes.

### Bài 29. Shutdown action có mục đích gì?

**Đáp án:** Dừng server khi recovery target đạt được, hữu ích trong một số quy trình giữ trạng thái target để kiểm tra offline.

### Bài 30. Pause có nghĩa server đã nhận writes chưa?

**Đáp án:** Không. Server vẫn ở recovery state.

### Bài 31. Timeline là gì?

**Đáp án:** Nhánh lịch sử WAL được phân biệt bằng timeline ID, thường tạo mới sau promotion.

### Bài 32. recovery_target_timeline = latest có nghĩa gì?

**Đáp án:** Chọn timeline mới nhất tìm được theo quy tắc của PostgreSQL trong archive.

### Bài 33. current timeline dùng khi nào?

**Đáp án:** Khi muốn giới hạn recovery theo timeline mà base backup thuộc về.

### Bài 34. Vì sao timeline history file quan trọng?

**Đáp án:** Nó mô tả nhánh timeline và điểm fork, giúp PostgreSQL theo đúng lịch sử WAL.

### Bài 35. Lựa chọn latest có luôn đúng?

**Đáp án:** Không. Có thể có nhánh mới hơn từ failover khác không phải mục tiêu incident.

### Bài 36. PostgreSQL 12+ dùng file nào để bắt đầu archive recovery?

**Đáp án:** recovery.signal.

### Bài 37. standby.signal có cùng nghĩa recovery.signal không?

**Đáp án:** Không. Nó khởi động standby mode liên tục.

### Bài 38. restore_command làm gì?

**Đáp án:** Lấy WAL/archive file được yêu cầu và đặt vào destination path PostgreSQL cung cấp.

### Bài 39. Placeholder %f và %p có nghĩa gì?

**Đáp án:** %f là tên file cần lấy; %p là đường dẫn đích.

### Bài 40. PostgreSQL 11 trở xuống cấu hình recovery theo cách nào?

**Đáp án:** Dùng recovery.conf theo semantics của phiên bản đó.

### Bài 41. Vì sao phải dùng đúng PostgreSQL major version?

**Đáp án:** Physical data format và recovery semantics phải tương thích với base backup.

### Bài 42. Hàm kiểm tra server có đang recovery?

**Đáp án:** pg_is_in_recovery().

### Bài 43. pg_last_wal_replay_lsn() có cho biết WAL đã nhận hết chưa?

**Đáp án:** Không. Nó cho biết replay position; receive position là thông tin khác.

### Bài 44. Vì sao replay LSN có thể thấp hơn receive LSN?

**Đáp án:** Standby có thể đã nhận WAL nhưng chưa replay hết.

### Bài 45. Nếu WAL segment bị thiếu thì sao?

**Đáp án:** Recovery có thể không tiến tới target nằm sau khoảng trống.

### Bài 46. Restore point name sai thì sao?

**Đáp án:** PostgreSQL không tìm thấy marker mục tiêu trong WAL history đang replay.

### Bài 47. Vì sao cần archive history files?

**Đáp án:** Recovery trên timeline mới có thể cần history file để tìm đúng nhánh.

### Bài 48. Có thể đặt recovery_target_time và recovery_target_name cùng lúc để dự phòng?

**Đáp án:** Không. Chọn một recovery target chính cho mỗi lần recovery.

### Bài 49. Target LSN lấy từ cluster khác có dùng được không?

**Đáp án:** Không nên. Phải xác minh system identifier, timeline và backup provenance.

### Bài 50. pg_create_restore_point cần quyền gì?

**Đáp án:** Quyền quản trị phù hợp, thường là superuser.

### Bài 51. pg_switch_wal() có thay archive verification không?

**Đáp án:** Không. Nó có thể yêu cầu segment switch, nhưng vẫn phải xác minh archive publish thành công.

### Bài 52. Vì sao phải restore vào môi trường tạm trước?

**Đáp án:** Để kiểm tra target/business state và tránh làm gián đoạn hoặc ghi đè cluster production.

### Bài 53. Recovery target reached chứng minh business data đúng?

**Đáp án:** Không. Cần kiểm tra rows, aggregates, audit records và application behavior.

### Bài 54. Sau pause có thể làm gì?

**Đáp án:** Kết nối read-only nếu cấu hình hỗ trợ, xác minh dữ liệu, rồi quyết định promote hoặc hành động theo runbook.

### Bài 55. Vì sao không resume replay tùy tiện?

**Đáp án:** Replay có thể đi qua target đã chọn và đưa các transactions sau target trở lại.

### Bài 56. Có thể PITR riêng một table bằng recovery_target_time không?

**Đáp án:** Không. Recovery target áp dụng cho cluster; thường restore cluster tạm rồi export table cần thiết.

### Bài 57. Nếu chỉ biết request time, nên làm gì?

**Đáp án:** Đối chiếu database commit logs/audit, thử nhiều target trên cluster tạm và xác minh business state.

### Bài 58. RPO thực tế phụ thuộc điều gì?

**Đáp án:** Backup cadence, WAL archive lag, continuity và khả năng truy cập recovery artifacts.

### Bài 59. Restore drill phải lưu bằng chứng nào?

**Đáp án:** Backup ID, target, timeline, WAL range, logs, replay LSN, validation results và elapsed time.

### Bài 60. Lập checklist chọn recovery target

**Đáp án gợi ý:**

1. Xác định transaction/event gây lỗi và thời điểm commit.
2. Tìm timestamp, XID, LSN hoặc restore point metadata.
3. Xác định base backup và system identifier.
4. Kiểm tra WAL continuity và timeline history files.
5. Chọn đúng một target chính.
6. Ghi rõ timezone và inclusive semantics nếu dùng time.
7. Xác minh LSN thuộc đúng timeline nếu dùng LSN.
8. Xác minh restore point đã được archive nếu dùng name.
9. Dùng recovery.signal/restore_command theo đúng major version.
10. Pause, kiểm tra business data, rồi mới quyết định promote/cutover.

## 29. Checklist production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| Base backup | Có bản hợp lệ và đã kiểm chứng |
| WAL archive | Liên tục từ base backup tới target |
| WAL gaps | Có monitoring và alert |
| Timeline history | Được archive và giữ retention |
| Target source | Có timestamp/LSN/name đáng tin |
| Timezone | Explicit UTC offset hoặc UTC |
| Commit time | Phân biệt với request/event time |
| Inclusive semantics | Được chọn có chủ đích |
| Restore point naming | Unique, gắn với change/incident |
| Restore point archive | Segment chứa marker đã được xác minh |
| LSN provenance | Gắn với đúng cluster/timeline |
| recovery_target_timeline | Chọn theo backup lineage |
| restore_command | Test đọc archive và xử lý file lỗi |
| Signal file | Đúng recovery.signal/standby.signal theo mục tiêu |
| PostgreSQL version | Runbook đúng major version |
| recovery_target_action | Pause/promote/shutdown được hiểu rõ |
| Recovery logs | Được lưu để audit |
| Replay LSN | Được ghi nhận sau recovery |
| pg_is_in_recovery | Được kiểm tra |
| Business validation | Có queries và owner |
| Restore environment | Tách biệt production |
| Tablespaces | Được restore/map đầy đủ |
| Encryption keys | Có thể truy cập trong incident |
| Archive retention | Đủ dài cho recovery window |
| Restore drill | Time, LSN, name target đã thử |
| RPO/RTO | Đo thực tế, không chỉ mục tiêu |
| Cutover | Có quyết định và rollback plan |
| Incident evidence | Được giữ theo retention |

## 30. Tổng kết

Recovery target xác định điểm dừng của WAL replay trong PostgreSQL PITR. Chọn target theo thời gian, LSN hoặc restore point tùy bằng chứng sẵn có và độ chính xác cần thiết. Dù chọn cách nào, recovery chỉ đáng tin khi base backup, WAL chain, timeline và restore procedure đều hợp lệ.

Những nguyên tắc quan trọng:

1. **Recovery target không phải backup.** Nó chỉ chọn nơi WAL replay dừng.
2. **PITR cần base backup và WAL liên tục.** Một segment bị thiếu có thể làm target không đạt được.
3. **Time target dựa trên commit time trong WAL.** Timestamp ứng dụng có thể khác commit timestamp.
4. **Dùng timezone rõ ràng.** UTC hoặc explicit offset giúp tránh sai lệch.
5. **LSN là WAL position, không phải XID hay timestamp.** Xác minh cluster và timeline provenance.
6. **Restore point là marker trong WAL.** Tạo bằng pg_create_restore_point() trước thay đổi cần bảo vệ.
7. **Marker phải được archive.** Ghi marker thành công chưa có nghĩa WAL segment đã được publish.
8. **Tên marker nên duy nhất.** Lưu cả name, LSN, timestamp và change ticket bên ngoài database.
9. **Inclusive semantics rất quan trọng.** Xác định transaction tại boundary được giữ hay loại.
10. **Pause cho phép kiểm tra trước promote.** Promote kết thúc recovery và bắt đầu nhánh primary mới.
11. **Timeline phải phù hợp backup lineage.** latest không phải lúc nào cũng là nhánh incident cần khôi phục.
12. **PostgreSQL 12+ dùng recovery.signal cho archive recovery.** Các bản cũ dùng recovery.conf.
13. **Replay LSN khác receive LSN.** Đọc đúng metric khi xác minh.
14. **Recovery target reached chưa chứng minh business state đúng.** Kiểm tra audit và dữ liệu thực tế.
15. **Restore vào môi trường tách biệt trước.** Chỉ cutover sau validation và quyết định vận hành.
16. **Restore drills phải đo thời gian thực tế.** Tính cả WAL replay, validation và cutover.

Mô hình điều tra:

```text
Sự cố đã commit?
       |
       v
Có restore point trước sự cố?
       |                 \
      Có                  Không
       |                    |
       v                    v
Target name/LSN       Có commit timestamp?
       |                    |
       |               +----+----+
       |               |         |
       |              Có       Không
       |               |         |
       |               v         v
       |          Target time   Thu thập audit,
       |                        LSN, XID
       +-------------+-----------+
                     |
                     v
             Base backup + WAL
             + timeline hợp lệ?
                     |
                     v
              Restore vào lab
                     |
                     v
              Target reached?
                     |
                     v
              Validate business
                     |
                     v
              Pause -> promote/
                 cutover plan
```

**Câu hỏi review cuối cùng:** “Nếu một migration làm hỏng dữ liệu lúc 10:32, chúng ta có biết commit timestamp thực tế, LSN hoặc restore point trước migration không? Base backup và WAL archive có đủ để replay tới đó trên đúng timeline không? Và sau khi PostgreSQL báo target reached, ai xác nhận business state trước khi promote?” Một quy trình PITR hoàn chỉnh phải trả lời được cả ba câu hỏi bằng metadata, logs, WAL và restore drill.
