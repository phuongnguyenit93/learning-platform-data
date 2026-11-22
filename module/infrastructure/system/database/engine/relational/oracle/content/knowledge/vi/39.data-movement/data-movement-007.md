# Consistent export bằng FLASHBACK_SCN/FLASHBACK_TIME

Khi export database bằng Oracle Data Pump, dữ liệu nguồn có thể tiếp tục thay đổi trong lúc job đang chạy. Nếu không xác định một mốc snapshot chung, các bảng có thể được đọc ở những thời điểm khác nhau. Khi dữ liệu liên quan được cập nhật đồng thời, dump file có thể chứa các trạng thái không cùng một thời điểm nghiệp vụ.

Data Pump Export cung cấp hai tham số để yêu cầu đọc dữ liệu theo một mốc lịch sử:

- **FLASHBACK_SCN:** export dữ liệu theo một System Change Number cụ thể.
- **FLASHBACK_TIME:** export dữ liệu theo một timestamp; Data Pump xác định SCN tương ứng để dùng làm mốc flashback.

Hai tham số này giúp tạo một export nhất quán về dữ liệu bảng tại cùng một snapshot, ngay cả khi ứng dụng vẫn tiếp tục INSERT, UPDATE hoặc DELETE trong lúc export.

Một nguyên tắc quan trọng: FLASHBACK_SCN và FLASHBACK_TIME không thay thế backup. Chúng tạo một ảnh chụp logic nhất quán cho Data Pump Export. Muốn phục hồi database vật lý sau media failure vẫn cần RMAN backup, archived redo log và quy trình recovery phù hợp.

## 1. Vì sao cần consistent export?

Giả sử ứng dụng quản lý đơn hàng có hai bảng:

- ORDERS: thông tin đơn hàng.
- ORDER_ITEMS: các dòng hàng của đơn.

Một transaction tạo đơn hàng có thể INSERT vào cả hai bảng rồi COMMIT:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (9001, 100, 'NEW');

INSERT INTO order_items (order_id, item_id, quantity)
VALUES (9001, 1, 2);

COMMIT;
~~~

Trong khi Data Pump export, ứng dụng vẫn hoạt động. Nếu export ORDERS trước khi transaction commit nhưng export ORDER_ITEMS sau khi commit, dump có thể không phản ánh cùng một thời điểm logic. Kết quả có thể là ORDER_ITEMS có hàng con nhưng ORDERS chưa có hàng cha, hoặc ngược lại, tùy thời điểm từng bảng được đọc và trạng thái transaction.

### 1.1 Read consistency ở cấp statement và consistency toàn job

Oracle cung cấp read consistency cho một câu SQL: câu lệnh nhìn thấy dữ liệu theo một snapshot nhất quán tại thời điểm bắt đầu statement.

Nhưng một Data Pump job có thể đọc nhiều bảng, nhiều partition và nhiều object bằng nhiều worker. Nếu không cố định một snapshot cho job, thời điểm đọc của từng phần dữ liệu có thể khác nhau.

Consistent export yêu cầu Data Pump dùng cùng một mốc SCN để đọc dữ liệu bảng:

~~~text
                   SCN = 123456789
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       ORDERS         ORDER_ITEMS    CUSTOMERS
          |              |              |
          +--------------+--------------+
                         |
                         v
                Consistent dump set
~~~

Các thay đổi đã commit trước hoặc tại mốc snapshot được nhìn thấy theo quy tắc SCN; thay đổi commit sau mốc đó không xuất hiện trong snapshot.

### 1.2 Ví dụ transaction xảy ra trong lúc export

Giả sử snapshot được chọn tại SCN 1000:

| Thời điểm | Sự kiện | Có trong export SCN 1000? |
|---|---|---|
| SCN 950 | INSERT khách hàng và COMMIT | Có |
| SCN 980 | UPDATE trạng thái đơn và COMMIT | Có |
| SCN 1010 | INSERT đơn hàng và COMMIT | Không |
| SCN 1020 | DELETE khách hàng và COMMIT | Không |
| SCN 1030 | UPDATE địa chỉ và COMMIT | Không |

Data Pump đọc theo SCN 1000, vì vậy dump thể hiện trạng thái dữ liệu tại mốc đó dù các transaction sau vẫn commit trong khi job chạy.

### 1.3 Consistent export không khóa toàn bộ ứng dụng

Flashback-based export sử dụng khả năng đọc phiên bản lịch sử của Oracle. Mục tiêu là giữ snapshot nhất quán mà không cần dừng mọi hoạt động DML trong suốt job.

Tuy nhiên:

- DDL đồng thời vẫn có thể ảnh hưởng export.
- UNDO phải còn đủ để dựng dữ liệu tại SCN đã chọn.
- Một số loại object hoặc nguồn dữ liệu không hỗ trợ cùng cơ chế snapshot.
- Các thay đổi ngoài database, như file external table, không tự động bị đóng băng theo SCN.

## 2. FLASHBACK_SCN là gì?

FLASHBACK_SCN là tham số của Data Pump Export chỉ định SCN mà tại đó dữ liệu cần được export.

Ví dụ:

~~~text
expdp app_user@PDB1 DIRECTORY=DP_DIR DUMPFILE=app_%U.dmp LOGFILE=app_export.log SCHEMAS=APP FLASHBACK_SCN=123456789
~~~

### 2.1 SCN là mốc logic của database

SCN (System Change Number) là số thứ tự logic Oracle sử dụng để xác định thứ tự thay đổi và snapshot. Nó phù hợp khi cần:

- Chụp snapshot chính xác trước một đợt export.
- Dùng cùng mốc cho nhiều export job.
- Ghi lại mốc dữ liệu trong runbook.
- Tương quan với log, transaction hoặc recovery.

### 2.2 Lấy SCN hiện tại

Có thể lấy SCN bằng DBMS_FLASHBACK:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS export_scn
FROM dual;
~~~

Hoặc xem current SCN trong V$DATABASE:

~~~sql
SELECT current_scn
FROM v$database;
~~~

DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER là cách trực tiếp để lấy một SCN hiện tại. Ghi lại giá trị trả về ngay trước khi bắt đầu Data Pump job.

