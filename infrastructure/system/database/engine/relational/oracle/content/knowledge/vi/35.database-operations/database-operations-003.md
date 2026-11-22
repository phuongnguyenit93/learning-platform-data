# PFILE, SPFILE và phạm vi MEMORY/SPFILE/BOTH của tham số

Oracle Database sử dụng initialization parameters để điều khiển cách instance khởi động và vận hành. Các tham số như MEMORY_TARGET, SGA_TARGET, PROCESSES, OPEN_CURSORS, DB_CACHE_SIZE, UNDO_TABLESPACE, CONTROL_FILES hoặc optimizer settings ảnh hưởng đến memory, process, transaction, SQL execution và nhiều thành phần khác.

Oracle có hai cách lưu các tham số khởi tạo:

- **PFILE (parameter file):** file văn bản thuần, thường được gọi là init.ora. DBA có thể đọc và sửa bằng text editor khi instance không dùng file đó để ghi tự động.
- **SPFILE (server parameter file):** file nhị phân do Oracle quản lý. DBA thay đổi nội dung bằng câu lệnh ALTER SYSTEM hoặc các công cụ quản trị được hỗ trợ; không chỉnh sửa trực tiếp bằng text editor.

Khi dùng SPFILE, câu lệnh ALTER SYSTEM SET có thể chọn nơi lưu thay đổi bằng SCOPE:

- **MEMORY:** thay đổi giá trị trong bộ nhớ của instance đang chạy; không lưu vào SPFILE để duy trì qua lần restart.
- **SPFILE:** chỉ ghi giá trị vào SPFILE; giá trị sẽ được dùng khi instance khởi động lại.
- **BOTH:** thay đổi cả giá trị runtime và giá trị lưu trong SPFILE.

Hiểu đúng ba phạm vi này giúp tránh hai lỗi vận hành phổ biến: thay đổi tham số xong restart thì mất vì chỉ đặt MEMORY, hoặc thay đổi SPFILE nhưng kỳ vọng instance hiện tại đổi ngay. Cũng cần phân biệt tham số dynamic có thể thay đổi khi instance đang chạy với tham số static chỉ có hiệu lực sau restart.

## 1. Initialization parameters và instance startup

### 1.1. Initialization parameter là gì?

Initialization parameter là cấu hình Oracle đọc khi tạo instance. Một số tham số xác định cấu trúc memory, số process, control files, database name và undo; một số tham số ảnh hưởng optimizer, parallel execution, auditing, security hoặc behavior của session.

Có thể chia khái quát thành:

- Tham số ảnh hưởng instance-wide.
- Tham số có thể thay đổi theo session.
- Tham số chỉ có hiệu lực khi khởi động instance.
- Tham số có thể thay đổi ngay hoặc áp dụng cho session mới.
- Tham số có thể được đặt riêng cho từng instance trong RAC.

Không phải mọi parameter đều có cùng phạm vi thay đổi. Trước khi thay đổi, kiểm tra thuộc tính của parameter trong data dictionary và tài liệu đúng Oracle release.

### 1.2. Instance cần parameter file khi startup

Khi khởi động, Oracle đọc initialization parameters để tạo SGA, khởi tạo background processes và chuẩn bị instance. Một số tham số phải có ngay từ bước NOMOUNT; một số tham số có thể có giá trị mặc định nếu không khai báo.

Quy trình startup thường đi qua:

1. NOMOUNT: đọc parameter file, tạo instance, cấp phát memory và khởi động background processes.
2. MOUNT: mở control files và liên kết instance với database.
3. OPEN: mở data files và redo logs để database phục vụ workload.

Nếu parameter file sai, thiếu hoặc chứa giá trị không hợp lệ, instance có thể không khởi động được hoặc không thể đi tới trạng thái mong muốn.

### 1.3. Default parameter file

Nếu không chỉ rõ PFILE trong lệnh STARTUP, Oracle tìm server parameter file theo quy tắc và vị trí mặc định của nền tảng/cấu hình. Nếu không tìm thấy SPFILE phù hợp, Oracle có thể tìm PFILE mặc định.

Tên file và thư mục khác nhau giữa Windows, Unix/Linux, Oracle Home và cấu hình ASM. Vì vậy, không nên giả định mọi database đều dùng cùng một đường dẫn. Có thể xác định file đang dùng sau khi instance khởi động bằng:

```sql
SHOW PARAMETER spfile;
```

Hoặc:

```sql
SELECT value
FROM v$parameter
WHERE name = 'spfile';
```

Nếu VALUE rỗng, instance có thể đã được khởi động bằng PFILE hoặc không có SPFILE path được báo trong parameter view.

## 2. PFILE: text parameter file

### 2.1. Đặc điểm

PFILE là file văn bản có thể đọc được. Một PFILE có các dòng parameter theo dạng:

```text
db_name='ORCL'
control_files='/u01/oradata/ORCL/control01.ctl'
memory_target=4G
processes=500
open_cursors=500
```

Đây là ví dụ minh họa; đường dẫn, database name và giá trị phải phù hợp với môi trường thực tế.

PFILE thường hữu ích khi:

- Cần khởi động instance bằng một bộ tham số được kiểm soát thủ công.
- Cần phục hồi sau khi SPFILE hỏng hoặc cấu hình sai.
- Muốn lưu bản cấu hình dễ đọc để review/version control.
- Muốn tạo SPFILE mới từ một file văn bản.
- Thực hiện thay đổi tham số tĩnh trong một cửa sổ bảo trì.

### 2.2. Ưu điểm

- Có thể mở và xem bằng editor.
- Dễ review thay đổi bằng diff.
- Dễ lưu vào hệ thống quản lý phiên bản nếu đã loại bỏ secret.
- Có thể dùng để startup mà không cần SPFILE mặc định.
- Dễ tạo một bản cấu hình lab riêng.

### 2.3. Hạn chế

- Oracle không tự ghi lại thay đổi runtime vào PFILE.
- DBA phải quản lý nội dung file và bảo đảm đúng đường dẫn khi startup.
- PFILE có thể bị lệch so với cấu hình runtime nếu thay đổi bằng SCOPE=MEMORY.
- Việc sửa file khi instance đang chạy không làm instance tự nạp lại tham số.
- Một lỗi cú pháp hoặc giá trị có thể làm startup thất bại.

### 2.4. Dùng PFILE để startup

Ví dụ khởi động bằng file cụ thể:

```sql
STARTUP PFILE='/u01/app/oracle/admin/ORCL/pfile/initORCL.ora';
```

Đường dẫn trên chỉ minh họa cho Linux/Unix. Trên Windows hoặc môi trường ASM, đường dẫn sẽ khác.

