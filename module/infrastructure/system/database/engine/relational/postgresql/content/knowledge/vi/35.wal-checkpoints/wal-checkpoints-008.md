# Archive WAL và kiểm tra tính liên tục trong PostgreSQL

Write-Ahead Log (WAL) là nền tảng để PostgreSQL phục hồi sau sự cố, hỗ trợ streaming replication và khôi phục cơ sở dữ liệu về một thời điểm trong quá khứ. Tuy nhiên, WAL đang nằm trong thư mục pg_wal của một server không tự động trở thành bản lưu trữ lâu dài. Các segment cũ có thể được tái sử dụng sau khi PostgreSQL không còn cần chúng cho crash recovery, replication hoặc archiving.

**WAL archiving** là quá trình sao chép các WAL segment đã hoàn tất ra một kho lưu trữ riêng. Khi kết hợp một base backup hợp lệ với chuỗi WAL liên tục bắt đầu từ điểm cần thiết, PostgreSQL có thể replay các thay đổi và khôi phục tới một thời điểm hoặc vị trí WAL đã chọn. Đây là nền tảng của **Point-in-Time Recovery (PITR)**.

~~~text
PostgreSQL primary
       |
       v
   pg_wal/
       |
       | WAL segment hoàn tất
       v
   archiver process
       |
       | archive_command / archive_library
       v
  Kho archive WAL
       |
       +----------------------+
                              |
Base backup -----------------+
                              |
                              v
                    PostgreSQL restore
                    + restore_command
                              |
                              v
                    Replay WAL liên tục
                              |
                              v
                    Recovery target (PITR)
~~~

Một hệ thống archive đáng tin cậy cần nhiều hơn một câu lệnh copy file. Cần bảo đảm lệnh archive chỉ báo thành công khi segment đã được lưu đầy đủ, không ghi đè nhầm file đã có, giữ đúng timeline history, giám sát lỗi và backlog, bảo vệ kho archive, đồng thời thường xuyên thử restore.

Bài này thuộc chương **WAL và checkpoint** của module *Database Engine Relational PostgreSQL*, tập trung vào cấu hình archive, tên WAL segment, timeline, cách kiểm tra tính liên tục, quy trình phục hồi và vận hành backup/PITR.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích WAL archiving và vai trò của nó trong PITR.
2. Phân biệt WAL đang hoạt động trong pg_wal với các segment đã được archive.
3. Mô tả vai trò của archive_mode, archive_command, archive_library và archive_timeout.
4. Hiểu khi nào archiver xử lý một segment và vì sao segment chưa đầy có thể chưa được archive ngay.
5. Viết archive command idempotent, an toàn khi PostgreSQL gọi lại cùng một segment.
6. Giải thích placeholders %p, %f và cách xử lý shell quoting.
7. Phân biệt quyền truy cập filesystem của tiến trình PostgreSQL với quyền SQL của database role.
8. Đọc tên WAL segment và hiểu timeline ID, log ID, segment ID.
9. Hiểu timeline history file và vì sao phải giữ chúng trong archive.
10. Theo dõi archiver bằng pg_stat_archiver và trạng thái .ready/.done.
11. Phân biệt WAL archiving với streaming replication, replication slots và wal_keep_size.
12. Kiểm tra segment, WAL record và backup bằng pg_waldump và pg_verifybackup.
13. Xác định khoảng WAL cần thiết từ backup start tới recovery target.
14. Nhận diện khoảng trống, file thiếu, file hỏng, timeline sai và lỗi quyền.
15. Cấu hình restore_command cho archive recovery.
16. Thiết lập PITR bằng recovery signal và recovery target.
17. Thiết kế retention an toàn theo backup chain, timeline và yêu cầu RPO/RTO.
18. Xây dựng quy trình kiểm tra archive định kỳ và restore drill có thể lặp lại.

## 2. WAL archiving giải quyết vấn đề gì?

PostgreSQL ghi thay đổi vào WAL trước khi các data pages tương ứng được ghi hoàn toàn xuống data files. Khi server crash, PostgreSQL đọc WAL còn cần thiết để redo các thao tác và đưa database về trạng thái nhất quán.

### 2.1. Crash recovery

WAL trong pg_wal giúp khôi phục sau crash của cùng một cluster. Cơ chế này không yêu cầu archive WAL ra một kho bên ngoài.

### 2.2. Streaming replication

Primary gửi WAL qua replication protocol tới standby. Standby nhận và replay WAL để theo kịp primary. Đây là một đường truyền liên tục, thường có kết nối tới primary hoặc replication source.

### 2.3. WAL archiving

Archiver sao chép WAL segment hoàn tất ra archive storage. Kho này có thể ở filesystem riêng, NAS, volume khác, object storage qua công cụ phù hợp hoặc hệ thống backup.

### 2.4. Point-in-Time Recovery

PITR kết hợp:

- Một base backup nhất quán.
- Tất cả WAL cần thiết bắt đầu từ điểm backup yêu cầu.
- Các WAL tiếp theo tới recovery target.
- Timeline history files cần thiết nếu recovery đi qua timeline switch.

Khi restore, PostgreSQL nạp base backup rồi replay WAL theo thứ tự cho tới target.

### 2.5. Archive không phải backup đầy đủ

Chỉ có WAL archive thì không đủ để tạo lại một database từ con số không. Cần một base backup phù hợp và toàn bộ WAL cần thiết từ backup đó.

## 3. Các thành phần trong quy trình archive

~~~text
Backend processes
      |
      | ghi WAL records
      v
WAL buffers -> WAL segment files trong pg_wal
      |
      | segment được đóng / switch
      v
Archiver process
      |
      | archive_command hoặc archive_library
      v
Archive destination
      |
      | giữ nhiều segment + timeline history
      v
Backup / PITR repository
      |
      | restore_command
      v
Recovery process
      |
      | replay liên tục
      v
Recovery target
~~~

### 3.1. WAL writer

Backend tạo WAL records khi thay đổi dữ liệu. WAL writer giúp ghi các WAL buffers xuống WAL files theo lịch/điều kiện.

### 3.2. Checkpointer

Checkpoint ghi dirty buffers và tạo mốc recovery trong WAL. Checkpoint không đồng nghĩa archive một segment ngay lập tức.

### 3.3. Archiver

Archiver xử lý các WAL segment đã hoàn tất, gọi command hoặc library được cấu hình. PostgreSQL đánh dấu trạng thái để biết segment nào đã archive thành công.

### 3.4. Archive destination

Đây là nơi giữ bản sao WAL lâu hơn vòng đời segment trong pg_wal. Cần độc lập về dung lượng, quyền, độ bền và retention.

### 3.5. Restore process

Trong archive recovery, PostgreSQL gọi restore_command để lấy file WAL cần thiết về vị trí đích, sau đó đọc và replay.

## 4. Bật WAL archiving

Các tham số cốt lõi trong postgresql.conf:

~~~conf
wal_level = replica
archive_mode = on
archive_command = '/usr/local/bin/archive-wal "%p" "%f"'
archive_timeout = 300
~~~

Đây là ví dụ cho môi trường Linux có script archive đã được cài đặt và kiểm thử. Thay đường dẫn, quyền và nơi lưu archive theo hạ tầng thực tế.

### 4.1. wal_level

Để hỗ trợ PITR và các tính năng replication thông thường, đặt wal_level ở replica hoặc logical. Mức minimal không giữ đủ WAL information cho mục đích PITR/replication như yêu cầu.

### 4.2. archive_mode

archive_mode bật archiving. Tham số này cần restart server để thay đổi có hiệu lực; không chỉ reload cấu hình.

### 4.3. archive_command

Định nghĩa shell command mà archiver chạy cho mỗi file cần archive. Command phải trả exit status 0 khi file đã được archive thành công và non-zero khi thất bại.

### 4.4. archive_library

Các phiên bản PostgreSQL hỗ trợ archive module có thể dùng archive_library thay cho shell command. Module phải được cài và tương thích với server. Không cấu hình đồng thời hai cơ chế archive theo cách xung đột; kiểm tra tài liệu phiên bản đang vận hành.

### 4.5. archive_timeout

Ép PostgreSQL switch WAL segment sau khoảng thời gian có hoạt động WAL đủ điều kiện, để giảm thời gian chờ segment đầy mới được archive. Giá trị quá nhỏ có thể tạo nhiều segment archive, tăng số file và overhead.

### 4.6. Kiểm tra tham số đang hiệu lực

~~~sql
SHOW wal_level;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_library;
SHOW archive_timeout;
~~~

Nếu server không nhận biết archive_library, có thể đang chạy phiên bản cũ hơn; bỏ dòng SHOW đó và kiểm tra các tham số có sẵn trong phiên bản hiện tại.

### 4.7. Kiểm tra nguồn cấu hình

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'archive_mode',
    'archive_command',
    'archive_library',
    'archive_timeout'
)
ORDER BY name;
~~~

pending_restart giúp nhận biết tham số cần restart nhưng thay đổi chưa có hiệu lực.

## 5. archive_mode: on và always

### 5.1. archive_mode = off

Không archive WAL segment bằng archiver, kể cả khi archive_command đã có giá trị.

