# TLS, sslMode, truststore và xác thực danh tính máy chủ

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài học này tập trung vào bảo vệ kết nối JDBC giữa ứng dụng Java và MySQL bằng TLS, cấu hình `sslMode` của MySQL Connector/J, quản lý CA trong Java truststore và xác minh danh tính máy chủ.

TLS bảo vệ dữ liệu trên đường truyền và giúp client xác minh máy chủ mà nó đang kết nối. Chỉ bật mã hóa chưa đủ để chống máy chủ giả mạo hoặc tấn công trung gian. Ứng dụng cần kiểm tra chuỗi chứng chỉ và tên máy chủ theo đúng hostname trong chứng chỉ. Với MySQL Connector/J, `sslMode=VERIFY_IDENTITY` là lựa chọn phù hợp cho kết nối production khi chứng chỉ và DNS đã được cấu hình đúng.

## 1. TLS bảo vệ kết nối JDBC như thế nào?

Khi ứng dụng Java kết nối đến MySQL qua TCP, Connector/J và MySQL thương lượng một phiên TLS trước khi trao đổi dữ liệu SQL. Sau handshake, dữ liệu truy vấn, kết quả và thông tin xác thực được truyền trong kênh đã mã hóa theo giao thức TLS được chọn.

Một phiên kết nối an toàn cần đáp ứng các yêu cầu khác nhau:

1. **Mã hóa:** dữ liệu không bị đọc trực tiếp khi đi qua mạng.
2. **Toàn vẹn:** dữ liệu không bị sửa đổi mà không bị phát hiện.
3. **Xác thực máy chủ:** ứng dụng xác minh chứng chỉ máy chủ được cấp bởi CA mà nó tin cậy.
4. **Xác minh danh tính:** tên DNS mà ứng dụng sử dụng phải khớp với danh tính được ghi trong chứng chỉ máy chủ.
5. **Quản lý vòng đời chứng chỉ:** chứng chỉ còn hạn, đúng mục đích, có chuỗi CA đầy đủ và được thay mới đúng hạn.

Mã hóa và xác minh danh tính là hai việc khác nhau. Một kết nối có thể được mã hóa nhưng không kiểm tra chứng chỉ hoặc hostname. Khi đó, ứng dụng vẫn có thể mã hóa dữ liệu với một máy chủ giả mạo do kẻ tấn công kiểm soát.

## 2. Các chế độ sslMode trong Connector/J

Thuộc tính `sslMode` được hỗ trợ từ MySQL Connector/J 8.0.13. Nó xác định Connector/J có sử dụng TLS và xác minh chứng chỉ máy chủ ở mức nào.

| Giá trị | Hành vi | Phù hợp khi nào |
|---|---|---|
| `DISABLED` | Không sử dụng TLS. | Chỉ dùng trong môi trường thử nghiệm cô lập hoặc khi có một cơ chế bảo vệ khác đã được đánh giá. |
| `PREFERRED` | Ưu tiên TLS nếu server hỗ trợ; có thể kết nối không mã hóa nếu server không hỗ trợ TLS. | Tương thích với môi trường cũ; không nên dùng làm chính sách bảo mật production. |
| `REQUIRED` | Bắt buộc TLS nhưng không xác minh chuỗi chứng chỉ máy chủ. | Khi yêu cầu mã hóa nhưng việc xác minh chứng chỉ được quản lý ở lớp khác; không bảo vệ đầy đủ trước máy chủ giả mạo. |
| `VERIFY_CA` | Bắt buộc TLS và xác minh chứng chỉ máy chủ được ký bởi CA tin cậy. | Khi cần xác minh chuỗi CA nhưng không kiểm tra hostname. |
| `VERIFY_IDENTITY` | Bắt buộc TLS, xác minh chuỗi chứng chỉ và kiểm tra danh tính máy chủ theo hostname. | Lựa chọn nên ưu tiên cho kết nối ứng dụng production. |

Ví dụ cấu hình nhanh trong JDBC URL:

```text
jdbc:mysql://db.example.com:3306/shop?sslMode=VERIFY_IDENTITY
```

