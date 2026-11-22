# Phân biệt kết nối cục bộ, kết nối mạng và xác thực hệ điều hành trong Oracle Database

Khi sử dụng SQL*Plus, SQLcl, SQL Developer hoặc một ứng dụng Java để kết nối Oracle Database, ta thường gặp ba cách nói: **kết nối cục bộ**, **kết nối qua mạng** và **xác thực bằng tài khoản hệ điều hành**. Ba cách nói này không nằm trên cùng một trục phân loại:

- **Cục bộ hay qua mạng** trả lời câu hỏi: *Client đi đến Oracle Database bằng đường kết nối nào?*
- **Xác thực bằng hệ điều hành hay mật khẩu database** trả lời câu hỏi: *Oracle xác định và cho phép người dùng đăng nhập dựa vào bằng chứng nào?*

Chẳng hạn, cùng một máy chủ cơ sở dữ liệu, lệnh `sqlplus / as sysdba` thường tạo **kết nối cục bộ theo giao thức bequeath** và dùng **xác thực hệ điều hành**. Trong khi đó, `sqlplus app_user@//localhost:1521/salespdb` lại tạo **kết nối Oracle Net qua TCP/IP**, dù máy khách và máy chủ có thể cùng một máy vật lý, và thường dùng **mật khẩu tài khoản database**.

Bài học dưới đây giải thích cơ chế kết nối, cú pháp thường gặp, các quyền liên quan và cách nhận biết nguyên nhân lỗi trong Oracle Database, đặc biệt khi thực hành với SQL*Plus/SQLcl và môi trường CDB/PDB.

## 1. Hai chiều độc lập: đường kết nối và cách xác thực

### 1.1. Phân loại theo đường kết nối

| Kiểu | Client chạy ở đâu? | Đường giao tiếp | Oracle Listener | Thông tin định tuyến thường dùng |
| --- | --- | --- | --- | --- |
| **Cục bộ trực tiếp (local bequeath)** | Trên **database server** | Tiến trình client làm việc với tiến trình Oracle trên chính máy đó qua cơ chế cục bộ | **Không cần** listener cho kết nối bequeath | `ORACLE_SID`, môi trường Oracle Home |
| **Oracle Net trên cùng máy** | Trên database server | Kết nối qua Oracle Net, ví dụ TCP đến `localhost:1521` | **Thường cần** listener | Host, port, service name hoặc alias |
| **Oracle Net từ máy khác** | Trên laptop, máy ứng dụng hoặc máy quản trị khác | Kết nối mạng TCP/IP hoặc giao thức Oracle Net đã cấu hình | **Thường cần** listener hoặc điểm truy cập dịch vụ tương đương | Host/IP, port, service name hoặc alias |

**“Local” không đồng nghĩa “không dùng mạng”.** Một client kết nối đến `localhost` bằng TCP vẫn sử dụng Oracle Net. Ngược lại, kết nối **bequeath** thường không ghi host/port/service trong chuỗi kết nối và không cần listener.

### 1.2. Phân loại theo cơ chế xác thực

| Phương thức xác thực | Căn cứ xác thực | Ví dụ khái niệm | Điều kiện quan trọng |
| --- | --- | --- | --- |
| **Mật khẩu database** | Tên người dùng và mật khẩu được Oracle xác nhận | `sqlplus app_user@//dbhost:1521/salespdb` | Tài khoản có thể đăng nhập và được cấp quyền phù hợp |
| **Xác thực hệ điều hành (OS authentication)** | Danh tính/nhóm của tài khoản hệ điều hành được hệ thống tin cậy cung cấp | `sqlplus / as sysdba` hoặc `sqlplus /` | Phải có nhóm quản trị hoặc user `IDENTIFIED EXTERNALLY` được cấu hình phù hợp |
| **Xác thực mạng/tích hợp** | Cơ chế được cấu hình như Kerberos, xác thực Windows, chứng chỉ, v.v. | Tùy cấu hình Oracle Net và môi trường | Không mặc định hoạt động chỉ vì có mạng hoặc có user OS |

Kết nối **local bequeath** có thể sử dụng **mật khẩu database** hoặc **OS authentication**. Kết nối **Oracle Net** thông thường sử dụng mật khẩu database, nhưng cũng có thể dùng phương thức xác thực tích hợp nếu môi trường đã được cấu hình hỗ trợ. Do đó, không được suy ra phương thức xác thực chỉ từ chữ “cục bộ” hoặc “qua mạng”.

### 1.3. Sơ đồ trực quan

