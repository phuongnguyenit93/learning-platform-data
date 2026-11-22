# Quản lý redo log group, member và log switch trong Oracle Database

Online redo log ghi lại các thay đổi được thực hiện đối với database. Khi user transaction thay đổi dữ liệu, Oracle tạo redo records mô tả những thay đổi cần thiết để phục hồi. LGWR (Log Writer) ghi redo từ redo log buffer trong SGA xuống các online redo log files. Nhờ redo, Oracle có thể phục hồi các thay đổi đã commit sau instance failure và phối hợp với cơ chế media recovery.

Online redo log được tổ chức thành **redo log groups**. Mỗi group có một hoặc nhiều **members**. Các member trong cùng group là những bản sao multiplexed của cùng một luồng redo. Khi một group đang được ghi, LGWR ghi cùng redo vào các member của group đó.

Một **log switch** xảy ra khi Oracle chuyển việc ghi redo từ group hiện tại sang group tiếp theo. Group vừa rời khỏi trạng thái CURRENT có thể vẫn ACTIVE vì còn cần cho instance recovery, hoặc trở thành INACTIVE khi checkpoint đã tiến đủ xa. Trong ARCHIVELOG mode, group còn phải được archive trước khi có thể được tái sử dụng.

Quản lý redo log vì vậy gồm bốn việc liên quan:

- Duy trì đủ số lượng group cho từng redo thread.
- Multiplex members trên các vị trí lưu trữ độc lập để giảm rủi ro hỏng một file.
- Theo dõi trạng thái CURRENT/ACTIVE/INACTIVE và archive/checkpoint.
- Điều chỉnh kích thước, số group và tần suất log switch theo redo generation rate của workload.

Tài liệu này hướng dẫn cách kiểm tra cấu hình, thêm/bớt group và member, thực hiện log switch, chẩn đoán các wait event liên quan và lưu ý riêng cho ARCHIVELOG, RAC và Data Guard.

## 1. Online redo log trong kiến trúc Oracle

### 1.1 Redo log buffer và LGWR

Khi transaction thay đổi block dữ liệu, Oracle tạo redo entries và đặt chúng vào redo log buffer trong SGA. LGWR ghi redo xuống online redo log files theo cơ chế tuần tự.

LGWR có thể được kích hoạt bởi nhiều điều kiện, ví dụ:

- User session commit.
- Redo log buffer cần được giải phóng.
- Một khoảng thời gian hoặc lượng redo nhất định đã trôi qua/phát sinh.
- DBWR cần ghi các dirty buffers theo một số điều kiện và redo tương ứng phải được ghi trước (write-ahead logging).
- Log switch hoặc các yêu cầu quản trị liên quan.

Redo được ghi xuống online redo log trước khi các data blocks tương ứng bắt buộc phải được ghi xuống datafiles. Đây là nguyên tắc write-ahead logging: để phục hồi một data block, Oracle phải có redo cần thiết được lưu bền vững trước.

### 1.2 Online redo log files

Online redo log files là các file vật lý được database sử dụng luân phiên. Một database cần ít nhất hai redo log groups cho mỗi redo thread để có thể tiếp tục ghi khi một group đang được xử lý/chuẩn bị tái sử dụng.

Trong một thời điểm, mỗi thread có một group ở trạng thái CURRENT. Khi group đó đầy, Oracle chuyển sang group khác. Sau khi group cũ không còn cần cho instance recovery và đã đáp ứng điều kiện archive (nếu ARCHIVELOG), nó có thể được dùng lại ở vòng tiếp theo.

### 1.3 Redo log group và member

Ví dụ một database có hai group, mỗi group có hai members:

~~~text
Redo thread 1

       +-------------------------------+
       | Group 1  (CURRENT)             |
       |                               |
LGWR --+--> redo01a.log                |
       +--> redo01b.log                |
       +-------------------------------+

       +-------------------------------+
       | Group 2  (INACTIVE)            |
       |                               |
       +--> redo02a.log                |
       +--> redo02b.log                |
       +-------------------------------+
~~~

Trong ví dụ, redo01a.log và redo01b.log là hai members của cùng group 1. Chúng chứa cùng một nội dung redo và không phải hai log stream khác nhau.

| Khái niệm | Ý nghĩa |
|---|---|
| Redo log group | Đơn vị được Oracle chọn làm group CURRENT để ghi redo |
| Redo log member | Một file thuộc group; các members trong group là bản sao multiplexed |
| Thread | Luồng redo riêng; trong RAC mỗi instance thường có một redo thread |
| Sequence# | Số thứ tự log trong một thread |
| Log switch | Chuyển CURRENT sang group khác và tăng sequence# |

### 1.4 Multiplexing

Multiplexing nghĩa là một group có nhiều members ở các vị trí lưu trữ khác nhau. LGWR ghi cùng redo vào tất cả members của group.

Mục tiêu là bảo vệ trước lỗi một file hoặc một thiết bị lưu trữ. Nếu một member bị hỏng nhưng member khác vẫn còn sử dụng được, database có thể tiếp tục hoạt động trong một số trường hợp; DBA cần sửa cấu hình và khôi phục redundancy sớm.

Đặt hai members trong hai thư mục khác nhau trên cùng một disk không tạo ra khả năng chịu lỗi của disk. Nên đặt members trên các disk group, ASM failure groups hoặc storage failure domains độc lập theo kiến trúc hạ tầng.

## 2. CURRENT, ACTIVE, INACTIVE và các trạng thái khác

Trạng thái của group được xem trong V$LOG.STATUS.

| STATUS | Ý nghĩa |
|---|---|
| CURRENT | Group đang được LGWR sử dụng để ghi redo hiện tại |
| ACTIVE | Group không còn CURRENT nhưng vẫn cần cho instance recovery |
| INACTIVE | Group không còn cần cho instance recovery; có thể được tái sử dụng khi các điều kiện khác được đáp ứng |
| UNUSED | Group chưa từng được ghi hoặc chưa được sử dụng sau khi tạo |
| CLEARING | Oracle đang clear group |
| CLEARING_CURRENT | Oracle đang clear group hiện là CURRENT trong một tình huống đặc biệt |

Không nhầm ACTIVE với “đang được ghi”. Group đang được ghi là CURRENT. ACTIVE có nghĩa redo trong group vẫn có thể cần để instance recovery hoàn tất.

### 2.1 CURRENT

Mỗi enabled redo thread có một group CURRENT tại một thời điểm. V$LOG cho biết group number, thread number và sequence number đang hoạt động.

### 2.2 ACTIVE

Group có thể đã được switch khỏi CURRENT nhưng checkpoint chưa ghi đủ dirty buffers để group không còn cần cho instance recovery. Khi group còn ACTIVE, Oracle chưa thể tái sử dụng nó như một log group bình thường.

