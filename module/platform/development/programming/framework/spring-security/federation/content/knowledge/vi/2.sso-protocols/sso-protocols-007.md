# Lựa chọn giao thức SSO cho ứng dụng web, mạng nội bộ và đối tác

**Bối cảnh:** Spring Security – federation → Giao thức SSO. Mục tiêu là chọn giao thức đăng nhập liên kết phù hợp với loại ứng dụng, hạ tầng danh tính và ranh giới tin cậy; đồng thời biết cách triển khai và kiểm chứng lựa chọn trong hệ sinh thái Spring Security.

## 1. Cần phân biệt SSO, federation, xác thực và cấp quyền

- **SSO (Single Sign-On)**: người dùng đã đăng nhập vào hệ thống danh tính có thể truy cập nhiều ứng dụng trong cùng một phiên nhận diện mà không phải nhập lại mật khẩu mỗi lần. SSO không đồng nghĩa với việc tất cả ứng dụng có chung cookie hay cùng phiên đăng xuất.
- **Federation (liên kết danh tính)**: ứng dụng tin vào bằng chứng xác thực do một tổ chức/hệ thống danh tính khác phát hành. Ví dụ: cổng đối tác tin vào IdP của doanh nghiệp đối tác theo hợp đồng kỹ thuật.
- **IdP/OP (Identity Provider/OpenID Provider)**: thành phần xác thực người dùng và phát hành thông tin đăng nhập. **RP/client** trong OIDC là ứng dụng sử dụng danh tính; **SP/RP** trong SAML là ứng dụng nhận assertion.
- **Authentication** xác định người dùng là ai; **authorization** quyết định họ được phép thao tác gì. Đăng nhập thành công không tự động trao quyền quản trị.
- **OAuth 2.0** là khung cấp quyền truy cập tài nguyên; bản thân OAuth 2.0 **không định nghĩa chuẩn xác thực người dùng**. **OpenID Connect (OIDC)** bổ sung lớp danh tính trên OAuth 2.0, gồm ID Token và các quy tắc kiểm chứng.
- **LDAP/Active Directory** là dịch vụ thư mục/danh tính, không phải một giao thức web SSO tương đương OIDC hay SAML. **SCIM** hỗ trợ cấp phát/thu hồi tài khoản, không thay cho luồng đăng nhập.

Phải phân biệt hai luồng: **người dùng đăng nhập vào web** (OIDC/SAML/Kerberos) và **dịch vụ gọi API** (thường OAuth 2.0 access token). Không lấy ID Token của OIDC làm Bearer token cho API chỉ vì cả hai đều là JWT.

## 2. Ma trận chọn giao thức theo môi trường

| Tình huống | Lựa chọn mặc định | Vì sao | Khi nào đổi phương án |
| --- | --- | --- | --- |
| Web hiện đại phục vụ nhân viên/khách hàng; ứng dụng Spring Boot | **OIDC – Authorization Code**, dùng PKCE theo loại client và chính sách bảo mật | Phù hợp web, mobile, API, có discovery/JWKS và claim chuẩn | IdP bắt buộc SAML hoặc ứng dụng legacy chỉ hỗ trợ SAML |
| SPA chạy trên trình duyệt, có backend | **OIDC Code + PKCE**; ưu tiên mô hình **BFF** khi có thể để giữ token tại server | Hạn chế token tồn tại trong mã JavaScript và dễ quản lý phiên | SPA thuần không có backend: public client + PKCE, xem xét kỹ nơi lưu token |
| Ứng dụng nội bộ chỉ dành cho máy Windows đã join domain, truy cập intranet | **Kerberos qua HTTP Negotiate/SPNEGO** nếu hạ tầng sẵn có và vận hành được | Tận dụng ticket đăng nhập Windows; trải nghiệm không nhập lại mật khẩu | Có thiết bị ngoài domain, mobile, Internet hoặc nhiều IdP: dùng OIDC qua IdP/broker liên kết AD |
| Cổng nội bộ đa thiết bị, hybrid, VPN/Internet | **OIDC với IdP doanh nghiệp**; IdP có thể dùng AD/Kerberos phía sau | Tách ứng dụng khỏi keytab, domain join và chính sách trình duyệt | Chỉ dùng Kerberos trực tiếp khi phạm vi đóng, các điều kiện SPNEGO ổn định |
| B2B đối tác yêu cầu SAML 2.0, ví dụ IdP doanh nghiệp truyền thống | **SAML 2.0 Web Browser SSO** | Tương thích hợp đồng metadata, certificate và assertion của đối tác | Nếu cả hai bên hỗ trợ OIDC và không ràng buộc SAML, xem xét OIDC để đơn giản hóa tích hợp web hiện đại |
| B2B đối tác hỗ trợ OIDC | **OIDC Code** với cấu hình issuer/client riêng theo đối tác | Tận dụng JSON/JWT, discovery/JWKS, liên kết API thuận lợi | Đối tác chỉ công bố metadata SAML hoặc yêu cầu luồng SAML |
| Backend gọi backend không có người dùng | **OAuth 2.0 Client Credentials** hoặc cơ chế workload identity thích hợp | Xác thực/ủy quyền máy, **không phải SSO của người dùng** | Nếu phải hành động nhân danh người dùng, đánh giá delegated access/token exchange thay vì giả lập tài khoản người dùng |
| Ứng dụng cũ chỉ hiểu CAS hoặc WS-Federation | Giữ giao thức ở **identity broker/gateway** hoặc lập kế hoạch nâng cấp | Giảm số lượng giao thức mà ứng dụng mới phải tự triển khai | Chỉ tích hợp trực tiếp khi có yêu cầu tương thích và thư viện được bảo trì |

