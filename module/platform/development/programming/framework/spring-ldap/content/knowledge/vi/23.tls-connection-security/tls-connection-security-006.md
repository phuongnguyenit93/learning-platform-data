# External TLS authentication strategy

## 1. Bài toán: xác thực LDAP bằng chứng chỉ ứng dụng

Trong một dịch vụ Java dùng **Spring LDAP**, `LdapTemplate`, `LdapClient` hoặc ODM thực hiện tìm kiếm, xác thực và cập nhật entry bằng những kết nối do `ContextSource` cung cấp. Cách cấu hình quen thuộc là kết nối LDAPS hoặc StartTLS, sau đó **simple bind** bằng DN và mật khẩu tài khoản dịch vụ.

Một số tổ chức muốn xác thực ứng dụng theo **chứng chỉ client TLS** thay vì phân phối mật khẩu LDAP cho từng dịch vụ. Máy chủ thư mục kiểm tra chứng chỉ client và gắn danh tính chứng chỉ với danh tính LDAP có quyền truy cập phù hợp. Với mô hình này, Spring LDAP cung cấp `ExternalTlsDirContextAuthenticationStrategy`, một chiến lược xác thực sử dụng **StartTLS và SASL EXTERNAL**.

Ví dụ, dịch vụ quản lý nhân sự cần tìm `uid`, `mail` và `memberOf` trong thư mục LDAP. Tổ chức cấp chứng chỉ client riêng cho dịch vụ, rồi quy định máy chủ LDAP ánh xạ chứng chỉ đó tới tài khoản chỉ đọc. Ứng dụng thực hiện StartTLS, trình bày chứng chỉ client trong quá trình bắt tay theo yêu cầu máy chủ, tiếp đến dùng **SASL EXTERNAL bind** để LDAP server nhận diện danh tính ứng dụng. Nếu bất kỳ bước nào thất bại, ứng dụng phải ngừng thao tác LDAP.

Trong chương **TLS và bảo mật kết nối**, bài học này giúp người học:

- Phân biệt **TLS mã hóa đường truyền**, **mTLS xác thực client ở tầng TLS** và **SASL EXTERNAL xác thực danh tính LDAP**.
- Hiểu cách `ExternalTlsDirContextAuthenticationStrategy` tham gia vòng đời `LdapContextSource`.
- Cấu hình keystore chứa chứng chỉ/khóa client, truststore chứa CA đáng tin và chính sách xác minh máy chủ.
- Xác minh quyền LDAP thực tế, xử lý lỗi và kiểm thử các trường hợp TLS hoặc SASL EXTERNAL bị từ chối.

## 2. Hiểu đúng mTLS và SASL EXTERNAL

Ba cơ chế có liên quan nhưng thực hiện những công việc khác nhau:

| Cơ chế | Tầng xử lý | Trả lời câu hỏi gì? |
| --- | --- | --- |
| TLS (LDAPS/StartTLS) | Kết nối mạng | Nội dung LDAP có được truyền trên kênh bảo mật và client có xác minh đúng máy chủ không? |
| Mutual TLS (mTLS) | Bắt tay TLS | Máy chủ có yêu cầu, kiểm tra và chấp nhận **chứng chỉ client** không? |
| SASL EXTERNAL | Xác thực LDAP | Máy chủ có chấp nhận dùng danh tính do lớp ngoài (ví dụ TLS client certificate) cung cấp để gán quyền LDAP không? |

Đây là các bước riêng. **Có TLS không đồng nghĩa có mTLS**: TLS thông thường chỉ yêu cầu máy chủ trình bày chứng chỉ. **Có mTLS cũng chưa đồng nghĩa đã LDAP bind**: máy chủ thư mục vẫn phải hỗ trợ cơ chế SASL EXTERNAL và ánh xạ danh tính được TLS xác thực tới danh tính LDAP.

Ngược lại, SASL EXTERNAL không bảo đảm tài khoản có quyền sửa entry. Quyền đọc/ghi do **ACL và chính sách của LDAP server** quyết định.

### 2.1. So sánh hai chiến lược TLS của Spring LDAP

