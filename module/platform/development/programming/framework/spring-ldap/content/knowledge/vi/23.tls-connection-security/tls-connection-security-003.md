# Truststore, certificate chain và hostname verification

## 1. Mục tiêu và bối cảnh

Trong **Spring LDAP**, ứng dụng Java thường dùng `LdapTemplate`, `LdapClient` hoặc Object-Directory Mapping (ODM) để tìm kiếm, xác thực và cập nhật entry. Các API này truy cập máy chủ thư mục thông qua một `ContextSource`, chẳng hạn `LdapContextSource`. Khi sử dụng **LDAPS** hoặc **StartTLS**, dữ liệu LDAP có thể được bảo vệ bằng TLS; tuy nhiên, một kết nối được mã hóa chỉ đáng tin khi ứng dụng cũng xác minh được **máy chủ ở đầu bên kia là máy chủ dự định kết nối**.

Ba thành phần quyết định điều đó là:

1. **Certificate chain (chuỗi chứng chỉ):** liên kết chứng chỉ của máy chủ với một tổ chức phát hành chứng chỉ (CA) đáng tin, kèm các điều kiện hiệu lực và mục đích sử dụng.
2. **Truststore:** kho chứng chỉ hoặc trust anchor mà ứng dụng Java dùng để xác định CA nào được tin cậy.
3. **Hostname verification:** đối chiếu tên máy chủ mà ứng dụng muốn kết nối với danh tính được khai báo trong chứng chỉ của máy chủ.

Bài học thuộc chương **TLS và bảo mật kết nối** này giải thích cả ba khái niệm, cách chúng phối hợp trong LDAP, cách cấu hình JVM và Spring LDAP, cách kiểm tra thực tế và xử lý các lỗi TLS thường gặp. Mọi tên miền, DN và đường dẫn trong ví dụ đều là dữ liệu minh họa.

## 2. Truststore là gì, và khác keystore ra sao?

Trong Java, **truststore** là kho chứa thông tin tin cậy được dùng khi xác minh chứng chỉ của đối tác TLS. Truststore thường chứa chứng chỉ **CA gốc (root CA)** hoặc CA được tổ chức phê duyệt. Các chứng chỉ đó đóng vai trò **trust anchor** để xây dựng và xác minh một chuỗi chứng chỉ.

**Keystore** là khái niệm kho khóa rộng hơn; trong thực tế TLS, keystore thường được dùng để lưu **khóa riêng và chuỗi chứng chỉ của chính ứng dụng**, ví dụ khi máy chủ LDAP yêu cầu xác thực bằng chứng chỉ client (mutual TLS). Cùng một định dạng tệp có thể chứa nhiều loại entry, nên sự khác biệt chủ yếu nằm ở **mục đích sử dụng**, không chỉ ở đuôi tệp.

| Thành phần | Thông thường chứa | Dùng để làm gì trong kết nối LDAP |
| --- | --- | --- |
| Truststore phía ứng dụng | Chứng chỉ CA/trust anchor đáng tin | Kiểm tra chứng chỉ máy chủ LDAPS/StartTLS |
| Keystore phía ứng dụng (khi cần mTLS) | Khóa riêng của client và chuỗi chứng chỉ client | Chứng minh danh tính client trong bắt tay TLS hai chiều |
| Keystore/cấu hình chứng chỉ phía máy chủ LDAP | Khóa riêng của máy chủ và chứng chỉ máy chủ cùng các chứng chỉ trung gian cần thiết | Máy chủ trình bày danh tính với client |
| Java `cacerts` mặc định | Tập CA tin cậy đi kèm bản phân phối JDK | Có thể được JSSE dùng khi không chỉ định kho tin cậy riêng |

**Không cần chép khóa riêng của LDAP server vào truststore phía client.** Client chỉ cần trust anchor thích hợp để kiểm tra danh tính server. Nhập một chứng chỉ chưa xác minh chỉ để “hết lỗi” có thể biến một đối tượng không đáng tin thành đáng tin đối với ứng dụng.

