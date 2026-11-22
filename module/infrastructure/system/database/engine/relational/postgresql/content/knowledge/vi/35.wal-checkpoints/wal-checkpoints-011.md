# Phân biệt crash recovery, archive recovery và standby replay trong PostgreSQL

PostgreSQL dùng Write-Ahead Logging (WAL) để phục hồi dữ liệu sau sự cố, khôi phục từ bản backup và đồng bộ standby server. Cả ba tình huống đều liên quan đến việc đọc và replay WAL records, nhưng mục tiêu, nguồn WAL, trạng thái server và cách kết thúc recovery khác nhau.

Ba khái niệm cần phân biệt:

- **Crash recovery**: PostgreSQL tự phục hồi sau khi server dừng không sạch. Khi khởi động lại, nó đọc WAL còn cần thiết trong data directory để đưa database về trạng thái nhất quán gần nhất mà WAL đã lưu.
- **Archive recovery**: PostgreSQL khởi động từ một base backup và phát lại WAL được lấy từ archive, thường để phục hồi tới thời điểm, transaction hoặc LSN mong muốn (Point-in-Time Recovery — PITR).
- **Standby replay**: một standby server liên tục nhận WAL từ primary qua streaming replication và/hoặc WAL archive, sau đó replay để theo kịp primary. Nó thường tiếp tục ở recovery mode để sẵn sàng đọc read-only hoặc promote khi failover.

Cả ba dùng nền tảng WAL redo, nhưng không phải cùng một quy trình vận hành.

Bài **“Phân biệt crash recovery, archive recovery và standby replay”**, thuộc chương **WAL và checkpoint** của module **Database Engine Relational PostgreSQL**, giải thích nguồn WAL, checkpoint/redo, timeline, signal files, PITR targets, streaming replication, hot standby, đồng bộ commit, cách giám sát và các lab thực hành.

> **Cách nhớ:** Crash recovery khôi phục server vừa crash; archive recovery khôi phục một bản backup bằng WAL archive; standby replay giữ server phụ liên tục áp dụng WAL để theo primary. Standby replay và archive recovery có thể cùng dùng WAL archive, nhưng mục đích và lifecycle khác nhau.

---

## 1. Cả ba đều dựa trên WAL

Khi transaction thay đổi dữ liệu, PostgreSQL tạo WAL records. Data pages có thể chưa được ghi xuống table files ngay, nhưng WAL cho phép redo những thay đổi cần thiết sau crash.

~~~text
Transaction
    |
    v
WAL records
    |
    v
WAL buffers
    |
    v
WAL segment files
    |
    +--> Crash recovery
    |
    +--> Archive recovery / PITR
    |
    +--> Standby replay
~~~

WAL record có thể mô tả thao tác heap, index, transaction commit, checkpoint và các thay đổi cần thiết khác.

### 1.1. Recovery không phải “undo từng câu SQL”

PostgreSQL chủ yếu dùng WAL để **redo** những thay đổi đã được ghi log theo cơ chế recovery. Nó không vận hành theo kiểu đọc log rồi chạy ngược từng câu SQL để undo.

MVCC và transaction status quyết định những tuple versions nào nhìn thấy được. Những thao tác của transaction chưa commit không trở thành dữ liệu nghiệp vụ đã commit chỉ vì một phần WAL của chúng được redo.

## 2. Checkpoint tạo điểm bắt đầu redo

Checkpoint ghi các dirty data pages theo quy tắc WAL và lưu checkpoint record/state. Khi crash recovery, PostgreSQL có thể bắt đầu redo từ vị trí cần thiết dựa trên checkpoint gần nhất.

~~~text
WAL timeline:
---- WAL ---- [checkpoint] ---- WAL ---- WAL ---- crash
                   |
                   +--> recovery bắt đầu redo từ vị trí liên quan
~~~

Checkpoint giúp giảm lượng WAL cần replay sau crash. Nó không thay thế WAL archive và không phải một bản backup.

### 2.1. Checkpoint không phải mốc commit

Transaction có thể đã commit durable bằng WAL từ trước checkpoint. Checkpoint chỉ làm giảm lượng redo cần thiết khi recovery; nó không phải điều kiện để transaction được xác nhận.

## 3. So sánh ba loại recovery

| Tiêu chí | Crash recovery | Archive recovery / PITR | Standby replay |
|---|---|---|---|
| Tình huống | Server dừng không sạch | Restore từ base backup | Server phụ theo primary |
| Mục tiêu | Đưa data directory hiện tại về trạng thái nhất quán | Khôi phục backup tới điểm WAL/transaction | Áp dụng WAL liên tục để theo primary |
| Nguồn WAL | Chủ yếu WAL còn cần trong pg_wal | WAL archive, có thể kết hợp WAL local | Streaming replication và/hoặc archive |
| Khởi đầu | Server restart tự phát hiện crash | Restore base backup và cấu hình recovery | Chuẩn bị standby từ base backup |
| Signal file PG 12+ | Không cần signal riêng | recovery.signal | standby.signal |
| Trạng thái trong quá trình | Startup recovery | Archive recovery | Recovery/standby mode |
| Kết thúc | Server mở phục vụ bình thường | Đạt target hoặc hết WAL theo cấu hình, sau đó thực hiện action đã chọn | Thường tiếp tục chạy và replay WAL |
| Vai trò cuối | Primary được phục hồi | Instance phục hồi độc lập hoặc được promote | Standby sẵn sàng đọc/failover |

**Điểm quan trọng:** archive recovery và standby replay đều có thể dùng WAL archive. Sự khác nhau nằm ở ý định phục hồi và việc server có tiếp tục ở chế độ standby hay kết thúc recovery để hoạt động độc lập.

## 4. Crash recovery là gì?

Crash recovery xảy ra khi PostgreSQL restart sau một shutdown không sạch, chẳng hạn:

- Máy chủ mất điện.
- Hệ điều hành crash.
- PostgreSQL process bị kill bất ngờ.
- Server dừng bằng chế độ immediate.
- Kernel hoặc storage gặp sự cố làm server không hoàn tất shutdown bình thường.

PostgreSQL nhận ra data directory không có trạng thái shutdown checkpoint sạch và tự động chạy recovery.

### 4.1. Crash recovery không cần tạo recovery.signal

Trong tình huống restart bình thường sau crash, PostgreSQL tự nhận diện trạng thái cần recovery. Không cần tạo `recovery.signal` hay `standby.signal` để yêu cầu crash recovery.

### 4.2. Nguồn WAL chủ yếu là pg_wal hiện có

