# Cấu hình TLS trong ContextSource

## 1. Vì sao phải cấu hình TLS ở ContextSource?

Ứng dụng Java dùng **Spring LDAP** thường không tự mở từng socket LDAP. Thay vào đó, các thành phần như `LdapTemplate`, `LdapClient` hoặc Object-Directory Mapping (ODM) dựa vào một `ContextSource` để lấy context kết nối đến dịch vụ thư mục. `LdapContextSource` là cách triển khai phổ biến dựa trên Java Naming and Directory Interface (JNDI).

Những thao tác LDAP có thể truyền dữ liệu nhạy cảm:

- **Bind** bằng DN và mật khẩu, đặc biệt là simple bind.
- **Search** với base DN, filter, danh sách thuộc tính và kết quả như `mail`, `memberOf`.
- **Add/Modify/Delete** với dữ liệu entry và thuộc tính người dùng hoặc nhóm.
- **Xác thực người dùng** qua bind hoặc những thao tác truy xuất sau đăng nhập.

Nếu nguồn kết nối dùng `ldap://` mà chưa nâng cấp StartTLS, dữ liệu LDAP có thể bị đọc hoặc can thiệp trên đường truyền. Do đó, trong chương **TLS và bảo mật kết nối**, mục tiêu cấu hình là **bảo đảm mọi context được sử dụng cho dữ liệu nhạy cảm đều có kênh TLS hợp lệ trước khi gửi LDAP bind và truy vấn**.

Sau bài học, người học có thể thiết lập `LdapContextSource` theo LDAPS hoặc StartTLS, quản lý truststore, kiểm tra hostname, hiểu tác động của pooling và triển khai kiểm thử khi TLS thất bại.

## 2. ContextSource nằm ở đâu trong luồng Spring LDAP?

`ContextSource` là điểm nối giữa mã nghiệp vụ và cơ chế tạo context LDAP. Nó nhận cấu hình endpoint, base DN, thông tin xác thực và những tùy chọn kết nối, rồi cung cấp context cho các thành phần gọi LDAP.

~~~mermaid
flowchart TD
    App["Mã nghiệp vụ Java"] --> API["LdapTemplate / LdapClient / ODM"]
    API --> CS["LdapContextSource"]
    CS --> JNDI["Java JNDI / TLS (JSSE)"]
    JNDI --> Server["Máy chủ LDAP"]
    Config["URL, base DN, bind DN, credentials"] --> CS
    TLS["LDAPS hoặc chiến lược StartTLS"] --> CS
    Trust["Truststore + xác minh certificate/hostname"] --> JNDI
~~~

`ContextSource` không phải cơ chế mã hóa riêng của Spring LDAP: kết nối TLS thực tế do JNDI/JSSE và máy chủ LDAP thương lượng. Vì thế, **tạo được `LdapTemplate` hoặc truy vấn thành công chưa chứng minh TLS an toàn**. Cần kiểm tra endpoint, cấu hình TLS, chứng chỉ và thứ tự bind.

### Các thiết lập liên quan

| Thiết lập hoặc thành phần | Mục đích | Lưu ý bảo mật |
| --- | --- | --- |
| `LdapContextSource#setUrl` / `setUrls` | Chỉ định máy chủ hoặc danh sách máy chủ LDAP | Đừng trộn endpoint TLS an toàn với endpoint LDAP rõ trong danh sách dự phòng. |
| `setBase` | Base DN dùng cho các thao tác tương đối | Không ảnh hưởng mã hóa; DN vẫn có thể lộ nếu kênh rõ. |
| `setUserDn` / `setPassword` | Cấu hình tài khoản bind cho context | Không lưu mật khẩu trực tiếp trong mã nguồn; chỉ bind sau TLS. |
| `setAuthenticationStrategy` | Chọn chiến lược xác thực, có thể bao gồm StartTLS | Với `ldap://`, cần kích hoạt StartTLS thực sự nếu chính sách yêu cầu TLS. |
| `setPooled` | Điều khiển cơ chế pooling JNDI ở context source | Với StartTLS, tránh pooling JNDI khi chưa kiểm chứng vòng đời TLS. |
| Java truststore / JSSE | Quy định CA tin cậy khi kiểm tra chứng chỉ server | Không vô hiệu hóa kiểm tra chứng chỉ hoặc hostname. |
| `LdapTemplate`, `LdapClient`, ODM | Thực hiện thao tác LDAP qua context | Mức bảo vệ phụ thuộc context source đang được sử dụng. |