### 5.2. archive_mode = on

Archive WAL được tạo trong hoạt động bình thường của primary. Trong standby/recovery, chế độ này không archive lại các segment đang được replay.

### 5.3. archive_mode = always

Cho phép archiver hoạt động cả trong recovery/standby mode và archive WAL được nhận/replay trong những tình huống phù hợp. Có ích khi xây chuỗi archive từ một standby được thiết kế làm archive source.

### 5.4. Không bật always tùy tiện

Nếu primary và standby cùng archive vào một destination, cần bảo đảm file naming/timeline và cơ chế ghi không xung đột. Hai server không được cùng ghi đè file archive của nhau.

### 5.5. archive_mode cần restart

Thay đổi từ off sang on/always hoặc ngược lại cần restart PostgreSQL. Thay đổi archive_command thường có thể áp dụng bằng reload.

## 6. archive_command và placeholders

PostgreSQL thay thế các placeholders trong command:

| Placeholder | Ý nghĩa |
| --- | --- |
| %p | Đường dẫn đầy đủ của file nguồn trong pg_wal |
| %f | Tên file cần archive, không kèm path |
| %% | Ký tự phần trăm literal |

Ví dụ:

~~~conf
archive_command = 'cp "%p" "/srv/pgarchive/%f"'
~~~

### 6.1. %p

%p thường là đường dẫn tới WAL segment hoặc timeline history file cần archive, nhìn từ filesystem của PostgreSQL server.

### 6.2. %f

%f là tên file, ví dụ một WAL segment hoặc file timeline history. Dùng nó làm basename trong archive directory.

### 6.3. Quoting

Command chạy qua shell. Path có dấu cách, dấu nháy hoặc ký tự đặc biệt phải được quote đúng. Đừng nối input người dùng vào command.

### 6.4. Quyền hệ điều hành

Command chạy dưới quyền OS của tiến trình PostgreSQL. Thư mục archive cần tồn tại và cho phép user dịch vụ ghi; archive destination cần được mount và truy cập đúng trên host/container database.

### 6.5. Exit status

Exit 0 nói với PostgreSQL rằng archive đã hoàn tất. Nếu command trả 0 trước khi dữ liệu được ghi bền vững, server có thể đánh dấu segment đã archive dù file đích thực tế thiếu/hỏng.

## 7. Thiết kế archive command idempotent

PostgreSQL có thể gọi lại archive command cho cùng một file khi lần trước thất bại hoặc kết quả chưa được xác nhận. Vì vậy command cần **idempotent**: chạy lại không tạo ra file sai, không ghi đè nội dung khác và chỉ báo thành công khi bản archive hợp lệ.

### 7.1. Ví dụ copy đơn giản

~~~conf
archive_command = 'cp "%p" "/srv/pgarchive/%f"'
~~~

Lệnh này minh họa cú pháp, nhưng trong production cần xử lý file đã tồn tại, copy dở, quyền và tính bền vững.

### 7.2. Quy tắc khi file đích đã tồn tại

- Nếu file đích giống hệt nguồn, trả thành công.
- Nếu file đích khác nguồn, trả lỗi và báo động; không ghi đè âm thầm.
- Nếu file đích chưa tồn tại, copy vào file tạm rồi publish atomically khi có thể.
- Nếu copy thất bại, giữ trạng thái để PostgreSQL retry.

### 7.3. Script mẫu trên Linux

Tạo script quản trị /usr/local/bin/archive-wal:

~~~bash
#!/bin/sh
set -eu

src=$1
name=$2
archive_dir=/srv/pgarchive
dest="$archive_dir/$name"
tmp="$archive_dir/.$name.tmp"

if [ -f "$dest" ]; then
    cmp -s "$src" "$dest"
    exit $?
fi

rm -f "$tmp"
cp "$src" "$tmp"
mv "$tmp" "$dest"
~~~

Sau đó cấu hình:

~~~conf
archive_command = '/usr/local/bin/archive-wal "%p" "%f"'
~~~

Đây là mẫu cơ bản cho một filesystem local được kiểm soát. Production cần xem xét filesystem semantics, quyền, xử lý race giữa nhiều archivers, durability/fsync, quota, monitoring và khả năng phục hồi khi máy mất điện. Với kho object storage, dùng client/tool có cơ chế upload hoàn chỉnh, checksum và publish semantics phù hợp.

### 7.4. Vì sao copy vào file tạm?

Nếu copy trực tiếp vào tên cuối rồi process bị kill giữa chừng, một file đích không đầy đủ có thể xuất hiện. Lần retry có thể thấy file đó và hiểu sai trạng thái. File tạm giúp chỉ công bố tên cuối sau khi copy xong.

### 7.5. Vì sao so sánh khi file đã tồn tại?

PostgreSQL có thể retry cùng segment. File tồn tại giống nguồn có thể được coi là thành công; file khác nguồn là dấu hiệu archive collision/corruption và cần dừng để điều tra.

### 7.6. Không xóa source thủ công

Không xóa file trong pg_wal hoặc các file trạng thái archive để “ép chạy lại”. Hãy sửa lỗi destination/command rồi để archiver retry theo cơ chế PostgreSQL.

## 8. Archive command và bảo mật

### 8.1. Quyền archive directory

Chỉ cấp quyền ghi cần thiết cho tài khoản dịch vụ PostgreSQL hoặc helper identity được thiết kế. Không mở thư mục archive cho mọi user.

### 8.2. Command injection

Tên file WAL do PostgreSQL tạo theo định dạng xác định; tuy nhiên command vẫn là shell. Không đưa chuỗi path/command do người dùng cung cấp trực tiếp vào archive_command.

### 8.3. Credentials

Không nhúng access key, password hoặc token cloud plaintext vào postgresql.conf nếu có lựa chọn an toàn hơn. Dùng identity/credential store và file permission phù hợp.

### 8.4. Mã hóa khi lưu

WAL có thể chứa thông tin nhạy cảm về thay đổi dữ liệu. Bảo vệ archive bằng encryption-at-rest, TLS khi truyền, access control, audit và retention phù hợp.

### 8.5. Tách failure domain

Archive đặt cùng một disk với data directory không bảo vệ trước mất disk/host. Dùng storage độc lập hoặc hệ thống backup có durability và replication riêng.

## 9. archive_timeout và thời điểm archive

WAL segment thường được archive khi segment hoàn tất. Nếu workload thấp, segment hiện tại có thể chưa đầy trong thời gian dài.

### 9.1. Vì sao cần archive_timeout?

Với workload ít ghi, base backup mới tạo nhưng WAL segment cuối có thể còn mở. archive_timeout ép switch theo chu kỳ để WAL có thể được archive sớm hơn.

### 9.2. Chọn giá trị

~~~conf
archive_timeout = 300
~~~

Nghĩa là khoảng 5 phút theo cấu hình timeout, khi có hoạt động WAL phù hợp. Giá trị nhỏ hơn làm archive segments xuất hiện thường xuyên hơn.

### 9.3. Không phải giới hạn RPO tuyệt đối

Timeout không đảm bảo một segment đã đến kho archive trong đúng số giây đó. Archive command, network, disk, cloud API và backlog có thể làm chậm.

### 9.4. Segment cuối

Khi cần kiểm tra archive trong lab, có thể dùng pg_switch_wal() trên primary để đóng segment hiện tại và tạo điều kiện cho archiver xử lý. Đây là thao tác chủ động tạo segment switch, không phải cách chạy liên tục trong mọi ứng dụng.

### 9.5. WAL volume và số file

Timeout quá ngắn có thể tạo nhiều segment partial có padding, tăng object count, metadata operations và chi phí lifecycle của object storage.

## 10. WAL segment naming

Tên WAL segment thường là 24 ký tự hex:

~~~text
TTTTTTTT LLLLLLLL SSSSSSSS
   |        |        |
   |        |        +-- Segment number trong WAL log
   |        +----------- WAL log number
   +-------------------- Timeline ID
~~~

Ví dụ:

~~~text
00000001000000000000000A
~~~

### 10.1. Timeline ID

8 ký tự đầu là timeline ID. Khi recovery được promote hoặc một nhánh WAL mới được tạo, timeline mới có thể xuất hiện.

### 10.2. Log ID

8 ký tự tiếp theo biểu diễn phần log ID trong WAL address.

### 10.3. Segment number

8 ký tự cuối là segment number trong log.

### 10.4. Tên file không phải timestamp

Không thể suy ra thời điểm tạo segment bằng cách đọc chuỗi hex như timestamp. Muốn map LSN/segment cần biết segment size và timeline context.

### 10.5. WAL segment size

Kích thước segment phổ biến là 16 MiB nhưng có thể được chọn khi initdb/build theo phiên bản. Dùng:

~~~sql
SHOW wal_segment_size;
~~~

Không hardcode 16 MiB vào script continuity nếu cluster có segment size khác.

## 11. Từ LSN tới tên WAL file

PostgreSQL có hàm:

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS wal_file;
~~~

### 11.1. pg_walfile_name

Trả tên WAL segment chứa LSN được truyền vào. Hàm này hữu ích để xác định segment chứa backup start/stop hoặc recovery target.

### 11.2. pg_walfile_name_offset

