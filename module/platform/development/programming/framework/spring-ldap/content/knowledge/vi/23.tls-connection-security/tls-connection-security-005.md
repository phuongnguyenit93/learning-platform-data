# Xác minh chứng thư khi kết nối server

## 1. Vì sao phải xác minh chứng thư TLS?

Trong ứng dụng sử dụng **Spring LDAP**, các lời gọi qua `LdapTemplate`, `LdapClient` hoặc ODM sẽ truy cập máy chủ thư mục thông qua `ContextSource`, thường là `LdapContextSource`. Dữ liệu trao đổi có thể chứa DN, mật khẩu của tài khoản bind, bộ lọc tìm kiếm, thuộc tính nhân sự và thông tin nhóm phục vụ phân quyền.

Khi sử dụng **LDAPS** hoặc **StartTLS**, TLS mã hóa dữ liệu trên đường truyền. Tuy nhiên, chỉ thấy kết nối đã mã hóa chưa đủ để biết ứng dụng đang nói chuyện với **đúng máy chủ LDAP**. Một máy chủ giả mạo cũng có thể cung cấp chứng thư TLS và hoàn tất một số bước bắt tay nếu client không xác minh danh tính máy chủ.

Vì vậy, xác minh chứng thư máy chủ (server certificate validation) cần trả lời đồng thời hai câu hỏi:

1. **Chuỗi tin cậy có hợp lệ?** Chứng thư máy chủ có thể được xác minh theo một đường dẫn chứng thư tới CA/trust anchor đã được ứng dụng chấp nhận không?
2. **Danh tính có khớp?** Tên máy chủ hoặc địa chỉ IP mà ứng dụng định kết nối có được chứng thư hợp lệ đại diện không?

Chương **TLS và bảo mật kết nối** tập trung vào kiểm tra những điều kiện này **trước khi thực hiện LDAP bind hoặc gửi truy vấn nhạy cảm**, cách nhận biết lỗi, và cách kiểm thử từ chính chương trình Java. Bài học này cũng chỉ ra điểm khác nhau giữa kiểm tra certificate chain, hostname verification và kiểm tra trạng thái thu hồi chứng thư.

## 2. Chứng thư X.509 chứa những thông tin nào?

