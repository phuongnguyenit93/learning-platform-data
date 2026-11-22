# Bộ ký tự, timezone file, VERSION và tương thích giữa nguồn/đích

Khi di chuyển Oracle Database bằng Data Pump, transportable tablespaces, RMAN hoặc các công cụ nâng cấp, khả năng tương thích giữa database nguồn và database đích không chỉ phụ thuộc vào số phiên bản Oracle. DBA cần kiểm tra ít nhất bốn lớp cấu hình:

1. **Character set:** bộ ký tự của database và national character set có biểu diễn được dữ liệu nguồn hay không.
2. **Time zone file version:** bộ quy tắc múi giờ mà Oracle dùng để xử lý các kiểu timestamp có timezone có tương thích hay không.
3. **Database release và COMPATIBLE:** phiên bản phần mềm, cấu trúc metadata và mức tính năng mà database được phép sử dụng.
4. **Data Pump VERSION:** phiên bản metadata mà Export tạo ra để hỗ trợ import vào database đích.

Các khái niệm này độc lập nhưng có thể cùng gây lỗi trong một lần migration. Ví dụ, Data Pump có thể đọc được dump file nhưng import thất bại do target có timezone file version thấp hơn source; hoặc metadata được export ở mức tương thích nhưng target character set không biểu diễn được một số ký tự nguồn.

Vì vậy, trước khi chạy export/import, cần lập compatibility matrix giữa nguồn và đích, kiểm kê dữ liệu thực tế, xác định các tính năng được sử dụng, rồi thử migration trên bản sao đại diện. Không nên xem việc expdp hoàn tất thành công là bằng chứng import sẽ thành công hoặc dữ liệu sau chuyển đổi không bị mất.

## 1. Bốn loại version cần phân biệt

Trong Oracle, từ “version” có thể chỉ nhiều khái niệm khác nhau:

| Khái niệm | Cho biết điều gì? | Ảnh hưởng chính |
|---|---|---|
| Oracle Database release | Phiên bản phần mềm/database, ví dụ 19c hoặc 21c | Khả năng đọc metadata, feature và dump format |
| COMPATIBLE | Mức tương thích tính năng database được cấu hình | Cấu trúc/feature database có thể sử dụng và khả năng downgrade |
| Data Pump VERSION | Mức metadata mà Export tạo ra | Khả năng import vào release cũ hơn trong phạm vi được hỗ trợ |
| Time zone file version | Bộ quy tắc timezone region mà Oracle sử dụng | Chuyển đổi timestamp có timezone và Data Pump TSTZ compatibility |

Character set lại là một thuộc tính khác, không phải version. Source và target có thể cùng Oracle release, cùng COMPATIBLE nhưng khác character set hoặc timezone file version.

### 1.1. Oracle release không đồng nghĩa COMPATIBLE

Oracle Home có thể là 19c nhưng database COMPATIBLE vẫn được đặt ở mức thấp hơn để giữ khả năng tương thích với feature set cũ. Ngược lại, khi COMPATIBLE được nâng lên, database có thể sử dụng cấu trúc hoặc tính năng không còn tương thích với release cũ.

### 1.2. Data Pump VERSION không nâng cấp database

Tham số VERSION của expdp điều khiển phiên bản metadata được ghi vào dump file trong phạm vi Oracle hỗ trợ. Nó không đổi database source, không chuyển character set, không nâng timezone file và không làm cho mọi tính năng mới hoạt động trên database cũ.

### 1.3. Time zone file version không phải DBTIMEZONE

Time zone file version là phiên bản bộ dữ liệu timezone region. DBTIMEZONE là timezone của database, còn SESSIONTIMEZONE là timezone của session hiện tại. Ba giá trị có mục đích khác nhau.

## 2. Character set của Oracle Database

### 2.1. Character set là gì?

Character set xác định cách mã hóa ký tự thành byte. Trong Oracle, character set ảnh hưởng cách dữ liệu ký tự được lưu, so sánh, chuyển đổi và trao đổi giữa client/database.

Ví dụ:

- AL32UTF8: Unicode UTF-8 theo chuẩn hiện đại, hỗ trợ supplementary characters.
- WE8MSWIN1252: bộ ký tự Windows Western European.
- WE8ISO8859P1: bộ ký tự ISO-8859-1.
- JA16SJIS: bộ ký tự Shift-JIS tiếng Nhật.
- AL16UTF16: Unicode UTF-16, thường dùng làm national character set.

Tên character set có ý nghĩa kỹ thuật; không nên suy luận chỉ từ tên ngôn ngữ hoặc locale của server.

### 2.2. NLS_CHARACTERSET

NLS_CHARACTERSET là database character set. Nó được dùng cho các kiểu dữ liệu ký tự thông thường:

- CHAR
- VARCHAR2
- CLOB
- Một số metadata và dữ liệu ký tự database khác

Kiểm tra:

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter = 'NLS_CHARACTERSET';
```

Hoặc:

```sql
SELECT value
FROM nls_database_parameters
WHERE parameter = 'NLS_CHARACTERSET';
```

### 2.3. NLS_NCHAR_CHARACTERSET

NLS_NCHAR_CHARACTERSET là national character set, được dùng cho:

- NCHAR
- NVARCHAR2
- NCLOB

Các giá trị thường gặp là AL16UTF16 hoặc UTF8 legacy. Kiểm tra:

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
```

National character set tách biệt với database character set. Việc database dùng AL32UTF8 không có nghĩa NLS_NCHAR_CHARACTERSET cũng tự động là AL32UTF8.

### 2.4. AL32UTF8 và UTF8 của Oracle

Hai tên này rất dễ nhầm:

- **AL32UTF8** là Oracle character set triển khai Unicode UTF-8 chuẩn, hỗ trợ các ký tự ngoài Basic Multilingual Plane.
- **UTF8** là tên character set legacy của Oracle, dùng CESU-8 để biểu diễn supplementary characters; nó không tương đương UTF-8 chuẩn hiện đại.

Với database mới cần Unicode, AL32UTF8 thường là lựa chọn được khuyến nghị. Không nên chọn UTF8 chỉ vì tên có chữ UTF.

### 2.5. Character set superset và subset

Một character set có thể biểu diễn toàn bộ ký tự của character set khác được xem là superset trong ngữ cảnh chuyển đổi tương ứng. Nếu target không biểu diễn được ký tự source, conversion có thể gây:

- Ký tự bị thay thế.
- Lỗi conversion.
- Giá trị bị mất hoặc thay đổi.
- Import thất bại ở một số dòng/cột.
- Dữ liệu dài hơn giới hạn byte sau conversion.

Không thể chỉ so sánh tên charset để kết luận tương thích. Cần kiểm tra quan hệ superset/subset, dữ liệu thực tế, kiểu dữ liệu và đường chuyển đổi.

## 3. Client character set và NLS_LANG

### 3.1. NLS_LANG là gì?

NLS_LANG là biến môi trường phía client Oracle OCI, có cấu trúc:

```text
NLS_LANG=LANGUAGE_TERRITORY.CHARACTERSET
```

Ví dụ minh họa:

```text
NLS_LANG=AMERICAN_AMERICA.AL32UTF8
```

Phần CHARACTERSET mô tả encoding mà client sử dụng. Oracle client có thể chuyển đổi giữa client character set và database character set khi truyền dữ liệu.

### 3.2. NLS_LANG không đổi database character set

Đặt NLS_LANG không thay đổi NLS_CHARACTERSET của database. Nó cũng không tự chuyển dữ liệu đã lưu. NLS_LANG chỉ ảnh hưởng quá trình trao đổi ký tự ở client OCI và cách client biểu diễn/nhận dữ liệu.

Nếu client terminal dùng encoding UTF-8 nhưng NLS_LANG khai báo một charset khác, dữ liệu nhập/xuất có thể bị mojibake hoặc ký tự sai. Đây có thể là lỗi client conversion dù dữ liệu trong database vẫn đúng.

### 3.3. Kiểm tra NLS session

```sql
SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;
```

NLS_SESSION_PARAMETERS cho biết các NLS settings của session. Nó không phải nguồn duy nhất để xác định client OS encoding.

### 3.4. NLS_LANG và Data Pump

Data Pump thực hiện chuyển đổi dữ liệu dựa trên metadata character set của database và dump file. Không dùng NLS_LANG như cách sửa một dump có source charset không tương thích target. Với lỗi chuyển đổi, kiểm tra database character set, national character set, dữ liệu và Data Pump logs.

### 3.5. Kiểm tra lỗi hiển thị

Khi dữ liệu tiếng Việt hoặc Unicode hiển thị sai:

1. Kiểm tra NLS_CHARACTERSET và NLS_NCHAR_CHARACTERSET.
2. Kiểm tra encoding của terminal, application driver và client.
3. Kiểm tra NLS_LANG nếu dùng OCI client.
4. Đọc cùng một giá trị qua nhiều client có encoding đã biết.
5. Phân biệt dữ liệu đã lưu sai với dữ liệu chỉ hiển thị sai.

Không cập nhật hàng loạt dữ liệu để “sửa encoding” trước khi xác định lỗi nằm ở storage hay client conversion.

## 4. Unicode và chuyển đổi character set

### 4.1. Vì sao migration cần kiểm tra Unicode?

Một database cũ có thể dùng character set giới hạn theo một vùng/ngôn ngữ. Khi chuyển sang hệ thống mới có dữ liệu đa ngôn ngữ, emoji hoặc ký tự supplementary, charset cũ có thể không biểu diễn được toàn bộ dữ liệu.

Chuyển sang Unicode thường là một phần của modernization, nhưng cần đánh giá dung lượng, index, column length semantics, ứng dụng và các interface ngoài database.

### 4.2. Conversion khi export/import

Data Pump có thể chuyển đổi dữ liệu ký tự từ character set của source sang character set target khi import. Kết quả phụ thuộc target có biểu diễn được dữ liệu nguồn hay không và kiểu dữ liệu được chuyển.

Ví dụ:

- Source WE8MSWIN1252 sang target AL32UTF8: target có thể biểu diễn tập ký tự nguồn và còn hỗ trợ nhiều ký tự hơn.
- Source AL32UTF8 sang target WE8MSWIN1252: các ký tự ngoài tập đích có thể không biểu diễn được; conversion có thể báo lỗi hoặc mất dữ liệu tùy đường chuyển đổi.

Phải kiểm tra bằng dữ liệu thật và log import, không chỉ nhìn tên charset.

### 4.3. Character set conversion không phải byte copy

Khi conversion, Oracle diễn giải byte theo source character set rồi mã hóa lại theo target character set. Số byte có thể tăng hoặc giảm. Một cột VARCHAR2 khai báo BYTE semantics có thể vượt giới hạn byte sau khi conversion dù số ký tự không đổi.

### 4.4. BYTE và CHAR length semantics

VARCHAR2(100 BYTE) giới hạn theo byte; VARCHAR2(100 CHAR) giới hạn theo số ký tự theo semantics được hỗ trợ. Trong AL32UTF8, một ký tự có thể chiếm từ 1 đến 4 byte.

Kiểm tra metadata:

```sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       char_length,
       char_used
FROM dba_tab_columns
WHERE data_type IN ('CHAR', 'VARCHAR2', 'NCHAR', 'NVARCHAR2')
ORDER BY owner, table_name, column_id;
```

CHAR_USED thường giúp phân biệt BYTE và CHAR semantics. Xem kỹ cột gần giới hạn trước khi chuyển sang charset có độ dài byte khác.

### 4.5. MAX_STRING_SIZE

MAX_STRING_SIZE điều khiển giới hạn kích thước một số kiểu dữ liệu SQL như VARCHAR2, NVARCHAR2 và RAW trong SQL. Đây là một tham số/feature khác với character set. Khi source và target khác cấu hình MAX_STRING_SIZE, kiểm tra các cột hoặc expression dùng kích thước mở rộng và yêu cầu nâng cấp tương ứng.

### 4.6. CLOB và NCLOB

CLOB dùng database character set; NCLOB dùng national character set. Chuyển đổi CLOB/NCLOB có thể khác với chuyển VARCHAR2/NVARCHAR2 về giới hạn kích thước và cách xử lý. Kiểm kê LOB columns và kiểm thử nội dung đa ngôn ngữ.

### 4.7. NLS_NCHAR_CONV_EXCP

NLS_NCHAR_CONV_EXCP có thể được bật để yêu cầu Oracle phát sinh exception khi chuyển đổi dữ liệu NCHAR/NVARCHAR2 gây mất ký tự trong những tình huống được parameter quản lý. Nó hữu ích cho kiểm thử conversion nhưng không thay thế quy trình đánh giá toàn bộ database.