PostgreSQL sử dụng WAL còn cần trong data directory, thường từ checkpoint gần nhất đến cuối WAL hợp lệ mà server có thể đọc.

Nếu những WAL segments cần thiết bị thiếu hoặc hỏng, recovery có thể không hoàn tất. WAL archive có thể là một phần của quy trình phục hồi nâng cao, nhưng crash recovery tự động cơ bản không đồng nghĩa với PITR từ base backup.

## 5. Crash recovery diễn ra như thế nào?

~~~text
PostgreSQL dừng bất thường
          |
          v
Server khởi động
          |
          v
Đọc control/checkpoint state
          |
          v
Xác định redo start LSN
          |
          v
Đọc WAL trong pg_wal
          |
          v
Redo những thay đổi cần thiết
          |
          v
Phục hồi transaction/visibility state
          |
          v
Database đạt trạng thái consistent
          |
          v
Mở kết nối phục vụ bình thường
~~~

Đây là sơ đồ khái niệm. Startup và transaction state recovery có nhiều chi tiết nội bộ hơn.

## 6. Vì sao crash recovery redo WAL của transaction chưa commit?

Một transaction có thể đã tạo WAL records cho một số thay đổi trước khi crash nhưng chưa ghi commit record.

PostgreSQL có thể redo các page-level changes đó để phục hồi trạng thái vật lý nhất quán. Tuy nhiên transaction chưa commit vẫn không được coi là transaction nghiệp vụ đã commit.

Các tuple versions được nhận diện bằng transaction IDs/status và MVCC visibility. Recovery không biến transaction chưa commit thành dữ liệu hợp lệ chỉ vì redo đã chạy.

### 6.1. Không có undo SQL statement theo kiểu truyền thống

PostgreSQL sử dụng MVCC, transaction status và các cơ chế cleanup về sau. Sau recovery, row versions không thuộc transaction committed sẽ không hiển thị như dữ liệu đã commit; VACUUM sau đó có thể thu hồi chúng khi an toàn.

## 7. Clean shutdown và crash recovery

Các chế độ dừng qua pg_ctl:

~~~bash
pg_ctl stop -m smart
pg_ctl stop -m fast
pg_ctl stop -m immediate
~~~

- `smart`: chờ clients disconnect; shutdown sạch.
- `fast`: ngắt clients, rollback transactions đang chạy và shutdown sạch theo quy trình.
- `immediate`: dừng ngay, bỏ qua shutdown sạch; lần khởi động sau cần crash recovery.

Một service bị kill đột ngột cũng có thể cần crash recovery.

Không dùng immediate như cách dừng production thường xuyên.

## 8. Archive recovery là gì?

**Archive recovery** là quá trình PostgreSQL phục hồi từ một **base backup** bằng cách phát lại WAL đã được archive.

Một use case phổ biến là **Point-in-Time Recovery (PITR)**:

- Người dùng xóa nhầm một bảng.
- Một migration làm hỏng dữ liệu.
- Một transaction nghiệp vụ sai được commit.
- Cần khôi phục database tới trước một thời điểm/sự kiện.

Thay vì quay lại chỉ base backup cũ, PostgreSQL replay WAL từ backup đến target mong muốn.

~~~text
Base backup tại T0
      |
      v
WAL archive: T0 -> T1 -> T2 -> T3 -> T4
      |
      v
Replay đến target T3
      |
      v
Phục hồi database tại T3
~~~

Archive recovery thường tạo một **instance phục hồi độc lập**. Khi target đạt được và action là promote, instance ngừng recovery và hoạt động như primary mới trên timeline mới.

## 9. Base backup và WAL archive là hai thành phần khác nhau

Một base backup chứa trạng thái vật lý ban đầu của cluster tại một thời điểm. WAL archive chứa các WAL segments cần để tiến database từ trạng thái backup đến thời điểm mong muốn.

~~~text
Base backup
   +
WAL archive liên tục
   =
Khả năng PITR trong khoảng được bao phủ
~~~

Chỉ có WAL archive mà không có base backup phù hợp thì không đủ để dựng một cluster hoàn chỉnh.

Chỉ có base backup mà thiếu WAL cần thiết thì không thể replay vượt quá điểm backup consistency.

### 9.1. WAL archive phải liên tục

PITR yêu cầu chuỗi WAL cần thiết từ base backup tới recovery target. Nếu thiếu một segment bắt buộc, recovery sẽ dừng vì không thể tiếp tục redo qua khoảng trống đó.

Kiểm tra archive command, archive logs, checksum/backup validation và retention policy.

## 10. Cấu hình archive WAL

Trên primary, cấu hình thường liên quan:

~~~sql
SHOW wal_level;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
~~~

Một ví dụ khái niệm:

~~~text
wal_level = replica
archive_mode = on
archive_command = '... copy %p to archive location using %f ...'
~~~

`%p` là path WAL file nguồn, `%f` là tên file. Nội dung archive_command phụ thuộc OS, storage và cách bảo vệ archive.

### 10.1. Archive command phải an toàn khi retry

PostgreSQL có thể gọi lại archive_command khi lần archive trước thất bại. Command phải xử lý idempotently, tránh ghi đè nhầm một archive file hợp lệ và trả exit status đúng.

Không dùng một lệnh copy minh họa chưa kiểm tra cho production. Cần xử lý file tạm, atomic rename, checksum, quyền và lỗi storage.

## 11. Base backup bằng pg_basebackup

Một physical base backup có thể được tạo bằng `pg_basebackup` theo cấu hình phù hợp.

Ví dụ khái niệm:

~~~bash
pg_basebackup -h primary.example -D /backup/base -U replicator -X stream -P
~~~

Tham số và authentication phụ thuộc deployment. Backup cần được lưu ở nơi có retention và restore test.

### 11.1. Backup không phải archive

- Base backup cung cấp ảnh chụp vật lý.
- WAL archive cung cấp chuỗi thay đổi sau đó.
- PITR cần cả hai và một chuỗi WAL liên tục.

## 12. Khởi động archive recovery trong PostgreSQL 12+

Từ PostgreSQL 12, recovery configuration không còn nằm trong `recovery.conf`. Thay vào đó dùng file signal:

~~~text
recovery.signal
~~~

Để thực hiện archive recovery/PITR:

1. Restore base backup vào một data directory riêng.
2. Cấu hình `restore_command` để lấy WAL từ archive.
3. Đặt recovery target nếu muốn dừng ở một điểm cụ thể.
4. Tạo file `recovery.signal`.
5. Khởi động PostgreSQL.
6. Theo dõi log và recovery progress.
7. Khi target đạt, thực hiện action được cấu hình.

