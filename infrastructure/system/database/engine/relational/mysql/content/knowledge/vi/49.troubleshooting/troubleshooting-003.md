# Access denied và kiểm tra user@host, plugin, TLS, mật khẩu

Lỗi `Access denied for user ...` khi kết nối MySQL thường xuất hiện trước khi ứng dụng chạy được câu SQL. Nguyên nhân có thể là password không đúng, account không khớp host client, MySQL chọn một account khác với dự kiến, authentication plugin không tương thích, TLS không đáp ứng yêu cầu hoặc account bị khóa/hết hạn. Vì nhiều nguyên nhân tạo ra thông báo gần giống nhau, cách xử lý hiệu quả là kiểm tra lần lượt danh tính kết nối, account `user@host`, plugin, kênh bảo mật và thông tin đăng nhập.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung xử lý lỗi đăng nhập trong MySQL và các ứng dụng kết nối từ xa. Nội dung kết nối quản trị user/privilege, Connector/J, TLS và vận hành cơ sở dữ liệu quan hệ.

Sau bài học, bạn có thể:

- Phân biệt lỗi xác thực với lỗi quyền truy cập database/table.
- Xác định username và host thực tế mà MySQL nhìn thấy.
- Tìm account `user@host` được chọn và phát hiện account bị shadow.
- Kiểm tra authentication plugin, trạng thái khóa và hết hạn password.
- Xác minh TLS, RSA public key và tương thích driver.
- Kiểm tra quyền SQL và cấu hình host resolution.
- Xoay vòng password an toàn và xử lý host bị chặn.
- Xây dựng checklist điều tra có thể lặp lại mà không làm lộ secret.

## 1. Phân biệt các lỗi kết nối phổ biến

Không phải mọi lỗi kết nối đều là `Access denied`. Đọc mã lỗi, thông báo đầy đủ và giai đoạn xảy ra lỗi trước khi thay đổi account.

| Lỗi thường gặp | Ý nghĩa khái quát | Hướng kiểm tra đầu tiên |
|---|---|---|
| `1045` / `ER_ACCESS_DENIED_ERROR` | Server từ chối xác thực account hoặc thông tin đăng nhập | Username, host, account match, plugin, password, TLS và trạng thái account |
| `1130` / `ER_HOST_NOT_PRIVILEGED` | Host client không được phép kết nối theo account/host policy | Host thực tế, account Host và cấu hình mạng |
| `1129` / `ER_HOST_IS_BLOCKED` | Host bị chặn do quá nhiều lỗi kết nối | Network errors, `max_connect_errors` và host cache |
| `1251` hoặc lỗi plugin tương tự | Client không hỗ trợ giao thức/plugin xác thực cần thiết | Phiên bản MySQL client/Connector/J và plugin của account |
| `2059` / lỗi không nạp được authentication plugin | Client không tìm thấy hoặc không nạp được plugin cần thiết | Driver, thư viện plugin và phiên bản client |
| Lỗi TLS/SSL handshake hoặc certificate | Kênh TLS không thiết lập được hoặc chứng thư không được tin cậy | CA, certificate chain, hostname, TLS version và truststore |
| Đăng nhập thành công nhưng `SELECT` bị từ chối | Xác thực đã thành công, quyền SQL chưa đủ | `SHOW GRANTS`, role và đối tượng truy cập |

Mã lỗi và câu chữ cụ thể có thể khác theo phiên bản server, connector và client. Lưu nguyên thông báo lỗi, SQLState và vendor error code để điều tra; không chỉ lưu dòng `Access denied` đã bị rút gọn.

## 2. Đọc thông báo Access denied đúng cách

Một thông báo phổ biến có dạng:

```text
ERROR 1045 (28000): Access denied for user 'shop_app'@'client.example'
(using password: YES)
```

Thông báo thường cho biết:

- Username client gửi lên.
- Host hoặc địa chỉ client mà server ghi nhận trong quá trình kết nối.
- Client có gửi password hay không (`YES`/`NO`).

`using password: YES` chỉ có nghĩa client đã gửi thông tin password; nó không chứng minh password đúng. `NO` thường cho thấy ứng dụng không gửi password hoặc cấu hình credential chưa được truyền tới driver.

Host trong thông báo là manh mối quan trọng nhưng không nên tự động coi nó là account row đã được chọn. MySQL thực hiện account matching theo các cột `Host` và `User`; cần kiểm tra các account ứng viên và xác nhận bằng một kết nối thành công tương đương nếu có thể.

## 3. Xác định MySQL nhìn thấy client từ đâu

Ứng dụng có thể kết nối qua nhiều lớp mạng: container, Kubernetes pod, NAT gateway, proxy, bastion hoặc load balancer. Host mà MySQL nhìn thấy có thể khác hostname của máy chạy ứng dụng.

Hãy ghi nhận:

- Hostname/IP trong JDBC URL hoặc lệnh client.
- IP nguồn thực tế sau NAT hoặc proxy.
- MySQL endpoint đang nhận kết nối: primary, replica, proxy hay node khác.
- DNS forward/reverse và cấu hình `skip_name_resolve`.
- Network policy, firewall, security group và cổng TCP.

Nếu có thể đăng nhập bằng một account quản trị từ cùng đường mạng, chạy:

```sql
SELECT
    USER() AS presented_identity,
    CURRENT_USER() AS matched_account,
    @@hostname AS server_hostname,
    @@port AS server_port,
    @@skip_name_resolve AS skip_name_resolve;
```

`USER()` trả về danh tính client trình bày và host client được server nhận diện. `CURRENT_USER()` trả về account MySQL thực tế được dùng để kiểm tra quyền. Hai giá trị có thể khác nhau do account matching.

Nếu đăng nhập thất bại hoàn toàn, không thể chạy truy vấn này bằng chính session lỗi. Khi đó hãy dùng thông tin lỗi, log server, account metadata và một kết nối quản trị độc lập từ cùng mạng để điều tra.

### 3.1. NAT, container và proxy

Ví dụ, ứng dụng chạy trong container với địa chỉ nội bộ `172.18.0.5`, nhưng MySQL chỉ nhìn thấy địa chỉ gateway `10.20.1.15` sau NAT. Account giới hạn host theo `172.18.0.5` sẽ không khớp. Tương tự, khi ứng dụng đi qua proxy TCP, server có thể nhìn thấy địa chỉ proxy thay vì IP pod.

Không sửa account bằng cách mở rộng Host thành `%` ngay khi gặp lỗi. Trước hết xác định IP nguồn mà server thực sự nhìn thấy, rồi chọn host pattern hẹp nhất phù hợp với topology.

### 3.2. `skip_name_resolve`

Kiểm tra:

```sql
SHOW VARIABLES LIKE 'skip_name_resolve';
```

Khi `skip_name_resolve=ON`, MySQL không thực hiện DNS lookup để phân giải hostname client trong quá trình account matching; các account Host cần dùng địa chỉ IP hoặc dạng host được hỗ trợ không phụ thuộc DNS. Account `localhost` vẫn có ý nghĩa riêng cho kết nối local.

Nếu account được khai báo bằng hostname nhưng server chạy với `skip_name_resolve=ON`, account có thể không khớp như mong đợi. Trước khi đổi account, kiểm tra đúng giá trị biến trên instance đích và host pattern đang có.

## 4. Cách MySQL chọn account `user@host`

MySQL account gồm hai phần: `User` và `Host`. Ví dụ:

```sql
'shop_app'@'localhost'
'shop_app'@'10.20.1.15'
'shop_app'@'10.20.%'
'shop_app'@'%'
```

Đây là các account khác nhau. Password, authentication plugin, trạng thái khóa và quyền có thể khác nhau giữa từng account dù username giống nhau.

