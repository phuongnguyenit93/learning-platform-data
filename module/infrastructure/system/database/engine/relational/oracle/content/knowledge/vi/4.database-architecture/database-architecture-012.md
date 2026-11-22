# Đọc kiến trúc từ các dynamic performance view phù hợp

Một sơ đồ kiến trúc Oracle Database thường có **instance**, **SGA**, **PGA**, **server process**, **background process**, **CDB/PDB**, **datafile**, **redo log** và các **session** của ứng dụng. Khi đứng trước một Oracle Database đang chạy, làm thế nào biết các thành phần đó thực sự tồn tại, liên hệ với nhau và đang ở trạng thái nào?

Oracle cung cấp các **dynamic performance view** thường được gọi là **V$ view** (và các **GV$ view** cho môi trường nhiều instance). Đây là cửa sổ quan sát trạng thái runtime của Oracle. Bài học hướng dẫn đọc kiến trúc từ các view thích hợp bằng những câu `SELECT`, giải thích giới hạn của từng kết quả và ghép chúng thành một bức tranh hệ thống.

Mục tiêu không phải nhớ thuộc hàng chục tên view. Điều cần hình thành là một cách hỏi có hệ thống: **muốn quan sát thành phần nào → dùng view nào → cột nào là bằng chứng → có thể và không thể kết luận điều gì?**

## 1. Bức tranh kiến trúc sẽ được kiểm chứng

~~~mermaid
flowchart TD
    A["Ứng dụng / SQL client"] --> B["Oracle Net service và session"]
    B --> C["Server process"]
    C <--> D["SGA: shared pool, buffer cache, redo buffer"]
    C <--> E["PGA: bộ nhớ riêng theo process"]
    C --> F["Các SQL cursor / execution plan"]
    D <--> G["Data block của bảng và chỉ mục"]
    G <--> H["Tablespace / datafile"]
    D --> I["Redo log buffer"]
    I --> J["LGWR → online redo log"]
    K["DBWn, CKPT, SMON, PMON..."] --> D
    K --> H
    C --> L["Container: CDB root hoặc PDB"]
~~~

Sơ đồ là mô hình khái niệm của **một Oracle instance**. Oracle RAC có nhiều instance cùng truy cập database chung; Oracle multitenant có thể chứa nhiều PDB. Không phải mỗi mũi tên đều tương ứng với một tiến trình hay một view riêng, và không phải mọi lần đọc SQL đều cần đọc datafile vật lý.

| Câu hỏi kiến trúc | View phù hợp | Bằng chứng thường đọc |
|---|---|---|
| Instance nào đang phục vụ phiên? | `V$INSTANCE`; RAC: `GV$INSTANCE` | `INSTANCE_NAME`, `HOST_NAME`, `STATUS`, `STARTUP_TIME` |
| Database và vai trò của nó là gì? | `V$DATABASE` | `NAME`, `CDB`, `OPEN_MODE`, `DATABASE_ROLE` |
| Có những container/PDB nào? | `V$CONTAINERS`, `V$PDBS` | `CON_ID`, `NAME`, `OPEN_MODE` |
| SGA được phân bổ như thế nào? | `V$SGAINFO`, `V$SGASTAT` | Tên vùng nhớ, `BYTES`, `POOL` |
| PGA đang tiêu thụ bao nhiêu? | `V$PGASTAT` | `NAME`, `VALUE`, `UNIT` |
| Session ứng dụng gắn với process nào? | `V$SESSION`, `V$PROCESS` | `SID`, `SERIAL#`, `PADDR`, `ADDR`, `SPID` |
| Có loại background process nào? | `V$BGPROCESS` | `NAME`, `DESCRIPTION` |
| Datafile thuộc tablespace nào? | `V$DATAFILE`, `V$TABLESPACE` | `TS#`, `CON_ID`, `NAME` |
| Redo log và control file ở đâu? | `V$LOG`, `V$LOGFILE`, `V$CONTROLFILE` | `GROUP#`, `STATUS`, `MEMBER`, `NAME` |
| SQL nào đang được cache/ghi nhận? | `V$SQLAREA`, `V$SESSION` | `SQL_ID`, `EXECUTIONS`, `BUFFER_GETS`, `DISK_READS` |
| Hoạt động đọc/ghi tổng thể ra sao? | `V$SYSSTAT` | Tên statistic và giá trị tích lũy |
| Các tham số cấu hình có hiệu lực là gì? | `V$SYSTEM_PARAMETER` | `NAME`, `DISPLAY_VALUE` |

Những view này phản ánh **trạng thái hoặc thống kê mà Oracle hiện có tại thời điểm truy vấn**. Chúng không phải bản dump vật lý của toàn bộ database và không có nhiệm vụ ghi lại mọi sự kiện trong quá khứ.

## 2. Chuẩn bị phiên quan sát an toàn

Các truy vấn trong bài là **chỉ đọc**. Chúng phù hợp cho việc khảo sát một database thực hành hoặc môi trường được cho phép giám sát. Việc xem một số V$ view yêu cầu quyền chuyên biệt; một tài khoản chỉ có quyền đọc bảng nghiệp vụ có thể không truy vấn được các view hệ thống.

Kết nối bằng SQL*Plus, SQLcl, SQL Developer hoặc một công cụ SQL phù hợp. Trong SQL*Plus/SQLcl có thể thiết lập định dạng:

~~~sql
SET LINESIZE 220
SET PAGESIZE 100
COLUMN instance_name FORMAT A20
COLUMN host_name FORMAT A30
COLUMN name FORMAT A28
COLUMN open_mode FORMAT A18
COLUMN status FORMAT A14
~~~

Trước hết, xác nhận **đang ở đâu**. Hai câu sau không cần quyền truy vấn một V$ view:

~~~sql
SELECT USER AS session_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

`USER` trả về tên database user trong phiên. `CON_NAME` cho biết đang ở `CDB$ROOT` hay một PDB nếu hệ thống sử dụng multitenant. `SERVICE_NAME` giúp nhận diện dịch vụ kết nối. Các kết quả này rất quan trọng vì một số dynamic performance view **có phạm vi kết quả khác nhau giữa root và PDB**.

### 2.1 Nếu truy vấn view bị từ chối

Ví dụ:

~~~text
ORA-00942: table or view does not exist
ORA-01031: insufficient privileges
~~~

Các lỗi này có thể là **thiếu quyền xem metadata**, không chứng minh view không tồn tại hoặc database gặp lỗi. Trong Oracle, tên công khai `V$INSTANCE` thường là synonym tới đối tượng nền như `V_$INSTANCE`; việc truy vấn được phụ thuộc quyền của tài khoản, vai trò và cách công cụ chạy SQL. Nên nhờ quản trị viên cấp **quyền xem cần thiết theo phạm vi công việc** hoặc cung cấp kết quả đã được phép chia sẻ. Không dùng `SYSDBA` làm tài khoản mặc định của ứng dụng và không tự cấp quyền rộng cho một tài khoản thực hành.

### 2.2 `V$` và `GV$` khác nhau thế nào?

- `V$...`: quan sát thành phần động trong ngữ cảnh instance kết nối; một số view thể hiện dữ liệu cấp database nhưng vẫn có phạm vi container.
- `GV$...`: biến thể *global* của nhiều view, thường có cột `INST_ID` để phân biệt instance trong cấu hình nhiều instance như RAC.

Ví dụ:

~~~sql
SELECT instance_name, host_name, status, startup_time
FROM v$instance;
~~~

Trong hệ thống RAC, nếu có quyền:

~~~sql
SELECT inst_id, instance_name, host_name, status, startup_time
FROM gv$instance
ORDER BY inst_id;
~~~

Một hàng từ `V$INSTANCE` không có nghĩa cả RAC chỉ có một instance. Ngược lại, trên hệ thống không chạy RAC, `GV$INSTANCE` thường chỉ cho thấy một instance. Không cần dùng `GV$` cho mọi ví dụ nếu mục tiêu chỉ là quan sát instance hiện tại.

## 3. Bắt đầu từ instance, database và container

Ba khái niệm thường bị gộp lại thành từ “Oracle”: **instance** (bộ nhớ và process), **database** (tập dữ liệu/tệp được quản lý) và **container/PDB** (phạm vi dữ liệu trong kiến trúc multitenant).

### 3.1 Instance có đang mở database?

~~~sql
SELECT instance_name,
       host_name,
       version,
       status,
       database_status,
       startup_time
FROM v$instance;
~~~

| Cột | Diễn giải |
|---|---|
| `INSTANCE_NAME` | Tên instance đang xử lý phiên |
| `HOST_NAME` | Máy chủ mà instance chạy |
| `VERSION` | Phiên bản engine instance báo cáo |
| `STATUS` | Các trạng thái như `STARTED`, `MOUNTED`, `OPEN` |
| `DATABASE_STATUS` | Thông tin trạng thái hoạt động như `ACTIVE` |
| `STARTUP_TIME` | Lần khởi động instance gần nhất được ghi nhận |

Một kết quả ví dụ:

~~~text
INSTANCE_NAME   HOST_NAME      STATUS   DATABASE_STATUS
-------------   -------------  -------  ---------------
orcl1           db-node-01     OPEN     ACTIVE
~~~

Kết luận hợp lý: instance tên `orcl1` trên host `db-node-01` đang ở trạng thái `OPEN`. **Chưa thể kết luận** mọi PDB đã mở, mọi service được listener đăng ký hoặc ứng dụng bên ngoài truy cập thành công.

### 3.2 Database đang ở vai trò và chế độ nào?

~~~sql
SELECT name,
       db_unique_name,
       cdb,
       open_mode,
       database_role,
       log_mode
FROM v$database;
~~~

| Cột | Cách đọc |
|---|---|
| `NAME` | Tên database |
| `DB_UNIQUE_NAME` | Tên định danh database, hữu ích khi phân biệt các database trong Data Guard |
| `CDB` | `YES` nếu là multitenant CDB; `NO` trong kiến trúc non-CDB cũ |
| `OPEN_MODE` | `READ WRITE`, `READ ONLY`, `MOUNTED`... |
| `DATABASE_ROLE` | Ví dụ `PRIMARY` hoặc `PHYSICAL STANDBY` |
| `LOG_MODE` | `ARCHIVELOG` hoặc `NOARCHIVELOG` |

Nếu `OPEN_MODE = READ WRITE` và `DATABASE_ROLE = PRIMARY`, đó là bằng chứng database hiện được mở cho thao tác ghi thông thường tại cấp database. Nó **không đủ** xác nhận một PDB cụ thể đã ở `READ WRITE`. Trong Data Guard, các database standby có trạng thái/vai trò khác theo mục đích thiết kế; đừng xem mọi kết quả `READ ONLY` là sự cố.