### 2.3 INACTIVE

Group INACTIVE không còn cần cho instance recovery. Trong ARCHIVELOG mode, group còn phải được archive thành công trước khi được tái sử dụng. INACTIVE không đồng nghĩa archive đã hoàn tất trong mọi trường hợp; luôn xem cột ARCHIVED và trạng thái archive liên quan.

### 2.4 UNUSED

Group mới thêm hoặc chưa từng được sử dụng có thể ở trạng thái UNUSED. Sau khi group được dùng và switch ra, nó sẽ chuyển sang trạng thái khác tùy checkpoint/archive.

### 2.5 Trạng thái member

V$LOGFILE.STATUS mô tả tình trạng member, không phải trạng thái group:

| STATUS | Ý nghĩa |
|---|---|
| NULL/blank | Member đang được sử dụng bình thường |
| INVALID | File không thể truy cập hoặc không được xác nhận là member hợp lệ |
| STALE | Nội dung member không đầy đủ hoặc không đồng bộ với redo hiện hành |
| DELETED | Member đã bị xóa khỏi cấu hình database |

Không nhầm V$LOG.STATUS với V$LOGFILE.STATUS. Một group có thể ACTIVE trong khi một member của group bị INVALID.

## 3. ARCHIVELOG và NOARCHIVELOG

Database có thể hoạt động ở ARCHIVELOG hoặc NOARCHIVELOG mode.

### 3.1 ARCHIVELOG mode

Trong ARCHIVELOG mode, khi một redo log group đã đầy và được switch ra, ARCn (Archiver processes) hoặc cơ chế archive được cấu hình sẽ sao chép redo log thành archived redo log. Sau khi group đã INACTIVE và được archive, Oracle có thể tái sử dụng group đó.

Archived redo logs hỗ trợ:

- Media recovery sau khi datafile hoặc storage bị hỏng.
- Point-in-time recovery.
- Backup online nhất quán.
- Data Guard redo transport/apply.

ARCHIVELOG mode không có nghĩa mọi group đều được archive ngay tại thời điểm switch. Archive có thể diễn ra bất đồng bộ sau switch.

### 3.2 NOARCHIVELOG mode

Trong NOARCHIVELOG mode, redo log group được tái sử dụng sau khi không còn cần cho instance recovery/checkpoint. Oracle không giữ archived redo logs cho các vòng switch thông thường.

Khả năng media recovery bị giới hạn; chiến lược backup cần phù hợp và thường phải dùng backup nhất quán trong điều kiện database được shutdown theo quy trình phù hợp.

### 3.3 Kiểm tra archive mode

~~~sql
ARCHIVE LOG LIST;
~~~

Hoặc:

~~~sql
SELECT log_mode,
       force_logging,
       open_mode,
       database_role
FROM v$database;
~~~

LOG_MODE cho biết ARCHIVELOG hoặc NOARCHIVELOG. DATABASE_ROLE giúp phân biệt PRIMARY và STANDBY trong môi trường Data Guard.

## 4. Kiểm tra cấu hình redo log hiện tại

### 4.1 Xem các group

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes,
       blocks,
       members,
       archived,
       status,
       first_change#,
       first_time,
       next_change#,
       next_time
FROM v$log
ORDER BY thread#, group#;
~~~

Các cột quan trọng:

- GROUP#: số group.
- THREAD#: redo thread chứa group.
- SEQUENCE#: sequence number của log.
- BYTES: kích thước group theo byte.
- MEMBERS: số members đã khai báo.
- ARCHIVED: trạng thái archive của log.
- STATUS: CURRENT/ACTIVE/INACTIVE/UNUSED và các trạng thái clearing.
- FIRST_CHANGE#/FIRST_TIME: điểm bắt đầu SCN/thời gian của log.
- NEXT_CHANGE#/NEXT_TIME: điểm kết thúc theo metadata của log khi có.

### 4.2 Xem từng member

~~~sql
SELECT group#,
       type,
       member,
       status,
       is_recovery_dest_file,
       con_id
FROM v$logfile
ORDER BY group#, member;
~~~

GROUP# nối với V$LOG.GROUP#. MEMBER là đường dẫn file hoặc tên ASM disk group/file. TYPE thường là ONLINE hoặc STANDBY. STATUS giúp nhận diện member INVALID, STALE hoặc DELETED.

### 4.3 Xem group và member trong một truy vấn

~~~sql
SELECT l.thread#,
       l.group#,
       l.sequence#,
       l.bytes,
       l.status AS group_status,
       l.archived,
       f.member,
       f.status AS member_status,
       f.type
FROM v$log l
JOIN v$logfile f
  ON f.group# = l.group#
ORDER BY l.thread#, l.group#, f.member;
~~~

Một group xuất hiện nhiều dòng nếu có nhiều members. Đây là điều mong đợi, không phải duplicate lỗi.

### 4.4 Đếm số group theo thread

~~~sql
SELECT thread#,
       COUNT(*) AS group_count,
       MIN(bytes) AS min_group_bytes,
       MAX(bytes) AS max_group_bytes,
       SUM(members) AS total_members
FROM v$log
GROUP BY thread#
ORDER BY thread#;
~~~

Các group trong cùng một thread nên được cấu hình kích thước đồng nhất để log switch và reuse diễn ra ổn định. Kiểm tra cả số members và dung lượng của từng group.

### 4.5 Kiểm tra redo thread

~~~sql
SELECT thread#,
       status,
       enabled,
       instance,
       groups,
       current_group#
FROM v$thread
ORDER BY thread#;
~~~

V$THREAD cho biết thread, trạng thái và instance liên quan. Trong RAC, cần kiểm tra mỗi thread được enabled và có đủ group theo cấu hình mong muốn.

## 5. Thêm redo log group

Có thể thêm redo log group khi database đang OPEN trong các tình huống thông thường. Cần chọn group number chưa được sử dụng, dung lượng phù hợp và vị trí file có đủ dung lượng/IOPS.

### 5.1 Thêm group với tên file tường minh

~~~sql
ALTER DATABASE ADD LOGFILE GROUP 4
(
    '/u02/oradata/ORCL/redo04a.log',
    '/u03/oradata/ORCL/redo04b.log'
)
SIZE 1G;
~~~

Lệnh tạo group 4 với hai members. Hai file trong cùng group có cùng kích thước và cùng nội dung redo. Các đường dẫn phải tồn tại/được Oracle tạo theo cơ chế storage đang dùng; Oracle OS user cần quyền phù hợp.

### 5.2 Thêm group bằng Oracle Managed Files