~~~sql
SELECT *
FROM pg_walfile_name_offset(pg_current_wal_lsn());
~~~

Trả tên segment và byte offset bên trong segment.

### 11.3. pg_current_wal_lsn

Trên primary, trả vị trí WAL hiện tại. Trên standby, dùng hàm receive/replay phù hợp vai trò server.

### 11.4. pg_wal_lsn_diff

~~~sql
SELECT pg_wal_lsn_diff(
    '0/5000000'::pg_lsn,
    '0/3000000'::pg_lsn
) AS bytes_between;
~~~

Tính chênh lệch bytes giữa hai LSN. Kết quả hữu ích để định lượng khoảng WAL cần xử lý, không thay thế kiểm tra file thực tế.

### 11.5. Chọn LSN trong backup

Backup metadata có thể cung cấp start/stop LSN và tên WAL cần thiết. Dùng các thông tin này để xác định segment range phải giữ, thay vì lấy segment “mới nhất” làm mốc tùy tiện.

## 12. Timeline và history file

Timeline là nhánh lịch sử WAL. Khi một standby được promote hoặc recovery kết thúc theo một nhánh mới, PostgreSQL tạo timeline mới để các thay đổi tiếp theo thuộc nhánh đó.

### 12.1. Vì sao có timeline?

Sau khi recovery tới một thời điểm rồi cho phép ghi mới, lịch sử mới phân nhánh từ WAL cũ. Timeline ID giúp phân biệt các nhánh có thể có cùng LSN range nhưng nội dung khác.

### 12.2. History file

Khi tạo timeline mới, PostgreSQL tạo một file history có tên dạng:

~~~text
00000002.history
~~~

File này mô tả quan hệ timeline cha và điểm chuyển nhánh. Nó rất quan trọng để recovery chọn đúng chuỗi WAL.

### 12.3. Phải archive history files

Giữ WAL segments mà bỏ timeline history files có thể khiến restore không xác định được nhánh WAL phù hợp. Đảm bảo archive mechanism lưu cả các history files do PostgreSQL gửi tới archiver.

### 12.4. Không ghép timeline chỉ bằng sort tên file

Không thể kiểm tra continuity giữa nhiều timeline bằng cách sort lexical tất cả tên file rồi đòi số segment tăng đều. Phải hiểu timeline ancestry và switchpoint trong history files.

### 12.5. target_timeline

Trong recovery, target_timeline = 'latest' cho phép chọn timeline mới nhất có thể tìm thấy theo quy tắc recovery. Khi cần khôi phục nhánh cụ thể, đặt timeline ID phù hợp và bảo đảm history file tương ứng có sẵn.

## 13. Kiểm tra trạng thái archiver bằng pg_stat_archiver

View hệ thống:

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

### 13.1. archived_count

Số lần archive thành công được thống kê kể từ lần reset stats gần nhất. Đây là counter, không phải số file còn được giữ trong archive.

### 13.2. last_archived_wal

Tên WAL file được archive thành công gần nhất.

### 13.3. last_archived_time

Thời điểm archive thành công gần nhất.

### 13.4. failed_count

Số lần archive thất bại được thống kê. Counter tăng là tín hiệu cần xem log và command output.

### 13.5. last_failed_wal và last_failed_time

Cho biết file và thời điểm thất bại gần nhất theo statistics.

### 13.6. stats_reset

Thời điểm counters được reset. Khi tính rate hoặc so sánh, phải xét reset time.

### 13.7. Không có archive mới chưa chắc lỗi

Nếu database không phát sinh WAL mới hoặc segment chưa được switch, last_archived_time có thể cũ mà archiver vẫn khỏe. Cần tạo hoạt động WAL và switch segment trong một bài kiểm tra có kiểm soát.

## 14. Kiểm tra archive_status

Trong thư mục pg_wal/archive_status, PostgreSQL duy trì trạng thái cho các segment:

- File .ready: segment cần được archive.
- File .done: archiver đã báo archive thành công.

Ví dụ:

~~~text
pg_wal/
  archive_status/
    00000001000000000000000A.ready
    000000010000000000000009.done
~~~

### 14.1. Ready backlog

Nhiều file .ready tồn tại lâu có thể cho thấy archiver không theo kịp, command liên tục thất bại hoặc archive destination không truy cập được.

### 14.2. Done không chứng minh kho archive còn file

.done cho biết PostgreSQL đã nhận báo thành công từ archive mechanism. Nếu ai đó xóa file ở destination sau đó, PostgreSQL không tự phát hiện bằng trạng thái .done.

### 14.3. Không sửa archive_status thủ công

Không xóa .ready, đổi .done hoặc tạo marker giả để ép PostgreSQL bỏ qua archive. Hãy sửa nguyên nhân rồi để archiver quản lý state.

### 14.4. Dùng filesystem monitoring

Giám sát số lượng, tuổi file .ready, kích thước archive, disk free, lỗi command và độ trễ từ WAL creation tới archive completion.

## 15. Kiểm tra archive bằng cách tạo segment mới

Trong môi trường lab hoặc cửa sổ kiểm tra được phê duyệt, trên primary:

~~~sql
SELECT pg_switch_wal();
~~~

Sau đó xem:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

### 15.1. Archive là asynchronous

pg_switch_wal() yêu cầu switch; archiver xử lý sau đó. Kết quả query ngay lập tức có thể chưa phản ánh file mới.

### 15.2. Kiểm tra file đích

Xác minh tên segment mới đã có trong destination, kích thước đúng với segment nguồn và checksum/byte comparison phù hợp.

### 15.3. Kiểm tra log

Nếu failed_count tăng, đọc PostgreSQL server log và output của archive script. Không chỉ dựa vào một dòng SQL.

### 15.4. Không chạy switch quá thường xuyên trên production

pg_switch_wal() tạo segment boundaries. Gọi liên tục có thể làm tăng số WAL files, archive objects và overhead; dùng như một thao tác test có kiểm soát.

## 16. Phân biệt archive với replication và retention trong pg_wal

Các cơ chế sau có liên quan WAL nhưng giải quyết vấn đề khác nhau:

| Cơ chế | Mục đích | Có thay archive backup chain không? |
| --- | --- | --- |
| WAL archiving | Giữ segment ngoài vòng đời pg_wal | Không; là một phần PITR |
| Streaming replication | Gửi WAL tới standby đang hoạt động | Không |
| Replication slot | Giữ WAL cần cho consumer | Không |
| wal_keep_size | Giữ một lượng WAL trong pg_wal cho standby | Không |
| archive_timeout | Ép switch segment theo thời gian | Không |
| Base backup | Tạo ảnh dữ liệu nhất quán để restore | Cần WAL phù hợp đi kèm |

### 16.1. Streaming standby không thay archive

Standby online có thể theo kịp primary nhưng không bảo vệ trước một lỗi logic bị replicate (ví dụ xóa nhầm bảng) nếu không có lịch sử WAL/base backup để PITR.

### 16.2. Replication slot không phải kho lưu trữ

Slot có thể giữ WAL trong pg_wal khi consumer chậm hoặc offline. Nếu slot bị bỏ quên, nó có thể làm đầy disk. Slot không thay archive destination độc lập.

### 16.3. wal_keep_size

wal_keep_size giữ tối thiểu một lượng WAL trong pg_wal cho nhu cầu replication nhất định. Khi vượt vòng đời, segment có thể bị recycle; không coi đây là retention PITR.

### 16.4. Archive và standby có thể phối hợp

Standby có thể được cấu hình archive WAL nhận được khi archive_mode=always, nhưng destination cần thiết kế tránh xung đột và giữ timeline/history chính xác.

## 17. Restore command

Khi phục hồi từ archive, PostgreSQL dùng restore_command để lấy WAL cần thiết.

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
~~~

### 17.1. Placeholders

- %f: tên file cần lấy từ archive.
- %p: đường dẫn đích mà PostgreSQL muốn file được đặt vào.
- %%: ký tự phần trăm literal.

### 17.2. Exit code

Trả 0 khi lấy file thành công; trả non-zero nếu file không tồn tại hoặc thao tác thất bại theo semantics command. PostgreSQL có thể thử tìm WAL tiếp theo/nguồn khác theo recovery logic.

### 17.3. Không trả thành công với file rỗng

Nếu command tạo một file đích rỗng rồi trả 0, PostgreSQL sẽ cố đọc file đó và recovery có thể lỗi. Chỉ báo success khi file đúng đã được lấy đầy đủ.

### 17.4. Timeline history files

restore_command cũng cần tìm được các history files khi recovery yêu cầu chúng. Đảm bảo kho archive chứa những file này và command có thể lấy chúng theo tên.

### 17.5. Đường dẫn trên máy restore

restore_command chạy ở môi trường OS của server đang restore. Path archive phải được mount/truy cập từ host/container restore, không phải đường dẫn trên máy backup operator.

## 18. Base backup và WAL cần thiết

Một PITR chain bắt đầu từ base backup. WAL phải bao phủ từ điểm backup cần để đưa backup về trạng thái nhất quán cho tới target.

### 18.1. Base backup với pg_basebackup

