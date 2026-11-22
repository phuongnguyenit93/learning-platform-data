# Cấu hình `tnsnames.ora`, `sqlnet.ora` và `listener.ora` trong Oracle Database

Khi một ứng dụng kết nối Oracle Database qua mạng, nó cần biết **địa chỉ máy chủ**, **cổng lắng nghe** và **database service** muốn truy cập. Oracle Net Services cung cấp ba tệp cấu hình quen thuộc để giải quyết các phần khác nhau của quá trình đó: `tnsnames.ora`, `sqlnet.ora` và `listener.ora`.

Đây là bài thực hành về **công cụ và kết nối** trong hệ quản trị cơ sở dữ liệu quan hệ Oracle. Người học sẽ cấu hình kết nối SQL*Plus trước, sau đó quan sát hoặc cấu hình listener trên máy chủ. Mỗi tệp có phạm vi áp dụng riêng: chỉnh đúng nội dung nhưng sai máy, sai Oracle Home hoặc sai thư mục cấu hình thì kết nối vẫn có thể thất bại.

**Kết quả mong đợi:** Bạn có thể giải thích vai trò từng tệp, tạo một TNS alias kết nối đến PDB, thiết lập thứ tự phân giải tên qua `sqlnet.ora`, nhận biết cấu hình listener và đăng ký service, dùng công cụ kiểm tra đúng lớp lỗi, và tránh nhầm SID với service name.

## 1. Bức tranh tổng thể của Oracle Net

Một phiên kết nối qua TCP thường diễn ra như sau:

~~~text
MÁY CLIENT                                             MÁY DATABASE SERVER

SQL*Plus / ứng dụng
     |
     |  sqlplus lab_user@LAB_PDB
     v
sqlnet.ora (quy định phương thức phân giải tên)
     |
     v
tnsnames.ora (LAB_PDB → host, port, service)
     |
     |  TCP tới db-host.example.com:1521
     +-------------------------------------------> Oracle Net Listener
                                                    (listener.ora)
                                                          |
                                                          | tra service được
                                                          | database đăng ký
                                                          v
                                                    Service FREEPDB1
                                                          |
                                                          v
                                                    Oracle instance / PDB
~~~

Đường đi trên là ví dụ khi **dùng TNS alias**. Nếu dùng chuỗi Easy Connect như `//db-host.example.com:1521/FREEPDB1`, client đã có trực tiếp host, port, service và có thể không cần `tnsnames.ora`. Tuy nhiên các thiết lập Oracle Net khác ở phía client vẫn có thể ảnh hưởng phiên kết nối.

| Tệp | Thường nằm ở đâu? | Chức năng chính | Ai cần chỉnh? |
| --- | --- | --- | --- |
| `tnsnames.ora` | Máy **client**, hoặc máy server khi server cũng đóng vai trò client | Ánh xạ **TNS alias** sang connect descriptor | Người cấu hình client/kết nối ứng dụng |
| `sqlnet.ora` | Có thể có **cả client lẫn server** | Cấu hình phương thức đặt tên, xác thực, bảo mật, timeout, trace… tùy tham số | Người quản trị từng môi trường Oracle Net |
| `listener.ora` | Máy **database server** nơi chạy listener | Địa chỉ/cổng listener và các tham số listener | DBA/người quản trị Oracle Net trên server |

Ba tên trong ví dụ cần phân biệt:

- **TNS alias `LAB_PDB`:** tên do client tự đặt, khai báo trong `tnsnames.ora`.
- **Listener `LISTENER`:** tiến trình trên server nhận yêu cầu kết nối, thường dùng cổng TCP `1521`.
- **Database service `FREEPDB1`:** tên service do Oracle database cung cấp, thông thường dẫn vào một PDB cụ thể.

**SID** là tên *instance* cục bộ, ví dụ `FREE`; **service name** là tên client yêu cầu listener định tuyến, ví dụ `FREEPDB1`. Trong mô hình multitenant, không được suy luận SID chính là tên PDB. Với client kết nối qua TCP, nên dùng `SERVICE_NAME` của dịch vụ phù hợp thay vì tự đoán SID.

## 2. Chuẩn bị môi trường và xác định cấu hình thực tế

Các ví dụ xuyên suốt sử dụng hệ thống minh họa:

| Thành phần | Giá trị ví dụ | Cần thay bằng |
| --- | --- | --- |
| Máy database | `db-host.example.com` | Tên DNS hoặc địa chỉ IP server thực tế |
| Listener | `LISTENER` | Tên listener được hệ thống quản lý |
| Giao thức/cổng | `TCP / 1521` | Protocol/port mà listener thực sự công bố |
| Service | `FREEPDB1` | Tên service database/PDB thực tế |
| Instance SID (để quản trị local) | `FREE` | SID của instance trên máy chủ |
| TNS alias trên client | `LAB_PDB` | Bí danh tùy chọn, có thể đặt theo môi trường |
| Database user | `LAB_USER` | User có quyền đăng nhập vào PDB |

