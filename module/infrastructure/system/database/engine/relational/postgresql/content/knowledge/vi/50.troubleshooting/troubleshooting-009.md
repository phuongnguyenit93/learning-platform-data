# Phục hồi bị kẹt, lỗi archive và thiếu chuỗi WAL

PostgreSQL dùng Write-Ahead Log (WAL) để bảo đảm tính nhất quán khi ghi dữ liệu và để truyền thay đổi sang standby. Khi cần khôi phục từ base backup, PostgreSQL phải đọc và phát lại một chuỗi WAL liên tục đến điểm cần phục hồi. Nếu một segment không được archive, bị hỏng, nằm sai timeline hoặc không thể tải về, quá trình recovery có thể dừng trước điểm đích.

Một cụm database có thể trông như đang “kẹt” vì nhiều nguyên nhân khác nhau: standby đang chờ WAL mới một cách bình thường, PITR đã đến recovery target và đang pause có chủ đích, restore command liên tục thất bại, archive bị thiếu một segment, hoặc storage không còn dung lượng. Cần xác định đúng trạng thái trước khi can thiệp. Xóa WAL, promote standby hoặc khởi động lại liên tục khi chưa hiểu nguyên nhân có thể làm mất khả năng khôi phục.

## 1. WAL, archive và recovery liên quan với nhau thế nào?

WAL ghi lại thay đổi ở mức thấp để PostgreSQL có thể redo các thao tác sau crash hoặc khi khôi phục từ backup. WAL được chia thành các segment có tên định danh theo timeline, log và segment number. Kích thước segment thường là 16 MB trong cấu hình mặc định, nhưng có thể khác nếu được chọn khi khởi tạo cluster; không nên giả định kích thước này trong công cụ kiểm tra.

Có ba hoạt động cần phân biệt:

- **WAL generation:** primary tạo WAL khi transaction và các hoạt động nội bộ làm thay đổi dữ liệu.
- **WAL archiving:** PostgreSQL chuyển các segment WAL đã hoàn tất sang kho archive bền vững.
- **WAL replay:** PostgreSQL đọc WAL và áp dụng lại các thay đổi lên data directory trong crash recovery, archive recovery hoặc standby recovery.

Một quy trình PITR (Point-in-Time Recovery) điển hình cần base backup và toàn bộ WAL bắt buộc kể từ điểm bắt đầu backup cho đến điểm đích. Nếu thiếu một segment ở giữa chuỗi, PostgreSQL không thể bỏ qua segment đó để tiếp tục như thể dữ liệu vẫn đầy đủ.

~~~mermaid
flowchart TD
    A[Base backup nhất quán] --> B[WAL segment tiếp theo]
    B --> C[WAL segment kế tiếp]
    C --> D[WAL segment ...]
    D --> E[WAL chứa recovery target]
    E --> F[Database phục hồi đến điểm đích]
    C --> X[Thiếu hoặc hỏng một segment]
    X --> Y[Recovery không thể tiếp tục qua khoảng trống]
~~~

Archive và replication có liên quan nhưng không thay thế nhau. Standby có thể nhận WAL qua streaming replication, qua archive recovery hoặc lần lượt thử cả hai tùy cấu hình. Backup archive phục vụ phục hồi dài hạn; streaming replication chủ yếu giữ standby cập nhật theo primary đang hoạt động.

### Những khái niệm cần phân biệt

| Thành phần | Vai trò |
|---|---|
| Base backup | Bản sao vật lý nhất quán làm điểm bắt đầu phục hồi |
| WAL segment | Đơn vị file chứa chuỗi bản ghi WAL |
| WAL archive | Kho lưu trữ các segment đã hoàn tất, thường nằm ngoài data directory |
| Timeline | Nhánh lịch sử WAL; timeline mới thường xuất hiện sau khi promote hoặc kết thúc một nhánh recovery |
| restore_command | Lệnh PostgreSQL gọi để lấy một file cần thiết từ archive |
| archive_command | Lệnh PostgreSQL gọi để chuyển segment đã hoàn tất vào archive |
| recovery target | Thời điểm, transaction hoặc vị trí WAL mà quá trình PITR cần dừng tại đó |

## 2. Phân biệt standby đang chờ WAL và recovery thực sự bị lỗi

Không phải mọi trạng thái recovery kéo dài đều là lỗi. Một standby đang hoạt động có thể đã replay hết WAL hiện có và chờ primary gửi thêm. Nếu primary không tạo transaction mới, LSN replay có thể đứng yên trong thời gian dài mà hệ thống vẫn bình thường.

Một PITR cũng có thể pause có chủ đích khi đã đến recovery target. Với cấu hình `recovery_target_action = 'pause'`, PostgreSQL dừng replay tại điểm đích để người vận hành kiểm tra dữ liệu trước khi promote. Trạng thái này khác với lỗi thiếu WAL.

Trước tiên xác định instance đang ở chế độ nào:

~~~sql
SELECT
    pg_is_in_recovery() AS is_in_recovery,
    pg_is_wal_replay_paused() AS replay_is_paused,
    pg_last_wal_receive_lsn() AS last_received_lsn,
    pg_last_wal_replay_lsn() AS last_replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_time;
~~~

Diễn giải:

- `pg_is_in_recovery() = false`: instance đang hoạt động như primary sau khi recovery kết thúc hoặc đã được promote.
- `pg_is_in_recovery() = true`: instance vẫn ở recovery/standby.
- `pg_is_wal_replay_paused() = true`: replay đã được pause. Kiểm tra recovery target và log trước khi resume.
- `last_received_lsn` và `last_replayed_lsn` khác nhau: standby đã nhận WAL nhưng còn dữ liệu chưa replay.
- Cả hai LSN không thay đổi: có thể standby đang chờ nguồn WAL, không nhất thiết bị lỗi.

`pg_last_xact_replay_timestamp()` chỉ phản ánh thời điểm transaction cuối cùng được replay. Nếu primary không có transaction mới, giá trị này có thể cũ dù standby đang đồng bộ. So sánh LSN, trạng thái receiver và log thay vì dựa vào timestamp đơn lẻ.

Trên standby đang dùng streaming replication, xem trạng thái WAL receiver:

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    latest_end_lsn,
    latest_end_time,
    slot_name,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
~~~

Nếu view không có hàng, receiver có thể chưa khởi tạo, đã mất kết nối, không được cấu hình hoặc instance hiện đang chỉ đọc archive. Hãy đối chiếu `primary_conninfo`, `restore_command` và log của PostgreSQL.

Trên primary, xem các standby đang kết nối:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_stat_replication;
~~~

Một standby có thể không xuất hiện trong view nếu nó chưa kết nối. View này không cho biết mọi bản sao lưu archive có đầy đủ hay không.

## 3. Cấu hình archive và restore

### archive_mode và archive_command

Trên primary, WAL archiving thường được bật bằng cấu hình tương tự:

~~~conf
archive_mode = on
archive_command = '/usr/local/bin/archive-wal "%p" "%f"'
archive_timeout = 60s
~~~

Đây là ví dụ minh họa. `archive_mode` cần được bật theo cách phù hợp với phiên bản và thường yêu cầu restart PostgreSQL; thay đổi `archive_command` có thể được áp dụng qua reload cấu hình. `archive_timeout` có thể buộc chuyển sang segment mới sau khoảng thời gian cấu hình khi có hoạt động WAL, giúp segment được archive sớm hơn. Nó không tạo WAL mới khi database hoàn toàn không có hoạt động.

PostgreSQL thay `%p` bằng đường dẫn file WAL nguồn và `%f` bằng tên file WAL. Script archive cần:

1. Chạy dưới tài khoản hệ điều hành của PostgreSQL.
2. Đọc được file nguồn và ghi được vào kho archive.
3. Chỉ trả exit code `0` khi file đã được lưu an toàn.
4. Có thể chạy lại mà không tạo bản archive sai hoặc ghi đè file khác nội dung.
5. Ghi log đủ để truy ra lỗi quyền, dung lượng, mạng hoặc dịch vụ lưu trữ.

Nếu archive đích đã có file cùng tên, script nên xác minh nội dung giống hệt rồi mới coi lần chạy là thành công. Nếu nội dung khác, cần báo lỗi và điều tra; không ghi đè mù. Với object storage, chỉ trả thành công sau khi thao tác upload hoàn tất và hệ thống lưu trữ xác nhận kết quả theo mức đảm bảo đã chọn.

PostgreSQL sẽ thử archive lại những segment mà lệnh trước đó trả về lỗi. Vì vậy, archive command phải có tính lặp an toàn. Một lệnh trả `0` dù file chưa được lưu sẽ làm PostgreSQL đánh dấu segment đã archive, tạo ra khoảng trống không thể khôi phục về sau.

`archive_mode = always` có thể dùng khi cần archive cả WAL được nhận hoặc replay trong recovery/standby, nếu operator và kiến trúc triển khai hỗ trợ. Cần xem xét timeline, tên file và khả năng xung đột khi nhiều instance ghi vào cùng kho archive. Không bật chế độ này chỉ để xử lý một lỗi archive chưa rõ nguyên nhân.

### restore_command

Khi phục hồi từ archive, PostgreSQL cần lấy từng WAL segment theo tên file. Cấu hình `restore_command` có dạng:

~~~conf
restore_command = '/usr/local/bin/restore-wal "%f" "%p"'
~~~

PostgreSQL thay `%f` bằng tên file cần lấy và `%p` bằng đường dẫn đích mà lệnh phải ghi file vào. Script cần trả `0` khi đã tải và ghi đầy đủ file vào đúng đường dẫn; trả khác `0` khi file không tồn tại hoặc thao tác thất bại.

Ví dụ đơn giản khi archive lưu file nén gzip:

~~~conf
restore_command = 'gzip -dc /srv/pg-archive/%f.gz > "%p"'
~~~

