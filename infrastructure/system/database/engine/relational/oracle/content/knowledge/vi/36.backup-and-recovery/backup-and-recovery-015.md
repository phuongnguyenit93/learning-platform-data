# RMAN DUPLICATE, tạo bản sao và tách dữ liệu nhạy cảm

RMAN DUPLICATE tạo một database khác từ database nguồn bằng cách sử dụng backup và archived redo log, hoặc truyền dữ liệu trực tiếp từ database nguồn qua Oracle Net. Bản sao có thể phục vụ kiểm thử, phát triển, phân tích, diễn tập phục hồi hoặc xây dựng physical standby cho Oracle Data Guard.

Cần phân biệt hai mục tiêu:

- **Tạo database clone độc lập**: tạo một database có danh tính riêng, có thể mở và sử dụng độc lập với database nguồn. Đây là cách thường dùng cho môi trường test, development, UAT hoặc báo cáo.
- **Tạo physical standby**: tạo một database dự phòng thuộc cấu hình Data Guard, tiếp tục dùng cùng DBID với primary và nhận redo để duy trì trạng thái đồng bộ. Đây không phải bản clone độc lập để thay đổi dữ liệu tùy ý.

RMAN DUPLICATE thực hiện sao chép vật lý. Nếu nguồn chứa dữ liệu khách hàng, thông tin định danh, bí mật ứng dụng hoặc dữ liệu được mã hóa, bản sao ban đầu cũng chứa những dữ liệu đó. DUPLICATE không tự động ẩn danh, xóa hoặc thay đổi dữ liệu nhạy cảm. Muốn dùng bản sao cho môi trường ít tin cậy hơn, cần cô lập database, kiểm soát quyền truy cập và thực hiện data masking hoặc sanitization trước khi cấp quyền cho người dùng ứng dụng.

## 1. RMAN DUPLICATE hoạt động như thế nào?

RMAN đọc các thành phần cần thiết từ database nguồn hoặc từ backup, khôi phục chúng vào auxiliary instance, áp dụng redo để đưa database đến điểm nhất quán cần thiết, sau đó hoàn tất database duplicate.

Các thành phần chính:

- **Target database**: database nguồn mà RMAN dùng làm cơ sở để tạo bản sao. Khi dùng active duplication, RMAN kết nối trực tiếp đến target.
- **Auxiliary instance**: instance đích được khởi động ở chế độ NOMOUNT để RMAN có nơi tạo database mới. Đây là instance sẽ trở thành database clone hoặc standby.
- **RMAN client**: phiên RMAN điều phối quá trình duplicate.
- **Backup và archived redo log**: dữ liệu cần thiết để tái tạo database. Chúng có thể được đọc từ backup hiện có hoặc được truyền trực tiếp từ target.
- **Oracle Net và password file**: hỗ trợ kết nối từ RMAN đến target và auxiliary, đặc biệt khi hai máy chủ khác nhau.

Luồng khái quát:

~~~text
                 Database nguồn
                  (TARGET)
                      |
          +-----------+-----------+
          |                       |
    Backup hiện có          Active duplication
          |                 qua Oracle Net
          |                       |
          +-----------+-----------+
                      |
                  RMAN client
                      |
                AUXILIARY instance
                   (NOMOUNT)
                      |
          restore / copy / recover
                      |
              Database duplicate
                      |
             kiểm soát và masking
                      |
             môi trường test/dev
~~~

RMAN tạo bản sao dựa trên một điểm dữ liệu và redo có sẵn. Nếu cần bản sao tại một thời điểm trong quá khứ, phải có backup và archived redo log đáp ứng điểm phục hồi đó. Nếu chỉ dùng active duplication, nguồn phải đáp ứng các điều kiện kết nối và trạng thái database mà phiên bản Oracle yêu cầu.

## 2. Phân biệt clone độc lập và physical standby

Đây là lựa chọn quan trọng nhất trước khi chạy DUPLICATE.

| Đặc điểm | Database clone độc lập | Physical standby |
|---|---|---|
| Mục đích | Test, development, UAT, báo cáo, phân tích | Data Guard, dự phòng và disaster recovery |
| Câu lệnh | DUPLICATE TARGET DATABASE TO ... | DUPLICATE TARGET DATABASE FOR STANDBY ... |
| DBID | RMAN tạo DBID mới cho duplicate không phải standby | Giữ DBID của primary |
| DB_UNIQUE_NAME | Phải riêng biệt với nguồn | Phải riêng biệt với primary |
| Trạng thái sau duplicate | Thường mở bằng RESETLOGS; có thể dùng NOOPEN để trì hoãn | Được giữ ở trạng thái phù hợp cho standby và tiếp tục apply redo |
| Có thể thay đổi dữ liệu độc lập? | Có, sau khi mở database và hoàn tất cấu hình | Không vận hành như một database test độc lập khi vẫn là physical standby |

### Clone độc lập

Ví dụ tạo database có tên CLONE1 từ database nguồn:

~~~rman
DUPLICATE TARGET DATABASE TO CLONE1
  FROM ACTIVE DATABASE;
~~~

Tên sau TO là tên database duplicate. RMAN tạo DBID mới cho duplicate thông thường. Clone có thể mở bằng RESETLOGS và vận hành độc lập sau khi hoàn tất cấu hình.

### Physical standby

Ví dụ tạo standby:

~~~rman
DUPLICATE TARGET DATABASE
  FOR STANDBY
  FROM ACTIVE DATABASE;
~~~

Physical standby dùng cùng DBID với primary và cần tiếp tục quy trình Data Guard, chẳng hạn cấu hình transport/apply redo, broker nếu sử dụng và các tham số liên quan. Không dùng cách này để tạo môi trường test có thể cập nhật dữ liệu độc lập.