Khi database chỉ được khởi động ở giai đoạn `NOMOUNT`, các thông tin phụ thuộc control file/database có thể chưa truy vấn được. Trước tiên hãy quan sát `V$INSTANCE.STATUS` và đối chiếu giai đoạn khởi động.

### 3.3 Quan sát danh sách container và PDB

Chỉ khi `V$DATABASE.CDB = YES` và phiên có quyền quan sát phù hợp:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$containers
ORDER BY con_id;
~~~

Với kết nối đến `CDB$ROOT`, truy vấn có thể cho thấy `CDB$ROOT`, `PDB$SEED` và các PDB ứng dụng. Một cách riêng để xem PDB:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;
~~~

Ví dụ **minh họa**:

~~~text
CON_ID  NAME       OPEN_MODE   RESTRICTED
------  ---------  ----------  ----------
2       PDB$SEED   READ ONLY   NO
3       APPPDB     READ WRITE  NO
4       REPORTPDB  MOUNTED     NO
~~~

`PDB$SEED` là PDB mẫu, thường ở `READ ONLY`. `APPPDB` được mở cho đọc/ghi. `REPORTPDB` mới ở `MOUNTED` nên chưa thể dùng như một PDB ứng dụng đã mở. Trong một phiên kết nối trực tiếp vào PDB, phạm vi nhìn thấy từ một số view có thể chỉ là container đó; khi muốn hiểu toàn bộ CDB, cần quan sát từ root với quyền tương ứng.

### 3.4 Đọc cột `CON_ID` theo đúng ngữ cảnh

Nhiều V$ view có cột `CON_ID`:

- `CON_ID = 0` thường biểu thị dữ liệu áp dụng cho toàn CDB hoặc dữ liệu không phân tách theo container (cũng gặp trong non-CDB).
- `CON_ID = 1` thường biểu thị `CDB$ROOT`.
- Các giá trị khác gắn với container cụ thể; tra tên từ `V$CONTAINERS` thay vì đoán tên PDB theo số.

Không tự cộng các hàng có `CON_ID = 0` với những hàng theo từng PDB rồi khẳng định đó là tổng toàn hệ thống: chúng có thể phản ánh **phạm vi khác nhau**, gây đếm trùng.

## 4. Quan sát bộ nhớ SGA và PGA

**SGA (System Global Area)** là vùng bộ nhớ dùng chung ở cấp instance, bao gồm các thành phần như shared pool, database buffer cache và redo log buffer. **PGA (Program Global Area)** là bộ nhớ riêng phục vụ các process Oracle (ví dụ vùng sort, hash, trạng thái thực thi), không phải một pool dùng chung theo cách SGA hoạt động.

### 4.1 Nhận diện thành phần SGA

~~~sql
SELECT name,
       ROUND(bytes / 1024 / 1024, 1) AS size_mb,
       resizeable
FROM v$sgainfo
WHERE name IN (
    'Maximum SGA Size',
    'Buffer Cache Size',
    'Shared Pool Size',
    'Redo Buffers',
    'Large Pool Size',
    'Java Pool Size'
)
ORDER BY name;
~~~

Một số hạng mục thường thấy:

| Hạng mục | Gợi ý đọc kiến trúc |
|---|---|
| `Buffer Cache Size` | Không gian instance dùng để cache nhiều data block |
| `Shared Pool Size` | Không gian dùng chung có các cấu trúc SQL/PLSQL và metadata |
| `Redo Buffers` | Bộ đệm redo trước khi LGWR ghi online redo log |
| `Large Pool Size` | Vùng nhớ phục vụ những hoạt động có sử dụng large pool theo cấu hình |
| `Java Pool Size` | Vùng nhớ cho thành phần Java trong database nếu được dùng |
| `Maximum SGA Size` | Chỉ báo kích thước tối đa theo cấu hình/giới hạn SGA của instance |

**Không cộng tùy tiện các hàng trong `V$SGAINFO`** để ra tổng SGA: một số hàng là thông tin tổng hợp, giới hạn hoặc phạm vi chồng nhau. Các vùng nhớ có thể tự điều chỉnh kích thước trong cơ chế quản lý bộ nhớ động.

Để xem mức phân bổ chi tiết hơn trong các pool:

~~~sql
SELECT NVL(pool, '(khac)') AS pool_name,
       ROUND(SUM(bytes) / 1024 / 1024, 1) AS allocated_mb
FROM v$sgastat
GROUP BY pool
ORDER BY pool_name;
~~~

`V$SGASTAT` mô tả thống kê phân bổ theo thành phần/pool trong SGA. Nó không đồng nghĩa với “mọi byte đang được một SQL statement sử dụng”, và cũng không phải bản đo trực tiếp dung lượng còn trống của ổ đĩa.

### 4.2 Nhìn PGA ở mức instance

~~~sql
SELECT name,
       value,
       unit
FROM v$pgastat
WHERE name IN (
    'total PGA allocated',
    'total PGA inuse',
    'aggregate PGA target parameter',
    'over allocation count'
)
ORDER BY name;
~~~

`VALUE` cần được giải thích cùng `UNIT`. Chẳng hạn một vài hàng là **bytes**, còn `over allocation count` là **số lần**, không được đem mọi giá trị chia cho `1024 × 1024` rồi coi là MB.