MySQL sắp xếp các dòng grant theo mức độ cụ thể của Host. Host cụ thể hơn được xét trước; nếu có account anonymous (`User` rỗng) với Host cụ thể hơn account username có Host rộng hơn, account anonymous đó có thể được chọn trước. Vì vậy, tồn tại một account `'shop_app'@'%'` không bảo đảm mọi client mang username `shop_app` đều sử dụng account này.

### 4.1. Liệt kê các account ứng viên

Quản trị viên có thể kiểm tra các account cùng username và anonymous account:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked,
    password_expired
FROM mysql.user
WHERE User IN ('shop_app', '')
ORDER BY Host, User;
```

Truy cập `mysql.user` cần quyền quản trị phù hợp và cấu trúc metadata có thể thay đổi theo phiên bản. Không truy vấn hoặc xuất `authentication_string` ra log/ticket; trường đó chứa dữ liệu xác thực nhạy cảm.

Kiểm tra xem có account trùng username nhưng Host khác nhau, account anonymous hoặc account cũ không còn dùng. Đối chiếu từng account với IP nguồn và quy tắc host matching.

### 4.2. Ví dụ account bị shadow

Giả sử tồn tại:

```sql
CREATE USER 'shop_app'@'%' IDENTIFIED BY '<secret-a>';
CREATE USER ''@'10.20.1.15' IDENTIFIED BY '<secret-b>';
```

Client tại `10.20.1.15` đăng nhập với username `shop_app`. Account anonymous có Host cụ thể hơn account named có Host `%`, vì vậy MySQL có thể chọn account anonymous để xác thực. Nếu password hoặc plugin của account anonymous khác, client sẽ nhận lỗi dù password của `'shop_app'@'%'` là đúng.

Ví dụ chỉ nhằm giải thích quy tắc matching. Không tạo anonymous account trong production để thử. Nếu phát hiện account không cần thiết, đánh giá tác động rồi khóa hoặc xóa theo quy trình quản trị.

### 4.3. Xác nhận account sau khi đăng nhập thành công

Khi kết nối được, chạy:

```sql
SELECT USER(), CURRENT_USER();
SHOW GRANTS;
```

`CURRENT_USER()` là bằng chứng trực tiếp cho biết account row nào được dùng. `SHOW GRANTS` cho biết quyền áp dụng cho account hiện tại. Lưu kết quả không chứa secret vào báo cáo điều tra.

## 5. Kiểm tra authentication plugin

Một username/password đúng vẫn có thể thất bại nếu client không hỗ trợ plugin của account hoặc plugin cần điều kiện bảo mật chưa được đáp ứng.

Các plugin thường gặp:

| Plugin | Đặc điểm | Khuyến nghị vận hành |
|---|---|---|
| `caching_sha2_password` | Plugin mặc định cho account mới trên MySQL 8.0; hỗ trợ fast/full authentication | Ưu tiên với client/driver hiện đại |
| `sha256_password` | Dựa trên SHA-256, có thể dùng TLS hoặc RSA | Chỉ dùng khi có yêu cầu tương thích rõ ràng |
| `mysql_native_password` | Plugin cũ, dùng cho tương thích legacy | Lập kế hoạch thay thế; không chọn cho ứng dụng mới |
| Plugin bên thứ ba | Phụ thuộc server/client plugin tương ứng | Xác nhận plugin được cài, hỗ trợ và cấu hình trên cả hai phía |

Kiểm tra plugin của account:

```sql
SELECT User, Host, plugin, account_locked
FROM mysql.user
WHERE User = 'shop_app';
```

### 5.1. `caching_sha2_password` và tương thích client

MySQL 8.0 sử dụng `caching_sha2_password` làm plugin mặc định cho account mới. Connector/J 8.0.9 trở lên hỗ trợ plugin này. Nếu ứng dụng dùng Connector/J cũ, driver có thể không hoàn tất handshake hoặc không tải được plugin.

Kiểm tra driver thực sự được ứng dụng nạp, không chỉ dependency khai báo trong `pom.xml` hoặc Gradle. Có thể nhiều phiên bản connector cùng tồn tại trong classpath hoặc container image vẫn chứa JAR cũ.

Với full authentication, `caching_sha2_password` cần kênh an toàn như TLS hoặc RSA public key exchange. Nếu TLS không được bật, client phải có cách lấy public key đáng tin cậy.

### 5.2. Vòng đời `mysql_native_password`

`mysql_native_password` đã deprecated từ MySQL 8.0.34, bị vô hiệu hóa mặc định trong MySQL 8.4 và bị loại bỏ trong MySQL 9.0. Một ứng dụng chỉ kết nối được khi account dùng plugin cũ có thể đang phụ thuộc driver hoặc thư viện quá cũ.

Giải pháp ưu tiên là nâng cấp Connector/J hoặc client library, sau đó chuyển account sang plugin hiện đại trong một đợt thay đổi có kiểm thử. Không bật lại plugin legacy trên server mới chỉ để che lỗi tương thích mà chưa đánh giá rủi ro và lộ trình thay thế.

## 6. Kiểm tra TLS và RSA public key

### 6.1. Account có yêu cầu SSL/TLS không?

Kiểm tra định nghĩa account bằng:

```sql
SHOW CREATE USER 'shop_app'@'10.20.1.15';
```

Lệnh có thể hiển thị metadata xác thực, vì vậy chỉ người có quyền phù hợp mới được chạy và không đưa toàn bộ output vào ticket/log. Xem các yêu cầu như `REQUIRE SSL`, `REQUIRE X509`, issuer hoặc subject.

Nếu account có `REQUIRE SSL`, client phải thiết lập TLS. Nếu server bật `require_secure_transport=ON`, các kết nối không an toàn có thể bị từ chối ở cấp server, kể cả khi account không khai báo riêng `REQUIRE SSL`.

Kiểm tra:

```sql
SHOW VARIABLES LIKE 'require_secure_transport';
SHOW VARIABLES LIKE 'have_ssl';
```

### 6.2. Ưu tiên TLS với xác minh hostname

Với MySQL command-line client, ví dụ:

```bash
mysql \
  --host=mysql.example.internal \
  --port=3306 \
  --user=shop_app \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/mysql/certs/ca.pem \
  shop