**Không tạo recovery.signal trên data directory production đang chạy.** Đây là quy trình restore trong data directory được chuẩn bị riêng.

### 12.1. recovery.signal và standby.signal

- `recovery.signal`: yêu cầu archive recovery.
- `standby.signal`: yêu cầu chạy như standby server.

Hai file phản ánh hai ý định khởi động khác nhau. Dùng đúng signal cho mục tiêu. Trong PostgreSQL 12+, nếu `standby.signal` tồn tại, server vào standby mode; tránh đặt cả hai tùy tiện vì standby mode có precedence theo startup behavior.

## 13. restore_command

`restore_command` cho PostgreSQL biết cách lấy một WAL file từ archive.

Ví dụ cấu hình khái niệm:

~~~text
restore_command = 'restore-tool %f %p'
~~~

Trong đó:

- `%f`: tên WAL file cần lấy.
- `%p`: đường dẫn đích mà PostgreSQL muốn file được restore.

Command phải trả success khi file được lấy thành công và failure khi không thể cung cấp file. PostgreSQL có thể gọi command nhiều lần với filenames khác nhau.

### 13.1. Restore command cần chịu được file không tồn tại

Khi đã replay hết archive hiện có, server có thể hỏi một segment chưa được archive. Command phải trả trạng thái “không có file” đúng cách, không báo thành công với file rỗng/không hợp lệ.

## 14. Recovery targets

Archive recovery có thể dừng tại một target:

| Target | Ý nghĩa |
|---|---|
| `recovery_target_time` | Thời điểm |
| `recovery_target_xid` | Transaction ID |
| `recovery_target_lsn` | LSN |
| `recovery_target_name` | Named restore point |
| `recovery_target = 'immediate'` | Dừng sớm tại điểm consistent phù hợp |

Ví dụ cấu hình khái niệm:

~~~text
recovery_target_time = '2026-11-14 09:30:00+07'
recovery_target_action = 'pause'
~~~

Timestamp phải có timezone rõ ràng để tránh nhầm giờ. Target được diễn giải theo semantics PostgreSQL; cần xác định chính xác thời điểm sự kiện đã commit.

### 14.1. recovery_target_inclusive

Tham số này điều khiển có bao gồm transaction/target record theo semantics target hay không. Mặc định thường là true. Khi phục hồi trước/sau một transaction cụ thể, cần hiểu inclusive behavior và test trên bản restore.

### 14.2. recovery_target_timeline

Có thể chọn timeline cụ thể hoặc `latest` để theo timeline mới nhất phù hợp. Timeline history files giúp PostgreSQL xác định quan hệ phân nhánh WAL sau các lần promote/PITR.

Không dùng latest như một bảo đảm tự động chọn “đúng lịch sử nghiệp vụ”; xác minh timeline và backup lineage.

## 15. recovery_target_action

Khi recovery target đạt được, `recovery_target_action` điều khiển hành động:

- `pause`: tạm dừng recovery tại target để DBA kiểm tra.
- `promote`: promote instance thành server hoạt động độc lập.
- `shutdown`: dừng server tại target theo cấu hình.

Giá trị mặc định thường là promote. Cấu hình target/action phải được xác minh theo PostgreSQL version.

### 15.1. pause hữu ích khi kiểm tra PITR

Có thể pause tại target, kiểm tra dữ liệu đã phục hồi và sau đó tiếp tục hoặc promote theo quyết định. Không để server pause vô thời hạn mà quên monitoring/storage/operations.

## 16. Restore point có tên

Trên primary trước sự kiện cần đánh dấu:

~~~sql
SELECT pg_create_restore_point('before_sensitive_migration');
~~~

Function tạo named restore point và trả LSN. Khi archive recovery, có thể chọn:

~~~text
recovery_target_name = 'before_sensitive_migration'
~~~

Restore point không tự tạo base backup và không tự đảm bảo WAL archive đã lưu mọi segment. Nó chỉ đánh dấu vị trí trong WAL stream.

### 16.1. Dùng restore point trước thao tác rủi ro

Một quy trình migration lớn có thể tạo restore point trước khi chạy. Nhưng vẫn cần base backup hợp lệ, WAL archive liên tục và test phục hồi.

## 17. Timeline là gì?

Mỗi lịch sử WAL thuộc một **timeline**. Timeline ID giúp PostgreSQL quản lý những nhánh lịch sử phát sinh khi một recovery được promote hoặc một standby được promote.

~~~text
Timeline 1
   |
   +---- WAL ---- WAL ---- WAL
                         |
                         | promote/PITR
                         v
                    Timeline 2
                         |
                         +---- WAL ---- WAL
~~~

Sau promote, server mới bắt đầu ghi WAL trên timeline mới. File history mô tả điểm timeline mới tách khỏi timeline trước.

### 17.1. Vì sao timeline quan trọng?

Một cluster có thể có nhiều nhánh WAL do failover/PITR. Restore cần chọn đúng timeline để không replay nhầm một lịch sử khác.

## 18. Archive recovery không nhất thiết là PITR

Archive recovery có thể replay WAL để đưa base backup đến điểm cuối có sẵn, không nhất thiết phải dừng tại một timestamp đã chọn.

PITR là một use case của archive recovery, trong đó DBA chọn recovery target để tránh một sự kiện xấu hoặc khôi phục tới trạng thái mong muốn.

- **Archive recovery** mô tả nguồn/phương thức replay từ archive.
- **PITR** mô tả mục tiêu phục hồi tới một điểm trong lịch sử.

## 19. Standby replay là gì?

Standby replay là quá trình một PostgreSQL standby liên tục áp dụng WAL do primary tạo ra.

WAL có thể đến từ:

- Streaming replication qua WAL receiver.
- WAL archive thông qua restore_command.
- WAL đã có sẵn trong pg_wal.

Standby thường ở recovery mode và tiếp tục chờ thêm WAL. Khác với PITR phục hồi độc lập đến một target rồi promote, standby replay có mục tiêu **theo kịp primary trong thời gian dài**.

~~~text
Primary
   |
   | WAL stream
   v
Standby WAL receiver
   |
   v
WAL files / receive position
   |
   v
Startup process replays WAL
   |
   v
Standby data state tiến gần primary
~~~

## 20. Chuẩn bị standby từ base backup

Một standby vật lý thường được tạo từ base backup của primary:

~~~bash
pg_basebackup -h primary.example -D /var/lib/postgresql/standby -U replicator -X stream -P -R
~~~

`-R` yêu cầu pg_basebackup tạo cấu hình standby phù hợp, thường bao gồm `standby.signal` và connection settings trong `postgresql.auto.conf`, theo version/tool behavior.

