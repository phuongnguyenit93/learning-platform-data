# Cấu hình `ORACLE_SID`, `PATH` và `TNS_ADMIN` trong môi trường thực hành Oracle

Khi thực hành Oracle Database, cùng một máy có thể chứa nhiều Oracle Home, nhiều database instance hoặc nhiều công cụ client. Ba biến môi trường `ORACLE_SID`, `PATH` và `TNS_ADMIN` giúp chỉ rõ **instance cục bộ cần làm việc**, **chương trình Oracle sẽ được chạy** và **thư mục chứa cấu hình kết nối mạng Oracle Net**. Thiết lập đúng các biến này giúp SQL*Plus hoạt động nhất quán, nhưng từng biến có vai trò riêng và không thay thế cho nhau.

Sau bài này, bạn có thể:

- Phân biệt **SID**, **service name**, **Oracle Home** và **TNS alias**, đặc biệt trong kiến trúc CDB/PDB.
- Thiết lập và kiểm tra ba biến trên Linux, Windows Command Prompt và PowerShell.
- Tạo `tnsnames.ora`, kết nối qua alias hoặc Easy Connect và xác định lỗi đang nằm ở đường dẫn chương trình, phân giải tên, listener hay database.
- Chọn cấu hình phù hợp khi dùng **Oracle Database Server** trên máy thực hành hoặc **Oracle Instant Client** trên máy chỉ đóng vai trò client.

> **Ngữ cảnh ví dụ:** Một máy thực hành chạy Oracle AI Database Free với instance `FREE`, PDB `FREEPDB1`, listener TCP cổng `1521`. Đây là tên mặc định của bản Free hiện hành; nếu dùng Oracle XE, Oracle 19c hoặc cơ sở dữ liệu được tạo riêng, hãy dùng **SID, service name và đường dẫn thực tế của hệ thống**. Các đường dẫn trong bài chỉ mang tính minh họa.

## 1. Hiểu đúng ba biến môi trường

| Biến | Dùng để làm gì? | Ảnh hưởng trực tiếp đến | Không dùng để |
| --- | --- | --- | --- |
| `ORACLE_SID` | Chọn tên **database instance trên máy cục bộ** | Kết nối local kiểu `sqlplus / as sysdba` khi có Oracle Database Server và quyền OSDBA | Chọn PDB hoặc định tuyến kết nối TCP đến máy từ xa |
| `PATH` | Liệt kê thư mục mà hệ điều hành tìm file thực thi | Lệnh `sqlplus`, `lsnrctl`, `tnsping` (nếu được cài) và trên Windows cả quá trình tìm DLL | Chọn database hoặc định nghĩa alias kết nối |
| `TNS_ADMIN` | Chỉ **thư mục** Oracle Net tìm các file cấu hình như `tnsnames.ora`, `sqlnet.ora` | Kết nối bằng alias `user@TEN_ALIAS` và các cấu hình Oracle Net khác | Trỏ trực tiếp đến file `tnsnames.ora` hay tự khởi động listener |

Biến liên quan thường gặp là `ORACLE_HOME`: thư mục cài **Oracle Database Home đầy đủ** (chứa `bin/sqlplus`, thư viện, công cụ quản trị...). Trên máy cài Database Server, `ORACLE_HOME` và `ORACLE_SID` cần tương ứng với cùng môi trường. Với **Instant Client**, thông thường **không cần đặt `ORACLE_HOME`** và client mạng **không cần `ORACLE_SID`**.

### 1.1. SID không phải service name

Oracle dùng nhiều tên cho những phạm vi khác nhau:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Instance SID | `FREE` | Tên instance Oracle chạy trên máy chủ; local connection sử dụng tên này |
| CDB | `FREE` | Container database chứa root và các PDB |
| PDB | `FREEPDB1` | Pluggable database nơi thường đặt schema và bảng của bài thực hành |
| Service name | `FREEPDB1` | Dịch vụ listener công bố để client kết nối đến PDB |
| Net service name / TNS alias | `FREE_LAB` | Bí danh do **client** định nghĩa trong `tnsnames.ora` |

