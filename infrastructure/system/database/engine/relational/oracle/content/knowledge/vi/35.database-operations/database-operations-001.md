# STARTUP NOMOUNT, MOUNT, OPEN và điều kiện sử dụng từng trạng thái

Oracle Database khởi động theo các giai đoạn. Ba trạng thái thường gặp nhất là **NOMOUNT**, **MOUNT** và **OPEN**. Mỗi trạng thái thể hiện mức độ mà instance đã khởi tạo và database đã được mở tới đâu:

- **NOMOUNT**: Oracle đã khởi tạo instance từ file tham số, cấp phát SGA và khởi động các background process cần thiết. Control file chưa được mở.
- **MOUNT**: instance đã chạy và database đã được gắn vào instance bằng cách mở control file. Datafile và online redo log chưa được mở để phục vụ hoạt động database bình thường.
- **OPEN**: Oracle mở datafile và online redo log cần thiết, kiểm tra tính nhất quán và thực hiện recovery cần thiết. Database sẵn sàng cho các kết nối và thao tác phù hợp với open mode.

Có thể hình dung chuỗi khởi động:

~~~text
SHUTDOWN
   |
   | STARTUP NOMOUNT
   v
NOMOUNT
   |
   | ALTER DATABASE MOUNT
   v
MOUNT
   |
   | ALTER DATABASE OPEN
   v
OPEN
~~~

Không phải mọi tác vụ đều cần database ở trạng thái OPEN. Tạo database và một số thao tác control file cần NOMOUNT; recovery hoặc thay đổi cấu hình file có thể cần MOUNT; hoạt động ứng dụng thông thường cần OPEN. Chọn sai trạng thái có thể khiến lệnh không thực hiện được hoặc làm tăng rủi ro vận hành.

Bài học giải thích sự khác nhau giữa instance và database, điều kiện của từng trạng thái, lệnh chuyển trạng thái, cách xác nhận trạng thái hiện tại, các open mode, recovery, CDB/PDB, RAC và những lỗi thường gặp khi khởi động.

## 1. Instance và database là hai khái niệm khác nhau

Muốn hiểu NOMOUNT, MOUNT và OPEN, trước hết cần tách hai thành phần:

- **Instance** là các cấu trúc bộ nhớ và tiến trình nền đang chạy để quản lý database.
- **Database** là tập các file vật lý chứa dữ liệu và metadata, chẳng hạn datafile, control file và online redo log.

Instance có thể đang chạy trong khi database chưa được mount hoặc open.

### 1.1. Instance gồm những gì?

Khi khởi động instance, Oracle đọc initialization parameter file rồi tạo môi trường thực thi, gồm:

- System Global Area (SGA).
- Background processes, ví dụ DBWn, LGWR, CKPT, SMON, PMON và các process khác tùy cấu hình.
- Các cấu trúc quản lý bộ nhớ, session, buffer và transaction.
- Thông tin cấu hình cần thiết để tiếp tục gắn với database.

Instance có thể tồn tại ở trạng thái NOMOUNT mà chưa mở control file.

### 1.2. Database gồm những file nào?

Các file quan trọng gồm:

| File | Vai trò |
| --- | --- |
| Control file | Ghi metadata cấu trúc database, checkpoint, danh sách datafile/redo log và thông tin recovery |
| Datafile | Chứa các database block, segment, table, index và dữ liệu khác |
| Online redo log | Ghi redo cần cho recovery và bảo đảm tính nhất quán |
| Archived redo log | Bản lưu của redo log đã đầy, dùng cho media recovery và Data Guard |
| Parameter file | Chứa tham số để khởi tạo instance; SPFILE/PFILE không phải datafile |

Control file không phải nơi lưu nội dung bảng. Datafile không thay thế control file. Online redo log cũng không phải bản sao đầy đủ của database; nó ghi các thay đổi cần thiết để recovery.

### 1.3. Instance chạy không có nghĩa database đã mở

Ba tình huống:

- NOMOUNT: instance đã chạy, database chưa mount.
- MOUNT: instance chạy, control file đã mở, database chưa open.
- OPEN: database đã được mở theo một open mode.

Do đó, câu “Oracle process đang chạy” không đủ để kết luận ứng dụng có thể truy cập dữ liệu. Cần kiểm tra cả instance status và database open mode.

## 2. Trạng thái NOMOUNT

NOMOUNT là giai đoạn instance đã được khởi tạo nhưng database chưa được mount.

### 2.1. Oracle làm gì trong NOMOUNT?

Khi thực hiện STARTUP NOMOUNT, Oracle thường thực hiện các công việc:

1. Xác định và đọc SPFILE hoặc PFILE.
2. Xác lập các tham số khởi tạo.
3. Cấp phát SGA.
4. Khởi động background processes.
5. Tạo instance và đưa instance vào trạng thái STARTED.
6. Chưa mở control file.

Ở thời điểm này Oracle chưa đọc control file để gắn database vào instance.

### 2.2. Điều kiện để vào NOMOUNT

Cần có:
- Oracle software và môi trường chạy hợp lệ.
- Kết nối có quyền khởi động instance, thường là SYSDBA hoặc quyền quản trị tương ứng.
- SPFILE/PFILE hợp lệ và có thể đọc.
- Các tham số khởi tạo đủ hợp lệ.
- Tài nguyên hệ điều hành cần thiết như bộ nhớ, process và quyền truy cập thư mục.

Control file chưa cần được mở ở giai đoạn NOMOUNT. Tuy nhiên, tham số CONTROL_FILES thường đã được khai báo trong parameter file để Oracle biết vị trí control file khi chuyển sang MOUNT.

### 2.3. Khởi động NOMOUNT

Nếu Oracle tìm được SPFILE mặc định:

~~~sql
STARTUP NOMOUNT;
~~~

Chỉ định PFILE cụ thể:

~~~sql
STARTUP NOMOUNT
PFILE='/u01/app/oracle/product/dbhome_1/dbs/initORCL.ora';
~~~