Máy chủ LDAP chạy TLS thường trình bày chứng thư theo chuẩn **X.509**. Các trường và phần mở rộng sau có vai trò trực tiếp trong việc xác minh:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Subject` | Chủ thể của chứng thư | `CN=directory.example.org` |
| `Issuer` | Đơn vị cấp chứng thư | `CN=Example Issuing CA` |
| `Validity` | Khoảng thời gian có hiệu lực | `Not Before` / `Not After` |
| `Subject Alternative Name` (SAN) | Danh tính DNS/IP mà máy chủ được phép đại diện | `DNS:directory.example.org` |
| `Subject Public Key Info` | Khóa công khai của chủ thể | Khóa RSA hoặc EC |
| `Basic Constraints` | Có phải chứng thư CA hay không; giới hạn đường dẫn | `CA:TRUE` đối với CA phù hợp |
| `Key Usage` / `Extended Key Usage` | Giới hạn mục đích sử dụng khóa/chứng thư | `serverAuth` nếu có ràng buộc EKU phù hợp |
| Chữ ký số | Bằng chứng chứng thư được ký bằng khóa của tổ chức cấp | Được kiểm tra với khóa công khai của issuer |

Không phải tất cả chứng thư đều có cùng bộ phần mở rộng. Bộ kiểm tra phải thực thi **những ràng buộc áp dụng** theo chuẩn PKI và chính sách bảo mật của JVM, thay vì chỉ tìm chuỗi văn bản của tên CA.

### Ví dụ một đường dẫn chứng thư

~~~text
Truststore của ứng dụng Java
  Example Root CA               <-- trust anchor được chấp nhận
       |
       +-- Example Issuing CA   <-- chứng thư CA trung gian
               |
               +-- directory.example.org
                   SAN: DNS:directory.example.org
                   EKU: TLS Web Server Authentication
~~~

Máy chủ thông thường gửi chứng thư **leaf** (máy chủ) và những chứng thư trung gian cần thiết. Root CA không nhất thiết phải được máy chủ gửi vì bên client đã phải **chủ động tin** trust anchor từ nguồn đáng tin cậy.

**Tin một CA và tin đúng hostname là hai kiểm tra độc lập.** Chứng thư được CA tin cậy ký cho `other.example.org` không được tự động chấp nhận khi ứng dụng định kết nối `directory.example.org`.

## 3. Trình tự xác minh khi bắt tay TLS

Trong kết nối LDAPS, client bắt đầu TLS ngay sau khi mở TCP (cổng quy ước 636). Với StartTLS, client kết nối LDAP (thường qua 389), gửi yêu cầu StartTLS, nhận phản hồi đồng ý, rồi **mới bắt đầu TLS handshake**. Các yêu cầu simple bind phải diễn ra **sau khi** kênh TLS được thiết lập và chấp nhận.

~~~mermaid
flowchart TD
    A["Ứng dụng chọn endpoint LDAP"] --> B["LDAPS hoặc yêu cầu StartTLS"]
    B --> C["TLS handshake: nhận chứng thư server"]
    C --> D{"Xây được đường dẫn tới trust anchor tin cậy?"}
    D -- "Không" --> R["Từ chối kết nối; không LDAP bind"]
    D -- "Có" --> E{"Chữ ký, hiệu lực, ràng buộc PKI và chính sách hợp lệ?"}
    E -- "Không" --> R
    E -- "Có" --> F{"SAN/hostname hoặc IP đích khớp?"}
    F -- "Không" --> R
    F -- "Có" --> G["Chấp nhận TLS theo chính sách"]
    G --> H["Mới thực hiện bind và thao tác LDAP"]
~~~

Trong thực tế, kiểm tra còn bao gồm lựa chọn phiên bản TLS, thuật toán mật mã, tham số bắt tay và các điều kiện PKI khác. Một số chính sách tổ chức yêu cầu kiểm tra chứng thư bị thu hồi; việc này cần được cấu hình và kiểm chứng riêng.

### 3.1. Các bước kiểm tra certificate path

Một trust manager phù hợp trong Java thường:

1. Xây hoặc xác minh đường dẫn từ chứng thư leaf qua các chứng thư intermediate đến một **trust anchor** được truststore chấp nhận.
2. Kiểm tra chữ ký số của các chứng thư trong đường dẫn, thời hạn, cấu trúc, `BasicConstraints` và `Key Usage`/`Extended Key Usage` áp dụng.
3. Áp dụng những chính sách thuật toán, độ dài khóa, giới hạn đường dẫn và các ràng buộc khác của nhà cung cấp Java.
4. Thực hiện kiểm tra thu hồi **nếu chính sách và cấu hình xác minh có bật chức năng đó**.
5. Kết hợp kiểm tra danh tính endpoint để quyết định chấp nhận hay từ chối máy chủ.

Thiếu intermediate, dùng sai truststore, dùng CA không tin cậy hoặc chứng thư hết hạn đều có thể khiến việc xây/xác minh đường dẫn thất bại. **Chứng thư không cần được cấp bởi CA công cộng**: CA nội bộ vẫn hợp lệ khi được tổ chức phê duyệt và cấu hình làm trust anchor đúng cách.

### 3.2. Hostname verification kiểm tra điều gì?

Hostname verification đối chiếu **đích client yêu cầu** với **SAN** trong chứng thư server:

| Đích ứng dụng dùng | SAN của server certificate | Kỳ vọng |
| --- | --- | --- |
| `ldaps://directory.example.org:636` | `DNS:directory.example.org` | Chấp nhận nếu các kiểm tra còn lại đều hợp lệ |
| `ldaps://directory.example.org:636` | `DNS:other.example.org` | Từ chối |
| `ldaps://10.40.2.15:636` | `IP Address:10.40.2.15` | Có thể chấp nhận nếu chain/chính sách hợp lệ |
| `ldaps://10.40.2.15:636` | `DNS:directory.example.org` | Không khớp định danh IP |
| `ldaps://ldap.internal.example.org:636` | `DNS:directory.example.org` | Không khớp, dù DNS trỏ về cùng IP |