Nếu instance đã chạy, không thể chỉ sửa file PFILE rồi mong các tham số trong bộ nhớ thay đổi. Phải dùng ALTER SYSTEM cho các parameter dynamic hoặc shutdown/startup bằng file đã sửa để áp dụng các tham số cần restart.

### 2.5. PFILE có thể là file trỏ tới SPFILE

Trong một số cấu hình, file init.ora văn bản rất ngắn chỉ chứa chỉ thị SPFILE trỏ đến server parameter file ở vị trí khác, ví dụ SPFILE trong ASM. Đây là cách giúp Oracle tìm được SPFILE dùng chung, đặc biệt trong RAC.

```text
SPFILE='+DATA/ORCL/PARAMETERFILE/spfile.123.456789'
```

Đây là ví dụ dạng pointer, không phải tên file cố định cho mọi database. Không sửa hoặc di chuyển SPFILE trong ASM bằng cách xử lý như file text thông thường.

## 3. SPFILE: server parameter file

### 3.1. Đặc điểm

SPFILE là file nhị phân do Oracle quản lý. Instance có thể đọc nó lúc startup và Oracle có thể cập nhật nó qua ALTER SYSTEM SET với phạm vi phù hợp.

SPFILE lưu các giá trị parameter đã được cấu hình tường minh, có thể bao gồm:

- Giá trị mặc định áp dụng cho mọi instance.
- Giá trị riêng theo SID trong RAC.
- Một số thông tin cấu hình cần duy trì qua lần restart.

Không mở SPFILE bằng text editor để sửa trực tiếp. Nội dung nhị phân có cấu trúc nội bộ; sửa ngoài Oracle có thể làm hỏng file hoặc khiến startup thất bại.

### 3.2. Ưu điểm

- Oracle có thể cập nhật bằng ALTER SYSTEM.
- Giá trị đặt với SCOPE=SPFILE hoặc BOTH được duy trì qua restart.
- Có thể quản lý giá trị chung và giá trị riêng từng instance trong RAC.
- DBA không phải chỉnh sửa text file thủ công cho từng thay đổi parameter.
- Dễ kết hợp với công cụ quản trị Oracle và cấu hình ASM.

### 3.3. Hạn chế

- Không đọc/sửa trực tiếp bằng editor như PFILE.
- Khi file hỏng hoặc giá trị sai, có thể phải khôi phục từ backup/PFILE.
- Cần kiểm soát rõ giá trị đang có hiệu lực và giá trị được lưu.
- Thay đổi SPFILE không có nghĩa mọi tham số runtime đã thay đổi ngay.
- Trong RAC, cần hiểu rõ SID='*' và các override riêng instance.

### 3.4. Xác định instance có dùng SPFILE hay không

```sql
SHOW PARAMETER spfile;

SELECT name, value, isdefault
FROM v$parameter
WHERE name = 'spfile';
```

Nếu SPFILE path được hiển thị, instance đang dùng server parameter file được chỉ ra. Nếu không, kiểm tra cách startup và PFILE cụ thể.

### 3.5. Tại sao không chỉnh sửa SPFILE bằng editor?

SPFILE là binary format. Việc thay đổi byte hoặc chuỗi bên trong không bảo đảm Oracle đọc được cấu trúc hợp lệ. Hãy dùng ALTER SYSTEM hoặc chuyển sang PFILE bằng CREATE PFILE để review/chỉnh sửa theo quy trình.

## 4. PFILE và SPFILE: so sánh

| Tiêu chí | PFILE | SPFILE |
|---|---|---|
| Định dạng | Text | Binary |
| DBA đọc trực tiếp | Có | Không nên |
| Sửa bằng text editor | Có | Không |
| Oracle tự ghi thay đổi parameter | Không | Có, qua ALTER SYSTEM phù hợp |
| Lưu giá trị qua restart | Chỉ khi file được sửa đúng | Có với SCOPE=SPFILE/BOTH |
| Thay đổi runtime | Qua ALTER SYSTEM nếu parameter cho phép | Qua ALTER SYSTEM nếu parameter cho phép |
| RAC per-instance values | Phải quản lý file theo cách cấu hình | Hỗ trợ giá trị theo SID |
| Dễ diff/version control | Dễ hơn | Thường xuất ra PFILE để review |
| Dùng để startup | STARTUP PFILE=... | Oracle tự tìm SPFILE hoặc dùng pointer PFILE |
| Backup/recovery | Copy file text | Export ra PFILE hoặc backup file phù hợp |

Một database có thể sử dụng SPFILE cho vận hành thường ngày nhưng vẫn duy trì PFILE backup để kiểm tra, so sánh hoặc phục hồi.

## 5. Chuyển đổi giữa PFILE và SPFILE

### 5.1. Tạo PFILE từ SPFILE

Đây là cách phổ biến để backup cấu hình SPFILE thành văn bản:

```sql
CREATE PFILE='/u01/backup/initORCL_20261114.ora'
FROM SPFILE;
```

Oracle đọc SPFILE mà instance đang sử dụng và ghi nội dung thành PFILE tại đường dẫn chỉ định. Cần bảo đảm thư mục tồn tại và Oracle process có quyền ghi.

Có thể tạo từ một SPFILE cụ thể:

```sql
CREATE PFILE='/u01/backup/initORCL.ora'
FROM SPFILE='/u01/app/oracle/product/19c/dbhome_1/dbs/spfileORCL.ora';
```

Đường dẫn chỉ là ví dụ. Khi dùng ASM hoặc RAC, SPFILE có thể nằm ở vị trí khác.

### 5.2. Review PFILE sau khi export

Sau khi tạo PFILE:

1. Đọc file bằng editor.
2. Xác nhận DB_NAME, CONTROL_FILES và các tham số quan trọng.
3. Kiểm tra giá trị memory, process, undo, archive và optimizer.
4. Xác định các dòng theo SID nếu database dùng RAC.
5. Lưu bản backup với timestamp và quyền file phù hợp.
6. Không đưa password, secret hoặc thông tin nhạy cảm vào kho version control không được bảo vệ.

PFILE export là snapshot của cấu hình được lưu trong SPFILE; nó không nhất thiết chứa mọi giá trị mặc định đang được Oracle sử dụng.

### 5.3. Tạo SPFILE từ PFILE

Ví dụ:

```sql
CREATE SPFILE='/u01/app/oracle/product/19c/dbhome_1/dbs/spfileORCL.ora'
FROM PFILE='/u01/backup/initORCL.ora';
```

Sau khi tạo SPFILE, instance đang chạy bằng PFILE không tự chuyển sang dùng SPFILE mới. Muốn dùng file mới ở lần startup tiếp theo, cần shutdown và startup theo quy tắc tìm SPFILE hoặc cấu hình pointer PFILE phù hợp.