Đường dẫn chỉ là ví dụ. Trên Windows hoặc môi trường khác, đường dẫn và tên file sẽ khác.

Nếu cần xác định SPFILE đang dùng sau khi instance khởi động:

~~~sql
SHOW PARAMETER spfile;
SHOW PARAMETER control_files;
~~~

Nếu SPFILE rỗng, instance có thể được khởi động từ PFILE hoặc từ cơ chế cấu hình khác. Kiểm tra nguồn tham số trong môi trường thực tế.

### 2.4. Công việc thường cần NOMOUNT

NOMOUNT phù hợp cho các tác vụ cần instance nhưng chưa cần control file:

- Tạo database mới bằng CREATE DATABASE.
- Tạo hoặc dựng lại control file bằng quy trình quản trị phù hợp.
- Một số bước chuẩn bị restore/recovery khi database chưa thể mount.
- Kiểm tra tham số và tài nguyên instance.
- Khởi tạo instance trước khi chuyển sang MOUNT.

Ví dụ, CREATE DATABASE được thực hiện khi instance ở NOMOUNT:

~~~sql
CREATE DATABASE demo
    USER SYS IDENTIFIED BY "ExampleSysPassword"
    USER SYSTEM IDENTIFIED BY "ExampleSystemPassword"
    LOGFILE GROUP 1 ('/u02/oradata/demo/redo01.log') SIZE 100M
    DATAFILE '/u02/oradata/demo/system01.dbf' SIZE 700M
    SYSAUX DATAFILE '/u02/oradata/demo/sysaux01.dbf' SIZE 500M
    DEFAULT TEMPORARY TABLESPACE temp
        TEMPFILE '/u02/oradata/demo/temp01.dbf' SIZE 100M
    UNDO TABLESPACE undotbs1
        DATAFILE '/u02/oradata/demo/undo01.dbf' SIZE 200M;
~~~

Đây là ví dụ minh họa rút gọn. Tạo database thật cần lập kế hoạch về character set, block size, redo groups, undo, temp, datafile layout, password file, archive mode và các tùy chọn bảo mật. Không chạy lệnh tạo database trên hệ thống đang có dữ liệu.

### 2.5. Điều chưa làm được ở NOMOUNT

Ở NOMOUNT:
- Database chưa được mount.
- Control file chưa mở.
- Không thể truy vấn metadata database cần control file như thể database đã mount.
- Không thể mở datafile để truy cập bảng bình thường.
- Không thể phục vụ workload SQL thông thường.

Ví dụ, V$INSTANCE có thể cho biết instance đang STARTED:

~~~sql
SELECT instance_name,
       status,
       database_status
FROM v$instance;
~~~

V$DATABASE cần database được mount. Truy vấn view này khi đang NOMOUNT có thể phát sinh lỗi vì database chưa được mount.

## 3. Trạng thái MOUNT

MOUNT là giai đoạn instance đã chạy và control file của database đã được mở.

### 3.1. Oracle làm gì khi MOUNT?

Khi chuyển từ NOMOUNT sang MOUNT, Oracle:
1. Đọc tham số CONTROL_FILES.
2. Mở control file được cấu hình.
3. Kiểm tra thông tin nhận diện và cấu trúc database trong control file.
4. Gắn database vào instance.
5. Đưa instance sang trạng thái MOUNTED.

Ở giai đoạn này, Oracle biết cấu trúc database, các datafile và redo log được ghi trong control file. Tuy nhiên, datafile chưa được mở để truy cập dữ liệu theo chế độ OPEN.

### 3.2. Điều kiện để MOUNT

Cần:
- Instance đã khởi tạo thành công.
- CONTROL_FILES được cấu hình đúng.
- Các control file cần thiết có thể được mở.
- Control file phù hợp với database cần mount.
- Quyền quản trị phù hợp.

Nếu control file bị thiếu, sai đường dẫn hoặc hỏng, database có thể không mount được. Không tự tạo control file rỗng để thay thế; phải phục hồi hoặc dựng lại theo đúng backup và quy trình recovery.

### 3.3. Chuyển NOMOUNT sang MOUNT

Khi instance đang NOMOUNT:

~~~sql
ALTER DATABASE MOUNT;
~~~

Hoặc khởi động thẳng tới MOUNT từ trạng thái shutdown:

~~~sql
STARTUP MOUNT;
~~~

STARTUP MOUNT sẽ khởi tạo instance rồi mount database. Không cần tự chạy STARTUP NOMOUNT trước nếu instance đang shutdown.

### 3.4. Công việc thường cần MOUNT

MOUNT phù hợp cho các thao tác quản trị cần control file nhưng chưa cần mở database cho user:

- Media recovery.
- Restore/recover database bằng RMAN theo quy trình phù hợp.
- Bật hoặc tắt ARCHIVELOG.
- Một số thao tác quản trị datafile, tablespace hoặc redo log.
- Đổi tên hoặc xử lý đường dẫn file theo quy trình được hỗ trợ.
- Mở database READ ONLY sau khi mount.
- Kiểm tra metadata database trong control file.

Ví dụ bật ARCHIVELOG:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;
~~~

Chỉ thực hiện khi đã chuẩn bị archive destination, dung lượng, chính sách backup và quy trình vận hành. ARCHIVELOG là quyết định cấu hình có ảnh hưởng tới lưu trữ và recovery; không bật tùy tiện trên production mà chưa có kế hoạch.

### 3.5. Điều chưa làm được ở MOUNT

Ở MOUNT:
- Control file đã mở.
- Datafile chưa được mở cho hoạt động database bình thường.
- User chưa thể truy cập các bảng như khi OPEN.
- Các truy vấn cần data dictionary đầy đủ có thể không thực hiện được.
- Database chưa sẵn sàng cho ứng dụng.

Một số view instance vẫn truy cập được; view cần database open có thể bị giới hạn. Luôn phân biệt trạng thái instance với open mode của database.

## 4. Trạng thái OPEN

OPEN là trạng thái database đã được mở để sử dụng theo open mode được chọn.