### 2.1. Định dạng truststore và phạm vi áp dụng

- **PKCS#12 (`.p12`/`.pfx`):** định dạng lưu trữ có thể chứa chứng chỉ và khóa, được hỗ trợ rộng rãi trên các JDK hiện đại; là lựa chọn phù hợp cho ví dụ mới.
- **JKS (`.jks`):** định dạng kho khóa của Java, vẫn xuất hiện nhiều trong hệ thống cũ.
- **`cacerts` của JDK:** kho CA mặc định có thể thay đổi giữa các bản phân phối hoặc lần cập nhật JDK.

Java Secure Socket Extension (JSSE) có thể lấy truststore theo cấu hình hệ thống, ví dụ `javax.net.ssl.trustStore` và `javax.net.ssl.trustStoreType`. Các tham số `-D...` ở mức JVM ảnh hưởng đến **những thành phần sử dụng cấu hình TLS mặc định của JVM**; nếu chương trình đã xây dựng `SSLContext`/`SSLSocketFactory` riêng, cần xác minh nguồn trust riêng đó.

Trong môi trường nhiều tích hợp, việc thay thế truststore toàn JVM bằng một kho chỉ chứa CA LDAP có thể vô tình làm mất các CA cần thiết cho HTTPS hoặc kết nối TLS khác. Hãy quyết định rõ phạm vi tin cậy dự định và thử nghiệm tất cả tích hợp chịu tác động.

## 3. Certificate chain hoạt động như thế nào?

Chứng chỉ TLS thường theo chuẩn **X.509**. Một chuỗi minh họa:

~~~text
Root CA (trust anchor do client chủ động tin cậy)
    |
    +-- Intermediate CA (CA trung gian)
            |
            +-- Leaf/server certificate
                Subject/SAN: directory.example.org
                Public key: khóa công khai của máy chủ
~~~

Khi ứng dụng kết nối `ldaps://directory.example.org:636`, máy chủ thường gửi chứng chỉ **leaf** và các chứng chỉ **intermediate** cần thiết. Root CA thường **không nhất thiết được máy chủ gửi**; client đã phải biết và tin cậy root CA hoặc một trust anchor phù hợp từ trước.

Quy trình xác minh cơ bản gồm:

1. Đọc chứng chỉ server và chuỗi mà máy chủ cung cấp.
2. Xây dựng một đường dẫn chứng chỉ hợp lệ từ chứng chỉ server qua các CA trung gian đến trust anchor được client tin cậy.
3. Kiểm tra chữ ký số, thời hạn hiệu lực, ràng buộc CA (chẳng hạn `BasicConstraints`), mục đích/khả năng sử dụng khóa và các điều kiện đường dẫn áp dụng.
4. Theo chính sách triển khai, kiểm tra thêm trạng thái thu hồi chứng chỉ (CRL/OCSP) và các ràng buộc PKI khác; **không mặc định** mọi JDK đều bật kiểm tra thu hồi cho mọi kết nối.
5. Kiểm tra **hostname** của endpoint ứng dụng yêu cầu kết nối khớp với danh tính trong chứng chỉ server.
6. Chỉ chấp nhận phiên TLS sau khi toàn bộ kiểm tra bắt buộc thành công.

~~~mermaid
flowchart TD
    A["Nhận chứng chỉ máy chủ"] --> B{"Xây được chain tới trust anchor tin cậy?"}
    B -- Không --> X["Từ chối TLS"]
    B -- Có --> C{"Chữ ký, thời hạn và điều kiện PKI hợp lệ?"}
    C -- Không --> X
    C -- Có --> D{"Hostname khớp danh tính chứng chỉ?"}
    D -- Không --> X
    D -- Có --> E["Chấp nhận TLS theo chính sách"]
    E --> F["Mới gửi LDAP bind/search"]
~~~