Nếu database đã cấu hình vị trí tạo online redo log files bằng DB_CREATE_ONLINE_LOG_DEST_n hoặc cấu hình OMF phù hợp, có thể để Oracle tự tạo tên file:

~~~sql
ALTER DATABASE ADD LOGFILE GROUP 5 SIZE 1G;
~~~

Oracle tạo member theo cấu hình OMF. Kiểm tra V$LOGFILE sau khi thêm để biết tên file và vị trí thực tế.

### 5.3 Thêm group cho một redo thread cụ thể

Trong RAC, chỉ định thread khi thêm group cho instance/thread tương ứng:

~~~sql
ALTER DATABASE ADD LOGFILE THREAD 2 GROUP 6
(
    '+DATA/ORCL/ONLINELOG/redo_t2_g6a.log',
    '+FRA/ORCL/ONLINELOG/redo_t2_g6b.log'
)
SIZE 1G;
~~~

Ví dụ đường dẫn ASM chỉ mang tính minh họa. Với OMF/ASM, tuân theo naming và failure-group design của hệ thống. Group number phải duy nhất trong database.

### 5.4 Kiểm tra sau khi thêm

~~~sql
SELECT group#,
       thread#,
       bytes,
       members,
       status
FROM v$log
WHERE group# IN (4, 5, 6)
ORDER BY thread#, group#;

SELECT group#,
       member,
       status,
       type
FROM v$logfile
WHERE group# IN (4, 5, 6)
ORDER BY group#, member;
~~~

Group mới thường có trạng thái UNUSED cho đến khi được sử dụng. Kiểm tra số members thực tế, kích thước và đường dẫn trước khi đưa vào vận hành.

## 6. Thêm member vào một group

Thêm member để tăng redundancy cho group hiện có. Member mới phải có tên/path hợp lệ, cùng dung lượng với các member trong group và nằm trên failure domain phù hợp.

### 6.1 Thêm member bằng tên file

~~~sql
ALTER DATABASE ADD LOGFILE MEMBER
    '/u04/oradata/ORCL/redo01c.log'
TO GROUP 1;
~~~

Oracle tạo member mới thuộc group 1. Không chỉ định SIZE vì kích thước được kế thừa từ group.

### 6.2 Thêm member bằng OMF

Khi OMF được cấu hình, có thể để Oracle chọn tên file:

~~~sql
ALTER DATABASE ADD LOGFILE MEMBER TO GROUP 1;
~~~

Kiểm tra đường dẫn mới trong V$LOGFILE. Cú pháp chính xác phụ thuộc cấu hình OMF và release; nếu hệ thống yêu cầu file name, dùng tên file được tạo theo quy trình storage.

### 6.3 Kiểm tra member mới

~~~sql
SELECT l.group#,
       l.thread#,
       l.status AS group_status,
       f.member,
       f.status AS member_status
FROM v$log l
JOIN v$logfile f
  ON f.group# = l.group#
WHERE l.group# = 1
ORDER BY f.member;
~~~

Sau khi thêm, member có thể chưa được xác nhận hoàn toàn cho đến khi Oracle khởi tạo/đồng bộ nó theo vòng đời log tiếp theo. Nếu V$LOGFILE.STATUS là INVALID hoặc STALE, xem alert log và xử lý member theo trạng thái thực tế; không xóa member còn hợp lệ chỉ vì member mới chưa sẵn sàng.

### 6.4 Multiplexing đúng cách

Ví dụ group 1 có hai member:

~~~text
+----------------------+       +----------------------+
| Storage failure A    |       | Storage failure B    |
| redo01a.log          |       | redo01b.log          |
+----------------------+       +----------------------+
             \                       /
              \                     /
               +-------------------+
               | Redo log group 1  |
               | same redo stream  |
               +-------------------+
~~~

Hai member cùng group nên được đặt trên các thiết bị hoặc failure group độc lập. Hai đường dẫn khác nhau nhưng cùng một filesystem/device không bảo vệ được trước lỗi của thiết bị đó.

## 7. Drop member hoặc drop group

Không drop redo log chỉ dựa trên tên file. Trước tiên xác định group, thread, trạng thái, archive status và member list.

### 7.1 Điều kiện drop member

Có thể drop một member khi group vẫn còn ít nhất một member khác hợp lệ. Không thể để group mất hết members. Không nên drop member đang cần để duy trì khả năng ghi redo.

~~~sql
ALTER DATABASE DROP LOGFILE MEMBER
    '/u04/oradata/ORCL/redo01c.log';
~~~

Sau lệnh, Oracle loại member khỏi control file. Việc xóa file vật lý khỏi filesystem/ASM cần theo trạng thái và quy trình của storage; kiểm tra V$LOGFILE trước khi xóa thủ công. Không xóa file khi database vẫn còn tham chiếu tới nó.

### 7.2 Điều kiện drop group

Trước khi drop một group:

1. Group không được là CURRENT.
2. Group phải không còn ACTIVE; cần INACTIVE để không còn cần cho instance recovery.
3. Trong ARCHIVELOG mode, log phải được archive theo yêu cầu.
4. Thread vẫn còn đủ group sau khi drop; không xóa group cuối cùng hoặc làm cấu hình không đủ để tiếp tục vận hành.
5. Đảm bảo backup/recovery policy và số member còn lại đáp ứng yêu cầu.

Ví dụ:

~~~sql
ALTER DATABASE DROP LOGFILE GROUP 4;
~~~

Nếu group đang CURRENT, thực hiện log switch và chờ group chuyển sang trạng thái có thể drop. Nếu group ACTIVE, chờ checkpoint hoàn tất hoặc xử lý nguyên nhân khiến group còn cần cho instance recovery. Trong ARCHIVELOG mode, xác nhận archive đã hoàn tất.

### 7.3 Kiểm tra trước và sau khi drop

~~~sql
SELECT group#,
       thread#,
       sequence#,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;

SELECT group#,
       member,
       status
FROM v$logfile
ORDER BY group#, member;
~~~

Sau khi drop, xác nhận group/member không còn trong control file. Nếu file vật lý còn lại trên disk, chỉ dọn khi chắc chắn file không được database khác hoặc cấu hình khác sử dụng.

### 7.4 Vì sao không nên drop group CURRENT hoặc ACTIVE?

- CURRENT đang được LGWR sử dụng để ghi redo.
- ACTIVE có thể chứa redo cần thiết cho instance recovery.
- Drop sai trạng thái có thể bị Oracle từ chối hoặc làm mất khả năng recovery nếu dùng thao tác clear không đúng.

Không tìm cách lách kiểm tra bằng cách clear hoặc xóa file ở hệ điều hành. Hãy switch, archive và chờ checkpoint theo quy trình.

## 8. Log switch