Không nhầm DB_UNIQUE_NAME với DBID. DB_UNIQUE_NAME xác định duy nhất một database trong cấu hình Data Guard hoặc hệ thống Oracle; DBID là định danh nội bộ của database. Một clone độc lập thường có DBID mới và DB_UNIQUE_NAME riêng.

## 3. Các phương pháp tạo duplicate

### Active database duplication

Active duplication truyền dữ liệu trực tiếp từ target đến auxiliary qua Oracle Net. Không cần tạo sẵn một bộ backup đầy đủ rồi chuyển thủ công sang máy auxiliary. RMAN có thể sử dụng image copy hoặc backup set tùy cách cấu hình và tùy chọn trong lệnh.

Ví dụ:

~~~rman
CONNECT TARGET sys@PROD;
CONNECT AUXILIARY sys@CLONE1;

DUPLICATE TARGET DATABASE TO CLONE1
  FROM ACTIVE DATABASE;
~~~

Có thể yêu cầu RMAN dùng backup set cho việc truyền dữ liệu:

~~~rman
DUPLICATE TARGET DATABASE TO CLONE1
  FROM ACTIVE DATABASE
  USING BACKUPSET;
~~~

Backup set có thể giảm lượng dữ liệu truyền qua mạng khi kết hợp với compression phù hợp. Tuy nhiên, compression tăng mức sử dụng CPU; cần đo trên hệ thống thật. Active duplication vẫn cần băng thông mạng đủ lớn, kết nối ổn định và quyền truy cập phù hợp trên cả hai máy chủ.

Ưu điểm:

- Không cần chuẩn bị và chuyển toàn bộ backup trước khi bắt đầu.
- Phù hợp khi target và auxiliary có kết nối Oracle Net ổn định.
- RMAN điều phối việc truyền, restore và recover.
- Có thể dùng backup set để tối ưu lượng dữ liệu truyền.

Giới hạn và điều kiện:

- Auxiliary instance phải được khởi động ở NOMOUNT.
- RMAN cần kết nối được đến target và auxiliary với quyền SYSDBA theo yêu cầu.
- Password file và Oracle Net phải được cấu hình phù hợp.
- Nguồn và đích cần đủ tài nguyên CPU, I/O và network.
- Active duplication tạo tải đọc trên database nguồn; cần chọn thời điểm và mức song song phù hợp.

### Backup-based duplication

Backup-based duplication sử dụng backup của database nguồn đã được tạo trước đó. Backup cần được RMAN truy cập từ auxiliary host qua filesystem, ASM, shared storage hoặc media manager thích hợp. Archived redo log cần thiết cũng phải có sẵn để recover đến điểm mong muốn.

Ví dụ khi backup được đặt trong một thư mục mà auxiliary host truy cập được:

~~~rman
CONNECT AUXILIARY sys@CLONE1;

DUPLICATE DATABASE TO CLONE1
  BACKUP LOCATION '/backup/rman';
~~~

Cú pháp và các kết nối cần thiết phụ thuộc cách RMAN repository được cung cấp. Khi không kết nối target hoặc recovery catalog, có thể cần cung cấp DBID và metadata cần thiết để RMAN xác định database nguồn. Hãy bảo đảm backup location chứa đầy đủ các backup piece, control file autobackup và archived log cần thiết.

Ưu điểm:

- Hạn chế tải đọc trực tiếp trên production trong thời điểm duplicate.
- Có thể chuẩn bị backup và chuyển đến máy đích trước.
- Phù hợp với mạng chậm hoặc môi trường tách biệt với production.
- Có thể lưu giữ một bộ backup làm nguồn cho nhiều lần tạo clone.

Hạn chế:

- Cần dung lượng để lưu và chuyển backup.
- Backup và archived log phải đủ để khôi phục đến điểm cần thiết.
- Quản lý metadata, DBID, control file autobackup và vị trí piece phải chính xác.
- Thời gian tạo clone phụ thuộc dung lượng backup và tốc độ restore.

### So sánh hai phương pháp

| Tiêu chí | Active duplication | Backup-based duplication |
|---|---|---|
| Nguồn dữ liệu | Đọc trực tiếp từ target | Backup đã tạo |
| Kết nối target khi chạy | Có | Có thể không cần, tùy repository và cách chạy |
| Ảnh hưởng nguồn | Có tải đọc và truyền dữ liệu trong lúc chạy | Backup tạo trước đó; lúc duplicate chủ yếu đọc bản backup |
| Chuẩn bị trước | Oracle Net, password file, auxiliary instance | Backup, archived log và vị trí lưu có thể truy cập |
| Mạng | Cần đường truyền giữa target và auxiliary | Có thể chuyển backup trước bằng phương tiện khác |
| Tình huống phù hợp | Clone nhanh từ nguồn đang hoạt động | Clone lặp lại từ bộ backup đã chuẩn bị hoặc môi trường tách biệt |

## 4. Chuẩn bị auxiliary instance

Auxiliary instance là instance đích RMAN sử dụng để tạo database mới. Instance phải được khởi động ở NOMOUNT với initialization parameter file phù hợp.

### Chuẩn bị thư mục và dung lượng

Xác định trước:

- Vị trí datafile và tempfile.
- Vị trí control file.
- Vị trí online redo log.
- Fast Recovery Area nếu sử dụng.
- Dung lượng cho database, temporary files, archived log và backup staging.
- Quyền truy cập của Oracle software owner.
- Storage có thể truy cập từ node chạy auxiliary instance.

Không nên để file của clone ghi đè lên datafile, control file hoặc redo log của production. Nếu source và auxiliary cùng máy hoặc cùng storage, phải thiết kế tên file và đường dẫn riêng trước khi chạy.

### Tạo PFILE tối thiểu

Ví dụ PFILE cho auxiliary database CLONE1:

~~~ini
db_name='CLONE1'
db_unique_name='CLONE1'
control_files='/u02/oradata/CLONE1/control01.ctl'
db_create_file_dest='/u02/oradata'
db_recovery_file_dest='/u03/fra'
db_recovery_file_dest_size=100G
~~~

Đây là cấu hình minh họa. Tùy môi trường, có thể cần thêm memory, audit, diagnostic destination, cluster và các tham số khởi động khác. Nếu sử dụng OMF, DB_CREATE_FILE_DEST giúp Oracle tạo tên file do Oracle quản lý. Nếu dùng tên file truyền thống, cần cấu hình chuyển đổi tên file phù hợp.

Khởi động auxiliary:

~~~sql
STARTUP NOMOUNT PFILE='/u01/app/oracle/product/dbhome/dbs/initCLONE1.ora';
~~~

Nếu dùng SPFILE, có thể khởi động bằng SPFILE tương ứng. Khi DUPLICATE có mệnh đề SPFILE, RMAN có thể tạo SPFILE cho database duplicate từ cấu hình nguồn và áp dụng các thay đổi được chỉ định trong lệnh. Hãy kiểm tra các tham số sau duplicate trước khi mở database.

### Cấu hình Oracle Net và password file

Từ máy chạy RMAN, cần phân giải được service name của target và auxiliary. Kiểm tra:

- TNS alias hoặc connect descriptor đúng host, port và service.
- Listener đang hoạt động và có thể tiếp nhận kết nối.
- Auxiliary service có thể kết nối khi instance ở NOMOUNT; thường cần static listener registration hoặc cấu hình phù hợp cho auxiliary.
- Password file cho phép kết nối từ xa bằng SYSDBA.
- Mật khẩu SYS phù hợp giữa kết nối RMAN và password file của auxiliary theo yêu cầu của phương pháp duplicate.

Có thể thử kết nối trước bằng SQL*Plus:

~~~text
sqlplus sys@PROD as sysdba
sqlplus sys@CLONE1 as sysdba
~~~

Thử kết nối thành công bằng SQL*Plus giúp xác nhận Oracle Net và xác thực. Lệnh tnsping chỉ kiểm tra khả năng phân giải và tiếp cận listener ở mức Oracle Net, không chứng minh SYSDBA authentication đã thành công.

Không đặt mật khẩu thật vào script, tài liệu hoặc command history dùng chung. Sử dụng cơ chế quản lý secret phù hợp và bảo vệ password file.

## 5. Chuyển đổi vị trí file database

Database clone phải sử dụng vị trí file riêng để không ảnh hưởng database nguồn.

Có ba cách thường dùng:

- Oracle Managed Files (OMF) thông qua DB_CREATE_FILE_DEST và các tham số destination.
- Chuyển đổi đường dẫn bằng DB_FILE_NAME_CONVERT và LOG_FILE_NAME_CONVERT.
- Chỉ định vị trí file bằng các mệnh đề phù hợp trong DUPLICATE, tùy cấu trúc database và phiên bản.

### Dùng OMF

Nếu auxiliary có DB_CREATE_FILE_DEST trỏ đến storage riêng, Oracle có thể tạo tên datafile do Oracle quản lý. Ví dụ trong PFILE:

~~~ini
db_create_file_dest='/u02/oradata'
db_recovery_file_dest='/u03/fra'
db_recovery_file_dest_size=100G
~~~

Với OMF, không cần tự ghép tên file datafile cho từng tablespace. Cần kiểm tra các destination có đúng storage của clone và không trỏ nhầm về vùng production.

### Dùng DB_FILE_NAME_CONVERT và LOG_FILE_NAME_CONVERT

Nếu source và auxiliary sử dụng tên file truyền thống, có thể chuyển đường dẫn:

~~~ini
db_file_name_convert=
  ('/u01/oradata/PROD/','/u02/oradata/CLONE1/')

log_file_name_convert=
  ('/u01/oradata/PROD/','/u02/oradata/CLONE1/')
~~~

Các cặp chuỗi được áp dụng theo thứ tự source pattern và destination pattern. Phải bảo đảm đường dẫn source khớp đúng tên file thực tế và đường dẫn đích không trùng với source. Nếu database có nhiều thư mục hoặc nhiều disk group, cần khai báo đủ cặp chuyển đổi hoặc chọn phương án OMF rõ ràng.

Với RMAN DUPLICATE, có thể đặt tham số trong SPFILE clause:

~~~rman
DUPLICATE TARGET DATABASE TO CLONE1
  FROM ACTIVE DATABASE
  SPFILE
    SET DB_UNIQUE_NAME='CLONE1'
    SET CONTROL_FILES='/u02/oradata/CLONE1/control01.ctl'
    SET DB_CREATE_FILE_DEST='/u02/oradata'
    SET DB_CREATE_ONLINE_LOG_DEST_1='/u02/oradata/CLONE1'
    SET DB_RECOVERY_FILE_DEST='/u03/fra'
    SET DB_RECOVERY_FILE_DEST_SIZE='100G';
~~~

Đây là ví dụ cho cấu hình OMF. Nếu dùng chuyển đổi tên file truyền thống, hãy đặt các tham số chuyển đổi thích hợp thay cho destination OMF hoặc kết hợp theo đúng quy tắc của phiên bản và cấu trúc lưu trữ. Không cấu hình mâu thuẫn giữa OMF và tên file thủ công.

### Vì sao phải thận trọng với NOFILENAMECHECK?

NOFILENAMECHECK yêu cầu RMAN bỏ qua một số kiểm tra trùng tên file giữa nguồn và đích. Tùy chọn này có thể cần trong một số tình huống đặc biệt, nhưng nếu source và auxiliary cùng truy cập một storage, tên file trùng có thể dẫn đến ghi đè hoặc phá hủy file nguồn.