Sơ đồ mô tả các **điều kiện chấp nhận chính**; thực tế JVM còn kiểm tra thuật toán, cấu hình TLS và các ràng buộc chứng chỉ khác. Nếu bất kỳ điều kiện bắt buộc nào thất bại, một ứng dụng yêu cầu bảo mật phải **dừng**; không thử gửi simple bind qua LDAP không mã hóa.

### 3.1. Vì sao chỉ có root CA vẫn có thể lỗi?

Giả sử truststore chứa `Example Internal Root CA`, nhưng máy chủ chỉ gửi chứng chỉ leaf do `Example Issuing CA` cấp mà không gửi chứng chỉ intermediate. Client có thể không dựng được đường dẫn tới root vì thiếu mắt xích. Việc sửa phù hợp thường là **cấu hình LDAP server trình bày đầy đủ chứng chỉ trung gian cần thiết**, rồi kiểm thử lại từ JVM thực tế.

Không nên xem việc tải bừa một file chứng chỉ từ kết nối đang bị nghi ngờ rồi nhập vào truststore là bước xử lý an toàn. Phải xác minh nguồn chứng chỉ/CA qua kênh tin cậy và đối chiếu dấu vân tay khi quy trình tổ chức yêu cầu.

### 3.2. Một CA được tin cậy không có nghĩa mọi hostname đều hợp lệ

Truststore trả lời: **“Có thể xác minh chứng chỉ này tới một trust anchor được phép không?”**. Nó không tự trả lời: **“Chứng chỉ này thuộc về đúng endpoint LDAP tôi muốn truy cập không?”**.

Ví dụ, client tin CA nội bộ cấp chứng chỉ cho cả `directory.example.org` và `other.example.org`. Một chứng chỉ hợp lệ cho `other.example.org` vẫn **không được** chấp nhận khi ứng dụng đang kết nối `directory.example.org`. Đây là lý do hostname verification phải hoạt động cùng quá trình xác minh chuỗi.

## 4. Hostname verification: xác minh đúng máy chủ

**Hostname verification** đối chiếu tên đích mà client dùng với danh tính trong chứng chỉ máy chủ. Chứng chỉ hiện đại khai báo tên trong phần mở rộng **Subject Alternative Name (SAN)**.

| URI hoặc đích client sử dụng | SAN của chứng chỉ máy chủ | Kết quả kỳ vọng |
| --- | --- | --- |
| `ldaps://directory.example.org:636` | `DNS:directory.example.org` | Khớp |
| `ldaps://directory.example.org:636` | `DNS:other.example.org` | Không khớp |
| `ldaps://10.20.30.40:636` | `IP Address:10.20.30.40` | Khớp nếu chính sách cho phép đích IP và chuỗi hợp lệ |
| `ldaps://10.20.30.40:636` | `DNS:directory.example.org` | Không đủ để xác minh địa chỉ IP |
| `ldaps://ldap.internal.example.org:636` | `DNS:directory.example.org` | Không khớp, dù hai tên trỏ cùng máy chủ |

Một số điểm cần nhớ:

- **SAN là nơi khai báo danh tính dự kiến.** Không dựa vào trường Common Name (CN) như cách thay thế mặc định cho SAN trong thiết kế mới.
- Nếu URL sử dụng địa chỉ IP, chứng chỉ cần có SAN loại **iPAddress** phù hợp; một SAN dạng DNS chứa chuỗi số không thay thế việc so khớp IP.
- Wildcard DNS (ví dụ `*.example.org`) có quy tắc so khớp giới hạn; không mặc định nó hợp lệ cho mọi cấp tên miền hoặc mọi ứng dụng.
- Cổng không tham gia so khớp hostname. Điều cần khớp là danh tính đích và chứng chỉ, sau khi đã kiểm tra chuỗi.
- Load balancer, alias DNS, CNAME hoặc Kubernetes service name có thể thay đổi **tên mà ứng dụng thực sự kết nối**. SAN phải phù hợp tên đích đó, hoặc kiến trúc cần được điều chỉnh đúng.

