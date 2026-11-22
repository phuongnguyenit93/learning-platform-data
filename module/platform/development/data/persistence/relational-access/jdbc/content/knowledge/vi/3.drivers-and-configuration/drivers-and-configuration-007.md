# Cấu hình xác thực, mã hóa đường truyền và kiểm tra chứng chỉ trong JDBC

**JDBC (Java Database Connectivity)** là API Java để truy cập cơ sở dữ liệu quan hệ. Khi ứng dụng mở kết nối qua `DriverManager` hoặc `DataSource`, driver JDBC phải biết nơi kết nối, danh tính tài khoản và chính sách bảo vệ lưu lượng mạng. Trong môi trường thực tế, cấu hình này quyết định liệu tài khoản có bị lộ, dữ liệu có bị đọc trộm và ứng dụng có nhận đúng máy chủ database hay không.

Bài thuộc chương **Driver và cấu hình**, tập trung vào ba lớp phải được phân biệt rõ: **xác thực tài khoản**, **mã hóa đường truyền bằng TLS** và **kiểm tra chứng chỉ máy chủ**. Các ví dụ sử dụng JDBC trên PostgreSQL, MySQL và Microsoft SQL Server, kèm cách kiểm tra hành vi cấu hình và chẩn đoán lỗi.

## 1. Ba nhiệm vụ bảo mật khác nhau

```text
    Ứng dụng Java                     Máy chủ cơ sở dữ liệu
          |                                      |
          |---------- Kết nối mạng ------------>|
          |<-------- Thương lượng TLS --------->|
          |<-------- Chứng chỉ máy chủ ---------|
          |--- Xác minh CA và hostname -------->|
          |<======== Kênh TLS an toàn =========>|
          |--- Tài khoản / cơ chế xác thực ---->|
          |<-------- Session và quyền --------->|
          |<========= SQL và kết quả ==========>|
```

Sơ đồ trình bày logic; thứ tự chính xác của các thông điệp phụ thuộc giao thức database. Ba nhiệm vụ có ý nghĩa riêng:

- **Xác thực (authentication)** trả lời “ai đang kết nối?”. Database kiểm tra user/password, token hoặc cơ chế đăng nhập khác; sau đó phân quyền để xác định tài khoản được thực hiện SQL nào.
- **Mã hóa đường truyền (transport encryption)** trả lời “người nghe lén mạng có đọc được nội dung không?”. TLS mã hóa và bảo vệ tính toàn vẹn trên chặng kết nối giữa client và điểm kết thúc TLS.
- **Xác minh chứng chỉ máy chủ (server certificate validation)** trả lời “máy chủ ở đầu kia có thật sự là database dự kiến?”. Client kiểm tra chuỗi CA tin cậy và tên máy chủ trên chứng chỉ.

Đăng nhập đúng **không tự bảo đảm** có TLS. Có TLS **không tự bảo đảm** đã kiểm tra danh tính server. Ngược lại, xác minh server thành công không có nghĩa tài khoản DB đã được cấp quyền thích hợp.

| Lớp | Bảo vệ chính | Điều không tự giải quyết |
|---|---|---|
| Tài khoản và quyền DB | Chỉ người dùng được phép mới thực hiện truy vấn phù hợp | Mã hóa gói tin trên mạng |
| TLS | Bảo mật lưu lượng giữa hai đầu phiên TLS | Xác thực tên server nếu client chấp nhận mọi chứng chỉ |
| Kiểm tra CA + hostname | Chống giả mạo máy chủ và tấn công người đứng giữa | Quyền đọc/ghi SQL |
| Mã hóa dữ liệu lưu trữ | Bảo vệ dữ liệu trên đĩa/backup theo cơ chế riêng | Bảo mật kết nối JDBC trên mạng |

## 2. Xác thực tài khoản JDBC

### 2.1. Username và password

