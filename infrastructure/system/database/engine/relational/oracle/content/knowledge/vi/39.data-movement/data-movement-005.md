# INCLUDE, EXCLUDE, QUERY và chọn phạm vi dữ liệu

Oracle Data Pump là công cụ xuất và nhập dữ liệu của Oracle Database, thường được gọi bằng **expdp** và **impdp**. Một job Data Pump có thể xử lý toàn bộ database, một hoặc nhiều schema, một nhóm table, một tablespace hoặc một tập đối tượng được chọn. Ngoài việc chọn đối tượng, Data Pump còn có thể kiểm soát metadata nào được xuất/nhập và, trong lúc export, những dòng dữ liệu nào được đưa vào dump file.

Bốn cơ chế cần phân biệt:

- **Chọn mode/phạm vi job** bằng các tham số như `FULL`, `SCHEMAS`, `TABLES`, `TABLESPACES` hoặc `TRANSPORT_TABLESPACES`. Đây là bước xác định tập dữ liệu ban đầu mà job sẽ xem xét.
- **INCLUDE** chỉ định các loại đối tượng hoặc đối tượng cụ thể được đưa vào job. Đây là bộ lọc metadata.
- **EXCLUDE** loại các loại đối tượng hoặc đối tượng cụ thể khỏi job. Đây cũng là bộ lọc metadata.
- **QUERY** lọc các dòng của table trong Data Pump Export bằng điều kiện SQL. Nó quyết định dòng nào được ghi vào dump file, không quyết định loại metadata nào được chọn.

Hiểu đúng thứ tự và phạm vi của các cơ chế này giúp tạo dump file đúng mục đích, giảm dung lượng, rút ngắn thời gian export/import và tránh bỏ sót đối tượng phụ thuộc.

## 1. Chọn phạm vi job trước khi lọc đối tượng

Data Pump có nhiều chế độ export/import. Mode xác định tập đối tượng ban đầu; INCLUDE và EXCLUDE tiếp tục thu hẹp tập metadata bên trong phạm vi đó.

| Mode | Tham số | Phạm vi |
|---|---|---|
| Full database | `FULL=YES` | Các đối tượng thuộc phạm vi full export/import mà tài khoản có quyền xử lý |
| Schema | `SCHEMAS=HR,SALES` | Đối tượng thuộc các schema được chỉ định |
| Table | `TABLES=HR.EMPLOYEES,HR.DEPARTMENTS` | Các bảng được chỉ định, cùng metadata và dữ liệu liên quan theo job |
| Tablespace | `TABLESPACES=USERS,APP_DATA` | Đối tượng thuộc các tablespace được chỉ định theo quy tắc Data Pump |
| Transportable tablespace | `TRANSPORT_TABLESPACES=...` | Di chuyển tập tablespace theo cơ chế transportable |

Các tham số mode thể hiện các cách xác định phạm vi khác nhau. Một job không kết hợp tùy ý `FULL`, `SCHEMAS` và `TABLES` như các bộ lọc độc lập. Hãy chọn mode đúng với mục tiêu trước khi thêm các filter.

Ví dụ export một schema:

~~~text
SCHEMAS=HR
~~~

Export hai bảng:

~~~text
TABLES=HR.EMPLOYEES,HR.DEPARTMENTS
~~~

Export toàn database:

~~~text
FULL=YES
~~~

Full export cần quyền thích hợp, thường là quyền Data Pump full database như `DATAPUMP_EXP_FULL_DATABASE`. Quyền thực tế còn phụ thuộc đối tượng và phiên bản. Không nên mặc định tài khoản schema owner có thể export full database.

### Phạm vi đối tượng và phạm vi dòng dữ liệu

Chọn `TABLES=HR.ORDERS` nghĩa là job xử lý bảng ORDERS trong schema HR. Điều đó không tự động giới hạn dòng dữ liệu theo ngày hoặc trạng thái. Nếu cần chỉ lấy một phần dòng, cần cơ chế row filter như QUERY trong export.

