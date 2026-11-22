# ORA-01652, ORA-01653 và lỗi không đủ vùng tạm hoặc lưu trữ

## 1. Phân biệt lỗi thiếu TEMP và thiếu tablespace dữ liệu

Oracle cần không gian lưu trữ cho cả dữ liệu lâu dài lẫn các thao tác trung gian. Hai lỗi thường gặp có ý nghĩa khác nhau:

- **ORA-01652**: Oracle không thể mở rộng một temporary segment trong tablespace được nêu trong lỗi. Thường gặp khi sort, hash join, hash aggregation, tạo index, temporary table hoặc một thao tác cần ghi dữ liệu trung gian ra TEMP.
- **ORA-01653**: Oracle không thể mở rộng segment của một table trong tablespace được nêu trong lỗi. Đây thường là thiếu chỗ trong permanent tablespace chứa bảng.

Ví dụ dạng thông báo:

```text
ORA-01652: unable to extend temp segment by 128 in tablespace TEMP
ORA-01653: unable to extend table APP.ORDERS by 8192 in tablespace APP_DATA
```

Con số `128` hoặc `8192` trong thông báo là số block mà Oracle muốn cấp thêm cho segment tại thời điểm lỗi; không phải số MB/GB. Muốn quy đổi ra dung lượng cần biết block size của tablespace.

Không nên xử lý cả hai lỗi bằng cùng một thao tác. Nếu lỗi xảy ra ở TEMP, thêm datafile vào permanent tablespace của bảng không giải quyết được vấn đề. Nếu bảng không thể mở rộng trong `APP_DATA`, tăng TEMP cũng không làm permanent segment có thêm chỗ.

## 2. TEMP tablespace và temporary segment

### 2.1. TEMP được dùng khi nào?

Oracle dùng temporary tablespace để lưu các dữ liệu trung gian vượt quá vùng nhớ làm việc được cấp cho một thao tác. Các tình huống thường gặp:

- `ORDER BY`, `GROUP BY`, `DISTINCT` cần sort lớn.
- Hash join hoặc hash aggregation có dữ liệu lớn và spill ra TEMP.
- Tạo hoặc rebuild index.
- Một số thao tác tạo bảng, partition, materialized view hoặc xử lý dữ liệu trung gian.
- Global temporary table hoặc thao tác khác được thiết kế dùng temporary segment.

Một câu SQL có thể chỉ dùng PGA khi vùng nhớ đủ, nhưng khi workarea không đủ, Oracle có thể spill một phần hoặc toàn bộ dữ liệu trung gian xuống TEMP. Vì vậy, TEMP usage phụ thuộc SQL, execution plan, lượng dữ liệu, concurrency và cấu hình PGA/workarea.

### 2.2. TEMP khác PGA

PGA là vùng nhớ riêng của server process để xử lý sort, hash và các thao tác workarea. TEMP là không gian trên storage để chứa phần dữ liệu trung gian không thể giữ trong memory. Hai thành phần liên quan nhưng không thay thế nhau.

| Thành phần | Vai trò | Dấu hiệu cần điều tra |
|---|---|---|
| PGA/workarea | Xử lý sort/hash trong bộ nhớ | PGA pressure, workarea chạy multipass, memory allocation |
| TEMP tablespace | Lưu phần sort/hash/temp segment spill ra đĩa | ORA-01652, TEMP usage tăng, tempfile hết khả năng mở rộng |
| Permanent tablespace | Lưu table/index/LOB segment lâu dài | ORA-01653, ORA-01654, ORA-01691 |
| Undo tablespace | Lưu undo record cho rollback/read consistency | ORA-30036, undo space pressure |

Nếu gặp `ORA-04030`, đây là lỗi không cấp phát được PGA memory cho process, khác với `ORA-01652` thiếu temporary segment. Nếu gặp `ORA-30036`, điều tra undo tablespace thay vì chỉ tăng TEMP.

### 2.3. Temporary segment được giải phóng khi nào?

Temporary segment có thể được dùng trong suốt thời gian thao tác hoặc transaction cần nó. Khi câu SQL/transaction hoàn tất, Oracle có thể tái sử dụng các extent đã cấp phát cho TEMP; do đó quan sát thấy tempfile vẫn có dung lượng đã cấp phát không có nghĩa toàn bộ dung lượng đó đang bị một session chiếm giữ.

TEMP tempfile thường giữ kích thước đã được cấp trên storage để phục vụ lần sử dụng sau. Cần phân biệt dung lượng tempfile đã cấp phát, dung lượng đang dùng và dung lượng còn có thể mở rộng.

