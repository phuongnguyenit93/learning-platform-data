# Đọc mã lỗi ORA và phân biệt lỗi kết nối với lỗi xác thực

Khi một ứng dụng Java hoặc một công cụ như SQL*Plus, SQLcl, SQL Developer không truy cập được **Oracle Database**, thông báo thường có dạng `ORA-xxxxx`, `TNS-xxxxx` hoặc một exception do driver JDBC trả về. Cùng biểu hiện “không vào được database” có thể xuất phát từ hai nhóm vấn đề rất khác nhau:

- **Lỗi kết nối (connectivity):** ứng dụng chưa đến được đúng Oracle listener/service hoặc không thiết lập, duy trì được phiên kết nối cần thiết. Nguyên nhân có thể nằm ở hostname, DNS, cổng mạng, routing, listener, tên service/PDB, TLS, tài nguyên hoặc kết nối bị ngắt.
- **Lỗi xác thực (authentication):** yêu cầu đăng nhập đã đến bước Oracle kiểm tra danh tính nhưng username, password, trạng thái tài khoản hoặc cơ chế xác thực không đáp ứng yêu cầu. Kết nối mạng vẫn có thể hoàn toàn bình thường.

Còn một nhóm thứ ba phải tách rõ: **lỗi phân quyền (authorization)**, xảy ra khi Oracle đã xác định được danh tính nhưng user không được phép mở session hoặc thực hiện thao tác. Đổi mật khẩu hay mở cổng mạng sẽ không giải quyết được lỗi thiếu quyền trên bảng.

Mục tiêu của bài học là đọc đúng **mã lỗi, vị trí phát sinh và ngữ cảnh kết nối**, từ đó tìm bước kiểm tra phù hợp mà không đoán mò hoặc thay đổi cấu hình production thiếu bằng chứng.

## 1. ORA là gì? Vì sao thông điệp lỗi có nhiều lớp?

Oracle sử dụng mã lỗi gồm tiền tố và số, ví dụ:

```text
ORA-01017: invalid username/password; logon denied
ORA-12514: TNS:listener does not currently know of service requested in connect descriptor
ORA-28000: the account is locked
```

Thông điệp chính xác có thể thay đổi theo phiên bản Oracle, driver và công cụ; **số mã** thường là điểm bắt đầu đáng tin hơn khi phân nhóm. Trên một số công cụ, lỗi tầng Oracle Net còn xuất hiện với tiền tố `TNS-`, chẳng hạn `TNS-12541`. `TNS` không đồng nghĩa với lỗi mật khẩu: Oracle Net có nhiệm vụ tìm và thiết lập đường kết nối tới dịch vụ database.

Ở phía ứng dụng Java, exception còn có nhiều lớp:

```text
Spring / Hibernate / connection pool
    |
    +-- CannotGetJdbcConnectionException / JDBCConnectionException
            |
            +-- java.sql.SQLException hoặc SQLRecoverableException
                    |
                    +-- ORA-12514 / ORA-01017 / ORA-17002 / ...
                            |
                            +-- lỗi socket / DNS / TLS nếu có
```

Đây là cấu trúc minh họa: không phải exception nào cũng có đầy đủ các lớp. Một thông báo tổng quát như `Failed to obtain JDBC Connection` **chưa đủ** kết luận mạng bị hỏng. Phải đọc phần **cause/next exception**, mã vendor do `SQLException.getErrorCode()` cung cấp, SQLState và thông điệp của driver.

Các thông tin nên ghi nhận khi điều tra gồm thời điểm, môi trường, ứng dụng/phiên bản triển khai, hostname/port/service name đã che thông tin nhạy cảm, mã ORA hoặc TNS, JDBC error code/SQLState, có kết nối được từ nguồn khác hay không và thay đổi gần nhất. Không ghi mật khẩu, token, wallet hoặc toàn bộ URL nếu URL chứa secret.

## 2. Luồng tạo kết nối Oracle: lỗi có thể nằm ở đâu?

Với một ứng dụng kết nối bằng Oracle JDBC Thin, có thể hình dung đường đi như sau:

```text
Ứng dụng / SQL client
       |
       |  (1) Đọc connect descriptor: host, port, service hoặc TNS alias
       v
Phân giải tên và tạo đường mạng (DNS, routing, firewall, TCP)
       |
       |  (2) Tới listener hoặc endpoint Oracle Net
       v
Oracle listener
       |
       |  (3) Nhận diện service và định tuyến đến instance/PDB phù hợp
       v
Oracle database server/session
       |
       |  (4) Kiểm tra cơ chế xác thực, username, password,
       |      trạng thái account; kiểm tra quyền mở session
       v
Session được thiết lập
       |
       |  (5) Thực thi SQL/PLSQL với quyền trên đối tượng
       v
Truy vấn, giao dịch, kết quả
```

Trong hệ thống dùng **TCPS/TLS**, việc xác minh chứng chỉ, ví/wallet và cấu hình mã hóa còn tham gia vào quá trình thiết lập kết nối; lỗi ở đây không nên gọi nhầm là “sai mật khẩu database”. Với Oracle RAC, Data Guard, service chuyển hướng hoặc database dịch vụ quản lý trên cloud, phần định tuyến phức tạp hơn nhưng cách tách pha chẩn đoán vẫn hữu ích.

