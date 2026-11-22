# Kiểm tra phiên bản, trạng thái database, PDB và listener

Trước khi thực hành SQL trên Oracle, cần biết mình đang kết nối đến **Oracle Database phiên bản nào**, database đã mở hay chưa, **PDB** chứa dữ liệu ứng dụng có sẵn sàng không, và **listener** có đang nhận kết nối từ bên ngoài hay không. Bốn câu hỏi này liên quan nhau nhưng được kiểm tra ở những lớp khác nhau.

Bài thực hành này dùng SQL*Plus hoặc SQLcl cho lệnh SQL và chương trình `lsnrctl` cho listener. Bạn có thể thực hiện trên máy cài Oracle trực tiếp, máy ảo, hoặc trong môi trường container nếu có shell và quyền phù hợp. Các ví dụ tên database/PDB như `FREE`, `FREEPDB1`, `XE`, `XEPDB1` chỉ là tên thường gặp ở một số bản Oracle; **hãy lấy tên thực tế từ môi trường của bạn**.

## 1. Phân biệt những gì sắp kiểm tra

~~~mermaid
flowchart TD
    U["Ứng dụng / SQL client"] -->|"host:port/service_name"| L["Listener (Oracle Net)"]
    L -->|"Chuyển yêu cầu kết nối"| S["Dịch vụ và server process"]
    S --> I["Oracle instance: SGA + background processes"]
    I --> C["CDB: container database"]
    C --> R["CDB$ROOT"]
    C --> P["PDB ứng dụng"]
    C --> Seed["PDB$SEED: template"]
    C --> F["Datafile, control file, redo log"]
~~~

| Thành phần | Câu hỏi cần trả lời | Cách quan sát chính |
|---|---|---|
| SQL client | Công cụ kết nối cài trên máy chạy lệnh phiên bản nào? | `sqlplus -v` hoặc lệnh phiên bản của công cụ |
| Oracle Database engine | Database server đang chạy phiên bản nào? | `V$VERSION`, `V$INSTANCE` |
| Instance | Các tiến trình và bộ nhớ Oracle ở trạng thái nào? | `V$INSTANCE.STATUS` |
| Database | Database đã `OPEN` và cho đọc/ghi không? | `V$DATABASE.OPEN_MODE` |
| CDB/PDB | Đang ở container nào, PDB ứng dụng có `READ WRITE` không? | `SHOW CON_NAME`, `SHOW PDBS`, `V$PDBS` |
| Listener | Listener chạy ở địa chỉ/cổng nào và biết service nào? | `lsnrctl status`, `lsnrctl services` |
| Kết nối thực tế | Tài khoản ứng dụng có đăng nhập đúng PDB được không? | Kết nối qua `host:port/service_name` rồi chạy `SELECT` |

**Oracle instance** là tập tiến trình và bộ nhớ đang chạy. **Oracle database** là tổ chức dữ liệu được instance quản lý. **Listener** là thành phần nhận yêu cầu kết nối Oracle Net. **Service name** định tuyến phiên kết nối đến database/container phù hợp; service không phải tên listener. Từ Oracle 12c, mô hình multitenant có **CDB** (Container Database) chứa `CDB$ROOT`, `PDB$SEED` và các **PDB** (Pluggable Database). Một số triển khai hoặc phiên bản cũ có thể là non-CDB; khi đó thao tác kiểm tra PDB không áp dụng.

## 2. Chuẩn bị một phiên SQL và một terminal

Bạn cần hai nơi chạy lệnh:

1. **SQL*Plus hoặc SQLcl**: chạy câu SQL, các lệnh hiển thị `SHOW ...` và truy vấn dynamic performance view.
2. **Terminal của hệ điều hành**: chạy `sqlplus -v`, `lsnrctl status` và `lsnrctl services`. Các lệnh này **không** được nhập sau dấu nhắc `SQL>`.

Nếu ở máy chủ Oracle và tài khoản hệ điều hành được cấp quyền quản trị OSDBA, ví dụ trên Linux/Unix:

~~~sh
sqlplus / as sysdba
~~~