### 4.1. Hostname verification ở Java/JNDI và Spring LDAP

Spring LDAP dựa trên Java/JNDI khi tạo kết nối LDAP. Với các JDK hiện đại, kết nối LDAPS qua JNDI có cơ chế nhận diện endpoint theo chính sách của runtime; tuy nhiên, hành vi còn phụ thuộc **phiên bản JDK, cách thiết lập TLS, các tùy chọn hệ thống và socket factory tùy biến**. Luồng StartTLS cũng cần được kiểm tra riêng.

Vì vậy, khi đánh giá bảo mật, **không chỉ kiểm tra truststore hay nhìn URL `ldaps://`**. Hãy chủ động thử một máy chủ có chuỗi CA hợp lệ nhưng SAN **không khớp hostname**, và xác nhận ứng dụng từ chối kết nối. Kiểm thử tương tự cho đường đi StartTLS nếu ứng dụng sử dụng StartTLS.

Không bật các tùy chọn vô hiệu hóa endpoint identification, không cấu hình `HostnameVerifier` luôn trả về `true` và không sử dụng trust manager chấp nhận mọi chứng chỉ. Những cách này làm mất ý nghĩa xác thực máy chủ, dù bản thân kênh TLS vẫn có mã hóa.

## 5. Cấu hình truststore cho Spring LDAP

### 5.1. Ví dụ cấu hình ứng dụng dùng LDAPS

Giả sử dịch vụ thư mục có hostname `directory.example.org`, chứng chỉ server hợp lệ với SAN `DNS:directory.example.org` và được ký bởi CA nội bộ mà ứng dụng đã xác minh qua kênh tin cậy.

Một cấu hình Spring Boot có thể là:

~~~yaml
# application.yml
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Ở đây `spring.ldap.urls` yêu cầu TLS ngay từ đầu kết nối. `spring.ldap.username` và `spring.ldap.password` dùng cho **LDAP bind sau khi TLS**; không thể dùng thông tin bind để “sửa” lỗi chứng chỉ TLS xảy ra trước bind.

Trong một chương trình dùng Spring LDAP thuần, cấu hình `LdapContextSource` tương đương:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
class DirectoryConfig {
    @Bean
    LdapContextSource ldapContextSource() {
        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://directory.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn("cn=app-reader,ou=services,dc=example,dc=org");
        source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
        return source;
    }

    @Bean
    LdapTemplate ldapTemplate(LdapContextSource source) {
        return new LdapTemplate(source);
    }
}
~~~

Ví dụ là cấu hình tối thiểu để minh họa mối liên hệ giữa `LdapContextSource` và TLS. Trong ứng dụng thật, hãy quản lý thông tin xác thực bằng hệ thống cấu hình/secret thích hợp, không ghi log secret và bổ sung chính sách kết nối, timeout, quyền tài khoản bind.

### 5.2. Tạo truststore từ CA đáng tin

Giả sử quản trị PKI cung cấp `org-directory-root-ca.pem` theo một kênh đã xác minh. Tạo truststore riêng cho môi trường bằng `keytool`:

~~~bash
# Nhập CA đáng tin vào truststore PKCS#12; keytool sẽ hỏi mật khẩu.
keytool -importcert \
  -alias org-directory-root \
  -file org-directory-root-ca.pem \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12

# Kiểm tra alias và thông tin chứng chỉ vừa nhập.
keytool -list -v \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12 \
  -alias org-directory-root
~~~

Trước khi xác nhận import, kiểm tra subject, issuer, hạn dùng và **fingerprint** với thông tin đã được tổ chức xác thực ngoài băng. Nếu máy chủ dùng chuỗi có intermediate CA, server cần trình bày đủ các intermediate cần thiết; client phải xây dựng được chuỗi tới trust anchor đã được phê duyệt.