- `total PGA allocated` phản ánh lượng PGA đã cấp phát theo thống kê instance.
- `total PGA inuse` gần hơn với lượng PGA đang sử dụng.
- `aggregate PGA target parameter` phản ánh mục tiêu quản lý PGA, **không phải** bảo đảm tuyệt đối rằng PGA không thể vượt giá trị này.
- `over allocation count` hỗ trợ nhận diện việc Oracle từng phải cấp PGA vượt mục tiêu trong những tình huống nhất định; cần xem mốc thời gian/thống kê liên quan.

Một phiên hoạt động chậm không thể được kết luận là “thiếu PGA” chỉ từ một con số trong `V$PGASTAT`. Cần liên hệ với truy vấn, workarea, thời gian và workload thực tế.

### 4.3 Đối chiếu cấu hình bộ nhớ với quan sát runtime

~~~sql
SELECT name, display_value
FROM v$system_parameter
WHERE name IN (
    'memory_target',
    'sga_target',
    'sga_max_size',
    'pga_aggregate_target',
    'db_block_size'
)
ORDER BY name;
~~~

`V$SYSTEM_PARAMETER` giúp xem giá trị tham số hệ thống đang có hiệu lực theo phạm vi được phép quan sát. Tham số **cấu hình** như `SGA_TARGET` là đầu vào/quy tắc điều khiển bộ nhớ; thống kê **runtime** ở `V$SGAINFO`, `V$SGASTAT`, `V$PGASTAT` là những góc nhìn khác. Đừng thay một nhóm cho nhóm kia. Khi multitenant, hiệu lực của một số tham số còn phụ thuộc container.

## 5. Quan sát session, server process và background process

Khi ứng dụng mở một kết nối vào Oracle, nó tạo một **session logic**. Server process thực hiện công việc SQL theo mô hình kết nối đang dùng. Trong cấu hình **dedicated server**, mỗi session người dùng thường gắn với một server process chuyên trách; trong **shared server**, quan hệ giữa session và process phức tạp hơn, nên không nên đồng nhất số session với số process.

### 5.1 Quan sát session người dùng

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       service_name,
       machine,
       program,
       con_id
FROM v$session
WHERE type = 'USER'
ORDER BY sid
FETCH FIRST 30 ROWS ONLY;
~~~

| Cột | Dùng để hiểu điều gì? |
|---|---|
| `SID`, `SERIAL#` | Định danh phiên trong instance ở thời điểm quan sát; SID có thể được tái sử dụng |
| `USERNAME` | Database user; có thể trống với một số phiên |
| `STATUS` | `ACTIVE` hoặc `INACTIVE` theo trạng thái session |
| `SERVICE_NAME` | Service mà phiên sử dụng |
| `MACHINE`, `PROGRAM` | Thông tin client gửi/được Oracle ghi nhận; hỗ trợ định vị ứng dụng |
| `CON_ID` | Container gắn với phiên trong môi trường multitenant |

`ACTIVE` không có nghĩa session đang tiêu thụ CPU liên tục; nó có thể đang chờ I/O, khóa, mạng hoặc tài nguyên khác. `INACTIVE` không đồng nghĩa kết nối bị lỗi: nhiều ứng dụng giữ connection trong pool và chỉ dùng khi có request. `MACHINE`/`PROGRAM` là metadata hữu ích nhưng không phải bằng chứng xác thực danh tính không thể giả mạo.

### 5.2 Ghép session với process

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status AS session_status,
       s.machine,
       s.program AS client_program,
       p.spid AS os_process_id,
       p.program AS oracle_process_program
FROM v$session s
LEFT JOIN v$process p
       ON p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY s.sid
FETCH FIRST 30 ROWS ONLY;
~~~

`V$SESSION.PADDR` trỏ tới địa chỉ cấu trúc process; `V$PROCESS.ADDR` giúp nối hai view và `SPID` thường cho biết PID ở hệ điều hành. Điều này giúp trả lời: **một session đang được phục vụ bởi process Oracle nào?**

Những giới hạn cần nhớ:

- Trong RAC, `SID` chỉ có ý nghĩa trong instance tương ứng; dùng thêm `INST_ID` khi truy vấn qua `GV$...`.
- Trong shared server/dispatcher hoặc các kiến trúc có pooling, một session không có quan hệ dedicated một-một cố định với một process trong mọi thời điểm.
- `SPID` có thể khác cách nhận diện process thực tế trong một số môi trường hoặc hệ điều hành; cần đối chiếu khi điều tra.
- `FETCH FIRST 30 ROWS ONLY` chỉ lấy mẫu 30 hàng theo `SID`, không phải tổng số connection.

Nếu muốn đếm session theo trạng thái:

~~~sql
SELECT type, status, COUNT(*) AS session_count
FROM v$session
GROUP BY type, status
ORDER BY type, status;
~~~

Số này là **tại thời điểm SELECT**. Không dùng một snapshot để kết luận năng lực tối đa, đỉnh kết nối hay xu hướng tải của cả ngày.

### 5.3 Tìm tên background process có trong kiến trúc

~~~sql
SELECT name, description
FROM v$bgprocess
WHERE name IS NOT NULL
ORDER BY name
FETCH FIRST 40 ROWS ONLY;
~~~

Các nhóm tên có thể bắt gặp:

| Process | Vai trò khái quát |
|---|---|
| `DBWn` | Ghi các dirty database block từ buffer cache về datafile theo cơ chế Oracle |
| `LGWR` | Ghi redo từ redo log buffer vào online redo log |
| `CKPT` | Phối hợp thông tin checkpoint và cập nhật metadata/checkpoint cần thiết |
| `SMON` | Hỗ trợ những nhiệm vụ phục hồi và bảo trì hệ thống |
| `PMON` | Hỗ trợ giám sát và dọn dẹp tài nguyên process/session khi cần |
| `ARCn` | Archiver trong cấu hình và trạng thái có lưu archive redo log |

Tên process, số lượng và phân công chi tiết phụ thuộc phiên bản, cấu hình và tính năng Oracle. `V$BGPROCESS` cung cấp mô tả các background process mà Oracle biết; **chỉ có tên trong view không phải bằng chứng process đó đang hoạt động hoặc đang gây tải**. Khi cần chứng minh một tiến trình đang chạy, phải đối chiếu với `V$PROCESS` và công cụ hệ điều hành trong phạm vi được phép.

## 6. Đọc lớp lưu trữ: tablespace, datafile, tempfile, redo, control file

Ở tầng logic, Oracle lưu segment của bảng/chỉ mục trong tablespace; tablespace được ánh xạ đến datafile. Instance thao tác qua buffer cache và các cơ chế I/O, không đơn giản “mỗi hàng SQL bằng một file”.

### 6.1 Datafile thuộc tablespace nào?

~~~sql
SELECT d.con_id,
       t.name AS tablespace_name,
       d.file#,
       d.name AS datafile_name,
       d.status
FROM v$datafile d
JOIN v$tablespace t
  ON t.ts# = d.ts#
 AND t.con_id = d.con_id
ORDER BY d.con_id, t.name, d.file#;
~~~

Truy vấn cho thấy quan hệ **datafile → tablespace**, và thêm `CON_ID` khi database là CDB. Đọc các cột:

- `TABLESPACE_NAME`: tên không gian lưu trữ logic.
- `FILE#`: số định danh datafile trong database.
- `DATAFILE_NAME`: tên/đường dẫn tệp hoặc định danh lưu trữ Oracle ASM.
- `STATUS`: trạng thái datafile ở góc nhìn view tương ứng.
- `CON_ID`: phạm vi container của datafile trong CDB.

Tệp thuộc ASM thường có tên như `+DATA/...`, không nhất thiết là một tệp thông thường có thể mở trực tiếp bằng file manager. Dữ liệu bảng còn nằm trong **segment/extent/block**; truy vấn này **chưa cho biết hàng cụ thể nằm ở block nào** hoặc một SQL sẽ thực sự đọc những block nào.

Trong các phiên bản/cấu hình và phạm vi container khác nhau, dữ liệu hiển thị từ `V$TABLESPACE`, `V$DATAFILE` có thể thay đổi. Nếu kết quả ghép không như mong đợi, xác nhận quyền, container và cột `CON_ID`; tránh bỏ điều kiện container trong một CDB có nhiều PDB.

### 6.2 Tempfile và vùng tạm

~~~sql
SELECT con_id, file#, name, status
FROM v$tempfile
ORDER BY con_id, file#;
~~~

Tempfile thuộc vùng lưu trữ tạm, thường phục vụ một số thao tác như sort/hash cần tràn khỏi bộ nhớ và các mục đích TEMP khác. Một tempfile có mặt không có nghĩa hiện tại đang có truy vấn thực sự spill ra đĩa; đó là bằng chứng về **cấu trúc lưu trữ được cấu hình**, không phải một trace thao tác.

### 6.3 Control file: metadata của database

~~~sql
SELECT name, status
FROM v$controlfile;
~~~

**Control file** chứa metadata quan trọng để Oracle nhận diện và quản lý database (ví dụ cấu trúc tệp, thông tin checkpoint). `V$CONTROLFILE` giúp biết những control file Oracle đang ghi nhận; đường dẫn trong kết quả có thể chứa thông tin hạ tầng cần bảo vệ khi chia sẻ log/screenshot.

### 6.4 Online redo log và redo log member

~~~sql
SELECT group#,
       thread#,
       ROUND(bytes / 1024 / 1024, 1) AS size_mb,
       members,
       status,
       archived
FROM v$log
ORDER BY thread#, group#;
~~~

~~~sql
SELECT group#, type, member, status
FROM v$logfile
ORDER BY group#, member;
~~~

`V$LOG` mô tả **redo log group** và trạng thái của group. `V$LOGFILE` cho thấy từng **member** vật lý thuộc group. Một group có thể có nhiều member nếu cấu hình multiplexing. Những trạng thái thường gặp như `CURRENT`, `ACTIVE`, `INACTIVE` mô tả vòng đời của group, không được hiểu đơn giản thành “file nào đã hỏng”.

Gắn với kiến trúc:

~~~mermaid
flowchart LR
    A["DML thay đổi data block"] --> B["Redo log buffer trong SGA"]
    B --> C["LGWR"]
    C --> D["Online redo log group"]
    D --> E["Member 1"]
    D --> F["Member 2 nếu cấu hình"]
    A --> G["Dirty buffer"]
    G --> H["DBWn"]
    H --> I["Datafile"]
~~~

**`COMMIT` thông thường cần bảo đảm redo liên quan được ghi bền vững**, trong khi DBWn có thể ghi dirty data block về datafile vào thời điểm khác. Vì vậy không thể suy ra từ `V$DATAFILE` rằng một giao dịch vừa commit đã ghi ngay mọi data block xuống tệp. Các view vừa nêu cho biết **cấu trúc** redo/datafile, không cung cấp danh sách tất cả thay đổi của từng transaction.

