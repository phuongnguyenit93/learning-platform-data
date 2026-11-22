# Cấu hình TLS, kiểm tra danh tính máy chủ và quản lý chứng thư

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích TLS bảo vệ kết nối MySQL như thế nào và phân biệt mã hóa đường truyền với xác minh danh tính server.
- Nhận biết vai trò của CA, chứng thư server, khóa riêng và chứng thư client.
- Cấu hình TLS cơ bản cho MySQL Server và buộc kết nối từ xa sử dụng kênh bảo mật.
- Kết nối bằng MySQL client và JDBC với chế độ xác minh chứng thư và hostname.
- Kiểm tra phiên TLS đang hoạt động, xử lý lỗi xác minh và lập kế hoạch gia hạn, luân chuyển chứng thư.

## 1. Vì sao kết nối MySQL cần TLS?

Ứng dụng thường kết nối MySQL qua mạng TCP/IP. Nếu không có lớp bảo vệ phù hợp, dữ liệu trao đổi có thể bị quan sát hoặc thay đổi trên đường truyền bởi một bên có khả năng can thiệp vào mạng. TLS (Transport Layer Security) tạo một kênh được mã hóa giữa client và server, đồng thời cung cấp cơ chế xác minh chứng thư để client kiểm tra server mà nó đang kết nối.

TLS giải quyết ba mục tiêu liên quan:

- **Bảo mật dữ liệu trên đường truyền:** người nghe lén mạng không thể đọc nội dung trao đổi nếu phiên TLS được thiết lập đúng.
- **Toàn vẹn dữ liệu:** dữ liệu truyền qua kênh TLS được bảo vệ khỏi việc sửa đổi mà không bị phát hiện.
- **Xác thực danh tính:** client có thể xác minh chứng thư server được cấp bởi CA mà client tin cậy và chứng thư phù hợp với hostname dự định kết nối.

Điểm cuối cùng rất quan trọng. Một kết nối có mã hóa chưa chắc đã kết nối đúng máy chủ. Nếu client chỉ yêu cầu mã hóa nhưng không xác minh chứng thư và tên máy chủ, kẻ tấn công có thể giả mạo server trong một cuộc tấn công trung gian (man-in-the-middle) và vẫn thiết lập được một kết nối TLS riêng với client.

Vì vậy, trong môi trường production, mục tiêu nên là **mã hóa kết nối và xác minh danh tính server**.

## 2. Các thành phần của hệ thống chứng thư

### 2.1. CA và chuỗi tin cậy

CA (Certificate Authority) là tổ chức hoặc hệ thống phát hành chứng thư số. Client lưu hoặc được cấu hình để tin cậy chứng thư CA. Khi nhận chứng thư server, client kiểm tra chữ ký và chuỗi chứng thư để xác định chứng thư đó được phát hành bởi một CA đáng tin cậy.

Một mô hình thường gặp:

```text
Client trust store
       |
       v
Root CA (CA gốc được tin cậy)
       |
       v
Intermediate CA (CA trung gian, nếu có)
       |
       v
Server certificate (chứng thư của db.example)
       |
       +-- Subject Alternative Name: DNS:db.example
       +-- Public key
       +-- Validity: Not Before / Not After

MySQL Server giữ private key tương ứng với public key trong server certificate.
```

Các thành phần chính:

| Thành phần | Nơi sử dụng | Vai trò |
|---|---|---|
| Root CA certificate | Trust store của client; phía server khi cần xác minh client certificate | Gốc tin cậy để xác minh chữ ký trong chuỗi chứng thư |
| Intermediate CA certificate | Chuỗi chứng thư gửi cùng server certificate hoặc trust bundle theo chính sách | Nối chứng thư server với CA gốc |
| Server certificate | MySQL Server gửi cho client trong TLS handshake | Chứa danh tính server, public key, thời hạn và thông tin CA ký |
| Server private key | Chỉ MySQL Server được phép đọc | Chứng minh server sở hữu private key tương ứng; không được chia sẻ cho client |
| Client certificate và private key | Ứng dụng/client khi dùng xác thực TLS hai chiều | Cho phép server xác minh danh tính client bằng chứng thư |