## 3. Hai cách thiết lập TLS ở ContextSource

Về mặt kết nối, **LDAPS** và **StartTLS** có điểm bắt đầu khác nhau:

| Cách kết nối | URL điển hình | Bắt tay TLS diễn ra khi nào? | Cấu hình ở Spring LDAP |
| --- | --- | --- | --- |
| LDAPS | `ldaps://directory.example.org:636` | Ngay sau khi mở TCP, trước mọi thông điệp LDAP | URL `ldaps://` cùng truststore và kiểm tra danh tính server |
| StartTLS | `ldap://directory.example.org:389` | Sau yêu cầu nâng cấp StartTLS, trước bind và truy vấn nhạy cảm | URL `ldap://` **và** chiến lược StartTLS, chẳng hạn `DefaultTlsDirContextAuthenticationStrategy` |

Cổng 636 và 389 là quy ước, không phải bằng chứng mã hóa. Máy chủ có thể sử dụng cổng khác. Thực tế phải xác minh bắt tay TLS, chứng chỉ server, hostname và hành vi lỗi.

Nếu hai cơ chế thương lượng cùng chính sách TLS và đều xác minh máy chủ đúng, thông điệp LDAP gửi **bên trong kênh TLS** có thể có mức bảo vệ tương đương. Khác biệt chính là cách tạo phiên và rủi ro cấu hình bỏ qua bước nâng cấp.

## 4. Cấu hình LDAPS với Spring Boot

Đối với ứng dụng Spring Boot dùng tính năng tự cấu hình Spring LDAP, cách triển khai ban đầu đơn giản là chỉ định endpoint `ldaps://`.

~~~yaml
# application.yml — tên miền và DN chỉ để minh họa
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Ý nghĩa:

1. `spring.ldap.urls` chỉ định kết nối **TLS từ đầu**.
2. `spring.ldap.base` xác định DN gốc cho các truy vấn tương đối.
3. `spring.ldap.username` và `spring.ldap.password` được dùng khi context thực hiện bind.
4. `${LDAP_BIND_PASSWORD}` yêu cầu cấu hình lấy mật khẩu từ môi trường triển khai, giúp tránh ghi cứng bí mật trong YAML.

Khi tự cấu hình hoạt động, Spring Boot tạo các bean LDAP phù hợp với những thuộc tính đó. `LdapTemplate` hoặc `LdapClient` sử dụng context source được cấp sẽ kết nối qua LDAPS. Chỉ thuộc tính `urls` không bảo đảm tin cậy server: **JVM vẫn phải xác minh chứng chỉ và hostname**.

### 4.1. Khi muốn tự định nghĩa LdapContextSource