### 2.3 Ghi nhận SCN cùng thông tin export

Nên lưu lại:

- Database name và DB_UNIQUE_NAME.
- PDB/service nguồn.
- SCN đã chọn.
- Timestamp lúc lấy SCN và timezone.
- Schema/table được export.
- Data Pump job name.
- Dump file và log file.
- Oracle version.
- Người thực hiện và change/incident ID.

SCN không có ý nghĩa độc lập nếu không biết nó thuộc database/incarnation nào.

## 3. FLASHBACK_TIME là gì?

FLASHBACK_TIME cho phép chỉ định thời điểm theo timestamp thay vì nhập SCN trực tiếp. Data Pump chuyển timestamp thành SCN tương ứng rồi sử dụng SCN đó cho export.

Ví dụ:

~~~text
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Khi chạy trong parfile, biểu thức timestamp được đặt trong dấu nháy kép bên ngoài và chuỗi format trong dấu nháy đơn.

### 3.1 Ví dụ parfile

Tạo file consistent_export.par:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=app_consistent_%U.dmp
LOGFILE=app_consistent.log
SCHEMAS=APP
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
PARALLEL=4
FILESIZE=10G
~~~

Chạy:

~~~text
expdp app_user@PDB1 PARFILE=consistent_export.par
~~~

Không lưu password database dạng plaintext trong file parfile hoặc command history. Dùng cơ chế xác thực an toàn theo chuẩn môi trường, chẳng hạn prompt password, Oracle Wallet/secure external password store hoặc cơ chế được DBA phê duyệt.

### 3.2 Timestamp và timezone

Timestamp literal ở ví dụ không chứa timezone. Cần hiểu rõ database/session timezone và timezone mà người vận hành dùng để xác định thời điểm.

Nếu ứng dụng ghi log theo UTC nhưng DBA nhập giờ local, có thể chọn sai snapshot. Nên:

- Chuẩn hóa mốc thời gian theo UTC hoặc quy ước chung.
- Ghi rõ timezone trong ticket/runbook.
- Lưu cả timestamp và SCN sau khi xác định.
- Ưu tiên FLASHBACK_SCN khi cần mốc logic chính xác và có thể lấy SCN trước.

### 3.3 FLASHBACK_TIME không phải thời điểm file bắt đầu ghi

FLASHBACK_TIME chọn snapshot dữ liệu, không có nghĩa Data Pump phải bắt đầu ghi dump đúng tại thời điểm đó. Export có thể bắt đầu sau đó và vẫn đọc dữ liệu theo SCN được xác định.

## 4. So sánh FLASHBACK_SCN và FLASHBACK_TIME

| Tiêu chí | FLASHBACK_SCN | FLASHBACK_TIME |
|---|---|---|
| Đầu vào | SCN số | Timestamp expression |
| Cách chọn snapshot | Trực tiếp theo SCN | Timestamp được ánh xạ sang SCN |
| Độ chính xác vận hành | Phù hợp mốc logic đã ghi nhận | Phụ thuộc mapping timestamp-SCN |
| Dễ dùng | Cần lấy/lưu SCN | Dễ đọc theo thời gian |
| Dùng nhiều job | Rất thuận tiện, truyền cùng SCN | Có thể dùng cùng timestamp nhưng nên ghi lại SCN đã xác định |
| Phù hợp | Migration/backup logic cần reproducibility | Export theo thời điểm nghiệp vụ |

Hai tham số này loại trừ nhau trong cùng một Data Pump Export job. Chỉ chọn một:

~~~text
FLASHBACK_SCN=123456789
~~~

hoặc:

~~~text
FLASHBACK_TIME="TO_TIMESTAMP('2026-11-14 10:00:00','YYYY-MM-DD HH24:MI:SS')"
~~~

Không khai báo cả hai trong cùng job.

## 5. Chọn SCN trước khi export

Để nhiều schema hoặc nhiều job có cùng snapshot, hãy lấy SCN một lần rồi dùng lại.

Ví dụ:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS export_scn
FROM dual;
~~~

Giả sử kết quả là 123456789. Ghi SCN vào change record và dùng cùng giá trị trong mọi job:

~~~text
expdp app_user@PDB1 parfile=app.par
expdp ref_user@PDB1 parfile=reference.par
~~~

Trong từng parfile:

~~~text
FLASHBACK_SCN=123456789
~~~

### 5.1 Vì sao phải dùng cùng SCN?

Nếu export APP lúc SCN 1000 và export REFERENCE lúc SCN 2000, hai dump không đại diện cùng một trạng thái database. Khi import cả hai, các quan hệ dữ liệu có thể không khớp nếu transaction đã thay đổi dữ liệu giữa hai mốc.

Dùng cùng SCN giúp các bảng được export trong các job khác nhau cùng nhìn một snapshot, với điều kiện:

- Cùng database nguồn và đúng database incarnation.
- SCN còn khả năng truy vấn bằng UNDO.
- Tất cả object cần thiết hỗ trợ flashback export.
- Không có giới hạn khác làm một phần dữ liệu không thể đọc tại SCN.

### 5.2 Nhiều job kéo dài cần giữ UNDO lâu hơn

Nếu job thứ nhất chạy xong nhưng job thứ hai bắt đầu muộn và vẫn dùng SCN cũ, Oracle phải dựng dữ liệu ở SCN cũ cho tới khi job thứ hai đọc xong. Undo cần thiết phải còn đủ trong toàn bộ khoảng thời gian đó.

Khi dùng chung SCN cho nhiều job, hãy tính tổng khoảng thời gian từ lúc lấy SCN tới khi job cuối cùng hoàn tất.

## 6. Ví dụ Data Pump Export theo schema

### 6.1 Lấy SCN

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS export_scn
FROM dual;
~~~

Giả sử SCN là 987654321.

### 6.2 Tạo parfile

~~~text
DIRECTORY=DP_DIR
DUMPFILE=app_full_%U.dmp
LOGFILE=app_full_consistent.log
SCHEMAS=APP
FLASHBACK_SCN=987654321
PARALLEL=4
FILESIZE=8G
METRICS=YES
LOGTIME=ALL
~~~

