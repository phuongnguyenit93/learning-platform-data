# Export/import theo database, schema, table hoặc tablespace

Oracle Database có nhiều cách di chuyển dữ liệu giữa môi trường, schema hoặc database. Với nhu cầu xuất và nhập dữ liệu logic, công cụ phổ biến là **Oracle Data Pump**, gồm hai tiện ích dòng lệnh **expdp** (export) và **impdp** (import). Data Pump cho phép chọn phạm vi theo toàn database, schema, table hoặc tablespace, lọc object, đổi tên schema/tablespace và theo dõi tiến trình.

Một lựa chọn khác là **transportable tablespaces**, trong đó DBA di chuyển metadata bằng Data Pump và chuyển các datafile của tablespace sang database đích. Cách này khác với export/import logic thông thường và có các điều kiện chặt chẽ về tính tự chứa của tablespace, nền tảng, endian format và phiên bản.

Điều quan trọng là chọn đúng phương pháp:

- Export/import logic phù hợp khi cần di chuyển object và dữ liệu, có thể lọc hoặc remap.
- Transportable tablespaces phù hợp khi cần di chuyển lượng dữ liệu lớn bằng cách chuyển datafile, giảm thời gian unload/load hàng triệu hàng.
- RMAN backup/restore phù hợp cho backup và recovery ở cấp database/datafile; nó không giống Data Pump export/import.

## 1. Data Pump là gì?

Data Pump là cơ chế Oracle dùng để unload metadata và dữ liệu từ database thành dump file, sau đó load chúng vào database khác hoặc database hiện tại. Data Pump chạy theo database server process; client expdp/impdp gửi yêu cầu và theo dõi job.

Luồng export:

~~~text
Database nguồn
      |
      | expdp tạo job
      v
Data Pump server process
      |
      | đọc metadata và dữ liệu
      v
Oracle DIRECTORY object
      |
      v
Dump file (.dmp) + log file
~~~

Luồng import:

~~~text
Dump file (.dmp)
      |
      v
Oracle DIRECTORY object
      |
      | impdp tạo job
      v
Data Pump server process
      |
      | tạo object và nạp dữ liệu
      v
Database đích
~~~

Dump file không phải datafile của Oracle. Nó là định dạng export logic chứa metadata và/hoặc dữ liệu theo phạm vi, bộ lọc và tùy chọn đã chọn. Không thể mount một file DMP như datafile hoặc dùng nó trực tiếp thay cho RMAN backup.

Data Pump có thể ghi một hoặc nhiều dump file, hỗ trợ parallel workers, compression, encryption, metadata filter, data filter, remap và nhiều tính năng khác tùy phiên bản.

## 2. Data Pump và công cụ exp/imp cũ

Oracle từng cung cấp tiện ích export/import truyền thống là exp và imp. Chúng dùng định dạng export cũ và có giới hạn khác với Data Pump.

| Tiêu chí | Data Pump: expdp/impdp | Export/import cũ: exp/imp |
|---|---|---|
| Cơ chế | Server-side jobs và worker processes | Tiện ích export/import truyền thống |
| Dump format | Data Pump dump file | Conventional export dump |
| Parallelism | Có hỗ trợ PARALLEL | Khả năng hạn chế hơn |
| Remap schema/tablespace | Có nhiều tùy chọn hỗ trợ | Khả năng khác và hạn chế hơn |
| Metadata/data filtering | Có INCLUDE, EXCLUDE, QUERY và nhiều filter | Hạn chế hơn |
| Job monitoring | Có Data Pump job views và ATTACH | Không cùng cơ chế |
| Transportable workflow | Tích hợp tốt với transportable tablespaces | Không phải công cụ chính cho workflow hiện đại |

Không dùng expdp để đọc dump được tạo bởi exp cũ hoặc ngược lại. Nếu nhận file export từ hệ thống cũ, cần xác định công cụ và phiên bản đã tạo file trước khi chọn tiện ích import.

## 3. DIRECTORY object và vị trí file

Data Pump đọc/ghi dump file trên máy database server, thông qua Oracle DIRECTORY object. Đường dẫn mà expdp chạy trên máy client không tự động là nơi dump file được tạo.

DBA tạo thư mục ở hệ điều hành, sau đó tạo DIRECTORY object:

~~~sql
CREATE OR REPLACE DIRECTORY dp_dir AS '/u02/oradata/dpump';
~~~

Trên Windows, đường dẫn có thể là:

~~~sql
CREATE OR REPLACE DIRECTORY dp_dir AS 'D:\oracle\dpump';
~~~

Đường dẫn phải tồn tại trên máy database server hoặc storage mà server process có thể truy cập. Oracle software owner cần có quyền đọc/ghi ở tầng hệ điều hành.

Sau đó cấp quyền trên DIRECTORY object:

~~~sql
GRANT READ, WRITE ON DIRECTORY dp_dir TO app_user;
~~~

Quyền READ/WRITE trên DIRECTORY là object privilege của Oracle; nó không tự cấp quyền đọc/ghi filesystem cho Oracle software owner. Cả hai lớp quyền đều phải đúng.

### Kiểm tra DIRECTORY object

~~~sql
SELECT directory_name,
       directory_path
  FROM dba_directories
 WHERE directory_name = 'DP_DIR';
~~~

Xem quyền:

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege
  FROM dba_tab_privs
 WHERE table_name = 'DP_DIR'
 ORDER BY grantee, privilege;
~~~

Tên DIRECTORY thường được lưu dưới dạng chữ hoa nếu tạo không đặt identifier trong dấu nháy kép.

### File ở đâu?

Ví dụ tham số:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=orders_%U.dmp
LOGFILE=orders_export.log
~~~

File được ghi vào đường dẫn được DIRECTORY DP_DIR trỏ tới trên database server. Khi chuyển file sang database đích, phải copy file đến một directory server-side có thể đọc được và tạo DIRECTORY object tương ứng ở database đích.

## 4. Các chế độ export/import chính

Data Pump hỗ trợ các phạm vi export phổ biến:

| Chế độ | Tham số | Phạm vi |
|---|---|---|
| Full database | FULL=YES | Export toàn bộ đối tượng trong phạm vi database/container mà job được kết nối và được phép truy cập |
| Schema | SCHEMAS | Export một hoặc nhiều schema |
| Table | TABLES | Export một hoặc nhiều bảng và object liên quan theo metadata được chọn |
| Tablespace | TABLESPACES | Export các bảng nằm trong một hoặc nhiều tablespace theo phạm vi Data Pump |
| Transportable tablespaces | TRANSPORT_TABLESPACES | Export metadata để di chuyển tablespace cùng datafile theo phương pháp transportable |

Các mode này không hoàn toàn thay thế nhau. Đặc biệt, TABLESPACES=... là một kiểu logical export theo phạm vi tablespace; TRANSPORT_TABLESPACES=... là workflow chuyển datafile, có yêu cầu riêng.

## 5. Export toàn database: FULL=YES

Full export phù hợp khi cần lấy metadata và dữ liệu trên phạm vi toàn database được Data Pump hỗ trợ. Ví dụ:

~~~text
expdp system@ORCL FULL=YES DIRECTORY=DP_DIR DUMPFILE=full_%U.dmp LOGFILE=full_export.log PARALLEL=4
~~~

Lệnh sẽ yêu cầu mật khẩu nếu connect string không chứa mật khẩu. Không đưa mật khẩu thật vào command line, script được commit hoặc log CI/CD.

Có thể dùng parameter file để lệnh dễ đọc và tránh lộ thông tin trong shell history:

~~~text
FULL=YES
DIRECTORY=DP_DIR
DUMPFILE=full_%U.dmp
LOGFILE=full_export.log
PARALLEL=4
FILESIZE=20G
LOGTIME=ALL
METRICS=YES
~~~

Chạy:

~~~text
expdp system@ORCL PARFILE=full_export.par
~~~

FULL=YES cần quyền Data Pump full export phù hợp, thường là role DATAPUMP_EXP_FULL_DATABASE. Không nên dùng SYSDBA cho export thông thường nếu không có yêu cầu và hướng dẫn cụ thể.

### Full export không phải physical backup

FULL=YES xuất object metadata và dữ liệu logic theo khả năng Data Pump. Nó không tạo bản sao byte-for-byte của toàn bộ datafile, control file và online redo. Vì vậy, full export không thay thế RMAN backup.

Một số thành phần hoặc trạng thái đặc biệt có quy tắc riêng và không được hiểu là mọi thứ ở cấp instance đều được xuất. Ví dụ, Data Pump không thay thế việc sao lưu cấu hình listener, password file, wallet, OS scripts, external files hoặc các cấu hình ngoài database.

### Import full database

~~~text
impdp system@TARGET FULL=YES DIRECTORY=DP_DIR DUMPFILE=full_%U.dmp LOGFILE=full_import.log
~~~

Full import có thể tạo hoặc nạp nhiều loại object và user. Phải lập kế hoạch tablespace, user, quyền, database link, directory, job và các object phụ thuộc trước khi chạy. Import full vào database đang có dữ liệu có thể gây xung đột hoặc thay đổi object ngoài dự kiến.

Không coi FULL=YES là cách đồng bộ production an toàn nếu chưa xác định database đích trống hay đang có workload.

## 6. Export/import theo schema: SCHEMAS

Schema mode là cách phổ biến để di chuyển một ứng dụng hoặc nhóm object thuộc một user.

Export một schema:

~~~text
expdp app_owner@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_owner_%U.dmp LOGFILE=app_owner_export.log PARALLEL=2
~~~

Có thể xuất nhiều schema:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER,APP_REPORT DIRECTORY=DP_DIR DUMPFILE=apps_%U.dmp LOGFILE=apps_export.log
~~~

Export schema của chính user thường có thể thực hiện với quyền phù hợp của owner. Export schema khác cần quyền Data Pump phù hợp, chẳng hạn DATAPUMP_EXP_FULL_DATABASE theo phạm vi thao tác.

### Schema mode gồm những gì?

Data Pump có thể xuất các object thuộc schema như:

- Tables và table data.
- Index.
- Constraints.
- Views và materialized views.
- Sequences.
- Procedures, functions và packages.
- Triggers.
- Synonyms.
- Grants và một số metadata liên quan.
- Các object khác được hỗ trợ trong phiên bản.

Không giả định mọi dependency ngoài schema sẽ tự động được xuất. Ví dụ, object tham chiếu đến user/schema khác, database link, external file hoặc directory cần được kiểm tra riêng.

### Import schema

~~~text
impdp system@TARGET SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_owner_%U.dmp LOGFILE=app_owner_import.log
~~~

Nếu schema đích chưa tồn tại, full export hoặc schema import không phải lúc nào cũng tạo user theo cách người vận hành mong đợi nếu thiếu metadata/quyền phù hợp. Hãy xác định user, tablespace mặc định, quota, profile và authentication ở database đích trước.

### Remap schema

Nếu muốn nhập APP_OWNER thành APP_OWNER_TEST:

~~~text
impdp system@TARGET DIRECTORY=DP_DIR DUMPFILE=app_owner_%U.dmp LOGFILE=app_test_import.log REMAP_SCHEMA=APP_OWNER:APP_OWNER_TEST
~~~

REMAP_SCHEMA đổi schema owner của object được import theo phạm vi hỗ trợ. Nó không tự sửa mọi chuỗi hard-code trong source code, dynamic SQL, external configuration hoặc dữ liệu chứa tên schema. Sau remap, kiểm tra synonym, grants, database links, job và ứng dụng.

## 7. Export/import theo table: TABLES

Table mode phù hợp khi chỉ cần một hoặc một số bảng cụ thể:

~~~text
expdp app_owner@ORCL TABLES=ORDERS,ORDER_ITEMS DIRECTORY=DP_DIR DUMPFILE=orders_tables.dmp LOGFILE=orders_tables_export.log
~~~

Có thể chỉ định bảng thuộc schema khác bằng cú pháp owner.table khi tài khoản có quyền:

~~~text
expdp system@ORCL TABLES=APP_OWNER.ORDERS,APP_OWNER.ORDER_ITEMS DIRECTORY=DP_DIR DUMPFILE=orders.dmp LOGFILE=orders_export.log
~~~

Table mode có thể bao gồm metadata của bảng, dữ liệu và một số object phụ thuộc theo cách Data Pump xử lý. Tuy nhiên, không nên mặc định mọi object mà ứng dụng cần đều được xuất cùng một table. Hãy xác định các object liên quan:

- Index và constraint.
- Trigger.
- Grant trên bảng.
- Sequence dùng để sinh khóa.
- View hoặc package tham chiếu bảng.
- Type, synonym và dependent object.
- Partition/subpartition nếu bảng được phân vùng.

### Import một bảng

~~~text
impdp app_owner@TARGET TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders_tables.dmp LOGFILE=orders_import.log
~~~

Nếu bảng đã tồn tại, quyết định cách xử lý bằng TABLE_EXISTS_ACTION:

| Giá trị | Hành vi khái quát |
|---|---|
| SKIP | Bỏ qua bảng đã tồn tại |
| APPEND | Thêm dữ liệu vào bảng hiện có |
| TRUNCATE | Xóa dữ liệu hiện có bằng TRUNCATE rồi nạp lại |
| REPLACE | Drop bảng hiện có rồi tạo lại từ dump trước khi nạp |

Ví dụ:

~~~text
impdp app_owner@TARGET TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders_tables.dmp TABLE_EXISTS_ACTION=APPEND LOGFILE=orders_append.log
~~~

APPEND có thể tạo bản ghi trùng hoặc vi phạm unique constraint nếu dữ liệu đã tồn tại. TRUNCATE và REPLACE có thể phá hủy dữ liệu hoặc object hiện có. Chỉ chọn sau khi xác nhận dữ liệu đích, backup và kế hoạch rollback.

## 8. Export/import theo tablespace: TABLESPACES

TABLESPACES mode là logical export theo các tablespace được chỉ định. Ví dụ:

~~~text
expdp system@ORCL TABLESPACES=USERS,APP_DATA DIRECTORY=DP_DIR DUMPFILE=ts_export_%U.dmp LOGFILE=ts_export.log
~~~

Mode này chọn các bảng nằm trong tablespace được nêu và export metadata/dữ liệu theo cơ chế Data Pump. Nó không tự chuyển nguyên datafile vật lý như transportable tablespaces.

Import:

~~~text
impdp system@TARGET TABLESPACES=USERS,APP_DATA DIRECTORY=DP_DIR DUMPFILE=ts_export_%U.dmp LOGFILE=ts_import.log
~~~

TABLESPACES mode có thể cần quyền Data Pump full database tương ứng khi truy cập object ngoài schema hiện tại. Hãy kiểm tra quyền và phạm vi object thực tế.

### TABLESPACES khác TRANSPORT_TABLESPACES

Đây là khác biệt rất quan trọng:

- TABLESPACES=APP_DATA chọn các object/dữ liệu trong tablespace để export logic.
- TRANSPORT_TABLESPACES=APP_DATA xuất metadata phục vụ chuyển tablespace, trong khi datafile được copy riêng.

Nếu mục tiêu là chuyển lượng dữ liệu rất lớn và muốn tránh unload/load từng hàng, hãy đánh giá transportable tablespaces. Không đổi tham số TABLESPACES thành TRANSPORT_TABLESPACES mà bỏ qua quy trình datafile.

## 9. Lọc object bằng INCLUDE và EXCLUDE

Data Pump hỗ trợ INCLUDE và EXCLUDE để chọn hoặc loại object metadata theo loại object và tên.

Ví dụ chỉ export bảng và index của một schema:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_selected.dmp LOGFILE=app_selected.log INCLUDE=TABLE,INDEX
~~~

Ví dụ loại statistics:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_no_stats.dmp LOGFILE=app_no_stats.log EXCLUDE=STATISTICS
~~~

Có thể dùng object path và điều kiện tên:

~~~text
INCLUDE=TABLE:"LIKE 'ORD_%'"
~~~

Khi truyền biểu thức có dấu nháy, ký tự đặc biệt hoặc shell quoting, cú pháp cần được viết đúng theo shell đang dùng. Parameter file thường dễ kiểm soát hơn command line dài.

Không dùng INCLUDE/EXCLUDE một cách tùy tiện: loại bỏ constraint, sequence, trigger hoặc package có thể khiến dữ liệu import không thể vận hành đúng.

### INCLUDE và EXCLUDE không dùng cùng lúc

Thông thường chọn một trong hai cách lọc cho một job. Hãy đọc tài liệu Data Pump đúng release về object path và quy tắc filter, đặc biệt khi dùng nhiều filter cùng lúc.

## 10. Lọc dữ liệu bằng QUERY

QUERY cho phép lọc hàng được export theo điều kiện SQL cho một bảng. Ví dụ chỉ export đơn hàng từ đầu năm:

~~~text
expdp app_owner@ORCL TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders_2026.dmp LOGFILE=orders_2026.log QUERY=ORDERS:"WHERE ORDER_DATE >= DATE '2026-01-01'"
~~~

Điều kiện phải hợp lệ với bảng và kiểu dữ liệu. Khi dùng nhiều bảng, cần cấu hình query filter đúng object và alias. Hãy kiểm tra cú pháp quoting trên shell thực tế.

QUERY lọc dữ liệu trong dump, nên import sẽ chỉ có hàng được chọn. Không dùng nó nếu cần một bản sao đầy đủ để backup hoặc recovery.

### Consistency khi export

Data Pump export thường đọc dữ liệu theo cơ chế read consistency. Với workload đang thay đổi liên tục, có thể chỉ định FLASHBACK_SCN hoặc FLASHBACK_TIME để export dữ liệu tại một mốc nhất quán nếu điều kiện undo/flashback và quyền đáp ứng.

Ví dụ:

~~~text
expdp app_owner@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_consistent.dmp LOGFILE=app_consistent.log FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 01:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Hoặc dùng SCN đã ghi nhận:

~~~text
FLASHBACK_SCN=123456789
~~~

FLASHBACK_TIME/SCN không phải bảo đảm mọi object ngoài phạm vi export có cùng trạng thái. Nếu undo không đủ để tái dựng snapshot, export có thể thất bại với lỗi snapshot too old hoặc lỗi liên quan. Với ứng dụng có giao dịch liên quan nhiều schema, cần lập kế hoạch consistency toàn bộ dữ liệu và dừng/đóng băng ghi nếu nghiệp vụ yêu cầu.

## 11. Remap tablespace và datafile

Khi import sang database đích, tablespace nguồn có thể không tồn tại hoặc muốn dùng storage layout khác. Có thể dùng REMAP_TABLESPACE:

~~~text
impdp system@TARGET SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_owner.dmp LOGFILE=app_remap_ts.log REMAP_TABLESPACE=APP_DATA:APP_DATA_NEW
~~~

Nếu cần nhiều mapping, có thể chỉ định nhiều tham số REMAP_TABLESPACE. Kiểm tra object được import và tablespace đích đã tồn tại hoặc có đủ điều kiện tạo.

### REMAP_DATAFILE

Trong một số workflow, REMAP_DATAFILE dùng để thay đổi tên/đường dẫn datafile được tham chiếu trong metadata import. Nó không thay thế việc lập kế hoạch storage và không tự chuyển dữ liệu datafile như transportable tablespace.

Ví dụ tham số có thể cần thiết khi import metadata có tham chiếu file path từ nguồn:

~~~text
REMAP_DATAFILE='/u01/oradata/src/users01.dbf':'/u02/oradata/dst/users01.dbf'
~~~

Cú pháp phụ thuộc shell và phiên bản. Chỉ dùng khi metadata chứa datafile path cần remap; với logical schema import thông thường, REMAP_TABLESPACE thường là điều cần xem xét trước.

## 12. TRANSFORM và metadata import

Data Pump có tham số TRANSFORM để thay đổi một số thuộc tính metadata khi import. Ví dụ:

~~~text
impdp system@TARGET SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_owner.dmp LOGFILE=app_transform.log TRANSFORM=SEGMENT_ATTRIBUTES:N
~~~

SEGMENT_ATTRIBUTES:N có thể bỏ qua một số thuộc tính segment như storage clause và tablespace trong metadata theo phạm vi hỗ trợ. Cần hiểu chính xác transform áp dụng cho object nào trong phiên bản đang dùng.

Một số transform thường gặp có thể liên quan:

- SEGMENT_ATTRIBUTES.
- STORAGE.
- OID.
- PCTSPACE.
- TABLESPACE hoặc các transform khác tùy phiên bản.

Không áp dụng TRANSFORM=SEGMENT_ATTRIBUTES:N nếu cần bảo toàn physical storage attributes hoặc muốn object vào đúng tablespace nguồn. Kiểm tra kết quả metadata và storage sau import.

## 13. PARALLEL, dump file template và FILESIZE

Với dữ liệu lớn, Data Pump có thể dùng nhiều worker để tăng throughput:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_%U.dmp LOGFILE=app_parallel.log PARALLEL=4 FILESIZE=10G
~~~

%U là placeholder để Data Pump tạo nhiều dump file có số thứ tự. Khi dùng parallel export, cần đủ dump file để các worker ghi đồng thời.

Import tương ứng:

~~~text
impdp system@TARGET SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_%U.dmp LOGFILE=app_parallel_import.log PARALLEL=4
~~~

PARALLEL không bảo đảm tốc độ tăng tuyến tính. Giới hạn có thể đến từ:

- CPU.
- Storage throughput/IOPS.
- Network nếu dùng network link.
- Số dump file và vị trí file.
- Database resource manager.
- Object dependency và các bước import phải tuần tự.
- Index build hoặc constraint validation.

Không đặt PARALLEL quá cao trên production mà không đo thử. Dùng nhiều worker có thể làm database và storage chịu tải lớn hơn.

### FILESIZE

FILESIZE giới hạn kích thước từng dump file. Khi đạt giới hạn, Data Pump có thể chuyển sang file tiếp theo nếu template cho phép. Nếu dump file chỉ định một tên cố định mà không có đủ file tiếp theo, job có thể thất bại khi không còn chỗ ghi.

Đảm bảo dung lượng filesystem/ASM và quota đủ cho toàn bộ dump set, không chỉ một file.

## 14. Compression và encryption

Data Pump hỗ trợ compression để giảm dung lượng dump và encryption để bảo vệ dữ liệu xuất ra. Tính năng, license requirement và mức compression phụ thuộc phiên bản/edition.

Ví dụ:

~~~text
expdp system@ORCL FULL=YES DIRECTORY=DP_DIR DUMPFILE=full_%U.dmp LOGFILE=full_secure.log COMPRESSION=ALL ENCRYPTION=ALL ENCRYPTION_MODE=PASSWORD
~~~

Với encryption mode dùng password, cần bảo vệ password độc lập và truyền cho import qua quy trình an toàn. Không ghi password vào file parameter được commit hoặc log.

Compression có thể tiêu tốn CPU. Encryption có thể ảnh hưởng throughput và yêu cầu quản lý key. Hãy đo trong môi trường tương đương và kiểm tra quyền sử dụng tính năng theo license.

Không phải mọi giá trị COMPRESSION/ENCRYPTION đều có sẵn trong mọi release hoặc edition. Đọc tài liệu đúng phiên bản và xác nhận quyền sử dụng trước khi áp dụng.

## 15. Network import bằng NETWORK_LINK

Data Pump có thể import trực tiếp từ database nguồn thông qua database link, không cần tạo dump file trung gian trong một số kịch bản:

~~~text
impdp app_user@TARGET NETWORK_LINK=SRC_LINK SCHEMAS=APP_OWNER LOGFILE=network_import.log
~~~

NETWORK_LINK tham chiếu database link có sẵn trong database đích, kết nối đến database nguồn. Cần kiểm tra:

- Database link trỏ đúng nguồn.
- Credential và network route.
- Phiên bản và khả năng tương thích.
- Quyền trên object nguồn.
- Băng thông và độ trễ.
- Tác động workload trên cả nguồn và đích.

NETWORK_LINK không phải cách bỏ qua kiểm soát bảo mật. Database link lưu hoặc sử dụng thông tin xác thực; phải bảo vệ, audit và thu hồi theo chính sách. Với dữ liệu lớn, network import có thể gây tải mạng và database nguồn trong thời gian dài.

## 16. Transportable tablespaces

Transportable tablespaces di chuyển datafile của tablespace thay vì unload/load từng hàng. Data Pump xuất metadata cần thiết; DBA copy datafile sang database đích rồi import metadata.

Workflow khái quát:

~~~text
Database nguồn
   |
   | kiểm tra self-contained
   v
Tablespace set
   |
   | chuyển READ ONLY theo quy trình
   v
Export metadata bằng expdp TRANSPORT_TABLESPACES
   |
   | copy datafile sang đích
   v
Database đích
   |
   | impdp TRANSPORT_DATAFILES
   v
Tablespace được gắn vào database đích
~~~

### Kiểm tra tính self-contained

Transportable tablespace set cần tự chứa: object trong tablespace được chuyển không được có dependency ngoài phạm vi theo các quy tắc transportable của Oracle.

Có thể kiểm tra bằng DBMS_TTS:

~~~sql
BEGIN
  DBMS_TTS.TRANSPORT_SET_CHECK(
    ts_list          => 'APP_DATA,APP_INDEX',
    incl_constraints => TRUE,
    full_check       => TRUE
  );
END;
/

SELECT *
  FROM transport_set_violations;
~~~

Nếu TRANSPORT_SET_VIOLATIONS trả về dòng, cần xử lý dependency hoặc mở rộng tablespace set theo yêu cầu. Một số dependency có thể liên quan index, partition, constraint hoặc object nằm ngoài tablespace.

### Đưa tablespace về READ ONLY

Trong workflow truyền thống, tablespace cần được đưa về READ ONLY để bảo đảm datafile không thay đổi trong khi copy:

~~~sql
ALTER TABLESPACE app_data READ ONLY;
ALTER TABLESPACE app_index READ ONLY;
~~~

Đây là thay đổi ảnh hưởng ứng dụng ghi dữ liệu. Cần có cửa sổ di chuyển và xác nhận không còn transaction cần ghi vào các tablespace.

### Export metadata

~~~text
expdp system@SOURCE DIRECTORY=DP_DIR DUMPFILE=app_transport.dmp LOGFILE=app_transport_export.log TRANSPORT_TABLESPACES=APP_DATA,APP_INDEX
~~~

Tùy phiên bản và chế độ transport, có thể cần thêm tùy chọn VERSION, TRANSPORT_FULL_CHECK hoặc các tham số liên quan. Kiểm tra tài liệu Oracle đúng release.

### Copy datafile

Copy các datafile của tablespace sang vị trí storage mà database đích truy cập được. Có thể dùng công cụ hệ điều hành, storage replication hoặc phương thức truyền file được phê duyệt. Bảo đảm file copy hoàn tất và checksum/size được xác nhận trước import.

### Import metadata và gắn datafile

~~~text
impdp system@TARGET DIRECTORY=DP_DIR DUMPFILE=app_transport.dmp LOGFILE=app_transport_import.log TRANSPORT_DATAFILES='/u02/oradata/app_data01.dbf','/u02/oradata/app_index01.dbf'
~~~

Các đường dẫn phải là vị trí thật trên database đích. Nếu datafile được copy sang ASM hoặc tên file khác, lập kế hoạch map đường dẫn phù hợp.

Sau khi import và xác nhận thành công, có thể đưa tablespace về READ WRITE ở database đích:

~~~sql
ALTER TABLESPACE app_data READ WRITE;
ALTER TABLESPACE app_index READ WRITE;
~~~

Không mở READ WRITE ở cả nguồn và đích cùng lúc nếu hai database đang cùng truy cập cùng một bản datafile. Transportable workflow phải quản lý quyền sở hữu file và thời điểm cutover rõ ràng.

## 17. Transportable và khác endian/platform

Transportable tablespace giữa hai platform có thể yêu cầu chuyển đổi endian format. Kiểm tra platform:

~~~sql
SELECT platform_name,
       endian_format
  FROM v$transportable_platform
 ORDER BY platform_name;
~~~

Kiểm tra platform của database:

~~~sql
SELECT platform_name
  FROM v$database;
~~~

Nếu endian khác, datafile cần được convert bằng phương pháp Oracle hỗ trợ, thường dùng RMAN CONVERT hoặc quy trình convert transportable tablespace tương ứng. Không chỉ copy file rồi import nếu format không tương thích.

Ví dụ khung RMAN:

~~~text
RMAN> CONVERT TABLESPACE app_data
  TO PLATFORM 'Linux x86 64-bit'
  FORMAT '/stage/converted/%U';
~~~

Cú pháp và quy trình convert cụ thể phụ thuộc platform nguồn/đích, Oracle release và vị trí file. Hãy dùng tài liệu transportable tablespaces đúng phiên bản và kiểm tra kết quả conversion trước khi import.

### Version compatibility

Database nguồn và đích cần đáp ứng điều kiện tương thích của Data Pump và transportable tablespace. Tham số VERSION có thể giúp export metadata theo phiên bản đích trong một số trường hợp, nhưng không làm cho tính năng mới hoặc kiểu dữ liệu không được hỗ trợ tự nhiên tương thích với database cũ.

Kiểm tra:

- Oracle release và patch level.
- Character set và national character set.
- Time zone file version.
- Platform và endian.
- Database compatibility setting.
- Các datatype, option và component được dùng.

Không bắt đầu transport khi chưa xác nhận ma trận tương thích nguồn/đích.

## 18. Consistency và thời điểm export

Khi export dữ liệu đang được ứng dụng cập nhật, cần xác định yêu cầu consistency:

- Có thể export theo snapshot nhất quán của Data Pump.
- Có thể dùng FLASHBACK_SCN hoặc FLASHBACK_TIME nếu cần một mốc chung.
- Cần bảo đảm undo retention và dữ liệu undo đủ để tái dựng snapshot.
- Với nhiều schema có quan hệ nghiệp vụ, cần thống nhất cùng một mốc SCN nếu cần consistency xuyên schema.
- Với transportable tablespaces, cần kiểm soát READ ONLY và thời điểm copy datafile.

Một dump file được tạo thành công không tự động bảo đảm các hệ thống ngoài database ở cùng mốc. Ví dụ, file đính kèm trong object storage hoặc message queue có thể thay đổi độc lập. Migration cần ghi nhận các dependency ngoài database.

### FLASHBACK_SCN

Ví dụ:

~~~text
expdp system@ORCL SCHEMAS=APP_OWNER DIRECTORY=DP_DIR DUMPFILE=app_scn.dmp LOGFILE=app_scn.log FLASHBACK_SCN=123456789
~~~

SCN phải được xác định trước và nằm trong khoảng undo/flashback hỗ trợ. Nếu export kéo dài lâu, cần tính đủ thời gian giữ undo.

### FLASHBACK_TIME

~~~text
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 01:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Data Pump chuyển thời gian thành một SCN phù hợp. Cần thống nhất timezone và tránh dùng thời gian mơ hồ khi có daylight saving hoặc host có timezone khác nhau.

## 19. Theo dõi Data Pump job

Data Pump job có thể chạy lâu. Có thể theo dõi bằng:

- Output trực tiếp của expdp/impdp.
- Log file trong DIRECTORY.
- ATTACH để kết nối lại job.
- Data dictionary views.

### ATTACH job

Nếu terminal bị đóng nhưng job vẫn chạy:

~~~text
impdp system@TARGET ATTACH=SYS_IMPORT_SCHEMA_01
~~~

Tên job cần lấy từ output ban đầu hoặc view DBA_DATAPUMP_JOBS. Khi attach, có thể dùng lệnh interactive như STATUS, STOP_JOB, START_JOB hoặc EXIT_CLIENT theo tình huống.

Không nhầm EXIT_CLIENT với STOP_JOB. EXIT_CLIENT chỉ thoát client đang attach; job có thể tiếp tục chạy ở server. STOP_JOB dừng job theo chế độ được chỉ định và có thể cần START_JOB để tiếp tục.

### Xem job

~~~sql
SELECT owner_name,
       job_name,
       operation,
       job_mode,
       state,
       degree,
       attached_sessions
  FROM dba_datapump_jobs
 ORDER BY owner_name, job_name;
~~~

### Xem session Data Pump

~~~sql
SELECT owner_name,
       job_name,
       instance_id,
       session_type,
       saddr
  FROM dba_datapump_sessions
 ORDER BY owner_name, job_name;
~~~

Một số view/cột phụ thuộc phiên bản và quyền truy cập. DBA có thể dùng DBA_DATAPUMP_JOBS, DBA_DATAPUMP_SESSIONS hoặc GV$SESSION để xác định worker/session liên quan.

## 20. Log, METRICS và kiểm soát lỗi

Luôn chỉ định LOGFILE:

~~~text
LOGFILE=app_export.log
LOGTIME=ALL
METRICS=YES
~~~

LOGTIME giúp ghi timestamp vào log theo chế độ được hỗ trợ; METRICS thêm thông tin số liệu object/data được xử lý. Log là bằng chứng quan trọng để điều tra lỗi và xác nhận object nào đã import.

Một job có thể hoàn tất với warning hoặc object bị bỏ qua. Hãy đọc toàn bộ log và tổng hợp:

- Job status.
- Object được export/import.
- Object bị skip hoặc fail.
- ORA- error và thời điểm.
- Số hàng được nạp.
- Thời gian từng giai đoạn.
- Tablespace/schema remap đã áp dụng.

Không chỉ dựa vào exit code của shell hoặc dòng “successfully completed” nếu log còn có lỗi object cần xử lý.

## 21. Các lỗi Data Pump thường gặp

| Mã lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| ORA-39002 | Invalid operation | Xem lỗi đi kèm, mode và tham số |
| ORA-39070 | Không mở được log file | DIRECTORY object, OS permission, đường dẫn và dung lượng |
| ORA-39087 | DIRECTORY object không hợp lệ | Tên DIRECTORY, quyền và container |
| ORA-31640 | Không mở được dump file để đọc | File tồn tại, server path, OS permission, mount và tên file |
| ORA-31693 | Table data object load/unload thất bại | Xem lỗi tiếp theo, table, datatype, space và constraint |
| ORA-39151 | Table tồn tại và bị skip theo hành vi import | TABLE_EXISTS_ACTION và trạng thái object đích |
| ORA-39126 | Worker gặp lỗi không mong đợi | Xem stack, worker trace và lỗi gốc |
| ORA-01031 | Thiếu privilege | DIRECTORY, Data Pump role, object privilege và quyền tạo object |
| ORA-01653 / ORA-01654 | Không mở rộng được segment/index | Tablespace free space, autoextend, quota |
| ORA-01555 | Snapshot too old | Undo retention/size và thời gian export |

Mã lỗi chỉ là điểm bắt đầu. Đọc các dòng trước/sau trong log để tìm lỗi gốc và object cụ thể.

## 22. Quyền cần thiết cho Data Pump

Quyền phụ thuộc mode và phạm vi object:

- User thường cần CREATE SESSION để kết nối.
- User cần READ/WRITE trên DIRECTORY object tương ứng.
- Export schema của chính mình có thể thực hiện với quyền của owner và quyền đọc object thuộc schema đó.
- Export/import schema hoặc object của user khác cần privilege phù hợp.
- Full database export/import thường cần role DATAPUMP_EXP_FULL_DATABASE hoặc DATAPUMP_IMP_FULL_DATABASE tương ứng.
- Tạo user, tablespace hoặc object đặc biệt có thể cần quyền quản trị bổ sung.

