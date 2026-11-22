# Point-in-Time Recovery từ base backup và WAL trong PostgreSQL

Point-in-Time Recovery (PITR) cho phép PostgreSQL khôi phục một cluster về một thời điểm, một vị trí WAL hoặc một mốc giao dịch cụ thể sau khi đã tạo base backup. Đây là kỹ thuật quan trọng khi cần quay lại trạng thái trước một thao tác nhầm, lỗi ứng dụng, xóa dữ liệu ngoài ý muốn hoặc sự cố làm hỏng dữ liệu logic.

PITR kết hợp hai thành phần:

- **Base backup:** bản sao vật lý nhất quán của PostgreSQL cluster, tạo điểm bắt đầu cho recovery.
- **WAL archive:** chuỗi Write-Ahead Log liên tục sau điểm cần thiết của base backup, cho phép replay các thay đổi tới recovery target.

~~~text
             PostgreSQL đang hoạt động
                       |
             +---------+---------+
             |                   |
             v                   v
        Base backup           WAL archive
        (data files)       (segment liên tục)
             |                   |
             +---------+---------+
                       |
                       v
              Restore vào cluster
                       |
                       v
              recovery.signal
              restore_command
                       |
                       v
               Replay WAL records
                       |
                       v
                Recovery target
                (time / LSN / XID
                 / restore point)
                       |
                       v
              Pause hoặc promote
                       |
                       v
               Database được phục hồi
~~~

Một base backup đơn lẻ chỉ đưa database về trạng thái nhất quán tại thời điểm backup. WAL archive giúp tiến từ trạng thái đó tới thời điểm cần phục hồi. Nếu thiếu một segment trong khoảng WAL bắt buộc, sai timeline hoặc mất metadata backup, PostgreSQL có thể không hoàn tất recovery tới target.

Bài này thuộc chương **Khôi phục** của module *Database Engine Relational PostgreSQL*, tập trung vào recovery chain, cấu hình archive recovery, lựa chọn target, timeline, quy trình PITR, xác minh kết quả và vận hành restore drill.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích PITR và phân biệt với crash recovery, standby recovery và logical restore.
2. Mô tả mối quan hệ giữa base backup, WAL segment và recovery target.
3. Xác định WAL cần thiết để phục hồi một base backup cụ thể.
4. Giải thích vì sao WAL archive phải liên tục từ điểm backup yêu cầu tới target.
5. Khôi phục physical base backup vào một PostgreSQL data directory riêng.
6. Cấu hình restore_command để lấy WAL từ archive.
7. Phân biệt recovery.signal và standby.signal trong PostgreSQL 12 trở lên.
8. Nhận biết recovery.conf ở các phiên bản PostgreSQL cũ.
9. Chọn recovery target theo time, LSN, transaction ID hoặc named restore point.
10. Sử dụng recovery_target_inclusive, recovery_target_action và recovery_target_timeline.
11. Hiểu timeline history và phục hồi qua timeline switch.
12. Phân tích lỗi thiếu WAL, file hỏng, sai timezone, sai timeline và sai backup.
13. Kiểm tra base backup bằng pg_verifybackup và đọc WAL bằng pg_waldump.
14. Xác minh trạng thái database sau khi recovery hoàn tất.
15. Hiểu việc promote tạo timeline mới và ảnh hưởng tới archive tiếp theo.
16. Đánh giá RPO, RTO, retention và độ trễ archive.
17. Xây dựng restore drill và runbook PITR có thể lặp lại.

## 2. PITR giải quyết vấn đề gì?

PITR cho phép khôi phục dữ liệu về trạng thái trước một sự kiện. Ví dụ:

- Một migration chạy nhầm lệnh DROP TABLE lúc 10:35.
- Một batch job cập nhật sai hàng triệu records lúc 14:20.
- Ứng dụng ghi dữ liệu sai trong một khoảng thời gian.
- Một thao tác xóa nhầm được commit và replicate sang standby.
- Cần dựng một bản database tại thời điểm trước một thay đổi nghiệp vụ.

### 2.1. Ví dụ về mục tiêu recovery

Giả sử:

| Thời điểm | Sự kiện |
| --- | --- |
| 02:00 | Hoàn thành base backup |
| 09:00 | Ứng dụng hoạt động bình thường |
| 10:34 | Dữ liệu còn đúng |
| 10:35 | Migration xóa nhầm bảng |
| 10:40 | Sự cố được phát hiện |

Nếu WAL archive đầy đủ từ base backup tới sau 10:35, có thể restore base backup rồi replay WAL tới 10:34:59 hoặc một mốc an toàn trước thao tác lỗi.

### 2.2. PITR không hoàn tác một transaction riêng lẻ tại chỗ

PITR khôi phục một cluster tới một điểm trong lịch sử. Đây không phải lệnh undo transaction trên primary đang chạy. Thông thường cần một môi trường restore riêng, kiểm tra dữ liệu, sau đó quyết định cách đưa dữ liệu phục hồi trở lại dịch vụ.

### 2.3. PITR bảo vệ trước lỗi logic

Standby streaming thường replay cả thao tác hợp lệ về mặt WAL lẫn thao tác sai về mặt nghiệp vụ. PITR giúp quay lại trước khi thao tác sai được replay.

### 2.4. PITR không thay thế backup

WAL không chứa toàn bộ trạng thái database tại một thời điểm. Cần một base backup phù hợp làm điểm xuất phát.

### 2.5. PITR không thể đi ngược trước base backup

Recovery chỉ có thể replay từ trạng thái base backup về phía trước. Muốn khôi phục một thời điểm trước backup hiện có, phải có một base backup cũ hơn và WAL tương ứng.

## 3. Các loại recovery cần phân biệt

| Cơ chế | Mục tiêu | Nguồn dữ liệu chính |
| --- | --- | --- |
| Crash recovery | Đưa cluster về trạng thái nhất quán sau crash | WAL trong pg_wal |
| Archive recovery | Replay WAL lấy từ archive | Base backup + restore_command |
| Standby recovery | Theo kịp primary để phục vụ standby | Streaming WAL, archive hoặc cả hai |
| PITR | Dừng replay tại một target lịch sử | Base backup + WAL chain + target |
| Logical restore | Tạo lại objects/dữ liệu từ dump | pg_dump/pg_restore hoặc SQL |

### 3.1. Crash recovery

Sau crash, PostgreSQL tự động đọc WAL cần thiết trong data directory để redo các thay đổi đã ghi WAL. Không cần tạo recovery.signal cho crash recovery thông thường.

### 3.2. Archive recovery

Khi restore từ base backup và cần lấy WAL ngoài pg_wal, PostgreSQL sử dụng restore_command để lấy từng file.

### 3.3. Standby mode

Standby mode giữ server ở trạng thái recovery liên tục, thường đọc WAL từ primary qua streaming replication và có thể dùng archive làm nguồn bổ sung.

### 3.4. PITR

PITR đặt một recovery target. Khi PostgreSQL replay tới target, hành động tiếp theo phụ thuộc recovery_target_action.

### 3.5. Logical restore

Logical restore tái tạo schema/data qua SQL. Nó không dùng cùng cơ chế physical WAL replay để quay cluster về một LSN.

## 4. Kiến trúc recovery chain

Một recovery chain cần các thành phần:

1. Base backup còn nguyên vẹn.
2. Backup metadata, bao gồm backup_label và thông tin tablespace.
3. WAL segment đầu tiên mà base backup yêu cầu.
4. Tất cả WAL tiếp theo theo đúng thứ tự cho tới target.
5. Timeline history files nếu có nhánh timeline.
6. restore_command có thể truy xuất các file.
7. PostgreSQL version, extension binaries và môi trường tương thích.

~~~text
Base backup
  |
  | backup start LSN
  v
WAL segment A
  |
  v
WAL segment B
  |
  v
WAL segment C
  |
  +---- Timeline history / branch nếu có
  |
  v
WAL segment D
  |
  v
Recovery target
  |
  v
Recovery kết thúc tại điểm đã chọn
~~~

### 4.1. Base backup xác định điểm xuất phát

Backup metadata cho PostgreSQL biết vị trí bắt đầu và WAL cần thiết để đưa backup về trạng thái nhất quán.

### 4.2. WAL phải liên tục

PostgreSQL không thể bỏ qua một WAL segment bắt buộc ở giữa rồi tiếp tục từ segment mới hơn. Một segment thiếu trong required range có thể làm recovery dừng hoặc thất bại.

### 4.3. Archive có thể chứa nhiều cluster

Nếu dùng chung repository cho nhiều cluster, phải namespace theo cluster identity và tránh trộn WAL có cùng tên file nhưng thuộc các cluster khác nhau.