Chỉ dùng NOFILENAMECHECK khi đã xác minh rõ ràng file đích nằm trên storage độc lập hoặc môi trường được thiết kế an toàn cho thao tác đó. Không dùng nó như cách chữa lỗi chuyển đổi tên file. Trong clone test/dev, ưu tiên đường dẫn riêng, OMF hoặc DB_FILE_NAME_CONVERT rõ ràng.

## 6. Ví dụ active duplication tạo clone độc lập

Ví dụ sau minh họa tạo clone CLONE1 từ database PROD qua Oracle Net, sử dụng OMF cho datafile và FRA.

Trước hết, auxiliary instance được khởi động NOMOUNT bằng PFILE có các tham số phù hợp với CLONE1 và destination của clone. Sau đó kết nối RMAN:

~~~rman
CONNECT TARGET sys@PROD;
CONNECT AUXILIARY sys@CLONE1;
~~~

Thực hiện duplicate:

~~~rman
DUPLICATE TARGET DATABASE TO CLONE1
  FROM ACTIVE DATABASE
  USING BACKUPSET
  SPFILE
    SET DB_UNIQUE_NAME='CLONE1'
    SET CONTROL_FILES='/u02/oradata/CLONE1/control01.ctl'
    SET DB_CREATE_FILE_DEST='/u02/oradata'
    SET DB_CREATE_ONLINE_LOG_DEST_1='/u02/oradata/CLONE1'
    SET DB_RECOVERY_FILE_DEST='/u03/fra'
    SET DB_RECOVERY_FILE_DEST_SIZE='100G'
    SET JOB_QUEUE_PROCESSES='0'
  NOOPEN;
~~~

Các điểm chính:

- TO CLONE1 đặt tên cho database duplicate.
- FROM ACTIVE DATABASE yêu cầu RMAN lấy dữ liệu trực tiếp từ target.
- USING BACKUPSET yêu cầu phương thức truyền qua backup set.
- SPFILE cho phép RMAN tạo SPFILE cho clone và áp dụng các tham số được chỉ định.
- DB_UNIQUE_NAME phân biệt clone với database nguồn.
- DB_CREATE_FILE_DEST và DB_RECOVERY_FILE_DEST xác định storage đích.
- JOB_QUEUE_PROCESSES bằng 0 giúp ngăn job queue khởi chạy trong giai đoạn chuẩn bị, nhưng vẫn cần kiểm tra và vô hiệu hóa các cơ chế tự động khác.
- NOOPEN trì hoãn việc RMAN tự mở database sau duplicate, tạo cơ hội kiểm tra và hoàn tất cấu hình trước khi đưa clone vào sử dụng.

Các giá trị đường dẫn và dung lượng trong ví dụ là placeholder, cần thay bằng cấu hình của hệ thống. Với cấu trúc không dùng OMF, phải bổ sung cấu hình chuyển đổi file phù hợp. Nếu phiên bản hoặc chính sách triển khai không hỗ trợ một tùy chọn theo đúng cách viết trên, đối chiếu cú pháp DUPLICATE của phiên bản đang vận hành.

Sau khi duplicate hoàn tất với NOOPEN, kiểm tra trạng thái auxiliary và các file đã được tạo. Mở database bằng quy trình phù hợp với trạng thái duplicate và hướng dẫn của phiên bản, thông thường clone độc lập cần được mở bằng RESETLOGS:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

Nếu cần thực hiện các thay đổi tham số trước khi open, có thể chỉnh SPFILE/PFILE khi database còn ở trạng thái thích hợp rồi restart. Không mở cho người dùng ứng dụng trước khi hoàn tất các bước cô lập và bảo vệ dữ liệu.

## 7. Ví dụ backup-based duplication

Giả sử đã tạo backup database PROD và archived redo log, sau đó chuyển toàn bộ backup cần thiết sang thư mục /backup/rman trên máy auxiliary.

Khởi động auxiliary instance ở NOMOUNT và kết nối:

~~~rman
CONNECT AUXILIARY sys@CLONE1;
~~~

Thực hiện duplicate từ backup location:

~~~rman
DUPLICATE DATABASE TO CLONE1
  BACKUP LOCATION '/backup/rman'
  NOOPEN;
~~~

Nếu dùng target connection hoặc recovery catalog, câu lệnh có thể dùng TARGET DATABASE và metadata từ repository tương ứng. Nếu không kết nối target/recovery catalog, cần cung cấp DBID khi RMAN yêu cầu và bảo đảm control file autobackup cùng các backup piece cần thiết có mặt.

Trước khi chạy, xác nhận:

- Backup được tạo từ đúng database nguồn.
- DBID và metadata cần thiết đã biết.
- Backup piece có thể đọc từ auxiliary host.
- Archived redo log đáp ứng điểm recover cần thiết.
- Control file autobackup và SPFILE backup có sẵn nếu quy trình cần dùng.
- Tên file đích và destination không trùng nguồn.

Backup-based duplication phù hợp khi tổ chức đã có quy trình backup chuẩn và muốn tạo clone từ một bản backup nhất quán đã được lưu trữ.

## 8. Tạo clone tại một thời điểm trong quá khứ

Trong một số trường hợp, môi trường test cần dữ liệu tại một mốc thời gian cụ thể thay vì thời điểm backup gần nhất. RMAN DUPLICATE hỗ trợ các điều kiện UNTIL phù hợp để dừng quá trình recover tại thời điểm hoặc SCN chỉ định.

Ví dụ về ý tưởng dùng SCN:

~~~rman
DUPLICATE TARGET DATABASE TO CLONE1
  UNTIL SCN 123456789
  BACKUP LOCATION '/backup/rman'
  NOOPEN;