Ví dụ này chỉ phù hợp nếu tên file trong archive thực sự là tên WAL cộng `.gz`, PostgreSQL có thể đọc kho lưu trữ đó và lệnh trả mã lỗi đúng khi file thiếu hoặc bị hỏng. Với object storage, dùng script/CLI có xác thực và kiểm tra mã thoát; tránh đưa credential vào câu lệnh hoặc log.

Không viết `restore_command` luôn trả thành công khi file không tồn tại. Nếu script tạo file rỗng hoặc trả `0` dù tải thất bại, PostgreSQL có thể cố đọc một file không hợp lệ và recovery sẽ lỗi theo cách khó chẩn đoán hơn.

Trong chế độ standby, nếu `restore_command` không tìm thấy WAL kế tiếp, PostgreSQL có thể thử streaming replication khi `primary_conninfo` được cấu hình. Nếu streaming không có dữ liệu mới, standby có thể quay lại chờ hoặc kiểm tra archive theo cơ chế recovery của nó. Vì vậy, log báo archive chưa có segment tiếp theo đôi khi là bình thường; cần xem cả trạng thái receiver và tiến trình replay.

## 4. Đọc trạng thái WAL archiver

View `pg_stat_archiver` là điểm bắt đầu để phát hiện archive thất bại:

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

Các trường có ý nghĩa:

- `archived_count`: số segment đã archive thành công kể từ lần reset thống kê.
- `last_archived_wal` và `last_archived_time`: segment và thời điểm archive thành công gần nhất.
- `failed_count`: số lần archive thất bại kể từ lần reset thống kê.
- `last_failed_wal` và `last_failed_time`: segment và thời điểm thất bại gần nhất.
- `stats_reset`: thời điểm bộ đếm được reset.

Đừng chỉ nhìn `failed_count` tuyệt đối. Hãy lấy mẫu theo thời gian để biết số lỗi có tiếp tục tăng không và `last_archived_time` có tiến lên không. Một lỗi cũ đã được khắc phục không giống tình trạng archive đang tiếp tục thất bại.

Trên máy chủ PostgreSQL, có thể quan sát hàng đợi archive trong thư mục nội bộ `pg_wal/archive_status`:

- File hậu tố `.ready` biểu thị segment đang chờ archive.
- File hậu tố `.done` biểu thị segment đã được archive.

Số lượng `.ready` tăng liên tục có thể cho thấy archiver không theo kịp. Không sửa, đổi tên hoặc xóa các file trạng thái này bằng tay. Đây là dữ liệu nội bộ do PostgreSQL quản lý; can thiệp trực tiếp có thể khiến trạng thái archive không còn phản ánh đúng dữ liệu đã lưu.

Nếu `pg_stat_archiver` không tiến triển, kiểm tra log PostgreSQL và lỗi từ archive script. Những nguyên nhân phổ biến:

- Archive target hết dung lượng, quota hoặc số lượng object.
- Mất mạng, DNS lỗi, TLS hết hạn hoặc object storage không truy cập được.
- Tài khoản PostgreSQL thiếu quyền đọc WAL hoặc ghi archive.
- Sai đường dẫn, sai tên bucket/prefix hoặc sai cấu hình mount.
- Script dùng sai placeholder, quoting hoặc xử lý tên file có ký tự đặc biệt.
- Lệnh archive trả mã lỗi dù file đã được ghi, khiến PostgreSQL thử lại.
- File cùng tên đã tồn tại nhưng nội dung khác hoặc script không xử lý trường hợp retry.
- Tốc độ upload thấp hơn tốc độ sinh WAL, khiến hàng đợi ngày càng dài.

### Vì sao archive lỗi có thể làm đầy pg_wal?

PostgreSQL cần giữ lại WAL chưa archive để có thể thử lại. Nếu archive bị lỗi kéo dài, các segment chưa archive tích tụ trong `pg_wal`. Replication slot hoặc standby bị tụt lại cũng có thể giữ WAL cần thiết. Dung lượng WAL vì vậy có thể tăng đến mức làm filesystem đầy, ảnh hưởng hoạt động database.

`max_wal_size` là ngưỡng quản lý/checkpoint mang tính mềm, không phải giới hạn cứng bảo đảm `pg_wal` sẽ không vượt quá dung lượng đó. Không xóa các segment trong `pg_wal` để giải phóng chỗ. Trước tiên phải khôi phục archive hoặc xử lý nguyên nhân giữ WAL, đồng thời bảo đảm có đủ dung lượng để PostgreSQL hoạt động và archive queue giảm xuống.

## 5. Xử lý lỗi archive theo thứ tự

Khi phát hiện `failed_count` tăng hoặc `.ready` tồn đọng, xử lý theo trình tự sau.

### Bước 1: xác định lỗi gần nhất

Đọc log PostgreSQL quanh thời điểm `last_failed_time` và tìm tên segment trong `last_failed_wal`. Đọc log của archive script, nếu script có log riêng. Ghi nhận chính xác lỗi hệ điều hành hoặc lỗi dịch vụ lưu trữ, không chỉ ghi “archive failed”.