| Tiêu chí | `DefaultTlsDirContextAuthenticationStrategy` | `ExternalTlsDirContextAuthenticationStrategy` |
| --- | --- | --- |
| Thiết lập kênh an toàn | Nâng cấp LDAP sang TLS qua StartTLS | Nâng cấp LDAP sang TLS qua StartTLS |
| Cách LDAP bind | SIMPLE, sử dụng DN và mật khẩu | SASL EXTERNAL, sử dụng danh tính do lớp TLS cung cấp |
| Thông tin cần cho xác thực LDAP | Bind DN và password | Chứng chỉ client cùng khóa riêng, cấu hình mapping phía máy chủ; thường không cần mật khẩu LDAP |
| Yêu cầu server | Hỗ trợ StartTLS và SIMPLE bind trên TLS | Hỗ trợ StartTLS, client-certificate TLS và SASL EXTERNAL |
| Sai sót điển hình | Gửi simple bind trên kết nối chưa được TLS bảo vệ | Có chứng chỉ client nhưng thiếu SASL EXTERNAL/mapping, hoặc dùng nhầm SIMPLE bind |

Trong Java, hai lớp trên cùng kế thừa `AbstractTlsDirContextAuthenticationStrategy` và được gắn qua `LdapContextSource#setAuthenticationStrategy(...)`. Việc lựa chọn phụ thuộc **phương thức xác thực** mà LDAP server hỗ trợ, không chỉ phụ thuộc nhu cầu mã hóa.

**Phạm vi chính của chiến lược External TLS:** mở kết nối `ldap://`, yêu cầu **StartTLS**, thương lượng TLS và áp dụng SASL EXTERNAL. URL `ldaps://` đã thiết lập TLS ngay từ đầu; không nên mặc định ghép `ldaps://` với chiến lược *có bước StartTLS* mà chưa kiểm chứng tương thích. Nếu hạ tầng muốn SASL EXTERNAL trên LDAPS, cần kiểm tra cơ chế hỗ trợ của client/JNDI và cấu hình riêng phù hợp.

## 3. Luồng hoạt động từ ContextSource đến LDAP server

~~~mermaid
sequenceDiagram
    participant App as LdapTemplate/LdapClient
    participant CS as LdapContextSource
    participant Dir as LDAP server
    App->>CS: Yêu cầu LDAP context
    CS->>Dir: Mở TCP ldap://:389
    CS->>Dir: StartTLS ExtendedRequest
    Dir-->>CS: Chấp nhận StartTLS
    CS->>Dir: TLS handshake; client xác minh server certificate
    Dir->>CS: TLS CertificateRequest (khi cấu hình mTLS)
    CS->>Dir: Chứng chỉ client và bằng chứng sở hữu private key
    Dir->>Dir: Kiểm tra chứng chỉ client theo chính sách
    Note over CS,Dir: Kênh TLS đã thiết lập và xác minh
    CS->>Dir: LDAP SASL bind: EXTERNAL
    Dir->>Dir: Ánh xạ TLS identity sang LDAP authorization identity
    Dir-->>CS: BindResponse thành công
    CS-->>App: Context đã xác thực
    App->>Dir: SearchRequest hoặc thao tác entry qua TLS
    Dir-->>App: Kết quả theo ACL LDAP
~~~

Sơ đồ rút gọn các bước của TLS handshake; thứ tự thông điệp chi tiết còn phụ thuộc phiên bản TLS và server. Điều kiện quan trọng là **server certificate được client xác minh, client certificate được server chấp nhận nếu chính sách yêu cầu, và SASL EXTERNAL bind thành công trước khi dùng quyền truy cập thư mục**.

Trong thực tế, máy chủ có thể từ chối một chứng chỉ client hợp lệ ở tầng TLS vì không có quy tắc ánh xạ danh tính LDAP phù hợp; cũng có thể chấp nhận EXTERNAL nhưng cấp quyền hạn chế. Cần kiểm tra cả hai lớp xác thực và ACL, thay vì suy đoán từ kết quả bắt tay TLS.

### 3.1. Lớp bảo mật nào phát hiện lỗi nào?

| Tình huống | Lớp phát hiện thường gặp | Kết quả mong đợi |
| --- | --- | --- |
| Chứng chỉ LDAP server không đáng tin | Java TLS trust manager | Không thiết lập phiên TLS |
| Chứng chỉ server sai hostname/SAN | Java/JNDI hostname verification | Từ chối endpoint |
| Client không có private key/chứng chỉ phù hợp | TLS handshake, hoặc server policy | Không xác thực mTLS thành công |
| Server không hỗ trợ SASL EXTERNAL | LDAP SASL bind | Báo lỗi xác thực/cơ chế không hỗ trợ |
| Server không ánh xạ được client certificate | Server mapping/SASL authorization | Từ chối hoặc không cấp danh tính dự kiến |
| Mapping đúng nhưng không được đọc `ou=people` | LDAP access control | Search bị từ chối hoặc không trả dữ liệu theo chính sách |

## 4. Chuẩn bị máy chủ và danh tính trước khi viết Java

