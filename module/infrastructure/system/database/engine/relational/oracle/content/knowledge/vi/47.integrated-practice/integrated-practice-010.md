# Di chuyển schema bằng Data Pump và kiểm tra dữ liệu/đối tượng

## 1. Mục tiêu và phạm vi

Oracle Data Pump là bộ công cụ di chuyển dữ liệu logic. Export đọc metadata và row data từ database nguồn, tạo dump file; Import đọc dump file để tạo lại object và nạp dữ liệu vào database đích.

Một lần di chuyển schema hoàn tất không chỉ vì lệnh expdp và impdp kết thúc bình thường. Cần chứng minh đúng schema và tập object đã được chuyển; dữ liệu nhất quán tại một mốc xác định; bảng, partition, LOB, index, constraint và trigger hoạt động; sequence, view, package, synonym và dependency được xử lý; user, role, grant, quota và default tablespace phù hợp; các thành phần ngoài schema được chuyển riêng; ứng dụng kết nối đúng service/PDB và chạy được các luồng nghiệp vụ.

Phương pháp trong bài là schema-mode Data Pump. Nó phù hợp khi chuyển một hoặc nhiều schema giữa hai database, chẳng hạn từ hệ thống cũ sang database mới, giữa hai PDB hoặc từ on-premises lên cloud.

Data Pump là logical migration, không phải physical database clone. Dump file không thay thế RMAN backup, không tự chuyển listener/service của hệ thống và không bảo đảm mọi thành phần ngoài schema được di chuyển.

## 2. Kiến trúc export/import

~~~text
SOURCE DATABASE
      |
      | 1. Kiểm kê schema, dependency, tablespace, quyền
      v
Chọn SCN nhất quán và chuẩn bị export
      |
      | 2. expdp SCHEMAS=...
      v
Dump file + export log
      |
      | 3. Copy/transfer và kiểm tra file
      v
TARGET DATABASE
      |
      | 4. Chuẩn bị user, role, tablespace, quota
      | 5. impdp REMAP_SCHEMA / REMAP_TABLESPACE
      v
Tạo object + nạp dữ liệu
      |
      | 6. Kiểm tra dữ liệu, object, quyền và dependency
      v
Kiểm thử ứng dụng + cutover
~~~

| Thành phần | Vai trò |
| --- | --- |
| expdp | Export metadata/data từ source |
| impdp | Import metadata/data vào target |
| DIRECTORY object | Ánh xạ tên logic tới thư mục trên database server |
| Dump file | Chứa nội dung export theo định dạng Data Pump |
| Log file | Ghi object đã xử lý, warning và lỗi |
| SCHEMAS | Chọn schema cần export/import |
| REMAP_SCHEMA | Đổi owner schema khi import |
| REMAP_TABLESPACE | Đổi tablespace chứa segment |
| FLASHBACK_SCN | Giữ dữ liệu export theo một SCN nhất quán khi được hỗ trợ |

## 3. Phân biệt các chế độ Data Pump

| Mode | Tham số | Phạm vi |
| --- | --- | --- |
| Full | FULL=Y | Phạm vi database theo quyền và filter |
| Schema | SCHEMAS=APP_OWNER | Một hoặc nhiều schema |
| Table | TABLES=APP_OWNER.ORDERS | Một hoặc nhiều table/partition |
| Tablespace | TABLESPACES=APP_DATA | Object thuộc tablespace được chọn |
| Transportable | TRANSPORTABLE | Di chuyển datafile cùng metadata theo điều kiện TTS |

Schema mode phù hợp với bài toán trong bài. Không dùng FULL=Y chỉ để chuyển một schema nếu không có lý do và quyền phù hợp.

INCLUDE và EXCLUDE cho phép lọc object type hoặc object cụ thể. Bộ lọc có thể làm mất dependency nếu dùng không cẩn thận. Trước khi loại một loại object, xác định ứng dụng có phụ thuộc vào nó hay không.

## 4. Kiểm kê source trước khi export

### 4.1. Xác nhận database, service và container

~~~sql
SELECT name,
       dbid,
       open_mode,
       database_role,
       platform_name
FROM v$database;

SHOW CON_NAME;