`DriverManager.getConnection(String url, Properties info)` hỗ trợ truyền tài khoản và mật khẩu qua thuộc tính. Chuyển secret khỏi URL giúp giảm nguy cơ chúng bị ghi vào log, lịch sử shell hoặc thông báo lỗi chứa connection string.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public final class JdbcLoginExample {
    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường: " + name);
        }
        return value;
    }

    public static void main(String[] args) throws SQLException {
        String jdbcUrl = requireEnv("DB_JDBC_URL");

        Properties properties = new Properties();
        properties.setProperty("user", requireEnv("DB_USERNAME"));
        properties.setProperty("password", requireEnv("DB_PASSWORD"));

        try (Connection connection =
                     DriverManager.getConnection(jdbcUrl, properties)) {
            System.out.println("Kết nối hoạt động: " + connection.isValid(5));
        }
    }
}
```

Đây mới là ví dụ **xác thực tài khoản**. Chính sách TLS chưa được chỉ rõ và phụ thuộc URL, driver hoặc cấu hình môi trường. Ngoài ra, `Connection.isValid(5)` kiểm tra kết nối còn dùng được, **không phải phép kiểm tra chứng chỉ, hostname hoặc TLS**.

Một số hệ quản trị hỗ trợ xác thực Kerberos, token, tài khoản đám mây hoặc chứng chỉ máy khách. Những tùy chọn đó là đặc thù của driver và server: chuẩn JDBC không định nghĩa một tập thuộc tính xác thực nâng cao dùng chung cho mọi database.

### 2.2. Nguyên tắc quản lý secret và quyền

- Cấp mỗi dịch vụ một danh tính DB riêng, chỉ với quyền `SELECT`, `INSERT`, `UPDATE`, `DELETE` thực sự cần thiết. Tránh dùng tài khoản quản trị.
- Cấp mật khẩu/token qua secret manager hoặc cơ chế cấu hình được bảo vệ. Biến môi trường trong ví dụ chỉ mang tính minh họa; chúng vẫn cần bảo vệ khỏi truy cập, dump hoặc log ngoài ý muốn.
- Không hard-code secret trong source, file được commit, URL có thể ghi log hoặc command-line argument. Không in giá trị secret khi kết nối lỗi.
- Có kế hoạch xoay vòng credential. Khi thay password, các connection trong pool có thể cần được làm mới để lần mở kết nối mới dùng secret mới.
- Bật TLS cả khi cơ chế password mạnh: truy vấn, dữ liệu trả về, các thuộc tính session và metadata vẫn có thể là thông tin nhạy cảm.

### 2.3. Chứng chỉ máy khách khác chứng chỉ máy chủ

Trong **TLS một chiều**, client xác minh server bằng chứng chỉ server, sau đó dùng cơ chế đăng nhập DB phù hợp. Với **mutual TLS (mTLS)**, server còn yêu cầu client trình chứng chỉ để xác minh phía máy khách. Chứng chỉ máy khách thường cần một *private key* trong keystore; cơ chế ánh xạ chứng chỉ sang user và phân quyền SQL tùy database.

Chứng chỉ server và private key server không được sao chép sang truststore của ứng dụng. Truststore chứa các trust anchor/CA mà client chủ động tin cậy; còn keystore danh tính máy khách chứa tài liệu định danh và private key của **client**, chỉ dùng khi cần mTLS.

## 3. Vì sao phải kiểm tra chứng chỉ khi đã mã hóa bằng TLS?

TLS thiết lập kênh mã hóa giữa hai đầu kết nối. Nếu client bật mã hóa nhưng **chấp nhận mọi chứng chỉ**, một máy chủ giả mạo có khả năng chặn lưu lượng vẫn có thể bắt tay TLS với client. Nội dung khi đó vẫn mã hóa trên đường dây, nhưng kẻ tấn công là một đầu của kết nối nên đọc được dữ liệu. Đây là lý do phải xác minh danh tính server.

Hai kiểm tra cốt lõi:

1. **Certificate-chain validation:** chứng chỉ server còn hiệu lực, có mục đích sử dụng phù hợp và được ký bởi chuỗi chứng chỉ dẫn đến một CA/trust anchor mà client tin cậy.
2. **Hostname verification:** hostname trong JDBC URL, chẳng hạn `db.prod.example.com`, khớp với tên khai báo trong `Subject Alternative Name (SAN)` của chứng chỉ. Nếu URL dùng địa chỉ IP, chứng chỉ phải hỗ trợ đối chiếu địa chỉ IP theo chính sách xác minh.

Một chứng chỉ được một CA tin cậy ký nhưng cấp cho **máy khác** không đủ để xác minh máy chủ cần kết nối. Một chứng chỉ có đúng tên nhưng được cấp bởi CA không tin cậy cũng phải bị từ chối. Tên hostname, SAN và CA cần phù hợp **đồng thời**.

### 3.1. Chế độ TLS có thể mang các ý nghĩa khác nhau

| Mức yêu cầu | Mã hóa lưu lượng | Xác minh CA | Xác minh hostname |
|---|---:|---:|---:|
| Tắt TLS | Không | Không | Không |
| Yêu cầu TLS, bỏ qua certificate validation | Có | Không | Không |
| Xác minh CA | Có | Có | Không nhất thiết |
| Xác minh CA và hostname | Có | Có | Có |

Tùy driver, các chế độ được đặt tên `require`, `verify-ca`, `verify-full`, `VERIFY_IDENTITY`... và không thể sao chép nguyên cấu hình của driver này sang driver khác. Với ứng dụng production, nên yêu cầu **TLS có xác minh CA và hostname**, trừ khi kiến trúc bảo mật có cơ chế tương đương được đánh giá và quản lý rõ ràng.

### 3.2. Truststore là gì?

Truststore là kho chứng chỉ mà client sử dụng để xác định các CA/trust anchor được tin cậy. Java có thể dùng kho tin cậy mặc định của runtime, nhưng một số JDBC driver hỗ trợ riêng đường dẫn CA PEM hoặc truststore PKCS#12/JKS.

Có thể chuẩn bị truststore PKCS#12 bằng công cụ `keytool`:

```bash
keytool -importcert \
  -alias company-db-ca \
  -file db-ca.crt \
  -keystore db-truststore.p12 \
  -storetype PKCS12