```text
Trục 1 — ĐƯỜNG KẾT NỐI

[SQL*Plus trên database server]
       |
       +-- Không có @connect_identifier
       |      |
       |      +-- local bequeath --> [Oracle instance]
       |               (thường dựa ORACLE_SID)
       |
       +-- @//localhost:1521/salespdb
              |
              +-- Oracle Net/TCP --> [Listener] --> [Database service/PDB]

[SQL*Plus trên máy khác]
       |
       +-- @//dbhost.example.com:1521/salespdb
              |
              +-- Oracle Net/TCP --> [Listener] --> [Database service/PDB]


Trục 2 — XÁC THỰC (áp dụng trên đường kết nối phù hợp)

[Mật khẩu database]  [OS user / nhóm OSDBA]  [Kerberos / cơ chế tích hợp]
```

Lưu ý: môi trường có thể thiết lập **default connect identifier** qua `TWO_TASK` (Unix/Linux) hoặc `LOCAL` (Windows), khiến lệnh SQL*Plus **không viết `@...`** vẫn kết nối qua Oracle Net. Vì thế “không thấy @” là dấu hiệu thường gặp của local bequeath, **không phải bằng chứng tuyệt đối**.

## 2. Kết nối cục bộ trực tiếp: local bequeath

### 2.1. Cơ chế hoạt động

Trên database server, client Oracle có thể kết nối trực tiếp đến một **instance đang chạy trên cùng hệ điều hành**. Trên Unix/Linux, kiểu này thường được gọi là **bequeath connection**; Oracle client khởi tạo hoặc giao tiếp với tiến trình server tương ứng mà không phải đi qua TCP listener thông thường.

Trong môi trường Unix/Linux, việc xác định instance đích thường dựa vào:

- `ORACLE_HOME`: vị trí cài phần mềm Oracle client/server được sử dụng.
- `ORACLE_SID`: **system identifier (SID)** của instance cục bộ cần kết nối.
- `PATH` và các biến môi trường liên quan để gọi đúng bản `sqlplus`.

Ví dụ minh họa trên database server Linux (giả sử Oracle Home và đường dẫn thực thi đã cấu hình đúng):

```bash
# Chọn instance cục bộ cần làm việc.
export ORACLE_SID=ORCL

# Kết nối bằng người dùng database, SQL*Plus sẽ hỏi mật khẩu.
sqlplus app_user

# Kết nối bằng xác thực OS với quyền quản trị SYSDBA.
sqlplus / as sysdba
```

Lệnh `sqlplus app_user` và `sqlplus / as sysdba` có thể dùng **cùng một đường kết nối cục bộ** nhưng **khác cách xác thực**. Không nên kết luận rằng mọi kết nối local đều là đăng nhập không mật khẩu.

**Điều kiện:** các ví dụ trên giả định không đặt `TWO_TASK`/`LOCAL` để chuyển hướng đến một Oracle Net service. Trên Windows, cách chọn instance, Oracle Home và dịch vụ Windows phụ thuộc cấu hình cài đặt.

### 2.2. Kết nối trực tiếp không cần listener

Với local bequeath, listener TCP ở cổng `1521` không nhất thiết phải hoạt động. Điều này hữu ích khi cần bảo trì instance, ví dụ listener bị dừng hoặc service chưa được đăng ký.

Tuy nhiên, **không cần listener không có nghĩa database luôn truy cập được**: instance phải ở trạng thái phù hợp, đường dẫn phần mềm đúng, tài khoản có quyền, và hệ điều hành cho phép thao tác. Với tài khoản quản trị đủ điều kiện, có thể dùng `sqlplus / as sysdba` ngay cả khi instance chưa mở để khởi động hoặc kiểm tra trạng thái, nhưng một user ứng dụng bình thường thì không có đặc quyền đó.

### 2.3. Local bequeath và CDB/PDB

Trong kiến trúc multitenant, `ORACLE_SID` chỉ đến **instance**; nó **không phải tên PDB**. Một kết nối quản trị cục bộ như `sqlplus / as sysdba` vào instance CDB thường bắt đầu ở `CDB$ROOT`. Muốn truy cập một PDB cụ thể, ứng dụng nên đi qua **database service** của PDB.

Ví dụ minh họa sau khi đã kết nối với quyền phù hợp:

```sql
SHOW CON_NAME;

-- Chỉ tài khoản được cấp quyền quản trị thích hợp mới có thể chuyển container.
ALTER SESSION SET CONTAINER = SALESPDB;

SHOW CON_NAME;
```

Không nên dùng `ORACLE_SID=SALESPDB` như một cách thay thế service name của PDB: đó là hai khái niệm khác nhau.

## 3. Kết nối qua mạng: Oracle Net

### 3.1. Host, port, listener và service

Kết nối mạng Oracle thường sử dụng các thành phần:

