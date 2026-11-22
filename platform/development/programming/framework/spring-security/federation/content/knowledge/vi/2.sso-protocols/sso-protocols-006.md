# Phân biệt Service Provider, Relying Party, CAS service và Resource Server

> **Ngữ cảnh:** Giao thức đăng nhập một lần (SSO) và federation trong hệ sinh thái Spring Security. Bốn tên gọi dưới đây mô tả **vai trò của ứng dụng trong một giao thức cụ thể**, không phải bốn loại máy chủ bắt buộc phải triển khai riêng.

## 1. Bức tranh tổng quát

Khi một ứng dụng sử dụng hệ thống danh tính trung tâm, cần xác định **ai xác thực người dùng**, **ứng dụng nhận bằng chứng gì**, **bằng chứng dành cho ai** và **ứng dụng làm gì sau khi kiểm tra bằng chứng**. Các chuẩn dùng những thuật ngữ khác nhau:

| Vai trò | Giao thức/ngữ cảnh thường gặp | Bên phát hành hoặc xác nhận | Bằng chứng ứng dụng tiếp nhận | Mục đích chính |
| --- | --- | --- | --- | --- |
| **Service Provider (SP)** | SAML 2.0 Web SSO | Identity Provider (IdP, còn gọi *Asserting Party*) | `SAML Response` chứa `Assertion` | Đăng nhập người dùng vào ứng dụng dựa trên khẳng định danh tính từ IdP |
| **Relying Party (RP)** | OpenID Connect (OIDC); thuật ngữ cũng được dùng trong SAML | OpenID Provider (OP) | `ID Token` và kết quả luồng OIDC | Xác thực danh tính người dùng để tạo phiên đăng nhập ứng dụng |
| **CAS service** | Giao thức Central Authentication Service (CAS) | CAS server | `Service Ticket` (`ST`), cần xác minh với CAS server | Đăng nhập người dùng vào ứng dụng đã tích hợp CAS |
| **Resource Server (RS)** | OAuth 2.0 | Authorization Server (AS) cấp `Access Token` | `Access Token`, thường qua HTTP `Authorization: Bearer ...` | Bảo vệ dữ liệu/API và quyết định có cho phép truy cập tài nguyên |

**Điểm quan trọng về từ ngữ:** `Relying Party` không dành riêng cho OIDC. Trong tài liệu Spring Security SAML, *Service Provider* và *Relying Party* là hai tên có thể dùng cho cùng vai trò SAML; vì vậy class `RelyingPartyRegistration` được dùng để cấu hình **SAML Service Provider**. Khi so sánh các giao thức, người ta thường gọi ứng dụng **SAML là SP** và ứng dụng **OIDC là RP** để dễ phân biệt; đó là quy ước trình bày, không phải ranh giới tuyệt đối của thuật ngữ.

## 2. Service Provider: bên dùng SAML Assertion để đăng nhập

Trong **SAML 2.0**, SP là ứng dụng cần biết người đang truy cập đã được xác thực. SP đặt niềm tin vào IdP theo cấu hình trước: `entityID`, metadata, chứng thư ký số, endpoint và chính sách giao thức.

Luồng **SP-initiated Web SSO** điển hình:

1. Người dùng vào trang cần đăng nhập trên SP.
2. SP tạo `AuthnRequest`, chuyển trình duyệt tới SAML IdP; yêu cầu có thể được ký tùy cấu hình và yêu cầu của IdP.
3. IdP xác thực người dùng hoặc dùng phiên SSO đang tồn tại, rồi phát `SAML Response` có `Assertion`.
4. Trình duyệt gửi response đến **Assertion Consumer Service (ACS)** của SP, thường qua HTTP POST.
5. SP xác minh chữ ký và bên phát hành, điều kiện thời gian, `AudienceRestriction`, `Recipient`, `Destination`, `InResponseTo` và các ràng buộc áp dụng cho luồng đã dùng; đồng thời chống phát lại.
6. Khi hợp lệ, SP thiết lập `Authentication`/phiên của chính ứng dụng và thực hiện **phân quyền nội bộ**.

`SAML Assertion` là khẳng định danh tính/thuộc tính có ngữ cảnh và đối tượng nhận xác định; nó **không mặc nhiên là OAuth Access Token** cho mọi REST API. Đừng nhầm SP với IdP: **IdP xác thực và phát assertion; SP tiếp nhận và kiểm tra**.

**Dấu hiệu nhận diện trong Spring Security:** dependency `spring-security-saml2-service-provider`, cấu hình `spring.security.saml2.relyingparty.registration`, `RelyingPartyRegistrationRepository` và `http.saml2Login(...)`. Endpoint ACS thường có dạng `/login/saml2/sso/{registrationId}` (có thể tùy chỉnh).

## 3. Relying Party: ứng dụng đăng nhập qua OpenID Connect