| Pha | Câu hỏi cần trả lời | Dấu hiệu/mã thường liên quan |
|---|---|---|
| Đọc địa chỉ kết nối | Alias TNS hay connect descriptor có được phân giải đúng không? | `ORA-12154` |
| Đường mạng và listener | Host/port có truy cập được, listener có sẵn sàng không? | `ORA-12541`, `ORA-12545`, timeout như `ORA-12170` |
| Định tuyến service/SID | Listener có biết service/PDB hoặc SID yêu cầu không? | `ORA-12514`, `ORA-12505` |
| Thiết lập phiên/tài nguyên | Server có thể cấp handler/session phù hợp không? | `ORA-12516`, `ORA-12519`, đôi khi lỗi giới hạn session/process |
| Xác thực | Account và cơ chế đăng nhập có hợp lệ không? | `ORA-01017`, `ORA-28000`, `ORA-28001`, `ORA-28040` |
| Quyền truy cập | User có quyền `CREATE SESSION` và quyền trên object không? | `ORA-01045`, `ORA-01031`, đôi khi `ORA-00942` |
| Sau khi kết nối | Session có bị ngắt trong lúc truy vấn hoặc giao dịch không? | `ORA-03113`, `ORA-03114`, các lỗi mạng tùy ngữ cảnh |

**Một mã lỗi mô tả điều Oracle/driver quan sát được, chưa chắc chỉ ra một nguyên nhân duy nhất.** Ví dụ timeout có thể do firewall, quá tải, endpoint không phản hồi hoặc cơ chế bảo mật; cần thêm log và phép thử từ đúng nơi ứng dụng chạy.

## 3. Nhóm lỗi kết nối: trước khi Oracle kiểm tra username/password

### 3.1. `ORA-12154` – không phân giải được connect identifier

Ví dụ:

```text
ORA-12154: TNS:could not resolve the connect identifier specified
```

Thông thường Oracle Net client không tìm hoặc không phân giải được alias/chuỗi kết nối thành một connect descriptor hợp lệ. Các hướng kiểm tra:

- Đánh máy đúng alias hoặc `SERVICE_NAME` chưa? Có nhầm tên alias (`ORCL_DEV`) với tên service (`app_dev_service`) không?
- Công cụ đang dùng đúng `tnsnames.ora`, `sqlnet.ora`, cấu hình `TNS_ADMIN` hoặc Oracle client configuration chưa?
- Có lỗi cú pháp connect descriptor hoặc đường dẫn tới cấu hình Oracle Net không?
- Nếu dùng Easy Connect, đang viết đúng cú pháp `//host:port/service` chưa?

Không nên bắt đầu bằng việc đổi mật khẩu: lỗi xảy ra trước khi Oracle có thể xác thực user. Nếu dùng alias, `tnsping <alias>` có thể giúp kiểm tra khả năng phân giải Oracle Net và tiếp cận listener, nhưng không xác minh login hoặc việc truy vấn sẽ thành công.

### 3.2. `ORA-12541` – không tìm thấy listener tại endpoint

Ví dụ:

```text
ORA-12541: TNS:no listener
```

Thường là không có listener nhận kết nối ở địa chỉ/cổng được yêu cầu, hoặc đường đi khiến client nhận kết quả tương ứng. Cần xác minh host, port, môi trường, listener đang chạy và cấu hình bind endpoint. Chẳng hạn, ứng dụng đổi sang port mới nhưng cấu hình mạng vẫn trỏ vào port cũ.

Ở máy Windows có thể thử một phép kiểm tra **TCP cơ bản**:

```powershell
Test-NetConnection -ComputerName oracle-dev.example.internal -Port 1521
```

`TcpTestSucceeded: True` chỉ chứng minh có thể thiết lập kết nối TCP tới địa chỉ/cổng tại thời điểm kiểm tra; nó **không chứng minh service Oracle đúng, tài khoản hợp lệ hoặc ứng dụng truy vấn được**. Nếu TCP không thành công, tiếp tục kiểm tra DNS, route, firewall, listener và đúng network segment. Dùng tên host/port thực tế đã được cấp, không lấy ví dụ trên làm endpoint thật.

### 3.3. `ORA-12545`, `ORA-12170`, `ORA-12535` – không tới được đích hoặc timeout

Các thông điệp thường thấy:

```text
ORA-12545: Connect failed because target host or object does not exist
ORA-12170: TNS:Connect timeout occurred
ORA-12535: TNS:operation timed out
```

`ORA-12545` gợi ý tên host/địa chỉ đích hoặc việc truy cập đích có vấn đề; kiểm tra DNS, hostname, route, cấu hình connect descriptor và khả năng đến đúng endpoint. `ORA-12170`/`ORA-12535` mô tả giới hạn thời gian đã hết, nhưng nguyên nhân cụ thể có thể là một mắt xích mạng không phản hồi, listener/database quá tải hoặc thiết lập bảo mật chậm/thất bại.

Phải thử từ **chính máy/container/pod chạy ứng dụng**, hoặc một nơi có cùng mạng và chính sách egress. Việc laptop của developer truy cập được database không chứng minh ứng dụng trong Kubernetes hoặc CI runner cũng truy cập được.

Không nên giải quyết mọi timeout bằng cách tăng timeout lên rất cao. Nếu endpoint sai hoặc firewall chặn, tăng thời gian chờ chỉ khiến người dùng đợi lâu hơn và làm cạn connection pool.

### 3.4. `ORA-12514` – listener không biết service được yêu cầu

Ví dụ:

```text
ORA-12514: TNS:listener does not currently know of service requested in connect descriptor
```

Client đã tới một listener nhưng listener không nhận diện **service name** đã khai báo tại thời điểm đó. Đây là lỗi **định tuyến dịch vụ Oracle**, không phải bằng chứng rằng username/password sai. Các khả năng thường cần xem:

- URL viết nhầm tên service hoặc trỏ nhầm môi trường/PDB.
- PDB chưa mở hoặc service ứng dụng chưa được khởi chạy/đăng ký phù hợp.
- Listener/đăng ký service chưa đồng bộ sau khởi động, chuyển đổi hoặc đổi cấu hình.
- Client đang đi tới listener khác dự kiến do DNS, routing hoặc một connect descriptor nhiều địa chỉ.

Ví dụ kết nối qua service name bằng JDBC Thin:

```text
jdbc:oracle:thin:@//oracle-dev.example.internal:1521/app_dev_service
```

Ở máy chủ được cấp quyền quản trị, DBA có thể xem trạng thái đăng ký bằng `lsnrctl services`, kiểm tra trạng thái PDB và dịch vụ Oracle. Trong môi trường database được quản lý, thông tin tương đương thường phải lấy qua công cụ/dịch vụ nhà cung cấp; không mặc định ứng dụng được phép chạy `lsnrctl`.

### 3.5. `ORA-12505` – listener không biết SID được yêu cầu

Ví dụ:

```text
ORA-12505: TNS:listener does not currently know of SID given in connect descriptor
```

Lỗi này liên quan đến kết nối yêu cầu **SID** không được listener nhận diện. Phân biệt hai kiểu định danh:

```text
# JDBC Thin dùng service name (thông dụng với PDB)
jdbc:oracle:thin:@//db.example.internal:1521/app_service

# JDBC Thin kiểu cũ định danh bằng SID
jdbc:oracle:thin:@db.example.internal:1521:ORCL
```

Trong kiến trúc multitenant, ứng dụng thường kết nối qua **service name của PDB**, không thay service name bằng tên SID của instance. Cần lấy đúng connect descriptor từ DBA; không tự đổi dấu `/` thành `:` với hy vọng khắc phục nhanh.

### 3.6. `ORA-12516`, `ORA-12519` – listener biết đích nhưng không có handler phù hợp

Ví dụ:

```text
ORA-12516: TNS:listener could not find available handler with matching protocol stack
ORA-12519: TNS:no appropriate service handler found
```

Nhóm này liên quan tới khả năng listener chuyển yêu cầu sang handler/server process phù hợp. Trường hợp phổ biến cần phân tích là tăng tải đột ngột, giới hạn process/session, trạng thái instance, đăng ký service hoặc loại server được yêu cầu. `ORA-00018`/`ORA-00020` cũng có thể xuất hiện khi chạm giới hạn session/process của database, tùy ngữ cảnh.

Developer kiểm tra số kết nối của pool, số replica ứng dụng, connection leak và retry storm; DBA kiểm tra instance, giới hạn tài nguyên và handler; operations đối chiếu thời điểm scale/release. Không mặc định “tăng `PROCESSES`” là biện pháp duy nhất; nếu ứng dụng mở connection không giới hạn, sự cố sẽ tái diễn.

### 3.7. `ORA-17002` và các lỗi JDBC I/O

Ở phía JDBC Thin, có thể gặp thông báo như:

```text
java.sql.SQLRecoverableException: IO Error: The Network Adapter could not establish the connection
... Error Code: 17002
```

`17002` là mã lỗi trong ngữ cảnh Oracle JDBC và thường báo một lỗi I/O ở phía driver. Nó **không tự phân biệt** DNS, firewall, host sai, listener không nghe, socket bị đóng hoặc TLS. Phải đọc exception được lồng bên trong, chẳng hạn `UnknownHostException`, `ConnectException`, `SocketTimeoutException` hoặc lỗi SSL, rồi đối chiếu endpoint/network.

Ngay cả khi thấy `SQLRecoverableException`, không tự retry vô hạn: connection có thể không phục hồi được cho đến khi cấu hình hoặc database được xử lý. Đối với transaction đang chạy, cần xác định liệu server đã commit trước khi đường truyền bị đứt hay chưa; retry thao tác ghi phải bảo đảm idempotency hoặc có cơ chế đối soát.

## 4. Nhóm lỗi xác thực: đã đến bước đăng nhập nhưng danh tính không hợp lệ

### 4.1. `ORA-01017` – username/password không được chấp nhận

Ví dụ:

```text
ORA-01017: invalid username/password; logon denied
```

Đây là dấu hiệu điển hình của **lỗi xác thực**, khác `ORA-12514` hay `ORA-12541`. Tuy nhiên “invalid username/password” không nhất thiết có nghĩa người dùng vừa nhập sai ký tự. Cần xem:

- Username, password và secret version đã được inject đúng môi trường chưa?
- Ứng dụng có đang tới **đúng PDB/service** chứa tài khoản đó không? User hợp lệ ở DEV chưa chắc tồn tại ở TEST/PROD.
- Mật khẩu vừa được rotate nhưng một số replica/CI secret hoặc connection pool còn giữ credential cũ?
- Tài khoản được tạo với quoted identifier có phân biệt chữ hoa/chữ thường hoặc client truyền username theo cách khác dự kiến?
- Password có ký tự đặc biệt bị shell, file cấu hình, URL hoặc secret templating xử lý sai? Không in password ra log để kiểm chứng.
- Phương thức xác thực dùng là password, external, wallet, proxy hay phương án khác? Cấu hình client và server có thống nhất không?

Để phân biệt, hãy giữ nguyên endpoint và thử bằng **một công cụ Oracle đã được phép** với cùng danh tính (nhập mật khẩu qua prompt an toàn), từ nguồn mạng tương đương. Không liên tục thử nhiều biến thể mật khẩu: chính sách profile có thể khóa tài khoản sau một số lần thất bại.

### 4.2. `ORA-28000` – tài khoản bị khóa

```text
ORA-28000: the account is locked
```

Oracle từ chối đăng nhập vì account ở trạng thái khóa. Khả năng gồm số lần đăng nhập sai vượt chính sách profile, DBA khóa chủ động hoặc chính sách bảo mật khác. DBA/người quản trị xác minh `ACCOUNT_STATUS`, nguyên nhân và quy trình mở khóa. **Không tự mở khóa liên tục** khi ứng dụng vẫn gửi mật khẩu cũ: account có thể lại bị khóa và cần điều tra nguồn login sai hoặc vòng retry.

### 4.3. `ORA-28001` – mật khẩu hết hạn

```text
ORA-28001: the password has expired
```