Sau đó cấu hình authentication, `primary_conninfo`, replication slot nếu dùng, WAL archive restore command và storage/network.

### 20.1. Standby phải bắt đầu từ base backup hợp lệ

Không chỉ copy thư mục data đang chạy bằng file copy thông thường. Dùng pg_basebackup hoặc phương pháp physical backup được hỗ trợ để đảm bảo consistency.

## 21. standby.signal

Trên PostgreSQL 12+, file:

~~~text
standby.signal
~~~

yêu cầu server chạy ở standby mode.

Trong standby mode, PostgreSQL tiếp tục recovery/replay WAL và chờ thêm WAL từ primary/archive. Nếu primary_conninfo được cấu hình, walreceiver có thể kết nối để nhận streaming WAL.

### 21.1. standby.signal khác recovery.signal

| File | Ý định |
|---|---|
| `recovery.signal` | Archive recovery/PITR |
| `standby.signal` | Continuous standby mode |

Đừng tạo file signal tùy tiện trên một cluster đang chạy. File được đọc khi startup.

## 22. primary_conninfo và walreceiver

Một standby thường cần `primary_conninfo`:

~~~text
primary_conninfo = 'host=primary.example port=5432 user=replicator application_name=standby_a'
~~~

Cấu hình chứa thông tin kết nối tới primary. Bảo vệ password/secret theo phương thức credential phù hợp; không commit secrets vào source control.

Walreceiver là process nhận WAL từ primary. Nó ghi WAL vào khu vực WAL của standby, sau đó startup process/recovery machinery replay các records.

### 22.1. Receive khác replay

WAL có thể đã được nhận và ghi vào standby nhưng chưa được replay tới data pages. Vì vậy receive LSN và replay LSN là hai mốc khác nhau.

## 23. Streaming replication và archive fallback

Standby có thể dùng `restore_command` để lấy WAL từ archive khi cần, sau đó streaming từ primary để theo kịp.

~~~text
Standby startup
      |
      v
Tìm WAL local
      |
      v
Thử lấy WAL archive nếu cần
      |
      v
Kết nối primary để streaming
      |
      v
Replay liên tục
~~~

Chi tiết thứ tự tìm WAL và retry phụ thuộc startup/recovery state. Điều quan trọng là archive và streaming có thể bổ trợ nhau; archive giúp standby bắt kịp khi WAL segment không còn trên primary nhưng đã được archive.

## 24. hot_standby

Nếu `hot_standby` được bật và recovery state phù hợp, standby có thể nhận read-only queries trong khi vẫn replay WAL.

~~~sql
SHOW hot_standby;

SELECT
    current_database(),
    pg_is_in_recovery();
~~~

Trong standby đang replay, `pg_is_in_recovery()` trả true.

### 24.1. Read-only không có nghĩa không có conflict

Standby query có thể xung đột với WAL replay, ví dụ recovery cần cleanup versions mà query standby vẫn đang sử dụng. PostgreSQL có cơ chế recovery conflict và có thể cancel query theo cấu hình/chính sách.

Hot standby là read-only query mode, không phải primary thứ hai cho writes.

## 25. Standby replay và promotion

Khi cần failover, standby có thể được promote thành primary mới.

~~~sql
SELECT pg_promote();
~~~

hoặc dùng công cụ quản lý/pg_ctl tương ứng.

Sau promote:

- Server kết thúc standby recovery mode.
- Bắt đầu chấp nhận writes theo role primary.
- Tạo timeline mới.
- Không còn tiếp tục replay WAL từ primary cũ như một standby bình thường.

Promotion là một quyết định failover; phải có fencing/STONITH hoặc cơ chế bảo đảm primary cũ không tiếp tục nhận writes gây split brain.

## 26. pg_is_in_recovery

~~~sql
SELECT pg_is_in_recovery();
~~~

Function trả true khi server đang ở recovery mode (bao gồm standby). Trả false khi server hoạt động bình thường sau recovery/promote.

Đây là phép kiểm tra hữu ích trong health checks và ứng dụng cần phân biệt primary/standby.

Không chỉ dựa vào function này để chọn primary trong hệ thống failover phức tạp; kết hợp cluster manager, routing và fencing.

## 27. Theo dõi WAL receive và replay LSN

Trên standby:

~~~sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
~~~

- `pg_last_wal_receive_lsn()`: vị trí WAL gần nhất đã nhận từ streaming replication.
- `pg_last_wal_replay_lsn()`: vị trí WAL gần nhất đã replay.
- `pg_last_xact_replay_timestamp()`: thời điểm transaction cuối cùng được replay theo metadata tương ứng.

### 27.1. Timestamp replay có giới hạn

Nếu primary không có transaction mới, timestamp replay có thể cũ dù standby hoàn toàn caught up. Không dùng riêng timestamp này để kết luận lag; so sánh LSN và trạng thái primary/standby.

## 28. Quan sát walreceiver

Trên standby:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

View cho biết trạng thái WAL receiver, nguồn upstream, slot, receive LSN và thông tin liên quan tùy version.

Nếu view không có rows, có thể standby không streaming ở thời điểm đó; nó có thể đang replay archive, chưa kết nối primary hoặc không ở standby mode.

## 29. Quan sát primary replication state

Trên primary:

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
    replay_lsn
FROM pg_stat_replication;
~~~

Đây là góc nhìn primary về các WAL sender connections.

Một standby có thể nhận WAL nhưng replay chậm. So sánh sent/write/flush/replay để phân biệt network/receiver/flush/replay lag.

## 30. Synchronous replication và thời điểm commit

Standby replay và synchronous replication liên quan nhưng không giống nhau.

Primary có thể cấu hình `synchronous_standby_names`, và transaction dùng `synchronous_commit`:

- `remote_write`: chờ standby ghi WAL vào OS.
- `on`: chờ standby flush WAL theo sync policy.
- `remote_apply`: chờ standby replay/apply transaction.
- `local`: chỉ chờ local flush.
- `off`: có thể trả success trước local flush.

`remote_apply` là mức có thể đảm bảo transaction đã được apply trên synchronous standby được chọn trước khi primary trả commit success. Nó không có nghĩa mọi replicas trong hệ thống đều đã replay.

### 30.1. Async standby có thể mất WAL gần đây khi failover

Nếu primary xác nhận commit mà không đợi standby nhận/flush, standby có thể bị tụt lại. Nếu promote standby ngay sau primary crash, những transactions gần đây có thể không có trên standby.

RPO phụ thuộc sync mode, topology, network và failover policy.

