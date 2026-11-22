# Flashback Data Archive và kiểm tra điều kiện tính năng

Flashback Data Archive (FDA), trước đây còn được gọi là Oracle Total Recall, là cơ chế lưu lịch sử thay đổi dữ liệu của bảng trong một khoảng thời gian dài hơn thời gian UNDO thông thường. Khi một bảng được bật Flashback Archive, Oracle lưu các phiên bản hàng đã thay đổi vào vùng lưu trữ lịch sử do database quản lý. Người dùng có thể truy vấn lại dữ liệu tại một thời điểm hoặc xem các phiên bản trong một khoảng bằng Flashback Query.

FDA phù hợp khi ứng dụng cần tra cứu lịch sử dữ liệu trong nhiều tháng hoặc nhiều năm, ví dụ:

- Xem thông tin khách hàng tại thời điểm trước khi cập nhật.
- Điều tra thay đổi giá, hạn mức hoặc trạng thái hợp đồng.
- Hỗ trợ yêu cầu kiểm toán và tra cứu lịch sử nghiệp vụ.
- So sánh giá trị hiện tại với các phiên bản trước đó.
- Phục hồi một số dữ liệu logic sau thao tác DML sai.

FDA không phải audit log đầy đủ và không thay thế backup. Nó chủ yếu lưu lịch sử row-level DML của các bảng được bật archive; không tự ghi lại mọi câu lệnh DDL, người dùng cuối, lý do nghiệp vụ hoặc các hoạt động ngoài database. Nếu cần chứng cứ kiểm toán, cần kết hợp Unified Auditing, application audit, CDC hoặc history table theo yêu cầu.

Một điểm cần phân biệt là FDA có vùng lưu trữ và retention riêng, trong khi Flashback Query thông thường phụ thuộc nhiều vào UNDO. FDA có thể giúp truy vấn lịch sử cũ hơn cửa sổ UNDO, nhưng chỉ đối với thay đổi được theo dõi sau khi bảng được bật archive và trong giới hạn retention của archive.

## 1. Flashback Data Archive là gì?

Flashback Data Archive là một vùng lưu trữ lịch sử do Oracle quản lý. Khi bật archive cho một bảng, Oracle theo dõi các thay đổi DML đã commit và lưu các row version lịch sử vào các history table nội bộ thuộc Flashback Archive.

Sơ đồ khái quát:

~~~text
Ứng dụng
   |
   | INSERT / UPDATE / DELETE
   v
Bảng nghiệp vụ được bật Flashback Archive
   |
   | Oracle ghi nhận row version
   v
Flashback Data Archive
   |
   +--> History table nội bộ
   |
   +--> Tablespace lưu lịch sử
   |
   +--> Retention và purge policy
            |
            v
     Flashback Query
       AS OF / VERSIONS
~~~

Người dùng truy vấn bảng bằng SQL Flashback Query. Oracle kết hợp dữ liệu hiện tại, thông tin phiên bản và history data để trả về trạng thái lịch sử.

### 1.1 FDA khác UNDO như thế nào?

UNDO được dùng cho read consistency, rollback và một số tính năng Flashback trong khoảng thời gian undo còn giữ. Undo segment được tái sử dụng theo cơ chế quản lý undo.

FDA lưu lịch sử vào tablespace archive riêng theo retention được cấu hình. Lịch sử không phụ thuộc hoàn toàn vào việc undo segment còn tồn tại hay không.

| Tiêu chí | UNDO | Flashback Data Archive |
|---|---|---|
| Mục tiêu chính | Read consistency, rollback, phục hồi phiên bản gần đây | Lưu lịch sử row version dài hạn |
| Vùng lưu | Undo tablespace | Tablespace của Flashback Archive |
| Thời gian giữ | UNDO_RETENTION là mục tiêu, còn phụ thuộc dung lượng/guarantee | Retention của từng Flashback Archive |
| Bảng cần bật riêng | Không | Có |
| Query | Flashback Query trong phạm vi undo | AS OF/VERSIONS có thể truy vấn lịch sử archive |
| Phù hợp | Lịch sử ngắn hạn, nhất quán đọc | Lịch sử dữ liệu dài hạn |

### 1.2 FDA không tự động lưu mọi bảng

Chỉ các bảng được gắn với Flashback Archive mới được theo dõi. Tạo một Flashback Archive không có nghĩa mọi bảng trong database tự động được lưu lịch sử.

### 1.3 FDA không hồi tố

Khi bật archive cho bảng tại thời điểm T, FDA bắt đầu theo dõi các thay đổi từ thời điểm đó theo cơ chế của Oracle. Nó không tự dựng lại lịch sử của các năm trước khi bật.

Nếu cần lịch sử trước thời điểm triển khai, phải lấy từ nguồn khác như audit, CDC, backup/recovery hoặc bảng history đã tồn tại.

## 2. Các thành phần chính

Một cấu hình FDA thường có:

- **Flashback Archive:** đối tượng quản lý retention và một hoặc nhiều tablespace lưu lịch sử.
- **Tablespace:** vùng chứa history data.
- **Quota:** giới hạn dung lượng archive được phép sử dụng trong tablespace.
- **Retention:** khoảng thời gian lịch sử cần giữ.
- **Archived table:** bảng nghiệp vụ được bật Flashback Archive.
- **History table:** bảng nội bộ do Oracle quản lý để lưu row version.
- **FBDA background process:** tiến trình nền xử lý dữ liệu lịch sử theo kiến trúc Oracle.

Không truy cập hoặc sửa trực tiếp các history table nội bộ. Dùng cú pháp Flashback Query và các dictionary views được Oracle hỗ trợ.

### 2.1 Flashback Archive có thể dùng nhiều tablespace

Một archive có thể được cấu hình với tablespace lưu lịch sử và có thể bổ sung tablespace theo nhu cầu. Oracle quản lý phân bổ history data theo cơ chế FDA.

### 2.2 Retention thuộc archive

Retention được gắn với Flashback Archive, không phải tham số UNDO_RETENTION. Có thể thay đổi retention theo quy trình quản trị archive.

### 2.3 Nhiều archive trong một database

Database có thể có nhiều Flashback Archive với retention/quota khác nhau để phân loại dữ liệu, ví dụ archive lịch sử 1 năm và archive lịch sử 7 năm.

Không phải mọi bảng đều phải dùng cùng một archive. Hãy thiết kế theo data classification, yêu cầu nghiệp vụ và dung lượng.

## 3. Tạo tablespace cho lịch sử

Nên bố trí history data trong tablespace riêng để quản lý dung lượng, I/O, backup và quyền vận hành.

Ví dụ:

~~~sql
CREATE TABLESPACE fda_ts
DATAFILE '/u02/oradata/ORCL/fda_ts01.dbf'
SIZE 2G
AUTOEXTEND ON NEXT 256M MAXSIZE 20G;
~~~

Đường dẫn và dung lượng chỉ là ví dụ. Trong production cần:

- Xác định storage tier phù hợp.
- Dự trù tốc độ phát sinh history data.
- Tính retention theo tháng/năm.
- Kiểm tra autoextend và giới hạn filesystem/ASM.
- Theo dõi I/O và backup window.
- Có cảnh báo khi tablespace gần đầy.

Không dùng cùng một datafile hoặc đường dẫn minh họa cho mọi môi trường.

## 4. Tạo Flashback Data Archive

Ví dụ tạo archive lưu lịch sử trong 5 năm:

~~~sql
CREATE FLASHBACK ARCHIVE fda_5y
TABLESPACE fda_ts
QUOTA 20G
RETENTION 5 YEAR;
~~~

Trong đó:

- FDA_5Y là tên Flashback Archive.
- TABLESPACE chỉ định tablespace lưu lịch sử.
- QUOTA giới hạn dung lượng archive có thể dùng trong tablespace đó.
- RETENTION 5 YEAR xác định thời gian giữ history data.

Cú pháp, đơn vị retention và các tùy chọn có thể khác theo Oracle release. Kiểm tra SQL Language Reference đúng phiên bản trước khi triển khai.

### 4.1 Tạo archive mặc định

Có thể chỉ định một archive làm default:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y SET DEFAULT;
~~~

Khi một bảng được bật Flashback Archive mà không chỉ rõ tên archive, Oracle có thể sử dụng archive mặc định nếu có và người thực hiện có quyền phù hợp.

### 4.2 Kiểm tra archive đã tạo

Các dictionary views thường dùng:

- DBA_FLASHBACK_ARCHIVE.
- DBA_FLASHBACK_ARCHIVE_TS.
- DBA_FLASHBACK_ARCHIVE_TABLES.
- USER_FLASHBACK_ARCHIVE.
- USER_FLASHBACK_ARCHIVE_TABLES.

Ví dụ:

~~~sql
SELECT *
FROM dba_flashback_archive;
~~~

Tablespace của archive:

~~~sql
SELECT *
FROM dba_flashback_archive_ts;
~~~

Bảng đã bật archive:

~~~sql
SELECT *
FROM dba_flashback_archive_tables;
~~~

Tên cột và quyền truy cập có thể thay đổi theo release. Dùng DESC hoặc truy vấn ALL_TAB_COLUMNS để kiểm tra metadata trước khi viết script giám sát dùng chung.

## 5. Bật Flashback Archive cho bảng

Sau khi archive được tạo, bật theo từng bảng:

~~~sql
ALTER TABLE employees
FLASHBACK ARCHIVE fda_5y;
~~~

Nếu đã cấu hình default archive:

~~~sql
ALTER TABLE employees
FLASHBACK ARCHIVE;
~~~

Từ thời điểm bật, Oracle bắt đầu theo dõi thay đổi DML của bảng theo cơ chế FDA.

### 5.1 Bật archive khi tạo bảng

Trong những phiên bản hỗ trợ cú pháp này, có thể chỉ định Flashback Archive khi tạo bảng:

~~~sql
CREATE TABLE employee_contracts (
    contract_id NUMBER PRIMARY KEY,
    employee_id NUMBER NOT NULL,
    contract_status VARCHAR2(30),
    effective_date DATE
)
FLASHBACK ARCHIVE fda_5y;
~~~

Kiểm tra cú pháp cụ thể của release trước khi dùng trong script tạo schema.

### 5.2 Kiểm tra bảng đã bật

~~~sql
SELECT *
FROM dba_flashback_archive_tables
WHERE owner_name = 'HR'
  AND table_name = 'EMPLOYEES';
~~~

Tên cột có thể khác theo phiên bản; nếu không chắc, dùng SELECT * hoặc xem dictionary metadata để xác nhận.

### 5.3 Tắt archive cho bảng

~~~sql
ALTER TABLE employees
NO FLASHBACK ARCHIVE;
~~~

Sau khi tắt, các thay đổi mới của bảng không còn được lưu vào archive theo cấu hình đó. Lịch sử đã lưu có thể vẫn tồn tại trong archive cho tới khi hết retention hoặc bị purge/drop theo quy trình.

Tắt archive không đồng nghĩa xóa ngay lịch sử cũ.

## 6. Truy vấn dữ liệu lịch sử bằng AS OF

Flashback Archive cho phép truy vấn trạng thái bảng tại một thời điểm:

~~~sql
SELECT employee_id,
       employee_name,
       salary
FROM employees
AS OF TIMESTAMP
    TIMESTAMP '2026-01-01 00:00:00'
WHERE employee_id = 100;
~~~

Hoặc theo SCN:

~~~sql
SELECT employee_id,
       employee_name,
       salary
FROM employees
AS OF SCN 123456789
WHERE employee_id = 100;
~~~

AS OF trả một snapshot tại mốc yêu cầu. Nếu cần xem nhiều phiên bản trong một khoảng, dùng VERSIONS BETWEEN.

### 6.1 Thời điểm trước khi bật archive

Nếu truy vấn một thời điểm trước khi bảng được bật FDA, Oracle có thể chỉ dùng UNDO nếu còn đủ dữ liệu. FDA không có lịch sử để trả về cho khoảng thời gian trước khi theo dõi bắt đầu.

### 6.2 Truy vấn join nhiều bảng

Có thể truy vấn nhiều bảng tại cùng một thời điểm:

~~~sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM employees AS OF TIMESTAMP
       TIMESTAMP '2026-01-01 00:00:00' e
JOIN departments AS OF TIMESTAMP
       TIMESTAMP '2026-01-01 00:00:00' d
  ON d.department_id = e.department_id;
~~~

Đảm bảo các bảng đều có lịch sử cần thiết cho thời điểm đó. Nếu chỉ một bảng được bật FDA, khả năng truy vấn lịch sử của join có thể bị giới hạn bởi bảng còn lại và UNDO.

## 7. Truy vấn nhiều phiên bản bằng VERSIONS BETWEEN

VERSIONS BETWEEN cho phép xem các row version trong một khoảng SCN hoặc timestamp:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_endscn,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation
FROM employees
VERSIONS BETWEEN TIMESTAMP
    TIMESTAMP '2026-01-01 00:00:00'
AND TIMESTAMP '2026-06-30 23:59:59'
WHERE employee_id = 100
ORDER BY versions_startscn;
~~~

Các pseudocolumn:

| Pseudocolumn | Ý nghĩa |
|---|---|
| VERSIONS_STARTSCN | SCN bắt đầu row version |
| VERSIONS_ENDSCN | SCN kết thúc row version |
| VERSIONS_STARTTIME | Timestamp bắt đầu |
| VERSIONS_ENDTIME | Timestamp kết thúc |
| VERSIONS_XID | Transaction ID tạo phiên bản |
| VERSIONS_OPERATION | I, U hoặc D |

### 7.1 Lịch sử INSERT

Khi hàng được INSERT và commit, một row version được tạo. VERSIONS_OPERATION có thể hiển thị I trong kết quả phù hợp.

### 7.2 Lịch sử UPDATE

Mỗi UPDATE đã commit tạo phiên bản mới và làm phiên bản trước kết thúc. VERSIONS BETWEEN có thể trả nhiều giá trị của cùng khóa chính.

### 7.3 Lịch sử DELETE

DELETE có thể được thể hiện bằng phiên bản liên quan thao tác D. Đây là cách điều tra giá trị trước khi hàng bị xóa, nếu lịch sử còn trong retention.

### 7.4 FDA và UNDO cùng tham gia

FDA giúp lưu lịch sử dài hạn, nhưng thay đổi mới có thể vẫn được đọc từ UNDO trước khi history data được xử lý hoặc tùy đường truy vấn. Không nên giả định mọi phiên bản vừa commit đã lập tức xuất hiện trong archive history table nội bộ.

## 8. FDA và Flashback Versions Query khác nhau ra sao?

VERSIONS BETWEEN là cú pháp truy vấn. Flashback Data Archive là cơ chế lưu lịch sử lâu dài. Hai thứ bổ sung cho nhau.

| Tiêu chí | Versions Query chỉ dựa UNDO | Versions Query với FDA |
|---|---|---|
| Cú pháp | VERSIONS BETWEEN | VERSIONS BETWEEN |
| Nguồn lịch sử | UNDO | UNDO và history data của FDA |
| Thời gian truy vấn | Bị giới hạn bởi undo retention/thực tế undo còn | Có thể dài hơn nhờ archive retention |
| Bật theo bảng | Không cần FDA | Bảng phải được bật archive |
| Lịch sử trước khi bật FDA | Chỉ có nếu UNDO còn | FDA không backfill lịch sử cũ |
| Lưu nhiều tháng/năm | Không bảo đảm | Theo retention archive |

### 8.1 FDA không thay thế Flashback Database

Flashback Database dùng flashback logs để đưa toàn database về một thời điểm trước đó. FDA lưu lịch sử row-level của các bảng được bật.

| Cơ chế | Phạm vi |
|---|---|
| Flashback Query AS OF | Snapshot bảng tại một thời điểm |
| Flashback Versions Query | Các row version trong một khoảng |
| Flashback Data Archive | Lưu lịch sử row version dài hạn |
| Flashback Table | Đưa bảng về trạng thái trước đó theo điều kiện hỗ trợ |
| Flashback Database | Đưa database về một mốc thời gian/SCN |

Không dùng FDA như phương án thay thế cho backup database hoặc Flashback Database.

## 9. Quản lý retention

Retention xác định khoảng thời gian Oracle giữ lịch sử trong Flashback Archive.

Ví dụ:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
MODIFY RETENTION 7 YEAR;
~~~

Thay đổi retention cần đánh giá:

- Yêu cầu pháp lý/nghiệp vụ.
- Dung lượng history hiện tại.
- Tốc độ DML và tỷ lệ thay đổi.
- Thời gian giữ theo data classification.
- Chi phí backup và storage.
- Thời gian cần để điều tra.

### 9.1 Retention không phải UNDO_RETENTION

UNDO_RETENTION điều khiển mục tiêu giữ undo. FDA retention điều khiển thời gian giữ lịch sử trong Flashback Archive.

Không tăng UNDO_RETENTION để thay thế một chính sách FDA nhiều năm. Ngược lại, không dùng FDA retention để giải quyết mọi lỗi read consistency trong query dài.

### 9.2 Hết retention

History data hết hạn có thể được Oracle purge theo cơ chế quản lý archive. Thời điểm dọn thực tế không nhất thiết trùng đúng giây retention kết thúc; hãy hiểu retention là chính sách thời gian giữ, không phải SLA về thời điểm file vật lý bị xóa.

### 9.3 Retention và yêu cầu legal hold

Nếu tổ chức cần giữ lịch sử lâu hơn policy chuẩn do điều tra hoặc legal hold, cần quy trình quản lý retention được phê duyệt. Không tự ý rút ngắn retention hoặc purge archive trong khi dữ liệu đang thuộc phạm vi điều tra.

## 10. Purge lịch sử

Oracle hỗ trợ purge lịch sử theo mốc thời gian hoặc toàn bộ archive trong phạm vi cú pháp được release hỗ trợ.

Ví dụ purge dữ liệu cũ hơn một năm:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
PURGE BEFORE TIMESTAMP
    (SYSTIMESTAMP - INTERVAL '1' YEAR);
~~~

Ví dụ purge toàn bộ history:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
PURGE ALL;
~~~

PURGE ALL là thao tác có tác động lớn, có thể xóa lịch sử cần cho truy vấn. Chỉ thực hiện theo phê duyệt, retention/legal hold và runbook.

### 10.1 Purge khác DROP archive

- PURGE xóa history data theo phạm vi được chỉ định.
- DROP FLASHBACK ARCHIVE xóa đối tượng archive và có thể làm mất lịch sử liên quan.

Không dùng DROP chỉ để giải phóng vài GB history nếu có thể quản lý bằng retention/purge.

### 10.2 Kiểm tra trước khi purge

- Archive nào đang được dùng?
- Những bảng nào đang gắn archive?
- Khoảng thời gian nào bị xóa?
- Có legal hold hoặc audit request?
- Có backup phù hợp nếu cần giữ bằng chứng?
- Có ứng dụng đang chạy query lịch sử?

## 11. Thêm và bỏ tablespace của Flashback Archive

Khi history data tăng, có thể bổ sung tablespace:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
ADD TABLESPACE fda_ts2
QUOTA 50G;
~~~

Ví dụ bỏ một tablespace:

~~~sql
ALTER FLASHBACK ARCHIVE fda_5y
REMOVE TABLESPACE fda_ts2;
~~~

Việc remove tablespace phải tuân theo điều kiện Oracle, bao gồm dữ liệu còn lưu và cách archive quản lý history segment. Không drop tablespace ở tầng SQL trước khi archive metadata được cập nhật và xác nhận an toàn.

### 11.1 Quota

Quota giới hạn dung lượng Flashback Archive được phép sử dụng trong tablespace. Nếu quota quá nhỏ, archive có thể không ghi được history data theo kỳ vọng.