Khi cấp chứng thư mới nên khai báo đầy đủ SAN của các tên endpoint mà client thực sự sẽ gọi. Không dựa vào `Common Name` (CN) như giải pháp thay thế mặc định cho SAN. Wildcard DNS, nếu được chính sách cho phép, cũng có giới hạn về số cấp tên miền và phạm vi khớp; không dùng wildcard như cách bỏ qua việc xác định danh tính.

**Lưu ý Java/JNDI:** Các phiên bản JDK và đường thiết lập LDAPS/StartTLS có thể khác nhau về cơ chế mặc định kiểm tra hostname. Có socket factory tùy biến hoặc chiến lược TLS riêng thì cần rà soát thêm. Cách kiểm chứng đáng tin là chủ động kết nối đến máy chủ có **chain hợp lệ nhưng SAN sai**, rồi xác nhận chính ứng dụng từ chối kết nối.

### 3.3. Kiểm tra thu hồi chứng thư có tự xảy ra không?

Kiểm tra thu hồi (revocation) có thể dùng **CRL** hoặc **OCSP** để xác định một chứng thư đã bị CA thu hồi trước khi hết hạn hay chưa. Cơ chế này **không mặc nhiên được thực hiện trong mọi kết nối Java** chỉ vì có truststore. Mức hỗ trợ, cấu hình, mạng truy cập CRL/OCSP và chính sách xử lý khi dịch vụ kiểm tra không khả dụng cần được kiểm thử theo yêu cầu tổ chức.

Không tự khẳng định một cấu hình Spring LDAP có xác minh revocation khi chưa biết chính xác nhà cung cấp JSSE/JDK và thiết lập xác minh đang chạy.

## 4. Truststore được sử dụng ở đâu?

**Truststore** là nguồn tin cậy để client kiểm tra certificate chain. Trong Java, cấu hình JSSE mặc định có thể sử dụng `cacerts` của JDK hoặc một truststore do ứng dụng chỉ định. Đó là truststore **phía client**; nó khác với keystore phía server LDAP lưu khóa riêng của server.

| Thành phần | Vai trò |
| --- | --- |
| Truststore của JVM/client | Chứa các CA/trust anchor mà client tin cậy |
| Chứng thư server | Chứng minh danh tính endpoint LDAP, chứa SAN và khóa công khai |
| Chứng thư intermediate | Nối server certificate với CA gốc/trust anchor |
| Keystore chứa khóa riêng server | Dùng để máy chủ chứng minh quyền sở hữu khóa trong TLS handshake |
| Keystore phía client (khi mTLS) | Lưu khóa riêng và chứng thư client cho TLS hai chiều, nếu hệ thống yêu cầu |

### 4.1. Nhập CA nội bộ đúng quy trình

Giả sử quản trị PKI cung cấp chứng thư CA nội bộ đã được xác minh bằng một kênh đáng tin là `example-directory-root-ca.pem`. Có thể nhập CA đó vào truststore PKCS#12:

~~~bash
# keytool có thể yêu cầu mật khẩu truststore và xác nhận import.
keytool -importcert \
  -alias directory-root-ca \
  -file example-directory-root-ca.pem \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12

# Đọc lại thông tin chứng thư và fingerprint.
keytool -list -v \
  -alias directory-root-ca \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12
~~~

Đối chiếu `Subject`, `Issuer`, fingerprint SHA-256 và nguồn CA bằng thông tin do đơn vị PKI cung cấp qua kênh xác thực. **Không tải chứng thư từ một kết nối đáng ngờ rồi tự động đưa vào truststore**: hành động đó có thể tạo niềm tin sai đối với máy chủ giả.

Nếu máy chủ thiếu chứng thư intermediate cần thiết, cách xử lý thường là cấu hình **server trình bày đúng chuỗi**. Không nên “khắc phục” bằng cách import tùy tiện chứng thư leaf vào truststore mà bỏ qua xác minh danh tính.

