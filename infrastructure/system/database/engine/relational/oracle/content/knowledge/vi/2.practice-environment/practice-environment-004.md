# Cấu trúc thư mục `ORACLE_HOME`, `ORACLE_BASE` và vùng dữ liệu

## 1. Vì sao cần hiểu cấu trúc thư mục của Oracle?

Khi thực hành Oracle Database, bạn sẽ gặp các đường dẫn chứa chương trình `sqlplus`, cấu hình kết nối `tnsnames.ora`, dữ liệu của database, log chẩn đoán hoặc bản sao lưu. Những thành phần này **không nằm chung một chỗ theo quy tắc cố định**. Nếu nhầm thư mục cài phần mềm với nơi chứa dữ liệu, bạn có thể tìm nhầm file, cấu hình sai biến môi trường hoặc vô tình tác động đến dữ liệu khi bảo trì.

Ba khái niệm cần phân biệt ngay từ đầu:

- **`ORACLE_HOME`**: thư mục gốc của **một bộ phần mềm Oracle được cài đặt**, chứa chương trình thực thi, thư viện và nhiều tệp hỗ trợ.
- **`ORACLE_BASE`**: thư mục gốc **của cây thư mục phục vụ cài đặt và vận hành Oracle** theo quy ước Oracle; có thể chứa vị trí chẩn đoán, quản trị và các thư mục thuộc một hay nhiều Oracle home.
- **Vùng dữ liệu của database**: nơi đặt **các tệp dữ liệu và tệp phục vụ khôi phục**. Vùng này được cấu hình độc lập, có thể ở filesystem, ASM hoặc dịch vụ lưu trữ được Oracle hỗ trợ, và **không bắt buộc nằm dưới `ORACLE_BASE`**.

Trong chương “Môi trường thực hành”, mục tiêu của bài này là nhận diện đúng từng khu vực, tự tra cứu các đường dẫn trên máy thực hành, hiểu quan hệ giữa đường dẫn hệ điều hành và tham số Oracle, đồng thời biết những thao tác kiểm tra nào là an toàn.

> Lưu ý phạm vi: các ví dụ chính sử dụng Oracle Database chạy trên Linux và đường dẫn giả định cho môi trường học tập. Bản cài đặt Windows, container, Oracle Grid Infrastructure/ASM hoặc môi trường do nhà cung cấp quản lý có thể dùng cấu trúc khác. Hãy **kiểm tra cấu hình thực tế** trước khi xác định vị trí file.

## 2. Bức tranh tổng thể: phần mềm, thông tin quản trị và dữ liệu

Ví dụ một máy chủ Linux dành riêng cho Oracle Database có thể được bố trí như sau:

```text
/
├── u01/
│   └── app/
│       ├── oraInventory/                  # Central Inventory (ví dụ)
│       └── oracle/                       # ORACLE_BASE (ví dụ)
│           ├── product/
│           │   └── 19.0.0/
│           │       └── dbhome_1/         # ORACLE_HOME
│           │           ├── bin/
│           │           ├── lib/
│           │           ├── rdbms/
│           │           └── network/
│           ├── diag/                     # ADR / log chẩn đoán
│           ├── admin/                    # Một số tệp quản trị, audit
│           └── homes/                    # Có thể có ở read-only home
├── u02/
│   └── oradata/
│       └── LABDB/                         # Vùng dữ liệu minh họa
│           ├── system01.dbf
│           ├── sysaux01.dbf
│           ├── users01.dbf
│           ├── undotbs01.dbf
│           ├── temp01.dbf
│           ├── control01.ctl
│           └── redo01.log
└── u03/
    └── fra/
        └── LABDB/                         # Fast Recovery Area minh họa
```

Đây là **sơ đồ minh họa**, không phải danh sách file bắt buộc. Tên, số lượng, vị trí của datafile, control file, redo log và thư mục phục hồi phụ thuộc lúc tạo database, cấu hình quản trị và tính năng đang dùng. Thư mục `u01`, `u02`, `u03` là cách phân chia thường thấy, không phải yêu cầu của Oracle.

| Vùng | Mục đích chính | Ví dụ | Có nên tự xóa/sửa tệp? |
|---|---|---|---|
| Phần mềm | Chứa bộ cài và chương trình Oracle | `/u01/app/oracle/product/19.0.0/dbhome_1` | Không tự sửa file thuộc phần mềm |
| Quản trị/chẩn đoán | Log, trace, audit, cấu hình theo mô hình triển khai | `/u01/app/oracle/diag` | Chỉ quản lý theo quy trình vận hành |
| Dữ liệu | Datafile, tempfile, control file, online redo log | `/u02/oradata/LABDB` | **Không thao tác trực tiếp khi database quản lý** |
| Phục hồi | Archived redo, backup/flashback file nếu cấu hình vào FRA | `/u03/fra/LABDB` | Dùng RMAN/chính sách của Oracle để quản lý |
| Inventory | Danh sách Oracle home và thông tin cài đặt/patch | `/u01/app/oraInventory` | Không chỉnh bằng tay |