Kết nối này dùng cơ chế xác thực hệ điều hành tại máy có Oracle; không mặc định hoạt động từ mọi máy trạm, mọi container hoặc mọi tài khoản. Trên Windows, người dùng cũng cần đúng cấu hình xác thực/quyền. Không sử dụng `SYSDBA` làm tài khoản kết nối thường xuyên của ứng dụng.

Nếu muốn thử đường kết nối giống ứng dụng, dùng tài khoản có quyền đăng nhập vào **service của PDB**, ví dụ:

~~~sh
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

SQL*Plus sẽ yêu cầu mật khẩu nếu chưa cung cấp. `-L` giúp thoát thay vì tiếp tục hỏi đăng nhập nhiều lần khi kết nối thất bại. Thay `db-host.example`, cổng `1521` và `my_pdb_service` bằng giá trị thật; port 1521 là quy ước phổ biến chứ không bắt buộc. Tránh ghi mật khẩu trực tiếp vào lệnh vì có thể để lộ qua lịch sử shell hoặc danh sách tiến trình.

Sau khi kết nối, có thể điều chỉnh cách hiển thị cho dễ đọc:

~~~sql
SET LINESIZE 200
SET PAGESIZE 100
COLUMN instance_name FORMAT A18
COLUMN status FORMAT A12
COLUMN database_status FORMAT A18
COLUMN name FORMAT A24
COLUMN open_mode FORMAT A20
~~~

Lưu ý: các câu truy vấn `V$...` bên dưới thường cần quyền xem thông tin hệ thống. Nếu tài khoản ứng dụng nhận `ORA-00942` hoặc `ORA-01031` thì trước hết kiểm tra quyền; không kết luận database bị hỏng hoặc PDB bị đóng. Quản trị viên có thể chạy các truy vấn phù hợp hoặc cấp quyền xem tối thiểu theo chính sách của môi trường.

## 3. Kiểm tra phiên bản: client, server và listener khác nhau

### 3.1 Phiên bản công cụ SQL*Plus trên máy chạy lệnh

Trong **terminal**:

~~~sh
sqlplus -v
~~~

Ví dụ đầu ra minh họa:

~~~text
SQL*Plus: Release 23.0.0.0.0 - Production
Version 23.x.x.x.x
~~~

Lệnh này xác nhận **phiên bản SQL*Plus client**, không phải phiên bản engine đang chạy ở database mà ứng dụng kết nối. Client và server có thể khác phiên bản trong phạm vi được Oracle hỗ trợ; muốn biết server phải đăng nhập và hỏi chính server.

### 3.2 Phiên bản Oracle Database engine

Trong **SQL*Plus/SQLcl đã kết nối đến Oracle**:

~~~sql
SELECT banner
FROM v$version;
~~~

Một hàng thường mô tả Oracle Database; các hàng khác có thể mô tả thành phần liên quan. Có thể xem thêm:

~~~sql
SELECT instance_name, version
FROM v$instance;
~~~

Trên một số phiên bản mới, `V$VERSION` còn có cột `BANNER_FULL` giúp xem chuỗi phiên bản/patch chi tiết. Nếu muốn viết bài thực hành tương thích rộng hơn, `BANNER` và `V$INSTANCE.VERSION` là hai điểm khởi đầu hữu ích. Phiên bản chính, mức release/update và patch đã cài không phải lúc nào cũng thể hiện đầy đủ trong một chuỗi duy nhất; khi điều tra patch cụ thể cần đối chiếu thông tin patch của môi trường.

**Điểm ghi nhận:** phiên bản Oracle ở **server**, không chỉ bản SQL client. Nếu ứng dụng báo không tương thích, ghi cả phiên bản driver JDBC, SQL client (nếu dùng) và Oracle server để phân tích.

### 3.3 Phiên bản listener

Trong terminal trên máy có công cụ Oracle Net:

~~~sh
lsnrctl version
~~~

Phiên bản listener giúp nhận diện bộ công cụ Oracle Net đang chạy trên host. Nó **không thay thế** truy vấn phiên bản database: một host có thể cài nhiều Oracle Home, nhiều listener hoặc nhiều database.