Trong ứng dụng Spring Framework hoặc khi cần kiểm soát rõ bean nguồn kết nối, có thể định nghĩa trực tiếp:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapsDirectoryConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.bind-dn}") String bindDn,
            @Value("${directory.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

Các thuộc tính của ví dụ trên:

~~~yaml
# application.yml — namespace riêng để cấu hình bean thủ công
directory:
  ldap:
    url: ldaps://directory.example.org:636
    base: dc=example,dc=org
    bind-dn: cn=app-reader,ou=services,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Hai ví dụ **là hai phương án thay thế**, không phải cấu hình bắt buộc chạy đồng thời. Nếu tự khai báo bean `LdapContextSource` trong ứng dụng Spring Boot đang có auto-configuration, phải xác định bean nào thực sự được tiêm vào từng thành phần LDAP. Nếu có nhiều bean, sử dụng cách định danh và inject rõ ràng để tránh vô tình chọn một kết nối khác.

Trong ví dụ Java, Spring quản lý lifecycle khởi tạo `LdapContextSource`. Nếu tạo đối tượng này trực tiếp bên ngoài container Spring để thử nghiệm, cần thực hiện lifecycle khởi tạo theo API trước khi sử dụng; không lấy mã cấu hình bean rồi dùng như một context đã khởi tạo.

### 4.2. Cấu hình nhiều endpoint LDAPS

Khi có nhiều máy chủ thư mục để dự phòng, có thể cấu hình danh sách URL:

~~~java
LdapContextSource source = new LdapContextSource();
source.setUrls(new String[] {
    "ldaps://directory-a.example.org:636",
    "ldaps://directory-b.example.org:636"
});
source.setBase("dc=example,dc=org");
source.setUserDn("cn=app-reader,ou=services,dc=example,dc=org");
source.setPassword(System.getenv("LDAP_BIND_PASSWORD"));
~~~

Mỗi máy chủ phải cung cấp chứng chỉ có hostname phù hợp với **tên endpoint tương ứng** và chuỗi CA mà ứng dụng tin cậy. Không thêm `ldap://...:389` vào danh sách để dùng như đường dự phòng không được bảo vệ. Việc chuyển máy chủ an toàn còn phụ thuộc cách client kết nối lại, chính sách TLS, thời gian chờ và hành vi của nhà cung cấp LDAP.

## 5. Cấu hình StartTLS trong LdapContextSource

StartTLS phù hợp khi máy chủ cung cấp kết nối `ldap://` và cho phép nâng cấp TLS thông qua LDAP Extended Operation. **Chỉ đặt `ldap://` không tự kích hoạt StartTLS**.

Với Spring LDAP, `DefaultTlsDirContextAuthenticationStrategy` hỗ trợ thực hiện StartTLS như một phần của quy trình xác thực. Đây là lựa chọn phù hợp cho tình huống simple bind bằng DN/mật khẩu sau khi kết nối đã được nâng cấp.

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class StartTlsDirectoryConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.bind-dn}") String bindDn,
            @Value("${directory.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);    // ldap://directory.example.org:389
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);

        // Mỗi kết nối LDAP phải nâng cấp TLS trước khi bind.
        source.setAuthenticationStrategy(
            new DefaultTlsDirContextAuthenticationStrategy()
        );

        // Tránh tái sử dụng kết nối JNDI khi chưa kiểm chứng vòng đời StartTLS.
        source.setPooled(false);
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

~~~yaml
# application.yml — dùng cùng Java configuration ở trên
directory:
  ldap:
    url: ldap://directory.example.org:389
    base: dc=example,dc=org
    bind-dn: cn=app-reader,ou=services,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

Đây là một ví dụ **cấu hình StartTLS ở ContextSource**, không phải cơ chế TLS mới do `LdapTemplate` cung cấp. Với cấu hình đúng, source quản lý context và chiến lược xác thực phải tiến hành nâng cấp TLS trước khi bind.

### 5.1. Thứ tự kết nối quyết định an toàn

~~~mermaid
sequenceDiagram
    participant T as LdapTemplate
    participant C as LdapContextSource
    participant D as LDAP server
    T->>C: Yêu cầu context để search
    C->>D: Mở kết nối ldap://
    C->>D: StartTLS ExtendedRequest
    D-->>C: Chấp nhận StartTLS
    C->>D: TLS handshake
    D-->>C: Chứng chỉ server
    C->>C: Xác minh chain, hostname và TLS
    alt TLS hợp lệ
        C->>D: BindRequest trong TLS
        D-->>C: BindResponse
        C-->>T: Context đã xác thực
        T->>D: SearchRequest trong TLS
        D-->>T: SearchResultEntry trong TLS
    else TLS thất bại
        C-->>T: Lỗi kết nối, không có context
    end
~~~

Phản hồi server chấp nhận yêu cầu StartTLS chỉ cho phép **bắt đầu** TLS handshake; chưa chứng minh TLS hoạt động. Cần để bắt tay và việc xác thực máy chủ thành công trước khi gửi thông tin bind.

Không nên tùy ý đổi chiến lược StartTLS thành `ExternalTlsDirContextAuthenticationStrategy`. Chiến lược này có liên quan đến xác thực **SASL EXTERNAL** trong những triển khai hỗ trợ, khác với ví dụ simple bind bằng DN/mật khẩu. Phải chọn đúng theo phương thức xác thực mà máy chủ yêu cầu.

### 5.2. Spring Boot không tự bật StartTLS chỉ vì có URL ldap://

Một cấu hình chỉ gồm:

~~~yaml
spring:
  ldap:
    urls: ldap://directory.example.org:389
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

