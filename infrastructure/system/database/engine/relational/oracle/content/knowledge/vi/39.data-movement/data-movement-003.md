# DIRECTORY object, quyền truy cập và vị trí dump/log

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Nhập xuất và di chuyển  
> **Mục tiêu:** Hiểu DIRECTORY object ánh xạ tên database tới đường dẫn trên máy chủ; phân biệt quyền DIRECTORY trong Oracle với quyền filesystem của operating-system account; cấu hình quyền READ/WRITE cho Data Pump, UTL_FILE và external table; xác định đúng nơi đặt dump, log và parameter file; xử lý khác biệt giữa client/server, PDB và RAC; bảo vệ dump/log và xây dựng quy trình kiểm tra trước khi export/import.

## 1. DIRECTORY object là gì?

Oracle DIRECTORY object là một đối tượng trong database dùng để ánh xạ một tên logic tới một đường dẫn thư mục trên filesystem mà database server có thể truy cập.

Ví dụ:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_stage
AS '/u02/oracle/exports';
~~~

Sau khi tạo, các công cụ phía database có thể tham chiếu tên DPUMP_STAGE thay vì phải lặp lại đường dẫn hệ điều hành trong từng thao tác.

DIRECTORY object thường được dùng bởi:

- Oracle Data Pump Export và Import.
- Package DBMS_DATAPUMP.
- UTL_FILE để đọc/ghi file văn bản hoặc dữ liệu theo chương trình.
- BFILE để tham chiếu file nhị phân bên ngoài database.
- External tables và một số tiện ích Oracle cần đọc file trên server.

Điểm cốt lõi: DIRECTORY object chỉ là ánh xạ tên và điểm kiểm tra quyền trong database. Nó không tự tạo thư mục trên hệ điều hành, không tự cấp quyền filesystem và không chuyển file từ máy client lên database server.

### 1.1. Phân biệt ba loại vị trí

| Thành phần | Nằm ở đâu? | Ai truy cập? |
|---|---|---|
| DIRECTORY object | Metadata trong Oracle Database | Oracle phân giải tên và kiểm tra privilege |
| Directory path | Filesystem mà database server truy cập được | Oracle server process dưới OS account của Oracle |
| Parameter file của expdp/impdp | Máy chạy client command | Tiến trình expdp/impdp phía client đọc |

Ví dụ:

- DIRECTORY object DPUMP_STAGE trỏ tới /u02/oracle/exports trên database host.
- Data Pump dump file ORDERS_01.DMP được tạo trong thư mục server đó.
- File PARFILE=export_orders.par thường được đọc từ máy đang chạy lệnh expdp, trừ khi đường dẫn client được chỉ rõ khác.
- Người dùng chạy expdp trên laptop không có nghĩa dump file được tạo trên laptop.

Đây là nguyên nhân phổ biến khiến người vận hành tìm dump file sai máy hoặc cấp quyền filesystem sai account.

### 1.2. DIRECTORY object không phải tablespace hoặc datafile

DIRECTORY object không chứa dữ liệu database theo cấu trúc tablespace. Nó không phải:

- Tablespace.
- Datafile hoặc tempfile.
- Redo log hoặc archived redo log.
- Schema chứa bảng.
- Thư mục local của ứng dụng client.
- Một bản backup có thể restore độc lập.

Dump file có thể chứa metadata và dữ liệu được export, nhưng vị trí dump được quản lý qua DIRECTORY object và filesystem/storage tương ứng.

## 2. Hai lớp quyền phải cùng đúng

Để Oracle đọc hoặc ghi file qua DIRECTORY object, thường phải thỏa hai lớp quyền độc lập:

1. **Oracle directory privilege:** user thực hiện thao tác được cấp READ hoặc WRITE trên DIRECTORY object.
2. **Operating-system permission:** OS account chạy Oracle Database có quyền traverse thư mục và đọc/ghi file tại path đích.

Ví dụ cấp quyền trong Oracle:

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_export;
~~~

Trên Linux, thư mục cũng phải cho phép OS account của Oracle truy cập. Ví dụ account cài đặt database thường là oracle, nhưng phải xác minh đúng account thực tế của dịch vụ:

~~~bash
ls -ld /u02/oracle/exports
namei -l /u02/oracle/exports
df -h /u02/oracle/exports
~~~

Nếu database service chạy bằng account khác, quyền phải phù hợp account đó. Trên Windows, cần kiểm tra quyền NTFS của account chạy Oracle Database service.

### 2.1. Có Oracle privilege nhưng thiếu OS permission

Giả sử APP_EXPORT có READ và WRITE trên DPUMP_STAGE, nhưng OS account Oracle không có quyền ghi vào /u02/oracle/exports.

Khi Data Pump export tạo dump file hoặc log, thao tác có thể thất bại với lỗi filesystem. Grant trong Oracle không thể vượt qua permission của hệ điều hành.

Các nguyên nhân thường gặp:

- Directory chưa tồn tại.
- Parent directory không có quyền execute/traverse.
- Owner/group/mode không đúng.
- Filesystem mount ở chế độ read-only.
- NFS mount mất kết nối hoặc credential mapping không đúng.
- Disk hoặc quota hết dung lượng.
- SELinux/AppArmor policy chặn truy cập.
- Path có khác biệt giữa các host trong cluster.

