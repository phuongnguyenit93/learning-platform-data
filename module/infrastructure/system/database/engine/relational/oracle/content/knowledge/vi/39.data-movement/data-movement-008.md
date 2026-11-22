# Parallel, compression, encryption và kiểm tra điều kiện sử dụng trong Oracle Data Pump

Oracle Data Pump Export và Import (expdp/impdp) thường được dùng để sao lưu logic, chuyển schema, di chuyển dữ liệu giữa database hoặc chuẩn bị một đợt nâng cấp. Với dữ liệu lớn, ba nhóm tham số có ảnh hưởng trực tiếp đến thời gian, dung lượng và an toàn của dump file là:

- **PARALLEL:** điều khiển số worker/process hoạt động đồng thời cho một Data Pump job.
- **COMPRESSION:** quyết định phần metadata và/hoặc table data được nén khi export; COMPRESSION_ALGORITHM chọn thuật toán nén.
- **ENCRYPTION:** mã hóa nội dung dump file; ENCRYPTION_MODE quyết định dùng password, wallet/keystore hay cả hai.

Các tham số này không phải lúc nào cũng dùng được trên mọi edition hoặc mọi license. Một cấu hình chạy được về mặt kỹ thuật chưa chứng minh tổ chức có quyền sử dụng tính năng đó. Trước khi lập lịch export/import, cần xác nhận edition, option license, COMPATIBLE, khả năng lưu trữ, CPU, memory, I/O, wallet và phương thức chuyển dump file.

Bài học lấy Oracle Database 19c làm mốc. Nội dung giải thích cơ chế song song, lựa chọn compression, các chế độ mã hóa, điều kiện sử dụng, ví dụ expdp/impdp, cách đo hiệu năng và checklist trước khi chạy migration.

## 1. Vai trò của Data Pump trong nhập xuất và di chuyển

### 1.1. Export tạo dump file set

Data Pump Export dùng lệnh expdp để đọc dữ liệu và metadata từ database, sau đó ghi ra một hoặc nhiều dump file. Dump file set là định dạng nhị phân riêng của Oracle, có thể chứa:
- Table data.
- Metadata của schema/object.
- Thông tin điều khiển cần thiết cho Import.

Dump file được ghi bởi database server vào vị trí được khai báo qua DIRECTORY object. Client expdp không tự ghi file dump trên máy chạy client nếu DIRECTORY trỏ tới một đường dẫn server khác.

### 1.2. Import nạp dump file hoặc đọc trực tiếp database nguồn

Data Pump Import dùng impdp để nạp dump file set vào database đích. Ngoài import từ file, có thể dùng NETWORK_LINK để đọc dữ liệu trực tiếp từ database nguồn qua database link.

Import có thể lọc hoặc biến đổi metadata/data bằng các tham số như:
- SCHEMAS, TABLES, FULL, TABLESPACES.
- INCLUDE, EXCLUDE, CONTENT, QUERY.
- REMAP_SCHEMA, REMAP_TABLESPACE, REMAP_TABLE, TRANSFORM.
- TABLE_EXISTS_ACTION.

PARALLEL, COMPRESSION và ENCRYPTION không thay thế các tham số chọn phạm vi dữ liệu. Chúng kiểm soát cách job xử lý, kích thước dump file và bảo vệ dump file.

### 1.3. Các giai đoạn cần phân biệt

~~~text
Database nguồn
     |
     | expdp
     v
Đọc metadata và table data
     |
     | PARALLEL: chia việc cho worker
     | COMPRESSION: nén nội dung dump
     | ENCRYPTION: mã hóa dump file
     v
Dump file set + log file
     |
     | chuyển file an toàn tới đích
     v
Dump file set tại môi trường đích
     |
     | impdp
     v
Đọc/giải mã/giải nén và tạo object, nạp dữ liệu
     |
     v
Database đích + validation
~~~

Parallelism, compression và encryption có thể cùng tham gia một export job. Chúng làm tăng hoặc giảm các loại tài nguyên khác nhau, nên cần kiểm thử phối hợp chứ không chọn từng tham số một cách độc lập.

## 2. Kiểm tra điều kiện sử dụng trước khi cấu hình

### 2.1. Xác định edition

Data Pump parallel export/import là tính năng của Enterprise Edition. Trong Standard Edition 2, Data Pump PARALLEL bị giới hạn ở degree 1; không thể dùng nó để chạy nhiều worker song song.

Có thể kiểm tra thông tin database:

~~~sql
SELECT banner
FROM   v$version
ORDER  BY banner;
~~~

Hoặc xem edition trong view phù hợp với quyền quản trị của môi trường. Không suy ra edition chỉ từ tên Oracle home hoặc từ việc một tham số được parser chấp nhận.

### 2.2. Kiểm tra COMPATIBLE

Một số tùy chọn compression/encryption có yêu cầu mức COMPATIBLE tối thiểu. Kiểm tra:

~~~sql
SHOW PARAMETER compatible;
~~~

Với Oracle 19c, các tham số COMPRESSION_ALGORITHM và nhiều tùy chọn ENCRYPTION yêu cầu COMPATIBLE ở mức tương thích được tài liệu 19c quy định, thường từ 11.0.0 hoặc 12.0.0 tùy tham số. Hãy kiểm tra đúng tham số thay vì áp một ngưỡng duy nhất cho tất cả.

### 2.3. Xác nhận license riêng của từng tính năng

Các điều kiện chính trong Oracle Database 19c:

| Tính năng | Điều kiện edition/option cần kiểm tra | Ghi chú |
| --- | --- | --- |
| Data Pump PARALLEL | Enterprise Edition | Standard Edition 2 giới hạn PARALLEL = 1 |
| COMPRESSION=METADATA_ONLY | Không cần Advanced Compression | Đây là mặc định của Data Pump Export |
| COMPRESSION=ALL hoặc DATA_ONLY | Enterprise Edition và Oracle Advanced Compression | Nén cả table data trong dump |
| COMPRESSION_ALGORITHM | Oracle Advanced Compression; COMPATIBLE theo yêu cầu | Áp dụng cho các thuật toán dump compression |
| Data Pump dump-file encryption | Enterprise Edition và Oracle Advanced Security theo licensing/reference 19c | Cần xác nhận entitlement theo hợp đồng |
| AES128/AES192/AES256 | Là thuật toán; không tự cấp quyền sử dụng encryption feature | Phải có tham số encryption phù hợp |

Oracle Advanced Compression và Oracle Advanced Security là các option có điều kiện license riêng trong nhiều mô hình triển khai Enterprise Edition. Một số dịch vụ cloud/engineered offering có thể bao gồm quyền sử dụng option; hãy kiểm tra đúng offering và hợp đồng của hệ thống đích/nguồn.

Không dùng V$OPTION, việc tham số chạy thành công hoặc một lần export trước đây làm bằng chứng license. Kiểm tra Licensing Information User Manual và quyền sử dụng của tổ chức trước khi bật tính năng.