## 31. Crash recovery và standby replay dùng cùng redo machinery

Cả hai đều sử dụng WAL redo để cập nhật pages theo lịch sử WAL.

Khác biệt chính:

- Crash recovery chạy sau shutdown không sạch và thường kết thúc để server hoạt động bình thường.
- Standby replay tiếp tục ở recovery mode, nhận thêm WAL và giữ server ở trạng thái standby.
- Standby có thể được promote để trở thành primary.

Đây là khác biệt về **lifecycle và mục tiêu**, không phải một thuật toán redo hoàn toàn khác.

## 32. Archive recovery và standby replay cùng dùng restore_command

Một standby có thể lấy WAL từ archive qua `restore_command`. Một PITR restore cũng lấy WAL từ archive.

Nhưng:

- PITR thường dừng tại target và promote/pauses/shutdown.
- Standby tiếp tục chờ WAL mới và giữ `standby.signal`.
- Một standby có thể kết hợp archive restore với streaming replication.

Không phân biệt hai trường hợp chỉ bằng việc thấy restore_command được cấu hình.

## 33. recovery_target_time và transaction boundaries

Ví dụ:

~~~text
recovery_target_time = '2026-11-14 09:30:00+07'
recovery_target_action = 'pause'
~~~

Target time được so sánh với transaction commit timing theo semantics PostgreSQL. Nếu nhiều transactions ở gần target, cần xác minh dữ liệu sau recovery, không giả định target là một câu SQL cụ thể.

Có thể chọn `recovery_target_xid` hoặc named restore point nếu cần điểm tham chiếu rõ hơn.

## 34. recovery_target_timeline và history files

Khi một standby được promote, PostgreSQL tạo timeline mới và file history tương ứng. PITR có thể chọn timeline theo cấu hình.

`recovery_target_timeline = 'latest'` cho phép theo timeline mới nhất có thể tìm thấy qua history files phù hợp.

Điều này hữu ích trong môi trường failover nhiều lần, nhưng cần đảm bảo archive có đầy đủ WAL và `.history` files.

### 34.1. Không xóa history files tùy tiện

Timeline history files giúp xác định nhánh WAL và điểm fork. Thiếu chúng có thể làm recovery chọn sai hoặc không thể theo timeline mong muốn.

## 35. Recovery consistency và control data

PostgreSQL dùng control file/checkpoint state để xác định trạng thái cluster và recovery start.

Công cụ:

~~~bash
pg_controldata /path/to/data_directory
~~~

cho phép xem control information như checkpoint location, timeline và trạng thái cluster theo version.

Không sửa control file bằng hex editor hoặc tự thay checkpoint LSN. Đây là metadata quan trọng của cluster.

## 36. Log messages khi recovery

Khi startup, log có thể chứa thông tin:

- Database system was interrupted.
- Starting crash recovery.
- Redo starts at LSN.
- Redo done at LSN.
- Consistent recovery state reached.
- Entering standby mode.
- Started streaming WAL from primary.
- Recovery paused/reached target.
- Database system is ready to accept connections.

Thông điệp chính xác tùy version và recovery path. Dùng logs cùng `pg_is_in_recovery()` và LSN metrics để xác định server đang ở pha nào.

## 37. PITR và archive gap

Nếu restore command không tìm được một WAL segment cần thiết:

- Archive recovery có thể dừng.
- Log ghi rõ không lấy được WAL file.
- Database không thể tiến qua điểm thiếu WAL.
- Target nằm sau gap không thể đạt được từ backup/archives đó.

Đừng bỏ qua lỗi bằng cách tạo WAL file rỗng có cùng tên. Cần phục hồi segment từ archive replica/backup hoặc chọn một target trước gap nếu hợp lệ.

## 38. Archive command thất bại và pg_wal tăng

Nếu `archive_command` thất bại liên tục, PostgreSQL giữ WAL cần archive thay vì recycle như bình thường, và `pg_wal` có thể tăng.

Theo dõi:

- Archive failures trong logs.
- `pg_stat_archiver` trên version có view.
- Filesystem free space.
- WAL generation rate.
- Archive destination connectivity/permissions.
- `archive_timeout` và workload segment switching.

Không xóa WAL chưa archive bằng filesystem commands để giải phóng disk.

## 39. pg_stat_archiver

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

View cho biết số archive thành công/thất bại và thông tin lần gần nhất. Nó không chứng minh archive repository đã có retention, replication và restore validation đầy đủ.

Nếu failed_count tăng, kiểm tra archive_command logs và destination.

## 40. archive_timeout

~~~sql
SHOW archive_timeout;
~~~

Tham số này có thể buộc switch WAL segment theo khoảng thời gian để archive WAL thường xuyên hơn, ngay cả khi segment chưa đầy.

Nó ảnh hưởng tần suất archive/độ trễ archive ở một số workload, nhưng không biến archive thành synchronous commit và không bảo đảm mỗi transaction được archive trước khi COMMIT trả về.

## 41. Backup verification và restore testing

Một backup được tạo thành công chưa đủ để chứng minh có thể phục hồi.

Thực hành:

- Xác minh backup hoàn tất.
- Kiểm tra manifest/backup integrity bằng công cụ phù hợp, ví dụ `pg_verifybackup` cho backup tương ứng.
- Kiểm tra WAL archive liên tục.
- Thử restore base backup.
- Thử replay tới một target.
- Xác nhận application data và constraints.
- Đo thời gian restore/replay.
- Ghi lại RPO/RTO đạt được.

**Restore test** mới chứng minh quy trình backup + WAL + recovery có thể vận hành.

## 42. Lab: phân biệt crash recovery bằng shutdown immediate

Chỉ thực hiện trên một PostgreSQL lab riêng, không phải cluster dùng chung.

Tạo bảng:

~~~sql
CREATE TABLE recovery_lab (
    id BIGINT PRIMARY KEY,
    note TEXT
);

INSERT INTO recovery_lab VALUES (1, 'before restart');
~~~

Sau đó dùng pg_ctl/service manager của môi trường lab để dừng bằng immediate mode và khởi động lại.

Quan sát startup logs: PostgreSQL nhận ra shutdown không sạch và chạy crash recovery.

Kiểm tra:

~~~sql
SELECT *
FROM recovery_lab;
~~~

Dữ liệu đã commit phải tồn tại theo durability/storage setup.

### 42.1. Không dùng power cut trên máy thật

Mô phỏng crash phải diễn ra trong VM/container/test cluster cô lập. Không kill storage hoặc power off máy production để thử WAL recovery.

## 43. Lab: archive recovery/PITR

Trong lab riêng, thiết lập:

1. `wal_level` và `archive_mode` phù hợp.
2. `archive_command` lưu WAL vào archive location bền vững.
3. Tạo base backup.
4. Ghi một số transactions có timestamp/restore point.
5. Tạo thêm một transaction sai để mô phỏng sự kiện cần tránh.
6. Restore base backup sang data directory mới.
7. Cấu hình `restore_command`.
8. Đặt `recovery.signal` và target trước transaction sai.
9. Khởi động restored instance.
10. Kiểm tra dữ liệu đã phục hồi.

Không ghi đè data directory primary trong lab. Đảm bảo WAL archive có đủ segments từ backup tới target.

## 44. Lab: standby replay

Trong hai PostgreSQL lab instances:

**Primary:**

- Bật cấu hình replication cần thiết.
- Tạo replication role và pg_hba rule phù hợp.
- Có `wal_level=replica` hoặc cao hơn.
- Cấu hình `max_wal_senders` và slot nếu dùng.

**Standby:**

- Tạo base backup bằng pg_basebackup.
- Dùng `-R` hoặc cấu hình `standby.signal` + `primary_conninfo`.
- Khởi động standby.
- Query `pg_is_in_recovery()`.
- Insert trên primary và quan sát row xuất hiện trên standby sau replay.

Trên standby:

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
~~~

Standby mặc định chỉ đọc trong quá trình recovery.

## 45. Lab: pause và resume replay

Trong môi trường standby lab:

~~~sql
SELECT pg_wal_replay_pause();
~~~

Quan sát replay LSN ngừng tiến trong khi primary tiếp tục ghi WAL.

Sau đó:

~~~sql
SELECT pg_wal_replay_resume();
~~~

Replay tiếp tục khi có WAL sẵn sàng.

Chỉ pause replay trong lab/maintenance có chủ đích; nó làm standby lag tăng và có thể giữ WAL/ảnh hưởng mục tiêu failover.

## 46. Lab: promote standby

Trên standby lab:

~~~sql
SELECT pg_promote();
~~~

Sau promote:

~~~sql
SELECT pg_is_in_recovery();
~~~

Kết quả chuyển sang false khi promotion hoàn tất và server hoạt động như primary.

Kiểm tra timeline/history và khả năng ghi. Trong production cần fencing primary cũ và cập nhật routing/cluster manager để tránh split brain.

## 47. Chọn loại recovery theo tình huống

| Sự cố/nhu cầu | Cách phù hợp |
|---|---|
| PostgreSQL process/máy crash, data directory còn hợp lệ | Crash recovery |
| Muốn khôi phục database trước một lệnh DELETE sai | Base backup + archive recovery/PITR |
| Cần database phụ theo primary liên tục | Physical standby replay |
| Primary mất, cần chuyển dịch vụ sang standby | Promote standby theo failover procedure |
| Muốn khôi phục một bảng/nhóm rows từ backup cũ | Restore riêng rồi export/import dữ liệu |
| Thiếu WAL segment cần cho PITR | Tìm lại archive segment hoặc chọn target sớm hơn hợp lệ |

Không dùng crash recovery để giải quyết một logical data error đã commit; crash recovery sẽ giữ transaction committed theo lịch sử database.

## 48. RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất.
- **RTO (Recovery Time Objective):** thời gian tối đa để dịch vụ phục hồi.

| Phương pháp | RPO phụ thuộc | RTO phụ thuộc |
|---|---|---|
| Crash recovery | WAL durable còn lại trên storage | Startup, redo volume, I/O |
| Archive recovery/PITR | Archive continuity và target có thể đạt | Restore base backup + WAL replay |
| Standby replay | Sync/async replication lag và failover state | Promotion, fencing, routing |

Một async standby có thể mất các commits chưa được nhận/replay nếu primary crash. Synchronous replication với policy phù hợp có thể giảm RPO nhưng tăng commit latency và phụ thuộc standby availability.

## 49. Synchronous replication không phải archive backup

Synchronous standby là server nhận WAL online. WAL archive là repository lưu WAL segments cho backup/PITR.

Chúng giải quyết những failure modes khác nhau:

- Standby hỗ trợ failover nhanh.
- Archive hỗ trợ PITR và phục hồi lịch sử.
- Base backup + archive giúp khôi phục khi cả primary/standby bị hỏng hoặc cần quay về trước một lỗi logic.

Một hệ thống production thường cần cả backup/archive và standby, cùng restore tests.

## 50. Những hiểu lầm thường gặp

### 50.1. Crash recovery là restore từ backup

Sai. Crash recovery dùng data directory hiện tại và WAL cần thiết để phục hồi sau shutdown không sạch.

### 50.2. Archive recovery và standby replay là một

Sai. Cùng dùng WAL archive được, nhưng PITR thường kết thúc ở target; standby tiếp tục chạy recovery và nhận WAL.

### 50.3. Chỉ cần WAL archive, không cần base backup

Sai. Muốn dựng cluster cần base backup hợp lệ.

### 50.4. Có base backup là đủ PITR

Sai. Cần chuỗi WAL liên tục từ backup tới target.

### 50.5. Standby đã nhận WAL là đã replay

Sai. Receive LSN và replay LSN khác nhau.

### 50.6. hot_standby cho phép ghi trên replica

Sai. Queries trên hot standby là read-only trong recovery.

### 50.7. pg_last_xact_replay_timestamp luôn đo lag chính xác

Sai. Nếu primary idle, timestamp cuối có thể cũ dù standby caught up.

### 50.8. recovery.signal dùng cho mọi loại recovery

Sai. Crash recovery tự động; recovery.signal cho archive recovery; standby.signal cho standby mode.

### 50.9. Promote chỉ đổi một flag

Sai. Promote kết thúc recovery, tạo timeline mới và thay đổi vai trò server; cần fencing/routing.

### 50.10. Archive command thành công nghĩa backup có thể restore

Sai. Cần xác minh archive continuity, base backup, timeline và restore test.

### 50.11. archive_timeout đồng nghĩa synchronous commit

Sai. Nó tác động segment switching/archive frequency, không bảo đảm archive trước COMMIT.

### 50.12. synchronous_commit=on nghĩa mọi standby đã replay

Sai. on đợi remote flush trên synchronous standby theo policy; remote_apply mới đợi apply/replay.

### 50.13. Xóa WAL file thủ công là cách chữa archive backlog

Sai. Có thể làm mất WAL cần cho crash recovery/replication/PITR và phá cluster.

## 51. Checklist vận hành recovery

**Crash recovery**