```

Tùy client/version, cách chỉ định CA và tùy chọn TLS có thể khác. `--password` không kèm giá trị yêu cầu client nhập tương tác, tránh đặt password trực tiếp trong command line.

Với Connector/J hiện đại:

```text
jdbc:mysql://mysql.example.internal:3306/shop?sslMode=VERIFY_IDENTITY
```

Client cần tin cậy CA cấp chứng thư server và hostname dùng trong URL phải khớp SAN của chứng thư. `sslMode=REQUIRED` chỉ yêu cầu mã hóa TLS; `VERIFY_IDENTITY` vừa xác minh CA vừa xác minh danh tính hostname.

### 6.3. Xác nhận TLS trên session đã kết nối

```sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
SHOW SESSION STATUS LIKE 'Ssl_version';
```

`Ssl_cipher` có giá trị cho biết session đang dùng TLS cipher. Tuy nhiên, truy vấn này không chứng minh client đã bật hostname verification; phải kiểm tra cấu hình client và kết quả xác minh chứng thư.

### 6.4. RSA khi không dùng TLS

Nếu dùng `caching_sha2_password` hoặc `sha256_password` trong full authentication mà không có TLS, client cần RSA public key để mã hóa password. Với Connector/J, có thể chỉ định public key file:

```text
jdbc:mysql://mysql.example.internal:3306/shop?sslMode=DISABLED&serverRSAPublicKeyFile=/etc/shop-app/mysql/server-rsa-public.pem
```

Đây là cấu hình minh họa cho môi trường kiểm soát; không khuyến nghị tắt TLS trên mạng không tin cậy. Public key phải được phân phối qua kênh xác thực và kiểm tra tính toàn vẹn. Không chia sẻ private key của server.

`allowPublicKeyRetrieval=true` cho phép driver yêu cầu server cung cấp public key. Nếu kết nối không được bảo vệ và xác thực, key có thể bị thay thế bởi kẻ trung gian. Không bật thuộc tính này như cách sửa nhanh lỗi `Public Key Retrieval is not allowed`; ưu tiên TLS `VERIFY_IDENTITY` hoặc public key file đã được xác minh.

## 7. Kiểm tra password, trạng thái account và chính sách xác thực

Sau khi xác nhận đúng account row và plugin, kiểm tra password và trạng thái account.

Các nguyên nhân thường gặp:

- Ứng dụng dùng secret cũ sau khi password đã xoay vòng.
- Secret có ký tự đặc biệt bị cắt, escape hoặc decode sai khi truyền qua YAML, environment variable hay JDBC URL.
- Secret manager trả về credential của môi trường khác.
- Account bị khóa hoặc password hết hạn.
- Account được tạo lại ở Host khác với account mà ứng dụng đang match.
- Một số pod/instance còn giữ cấu hình hoặc connection pool cũ.

Kiểm tra trạng thái account:

```sql
SELECT
    User,
    Host,
    plugin,
    account_locked,
    password_expired