**Nguyên tắc lựa chọn:** yêu cầu tương thích của IdP đối tác và môi trường người dùng là ràng buộc đầu tiên; sau đó cân đối an ninh, hỗ trợ thiết bị, khả năng vận hành, vòng đời chứng chỉ/khóa và trải nghiệm đăng nhập. Không có một giao thức thắng trong mọi trường hợp.

## 3. Hiểu cơ chế trước khi đưa ra quyết định

### 3.1. OIDC: lựa chọn chủ đạo cho web và hệ thống đa nền tảng

Luồng điển hình khi dùng **Authorization Code**:

1. Người dùng mở tài nguyên cần đăng nhập trên RP (ứng dụng Spring).
2. RP chuyển trình duyệt sang authorization endpoint của OP, kèm `client_id`, `redirect_uri`, `scope=openid`, `state` và tham số PKCE nếu áp dụng; `nonce` được dùng theo luồng/chính sách OIDC.
3. OP xác thực người dùng (có thể bằng MFA, Windows SSO hoặc cách khác) rồi chuyển trình duyệt về callback đã đăng ký với một authorization code.
4. RP đổi code lấy token qua kênh server-to-server khi là confidential client, kiểm chứng ID Token, thiết lập phiên ứng dụng và áp chính sách cấp quyền nội bộ.
5. Khi cần gọi API, client/backend dùng **access token** dành cho API đó; API tự kiểm chứng token theo vai trò resource server.

OIDC cho ứng dụng biết danh tính dựa trên `iss` (issuer), `sub` (subject) và các claim đã được kiểm chứng. **Cặp `(iss, sub)`** nên là khóa định danh liên kết bền vững; email hoặc tên hiển thị có thể đổi, tái sử dụng hay không được xác minh.

Các kiểm tra cốt lõi gồm chữ ký/thuật toán tin cậy, `iss`, `aud` chứa `client_id`, `exp`/thời gian, `nonce` khi đã gửi và ràng buộc giao dịch. `state` chống trộn lẫn yêu cầu và CSRF trong redirect; PKCE giúp ràng buộc code với client phát lệnh. Không tự viết trình kiểm chứng token bằng cách chỉ Base64-decode JWT.

**Chọn client hợp lý:** Spring MVC server-rendered thường là confidential client; SPA/mobile là public client. Public client phải dùng PKCE; confidential client cũng nên dùng PKCE. Với SPA có BFF, browser dùng cookie phiên `HttpOnly; Secure; SameSite`, còn BFF giữ token ở server và thực thi CSRF protection cho yêu cầu dùng cookie. Không sử dụng implicit flow hay Resource Owner Password Credentials để xây SSO mới.