### 6.3 Chạy export

~~~text
expdp app_user@PDB1 PARFILE=app_export.par
~~~

### 6.4 Đọc log

Kiểm tra:

- Export job bắt đầu và kết thúc.
- Job đã dùng đúng schema/mode.
- Các table data được export thành công.
- Không có table bị skip hoặc lỗi.
- Dump file được tạo đủ pieces.
- Log ghi nhận tham số flashback như mong muốn.

Log file là bằng chứng vận hành quan trọng. Không chỉ dựa vào exit code hoặc thông báo job đã hoàn tất.

## 7. Ví dụ export theo table

Nếu chỉ cần một số bảng:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=orders_%U.dmp
LOGFILE=orders_consistent.log
TABLES=APP.ORDERS,APP.ORDER_ITEMS
FLASHBACK_SCN=987654321
PARALLEL=2
~~~

Các bảng được export theo cùng SCN. Điều này hữu ích khi cần di chuyển một nhóm bảng có quan hệ.

### 7.1 INCLUDE/EXCLUDE

Có thể dùng INCLUDE/EXCLUDE để chọn object metadata/data theo quy tắc Data Pump:

~~~text
SCHEMAS=APP
INCLUDE=TABLE:"IN ('ORDERS','ORDER_ITEMS','CUSTOMERS')"
FLASHBACK_SCN=987654321
~~~

Biểu thức INCLUDE/EXCLUDE có yêu cầu quoting riêng của shell và parfile. Với filter phức tạp, nên dùng parfile để tránh lỗi escape.

## 8. Ví dụ export toàn database

Data Pump có thể export toàn database bằng FULL=Y nếu user có quyền tương ứng:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=full_%U.dmp
LOGFILE=full_consistent.log
FULL=Y
FLASHBACK_SCN=987654321
PARALLEL=8
FILESIZE=16G
~~~

Chạy:

~~~text
expdp system@PDB1 PARFILE=full_export.par
~~~

Trong môi trường multitenant, cần xác định rõ đang export CDB hay PDB và dùng service/container phù hợp. FULL=Y trong PDB không đồng nghĩa export toàn bộ CDB.

## 9. FLASHBACK_SCN/FLASHBACK_TIME và Data Pump Import

FLASHBACK_SCN và FLASHBACK_TIME là tham số của Data Pump Export. Chúng quyết định snapshot dữ liệu ở nguồn khi dump được tạo.

Khi import:

~~~text
impdp app_user@TARGET PARFILE=app_import.par
~~~

Import đọc nội dung đã được ghi trong dump file. Không cần chỉ định lại SCN của database nguồn để tái tạo snapshot export.

### 9.1 Import không làm dữ liệu thành trạng thái hiện tại của source

Nếu dump được export tại SCN 1000, import sau vài giờ vẫn nạp dữ liệu của snapshot SCN 1000. Các transaction commit sau SCN đó không có trong dump.

### 9.2 Import vào schema khác

Có thể dùng REMAP_SCHEMA hoặc REMAP_TABLESPACE theo nhu cầu:

~~~text
REMAP_SCHEMA=APP:APP_TEST
REMAP_TABLESPACE=APP_DATA:APP_TEST_DATA
~~~

Các tham số remap không thay đổi snapshot SCN đã dùng khi export.

## 10. Quyền cần thiết

Để chạy Data Pump Export, user cần quyền phù hợp với export mode và object được chọn. Ngoài ra, sử dụng FLASHBACK_SCN/FLASHBACK_TIME cần quyền Flashback trên các bảng được export.

Các quyền thường được xem xét:

- Quyền sử dụng DIRECTORY object với READ và WRITE.
- Quyền SELECT trên các bảng/đối tượng được export theo mode.
- Quyền Data Pump phù hợp, ví dụ role DATAPUMP_EXP_FULL_DATABASE khi export vượt phạm vi schema của chính user.
- Quyền FLASHBACK trên các bảng liên quan hoặc FLASHBACK ANY TABLE nếu cần trên phạm vi rộng.

Ví dụ cấp quyền directory:

~~~sql
GRANT READ, WRITE ON DIRECTORY dp_dir TO app_user;
~~~

Ví dụ cấp FLASHBACK trên một bảng:

~~~sql
GRANT FLASHBACK ON app.orders TO export_user;
GRANT FLASHBACK ON app.order_items TO export_user;
~~~

Ví dụ quyền hệ thống phạm vi rộng:

~~~sql
GRANT FLASHBACK ANY TABLE TO export_user;
~~~

FLASHBACK ANY TABLE là quyền rộng. Chỉ cấp khi export scope cần thiết và theo chính sách least privilege. Ưu tiên object privilege nếu chỉ export một tập bảng xác định.

### 10.1 DIRECTORY là đường dẫn phía database server

DIRECTORY=DP_DIR tham chiếu Oracle DIRECTORY object:

~~~sql
CREATE OR REPLACE DIRECTORY dp_dir
AS '/u05/oracle/dpump';
~~~

Đường dẫn là filesystem trên database server, không phải thư mục hiện tại trên máy chạy SQL Developer hoặc terminal client.

### 10.2 Quyền OS

Oracle Database software owner cần quyền đọc/ghi thư mục vật lý. Grant READ/WRITE trên DIRECTORY không tự cấp quyền filesystem ở hệ điều hành.

### 10.3 Không dùng SYSDBA cho Data Pump thông thường

Chạy Data Pump bằng user quản trị có quyền phù hợp và theo quy trình tổ chức. Tránh dùng SYSDBA như một cách bỏ qua thiết kế quyền. Nếu phải dùng tài khoản đặc quyền trong tình huống cụ thể, cần hiểu yêu cầu kết nối và ghi nhận audit.

## 11. UNDO và khả năng giữ snapshot

Data Pump cần đọc dữ liệu tại SCN cũ trong khi database vẫn tiếp tục thay đổi. Oracle có thể phải dùng UNDO để tái tạo phiên bản row tại SCN đó.