`ExternalTlsDirContextAuthenticationStrategy` **không tự cấu hình server**. Trước khi triển khai, người quản trị phải bảo đảm:

1. LDAP endpoint hỗ trợ **StartTLS** và có chứng chỉ server hợp lệ cho đúng hostname, với chuỗi CA đáng tin.
2. TLS server được cấu hình **yêu cầu hoặc chấp nhận chứng chỉ client**, đồng thời kiểm tra CA phát hành chứng chỉ client, hiệu lực và ràng buộc sử dụng phù hợp.
3. Máy chủ có cơ chế **SASL EXTERNAL**, cho phép dùng danh tính do TLS đã xác thực để bind.
4. Có quy tắc chuyển chứng chỉ client/identity từ tầng TLS sang một **authorization identity LDAP** hợp lệ. Cách ánh xạ phụ thuộc sản phẩm (ví dụ OpenLDAP, 389 Directory Server hoặc máy chủ khác).
5. Authorization identity được cấp đúng quyền theo nguyên tắc **least privilege**, ví dụ chỉ tìm kiếm người dùng/nhóm cần thiết.
6. Có quy trình cấp phát, thu hồi và thay mới chứng chỉ client, bảo vệ khóa riêng, và thử nghiệm khi chứng chỉ hết hạn.

Không phải LDAP server nào cũng triển khai cùng cách ánh xạ chủ thể X.509 sang DN. Một số máy chủ yêu cầu cấu hình nhận diện chứng chỉ client ở tầng TLS, một số dùng quy tắc mapping định danh SASL. Không thể “sửa” lỗi mapping chỉ bằng thay DN trong `LdapContextSource`, vì danh tính EXTERNAL được suy ra từ cơ chế xác thực bên ngoài.

### 4.1. Quy tắc quyền hạn rõ ràng

Ví dụ máy chủ ánh xạ chứng chỉ của dịch vụ `people-lookup` thành một authorization identity có quyền tìm kiếm `ou=people,dc=example,dc=org` nhưng không có quyền sửa thành viên nhóm. Khi ấy:

- Thao tác `search` hợp lệ có thể thành công.
- Thao tác `modify` trên `memberOf` phải bị ACL từ chối.
- Nếu chứng chỉ đã bị thu hồi hoặc thay bằng chứng chỉ không được phép, client phải mất quyền kết nối/xác thực theo chính sách.

Lưu ý: **chứng chỉ client không được dùng làm “quyền quản trị” mặc định**. Server phải kiểm tra cả danh tính và quyền truy cập cụ thể.

## 5. Chuẩn bị Java keystore và truststore

Trong trường hợp TLS hai chiều, ứng dụng Java có hai nhu cầu khác nhau:

| Cấu hình phía ứng dụng | Thường chứa | Vai trò |
| --- | --- | --- |
| `javax.net.ssl.keyStore` | Khóa riêng client cùng chuỗi chứng chỉ client | Cung cấp danh tính TLS của ứng dụng khi server yêu cầu |
| `javax.net.ssl.trustStore` | CA/trust anchor được phép tin | Xác minh certificate chain của LDAP server |

**Keystore không thay thế truststore.** Việc client có chứng chỉ riêng không có nghĩa nó tự động tin đúng server. Tương tự, truststore chứa CA server không làm máy chủ tự động chấp nhận chứng chỉ client.

### 5.1. Chứng chỉ client cần phù hợp mục đích

Thông thường tổ chức/PKI sẽ cấp private key và chứng chỉ client với `Extended Key Usage` phù hợp, chẳng hạn `clientAuth` khi chính sách yêu cầu. Chứng chỉ client phải thuộc một CA mà LDAP server chấp nhận, còn khóa riêng phải được bảo vệ với quyền truy cập hạn chế.

Nếu được bàn giao dưới dạng PKCS#12 (`.p12`/`.pfx`), có thể kiểm tra **thông tin không nhạy cảm** của keystore:

~~~bash
# Kiểm tra alias/chứng chỉ; keytool sẽ hỏi mật khẩu store.
keytool -list -v \
  -keystore /etc/app/security/ldap-client.p12 \
  -storetype PKCS12
~~~

Tệp này có thể chứa **private key**, vì vậy không đưa vào kho mã nguồn, artifact công khai, ảnh chụp lỗi hoặc file đính kèm để chia sẻ tùy tiện. Nếu dùng HSM hoặc kho secret của môi trường, cách tích hợp key material có thể khác với JVM system properties; phải kiểm tra socket factory/SSLContext sử dụng thực tế.

### 5.2. Truststore cho certificate server