### 2.2. Có OS permission nhưng thiếu Oracle privilege

Ngược lại, OS account Oracle có quyền ghi filesystem nhưng APP_EXPORT không có WRITE trên DIRECTORY object. Oracle vẫn từ chối thao tác theo privilege model của database.

Không giải quyết lỗi bằng cách cấp quyền OS rộng hơn cho toàn bộ user hoặc cấp READ/WRITE trên directory cho PUBLIC. Hãy xác định principal thực hiện và cấp đúng object privilege.

### 2.3. READ và WRITE có ý nghĩa gì?

| Privilege | Khả năng chính |
|---|---|
| READ | Đọc file trong directory qua các tính năng Oracle hỗ trợ |
| WRITE | Tạo/ghi file trong directory qua các tính năng Oracle hỗ trợ |

Ví dụ theo Data Pump:

- Export dump file: cần WRITE.
- Export log file: cần WRITE.
- Import dump file: cần READ.
- Import log file: cần WRITE.
- SQLFILE output: cần WRITE.
- UTL_FILE đọc file: cần READ.
- UTL_FILE tạo/ghi file: cần WRITE.
- BFILE đọc file nhị phân: cần READ.

Đối với account vận hành chuyên dùng Data Pump, có thể grant READ và WRITE trên đúng directory. Nếu chỉ có import hoặc export, hãy cấp tối thiểu theo chức năng thực tế.

## 3. Tạo và quản lý DIRECTORY object

### 3.1. Tạo directory

Ví dụ:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_stage
AS '/u02/oracle/exports';
~~~

CREATE DIRECTORY cần system privilege phù hợp, thông thường là CREATE ANY DIRECTORY. Quyền này mạnh vì cho phép tạo hoặc thay đổi ánh xạ directory trong database; chỉ DBA hoặc principal được ủy quyền mới nên có.

Lệnh trên không tạo thư mục /u02/oracle/exports trên OS. Thư mục phải được chuẩn bị trước và có permission phù hợp.

### 3.2. Cấp quyền cho user

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_export;
~~~

Nếu tách user import và export:

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_import;
~~~

Trong môi trường yêu cầu least privilege, có thể tạo directory riêng cho luồng import chỉ cần READ dump và WRITE log; export account chỉ cần WRITE dump/log. Kiểm tra privilege behavior bằng đúng account thực tế thay vì dựa vào role không rõ ràng.

### 3.3. Thu hồi quyền

~~~sql
REVOKE READ, WRITE
ON DIRECTORY dpump_stage
FROM app_export;
~~~

Thu hồi quyền không xóa file đã được tạo trên filesystem. Nó chỉ thay đổi khả năng sử dụng DIRECTORY object của principal đó.

### 3.4. Xóa DIRECTORY object

~~~sql
DROP DIRECTORY dpump_stage;
~~~

DROP DIRECTORY xóa object mapping trong database, không xóa thư mục OS hoặc các file bên trong.

Trước khi drop, tìm các job, package, external table, BFILE reference và Data Pump script đang sử dụng directory. Thao tác có thể làm các quy trình phụ thuộc thất bại.

### 3.5. Đổi path của directory

Ví dụ:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_stage
AS '/u03/new_exports';
~~~

Thay đổi này chuyển mọi consumer của DPUMP_STAGE sang path mới. Các dump file cũ vẫn nằm ở path cũ; Oracle không tự di chuyển chúng.

Trước khi thay đổi:

1. Liệt kê consumer và job phụ thuộc.
2. Xác minh path mới tồn tại trên database host.
3. Xác minh owner/group/permission, mount và free space.
4. Kiểm tra RAC node visibility nếu áp dụng.
5. Lập kế hoạch chuyển file nếu cần.
6. Thực hiện change và xác nhận export/import test.
7. Lưu mapping cũ để rollback nếu chưa xóa dữ liệu cũ.

Không dùng CREATE OR REPLACE DIRECTORY để trỏ sang một path chưa được chuẩn bị rồi mới tìm hiểu vì sao job không chạy.

## 4. Kiểm tra DIRECTORY metadata và quyền

### 4.1. Xem directory objects

Từ tài khoản có quyền phù hợp:

~~~sql
SELECT owner,
       directory_name,
       directory_path
FROM dba_directories
ORDER BY directory_name;
~~~

Từ phạm vi object mà user có thể thấy:

~~~sql
SELECT directory_name,
       directory_path
FROM all_directories
ORDER BY directory_name;
~~~

USER_DIRECTORIES hoặc view tương ứng có thể được dùng tùy release và quyền. Không giả định directory object chỉ hiện trong schema tạo lệnh; metadata directory có quy tắc riêng so với table/view thông thường.

### 4.2. Xem privilege trên directory

DBA có thể kiểm tra object grants:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM dba_tab_privs
WHERE table_name = 'DPUMP_STAGE'
ORDER BY grantee, privilege;
~~~

Directory privilege được thể hiện trong metadata object privilege theo quy tắc của release. Đối chiếu tên object, grantee, privilege và grantable; không chỉ kiểm tra user có role nào.

### 4.3. Xác định container trong CDB/PDB