Nếu export kéo dài, lượng UNDO cần giữ cũng kéo dài. Khi undo cần thiết bị tái sử dụng trước khi worker đọc xong, export có thể thất bại với lỗi snapshot too old, thường là ORA-01555.

### 11.1 UNDO_RETENTION

Kiểm tra:

~~~sql
SHOW PARAMETER undo_retention;
~~~

UNDO_RETENTION là mục tiêu thời gian giữ undo trong automatic undo management. Nó không phải cam kết tuyệt đối rằng mọi undo sẽ còn đủ nếu undo tablespace thiếu dung lượng.

### 11.2 Xem thống kê undo

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

Các cột có thể khác theo phiên bản. V$UNDOSTAT thường tổng hợp theo khoảng thời gian, hữu ích để xem query dài nhất, undo block usage và snapshot-too-old count.

### 11.3 Ước lượng retention

Thời gian giữ undo nên bao phủ:

~~~text
Snapshot age at job completion
  = time from choosing SCN
    to the last worker finishing its table data
~~~

Thực tế cần cộng thêm:

- Thời gian chuẩn bị và xếp lịch job.
- Thời gian chạy các export job song song/tuần tự.
- Thời gian retry nếu job lỗi.
- Biên an toàn cho workload peak.

Nếu dùng một SCN chung cho nhiều job, retention phải đủ tới khi job cuối cùng đọc xong.

### 11.4 Dung lượng undo

Kiểm tra undo tablespace:

~~~sql
SELECT tablespace_name,
       status,
       contents,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

Kiểm tra datafile:

~~~sql
SELECT tablespace_name,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_data_files
WHERE tablespace_name IN (
    SELECT tablespace_name
    FROM dba_tablespaces
    WHERE contents = 'UNDO'
);
~~~

Dung lượng cần dựa trên undo generation rate trong giờ cao điểm và thời gian snapshot phải được giữ.

### 11.5 RETENTION GUARANTEE

Undo tablespace có thể dùng RETENTION GUARANTEE để ưu tiên giữ undo trong retention. Tuy nhiên, nếu tablespace hết chỗ, DML có thể thất bại thay vì ghi đè undo còn cần giữ.

Không bật RETENTION GUARANTEE chỉ để một export job chạy thành công mà chưa đánh giá nguy cơ ảnh hưởng ứng dụng ghi dữ liệu.

## 12. ORA-01555 trong Data Pump Export

ORA-01555 xảy ra khi Oracle không còn đủ undo để dựng snapshot cần thiết cho query. Với Data Pump, lỗi có thể xảy ra ở một bảng lớn hoặc một worker chạy lâu.

Nguyên nhân thường gặp:

- Export duration dài.
- DML volume cao trong thời gian export.
- Undo tablespace nhỏ.
- UNDO_RETENTION thấp so với thời gian snapshot.
- Autoextend không đủ hoặc bị giới hạn.
- Nhiều export job cùng giữ snapshot cũ.

### 12.1 Hướng xử lý

1. Xác định bảng/worker lỗi trong Data Pump log.
2. Đo thời gian job và thời gian query dài.
3. Xem V$UNDOSTAT, undo tablespace và alert log.
4. Tăng dung lượng undo nếu có cơ sở.
5. Điều chỉnh UNDO_RETENTION phù hợp.
6. Chạy ở thời điểm ít DML hơn.
7. Giảm số job chạy đồng thời nếu undo contention/dung lượng là vấn đề.
8. Chạy lại với SCN mới sau khi chuẩn bị.

### 12.2 Không đổi SCN giữa các phần của cùng một logical export

Nếu một job lỗi và phải chạy lại, có thể chọn SCN mới cho toàn bộ logical export mới. Nhưng không nên export một số bảng ở SCN cũ và phần còn lại ở SCN mới rồi ghép dump thành một snapshot, trừ khi có thiết kế đối soát rõ ràng.

## 13. DDL trong lúc export

FLASHBACK_SCN/FLASHBACK_TIME tập trung tạo snapshot nhất quán cho dữ liệu. Chúng không biến mọi thay đổi cấu trúc database thành lịch sử schema có thể truy vấn tùy ý.

Trong lúc export, các thao tác DDL như:

- ALTER TABLE.
- DROP/RENAME TABLE.
- TRUNCATE.
- MOVE/SHRINK.
- Thay đổi partition.
- Thay đổi datatype/constraint.

có thể làm Data Pump gặp lỗi metadata hoặc không thể đọc object theo snapshot mong muốn.

### 13.1 Khuyến nghị

- Đóng băng DDL trên schema trong cửa sổ export.
- Ghi nhận deployment window.
- Không chạy migration đồng thời với export nếu không cần thiết.
- Nếu bắt buộc có DDL, chia thành các giai đoạn và kiểm thử.
- Đọc log để xác định object lỗi thay vì chỉ retry toàn job.

### 13.2 ORA-01466

ORA-01466 có thể xuất hiện khi định nghĩa object thay đổi trong khoảng flashback cần đọc. Nếu export thất bại vì DDL, tăng UNDO không giải quyết nguyên nhân gốc.

## 14. Parallelism và consistent snapshot

Data Pump có thể dùng nhiều worker thông qua PARALLEL. Khi cung cấp FLASHBACK_SCN, các worker cần đọc dữ liệu theo snapshot đã chỉ định.

Ví dụ:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=app_%U.dmp
LOGFILE=app.log
SCHEMAS=APP
FLASHBACK_SCN=987654321
PARALLEL=4
~~~

PARALLEL=4 có thể giúp export nhanh hơn nếu storage/CPU đủ khả năng. Tuy nhiên:

- Nhiều worker có thể làm tăng I/O và CPU.
- Các worker vẫn cần undo để dựng cùng snapshot.
- Một worker chạy lâu có thể kéo dài thời gian cần giữ undo.
- Parallelism không tự sửa lỗi DDL hoặc thiếu undo.

### 14.1 %U trong DUMPFILE

Khi PARALLEL lớn hơn 1 hoặc dump được chia nhiều file, dùng substitution variable như %U:

~~~text
DUMPFILE=app_%U.dmp
~~~

Oracle tạo các file dump có số thứ tự phù hợp. Cần bảo đảm đủ filesystem space và có thể ghi nhiều file đồng thời.