### Bước 2: xác minh quyền và đích lưu trữ

Kiểm tra dưới đúng tài khoản hệ điều hành chạy PostgreSQL:

- Thư mục archive có tồn tại và được mount đúng không?
- Tài khoản có quyền đọc WAL nguồn và ghi vào đích không?
- Filesystem hoặc bucket còn dung lượng/quota không?
- DNS, route, proxy, TLS và credential của dịch vụ ngoài có hoạt động không?
- Có giới hạn kích thước object, request rate hoặc thời gian timeout không?

Kiểm tra thủ công bằng một file thử nghiệm riêng, không lấy một WAL segment đang được PostgreSQL quản lý để thử upload rồi di chuyển hoặc xóa.

### Bước 3: kiểm tra tính lặp an toàn

Nếu file đích đã tồn tại, xác minh checksum hoặc so sánh byte với file nguồn. Nếu trùng nội dung, archive script có thể coi lần retry là thành công. Nếu khác nội dung, dừng ghi và điều tra timeline, đường dẫn, nguồn backup hoặc việc dùng chung archive sai cách.

Không sửa file WAL cũ bằng cách đổi tên hay nén lại ngay trong archive mà không cập nhật restore command và metadata. Archive phải giữ được ánh xạ rõ ràng giữa tên segment PostgreSQL yêu cầu và nội dung file có thể phục hồi.

### Bước 4: khắc phục và theo dõi hàng đợi

Sửa lỗi đích lưu trữ, quyền hoặc script; sau đó theo dõi `pg_stat_archiver` để xác nhận `last_archived_wal` tiến lên và số `.ready` giảm. So sánh các tên WAL đã archive với thứ tự segment cần thiết. Chỉ coi sự cố đã được xử lý khi archive tiếp tục thành công và có thể đọc lại các file đã lưu.

Nếu filesystem `pg_wal` gần đầy, ưu tiên phục hồi khả năng archive và mở rộng dung lượng an toàn theo quy trình vận hành. Không dừng PostgreSQL hoặc xóa WAL một cách tùy tiện vì điều đó có thể khiến standby hoặc backup không thể tiếp tục.

## 6. Nhận diện và xử lý thiếu WAL

Thiếu WAL thường biểu hiện qua log cho biết một segment được yêu cầu nhưng không thể tìm thấy, không thể tải, hoặc dữ liệu WAL không hợp lệ. Nguyên nhân không chỉ là file bị xóa. Có thể PostgreSQL đang tìm sai timeline, archive bị đổi prefix, file nén chưa được giải nén đúng, base backup không khớp với archive, hoặc restore command đang trỏ đến kho khác.

### Những điều kiện để PITR thành công

Một quy trình PITR cần:

1. Base backup hoàn chỉnh và hợp lệ.
2. WAL cần thiết để đưa backup đến trạng thái nhất quán.
3. Mọi WAL segment liên tục từ điểm bắt đầu backup đến recovery target.
4. Timeline history cần thiết nếu phục hồi qua một lần promote hoặc chuyển timeline.
5. `restore_command` tải đúng tên file, đúng nội dung và trả mã thoát phù hợp.
6. Recovery target nằm trong khoảng thời gian hoặc LSN mà dữ liệu backup và WAL thực sự bao phủ.

Một archive có segment đầu và cuối nhưng thiếu một segment ở giữa vẫn không đủ. PostgreSQL không thể suy ra các thay đổi đã mất từ segment sau.

### Phân biệt file thiếu và file chưa được tạo

Nếu standby đang theo dõi primary, segment tiếp theo có thể chưa tồn tại vì primary chưa ghi đủ WAL để hoàn thành segment. Khi đó standby chờ là bình thường. `archive_timeout` có thể giúp archive segment sớm hơn khi có hoạt động, nhưng không thể tạo dữ liệu WAL không tồn tại.

Nếu PITR yêu cầu đến một thời điểm cụ thể, hãy xác minh thời điểm đó có nằm trong phạm vi WAL đã archive. Nếu target muộn hơn WAL cuối cùng có sẵn, recovery không thể đạt target. Nếu target sớm hơn, có thể đã chọn sai timezone, timestamp hoặc timeline.

### Kiểm tra tên và tính liên tục của WAL

Tên WAL mã hóa timeline ID, log ID và segment ID. Hãy so sánh tên file PostgreSQL yêu cầu với danh sách trong archive, bao gồm cả file history có đuôi `.history`. Không giả định hai file kế tiếp có thể so sánh chỉ bằng chuỗi thời gian hoặc chỉ số cuối cùng khi timeline đã thay đổi.

Khi cần, kiểm tra metadata và checksum của file lưu trữ bằng công cụ của kho archive. Với file nén, xác minh giải nén thành công và kích thước hợp lý. `pg_waldump` có thể giúp đọc/kiểm tra nội dung WAL ở mức thấp, nhưng phải dùng phiên bản công cụ tương thích với phiên bản PostgreSQL và file WAL; đây không phải công cụ để tự tạo hoặc vá segment bị thiếu.