### 4.2. Chỉ định truststore cho JVM

Ví dụ khi chạy ứng dụng Java:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/etc/app/security/ldap-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar spring-ldap-service.jar
~~~

Đường dẫn và tên file jar là minh họa. Nếu truststore có mật khẩu, quản lý bằng cơ chế cấp phát secret phù hợp; tránh in bí mật ra log hoặc lịch sử lệnh. Các thuộc tính `javax.net.ssl.*` có phạm vi toàn tiến trình khi thành phần sử dụng JSSE mặc định. Cần kiểm tra tác động tới những kết nối TLS khác như HTTPS, cơ sở dữ liệu hoặc dịch vụ nội bộ. Một custom `SSLContext` hoặc custom socket factory có thể dùng tập CA riêng và không kế thừa những cấu hình mặc định này.

Chỉ thay truststore **không thể sửa lỗi SAN/hostname mismatch**. Khi lỗi nằm ở hostname, phải dùng endpoint đúng hoặc yêu cầu cấp lại chứng thư phù hợp với tên endpoint thật.

## 5. Thực thi xác minh trong Spring LDAP

Trong Spring LDAP, `LdapContextSource` quản lý cách tạo context; các API `LdapTemplate`, `LdapClient` hoặc ODM sử dụng context đó để thực hiện thao tác. Chọn **LDAPS** hoặc **StartTLS** quyết định thời điểm bắt tay TLS:

### 5.1. Cấu hình LDAPS

Ứng dụng Spring Boot có thể sử dụng cấu hình tự động Spring LDAP:

~~~yaml
# application.yml — endpoint, DN giả định
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: cn=ldap-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Nếu tự tạo bean trong Spring Framework, mã tương đương ở mức nguồn kết nối có dạng:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryLdapConfiguration {
    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.bind-dn}") String bindDn,
            @Value("${directory.ldap.bind-password}") String password) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(url); // ví dụ ldaps://directory.example.org:636
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
~~~

Nếu sử dụng bean thủ công ở trên, các khóa cấu hình tương ứng có thể là:

~~~yaml
directory:
  ldap:
    url: ldaps://directory.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=ldap-reader,ou=services,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Hai ví dụ là **hai cách cấu hình thay thế**, không yêu cầu định nghĩa hai context source cho cùng một kết nối. Spring quản lý lifecycle bean `LdapContextSource` khi nó được tạo qua `@Bean`. SSL/TLS truststore và chính sách xác thực máy chủ ở tầng JVM/JNDI vẫn phải được kiểm tra.

### 5.2. StartTLS cần nâng cấp và xác minh trước bind

Với StartTLS, URI `ldap://` chỉ xác định kết nối LDAP ban đầu; chưa có TLS khi mới mở socket. Trong Spring LDAP, có thể cấu hình chiến lược `DefaultTlsDirContextAuthenticationStrategy` để nâng cấp TLS rồi xác thực:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryStartTlsConfiguration {
    @Bean
    public LdapContextSource ldapContextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldap://directory.example.org:389");
        source.setBase("dc=example,dc=org");
        source.setUserDn("cn=ldap-reader,ou=services,dc=example,dc=org");
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
        source.setAuthenticationStrategy(
            new DefaultTlsDirContextAuthenticationStrategy()
        );
        source.setPooled(false);
        return source;
    }
}
~~~

Đây là ví dụ cho **simple bind sau StartTLS**. Trong một số triển khai, chiến lược `ExternalTlsDirContextAuthenticationStrategy` phục vụ cơ chế xác thực **SASL EXTERNAL**; cần lựa chọn dựa trên phương thức xác thực thực tế. Không mặc định rằng tên lớp có chữ “Tls” sẽ phù hợp mọi kiểu bind.

Điều kiện bắt buộc cho StartTLS là:

1. Gửi LDAP StartTLS ExtendedRequest khi chưa có bind nhạy cảm.
2. Chỉ sau khi máy chủ chấp nhận yêu cầu mới thực hiện TLS handshake.
3. Xác minh chứng thư server và hostname theo chính sách TLS.
4. Nếu thành công, mới gửi simple bind và các tìm kiếm/cập nhật; nếu thất bại, **đóng kết nối**.