### 4.1. Oracle làm gì khi OPEN?

Khi chuyển từ MOUNT sang OPEN, Oracle thực hiện các bước cần thiết để mở database, bao gồm:
1. Mở các datafile cần thiết theo cấu hình và trạng thái file.
2. Mở online redo log.
3. Kiểm tra tính nhất quán giữa control file, datafile và redo.
4. Thực hiện instance recovery nếu database cần phục hồi sau sự cố instance.
5. Đưa database vào open mode được yêu cầu.

Các chi tiết nội bộ có thể khác theo loại database, role, cấu hình và trạng thái recovery. Nếu file cần thiết không sẵn sàng hoặc yêu cầu media recovery chưa hoàn tất, OPEN có thể thất bại.

### 4.2. Khởi động trực tiếp tới OPEN

Lệnh thông thường:

~~~sql
STARTUP;
~~~

Tương đương ý định mở database theo chế độ mặc định, thường là READ WRITE với primary database:

~~~sql
STARTUP OPEN;
~~~

Nếu instance đang MOUNT:

~~~sql
ALTER DATABASE OPEN;
~~~

### 4.3. Điều kiện để OPEN

Cần:
- Database đã MOUNT.
- Control file hợp lệ.
- Các datafile bắt buộc có thể được mở hoặc được xử lý theo trạng thái offline/recovery được hỗ trợ.
- Online redo log cần thiết sẵn sàng.
- Không còn yêu cầu recovery chưa được xử lý.
- Database role và open mode cho phép thao tác.
- Các điều kiện về resetlogs/noresetlogs phù hợp với lịch sử recovery.

Nếu một datafile cần media recovery, Oracle có thể từ chối OPEN và yêu cầu phục hồi file hoặc database. Không lặp lại ALTER DATABASE OPEN với hy vọng lỗi tự biến mất.

### 4.4. OPEN READ WRITE

READ WRITE cho phép thực hiện các thao tác đọc/ghi bình thường theo quyền và trạng thái object:

~~~sql
ALTER DATABASE OPEN READ WRITE;
~~~

Với primary database thông thường, OPEN READ WRITE là open mode mặc định khi chạy STARTUP không chỉ định READ ONLY.

### 4.5. OPEN READ ONLY

READ ONLY mở database cho truy vấn đọc, không cho phép DML thông thường lên dữ liệu database:

~~~sql
STARTUP MOUNT;
ALTER DATABASE OPEN READ ONLY;
~~~

Hoặc trên một instance đang MOUNT:

~~~sql
ALTER DATABASE OPEN READ ONLY;
~~~

READ ONLY có ích cho:
- Báo cáo.
- Truy vấn phân tích.
- Một số hoạt động kiểm tra hoặc tra cứu.
- Các cấu hình standby/read-only được hỗ trợ.

READ ONLY không có nghĩa mọi thao tác trong database đều bất khả thi; một số hoạt động quản trị hoặc thao tác tạm thời vẫn có quy tắc riêng. Hãy hiểu giới hạn của open mode thay vì coi đây là một sandbox hoàn toàn bất biến.

### 4.6. OPEN RESTRICTED

Restricted session là chế độ giới hạn người được kết nối, không phải một trạng thái NOMOUNT/MOUNT/OPEN mới.

Khởi động restricted:

~~~sql
STARTUP RESTRICT;
~~~

Hoặc bật khi database đã mở:

~~~sql
ALTER SYSTEM ENABLE RESTRICTED SESSION;
~~~

Chỉ user có quyền RESTRICTED SESSION mới có thể kết nối trong chế độ này. Dùng cho bảo trì, migration hoặc công việc cần ngăn user thông thường đăng nhập.

Tắt restricted session:

~~~sql
ALTER SYSTEM DISABLE RESTRICTED SESSION;
~~~

Restricted session không thay thế backup, maintenance window hoặc kiểm soát connection pool. Một số background job/service có thể tiếp tục hoạt động tùy cấu hình.

## 5. So sánh NOMOUNT, MOUNT và OPEN

| Tiêu chí | NOMOUNT | MOUNT | OPEN |
| --- | --- | --- | --- |
| Instance đã chạy | Có | Có | Có |
| SGA/background processes | Đã khởi tạo | Đang chạy | Đang chạy |
| Control file | Chưa mở | Đã mở | Đã mở |
| Datafile | Chưa mở cho database | Chưa mở bình thường | Được mở theo trạng thái database |
| Online redo log | Chưa mở cho hoạt động database | Chưa mở bình thường | Được mở theo trạng thái database |
| Truy cập dữ liệu bảng bình thường | Không | Không | Có, theo open mode/quyền |
| CREATE DATABASE | Có thể thực hiện | Không phải giai đoạn phù hợp | Không |
| Media recovery | Một số bước chuẩn bị | Nhiều thao tác recovery cần MOUNT | Một số loại recovery online có thể cần OPEN |
| ARCHIVELOG mode change | Không | Thường cần MOUNT | Không trực tiếp khi đang OPEN |
| Ứng dụng hoạt động bình thường | Không | Không | Có nếu READ WRITE và dịch vụ sẵn sàng |

### 5.1. Nhớ theo ba câu hỏi

- **NOMOUNT**: instance đã được tạo chưa?
- **MOUNT**: control file đã được mở và database đã được gắn chưa?
- **OPEN**: datafile/redo đã được mở để database phục vụ hoạt động chưa?

Đây là cách ghi nhớ ngắn gọn khi đọc alert log hoặc xử lý sự cố startup.

## 6. Các lệnh chuyển trạng thái

### 6.1. Từ SHUTDOWN tới NOMOUNT

~~~sql
STARTUP NOMOUNT;
~~~

Oracle đọc parameter file, tạo instance và dừng ở trạng thái NOMOUNT.

### 6.2. Từ NOMOUNT tới MOUNT

~~~sql
ALTER DATABASE MOUNT;
~~~

Oracle mở control file và gắn database.

### 6.3. Từ MOUNT tới OPEN

