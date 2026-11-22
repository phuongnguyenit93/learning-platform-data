# Transportable tablespace và full transportable theo điều kiện tương thích

## 1. Tổng quan

**Transportable Tablespaces (TTS)** là phương pháp di chuyển dữ liệu Oracle bằng cách chuyển metadata qua Data Pump và chuyển datafile của tablespace sang database đích. Thay vì đọc rồi ghi lại toàn bộ row như export/import truyền thống, Oracle có thể gắn các datafile đã được vận chuyển vào database đích sau khi xác nhận metadata và điều kiện tương thích.

Phương pháp này đặc biệt hữu ích khi:

- Di chuyển một tập tablespace lớn giữa hai database.
- Chuyển dữ liệu giữa các hệ thống có storage hoặc platform khác nhau.
- Giảm thời gian downtime so với export/import row-level cho khối lượng dữ liệu lớn.
- Tách một nhóm schema/tablespace khỏi database nguồn.
- Di chuyển dữ liệu từ hệ thống cũ sang database mới trong một kế hoạch nâng cấp.

**Full Transportable Export/Import** mở rộng phương pháp này lên gần phạm vi toàn database. Các user tablespace được vận chuyển bằng datafile; metadata và dữ liệu nằm trong các tablespace không thể transport (đặc biệt SYSTEM và SYSAUX) được xử lý qua Data Pump.

Hai phương pháp không phải là một bản backup. Datafile được copy sang target phải nhất quán, metadata phải khớp với datafile, và các dependency phải được kiểm tra trước khi đưa database đích vào sử dụng.

## 2. Transportable Tablespaces hoạt động như thế nào?

Một transportable tablespace set gồm:

1. Datafile của các tablespace được chọn.
2. Metadata mô tả object trong các tablespace đó, được xuất bằng Data Pump.
3. Các dependency cần thiết để tập tablespace có thể được gắn vào database đích.

Luồng cơ bản:

~~~text
SOURCE DATABASE
      |
      | 1. Kiểm tra transport set tự chứa
      v
DBMS_TTS.TRANSPORT_SET_CHECK
      |
      | 2. Đưa tablespace về READ ONLY
      v
ALTER TABLESPACE ... READ ONLY
      |
      | 3. Export metadata
      v
Data Pump expdp
      |
      +--------------------------+
      |                          |
      v                          v
Metadata dump file          Tablespace datafiles
      |                          |
      +------------+-------------+
                   |
                   | 4. Copy sang target
                   v
             TARGET DATABASE
                   |
                   | 5. impdp + TRANSPORT_DATAFILES
                   v
             Attach/import metadata
                   |
                   | 6. Kiểm tra object và dependency
                   v
             READ WRITE / Application
~~~

Điểm khác biệt cốt lõi:

- Dump file của TTS chủ yếu chứa metadata.
- Dữ liệu bảng nằm trong datafile được copy riêng.
- Datafile phải ở trạng thái nhất quán khi được vận chuyển.
- Target phải hiểu metadata, block format, platform và các thuộc tính liên quan của datafile.

## 3. Phạm vi và điều kiện của transport set

### 3.1. Chọn đúng tablespace

Transportable tablespace làm việc ở cấp tablespace, không phải chỉ cấp schema. Một schema có thể có object nằm trong nhiều tablespace; một tablespace cũng có thể chứa object của nhiều schema.

Trước khi chọn transport set, kiểm tra:

~~~sql
SELECT owner,
       segment_type,
       segment_name,
       partition_name,
       tablespace_name
FROM dba_segments
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX')
ORDER BY owner, segment_type, segment_name;
~~~

Với partitioned table hoặc partitioned index, các partition/subpartition có thể nằm ở nhiều tablespace. Phải xác định toàn bộ tablespace chứa các phần cần vận chuyển.

### 3.2. Transport set phải self-contained

Một transport set được gọi là **self-contained** khi các dependency cần thiết không vượt ra ngoài tập tablespace được chọn theo những quy tắc kiểm tra của Oracle.

Ví dụ:

- Table ở APP_DATA có foreign key tham chiếu table ở APP_REFERENCE.
- Nếu chỉ transport APP_DATA, dependency tham chiếu có thể nằm ngoài tập.
- Có thể cần đưa APP_REFERENCE vào transport set hoặc xử lý dependency theo thiết kế được hỗ trợ.

Kiểm tra bằng package DBMS_TTS:

~~~sql
EXEC DBMS_TTS.TRANSPORT_SET_CHECK(
    ts_list          => 'APP_DATA,APP_INDEX,APP_REFERENCE',
    incl_constraints => TRUE,
    full_check       => TRUE
);
~~~

Xem vi phạm:

~~~sql
SELECT *
FROM transport_set_violations;
~~~

Nếu query trả về row, cần xử lý từng vi phạm trước khi export. Không bỏ qua cảnh báo chỉ để hoàn tất lệnh expdp.

### 3.3. Vì sao cần kiểm tra cả constraint?

Foreign key hoặc constraint có thể liên kết object trong các tablespace khác nhau. Khi transport một phần, target có thể thiếu table được tham chiếu hoặc không có metadata cần thiết để tạo lại dependency.

Sử dụng FULL_CHECK để yêu cầu kiểm tra dependency đầy đủ theo phạm vi DBMS_TTS. Kiểm tra cả index, partition, LOB segment và các object liên quan trong data dictionary.

### 3.4. Các tablespace không transport như tablespace ứng dụng thông thường

Không chọn các tablespace hệ thống như SYSTEM, SYSAUX, UNDO hoặc TEMP làm transportable application tablespace set. Chúng có vai trò nội bộ trong database và được tạo/quản lý theo kiến trúc database đích.