Điểm mấu chốt: **đường dẫn là thuộc tính của môi trường triển khai**. Không thể nhìn vào tên thư mục `ORACLE_HOME` để kết luận database đang lưu dữ liệu ở đâu.

## 3. `ORACLE_HOME`: nơi cài phần mềm Oracle

### 3.1. Khái niệm và vai trò

`ORACLE_HOME` thường chỉ đường dẫn đến **một Oracle home**, chẳng hạn:

```bash
export ORACLE_HOME=/u01/app/oracle/product/19.0.0/dbhome_1
```

Trong hệ điều hành, `ORACLE_HOME` cũng là tên biến môi trường mà nhiều công cụ Oracle dùng để tìm thư viện, chương trình và tệp cấu hình liên quan. Một máy chủ có thể có nhiều home khác nhau, ví dụ `dbhome_1` và `dbhome_2` cho những bộ cài hoặc giai đoạn chuyển đổi phiên bản khác nhau. Oracle Database home và Grid Infrastructure home cũng có thể riêng biệt.

Một số thư mục con thường thấy:

| Thư mục dưới `ORACLE_HOME` | Nội dung/vai trò thường gặp |
|---|---|
| `bin/` | Chương trình như `sqlplus`, `lsnrctl`, `rman`, `dbca` tùy loại home và phiên bản |
| `lib/` | Thư viện dùng bởi các thành phần Oracle |
| `rdbms/admin/` | Các script SQL và tài nguyên quản trị RDBMS |
| `network/admin/` | Vị trí mặc định truyền thống của một số tệp Oracle Net, khi không có chỉ định khác |
| `dbs/` (Linux/Unix) | Một số tệp liên quan instance như `spfile`, password file trong cấu hình thông thường; vị trí thực tế có thể khác |
| `OPatch/` | Công cụ/hạ tầng áp dụng patch tùy bộ cài |

Ví dụ `ORACLE_HOME/bin/sqlplus` là **chương trình máy khách SQL*Plus**, không phải tệp bảng dữ liệu. `ORACLE_HOME/rdbms/admin` chứa script hỗ trợ database, không phải vùng dành cho các bảng của ứng dụng.

### 3.2. Kiểm tra Oracle home đang dùng trên Linux

Trong terminal đang được cấu hình để dùng Oracle, chạy các lệnh **chỉ đọc**:

```bash
printf 'ORACLE_HOME=%s\n' "$ORACLE_HOME"
printf 'ORACLE_BASE=%s\n' "$ORACLE_BASE"
printf 'ORACLE_SID=%s\n' "$ORACLE_SID"

command -v sqlplus
test -d "$ORACLE_HOME" && ls -ld "$ORACLE_HOME"
test -x "$ORACLE_HOME/bin/sqlplus" && "$ORACLE_HOME/bin/sqlplus" -V
```

`command -v sqlplus` cho biết chương trình được tìm qua `PATH`; nếu `PATH` trỏ đến home khác, kết quả có thể không khớp với `ORACLE_HOME`. Khi điều tra nhầm phiên bản phần mềm, đây là một kiểm tra rất hữu ích.

Ví dụ thiết lập cho **một phiên shell thực hành**:

```bash
export ORACLE_BASE=/u01/app/oracle
export ORACLE_HOME=/u01/app/oracle/product/19.0.0/dbhome_1
export ORACLE_SID=LABDB
export PATH="$ORACLE_HOME/bin:$PATH"
```

Đây chỉ là giá trị giả định. Không sao chép nguyên đường dẫn vào máy thật nếu Oracle đã được cài ở nơi khác. Đặt biến môi trường không tạo ra Oracle home hay instance; nó chỉ thay đổi cách các công cụ trong shell định vị và kết nối.

### 3.3. Điểm cần hiểu về `ORACLE_SID`

`ORACLE_HOME` chỉ phần mềm; `ORACLE_SID` thường xác định **instance cục bộ** mà công cụ muốn kết nối tới khi dùng cơ chế kết nối local. `ORACLE_SID` không phải đường dẫn, cũng không đồng nhất với service name của PDB trong kiến trúc multitenant. Ứng dụng kết nối qua listener thường sử dụng **service name** trong connect descriptor.

Trên máy chỉ cài SQL*Plus hoặc Oracle Instant Client, đường dẫn phần mềm máy khách cũng không cho biết home của database ở máy chủ từ xa. Khi cần xác định nơi lưu dữ liệu của server, hãy truy vấn database hoặc hỏi DBA, thay vì suy từ `ORACLE_HOME` trên máy ứng dụng.