Chứng thư server cần có tên DNS mà ứng dụng thực sự sử dụng trong trường Subject Alternative Name (SAN). Ví dụ, nếu ứng dụng kết nối tới `db.example.internal`, SAN phải chứa tên đó. Nếu kết nối bằng địa chỉ IP, chứng thư cần có SAN kiểu IP tương ứng. Không nên dựa vào Common Name (CN) cũ thay cho SAN.

Private key phải được bảo vệ bằng quyền truy cập hệ điều hành. Chỉ tài khoản dịch vụ MySQL và quản trị viên được ủy quyền mới nên đọc được khóa này. Không đưa private key lên Git, image container công khai, ticket hoặc log.

### 2.2. TLS một chiều và TLS hai chiều

Trong cấu hình phổ biến, server trình chứng thư cho client; client xác minh chứng thư server. Đây là xác thực server, thường được gọi là TLS một chiều.

Với xác thực TLS hai chiều (mutual TLS hoặc mTLS), client cũng trình chứng thư của mình. Server xác minh chứng thư client dựa trên CA được cấu hình. mTLS bổ sung một lớp xác thực ở tầng kết nối; MySQL vẫn thực hiện xác thực tài khoản và phân quyền SQL theo cơ chế riêng.

Không nhầm lẫn ba việc sau:

1. TLS mã hóa đường truyền.
2. Client xác minh danh tính server.
3. Server xác minh chứng thư client (nếu bật mTLS).

Một hệ thống có thể sử dụng hai bước đầu mà không cần chứng thư client. Chỉ triển khai mTLS khi có yêu cầu quản lý danh tính thiết bị hoặc ứng dụng ở tầng kết nối và đã có quy trình cấp phát, gia hạn, thu hồi chứng thư client.

## 3. Chuẩn bị chứng thư cho MySQL Server

Trước khi cấu hình MySQL, cần có:

- Chứng thư CA gốc mà client sẽ tin cậy (`ca.pem` hoặc CA bundle tương đương).
- Server certificate do CA đó hoặc CA trung gian của nó ký (`server-cert.pem`).
- Server private key tương ứng (`server-key.pem`).
- Intermediate certificate nếu chuỗi chứng thư yêu cầu.

Trong môi trường doanh nghiệp, nên dùng CA nội bộ được quản lý tập trung hoặc CA công khai phù hợp với tên miền và chính sách. Với môi trường phát triển, có thể dùng CA thử nghiệm riêng. Không dùng chứng thư tự ký tạm thời như một giải pháp production lâu dài.

Khi yêu cầu cấp chứng thư server, cung cấp đúng hostname mà client sẽ dùng để kết nối. Chứng thư nên có mục đích sử dụng phù hợp cho TLS server authentication, thời hạn hợp lý và chuỗi CA đầy đủ. Nếu có nhiều endpoint hoặc alias DNS, cần bảo đảm các tên được client sử dụng đều có trong SAN.

### 3.1. Kiểm tra chứng thư và private key

Có thể dùng OpenSSL để đọc thông tin chứng thư:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates -ext subjectAltName
```

Lệnh này giúp kiểm tra chủ thể, CA phát hành, thời hạn và SAN. Xem thông tin private key mà không in nội dung khóa:

```bash
openssl pkey -in server-key.pem -check -noout
```

Kiểm tra chữ ký chứng thư với CA. Nếu có CA trung gian, đưa chứng thư trung gian vào tham số `-untrusted`:

```bash
# Trường hợp CA ký trực tiếp
openssl verify -CAfile ca.pem server-cert.pem