### 5.4. Tạo SPFILE ở vị trí mặc định

Có thể bỏ tên file đích để Oracle tạo SPFILE ở vị trí mặc định của platform/database:

```sql
CREATE SPFILE FROM PFILE='/u01/backup/initORCL.ora';
```

Trước khi chạy, kiểm tra file đích mặc định có tồn tại hay không và quy tắc tên file trên Oracle Home đó. Không ghi đè một SPFILE đang dùng mà chưa có backup và kế hoạch rollback.

### 5.5. Tạo PFILE từ SPFILE trong ASM

Nếu SPFILE nằm trong ASM, Oracle có thể đọc từ ASM và xuất ra PFILE trên filesystem:

```sql
CREATE PFILE='/u01/backup/initORCL.ora'
FROM SPFILE='+DATA/ORCL/PARAMETERFILE/spfile.123.456789';
```

Tên ASM file phải lấy từ cấu hình thực tế, không đoán. Có thể kiểm tra cấu hình database bằng công cụ Oracle Clusterware/ASM và các view phù hợp.

### 5.6. Kiểm tra sau chuyển đổi

Sau khi chuyển:

- Kiểm tra file được tạo và kích thước khác 0.
- Đọc lại PFILE nếu đó là output.
- Nếu tạo SPFILE, xem V$SPPARAMETER khi instance sử dụng file đó.
- Thử startup bằng file mới trong môi trường an toàn nếu có thể.
- Xác nhận SHOW PARAMETER SPFILE sau khi khởi động.

Không coi lệnh CREATE SPFILE thành công là bằng chứng mọi tham số đều có thể khởi động database trong mọi trạng thái.

## 6. SCOPE trong ALTER SYSTEM SET

### 6.1. Cú pháp tổng quát

```sql
ALTER SYSTEM SET parameter_name = value
    SCOPE = {MEMORY | SPFILE | BOTH}
    SID = {'*' | 'instance_name'};
```

SID là phần cần quan tâm trong RAC. Với database không dùng RAC, có thể bỏ SID theo cú pháp và phạm vi áp dụng của release. Không phải mọi parameter đều cho phép mọi combination của SCOPE và SID.

### 6.2. SCOPE=MEMORY

Chỉ thay đổi giá trị trong memory của instance đang chạy:

```sql
ALTER SYSTEM SET open_cursors = 600
    SCOPE = MEMORY;
```

Đặc điểm:

- Thay đổi có hiệu lực ngay nếu parameter cho phép dynamic modification.
- Không ghi giá trị vào SPFILE.
- Khi restart, Oracle đọc giá trị từ SPFILE/PFILE và giá trị MEMORY sẽ mất.
- Nếu instance khởi động bằng PFILE, MEMORY là phạm vi có thể dùng cho các thay đổi runtime được hỗ trợ.

MEMORY không phải lựa chọn cho parameter static vì parameter đó không thể thay đổi trong memory khi instance đang chạy.

### 6.3. SCOPE=SPFILE

Chỉ ghi giá trị vào SPFILE:

```sql
ALTER SYSTEM SET processes = 700
    SCOPE = SPFILE;
```

Đặc điểm:

- Giá trị được lưu cho lần startup tiếp theo.
- Giá trị runtime hiện tại không đổi ngay.
- Thường dùng cho parameter static cần restart.
- Cần instance sử dụng SPFILE để Oracle có nơi ghi thay đổi.

Nếu instance được startup bằng PFILE mà không có SPFILE được sử dụng, yêu cầu ghi vào SPFILE có thể thất bại với lỗi ORA-32001. Khi đó cần tạo/chuẩn bị SPFILE đúng cách hoặc sửa PFILE và startup lại.

### 6.4. SCOPE=BOTH

Thay đổi cả memory và SPFILE:

```sql
ALTER SYSTEM SET open_cursors = 700
    SCOPE = BOTH;
```

Đặc điểm:

- Giá trị runtime được thay đổi nếu parameter dynamic và cho phép áp dụng ngay.
- Giá trị mới được lưu trong SPFILE để duy trì qua restart.
- Là lựa chọn phổ biến cho thay đổi parameter dynamic khi muốn hiệu lực ngay và bền vững.
- Không dùng như cách áp dụng ngay cho parameter static.

Nếu tham số không thể thay đổi runtime, phải dùng phạm vi lưu SPFILE và restart theo yêu cầu; không giả định BOTH có thể vượt qua giới hạn static.

### 6.5. Bảng so sánh

| SCOPE | Thay đổi memory hiện tại | Ghi SPFILE | Còn sau restart | Dùng điển hình |
|---|---|---|---|---|
| MEMORY | Có, nếu parameter dynamic | Không | Không | Thử tạm hoặc thay đổi runtime |
| SPFILE | Không | Có | Có | Parameter static hoặc chuẩn bị thay đổi sau restart |
| BOTH | Có, nếu parameter dynamic | Có | Có | Thay đổi dynamic cần duy trì |

### 6.6. Giá trị mặc định của SCOPE

Nếu bỏ SCOPE, hành vi mặc định phụ thuộc cách instance được khởi động và cấu hình Oracle. Trong trường hợp dùng SPFILE, mặc định thường là BOTH; khi dùng PFILE, mặc định là MEMORY. Để tránh phụ thuộc ngữ cảnh, script vận hành nên ghi SCOPE tường minh.

### 6.7. SCOPE không phải SESSION

ALTER SYSTEM tác động ở phạm vi instance/SPFILE theo policy. Nếu parameter cho phép session-level modification, ALTER SESSION là một cơ chế khác:

```sql
ALTER SESSION SET optimizer_mode = FIRST_ROWS_10;
```

Thay đổi session không có nghĩa SPFILE hoặc instance-wide value thay đổi. Khi điều tra giá trị parameter, phân biệt session value với system value.

## 7. Dynamic, deferred và static parameters

### 7.1. Dynamic parameter

Dynamic parameter có thể thay đổi khi instance đang chạy. Thuộc tính ISSYS_MODIFIABLE trong V$PARAMETER giúp xác định cách thay đổi:

- IMMEDIATE: thay đổi được áp dụng ngay.
- DEFERRED: thay đổi được áp dụng cho session mới hoặc theo semantics deferred.
- FALSE: không thể thay đổi động ở cấp system; cần restart hoặc cơ chế được tài liệu quy định.

Không phải mọi dynamic parameter đều cho phép đổi bằng mọi SCOPE.

### 7.2. Static parameter

Parameter có ISSYS_MODIFIABLE = FALSE thường cần restart để giá trị mới có hiệu lực. Ví dụ PROCESSES là một parameter thường cần khởi động lại sau khi thay đổi.

Quy trình điển hình:

```sql
ALTER SYSTEM SET processes = 700
    SCOPE = SPFILE;
```

Sau đó lên kế hoạch restart trong cửa sổ bảo trì và kiểm tra giá trị sau startup.

### 7.3. Immediate parameter

Với parameter có ISSYS_MODIFIABLE = IMMEDIATE, giá trị có thể thay đổi ngay:

```sql
ALTER SYSTEM SET open_cursors = 600
    SCOPE = BOTH;
```

Ví dụ chỉ minh họa cú pháp; hãy kiểm tra parameter cụ thể và quyền trước khi áp dụng.

### 7.4. Deferred parameter

Với parameter có ISSYS_MODIFIABLE = DEFERRED, thay đổi thường áp dụng cho session mới, không nhất thiết thay đổi giá trị đã được session đang tồn tại sử dụng. Cú pháp ALTER SYSTEM có thể dùng keyword DEFERRED theo yêu cầu:

```sql
ALTER SYSTEM SET optimizer_mode = FIRST_ROWS_10
    DEFERRED SCOPE = BOTH;
```

Chỉ dùng khi parameter và Oracle release hỗ trợ. Kiểm tra session cũ và session mới để xác nhận behavior.

### 7.5. Session-modifiable parameters

ISSES_MODIFIABLE trong V$PARAMETER cho biết parameter có thể thay đổi bằng ALTER SESSION hay không. Một parameter có thể session-modifiable nhưng không cho phép system-wide change theo cách mong muốn. Đọc đúng thuộc tính thay vì suy luận từ tên parameter.

### 7.6. Kiểm tra thuộc tính parameter

```sql
SELECT name,
       value,
       isses_modifiable,
       issys_modifiable,
       isinstance_modifiable,
       isdefault,
       ismodified
FROM v$parameter
WHERE name IN (
    'processes',
    'open_cursors',
    'optimizer_mode',
    'sga_target'
)
ORDER BY name;
```

Cột và giá trị có thể khác theo release. Dùng view này trước khi quyết định SCOPE và thời điểm restart.

## 8. Đọc giá trị runtime và giá trị đã lưu

### 8.1. SHOW PARAMETER

Trong SQL*Plus/SQLcl:

```sql
SHOW PARAMETER processes;
SHOW PARAMETER open_cursors;
SHOW PARAMETER spfile;
```

SHOW PARAMETER tiện cho kiểm tra nhanh giá trị đang được session tool hiển thị.

### 8.2. V$PARAMETER

V$PARAMETER hiển thị giá trị parameter theo session hiện tại và metadata liên quan. Một số parameter có thể khác giữa session nếu session-level modification được phép.

```sql
SELECT name,
       value,
       display_value,
       isdefault,
       ismodified,
       issys_modifiable,
       isses_modifiable
FROM v$parameter
WHERE name = 'open_cursors';
```

### 8.3. V$SYSTEM_PARAMETER

V$SYSTEM_PARAMETER hiển thị system-wide parameter values của instance, không phản ánh override riêng của session như V$PARAMETER có thể làm.

```sql
SELECT name, value, display_value, isdefault, issys_modifiable
FROM v$system_parameter
WHERE name IN ('open_cursors', 'processes');
```

### 8.4. V$SPPARAMETER

V$SPPARAMETER cho biết các giá trị được lưu trong SPFILE:

```sql
SELECT sid,
       name,
       value,
       display_value,
       isspecified
FROM v$spparameter
WHERE name IN ('processes', 'open_cursors')
ORDER BY name, sid;
```

ISSPECIFIED cho biết parameter có được chỉ định trong SPFILE hay không. Nếu không có dòng được cấu hình tường minh, Oracle có thể dùng default hoặc giá trị được suy ra theo quy tắc parameter.

### 8.5. So sánh runtime với SPFILE

```sql
SELECT p.name,
       p.value AS runtime_value,
       s.value AS spfile_value,
       s.sid,
       s.isspecified
FROM v$system_parameter p
LEFT JOIN v$spparameter s
  ON s.name = p.name
WHERE p.name IN (
    'processes',
    'open_cursors',
    'optimizer_mode',
    'sga_target'
)
ORDER BY p.name, s.sid;
```

Đây là truy vấn đối chiếu đơn giản. Với RAC và SID-specific values, cần diễn giải đúng dòng SID='*' và các override theo instance. Runtime value hiện tại có thể không giống SPFILE value nếu đã dùng SCOPE=MEMORY, nếu parameter được điều chỉnh tự động hoặc nếu có session-level override.

### 8.6. ISMODIFIED và ISDEFAULT

ISDEFAULT cho biết giá trị có phải default theo metadata hay không. ISMODIFIED cho biết parameter đã được thay đổi trong session/system theo trạng thái mà view cung cấp. Các cột này hỗ trợ điều tra nhưng không thay thế việc so sánh trực tiếp V$SYSTEM_PARAMETER và V$SPPARAMETER.

## 9. SCOPE và RAC: SID='*' và instance-specific values

### 9.1. Một SPFILE dùng chung

Trong Oracle RAC, các instance thường dùng một SPFILE chung trên ASM hoặc shared storage. SPFILE có thể chứa:

- Giá trị mặc định với SID='*'.
- Giá trị override cho instance cụ thể, ví dụ ORCL1 hoặc ORCL2.

### 9.2. Đặt giá trị cho mọi instance

Ví dụ:

```sql
ALTER SYSTEM SET open_cursors = 600
    SCOPE = SPFILE
    SID = '*';
```

Giá trị wildcard được dùng làm mặc định cho các instance theo quy tắc SPFILE. Thay đổi memory runtime trong RAC cần xem xét SID và hành vi của lệnh theo release; xác nhận trên từng instance.

### 9.3. Đặt giá trị riêng cho một instance

Ví dụ:

```sql
ALTER SYSTEM SET undo_tablespace = 'UNDOTBS1'
    SCOPE = SPFILE
    SID = 'ORCL1';
```

Instance ORCL1 có thể có giá trị riêng, trong khi ORCL2 tiếp tục dùng wildcard hoặc override của chính nó. Giá trị cụ thể cần phù hợp cấu trúc database.

### 9.4. Override và wildcard

Khi có giá trị SID-specific, giá trị riêng instance có thể override giá trị wildcard cho instance đó. Vì vậy, chỉ xem dòng SID='*' chưa đủ để hiểu cấu hình cuối cùng của từng instance.

Kiểm tra toàn bộ dòng của parameter:

```sql
SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE name = 'undo_tablespace'
ORDER BY sid;
```

### 9.5. MEMORY trong RAC