## 4. `ORACLE_BASE`: gốc của khu vực cài đặt và vận hành

Theo cách tổ chức thường thấy trên Linux, `ORACLE_BASE` có giá trị như:

```text
ORACLE_BASE=/u01/app/oracle
```

`ORACLE_BASE` có thể chứa nhiều thành phần của cùng một chủ sở hữu phần mềm Oracle (*Oracle software owner*), bao gồm các home trong `product/`, thông tin chẩn đoán trong `diag/` và một số thư mục quản trị/audit trong `admin/`. Theo các quy ước triển khai, một số dữ liệu hoặc tệp phục hồi cũng có thể đặt bên dưới base, **nhưng đây không phải mối quan hệ bắt buộc**.

Một số vị trí cần phân biệt:

| Đường dẫn ví dụ | Ý nghĩa | Điều cần nhớ |
|---|---|---|
| `$ORACLE_BASE/product/...` | Oracle home | Phần mềm cài đặt; một base có thể có nhiều home |
| `$ORACLE_BASE/diag/...` | **ADR — Automatic Diagnostic Repository** | Vị trí log/trace chẩn đoán, cấu trúc phụ thuộc database/instance/listener |
| `$ORACLE_BASE/admin/.../adump` | Audit files theo cấu hình | Không phải datafile của bảng |
| `$ORACLE_BASE/homes/...` | Cấu hình/ghi runtime của read-only Oracle home trong một số phiên bản và cấu hình | Dùng công cụ Oracle để xác định chính xác |

Một đường dẫn ADR cho database có thể có dạng:

```text
/u01/app/oracle/diag/rdbms/labdb/LABDB/trace/
```

Tại đây có thể xuất hiện alert log dưới dạng text, trace do tiến trình Oracle ghi, và các thông tin dùng khi điều tra sự cố. Tên từng cấp được hình thành theo tên database/instance thực tế. Không giả định cứ có `ORACLE_BASE` là chắc chắn có đường dẫn này; tham số `DIAGNOSTIC_DEST` và cấu hình ADR mới cho biết vị trí hoạt động.

### `ORACLE_BASE` và `ORACLE_HOME` khác nhau thế nào?

```text
ORACLE_BASE  → Vùng gốc tổ chức một số cài đặt và dữ liệu vận hành
     └── ORACLE_HOME  → Một bộ phần mềm Oracle cụ thể
```

Trong sơ đồ thường gặp này, `ORACLE_HOME` là một thư mục nằm dưới `ORACLE_BASE`, nhưng không nên coi là một quan hệ tuyệt đối trong mọi môi trường. Điều quan trọng hơn vị trí lồng nhau là **vai trò**: base giúp tổ chức các khu vực, còn home xác định bộ phần mềm đang chạy.

## 5. Read-only Oracle home và các đường dẫn bổ sung

Ở các phiên bản Oracle hiện đại, môi trường có thể cấu hình **read-only Oracle home** để hạn chế những tệp cấu hình và dữ liệu thay đổi trong thư mục chứa phần mềm. Khi đó cần hiểu thêm hai khái niệm:

- **`ORACLE_BASE_HOME`**: vị trí các tệp mang tính cấu hình/trạng thái của một home thay vì viết ngay dưới software home.
- **`ORACLE_BASE_CONFIG`**: vị trí cấu hình chung được Oracle xác định cho cách triển khai đó.

Các đường dẫn trả về phụ thuộc phiên bản và mô hình cài đặt. Không suy luận đường dẫn bằng cách ghép chuỗi thủ công. Khi các tiện ích có sẵn, có thể kiểm tra:

```bash
"$ORACLE_HOME/bin/orabase"
"$ORACLE_HOME/bin/orabasehome"
"$ORACLE_HOME/bin/orabaseconfig"
```

`orabasehome` và `orabaseconfig` liên quan những bản cài đặt có hỗ trợ cơ chế tương ứng; nếu không tìm thấy trên phiên bản cũ, đó chưa đủ để kết luận môi trường lỗi. Trước khi chạy hãy kiểm tra file công cụ có tồn tại. Một số tệp trước đây đặt dưới `$ORACLE_HOME/network/admin` hoặc `$ORACLE_HOME/dbs` có thể được đặt trong các vị trí cấu hình được chuyển hướng ở read-only home.

**Ý nghĩa thực hành:** khi sửa cấu hình Oracle Net hoặc truy tìm SPFILE, đừng chỉ tìm ở `ORACLE_HOME` theo ví dụ cổ điển. Hãy kiểm tra đường dẫn cấu hình mà home đang sử dụng, và nếu cần thì hỏi DBA hoặc đối chiếu tài liệu dành cho đúng phiên bản.