Log switch là quá trình Oracle chuyển group CURRENT sang một group khác trong cùng redo thread. Khi switch:

- Group mới trở thành CURRENT.
- SEQUENCE# tăng lên trong thread.
- Group cũ không còn CURRENT; nó có thể ACTIVE hoặc INACTIVE tùy checkpoint.
- Trong ARCHIVELOG mode, group cũ được archive bất đồng bộ.

### 8.1 Khi nào tự động switch?

LGWR chuyển sang group khác khi group CURRENT đầy. Oracle tiếp tục ghi redo vào group kế tiếp có thể sử dụng.

Nếu group kế tiếp chưa sẵn sàng vì checkpoint chưa hoàn tất hoặc archive chưa xong, database có thể phải chờ. Đây là lý do cần đủ group và kích thước group phù hợp.

### 8.2 Ép log switch thủ công

~~~sql
ALTER SYSTEM SWITCH LOGFILE;
~~~

Lệnh yêu cầu switch redo log của thread thuộc instance hiện tại. Nó hữu ích để kiểm tra cấu hình, archive hoặc đưa group hiện tại ra khỏi trạng thái CURRENT trước thao tác quản trị. Trong RAC, cần xác định instance/thread đang thao tác.

### 8.3 Ép archive log hiện tại

~~~sql
ALTER SYSTEM ARCHIVE LOG CURRENT;
~~~

Trong ARCHIVELOG mode, lệnh yêu cầu archive redo log hiện tại; thao tác này bao gồm việc chuyển log để tạo log cần archive. Nó thường được dùng trong quy trình backup hoặc khi cần đảm bảo log hiện tại được archive.

SWITCH LOGFILE và ARCHIVE LOG CURRENT không hoàn toàn giống nhau về mục tiêu:

| Lệnh | Mục tiêu |
|---|---|
| ALTER SYSTEM SWITCH LOGFILE | Yêu cầu chuyển sang redo log group khác |
| ALTER SYSTEM ARCHIVE LOG CURRENT | Yêu cầu archive redo log hiện tại; thường bao gồm log switch |

Switch không đồng nghĩa archive đã hoàn tất. Sau lệnh, kiểm tra V$LOG.ARCHIVED, V$ARCHIVED_LOG và alert log.

### 8.4 Theo dõi sequence trước và sau switch

~~~sql
SELECT thread#,
       group#,
       sequence#,
       status,
       archived,
       first_time
FROM v$log
ORDER BY thread#, group#;
~~~

Sau switch, group CURRENT có sequence mới. Group cũ chuyển sang ACTIVE hoặc INACTIVE.

### 8.5 Theo dõi lịch sử switch

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       first_change#
FROM v$log_history
ORDER BY first_time DESC
FETCH FIRST 50 ROWS ONLY;
~~~

V$LOG_HISTORY ghi lịch sử log switch theo thread/sequence. Có thể dùng FIRST_TIME để tính khoảng cách giữa hai lần switch.

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       ROUND(
           (first_time - LAG(first_time) OVER (
               PARTITION BY thread#
               ORDER BY first_time
           )) * 1440,
           2
       ) AS minutes_since_previous_switch
FROM v$log_history
ORDER BY thread#, first_time DESC;
~~~

Khoảng thời gian rất ngắn giữa các switch liên tiếp có thể gợi ý group quá nhỏ hoặc redo generation tăng mạnh. Cần so sánh với workload và thời điểm batch/ETL.

## 9. Checkpoint, archive và khả năng tái sử dụng group

Log switch chỉ thay đổi group CURRENT; nó không tự động làm group cũ INACTIVE ngay lập tức.

### 9.1 Checkpoint

Checkpoint ghi tiến độ của các dirty buffers từ buffer cache xuống datafiles và cập nhật checkpoint information trong control file/datafile headers. Khi checkpoint tiến qua redo range của một group, group đó có thể không còn cần cho instance recovery.

Nếu checkpoint chưa hoàn tất, group cũ có thể vẫn ACTIVE.

### 9.2 Archive

Trong ARCHIVELOG mode, redo log cần được archive trước khi group được tái sử dụng. ARCn đọc online redo log và tạo archived redo log tại archive destination.

### 9.3 Điều kiện để group được reuse

Trong ARCHIVELOG mode, thông thường group phải:

- Không còn CURRENT.
- Không còn ACTIVE (đã đủ điều kiện checkpoint).
- Được archive thành công.

Trong NOARCHIVELOG mode, điều kiện archive không áp dụng; group vẫn phải không còn cần cho instance recovery trước khi được reuse.

### 9.4 Kiểm tra archive destination

~~~sql
SELECT dest_id,
       status,
       destination,
       error,
       recovery_mode,
       synchronization_status
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Một số cột có thể khác theo release/role; nếu view không có cột trong phiên bản đang dùng, kiểm tra Database Reference tương ứng. Cần xem ERROR và destination khi archive không tiến triển.

### 9.5 Kiểm tra archived redo logs

~~~sql
SELECT thread#,
       sequence#,
       first_time,
       completion_time,
       archived,
       deleted,
       status,
       name
FROM v$archived_log
ORDER BY thread#, sequence# DESC
FETCH FIRST 100 ROWS ONLY;
~~~

V$ARCHIVED_LOG có thể có nhiều bản ghi cho cùng thread/sequence khi log được lưu ở nhiều destination hoặc được copy/restore. Không giả định mỗi sequence chỉ có một row.

## 10. Xử lý member bị lỗi hoặc mất file

Redo log member là bản sao của group. Nếu một member không thể truy cập, Oracle có thể tiếp tục ghi vào member còn lại của group trong nhiều tình huống, nhưng redundancy đã bị suy giảm. Cần kiểm tra alert log, sửa storage/path và khôi phục member sớm.

### 10.1 Nhận diện member lỗi

~~~sql
SELECT group#,
       member,
       status,
       type
FROM v$logfile
WHERE status IS NOT NULL
ORDER BY group#, member;
~~~

Các trạng thái INVALID hoặc STALE cần được điều tra. STATUS NULL/blank thường biểu thị member bình thường. Đối chiếu với alert log để biết lỗi mở file, I/O, permission hay storage.

### 10.2 Một member hỏng, member khác vẫn hoạt động

Quy trình khái quát:

1. Xác định group và thread chứa member lỗi.
2. Kiểm tra group còn member hợp lệ và database vẫn ghi redo được.
3. Xác định nguyên nhân storage/path/permission.
4. Thêm member mới vào đúng group ở vị trí lưu trữ độc lập.
5. Kiểm tra trạng thái member mới và alert log.
6. Khi member mới hoạt động, drop member lỗi khỏi control file.
7. Kiểm tra lại số member và đường dẫn.