### 4.4. Recovery target phải nằm trong phạm vi có thể replay

Target cần ở sau điểm nhất quán của base backup và không vượt quá WAL có thể truy cập. Nếu target nằm ngoài archive hiện có, không thể khôi phục tới target đó.

### 4.5. Không chỉ dựa vào timestamp file

Tên file WAL không phải timestamp. Dùng LSN, timeline history và metadata backup để xác định chain.

## 5. Base backup cần chuẩn bị

Một ví dụ tạo physical base backup:

~~~bash
pg_basebackup \
  -h primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backup/base_2026_11_14 \
  -F plain \
  -X stream \
  -P \
  -v
~~~

### 5.1. Plain format

Plain format tạo cây thư mục tương tự data directory PostgreSQL. Đây là dạng thuận tiện để restore và chạy pg_verifybackup.

### 5.2. Tar format

Tar format đóng gói base data, WAL và tablespace thành các tar archives. Cần extract từng phần đúng vị trí trước khi khởi động server.

### 5.3. WAL stream

Tùy chọn -X stream lấy WAL cần thiết trong khi copy data files. Điều này giúp base backup có WAL để hoàn tất consistency ngay cả khi server tiếp tục ghi.

### 5.4. WAL fetch

-X fetch lấy WAL sau khi copy dữ liệu xong. Server phải giữ segment cần thiết đủ lâu cho tới lúc fetch hoàn tất.

### 5.5. WAL none

-X none không lấy WAL cùng lệnh. Chỉ dùng nếu một archive/retention workflow khác bảo đảm có đầy đủ WAL cần thiết cho backup.

### 5.6. WAL kèm backup và WAL archive

WAL stream kèm base backup giúp backup đó có thể phục hồi nhất quán. Muốn PITR tới thời điểm sau khi backup kết thúc, vẫn cần WAL liên tục sau đó.

### 5.7. Backup metadata

Giữ nguyên backup_label, tablespace_map, backup_manifest và mọi metadata do công cụ backup tạo. Không sửa thủ công các file này.

## 6. Kiểm tra base backup trước khi restore

### 6.1. Xác minh backup manifest

Với plain-format backup có manifest:

~~~bash
pg_verifybackup /backup/base_2026_11_14
~~~

Công cụ kiểm tra file backup theo manifest và thực hiện những kiểm tra WAL mà phiên bản hỗ trợ.

### 6.2. Giới hạn của pg_verifybackup

Verify pass không chứng minh archive WAL bên ngoài còn liên tục tới mọi recovery target trong tương lai. Nó cũng không kiểm tra toàn bộ DNS, secrets, extension packages hay cấu hình ứng dụng trên máy restore.

### 6.3. Kiểm tra backup metadata

~~~bash
ls -l /backup/base_2026_11_14/backup_label
ls -l /backup/base_2026_11_14/backup_manifest
~~~

Các file cụ thể phụ thuộc phiên bản và cách tạo backup. Không tự tạo file giả nếu một file không có.

### 6.4. Kiểm tra tablespaces

Đối chiếu tablespace_map, các symlink trong pg_tblspc và nơi lưu tablespace. Bản backup thiếu một tablespace có thể không khởi động được.

### 6.5. Kiểm tra version

Physical backup thường được restore bằng PostgreSQL cùng major version. Đảm bảo extension binaries, shared libraries và OS dependencies tương thích.

### 6.6. Lưu system identifier

Đối chiếu cluster identity của backup với WAL archive. Không ghép WAL từ cluster khác dù tên segment có vẻ phù hợp.

## 7. Xác định WAL cần thiết từ backup

Base backup có một điểm bắt đầu WAL. PostgreSQL dùng backup metadata để biết cần replay từ đâu.

### 7.1. Backup start LSN

Backup label chứa thông tin cần cho recovery, bao gồm checkpoint/start information theo định dạng phiên bản.

### 7.2. Backup stop

Khi backup kết thúc, PostgreSQL có thể yêu cầu WAL bổ sung để làm bản sao nhất quán. Giữ WAL segment range do backup protocol xác định.

### 7.3. WAL segment đầu tiên

Không chọn segment đầu tiên bằng cách nhìn ngày tạo backup hoặc timestamp tên file. Dựa trên LSN/backup metadata và hàm PostgreSQL map LSN sang filename.

### 7.4. pg_walfile_name

Trên primary có thể map LSN sang segment:

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;
~~~

### 7.5. pg_walfile_name_offset

~~~sql
SELECT *
FROM pg_walfile_name_offset(pg_current_wal_lsn());
~~~

Hàm trả tên segment và offset byte bên trong segment.

### 7.6. Segment size

~~~sql
SHOW wal_segment_size;
~~~

Kích thước phổ biến là 16 MiB nhưng có thể khác tùy cluster/build. Không hardcode segment size khi tự tạo continuity checker.

## 8. WAL archive phải liên tục

Một kho archive có hàng nghìn file vẫn có thể thiếu đúng một segment mà recovery cần.

### 8.1. Xác định khoảng cần giữ

Với mỗi backup:

- Lấy backup start/required WAL metadata.
- Xác định recovery target.
- Map start và target LSN sang WAL segment.
- Xây danh sách segment theo segment size và timeline ancestry.
- Kiểm tra từng file trong archive.

### 8.2. Không cần giữ toàn bộ WAL từ ngày đầu cluster

Retention có thể xóa WAL cũ hơn nếu mọi base backup còn giữ đều không còn phụ thuộc vào chúng và PITR window cam kết không cần chúng.

### 8.3. Một gap ở ngoài required range

Một file thiếu ngoài khoảng cần thiết của backup/target không nhất thiết làm chain đó thất bại.

### 8.4. Một gap ở giữa required range

Nếu PostgreSQL cần segment A, B, C và archive thiếu B, không thể replay từ A nhảy thẳng sang C.

### 8.5. Kiểm tra file

Với mỗi segment cần thiết, xác minh:

- Đúng tên theo timeline và WAL address.
- File tồn tại.
- Kích thước hợp lệ, thường bằng wal_segment_size.
- Checksum/byte integrity phù hợp nếu có manifest.
- File có thể đọc/parse.
- File đã được giải mã/giải nén về WAL raw nếu archive dùng transform.

### 8.6. Checksum không chứng minh continuity

Checksum đúng xác nhận nội dung một file khớp với checksum tin cậy. Nó không chứng minh danh sách không thiếu segment.

## 9. Timeline và timeline history

Timeline là nhánh lịch sử WAL. Khi recovery được promote hoặc một standby được promote, PostgreSQL có thể tạo timeline mới.

### 9.1. Timeline 1 và timeline 2

~~~text
Timeline 1:
  WAL A ---- WAL B ---- WAL C ---- WAL D
                              |
                              +-- điểm fork
                                     |
Timeline 2:                          +---- WAL E ---- WAL F
~~~

Timeline 2 bắt đầu từ một điểm trên timeline 1, sau đó có lịch sử WAL riêng.

### 9.2. History file

Khi timeline mới được tạo, PostgreSQL tạo file dạng:

~~~text
00000002.history
~~~

File history mô tả timeline cha, điểm switch và thông tin liên quan để recovery dựng nhánh đúng.

### 9.3. Giữ history files

WAL segment của timeline con có thể tồn tại nhưng nếu history file bị mất, PostgreSQL có thể không xác định được timeline ancestry cần thiết.

### 9.4. Recovery qua nhánh

Nếu target ở timeline 2, recovery cần WAL timeline 1 tới điểm fork và WAL timeline 2 sau điểm fork, cùng history files cần thiết.

### 9.5. recovery_target_timeline

Có thể chọn latest hoặc timeline ID cụ thể. Latest tiện khi muốn đi theo nhánh mới nhất; timeline cụ thể phù hợp khi cần phục hồi một nhánh đã biết.

### 9.6. Không sort file nhiều timeline để kiểm tra liên tục

Tên file cùng log/segment ở timeline khác nhau không thể thay thế lẫn nhau. Dựng chain theo history ancestry và target timeline.

## 10. restore_command

Trong archive recovery, PostgreSQL gọi restore_command để lấy file cần thiết từ archive.

Ví dụ với archive filesystem:

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
~~~

### 10.1. Placeholder %f

Tên file cần lấy từ archive, có thể là WAL segment hoặc timeline history file.

### 10.2. Placeholder %p

Đường dẫn đích mà PostgreSQL yêu cầu command ghi file vào.

### 10.3. Placeholder %%

Ký tự phần trăm literal trong command.

### 10.4. Exit code thành công

Command trả 0 chỉ khi file được lấy đầy đủ và đặt đúng vào path đích.

### 10.5. File không tồn tại

Nếu file không có trong archive, command trả non-zero. Không tạo file rỗng rồi trả 0.