### 4.8. Database character set migration và DMU

Khi cần đổi database character set, Oracle cung cấp Database Migration Assistant for Unicode (DMU) để phân tích dữ liệu, tìm cột có nguy cơ, hỗ trợ làm sạch và chuyển đổi. Đây là phương pháp nên đánh giá cho chuyển đổi database sang Unicode.

Không chạy ALTER DATABASE CHARACTER SET như một lệnh sửa nhanh. Thao tác đó có các điều kiện chặt chẽ và không thay thế quy trình migration được hỗ trợ. Với database cũ, các công cụ CSSCAN/CSALTER từng được dùng trong một số release; hãy dùng công cụ được Oracle hỗ trợ cho release hiện tại.

## 5. Time zone file trong Oracle

### 5.1. Time zone file là gì?

Oracle sử dụng timezone files chứa tên vùng múi giờ và quy tắc offset theo thời gian, bao gồm lịch sử thay đổi timezone và daylight saving time của các khu vực. Quy tắc này có thể thay đổi theo quyết định của chính phủ, vì vậy Oracle phát hành các version timezone file mới.

Time zone file version ảnh hưởng cách Oracle diễn giải các timestamp có timezone region. Khi database nguồn và đích có version khác nhau, Data Pump có thể cần xử lý tương thích trước khi import dữ liệu TSTZ.

### 5.2. Vị trí timezone files

Trong Oracle Home, timezone files thường nằm dưới thư mục:

```text
$ORACLE_HOME/oracore/zoneinfo
```

Có thể có file nhỏ và file lớn theo naming convention của release, ví dụ timezlrg_n.dat. Không copy file timezone từ Oracle Home khác vào database đang chạy như một cách nâng version thủ công.

### 5.3. Kiểm tra timezone file version

```sql
SELECT * FROM v$timezone_file;
```

View thường hiển thị filename và version đang được database sử dụng. Kiểm tra trên cả source và target; ghi lại kết quả cùng Oracle Home/release.

### 5.4. Xem tên timezone được hỗ trợ

```sql
SELECT tzname
FROM v$timezone_names
WHERE tzname IN (
    'UTC',
    'Asia/Ho_Chi_Minh',
    'America/New_York',
    'Europe/London'
)
ORDER BY tzname;
```

Tên vùng được hỗ trợ phụ thuộc timezone file. Không nên lưu timezone abbreviation mơ hồ như CST khi nghiệp vụ cần vùng cụ thể; ưu tiên region name.

## 6. DBTIMEZONE, SESSIONTIMEZONE và timestamp

### 6.1. DBTIMEZONE

DBTIMEZONE là timezone của database. Nó không phải timezone file version và cũng không nhất thiết bằng timezone của operating system.

Kiểm tra:

```sql
SELECT dbtimezone FROM dual;
```

### 6.2. SESSIONTIMEZONE

SESSIONTIMEZONE là timezone của session hiện tại:

```sql
SELECT sessiontimezone FROM dual;
```

Ứng dụng có thể đặt session timezone bằng ALTER SESSION hoặc thông qua connection initialization. Các session khác nhau có thể hiển thị timestamp theo timezone khác nhau.

### 6.3. SYSTIMESTAMP và CURRENT_TIMESTAMP

- SYSTIMESTAMP trả timestamp của hệ thống database host kèm timezone/offset.
- CURRENT_TIMESTAMP trả timestamp hiện tại theo session timezone.
- LOCALTIMESTAMP trả timestamp không kèm timezone theo session timezone.

Ví dụ:

```sql
SELECT systimestamp,
       current_timestamp,
       localtimestamp,
       dbtimezone,
       sessiontimezone
FROM dual;
```

### 6.4. TIMESTAMP WITH TIME ZONE

TIMESTAMP WITH TIME ZONE (TSTZ) lưu timestamp kèm timezone displacement hoặc region information theo cách Oracle quản lý. Dùng region name cho nghiệp vụ cần giữ danh tính vùng timezone, vì offset cố định không biểu diễn đầy đủ quy tắc DST lịch sử/tương lai.

### 6.5. TIMESTAMP WITH LOCAL TIME ZONE

TIMESTAMP WITH LOCAL TIME ZONE (TSLTZ) được chuẩn hóa theo DBTIMEZONE khi lưu và được hiển thị theo SESSIONTIMEZONE khi truy vấn. Giá trị không giữ timezone region ban đầu như TSTZ.

### 6.6. TIMESTAMP không timezone

TIMESTAMP thông thường không chứa timezone. Nếu ứng dụng lưu thời điểm UTC vào TIMESTAMP mà không ghi quy ước, người đọc có thể diễn giải sai thành giờ địa phương. Cần chuẩn hóa quy ước ở schema và application contract.

### 6.7. Ví dụ phân biệt

```sql
CREATE TABLE timezone_lab (
    event_id NUMBER,
    event_tstz TIMESTAMP WITH TIME ZONE,
    event_tsltz TIMESTAMP WITH LOCAL TIME ZONE,
    event_ts TIMESTAMP
);

INSERT INTO timezone_lab
VALUES (
    1,
    TO_TIMESTAMP_TZ(
        '2026-11-14 09:00:00 Asia/Ho_Chi_Minh',
        'YYYY-MM-DD HH24:MI:SS TZR'
    ),
    TO_TIMESTAMP_TZ(
        '2026-11-14 09:00:00 Asia/Ho_Chi_Minh',
        'YYYY-MM-DD HH24:MI:SS TZR'
    ),
    TIMESTAMP '2026-11-14 09:00:00'
);
COMMIT;
```

Khi thay đổi SESSIONTIMEZONE rồi query lại, cách hiển thị TSTZ và TSLTZ có thể khác. TSTZ giữ thông tin timezone của giá trị; TSLTZ hiển thị theo session timezone.

## 7. Time zone file version và dữ liệu TSTZ

### 7.1. Vì sao version có thể khác?

Oracle cập nhật timezone rules khi có thay đổi chính sách giờ địa phương hoặc DST. Hai Oracle Home khác release/patch level có thể đi kèm timezone file versions khác nhau.

Source có thể lưu TSTZ values theo version cũ, trong khi target dùng version mới; hoặc source có version mới hơn target. Tình huống thứ hai đặc biệt quan trọng khi Data Pump import dữ liệu timestamp có timezone.

### 7.2. ORA-39405

