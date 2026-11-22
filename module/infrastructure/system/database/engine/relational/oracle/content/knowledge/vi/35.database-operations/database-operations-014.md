# Lập kế hoạch dung lượng, ngưỡng cảnh báo và xử lý tài nguyên cạn

Vận hành Oracle Database không chỉ là bảo đảm instance luôn chạy. DBA còn phải dự đoán khi nào các tài nguyên sẽ chạm giới hạn, phát hiện xu hướng đủ sớm để xử lý và có quy trình ứng phó khi một tài nguyên thực sự cạn. Một database có thể vẫn OPEN nhưng ứng dụng không ghi được dữ liệu vì tablespace hết chỗ, không tạo được archive log vì FRA đầy, không cấp phát được temporary extent, hoặc không tạo thêm session/process.

**Lập kế hoạch dung lượng** là quá trình đo mức sử dụng hiện tại, hiểu tốc độ tăng, dự báo nhu cầu và giữ đủ headroom cho workload lẫn hoạt động bảo trì. **Ngưỡng cảnh báo** biến các phép đo đó thành tín hiệu hành động. **Xử lý tài nguyên cạn** cần xác định đúng loại tài nguyên, bảo vệ dữ liệu, khôi phục khả năng phục vụ và loại bỏ nguyên nhân tái diễn.

Không có một ngưỡng phần trăm dùng chung cho mọi database. Tablespace 90% có thể vẫn an toàn nếu còn hàng trăm GB và tăng chậm; một filesystem 70% có thể đã nguy hiểm nếu tốc độ ghi tăng rất nhanh và không thể mở rộng. Cần kết hợp tỷ lệ sử dụng, dung lượng còn lại, giới hạn tối đa, tốc độ tăng, thời gian phản ứng và khả năng mở rộng vật lý.

## 1. Các lớp tài nguyên cần lập kế hoạch

Dung lượng Oracle gồm nhiều lớp liên quan nhưng không đồng nhất. Theo dõi một lớp không thể thay thế cho lớp khác.

| Lớp tài nguyên | Thành phần cần theo dõi | Rủi ro khi cạn |
| --- | --- | --- |
| Database storage | Datafile, tablespace, tempfile | Không cấp phát được extent hoặc không ghi được dữ liệu |
| ASM/storage | Disk group, filesystem, volume, SAN | Datafile/redo/archive không thể mở rộng hoặc ghi |
| Recovery storage | Fast Recovery Area, archived redo, backup | Archiver dừng, backup/recovery bị ảnh hưởng |
| Temporary space | TEMP tablespace, tempfiles, temp segments | Sort, hash join, index build hoặc truy vấn lớn thất bại |
| Undo | Undo tablespace, undo extents, retention | Transaction không có undo, query có thể gặp snapshot too old |
| Redo | Online redo log groups, archive throughput | Log switch bị chậm, archiver nghẽn hoặc database bị treo do archive destination |
| Memory | SGA, PGA, process memory, OS memory | Không cấp phát được shared memory hoặc process memory |
| Process/session | PROCESSES, SESSIONS, transactions | Không tạo được process/session mới |
| CPU/I/O capacity | CPU run queue, IOPS, latency, throughput | Hàng đợi tăng, response time tăng dù storage còn trống |
| Operational capacity | Backup window, maintenance window, recovery time | Không đủ thời gian hoặc tài nguyên để hoàn thành công việc quản trị |

### 1.1. Phân biệt logical capacity và physical capacity

Một datafile có thể được cấu hình AUTOEXTEND tới 100 GB nhưng filesystem chỉ còn 5 GB. Theo metadata Oracle, file còn headroom 70 GB; theo storage thực tế, nó chỉ có thể tăng tối đa khoảng 5 GB trước khi filesystem đầy.

Ngược lại, ASM disk group có thể còn nhiều dung lượng nhưng datafile đã đạt MAXSIZE hoặc tablespace đã chạm giới hạn cấu trúc. Khi đó, tăng storage bên dưới không tự làm datafile mở rộng.

Vì vậy cần theo dõi ít nhất ba mức:

1. **Mức sử dụng logic**: extent đã dùng trong tablespace hoặc tài nguyên đã tiêu thụ.
2. **Mức mở rộng của file/database**: BYTES, MAXBYTES, AUTOEXTENSIBLE và giới hạn tablespace.
3. **Mức storage vật lý**: ASM usable space, filesystem/volume free space và quota ở tầng hạ tầng.

### 1.2. Dung lượng đã cấp phát không phải dung lượng đã dùng

Datafile 500 GB có thể mới dùng 300 GB; 200 GB còn trống bên trong file. Phần trống đó vẫn đã được cấp phát từ storage bên dưới. Nếu datafile AUTOEXTEND, Oracle có thể mở rộng file khi cần, nhưng chỉ khi còn headroom ở MAXSIZE và physical storage.

Báo cáo nên phân biệt:
- Allocated bytes: dung lượng datafile hiện có.
- Used bytes: dung lượng extent đã sử dụng.
- Free bytes inside files: phần trống trong datafile hiện tại.
- Autoextend headroom: phần có thể tăng tới MAXSIZE.
- Physical free bytes: dung lượng còn lại trên ASM/filesystem.

Không cộng các đại lượng này với nhau như thể chúng là những vùng trống độc lập. Free bên trong datafile đã nằm trong allocated bytes; autoextend headroom cũng cần storage vật lý để hiện thực hóa.

## 2. Xây dựng baseline dung lượng

Trước khi dự báo, cần có baseline nhất quán. Baseline là ảnh chụp có định danh, thời điểm, đơn vị và phạm vi.

### 2.1. Thu thập thông tin database

Các thông tin nên ghi nhận:

- DB_NAME và DB_UNIQUE_NAME.
- DBID và database role.
- Oracle version và COMPATIBLE.
- Instance, host và INST_ID nếu dùng RAC.
- CDB/PDB và CON_ID nếu dùng multitenant.
- Tablespace, datafile, tempfile và block size.
- ASM disk group hoặc filesystem chứa từng file.
- FRA size và archive destinations.
- SGA/PGA/process/session limits.
- Backup retention, archive deletion policy và thời gian lưu dữ liệu.
- Tăng trưởng theo ngày/tuần/tháng và các đợt batch định kỳ.

Ví dụ thông tin database:

~~~sql
SELECT name,
       dbid,
       open_mode,
       database_role,
       log_mode
FROM v$database;
~~~

Thông tin instance:

~~~sql
SELECT instance_name,
       host_name,
       status,
       startup_time
FROM v$instance;
~~~

Trong RAC, dùng GV$INSTANCE và giữ INST_ID khi tổng hợp.

### 2.2. Thu thập theo chu kỳ

Một snapshot đơn lẻ chỉ cho biết hiện trạng. Muốn dự báo, cần chuỗi snapshot theo thời gian, ví dụ mỗi 15 phút hoặc mỗi giờ tùy tốc độ thay đổi và chi phí giám sát.

Nên lưu:
- Timestamp có timezone.
- Resource name và scope.
- Allocated, used, free, maximum.
- Growth trong interval.
- Alert state.
- SQL_ID/session/module nếu có thể xác định nguồn tiêu thụ.
- Sự kiện bảo trì, purge, partition drop, backup và batch.

Không ghi đè snapshot cũ. Lịch sử là dữ liệu cần thiết để xác định xu hướng, seasonality và hiệu quả của các hành động mở rộng.

### 2.3. Baseline phải bao gồm peak

Giá trị trung bình thường che giấu peak. Với TEMP, PGA, process và I/O, peak theo giờ hoặc theo batch có thể quyết định khả năng phục vụ.

Ghi nhận:
- Mức bình thường.
- Peak trong ngày.
- Peak cuối tháng/cuối kỳ.
- Peak khi chạy backup, index rebuild, ETL hoặc báo cáo.
- Mức tăng trong sự kiện bất thường.
- Headroom còn lại ở thời điểm peak.

Không thiết kế capacity chỉ dựa trên thời điểm tải thấp.

## 3. Lập kế hoạch tăng trưởng