Ví dụ:

~~~sql
ALTER DATABASE ADD LOGFILE MEMBER
    '/u04/oradata/ORCL/redo01c.log'
TO GROUP 1;

SELECT group#,
       member,
       status
FROM v$logfile
WHERE group# = 1;
~~~

Khi member mới đã hợp lệ và group vẫn có đủ member hoạt động:

~~~sql
ALTER DATABASE DROP LOGFILE MEMBER
    '/u02/oradata/ORCL/redo01a.log';
~~~

Tên file và group trong ví dụ phải được thay bằng giá trị đã xác minh trong môi trường. Không drop member hợp lệ nếu group chỉ còn một member có thể ghi.

### 10.3 Nếu tất cả members của CURRENT group bị mất

Đây là tình huống nghiêm trọng vì LGWR không còn nơi ghi redo hiện tại. Database có thể bị treo hoặc instance termination tùy tình huống. Không xóa file, clear group hoặc restart tùy tiện.

Hãy:

- Giữ lại alert log và chẩn đoán lỗi storage.
- Xác định member còn có thể phục hồi từ bản sao/storage snapshot hay không.
- Thực hiện quy trình recovery theo Oracle Support/DBA runbook của môi trường.
- Đánh giá khả năng mất redo và tính nhất quán của database trước khi mở lại.

Nếu group CURRENT không còn bản redo hợp lệ, đây có thể là sự cố recovery chứ không còn là thao tác thêm member thông thường.

### 10.4 Member mới có trạng thái INVALID hoặc STALE

Không mặc định member đã được đồng bộ chỉ vì lệnh ADD LOGFILE MEMBER thành công. Kiểm tra V$LOGFILE.STATUS, alert log và vòng đời log switch. Nếu member không được khởi tạo đúng, sửa path/permission hoặc drop member lỗi và thêm lại theo quy trình phù hợp.

## 11. CLEAR LOGFILE và các cảnh báo recovery

ALTER DATABASE CLEAR LOGFILE được dùng trong các tình huống đặc biệt khi cần khởi tạo lại nội dung một redo log group, ví dụ log bị hỏng hoặc không thể sử dụng theo quy trình thông thường.

### 11.1 Cú pháp cơ bản

~~~sql
ALTER DATABASE CLEAR LOGFILE GROUP 4;
~~~

Lệnh này không phải cách thông thường để giải phóng group ACTIVE hoặc ép log switch. Trước khi clear, phải xác định group có đang cần cho instance/media recovery hay không và trạng thái archive của nó.

### 11.2 CLEAR UNARCHIVED LOGFILE

Trong một số tình huống recovery, Oracle cho phép clear một log chưa archive:

~~~sql
ALTER DATABASE CLEAR UNARCHIVED LOGFILE GROUP 4;
~~~

Đây là thao tác có rủi ro cao. Khi clear một unarchived log, redo cần thiết cho recovery có thể bị mất. Backup hiện có có thể không còn recoverable qua redo bị clear; cần thực hiện backup mới và kiểm tra chiến lược recovery.

Không dùng CLEAR UNARCHIVED như cách xử lý nhanh khi ARCn chậm hoặc archive destination đầy. Trước tiên phải sửa nguyên nhân archive/checkpoint.

### 11.3 Khi nào cần hỗ trợ recovery chuyên biệt?

Nếu group đang CURRENT, ACTIVE hoặc chứa redo cần cho crash/media recovery, Oracle có thể từ chối thao tác clear/drop. Trong trường hợp log bị hỏng hoặc mất, cần xác định database state, thread, sequence, archive status và backup availability. Thực hiện recovery theo đúng tài liệu/Oracle Support thay vì thử nhiều lệnh ALTER DATABASE.

## 12. Di chuyển redo log member

Không di chuyển hoặc đổi tên file redo log bằng cách chỉ đổi tên file ở hệ điều hành trong khi database đang sử dụng. Control file lưu tên/path của member; phải cập nhật metadata database.

### 12.1 Quy trình offline dùng RENAME FILE

Quy trình tổng quát cho một database non-RAC hoặc thao tác được phối hợp đúng với RAC:

1. Lên kế hoạch downtime và xác định tất cả members cần di chuyển.
2. Shutdown database sạch theo runbook.
3. Copy file từ vị trí cũ sang vị trí mới ở storage.
4. Startup MOUNT, chưa OPEN database.
5. Dùng ALTER DATABASE RENAME FILE để cập nhật tên trong control file.
6. Mở database và kiểm tra V$LOGFILE.

Ví dụ:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

ALTER DATABASE RENAME FILE
    '/u02/oradata/ORCL/redo01a.log'
TO  '/u05/oradata/ORCL/redo01a.log';

ALTER DATABASE OPEN;
~~~

File phải được copy đầy đủ sang vị trí mới trước khi rename metadata. Với RAC, cần phối hợp các instance/threads và thực hiện theo runbook cluster; không áp dụng một lệnh offline cho một file rồi giả định các instance khác không bị ảnh hưởng.

### 12.2 Di chuyển bằng cách add member rồi drop member

Nếu database có member khác hoạt động và kiến trúc cho phép, có thể:

1. ADD LOGFILE MEMBER tại storage mới.
2. Xác nhận member mới hợp lệ.
3. DROP LOGFILE MEMBER cũ.
4. Dọn file cũ sau khi database không còn tham chiếu.

Cách này có thể tránh downtime cho một số thay đổi storage, nhưng cần xác minh trạng thái group và quy trình vận hành của release/ASM. Không dùng nó để thay thế recovery khi tất cả members đã mất.

## 13. Đổi kích thước redo log group

Không có thao tác resize tại chỗ một online redo log group đang được sử dụng. Cách thông dụng là tạo các group mới với kích thước mong muốn, chuyển workload qua chúng, rồi drop các group cũ khi chúng đủ điều kiện.

### 13.1 Quy trình add–switch–drop

Giả sử group cũ có kích thước 100 MB và muốn chuyển sang 1 GB:

~~~sql
ALTER DATABASE ADD LOGFILE GROUP 10
(
    '/u02/oradata/ORCL/redo10a.log',
    '/u03/oradata/ORCL/redo10b.log'
)
SIZE 1G;
~~~

Sau đó:

1. Xác nhận group 10 có đủ members và dung lượng.
2. Thực hiện log switch theo kế hoạch.
3. Theo dõi để các group cũ trở thành INACTIVE và được archive (nếu ARCHIVELOG).
4. Drop từng group cũ khi đủ điều kiện.
5. Kiểm tra mọi group còn lại có cùng kích thước theo thread và đủ redundancy.

Không drop hết group cũ trước khi chắc chắn database có đủ group mới để tiếp tục hoạt động.