`FREE` và `FREEPDB1` là cặp tên dùng trong nhiều cài đặt **Oracle Database Free**. Với Oracle XE thường gặp `XE` / `XEPDB1`, còn database được cài riêng có thể dùng tên bất kỳ. Không đổi tên service thực tế chỉ để khớp một ví dụ trong tài liệu.

Trước khi sửa file, kiểm tra:

1. SQL*Plus hoặc một Oracle client phù hợp đã được cài trên máy sẽ chạy lệnh kết nối.
2. Có thông tin host, port, service name và user/password hợp lệ từ hệ thống cần kết nối.
3. Có quyền sửa file cấu hình trong thư mục được chọn. **Chỉ người quản trị được phép** chỉnh cấu hình listener và tham số database trên server.
4. Phân biệt môi trường local, VM, Docker và máy khác. `127.0.0.1`/`localhost` luôn chỉ về **môi trường mạng hiện tại của client**, không tự trỏ tới server Oracle ở máy hoặc container khác.

### 2.1. Oracle tìm các tệp `.ora` ở đâu?

Trên bản cài Oracle Database Home truyền thống, thư mục thường gặp là:

~~~text
Linux:    $ORACLE_HOME/network/admin
Windows:  %ORACLE_HOME%\network\admin
~~~

Một số bản cài dùng **read-only Oracle Home**, khi đó cấu hình có thể nằm trong `ORACLE_BASE_HOME/network/admin`. Oracle Instant Client có thể dùng thư mục `network/admin` bên trong thư mục Instant Client. Nếu chạy Oracle Grid Infrastructure hoặc RAC, listener có thể thuộc **Grid Home** và được quản lý bởi công cụ cluster thay vì cách cấu hình thủ công của máy đơn.

Biến môi trường **`TNS_ADMIN` trỏ đến thư mục chứa các tệp**, ví dụ:

~~~text
Linux:    TNS_ADMIN=/home/lab/oracle-net
Windows:  TNS_ADMIN=C:\oracle\net-admin
~~~

Khi thiết lập `TNS_ADMIN` cho tiến trình client, Oracle Net ưu tiên tìm cấu hình ở thư mục này; nếu không đặt, cơ chế tìm kiếm mặc định phụ thuộc bản cài và nền tảng. Trên Windows, dịch vụ có thể còn tra thông tin từ Registry. **Không đặt `TNS_ADMIN` thành đường dẫn đầy đủ đến `tnsnames.ora`.**

Điểm dễ bỏ qua: `TNS_ADMIN` là biến của **tiến trình**. Terminal mới, IDE, ứng dụng Java, Windows Service hoặc listener đã chạy từ trước có thể sử dụng môi trường khác nhau. Thay đổi biến trong terminal đang mở **không tự chuyển cấu hình của các tiến trình đã chạy**.

## 3. Cấu hình `tnsnames.ora`: đặt tên kết nối từ phía client

### 3.1. Cú pháp của một TNS alias

Trong thư mục cấu hình mà client đang sử dụng, tạo hoặc bổ sung file văn bản thuần `tnsnames.ora`:

~~~text
LAB_PDB =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = db-host.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = FREEPDB1)
    )
  )
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `LAB_PDB` | Alias nhập sau ký hiệu `@` trong SQL*Plus |
| `DESCRIPTION` | Nhóm thông tin mô tả đích cần kết nối |
| `ADDRESS` | Địa chỉ mạng của listener |
| `PROTOCOL = TCP` | Sử dụng kết nối TCP |
| `HOST` | Host mà client phải truy cập được |
| `PORT` | Cổng listener đang nhận kết nối |
| `CONNECT_DATA` | Thông tin nhận dạng dịch vụ Oracle |
| `SERVICE_NAME = FREEPDB1` | Service đích, thường tương ứng với PDB thực hành |

Oracle Net sử dụng cú pháp cặp ngoặc `(KEY = VALUE)`, **không phải YAML hoặc JSON**. Đảm bảo các dấu ngoặc mở/đóng khớp nhau; dấu `#` có thể dùng cho comment. Tên file phải chính xác là `tnsnames.ora`, không để trình soạn thảo Windows vô tình lưu thành `tnsnames.ora.txt`.

Một file có thể chứa nhiều alias khác nhau:

~~~text
LAB_PDB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db-host.example.com)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = FREEPDB1))
  )