Dự báo cần kết hợp lịch sử, kế hoạch nghiệp vụ và các hoạt động kỹ thuật. Không nên chỉ ngoại suy một ngày gần nhất.

### 3.1. Tốc độ tăng trưởng đơn giản

Nếu used space tăng từ 400 GB lên 430 GB trong 10 ngày:

\[
Growth/day = \frac{430 - 400}{10} = 3\ GB/day
\]

Nếu còn 90 GB dung lượng usable:

\[
Time\ to\ full = \frac{90}{3} = 30\ days
\]

Đây là dự báo tuyến tính đơn giản. Nó giả định tốc độ tăng ổn định, không có thay đổi workload, purge, partition maintenance hoặc chiến dịch dữ liệu mới.

### 3.2. Dùng nhiều cửa sổ thời gian

Nên so sánh:
- Tăng trưởng 24 giờ.
- Trung bình 7 ngày.
- Trung bình 30 ngày.
- Cùng ngày/giờ của tuần trước.
- Peak theo chu kỳ nghiệp vụ.

Một đợt import lớn có thể làm tốc độ tăng 24 giờ cao hơn nhiều so với xu hướng tháng. Ngược lại, một tuần thấp tải có thể làm dự báo 7 ngày quá lạc quan.

### 3.3. Dự báo có seasonality

Hệ thống có thể tăng dữ liệu mạnh vào cuối ngày, cuối tháng hoặc mùa cao điểm. Hãy lập kế hoạch theo chu kỳ:
- Số giao dịch theo ngày.
- Tăng dữ liệu theo tháng.
- Retention của log và dữ liệu audit.
- Chu kỳ partition.
- Batch archive/purge.
- Kế hoạch onboarding khách hàng hoặc mở tính năng.

Nếu workload có mùa vụ, dùng kịch bản peak đã quan sát hoặc kế hoạch kinh doanh thay vì chỉ lấy trung bình tuyến tính.

### 3.4. Tính time-to-full

\[
TimeToFull = \frac{UsableHeadroom}{ExpectedGrowthRate}
\]

UsableHeadroom phải tính theo giới hạn thực tế thấp nhất giữa:
- Headroom tablespace/datafile.
- Dung lượng ASM/filesystem có thể cấp cho file.
- Quota hoặc giới hạn storage.
- Giới hạn vận hành và thời gian cần để provision thêm capacity.

Nếu growth rate bằng 0 hoặc âm, time-to-full không xác định theo mô hình tuyến tính. Không hiển thị vô cực như một bảo đảm an toàn; vẫn cần ngưỡng tuyệt đối và theo dõi thay đổi.

### 3.5. Kịch bản tăng trưởng

Lập ít nhất ba kịch bản:

| Kịch bản | Giả định | Mục đích |
| --- | --- | --- |
| Base | Tốc độ tăng bình thường đã quan sát | Kế hoạch vận hành thường ngày |
| High | Tăng trưởng cao điểm hoặc workload tăng | Chuẩn bị cho mùa cao điểm |
| Stress | Import lớn, retention tăng, purge thất bại hoặc batch bất thường | Kiểm tra giới hạn và phương án ứng phó |

Kế hoạch provision nên đáp ứng kịch bản High hoặc mức rủi ro đã được tổ chức chấp nhận, đồng thời có phương án cho Stress.

## 4. Ước lượng nhu cầu theo workload

Dung lượng không chỉ tăng theo số hàng. Index, LOB, undo, redo, temporary segment và backup có thể tăng theo cách khác nhau.

### 4.1. Dữ liệu bảng và index

Ước lượng từ:
- Số row mới mỗi ngày.
- Kích thước row trung bình.
- Tỷ lệ update/delete.
- Index count và index key width.
- LOB size và tỷ lệ lưu ngoài hàng.
- Partitioning và retention.
- Compression và deduplication nếu được dùng.

Công thức sơ bộ:

\[
TableGrowth \approx NewRows \times AverageStoredRowBytes
\]

\[
IndexGrowth \approx NewRows \times AverageIndexEntryBytes
\]

Đây là ước lượng ban đầu; overhead block, PCTFREE, row migration, index split, compression và segment allocation làm số thực tế khác đi.

### 4.2. LOB và dữ liệu lớn

CLOB/BLOB có thể tăng nhanh hơn bảng metadata chứa locator. Theo dõi segment LOB và LOB index riêng, đồng thời kiểm tra retention của file, ảnh, PDF và payload.

### 4.3. Partition lifecycle

Partition exchange, truncate/drop partition và interval partition có thể làm dung lượng tăng/giảm theo bước. Forecast tuyến tính cần tính các đợt tạo partition mới và thời điểm purge partition cũ.

### 4.4. Index maintenance

Rebuild index có thể cần không gian tạm thời đáng kể. Tùy thao tác và tùy chọn, Oracle có thể phải giữ index cũ trong khi tạo cấu trúc mới. Không chỉ dự trù dung lượng cuối cùng của index; phải dự trù peak trong maintenance window.

### 4.5. Undo và redo

Undo phụ thuộc transaction concurrency, thời gian transaction, query duration và retention. Redo phụ thuộc lượng thay đổi dữ liệu, index maintenance, batch và workload. Không suy ra undo/redo chỉ từ dung lượng bảng.

### 4.6. Backup và archived redo

Backup full, incremental, archived redo và backup copy có retention riêng. Dự báo FRA phải xét lượng archive sinh ra mỗi giờ, backup frequency, deletion policy, standby apply lag và thời gian cần giữ để recovery.

## 5. Theo dõi tablespace và datafile

Tablespace là lớp quản lý logic. Datafile là file vật lý hoặc file được quản lý bởi ASM/OMF. Cần theo dõi cả mức used/free của tablespace và khả năng mở rộng từng datafile.

### 5.1. Xem datafile và autoextend

~~~sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS allocated_mb,
       maxbytes / 1024 / 1024 AS max_mb,
       autoextensible,
       increment_by
FROM dba_data_files
ORDER BY tablespace_name, file_name;
~~~

DBA_TEMP_FILES cung cấp thông tin tương tự cho tempfile.

Các cột:
- BYTES: kích thước hiện tại của file.
- MAXBYTES: giới hạn mở rộng được khai báo.
- AUTOEXTENSIBLE: có cho phép tự mở rộng hay không.
- INCREMENT_BY: số block mỗi lần tăng, cần nhân với block size để ra byte.

Nếu AUTOEXTENSIBLE = NO, không tính MAXBYTES như headroom có thể dùng.

### 5.2. Xem free extents của permanent tablespace

~~~sql
SELECT tablespace_name,
       SUM(bytes) AS free_bytes,
       MAX(bytes) AS largest_free_extent
FROM dba_free_space
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

FREE_BYTES là tổng dung lượng free extent. LARGEST_FREE_EXTENT giúp nhận biết một số thao tác cần extent liên tục có thể gặp vấn đề dù tổng free còn nhiều. Với locally managed tablespace và autoallocate, allocation có thể theo extent size do Oracle quản lý; không suy luận mọi segment đều cần một extent bằng largest request.

### 5.3. Tổng hợp allocated, used và theoretical maximum

Ví dụ cho permanent tablespace:

~~~sql
WITH datafiles AS (
    SELECT
        tablespace_name,
        SUM(bytes) AS allocated_bytes,
        SUM(
            CASE
                WHEN autoextensible = 'YES'
                THEN GREATEST(maxbytes, bytes)
                ELSE bytes
            END
        ) AS configured_max_bytes
    FROM dba_data_files
    GROUP BY tablespace_name
),
free_space AS (
    SELECT
        tablespace_name,
        SUM(bytes) AS free_bytes
    FROM dba_free_space
    GROUP BY tablespace_name
)
SELECT
    d.tablespace_name,
    d.allocated_bytes,
    NVL(f.free_bytes, 0) AS free_bytes_inside_files,
    d.allocated_bytes - NVL(f.free_bytes, 0) AS used_bytes,
    d.configured_max_bytes,
    d.configured_max_bytes -
        (d.allocated_bytes - NVL(f.free_bytes, 0))
        AS theoretical_headroom_bytes,
    ROUND(
        100 * (d.allocated_bytes - NVL(f.free_bytes, 0))
        / NULLIF(d.allocated_bytes, 0),
        2
    ) AS used_pct_of_allocated