~~~

SCN trong ví dụ chỉ là giá trị minh họa. Phải có backup và archived redo log bao phủ đến SCN yêu cầu. Nếu thiếu redo, RMAN không thể recover clone đến đúng điểm đó.

Có thể dùng thời gian thay cho SCN:

~~~rman
DUPLICATE TARGET DATABASE TO CLONE1
  UNTIL TIME "TO_DATE('2026-11-01 00:00:00',
                     'YYYY-MM-DD HH24:MI:SS')"
  BACKUP LOCATION '/backup/rman'
  NOOPEN;
~~~

Điểm thời gian cần được diễn giải theo thời gian của database và quy trình vận hành. Với dữ liệu nghiệp vụ, cần xác nhận múi giờ, thời điểm giao dịch và độ đầy đủ của archived redo log.

Point-in-time duplicate hữu ích khi cần tái hiện lỗi, kiểm thử báo cáo hoặc tạo bản sao trước một thao tác thay đổi dữ liệu. Nó không thay thế việc quản lý backup retention và lưu trữ redo.

## 9. Vì sao clone cần được cô lập trước khi mở cho người dùng?

Clone vật lý thường chứa gần như toàn bộ nội dung database nguồn tại thời điểm duplicate, bao gồm:

- Bảng nghiệp vụ, dữ liệu cá nhân, dữ liệu khách hàng, dữ liệu thanh toán và thông tin nhạy cảm.
- User, role, profile, quyền hệ thống và quyền object.
- Database link, network ACL, directory object và external table.
- Scheduler job, DBMS_JOB, chương trình tự động và cấu hình gửi thông báo.
- Thông tin kết nối ứng dụng, endpoint tích hợp, credential và một số secret được lưu trong database hoặc wallet.
- Stored procedure, trigger và code có thể gọi dịch vụ bên ngoài.
- Cấu hình audit, TDE, wallet, certificate và các thành phần bảo mật khác.

Nếu clone được mở trong mạng production với cùng cấu hình dịch vụ, các job hoặc chương trình có thể kết nối đến hệ thống thật, gửi email, gọi API, ghi dữ liệu vào hệ thống khác hoặc chạy batch ngoài dự kiến.

Vì vậy, cần cô lập clone ngay từ đầu. Việc tạo database thành công không đồng nghĩa clone đã an toàn để chia sẻ.

## 10. Cô lập clone và vô hiệu hóa hoạt động tự động

### Cô lập mạng và dịch vụ

Trước khi mở clone cho ứng dụng hoặc người dùng:

1. Đặt clone trong subnet hoặc VLAN riêng, hoặc áp dụng firewall rule giới hạn kết nối.
2. Chỉ cho phép kết nối quản trị từ các máy chủ được phê duyệt.
3. Không công bố service name của clone trong DNS hoặc load balancer production.
4. Kiểm tra LOCAL_LISTENER, REMOTE_LISTENER, SERVICE_NAMES, DB_DOMAIN và cấu hình listener để clone không đăng ký nhầm vào hạ tầng production.
5. Thay endpoint tích hợp bằng endpoint test hoặc vô hiệu hóa kết nối ra ngoài.
6. Chặn outbound network trong giai đoạn đầu nếu ứng dụng có thể gọi email, SMS, payment gateway, webhook hoặc API production.

Không dựa riêng vào việc đổi DB_UNIQUE_NAME để cách ly. Đây là định danh database, không phải cơ chế firewall hoặc kiểm soát outbound traffic.

### Ngăn Scheduler và job queue chạy ngoài ý muốn

Có thể đặt JOB_QUEUE_PROCESSES bằng 0 trong giai đoạn chuẩn bị:

~~~sql
ALTER SYSTEM SET job_queue_processes = 0 SCOPE = BOTH;
~~~

Trong môi trường RAC, cần hiểu phạm vi tham số và cấu hình instance phù hợp. Với multitenant, cần xem xét cấu hình ở CDB/PDB theo phiên bản và chính sách vận hành.

Ngoài tham số này, hãy liệt kê và kiểm tra các job hiện có:

~~~sql
SELECT owner,
       job_name,
       enabled,
       state,
       job_type,
       program_name
FROM   dba_scheduler_jobs
ORDER BY owner, job_name;
~~~

Vô hiệu hóa các job không được phép chạy trên clone theo chính sách:

~~~sql
BEGIN
  DBMS_SCHEDULER.DISABLE(
    name  => 'APP_OWNER.NIGHTLY_EXPORT',
    force => TRUE
  );
END;
/
~~~

Nếu hệ thống còn dùng DBMS_JOB, kiểm tra các job cũ trong DBA_JOBS và vô hiệu hóa theo quy trình phù hợp. Cần kiểm tra external job, chain, program, event-based job và các cơ chế tự động riêng của ứng dụng.

Không mặc định rằng JOB_QUEUE_PROCESSES bằng 0 giải quyết toàn bộ nguy cơ. Nó không thay thế firewall, kiểm soát quyền, rà soát chương trình tự động hoặc kiểm tra các service bên ngoài.

### Kiểm tra database link và network ACL

Database link có thể chứa thông tin xác thực để truy cập database khác. Clone giữ lại các link từ nguồn có thể kết nối nhầm production hoặc hệ thống nhạy cảm.

Liệt kê database link:

~~~sql
SELECT owner,
       db_link,
       username,
       host
FROM   dba_db_links
ORDER BY owner, db_link;
~~~

Xác định link cần giữ cho test và link cần xóa hoặc thay thế. Không sao chép credential production sang môi trường test nếu không có yêu cầu được phê duyệt.

Kiểm tra network ACL và quyền truy cập mạng của schema, đặc biệt với UTL_HTTP, UTL_SMTP, UTL_TCP và các package tích hợp. Giới hạn hoặc thay đổi ACL để clone chỉ truy cập các endpoint được phép.