## 3. Permanent tablespace và segment mở rộng

### 3.1. ORA-01653 thường liên quan đối tượng nào?

Thông báo `ORA-01653` chỉ rõ table không thể mở rộng trong tablespace. Segment có thể đang cần extent mới do:

- Insert thêm dữ liệu.
- Update làm dòng dài hơn và cần thêm block/extent.
- Partition hoặc subpartition tăng trưởng.
- Một thao tác tạo dữ liệu khiến table segment tăng kích thước.

Các lỗi gần nghĩa khác giúp xác định loại segment:

| Mã lỗi | Đối tượng/tình huống thường gặp |
|---|---|
| `ORA-01652` | Temporary segment không thể mở rộng trong TEMP hoặc tablespace được nêu |
| `ORA-01653` | Table segment không thể mở rộng |
| `ORA-01654` | Index segment không thể mở rộng |
| `ORA-01658` | Không thể tạo initial extent cho segment trong tablespace |
| `ORA-01691` | LOB segment không thể mở rộng |
| `ORA-01950` | User không có quota phù hợp trên tablespace |
| `ORA-30036` | Undo segment không thể mở rộng trong undo tablespace |

Thông báo lỗi là manh mối đầu tiên. Cần xác định object, owner, tablespace, file và nguyên nhân thực tế trước khi cấp thêm dung lượng.

### 3.2. Tablespace còn free space nhưng vẫn không cấp được extent

Tổng free space không phải lúc nào cũng đủ để giải thích lỗi. Cần kiểm tra:

- Các datafile đã đạt `MAXSIZE` hay chưa.
- `AUTOEXTEND` có bật không.
- Storage filesystem/ASM còn đủ chỗ không.
- Kích thước datafile có chạm giới hạn theo block size/platform không.
- Tablespace dùng uniform extent hay autoallocate; extent cần cấp có phù hợp allocation policy không.
- User có quota đủ không.
- PDB có giới hạn storage được cấu hình không.

Với locally managed tablespace, không nên dùng mô hình free space liên tục như cách xử lý fragmentation của hệ thống cũ. Oracle quản lý extent theo bitmap; tuy nhiên kích thước extent, file capacity và storage underlying vẫn cần kiểm tra.

## 4. Quy trình chẩn đoán ban đầu

### 4.1. Thu thập chính xác lỗi

Ghi lại toàn bộ error stack, không chỉ dòng cuối:

- ORA code và text đầy đủ.
- SQL_ID, SQL text, module/action và client identifier nếu có.
- Thời điểm, service, container/PDB và instance phát sinh lỗi.
- User/schema, object được thao tác và tablespace được nêu trong lỗi.
- Loại thao tác: SELECT, INSERT, UPDATE, CREATE INDEX, CTAS, batch hay maintenance job.
- Lượng dữ liệu và số session chạy đồng thời.

Nếu lỗi đến từ ứng dụng, giữ correlation ID để đối chiếu với `V$SESSION` và alert log. Không log password, bind data nhạy cảm hoặc nội dung LOB chỉ để chẩn đoán dung lượng.

### 4.2. Xác định container và tablespace

Trong SQL*Plus:

```sql
SHOW CON_NAME;

SELECT name, cdb, open_mode
FROM v$database;
```

Trong CDB, hãy xác định đúng PDB nơi SQL chạy. Các truy vấn `DBA_*` từ bên trong PDB thường hiển thị metadata của PDB đó; từ `CDB$ROOT`, dùng các view `CDB_*` và `CON_ID` để phân biệt container. Không so sánh số liệu của các PDB khác nhau mà bỏ qua `CON_ID`.

### 4.3. Kiểm tra loại tablespace

```sql
SELECT tablespace_name,
       contents,
       status,
       bigfile,
       extent_management,
       allocation_type,
       block_size
FROM dba_tablespaces
ORDER BY tablespace_name;
```

`CONTENTS` cho biết `PERMANENT`, `TEMPORARY` hoặc `UNDO`; `BIGFILE` cho biết tablespace có một datafile/tempfile lớn hay nhiều file nhỏ; `BLOCK_SIZE` giúp quy đổi block trong thông báo lỗi ra byte.

## 5. Chẩn đoán ORA-01652: thiếu TEMP

### 5.1. Xem TEMP đang dùng và còn trống

`V$TEMP_SPACE_HEADER` cung cấp số liệu theo tempfile:

```sql
SELECT tablespace_name,
       file_id,
       ROUND(bytes_used / 1024 / 1024, 2) AS used_mb,
       ROUND(bytes_free / 1024 / 1024, 2) AS free_mb,
       ROUND((bytes_used + bytes_free) / 1024 / 1024, 2) AS file_mb
FROM v$temp_space_header
ORDER BY tablespace_name, file_id;
```

Tổng hợp theo TEMP tablespace:

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes_used) / 1024 / 1024, 2) AS used_mb,
       ROUND(SUM(bytes_free) / 1024 / 1024, 2) AS free_mb,
       ROUND(SUM(bytes_used + bytes_free) / 1024 / 1024, 2) AS allocated_mb
FROM v$temp_space_header
GROUP BY tablespace_name
ORDER BY tablespace_name;
```

Số liệu này phản ánh dung lượng tempfile đã được cấp và phần đang dùng/còn trống trong các file hiện có. Nó chưa cho biết chắc chắn tempfile còn có thể autoextend đến đâu; cần đối chiếu `DBA_TEMP_FILES`, `MAXBYTES` và storage underlying.

### 5.2. Xem tempfile, AUTOEXTEND và MAXSIZE

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 2) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 2) AS max_mb,
       increment_by
FROM dba_temp_files
ORDER BY tablespace_name, file_id;
```

Các cột quan trọng:

- `BYTES`: kích thước tempfile hiện tại.
- `AUTOEXTENSIBLE`: `YES` nếu file được phép tự tăng.
- `MAXBYTES`: mức tối đa được cấu hình cho file khi autoextend bật.
- `INCREMENT_BY`: số block tăng mỗi lần autoextend.

Nếu `AUTOEXTENSIBLE='NO'`, tempfile không tự tăng. Nếu đã đạt `MAXBYTES`, việc bật autoextend cũng không giúp tăng thêm. Cần kiểm tra dung lượng filesystem/ASM và giới hạn file trước khi thay đổi.

### 5.3. Tìm session đang chiếm TEMP

```sql
SELECT u.username,
       s.sid,
       s.serial#,
       s.status,
       s.sql_id,
       s.module,
       s.action,
       u.tablespace,
       u.segtype,
       u.extents,
       u.blocks,
       ROUND(u.blocks * t.block_size / 1024 / 1024, 2) AS temp_mb
FROM v$tempseg_usage u
JOIN v$session s
  ON s.saddr = u.session_addr
 AND s.serial# = u.session_num
JOIN dba_tablespaces t
  ON t.tablespace_name = u.tablespace
ORDER BY u.blocks DESC;
```

`SEGTYPE` giúp phân biệt loại temporary segment, chẳng hạn sort, hash hoặc temporary table. `SQL_ID`, `MODULE` và `ACTION` giúp tìm câu SQL/ứng dụng đang dùng TEMP. Một session có thể có nhiều dòng segment; tổng hợp theo session hoặc SQL_ID nếu cần báo cáo tổng mức dùng.

Với RAC, dùng `GV$TEMPSEG_USAGE` và `GV$SESSION`, join thêm `INST_ID`:

```sql
SELECT u.inst_id,
       u.username,
       s.sid,
       s.serial#,
       s.sql_id,
       s.module,
       u.tablespace,
       u.segtype,
       ROUND(SUM(u.blocks * t.block_size) / 1024 / 1024, 2) AS temp_mb
FROM gv$tempseg_usage u
JOIN gv$session s
  ON s.inst_id = u.inst_id
 AND s.saddr = u.session_addr
 AND s.serial# = u.session_num
JOIN dba_tablespaces t
  ON t.tablespace_name = u.tablespace
GROUP BY u.inst_id, u.username, s.sid, s.serial#, s.sql_id,
         s.module, u.tablespace, u.segtype
ORDER BY temp_mb DESC;
```

Tên cột và quyền truy cập dynamic performance views cần được xác nhận theo phiên bản và môi trường. Trong CDB/RAC, bổ sung container/instance context khi cần để không nhầm session cùng SID.

### 5.4. Xem hoạt động sort segment

```sql
SELECT tablespace_name,
       current_users,
       total_extents,
       used_extents,
       free_extents,
       max_used_size
FROM v$sort_segment
ORDER BY tablespace_name;
```

View này cho biết tình trạng sort segment ở mức tablespace. Các extent TEMP có thể được tái sử dụng; vì vậy không chỉ dựa vào `USED_EXTENTS` tại một thời điểm để kết luận một query cụ thể đã làm đầy TEMP.