### 10.6. Archive nén

Nếu archive lưu file gzip:

~~~conf
restore_command = 'gzip -dc /srv/pgarchive/%f.gz > "%p"'
~~~

Chỉ dùng khi archive tool thực sự lưu segment dưới dạng gzip với quy tắc đặt tên tương ứng. Command phải trả lỗi nếu giải nén thất bại.

### 10.7. Archive mã hóa

Nếu WAL được mã hóa, restore_command phải tải và giải mã bằng key hợp lệ trước khi PostgreSQL đọc file. Bảo đảm key không phụ thuộc duy nhất vào chính archive repository.

### 10.8. Quyền truy cập

restore_command chạy dưới quyền OS của tiến trình PostgreSQL trên máy restore. User này cần quyền đọc archive và ghi file đích.

### 10.9. Không dùng đường dẫn máy backup operator

Path phải truy cập được từ host/container đang chạy PostgreSQL restore, chẳng hạn volume đã mount hoặc client object storage.

## 11. recovery.signal và standby.signal

Từ PostgreSQL 12, recovery settings được đặt trong postgresql.conf hoặc file cấu hình được include; file recovery.conf cũ không còn được dùng.

### 11.1. recovery.signal

Tạo file recovery.signal trong PGDATA để yêu cầu server bắt đầu archive recovery.

~~~bash
touch /restore/pgdata/recovery.signal
~~~

### 11.2. standby.signal

standby.signal yêu cầu server khởi động ở standby mode, thường tiếp tục lấy WAL từ primary.

### 11.3. Khác biệt

| Signal file | Mục đích |
| --- | --- |
| recovery.signal | Archive recovery/PITR |
| standby.signal | Standby mode |

### 11.4. Không để nhầm signal file

Nếu muốn PITR độc lập tới một target, kiểm tra không còn standby.signal ngoài ý muốn. Nếu muốn dựng standby, dùng quy trình standby và primary_conninfo/slot phù hợp.

### 11.5. PostgreSQL 11 trở xuống

Các phiên bản cũ dùng recovery.conf cho recovery settings và standby_mode cho standby behavior. Dùng tài liệu đúng major version.

### 11.6. Không tạo recovery.conf trên PostgreSQL 12+

PostgreSQL 12 trở lên không sử dụng recovery.conf. Tạo file đó không thay thế recovery.signal và các tham số recovery trong cấu hình hiện tại.

## 12. Các recovery target

PITR có thể dừng theo một trong các loại target:

| Tham số | Ý nghĩa |
| --- | --- |
| recovery_target_time | Thời điểm theo timestamp |
| recovery_target_lsn | Vị trí WAL |
| recovery_target_name | Named restore point |
| recovery_target_xid | Transaction ID |

Chỉ chọn một target chính trong một lần recovery. Target phải có thể đạt được từ base backup và WAL chain hiện có.

### 12.1. Recovery theo thời gian

~~~conf
recovery_target_time = '2026-11-14 10:34:59+07'
~~~

Dùng timezone offset rõ ràng để tránh nhầm giữa local time và UTC.

### 12.2. Recovery theo LSN

~~~conf
recovery_target_lsn = '0/5A0000F0'
~~~

LSN phù hợp khi đã ghi lại vị trí WAL cụ thể từ ứng dụng, backup metadata hoặc restore point.

### 12.3. Recovery theo named restore point

~~~conf
recovery_target_name = 'before_customer_migration'
~~~

Target này cần được tạo trước bằng pg_create_restore_point và đã có trong WAL chain.

### 12.4. Recovery theo transaction ID

~~~conf
recovery_target_xid = '1234567'
~~~

Hữu ích khi đã xác định transaction gây lỗi. Cần hiểu transaction ID và thời điểm commit trong bối cảnh cluster.

### 12.5. Target không thể đạt

Nếu target nằm trước consistency point của base backup hoặc sau WAL cuối cùng có thể truy cập, recovery không thể đạt target như yêu cầu. Đọc log để biết PostgreSQL đã replay tới đâu và vì sao dừng.

## 13. recovery_target_time

Tham số này yêu cầu PostgreSQL dừng khi replay tới transaction commit timestamp tương ứng.

### 13.1. Dùng timezone rõ

~~~conf
recovery_target_time = '2026-11-14 10:34:59+07'
~~~

Không để thời gian không có timezone nếu môi trường backup/restore có timezone khác nhau.

### 13.2. Transaction boundary

PostgreSQL replay transaction theo WAL/commit semantics. Một transaction không bị cắt đôi để chỉ giữ một phần các thay đổi đã commit.

### 13.3. Target trước thao tác lỗi

Nếu lệnh sai commit lúc 10:35:00, chọn target trước commit đó, ví dụ 10:34:59+07, sau đó kiểm tra dữ liệu thực tế.

### 13.4. Không dùng thời điểm phát hiện sự cố

Thời điểm phát hiện có thể muộn hơn thời điểm dữ liệu bị hỏng. Cần tìm thời điểm transaction lỗi được commit hoặc khoảng thời gian an toàn.

### 13.5. Time precision

Chọn độ chính xác phù hợp với timestamp/commit record. Nếu cần chính xác hơn, dùng LSN hoặc named restore point đã ghi lại.

## 14. recovery_target_lsn

LSN xác định vị trí trong WAL.

### 14.1. LSN format

LSN thường hiển thị dạng hai phần hexadecimal, ví dụ 0/5A0000F0.

### 14.2. Lấy LSN hiện tại

Trên primary:

~~~sql
SELECT pg_current_wal_lsn();
~~~

### 14.3. Lấy filename từ LSN

~~~sql
SELECT pg_walfile_name('0/5A0000F0'::pg_lsn);
~~~

### 14.4. So sánh LSN

~~~sql
SELECT
    pg_wal_lsn_diff(
        '0/5A0000F0'::pg_lsn,
        '0/59000000'::pg_lsn
    ) AS bytes_between;
~~~

### 14.5. LSN không phải timestamp

Không đổi LSN thành ngày giờ bằng phép tính đơn giản. WAL generation rate thay đổi theo workload.

### 14.6. Ghi lại LSN cùng sự kiện

Nếu cần mốc phục hồi chính xác trước deployment, ghi LSN từ restore point hoặc quy trình release và lưu cùng change record.

## 15. Named restore point

Trước một thao tác quan trọng, có thể ghi mốc trong WAL:

~~~sql
SELECT pg_create_restore_point('before_customer_migration');
~~~

### 15.1. Kết quả

Hàm trả về LSN của restore point. Lưu LSN, tên, thời gian, người thực hiện và change/ticket liên quan.

### 15.2. Recovery theo tên

~~~conf
recovery_target_name = 'before_customer_migration'
recovery_target_action = 'pause'
~~~

### 15.3. Restore point không phải base backup

Restore point chỉ là marker trong WAL. Vẫn cần base backup và WAL chain liên tục từ backup tới marker.

### 15.4. Tên duy nhất

Đặt tên có ý nghĩa và tránh tái sử dụng tên dễ gây nhầm lẫn. Có thể thêm release ID hoặc ngày giờ vào tên.

### 15.5. Tạo restore point trên primary

Hàm này cần được gọi trên server đang ghi WAL theo workflow. Không giả định một query trên standby sẽ tạo marker trên primary.

## 16. recovery_target_xid

Có thể dừng recovery theo transaction ID:

~~~conf
recovery_target_xid = '1234567'
recovery_target_action = 'pause'
~~~

### 16.1. Xác định transaction

Transaction ID có thể lấy từ log, audit, extension hoặc thông tin ứng dụng tùy hệ thống. Không phải lúc nào cũng có sẵn mapping từ user action sang XID.

### 16.2. Transaction commit

Recovery target theo XID liên quan tới transaction record trong WAL. Đọc semantics inclusive/exclusive và kiểm tra kết quả sau recovery.

### 16.3. XID wraparound

Transaction IDs có vòng đời/wraparound. Ghi XID kèm thời điểm, cluster và bối cảnh; không coi một con số XID đơn lẻ là định danh vĩnh viễn.

### 16.4. Dùng time hoặc LSN nếu rõ hơn

Nếu XID không được ghi nhận chắc chắn, recovery_target_time hoặc LSN có thể dễ xác định và kiểm chứng hơn.

## 17. recovery_target_inclusive

Tham số này quyết định có bao gồm sự kiện target theo semantics recovery hay không.

~~~conf
recovery_target_inclusive = false
~~~

### 17.1. true

Mặc định thông thường là true: target event được bao gồm theo quy tắc của target type.

### 17.2. false

Dừng trước target event theo semantics của recovery target.

### 17.3. Không phải lệnh rollback một transaction