SCOPE=MEMORY tác động đến giá trị runtime, nhưng phạm vi instance phải được hiểu rõ. Trong RAC, một lệnh thực hiện trên instance hiện tại không tự động có nghĩa mọi instance khác đã nhận cùng thay đổi trong memory. Nếu cần thay đổi runtime trên nhiều instance, dùng phương pháp được hỗ trợ cho cluster và xác nhận giá trị ở từng instance.

### 9.6. SID clause

SID='*' và SID='instance_name' chủ yếu quan trọng khi quản lý SPFILE dùng cho nhiều instance. Không sử dụng tên SID tùy ý; lấy đúng instance name từ cấu hình cluster/database. Một typo có thể tạo entry không được instance mong muốn sử dụng.

## 10. Thay đổi parameter theo quy trình an toàn

### 10.1. Xác định mục tiêu

Trước khi thay đổi, ghi rõ:

- Parameter nào cần thay đổi?
- Vấn đề vận hành nào cần giải quyết?
- Giá trị hiện tại là gì?
- Giá trị mới dựa trên tài liệu, capacity planning hay kết quả đo nào?
- Parameter dynamic, deferred hay static?
- Thay đổi cần có hiệu lực ngay hay chỉ sau restart?
- Phạm vi là session, instance hay toàn bộ RAC?

### 10.2. Kiểm tra trạng thái hiện tại

Thu thập:

- SHOW PARAMETER.
- V$PARAMETER/V$SYSTEM_PARAMETER.
- V$SPPARAMETER.
- SPFILE path.
- Instance name và database role.
- Startup options nếu biết.
- Current resource usage và alert log nếu parameter liên quan capacity.

### 10.3. Backup cấu hình

Nếu dùng SPFILE, export ra PFILE trước thay đổi:

```sql
CREATE PFILE='/u01/backup/init_before_change.ora'
FROM SPFILE;
```

Đặt tên file có timestamp/change ticket. Với RAC, kiểm tra file backup có giữ đủ wildcard và instance-specific entries.

### 10.4. Chọn SCOPE

| Nhu cầu | Lựa chọn thường dùng |
|---|---|
| Thử dynamic parameter tạm thời | MEMORY |
| Thay parameter static cho lần startup sau | SPFILE |
| Thay dynamic parameter ngay và giữ sau restart | BOTH |
| Đang dùng PFILE, cần thay runtime dynamic | MEMORY hoặc sửa PFILE cho lần startup |
| Đang dùng PFILE, cần lưu thay đổi vào SPFILE | Tạo SPFILE phù hợp rồi chuyển startup sang SPFILE |

Luôn kiểm tra khả năng thay đổi cụ thể của parameter.

### 10.5. Thực hiện thay đổi

Ví dụ dynamic:

```sql
ALTER SYSTEM SET open_cursors = 700
    SCOPE = BOTH;
```

Ví dụ static:

```sql
ALTER SYSTEM SET processes = 700
    SCOPE = SPFILE;
```

Không chạy các giá trị ví dụ trên production nếu chưa đánh giá capacity, license, OS limits và application behavior.

### 10.6. Xác minh sau thay đổi

Với dynamic parameter, kiểm tra V$SYSTEM_PARAMETER và session mới nếu parameter deferred. Với SPFILE-only, kiểm tra V$SPPARAMETER. Sau restart, xác nhận runtime value đã nhận giá trị mong muốn.

### 10.7. Ghi nhận thay đổi

Lưu:

- SQL statement hoặc bản PFILE trước/sau.
- Giá trị trước và sau.
- SCOPE và SID.
- Thời điểm thay đổi.
- Người thực hiện/change ticket.
- Kết quả validation.
- Kế hoạch rollback.

## 11. RESET parameter và khôi phục giá trị

### 11.1. Vì sao cần RESET?

Khi một parameter được cấu hình tường minh trong SPFILE, DBA có thể muốn bỏ override để Oracle dùng lại giá trị default hoặc giá trị wildcard tương ứng. ALTER SYSTEM RESET được dùng để loại bỏ entry đã đặt trong SPFILE theo phạm vi SID phù hợp.

### 11.2. RESET trong SPFILE

Ví dụ loại bỏ một cấu hình instance-specific:

```sql
ALTER SYSTEM RESET open_cursors
    SCOPE = SPFILE
    SID = 'ORCL1';
```

Ví dụ loại bỏ cấu hình wildcard:

```sql
ALTER SYSTEM RESET open_cursors
    SCOPE = SPFILE
    SID = '*';
```

Kiểm tra lại V$SPPARAMETER sau thao tác. RESET không có nghĩa mọi instance runtime lập tức quay về default; nếu chỉ reset SPFILE, thay đổi có hiệu lực theo lần startup tiếp theo.

### 11.3. Rollback bằng giá trị cũ

Nếu biết giá trị cũ, có thể đặt lại bằng ALTER SYSTEM SET với SCOPE và SID tương ứng. Đây thường là cách rõ ràng khi cần rollback một giá trị cụ thể.

### 11.4. Rollback từ PFILE backup

Nếu thay đổi SPFILE gây startup failure:

1. Dùng PFILE backup đã xác nhận hợp lệ.
2. Khởi động instance bằng STARTUP PFILE=... nếu có thể.
3. Kiểm tra alert log và lỗi startup.
4. Sửa giá trị sai trong PFILE.
5. Tạo SPFILE mới từ PFILE nếu cần.
6. Khởi động lại bằng SPFILE đã được xác minh.

Không ghi đè file gốc trước khi giữ bản backup và không xóa SPFILE cũ khi chưa xác nhận file mới hoạt động.

## 12. Startup bằng PFILE khi SPFILE có vấn đề

### 12.1. Khi nào cần?

Các tình huống thường gặp:

- SPFILE bị hỏng hoặc không đọc được.
- Một parameter static được đặt sai khiến instance không startup.
- Cần thử cấu hình sửa lỗi mà không phá hủy bản SPFILE cũ.
- Cần kiểm tra một bộ tham số khác trong môi trường recovery.

### 12.2. Tạo PFILE từ backup

Nếu SPFILE còn đọc được, xuất ra PFILE:

```sql
CREATE PFILE='/u01/backup/init_recovery.ora'
FROM SPFILE;
```

Nếu SPFILE không đọc được, dùng PFILE backup đã lưu trước đó hoặc bản cấu hình được quản lý an toàn.

### 12.3. Chỉnh sửa PFILE

Sửa đúng parameter gây lỗi. Không xóa hàng loạt parameter vì nhiều tham số có thể được yêu cầu bởi kiến trúc database, control files, RAC hoặc recovery configuration.

Kiểm tra:

- DB_NAME và DB_UNIQUE_NAME.
- CONTROL_FILES.
- MEMORY_TARGET/SGA/PGA settings.
- PROCESSES và các giới hạn liên quan.
- UNDO_TABLESPACE.
- ARCHIVELOG/FRA settings nếu liên quan.
- Các tham số đặc thù RAC.