Chứng chỉ trong truststore được dùng làm cơ sở xác minh **đối tác**. Không nhầm với khóa riêng của client. Không lưu certificate/key của ứng dụng trong repository hoặc tài liệu công khai.

### 5.3. Khởi chạy JVM với truststore

Truyền các thuộc tính JVM khi khởi chạy ứng dụng:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/etc/app/security/ldap-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar directory-service.jar
~~~

Đường dẫn và tên jar là minh họa. Có thể cần cấu hình mật khẩu truststore bằng cơ chế secret phù hợp với hệ thống, không đưa giá trị bí mật vào log, câu lệnh được ghi lịch sử hoặc tài liệu. Nếu JVM sử dụng một `SSLContext` tùy biến, cần xác nhận nguồn truststore thực tế thay vì cho rằng thuộc tính hệ thống luôn được áp dụng.

**Chú ý phạm vi cấu hình:** Các thuộc tính `javax.net.ssl.*` đặt ở mức JVM có thể tác động tới nhiều kết nối TLS khác trong cùng tiến trình. Việc dùng một truststore chứa duy nhất CA nội bộ có thể khiến HTTPS hay tích hợp khác vốn dựa trên `cacerts` bị lỗi. Hãy chọn kho CA theo nhu cầu thực tế và kiểm thử toàn bộ các luồng TLS liên quan.

### 5.4. Nếu ứng dụng dùng StartTLS

Với StartTLS, URL thường là `ldap://directory.example.org:389`. Trong Spring LDAP, một cách triển khai simple bind sau StartTLS là cấu hình `DefaultTlsDirContextAuthenticationStrategy` trên `LdapContextSource`:

~~~java
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldap://directory.example.org:389");
source.setBase("dc=example,dc=org");
source.setUserDn("cn=app-reader,ou=services,dc=example,dc=org");
source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
source.setAuthenticationStrategy(
    new DefaultTlsDirContextAuthenticationStrategy()
);
// Khi quản lý bằng Spring bean, lifecycle khởi tạo do Spring thực hiện.
~~~

Trình tự đúng là: yêu cầu StartTLS → bắt tay và xác minh server certificate/hostname → simple bind → thao tác LDAP. Truststore Java vẫn có vai trò trong việc xác minh chuỗi server. Vì StartTLS có thêm bước nâng cấp, hãy kiểm thử cả **lỗi nâng cấp**, **lỗi xác minh chứng chỉ** và **vòng đời kết nối/pooling**; không mặc định chỉ đặt `ldap://` là được mã hóa.

## 6. Kiểm tra certificate chain và hostname trong thực tế

Các công cụ sau thích hợp để chẩn đoán **endpoint thử nghiệm được phép**. Chúng không thay thế thử nghiệm cuối cùng trong JVM và `LdapContextSource` của ứng dụng.

### 6.1. Kiểm tra chứng chỉ trong tệp

~~~bash
# Hiển thị subject, issuer, hạn dùng, SAN và các extension liên quan.
keytool -printcert -v -file org-directory-root-ca.pem

# Xem chứng chỉ server PEM trong môi trường kiểm thử.
openssl x509 -in directory-server.pem -noout -text
~~~

Trong kết quả, hãy tìm các trường:

| Trường | Ý nghĩa cần kiểm tra |
| --- | --- |
| `Subject` / `Issuer` | Chủ thể và CA phát hành; tham khảo cấu trúc chuỗi |
| `Not Before` / `Not After` | Thời hạn hiệu lực của từng chứng chỉ |
| `Subject Alternative Name` | DNS hoặc địa chỉ IP mà server certificate được phép đại diện |
| `Basic Constraints` | Chứng chỉ trung gian/gốc có được đánh dấu là CA khi cần không |
| `Key Usage` và `Extended Key Usage` | Khả năng và mục đích sử dụng phù hợp cho chứng chỉ TLS |
| Fingerprint (SHA-256) | Đối chiếu chứng chỉ hoặc CA với dữ liệu đã xác minh ngoài băng |