keytool -list \
  -keystore db-truststore.p12 \
  -storetype PKCS12
```

Lệnh có thể hỏi mật khẩu để bảo vệ kho. **Trước khi import, kiểm tra nguồn phát hành và fingerprint CA qua một kênh tin cậy độc lập**. Nếu tự động tin chứng chỉ lấy trực tiếp từ endpoint chưa được xác minh, ứng dụng có thể hợp thức hóa chính máy chủ giả mạo.

Không nhập private key của server vào truststore. Nếu cần mTLS, client identity keystore là một cấu hình riêng, có kiểm soát quyền đọc private key.

## 4. PostgreSQL JDBC: cấu hình `sslmode=verify-full`

Driver PostgreSQL (*pgJDBC*) cung cấp thuộc tính `sslmode` với các mức thường gặp:

| `sslmode` | Ý nghĩa |
|---|---|
| `disable` | Không dùng TLS. |
| `allow` / `prefer` | Cho phép kết nối dự phòng; không bảo đảm luôn dùng TLS. |
| `require` | Yêu cầu TLS, nhưng không có mức kiểm tra CA và hostname đầy đủ như `verify-full`. |
| `verify-ca` | Yêu cầu TLS và xác minh chứng chỉ theo CA đáng tin cậy. |
| `verify-full` | Yêu cầu TLS, xác minh CA **và** hostname. |

Ví dụ sử dụng `Properties` để giữ password bên ngoài JDBC URL:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public final class SecurePostgres {
    public static Connection open(String username, String password)
            throws SQLException {
        Properties p = new Properties();
        p.setProperty("user", username);
        p.setProperty("password", password);
        p.setProperty("sslmode", "verify-full");
        p.setProperty("sslrootcert", "/etc/app/certs/postgres-ca.crt");

        return DriverManager.getConnection(
                "jdbc:postgresql://db.prod.example.com:5432/orders", p);
    }
}
```