Ví dụ tạo backup directory:

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -U backup_user \
  -D /backup/base_2026_11_14 \
  -Fp \
  -X stream \
  -P
~~~

-X stream yêu cầu pg_basebackup stream WAL đồng thời trong quá trình backup để backup có WAL cần thiết cho consistency. Các lựa chọn backup cụ thể phụ thuộc quy trình và phiên bản.

### 18.2. Backup start và stop

Backup metadata/backup label cung cấp thông tin về điểm bắt đầu/kết thúc và WAL cần thiết. Giữ nguyên các file metadata do công cụ backup tạo.

### 18.3. Không suy ra start segment từ timestamp thư mục

Tên folder backup không chứng minh segment đầu tiên cần thiết. Dùng backup label/manifest và LSN/timeline metadata.

### 18.4. WAL trước backup có thể cần thiết

Một số WAL bắt đầu trước khi lệnh backup kết thúc vẫn cần để phục hồi backup nhất quán. Không chỉ archive các segment có timestamp sau thời điểm hoàn tất backup.

### 18.5. Base backup và archive phải cùng cluster history

Đảm bảo backup và WAL thuộc cùng PostgreSQL cluster/system identifier và timeline ancestry phù hợp. Một WAL file có tên giống nhau từ cluster khác không phải segment thay thế hợp lệ.

## 19. Kiểm tra backup bằng pg_verifybackup

PostgreSQL cung cấp pg_verifybackup để xác minh backup có manifest, checksum và dữ liệu WAL cần thiết theo các khả năng của phiên bản.

~~~bash
pg_verifybackup /backup/base_2026_11_14
~~~

### 19.1. Manifest

Backup có manifest liệt kê các file và checksum theo định dạng backup. Công cụ kiểm tra sự phù hợp của file backup với manifest.

### 19.2. WAL consistency

Công cụ có thể kiểm tra WAL đi kèm backup có hợp lệ/cần thiết để làm backup nhất quán theo khả năng được hỗ trợ. Đây là một kiểm tra quan trọng trước khi đưa backup vào retention.

### 19.3. Không chứng minh toàn bộ archive tương lai liên tục

pg_verifybackup xác minh backup directory và WAL thuộc phạm vi nó kiểm tra. Nó không tự chứng minh kho archive chứa mọi segment từ backup tới một recovery target trong tương lai.

### 19.4. Phiên bản

pg_verifybackup có từ PostgreSQL 13. Tùy chọn và hành vi mở rộng khác nhau theo phiên bản; dùng binary cùng major version phù hợp với backup/server và đọc help của tool đang cài.

### 19.5. Kết hợp restore drill

Một backup pass verify vẫn cần thử restore thật, replay archive tới target và kiểm tra ứng dụng/dữ liệu sau recovery.

## 20. Kiểm tra WAL bằng pg_waldump

pg_waldump đọc và hiển thị WAL records. Đây là công cụ chẩn đoán hữu ích để xác nhận segment có thể parse và quan sát nội dung WAL ở mức record.

~~~bash
pg_waldump \
  --path=/srv/pgarchive \
  --timeline=1 \
  --start=0/3000000 \
  --end=0/5000000
~~~

Ví dụ chỉ mang tính minh họa; thay path, timeline và LSN bằng dữ liệu thực của cluster.

### 20.1. --path

Chỉ định thư mục chứa WAL segments mà công cụ đọc.

### 20.2. --timeline

Chọn timeline ID tương ứng với chuỗi WAL cần xem.

### 20.3. --start và --end

Giới hạn khoảng LSN cần đọc. Có thể dùng để khảo sát một khoảng nhỏ thay vì scan toàn archive.

### 20.4. Parse errors

Nếu file bị cắt, sai format, thiếu segment tiếp theo hoặc thuộc timeline không phù hợp, công cụ có thể báo lỗi. Ghi nhận lỗi và xác minh nguồn file.

### 20.5. pg_waldump không thay restore

pg_waldump đọc WAL records; nó không chứng minh mọi data file, extension, configuration và recovery chain sẽ khởi động thành công. Chỉ restore drill mới kiểm chứng được mục tiêu phục hồi end-to-end.

## 21. Kiểm tra tính liên tục của archive

Một archive có nhiều file WAL chưa chắc là một chuỗi liên tục. Cần xác định **khoảng WAL bắt buộc**, timeline và các segment cần thiết.

### 21.1. Xác định điểm bắt đầu

Lấy backup start LSN, backup label/manifest và timeline của base backup.

### 21.2. Xác định điểm kết thúc

Chọn recovery target theo LSN/time/name hoặc target đã được hệ thống backup ghi nhận. Map target LSN sang WAL filename bằng PostgreSQL function trong môi trường có cùng cluster metadata.

### 21.3. Liệt kê segment trong khoảng

Với cùng một timeline và segment size, các tên segment phải liên tiếp theo thứ tự WAL address. Tạo danh sách kỳ vọng từ start segment tới end segment bằng logic biết segment size; không sort toàn bộ tên file ở nhiều timeline rồi so chuỗi.

### 21.4. Kiểm tra file thực tế

Với từng segment bắt buộc:

- File tồn tại ở archive storage.
- File không rỗng và có kích thước hợp lệ.
- Checksum hoặc byte validation khớp với nguồn/manifest nếu có.
- Có thể đọc/parse bằng công cụ phù hợp.
- Không bị nén/encrypt mà restore_command không thể giải mã.

### 21.5. Timeline ancestry

Nếu target nằm trên timeline mới, phải giữ history files và các segment trên timeline cha tới switchpoint, sau đó tiếp tục trên timeline con. Dùng history metadata để xây chain.

### 21.6. Khoảng trống

Một segment thiếu trong đoạn WAL bắt buộc có thể khiến recovery không tiến qua được vị trí đó. Segment thiếu ngoài khoảng cần thiết cho backup/target không nhất thiết làm chain cụ thể đó thất bại.

### 21.7. Archive không cần có mọi segment từ ngày đầu cluster

Mỗi base backup có một điểm bắt đầu WAL cần thiết. Retention có thể xóa WAL cũ hơn nếu mọi backup còn giữ đều không còn phụ thuộc vào chúng và policy cho phép.

## 22. Tính segment range theo segment size

PostgreSQL có các hàm map LSN thành WAL file. Để xây danh sách kiểm tra, trước hết lấy:

~~~sql
SHOW wal_segment_size;
~~~

Sau đó xác định:

~~~sql
SELECT
    pg_walfile_name('0/3000000'::pg_lsn) AS start_file,
    pg_walfile_name('0/5000000'::pg_lsn) AS end_file;
~~~

### 22.1. Vì sao không tự cắt LSN bằng chuỗi?

LSN là địa chỉ 64-bit dạng hai phần hex; tên segment còn phụ thuộc timeline và WAL segment size. Phân tích string bằng script ngắn có thể sai khi log ID/segment rollover.

### 22.2. Dùng hàm PostgreSQL

pg_walfile_name() và pg_walfile_name_offset() là cách an toàn để map một LSN cụ thể khi chạy trên server tương ứng.

### 22.3. Tạo expected manifest

Một công cụ archive kiểm tra nên nhận:

- System identifier/cluster identity.
- Segment size.
- Timeline history.
- Backup start LSN và required WAL.
- Recovery target LSN/timeline.

Từ đó tạo danh sách segment kỳ vọng và so với object inventory.

### 22.4. Đừng coi lexical gap là lỗi trong mọi trường hợp

Timeline switch, file history, segment archive từ nhiều cluster hoặc retention boundaries có thể làm tên file không tăng theo một chuỗi đơn giản. Phải so sánh theo chain cụ thể.

## 23. Kiểm tra checksum và tính toàn vẹn file

### 23.1. File size

WAL segment thông thường có kích thước đúng bằng wal_segment_size; history file nhỏ hơn và không theo kích thước segment. Một file segment ngắn bất thường cần điều tra.

### 23.2. Hash

Có thể tạo checksum khi archive:

~~~bash
sha256sum /srv/pgarchive/00000001000000000000000A
~~~

Lưu checksum trong manifest độc lập hoặc hệ thống object metadata. Hash giúp phát hiện thay đổi/corruption, nhưng chỉ hữu ích nếu checksum được bảo vệ và có nguồn đối chiếu tin cậy.

### 23.3. Hash không chứng minh continuity

Một tập file có checksum đúng vẫn có thể thiếu segment ở giữa. Integrity từng object và continuity của chuỗi là hai kiểm tra riêng.

### 23.4. Object storage checksum

Một số dịch vụ object storage cung cấp checksum/ETag có semantics khác nhau tùy multipart upload/encryption. Không mặc định ETag luôn là MD5 của nội dung.

### 23.5. Kiểm tra sau upload

Nếu archive tool upload thành công nhưng chưa xác minh object có thể đọc lại, có thể báo success quá sớm. Dùng cơ chế upload completion, checksum và read-after-write semantics được dịch vụ đảm bảo.

## 24. Khoảng trống archive và nguyên nhân thường gặp

### 24.1. Archive command trả lỗi

Lệnh copy/upload trả non-zero, archiver retry và segment còn pending. Xem pg_stat_archiver, PostgreSQL log và script log.

### 24.2. Hết dung lượng

