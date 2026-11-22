# Kết nối TCP/IP, Unix socket và named pipe theo nền tảng

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Để thực hành được các nội dung đó, trước hết cần hiểu chương trình khách giao tiếp với MySQL Server qua cơ chế nào. MySQL hỗ trợ TCP/IP trên các hệ điều hành, Unix domain socket trên Unix/Linux và named pipe trên Windows. Chọn đúng giao thức giúp kết nối hoạt động ổn định, dễ chẩn đoán và đáp ứng yêu cầu bảo mật của môi trường.

## 1. Ba cơ chế kết nối

Khi client mở kết nối, nó cần xác định máy chủ, giao thức, địa chỉ hoặc tên endpoint và thông tin xác thực. MySQL sau đó tiếp nhận kết nối, thực hiện bắt tay giao thức, xác thực tài khoản và kiểm tra quyền. Giao thức truyền tải chỉ quyết định dữ liệu đi từ client đến server bằng đường nào; nó không thay thế cơ chế tài khoản và phân quyền của MySQL.

| Cơ chế | Nền tảng | Địa chỉ kết nối | Phạm vi thường dùng | Đặc điểm |
|---|---|---|---|---|
| TCP/IP | Windows, Linux, Unix, macOS | Host/IP và port, thường là `3306` | Cùng máy hoặc qua mạng | Phù hợp ứng dụng máy khách/máy chủ và kết nối từ xa |
| Unix domain socket | Linux, Unix, macOS | Đường dẫn file socket | Các tiến trình trên cùng máy | Không dùng IP hay TCP port; quyền truy cập phụ thuộc hệ điều hành |
| Named pipe | Windows | Tên pipe, mặc định thường là `MySQL` | Chủ yếu là các tiến trình trên máy Windows chạy MySQL | Cần bật named pipe ở máy chủ và client chọn đúng protocol |

TCP/IP là lựa chọn phổ biến cho ứng dụng backend, kể cả khi ứng dụng và MySQL nằm trên cùng máy. Unix socket thường thuận tiện cho công cụ dòng lệnh trên Linux. Named pipe là một cơ chế IPC dành cho Windows. Không thể dùng đường dẫn Unix socket trên Windows hoặc yêu cầu client Linux mở named pipe của Windows như một file cục bộ.

## 2. Kết nối bằng TCP/IP

### 2.1. Địa chỉ và cổng

TCP/IP sử dụng địa chỉ mạng và cổng. Với giao thức MySQL cổ điển, cổng mặc định thường là `3306`; instance có thể được cấu hình dùng cổng khác. Client phải biết đúng host và port:

```bash
mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=app_user --password
```

`--protocol=TCP` buộc client sử dụng TCP. `--host` có thể là địa chỉ IP hoặc tên DNS. `127.0.0.1` là loopback IPv4, chỉ trỏ về chính máy đang chạy client; khi kết nối từ máy khác, hãy thay bằng hostname hoặc địa chỉ máy chủ có thể định tuyến tới được. Nếu máy chủ lắng nghe trên IPv6, client có thể dùng địa chỉ IPv6 như `::1` cho loopback hoặc địa chỉ IPv6 của máy chủ.

Trên Unix, `localhost` thường khiến client chọn Unix socket thay vì TCP. Vì vậy, khi cần kiểm tra TCP trên cùng máy, dùng `127.0.0.1` cùng `--protocol=TCP`. Khi cần loại bỏ mọi suy đoán về giao thức mặc định, hãy chỉ định `--protocol` rõ ràng.

Không nhập mật khẩu trực tiếp vào câu lệnh. Dùng `--password` hoặc `-p` không kèm giá trị để client hỏi mật khẩu tương tác; cách này tránh để mật khẩu xuất hiện trong lịch sử shell hoặc danh sách tiến trình.

### 2.2. Cấu hình máy chủ

Các tùy chọn TCP quan trọng nằm trong nhóm `[mysqld]` của file cấu hình:

```ini
[mysqld]
port=3306
bind-address=127.0.0.1
```

- `port` xác định cổng TCP mà MySQL Server sử dụng cho giao thức SQL cổ điển.
- `bind-address` xác định địa chỉ mạng mà máy chủ lắng nghe. `127.0.0.1` giới hạn kết nối IPv4 vào máy cục bộ; một địa chỉ IP cụ thể giới hạn vào giao diện tương ứng; `0.0.0.0` lắng nghe trên mọi giao diện IPv4.
- `skip-networking` khi được bật sẽ tắt kết nối TCP/IP. Client TCP sẽ không kết nối được dù máy chủ có thể vẫn nhận kết nối bằng cơ chế cục bộ khác.