Nếu tìm thấy một bản sao cùng tên từ backup khác, không thay thế ngay. Phải xác minh nguồn cluster, timeline, checksum và tính tương thích với base backup đang phục hồi. Hai cluster khác nhau có thể có tên WAL trùng nhau nhưng nội dung khác.

## 7. Timeline và file history

PostgreSQL tạo timeline mới khi một nhánh recovery được kết thúc, chẳng hạn standby được promote. Timeline giúp phân biệt các nhánh lịch sử WAL phát sinh từ cùng một điểm phân nhánh.

Khi PITR hoặc standby cần theo một timeline mới, ngoài WAL segment còn có thể cần file timeline history. File `.history` mô tả quan hệ giữa timeline mới và timeline cha, cùng vị trí chuyển nhánh. Nếu thiếu file history hoặc cấu hình chọn timeline sai, PostgreSQL có thể không tìm đúng nhánh WAL dù archive vẫn có nhiều segment.

Tham số `recovery_target_timeline` điều khiển timeline đích. Các giá trị thường dùng gồm `current`, `latest` hoặc một số timeline cụ thể; hành vi và mặc định cần đối chiếu tài liệu của phiên bản PostgreSQL đang chạy. Với standby cần theo nhánh mới nhất, cấu hình `latest` thường là lựa chọn phù hợp khi topology yêu cầu điều đó.

Một lỗi thường gặp là chỉ sao chép WAL từ primary hiện tại mà quên lịch sử của nhánh cũ, hoặc gộp archive của nhiều cluster vào cùng một prefix mà không phân vùng theo cluster/timeline. Nên tổ chức archive theo định danh cluster và chính sách retention rõ ràng. Tên file WAL không phải định danh toàn cục cho mọi cluster.

## 8. Cấu hình recovery trên PostgreSQL 12 trở lên

Từ PostgreSQL 12, các tham số recovery được đặt trong cấu hình PostgreSQL (ví dụ `postgresql.conf` hoặc file được include), còn chế độ khởi động recovery được biểu thị bằng file signal trong data directory:

- `recovery.signal`: yêu cầu archive recovery/PITR.
- `standby.signal`: yêu cầu chạy ở chế độ standby.

Các phiên bản PostgreSQL cũ hơn dùng `recovery.conf`; không áp dụng hướng dẫn file signal của phiên bản mới cho server cũ.

Ví dụ cấu hình phục hồi từ archive đến một thời điểm:

~~~conf
restore_command = '/usr/local/bin/restore-wal "%f" "%p"'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

Đây chỉ là cấu hình minh họa. Thời gian đích phải dùng múi giờ rõ ràng và phải nằm trong dữ liệu WAL có sẵn. Chọn `recovery_target_action` theo mục đích:

- `pause`: dừng replay tại target để kiểm tra dữ liệu.
- `promote`: tự promote khi đạt target.
- `shutdown`: dừng server khi đạt target.

Nếu đã tạo `recovery.signal` nhưng recovery target không thể đạt vì thiếu WAL, thay đổi `recovery_target_action` không khắc phục được khoảng trống dữ liệu. Phải khôi phục đúng archive hoặc chọn một target có dữ liệu hợp lệ nếu chủ sở hữu dữ liệu chấp thuận.

Trước khi khởi động, xác nhận `PGDATA` đúng, base backup đúng cluster, quyền sở hữu file đúng và signal file phù hợp. Không để đồng thời các cấu hình recovery cũ và mới gây nhầm lẫn.

## 9. Chẩn đoán recovery bị kẹt

Điều tra từ log đầu tiên xuất hiện lỗi, không chỉ dòng log cuối cùng. Log có thể cho biết PostgreSQL đang khôi phục từ archive, chờ segment tiếp theo, thử streaming, pause tại target hay thất bại khi đọc WAL.

### Bước 1: xác định chế độ và trạng thái