**không đủ để khẳng định có StartTLS**. Cần bảo đảm cấu hình ứng dụng thực sự gắn chiến lược StartTLS với `LdapContextSource` mà các thao tác LDAP dùng. Khi có cả cấu hình tự động và bean tạo thủ công, hãy kiểm tra bean được inject và thử kết nối từ ứng dụng thật.

## 6. Truststore và xác minh danh tính máy chủ

TLS chỉ bảo vệ khỏi kết nối nhầm máy chủ khi client xác minh được chứng chỉ. Hai kiểm tra cần phân biệt:

1. **Certificate chain validation:** chứng chỉ server phải xây được đường tin cậy tới CA/trust anchor được phép, có chữ ký và thời hạn hợp lệ, tuân thủ các ràng buộc PKI.
2. **Hostname verification:** hostname trong URL mà client đang kết nối phải khớp với danh tính được khai báo trong `Subject Alternative Name (SAN)` của chứng chỉ server.

Ví dụ `ldaps://directory.example.org:636` thường cần chứng chỉ có `DNS:directory.example.org` trong SAN. Chứng chỉ hợp lệ cho `other.example.org` không được chấp nhận chỉ vì cùng CA ký. Nếu client sử dụng địa chỉ IP, chứng chỉ cần có SAN loại IP phù hợp.

### 6.1. Truststore cho JVM

Nếu CA nội bộ không có trong tập CA đáng tin của JDK, có thể tạo truststore PKCS#12 từ chứng chỉ CA do tổ chức cung cấp và đã xác minh:

~~~bash
# Import CA đã được xác minh, keytool yêu cầu mật khẩu khi cần.
keytool -importcert \
  -alias organization-directory-ca \
  -file organization-directory-ca.pem \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12

# Kiểm tra lại alias, fingerprint, hiệu lực và thông tin CA.
keytool -list -v \
  -alias organization-directory-ca \
  -keystore ldap-truststore.p12 \
  -storetype PKCS12
~~~

Sau đó cấu hình JVM sử dụng truststore phù hợp:

~~~text
-Djavax.net.ssl.trustStore=/etc/app/security/ldap-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Nếu cần mật khẩu truststore, hãy phân phối nó bằng cơ chế quản lý secret của môi trường và tránh in ra dòng lệnh/log. Các thuộc tính `javax.net.ssl.*` có phạm vi tiến trình JVM khi dùng cấu hình JSSE mặc định; chúng **có thể ảnh hưởng** các kết nối TLS khác như HTTPS. Nếu ứng dụng dùng `SSLContext` hoặc socket factory tùy biến, phải kiểm tra chính xác nơi cấu hình tin cậy thực sự được áp dụng.

Đồng thời, máy chủ LDAP nên gửi đầy đủ các chứng chỉ trung gian cần thiết để client xây được chain tới trust anchor. Việc import CA vào truststore **không thay thế** hostname verification.

### 6.2. Kiểm tra hostname trong LDAPS và StartTLS

Hành vi xác minh endpoint trên Java/JNDI có thể khác theo phiên bản JDK, đường kết nối, socket factory hoặc chiến lược TLS tùy biến. Vì vậy, với cả LDAPS và StartTLS cần kiểm tra bằng **kết nối thực tế của ứng dụng**:

- Chứng chỉ hợp lệ và SAN khớp hostname → có thể tiến hành bind nếu mọi điều kiện TLS khác đạt.
- CA không tin cậy → kết nối bị từ chối.
- CA tin cậy nhưng SAN sai hostname → kết nối vẫn phải bị từ chối.
- Chứng chỉ hết hạn → không được tiếp tục bind.

Không dùng trust manager chấp nhận mọi chứng chỉ, bỏ qua hostname hay hạ cấp sang LDAP không TLS khi xác minh thất bại.

## 7. Pooling, bind và vòng đời context

Spring LDAP có thể tạo nhiều context trong suốt vòng đời ứng dụng. Tối ưu kết nối bằng pooling giúp giảm chi phí mở kết nối nhưng cũng làm thay đổi cách quản lý phiên TLS và xác thực.