## 6. Vùng dữ liệu: nơi database thật sự lưu thông tin

Vùng dữ liệu là nơi chứa các tệp Oracle tự quản lý. Đường dẫn có thể giống `/u02/oradata/LABDB/...`, nhưng cũng có thể là đường dẫn khác hoàn toàn, thậm chí là **tên file trong ASM**, chẳng hạn `+DATA/LABDB/...` thay cho đường dẫn filesystem.

### 6.1. Các loại tệp quan trọng

| Loại tệp | Công dụng chính | Ví dụ minh họa |
|---|---|---|
| **Datafile** | Chứa dữ liệu trong các tablespace: bảng, index và cấu trúc lưu trữ khác | `system01.dbf`, `users01.dbf` |
| **Tempfile** | Cung cấp vùng làm việc tạm cho các thao tác cần temporary tablespace | `temp01.dbf` |
| **Control file** | Metadata quan trọng về cấu trúc database và trạng thái liên quan khôi phục | `control01.ctl` |
| **Online redo log** | Lưu thông tin thay đổi để hỗ trợ phục hồi; được tổ chức thành các nhóm redo | `redo01.log` |
| **Archived redo log** | Bản lưu của redo log đã chuyển vòng khi database chạy ở `ARCHIVELOG` mode; dùng cho phục hồi | Các file archive theo cấu hình |
| **SPFILE / PFILE** | Cấu hình tham số khởi động instance | `spfileLABDB.ora`, `initLABDB.ora` |
| **Password file** | Hỗ trợ xác thực quyền quản trị đặc biệt khi được cấu hình | `orapwLABDB` trong bố trí thông thường trên Linux |
| **Backup / image copy** | Bản sao phục vụ phục hồi, thường quản lý qua RMAN | File backup trong vị trí được cấu hình |

**Đừng nhầm:** `tablespace` là đơn vị lưu trữ *logic* của Oracle; `datafile` là thành phần *vật lý* hoặc tệp lưu trữ được Oracle quản lý. Một tablespace có thể có nhiều datafile. Bảng của người dùng thuộc schema và được đặt trong segment/tablespace; thông thường không có một file riêng tên `CUSTOMERS.dbf` cho bảng `CUSTOMERS`.

Datafile của các tablespace hệ thống (`SYSTEM`, `SYSAUX`), undo tablespace, tablespace ứng dụng và temporary tablespace có vai trò khác nhau. Việc thấy nhiều file `.dbf` không có nghĩa tất cả đều chứa bảng nghiệp vụ.

### 6.2. Oracle Managed Files (OMF) và ASM

Với **Oracle Managed Files (OMF)**, Oracle có thể tự đặt tên và quản lý một số file database dựa trên vị trí cấu hình, thay vì DBA tự đặt tên file cho mỗi thao tác tạo tablespace hoặc redo log. Tham số thường cần xem là `DB_CREATE_FILE_DEST`.

Với **Automatic Storage Management (ASM)**, Oracle có thể lưu database file trong disk group như `+DATA` và `+RECO`. Các tên đó là đường dẫn logic do ASM quản lý, **không phải thư mục Linux thông thường** để mở bằng `ls /...` hoặc chép/xóa như file thường. Cần dùng công cụ và câu lệnh Oracle phù hợp để quản trị.

Với kiến trúc **CDB/PDB**, có thể có các file cho CDB và từng PDB; việc một PDB kết nối bằng service riêng không đồng nghĩa dữ liệu của nó phải nằm trong một thư mục riêng theo tên service. Luôn lấy danh sách file từ database thay vì tự suy đoán theo tên PDB.

### 6.3. Fast Recovery Area (FRA) có phải là vùng dữ liệu chính?

**Không.** FRA là vùng do Oracle quản lý dành cho một số tệp phục vụ backup và phục hồi, như archived redo, flashback logs và backup pieces tùy tính năng/cấu hình. Vị trí FRA được xác định bởi `DB_RECOVERY_FILE_DEST`; mức dung lượng mục tiêu được chỉ định bằng `DB_RECOVERY_FILE_DEST_SIZE`.

Ví dụ:

```text
Datafiles, online redo (ví dụ): /u02/oradata/LABDB/
FRA (ví dụ):                    /u03/fra/
```

Hai vùng có mục đích khác nhau. Nếu FRA đầy, hoạt động tạo archived redo và một số hoạt động database có thể bị ảnh hưởng nghiêm trọng. Việc giải phóng không gian phải tuân theo chính sách backup/retention và công cụ Oracle, không tùy tiện xóa archived redo bằng lệnh hệ điều hành.

## 7. Xác định vị trí bằng biến môi trường và tham số database

Biến môi trường của shell phản ánh **ngữ cảnh tiến trình sử dụng công cụ**. Các tham số và view của database cho biết **cấu hình đang được instance/database sử dụng**. Hai nguồn thông tin này trả lời các câu hỏi khác nhau:

| Câu hỏi | Nơi kiểm tra |
|---|---|
| Terminal hiện dùng Oracle home nào? | `$ORACLE_HOME`, `PATH`, `command -v sqlplus` |
| Thư mục base được công cụ xác định ở đâu? | `$ORACLE_BASE`, tiện ích `orabase` nếu có |
| Local instance mặc định của phiên shell là gì? | `$ORACLE_SID` |
| Tệp datafile đang nằm ở đâu? | `V$DATAFILE`, `DBA_DATA_FILES` |
| Các control file đang ở đâu? | `V$CONTROLFILE`, tham số `CONTROL_FILES` |
| Các thành viên online redo log ở đâu? | `V$LOGFILE` |
| Vùng OMF/FRA cấu hình ở đâu? | `DB_CREATE_FILE_DEST`, `DB_RECOVERY_FILE_DEST` |
| Log/trace Oracle ghi ở đâu? | `V$DIAG_INFO`, tham số `DIAGNOSTIC_DEST` |
| Tệp cấu hình Oracle Net ở đâu? | Cấu hình Oracle Net đang dùng, `TNS_ADMIN` nếu có và cơ chế read-only home |

### 7.1. Kiểm tra từ terminal Linux

```bash
# Xem biến môi trường của phiên shell hiện tại
printf 'HOME=%s\nBASE=%s\nSID=%s\n' "$ORACLE_HOME" "$ORACLE_BASE" "$ORACLE_SID"

# Xem phần mềm và thư mục hiện có (không thay đổi file)
ls -ld "$ORACLE_HOME" "$ORACLE_HOME/bin"
ls -ld "$ORACLE_BASE" "$ORACLE_BASE/diag"

# Kiểm tra không gian các filesystem chứa vùng được cấu hình
df -h /u01 /u02 /u03
```

Lệnh `df -h /u01 /u02 /u03` chỉ có ý nghĩa nếu các đường dẫn đó thực sự tồn tại trong máy đang dùng. Nếu vùng dữ liệu được đặt qua ASM, `df` trên filesystem Linux không biểu diễn dung lượng disk group ASM.

### 7.2. Kiểm tra bằng SQL từ một phiên có quyền phù hợp

Kết nối vào database bằng SQL*Plus, SQLcl hoặc công cụ SQL tương thích. Người thực hành cần được cấp quyền đối với các dynamic performance views (`V$...`) hoặc dictionary views tương ứng; tài khoản ứng dụng hạn chế quyền có thể không truy cập được. Ví dụ sau là **SQL** gửi tới database, không chạy như câu lệnh shell:

```sql
-- Tham số liên quan vị trí và khả năng khôi phục
SELECT name, value
FROM v$parameter
WHERE name IN (
    'db_create_file_dest',
    'db_recovery_file_dest',
    'db_recovery_file_dest_size',
    'diagnostic_dest',
    'control_files',
    'audit_file_dest'
)
ORDER BY name;
```

Tham số trả giá trị rỗng không có nghĩa database không có tệp tương ứng: có thể đường dẫn mặc định do Oracle xác định, hoặc file cụ thể được chỉ định ở cấp đối tượng. **Danh sách file thực tế vẫn là nguồn đáng tin cậy hơn một đường dẫn ví dụ.**

```sql
-- Vị trí datafile và tempfile
SELECT name FROM v$datafile ORDER BY name;
SELECT name FROM v$tempfile ORDER BY name;

-- Vị trí control file và thành viên online redo log
SELECT name FROM v$controlfile ORDER BY name;
SELECT group#, member FROM v$logfile ORDER BY group#, member;

-- Vị trí chẩn đoán/trace được database công bố
SELECT name, value FROM v$diag_info ORDER BY name;
```

Nếu có quyền đối với dictionary views, có thể xem tablespace tương ứng với datafile và tempfile:

```sql
SELECT tablespace_name, file_name
FROM dba_data_files
ORDER BY tablespace_name, file_name;

SELECT tablespace_name, file_name
FROM dba_temp_files
ORDER BY tablespace_name, file_name;
```

Trong SQL*Plus, `SHOW PARAMETER` là một lệnh hỗ trợ tiện tra cứu:

```sql
SHOW PARAMETER db_create_file_dest
SHOW PARAMETER db_recovery_file_dest
SHOW PARAMETER diagnostic_dest
```

`SHOW PARAMETER` không phải câu lệnh SQL tiêu chuẩn để đưa trực tiếp vào mọi driver JDBC. Với chương trình Java hoặc công cụ chỉ hỗ trợ SQL thuần, dùng `SELECT` trên các view thích hợp.

### 7.3. Phân biệt đường dẫn thực tế và đường dẫn từ tham số