Đây là vấn đề vòng đời credential. Quy trình thường gồm thay/rotate mật khẩu theo chính sách, cập nhật secret manager và bảo đảm mọi workload dùng phiên bản mới. `ORA-28002` là thông báo **mật khẩu sắp hết hạn**; trong nhiều ngữ cảnh kết nối vẫn được tạo, nhưng đó là cảnh báo phải xử lý sớm chứ không phải lỗi kết nối TCP.

### 4.4. `ORA-28040` – không thống nhất giao thức xác thực

```text
ORA-28040: No matching authentication protocol
```

Mã này thường phản ánh **không tương thích giao thức/cơ chế xác thực** giữa client và Oracle server hoặc chính sách được cấu hình. Nguyên nhân cần DBA và developer kiểm tra: phiên bản JDBC/Oracle client, chính sách xác thực của database, tài khoản và cấu hình bảo mật. Đừng diễn giải mã này thành “mật khẩu sai” rồi đổi mật khẩu hàng loạt; tránh hạ cấu hình bảo mật chỉ để kết nối được nếu chưa đánh giá rủi ro và phương án nâng cấp client.

### 4.5. Phân quyền: `ORA-01045`, `ORA-01031`, `ORA-00942`

```text
ORA-01045: user ... lacks CREATE SESSION privilege; logon denied
ORA-01031: insufficient privileges
ORA-00942: table or view does not exist
```

- `ORA-01045` xảy ra ở ranh giới **quyền mở session**, khi danh tính user được nhận diện nhưng không có quyền `CREATE SESSION` cần thiết.
- `ORA-01031` xảy ra khi Oracle từ chối một thao tác do thiếu privilege; có thể liên quan SQL, DDL hoặc thủ tục.
- `ORA-00942` có thể do đối tượng thật sự không tồn tại, sai schema/đồng nghĩa đối tượng (synonym) hoặc user thiếu quyền nhìn/truy cập đối tượng. Không tự kết luận user đã nhập sai mật khẩu.

Ví dụ ứng dụng đăng nhập thành công và chạy `SELECT * FROM orders`, nhưng Oracle báo `ORA-00942`. Điều tra **schema sở hữu `ORDERS`, câu SQL, synonym và grant cần thiết**, không kiểm tra listener nữa. Với truy cập cross-schema, grant trực tiếp cho schema hoặc quyền phù hợp cần được DBA/chủ sở hữu dữ liệu phê duyệt; cấp `DBA` để sửa lỗi là quá mức.

## 5. Lỗi bảo mật đường truyền khác lỗi mật khẩu Oracle

Một số môi trường yêu cầu **TCPS/TLS**, xác thực chứng chỉ, Oracle wallet hoặc mTLS. Khi cấu hình bảo mật tầng truyền dẫn không khớp, Oracle client có thể thất bại **trước khi** bước đăng nhập bằng password diễn ra.

| Mã/vùng lỗi | Ý nghĩa định hướng | Hướng kiểm tra |
|---|---|---|
| `ORA-29024` | Xác thực certificate không thành công | Chuỗi trust, tên máy chủ, thời hạn cert, CA và cấu hình TLS được duyệt |
| `ORA-28759` | Không mở được file/nguồn wallet theo yêu cầu | Đường dẫn, quyền truy cập file, bản phân phối wallet và cấu hình client |
| `ORA-12638` | Lỗi truy xuất thông tin credential trong một cơ chế xác thực | Credential provider/external auth, cấu hình client và môi trường chạy |
| Lỗi `SSLHandshakeException` trong JDBC | TLS handshake thất bại | Truststore/wallet, certificate, phiên bản giao thức, proxy/load balancer liên quan |

Mã cụ thể còn tùy cách cấu hình Oracle Net và JDBC. Tránh bỏ kiểm chứng certificate, tắt mã hóa hoặc chuyển sang TCP không mã hóa để “fix nhanh” trong hệ thống có yêu cầu bảo mật. Cần xử lý nguyên nhân theo cấu hình và chính sách được chấp thuận.

## 6. Bảng tra nhanh: nhìn mã nào, gọi nhóm nào?

| Mã/biểu hiện | Nhóm ưu tiên | Việc kiểm tra đầu tiên | Nhóm thường phối hợp |
|---|---|---|---|
| `ORA-12154` | Cấu hình client/định danh | Alias, `tnsnames.ora`, `TNS_ADMIN`, Easy Connect | Developer / operations |
| `ORA-12541` | Listener/đường mạng | Host, port, TCP, listener endpoint | Operations / DBA |
| `ORA-12545` | Host/route | DNS, địa chỉ đích, kết nối từ runtime | Operations |
| `ORA-12170`, `ORA-12535` | Timeout | Mốc timeout, route, firewall, tải và server response | Operations / DBA |
| `ORA-12514` | Định tuyến service | Service name, trạng thái PDB, đăng ký listener | DBA / operations |
| `ORA-12505` | Định tuyến SID | Kết nối dùng SID hay service, SID/service có tồn tại không | DBA / developer |
| `ORA-12516`, `ORA-12519` | Handler/tài nguyên | Session/process/handler, pool và tải | DBA / developer |
| JDBC `17002` | I/O phía client | Nested exception và đích TCP/TLS | Developer / operations |
| `ORA-01017` | Xác thực user/password | Secret, user, đúng PDB/service, thay đổi credential | Developer / DBA |
| `ORA-28000` | Account bị khóa | Trạng thái account, nguồn login thất bại, retry | DBA / owner ứng dụng |
| `ORA-28001` | Password hết hạn | Chính sách expiry và luồng rotate secret | DBA / owner ứng dụng |
| `ORA-28040` | Giao thức xác thực | Phiên bản client/driver và chính sách auth | DBA / developer |
| `ORA-01045` | Quyền mở session | `CREATE SESSION` của user | DBA |
| `ORA-01031`, `ORA-00942` | Quyền hoặc schema sau login | Object owner, grant, câu SQL, current schema | Developer / DBA |
| `ORA-29024`, lỗi wallet/TLS | Bảo mật đường truyền | Certificate/wallet/trust config | Operations / DBA |
| `ORA-03113`, `ORA-03114` | Session/communication sau hoặc trong kết nối | Thời điểm rớt phiên, database/network logs, transaction | DBA / operations / developer |