## 4. Kiểm tra instance và trạng thái database

### 4.1 Trạng thái của instance

Trong SQL*Plus khi có quyền truy cập:

~~~sql
SELECT instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM v$instance;
~~~

Ví dụ diễn giải hai cột quan trọng:

| Cột | Giá trị thường gặp | Ý nghĩa |
|---|---|---|
| `STATUS` | `STARTED` | Instance đã khởi động ở giai đoạn NOMOUNT; database chưa mount |
| `STATUS` | `MOUNTED` | Instance đã mount database, chưa mở để sử dụng bình thường |
| `STATUS` | `OPEN` | Instance đã mở database |
| `DATABASE_STATUS` | `ACTIVE` | Database đang hoạt động theo trạng thái mà instance báo cáo |

`STATUS = OPEN` và `DATABASE_STATUS = ACTIVE` là tín hiệu tốt, nhưng **chưa khẳng định PDB ứng dụng đã mở** hoặc client bên ngoài kết nối được. `STARTUP_TIME` hữu ích để nhận diện instance vừa khởi động lại; `HOST_NAME` giúp tránh nhầm với server khác.

Các giai đoạn cơ bản:

~~~mermaid
flowchart LR
    A["NOMOUNT: instance STARTED"] --> B["MOUNT: control file được mở"]
    B --> C["OPEN: database được mở"]
~~~

Các chuyển trạng thái trên là kiến thức để **đọc kết quả**, không phải yêu cầu chạy lệnh `STARTUP` hay `ALTER DATABASE` trong bài kiểm tra.

### 4.2 Trạng thái của database

~~~sql
SELECT name,
       db_unique_name,
       cdb,
       open_mode,
       database_role,
       log_mode
FROM v$database;
~~~

Những cột đáng chú ý:

- `NAME`: tên database, không nhất thiết bằng service name mà client dùng.
- `DB_UNIQUE_NAME`: định danh database trong các cấu hình cần phân biệt nhiều bản sao/cấu hình Data Guard.
- `CDB`: `YES` nếu là container database; `NO` nếu là non-CDB.
- `OPEN_MODE`: ví dụ `READ WRITE`, `READ ONLY` hoặc `MOUNTED`. Database chính chạy ứng dụng giao dịch thường cần `READ WRITE`, nhưng cơ sở dữ liệu báo cáo/standby có thể cố ý để chế độ khác.
- `DATABASE_ROLE`: chẳng hạn `PRIMARY` hoặc `PHYSICAL STANDBY`; giúp giải thích vì sao một database không ở chế độ ghi.
- `LOG_MODE`: `ARCHIVELOG` hoặc `NOARCHIVELOG`; là thông tin về chế độ lưu trữ redo phục vụ phục hồi, không phải thước đo PDB đã sẵn sàng.

Nếu instance mới ở **NOMOUNT**, truy vấn `V$DATABASE` có thể chưa dùng được vì database chưa mount. Khi đó dựa vào `V$INSTANCE.STATUS` và log/chuẩn vận hành của môi trường; không suy diễn từ lỗi truy vấn rằng dữ liệu đã mất.

### 4.3 Hai trạng thái phải được đọc cùng nhau

| Quan sát | Kết luận phù hợp |
|---|---|
| Instance `OPEN`, database `READ WRITE` | Phần CDB/database chính đã mở để đọc/ghi |
| Instance `MOUNTED`, database `MOUNTED` | Database đã mount nhưng chưa mở bình thường |
| Instance `STARTED` | Mới có instance, database chưa mount |
| Database `READ ONLY` | Đọc được theo cấu hình, không xem đây là nơi ghi nghiệp vụ khi chưa xác nhận kiến trúc |
| Instance `OPEN` nhưng ứng dụng vẫn không kết nối | Cần kiểm tra tiếp PDB, service, listener, địa chỉ mạng và quyền đăng nhập |

Đối với Oracle RAC, mỗi instance có trạng thái và host riêng; ví dụ truy vấn `GV$INSTANCE` khi có quyền có thể cho thấy nhiều instance. Bài thực hành cơ bản có thể bắt đầu bằng `V$INSTANCE` trên phiên đang kết nối.