Inclusive không cắt một transaction đã commit thành một phần. PostgreSQL giữ tính nhất quán transaction khi replay.

### 17.4. Kiểm tra target thực tế

Đặc biệt với time target, hãy xác minh transaction gây lỗi đã bị loại khỏi kết quả và các transaction hợp lệ trước đó vẫn có mặt.

### 17.5. Version semantics

Đọc tài liệu đúng phiên bản PostgreSQL và loại target đang dùng. Không suy diễn inclusive giống hệt cho mọi dạng target nếu chưa kiểm tra.

## 18. recovery_target_action

Khi đạt target, PostgreSQL có thể thực hiện hành động:

| Giá trị | Hành vi |
| --- | --- |
| pause | Tạm dừng replay tại target |
| promote | Promote server sau khi đạt target |
| shutdown | Tắt server sau khi đạt target |

Ví dụ:

~~~conf
recovery_target_action = 'pause'
~~~

### 18.1. pause

Hữu ích khi muốn kiểm tra dữ liệu tại target trước khi promote. Server chưa trở thành primary writable cho đến khi recovery được kết thúc/promote theo cách phù hợp.

### 18.2. promote

Server tự promote khi target đạt được, kết thúc recovery và tạo nhánh timeline mới.

### 18.3. shutdown

Server shutdown khi target đạt. Có thể hữu ích trong workflow kiểm tra/automation cần dừng tại target.

### 18.4. Chọn action

Trong restore drill hoặc phục hồi lỗi logic, pause thường giúp kiểm tra trước. Khi đã quyết định dùng cluster được phục hồi làm primary, promote theo runbook.

### 18.5. Không nhầm pause với thành công ứng dụng

Pause chỉ cho biết recovery dừng tại target. Cần kiểm tra schema, dữ liệu và business invariants trước khi chuyển traffic.

## 19. recovery_target_timeline

Tham số chọn timeline mà recovery sẽ theo:

~~~conf
recovery_target_timeline = 'latest'
~~~

### 19.1. latest

Cho phép PostgreSQL chọn timeline mới nhất có thể xác định từ history files trong archive.

### 19.2. Timeline ID cụ thể

~~~conf
recovery_target_timeline = '2'
~~~

Chọn nhánh đã biết, tránh vô tình theo một timeline mới hơn không thuộc mục tiêu phục hồi.

### 19.3. Timeline history

Khi target timeline là nhánh con, PostgreSQL cần history files và WAL timeline cha tới điểm fork.

### 19.4. Latest không luôn là nhánh mong muốn

Một archive có thể chứa nhánh mới từ một lần failover khác. Khi cần phục hồi một incident trên lịch sử cũ, xác định timeline chính xác trước khi restore.

### 19.5. Không trộn nhiều cluster

Timeline ID không phải định danh cluster toàn cục. Kết hợp system identifier, backup metadata và timeline history.

## 20. PITR trên PostgreSQL 12 trở lên: cấu hình mẫu

Giả sử:

- Base backup plain đã được restore vào /restore/pgdata.
- WAL archive ở /srv/pgarchive.
- Cần phục hồi tới 10:34:59 giờ Việt Nam ngày 14-11-2026.

Thêm vào cấu hình server:

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
recovery_target_time = '2026-11-14 10:34:59+07'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
~~~

Tạo signal file:

~~~bash
touch /restore/pgdata/recovery.signal
~~~

Khởi động server restore:

~~~bash
pg_ctl -D /restore/pgdata start
~~~

### 20.1. Kiểm tra đúng data directory

Xác nhận PGDATA là bản restore riêng, không phải data directory đang phục vụ production.

### 20.2. Kiểm tra archive access

Chạy thử lệnh lấy một file test dưới cùng OS user mà PostgreSQL sử dụng. Đảm bảo restore_command có thể đọc file và ghi path đích.

### 20.3. Kiểm tra timezone

Target time có offset +07. Điều này tránh phụ thuộc timezone mặc định của host restore.

### 20.4. Đọc log

Theo dõi log để xác nhận PostgreSQL tìm được WAL, replay liên tục và đạt target.

### 20.5. Trạng thái pause

Khi đạt target, server dừng replay. Xác minh dữ liệu trước khi promote.

## 21. Quy trình PITR từng bước

### Bước 1. Xác định sự cố

Ghi thời điểm thao tác sai, loại transaction, đối tượng bị ảnh hưởng và thời điểm cuối cùng dữ liệu còn đúng. Dùng application logs, audit logs và deployment records để xác định target.

### Bước 2. Chọn base backup

Chọn một base backup còn hợp lệ, được verify và có điểm consistency trước target. Base backup gần target thường giảm WAL replay nhưng không phải lúc nào cũng có sẵn.

### Bước 3. Kiểm tra backup metadata

Ghi backup ID, server/system identifier, major version, start/stop LSN, timeline, tablespace paths và manifest.

### Bước 4. Xác định WAL range

Từ metadata backup và target, dựng danh sách WAL segments cần thiết. Bao gồm history files nếu có timeline switch.

### Bước 5. Kiểm tra archive continuity

Xác nhận mọi file bắt buộc tồn tại, có kích thước/checksum hợp lệ và đọc được. Nếu thiếu segment, tìm bản sao khác hoặc backup chain khác.

### Bước 6. Chuẩn bị môi trường restore

Tạo host/VM/container và volume riêng. Cài đúng PostgreSQL major version, extension binaries, locale và dependencies.

### Bước 7. Restore base backup

Với plain format, đặt file backup vào PGDATA rỗng. Với tar format, extract base, WAL và tablespaces vào đúng vị trí.

### Bước 8. Khôi phục cấu hình ngoài PGDATA

Chuẩn bị postgresql.conf, pg_hba.conf, SSL certificates, secrets, archive path và cấu hình extension cần thiết.

### Bước 9. Cấu hình recovery

Đặt restore_command, target time/LSN/name/XID, timeline và action. PostgreSQL 12+ tạo recovery.signal.

### Bước 10. Khởi động recovery

Start PostgreSQL và đọc log. Không mở traffic ứng dụng khi chưa xác nhận recovery đã đạt target và dữ liệu đúng.

### Bước 11. Xác minh

Kiểm tra database list, schema, row counts, business markers, constraints và các truy vấn đại diện.

### Bước 12. Promote khi đã quyết định

Nếu dùng bản phục hồi làm primary, kết thúc recovery/promote theo action đã chọn. Ghi nhận timeline mới và cấu hình lại archive/replication.

### Bước 13. Chuyển dịch vụ

Điều phối ứng dụng, connection strings, DNS/proxy và quyền ghi. Tránh để primary cũ và primary mới cùng nhận write traffic.

### Bước 14. Lưu bằng chứng

Ghi target, backup ID, timeline, WAL range, log, thời gian phục hồi, kết quả validation và quyết định vận hành.

## 22. Ví dụ sự cố: xóa nhầm bảng

Giả sử bảng orders bị xóa nhầm lúc 10:35:

~~~sql
DROP TABLE app.orders;
~~~

Lệnh đã commit và sự cố được phát hiện lúc 10:40.

### 22.1. Xác định target

Tìm transaction commit time trong audit/application logs. Chọn thời điểm ngay trước commit, ví dụ 10:34:59+07.

### 22.2. Restore vào cluster riêng

Không PITR trực tiếp primary đang chạy. Restore base backup vào một instance độc lập.

### 22.3. Replay tới trước DROP

~~~conf
recovery_target_time = '2026-11-14 10:34:59+07'
recovery_target_action = 'pause'
~~~

### 22.4. Kiểm tra bảng

~~~sql
SELECT to_regclass('app.orders');
SELECT count(*) FROM app.orders;
~~~

So sánh dữ liệu với business records và thời điểm sự cố.

### 22.5. Lấy dữ liệu cần thiết

Có thể export bảng orders từ cluster phục hồi rồi import vào primary hiện tại nếu chỉ cần khôi phục một object. Cần xử lý sequence, foreign keys, triggers, dependent objects và các thay đổi phát sinh sau target.

### 22.6. Khôi phục toàn cluster

Nếu quyết định dùng toàn bộ cluster ở target, promote instance phục hồi và chuyển ứng dụng sang đó theo quy trình failover. Các thay đổi sau target sẽ không còn trong cluster mới.

### 22.7. Phân biệt object recovery và cluster PITR

PITR phục hồi cluster. Nếu chỉ cần một bảng, có thể dùng cluster phục hồi làm nguồn export object để giảm ảnh hưởng tới các dữ liệu khác trên production.

## 23. Khôi phục một phần dữ liệu sau PITR

PITR luôn replay cả cluster tới target. Sau đó có thể trích xuất một phần dữ liệu từ instance phục hồi.