Không cấp DBA chỉ để chạy expdp/impdp. Hãy xác định mode, owner, object, directory và operation cụ thể rồi cấp quyền tối thiểu.

Kiểm tra role:

~~~sql
SELECT grantee,
       granted_role
  FROM dba_role_privs
 WHERE grantee IN ('APP_USER', 'SYSTEM')
 ORDER BY grantee, granted_role;
~~~

Với definer-rights PL/SQL hoặc một số thao tác đặc biệt, quyền qua role không thay thế direct grant theo quy tắc Oracle. Tuy nhiên, Data Pump job được chạy theo ngữ cảnh session và quyền phù hợp của user/job; hãy đọc yêu cầu của từng mode thay vì áp dụng máy móc quy tắc PL/SQL.

## 23. Bảo mật dump file

Dump file có thể chứa dữ liệu nhạy cảm, metadata về cấu trúc ứng dụng, tên user, grant và thông tin cấu hình. Bảo vệ dump như một bản sao dữ liệu:

- Giới hạn quyền filesystem và DIRECTORY object.
- Không đặt dump trong web root hoặc thư mục public.
- Mã hóa dump khi dữ liệu cần được bảo vệ.
- Mã hóa kênh truyền file và xác minh nguồn/đích.
- Lưu password encryption/key riêng với dump.
- Đặt retention và quy trình xóa an toàn.
- Không gửi dump qua email hoặc dịch vụ chia sẻ công khai.
- Không đưa password database vào PARFILE hoặc shell history.
- Xóa file tạm sau khi hoàn tất và được phép.

Một user có READ trên DIRECTORY có thể đọc các file thuộc directory qua cơ chế Oracle; không cấp READ/WRITE rộng cho PUBLIC hoặc mọi schema.

## 24. Lập kế hoạch import vào database đích

Trước khi import, cần chuẩn bị:

1. Database đích đã tạo và ở trạng thái phù hợp.
2. PDB/service đích đúng.
3. DIRECTORY object trỏ đến dump file.
4. User/schema đích và authentication.
5. Tablespace, datafile và quota.
6. Character set và compatibility.
7. Quyền role/object cần thiết.
8. Sequence, database link, directory, external file và dependency ngoài schema.
9. Dung lượng datafile, TEMP, UNDO và redo.
10. Kế hoạch xử lý object đã tồn tại.
11. Kế hoạch rollback và kiểm thử sau import.

Không chạy import lớn vào database production đang phục vụ ứng dụng mà chưa đánh giá lock, redo, undo, storage, CPU và ảnh hưởng của DDL.

## 25. Ví dụ workflow schema migration

Giả sử cần chuyển schema APP_OWNER từ database nguồn sang database đích.

### Bước 1: kiểm tra nguồn

- Xác nhận schema và object.
- Xác định dependency ngoài schema.
- Xác định SCN/time nếu cần consistency.
- Kiểm tra dung lượng dump và DIRECTORY.
- Xác nhận quyền export.

### Bước 2: export schema

Tạo file parameter:

~~~text
SCHEMAS=APP_OWNER
DIRECTORY=DP_DIR
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_export.log
PARALLEL=4
FILESIZE=10G
LOGTIME=ALL
METRICS=YES
~~~

Chạy:

~~~text
expdp system@SOURCE PARFILE=app_owner_export.par
~~~

### Bước 3: chuyển dump

Copy tất cả dump piece và log cần lưu sang staging/đích theo kênh được bảo vệ. Xác nhận số file, kích thước và checksum nếu quy trình yêu cầu.

### Bước 4: chuẩn bị đích

- Tạo hoặc xác nhận APP_OWNER.
- Tạo tablespace và quota.
- Tạo DIRECTORY object trỏ tới vị trí dump ở server đích.
- Cấp READ/WRITE trên DIRECTORY.
- Kiểm tra compatibility.

### Bước 5: import

~~~text
impdp system@TARGET PARFILE=app_owner_import.par
~~~

Ví dụ file parameter:

~~~text
SCHEMAS=APP_OWNER
DIRECTORY=DP_DIR
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_import.log
PARALLEL=4
LOGTIME=ALL
METRICS=YES
~~~

Nếu đổi schema hoặc tablespace, thêm REMAP_SCHEMA/REMAP_TABLESPACE theo mapping đã được xác nhận.

### Bước 6: kiểm tra sau import

- Đọc log và xử lý mọi object lỗi.
- Kiểm tra invalid objects.
- Kiểm tra số hàng và tổng dữ liệu quan trọng.
- Kiểm tra index/constraint/trigger.
- Kiểm tra sequence và giá trị sequence tiếp theo.
- Kiểm tra grants, roles, synonyms, database links.
- Kiểm tra scheduler jobs và external dependencies.
- Chạy smoke test ứng dụng.
- Xác nhận connection service và user đúng.

Ví dụ xem invalid objects:

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
  FROM dba_objects
 WHERE owner = 'APP_OWNER'
   AND status = 'INVALID'
 ORDER BY object_type, object_name;
~~~

Không chỉ so sánh tổng số hàng. Hãy kiểm tra các tổng nghiệp vụ, khóa chính, quan hệ tham chiếu và dữ liệu ở các bảng quan trọng.

## 26. Ví dụ workflow table migration

Nếu chỉ cần chuyển một bảng:

Export:

~~~text
expdp app_owner@SOURCE TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders.dmp LOGFILE=orders_export.log
~~~

Import:

~~~text
impdp app_owner@TARGET TABLES=ORDERS DIRECTORY=DP_DIR DUMPFILE=orders.dmp LOGFILE=orders_import.log TABLE_EXISTS_ACTION=SKIP
~~~

Nếu bảng đã tồn tại, chọn SKIP, APPEND, TRUNCATE hoặc REPLACE theo mục tiêu. Trước khi import, kiểm tra:

- Bảng đích có cấu trúc giống nguồn không?
- Có dữ liệu cần giữ không?
- Index và constraint có được import không?
- Trigger có chạy khi load dữ liệu không?
- Sequence có cần đồng bộ không?
- Có bảng cha/con cần chuyển cùng không?
- Có khóa ngoại hoặc trigger tạo side effect không?