## 5. Kiểm tra đang ở CDB hay PDB nào

Với Oracle multitenant, một **CDB đang OPEN** vẫn có thể chứa một **PDB đang MOUNTED**. Đây là nguyên nhân phổ biến khiến người mới thấy database “đã chạy” nhưng ứng dụng không vào được PDB cần dùng.

### 5.1 Xác định container của phiên SQL hiện tại

Trong SQL*Plus:

~~~sql
SHOW CON_NAME
~~~

Hoặc dùng câu SQL:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

Kết quả có thể là `CDB$ROOT` nếu đang ở root, hoặc tên PDB ứng dụng, chẳng hạn `FREEPDB1`. Mọi truy vấn về bảng ứng dụng phải được hiểu trong ngữ cảnh container/schema đang kết nối.

### 5.2 Kiểm tra CDB có bật multitenant không

~~~sql
SELECT name, cdb, open_mode
FROM v$database;
~~~

Nếu `CDB = YES`, tiếp tục kiểm tra PDB. Nếu `CDB = NO`, môi trường là non-CDB và không cần ép chạy `SHOW PDBS`. Đừng tự suy rằng mọi phiên bản Oracle hoặc mọi môi trường đều có cùng tên PDB.

### 5.3 Danh sách PDB và chế độ mở

Khi kết nối có đủ quyền vào `CDB$ROOT`:

~~~sql
SHOW PDBS
~~~

Tương đương để lấy cột cụ thể bằng SQL:

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
~~~

Ví dụ kết quả **minh họa**, không phải dữ liệu thật của máy:

~~~text
CON_ID  NAME       OPEN_MODE   RESTRICTED
------  ---------  ----------  ----------
2       PDB$SEED   READ ONLY   NO
3       FREEPDB1   READ WRITE  NO
~~~

`PDB$SEED` là PDB mẫu dùng để tạo PDB mới và thường ở `READ ONLY`; đây là trạng thái bình thường, không phải lỗi. PDB chứa schema ứng dụng thường cần `READ WRITE` để chạy bài DML. `MOUNTED` nghĩa là PDB chưa mở; `READ ONLY` không cho thao tác ghi thông thường; `RESTRICTED = YES` cho biết khả năng kết nối đang bị hạn chế. Việc cho phép kết nối còn phụ thuộc service, quyền người dùng và cấu hình.

Bạn cũng có thể dùng:

~~~sql
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;
~~~

`V$CONTAINERS` bao gồm các container mà phiên được quyền nhìn thấy; từ root có thể quan sát cả root và PDB. Trong một PDB, kết quả các dynamic view có thể bị giới hạn theo container/quyền. Nếu không thấy PDB mong muốn, kiểm tra **đang kết nối vào root hay PDB nào** và có đủ quyền truy vấn, trước khi kết luận PDB đó không tồn tại.

### 5.4 PDB nào là đích kết nối của ứng dụng?

Tên PDB và service name thường liên quan nhưng **không được mặc định luôn trùng nhau**. Một PDB có thể gắn với nhiều service. Từ tài khoản quản trị có quyền xem, có thể liệt kê:

~~~sql
SELECT name, con_id
FROM v$services
ORDER BY con_id, name;
~~~

Đối chiếu `CON_ID` với PDB ở `V$PDBS`, rồi kiểm tra service tương ứng có được listener đăng ký hay không. Không nên dùng service trỏ vào `CDB$ROOT` để chạy DDL/DML cho schema ứng dụng khi mục tiêu là PDB riêng.

## 6. Kiểm tra listener ở hệ điều hành

**Listener hoạt động** là điều kiện quan trọng với kết nối Oracle Net từ xa, nhưng listener chạy **không có nghĩa** database/PDB đều đã OPEN. Ngược lại, phiên quản trị đăng nhập cục bộ qua OS authentication có thể làm việc trong lúc listener bị dừng, nên một kết nối local thành công chưa chứng minh mạng bên ngoài thông suốt.

### 6.1 Kiểm tra trạng thái listener