### 5.5. Xác định TEMP tablespace mặc định của user

```sql
SELECT username, temporary_tablespace
FROM dba_users
WHERE username = 'APP_USER';
```

User có thể dùng TEMP tablespace khác với tên được nêu trong một giả định của DBA. Ngoài ra, database có thể có temporary tablespace group. Kiểm tra mapping thực tế và cấu hình session trước khi thêm file vào tablespace không liên quan.

## 6. Chẩn đoán ORA-01653: thiếu permanent tablespace

### 6.1. Xem dung lượng datafile và khả năng tăng

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 2) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 2) AS max_mb,
       increment_by
FROM dba_data_files
ORDER BY tablespace_name, file_id;
```

Nếu file đã chạm `MAXBYTES`, autoextend không còn khả năng tăng. Nếu `AUTOEXTENSIBLE='NO'`, file giữ nguyên kích thước. Cũng cần xác nhận storage còn chỗ; cấu hình `MAXSIZE` lớn hơn không tạo ra dung lượng vật lý.

### 6.2. Tổng dung lượng đã cấp và mức tối đa cấu hình

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS allocated_mb,
       ROUND(SUM(CASE
                   WHEN autoextensible = 'YES' THEN maxbytes
                   ELSE bytes
                 END) / 1024 / 1024, 2) AS configured_max_mb,
       ROUND(SUM(CASE
                   WHEN autoextensible = 'YES'
                   THEN GREATEST(maxbytes - bytes, 0)
                   ELSE 0
                 END) / 1024 / 1024, 2) AS potential_growth_mb
FROM dba_data_files
GROUP BY tablespace_name
ORDER BY tablespace_name;
```

`POTENTIAL_GROWTH_MB` là mức tăng còn lại theo cấu hình file, không phải cam kết storage thực tế còn đủ. Nếu filesystem/ASM hết chỗ, autoextend sẽ thất bại trước khi đạt `MAXBYTES`.

### 6.3. Xem free extent và extent lớn nhất

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS free_mb,
       ROUND(MAX(bytes) / 1024 / 1024, 2) AS largest_free_extent_mb,
       COUNT(*) AS free_extent_count