Theo dõi cả:

- Quota được cấu hình.
- Dung lượng tablespace đã dùng.
- Dung lượng vật lý còn lại.
- Tốc độ tăng history.
- Retention.

### 11.2 Ước lượng dung lượng

Ước lượng sơ bộ:

~~~text
History capacity
  ≈ average changed row volume per day
    × retention days
    × storage overhead factor
    + safety margin
~~~

Đây chỉ là mô hình dự trù. Row width, số lần update cùng một hàng, index/history metadata, compression và phân bố DML làm dung lượng thực tế thay đổi. Hãy đo trên workload đại diện.

## 12. Quyền quản trị và quyền sử dụng FDA

FDA có các quyền hệ thống và object privilege riêng. Cần tách vai trò quản trị archive khỏi vai trò bật archive cho bảng và vai trò truy vấn dữ liệu.

### 12.1 FLASHBACK ARCHIVE ADMINISTER

Quyền hệ thống FLASHBACK ARCHIVE ADMINISTER cho phép quản lý Flashback Archive như tạo, thay đổi hoặc xóa archive theo quy tắc Oracle.

Ví dụ:

~~~sql
GRANT FLASHBACK ARCHIVE ADMINISTER TO fda_admin;
~~~

Không cấp quyền này cho mọi schema ứng dụng. Đây là quyền quản trị retention và vùng lưu lịch sử.

### 12.2 FLASHBACK ARCHIVE object privilege

Có thể cấp quyền sử dụng một archive cho user/schema:

~~~sql
GRANT FLASHBACK ARCHIVE ON fda_5y TO hr_owner;
~~~

Quyền cụ thể cần thiết để bật bảng phụ thuộc owner và thao tác. Người thực hiện ALTER TABLE vẫn cần quyền ALTER trên bảng. Kiểm tra SQL Language Reference đúng release.

### 12.3 Quyền truy vấn lịch sử

Người dùng truy vấn bảng cần quyền SELECT và quyền Flashback phù hợp theo chính sách database. Ví dụ quyền trên bảng:

~~~sql
GRANT SELECT ON hr.employees TO auditor;
GRANT FLASHBACK ON hr.employees TO auditor;
~~~

Không cấp FLASHBACK ANY TABLE cho user chỉ cần xem lịch sử một bảng. Dùng object privilege và role có phạm vi nhỏ.

### 12.4 Phân vai

| Vai trò | Trách nhiệm |
|---|---|
| DBA/FDA admin | Tạo archive, quota, retention, tablespace, purge |
| Schema owner | Bật/tắt archive trên bảng thuộc schema |
| Auditor/analyst | SELECT dữ liệu và truy vấn lịch sử được cấp |
| Security/compliance | Phê duyệt retention, quyền và legal hold |
| Storage admin | Bảo đảm dung lượng, backup và khả năng lưu trữ |

## 13. Kiểm tra dictionary views

Các view thường dùng:

| View | Mục đích |
|---|---|
| DBA_FLASHBACK_ARCHIVE | Thông tin các Flashback Archive |
| DBA_FLASHBACK_ARCHIVE_TS | Tablespace và quota của archive |
| DBA_FLASHBACK_ARCHIVE_TABLES | Các bảng được bật archive |
| USER_FLASHBACK_ARCHIVE | Archive mà user có thể thấy |
| USER_FLASHBACK_ARCHIVE_TABLES | Bảng archive trong schema hiện tại |
| DBA_TABLES | Metadata bảng |
| DBA_TABLESPACES | Metadata tablespace |

Ví dụ kiểm tra danh sách archive:

~~~sql
SELECT *
FROM dba_flashback_archive
ORDER BY flashback_archive_name;
~~~

Kiểm tra bảng:

~~~sql
SELECT *
FROM dba_flashback_archive_tables
ORDER BY owner_name, table_name;
~~~

Kiểm tra tablespace:

~~~sql
SELECT *
FROM dba_flashback_archive_ts
ORDER BY flashback_archive_name, tablespace_name;
~~~

Không hard-code danh sách cột từ một phiên bản vào script dùng cho mọi release. Xác định cấu trúc view bằng:

~~~sql
SELECT column_name,
       data_type
FROM all_tab_columns
WHERE owner = 'SYS'
  AND table_name = 'DBA_FLASHBACK_ARCHIVE'
ORDER BY column_id;
~~~

## 14. Theo dõi dung lượng history

History data nằm trong tablespace của archive. Có thể dùng DBA_SEGMENTS/DBA_DATA_FILES/DBA_FREE_SPACE để theo dõi tổng quan:

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS segment_mb
FROM dba_segments
GROUP BY tablespace_name
ORDER BY segment_mb DESC;
~~~

Kiểm tra datafile:

~~~sql
SELECT tablespace_name,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_data_files
ORDER BY tablespace_name, file_name;
~~~

History table nội bộ thường có tên hệ thống. Không dựa vào pattern tên để sửa/xóa segment. Hãy quản lý qua Flashback Archive, tablespace và dictionary metadata.

### 14.1 Cảnh báo dung lượng

Nên cảnh báo:

- Tablespace history đạt 70%, 85%, 95%.
- Autoextend gần MAXSIZE.
- Filesystem/ASM diskgroup gần đầy.
- Quota archive gần hết.
- History growth cao bất thường.
- FBDA background process gặp lỗi.

Ngưỡng cụ thể phải dựa trên tốc độ tăng và thời gian cần để bổ sung storage.

## 15. Bảng nào có thể dùng Flashback Archive?

Không phải mọi table/object đều hỗ trợ FDA trong mọi phiên bản. Các giới hạn có thể liên quan:

- Kiểu dữ liệu hoặc cấu trúc cột đặc biệt.
- Temporary table.
- Nested table hoặc object-relational type.
- External table.
- Bảng thuộc một số cấu trúc đặc biệt.
- Một số thao tác partition maintenance.
- DDL làm thay đổi cấu trúc table.
- Table đã có thuộc tính hoặc feature không tương thích.

Ví dụ các datatype/đặc điểm như LONG, một số kiểu object collection, BFILE hoặc các cấu trúc đặc biệt có thể bị giới hạn tùy release. Không coi danh sách này là đầy đủ cho mọi phiên bản.

Trước khi bật FDA cho schema lớn:

1. Lập inventory table.
2. Kiểm tra datatype và thuộc tính.
3. Kiểm tra partitioning/LOB/index.
4. Kiểm tra DDL/deployment workflow.
5. Thử bật trên bản sao schema.
6. Chạy DML đại diện và truy vấn lịch sử.

### 15.1 DDL và Flashback Archive