Ở terminal trên máy Oracle hoặc trong container có cài công cụ listener:

~~~sh
lsnrctl status
~~~

Nếu listener không mang tên mặc định `LISTENER`, chỉ rõ tên:

~~~sh
lsnrctl status MY_LISTENER
~~~

Các phần cần đọc trong kết quả `lsnrctl status`:

| Mục | Cách đọc |
|---|---|
| `Alias` | Tên listener đang được hỏi |
| `Start Date` và `Uptime` | Listener bắt đầu chạy khi nào |
| `Listening Endpoints Summary` | Protocol/host/port listener đang lắng nghe; chẳng hạn TCP port 1521 |
| `Services Summary` | Các service mà listener biết tới |
| `The command completed successfully` | Lệnh kiểm tra listener thực thi thành công; chưa phải bằng chứng tài khoản ứng dụng đăng nhập thành công |

Ví dụ **rút gọn và minh họa**:

~~~text
Alias                     LISTENER
Listening Endpoints Summary...
  (DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=db-host)(PORT=1521)))
Services Summary...
Service "my_pdb_service" has 1 instance(s).
  Instance "mycdb", status READY, has 1 handler(s) for this service...
The command completed successfully
~~~

Đừng lấy `HOST=db-host` hoặc `PORT=1521` từ ví dụ để dùng nguyên trong ứng dụng. Khi chạy trong Docker/VM, địa chỉ và cổng mà máy khác nhìn thấy có thể qua ánh xạ cổng/NAT nên khác với endpoint bên trong môi trường Oracle.

### 6.2 Kiểm tra chi tiết service và handler

~~~sh
lsnrctl services
~~~

Lệnh này cho biết service, instance và handler mà listener biết để xử lý yêu cầu kết nối. Với đăng ký động thông thường, trạng thái `READY` của instance/service là tín hiệu listener có thể tiếp nhận kết nối phù hợp. Trạng thái `UNKNOWN` thường gặp ở đăng ký tĩnh vì listener không biết chắc trạng thái instance qua cơ chế đó; **không thể kết luận instance bị lỗi chỉ từ chữ UNKNOWN**.

Nếu `lsnrctl status` báo listener đang chạy nhưng **không thấy service PDB**:

1. Kiểm tra PDB có ở `READ WRITE` hoặc chế độ mở được mong đợi không.
2. Kiểm tra service được cấu hình/khởi động cho PDB chưa; đừng đoán service chỉ từ tên database.
3. Kiểm tra listener đang hỏi đúng host, đúng Oracle Home và đúng cổng hay chưa.
4. Kiểm tra cơ chế đăng ký service động và cấu hình liên quan như `LOCAL_LISTENER` trong phạm vi quản trị.

Ví dụ đôi khi quản trị viên dùng `ALTER SYSTEM REGISTER` để yêu cầu đăng ký lại service; đây là **lệnh thay đổi trạng thái đăng ký**, không thuộc loạt lệnh kiểm tra chỉ đọc và chỉ nên thực hiện khi đã có thẩm quyền cũng như chẩn đoán đúng nguyên nhân.

### 6.3 Trên máy khách không có `lsnrctl`

`lsnrctl` là tiện ích Oracle Net và không nhất thiết được cài trên mọi máy chạy ứng dụng. Khi kiểm tra từ máy khách, thử kết nối đến đúng service bằng SQL*Plus/JDBC để xác nhận thực tế. Kiểm tra cổng ở mức TCP chỉ cho biết có đường mạng tới cổng, **không** chứng minh service PDB tồn tại hoặc thông tin đăng nhập đúng.

Trên Windows PowerShell, ví dụ kiểm tra kết nối TCP:

~~~powershell
Test-NetConnection -ComputerName db-host.example -Port 1521
~~~

Trên máy Unix/Linux có `nc`:

~~~sh
nc -vz db-host.example 1521
~~~

Những lệnh mạng này được thực hiện ở **máy có cùng đường đi mạng với ứng dụng**, trong khi `lsnrctl status` nên hỏi listener trên host phù hợp. Kết quả có thể khác nhau do firewall, container network, DNS, NAT hoặc load balancer.