Giả sử `DB_CREATE_FILE_DEST` là `+DATA`; các giá trị `V$DATAFILE.NAME` có thể giống `+DATA/LABDB/...`. Khi đó không tìm file bằng `ls /u02/oradata` nữa. Ngược lại, `DB_CREATE_FILE_DEST` có thể rỗng, nhưng `V$DATAFILE` vẫn chỉ rõ datafile nằm ở filesystem như `/u02/oradata/LABDB/system01.dbf`.

Tương tự, tham số `DIAGNOSTIC_DEST` chỉ nơi chứa ADR gốc; truy vấn `V$DIAG_INFO` thường hữu ích hơn để xác định đường dẫn trace hoặc alert log cụ thể của instance đang kết nối.

## 8. Các tệp Oracle Net: nằm ở đâu và dùng để làm gì?

Oracle Net quản lý phần cấu hình liên quan kết nối giữa client và database. Ba tên thường gặp:

| Tệp | Vai trò điển hình |
|---|---|
| `tnsnames.ora` | Ánh xạ alias kết nối sang connect descriptor, host, port và service name |
| `sqlnet.ora` | Thiết lập Oracle Net phía client/server tùy môi trường, ví dụ phương pháp phân giải tên và bảo mật |
| `listener.ora` | Thiết lập listener trên máy chủ khi cần cấu hình tĩnh hoặc tùy chỉnh |

Với bố trí truyền thống, các tệp này có thể ở:

```text
$ORACLE_HOME/network/admin/
```

Nhưng thư mục thực tế có thể bị ảnh hưởng bởi `TNS_ADMIN`, cơ chế read-only home, cách đóng gói client hoặc cấu hình nền tảng. `TNS_ADMIN` thường chỉ **thư mục chứa cấu hình Oracle Net**, không phải thư mục datafile.

Ví dụ một `tnsnames.ora` dành cho môi trường học tập:

```text
LABPDB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db.example.internal)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = labpdb.example.internal))
  )
```

`HOST`, `PORT` và `SERVICE_NAME` là ví dụ; cấu hình thật do người quản trị cung cấp. Một alias như `LABPDB` là tên kết nối logic, **không phải tên folder** hay vị trí lưu file PDB. Listener có nhiệm vụ tiếp nhận và định tuyến yêu cầu kết nối đến database service; listener không phải nơi chứa dữ liệu bảng.

## 9. `oraInventory`, `oratab` và các đường dẫn thường bị hiểu nhầm

Ngoài `ORACLE_BASE` và `ORACLE_HOME`, có vài vị trí quan trọng liên quan việc cài và quản trị:

| Thành phần | Thường xuất hiện ở đâu? | Mục đích |
|---|---|---|
| **Central Inventory (`oraInventory`)** | Ví dụ `/u01/app/oraInventory` | Theo dõi Oracle home và thông tin cài đặt/patch; có thể được nhiều home sử dụng |
| **`oraInst.loc`** (Linux/Unix) | Một số hệ thống dùng `/etc/oraInst.loc` | Trỏ đến inventory và nhóm sở hữu inventory |
| **`oratab`** (Linux/Unix) | Tùy hệ điều hành, thường `/etc/oratab` | Danh sách SID và home phục vụ công cụ khởi động/quản trị, không chứa dữ liệu bảng |
| **ADR** | Dưới diagnostic destination | Log và trace chẩn đoán database/listener |
| **`adump`** | Theo `AUDIT_FILE_DEST` | Một số tệp audit của database |
| **Oracle wallet / tệp bảo mật** | Theo cấu hình Oracle Net hoặc sản phẩm | Chứng chỉ, khóa, bí mật liên quan tính năng bảo mật |

Tệp `oraInventory` không phải backup của database; mất inventory có thể làm hỏng khả năng quản lý cài đặt hoặc patch. Tương tự, một mục trong `oratab` không chứng minh rằng database tương ứng đang chạy hoặc các file của nó còn nguyên. Những file này phục vụ quản trị hệ thống, không thay thế việc truy vấn trạng thái database.

## 10. Bài thực hành: tự lập bản đồ đường dẫn Oracle

**Bối cảnh giả định:** bạn có một máy Linux đã cài Oracle Database, có quyền xem các biến môi trường và một tài khoản được phép thực hiện truy vấn hệ thống. Bài tập chỉ yêu cầu đọc và ghi chú kết quả; không tạo, di chuyển hoặc xóa bất kỳ database file nào.

### Bước 1. Nhận diện bộ phần mềm đang sử dụng

Từ phiên shell đã cấu hình Oracle, chạy:

```bash
printf '%s\n' "$ORACLE_HOME" "$ORACLE_BASE" "$ORACLE_SID"
command -v sqlplus
"$ORACLE_HOME/bin/sqlplus" -V
```