Trong ví dụ, `setPooled(false)` tránh cơ chế tái sử dụng kết nối JNDI cho source này. Nếu ứng dụng dùng pooling riêng của Spring LDAP hoặc wrapper khác, phải kiểm tra cách pool tạo, nâng cấp TLS, tái sử dụng và đóng context. Không tái sử dụng một kết nối còn ở trạng thái chưa nâng cấp TLS.

### 5.3. Các đường kết nối khác cũng cần xác minh

Ứng dụng có thể tạo nhiều `ContextSource`, cho phép bind bằng tài khoản người dùng cuối, theo LDAP referral hoặc dùng endpoint dự phòng. Việc xác minh TLS cho **một** source không bảo đảm an toàn cho toàn bộ đường truyền:

- Mỗi `ContextSource` dùng cho dữ liệu nhạy cảm phải bật LDAPS hoặc StartTLS bắt buộc.
- Mỗi endpoint dự phòng phải có certificate chain hợp lệ và SAN đúng với hostname trong URL tương ứng.
- Kết nối qua proxy/load balancer phải được phân tích điểm kết thúc TLS và sự bảo vệ ở từng chặng.
- Nếu cho phép referral, phải kiểm tra yêu cầu TLS trên cả kết nối tới máy chủ đích mới.
- Không sửa lỗi chứng thư bằng cách chuyển sang `ldap://` không có StartTLS.

## 6. Kiểm tra server certificate trước khi triển khai

Các lệnh dưới đây chỉ phục vụ môi trường phát triển hoặc kiểm thử được phép. Chúng giúp chẩn đoán **endpoint** nhưng chưa thay thế thử nghiệm trong chính JVM của ứng dụng.

### 6.1. Kiểm tra chứng thư đang có trên đĩa

~~~bash
# Đọc Subject, Issuer, thời hạn, SAN và extensions từ file PEM.
openssl x509 -in directory-server.pem -noout -text

# Xem fingerprint SHA-256 để đối chiếu với thông tin PKI.
openssl x509 -in directory-server.pem -noout -fingerprint -sha256

# In thông tin chứng thư CA trước khi nhập vào truststore.
keytool -printcert -v -file example-directory-root-ca.pem
~~~

Việc nhìn thấy SAN đúng hoặc thời hạn hợp lệ **chưa đủ** để khẳng định toàn bộ certificate chain được chấp nhận. Phải thử xác minh thực tế với CA/trust anchor thích hợp.

### 6.2. Kiểm tra chuỗi chứng thư khi kết nối LDAPS

~~~bash
openssl s_client \
  -connect directory.example.org:636 \
  -servername directory.example.org \
  -showcerts \
  -CAfile example-directory-root-ca.pem \
  -verify_hostname directory.example.org \
  -verify_return_error
~~~

Trong lệnh này:

- `-showcerts` in các chứng thư được server trình bày, giúp tìm intermediate bị thiếu.
- `-CAfile` dùng CA đã xác minh làm nguồn tin cậy cho lần kiểm tra với OpenSSL.
- `-verify_hostname` thực hiện kiểm tra danh tính tên miền đích.
- `-verify_return_error` khiến lỗi xác minh ảnh hưởng kết quả bắt tay thay vì chỉ hiện cảnh báo.

Với chuỗi chứng thư và hostname hợp lệ theo OpenSSL, đầu ra xác minh thường có mã kết quả thành công như `Verify return code: 0 (ok)`. Không chỉ dựa vào dòng “CONNECTED” vì nó chỉ nói về kết nối TCP; cần đọc **kết quả xác minh certificate**.

### 6.3. Kiểm tra chứng thư qua StartTLS

~~~bash
openssl s_client \
  -starttls ldap \
  -connect directory.example.org:389 \
  -showcerts \
  -CAfile example-directory-root-ca.pem \
  -verify_hostname directory.example.org \
  -verify_return_error
~~~