# Trường hợp có intermediate CA
openssl verify -CAfile root-ca.pem -untrusted intermediate-ca.pem server-cert.pem
```

Kết quả `OK` cho biết phép kiểm tra chuỗi theo CA và đầu vào đã cung cấp thành công. Đây chưa phải toàn bộ kiểm tra TLS: vẫn cần kiểm tra SAN có khớp hostname client dùng, thời hạn chứng thư, mục đích sử dụng và cấu hình thực tế của MySQL.

Nếu server certificate cần gửi intermediate certificate, cấu hình file chứng thư theo định dạng chain mà MySQL và CA của bạn yêu cầu. Không thay thế CA root trong trust store bằng một chứng thư server leaf chỉ để làm cho kết nối vượt qua bước xác minh.

## 4. Cấu hình TLS trên MySQL Server

Tên file và đường dẫn dưới đây là ví dụ trên Linux. Với Windows hoặc container, thay bằng đường dẫn thực tế mà tiến trình MySQL có thể đọc.

Trong file cấu hình MySQL, thường là một file `my.cnf` hoặc file được include, đặt các tùy chọn trong nhóm `[mysqld]`:

```ini
[mysqld]
ssl_ca=/etc/mysql/certs/ca.pem
ssl_cert=/etc/mysql/certs/server-cert.pem
ssl_key=/etc/mysql/certs/server-key.pem

# Chỉ chấp nhận kết nối cần transport bảo mật
require_secure_transport=ON

# Giới hạn phiên bản TLS theo chính sách của môi trường
tls_version=TLSv1.2,TLSv1.3
```

Ý nghĩa:

- `ssl_ca`: CA hoặc CA bundle dùng trong xác minh chứng thư theo cấu hình TLS của server; đặc biệt cần thiết khi server xác minh client certificate.
- `ssl_cert`: chứng thư server và, khi cần, chuỗi chứng thư trung gian.
- `ssl_key`: private key tương ứng với server certificate.
- `require_secure_transport`: yêu cầu kết nối sử dụng transport được MySQL xem là bảo mật. Kết nối TCP không có TLS sẽ bị từ chối; một số transport cục bộ như Unix socket có thể vẫn được xem là bảo mật.
- `tls_version`: danh sách phiên bản TLS server cho phép. Chỉ bật phiên bản mà bản MySQL, thư viện TLS và client trong hệ thống hỗ trợ.

Hãy bảo đảm tiến trình MySQL đọc được CA và certificate, đồng thời private key không thể bị người dùng không được phép đọc. Trên Linux, chủ sở hữu và quyền file thường cần được đặt theo tài khoản dịch vụ MySQL của bản cài đặt; ví dụ `mysql:mysql` và quyền đọc hạn chế cho private key. Trên Windows, cấu hình ACL cho tài khoản chạy dịch vụ.

Sau khi thay đổi cấu hình, thực hiện reload hoặc restart theo quy trình vận hành và khả năng của phiên bản MySQL đang dùng. Một số phiên bản MySQL hỗ trợ nạp lại cấu hình TLS mà không restart; không giả định lệnh reload giống nhau giữa MySQL, MariaDB và mọi phiên bản. Kiểm tra error log nếu server không khởi động hoặc không nạp được chứng thư.

### 4.1. Kiểm tra cấu hình server đã được nạp

Kết nối bằng tài khoản quản trị phù hợp rồi đọc các biến:

```sql
SHOW GLOBAL VARIABLES LIKE 'ssl_ca';
SHOW GLOBAL VARIABLES LIKE 'ssl_cert';
SHOW GLOBAL VARIABLES LIKE 'ssl_key';
SHOW GLOBAL VARIABLES LIKE 'tls_version';
SHOW GLOBAL VARIABLES LIKE 'require_secure_transport';
```

Các biến này cho biết đường dẫn và chính sách mà server công bố. Chúng không tự chứng minh client đang sử dụng TLS; phải kiểm tra trạng thái của chính phiên kết nối ở bước tiếp theo.

## 5. Kết nối bằng MySQL client và xác minh server

### 5.1. Các chế độ SSL của MySQL client

MySQL client hiện đại hỗ trợ `--ssl-mode` với các giá trị thường dùng sau:

| Chế độ | Hành vi |
|---|---|
| `DISABLED` | Không dùng TLS |
| `PREFERRED` | Ưu tiên TLS nhưng có thể kết nối không mã hóa nếu server không hỗ trợ TLS |
| `REQUIRED` | Bắt buộc TLS nhưng không xác minh chuỗi CA và hostname server như các chế độ verify |
| `VERIFY_CA` | Bắt buộc TLS và xác minh chứng thư theo CA tin cậy |
| `VERIFY_IDENTITY` | Bắt buộc TLS, xác minh chuỗi CA và xác minh hostname client đang kết nối khớp danh tính trong chứng thư |

`REQUIRED` bảo đảm kênh được mã hóa nhưng chưa đủ để xác minh server là đúng máy chủ dự định. Với kết nối production, dùng `VERIFY_IDENTITY` và cung cấp CA tin cậy phù hợp.

### 5.2. Kết nối với xác minh hostname

Ví dụ kết nối tới `db.example.internal`:

```bash
mysql \
  --host=db.example.internal \
  --port=3306 \
  --user=app_user \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/myapp/certs/ca.pem \
  app_db