### 3.2. SAML 2.0: chuẩn trao đổi assertion phổ biến trong B2B

Trong **SAML Web Browser SSO**:

1. SP tạo `AuthnRequest` (thường qua browser redirect) đến IdP.
2. IdP xác thực người dùng theo chính sách doanh nghiệp.
3. Browser gửi `SAMLResponse`, chứa assertion XML, về **Assertion Consumer Service (ACS)** của SP, thường qua HTTP POST.
4. SP kiểm chứng chữ ký bằng chứng chỉ IdP đã tin cậy, kiểm tra issuer, audience, recipient/destination, thời hạn, `InResponseTo` (với yêu cầu SP-initiated) và điều kiện của assertion trước khi tạo phiên đăng nhập.

Điểm mạnh là tương thích lâu năm với các IdP doanh nghiệp và hợp đồng federation qua metadata XML/X.509. Điểm tốn công là quản lý metadata, chứng chỉ ký/mã hóa, lệch giờ, binding, kích thước payload và sự khác nhau về claim/NameID giữa đối tác.

**Không nhầm** chứng chỉ ký assertion của IdP với chứng chỉ TLS của endpoint. Chữ ký XML hợp lệ là điều kiện cần nhưng phải được kiểm chứng trên đúng assertion/response thực sự dùng để xác thực, tránh nguy cơ XML signature wrapping. Đặc biệt không chấp nhận assertion do tenant khác phát hành vì cùng có email.

### 3.3. Kerberos/SPNEGO: SSO dựa trên đăng nhập máy trong intranet

Với máy thuộc domain và trình duyệt hỗ trợ HTTP Negotiate:

1. Ứng dụng yêu cầu xác thực qua `WWW-Authenticate: Negotiate`.
2. Trình duyệt lấy service ticket Kerberos cho SPN của dịch vụ, chẳng hạn `HTTP/portal.corp.example@CORP.EXAMPLE`, từ KDC/AD.
3. Trình duyệt gửi `Authorization: Negotiate ...`; server kiểm chứng ticket bằng service principal/keytab tương ứng và ánh xạ principal sang người dùng/nhóm của ứng dụng.
4. Ứng dụng có thể tạo phiên HTTP để thực thi phân quyền như các cơ chế đăng nhập khác.

Ưu điểm là SSO tự nhiên trên thiết bị doanh nghiệp đã cấu hình. Hạn chế là phụ thuộc DNS, SPN, đồng bộ thời gian, khả năng liên lạc với KDC, cấu hình browser/OS và bảo vệ keytab; trải nghiệm không tự hoạt động cho thiết bị không join domain hoặc bên ngoài mạng. HTTP Negotiate không có nghĩa là “gửi mật khẩu Windows lên web”. Cần xác nhận cơ chế đã thương lượng thực sự là Kerberos theo chính sách, không vô tình chấp nhận NTLM ngoài thiết kế.

Spring có **Spring Security Kerberos extension** cho SPNEGO; tích hợp này có cấu hình và vòng đời khác với `oauth2Login` hay `saml2Login`. Đánh giá tương thích phiên bản Spring, browser và môi trường AD trước khi chọn triển khai trực tiếp.

## 4. Ra quyết định theo từng nhóm ứng dụng

### 4.1. Web công khai hoặc web đa thiết bị

**Ưu tiên OIDC** khi tổ chức có một OP/IdP đáng tin cậy hỗ trợ OIDC. Triển khai Code flow, đăng ký chính xác redirect URI, bật HTTPS, thiết lập MFA/chính sách xác thực tại IdP, dùng bộ thư viện Spring Security để kiểm chứng. Ví dụ: cổng đặt hàng có backend Spring Boot nhận đăng nhập từ IdP; người dùng có thể tiếp tục sang hệ thống hỗ trợ cùng IdP mà không phải nhập lại thông tin nếu phiên IdP còn hiệu lực.

Với nhiều frontend hoặc SPA, quyết định rõ ai sở hữu phiên: (a) BFF giữ token và browser chỉ có session cookie, hay (b) SPA dùng OAuth public client + PKCE và quản lý token/refresh theo khả năng IdP. Phương án (a) thường dễ kiểm soát token hơn khi có backend; không đặt client secret vào bundle frontend. Tránh mặc định tắt CSRF chỉ vì ứng dụng dùng OIDC; CSRF của cookie session và state của redirect giải quyết các vấn đề liên quan nhưng không hoàn toàn trùng nhau.