`PREFERRED` có thể tự hạ xuống kết nối không TLS nếu server không hỗ trợ TLS. `REQUIRED` mã hóa nhưng không xác minh máy chủ. `VERIFY_CA` xác minh CA nhưng có thể vẫn chấp nhận chứng chỉ hợp lệ được cấp cho hostname khác. `VERIFY_IDENTITY` thực hiện cả hai bước xác minh, do đó cần hostname trong JDBC URL khớp với tên trong chứng chỉ.

Trong cấu hình production, không dùng `PREFERRED` chỉ vì nó giúp ứng dụng tiếp tục kết nối khi TLS bị lỗi. Hãy dùng chế độ bắt buộc xác minh và xử lý nguyên nhân chứng chỉ hoặc cấu hình server khi handshake thất bại.

## 3. Chứng chỉ máy chủ và hostname verification

MySQL server cần một chứng chỉ máy chủ còn hạn và khóa riêng tương ứng. Chứng chỉ thường được CA nội bộ hoặc CA công khai ký. Tên DNS mà ứng dụng dùng để kết nối phải nằm trong Subject Alternative Name (SAN) của chứng chỉ.

Ví dụ chứng chỉ có SAN:

```text
DNS:db.example.com
DNS:mysql-prod.internal.example.com
```

Nếu JDBC URL sử dụng `db.example.com`, Connector/J với `VERIFY_IDENTITY` có thể xác minh tên đó. Nếu ứng dụng kết nối bằng `10.20.5.10` nhưng chứng chỉ chỉ có SAN DNS, xác minh danh tính theo IP có thể thất bại. Cần dùng hostname có trong SAN hoặc cấp chứng chỉ có IP SAN phù hợp nếu kết nối bằng địa chỉ IP là yêu cầu thực tế.

Không dựa vào Common Name (CN) cũ thay cho SAN. Khi cấp mới chứng chỉ, đưa các hostname thật sự được dùng vào SAN và bỏ các alias không còn hợp lệ. Nếu ứng dụng kết nối qua DNS alias, proxy hoặc load balancer, chứng chỉ tại đầu cuối TLS mà client nhìn thấy phải xác minh được đúng tên URL.

### Cấu hình TLS ở MySQL server

Ví dụ cấu hình server trong option file:

```ini
[mysqld]
ssl_ca=/etc/mysql/certs/client-ca.pem
ssl_cert=/etc/mysql/certs/server-cert-chain.pem
ssl_key=/etc/mysql/certs/server-key.pem
tls_version=TLSv1.2,TLSv1.3
require_secure_transport=ON
```

Các đường dẫn chỉ là ví dụ Linux. `ssl_cert` trỏ đến chứng chỉ máy chủ (có thể chứa chuỗi chứng chỉ cần gửi cho client); `ssl_key` trỏ đến khóa riêng tương ứng; `ssl_ca` được dùng trong cấu hình xác thực chứng chỉ client khi triển khai mutual TLS. CA mà Java dùng để xác minh chứng chỉ server phải được tin cậy trong truststore phía client.

`require_secure_transport=ON` yêu cầu các kết nối từ xa sử dụng phương thức truyền tải an toàn được MySQL hỗ trợ, chẳng hạn TCP có TLS. Các kết nối local qua Unix socket hoặc named pipe có thể được xem là an toàn theo cơ chế transport tương ứng; tùy chọn này không có nghĩa mọi kết nối nội bộ đều phải thực hiện TLS handshake.

Kiểm tra cấu hình server:

```sql
SHOW GLOBAL VARIABLES LIKE 'require_secure_transport';
SHOW GLOBAL VARIABLES LIKE 'tls_version';
SHOW GLOBAL VARIABLES LIKE 'ssl_ca';
SHOW GLOBAL VARIABLES LIKE 'ssl_cert';
SHOW GLOBAL VARIABLES LIKE 'ssl_key';
```

Tên file, quyền truy cập và cú pháp cần điều chỉnh theo hệ điều hành, phiên bản MySQL và cách quản lý chứng chỉ của tổ chức. Khóa riêng server phải được bảo vệ để chỉ tài khoản dịch vụ MySQL và quản trị viên được ủy quyền mới đọc được.

### Yêu cầu TLS theo tài khoản MySQL

Ngoài chính sách toàn server, MySQL có thể đặt yêu cầu bảo mật theo từng tài khoản:

```sql
CREATE USER 'app_user'@'10.20.5.%'
    IDENTIFIED BY 'MAT_KHAU_LAY_TU_KHO_BI_MAT'
    REQUIRE SSL;
```