## 7. Xác nhận bằng một kết nối thực tế tới PDB

Sau khi thấy database và PDB đã mở, listener đã đăng ký service, cần kiểm chứng đường đi **end-to-end** từ nơi ứng dụng sẽ chạy.

~~~sh
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

Sau khi đăng nhập thành công:

~~~sql
SELECT USER AS session_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'SERVER_HOST') AS server_host
FROM dual;
~~~

Kết quả cho thấy **tài khoản**, **container**, **service** và host gắn với phiên hiện tại. Một kết nối thành công nhưng `CONTAINER_NAME` là `CDB$ROOT` hoặc PDB khác với dự kiến vẫn là **sai đích nghiệp vụ**, dù không có lỗi mạng.

Nếu dùng Java JDBC Thin, cú pháp Easy Connect tương ứng thường là:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db-host.example:1521/my_pdb_service
spring.datasource.username=app_user
~~~

Đây chỉ là minh họa địa chỉ và username cho ứng dụng Spring Boot; mật khẩu/secret cần được cấp qua cơ chế cấu hình bảo mật của môi trường. Cú pháp `@//host:port/service` biểu diễn **service name**; đừng lẫn với cú pháp kết nối cũ dùng SID. Một service có thể chuyển đến nhiều instance trong RAC và nhiều handler mà không đổi cách client mô tả dịch vụ.

## 8. Tập lệnh kiểm tra nhanh theo đúng thứ tự

Trước tiên ở **terminal** (với listener trên host tương ứng):

~~~sh
sqlplus -v
lsnrctl version
lsnrctl status
lsnrctl services
~~~

Sau đó trong **SQL*Plus kết nối bằng tài khoản có quyền quan sát**, tốt nhất tại CDB root khi kiểm tra toàn bộ PDB:

~~~sql
SET LINESIZE 200
SET PAGESIZE 100

-- 1) Server version
SELECT banner FROM v$version;

-- 2) Instance
SELECT instance_name, host_name, status, database_status
FROM v$instance;

-- 3) Database và loại CDB
SELECT name, db_unique_name, cdb, open_mode, database_role
FROM v$database;

-- 4) Container hiện tại
SHOW CON_NAME

-- 5) Chỉ áp dụng khi CDB = YES và có đủ quyền
SHOW PDBS

SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;

-- 6) Các service mà instance biết tới
SELECT name, con_id
FROM v$services
ORDER BY con_id, name;
~~~

Cuối cùng, từ nơi đặt ứng dụng, đăng nhập bằng `app_user@//host:port/service` rồi xác nhận `CON_NAME` và `SERVICE_NAME` từ `SYS_CONTEXT`. **Không** dùng tài khoản `SYS`/`SYSTEM` để xác nhận quyền nghiệp vụ của `app_user`; nếu kết nối của quản trị viên thành công, điều đó chưa chứng minh ứng dụng đã được cấp quyền đúng.

Ghi chép mẫu cho một phiên thực hành:

| Hạng mục | Kết quả cần tự ghi |
|---|---|
| Oracle server version | Phiên bản từ `V$VERSION` / `V$INSTANCE` |
| Instance name/host/status | Ví dụ: `mycdb` / `db-host` / `OPEN` |
| Database name/open mode | Tên thật / `READ WRITE` hoặc trạng thái thực tế |
| CDB? | `YES` hoặc `NO` |
| Current container | `CDB$ROOT` hoặc PDB cụ thể |
| PDB ứng dụng/open mode | Tên PDB thật / `READ WRITE` hoặc trạng thái thực tế |
| Listener endpoint | Host/port thực tế từ listener |
| Service của PDB | Tên service và trạng thái handler |
| Kết nối từ ứng dụng | Thành công/thất bại; service/container được xác nhận |

Không nên ghi mật khẩu vào bảng kết quả, nhật ký bài thực hành hoặc ảnh chụp terminal.

## 9. Đọc lỗi thường gặp theo từng lớp