~~~sql
ALTER DATABASE OPEN;
~~~

Oracle mở database theo open mode mặc định phù hợp với role và trạng thái database.

### 6.4. Đi thẳng từ SHUTDOWN tới MOUNT

~~~sql
STARTUP MOUNT;
~~~

SQL*Plus thực hiện các bước khởi tạo instance rồi mount database.

### 6.5. Đi thẳng từ SHUTDOWN tới OPEN

~~~sql
STARTUP;
~~~

Đây là lệnh thường dùng khi khởi động database phục vụ ứng dụng.

### 6.6. Từ OPEN trở về MOUNT

Không dùng ALTER DATABASE MOUNT khi database đang OPEN. Cần đóng database và shutdown instance rồi khởi động lại ở MOUNT:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

Nếu chỉ cần thay đổi READ WRITE/READ ONLY, hãy lập kế hoạch chuyển trạng thái qua MOUNT theo yêu cầu của Oracle và role database.

### 6.7. Không chạy STARTUP lặp trên instance đang hoạt động

Nếu instance đã chạy, STARTUP có thể trả lỗi cho biết instance đã khởi động. Kiểm tra trạng thái trước khi chạy lệnh. Dùng ALTER DATABASE MOUNT/OPEN cho chuyển trạng thái hợp lệ từ trạng thái hiện tại.

## 7. Kiểm tra trạng thái instance và database

Không dựa vào một dòng “Connected” hoặc một process còn tồn tại để kết luận database OPEN.

### 7.1. Kiểm tra instance

~~~sql
SELECT instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM v$instance;
~~~

Các trạng thái thường gặp của V$INSTANCE.STATUS:
- STARTED: instance đã khởi động, tương ứng NOMOUNT.
- MOUNTED: database đã mount.
- OPEN: database đã open.
- OPEN MIGRATE: database mở trong chế độ migration/upgrade tương ứng.

Cột DATABASE_STATUS cung cấp thông tin trạng thái database ở góc nhìn instance. Đọc cùng STATUS và thông tin database, không dùng riêng một cột làm kết luận.

### 7.2. Kiểm tra database open mode

Khi database đã MOUNT, truy vấn:

~~~sql
SELECT name,
       dbid,
       open_mode,
       database_role,
       controlfile_type
FROM v$database;
~~~

OPEN_MODE có thể cho biết MOUNTED, READ WRITE, READ ONLY hoặc các trạng thái đặc thù như READ ONLY WITH APPLY trên cấu hình standby được hỗ trợ.

Nếu database đang NOMOUNT, V$DATABASE chưa thể được truy vấn như khi đã mount. Đây là lý do cần dùng V$INSTANCE để xác nhận instance ở giai đoạn đầu.

### 7.3. Kiểm tra tham số quan trọng

~~~sql
SHOW PARAMETER spfile;
SHOW PARAMETER control_files;
SHOW PARAMETER db_name;
SHOW PARAMETER db_unique_name;
SHOW PARAMETER compatible;
~~~

Các tham số giúp xác nhận instance đang dùng cấu hình nào và control file nằm ở đâu. Không tự sửa tham số trên production nếu chưa có change plan và backup cấu hình.

### 7.4. Kiểm tra datafile và redo log khi đã MOUNT/OPEN

~~~sql
SELECT file#, name, status
FROM v$datafile
ORDER BY file#;
~~~

~~~sql
SELECT group#, member, status
FROM v$logfile
ORDER BY group#, member;
~~~

~~~sql
SELECT group#, sequence#, status, archived
FROM v$log
ORDER BY group#;
~~~

Các view và cột phản ánh trạng thái file/redo; cách diễn giải phụ thuộc database open/mount state và loại file. Kiểm tra cả alert log khi có file không sẵn sàng hoặc recovery.

## 8. Điều kiện và lỗi thường gặp ở NOMOUNT

NOMOUNT chủ yếu phụ thuộc parameter file, tài nguyên instance và môi trường hệ điều hành.

### 8.1. Không tìm thấy PFILE/SPFILE

Lỗi có thể gồm:
- ORA-01078: failure in processing system parameters.
- LRM-00109: could not open parameter file.

Kiểm tra:
1. ORACLE_SID.
2. ORACLE_HOME.
3. Đường dẫn SPFILE/PFILE.
4. Quyền đọc file.
5. Cú pháp tham số.
6. File có bị truncate hoặc sai encoding không.

Ví dụ chỉ định rõ PFILE:

~~~sql
STARTUP NOMOUNT
PFILE='/u01/app/oracle/product/dbhome_1/dbs/initORCL.ora';
~~~

Không tạo SPFILE mới từ một file không rõ nguồn khi chưa xác minh cấu hình hiện tại.

### 8.2. Không đủ tài nguyên hệ điều hành

NOMOUNT có thể thất bại nếu:
- Không đủ memory để cấp phát SGA.
- Giới hạn process/thread không phù hợp.
- Shared memory hoặc semaphore không đủ trên nền tảng tương ứng.
- Filesystem chứa audit/diagnostic hoặc parameter file không khả dụng.
- Environment variable sai.

Kiểm tra alert log, trace file, OS log và giới hạn tài nguyên. Không chỉ tăng SGA_TARGET hoặc PROCESSES theo phỏng đoán; cần xác định lỗi thực tế.

### 8.3. Tham số không tương thích

Một tham số có thể sai kiểu, sai giá trị hoặc không phù hợp với version/COMPATIBLE. Kiểm tra lỗi LRM/ORA trong alert log và đối chiếu tài liệu phiên bản. Thay đổi từng tham số có kiểm soát, giữ bản sao PFILE/SPFILE trước khi chỉnh sửa.

## 9. Điều kiện và lỗi thường gặp ở MOUNT

MOUNT cần mở control file được khai báo trong CONTROL_FILES.

### 9.1. Control file không tồn tại hoặc không truy cập được