REPORTING =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = reports.example.com)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = REPORTSVC))
  )
~~~

Ví dụ trên cho thấy **alias là nhãn của phía client**; `REPORTING` không bắt buộc trùng với `REPORTSVC`, và tên listener cũng không nhất thiết trùng bất kỳ tên nào trong số đó.

### 3.2. Kết nối qua TNS alias

Sau khi có file, dùng:

~~~bash
tnsping LAB_PDB
sqlplus -L lab_user@LAB_PDB
~~~

`tnsping` chỉ có nếu bộ client cài tiện ích này. Kết quả `OK` cho biết Oracle Net có thể phân giải connect identifier và nhận phản hồi theo đường kết nối được kiểm tra; nó **không kiểm tra mật khẩu** và **không chứng minh rằng PDB/service đã sẵn sàng cho câu lệnh SQL**.

`sqlplus -L lab_user@LAB_PDB` sẽ yêu cầu nhập mật khẩu, đồng thời giới hạn số lần thử đăng nhập; cách này tránh ghi mật khẩu trong lệnh, lịch sử shell hoặc log. Với một phiên đã kết nối thành công, chạy:

~~~sql
SELECT USER AS current_user FROM dual;

SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

`CONTAINER_NAME` giúp xác nhận bạn đã vào PDB dự kiến. Dùng `EXIT;` để rời SQL*Plus.

### 3.3. Đối chiếu bằng Easy Connect

Easy Connect cho phép sử dụng connect identifier trực tiếp:

~~~bash
sqlplus -L lab_user@//db-host.example.com:1521/FREEPDB1
~~~

Nếu câu lệnh này thành công nhưng `lab_user@LAB_PDB` báo lỗi phân giải tên, bạn có cơ sở kiểm tra **`tnsnames.ora`, `TNS_ADMIN`, alias và `sqlnet.ora`** trước khi thay đổi listener/database.

Một số cấu hình doanh nghiệp dùng nhiều address cho HA, RAC/SCAN, TCPS hoặc wallet. Những mô hình đó có thêm tham số và phụ thuộc hạ tầng thật; không nên chép một `ADDRESS_LIST` tùy ý và mặc định kết nối sẽ tự dự phòng chính xác.

## 4. Cấu hình `sqlnet.ora`: hành vi Oracle Net

`sqlnet.ora` có thể tồn tại ở cả client và server, nhưng **mỗi tiến trình đọc cấu hình tương ứng với môi trường chạy của nó**. Phía client thường quan tâm trước tiên đến cách phân giải connect identifier.

### 4.1. Cấu hình tối thiểu cho TNS alias và Easy Connect

Tạo hoặc bổ sung `sqlnet.ora` trong cùng thư mục `TNS_ADMIN` mà client sử dụng:

~~~text
# Uu tien tim alias trong tnsnames.ora; sau do ho tro Easy Connect.
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
~~~

`NAMES.DIRECTORY_PATH` chỉ thứ tự các phương thức phân giải tên. Trong ví dụ:

1. `TNSNAMES` tìm alias `LAB_PDB` trong `tnsnames.ora`.
2. `EZCONNECT` cho phép sử dụng chuỗi chứa host, port và service theo cú pháp Easy Connect.

Trên hệ thống đã có `sqlnet.ora` do DBA quản lý, **không thay thế toàn bộ nội dung bằng một dòng duy nhất**. File có thể chứa chính sách xác thực, mã hóa, TLS, tracing hoặc quy tắc tổ chức. Chỉ chỉnh phần liên quan khi được phép; giữ nguyên những tham số khác.

### 4.2. Các nhóm tham số thường gặp

| Tham số / nhóm tham số | Ý nghĩa thực hành | Lưu ý |
| --- | --- | --- |
| `NAMES.DIRECTORY_PATH` | Thứ tự tra TNS alias, Easy Connect và các naming method khác | Thiếu `TNSNAMES` có thể làm alias không phân giải được |
| `NAMES.DEFAULT_DOMAIN` | Bổ sung domain theo chính sách đặt tên | Có thể khiến tên không đầy đủ được diễn giải khác mong đợi |
| `SQLNET.OUTBOUND_CONNECT_TIMEOUT` | Giới hạn thời gian client chờ hoàn thành kết nối outbound | Chọn ngưỡng theo mạng/ứng dụng; không phải query timeout |
| `SQLNET.EXPIRE_TIME` | Giúp phát hiện các kết nối mạng không còn hoạt động theo cơ chế của Oracle Net | Không đồng nghĩa giới hạn thời gian chạy SQL |
| `SQLNET.AUTHENTICATION_SERVICES` | Chọn các cơ chế xác thực được Oracle Net hỗ trợ | Có thể ảnh hưởng OS/external authentication; không đổi tùy tiện |
| Các tham số mã hóa / TLS / wallet | Quy định khả năng kết nối an toàn và chứng thư | Client và server cần cấu hình tương thích, thường theo chính sách DBA |