Lệnh hiển thị chứng chỉ **không tự chứng minh toàn bộ path validation đạt yêu cầu**. Cần kiểm tra tương quan chuỗi thực tế, trust anchor và hostname của endpoint.

### 6.2. Xem chuỗi mà máy chủ thực sự trình bày

~~~bash
# LDAPS: bắt tay TLS ngay trên kết nối.
openssl s_client \
  -connect directory.example.org:636 \
  -servername directory.example.org \
  -showcerts \
  -CAfile org-directory-root-ca.pem \
  -verify_hostname directory.example.org \
  -verify_return_error

# StartTLS: gửi yêu cầu nâng cấp LDAP trước khi bắt tay.
openssl s_client \
  -starttls ldap \
  -connect directory.example.org:389 \
  -showcerts \
  -CAfile org-directory-root-ca.pem \
  -verify_hostname directory.example.org \
  -verify_return_error
~~~

- `-showcerts` hiển thị những chứng chỉ được máy chủ gửi, giúp nhận biết intermediate bị thiếu.
- `-CAfile` chỉ rõ nguồn CA tin cậy cho phép thử bằng OpenSSL; tệp CA phải được xác minh trước.
- `-verify_hostname` kiểm tra tên đích chỉ định; `-verify_return_error` giúp phép thử dừng khi xác minh lỗi.
- `-starttls ldap` kích hoạt yêu cầu StartTLS phù hợp với LDAP, **khác** với một kết nối TLS trực tiếp tới cổng 389.

OpenSSL và Java có thể sử dụng kho CA, quy tắc xác minh hoặc chính sách thuật toán khác nhau. **Phải thử từ chính ứng dụng Java**, đặc biệt khi dùng custom truststore, custom socket factory, JNDI StartTLS hoặc một phiên bản JDK khác môi trường phát triển.

### 6.3. Kiểm chứng từ chương trình Spring LDAP

Một thử nghiệm tích hợp đơn giản có thể yêu cầu đọc một entry thử nghiệm bằng `LdapTemplate`:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class TlsConnectionProbe {
    private final LdapTemplate template;

    public TlsConnectionProbe(LdapTemplate template) {
        this.template = template;
    }

    public List<String> findCnByUid(String uid) {
        return template.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("cn").get()
        );
    }
}
~~~

Kết nối và truy vấn thành công là tín hiệu chức năng, **chưa đủ để chứng minh hostname verification hoạt động**. Trong lab, hãy lần lượt thay server certificate bằng chứng chỉ có SAN không khớp, dùng CA không đáng tin, hoặc mô phỏng certificate hết hạn; kỳ vọng ứng dụng từ chối mà không gửi simple bind. Để kiểm chứng sâu, có thể bật log chẩn đoán TLS của JSSE ở môi trường thử nghiệm theo chính sách bảo mật log của tổ chức.

## 7. Nhận diện và xử lý lỗi thường gặp

| Triệu chứng / thông báo thường thấy | Nguyên nhân có thể | Hướng kiểm tra và khắc phục |
| --- | --- | --- |
| `SSLHandshakeException` kèm `PKIX path building failed` | Không xây được đường chứng chỉ đến trust anchor; CA không được tin hoặc thiếu intermediate | Xác minh CA/chuỗi server, truststore JVM và các intermediate server cung cấp |
| `No subject alternative DNS name matching ...` hoặc lỗi hostname tương đương | SAN không khớp hostname URL | Dùng hostname đúng hoặc cấp lại chứng chỉ có SAN phù hợp |
| Certificate expired / not yet valid | Chứng chỉ hết hạn, chưa có hiệu lực hoặc đồng hồ hệ thống sai | Kiểm tra thời gian và gia hạn/cấp lại chứng chỉ |
| `unable to find valid certification path` dù đã import CA | Import nhầm truststore, chạy JVM khác, CA sai hoặc server thiếu intermediate | Xác nhận JVM/container thực tế, đường truststore và chuỗi đang được gửi |
| LDAPS bắt tay được nhưng bind thất bại | Có thể sai DN/mật khẩu hoặc quyền tài khoản sau khi TLS đã thành công | Phân biệt lỗi xác thực LDAP với lỗi TLS; không sửa truststore chỉ dựa vào lỗi bind |
| OpenSSL thành công, Java vẫn thất bại | Hai công cụ dùng CA/chính sách/hostname validation khác nhau | Kiểm tra JSSE, `javax.net.ssl.trustStore`, phiên bản JDK và socket factory |
| StartTLS không được hỗ trợ hoặc handshake fail | Server hoặc mạng không hỗ trợ thao tác nâng cấp; chứng chỉ/policy không hợp lệ | Kiểm tra phản hồi StartTLS và TLS; dừng trước bind, không fallback |