1. **Client**: SQL*Plus, SQLcl, SQL Developer, ứng dụng Java/JDBC, v.v.
2. **Host/IP**: địa chỉ máy chủ hoặc điểm truy cập dịch vụ database.
3. **Port**: cổng Oracle Listener (thường gặp `1521`, nhưng có thể khác).
4. **Listener**: tiếp nhận yêu cầu kết nối và điều phối tới dịch vụ/tiến trình server tương ứng.
5. **Service name**: tên logic của **database service**; thường dùng để chỉ CDB hoặc một PDB cụ thể.

Ví dụ một kết nối Oracle Net bằng **Easy Connect**:

```bash
sqlplus app_user@//dbhost.example.com:1521/salespdb.example.com
```

SQL*Plus sẽ hỏi mật khẩu của `app_user` khi cần. Chuỗi `//dbhost.example.com:1521/salespdb.example.com` chứa **host**, **port** và **service name**. Port `1521` là giá trị thường thấy, không phải quy tắc bắt buộc.

Một biến thể trên chính máy chủ:

```bash
sqlplus app_user@//localhost:1521/salespdb.example.com
```

Dù chạy cùng database server, đây vẫn là **kết nối Oracle Net/TCP**. Listener và service phải được cấu hình/đăng ký phù hợp.

### 3.2. Service name khác SID

Đây là một trong những nhầm lẫn phổ biến nhất:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **SID** | Tên định danh một **Oracle instance** | `ORCL` |
| **Service name** | Tên logic để client kết nối tới database hoặc workload; có thể hướng đến PDB, nhiều instance hoặc cấu hình dịch vụ | `salespdb.example.com` |
| **TNS alias** | Bí danh phía client, ánh xạ đến thông tin kết nối Oracle Net | `SALES_DB` |

Trong RAC, một service có thể chạy trên nhiều instance. Trong CDB, mỗi PDB có thể có service riêng để client kết nối vào đúng container. Vì vậy, ưu tiên **service name** trong các chuỗi kết nối ứng dụng; tránh dùng SID làm thay thế tùy tiện cho service.

### 3.3. Dùng `tnsnames.ora`

Để không phải nhập đầy đủ host/port/service trong mỗi lệnh, client có thể khai báo alias:

```text
SALES_DB =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbhost.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = salespdb.example.com)
    )
  )
```

Sau đó dùng:

```bash
sqlplus app_user@SALES_DB
```

File `tnsnames.ora` thường được client tìm trong vị trí do `TNS_ADMIN` chỉ định hoặc thư mục cấu hình Oracle Net của Oracle Home, tùy phần mềm đang dùng. **TNS alias chỉ là bí danh cấu hình phía client**, không phải đối tượng tài khoản database và không thay thế xác thực.

Lệnh:

```bash
tnsping SALES_DB
```

có thể giúp kiểm tra cách client phân giải alias và phản hồi từ đầu mối Oracle Net. **`tnsping` thành công không có nghĩa đăng nhập database thành công**: nó không kiểm tra mật khẩu, quyền tài khoản hoặc toàn bộ trạng thái database service.

### 3.4. Tài khoản ứng dụng có cần cài Oracle Database trên laptop không?

Không. Một ứng dụng dùng **JDBC Thin** có thể kết nối qua TCP/IP đến Oracle Database mà không cần Oracle Database server hoặc Oracle Client dạng đầy đủ trên máy ứng dụng. Ví dụ URL JDBC Thin theo service name:

```java
String url = "jdbc:oracle:thin:@//dbhost.example.com:1521/salespdb.example.com";
String user = "app_user";

// Ví dụ minh họa: lấy mật khẩu từ cơ chế quản lý secret phù hợp.
String password = System.getenv("DB_PASSWORD");

try (java.sql.Connection connection =
         java.sql.DriverManager.getConnection(url, user, password)) {
    System.out.println("Connected: " + !connection.isClosed());
}
```

Ví dụ giả định driver JDBC Oracle đã có trong dependencies và biến `DB_PASSWORD` đã được cấp từ một cơ chế phù hợp. JDBC Thin ở đây dùng **đường kết nối mạng**; không tự kế thừa quyền `/ as sysdba` từ máy chủ chỉ vì ứng dụng chạy trên cùng host.

## 4. Xác thực hệ điều hành (OS authentication)

### 4.1. Khái niệm

Với OS authentication, Oracle tin cậy thông tin danh tính đã được hệ điều hành hoặc cơ chế xác thực tích hợp xác minh, theo chính sách đã cấu hình. Người dùng có thể kết nối bằng cú pháp `/` mà **không gõ mật khẩu database** trong một số trường hợp.

Có **hai tình huống khác nhau** cần hiểu:

1. **Đăng nhập quản trị bằng nhóm OSDBA/OSOPER**: chẳng hạn `sqlplus / as sysdba`. Quyền SYSDBA/SYSOPER đến từ tư cách thành viên nhóm hệ điều hành được Oracle cấu hình và được đánh giá khi kết nối.
2. **Đăng nhập người dùng thông thường được xác thực ngoài database**: chẳng hạn `sqlplus /` đối với user `IDENTIFIED EXTERNALLY` được ánh xạ phù hợp và có quyền `CREATE SESSION`.

Hai tình huống không tương đương: thành viên nhóm OSDBA được cấp quyền quản trị rất mạnh; một tài khoản `IDENTIFIED EXTERNALLY` thông thường chỉ có các quyền database được cấp cho nó.

### 4.2. `sqlplus / as sysdba`: OS authentication cho quản trị

Trên máy database Linux/Unix, người dùng hệ điều hành thuộc nhóm **OSDBA** đã cấu hình (thường là `dba`, nhưng tên thực tế có thể khác) có thể chạy:

```bash
sqlplus / as sysdba
```

Ý nghĩa:

- Dấu `/`: không cung cấp username/password database theo kiểu thông thường; yêu cầu xác thực bên ngoài.
- `AS SYSDBA`: yêu cầu kết nối với **đặc quyền quản trị SYSDBA**.
- Danh tính/nhóm OS của tiến trình client được Oracle kiểm tra theo cấu hình; nếu đủ quyền, phiên quản trị được thiết lập.
- Với kết nối quản trị bằng `SYSDBA`, `SHOW USER` thường hiển thị `SYS`, **không nhất thiết là tên login hệ điều hành**.

Ví dụ trên SQL*Plus:

```sql
SHOW USER;

SELECT sys_context('USERENV', 'SESSION_USER') AS session_user
FROM   dual;
```

Trên Windows, việc xác thực quản trị bằng hệ điều hành thường liên quan các nhóm như `ORA_DBA` hoặc nhóm OSDBA riêng cho Oracle Home và cơ chế xác thực Windows được cấu hình. Không mặc định rằng tên nhóm Linux và Windows giống nhau.

**Quyền SYSDBA không phải role DBA thông thường.** Một user được cấp role `DBA` trong database không vì thế tự được phép chạy `sqlplus / as sysdba`; ngược lại, một OS user ở nhóm OSDBA có thể có quyền SYSDBA dù không biết mật khẩu database của `SYS`.

### 4.3. `sqlplus /`: OS authentication cho user thông thường

Lệnh sau **không** có `AS SYSDBA`:

```bash
sqlplus /
```

Trong một môi trường được cấu hình xác thực OS cho user thông thường, Oracle ánh xạ login OS sang một **database user được định nghĩa `IDENTIFIED EXTERNALLY`**.

Ví dụ *mang tính nguyên tắc* trên hệ thống có `OS_AUTHENT_PREFIX='OPS$'` và OS login là `labuser`:

```sql
-- Thực hiện bằng tài khoản quản trị, trong database/container phù hợp.
CREATE USER "OPS$LABUSER" IDENTIFIED EXTERNALLY;
GRANT CREATE SESSION TO "OPS$LABUSER";
```

Sau đó trên máy chủ, dưới đúng OS login và cấu hình hỗ trợ:

```bash
sqlplus /
```

Oracle có thể nhận ra user database `OPS$LABUSER` theo quy tắc ánh xạ đã cấu hình. Ví dụ này **không áp dụng nguyên xi** cho mọi hệ điều hành hoặc mọi CDB/PDB: prefix, cách ghi tên user, container hiện tại và cơ chế OS authentication đều có thể thay đổi kết quả. Đặc biệt, kết nối local bequeath vào CDB thường gắn với root, nên không thể mặc định dùng một user local của PDB bằng lệnh `sqlplus /`.

Điểm chính: đăng nhập bằng `/` **không cấp quyền tự động**. User cần tồn tại đúng chỗ, ánh xạ đúng và có quyền đăng nhập cùng các quyền thao tác nghiệp vụ cần thiết.

### 4.4. Có thể xác thực OS từ xa không?

Cần phân biệt:

- **OS authentication cục bộ kiểu bequeath** tin cậy danh tính của tiến trình chạy ngay trên database server và nhóm hệ điều hành cục bộ. Đây là trường hợp phổ biến nhất khi thực hành `/ as sysdba`.
- **Xác thực mạng tích hợp** như Kerberos, cơ chế Windows được Oracle Net hỗ trợ hoặc xác thực bằng chứng chỉ có thể cho phép login không dùng mật khẩu database theo cách khác, khi server/client đã cấu hình tương ứng.
- **Không thể suy rằng một OS user trên laptop sẽ được máy database tự tin cậy** chỉ vì dùng `sqlplus /@SALES_DB`. Lệnh này không có nghĩa hệ thống tự động nhận tài khoản OS từ máy bất kỳ.