Giả định file `/etc/app/certs/postgres-ca.crt` là CA được cung cấp và xác minh bởi bộ phận vận hành, theo định dạng mà pgJDBC hỗ trợ. `db.prod.example.com` phải trùng danh tính DNS trên chứng chỉ server. Các giá trị tài khoản được cấp bởi cấu hình an toàn của ứng dụng.

Có thể truyền tương đương bằng URL `jdbc:postgresql://db.prod.example.com:5432/orders?sslmode=verify-full&sslrootcert=/etc/app/certs/postgres-ca.crt`; nếu đường dẫn có ký tự đặc biệt cần mã hóa URL đúng cách. Với đường dẫn khác nhau giữa môi trường, dùng cấu hình theo môi trường nhưng **giữ nguyên yêu cầu xác minh danh tính**.

Nếu một chứng chỉ bị thay bằng chứng chỉ CA không tin cậy, hết hạn hoặc có SAN không khớp, ứng dụng phải từ chối kết nối. Không chuyển sang `sslmode=require` như giải pháp lâu dài cho lỗi truststore.

**Kiểm tra session phía server PostgreSQL:**

```sql
SELECT ssl, version, cipher
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
```

Kết quả `ssl = true` cho biết session đang dùng TLS theo quan sát của server. Giá trị `version`, `cipher` giúp quan sát giao thức đang dùng. Truy vấn **không thể chứng minh** rằng client đã kiểm tra CA và hostname: phải kết hợp với cấu hình driver và kiểm thử từ chối chứng chỉ không hợp lệ.

## 5. MySQL Connector/J: cấu hình `sslMode=VERIFY_IDENTITY`

MySQL Connector/J dùng thuộc tính `sslMode`. Cách đặt tên khác PostgreSQL:

| `sslMode` | Ý nghĩa |
|---|---|
| `DISABLED` | Không dùng TLS. |
| `PREFERRED` | Ưu tiên TLS nhưng có thể kết nối theo chế độ khác nếu điều kiện cho phép. |
| `REQUIRED` | Bắt buộc TLS, chưa xác minh danh tính server như các chế độ mạnh hơn. |
| `VERIFY_CA` | Bắt buộc TLS và kiểm tra chuỗi CA. |
| `VERIFY_IDENTITY` | Bắt buộc TLS, kiểm tra CA và hostname. |