Với full transportable, SYSTEM và SYSAUX vẫn thuộc database đích; dữ liệu người dùng nằm trong các tablespace này được xử lý theo cơ chế Data Pump thay vì copy nguyên datafile hệ thống.

### 3.5. Kiểm tra tablespace và datafile

~~~sql
SELECT tablespace_name,
       status,
       contents,
       block_size,
       bigfile
FROM dba_tablespaces
ORDER BY tablespace_name;

SELECT tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible
FROM dba_data_files
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX', 'APP_REFERENCE')
ORDER BY tablespace_name, file_id;
~~~

Đảm bảo đã nhận diện đúng tất cả datafile, kể cả file thuộc tablespace nhiều datafile hoặc bigfile tablespace.

## 4. Điều kiện tương thích giữa source và target

TTS không đơn giản là copy một file DBF sang máy khác. Datafile có platform, endian format, block size, database compatibility và metadata phụ thuộc database. Cần lập compatibility matrix trước khi thực hiện.

### 4.1. Platform và endian format

Oracle cung cấp danh sách platform có thể dùng cho transport:

~~~sql
SELECT platform_id,
       platform_name,
       endian_format
FROM v$transportable_platform
ORDER BY platform_name;
~~~

Kiểm tra platform database hiện tại:

~~~sql
SELECT platform_name
FROM v$database;
~~~

Nếu source và target có cùng endian format, datafile thường không cần endian conversion. Nếu khác endian format, phải chuyển đổi datafile bằng RMAN CONVERT hoặc phương pháp được Oracle hỗ trợ.

Ví dụ về endian:

| Platform family | Endian thường gặp |
| --- | --- |
| Linux x86/x86-64 | Little endian |
| Windows x86/x86-64 | Little endian |
| Solaris SPARC | Big endian |
| AIX POWER | Big endian |

Không dựa vào tên hệ điều hành để tự kết luận; hãy lấy ENDIAN_FORMAT từ V$TRANSPORTABLE_PLATFORM cho chính platform source và target.

### 4.2. Chuyển đổi endian bằng RMAN

Ví dụ minh họa chuyển tablespace sang platform đích:

~~~text
RMAN> CONVERT TABLESPACE app_data
      TO PLATFORM 'Linux x86 64-bit'
      FORMAT '/stage/tts/%U';
~~~

Tên platform phải khớp với PLATFORM_NAME trong V$TRANSPORTABLE_PLATFORM. FORMAT là vị trí file đầu ra trên host chạy conversion.

Có thể thực hiện conversion ở source hoặc target tùy workflow, network và staging storage. Dù chọn vị trí nào, datafile phải ở trạng thái nhất quán theo yêu cầu của RMAN và TTS. Thực hiện conversion trước khi import/attach datafile vào target.

Ví dụ kiểm tra file đã chuyển:

~~~text
RMAN> CONVERT DATAFILE '/stage/tts/app_data01.dbf'
      TO PLATFORM 'Linux x86 64-bit'
      FORMAT '/target/stage/app_data01.dbf';
~~~

Đây là cú pháp minh họa; với file đã convert ở source thì không convert lần nữa. Không chuyển đổi datafile đang được ghi bởi source database.

### 4.3. Database version và COMPATIBLE

Data Pump dump file có version metadata và target phải có khả năng đọc metadata đó. Quy tắc chung là đường di chuyển từ source sang target cùng version hoặc target mới hơn; không giả định có thể transport ngược từ database mới sang database cũ.

Kiểm tra:

~~~sql
SELECT banner_full
FROM v$version
WHERE banner_full LIKE 'Oracle Database%';

SHOW PARAMETER compatible;
~~~

Đối chiếu:

- Release và Release Update của source/target.
- Data Pump export/import version.
- COMPATIBLE initialization parameter.
- Các feature hoặc datatype chỉ có ở phiên bản source.
- Quy tắc downgrade/upgrade trong Oracle Database Upgrade Guide.

Không hạ COMPATIBLE chỉ để ép một file transportable tương thích. Thay đổi COMPATIBLE có thể ảnh hưởng tính năng và khả năng downgrade.

### 4.4. Block size

Tablespace có thể dùng block size khác standard block size của database. Target cần được cấu hình cache tương ứng để hỗ trợ nonstandard block size.

Kiểm tra:

~~~sql
SELECT tablespace_name,
       block_size
FROM dba_tablespaces
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');

SHOW PARAMETER db_block_size;
SHOW PARAMETER db_2k_cache_size;
SHOW PARAMETER db_4k_cache_size;
SHOW PARAMETER db_8k_cache_size;
SHOW PARAMETER db_16k_cache_size;
SHOW PARAMETER db_32k_cache_size;
~~~

Các cache parameter chỉ là ví dụ theo kích thước block. Chỉ cấu hình cache cần thiết cho target và bảo đảm SGA đủ dung lượng.

### 4.5. Character set và national character set

Vì dữ liệu bảng được vận chuyển bên trong datafile, không được giả định Data Pump sẽ chuyển đổi mọi byte dữ liệu trong datafile như conventional export/import.

Trước khi transport, so sánh:

~~~sql
SELECT parameter,
       value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
~~~

Với transportable tablespace truyền thống, hãy coi sự tương thích character set giữa source và target là một cổng bắt buộc phải xác nhận theo đúng release/platform. Nếu character set khác, không tiếp tục chỉ vì metadata export/import chạy được; đánh giá phương án chuyển đổi được Oracle hỗ trợ, chẳng hạn Data Pump conventional migration hoặc chuyển đổi database theo quy trình riêng.