### 12.4. Startup bằng PFILE

```sql
STARTUP PFILE='/u01/backup/init_recovery.ora' NOMOUNT;
```

Sau đó mount/open theo quy trình recovery phù hợp. Không dùng lệnh OPEN nếu database cần recovery hoặc chưa sẵn sàng.

### 12.5. Tạo SPFILE mới

Khi cấu hình PFILE đã được kiểm tra:

```sql
CREATE SPFILE='/u01/app/oracle/product/19c/dbhome_1/dbs/spfileORCL.ora'
FROM PFILE='/u01/backup/init_recovery.ora';
```

Lên kế hoạch shutdown/startup để instance sử dụng SPFILE mới. Nếu dùng ASM/RAC, tạo SPFILE tại vị trí shared được chỉ định bởi cấu hình cluster và cập nhật pointer PFILE nếu cần.

### 12.6. Kiểm tra sau recovery

- SHOW PARAMETER SPFILE hiển thị đúng file đang dùng.
- V$SPPARAMETER có các giá trị mong muốn.
- V$SYSTEM_PARAMETER phản ánh runtime values.
- Instance ở trạng thái phù hợp.
- Alert log không có lỗi parameter/startup mới.
- Các instance RAC khác khởi động và nhận đúng SID-specific settings.

## 13. Tham số nhiều giá trị và ký tự đặc biệt

### 13.1. Parameter dạng danh sách

Một số parameter có nhiều giá trị, ví dụ CONTROL_FILES hoặc LOG_ARCHIVE_DEST_n. Khi thay đổi, phải giữ đầy đủ các mục cần thiết:

```sql
ALTER SYSTEM SET control_files =
    '/u01/oradata/ORCL/control01.ctl',
    '/u02/oradata/ORCL/control02.ctl'
    SCOPE = SPFILE;
```

Đây là cú pháp minh họa. Cần xác nhận đường dẫn thật và số control files đúng trước khi thay đổi; thiếu control file có thể làm database không mount được.

### 13.2. Parameter có dấu phẩy hoặc chuỗi

Một số parameter nhận chuỗi có danh sách hoặc ký tự đặc biệt. Dùng quoting đúng SQL và kiểm tra giá trị sau khi lưu. Tránh nối dynamic SQL từ input không tin cậy.

### 13.3. Parameter có đơn vị

Một số tham số memory hoặc time hỗ trợ suffix như K/M/G hoặc đơn vị thời gian. Dùng đúng định dạng theo tài liệu parameter. Không suy luận mọi tham số số học đều nhận suffix.

### 13.4. Boolean parameters

Boolean parameter thường dùng TRUE/FALSE hoặc giá trị được tài liệu định nghĩa. Không dùng chuỗi tùy ý.

## 14. MEMORY, SPFILE và PFILE trong các tình huống thực tế

### 14.1. Thử một thay đổi dynamic trước

DBA muốn thử tăng OPEN_CURSORS trong thời gian kiểm tra:

1. Kiểm tra giá trị hiện tại và ISSYS_MODIFIABLE.
2. Đặt SCOPE=MEMORY.
3. Kiểm tra session/app behavior.
4. Nếu không phù hợp, đặt lại giá trị cũ trong memory.
5. Nếu phù hợp và cần giữ, thực hiện SCOPE=BOTH theo change process.

Đây là cách dùng MEMORY để thử tạm, nhưng vẫn cần đánh giá tác động và khả năng rollback.

### 14.2. Thay đổi parameter static

DBA muốn tăng PROCESSES:

1. Kiểm tra process usage hiện tại và OS/process limits.
2. Backup SPFILE.
3. Đặt SCOPE=SPFILE.
4. Xác nhận V$SPPARAMETER.
5. Lập lịch restart.
6. Sau restart, xác nhận runtime value và process capacity.

Không kỳ vọng thay đổi có hiệu lực ngay trong instance đang chạy.

### 14.3. Thay đổi chỉ cho lần restart kế tiếp

Có thể chuẩn bị cấu hình SPFILE trong khi database vẫn chạy. Điều này hữu ích khi cần thực hiện restart trong cửa sổ bảo trì sau. Hãy ghi rõ thay đổi chưa có hiệu lực runtime để đội vận hành không nhầm trạng thái.

### 14.4. Instance khởi động bằng PFILE

Nếu SHOW PARAMETER SPFILE không có đường dẫn, xác nhận startup bằng PFILE. Khi đó:

- ALTER SYSTEM SCOPE=MEMORY vẫn có thể dùng cho parameter dynamic.
- SCOPE=SPFILE/BOTH cần SPFILE được sử dụng theo quy tắc Oracle.
- Muốn thay đổi bền vững, sửa PFILE hoặc tạo SPFILE rồi chuyển startup.

### 14.5. RAC có giá trị riêng instance

Nếu mỗi instance có undo tablespace hoặc thread khác nhau, cấu hình SID-specific trong SPFILE có thể cần thiết. Kiểm tra cả wildcard và override, sau đó xác minh runtime từng instance.

## 15. Data dictionary và lệnh kiểm tra thường dùng

### 15.1. Kiểm tra SPFILE đang dùng

```sql
SHOW PARAMETER spfile;
```

### 15.2. Kiểm tra parameter hiện tại

```sql
SELECT name, value, display_value, isdefault,
       issys_modifiable, isses_modifiable,
       isinstance_modifiable
FROM v$parameter
WHERE name LIKE '%memory%'
   OR name IN ('processes', 'open_cursors', 'undo_tablespace')
ORDER BY name;
```

### 15.3. Kiểm tra system parameter

```sql
SELECT name, value, display_value, ismodified
FROM v$system_parameter
WHERE name IN (
    'processes',
    'open_cursors',
    'undo_tablespace',
    'optimizer_mode'
)
ORDER BY name;
```

### 15.4. Kiểm tra SPFILE entries

```sql
SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE isspecified = 'TRUE'
ORDER BY name, sid;
```

### 15.5. Kiểm tra tham số không thay đổi được

```sql
SELECT name, value, issys_modifiable
FROM v$parameter
WHERE issys_modifiable = 'FALSE'
ORDER BY name;
```

### 15.6. Kiểm tra instance

```sql
SELECT instance_name,
       host_name,
       version,
       status,
       database_status
FROM v$instance;
```

Trong RAC, chạy hoặc truy vấn GV$ views để xem trạng thái trên nhiều instance:

```sql
SELECT inst_id, instance_name, host_name, status
FROM gv$instance
ORDER BY inst_id;
```

### 15.7. Kiểm tra alert log