| Trường hợp | Điều cần chú ý |
| --- | --- |
| LDAPS, context mới | Mỗi kết nối mới cần hoàn tất TLS và xác thực máy chủ trước LDAP bind. |
| LDAPS, context được tái sử dụng | Pool phải quản lý kết nối còn sống, thuộc tính bảo mật và cách hết hạn phiên phù hợp. |
| StartTLS, context mới | Bắt buộc nâng cấp TLS trước bind; không tái sử dụng kết nối rõ do lỗi. |
| StartTLS với JNDI pooling | Không mặc định pooling tương thích vòng đời StartTLS; cần kiểm thử kỹ hoặc tắt pooling này. |
| Pooling ở tầng Spring LDAP | Kiểm chứng factory, xác thực, đóng/trả context và chính sách hủy kết nối lỗi TLS. |
| Bind theo người dùng cuối | Mọi thông tin đăng nhập của người dùng cũng phải đi qua TLS; xem xét việc context có thể bị tái sử dụng sai danh tính. |

Trong ví dụ StartTLS, `source.setPooled(false)` giữ tắt pooling JNDI cho source được tạo. Tuy nhiên điều đó **không tự động tắt** một pooling wrapper khác mà ứng dụng có thể khai báo. Nếu dùng cơ chế pooling riêng của Spring LDAP, phải xác minh nó tạo, xác thực, tái sử dụng và đóng context TLS đúng.

Ngoài pooling, cần kiểm tra những đường đi đặc biệt: nhiều `ContextSource`, máy chủ dự phòng, referral LDAP dẫn sang endpoint khác, proxy, load balancer và thao tác JNDI trực tiếp. **Một bean nguồn kết nối có TLS không chứng minh tất cả kết nối LDAP của ứng dụng đều an toàn.**

## 8. Độ tin cậy và xử lý lỗi TLS

Hệ thống có thể gặp lỗi khi bắt tay TLS, xây certificate chain, so khớp hostname hoặc khi máy chủ StartTLS từ chối nâng cấp. Quy tắc ứng dụng là **fail closed**: không tiếp tục thao tác nhạy cảm trên kết nối chưa được TLS bảo vệ.

| Lỗi hoặc tình huống | Nguyên nhân có thể | Cách xử lý an toàn |
| --- | --- | --- |
| `PKIX path building failed` | Không tin CA, thiếu intermediate hoặc cấu hình sai truststore | Xác minh chuỗi và truststore đang dùng; dừng bind đến khi sửa xong. |
| Hostname/SAN mismatch | URL không khớp SAN của chứng chỉ | Sửa endpoint hoặc cấp chứng chỉ đúng; không tắt hostname verification. |
| Certificate expired | Chứng chỉ máy chủ hết hạn hoặc đồng hồ sai | Gia hạn/cập nhật chứng chỉ và thử lại. |
| StartTLS operation unavailable | Server không hỗ trợ hoặc từ chối StartTLS | Báo lỗi; không thử simple bind trên kết nối rõ. |
| TLS handshake timeout | Sự cố mạng hoặc endpoint không phản hồi | Cấu hình timeout và retry có giới hạn, chỉ retry các endpoint TLS hợp lệ. |
| Bind trả invalid credentials **sau khi TLS thành công** | Sai tài khoản, mật khẩu hoặc chính sách xác thực LDAP | Điều tra bind riêng; không biến lỗi mật khẩu thành lý do tắt TLS. |
| Máy chủ dự phòng chỉ cho LDAP rõ | Cấu hình dự phòng không đạt chính sách | Loại endpoint không an toàn khỏi danh sách; sửa hạ tầng. |

### 8.1. Tách lỗi kết nối và lỗi xác thực

Lỗi TLS thường xảy ra **trước** LDAP bind. Lỗi `invalidCredentials` sau khi TLS hoạt động là lỗi xác thực LDAP. Nếu không phân biệt, người vận hành có thể cố “sửa lỗi” bằng cách vô hiệu hóa kiểm tra chứng chỉ, khiến vấn đề nghiêm trọng hơn.

Spring LDAP có thể chuyển lỗi JNDI thành các exception của Spring LDAP. Khi log, ghi loại lỗi, endpoint logic và thông tin chẩn đoán phù hợp; **không ghi mật khẩu, khóa riêng, nội dung nhạy cảm của entry hoặc đầy đủ thông tin xác thực**.

### 8.2. Timeout và retry

JNDI LDAP hỗ trợ các thuộc tính môi trường, ví dụ:

~~~java
import java.util.Map;
import org.springframework.ldap.core.support.LdapContextSource;