```

Client sẽ hỏi mật khẩu tương tác. Không ghi mật khẩu trực tiếp vào câu lệnh hoặc file cấu hình không được bảo vệ. `--ssl-ca` chỉ định CA mà client dùng để xác minh chứng thư server.

Hostname trong `--host` phải khớp với SAN của server certificate. Nếu chứng thư có `DNS:db.example.internal` nhưng ứng dụng kết nối bằng một IP hoặc alias khác không nằm trong SAN, chế độ `VERIFY_IDENTITY` sẽ từ chối kết nối. Cách xử lý đúng là cấp chứng thư có SAN phù hợp với endpoint được sử dụng hoặc dùng hostname chuẩn đã được cấp chứng thư.

Các tùy chọn `--ssl-mode` là của MySQL client. MariaDB client và các phiên bản connector khác có thể dùng tên tùy chọn hoặc cách cấu hình khác; cần kiểm tra tài liệu đúng client thay vì sao chép nguyên lệnh này.

### 5.3. Kiểm tra phiên hiện tại có sử dụng TLS

Sau khi kết nối, chạy:

```sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
SHOW SESSION STATUS LIKE 'Ssl_version';
```

`Ssl_cipher` cho biết cipher suite của phiên; giá trị rỗng thường cho biết phiên hiện tại không dùng TLS. `Ssl_version` cho biết phiên bản TLS được thương lượng. Có thể dùng lệnh `\s` trong MySQL client để xem tóm tắt trạng thái kết nối; đầu ra thường có dòng SSL khi phiên dùng TLS.

Hãy kiểm tra từ đúng kết nối ứng dụng hoặc một kết nối thử có cùng hostname, CA và chế độ SSL. Một phiên quản trị có TLS không chứng minh mọi kết nối trong connection pool đều đã cấu hình TLS.

## 6. Cấu hình TLS trong ứng dụng Java

Với MySQL Connector/J, URL JDBC có thể yêu cầu xác minh danh tính server bằng thuộc tính `sslMode`:

```properties
jdbc:mysql://db.example.internal:3306/app_db?sslMode=VERIFY_IDENTITY
```

Khi CA đã được cài trong trust store mặc định mà JVM sử dụng, Connector/J có thể dựa vào trust store đó để xác minh chuỗi chứng thư. Nếu dùng CA nội bộ riêng, cấu hình trust store dành cho ứng dụng. Ví dụ tạo trust store PKCS12 từ CA certificate:

```bash
keytool -importcert \
  -alias mysql-private-ca \
  -file ca.pem \
  -keystore mysql-truststore.p12 \
  -storetype PKCS12
```

Sau đó cấu hình Connector/J để dùng trust store. Ví dụ Java minh họa:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Properties;

String url = "jdbc:mysql://db.example.internal:3306/app_db";

Properties properties = new Properties();
properties.setProperty("sslMode", "VERIFY_IDENTITY");
properties.setProperty(
    "trustCertificateKeyStoreUrl",
    "file:/etc/myapp/certs/mysql-truststore.p12"
);
properties.setProperty("trustCertificateKeyStoreType", "PKCS12");
properties.setProperty(
    "trustCertificateKeyStorePassword",
    System.getenv("DB_TRUSTSTORE_PASSWORD")
);

try (Connection connection = DriverManager.getConnection(url, properties)) {
    System.out.println("Connected with verified TLS");
}
```