Ngược lại, `QUERY` không tự chọn thêm schema hoặc bảng. Nó chỉ áp dụng cho table data trong phạm vi job đã chọn. Hãy xác định mode trước, sau đó mới dùng INCLUDE/EXCLUDE và QUERY khi phù hợp.

## 2. INCLUDE: chỉ đưa các đối tượng được chọn vào job

`INCLUDE` dùng để giới hạn các object type hoặc tên đối tượng được đưa vào job. Tên object type phải là object path hợp lệ trong mode đang chạy.

Ví dụ schema export chỉ đưa các table có tên bắt đầu bằng EMP:

~~~text
SCHEMAS=HR
INCLUDE=TABLE:"LIKE 'EMP%'"
~~~

Ví dụ schema export chỉ lấy hai table:

~~~text
SCHEMAS=HR
INCLUDE=TABLE:"IN ('EMPLOYEES','DEPARTMENTS')"
~~~

Ví dụ trên lọc metadata theo object path TABLE và tên table. Các object path có thể dùng được phụ thuộc mode và phiên bản Oracle.

### INCLUDE lọc object type như thế nào?

Nếu chỉ định:

~~~text
INCLUDE=TABLE
~~~

Data Pump đưa các table vào job. Những metadata phụ thuộc cần thiết của đối tượng được chọn có thể được đưa vào theo quy tắc dependency của Data Pump, ví dụ các thành phần cần thiết để tạo table. Vì vậy, không nên hiểu INCLUDE là danh sách file độc lập chỉ chứa đúng một loại dòng metadata.

Nếu muốn kiểm soát thêm các object type, có thể chỉ định nhiều INCLUDE filter trong parameter file, ví dụ:

~~~text
SCHEMAS=HR
INCLUDE=TABLE
INCLUDE=VIEW
INCLUDE=PROCEDURE
~~~

Các filter INCLUDE có thể được dùng để chỉ rõ tập object type cần xử lý. Tuy nhiên, dependency của đối tượng vẫn có thể ảnh hưởng đến metadata xuất/nhập. Khi thiết kế job chỉ lấy một số loại đối tượng, hãy xem log và kiểm tra dump bằng SQLFILE trước khi import vào hệ thống đích.

### INCLUDE theo tên đối tượng

Có thể dùng biểu thức tên như `LIKE` hoặc `IN` trong object filter:

~~~text
SCHEMAS=HR
INCLUDE=TABLE:"LIKE 'EMP%'"
~~~

~~~text
SCHEMAS=HR
INCLUDE=TABLE:"IN ('EMPLOYEES','DEPARTMENTS')"
~~~

Đối với object name không đặt trong dấu nháy kép khi tạo trong Oracle, tên thường được lưu ở dạng chữ hoa. Biểu thức lọc cần khớp với cách tên được lưu trong data dictionary. Với tên có phân biệt chữ hoa/thường do được tạo bằng quoted identifier, hãy kiểm tra tên thực tế trước khi viết filter.

## 3. EXCLUDE: loại đối tượng khỏi job

`EXCLUDE` loại một object type hoặc các đối tượng cụ thể ra khỏi job. Cơ chế này hữu ích khi cần export/import gần như toàn bộ phạm vi nhưng bỏ qua một số đối tượng không cần thiết.

Ví dụ schema export nhưng bỏ qua các table audit và staging:

~~~text
SCHEMAS=HR
EXCLUDE=TABLE:"IN ('AUDIT_LOG','TEMP_STAGE')"
~~~

Ví dụ export schema nhưng loại statistics metadata:

~~~text
SCHEMAS=HR
EXCLUDE=STATISTICS
~~~

Tên object path phải hợp lệ trong mode tương ứng. Không phải mọi object type đều có thể được lọc trong mọi mode.

### EXCLUDE và dependency

Khi loại một đối tượng, Data Pump có thể loại cả metadata phụ thuộc vào đối tượng đó. Ví dụ, nếu loại một table, các object phụ thuộc vào table có thể không được đưa vào job theo dependency rules. Điều này có thể ảnh hưởng đến index, constraint, trigger, grant hoặc metadata liên quan.