Ví dụ, khi thực hành trên máy chủ:

~~~bash
export ORACLE_SID=FREE
sqlplus / as sysdba
~~~

Lệnh trên dựa vào instance **local** và xác thực hệ điều hành. Sau khi đăng nhập, phiên quản trị thường bắt đầu ở `CDB$ROOT`. Đặt `ORACLE_SID=FREEPDB1` để «chọn PDB» là sai: `FREEPDB1` là tên PDB/service trong ví dụ, không phải SID của một instance riêng.

Ngược lại:

~~~bash
sqlplus lab_user@//127.0.0.1:1521/FREEPDB1
~~~

đi qua **Oracle Net listener** để tìm service `FREEPDB1`; nó không chọn mục tiêu thông qua `ORACLE_SID` của shell. SQL*Plus sẽ hỏi mật khẩu của `lab_user`. Hãy thay `127.0.0.1` bằng tên/IP máy chủ nếu chạy client từ máy khác.

### 1.2. Hai luồng kết nối cần hình dung

~~~text
KẾT NỐI LOCAL (máy có Database Server)
Shell → PATH tìm sqlplus → ORACLE_HOME + ORACLE_SID
      → Oracle instance local (cần quyền xác thực phù hợp)

KẾT NỐI QUA MẠNG (máy chủ hoặc máy client)
Shell → PATH tìm sqlplus → chuỗi kết nối
      → TNS_ADMIN/tnsnames.ora (nếu dùng alias)
      → host:port → listener → SERVICE_NAME → CDB/PDB
~~~

**Listener không cần thiết cho kết nối OS authentication local** (`sqlplus / as sysdba`), nhưng cần cho kết nối TCP như `user@//host:1521/service`. Việc đặt biến môi trường không đồng nghĩa database hoặc listener đã chạy.

## 2. Chuẩn bị trước khi cấu hình

Xác định môi trường đang thực hành:

1. **Máy database server:** Có Oracle Database Home và instance chạy tại chỗ. Cần biết SID thực tế, Oracle Home thực tế và tài khoản hệ điều hành được phép quản trị (trên Linux thường là `oracle`).
2. **Máy client:** Có SQL*Plus/Instant Client nhưng database chạy trên máy khác. Cần biết `host`, `port`, `service name` và tài khoản database. Không cần đoán hoặc tự đặt SID của máy chủ.
3. **Môi trường container/VM:** Phân biệt shell ở host với shell **bên trong** container/VM. Biến môi trường được đặt ở host không tự xuất hiện trong tiến trình ở môi trường khác.

Nếu chưa biết các giá trị, đối chiếu cấu hình cài đặt hoặc hỏi người quản trị. **Không sao chép nguyên đường dẫn ví dụ** vì Oracle Home thay đổi theo phiên bản, hệ điều hành và cách cài.

## 3. Cấu hình trên Linux

Các lệnh dưới đây dành cho shell `bash` hoặc tương đương. `export` đặt biến cho shell hiện tại và các tiến trình con được khởi chạy từ shell đó.

### 3.1. Máy có Oracle Database Server

Đăng nhập đúng tài khoản hệ điều hành quản trị database (tên tài khoản có thể khác `oracle`):

~~~bash
sudo -iu oracle
~~~

Thiết lập phiên thực hành, **thay `ORACLE_HOME` theo nơi Oracle thực sự được cài**:

~~~bash
export ORACLE_SID=FREE
export ORACLE_HOME=/opt/oracle/product/26ai/dbhomeFree
export PATH="$ORACLE_HOME/bin:$PATH"

# Chỉ đặt TNS_ADMIN khi muốn chỉ định thư mục cấu hình Oracle Net riêng.
export TNS_ADMIN="$HOME/oracle-net"
mkdir -p "$TNS_ADMIN"
~~~

Ở đây:

- `ORACLE_SID=FREE` chọn instance cục bộ dùng cho local connection.
- `ORACLE_HOME/bin` nằm **trước** các mục còn lại trong `PATH` để shell ưu tiên công cụ của Oracle Home này; đặc biệt quan trọng nếu máy có nhiều bản Oracle.
- `TNS_ADMIN` là một **thư mục**. Sau này đặt file `$TNS_ADMIN/tnsnames.ora` vào đó. Chỉ tạo thư mục chưa tạo ra alias kết nối.

Kiểm tra trạng thái shell:

~~~bash
printf 'SID=%s\nHOME=%s\nTNS_ADMIN=%s\n' \
  "$ORACLE_SID" "$ORACLE_HOME" "$TNS_ADMIN"
command -v sqlplus
sqlplus -v
~~~

Kết quả `command -v sqlplus` phải trỏ đến executable dự định dùng, chẳng hạn `/opt/oracle/product/26ai/dbhomeFree/bin/sqlplus`. Lệnh `sqlplus -v` chỉ xác nhận client có thể chạy; nó **chưa xác nhận database đang hoạt động**.

Nếu tài khoản hệ điều hành thuộc nhóm được cấp quyền SYSDBA, thử kết nối local:

~~~bash
sqlplus / as sysdba
~~~

Tại dấu nhắc `SQL>`:

~~~sql
SELECT instance_name, host_name, status
FROM v$instance;

SHOW CON_NAME;
EXIT;
~~~

Tên instance kỳ vọng theo ví dụ là `FREE`. `SHOW CON_NAME` cho biết container của phiên hiện tại, thường là `CDB$ROOT` đối với local SYSDBA ban đầu.

> Chỉ dùng `SYSDBA` cho tác vụ quản trị. Khi tạo bảng, chạy truy vấn và luyện SQL, nên kết nối bằng tài khoản ứng dụng tại PDB; không dùng `SYS` như tài khoản bài tập.

### 3.2. Dùng `oraenv` để chuyển giữa các Oracle Home

Với bản cài đặt có script `oraenv` và bảng cấu hình `oratab` hợp lệ, dùng script này giúp cập nhật `ORACLE_HOME`, `ORACLE_SID` và `PATH` đồng bộ:

~~~bash
export ORACLE_SID=FREE
export ORAENV_ASK=NO
. /usr/local/bin/oraenv
unset ORAENV_ASK

command -v sqlplus
printf '%s\n' "$ORACLE_HOME"
~~~

Dấu chấm và dấu cách trong `. /usr/local/bin/oraenv` có ý nghĩa **source script vào shell hiện tại**. Đường dẫn đến `oraenv` có thể khác giữa các máy; không chạy lệnh nếu file đó không tồn tại. `oraenv` tra cấu hình cài đặt như `/etc/oratab` và không tự biết thư mục `TNS_ADMIN` tùy chỉnh của bạn. Nếu cần alias riêng, đặt `TNS_ADMIN` thêm sau khi chạy `oraenv`.

### 3.3. Máy chỉ cài Oracle Instant Client

Instant Client không quản lý instance local; sử dụng `PATH` để tìm `sqlplus`, `TNS_ADMIN` để tìm alias và chuỗi kết nối để chọn service. Ví dụ, khi gói Instant Client SQL*Plus đã được cài:

~~~bash
# Thay bằng thư mục Instant Client thực tế.
export IC_DIR=/opt/oracle/instantclient_23_8
export PATH="$IC_DIR:$PATH"
export TNS_ADMIN="$HOME/oracle-net"

command -v sqlplus
sqlplus -v
~~~

Nếu thư viện Instant Client chưa được đăng ký với bộ nạp thư viện của Linux, có thể cần cấu hình `ldconfig` của hệ thống hoặc `LD_LIBRARY_PATH` theo hướng dẫn cài đặt tương ứng. Chỉ thêm `PATH` sẽ không chữa được lỗi thiếu shared library. **Không trỏ `ORACLE_HOME` vào thư mục Instant Client như thể đó là một Database Home đầy đủ**; việc này không cần cho kết nối Oracle Net thông thường và có thể gây nhầm lẫn.

### 3.4. Thiết lập lâu dài trên Linux