FROM datafiles d
LEFT JOIN free_space f
  ON f.tablespace_name = d.tablespace_name
ORDER BY d.tablespace_name;
~~~

THEORETICAL_HEADROOM_BYTES là headroom theo cấu hình datafile, không phải cam kết storage vật lý sẽ cấp được. Nó có thể lớn hơn dung lượng còn lại trên ASM/filesystem. Cũng cần xem giới hạn block/file size và giới hạn tablespace.

### 5.4. Dùng DBA_TABLESPACE_USAGE_METRICS

Ở các phiên bản hỗ trợ, DBA_TABLESPACE_USAGE_METRICS cung cấp mức sử dụng tablespace và tỷ lệ sử dụng. Các giá trị TABLESPACE_SIZE và USED_SPACE được biểu diễn theo block; join DBA_TABLESPACES để biết BLOCK_SIZE nếu cần quy đổi byte.

~~~sql
SELECT m.tablespace_name,
       t.block_size,
       m.tablespace_size,
       m.used_space,
       m.used_percent
FROM dba_tablespace_usage_metrics m
JOIN dba_tablespaces t
  ON t.tablespace_name = m.tablespace_name
ORDER BY m.used_percent DESC;
~~~

View này hữu ích cho monitoring, nhưng vẫn cần kiểm tra giới hạn storage và datafile. Không diễn giải USED_PERCENT tách rời khỏi cấu hình autoextend và physical storage.

### 5.5. Bigfile và smallfile tablespace

Smallfile tablespace có thể chứa nhiều datafile. Bigfile tablespace có một datafile rất lớn. Cách mở rộng khác nhau:
- Smallfile: có thể thêm datafile nếu còn giới hạn số file và storage.
- Bigfile: thường resize hoặc bật autoextend trên datafile duy nhất; không thêm datafile thứ hai vào cùng bigfile tablespace.

Xác định loại tablespace trước khi chọn lệnh mở rộng.

## 6. AUTOEXTEND và giới hạn mở rộng

AUTOEXTEND giúp Oracle tự tăng datafile khi cần extent. Nó không thay thế capacity planning.

### 6.1. Bật AUTOEXTEND có giới hạn

~~~sql
ALTER DATABASE DATAFILE
    '/u02/oradata/app/app_data01.dbf'
AUTOEXTEND ON
NEXT 512M
MAXSIZE 40G;
~~~

Đây là ví dụ với đường dẫn filesystem. Trong ASM/OMF, cú pháp và tên file có thể khác. Chọn NEXT dựa trên pattern tăng trưởng và overhead quản lý; MAXSIZE phải nằm trong ngân sách storage.

### 6.2. Tắt AUTOEXTEND

~~~sql
ALTER DATABASE DATAFILE
    '/u02/oradata/app/app_data01.dbf'
AUTOEXTEND OFF;
~~~

Tắt autoextend có thể hữu ích khi cần kiểm soát chặt việc sử dụng storage, nhưng phải có cảnh báo và quy trình mở rộng chủ động. Nếu file sắp đầy mà không có người xử lý, ứng dụng sẽ gặp lỗi cấp phát extent.

### 6.3. Tăng kích thước datafile

~~~sql
ALTER DATABASE DATAFILE
    '/u02/oradata/app/app_data01.dbf'
RESIZE 30G;
~~~

RESIZE chỉ thành công nếu không cắt bỏ vùng đã chứa extent đang sử dụng. Nếu file có extent ở cuối file, Oracle có thể trả ORA-03297. Không xóa segment hoặc shrink file tùy tiện để ép resize.

### 6.4. Thêm datafile cho smallfile tablespace

~~~sql
ALTER TABLESPACE app_data
ADD DATAFILE '/u02/oradata/app/app_data02.dbf'
SIZE 10G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 30G;
~~~

Đối với OMF/ASM, có thể để Oracle tạo tên file theo cấu hình. Ví dụ:

~~~sql
ALTER TABLESPACE app_data
ADD DATAFILE '+DATA'
SIZE 10G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 30G;
~~~

Chỉ sử dụng cú pháp ASM khi disk group đã sẵn sàng và chính sách OMF phù hợp.

### 6.5. Vì sao AUTOEXTEND có thể không cứu được tablespace?

Các nguyên nhân:
- File đã đạt MAXSIZE.
- Filesystem/ASM disk group hết chỗ.
- File size chạm giới hạn platform hoặc block size.
- Không đủ quyền hoặc storage path không khả dụng.
- Tablespace là bigfile và đã đạt giới hạn.
- Storage quota hoặc thin-provisioned volume đã cạn.
- Autoextend increment quá lớn so với dung lượng còn lại.

Cần kiểm tra cả DBA_DATA_FILES, alert log và tầng storage.

## 7. Theo dõi ASM và filesystem

Tablespace có thể còn free extent nhưng datafile không thể tăng vì storage bên dưới đã đầy. Đây là một trong những nguyên nhân khiến dự báo chỉ dựa vào DBA_FREE_SPACE thất bại.

### 7.1. ASM disk group

Từ ASM instance hoặc tài khoản có quyền xem dynamic performance view:

~~~sql
SELECT name,
       state,
       type,
       total_mb,
       free_mb,
       required_mirror_free_mb,
       usable_file_mb
FROM v$asm_diskgroup
ORDER BY name;
~~~

USABLE_FILE_MB quan trọng vì đã xét tới yêu cầu redundancy/mirroring và dung lượng cần giữ. FREE_MB không nhất thiết bằng dung lượng an toàn có thể cấp cho file mới.

Trong RAC/ASM, dùng GV$ASM_DISKGROUP khi phù hợp và giữ INST_ID. Một disk group có thể được nhìn thấy qua nhiều instance; không cộng lặp các dòng của cùng disk group từ các instance.

### 7.2. Filesystem và volume

Theo dõi:
- Total bytes.
- Used/free bytes.
- Inode usage.
- Mount point.
- Quota.
- Storage latency và throughput.
- Thin pool hoặc SAN capacity nếu có.

Filesystem có thể hết inode trước khi hết byte. Thin-provisioned volume có thể báo dung lượng logic còn nhiều nhưng physical pool phía sau đã gần cạn.

### 7.3. Không dùng df thay cho Oracle metadata

Lệnh OS cho biết tình trạng filesystem nhưng không cho biết extent nào trong tablespace đã dùng. Ngược lại, DBA_DATA_FILES không biết toàn bộ storage khác đang cạnh tranh cùng filesystem. Phải kết hợp cả hai nguồn.

## 8. Fast Recovery Area và archived redo

FRA chứa các file liên quan đến recovery như archived redo log, backup piece, image copy, flashback log và control file/autobackup tùy cấu hình.

### 8.1. Kiểm tra FRA

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

Các giá trị space được tính theo byte. SPACE_RECLAIMABLE là dung lượng có thể được Oracle reclaim theo quy tắc quản lý FRA; không nên coi toàn bộ số này là file có thể xóa tùy ý ngay lập tức.

### 8.2. Phân loại dung lượng FRA

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage
ORDER BY percent_space_used DESC;
~~~

View này giúp xác định file type nào đang chiếm FRA. Nếu archived log tăng mạnh, điều tra archive generation, backup, standby apply và deletion policy. Nếu flashback log tăng, xem flashback database và retention target. Nếu backup piece tăng, xem retention policy và backup schedule.

### 8.3. Tăng FRA size không tạo thêm physical storage

Có thể điều chỉnh giới hạn FRA:

~~~sql
ALTER SYSTEM SET db_recovery_file_dest_size = 200G
SCOPE = BOTH;
~~~

Đây chỉ là ví dụ. Chỉ tăng khi storage vật lý phía sau có đủ chỗ và ngân sách đã được duyệt. Tăng SPACE_LIMIT lớn hơn filesystem/ASM capacity có thể khiến Oracle tiếp tục ghi cho tới khi tầng storage thực sự đầy.

### 8.4. Archived log và ORA-00257

Khi archive destination đầy hoặc archiver không thể ghi archive log, database có thể bị hạn chế hoạt động. ORA-00257 thường báo archiver error và yêu cầu xử lý archive destination.

