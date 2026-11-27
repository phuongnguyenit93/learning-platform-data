# LDAPS và StartTLS

## 1. Bối cảnh và mục tiêu học tập

**Spring LDAP** hỗ trợ ứng dụng Java truy cập dịch vụ thư mục: xác thực tài khoản, tra cứu DN và entry, lọc kết quả, đọc thuộc tính, kiểm tra nhóm hoặc cập nhật dữ liệu. Các API như `LdapTemplate`, `LdapClient` và ODM dùng kết nối do `ContextSource` cung cấp. Vì thông điệp LDAP có thể chứa mật khẩu khi **simple bind**, DN, bộ lọc, thuộc tính và kết quả tìm kiếm, bảo mật đường truyền phải được thiết lập trước khi gửi dữ liệu nhạy cảm.

Trong chương **TLS và bảo mật kết nối**, hai cơ chế kết nối quan trọng là:

- **LDAPS:** dùng TLS từ lúc bắt đầu kết nối TCP, trước khi trao đổi thông điệp LDAP.
- **StartTLS:** bắt đầu trên kết nối LDAP thông thường, yêu cầu nâng cấp sang TLS, xác thực máy chủ và chỉ tiếp tục trao đổi LDAP nhạy cảm sau khi TLS thành công.

Sau bài học, người học có thể phân biệt hai cơ chế, chọn cách kết nối phù hợp, cấu hình `LdapContextSource`, kiểm tra chứng chỉ và triển khai chính sách **không tiếp tục trên kết nối rõ nếu TLS thất bại**.

## 2. So sánh LDAPS và StartTLS

LDAP là giao thức thao tác dịch vụ thư mục; TLS là cơ chế bảo vệ kênh truyền. TLS giúp bảo vệ tính bí mật và toàn vẹn của dữ liệu, đồng thời xác thực danh tính máy chủ bằng chứng chỉ khi được cấu hình đúng. **TLS không tự phân quyền LDAP**: máy chủ vẫn quyết định tài khoản nào được đọc, sửa hoặc xóa entry.

| Tiêu chí | LDAPS (LDAP over TLS) | LDAP + StartTLS |
| --- | --- | --- |
| URI thường gặp | `ldaps://directory.example.org:636` | `ldap://directory.example.org:389` |
| Cổng quy ước | 636 | 389 |
| Thời điểm thiết lập TLS | Ngay sau kết nối TCP | Sau yêu cầu mở rộng StartTLS và phản hồi chấp nhận |
| Thời điểm được gửi simple bind | Sau bắt tay TLS thành công | Sau **yêu cầu StartTLS, bắt tay TLS và kiểm tra chứng chỉ** thành công |
| Yêu cầu phía máy chủ | Endpoint TLS ngay từ đầu | Hỗ trợ thao tác LDAP StartTLS |
| Cấu hình Spring LDAP chính | URL `ldaps://` và truststore phù hợp | URL `ldap://` cùng chiến lược StartTLS bắt buộc |
| Lỗi triển khai thường gặp | Tắt xác minh chứng chỉ; fallback sang LDAP rõ | Chỉ khai báo URL `ldap://`; nâng cấp thất bại nhưng vẫn bind |

Khi thương lượng cùng phiên bản TLS, thuật toán và chính sách xác thực chứng chỉ, LDAPS và StartTLS có thể bảo vệ **các thông điệp LDAP ở trong kênh TLS** ở mức tương đương. Điểm khác biệt lớn nằm ở **thứ tự thiết lập kênh** và cách xử lý lỗi.

Không thể kết luận kết nối đã mã hóa chỉ dựa vào cổng 636 hoặc 389. Cổng là quy ước có thể thay đổi theo cấu hình; điều quan trọng là bắt tay TLS thật sự thành công và xác minh máy chủ đúng.

## 3. LDAPS: thiết lập TLS trước LDAP