Với một máy thực hành dùng cố định một Oracle Home, có thể đặt các dòng `export` phù hợp trong `~/.bashrc` cho các shell Bash tương tác; sau đó mở terminal mới hoặc chạy:

~~~bash
source ~/.bashrc
~~~

Đối với login shell, cần kiểm tra `~/.bash_profile` hoặc `~/.profile` có nạp `~/.bashrc` hay không. Nếu thường xuyên chuyển nhiều SID/Home, ưu tiên chạy `oraenv` theo từng phiên thay vì cố định một bộ giá trị cho mọi phiên.

Biến đặt trong shell **không tự áp dụng cho systemd service, chương trình IDE đã mở từ trước, process của user khác hoặc container khác**. Cần cấu hình trong môi trường khởi chạy của chính tiến trình đó.

## 4. Cấu hình trên Windows

Windows có hai shell phổ biến với cú pháp khác nhau. Những lệnh dưới đây chỉ ảnh hưởng **cửa sổ terminal hiện tại và tiến trình con của nó**. Đường dẫn Oracle Home là ví dụ, phải thay theo máy cài đặt.

### 4.1. Command Prompt (`cmd.exe`)

~~~bat
set "ORACLE_SID=FREE"
set "ORACLE_HOME=C:\app\oracle\product\26ai\dbhomeFree"
set "PATH=%ORACLE_HOME%\bin;%PATH%"
set "TNS_ADMIN=C:\oracle\net-admin"

echo %ORACLE_SID%
echo %TNS_ADMIN%
where sqlplus
sqlplus -v
~~~

Tạo thư mục cấu hình (nếu chưa tồn tại):

~~~bat
if not exist "C:\oracle\net-admin" mkdir "C:\oracle\net-admin"
~~~

Cú pháp `set "NAME=value"` giúp tránh vô tình thêm khoảng trắng vào giá trị. Windows phân cách các thư mục trong `PATH` bằng dấu chấm phẩy `;`, trong khi Linux sử dụng dấu hai chấm `:`.

### 4.2. PowerShell

~~~powershell
$env:ORACLE_SID = 'FREE'
$env:ORACLE_HOME = 'C:\app\oracle\product\26ai\dbhomeFree'
$env:Path = "$($env:ORACLE_HOME)\bin;$env:Path"
$env:TNS_ADMIN = 'C:\oracle\net-admin'

New-Item -ItemType Directory -Force -Path $env:TNS_ADMIN
$env:ORACLE_SID
$env:TNS_ADMIN
where.exe sqlplus
sqlplus -v
~~~

Nếu chỉ cài **Instant Client trên Windows**, hãy đưa thư mục chứa `sqlplus.exe` và các DLL của Instant Client vào `Path`; bỏ các bước `ORACLE_HOME`, `ORACLE_SID` vì kết nối đến database được chỉ định trong chuỗi Oracle Net. Không dùng nhầm dấu `:` phân cách PATH của Linux trên Windows.

### 4.3. Lưu biến môi trường sau khi đóng terminal

Mở **System Properties → Advanced → Environment Variables** của Windows, cấu hình biến ở phạm vi User hoặc System phù hợp:

- `ORACLE_SID`: chỉ cần khi làm việc với instance local và ứng dụng thực sự cần SID.
- `Path`: thêm thư mục `bin` của Oracle Home **hoặc** thư mục Instant Client đang sử dụng; xem thứ tự khi có nhiều bộ client.
- `TNS_ADMIN`: nhập **đường dẫn thư mục**, không nhập `...\tnsnames.ora`.

Sau khi lưu, **mở terminal/ứng dụng mới** để nhận giá trị mới. Nếu hệ thống có nhiều Oracle Home, kiểm tra `where.exe sqlplus` vì bản đứng trước trong `Path` có thể không phải bản bạn định dùng. Tránh thao tác `setx PATH ...` tùy tiện do nguy cơ làm biến PATH dài hoặc mất/thay đổi các mục có sẵn. Trên máy Windows có Database Server, Oracle cũng có thể lưu thông tin Home trong Registry; xác nhận đường dẫn thực tế của chương trình đang chạy thay vì suy đoán từ một biến duy nhất.