### 14.2 Không tăng PARALLEL vô hạn

Nếu storage đã đạt throughput tối đa, tăng worker có thể làm export chậm hơn và ảnh hưởng workload production. Benchmark với 1, 2, 4, 8 worker theo tải thật.

## 15. Nhiều export job dùng cùng một SCN

Một migration có thể cần export nhiều schema riêng biệt:

~~~text
SCN = 987654321

Job 1: APP
Job 2: CRM
Job 3: BILLING
Job 4: REFERENCE
~~~

Mọi parfile dùng cùng FLASHBACK_SCN=987654321.

### 15.1 Lợi ích

- Các schema có thể được import cùng nhau ở trạng thái logic nhất quán.
- Dễ ghi nhận mốc dữ liệu.
- Có thể chạy job độc lập theo năng lực storage.
- Có thể retry toàn bộ export theo một snapshot mới nếu snapshot cũ không còn undo.

### 15.2 Rủi ro

- Job cuối cùng có thể bắt đầu muộn, khiến SCN rất cũ.
- Undo phải đủ cho toàn bộ khoảng thời gian.
- Một số object có thể không hỗ trợ flashback export.
- Các thao tác ngoài database không được đồng bộ tự động.
- DDL phải được quản lý xuyên suốt toàn bộ job.

### 15.3 Một SCN cho mọi PDB?

SCN là mốc thuộc database/container context cụ thể. Với multitenant, cần xác định rõ export ở CDB hay PDB và dùng service/container đúng. Không lấy SCN từ một database rồi áp dụng sang database khác hoặc PDB khác mà không hiểu phạm vi và khả năng hỗ trợ.

## 16. Consistent export và Data Pump modes

Data Pump Export hỗ trợ nhiều mode:

- FULL.
- SCHEMAS.
- TABLES.
- TABLESPACES.

Có thể kết hợp mode phù hợp với FLASHBACK_SCN/FLASHBACK_TIME theo các giới hạn của release và object type.

### 16.1 Schema mode

~~~text
SCHEMAS=APP
FLASHBACK_SCN=987654321
~~~

Phù hợp export một schema ứng dụng.

### 16.2 Table mode

~~~text
TABLES=APP.ORDERS,APP.ORDER_ITEMS
FLASHBACK_SCN=987654321
~~~

Phù hợp export một nhóm bảng.

### 16.3 Full mode

~~~text
FULL=Y
FLASHBACK_SCN=987654321
~~~

Cần quyền Data Pump full export và phạm vi container phù hợp.

### 16.4 Transportable tablespaces

Transportable tablespace export có quy trình và điều kiện consistency riêng. Không giả định FLASHBACK_SCN/FLASHBACK_TIME có thể được dùng giống schema/table mode cho mọi transportable workflow. Kiểm tra tài liệu Data Pump của đúng release, đặc biệt các điều kiện self-contained tablespace set, read-only transition và metadata export.

## 17. Những đối tượng không được đóng băng chỉ bằng FLASHBACK_SCN

Flashback SCN áp dụng cho dữ liệu bảng mà Data Pump có thể đọc bằng cơ chế flashback. Nó không tự đồng bộ mọi tài nguyên ngoài database:

- File bên ngoài được external table tham chiếu.
- File BFILE hoặc nội dung lưu ở filesystem.
- Dữ liệu trong hệ thống khác qua DB link.
- Message queue hoặc event stream bên ngoài.
- File ứng dụng được tạo đồng thời.
- Trạng thái sequence hoặc side effect không mang tính transactional như row DML.

Đối với các đối tượng này, cần quy trình snapshot riêng hoặc đóng băng nguồn trong thời gian export.

### 17.1 Sequence

Sequence không hoạt động như một cột transactional trong bảng. Việc gọi NEXTVAL có thể tiến sequence dù transaction rollback. Không giả định mọi sequence value được export theo cùng snapshot semantics như table data.

Nếu cần đảm bảo sequence sau migration:

- Ghi nhận sequence metadata/current value theo quy trình.
- Kiểm tra sequence cache và concurrent NEXTVAL.
- Dừng hoặc điều phối ứng dụng cấp sequence trong cửa sổ cutover nếu cần.
- Đối soát giá trị sequence ở target trước khi mở ghi.

### 17.2 External table

External table đọc dữ liệu từ file ngoài database. FLASHBACK_SCN không chụp snapshot nội dung file. Nếu file thay đổi trong lúc export, cần snapshot/copy file riêng hoặc đóng băng nguồn.

### 17.3 Metadata và DDL

Flashback SCN không phải hệ thống version hóa DDL. Giữ ổn định schema và metadata trong thời gian export.

## 18. FLASHBACK_TIME và chuyển timestamp sang SCN

Có thể dùng TIMESTAMP_TO_SCN để tìm SCN gần tương ứng:

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP('2026-11-14 10:00:00',
                        'YYYY-MM-DD HH24:MI:SS')
       ) AS flashback_scn
FROM dual;
~~~

Sau đó có thể truyền SCN đó vào parfile:

~~~text
FLASHBACK_SCN=987654321
~~~

Timestamp-to-SCN mapping chỉ có trong phạm vi metadata Oracle còn giữ và có tính chất xấp xỉ. Nếu timestamp quá cũ, mapping có thể không còn.

### 18.1 Dùng SCN sau khi đã chọn FLASHBACK_TIME

Khi cần tái lập export, ghi lại SCN thực tế được dùng. Timestamp ban đầu là thông tin nghiệp vụ; SCN là mốc kỹ thuật tốt hơn để tái sử dụng.

### 18.2 Không nhầm SCN lấy sau export

Nếu lấy SCN sau khi export hoàn tất, đó không phải snapshot SCN của dump. Lấy SCN trước khi chạy job và truyền rõ vào Data Pump.

## 19. Kiểm tra dữ liệu sau export

Data Pump log cần được kiểm tra cẩn thận:

- Job hoàn tất thành công.
- Không có table data bị skip.
- Không có lỗi ORA-/UDE- đáng chú ý.
- Số hàng được export hợp lý.
- Dump pieces đủ và có thể đọc.
- Log ghi đúng SCN hoặc timestamp đã cấu hình.