### Kiểm tra directory và external integration

Directory object có thể trỏ đến thư mục chứa file nhạy cảm hoặc file tích hợp. External table, external procedure và scheduler external job có thể thực thi hoặc đọc dữ liệu bên ngoài database.

Liệt kê directory:

~~~sql
SELECT owner,
       directory_name,
       directory_path
FROM   dba_directories
ORDER BY owner, directory_name;
~~~

Rà soát đường dẫn và quyền OS trên auxiliary host. Một directory object có cùng tên với production nhưng trỏ đến thư mục khác vẫn có thể làm ứng dụng chạy sai nếu không kiểm tra cấu hình.

## 11. Tách dữ liệu nhạy cảm bằng data masking

RMAN DUPLICATE sao chép dữ liệu vật lý. Sau duplicate, các giá trị trong bảng vẫn là dữ liệu gốc. Để chia sẻ clone với developer, tester hoặc đối tác mà không để lộ dữ liệu thật, cần thực hiện masking hoặc thay thế dữ liệu.

### Data masking là gì?

Data masking thay thế dữ liệu nhạy cảm bằng giá trị giả hoặc giá trị đã biến đổi, nhưng vẫn giữ được cấu trúc cần thiết cho kiểm thử. Ví dụ:

| Dữ liệu nguồn | Dữ liệu sau masking minh họa |
|---|---|
| Họ tên thật | Tên giả theo bộ dữ liệu test |
| Email khách hàng | user000123@example.test |
| Số điện thoại | Dãy số test không định tuyến đến thuê bao thật |
| Địa chỉ | Địa chỉ giả hoặc dữ liệu đã tổng quát hóa |
| Số tài khoản/thẻ | Token hoặc số test theo quy tắc an toàn |
| Mã định danh cá nhân | Giá trị giả, không thể suy ra định danh gốc |
| Ghi chú tự do | Văn bản thay thế đã loại bỏ thông tin nhận diện |

Không chỉ mask các cột dễ nhận ra. Thông tin cá nhân có thể xuất hiện trong LOB, JSON, XML, log, audit table, comment, tên file, dữ liệu lịch sử hoặc các trường văn bản tự do.

### Yêu cầu của bộ quy tắc masking

Một quy tắc masking tốt cần:

- **Không thể đảo ngược bằng dữ liệu được chia sẻ**: người dùng test không thể suy ra giá trị gốc từ giá trị đã mask.
- **Giữ tính nhất quán**: cùng một khách hàng có cùng giá trị giả ở các bảng liên quan nếu cần kiểm thử join.
- **Giữ ràng buộc dữ liệu**: primary key, foreign key, unique constraint và các quan hệ nghiệp vụ vẫn hợp lệ.
- **Giữ định dạng cần thiết**: dữ liệu giả vẫn đáp ứng kiểu dữ liệu, độ dài và quy tắc validation của ứng dụng.
- **Không tạo giá trị thật có thể gây tác động**: số điện thoại, email, tài khoản hoặc địa chỉ giả không được trỏ đến người hay dịch vụ thật.
- **Có thể kiểm chứng**: có báo cáo phạm vi cột/table được mask và cách xác nhận không còn dữ liệu nhạy cảm trong phạm vi yêu cầu.

Ví dụ, nếu bảng CUSTOMER có CUSTOMER_ID được tham chiếu ở ORDER và PAYMENT, masking các thuộc tính tên, email, điện thoại phải giữ nguyên hoặc ánh xạ nhất quán CUSTOMER_ID để các quan hệ vẫn hoạt động.

### Ví dụ masking bằng SQL

Ví dụ đơn giản sau thay email bằng địa chỉ giả dựa trên ID:

~~~sql
UPDATE app_owner.customers
SET email = 'user' || TO_CHAR(customer_id) || '@example.test';
~~~

Thay số điện thoại bằng dãy số test:

~~~sql
UPDATE app_owner.customers
SET phone_number = '000' || LPAD(TO_CHAR(customer_id), 7, '0');
~~~

Đây chỉ là minh họa cho ý tưởng. Trước khi dùng, phải kiểm tra độ dài cột, unique constraint, định dạng ứng dụng và dải số test không trùng dữ liệu thật. Không dùng phép biến đổi đơn giản này cho dữ liệu có yêu cầu bảo mật cao hoặc dữ liệu có thể tái nhận diện.

Nếu cần nhất quán giữa nhiều bảng, nên tạo mapping table được kiểm soát hoặc dùng một hàm masking xác định (deterministic) với khóa bí mật được bảo vệ. Không lưu mapping ngược hoặc khóa đó trong môi trường clone mà người dùng test có thể truy cập.

### Dùng công cụ masking

Oracle cung cấp các công cụ và tính năng hỗ trợ data masking trong hệ sinh thái Oracle, nhưng việc sử dụng có thể phụ thuộc phiên bản, dịch vụ và giấy phép. Trước khi triển khai, kiểm tra entitlement, phạm vi hỗ trợ và quy trình bảo mật của tổ chức.

Có thể dùng:

- Công cụ Data Masking and Subsetting của Oracle khi được cấp phép.
- Công cụ masking chuyên dụng đã được tổ chức phê duyệt.
- Script SQL/PLSQL được kiểm soát, có kiểm thử và có quy trình xác nhận kết quả.
- Bộ dữ liệu synthetic thay thế hoàn toàn dữ liệu production nếu ứng dụng không cần dữ liệu thật để tái hiện lỗi.

### Data Redaction không thay thế masking

Oracle Data Redaction có thể che giá trị khi truy vấn theo policy, nhưng dữ liệu gốc vẫn được lưu trong database. Nó phục vụ kiểm soát hiển thị theo ngữ cảnh, không tự động biến bản clone thành bản sao đã ẩn danh.