## 5. Cấu hình `TNS_ADMIN` và `tnsnames.ora`

### 5.1. Thư mục mà Oracle Net tìm cấu hình

Ví dụ:

~~~text
Linux:   TNS_ADMIN=/home/oracle/oracle-net
         /home/oracle/oracle-net/tnsnames.ora

Windows: TNS_ADMIN=C:\oracle\net-admin
         C:\oracle\net-admin\tnsnames.ora
~~~

`TNS_ADMIN` phải trỏ tới **thư mục cha** chứa file. Khi không đặt biến này, Oracle Net sẽ tìm trong các vị trí mặc định tùy loại cài đặt và nền tảng, chẳng hạn `ORACLE_HOME/network/admin` hoặc vị trí Oracle Base Home đối với read-only Oracle Home; Instant Client cũng có vị trí mặc định riêng. Dùng `TNS_ADMIN` giúp chủ động chỉ đúng bộ cấu hình cần thực hành.

Ngoài `tnsnames.ora`, thư mục này có thể chứa `sqlnet.ora` và các file Oracle Net khác. Việc dùng `TNS_ADMIN` để chạy client không đồng nghĩa listener đang chạy bằng cấu hình mới đó; listener là tiến trình trên **máy chủ** với môi trường khởi chạy riêng.

### 5.2. Tạo alias `FREE_LAB`

Tạo file văn bản thuần tên chính xác `tnsnames.ora` trong thư mục `TNS_ADMIN`:

~~~text
FREE_LAB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 127.0.0.1)(PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = FREEPDB1)
    )
  )
~~~

Giải thích:

| Thành phần | Vai trò |
| --- | --- |
| `FREE_LAB` | Alias tùy chọn do bạn đặt, dùng trong lệnh `sqlplus user@FREE_LAB` |
| `HOST` | Địa chỉ **máy chủ Oracle**; `127.0.0.1` chỉ đúng khi client và listener nằm trong cùng ngữ cảnh mạng/máy |
| `PORT` | Cổng listener, ví dụ `1521`; không nhất thiết luôn là cổng mặc định |
| `SERVICE_NAME` | Service đích mà listener biết; ở ví dụ này `FREEPDB1` dẫn đến PDB thực hành |

**Ví dụ từ máy client khác:** đổi `HOST = 127.0.0.1` thành hostname/IP có thể truy cập của máy Oracle (chẳng hạn `db-server.example.com`). Trong Docker, `localhost` bên trong container chỉ trỏ tới **container đó**, không mặc nhiên trỏ tới container database hoặc host; dùng hostname/service phù hợp với mạng Docker và cổng thực tế.

Nếu file `sqlnet.ora` tùy chỉnh có khai báo `NAMES.DIRECTORY_PATH`, bảo đảm phương thức `TNSNAMES` không bị loại bỏ khi muốn sử dụng alias. Một cấu hình ví dụ là:

~~~text
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
~~~

Không cần tạo `sqlnet.ora` chỉ để sử dụng ví dụ cơ bản nếu phương thức phân giải tên mặc định đã hoạt động.

### 5.3. Kết nối bằng alias hoặc Easy Connect

Sau khi có tài khoản database cho bài tập:

~~~bash
# Dùng alias đã đặt trong tnsnames.ora:
sqlplus lab_user@FREE_LAB

# Kết nối trực tiếp không cần alias:
sqlplus lab_user@//127.0.0.1:1521/FREEPDB1
~~~

Cả hai lệnh sẽ yêu cầu mật khẩu của `lab_user`. Với Easy Connect ở ví dụ này, `TNS_ADMIN` không cần để chỉ định `host:port/service`; tuy nhiên các thiết lập Oracle Net khác có thể vẫn phụ thuộc cấu hình client.

Tại `SQL>`, kiểm tra đã vào đúng container/service:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