Vì vậy, nếu cần bỏ riêng một loại metadata nhưng vẫn giữ table, hãy chọn object path cụ thể phù hợp và kiểm tra kết quả. Không nên mặc định rằng loại một object path sẽ không ảnh hưởng đến các thành phần phụ thuộc.

### INCLUDE và EXCLUDE không dùng chung trong một job

Một job Data Pump không cho phép chỉ định đồng thời INCLUDE và EXCLUDE. Hãy chọn một chiến lược:

- Dùng INCLUDE khi muốn xác định rõ những loại đối tượng cần xử lý.
- Dùng EXCLUDE khi muốn xử lý phạm vi rộng rồi loại một số đối tượng không cần thiết.

Ví dụ, nếu mục tiêu là export schema HR nhưng bỏ bảng audit, dùng SCHEMAS kết hợp EXCLUDE. Nếu mục tiêu là chỉ export table, view và procedure, dùng SCHEMAS kết hợp INCLUDE.

## 4. Object path và cách tìm tên filter hợp lệ

Tên object type trong INCLUDE/EXCLUDE là object path của Data Pump. Chúng không phải lúc nào cũng trùng với tên loại đối tượng quen thuộc trong câu SQL. Một số object path có tên riêng hoặc phân cấp theo loại export.

Oracle cung cấp các view mô tả object path theo mode:

- `DATABASE_EXPORT_OBJECTS`: object path có thể dùng trong full database export/import.
- `SCHEMA_EXPORT_OBJECTS`: object path có thể dùng trong schema mode.
- `TABLE_EXPORT_OBJECTS`: object path có thể dùng trong table mode.

Có thể tra cứu danh sách object path trong database:

~~~sql
SELECT object_path,
       comments
FROM   schema_export_objects
ORDER BY object_path;
~~~

Với full export:

~~~sql
SELECT object_path,
       comments
FROM   database_export_objects
ORDER BY object_path;
~~~

Với table mode:

~~~sql
SELECT object_path,
       comments
FROM   table_export_objects
ORDER BY object_path;
~~~

Các view này giúp xác định đúng tên object path và mô tả của chúng trong phiên bản hiện tại. Nếu tài khoản không truy cập được view, DBA có thể cấp quyền đọc phù hợp hoặc thực hiện truy vấn bằng tài khoản quản trị.

Không nên đoán object path từ tên dictionary view như DBA_TABLES hoặc DBA_INDEXES. Hãy dùng danh sách object path của Data Pump để tránh lỗi filter không hợp lệ.

## 5. QUERY: lọc dòng dữ liệu khi export

`QUERY` cho phép Data Pump Export chọn một tập dòng của table bằng điều kiện SQL. Nó tác động đến table data; metadata của table vẫn được xử lý theo mode và các filter khác.

Ví dụ chỉ export các đơn hàng đang mở:

~~~text
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN'"
~~~

Ví dụ lọc theo ngày:

~~~text
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE ORDER_DATE >= DATE '2026-01-01'"
~~~

Ví dụ kết hợp nhiều điều kiện:

~~~text
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN' AND ORDER_DATE >= DATE '2026-01-01'"
~~~

Cú pháp tổng quát:

~~~text
QUERY=[schema.][table_name:] query_clause
~~~

Trong đó `query_clause` thường là một mệnh đề WHERE hợp lệ. Với table-specific query, hãy ghi rõ table name; khi làm việc với nhiều schema, ghi cả schema để tránh nhầm tên. QUERY là tham số của Data Pump Export (`expdp`); không dùng nó như filter object metadata trong Import.

### QUERY không thay thế TABLES hoặc SCHEMAS

`QUERY` không xác định phạm vi đối tượng. Ví dụ:

~~~text
SCHEMAS=HR
QUERY=ORDERS:"WHERE STATUS = 'OPEN'"
~~~