FROM mysql.user
WHERE User = 'shop_app';
```

Không đọc hoặc xuất password hash. Nếu cần reset, dùng `ALTER USER` trên đúng account row sau khi xác nhận host:

```sql
ALTER USER 'shop_app'@'10.20.1.15'
    IDENTIFIED WITH caching_sha2_password BY '<new-secret-from-secret-manager>';
```

`<new-secret-from-secret-manager>` là chỗ giữ chỗ, không phải password thật. Không commit lệnh có secret vào repository hoặc ghi vào shell history. Sau khi reset, cập nhật secret manager và recycle pool để connection mới dùng credential mới.

### 7.1. Account bị khóa hoặc password hết hạn

Nếu account bị khóa, kiểm tra lý do trước khi mở khóa. Chỉ sau khi xác nhận account cần hoạt động và credential được quản lý đúng mới thực hiện:

```sql
ALTER USER 'shop_app'@'10.20.1.15' ACCOUNT UNLOCK;
```

Nếu password hết hạn, thay password theo chính sách của tổ chức. Không tắt chính sách hết hạn trên toàn server chỉ để một ứng dụng cũ kết nối được.

### 7.2. Ký tự đặc biệt trong password

Password có ký tự `&`, `?`, `#`, `%`, `@`, dấu nháy hoặc dấu gạch chéo có thể bị hiểu sai nếu nối trực tiếp vào JDBC URL. Hãy truyền username/password qua `Properties`, `DataSource` hoặc secret provider thay vì ghép password vào URL.

Ví dụ:

```java
Properties properties = new Properties();
properties.setProperty("user", secretProvider.get("shop-db-user"));
properties.setProperty("password", secretProvider.get("shop-db-password"));

Connection connection = DriverManager.getConnection(
    "jdbc:mysql://mysql.example.internal:3306/shop?sslMode=VERIFY_IDENTITY",
    properties
);
```

`secretProvider` là thành phần minh họa đại diện cho secret manager. Không in `Properties`, JDBC URL hoặc exception context chứa secret vào log.

## 8. Kiểm tra quyền sau khi xác thực thành công

Nếu login thành công nhưng câu lệnh trả `SELECT command denied`, `INSERT command denied` hoặc lỗi quyền khác, vấn đề nằm ở authorization chứ không phải authentication.

Kiểm tra:

```sql
SELECT USER(), CURRENT_USER();
SHOW GRANTS;
```

Hoặc với account cụ thể:

```sql
SHOW GRANTS FOR 'shop_app'@'10.20.1.15';
```

Kiểm tra role được gán và role nào đang active trong session nếu hệ thống dùng MySQL roles. Không cấp `ALL PRIVILEGES` hoặc `GRANT OPTION` như một cách xử lý mặc định.

Ví dụ cấp quyền tối thiểu cho service cần đọc và ghi một schema:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON shop.* TO 'shop_app'@'10.20.1.15';
```

Quyền cần thiết tùy nghiệp vụ. Một service đọc báo cáo có thể chỉ cần `SELECT`; service migration cần quyền DDL riêng và không nên dùng cùng account runtime của ứng dụng.

## 9. Host bị chặn và host cache

Nếu có quá nhiều lỗi kết nối từ một địa chỉ, MySQL có thể chặn host và trả lỗi `1129` (`Host ... is blocked because of many connection errors`). Đây là trường hợp khác với `1045` do password hoặc account matching.

Kiểm tra biến:

```sql
SHOW VARIABLES LIKE 'max_connect_errors';
```

Nếu có quyền, kiểm tra host cache:

```sql
SELECT *
FROM performance_schema.host_cache
WHERE IP = '10.20.1.15'\G
```

Host cache có thể chứa số liệu về lỗi phân giải tên, handshake, xác thực, TLS và số lỗi kết nối. Các cột có thể thay đổi theo phiên bản MySQL. Không xuất thông tin nhạy cảm của client ngoài phạm vi cần thiết.

Trước khi xóa hoặc reset host cache, phải sửa nguyên nhân gốc như password sai được retry liên tục, TLS handshake lỗi hoặc client gửi handshake không hợp lệ. Nếu chỉ xóa cache mà không sửa ứng dụng, host có thể bị chặn lại ngay. Thao tác làm sạch host cache cần quyền quản trị và phải theo tài liệu của phiên bản đang chạy.

## 10. Quy trình điều tra Access denied theo thứ tự

Thực hiện theo luồng sau để tránh đổi password hoặc mở quyền quá sớm:

1. **Thu thập lỗi:** lưu đầy đủ error code, SQLState, thông báo, thời điểm, endpoint và client/driver version.
2. **Xác nhận endpoint:** chắc chắn ứng dụng đang kết nối đúng MySQL instance, proxy hoặc replica dự kiến.
3. **Xác định client host:** kiểm tra IP nguồn sau NAT/proxy và giá trị `skip_name_resolve`.
4. **Kiểm tra account matching:** liệt kê các dòng `User`/`Host`, anonymous account và host pattern cụ thể hơn.
5. **Kiểm tra plugin:** xác định plugin của đúng account row và khả năng hỗ trợ của client/Connector/J.
6. **Kiểm tra TLS/RSA:** xem account có `REQUIRE SSL/X509`, server có yêu cầu secure transport, client có CA/hostname phù hợp hay RSA key đáng tin cậy.
7. **Kiểm tra credential:** xác nhận secret version, password expiry, account lock và cấu hình truyền password.
8. **Kiểm tra quyền:** sau khi đăng nhập thành công, xác nhận `CURRENT_USER()` và `SHOW GRANTS`.
9. **Kiểm tra host cache:** chỉ khi lỗi là host blocked hoặc có dấu hiệu handshake lặp.
10. **Thử lại bằng đúng đường mạng:** dùng client tương thích và cùng endpoint/host để xác nhận kết quả.
11. **Cập nhật runbook:** ghi account row đã chọn, plugin, TLS mode, thay đổi và kết quả xác minh mà không lưu secret.

Không thay đổi nhiều biến cùng lúc. Nếu đổi plugin, password, host pattern và TLS đồng thời, sẽ khó xác định thay đổi nào giải quyết lỗi và có thể tạo thêm account ngoài ý muốn.

## 11. Ma trận triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần kiểm tra | Hành động phù hợp |
|---|---|---|---|
| Password đúng nhưng vẫn `1045` | MySQL chọn account Host khác | Các dòng `mysql.user`, host trong error, anonymous account | Sửa account matching và thu hồi account thừa sau đánh giá |
| Chỉ container/pod bị lỗi | IP sau NAT khác dự kiến | IP client server nhìn thấy, network path | Cập nhật host pattern hẹp phù hợp hoặc sửa network path |
| Máy local kết nối được, remote không | `localhost` account khác remote account; firewall hoặc TLS | `User`/`Host`, IP, port và log server | Tạo/cấu hình account remote đúng và kiểm tra mạng |
| `using password: NO` | Password không được truyền | Secret injection, DataSource properties | Sửa cấu hình credential và tránh nối password vào URL |
| `caching_sha2_password` không được hỗ trợ | Connector/J/client quá cũ | Driver thực tế runtime nạp | Nâng cấp driver và kiểm thử |
| `Public Key Retrieval is not allowed` | Full authentication không TLS và thiếu RSA key | TLS mode, plugin, public key config | Dùng TLS đã xác minh hoặc public key file đáng tin cậy |
| SSL handshake thất bại | CA, certificate chain hoặc hostname sai | Truststore, SAN, thời hạn chứng thư | Cập nhật CA/chứng thư và dùng hostname khớp |
| Account bị khóa | Chính sách hoặc thao tác quản trị | `account_locked`, audit/change log | Xác minh nguyên nhân rồi mở khóa có kiểm soát |
| Password hết hạn | Chính sách password | `password_expired`, thông báo client | Đổi password theo chính sách và cập nhật secret |
| Login được nhưng truy vấn bị từ chối | Thiếu quyền hoặc role chưa active | `CURRENT_USER()`, `SHOW GRANTS` | Cấp quyền tối thiểu đúng account |
| `1129` host blocked | Nhiều lỗi handshake/kết nối | `host_cache`, `max_connect_errors`, log | Sửa lỗi gốc rồi xử lý host cache theo phiên bản |

## 12. Xoay vòng password mà không gây gián đoạn

Đổi password trực tiếp trên account đang dùng có thể làm connection mới trong pool thất bại nếu ứng dụng vẫn giữ secret cũ. Với MySQL version hỗ trợ dual password, có thể giữ password cũ trong giai đoạn chuyển đổi:

```sql
ALTER USER 'shop_app'@'10.20.1.15'
    IDENTIFIED BY '<new-secret>' RETAIN CURRENT PASSWORD;