`CONTAINER_NAME` kỳ vọng là `FREEPDB1` trong ví dụ. Giá trị `SERVICE_NAME` có thể hiển thị theo tên dịch vụ thực tế mà cơ sở dữ liệu sử dụng. Chỉ thành công ở `sqlplus -v` hoặc `tnsping` chưa đủ khẳng định đăng nhập đã thành công hay vào đúng PDB.

## 6. Quy trình kiểm tra theo từng lớp

Khi có vấn đề, kiểm tra theo thứ tự **biến môi trường → executable → phân giải alias → listener/service → xác thực → PDB**. Cách này thu hẹp nguyên nhân mà không cần thay đổi đồng thời nhiều cấu hình.

| Lớp kiểm tra | Linux | Windows CMD / PowerShell | Điều cần xác nhận |
| --- | --- | --- | --- |
| Giá trị SID | `echo "$ORACLE_SID"` | `echo %ORACLE_SID%` / `$env:ORACLE_SID` | SID là instance local dự định thao tác |
| Giá trị TNS_ADMIN | `echo "$TNS_ADMIN"` | `echo %TNS_ADMIN%` / `$env:TNS_ADMIN` | Đang trỏ tới **đúng thư mục** |
| Đường dẫn SQL*Plus | `command -v sqlplus` | `where.exe sqlplus` | Đúng executable và đúng thứ tự PATH |
| Client có chạy được? | `sqlplus -v` | `sqlplus -v` | Không lỗi thiếu executable/DLL/thư viện |
| TNS alias | `tnsping FREE_LAB` | `tnsping FREE_LAB` | Alias được phân giải và listener có thể phản hồi, nếu có tiện ích `tnsping` |
| Đăng nhập thực tế | `sqlplus lab_user@FREE_LAB` | `sqlplus lab_user@FREE_LAB` | Đăng nhập thành công; truy vấn xác định container |

`tnsping` **không xác thực tài khoản** và **không chứng minh rằng service/PDB đã sẵn sàng cho SQL**. Một số bộ cài Instant Client không kèm `tnsping`; trong trường hợp đó, dùng `sqlplus` để kiểm tra kết nối thực tế.

Trên **máy chủ database**, người có quyền quản trị có thể xem listener và service đã đăng ký:

~~~bash
lsnrctl status
~~~

Tìm cổng đang nghe và phần `Services Summary`. Nếu `FREEPDB1` không xuất hiện hoặc PDB chưa mở, việc sửa `TNS_ADMIN` phía client sẽ không tự khắc phục tình trạng server.

## 7. Lỗi thường gặp và hướng khoanh vùng

| Dấu hiệu | Nhóm nguyên nhân thường gặp | Kiểm tra/hướng xử lý |
| --- | --- | --- |
| `sqlplus: command not found` hoặc `'sqlplus' is not recognized` | `PATH` sai hoặc SQL*Plus chưa được cài | Xác định thư mục có `sqlplus`/`sqlplus.exe`, cập nhật PATH và mở shell mới |
| Chạy nhầm SQL*Plus của bản Oracle khác | Nhiều Oracle Home/Instant Client trong PATH | Xem `command -v sqlplus` / `where.exe sqlplus`; kiểm tra đường dẫn nào được ưu tiên |
| Lỗi thiếu thư viện `libclntsh.so` / DLL | Bộ nạp thư viện không tìm được client library | Kiểm tra thư mục cài, phụ thuộc thư viện và cấu hình loader/Path theo hệ điều hành |
| `ORA-12154` hoặc `TNS-03505` | Không phân giải được net service name | Kiểm tra `TNS_ADMIN` trỏ thư mục, tên `tnsnames.ora`, alias, dấu ngoặc và `sqlnet.ora` |
| `ORA-12541` | Không kết nối được tới listener ở host/port đã chọn | Kiểm tra hostname, cổng, listener, firewall và ánh xạ cổng container |
| `ORA-12514` | Listener không biết service yêu cầu | Xem `SERVICE_NAME`, danh sách service trong `lsnrctl status`, trạng thái instance/PDB |
| `ORA-12505` | Descriptor yêu cầu SID mà listener không biết | Kiểm tra `SID` trong descriptor; ưu tiên `SERVICE_NAME` phù hợp với PDB |
| `ORA-01034` / `ORA-27101` khi kết nối local | SID/HOME không khớp hoặc instance chưa sẵn sàng | Kiểm tra `ORACLE_SID`, `ORACLE_HOME`, quyền và trạng thái instance thực tế |
| `ORA-01031` khi `/ as sysdba` | Tài khoản OS không có quyền quản trị cần thiết | Kiểm tra tài khoản và nhóm OSDBA; không cấp quyền SYSDBA tùy tiện để chữa lỗi |
| `ORA-01017` | Sai thông tin xác thực, hoặc tài khoản/chính sách không phù hợp | Kiểm tra username/password, service/PDB và trạng thái tài khoản với quản trị viên |
| Terminal chạy được nhưng IDE/service không kết nối | Tiến trình không nhận biến của terminal vừa sửa | Xác định môi trường khởi chạy của IDE/service, cập nhật đúng cấu hình rồi khởi động lại tiến trình |