### 2.4. Phân biệt license với điều kiện kỹ thuật

Một tính năng có thể:
- Có trong binary nhưng không được license cho hệ thống.
- Có license nhưng chưa cấu hình wallet, directory hoặc storage.
- Được phép dùng ở nguồn nhưng đích có edition/option khác.
- Tạo dump file thành công nhưng import không thể giải mã hoặc thiếu option tương ứng.

Do đó, preflight cần kiểm tra cả quyền sử dụng và điều kiện kỹ thuật ở hai đầu.

## 3. PARALLEL — điều khiển worker của Data Pump

### 3.1. PARALLEL làm gì?

PARALLEL đặt giới hạn số process thực thi đồng thời cho Data Pump job. Data Pump có control process điều phối công việc và các worker thực hiện việc unload/load metadata, table data, index hoặc các tác vụ phù hợp.

Ví dụ:

~~~text
Data Pump control process
       |
       +---- Worker 1
       +---- Worker 2
       +---- Worker 3
       +---- Worker 4
~~~

Nếu job có đủ công việc độc lập, nhiều worker có thể xử lý các object hoặc partition cùng lúc. Nếu công việc có dependency tuần tự hoặc chỉ có một object không thể chia nhỏ theo cách phù hợp, tăng PARALLEL có thể không làm job nhanh hơn.

### 3.2. Cú pháp cơ bản

Export:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_%U.dmp \
  LOGFILE=app_export.log \
  SCHEMAS=APP \
  PARALLEL=4
~~~

Import:

~~~bash
impdp app_user@target_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_%U.dmp \
  LOGFILE=app_import.log \
  SCHEMAS=APP \
  PARALLEL=4
~~~

Ví dụ dùng dấu gạch chéo để minh họa cú pháp shell kiểu Unix. Trên Windows hoặc khi dùng parameter file, cách xuống dòng có thể khác. DIRECTORY là Oracle DIRECTORY object, không phải tùy ý một đường dẫn trên máy client.

### 3.3. PARALLEL mặc định và edition

Mặc định PARALLEL là 1. Để chạy nhiều worker, phải có edition và điều kiện license phù hợp. Oracle 19c xác định PARALLEL chỉ có hiệu lực đa worker trong Enterprise Edition; Standard Edition bị giới hạn ở 1.

Không dùng PARALLEL=8 trên Standard Edition với kỳ vọng có tám worker. Kiểm tra edition trước khi lập kế hoạch thời gian migration.

### 3.4. Chọn degree ban đầu

Một điểm bắt đầu thực nghiệm có thể là 2, 4 hoặc 8 worker tùy:
- Số CPU/vCPU thực sự được cấp.
- CPU headroom dành cho ứng dụng.
- Tốc độ đọc datafile.
- Tốc độ ghi dump file.
- Dung lượng PGA và memory tổng.
- Số lượng table/partition độc lập.
- Khả năng phân tán dump file trên storage.

Oracle khuyến nghị không đặt PARALLEL cao hơn nhiều so với khoảng hai lần số CPU cho mục tiêu throughput tối đa trong hướng dẫn Data Pump performance. Đây là gợi ý tuning, không phải công thức bảo đảm tối ưu. Trong production, mức thấp hơn có thể phù hợp để bảo vệ workload ứng dụng.

### 3.5. Tăng PARALLEL không đồng nghĩa tăng tốc tuyến tính

Khi tăng worker:
- CPU usage tăng.
- PGA/memory tiêu thụ tăng.
- Datafile và dumpfile I/O tăng.
- Storage queue có thể tăng.
- Nhiều worker có thể tranh chấp cùng một file hoặc segment.
- Các thao tác metadata có dependency vẫn phải chạy tuần tự.

Ví dụ PARALLEL=8 không bảo đảm job nhanh gấp tám lần PARALLEL=1. Nếu storage đã bão hòa, thêm worker có thể chỉ làm latency tăng.

### 3.6. Cần đủ dump file cho worker

Mỗi worker ghi hoặc đọc một dump file tại một thời điểm. Để khai thác parallelism, nên cung cấp đủ file hoặc dùng substitution variable như %U:

~~~bash
DUMPFILE=app_%U.dmp
PARALLEL=4
FILESIZE=20G
~~~

%U cho phép Data Pump tạo tên file theo số thứ tự. FILESIZE đặt giới hạn kích thước mỗi dump file; khi file đầy, Data Pump có thể dùng file tiếp theo theo cấu hình file set.

Nếu chỉ khai báo một file tĩnh mà không có pattern phù hợp, số worker có thể bị giới hạn bởi số file sẵn có hoặc job không tận dụng được I/O song song như mong đợi.

### 3.7. Phân tán file trên storage

Nếu có nhiều volume phù hợp, có thể khai báo nhiều DIRECTORY object hoặc dump file trên các vị trí khác nhau để phân phối I/O. Tác dụng phụ thuộc kiến trúc storage:
- Nhiều path trên cùng một volume logic không nhất thiết tạo thêm bandwidth.
- Dump file trên cùng thiết bị với datafile có thể tranh chấp đọc/ghi.
- Storage đã stripe có thể tự phân phối I/O tốt hơn.
- Trong RAC, vị trí dump file phải truy cập được từ node chạy worker.

Đo throughput và latency của từng volume trước khi quyết định phân tán.

### 3.8. Giới hạn parallelism theo loại công việc

Không phải mọi phần của Data Pump đều parallel được:
- Export transportable tablespace có khác biệt về cách unload data.
- Import metadata có dependency và một số object phải tạo tuần tự.
- Metadata import qua NETWORK_LINK có giới hạn parallel.
- Transportable tablespace metadata không được import song song theo các hạn chế trong tài liệu.
- Một số loại object như trigger, view, sequence, constraint, object grant và referential constraint có thể không được xử lý song song trong một số đường import.

Vì vậy, PARALLEL là mức tối đa cho job, không phải cam kết mọi object đều có worker riêng.

### 3.9. PARALLEL trong RAC

Trong RAC, Data Pump có thể dùng tài nguyên nhiều instance nếu cấu hình cho phép. Tham số CLUSTER mặc định có thể cho phép worker chạy trên các node khác. Có thể giới hạn job vào instance khởi chạy bằng:

~~~bash
CLUSTER=NO
~~~

Hoặc dùng SERVICE_NAME cùng CLUSTER để ràng buộc worker vào các instance của service phù hợp.

Khi dùng RAC, kiểm tra:
- DIRECTORY path có sẵn trên mọi node hay không.
- Dump file nằm trên shared filesystem/ASM/object storage phù hợp.
- Service và instance được phép chạy worker.
- CPU/storage của node nào đang chịu tải.
- Có cần CLUSTER=NO cho job nhỏ để tránh overhead phân tán không.

### 3.10. Thay đổi PARALLEL khi job đang chạy

Có thể attach vào job đang chạy:

~~~bash
expdp app_user@source_db ATTACH=APP_EXPORT_JOB
~~~

Trong interactive mode:

~~~text
Export> STATUS
Export> PARALLEL=2
Export> STATUS
Export> PARALLEL=6
~~~

Tăng số worker chỉ có tác dụng nếu đủ file, tài nguyên và công việc có thể chia song song. Khi giảm, worker đang làm task có thể hoàn tất phần việc hiện tại trước khi được đưa về trạng thái idle.

Không kill job chỉ vì muốn thay đổi degree. Dùng ATTACH/interactive command và hiểu khác biệt giữa STOP_JOB, KILL_JOB, EXIT_CLIENT và CONTINUE_CLIENT.

## 4. Theo dõi và đo hiệu năng parallel

### 4.1. Hiển thị tiến độ

Có thể yêu cầu Data Pump ghi thời gian và metrics vào log:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_%U.dmp \
  LOGFILE=app_export.log \
  SCHEMAS=APP \
  PARALLEL=4 \
  LOGTIME=ALL \
  METRICS=YES \
  STATUS=60
~~~

LOGTIME=ALL thêm timestamp cho message; METRICS=YES bổ sung thông tin object/elapsed trong log; STATUS đặt chu kỳ hiển thị trạng thái trong client.

### 4.2. Theo dõi Data Pump job

~~~sql
SELECT owner_name,
       job_name,
       operation,
       job_mode,
       state,
       degree,
       attached_sessions,
       datapump_sessions
FROM   dba_datapump_jobs
ORDER  BY owner_name, job_name;
~~~

View DBA_DATAPUMP_JOBS cho biết job Data Pump đang tồn tại và trạng thái. Tên/cột có thể khác tùy view và quyền; dùng DESC để kiểm tra khi cần.

### 4.3. Xem session gắn với job

~~~sql
SELECT owner_name,
       job_name,
       instance_id,
       session_type,
       saddr
FROM   dba_datapump_sessions
ORDER  BY owner_name, job_name, session_type;
~~~

Dùng thông tin này kết hợp V$SESSION để xác định worker và control session. Trong RAC, lưu ý INST_ID/INSTANCE_ID để không nhầm session giữa các node.

### 4.4. Theo dõi long operation

~~~sql
SELECT sid,
       serial#,
       opname,
       target,
       sofar,
       totalwork,
       units,
       elapsed_seconds,
       time_remaining
FROM   v$session_longops
WHERE  totalwork > 0
AND    sofar < totalwork
ORDER  BY elapsed_seconds DESC;
~~~

Không phải mọi Data Pump operation đều được biểu diễn thành một dòng longops đầy đủ. Dùng log và job status cùng với view này.

### 4.5. So sánh các mức parallel

Để tìm degree phù hợp, chạy thử trên dữ liệu đại diện:

| Lần chạy | PARALLEL | Elapsed | CPU | Read/write throughput | Dump size |
| --- | ---: | --- | --- | --- | --- |
| A | 1 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| B | 2 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| C | 4 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| D | 8 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |

Giữ cùng dữ liệu, mode, dump storage, compression, encryption và tải nền khi so sánh. Nếu thay đổi nhiều tham số cùng lúc, khó xác định nguyên nhân cải thiện hoặc suy giảm.

## 5. COMPRESSION — nén dump file khi export

### 5.1. COMPRESSION khác gì table compression?

Data Pump COMPRESSION nén nội dung được ghi vào dump file set. Nó nhằm giảm kích thước file và có thể giảm lượng byte truyền qua mạng.

Nó không tự thay đổi cấu hình nén của bảng trong database đích. Các tính năng như Basic Table Compression, Advanced Row Compression, SecureFiles compression và RMAN backup compression là các tính năng khác, có điều kiện và cách tính license riêng.

### 5.2. Các giá trị COMPRESSION

~~~text
COMPRESSION = ALL
COMPRESSION = DATA_ONLY
COMPRESSION = METADATA_ONLY
COMPRESSION = NONE
~~~

| Giá trị | Nội dung được nén | Ý nghĩa |
| --- | --- | --- |
| ALL | Metadata và table data | Nén toàn bộ nội dung export |
| DATA_ONLY | Table data | Metadata không được nén bởi lựa chọn này |
| METADATA_ONLY | Metadata | Giá trị mặc định |
| NONE | Không nén | Dump file không dùng Data Pump compression |

Mặc định của Data Pump Export là METADATA_ONLY. Nén metadata có thể dùng mà không cần Oracle Advanced Compression option. Nén table data bằng ALL hoặc DATA_ONLY cần Enterprise Edition và Oracle Advanced Compression theo tài liệu 19c.

### 5.3. Ví dụ nén metadata

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_meta_%U.dmp \
  LOGFILE=app_meta.log \
  SCHEMAS=APP \
  COMPRESSION=METADATA_ONLY
~~~

Đây là lựa chọn mặc định nếu không chỉ định COMPRESSION. Nó nén metadata trong dump file, không nén table data theo Data Pump compression.

### 5.4. Ví dụ nén cả data và metadata

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_all_%U.dmp \
  LOGFILE=app_all.log \
  SCHEMAS=APP \
  COMPRESSION=ALL \
  COMPRESSION_ALGORITHM=BASIC
~~~

COMPRESSION=ALL cần Oracle Advanced Compression option và Enterprise Edition. Xác nhận license trước khi chạy trên môi trường được cấp phép.

### 5.5. Ví dụ nén riêng table data

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_data_%U.dmp \
  LOGFILE=app_data.log \
  SCHEMAS=APP \
  COMPRESSION=DATA_ONLY \
  COMPRESSION_ALGORITHM=LOW
~~~

Metadata không được nén theo lựa chọn DATA_ONLY. Tùy mục tiêu migration, có thể muốn nén data để giảm dung lượng truyền, nhưng phải cân nhắc CPU của source.

### 5.6. COMPRESSION_ALGORITHM

Oracle Data Pump 19c hỗ trợ:

| Thuật toán | Đặc điểm | Khi cân nhắc |
| --- | --- | --- |
| BASIC | Cân bằng tỷ lệ nén và tốc độ; thuật toán tương thích cách dùng trước đây | Khi muốn lựa chọn mặc định |
| LOW | Ít ảnh hưởng throughput export, dùng CPU ít hơn | Khi CPU là tài nguyên giới hạn |
| MEDIUM | Cân bằng tỷ lệ nén và tốc độ, Oracle khuyến nghị thử cho workload phổ biến | Khi cần trade-off cân bằng |
| HIGH | Tỷ lệ nén thường cao hơn nhưng có thể dùng CPU nhiều hơn | Khi mạng chậm hoặc dung lượng truyền là giới hạn |

Mức nén thực tế phụ thuộc dữ liệu. Text lặp lại có thể nén tốt; dữ liệu đã nén, encrypted hoặc binary có thể không giảm nhiều.

### 5.7. Cú pháp và điều kiện thuật toán

~~~bash
COMPRESSION=DATA_ONLY
COMPRESSION_ALGORITHM=MEDIUM
~~~