### 13.2 Vì sao các group trong cùng thread nên cùng kích thước?

Nếu group có kích thước khác nhau, thời gian giữa các log switch sẽ không đều và Oracle có thể chuyển qua các group nhỏ thường xuyên hơn. Đồng nhất kích thước giúp dự đoán switch interval và dung lượng archive dễ hơn.

### 13.3 Bao nhiêu group là đủ?

Oracle cần tối thiểu hai groups cho mỗi thread. Production thường cần nhiều hơn để có thời gian cho checkpoint và archive hoàn tất trước khi group quay lại được cần dùng. Ba hoặc nhiều hơn là điểm khởi đầu thường gặp, nhưng số lượng đúng phụ thuộc redo rate, archive throughput, checkpoint và thời gian switch.

Nếu group luôn bị tái sử dụng trước khi checkpoint/archive xong, tăng số group có thể giảm việc LGWR phải chờ reuse. Tuy nhiên, tăng số group không sửa được archive destination bị đầy hoặc storage I/O quá chậm.

## 14. Chọn kích thước redo log

Kích thước group ảnh hưởng tần suất log switch và lượng redo cần archive trong mỗi file.

### 14.1 Group quá nhỏ

Hệ quả có thể gồm:

- Log switch xảy ra quá thường xuyên.
- ARCn phải archive nhiều file nhỏ.
- Checkpoint phải xử lý liên tục.
- Có thể xuất hiện wait log file switch (checkpoint incomplete) hoặc log file switch (archiving needed).
- Tăng overhead quản lý archive logs và backup.

### 14.2 Group quá lớn

Group quá lớn cũng có đánh đổi:

- Archive log mỗi lần switch lớn hơn.
- Archive/backup/transport có thể cần nhiều thời gian và dung lượng hơn cho từng file.
- Khi cần chuyển log để tạo điểm archive, phải chờ lượng redo lớn hơn được ghi.
- Có thể làm khó quản lý retention/storage nếu không có chính sách phù hợp.

Không có một kích thước đúng cho mọi database. Chọn theo redo generation rate ở giờ cao điểm, thời gian switch mong muốn, tốc độ archive và khả năng recovery.

### 14.3 Ước lượng kích thước theo redo rate

Có thể dùng công thức khởi đầu:

\[
\text{Group size} \approx
\text{Peak redo bytes per second}
\times
\text{Target switch interval in seconds}
\]

Ví dụ, peak redo generation khoảng 8 MB/s và mục tiêu switch khoảng 15 phút:

\[
8 \times 900 = 7.200\ \text{MB} \approx 7,2\ \text{GB}
\]

Đây là ước lượng ban đầu, không phải cấu hình bắt buộc. Cần kiểm tra archive throughput, storage, số group và thời gian checkpoint. Có thể chọn dung lượng thấp hơn/cao hơn tùy mục tiêu vận hành.

### 14.4 Tính redo generation rate bằng V$SYSSTAT

Statistic redo size là số byte redo được tạo tích lũy ở phạm vi instance:

~~~sql
SELECT name,
       value
FROM v$sysstat
WHERE name = 'redo size';
~~~

Lấy snapshot T0 và T1:

\[
\text{Redo rate} =
\frac{\text{redo size}_{T1}-\text{redo size}_{T0}}
{\text{seconds between snapshots}}
\]

Trong RAC, dùng GV$SYSSTAT và tính riêng từng INST_ID. Nếu lấy tổng toàn cluster, cộng delta của các instance sau khi xác nhận cùng khoảng thời gian.

### 14.5 Theo dõi switch interval thực tế

~~~sql
SELECT thread#,
       COUNT(*) AS switches,
       MIN(first_time) AS first_switch_time,
       MAX(first_time) AS last_switch_time
FROM v$log_history
WHERE first_time >= SYSDATE - 1
GROUP BY thread#
ORDER BY thread#;
~~~

Để xem khoảng cách giữa các switch:

~~~sql
WITH history AS (
    SELECT thread#,
           sequence#,
           first_time,
           LAG(first_time) OVER (
               PARTITION BY thread#
               ORDER BY first_time
           ) AS previous_time
    FROM v$log_history
    WHERE first_time >= SYSDATE - 1
)
SELECT thread#,
       sequence#,
       first_time,
       ROUND((first_time - previous_time) * 1440, 2)
           AS minutes_since_previous
FROM history
WHERE previous_time IS NOT NULL
ORDER BY thread#, first_time;
~~~

Nhiều hệ thống dùng 15–30 phút làm khoảng switch tham khảo ban đầu; đây không phải giới hạn hay yêu cầu cứng của Oracle. Hãy đo theo workload, redo rate và archive/checkpoint capacity.

## 15. Chẩn đoán log switch waits và LGWR

Các wait event liên quan redo thường chỉ ra group chưa sẵn sàng, archive chậm hoặc I/O ghi redo chậm.

### 15.1 log file switch (checkpoint incomplete)

Session hoặc LGWR phải chờ vì group kế tiếp chưa thể tái sử dụng; checkpoint chưa hoàn tất việc ghi các dirty buffers cần thiết.

Hướng điều tra:

- Kiểm tra V$LOG để thấy nhiều group ACTIVE không.
- Xem DBWR/checkpoint workload và I/O datafiles.
- Kiểm tra số group có đủ không.
- Đánh giá kích thước group và redo rate.
- Xem storage latency cho datafiles.

Tăng số group hoặc kích thước có thể giúp nếu vấn đề là log quay vòng quá nhanh, nhưng không sửa được datafile I/O nghẽn kéo dài.

### 15.2 log file switch (archiving needed)

Group cần được archive trước khi tái sử dụng nhưng archive chưa hoàn tất.

Hướng điều tra:

- Kiểm tra LOG_MODE.
- Xem V$ARCHIVE_DEST_STATUS.ERROR và destination.
- Kiểm tra FRA/destination còn đủ dung lượng không.
- Kiểm tra ARCn và tốc độ ghi archive.
- Kiểm tra Data Guard transport nếu archive/redo bị chặn bởi cấu hình liên quan.

Không chỉ tăng số group để che lỗi archive destination đầy. Cần giải phóng/mở rộng destination hoặc sửa lỗi archive.

### 15.3 log file switch completion

Session đang chờ log switch hoàn tất. Xem trạng thái các group, LGWR, checkpoint và archive để tìm lý do switch chưa hoàn tất.

### 15.4 log file parallel write

LGWR chờ hoàn thành I/O ghi redo log members. Có thể liên quan latency storage, số member, đường đi I/O hoặc contention trên thiết bị.