Archive filesystem/object quota đầy; command thất bại. Giám sát disk free, quota, object count và retention.

### 24.3. Mất mount/network

Thư mục mount biến mất hoặc network storage unavailable. Command có thể tạo file cục bộ ngoài ý muốn nếu mount point rỗng; kiểm tra mount trước khi ghi.

### 24.4. Permission

OS account chạy PostgreSQL không có quyền ghi/đọc archive path hoặc credential cloud hết hạn.

### 24.5. File đích tồn tại nhưng khác

Archive script thấy tên file đã có và trả success mà không so sánh nội dung; đây là lỗi thiết kế có thể che corruption hoặc collision.

### 24.6. Segment bị xóa bởi retention quá sớm

Retention job xóa WAL mà backup còn cần. Đây là nguyên nhân PITR thường gặp; phải gắn retention với backup chain thay vì chỉ xóa file cũ hơn N ngày.

### 24.7. Timeline history bị thiếu

WAL segments tồn tại nhưng .history bị xóa hoặc không archive. Recovery có thể không dựng được nhánh timeline.

### 24.8. Backup metadata không còn

Không còn manifest/backup label/LSN metadata khiến khó xác định required WAL range. Bảo quản metadata cùng backup.

### 24.9. Sai cluster

WAL từ một cluster khác được đưa vào cùng archive prefix. Dùng namespace theo cluster/system identifier và kiểm tra provenance.

### 24.10. Không có base backup phù hợp

Archive có thể đầy đủ nhưng không có base backup còn dùng được; PITR vẫn không khả thi.

## 25. PITR: phục hồi tới một thời điểm

Giả sử có base backup trong /restore/cluster và archive WAL trong /srv/pgarchive. Trên server restore, cấu hình recovery:

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
~~~

Tạo file signal thích hợp:

~~~bash
touch /restore/cluster/recovery.signal
~~~

Sau đó khởi động PostgreSQL để recovery đọc base backup và replay WAL.

### 25.1. recovery.signal

Trong PostgreSQL 12 trở lên, file recovery.signal yêu cầu server vào archive recovery. File standby.signal được dùng cho standby mode.

### 25.2. Recovery target

Có thể chọn target theo:

- recovery_target_time.
- recovery_target_lsn.
- recovery_target_name.
- recovery_target_xid.

Chọn target phù hợp và bảo đảm WAL archive chứa toàn bộ chain tới target.

### 25.3. recovery_target_action

Các lựa chọn gồm pause, promote hoặc shutdown theo version/semantics. pause hữu ích khi muốn kiểm tra trạng thái ngay tại target trước khi quyết định promote/tiếp tục.

### 25.4. recovery_target_inclusive

Điều khiển việc target record có được bao gồm hay không cho một số target types. Đọc semantics chính xác theo phiên bản và target đã chọn.

### 25.5. recovery_target_timeline

Chọn timeline cần replay, thường là latest hoặc timeline cụ thể. Đừng chọn latest nếu quy trình yêu cầu phục hồi nhánh cũ.

## 26. PITR theo LSN hoặc named restore point

### 26.1. Recovery theo LSN

~~~conf
recovery_target_lsn = '0/5A0000F0'
recovery_target_action = 'pause'
~~~

LSN hữu ích khi ứng dụng/backup orchestration đã ghi nhận một mốc WAL chính xác.

### 26.2. Tạo named restore point

Trên primary, trước thao tác rủi ro:

~~~sql
SELECT pg_create_restore_point('before_customer_migration');
~~~

PostgreSQL ghi một named restore point trong WAL. Ghi lại LSN trả về cùng thời điểm và thông tin deployment.

### 26.3. Recovery theo tên

~~~conf
recovery_target_name = 'before_customer_migration'
recovery_target_action = 'pause'
~~~

### 26.4. Restore point không phải backup

Named restore point chỉ là mốc trong WAL. Vẫn cần base backup và WAL liên tục để replay tới đó.

### 26.5. Tránh trùng tên

Đặt restore point name có ý nghĩa, có timestamp/version nếu cần, và lưu trong deployment/change log.

## 27. Timeline history và restore chain

Ví dụ một primary chạy trên timeline 1. Standby được promote thành timeline 2:

~~~text
Timeline 1:
  WAL ... A -- B -- C -- D
                     |
                     +---- promotion point
                              |
Timeline 2:                   +-- E -- F -- G

History file: 00000002.history
  parent timeline = 1
  switchpoint = vị trí WAL tại nhánh
~~~

### 27.1. Segment cha

Recovery cần timeline 1 tới điểm switchpoint.

### 27.2. Segment con

Sau switchpoint, recovery đi tiếp trên timeline 2.

### 27.3. History file

00000002.history mô tả timeline 2 xuất phát từ đâu. Giữ file này cùng archive.

### 27.4. Nhiều lần promote

Một hệ thống có thể tạo timeline 3, 4... Recovery target trên nhánh mới cần chain history từ timeline gốc tới timeline đích.

### 27.5. Không xóa WAL timeline cha theo tuổi file đơn thuần

Một backup cũ hoặc target ở nhánh khác có thể còn cần segment timeline cha. Retention phải hiểu ancestry và backup dependencies.

## 28. Archive retention và backup lifecycle

Không thể đặt retention chỉ bằng câu “xóa WAL cũ hơn 7 ngày” nếu base backup cần WAL từ trước thời điểm đó.

### 28.1. Dependency

Mỗi base backup có một khoảng WAL tối thiểu cần thiết. Khi backup được giữ lại, các segment trong chain cần giữ theo policy.

### 28.2. Retention theo backup

Một quy trình backup manager nên biết backup nào còn hợp lệ, backup nào đã hết hạn và WAL nào là dependency của backup còn giữ.

### 28.3. pg_archivecleanup

PostgreSQL cung cấp pg_archivecleanup để xóa WAL archive không còn cần thiết theo một mốc WAL file được chọn, thường dùng trong một số cấu hình standby/archive cleanup.

~~~bash
pg_archivecleanup /srv/pgarchive 000000010000000000000020
~~~

Đây chỉ là minh họa cú pháp; không chạy trực tiếp nếu chưa xác định retention boundary và dependencies.

### 28.4. Không dùng pg_archivecleanup như retention manager tổng quát

Tool không hiểu toàn bộ inventory base backups, PITR windows, object locks, nhiều timelines và yêu cầu pháp lý của tổ chức. Cần orchestration biết các dependency.

### 28.5. WAL-G, pgBackRest và công cụ backup khác

Các công cụ chuyên dụng có thể quản lý base backups, WAL archive, retention và verify theo repository. Chọn một công cụ có policy rõ ràng thay vì tự viết toàn bộ lifecycle nếu hệ thống cần độ tin cậy cao.

### 28.6. Object lifecycle

Lifecycle rule của object storage không được xóa WAL còn cần cho backup. Đồng bộ retention policy giữa backup manager và object lifecycle.

## 29. RPO, RTO và archive lag

### 29.1. RPO

Recovery Point Objective là lượng dữ liệu tối đa tổ chức chấp nhận mất theo thời gian. Nếu chỉ có archive WAL, RPO phụ thuộc độ trễ từ lúc WAL được tạo tới lúc segment được lưu bền vững và có thể khôi phục.

### 29.2. RTO

Recovery Time Objective là thời gian mục tiêu để đưa dịch vụ trở lại. RTO phụ thuộc kích thước base backup, tốc độ restore, số WAL phải replay, I/O và validation sau recovery.

### 29.3. Archive lag

Khoảng cách giữa WAL hiện tại và WAL đã archive thành công gần nhất. Cần tính theo LSN/segment và timeline, không chỉ nhìn timestamp.

### 29.4. Tạo nhiều archive objects

Segment nhỏ/timeout ngắn có thể làm tăng số object và overhead listing/retrieval. RPO tốt hơn không miễn phí.

### 29.5. Replay time

Một chain dài nhiều giờ/ngày có thể mất thời gian replay đáng kể. Base backup thường xuyên hơn có thể giảm RTO nhưng tăng chi phí backup.

## 30. Monitoring và cảnh báo

Một bộ monitoring cơ bản nên thu thập:

| Chỉ số | Mục đích |
| --- | --- |
| archived_count | Số lần archive thành công kể từ reset |
| failed_count | Số lần archive thất bại |
| last_archived_wal/time | Tiến độ archive gần nhất |
| last_failed_wal/time | Lỗi gần nhất |
| Số file .ready | Backlog đang chờ |
| Tuổi file .ready lâu nhất | Độ trễ xử lý |
| Archive storage free/quota | Nguy cơ hết dung lượng |
| WAL bytes generated | Tốc độ phát sinh WAL |
| Archive bytes uploaded | Throughput archive |
| Segment gap checker | Tính liên tục theo chain |
| Backup verify status | Khả năng dùng backup |
| Restore drill status/time | Khả năng phục hồi thực tế |

### 30.1. Alert theo failed_count delta

Theo dõi mức tăng của failed_count giữa hai lần scrape; một counter tích lũy cần được tính delta và xử lý stats reset.

### 30.2. Alert theo archive age