COMPRESSION_ALGORITHM có giá trị BASIC, LOW, MEDIUM hoặc HIGH. Trong Oracle 19c, tính năng thuật toán này yêu cầu COMPATIBLE theo mức tài liệu quy định và Oracle Advanced Compression option.

Không nhầm:
- COMPRESSION chọn phạm vi nén.
- COMPRESSION_ALGORITHM chọn cách nén.
- COMPRESS trong DDL của bảng là thuộc tính lưu trữ khác.
- RMAN COMPRESS là tính năng backup khác.

### 5.8. Tác động hiệu năng

Nén dump có thể:
- Giảm số byte ghi vào storage.
- Giảm dung lượng file và thời gian truyền qua network.
- Giảm I/O nếu storage/network là bottleneck.
- Tăng CPU do phải nén khi export và giải nén khi import.
- Tăng thời gian nếu CPU đã bão hòa hoặc dữ liệu không nén được.

Khi CPU là bottleneck, LOW có thể phù hợp hơn HIGH. Khi network là bottleneck, HIGH có thể giảm byte truyền nhưng cần benchmark CPU. MEDIUM là điểm bắt đầu để thử, không phải lựa chọn tối ưu cố định.

### 5.9. Import dump đã nén

impdp tự xử lý định dạng dump file đã được nén bởi Data Pump. Theo hướng dẫn Oracle Data Pump Best Practices, việc import một dump file đã nén không yêu cầu license Advanced Compression chỉ để giải nén file. Điều kiện license liên quan tới thao tác export và tính năng nén dữ liệu được dùng.

### 5.10. Dữ liệu không nén được

Nếu dữ liệu đã được nén trước ở tầng ứng dụng hoặc có entropy cao, nén thêm có thể:
- Tốn CPU.
- Không giảm dung lượng đáng kể.
- Làm job chậm hơn.
- Tạo nhiều file nhưng tổng kích thước gần như không đổi.

Đo dump size thực tế trước khi chọn mức compression cho migration lớn.

## 6. ENCRYPTION — mã hóa dump file

### 6.1. Vì sao cần mã hóa dump?

Dump file có thể chứa toàn bộ dữ liệu nhạy cảm của schema/database. Khi dump được ghi vào thư mục trung gian, backup staging hoặc chuyển qua network, quyền truy cập filesystem đơn thuần có thể không đủ.

Data Pump encryption mã hóa nội dung dump file set để người không có khóa/password không thể đọc dữ liệu bằng cách mở file thông thường.

Mã hóa dump file khác với:
- TDE mã hóa datafile/tablespace/column trong database.
- TLS/native network encryption bảo vệ đường truyền.
- Mã hóa filesystem/object storage bảo vệ thiết bị lưu trữ.

Một hệ thống migration an toàn có thể cần kết hợp nhiều lớp.

### 6.2. Các mức ENCRYPTION

~~~text
ENCRYPTION = ALL
ENCRYPTION = DATA_ONLY
ENCRYPTION = METADATA_ONLY
ENCRYPTION = ENCRYPTED_COLUMNS_ONLY
ENCRYPTION = NONE
~~~

| Giá trị | Phần dump được mã hóa |
| --- | --- |
| ALL | Toàn bộ data và metadata |
| DATA_ONLY | Table data |
| METADATA_ONLY | Metadata |
| ENCRYPTED_COLUMNS_ONLY | Dữ liệu của các cột đã được mã hóa TDE theo điều kiện hỗ trợ |
| NONE | Không mã hóa dump |

Nếu chỉ cung cấp ENCRYPTION_PASSWORD mà không chỉ định ENCRYPTION, Oracle Data Pump 19c mặc định ENCRYPTION=ALL. Để tránh hiểu nhầm, nên chỉ định rõ mục tiêu mã hóa.

### 6.3. SecureFiles và mã hóa

Nếu export có SecureFiles và cần bảo đảm chúng được mã hóa trong dump, Oracle yêu cầu ENCRYPTION=ALL để mã hóa toàn bộ dump file set. Không giả định ENCRYPTED_COLUMNS_ONLY sẽ bảo vệ mọi dữ liệu LOB/SecureFiles.

### 6.4. ENCRYPTION_MODE

Oracle Data Pump hỗ trợ ba chế độ:

| Mode | Cơ chế | Dùng khi |
| --- | --- | --- |
| PASSWORD | Password do người vận hành cung cấp để mã hóa/giải mã dump | Chuyển file sang database/môi trường khác |
| TRANSPARENT | Dùng Oracle encryption wallet/keystore | Import trong môi trường có cùng khóa/wallet được quản lý |
| DUAL | Cho phép giải mã bằng wallet hoặc password | Cần import nội bộ bằng wallet và có khả năng phục hồi ngoài site bằng password |

Chọn mode tường minh để tránh phụ thuộc default dựa trên wallet đang mở hay đóng.

### 6.5. PASSWORD mode

Ví dụ export:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_secure_%U.dmp \
  LOGFILE=app_secure.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=PASSWORD \
  ENCRYPTION_PASSWORD \
  ENCRYPTION_PWD_PROMPT=YES
~~~

Cách nhập password phụ thuộc client và cú pháp sử dụng; với command-line client, ENCRYPTION_PWD_PROMPT=YES yêu cầu Data Pump hỏi password mà không echo giá trị ra màn hình.

Khi import, phải cung cấp cùng password:

~~~bash
impdp app_user@target_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_secure_%U.dmp \
  LOGFILE=app_secure_import.log \
  SCHEMAS=APP \
  ENCRYPTION_PWD_PROMPT=YES
~~~

Trong một số phiên bản/cú pháp, có thể dùng ENCRYPTION_PASSWORD trực tiếp. Không ghi password rõ vào parameter file được commit vào source control, script chia sẻ hoặc shell history.

### 6.6. TRANSPARENT mode

Transparent mode dựa vào Oracle encryption wallet/keystore đã được cấu hình và sẵn sàng. Ví dụ:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_transparent_%U.dmp \
  LOGFILE=app_transparent.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=TRANSPARENT
~~~

Không dùng ENCRYPTION_PASSWORD cùng TRANSPARENT mode; Oracle báo lỗi nếu tham số password được cung cấp trong chế độ này.

Khi import, wallet/keystore chứa khóa phù hợp phải sẵn sàng ở môi trường đích. Nếu file được chuyển sang một host/database khác mà không có khóa tương ứng, import sẽ không giải mã được.

### 6.7. DUAL mode

DUAL tạo dump có thể được giải mã bằng wallet hoặc password đã khai báo:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_dual_%U.dmp \
  LOGFILE=app_dual.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=DUAL \
  ENCRYPTION_PASSWORD \
  ENCRYPTION_PWD_PROMPT=YES \
  ENCRYPTION_ALGORITHM=AES256
~~~

Mode này hữu ích khi có thể import trong site bằng wallet nhưng vẫn cần khả năng import offsite bằng password. DUAL cần cả cơ chế khóa/wallet và password theo cấu hình Oracle.