Full transportable có thể xử lý dữ liệu trong non-transportable tablespace qua Data Pump, nhưng các datafile transportable vẫn cần tuân theo điều kiện tương thích của transportable data. Không dùng full transportable như cách tự động chuyển đổi mọi character set.

### 4.6. Time zone file version

Nếu tablespace có cột TIMESTAMP WITH TIME ZONE, cần kiểm tra timezone file version:

~~~sql
SELECT filename,
       version
FROM v$timezone_file;
~~~

Khác biệt timezone file có thể ảnh hưởng cách diễn giải dữ liệu timestamp và khả năng import/upgrade. Xác định target timezone file version, kiểm tra yêu cầu của Oracle Data Pump/TTS và thực hiện DBMS_DST upgrade nếu cần theo quy trình riêng. Không tự sửa byte trong datafile để xử lý timezone.

### 4.7. TDE và encrypted tablespace

Nếu transport set chứa encrypted tablespace hoặc dữ liệu phụ thuộc TDE:

- Xác định keystore/wallet đang dùng.
- Kiểm tra keystore đã backup và có thể mở.
- Bảo đảm target có key cần thiết hoặc quy trình export/import key được thực hiện đúng.
- Chuyển key qua kênh an toàn, không đặt secret trong command history hoặc log.
- Kiểm tra chế độ encryption, algorithm và key version sau import.

Datafile encrypted không thể đọc chỉ bằng cách copy file sang target nếu target không có key phù hợp. Với encrypted tablespace, cần tuân thủ quy trình TDE transportable tablespace của đúng release.

### 4.8. Các điều kiện khác

Kiểm tra thêm:

- Database target đã tạo và mở đúng trạng thái.
- Tablespace target name không xung đột.
- User/schema owner và quota tồn tại hoặc được import đúng.
- Target có đủ dung lượng cho mọi datafile.
- Directory object của Data Pump tồn tại và quyền đọc/ghi đúng.
- File permission/ownership trên filesystem phù hợp.
- ASM disk group hoặc OMF path được cấu hình đúng.
- Tablespace encryption, compression, SecureFiles và datatype được hỗ trợ.
- Không có dependency nằm ngoài transport set.

## 5. Quy trình Transportable Tablespaces truyền thống

Ví dụ transport APP_DATA và APP_INDEX từ source sang target. Giả định hai tablespace đã được kiểm tra tương thích và target đã chuẩn bị schema/metadata cần thiết.

### Bước 1. Kiểm tra source

~~~sql
SELECT name,
       open_mode,
       database_role,
       platform_name
FROM v$database;

SELECT tablespace_name,
       status,
       contents,
       block_size
FROM dba_tablespaces
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');
~~~

Kiểm tra tất cả object và datafile thuộc hai tablespace. Chạy DBMS_TTS.TRANSPORT_SET_CHECK với FULL_CHECK trước khi chuyển.

### Bước 2. Xác nhận transport set tự chứa

~~~sql
EXEC DBMS_TTS.TRANSPORT_SET_CHECK(
    ts_list          => 'APP_DATA,APP_INDEX',
    incl_constraints => TRUE,
    full_check       => TRUE
);

SELECT *
FROM transport_set_violations;
~~~

Kết quả cần không còn vi phạm. Nếu có vi phạm, mở rộng transport set hoặc xử lý dependency trước khi tiếp tục.

### Bước 3. Đưa tablespace về READ ONLY

~~~sql
ALTER TABLESPACE app_data READ ONLY;
ALTER TABLESPACE app_index READ ONLY;
~~~

READ ONLY giúp datafile không thay đổi trong lúc export metadata và copy. Ứng dụng không thể tiếp tục ghi vào các tablespace này trong thời gian cutover.

### Bước 4. Export metadata bằng Data Pump

Tạo directory object nếu chưa có:

~~~sql
CREATE OR REPLACE DIRECTORY dpump_dir AS '/u02/dpump';
GRANT READ, WRITE ON DIRECTORY dpump_dir TO system;
~~~

Chạy expdp:

~~~text
expdp system@source_db DIRECTORY=DPUMP_DIR
  DUMPFILE=app_tts.dmp
  LOGFILE=app_tts_export.log
  TRANSPORT_TABLESPACES=APP_DATA,APP_INDEX
  TRANSPORT_FULL_CHECK=Y
~~~

Transportable export tập trung vào metadata của object trong tablespace; row data vẫn nằm trong datafile. Bảo vệ dump file và log theo chính sách vận hành.

### Bước 5. Copy datafile và dump file

Copy tất cả datafile thuộc APP_DATA và APP_INDEX sang staging/target. Copy dump file app_tts.dmp sang directory mà Data Pump import có thể đọc.

Nếu source và target khác endian, thực hiện RMAN conversion theo platform target trước khi import. Nếu cùng endian, có thể copy datafile nguyên trạng khi các điều kiện khác đáp ứng.

Không copy thiếu datafile hoặc chỉ copy một file trong tablespace nhiều datafile.

### Bước 6. Import metadata và gắn datafile

Trên target:

~~~text
impdp system@target_db DIRECTORY=DPUMP_DIR
  DUMPFILE=app_tts.dmp
  LOGFILE=app_tts_import.log
  TRANSPORT_DATAFILES='/u03/oradata/target/app_data01.dbf',
                     '/u03/oradata/target/app_index01.dbf'
~~~

Đường dẫn trong TRANSPORT_DATAFILES là đường dẫn target có thể truy cập. Với ASM/OMF, sử dụng đường dẫn và cú pháp phù hợp với kiến trúc storage đích.

### Bước 7. Kiểm tra target