Nếu workload có WAL activity nhưng last_archived_time quá cũ, cảnh báo. Cần tránh alert giả khi database không có thay đổi.

### 30.3. Alert theo ready backlog

Số .ready tăng hoặc tuổi file lớn nhất tăng là dấu hiệu archiver không theo kịp.

### 30.4. Alert theo disk

Archive destination đầy có thể làm archive fail; pg_wal cũng có thể phình vì WAL không được archive/recycle hoặc bị replication slot giữ.

### 30.5. Monitoring phải có test

Định kỳ tạo một segment trong môi trường test, xác nhận nó xuất hiện trong archive và có thể đọc lại.

## 31. Quy trình restore drill

Một restore drill cần diễn tập toàn bộ chuỗi:

1. Chọn một base backup còn trong retention.
2. Lấy backup manifest/label, start LSN, timeline và required WAL.
3. Xác định recovery target và timeline ancestry.
4. Tạo inventory WAL segments/history files bắt buộc.
5. Kiểm tra object tồn tại, size, checksum và parse.
6. Chạy pg_verifybackup trên backup phù hợp.
7. Tạo một PostgreSQL instance restore cô lập.
8. Cấu hình restore_command, target và signal file.
9. Khởi động và theo dõi recovery logs.
10. Xác nhận PostgreSQL đạt target hoặc trạng thái pause mong đợi.
11. Kiểm tra schema, số hàng, transaction marker và dữ liệu ứng dụng.
12. Ghi thời gian restore, WAL replay duration, lỗi và kết quả.
13. Hủy môi trường test theo quy trình an toàn sau khi lưu report.

### 31.1. Restore vào môi trường cô lập

Không phục hồi thử đè lên primary production. Dùng host/volume riêng, network isolation và port riêng.

### 31.2. Kiểm tra ứng dụng

Database start thành công chưa đủ. Chạy các truy vấn kiểm tra business invariants, foreign keys, row counts hoặc smoke tests.

### 31.3. Đo RTO thực tế

Ghi thời gian lấy base backup, copy/restore files, replay WAL, startup và application validation. Đây là dữ liệu để điều chỉnh RTO.

### 31.4. Diễn tập failure scenarios

Thử một backup thiếu WAL, một segment checksum sai, một history file thiếu và một archive command không truy cập được trong lab để xác nhận cảnh báo/runbook.

### 31.5. Lưu bằng chứng

Lưu backup ID, system identifier, timeline, target LSN/time, danh sách segment, tool versions, log và kết quả test.

## 32. Quy trình vận hành khi archive bị lỗi

Khi failed_count tăng hoặc .ready backlog kéo dài:

### Bước 1. Xác định segment lỗi

~~~sql
SELECT
    failed_count,
    last_failed_wal,
    last_failed_time,
    last_archived_wal,
    last_archived_time
FROM pg_stat_archiver;
~~~

### Bước 2. Đọc log

Tìm command exit status, permission denied, no space, mount/network error, credential expiry hoặc checksum mismatch.

### Bước 3. Kiểm tra destination

Xác minh archive directory/mount/object bucket đúng, còn dung lượng và có thể ghi/đọc.

### Bước 4. Kiểm tra script

Chạy thử script với một file test trong môi trường an toàn, xác nhận exit code và nội dung đích. Không tự ý copy/xóa file WAL production để thử.

### Bước 5. Khắc phục

Sửa permission, mount, credentials, quota hoặc command; reload cấu hình nếu đã thay archive_command.

### Bước 6. Để archiver retry

PostgreSQL sẽ thử lại các file chưa archive. Theo dõi .ready, failed_count và last_archived_wal.

### Bước 7. Kiểm tra continuity

Sau khi backlog xử lý xong, xác nhận tất cả segment trong khoảng cần thiết đã có ở destination, không chỉ segment mới nhất.

### Bước 8. Đánh giá pg_wal pressure

Nếu archiver fail kéo dài, WAL có thể không được recycle và disk pg_wal tăng. Theo dõi disk và replication slots; không xóa WAL bằng OS.

## 33. archive_command thay đổi và reload

Sau khi sửa archive_command:

~~~sql
SELECT pg_reload_conf();
~~~

Kiểm tra:

~~~sql
SELECT name, setting, source, pending_restart
FROM pg_settings
WHERE name IN ('archive_command', 'archive_timeout', 'archive_mode');
~~~

### 33.1. archive_command

Thường áp dụng sau reload.

### 33.2. archive_mode

Cần restart; pg_reload_conf() không bật archiving nếu server đang chạy với archive_mode off.

### 33.3. archive_timeout

Có thể thay đổi bằng reload theo tham số/version behavior.

### 33.4. Kiểm tra server log

Nếu cấu hình mới sai quoting/path, PostgreSQL log sẽ có thông tin lỗi. Không cho rằng pg_reload_conf() trả true nghĩa mọi tham số đã được áp dụng như mong đợi.

## 34. WAL archive và cloud/object storage

Khi archive lên object storage, command cần upload segment hoàn chỉnh và chỉ trả thành công sau khi dịch vụ xác nhận upload thành công.

### 34.1. Object key

Có thể tổ chức theo cluster identity/timeline/year/month hoặc prefix ổn định. Không thay đổi naming khiến restore_command không tìm được file theo %f.

### 34.2. Upload multipart

Nếu dùng multipart upload, phải complete multipart trước khi báo success. Upload dở không phải archive file hợp lệ.

### 34.3. Checksum

Lưu checksum/metadata phù hợp. Xác minh semantics checksum của dịch vụ, đặc biệt với multipart và server-side encryption.

### 34.4. Retry

Client upload phải xử lý retry idempotent. Object đã tồn tại phải được xác minh là cùng nội dung.

### 34.5. Restore latency

PITR có thể cần đọc hàng nghìn segment. Đánh giá tốc độ list/get, parallelism của công cụ backup, egress và cache.

### 34.6. Credentials

Dùng IAM/service identity với quyền tối thiểu: ghi archive ở primary, đọc archive ở restore host; không dùng một key admin dùng chung cho mọi server.

### 34.7. Immutable retention

Object lock/versioning có thể bảo vệ khỏi xóa nhầm hoặc ransomware, nhưng cần policy rõ và kiểm thử chi phí/khả năng restore.

## 35. Nén và mã hóa WAL archive

### 35.1. Nén

WAL có thể nén để giảm storage, tùy mức độ lặp và workload. Archive tool phải ghi nhận định dạng nén và restore_command/tool phải giải nén trước khi PostgreSQL đọc file.

### 35.2. Không đặt extension tùy ý

Nếu archive file được nén thành .gz, PostgreSQL vẫn yêu cầu restore command trả ra file WAL tên đúng tại %p; command cần giải nén vào destination path đó.

Ví dụ:

~~~conf
restore_command = 'gzip -dc /srv/pgarchive/%f.gz > "%p"'
~~~

Chỉ dùng nếu archive process thực sự lưu từng WAL segment dưới dạng gzip với tên tương ứng.

### 35.3. Mã hóa

Mã hóa archive bảo vệ dữ liệu khi lưu/truyền. Restore workflow phải lấy key/credential hợp lệ và giải mã trước khi PostgreSQL đọc WAL.

### 35.4. Key management

Không lưu key giải mã duy nhất trong cùng archive bucket mà không có bản dự phòng độc lập. Mất key đồng nghĩa mất khả năng restore dù file vẫn tồn tại.

### 35.5. Compression/encryption phải được test end-to-end

Kiểm tra upload, checksum, download, decrypt, decompress, WAL parse và full restore. Một file tải xuống thành công nhưng giải nén sai vẫn không hữu dụng.

## 36. Kiểm tra bằng SQL và shell

### 36.1. Archiver status

~~~sql
SELECT *
FROM pg_stat_archiver;
~~~

### 36.2. Current WAL location

~~~sql
SELECT
    pg_current_wal_lsn(),
    pg_walfile_name(pg_current_wal_lsn());
~~~

Chạy trên primary. Trên standby, dùng các hàm receive/replay phù hợp.

### 36.3. Segment size

~~~sql
SHOW wal_segment_size;
~~~

### 36.4. Switch trong lab

~~~sql
SELECT pg_switch_wal();
~~~

### 36.5. List archive files

~~~bash
find /srv/pgarchive -maxdepth 1 -type f -printf '%f %s bytes\n' | sort
~~~

Đây là ví dụ Linux. Với object storage, dùng CLI/API inventory của dịch vụ.

### 36.6. Check checksum

~~~bash
sha256sum /srv/pgarchive/00000001000000000000000A
~~~

### 36.7. Parse WAL

~~~bash
pg_waldump --path=/srv/pgarchive --timeline=1
~~~

Giới hạn LSN/time nếu archive lớn; xác nhận segment naming/timeline trước khi đọc.

## 37. WAL archive và các công cụ backup

### 37.1. pg_basebackup

Tạo physical base backup từ PostgreSQL server. Có thể stream WAL trong quá trình backup với tùy chọn phù hợp.

### 37.2. pg_verifybackup

Kiểm tra tính toàn vẹn backup theo manifest và các kiểm tra WAL được hỗ trợ.

### 37.3. pg_waldump

Đọc WAL records để chẩn đoán segment và phạm vi LSN.