Một lỗi thường gặp khi import Data Pump là ORA-39405: source database có TSTZ version cao hơn target database. Data Pump không hỗ trợ import dữ liệu TSTZ theo chiều version đó khi target timezone file thấp hơn source trong các trường hợp bị giới hạn.

Thông điệp cụ thể phụ thuộc release, nhưng cách xử lý thường là chuẩn bị target timezone file version tương thích hoặc cao hơn trước khi import, theo quy trình DBMS_DST được hỗ trợ.

### 7.3. Vì sao không chỉ đổi DBTIMEZONE?

DBTIMEZONE không thay thế timezone file. Đổi DBTIMEZONE không nâng timezone rules version và không sửa compatibility của TSTZ data. Cần kiểm tra V$TIMEZONE_FILE và quy trình DBMS_DST.

### 7.4. TSTZ và TSLTZ trong migration

Kiểm kê các cột timestamp có timezone:

```sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length
FROM dba_tab_columns
WHERE data_type LIKE 'TIMESTAMP%TIME ZONE%'
ORDER BY owner, table_name, column_id;
```

Kiểm tra các table có dữ liệu TSTZ/TSLTZ bằng các data dictionary views liên quan như DBA_TSTZ_TABLES và DBA_TSTZ_TAB_COLS nếu release cung cấp. Không chỉ tìm tên cột có chữ DATE vì DATE không lưu timezone.

### 7.5. Tác động của timezone rule change

Khi timezone rules thay đổi, cùng một local timestamp/region có thể ánh xạ sang UTC instant khác so với version trước. Oracle cung cấp quy trình upgrade timezone data để xử lý các dữ liệu liên quan. Cần đánh giá affected rows, ambiguous/nonexistent local times và ứng dụng downstream.

## 8. Nâng timezone file bằng DBMS_DST

### 8.1. DBMS_DST là gì?

DBMS_DST là package hỗ trợ nâng cấp timezone data trong database. Quy trình có prepare window và upgrade window, cho phép đánh giá bảng/cột bị ảnh hưởng và thực hiện chuyển đổi theo quy trình Oracle.

### 8.2. Kiểm tra version hiện tại và version có sẵn

```sql
SELECT * FROM v$timezone_file;
```

Các timezone files có sẵn phụ thuộc Oracle Home và patch level. Không phải cứ cài Oracle Home mới là database đã chuyển sang timezone file version mới; database cần chạy quy trình upgrade tương ứng.

### 8.3. Kiểm tra trước upgrade

Oracle cung cấp script kiểm tra timezone upgrade trong thư mục admin của Oracle Home ở các release tương ứng, thường có tên:

```text
utltz_upg_check.sql
```

Script kiểm tra giúp xác định version mục tiêu, số lượng dữ liệu liên quan và các vấn đề cần xử lý. Xác nhận script chính xác trong Oracle Home của release đang dùng.

### 8.4. Prepare window

Ở giai đoạn prepare, DBA xác định version mục tiêu, mở prepare window và tìm các bảng/cột bị ảnh hưởng. Có thể sử dụng API như DBMS_DST.BEGIN_PREPARE, DBMS_DST.FIND_AFFECTED_TABLES và DBMS_DST.END_PREPARE theo quy trình phiên bản.

Kết quả cần được lưu lại để đánh giá trước khi vào upgrade window. Đặc biệt chú ý bảng lớn, TSTZ columns, error rows và thời gian cần thiết.

### 8.5. Upgrade window

Giai đoạn upgrade thực hiện nâng timezone version và cập nhật dữ liệu cần thiết. Oracle cung cấp script apply tương ứng, thường là:

```text
utltz_upg_apply.sql
```

Trong một số release, quy trình có các bước mở upgrade window, chạy UPGRADE_DATABASE, xử lý lỗi và đóng upgrade window qua DBMS_DST. Trạng thái database, open mode, CDB/PDB và downtime requirement phụ thuộc release.

### 8.6. Không sao chép ví dụ API thành runbook chung

Signature DBMS_DST và yêu cầu startup mode đã thay đổi giữa các release. Hãy dùng script và hướng dẫn chính thức đi kèm đúng Oracle Home, kiểm tra package specification và thực hiện trong maintenance window có backup/rollback. Không chạy BEGIN_UPGRADE hoặc UPGRADE_DATABASE trên production chỉ dựa vào một ví dụ rút gọn.

### 8.7. Xác minh sau upgrade

Sau khi hoàn tất:

```sql
SELECT * FROM v$timezone_file;
```

Kiểm tra trạng thái upgrade, error tables/logs do script tạo, DBA_TSTZ_TABLES và các ứng dụng dùng timezone region. Chạy test chuyển đổi timestamp quanh các thời điểm DST nếu nghiệp vụ có sử dụng.

### 8.8. CDB/PDB

Trong multitenant, timezone file version và quy trình upgrade có thể có điều kiện riêng ở CDB root và PDB. Thực hiện đúng container, kiểm tra trạng thái từng PDB và theo tài liệu của release. Không giả định một lần chạy script ở root tự động xử lý mọi container theo cùng cách.

## 9. Data Pump VERSION

### 9.1. VERSION là gì?

Tham số VERSION của Data Pump Export chỉ định phiên bản metadata mà Export tạo ra. Nó hỗ trợ xuất dữ liệu/metadata để import vào một release cũ hơn trong phạm vi tương thích mà Oracle hỗ trợ.

Ví dụ:

```text
expdp system@SRCDB schemas=APP directory=DP_DIR dumpfile=app_%U.dmp logfile=app_exp.log parallel=4 version=12.2
```

Giá trị VERSION phải là release đích được hỗ trợ và phù hợp với source. Ví dụ trên chỉ minh họa cú pháp; kiểm tra compatibility matrix của đúng source/target release trước khi chạy.

### 9.2. VERSION=COMPATIBLE

Nếu không chỉ định VERSION, Export thường dùng giá trị COMPATIBLE của database nguồn để quyết định mức metadata tương ứng. Có thể chỉ định rõ:

```text
expdp system@SRCDB schemas=APP directory=DP_DIR dumpfile=app.dmp logfile=app.log version=COMPATIBLE
```

### 9.3. VERSION chỉ điều khiển metadata

VERSION không:

- Thay đổi NLS_CHARACTERSET.
- Nâng hoặc hạ timezone file.
- Hạ COMPATIBLE của source.
- Chuyển đổi mọi datatype mới thành datatype cũ.
- Bảo đảm tính năng riêng của source có biểu diễn tương đương ở target.
- Làm cho mọi release cũ có thể đọc mọi dump file mới.