Với LDAPS, kết nối TCP khởi tạo được dùng ngay cho bắt tay TLS. Client kiểm tra chứng chỉ và tên máy chủ, sau đó mới gửi `BindRequest` hoặc `SearchRequest`.

~~~mermaid
sequenceDiagram
    participant App as Spring LDAP client
    participant Dir as LDAP server
    App->>Dir: TCP tới cổng LDAPS
    App->>Dir: TLS ClientHello
    Dir-->>App: TLS ServerHello và certificate
    App->>App: Kiểm tra CA, SAN/hostname, TLS
    App->>Dir: Hoàn tất bắt tay TLS
    Note over App,Dir: Kênh TLS đã sẵn sàng
    App->>Dir: BindRequest trong TLS
    Dir-->>App: BindResponse trong TLS
    App->>Dir: SearchRequest trong TLS
    Dir-->>App: SearchResultEntry trong TLS
~~~

Nếu máy chủ gửi chứng chỉ hết hạn, không được tin cậy hoặc không khớp hostname, ứng dụng phải báo lỗi và ngừng kết nối. Việc thử lại bằng `ldap://` không mã hóa sau lỗi TLS sẽ làm mất chính sách bảo vệ ban đầu.

### 3.1. Cấu hình LDAPS cho Spring Boot

Nếu ứng dụng sử dụng cấu hình tự động Spring Boot cho Spring LDAP, có thể khai báo:

~~~yaml
# application.yml, giá trị tên miền/DN chỉ để minh họa
spring:
  ldap:
    urls: ldaps://directory.example.org:636
    base: dc=example,dc=org
    username: cn=app-reader,ou=services,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

- `spring.ldap.urls` chọn endpoint LDAPS.
- `base` là DN gốc để tra cứu tương đối.
- `username` và `password` là thông tin đăng nhập của tài khoản dịch vụ.
- Biến môi trường giúp tránh ghi mật khẩu trực tiếp trong mã nguồn, nhưng không thay thế TLS.

Khi Spring Boot tạo `LdapContextSource` từ cấu hình trên, những thao tác thông qua `LdapTemplate`, `LdapClient` hoặc ODM sử dụng nguồn context đó sẽ đi qua endpoint LDAPS. Nếu hệ thống có nhiều `ContextSource` hoặc client kết nối trực tiếp JNDI, cần kiểm tra từng đường kết nối riêng.

### 3.2. Chứng chỉ và Java truststore

TLS chỉ đạt mục tiêu xác thực máy chủ khi ứng dụng xác minh được chuỗi chứng chỉ, tính hợp lệ và tên máy chủ. Chứng chỉ máy chủ cần có SAN chứa DNS/IP phù hợp với địa chỉ client dùng kết nối. Với CA nội bộ, JVM cần tin cậy CA đó; có thể cấu hình truststore PKCS#12:

~~~text
-Djavax.net.ssl.trustStore=/etc/app/security/ldap-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Đường dẫn minh họa cần đổi theo môi trường triển khai. Bí mật mở truststore (nếu có) phải được quản lý bằng cơ chế secret phù hợp. Không đưa mật khẩu vào tài liệu vận hành hoặc log. Ngoài truststore, hãy kiểm tra hành vi xác thực hostname của phiên bản JDK/JNDI đang dùng; không tắt xác thực endpoint hoặc sử dụng trust manager chấp nhận mọi chứng chỉ để vượt qua lỗi cấu hình.

## 4. StartTLS: nâng cấp một kết nối LDAP

**StartTLS** là LDAP Extended Operation với OID `1.3.6.1.4.1.1466.20037`. Client bắt đầu kết nối LDAP thường, yêu cầu nâng cấp, nhận phản hồi của máy chủ rồi mới tiến hành bắt tay TLS. Điều này thường được thực hiện trên cổng 389.

Trình tự bắt buộc khi dùng StartTLS cho thông tin nhạy cảm:

1. Mở TCP tới `ldap://directory.example.org:389`.
2. Gửi `StartTLS ExtendedRequest` **trước** simple bind và các truy vấn nhạy cảm.
3. Chờ máy chủ chấp nhận yêu cầu nâng cấp.
4. Bắt tay TLS và xác minh CA, hostname, hiệu lực chứng chỉ và chính sách TLS.
5. Chỉ sau khi TLS thành công mới gửi bind, tìm kiếm và cập nhật entry.
6. Nếu StartTLS bị từ chối hoặc bắt tay thất bại, đóng kết nối và báo lỗi; tuyệt đối không tiếp tục simple bind qua phiên rõ.

~~~mermaid
sequenceDiagram
    participant App as Spring LDAP client
    participant Dir as LDAP server
    App->>Dir: TCP tới cổng LDAP
    App->>Dir: StartTLS ExtendedRequest
    Dir-->>App: ExtendedResponse: success
    App->>Dir: TLS handshake
    Dir-->>App: Chứng chỉ máy chủ
    App->>App: Xác thực CA và hostname
    Note over App,Dir: TLS được xác minh thành công
    App->>Dir: BindRequest trong TLS
    Dir-->>App: BindResponse trong TLS
    App->>Dir: SearchRequest trong TLS
    Dir-->>App: SearchResultEntry trong TLS
~~~

**Phản hồi StartTLS thành công chưa chứng minh TLS đã hoạt động.** Nó chỉ cho phép bắt đầu quá trình bắt tay; chỉ khi bắt tay hoàn tất và việc xác thực máy chủ đạt yêu cầu, client mới có thể sử dụng kênh được bảo vệ.

### 4.1. “Máy chủ hỗ trợ StartTLS” không có nghĩa “client đang dùng TLS”

Giả sử server trên cổng 389 công bố hỗ trợ StartTLS. Nếu ứng dụng chỉ đặt URL `ldap://directory.example.org:389` nhưng không gọi cơ chế nâng cấp, phiên có thể vẫn là LDAP không mã hóa. Nếu ứng dụng cố nâng cấp nhưng xử lý lỗi bằng cách bỏ qua TLS và tiếp tục bind, mật khẩu vẫn có thể bị lộ.

Vì vậy, cần yêu cầu **StartTLS bắt buộc** ở client và nên bổ sung chính sách máy chủ từ chối simple bind chưa được bảo vệ. Đường kết nối phải **fail closed**: từ chối thay vì hạ cấp bảo mật khi gặp lỗi.

## 5. Ví dụ StartTLS với Spring LDAP

Spring LDAP cung cấp `DefaultTlsDirContextAuthenticationStrategy`, dùng cùng `LdapContextSource` để nâng cấp StartTLS trước khi xác thực bằng thông tin bind được cấu hình.

Ví dụ cấu hình ứng dụng:

~~~yaml
# application.yml
directory:
  ldap:
    url: ldap://directory.example.org:389
    base: dc=example,dc=org
    bind-dn: cn=app-reader,ou=services,dc=example,dc=org
    bind-password: ${LDAP_BIND_PASSWORD}