```

Sau khi ứng dụng đã nhận secret mới và các pool đã được recycle:

```sql
ALTER USER 'shop_app'@'10.20.1.15'
    DISCARD OLD PASSWORD;
```

Tính năng dual password phụ thuộc phiên bản và plugin. Nếu không hỗ trợ, có thể tạo account mới với quyền tương đương, chuyển ứng dụng sang account mới rồi khóa/thu hồi account cũ sau khi xác nhận không còn kết nối sử dụng.

Quy trình an toàn:

1. Xác định đúng account `user@host` và service sử dụng nó.
2. Tạo credential mới trong secret manager.
3. Cập nhật account hoặc tạo account mới theo phương án hỗ trợ.
4. Cập nhật secret của ứng dụng và rolling restart/recycle connection pool.
5. Kiểm tra kết nối mới, `CURRENT_USER()` và quyền truy vấn.
6. Xác nhận không còn instance sử dụng password cũ.
7. Thu hồi password cũ hoặc account cũ.
8. Ghi lại thời điểm, người thực hiện và kết quả mà không lưu giá trị secret.

## 13. Bảo mật khi xử lý sự cố

- Không yêu cầu người dùng gửi password qua chat, ticket hoặc log.
- Không ghi `authentication_string`, password, token, private key hoặc truststore password vào báo cáo.
- Không cấp `ALL PRIVILEGES`, `CONNECTION_ADMIN` hoặc quyền quản trị rộng chỉ để xử lý lỗi đăng nhập.
- Không mở Host thành `%` hoặc tắt TLS như biện pháp sửa nhanh.
- Không bật lại plugin xác thực legacy nếu chưa có đánh giá và thời hạn thay thế.
- Không dùng account `root` trong ứng dụng.
- Giới hạn quyền xem `mysql.user`, `SHOW CREATE USER`, log server và host cache.
- Thực hiện reset password hoặc mở khóa account sau khi xác nhận đúng account row và chủ sở hữu service.

Một báo cáo điều tra tốt có thể ghi username, Host row được chọn, plugin, TLS mode, client version, error code và thay đổi đã thực hiện; không cần ghi password hoặc hash.

## 14. Tình huống thực hành

Một ứng dụng Spring Boot chạy trong Kubernetes không kết nối được MySQL sau khi chuyển sang cụm mới. Log ghi `Access denied for user 'shop_app'@'10.20.1.15' (using password: YES)`. Nhóm vận hành khẳng định password trong secret manager vẫn đúng.

Thực hiện trong môi trường lab:

1. Xác nhận hostname/port mà pod đang kết nối và IP nguồn server nhìn thấy.
2. Kiểm tra `skip_name_resolve` và liệt kê các account `shop_app` cùng anonymous account có thể match.
3. So sánh `plugin`, `account_locked` và `password_expired` của từng account row.
4. Kiểm tra Connector/J version thực tế trong container image và xác nhận hỗ trợ `caching_sha2_password`.
5. Kiểm tra account có `REQUIRE SSL` và server có `require_secure_transport` hay không.
6. Cấu hình TLS `VERIFY_IDENTITY`, trust CA và hostname khớp SAN; xác nhận kết nối thành công.
7. Dùng `USER()` và `CURRENT_USER()` để chứng minh account row thực tế sau khi login.
8. Dùng `SHOW GRANTS` để kiểm tra quyền và thử một thao tác được phép cùng một thao tác bị cấm.
9. Thử xoay password trong lab, cập nhật secret và recycle pool.
10. Ghi báo cáo gồm nguyên nhân gốc, bằng chứng, thay đổi và bước ngăn tái diễn; không lưu secret.

**Câu hỏi tự đánh giá:**

- Vì sao `using password: YES` không chứng minh password đúng?
- `USER()` và `CURRENT_USER()` khác nhau như thế nào?
- Vì sao một anonymous account có Host cụ thể có thể ảnh hưởng việc chọn account?
- `skip_name_resolve=ON` làm thay đổi cách dùng hostname trong account Host ra sao?
- Vì sao `caching_sha2_password` có thể cần TLS hoặc RSA public key trong full authentication?
- `sslMode=REQUIRED` khác `VERIFY_IDENTITY` ở điểm nào?
- Khi nào cần điều tra host cache và `max_connect_errors` thay vì reset password?
- Vì sao lỗi quyền `SELECT` sau khi đăng nhập thành công không phải lỗi authentication?
- Làm thế nào xoay password mà không làm toàn bộ connection pool mất khả năng kết nối?

## Kết luận

Lỗi `Access denied` cần được điều tra từ danh tính client và account `user@host` trước khi thay đổi password hoặc quyền. Hãy xác định đúng account row, kiểm tra plugin và tương thích driver, xác minh TLS/RSA, trạng thái account rồi mới kiểm tra quyền SQL. Với ứng dụng hiện đại, ưu tiên `caching_sha2_password`, TLS `VERIFY_IDENTITY`, account Host giới hạn và secret manager. Ghi lại bằng chứng và thay đổi nhưng tuyệt đối không đưa password hoặc khóa riêng vào log.