### 6.8. ENCRYPTION_ALGORITHM

Oracle Database 19c hỗ trợ:
- AES128.
- AES192.
- AES256.

Mặc định là AES128. Tài liệu Oracle Advanced Security Guide khuyến nghị AES256 cho Data Pump export trong 19c.

Ví dụ:

~~~bash
ENCRYPTION=ALL
ENCRYPTION_MODE=PASSWORD
ENCRYPTION_ALGORITHM=AES256
ENCRYPTION_PASSWORD
ENCRYPTION_PWD_PROMPT=YES
~~~

ENCRYPTION_ALGORITHM cần đi cùng ENCRYPTION hoặc ENCRYPTION_PASSWORD. Không dùng nó với ENCRYPTED_COLUMNS_ONLY vì các cột đã có định dạng mã hóa riêng.

### 6.9. ENCRYPTED_COLUMNS_ONLY

Lựa chọn này dành cho các cột đã mã hóa TDE, không có nghĩa toàn bộ dump file được mã hóa. Theo điều kiện của Oracle:
- Cần TDE cho các cột liên quan.
- Cần ENCRYPTION_PASSWORD.
- Không dùng ENCRYPTION_MODE.
- Không dùng ENCRYPTION_ALGORITHM để gán thêm một lớp algorithm cho cột vốn đã mã hóa.

Nếu cần bảo vệ toàn bộ nội dung dump, dùng ENCRYPTION=ALL.

### 6.10. Import dump đã mã hóa

Import phải dùng cơ chế tương ứng với export:
- PASSWORD: cung cấp đúng password đã dùng khi export.
- TRANSPARENT: wallet/keystore phù hợp phải sẵn sàng.
- DUAL: có thể dùng wallet hoặc password theo cách dump được tạo.

Nếu dump có encrypted columns, thuộc tính mã hóa của cột ở source và target cần tương thích. Import có thể lỗi nếu định nghĩa encrypted column khác nhau.

### 6.11. Bảo vệ password và wallet

- Dùng prompt thay vì ghi password rõ trong command line khi có thể.
- Không commit password vào PARFILE, shell script hoặc source control.
- Chuyển password qua kênh bảo mật độc lập với dump file.
- Quản lý wallet/keystore backup, quyền truy cập và rotation.
- Không đặt dump file và file wallet cạnh nhau trong cùng thư mục mở quyền.
- Không gửi password cùng email/chat chứa link dump file.
- Hủy bản staging theo retention và quy trình secure deletion của tổ chức.

## 7. Điều kiện license và compatibility chi tiết

### 7.1. Parallel Data Pump

Oracle Database 19c Licensing Information liệt kê Parallel Data Pump Export/Import là tính năng Enterprise Edition. Trong Standard Edition 2, PARALLEL bị giới hạn ở 1.

Nếu nguồn và đích khác edition, kiểm tra từng phía. Ví dụ export từ EE và import vào SE2 có thể cần điều chỉnh job/đối tượng; không giữ PARALLEL lớn rồi kỳ vọng SE2 sử dụng.

### 7.2. Data Pump compression

Oracle Advanced Compression option bao gồm Data Pump Export Data Compression. Theo tài liệu:
- COMPRESSION=METADATA_ONLY không cần Advanced Compression.
- COMPRESSION=ALL hoặc DATA_ONLY cần Advanced Compression và Enterprise Edition.
- COMPRESSION_ALGORITHM yêu cầu Advanced Compression và COMPATIBLE phù hợp.
- Import dump file đã được nén không cần option chỉ để giải nén dump.

Advanced Compression là option riêng đối với nhiều mô hình EE, nhưng có thể được bao gồm trong một số offering cloud/engineered. Kiểm tra bảng permitted features và hợp đồng của đúng deployment.

### 7.3. Data Pump encryption

Oracle Database 19c Licensing Information liệt kê Data Pump Export File encryption trong Oracle Advanced Security. Các tham số encryption trong tài liệu Data Pump cũng có giới hạn edition và điều kiện sử dụng option. TDE/Transparent mode còn cần wallet/keystore và khóa.

Phân biệt:
- Điều kiện edition cho tính năng Data Pump.
- Quyền sử dụng Oracle Advanced Security.
- Điều kiện kỹ thuật của wallet/TDE.
- Khả năng import trên database đích.

Không giả định PASSWORD mode, TRANSPARENT mode hay DUAL mode được miễn license chỉ vì chúng khác nhau về cách quản lý khóa. Kiểm tra Licensing Information hiện hành cho offering đang dùng.

### 7.4. Các dịch vụ cloud có entitlement khác

Một số Oracle Cloud Database offering bao gồm option mà khách hàng on-premises phải mua riêng. Bảng license 19c có các cột cho BaseDB, ExaDB và các offering khác. Hãy kiểm tra đúng loại dịch vụ, BYOL hay license-included và RU đang chạy.

### 7.5. Ma trận kiểm tra trước khi chạy

| Câu hỏi | Nguồn xác nhận |
| --- | --- |
| Database là EE hay SE2? | V$VERSION, thông tin hợp đồng/edition |
| PARALLEL có được phép? | Oracle Licensing Information |
| Data compression có license? | Oracle Advanced Compression entitlement |
| Dump encryption có license? | Oracle Advanced Security entitlement |
| COMPATIBLE có đủ mức? | SHOW PARAMETER compatible |
| Wallet/keystore đã sẵn sàng? | TDE/keystore configuration |
| Target có giải mã được dump? | Kiểm tra wallet/password và test import |
| Dump file đủ chỗ? | Filesystem/object storage capacity |
| Worker có đủ file? | DUMPFILE pattern và số file |
| Tài nguyên có đủ? | CPU, PGA, I/O và workload baseline |

## 8. Kết hợp PARALLEL, COMPRESSION và ENCRYPTION

### 8.1. Một cấu hình cân bằng

Ví dụ export schema với 4 worker, nén toàn bộ dump bằng MEDIUM và mã hóa bằng password:

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  FILESIZE=20G \
  LOGFILE=app_migration.log \
  SCHEMAS=APP \
  PARALLEL=4 \
  COMPRESSION=ALL \
  COMPRESSION_ALGORITHM=MEDIUM \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=PASSWORD \
  ENCRYPTION_ALGORITHM=AES256 \
  ENCRYPTION_PWD_PROMPT=YES \
  LOGTIME=ALL \
  METRICS=YES \
  STATUS=60
~~~

Cấu hình này yêu cầu:
- Enterprise Edition.
- Oracle Advanced Compression cho nén data.
- Oracle Advanced Security cho dump encryption theo licensing.
- COMPATIBLE phù hợp.
- DIRECTORY object và dump storage đủ dung lượng.
- Password được nhập qua prompt và bảo vệ riêng.

Đây là ví dụ cấu hình, không phải mức PARALLEL hoặc compression được khuyến nghị cho mọi database.

### 8.2. Import tương ứng