Tham số legacy `REMOTE_OS_AUTHENT` từng tồn tại trong Oracle Database nhưng **không nên bật chỉ để đăng nhập từ xa bằng OS**; cơ chế tin cậy danh tính OS qua mạng kiểu cũ có nguy cơ giả mạo và đã bị Oracle khuyến cáo tránh sử dụng. Với yêu cầu đăng nhập tập trung hoặc không dùng mật khẩu database, hãy chọn cơ chế xác thực mạng được hỗ trợ và cấu hình đầy đủ.

### 4.5. SYSDBA từ xa khác SYSDBA cục bộ

Ví dụ quản trị bằng Oracle Net:

```bash
sqlplus 'sys@//dbhost.example.com:1521/orcl.example.com as sysdba'
```

SQL*Plus sẽ yêu cầu mật khẩu phù hợp. Với kết nối quản trị từ xa kiểu mật khẩu, database thường cần **password file** và cấu hình cấp quyền SYSDBA cho tài khoản tương ứng; các giới hạn mạng, dịch vụ và chính sách bảo mật vẫn áp dụng.

Khác biệt:

| | Local `/ as sysdba` | Remote `sys@... as sysdba` |
| --- | --- | --- |
| Đường kết nối phổ biến | Bequeath | Oracle Net |
| Bằng chứng xác thực phổ biến | Nhóm OSDBA trên database server | Mật khẩu quản trị qua password file |
| Có cần Listener TCP không? | Không cho đường bequeath | Thường có |
| Có thể quản trị instance không? | Có, nếu OS user đủ quyền | Có, nếu cấu hình và đặc quyền cho phép |

Không đưa mật khẩu SYS vào câu lệnh có thể bị lưu trong lịch sử shell hoặc danh sách tiến trình. Trong môi trường sản xuất, dùng kênh quản trị được bảo vệ, giới hạn quyền và phương án quản lý thông tin xác thực phù hợp.

## 5. Đọc đúng những câu lệnh thường gặp

Các ví dụ sau giả định client SQL*Plus/SQLcl đã có môi trường phù hợp; database user tồn tại, tài khoản không bị khóa và listener/service đã được cấu hình khi cần.

| Câu lệnh | Đường kết nối mặc định | Xác thực thường dùng | Điều dễ nhầm |
| --- | --- | --- | --- |
| `sqlplus app_user` | Bequeath trên database server, nếu không có default connect identifier | Mật khẩu database | Không có `@` không có nghĩa OS authentication |
| `sqlplus /` | Bequeath trên database server, theo cấu hình | OS external user | Không đồng nghĩa `SYSDBA` |
| `sqlplus / as sysdba` | Bequeath trên database server, theo cấu hình | OSDBA/đặc quyền OS quản trị | Không cần mật khẩu database nhưng cần quyền OS |
| `sqlplus app_user@//localhost:1521/salespdb` | Oracle Net đến loopback | Mật khẩu database | Vẫn đi qua TCP/listener dù cùng host |
| `sqlplus app_user@//dbhost:1521/salespdb` | Oracle Net từ máy client | Mật khẩu database | Service name khác SID |
| `sqlplus app_user@SALES_DB` | Theo alias trong cấu hình Oracle Net | Mật khẩu database | `SALES_DB` là alias phía client |
| `sqlplus 'sys@//dbhost:1521/orcl as sysdba'` | Oracle Net | SYSDBA qua password file trong cấu hình thông thường | Quyền SYSDBA khác role DBA |

Lưu ý: nếu `TWO_TASK`/`LOCAL` được đặt, SQL*Plus có thể chọn Oracle Net ngay khi câu lệnh không chứa `@`; phải kiểm tra cấu hình thực tế khi phân tích một kết nối cụ thể.

### 5.1. Vì sao dấu `/` không phải “tắt bảo mật”?

Trong `sqlplus / as sysdba`, dấu `/` có nghĩa **ủy thác xác thực** cho một cơ chế bên ngoài, phổ biến là OS user/group trên database server. Oracle vẫn kiểm tra danh tính và đặc quyền. Nếu bất kỳ OS login nào cũng có thể chạy câu lệnh thành công, vấn đề nằm ở việc cấp quyền OSDBA hoặc cấu hình bảo mật, không phải cú pháp tự nó bỏ qua xác thực.

### 5.2. Vì sao `localhost` không tương đương local bequeath?