FROM dba_free_space
GROUP BY tablespace_name
ORDER BY tablespace_name;
```

Đối với locally managed tablespace, tổng free space, allocation policy và khả năng mở rộng file là các yếu tố chính. Nếu thông báo cần một extent lớn hơn free extent hiện có, kiểm tra tablespace allocation type, file growth và giới hạn file. Không nên lập tức chạy `COALESCE`/rebuild chỉ vì tổng free space bị chia thành nhiều extent; với locally managed tablespace, Oracle quản lý extent và không yêu cầu mọi free space phải liên tục như một số mô hình cũ.

### 6.4. Tìm segment lớn nhất trong tablespace

```sql
SELECT owner,
       segment_name,
       partition_name,
       segment_type,
       tablespace_name,
       ROUND(bytes / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE tablespace_name = 'APP_DATA'
ORDER BY bytes DESC
FETCH FIRST 30 ROWS ONLY;
```

Thay `APP_DATA` bằng tablespace thực tế. Kết quả giúp xác định bảng/index/LOB/partition đang chiếm nhiều chỗ. Segment lớn không nhất thiết là nguyên nhân duy nhất; cần kết hợp tốc độ tăng, thời điểm lỗi và object trong error stack.

### 6.5. Kiểm tra quota user

```sql
SELECT username,
       tablespace_name,
       bytes,
       max_bytes
FROM dba_ts_quotas
WHERE username = 'APP_USER'
ORDER BY tablespace_name;
```

Nếu lỗi là `ORA-01950`, user có thể hết quota dù tablespace vẫn còn free space. Cấp thêm quota có kiểm soát:

```sql
ALTER USER app_user QUOTA 5G ON app_data;
```

Chỉ dùng `UNLIMITED` khi chính sách bảo mật và capacity planning cho phép. Quota user là giới hạn riêng, không giống giới hạn datafile/tablespace.

## 7. Kiểm tra storage bên dưới: filesystem, ASM và giới hạn file

### 7.1. Filesystem

Với datafile/tempfile trên filesystem, DBA cần kiểm tra mount point chứa file:

```bash
df -h /u02/oradata
df -i /u02/oradata
```

`df -h` kiểm tra dung lượng block; `df -i` kiểm tra inode. Một filesystem có thể hết inode dù vẫn còn byte trống. Cũng cần kiểm tra quota ở OS, mount read-only, quyền owner/group và storage alert.

Đường dẫn trên chỉ là ví dụ. Dùng đúng mount point thực tế từ `DBA_DATA_FILES` hoặc `DBA_TEMP_FILES`.

### 7.2. ASM disk group

Nếu file nằm trong ASM, kiểm tra disk group từ ASM instance hoặc view được cấp quyền:

```sql
SELECT name,
       state,
       type,
       total_mb,
       free_mb,
       usable_file_mb
FROM v$asm_diskgroup
ORDER BY name;
```

`USABLE_FILE_MB` quan trọng khi ASM dùng redundancy vì dung lượng có thể cấp cho file còn phụ thuộc mirror/redundancy và trạng thái disk group. `FREE_MB` không nhất thiết bằng dung lượng an toàn có thể cấp thêm.

Nếu ASM disk group gần hết chỗ, DBA cần xử lý storage theo quy trình ASM, ví dụ bổ sung disk hoặc cân bằng lại theo thiết kế. Không xóa ASM file thủ công bằng công cụ OS.

### 7.3. Giới hạn datafile và bigfile tablespace

Mỗi datafile có giới hạn kích thước phụ thuộc block size, platform và Oracle release. Khi một file không thể lớn thêm, có thể cần thêm datafile nếu tablespace là smallfile và storage cho phép.

Bigfile tablespace chỉ có một datafile lớn. Không thể thêm nhiều datafile như smallfile; cần resize hoặc bật autoextend cho file hiện có trong giới hạn được hỗ trợ. Kiểm tra cột `BIGFILE` trong `DBA_TABLESPACES` trước khi chọn câu lệnh.

### 7.4. PDB storage limit

Trong CDB, một PDB có thể chịu giới hạn storage theo cấu hình quản trị. Cần xác định PDB nào phát sinh lỗi và hỏi DBA CDB kiểm tra storage limit/container quota nếu tổng dung lượng file có vẻ còn nhưng PDB không được phép mở rộng thêm. Không tự tăng giới hạn PDB khi chưa xác nhận policy cấp tài nguyên.

## 8. Cách khắc phục ORA-01652

### 8.1. Tăng khả năng mở rộng TEMP hiện có

Nếu tempfile chưa bật autoextend và storage còn đủ, có thể bật autoextend với mức tăng và trần rõ ràng:

```sql
ALTER DATABASE TEMPFILE '/u02/oradata/DB/temp01.dbf'
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

Đường dẫn và kích thước chỉ là ví dụ. `MAXSIZE` phải nằm trong giới hạn file, filesystem/ASM và capacity plan. Tránh `MAXSIZE UNLIMITED` khi chưa có cơ chế giám sát storage.

### 8.2. Resize tempfile

```sql
ALTER DATABASE TEMPFILE '/u02/oradata/DB/temp01.dbf'
  RESIZE 20G;
```

Resize tăng kích thước sẽ cần storage vật lý. Resize giảm có thể thất bại nếu phần cuối file đang chứa extent được sử dụng; không shrink trong lúc TEMP còn đang được session dùng.

### 8.3. Thêm tempfile cho smallfile temporary tablespace

```sql
ALTER TABLESPACE temp
  ADD TEMPFILE '/u02/oradata/DB/temp02.dbf'
  SIZE 10G
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

Nếu dùng Oracle Managed Files hoặc ASM, có thể dùng tên file theo cấu hình `DB_CREATE_FILE_DEST`/ASM disk group:

```sql
ALTER TABLESPACE temp
  ADD TEMPFILE '+DATA'
  SIZE 10G
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

Thêm file giúp tăng tổng dung lượng TEMP nhưng không sửa nguyên nhân SQL tạo quá nhiều temporary data. Nếu workload liên tục tăng vượt capacity, cần tối ưu SQL hoặc thiết kế xử lý dữ liệu.

### 8.4. Khi dùng bigfile TEMP tablespace

Bigfile tablespace chỉ có một tempfile. Không thêm tempfile thứ hai như ví dụ smallfile; hãy kiểm tra giới hạn file, storage và resize/autoextend tempfile hiện tại theo khả năng của release.

### 8.5. Giảm nhu cầu TEMP

Điều tra SQL_ID đang dùng TEMP lớn:

- Xem execution plan và actual rows.
- Kiểm tra sort/hash operation, join cardinality và statistics.
- Tránh `SELECT DISTINCT` hoặc `ORDER BY` không cần thiết.
- Đảm bảo predicate lọc sớm và join key phù hợp.
- Kiểm tra index và partition pruning nếu phù hợp.
- Xem query có tạo intermediate result lớn do join sai cardinality hay không.
- Với batch, chia dữ liệu theo key range/partition thay vì xử lý một tập khổng lồ.

Không thêm `PGA_AGGREGATE_TARGET` hoặc `PGA_AGGREGATE_LIMIT` một cách tùy tiện. Tăng PGA có thể giảm spill trong một số trường hợp nhưng còn phụ thuộc tổng memory, số session đồng thời và giới hạn hệ thống. Đo workarea trước khi thay đổi.

## 9. Cách khắc phục ORA-01653

### 9.1. Bật autoextend cho datafile

```sql
ALTER DATABASE DATAFILE '/u02/oradata/DB/app_data01.dbf'
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

Chỉ bật khi storage bên dưới có đủ capacity và mức tối đa được phê duyệt. Autoextend có thể giúp ứng dụng tiếp tục chạy nhưng cũng có thể làm đầy filesystem/ASM nếu không đặt trần và giám sát.

### 9.2. Resize datafile hiện tại

```sql
ALTER DATABASE DATAFILE '/u02/oradata/DB/app_data01.dbf'
  RESIZE 20G;
```

Resize tăng cần đủ dung lượng storage. Với bigfile tablespace, file hiện tại có thể được resize tới giới hạn được Oracle/platform hỗ trợ. Với smallfile, nếu file chạm giới hạn kích thước tối đa thì thêm datafile có thể phù hợp hơn.

### 9.3. Thêm datafile cho smallfile tablespace

```sql
ALTER TABLESPACE app_data
  ADD DATAFILE '/u02/oradata/DB/app_data02.dbf'
  SIZE 10G
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

Với ASM:

```sql
ALTER TABLESPACE app_data
  ADD DATAFILE '+DATA'
  SIZE 10G
  AUTOEXTEND ON NEXT 1G MAXSIZE 30G;
```

Nếu dùng OMF và `DB_CREATE_FILE_DEST` đã được cấu hình, có thể bỏ tên file theo cú pháp Oracle hỗ trợ. Kiểm tra quy ước lưu trữ và tên file trước khi chạy; không dùng một đường dẫn ví dụ trong production.

### 9.4. Bigfile tablespace

Với bigfile tablespace, không thêm datafile thứ hai. Tăng kích thước datafile hiện tại hoặc cấu hình autoextend trong giới hạn hợp lệ. Kiểm tra `DBA_TABLESPACES.BIGFILE` và giới hạn block/file trước khi thực hiện.

### 9.5. Xử lý quota hoặc segment tăng trưởng bất thường

Nếu lỗi thực tế là `ORA-01950`, cấp quota phù hợp cho user thay vì thêm file vào tablespace. Nếu segment tăng bất thường, xác định nguyên nhân dữ liệu hoặc job:

- Bảng log/audit tăng không có retention.
- Batch insert chạy lặp hoặc tạo dữ liệu trùng.
- Index/LOB tăng do workload hoặc thay đổi ứng dụng.
- Partition mới chưa được tạo/đặt tablespace đúng.
- Rebuild index hoặc move table cần thêm chỗ tạm thời.

Không drop table/index hoặc purge dữ liệu chỉ dựa trên kích thước lớn. Phải có owner xác nhận retention, dependency và yêu cầu khôi phục.

## 10. Giải phóng dung lượng an toàn

### 10.1. TEMP usage do query đang chạy

Nếu một query đang dùng TEMP bất thường, trước tiên xác định SQL_ID, session, module và thời gian chạy. Tra cứu execution plan, SQL Monitor (nếu có quyền/license phù hợp) và workarea. Hỏi owner ứng dụng xem query có thể hủy an toàn không.

Không kill session chỉ vì nó đứng đầu danh sách TEMP. Session có thể là batch hợp lệ; kill có thể gây rollback, retry storm hoặc làm ứng dụng lỗi dây chuyền. Chỉ terminate khi có quyết định vận hành và hiểu tác động.

### 10.2. Segment dữ liệu không còn cần thiết

Đối với permanent tablespace, chỉ xóa/archival dữ liệu theo retention đã được phê duyệt. Xóa nhiều dòng tạo undo/redo và không nhất thiết trả ngay toàn bộ dung lượng segment cho tablespace. Có thể cần shrink/move/rebuild theo loại object và điều kiện Oracle, các thao tác này lại cần thêm TEMP/permanent free space.

### 10.3. Recycle bin

Các object đã drop có thể còn trong recycle bin và tiếp tục chiếm dung lượng cho tới khi purge. Kiểm tra:

```sql
SELECT owner,
       original_name,
       object_name,
       type,
       droptime,
       space
FROM dba_recyclebin
ORDER BY droptime;
```

Chỉ purge khi owner/DBA xác nhận không cần flashback drop hoặc khôi phục object. `PURGE DBA_RECYCLEBIN` có phạm vi rộng; ưu tiên purge đúng object/tablespace khi có phê duyệt và hiểu rõ khả năng phục hồi bị mất.

### 10.4. Không xóa tempfile bằng hệ điều hành

Tempfile phải được quản lý qua SQL/Oracle. Không dùng `rm`, PowerShell `Remove-Item` hoặc công cụ OS để xóa file đang được Oracle quản lý. Nếu cần drop tempfile, dùng câu lệnh Oracle phù hợp và xác nhận file không còn được dùng.

## 11. TEMP tablespace group và phân bổ cho user

Oracle có thể cấu hình temporary tablespace group để phân phối nhu cầu TEMP giữa nhiều temporary tablespace. Kiểm tra:

```sql
SELECT tablespace_name, group_name
FROM dba_tablespace_groups
ORDER BY group_name, tablespace_name;

SELECT username, temporary_tablespace
FROM dba_users
ORDER BY username;
```

Nếu user dùng tablespace group, việc thêm tempfile vào một thành viên có thể tăng capacity của group, nhưng vẫn cần kiểm tra storage, load distribution và tình trạng các member. Không thay default temporary tablespace của toàn database chỉ để xử lý lỗi của một user nếu chưa đánh giá các session khác.

## 12. Giám sát trong CDB và RAC

### 12.1. CDB/PDB

Trong CDB, cùng một tên tablespace có thể xuất hiện ở nhiều container. Từ root, dùng view `CDB_*` có `CON_ID` để biết file thuộc PDB nào:

```sql
SELECT con_id,
       tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM cdb_temp_files
ORDER BY con_id, tablespace_name, file_id;
```

Với permanent datafile:

```sql
SELECT con_id,
       tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM cdb_data_files
ORDER BY con_id, tablespace_name, file_id;
```

Kiểm tra đúng PDB phát sinh lỗi và giới hạn storage của PDB. Không thêm file vào root hoặc PDB khác chỉ vì chúng có cùng tên tablespace.

### 12.2. RAC

Trong RAC, các instance có thể dùng chung TEMP tablespace/datafiles nhưng session và TEMP usage được quan sát theo instance. Dùng `GV$SESSION`, `GV$TEMPSEG_USAGE` và `INST_ID` để tìm session trên node nào. Cần tránh kill hoặc chẩn đoán nhầm session có cùng SID ở instance khác.

### 12.3. Thiết lập cảnh báo

Theo dõi:

- TEMP used/free và tốc độ tăng theo giờ cao điểm.
- Datafile allocated/current/max bytes và autoextend status.
- Filesystem/ASM usable capacity.
- Tablespace growth và top segment theo owner/object.
- TEMP usage theo SQL_ID, module và session.
- Undo usage và long-running transaction nếu lỗi liên quan undo.
- PDB storage limit và phân bố dung lượng giữa PDB.

Thiết lập cảnh báo trước khi dung lượng đạt 100%, với ngưỡng theo headroom thực tế và thời gian cần để bổ sung storage. Không chỉ cảnh báo theo phần trăm; một tablespace tăng rất nhanh có thể cần cảnh báo dù tỷ lệ hiện tại còn thấp.

## 13. Ví dụ quy trình xử lý sự cố

### 13.1. Ví dụ ORA-01652 trong báo cáo lớn

1. Lấy SQL_ID từ log ứng dụng hoặc `V$SESSION`.
2. Xem `V$TEMPSEG_USAGE` để xác định session/SQL_ID đang dùng TEMP.
3. Kiểm tra `V$TEMP_SPACE_HEADER` và `DBA_TEMP_FILES` để xác định free space, autoextend và max size.
4. Kiểm tra filesystem/ASM và PDB limit.
5. Xem execution plan, sort/hash operation, cardinality estimate và query result size.
6. Nếu cần khôi phục dịch vụ ngay, tăng TEMP có kiểm soát sau khi storage được xác nhận đủ.
7. Sau đó tối ưu SQL, giảm dữ liệu trung gian hoặc chia batch; theo dõi TEMP usage sau khi triển khai.

### 13.2. Ví dụ ORA-01653 khi insert vào bảng đơn hàng

1. Đọc đầy đủ lỗi để xác định owner/table/tablespace.
2. Xác nhận PDB và tablespace là permanent.
3. Kiểm tra `DBA_DATA_FILES`, `AUTOEXTENSIBLE`, `MAXBYTES` và free extent.
4. Kiểm tra quota user, ASM/filesystem và PDB storage limit.
5. Kiểm tra segment/partition tăng trưởng, top objects và tốc độ tăng dữ liệu.
6. Nếu cần capacity, resize hoặc thêm datafile cho smallfile; bigfile thì resize/autoextend file hiện có.
7. Xác nhận insert tiếp tục được và đặt cảnh báo/retention để tránh tái diễn.

## 14. Checklist trước khi thay đổi dung lượng

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Lỗi là ORA-01652 hay ORA-01653? | Xác định TEMP hay permanent segment |
| Tablespace thuộc PDB nào? | Tránh thay đổi nhầm container |
| Tablespace là TEMP/PERMANENT/UNDO? | Chọn đúng datafile hay tempfile |
| AUTOEXTEND đang bật? | Kiểm tra từng file, không chỉ tablespace |
| Đã đạt MAXBYTES hoặc file limit? | Xác định còn khả năng tăng theo cấu hình |
| ASM/filesystem còn đủ chỗ? | Xác nhận storage vật lý và usable capacity |
| Tablespace là BIGFILE? | Chọn resize hay add file đúng loại |
| User có quota? | Phân biệt ORA-01950 với thiếu tablespace |
| SQL/session nào đang dùng TEMP? | Xác định nguyên nhân và owner trước khi hủy query |
| Dung lượng tăng do dữ liệu hợp lệ hay bất thường? | Xác nhận retention, partition, batch và job |
| Đã có phương án giám sát? | Đặt ngưỡng cảnh báo và headroom sau thay đổi |

## 15. Nguyên tắc cần ghi nhớ

- ORA-01652 thường liên quan temporary segment/TEMP; ORA-01653 thường liên quan table segment trong permanent tablespace.
- TEMP usage, tempfile allocated size và free storage trên disk là ba số liệu khác nhau.
- `V$TEMPSEG_USAGE`, `V$TEMP_SPACE_HEADER` và `DBA_TEMP_FILES` giúp điều tra TEMP; `DBA_DATA_FILES`, `DBA_FREE_SPACE` và `DBA_SEGMENTS` giúp điều tra permanent tablespace.
- `AUTOEXTEND` chỉ hoạt động trong giới hạn `MAXSIZE`, file/platform và storage underlying.
- Bigfile tablespace không thêm datafile thứ hai như smallfile; phải xem xét resize/autoextend file hiện có.
- Kiểm tra ASM `USABLE_FILE_MB`, filesystem space/inode và PDB storage limit trước khi tăng file.
- `ORA-01950` là vấn đề quota; `ORA-30036` là vấn đề undo; `ORA-04030` là vấn đề PGA, không nên nhầm với TEMP.
- Tìm SQL/session dùng TEMP và tối ưu sort/hash/cardinality; tăng TEMP chỉ giải quyết capacity, không loại bỏ nguyên nhân SQL.
- Không kill session, drop object, purge recycle bin hoặc xóa file ở OS khi chưa xác định tác động và có phê duyệt.
- Theo dõi dung lượng, tốc độ tăng, headroom và cảnh báo để xử lý trước khi tablespace cạn.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Error Messages — ORA-01652](https://docs.oracle.com/en/error-help/db/ora-01652/)
- [Oracle Database 19c Error Messages — ORA-01653](https://docs.oracle.com/en/error-help/db/ora-01653/)
- [Oracle Database 19c Administrator's Guide — Managing Tablespaces](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tablespaces.html)
- [Oracle Database 19c Administrator's Guide — Managing Temporary Tablespaces](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tablespaces.html)
- [Oracle Database 19c Reference — DBA_DATA_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DATA_FILES.html)
- [Oracle Database 19c Reference — DBA_TEMP_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TEMP_FILES.html)
- [Oracle Database 19c Reference — V$TEMPSEG_USAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TEMPSEG_USAGE.html)
- [Oracle Database 19c Reference — V$TEMP_SPACE_HEADER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TEMP_SPACE_HEADER.html)
- [Oracle Database 19c Reference — DBA_FREE_SPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_FREE_SPACE.html)
- [Oracle Database 19c Reference — DBA_SEGMENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SEGMENTS.html)