Giả sử tổ chức cấp tệp CA đáng tin `directory-root-ca.pem` qua kênh đã xác minh:

~~~bash
keytool -importcert \
  -alias directory-root \
  -file directory-root-ca.pem \
  -keystore /etc/app/security/ldap-trust.p12 \
  -storetype PKCS12

keytool -list -v \
  -alias directory-root \
  -keystore /etc/app/security/ldap-trust.p12 \
  -storetype PKCS12
~~~

Trước khi nhập, đối chiếu fingerprint và thông tin CA với bản ghi từ quản trị PKI. Không nhập chứng chỉ từ một endpoint khả nghi chỉ để tắt lỗi xác minh. Đồng thời kiểm tra **hostname/SAN** của LDAP server; chain hợp lệ nhưng hostname sai vẫn phải bị từ chối.

### 5.3. Truyền cấu hình cho JVM

Có thể dùng các thuộc tính JSSE khi khởi chạy ứng dụng, thay đường dẫn theo môi trường:

~~~text
-Djavax.net.ssl.keyStore=/etc/app/security/ldap-client.p12
-Djavax.net.ssl.keyStoreType=PKCS12
-Djavax.net.ssl.trustStore=/etc/app/security/ldap-trust.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Mật khẩu keystore/truststore, nếu được yêu cầu, cần cung cấp bằng cách quản lý bí mật phù hợp với hệ thống triển khai. Tránh gõ secret trực tiếp trong dòng lệnh được lưu lịch sử, log CI hoặc tệp cấu hình công khai. Các thuộc tính `javax.net.ssl.keyStorePassword` và `javax.net.ssl.trustStorePassword` là những thiết lập JSSE có thể liên quan, nhưng **đường phân phối giá trị** phải được thiết kế phù hợp chính sách bảo vệ bí mật.

Nếu sử dụng `SSLSocketFactory` hoặc `SSLContext` tùy biến, hãy xác minh nó nạp đúng key material và trust anchors. Không mặc định cấu hình JVM luôn có hiệu lực cho mọi library tùy biến.

## 6. Cấu hình ExternalTlsDirContextAuthenticationStrategy

### 6.1. Spring LDAP với LdapContextSource

Ví dụ sau tập trung vào cấu hình **StartTLS và SASL EXTERNAL**. Chứng chỉ client/khóa riêng và truststore được cung cấp qua cấu hình TLS của JVM trong môi trường triển khai.

~~~yaml
# application.yml
directory:
  ldap:
    url: ldap://directory.example.org:389
    base: dc=example,dc=org
~~~

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.ExternalTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class ExternalTlsLdapConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);                 // ldap://...:389
        source.setBase(base);
        source.setAnonymousReadOnly(false);
        source.setPooled(false);           // Không dùng JNDI native pooling với StartTLS

        source.setAuthenticationStrategy(
            new ExternalTlsDirContextAuthenticationStrategy()
        );
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

Trong cấu hình này, ứng dụng không khai báo `setUserDn` và `setPassword` cho simple bind, vì mục tiêu là **SASL EXTERNAL với chứng chỉ client**. Chính máy chủ LDAP quyết định authorization identity dựa trên danh tính bên ngoài đã xác thực; điều đó không có nghĩa `LdapContextSource` tự tạo chứng chỉ client hoặc tự cấu hình mapping của server.

Spring quản lý lifecycle khởi tạo bean `LdapContextSource`. Nếu khởi tạo trực tiếp bên ngoài container, cần thực hiện đúng lifecycle của Spring LDAP trước khi lấy context. Ví dụ định nghĩa bean trên chỉ minh họa cấu hình; để chạy được, môi trường còn cần endpoint LDAP hỗ trợ StartTLS, chứng chỉ client/CA hợp lệ, SASL EXTERNAL và quy tắc ánh xạ server.

### 6.2. Vì sao không dùng riêng cấu hình spring.ldap.urls?

Ví dụ sau **chưa đủ** để xác thực SASL EXTERNAL:

~~~yaml
spring:
  ldap:
    urls: ldap://directory.example.org:389
~~~

URI `ldap://` chỉ xác định điểm kết nối LDAP ban đầu. Nó không tự kích hoạt StartTLS, không trình bày chứng chỉ client và không tự chuyển sang EXTERNAL bind. Cần bảo đảm bean `LdapContextSource` mà `LdapTemplate`/`LdapClient` sử dụng **thực sự có** `ExternalTlsDirContextAuthenticationStrategy`.