`localhost` chỉ là địa chỉ loopback của **máy đang chạy client**. Trên laptop của bạn, `localhost:1521` chỉ tới laptop, **không phải máy database ở trung tâm dữ liệu**. Trên database server, `localhost:1521` trỏ tới listener của máy đó nhưng vẫn dùng TCP. Local bequeath lại chọn instance tại máy theo môi trường Oracle mà không dùng địa chỉ TCP.

## 6. Thực hành phân biệt qua ba bài thử

### Bài thử A — Trực tiếp trên database server

Giả sử bạn đang dùng shell của OS user thuộc OSDBA, trên máy chủ có SID `ORCL`:

```bash
export ORACLE_SID=ORCL
sqlplus / as sysdba
```

Trong SQL*Plus:

```sql
SHOW USER;
SHOW CON_NAME;

SELECT instance_name, host_name, status
FROM   v$instance;
```

Điểm cần quan sát: client chạy trên database server; không cần cung cấp host/port/service; OS user có quyền SYSDBA nên được đăng nhập và xem instance. `SHOW CON_NAME` giúp phân biệt CDB root với PDB.

### Bài thử B — Từ cùng server nhưng qua Oracle Net

Tại cùng database server:

```bash
sqlplus app_user@//localhost:1521/salespdb.example.com
```

Cú pháp `@//localhost:1521/...` khiến client đi qua Oracle Net/TCP. Để thành công, cần listener nhận kết nối, service tồn tại/được đăng ký và user có quyền truy cập container/database tương ứng. Có thể kiểm tra listener ngay trên database server:

```bash
lsnrctl status
```

Lệnh này phản ánh listener đang được kiểm tra, **không xác thực giúp user app_user** và không khẳng định mọi PDB đã sẵn sàng cho nghiệp vụ.

### Bài thử C — Từ một máy khác

Từ laptop hoặc máy ứng dụng đã có SQL*Plus/SQLcl:

```bash
sqlplus app_user@//dbhost.example.com:1521/salespdb.example.com
```

Ở đây phải có đường mạng từ client tới database endpoint, đúng service name, tài khoản hợp lệ và cấu hình cho phép kết nối. **Không cần** đặt `ORACLE_SID` thành SID của server để dùng Easy Connect. Client không thể dùng local bequeath tới một instance trên máy khác chỉ bằng cách đặt `ORACLE_SID`.

### 6.1. Xem danh tính phiên đã đăng nhập

Sau khi kết nối, chạy câu lệnh read-only:

```sql
SELECT sys_context('USERENV', 'SESSION_USER')           AS database_user,
       sys_context('USERENV', 'AUTHENTICATION_METHOD') AS auth_method,
       sys_context('USERENV', 'HOST')                  AS client_host,
       sys_context('USERENV', 'SERVICE_NAME')          AS service_name,
       sys_context('USERENV', 'CON_NAME')              AS container_name
FROM   dual;
```

Các trường giúp nhận biết database user, cơ chế xác thực được Oracle báo cáo, máy client, service và container. Giá trị thực tế phụ thuộc release/cấu hình; một số trường có thể rỗng hoặc phản ánh thông tin mặc định của phiên, vì vậy **không dùng chỉ một trường để kết luận chắc chắn kết nối là bequeath hay TCP**. Khi cần kiểm tra chuyên sâu, kết hợp cấu hình client, listener log và các dynamic performance view được cấp quyền đọc.

## 7. Chẩn đoán sự cố theo đúng lớp vấn đề

Khi kết nối thất bại, hãy xác định lỗi thuộc **định tuyến/kết nối**, **xác thực**, **quyền** hay **trạng thái database**.

| Dấu hiệu thường gặp | Lớp vấn đề cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `ORA-12154: TNS:could not resolve the connect identifier specified` | Phân giải alias/chuỗi kết nối | Kiểm tra alias, `tnsnames.ora`, `TNS_ADMIN`, cú pháp Easy Connect và naming methods |
| `ORA-12541: TNS:no listener` | Đầu mối Oracle Net không phản hồi | Kiểm tra hostname, port, listener và mạng/firewall |
| `ORA-12514: TNS:listener does not currently know of service requested` | Listener không nhận diện service yêu cầu | Kiểm tra service name, trạng thái PDB/database và đăng ký dịch vụ với listener |
| `ORA-01017: invalid username/password; logon denied` | Xác thực tài khoản | Kiểm tra user/password, container đích, cách đăng nhập và cơ chế xác thực được cấu hình |
| `ORA-01031: insufficient privileges` | Quyền không đủ | Nếu đang dùng `AS SYSDBA`, kiểm tra OSDBA/password file; nếu là user thường, kiểm tra quyền cần thiết |
| `ORA-01034: ORACLE not available` hoặc lỗi local instance liên quan | Instance/môi trường cục bộ | Kiểm tra `ORACLE_SID`, Oracle Home, trạng thái instance và quyền OS |
| `ORA-28000: the account is locked` | Chính sách tài khoản database | Liên hệ DBA kiểm tra trạng thái/mở khóa theo quy trình, không tự bỏ qua chính sách |