Nếu ứng dụng ở máy khác cần truy cập MySQL, máy chủ phải lắng nghe trên giao diện có thể truy cập từ ứng dụng. Đồng thời, firewall hoặc security group phải cho phép đúng nguồn truy cập đến đúng cổng. Không nên mở cổng MySQL cho toàn bộ Internet để giải quyết lỗi kết nối.

Thay đổi `port`, `bind-address` hoặc `skip-networking` thường cần khởi động lại dịch vụ để có hiệu lực. Sau khi áp dụng, kiểm tra lại giá trị runtime bằng SQL:

```sql
SHOW GLOBAL VARIABLES WHERE Variable_name IN
  ('port', 'bind_address', 'skip_networking');
```

### 2.3. Bảo vệ kết nối TCP

Khi dữ liệu đi qua mạng, cần cân nhắc mã hóa TLS và xác minh danh tính máy chủ. Với MySQL client hiện đại, có thể yêu cầu xác minh chứng chỉ và hostname:

```bash
mysql --protocol=TCP \
  --host=db.example.internal \
  --port=3306 \
  --user=app_user \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/path/to/ca.pem
```

Đường dẫn CA là ví dụ và phải trỏ đến chứng chỉ CA đáng tin cậy của môi trường. `VERIFY_IDENTITY` yêu cầu TLS, xác minh chuỗi chứng chỉ và tên máy chủ khớp với chứng chỉ. Chỉ bật mã hóa mà không xác minh danh tính máy chủ vẫn có thể để client kết nối nhầm endpoint. Phía server có thể áp dụng chính sách yêu cầu kết nối an toàn bằng biến `require_secure_transport`, tùy phiên bản và chính sách triển khai.

TLS không thay thế việc giới hạn mạng, xác thực tài khoản và cấp quyền tối thiểu. Hãy dùng tài khoản ứng dụng riêng, giới hạn host được phép đăng nhập và chỉ cấp quyền trên schema hoặc đối tượng mà ứng dụng cần.

### 2.4. TCP trong ứng dụng Java

Ứng dụng Java sử dụng MySQL Connector/J thường kết nối bằng JDBC URL qua TCP/IP. Ví dụ:

```java
String url = "jdbc:mysql://db.example.internal:3306/sales";
Connection connection = DriverManager.getConnection(url, user, password);
```

Trong môi trường yêu cầu TLS, cấu hình `sslMode=VERIFY_IDENTITY` và trust material theo hướng dẫn của phiên bản Connector/J đang dùng. Không hard-code mật khẩu trong mã nguồn; đọc bí mật từ cơ chế quản lý cấu hình hoặc secret của môi trường triển khai. Nếu ứng dụng Java chạy cùng máy với MySQL trên Linux, TCP loopback vẫn là cách kết nối trực tiếp phổ biến và được Connector/J hỗ trợ thông qua JDBC URL tiêu chuẩn.

## 3. Kết nối bằng Unix domain socket

### 3.1. Cách hoạt động

Unix domain socket là cơ chế giao tiếp liên tiến trình của các hệ điều hành Unix-like. Thay vì gửi gói tin qua địa chỉ IP và cổng TCP, client mở một endpoint dạng file socket trên cùng máy với MySQL Server. Đường dẫn thường gặp là `/run/mysqld/mysqld.sock`, nhưng vị trí thực tế phụ thuộc bản phân phối, gói cài đặt và cấu hình instance.

Socket phù hợp với client chạy cục bộ như MySQL CLI, script quản trị hoặc dịch vụ cùng máy có thư viện hỗ trợ Unix socket. Nó không phải endpoint mạng để client ở máy khác truy cập trực tiếp. Nếu cần kết nối giữa hai máy, hãy dùng TCP/IP hoặc một giải pháp tunnel phù hợp.

### 3.2. Cấu hình và kết nối

Máy chủ và client cần sử dụng cùng đường dẫn socket. Ví dụ trên Linux:

```ini
[mysqld]
socket=/run/mysqld/mysqld.sock

[client]
socket=/run/mysqld/mysqld.sock
```

Kết nối bằng MySQL CLI:

```bash
mysql --protocol=SOCKET \
  --socket=/run/mysqld/mysqld.sock \
  --user=app_user \
  --password
```

Để xem đường dẫn socket máy chủ đang sử dụng:

```sql
SHOW GLOBAL VARIABLES LIKE 'socket';
```

Client cũng có thể nhận giá trị mặc định từ nhóm `[client]` trong option file. Khi cần chẩn đoán, truyền `--protocol=SOCKET` và `--socket` tường minh để biết chắc client đang thử endpoint nào.