Đây là **bảng định tuyến điều tra**, không phải khẳng định rằng mỗi mã chỉ có đúng một nguyên nhân hoặc một nhóm được phép thực thi tất cả thao tác liên quan.

## 7. Quy trình chẩn đoán từng bước khi “không kết nối được Oracle”

### Bước 1 – Thu thập mã lỗi gốc và xác định phạm vi

Ghi nhận một vài trường thông tin có ích:

```text
Environment: TEST
Application: order-api
Release: 2026.11.x
Time: 14:25 +07
Error: ORA-12514
Database target: test-db.internal:1521 / order_test_service
Impact: all pods after rollout; other apps unknown
Recent change: service name configuration updated
```

Đây là ví dụ giả định, không chứa credential. Cần trả lời: lỗi có xảy ra với **mọi replica** hay chỉ một node? Chỉ một môi trường hay tất cả? Khi startup, lấy connection từ pool, chạy một truy vấn cụ thể hay giữa giao dịch? Nếu số ít kết nối lỗi ngẫu nhiên, hướng điều tra khác lỗi mọi kết nối đều bị từ chối.

### Bước 2 – Kiểm tra connect descriptor, không nhầm SID với service

Với JDBC Thin, cú pháp thường dùng là:

```text
jdbc:oracle:thin:@//<host>:<port>/<service_name>
```

Ví dụ:

```text
jdbc:oracle:thin:@//oracle-test.example.internal:1521/order_test_service
```

Đối chiếu host/port/service được DBA cấp, cấu hình thực tế sau khi secret/config được inject, profile ứng dụng và các thay đổi triển khai. Hai nơi có cùng hostname chưa chắc cùng PDB; hai URL khác nhau cũng có thể đi tới cùng database nếu mapping sai. Không chụp hay chia sẻ cấu hình chứa mật khẩu.

### Bước 3 – Kiểm tra tên host, mạng, listener từ vị trí ứng dụng

Nếu mã chỉ đến network/listener, hãy bắt đầu với DNS/route/port tại máy chạy ứng dụng. Với Windows, phép thử TCP có thể dùng `Test-NetConnection`; trên hệ thống Linux hoặc container, dùng công cụ mạng được cho phép. Từ phía DBA, kiểm tra listener service registration và trạng thái PDB/instance bằng công cụ quản trị phù hợp.

**Diễn giải kết quả cẩn thận:**

- Không resolve được hostname: kiểm tra DNS và cấu hình runtime.
- TCP không mở: kiểm tra firewall, routing, port/listener, trạng thái server.
- TCP mở nhưng `ORA-12514`: service/PDB/registration còn sai hoặc chưa sẵn sàng.
- Có tới database nhưng `ORA-01017`: chuyển sang xác thực và đích PDB/user.

Một kiểm tra mạng thành công không bỏ qua được bước xác thực; một thông báo xác thực không nói rằng mọi endpoint khác đều khỏe.

### Bước 4 – Thử đăng nhập bằng client đáng tin cậy

Từ một nơi được phép truy cập Oracle, có thể dùng SQL*Plus để xác minh kết nối trên **môi trường phù hợp**:

```text
sqlplus -L app_reader@//oracle-test.example.internal:1521/order_test_service
```

Khi client yêu cầu, nhập mật khẩu qua prompt tương tác hoặc cơ chế bảo mật đã được thiết lập. **Không** nhúng mật khẩu vào command line, không dán kết quả chứa secret vào chat/ticket. Tùy chính sách môi trường, việc cố đăng nhập sai nhiều lần có thể khóa account; chỉ thực hiện với sự cho phép và hạn chế số lần thử.

So sánh kết quả test bằng client và ứng dụng:

| Quan sát | Hướng giải thích |
|---|---|
| SQL*Plus và ứng dụng đều `ORA-12514` cùng đích | Ưu tiên kiểm tra service/listener/PDB |
| SQL*Plus kết nối được, ứng dụng `ORA-12541` | Kiểm tra network path khác nhau, host/port cấu hình, DNS hoặc runtime environment |
| Client và app đều `ORA-01017` cùng account/PDB | Kiểm tra secret, trạng thái user và phương thức auth |
| Client được, app `ORA-01017` | So sánh secret injected, username, service/PDB, client/driver auth, rotation |
| Cùng user login được nhưng query `ORA-00942` | Kết nối/xác thực xong; chuyển sang schema/privilege/object |

### Bước 5 – Khi login thành công, xác minh đang ở đúng database/PDB

Chạy truy vấn chỉ đọc sau bằng session có quyền bình thường:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

`SESSION_USER` giúp biết danh tính đăng nhập; `CURRENT_SCHEMA` là schema dùng để phân giải tên đối tượng không được chỉ rõ owner và có thể được thay đổi cho session. Nó **không cấp thêm quyền** và không nhất thiết trùng `SESSION_USER`. Trong Oracle multitenant, giá trị `CON_NAME` giúp xác nhận PDB hiện tại. Đối chiếu kết quả với môi trường mong đợi, không lấy tên alias trên laptop làm bằng chứng duy nhất.

### Bước 6 – Nếu là lỗi xác thực, kiểm tra account bằng kênh quản trị

DBA hoặc người có quyền phù hợp có thể tra trạng thái account, ví dụ:

```sql
-- Chỉ dành cho người có quyền xem DBA_USERS.
SELECT username, account_status, lock_date, expiry_date
FROM dba_users
WHERE username = 'APP_RUNTIME';
```

Đây là truy vấn minh họa dành cho user thông thường được tạo bằng tên không quote; tên thật phải đối chiếu đúng. Kết quả giúp phân biệt `OPEN`, `LOCKED`, `EXPIRED` và các trạng thái kết hợp. Developer thường không cần quyền `SELECT` trên `DBA_USERS`; có thể yêu cầu DBA kiểm tra mà không mở quyền quản trị cho tài khoản ứng dụng.

Nếu account khóa, cần tìm nguồn đang gửi mật khẩu cũ hoặc script retry; nếu password hết hạn, thực hiện quy trình rotate; nếu `ORA-28040`, kiểm tra tương thích giao thức với driver. Không mở `SYSDBA`, tắt policy mật khẩu hoặc thay hàng loạt quyền chỉ để thử kết nối.

### Bước 7 – Kiểm tra sau sửa và lưu bằng chứng

Sau khi thay cấu hình hợp lệ, xác nhận **đúng vấn đề đã được giải quyết**: session mới kết nối tới service/PDB đích, ứng dụng chạy một truy vấn chỉ đọc hoặc smoke test an toàn, connection pool không còn tạo lỗi, tỷ lệ lỗi và thời gian phản hồi trở về bình thường. Ghi thời điểm, thay đổi, kết quả và người chịu trách nhiệm. Nếu sửa mạng làm chuyển sang `ORA-01017`, đó có thể là bằng chứng đã đi qua được lớp kết nối và hiện đang tới bước xác thực; không có nghĩa sửa mạng thất bại.

## 8. Ví dụ Java: lấy vendor code và nguyên nhân từ `SQLException`