### 7.1. Một trình tự kiểm tra thực tế

**Nếu đăng nhập local `/ as sysdba` bị lỗi:**

1. Xác nhận đang ở **database server** và dùng OS login đúng đối tượng.
2. Kiểm tra `ORACLE_SID`, Oracle Home và client được gọi.
3. Kiểm tra `TWO_TASK`/`LOCAL` có vô tình chuyển kết nối sang mạng hay không.
4. Kiểm tra OS user có thuộc nhóm OSDBA tương ứng hay không, và cấu hình xác thực hệ điều hành có đúng không.
5. Kiểm tra trạng thái instance, service hệ điều hành và log cần thiết.

**Nếu `app_user@//host:port/service` bị lỗi:**

1. Kiểm tra kết nối mạng tới đúng host/port.
2. Xác nhận listener và service name bằng thông tin phía server.
3. Dùng đúng service của PDB, tránh nhầm SID với service name.
4. Kiểm tra user/password, trạng thái khóa tài khoản và quyền `CREATE SESSION` ở đúng container.
5. Nếu hệ thống dùng TLS, wallet, Kerberos hoặc chính sách mạng riêng, đối chiếu cấu hình client/server.

Không nên xử lý lỗi `ORA-12514` bằng cách thay mật khẩu, cũng không nên xử lý `ORA-01017` bằng cách mở cổng listener nếu kết nối mạng đã tới được database. Mỗi mã lỗi chỉ hướng đến một nhóm nguyên nhân ưu tiên, không thay thế việc xem log đầy đủ.

## 8. Quyền truy cập và các thực hành an toàn

**Hạn chế quyền OSDBA.** Tài khoản có quyền đăng nhập `/ as sysdba` có thể thực hiện thao tác quản trị nhạy cảm, kể cả khi không biết mật khẩu của `SYS`. Phải bảo vệ nhóm hệ điều hành, quyền `sudo`/đăng nhập máy chủ và dấu vết kiểm toán tương ứng.

**Sử dụng user ứng dụng có quyền tối thiểu.** Ứng dụng nên dùng user/schema chuyên dụng trên database service/PDB phù hợp; không chạy kết nối nghiệp vụ thường ngày bằng `SYS` hoặc `SYSDBA`.

**Không nhúng mật khẩu vào lệnh shell hoặc mã nguồn.** Dạng `sqlplus user/password@service` có thể làm lộ bí mật trong lịch sử terminal, tập lệnh hoặc công cụ giám sát tiến trình. Với ứng dụng, dùng công cụ lưu trữ bí mật hoặc cơ chế xác thực được quản trị phù hợp.

**Bảo vệ kết nối mạng.** Một kết nối Oracle Net qua TCP không mặc nhiên được mã hóa toàn bộ theo chính sách bạn mong muốn. Khi có yêu cầu bảo mật dữ liệu truyền tải, cần cấu hình/kiểm tra Oracle Net encryption hoặc TLS theo phiên bản và hạ tầng được hỗ trợ.

**Không bật cơ chế tin cậy OS từ xa kiểu cũ.** Không đặt `REMOTE_OS_AUTHENT=TRUE` chỉ để làm cho `/@service` hoạt động. Với đăng nhập một lần, tích hợp danh tính hoặc chứng chỉ, sử dụng giải pháp xác thực mạng được Oracle hỗ trợ, có cấu hình client/server và kiểm soát truy cập cụ thể.

**Không đánh đồng “có thể kết nối” với “được phép làm mọi việc”.** Qua được bước kết nối chỉ là bước đầu. Sau xác thực, Oracle còn kiểm tra đặc quyền hệ thống, quyền trên object, role, chính sách và container hiện tại.

## 9. Những ngộ nhận cần tránh

**Ngộ nhận 1: “Chạy SQL*Plus trên database server là OS authentication.”**  
Không đúng. `sqlplus app_user` (không có `@`, không bị chuyển hướng) có thể kết nối local bequeath nhưng vẫn yêu cầu mật khẩu database.

**Ngộ nhận 2: “Dùng `localhost` là kết nối cục bộ không cần listener.”**  
Không đúng. `@//localhost:1521/service` yêu cầu Oracle Net/TCP và listener/service phù hợp; local bequeath lại không dùng TCP listener.