Trong **OpenID Connect**, RP là **OAuth 2.0 client sử dụng thêm lớp xác thực danh tính OIDC**. OP xác thực người dùng; RP dựa trên kết quả đó để biết người dùng là ai. RP thường là website hoặc backend-for-frontend có phiên trình duyệt.

Luồng **OIDC Authorization Code** tiêu biểu:

1. Người dùng chọn đăng nhập; RP chuyển trình duyệt tới authorization endpoint của OP với `client_id`, `redirect_uri`, `scope` chứa `openid`, `state` và các tham số thích hợp (ví dụ `nonce`; dùng PKCE theo chính sách client).
2. OP xác thực người dùng và chuyển trình duyệt về `redirect_uri` kèm **authorization code**.
3. RP kiểm tra `state` và đổi code tại token endpoint của OP, dùng cơ chế xác thực client/PKCE phù hợp.
4. RP nhận **ID Token** (thường là JWT) và có thể nhận **Access Token**, xác minh chữ ký, `iss`, `aud`, `exp`, `nonce` khi được sử dụng và các điều kiện khác theo OIDC.
5. RP xác lập danh tính người dùng (thường dựa trên cặp `iss` + `sub`), tạo phiên ứng dụng. Nếu cần thông tin bổ sung, RP có thể dùng Access Token gọi **UserInfo Endpoint** theo đặc tả và chính sách OP.

**Phân biệt hai token cùng nhận:** **ID Token** được phát cho **RP** nhằm thông báo kết quả xác thực; **Access Token** được cấp để client gọi **Resource Server** tương ứng. Không lấy ID Token gửi như Bearer token tới API chỉ vì cả hai đều có thể có định dạng JWT. Cũng không coi `email` là khóa định danh bất biến giữa các hệ thống.

Trong Spring Security, `oauth2Login(...)` cung cấp đăng nhập dựa trên OAuth 2.0/OIDC; để là **OIDC RP**, registration cần dùng OIDC provider và scope `openid`. Các thành phần thường thấy: `ClientRegistrationRepository`, `OAuth2AuthorizedClient`, `OidcUser`, `OidcIdToken` và callback mặc định `/login/oauth2/code/{registrationId}`.

**Không đánh đồng:** OAuth 2.0 bản thân định nghĩa **ủy quyền truy cập tài nguyên**, không tự chuẩn hóa tuyên bố danh tính của người dùng như OIDC. Một OAuth client không yêu cầu `openid` không nhất thiết là OIDC RP.

## 4. CAS service: ứng dụng nhận Service Ticket từ CAS server

Trong giao thức **CAS**, *CAS service* nghĩa là **ứng dụng được bảo vệ bởi CAS**, sử dụng CAS client hoặc cơ chế tích hợp tương đương. `service` cũng là tham số định danh URL/điểm nhận đăng nhập của ứng dụng. Nó **khác CAS server**: CAS server thực hiện xác thực trung tâm và cấp ticket.

Luồng CAS cơ bản:

1. Người dùng truy cập ứng dụng; CAS service thấy chưa có phiên cục bộ.
2. Ứng dụng chuyển trình duyệt đến `https://sso.example.org/cas/login?service=<URL-ứng-dụng>` (URL của `service` phải được encode chính xác).
3. CAS server xác thực người dùng hoặc nhận diện phiên SSO của mình qua **Ticket Granting Cookie (TGC)**, liên hệ với **Ticket Granting Ticket (TGT)**.
4. CAS server chuyển trình duyệt về đúng `service`, kèm query parameter `ticket=ST-...`.
5. Backend CAS service gửi `service` **và** `ticket` đến endpoint xác minh của CAS server, như `/serviceValidate` hoặc `/p3/serviceValidate`. CAS server trả kết quả và danh tính/thuộc tính nếu hợp lệ.
6. Ứng dụng lập phiên riêng, áp dụng quyền truy cập riêng. **Service Ticket dùng một lần, gắn với service cụ thể**; không được xem như access token có thể dùng nhiều lần ở các API khác nhau.

Ví dụ minh họa giao tiếp (URL trong ví dụ là giả định, `ST-xyz` không phải ticket thật):

```http
GET /cas/login?service=https%3A%2F%2Flegacy.example.org%2Flogin%2Fcas HTTP/1.1
Host: sso.example.org

# Sau khi xác thực, trình duyệt được chuyển về:
# https://legacy.example.org/login/cas?ticket=ST-xyz

GET /cas/serviceValidate?service=https%3A%2F%2Flegacy.example.org%2Flogin%2Fcas&ticket=ST-xyz HTTP/1.1
Host: sso.example.org
```