### 23.1. Export table

~~~bash
pg_dump -h restore-host -U app_reader \
  -d appdb -t app.orders \
  -Fc -f /tmp/orders_before_error.dump
~~~

### 23.2. Restore object

~~~bash
pg_restore -h current-primary -U restore_operator \
  -d appdb --clean --if-exists \
  /tmp/orders_before_error.dump
~~~

Đây là ví dụ minh họa; tùy chọn --clean có thể xóa object hiện tại, cần review dependency và thử trên môi trường phù hợp trước khi chạy.

### 23.3. Import vào staging trước

Với dữ liệu quan trọng, restore dump vào database/schema staging, so sánh và merge có kiểm soát thay vì ghi đè trực tiếp.

### 23.4. Sequences

Sequence state không phải lúc nào cũng được đồng bộ như kỳ vọng khi chỉ export một table. Kiểm tra sequence ownership, current value và dữ liệu sau import.

### 23.5. Foreign keys và dependent objects

Một table có thể phụ thuộc types, functions, triggers, sequences và foreign keys. Đảm bảo các object liên quan tồn tại và tương thích.

### 23.6. Data created after target

Khi copy bảng cũ trở lại primary hiện tại, xác định cách xử lý rows được tạo/sửa sau target. Có thể cần merge thay vì thay thế toàn bộ.

## 24. Recovery target và transaction semantics

PITR làm việc theo WAL và transaction commit semantics.

### 24.1. Không phục hồi transaction chưa commit

Transaction chưa commit tại target không được xem như transaction đã hoàn tất trong database phục hồi.

### 24.2. Không cắt transaction thành hai phần

PostgreSQL đảm bảo transaction consistency. Không thể giữ nửa đầu transaction đã commit và bỏ nửa sau theo một mốc tùy ý bên trong transaction.

### 24.3. Target time là thời điểm commit

Recovery target time gắn với commit timestamps của transaction trong WAL. Thời điểm một câu lệnh bắt đầu chạy hoặc thời điểm ứng dụng gửi request có thể khác thời điểm transaction commit.

### 24.4. Tìm thời điểm chính xác

Dùng audit log, application log, deployment timeline, transaction logs và restore point nếu có. Đừng chỉ dựa trên timestamp file WAL.

### 24.5. Inclusive

recovery_target_inclusive điều khiển có bao gồm target event theo semantics của target hay không. Kiểm tra dữ liệu thực tế sau recovery để xác nhận thao tác lỗi đã bị loại.

## 25. Recovery kết thúc và promote

Khi recovery target được đạt, PostgreSQL có thể pause, promote hoặc shutdown tùy cấu hình.

### 25.1. Promote

Nếu chọn promote, server kết thúc recovery và bắt đầu hoạt động như một primary mới.

### 25.2. pg_promote

Trong một số workflow, có thể promote bằng SQL:

~~~sql
SELECT pg_promote();
~~~

Chỉ gọi khi đã kiểm tra target và có quyết định rõ ràng đưa cluster này vào hoạt động writable.

### 25.3. Timeline mới

Promotion tạo timeline mới để các WAL mới không bị nhầm với lịch sử của timeline trước. History file được tạo để mô tả quan hệ nhánh.

### 25.4. Archive sau promote

Đảm bảo archive command hoạt động trên primary mới và lưu được WAL/timeline history của nhánh mới. Kiểm tra archive destination và tránh xung đột với primary cũ.

### 25.5. Không để hai primary cùng ghi

Trước khi chuyển traffic, fencing hoặc tắt khả năng ghi của primary cũ. Split-brain có thể tạo hai nhánh dữ liệu không thể tự hợp nhất.

### 25.6. Chuyển replication

Standbys cần được reconfigure/rebuild theo timeline mới và primary mới. Kiểm tra replication slots, connection info và WAL availability.

## 26. PITR trên PostgreSQL 11 trở xuống

PostgreSQL 11 và các phiên bản cũ hơn dùng recovery.conf để cấu hình archive recovery.

Ví dụ dạng cũ:

~~~conf
restore_command = 'cp /srv/pgarchive/%f "%p"'
recovery_target_time = '2026-11-14 10:34:59+07'
recovery_target_action = 'pause'
~~~

### 26.1. recovery.conf

File recovery.conf được đặt trong data directory và chứa các recovery parameters theo version cũ.

### 26.2. standby_mode

Các phiên bản cũ dùng standby_mode trong recovery.conf để cấu hình standby behavior.

### 26.3. PostgreSQL 12 thay đổi

Từ PostgreSQL 12, recovery.conf bị loại bỏ; recovery parameters được đặt trong cấu hình thông thường và dùng recovery.signal/standby.signal.

### 26.4. Không trộn cú pháp

Đọc tài liệu đúng major version. Một file recovery.conf từ cluster cũ không phải cấu hình PITR hợp lệ cho PostgreSQL 12+.

## 27. Kiểm tra tiến trình recovery

### 27.1. Server log

Log là nguồn quan trọng để biết PostgreSQL đang tìm WAL nào, replay đến đâu, target đã đạt hay recovery dừng vì thiếu file.

### 27.2. Recovery state

~~~sql
SELECT pg_is_in_recovery();
~~~

Trả true khi server còn ở recovery/standby state; sau khi promote và kết thúc recovery, kết quả thường là false.

### 27.3. Replay LSN

Trên standby/recovery:

~~~sql
SELECT pg_last_wal_replay_lsn();
~~~

Cho biết vị trí WAL đã replay gần nhất.

### 27.4. Receive LSN

~~~sql
SELECT pg_last_wal_receive_lsn();
~~~

Hữu ích trên standby nhận WAL qua streaming; không phải chỉ số thay thế cho archive completeness.

### 27.5. Replay timestamp

~~~sql
SELECT pg_last_xact_replay_timestamp();
~~~

Cho biết thời điểm transaction cuối cùng được replay theo thống kê. Nếu database không có transaction mới, timestamp có thể cũ dù standby/recovery không lỗi.

### 27.6. Pause state

Trên phiên bản hỗ trợ, có thể kiểm tra trạng thái pause bằng hàm recovery pause status. Dùng tài liệu phiên bản cụ thể và không nhầm replay paused với server đã promote.

## 28. pg_waldump để chẩn đoán WAL

pg_waldump đọc WAL records và có thể giúp xác định segment có parse được hay không.

~~~bash
pg_waldump \
  --path=/srv/pgarchive \
  --timeline=1 \
  --start=0/3000000 \
  --end=0/5000000
~~~

### 28.1. Chọn timeline

Chọn timeline phù hợp với chain đang kiểm tra.

### 28.2. Chọn LSN range

Giới hạn start/end để giảm lượng output và tập trung vào vùng nghi ngờ.

### 28.3. File hỏng

Parse error có thể gợi ý file bị cắt, hỏng, không đúng version hoặc thiếu segment liên quan. Xác minh nguồn trước khi kết luận.

### 28.4. Không chứng minh toàn bộ restore

pg_waldump không kiểm tra data files, tablespace mappings, extension libraries hoặc application behavior. Nó chỉ là một công cụ chẩn đoán WAL.

## 29. pg_verifybackup và giới hạn

~~~bash
pg_verifybackup /restore/base_backup
~~~

### 29.1. Kiểm tra base backup

Xác minh backup file khớp manifest và các điều kiện tool hỗ trợ.

### 29.2. Không verify WAL archive vô hạn

Không dùng kết quả pass để kết luận mọi WAL từ backup tới một thời điểm tương lai đều có mặt.

### 29.3. Không thay restore test

Backup verify pass vẫn có thể không start nếu config, tablespace, extension hoặc môi trường restore không phù hợp.

### 29.4. Tar format

pg_verifybackup được thiết kế cho plain-format backup; tar backup cần extract/kiểm tra theo quy trình phù hợp với phiên bản và công cụ.

## 30. PITR và retention

Retention cần biết mỗi base backup phụ thuộc vào khoảng WAL nào.

### 30.1. Backup còn giữ

Nếu một base backup vẫn được policy giữ lại, các WAL cần thiết để restore backup đó phải còn khả dụng.

### 30.2. PITR window

Nếu tổ chức cam kết phục hồi tới mọi thời điểm trong 14 ngày, phải giữ base backup và WAL đủ để phủ toàn bộ cửa sổ đó.

### 30.3. Không xóa theo tuổi file đơn giản

Xóa mọi WAL cũ hơn 7 ngày có thể làm mất khả năng phục hồi một base backup 10 ngày tuổi vẫn còn trong retention.

### 30.4. pg_archivecleanup

pg_archivecleanup có thể dọn WAL archive theo một boundary file trong một số workflow. Nó không tự hiểu mọi base backup, target time, timeline branch và policy compliance.