Quy trình:
1. Kiểm tra V$ARCHIVE_DEST_STATUS và alert log.
2. Xác định destination nào lỗi.
3. Kiểm tra FRA hoặc filesystem chứa archive.
4. Xác nhận backup archive gần nhất.
5. Xác nhận standby đã nhận/apply redo theo chính sách.
6. Dùng RMAN và deletion policy để reclaim file đủ điều kiện.
7. Mở rộng storage hoặc sửa destination nếu cần.
8. Xác nhận archiver hoạt động trở lại.

Không xóa archived redo bằng lệnh OS để giải phóng chỗ. Việc xóa có thể phá vỡ recovery chain hoặc Data Guard.

### 8.5. RMAN và cleanup an toàn

Các lệnh RMAN cần được thực hiện theo retention/deletion policy của hệ thống. Ví dụ kiểm tra:

~~~text
RMAN> SHOW RETENTION POLICY;
RMAN> SHOW ARCHIVELOG DELETION POLICY;
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> REPORT OBSOLETE;
~~~

CROSSCHECK đồng bộ metadata RMAN với file thực tế; REPORT OBSOLETE chỉ liệt kê backup không còn cần theo retention policy. Sau khi xác nhận backup, standby và chính sách, DBA có thể dùng DELETE OBSOLETE hoặc backup archived log kèm DELETE INPUT theo runbook đã phê duyệt.

Không dùng DELETE EXPIRED như cách dọn file còn tồn tại; EXPIRED biểu thị RMAN không tìm thấy file khi crosscheck. Không xóa log chưa được backup hoặc chưa được standby áp dụng nếu deletion policy yêu cầu giữ chúng.

## 9. TEMP tablespace

TEMP được dùng cho sort, hash join, bitmap operation, index build và các thao tác cần temporary segment. TEMP có thể tăng mạnh trong một truy vấn dù permanent tablespace còn nhiều chỗ.

### 9.1. Theo dõi tempfile

~~~sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS allocated_mb,
       maxbytes / 1024 / 1024 AS max_mb,
       autoextensible
FROM dba_temp_files
ORDER BY tablespace_name, file_name;
~~~

### 9.2. Theo dõi TEMP usage

~~~sql
SELECT tablespace_name,
       SUM(bytes_used) / 1024 / 1024 AS used_mb,
       SUM(bytes_free) / 1024 / 1024 AS free_mb
FROM v$temp_space_header
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

Số liệu là snapshot tại thời điểm truy vấn. TEMP segment có thể được tái sử dụng; một lần usage cao không tự chứng minh leak.

### 9.3. Tìm session dùng TEMP

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       u.tablespace,
       u.segtype,
       u.blocks,
       u.sql_id
FROM v$tempseg_usage u
JOIN v$session s
  ON s.saddr = u.session_addr
ORDER BY u.blocks DESC;
~~~

Trong RAC, dùng GV$TEMPSEG_USAGE và GV$SESSION, ghép INST_ID. Tìm SQL_ID và module để xác định workload gây tiêu thụ.

### 9.4. Mở rộng TEMP

Có thể thêm tempfile:

~~~sql
ALTER TABLESPACE temp
ADD TEMPFILE '/u02/oradata/app/temp02.dbf'
SIZE 10G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 30G;
~~~

Kiểm tra physical storage trước khi thêm. TEMP tăng không phải lúc nào cũng cần mở rộng: một SQL có thể tạo sort/hash spill bất thường do plan, cardinality estimate hoặc thiếu PGA. Điều tra SQL trước khi cấp thêm dung lượng lớn.

### 9.5. Xử lý TEMP cạn

Khi gặp ORA-01652:
1. Xác định tablespace/tempfile và session/SQL_ID liên quan.
2. Kiểm tra usage hiện tại và peak.
3. Kiểm tra execution plan, sort/hash, parallelism và cardinality.
4. Nếu là workload hợp lệ và storage còn, thêm tempfile hoặc mở rộng có kiểm soát.
5. Nếu SQL bất thường, dừng/cancel theo quy trình và sửa query/plan.
6. Kiểm tra usage giảm sau khi statement kết thúc.
7. Thiết lập ngưỡng theo peak và concurrency.

Không kill session ngay khi thấy TEMP cao mà chưa xác định đó là batch quan trọng hay query runaway. Dừng session có thể rollback công việc và tạo thêm tải.

## 10. UNDO tablespace và retention

UNDO lưu các phiên bản trước của dữ liệu để rollback transaction, read consistency và một số thao tác recovery. Nhu cầu undo phụ thuộc tốc độ thay đổi dữ liệu, concurrency, transaction duration, query duration và UNDO_RETENTION.

### 10.1. Kiểm tra undo configuration

~~~sql
SHOW PARAMETER undo_tablespace;
SHOW PARAMETER undo_retention;
SHOW PARAMETER undo_management;
~~~

Trong hệ thống dùng automatic undo management, Oracle tự quản lý extent theo trạng thái ACTIVE, UNEXPIRED và EXPIRED.

### 10.2. Theo dõi undo extents

~~~sql
SELECT tablespace_name,
       status,
       SUM(bytes) / 1024 / 1024 AS size_mb
FROM dba_undo_extents
GROUP BY tablespace_name, status
ORDER BY tablespace_name, status;
~~~

ACTIVE extent đang được transaction sử dụng. UNEXPIRED extent còn trong retention period; EXPIRED có thể được tái sử dụng. Việc reclaim UNEXPIRED phụ thuộc cấu hình và điều kiện retention/space pressure.

### 10.3. Theo dõi V$UNDOSTAT

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC;
~~~

V$UNDOSTAT cung cấp thống kê theo interval, thường dùng để hiểu undo generation, query length, tuned retention và lỗi liên quan. Xem nhiều interval, không chỉ một hàng mới nhất.

### 10.4. ORA-30036 và ORA-01555

- ORA-30036: không thể mở rộng undo segment trong undo tablespace.
- ORA-01555: snapshot too old, query không thể đọc phiên bản cũ cần thiết.

Hai lỗi có thể liên quan tới undo pressure nhưng không có cùng nguyên nhân. ORA-01555 có thể do query chạy lâu, undo bị tái sử dụng, workload DML cao hoặc cấu hình retention/space không phù hợp. Chỉ tăng UNDO_RETENTION mà không tăng dung lượng hoặc thay đổi workload có thể không giải quyết được.

### 10.5. Hướng xử lý

- Đo undo generation theo giờ/ngày.
- Xác định transaction dài và query dài.
- Kiểm tra UNDO_RETENTION và retention guarantee.
- Kiểm tra dung lượng còn lại và active/unexpired extents.
- Tăng undo tablespace khi có storage và lý do rõ.
- Điều chỉnh batch/commit strategy nếu transaction quá lớn, nhưng không chia transaction tùy tiện làm thay đổi semantics.
- Điều chỉnh query để giảm thời gian đọc snapshot nếu phù hợp.

Không xóa undo segment thủ công hoặc cố giải phóng extent ACTIVE.

## 11. REDO log và archive throughput

Redo log là tài nguyên có ảnh hưởng trực tiếp tới khả năng ghi và recovery.

### 11.1. Theo dõi online redo log

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes / 1024 / 1024 AS size_mb,
       members,
       archived,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

Thành viên redo log:

~~~sql
SELECT group#,
       type,
       member,
       status
FROM v$logfile
ORDER BY group#, member;
~~~

### 11.2. Log switch quá thường xuyên

Log switch liên tục có thể gây archive pressure và checkpoint pressure. Theo dõi V$LOG_HISTORY theo thời gian:

~~~sql
SELECT TRUNC(first_time, 'HH24') AS hour_start,
       COUNT(*) AS log_switches
FROM v$log_history
WHERE first_time >= SYSDATE - 1
GROUP BY TRUNC(first_time, 'HH24')
ORDER BY hour_start;
~~~

Số log switch cần được diễn giải theo workload và kích thước redo log. Không có một con số log switch/giờ phù hợp cho mọi database.

### 11.3. Không xóa online redo log để lấy chỗ