Để thực hành **phân giải tên**, chỉ cần dòng `NAMES.DIRECTORY_PATH`. Không nên copy các thông số bảo mật như `SQLNET.AUTHENTICATION_SERVICES=(NONE)`, tắt mã hóa hoặc cấu hình wallet không phù hợp chỉ để làm ví dụ «kết nối cho được».

### 4.3. Xác định Oracle Net thật sự đọc file nào

Trên client, dùng `tnsping LAB_PDB` nếu có. Đầu ra có thể thể hiện đường dẫn file tham số đã dùng và descriptor được phân giải, giúp phát hiện tình huống đã chỉnh `sqlnet.ora` trong một Oracle Home nhưng client đang chạy từ một Home khác.

Nếu một ứng dụng không dùng SQL*Plus, hãy kiểm tra cách **driver và tiến trình ứng dụng** nhận cấu hình. Chẳng hạn, JDBC Thin với URL `jdbc:oracle:thin:@//db-host.example.com:1521/FREEPDB1` thường không cần alias `tnsnames.ora`; kết nối bằng alias có thể yêu cầu cấu hình đường dẫn Oracle Net dành cho driver. Một thiết lập trong terminal không tự truyền sang tiến trình IDE đã mở trước đó.

## 5. Cấu hình `listener.ora`: địa chỉ nhận kết nối trên database server

Listener là tiến trình riêng nhận kết nối ban đầu. Nó không đồng nghĩa với database instance; listener có thể đang chạy trong khi database/PDB vẫn chưa mở, hoặc database đang chạy nhưng listener chưa nhận yêu cầu mạng.

### 5.1. Cấu hình listener TCP cơ bản

Trên **database server**, với một môi trường thực hành do bạn có quyền quản trị, file `listener.ora` có thể có dạng:

~~~text
LISTENER =
  (DESCRIPTION_LIST =
    (DESCRIPTION =
      (ADDRESS = (PROTOCOL = TCP)
                 (HOST = db-host.example.com)
                 (PORT = 1521))
    )
  )
~~~

`LISTENER` là **tên listener**, không phải SID, PDB hoặc service. `HOST` phải là địa chỉ/tên mà server có thể bind, đồng thời phù hợp với cách client truy cập. Listener nhận kết nối trên cổng `1521` trong ví dụ; cổng đó phải được cho phép qua firewall và không bị tiến trình khác chiếm dụng.

**Không phải mọi hệ thống đều cần tự tạo file `listener.ora`.** Oracle có thể chạy một listener mặc định tên `LISTENER` với TCP cổng `1521` ngay cả khi chưa có file cấu hình riêng. Các công cụ cài đặt Oracle cũng có thể đã tạo và quản lý file này. Luôn xem cấu hình hiện hành trước khi sửa.

> Trên máy đã có database phục vụ người khác, không ghi đè `listener.ora` và không tự ý đổi địa chỉ/cổng. Sao lưu file hiện tại, xác nhận Oracle Home/Grid Home nào sở hữu listener và lên kế hoạch áp dụng thay đổi cùng DBA. Phần cấu hình server ở đây phù hợp nhất với VM/lab dùng riêng.

### 5.2. Quản lý listener bằng `lsnrctl`

Chạy trên **server** bằng tài khoản có quyền quản lý listener:

~~~bash
# Kiem tra listener hien tai:
lsnrctl status LISTENER

# Xem nhung service va handler listener biet:
lsnrctl services LISTENER

# Chi chay khi listener chua duoc khoi dong:
lsnrctl start LISTENER
~~~

`lsnrctl status` thường hiển thị đường dẫn **Listener Parameter File**, endpoints đang nghe và tóm tắt services. Đây là dấu hiệu quan trọng để tìm đúng `listener.ora` thực sự được tiến trình sử dụng. `lsnrctl services` có thông tin chi tiết hơn về service và handler.

Nếu đã sửa một tham số listener phù hợp với việc nạp lại:

~~~bash
lsnrctl reload LISTENER
lsnrctl status LISTENER
lsnrctl services LISTENER
~~~

Đổi cổng hoặc địa chỉ endpoint có thể đòi hỏi quy trình restart listener và cập nhật đồng thời cấu hình client/database; không giả định mọi thay đổi sẽ được áp dụng an toàn bằng `reload`. Listener trên Oracle Restart/RAC thường thuộc quyền quản lý của Grid Infrastructure (`srvctl`); không điều khiển nó như một listener độc lập khi cluster là nguồn quản lý chính.