Khi startup thất bại sau thay đổi parameter, alert log là nguồn bằng chứng quan trọng. Kiểm tra lỗi ORA, parameter value, file path, memory allocation và các bước startup đã hoàn thành.

## 16. Quản lý tham số trong RAC và Clusterware

### 16.1. SPFILE trong ASM

RAC thường lưu SPFILE trên ASM để các instance cùng truy cập. Oracle Clusterware giữ thông tin về vị trí SPFILE dùng để khởi động database. Không di chuyển hoặc đổi tên SPFILE chỉ bằng thao tác filesystem; cập nhật cấu hình bằng công cụ Oracle phù hợp.

### 16.2. Giá trị chung và riêng

SPFILE RAC có thể lưu giá trị chung SID='*' và override theo instance. Một parameter như UNDO_TABLESPACE thường cần giá trị riêng theo instance; các parameter khác có thể dùng giá trị chung.

### 16.3. Thay đổi toàn cluster

Khi đặt SID='*', hiểu rõ lệnh có thay đổi SPFILE cho mọi instance và memory trên các instance đang chạy theo semantics nào. Xác nhận giá trị trên từng instance bằng GV$SYSTEM_PARAMETER hoặc kết nối trực tiếp từng instance.

### 16.4. Thay đổi một instance

Nếu chỉ một instance cần thay đổi, dùng SID cụ thể và xác minh đúng instance name. Đảm bảo wildcard không bị hiểu nhầm là giá trị sẽ ghi đè override riêng.

### 16.5. Dùng SRVCTL/Clusterware

Trong RAC, database startup configuration và SPFILE location có thể được Clusterware quản lý. Dùng SRVCTL và công cụ Oracle Clusterware để kiểm tra/cập nhật cấu hình database resource theo hướng dẫn phiên bản. ALTER SYSTEM quản lý parameter; SRVCTL quản lý tài nguyên database trong cluster. Hai lớp cần nhất quán.

## 17. Những lỗi và hiểu nhầm thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Thay đổi mất sau restart | Dùng SCOPE=MEMORY | Đặt SPFILE/BOTH hoặc sửa PFILE |
| SHOW PARAMETER không đổi ngay | Dùng SCOPE=SPFILE | Restart nếu parameter cần hoặc muốn nạp giá trị mới |
| ORA-32001 | Yêu cầu ghi SPFILE nhưng instance không dùng SPFILE | Xác nhận PFILE startup; tạo/chuyển sang SPFILE |
| ORA-02095 | Parameter không thể thay đổi động | Dùng SCOPE=SPFILE và restart nếu tài liệu yêu cầu |
| ORA-01078 khi startup | Parameter file sai/không hợp lệ | Đọc alert log, sửa PFILE/khôi phục SPFILE |
| Instance không mount | CONTROL_FILES hoặc tham số nền tảng sai | Dùng PFILE backup đã xác nhận |
| RAC instance dùng giá trị khác nhau | SID-specific override hoặc wildcard | Xem V$SPPARAMETER và GV$SYSTEM_PARAMETER |
| DBA đọc SPFILE bằng editor thấy ký tự lạ | SPFILE là binary | Xuất PFILE để đọc |
| PFILE sửa nhưng runtime không đổi | Instance đã chạy và không nạp lại file | ALTER SYSTEM hoặc restart bằng PFILE |
| BOTH không áp dụng parameter static | Parameter không dynamic | Dùng SPFILE và restart |
| Runtime khác SPFILE | SCOPE=MEMORY, session override, auto-adjust hoặc SID khác | So sánh V$PARAMETER, V$SYSTEM_PARAMETER, V$SPPARAMETER |

## 18. Quy trình thay đổi và rollback đề xuất

### Trước thay đổi

1. Xác định parameter, mục đích và giá trị mục tiêu.
2. Kiểm tra ISSYS_MODIFIABLE, ISSES_MODIFIABLE và ISINSTANCE_MODIFIABLE.
3. Xác định PFILE hay SPFILE đang được dùng.
4. Với RAC, kiểm tra SID wildcard và instance overrides.
5. Backup SPFILE thành PFILE và lưu cấu hình hiện tại.
6. Kiểm tra tài nguyên, dependency và restart requirement.
7. Xác định rollback command/file.

### Khi thay đổi

1. Chọn SCOPE tường minh.
2. Chọn SID đúng phạm vi.
3. Thực hiện câu ALTER SYSTEM hoặc sửa PFILE theo kế hoạch.
4. Ghi log command, operator và thời điểm.
5. Kiểm tra V$SYSTEM_PARAMETER hoặc V$SPPARAMETER tương ứng.

### Sau thay đổi

1. Nếu dynamic, kiểm tra hiệu lực runtime.
2. Nếu deferred, xác minh session mới.
3. Nếu static, restart theo change window.
4. Kiểm tra giá trị sau startup.
5. Kiểm tra alert log và database status.
6. Theo dõi workload và ứng dụng.
7. Cập nhật build/configuration manifest.

### Rollback

1. Dùng giá trị cũ đã lưu hoặc PFILE backup.
2. Chọn đúng SCOPE và SID để phục hồi.
3. Nếu static, restart lại theo kế hoạch.
4. Kiểm tra cả runtime và persistent value.
5. Xác nhận database và application trở lại trạng thái ổn định.

## 19. Bài thực hành: PFILE, SPFILE và SCOPE

Thực hiện trong database lab hoặc môi trường staging có quyền SYSDBA phù hợp. Không thực hành restart hoặc sửa parameter static trên production ngoài change process.

### Bước 1 — Xác định startup file

```sql
SHOW PARAMETER spfile;
SELECT name, value FROM v$parameter WHERE name = 'spfile';
```

Ghi nhận instance dùng SPFILE hay PFILE.

### Bước 2 — Xem một số parameter

```sql
SELECT name, value, issys_modifiable,
       isses_modifiable, isinstance_modifiable
FROM v$parameter
WHERE name IN ('open_cursors', 'processes', 'optimizer_mode');
```

Ghi lại parameter nào dynamic, deferred hoặc static.

### Bước 3 — Export PFILE

```sql
CREATE PFILE='/u01/backup/init_lab_before.ora'
FROM SPFILE;
```

Đọc file PFILE, ghi nhận các parameter đã được cấu hình.

### Bước 4 — Thử SCOPE=MEMORY

Chọn một parameter dynamic an toàn trong lab. Ghi giá trị ban đầu, thay đổi bằng SCOPE=MEMORY và kiểm tra V$SYSTEM_PARAMETER. Sau đó restart lab và xác nhận giá trị tạm không còn được duy trì nếu SPFILE không có giá trị tương ứng.

### Bước 5 — Thử SCOPE=SPFILE