**SAML** phù hợp nếu web phải kết nối trực tiếp với IdP enterprise vốn chỉ cấp SAML hoặc quy định mua bán yêu cầu SAML. Không chuyển sang SAML chỉ vì đối tượng là “doanh nghiệp”: giao thức cần theo khả năng, ràng buộc và chi phí vận hành thực tế.

### 4.2. Web nội bộ, Active Directory và máy Windows

- **Chỉ thiết bị Windows domain-joined, browser do IT quản lý, intranet ổn định:** Kerberos/SPNEGO là ứng viên tốt. Chuẩn bị SPN/keytab, DNS chính xác, Kerberos realm trust, NTP, HTTPS và cấu hình browser cho tên miền tin cậy. Kiểm tra trên máy domain-joined và máy không thuộc domain để biết hành vi dự phòng.
- **Nhân viên làm từ xa, macOS/Linux, mobile, nhiều domain/IdP:** dùng OIDC qua IdP doanh nghiệp. IdP có thể tận dụng Kerberos phía trong mạng để cho nhân viên SSO; ứng dụng chỉ làm OIDC RP. Cách này tách logic web khỏi KDC/keytab và hỗ trợ MFA/conditional access thống nhất.
- **Ứng dụng nội bộ cũ đang dùng LDAP Bind:** LDAP xác thực mật khẩu trực tiếp không tạo web SSO xuyên ứng dụng. Có thể chuyển qua IdP liên kết AD rồi dùng OIDC/SAML; duy trì LDAP lookup nhóm chỉ khi thật cần và bảo đảm kết nối bảo mật.

Ví dụ: cổng quản lý kho trước đây chỉ chạy Windows LAN, nay cần truy cập qua điện thoại khi đi công tác. Đầu vào đã thay đổi; nên cân nhắc IdP + OIDC thay vì cố mở rộng SPNEGO trực tiếp đến mọi client.

### 4.3. Portal cho đối tác ngoài tổ chức (B2B)

**Bắt đầu bằng hợp đồng giao thức của từng đối tác, không áp một mô hình cứng cho tất cả.**

- Nếu đối tác chỉ có **SAML**: trao đổi SP entity ID, ACS URL, metadata, IdP entity ID, SSO URL, chứng chỉ xác minh; thống nhất yêu cầu ký AuthnRequest, mã hóa assertion, NameID và thuộc tính được phát hành. Kiểm thử IdP-initiated (nếu cho phép) và SP-initiated theo chính sách chống replay/mix-up.
- Nếu hai bên có **OIDC**: dùng issuer và client registration riêng theo đối tác, đăng ký redirect URI cố định, định nghĩa scopes/claims, ký/rotate keys qua JWKS và quản lý client credentials an toàn. Không chỉ lấy domain email để quyết định tin IdP nào.
- Trong mô hình **nhiều tenant**, định danh người dùng phải có cả **tenant/issuer và subject ổn định**; ánh xạ vào tổ chức nội bộ trước khi gán quyền. Phải ngăn một tài khoản đối tác A đăng nhập vào không gian của B khi claim tên/email trùng nhau.
- Thỏa thuận các khía cạnh ngoài login: JIT provisioning so với SCIM, khóa tài khoản khi nghỉ việc, thu hồi phiên, thay đổi thuộc tính/nhóm, SLA sự cố, quyền truy cập mặc định, rotation chứng chỉ/secret, người liên hệ kỹ thuật.

**Identity broker** phù hợp khi có hàng chục đối tác khác giao thức: mỗi đối tác giao tiếp với broker theo OIDC/SAML riêng, còn ứng dụng Spring dùng một giao thức thống nhất (thường OIDC) với broker. Broker là điểm tập trung rủi ro và cần kiểm chứng ánh xạ tenant/identity, chính sách MFA và độ tin cậy của từng nguồn danh tính.

### 4.4. API và giao tiếp dịch vụ