Những thông báo trên chỉ là **gợi ý chẩn đoán**; chuỗi lỗi cụ thể tùy JDK, nhà cung cấp LDAP và tầng thư viện. Cần điều tra nguyên nhân bằng chứng cứ từ endpoint, truststore và phiên Java thật.

### Hai cách “sửa nhanh” cần tránh

**(1) Tắt xác minh chứng chỉ hoặc hostname:** ví dụ thay trust manager bằng kiểu chấp nhận mọi chứng chỉ, tạo hostname verifier luôn trả về `true`, hoặc dùng tùy chọn vô hiệu hóa endpoint identification. Điều này làm client không còn xác thực đúng máy chủ và có thể mở đường cho tấn công xen giữa.

**(2) Thấy lỗi TLS thì chuyển sang LDAP không mã hóa:** nếu thực hiện simple bind trên kênh đó, mật khẩu có thể lộ. Chính sách đúng là **fail closed**, sửa chứng chỉ/cấu hình hoặc kết nối tới endpoint TLS hợp lệ.

## 8. Vận hành certificate chain và truststore an toàn

Một quy trình vận hành bền vững cần trả lời được các câu hỏi:

1. **CA nào được tin?** Lưu danh mục CA được tổ chức phê duyệt, nơi lấy chứng chỉ và cách xác minh fingerprint.
2. **Ai sở hữu vòng đời chứng chỉ?** Có lịch theo dõi ngày hết hạn server certificate/intermediate/root CA, cùng cách gia hạn và cập nhật truststore.
3. **Đổi CA sẽ diễn ra thế nào?** Thử giai đoạn truststore chứa cả CA cũ và mới khi cần chuyển tiếp, triển khai có kiểm soát rồi thu hồi CA cũ theo chính sách.
4. **Tên endpoint có ổn định không?** Chứng chỉ phải bao phủ hostname thực tế của mỗi endpoint, gồm máy chủ dự phòng, proxy và tên được ứng dụng sử dụng.
5. **Kết nối phụ được bảo vệ chưa?** Rà soát mọi `ContextSource`, referral, kết nối dự phòng, luồng authentication theo người dùng và pooling.
6. **Chính sách thu hồi đã rõ chưa?** Nếu tổ chức cần CRL/OCSP, phải cấu hình và kiểm thử đúng; không coi việc có truststore là mặc nhiên kiểm tra revocation.
7. **Ứng dụng xử lý lỗi ra sao?** Ghi log đủ để điều tra nhưng không lộ mật khẩu bind, khóa riêng hoặc dữ liệu LDAP nhạy cảm; cảnh báo lỗi cert để khắc phục kịp thời.

### Minh họa sự cố đổi CA

Một hệ thống nhân sự truy cập `ldaps://directory.example.org:636` đang tin `Root-Old` trong truststore. Nhóm PKI cấp lại chứng chỉ server qua `Root-New` nhưng chưa cập nhật truststore của ứng dụng Java. Kết nối bắt đầu thất bại với lỗi xây dựng đường dẫn chứng chỉ, dù hostname vẫn chính xác.