### 5.3. Đăng ký service động qua LREG

Trên Oracle hiện đại, database process **LREG** tự đăng ký các dịch vụ và instance handler với listener. Vì vậy một `listener.ora` thông thường **không cần khai báo thủ công từng PDB**.

~~~text
Database instance (LREG)
    │  dang ky ten service, handler, trang thai
    ▼
Listener:1521
    │  nhan ket noi toi SERVICE_NAME=FREEPDB1
    ▼
Service/handler phu hop → database session
~~~

Trên server có quyền quản trị, có thể đối chiếu:

~~~bash
lsnrctl services LISTENER
~~~

Khi có service `FREEPDB1`, listener đã biết tên mà client yêu cầu. Trạng thái handler `READY` thường là kết quả của đăng ký động. Nếu vừa khởi động listener, có thể cần đợi database đăng ký lại hoặc yêu cầu đăng ký từ phía instance bằng quyền DBA:

~~~sql
ALTER SYSTEM REGISTER;
~~~

Thao tác SQL trên phải thực hiện trong phiên quản trị database phù hợp; không nhập vào dấu nhắc của `lsnrctl`. Nếu PDB chưa mở hoặc service chưa khởi chạy, chỉ chạy `ALTER SYSTEM REGISTER` không thay thế việc xử lý trạng thái PDB/service.

**Khai báo tĩnh** bằng cấu trúc `SID_LIST_<listener_name>` trong `listener.ora` chỉ cần ở một số tình huống đặc thù (chẳng hạn một số quy trình khởi động/quản trị từ xa hoặc external procedures). Với kết nối ứng dụng thông thường đến PDB, hãy ưu tiên service registration động. Không tạo `SID_LIST` giả chỉ vì thấy `ORA-12514`: nguyên nhân có thể là service name sai, PDB chưa mở, database chưa đăng ký hoặc listener lắng nghe sai cổng.

### 5.4. Khi listener sử dụng cổng khác 1521

Giả sử trong lab bạn được giao listener TCP cổng `1522`. Ba chỗ phải thống nhất:

1. `listener.ora`: listener thực sự bind vào `HOST=db-host.example.com, PORT=1522`.
2. Database: tiến trình LREG biết địa chỉ listener cần đăng ký, thường qua tham số `LOCAL_LISTENER`.
3. `tnsnames.ora` của client: `ADDRESS` sử dụng port `1522` tương ứng.

Một ví dụ **chỉ dành cho instance lab tự quản lý**:

~~~sql
-- Ket noi quyen DBA tren CDB/instance phu hop.
ALTER SYSTEM SET LOCAL_LISTENER =
  '(ADDRESS=(PROTOCOL=TCP)(HOST=db-host.example.com)(PORT=1522))'
  SCOPE=BOTH;

ALTER SYSTEM REGISTER;
~~~

Lệnh `LOCAL_LISTENER` thay đổi địa chỉ listener mà instance đăng ký và có thể ảnh hưởng các kết nối hiện hữu/tương lai, nhất là khi instance dùng nhiều listener. Chỉ chạy sau khi biết cấu hình hiện hành; hệ thống nhiều listener, RAC và cluster có quy tắc riêng. Nếu bạn **chỉ cấu hình client kết nối tới listener đã tồn tại**, không cần thay đổi `LOCAL_LISTENER`.

## 6. Thực hành: cấu hình client kết nối đến Oracle PDB

Phần thực hành chính chỉ yêu cầu một **Oracle client** và một database server đã có listener/service hoạt động. Không cần thay đổi listener trên máy chủ.

### Bước 1 — Chỉ định thư mục Oracle Net cho client

Trên Linux/Bash:

~~~bash
export TNS_ADMIN="$HOME/oracle-net-lab"
mkdir -p "$TNS_ADMIN"
echo "$TNS_ADMIN"
command -v sqlplus
sqlplus -v
~~~

Trên Windows PowerShell:

~~~powershell
$env:TNS_ADMIN = Join-Path $HOME 'oracle-net-lab'
New-Item -ItemType Directory -Force -Path $env:TNS_ADMIN
$env:TNS_ADMIN
where.exe sqlplus
sqlplus -v
~~~

Trên Windows Command Prompt (nếu muốn dùng CMD thay PowerShell):

~~~bat
set "TNS_ADMIN=C:\oracle\net-lab"
if not exist "%TNS_ADMIN%" mkdir "%TNS_ADMIN%"
echo %TNS_ADMIN%
where sqlplus
sqlplus -v
~~~