Các lỗi thường thấy có thể gồm ORA-00205, ORA-00210 hoặc thông báo liên quan tới control file. Nguyên nhân có thể là:
- Sai đường dẫn CONTROL_FILES.
- Filesystem/ASM disk group chưa mount.
- File bị xóa hoặc rename.
- Quyền truy cập không đúng.
- Storage không sẵn sàng.
- Control file hỏng hoặc không đồng bộ.

Kiểm tra:
- SHOW PARAMETER control_files.
- Alert log.
- Trạng thái ASM/disk group hoặc filesystem.
- Backup control file và bản sao multiplexed nếu có.

Không copy một control file cũ tùy tiện vào vị trí production. Control file lưu thông tin cấu trúc và recovery; cần restore/recreate đúng quy trình.

### 9.2. Control file không phù hợp database

Control file có thể thuộc database khác hoặc không khớp với datafile/redo log. Xác nhận DBID, DB_NAME, DB_UNIQUE_NAME và nguồn backup trước khi mount/open. Không cố vượt qua mismatch bằng cách đổi tham số để ép database mở.

### 9.3. MOUNT thành công nhưng datafile bị thiếu

MOUNT thành công không chứng minh tất cả datafile đã sẵn sàng. Control file có thể mở được trong khi một datafile không có mặt hoặc cần recovery. Các vấn đề này thường được phát hiện khi OPEN hoặc trong quy trình recovery.

## 10. Điều kiện và lỗi thường gặp ở OPEN

OPEN cần file và recovery state phù hợp.

### 10.1. Datafile cần media recovery

Một lỗi phổ biến là:
- ORA-01113: file needs media recovery.
- ORA-01110: data file identification.

Điều này có nghĩa datafile cần được recovery theo đúng backup/redo trước khi mở. Không coi OPEN là lệnh sửa lỗi. Xác định file, kiểm tra backup và archived redo, rồi dùng RMAN hoặc quy trình recovery đã được DBA phê duyệt.

Ví dụ minh họa trong môi trường phù hợp:

~~~sql
RECOVER DATABASE;
ALTER DATABASE OPEN;
~~~

Trong production, ưu tiên RMAN và quy trình recovery được thiết kế cho database/role cụ thể. Không chạy RECOVER DATABASE một cách mù quáng nếu chưa biết trạng thái control file, backup và redo.

### 10.2. Thiếu online redo log

Nếu online redo log cần thiết không sẵn sàng hoặc bị hỏng, database có thể không mở được hoặc cần recovery đặc biệt. Kiểm tra V$LOG, V$LOGFILE và alert log. Không xóa redo log file thủ công khi database đang sử dụng.

### 10.3. Instance recovery sau crash

Nếu instance bị crash hoặc shutdown abort, Oracle thường thực hiện instance recovery khi mở database bằng online redo để đưa datafile về trạng thái transaction-consistent.

Instance recovery khác media recovery:
- Instance recovery thường được Oracle tự thực hiện khi startup sau sự cố instance.
- Media recovery cần phục hồi file bị mất/hỏng từ backup và áp dụng redo thích hợp.

Không nhầm một database đang crash-recovery với database cần restore datafile.

### 10.4. OPEN bị từ chối vì database chưa MOUNT

Nếu chạy ALTER DATABASE OPEN khi instance đang NOMOUNT, trước hết cần:

~~~sql
ALTER DATABASE MOUNT;
ALTER DATABASE OPEN;
~~~

Nếu lỗi nằm ở control file, datafile hoặc recovery, xử lý nguyên nhân tương ứng thay vì lặp lại OPEN.

## 11. OPEN RESETLOGS và NORESETLOGS

RESETLOGS là một thao tác recovery quan trọng, không phải tùy chọn “thử mở database” thông thường.

### 11.1. Khi nào cần RESETLOGS?

Một số tình huống recovery yêu cầu OPEN RESETLOGS, thường gồm:
- Incomplete recovery tới một thời điểm/SCN/log trước hiện tại.
- Recovery sử dụng backup control file trong các tình huống yêu cầu resetlogs.
- Quy trình recovery tạo ra một database incarnation mới.

Ví dụ hình thức lệnh:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

Chỉ chạy sau khi recovery hoàn tất và Oracle yêu cầu hoặc quy trình recovery chỉ định. RESETLOGS tạo một incarnation mới và khởi tạo lại online redo log sequence theo semantics Oracle.

### 11.2. NORESETLOGS

~~~sql
ALTER DATABASE OPEN NORESETLOGS;
~~~

NORESETLOGS dùng trong các tình huống complete recovery phù hợp, với current control file và điều kiện recovery cho phép. Không phải lúc nào cũng cần chỉ rõ NORESETLOGS; OPEN bình thường thường đủ nếu điều kiện mặc định đáp ứng.

### 11.3. Vì sao không dùng RESETLOGS để chữa mọi lỗi OPEN?

RESETLOGS thay đổi lịch sử incarnation và ảnh hưởng tới chiến lược backup/recovery. Nếu chạy sai thời điểm, có thể làm phức tạp việc dùng backup và archived redo cũ. Sau RESETLOGS cần thực hiện backup phù hợp theo chính sách DBA.

Luôn kiểm tra:
- Recovery đã hoàn tất chưa?
- Control file là current hay backup?
- Có phải incomplete recovery không?
- Oracle yêu cầu RESETLOGS hay NORESETLOGS?
- Kế hoạch backup sau khi mở là gì?

## 12. Trình tự startup trong các tình huống vận hành

### 12.1. Khởi động database bình thường

~~~sql
STARTUP;
~~~

Sau đó xác nhận:

~~~sql
SELECT status FROM v$instance;
SELECT open_mode, database_role FROM v$database;
~~~

Kỳ vọng instance OPEN và primary database READ WRITE nếu đây là primary thông thường.

### 12.2. Chỉ cần instance NOMOUNT

~~~sql
STARTUP NOMOUNT;
~~~

Dùng khi chuẩn bị CREATE DATABASE, xử lý parameter hoặc bước recovery cần instance chưa mount. Không để instance NOMOUNT lâu trên môi trường ứng dụng vì database chưa phục vụ truy cập dữ liệu.