1. Xác định server dừng clean hay immediate/crash.
2. Giữ nguyên data directory và WAL.
3. Đọc startup logs.
4. Xác định redo start/end và checkpoint.
5. Kiểm tra storage/filesystem errors.
6. Xác nhận server consistent và mở connections.

**Archive recovery/PITR**

7. Có base backup phù hợp?
8. Có đầy đủ WAL segments từ backup đến target?
9. Archive repository và timeline history files còn đủ?
10. restore_command có thể lấy đúng file?
11. Target time/XID/LSN/name có timezone/semantics rõ?
12. recovery_target_action có được chọn rõ?
13. Restore trên data directory/host riêng?
14. Đã test application data sau recovery?

**Standby replay**

15. Base backup standby hợp lệ?
16. standby.signal và primary_conninfo đúng?
17. WAL receiver đang kết nối?
18. Receive/replay LSN có tiến?
19. hot_standby có bật nếu cần read-only queries?
20. Có recovery conflicts?
21. Sync/async mode có phù hợp RPO?
22. Promotion có fencing/routing an toàn?

**Disaster recovery**

23. Backup + WAL archive có restore test?
24. RPO/RTO đo thực tế?
25. Có giám sát archive failures và disk capacity?
26. Có playbook failover/PITR được review?

## 52. Bài tập thực hành

### Bài 1 — Crash recovery

Khi nào PostgreSQL tự chạy crash recovery?

**Gợi ý:** sau shutdown không sạch/crash.

### Bài 2 — Archive recovery

Archive recovery cần hai thành phần dữ liệu nền tảng nào?

**Gợi ý:** base backup và WAL archive liên tục.

### Bài 3 — Standby replay

Mục tiêu chính của standby replay là gì?

**Gợi ý:** liên tục áp dụng WAL để theo primary.

### Bài 4 — WAL redo

Tại sao cả ba loại recovery đều liên quan WAL redo?

**Gợi ý:** WAL mô tả thay đổi cần áp dụng.

### Bài 5 — Checkpoint

Checkpoint giúp recovery điều gì?

**Gợi ý:** xác định redo start và giảm lượng WAL phải replay.

### Bài 6 — Crash transaction

WAL records của transaction chưa commit có thể được redo không?

**Gợi ý:** có thể redo physical changes; transaction vẫn không committed/visible.

### Bài 7 — Clean shutdown

pg_ctl immediate khác fast ở đâu?

**Gợi ý:** immediate không clean shutdown và cần crash recovery.

### Bài 8 — recovery.signal

File này yêu cầu chế độ gì?

**Gợi ý:** archive recovery.

### Bài 9 — standby.signal

File này yêu cầu chế độ gì?

**Gợi ý:** standby.

### Bài 10 — PostgreSQL 12

Từ PostgreSQL 12, recovery.conf được thay bằng gì?

**Gợi ý:** signal files và recovery parameters trong postgresql.conf/auto.conf.

### Bài 11 — restore_command

Hai placeholder quan trọng là gì?

**Gợi ý:** %f và %p.

### Bài 12 — PITR

recovery_target_time có tác dụng gì?

**Gợi ý:** dừng replay tại target time.

### Bài 13 — Target action

Nêu ba recovery_target_action values.

**Gợi ý:** pause, promote, shutdown.

### Bài 14 — Restore point

Function nào tạo named restore point?

**Gợi ý:** pg_create_restore_point.

### Bài 15 — Timeline

Vì sao promote tạo timeline mới?

**Gợi ý:** tạo nhánh lịch sử WAL mới.

### Bài 16 — History file

Timeline history file dùng làm gì?

**Gợi ý:** mô tả điểm fork/quan hệ timeline.

### Bài 17 — Base backup

Vì sao archive WAL không thay base backup?

**Gợi ý:** WAL chỉ mô tả thay đổi, không dựng toàn bộ cluster từ đầu.

### Bài 18 — Archive gap

Điều gì xảy ra nếu thiếu WAL segment cần thiết?

**Gợi ý:** recovery không thể replay qua gap.

### Bài 19 — Standby receive

Function nào trả receive LSN?

**Gợi ý:** pg_last_wal_receive_lsn.

### Bài 20 — Standby replay

Function nào trả replay LSN?

**Gợi ý:** pg_last_wal_replay_lsn.

### Bài 21 — Recovery state

Function nào kiểm tra server đang recovery?

**Gợi ý:** pg_is_in_recovery.

### Bài 22 — WAL receiver

View nào quan sát WAL receiver?

**Gợi ý:** pg_stat_wal_receiver.

### Bài 23 — Primary view

View nào quan sát WAL sender/standby progress từ primary?

**Gợi ý:** pg_stat_replication.

### Bài 24 — hot_standby

Hot standby cho phép loại query nào?

**Gợi ý:** read-only.

### Bài 25 — Recovery conflict

Vì sao query trên standby có thể bị cancel?

**Gợi ý:** xung đột với WAL replay/cleanup.

### Bài 26 — Promotion

Function nào có thể promote standby?

**Gợi ý:** pg_promote.

### Bài 27 — Split brain

Vì sao cần fencing primary cũ trước/đồng thời promote?

**Gợi ý:** tránh hai primary nhận writes.

### Bài 28 — Sync replication

remote_write, on và remote_apply khác nhau thế nào?

**Gợi ý:** standby write, flush và apply.

### Bài 29 — Async replication

Failover sang async standby có thể mất gì?

**Gợi ý:** commits chưa nhận/replay.

### Bài 30 — Archive timeout

archive_timeout có buộc COMMIT chờ archive không?

**Gợi ý:** không.

### Bài 31 — Archive failure

Vì sao pg_wal có thể tăng khi archive_command thất bại?

**Gợi ý:** WAL chưa archive không được recycle như bình thường.

### Bài 32 — pg_stat_archiver

Nêu ba metrics hữu ích.

**Gợi ý:** archived_count, failed_count, last_failed_wal/time.

### Bài 33 — Restore verification

Vì sao cần restore test?

**Gợi ý:** backup thành công không chứng minh khôi phục được.

### Bài 34 — pg_verifybackup

Công cụ này hỗ trợ kiểm tra điều gì?

**Gợi ý:** integrity của base backup phù hợp.

### Bài 35 — RPO

RPO biểu thị điều gì?

**Gợi ý:** lượng dữ liệu tối đa có thể mất.

### Bài 36 — RTO

RTO biểu thị điều gì?

**Gợi ý:** thời gian phục hồi mục tiêu.

### Bài 37 — PITR lab

Nêu các bước chính restore base backup đến trước một transaction sai.

**Gợi ý:** restore, restore_command, recovery.signal, target, replay.