Phần thứ ba là **backend của CAS service gọi tới CAS server**, không phải API mà người dùng cuối tự xác thực bằng ST. Khi xác minh thất bại, service phải từ chối đăng nhập; không tin `ticket` chỉ vì nó xuất hiện trên URL.

Trong hệ Spring, CAS có thể được tích hợp qua CAS client và các thành phần phù hợp với phiên bản dự án. Hãy kiểm tra khả năng tương thích của thư viện CAS/Spring Security thực tế; không dùng cấu hình `oauth2Login` hoặc `saml2Login` rồi mặc định gọi đó là CAS protocol.

## 5. Resource Server: API kiểm soát truy cập bằng OAuth Access Token

Trong **OAuth 2.0**, Resource Server là máy chủ lưu/tiếp nhận yêu cầu tới **tài nguyên được bảo vệ** (ví dụ `GET /api/orders`). Authorization Server cấp Access Token cho client, còn Resource Server **kiểm tra Access Token** trước khi cấp dữ liệu. RS không cần tự thực hiện giao diện đăng nhập hay trực tiếp yêu cầu mật khẩu người dùng.

Luồng điển hình:

1. Client có được Access Token từ Authorization Server bằng một grant phù hợp.
2. Client gọi API: `Authorization: Bearer <access-token>`.
3. RS kiểm tra token: với JWT, thường xác thực chữ ký qua khóa công khai/JWKS, `iss`, thời hạn `exp`/`nbf` và **`aud` dành cho chính API**; với opaque token, có thể hỏi endpoint **introspection** của AS.
4. RS kiểm tra scope/quyền/ngữ cảnh nghiệp vụ của endpoint, ví dụ `orders.read`; token hợp lệ **chưa có nghĩa** được phép mọi thao tác.
5. RS trả tài nguyên hoặc HTTP `401 Unauthorized` khi chưa xác thực hợp lệ, `403 Forbidden` khi đã xác thực nhưng không đủ quyền (tùy cơ chế xử lý).

Ví dụ request:

```http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...
```

**RS không phải Authorization Server:** AS phát token và định nghĩa quyền cấp cho client; RS tiếp nhận token và bảo vệ tài nguyên. RS có thể không phải IdP/OP. **JWT là định dạng token, không phải một giao thức đăng nhập**; phải xác định đó là ID Token hay Access Token và kiểm tra đúng `aud`/mục đích. Khi token bị ràng buộc với một API khác, RS phải từ chối dù chữ ký hợp lệ.

Trong Spring Security, cặp cấu hình thường gặp là `http.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` với JWT, hoặc cơ chế opaque-token introspection; authority mặc định từ scope thường mang tiền tố `SCOPE_`. Khi cần bảo vệ API, khai báo issuer, audience và quy tắc ủy quyền cụ thể.

## 6. So sánh theo luồng tin cậy

```text
SAML:
Browser -> SAML SP -> IdP -> (SAML Response qua browser) -> SP/ACS
                                                       -> phiên SP

OIDC:
Browser -> OIDC RP -> OP -> (authorization code qua browser) -> RP
RP -> OP/token endpoint -> ID Token (+ Access Token) -> phiên RP

CAS:
Browser -> CAS service -> CAS server -> (ticket=ST qua browser) -> service
CAS service -> CAS /serviceValidate(service, ST) -> phiên service

OAuth 2.0 API:
Client -> Authorization Server -> Access Token
Client -> Resource Server (Authorization: Bearer Access Token) -> API response
```

Có thể nhớ theo câu hỏi **“bằng chứng nào và ai phải kiểm tra?”**: SP kiểm tra **SAML Assertion** theo tin cậy SAML; OIDC RP kiểm tra **ID Token** từ OP; CAS service **đổi/kiểm tra Service Ticket** với CAS server; OAuth Resource Server kiểm tra **Access Token** dành cho tài nguyên của mình. Cả bốn vẫn phải thực hiện phân quyền theo nhu cầu ứng dụng.

## 7. Cùng một hệ thống có thể mang nhiều vai trò

Giả sử một doanh nghiệp có:

- **Cổng nhân sự dùng SAML:** cổng đóng vai trò **SP**, nhà cung cấp danh tính doanh nghiệp là **IdP**.
- **Trang khách hàng dùng OIDC:** trang đóng vai trò **RP**; nhà cung cấp danh tính là **OP**. Trang có thể đồng thời là **OAuth client** khi gọi API.
- **Ứng dụng cũ dùng CAS:** ứng dụng là **CAS service**, CAS server phát và xác minh Service Ticket.
- **API đơn hàng:** backend là **OAuth Resource Server**, chấp nhận Access Token có audience/scope phù hợp.