### 12.3. Khởi động để recovery ở MOUNT

~~~sql
STARTUP MOUNT;
~~~

Sau khi hoàn tất thao tác recovery/maintenance và xác nhận điều kiện:

~~~sql
ALTER DATABASE OPEN;
~~~

Nếu recovery yêu cầu RESETLOGS, chỉ dùng lệnh đó theo quy trình recovery.

### 12.4. Mở READ ONLY

~~~sql
STARTUP MOUNT;
ALTER DATABASE OPEN READ ONLY;
~~~

Nếu database đã OPEN READ WRITE, không thể đổi mode bằng cách gọi STARTUP MOUNT trên instance đang chạy. Lập kế hoạch shutdown và khởi động lại ở MOUNT rồi OPEN READ ONLY, cân nhắc ảnh hưởng tới session và dịch vụ.

### 12.5. Bảo trì trong restricted session

~~~sql
STARTUP RESTRICT;
~~~

Hoặc khi database đã OPEN:

~~~sql
ALTER SYSTEM ENABLE RESTRICTED SESSION;
-- Thực hiện công việc bảo trì.
ALTER SYSTEM DISABLE RESTRICTED SESSION;
~~~

Kiểm tra user ứng dụng và job nền trước khi mở lại quyền truy cập bình thường.

## 13. Shutdown và quan hệ với startup state

Shutdown đưa instance và database qua các bước đóng, dismount và dừng process. Chế độ shutdown ảnh hưởng tới công việc đang chạy và recovery ở lần startup kế tiếp.

### 13.1. SHUTDOWN NORMAL

Chờ user disconnect. Có thể chờ lâu nếu session còn mở.

### 13.2. SHUTDOWN TRANSACTIONAL

Chờ transaction đang hoạt động kết thúc, sau đó đóng database theo semantics của lệnh.

### 13.3. SHUTDOWN IMMEDIATE

Ngắt các session theo quy trình shutdown, rollback transaction chưa commit và đóng database có kiểm soát. Đây là lựa chọn thường dùng cho maintenance khi cần shutdown chủ động.

~~~sql
SHUTDOWN IMMEDIATE;
~~~

### 13.4. SHUTDOWN ABORT

Dừng instance ngay mà không thực hiện quy trình đóng bình thường:

~~~sql
SHUTDOWN ABORT;
~~~

Lần startup tiếp theo có thể cần instance recovery. Chỉ dùng khi các phương thức shutdown có kiểm soát không khả thi hoặc theo chỉ dẫn xử lý sự cố. Không dùng ABORT như cách shutdown mặc định.

### 13.5. Sau shutdown, startup lại ở trạng thái cần thiết

| Mục tiêu tiếp theo | Lệnh |
| --- | --- |
| Phục vụ ứng dụng bình thường | STARTUP |
| Chuẩn bị tạo database | STARTUP NOMOUNT |
| Recovery/maintenance cần control file | STARTUP MOUNT |
| Mở chỉ đọc | STARTUP MOUNT rồi ALTER DATABASE OPEN READ ONLY |

## 14. CDB và PDB trong kiến trúc multitenant

Trong Oracle multitenant, CDB và PDB có vòng đời mở riêng.

### 14.1. CDB OPEN không đồng nghĩa mọi PDB OPEN

CDB root có thể OPEN trong khi một hoặc nhiều PDB vẫn MOUNTED. Vì vậy, xác nhận V$DATABASE.OPEN_MODE của CDB chưa đủ để kết luận ứng dụng trong mọi PDB đã sẵn sàng.

Kiểm tra PDB:

~~~sql
SHOW PDBS;
~~~

Hoặc:

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
~~~

### 14.2. Mở PDB

Khi CDB đã OPEN:

~~~sql
ALTER PLUGGABLE DATABASE apppdb OPEN;
~~~

Mở tất cả PDB được phép:

~~~sql
ALTER PLUGGABLE DATABASE ALL OPEN;
~~~

Chỉ mở các PDB cần thiết theo kế hoạch vận hành và role. Một số PDB có thể được cấu hình để mở READ ONLY hoặc restricted theo yêu cầu.

### 14.3. Lưu trạng thái PDB qua lần startup

Có thể lưu open state của PDB:

~~~sql
ALTER PLUGGABLE DATABASE apppdb SAVE STATE;
~~~

Lệnh này giúp Oracle khôi phục trạng thái PDB đã lưu trong lần CDB startup tiếp theo theo cơ chế hỗ trợ của phiên bản. Kiểm tra PDB saved state và chính sách startup của hệ thống trước khi dùng.

### 14.4. Kiểm tra đúng container

Khi làm việc với PDB, kiểm tra CON_NAME:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Không nhầm thao tác trên CDB root với thao tác trên một PDB. Một lệnh startup/mount/open database thường điều khiển CDB ở cấp database; PDB được mở/đóng bằng ALTER PLUGGABLE DATABASE.

## 15. Oracle RAC và Data Guard

Trạng thái startup trong môi trường HA có thêm yếu tố instance, role và cluster coordination.

### 15.1. RAC: database có nhiều instance

Trong RAC, nhiều instance có thể cùng mount/open một database. Mỗi instance có trạng thái riêng, trong khi database là tài nguyên chung.

Kiểm tra:

~~~sql
SELECT inst_id,
       instance_name,
       status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
~~~

Một instance có thể OPEN trong khi instance khác đang STARTED/MOUNTED hoặc chưa chạy. Không chỉ nhìn một instance để kết luận trạng thái toàn cluster.

Trong môi trường Oracle Restart/RAC do Clusterware quản lý, dùng SRVCTL hoặc công cụ cluster được chuẩn hóa để start/stop database và instance. Tránh khởi động thủ công bằng SQL*Plus nếu việc đó làm lệch trạng thái resource của Clusterware. Cú pháp SRVCTL có thể khác theo release; kiểm tra help/tài liệu đúng phiên bản.

### 15.2. Data Guard physical standby