API dùng access token đúng đối tượng nhận (`aud`) và scope/role; dịch vụ không đăng nhập tương tác bằng SAML browser redirect. Spring Security **Resource Server** hỗ trợ JWT Bearer; cấu hình issuer chưa đủ để khẳng định token được cấp cho API, cần ràng buộc audience kỳ vọng khi hệ thống yêu cầu. Với daemon/job, xét OAuth Client Credentials hoặc workload identity. Khi API xử lý thay người dùng, thiết kế delegated authorization một cách tường minh, không lấy ID Token làm access token.

## 5. Áp dụng trong Spring Security (Servlet / Java 17+)

Những đoạn cấu hình dưới đây là **mảnh cấu hình tích hợp vào dự án Spring Boot** đã có dependency, controller và IdP thực, **không phải chương trình Java độc lập chạy bằng `javac` hoặc có stdout cố định**. Các URI dùng miền ví dụ; phải thay bằng cấu hình do IdP cấp. Nếu dùng WebFlux, phải chọn DSL reactive tương ứng (`SecurityWebFilterChain`), không chép `SecurityFilterChain` servlet.

### 5.1. OIDC login – Spring MVC

Thêm dependency `spring-boot-starter-security` và `spring-boot-starter-oauth2-client` vào dự án Spring Boot tương thích. Đăng ký client ở OP, ví dụ redirect URI `https://app.example.com/login/oauth2/code/corp`. Mẫu `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-idp
            client-id: ${SSO_CLIENT_ID}
            client-secret: ${SSO_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          corp-idp:
            issuer-uri: https://idp.example.com/realms/company
```

Scope `openid` khiến Spring Security xử lý login theo OIDC khi OP hỗ trợ các endpoint tương ứng. Client secret được cấp từ biến môi trường/secret manager, không commit vào mã nguồn. Cấu hình Java:

```java
package example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

Sau khi tích hợp, truy cập một trang được bảo vệ sẽ dẫn đến IdP; endpoint khởi tạo đăng nhập mặc định là `/oauth2/authorization/corp` và callback là `/login/oauth2/code/corp`. Code cấu hình chưa ánh xạ vai trò: chỉ coi người dùng là authenticated; việc vào trang nghiệp vụ phải có kiểm tra quyền từ dữ liệu tin cậy. Khi có reverse proxy, cấu hình forwarded headers/HTTPS đúng để redirect URI không bị dựng sai host/scheme. Không mong chờ chạy được chỉ bằng `javac SecurityConfig.java` vì cần classpath của Spring Boot.

### 5.2. SAML 2.0 login – Spring MVC

Thêm `spring-boot-starter-security` và `org.springframework.security:spring-security-saml2-service-provider` phù hợp với BOM của dự án. Giả sử đối tác cung cấp issuer, SSO URL và chứng chỉ công khai của IdP:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              entity-id: https://idp.partner.example/saml
              verification:
                credentials:
                  - certificate-location: classpath:partner-a-idp.crt
              singlesignon:
                url: https://idp.partner.example/saml/sso
                sign-request: false
```

`sign-request: false` **chỉ là giá trị minh họa cho IdP không yêu cầu ký AuthnRequest**; nếu chính sách đối tác yêu cầu ký, cấu hình private key/chứng chỉ ký của SP và bật ký theo đúng metadata/hợp đồng. Không tắt xác minh chữ ký SAMLResponse. Bộ Java Config cho ứng dụng **chọn SAML thay OIDC**:

```java
package example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
```

Cấu hình này là **phương án thay thế**, không đặt cùng lớp `SecurityConfig` với mẫu OIDC khi thử độc lập. Đường dẫn khởi tạo thông dụng là `/saml2/authenticate/partner-a`, ACS mặc định `/login/saml2/sso/partner-a`; `/saml2/metadata/partner-a` công bố metadata SP khi bật `saml2Metadata`. Phải đăng ký đúng ACS/entity ID với IdP và xác minh cả luồng SP-initiated, tình huống sai chữ ký và thời gian assertion hết hạn. Khi tích hợp nhiều đối tác, dùng nhiều registration có định danh rõ ràng, không tái sử dụng cấu hình xác minh của đối tác A cho B.

### 5.3. Resource Server cho API sử dụng JWT