`REQUIRE SSL` buộc tài khoản sử dụng kết nối mã hóa. Nó không đồng nghĩa với yêu cầu client phải trình chứng chỉ X.509. Nếu triển khai mutual TLS và muốn tài khoản bắt buộc có chứng chỉ client hợp lệ, có thể dùng:

```sql
ALTER USER 'app_user'@'10.20.5.%' REQUIRE X509;
```

Quyền và host trong ví dụ cần được thu hẹp theo môi trường thực tế. `REQUIRE X509` yêu cầu client cung cấp chứng chỉ hợp lệ; để ràng buộc chặt hơn, MySQL còn hỗ trợ điều kiện issuer hoặc subject. Chỉ bật yêu cầu này sau khi đã cấp chứng chỉ client, cấu hình CA phía server và kiểm thử việc luân chuyển chứng chỉ.

## 4. Truststore và keystore trong Java

Java dùng kho chứng chỉ để xác định CA nào được tin cậy và, nếu cần, kho khóa để cung cấp chứng chỉ client.

| Kho | Chứa gì? | Vai trò trong TLS |
|---|---|---|
| Truststore | Chứng chỉ CA hoặc chứng chỉ được chọn làm trust anchor. Thường không chứa private key. | Giúp Java xác minh chuỗi chứng chỉ mà MySQL server gửi. |
| Client keystore | Chứng chỉ client cùng private key tương ứng. | Giúp ứng dụng trình danh tính client khi server yêu cầu mutual TLS. |
| Server keystore/certificate files | Chứng chỉ server và private key. | MySQL dùng để chứng minh danh tính server trong TLS handshake. |

Truststore không phải nơi lưu mật khẩu MySQL. Client keystore cũng không thay thế user/password SQL trừ khi ứng dụng có một cơ chế xác thực khác được cấu hình riêng.

Các định dạng thường gặp gồm JKS và PKCS12. PKCS12 là định dạng trao đổi phổ biến và được Java hỗ trợ rộng rãi. Hãy thống nhất định dạng, bảo vệ password của kho và giới hạn quyền đọc file.

### Tạo truststore từ CA

Trước tiên, lấy chứng chỉ CA gốc hoặc CA trung gian đúng từ đội PKI/hạ tầng qua kênh tin cậy. Xác minh fingerprint của chứng chỉ với một nguồn độc lập trước khi import.

Ví dụ tạo truststore PKCS12:

```bash
keytool -importcert \
  -alias mysql-issuing-ca \
  -file mysql-issuing-ca.pem \
  -keystore mysql-truststore.p12 \
  -storetype PKCS12
```

`keytool` sẽ yêu cầu password và xác nhận tin cậy chứng chỉ. Chỉ chấp nhận import sau khi fingerprint đã được xác minh. Thông thường nên tin cậy CA phát hành thay vì nhập một chứng chỉ server leaf cố định, trừ khi có chủ đích certificate pinning và quy trình thay chứng chỉ tương ứng.

Kiểm tra nội dung truststore:

```bash
keytool -list -v \
  -keystore mysql-truststore.p12 \
  -storetype PKCS12
```

Lệnh hiển thị alias, chủ thể, issuer, thời hạn và fingerprint. Không đưa password thật vào tham số dòng lệnh hoặc lịch sử shell; để `keytool` hỏi tương tác hoặc dùng cơ chế bí mật phù hợp với nền tảng triển khai.

## 5. Cấu hình Connector/J với sslMode=VERIFY_IDENTITY

Ví dụ sau dùng JDBC `DriverManager` và một truststore riêng. Password được lấy từ secret manager hoặc biến môi trường do môi trường triển khai cấp; không hard-code vào source code.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.Properties;