Nếu object sử dụng feature không tồn tại ở target release, object có thể không được export, metadata có thể bị biến đổi hoặc export/import có thể phát sinh lỗi tùy feature.

### 9.4. VERSION là tham số Export

VERSION là tham số của expdp. Không nhầm nó với tham số COMPATIBLE của database hoặc một tùy chọn nâng cấp target. Khi lập lệnh import, kiểm tra các tham số impdp riêng và compatibility của dump file.

### 9.5. Ví dụ export để import vào release cũ hơn

```text
expdp system@SRCDB \
  schemas=APP \
  directory=DP_DIR \
  dumpfile=app_legacy_%U.dmp \
  logfile=app_legacy_exp.log \
  parallel=4 \
  version=12.2
```

Lệnh minh họa trên shell kiểu Unix. Trong Windows CMD/PowerShell, cách xuống dòng khác nhau; có thể viết thành một dòng. Thay 12.2 bằng release đích thực tế được hỗ trợ.

### 9.6. Data Pump client/server version

Data Pump là công cụ server-based. Binary expdp/impdp client, database server source/target và dump file version đều có thể ảnh hưởng khả năng chạy. Dùng Data Pump client phù hợp với database server và tuân theo quy tắc interoperability của Oracle. Không suy luận tương thích chỉ từ việc lệnh expdp hiển thị version mới hơn.

## 10. COMPATIBLE parameter

### 10.1. Mục đích

COMPATIBLE là initialization parameter xác định mức tương thích tính năng mà database được phép sử dụng. Nó giúp Oracle duy trì khả năng tương thích cấu trúc và feature trong một số giai đoạn nâng cấp.

Kiểm tra:

```sql
SELECT name, value, isdefault, issys_modifiable
FROM v$parameter
WHERE name = 'compatible';
```

### 10.2. COMPATIBLE khác Oracle release

Ví dụ database chạy trên Oracle Home 19c nhưng COMPATIBLE có thể vẫn đặt ở mức thấp hơn. Database chưa nhất thiết sử dụng mọi feature mới của release cho tới khi parameter được nâng và các điều kiện khác được đáp ứng.

### 10.3. Tính chất không dễ đảo ngược

Nâng COMPATIBLE có thể cho phép Oracle sử dụng cấu trúc/feature không tương thích với release trước. Sau khi nâng và database đã sử dụng feature mới, không thể coi việc hạ lại giá trị parameter là downgrade được hỗ trợ.

Vì vậy, chỉ nâng COMPATIBLE sau khi:

- Hoàn tất upgrade phần mềm/database.
- Kiểm tra application và database components.
- Xác nhận không cần quay lại release cũ.
- Có backup và kế hoạch recovery.
- Đã review yêu cầu của feature/upgrade path.

### 10.4. COMPATIBLE và Data Pump VERSION

Hai tham số phục vụ hai mục tiêu:

- COMPATIBLE quyết định feature compatibility của database đang chạy.
- Data Pump VERSION quyết định mức metadata được ghi trong export dump.

Đặt VERSION thấp không làm COMPATIBLE của source thấp đi. Giữ COMPATIBLE thấp cũng không tự động làm mọi object export ra có metadata tương thích với target.

### 10.5. COMPATIBLE và source/target

Khi chuyển database sang target release mới hơn, target thường có thể sử dụng COMPATIBLE phù hợp với release sau khi hoàn tất upgrade và validation. Khi chuyển dữ liệu từ source mới về target cũ, cần kiểm tra COMPATIBLE source, feature sử dụng và VERSION export; không thể chỉ thay giá trị COMPATIBLE để tạo dump tương thích.

## 11. Compatibility matrix cho source và target

Trước migration, lập bảng ít nhất các mục sau:

| Hạng mục | Source | Target | Điều cần xác nhận |
|---|---|---|---|
| Oracle release | | | Đường migration/upgrade có hỗ trợ |
| COMPATIBLE | | | Feature và downgrade implications |
| NLS_CHARACTERSET | | | Target biểu diễn được dữ liệu source |
| NLS_NCHAR_CHARACTERSET | | | NCHAR/NVARCHAR2/NCLOB tương thích |
| Time zone file version | | | Target không thấp hơn mức cần cho TSTZ import |
| MAX_STRING_SIZE | | | Cột/metadata dùng extended strings |
| Database role/architecture | | | CDB/PDB, RAC, non-CDB |
| Platform/endian | | | Transportable tablespace có cần convert |
| Data Pump VERSION | | | Metadata export phù hợp target |
| Encryption/TDE | | | Wallet/keystore và quyền giải mã |
| Options/components | | | Spatial, XML DB, Java, Text, Partitioning... |
| Timezone semantics | | | Session/database/application timezone |
| Storage/LOB | | | SecureFiles, tablespace và capacity |

Không để trống các mục chưa biết. Đánh dấu rõ “chưa xác minh” và thực hiện kiểm tra trước khi lên lịch migration.

## 12. Quy trình kiểm kê source

### 12.1. Oracle release

```sql
SELECT banner
FROM v$version
ORDER BY banner;
```

Có thể kiểm tra thêm:

```sql
SELECT version, version_full, instance_name
FROM v$instance;
```

Cột version_full có thể không tồn tại ở một số release cũ.

### 12.2. Character sets

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
```

### 12.3. Timezone

```sql
SELECT * FROM v$timezone_file;

SELECT dbtimezone, sessiontimezone
FROM dual;
```

### 12.4. COMPATIBLE và MAX_STRING_SIZE

```sql
SELECT name, value
FROM v$parameter
WHERE name IN ('compatible', 'max_string_size');
```

### 12.5. Kiểm kê TSTZ/TSLTZ columns

```sql
SELECT owner,
       table_name,
       column_name,
       data_type
FROM dba_tab_columns
WHERE data_type LIKE 'TIMESTAMP%TIME ZONE%'
ORDER BY owner, table_name, column_id;
```

### 12.6. Kiểm kê character columns

```sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       char_length,
       char_used