Ví dụ giả định biến môi trường `DB_TRUSTSTORE_PASSWORD` đã được cấp qua secret manager hoặc cơ chế quản lý bí mật của môi trường triển khai. Không commit mật khẩu trust store vào source code. Kiểm tra tên thuộc tính và hành vi TLS theo phiên bản MySQL Connector/J thực tế; driver MariaDB dùng cấu hình riêng.

Nếu ứng dụng cần mTLS, ngoài trust store để xác minh server, cấu hình thêm client key store chứa client certificate và private key. Không dùng server private key làm client key; hai danh tính và mục đích sử dụng khác nhau.

## 7. Bật xác thực TLS hai chiều (mTLS) khi cần

Để server yêu cầu client có chứng thư hợp lệ, tài khoản MySQL có thể được cấu hình với điều kiện chứng thư. Ví dụ:

```sql
ALTER USER 'app_user'@'%' REQUIRE X509;
```

Điều kiện `REQUIRE X509` yêu cầu client trình chứng thư X.509 hợp lệ theo chính sách TLS của server. MySQL cũng hỗ trợ ràng buộc issuer hoặc subject trong những phiên bản phù hợp; hãy đối chiếu tài liệu phiên bản trước khi dùng các điều kiện chi tiết đó.

Client cần cung cấp client certificate và private key, ví dụ với MySQL client:

```bash
mysql \
  --host=db.example.internal \
  --user=app_user \
  --password \
  --ssl-mode=VERIFY_IDENTITY \
  --ssl-ca=/etc/myapp/certs/ca.pem \
  --ssl-cert=/etc/myapp/certs/client-cert.pem \
  --ssl-key=/etc/myapp/certs/client-key.pem \
  app_db
```

Ở đây `--ssl-ca` giúp client xác minh server; `--ssl-cert` và `--ssl-key` cung cấp danh tính client để server xác minh. Hai hướng xác minh này độc lập với nhau.

Trước khi bật `REQUIRE X509` cho tài khoản ứng dụng production, cần cấp và phân phối client certificate cho mọi instance, kiểm tra quyền đọc private key, thiết lập gia hạn và thu hồi, rồi thử trên môi trường staging. Nếu tài khoản không có chứng thư hợp lệ, kết nối sẽ thất bại ngay ở bước xác thực.

## 8. Buộc kết nối bảo mật mà không làm gián đoạn ứng dụng

Không nên bật `require_secure_transport=ON` một cách bất ngờ trên server đang có ứng dụng cũ. Các client chưa hỗ trợ TLS hoặc đang dùng cấu hình `PREFERRED` có thể bị từ chối hoặc kết nối theo cách không đáp ứng yêu cầu xác minh danh tính.

Một trình tự triển khai an toàn:

1. **Kiểm kê client:** xác định tất cả ứng dụng, job, công cụ quản trị, connector, phiên bản driver và endpoint đang kết nối.
2. **Cấp CA và server certificate:** bảo đảm chứng thư có SAN khớp hostname thực tế và còn hạn.
3. **Cài trust:** phân phối CA certificate tới trust store của từng ứng dụng và công cụ cần kết nối.
4. **Thử xác minh:** chuyển client sang `VERIFY_IDENTITY`; kiểm tra handshake, hostname, chuỗi CA và trạng thái `Ssl_cipher`/`Ssl_version`.
5. **Cập nhật toàn bộ client:** xác nhận mọi connection pool, tác vụ nền, công cụ backup và giám sát đều kết nối được qua TLS.
6. **Bật chính sách server:** bật `require_secure_transport` theo cửa sổ thay đổi đã lên kế hoạch.
7. **Theo dõi và đối soát:** kiểm tra error log, lỗi kết nối của ứng dụng và các phiên đang sử dụng TLS; giữ phương án rollback cấu hình nếu phát sinh client chưa được cập nhật.