Ví dụ này dùng truststore PKCS#12 đã được chuẩn bị:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public final class SecureMySql {
    public static Connection open(
            String username, String password, String truststorePassword)
            throws SQLException {

        Properties p = new Properties();
        p.setProperty("user", username);
        p.setProperty("password", password);
        p.setProperty("sslMode", "VERIFY_IDENTITY");
        p.setProperty("trustCertificateKeyStoreUrl",
                "file:/etc/app/certs/mysql-truststore.p12");
        p.setProperty("trustCertificateKeyStoreType", "PKCS12");
        p.setProperty("trustCertificateKeyStorePassword", truststorePassword);

        return DriverManager.getConnection(
                "jdbc:mysql://mysql.prod.example.com:3306/orders", p);
    }
}
```

Các tham số secret phải được cung cấp qua hệ thống cấu hình an toàn. Truststore cần chứa CA phù hợp để xác minh server, và chứng chỉ server cần có tên SAN trùng `mysql.prod.example.com`. Thuộc tính được driver hỗ trợ có thể thay đổi theo phiên bản, vì vậy luôn xác minh với tài liệu Connector/J dùng trong dự án.

MySQL có thể cho biết TLS session thông qua:

```sql
SHOW SESSION STATUS LIKE 'Ssl_version';
SHOW SESSION STATUS LIKE 'Ssl_cipher';
```

Có phiên bản TLS/cipher là bằng chứng về TLS ở session; nó không chứng minh client dùng `VERIFY_IDENTITY`. Để xác minh danh tính, cần cấu hình đúng và thử trường hợp chứng chỉ sai trong môi trường kiểm thử.

## 6. Microsoft SQL Server JDBC: `encrypt` và `trustServerCertificate`

Driver Microsoft SQL Server JDBC có các thuộc tính như `encrypt` và `trustServerCertificate`. Một cấu hình cơ bản yêu cầu TLS và không bỏ qua kiểm tra chứng chỉ:

```text
jdbc:sqlserver://sql.prod.example.com:1433;
databaseName=orders;
encrypt=true;
trustServerCertificate=false;
```

Ví dụ được ngắt dòng cho dễ đọc; URL triển khai cần ghép các phần lại theo cú pháp kết nối SQL Server. Có thể chuyển thuộc tính sang `Properties`:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public final class SecureSqlServer {
    public static Connection open(String username, String password)
            throws SQLException {
        Properties p = new Properties();
        p.setProperty("user", username);
        p.setProperty("password", password);
        p.setProperty("encrypt", "true");
        p.setProperty("trustServerCertificate", "false");

        return DriverManager.getConnection(
                "jdbc:sqlserver://sql.prod.example.com:1433;databaseName=orders",
                p);
    }
}
```

Cấu hình này dựa trên giả định môi trường Java/driver có kho CA tin cậy phù hợp với chứng chỉ server. Nếu CA chưa được tin cậy, cần cấu hình truststore theo tài liệu của driver, không chuyển thành `trustServerCertificate=true` để qua lỗi chứng chỉ.

Khi SQL Server dùng proxy hoặc DNS alias, có thể cần cấu hình tên kiểm tra trên chứng chỉ theo khả năng driver, chẳng hạn `hostNameInCertificate` trong một số môi trường. Phải xác định tên danh tính chính xác và kiểm soát việc ghi đè, không dùng tùy chọn này để bỏ qua xác minh. Các phiên bản driver còn có thể hỗ trợ các mức mã hóa mới; không suy luận mặc định luôn giống nhau.

## 7. Không có thuộc tính SSL chung cho mọi JDBC driver

| Yêu cầu | PostgreSQL JDBC | MySQL Connector/J | Microsoft SQL Server JDBC |
|---|---|---|---|
| Bắt buộc TLS và xác minh hostname | `sslmode=verify-full` | `sslMode=VERIFY_IDENTITY` | `encrypt=true` với `trustServerCertificate=false` và trust phù hợp |
| Nguồn CA tin cậy | `sslrootcert` hoặc cơ chế SSL được driver hỗ trợ | Truststore/CA driver hỗ trợ | Truststore/cấu hình tin cậy driver hỗ trợ |
| Kiểm tra TLS session | `pg_stat_ssl` | `Ssl_version`/`Ssl_cipher` | Công cụ quan sát của SQL Server/driver |
| Cần tránh trong production | Hạ về `require` để bỏ qua lỗi cert | Coi `PREFERRED` là bắt buộc TLS | Bật `trustServerCertificate=true` thiếu kiểm soát |

Với Oracle Database, TLS thường liên quan đến **TCPS**, wallet/truststore và quy tắc kiểm tra danh tính máy chủ của driver Oracle. Không dùng thuộc tính PostgreSQL `sslmode` hoặc MySQL `sslMode` cho Oracle. **Tên thuộc tính và mặc định có thể đổi theo driver/version**, nên khi nâng driver cần kiểm tra tài liệu và các bài thử kết nối.

## 8. Cách kiểm tra kết nối thực sự an toàn

Một kết nối thành công chỉ cho biết ứng dụng và database đã trao đổi được; nó chưa đủ để kết luận chính sách TLS đã được áp dụng. Có thể kiểm tra theo thứ tự:

1. **Kiểm tra URL, driver và phiên bản:** hostname, chế độ TLS, thuộc tính xác minh CA/hostname, đường dẫn truststore. Tránh cấu hình có khả năng fallback plaintext.
2. **Kiểm tra chứng chỉ server:** CA, chuỗi chứng chỉ trung gian, SAN, ngày hết hạn, mục đích sử dụng, chứng chỉ ở từng endpoint sau load balancer.
3. **Quan sát phiên TLS:** dùng các view/trạng thái của database hoặc công cụ driver để kiểm tra kết nối vật lý thực sự có TLS và phiên bản/cipher phù hợp.
4. **Kiểm thử từ chối CA sai:** trong môi trường thử nghiệm, thay nguồn CA bằng một CA không tin cậy và bảo đảm JDBC từ chối kết nối **trước khi chạy SQL**.
5. **Kiểm thử hostname sai:** kết nối đến endpoint có chứng chỉ không khớp hostname và xác nhận lỗi. Không tạo hoặc thay đổi chứng chỉ production để thử.
6. **Kiểm tra đăng nhập và quyền:** mật khẩu sai bị từ chối; tài khoản hợp lệ không thực hiện được SQL ngoài quyền đã được cấp.
7. **Kiểm tra connection pool và xoay vòng:** mọi kết nối vật lý mới phải áp dụng chính sách TLS; CA, token, credential hoặc chứng chỉ thay đổi có thể đòi làm mới các connection cũ.

**Chú ý khi dùng công cụ mạng:** một số giao thức database có bước thương lượng TLS riêng, nên `openssl s_client -connect host:port` không phải phép kiểm tra đầy đủ dùng cho mọi cổng JDBC. Kết quả thực tế nên được xác minh bằng driver/database mục tiêu, cùng việc kiểm tra chứng chỉ ở đầu client.

Nếu ứng dụng kết nối thông qua proxy hoặc load balancer, phải biết **TLS kết thúc tại đâu**. Một kết nối an toàn từ Java đến proxy không chứng minh chặng từ proxy đến database cũng được mã hóa; đó là ranh giới kiến trúc riêng cần cấu hình và kiểm soát.

## 9. Chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `PKIX path building failed` / `unable to find valid certification path` | CA hoặc certificate chain không được truststore tin cậy | Kiểm tra CA gốc/trung gian, đường dẫn truststore và driver có dùng đúng kho đó không |
| `No subject alternative names` / hostname mismatch | DNS hoặc IP trong URL không khớp SAN | Kiểm tra hostname kết nối và chứng chỉ thực sự được server trình ra |
| Certificate expired/not yet valid | Chứng chỉ hết hạn, chưa tới hạn hoặc đồng hồ sai | Kiểm tra thời hạn cert và đồng bộ đồng hồ |
| SSL/TLS handshake failure | Chênh lệch phiên bản TLS/cipher, CA, giao thức hoặc cấu hình client/server | Kiểm tra JDK, driver, policy và log hai phía |
| Kết nối thành công dù CA sai | Driver đang không xác minh, hoặc đang dùng truststore khác dự kiến | Kiểm tra các tùy chọn thực tế và làm negative test |
| `Access denied` / password authentication failed | Mật khẩu, tài khoản hoặc chính sách xác thực sai | Xác minh thông tin cấp quyền và cơ chế xác thực; không log secret |
| Connection timeout / không kết nối được | DNS, firewall, mạng, port, server không sẵn sàng | Kiểm tra tuyến mạng và trạng thái máy chủ; chưa thể kết luận là lỗi TLS |
| Sau khi đổi CA, lỗi xuất hiện không đồng đều | Pool có kết nối cũ, các nút DB/proxy trình khác chứng chỉ | Kiểm tra từng endpoint và kế hoạch rollout/refresh pool |