| Triệu chứng / thông báo | Lớp nên kiểm tra trước | Hướng xác minh |
|---|---|---|
| `sqlplus` hoặc `lsnrctl` không được nhận diện là lệnh | Máy chạy công cụ | Công cụ đã cài chưa, đúng Oracle Home/`PATH` chưa |
| `ORA-12541: TNS:no listener` hoặc thông báo tương đương | Listener / host / port / mạng | Listener có chạy và nghe đúng endpoint không; client có truy cập được cổng không |
| `ORA-12514`: listener không biết service được yêu cầu | Service registration / PDB | So sánh service trong connect string với `lsnrctl services`; kiểm tra PDB open và việc đăng ký service |
| `ORA-12505` liên quan SID listener không nhận diện | Kiểu connect identifier | Kiểm tra có dùng nhầm SID thay cho service name không |
| `ORA-01017`: sai thông tin xác thực | User/password/đích PDB | Tài khoản, mật khẩu và service kết nối có đúng không |
| `ORA-28000`: tài khoản bị khóa | Trạng thái user | Liên hệ người quản lý tài khoản; không tự thay đổi chính sách người dùng |
| `ORA-01034`: Oracle not available | Instance / đích kết nối | Kiểm tra instance đang chạy, database được mount/open đến đâu |
| `ORA-01109`: database not open | Database open mode | Kiểm tra `V$INSTANCE` và `V$DATABASE` trong phiên quản trị phù hợp |
| `ORA-00942` / `ORA-01031` khi truy vấn `V$...` | Quyền quan sát metadata | Dùng tài khoản được phép hoặc hỏi DBA cấp quyền xem phù hợp |
| Listener chạy, nhưng PDB ở `MOUNTED` | PDB state | Kiểm tra `SHOW PDBS`; kết nối đến service PDB có thể chưa sẵn sàng |
| Kết nối thành công nhưng không thấy bảng ứng dụng | Sai PDB hoặc schema/quyền | Kiểm tra `CON_NAME`, `SESSION_USER`, schema và quyền đối tượng |

Mã lỗi trong bảng giúp **khoanh vùng**, không phải chẩn đoán chắc chắn trong mọi môi trường. Ví dụ `ORA-12514` còn có thể xuất hiện khi database vừa khởi động và chưa kịp đăng ký service, client trỏ nhầm listener, hoặc service đã bị dừng. Cần đọc thông báo đầy đủ và đối chiếu các bước kiểm tra.

### Cách cô lập sự cố theo câu hỏi

~~~mermaid
flowchart TD
    A["Ứng dụng không vào được Oracle"] --> B{"Từ client tới host/port được không?"}
    B -->|Không| C["Kiểm tra DNS, mạng, firewall, listener endpoint"]
    B -->|Có| D{"Listener thấy service yêu cầu?"}
    D -->|Không| E["Đối chiếu service, PDB OPEN, registration"]
    D -->|Có| F{"Đăng nhập qua service thành công?"}
    F -->|Không| G["Kiểm tra lỗi xác thực, quyền, hạn chế phiên, log"]
    F -->|Có| H{"CON_NAME và schema đúng?"}
    H -->|Không| I["Sửa đích service hoặc ngữ cảnh schema"]
    H -->|Có| J["Kiểm tra truy vấn và nghiệp vụ ứng dụng"]
~~~

Thực tế có thể nhiều lỗi xuất hiện cùng lúc. Sơ đồ nhằm tránh việc chữa sai lớp, chẳng hạn khởi động lại listener chỉ vì tài khoản nhập sai mật khẩu hoặc sửa JDBC URL khi PDB chưa được mở.

## 10. Ví dụ kết luận từ hai môi trường khác nhau

**Môi trường A — Sẵn sàng cho bài thực hành ghi dữ liệu**

~~~text
V$INSTANCE.STATUS       = OPEN
V$DATABASE.OPEN_MODE    = READ WRITE
V$DATABASE.CDB          = YES
PDB ứng dụng OPEN_MODE  = READ WRITE
lsnrctl services        = service của PDB có handler READY
Kết nối app_user        = thành công, CON_NAME đúng PDB
~~~