Lưu ý: một số kết nối cục bộ qua Unix socket có thể vẫn thỏa điều kiện secure transport của MySQL dù không dùng TLS. Nếu chính sách yêu cầu TLS cho mọi kết nối, cần kiểm tra cả loại transport và cách ứng dụng kết nối, không chỉ nhìn `require_secure_transport`.

## 9. Gia hạn, luân chuyển và thu hồi chứng thư

Chứng thư có thời hạn. Nếu server certificate hết hạn, client xác minh nghiêm ngặt sẽ từ chối kết nối. Nếu CA hết hạn hoặc bị loại khỏi trust store, các chứng thư được CA đó ký cũng có thể không còn được tin cậy.

### 9.1. Theo dõi vòng đời

Quản lý tối thiểu các thông tin sau cho từng chứng thư:

- Chủ thể, SAN và mục đích sử dụng (server authentication hoặc client authentication).
- CA phát hành và chuỗi intermediate.
- Thời điểm bắt đầu và kết thúc hiệu lực.
- Vị trí triển khai, hệ thống hoặc service sử dụng.
- Người hoặc hệ thống chịu trách nhiệm gia hạn, luân chuyển và thu hồi.

Có thể dùng OpenSSL để kiểm tra thời hạn:

```bash
openssl x509 -in server-cert.pem -noout -dates
```

Nên có cảnh báo trước khi chứng thư hết hạn đủ lâu để xử lý việc cấp mới, phân phối và kiểm thử. Không chờ đến khi chứng thư hết hạn mới bắt đầu gia hạn.

### 9.2. Luân chuyển server certificate

Nếu thay server certificate nhưng vẫn dùng CA hiện tại, client thường tiếp tục tin cậy CA đó. Tuy nhiên, chứng thư mới vẫn phải có SAN chính xác, chuỗi hợp lệ và private key tương ứng.

Nếu chuyển sang CA mới, cần tránh khoảng thời gian mà một số client chỉ tin CA cũ trong khi server đã chuyển sang chứng thư mới. Một cách triển khai phổ biến là:

1. Phân phối trust bundle có cả CA cũ và CA mới tới client.
2. Xác nhận client đã cập nhật trust store.
3. Cài server certificate mới và nạp lại TLS context hoặc restart theo hướng dẫn của phiên bản.
4. Kiểm tra client xác minh thành công qua mọi endpoint.
5. Sau khi không còn server/client certificate phụ thuộc CA cũ, loại CA cũ khỏi trust store theo kế hoạch.

Việc nạp lại TLS có thể cần quyền quản trị và có hành vi khác nhau theo phiên bản. Đọc tài liệu MySQL đúng phiên bản và thử quy trình trên staging trước khi áp dụng production.

### 9.3. Thu hồi chứng thư và bảo vệ private key

Nếu private key bị lộ hoặc một client không còn được phép truy cập, thu hồi chứng thư theo quy trình CA. MySQL có các tùy chọn liên quan danh sách thu hồi chứng thư (CRL), chẳng hạn `ssl_crl` và `ssl_crlpath` ở những phiên bản hỗ trợ. Cấu hình và cách cập nhật CRL phải được kiểm tra theo phiên bản server, CA và thư viện TLS đang dùng.

Khi nghi ngờ server private key bị lộ, cần thay key và certificate, cập nhật chuỗi tin cậy nếu cần, đồng thời điều tra phạm vi ảnh hưởng. Không chỉ xóa file key cũ rồi coi sự cố đã được xử lý; bản sao key có thể tồn tại trong backup, image, log hoặc hệ thống phân phối bí mật.