Hãy chạy **bộ lệnh của đúng hệ điều hành/shell**, không trộn cú pháp `$env:`, `%VAR%` và `$VAR`. Đường dẫn `TNS_ADMIN` phải được tiến trình SQL*Plus sử dụng; terminal mới không mặc nhiên giữ giá trị vừa đặt nếu chưa cấu hình lâu dài.

### Bước 2 — Tạo `tnsnames.ora`

Trong thư mục vừa tạo, dùng trình soạn thảo để lưu file `tnsnames.ora` với nội dung:

~~~text
# Thay HOST, PORT va SERVICE_NAME theo may Oracle thuc te.
LAB_PDB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)
               (HOST = db-host.example.com)
               (PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = FREEPDB1))
  )
~~~

Để thử từ **cùng máy với listener**, bạn có thể dùng `HOST=127.0.0.1` nếu listener đang nghe ở giao diện tương ứng. Nếu client chạy trong container, `127.0.0.1` là container client và thường không trỏ đến container database; dùng hostname và cổng nội bộ phù hợp.

### Bước 3 — Tạo `sqlnet.ora`

Trong **cùng thư mục**, lưu file `sqlnet.ora`:

~~~text
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
~~~

Các file trong lab là ví dụ tối giản. Nếu thư mục thực tế đã chứa cấu hình do tổ chức quản lý, hãy **thêm alias hoặc chỉnh tham số có chủ đích** thay vì ghi đè toàn bộ file.

### Bước 4 — Kiểm tra từ mạng tới SQL

Trên client:

~~~bash
# Chi su dung neu bo client co tien ich tnsping:
tnsping LAB_PDB

# Kiem tra ket noi thuc su va nhap password khi duoc hoi:
sqlplus -L lab_user@LAB_PDB
~~~

Sau khi kết nối vào SQL*Plus, chạy:

~~~sql
SELECT
    USER AS current_user,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;

EXIT;
~~~

Nếu ví dụ phù hợp với máy cài của bạn, kết quả cần thể hiện user `LAB_USER` tại PDB `FREEPDB1`. Không dựa vào việc `tnsping` trả `OK` để kết luận đăng nhập thành công.

### Bước 5 — So sánh với kết nối không dùng alias

~~~bash
sqlplus -L lab_user@//db-host.example.com:1521/FREEPDB1
~~~

So sánh hai cách:

| Cách kết nối | Phụ thuộc vào | Phù hợp với |
| --- | --- | --- |
| `lab_user@LAB_PDB` | Alias trong `tnsnames.ora` và naming method phù hợp | Đặt tên rõ ràng cho môi trường, tránh lặp host/port/service trong lệnh |
| `lab_user@//host:port/service` | Host/port/service trực tiếp và hỗ trợ Easy Connect | Kiểm tra nhanh hoặc môi trường không cần file alias |

Nếu Easy Connect hoạt động còn alias không hoạt động, kiểm tra lớp **client name resolution** trước. Nếu cả hai đều thất bại với cùng host/port/service, kiểm tra kết nối mạng, listener, service và xác thực theo mã lỗi.

## 7. Kiểm tra và khoanh vùng lỗi

Không nên sửa cả ba file đồng thời khi chưa biết lỗi nằm ở đâu. Một quy trình thực dụng là:

~~~text
1. Client co chay duoc?          sqlplus -v
              |
2. Co tim duoc alias?            tnsping LAB_PDB (neu co)
              |
3. Host/port co truy cap duoc?   test ket noi TCP
              |
4. Listener co biet service?     lsnrctl services LISTENER (tren server)
              |
5. Co dang nhap vao DB duoc?     sqlplus -L lab_user@LAB_PDB
              |
6. Dung PDB/user hay chua?       SYS_CONTEXT('USERENV', 'CON_NAME')
~~~

### 7.1. Lệnh hữu ích theo nền tảng

Trên Linux:

~~~bash
printf 'TNS_ADMIN=%s\n' "$TNS_ADMIN"
command -v sqlplus
sqlplus -v
tnsping LAB_PDB

# Neu may co netcat (nc), thu TCP toi port listener:
nc -vz db-host.example.com 1521
~~~

Trên Windows PowerShell:

~~~powershell
$env:TNS_ADMIN
where.exe sqlplus
sqlplus -v
tnsping LAB_PDB
Test-NetConnection -ComputerName db-host.example.com -Port 1521
~~~

Lệnh kiểm tra TCP chỉ chứng minh host/port có thể nhận kết nối ở mức mạng; **không xác thực Oracle service, PDB hoặc user**. Nếu không cài `tnsping` hoặc `nc` thì có thể bỏ qua công cụ đó và thử trực tiếp bằng SQL*Plus.

Trên **database server**:

~~~bash
lsnrctl status LISTENER
lsnrctl services LISTENER
~~~