## 7. Nối kiến trúc với quá trình chạy SQL

Khi client gửi SQL, Oracle kiểm tra/parse, có thể dùng lại cursor trong shared pool, tối ưu kế hoạch truy cập dữ liệu, thực thi và trả kết quả. Có thể quan sát **SQL/cursor trong bộ nhớ** và **trạng thái session** bằng các view phù hợp, nhưng cần hiểu rõ phạm vi và tính thời điểm của số liệu.

### 7.1 SQL cursor được Oracle ghi nhận

~~~sql
SELECT sql_id,
       executions,
       buffer_gets,
       disk_reads,
       rows_processed
FROM v$sqlarea
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Ý nghĩa các cột:

| Cột | Nên hiểu thế nào? |
|---|---|
| `SQL_ID` | Định danh SQL để liên hệ với session, plan và thống kê |
| `EXECUTIONS` | Số lượt thực thi được thống kê cho cursor/SQL theo phạm vi view |
| `BUFFER_GETS` | Tổng số lần lấy block logic được ghi nhận, không bằng số lần đọc đĩa |
| `DISK_READS` | Số lần đọc đĩa được thống kê cho SQL; không có nghĩa mỗi lần là đọc đĩa quay vật lý ở phần cứng |
| `ROWS_PROCESSED` | Số hàng đã xử lý theo thống kê của SQL, không đồng nhất với số hàng API trả về |

`V$SQLAREA` tổng hợp thống kê liên quan các SQL cursor mà Oracle hiện ghi nhận; các SQL có thể bị đẩy khỏi shared pool, parse lại hoặc có nhiều child cursor. **Không** coi `EXECUTIONS` là số lần SQL đã chạy từ ngày database được tạo; cũng không coi `BUFFER_GETS` cao là đủ để kết luận SQL có lỗi.

Nếu muốn kiểm tra một `SQL_ID` cụ thể sau khi tìm thấy, lọc theo biến bind (SQL*Plus/SQLcl):

~~~sql
VARIABLE target_sql_id VARCHAR2(13)
EXEC :target_sql_id := 'thay_bang_sql_id'

SELECT sql_id, executions, buffer_gets, disk_reads, rows_processed
FROM v$sqlarea
WHERE sql_id = :target_sql_id;
~~~

Lệnh `VARIABLE` và `EXEC` là lệnh của công cụ SQL*Plus/SQLcl; trong ứng dụng Java, sử dụng bind variable của JDBC thay vì sao chép nguyên văn hai lệnh trên. Một `SQL_ID` không còn ở shared pool có thể không xuất hiện trong `V$SQLAREA` dù SQL từng chạy.

### 7.2 Session đang làm gì hoặc chờ gì?

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       wait_class,
       state
FROM v$session
WHERE type = 'USER'
ORDER BY sid
FETCH FIRST 30 ROWS ONLY;
~~~

`SQL_ID` có thể cho biết SQL đang được gắn với session tại thời điểm quan sát. `EVENT` và `WAIT_CLASS` giúp nhận biết điểm chờ được Oracle ghi nhận, ví dụ chờ I/O hoặc chờ khóa. Tuy nhiên:

- Một snapshot rất ngắn có thể bỏ lỡ SQL chạy nhanh.
- Session `ACTIVE` vẫn có thể đang chờ; `STATUS` không phải biểu đồ CPU.
- `EVENT` và `STATE` phải được đọc cùng ngữ cảnh; sự kiện chờ được ghi nhận không chứng minh đó là nút thắt hiệu năng chính của cả request.
- Với ứng dụng dùng connection pool, request HTTP có thể chạy qua nhiều thao tác SQL; một session trong một thời điểm chỉ là một mảnh bằng chứng.

Muốn phân tích SQL chậm một cách đáng tin, cần kết hợp thời gian, execution plan, giá trị bind, thống kê runtime và các phép đo có cùng khoảng quan sát. Dynamic performance view giúp **đặt câu hỏi** và chọn đối tượng cần điều tra sâu hơn, nhưng không tự tạo ra trace nhân quả hoàn chỉnh.

### 7.3 Các bộ đếm đọc/ghi ở mức instance

~~~sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size'
)
ORDER BY name;
~~~

`V$SYSSTAT` có các bộ đếm thống kê **theo phạm vi instance/container của view**, nhiều bộ đếm tích lũy từ lúc instance khởi động. Để phân tích mức độ thay đổi của tải, nên lấy **hai thời điểm** trong cùng phạm vi quan sát rồi so sánh chênh lệch; vẫn cần giải thích ý nghĩa chính xác từng statistic.

Ví dụ:

~~~text
T1: physical reads = 1 000 000
T2: physical reads = 1 012 000
Chênh lệch = 12 000 (đơn vị theo statistic của Oracle)
~~~

Không thể suy ra “12 000 lần đụng ổ đĩa của request X” nếu số liệu được thu thập ở cấp instance đang phục vụ nhiều session. Những bộ đếm này cũng không trực tiếp cho biết latency hoặc số byte đã truyền qua mạng cho một API.

## 8. Truy vấn bản đồ kiến trúc theo từng chặng

Sau khi hiểu từng view, có thể gom các bước thành một chuỗi khảo sát. Mỗi truy vấn là một phép **quan sát có phạm vi**, không phải lệnh thay đổi cấu hình.

**Chặng 1 — Nhận diện nơi đang đứng**