`-starttls ldap` khiến OpenSSL yêu cầu nâng cấp giao thức LDAP trước khi bắt tay TLS. Việc máy chủ phản hồi chấp nhận StartTLS **không có nghĩa** chứng thư hợp lệ: client vẫn phải kiểm tra chain và hostname trong TLS handshake.

OpenSSL có thể dùng chính sách CA/thuật toán khác Java. Vì vậy, kiểm tra thành công bằng OpenSSL chưa bảo đảm `LdapContextSource` sẽ dùng đúng truststore và hostname verifier.

### 6.4. Kiểm tra từ tiến trình Java thật

Ứng dụng cần thực hiện một truy vấn thử nghiệm bằng `LdapTemplate` và quan sát:

1. Kết nối TLS thành công khi chứng thư hợp lệ và hostname chính xác.
2. Bind chỉ được gửi **sau** TLS handshake được chấp nhận.
3. Một chứng thư được CA tin cậy ký nhưng **SAN sai hostname** bị từ chối.
4. Một chứng thư từ CA chưa được tin bị từ chối.
5. Khi StartTLS không được hỗ trợ hoặc TLS handshake thất bại, không có bind trên kết nối rõ.

Đối với môi trường lab, có thể bật chẩn đoán JSSE:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
~~~

Chẩn đoán này giúp phân tích cách chọn trust anchor và xử lý bắt tay, nhưng có thể tạo log rất lớn và tiết lộ metadata kết nối/chứng thư. Chỉ bật tạm thời ở môi trường được phép, bảo vệ log và tắt sau khi điều tra. Không đưa thông tin xác thực LDAP hoặc bí mật thật vào log thử nghiệm.

## 7. Kiểm thử âm tính: chứng minh hệ thống biết từ chối

Kết nối hợp lệ hoạt động chỉ chứng minh trường hợp thành công. Để xác minh chính sách TLS thật sự có hiệu lực, phải thử những trường hợp **chứng thư không hợp lệ** trong lab do nhóm kiểm soát.

| Thử nghiệm | Thiết lập lab | Hành vi phải quan sát |
| --- | --- | --- |
| CA không tin cậy | Server certificate từ CA không nằm trong truststore được chấp nhận | TLS bị từ chối; không bind |
| Sai hostname | SAN là `other.example.org`, client gọi `directory.example.org` | TLS bị từ chối dù chain hợp lệ |
| Hết hạn chứng thư | Server certificate đã vượt `Not After` | TLS bị từ chối |
| Chứng thư chưa có hiệu lực | Client có thời gian trước `Not Before` | TLS bị từ chối theo kiểm tra thời gian |
| Thiếu intermediate | Server không trình bày chain đủ để client xây path, và client không có trung gian phù hợp | Xác minh chain thất bại |
| Cert/key usage không phù hợp | Chứng thư bị ràng buộc mục đích không dùng cho TLS server | TLS bị từ chối theo chính sách |
| StartTLS bị từ chối | Server phản hồi lỗi StartTLS | Không gửi simple bind trên phiên rõ |
| StartTLS chấp nhận nhưng handshake lỗi | Client không tin CA hoặc gặp lỗi TLS | Đóng kết nối trước bind |
| Endpoint dự phòng sai chứng thư | Đổi sang node thứ hai với SAN không khớp | Không hạ cấp sang kết nối rõ |

Không cần lấy chứng thư thật từ máy chủ sản xuất để tạo trường hợp sai: có thể dựng CA và endpoint thử nghiệm do đội kiểm thử kiểm soát. Điều quan trọng là đo được hành vi **fail closed** của ứng dụng, bao gồm retry, pool và referral nếu chúng được sử dụng.

### Phân biệt lỗi TLS với lỗi LDAP bind