Nếu phần API là ứng dụng/tuyến lọc riêng, thêm `spring-boot-starter-oauth2-resource-server` và đặt:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/company
          audiences: https://api.example.com
```

Bảo vệ API bằng `.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` trong `SecurityFilterChain` của API. Mẫu cấu hình JWT này phục vụ **kiểm chứng access token khi gọi API**, không tự tạo màn hình SSO cho người dùng. Các bean/filter chain và matcher phải được thiết kế đúng nếu vừa có web cookie session vừa có API Bearer. Đừng cho rằng cùng issuer thì mọi token đều có quyền gọi mọi API.

## 6. Các kiểm soát bắt buộc dù chọn giao thức nào

**Ranh giới tin cậy và định danh**
1. Xác định và giới hạn issuer/IdP nào được tin cho từng ứng dụng hoặc tenant; không tự động chấp nhận issuer bất kỳ từ request.
2. Ánh xạ danh tính theo khóa ổn định có namespace (OIDC `iss+sub`; SAML `issuer+NameID` nếu NameID có định dạng/độ bền phù hợp), gắn tenant nội bộ; chỉ dùng email làm thuộc tính liên hệ sau khi chính sách xác minh thỏa đáng.
3. Tách vai trò nghiệp vụ khỏi việc login. Kiểm tra least privilege, tenant isolation và chính sách gán nhóm/role; không mặc định tin mọi claim role đối tác gửi.

**An toàn trao đổi**
4. Luôn dùng HTTPS; cấu hình redirect URI/ACS và reverse proxy chính xác. OIDC kiểm chứng chữ ký, issuer, audience, thời hạn, state/PKCE/nonce theo luồng. SAML kiểm chứng chữ ký, issuer, audience, recipient, destination, conditions và chống replay.
5. Bảo vệ client secret, private key, keytab trong secret manager/quyền file; xoay vòng có giai đoạn chồng lấp. OIDC dùng JWKS/metadata có kiểm soát; SAML cập nhật chứng chỉ theo lịch và kiểm thử cả ký lẫn mã hóa.
6. Bật MFA/chính sách rủi ro tại IdP theo mức bảo đảm yêu cầu. SSO chỉ tái sử dụng trạng thái xác thực; nếu tác vụ nhạy cảm yêu cầu xác thực lại, phải thiết kế re-authentication/step-up thích hợp.

**Phiên và vận hành**
7. Thiết lập session idle/absolute timeout, cookie Secure/HttpOnly/SameSite, CSRF cho luồng dựa trên cookie, hạn mức và thu hồi quyền. Đăng xuất ứng dụng, đăng xuất IdP và single logout liên ứng dụng là ba hành vi có thể khác nhau; kiểm chứng từng trường hợp.
8. Có kế hoạch lỗi IdP/AD hoặc mạng, thời gian chờ, circuit breaker ở các điểm phù hợp; không chuyển thành “cho phép truy cập khi IdP lỗi”. Đồng bộ giờ máy chủ vì assertion/token có thời hạn.
9. Log sự kiện đăng nhập/thất bại với correlation ID, tenant/issuer, mã lỗi đã lọc; không log nguyên token, SAML assertion, mật khẩu, private key hay keytab. Giám sát tỉ lệ lỗi redirect, chữ ký, lệch giờ và thay đổi metadata.

## 7. Checklist triển khai và kiểm thử quyết định

| Câu hỏi cần trả lời trước khi chốt | Bằng chứng/tiêu chí chấp nhận |
| --- | --- |
| Người dùng truy cập bằng trình duyệt, SPA, mobile hay server? Có máy domain-joined không? | Danh sách client, môi trường truy cập, giới hạn browser/VPN |
| Ai là IdP và giao thức nào được công bố/hợp đồng yêu cầu? | OIDC discovery hoặc SAML metadata, owner kỹ thuật và quy trình thay khóa |
| Kết nối là cùng doanh nghiệp hay liên kết B2B nhiều tenant? | Mapping issuer → tenant, danh tính ổn định, ranh giới quyền |
| Đăng nhập, API authorization, cấp phát tài khoản và logout cần gì? | Luồng và giao thức được chỉ rõ cho từng phần; không gộp OAuth, OIDC, SCIM |
| MFA, phiên, mật khẩu, secret/certificate và chính sách thu hồi do ai quản lý? | Trách nhiệm của IdP, ứng dụng và đội vận hành được ghi rõ |
| Có kiểm thử tấn công và trường hợp ngoại lệ chưa? | Sai issuer/audience, hết hạn, replay, sai chữ ký, tenant mismatch, thay chứng chỉ, IdP outage, user bị vô hiệu hóa đều bị chặn/phản ứng đúng |

**Ma trận kiểm thử tối thiểu** sau tích hợp:
- Người dùng hợp lệ vào đúng ứng dụng/tenant → xác thực thành công, quyền chỉ đủ phạm vi.
- Người dùng chưa xác thực → được chuyển đến IdP đúng, callback hợp lệ; sau login truy cập tài nguyên ban đầu.
- Code/token/assertion sai issuer, audience, chữ ký hoặc quá hạn → bị từ chối, không tạo session mới.
- Đối tác A cố dùng assertion/token để truy cập tenant B → bị chặn dù email giống nhau.
- Thay khóa/chứng chỉ IdP theo quy trình → hệ thống tiếp nhận khóa mới có kiểm soát, không bỏ qua xác minh.
- Người dùng bị khóa, phiên hết hạn hoặc yêu cầu logout → hành vi đúng thiết kế, không hiểu nhầm logout cục bộ là logout tất cả ứng dụng.
- Với intranet SPNEGO: thử máy join domain và không join domain, hostname alias, SPN sai, lệch giờ; dự phòng chỉ dùng phương thức đã được phê duyệt.
- Với SPA: kiểm tra redirect/code PKCE, refresh token/cookie, CSRF và khả năng rò token trong URL, storage hoặc log.

## 8. Ba ví dụ quyết định thực tế

**Tình huống A – Cổng bán hàng web mới có Spring Boot + React, nhân viên và khách dùng nhiều thiết bị:** Chọn OIDC Authorization Code; cân nhắc BFF để browser chỉ giữ cookie phiên. IdP xử lý MFA và đăng nhập; backend giữ phiên, API dùng access token đúng audience. Không chọn Kerberos vì khách/máy cá nhân ngoài domain; SAML chỉ bổ sung nếu có IdP đối tác yêu cầu.

**Tình huống B – Công cụ chấm công LAN cho nhân viên Windows domain-joined:** Nếu thiết bị, hostname, browser và AD do IT kiểm soát chặt, Kerberos/SPNEGO giúp dùng ticket Windows hiện có. Nếu roadmap có mobile/Internet, chọn OIDC qua IdP kết nối AD để tránh gắn chặt web vào cơ chế intranet. Giữ kiểm tra quyền theo ứng dụng dù SSO không hỏi lại mật khẩu.

**Tình huống C – Portal cho 20 nhà cung cấp với IdP không đồng nhất:** Hợp đồng SAML/OIDC riêng theo đối tác; ưu tiên identity broker nếu giảm được số cấu hình giao thức trong ứng dụng. Ánh xạ mỗi issuer/tenant tới tổ chức, chính sách quyền và khóa tài khoản riêng; thử tấn công cross-tenant, certificate rotation và JIT/SCIM. Không coi email hoặc tên miền người dùng là đủ bằng chứng để ghép tài khoản.

## 9. Tài liệu chuẩn để đối chiếu triển khai

- [Spring Security – OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): client registration, callback và `oauth2Login`.
- [Spring Security – SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): asserting party, relying party, ACS, xác minh SAML Response.
- [Spring Security – Kerberos extension](https://docs.spring.io/spring-security-kerberos/reference/index.html): SPNEGO/Kerberos và các mẫu cấu hình.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer, audience, JWT validation.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) và [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700.html): yêu cầu bảo mật của luồng đăng nhập/ủy quyền.

**Ghi nhớ khi chọn:** web đa nền tảng thường dùng **OIDC**, intranet Windows đã quản lý tập trung có thể dùng **Kerberos/SPNEGO**, B2B theo chuẩn mà IdP đối tác thực sự cung cấp (**SAML hoặc OIDC**). Mọi phương án đều cần thiết kế phân quyền, định danh liên tenant, lifecycle tài khoản và bảo vệ session riêng.