~~~sql
SELECT USER, SYS_CONTEXT('USERENV','CON_NAME') AS con_name
FROM dual;

SELECT instance_name, host_name, status
FROM v$instance;

SELECT name, cdb, open_mode, database_role
FROM v$database;
~~~

**Chặng 2 — Nhận diện các container khi là CDB**

~~~sql
-- Chỉ áp dụng khi CDB = YES và phiên có quyền phù hợp:
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;
~~~

**Chặng 3 — Đọc bộ nhớ và process**

~~~sql
SELECT name, ROUND(bytes / 1024 / 1024, 1) AS size_mb
FROM v$sgainfo
WHERE name IN ('Shared Pool Size', 'Buffer Cache Size', 'Redo Buffers');

SELECT name, value, unit
FROM v$pgastat
WHERE name IN ('total PGA allocated', 'total PGA inuse');

SELECT type, status, COUNT(*) AS sessions
FROM v$session
GROUP BY type, status;
~~~

**Chặng 4 — Đọc vị trí các tệp chính**

~~~sql
SELECT file#, name, status
FROM v$datafile
ORDER BY file#;

SELECT group#, thread#, status, archived
FROM v$log
ORDER BY thread#, group#;

SELECT group#, member
FROM v$logfile
ORDER BY group#, member;
~~~

**Chặng 5 — Gắn SQL workload với các bộ đếm**

~~~sql
SELECT sql_id, executions, buffer_gets, disk_reads
FROM v$sqlarea
WHERE executions > 0
ORDER BY buffer_gets DESC
FETCH FIRST 5 ROWS ONLY;
~~~

Khi ghi nhận kết quả trong báo cáo, luôn kèm **thời điểm**, **instance**, **container**, **vai trò database** và **quyền/phạm vi truy vấn**. Hai bản chụp từ hai PDB hoặc hai instance khác nhau không thể so sánh trực tiếp như thể chúng là cùng một đối tượng.

## 9. Diễn giải tình huống thực tế

### Tình huống A: Instance `OPEN` nhưng ứng dụng không vào được PDB

Quan sát:

~~~text
V$INSTANCE.STATUS      = OPEN
V$DATABASE.CDB         = YES
V$DATABASE.OPEN_MODE   = READ WRITE
V$PDBS: APPPDB         = MOUNTED
~~~

Instance và CDB đang mở, nhưng `APPPDB` chưa mở để phục vụ hoạt động thông thường. Nếu ứng dụng kết nối đến service của PDB này, cần kiểm tra tiếp trạng thái PDB và đăng ký service. Các dynamic performance view trên **không thay thế** việc kiểm tra listener từ hệ điều hành bằng `lsnrctl status` / `lsnrctl services` hoặc thử kết nối thực tế từ máy client.

### Tình huống B: Session tăng nhưng process không tăng tương ứng

`V$SESSION` cho thấy nhiều session, còn số process quan sát từ `V$PROCESS` không tăng một-một. Đây có thể phù hợp với shared server, cấu hình multiplexing hoặc cách Oracle quản lý các session/process. Không nên vội kết luận view sai hay process bị rò rỉ. Trước tiên cần kiểm tra mô hình kết nối và phạm vi instance/container của số liệu.

### Tình huống C: `V$SGAINFO` có Buffer Cache Size lớn nhưng SQL vẫn có physical read

Buffer cache giúp giảm đọc datafile ở những trường hợp phù hợp; nó không phải lời bảo đảm mọi block cần đọc luôn hiện diện trong cache. Kích thước cache, working set, chiến lược I/O, truy vấn và tình trạng dữ liệu đều ảnh hưởng kết quả. Cần quan sát `V$SQLAREA` hoặc thống kê liên quan trong cùng khoảng thời gian trước khi kết luận.

### Tình huống D: Redo log group `CURRENT` nhưng datafile không đổi ngay

`V$LOG` mô tả redo log group; nó không hiển thị thời điểm mọi dirty data block đã được DBWn ghi xuống datafile. Oracle sử dụng cơ chế write-ahead logging và phục hồi để tách mốc ghi redo với mốc ghi block. Quan sát file metadata không phải phép đo trực tiếp tiến trình commit của một giao dịch cụ thể.

### Tình huống E: Hai người cùng truy vấn `V$SESSION` ra số lượng khác nhau

Hãy kiểm tra họ kết nối **cùng instance không**, ở **cùng container không**, có dùng cùng điều kiện lọc không và quan sát **cùng thời điểm không**. Session đến và đi liên tục; connection pool có thể tạo thêm hoặc trả lại các phiên. Chênh lệch số đếm đơn lẻ chưa đủ chứng minh database hoạt động sai.

## 10. Các ranh giới suy luận cần nhớ

| Kết quả đã nhìn thấy | Không nên kết luận ngay |
|---|---|
| `V$INSTANCE.STATUS = OPEN` | Toàn bộ PDB và service đều truy cập được từ client |
| `V$DATABASE.OPEN_MODE = READ WRITE` | Mọi user có quyền `INSERT` hoặc mọi PDB đều `READ WRITE` |
| SGA lớn trong `V$SGAINFO` | Tất cả truy vấn sẽ tránh physical I/O |
| Nhiều hàng `ACTIVE` trong `V$SESSION` | Tất cả session đang dùng CPU và hệ thống đang quá tải |
| Một hàng process ở `V$PROCESS` | Luôn có đúng một session dành riêng cho process đó |
| Có datafile trong `V$DATAFILE` | Biết chính xác hàng/SQL nào đang nằm ở block nào |
| `CURRENT` trong `V$LOG` | Mọi datafile đã được đồng bộ sau lần commit gần nhất |
| SQL có `DISK_READS` cao | Chắc chắn SQL là nguyên nhân duy nhất gây chậm HTTP request |
| Số `V$SYSSTAT.VALUE` cao | Biết tải của 1 request mà không đo mốc thời gian và phạm vi |
| `V$SERVICES` biết một service | Listener từ mọi mạng đều truy cập được service đó |