Những thông tin này là **các điều kiện quan sát thuận lợi**, không khẳng định toàn bộ chính sách cấp quyền bảng, dung lượng, hiệu năng hay HA đã được kiểm tra. Để thực hiện `INSERT` thành công, tài khoản vẫn cần quyền tương ứng và các ràng buộc dữ liệu phải được thỏa mãn.

**Môi trường B — CDB đã mở, nhưng ứng dụng không vào PDB**

~~~text
V$INSTANCE.STATUS       = OPEN
V$DATABASE.OPEN_MODE    = READ WRITE
V$DATABASE.CDB          = YES
PDB ứng dụng OPEN_MODE  = MOUNTED
lsnrctl status          = listener vẫn hoạt động
Kết nối service PDB     = thất bại hoặc service không sẵn sàng
~~~

Không có mâu thuẫn: trạng thái `OPEN` của instance/CDB và trạng thái `MOUNTED` của một PDB là hai mức khác nhau. Người được giao quản trị PDB cần xác minh lý do PDB chưa mở và áp dụng quy trình vận hành phù hợp. Người thực hành chỉ đọc được phép ghi nhận rõ lỗi và báo đúng thành phần.

## 11. Bài thực hành tự kiểm tra

Thực hiện tại một môi trường Oracle được phép truy cập và trả lời các câu hỏi sau bằng kết quả thu thập **thực tế**:

1. Phiên bản `sqlplus -v` có giống phiên bản server trong `V$VERSION` không? Nếu khác, từng kết quả phản ánh thành phần nào?
2. `V$INSTANCE.STATUS` và `V$DATABASE.OPEN_MODE` đang cho biết database ở giai đoạn nào?
3. `V$DATABASE.CDB` là `YES` hay `NO`? Nếu là `YES`, `SHOW CON_NAME` đang trả về root hay PDB?
4. `SHOW PDBS` cho thấy PDB ứng dụng ở `MOUNTED`, `READ ONLY` hay `READ WRITE`? Tại sao không nên coi trạng thái `PDB$SEED = READ ONLY` là lỗi?
5. `lsnrctl status` đang lắng nghe host và port nào? `lsnrctl services` có tên service client đang dùng không?
6. Từ máy ứng dụng, bạn có thể đăng nhập bằng service của PDB không? Truy vấn `SYS_CONTEXT('USERENV','CON_NAME')` trả về điều gì?
7. Nếu một kết nối local `/ as sysdba` thành công nhưng kết nối từ ứng dụng báo `ORA-12514`, bạn sẽ kiểm tra lớp nào tiếp theo?

Để hoàn thành bài thực hành, cần diễn giải được **vì sao một database OPEN chưa đủ bảo đảm ứng dụng kết nối và ghi được dữ liệu**: PDB phải có chế độ mở phù hợp, listener phải biết service được yêu cầu, mạng phải tới được listener, phiên đăng nhập phải đúng đích và tài khoản phải có quyền cần thiết.

## 12. Ghi nhớ mối quan hệ giữa bốn phép kiểm tra

- **Phiên bản** trả lời “Mình đang chạy bộ Oracle nào?”; cần phân biệt SQL client, listener và database engine.
- **Instance/database state** trả lời “Oracle đã khởi động và database đang ở giai đoạn nào?”; đọc `V$INSTANCE` cùng `V$DATABASE`.
- **PDB state** trả lời “Container dữ liệu của ứng dụng đã mở ở chế độ thích hợp chưa?”; kiểm tra `CON_NAME` và `V$PDBS` khi là CDB.
- **Listener/service** trả lời “Yêu cầu kết nối từ client có được định tuyến đến đúng dịch vụ không?”; kiểm tra endpoint bằng `lsnrctl status`, service bằng `lsnrctl services`, rồi thử đăng nhập thực tế.

Thứ tự thực hành hiệu quả là: **xác định phiên bản → kiểm tra instance và database → xác định CDB/PDB → kiểm tra listener/service → thử kết nối từ máy ứng dụng → xác nhận container đang dùng**. Mỗi bước chỉ chứng minh một phần của hệ thống; phối hợp chúng mới tạo được bức tranh đủ rõ để bắt đầu các bài SQL tiếp theo.