### 37.4. pg_archivecleanup

Dọn WAL archive cũ hơn một boundary theo một số workflow; phải bảo đảm không xóa dependency của backup còn giữ.

### 37.5. pgBackRest / WAL-G

Công cụ backup chuyên dụng có thể quản lý backup sets, WAL archive, retention, encryption, compression và restore. Cần cấu hình repository và verify theo tài liệu công cụ/version.

### 37.6. Không trộn nhiều archive managers

Nếu hai công cụ cùng quản lý cùng một archive path/retention, chúng có thể xóa hoặc ghi file mà bên kia còn cần. Chọn một owner rõ ràng cho archive lifecycle.

## 38. Các lỗi cấu hình thường gặp

### Lỗi 1. archive_mode vẫn off

Có archive_command nhưng chưa bật archive_mode hoặc chưa restart. Kiểm tra pg_settings.pending_restart.

### Lỗi 2. wal_level không phù hợp

Đặt wal_level minimal làm mất khả năng WAL cần thiết cho PITR/replication. Dùng replica hoặc logical theo yêu cầu.

### Lỗi 3. Path là đường dẫn laptop

Archive command chạy ở OS server PostgreSQL; nó không thấy filesystem laptop nếu không được mount.

### Lỗi 4. Destination directory chưa tồn tại

Command thất bại liên tục. Tạo directory, mount và quyền trước khi bật archiving.

### Lỗi 5. Exit code luôn bằng 0

Script bỏ qua lỗi copy/upload nhưng trả success; PostgreSQL đánh dấu segment done dù file không có.

### Lỗi 6. File đã tồn tại thì trả success vô điều kiện

File có thể sai nội dung. So sánh bytes/checksum trước khi coi retry là thành công.

### Lỗi 7. Copy trực tiếp file cuối

Process bị kill có thể để lại file dở. Dùng temp + atomic publish hoặc cơ chế upload hoàn chỉnh.

### Lỗi 8. Không archive timeline history

Recovery qua timeline switch có thể thất bại do thiếu .history.

### Lỗi 9. Retention xóa WAL quá sớm

Một base backup còn giữ có thể mất segment cần để replay. Retention phải dựa trên dependency.

### Lỗi 10. Chỉ nhìn last_archived_wal

File mới nhất có thể đã archive nhưng một segment ở giữa bị thiếu. Cần continuity checker theo range.

### Lỗi 11. Chỉ nhìn failed_count

Không có failure counter tăng không chứng minh mọi file trong kho còn tồn tại và đọc được.

### Lỗi 12. Nhầm archive với streaming replication

Standby khỏe không chứng minh archive PITR đầy đủ.

### Lỗi 13. Nhầm wal_keep_size với retention archive

wal_keep_size chỉ ảnh hưởng WAL giữ trong pg_wal cho replication; không tạo kho archive.

### Lỗi 14. Dùng archive_timeout quá thấp

Tạo nhiều segment partial và tăng object/file overhead.

### Lỗi 15. Không thử restore

Backup/archive chỉ được chứng minh khi restore được tới target và dữ liệu sau recovery hợp lệ.

### Lỗi 16. Đọc sai timeline ID

Segment cùng LSN ở timeline khác có thể khác nội dung. Không thay file theo tên log/segment mà bỏ timeline.

### Lỗi 17. Thiếu system identifier

Trộn archive từ nhiều cluster vào cùng namespace làm tăng nguy cơ restore nhầm.

### Lỗi 18. Chỉ kiểm tra file size

File có đúng số bytes vẫn có thể hỏng. Kết hợp checksum, parse WAL và restore.

### Lỗi 19. Hash nhưng không có trusted manifest

Checksum được lưu cùng nơi có thể bị thay cùng file; bảo vệ metadata/checksum độc lập.

### Lỗi 20. Object upload chưa complete

Command trả success trước khi multipart upload complete; object không đọc được khi restore.

### Lỗi 21. restore_command không giải nén/giải mã

PostgreSQL nhận file nén hoặc encrypted thay vì WAL segment raw. Command phải trả đúng nội dung tại %p.

### Lỗi 22. restore_command trả 0 khi file thiếu

Tạo file rỗng hoặc không hợp lệ rồi báo thành công khiến recovery lỗi khó hiểu. Trả non-zero khi không lấy được file.

### Lỗi 23. Dùng target_time không có timezone rõ

Thời điểm recovery có thể bị hiểu khác theo timezone. Dùng timestamp có offset rõ và ghi lại timezone.

### Lỗi 24. Xóa WAL trong pg_wal bằng OS

Có thể phá crash recovery/replication và làm cluster hỏng. Chỉ dùng PostgreSQL/tool quản lý WAL.

### Lỗi 25. Đặt archive cùng data disk

Disk/host failure có thể làm mất cả database và archive. Tách failure domain.

## 39. Bài tập thực hành

Các bài dựa trên PostgreSQL primary/standby và archive repository trong môi trường lab. Không thay đổi archive settings hoặc chạy restore trên production chỉ để làm bài.

### Bài 1. WAL archive

WAL archiving khác crash recovery như thế nào?

### Bài 2. PITR

Hai thành phần tối thiểu nào cần có để phục hồi database tới một thời điểm?

### Bài 3. wal_level

Mức wal_level nào thường cần cho PITR và streaming replication?

### Bài 4. archive_mode

Thay đổi archive_mode có cần restart PostgreSQL không?

### Bài 5. on và always

Khác biệt chính giữa archive_mode=on và always?

### Bài 6. archive_command

Ý nghĩa của %p và %f là gì?

### Bài 7. Exit code

Archive command nên trả 0 trong trường hợp nào?

### Bài 8. Retry

Vì sao archive command cần idempotent?

### Bài 9. Existing file

Nếu file archive đích đã tồn tại, cần kiểm tra gì trước khi trả success?

### Bài 10. Temp file

Vì sao nên copy/upload vào file tạm rồi mới publish tên cuối?

### Bài 11. archive_timeout

Mục đích của archive_timeout là gì?

### Bài 12. WAL segment size

Viết SQL lấy segment size của cluster.

### Bài 13. WAL filename

Viết SQL lấy WAL filename chứa current WAL LSN trên primary.

### Bài 14. Segment name

Tên WAL segment có những thành phần nào?

### Bài 15. Timeline

Timeline history file dùng để làm gì?

### Bài 16. pg_stat_archiver

Viết query hiển thị success/failure counters và WAL/time gần nhất.

### Bài 17. archive_status

File .ready và .done biểu thị gì?

### Bài 18. pg_switch_wal

Vì sao gọi pg_switch_wal trong lab có thể giúp kiểm tra archiver?

### Bài 19. Streaming

Vì sao một standby streaming khỏe không chứng minh PITR archive chain đầy đủ?

### Bài 20. Replication slot

Replication slot có thay thế archive repository không?

### Bài 21. restore_command

Ý nghĩa của %f và %p trong restore_command?

### Bài 22. Base backup

Vì sao WAL archive không thể thay thế base backup?

### Bài 23. pg_verifybackup

Công cụ này kiểm tra những gì và giới hạn quan trọng nào?

### Bài 24. pg_waldump

pg_waldump giúp kiểm tra điều gì?

### Bài 25. Continuity

Nêu bốn bước để kiểm tra WAL liên tục từ backup tới target.

### Bài 26. Timeline chain

Khi target nằm ở timeline 2 được fork từ timeline 1, cần giữ những gì?

### Bài 27. Gap

Một segment thiếu nằm trong required WAL range gây hậu quả gì?

### Bài 28. Checksum

Checksum file có chứng minh archive chain liên tục không?

### Bài 29. Retention

Vì sao không thể chỉ xóa mọi WAL cũ hơn 7 ngày?

### Bài 30. pg_archivecleanup

Tool này làm gì và vì sao phải thận trọng?

### Bài 31. RPO

Archive lag ảnh hưởng RPO thế nào?

### Bài 32. RTO

Base backup và WAL replay length ảnh hưởng RTO thế nào?

### Bài 33. failed_count

Viết query đọc last_failed_wal, failed_count và last_archived_wal.

### Bài 34. backlog

Nêu hai tín hiệu cho thấy archiver không theo kịp.

### Bài 35. Archive command lỗi

Kể bốn nguyên nhân thường gặp làm command thất bại.

### Bài 36. restore signal

PostgreSQL 12+ dùng file signal nào để bắt đầu archive recovery?

### Bài 37. Recovery target

Nêu ba loại recovery target có thể dùng cho PITR.

### Bài 38. Restore drill

Nêu năm bước quan trọng của một restore drill.

### Bài 39. Archive storage

Vì sao nên đặt archive ở failure domain khác data directory?

### Bài 40. Thiết kế tổng thể

Đề xuất quy trình từ base backup, archive WAL, kiểm tra continuity tới PITR test định kỳ.

## 40. Lời giải tham khảo

### Bài 1–2. Archiving và PITR

Crash recovery dùng WAL trong vòng đời hoạt động của cluster để khôi phục sau crash. Archiving giữ segment ngoài pg_wal để phục hồi dài hạn. PITR cần base backup phù hợp và chuỗi WAL cần thiết tới target.