Nếu một group có nhiều members trên các thiết bị chậm khác nhau, tốc độ ghi của group có thể bị ảnh hưởng bởi member chậm. Multiplexing nên dùng các storage có hiệu năng phù hợp, không chỉ khác đường dẫn.

### 15.5 log file sync

Foreground session chờ LGWR flush redo để hoàn tất COMMIT. Đây là commit latency, không đồng nghĩa với log switch wait. Điều tra:

- log file parallel write.
- Storage latency của redo log.
- Tần suất commit và ứng dụng commit quá thường xuyên.
- Network/application behavior nếu client phản hồi chậm sau commit.

Tăng kích thước redo log group thường không trực tiếp giải quyết log file sync.

### 15.6 log buffer space

Session chờ vì không có đủ không gian redo log buffer để ghi redo mới. Điều này có thể xảy ra khi redo generation vượt tốc độ LGWR giải phóng buffer hoặc có bottleneck ghi redo. Cần xem redo rate, LGWR I/O và các wait liên quan; không tự động tăng LOG_BUFFER mà chưa đo nguyên nhân.

### 15.7 Xem wait event ở cấp instance

~~~sql
SELECT event,
       total_waits,
       ROUND(time_waited_micro / 1000000, 2) AS total_wait_seconds,
       ROUND(average_wait, 3) AS average_wait_centiseconds
FROM v$system_event
WHERE event IN (
    'log file switch (checkpoint incomplete)',
    'log file switch (archiving needed)',
    'log file switch completion',
    'log file parallel write',
    'log file sync',
    'log buffer space'
)
ORDER BY time_waited_micro DESC;
~~~

Các giá trị trong V$SYSTEM_EVENT là tích lũy từ khi instance startup. Để đánh giá một khoảng thời gian, lấy hai snapshot và tính delta. Trong RAC dùng GV$SYSTEM_EVENT và giữ INST_ID.

### 15.8 Xem wait của session

~~~sql
SELECT sid,
       event,
       total_waits,
       time_waited_micro,
       average_wait
FROM v$session_event
WHERE event LIKE 'log file%'
   OR event = 'log buffer space'
ORDER BY time_waited_micro DESC;
~~~

V$SESSION_EVENT cũng là số liệu tích lũy theo session. Với session lâu năm, tổng wait có thể lớn nhưng không nhất thiết đang có vấn đề ở hiện tại. Kết hợp V$SESSION.EVENT/STATE và snapshot delta.

## 16. RAC: redo threads và log groups

Trong Oracle RAC, mỗi instance thường có một redo thread riêng. Mỗi thread có các online redo log groups riêng, nhưng tất cả đều thuộc cùng database.

### 16.1 Thread và instance

V$THREAD hiển thị:

- THREAD#: định danh redo thread.
- STATUS/ENABLED: trạng thái thread.
- INSTANCE: instance liên quan.
- GROUPS: số group của thread.
- CURRENT_GROUP#: group hiện tại.

Trong RAC, không chỉ xem tổng số group toàn database. Phải bảo đảm từng thread có đủ group, đúng kích thước và số member.

### 16.2 Xem group theo thread

~~~sql
SELECT thread#,
       group#,
       sequence#,
       bytes,
       members,
       archived,
       status
FROM gv$log
ORDER BY thread#, group#;
~~~

### 16.3 Thêm group cho thread

~~~sql
ALTER DATABASE ADD LOGFILE THREAD 2 GROUP 12
(
    '+DATA/ORCL/ONLINELOG/redo_t2_g12a.log',
    '+FRA/ORCL/ONLINELOG/redo_t2_g12b.log'
)
SIZE 1G;
~~~

Tên ASM chỉ minh họa. Trong RAC, phối hợp với DBA/storage để bảo đảm members ở các failure groups phù hợp và group được gán đúng thread.

### 16.4 Log switch trong RAC

ALTER SYSTEM SWITCH LOGFILE tác động redo thread của instance thực hiện lệnh. Nếu cần switch thread của instance khác, kết nối đúng instance hoặc dùng quy trình cluster đã được phê duyệt. Không coi một lệnh từ một instance là đã switch mọi thread.

### 16.5 GV$ và INST_ID

Khi truy vấn toàn cluster, dùng GV$LOG, GV$LOGFILE, GV$THREAD, GV$SYSTEM_EVENT và giữ INST_ID. Một group number trong database là duy nhất, nhưng trạng thái thread/instance vẫn cần được xem cùng nhau.

## 17. Data Guard và Standby Redo Logs

Standby redo logs (SRL) thường được dùng ở physical standby để nhận redo từ primary và hỗ trợ real-time apply. Chúng khác online redo log groups của primary.

Trong V$LOGFILE, TYPE có thể là ONLINE hoặc STANDBY. Không nhầm SRL với online redo log của thread đang phục vụ user workload.

Một số lưu ý:

- Standby cần số lượng và kích thước SRL phù hợp với online redo logs của primary và số redo threads.
- SRL được dùng theo cơ chế nhận redo, không phải nơi LGWR của primary ghi online redo thông thường.
- Data Guard transport/apply lag có thể khiến archive/log reuse và recovery operations bị ảnh hưởng; kiểm tra destination status và broker/standby metrics.
- Thay đổi redo configuration trong Data Guard phải được phối hợp trên primary và standby theo quy trình role tương ứng.

## 18. Backup và recovery khi thay đổi redo logs

Redo log là thành phần thiết yếu của recovery. Trước khi drop, clear, rename hoặc thay đổi cấu hình, phải biết redo nào còn cần cho instance recovery, media recovery, backup và standby.

### 18.1 Sau khi thêm hoặc drop group

Kiểm tra:

- Database còn đủ group cho mỗi thread.
- Members có thể truy cập.
- Group size và member count nhất quán.
- Archive destination hoạt động.
- Data Guard (nếu có) vẫn nhận/apply redo.
- Alert log không có lỗi LGWR/ARCn.

### 18.2 Sau CLEAR UNARCHIVED LOGFILE

Nếu đã clear một unarchived log, cần đánh giá lại khả năng phục hồi từ backup hiện tại. Thực hiện backup database mới theo recovery policy và lưu lại sự kiện/sequence bị ảnh hưởng.

### 18.3 Không xóa file redo bằng OS khi control file còn tham chiếu

Xóa file vật lý trước khi drop/rename metadata có thể làm database không mở được hoặc LGWR báo lỗi khi cần group. Luôn cập nhật database metadata bằng SQL đúng quy trình trước khi dọn file.

### 18.4 Giữ alert log

Alert log ghi lại log switch, archive errors, member I/O errors, group clearing và nhiều sự kiện recovery. Khi có sự cố, kiểm tra alert log cùng timestamp của V$LOG/V$LOGFILE/V$ARCHIVED_LOG để dựng lại trình tự.