public class SecureMysqlConnection {
    public static void main(String[] args) throws Exception {
        String url = "jdbc:mysql://db.example.com:3306/shop";

        Properties props = new Properties();
        props.setProperty("user", System.getenv("DB_USER"));
        props.setProperty("password", System.getenv("DB_PASSWORD"));
        props.setProperty("sslMode", "VERIFY_IDENTITY");
        props.setProperty(
            "trustCertificateKeyStoreUrl",
            "file:/etc/myapp/certs/mysql-truststore.p12"
        );
        props.setProperty("trustCertificateKeyStoreType", "PKCS12");
        props.setProperty(
            "trustCertificateKeyStorePassword",
            System.getenv("MYSQL_TRUSTSTORE_PASSWORD")
        );

        try (Connection connection = DriverManager.getConnection(url, props);
             Statement statement = connection.createStatement();
             ResultSet rs = statement.executeQuery(
                 "SHOW SESSION STATUS LIKE 'Ssl_cipher'")) {
            while (rs.next()) {
                System.out.println(rs.getString("Variable_name") + "="
                    + rs.getString("Value"));
            }
        }
    }
}
```

Ví dụ giả định Connector/J đã có trong classpath và các biến môi trường được cấp an toàn. `db.example.com` phải nằm trong SAN của chứng chỉ server. Đường dẫn `file:/...` phải trỏ đến truststore mà tiến trình Java có quyền đọc. Tên thuộc tính phải giữ đúng chữ hoa/thường như tài liệu Connector/J.

Có thể cấu hình truststore ở cấp JVM bằng các thuộc tính JSSE như `javax.net.ssl.trustStore`, `javax.net.ssl.trustStoreType` và `javax.net.ssl.trustStorePassword`. Cách này ảnh hưởng đến các kết nối TLS khác trong cùng JVM nếu chúng dùng truststore mặc định. Khi ứng dụng có nhiều dịch vụ hoặc kết nối đến nhiều hệ thống với CA khác nhau, truststore riêng cho Connector/J giúp khoanh vùng phạm vi tin cậy rõ hơn.

Không cấu hình đồng thời nhiều cơ chế truststore mà không xác định thứ tự ưu tiên của Connector/J và JSSE. Hãy kiểm tra đúng tài liệu phiên bản Connector/J đang sử dụng, sau đó kiểm thử chứng chỉ thực tế trên môi trường staging.

## 6. Mutual TLS: xác thực cả client và server

Trong TLS thông thường, client xác minh chứng chỉ server. Với mutual TLS (mTLS), server cũng yêu cầu client trình chứng chỉ để xác minh danh tính của ứng dụng.

Quy trình tổng quát:

1. MySQL server trình chứng chỉ server; Connector/J xác minh CA và hostname theo `VERIFY_IDENTITY`.
2. MySQL yêu cầu client certificate theo chính sách tài khoản hoặc cấu hình kết nối.
3. Connector/J lấy certificate và private key từ client keystore.
4. MySQL kiểm tra chứng chỉ client dựa trên CA được cấu hình ở server.
5. Sau TLS handshake, MySQL vẫn thực hiện xác thực tài khoản và kiểm tra quyền SQL theo cơ chế đã cấu hình.

Ví dụ cấu hình client keystore trong Connector/J:

```java
props.setProperty("sslMode", "VERIFY_IDENTITY");
props.setProperty(
    "trustCertificateKeyStoreUrl",
    "file:/etc/myapp/certs/mysql-truststore.p12"
);
props.setProperty("trustCertificateKeyStoreType", "PKCS12");
props.setProperty(
    "trustCertificateKeyStorePassword",
    System.getenv("MYSQL_TRUSTSTORE_PASSWORD")
);
props.setProperty(
    "clientCertificateKeyStoreUrl",
    "file:/etc/myapp/certs/app-client-keystore.p12"
);
props.setProperty("clientCertificateKeyStoreType", "PKCS12");
props.setProperty(
    "clientCertificateKeyStorePassword",
    System.getenv("MYSQL_CLIENT_KEYSTORE_PASSWORD")
);
```

Server cần cấu hình CA tin cậy để xác minh client certificate và tài khoản cần yêu cầu X.509 nếu chính sách yêu cầu:

```sql
ALTER USER 'app_user'@'10.20.5.%' REQUIRE X509;
```

Client keystore phải chứa private key và certificate chain phù hợp. Không chia sẻ một private key cho nhiều ứng dụng nếu cần khả năng thu hồi và truy vết độc lập. Hãy cấp chứng chỉ riêng cho từng service, đặt thời hạn hợp lý và có kế hoạch thay mới trước khi hết hạn.

## 7. Chọn TLS protocol và kiểm tra phiên bản thực tế

Giao thức TLS mà kết nối sử dụng phụ thuộc vào nhiều thành phần: MySQL server, OpenSSL hoặc thư viện TLS của server, JDK, Connector/J và cấu hình cho phép ở hai phía.

Connector/J có thuộc tính `tlsVersions` để giới hạn các phiên bản TLS mà client được phép thương lượng. Ví dụ:

```java
props.setProperty("tlsVersions", "TLSv1.2,TLSv1.3");
```

Chỉ cấu hình protocol được cả server và JDK hỗ trợ. Không bật lại TLS cũ chỉ để làm cho một client lỗi thời kết nối được; hãy nâng cấp JDK hoặc Connector/J nếu cần. Ở server, biến `tls_version` xác định protocol được phép sử dụng.

Sau khi kết nối, xác minh phiên TLS thực tế:

```sql
SHOW SESSION STATUS LIKE 'Ssl_version';
SHOW SESSION STATUS LIKE 'Ssl_cipher';
```

`Ssl_version` cho biết protocol được thương lượng, `Ssl_cipher` cho biết cipher suite đang dùng. Nếu `Ssl_cipher` rỗng, phiên hiện tại không sử dụng TLS. Đừng chỉ dựa vào URL đã cấu hình; cần kiểm tra trạng thái trên chính session của ứng dụng.

## 8. Các thuộc tính cũ và cấu hình cần tránh

Connector/J có các thuộc tính SSL cũ như `useSSL`, `requireSSL` và `verifyServerCertificate`. Từ Connector/J 8.0.13, `sslMode` là thuộc tính thống nhất để mô tả chính sách TLS; các thuộc tính cũ được giữ lại chủ yếu cho tương thích và đã được đánh dấu deprecated trong tài liệu tương ứng.

Khi chuyển cấu hình, không đặt các thuộc tính cũ với `sslMode` theo những tổ hợp mâu thuẫn. Hãy chuyển sang một giá trị `sslMode` rõ ràng và xóa các tham số cũ sau khi kiểm thử.

Ví dụ cấu hình cần tránh:

```text
jdbc:mysql://db.example.com:3306/shop?useSSL=true&verifyServerCertificate=false
```

URL này bật SSL nhưng tắt xác minh chứng chỉ máy chủ. Nó không đáp ứng yêu cầu xác thực danh tính. Cấu hình thay thế:

```text
jdbc:mysql://db.example.com:3306/shop?sslMode=VERIFY_IDENTITY
```

Nếu dùng truststore tùy chỉnh, cấu hình các thuộc tính truststore riêng trong `Properties` hoặc URL đã được encode đúng. Tránh ghép password, token hoặc bí mật vào JDBC URL vì URL thường xuất hiện trong log, exception, metrics hoặc màn hình quản trị connection pool.

## 9. Kiểm tra TLS trong ứng dụng và vận hành

Một checklist xác minh kết nối nên có các bước:

1. Xác nhận JDBC URL dùng hostname nằm trong SAN của chứng chỉ.
2. Xác nhận `sslMode=VERIFY_IDENTITY` được áp dụng cho mọi physical connection trong pool.
3. Xác nhận truststore chứa CA đúng và chuỗi chứng chỉ server đầy đủ.
4. Xác nhận JDK và Connector/J hỗ trợ protocol TLS đã chọn.
5. Mở kết nối qua đúng driver và tài khoản ứng dụng.
6. Chạy `SHOW SESSION STATUS LIKE 'Ssl_version'` và `Ssl_cipher` trên session đó.
7. Thử kết nối với CA sai hoặc hostname không khớp trên môi trường thử nghiệm; kết nối phải thất bại.
8. Kiểm tra server từ chối kết nối không TLS khi `require_secure_transport=ON` hoặc tài khoản `REQUIRE SSL`.
9. Kiểm tra connection pool tạo lại kết nối sau khi thay truststore hoặc chứng chỉ.
10. Ghi lại thời hạn chứng chỉ, cảnh báo sắp hết hạn và người chịu trách nhiệm luân chuyển.

TLS handshake thường diễn ra khi tạo physical connection. Connection pool có thể tái sử dụng kết nối đã mở, do đó thay chứng chỉ hoặc truststore không tự động thay đổi các session đang tồn tại. Sau khi luân chuyển CA/certificate, cần có chiến lược overlap CA cũ/mới, tạo lại physical connection theo kế hoạch và xác minh các kết nối mới.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `PKIX path building failed` hoặc `unable to find valid certification path` | Truststore thiếu CA gốc/trung gian, sai truststore hoặc chuỗi server không đầy đủ. | Xác minh CA/fingerprint, import CA đúng vào truststore và kiểm tra chuỗi server gửi. |
| Hostname verification failed | Hostname trong JDBC URL không khớp SAN của chứng chỉ. | Dùng DNS name hợp lệ hoặc cấp lại chứng chỉ có SAN chính xác. Không hạ xuống `VERIFY_CA` chỉ để bỏ qua lỗi danh tính. |
| TLS handshake failure | Protocol/cipher không giao nhau, chứng chỉ hết hạn, sai mục đích hoặc cấu hình server/client không tương thích. | Kiểm tra JDK, Connector/J, `tlsVersions`, `tls_version`, ngày hết hạn và log hai phía. |
| Kết nối vẫn chạy khi server không hỗ trợ TLS | Client đang dùng `PREFERRED` và đã fallback sang plaintext. | Chuyển sang `REQUIRED`, `VERIFY_CA` hoặc `VERIFY_IDENTITY`; bật chính sách bắt buộc TLS ở server. |
| `REQUIRED` kết nối được nhưng không xác minh được server | Chế độ này chỉ bắt buộc mã hóa, không kiểm tra chuỗi CA và hostname. | Dùng `VERIFY_IDENTITY` và cấu hình truststore đúng. |
| `REQUIRE X509` báo lỗi chứng chỉ client | Client keystore thiếu private key/certificate, CA server không tin cậy hoặc tài khoản yêu cầu certificate khác. | Kiểm tra client keystore, CA ở server và điều kiện X.509 của tài khoản. |
| Chỉ một số instance trong pool lỗi sau khi thay cert | Các instance dùng truststore, JDK, DNS hoặc kết nối vật lý khác nhau. | Kiểm kê cấu hình từng instance, recycle connection có kiểm soát và kiểm tra lại TLS status. |

Không xử lý lỗi chứng chỉ bằng cách tắt xác minh trong production. Hãy tìm nguyên nhân ở chuỗi CA, SAN, thời hạn chứng chỉ, truststore, DNS hoặc cấu hình protocol.

## 11. Bài tập thực hành

Thiết lập một MySQL server thử nghiệm có chứng chỉ được ký bởi CA thử nghiệm. Tạo ứng dụng Java dùng Connector/J và thực hiện các bước:

1. Cấp chứng chỉ server có SAN `mysql-lab.example.test`; cấu hình `ssl_cert`, `ssl_key` và TLS protocol trên MySQL.
2. Tạo truststore PKCS12 chứa CA thử nghiệm; xác minh fingerprint trước khi import.
3. Kết nối bằng JDBC URL dùng `sslMode=VERIFY_IDENTITY` và hostname đúng.
4. Truy vấn `Ssl_version` và `Ssl_cipher` để xác nhận phiên hiện tại có TLS.
5. Thử `sslMode=DISABLED` khi server bật `require_secure_transport=ON`; xác nhận kết nối bị từ chối.
6. Thử `VERIFY_IDENTITY` với hostname không có trong SAN; xác nhận hostname verification thất bại.
7. Thử truststore thiếu CA hoặc chứa CA không đúng; xác nhận chain verification thất bại.
8. Nếu có điều kiện, cấp client certificate riêng, cấu hình client keystore và đặt tài khoản `REQUIRE X509`; xác minh mTLS hoạt động.
9. Thay chứng chỉ server trong môi trường thử nghiệm, luân chuyển CA theo giai đoạn và tạo lại physical connection trong pool.
10. Ghi lại cấu hình JDK/Connector/J, `sslMode`, protocol, cipher, lỗi cố ý tạo ra và kết quả kiểm tra.

Sau bài tập, người học cần giải thích được vì sao mã hóa TLS chưa đủ nếu không xác minh máy chủ, sự khác nhau giữa `VERIFY_CA` và `VERIFY_IDENTITY`, vai trò của truststore và client keystore, và cách chứng minh session JDBC thực tế đang dùng TLS. Đây là nền tảng để bảo vệ kết nối MySQL từ ứng dụng Java một cách nhất quán và có thể kiểm tra.