Physical standby thường được mount để áp dụng redo. Tùy cấu hình và license, standby có thể mở READ ONLY trong khi redo apply hoạt động thông qua Active Data Guard.

Kiểm tra role và open mode:

~~~sql
SELECT database_role,
       open_mode,
       switchover_status
FROM v$database;
~~~

Không áp dụng quy trình OPEN READ WRITE của primary lên physical standby. Role database quyết định open mode nào hợp lệ.

### 15.3. Không suy luận role chỉ từ OPEN_MODE

READ ONLY có thể là reporting database, standby hoặc một trạng thái vận hành đặc thù. Hãy xem DATABASE_ROLE cùng OPEN_MODE. Trong Data Guard, việc mở READ WRITE trên standby có thể yêu cầu quy trình activation/failover và thay đổi role; không thử như thao tác mở bình thường.

## 16. Alert log và chẩn đoán startup

Alert log là nguồn quan trọng để hiểu Oracle đã đi tới giai đoạn nào và vì sao startup thất bại.

### 16.1. Tìm alert log

Có thể xem vị trí diagnostic bằng ADR:

~~~sql
SELECT name, value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Diag Alert', 'Default Trace File');
~~~

Tùy phiên bản, có thể dùng ADRCI để xem alert log:

~~~text
adrci
show homes
set homepath <ADR_HOME>
show alert -tail 100
~~~

Tên ADR home là giá trị thực tế của môi trường, không dùng nguyên placeholder.

### 16.2. Đọc theo trình tự

Khi startup:
1. Kiểm tra lỗi đọc parameter file.
2. Xác nhận instance tạo SGA và background process.
3. Tìm thông báo mở control file.
4. Xác nhận database mounted.
5. Tìm thông báo mở datafile và redo log.
6. Kiểm tra recovery bắt đầu/kết thúc.
7. Xác nhận database open và open mode.
8. Nếu lỗi, đọc các ORA- phía trước lỗi cuối cùng để tìm nguyên nhân gốc.

Không chỉ lấy ORA cuối cùng từ client. Alert log thường có thêm file path, process, checkpoint và recovery detail.

### 16.3. Chẩn đoán theo giai đoạn

| Giai đoạn thất bại | Nhóm nguyên nhân nên kiểm tra |
| --- | --- |
| NOMOUNT | PFILE/SPFILE, tham số, memory, OS process/shared memory |
| MOUNT | CONTROL_FILES, storage, quyền file, control file consistency |
| OPEN | Datafile, online redo, checkpoint, recovery, database role |
| PDB OPEN | PDB file, PDB state, plugin compatibility, service/configuration |
| RAC instance start | Clusterware resource, ASM, network, instance-specific configuration |

## 17. An toàn vận hành khi thay đổi startup state

Startup và open mode là thao tác quản trị ảnh hưởng trực tiếp tới khả năng phục vụ ứng dụng.

Trước khi thực hiện:
- Xác định DB_NAME và DB_UNIQUE_NAME.
- Xác định primary/standby role.
- Xác định instance và host đang điều khiển.
- Kiểm tra có backup và recovery plan phù hợp.
- Kiểm tra control file, datafile, redo log và ASM/filesystem.
- Xác định ứng dụng/session nào bị ảnh hưởng.
- Kiểm tra PDB và service cần mở.
- Đọc alert log và ghi nhận trạng thái hiện tại.
- Thực hiện change trong maintenance window nếu có downtime.
- Xác nhận trạng thái sau mỗi transition.

Không chạy các lệnh có thể thay đổi incarnation, recreate control file hoặc bỏ qua recovery nếu chưa hiểu hậu quả. Không xóa file database bằng lệnh OS để “dọn lỗi” khi Oracle còn quản lý file đó.

## 18. Quy trình quyết định trạng thái cần dùng

Có thể chọn trạng thái theo mục tiêu:

~~~text
Mục tiêu là gì?
  |
  +-- Tạo database / chuẩn bị control file?
  |       |
  |       +-- STARTUP NOMOUNT
  |
  +-- Recovery / thay đổi ARCHIVELOG / thao tác control file?
  |       |
  |       +-- STARTUP MOUNT
  |
  +-- Ứng dụng cần đọc/ghi bình thường?
  |       |
  |       +-- STARTUP hoặc ALTER DATABASE OPEN READ WRITE
  |
  +-- Báo cáo chỉ đọc?
  |       |
  |       +-- MOUNT rồi OPEN READ ONLY
  |
  +-- Bảo trì, giới hạn user?
          |
          +-- OPEN RESTRICTED
~~~

Sơ đồ là hướng dẫn lựa chọn ban đầu. Các workflow Data Guard, RAC, recovery và upgrade có điều kiện riêng; luôn kiểm tra role, phiên bản và trạng thái file trước khi chạy lệnh.

## 19. Ví dụ thực hành tổng hợp: khởi động theo từng giai đoạn

### 19.1. Kết nối với quyền quản trị

Trên máy database, ví dụ:

~~~text
sqlplus / as sysdba
~~~

Kết nối OS authentication phụ thuộc cấu hình hệ điều hành và nhóm OSDBA. Kết nối remote có thể cần password file và cấu hình mạng phù hợp.

### 19.2. Khởi động NOMOUNT

~~~sql
STARTUP NOMOUNT;
~~~

Kiểm tra:

~~~sql
SELECT instance_name, status, startup_time
FROM v$instance;
~~~

Kỳ vọng STATUS là STARTED.

### 19.3. Chuyển sang MOUNT

~~~sql
ALTER DATABASE MOUNT;
~~~

Kiểm tra:

~~~sql
SELECT instance_name, status
FROM v$instance;

SELECT name, open_mode, database_role
FROM v$database;
~~~

Kỳ vọng V$INSTANCE.STATUS là MOUNTED và V$DATABASE.OPEN_MODE là MOUNTED.

### 19.4. Chuyển sang OPEN

~~~sql
ALTER DATABASE OPEN;
~~~

Kiểm tra:

~~~sql
SELECT instance_name, status
FROM v$instance;