Mục đích của job vẫn là schema export. QUERY chỉ lọc dữ liệu của table được chỉ định theo cú pháp và điều kiện áp dụng; các table khác trong schema không tự biến mất chỉ vì không có QUERY riêng.

Đối với ví dụ đơn giản, nên dùng TABLES mode để giới hạn rõ table cần lọc:

~~~text
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN'"
~~~

Điều này giúp job dễ hiểu, dễ kiểm tra và giảm rủi ro vô tình export thêm các table không cần thiết.

### QUERY lọc dòng, không lọc cột

QUERY là điều kiện chọn dòng. Ví dụ:

~~~text
QUERY=ORDERS:"WHERE STATUS = 'OPEN'"
~~~

sẽ chọn các dòng có STATUS là OPEN, nhưng vẫn export các cột của table theo cấu trúc table. Nếu cần bỏ cột hoặc thay đổi cấu trúc dữ liệu, cần thiết kế cách xử lý khác như view, table staging, REMAP_DATA hoặc thao tác SQL sau khi import.

### Điều kiện SQL và kiểu dữ liệu

Điều kiện QUERY phải hợp lệ với table và database nguồn. Cần chú ý:

- Dùng literal đúng kiểu dữ liệu, ví dụ DATE literal thay cho chuỗi ngày phụ thuộc NLS.
- Dùng tên cột đúng với table và cách đặt tên identifier.
- Kiểm tra NULL semantics khi dùng điều kiện so sánh.
- Với điều kiện có nhiều toán tử, đặt ngoặc để thể hiện rõ thứ tự logic.
- Nếu dùng hàm hoặc biểu thức, xác nhận biểu thức chạy được trên database nguồn.
- Không đưa dữ liệu người dùng chưa được kiểm soát vào câu QUERY được ghép động.

Ví dụ điều kiện ngày an toàn hơn:

~~~text
QUERY=ORDERS:"WHERE ORDER_DATE >= DATE '2026-01-01' AND ORDER_DATE < DATE '2027-01-01'"
~~~

Điều kiện trên tạo khoảng ngày nửa mở, phù hợp với cột DATE có thể chứa cả phần giờ.

## 6. Phân biệt INCLUDE, EXCLUDE và QUERY

| Tiêu chí | INCLUDE | EXCLUDE | QUERY |
|---|---|---|---|
| Đối tượng tác động | Object type hoặc object name | Object type hoặc object name | Các dòng table data |
| Mục đích | Chỉ chọn những metadata cần thiết | Loại metadata không cần thiết | Lấy một phần dòng theo điều kiện |
| Dùng trong | Data Pump Export và Import | Data Pump Export và Import | Data Pump Export |
| Ví dụ | `INCLUDE=TABLE` | `EXCLUDE=STATISTICS` | `QUERY=ORDERS:"WHERE STATUS='OPEN'"` |
| Thay đổi cấu trúc metadata? | Có thể giới hạn metadata được xử lý | Có thể loại metadata khỏi job | Không; chỉ lọc dòng được export |
| Kết hợp với mode? | Có | Có | Có, trong những mode/phạm vi được hỗ trợ |

Một cách ghi nhớ:

- Mode trả lời: **job xem xét vùng dữ liệu nào?**
- INCLUDE/EXCLUDE trả lời: **metadata object nào được xử lý?**
- QUERY trả lời: **những dòng nào của table được export?**
- CONTENT trả lời: **job xử lý metadata, table data hay cả hai?**

## 7. CONTENT và các tham số chọn phạm vi liên quan

`CONTENT` điều khiển loại nội dung được Data Pump Export/Import xử lý:

| CONTENT | Ý nghĩa |
|---|---|
| ALL | Metadata và table data |
| METADATA_ONLY | Metadata, không export table rows |
| DATA_ONLY | Table data, không export metadata |

Ví dụ export chỉ metadata của một schema:

~~~text
SCHEMAS=HR
CONTENT=METADATA_ONLY
~~~

Ví dụ export chỉ dữ liệu của một table:

~~~text
TABLES=HR.ORDERS
CONTENT=DATA_ONLY
~~~