### Bài 3–5. Cấu hình

wal_level=replica hoặc logical thường cần cho PITR/replication. Thay archive_mode cần restart. on archive WAL được tạo trên primary; always còn archive WAL được nhận/replay trong recovery/standby theo semantics của nó.

### Bài 6–10. Archive command

%p là path nguồn, %f là filename. Trả 0 chỉ khi file đã được lưu đầy đủ và hợp lệ. Idempotency cần vì PostgreSQL retry. Nếu file đích tồn tại, so sánh nội dung/checksum. Temp + atomic publish tránh công bố file copy dở.

### Bài 11–14. Segment

archive_timeout ép switch segment theo khoảng thời gian để giảm chờ segment đầy. Segment size:

~~~sql
SHOW wal_segment_size;
~~~

Current filename:

~~~sql
SELECT pg_walfile_name(pg_current_wal_lsn());
~~~

Tên segment gồm timeline ID, log ID và segment number.

### Bài 15. Timeline

History file mô tả timeline con xuất phát từ timeline cha ở switchpoint nào; recovery cần nó để chọn đúng WAL branch.

### Bài 16–18. Monitoring

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

.ready nghĩa segment đang chờ archive; .done nghĩa archive mechanism báo thành công. pg_switch_wal() trong lab đóng segment để tạo cơ hội cho archiver xử lý, nhưng archive hoàn tất bất đồng bộ.

### Bài 19–20. Replication

Streaming standby không lưu đầy đủ lịch sử WAL ngoài retention và có thể replicate lỗi logic. Replication slot giữ WAL trong pg_wal cho consumer; không phải kho archive PITR.

### Bài 21–24. Restore và tool

restore_command: %f là tên file archive, %p là path đích. Base backup chứa trạng thái data files cần làm điểm bắt đầu. pg_verifybackup kiểm tra backup manifest/checksum và WAL trong phạm vi hỗ trợ; không chứng minh archive tương lai liên tục. pg_waldump parse WAL records, hữu ích để phát hiện segment lỗi/khảo sát LSN.

### Bài 25–28. Continuity

Quy trình: lấy backup start LSN/timeline; xác định target LSN/timeline; dựng expected segment range và history ancestry; xác nhận mọi file tồn tại/size/checksum; parse và thử restore. Với timeline 2 cần history file, WAL timeline 1 tới switchpoint và WAL timeline 2 từ đó tới target. Segment thiếu trong required range có thể chặn recovery. Checksum chỉ kiểm tra integrity object, không chứng minh không có gap.

### Bài 29–30. Retention

Backup còn giữ có thể phụ thuộc WAL cũ hơn 7 ngày. pg_archivecleanup dọn theo boundary file trong workflow phù hợp, nhưng không thay backup manager biết mọi backup/timeline dependencies.

### Bài 31–32. RPO/RTO

Archive lag lớn có thể làm mất nhiều thay đổi hơn khi primary hỏng, tăng RPO. Base backup lớn và WAL replay dài làm restore chậm, tăng RTO; backup thường xuyên hơn có thể giảm replay nhưng tăng chi phí.

### Bài 33–35. Lỗi và backlog

~~~sql
SELECT
    failed_count,
    last_failed_wal,
    last_failed_time,
    last_archived_wal,
    last_archived_time
FROM pg_stat_archiver;
~~~

Backlog .ready tăng/già và last archived age tăng khi có WAL activity là hai tín hiệu. Nguyên nhân gồm permission, disk full, mount/network failure, credential expired, command sai hoặc object upload chưa complete.

### Bài 36–37. Recovery

PostgreSQL 12+ dùng recovery.signal cho archive recovery. Recovery targets có thể là time, LSN, named restore point hoặc transaction ID.

### Bài 38. Restore drill

Chọn backup; xác định WAL/timeline range; verify backup và archive files; restore vào host cô lập với restore_command/target; kiểm tra PostgreSQL và business data; ghi RTO và kết quả.

### Bài 39–40. Thiết kế

Archive ở failure domain khác bảo vệ trước mất host/disk chứa database. Một quy trình đầy đủ tạo base backup theo lịch, archive WAL liên tục với command idempotent, giám sát backlog/failure/disk, kiểm tra continuity theo backup dependency/timeline, retention có hiểu chain, và restore drill định kỳ.

## 41. Bảng tra cứu nhanh

| Nhu cầu | Công cụ/cấu hình |
| --- | --- |
| Bật archiving | archive_mode = on |
| Archive WAL bằng command | archive_command |
| Archive bằng module | archive_library nếu phiên bản hỗ trợ |
| Ép switch segment | archive_timeout |
| Xem WAL level | SHOW wal_level |
| Xem segment size | SHOW wal_segment_size |
| Map LSN sang file | pg_walfile_name(lsn) |
| Map LSN và offset | pg_walfile_name_offset(lsn) |
| Switch segment trong lab | pg_switch_wal() |
| Theo dõi archive success/failure | pg_stat_archiver |
| Xem segment đang chờ | pg_wal/archive_status/*.ready |
| Lấy WAL khi restore | restore_command |
| Verify base backup | pg_verifybackup |
| Parse WAL records | pg_waldump |
| Dọn archive theo boundary | pg_archivecleanup |
| Bắt đầu archive recovery | recovery.signal |
| Bắt đầu standby mode | standby.signal |
| Recovery tới thời điểm | recovery_target_time |
| Recovery tới LSN | recovery_target_lsn |
| Recovery tới restore point | recovery_target_name |
| Chọn timeline | recovery_target_timeline |
| Kiểm tra byte range | pg_wal_lsn_diff() |

## 42. Checklist vận hành archive và continuity

1. wal_level được đặt ở replica hoặc logical theo yêu cầu.
2. archive_mode đang bật và thay đổi đã restart có hiệu lực.
3. archive_command hoặc archive_library được cấu hình đúng một cơ chế phù hợp.
4. Archive destination nằm ở failure domain riêng và có quota/dung lượng dự phòng.
5. OS identity PostgreSQL có quyền tối thiểu cần thiết.
6. Archive command trả success chỉ khi file đã hoàn chỉnh.
7. Command idempotent và xác minh file đích tồn tại có cùng nội dung.
8. Copy/upload dùng temp + publish hoặc cơ chế object completion an toàn.
9. Command có logging/monitoring và timeout/retry phù hợp.
10. archive_timeout cân bằng RPO với số lượng segment/object.
11. pg_stat_archiver được scrape và alert theo counter delta.
12. Số lượng/tuổi .ready được giám sát.
13. Archive destination free space, quota và object count được theo dõi.
14. Timeline history files được archive và retention.
15. Base backup giữ manifest/label/LSN/timeline metadata.
16. Mỗi backup có inventory WAL bắt buộc.
17. Continuity checker hiểu segment size và timeline ancestry.
18. Integrity kiểm tra bằng checksum/size/parse phù hợp.
19. Không coi checksum riêng lẻ là chứng minh continuity.
20. pg_verifybackup chạy cho base backup theo phiên bản hỗ trợ.
21. pg_waldump được dùng chẩn đoán các khoảng WAL cần thiết.
22. restore_command có thể lấy đúng file và trả exit code chính xác.
23. Nén/mã hóa được đảo ngược trước khi PostgreSQL đọc WAL.
24. Retention biết dependencies của mọi base backup còn giữ.
25. Object lifecycle không xóa WAL còn cần.
26. Archive không bị nhiều manager xung đột.
27. RPO/RTO được đo qua restore drill thực tế.
28. Restore drill chạy trên môi trường cô lập.
29. Kiểm tra dữ liệu ứng dụng sau recovery, không chỉ server startup.
30. Runbook xử lý gap, corruption, archiver failure và disk pressure được cập nhật.

## 43. Tổng kết

WAL archiving giữ các segment đã hoàn tất ra khỏi vòng đời ngắn của pg_wal để hỗ trợ PITR. Một cấu hình điển hình dùng wal_level=replica, archive_mode=on, một archive_command hoặc archive library đã kiểm thử và archive_timeout phù hợp. Archive command phải idempotent, chỉ trả thành công khi dữ liệu đã được lưu hoàn chỉnh và xử lý an toàn trường hợp file đích đã tồn tại.

Kiểm tra continuity cần bắt đầu từ một **base backup cụ thể**: xác định start LSN/timeline, target LSN/timeline, dựng danh sách segment cần thiết, giữ timeline history files, xác minh file tồn tại và có thể đọc, sau đó thử phục hồi. pg_stat_archiver cho biết tiến độ và lỗi gần nhất; archive_status cho biết file đang chờ/đã báo thành công; pg_verifybackup và pg_waldump hỗ trợ kiểm tra backup/WAL trong phạm vi của chúng.

Không có một truy vấn SQL duy nhất chứng minh archive hoàn chỉnh. Chỉ khi một base backup có thể được restore qua chuỗi WAL liên tục tới target, PostgreSQL khởi động đúng và dữ liệu ứng dụng vượt qua kiểm tra, quy trình PITR mới được chứng minh. Giám sát backlog, retention theo dependency, bảo vệ timeline history và diễn tập restore thường xuyên là những phần thiết yếu của vận hành.