Chọn parameter dynamic hoặc static phù hợp. Dùng SCOPE=SPFILE, kiểm tra V$SPPARAMETER và xác nhận giá trị runtime hiện tại chưa thay đổi. Restart theo kế hoạch rồi kiểm tra lại runtime.

### Bước 6 — Thử SCOPE=BOTH

Với một parameter dynamic an toàn, đặt SCOPE=BOTH. So sánh V$SYSTEM_PARAMETER và V$SPPARAMETER trước/sau, sau đó restart lab để xác nhận giá trị vẫn được giữ.

### Bước 7 — So sánh PFILE và SPFILE

Export PFILE lần nữa và so sánh với bản trước. Ghi nhận các thay đổi đã lưu. Không sửa trực tiếp binary SPFILE.

### Bước 8 — Thử parameter static

Trong lab, chọn parameter được tài liệu xác định là static. Thử SCOPE=SPFILE, kiểm tra giá trị lưu và lên kế hoạch restart. Không cố dùng MEMORY để áp dụng static parameter.

### Bước 9 — Thử RESET

Tạo một override thử nghiệm trong SPFILE, dùng ALTER SYSTEM RESET với đúng SID, rồi xem V$SPPARAMETER. Xác nhận giá trị wildcard/default được dùng theo quy tắc sau restart.

### Bước 10 — RAC (nếu có)

Trong lab RAC, đặt một giá trị wildcard và một giá trị SID-specific. Kiểm tra V$SPPARAMETER, GV$SYSTEM_PARAMETER trên từng instance. Xác nhận instance override được áp dụng như mong muốn.

### Bước 11 — Ghi kết quả

| Thử nghiệm | Runtime value trước | SPFILE value trước | SCOPE | Runtime sau | SPFILE sau | Sau restart |
|---|---|---|---|---|---|---|
| MEMORY |  |  | MEMORY |  |  |  |
| SPFILE |  |  | SPFILE |  |  |  |
| BOTH |  |  | BOTH |  |  |  |
| Static parameter |  |  | SPFILE |  |  |  |
| RESET |  |  | SPFILE |  |  |  |

Điền kết quả thật của lab; không dùng giá trị minh họa trong tài liệu làm số đo.

## 20. Checklist vận hành

- [ ] Đã xác định instance đang dùng PFILE hay SPFILE.
- [ ] Đã backup cấu hình trước thay đổi.
- [ ] Không chỉnh sửa trực tiếp binary SPFILE.
- [ ] Đã kiểm tra ISSYS_MODIFIABLE và ISSES_MODIFIABLE.
- [ ] Đã phân biệt dynamic, deferred và static parameter.
- [ ] Đã chọn SCOPE=MEMORY/SPFILE/BOTH tường minh.
- [ ] Đã xác định thay đổi có cần restart không.
- [ ] Đã kiểm tra V$PARAMETER/V$SYSTEM_PARAMETER cho runtime value.
- [ ] Đã kiểm tra V$SPPARAMETER cho persistent value.
- [ ] Đã kiểm tra ISDEFAULT/ISSPECIFIED và SID.
- [ ] Với RAC, đã kiểm tra wildcard và per-instance overrides.
- [ ] Đã xác minh giá trị trên từng instance sau thay đổi.
- [ ] Đã xem alert log sau restart.
- [ ] Có PFILE backup hoặc phương án recovery.
- [ ] Có rollback command/file và change record.
- [ ] Đã kiểm tra ứng dụng và workload sau thay đổi.
- [ ] Không nhầm SCOPE=MEMORY với ALTER SESSION.
- [ ] Không giả định thay đổi SPFILE-only đã có hiệu lực runtime.

## 21. Câu hỏi tự kiểm tra

1. PFILE và SPFILE khác nhau ở định dạng và cách quản lý nào?
2. Oracle dùng parameter file ở bước nào của startup?
3. Làm thế nào xác định instance đang dùng SPFILE?
4. Vì sao không nên chỉnh sửa SPFILE bằng text editor?
5. Khi nào nên dùng PFILE để startup?
6. CREATE PFILE FROM SPFILE có mục đích gì?
7. CREATE SPFILE FROM PFILE được dùng trong tình huống nào?
8. Vì sao tạo SPFILE mới không tự chuyển instance đang chạy từ PFILE sang SPFILE?
9. SCOPE=MEMORY thay đổi nơi nào?
10. Vì sao thay đổi MEMORY mất sau restart?
11. SCOPE=SPFILE có tác động gì tới runtime value hiện tại?
12. SCOPE=BOTH phù hợp với loại parameter nào?
13. Giá trị mặc định của SCOPE phụ thuộc startup file ra sao?
14. Parameter có ISSYS_MODIFIABLE=FALSE cần xử lý thế nào?
15. IMMEDIATE và DEFERRED khác nhau ra sao?
16. ISSES_MODIFIABLE cho biết điều gì?
17. V$PARAMETER, V$SYSTEM_PARAMETER và V$SPPARAMETER khác nhau ở nguồn giá trị nào?
18. ISSPECIFIED và ISDEFAULT giúp xác định điều gì?
19. SID='*' và SID='instance_name' có ý nghĩa gì trong RAC?
20. Vì sao cần kiểm tra wildcard và SID-specific overrides?
21. ORA-32001 thường xuất hiện trong trường hợp nào?
22. ORA-02095 gợi ý điều gì về parameter?
23. ALTER SYSTEM RESET loại bỏ loại cấu hình nào?
24. Làm thế nào phục hồi khi SPFILE chứa giá trị khiến instance không startup?
25. Vì sao cần backup PFILE trước khi thay đổi SPFILE?
26. Khi nào dùng SCOPE=MEMORY để thử nghiệm?
27. Làm thế nào xác nhận thay đổi dynamic đã có hiệu lực?
28. Vì sao phải xem alert log sau khi restart?
29. Resource Manager/Clusterware có vai trò gì khi quản lý SPFILE trong RAC?
30. Những thông tin nào phải ghi lại trong change record parameter?

**Nguyên tắc cần nhớ:** PFILE là file văn bản; SPFILE là file nhị phân do Oracle quản lý. SCOPE=MEMORY chỉ đổi runtime, SCOPE=SPFILE chỉ lưu cho lần startup sau, còn SCOPE=BOTH thay đổi cả hai khi parameter cho phép. Kiểm tra ISSYS_MODIFIABLE để phân biệt immediate, deferred và static; parameter static cần restart. Trong RAC, xem cả SID='*' và override theo instance. Luôn backup cấu hình, đặt SCOPE/SID tường minh, xác minh V$SYSTEM_PARAMETER cùng V$SPPARAMETER và giữ PFILE recovery trước khi thay đổi quan trọng.