## 19. Các lỗi thường gặp

| Lỗi/tình huống | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| ORA-00313 / ORA-00312 | Không mở/đọc/ghi được redo log member | Kiểm tra path, permission, storage và alert log |
| ORA-00308 | Không mở được archived log | Kiểm tra archive destination, file tồn tại và quyền |
| ORA-00257 | Archiver error, thường do archive destination/FRA hết chỗ hoặc lỗi archive | Xử lý destination/ARCn; không chỉ switch thêm |
| ORA-01624 | Log cần cho crash recovery, chưa thể drop/clear | Chờ/hoàn tất recovery/checkpoint theo đúng quy trình |
| ORA-01623 | Không thể drop log group đang CURRENT | Switch sang group khác trước |
| ORA-01624 hoặc group vẫn ACTIVE | Redo còn cần cho instance recovery | Chờ checkpoint hoặc điều tra I/O/checkpoint |
| Log switch liên tục | Group quá nhỏ hoặc redo rate tăng | Đo redo rate, tăng size/số group phù hợp |
| log file switch (checkpoint incomplete) | Checkpoint chưa giải phóng group kế tiếp | Kiểm tra DBWR/datafile I/O, group count và size |
| log file switch (archiving needed) | Archive chưa hoàn tất | Kiểm tra ARCn, FRA/destination và Data Guard |
| Member INVALID/STALE | File thiếu, lỗi I/O hoặc chưa đồng bộ | Khôi phục/add member, kiểm tra trạng thái rồi drop member lỗi |
| Group có một member | Multiplexing chưa đủ redundancy | Thêm member trên failure domain độc lập |
| Group size không đồng nhất | Thay đổi cấu hình chưa hoàn tất | Add group mới cùng size, switch và drop group cũ |

Mã lỗi cụ thể và điều kiện phát sinh phụ thuộc trạng thái database và release. Đọc toàn bộ error stack và alert log; không chỉ xử lý theo một mã lỗi rút gọn.

## 20. Checklist vận hành redo log

Trước khi thay đổi redo log:

1. Đã xác nhận ARCHIVELOG/NOARCHIVELOG mode chưa?
2. Đã xem tất cả group, thread, sequence, size và status trong V$LOG chưa?
3. Đã xem mọi member và status trong V$LOGFILE chưa?
4. Các members có nằm trên failure domains độc lập không?
5. Mỗi thread có đủ group để log switch, checkpoint và archive không?
6. Group sizes trong cùng thread có đồng nhất không?
7. Đã kiểm tra archive destination, FRA và ARCn chưa?
8. Đã xác nhận group định drop không CURRENT, không ACTIVE và đã archive nếu cần chưa?
9. Đã kiểm tra Data Guard/SRL nếu database có standby chưa?
10. Đã xác định tác động backup/recovery của CLEAR hoặc CLEAR UNARCHIVED chưa?
11. Đã giữ file vật lý cho đến khi control file không còn tham chiếu chưa?
12. Đã xem alert log sau thao tác chưa?

Khi điều tra log switch:

1. Đã tính switch interval theo thread chưa?
2. Đã đo redo generation rate bằng delta redo size chưa?
3. Có wait checkpoint incomplete hay archiving needed không?
4. LGWR có chờ log file parallel write không?
5. Foreground có chờ log file sync không?
6. Archive destination có ERROR hoặc hết dung lượng không?
7. Group kế tiếp có INACTIVE và ARCHIVED phù hợp không?
8. Số group/size có phù hợp peak workload không?

## 21. Tổng kết

Online redo logs là nền tảng cho instance recovery và media recovery. Oracle tổ chức chúng thành groups; mỗi group có một hoặc nhiều members chứa cùng redo. LGWR ghi vào group CURRENT, còn các group cũ chuyển qua ACTIVE/INACTIVE tùy checkpoint và điều kiện archive.

- Multiplex members trên các storage failure domains độc lập để bảo vệ trước lỗi một file/thiết bị.
- Theo dõi group bằng V$LOG, member bằng V$LOGFILE và thread bằng V$THREAD.
- Trong ARCHIVELOG mode, group phải được archive trước khi tái sử dụng; checkpoint cũng phải giải phóng redo khỏi nhu cầu instance recovery.
- Log switch tự động xảy ra khi group đầy; ALTER SYSTEM SWITCH LOGFILE yêu cầu switch thủ công cho thread hiện tại, còn ARCHIVE LOG CURRENT yêu cầu archive log hiện tại.
- Thêm group/member có thể thực hiện theo SQL DDL; drop group chỉ khi không CURRENT/ACTIVE và đáp ứng archive/recovery requirements.
- Không resize group tại chỗ; dùng add–switch–drop để chuyển sang kích thước mới.
- CLEAR LOGFILE và đặc biệt CLEAR UNARCHIVED LOGFILE là thao tác recovery có rủi ro, không phải công cụ xử lý switch thường ngày.
- Trong RAC, mỗi instance có redo thread riêng; giữ thread/INST_ID khi kiểm tra và thao tác.
- Phân biệt online redo logs với standby redo logs trong Data Guard.
- Đo redo rate và switch interval theo workload thực tế; chẩn đoán riêng checkpoint waits, archive waits, LGWR I/O và commit waits.

Quản lý redo log tốt là duy trì đủ group và member, đặt chúng trên storage phù hợp, giữ archive/checkpoint tiến triển và kiểm tra recovery trước mọi thay đổi có tính phá hủy.

## 22. Tài liệu Oracle tham khảo

- Oracle Database 19c Administrator's Guide, “Managing the Redo Log”: https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-the-redo-log.html
- Oracle Database 19c Administrator's Guide, “Multiplexing the Redo Log”: https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-the-redo-log.html#GUID-7F4D4A6B-2A0A-4D3E-8C1E-6E8C8B6A9C3A
- Oracle Database 19c Database Reference, “V$LOG”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOG.html
- Oracle Database 19c Database Reference, “V$LOGFILE”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOGFILE.html
- Oracle Database 19c Database Reference, “V$LOG_HISTORY”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOG_HISTORY.html
- Oracle Database 19c Database Reference, “V$THREAD”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-THREAD.html
- Oracle Database 19c Database Reference, “V$ARCHIVED_LOG”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ARCHIVED_LOG.html
- Oracle Database 19c Database Reference, “V$ARCHIVE_DEST_STATUS”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-ARCHIVE_DEST_STATUS.html
- Oracle Database 19c Database Reference, “V$SYSTEM_EVENT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SYSTEM_EVENT.html
- Oracle Database 19c Data Guard Concepts and Administration, “Managing Standby Redo Logs”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/managing-oracle-data-guard-physical-standby-databases.html