Một lỗi chứng chỉ nên được xử lý bằng **khôi phục trust chain hoặc hostname đúng**, không bằng cách tắt TLS. Retry kết nối liên tục cũng không giải quyết được lỗi xác minh danh tính có tính xác định; cần phân loại lỗi và giới hạn retry khi thực sự có khả năng phục hồi.

## 10. Tiêu chí thiết kế và vận hành

Khi xem xét một cấu hình JDBC, hãy tự trả lời:

- **Endpoint:** ứng dụng thực sự kết nối đến hostname nào? Tên đó có trong SAN của chứng chỉ server không?
- **TLS:** driver có bắt buộc mã hóa và **xác minh CA cùng hostname**? Có trường hợp fallback không mã hóa không?
- **Truststore:** nguồn CA có được xác minh độc lập và phân phối qua kênh đáng tin? Có quy trình xoay vòng CA trước khi chứng chỉ hết hạn?
- **Credential:** tài khoản DB được cấp quyền SQL tối thiểu, secret không bị hard-code và không bị ghi log?
- **Pool:** mọi connection vật lý đều dùng cùng cấu hình bảo mật? Cấu hình mới có được áp dụng khi credential/CA thay đổi?
- **Quan sát:** có bằng chứng session dùng TLS, đồng thời đã kiểm tra việc từ chối chứng chỉ sai trong môi trường thử nghiệm?
- **Hệ thống nhiều chặng:** nếu có proxy hoặc gateway, các chặng kết nối phía sau có chính sách mã hóa và danh tính phù hợp?

Các cấu hình có thể khác nhau giữa môi trường phát triển, staging và production, nhưng chính sách bảo mật cần được mô tả rõ và có thử nghiệm xác nhận. Không coi `SELECT 1`, `Connection.isValid()` hoặc đăng nhập thành công là kiểm tra an toàn đầy đủ.

## 11. Tình huống vận dụng

**Tình huống 1.** Ứng dụng PostgreSQL dùng `sslmode=require` và kết nối thành công. Nhóm phát triển khẳng định đã an toàn vì lưu lượng mã hóa. Hãy giải thích điều kiện nào chưa được chứng minh và đề xuất cấu hình phù hợp khi cần kiểm tra máy chủ.

*Gợi ý:* So sánh mã hóa với xác minh CA/hostname, xem `verify-full`.

**Tình huống 2.** JDBC URL dùng `db-old.example.com` nhưng chứng chỉ mới chỉ có SAN `db-new.example.com`. Kết nối từ chối. Bạn sẽ xác minh DNS, certificate SAN và cách triển khai thay chứng chỉ như thế nào?

*Gợi ý:* Đồng bộ endpoint và danh tính chứng chỉ, không tắt hostname verification.

**Tình huống 3.** MySQL trả về một giá trị `Ssl_cipher`, nhưng client bật `sslMode=REQUIRED`. Điều này chứng minh được gì và chưa chứng minh được gì?

*Gợi ý:* Có TLS không đồng nghĩa đã kiểm tra chứng chỉ server.

**Tình huống 4.** Khi đổi CA, một số kết nối trong pool còn dùng được nhưng kết nối mới bị lỗi `PKIX`. Những điều gì phải được kiểm tra?

*Gợi ý:* Kho tin cậy của driver, chuỗi CA mới, từng endpoint và cách refresh pool.

**Tình huống 5.** Ứng dụng đã mã hóa và xác minh server đúng nhưng đang dùng tài khoản quản trị database cho mọi truy vấn. Đâu là rủi ro còn lại?

*Gợi ý:* TLS bảo vệ kết nối, còn **quyền SQL** phải được cấp theo nguyên tắc tối thiểu.

**Ghi nhớ:** Trong JDBC, **xác thực tài khoản**, **mã hóa đường truyền** và **xác minh chứng chỉ** là những trách nhiệm phối hợp nhưng khác nhau. Một cấu hình đáng tin cậy phải bảo vệ secret, yêu cầu TLS, kiểm tra CA + hostname, giới hạn quyền SQL và được kiểm chứng bằng driver/database đang triển khai.