### 3.3. Quyền truy cập socket

Quyền truy cập socket chịu ảnh hưởng của quyền trên file socket và các thư mục cha. Tài khoản hệ điều hành chạy client cần có quyền đi qua thư mục và truy cập endpoint; tài khoản dịch vụ MySQL cần quyền tạo socket tại thư mục đích. Một số hệ thống tạo socket trong `/run`, là vùng dữ liệu runtime có thể được tạo lại sau khi khởi động máy.

Quyền hệ điều hành và quyền MySQL là hai lớp riêng. Có quyền mở socket không đồng nghĩa được phép đăng nhập vào database; MySQL vẫn xác thực tài khoản và kiểm tra grants. Ngược lại, tài khoản MySQL có mật khẩu đúng cũng không thể kết nối nếu tiến trình không mở được file socket.

Không xóa file socket khi máy chủ còn chạy. Nếu cần thay đường dẫn, hãy cập nhật cấu hình của cả server và client, kiểm tra thư mục đích cùng quyền sở hữu, sau đó khởi động lại dịch vụ theo quy trình quản trị.

## 4. Kết nối bằng named pipe trên Windows

### 4.1. Cơ chế named pipe

Named pipe là cơ chế giao tiếp giữa các tiến trình của Windows. MySQL Server chỉ chấp nhận kết nối kiểu này khi tính năng named pipe được bật. Tên pipe mặc định thường là `MySQL`; giá trị thực tế có thể được cấu hình. Named pipe thường hữu ích cho client chạy trên cùng máy Windows với MySQL Server và không cần mở cổng TCP cho luồng kết nối đó.

Named pipe vẫn đi qua bước xác thực tài khoản MySQL. ACL của Windows kiểm soát tiến trình nào có thể mở pipe, còn MySQL kiểm soát user, host và quyền trên database. Hai lớp quyền này cần được cấu hình phù hợp.

### 4.2. Bật named pipe ở máy chủ

Trong file cấu hình MySQL trên Windows, đặt tùy chọn trong nhóm `[mysqld]`:

```ini
[mysqld]
enable-named-pipe
socket=MySQL
```

`enable-named-pipe` bật giao thức named pipe. Tùy chọn `socket` trong ngữ cảnh Windows chỉ tên pipe được sử dụng; tên mặc định thường là `MySQL`. Nếu thay tên, client cũng phải dùng đúng tên đó. Thay đổi cấu hình này cần khởi động lại MySQL Server.

MySQL có tùy chọn `named_pipe_full_access_group` để chỉ định nhóm Windows được cấp quyền truy cập đầy đủ vào named pipe. Khi triển khai trong môi trường nhiều người dùng, cần xem xét nhóm được chỉ định và chính sách ACL theo nguyên tắc quyền tối thiểu. Không thêm tùy chọn này theo một tên nhóm mẫu mà chưa kiểm tra tên nhóm thực tế trên máy.

### 4.3. Kết nối từ client Windows

Client phải chọn protocol `PIPE` và chỉ định tên pipe nếu không dùng giá trị mặc định:

```powershell
mysql --protocol=PIPE --socket=MySQL --user=app_user --password
```

Nếu server và client dùng tên pipe khác nhau, client sẽ không mở được endpoint dù dịch vụ MySQL đang chạy. Nếu named pipe chưa được bật ở server, yêu cầu kết nối `PIPE` cũng thất bại. Hãy kiểm tra file cấu hình server, trạng thái dịch vụ, tên pipe và quyền Windows trước khi thay đổi tài khoản MySQL.

Windows còn hỗ trợ cơ chế shared memory trong một số cấu hình MySQL. Đây là một giao thức cục bộ khác named pipe; server cần bật tùy chọn shared memory và client phải chọn protocol `MEMORY`. Khi bài toán yêu cầu named pipe, không nhầm `--protocol=PIPE` với `--protocol=MEMORY`.

## 5. Chọn giao thức phù hợp

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Ứng dụng Java hoặc dịch vụ backend kết nối MySQL qua mạng | TCP/IP | JDBC URL tiêu chuẩn hỗ trợ host và port; dễ triển khai trên nhiều máy |
| MySQL CLI chạy trên cùng máy Linux | Unix socket hoặc TCP loopback | Socket tiện cho quản trị cục bộ; TCP hữu ích khi cần kiểm tra đúng đường mạng |
| Ứng dụng chạy trên máy khác | TCP/IP có TLS | Socket file không phải endpoint truy cập trực tiếp qua mạng; TCP hỗ trợ kết nối từ xa |
| Công cụ Windows cần kết nối cục bộ qua named pipe | Named pipe | IPC của Windows, không cần dùng cổng TCP cho kết nối đó |
| Cần chuẩn hóa cách chẩn đoán trên mọi hệ điều hành | TCP/IP được chỉ định tường minh | Cùng mô hình host/port và dễ kiểm tra bằng công cụ mạng |