Một ứng dụng Spring Boot hoàn toàn có thể vừa là **OIDC RP** cho phần web đăng nhập, vừa là **Resource Server** cho `/api/**`. Hai vai trò phục vụ **hai loại request** và phải dùng cơ chế xác thực thích hợp. Ví dụ cấu hình minh họa Java 17+ dưới đây dành cho **một dự án Spring Boot có đủ dependency Web, Spring Security, OAuth2 Client, OAuth2 Resource Server và JOSE**; đây là một class cấu hình trong ứng dụng, **không phải chương trình Java độc lập chạy bằng `javac` thuần**.

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityRoleConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Cấu hình Spring Boot tương ứng (các URI là ví dụ; biến môi trường phải được cấp khi chạy):

```yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corp:
            issuer-uri: https://login.example.org/realms/corp
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope: [openid, profile, email]
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/corp
          audiences: https://api.example.org/orders
```

**Cách đọc ví dụ:** Chuỗi filter có `@Order(1)` ưu tiên `/api/**`, đọc **Bearer Access Token** và yêu cầu quyền `SCOPE_orders.read` cho GET đơn hàng. Chuỗi web dùng `oauth2Login` cho phiên trình duyệt và, vì đăng ký chứa `openid`, đóng vai trò **OIDC RP**. `issuer-uri` trùng nhau không khiến **ID Token của web** trở thành Access Token cho API; API vẫn phải có `aud` phù hợp. Việc tắt CSRF chỉ áp dụng cho chuỗi API stateless dùng Bearer token; web đăng nhập bằng cookie vẫn cần bảo vệ CSRF theo cấu hình phù hợp.

Nếu triển khai **SAML SP** thay OIDC RP cho trang web, cấu hình tập trung ở `RelyingPartyRegistration` và `saml2Login`; đó là **một giao thức đăng nhập khác**, không thể thay bằng cách đổi tên token. Nếu dùng **CAS service**, cần kiểm tra CAS ST với CAS server theo protocol CAS thay vì xử lý như JWT/OAuth bearer.

## 8. Nhầm lẫn phổ biến và cách tự kiểm tra

| Nhận định dễ sai | Cách hiểu chính xác |
| --- | --- |
| “Relying Party chắc chắn là OIDC, SP chắc chắn không phải RP.” | RP cũng là thuật ngữ cho SP trong ngữ cảnh SAML; Spring SAML có `RelyingPartyRegistration`. Cần nhìn vào giao thức và loại bằng chứng. |
| “CAS service là CAS server.” | CAS **server** xác thực và cấp ticket; CAS **service** là ứng dụng được bảo vệ, nhận ST rồi gọi CAS server xác minh. |
| “Resource Server xác thực người dùng bằng màn hình đăng nhập.” | RS thường xác thực **request API bằng Access Token**; màn hình đăng nhập thường thuộc client/RP, IdP/OP hoặc CAS server. |
| “Có JWT thì dùng chung cho đăng nhập và gọi API.” | Phải biết JWT là **ID Token** hay **Access Token**, đúng issuer, audience, scope và mục đích sử dụng. |
| “Access Token hợp lệ là truy cập được mọi endpoint.” | RS cần phân quyền theo scope/authority và chính sách nghiệp vụ; token còn hạn không đồng nghĩa đủ quyền. |
| “SSO nghĩa là mọi ứng dụng dùng chung HTTP session.” | SSO chia sẻ trạng thái đăng nhập ở bên cung cấp danh tính; mỗi SP/RP/CAS service thường giữ **phiên ứng dụng riêng**. |
| “SAML assertion/CAS ST có thể đưa vào Bearer header để gọi OAuth API.” | Không có sự tương đương mặc định; nếu cần, dùng cơ chế token exchange/gateway được thiết kế và kiểm soát rõ ràng. |

**Checklist khi thiết kế hoặc đọc code:**

1. Xác định **giao thức** đang chạy: SAML, OIDC, CAS hay OAuth bảo vệ API.
2. Xác định **ai cấp/chứng thực** bằng chứng và **ứng dụng nào là người nhận dự kiến**.
3. Xác định **loại artifact**: SAML Assertion, OIDC ID Token, CAS ST hay OAuth Access Token.
4. Kiểm tra **ràng buộc bảo mật** tương ứng: chữ ký, issuer, audience/service/recipient, thời gian, state/nonce hoặc chống replay, tùy giao thức.
5. Xác định ứng dụng sẽ tạo **phiên trình duyệt** hay trả lời **request API**, rồi cấu hình phân quyền riêng.

## 9. Tài liệu đối chiếu

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — đối chiếu thuật ngữ SP/RP và luồng SAML.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — RP, OP, ID Token và xác minh.
- [Apereo CAS — CAS Protocol](https://github.com/apereo/cas/blob/master/docs/cas-server-documentation/protocol/CAS-Protocol.md) — CAS service, server, TGT/TGC/ST.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749) — các vai trò client, Authorization Server và Resource Server.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — `issuer-uri`, `aud` và xác thực access token.