Nếu `lsnrctl status` hiển thị `Listener Parameter File` khác đường dẫn bạn vừa sửa, hãy xác định **listener đang dùng Oracle Home/TNS_ADMIN nào**. Đừng mặc định file ở thư mục client chính là cấu hình server listener.

### 7.2. Bảng lỗi thường gặp

| Biểu hiện / mã lỗi | Lớp nghi ngờ | Hướng kiểm tra |
| --- | --- | --- |
| Không chạy được `sqlplus` | Chưa cài client / sai `PATH` | `command -v sqlplus` hoặc `where.exe sqlplus`; kiểm tra executable và thư viện phụ thuộc |
| `ORA-12154` | Client không phân giải được connect identifier | `TNS_ADMIN`, đúng tên file, alias, dấu ngoặc, `NAMES.DIRECTORY_PATH` và SQL*Plus đang dùng Home nào |
| `TNS-03505` khi `tnsping` | Alias không phân giải được | Tên alias, `tnsnames.ora` thực tế, `TNS_ADMIN`, phương thức naming |
| `ORA-12541` | Không có listener phù hợp tại endpoint được chọn | Host, port, listener đang chạy, firewall, DNS và Docker port mapping |
| `ORA-12545` | Host/địa chỉ đích không được xác định hoặc kết nối không thể thực hiện | DNS, IP, mạng, địa chỉ server trong descriptor |
| `ORA-12514` | Listener không biết `SERVICE_NAME` yêu cầu | `lsnrctl services`, service name, DB/PDB đang chạy, service registration và listener port |
| `ORA-12505` | Listener không biết SID mà connect descriptor yêu cầu | Tránh nhầm `SID` với `SERVICE_NAME`, nhất là khi muốn vào PDB |
| `ORA-01017` | Sai thông tin xác thực/đích kết nối | Kiểm tra user/password, PDB/service và chính sách đăng nhập |
| `ORA-28000` | Tài khoản bị khóa | Nhờ người có quyền quản trị kiểm tra trạng thái user; không sửa file Oracle Net để chữa |
| Kết nối alias được trong terminal, không được trong IDE | Môi trường client khác | So sánh `TNS_ADMIN`, client/driver, file cấu hình và quá trình khởi động IDE |
| Listener chạy nhưng service không hiện | Database chưa đăng ký hoặc PDB/service chưa sẵn sàng | Kiểm tra `LOCAL_LISTENER`, trạng thái DB/PDB, dùng `ALTER SYSTEM REGISTER` khi thích hợp |

### 7.3. Phân biệt ba lỗi rất dễ nhầm

**Tình huống A — `ORA-12154`:** client chưa tìm được descriptor cho `LAB_PDB`. Listener có thể đang chạy hoàn toàn bình thường; ưu tiên kiểm tra `tnsnames.ora` và `sqlnet.ora` trên máy client.

**Tình huống B — `ORA-12541`:** client đã biết endpoint nhưng không gặp listener phù hợp tại host/port. Kiểm tra listener, DNS, firewall, port mapping và địa chỉ bind trên server. Việc đặt một alias khác tên không tự làm listener chạy.

**Tình huống C — `ORA-12514`:** listener nhận yêu cầu nhưng không biết service mà client chỉ định. Xem `lsnrctl services`, tên service thực tế, trạng thái PDB và quá trình đăng ký động; thông thường không giải quyết bằng việc tự thêm SID tĩnh tùy ý.

## 8. Các lưu ý vận hành và bảo mật

### 8.1. Kiểm tra đúng phía client và server

- **Client:** `tnsnames.ora` và các tham số `sqlnet.ora` client được đọc trong môi trường tiến trình kết nối.
- **Server:** listener được khởi chạy từ Oracle Home/Grid Home và môi trường của riêng nó; `listener.ora` tại đây quyết định endpoint lắng nghe.
- **Database:** tham số `LOCAL_LISTENER` cùng dịch vụ đang chạy giúp instance đăng ký với listener. Sửa `listener.ora` không tự sửa tham số database.

Tại một server có nhiều Oracle Home, có thể tồn tại nhiều file `tnsnames.ora`, `sqlnet.ora`, `listener.ora` cùng tên. Xem đường dẫn thực tế trong `lsnrctl status` và công cụ phía client để tránh chỉnh nhầm.

### 8.2. Nguyên tắc bảo mật cơ bản