Tương tự, VPD giới hạn những dòng mà session có thể nhìn thấy; nó không thay đổi dữ liệu gốc trong bảng. Nếu clone được cấp cho nhóm có quyền cao hoặc có thể truy cập trực tiếp storage/backup, chỉ dùng VPD hoặc Data Redaction là chưa đủ để loại bỏ dữ liệu nhạy cảm.

## 12. Credential, wallet và khóa mã hóa

Một clone có thể mang theo các thành phần bảo mật từ nguồn. Cần xử lý riêng từng nhóm, vì xóa nhầm có thể làm database không mở được hoặc không đọc được dữ liệu mã hóa.

### Database account và password file

- Xác định các tài khoản quản trị và tài khoản ứng dụng được sao chép.
- Thay đổi mật khẩu cho tài khoản quản trị theo chính sách môi trường clone.
- Khóa tài khoản ứng dụng production không cần dùng trong clone.
- Tạo user/service account riêng cho môi trường test.
- Kiểm tra password file và quyền SYSDBA; không để password file của clone bị chia sẻ ngoài phạm vi quản trị.

Không cần đổi toàn bộ mật khẩu theo cách máy móc nếu một số account nội bộ cần thiết cho Oracle. Phải phân biệt account do Oracle quản lý với account ứng dụng và account tích hợp.

### Credential và database link

Kiểm tra credential được lưu trong Scheduler, external procedure, external job hoặc cơ chế tích hợp. Thay bằng secret riêng của môi trường test, hoặc xóa/vô hiệu hóa nếu không cần.

Không giữ lại credential cho production database, email server, object storage, payment gateway, API hoặc hệ thống bên ngoài trong clone dành cho developer/tester.

### TDE wallet/keystore

Nếu source dùng Transparent Data Encryption, RMAN duplicate cần có khả năng truy cập TDE keystore/wallet để đọc các datafile được mã hóa. Cần chuẩn bị và chuyển keystore theo quy trình bảo mật của Oracle và tổ chức.

- Bảo vệ wallet/keystore trong quá trình chuyển và lưu trữ.
- Cấp quyền mở keystore cho nhóm quản trị được phê duyệt.
- Không đưa mật khẩu keystore hoặc key material vào script hay repository.
- Không xóa keystore trước khi xác nhận database và backup không còn cần khóa để giải mã.
- Nếu clone cần một miền khóa riêng, thực hiện quy trình quản lý/rekey sau khi xác nhận dữ liệu đã được bảo vệ và có kế hoạch phục hồi.

Wallet còn có thể chứa certificate, TLS client credential hoặc thông tin xác thực tích hợp. Cần kiểm tra nội dung và mục đích của wallet; không giả định mọi wallet chỉ chứa TDE master key.

## 13. Quy trình chuẩn để tạo clone test/dev an toàn

Một quy trình thực tế có thể chia thành các giai đoạn sau.

### Giai đoạn A — Chuẩn bị

1. Xác định mục tiêu: clone độc lập hay physical standby.
2. Chọn active duplication hoặc backup-based duplication.
3. Chọn điểm dữ liệu cần sao chép và xác nhận backup/redo sẵn có.
4. Chuẩn bị auxiliary host, storage, listener, password file và PFILE/SPFILE.
5. Xác định DB_NAME, DB_UNIQUE_NAME, destination datafile, control file, redo log và FRA.
6. Lập kế hoạch cô lập mạng và masking trước khi mở quyền ứng dụng.

### Giai đoạn B — Duplicate

1. Khởi động auxiliary ở NOMOUNT.
2. Kiểm tra kết nối SYSDBA đến target và auxiliary nếu dùng active duplication.
3. Kết nối RMAN và chạy DUPLICATE với destination riêng.
4. Theo dõi output RMAN, alert log và dung lượng storage.
5. Nếu dùng NOOPEN, giữ clone ở trạng thái chưa mở cho đến khi hoàn tất bước kiểm tra cần thiết.
6. Xác nhận RMAN kết thúc thành công và các file được tạo ở đúng nơi.

### Giai đoạn C — Cô lập và hardening

1. Đặt firewall và network rule để ngăn clone kết nối production.
2. Đặt JOB_QUEUE_PROCESSES bằng 0 trong giai đoạn chuẩn bị.
3. Kiểm tra và vô hiệu hóa Scheduler job, DBMS_JOB và external job.
4. Rà soát database link, network ACL, directory, external table và external procedure.
5. Đổi service name, listener registration, endpoint tích hợp và thông tin định danh phù hợp.
6. Đổi/khóa account ứng dụng và credential production không cần dùng.
7. Giữ clone chỉ cho nhóm quản trị thực hiện masking.

### Giai đoạn D — Masking và xác nhận

1. Lập danh mục bảng, cột, LOB, log và file có dữ liệu nhạy cảm.
2. Chạy masking theo thứ tự bảo đảm quan hệ khóa và tính toàn vẹn dữ liệu.
3. Kiểm tra số dòng, unique constraint, foreign key và dữ liệu tham chiếu.
4. Quét lại các cột và vùng dữ liệu nhạy cảm để xác nhận không còn giá trị thật trong phạm vi yêu cầu.
5. Kiểm tra code, job, link và endpoint không còn gọi hệ thống production.
6. Lưu báo cáo masking và người phê duyệt.

### Giai đoạn E — Bàn giao

1. Tạo hoặc bật service dành riêng cho test/dev.
2. Cấp quyền theo nguyên tắc tối thiểu.
3. Cấu hình backup/retention riêng cho clone nếu cần.
4. Theo dõi audit và hoạt động truy cập.
5. Lập lịch refresh clone và masking lại mỗi lần refresh.
6. Xóa hoặc hết hạn clone theo chính sách lưu trữ.