Cách xử lý đúng là kiểm tra chuỗi server mới, xác minh `Root-New` qua nguồn PKI được phép, cập nhật truststore theo quy trình và chạy kiểm thử LDAPS từ JVM của ứng dụng. Chỉ sau khi TLS và hostname verification thành công mới cho phép LDAP bind. Không tắt kiểm tra chứng chỉ hoặc tự đổi sang `ldap://`.

## 9. Bài tập áp dụng

**Tình huống:** Ứng dụng Spring LDAP sử dụng:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.hr.example.org:636
    base: dc=hr,dc=example,dc=org
    username: cn=read-only,ou=services,dc=hr,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Máy chủ trình bày:

~~~text
Leaf certificate:
  SAN: DNS:directory.hr.example.org
  Issuer: HR Issuing CA
Intermediate:
  Subject: HR Issuing CA
  Issuer: HR Root CA
Truststore của JVM:
  HR Root CA
~~~

**Câu hỏi:**

1. Truststore có đủ để ứng dụng chấp nhận certificate chain theo mô hình trên không? Những điều kiện khác còn phải kiểm tra?
2. Giả sử chain hợp lệ và root CA được tin, tại sao hostname verification vẫn phải từ chối kết nối?
3. Nêu hai hướng sửa đúng mà không bỏ qua xác minh máy chủ.
4. Nếu thay LDAPS bằng StartTLS, truststore và hostname verification có còn cần không?
5. Vì sao không nên khắc phục bằng cách nhập chứng chỉ leaf tùy ý rồi tắt kiểm tra hostname?

**Gợi ý lời giải:**

1. Root CA trong truststore cho phép **thử xây chain** qua intermediate. Vẫn phải kiểm tra chữ ký, thời hạn, ràng buộc CA, mục đích sử dụng, chính sách thuật toán và mọi điều kiện PKI áp dụng.
2. URI kết nối dùng `ldap.hr.example.org` nhưng SAN chỉ chứa `directory.hr.example.org`. Hai tên không khớp dù cùng tổ chức hoặc trỏ cùng IP.
3. Đổi URI sang hostname thực sự có trong SAN **nếu đó là đúng endpoint cần kết nối**, hoặc cấp lại server certificate có SAN `DNS:ldap.hr.example.org` sau khi xác thực quyền sở hữu/định danh.
4. Có. StartTLS chỉ thay đổi thời điểm nâng cấp kênh, không bỏ yêu cầu xác minh danh tính máy chủ.
5. Cách đó không chứng minh được đối tác là endpoint dự kiến, dễ tạo niềm tin sai và làm suy yếu mục tiêu chống MITM. Cần xác minh đúng CA và hostname.

## 10. Ghi nhớ

- **Truststore** xác định trust anchor của client; **certificate chain** cho phép kiểm tra con đường tin cậy từ chứng chỉ server tới anchor đó; **hostname verification** bảo đảm chứng chỉ thuộc đúng endpoint được yêu cầu.
- Một certificate chain hợp lệ **chưa đủ** nếu SAN không khớp hostname. Ngược lại, SAN khớp cũng không đủ nếu CA không được tin hoặc chứng chỉ không hợp lệ.
- Spring LDAP dựa vào `ContextSource` và tầng Java/JNDI để thiết lập LDAPS/StartTLS. Kiểm tra nguồn truststore và hành vi xác minh hostname của **JDK cùng đường kết nối thực tế**.
- Sửa certificate chain thiếu intermediate từ phía máy chủ, cập nhật CA đúng quy trình, kiểm tra SAN/DNS và kiểm thử từ Java; không vô hiệu hóa certificate validation để vượt lỗi.
- Khi TLS lỗi, dừng trước LDAP bind. Quản lý việc gia hạn chứng chỉ, chuyển CA, endpoint dự phòng, proxy, referral và pool để duy trì bảo mật lâu dài.