**Ngộ nhận 3: “Có user Linux `oracle` thì mặc định user đó là `SYS`.”**  
Không đúng. Khi OS user có quyền OSDBA và kết nối `/ as sysdba`, Oracle cấp phiên quản trị với quyền SYSDBA, thường dưới danh tính database `SYS`. Đó là cơ chế đặc quyền, không phải phép ánh xạ tên đơn giản.

**Ngộ nhận 4: “Đổi `ORACLE_SID` là kết nối được vào một PDB.”**  
Không đúng. `ORACLE_SID` chọn instance. PDB thường được chọn qua service name, hoặc một thao tác chuyển container được cấp quyền trong phiên quản trị.

**Ngộ nhận 5: “`sqlplus /@SALES_DB` sẽ tự dùng tài khoản Windows/Linux của tôi trên server.”**  
Không đúng trong cấu hình mặc định. Xác thực tích hợp qua mạng cần có cơ chế và chính sách được cấu hình rõ ràng trên client/server.

**Ngộ nhận 6: “Đăng nhập thành công bằng `SYSDBA` chứng tỏ app user cũng đăng nhập được.”**  
Không đúng. SYSDBA có cơ chế quyền/xác thực đặc biệt; ứng dụng phải kiểm tra đăng nhập bằng chính database user, service/PDB và quyền thực tế của ứng dụng.

## 10. Bài tập tự kiểm tra

1. Trên máy chủ Oracle, hai câu lệnh `sqlplus / as sysdba` và `sqlplus app_user` đều không có `@...`. Chúng giống nhau ở điểm nào, khác nhau ở điểm nào?
2. Một lập trình viên đang ở laptop và chạy `sqlplus app_user@//localhost:1521/SALES`. Lệnh sẽ thử kết nối vào database server ở trung tâm dữ liệu hay vào laptop?
3. Database server có listener ở cổng `1521` bị dừng. DBA thuộc nhóm OSDBA có thể thử cách kết nối nào để kiểm tra instance cục bộ?
4. Trên cùng database server, vì sao `sqlplus app_user@//localhost:1521/salespdb` có thể lỗi `ORA-12514` trong khi `sqlplus / as sysdba` vẫn thành công?
5. Người dùng OS trên máy client muốn đăng nhập qua mạng không cần gõ mật khẩu database. Chỉ cần chạy `sqlplus /@SALES_DB` là đủ chưa? Cần xem xét thêm điều gì?
6. Một ứng dụng Java sử dụng URL `jdbc:oracle:thin:@//dbhost:1521/salespdb`. Nó sử dụng đường kết nối gì? Nó có tự kế thừa quyền SYSDBA của OS user chạy ứng dụng không?

**Gợi ý đáp án:**

1. Có thể đều dùng local bequeath (nếu không có default connect identifier). Lệnh đầu dùng OS authentication với đặc quyền SYSDBA; lệnh sau thường dùng xác thực mật khẩu của database user.
2. `localhost` chỉ chính laptop. Phải dùng địa chỉ/hostname của database server hoặc endpoint phù hợp.
3. Thử `sqlplus / as sysdba` từ chính database server, sau khi kiểm tra đúng môi trường Oracle và nhóm OSDBA.
4. Lệnh mạng cần listener nhận biết service; lệnh bequeath không dựa vào listener TCP và kết nối theo instance.
5. Chưa. Cần cấu hình cơ chế xác thực mạng tích hợp được hỗ trợ, quan hệ tin cậy và ánh xạ danh tính/đặc quyền tương ứng.
6. JDBC Thin đi qua Oracle Net/TCP trong ví dụ. Không tự có quyền SYSDBA từ tài khoản OS; quyền database phụ thuộc phương thức xác thực và cấp quyền thực tế.

## 11. Tài liệu Oracle tham khảo

- [Oracle Database Net Services Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/): Oracle Net, naming methods, listener, service và quản lý kết nối.
- [Oracle Database Net Services Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/netrf/): các tệp/tham số mạng, giao thức và cách cấu hình kết nối.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): external authentication, SYSDBA, password file và các cơ chế xác thực.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): instance, môi trường quản trị, multitenant và quản lý database.
- [SQL*Plus User's Guide and Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqpug/): cú pháp đăng nhập và lệnh SQL*Plus.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): các tham số như `OS_AUTHENT_PREFIX`, `REMOTE_OS_AUTHENT` và các view theo dõi kết nối.

Khi mô tả một phiên Oracle, hãy ghi rõ **client đang chạy ở đâu**, **đường kết nối là bequeath hay Oracle Net**, **service/SID được dùng để chọn database**, **cơ chế xác thực** và **quyền của user sau đăng nhập**. Những thông tin này giúp giải thích đúng hành vi kết nối và tránh nhầm lẫn giữa quyền của hệ điều hành với quyền trong database.