### 19.1 Row count

Không so sánh số hàng dump với số hàng hiện tại ở source nếu source tiếp tục thay đổi sau SCN. Hãy so sánh với snapshot cùng SCN:

~~~sql
SELECT COUNT(*)
FROM app.orders AS OF SCN 987654321;
~~~

Đối chiếu với số hàng trong Data Pump log hoặc sau import vào môi trường test. Với table lớn, việc đếm có thể tốn thời gian.

### 19.2 Kiểm tra dump set

Có thể dùng Data Pump Import ở chế độ SQLFILE để xem DDL mà không thực thi:

~~~text
impdp app_user@TARGET DIRECTORY=DP_DIR DUMPFILE=app_consistent_%U.dmp SQLFILE=app_ddl_review.sql
~~~

SQLFILE giúp kiểm tra metadata DDL; nó không xác minh đầy đủ table data.

### 19.3 Import thử vào schema riêng

Nên import dump vào môi trường kiểm thử hoặc schema đích cô lập:

~~~text
impdp app_user@TEST PARFILE=app_test_import.par
~~~

Kiểm tra:

- Bảng và constraint.
- Row count.
- Foreign key relationships.
- Index và trigger.
- Sequence state.
- Stored procedures/packages.
- Data integrity theo nghiệp vụ.

## 20. Data Pump log và job monitoring

Data Pump tạo master table và worker process để điều phối job. Có thể theo dõi job đang chạy qua các view:

- DBA_DATAPUMP_JOBS.
- DBA_DATAPUMP_SESSIONS.
- V$SESSION_LONGOPS.

Ví dụ:

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

Theo dõi long operations:

~~~sql
SELECT sid,
       serial#,
       opname,
       sofar,
       totalwork,
       units,
       elapsed_seconds,
       time_remaining
FROM v$session_longops
WHERE totalwork > 0
  AND sofar < totalwork
ORDER BY start_time;
~~~

Các view và cột cần quyền catalog/performance phù hợp. Không cấp quyền rộng cho user ứng dụng chỉ để giám sát một job.

## 21. Lỗi thường gặp

### ORA-01555: snapshot too old

Undo cần thiết để đọc dữ liệu tại SCN đã chọn không còn đủ.

Hướng xử lý:

- Xem Data Pump log để xác định object/worker lỗi.
- Kiểm tra V$UNDOSTAT và undo tablespace.
- Tăng dung lượng undo hoặc retention có cơ sở.
- Chạy ở thời điểm DML thấp hơn.
- Giảm thời gian tổng từ lúc lấy SCN tới khi job hoàn tất.
- Chọn SCN mới cho lần export mới.

### ORA-01466: unable to read data - table definition has changed

DDL thay đổi định nghĩa object trong khoảng cần flashback.

Hướng xử lý:

- Kiểm tra deployment/DDL log.
- Tạm dừng DDL trong cửa sổ export.
- Retry với schema ổn định và SCN phù hợp.
- Không chỉ tăng UNDO vì nguyên nhân là metadata/DDL.

### UDE-/ORA- lỗi quyền

Nguyên nhân có thể:

- Thiếu quyền FLASHBACK trên bảng.
- Thiếu quyền SELECT hoặc quyền Data Pump.
- DIRECTORY object chưa được cấp READ/WRITE.
- OS user không ghi được thư mục.

Kiểm tra privilege theo phạm vi export, không cấp DBA hoặc SELECT ANY DICTIONARY như giải pháp mặc định.

### Dump file không đủ hoặc hết dung lượng

Kiểm tra:

- Dung lượng filesystem/ASM.
- FILESIZE và DUMPFILE substitution.
- Quyền OS.
- Số lượng dump piece.
- Log cuối job.

### Timestamp không được chấp nhận

Kiểm tra:

- Cú pháp TO_TIMESTAMP.
- Dấu nháy trong parfile/shell.
- Format mask.
- Timezone.
- Timestamp-to-SCN mapping còn khả dụng.

## 22. Quy trình migration dùng consistent export

Một migration schema có thể tổ chức như sau:

### Giai đoạn 1: Chuẩn bị

1. Xác định source database/PDB và target.
2. Lập inventory schema, table, dependency và object ngoài database.
3. Kiểm tra Data Pump version compatibility.
4. Kiểm tra directory, filesystem, quota và dump capacity.
5. Xác nhận quyền FLASHBACK/Data Pump.
6. Đánh giá UNDO retention và dung lượng.
7. Xác định DDL freeze window.
8. Kiểm thử export/import với dữ liệu đại diện.

### Giai đoạn 2: Chọn snapshot

1. Chọn thời điểm nghiệp vụ.
2. Lấy SCN bằng DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER hoặc xác định timestamp.
3. Ghi SCN, timestamp, timezone và database identity.
4. Truyền cùng SCN cho tất cả export job cần một snapshot chung.

### Giai đoạn 3: Export

1. Chạy expdp bằng parfile.
2. Theo dõi worker, elapsed time và undo.
3. Không triển khai DDL trên schema trong cửa sổ export.
4. Kiểm tra log, dump pieces và lỗi.
5. Nếu job lỗi, xác định có thể restart/resume hay phải chạy lại snapshot.

### Giai đoạn 4: Import và đối soát

1. Chạy impdp vào target/schema test.
2. Kiểm tra metadata và object status.
3. So row count với source AS OF cùng SCN.
4. Kiểm tra quan hệ cha-con và constraint.
5. Kiểm tra sequence và external files riêng.
6. Chạy smoke test nghiệp vụ.

### Giai đoạn 5: Cutover

1. Chốt thay đổi mới phát sinh sau snapshot theo chiến lược migration.
2. Dừng/điều phối ghi dữ liệu nếu cần.
3. Đồng bộ delta sau snapshot bằng cơ chế riêng nếu yêu cầu.
4. Đối soát cuối.
5. Mở ứng dụng ghi tại target.