| Dấu hiệu | Thời điểm thường gặp | Cách xử lý |
| --- | --- | --- |
| `SSLHandshakeException` | Trong TLS handshake | Kiểm tra certificate chain, thuật toán, truststore, hostname |
| `PKIX path building failed` | Khi xác minh đường dẫn chứng thư | Kiểm tra CA, intermediate và truststore đang dùng |
| `No subject alternative DNS name matching` hoặc lỗi tên endpoint tương đương | Khi hostname verification | Kiểm tra URL, DNS và SAN, cấp chứng thư đúng |
| Chứng thư hết hạn | Khi kiểm tra hiệu lực | Gia hạn/cấp lại chứng thư, kiểm tra đồng hồ |
| `invalidCredentials` sau khi TLS đã thành công | Trong LDAP bind | Xem DN/mật khẩu và chính sách xác thực; không sửa TLS nếu TLS đã hợp lệ |

Nội dung thông báo lỗi cụ thể còn phụ thuộc JDK và thư viện LDAP. Trong Java, lỗi TLS từ JNDI có thể được Spring LDAP bao bọc thành một exception khác; khi chẩn đoán, xem chuỗi nguyên nhân (cause chain) thay vì chỉ xét tên exception ngoài cùng.

## 8. Sự cố thường gặp và cách sửa đúng

### Trường hợp A: có root CA nhưng vẫn thấy `PKIX path building failed`

**Bối cảnh:** Truststore đã chứa `Example Root CA` nhưng LDAP server chỉ gửi leaf certificate do `Example Issuing CA` ký và thiếu intermediate `Example Issuing CA`.

**Phân tích:** Client có thể không đủ thông tin để xây đường dẫn từ leaf tới trust anchor. Cần kiểm tra server chain bằng `openssl s_client -showcerts` và đối chiếu với đường dẫn PKI được cấp.

**Khắc phục:** Cấu hình server trình bày đủ intermediate cần thiết, rồi thử lại với truststore đúng của JVM. Không xóa xác thực chứng thư để tránh lỗi.

### Trường hợp B: cert hợp lệ nhưng SAN không khớp

**Bối cảnh:** Ứng dụng gọi `ldaps://directory.example.org:636`, nhưng cert có `DNS:ldap-node-01.example.org`. Hai tên có thể trỏ cùng IP, nhưng danh tính endpoint vẫn không khớp.

**Khắc phục:** Dùng tên endpoint thực sự được phép trong SAN nếu đó là đích hợp lệ, hoặc cấp lại cert có `DNS:directory.example.org` sau khi xác thực quyền sở hữu tên. Không tắt hostname verification.

### Trường hợp C: OpenSSL thành công, Spring LDAP thất bại

**Nguyên nhân khả dĩ:** JVM đang dùng JDK khác dự kiến, truststore không đúng đường dẫn, thiếu CA trong truststore của Java, custom socket factory, chính sách thuật toán khác hoặc hostname validation khác.

**Hướng kiểm tra:** Xác nhận JVM thực tế, các thuộc tính JSSE, truststore đang được load, chain server và hostname; bật JSSE debug ở môi trường lab, sau đó thử lại bằng `LdapTemplate`.

### Trường hợp D: StartTLS lỗi nhưng code cố kết nối lại qua LDAP rõ

**Vấn đề:** Mật khẩu simple bind có nguy cơ lộ nếu retry dùng `ldap://` mà không thực hiện nâng cấp TLS. Dữ liệu đọc cũng có thể lộ dù tài khoản bind không có quyền ghi.

**Khắc phục:** Dừng kết nối khi StartTLS bị từ chối hoặc xác minh chứng thư thất bại, sửa server/certificate/policy và chỉ retry qua một đường TLS hợp lệ. Không chuyển chiến lược xác thực sang simple bind trên kết nối rõ.

## 9. Bài tập thực hành

Một ứng dụng Spring LDAP đọc thuộc tính `cn`, `mail` và `memberOf` qua `LdapTemplate`. Cấu hình hiện tại:

~~~yaml
spring:
  ldap:
    urls: ldaps://directory.hr.example.org:636
    base: dc=hr,dc=example,dc=org
    username: cn=app-reader,ou=services,dc=hr,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Máy chủ gửi chuỗi:

~~~text
Leaf:
  Subject: CN=ldap-node-01.hr.example.org
  SAN: DNS:ldap-node-01.hr.example.org
  Issuer: HR Issuing CA
  Validity: còn hiệu lực