Ghi nhận giá trị thực tế và xác định `sqlplus` từ `PATH` có trỏ đến đúng home mong muốn hay không. Nếu máy không có lệnh hoặc biến rỗng, đó có thể là do bạn đang ở terminal chưa cấu hình môi trường hoặc ở máy chỉ có client; hãy xác nhận môi trường thay vì tự điền giá trị đoán trước.

### Bước 2. Quan sát các thư mục cấu thành home và base

```bash
ls -ld "$ORACLE_HOME/bin" "$ORACLE_HOME/rdbms"
ls -ld "$ORACLE_BASE" "$ORACLE_BASE/diag"
```

Nếu một thư mục không tồn tại, ghi nhận kết quả và kiểm tra bố trí home thực tế; không tự tạo `diag` hay `rdbms` để “sửa” đầu ra. Với read-only home, dùng công cụ như `orabasehome`/`orabaseconfig` nếu có để xác định vị trí cấu hình.

### Bước 3. Ghi lại vị trí file từ database

Đăng nhập bằng công cụ SQL và quyền phù hợp, sau đó chạy:

```sql
SELECT name FROM v$datafile ORDER BY name;
SELECT name FROM v$controlfile ORDER BY name;
SELECT group#, member FROM v$logfile ORDER BY group#, member;
SELECT name, value FROM v$diag_info ORDER BY name;
```

Ghi kết quả vào bảng so sánh (tự điền đường dẫn của bạn):

| Hạng mục | Bạn tra ở đâu? | Giá trị trong môi trường thực hành |
|---|---|---|
| Software home | `$ORACLE_HOME` | ... |
| Base | `$ORACLE_BASE` hoặc `orabase` | ... |
| Datafile | `V$DATAFILE` | ... |
| Control file | `V$CONTROLFILE` | ... |
| Online redo | `V$LOGFILE` | ... |
| Trace/alert | `V$DIAG_INFO` | ... |
| FRA (nếu có) | `DB_RECOVERY_FILE_DEST` | ... |

### Bước 4. Giải thích kết quả bằng chính môi trường của bạn

Trả lời lần lượt:

1. `ORACLE_HOME` có nằm dưới `ORACLE_BASE` không? Điều đó cho biết gì về bố trí của máy bạn?
2. Đường dẫn datafile có trùng `ORACLE_HOME` không? Nếu không, database vẫn chạy được vì sao?
3. Có tìm được `V$DATAFILE.NAME` bắt đầu bằng `+DATA` không? Nếu có, vì sao không dùng `ls` để xem trực tiếp như thư mục filesystem thông thường?
4. Log chẩn đoán nằm trong cùng vùng với datafile hay ở vị trí khác?
5. Có FRA được cấu hình không? Nếu không, có thể kết luận database “không có khả năng backup” không? (Không; FRA chỉ là một cơ chế/vị trí quản lý file phục hồi.)

Sau bài thực hành, bạn nên có **một bản đồ đường dẫn đúng với máy mình đang dùng**, thay vì chỉ ghi nhớ đường dẫn minh họa trong tài liệu.

## 11. Khác biệt giữa Linux, Windows, container và môi trường quản lý

### Linux

Quy ước như `/u01/app/oracle` và `/u02/oradata` phổ biến trong ví dụ và tài liệu triển khai. Các thư mục thuộc về tài khoản/phân quyền hệ điều hành phù hợp, ví dụ Oracle software owner; việc chạy công cụ quản trị phụ thuộc quyền tương ứng. Dấu `/` là dấu phân cách đường dẫn Linux, và biến môi trường được truy cập bằng cú pháp `$ORACLE_HOME` trong shell.

### Windows

Đường dẫn có thể ở dạng `C:\app\oracle\product\19.0.0\dbhome_1`, còn biến môi trường trong Command Prompt thường được đọc bằng `%ORACLE_HOME%`. Tên thư mục và cách đăng ký Oracle home khác Linux; một số cấu hình còn được lưu qua cơ chế hệ thống Windows. Vì vậy không chuyển nguyên lệnh Linux `ls`, `export`, `oratab` sang Windows rồi mặc định kết quả tương đương.

### Container và môi trường phát triển

Một image Oracle có thể cài phần mềm ở một đường dẫn trong image, nhưng đặt datafile vào **volume** hoặc bind mount khác để giữ dữ liệu qua vòng đời container. Ví dụ về mặt khái niệm:

```text
Container filesystem:
  /opt/oracle/product/...   → phần mềm (ví dụ)
  /opt/oracle/oradata       → vùng dữ liệu được mount ra volume (ví dụ)

Host / Docker volume:
  [volume đã cấu hình]      → lưu các tệp dữ liệu thực tế
```