~~~bash
impdp app_user@target_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  LOGFILE=app_import.log \
  SCHEMAS=APP \
  PARALLEL=4 \
  ENCRYPTION_PWD_PROMPT=YES \
  LOGTIME=ALL \
  METRICS=YES \
  STATUS=60
~~~

Import sẽ đọc, giải mã và giải nén theo metadata của dump file. Không cần chỉ định lại COMPRESSION_ALGORITHM để giải nén dump. Password phải khớp nếu export dùng PASSWORD mode.

Nếu dùng TRANSPARENT mode, cần wallet/keystore phù hợp và không cung cấp password. Nếu dùng DUAL, chọn wallet hoặc password theo quy trình đã thiết kế.

### 8.3. Khi CPU là giới hạn

Nếu export làm CPU database tăng cao:
- Giảm PARALLEL.
- Thử COMPRESSION_ALGORITHM=LOW nếu đã có license.
- Đánh giá có cần nén data hay chỉ metadata.
- Chạy vào khung giờ ít tải.
- Phân tán I/O nếu storage cho phép.

Không tăng worker để bù cho compression tốn CPU; cả hai đều có thể làm CPU pressure cao hơn.

### 8.4. Khi network là giới hạn

Nếu dump file cần truyền qua đường mạng chậm:
- COMPRESSION có thể giảm byte cần truyền.
- HIGH có thể cải thiện tỷ lệ nén nhưng dùng CPU nhiều hơn.
- AES encryption tăng thêm chi phí xử lý CPU.
- Dùng file set có kích thước phù hợp để truyền/retry.
- Kiểm tra băng thông, latency và checksum sau truyền.

Nếu network đã mã hóa bằng TLS, dump encryption vẫn bảo vệ file khi nằm trên storage trung gian. Hai lớp giải quyết hai rủi ro khác nhau.

### 8.5. Khi storage là giới hạn

Nếu dump write/read storage là bottleneck:
- Kiểm tra IOPS, throughput và latency.
- Tránh đặt dump file trên cùng volume đang chịu tải datafile nặng nếu có thể.
- Dùng PARALLEL vừa phải.
- Chọn số dump file và phân bố file phù hợp.
- Không tăng worker vượt khả năng storage.

### 8.6. Khi dump size là giới hạn

Nếu cần giảm dung lượng:
- So sánh METADATA_ONLY với ALL/DATA_ONLY.
- Đo tỷ lệ nén trên mẫu dữ liệu đại diện.
- Kiểm tra dữ liệu đã nén hoặc encrypted từ trước.
- Cân nhắc thời gian giải nén ở target.
- Đảm bảo option license cho compression data.

## 9. Tách biệt mã hóa dump, TDE và bảo vệ đường truyền

### 9.1. Dump-file encryption

ENCRYPTION bảo vệ nội dung dump file set. Người có file nhưng không có password hoặc wallet/keystore tương ứng không thể đọc dữ liệu qua Data Pump bình thường.

### 9.2. TDE at rest

TDE bảo vệ datafile/tablespace/column theo cấu hình database. Nó không tự động có nghĩa mọi dump file export đều được mã hóa bằng cùng cơ chế. Data Pump có tham số riêng cho encryption dump.

### 9.3. Network encryption

TLS hoặc native network encryption bảo vệ đường truyền giữa client/database hoặc giữa các endpoint theo cấu hình. Dump file encryption bảo vệ file đã lưu. Khi chuyển dump qua SFTP/object storage, dùng thêm kênh truyền an toàn và access policy.

### 9.4. Dump, log và SQL file

ENCRYPTION của Data Pump áp dụng dump file set. File log, SQLFILE, parfile và các file hỗ trợ khác không mặc nhiên được mã hóa cùng cách. Bảo vệ chúng bằng quyền filesystem, object storage policy, mã hóa volume và retention.

## 10. Kiểm tra kết quả export và import

### 10.1. Đọc log export

Kiểm tra:
- Job có hoàn tất thành công không.
- Số object và số hàng được export.
- Dump file được tạo đủ chưa.
- Có warning về encryption hoặc object bị skip không.
- Elapsed time và throughput.
- File size thực tế so với estimate.

Không chỉ nhìn process expdp đã kết thúc. Job có thể hoàn tất với warning hoặc object bị skip.

### 10.2. Xác nhận dump file set

Trên server/storage:
- Kiểm tra tất cả file trong pattern %U.
- Kiểm tra kích thước, timestamp và số lượng file.
- Kiểm tra file được chuyển đầy đủ tới target.
- Tạo/check checksum theo quy trình.
- Kiểm tra quyền đọc của database server tại target.

Không đổi tên file thiếu nhất quán nếu dump set có nhiều phần. Data Pump cần đủ các file để đọc toàn bộ job.

### 10.3. Kiểm tra import trước khi thực thi

Có thể tạo SQL preview bằng SQLFILE:

~~~bash
impdp app_user@target_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  SQLFILE=app_preview.sql \
  SCHEMAS=APP
~~~

SQLFILE ghi DDL mà Import dự kiến chạy theo bộ tham số, không nạp dữ liệu. Bảo vệ file này vì có thể chứa tên schema, object và DDL nhạy cảm. SQLFILE không phải bản preview đầy đủ mọi hành động runtime hay bằng chứng import chắc chắn thành công.

### 10.4. Kiểm tra sau import

- Đọc log và xác nhận job status.
- So sánh số lượng bảng, index, constraint và object.
- Kiểm tra invalid objects.
- Kiểm tra row counts cho bảng trọng yếu.
- Kiểm tra sequence/identity và grant.
- Kiểm tra trigger, synonym, database link và job.
- Chạy smoke test nghiệp vụ.
- Thu thập statistics theo chính sách target.
- Kiểm tra dữ liệu nhạy cảm có được bảo vệ ở target.

### 10.5. So sánh dữ liệu có kiểm soát

COUNT(*) chỉ là một phép kiểm tra cơ bản. Với bảng quan trọng, có thể so sánh:
- Row count.
- Min/max khóa.
- Tổng số theo partition hoặc nhóm.
- Hash/checksum trên tập cột phù hợp.
- Constraint violations.
- Mẫu nghiệp vụ đại diện.

Nếu nguồn tiếp tục ghi trong lúc export, dùng FLASHBACK_SCN/FLASHBACK_TIME hoặc một quy trình consistency phù hợp để xác định mốc dữ liệu. Parallel, compression và encryption không tự bảo đảm tính nhất quán giữa các bảng nếu workload nguồn thay đổi trong quá trình export.

## 11. Những tình huống cấu hình mẫu

### 11.1. Export schema nhỏ, ưu tiên đơn giản

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_small.dmp \
  LOGFILE=app_small.log \
  SCHEMAS=APP \
  COMPRESSION=METADATA_ONLY
~~~

Phù hợp khi không cần parallelism, không nén table data và không dùng dump encryption. Vẫn phải bảo vệ file theo chính sách dữ liệu.