FROM dba_tab_columns
WHERE data_type IN ('CHAR', 'VARCHAR2', 'NCHAR', 'NVARCHAR2')
ORDER BY owner, table_name, column_id;
```

### 12.7. Kiểm tra database components

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

Target cần có các component/option cần thiết cho object được import. Trạng thái INVALID hoặc component chưa được cài đặt có thể làm object compile thất bại.

## 13. Preflight character set conversion

### 13.1. Xác định ký tự không biểu diễn được

Đừng chỉ kiểm tra một vài hàng mẫu. Dùng DMU hoặc công cụ assessment phù hợp để phát hiện dữ liệu không biểu diễn được trong target charset, byte expansion và vấn đề column length.

### 13.2. Kiểm tra dữ liệu dài sát giới hạn

Các cột BYTE semantics có nguy cơ vượt giới hạn sau conversion sang charset dùng nhiều byte hơn. Tìm cột có DATA_LENGTH sát giới hạn và đo chiều dài byte của dữ liệu sau conversion trong môi trường thử nghiệm.

### 13.3. Kiểm tra ứng dụng

Kiểm thử:

- Insert/update Unicode từ ứng dụng.
- Đọc lại dữ liệu qua JDBC/OCI/ODP.NET và SQL*Plus.
- Search, sort, compare và index trên dữ liệu đa ngôn ngữ.
- Export/import dữ liệu LOB.
- Kết nối qua các client có NLS_LANG/encoding khác nhau.

### 13.4. Data cleansing

Nếu dữ liệu source chứa byte không hợp lệ hoặc ký tự đã bị lưu sai, conversion không thể tự suy ra ý định ban đầu. Cần làm sạch dữ liệu trước migration và ghi lại quy tắc chuyển đổi.

### 13.5. Không dùng NLS_LANG để sửa dữ liệu đã hỏng

NLS_LANG chỉ ảnh hưởng client conversion. Nếu byte đã lưu trong database sai charset, đổi NLS_LANG không khôi phục ký tự gốc. Cần assessment và repair dữ liệu có kiểm soát.

## 14. Preflight timezone compatibility

### 14.1. So sánh source và target

Chạy trên cả hai database:

```sql
SELECT filename, version
FROM v$timezone_file;
```

Ghi lại version. Nếu source version cao hơn target, đặc biệt khi dump có TSTZ data, xử lý timezone file target trước import theo hướng dẫn Oracle.

### 14.2. Kiểm tra TSTZ data

Liệt kê cột TSTZ/TSLTZ và xác định số lượng dữ liệu, kích thước bảng, ứng dụng phụ thuộc timezone region. Xác định thời gian upgrade và cách kiểm tra kết quả sau conversion.

### 14.3. Nâng timezone file trước import

Trong nhiều tình huống ORA-39405, giải pháp là nâng target timezone file version lên mức phù hợp với source trước khi chạy impdp. Thực hiện bằng DBMS_DST/scripts đúng release và kiểm thử trước.

### 14.4. Không hạ timezone file để khớp source

Không coi timezone file version thấp là một tùy chọn cấu hình có thể đổi tùy ý. Việc hạ version có thể không được hỗ trợ và có thể làm sai diễn giải timestamp. Ưu tiên nâng target lên version tương thích.

### 14.5. Timezone rule của ứng dụng

Ngay cả khi Data Pump import thành công, ứng dụng có thể hiển thị thời gian khác nếu session timezone, DBTIMEZONE hoặc timezone region assumptions thay đổi. Kiểm thử các mốc ngày quanh DST, midnight, month-end và business cutoff.

## 15. Data Pump migration giữa các release

### 15.1. Export và import cơ bản

Ví dụ export schema:

```text
expdp system@SRCDB \
  schemas=APP \
  directory=DP_DIR \
  dumpfile=app_%U.dmp \
  logfile=app_export.log \
  parallel=4
```

Ví dụ import vào target:

```text
impdp system@TGTDB \
  schemas=APP \
  directory=DP_DIR \
  dumpfile=app_%U.dmp \
  logfile=app_import.log \
  parallel=4
```

Directory object và file location phải được cấu hình trên database server tương ứng. Khi source/target khác host, dump file cần được chuyển qua kênh an toàn hoặc dùng phương thức Data Pump phù hợp.

### 15.2. Export với VERSION

```text
expdp system@SRCDB \
  schemas=APP \
  directory=DP_DIR \
  dumpfile=app_for_target.dmp \
  logfile=app_for_target.log \
  version=12.2
```

VERSION cần đặt theo release target được Oracle hỗ trợ. Đọc export log để phát hiện object/feature không tương thích.

### 15.3. SQLFILE để xem DDL

Trước khi import thật, có thể dùng SQLFILE của impdp để ghi DDL ra file:

```text
impdp system@TGTDB \
  schemas=APP \
  directory=DP_DIR \
  dumpfile=app_for_target.dmp \
  sqlfile=app_preview.sql \
  logfile=app_preview.log
```

SQLFILE hỗ trợ review DDL mà không thực thi các câu lệnh import thông thường. Nó không chứng minh dữ liệu sẽ import thành công; cần test import trên target clone.

### 15.4. Import thử trên schema khác

REMAP_SCHEMA và REMAP_TABLESPACE có thể giúp thử import vào schema/tablespace riêng:

```text
impdp system@TGTDB \
  schemas=APP \
  remap_schema=APP:APP_TEST \
  remap_tablespace=APP_DATA:APP_TEST_DATA \
  directory=DP_DIR \
  dumpfile=app_for_target.dmp \
  logfile=app_test_import.log