### 30.5. Backup manager

Công cụ như pgBackRest hoặc WAL-G có thể quản lý backup catalog, WAL archive và retention dependency. Chỉ nên có một owner rõ ràng cho lifecycle của repository.

### 30.6. Object lifecycle

Cloud lifecycle rules không được xóa segment mà backup manager còn cần. Đồng bộ policy giữa object storage và backup catalog.

## 31. RPO, RTO và thời gian recovery

### 31.1. RPO

Recovery Point Objective là lượng dữ liệu tối đa tổ chức chấp nhận mất. RPO của PITR phụ thuộc WAL archive lag, tính liên tục và khả năng đọc file.

### 31.2. RTO

Recovery Time Objective là thời gian mục tiêu đưa hệ thống trở lại. RTO phụ thuộc:

- Thời gian lấy/copy base backup.
- Tốc độ disk/network.
- Dung lượng WAL phải replay.
- Số lượng segment và latency archive retrieval.
- Startup và extension initialization.
- Thời gian kiểm tra dữ liệu/ứng dụng.

### 31.3. Base backup gần hơn

Base backup mới hơn thường giảm số WAL phải replay, có thể giảm RTO nhưng tăng backup storage và tải hệ thống.

### 31.4. Archive lag

Archive lag lớn làm target mới nhất có thể phục hồi lùi xa hơn. Monitoring chỉ nhìn last_archived_time cần kết hợp WAL activity và LSN.

### 31.5. Đo bằng restore drill

RTO không nên chỉ là ước lượng từ tốc độ đọc disk. Đo toàn bộ quy trình restore và application validation trên môi trường tương tự production.

## 32. Monitoring PITR readiness

Các chỉ số nên theo dõi:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Base backup age | Tuổi base backup gần nhất |
| Backup verify status | Kết quả xác minh backup |
| Backup duration/size | Thời gian và dung lượng backup |
| WAL archived count | Số lần archive thành công |
| WAL archive failures | Lỗi archive |
| Last archived WAL/time | Tiến độ archive gần nhất |
| Ready backlog | Segment đang chờ archive |
| Archive storage capacity | Dung lượng/quota |
| WAL continuity status | Gap trong required ranges |
| Timeline history inventory | History files còn đủ |
| Restore drill age | Lần thử restore gần nhất |
| Measured RTO | Thời gian phục hồi thực tế |

### 32.1. pg_stat_archiver

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

### 32.2. Archive status

Đếm/đo tuổi file .ready trong pg_wal/archive_status để phát hiện backlog. Không chỉnh sửa các marker này thủ công.

### 32.3. Base backup inventory

Lưu catalog backup với backup ID, timestamp, start/stop LSN, timeline, version, manifest và WAL dependencies.

### 32.4. Continuity checker

Kiểm tra từng backup còn giữ tới các target window mà policy cam kết. Không chỉ kiểm tra segment mới nhất.

### 32.5. Restore drill alert

Nếu quá lâu không có restore drill thành công, cảnh báo ngay cả khi backup jobs vẫn báo success.

## 33. Những nguyên nhân PITR thất bại

### Lỗi 1. Không có base backup phù hợp

WAL archive không thể thay thế data files. Chọn một base backup còn hợp lệ và có consistency point trước target.

### Lỗi 2. Thiếu WAL segment

Một segment bắt buộc bị retention xóa hoặc archive command thất bại. Tìm bản sao khác hoặc base backup khác có required range phù hợp.

### Lỗi 3. Sai timeline

Segment cùng log/segment number nhưng khác timeline không thể dùng thay nhau. Kiểm tra history files và target timeline.

### Lỗi 4. Thiếu history file

Recovery không dựng được ancestry của timeline con. Khôi phục history file từ archive/backup repository.

### Lỗi 5. Sai system identifier

Backup và WAL không thuộc cùng cluster. Kiểm tra provenance và namespace repository.

### Lỗi 6. restore_command sai

Command dùng sai path, sai placeholders, không có quyền hoặc trả exit code sai.

### Lỗi 7. restore_command báo success với file rỗng

PostgreSQL cố parse file không hợp lệ. Chỉ trả 0 sau khi tải file đúng và đầy đủ.

### Lỗi 8. WAL bị nén hoặc mã hóa

Command không giải nén/giải mã trước khi trả file cho PostgreSQL.

### Lỗi 9. Sai timezone target

Recovery dừng ở thời điểm khác mong đợi. Dùng offset rõ và xác minh transaction commit time.

### Lỗi 10. Target trước backup consistency point

Không thể replay ngược. Cần base backup cũ hơn.

### Lỗi 11. Target sau WAL cuối

Archive không có đủ WAL tới target. Khôi phục file còn thiếu hoặc chọn target sớm hơn.

### Lỗi 12. Major version mismatch

Physical backup không phải định dạng nâng cấp trực tiếp qua major versions. Dùng cùng major version để restore hoặc quy trình upgrade phù hợp.

### Lỗi 13. Tablespace path sai

Relation files không tìm thấy. Restore/mapping tablespaces trước khi start.

### Lỗi 14. Extension library thiếu

Catalog objects tồn tại nhưng server không load được shared library cần thiết. Cài đúng package/version.

### Lỗi 15. Config ngoài PGDATA bị thiếu

Server không đọc được SSL, hba, ident hoặc include files. Khôi phục cấu hình/secret từ backup quản trị.

### Lỗi 16. Disk không đủ

Restore/extract/WAL replay cần dung lượng lớn. Kiểm tra headroom trước khi bắt đầu.

### Lỗi 17. Backup bị sửa sau verify

File đã verify nhưng bị thay đổi khi copy/lưu trữ. Verify lại sau transfer và dùng immutable/checksum.

### Lỗi 18. Chỉ kiểm tra pg_stat_archiver

Counter thành công không chứng minh mọi archive object vẫn tồn tại. Cần inventory và continuity check.

### Lỗi 19. Promote quá sớm

Chuyển cluster thành primary trước khi xác nhận target/data có thể khiến việc quay lại recovery phức tạp hơn.

### Lỗi 20. Split-brain

Primary cũ vẫn nhận writes sau khi primary phục hồi được promote. Dùng fencing và điều phối traffic để chỉ có một writer.

## 34. Runbook khi cần PITR khẩn cấp

1. Tạm dừng hoặc cô lập nguồn ghi sai nếu điều đó không làm mất thêm bằng chứng.
2. Ghi lại thời điểm/transaction gây lỗi và thời điểm cuối cùng dữ liệu đúng.
3. Xác định cluster identity, PostgreSQL version và timeline hiện tại.
4. Chọn base backup còn hợp lệ và có consistency point trước target.
5. Kiểm tra manifest, tablespaces và backup metadata.
6. Xác định WAL range bắt buộc từ backup tới target.
7. Kiểm tra tất cả WAL segments và timeline history files.
8. Chuẩn bị máy/volume restore độc lập.
9. Restore base backup và cấu hình tablespaces.
10. Khôi phục external config, secrets và extension packages.
11. Cấu hình restore_command và recovery target.
12. Tạo recovery.signal trên PostgreSQL 12+.
13. Start server và theo dõi log.
14. Xác nhận recovery đạt đúng target.
15. Kiểm tra schema, dữ liệu và business invariants.
16. Quyết định export object hay promote toàn cluster.
17. Nếu promote, fencing primary cũ và tạo timeline/replication plan mới.
18. Kiểm tra WAL archiving trên primary mới.
19. Chuyển traffic có kiểm soát.
20. Ghi kết quả, RTO, dữ liệu mất có chủ đích và bài học sau sự cố.

## 35. Restore drill định kỳ

Restore drill là bài diễn tập thực tế để chứng minh backup/PITR có thể hoạt động.

### 35.1. Chọn backup

Chọn một base backup trong retention, không chỉ backup mới nhất.

### 35.2. Chọn target

Chọn một mốc thời gian/LSN có WAL archive sẵn và một restore point nếu hệ thống có tạo.

### 35.3. Kiểm tra trước

Verify base backup, inventory WAL range, history files, checksum và extension/config dependencies.

### 35.4. Restore độc lập

Khởi tạo môi trường cô lập, restore data files và cấu hình restore_command/recovery target.

### 35.5. Replay

Theo dõi log, đo tốc độ replay và xác nhận target reached.

### 35.6. Application validation

Chạy truy vấn kiểm tra, smoke tests và business invariants.

### 35.7. Đo thời gian

Ghi thời gian download, extract, startup, replay, validation và tổng RTO.

### 35.8. Lưu bằng chứng

Lưu backup ID, target, timeline, WAL range, tool versions, log và kết quả.

### 35.9. Thử failure cases