**Tránh sửa ngẫu nhiên cả ba biến cùng lúc.** Ví dụ, nếu `sqlplus -v` chạy được nhưng `sqlplus user@FREE_LAB` báo `ORA-12154`, đầu tiên hãy kiểm tra `TNS_ADMIN` và file `tnsnames.ora`; thay `ORACLE_SID` thường không liên quan đến lỗi phân giải alias mạng.

## 8. Bài thực hành hoàn chỉnh

Giả sử Oracle Free đang chạy trên máy Linux và đã có schema `LAB_USER` trong PDB `FREEPDB1`. Thực hiện lần lượt:

**Bước 1 — Chọn đúng instance và chương trình Oracle (trên database host):**

~~~bash
export ORACLE_SID=FREE
export ORACLE_HOME=/opt/oracle/product/26ai/dbhomeFree
export PATH="$ORACLE_HOME/bin:$PATH"

command -v sqlplus
sqlplus -v
~~~

**Bước 2 — Chỉ định thư mục Oracle Net và tạo file alias:**

~~~bash
export TNS_ADMIN="$HOME/oracle-net"
mkdir -p "$TNS_ADMIN"
cat > "$TNS_ADMIN/tnsnames.ora" <<'EOF'
FREE_LAB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 127.0.0.1)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = FREEPDB1))
  )
EOF
~~~

Lưu ý: lệnh ghi file ở bước này dành cho **thư mục thực hành do bạn sở hữu**. Nếu trên máy đã có `tnsnames.ora` chứa nhiều alias đang sử dụng, **chỉnh sửa thêm alias vào file hiện có**, không dùng cách ghi đè nguyên file. Thay địa chỉ `HOST` nếu listener không nằm cùng máy/ngữ cảnh mạng.

**Bước 3 — Kiểm tra từ kết nối mạng đến SQL:**

~~~bash
tnsping FREE_LAB
sqlplus lab_user@FREE_LAB
~~~

SQL*Plus hỏi mật khẩu. Sau khi vào `SQL>`:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name
FROM dual;

SELECT USER FROM dual;

EXIT;
~~~

Kỳ vọng `CON_NAME = FREEPDB1` và `USER = LAB_USER`. Nếu không có `tnsping` nhưng `sqlplus` đã cài, vẫn có thể thử kết nối bằng `sqlplus`.

**Bước 4 — Đối chiếu bằng Easy Connect (không dùng alias):**

~~~bash
sqlplus lab_user@//127.0.0.1:1521/FREEPDB1
~~~

Nếu **Easy Connect thành công nhưng `FREE_LAB` thất bại**, ưu tiên kiểm tra `TNS_ADMIN`, đường dẫn `tnsnames.ora` và cú pháp alias. Nếu **cả hai đều thất bại**, kiểm tra host/port, listener, service, tài khoản và trạng thái PDB theo thông báo lỗi.

**Bước 5 — Thử tác động của phạm vi biến:**