Nếu ứng dụng Spring Boot vừa dùng auto-configuration vừa khai báo context source thủ công, hãy kiểm tra bean được inject vào mỗi đường truy cập. Nhiều `ContextSource`, kết nối JNDI trực tiếp, endpoint dự phòng hoặc referral có thể dẫn đến những đường kết nối không dùng chiến lược đã định.

### 6.3. Thay đổi hành vi xác minh TLS

`ExternalTlsDirContextAuthenticationStrategy` kế thừa các tùy chọn của `AbstractTlsDirContextAuthenticationStrategy`, trong đó có:

| API | Vai trò | Khuyến nghị |
| --- | --- | --- |
| `setHostnameVerifier(...)` | Đặt verifier tùy biến cho chứng chỉ server ở bước StartTLS | Giữ mặc định khi phù hợp; nếu tùy biến phải xác minh danh tính thật, **không** luôn trả về `true` |
| `setSslSocketFactory(...)` | Đặt socket factory cho StartTLS handshake | Chỉ tùy biến khi có nhu cầu quản lý SSLContext/key/trust rõ ràng; kiểm thử mTLS thực tế |
| `setShutdownTlsGracefully(...)` | Chọn có thực hiện kết thúc TLS rõ ràng trước khi đóng context | Mặc định `false`; cần kiểm thử vì server LDAP khác nhau về cách đóng StartTLS |

Ví dụ khi cần thay đổi hành vi đóng TLS:

~~~java
ExternalTlsDirContextAuthenticationStrategy strategy =
    new ExternalTlsDirContextAuthenticationStrategy();

// Chỉ bật khi server LDAP hỗ trợ đóng StartTLS theo cách này.
strategy.setShutdownTlsGracefully(true);

source.setAuthenticationStrategy(strategy);
~~~

Đoạn mã rút gọn này giả định biến `source` đã tồn tại. Không bật `setShutdownTlsGracefully(true)` tùy tiện: một số server không hỗ trợ hành vi shutdown được yêu cầu. Dùng mặc định `false` khi chưa có nhu cầu hoặc bằng chứng vận hành rõ ràng.

**Không thiết lập hostname verifier bỏ qua chứng chỉ**, không tự hạ cấp sang LDAP không TLS sau lỗi và không suy đoán rằng xác thực client certificate là thành công chỉ vì kết nối TCP mở được.

## 7. Truy vấn thư mục sau khi SASL EXTERNAL bind

Sau khi source tạo context đã xác thực, mã truy vấn bằng `LdapTemplate` vẫn có hình thức quen thuộc. Ví dụ tìm tên hiển thị của một người dùng:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class PeopleDirectory {
    private final LdapTemplate ldapTemplate;

    public PeopleDirectory(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("displayName").get()
        );
    }
}
~~~

Đoạn mã `search` không có logic liên quan đến chứng chỉ: việc thương lượng TLS, SASL EXTERNAL bind và mở context phải được xử lý ở `LdapContextSource`. Tương tự, `LdapClient` và ODM phải sử dụng context source được cấu hình đúng.

Kết quả tìm kiếm phụ thuộc **ACL của authorization identity** trên server. Nếu server ánh xạ client certificate sang danh tính không có quyền đọc `displayName`, truy vấn sẽ thất bại hoặc bị lọc theo chính sách dù TLS và EXTERNAL bind đã hoạt động.

### 7.1. Phân biệt client identity và người dùng nghiệp vụ

Chứng chỉ dịch vụ dùng để xác thực **ứng dụng gọi thư mục**. Nó không tự xác thực người dùng cuối của một phiên web hay cấp quyền LDAP riêng theo từng người dùng đó. Nếu ứng dụng cần xác minh mật khẩu người dùng cuối, phải thiết kế quy trình riêng (ví dụ LDAP bind theo người dùng trên TLS) và bảo đảm quyền ứng dụng không bị lạm dụng để vượt qua kiểm tra nghiệp vụ.

Không dùng cùng một chứng chỉ client/khóa riêng cho mọi dịch vụ nếu tổ chức cần phân tách danh tính và thu hồi theo ứng dụng; cấp chứng chỉ/identity theo phạm vi và chính sách thích hợp.

## 8. Kiểm tra với công cụ LDAP và Java

### 8.1. Phân biệt kiểm tra TLS và kiểm tra SASL

Kiểm tra TLS có thể dùng OpenSSL:

~~~bash
openssl s_client \
  -starttls ldap \
  -connect directory.example.org:389 \
  -servername directory.example.org \
  -verify_hostname directory.example.org \
  -CAfile directory-root-ca.pem \
  -cert client.crt \
  -key client.key \
  -verify_return_error
~~~