~~~

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.DefaultTlsDirContextAuthenticationStrategy;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapStartTlsConfiguration {

    @Bean
    public LdapContextSource ldapContextSource(
            @Value("${directory.ldap.url}") String url,
            @Value("${directory.ldap.base}") String base,
            @Value("${directory.ldap.bind-dn}") String bindDn,
            @Value("${directory.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url); // ldap://...:389
        source.setBase(base);
        source.setUserDn(bindDn);
        source.setPassword(password);

        // Thương lượng StartTLS trước khi xác thực.
        source.setAuthenticationStrategy(
            new DefaultTlsDirContextAuthenticationStrategy()
        );
        return source;
    }

    @Bean
    public LdapTemplate ldapTemplate(LdapContextSource ldapContextSource) {
        return new LdapTemplate(ldapContextSource);
    }
}
~~~

Tên thuộc tính `directory.ldap.*` được đặt riêng để cấu hình chủ động `LdapContextSource` trong ví dụ Java; không nhầm với namespace `spring.ldap.*` của cấu hình tự động Spring Boot. Spring sẽ gọi lifecycle khởi tạo cần thiết khi quản lý `LdapContextSource` dưới dạng bean.

Trong trường hợp máy chủ sử dụng xác thực **SASL EXTERNAL** dựa trên danh tính từ kết nối TLS, Spring LDAP còn có `ExternalTlsDirContextAuthenticationStrategy`. Đây là cơ chế xác thực khác với simple bind bằng DN/mật khẩu; phải chọn theo chính sách của máy chủ, không thay thế tùy ý hai chiến lược.

Lưu ý vận hành:

- `ldap://` trong ví dụ là có chủ đích **chỉ khi** chiến lược StartTLS được áp dụng. Gỡ `setAuthenticationStrategy(...)` mà giữ URL có thể khiến kênh trở nên không mã hóa.
- Nếu ứng dụng có thêm `ContextSource` khác, dùng JNDI trực tiếp, hoặc thực hiện bind bằng tài khoản người dùng cuối, phải xác minh TLS cũng được kích hoạt trên các đường đi đó.
- Với StartTLS, vòng đời context gồm tạo kết nối, nâng cấp TLS, bind, truy vấn và đóng kết nối. Không bật pooling hoặc tái sử dụng context nếu chưa kiểm chứng cách pool quản lý kết nối có trạng thái TLS, đặc biệt với JNDI pooling.
- Không để thư viện tự hạ cấp sang LDAP rõ khi StartTLS lỗi; thông báo lỗi và thử kết nối an toàn khi hạ tầng được khắc phục.
- TLS cung cấp kênh an toàn; quyền đọc/ghi của tài khoản dịch vụ vẫn cần giới hạn theo nguyên tắc quyền tối thiểu.

### 5.1. Truy vấn Spring LDAP đi qua context đã cấu hình

~~~java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

public class DirectoryLookup {
    private final LdapTemplate ldapTemplate;

    public DirectoryLookup(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findDisplayNames(String uid) {
        return ldapTemplate.search(
            query().base("ou=people").where("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("displayName").get()
        );
    }
}
~~~

`LdapTemplate` chỉ gửi tìm kiếm qua context; đoạn truy vấn **không tự bật TLS**. Cách bảo vệ đến từ `ContextSource` đã được cấu hình ở trên. Tương tự, những thao tác bằng `LdapClient` hoặc ODM cần sử dụng context source an toàn.

## 6. Nên chọn LDAPS hay StartTLS?

| Tình huống | Hướng chọn hợp lý | Điểm cần kiểm chứng |
| --- | --- | --- |
| Server có endpoint LDAPS ổn định, client muốn TLS ngay từ đầu | LDAPS | CA, SAN/hostname, giao thức TLS, truststore |
| Hạ tầng chuẩn hóa cổng LDAP và hỗ trợ StartTLS | StartTLS bắt buộc | Chiến lược nâng cấp trước bind; fail closed |
| Client dùng nhiều connection pool hoặc context provider | Đánh giá LDAPS trước và kiểm thử tùy hệ thống | Vòng đời TLS trên kết nối được tái sử dụng |
| Phải đi qua proxy/load balancer | Một trong hai tùy kiến trúc | TLS kết thúc ở đâu; mọi chặng nhạy cảm có bảo vệ không |
| Xác thực qua chứng chỉ client, thay vì mật khẩu | TLS với client certificate và cơ chế xác thực thích hợp | Cấu hình mTLS, chính sách SASL EXTERNAL, quyền thư mục |

Ví dụ: một dịch vụ Spring Boot chỉ cần tìm thuộc tính `memberOf` và hệ thống đã có `ldaps://directory.example.org:636` với chứng chỉ hợp lệ. LDAPS thường là lựa chọn có ít bước khởi tạo hơn. Nếu máy chủ chỉ cung cấp LDAP/389 và hỗ trợ StartTLS, có thể dùng StartTLS với điều kiện bắt buộc nâng cấp, xác thực chứng chỉ và dừng ngay nếu TLS không thành công.

### Rủi ro vận hành phải tính đến

**Nhiều endpoint:** Một endpoint dự phòng không hỗ trợ TLS sẽ tạo lỗ hổng nếu client tự fallback sang kết nối rõ.

**Proxy hoặc load balancer:** Nếu TLS kết thúc ở tầng proxy, đoạn từ proxy đến thư mục phải được đánh giá riêng. Kết nối được mã hóa từ ứng dụng đến proxy không bảo đảm mọi chặng sau đều được bảo vệ.

**Referral:** LDAP có thể trả địa chỉ một máy chủ thư mục khác. Kết nối khi theo referral phải tuân thủ chính sách TLS riêng; không giả định nó được kế thừa từ kết nối ban đầu.

**Đổi chứng chỉ:** Thay hostname, gia hạn chứng chỉ hoặc đổi CA có thể làm client Java từ chối bắt tay. Cần quy trình triển khai chứng chỉ và truststore phù hợp.

**TLS phiên bản và thuật toán:** Chính sách phải phù hợp yêu cầu bảo mật của tổ chức, thường ưu tiên phiên bản TLS hiện đại mà client/server cùng hỗ trợ. Không vô hiệu hóa kiểm tra hostname hay CA để tránh phải sửa nguyên nhân gốc.

## 7. Kiểm tra LDAPS và StartTLS trong lab

Với `openssl s_client`, có thể kiểm tra quá trình bắt tay và chứng chỉ. Thay hostname bằng endpoint thực của môi trường kiểm thử được phép:

~~~bash
# LDAPS: TLS ngay từ đầu.
openssl s_client \
  -connect directory.example.org:636 \
  -servername directory.example.org \
  -verify_hostname directory.example.org \
  -verify_return_error

# StartTLS: yêu cầu nâng cấp từ LDAP/389.
openssl s_client \
  -starttls ldap \
  -connect directory.example.org:389 \
  -verify_hostname directory.example.org \
  -verify_return_error
~~~

Hãy kiểm tra chứng chỉ, chain CA, hostname và phiên bản TLS được thương lượng. OpenSSL có thể dùng kho CA khác với JVM; kết quả OpenSSL thành công **không chứng minh** ứng dụng Java đã có truststore, xác minh endpoint hoặc chiến lược StartTLS đúng.

Để kiểm thử cả thao tác LDAP, dùng `ldapsearch` của OpenLDAP với mật khẩu nhập tương tác:

~~~bash
# Simple bind qua kênh LDAPS.
ldapsearch -H ldaps://directory.example.org:636 \
  -x -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "dc=example,dc=org" "(uid=test.user)" cn

# -ZZ: yêu cầu StartTLS bắt buộc trước simple bind.
ldapsearch -H ldap://directory.example.org:389 \
  -ZZ -x -D "cn=app-reader,ou=services,dc=example,dc=org" -W \
  -b "dc=example,dc=org" "(uid=test.user)" cn
~~~

`-W` giúp tránh truyền mật khẩu trong tham số lệnh; `-ZZ` trong `ldapsearch` yêu cầu StartTLS thành công. Vẫn cần cấu hình CA đáng tin cậy cho OpenLDAP client, xác minh máy chủ và thử nghiệm kết nối thật bằng ứng dụng Spring LDAP.

### Ma trận kiểm thử bảo mật

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| Chứng chỉ server được ký bởi CA không tin cậy | Client từ chối TLS; không fallback sang LDAP rõ |
| Chứng chỉ không khớp hostname | Client từ chối kết nối |
| Máy chủ từ chối yêu cầu StartTLS | Không thực hiện simple bind hoặc truy vấn nhạy cảm |
| StartTLS được chấp nhận nhưng bắt tay TLS lỗi | Dừng phiên trước bind |
| LDAPS hợp lệ | Bind và truy vấn hoạt động trong TLS |
| StartTLS hợp lệ | Yêu cầu nâng cấp trước, rồi TLS, sau đó mới có bind/truy vấn |
| Endpoint dự phòng không có TLS | Không tự chuyển sang kết nối không mã hóa |
| Pool, referral hoặc ContextSource thứ hai | Chính sách TLS vẫn được áp dụng cho mọi kết nối mới |

Nếu quan sát lưu lượng bằng công cụ bắt gói tin, chỉ dùng **tài khoản giả** trong lab được phép. Ở phiên LDAP rõ, các thông điệp có thể đọc được; với LDAPS và phiên đã nâng cấp StartTLS, dữ liệu LDAP được bảo vệ bên trong TLS, dù metadata như IP và cổng vẫn có thể lộ.

## 8. Bài tập tình huống

**Bối cảnh:** Dịch vụ quản lý nhân sự dùng `LdapTemplate` để tra cứu `mail` và `memberOf`. Dev có `ldap://dev-directory.example.org:389` hỗ trợ StartTLS; Staging có `ldaps://stage-directory.example.org:636` sử dụng CA nội bộ. Production có hai endpoint LDAPS; chứng chỉ ở endpoint dự phòng bị hết hạn. Một cơ chế retry cũ đang tự đổi từ `ldaps://` sang `ldap://` khi kết nối lỗi.

**Câu hỏi:**

1. Cấu hình Dev và Staging như thế nào để simple bind chỉ diễn ra trên TLS?
2. Khi Production lỗi chứng chỉ, có nên sử dụng fallback sang `ldap://` không?
3. Tại sao chỉ thay URL hoặc xác nhận cổng đang mở là chưa đủ?
4. Nếu đã thêm `DefaultTlsDirContextAuthenticationStrategy` cho một `LdapContextSource`, có thể khẳng định mọi truy vấn ứng dụng đã được bảo vệ chưa?

**Hướng giải:**

1. Dev cấu hình `ldap://` và chiến lược StartTLS bắt buộc, kiểm tra chứng chỉ và hostname. Staging cấu hình `ldaps://` và truststore tin cậy CA nội bộ.
2. Không. Dừng kết nối lỗi, sửa hoặc thay chứng chỉ endpoint và chỉ phục hồi khi TLS hoạt động hợp lệ.
3. Cần kiểm tra TLS handshake, xác thực CA/hostname, client truststore, đường qua proxy, retry, referral và pool. URI/cổng không chứng minh kênh đã được bảo vệ.
4. Chưa. Phải xác nhận mọi `ContextSource`, kết nối JNDI khác và luồng bind theo người dùng đều dùng TLS; đặc biệt kiểm thử các nhánh StartTLS thất bại hoặc kết nối tái sử dụng.

## 9. Tổng kết

- **LDAPS** thiết lập TLS trước mọi thông điệp LDAP; **StartTLS** yêu cầu nâng cấp kết nối LDAP rồi mới trao đổi dữ liệu nhạy cảm.
- Khi cấu hình chứng chỉ và thuật toán tương đương, hai cách có thể cung cấp mức bảo vệ tương đương cho thông điệp được gửi **sau khi TLS thành công**.
- Trong Spring LDAP, dùng URL `ldaps://` cho LDAPS hoặc `DefaultTlsDirContextAuthenticationStrategy` trên `LdapContextSource` dùng `ldap://` để triển khai StartTLS với simple bind.
- **Không gửi bind khi TLS chưa hoàn tất, không fallback xuống LDAP rõ và không tắt kiểm tra chứng chỉ.**
- Kiểm thử trên JVM thực tế, bao gồm truststore, hostname, máy chủ dự phòng, proxy, pool, referral và các trường hợp lỗi TLS.