```

Đây là ví dụ; kiểm tra dependency, grants, synonym, directory, external tables và object references trước khi dùng.

### 15.5. VERSION không xử lý mọi feature mới

Nếu source sử dụng datatype, object metadata hoặc database feature không có ở target release, export/import có thể bỏ qua, biến đổi hoặc báo lỗi. Review Data Pump log, SQLFILE, invalid objects và application tests.

## 16. Compatibility theo hướng migration

### 16.1. Source cũ sang target mới

Đây là hướng phổ biến khi nâng cấp:

- Target thường hỗ trợ metadata của source cũ hơn, nhưng vẫn cần kiểm tra upgrade path và Data Pump compatibility.
- Character set target có thể là Unicode rộng hơn; kiểm tra conversion và column byte limits.
- Timezone file target có thể mới hơn; kiểm tra dữ liệu TSTZ và version compatibility.
- Kiểm tra component/option, datatype, MAX_STRING_SIZE, TDE và platform.

### 16.2. Source mới sang target cũ

Đây là hướng có nhiều hạn chế hơn:

- Dùng Data Pump VERSION trong phạm vi hỗ trợ.
- Không phải feature mới nào cũng có thể biểu diễn ở target.
- Source COMPATIBLE/feature usage có thể ngăn downgrade.
- Timezone file source cao hơn target có thể gây ORA-39405.
- Character set source Unicode sang target legacy có nguy cơ mất ký tự.
- Kiểm tra rõ downgrade/migration matrix của Oracle.

### 16.3. Cùng release nhưng khác timezone file

Hai database cùng release có thể được patch khác nhau và dùng timezone file version khác nhau. Không suy luận timezone compatibility chỉ từ 19c/21c; luôn truy vấn V$TIMEZONE_FILE.

### 16.4. Cùng release nhưng khác character set

Hai database cùng release vẫn có thể chuyển đổi dữ liệu không lossless. So sánh NLS_CHARACTERSET và NLS_NCHAR_CHARACTERSET, sau đó kiểm tra dữ liệu thật.

### 16.5. Cùng charset nhưng khác NLS settings

NLS_DATE_FORMAT, NLS_TIMESTAMP_FORMAT, NLS_SORT, NLS_COMP và session timezone có thể ảnh hưởng ứng dụng hoặc kết quả xử lý dù database charset giống nhau. Chuẩn hóa định dạng và bind datatype trong ứng dụng thay vì dựa vào NLS defaults.

## 17. Các phương pháp migration và giới hạn tương thích

### 17.1. Data Pump logical migration

Data Pump export/import chuyển object metadata và rows logic. Nó có thể chuyển đổi character data giữa database character sets và cho phép chọn VERSION cho metadata trong phạm vi hỗ trợ.

Data Pump không tự nâng timezone file target, không tự nâng COMPATIBLE và không tự cài mọi database option còn thiếu.

### 17.2. Transportable tablespaces

Transportable tablespaces di chuyển datafiles cùng metadata thay vì unload/reload toàn bộ rows. Cần kiểm tra:

- Source/target endian format.
- Character set compatibility theo quy định transportable.
- Database release và COMPATIBLE.
- Tablespace self-containment.
- TDE/encryption và wallet.
- Datafile version và platform support.

Nếu cross-platform endian khác nhau, có thể cần RMAN CONVERT hoặc quy trình convert datafile được hỗ trợ. Không coi Data Pump VERSION là công cụ đổi endian.

### 17.3. RMAN duplicate/restore

RMAN physical migration/duplicate có yêu cầu tương thích release, platform, endian, storage và backup format riêng. Character set và timezone file của database được giữ theo physical database; đây không phải logical character-set conversion.

### 17.4. Upgrade database

Upgrade trực tiếp database có đường đi và yêu cầu riêng với Data Pump. Kiểm tra upgrade path, preupgrade checks, component status, COMPATIBLE và timezone file. Không dùng Data Pump VERSION thay cho database upgrade.

### 17.5. Heterogeneous migration

Khi chuyển từ non-Oracle sang Oracle hoặc ngược lại, character mapping, datatype mapping, timezone semantics và collation có thể khác. Cần mapping specification, conversion tests và reconciliation theo business key.

## 18. Các lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| ORA-39405 | Source TSTZ version cao hơn target | Kiểm tra V$TIMEZONE_FILE, nâng target timezone file theo DBMS_DST |
| ORA-02374 | Lỗi conversion khi load dữ liệu | Xem import log, charset, row/column và dữ liệu nguồn |
| ORA-12899 sau conversion | Giá trị vượt giới hạn cột sau đổi encoding | Kiểm tra BYTE/CHAR semantics và thiết kế cột |
| Ký tự thành dấu hỏi hoặc sai glyph | Target charset không biểu diễn được hoặc client encoding sai | Phân biệt database conversion và NLS_LANG |
| Import không hỗ trợ object metadata | Target release thấp hơn feature source | Kiểm tra Data Pump VERSION và feature compatibility |
| Dump file không đọc được | Data Pump dump format/client/server version không tương thích | Dùng Data Pump version/path được hỗ trợ |
| TSTZ hiển thị khác sau migration | Timezone rules/session timezone khác | So sánh timezone file, DBTIMEZONE, SESSIONTIMEZONE |
| Dữ liệu DATE/TIMESTAMP lệch giờ | Ứng dụng giả định timezone không được lưu | Xác định quy ước lưu và chuyển đổi application |
| Object INVALID sau import | Component/feature/privilege thiếu | Kiểm tra DBA_REGISTRY, grants và compile errors |
| Transportable import thất bại | Endian, self-containment, tablespace hoặc version mismatch | Kiểm tra transportable compatibility và RMAN CONVERT nếu cần |

## 19. Kịch bản migration mẫu

Giả sử source Oracle 19c dùng AL32UTF8 và timezone file version 42; target Oracle 19c mới cài có database character set AL32UTF8 nhưng timezone file version 32. Schema APP có nhiều cột TSTZ.

### Bước 1 — Kiểm kê source và target

Chạy các truy vấn về Oracle release, COMPATIBLE, character sets, timezone file, MAX_STRING_SIZE và DBA_REGISTRY trên cả hai database.

### Bước 2 — Xác định incompatibility

Character set source/target giống nhau, nhưng timezone file target thấp hơn source. Data Pump import có thể báo ORA-39405 khi gặp dữ liệu TSTZ.

### Bước 3 — Lập kế hoạch timezone upgrade

Kiểm tra timezone file mới có sẵn trong target Oracle Home. Chạy precheck bằng script tương ứng, đánh giá affected tables, chuẩn bị backup và maintenance window.

### Bước 4 — Nâng timezone file target

Thực hiện quy trình DBMS_DST/scripts đúng release. Xác minh V$TIMEZONE_FILE và dữ liệu TSTZ sau upgrade.

### Bước 5 — Export schema

Dùng expdp với VERSION phù hợp nếu target cần metadata tương thích release cụ thể. Lưu dump/log và checksum.

### Bước 6 — Import thử

Dùng impdp trên target clone. Review SQLFILE, import log, conversion warnings và invalid objects.

### Bước 7 — Reconciliation

So sánh row counts, business totals, LOB counts, character samples, timestamp samples và sequence/identity behavior.

### Bước 8 — Cutover

Chốt thời điểm freeze source, export delta/final, import, validate ứng dụng, cập nhật connection/service và giữ rollback plan theo thời hạn đã thống nhất.

Ví dụ này chỉ minh họa thứ tự xử lý. Version cụ thể và script timezone phải dựa trên Oracle Home thật.

## 20. Kiểm tra sau import

### 20.1. Character set

Xác nhận target NLS_CHARACTERSET và NLS_NCHAR_CHARACTERSET đúng với thiết kế. Kiểm tra các chuỗi đa ngôn ngữ qua ứng dụng thực tế.

### 20.2. Timezone file

```sql
SELECT * FROM v$timezone_file;
SELECT dbtimezone, sessiontimezone FROM dual;
```

Kiểm tra timestamp samples quanh DST/offset changes nếu nghiệp vụ dùng timezone region.

### 20.3. Object và component

```sql
SELECT owner, object_type, status, COUNT(*)
FROM dba_objects
WHERE owner = 'APP'
GROUP BY owner, object_type, status
ORDER BY object_type, status;