~~~sql
SELECT tablespace_name,
       status,
       contents,
       block_size
FROM dba_tablespaces
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');

SELECT owner,
       object_type,
       COUNT(*) AS object_count
FROM dba_objects
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX')
GROUP BY owner, object_type
ORDER BY owner, object_type;
~~~

DBA_OBJECTS không có TABLESPACE_NAME cho mọi object type; dùng DBA_SEGMENTS để kiểm tra segment placement:

~~~sql
SELECT owner,
       segment_type,
       COUNT(*) AS segment_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX')
GROUP BY owner, segment_type
ORDER BY owner, segment_type;
~~~

Kiểm tra object invalid, constraint, index, grants và application smoke test trước khi mở traffic.

### Bước 8. Chuyển tablespace sang READ WRITE

Trên target, sau khi xác nhận import và file status:

~~~sql
ALTER TABLESPACE app_data READ WRITE;
ALTER TABLESPACE app_index READ WRITE;
~~~

Trên source, sau khi cutover hoàn tất và không còn yêu cầu giữ source ở READ ONLY:

~~~sql
ALTER TABLESPACE app_data READ WRITE;
ALTER TABLESPACE app_index READ WRITE;
~~~

Không mở ghi đồng thời trên source và target nếu chưa có cơ chế đồng bộ dữ liệu được thiết kế. Sau cutover, xác định rõ hệ thống nào là writer chính.

## 6. Full Transportable Export/Import

### 6.1. Full transportable là gì?

Full transportable kết hợp transportable tablespaces và Data Pump full export/import để di chuyển gần như toàn bộ database:

- User data trong các tablespace transportable được di chuyển bằng datafile.
- Metadata của database được xuất/import bằng Data Pump.
- Dữ liệu nằm trong non-transportable tablespace được chuyển qua Data Pump thay vì copy nguyên datafile.
- SYSTEM và SYSAUX của database đích vẫn được tạo và quản lý bởi target database.

Điều này giảm lượng row phải đi qua dump file so với full conventional export/import, đặc biệt khi phần lớn dữ liệu nghiệp vụ nằm trong user tablespaces lớn.

### 6.2. Nguồn và đích được hỗ trợ

Full transportable được giới thiệu để hỗ trợ di chuyển từ Oracle Database 11g Release 2 11.2.0.3 trở lên sang Oracle Database 12c Release 1 12.1 hoặc mới hơn theo ma trận hỗ trợ. Target phải hỗ trợ metadata và định dạng transportable được tạo từ source.

Luôn kiểm tra:

- Phiên bản source và target.
- Data Pump compatibility và VERSION parameter.
- COMPATIBLE.
- Platform/endian.
- Database character set.
- Time zone file.
- Block size và feature được sử dụng.

Không dùng ví dụ 11.2.0.3 sang 12.1 làm bằng chứng rằng mọi source/target version đều tương thích.

### 6.3. SYSTEM và SYSAUX trong full transportable

SYSTEM và SYSAUX không được chuyển bằng cách gắn datafile của source vào target. Chúng thuộc cấu trúc database đích.

Nếu có user object nằm trong SYSTEM hoặc SYSAUX, Data Pump chuyển metadata và dữ liệu object đó theo cơ chế export/import phù hợp. Vì vậy, full transportable vẫn cần dump file có dung lượng và thời gian đủ cho dữ liệu nằm trong non-transportable tablespace.

### 6.4. Chuẩn bị source

Kiểm tra tablespace:

~~~sql
SELECT tablespace_name,
       contents,
       status,
       block_size
FROM dba_tablespaces
ORDER BY tablespace_name;
~~~

Xác định user tablespace sẽ được transport. Đưa các tablespace này về READ ONLY theo quy trình cutover và kiểm tra self-contained/full transport dependencies.

### 6.5. Full transportable export

Ví dụ:

~~~text
expdp system@source_db DIRECTORY=DPUMP_DIR
  FULL=Y
  TRANSPORTABLE=ALWAYS
  TRANSPORT_FULL_CHECK=Y
  DUMPFILE=full_tts_%U.dmp
  FILESIZE=20G
  LOGFILE=full_tts_export.log
~~~

FULL=Y yêu cầu export metadata ở phạm vi full database. TRANSPORTABLE=ALWAYS yêu cầu Data Pump sử dụng phương thức transportable cho các tablespace đủ điều kiện. TRANSPORT_FULL_CHECK=Y yêu cầu kiểm tra dependency đầy đủ.

Data Pump có thể xuất dữ liệu trong non-transportable tablespace vào dump file. Datafile của user tablespace transportable vẫn phải được copy riêng.

### 6.6. Copy datafile

Copy toàn bộ datafile của user tablespace được transport sang target. Nếu khác endian, dùng RMAN CONVERT. Giữ nguyên source tablespace READ ONLY cho đến khi datafile snapshot đã được copy/convert hoàn tất.

### 6.7. Full transportable import

Ví dụ:

~~~text
impdp system@target_db DIRECTORY=DPUMP_DIR
  FULL=Y
  DUMPFILE=full_tts_%U.dmp
  TRANSPORT_DATAFILES='/u03/oradata/target/app_data01.dbf',
                     '/u03/oradata/target/app_index01.dbf'
  LOGFILE=full_tts_import.log
~~~

Danh sách TRANSPORT_DATAFILES phải khớp toàn bộ datafile transportable có trong dump metadata. Dữ liệu từ non-transportable tablespace được nạp từ dump file.

### 6.8. Sau import

Kiểm tra:

- Database users, roles, profiles và grants.
- Tablespace/datafile status.
- Object count, segment size và invalid objects.
- Public/private synonym, database link và directory.
- External table, scheduler job, credential và network ACL.
- TDE keystore và encrypted tablespace.
- Database link, service và application configuration.
- Character set/timezone và các feature phụ thuộc version.

Full transportable không tự động di chuyển mọi cấu hình ngoài database như listener, wallet file, OS credential, external file, backup policy, service registration hoặc ứng dụng ở middle tier.

## 7. So sánh TTS, full transportable và Data Pump conventional

| Tiêu chí | Transportable tablespaces | Full transportable | Conventional Data Pump |
| --- | --- | --- | --- |
| Phạm vi | Một hoặc một nhóm tablespace | Gần như toàn database | Schema/table/full export |
| Dữ liệu user tablespace | Copy datafile | Copy datafile | Đọc/ghi qua dump file |
| Metadata | Data Pump | Data Pump full | Data Pump |
| Data trong SYSTEM/SYSAUX | Không thuộc transport set thông thường | Chuyển qua dump file khi cần | Chuyển qua dump file |
| Self-contained check | Cần cho transport set | Kiểm tra dependency full | Không yêu cầu transport set |
| Downtime | READ ONLY/cutover của tablespace được chọn | READ ONLY/cutover cho user tablespace transportable và export phần còn lại | Phụ thuộc export/import, consistency và phương án downtime |
| Cross-endian | RMAN conversion nếu khác endian | RMAN conversion cho datafile transportable nếu khác endian | Data Pump xử lý dữ liệu theo cơ chế logical |
| Use case | Di chuyển dữ liệu lớn theo tablespace | Di chuyển database gần toàn bộ | Chuyển schema/table, lọc hoặc tái cấu trúc dữ liệu |

### 7.1. Khi nào chọn TTS?

Chọn TTS khi chỉ cần một nhóm tablespace lớn, có thể xác định dependency rõ và target đã có database phù hợp.

### 7.2. Khi nào chọn full transportable?

Chọn full transportable khi muốn chuyển gần toàn bộ database, phần lớn dữ liệu nằm trong user tablespaces transportable và các điều kiện compatibility được đáp ứng.

### 7.3. Khi nào chọn conventional Data Pump?

Chọn conventional Data Pump khi cần:

- Chuyển một số schema/table.
- Lọc row hoặc object.
- Đổi cấu trúc/schema/table.
- Chuyển đổi dữ liệu qua cơ chế logical.
- Nguồn/đích không đáp ứng điều kiện TTS.

Conventional Data Pump có thể chậm hơn với khối lượng dữ liệu rất lớn nhưng linh hoạt hơn về logical transformation.

## 8. Cross-platform transport và RMAN CONVERT

### 8.1. Cùng endian

Nếu source và target cùng endian format, không cần endian conversion. Vẫn phải kiểm tra platform compatibility, version, block size, character set, timezone và TDE.

### 8.2. Khác endian

Nếu endian khác:

1. Đưa tablespace về READ ONLY.
2. Chạy RMAN CONVERT TABLESPACE hoặc CONVERT DATAFILE sang platform target.
3. Xác nhận file đầu ra và vị trí.
4. Copy file đã convert và metadata dump.
5. Import trên target.
6. Kiểm tra datafile/tablespace.

Không copy datafile big endian sang little endian rồi attach trực tiếp mà không conversion.

### 8.3. Kiểm tra platform target

~~~sql
SELECT platform_name,
       endian_format
FROM v$transportable_platform
WHERE platform_name IN (
    'Linux x86 64-bit',
    'Microsoft Windows x86 64-bit'
);
~~~

Tên cụ thể phải lấy từ view trên database; không hardcode tên platform theo ví dụ nếu khác release.

### 8.4. Conversion trên source hay target?

RMAN có thể thực hiện conversion trên source hoặc target. Chọn theo:

- CPU và I/O của host.
- Băng thông mạng.
- Dung lượng staging.
- Source có thể chịu conversion workload hay không.
- Security boundary và quyền đọc datafile.

Nếu convert trên target, chuyển file gốc tới staging trước và đảm bảo target host có thể đọc file. Nếu convert trên source, chỉ copy file output đã convert.

### 8.5. Không dùng OS byte-swap tự chế

Datafile Oracle có header, block structure và metadata nội bộ. Không tự viết script đổi byte order hoặc sửa header bằng công cụ hệ điều hành. Dùng RMAN CONVERT hoặc phương thức Oracle hỗ trợ.

## 9. Giảm downtime với incremental transportable tablespaces

Với tablespace rất lớn, thời gian READ ONLY để copy toàn bộ datafile có thể dài. Oracle có phương pháp incremental cross-platform transportable tablespaces (XTTS) dùng RMAN incremental backup để áp dụng thay đổi trong khi source vẫn tiếp tục ghi ở các giai đoạn phù hợp.

Luồng khái quát:

1. Chuẩn bị source/target và transport set.
2. Tạo baseline backup datafile.
3. Copy baseline sang target.
4. Thực hiện các incremental backup ở source.
5. Chuyển incremental backup sang target và apply vào datafile copy.
6. Lặp lại cho đến khi delta nhỏ.
7. Đưa tablespace READ ONLY trong cutover window.
8. Apply incremental cuối cùng.
9. Export metadata, import/attach và mở tablespace ở target.
10. Chuyển ứng dụng sang target.

XTTS có quy trình riêng, phụ thuộc phiên bản, platform, block size và RMAN support. Không thay thế nó bằng việc tự copy datafile đang ghi. Thực hiện theo Oracle XTTS documentation và script được hỗ trợ cho đúng release.

## 10. Tên file, OMF và ASM ở target