SELECT sys_context('USERENV', 'SERVICE_NAME') AS service_name,
       sys_context('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

Trong môi trường CDB, Data Pump phải kết nối đúng PDB service nếu schema nằm trong PDB. Không export nhầm từ CDB root hoặc một PDB khác có cùng schema name.

### 4.2. Thông tin schema

~~~sql
SELECT username,
       account_status,
       default_tablespace,
       temporary_tablespace,
       profile,
       created
FROM dba_users
WHERE username = 'APP_OWNER';
~~~

Kiểm tra schema có bị khóa, hết hạn password, dùng profile đặc biệt hoặc có default tablespace không còn tồn tại ở target.

### 4.3. Đếm object theo loại và trạng thái

~~~sql
SELECT owner,
       object_type,
       status,
       COUNT(*) AS object_count
FROM dba_objects
WHERE owner = 'APP_OWNER'
GROUP BY owner, object_type, status
ORDER BY object_type, status;
~~~

Ghi nhận baseline trước export, đặc biệt số lượng TABLE, TABLE PARTITION, TABLE SUBPARTITION, INDEX, INDEX PARTITION, VIEW, MATERIALIZED VIEW, SEQUENCE, PROCEDURE, FUNCTION, PACKAGE, PACKAGE BODY, TRIGGER, TYPE, SYNONYM và DATABASE LINK.

Một số object type hoặc metadata có quy tắc export riêng. Số object trong DBA_OBJECTS là baseline đối chiếu, không phải cam kết mọi row sẽ xuất hiện dưới cùng object type sau import.

### 4.4. Kiểm tra segment và dung lượng

~~~sql
SELECT tablespace_name,
       segment_type,
       COUNT(*) AS segment_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE owner = 'APP_OWNER'
GROUP BY tablespace_name, segment_type
ORDER BY tablespace_name, segment_type;
~~~

Kiểm tra các segment lớn:

~~~sql
SELECT segment_name,
       partition_name,
       segment_type,
       tablespace_name,
       ROUND(bytes / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE owner = 'APP_OWNER'
ORDER BY bytes DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Dung lượng segment không bằng dung lượng dump file. Compression, datatype, LOB và dữ liệu lặp có thể làm kích thước dump khác đáng kể. Target cần đủ dung lượng datafile, TEMP, UNDO, redo, archive log và staging dump.

### 4.5. Kiểm tra tablespace và quota

~~~sql
SELECT tablespace_name,
       status,
       contents,
       block_size,
       bigfile
FROM dba_tablespaces
ORDER BY tablespace_name;

SELECT username,
       tablespace_name,
       bytes,
       max_bytes,
       blocks,
       max_blocks
FROM dba_ts_quotas
WHERE username = 'APP_OWNER'
ORDER BY tablespace_name;

SELECT DISTINCT tablespace_name
FROM dba_segments
WHERE owner = 'APP_OWNER'
ORDER BY tablespace_name;
~~~

Lập bảng ánh xạ source tablespace sang target tablespace. Không mặc định target có cùng tên, cùng block size hoặc cùng dung lượng.

### 4.6. Kiểm tra invalid object trước khi export

~~~sql
SELECT object_type,
       object_name,
       status
FROM dba_objects
WHERE owner = 'APP_OWNER'
  AND status <> 'VALID'
ORDER BY object_type, object_name;

SELECT name,
       type,
       line,
       position,
       text
FROM dba_errors
WHERE owner = 'APP_OWNER'
ORDER BY name, sequence;
~~~

Ghi nhận invalid object có sẵn trước migration. Sau import, cần phân biệt lỗi mới phát sinh với lỗi đã tồn tại ở source.

### 4.7. Dependency giữa schema

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM dba_dependencies
WHERE owner = 'APP_OWNER'
  AND referenced_owner <> 'APP_OWNER'
ORDER BY referenced_owner, referenced_name, name;
~~~

Nếu APP_OWNER gọi package hoặc đọc table của schema khác, schema mode không tự động chuyển toàn bộ schema phụ thuộc đó. Cần chuyển thêm schema phụ thuộc, bảo đảm object đã có ở target, tạo lại synonym/grant/database link phù hợp hoặc thay đổi cấu hình ứng dụng.

### 4.8. Kiểm tra quyền

System privileges:

~~~sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee = 'APP_OWNER'
ORDER BY privilege;
~~~

Role grants:

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
WHERE grantee = 'APP_OWNER'
ORDER BY granted_role;
~~~

Object grants do schema sở hữu cấp cho user khác:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'APP_OWNER'
ORDER BY table_name, grantee, privilege;
~~~

Ghi lại grants cho role và user bên ngoài schema. Khi chỉ export một schema, không mặc định mọi role, system privilege, public synonym, ACL và quyền ngoài schema đều được chuyển đầy đủ.

## 5. Thành phần ngoài schema cần kiểm kê riêng

Schema export chuyển metadata và dữ liệu thuộc schema theo phạm vi Data Pump, nhưng ứng dụng thường phụ thuộc tài nguyên cấp database hoặc hệ điều hành.

| Thành phần | Vì sao cần kiểm tra riêng |
| --- | --- |
| Database user, profile, authentication | User/security policy có thể cần tạo lại hoặc điều chỉnh |
| Roles và system privileges | Role có thể được quản lý tập trung ngoài schema |
| Tablespace và quota | Storage layout ở target có thể khác |
| Public synonym | Là object cấp database |
| Directory object | Trỏ tới filesystem server, không mang theo thư mục/OS file |
| External table và file | File nằm ngoài database |
| Database link | Endpoint, credential và quyền kết nối cần xác nhận |
| Network ACL | Điều khiển UTL_HTTP/UTL_TCP và network access |
| Scheduler credentials | Secret/external credential cần quản lý riêng |
| External jobs | Phụ thuộc executable, OS user và host |
| Service/listener/tnsnames | Thuộc cấu hình kết nối, không phải schema data |
| TDE wallet/keystore | Cần key để đọc dữ liệu được mã hóa |
| Application config | JDBC URL, secret, endpoint, feature flag |
| Backup/monitoring policy | Phải thiết lập cho database đích |

Kiểm tra directory object:

~~~sql
SELECT owner,
       directory_name,
       directory_path
FROM dba_directories
ORDER BY owner, directory_name;
~~~

Kiểm tra database link:

~~~sql
SELECT owner,
       db_link,
       username,
       host
FROM dba_db_links
WHERE owner IN ('APP_OWNER', 'PUBLIC')
ORDER BY owner, db_link;
~~~

Không cố đọc password database link từ dictionary view. Nếu cần tạo lại link, lấy credential từ nguồn bí mật được phê duyệt và xác nhận remote service tồn tại.

Kiểm tra scheduler job:

~~~sql
SELECT owner,
       job_name,
       enabled,
       state,
       job_type,
       program_name,
       schedule_name
FROM dba_scheduler_jobs
WHERE owner = 'APP_OWNER'
ORDER BY job_name;
~~~

Kiểm tra synonym:

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM dba_synonyms
WHERE owner IN ('APP_OWNER', 'PUBLIC')
ORDER BY owner, synonym_name;
~~~

## 6. Chuẩn bị target database

### 6.1. Kiểm tra phiên bản và character set

~~~sql
SELECT banner_full
FROM v$version
WHERE banner_full LIKE 'Oracle Database%';

SELECT parameter,
       value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;

SELECT filename,
       version
FROM v$timezone_file;
~~~

Target cần hỗ trợ metadata và feature do source export tạo ra. Kiểm tra source/target release, Data Pump version, COMPATIBLE, character set, national character set, timezone file và datatype/feature đang sử dụng.

Data Pump có thể thực hiện character-set conversion theo quy tắc Oracle khi nạp dữ liệu logical, nhưng không nên giả định mọi conversion đều không mất dữ liệu. Kiểm tra khả năng biểu diễn ký tự, độ dài cột, semantics BYTE/CHAR và dữ liệu thực tế.

### 6.2. Tạo tablespace đích

~~~sql
CREATE TABLESPACE APP_DATA
DATAFILE '/u02/oradata/DBTARGET/app_data01.dbf'
SIZE 8G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 64G;

CREATE TABLESPACE APP_INDEX
DATAFILE '/u02/oradata/DBTARGET/app_index01.dbf'
SIZE 4G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 32G;
~~~

Đường dẫn và dung lượng chỉ là ví dụ. Với ASM/OMF, dùng destination tương ứng. Xác nhận filesystem/disk group có đủ capacity và autoextend có giới hạn.

### 6.3. Tạo user đích và quota

Nếu đổi schema owner, tạo user đích có default tablespace, temporary tablespace, profile và quota phù hợp:

~~~sql
CREATE USER APP_RUNTIME
IDENTIFIED BY "<password-from-approved-secret-process>"
DEFAULT TABLESPACE APP_DATA
TEMPORARY TABLESPACE TEMP
QUOTA 20G ON APP_DATA
QUOTA 10G ON APP_INDEX;

GRANT CREATE SESSION TO APP_RUNTIME;
~~~

Đây là ví dụ lab. Trong production, không gõ password thật vào script commit/log; cấp quota theo dung lượng được phê duyệt; cấp đúng privilege; có thể tách owner schema và runtime account; xác nhận profile/password policy và account status.

Data Pump có thể nhập metadata user/grant trong một số export/import scope và quyền phù hợp. Tuy vậy, chuẩn bị user, role, quota và security policy rõ ràng giúp tránh phụ thuộc vào việc tự động tạo user hoặc dùng credential mặc định. Nếu chủ động tạo user trước, xem trước DDL bằng SQLFILE và điều chỉnh tham số import/filter để không ghi đè ngoài ý muốn.

### 6.4. Tạo DIRECTORY object cho Data Pump

Directory object trỏ tới thư mục trên database server, không phải thư mục máy client chạy expdp/impdp:

~~~sql
CREATE OR REPLACE DIRECTORY DPUMP_STAGE AS '/u03/dpump';
GRANT READ, WRITE ON DIRECTORY DPUMP_STAGE TO SYSTEM;
~~~

Thư mục /u03/dpump phải tồn tại trên host database và Oracle Database process phải có quyền OS đọc/ghi. User chạy Data Pump cần quyền READ/WRITE trên DIRECTORY object. DIRECTORY object không tự cấp quyền filesystem.

Không cấp READ/WRITE cho PUBLIC. Chọn account vận hành phù hợp và bảo vệ dump file vì file có thể chứa toàn bộ dữ liệu nghiệp vụ.

### 6.5. Kiểm tra target trước import

~~~sql
SELECT tablespace_name,
       status,
       contents
FROM dba_tablespaces
ORDER BY tablespace_name;

SELECT username,
       account_status,
       default_tablespace,
       temporary_tablespace
FROM dba_users
WHERE username IN ('APP_OWNER', 'APP_RUNTIME');
~~~

Đảm bảo target đang ở đúng PDB, user/tablespace tồn tại, storage đủ, directory hợp lệ và service có thể kết nối.

## 7. Chọn SCN nhất quán cho export

### 7.1. Vì sao cần consistency?

Schema có thể tiếp tục thay đổi trong lúc export. Nếu các bảng được đọc ở những thời điểm khác nhau, dữ liệu liên quan có thể không khớp. Ví dụ ORDERS được export trước khi một transaction commit, còn ORDER_LINES được export sau commit; target có thể nhận trạng thái khác nhau giữa hai bảng nếu không dùng một mốc nhất quán phù hợp.

Data Pump hỗ trợ Flashback Query thông qua FLASHBACK_SCN hoặc FLASHBACK_TIME trong các điều kiện được hỗ trợ. Với migration cần đối chiếu dữ liệu, lấy SCN tại thời điểm đã thống nhất và export dữ liệu theo SCN đó.

### 7.2. Lấy SCN

~~~sql
SELECT current_scn
FROM v$database;
~~~

Ghi lại giá trị SCN trong change record và truyền vào expdp. Cần quyền đọc view phù hợp.

### 7.3. FLASHBACK_SCN

~~~text
expdp system@SOURCE_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_owner_export.log
  SCHEMAS=APP_OWNER
  FLASHBACK_SCN=123456789012
  PARALLEL=4
  FILESIZE=10G
  LOGTIME=ALL
  METRICS=YES
~~~

SCN trên chỉ là placeholder. Thay bằng SCN thực tế được ghi nhận trước export.

FLASHBACK_SCN yêu cầu Oracle có đủ undo để đọc dữ liệu tại SCN đó trong suốt quá trình export. Nếu export kéo dài hơn khả năng giữ undo, Data Pump có thể gặp ORA-01555. Vì vậy, kiểm tra thời gian export, undo generation, UNDO_RETENTION và dung lượng trước khi chạy.

### 7.4. FLASHBACK_TIME

Có thể chỉ định thời điểm:

~~~text
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Data Pump chuyển thời điểm thành SCN gần tương ứng. Dùng một trong hai cách theo kế hoạch; không đặt cả FLASHBACK_SCN và FLASHBACK_TIME trong cùng job.

### 7.5. Khi không thể giữ undo đủ lâu

Nếu export dài và source có tải DML lớn:

- Tối ưu thời gian export và storage throughput.
- Dùng dump file nhiều piece/parallel phù hợp.
- Tăng undo theo sizing và kiểm tra retention.
- Chọn maintenance window ít ghi hơn.
- Tạm ngừng writer hoặc đưa ứng dụng vào read-only trong cutover window.
- Xem xét Data Pump network link hoặc phương án migration khác nếu phù hợp.

Không tắt undo hoặc tùy tiện tăng UNDO_RETENTION mà không có dung lượng hỗ trợ.

## 8. Export schema bằng expdp

### 8.1. Tạo parameter file

Dùng parfile để dễ review và lưu lại cấu hình:

~~~text
DIRECTORY=DPUMP_STAGE
DUMPFILE=app_owner_%U.dmp
LOGFILE=app_owner_export.log
SCHEMAS=APP_OWNER
FLASHBACK_SCN=123456789012
PARALLEL=4
FILESIZE=10G
COMPRESSION=ALL
LOGTIME=ALL
METRICS=YES
REUSE_DUMPFILES=NO
~~~

Chạy:

~~~text
expdp system@SOURCE_PDB PARFILE=app_owner_export.par
~~~

Parfile chứa cấu hình, không nên chứa password plaintext. Dùng Oracle Secure External Password Store, prompt tương tác hoặc cơ chế xác thực được tổ chức phê duyệt. Bảo vệ file parfile và log vì chúng có thể tiết lộ thông tin hệ thống.

### 8.2. Ý nghĩa tham số

| Tham số | Vai trò |
| --- | --- |
| DIRECTORY | Directory object chứa dump/log |
| DUMPFILE | Tên file dump; %U tạo nhiều piece |
| LOGFILE | Log export |
| SCHEMAS | Danh sách schema |
| FLASHBACK_SCN | Snapshot SCN cho export |
| PARALLEL | Số worker song song |
| FILESIZE | Giới hạn kích thước mỗi dump piece |
| COMPRESSION | Nén metadata/data theo mức hỗ trợ |
| LOGTIME | Ghi timestamp vào log |
| METRICS | Ghi số liệu object trong log |
| REUSE_DUMPFILES | Có cho phép ghi đè dump file đã tồn tại hay không |

PARALLEL không làm mọi object export song song như nhau. Mức parallel quá cao có thể gây tải CPU/I/O, tăng undo/redo và tạo nhiều file. Chọn theo storage throughput, CPU và giới hạn edition/feature.

### 8.3. Kiểm tra log export

Sau export, kiểm tra:

- Job kết thúc bình thường.
- Không có ORA-, UDE- hoặc LRM- error chưa được xử lý.
- Số lượng object/data được export hợp lý.
- Không có object bị bỏ qua ngoài dự kiến.
- Dump piece đầy đủ và kích thước phù hợp.
- SCN và schema trong log đúng với change record.

Không chỉ dựa vào exit code của shell. Data Pump log là bằng chứng quan trọng.

### 8.4. Export metadata-only để khảo sát

~~~text
expdp system@SOURCE_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_metadata.dmp
  LOGFILE=app_metadata.log
  SCHEMAS=APP_OWNER
  CONTENT=METADATA_ONLY
~~~

Metadata-only hữu ích để xem DDL và dependency trước khi chuyển dữ liệu. Nó không thay thế export đầy đủ.

## 9. Import và remap schema/tablespace

### 9.1. Import cùng schema name

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_owner_import.log
  SCHEMAS=APP_OWNER
  PARALLEL=4
~~~

Schema/user target phải được chuẩn bị theo chính sách. Nếu target đã có object cùng tên, xác định rõ TABLE_EXISTS_ACTION và object conflict trước import.

### 9.2. Đổi schema owner bằng REMAP_SCHEMA

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_runtime_import.log
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  PARALLEL=4
~~~

REMAP_SCHEMA đổi owner của object được import. Nó không tự sửa mọi chuỗi schema name được hardcode trong source code, dynamic SQL, file cấu hình hoặc external integration. Kiểm tra view, procedure, package, trigger, synonym, database link và ứng dụng có tham chiếu tên schema cũ.

### 9.3. Đổi tablespace bằng REMAP_TABLESPACE

~~~text
REMAP_TABLESPACE=APP_DATA:APP_DATA_NEW
REMAP_TABLESPACE=APP_INDEX:APP_INDEX_NEW
~~~

Có thể dùng nhiều mapping. Tablespace đích phải tồn tại hoặc được tạo theo kế hoạch. Kiểm tra partition, LOB, index và segment có tablespace override riêng. Nếu không remap, Data Pump có thể giữ tablespace name cũ trong DDL.

### 9.4. Kết hợp remap

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_runtime_import.log
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  REMAP_TABLESPACE=APP_DATA:APP_DATA_NEW
  REMAP_TABLESPACE=APP_INDEX:APP_INDEX_NEW
  PARALLEL=4
  LOGTIME=ALL
  METRICS=YES
~~~

Đây là ví dụ. Nếu dùng parfile, đặt mỗi REMAP_TABLESPACE trên một dòng theo cú pháp Data Pump. Kiểm tra DDL target bằng SQLFILE trước khi import production.

### 9.5. TABLE_EXISTS_ACTION

Khi table đã tồn tại ở target, TABLE_EXISTS_ACTION điều khiển hành vi:

| Giá trị | Hành vi |
| --- | --- |
| SKIP | Bỏ qua table đã tồn tại |
| APPEND | Thêm row vào table đã tồn tại |
| TRUNCATE | Xóa row hiện tại rồi nạp row mới |
| REPLACE | Drop table hiện tại rồi tạo lại từ dump |

Mặc định thường là SKIP với table đã tồn tại. Không dùng APPEND hoặc TRUNCATE một cách máy móc vì có thể tạo dữ liệu trùng hoặc xóa dữ liệu đích. REPLACE có thể làm mất grant, constraint, trigger hoặc object phụ thuộc nếu không kiểm soát.

Với lần migration đầu tiên, target schema nên sạch hoặc đã được chuẩn bị rõ ràng. Tránh import đè vào schema đang có traffic.

## 10. Xem trước DDL bằng SQLFILE

SQLFILE yêu cầu Data Pump ghi DDL sẽ được thực thi ra file SQL thay vì thực thi import object đó. Nó hữu ích để review schema remap, tablespace, user, grant, storage clause và object creation.

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  SQLFILE=app_owner_preview.sql
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  REMAP_TABLESPACE=APP_DATA:APP_DATA_NEW
~~~

SQLFILE được ghi vào directory server. Review owner, tablespace, DDL drop/replace, reference tới schema cũ, grant cho user/role không tồn tại và object cần external file/directory/credential.

SQLFILE là bản xem trước DDL, không phải kiểm tra dữ liệu. Một số giá trị bí mật có thể được xử lý/ẩn theo cơ chế export; không coi SQLFILE là nguồn credential.

## 11. Các tùy chọn lọc object

### 11.1. INCLUDE và EXCLUDE

Ví dụ chỉ import table và sequence:

~~~text
INCLUDE=TABLE
INCLUDE=SEQUENCE
~~~

Ví dụ loại statistics để gather lại ở target:

~~~text
EXCLUDE=STATISTICS
~~~

Không dùng filter này cho migration hoàn chỉnh nếu chưa xác định view, package, trigger, type, synonym, grant, materialized view và dependency có cần hay không.

Data Pump có object path và filter syntax riêng. Cần tham khảo DATABASE_EXPORT_OBJECTS hoặc SCHEMA_EXPORT_OBJECTS để biết path hợp lệ; không đoán tên object path.

### 11.2. CONTENT

- CONTENT=DATA_ONLY: chỉ nạp row data vào object đã có.
- CONTENT=METADATA_ONLY: chỉ tạo metadata/DDL, không nạp row.
- Bỏ CONTENT: metadata và data theo mode export.

Nếu dùng DATA_ONLY, target table structure phải tương thích và các constraint/trigger có thể ảnh hưởng quá trình nạp. Không tự drop object mà chưa có phương án khôi phục.

## 12. Phương án NETWORK_LINK

Data Pump có thể đọc dữ liệu từ database nguồn qua database link trong một số workflow:

- expdp với NETWORK_LINK đọc remote source và tạo dump file ở nơi export job chạy.
- impdp với NETWORK_LINK có thể đọc remote source và nạp trực tiếp vào target theo điều kiện hỗ trợ.

Ví dụ ý tưởng import trực tiếp:

~~~text
impdp system@TARGET_PDB
  NETWORK_LINK=SOURCE_LINK
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  LOGFILE=network_import.log
~~~

SOURCE_LINK là database link được tạo trên target và kết nối tới source. Cần kiểm tra quyền database link, network connectivity, version compatibility, datatype và Data Pump restrictions.

Ưu điểm là không cần staging toàn bộ dump file ở client. Hạn chế là phụ thuộc network throughput/latency, credential và quyền database link, khó lưu dump artifact để kiểm toán, và có giới hạn version/object/parallelism tùy workflow.

Chọn dump file khi cần artifact có thể checksum, lưu trữ, scan, chuyển qua vùng staging hoặc import lại. Chọn NETWORK_LINK khi topology và policy cho phép và đã thử tải thực tế.

## 13. Mã hóa dump file và bảo vệ dữ liệu

Dump file có thể chứa dữ liệu nhạy cảm. Bảo vệ filesystem ACL, owner của Oracle process, quyền DIRECTORY object, transfer channel, backup/staging retention và encryption.

Data Pump hỗ trợ tham số encryption theo phiên bản/edition và cấu hình:

~~~text
ENCRYPTION=ALL
ENCRYPTION_MODE=PASSWORD
ENCRYPTION_PASSWORD=<supplied-securely>
~~~

Ví dụ chỉ minh họa. Không ghi encryption password trong parfile commit vào Git, shell history hoặc ticket. Dùng prompt/cơ chế secret được phê duyệt; xác nhận target có thể giải mã dump. Một số chế độ encryption yêu cầu TDE/keystore hoặc có giới hạn edition/version.

Nếu dump file đã mã hóa bằng password, lưu password trong secret store riêng và bàn giao qua kênh bảo mật. Mất encryption password có thể khiến dump không thể import.

## 14. Kiểm tra dữ liệu sau import

Import log không chứng minh dữ liệu nghiệp vụ đúng. Cần so sánh source và target tại cùng snapshot hoặc trong cửa sổ source đã ngừng ghi.

### 14.1. Số lượng table

~~~sql
SELECT COUNT(*) AS table_count
FROM dba_tables
WHERE owner = 'APP_RUNTIME'
  AND nested = 'NO';
~~~

Đối chiếu số table source/target theo cùng quy tắc lọc. Không so sánh tổng object count mà bỏ qua partition/subpartition hoặc nested table.

### 14.2. Exact row count

DBA_TABLES.NUM_ROWS là thống kê optimizer, không nhất thiết là row count hiện tại. Sau import, statistics có thể cũ hoặc không được gather. Với bảng quan trọng, dùng COUNT(*) tại source/target:

~~~sql
SELECT COUNT(*) AS row_count
FROM APP_OWNER.ORDERS;
~~~

Nếu đổi schema:

~~~sql
SELECT COUNT(*) AS row_count
FROM APP_RUNTIME.ORDERS;
~~~

Với nhiều bảng, tạo danh sách bảng được kiểm tra và chạy COUNT(*) theo từng bảng. Không dùng dynamic SQL từ input không tin cậy; quote schema/table identifier đúng quy tắc Oracle.

### 14.3. Snapshot nhất quán khi so sánh

Nếu source tiếp tục ghi trong lúc target được import, COUNT(*) tại hai thời điểm khác nhau có thể khác dù export đúng. Cần so sánh tại cùng SCN bằng Flashback Query khi undo còn đủ, dừng writer và so sánh trong cutover window, hoặc dùng CDC/replication để bắt kịp delta trước cutover.

Không dùng số row hiện tại ở source sau migration để so với target đã export ở SCN cũ mà không tính các transaction phát sinh sau SCN.

### 14.4. So sánh dữ liệu theo nghiệp vụ

Row count là cần thiết nhưng chưa đủ. Với bảng nghiệp vụ quan trọng, so sánh tổng amount/quantity, MIN/MAX business key, số trạng thái theo nhóm, số NULL ở cột bắt buộc, tổng row theo ngày/tháng/partition, duplicate business key và orphan row.

Ví dụ:

~~~sql
SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS amount_sum,
       MIN(order_id) AS min_order_id,
       MAX(order_id) AS max_order_id
FROM APP_RUNTIME.ORDERS
GROUP BY status
ORDER BY status;
~~~

Lấy cùng báo cáo trên source tại snapshot phù hợp và đối chiếu. Nếu kiểu dữ liệu/rounding khác nhau, xác định tolerance nghiệp vụ thay vì so chuỗi format.

### 14.5. Hash/checksum dữ liệu

Với bảng quan trọng, có thể tạo digest theo key range hoặc partition để so sánh. Hash phải được tính trên cột có thứ tự và canonical representation rõ ràng; không nối chuỗi tùy tiện vì NULL, delimiter, timezone, number formatting và character encoding có thể gây collision logic.

Ví dụ khái niệm:

~~~sql
SELECT STANDARD_HASH(
           TO_CHAR(order_id) || '|' ||
           NVL(status, '<NULL>') || '|' ||
           TO_CHAR(total_amount, 'FM9999999999990D00',
                   'NLS_NUMERIC_CHARACTERS=.,'),
           'SHA256'
       ) AS row_hash
FROM APP_RUNTIME.ORDERS
WHERE order_id BETWEEN 1 AND 100000
ORDER BY order_id;
~~~

Đây là ví dụ minh họa. Cần thiết kế canonical encoding cho mọi datatype; với CLOB/BLOB, timestamp with time zone và dữ liệu lớn, cần hàm/tiến trình digest riêng. Hash không thay thế kiểm tra row count, constraint và nghiệp vụ.

### 14.6. Partition và LOB

~~~sql
SELECT table_name,
       partition_name,
       num_rows,
       tablespace_name
FROM dba_tab_partitions
WHERE table_owner = 'APP_RUNTIME'
ORDER BY table_name, partition_position;

SELECT owner,
       table_name,
       column_name,
       segment_name,
       tablespace_name,
       securefile
FROM dba_lobs
WHERE owner = 'APP_RUNTIME'
ORDER BY table_name, column_name;
~~~

Kiểm tra đúng partition/subpartition và LOB segment. Một bảng có tổng row count đúng vẫn có thể thiếu partition, sai tablespace hoặc LOB storage attributes.

## 15. Kiểm tra object sau import

### 15.1. Object count theo loại/trạng thái

~~~sql
SELECT object_type,
       status,
       COUNT(*) AS object_count
FROM dba_objects
WHERE owner = 'APP_RUNTIME'
GROUP BY object_type, status
ORDER BY object_type, status;
~~~

So sánh với baseline source sau khi đổi owner logic. Điều tra object thiếu, thừa hoặc INVALID.

### 15.2. Invalid object và compile errors

~~~sql
SELECT object_type,
       object_name,
       status
FROM dba_objects
WHERE owner = 'APP_RUNTIME'
  AND status <> 'VALID'
ORDER BY object_type, object_name;

SELECT name,
       type,
       line,
       position,
       text
FROM dba_errors
WHERE owner = 'APP_RUNTIME'
ORDER BY name, sequence;
~~~

Nếu invalid do dependency được tạo sau, compile lại sau khi hoàn tất import:

~~~sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema      => 'APP_RUNTIME',
        compile_all => FALSE
    );
END;
/
~~~

Với nhiều schema hoặc invalid phức tạp, dùng quy trình compile phù hợp và kiểm tra lại DBA_ERRORS. Không che invalid bằng cách chỉ chạy compile mà không đọc lỗi.

### 15.3. Index

~~~sql
SELECT index_name,
       table_name,
       index_type,
       uniqueness,
       status,
       tablespace_name
FROM dba_indexes
WHERE owner = 'APP_RUNTIME'
ORDER BY table_name, index_name;

SELECT index_name,
       partition_name,
       status,
       tablespace_name
FROM dba_ind_partitions
WHERE index_owner = 'APP_RUNTIME'
ORDER BY index_name, partition_position;
~~~

Kiểm tra index unusable, partition index chưa usable, index bị bỏ qua hoặc không tạo được do quota/tablespace.

### 15.4. Constraint

~~~sql
SELECT table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred
FROM dba_constraints
WHERE owner = 'APP_RUNTIME'
ORDER BY table_name, constraint_name;
~~~

Các giá trị cần chú ý: ENABLED/DISABLED, VALIDATED/NOT VALIDATED, DEFERRABLE/NOT DEFERRABLE, trạng thái foreign key và unique/primary key. Kiểm tra cả số lượng lẫn trạng thái.

### 15.5. Trigger

~~~sql
SELECT trigger_name,
       table_name,
       status,
       triggering_event,
       trigger_type
FROM dba_triggers
WHERE owner = 'APP_RUNTIME'
ORDER BY table_name, trigger_name;
~~~

Trigger có thể làm thay đổi dữ liệu khi ứng dụng chạy test. Khi validation, tránh chạy DML thử trên production schema nếu chưa hiểu side effect.

### 15.6. View và materialized view

~~~sql
SELECT object_name,
       status
FROM dba_objects
WHERE owner = 'APP_RUNTIME'
  AND object_type IN ('VIEW', 'MATERIALIZED VIEW')
ORDER BY object_type, object_name;
~~~

Materialized view cần kiểm tra refresh mode, refresh group/job, materialized view log và dependency. Import object không bảo đảm dữ liệu materialized view được refresh đúng thời điểm.

### 15.7. Sequence và identity

~~~sql
SELECT sequence_name,
       min_value,
       max_value,
       increment_by,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM dba_sequences
WHERE sequence_owner = 'APP_RUNTIME'
ORDER BY sequence_name;
~~~

LAST_NUMBER có thể phản ánh giá trị đã cấp phát/cache boundary chứ không nhất thiết là giá trị NEXTVAL chính xác tiếp theo. So sánh sequence chỉ bằng LAST_NUMBER có thể gây kết luận sai.

Khi migration cần bảo toàn thứ tự cấp ID:

1. Dừng writer hoặc khóa đường tạo ID ở source.
2. Ghi nhận high-water mark theo quy trình đã kiểm thử.
3. Import sequence definition.
4. Kiểm tra target NEXTVAL không thấp hơn ID đã sử dụng ở source.
5. Điều chỉnh sequence nếu cần, có kiểm soát INCREMENT/CACHE/CYCLE.
6. Mở writer ở target sau khi xác nhận.

Với identity column, kiểm tra metadata identity và giá trị sinh ID sau import bằng test trong transaction có thể rollback hoặc bảng thử. Không reset sequence/identity tùy tiện vì có thể tạo duplicate key.

### 15.8. Grants và quota

~~~sql
SELECT grantee,
       table_name,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'APP_RUNTIME'
ORDER BY grantee, table_name, privilege;

SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee = 'APP_RUNTIME'
ORDER BY privilege;

SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
WHERE grantee = 'APP_RUNTIME'
ORDER BY granted_role;

SELECT username,
       tablespace_name,
       bytes,
       max_bytes
FROM dba_ts_quotas
WHERE username = 'APP_RUNTIME'
ORDER BY tablespace_name;
~~~

Nếu schema đổi owner, object grant cũ có thể cần cấp lại cho user/role target. Xác nhận ứng dụng dùng đúng account và quyền hiệu lực.

## 16. Kiểm tra dependency và thành phần ứng dụng

### 16.1. Dependency nội bộ schema

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM dba_dependencies
WHERE owner = 'APP_RUNTIME'
ORDER BY name, referenced_owner, referenced_name;
~~~

Tìm dependency còn trỏ tới schema cũ:

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM dba_dependencies
WHERE owner = 'APP_RUNTIME'
  AND referenced_owner = 'APP_OWNER'
ORDER BY name;
~~~

Đây là dấu hiệu để điều tra, không phải mọi reference đều sai: schema mới có thể cố ý đọc schema cũ hoặc dùng database link.

### 16.2. Dynamic SQL

DBA_DEPENDENCIES không thể phát hiện đầy đủ tên schema được ghép trong dynamic SQL, stored string, Java code, configuration file hoặc scheduler command. Search source code/configuration và kiểm thử các luồng nghiệp vụ.

### 16.3. Scheduler job

~~~sql
SELECT owner,
       job_name,
       enabled,
       state,
       job_type,
       job_action,
       schedule_name
FROM dba_scheduler_jobs
WHERE owner = 'APP_RUNTIME'
ORDER BY job_name;
~~~

Job có thể được import nhưng cần tắt trước cutover để tránh chạy đồng thời ở source và target. Chỉ enable tại target khi đã chuyển quyền vận hành.

### 16.4. Database link và network ACL

Kiểm tra DB link host, service và credential. Network ACL cần được tạo/điều chỉnh theo target host/user. Test UTL_HTTP/UTL_TCP bằng endpoint kiểm thử được phê duyệt.

### 16.5. External table và file

External table phụ thuộc file nằm trên filesystem hoặc object storage. Data Pump không copy các file external đó. Copy file, kiểm tra directory object, OS permissions và credential/ACL ở target.

### 16.6. Public synonym và public grant

Public synonym và public privilege có phạm vi database. Nếu ứng dụng dùng chúng, tạo lại theo change script riêng sau khi kiểm tra tên không xung đột và owner target đúng.

## 17. So sánh source và target có hệ thống

### 17.1. Tạo migration manifest

Trước khi export, lưu manifest có:

- Source DB/PDB/service và target DB/PDB/service.
- Schema nguồn/đích.
- SCN export.
- Danh sách tablespace source-to-target.
- Object counts theo type/status.
- Segment sizes theo tablespace/type.
- Row count hoặc business aggregates của bảng trọng yếu.
- Sequence/identity high-water notes.
- Grants, roles, quotas và dependencies ngoài schema.
- Dump file list, size và checksum.
- Export/import log path và timestamp.

Manifest là baseline để đối chiếu. Không đặt password, token hoặc encryption password vào manifest.

### 17.2. Checksum file

Sau khi copy dump file sang target, tính checksum bằng công cụ hệ điều hành:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'D:\dpump\app_owner_01.dmp'
~~~

So sánh hash source và target cho từng piece. Checksum chỉ xác nhận file copy không bị thay đổi; nó không chứng minh nội dung dump logic đúng hoặc mọi object đã import.

### 17.3. Ma trận validation

| Nhóm | Source baseline | Target check | Điều kiện chấp nhận |
| --- | --- | --- | --- |
| Database/PDB | DB name, service, SCN | Đúng target service/PDB | Kết nối đúng nơi |
| Schema | Owner, status, default TS | Owner target, quota, status | User và quyền hợp lệ |
| Tables | Table/partition count | DBA_TABLES/DBA_TAB_PARTITIONS | Không thiếu object ngoài kế hoạch |
| Data | Exact count/aggregate tại SCN | Exact count/aggregate | Khớp theo snapshot |
| Index | Count/status/partition | DBA_INDEXES/DBA_IND_PARTITIONS | Không unusable ngoài kế hoạch |
| Constraint | Type/status/validated | DBA_CONSTRAINTS | Đúng semantics |
| Program units | Object status/errors | DBA_OBJECTS/DBA_ERRORS | VALID hoặc exception được chấp nhận |
| Sequence | Definition/high-water | DBA_SEQUENCES và test NEXTVAL | Không sinh ID trùng |
| Grants | System/role/object grants | DBA_*_PRIVS | Account đủ quyền, không thừa quyền |
| Dependency | Cross-schema refs | DBA_DEPENDENCIES và app tests | Không còn reference ngoài dự kiến |
| External | Jobs, links, files, ACL | Kiểm tra riêng | Được tạo lại và an toàn |
| Application | Business smoke tests | Test trên target | Luồng nghiệp vụ đạt |

## 18. Kế hoạch cutover

### 18.1. Trước cutover

1. Hoàn tất rehearsal trên môi trường staging.
2. Chốt downtime và người chịu trách nhiệm.
3. Xác nhận backup source và target.
4. Xác nhận dump file/checksum đã sẵn sàng.
5. Kiểm tra target capacity, service, account và monitoring.
6. Tắt hoặc pause scheduler/job có thể chạy trùng.
7. Chuẩn bị cấu hình ứng dụng trỏ target.
8. Xác định cách rollback và điều kiện rollback.

### 18.2. Cutover có downtime

~~~text
1. Stop application writers
2. Stop/pause background jobs and integrations
3. Record final SCN or freeze source writes
4. Run final expdp (or final delta method)
5. Transfer and verify dump files
6. Run impdp on target
7. Validate row counts, objects, grants and dependencies
8. Enable target jobs and integrations deliberately
9. Point application to target service
10. Run smoke tests and monitor
11. Declare target primary for writes
~~~

Nếu đã export full schema trước đó và source vẫn ghi sau SCN, dump không chứa các thay đổi sau SCN. Cần final export hoặc cơ chế delta/CDC để bắt kịp. Chỉ đổi JDBC URL mà không xử lý delta sẽ làm mất các giao dịch phát sinh sau snapshot.

### 18.3. Cutover giảm downtime

Có thể dùng initial export/import rồi đồng bộ thay đổi cuối bằng replication/CDC hoặc một chiến lược delta được hỗ trợ. Data Pump không phải công cụ CDC liên tục. Phải xác định cách capture INSERT/UPDATE/DELETE sau initial SCN, giữ thứ tự transaction, xử lý DDL, đồng bộ sequence và scheduler, thời điểm dừng writer và áp dụng delta cuối, và cách xác nhận source/target đã bắt kịp.

Không tự ghép export nhiều lần rồi APPEND dữ liệu nếu chưa có logic deduplication và ordering.

## 19. Rollback plan

Rollback phải được thiết kế trước khi chuyển traffic:

- Giữ source database và schema ở trạng thái có thể phục hồi trong khoảng thời gian chấp nhận.
- Lưu dump file, log, manifest và checksum.
- Không drop source schema ngay sau cutover.
- Ghi nhận thời điểm target bắt đầu nhận write.
- Nếu target đã nhận write, không chỉ chuyển URL về source vì source sẽ thiếu transaction mới.
- Xác định cách reverse-sync hoặc reconcile dữ liệu nếu phải quay lại source.
- Tắt job/integration ở một phía để tránh gửi event hoặc chạy batch hai lần.
- Kiểm tra sequence/identity khi rollback.

Trước khi target nhận write, rollback có thể đơn giản là đưa ứng dụng về source. Sau khi target nhận write, rollback là bài toán đồng bộ dữ liệu hai chiều hoặc phục hồi từ log/CDC, không còn là thao tác đổi connection string đơn giản.

## 20. Lỗi Data Pump thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-39002 invalid operation | Tham số/job không hợp lệ hoặc mode không tương thích | Đọc lỗi đi kèm và kiểm tra parfile |
| ORA-39070 unable to open log file | DIRECTORY/path/OS permission | Kiểm tra directory object, path và Oracle process permissions |
| ORA-39087 directory name invalid | DIRECTORY object không tồn tại hoặc tên sai | Tạo/kiểm tra DIRECTORY và quyền |
| ORA-31655 no data or metadata objects selected | Filter/schema không khớp hoặc không có quyền nhìn thấy object | Kiểm tra SCHEMAS, INCLUDE/EXCLUDE và quyền |
| ORA-39151 table exists | Table đã có ở target và action là SKIP | Dọn target hoặc chọn TABLE_EXISTS_ACTION sau khi đánh giá |
| ORA-31684 object already exists | Metadata object đã tồn tại | Xác định object nào được giữ/recreate |
| ORA-01918 user does not exist | Schema owner chưa có ở target hoặc import user metadata không theo kế hoạch | Chuẩn bị user/remap và xem SQLFILE |
| ORA-00959 tablespace does not exist | Tablespace source chưa có mapping | Tạo target TS hoặc REMAP_TABLESPACE |
| ORA-01653 unable to extend table | Target tablespace thiếu dung lượng/quota | Kiểm tra datafile, autoextend, quota và storage |
| ORA-01031 insufficient privileges | Account chạy Data Pump thiếu quyền | Cấp quyền phù hợp hoặc dùng account quản trị được phê duyệt |
| ORA-01555 during export | Undo không đủ để giữ snapshot export | Giảm thời gian export, tăng undo có sizing, chọn window khác |
| ORA-39126 worker unexpected fatal error | Worker gặp lỗi ở object/metadata cụ thể | Đọc stack/log đầy đủ và cô lập object gây lỗi |
| ORA-39083 object creation failed | DDL object cụ thể lỗi do dependency, privilege hoặc syntax | Đọc failing SQL trong log/SQLFILE và xử lý nguyên nhân |
| Invalid objects after import | Dependency/grant/version khác | Tạo dependency, compile và kiểm tra DBA_ERRORS |
| Row count mismatch | SCN khác nhau, object thiếu, filter hoặc load lỗi | Đối chiếu snapshot, log, filter và bảng cụ thể |

Không bỏ qua lỗi object chỉ để job có trạng thái hoàn tất. Một import có warning có thể chấp nhận nếu lỗi đã được hiểu, xử lý riêng và ghi trong manifest; mọi lỗi không giải thích được phải chặn cutover.

## 21. Lab: di chuyển schema APP_OWNER sang APP_RUNTIME

Lab chạy trong hai database/PDB thử nghiệm. Không dùng schema production hoặc password thật.

### 21.1. Tạo source schema và bảng

~~~sql
CREATE USER APP_OWNER
IDENTIFIED BY "LabOnlyPassword"
DEFAULT TABLESPACE USERS
QUOTA UNLIMITED ON USERS;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW,
      CREATE SEQUENCE, CREATE PROCEDURE, CREATE TRIGGER
TO APP_OWNER;
~~~

Kết nối bằng APP_OWNER:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE SEQUENCE customers_seq START WITH 1001 INCREMENT BY 1;

CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

INSERT INTO customers(customer_id, customer_name)
VALUES (1, 'Customer A');

INSERT INTO customers(customer_id, customer_name)
VALUES (2, 'Customer B');

INSERT INTO orders(order_id, customer_id, status, total_amount)
VALUES (101, 1, 'NEW', 120.50);

INSERT INTO orders(order_id, customer_id, status, total_amount)
VALUES (102, 2, 'PAID', 350.00);

COMMIT;
~~~

### 21.2. Ghi nhận baseline

~~~sql
SELECT COUNT(*) AS customer_count FROM customers;
SELECT COUNT(*) AS order_count FROM orders;

SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders
GROUP BY status
ORDER BY status;
~~~

Ghi nhận object list, schema name, tablespace và SCN source.

### 21.3. Export

Tạo DIRECTORY object và parfile theo môi trường lab. Chạy:

~~~text
expdp system@SOURCE_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_owner_export.log
  SCHEMAS=APP_OWNER
  FLASHBACK_SCN=<SCN_FROM_SOURCE>
  PARALLEL=2
  LOGTIME=ALL
  METRICS=YES
~~~

Thay placeholder SCN bằng giá trị thực. Kiểm tra log và file.

### 21.4. Tạo target user

~~~sql
CREATE USER APP_RUNTIME
IDENTIFIED BY "AnotherLabPassword"
DEFAULT TABLESPACE USERS
QUOTA UNLIMITED ON USERS;

GRANT CREATE SESSION TO APP_RUNTIME;
~~~

Trong lab có thể dùng USERS cho cả object. Production nên tạo tablespace riêng và quota rõ ràng.

### 21.5. Xem SQLFILE

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  SQLFILE=app_preview.sql
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
~~~

Review DDL trước import.

### 21.6. Import

~~~text
impdp system@TARGET_PDB
  DIRECTORY=DPUMP_STAGE
  DUMPFILE=app_owner_%U.dmp
  LOGFILE=app_runtime_import.log
  SCHEMAS=APP_OWNER
  REMAP_SCHEMA=APP_OWNER:APP_RUNTIME
  PARALLEL=2
  LOGTIME=ALL
  METRICS=YES
~~~

### 21.7. Đối chiếu dữ liệu

Trên target:

~~~sql
SELECT COUNT(*) AS customer_count
FROM APP_RUNTIME.CUSTOMERS;

SELECT COUNT(*) AS order_count
FROM APP_RUNTIME.ORDERS;

SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM APP_RUNTIME.ORDERS
GROUP BY status
ORDER BY status;
~~~

So sánh với baseline source. Kiểm tra constraint, sequence, object status và grants.

### 21.8. Kiểm thử ứng dụng

Thử login bằng runtime account, SELECT customer/order, INSERT order trong transaction test rồi rollback, kiểm tra foreign key, sequence/ID generation và procedure/view nếu lab có tạo.

Không chỉ xác nhận số row; phải xác nhận ứng dụng có thể thực hiện nghiệp vụ đúng với quyền runtime.

## 22. Checklist trước khi tuyên bố migration hoàn tất

1. **Source đúng chưa?** Database, PDB, service và schema owner.
2. **Target đúng chưa?** Database/PDB/service và version compatibility.
3. **Baseline đã lưu chưa?** SCN, object count, row count, aggregates và grants.
4. **Dependency ngoài schema đã nhận diện chưa?** Cross-schema references, links, ACL, directory và jobs.
5. **Tablespace mapping rõ chưa?** Segment, LOB, partition và quota.
6. **Undo đủ cho FLASHBACK_SCN chưa?** Đánh giá thời gian export và undo workload.
7. **Dump file đủ chưa?** Tất cả piece, checksum và dung lượng.
8. **Export log sạch chưa?** Mọi warning/error đã được phân loại.
9. **SQLFILE đã review chưa?** Owner, tablespace, DDL và grant.
10. **Import log đã kiểm tra chưa?** Không bỏ qua object creation failure.
11. **Schema/user/role đã sẵn sàng chưa?** Profile, quota, grants và secret.
12. **Dữ liệu đã đối chiếu chưa?** Exact counts và business aggregates cùng snapshot.
13. **Object đã kiểm tra chưa?** Invalid, index, constraint, trigger, view, package.
14. **Sequence/identity đã kiểm tra chưa?** Không sinh ID trùng.
15. **Scheduler và integration đã kiểm soát chưa?** Không chạy job hai nơi.
16. **External file/directory đã chuyển chưa?** Kiểm tra filesystem và ACL.
17. **Application smoke test đạt chưa?** Đúng service/PDB và runtime privileges.
18. **Cutover window và rollback rõ chưa?** Source writer, target writer và delta.
19. **Backup/monitoring target đã sẵn sàng chưa?** Có thể vận hành sau cutover.
20. **Owner nghiệp vụ đã chấp nhận chưa?** Ký xác nhận dữ liệu và luồng nghiệp vụ.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Data Pump là logical hay physical migration?

**Câu 2.** SCHEMAS khác FULL=Y như thế nào?

**Câu 3.** DIRECTORY object trỏ tới thư mục nào?

**Câu 4.** Vì sao phải kiểm kê dependency ngoài schema?

**Câu 5.** FLASHBACK_SCN bảo đảm điều gì trong export?

**Câu 6.** Vì sao export với FLASHBACK_SCN có thể gặp ORA-01555?

**Câu 7.** REMAP_SCHEMA làm gì và không làm gì?

**Câu 8.** REMAP_TABLESPACE dùng để làm gì?

**Câu 9.** TABLE_EXISTS_ACTION=REPLACE có rủi ro gì?

**Câu 10.** SQLFILE hữu ích ở bước nào?

**Câu 11.** Vì sao DBA_TABLES.NUM_ROWS không phải exact count?

**Câu 12.** Vì sao source và target cần được so sánh tại cùng SCN hoặc trong cửa sổ dừng ghi?

**Câu 13.** Vì sao DBA_SEQUENCES.LAST_NUMBER không nhất thiết là NEXTVAL chính xác?

**Câu 14.** Những thành phần nào không tự động được chuyển chỉ bằng schema mode?

**Câu 15.** Vì sao scheduler job cần được kiểm soát khi cutover?

**Câu 16.** Checksum dump file chứng minh điều gì?

**Câu 17.** Vì sao invalid object cần được so với baseline source?

**Câu 18.** Hai local transaction ở hai database có tự atomic không?

**Câu 19.** Vì sao rollback sau khi target nhận write phức tạp hơn trước cutover?

**Câu 20.** Điều kiện nào cần đạt trước khi chuyển application traffic?

<details>
<summary>Gợi ý đáp án</summary>

1. Logical migration: Data Pump export/import metadata và row data.
2. SCHEMAS chọn một/nhiều schema; FULL chọn phạm vi database.
3. Thư mục trên database server mà Oracle process có quyền OS đọc/ghi.
4. Schema có thể gọi object, role, link hoặc tài nguyên do schema khác/database quản lý.
5. Export dữ liệu theo snapshot SCN được chọn trong điều kiện Flashback Query hỗ trợ.
6. Undo cần để đọc snapshot có thể bị tái sử dụng trước khi export hoàn tất.
7. Đổi owner object khi import; không tự sửa mọi hardcoded schema reference trong code/external config.
8. Ánh xạ tablespace source sang target.
9. Drop và tạo lại table, có thể ảnh hưởng dữ liệu, grant và dependency target.
10. Xem trước DDL import để review remap, tablespace, user và object.
11. Đây là optimizer statistics, có thể cũ hoặc chưa được gather.
12. Tránh so sánh hai trạng thái dữ liệu ở thời điểm khác nhau.
13. Sequence cache và allocation khiến LAST_NUMBER có thể là high-water boundary.
14. Listener/service, external files, directory OS, ACL, wallet, application config và một số public/database-level metadata.
15. Tránh chạy cùng job ở source và target, gây gửi event hoặc xử lý batch hai lần.
16. Xác nhận file không bị thay đổi trong quá trình copy; không chứng minh nội dung logical đúng.
17. Phân biệt invalid đã tồn tại với invalid phát sinh sau migration.
18. Không; cần JTA/XA hoặc một mô hình phân tán như saga/outbox.
19. Target có transaction mới mà source chưa có; đổi URL về source sẽ làm mất hoặc tách dữ liệu.
20. Data, object, grants, dependencies, sequences, application smoke tests và rollback plan đều được chấp nhận.

</details>

## 24. Tài liệu Oracle chính thức

1. [Oracle Database 19c Database Utilities — Oracle Data Pump Overview](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-overview.html): kiến trúc, export/import modes và job.
2. [Oracle Database 19c Database Utilities — Data Pump Export](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): expdp, schema mode, Flashback và dump parameters.
3. [Oracle Database 19c Database Utilities — Data Pump Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html): impdp, REMAP_SCHEMA, REMAP_TABLESPACE, TABLE_EXISTS_ACTION và SQLFILE.
4. [Oracle Database 19c Database Utilities — Data Pump Export Parameters](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): filter, parallel, compression và consistency parameters.
5. [Oracle Database 19c Database Utilities — Data Pump Import Parameters](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html): import filters, remap và network link.
6. [Oracle Database 19c Administrator's Guide — Managing Users and Security](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): users, roles, privileges và secure credential management.
7. [Oracle Database 19c Reference — DBA_OBJECTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_OBJECTS.html): inventory và object status.
8. [Oracle Database 19c Reference — DBA_DEPENDENCIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DEPENDENCIES.html): dependency giữa database objects.
9. [Oracle Database 19c SQL Language Reference — STANDARD_HASH](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/STANDARD_HASH.html): tạo hash để hỗ trợ đối chiếu dữ liệu.

**Nguyên tắc cần nhớ:** Di chuyển schema bằng Data Pump phải bắt đầu từ inventory và một snapshot nhất quán, sau đó export/import với remap có kiểm soát. Kiểm tra row count, business aggregates, object status, index, constraint, sequence, grants và dependency; xử lý riêng directory, external file, database link, ACL, scheduler, wallet và application configuration. Chỉ cutover khi dữ liệu đã đối chiếu tại cùng mốc, ứng dụng chạy đúng trên target và rollback plan đã rõ.