SELECT name, open_mode, database_role
FROM v$database;
~~~

Với primary database thông thường, kỳ vọng STATUS là OPEN và OPEN_MODE là READ WRITE.

### 19.5. Đọc alert log và kiểm tra ứng dụng

Sau khi mở:
- Kiểm tra alert log không có lỗi startup/recovery chưa xử lý.
- Kiểm tra tablespace/datafile và PDB.
- Kiểm tra service đã đăng ký và listener có thể định tuyến kết nối.
- Thực hiện health check ứng dụng.
- Xác nhận user có quyền và object cần thiết ở trạng thái hợp lệ.

Database OPEN chưa đảm bảo mọi ứng dụng hoạt động; service, PDB, listener, job, credential và dependency bên ngoài cũng phải sẵn sàng.

## 20. Những nhầm lẫn thường gặp

**NOMOUNT nghĩa là database đã mở nhưng chưa có user.** Không đúng. Instance đã chạy nhưng control file chưa được mở và database chưa mount.

**MOUNT nghĩa là datafile đã sẵn sàng cho SELECT.** Không đúng. Control file đã mở; database chưa OPEN để truy cập dữ liệu bình thường.

**OPEN chỉ là một tên khác của MOUNT.** Không đúng. OPEN mở datafile/online redo và đưa database vào open mode.

**Instance chạy nghĩa là ứng dụng kết nối được.** Không đúng. Instance có thể chỉ ở NOMOUNT hoặc MOUNT.

**STARTUP MOUNT cần chạy STARTUP NOMOUNT trước.** Không cần. STARTUP MOUNT tự khởi tạo instance rồi mount database nếu đang shutdown.

**Có thể ALTER DATABASE MOUNT khi database đang OPEN.** Không theo luồng chuyển trạng thái thông thường. Cần shutdown rồi startup ở MOUNT.

**V$DATABASE luôn truy vấn được ở NOMOUNT.** Không đúng. Database chưa được mount nên view cần database metadata có thể không truy cập được.

**MOUNT thành công nghĩa là mọi datafile đều tốt.** Không đúng. Control file đã mở; lỗi datafile có thể chỉ xuất hiện khi OPEN hoặc recovery.

**OPEN READ ONLY giống restricted session.** Không đúng. READ ONLY giới hạn ghi dữ liệu; restricted session giới hạn người được đăng nhập.

**RESETLOGS là cách thử lại OPEN khi gặp lỗi.** Không đúng. RESETLOGS thuộc quy trình recovery và tạo incarnation mới.

**Instance recovery và media recovery là một.** Không đúng. Instance recovery thường tự chạy sau crash; media recovery cần phục hồi file từ backup và áp dụng redo.

**CDB OPEN nghĩa là mọi PDB OPEN.** Không đúng. Kiểm tra V$PDBS hoặc SHOW PDBS.

**OPEN READ WRITE luôn đúng cho mọi database role.** Không đúng. Physical standby và các role khác có quy tắc riêng.

**RAC chỉ cần kiểm tra một instance.** Không đúng. Mỗi instance có trạng thái riêng; kiểm tra GV$INSTANCE và trạng thái Clusterware.

**Alert log chỉ có lỗi, không có thông tin startup.** Không đúng. Alert log ghi các sự kiện startup, mount, open, recovery và thông tin chẩn đoán.

## 21. Bài tập tự luyện

1. Phân biệt instance và database trong Oracle.
2. Nêu các thành phần chính của instance.
3. Control file chứa những loại metadata nào?
4. Giải thích điều gì xảy ra khi STARTUP NOMOUNT.
5. Vì sao NOMOUNT chưa thể truy cập bảng?
6. Nêu hai công việc quản trị phù hợp với NOMOUNT.
7. Khởi động instance bằng PFILE chỉ định đường dẫn.
8. Giải thích vai trò của CONTROL_FILES.
9. Mô tả những bước Oracle thực hiện khi MOUNT.
10. Viết lệnh chuyển NOMOUNT sang MOUNT.
11. Vì sao MOUNT chưa sẵn sàng cho ứng dụng?
12. Nêu các công việc thường cần database ở MOUNT.
13. Viết trình tự bật ARCHIVELOG an toàn ở mức khái niệm.
14. Mô tả các bước chính khi OPEN.
15. Phân biệt OPEN READ WRITE và OPEN READ ONLY.
16. Restricted session khác READ ONLY ở điểm nào?
17. Viết lệnh mở và tắt restricted session.
18. Dùng V$INSTANCE để xác nhận trạng thái.
19. Dùng V$DATABASE để xác nhận OPEN_MODE và DATABASE_ROLE.
20. Vì sao V$DATABASE có thể không truy vấn được ở NOMOUNT?
21. Nêu các nguyên nhân khiến MOUNT thất bại.
22. Phân biệt lỗi control file với lỗi datafile.
23. ORA-01113 thường gợi ý tình trạng gì?
24. Phân biệt instance recovery và media recovery.
25. Khi nào có thể cần OPEN RESETLOGS?
26. Vì sao không dùng RESETLOGS để thử mở database?
27. Giải thích vì sao CDB OPEN chưa chắc PDB OPEN.
28. Viết lệnh mở một PDB và lưu trạng thái của PDB.
29. Trong RAC, vì sao cần kiểm tra từng INST_ID?
30. Thiết kế runbook startup từ SHUTDOWN tới OPEN, gồm kiểm tra file, recovery, alert log và health check.

**NOMOUNT khởi tạo instance, MOUNT mở control file và gắn database, OPEN mở datafile/redo để database phục vụ theo open mode.** Hãy chọn trạng thái theo mục tiêu quản trị, kiểm tra identity/role và file trước khi chuyển bước, xác nhận kết quả bằng V$INSTANCE cùng V$DATABASE, và đọc alert log khi có lỗi. Đặc biệt, không dùng OPEN RESETLOGS như một cách thử lại thông thường; đó là bước có ảnh hưởng tới lịch sử recovery và phải theo đúng quy trình.