LdapContextSource source = new LdapContextSource();
source.setUrl("ldaps://directory.example.org:636");
source.setBase("dc=example,dc=org");
source.setBaseEnvironmentProperties(Map.of(
    "com.sun.jndi.ldap.connect.timeout", "5000",
    "com.sun.jndi.ldap.read.timeout", "10000"
));
~~~

Các giá trị được biểu diễn bằng **mili giây**, chỉ có tính minh họa; hiệu lực cụ thể tùy nhà cung cấp JNDI và môi trường. Đoạn mã rút gọn để thể hiện thuộc tính timeout, chưa bao gồm tài khoản bind và lifecycle bean. Có timeout không thay thế việc xác minh TLS, nhưng giúp ứng dụng không treo vô hạn trong một số tình huống kết nối.

Nếu retry khi có lỗi, chỉ dùng các endpoint đáp ứng yêu cầu bảo mật. **Không tự thay `ldaps://` bằng `ldap://`**, cũng không xóa chiến lược StartTLS sau lần đầu thất bại.

## 9. Kiểm thử cấu hình ContextSource

### 9.1. Kiểm tra endpoint độc lập

Trong môi trường lab được phép, có thể kiểm tra LDAPS hoặc StartTLS bằng OpenSSL:

~~~bash
# LDAPS: TLS từ đầu kết nối.
openssl s_client \
  -connect directory.example.org:636 \
  -servername directory.example.org \
  -verify_hostname directory.example.org \
  -verify_return_error

# StartTLS: yêu cầu nâng cấp kết nối LDAP rồi mới TLS.
openssl s_client \
  -starttls ldap \
  -connect directory.example.org:389 \
  -verify_hostname directory.example.org \
  -verify_return_error
~~~

Kiểm tra kết quả xác minh chuỗi, hostname, thời hạn chứng chỉ và TLS version. OpenSSL có truststore/chính sách riêng; kết quả thành công **chưa đủ** để kết luận JVM của ứng dụng cũng sẽ thành công.

### 9.2. Kiểm tra LDAP với thông tin giả

Với công cụ `ldapsearch` trong môi trường thử nghiệm:

~~~bash
# Kết nối LDAPS, nhập mật khẩu tương tác.
ldapsearch -H ldaps://directory.example.org:636 \
  -x -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "dc=example,dc=org" "(uid=test.user)" cn

# StartTLS bắt buộc (-ZZ), rồi mới simple bind.
ldapsearch -H ldap://directory.example.org:389 \
  -ZZ -x -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "dc=example,dc=org" "(uid=test.user)" cn
~~~

Trong `ldapsearch`, `-ZZ` yêu cầu StartTLS thành công, `-W` hỏi mật khẩu tương tác. Cấu hình CA phù hợp cho công cụ; không nhập mật khẩu thật trên dòng lệnh hoặc tắt xác minh chứng chỉ để đạt kết quả.

### 9.3. Kiểm thử bằng chính LdapTemplate

Một truy vấn đọc đơn giản giúp xác nhận `LdapTemplate` đang dùng đúng context:

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class DirectoryProbe {
    private final LdapTemplate ldapTemplate;

    public DirectoryProbe(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findCommonNames(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attributes ->
                (String) attributes.get("cn").get()
        );
    }
}
~~~

Truy vấn thành công kiểm chứng **khả năng hoạt động**, chưa đủ chứng minh bảo mật. Hãy bổ sung trường hợp lỗi có chủ đích trong lab:

| Kiểm thử | Kết quả bắt buộc |
| --- | --- |
| LDAPS dùng chứng chỉ hợp lệ đúng hostname | Kết nối và bind thành công; truy vấn hoạt động. |
| CA không có trong truststore | Kết nối thất bại trước bind. |
| Chứng chỉ có SAN không khớp URL | Kết nối bị từ chối; không gửi simple bind. |
| Chứng chỉ server hết hạn | Kết nối bị từ chối. |
| StartTLS không được máy chủ hỗ trợ | Không bind/truy vấn nhạy cảm qua kết nối rõ. |
| StartTLS được chấp nhận nhưng TLS handshake lỗi | Ngừng phiên trước bind. |
| Có hai `ContextSource` với cấu hình khác nhau | Kiểm tra từng bean được inject; không cho phép bean không bảo vệ dữ liệu nhạy cảm. |
| Máy chủ chính lỗi, thử endpoint dự phòng | Chỉ endpoint có TLS hợp lệ được sử dụng. |
| Pool tái sử dụng context sau lỗi hoặc hết hạn | Context phải được hủy/tạo lại an toàn; không gửi dữ liệu trên phiên TLS không hợp lệ. |