Đường dẫn datafile ở source thường không tồn tại ở target. Cần xác định cách đặt tên:

- TRANSPORT_DATAFILES chỉ định file target.
- OMF có thể tự sinh tên theo DB_CREATE_FILE_DEST.
- ASM cần đường dẫn disk group và quyền truy cập phù hợp.
- Có thể dùng các tham số Data Pump như REMAP_DATAFILE trong tình huống được hỗ trợ.

Ví dụ filesystem:

~~~text
TRANSPORT_DATAFILES='/u03/oradata/target/app_data01.dbf'
~~~

Ví dụ ASM:

~~~text
TRANSPORT_DATAFILES='+DATA/DBTARGET/DATAFILE/app_data.123.123456789'
~~~

Đường dẫn ASM trên là minh họa; tên file thực tế có thể do OMF sinh. Không sửa file name trong metadata bằng cách đổi tên file bên ngoài database mà không cập nhật theo quy trình Oracle.

## 11. User, schema, grants và dependency

### 11.1. TTS không đồng nghĩa di chuyển toàn bộ môi trường ứng dụng

Transportable tablespace chuyển object và metadata liên quan đến tablespace. Các cấu hình cấp database hoặc nằm ngoài tablespace có thể cần migrate riêng:

- User, role và profile.
- System privilege và role grants.
- Tablespace quota.
- Public synonym.
- Database link.
- Directory object và OS directory.
- Scheduler job, credential và external job.
- Network ACL.
- Context, service và application configuration.
- TDE wallet/keystore.

Full transportable có phạm vi metadata rộng hơn vì FULL=Y, nhưng vẫn cần kiểm tra các yếu tố external và các cấu hình phụ thuộc môi trường.

### 11.2. Schema owner và quota

Kiểm tra user:

~~~sql
SELECT username,
       default_tablespace,
       temporary_tablespace,
       account_status
FROM dba_users
WHERE username IN ('APP_OWNER', 'APP_READ');
~~~

Kiểm tra quota:

~~~sql
SELECT username,
       tablespace_name,
       bytes,
       max_bytes
FROM dba_ts_quotas
WHERE username = 'APP_OWNER';
~~~

Đảm bảo user có default tablespace và quota phù hợp. Không cấp UNLIMITED TABLESPACE một cách máy móc.

### 11.3. Object grants

Kiểm tra grants:

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'APP_OWNER'
ORDER BY table_name, grantee, privilege;
~~~

Sau import, xác nhận grantee tồn tại, role được cấp và quyền hiệu lực phù hợp. Không giả định mọi grant ngoài object sẽ tự xuất hiện chỉ vì datafile đã attach.

### 11.4. Dependency ngoài tablespace

Kiểm tra view, procedure, package và synonym tham chiếu object được transport. Một object ở schema khác hoặc tablespace khác có thể phụ thuộc table được chuyển. Sau import, compile invalid object và chạy smoke test ứng dụng.

## 12. CDB/PDB và transportable tablespaces

Trong kiến trúc multitenant, phải phân biệt:

- Transport trong cùng CDB/PDB.
- Transport giữa hai PDB.
- Transport giữa non-CDB và PDB.
- Di chuyển toàn bộ PDB bằng unplug/plug.

Nếu mục tiêu là chuyển nguyên một PDB, unplug/plug hoặc clone PDB có thể phù hợp hơn transportable tablespace. Nếu chỉ chuyển một nhóm tablespace vào PDB đích, kiểm tra quy tắc TTS của multitenant và khả năng tương thích của source/target PDB.

Kiểm tra container hiện tại:

~~~sql
SHOW CON_NAME;

SELECT con_id,
       name,
       open_mode
FROM v$pdbs
ORDER BY con_id;
~~~

Đảm bảo expdp/impdp kết nối đúng PDB service. Không chạy import vào CDB root nếu object phải thuộc một PDB ứng dụng.

## 13. Kiểm tra sau import và cutover

### 13.1. Tablespace/datafile

~~~sql
SELECT tablespace_name,
       status,
       contents,
       block_size
FROM dba_tablespaces
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');

SELECT file_name,
       tablespace_name,
       status,
       bytes
FROM dba_data_files
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX');
~~~

### 13.2. Segment và object

~~~sql
SELECT owner,
       segment_type,
       COUNT(*) AS segment_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_segments
WHERE tablespace_name IN ('APP_DATA', 'APP_INDEX')
GROUP BY owner, segment_type
ORDER BY owner, segment_type;
~~~

### 13.3. Invalid objects

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
FROM dba_objects
WHERE status = 'INVALID'
  AND owner IN ('APP_OWNER', 'APP_API')
ORDER BY owner, object_type, object_name;
~~~

### 13.4. Constraint và index

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM dba_constraints
WHERE owner = 'APP_OWNER'
ORDER BY table_name, constraint_name;

SELECT owner,
       index_name,
       table_name,
       status
FROM dba_indexes
WHERE owner = 'APP_OWNER'
ORDER BY table_name, index_name;
~~~

### 13.5. Row count và application checks

Không chỉ so sánh kích thước file. Chọn các bảng nghiệp vụ quan trọng, kiểm tra row count, tổng số tiền, min/max business key, partition count và các invariant nghiệp vụ.

Nếu có thể, tạo báo cáo đối chiếu ở source và target trước khi cutover. Chú ý source có thể thay đổi sau thời điểm snapshot; phải so sánh cùng SCN/snapshot hoặc giữ source READ ONLY trong giai đoạn đối chiếu.

### 13.6. Application smoke test

Kiểm tra:

- Kết nối bằng service đích.
- SELECT/INSERT/UPDATE trong transaction thử.
- Package/procedure quan trọng.
- Database link và external integration.
- Job, scheduler và queue.
- Quyền của application account.
- Tốc độ query và execution plan quan trọng.
- Backup/recovery policy của target.

## 14. Các lỗi thường gặp

| Hiện tượng/lỗi | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Transport set violations | Dependency nằm ngoài tablespace được chọn | Mở rộng transport set hoặc xử lý dependency |
| ORA-399xx khi kiểm tra TTS | Transport set không self-contained hoặc vi phạm điều kiện | Đọc TRANSPORT_SET_VIOLATIONS và sửa từng dependency |
| ORA-29345 / endian mismatch | Datafile khác endian với target | RMAN CONVERT sang platform target |
| Data Pump báo version incompatibility | Dump metadata không tương thích target | Kiểm tra source/target release, VERSION và Data Pump compatibility |
| ORA-01122 / ORA-01110 khi attach datafile | Datafile header/metadata không khớp hoặc file không hợp lệ | Kiểm tra đúng file, conversion, DBID/incarnation và trạng thái datafile |
| ORA-01119 / ORA-270xx | Target không tạo/đọc được file do path, permission hoặc storage | Kiểm tra filesystem/ASM, quyền và dung lượng |
| ORA-01536 quota exceeded | Schema owner không đủ quota ở target | Điều chỉnh quota theo chính sách |
| ORA-01031 insufficient privileges | User chạy Data Pump/DDL thiếu quyền | Cấp quyền đúng hoặc chạy bằng account quản trị phù hợp |
| Object invalid sau import | Dependency, user/grant hoặc version khác | Kiểm tra dependency, compile và grants |
| Encrypted tablespace không mở được | Target thiếu TDE key/keystore chưa mở | Chuẩn bị và import key theo TDE procedure |
| TSTZ data gặp vấn đề | Time zone file version không tương thích | Kiểm tra V$TIMEZONE_FILE và DBMS_DST |
| Thiếu datafile | Chưa copy toàn bộ datafile của transport set | Đối chiếu DBA_DATA_FILES và TRANSPORT_DATAFILES |
| Target attach file nhưng không thấy object | Metadata dump thiếu hoặc import sai PDB/schema | Kiểm tra log expdp/impdp, service và dump file |
| Downtime dài | Copy full datafile diễn ra trong READ ONLY window | Đánh giá XTTS/incremental transportable hoặc tăng throughput |

Mã lỗi chính xác phụ thuộc release và thao tác. Luôn đọc Data Pump log, alert log và error stack đầy đủ.

## 15. Quy trình lựa chọn phương pháp di chuyển

~~~text
Chỉ chuyển một số tablespace lớn?
        |
        +-- YES --> Kiểm tra self-contained và compatibility
        |               |
        |               +-- Đạt --> Transportable Tablespaces
        |               |
        |               +-- Không đạt --> conventional Data Pump
        |
        +-- NO --> Chuyển gần toàn database?
                        |
                        +-- YES --> Full transportable compatibility?
                        |               |
                        |               +-- Đạt --> Full transportable
                        |               |
                        |               +-- Không đạt --> Full Data Pump / upgrade path khác
                        |
                        +-- NO --> Chuyển schema/table, lọc dữ liệu?
                                        |
                                        +--> Conventional Data Pump
~~~

Nếu chỉ chuyển nguyên PDB, đánh giá unplug/plug hoặc clone PDB trước khi chọn TTS. Nếu downtime copy datafile quá dài, đánh giá incremental XTTS.

## 16. Checklist trước khi cutover

1. **Đúng phạm vi chưa?** TTS cho nhóm tablespace; full transportable cho gần toàn database.
2. **Transport set self-contained chưa?** DBMS_TTS.TRANSPORT_SET_CHECK không còn violation.
3. **Đã chọn đủ partition/index tablespace chưa?** Không để dependency quan trọng ở ngoài set.
4. **Source và target version tương thích chưa?** Kiểm tra release, Data Pump version và COMPATIBLE.
5. **Platform/endian đã xác nhận chưa?** Dùng V$TRANSPORTABLE_PLATFORM.
6. **Đã convert nếu khác endian chưa?** RMAN CONVERT, không dùng OS byte-swap.
7. **Block size có hỗ trợ không?** Target có cache cho nonstandard block size.
8. **Character set tương thích chưa?** Không giả định copied datafile được Data Pump chuyển đổi.
9. **Timezone file version phù hợp chưa?** Đặc biệt với TIMESTAMP WITH TIME ZONE.
10. **TDE key đã sẵn sàng chưa?** Target mở được keystore và có key cần thiết.
11. **Datafile đã đủ chưa?** Copy mọi datafile của tất cả tablespace được chọn.
12. **Tablespace đã READ ONLY đúng thời điểm chưa?** Snapshot không bị thay đổi trong lúc copy.
13. **Dump file và directory đã sẵn sàng chưa?** Quyền, dung lượng và path hợp lệ.
14. **User, role, quota và grants đã được xử lý chưa?** Đặc biệt với TTS truyền thống.
15. **Import vào đúng database/PDB chưa?** Dùng đúng service.
16. **Datafile target name đúng chưa?** Kiểm tra filesystem/ASM/OMF.
17. **Target đã kiểm tra object/dependency chưa?** Invalid, constraints, indexes, synonyms, jobs.
18. **Đã đối chiếu dữ liệu chưa?** Row count và business invariants.
19. **Có kế hoạch rollback không?** Giữ source và backup cho đến khi target được chấp nhận.
20. **Đã có backup target sau cutover chưa?** Thiết lập backup policy mới.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Transportable tablespaces khác conventional Data Pump ở cách di chuyển row data như thế nào?