Đường dẫn cụ thể tùy image, phiên bản và file cấu hình container. Xóa container không nhất thiết xóa volume, nhưng **xóa volume chứa dữ liệu có thể khiến database mất dữ liệu**, nếu không có bản sao lưu. Khi khảo sát, cần kiểm tra cả đường dẫn **bên trong container** và mount thực tế.

### Môi trường do dịch vụ quản lý

Với các dịch vụ database được quản lý, người dùng có thể không có quyền xem filesystem, `ORACLE_HOME` hoặc tệp vật lý. Việc quan sát sẽ đi qua SQL, giao diện quản trị, log được nhà cung cấp công bố hoặc API. Đây là khác biệt về quyền vận hành, không làm thay đổi các khái niệm logic như datafile, transaction và tablespace.

## 12. Tình huống lỗi thường gặp và cách xác định đúng khu vực

| Biểu hiện | Điều nên kiểm tra đầu tiên | Sai lầm cần tránh |
|---|---|---|
| `sqlplus: command not found` | `PATH`, sự tồn tại của `$ORACLE_HOME/bin/sqlplus`, máy có cài client không | Kết luận database server bị mất dữ liệu |
| Kết nối alias không được phân giải | `TNS_ADMIN`, `tnsnames.ora`, service name và môi trường client | Tìm hoặc sửa datafile để chữa lỗi Oracle Net |
| Đường dẫn `ORACLE_HOME` có vẻ sai | `PATH`, home đang chọn, nhiều home trên máy | Chỉnh/sao chép file tùy ý giữa các home |
| Không tìm thấy datafile trong `/u02/oradata` | `V$DATAFILE`, OMF, ASM, đường dẫn triển khai thật | Tự tạo `.dbf` ở thư mục đang tìm |
| Không thấy alert log ở nơi dự đoán | `V$DIAG_INFO`, `DIAGNOSTIC_DEST`, ADR home | Nghĩ rằng database không có log |
| FRA gần đầy | `DB_RECOVERY_FILE_DEST`, dung lượng FRA, chính sách RMAN | Xóa hàng loạt archived redo bằng `rm` |
| Cài/patch lỗi do inventory | Đường dẫn Central Inventory và quyền sở hữu đúng | Sửa tay `oraInventory` hoặc xóa inventory |

**Nguyên tắc an toàn trong thực hành:** các lệnh `ls`, `printf`, `df` và câu truy vấn `SELECT` phù hợp để khảo sát. Các thao tác như `rm`, `mv`, chỉnh sửa nội dung `.dbf`/`.ctl`/redo log hoặc đổi quyền đệ quy (`chmod -R`) có thể gây hỏng cấu trúc hoặc làm database không khởi động được. Đổi vị trí datafile, quản lý archive, backup và khôi phục phải theo quy trình, câu lệnh và công cụ Oracle chuyên dụng.

## 13. Tổng hợp kiến thức cần ghi nhớ

| Khái niệm | Câu hỏi mà nó trả lời |
|---|---|
| **`ORACLE_HOME`** | Bộ chương trình Oracle mà terminal/tiến trình đang dùng nằm ở đâu? |
| **`ORACLE_BASE`** | Khu vực tổ chức cài đặt và hoạt động Oracle đặt ở đâu? |
| **`ORACLE_BASE_HOME` / `ORACLE_BASE_CONFIG`** | Trong một số kiểu cài đặt, nơi cấu hình/ghi runtime được chuyển ra khỏi software home ở đâu? |
| **`ORACLE_SID`** | Công cụ local đang hướng tới instance nào? |
| **Datafile / tempfile / control file / redo log** | Database đang lưu dữ liệu và thông tin phục hồi ở các file nào? |
| **`DB_CREATE_FILE_DEST`** | Vị trí đích mặc định cho file Oracle quản lý, nếu được cấu hình, là gì? |
| **`DB_RECOVERY_FILE_DEST`** | Vùng phục hồi FRA được cấu hình ở đâu? |
| **`DIAGNOSTIC_DEST`, `V$DIAG_INFO`** | Log và trace chẩn đoán nằm ở đâu? |
| **`TNS_ADMIN`** | Nơi cấu hình Oracle Net được chỉ định ở đâu? |

Hãy nhớ sự phân tách **phần mềm — cấu hình/chẩn đoán — dữ liệu/phục hồi**. `ORACLE_HOME` cho biết bạn chạy bộ chương trình nào; `ORACLE_BASE` giúp tổ chức các vùng phục vụ cài đặt và vận hành; database file lại được xác định bằng tham số và thông tin từ chính Oracle. Biết tra cứu ba khu vực này giúp bạn thiết lập đúng môi trường thực hành, đọc đúng log, tìm đúng tệp và tránh tác động nhầm vào dữ liệu đang được database quản lý.