Trong lab, mô phỏng thiếu segment, checksum mismatch, history file missing và restore_command lỗi để kiểm tra alert/runbook.

### 35.10. Cập nhật quy trình

Sửa runbook, retention và capacity dựa trên kết quả drill.

## 36. PITR và bảo mật

### 36.1. WAL có thể chứa dữ liệu nhạy cảm

WAL phản ánh thay đổi dữ liệu. Bảo vệ archive như dữ liệu production.

### 36.2. Encryption at rest và in transit

Mã hóa archive storage và truyền tải. Quản lý key riêng, có backup/rotation và quyền truy cập rõ.

### 36.3. Immutable backups

Object lock/versioning hoặc repository bất biến giúp chống xóa nhầm/ransomware, nhưng phải thử restore với policy lock thực tế.

### 36.4. Least privilege

Archive writer chỉ cần quyền ghi vào prefix phù hợp; restore host chỉ cần quyền đọc. Tránh dùng credential admin chung.

### 36.5. Audit

Ghi ai tạo backup, ai thay đổi retention, ai xóa object và ai thực hiện restore.

### 36.6. Tách failure domain

Base backup và WAL archive cần được bảo vệ khỏi cùng một lỗi disk/host/region. Có ít nhất một bản sao ở miền lỗi độc lập theo policy.

## 37. Những hiểu lầm thường gặp

### Lỗi 1. Có base backup là đủ PITR

Base backup chỉ là điểm xuất phát. Cần WAL liên tục tới target.

### Lỗi 2. Có nhiều WAL file là archive đầy đủ

Có thể thiếu một segment ở giữa. Phải kiểm tra required range.

### Lỗi 3. WAL stream trong pg_basebackup thay archive mãi mãi

Stream kèm backup chỉ bảo đảm WAL cần cho backup đó, không tạo lịch sử WAL liên tục vô hạn sau backup.

### Lỗi 4. Standby khỏe đồng nghĩa PITR được bảo vệ

Standby có thể replay cả thao tác xóa nhầm. Cần backup và WAL history để quay lại trước lỗi.

### Lỗi 5. WAL filename chứa timestamp

Tên segment mã hóa timeline/log/segment IDs, không phải thời gian tạo.

### Lỗi 6. Segment cùng số ở timeline khác giống nhau

Timeline khác có lịch sử WAL khác. Không dùng file thay thế chỉ dựa vào phần log/segment.

### Lỗi 7. Checksum pass chứng minh continuity

Checksum xác nhận file integrity, không phát hiện một segment bị thiếu nếu không có expected inventory.

### Lỗi 8. pg_verifybackup kiểm tra toàn bộ archive

Công cụ kiểm tra backup trong phạm vi hỗ trợ; không chứng minh WAL archive tương lai đầy đủ.

### Lỗi 9. recovery.signal giống standby.signal

recovery.signal yêu cầu archive recovery; standby.signal yêu cầu standby mode.

### Lỗi 10. recovery.conf dùng được trên PostgreSQL 12+

Từ PostgreSQL 12, recovery.conf đã bị loại bỏ.

### Lỗi 11. Target time là thời điểm câu lệnh bắt đầu

Recovery target time dựa trên commit timestamps. Transaction start và commit có thể khác nhau.

### Lỗi 12. PITR có thể dừng giữa transaction

PostgreSQL giữ transaction consistency, không phục hồi một phần transaction đã commit.

### Lỗi 13. Target time không cần timezone

Timezone host có thể làm target lệch. Ghi offset rõ ràng.

### Lỗi 14. Có thể restore trước base backup

WAL chỉ replay tiến về phía trước. Cần base backup cũ hơn để phục hồi về thời điểm trước.

### Lỗi 15. promote không tạo timeline mới

Promotion tạo nhánh timeline mới để phân biệt WAL tiếp theo.

### Lỗi 16. Có thể để primary cũ và primary mới cùng ghi

Điều đó tạo split-brain. Fencing và chuyển traffic là bước bắt buộc.

### Lỗi 17. pg_stat_archiver archived_count là số file còn trong archive

Đây là counter thành công từ lần reset stats, không phải inventory hiện tại.

### Lỗi 18. Retention xóa WAL theo ngày là an toàn

WAL có thể còn là dependency của base backup cũ.

### Lỗi 19. Restore server start được nghĩa là dữ liệu đúng

Cần kiểm tra business invariants, schema và dữ liệu tại target.

### Lỗi 20. PITR là cách tốt nhất cho một bảng duy nhất

PITR phục hồi toàn cluster. Có thể dùng instance PITR làm nguồn export một object.

## 38. Bài tập thực hành

Các bài tập sử dụng PostgreSQL lab và một archive repository riêng. Không chạy restore ghi đè lên production.

### Bài 1. PITR

PITR là gì và giải quyết vấn đề nào?

### Bài 2. Hai thành phần

Hai thành phần tối thiểu của recovery chain là gì?

### Bài 3. Base backup

Vì sao không thể dùng WAL archive thay thế base backup?

### Bài 4. WAL continuity

Điều gì xảy ra nếu thiếu một segment bắt buộc ở giữa chain?

### Bài 5. Crash recovery

Crash recovery khác PITR thế nào?

### Bài 6. Logical restore

Nêu một trường hợp nên dùng pg_dump thay vì PITR.

### Bài 7. Backup metadata

Kể tên ba file/metadata cần giữ cùng base backup.

### Bài 8. pg_verifybackup

Công cụ này kiểm tra điều gì?

### Bài 9. WAL segment size

Viết SQL lấy WAL segment size.

### Bài 10. LSN filename

Viết SQL map current WAL LSN sang filename.

### Bài 11. restore_command

Ý nghĩa của %f và %p là gì?

### Bài 12. Exit code

restore_command nên trả non-zero khi nào?

### Bài 13. recovery.signal

File này có tác dụng gì trên PostgreSQL 12+?

### Bài 14. standby.signal

Khác recovery.signal ở điểm nào?

### Bài 15. recovery.conf

PostgreSQL major version nào còn dùng recovery.conf?

### Bài 16. recovery_target_time

Viết ví dụ target time có timezone offset +07.

### Bài 17. recovery_target_lsn

LSN phù hợp khi nào?

### Bài 18. Restore point

Viết SQL tạo named restore point.

### Bài 19. recovery_target_xid

Target theo XID có ý nghĩa gì?

### Bài 20. Inclusive

recovery_target_inclusive điều khiển điều gì?

### Bài 21. Action

Nêu ba giá trị recovery_target_action.

### Bài 22. Timeline

Vì sao cần timeline history file?

### Bài 23. Timeline target

Khi nào nên đặt recovery_target_timeline thành ID cụ thể?

### Bài 24. PITR trước sự cố

Một thao tác sai commit lúc 10:35. Nên chọn target time theo nguyên tắc nào?

### Bài 25. Target trước backup

Có thể PITR về trước consistency point của base backup không?

### Bài 26. Target sau WAL cuối

Điều kiện nào khiến target không thể đạt?

### Bài 27. Promotion

Điều gì xảy ra với timeline sau promote?

### Bài 28. Split-brain

Vì sao phải fencing primary cũ trước khi chuyển traffic?

### Bài 29. pg_waldump

Công cụ này giúp chẩn đoán điều gì?

### Bài 30. Archive status

pg_stat_archiver có thể cho biết những counter/filename nào?

### Bài 31. Retention

Vì sao không xóa WAL chỉ dựa trên tuổi file?

### Bài 32. RPO

Archive lag ảnh hưởng RPO thế nào?

### Bài 33. RTO

Nêu bốn yếu tố ảnh hưởng RTO.

### Bài 34. Partial recovery

Nếu chỉ cần một bảng, có thể làm gì sau khi PITR một cluster riêng?

### Bài 35. Tablespaces

Vì sao phải kiểm tra tablespace mapping trước khi start restore?

### Bài 36. Version

Có thể restore physical backup PostgreSQL 15 trực tiếp bằng PostgreSQL 16 không?

### Bài 37. Restore drill

Nêu ít nhất năm bước của một restore drill.

### Bài 38. Integrity

Checksum file có chứng minh WAL continuity không?

### Bài 39. Recovery validation

Nêu bốn loại kiểm tra sau khi target đạt.

### Bài 40. Runbook

Đề xuất quy trình PITR từ lúc phát hiện lỗi tới khi chuyển dịch vụ.

## 39. Lời giải tham khảo

### Bài 1–5. Khái niệm

PITR khôi phục cluster tới một thời điểm/LSN/transaction target bằng base backup và WAL. Base backup chứa data files; WAL chỉ chứa lịch sử thay đổi, không đủ dựng database từ đầu. Thiếu segment bắt buộc làm recovery không thể replay qua gap. Crash recovery xử lý crash của cluster hiện tại; PITR dựng lại từ backup và dừng tại target lịch sử.