FDA tập trung lưu lịch sử DML. Không coi nó là công cụ version hóa schema.

Một số DDL có thể bị hạn chế khi bảng đang được archive; một số thay đổi schema cần thao tác disable/re-enable hoặc quy trình được release hỗ trợ. Trước khi chạy ALTER TABLE, MOVE, TRUNCATE, partition maintenance hoặc đổi datatype, kiểm tra tài liệu Oracle và thử trong môi trường tương đương.

### 15.2 TRUNCATE không giống DELETE

DELETE là DML theo từng hàng. TRUNCATE là DDL tác động segment. Không giả định FDA sẽ lưu một phiên bản DELETE cho mọi hàng khi chạy TRUNCATE.

Nếu cần lịch sử xóa từng hàng, dùng DELETE theo quy trình hoặc thiết kế audit/CDC; không thay bằng TRUNCATE.

### 15.3 Drop table

DROP TABLE là DDL và có thể có quy tắc riêng với Flashback Archive. Không dùng thao tác này như một cách xóa history. Kiểm tra tài liệu release và archive state trước khi drop object.

## 16. FDA không tự ghi người dùng cuối hoặc lý do nghiệp vụ

Flashback Archive có thể cho biết row version, SCN, timestamp và transaction metadata qua Flashback Query. Nhưng các trường đó không phải audit context đầy đủ.

Ví dụ Versions Query:

~~~sql
SELECT employee_id,
       salary,
       versions_starttime,
       versions_xid,
       versions_operation
FROM employees
VERSIONS BETWEEN TIMESTAMP
    SYSTIMESTAMP - INTERVAL '30' DAY
AND SYSTIMESTAMP
WHERE employee_id = :employee_id;
~~~

Để biết request nào thay đổi dữ liệu, ứng dụng nên thiết lập:

- MODULE.
- ACTION.
- CLIENT_IDENTIFIER.
- Correlation/request ID trong application log.
- Audit policy cho các hành động nhạy cảm.

Không ghi token, mật khẩu hoặc thông tin cá nhân không cần thiết vào module/action/client identifier.

## 17. FDA và Flashback Transaction Query

VERSIONS_XID có thể được dùng để tìm transaction ID tương ứng. Trong điều kiện được hỗ trợ, FLASHBACK_TRANSACTION_QUERY có thể cung cấp metadata transaction và UNDO_SQL.

Ví dụ:

~~~sql
SELECT xid,
       start_scn,
       commit_scn,
       start_timestamp,
       commit_timestamp,
       logon_user,
       operation,
       table_name,
       undo_sql
FROM flashback_transaction_query
WHERE xid = :xid;
~~~

Thông tin có thể không đầy đủ nếu transaction metadata hoặc undo đã hết. Một số thông tin phụ thuộc supplemental logging và quyền truy cập.

UNDO_SQL là dữ liệu hỗ trợ điều tra, không phải script rollback được bảo đảm an toàn. Kiểm tra side effect, trigger, foreign key, thứ tự transaction và trạng thái hiện tại trước khi dùng bất kỳ câu SQL nào để khôi phục.

## 18. FDA và audit/CDC

FDA trả lời câu hỏi “dòng dữ liệu đã có những phiên bản nào?”. Audit/CDC có thể trả lời thêm “ai đã thực hiện, từ ứng dụng nào, theo request nào, và vì sao?” nếu hệ thống được thiết kế ghi nhận.

| Nhu cầu | FDA | Audit/CDC/history table |
|---|---|---|
| Lưu row version theo thời gian | Có | Có thể |
| Truy vấn AS OF/VERSIONS | Có | Cần tự triển khai hoặc xử lý dữ liệu |
| Retention nhiều tháng/năm | Có theo archive policy | Theo retention của giải pháp |
| Actor/user cuối | Không tự bảo đảm | Có thể ghi |
| Business reason/request ID | Không tự bảo đảm | Có thể ghi |
| DDL audit | Không phải mục tiêu chính | Audit/deployment log phù hợp hơn |
| Phát sự kiện sang hệ thống khác | Không phải CDC stream | CDC được thiết kế cho việc đó |
| Chống sửa lịch sử | Không phải immutable audit store | Có thể thiết kế bất biến/off-host |

Nếu yêu cầu là compliance audit, FDA có thể là một nguồn bổ sung nhưng không nên là nguồn duy nhất nếu cần chứng minh actor và hành vi.

## 19. FDA và Flashback Table

Flashback Table có thể đưa một hoặc nhiều bảng về trạng thái tại một mốc thời gian/SCN nếu đáp ứng điều kiện. FDA có thể cung cấp lịch sử lâu dài hỗ trợ một số trường hợp Flashback Query, nhưng không có nghĩa mọi thao tác Flashback Table đều có thể dùng vô hạn.

Ví dụ cú pháp khái quát:

~~~sql
FLASHBACK TABLE employees
TO TIMESTAMP
    (TIMESTAMP '2026-01-01 00:00:00');
~~~

Flashback Table có yêu cầu như row movement và có tác động ghi dữ liệu. Hãy kiểm tra điều kiện, khóa ngoại, trigger, replication và ứng dụng trước khi chạy.

Không dùng Flashback Table trong production chỉ để “xem thử”. Dùng SELECT AS OF/VERSIONS trước để xác định dữ liệu cần khôi phục.

## 20. FDA và backup/recovery

Flashback Archive là dữ liệu database và phải được bảo vệ trong backup strategy. Tablespace chứa history data cần được backup như các tablespace liên quan khác.

Một kế hoạch bảo vệ FDA cần:

- Backup datafile của tablespace archive.
- Backup control file/SPFILE.
- Backup archived redo log nếu ARCHIVELOG.
- Bảo vệ metadata archive.
- Kiểm tra retention sau restore.
- Diễn tập truy vấn lịch sử sau khi restore.

### 20.1 Không nhầm FDA retention với backup retention

FDA retention quy định lịch sử logic còn được giữ trong archive. RMAN retention policy quy định backup vật lý nào cần giữ.

Hai policy độc lập:

| Policy | Quản lý |
|---|---|
| Flashback Archive retention | Row history trong FDA |
| RMAN retention policy | Backup datafile/controlfile/archivelog |
| UNDO_RETENTION | Mục tiêu giữ undo |
| Audit retention | Audit records |

Nếu xóa RMAN backup cũ, FDA history hiện tại có thể vẫn còn. Ngược lại, nếu purge FDA, RMAN backup cũ vẫn có thể chứa dữ liệu lịch sử ở mốc backup.

### 20.2 Restore archive tablespace