Online redo log đang tham gia vòng đời recovery. Không xóa file bằng OS. Nếu cần thay đổi kích thước hoặc số nhóm, thực hiện theo quy trình add/drop log group phù hợp, bảo đảm thread và trạng thái log an toàn.

## 12. Process, session và transaction limits

Database có thể còn storage nhưng không tạo được kết nối mới do giới hạn process/session.

### 12.1. Kiểm tra resource limit

~~~sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM v$resource_limit
WHERE resource_name IN (
    'processes',
    'sessions',
    'transactions'
)
ORDER BY resource_name;
~~~

MAX_UTILIZATION giúp thấy peak kể từ lần khởi động/reset tương ứng. Đây không phải mức sử dụng hiện tại.

### 12.2. ORA-00020 và ORA-00018

- ORA-00020: số process vượt giới hạn PROCESSES.
- ORA-00018: số session vượt giới hạn SESSIONS.

Điều tra:
- Connection pool có mở quá nhiều connection không?
- Có session idle không được trả về pool?
- Có job/batch tạo nhiều process?
- Có connection leak hoặc retry storm?
- Có session background hoặc parallel execution tăng bất thường?

Không chỉ tăng PROCESSES. Mỗi process tiêu thụ tài nguyên OS và có thể làm tăng PGA; tăng giới hạn mà không kiểm tra memory và OS limits có thể chuyển lỗi sang tầng khác.

### 12.3. Thay đổi giới hạn

PROCESSES thường là tham số cần restart để thay đổi. Kiểm tra ISSES_MODIFIABLE/ISSYS_MODIFIABLE trong V$PARAMETER hoặc tài liệu phiên bản trước khi lập kế hoạch.

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isinstance_modifiable
FROM v$parameter
WHERE name IN ('processes', 'sessions');
~~~

Tên cột thực tế trong V$PARAMETER cần kiểm tra theo phiên bản; có thể dùng ISSES_MODIFIABLE và ISSYS_MODIFIABLE. Không chạy thay đổi tham số khi chưa biết yêu cầu restart và tác động.

## 13. SGA, PGA và bộ nhớ hệ điều hành

Memory pressure có thể gây lỗi dù disk còn nhiều. Cần phân biệt SGA dùng chung và PGA riêng cho process.

### 13.1. Theo dõi SGA

~~~sql
SELECT name,
       bytes / 1024 / 1024 AS mb
FROM v$sgainfo
ORDER BY name;
~~~

V$SGAINFO cung cấp thông tin kích thước các thành phần SGA. Xem cùng V$SGASTAT, shared pool, buffer cache và alert log để hiểu thành phần nào tăng.

### 13.2. Theo dõi PGA

~~~sql
SELECT name,
       value,
       unit
FROM v$pgastat
ORDER BY name;
~~~

Các metric như total PGA allocated, maximum PGA allocated, aggregate PGA target parameter và over allocation count giúp đánh giá áp lực PGA. Đơn vị cần đọc từ cột UNIT.

### 13.3. ORA-04031 và ORA-04030

- ORA-04031: Oracle không cấp phát được vùng shared memory theo yêu cầu, thường liên quan SGA/shared pool hoặc pool cụ thể.
- ORA-04030: process không cấp phát được memory trong process private memory/PGA.

Điều tra:
- Alert log và trace file.
- V$SGASTAT hoặc V$PGASTAT.
- SQL có sort/hash lớn.
- Số process/session và parallelism.
- OS memory, swap/pagefile và giới hạn process.
- SGA/PGA configuration và memory target.

Không tăng SGA/PGA theo cảm tính. Tăng một vùng có thể làm giảm memory dành cho vùng khác hoặc khiến OS bắt đầu swapping.

## 14. CPU và I/O cũng là capacity

Capacity planning không chỉ là GB. CPU và storage throughput có thể đạt giới hạn trước dung lượng.

### 14.1. CPU

Theo dõi:
- CPU utilization của host.
- Run queue và CPU saturation.
- DB CPU và DB time.
- Parallel execution.
- Số process runnable.
- Throughput và response time theo service.

Một host CPU 90% có thể đang xử lý workload tốt hoặc đang quá tải; phải xem latency, queue và SLA. Trung bình CPU thấp có thể che giấu một core nóng hoặc thời điểm peak ngắn.

### 14.2. I/O

Theo dõi:
- IOPS và MB/s.
- Read/write latency.
- Queue depth.
- ASM disk group throughput.
- Datafile/redo/archive I/O.
- Storage path và multipath health.

Dung lượng còn nhiều không bảo đảm I/O đủ nhanh. Khi latency tăng, query có thể chậm dù không có ORA-01653 hay filesystem full.

### 14.3. Backup window và recovery capacity

Backup có thể tiêu thụ I/O, CPU, network và FRA. Lập kế hoạch sao cho backup không làm ảnh hưởng SLA; đồng thời phải hoàn thành trong thời gian cho phép và đáp ứng RPO/RTO.

Recovery capacity bao gồm:
- Backup set và archived redo còn sẵn.
- Dung lượng để restore/recover.
- Thời gian restore từ storage/network.
- Nhân lực và runbook.
- Khả năng mở database sau recovery.

Không coi backup thành công là bằng chứng recovery sẽ đáp ứng RTO; cần kiểm tra restore/recovery định kỳ.

## 15. Thiết kế ngưỡng cảnh báo

Một ngưỡng tốt phải tạo đủ thời gian phản ứng, tránh cảnh báo giả và chỉ rõ hành động tiếp theo.

### 15.1. Kết hợp nhiều loại ngưỡng

Nên dùng đồng thời:

1. **Percentage threshold**: tỷ lệ sử dụng.
2. **Absolute free threshold**: dung lượng còn lại tối thiểu.
3. **Time-to-full threshold**: số ngày/giờ còn lại theo tốc độ tăng.
4. **Growth-rate threshold**: tốc độ tăng bất thường.
5. **Operational threshold**: thời gian còn lại trước maintenance/backup hoặc deadline nghiệp vụ.

Ví dụ, tablespace đạt 85% nhưng còn 500 GB và tăng 1 GB/tháng có thể ít khẩn cấp hơn tablespace 65% nhưng chỉ còn 2 GB usable và tăng 1 GB/giờ.

### 15.2. Warning và critical

Ngưỡng minh họa:

| Mức | Điều kiện ví dụ | Hành động |
| --- | --- | --- |
| Normal | Dưới warning và còn đủ runway | Theo dõi định kỳ |
| Warning | 80% used hoặc time-to-full dưới 30 ngày | Tạo ticket, xác định owner và kế hoạch mở rộng |
| Critical | 90% used hoặc time-to-full dưới 7 ngày | Escalate ngay, chuẩn bị capacity hoặc giảm tăng trưởng |
| Emergency | Còn rất ít headroom hoặc tài nguyên đã chạm giới hạn | Kích hoạt incident runbook |

Các phần trăm và số ngày chỉ là ví dụ. Hãy hiệu chỉnh theo tốc độ tăng, response time của đội hạ tầng, thời gian mua/provision storage, workload peak và mức độ quan trọng của database.

### 15.3. Hysteresis để tránh flapping

Nếu cảnh báo bật ở 80% và tắt ngay khi xuống 79,9%, hệ thống có thể liên tục bật/tắt khi usage dao động.

Ví dụ:
- Warning bật ở 80%, clear ở 75%.
- Critical bật ở 90%, clear ở 85%.

Khoảng clear thấp hơn ngưỡng bật tạo hysteresis. Có thể yêu cầu nhiều lần liên tiếp vượt ngưỡng trước khi phát cảnh báo và nhiều lần dưới clear threshold mới đóng cảnh báo.

### 15.4. Dùng thời gian xác nhận

Một spike 10 giây không nhất thiết cần paging. Có thể yêu cầu:
- Vượt ngưỡng trong 2–3 mẫu liên tiếp.
- Hoặc vượt ngưỡng tuyệt đối ngay lập tức nếu nguy cơ hết tài nguyên.
- Critical alert bỏ qua thời gian trì hoãn nếu resource đã hết hoặc database không thể ghi.