Mỗi lần refresh từ production đều có thể đưa dữ liệu thật, password hash, credential, database link và job trở lại clone. Do đó, cô lập và masking phải là bước bắt buộc trong mỗi chu kỳ refresh, không chỉ trong lần tạo clone đầu tiên.

## 14. Kiểm tra database clone sau DUPLICATE

Sau khi database mở, xác nhận danh tính:

~~~sql
SELECT name, dbid, open_mode, database_role
FROM   v$database;
~~~

Kiểm tra unique name và các tham số định danh:

~~~sql
SHOW PARAMETER db_name;
SHOW PARAMETER db_unique_name;
SHOW PARAMETER service_names;
SHOW PARAMETER db_domain;
~~~

Kiểm tra trạng thái file:

~~~sql
SELECT file#, name, status
FROM   v$datafile
ORDER BY file#;
~~~

~~~sql
SELECT group#, member
FROM   v$logfile
ORDER BY group#, member;
~~~

Kiểm tra control file:

~~~sql
SELECT name, status
FROM   v$controlfile;
~~~

Kiểm tra backup và archived log nếu quy trình clone yêu cầu:

~~~rman
LIST BACKUP SUMMARY;
LIST ARCHIVELOG ALL;
~~~

Các truy vấn này giúp xác nhận database identity và file location. Chúng không chứng minh dữ liệu đã được masking hoặc clone đã được cô lập an toàn. Cần có kiểm tra riêng cho job, database link, ACL, credential và dữ liệu nhạy cảm.

## 15. Những lỗi thường gặp khi DUPLICATE

### Auxiliary instance không kết nối được

Nguyên nhân thường gặp:

- Listener không đăng ký auxiliary service khi instance ở NOMOUNT.
- TNS alias hoặc connect descriptor sai.
- Password file thiếu hoặc mật khẩu không khớp.
- Kết nối mạng bị firewall chặn.
- Quyền SYSDBA không được cấp.

Kiểm tra listener, Oracle Net, password file và thử đăng nhập SYSDBA trước khi chạy RMAN.

### File name conflict hoặc file ghi sai vị trí

Nguyên nhân có thể là DB_FILE_NAME_CONVERT hoặc LOG_FILE_NAME_CONVERT thiếu cặp, OMF destination sai, control_files trỏ về vị trí production hoặc FORMAT/destination không được xác định rõ.

Kiểm tra đường dẫn nguồn và đích, tham số SPFILE, file được tạo và alert log. Không dùng NOFILENAMECHECK để che giấu một cấu hình file name chưa rõ ràng.

### Thiếu backup hoặc archived redo log

Backup-based duplication cần backup piece và redo phù hợp. Nếu thiếu archived log, RMAN có thể không recover được đến điểm yêu cầu. Kiểm tra DBID, control file autobackup, backup piece, thời điểm backup và archive log sequence.

### Active duplication chậm hoặc bị gián đoạn

Kiểm tra băng thông mạng, latency, tải đọc trên source, I/O đích, số channel, compression và alert log. Nếu đường truyền không ổn định, cân nhắc backup-based duplication để chuyển backup theo cơ chế truyền file được tổ chức kiểm soát.

### Clone mở ra và chạy job production

Đây là rủi ro vận hành nghiêm trọng khi clone được tạo từ source có scheduler, link hoặc endpoint production. Cần cô lập mạng trước khi mở quyền ứng dụng, đặt JOB_QUEUE_PROCESSES bằng 0 trong giai đoạn chuẩn bị và rà soát các job cùng kết nối bên ngoài trước khi cho clone hoạt động.

### Clone vẫn chứa dữ liệu thật

RMAN DUPLICATE không mask dữ liệu. Nếu người dùng test có thể đọc bảng, LOB, log hoặc backup chưa được xử lý, dữ liệu nhạy cảm vẫn có thể bị lộ. Chỉ cấp quyền sau khi hoàn thành masking và kiểm tra lại toàn bộ phạm vi dữ liệu.

## 16. Những nguyên tắc cần nhớ

- Chọn DUPLICATE độc lập cho clone test/dev; dùng FOR STANDBY cho physical standby của Data Guard.
- Phân biệt DBID và DB_UNIQUE_NAME. Clone độc lập cần danh tính riêng.
- Auxiliary instance phải được chuẩn bị và khởi động ở NOMOUNT.
- Active duplication cần Oracle Net và kết nối SYSDBA phù hợp; backup-based duplication cần backup và redo có thể truy cập.
- Chuyển đổi tên file và destination trước khi chạy để tránh ghi đè file nguồn.
- NOFILENAMECHECK chỉ dùng khi đã xác minh rõ ràng storage và đường dẫn.
- RMAN DUPLICATE sao chép dữ liệu vật lý; nó không tự ẩn danh dữ liệu.
- Cô lập network, tắt job tự động và rà soát database link/credential trước khi cấp quyền ứng dụng.
- Mask dữ liệu nhạy cảm một cách nhất quán và kiểm tra lại các bảng, LOB, log, file liên quan.
- TDE keystore phải được xử lý đúng để clone có thể đọc dữ liệu mã hóa; bảo vệ key material trong suốt quá trình.
- Mỗi lần refresh clone phải lặp lại quy trình cô lập và masking.
- Kiểm tra restore/recover và khả năng vận hành của clone theo lịch.

RMAN DUPLICATE giúp tạo database copy đáng tin cậy từ backup hoặc database đang hoạt động. Để bản sao thực sự phù hợp cho test/dev, cần hoàn tất cả hai phần: tạo database đúng kỹ thuật và xử lý dữ liệu, credential, job cùng kết nối bên ngoài trước khi mở cho người dùng.