Nếu tablespace chứa Flashback Archive bị mất, phải phục hồi theo quy trình RMAN và đảm bảo metadata archive/segment được khôi phục nhất quán. Không tạo lại archive cùng tên rồi mong Oracle tự nhận history cũ nếu các datafile/history segment đã mất.

### 20.3 Clone/PDB move

Khi clone database/PDB, cần hiểu archive metadata, tablespace, history data và retention sẽ được chuyển như thế nào. Thử nghiệm trên bản sao trước khi dùng cho môi trường production.

## 21. Kiểm tra trạng thái tính năng và điều kiện license

Tên bài yêu cầu kiểm tra điều kiện tính năng vì Flashback Data Archive có lịch sử thay đổi về tên gọi, hỗ trợ theo release và điều khoản license. Cần tách ba câu hỏi:

1. Database release/edition có hỗ trợ feature không?
2. Feature có được cấu hình và sử dụng trong môi trường này không?
3. Tổ chức có quyền license/entitlement để sử dụng feature đó không?

Ba câu hỏi này không tương đương nhau.

### 21.1 Xác định phiên bản database

~~~sql
SELECT banner
FROM v$version;
~~~

Hoặc:

~~~sql
SELECT version,
       version_full
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

Cột VERSION_FULL có thể không tồn tại ở release cũ. Kiểm tra dictionary metadata nếu cần script tương thích nhiều phiên bản.

### 21.2 Xác định edition

~~~sql
SELECT banner
FROM v$version
WHERE banner LIKE '%Edition%';
~~~

Trong môi trường có quyền phù hợp, có thể xem:

~~~sql
SELECT parameter,
       value
FROM v$option
WHERE parameter LIKE '%Flashback%';
~~~

V$OPTION và V$VERSION cung cấp thông tin kỹ thuật về môi trường. Chúng không chứng minh tổ chức đã mua hoặc có quyền sử dụng một option/feature theo hợp đồng.

### 21.3 Kiểm tra feature usage metadata

Oracle có view theo dõi việc sử dụng feature:

~~~sql
SELECT name,
       detected_usages,
       currently_used,
       first_usage_date,
       last_usage_date,
       last_sample_date
FROM dba_feature_usage_statistics
WHERE LOWER(name) LIKE '%flashback%'
ORDER BY name;
~~~

View này có thể giúp DBA/license owner nhận biết feature usage mà database ghi nhận. Dữ liệu có thể phụ thuộc thời điểm sample, phiên bản và cơ chế tracking. Không coi kết quả là báo cáo license cuối cùng.

### 21.4 Feature usage không đồng nghĩa entitlement

Các điều sau không chứng minh có license:

- Tạo được Flashback Archive.
- Chạy được ALTER TABLE ... FLASHBACK ARCHIVE.
- V$OPTION hiển thị TRUE.
- DBA_FEATURE_USAGE_STATISTICS ghi nhận feature.
- Database đã cài binary có hỗ trợ feature.

Khả năng kỹ thuật và quyền sử dụng thương mại là hai vấn đề khác nhau. Phải đối chiếu Oracle Licensing Information cho đúng release, edition, platform, cloud service và order document của tổ chức.

### 21.5 Tên gọi Total Recall và Flashback Data Archive

Tài liệu cũ có thể gọi feature là Oracle Total Recall; tài liệu mới thường dùng Flashback Data Archive. Khi tra cứu license, cần tìm cả tên feature lịch sử và tên hiện tại, đồng thời kiểm tra release cụ thể.

Không áp dụng một kết luận license từ bài blog cũ cho mọi phiên bản. Điều khoản có thể khác theo release, edition, chương trình license và dịch vụ cloud.

### 21.6 Kiểm tra quyền với license owner

Trước khi bật FDA trong production, gửi các thông tin sau cho license owner/Oracle account team:

- Database version và Release Update.
- Edition.
- Deployment: on-premises, engineered system hoặc cloud service.
- Feature cần sử dụng: Flashback Data Archive.
- Database/PDB/standby/dev/test có sử dụng hay không.
- Hợp đồng/order document và metric liên quan.
- Tài liệu Oracle Licensing Information áp dụng.

Chỉ tiếp tục triển khai khi entitlement đã được xác nhận theo quy trình tổ chức.

## 22. Khác biệt giữa version và edition

Version trả lời database đang chạy release nào. Edition trả lời sản phẩm/edition được cài. License entitlement trả lời tổ chức có quyền sử dụng feature theo hợp đồng.

| Thông tin | Ví dụ nguồn kiểm tra | Có đủ để xác nhận license? |
|---|---|---|
| Version | V$VERSION, PRODUCT_COMPONENT_VERSION | Không |
| Edition | Banner/version metadata | Không |
| Option visibility | V$OPTION | Không |
| Feature usage | DBA_FEATURE_USAGE_STATISTICS | Không |
| Contract entitlement | Order document, licensing records | Là nguồn cần đối chiếu |
| Product feature matrix | Licensing Information/User Guide đúng release | Cần kết hợp hợp đồng |

Không tự kết luận “đã license” chỉ vì câu SQL chạy thành công. Ngược lại, nếu feature không khả dụng kỹ thuật, cũng cần xác định đó là giới hạn release, edition, cấu hình hay quyền.

## 23. Cấu hình FDA trong CDB/PDB

Trong môi trường multitenant, cần xác định Flashback Archive được quản lý trong container nào và bảng thuộc PDB nào.

Trước khi tạo archive:

- Kết nối đúng CDB root hay PDB.
- Kiểm tra tablespace nằm trong container phù hợp.
- Xác định user quản trị archive.
- Xác định bảng được bật thuộc schema/PDB nào.
- Kiểm tra quyền và khả năng quản lý history trong container.

Ví dụ kiểm tra container:

~~~sql
SHOW CON_NAME;
~~~

Hoặc:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Không giả định archive tạo trong root có thể dùng theo cùng cách trong mọi PDB hoặc mọi release. Xác nhận tài liệu multitenant của phiên bản.

## 24. FDA trong RAC và Data Guard

### 24.1 RAC

Trong RAC, các instance cùng truy cập database storage. Tablespace history và file liên quan phải nằm trên storage được kiến trúc cluster hỗ trợ. Theo dõi dung lượng và background process ở cấp database/instance phù hợp.

Không đặt datafile history trên local filesystem của một node nếu các instance khác không thể truy cập.

### 24.2 Data Guard

Flashback Archive data được lưu trong tablespace và thay đổi được ghi redo theo cơ chế database. Standby nhận/apply redo để duy trì dữ liệu archive cùng database.

Kiểm tra:

- Tablespace archive có trên standby?
- Redo apply có theo kịp?
- Sau switchover, archive query có hoạt động?
- Retention/purge có đồng nhất?
- Backup standby/primary có đủ?