~~~sql
SELECT
    pg_is_in_recovery(),
    pg_is_wal_replay_paused(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
~~~

Nếu instance không ở recovery, vấn đề có thể đã xảy ra sau khi promote hoặc trong hoạt động primary. Nếu replay paused, xác minh có chủ đích đạt target hay không. Nếu standby đang recovery và LSN không tiến triển, chuyển sang kiểm tra nguồn WAL.

### Bước 2: đọc log và phân loại nguyên nhân

| Dấu hiệu | Hướng điều tra |
|---|---|
| Restore command trả lỗi hoặc không tìm thấy file | Đường dẫn, quyền, credential, tên file, kho archive và mã thoát |
| Segment được yêu cầu không tồn tại | Tính liên tục WAL, timeline, retention và đúng base backup |
| Lỗi giải nén hoặc WAL không hợp lệ | File hỏng, truyền thiếu byte, sai thuật toán nén hoặc nhầm cluster |
| Đang chờ WAL tiếp theo | Standby có thể đang ở cuối archive; kiểm tra streaming và primary |
| Replay đã pause tại recovery target | Xác minh target và `recovery_target_action`; có thể là trạng thái mong muốn |
| PVC pending hoặc volume attach thất bại | StorageClass, CSI, quota, zone và event Kubernetes |
| Disk đầy hoặc I/O error | Dung lượng `PGDATA`/`pg_wal`, storage backend và WAL backlog |
| WAL receiver disconnected | `primary_conninfo`, DNS, mạng, TLS, credential và replication slot |

### Bước 3: xác minh restore command độc lập

Chạy thử script bằng đúng tài khoản hệ điều hành PostgreSQL với một WAL file đã biết chắc có trong archive. Xác minh:

- Script nhận đúng tên file và đích đầu ra.
- Kết quả được ghi đầy đủ vào đích mà PostgreSQL truyền qua `%p`.
- Exit code là `0` khi tải thành công.
- Exit code khác `0` khi file không tồn tại hoặc dữ liệu bị lỗi.
- Script không ghi credential hoặc dữ liệu nhạy cảm vào log.
- File tải về có checksum/size phù hợp với bản archive đã lưu.

Không chạy thử bằng cách thay đổi file đang được PostgreSQL phục hồi. Dùng bản sao hoặc môi trường phục hồi riêng.

### Bước 4: kiểm tra nguồn WAL thay thế

Nếu standby được cấu hình cả archive và streaming, kiểm tra `pg_stat_wal_receiver`, `primary_conninfo`, kết nối mạng và trạng thái primary. Trên primary, kiểm tra `pg_stat_replication` và replication slot nếu có. Một slot có thể giữ WAL để standby bắt kịp; slot bị mất hoặc WAL cần thiết đã bị loại bỏ có thể buộc standby phải được tạo lại từ backup mới.

Nếu không còn bản WAL cần thiết ở archive, primary, replica khác hoặc bản sao lưu độc lập, không có lệnh SQL nào có thể tái tạo chính xác các bản ghi WAL đã mất. Cần đánh giá lại backup, target và khả năng dựng lại standby.

## 10. Khôi phục khi archive bị lỗi hoặc thiếu segment

Thứ tự xử lý an toàn phụ thuộc vai trò của instance.

### Trường hợp A: primary vẫn hoạt động, archive command đang lỗi

1. Giữ primary hoạt động nếu nó vẫn ổn định và còn đủ dung lượng; tránh restart không cần thiết.
2. Xác định `last_failed_wal` và lỗi thực tế.
3. Khôi phục quyền, dung lượng, mạng hoặc credential của archive target.
4. Sửa archive script để retry an toàn và kiểm tra nội dung file đã tồn tại.
5. Theo dõi `pg_stat_archiver` và `.ready` cho đến khi queue giảm.
6. Kiểm tra segment mới nhất và một số segment cũ có thể đọc lại từ archive.
7. Xác minh backup policy và retention vẫn bao phủ các base backup đang được giữ.

Nếu archive đã bỏ sót một file do script trả thành công sai, PostgreSQL có thể đã đánh dấu file đó hoàn tất. Cần xác định chính xác segment nào bị thiếu, khôi phục từ bản sao đáng tin cậy nếu có và kiểm tra chuỗi WAL trước khi coi archive hợp lệ.

### Trường hợp B: standby không nhận được WAL

1. Xác định standby đang chờ archive hay streaming.
2. Kiểm tra receiver và log để biết lỗi kết nối hoặc segment nào đang được yêu cầu.
3. Kiểm tra primary có còn WAL cần thiết không và replication slot có giữ WAL không.
4. Kiểm tra archive có segment đó cùng timeline history phù hợp không.
5. Khôi phục kết nối hoặc đưa file hợp lệ vào đúng archive theo quy trình được kiểm soát.
6. Xác nhận receive LSN và replay LSN tiếp tục tăng, replication lag giảm.

Không xóa replication slot hoặc WAL chỉ để giảm dung lượng trước khi xác định standby có còn cần chúng hay không. Xóa slot có thể làm WAL bị loại bỏ và khiến standby không thể tiếp tục theo kịp.

### Trường hợp C: PITR dừng vì thiếu WAL

1. Ghi lại base backup được chọn, thời điểm backup và recovery target.
2. Xác định segment đầu tiên không thể lấy và timeline mà PostgreSQL đang theo.
3. Tìm segment đó trong archive chính, bản sao archive, object versioning hoặc bản lưu ngoài vùng.
4. Xác minh file đúng cluster/timeline, đủ kích thước và đọc được.
5. Đưa file về kho mà `restore_command` sử dụng hoặc điều chỉnh restore script để đọc đúng nguồn.
6. Khởi chạy lại recovery theo quy trình đã kiểm tra; xác nhận PostgreSQL vượt qua segment bị thiếu và đạt target.
7. Kiểm tra dữ liệu nghiệp vụ trước khi promote và mở traffic.

Nếu không thể tìm được segment bị thiếu, chọn một base backup khác có chuỗi WAL đầy đủ hoặc một recovery target sớm hơn nằm trong phạm vi có thể khôi phục. Đây là quyết định về mức mất dữ liệu và phải được data owner/DBA chấp thuận. Không được tự ý bỏ qua segment để “cho database chạy lên”.

## 11. Pause, resume và promote đúng thời điểm

Nếu `pg_is_wal_replay_paused()` trả `true`, xem log và recovery target. Nếu PostgreSQL pause vì đã đến target và người vận hành muốn tiếp tục replay vượt qua target, có thể dùng:

~~~sql
SELECT pg_wal_replay_resume();
~~~

Lệnh này tiếp tục áp dụng WAL. Nó có thể khiến database đi qua thời điểm PITR đã chọn, vì vậy chỉ dùng khi mục tiêu thực sự là tiếp tục recovery.

Nếu đã đạt target, đã kiểm tra dữ liệu và muốn đưa instance thành primary độc lập, cần promote theo quy trình PostgreSQL/operator hỗ trợ. Có thể dùng `pg_promote()` trên các phiên bản hỗ trợ hoặc lệnh promote được operator cung cấp. Trong môi trường do operator quản lý, thực hiện promote qua custom resource/API của operator nếu đó là cơ chế được tài liệu chỉ định; thao tác trực tiếp có thể khiến trạng thái operator và database lệch nhau.

Không promote một standby chỉ vì nó đang chờ WAL. Trước tiên phải quyết định có chấp nhận mất các transaction chưa nhận được từ primary hay không, bảo đảm primary cũ không tiếp tục nhận ghi và kiểm tra fencing. Promote sai thời điểm có thể tạo hai nhánh dữ liệu ghi độc lập.

## 12. Retention và dọn dẹp WAL an toàn

Archive retention phải dựa trên base backup cũ nhất còn được giữ và mọi nhu cầu PITR/standby. Muốn phục hồi từ một base backup, cần giữ WAL liên tục bắt đầu từ điểm WAL mà backup yêu cầu đến hết khoảng thời gian muốn phục hồi. Xóa một segment ở giữa làm hỏng khả năng phục hồi của backup đó.

Trước khi dọn archive, xác định:

- Các base backup còn hiệu lực và thời điểm/LSN bắt đầu WAL cần giữ.
- Thời hạn PITR được cam kết.
- Standby hoặc replica nào còn có thể cần WAL.
- Các timeline history file có liên quan.
- Bản sao archive đã được xác minh ở vùng lưu trữ độc lập chưa.
- Chính sách legal hold, retention và xóa dữ liệu của tổ chức.

`pg_archivecleanup` có thể hữu ích trong một số thiết kế archive dành riêng cho standby, nhưng nó xóa các WAL cũ hơn một mốc được đưa vào. Không chạy nó trên kho archive dùng chung cho nhiều base backup hoặc nhiều cluster nếu chưa tính toán chính xác mốc giữ. Không xóa thủ công file trong `pg_wal` hoặc `pg_wal/archive_status`.

WAL archive cần được bảo vệ khỏi xóa nhầm, overwrite và ghi đè từ cluster khác. Nên phân vùng theo cluster, có quyền ghi hạn chế, versioning hoặc immutable retention khi yêu cầu bảo vệ dữ liệu đòi hỏi.

## 13. Ví dụ runbook: archive lỗi khiến standby tụt lại

Giả sử primary vẫn nhận ghi nhưng standby ngày càng trễ. DBA nhận thấy `failed_count` trong `pg_stat_archiver` tăng và filesystem chứa `pg_wal` đang tăng dung lượng.

**Trên primary**, kiểm tra:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;

SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_stat_replication;
~~~

Kết quả cho thấy archive thất bại gần đây và standby có replay LSN thấp hơn sent LSN. Tiếp theo, người vận hành đọc log archive command và phát hiện credential object storage hết hạn.

Các bước xử lý:

1. Xác nhận primary còn đủ dung lượng để tiếp tục hoạt động trong thời gian sửa lỗi.
2. Cấp lại credential theo hệ thống quản lý secret, không ghi mật khẩu vào command history.
3. Kiểm tra script upload bằng một file thử nghiệm độc lập.
4. Xác minh retry cho segment đang `.ready` không ghi đè nội dung khác.
5. Theo dõi `pg_stat_archiver` cho đến khi `last_archived_time` mới và queue giảm.
6. Xác minh standby receiver kết nối lại, receive/replay LSN tăng.
7. Kiểm tra backup mới và thực hiện một lần restore thử theo lịch vận hành.

Nếu một segment đã bị đánh dấu archive thành công nhưng thực tế không có trong object storage, phải xác định segment cụ thể và tìm bản sao hợp lệ. Không thể coi sự cố đã kết thúc chỉ vì các segment mới tiếp tục archive.

## 14. Ví dụ runbook: PITR dừng ở một segment không tìm thấy

Giả sử một bản restore dùng base backup gần đầu tháng và target là một thời điểm giữa tháng. Log cho biết `restore_command` không lấy được segment được yêu cầu.

Trình tự xử lý:

1. Xác định file WAL đầy đủ mà PostgreSQL đang yêu cầu, kể cả timeline ID.
2. Kiểm tra target time và múi giờ có đúng như yêu cầu khôi phục không.
3. Kiểm tra file đó trong archive chính, replica archive, object version history và bản sao ngoài vùng.
4. Nếu tìm thấy, so sánh checksum với nguồn tin cậy, xác nhận đúng cluster/timeline rồi khôi phục.
5. Nếu file có dạng nén, kiểm tra giải nén và đảm bảo restore command ghi đúng file đích.
6. Nếu file không tồn tại ở mọi nguồn, tìm base backup khác hoặc xác định target sớm hơn mà chuỗi WAL còn đầy đủ.
7. Sau khi recovery thành công, kiểm tra dữ liệu nghiệp vụ, role database, extension và quyền trước khi cho ứng dụng kết nối.

Không thay file thiếu bằng một segment có cùng kích thước nhưng không rõ nguồn. WAL là chuỗi bản ghi có quan hệ logic; dữ liệu sai có thể làm recovery thất bại hoặc tạo trạng thái không đáng tin cậy.

## 15. Những lỗi xử lý thường gặp

**Xóa WAL trong `pg_wal` để giải phóng dung lượng.** Điều này có thể phá vỡ recovery, replication hoặc archive retry. Sửa nguyên nhân giữ WAL và mở rộng storage theo quy trình.

**Coi mọi lần restore command trả “not found” là lỗi nghiêm trọng.** Standby có thể hỏi segment chưa được tạo hoặc đang chờ nguồn streaming. Đọc log cùng trạng thái receiver và LSN.

**Coi `kubectl get pods` báo Running là PostgreSQL đã sẵn sàng.** Pod Running không khẳng định database đã replay đủ WAL, đã trở thành primary hoặc có thể nhận traffic.

**Bỏ qua timeline history.** File WAL có thể tồn tại nhưng thuộc nhánh lịch sử khác. Xác minh timeline và file `.history`.

**Trả exit code 0 khi upload chưa hoàn tất.** PostgreSQL sẽ tin rằng segment đã archive và không thử lại theo cách mong muốn. Chỉ báo thành công sau khi dữ liệu được lưu an toàn.

**Chạy restore bằng tài khoản khác với tài khoản PostgreSQL.** Lệnh thử thành công dưới tài khoản quản trị không chứng minh process PostgreSQL có quyền đọc archive hoặc ghi file đích.

**Promote standby để thoát trạng thái chờ.** Promote có thể tạo nhánh dữ liệu mới và chấp nhận mất WAL chưa nhận. Phải xác minh primary cũ đã bị fencing và có phê duyệt về RPO.

**Dọn archive theo tuổi file đơn thuần.** Một file cũ có thể vẫn cần cho base backup đang được giữ. Retention phải dựa trên backup, WAL range, timeline và nhu cầu PITR.

## 16. Checklist vận hành và phục hồi

- [ ] Xác định instance là primary, standby, PITR recovery hay crash recovery.
- [ ] Kiểm tra `pg_is_in_recovery()` và trạng thái replay pause.
- [ ] So sánh receive LSN, replay LSN và trạng thái WAL receiver.
- [ ] Đọc log đầu tiên báo lỗi và ghi lại segment/timeline được yêu cầu.
- [ ] Kiểm tra `pg_stat_archiver`, thời điểm archive gần nhất và lỗi gần nhất.
- [ ] Kiểm tra số file `.ready`, dung lượng `pg_wal` và filesystem archive.
- [ ] Xác minh archive command/restore command bằng đúng tài khoản hệ điều hành PostgreSQL.
- [ ] Kiểm tra tên WAL, timeline history, checksum và khả năng giải nén.
- [ ] Xác minh base backup có thể dùng và WAL liên tục đến target.
- [ ] Kiểm tra replication slot và nguồn streaming nếu standby cần WAL.
- [ ] Không xóa WAL, archive status, PVC hoặc CR khi chưa xác định tác động.
- [ ] Chỉ resume hoặc promote sau khi hiểu recovery target và rủi ro mất dữ liệu.
- [ ] Sau phục hồi, xác minh dữ liệu nghiệp vụ, replication, backup và cảnh báo.

Một hệ thống PostgreSQL có thể phục hồi tin cậy khi base backup, WAL archive, timeline history và restore command được quản lý như một chuỗi thống nhất. Khi recovery dừng, hãy xác định chính xác segment và trạng thái mà PostgreSQL đang chờ, khôi phục nguồn WAL hợp lệ hoặc điều chỉnh target theo quyết định dữ liệu có thẩm quyền. Không có thao tác promote, restart hay xóa file nào có thể thay thế một chuỗi WAL bị thiếu.