Oracle JDBC thường cung cấp **numeric vendor error code**, SQLState và chuỗi exception. Mã Spring/Hibernate bên ngoài có thể bọc `SQLException`, vì vậy log cần giữ được nguyên nhân gốc theo cách bảo mật.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class OracleConnectionProbe {
    public static void main(String[] args) {
        String url = System.getenv("ORACLE_JDBC_URL");
        String user = System.getenv("ORACLE_DB_USER");
        String password = System.getenv("ORACLE_DB_PASSWORD");

        if (url == null || user == null || password == null) {
            System.err.println("Missing Oracle connection configuration");
            return;
        }

        try (Connection connection = DriverManager.getConnection(url, user, password)) {
            System.out.println("Oracle connection established");
        } catch (SQLException error) {
            SQLException current = error;
            while (current != null) {
                int code = current.getErrorCode();
                System.err.printf(
                    "SQL vendor code=%d, SQLState=%s, category=%s%n",
                    code,
                    current.getSQLState(),
                    classify(code)
                );
                current = current.getNextException();
            }
            // Trong hệ thống thật, ghi nhận cause chain theo cơ chế log
            // có kiểm soát để tránh làm lộ secret hoặc thông tin nhạy cảm.
        }
    }

    private static String classify(int code) {
        return switch (code) {
            case 12154, 12541, 12545, 12170, 12535, 12514, 12505 -> "CONNECTIVITY";
            case 1017, 28000, 28001, 28040 -> "AUTHENTICATION";
            case 1045, 1031, 942 -> "AUTHORIZATION_OR_SCHEMA";
            case 17002 -> "JDBC_IO_NEEDS_CAUSE";
            default -> "CHECK_FULL_CONTEXT";
        };
    }
}
```

Đoạn mã minh họa cần Oracle JDBC driver trên classpath và thông tin môi trường hợp lệ. Nó **phân loại phục vụ chẩn đoán**, không tự sửa lỗi hoặc bảo đảm rằng tất cả tình huống đã được bao phủ. Trong thực tế, Spring connection pool, Hibernate và ứng dụng có thể bọc lỗi ở nhiều lớp `Throwable`; cần lưu thêm cause chain và metadata phù hợp, nhưng không log toàn bộ config, password, credential, wallet hay truy vấn có dữ liệu nhạy cảm.

Với `ORA-17002` hoặc một lỗi `SQLRecoverableException` không có mã Oracle rõ ràng, `getCause()` có thể chứa `UnknownHostException`, `ConnectException`, timeout hoặc SSL exception. Vì thế **đừng chỉ kiểm tra một vài số và bỏ qua stack trace**. Mã `SQLState` cũng có ích cho phân nhóm, nhưng cách map SQLState có thể khác giữa phiên bản driver/cơ chế phát sinh lỗi; tránh xây logic nghiệp vụ chỉ dựa trên SQLState.

### 8.1. Ví dụ cấu hình ứng dụng Java/Spring Boot

```yaml
spring:
  datasource:
    url: ${ORACLE_JDBC_URL}
    username: ${ORACLE_DB_USER}
    password: ${ORACLE_DB_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
```

DEV, TEST, PROD cần URL, user và secret được cấp riêng. Cách cấu hình qua biến môi trường là ví dụ; ứng dụng production nên dùng cơ chế secret management của nền tảng và phân quyền đọc secret thích hợp. Khi debug, chỉ ghi **tên môi trường, service/host an toàn và mã lỗi**; không in các biến chứa mật khẩu hay giá trị truststore/wallet nhạy cảm.

## 9. Ba tình huống điều tra thực tế

### Tình huống A – Sau triển khai, mọi pod báo `ORA-12514`

Ứng dụng trước đó kết nối ổn định. Sau release đổi `ORACLE_JDBC_URL`, tất cả replica đều báo `ORA-12514`. Từ cùng mạng, TCP tới port listener mở; không có thông báo password sai.

1. Developer đối chiếu URL đã triển khai với tài liệu service được cấp, xem tên service có bị typo hoặc trỏ sang môi trường khác.
2. Operations kiểm tra config injection, DNS/route và thay đổi deployment.
3. DBA xác nhận PDB/service hoạt động và service đã được listener đăng ký.
4. Sau khi sửa đúng đích, chạy smoke test kết nối và query chỉ đọc, theo dõi tỷ lệ lỗi.

Kết luận phân nhóm: **lỗi kết nối/định tuyến service**. Rotate password hoặc cấp thêm privilege không giải quyết đúng nguyên nhân.

### Tình huống B – Mạng hoạt động nhưng xuất hiện `ORA-01017` rồi `ORA-28000`

Sau kỳ rotate mật khẩu, một replica cũ còn sử dụng secret version trước. Replica này liên tục tạo session mới và nhận `ORA-01017`; sau nhiều lần thất bại, account bị khóa nên các replica khác cũng gặp `ORA-28000`.

1. Operations xác định replica/deployment nào phát sinh login fail, tạm dừng vòng retry theo runbook.
2. Developer xác minh cấu hình injected có cùng version với secret vừa rotate mà không in password.
3. DBA kiểm tra trạng thái account, audit phù hợp và chỉ mở khóa sau khi nguồn login sai đã được sửa.
4. Đưa mọi replica về credential đúng, kiểm tra connection mới và theo dõi phát sinh lỗi.

Kết luận phân nhóm: **xác thực/vòng đời credential**. Listener và TCP có thể hoàn toàn khỏe. Cứ mở khóa account mà không loại bỏ nguồn gửi mật khẩu cũ sẽ làm lỗi lặp lại.

### Tình huống C – Login thành công, query báo `ORA-00942`

Ứng dụng kết nối được vào đúng PDB và user. Lệnh `SELECT 1 FROM dual` chạy thành công, nhưng câu truy vấn bảng nghiệp vụ lỗi `ORA-00942`.

1. Developer kiểm tra tên bảng, schema owner, migration của release và việc query có chỉ rõ owner hay không.
2. DBA/chủ sở hữu schema xác minh đối tượng đã tồn tại và grant cần thiết; kiểm tra nếu synonym được kỳ vọng.
3. Chạy lại đúng câu SQL bằng account runtime, không dùng account DBA để tạo ra một kết quả sai lệch về quyền.

Kết luận phân nhóm: **schema/quyền sau xác thực**. Đổi port, listener hay mật khẩu sẽ không xử lý nguyên nhân.

## 10. Khi kết nối đã thành công nhưng session bị ngắt

“Kết nối lỗi” còn có thể chỉ một session đang hoạt động bị đóng đột ngột. Ví dụ:

```text
ORA-03113: end-of-file on communication channel
ORA-03114: not connected to ORACLE
```

Những mã này không nói trực tiếp mật khẩu đúng hay sai; session có thể đã bị ngắt do lỗi server process, mạng, cấu hình hạ tầng, restart/failover, timeout hoặc sự cố ở phía client/server. Cần thu thập cùng lúc log ứng dụng, thời điểm request, Oracle alert/trace khi được DBA hỗ trợ, các sự kiện restart/failover và metric mạng. Nếu dùng connection pool, kiểm tra validation/eviction và cách ứng dụng xử lý connection mất hiệu lực.

**Đặc biệt với giao dịch ghi:** mất kết nối sau khi gửi `COMMIT` có thể khiến client không biết transaction đã commit trên server hay chưa. Không tự retry một lệnh thanh toán/chuyển tiền chỉ vì thấy lỗi đường truyền. Cần cơ chế định danh nghiệp vụ, idempotency, đối soát hoặc giải pháp transaction recovery phù hợp với kiến trúc.

## 11. Thực hành phân biệt lỗi có kiểm soát

Bài tập nên thực hiện trên **DEV/TEST được cấp phép**, không cố tình gây lỗi trên production hoặc tài khoản có chính sách khóa nghiêm ngặt. Không chỉnh listener, PDB, firewall hoặc mật khẩu hệ thống chỉ để tái hiện nếu chưa có quyền và kế hoạch phù hợp.

### Bài tập 1 – Dự đoán lỗi theo pha

Giả sử có một JDBC URL hợp lệ tới `dev-db.example.internal:1521/dev_service`. Với từng thay đổi sau, xác định **pha có thể bị ảnh hưởng**, không yêu cầu dự đoán chính xác một mã duy nhất:

| Thay đổi giả định | Pha nên điều tra |
|---|---|
| Sai tên alias trong `tnsnames.ora` | Phân giải connect identifier |
| Trỏ tới port không có listener | Đường mạng/listener |
| Giữ đúng host/port nhưng sai service name | Định tuyến service |
| Đúng service nhưng đưa secret cũ vào ứng dụng | Xác thực |
| User được nhận diện nhưng không có `CREATE SESSION` | Phân quyền tạo session |
| User đăng nhập được nhưng thiếu quyền đọc bảng `ORDERS` | Quyền/schema khi thực thi SQL |

### Bài tập 2 – Dùng cùng phép kiểm tra sau khi login

Nếu có hai môi trường Oracle DEV/TEST và tài khoản read-only, hãy kết nối từng nơi rồi chạy:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
```

Ghi lại **môi trường, đích kết nối dự kiến, kết quả thực tế** (không chụp secret), rồi giải thích vì sao chỉ thấy ứng dụng khai báo profile `test` chưa đủ để bảo đảm nó kết nối vào TEST. Nếu các môi trường nằm trên những PDB khác nhau, đối chiếu `CON_NAME`; nếu là database độc lập, đối chiếu thêm endpoint/định danh database do DBA cung cấp.

### Bài tập 3 – Từ log đến quyết định đầu tiên

Không cần tạo lỗi thật. Hãy tự phân loại bốn thông báo giả định:

```text
A. ORA-12541: TNS:no listener
B. ORA-01017: invalid username/password; logon denied
C. ORA-12514: listener does not currently know of service requested
D. ORA-01031: insufficient privileges
```

- **A:** xác minh host/port và listener từ nguồn mạng của ứng dụng.
- **B:** xác minh account, secret version, service/PDB và cơ chế xác thực; giới hạn số lần login thử.
- **C:** kiểm tra service name, đăng ký listener và trạng thái PDB; không đổi password theo phản xạ.
- **D:** xác định thao tác bị từ chối và quyền cần thiết; xem bằng user runtime, không sử dụng DBA để kiểm thử thay.

Kết quả bài tập nên ghi được ít nhất ba thông tin: mã lỗi nguyên gốc, **pha kết nối**, và **bước kiểm tra có bằng chứng**. Việc xử lý production sau đó tuân theo quyền truy cập/runbook của tổ chức.

## 12. Sai lầm dễ gặp khi đọc lỗi ORA

| Suy luận sai | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| “Không login được nên chắc mật khẩu sai.” | Không resolve alias, sai service hoặc mất listener đều có thể chặn trước xác thực. | Đọc mã lỗi và định vị đúng pha. |
| “TCP port 1521 mở thì Oracle ổn.” | TCP không kiểm tra service/PDB, credential hoặc quyền SQL. | Kiểm tra service, login và query read-only theo từng bước. |
| “`ORA-12514` là user không tồn tại.” | Listener không biết service, chưa tới kiểm tra user. | Xác nhận service/registration/PDB. |
| “`ORA-01017` chắc chắn vì gõ sai password.” | Có thể dùng sai PDB, secret cũ, username khác hoặc auth config khác. | Đối chiếu identity, target và vòng đời secret. |
| “Cấp `DBA` cho ứng dụng sẽ hết lỗi.” | Quyền cao không sửa mạng/service/auth và tạo rủi ro lớn. | Cấp quyền tối thiểu cho đúng thao tác sau khi xác định nguyên nhân. |
| “`ORA-00942` nghĩa là Oracle chưa kết nối.” | Lỗi xuất hiện khi câu SQL tìm/truy cập object thất bại. | Kiểm tra schema/migration/grant. |
| “Driver báo `17002` thì đổi mật khẩu.” | Mã I/O không khẳng định xác thực thất bại. | Đọc nested exception và kiểm tra socket/DNS/TLS. |
| “Cứ retry đến khi được.” | Có thể khóa account, làm quá tải DB hoặc lặp lại thao tác ghi. | Retry có giới hạn, phân loại lỗi, kiểm soát idempotency. |
| “Test từ laptop chạy được thì pod cũng chạy được.” | Mỗi nguồn có mạng, DNS, secret và policy khác nhau. | Thử từ môi trường cùng đường mạng và cấu hình với workload. |
| “Tắt TLS là cách nhanh để hết lỗi cert.” | Làm mất kiểm chứng danh tính server/bảo vệ truyền tải. | Sửa trust/wallet/certificate theo chính sách. |

## 13. Hợp tác xử lý sự cố và thông tin bàn giao

Lỗi kết nối thường cần phối hợp **developer, DBA và operations** vì ba nhóm quan sát những lớp khác nhau:

| Nhóm | Bằng chứng/công việc chính |
|---|---|
| Developer | JDBC URL đã che thông tin nhạy cảm, phiên bản driver, stack/cause chain, connection pool, thời điểm lỗi, hành vi retry, code và migration mới |
| DBA | Trạng thái PDB/service/listener, session/handler/tài nguyên, trạng thái user/privilege, Oracle log/trace và chính sách xác thực |
| Operations | DNS, route, firewall, cổng mạng, secret injection, thay đổi deployment, TLS/certificate, metric/alert, phạm vi tác động và incident coordination |

Một ticket hữu ích có thể viết như sau:

```text
Environment: TEST
Component: inventory-api / build 47
When: 2026-11-14 10:20 +07
Observed error: ORA-01017 (JDBC vendor code 1017)
Target (sanitized): test-db.internal:1521 / inventory_test_service
Scope: 2/4 pods after secret rotation
Network: port reachable from affected pods
Recent changes: credentials rotated; deployment still rolling
Requested action: verify injected secret versions and account status
Do not include: password, token, wallet, unredacted connection URL
```

Thông tin này giúp bắt đầu đúng từ credential/deployment, không đổ lỗi cho listener. Nếu mã chuyển thành `ORA-28000`, báo ngay khả năng account bị khóa và xem xét dừng retry để tránh làm trầm trọng thêm sự cố.

## 14. Ghi nhớ cách đọc mã ORA

Khi gặp thông báo Oracle, hãy theo thứ tự: **đọc mã gốc → nhận diện pha đang lỗi → xác minh đích kết nối → kiểm tra từ nguồn chạy ứng dụng → chuyển sang credential/quyền khi đã có bằng chứng tới bước đó → xác nhận lại bằng session và truy vấn an toàn**.

Điểm phân biệt cốt lõi:

- **`ORA-12154`, `ORA-12541`, `ORA-12514`, timeout:** ưu tiên điều tra cấu hình Oracle Net, đường mạng, listener/service và tài nguyên kết nối.
- **`ORA-01017`, `ORA-28000`, `ORA-28001`:** ưu tiên điều tra danh tính, secret, trạng thái account và vòng đời mật khẩu.
- **`ORA-01045`, `ORA-01031`, `ORA-00942`:** điều tra quyền mở session hoặc quyền/schema khi thực thi SQL.
- **`ORA-17002`, lỗi TLS, `ORA-03113` và lỗi driver tổng quát:** cần đọc exception/cause chain và bối cảnh trước khi kết luận nguyên nhân.

Nhận diện đúng lớp lỗi giúp người xử lý chọn phép thử có giá trị, giảm việc đổi cấu hình tùy tiện và bảo vệ Oracle production khỏi các thao tác khắc phục thiếu căn cứ.