Intermediate:
  Subject: HR Issuing CA
  Issuer: HR Root CA
JVM truststore:
  HR Root CA (đã được tổ chức xác minh và tin cậy)
~~~

**Câu hỏi:**

1. Trong giả định chữ ký và chuỗi đều hợp lệ, còn điều kiện nào khiến kết nối phải bị từ chối?
2. Có thể sửa lỗi bằng cách import leaf certificate vào truststore rồi tắt hostname verification không? Vì sao?
3. Nếu đổi tên URL sang `ldaps://ldap-node-01.hr.example.org:636`, những gì cần kiểm chứng trước khi chấp nhận giải pháp?
4. Làm thế nào thử được cùng chính sách khi ứng dụng chuyển sang StartTLS?
5. Nêu ba kiểm thử âm tính cần có trước khi phát hành.

**Gợi ý lời giải:**

1. URL gọi `directory.hr.example.org` nhưng SAN chỉ chứa `ldap-node-01.hr.example.org`, nên hostname verification phải từ chối dù truststore tin CA.
2. Không. Import leaf một cách tùy tiện và vô hiệu hóa hostname phá vỡ việc xác minh danh tính đúng endpoint; ứng dụng có thể nhận kết nối từ máy chủ không mong muốn.
3. Phải xác nhận tên mới thật sự đại diện endpoint LDAP được phép, có DNS/định tuyến đúng, SAN khớp, toàn bộ certificate chain hợp lệ và chính sách truy cập không đổi. Nếu hostname cũ là tên dịch vụ chính thức, hướng phù hợp hơn có thể là cấp lại cert với SAN bao gồm tên đó.
4. Dùng `ldap://` với chiến lược StartTLS bắt buộc trong `LdapContextSource`, kiểm tra chain/hostname như LDAPS và xác minh TLS hoàn tất trước bind; khi lỗi phải ngừng phiên.
5. Ví dụ: CA không tin cậy, SAN sai hostname, server certificate hết hạn, thiếu intermediate, hoặc StartTLS bị từ chối. Kỳ vọng không có bind trên kênh rõ trong mọi nhánh lỗi.

## 10. Checklist trước khi đưa hệ thống vào vận hành

- **Định danh endpoint:** liệt kê hostname/IP được ứng dụng dùng cho mọi máy chủ LDAP, dự phòng, proxy và referral.
- **Certificate chain:** server gửi chain đủ để xây đường dẫn tin cậy; chữ ký, thời hạn, CA constraints, thuật toán và mục đích sử dụng hợp lệ.
- **Nguồn tin cậy:** truststore JVM chứa đúng CA đã xác minh; không tự import certificate không rõ nguồn.
- **Hostname verification:** ứng dụng thực tế từ chối chain hợp lệ nhưng SAN sai; không có tùy chọn bỏ qua xác minh.
- **Thứ tự kết nối:** LDAPS bắt tay TLS trước LDAP; StartTLS hoàn tất nâng cấp và TLS handshake trước simple bind.
- **Ứng dụng thực tế:** kiểm tra đúng `ContextSource` được `LdapTemplate`, `LdapClient`, ODM hoặc luồng xác thực sử dụng.
- **Các trường hợp lỗi:** không fallback sang LDAP rõ, không tái sử dụng context TLS lỗi trong pool, có log chẩn đoán phù hợp mà không tiết lộ bí mật.
- **Vòng đời chứng thư:** giám sát ngày hết hạn, chuẩn bị gia hạn và thay CA, kiểm thử endpoint dự phòng; xác định rõ chính sách thu hồi CRL/OCSP nếu tổ chức yêu cầu.

**Điểm cốt lõi:** TLS an toàn trong Spring LDAP yêu cầu **vừa kiểm tra sự tin cậy của certificate chain, vừa kiểm tra đúng danh tính server** trước mọi thao tác LDAP nhạy cảm. Kết nối thành công về mặt mạng hoặc nhận phản hồi StartTLS chưa đủ; chính sách phải được chứng minh bằng kiểm thử từ JVM thật và cả những trường hợp kết nối cần bị từ chối.