Không chỉ kiểm tra query trên primary rồi kết luận DR đã sẵn sàng. Phải diễn tập switchover/failover và query lịch sử trên database đích.

## 25. Hiệu năng và tác động lưu trữ

FDA làm tăng dung lượng lưu trữ vì các phiên bản lịch sử được giữ lại. Chi phí phụ thuộc:

- Số hàng được bật archive.
- Tần suất UPDATE/DELETE.
- Độ rộng hàng.
- Số lần một hàng thay đổi trong retention.
- Retention duration.
- Kiểu dữ liệu.
- Compression/storage characteristics.
- Purge schedule.

Một bảng OLTP update cùng hàng nhiều lần mỗi phút có thể tạo history lớn hơn bảng chỉ insert một lần.

### 25.1 Đo trước khi mở rộng

Thực hiện thử nghiệm:

1. Lấy baseline dung lượng tablespace.
2. Bật FDA trên một nhóm bảng đại diện.
3. Chạy workload thật hoặc dữ liệu mô phỏng.
4. Đo history growth theo ngày.
5. Ước lượng theo retention.
6. Kiểm tra backup duration và restore.

Không nhân số hàng hiện tại với số năm retention rồi coi là dự toán chính xác.

### 25.2 Tác động DML

FDA có thể tạo thêm công việc nền và I/O để lưu lịch sử. Đo latency, throughput, CPU và storage I/O trước/sau khi bật trên workload đại diện.

### 25.3 FBDA background process

Oracle sử dụng background process liên quan Flashback Data Archive để xử lý history. Nếu history không được lưu như mong đợi, kiểm tra alert log, background process và archive tablespace thay vì sửa trực tiếp history table nội bộ.

## 26. Thay đổi schema và migration

Trước khi triển khai DDL trên bảng đang bật FDA:

- Kiểm tra loại DDL có được hỗ trợ không.
- Kiểm tra có cần tạm disable archive không.
- Xác định lịch sử cũ có được giữ không.
- Kiểm tra index, partition, LOB và constraint.
- Kiểm tra application compatibility.
- Kiểm thử trên bản sao.

Không coi NO FLASHBACK ARCHIVE rồi ALTER TABLE là quy trình mặc định an toàn. Việc tắt archive có thể làm mất khả năng theo dõi các thay đổi trong khoảng tạm dừng.

Nếu cần thay đổi schema:

1. Lập kế hoạch downtime/online DDL.
2. Xác định khoảng lịch sử có thể bị gián đoạn.
3. Backup và kiểm thử.
4. Thực hiện thao tác được release hỗ trợ.
5. Bật lại archive nếu cần.
6. Xác minh dictionary và query lịch sử.

## 27. Quy trình điều tra thay đổi dữ liệu dài hạn

Giả sử cần tìm lịch sử thay đổi trạng thái hợp đồng trong 3 năm:

1. Xác nhận bảng CONTRACTS đã bật FDA từ trước thời điểm cần tra.
2. Xác định archive và retention có bao phủ 3 năm.
3. Xác nhận history tablespace còn dữ liệu.
4. Query AS OF hoặc VERSIONS BETWEEN theo SCN/TIMESTAMP.
5. Lọc theo contract_id.
6. Đọc STARTSCN/ENDSCN/XID/OPERATION.
7. Tương quan XID với audit/application context nếu cần.
8. Lưu kết quả theo chính sách bảo vệ dữ liệu.

Ví dụ:

~~~sql
SELECT contract_id,
       contract_status,
       effective_date,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation
FROM contracts
VERSIONS BETWEEN TIMESTAMP
    TIMESTAMP '2023-01-01 00:00:00'
AND TIMESTAMP '2026-01-01 00:00:00'
WHERE contract_id = :contract_id
ORDER BY versions_starttime;
~~~

Nếu bảng chỉ được bật FDA từ năm 2025, query không thể tự tạo lịch sử 2023-2024. Cần nguồn dữ liệu khác cho giai đoạn đó.

## 28. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không thấy lịch sử trước ngày bật FDA | FDA không backfill | Tìm audit/backup/CDC cũ |
| AS OF trả lỗi snapshot | Mốc quá cũ so với UNDO/FDA hoặc object restriction | Kiểm tra archive enablement, retention, object |
| Tablespace archive đầy | Quota/retention/growth không phù hợp | Mở rộng storage, thêm tablespace, review retention |
| Không bật được archive cho bảng | Quyền thiếu hoặc table feature không hỗ trợ | Kiểm tra privilege và release restrictions |
| DDL bị từ chối | Table đang FDA-enabled và thao tác không hỗ trợ | Kiểm tra tài liệu DDL, runbook migration |
| History query không đủ hàng | Retention/purge/enablement window | Kiểm tra archive metadata và thời gian bật |
| FDA admin không tạo được archive | Thiếu privilege/tablespace quota | Kiểm tra FLASHBACK ARCHIVE ADMINISTER |
| Query lịch sử không chạy | Thiếu SELECT/FLASHBACK privilege | Cấp object privilege tối thiểu |
| FBDA process có lỗi | Storage, metadata hoặc background issue | Kiểm tra alert log và DBA |
| Feature chạy được nhưng license chưa rõ | Technical capability bị nhầm với entitlement | Xác nhận licensing information và hợp đồng |
| Drop archive làm mất lịch sử | Thao tác destructive | Backup, phê duyệt và purge policy |
| Tưởng FDA là audit log | Thiếu actor/reason/request context | Kết hợp auditing/CDC/application log |

## 29. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Nghĩ tạo archive là tự theo dõi mọi bảng | Không có history cho bảng chưa bật | ALTER TABLE ... FLASHBACK ARCHIVE |
| Nghĩ FDA backfill lịch sử cũ | Không thể truy vấn giai đoạn trước enablement | Xác định mốc bật và nguồn lịch sử khác |
| Nhầm FDA retention với UNDO_RETENTION | Thiết kế sai thời gian lưu | Quản lý hai policy độc lập |
| Nghĩ FDA là audit trail đầy đủ | Thiếu actor, reason, DDL | Kết hợp Unified Auditing/CDC/application log |
| Sửa SYS_FBA_* trực tiếp | Có thể phá metadata/history | Chỉ dùng supported SQL/dictionary |
| Purge ALL để giải phóng disk ngay | Mất lịch sử dài hạn | Review retention/legal hold trước |
| Drop tablespace trước khi remove khỏi archive | Mất dữ liệu hoặc metadata không nhất quán | Quản lý qua ALTER FLASHBACK ARCHIVE |
| Bật FDA cho mọi bảng | Tăng storage/I/O không cần thiết | Chọn bảng theo data classification |
| Không tính history growth | Tablespace/quota đầy | Benchmark và cảnh báo |
| Nghĩ DDL cũng được lưu như DML | Không có schema history đầy đủ | Dùng DDL audit/deployment log |
| Dùng feature usage view để xác nhận license | Kết luận license sai | Đối chiếu contract/licensing guide |
| Dùng V$OPTION làm bằng chứng entitlement | Khả năng kỹ thuật bị nhầm quyền thương mại | License owner xác nhận |
| Chỉ test trên primary | DR/PDB chưa sẵn sàng | Restore/switchover drill |
| Không backup tablespace history | Mất khả năng truy vấn lịch sử sau recovery | Bao gồm FDA tablespace trong backup |