`CONTENT=DATA_ONLY` không tự lọc dòng. Nếu cần subset rows, dùng QUERY trong export khi mode và cấu hình hỗ trợ. Tương tự, `CONTENT=METADATA_ONLY` không có nghĩa là chỉ lấy một số cột; nó loại table data khỏi job.

### TABLES và partition

Trong table mode, có thể chỉ định partition hoặc subpartition theo cú pháp Data Pump. Ví dụ:

~~~text
TABLES=SH.SALES:SALES_Q1_2026
~~~

Cách chọn partition hữu ích khi cần di chuyển dữ liệu theo kỳ hoặc chia nhỏ job. Cần xác nhận tên partition tồn tại, quyền truy cập và cú pháp được phiên bản hỗ trợ.

Chọn partition và dùng QUERY là hai mức khác nhau: partition xác định vùng dữ liệu vật lý/logical được xử lý; QUERY lọc các dòng trong phạm vi table data được export. Hãy kiểm tra điều kiện kết hợp cụ thể trong phiên bản Oracle đang dùng.

## 8. Ví dụ thực tế: export một tập table với INCLUDE

Giả sử cần export schema HR nhưng chỉ muốn table và view thuộc phạm vi. Có thể dùng parameter file:

**hr_objects.par**

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_objects_%U.dmp
LOGFILE=hr_objects.log
SCHEMAS=HR
INCLUDE=TABLE
INCLUDE=VIEW
PARALLEL=2
METRICS=YES
~~~

Chạy:

~~~bash
expdp system@ORCL PARFILE=hr_objects.par
~~~

Job chỉ định schema HR và các object path được INCLUDE. Những metadata phụ thuộc cần thiết có thể được xử lý theo dependency rules. Hãy xem log để xác nhận số object được xử lý và dùng SQLFILE nếu cần xem DDL trước khi import.

## 9. Ví dụ thực tế: export schema nhưng loại table không cần

Giả sử schema HR có các bảng nghiệp vụ và bảng tạm/audit. Cần export toàn schema ngoại trừ hai bảng không cần di chuyển.

**hr_without_audit.par**

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_clean_%U.dmp
LOGFILE=hr_clean.log
SCHEMAS=HR
EXCLUDE=TABLE:"IN ('AUDIT_LOG','TEMP_STAGE')"
PARALLEL=2
METRICS=YES
~~~

Chạy:

~~~bash
expdp system@ORCL PARFILE=hr_without_audit.par
~~~

Khi EXCLUDE một table, cần lưu ý các object phụ thuộc có thể bị loại theo dependency rules. Sau export, xem log và nội dung DDL dự kiến để chắc chắn các object còn lại vẫn phù hợp với yêu cầu triển khai.

## 10. Ví dụ thực tế: export một phần dòng của table

Giả sử chỉ cần đưa các đơn hàng đang OPEN từ đầu năm 2026 vào hệ thống báo cáo.

**orders_open.par**

~~~text
DIRECTORY=DP_DIR
DUMPFILE=orders_open_%U.dmp
LOGFILE=orders_open.log
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN' AND ORDER_DATE >= DATE '2026-01-01'"
PARALLEL=2
METRICS=YES
~~~

Chạy:

~~~bash
expdp system@ORCL PARFILE=orders_open.par
~~~

Khi import dump file, Data Pump tạo hoặc nạp table theo nội dung dump. Các dòng được export chính là tập dòng thỏa mãn điều kiện QUERY. Metadata table không tự thay đổi thành một view có điều kiện; đây là một bản export dữ liệu con của table.

Nếu cần xuất nhiều tập điều kiện khác nhau, có thể tạo các job export riêng hoặc thiết kế quy trình staging phù hợp. Không nên cố ghép nhiều điều kiện khác nhau vào một QUERY không được kiểm tra cú pháp.

## 11. Import và tác động của INCLUDE/EXCLUDE