Trong lệnh thử nghiệm này, `-cert` và `-key` chỉ định chứng chỉ và private key **giả/lab** của client, còn `-CAfile` là nguồn CA tin server LDAP. Nếu server không yêu cầu chứng chỉ client trong TLS handshake, việc truyền hai tham số này chưa chứng minh server đã xác thực mTLS. OpenSSL kiểm tra TLS, **không thực hiện SASL EXTERNAL bind**.

Chỉ chạy các lệnh với tài khoản và certificate thử nghiệm được phép; private key cần được bảo vệ, không đưa lên repository, log hay hệ thống chia sẻ công khai.

### 8.2. Thử SASL EXTERNAL với ldapwhoami

Với công cụ OpenLDAP, có thể dùng `ldapwhoami` để xem authorization identity sau khi EXTERNAL bind:

~~~bash
# Cấu hình CA và client certificate/key qua cấu hình OpenLDAP client
# trong lab, sau đó thực hiện StartTLS và SASL EXTERNAL.
ldapwhoami \
  -H ldap://directory.example.org:389 \
  -ZZ \
  -Y EXTERNAL
~~~

`-ZZ` yêu cầu StartTLS thành công; `-Y EXTERNAL` yêu cầu SASL EXTERNAL. Công cụ OpenLDAP dùng **cấu hình TLS riêng của nó** (CA, chứng chỉ client và khóa riêng), không tự đọc JVM keystore. Xem kết quả và log server để xác minh server đã ánh xạ chứng chỉ client tới đúng authorization identity dự kiến.

Nếu chỉ dùng `ldapwhoami -Y EXTERNAL` mà không có TLS client certificate thực sự được server xác minh, thao tác có thể bị từ chối. Một số LDAP server không hỗ trợ EXTERNAL trên giao thức/kênh đã chọn hoặc có chính sách ánh xạ riêng.

### 8.3. Kiểm thử qua Spring LDAP/JVM thực tế

Khi đã xác minh server và công cụ bên ngoài, chạy cùng thao tác `search` bằng bean `LdapContextSource` của ứng dụng Java. Có thể bật JSSE debug **tạm thời trong môi trường lab** để xem quá trình chọn certificate:

~~~text
-Djavax.net.debug=ssl,handshake,keymanager,trustmanager
~~~

Tìm bằng chứng cho các bước:

1. Client mở đúng endpoint `ldap://` và phát StartTLS request.
2. Java xác minh server certificate chain và hostname.
3. Khi server yêu cầu, JSSE chọn chứng chỉ client và chứng minh sở hữu private key phù hợp.
4. TLS handshake thành công, sau đó LDAP SASL EXTERNAL bind thành công.
5. Máy chủ xác định authorization identity/ACL đúng; thao tác `LdapTemplate` trả kết quả theo quyền.

Các bản ghi debug có thể chứa metadata kết nối và thông tin chứng chỉ; không bật thường trực trong production hoặc chia sẻ log chưa kiểm soát.

## 9. Pooling, vòng đời TLS và sai lệch danh tính

Cả `DefaultTlsDirContextAuthenticationStrategy` và `ExternalTlsDirContextAuthenticationStrategy` đều dùng StartTLS, vì vậy phải quan tâm vòng đời kết nối:

- **Tắt native JNDI LDAP connection pooling** đối với StartTLS. Trong ví dụ, `source.setPooled(false)` thể hiện chủ đích đó. Pooling mặc định của Spring LDAP/JNDI không được tùy tiện bật chỉ vì handshake TLS tốn tài nguyên.
- Nếu cần tối ưu kết nối, cân nhắc **Spring LDAP pooling support** và kiểm thử đầy đủ việc cấp phát, kiểm tra, thu hồi, đóng context cùng phiên TLS.
- Nếu thay đổi chứng chỉ client hoặc truststore, các kết nối TLS đã mở có thể đang dùng danh tính/chính sách cũ. Cần có cách quản lý vòng đời pool, giải phóng kết nối và xác minh chứng chỉ mới đã có hiệu lực.
- Nếu server trả referral dẫn sang LDAP endpoint khác, mỗi kết nối mới phải đáp ứng chính sách StartTLS, chứng chỉ và ánh xạ danh tính; không tự thừa kế quyền/phiên TLS cũ.
- Nếu có nhiều môi trường hoặc tenant, không tái sử dụng nhầm context được xác thực bằng chứng chỉ của tenant này cho tenant khác.

`setShutdownTlsGracefully` có mặc định `false`. Khi muốn thay đổi, kiểm thử với LDAP server cụ thể; việc kết thúc TLS có thể phụ thuộc cách server đóng kết nối. Pool phải hủy context lỗi và không cho mượn lại phiên thiếu TLS hoặc xác thực sai danh tính.