### 11.2. Export lớn, EE có ACO

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_large_%U.dmp \
  FILESIZE=10G \
  LOGFILE=app_large.log \
  SCHEMAS=APP \
  PARALLEL=6 \
  COMPRESSION=ALL \
  COMPRESSION_ALGORITHM=MEDIUM \
  LOGTIME=ALL \
  METRICS=YES
~~~

Chỉ dùng khi có Enterprise Edition và Oracle Advanced Compression. Benchmark với PARALLEL=2/4/6/8 trên môi trường tương đương trước khi chọn production degree.

### 11.3. Export để chuyển qua site khác, dùng password encryption

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_offsite_%U.dmp \
  LOGFILE=app_offsite.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=PASSWORD \
  ENCRYPTION_ALGORITHM=AES256 \
  ENCRYPTION_PWD_PROMPT=YES
~~~

Password được trao đổi qua kênh độc lập. Người nhận cần password để import. Không gửi password cùng đường dẫn/file dump.

### 11.4. Export dùng wallet tại cùng hệ thống

~~~bash
expdp app_user@source_db \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_wallet_%U.dmp \
  LOGFILE=app_wallet.log \
  SCHEMAS=APP \
  ENCRYPTION=ALL \
  ENCRYPTION_MODE=TRANSPARENT \
  ENCRYPTION_ALGORITHM=AES256
~~~

Wallet/keystore cần sẵn sàng và có khóa cần thiết. Nếu chuyển sang host khác, phải có kế hoạch chuyển/khôi phục key an toàn.

### 11.5. Import từ EE sang SE2

Một số migration có thể export từ Enterprise Edition rồi import vào Standard Edition 2, nhưng cần:
- Đặt PARALLEL phù hợp với target (SE2 degree 1).
- Xác minh object/feature có tương thích edition không.
- Không dùng tính năng target không được license.
- Kiểm tra partition, option-specific object và dependency.
- Đánh giá import encryption theo edition/option và licensing rules.
- Kiểm tra performance với single worker.

## 12. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| PARALLEL không chạy nhiều worker | SE2 hoặc giới hạn edition/license | Xác nhận edition; SE2 giới hạn degree 1 |
| Worker không tăng theo PARALLEL | Thiếu dump file, ít task độc lập hoặc object dependency | Dùng %U, thêm file, xem job status |
| PARALLEL cao nhưng job không nhanh hơn | CPU/I/O/memory bão hòa | Giảm worker, đo storage/CPU và benchmark |
| Dump file không giảm dù compression HIGH | Dữ liệu đã nén/encrypted hoặc không có pattern lặp | Benchmark dữ liệu, thử NONE/LOW/MEDIUM |
| ORA lỗi do compression option | Thiếu ACO hoặc COMPATIBLE chưa đủ | Kiểm tra license và parameter |
| ENCRYPTION_PASSWORD bị từ chối | Dump dùng TRANSPARENT mode hoặc password sai | Kiểm tra mode, dùng wallet hoặc đúng password |
| Import không giải mã được | Wallet thiếu/đóng, password sai, key không có | Xác minh keystore/password và mode export |
| Dump file quá lớn | COMPRESSION=METADATA_ONLY hoặc nén không hiệu quả | Cân nhắc data compression nếu có ACO |
| CPU tăng mạnh | Parallel + compression + encryption cùng tiêu thụ CPU | Giảm PARALLEL, thử mức nén thấp hơn |
| Storage queue tăng | Quá nhiều worker cùng đọc/ghi | Giảm degree, phân tán file hợp lý |
| Import thiếu object | Object bị filter/skip hoặc dependency/privilege | Đọc log, kiểm tra INCLUDE/EXCLUDE và quyền |
| Dump file set thiếu file | File pattern/transfer không đầy đủ | Kiểm tra %U và checksum toàn bộ file set |

### 12.1. ORA-390xx và worker error

Data Pump có thể trả các lỗi ORA-390xx bao quanh lỗi gốc của worker. Đọc toàn bộ log để tìm ORA error đầu tiên và object đang xử lý. Không chỉ xử lý dòng lỗi cuối cùng.

### 12.2. Không đủ disk space

Kiểm tra:
- Dump directory free space.
- Số file và FILESIZE.
- Temporary space/workarea nếu import tạo index/sort.
- Tablespace target.
- FRA/archivelog nếu import sinh redo lớn.
- Dung lượng log file và auxiliary storage nếu có.

### 12.3. Job treo hoặc worker không hoạt động

Dùng STATUS, DBA_DATAPUMP_JOBS, DBA_DATAPUMP_SESSIONS và V$SESSION_LONGOPS. Xác định job đang chờ I/O, lock, worker, metadata dependency hay tài nguyên. Attach để kiểm tra trước khi STOP_JOB/KILL_JOB.

### 12.4. Encryption/password không khớp

Kiểm tra chính xác:
- ENCRYPTION_MODE ở export.
- Có password được dùng không.
- Wallet/keystore có mở không.
- AES algorithm.
- File dump có đủ các phần không.
- Tài khoản import có quyền truy cập DIRECTORY.
- Database đích có điều kiện licensing/feature phù hợp không.

Không thử đoán password bằng cách chạy import lặp liên tục; dùng quy trình secret management.

## 13. Quy trình benchmark chọn cấu hình

### 13.1. Chuẩn bị workload đại diện

Chọn một schema/table có:
- Kích thước gần production.
- Kiểu dữ liệu đại diện: text, number, date, LOB, encrypted columns.
- Phân bố dữ liệu thực tế.
- Số lượng partition/object tương tự.
- Storage và network gần môi trường đích.

### 13.2. Thiết lập baseline

Chạy export với:
- PARALLEL=1.
- COMPRESSION=METADATA_ONLY hoặc NONE theo mục tiêu.
- Không encryption nếu môi trường test và chính sách cho phép.

Ghi:
- Elapsed time.
- CPU time/CPU utilization.
- Read/write throughput.
- Dump size.
- Số worker.
- Warning/error.
- Import elapsed time.

### 13.3. Thử parallelism riêng

Chạy lần lượt PARALLEL=2, 4, 8. Giữ compression/encryption không đổi. Xem điểm nào throughput ngừng tăng hoặc workload ứng dụng bị ảnh hưởng.

### 13.4. Thử compression riêng

Giữ PARALLEL cố định, so sánh:
- METADATA_ONLY.
- ALL BASIC.
- ALL LOW.
- ALL MEDIUM.
- ALL HIGH.

Chỉ thử các mức cần license. Ghi dump size, CPU, elapsed và import time. Đừng chỉ chọn theo file nhỏ nhất.

### 13.5. Thử encryption riêng

Giữ PARALLEL/compression cố định, đo overhead của:
- PASSWORD.
- TRANSPARENT.
- DUAL nếu use case cần.
- AES128/AES256 theo security policy.

Đánh giá thời gian export/import và quy trình quản lý key. Security policy có thể yêu cầu AES256 dù AES128 chạy nhanh hơn; không hạ thuật toán chỉ để tối ưu tốc độ nếu không có phê duyệt.