- Không đưa mật khẩu vào `tnsnames.ora`, `sqlnet.ora`, `listener.ora` hoặc lưu trong command history.
- Giới hạn quyền đọc/ghi các file cấu hình theo tài khoản thích hợp; chỉ DBA hoặc chủ hệ thống có quyền chỉnh listener đang phục vụ người dùng.
- Cân nhắc phân đoạn mạng, firewall, TLS/TCPS, wallet và chính sách mã hóa theo chuẩn môi trường. Ví dụ TCP thuần của bài chỉ mô tả cách định tuyến kết nối.
- Không mở listener ra mọi giao diện hoặc đưa cổng database lên Internet công cộng nếu không có thiết kế bảo mật và kiểm soát truy cập.
- Đừng tự giảm mức xác thực/mã hóa chỉ vì một bản demo gặp lỗi kết nối. Lỗi bảo mật cần được chẩn đoán đúng nguyên nhân.

### 8.3. Khác biệt ở Oracle RAC, Data Guard và môi trường quản lý tập trung

Trong môi trường nhiều instance, listener và dịch vụ có thể được quản lý bởi Grid Infrastructure, SCAN listener, `REMOTE_LISTENER`, Oracle Clusterware hoặc các công cụ tự động. Không áp dụng máy móc một file `listener.ora` và một `LOCAL_LISTENER` trong bài lab cho hệ thống nhiều node. Mục tiêu của bài là hiểu **vai trò các tệp và luồng kết nối cơ bản**; triển khai HA và quản trị cluster cần thiết kế riêng.

## 9. Bài tập củng cố

1. Máy client đặt `LAB_PDB` trong `tnsnames.ora` và service đích là `FREEPDB1`. Hai tên này có buộc phải giống nhau không? Vì sao?
2. Một client dùng `sqlplus user@//db-host.example.com:1521/FREEPDB1` thành công, nhưng `sqlplus user@LAB_PDB` báo `ORA-12154`. Bạn sẽ kiểm tra file nào và biến môi trường nào trước?
3. Đổi `TNS_ADMIN` trong terminal có tự thay đường dẫn `listener.ora` mà listener đang chạy sử dụng hay không?
4. Listener ở cổng `1521` đang hoạt động nhưng `lsnrctl services` không liệt kê `FREEPDB1`. Vì sao không nên vội thêm một `SID_LIST` tĩnh?
5. Vì sao `tnsping LAB_PDB` trả `OK` vẫn chưa đủ kết luận tài khoản `LAB_USER` vào được đúng PDB?
6. Khi đổi listener từ `1521` sang `1522` trên một instance lab, những thành phần nào cần được đối chiếu lại?

**Gợi ý trả lời:**

1. Không. `LAB_PDB` là alias phía client, `FREEPDB1` là tên service do database công bố.
2. `tnsnames.ora`, `sqlnet.ora` và `TNS_ADMIN` của tiến trình client, bao gồm đúng đường dẫn file.
3. Không. Tiến trình listener đã chạy có môi trường và đường dẫn cấu hình riêng; cần xác định file thật mà listener dùng và áp dụng thay đổi đúng cách.
4. Vì service có thể chưa được LREG đăng ký, database/PDB chưa sẵn sàng hoặc tên service/port đang sai; đăng ký động là cơ chế thông thường.
5. `tnsping` không xác thực user, không chạy truy vấn vào PDB; phải kết nối SQL*Plus và kiểm tra container.
6. Endpoint trong `listener.ora`, địa chỉ database đăng ký (`LOCAL_LISTENER` trong môi trường liên quan), cấu hình host/port trên client, firewall và trạng thái listener/service.

## Tài liệu Oracle tham khảo

- [Oracle Database Net Services Administrator's Guide — Managing Network Address Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/managing-network-address-information.html): vai trò của các tệp cấu hình Oracle Net.
- [Oracle Net Services Reference — Local Naming Parameters in `tnsnames.ora`](https://docs.oracle.com/en/database/oracle/oracle-database/19/netrf/local-naming-parameters-in-tns-ora-file.html): cú pháp alias, descriptor và tìm kiếm file.
- [Oracle Net Services Reference — Parameters for the `sqlnet.ora` File](https://docs.oracle.com/en/database/oracle/oracle-database/19/netrf/parameters-for-the-sqlnet.ora.html): thông số naming, networking và bảo mật.
- [Oracle Database 26ai — Overview of Oracle Net Listener](https://docs.oracle.com/en/database/oracle/oracle-database/26/netag/overview-oracle-net-listener.html): listener mặc định và service registration động.
- [Oracle Database 26ai — Configuring Dynamic Service Registration](https://docs.oracle.com/en/database/oracle/oracle-database/26/netag/configuring-dynamic-service-registration.html): quan hệ giữa listener và dịch vụ đăng ký động.
- [Oracle Database Error Messages — ORA-12514](https://docs.oracle.com/en/error-help/db/ora-12514/): chẩn đoán listener chưa biết service.