## 10. Chẩn đoán lỗi

| Triệu chứng | Nhóm nguyên nhân thường gặp | Cách kiểm tra đúng |
| --- | --- | --- |
| `PKIX path building failed` | Client không tin certificate chain của server hoặc server thiếu intermediate | Kiểm tra Java truststore, chain server, CA đáng tin |
| Hostname/SAN mismatch | URL client không khớp SAN của server | Kiểm tra tên endpoint; sửa certificate/DNS đúng, không tắt verifier |
| TLS báo thiếu `client certificate` hoặc handshake alert | Server yêu cầu certificate mà client không cung cấp hoặc cung cấp certificate không hợp lệ | Kiểm tra client keystore, alias, key password, CA/EKU được server chấp nhận |
| OpenSSL bắt tay thành công nhưng Spring LDAP thất bại | OpenSSL và JVM dùng cấu hình/CA/key material khác nhau | Kiểm tra `javax.net.ssl.*`, JSSE debug và socket factory thực tế |
| `SASL(-) EXTERNAL` / `authMethodNotSupported` | Server không hỗ trợ EXTERNAL hoặc chính sách xác thực khác | Xem LDAP capabilities, cấu hình SASL và log server |
| EXTERNAL bind thất bại dù TLS thành công | Mapping client identity sang LDAP identity lỗi, không được phép hoặc server không nhận client cert | Phân biệt bằng log TLS, LDAP bind và server mapping |
| EXTERNAL bind thành công nhưng search bị từ chối | Authorization identity không có ACL cần thiết | Kiểm tra danh tính ánh xạ và quyền LDAP cụ thể |
| Hết hạn chứng chỉ client | Certificate client không còn hiệu lực hoặc bị từ chối | Gia hạn qua PKI, cập nhật keystore và kết nối mới |
| Hạ tầng chỉ cho LDAPS, không hỗ trợ StartTLS | Chiến lược cố gửi StartTLS trên endpoint không tương thích | Chọn phương thức và client phù hợp; không xóa xác thực để bỏ qua lỗi |

Phân tích chuỗi nguyên nhân (cause chain) vì Spring LDAP có thể bọc ngoại lệ JNDI/TLS bằng exception của riêng thư viện. Không kết luận lỗi nào cũng là “sai mật khẩu LDAP”: **EXTERNAL không dùng mật khẩu simple bind làm định danh chính**.

### Ba trường hợp cần xử lý dứt điểm

**Trường hợp A — server không yêu cầu chứng chỉ client.** TLS có thể thành công ở chế độ xác thực máy chủ một chiều. Sang bước EXTERNAL, server không có danh tính TLS client để ánh xạ và có thể từ chối bind. Sửa cấu hình mTLS phía server/client; không biến ví dụ sang SIMPLE bind trên kết nối rõ.

**Trường hợp B — client certificate hợp lệ nhưng quyền sai.** SASL EXTERNAL thành công, nhưng ACL chỉ cho phép đọc một nhánh thư mục khác. Cần sửa mapping/ACL theo quy trình và quyền tối thiểu, không cấp quyền quản trị chung để “thử cho nhanh”.

**Trường hợp C — certificate được gia hạn nhưng pool dùng phiên cũ.** Một số context tồn tại từ trước khi thay key material và vẫn phản ánh kết nối/danh tính cũ. Cần quản lý khởi tạo lại SSLContext/pool/kết nối theo kiến trúc và xác minh server nhận chứng chỉ mới.

## 11. Bài thực hành: dịch vụ đọc nhóm bằng client certificate

**Bối cảnh:** Một ứng dụng quản lý truy cập nội bộ dùng Spring LDAP để đọc `mail` và `memberOf` từ `ou=people,dc=example,dc=org`. Nhóm vận hành không muốn quản lý mật khẩu bind chung. Tổ chức đã cấp `ldap-client.p12` cho dịch vụ cùng `ldap-trust.p12` chứa CA tin cậy của server. LDAP server hỗ trợ StartTLS, TLS client certificate và SASL EXTERNAL, đồng thời có mapping tới tài khoản dịch vụ chỉ đọc.

Hãy trả lời:

1. Phải dùng chiến lược Spring LDAP nào? Vì sao `DefaultTlsDirContextAuthenticationStrategy` không thể thay thế trực tiếp?
2. Vì sao ứng dụng cần cả keystore và truststore?
3. Trình tự bắt buộc trước khi `LdapTemplate` được phép tìm kiếm là gì?
4. Nếu TLS handshake thành công nhưng `ldapwhoami -ZZ -Y EXTERNAL` thất bại, cần kiểm tra lớp nào?
5. Nếu kết nối thành công mà `modify` entry bị từ chối, đó có chắc chắn là lỗi TLS không?
6. Thiết kế ít nhất ba kiểm thử âm tính nhằm chứng minh ứng dụng từ chối kết nối/xác thực sai.