Chọn observation period theo tốc độ thay đổi của resource. TEMP có thể tăng rất nhanh; tablespace tăng theo ngày có thể dùng chu kỳ dài hơn.

### 15.5. Cảnh báo phải gắn owner và action

Một alert hữu ích cần có:
- Database/instance/PDB.
- Resource/tablespace/disk group.
- Current used/free/max.
- Growth rate và time-to-full.
- Metric window.
- Alert timestamp và severity.
- Runbook link hoặc action đề xuất.
- Owner và escalation target.

Cảnh báo chỉ ghi “Tablespace 90%” khiến người nhận phải tự tìm lại toàn bộ bối cảnh.

## 16. Ngưỡng theo từng loại tài nguyên

### 16.1. Permanent tablespace

Theo dõi:
- Used percent trên allocated.
- Used percent trên maximum usable.
- Free bytes.
- Largest free extent khi cần.
- Datafile maxsize.
- ASM/filesystem headroom.
- Time-to-full.

### 16.2. TEMP

Theo dõi:
- Current/peak used.
- Free tempfile capacity.
- Autoextend headroom.
- Số session/SQL_ID đang dùng.
- Tốc độ tăng theo giờ và peak concurrency.

Cảnh báo TEMP nên phân biệt spike do một query với mức sử dụng nền tăng dần. Nếu TEMP chạm 100% trong vài phút, warning theo ngày là quá muộn.

### 16.3. UNDO

Theo dõi:
- Undo tablespace usage.
- ACTIVE/UNEXPIRED/EXPIRED extents.
- Undo generation rate.
- Longest query và transaction.
- SSOLDERRCNT và NOSPACEERRCNT.
- Tuned undo retention.

### 16.4. FRA và archive destination

Theo dõi:
- SPACE_USED / SPACE_LIMIT.
- SPACE_RECLAIMABLE.
- Archive generation rate.
- Backup age và backup success.
- Standby transport/apply lag.
- Destination STATUS/ERROR.
- Thời gian còn lại trước khi FRA đầy.

### 16.5. ASM/filesystem

Theo dõi:
- Usable_file_mb và free_mb.
- Filesystem bytes và inode.
- Growth của volume.
- Latency và error.
- Dung lượng dành cho mirror/rebalance.
- Capacity của thin pool/SAN.

### 16.6. Processes/sessions

Theo dõi:
- Current utilization.
- Max utilization.
- Limit value.
- Connection pool active/idle/wait.
- Session theo username/module/program.
- Login rate và retry storm.

### 16.7. PGA/SGA/CPU/I/O

Theo dõi:
- PGA allocation và over allocation.
- SGA component allocation.
- OS available memory/swap.
- CPU utilization và run queue.
- I/O latency/throughput.
- DB time, DB CPU và response time.

Không dùng một ngưỡng phần trăm memory chung cho mọi cấu hình. Phải tính tới memory của OS, agent, backup, Grid Infrastructure và các instance khác cùng host.

## 17. Oracle alerting và công cụ giám sát

### 17.1. Enterprise Manager

Oracle Enterprise Manager có thể giám sát tablespace, FRA, host filesystem, ASM, session/process, availability và các metric khác. Cấu hình:
- Warning/critical threshold.
- Metric collection interval.
- Notification rule.
- Incident rule.
- Escalation và suppression.
- Owner/team nhận cảnh báo.

Không bật mọi metric ở tần suất cao mà không đánh giá overhead và alert noise.

### 17.2. DBMS_SERVER_ALERT

Oracle cung cấp DBMS_SERVER_ALERT để cấu hình một số server-generated metric threshold. Có thể tra metric được hỗ trợ trong V$METRICNAME và tài liệu package của đúng release.

Các thành phần cần xác định trước khi gọi API:
- Metric ID.
- Object type và object name.
- Instance scope.
- Warning/critical operator và value.
- Observation period.
- Consecutive occurrences.
- Message và trạng thái threshold.

Cú pháp và metric support phụ thuộc phiên bản. Hãy xem package specification trong database và tài liệu release đang chạy; không copy metric ID hoặc tham số từ một phiên bản khác mà chưa xác minh.

### 17.3. Xem outstanding alerts

~~~sql
SELECT reason,
       suggested_action,
       object_type,
       object_name,
       message_level,
       creation_time
FROM dba_outstanding_alerts
ORDER BY creation_time DESC;
~~~

View này giúp xem alert chưa được giải quyết. Kiểm tra quyền truy cập và tên cột theo release. Đừng chỉ xóa/clear alert để làm dashboard xanh; xử lý nguyên nhân rồi xác nhận metric đã trở lại vùng an toàn.

### 17.4. Alert log

Có thể xem diagnostic location:

~~~sql
SELECT name,
       value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Diag Alert');
~~~

Alert log ghi các sự kiện quan trọng như archive error, datafile error, recovery, space-related error và startup/shutdown. Khi xử lý capacity incident, ghi lại ORA code, file path, tablespace, process và thời điểm.

### 17.5. Monitoring bên ngoài

Có thể đẩy metric ra hệ thống giám sát tập trung. Thiết kế collector:
- Query read-only với tần suất hợp lý.
- Ghi timestamp và instance identity.
- Không dùng một connection riêng cho mỗi metric.
- Giới hạn thời gian truy vấn.
- Có timeout và retry có backoff.
- Giữ dữ liệu khi database tạm thời không truy cập được.
- Phát hiện collector bị mất heartbeat.

Nếu monitoring ngừng thu thập, dashboard “không có alert” không có nghĩa database an toàn. Cần alert cho chính pipeline monitoring.

## 18. Quy trình xử lý khi tài nguyên cạn

Khi có incident, mục tiêu đầu tiên là khôi phục khả năng hoạt động an toàn. Không thay đổi nhiều tham số cùng lúc vì sẽ khó xác định nguyên nhân và có thể làm tình hình xấu hơn.

### 18.1. Bước 1 — Xác định resource và phạm vi

Ghi nhận:
- ORA error và SQL_ID nếu có.
- DBID, DB_UNIQUE_NAME, instance, host.
- PDB/container và service.
- Tablespace/file/disk group/destination cụ thể.
- Thời điểm bắt đầu và workload liên quan.
- Tác động: chỉ một batch, một PDB hay toàn database.

### 18.2. Bước 2 — Xác nhận trạng thái thực tế

Kiểm tra:
- Dung lượng used/free hiện tại.
- AUTOEXTEND và MAXSIZE.
- Physical storage headroom.
- Resource limit.
- Growth rate.
- Alert log và monitoring history.
- Có backup/recovery file nào cần giữ không.

Đừng thực hiện cleanup chỉ dựa trên một alert cũ. Có thể tài nguyên đã được giải phóng hoặc alert phản ánh một spike đã kết thúc.

### 18.3. Bước 3 — Chọn containment ít rủi ro

Các lựa chọn tùy resource:
- Thêm datafile/tempfile nếu storage có đủ chỗ.
- Tăng FRA limit sau khi xác nhận physical storage.
- Reclaim backup/archive đủ điều kiện qua RMAN.
- Dừng hoặc điều chỉnh job/query bất thường theo change/incident policy.
- Giảm concurrency hoặc tạm hoãn batch không thiết yếu.
- Mở rộng ASM/filesystem/volume qua đội hạ tầng.
- Tăng process/session limit theo kế hoạch nếu có đủ memory và OS capacity.

Không xóa file database trực tiếp bằng OS, không xóa online redo log đang hoạt động và không truncate dữ liệu nghiệp vụ khi chưa có phê duyệt.

### 18.4. Bước 4 — Xác nhận phục hồi

Sau containment:
- Lệnh gây lỗi chạy lại được chưa?
- Archive destination có hoạt động không?
- TEMP usage có giảm hoặc còn đủ headroom không?
- Tablespace có thể allocate extent không?
- Session/process mới có đăng nhập được không?
- Alert mới có tiếp tục xuất hiện không?
- Ứng dụng có phục hồi latency/throughput không?

### 18.5. Bước 5 — Tìm nguyên nhân gốc