Trước khi chọn, hãy trả lời ba câu hỏi: client chạy trên hệ điều hành nào, client ở cùng máy hay máy khác, và thư viện kết nối có hỗ trợ giao thức đó hay không. Với ứng dụng Java sử dụng Connector/J tiêu chuẩn, hãy ưu tiên JDBC qua TCP/IP; không giả định rằng URL JDBC có thể tự dùng Unix socket hoặc Windows named pipe.

## 6. Xác định giao thức client thực sự sử dụng

Đừng chỉ dựa vào hostname trong cấu hình. Một số giá trị mặc định có thể khiến client chọn giao thức khác dự kiến. Trên Unix, `localhost` thường dùng socket; `127.0.0.1` với `--protocol=TCP` buộc kết nối TCP. Trên Windows, hãy chỉ định `--protocol=TCP` hoặc `--protocol=PIPE` rõ ràng khi kiểm tra.

Ví dụ các lệnh tương ứng:

```bash
# TCP/IP
mysql --protocol=TCP --host=127.0.0.1 --port=3306 -u app_user -p

# Unix domain socket (Linux/Unix)
mysql --protocol=SOCKET --socket=/run/mysqld/mysqld.sock -u app_user -p
```

```powershell
# TCP/IP trên Windows
mysql --protocol=TCP --host=127.0.0.1 --port=3306 -u app_user -p

# Named pipe trên Windows
mysql --protocol=PIPE --socket=MySQL -u app_user -p
```

Sau khi đăng nhập, lệnh `status` trong MySQL CLI hiển thị thông tin phiên, bao gồm loại kết nối mà client đang sử dụng. Có thể chạy:

```sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('port', 'socket', 'bind_address');
```

`status` giúp xác nhận transport phía client; các biến hệ thống cho biết cấu hình server. `Ssl_cipher` có giá trị không rỗng khi phiên đang dùng TLS. Không suy luận rằng một kết nối TCP luôn được mã hóa; phải kiểm tra cấu hình và trạng thái TLS thực tế.

## 7. Chẩn đoán lỗi kết nối theo từng tầng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| TCP báo `Connection refused` | Không có tiến trình lắng nghe tại địa chỉ/cổng, dịch vụ dừng hoặc port sai | Kiểm tra trạng thái MySQL, `@@port`, `@@bind_address` và danh sách cổng lắng nghe |
| TCP timeout | Firewall, security group, định tuyến hoặc DNS không đúng | Kiểm tra phân giải tên, đường mạng, rule firewall và thử từ đúng máy client |
| TCP kết nối được nhưng `Access denied` | Sai mật khẩu, tài khoản không khớp host hoặc thiếu quyền | Kiểm tra user, host được phép, phương thức xác thực và grants |
| Socket báo `No such file or directory` | Client dùng sai đường dẫn hoặc server chưa tạo socket | Đọc `@@socket`, kiểm tra file socket và error log |
| Socket báo `Permission denied` | Quyền file socket hoặc thư mục cha không phù hợp | Kiểm tra user/group, quyền thư mục và chính sách bảo mật hệ điều hành |
| Named pipe không tồn tại hoặc không mở được | Server chưa bật named pipe, pipe name sai hoặc dịch vụ chưa sẵn sàng | Kiểm tra `enable-named-pipe`, tên `socket`, trạng thái server và cấu hình client |
| Named pipe bị từ chối truy cập | ACL hoặc nhóm Windows không cấp quyền mở pipe | Kiểm tra ACL và `named_pipe_full_access_group` cùng danh tính tiến trình client |

### 7.1. Công cụ kiểm tra TCP

Trên Linux, có thể xem cổng TCP đang lắng nghe:

```bash
ss -ltnp
```

Để lọc cổng mặc định:

```bash
ss -ltnp 'sport = :3306'
```