**Gợi ý lời giải:**

1. Dùng `ExternalTlsDirContextAuthenticationStrategy` qua `LdapContextSource` dùng `ldap://`, vì đây là chiến lược thực hiện StartTLS rồi LDAP SASL EXTERNAL. `DefaultTlsDirContextAuthenticationStrategy` dùng simple bind theo DN/mật khẩu.
2. Keystore cung cấp chứng chỉ client và private key cho mTLS; truststore chứa CA để client xác minh server. Hai phía cần kiểm tra danh tính đối tác riêng.
3. Mở LDAP, StartTLS thành công, bắt tay TLS và xác minh server, server chấp nhận chứng chỉ client, SASL EXTERNAL bind thành công, sau đó mới gửi search.
4. Kiểm tra server có thực sự yêu cầu/nhận client certificate không, SASL EXTERNAL có được bật và mapping authorization identity có hợp lệ không.
5. Không. Nếu bind đã thành công, việc từ chối modify thường liên quan ACL hoặc quyền của danh tính được ánh xạ; cần điều tra quyền riêng.
6. Ví dụ: truststore không tin CA server, server certificate sai hostname, client certificate không được tin/hết hạn, server không hỗ trợ SASL EXTERNAL, mapping không tồn tại, hoặc StartTLS bị từ chối. Kỳ vọng không có fallback sang kết nối rõ.

### Ma trận kiểm thử đề xuất

| Phép thử | Điều phải quan sát |
| --- | --- |
| Server certificate hợp lệ; client cert được phép; mapping đúng | SASL EXTERNAL bind và read theo ACL thành công |
| Server certificate có SAN sai | Client từ chối TLS trước LDAP bind |
| Server không hỗ trợ StartTLS | Không chuyển sang simple bind trên kết nối rõ |
| Client cert bị từ chối hoặc thiếu private key | mTLS/EXTERNAL không được coi là thành công |
| Mapping SASL EXTERNAL không tồn tại | Xác thực LDAP bị từ chối, không tự dùng quyền khác |
| Mapping chỉ có quyền đọc | Search hợp lệ; Modify bị từ chối theo ACL |
| Node dự phòng thiếu cấu hình mTLS/SASL | Không tự hạ cấp phương thức xác thực |
| Keystore được thay mới | Kết nối mới dùng đúng certificate và quyền dự kiến |

## 12. Ghi nhớ và nguồn tra cứu

- `ExternalTlsDirContextAuthenticationStrategy` là chiến lược **StartTLS + SASL EXTERNAL** của Spring LDAP; nó khác với cơ chế **StartTLS + SIMPLE bind** trong `DefaultTlsDirContextAuthenticationStrategy`.
- **TLS mã hóa**, **mTLS nhận diện client ở tầng TLS**, còn **SASL EXTERNAL gắn danh tính ngoài vào xác thực LDAP**. Cả ba cần hoạt động đúng khi dùng mô hình này.
- Chứng chỉ client và private key được quản lý trong **keystore**; CA tin cậy để xác minh LDAP server nằm trong **truststore**. Luôn kiểm tra chain, SAN/hostname và chính sách TLS.
- Không mặc định mọi LDAP server đều hỗ trợ SASL EXTERNAL hoặc có mapping chứng chỉ. **Bind thành công không đồng nghĩa có mọi quyền LDAP**.
- Tắt native JNDI pooling với StartTLS, kiểm thử vòng đời TLS, pool riêng, nhiều context source, referral và certificate rotation.
- Khi TLS hay EXTERNAL thất bại, **dừng kết nối và báo lỗi**, không fallback sang bind không mã hóa hoặc bỏ kiểm tra danh tính.

**Tài liệu tham khảo chính thức:**

- [Spring LDAP — Configuration, mục TLS và các authentication strategy](https://docs.spring.io/spring-ldap/reference/configuration.html)
- [Javadoc — ExternalTlsDirContextAuthenticationStrategy](https://docs.spring.io/spring-ldap/docs/3.3.x/api/org/springframework/ldap/core/support/ExternalTlsDirContextAuthenticationStrategy.html)
- [Javadoc — AbstractTlsDirContextAuthenticationStrategy](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/AbstractTlsDirContextAuthenticationStrategy.html)