Mở một terminal mới, kiểm tra lại `echo "$ORACLE_SID"` và `echo "$TNS_ADMIN"`. Nếu giá trị không có, đó là hành vi bình thường của biến chỉ đặt trong phiên trước; hãy thiết lập lại hoặc đưa cấu hình cần thiết vào file khởi tạo shell. Không cần sửa database để giải quyết việc biến môi trường không được kế thừa.

## 9. Những lưu ý để môi trường thực hành ổn định

- **Giữ bí mật thông tin đăng nhập.** Chỉ đưa host, port và service name vào `tnsnames.ora`; không đặt mật khẩu dạng rõ trong file hay trong lệnh có thể lưu lịch sử shell.
- **Chọn đúng lớp cấu hình.** `ORACLE_SID` là thuộc tính kết nối local với instance; khi client đi qua TCP, thông tin quyết định database đích nằm ở chuỗi kết nối và service mà listener công bố.
- **Quản lý nhiều phiên bản Oracle cẩn thận.** `PATH` của shell xác định binary sẽ chạy. Khi chuyển Home, dùng `oraenv` hoặc bảo đảm ba thành phần SID, Home và executable khớp nhau.
- **Nhận biết Java/JDBC Thin.** Với URL như `jdbc:oracle:thin:@//db-server:1521/FREEPDB1`, ứng dụng Java thường không cần `ORACLE_SID` hoặc `ORACLE_HOME` vì kết nối dựa trên địa chỉ mạng và service. Nếu dùng TNS alias trong JDBC, cần cấu hình Oracle Net của driver theo phiên bản đang dùng; đừng giả định môi trường terminal sẽ tự truyền vào IDE hoặc Java process.
- **Đọc lỗi theo từng lớp.** PATH sai thì chương trình không khởi chạy; TNS alias sai thì tên không phân giải; listener/service sai thì kết nối mạng thất bại; đăng nhập sai thì lỗi xác thực. Mỗi lớp cần một cách kiểm tra khác nhau.

### Tự kiểm tra kiến thức

1. Vì sao `ORACLE_SID=FREEPDB1` thường không phải cách đúng để kết nối đến PDB `FREEPDB1`?
2. Nếu `where.exe sqlplus` trả về hai đường dẫn, đường dẫn nào được sử dụng khi gõ `sqlplus`, và bạn sẽ thay đổi điều đó như thế nào?
3. Vì sao `TNS_ADMIN=C:\oracle\net-admin\tnsnames.ora` là sai?
4. `tnsping FREE_LAB` thành công có đủ chứng minh `LAB_USER` đăng nhập được vào PDB hay không?
5. Nếu `sqlplus user@//host:1521/FREEPDB1` thành công nhưng `sqlplus user@FREE_LAB` báo `ORA-12154`, nên kiểm tra gì trước?

**Đáp án định hướng:** (1) SID thuộc instance, PDB được chọn qua service/container; (2) executable xuất hiện trước trong PATH được ưu tiên; (3) TNS_ADMIN cần tên thư mục; (4) không, phải đăng nhập và truy vấn; (5) thư mục TNS_ADMIN, nội dung tnsnames.ora và alias.

## Tài liệu tham khảo chính thức

- [Oracle SQL*Plus — Configuring SQL*Plus](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqpug/configuring-SQL-Plus.html): vai trò của các biến môi trường.
- [Oracle Net Services — Local Naming Parameters in `tnsnames.ora`](https://docs.oracle.com/en/database/oracle/oracle-database/21/netrf/local-naming-parameters-in-tns-ora-file.html): vị trí file và cú pháp Oracle Net.
- [Oracle AI Database Free — Connecting to Oracle AI Database Free](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/connecting-to-oracle-ai-database-free.html): service `FREE`/`FREEPDB1`, kết nối local, Easy Connect và listener.
- [Oracle Database 19c — Administering Oracle Database on Linux/UNIX](https://docs.oracle.com/en/database/oracle/oracle-database/19/unxar/administering-oracle-database.html): dùng `oraenv` khi làm việc với Oracle Home.