Tại lab, có thể quan sát lưu lượng để xác minh TLS bắt đầu **trước** bind, chỉ dùng tài khoản giả và dữ liệu không nhạy cảm. Đối với StartTLS, kỳ vọng thấy thao tác mở rộng StartTLS trước bản ghi TLS; các thông điệp bind và search sau khi nâng cấp phải được bảo vệ trong TLS.

## 10. Tình huống thực hành: cấu hình ContextSource cho hai môi trường

**Bối cảnh:** Một dịch vụ quản lý nhân sự Spring LDAP cần đọc `mail` và `memberOf`:

- **Staging:** máy chủ cung cấp `ldaps://staging-directory.example.org:636` với chứng chỉ do CA nội bộ ký.
- **Production:** hệ thống LDAP chỉ cung cấp `ldap://prod-directory.example.org:389` nhưng hỗ trợ StartTLS.
- Ứng dụng hiện có `LdapTemplate`, một tài khoản dịch vụ chỉ đọc và một cơ chế retry khi kết nối lỗi.

Nhóm phát triển đề xuất dùng cùng `ldap://` cho cả hai môi trường để giảm cấu hình và bật fallback không mã hóa khi StartTLS lỗi.

**Yêu cầu:**

1. Chọn cách cấu hình `ContextSource` cho mỗi môi trường và giải thích vì sao.
2. Mô tả thứ tự thiết lập kết nối cần có trước khi `LdapTemplate` gửi search.
3. Nêu ít nhất ba phép thử chứng minh chính sách TLS thực sự hoạt động.
4. Khi StartTLS lỗi ở production, ứng dụng cần xử lý như thế nào?
5. Nếu bổ sung `LdapClient` hoặc ODM, cần làm gì để các thao tác mới an toàn?

**Hướng giải:**

1. Staging dùng URL `ldaps://` với truststore tin cậy CA nội bộ và kiểm tra SAN/hostname. Production dùng `ldap://` **cùng** `DefaultTlsDirContextAuthenticationStrategy`; kiểm tra khả năng StartTLS của máy chủ.
2. LDAPS phải bắt tay và xác minh TLS trước LDAP bind. StartTLS phải gửi yêu cầu nâng cấp, bắt tay, xác minh TLS, rồi mới bind. Sau khi có context phù hợp, `LdapTemplate` thực hiện search trong kênh an toàn.
3. Thử kết nối hợp lệ; thử CA không tin cậy; thử SAN sai; thử server từ chối StartTLS và xác nhận không có bind trên kênh rõ; kiểm tra endpoint dự phòng và pooling.
4. Ghi nhận lỗi, không thực hiện thao tác LDAP nhạy cảm và không fallback sang kết nối rõ. Retry chỉ sau khi có endpoint an toàn và điều kiện vận hành phù hợp.
5. Bảo đảm `LdapClient` hoặc ODM dùng cùng nguồn `ContextSource` đã kiểm chứng, hoặc một context source khác được cấu hình và thử nghiệm TLS tương đương. Rà soát thêm bind theo tài khoản người dùng cuối, referral và kết nối phụ.

## 11. Những điểm cần nhớ

- **`ContextSource` quyết định cách tạo kết nối LDAP** cho `LdapTemplate`, `LdapClient` và ODM; các API truy vấn không tự kích hoạt TLS.
- Với **LDAPS**, cấu hình `ldaps://` và xác minh CA, certificate chain, SAN/hostname của endpoint.
- Với **StartTLS**, chỉ `ldap://` là chưa đủ; cần cơ chế nâng cấp như `DefaultTlsDirContextAuthenticationStrategy`, và phải hoàn tất TLS **trước simple bind**.
- **Truststore, xác minh hostname, vòng đời pooling và danh sách endpoint dự phòng** đều là một phần của bảo mật kết nối.
- Khi TLS lỗi, **fail closed**: dừng thao tác, xử lý nguyên nhân rồi thử lại qua kết nối được bảo vệ. Kiểm thử cả trường hợp hoạt động và các nhánh lỗi trong chính ứng dụng Java.