Trong multitenant, cần biết directory object được tạo và sử dụng trong container nào:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id,
       sys_context('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Ở CDB root, DBA có thể xem:

~~~sql
SELECT con_id,
       owner,
       directory_name,
       directory_path
FROM cdb_directories
ORDER BY con_id, directory_name;
~~~

Đối chiếu CON_ID với PDB cần export/import. Không tạo directory trong root rồi mặc định cho rằng mọi PDB có cùng object mapping và grant.

Directory object có thể được quản lý ở phạm vi container theo cấu hình/release. Thực hiện DDL và grant trong đúng container; xác nhận metadata và privilege ngay tại PDB mà Data Pump job sẽ kết nối.

## 5. Data Pump: dump file và log file nằm ở server

Data Pump Export và Import thường được chạy bằng tiện ích:

- expdp: Data Pump Export.
- impdp: Data Pump Import.

Phần xử lý Data Pump được thực hiện bởi database server processes. File dump và log được ghi/đọc trên filesystem phía database server theo DIRECTORY object.

### 5.1. Export đơn giản

Ví dụ export schema SALES:

~~~bash
expdp app_export@APP_PDB \
  DIRECTORY=DPUMP_STAGE \
  DUMPFILE=sales_export.dmp \
  LOGFILE=sales_export.log \
  SCHEMAS=SALES
~~~

Giả sử DPUMP_STAGE trỏ tới /u02/oracle/exports. Dump và log sẽ được tạo trong thư mục server đó, nếu cả Oracle privilege và OS permission đều cho phép.

Lệnh trên là ví dụ cấu trúc. Kết nối, password, service và schema phải thay bằng giá trị môi trường; không đặt password rõ trong command history hoặc script dùng chung.

### 5.2. Export với nhiều dump file

Với dữ liệu lớn hoặc PARALLEL, có thể chia dump thành nhiều file:

~~~bash
expdp app_export@APP_PDB \
  DIRECTORY=DPUMP_STAGE \
  DUMPFILE=sales_%U.dmp \
  LOGFILE=sales_export.log \
  SCHEMAS=SALES \
  PARALLEL=4 \
  FILESIZE=10G \
  LOGTIME=ALL \
  METRICS=YES
~~~

%U là substitution variable để Data Pump tạo tên file theo nhiều phần. FILESIZE giới hạn kích thước mỗi dump file theo cấu hình. PARALLEL điều khiển mức song song của job; cần cân nhắc CPU, I/O, storage và số file.

Tăng PARALLEL không luôn làm export nhanh hơn. Nếu storage hoặc network đã bão hòa, nhiều worker có thể làm workload khác chậm đi.

### 5.3. Import schema

~~~bash
impdp app_import@APP_PDB \
  DIRECTORY=DPUMP_STAGE \
  DUMPFILE=sales_%U.dmp \
  LOGFILE=sales_import.log \
  SCHEMAS=SALES \
  REMAP_SCHEMA=SALES:SALES_TEST
~~~

Import đọc dump file từ directory phía server và ghi log ở phía server. Target schema, tablespace, quota, object ownership, grants và dependencies phải được chuẩn bị theo yêu cầu.

REMAP_SCHEMA chỉ thay đổi mapping schema trong import; nó không tự tạo user, quota, tablespace hoặc đảm bảo mọi object có thể được tạo thành công.

### 5.4. Directory parameter

Tham số DIRECTORY chỉ định directory object mặc định cho file của Data Pump job. DUMPFILE, LOGFILE và các file output liên quan sẽ được giải quyết theo directory đã chỉ định nếu không có cách chỉ định directory khác được hỗ trợ.

Ví dụ:

~~~text
DIRECTORY=DPUMP_STAGE
DUMPFILE=orders_%U.dmp
LOGFILE=orders_export.log
~~~

Tên directory object phải tồn tại trong container mà job kết nối. User chạy job phải có quyền cần thiết trên directory đó.

### 5.5. Log file là bằng chứng vận hành

LOGFILE ghi lại quá trình export/import, object được xử lý, warning và lỗi. Luôn tạo log cho job quan trọng.

Có thể bổ sung:

- LOGTIME=ALL để ghi timestamp theo từng thông báo.
- METRICS=YES để ghi metric object/operation theo phiên bản hỗ trợ.
- Job name có ý nghĩa để dễ ATTACH/monitor.
- Lưu exit code của expdp/impdp và log vào nơi quản lý run.

NOLOGFILE=YES làm mất một nguồn bằng chứng quan trọng. Chỉ dùng khi có lý do và có hệ thống log/monitoring thay thế.

## 6. Phân biệt dump/log phía server và PARFILE phía client

Đây là khác biệt rất quan trọng khi chạy Data Pump từ máy quản trị.

Ví dụ:

~~~bash
expdp app_export@APP_PDB parfile=./export_sales.par
~~~

File export_sales.par được đọc bởi chương trình expdp ở máy đang chạy command. Trong file có thể chứa:

~~~text
DIRECTORY=DPUMP_STAGE
DUMPFILE=sales_%U.dmp
LOGFILE=sales_export.log
SCHEMAS=SALES
PARALLEL=4
LOGTIME=ALL
METRICS=YES
~~~

Trong khi đó:

- PARFILE: file cấu hình phía client.
- DUMPFILE: file dump phía database server.
- LOGFILE: file log phía database server.
- SQLFILE: file DDL output phía database server.
- DIRECTORY: tên directory object được database server phân giải.

Không đưa path client vào DIRECTORY nếu path đó không tồn tại trên database server. Cũng không tìm dump file trong thư mục client chỉ vì lệnh expdp được chạy tại đó.

### 6.1. Credential và command line

Tránh truyền password trực tiếp sau dấu slash trong command nếu shell history, process listing hoặc automation log có thể ghi lại. Dùng cơ chế xác thực được tổ chức chấp thuận, Oracle wallet/secure external password store hoặc prompt tương tác phù hợp.

Parameter file cũng có thể chứa thông tin nhạy cảm. Bảo vệ quyền đọc, retention và nơi lưu file.

## 7. Data Pump cần những quyền nào?

Quyền cần thiết phụ thuộc chế độ export/import và object được xử lý.

### 7.1. Directory privileges

Ví dụ cấp quyền cho export account:

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_export;
~~~

Và import account:

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_import;
~~~

READ/WRITE trên DIRECTORY không cấp quyền SELECT trên bảng SALES.ORDERS, và quyền SELECT trên bảng cũng không tự cấp quyền ghi dump file.

### 7.2. Schema mode và quyền dữ liệu

Một user có thể export schema của chính mình theo các điều kiện Data Pump phù hợp. Export/import toàn database hoặc schema khác có thể yêu cầu role đặc quyền tương ứng.

Các role Data Pump thường gặp:

- DATAPUMP_EXP_FULL_DATABASE: quyền bổ sung cho export ngoài schema của chính user hoặc full database theo phạm vi role.
- DATAPUMP_IMP_FULL_DATABASE: quyền bổ sung cho import full database hoặc object/schema ngoài phạm vi thông thường của user.

Không grant các role này chỉ để xử lý một lỗi directory. Xác định chế độ export/import, owner object và privilege thực sự cần.

### 7.3. Tách quyền theo trách nhiệm

Một mô hình có thể là:

| Principal | Quyền cần thiết |
|---|---|
| DBA quản lý directory | CREATE ANY DIRECTORY theo nhiệm vụ |
| Export account | READ/WRITE trên directory export và quyền export dữ liệu được phép |
| Import account | READ/WRITE trên directory import và quyền import mục tiêu |
| Application runtime | Không cần quyền Data Pump nếu không tự export/import |
| OS Oracle account | Filesystem permission trên path server |

Không cấp CREATE ANY DIRECTORY cho ứng dụng runtime. Quyền này có thể cho phép tạo hoặc thay đổi mapping tới path khác và mở rộng khả năng truy cập file của database server.

## 8. Vị trí file trên filesystem server

### 8.1. Chuẩn bị thư mục

Trên Linux/Unix, DBA hoặc system administrator tạo path và gán owner/group/mode phù hợp trước khi tạo DIRECTORY object.

Ví dụ minh họa:

~~~bash
mkdir -p /u02/oracle/exports
chown oracle:oinstall /u02/oracle/exports
chmod 750 /u02/oracle/exports
ls -ld /u02/oracle/exports
df -h /u02/oracle/exports
~~~

Các lệnh trên thay đổi filesystem; chỉ chạy theo change procedure và thay account/group theo môi trường thực tế. Không mặc định owner luôn là oracle:oinstall.

Để Oracle truy cập, mọi thư mục cha trên path cần quyền traverse phù hợp. Kiểm tra cả mount options, quota, ACL và security policy.

### 8.2. Kiểm tra file và dung lượng

~~~bash
ls -lh /u02/oracle/exports
df -h /u02/oracle/exports
du -sh /u02/oracle/exports
~~~

Với file lớn, theo dõi dung lượng trong lúc job chạy. Dự phòng dung lượng cho dump, log, file tạm, concurrent job và output import.

### 8.3. NFS và shared filesystem

Nếu path nằm trên NFS:

- Kiểm tra mount trên database host.
- Xác nhận export/mount permission.
- Kiểm tra UID/GID mapping của OS account Oracle.
- Xác nhận network ổn định.
- Kiểm tra throughput và latency.
- Xác định hành vi khi NFS server mất kết nối.
- Xác nhận mọi RAC node cần chạy Data Pump đều nhìn thấy cùng dữ liệu.

Directory object không mount NFS và không làm path xuất hiện trên server. Nó chỉ lưu mapping tới path.

### 8.4. Không dùng thư mục tùy tiện

Tránh đặt dump trong:

- Oracle Home.
- Datafile/redo log directory.
- Diagnostic trace directory không có quota riêng.
- Filesystem root.
- Thư mục ứng dụng có quyền ghi rộng.
- Path tạm bị cleanup tự động.
- Shared path không có access control.

Tạo vùng staging chuyên biệt với quota, monitoring, retention và quyền truy cập riêng.

## 9. Oracle RAC: path phải nhìn thấy từ worker node

Trong RAC, Data Pump master process và worker process có thể được phân bố trên các instance tùy cấu hình. Nếu directory path chỉ tồn tại trên filesystem local của một node, worker chạy trên node khác có thể không tìm thấy file hoặc ghi vào một path khác.

Khuyến nghị:

- Dùng shared filesystem được hỗ trợ và mount nhất quán trên các node cần tham gia job.
- Xác nhận cùng directory object path được nhìn thấy từ mọi node.
- Kiểm tra OS permission trên từng node.
- Nếu dùng local filesystem, cân nhắc giới hạn job chạy trên instance phù hợp bằng cấu hình Data Pump như CLUSTER=NO theo release và topology.
- Đo tác động của PARALLEL và storage throughput.

Ví dụ:

~~~text
DIRECTORY=DPUMP_STAGE
CLUSTER=NO
PARALLEL=2
DUMPFILE=orders_%U.dmp
LOGFILE=orders_export.log
~~~

CLUSTER=NO giới hạn Data Pump job không phân tán worker qua cluster theo hành vi được hỗ trợ của release. Nó không tự bảo đảm mọi path và service đều đúng; kiểm tra instance/service nơi job được khởi chạy.

Không dùng một path local giống tên trên các node nếu nội dung thực tế khác nhau. Một dump file phân mảnh cần được tập hợp đầy đủ để import.

## 10. CDB/PDB và DIRECTORY object

Với multitenant, phải kết nối đúng PDB trước khi chạy Data Pump cho schema/object trong PDB đó.

Ví dụ kiểm tra:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id,
       sys_context('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Xem directory metadata từ CDB root khi có quyền:

~~~sql
SELECT con_id,
       owner,
       directory_name,
       directory_path
FROM cdb_directories
ORDER BY con_id, directory_name;
~~~

Các directory object có thể có phạm vi container khác nhau. Xác nhận object và grant tồn tại trong đúng container mà user kết nối.

Data Pump job kết nối service của PDB có thể nhìn thấy directory object được định nghĩa ở phạm vi phù hợp theo quy tắc multitenant. Không suy luận từ kết quả query ở root rằng PDB đã có quyền sử dụng.

## 11. Data Pump import/export với nhiều directory

Một số job cần tách vị trí đọc dump và ghi log/output. Data Pump hỗ trợ chỉ định directory object theo cú pháp parameter được release hỗ trợ; cần tham khảo Data Pump Utilities Guide cho cách ghi file parameter.

Ví dụ đơn giản nhất là dùng một directory staging có READ/WRITE và đặt dump/log trong đó. Khi cần tách:

- Dump input nằm ở vùng chỉ cho phép import account đọc.
- Log output nằm ở vùng chỉ cho phép operator đọc/ghi.
- SQLFILE output nằm ở vùng kiểm tra DDL riêng.
- Backup archive được chuyển sang storage khác theo policy.

Giữ thiết kế đơn giản nếu không có nhu cầu tách biệt. Mỗi directory bổ sung tạo thêm grant, path, mount, capacity và dependency phải quản lý.

### 11.1. SQLFILE

IMPDP có thể tạo file SQL chứa DDL mà job dự kiến thực hiện thay vì thực thi DDL đó:

~~~bash
impdp app_import@APP_PDB \
  DIRECTORY=DPUMP_STAGE \
  DUMPFILE=sales_export.dmp \
  SQLFILE=sales_preview.sql \
  SCHEMAS=SALES
~~~

SQLFILE được ghi phía database server theo DIRECTORY object. Nó hữu ích để review DDL trước import, nhưng không thay thế kiểm thử import thực tế.

Bảo vệ SQLFILE như metadata nhạy cảm: có thể chứa tên schema, object, cấu trúc và chi tiết triển khai.

### 11.2. Network mode

Data Pump có thể dùng NETWORK_LINK để import trực tiếp từ database nguồn qua database link mà không cần dump file trung gian cho luồng dữ liệu.

Ví dụ khái niệm:

~~~text
impdp app_import@TARGET_PDB
  NETWORK_LINK=SOURCE_LINK
  SCHEMAS=SALES
  LOGFILE=network_import.log
  DIRECTORY=DPUMP_STAGE
~~~

NETWORK_LINK thay đổi nguồn dữ liệu, nhưng log file vẫn cần vị trí server-side và quyền DIRECTORY thích hợp. Cần quyền remote, network, version compatibility và capacity ở cả hai database.

## 12. UTL_FILE và BFILE cũng dùng DIRECTORY object

DIRECTORY object không chỉ phục vụ Data Pump.

### 12.1. UTL_FILE

UTL_FILE cho phép PL/SQL đọc/ghi file text hoặc file theo chế độ mà package hỗ trợ.

Ví dụ khái niệm:

~~~sql
DECLARE
    l_file UTL_FILE.FILE_TYPE;
BEGIN
    l_file := UTL_FILE.FOPEN(
        location     => 'APP_LOG_DIR',
        filename     => 'job_status.txt',
        open_mode    => 'w',
        max_linesize => 32767
    );

    UTL_FILE.PUT_LINE(l_file, 'Job completed');
    UTL_FILE.FCLOSE(l_file);
END;
/
~~~

User/schema thực hiện cần quyền DIRECTORY phù hợp và OS account Oracle phải ghi được file. Đóng file trong cả luồng thành công lẫn exception; production code nên có exception handler gọi FCLOSE khi handle còn mở.

Không nối input user thành tên file tùy ý. Whitelist filename hoặc tạo tên theo quy tắc kiểm soát để tránh ghi đè file không mong muốn.

### 12.2. BFILE

BFILE là locator tới file nhị phân ngoài database, được truy cập ở chế độ chỉ đọc qua DIRECTORY object.

Ví dụ tạo locator:

~~~sql
SELECT BFILENAME('APP_MEDIA_DIR', 'image_001.bin')
FROM dual;
~~~

BFILE không lưu nội dung file trong database và không cho Oracle ghi ngược nội dung vào file theo cơ chế BFILE. Consumer cần READ privilege trên directory và OS account Oracle phải đọc được file.

### 12.3. External tables

External table cho phép SQL đọc dữ liệu từ file ngoài database bằng access driver phù hợp, chẳng hạn ORACLE_LOADER hoặc ORACLE_DATAPUMP.

Ví dụ đơn giản:

~~~sql
CREATE TABLE ext_orders (
    order_id      NUMBER,
    customer_id   NUMBER,
    status        VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY ext_data_dir
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        FIELDS TERMINATED BY ','
        MISSING FIELD VALUES ARE NULL
    )
    LOCATION ('orders.csv')
)
REJECT LIMIT UNLIMITED;
~~~

External table không lưu dữ liệu như heap table thông thường. Query đọc file tại vị trí server; directory privilege và OS access vẫn cần đúng.

Với file không tin cậy, kiểm tra format, encoding, delimiter, line ending, record length và reject file. Không đặt REJECT LIMIT UNLIMITED một cách vô điều kiện nếu lỗi dữ liệu phải được phát hiện sớm.

## 13. Bảo vệ dump file và log

Dump file có thể chứa dữ liệu nghiệp vụ, thông tin cá nhân, cấu trúc schema, metadata và nội dung nhạy cảm. Việc cấp quyền DIRECTORY rộng có thể làm tăng nguy cơ lộ dữ liệu.

### 13.1. Quyền filesystem

Dùng owner/group riêng, hạn chế quyền đọc cho operator và service account cần thiết. Tránh chmod 777 hoặc thư mục writable bởi mọi OS user.

Kiểm tra:

- Directory owner/group/mode.
- ACL.
- NFS export permission.
- SELinux/AppArmor.
- Storage encryption.
- Quota và retention.
- Quyền xóa file.
- Audit truy cập.

### 13.2. Encryption

Nếu dump chứa dữ liệu nhạy cảm, đánh giá Data Pump encryption theo tính năng và license được hỗ trợ, hoặc mã hóa storage/file theo policy.

Khi dùng encryption, bảo vệ password/keystore riêng với dump file. Backup encrypted mà mất key có thể không phục hồi được.

Không ghi encryption password vào source control, shell history, log hoặc ticket. Kiểm tra quy trình restore từ bản encrypted trước khi áp dụng rộng.

### 13.3. Retention và cleanup

Đặt lifecycle rõ:

- Job owner.
- Ngày tạo và export scope.
- Backup/dump purpose.
- Thời hạn lưu.
- Người được đọc.
- Offsite/immutable copy nếu cần.
- Điều kiện xóa.
- Log và evidence của cleanup.

Không xóa file dump ngay sau import nếu đó là bản duy nhất đáp ứng recovery/compliance requirement. Không coi dump Data Pump là thay thế RMAN backup của toàn database.

### 13.4. Log cũng cần bảo vệ

Log có thể chứa object names, SQL/error text, path và thông tin vận hành. Hạn chế quyền truy cập và retention theo chính sách.

Không tắt log chỉ để tránh lỗi ghi file. Sửa quyền/path/capacity hoặc thiết kế logging phù hợp.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| ORA-39002 invalid operation | Job parameter hoặc operation không hợp lệ | Đọc toàn bộ Data Pump error stack |
| ORA-39070 unable to open log file | Thiếu WRITE, path sai hoặc filesystem không ghi được | DIRECTORY grant, OS permission, disk |
| ORA-39087 directory name invalid | DIRECTORY object không tồn tại hoặc tên không đúng | DBA_DIRECTORIES, container và spelling |
| ORA-29283 invalid file operation | UTL_FILE/file access lỗi | Directory grant, OS permission, filename, path |
| ORA-29289 directory access denied | Thiếu quyền DIRECTORY phù hợp | Kiểm tra READ/WRITE grant cho principal |
| ORA-31640 unable to open dump file | Dump không tồn tại/không đọc được | Path server, READ grant, mount, filename |
| ORA-31641 unable to create dump file | Không tạo được dump output | WRITE grant, OS permission, disk/quota |
| OS permission denied | Oracle OS account không có quyền | Owner/group/mode/ACL/SELinux |
| No space left on device | Filesystem hoặc quota hết | df, quota, storage alert |
| File not found dù client thấy file | File chỉ có trên client, không có trên server | Chuyển file tới server path được cấp |
| RAC worker không thấy file | Path local chỉ tồn tại trên một node | Shared mount hoặc CLUSTER=NO |
| Job chạy nhầm PDB | Kết nối sai service/container | CON_NAME, CON_ID và service |
| Dump file có nhưng import lỗi | Dump thiếu part, version/privilege/object dependency | Log export/import, file set và metadata |

Luôn đọc error stack đầy đủ. ORA-390xx thường là lỗi bao ngoài; nguyên nhân gốc có thể nằm ở ORA-01031, ORA-29283 hoặc thông báo OS phía sau.

## 15. Runbook: chuẩn bị directory cho Data Pump

### Bước 1 — Xác định môi trường

Ghi database, DB_UNIQUE_NAME, PDB, service, host/instance, Oracle release và account chạy Data Pump.

~~~sql
SELECT name, db_unique_name, database_role, open_mode
FROM v$database;

SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

### Bước 2 — Xác định path server

Chọn path server-side theo capacity, backup/retention và security. Xác nhận path tồn tại trên host chạy database và trên các node liên quan nếu RAC.

### Bước 3 — Kiểm tra OS permission

Dùng OS account quản trị phù hợp để kiểm tra directory owner, group, mode, mount, ACL, free space và khả năng đọc/ghi của account Oracle service.

### Bước 4 — Tạo DIRECTORY object

~~~sql
CREATE OR REPLACE DIRECTORY dpump_stage
AS '/u02/oracle/exports';
~~~

Thực hiện bằng principal được cấp CREATE ANY DIRECTORY theo change policy.

### Bước 5 — Grant tối thiểu

~~~sql
GRANT READ, WRITE
ON DIRECTORY dpump_stage
TO app_export;
~~~

Chỉ grant cho user/role được phép sử dụng và kiểm tra bằng chính account chạy Data Pump.

### Bước 6 — Kiểm tra metadata

~~~sql
SELECT directory_name, directory_path
FROM all_directories
WHERE directory_name = 'DPUMP_STAGE';
~~~

Nếu metadata đúng nhưng job vẫn lỗi, tiếp tục kiểm tra OS permission, path mount và container.

### Bước 7 — Chạy thử nhỏ

Export một schema/table test có phạm vi nhỏ, tạo log và dump. Kiểm tra file xuất hiện trên server path, kích thước hợp lý và log kết thúc thành công.

### Bước 8 — Kiểm tra import

Import vào schema/PDB test. Xác nhận object, row count, grants và business result. Không dùng production target cho lần thử đầu.

### Bước 9 — Lưu evidence

Ghi DDL directory, grants, path, OS owner/mode, test log, file size, thời điểm và người thực hiện. Không lưu password hoặc key.

## 16. Runbook: Data Pump job thất bại do directory/file

1. Lưu toàn bộ expdp/impdp output và log nếu có.
2. Xác định job name, owner, service/PDB và directory object.
3. Query ALL_DIRECTORIES/DBA_DIRECTORIES xác nhận mapping.
4. Query directory grants để xác nhận READ/WRITE.
5. Xác nhận OS account Oracle có thể traverse/read/write path.
6. Kiểm tra file tồn tại ở database server, đúng filename và đúng case theo filesystem.
7. Kiểm tra mount, ACL, SELinux, quota và free space.
8. Với RAC, kiểm tra path trên tất cả node worker có thể chạy.
9. Với import, xác nhận mọi dump file part đều hiện diện và có thể đọc.
10. Khắc phục nguyên nhân và chạy lại bằng job mới hoặc ATTACH theo runbook.
11. Kiểm tra log, row count, object status và dữ liệu sau job.
12. Ghi root cause, thời gian gián đoạn và hành động phòng ngừa.

Không xóa job master table, dump file hoặc log khi chưa xác định job state và khả năng resume/attach.

## 17. Những điểm cần cân nhắc về version và deployment

- Data Pump parameter và option có thể khác giữa Oracle release.
- Directory object trong CDB/PDB cần được tạo/grant đúng container.
- RAC yêu cầu path dùng bởi worker phải truy cập được trên node liên quan.
- ASM và filesystem không thể thay thế cho nhau trong mọi workflow; xác nhận loại storage được tính năng hỗ trợ.
- NFS, cloud filesystem và object storage có thể cần integration/tooling riêng.
- Data Pump encryption và một số tính năng có yêu cầu option/license.
- PDB clone/plug/unplug hoặc migration có thể cần điều chỉnh directory mapping theo host đích.
- Oracle Database service account và permission model khác nhau giữa Linux/Unix và Windows.

Luôn dùng SQL Language Reference, Data Pump Utilities Guide và tài liệu platform cho đúng release, không sao chép nguyên một lệnh từ môi trường khác mà không kiểm tra.

## 18. Bài thực hành

Thực hiện trên lab với thư mục riêng và dữ liệu không nhạy cảm.

### Bài 1 — Tạo directory object

Tạo path server, tạo DPUMP_STAGE và query ALL_DIRECTORIES để xác nhận mapping.

### Bài 2 — Thiếu Oracle privilege

Tạo user test không có READ/WRITE, thử Data Pump hoặc UTL_FILE và ghi lại lỗi. Grant đúng privilege rồi thử lại.

### Bài 3 — Thiếu OS permission

Trong lab, đổi permission để Oracle service account không ghi được. Quan sát lỗi và khôi phục permission đúng. Không thử trên path production.

### Bài 4 — Export và log

Export một schema test, dùng DUMPFILE và LOGFILE. Xác nhận vị trí file trên database server.

### Bài 5 — Parameter file

Chạy expdp bằng PARFILE đặt trên client. So sánh path của PARFILE với directory server-side dùng cho dump/log.

### Bài 6 — Multi-file export

Dùng %U, PARALLEL và FILESIZE. Kiểm tra số dump part và import đầy đủ tất cả file.

### Bài 7 — Import vào schema khác

Dùng REMAP_SCHEMA trong PDB lab. Xác nhận user, quota, tablespace và grants.

### Bài 8 — PDB scope

Tạo directory object trong PDB test, query CDB_DIRECTORIES từ root và xác định CON_ID. Kết nối nhầm PDB rồi quan sát khác biệt.

### Bài 9 — RAC visibility

Nếu có RAC lab, thử shared filesystem và path local. So sánh job chạy cluster với CLUSTER=NO theo support của release.

### Bài 10 — UTL_FILE

Tạo file text qua UTL_FILE, đọc lại trong lab và xử lý exception/close file.

### Bài 11 — External table

Tạo external table đọc CSV, kiểm tra READ privilege, OS permission và reject behavior.

### Bài 12 — SQLFILE

Dùng IMPDP SQLFILE để tạo DDL preview, đọc log và review output trước import thật.

## 19. Checklist trước khi export/import

- [ ] Xác nhận đúng database, DB_UNIQUE_NAME, service và PDB.
- [ ] Xác nhận DIRECTORY object tồn tại trong đúng container.
- [ ] Xác nhận directory path là path phía database server.
- [ ] Xác nhận OS account Oracle có quyền traverse/read/write phù hợp.
- [ ] Kiểm tra mount, ACL, filesystem quota và free space.
- [ ] Cấp READ/WRITE DIRECTORY privilege tối thiểu cho account chạy job.
- [ ] Xác nhận quyền export/import schema hoặc full database cần thiết.
- [ ] Xác định vị trí DUMPFILE và LOGFILE.
- [ ] Xác định PARFILE nằm ở máy client.
- [ ] Với RAC, xác nhận path shared hoặc giới hạn cluster theo thiết kế.
- [ ] Với PDB, xác nhận CON_NAME/CON_ID.
- [ ] Dùng DUMPFILE pattern phù hợp khi PARALLEL hoặc nhiều part.
- [ ] Có LOGFILE và lưu exit status/evidence.
- [ ] Kiểm tra dump encryption và credential/key nếu dữ liệu nhạy cảm.
- [ ] Kiểm tra retention và quyền đọc/xóa dump file.
- [ ] Test export/import trên dữ liệu nhỏ trước khi chạy production.
- [ ] Sau import, xác nhận object, row count, grants và business correctness.
- [ ] Không xóa file hoặc drop directory object khi còn consumer/job phụ thuộc.

## 20. Ghi nhớ cốt lõi

- DIRECTORY object ánh xạ một tên logic trong database tới thư mục trên filesystem server.
- CREATE DIRECTORY không tự tạo thư mục OS và không tự cấp quyền filesystem.
- Data Pump dump/log file nằm ở phía database server; PARFILE được client expdp/impdp đọc.
- Oracle READ/WRITE privilege và OS account permission là hai điều kiện độc lập; cả hai phải đúng.
- Export cần quyền ghi dump/log; import cần đọc dump và ghi log/output.
- Directory privilege không cấp quyền SELECT trên bảng; quyền dữ liệu và quyền file là hai lớp khác nhau.
- CREATE ANY DIRECTORY là quyền quản trị mạnh; không cấp cho application runtime.
- DROP DIRECTORY chỉ xóa mapping trong database, không xóa thư mục hoặc file trên OS.
- Thay path của directory object ảnh hưởng mọi consumer và không tự di chuyển file cũ.
- Trong RAC, worker phải nhìn thấy cùng path; dùng shared filesystem hoặc cấu hình job phù hợp như CLUSTER=NO khi cần.
- Trong CDB/PDB, tạo và grant directory trong đúng container, kiểm tra CON_ID.
- UTL_FILE, BFILE và external tables cũng dựa trên DIRECTORY object và OS permissions.
- Dump file có thể chứa dữ liệu nhạy cảm; bảo vệ filesystem, encryption key, log, retention và quyền xóa.
- Data Pump export/import cần cả directory privilege lẫn quyền dữ liệu/schema phù hợp.
- Không nhầm path client với path server; không tìm dump file ở máy chạy expdp nếu DIRECTORY trỏ tới server path.
- Luôn lưu log, kiểm tra exit status và xác minh dữ liệu sau import.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Language Reference — CREATE DIRECTORY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-DIRECTORY.html) — Tạo, thay thế và quản lý DIRECTORY object.
- [Oracle Database Utilities — Data Pump Export and Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/) — DIRECTORY, DUMPFILE, LOGFILE, PARFILE, parallelism, export/import modes và security.
- [Oracle Database PL/SQL Packages and Types Reference — UTL_FILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_FILE.html) — File access qua DIRECTORY object.
- [Oracle Database SecureFiles and Large Objects Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adlob/) — BFILE và external file locators.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Multitenant administration và directory metadata.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — DBA_DIRECTORIES, ALL_DIRECTORIES và CDB_DIRECTORIES.

Directory object behavior, Data Pump parameters, RAC worker placement, PDB scope and encryption options vary by Oracle release and platform. Confirm the exact release documentation and OS service identity; test file access, export, import and recovery in a non-production environment before production use.