Data Pump Import (`impdp`) cũng hỗ trợ INCLUDE và EXCLUDE để chọn metadata được nhập từ dump file. Phạm vi import ban đầu được xác định bằng FULL, SCHEMAS, TABLES hoặc mode tương ứng; sau đó filter giới hạn đối tượng được tạo hoặc xử lý.

Ví dụ import một schema nhưng chỉ tạo table và view:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_objects_%U.dmp
LOGFILE=hr_import.log
SCHEMAS=HR
INCLUDE=TABLE
INCLUDE=VIEW
~~~

Ví dụ import schema nhưng loại một table:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_full_%U.dmp
LOGFILE=hr_import_no_audit.log
SCHEMAS=HR
EXCLUDE=TABLE:"IN ('AUDIT_LOG','TEMP_STAGE')"
~~~

Khi import, INCLUDE/EXCLUDE kiểm soát object metadata trong dump. Nếu dump đã được export với QUERY, các dòng đã bị lọc ở bước export sẽ không tự xuất hiện trở lại khi import.

QUERY là cơ chế lọc dòng của Export. Nếu cần chỉ import một tập dòng khác với tập dòng đã có trong dump, hãy thiết kế bước xử lý dữ liệu riêng, chẳng hạn import vào schema staging rồi dùng INSERT ... SELECT với WHERE, hoặc tạo dump đã lọc đúng từ nguồn.

### Kiểm tra DDL trước khi import bằng SQLFILE

Có thể tạo file SQL chứa DDL Data Pump dự kiến thực thi:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=hr_objects.dmp
SQLFILE=hr_preview.sql
SCHEMAS=HR
~~~

Chạy:

~~~bash
impdp system@ORCL PARFILE=preview.par
~~~

SQLFILE giúp xem các lệnh DDL được tạo từ dump và filter hiện tại. Nó không thực thi các lệnh DDL đó và không thay thế kiểm tra nội dung table data. Đây là cách hữu ích để xác nhận object scope trước khi import vào database đích.

## 12. Cách kết hợp các filter mà không nhầm phạm vi

Có thể hình dung phạm vi Data Pump theo các lớp:

~~~text
Mode / Job scope
(FULL, SCHEMAS, TABLES, TABLESPACES)
          |
          v
Metadata filters
(INCLUDE hoặc EXCLUDE)
          |
          v
Các object được chọn và dependency
          |
          v
Table data
(CONTENT và QUERY ở Export)
          |
          v
Dump file / Import target
~~~

Ví dụ mục tiêu là export table ORDERS, chỉ lấy metadata cần thiết và chỉ lấy đơn hàng OPEN:

1. Chọn TABLES mode với HR.ORDERS.
2. Nếu cần lọc object type, dùng INCLUDE hoặc EXCLUDE phù hợp.
3. Dùng QUERY để chọn các dòng STATUS = 'OPEN'.
4. Chọn CONTENT=ALL nếu cần cả metadata và data.
5. Kiểm tra log, dump và DDL trước khi import.

Không nên dùng EXCLUDE để giải quyết bài toán lọc dòng, hoặc dùng QUERY để loại index/trigger. Hai loại filter hoạt động trên các lớp khác nhau.

## 13. Quoting và parameter file

Các biểu thức INCLUDE, EXCLUDE và QUERY thường chứa dấu nháy kép, dấu nháy đơn, dấu phẩy và ký tự đặc biệt. Cách shell xử lý dấu nháy khác nhau giữa Linux/Unix và Windows. Vì vậy, parameter file thường dễ kiểm soát hơn việc truyền toàn bộ filter trực tiếp trên command line.

Ví dụ parameter file:

~~~text
DIRECTORY=DP_DIR
DUMPFILE=orders_%U.dmp
LOGFILE=orders.log
TABLES=HR.ORDERS
QUERY=ORDERS:"WHERE STATUS = 'OPEN' AND AMOUNT >= 1000"
~~~

Sau đó gọi:

~~~bash
expdp system@ORCL PARFILE=orders.par
~~~

Một số lưu ý:

- Dùng dấu nháy kép bên ngoài biểu thức filter để giữ nguyên chuỗi điều kiện.
- Dùng dấu nháy đơn cho literal SQL bên trong.
- Nếu điều kiện có dấu nháy đơn trong giá trị, cần escape theo cú pháp SQL.
- Không tự ý thêm dấu chấm phẩy vào cuối giá trị QUERY nếu nó làm thay đổi chuỗi WHERE.
- Trên Windows, PowerShell và Command Prompt có quy tắc quoting khác nhau; hãy kiểm thử bằng parameter file.
- Bảo vệ parameter file nếu có thông tin xác thực. Tốt hơn là dùng Oracle Wallet hoặc cơ chế xác thực phù hợp thay vì ghi password dạng rõ trong file.

## 14. Xác minh phạm vi export/import

Không nên chỉ dựa vào việc job kết thúc với trạng thái thành công. Hãy kiểm tra phạm vi đối tượng và số dòng thực tế.

### Đọc log Data Pump

Bật METRICS để có thêm thông tin số lượng object và thời gian xử lý:

~~~text
METRICS=YES
LOGTIME=ALL
~~~

Log cho biết object được xử lý, lỗi, cảnh báo và tiến trình job. Khi filter không khớp object path hoặc tên đối tượng, log thường là nơi đầu tiên để nhận biết phạm vi thực tế khác dự kiến.

### Xem DDL dự kiến

Dùng `impdp ... SQLFILE=...` để xuất DDL ra file kiểm tra. So sánh danh sách table, index, constraint, trigger, sequence, package và các object cần thiết với yêu cầu migration.

### Kiểm tra số dòng sau import

Sau import, so sánh số dòng ở nguồn và đích theo đúng điều kiện QUERY. Ví dụ ở nguồn:

~~~sql
SELECT COUNT(*)
FROM   hr.orders
WHERE  status = 'OPEN'
AND    order_date >= DATE '2026-01-01';
~~~

Ở đích:

~~~sql
SELECT COUNT(*)
FROM   hr.orders;
~~~

Nếu dump được export bằng điều kiện trên và không có bước lọc/thay đổi dữ liệu khác, số dòng trong table đích cần khớp với số dòng được export. Với table partition hoặc quy trình transform, cần so sánh theo đúng phạm vi partition và điều kiện đã áp dụng.

### Kiểm tra object metadata

Có thể đối chiếu các đối tượng quan trọng bằng data dictionary như DBA_TABLES, DBA_INDEXES, DBA_CONSTRAINTS, DBA_TRIGGERS, DBA_OBJECTS và DBA_TAB_PRIVS. Chọn view phù hợp với quyền hiện có. Đối với đối tượng invalid sau import, kiểm tra trạng thái và compile theo quy trình triển khai.

## 15. Lỗi thường gặp và cách xử lý

### ORA-39001 hoặc lỗi filter không hợp lệ

Nguyên nhân có thể là object path sai, biểu thức INCLUDE/EXCLUDE không đúng cú pháp, tên object không khớp hoặc filter không được hỗ trợ trong mode hiện tại. Tra cứu object path từ view export objects của đúng mode và kiểm tra quoting.

### Object được export nhiều hơn dự kiến

Kiểm tra mode ban đầu, INCLUDE/EXCLUDE, dependency của object và cách biểu thức tên được áp dụng. Nếu mục tiêu chỉ là một nhóm table, cân nhắc dùng TABLES mode để giới hạn phạm vi trước.

### Table có metadata nhưng không có dòng dữ liệu

Có thể job dùng CONTENT=METADATA_ONLY, table không có dòng phù hợp với QUERY, hoặc table data không thuộc phạm vi job. Kiểm tra CONTENT, QUERY, log và số dòng nguồn.

### QUERY báo lỗi SQL

Kiểm tra tên cột, kiểu dữ liệu, literal ngày, dấu nháy và biểu thức WHERE. Chạy điều kiện SQL tương ứng trực tiếp trên database nguồn trước khi export. Nếu biểu thức có tên cột hoặc function phức tạp, cần xác nhận quyền và ngữ cảnh thực thi.