Phân loại:
- Growth bình thường nhưng kế hoạch thiếu.
- Autoextend/MAXSIZE cấu hình sai.
- Storage vật lý hết.
- Retention/cleanup thất bại.
- Query/job bất thường.
- Connection leak hoặc retry storm.
- Data load/partition lifecycle thay đổi.
- Backup/standby lag.
- Monitoring/alert đến muộn.

Sau incident, cập nhật forecast, threshold, runbook và ownership.

## 19. Runbook: tablespace cạn

Lỗi thường gặp:
- ORA-01653: không thể mở rộng table.
- ORA-01654: không thể mở rộng index.
- ORA-01658: không thể tạo initial extent.

### 19.1. Xác định tablespace và file

~~~sql
SELECT tablespace_name,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_data_files
WHERE tablespace_name = :tablespace_name
ORDER BY file_name;
~~~

~~~sql
SELECT tablespace_name,
       SUM(bytes) AS free_bytes,
       MAX(bytes) AS largest_free_extent
FROM dba_free_space
WHERE tablespace_name = :tablespace_name
GROUP BY tablespace_name;
~~~

### 19.2. Kiểm tra storage vật lý

Nếu file nằm trên ASM, xem disk group usable capacity. Nếu file nằm trên filesystem, kiểm tra mount point, inode và quota. Xác nhận storage có thể mở rộng trước khi chạy ALTER DATABASE.

### 19.3. Chọn hành động

- Resize file nếu có physical headroom và file chưa đạt giới hạn.
- Bật AUTOEXTEND với NEXT/MAXSIZE có kiểm soát.
- Thêm datafile cho smallfile tablespace.
- Với bigfile, mở rộng file duy nhất theo giới hạn.
- Xem xét purge/archive/partition lifecycle nếu dữ liệu hết hạn.
- Điều tra segment tăng bất thường bằng DBA_SEGMENTS.

Không drop segment để lấy chỗ nếu chưa xác nhận owner và yêu cầu retention.

## 20. Runbook: FRA hoặc archive destination đầy

Các lỗi có thể gồm ORA-19809, ORA-19804 và ORA-00257.

### 20.1. Xác định thành phần chiếm chỗ

~~~sql
SELECT name,
       space_limit,
       space_used,
       space_reclaimable,
       number_of_files
FROM v$recovery_file_dest;
~~~

~~~sql
SELECT file_type,
       percent_space_used,
       percent_space_reclaimable,
       number_of_files
FROM v$flash_recovery_area_usage;
~~~

### 20.2. Kiểm tra archive destinations

~~~sql
SELECT dest_id,
       status,
       destination,
       error
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Kiểm tra destination lỗi, network/standby state và archive generation.

### 20.3. Reclaim theo RMAN policy

- Kiểm tra backup gần nhất và retention policy.
- Xác nhận archived log đã backup và standby đã áp dụng nếu deletion policy yêu cầu.
- Dùng RMAN REPORT OBSOLETE và DELETE OBSOLETE theo policy.
- Nếu cần backup archive trước khi xóa, bảo đảm backup thành công và được xác minh.
- Nếu storage không đủ, provision thêm dung lượng hoặc thay đổi destination có kiểm soát.

Không xóa archived log bằng OS và không đặt deletion policy lỏng hơn chỉ để làm alert biến mất.

## 21. Runbook: TEMP cạn

Lỗi thường gặp: ORA-01652, unable to extend temp segment.

1. Xác định TEMP tablespace và tempfile.
2. Xem V$TEMP_SPACE_HEADER.
3. Xem V$TEMPSEG_USAGE để tìm session/SQL_ID.
4. Kiểm tra plan, sort/hash operation, parallelism và dữ liệu trung gian.
5. Nếu query hợp lệ và storage còn, thêm tempfile hoặc mở rộng.
6. Nếu query runaway, phối hợp owner để cancel hoặc điều chỉnh workload.
7. Xác nhận temp segment được giải phóng/reuse sau khi statement kết thúc.
8. Thiết lập cảnh báo peak và growth rate.

Không nhầm TEMP full với permanent tablespace full. Thêm datafile permanent không giải quyết TEMP exhaustion.

## 22. Runbook: UNDO cạn hoặc snapshot too old

Lỗi thường gặp:
- ORA-30036.
- ORA-01555.

1. Xem DBA_UNDO_EXTENTS theo trạng thái.
2. Xem V$UNDOSTAT theo interval.
3. Xác định transaction dài và query dài.
4. Kiểm tra undo generation rate và peak.
5. Kiểm tra UNDO_RETENTION và RETENTION GUARANTEE.
6. Tăng dung lượng nếu workload hợp lệ và storage đủ.
7. Điều chỉnh query/batch/transaction theo nghiệp vụ.
8. Theo dõi SSOLDERRCNT và NOSPACEERRCNT sau thay đổi.

Không kill transaction hoặc thay retention guarantee khi chưa hiểu ảnh hưởng tới consistency và transaction đang chạy.

## 23. Runbook: process/session limit

Lỗi thường gặp ORA-00020 hoặc ORA-00018.

1. Xem V$RESOURCE_LIMIT.
2. Phân nhóm session theo username, machine, program, module và status.
3. Kiểm tra connection pool active/idle/wait.
4. Tìm retry storm, leak hoặc job tạo process quá nhiều.
5. Giảm connection creation/concurrency nếu cần.
6. Tăng PROCESSES/SESSIONS chỉ sau khi đánh giá memory, OS limit và restart requirement.
7. Theo dõi peak utilization sau khi phục hồi.

Không chỉ tăng giới hạn mà bỏ qua nguyên nhân connection leak; hệ thống sẽ tiếp tục chạm giới hạn mới.

## 24. Runbook: memory exhaustion

Lỗi có thể gồm ORA-04031 hoặc ORA-04030.

1. Lấy alert log và trace file.
2. Xác định lỗi xảy ra ở SGA hay process PGA.
3. Xem V$SGASTAT/V$SGAINFO hoặc V$PGASTAT.
4. Xem số process/session, parallelism và SQL gây allocation lớn.
5. Kiểm tra OS memory/swap.
6. Kiểm tra memory target và giới hạn thực tế.
7. Giảm workload bất thường hoặc sửa query nếu cần.
8. Thay đổi memory parameter theo kế hoạch và xác nhận yêu cầu restart.

Không tăng SGA/PGA vượt khả năng OS. Swapping nặng có thể làm database chậm nghiêm trọng hơn.

## 25. Các lỗi thường gặp và ý nghĩa vận hành

| Mã lỗi | Ngữ cảnh thường gặp | Hướng điều tra đầu tiên |
| --- | --- | --- |
| ORA-01653 | Table không mở rộng được | Tablespace, datafile, free extent, MAXSIZE và storage |
| ORA-01654 | Index không mở rộng được | Index tablespace, rebuild/maintenance và file headroom |
| ORA-01658 | Không tạo được initial extent | Tablespace và kích thước extent yêu cầu |
| ORA-01652 | Không mở rộng được temporary segment | TEMP usage, SQL_ID, tempfile và sort/hash |
| ORA-30036 | Undo segment không mở rộng được | Undo extents, transaction, retention và dung lượng |
| ORA-01555 | Snapshot too old | Query duration, undo generation và retention |
| ORA-19809 | FRA vượt giới hạn | FRA usage, reclaimable, backup và archive |
| ORA-19804 | Không reclaim được đủ dung lượng FRA | Retention/deletion policy, file cần giữ |
| ORA-00257 | Archiver error | Archive destination, FRA/filesystem và standby |
| ORA-00020 | Hết process slot | PROCESSES, connection pool và process leak |
| ORA-00018 | Hết session slot | SESSIONS, pool và session leak |
| ORA-04031 | Không cấp phát được shared memory | SGA/pool, fragmentation và alert/trace |
| ORA-04030 | Process không cấp phát được memory | PGA, OS memory, query và parallelism |
| ORA-270xx | Lỗi I/O hệ điều hành | File path, permission, storage và OS error |

Mã lỗi chỉ là điểm bắt đầu. Đọc toàn bộ stack, alert log và trace để xác định resource, file và thao tác cụ thể.

## 26. Governance: ownership, ngân sách và quy trình mở rộng