Dynamic performance view là phép quan sát, không phải bộ công cụ kết luận tự động. Một số thống kê có thể được thu thập theo vòng đời cursor hoặc instance, bị reset khi instance khởi động lại, thay đổi khi cache bị thay thế hoặc thay đổi phạm vi theo CDB/PDB. Lấy hai thời điểm, xác định phạm vi và đối chiếu bằng chứng của lớp liên quan là cách diễn giải đáng tin hơn.

## 11. Bài thực hành: tự vẽ lại một Oracle đang chạy

Trong một môi trường được phép quan sát, ghi lại các dữ liệu sau:

1. Tên instance/host và `STATUS` từ `V$INSTANCE`. Nếu có RAC, ghi `INST_ID` từ `GV$INSTANCE`.
2. Tên database, `DATABASE_ROLE`, `OPEN_MODE` và `CDB` từ `V$DATABASE`.
3. Container hiện tại từ `SYS_CONTEXT`. Nếu là CDB, ghi danh sách PDB và `OPEN_MODE` từ `V$PDBS` hoặc `V$CONTAINERS`.
4. Kích thước buffer cache, shared pool, redo buffers từ `V$SGAINFO`; PGA allocated/inuse từ `V$PGASTAT`.
5. Số session người dùng, số session background, vài ví dụ `SID` và tên process liên quan từ `V$SESSION` và `V$PROCESS`.
6. Một tablespace cùng datafile của nó, một redo log group cùng các member, và đường dẫn control file từ `V$DATAFILE`, `V$TABLESPACE`, `V$LOG`, `V$LOGFILE`, `V$CONTROLFILE`.
7. Một `SQL_ID` có mặt trong `V$SQLAREA`; nêu `EXECUTIONS`, `BUFFER_GETS`, `DISK_READS` và vì sao không thể xem một hàng là số liệu của riêng một HTTP request.

Từ những ghi nhận đó, tự phác thảo:

~~~text
Database: <name>  |  Role: <role>  |  CDB: <YES/NO>
  Instance: <instance_name>@<host>  |  Status: <status>
    SGA: shared pool / buffer cache / redo buffers
    PGA: allocated / inuse
    Server processes <-> User sessions <-> SQL cursors
    Background processes: LGWR, DBWn, ...
  Container:
    Root (nếu là CDB)
    PDB A: <open_mode>
    PDB B: <open_mode>
  Storage:
    Tablespace -> datafile
    Online redo group -> member(s)
    Control file(s)
~~~

Cuối cùng, trả lời bằng **bằng chứng view**:

- Vì sao nói SGA thuộc instance, nhưng datafile thuộc lớp lưu trữ database?
- Khi `V$SESSION` cho thấy kết nối tới PDB, dựa vào thông tin nào để xác nhận container?
- Vì sao phải phân biệt `V$SQLAREA`, `V$SYSSTAT` và `V$SESSION` khi phân tích workload?
- Có thể dùng V$ view để chứng minh listener từ một máy khách bất kỳ truy cập được không? Nếu không, cần kiểm tra lớp nào nữa?
- Nếu PDB ở `MOUNTED` nhưng CDB đã `OPEN`, sơ đồ nên thể hiện ra sao?

## 12. Tổng hợp: từ tên view sang khả năng đọc kiến trúc

Đọc kiến trúc Oracle bằng dynamic performance view là phép nối giữa **khái niệm hệ thống** và **dữ kiện có thể quan sát**:

~~~text
V$INSTANCE / GV$INSTANCE  -> instance, host, trạng thái, RAC
V$DATABASE               -> database, role, open mode, CDB
V$CONTAINERS / V$PDBS     -> container và trạng thái PDB
V$SGAINFO / V$SGASTAT     -> bộ nhớ dùng chung SGA
V$PGASTAT                -> bộ nhớ PGA
V$SESSION / V$PROCESS     -> kết nối logic và process thực thi
V$BGPROCESS              -> các nhóm background process
V$TABLESPACE / V$DATAFILE -> tổ chức dữ liệu trên datafile
V$LOG / V$LOGFILE        -> nhóm và member online redo log
V$CONTROLFILE            -> control file của database
V$SQLAREA / V$SYSSTAT    -> SQL và các thống kê workload
V$SYSTEM_PARAMETER       -> cấu hình hệ thống đang có hiệu lực
~~~

Kết quả tốt của bài thực hành là một **sơ đồ kiến trúc gắn với dữ liệu thực tế**, có tên instance, database, PDB, đường đi process/session, vùng nhớ và tệp lưu trữ. Khi chuyển sang phân tích sự cố hoặc hiệu năng, luôn giữ nguyên nguyên tắc: **chọn đúng view cho đúng lớp, kiểm tra phạm vi instance/container và thời điểm, rồi chỉ rút ra kết luận mà bằng chứng thực sự hỗ trợ**.