### Import tạo thiếu object phụ thuộc

Xem lại filter và dependency rules. Việc loại table hoặc loại object path có thể loại luôn metadata phụ thuộc. Dùng SQLFILE để xem DDL dự kiến, điều chỉnh filter và tạo lại dump hoặc chạy lại import theo kế hoạch phù hợp.

### Filter đúng nhưng job chạy lâu

INCLUDE/EXCLUDE chỉ giảm công việc metadata ở phạm vi phù hợp; QUERY có thể vẫn phải đọc nhiều dữ liệu để đánh giá điều kiện. Kiểm tra execution plan của điều kiện nguồn, index, partition pruning, dung lượng dump, PARALLEL và năng lực I/O. Tăng PARALLEL không đảm bảo nhanh hơn nếu storage hoặc CPU đã bão hòa.

## 16. Quy trình thiết kế job Data Pump có filter

1. **Xác định mục tiêu.** Cần chuyển cả database, schema, table hay partition? Cần metadata, data hay cả hai?
2. **Chọn mode.** Chọn đúng một phạm vi chính như FULL, SCHEMAS hoặc TABLES.
3. **Liệt kê object cần có.** Xác định table, view, sequence, package, procedure, trigger, constraint, index và grant cần thiết.
4. **Chọn INCLUDE hoặc EXCLUDE.** Dùng INCLUDE nếu danh sách object type cần xử lý rõ ràng; dùng EXCLUDE nếu chỉ cần bỏ một vài object khỏi phạm vi rộng.
5. **Kiểm tra dependency.** Tra object path, hiểu quan hệ phụ thuộc và xem DDL bằng SQLFILE khi cần.
6. **Xác định row filter.** Nếu chỉ cần một phần dòng, dùng QUERY trong Data Pump Export và kiểm tra điều kiện WHERE trên nguồn.
7. **Chọn CONTENT.** Quyết định export/import metadata, data hoặc cả hai.
8. **Chuẩn bị parameter file.** Tách filter và quoting khỏi command line; bảo vệ thông tin xác thực.
9. **Chạy job thử và đọc log.** Xác nhận object, số dòng, cảnh báo và lỗi.
10. **Xác minh ở đích.** Dùng SQLFILE, data dictionary và đối chiếu số dòng theo điều kiện đã chọn.

## 17. Nguyên tắc quan trọng khi chọn phạm vi

- Mode xác định phạm vi lớn ban đầu; INCLUDE/EXCLUDE lọc metadata bên trong phạm vi đó.
- INCLUDE và EXCLUDE là hai chiến lược thay thế nhau trong một job; không chỉ định cả hai cùng lúc.
- Object path phải hợp lệ với mode. Tra cứu từ DATABASE_EXPORT_OBJECTS, SCHEMA_EXPORT_OBJECTS hoặc TABLE_EXPORT_OBJECTS.
- Dependency có thể khiến metadata liên quan được đưa vào hoặc bị loại theo object được chọn.
- QUERY lọc dòng table data trong Data Pump Export; nó không lọc object type và không thay thế TABLES/SCHEMAS.
- CONTENT điều khiển metadata/data được xử lý, không phải điều kiện lọc dòng.
- Dùng parameter file để quản lý quoting và tái sử dụng cấu hình.
- Đọc log và xem SQLFILE để xác nhận phạm vi trước khi import vào hệ thống quan trọng.
- Đối chiếu số dòng ở nguồn và đích theo đúng điều kiện WHERE, partition và phạm vi job.
- Lưu parameter file, log và thông tin filter cùng hồ sơ migration để có thể tái hiện hoặc điều tra job.

Chọn phạm vi Data Pump chính xác là sự kết hợp giữa mode, object filters và row filter. Khi mỗi tham số được dùng đúng lớp, job export/import sẽ rõ ràng, có thể kiểm tra và đáp ứng chính xác yêu cầu di chuyển metadata cùng dữ liệu.