### 13.6. Đánh giá end-to-end

Tổng thời gian migration gồm:
- Export.
- Transfer.
- Import.
- Index/constraint creation.
- Statistics gathering.
- Validation.
- Cutover.

Compression có thể làm export chậm hơn nhưng transfer nhanh hơn. Parallel có thể rút ngắn export nhưng làm import hoặc workload ứng dụng bị chậm. Chọn cấu hình theo end-to-end time và mức độ ảnh hưởng hệ thống.

## 14. Preflight checklist

### Edition và license

- [ ] Xác nhận Oracle Database edition ở nguồn và đích.
- [ ] Xác nhận PARALLEL có được phép; SE2 chỉ degree 1.
- [ ] Xác nhận Advanced Compression nếu nén table data/thuật toán.
- [ ] Xác nhận Advanced Security cho dump encryption.
- [ ] Kiểm tra entitlement cloud/engineered offering nếu có.
- [ ] Không dựa vào việc tham số chạy được để kết luận có license.

### Compatibility và encryption

- [ ] Kiểm tra COMPATIBLE.
- [ ] Chọn COMPRESSION và COMPRESSION_ALGORITHM phù hợp.
- [ ] Chọn ENCRYPTION scope và mode.
- [ ] Xác định password hay wallet/keystore.
- [ ] Xác nhận target có thể giải mã.
- [ ] Kiểm tra AES algorithm theo security policy.
- [ ] Bảo vệ password, wallet và file hỗ trợ.

### Tài nguyên

- [ ] Ước lượng dump size và free space.
- [ ] Có đủ dump file cho PARALLEL degree.
- [ ] Kiểm tra CPU, PGA, I/O và network.
- [ ] Phân bố dump file trên storage phù hợp.
- [ ] Xem xét RAC CLUSTER/SERVICE_NAME.
- [ ] Xác định thời gian maintenance và tải ứng dụng.

### Chạy và xác minh

- [ ] Ghi LOGFILE, LOGTIME và METRICS.
- [ ] Ghi JOB_NAME và STATUS interval.
- [ ] Xác nhận export hoàn tất và đủ file.
- [ ] Tạo checksum và chuyển file an toàn.
- [ ] Xem SQLFILE/preview khi cần.
- [ ] Import với đúng password/wallet.
- [ ] Đọc log và kiểm tra object/data.
- [ ] Chạy validation nghiệp vụ và ghi kết quả.

## 15. Bài thực hành

Thực hành trong database test, có dump directory riêng và dữ liệu không nhạy cảm. Chỉ thử tùy chọn yêu cầu license nếu môi trường đã được cấp quyền.

### Bài 1 — Export tuần tự

Export một schema với PARALLEL=1. Ghi elapsed, dump size và log.

### Bài 2 — So sánh PARALLEL

Lặp lại với degree 2 và 4 trên cùng dữ liệu. So sánh worker count, elapsed, CPU và I/O.

### Bài 3 — Dump file pattern

Dùng DUMPFILE=lab_%U.dmp, PARALLEL=4 và FILESIZE phù hợp. Xác nhận Data Pump tạo nhiều file.

### Bài 4 — PARALLEL trên Standard Edition

Nếu có môi trường SE2 được cấp phép, kiểm tra giới hạn PARALLEL=1 và so sánh với EE test. Không cố ép degree cao.

### Bài 5 — METADATA_ONLY

Export với COMPRESSION=METADATA_ONLY. Ghi dump size và xác nhận không nén table data theo Data Pump.

### Bài 6 — So sánh thuật toán nén

Trên môi trường có ACO, thử LOW, MEDIUM, HIGH và BASIC. So sánh CPU, elapsed, ratio và import time.

### Bài 7 — Không nén

Export COMPRESSION=NONE. So sánh kích thước và thời gian với metadata/data compression.

### Bài 8 — PASSWORD encryption

Export với ENCRYPTION=ALL và PASSWORD mode. Import bằng password được nhập qua prompt. Kiểm tra trường hợp password sai trong môi trường test.

### Bài 9 — TRANSPARENT encryption

Cấu hình wallet/keystore test, export transparent và import với wallet tương ứng. Thử import khi wallet không sẵn sàng để hiểu điều kiện lỗi.

### Bài 10 — DUAL mode

Tạo dump DUAL. Thử import bằng wallet và bằng password theo quy trình được Oracle hỗ trợ.

### Bài 11 — AES algorithm

So sánh AES128 và AES256 trên cùng schema test. Đo CPU/elapsed và xác nhận thuật toán phù hợp security policy.

### Bài 12 — Parallel kết hợp compression

Cố định một compression setting đã được cấp phép. Thử PARALLEL=1/2/4 và xác định điểm throughput bắt đầu bão hòa.

### Bài 13 — Parallel kết hợp encryption

Cố định AES algorithm và mode. Đo tác động khi tăng worker; kiểm tra CPU có trở thành bottleneck không.

### Bài 14 — Lập kế hoạch migration

Viết parameter file export/import cho một schema test, nêu edition, license, COMPATIBLE, số worker, số dump file, compression, encryption, key handoff, storage và validation plan.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database 19c Utilities — Oracle Data Pump Overview](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-overview.html): kiến trúc Data Pump, worker và điều phối job.
- [Oracle Database 19c Utilities — Oracle Data Pump Performance](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-performance-tips.html): PARALLEL, resource consumption, compression/encryption overhead và tuning.
- [Oracle Database 19c Utilities — Data Pump Export](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-data-pump-export-utility.html): tham số PARALLEL, COMPRESSION, COMPRESSION_ALGORITHM và ENCRYPTION.
- [Oracle Database 19c Utilities — Data Pump Import](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/datapump-import-utility.html): import dump file, PARALLEL và ENCRYPTION_PASSWORD.
- [Oracle Database 19c Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html): edition, Oracle Advanced Compression, Oracle Advanced Security và Parallel Data Pump licensing.
- [Oracle Database 19c Advanced Security Guide — Using TDE with Other Oracle Features](https://docs.oracle.com/en/database/oracle/oracle-database/19/asoag/using-transparent-data-encryption-with-other-oracle-features.html): Data Pump encryption modes và thuật toán AES.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_DATAPUMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_DATAPUMP.html): API Data Pump và các tham số job.

PARALLEL quyết định mức đồng thời của worker và chỉ khai thác được khi edition, số file, loại object và tài nguyên cho phép. COMPRESSION giảm kích thước dump nhưng có thể tăng CPU; METADATA_ONLY không cần Advanced Compression, trong khi nén table data cần option tương ứng. ENCRYPTION bảo vệ dump file bằng password, wallet hoặc cả hai; cần quản lý khóa và xác nhận Oracle Advanced Security entitlement. **Trước khi chạy migration, hãy kiểm tra edition/license/COMPATIBLE, benchmark trên dữ liệu đại diện, bảo vệ dump và khóa, rồi xác minh đầy đủ kết quả import.**