Nếu cần dữ liệu nhất quán giữa nhiều bảng có quan hệ, cân nhắc schema export hoặc một SCN chung thay vì export từng bảng ở các thời điểm khác nhau.

## 27. Khi nào chọn mode nào?

| Nhu cầu | Cách chọn thường phù hợp | Lý do |
|---|---|---|
| Di chuyển gần như toàn bộ object database | FULL=YES | Bao phủ phạm vi rộng, cần quyền và kế hoạch đích tương ứng |
| Di chuyển một ứng dụng theo schema | SCHEMAS | Giữ object theo owner, dễ remap schema |
| Chuyển một vài bảng | TABLES | Giảm phạm vi, phù hợp trao đổi dữ liệu chọn lọc |
| Export các bảng thuộc tablespace cụ thể theo logic | TABLESPACES | Chọn object theo vị trí tablespace |
| Chuyển lượng dữ liệu lớn bằng datafile | TRANSPORT_TABLESPACES | Tránh unload/load từng hàng, nhưng có điều kiện transportable |
| Import trực tiếp từ database nguồn | NETWORK_LINK | Có thể tránh dump trung gian, phụ thuộc network và database link |
| Chỉ xuất hàng theo điều kiện | QUERY | Lọc dữ liệu trong dump |
| Chỉ xuất một số loại object | INCLUDE/EXCLUDE | Lọc metadata theo object path |

Lựa chọn cuối cùng cần xét RTO, RPO, dung lượng, downtime, compatibility, consistency, dependency và khả năng rollback.

## 28. Những sai lầm thường gặp

**Nhầm DIRECTORY object với thư mục trên client:** Data Pump server đọc/ghi đường dẫn phía database server. Kiểm tra đúng host và quyền filesystem.

**Dùng FULL=YES như RMAN backup:** Data Pump là logical export, không sao chép toàn bộ physical database files.

**Nhầm TABLESPACES với TRANSPORT_TABLESPACES:** một mode export logic, mode kia chuyển datafile và metadata.

**Chỉ copy một dump piece:** khi dùng %U/PARALLEL, cần chuyển đủ tất cả dump piece.

**Import vào schema đang có dữ liệu mà không chọn TABLE_EXISTS_ACTION:** có thể skip, append, truncate hoặc replace theo hành vi mặc định/option; cần quyết định rõ.

**Dùng REMAP_SCHEMA nhưng quên dependency:** hard-coded schema name, database link, job và external config có thể vẫn trỏ đến nguồn.

**Dùng PARALLEL quá cao:** có thể gây I/O, CPU và TEMP pressure.

**Không dùng FLASHBACK_SCN/TIME khi cần snapshot chung:** các bảng được export ở các thời điểm khác nhau có thể không đáp ứng yêu cầu consistency nghiệp vụ.

**Không kiểm tra quyền DIRECTORY:** user có thể kết nối database nhưng job không mở được dump/log file.

**Không đọc log import:** job có thể hoàn tất nhưng một số object bị skip hoặc lỗi.

**Không kiểm tra sequence và constraint:** dữ liệu có thể import đủ nhưng ứng dụng lỗi khi ghi tiếp.

**Không bảo vệ dump:** dump file có thể chứa dữ liệu nhạy cảm tương đương bản sao database.

## 29. Checklist trước và sau export/import

### Trước export

- [ ] Xác định mode: FULL, SCHEMAS, TABLES, TABLESPACES hay TRANSPORT_TABLESPACES.
- [ ] Xác định database/PDB và service nguồn.
- [ ] Xác nhận owner và quyền Data Pump.
- [ ] Xác nhận DIRECTORY và quyền OS.
- [ ] Xác định dump file naming, FILESIZE và PARALLEL.
- [ ] Đánh giá consistency và FLASHBACK_SCN/TIME.
- [ ] Kiểm tra dung lượng và encryption/compression.
- [ ] Ghi nhận dependency ngoài phạm vi export.

### Trước import

- [ ] Xác nhận dump piece đầy đủ và đọc được.
- [ ] Xác nhận database/PDB/service đích.
- [ ] Chuẩn bị user, role, tablespace và quota.
- [ ] Cấp READ/WRITE DIRECTORY.
- [ ] Kiểm tra compatibility, character set và version.
- [ ] Chọn REMAP_SCHEMA/REMAP_TABLESPACE nếu cần.
- [ ] Xác định TABLE_EXISTS_ACTION và object conflict.
- [ ] Chuẩn bị rollback và cửa sổ thay đổi.

### Sau import

- [ ] Đọc toàn bộ log và lỗi.
- [ ] Kiểm tra object invalid.
- [ ] Kiểm tra row counts và số liệu nghiệp vụ.
- [ ] Kiểm tra index, constraints, triggers và sequences.
- [ ] Kiểm tra grants, synonyms, jobs và database links.
- [ ] Kiểm tra external dependencies.
- [ ] Chạy smoke test và kiểm tra kết nối ứng dụng.
- [ ] Lưu dump, log, checksum và bằng chứng theo retention.

## 30. Kết luận

Oracle Data Pump cung cấp các mode export/import theo database, schema, table và tablespace. FULL=YES phù hợp cho phạm vi rộng; SCHEMAS cho ứng dụng theo owner; TABLES cho một số bảng; TABLESPACES chọn dữ liệu theo tablespace. Cần phân biệt TABLESPACES với TRANSPORT_TABLESPACES: transportable tablespaces chuyển datafile cùng metadata, yêu cầu kiểm tra self-contained, trạng thái READ ONLY, platform/endian và compatibility.

Một quy trình di chuyển an toàn phải chuẩn bị DIRECTORY ở phía database server, quyền Data Pump và filesystem, dump piece, consistency, storage, user/schema, tablespace, remap và dependency. Sau import, đọc log, kiểm tra object, dữ liệu, sequence, constraint, grant, job và smoke test. Dump file cần được bảo vệ như dữ liệu nhạy cảm; Data Pump export/import là cơ chế di chuyển logic, không thay thế RMAN backup/restore.