**Câu 2.** Transport set self-contained có ý nghĩa gì?

**Câu 3.** DBMS_TTS.TRANSPORT_SET_CHECK dùng để làm gì?

**Câu 4.** Vì sao cần đưa tablespace về READ ONLY trước khi copy datafile?

**Câu 5.** Dump file của transportable tablespace thường chứa gì?

**Câu 6.** Vì sao phải copy tất cả datafile của một tablespace?

**Câu 7.** V$TRANSPORTABLE_PLATFORM cung cấp thông tin gì?

**Câu 8.** Khi nào cần RMAN CONVERT?

**Câu 9.** Vì sao không được tự byte-swap datafile bằng script?

**Câu 10.** DB_RECOVERY_FILE_DEST hoặc ASM path có thay thế TRANSPORT_DATAFILES không?

**Câu 11.** Full transportable khác TTS thông thường như thế nào?

**Câu 12.** Vì sao SYSTEM và SYSAUX không được copy nguyên datafile sang target trong full transportable?

**Câu 13.** Vì sao full transportable vẫn cần dump file có thể lớn?

**Câu 14.** Vì sao phải kiểm tra database version và COMPATIBLE?

**Câu 15.** Vì sao character set không thể được giả định tự chuyển đổi khi copy datafile?

**Câu 16.** TDE keystore ảnh hưởng transportable tablespace encrypted ra sao?

**Câu 17.** Vì sao user, role, quota và grants cần được kiểm tra sau TTS?

**Câu 18.** Khi nào XTTS giúp giảm downtime?

**Câu 19.** Khi mục tiêu là di chuyển nguyên một PDB, phương pháp nào nên được đánh giá?

**Câu 20.** Vì sao cần đối chiếu business invariant chứ không chỉ so kích thước datafile?

<details>
<summary>Gợi ý đáp án</summary>

1. TTS copy datafile và import metadata; conventional Data Pump đọc/ghi dữ liệu qua dump file.
2. Các dependency cần thiết nằm trong transport set theo quy tắc Oracle.
3. Kiểm tra dependency và self-contained condition của tập tablespace.
4. Để datafile không thay đổi trong khi export metadata và copy.
5. Chủ yếu metadata của object/tablespace, không phải toàn bộ row data trong datafile.
6. Tablespace có thể gồm nhiều datafile; thiếu một file sẽ khiến set không đầy đủ.
7. Platform ID/name và endian format.
8. Khi source và target khác endian format.
9. Datafile có block/header/metadata nội bộ; conversion phải dùng RMAN hoặc phương pháp Oracle hỗ trợ.
10. Không. TRANSPORT_DATAFILES chỉ đường dẫn datafile đích; storage destination cần được cấu hình riêng.
11. Full transportable di chuyển gần toàn database, dùng datafile cho user tablespaces và Data Pump cho non-transportable tablespace data/metadata.
12. SYSTEM/SYSAUX là cấu trúc nội bộ của database đích và được target quản lý.
13. Dữ liệu nằm trong non-transportable tablespace vẫn được xuất vào dump file.
14. Metadata và feature phải được target hỗ trợ; COMPATIBLE ảnh hưởng định dạng/tính năng database.
15. Row data nằm trong datafile đã mã hóa theo database character set; không đi qua logical conversion như conventional Data Pump.
16. Target phải có key/keystore phù hợp để đọc datafile encrypted.
17. TTS truyền thống không tự động di chuyển toàn bộ cấu hình database/user/security và môi trường ứng dụng.
18. Khi tablespace lớn và thời gian copy full datafile trong READ ONLY window quá dài.
19. Unplug/plug hoặc clone PDB.
20. Kích thước file không chứng minh dữ liệu nghiệp vụ đầy đủ và nhất quán.

</details>

## 18. Tài liệu Oracle chính thức

1. [Oracle Database 19c Administrator's Guide — Transporting Tablespaces Between Databases](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/transporting-tablespaces-between-databases.html): quy trình TTS, self-contained set và transportable restrictions.
2. [Oracle Database 19c Database Utilities — Transportable Tablespaces](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): Data Pump transportable export.
3. [Oracle Database 19c Database Utilities — Oracle Data Pump Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-import-utility.html): TRANSPORT_DATAFILES và import metadata.
4. [Oracle Database 19c Backup and Recovery Reference — CONVERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/CONVERT.html): RMAN cross-platform conversion.
5. [Oracle Database 19c Reference — V$TRANSPORTABLE_PLATFORM](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSPORTABLE_PLATFORM.html): platform và endian format.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_TTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_TTS.html): kiểm tra transport set.
7. [Oracle Database 19c Database Utilities — Full Transportable Export/Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-overview.html): full transportable và Data Pump.
8. [Oracle Database 19c Security Guide — Transparent Data Encryption](https://docs.oracle.com/en/database/oracle/oracle-database/19/asoag/): TDE keystore và encrypted tablespaces.
9. [Oracle Database 19c Upgrade Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/upgrd/): version compatibility và database upgrade path.

**Nguyên tắc cần nhớ:** TTS vận chuyển metadata bằng Data Pump và dữ liệu bằng datafile; full transportable kết hợp phương pháp này với full Data Pump cho phần không thể transport. Trước khi di chuyển phải kiểm tra transport set tự chứa, READ ONLY consistency, version, platform/endian, block size, character set, timezone và TDE. Khác endian phải dùng RMAN conversion. Sau import, kiểm tra object, dependency, quyền, dữ liệu nghiệp vụ và backup target trước khi cutover.