## 10. Xử lý lỗi TLS thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| `certificate verify failed` | CA không được tin cậy, chuỗi intermediate thiếu, chứng thư hết hạn hoặc chưa có hiệu lực | Kiểm tra issuer, validity, CA bundle và chain bằng OpenSSL; cập nhật trust đúng CA |
| Hostname verification failed | SAN không chứa hostname hoặc IP client đang dùng | Kết nối bằng DNS name có trong SAN hoặc cấp lại chứng thư với SAN chính xác |
| `unknown ca` hoặc lỗi CA | Client không có CA phù hợp hoặc server không tin CA cấp client certificate trong mTLS | Xác định bên nào đang xác minh chứng thư; cài CA đúng trust store hoặc cấu hình CA phía server |
| `handshake failure` | Không có phiên bản TLS/cipher suite chung, chứng thư hoặc key không hợp lệ, hoặc chính sách mTLS không đáp ứng | Đối chiếu `tls_version`, thư viện TLS, log server và cấu hình client certificate |
| Server không khởi động sau khi bật TLS | Đường dẫn sai, file không đọc được, private key không khớp certificate hoặc định dạng không hợp lệ | Kiểm tra error log, quyền file, chain và tính hợp lệ của key/certificate |
| Ứng dụng kết nối được ở máy cá nhân nhưng lỗi trên server ứng dụng | Trust store JVM, hostname, DNS hoặc file CA giữa hai môi trường khác nhau | Kiểm tra cấu hình JVM/Connector/J và endpoint thực tế của ứng dụng |
| Kết nối bị từ chối sau khi bật `require_secure_transport` | Có client đang kết nối TCP không TLS hoặc driver chưa cấu hình TLS | Kiểm kê client, bật TLS và xác minh trước khi áp dụng lại chính sách |

Không khắc phục lỗi xác minh bằng cách tắt kiểm tra certificate, chuyển sang `VERIFY_CA` khi cần xác minh hostname, hoặc hạ xuống `REQUIRED`/`PREFERRED` trong production. Hãy sửa CA, SAN, chain, thời hạn hoặc cấu hình client để đáp ứng đúng chính sách.

## 11. Checklist kiểm tra một kết nối MySQL an toàn

Trước khi đưa cấu hình vào production, xác nhận:

- [ ] Server certificate được cấp bởi CA mà client tin cậy.
- [ ] SAN có hostname hoặc IP mà ứng dụng thực sự sử dụng.
- [ ] Chứng thư còn hạn, có mục đích sử dụng phù hợp và gửi đủ intermediate chain.
- [ ] Server private key khớp certificate và chỉ tài khoản dịch vụ cần thiết được đọc.
- [ ] Server chỉ cho phép phiên bản TLS theo chính sách bảo mật hiện hành.
- [ ] MySQL client dùng `--ssl-mode=VERIFY_IDENTITY` hoặc chế độ tương đương có xác minh hostname.
- [ ] Ứng dụng Java dùng `sslMode=VERIFY_IDENTITY` và trust store đúng CA.
- [ ] `Ssl_cipher` và `Ssl_version` có giá trị phù hợp trong phiên kiểm tra.
- [ ] Nếu bật mTLS, client certificate có quy trình cấp, gia hạn và thu hồi riêng.
- [ ] `require_secure_transport` chỉ được bật sau khi mọi client cần thiết đã được kiểm tra.
- [ ] Có cảnh báo hết hạn chứng thư, kế hoạch luân chuyển và phương án xử lý khi key bị lộ.

## 12. Kết luận

TLS bảo vệ dữ liệu MySQL trên đường truyền, nhưng một cấu hình an toàn còn cần xác minh danh tính server. Hãy dùng CA đáng tin cậy, chứng thư có SAN khớp endpoint, private key được bảo vệ và chế độ client xác minh cả chuỗi CA lẫn hostname.

Quản lý chứng thư là công việc liên tục: theo dõi thời hạn, gia hạn, luân chuyển CA/server certificate, cập nhật trust store và thu hồi khi cần. Khi thay đổi chính sách TLS hoặc bật `require_secure_transport`, kiểm tra toàn bộ client và connection pool để duy trì kết nối an toàn mà không làm gián đoạn ứng dụng MySQL.