Consistent export chỉ bảo đảm snapshot tại SCN. Nếu source tiếp tục nhận giao dịch sau SCN, các giao dịch đó không có trong dump. Muốn cutover không mất giao dịch cần cơ chế delta replication/CDC hoặc cửa sổ dừng ghi được thiết kế riêng.

## 23. Consistent export không phải đồng bộ liên tục

Một dump tại SCN là snapshot tĩnh. Nó không tự nhận các thay đổi phát sinh sau khi snapshot được chọn.

Ví dụ:

~~~text
SCN 1000: chọn snapshot
SCN 1010: bắt đầu export
SCN 1050: export xong
SCN 1060: source tiếp tục có transaction mới
~~~

Dump phản ánh trạng thái tại SCN 1000, không phải trạng thái tại SCN 1050 hay 1060.

Nếu cần target theo kịp source:

- Dùng replication/CDC.
- Dùng Data Guard cho physical database replication.
- Dùng GoldenGate hoặc giải pháp logical replication phù hợp.
- Hoặc dừng ghi source, export snapshot cuối và cutover.

Chọn giải pháp theo RPO, RTO, downtime và loại dữ liệu.

## 24. Consistent export và application quiesce

Dù flashback export không bắt buộc dừng DML, vẫn có trường hợp nên quiesce ứng dụng:

- Cần snapshot nhất quán với file ngoài database.
- Cần sequence state đồng bộ với dữ liệu.
- Cần bảo đảm không có DDL.
- Cần cutover và không chấp nhận transaction mới sau mốc.
- Ứng dụng có side effect ngoài database.

Có thể chỉ dừng ghi (read-only mode ở tầng ứng dụng) thay vì dừng toàn bộ database. Điều quan trọng là xác định rõ ranh giới snapshot và giao dịch được phép sau mốc.

## 25. Consistent export và network link

Data Pump có thể export dữ liệu từ nguồn từ xa thông qua NETWORK_LINK trong một số workflow. Khi dùng network link:

- Xác định database nào là source thực sự.
- Quyền Flashback phải phù hợp ở nơi Data Pump thực hiện truy vấn nguồn.
- SCN phải thuộc database nguồn.
- Kiểm tra version compatibility và network stability.
- Kiểm tra các hạn chế của network export và flashback parameter trong release.

Không truyền SCN lấy từ target vào source hoặc ngược lại. SCN không phải timestamp toàn cục dùng chung giữa database độc lập.

## 26. Các tham số Data Pump hữu ích đi kèm

Ví dụ parfile:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=app_%U.dmp
LOGFILE=app_consistent.log
SCHEMAS=APP
FLASHBACK_SCN=987654321
PARALLEL=4
FILESIZE=8G
METRICS=YES
LOGTIME=ALL
STATUS=60
~~~

Ý nghĩa:

- DIRECTORY: Oracle DIRECTORY object.
- DUMPFILE: tên dump file; %U cho nhiều piece.
- LOGFILE: log export.
- SCHEMAS: schema cần export.
- FLASHBACK_SCN: snapshot SCN.
- PARALLEL: số worker mục tiêu.
- FILESIZE: giới hạn kích thước từng dump piece.
- METRICS: ghi metric object trong log.
- LOGTIME: ghi timestamp trong log.
- STATUS: chu kỳ hiển thị trạng thái job trong môi trường hỗ trợ.

Kiểm tra Data Pump parameter reference của phiên bản đang dùng. Một số tham số hoặc giá trị có thể thay đổi theo release.

## 27. Best practices

- Ưu tiên FLASHBACK_SCN nếu cần snapshot có thể ghi nhận và tái sử dụng.
- Dùng FLASHBACK_TIME khi mốc nghiệp vụ được xác định bằng thời gian.
- Ghi lại SCN thực tế, timestamp và timezone.
- Dùng cùng SCN cho mọi job thuộc một logical export.
- Đảm bảo UNDO đủ cho thời gian dài nhất từ lúc chọn SCN tới khi job cuối kết thúc.
- Theo dõi V$UNDOSTAT, alert log và Data Pump log.
- Tránh DDL trên schema trong thời gian export.
- Dùng parfile để giảm lỗi quoting và bảo vệ password.
- Không đưa password database vào command history hoặc file chia sẻ.
- Dùng DIRECTORY server-side có quyền filesystem tối thiểu.
- Kiểm tra mọi table/object bị skip hoặc lỗi.
- Import thử vào môi trường riêng trước cutover.
- Đối soát source bằng AS OF cùng SCN.
- Xử lý sequence, external files và side effect riêng.
- Không nhầm snapshot export với đồng bộ delta liên tục.

## 28. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Không dùng flashback parameter cho nhiều bảng liên quan | Bảng có thể được đọc ở các thời điểm khác nhau | Dùng một FLASHBACK_SCN/TIME |
| Khai báo cả FLASHBACK_SCN và FLASHBACK_TIME | Tham số loại trừ nhau | Chọn một |
| Lấy SCN sau khi export xong | SCN không đại diện snapshot của dump | Lấy trước khi chạy job |
| Dùng SCN khác nhau cho từng schema | Các dump không cùng trạng thái | Dùng cùng SCN |
| Chỉ tăng UNDO_RETENTION | Có thể vẫn thiếu dung lượng undo | Đo undo rate, tăng capacity và kiểm soát workload |
| Nghĩ UNDO_RETENTION là guarantee | ORA-01555 vẫn có thể xảy ra | Hiểu retention target và retention guarantee |
| Chạy DDL trong lúc export | Object metadata có thể thay đổi, export lỗi | DDL freeze window |
| Tăng PARALLEL vô hạn | I/O/CPU contention | Benchmark |
| Nghĩ dump phản ánh trạng thái lúc kết thúc | Dữ liệu sau SCN bị bỏ qua | Ghi rõ snapshot SCN |
| Dùng dump snapshot như CDC | Mất giao dịch sau snapshot | Có delta replication/cutover plan |
| So row count dump với source hiện tại | Source đã thay đổi sau SCN | So với AS OF cùng SCN |
| Bỏ qua sequence/external file | Target thiếu trạng thái ngoài row data | Đồng bộ riêng |
| Quên quyền FLASHBACK | Job lỗi khi đọc lịch sử | Cấp object/system privilege tối thiểu |
| Nghĩ DIRECTORY là local client folder | Dump file nằm sai nơi hoặc không ghi được | Xác định server-side path |
| Không đọc log | Bỏ sót table skip hoặc warning | Đối chiếu log, dump pieces và import test |