### Bài 38 — Standby lab

Làm sao kiểm tra standby đã replay tới đâu?

**Gợi ý:** so receive/replay LSN.

### Bài 39 — Recovery target timeline

Vì sao cần history files khi phục hồi sau nhiều lần promote?

**Gợi ý:** chọn đúng nhánh WAL.

### Bài 40 — Lựa chọn recovery

Một DBA cần khôi phục database về trước lệnh DROP TABLE đã commit. Chọn phương pháp nào?

**Gợi ý:** PITR từ base backup và WAL archive.

## 53. Câu hỏi thường gặp

### Crash recovery có cần base backup không?

Không trong tình huống thông thường. Nó phục hồi data directory hiện tại bằng WAL còn cần sau crash. Nếu data directory hỏng/mất thì cần backup/restore.

### Archive recovery có phải luôn là PITR không?

Không. Archive recovery mô tả replay từ archive; PITR là use case dừng ở một target cụ thể.

### Standby replay có dùng WAL archive không?

Có thể. Standby có thể kết hợp archive restore và streaming replication.

### recovery.signal và standby.signal khác nhau thế nào?

recovery.signal yêu cầu archive recovery; standby.signal yêu cầu continuous standby mode.

### Một standby nhận WAL rồi có thể đọc ngay dữ liệu mới không?

Không nhất thiết. WAL cần được replay; receive LSN có thể tiến trước replay LSN.

### hot_standby có cho phép INSERT/UPDATE trên standby không?

Không. Queries trên hot standby là read-only trong recovery.

### Promote có làm mất khả năng replay primary cũ không?

Sau promote, server trở thành một timeline mới và hoạt động như primary. Muốn rejoin cần quy trình thích hợp, ví dụ pg_rewind hoặc rebuild tùy trạng thái/timeline.

### Synchronous commit on có đợi standby replay không?

Không theo nghĩa apply. Nó đợi remote flush của synchronous standby; remote_apply mới đợi replay/apply.

### Archive WAL có thay backup không?

Không. Cần base backup phù hợp cùng chuỗi WAL liên tục.

### archive_timeout có bảo đảm mọi transaction đã archive khi COMMIT trả về không?

Không. Archive segment và commit acknowledgment là hai quy trình khác nhau.

### Nếu thiếu một WAL segment thì sao?

Recovery không thể replay qua khoảng trống đó. Cần lấy lại segment hoặc chọn target trước gap nếu hợp lệ.

### pg_last_xact_replay_timestamp có đo lag tuyệt đối không?

Không. Primary idle có thể khiến timestamp cũ dù standby đã caught up. So sánh LSN và primary/standby state.

### Có thể chạy crash recovery thủ công bằng cách tạo recovery.signal không?

Không cần. Crash recovery được PostgreSQL tự phát hiện. recovery.signal dành cho archive recovery.

### Backup đã hoàn tất có chắc restore được không?

Không. Cần kiểm tra integrity, WAL continuity và thực hiện restore test.

## 54. Tổng kết

Các function/view/file quan trọng:

~~~sql
-- Server có đang recovery/standby không?
SELECT pg_is_in_recovery();

-- Trên standby: nhận và replay progress.
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();

-- Trên standby: receiver state.
SELECT * FROM pg_stat_wal_receiver;

-- Trên primary: standby progress.
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;

-- Archive health.
SELECT * FROM pg_stat_archiver;

-- Tạo restore point trước thay đổi quan trọng.
SELECT pg_create_restore_point('before_migration');

-- Promote standby theo failover procedure.
SELECT pg_promote();

-- Pause/resume standby replay trong lab.
SELECT pg_wal_replay_pause();
SELECT pg_wal_replay_resume();
~~~

Những nguyên tắc cần nhớ:

1. **Crash recovery** tự chạy sau shutdown không sạch, sử dụng WAL còn cần trong data directory.
2. **Archive recovery** bắt đầu từ base backup và replay WAL archive; PITR là việc chọn một recovery target.
3. **Standby replay** áp dụng WAL liên tục để standby theo primary, thường qua streaming và/hoặc archive.
4. Cả ba dùng WAL redo nhưng khác mục tiêu, nguồn WAL, signal file và lifecycle.
5. Checkpoint giúp xác định redo start; nó không thay base backup hoặc WAL archive.
6. Transaction chưa commit không trở thành committed chỉ vì WAL records của nó được redo.
7. PostgreSQL 12+ dùng recovery.signal cho archive recovery và standby.signal cho standby mode.
8. PITR cần base backup hợp lệ và chuỗi WAL liên tục.
9. Recovery target có thể dựa trên time, XID, LSN hoặc named restore point.
10. Timeline/history files quan trọng sau promote/PITR.
11. Standby receive LSN và replay LSN là hai tiến độ khác nhau.
12. Hot standby cung cấp read-only queries trong recovery, có thể gặp recovery conflicts.
13. Promotion tạo primary/timeline mới và cần fencing để tránh split brain.
14. synchronous_commit=on đợi remote flush theo synchronous replication policy; remote_apply đợi replay.
15. Async standby có thể thiếu những commits gần đây khi failover.
16. WAL archive và synchronous standby giải quyết những failure modes khác nhau; production thường cần cả hai.
17. archive_command failure có thể khiến pg_wal tăng; không xóa WAL thủ công.
18. Backup cần được verify và restore test; RPO/RTO phải đo thực tế.

Sơ đồ lựa chọn:

~~~text
PostgreSQL cần phục hồi?
        |
        +--> Server vừa crash, data directory còn nguyên?
        |          |
        |          v
        |      Crash recovery
        |      WAL local + checkpoint
        |
        +--> Cần restore backup tới một thời điểm?
        |          |
        |          v
        |      Archive recovery / PITR
        |      Base backup + WAL archive
        |      recovery.signal + target
        |
        +--> Cần server phụ theo primary liên tục?
                   |
                   v
               Standby replay
               standby.signal
               Streaming/archive WAL
                   |
                   +--> Read-only hot standby
                   |
                   +--> Promote khi failover
~~~

**Kết luận:** Crash recovery, archive recovery và standby replay đều dựa trên WAL, nhưng phục vụ ba mục tiêu khác nhau: **khôi phục server sau crash, phục hồi một bản backup tới điểm lịch sử, và duy trì một standby theo primary**. Thiết kế backup/failover đúng cần phân biệt nguồn WAL, signal files, timeline, target và acknowledgment semantics; chỉ khi kết hợp base backup, archive liên tục, standby được giám sát và restore/failover tests, hệ thống mới có một quy trình phục hồi đáng tin cậy.