SELECT comp_id, comp_name, version, status
FROM dba_registry
ORDER BY comp_id;
```

### 20.4. Data validation

So sánh row counts theo bảng, tổng tiền/số lượng theo business key, dữ liệu LOB, null counts và các cột quan trọng. Row count giống nhau không chứng minh ký tự hoặc timestamp được chuyển đúng.

### 20.5. Application validation

Kiểm thử:

- Login/session timezone.
- Insert/update Unicode.
- Search/sort/collation.
- Timestamp conversion giữa các múi giờ.
- Batch jobs, Scheduler và Data Guard nếu có.
- Report theo ngày nghiệp vụ và cutoff.
- API/client encoding.

### 20.6. Hiệu năng sau migration

Character set, index, collation, data length và storage có thể ảnh hưởng dung lượng/index size. Sau cutover, theo dõi SQL plans, buffer gets, I/O, CPU và latency.

## 21. Checklist trước khi bắt đầu migration

- [ ] Đã ghi nhận Oracle release và patch level của source/target.
- [ ] Đã kiểm tra COMPATIBLE trên cả hai database.
- [ ] Đã kiểm tra NLS_CHARACTERSET.
- [ ] Đã kiểm tra NLS_NCHAR_CHARACTERSET.
- [ ] Đã xác định client encoding/NLS_LANG của các ứng dụng.
- [ ] Đã kiểm kê cột BYTE/CHAR semantics và các cột sát giới hạn.
- [ ] Đã đánh giá Unicode conversion bằng DMU/công cụ phù hợp.
- [ ] Đã kiểm tra CLOB/NCLOB và dữ liệu đa ngôn ngữ.
- [ ] Đã so sánh V$TIMEZONE_FILE source/target.
- [ ] Đã kiểm kê TSTZ/TSLTZ columns.
- [ ] Đã lập kế hoạch DBMS_DST nếu cần nâng timezone file.
- [ ] Đã kiểm tra Data Pump VERSION và release compatibility.
- [ ] Đã review feature/type không tồn tại ở target.
- [ ] Đã kiểm tra MAX_STRING_SIZE và database components.
- [ ] Đã kiểm tra platform/endian nếu dùng transportable tablespaces/RMAN.
- [ ] Đã kiểm tra TDE/wallet và encryption dependencies.
- [ ] Đã chạy export/import thử trên môi trường đại diện.
- [ ] Đã kiểm tra logs, warnings và invalid objects.
- [ ] Đã xác định RPO/RTO và rollback strategy.
- [ ] Đã chuẩn bị data reconciliation và application test.

## 22. Câu hỏi tự kiểm tra

1. NLS_CHARACTERSET và NLS_NCHAR_CHARACTERSET khác nhau ở đâu?
2. CHAR/VARCHAR2/CLOB sử dụng character set nào?
3. NCHAR/NVARCHAR2/NCLOB sử dụng character set nào?
4. AL32UTF8 khác UTF8 legacy của Oracle như thế nào?
5. Character set superset có ý nghĩa gì khi migration?
6. NLS_LANG ảnh hưởng client conversion ra sao?
7. Vì sao NLS_LANG không đổi database character set?
8. Data Pump conversion có thể mất dữ liệu trong trường hợp nào?
9. BYTE semantics và CHAR semantics khác nhau thế nào?
10. Vì sao chuyển sang AL32UTF8 có thể làm cột BYTE semantics vượt giới hạn?
11. DMU hỗ trợ nhiệm vụ nào?
12. Vì sao không nên chạy ALTER DATABASE CHARACTER SET như cách sửa nhanh?
13. Time zone file chứa thông tin gì?
14. V$TIMEZONE_FILE cho biết điều gì?
15. DBTIMEZONE khác SESSIONTIMEZONE ra sao?
16. TIMESTAMP WITH TIME ZONE khác TIMESTAMP WITH LOCAL TIME ZONE như thế nào?
17. Vì sao timezone region quan trọng khi có DST?
18. ORA-39405 thường liên quan đến khác biệt nào giữa source và target?
19. Vì sao đổi DBTIMEZONE không giải quyết timezone file version mismatch?
20. DBMS_DST và các script utltz_upg_* được dùng trong công việc nào?
21. Vì sao cần prepare window trước timezone upgrade?
22. Data Pump VERSION có nhiệm vụ gì?
23. VERSION=COMPATIBLE khác VERSION=12.2 như thế nào?
24. Vì sao VERSION thấp không bảo đảm mọi object source có thể import?
25. COMPATIBLE khác Oracle release ra sao?
26. Vì sao nâng COMPATIBLE cần thận trọng với downgrade?
27. Cần so sánh những hạng mục nào trong source-target compatibility matrix?
28. Transportable tablespaces cần kiểm tra endian và điều kiện gì?
29. Vì sao Data Pump import thành công chưa chứng minh dữ liệu đúng?
30. Những test nào cần chạy sau migration để xác nhận charset và timezone?

**Nguyên tắc cần nhớ:** Trước migration, so sánh riêng Oracle release, COMPATIBLE, Data Pump VERSION, database/national character sets và timezone file version. AL32UTF8 là Unicode UTF-8 chuẩn của Oracle; NLS_LANG chỉ điều khiển client conversion. Time zone file version khác DBTIMEZONE và SESSIONTIMEZONE; source có version cao hơn target có thể gây ORA-39405 khi import TSTZ. Data Pump VERSION chỉ điều khiển metadata export trong phạm vi được hỗ trợ. Hãy kiểm kê dữ liệu, đánh giá conversion, nâng timezone file theo DBMS_DST khi cần, thử import trên target clone và xác nhận dữ liệu bằng cả kỹ thuật lẫn nghiệp vụ.