## 29. Bài thực hành tự kiểm tra

Thực hiện trong database lab hoặc môi trường được DBA cho phép.

### Bài 1 — Lấy SCN

Dùng DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER. Ghi SCN, timestamp, database name và PDB.

### Bài 2 — Export một schema

Tạo parfile có SCHEMAS và FLASHBACK_SCN. Chạy expdp và xác nhận log.

### Bài 3 — Dữ liệu thay đổi trong lúc export

Chạy một export dài trong lab, đồng thời cập nhật dữ liệu. Import dump và so sánh với source AS OF SCN đã chọn.

### Bài 4 — FLASHBACK_TIME

Chạy export theo timestamp expression. So sánh với SCN được ánh xạ bằng TIMESTAMP_TO_SCN.

### Bài 5 — Cùng SCN cho nhiều job

Export hai schema bằng hai job riêng nhưng cùng SCN. Import chung và kiểm tra quan hệ dữ liệu.

### Bài 6 — Thiếu undo

Trong lab, chạy export dài với undo capacity hạn chế. Quan sát khả năng xuất hiện ORA-01555 và đọc V$UNDOSTAT.

### Bài 7 — DDL trong lúc export

Thử DDL trên bảng đang export trong lab. Ghi nhận lỗi/ảnh hưởng và xây dựng DDL freeze window.

### Bài 8 — Parallelism

So sánh PARALLEL=1, 2 và 4 trong cùng workload. Đo elapsed, I/O và CPU.

### Bài 9 — Import test

Import dump vào schema khác bằng REMAP_SCHEMA. Kiểm tra row count và constraint.

### Bài 10 — External table

Export một schema có external table. Thay đổi file ngoài database và giải thích vì sao FLASHBACK_SCN không đóng băng nội dung file.

### Bài 11 — Sequence

Gọi NEXTVAL trong lúc export. Kiểm tra sequence ở target và thiết kế bước đồng bộ riêng.

### Bài 12 — Cutover

Thiết kế quy trình snapshot SCN, export, delta capture, freeze writes, final sync và cutover. Ghi RPO/downtime.

## 30. Checklist trước khi chạy production export

**Snapshot**

- Đã chọn SCN hay timestamp?
- Nếu dùng timestamp, timezone đã rõ?
- Đã ghi SCN thực tế?
- Nhiều job có dùng cùng SCN?
- SCN thuộc đúng source database/PDB?

**UNDO**

- Undo retention đủ cho job dài nhất?
- Undo tablespace có đủ dung lượng?
- Đã xem V$UNDOSTAT?
- Có peak DML hoặc batch trong cửa sổ export?
- Có kế hoạch xử lý ORA-01555?

**Object và DDL**

- Đã inventory table/object?
- Có external table hoặc dữ liệu ngoài database?
- Sequence state có cần đồng bộ riêng?
- DDL freeze window đã thống nhất?
- Có object không hỗ trợ flashback export?

**Data Pump**

- DIRECTORY object đúng?
- Quyền READ/WRITE và filesystem đúng?
- FLASHBACK privilege đủ?
- DUMPFILE %U, FILESIZE, PARALLEL phù hợp?
- Parfile không chứa password plaintext?
- Logfile được theo dõi?

**Import/cutover**

- Dump pieces đầy đủ?
- Log không có table bị skip/lỗi?
- Import test thành công?
- Row count đối chiếu cùng SCN?
- Constraint và dữ liệu quan hệ đúng?
- Có kế hoạch đồng bộ thay đổi sau snapshot?

## 31. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| Consistent export | Export table data theo cùng một snapshot |
| FLASHBACK_SCN | Chọn snapshot bằng SCN |
| FLASHBACK_TIME | Chọn snapshot bằng timestamp được ánh xạ sang SCN |
| SCN | Mốc logic của một database |
| DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER | Lấy SCN hiện tại |
| TIMESTAMP_TO_SCN | Ánh xạ timestamp sang SCN trong phạm vi mapping còn |
| Data Pump Export | Công cụ tạo dump logical |
| Data Pump Import | Nạp snapshot đã có trong dump |
| DIRECTORY | Oracle object trỏ tới filesystem phía database server |
| FLASHBACK privilege | Quyền cần để đọc dữ liệu lịch sử |
| UNDO_RETENTION | Mục tiêu giữ undo, không phải guarantee tuyệt đối |
| ORA-01555 | Không còn đủ undo để dựng snapshot |
| ORA-01466 | Định nghĩa object thay đổi trong khoảng flashback |
| DDL freeze | Tránh thay đổi cấu trúc trong cửa sổ export |
| PARALLEL | Số worker Data Pump mục tiêu |
| %U | Substitution variable tạo nhiều dump pieces |
| External table | File ngoài database không được đóng băng bởi SCN |
| Sequence | Trạng thái không có transactional snapshot semantics như table DML |
| CDC/delta sync | Đồng bộ thay đổi phát sinh sau snapshot |

FLASHBACK_SCN và FLASHBACK_TIME giúp Data Pump Export đọc dữ liệu bảng tại một snapshot chung trong khi ứng dụng vẫn tiếp tục hoạt động. SCN phù hợp khi cần mốc kỹ thuật có thể ghi nhận và tái sử dụng; timestamp thuận tiện theo thời điểm nghiệp vụ nhưng cần chú ý timezone và mapping. Để export thành công, phải giữ đủ UNDO cho tới khi worker cuối cùng đọc xong, tránh DDL trong cửa sổ export, cấp đúng quyền FLASHBACK và kiểm tra toàn bộ log/dump. Snapshot không bao gồm các thay đổi commit sau SCN, không đóng băng file ngoài database và không thay thế cơ chế đồng bộ delta khi cutover. Hãy import thử, đối soát với source AS OF cùng SCN và diễn tập quy trình trước khi migration production.