Trên Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 3306 -State Listen
Test-NetConnection -ComputerName db.example.internal -Port 3306
```

`Get-NetTCPConnection` kiểm tra socket TCP ở máy đang chạy lệnh; `Test-NetConnection` kiểm tra khả năng tiếp cận host/port từ máy client. Các công cụ này không xác minh mật khẩu hoặc quyền MySQL.

### 7.2. Công cụ kiểm tra Unix socket

Trên Linux, dùng:

```bash
ss -lxnp
ls -l /run/mysqld/mysqld.sock
```

Tên và đường dẫn phải khớp với `@@socket`. Nếu socket không tồn tại, xem trạng thái dịch vụ và error log để xác định vì sao server chưa tạo endpoint. Nếu socket tồn tại nhưng bị từ chối, kiểm tra quyền truy cập trên toàn bộ đường dẫn, không chỉ file cuối.

### 7.3. Kiểm tra log và runtime

Khi client không kết nối được, đọc error log của MySQL và log dịch vụ để tìm lỗi lúc khởi động hoặc lúc tạo endpoint. Đường dẫn error log có thể lấy bằng:

```sql
SHOW GLOBAL VARIABLES LIKE 'log_error';
```

Khi đã có phiên SQL, đối chiếu cấu hình runtime:

```sql
SELECT @@hostname AS server_host,
       @@port AS tcp_port,
       @@bind_address AS bind_address,
       @@socket AS local_endpoint,
       @@skip_networking AS tcp_disabled;
```

Lưu ý `@@socket` trên Unix thường là đường dẫn Unix socket; trên Windows, khi named pipe được bật, giá trị này có thể biểu thị tên pipe. Hãy đọc giá trị trong đúng ngữ cảnh hệ điều hành.

## 8. Bài thực hành: so sánh các giao thức kết nối

Thực hiện trên instance phát triển hoặc môi trường lab mà bạn được phép truy cập. Dùng tài khoản đã được cấp và không thay đổi cấu hình máy chủ dùng chung khi chưa có kế hoạch.

**Bước 1 — Ghi nhận cấu hình server.** Kết nối bằng một phương thức đang hoạt động, chạy truy vấn lấy `port`, `bind_address`, `socket`, `skip_networking` và `hostname`. Ghi lại hệ điều hành, phiên bản MySQL và đường dẫn error log.

**Bước 2 — Thử TCP rõ ràng.** Trên máy có MySQL, kết nối đến `127.0.0.1` bằng `--protocol=TCP` và cổng runtime. Nếu thử từ máy khác, dùng hostname/IP máy chủ và xác minh firewall cho phép nguồn client.

**Bước 3 — Thử IPC phù hợp hệ điều hành.** Trên Linux/Unix, kết nối bằng `--protocol=SOCKET` và đúng `@@socket`. Trên Windows, chỉ thử named pipe nếu server đã bật `enable-named-pipe`; dùng `--protocol=PIPE` và đúng tên pipe. Không cố chạy lệnh Unix socket trên Windows.

**Bước 4 — Xác minh transport.** Sau mỗi lần đăng nhập, chạy `status` trong MySQL CLI và ghi lại loại kết nối. Đối chiếu với giao thức đã chỉ định trong câu lệnh.

**Bước 5 — Phân loại lỗi.** Nếu một phương thức thất bại, xác định lỗi thuộc tầng endpoint, mạng/quyền hệ điều hành hay xác thực/quyền MySQL. Dùng công cụ hệ điều hành và error log để tìm bằng chứng trước khi thay đổi cấu hình.

**Kết quả cần đạt:** giải thích được vì sao TCP/IP dùng host/port, Unix socket dùng đường dẫn file, named pipe dùng tên pipe trên Windows; biết chọn protocol tường minh, xác minh transport thực tế và khoanh vùng lỗi theo từng tầng.

## 9. Những nguyên tắc cần nhớ

- TCP/IP là lựa chọn đa nền tảng và phù hợp kết nối từ xa; kiểm soát `bind-address`, firewall, TLS và tài khoản MySQL.
- Unix socket là IPC cục bộ trên Unix-like; server và client phải thống nhất đường dẫn, đồng thời bảo đảm quyền hệ điều hành.
- Named pipe là IPC của Windows; server phải bật `enable-named-pipe`, client chọn `PIPE` và hai bên dùng cùng tên pipe.
- Giao thức truyền tải không cấp quyền database. Sau khi mở kết nối, MySQL vẫn xác thực tài khoản và kiểm tra grants.
- Khi chẩn đoán, chỉ định `--protocol` rõ ràng và kiểm tra `status` để tránh nhầm giao thức mặc định.
- Với ứng dụng Java dùng MySQL Connector/J tiêu chuẩn, dùng TCP/IP qua JDBC URL và cấu hình TLS khi kết nối qua mạng.

Hiểu cách MySQL kết nối theo từng nền tảng giúp lựa chọn đúng endpoint cho client, triển khai quyền truy cập phù hợp và xác định nhanh lỗi nằm ở mạng, IPC của hệ điều hành hay ở lớp xác thực MySQL.