Capacity planning cần có owner rõ ràng giữa DBA, storage, OS, application và business.

### 26.1. Phân công trách nhiệm

| Nhóm | Trách nhiệm |
| --- | --- |
| DBA | Tablespace, datafile, TEMP, UNDO, redo, FRA và database thresholds |
| Storage/Infrastructure | ASM backing storage, filesystem, SAN, volume, IOPS và capacity provisioning |
| Application team | Connection pool, query, batch, data retention và workload forecast |
| Security/Compliance | Retention, audit, backup protection và dữ liệu cần giữ |
| Operations/NOC | Nhận alert, incident routing, escalation và theo dõi |
| Business owner | Dự báo tăng trưởng, peak season và retention requirement |

### 26.2. Capacity review định kỳ

Một review hàng tháng có thể gồm:
- Top tablespace theo used/free/time-to-full.
- Growth theo ngày/tuần/tháng.
- FRA/archive/backup retention.
- TEMP và UNDO peak.
- ASM/filesystem headroom.
- Process/session peak.
- CPU/I/O saturation.
- Forecast 30/60/90 ngày.
- Storage provisioning lead time.
- Hành động và owner.

### 26.3. Quy trình yêu cầu mở rộng

Một request mở rộng nên nêu:
- Resource cần mở rộng.
- Current used/allocated/max.
- Growth rate và forecast.
- Lý do nghiệp vụ.
- Dung lượng cần thêm.
- Storage location và redundancy.
- Tác động tới backup/recovery.
- Chi phí và thời gian provision.
- Rollback/validation plan.
- Người phê duyệt và owner.

Không dùng một lệnh ALTER TABLESPACE để bỏ qua quy trình cấp phát storage nếu storage thuộc hạ tầng dùng chung.

## 27. Checklist thiết kế alert

Trước khi đưa threshold vào production, xác nhận:

1. Metric phản ánh đúng resource.
2. Unit và scope đã rõ.
3. Có absolute free threshold.
4. Có percentage threshold.
5. Có time-to-full threshold nếu growth đủ đo được.
6. Có peak baseline.
7. Warning đủ sớm để provision.
8. Critical đủ sớm để containment.
9. Có hysteresis và consecutive samples.
10. Có ngoại lệ cho maintenance window đã biết.
11. Có owner và escalation.
12. Có runbook tương ứng.
13. Có alert cho collector/monitoring failure.
14. Có kiểm tra alert delivery.
15. Có review false positive/false negative định kỳ.

## 28. Checklist khi tài nguyên gần cạn

- [ ] Xác định đúng database, instance, PDB và host.
- [ ] Ghi lại ORA error, timestamp và SQL_ID/session nếu có.
- [ ] Xác nhận current used/free và peak.
- [ ] Kiểm tra AUTOEXTEND, MAXSIZE và file state.
- [ ] Kiểm tra ASM/filesystem/quota/inode.
- [ ] Kiểm tra growth rate và time-to-full.
- [ ] Xác định segment/job/query gây tăng.
- [ ] Xác nhận backup, archive và standby retention trước cleanup.
- [ ] Chọn containment có rủi ro thấp.
- [ ] Thông báo owner và ghi nhận change.
- [ ] Xác nhận database/application phục hồi.
- [ ] Theo dõi lại metric sau incident.
- [ ] Cập nhật forecast, threshold và runbook.

## 29. Ví dụ thực hành: tính time-to-full cho tablespace

Giả sử một tablespace có:
- Used hiện tại: 720 GB.
- Configured usable ceiling: 900 GB.
- Physical storage còn có thể cấp cho datafile: 120 GB.
- Tốc độ tăng trung bình 7 ngày: 4 GB/ngày.
- Storage provisioning cần 10 ngày làm việc.

Headroom theo file/database là 180 GB, nhưng physical headroom chỉ 120 GB. Usable headroom thấp hơn là 120 GB.

\[
TimeToFull = 120 / 4 = 30\ days
\]

Nếu cần 10 ngày làm việc để provision, cộng thêm thời gian change/validation và buffer cho peak, warning phải phát sớm hơn 30 ngày. Ngưỡng 80% đơn thuần có thể không phản ánh đúng thời gian còn lại.

Nếu tốc độ tăng high scenario là 8 GB/ngày:

\[
TimeToFull_{high} = 120 / 8 = 15\ days
\]

Kế hoạch nên dựa vào kịch bản High nếu workload có khả năng xảy ra.

## 30. Ví dụ thực hành: thiết kế ngưỡng cho FRA

Giả sử:
- FRA limit: 2 TB.
- Used: 1,2 TB.
- Reclaimable: 300 GB.
- Archive generation: 80 GB/ngày.
- Backup chạy mỗi đêm.
- Storage provisioning mất 5 ngày.

Không nên coi 300 GB reclaimable là 300 GB chắc chắn có thể xóa ngay. Kiểm tra file type, backup policy và standby apply. Nếu chỉ còn 500 GB headroom không reclaim được, time-to-full theo archive generation là khoảng 6,25 ngày. Warning cần kích hoạt ngay để DBA xác minh backup/archive policy và đội storage chuẩn bị mở rộng.

Alert nên gồm:
- FRA used percent.
- Non-reclaimable bytes.
- Archive generation rate.
- Backup age/success.
- Standby apply lag.
- Forecast time-to-full.

## 31. Bài tập tự luyện

1. Phân biệt logical capacity và physical capacity.
2. Giải thích vì sao AUTOEXTEND không bảo đảm datafile có thể tăng.
3. Nêu các thành phần cần đưa vào baseline capacity.
4. Tính growth/day khi used tăng 60 GB trong 12 ngày.
5. Tính time-to-full khi headroom 240 GB và growth 8 GB/ngày.
6. Vì sao phải lập base, high và stress scenario?
7. Nêu các yếu tố ảnh hưởng tới table/index growth.
8. Vì sao index rebuild cần dự trù peak storage?
9. Viết truy vấn xem datafile, MAXBYTES và AUTOEXTENSIBLE.
10. Viết truy vấn tổng hợp free extents của permanent tablespace.
11. Giải thích giới hạn của theoretical autoextend headroom.
12. Phân biệt bigfile và smallfile tablespace khi mở rộng.
13. Viết lệnh thêm datafile cho smallfile tablespace.
14. Vì sao không xóa datafile bằng OS?
15. Giải thích USABLE_FILE_MB của ASM khác FREE_MB thế nào.
16. Viết truy vấn kiểm tra FRA usage và reclaimable space.
17. Vì sao không xóa archived redo trực tiếp bằng OS?
18. Phân biệt TEMP exhaustion và permanent tablespace exhaustion.
19. Viết truy vấn tìm session đang dùng TEMP theo SQL_ID.
20. Phân biệt ACTIVE, UNEXPIRED và EXPIRED undo extent.
21. Giải thích mối liên hệ giữa ORA-30036 và ORA-01555.
22. Viết truy vấn xem V$UNDOSTAT.
23. Viết truy vấn xem PROCESSES/SESSIONS current và peak utilization.
24. Vì sao tăng PROCESSES có thể gây memory pressure?
25. Phân biệt ORA-04031 và ORA-04030.
26. Thiết kế warning/critical threshold có hysteresis cho tablespace.
27. Vì sao time-to-full thường hữu ích hơn percentage đơn lẻ?
28. Lập runbook xử lý ORA-00257.
29. Thiết kế capacity review hàng tháng cho database có RAC và nhiều PDB.
30. Viết kế hoạch 90 ngày kết hợp growth forecast, storage lead time, alert, owner và hành động mở rộng.

**Capacity planning phải kết nối số liệu Oracle với giới hạn storage, tốc độ tăng trưởng và thời gian phản ứng của đội vận hành.** Theo dõi allocated/used/free, autoextend/MAXSIZE, ASM/filesystem, FRA, TEMP, UNDO, process và memory theo đúng scope; đặt ngưỡng theo cả phần trăm, dung lượng còn lại và time-to-full. Khi tài nguyên cạn, xác định đúng resource và nguyên nhân, chọn containment an toàn, xác nhận dịch vụ phục hồi rồi cập nhật forecast, alert và runbook để sự cố không lặp lại.