## 30. Checklist triển khai Flashback Data Archive

**Nhu cầu**

- Bảng nào cần lưu lịch sử?
- Cần giữ bao lâu?
- Cần row history hay audit evidence?
- Có cần actor/request/reason?
- Có dữ liệu lịch sử trước thời điểm triển khai?

**Điều kiện tính năng**

- Database version/Release Update đã xác định?
- Edition/platform đã xác định?
- Flashback Data Archive có được hỗ trợ trong cấu hình đó?
- License entitlement đã được license owner xác nhận?
- Có điều kiện riêng cho cloud/DR/test/standby?

**Storage và retention**

- Tablespace riêng đã tạo?
- Quota và autoextend phù hợp?
- Đã đo history growth?
- Retention được business/compliance phê duyệt?
- Có purge/legal hold policy?
- Có cảnh báo dung lượng?

**Quyền**

- FDA admin có quyền FLASHBACK ARCHIVE ADMINISTER?
- Schema owner có quyền cần thiết để bật bảng?
- Auditor chỉ có SELECT/FLASHBACK object privilege phù hợp?
- Không cấp quyền toàn hệ thống quá rộng?

**Vận hành**

- Bảng đã được bật đúng archive?
- Query AS OF/VERSIONS hoạt động?
- DDL migration đã có runbook?
- Backup bao gồm history tablespace?
- Restore test có query được history?
- RAC/Data Guard/PDB đã được kiểm tra?

## 31. Bài thực hành tự kiểm tra

Thực hiện trong schema lab và database đã xác nhận quyền sử dụng feature.

### Bài 1 — Tạo tablespace

Tạo tablespace riêng cho history, xác nhận datafile, autoextend và dung lượng.

### Bài 2 — Tạo Flashback Archive

Tạo archive với retention 1 năm và quota phù hợp. Query DBA_FLASHBACK_ARCHIVE để xác nhận.

### Bài 3 — Bật archive cho bảng

Tạo bảng demo và chạy ALTER TABLE ... FLASHBACK ARCHIVE. Xác nhận trong DBA_FLASHBACK_ARCHIVE_TABLES.

### Bài 4 — INSERT/UPDATE/DELETE

Thực hiện nhiều thao tác DML và commit. Query VERSIONS BETWEEN để xem row version.

### Bài 5 — AS OF

Query bảng tại một thời điểm giữa hai lần UPDATE. So sánh với dữ liệu hiện tại.

### Bài 6 — So sánh UNDO và FDA

Trong lab có retention phù hợp, truy vấn một mốc cũ hơn cửa sổ UNDO nhưng còn trong FDA. Ghi nhận khác biệt.

### Bài 7 — Thay đổi retention

Thay đổi retention archive trong lab. Quan sát metadata và cách history hết hạn được quản lý.

### Bài 8 — Purge

Tạo dữ liệu lịch sử thử, purge một khoảng cũ và xác nhận query lịch sử. Không chạy PURGE ALL trên dữ liệu quan trọng.

### Bài 9 — Tablespace capacity

Theo dõi DBA_SEGMENTS và DBA_DATA_FILES trước/sau workload update. Ước lượng growth theo ngày.

### Bài 10 — Quyền

Tạo FDA admin và schema owner riêng. Thử cấp quyền tối thiểu, bật archive và truy vấn lịch sử.

### Bài 11 — Feature usage

Query DBA_FEATURE_USAGE_STATISTICS cho tên Flashback. Giải thích vì sao đây không phải bằng chứng license.

### Bài 12 — Backup/restore

Backup database có FDA tablespace, restore trong lab và xác nhận truy vấn lịch sử sau recovery.

## 32. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| Flashback Data Archive | Lưu row history dài hạn theo retention |
| Total Recall | Tên gọi lịch sử của feature |
| FDA tablespace | Vùng chứa history data |
| History table | Bảng nội bộ Oracle quản lý, không sửa trực tiếp |
| FBDA | Background process xử lý history |
| CREATE FLASHBACK ARCHIVE | Tạo archive với tablespace/quota/retention |
| ALTER TABLE ... FLASHBACK ARCHIVE | Bật theo dõi lịch sử cho bảng |
| NO FLASHBACK ARCHIVE | Tắt theo dõi cho bảng |
| AS OF | Xem trạng thái tại một mốc |
| VERSIONS BETWEEN | Xem nhiều row version trong một khoảng |
| FDA retention | Thời gian giữ history trong archive |
| UNDO_RETENTION | Mục tiêu giữ undo, độc lập với FDA retention |
| PURGE | Xóa history theo phạm vi |
| FLASHBACK ARCHIVE ADMINISTER | Quyền quản trị archive |
| FLASHBACK ARCHIVE object privilege | Quyền sử dụng archive |
| DBA_FLASHBACK_ARCHIVE | Metadata archive |
| DBA_FLASHBACK_ARCHIVE_TS | Tablespace/quota archive |
| DBA_FLASHBACK_ARCHIVE_TABLES | Bảng được bật archive |
| DBA_FEATURE_USAGE_STATISTICS | Thống kê feature usage, không chứng minh license |
| License entitlement | Quyền sử dụng theo hợp đồng và licensing guide |

Flashback Data Archive giúp lưu lịch sử row version lâu dài hơn UNDO cho các bảng được bật theo dõi. Hãy tạo archive trong tablespace riêng, chọn retention/quota theo yêu cầu nghiệp vụ, cấp quyền theo vai trò và dùng AS OF/VERSIONS để truy vấn. FDA không backfill lịch sử trước ngày enable, không phải audit trail đầy đủ và không thay thế RMAN backup. Khi kiểm tra điều kiện tính năng, phân biệt version/edition, khả năng kỹ thuật và entitlement theo hợp đồng; DBA_FEATURE_USAGE_STATISTICS hay V$OPTION chỉ là thông tin kỹ thuật, không phải xác nhận license. Trước production, hãy thử DML, DDL, purge, backup/restore và truy vấn lịch sử trên môi trường tương đương.