### Bài 6–8. Backup

pg_dump phù hợp khi cần backup một table/schema hoặc di chuyển logical objects. Metadata cần giữ gồm backup_label, backup_manifest và tablespace_map khi được tạo. pg_verifybackup xác minh file backup theo manifest và các kiểm tra WAL mà phiên bản hỗ trợ; nó không chứng minh archive chain tới mọi target.

### Bài 9–12. WAL và restore_command

~~~sql
SHOW wal_segment_size;
~~~

~~~sql
SELECT pg_walfile_name(pg_current_wal_lsn());
~~~

%f là tên file archive cần lấy; %p là path đích. Command trả non-zero khi file không tồn tại hoặc không lấy/giải mã/giải nén được file hợp lệ.

### Bài 13–15. Signal và version

recovery.signal yêu cầu archive recovery; standby.signal yêu cầu standby mode. PostgreSQL 11 trở xuống dùng recovery.conf; PostgreSQL 12+ dùng cấu hình thường và signal files.

### Bài 16–20. Target

~~~conf
recovery_target_time = '2026-11-14 10:34:59+07'
~~~

LSN phù hợp khi cần mốc WAL cụ thể. Named restore point:

~~~sql
SELECT pg_create_restore_point('before_migration');
~~~

XID target dừng theo transaction ID. recovery_target_inclusive quyết định target event được bao gồm hay không theo semantics của target.

### Bài 21–23. Action và timeline

Action gồm pause, promote, shutdown. Timeline history file mô tả quan hệ nhánh và switchpoint. Chọn timeline ID cụ thể khi cần phục hồi đúng một nhánh lịch sử, không theo latest.

### Bài 24–26. Chọn target

Chọn thời điểm ngay trước transaction lỗi commit, dùng timezone rõ và xác minh sau recovery. Không thể PITR trước consistency point của base backup. Target không đạt được nếu WAL cần thiết sau backup bị thiếu hoặc target vượt WAL cuối cùng có thể truy cập.

### Bài 27–28. Promote

Promote kết thúc recovery và tạo timeline mới. Fencing primary cũ tránh hai server cùng nhận writes và tạo split-brain.

### Bài 29–30. Công cụ

pg_waldump đọc/parse WAL records. pg_stat_archiver cung cấp archived_count, failed_count, last_archived_wal/time và last_failed_wal/time.

### Bài 31–33. Retention và objectives

WAL cũ có thể còn là dependency của base backup đang giữ. Archive lag lớn làm tăng lượng thay đổi không thể phục hồi gần hiện tại, ảnh hưởng RPO. RTO chịu ảnh hưởng bởi backup size, network/disk throughput, WAL replay volume, tablespace extraction và application validation.

### Bài 34–36. Khôi phục một phần và version

Restore cluster riêng tới target, sau đó pg_dump table cần thiết và import vào staging/production có kiểm soát. Tablespace path sai làm server không tìm thấy relation files. Physical backup không restore trực tiếp qua major version; dùng cùng major hoặc quy trình upgrade.

### Bài 37–39. Drill và validation

Restore drill gồm chọn backup, verify, kiểm tra WAL range, restore độc lập, replay tới target, kiểm tra server và business data, ghi RTO. Checksum chỉ xác nhận integrity file, không chứng minh không có gap. Sau target, kiểm tra schema, row counts/business markers, constraints và truy vấn ứng dụng.

### Bài 40. Runbook

Xác định sự cố/target; chọn backup; dựng WAL/timeline range; verify file; restore vào host riêng; cấu hình restore_command và recovery.signal; replay; xác nhận target; validate dữ liệu; quyết định export object hay promote; fencing primary cũ; cấu hình archive/replication mới; chuyển traffic và lưu report.

## 40. Bảng tra cứu nhanh

| Nhu cầu | Công cụ/cấu hình |
| --- | --- |
| Tạo physical base backup | pg_basebackup |
| Kiểm tra backup manifest | pg_verifybackup |
| Lấy WAL từ archive | restore_command |
| Bắt đầu archive recovery | recovery.signal |
| Bắt đầu standby mode | standby.signal |
| Recovery theo thời gian | recovery_target_time |
| Recovery theo LSN | recovery_target_lsn |
| Recovery theo restore point | recovery_target_name |
| Recovery theo transaction | recovery_target_xid |
| Bao gồm/loại target event | recovery_target_inclusive |
| Chọn timeline | recovery_target_timeline |
| Hành động khi đạt target | recovery_target_action |
| Tạo restore point | pg_create_restore_point() |
| Lấy current LSN | pg_current_wal_lsn() |
| Map LSN sang WAL file | pg_walfile_name() |
| Map LSN và offset | pg_walfile_name_offset() |
| Tính chênh lệch LSN | pg_wal_lsn_diff() |
| Kiểm tra đang recovery | pg_is_in_recovery() |
| Replay LSN | pg_last_wal_replay_lsn() |
| Receive LSN | pg_last_wal_receive_lsn() |
| Kiểm tra archive stats | pg_stat_archiver |
| Đọc WAL records | pg_waldump |
| Kiểm tra segment size | SHOW wal_segment_size |
| Promote server | pg_promote() |

## 41. Checklist sẵn sàng PITR

1. Có base backup hợp lệ, còn trong retention.
2. Backup có metadata/manifest và system identifier.
3. Base backup thuộc PostgreSQL major version tương thích với restore server.
4. Có backup_label và tablespace metadata cần thiết.
5. Tất cả tablespaces được backup và có mapping đúng.
6. Extension binaries và OS dependencies có thể cài trên restore host.
7. Có WAL segment đầu tiên mà base backup yêu cầu.
8. Có toàn bộ WAL liên tục tới recovery target.
9. Có timeline history files cho mọi nhánh cần đi qua.
10. WAL thuộc đúng cluster identity.
11. Archive object có checksum/size phù hợp.
12. File WAL có thể đọc/parse và giải mã/giải nén.
13. restore_command hoạt động dưới OS identity của PostgreSQL.
14. restore_command trả exit code đúng khi file có/không tồn tại.
15. recovery.signal được tạo cho PostgreSQL 12+ archive recovery.
16. Không để standby.signal ngoài ý muốn trong PITR độc lập.
17. Recovery target có timezone rõ nếu dùng time.
18. Target nằm sau backup consistency point.
19. Target nằm trong WAL range có thể truy cập.
20. Timeline được chọn đúng với nhánh cần phục hồi.
21. recovery_target_action phù hợp với bước validation.
22. Restore thực hiện trên host/volume riêng.
23. Disk đủ cho data, tablespaces và WAL replay.
24. External config, SSL, secrets và extensions đã chuẩn bị.
25. Server log được theo dõi trong recovery.
26. Sau target, kiểm tra schema và dữ liệu nghiệp vụ.
27. Chỉ promote khi đã quyết định dùng cluster phục hồi làm primary.
28. Fencing primary cũ trước khi chuyển traffic.
29. Archive WAL và replication được cấu hình cho timeline mới.
30. Restore drill định kỳ và đo RPO/RTO thực tế.

## 42. Tổng kết

PITR khôi phục PostgreSQL bằng cách nạp một **base backup** rồi replay chuỗi **WAL liên tục** tới một recovery target. Base backup cung cấp data files; WAL cung cấp lịch sử thay đổi; timeline history giúp chọn đúng nhánh sau promotion/failover. Thiếu base backup, WAL segment bắt buộc hoặc history file đều có thể khiến recovery không đạt target.

Trên PostgreSQL 12 trở lên, cấu hình archive recovery bằng restore_command và các recovery parameters trong cấu hình server, sau đó tạo recovery.signal. Chọn target theo time, LSN, named restore point hoặc XID; cân nhắc inclusive, action và timeline. Với PostgreSQL 11 trở xuống, dùng recovery.conf theo tài liệu phiên bản đó.

Khi target đạt, kiểm tra dữ liệu và business invariants trước khi promote. Promotion tạo timeline mới; cần fencing primary cũ và cấu hình lại archive/replication để tránh split-brain. Nếu chỉ cần một bảng, có thể dùng instance PITR làm nguồn export thay vì thay toàn bộ cluster.

Một quy trình PITR chỉ đáng tin cậy khi base backup được verify, WAL dependencies được kiểm tra theo từng backup, restore_command hoạt động, timeline chain đầy đủ và restore drill end-to-end thành công. Giám sát archive lag, giữ retention theo dependency, đo RPO/RTO thực tế và diễn tập thường xuyên giúp biến backup thành khả năng phục hồi có thể chứng minh.
