# Phân biệt đăng xuất ứng dụng, đăng xuất OIDC và đăng xuất IdP phía sau môi giới

## 1. Mục tiêu và bối cảnh

Trong hệ thống **Spring Security – federation**, một ứng dụng Java có thể đăng nhập người dùng qua OpenID Connect (OIDC) nhưng **không kết nối trực tiếp tới hệ thống định danh gốc**. Thay vào đó có một **identity broker** đứng giữa ứng dụng và Identity Provider (IdP) upstream. Ví dụ ứng dụng Spring Boot dùng OIDC đăng nhập với Keycloak, còn Keycloak dùng OIDC, SAML 2.0 hoặc một phương thức federation khác để xác thực người dùng tại IdP doanh nghiệp.

Khi người dùng bấm **Đăng xuất**, có ít nhất ba đối tượng cần phân biệt:

1. **Phiên ứng dụng** — session/cookie và SecurityContext tại Spring Boot Relying Party (RP).
2. **Phiên của OIDC Provider/môi giới** — SSO session của OpenID Provider (OP) mà ứng dụng trực tiếp tin, ví dụ một realm Keycloak.
3. **Phiên ở IdP upstream** — phiên đăng nhập tại hệ thống định danh nằm phía sau broker, ví dụ IdP OIDC/SAML của đối tác.

Ngoài ba phiên, có một trục khác không thể bỏ qua: **OAuth access token/refresh token** và các phiên **ứng dụng RP khác** cùng đăng nhập qua broker. Kết thúc một session trên trình duyệt **không tự bảo đảm** mọi access token đã được thu hồi hoặc mọi RP khác đã xóa session.

Bài học thuộc nhóm **OIDC và môi giới**. Sau khi học, bạn cần:

- Phân biệt **local application logout**, **OIDC RP-Initiated Logout**, **OIDC OP-initiated front-channel/back-channel logout**, và **upstream IdP logout**.
- Giải thích được vì sao một người bấm logout ở app nhưng **lần đăng nhập tiếp theo vẫn SSO không cần nhập mật khẩu**.
- Cấu hình Spring Security sử dụng **OidcClientInitiatedLogoutSuccessHandler** và **end_session_endpoint** đúng nơi.
- Hiểu broker là **OP đối với ứng dụng**, nhưng là **RP/SP đối với IdP upstream**; do đó logout cần được nối qua **hai quan hệ tin cậy khác nhau**.
- Phân biệt protocol logout với **token revocation**, expiration, SAML Single Logout và chính sách đăng xuất toàn bộ thiết bị.
- Thiết kế kiểm chứng **state, id_token_hint, post_logout_redirect_uri, logout_token, iss, aud, sid, sub**, và chống replay/cross-session logout.
- Xây dựng test matrix, câu thông báo UI và runbook vận hành minh bạch về phạm vi đăng xuất.

**Nguyên tắc gốc:** chữ “logout” không có một nghĩa chung xuyên suốt mọi hệ thống. Một bước logout chỉ tác động đến **những phiên/tokens/đối tác mà thành phần đó có quyền và có giao thức thông báo thực sự được cấu hình, hỗ trợ và thực thi**.

## 2. Sơ đồ ba tầng và quan hệ vai trò

~~~text
                   Browser / End User
                           |
                           v
                  +-------------------+
                  | Ứng dụng Spring   |
                  | Boot Web (RP)     |
                  | APP session A     |
                  +-------------------+
                           |
                           | OIDC Authorization Code
                           | issuer = broker OP
                           v
                  +-------------------+
                  | Identity Broker   |
                  | Keycloak / OP     |
                  | Broker session B  |
                  +-------------------+
                           |
                           | OIDC, SAML, hoặc
                           | protocol federation khác
                           v
                  +-------------------+
                  | IdP upstream      |
                  | Org/Partner IdP   |
                  | Upstream session C|
                  +-------------------+

              Broker OP còn phục vụ:
                 RP 2 / RP 3 / mobile / API
                 (mỗi bên có session hoặc tokens riêng)
~~~

Hai quan hệ có **vai trò đổi chiều**:

| Quan hệ | Bên yêu cầu xác thực | Bên phát identity | Ai được app tin? |
| --- | --- | --- | --- |
| **Spring app ↔ broker** | Spring app là **OIDC RP/client** | Broker là **OIDC OP** | App tin **issuer/JWKS của broker**, không tự tin token upstream |
| **Broker ↔ IdP upstream OIDC** | Broker là **OIDC RP/client** | Upstream là **OIDC OP** | Broker kiểm upstream issuer/JWKS |
| **Broker ↔ IdP upstream SAML** | Broker là **SAML SP** | Upstream là **SAML IdP** | Broker kiểm upstream SAML signature/metadata |

Định danh người dùng, session ID và tokens **không tự đồng nhất** giữa ba tầng. Một ID Token được cấp cho app bởi broker có **iss=broker**, **aud=client ID của app**. Nếu upstream cấp ID Token cho broker thì token ấy có **iss=upstream** và **aud=client ID của broker ở upstream**. App **không được dùng upstream ID Token làm id_token_hint khi logout ở broker**; đó là token thuộc quan hệ khác.

### 2.1. Bảng trạng thái trực quan

Giả sử cả ba phiên ban đầu đều đang hoạt động:

| Hành động | App session A | Broker session B | Upstream session C | RP khác trên broker |
| --- | --- | --- | --- | --- |
| **Chỉ logout local** | Đã đóng | **Có thể còn** | **Có thể còn** | Có thể còn |
| **OIDC RP-Initiated Logout ở broker, OP chấp nhận** | Đã đóng | Đã đóng theo OP | **Không bảo đảm đã đóng** | Tùy OP có gửi notification và RP nhận/xử lý |
| **Broker có upstream logout hoạt động** | Đã đóng | Đã đóng | Có thể đóng khi upstream thực hiện thành công | Tùy cơ chế thông báo |
| **Người dùng logout trực tiếp ở upstream** | **Có thể còn** | **Có thể còn** nếu không được upstream thông báo | Đã đóng | Có thể còn |
| **Upstream gửi back-channel hợp lệ, broker xử lý và thông báo downstream** | Có thể được đóng qua downstream notification | Đã đóng | Đã đóng | Có thể được đóng |

“Có thể” trong bảng là **tính phụ thuộc triển khai**, không phải kết luận tiêu cực về OIDC. Các tầng chỉ liên động khi có một **chuỗi sự kiện logout được hỗ trợ, tin cậy, đến được đích và được xử lý thành công**.

## 3. Lớp 1 — Đăng xuất ứng dụng (local logout)

**Local logout** nghĩa là ứng dụng Spring Boot chấm dứt **phiên đăng nhập local**: xóa hoặc vô hiệu hóa SecurityContext, HttpSession/cookie session liên quan, làm sạch dữ liệu nhạy cảm trong application state và điều hướng đến trang thông báo.

~~~text
Browser -> Spring POST /logout
  -> Spring Security LogoutFilter
  -> SecurityContextLogoutHandler
  -> clear Authentication/SecurityContext
  -> invalidate HttpSession
  -> local logout success URL

Không tự gửi OIDC end-session request tới broker.
Không tự gửi SAML LogoutRequest đến IdP upstream.
~~~

Spring Security mặc định có cơ chế logout Servlet với **POST /logout** khi CSRF được bật. Thao tác local logout độc lập với việc bạn dùng form login, OAuth2 Login hay OIDC Login. Nếu chỉ cấu hình trang success URL, **không có quy tắc OIDC tiêu chuẩn nào tự được kích hoạt để chấm dứt SSO session phía OP**.

### 3.1. Kết quả trải nghiệm người dùng

Sau khi local logout, người dùng quay lại trang cần xác thực. Ứng dụng chuyển họ tới broker. Nếu **broker session B còn hiệu lực**, broker có thể cấp một authorization code/ID Token mới **không yêu cầu đăng nhập lại**. Nếu broker cần tới upstream IdP mà **upstream session C vẫn còn**, upstream cũng có thể SSO âm thầm.

Điều đó không nhất thiết là “Spring Security logout thất bại”. Local session thực sự có thể đã bị xóa đúng, nhưng **session tại những hệ thống khác vẫn có hiệu lực**.

### 3.2. Ví dụ Spring Security local-only

Đây là **class cấu hình cho dự án Spring Boot 3.x / Spring Security Servlet** có dependency OAuth2 Client; không chạy với JDK thuần nếu thiếu Spring:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LocalLogoutConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/assets/**")
                .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessUrl("/signed-out"));
        return http.build();
    }
}
~~~

**Kết quả:** ứng dụng logout local rồi chuyển đến **/signed-out**. Không có **OidcClientInitiatedLogoutSuccessHandler** nên không nên kỳ vọng broker OP session kết thúc. **/signed-out** phải có controller/static page hoặc route tương ứng; ví dụ chỉ minh họa security config, không tạo page.

Cần lưu ý:

- Không biến **GET /logout** thành thao tác thay đổi trạng thái không có CSRF protection chỉ để tiện làm nút.
- Session backend phân tán/Spring Session phải nhận việc xóa session.
- Nếu SPA giữ state trong memory/localStorage, ứng dụng cần xóa dữ liệu phù hợp trong client theo chính sách; việc xóa **HttpSession** không tự xóa mọi cache của JavaScript.
- Nếu ứng dụng là API dùng **Bearer JWT** mà không có server session, “local logout” của web browser không tự làm JWT ở nơi khác mất hiệu lực.
- Logout là một sự kiện bảo mật; đừng log session cookie, ID Token, access/refresh token hoặc PII vào trang/log debug.

## 4. Lớp 2 — Đăng xuất OIDC ở broker (RP-Initiated Logout)

Trong quan hệ **Spring app ↔ broker OP**, OpenID Connect RP-Initiated Logout 1.0 cho phép **RP đề nghị OP đăng xuất người dùng** bằng cách chuyển trình duyệt đến **Logout Endpoint của OP**, thường được công bố trong **Discovery metadata** dưới khóa **end_session_endpoint**.

~~~text
User bấm Sign out trên Spring app
     |
     v
Spring Security xử lý local logout
     |
     v
302 -> broker end_session_endpoint
       id_token_hint / client_id (theo policy)
       post_logout_redirect_uri (nếu muốn callback)
       state (nếu sử dụng)
     |
     v
Broker xác định user/OP session, áp policy và confirmation nếu cần
     |
     +-> Kết thúc broker SSO session
     +-> Có thể gửi front/back-channel logout đến các RP downstream
     +-> Có thể đề nghị logout upstream theo cấu hình broker/IdP
     |
     v
Browser trở lại post_logout_redirect_uri hợp lệ, nếu OP cho phép
~~~

**Quan trọng:** việc **redirect sang end_session_endpoint** là **gửi yêu cầu logout**, không phải bằng chứng rằng OP đã đóng phiên, các RP khác đã nhận notification hay upstream IdP đã đăng xuất. Phải quan sát response, trạng thái session/token và các cơ chế callback để khẳng định phạm vi kết quả.

### 4.1. Tham số RP-Initiated Logout

| Tham số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **end_session_endpoint** | Logout URL do OP công bố qua Discovery | URL phải đến từ issuer/config đáng tin, không do user chỉ định |
| **id_token_hint** | ID Token **trước đây OP cấp cho chính RP** | **RECOMMENDED**; giúp OP xác định phiên/client liên quan |
| **client_id** | Client ID của RP tại OP | Có thể cần nếu không có id_token_hint; OP có policy riêng |
| **post_logout_redirect_uri** | URL RP muốn OP đưa browser về sau logout | Phải **khớp chính xác URL đã đăng ký** tại OP |
| **state** | Opaque value ràng buộc logout request và callback | Nếu gửi, cần kiểm tra khi nhận lại; chống mix-up/cross-request |
| **logout_hint** | Gợi ý người dùng tùy OP | Không thay thế trust, không nên chứa bí mật |
| **ui_locales** | Locale UI của OP, nếu được hỗ trợ | Chỉ ảnh hưởng trải nghiệm, không xác thực |

Theo đặc tả, **post_logout_redirect_uri** không thể là URL tùy ý. OP không được redirect về URL không khớp giá trị được đăng ký. Khi có post_logout_redirect_uri nhưng thiếu **id_token_hint**, OP cần phương thức khác để xác nhận tính hợp lệ của đích redirect; không được bỏ kiểm tra.

**Không nhầm:** OIDC **redirect_uri** dùng khi **đăng nhập** và **post_logout_redirect_uri** dùng khi **đăng xuất** có vai trò và allowlist khác nhau. Đừng lấy bất cứ giá trị **returnTo** hoặc **next** của browser rồi gửi thẳng thành post_logout_redirect_uri.

### 4.2. Ví dụ Discovery metadata của broker

Ví dụ JSON **minh họa**, chỉ giữ các trường quan trọng:

~~~json
{
  "issuer": "https://broker.example.test/realms/enterprise",
  "authorization_endpoint":
    "https://broker.example.test/realms/enterprise/protocol/openid-connect/auth",
  "token_endpoint":
    "https://broker.example.test/realms/enterprise/protocol/openid-connect/token",
  "jwks_uri":
    "https://broker.example.test/realms/enterprise/protocol/openid-connect/certs",
  "end_session_endpoint":
    "https://broker.example.test/realms/enterprise/protocol/openid-connect/logout"
}
~~~

Đây **không phải Discovery document đầy đủ**; URL và realm là ví dụ. Ứng dụng thật có thể đọc **/.well-known/openid-configuration** từ issuer URI được quản trị, xác minh issuer theo cấu hình và dùng những endpoint thực tế. Không tìm kiếm end_session_endpoint dựa vào domain do browser nhập và **không hard-code đường dẫn của một sản phẩm** để giả định mọi OIDC OP đều giống nhau.

### 4.3. Ví dụ request ở mức wire

~~~text
GET https://broker.example.test/realms/enterprise/protocol/openid-connect/logout
    ?id_token_hint=<OIDC-ID-Token-issued-by-broker>
    &post_logout_redirect_uri=https%3A%2F%2Fportal.example.test%2Fsigned-out
    &state=<opaque-random-logout-state>
~~~

Đây là **URL minh họa cấu trúc**, các giá trị trong dấu ngoặc là mô tả, không phải token thật. Giá trị token và state phải URL-encode đúng. ID Token là một credential nhạy cảm: việc gửi qua URL có thể làm tăng rủi ro xuất hiện trong browser history, access log, proxy telemetry; cần thiết kế giảm lộ dữ liệu và tuân theo khả năng GET/POST của OP. **Không log toàn bộ query string chứa id_token_hint**.

Nếu OP hỗ trợ và framework được cấu hình đúng, RP-Initiated Logout cũng có thể dùng POST theo đặc tả/cấu hình; không tự kết luận một POST bất kỳ tới URL login là logout.

## 5. Cấu hình Spring Boot OIDC Client với broker

Ví dụ **application.yml** trong Spring Boot 3.x, ứng dụng dùng **OIDC Authorization Code flow** với broker:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: "portal-web"
            client-secret: "${BROKER_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
        provider:
          broker:
            issuer-uri: "https://broker.example.test/realms/enterprise"
~~~

**Giải thích:**

- **registration.broker** là **ClientRegistration** local Spring Security để đăng nhập với OIDC OP broker.
- **client-id=portal-web** là client ID mà broker cấp cho **ứng dụng**, không phải client ID mà broker dùng khi kết nối IdP upstream.
- **issuer-uri** phải là **issuer broker**, vì broker là OP trực tiếp phát ID Token cho app. Không đặt issuer của upstream vào đây nếu app **không** xác thực trực tiếp với upstream.
- **scope: openid** phân biệt OIDC login với OAuth2-only; Spring Security có thể tạo **OidcUser** và lưu ID Token từ broker.
- Client secret trong ví dụ lấy từ biến môi trường để minh họa; ở production nên dùng secret manager/keystore/volume được bảo vệ, không commit literal secret vào repo. Lưu ý process environment cũng có rủi ro bị lộ qua tooling/debug.
- Spring Security dùng provider metadata để nhận discovery endpoints, gồm **end_session_endpoint** khi OP quảng bá RP-Initiated Logout.

Ứng dụng còn cần đăng ký **login redirect URI** và **Valid Post Logout Redirect URI** tại broker. Một bên chạy thành công OAuth2 login **không chứng minh** broker đã cho phép post-logout redirection.

## 6. Spring Security Servlet: OidcClientInitiatedLogoutSuccessHandler

Spring Security có sẵn **OidcClientInitiatedLogoutSuccessHandler** cho RP-Initiated Logout. Đây là cơ chế dành cho ứng dụng **OIDC RP trực tiếp kết nối broker**. Không gọi API của upstream từ application handler nếu giữa hai bên là broker, vì app không sở hữu phiên/client context của broker ở upstream.

Ví dụ class **SecurityConfig.java** trong ứng dụng Spring Boot có dependency **spring-security-oauth2-client**:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations)
            throws Exception {

        OidcClientInitiatedLogoutSuccessHandler oidcLogout =
            new OidcClientInitiatedLogoutSuccessHandler(
                clientRegistrations);

        oidcLogout.setPostLogoutRedirectUri(
            "{baseUrl}/signed-out");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/assets/**")
                .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessHandler(oidcLogout));

        return http.build();
    }
}
~~~

**Đây là class cấu hình Spring Boot**, không thể chạy độc lập bằng javac nếu thiếu dependencies, broker metadata, client registration, secrets và trang **/signed-out**. Các API tương ứng phải được kiểm tra theo **Spring Security phiên bản đang chạy**.

Theo Spring Security docs:

- **OidcClientInitiatedLogoutSuccessHandler** nhận **ClientRegistrationRepository** để xác định OP/metadata của OIDC client.
- **setPostLogoutRedirectUri("{baseUrl}/signed-out")** chỉ định đích callback; template **{baseUrl}** dựa vào base scheme/host/port/path mà ứng dụng nhìn thấy.
- Mặc định handler dùng HTTP redirect **GET** đến OP logout URL; bản mới có API dùng **FormPostRedirectStrategy** nếu cần POST và OP/framework hỗ trợ.
- Để việc phát OIDC logout phù hợp, Authentication phải là **OIDC login**, và OP phải có **end_session_endpoint**/client registration hợp lệ. Nếu chỉ OAuth2 login không có OIDC ID Token hoặc OP không công bố endpoint, cần thiết kế **fallback local logout** rõ; không tự khẳng định handler chắc chắn gọi được OP.

**Một lưu ý quản lý URL:** nếu ứng dụng chạy sau ingress/reverse proxy, phải bảo đảm **{baseUrl}** được tính từ public URL đã tin cậy. Nếu tạo **http://internal-node:8080/signed-out**, OP sẽ từ chối post_logout_redirect_uri hoặc redirect về sai host. Không đặt niềm tin vô điều kiện vào Host/X-Forwarded-* do browser tự cung cấp.

### 6.1. OIDC client-initiated handler không phải back-channel receiver

Class trên **khởi tạo** logout từ app đến broker. Nó **không tự cài đặt endpoint nhận Logout Token** của OIDC Back-Channel Logout. Nếu sản phẩm cần broker thông báo logout tới app **khi người dùng thoát ở một RP khác, IdP hoặc admin console**, cần cấu hình **front-channel/back-channel** theo khả năng Spring Security/adapter/framework và một endpoint thực thi đúng đặc tả.

Không tự kết luận **đã dùng OidcClientInitiatedLogoutSuccessHandler** tức là app tự biết khi upstream IdP logout ở một cửa sổ khác.

## 7. Lớp 3 — Đăng xuất IdP upstream phía sau môi giới

Broker đóng hai vai trò: là **OP đối với app**, nhưng là **RP hoặc SP đối với upstream**. Khi app gửi RP-Initiated Logout tới broker, broker phải quyết định **có nên và có thể gửi yêu cầu logout lên IdP upstream không**.

~~~text
App --(OIDC logout)--> Broker OP
                       |
                       +-- xóa broker session
                       |
                       +-- tùy cấu hình:
                           |
                           +-- OIDC upstream:
                           |      RP-Initiated Logout / Logout URL
                           |      hoặc back-channel khi IdP hỗ trợ
                           |
                           +-- SAML upstream:
                           |      SAML Single Logout (SLO)
                           |
                           +-- Social/custom IdP:
                                  có thể không có logout API/
                                  không có session mapping
~~~

**Không có một tiêu chuẩn OIDC chung bắt buộc mọi broker phải đăng xuất được ở mọi upstream IdP.** Tùy sản phẩm, phiên bản, cấu hình broker, type của IdP, transport, vòng đời browser cookie, khả năng logout protocol và sự chấp thuận của người dùng.

### 7.1. OIDC upstream

Broker có thể cấu hình một **Logout URL** hoặc sử dụng discovery của upstream OP để thực hiện RP-Initiated Logout. Trong tình huống này:

- **Broker** là OIDC RP của upstream.
- **Upstream IdP** là OP thực hiện logout.
- **ID Token hint mà upstream hiểu** phải là ID Token **upstream cấp cho broker**, không phải ID Token **broker cấp cho app**.
- **post_logout_redirect_uri** (nếu dùng) phải là URI **đã đăng ký của broker với upstream**, không phải URL cuối của app.
- Có thể dùng **back-channel logout** nếu broker và IdP upstream hỗ trợ, cùng mapping session phù hợp.
- Không đoán rằng broker giữ được upstream ID Token sau khi xóa session; cần biết provider/broker lưu loại token và logout context nào.

### 7.2. SAML upstream

Nếu broker dùng SAML 2.0 để đăng nhập tại IdP upstream, việc đăng xuất có thể dùng **SAML Single Logout**:

~~~text
Broker (SAML SP) -> upstream (SAML IdP):
  LogoutRequest ID / NameID / SessionIndex
upstream -> Broker:
  LogoutResponse InResponseTo = request ID
~~~

Khả năng SAML SLO phụ thuộc **SingleLogoutService endpoint, signing credentials, NameID/SessionIndex còn lưu, binding, chữ ký và correlation state**. Nó khác hoàn toàn với OIDC end_session_endpoint; không gửi OIDC ID Token hint cho một SAML SLO endpoint.

Nếu IdP upstream chỉ hỗ trợ login SAML mà **không hỗ trợ SLO**, broker không thể “tự phát minh” lời gọi logout phổ quát. Có thể tiếp tục xóa broker/local sessions và thông báo rõ rằng phiên upstream còn tồn tại, kết hợp logout link/thủ tục theo sản phẩm nếu được phê duyệt.

### 7.3. Ví dụ Keycloak Identity Brokering

Keycloak có thể đóng vai broker giữa OIDC client app và upstream OIDC/SAML IdP. Tài liệu quản trị Keycloak có phần **Identity brokering** và **OIDC Logout**. Với upstream OIDC, cấu hình có **Logout URL** tùy chọn và khả năng **Backchannel Logout** ở một số nhà cung cấp. Keycloak cũng có tùy chọn cho hành vi logout broker/upstream tùy loại IdP và phiên bản.

**Không khẳng định “Keycloak luôn logout upstream” hoặc “Keycloak không bao giờ logout upstream”.** Phải kiểm tra phiên bản hiện tại và provider configuration: Logout URL, broker-initiated logout behavior, chế độ back-channel, session mapping và phía upstream có nhận và xử lý không.

Cũng cần phân biệt hai nhóm cài đặt Keycloak:

- **Client của ứng dụng ở realm broker**: Valid Post Logout Redirect URIs, Front-Channel Logout, Backchannel Logout URL, session required, client session behavior.
- **Identity Provider upstream trong realm broker**: Identity Provider alias/type, Logout URL/SLO URL, Backchannel Logout, lưu trữ/khôi phục token upstream, tùy chọn propagating logout.

Cấu hình client **không tự thay thế** cấu hình upstream identity provider và ngược lại.

### 7.4. IdP upstream có thể giữ SSO session dù browser vừa đi qua trang logout broker

Điều này giải thích hiện tượng:

~~~text
App logout local -> broker logout thành công
Upstream IdP session vẫn còn

User vào app lần nữa -> app redirect broker
Broker không còn session -> broker redirect upstream IdP
Upstream IdP vẫn có cookie SSO -> xác thực im lặng
Broker tạo session mới -> app tạo session mới
~~~

Một kết quả login nhanh sau logout **không nhất thiết chứng minh broker logout chưa chạy**; cũng có thể upstream đã tạo **một phiên broker hoàn toàn mới** từ SSO session upstream còn hiệu lực.

Để phân loại, phải theo dõi session/cookie và telemetry tại **đúng từng tầng**, không chỉ đo cảm giác “người dùng không phải nhập mật khẩu”.

## 8. OP-initiated logout: từ broker xuống các ứng dụng khác

Khi broker session B bị đóng, broker có thể thông báo đến các **Relying Party khác** dùng broker này. OIDC có nhiều cơ chế khác nhau:

| Cơ chế | Hướng thông báo | Nội dung chính | Điểm hạn chế |
| --- | --- | --- | --- |
| **RP-Initiated Logout 1.0** | App RP -> Broker OP | Browser gửi yêu cầu đến end_session_endpoint | Chỉ là đề nghị OP logout |
| **Front-Channel Logout 1.0** | Broker OP -> RP qua browser | RP nhận GET ở frontchannel_logout_uri, có thể có iss/sid | Phụ thuộc iframe/cookie/cross-site browser |
| **Back-Channel Logout 1.0** | Broker OP -> RP server-to-server | HTTP POST logout_token JWT đến backchannel_logout_uri | Cần endpoint, JWT validation và session mapping |
| **OIDC Session Management 1.0** | Browser RP theo dõi OP session state | RP phát hiện thay đổi SSO state | Phụ thuộc browser, cookie và tích hợp |
| **Local logout** | Người dùng -> một ứng dụng | Xóa session/cookie của chính ứng dụng | Không chạm broker/IdP nếu không có protocol |

Không coi cơ chế nào có sẵn chỉ vì OP đã hỗ trợ OIDC login. **Login endpoint, logout endpoint và notification endpoint là các khả năng khác nhau**, phải đăng ký/test riêng.

### 8.1. Front-channel: dựa vào browser

OIDC Front-Channel Logout cho phép OP dùng user agent để mở **frontchannel_logout_uri** của RP, thông thường thông qua iframe. OP có thể truyền **iss** và **sid** để RP biết session nào cần kết thúc; RP nên kiểm tra mapping session phù hợp.

Hạn chế:

- Third-party cookie restrictions hoặc **SameSite** có thể khiến RP không đọc được session cookie trong iframe.
- **Content Security Policy (CSP)** hoặc X-Frame-Options có thể chặn embedding.
- Browser/tab bị đóng trước khi các iframe chạy khiến notification không tới đích.
- Một số RP là BFF có cookie httpOnly và không thể xác định session từ iframe nếu third-party cookie bị chặn.
- Không xem “trang broker logout đã hiển thị” là bằng chứng mọi iframe logout thành công.

Đặc tả OIDC Front-Channel Logout khuyến nghị xử lý các trình duyệt chặn third-party content, và nêu rằng back-channel không chịu cùng hạn chế browser đó.

### 8.2. Back-channel: thông báo server-to-server

OIDC Back-Channel Logout 1.0 cho phép OP gửi HTTP POST tới **backchannel_logout_uri** đã đăng ký của RP. Request body dạng **application/x-www-form-urlencoded** chứa trường **logout_token**, một **JWT có chữ ký**.

~~~text
POST /oidc/backchannel-logout HTTP/1.1
Content-Type: application/x-www-form-urlencoded

logout_token=<signed-jwt-from-trusted-broker>
~~~

Đây là **mẫu mô tả giao thức**, không phải HTTP request đã có token hợp lệ.

Back-channel có thể vận hành khi browser đã đóng hoặc không cho third-party cookies, nhưng không tự biến thành “đảm bảo tuyệt đối”:

- OP phải được cấu hình gửi notification.
- RP phải có public endpoint phù hợp và **xác minh JWT**.
- RP phải có cách map **iss+sid/sub** đến **đúng local session** để invalidate.
- Server cần quản lý retries/duplicate delivery, expiration, replay và đồng bộ distributed session.
- Notification có thể thất bại do network hoặc configuration; cần đo lường và retry policy.

**Một SecurityFilterChain đã có oauth2Login() không tự tạo đầy đủ backchannel logout endpoint và session registry**. Việc hỗ trợ có thể qua adapter/phiên bản Spring Security hoặc implementation riêng; phải xác minh API và khả năng thực tế.

## 9. Logout Token: không phải ID Token, không phải access token

OIDC Back-Channel Logout Token là một JWT có mục đích riêng. Ví dụ **claims minh họa**:

~~~json
{
  "iss": "https://broker.example.test/realms/enterprise",
  "aud": "portal-web",
  "iat": 1760000000,
  "exp": 1760000300,
  "jti": "logout-event-123",
  "sid": "broker-session-7",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

JSON chỉ là **JWT claims payload minh họa**, không có JOSE header/signature và **không phải Logout Token hợp lệ để gửi**. Giá trị **iat/exp** ở đây chỉ để minh họa định dạng Unix time, không mô tả thời điểm vận hành hiện tại.

Các kiểm tra thiết yếu theo **OpenID Connect Back-Channel Logout 1.0**:

1. Token là JWT được **ký số hợp lệ**, dùng khóa OP/JWKS đáng tin cho đúng issuer; **không chấp nhận alg=none**.
2. Kiểm **iss** chính xác là broker OP tin cậy đã đăng ký, không phải upstream issuer nếu RP trực tiếp trust broker.
3. Kiểm **aud** chứa client ID của chính RP nhận notification.
4. Kiểm thời gian **iat** và **exp** khi có, độ lệch đồng hồ/expiry theo đặc tả và policy.
5. Có **events** với key chính xác **http://schemas.openid.net/event/backchannel-logout** và giá trị object.
6. Phải có ít nhất một trong **sub hoặc sid**, có thể có cả hai.
7. **Không được có nonce**. Token ID Token và Logout Token phải phân biệt để tránh token-type confusion.
8. Có **jti** theo yêu cầu và chống duplicate/replay trong cửa sổ hợp lý.
9. Mapping **sid** phải xét cả issuer/client/session scope; sid chỉ là identifier trong ngữ cảnh OP.
10. Tìm đúng session local, invalidate session/các token theo chính sách; xử lý idempotent nếu đã logout.

**Không chỉ đọc JWT payload Base64 rồi thấy sid trùng là logout.** Một attacker có thể tự tạo JSON giả và ép RP xóa phiên của người khác nếu bỏ kiểm chữ ký, iss, aud hoặc event type.

Với hệ thống môi giới, còn một cấp validation khác: **broker nhận upstream backchannel logout token** cần xác minh **issuer/JWKS upstream và client ID của broker**, sau đó broker **tự phát notification đến các RP downstream** nếu policy/capability cho phép. App **không nên trực tiếp xử lý logout token từ upstream** khi nó là client của broker, trừ khi có thiết kế riêng đã được đánh giá.

### 9.1. oidc sid khác app session ID

- **sid** OIDC đại diện phiên do OP định danh; có thể khác giữa broker và upstream.
- **JSESSIONID** là HTTP session cookie của Java web app; không phải OIDC sid.
- **sub** là subject từ issuer; giá trị chỉ unique trong đúng **issuer** và client/session scope theo profile.
- **jti** định danh **JWT sự kiện**, dùng chống replay, không phải ID session.
- Một người dùng có nhiều browser/devices; logout theo sid có thể chỉ nhằm một phiên, logout theo sub không sid có thể nhắm nhiều phiên theo quy định.
- Không dùng email để tìm và hủy toàn bộ phiên của mọi tenant nếu chỉ một OP gửi logout token.

## 10. Đăng xuất từ upstream xuống broker rồi xuống app

Kịch bản **người dùng logout trực tiếp ở IdP upstream**:

~~~text
Upstream user session C kết thúc
     |
     +-- upstream hỗ trợ OIDC Back-Channel / SAML SLO / cơ chế thông báo?
     |       |
     |       +-- KHÔNG:
     |       |     Broker B có thể tiếp tục sống
     |       |     App A có thể tiếp tục sống
     |       |
     |       +-- CÓ, broker thực sự nhận/verify:
     |             |
     |             v
     |           Broker vô hiệu hóa đúng broker session B
     |             |
     |             +-- broker có gửi logout cho downstream RPs?
     |                    |
     |                    +-- Có, RP nhận/verify/match:
     |                    |      App A bị vô hiệu hóa
     |                    |
     |                    +-- Không / gửi lỗi:
     |                           App A có thể còn
~~~

**Cần hai bước propagation độc lập**:

- **Upstream → broker**: upstream phải hỗ trợ và cấu hình logout notification, broker phải xử lý/kiểm chứng và biết broker session nào gắn với upstream session.
- **Broker → app**: broker phải hỗ trợ và cấu hình RP notifications; app phải có session mapping và endpoint xử lý đúng.

Một bước ở giữa lỗi không thể được suy ra chỉ từ trạng thái cuối của hệ thống khác. Để kiểm chứng, cần quan sát logs an toàn và session state ở từng tầng.

### 10.1. Một môi giới có nhiều upstream IdP

Một broker có thể phục vụ nhiều IdP (Corporate A, Corporate B, social login). Khi nhận sự kiện logout từ upstream A, broker không nên xóa bừa **mọi phiên của mọi user trùng email** hoặc dùng issuer B để xác minh token A.

State cần map:

~~~text
Broker session:
  brokerIssuer
  brokerSid
  localSubject
  upstreamProviderAlias
  upstreamIssuer
  upstreamSubject
  upstreamSid / SAML SessionIndex
  downstreamClientSessions
~~~

Đây là **mô hình logical data**, không nói sản phẩm nào nhất thiết lưu đủ từng field như vậy. Một lần logout upstream phải tìm đúng **provider + subject/session**, rồi áp chính sách fanout có scope, không cho client/browser tự khai provider alias và tắt session của đối tác khác.

### 10.2. IdP kết thúc session nhưng access token vẫn còn

Nếu ứng dụng có access token JWT do broker cấp và resource server chỉ xác minh **signature + exp** offline, token có thể tiếp tục được chấp nhận **đến khi hết hạn** dù browser session ở broker đã đóng. Điều này không tự chứng minh logout thất bại; nó là ranh giới giữa **session invalidation** và **token validation policy**.

Cần thiết kế token expiry ngắn, refresh-token policy, token revocation/introspection hoặc kiểm trạng thái khi yêu cầu rủi ro cao, tùy kiến trúc. Không khẳng định mọi JWT bị thu hồi ngay khi RP-Initiated Logout, vì không có cam kết chung như vậy.

## 11. Đăng xuất OIDC và OAuth2 Token Revocation là hai nghiệp vụ khác nhau

**OIDC logout** hướng đến chấm dứt **OP/RP session** theo các cơ chế chuẩn. **OAuth 2.0 Token Revocation (RFC 7009)** hướng đến vô hiệu hóa **token hoặc authorization grant** qua **revocation_endpoint**, nếu authorization server hỗ trợ.

| Nghiệp vụ | Thành phần nhận | Đối tượng kết thúc | Điều không tự đảm bảo |
| --- | --- | --- | --- |
| Spring local logout | Ứng dụng RP | HttpSession/SecurityContext local | Broker/upstream session, tokens độc lập |
| OIDC RP-initiated logout | Broker OP | Broker SSO session theo chính sách | Upstream session, mọi JWT/refresh token và RP khác |
| OAuth2 token revocation | Authorization server | Token/authorization grant theo policy AS | Browser SSO session ở OP hoặc upstream |
| OIDC back-channel logout | RP receiving OP event | Local sessions xác định bởi logout_token | Access JWT ở resource server khác nếu không có kiểm tra |
| SAML Single Logout upstream | SAML IdP/partner SPs | SAML sessions theo SLO profile | OIDC tokens, tất cả ứng dụng khác không tham gia SLO |

Các điểm vận hành:

- RFC 7009 yêu cầu hỗ trợ **refresh token revocation** và khuyến nghị hỗ trợ **access token revocation**; hiệu ứng dây chuyền phụ thuộc AS policy.
- Một refresh token bị vô hiệu hóa khiến app không lấy token mới được, nhưng **access JWT đã phát có thể còn khả dụng** đối với resource server kiểm token offline cho đến khi exp hoặc bị chặn theo cơ chế khác.
- Access token, refresh token và ID Token có **mục đích khác nhau**. ID Token là chứng nhận đăng nhập cho RP, thường dùng làm id_token_hint trong RP-Initiated Logout; nó không phải API Bearer Access Token.
- Nếu ứng dụng lưu OAuth2AuthorizedClient trong database/cache, cần quyết định cleanup/revocation khi logout, không chỉ xóa HttpSession.
- Nếu dùng **offline_access**, refresh/offline token có thể có vòng đời khác browser session; phải quản lý riêng theo policy và OP implementation.
- Không gọi một endpoint revocation với client secret hoặc refresh token của **upstream** từ ứng dụng đang chỉ tin **broker**: broker mới là RP nắm quan hệ upstream đó.

## 12. Hai cách triển khai phổ biến: server-rendered/BFF và SPA

### 12.1. Server-rendered Spring Boot hoặc BFF

Ở mô hình này browser giữ **session cookie của Spring**, còn ID/access/refresh tokens chủ yếu ở server:

~~~text
Browser cookie -> Spring HttpSession
Spring server -> OAuth2AuthorizedClient tokens -> broker
~~~

Logout tối thiểu nên:

1. Vô hiệu hóa session local, clear SecurityContext và thông tin AuthorizedClient theo chính sách.
2. Nếu logout broker được yêu cầu, gửi browser tới broker **end_session_endpoint** bằng handler OIDC.
3. Nhận callback qua post_logout_redirect_uri được đăng ký; nếu có state, xác minh state.
4. Hiển thị thông báo chính xác về những lớp đã biết hoàn tất.
5. Không hiển thị nguyên văn ID Token hoặc session cookie trong redirect logs.

Nếu OP không hỗ trợ RP-Initiated Logout, fallback là local-only và **nói rõ giới hạn**. Không tự gọi SAML endpoint upstream từ BFF.

### 12.2. SPA có token phía trình duyệt

Ở SPA, JavaScript app có thể giữ tokens trong memory, trong khi browser cũng có OP SSO cookie. Logout cần:

- Xóa app state/tokens ở nơi đang lưu theo policy.
- Gọi OIDC client library/redirect đến end_session_endpoint phù hợp.
- Không lưu client secret vào frontend bundle.
- Xem xét nhiều tab/broadcast state, cookie SameSite và callback.
- Tránh lưu tokens nhạy cảm vào localStorage nếu có phương án bảo mật tốt hơn, nhất là khi XSS là rủi ro.
- Không tin lời hứa “đã xóa localStorage” là đã thu hồi refresh token ở OP.

Với BFF, backend có thể quản lý token và cookie an toàn hơn; song việc kết thúc **upstream IdP session** vẫn là chuyện của broker và upstream protocol.

## 13. Redirect, state, cookie và reverse proxy

### 13.1. post_logout_redirect_uri cần exact matching

Một đường dẫn có thể được đăng ký:

~~~text
https://portal.example.test/signed-out
~~~

Nếu Spring tạo:

~~~text
http://portal.internal:8080/signed-out
~~~

broker có thể từ chối vì không khớp allowlist. Khi chạy sau ingress:

- Dùng public HTTPS base URL cố định hoặc cấu hình forwarded headers từ **trusted proxy**.
- Không tin tùy ý Host/X-Forwarded-Host do browser tự gửi.
- Đối chiếu callback được OP đăng ký **đúng path, scheme, host, port**.
- Không chuyển post_logout_redirect_uri thành **open redirect** dựa trên tham số returnUrl chưa validate.

### 13.2. state và logout CSRF

Nếu RP gửi tham số **state**, cần gắn nó với **một logout flow cụ thể**, có TTL, đủ entropy và đối chiếu khi browser quay về. State **không phải session ID**, không phải JWT dùng xác thực và không nên chứa bí mật.

Một attacker có thể cố buộc browser truy cập một logout endpoint không có cơ chế chống CSRF/confirmation để gây **forced logout**. Vì vậy:

- Local logout trên web nên đi qua POST có CSRF protection đúng.
- OP phải áp quy tắc RP-Initiated Logout: id_token_hint hoặc xác minh client/logout target, confirmation khi cần.
- Front-channel logout phải xác minh/đối chiếu iss+sid theo profile, không nhận GET nào cũng hủy mọi phiên.
- Back-channel logout phải verify signed JWT và chống replay.
- Không tắt CSRF toàn bộ app chỉ vì muốn gọi OIDC logout qua link GET.

### 13.3. Browser cookies quyết định điều gì?

- App cookie nhận diện **ứng dụng**.
- Broker cookie nhận diện **OP SSO session**.
- Upstream cookie nhận diện **IdP upstream session**.

Mỗi cookie có domain, path, SameSite, Secure và lifetime riêng. Một response xóa cookie app **không thể tùy ý xóa cookie có domain thuộc upstream IdP**. Cơ chế front-channel phụ thuộc browser có gửi cookie đích khi iframe/redirect; back-channel không phụ thuộc browser nhưng yêu cầu server-side session mapping.

## 14. Security boundaries khi broker nhiều đối tác/tenant

Trong multi-IdP/multi-tenant, một broker có thể đăng nhập người dùng từ IdP A hoặc IdP B. Logout propagation cần giữ **issuer/subject/session scope**:

| Đối tượng | Key định danh tốt để correlation | Không nên chỉ dùng |
| --- | --- | --- |
| App local session | application session ID + OIDC provider registration / broker sid đã xác minh | Email từ browser |
| Broker session | broker issuer + broker sid, local subject + RP client link | App JSESSIONID |
| Upstream OIDC session | upstream issuer + upstream sid/sub + provider alias | sub không kèm issuer |
| Upstream SAML session | upstream IdP entityId + NameID + SessionIndex theo profile | Chỉ email/NameID chưa đủ scope |
| Logout Token event | issuer + audience/client + jti + sid/sub đã verified | Payload JWT chưa kiểm chữ ký |

Một user có thể đăng nhập hai tài khoản/tenant trên hai trình duyệt. Sự kiện logout theo một upstream sid **không nên vô hiệu hóa mọi user có cùng email**. Khi có lỗi mapping, chọn **fail closed** và báo trạng thái không hoàn tất, không “broadcast logout tất cả” để dễ lập trình.

Nếu broker và app hỗ trợ nhiều OP/realms, cần xác minh **iss và aud theo đúng client registration**. Một Logout Token của Broker A không được dùng để xóa session được xác thực bởi Broker B.

## 15. Ví dụ trải nghiệm: tại sao logout xong lại đăng nhập không cần mật khẩu?

### Kịch bản A — Chỉ logout local

~~~text
A (app session):      ĐÓNG
B (broker session):   CÒN
C (upstream session): CÒN

User vào /protected -> redirect broker
Broker nhận thấy B còn -> phát code/ID Token mới
User đăng nhập lại gần như tức thì
~~~

**Chẩn đoán:** app logout có thể đã đúng. Nếu UX yêu cầu kết thúc SSO ở broker, hãy dùng RP-Initiated Logout và kiểm OP metadata.

### Kịch bản B — Broker logout, upstream còn

~~~text
A: ĐÓNG
B: ĐÓNG
C: CÒN

User vào /protected -> broker không còn B
Broker redirect upstream -> upstream vẫn có C
Upstream cấp identity -> broker tạo B mới
Broker quay về app -> app tạo A mới
~~~

**Chẩn đoán:** cần kiểm cấu hình **broker → upstream Logout URL/SAML SLO/backchannel**, không sửa local HttpSession.

### Kịch bản C — Upstream logout, broker không nhận được notification

~~~text
A: CÒN
B: CÒN
C: ĐÓNG

Browser vẫn truy cập app với session A hợp lệ
Broker B chưa biết upstream C bị đóng
~~~

**Chẩn đoán:** thiếu hoặc lỗi **upstream → broker notification**, và/hoặc thiếu **broker → downstream RP logout**. Cần cấu hình các kênh này hoặc kiểm lại session freshness/reauthentication policy.

### Kịch bản D — Logout toàn chuỗi được hỗ trợ

~~~text
App local logout -> broker RP-initiated logout accepted
Broker xử lý session B -> gửi logout downstream
Broker thực hiện upstream logout -> upstream xác nhận
Broker/app nhận và xử lý callbacks/notifications

A: ĐÓNG
B: ĐÓNG
C: ĐÓNG
Other RPs: tùy từng notification đã được xử lý thực tế
~~~

**Đừng dùng câu “đăng xuất tất cả thành công” chỉ vì app có một HTTP 302**. Mỗi bước có thể timeout/retry/partial failure; cần định nghĩa success ở mức hệ thống.

## 16. Java 17 độc lập: mô hình các lớp phiên và propagation

Chương trình dưới chạy bằng **JDK 17 trở lên**, không cần Spring hay OIDC server. Nó là **mô phỏng state-machine** để làm rõ các kết quả logout:

- **Local logout** chỉ đóng app session.
- **Broker accepted RP-Initiated Logout** đóng broker session; có hai policy độc lập **notify sibling RPs** và **propagate upstream**.
- **Upstream direct logout** không tự đóng app/broker nếu không có notification đến broker.
- **Upstream back-channel event** phải được thư viện tin cậy xác minh và match issuer/audience/session trước khi broker được phép propagate.
- Sau broker logout, **refreshTokenUsable=false trong demo** là **giả định policy broker có áp dụng token invalidation**; **không phải quy định bắt buộc của RP-Initiated Logout**.
- **accessTokenNotExpired=true** minh họa JWT đã phát vẫn có thể còn hạn theo exp; resource server có chấp nhận nó không còn phụ thuộc revocation/introspection/policy.

**Cảnh báo:** boolean **validatedByJwtLibrary** trong demo là **đầu ra giả lập của bộ xác minh**. Không lấy boolean này từ HTTP body/query! Mã này không thực hiện JWT signature verification, HTTP redirect, OIDC Discovery, broker session lookup hay token revocation. Hệ thống thật phải dùng Spring Security/OIDC libraries, database session registry và trust configuration.

Tệp **OidcBrokerLogoutLayersDemo.java**:

~~~java
import java.util.Objects;

public class OidcBrokerLogoutLayersDemo {
    static final class Sessions {
        boolean application = true;
        boolean brokerOp = true;
        boolean upstreamIdp = true;
        boolean siblingRp = true;
        boolean refreshTokenUsable = true;
        boolean accessTokenNotExpired = true;

        void localLogout() {
            application = false;
        }

        // Models an OP that accepted the RP-initiated logout request.
        // Notification/propagation are explicit capabilities, not guarantees.
        void acceptedOidcLogout(boolean notifySibling,
                                boolean upstreamPropagationEnabled) {
            localLogout();
            brokerOp = false;
            refreshTokenUsable = false;
            if (notifySibling) siblingRp = false;
            if (upstreamPropagationEnabled) upstreamIdp = false;
        }

        boolean onUpstreamBackchannel(
                String issuer, String audience, String sessionId,
                boolean validatedByJwtLibrary) {
            // "validatedByJwtLibrary" is MOCK TRUST from tests only.
            if (!validatedByJwtLibrary
                    || !Objects.equals(
                        issuer, "https://upstream.example.test")
                    || !Objects.equals(audience, "broker-client")
                    || !Objects.equals(sessionId, "upstream-session-7")) {
                return false;
            }
            upstreamIdp = false;
            brokerOp = false;
            application = false;
            siblingRp = false;
            refreshTokenUsable = false;
            return true;
        }

        String summary() {
            return "app=" + application + ",broker=" + brokerOp
                + ",upstream=" + upstreamIdp + ",sibling=" + siblingRp;
        }
    }

    public static void main(String[] args) {
        Sessions local = new Sessions();
        local.localLogout();
        System.out.println("localOnly=" + local.summary());

        Sessions oidc = new Sessions();
        oidc.acceptedOidcLogout(true, false);
        System.out.println("oidcNoUpstream=" + oidc.summary());

        Sessions isolated = new Sessions();
        isolated.acceptedOidcLogout(false, false);
        System.out.println("oidcNoSiblingNotification=" + isolated.summary());

        Sessions propagated = new Sessions();
        propagated.acceptedOidcLogout(true, true);
        System.out.println("oidcAndUpstream=" + propagated.summary());

        Sessions upstream = new Sessions();
        upstream.upstreamIdp = false; // user signed out upstream directly
        System.out.println("upstreamWithoutNotice=" + upstream.summary());
        boolean rejected = !upstream.onUpstreamBackchannel(
            "https://fake.example.test", "broker-client",
            "upstream-session-7", false);
        System.out.println("untrustedNoticeRejected=" + rejected);
        System.out.println("upstreamAfterUntrustedNotice=" + upstream.summary());
        boolean accepted = upstream.onUpstreamBackchannel(
            "https://upstream.example.test", "broker-client",
            "upstream-session-7", true);
        System.out.println("trustedNoticeAccepted=" + accepted);
        System.out.println("upstreamWithNotice=" + upstream.summary());

        System.out.println("refreshTokenUsableAfterOidc=" + oidc.refreshTokenUsable);
        System.out.println("accessTokenMayRemainTimeValid=" + oidc.accessTokenNotExpired);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 OidcBrokerLogoutLayersDemo.java
java OidcBrokerLogoutLayersDemo
~~~

**Stdout chính xác**:

~~~text
localOnly=app=false,broker=true,upstream=true,sibling=true
oidcNoUpstream=app=false,broker=false,upstream=true,sibling=false
oidcNoSiblingNotification=app=false,broker=false,upstream=true,sibling=true
oidcAndUpstream=app=false,broker=false,upstream=false,sibling=false
upstreamWithoutNotice=app=true,broker=true,upstream=false,sibling=true
untrustedNoticeRejected=true
upstreamAfterUntrustedNotice=app=true,broker=true,upstream=false,sibling=true
trustedNoticeAccepted=true
upstreamWithNotice=app=false,broker=false,upstream=false,sibling=false
refreshTokenUsableAfterOidc=false
accessTokenMayRemainTimeValid=true
~~~

**Cách diễn giải:** true/false ở các dòng không chứng minh trạng thái SSO của một broker thật. Đó là **các kết quả giả định** ứng với khả năng notify/propagate cụ thể. Nhờ đó thấy rõ **local logout**, **broker OP logout** và **upstream IdP logout** là ba sự kiện khác nhau, và nhiều sự kiện độc lập phải cùng thành công nếu muốn kết luận “logout toàn chuỗi”.

## 17. Ma trận kiểm thử tích hợp

| Test case | Hành động | Kỳ vọng kiểm chứng |
| --- | --- | --- |
| Chỉ local logout | App POST /logout với local handler | A đóng; **không** tự yêu cầu B/C đóng |
| RP-Initiated Logout hợp lệ | App logout với OIDC handler, broker hỗ trợ endpoint | A đóng, browser tới broker end_session_endpoint; kiểm trạng thái B |
| OP không có end_session_endpoint | Discovery thiếu endpoint | Local fallback rõ; không báo broker logout chắc chắn |
| OIDC login vs OAuth2-only | Authentication không có OidcUser/ID Token phù hợp | Không gửi id_token_hint giả; local fallback policy |
| Sai post_logout_redirect_uri | URI khác allowlist broker | OP từ chối redirect; không tạo open redirect |
| Reverse proxy sai host | {baseUrl} trỏ internal HTTP | Test phát hiện callback mismatch |
| state bị sửa | Callback có state không khớp request đã lưu | Từ chối/không tin callback |
| Không có ID Token hint | OP yêu cầu xác nhận thêm | OP áp policy/confirmation, không bypass |
| Broker OP logout thành công, upstream không có SLO | A/B đóng, C còn | UI không tuyên bố C đã đóng |
| Broker logout có upstream propagation | Cấu hình upstream Logout URL/SAML SLO | Xác nhận notification và trạng thái C thật |
| Upstream OIDC logout token đến broker | JWT signed bằng upstream OP key, iss/aud/sid đúng | Broker mapping session và xử lý đúng |
| Upstream logout token alg=none | Token không có signature hợp lệ | Từ chối |
| Upstream logout token sai issuer | Issuer IdP khác | Không hủy broker session của IdP này |
| Back-channel thiếu event | JWT không có backchannel-logout events claim | Từ chối |
| Back-channel có nonce | Logout Token có nonce claim | Từ chối theo spec |
| Back-channel thiếu sub/sid | Không định vị được session | Từ chối |
| Back-channel sai aud | Token dành cho client khác | Từ chối |
| Back-channel replay | jti bị gửi lại | Idempotent + replay protection |
| Broker gửi front-channel iframe | App nhận request trong iframe | Test SameSite/CSP/third-party cookie |
| Browser đóng giữa logout | OP đang notify front-channel | Không tự kết luận RP khác đã logout |
| Broker gửi downstream back-channel | RP endpoint nhận signed Logout Token | Match đúng session, invalidate thành công |
| Sibling RP thiếu backchannel URL | Broker không có nơi gửi notification | Sibling session có thể còn |
| Upstream SAML IdP | Broker gửi SAML LogoutRequest nếu SLO hỗ trợ | Kiểm issuer, signature, SessionIndex, InResponseTo |
| Same user nhiều phiên | Hai devices với sid khác | Logout scope đúng session/sub theo policy |
| Multi-tenant cùng email | IdP A/B phát email giống nhau | Không hủy phiên sai issuer/provider |
| Refresh token revocation | AS hỗ trợ RFC 7009, revoke đúng token | Không lấy được token mới sau revoke theo policy |
| JWT access vẫn chưa exp | Resource server verify offline | Có thể còn sử dụng; cần chính sách riêng |
| Logout OP lỗi/timeout | Browser nhận lỗi, upstream không xác nhận | Không hiển thị “toàn bộ đã logout” |
| CSRF logout | Attacker chèn GET/POST không có CSRF valid | App/OP không bị forced logout trái policy |
| Lộ token qua log | Proxy ghi full logout query | Phát hiện và lọc id_token_hint/token |
| UI “Sign out everywhere” | Hứa đăng xuất mọi device/app | Chỉ hiển thị nếu toàn chuỗi có bằng chứng hỗ trợ; nếu không, giới hạn lời hứa |

Test integration cần thực hiện với **broker/IdP thật hoặc test environment**, không chỉ unit test Java. Quan sát session/cookies một cách an toàn, OP events, token refresh, các RP khác và IdP upstream. **Không đưa ID Token/access token production vào log hoặc công cụ công khai** để debug.

## 18. Troubleshooting theo từng lớp

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra đúng nơi |
| --- | --- | --- |
| Logout local xong đăng nhập lại ngay | Broker session B hoặc upstream session C còn | So session A/B/C, không chỉ app cookie |
| Spring không redirect đến OP logout | Thiếu OIDC handler, Auth không phải OIDC hoặc OP không công bố endpoint | ClientRegistration, OidcUser, Discovery |
| Broker báo invalid redirect URI | post_logout_redirect_uri chưa đăng ký hoặc {baseUrl} sai | OP client config, proxy/public URL |
| Browser về app nhưng B vẫn còn | OP logout chưa xử lý, user confirmation, sai session hint | OP logs và session store |
| Broker B đóng nhưng C vẫn còn | Không bật/không hỗ trợ upstream logout | Upstream IdP provider config, Logout URL/SAML SLO |
| Upstream C đóng, B còn | Không có upstream→broker logout notification | Upstream back-channel/SAML SLO + broker session mapping |
| Broker B đóng, app A khác còn | Không có broker→RP notification hoặc RP không nhận | Backchannel Logout URL/front-channel config |
| Front-channel logout không đóng session RP | Iframe bị CSP/SameSite/third-party cookies chặn | Browser Network, cookie, iframe errors |
| Back-channel token tới nhưng RP không logout | JWT invalid, missing sid mapping hoặc endpoint không wired | JWT verifier, iss/aud/events/jti, session registry |
| Session bị logout nhầm tenant | Dò user theo email/sub thiếu issuer/session scope | Mapping (issuer, sid/sub, client, tenant) |
| App vẫn gọi API được sau broker logout | JWT access token còn valid/accepted | Token expiry, Resource Server policy, revocation |
| Refresh token vẫn dùng được | OP không revoke theo policy hoặc offline_access | AS revocation/session policies |
| Logout loop | Callback lại bị bảo vệ/auth redirect | /signed-out permitAll, authorization rules |
| SAML upstream báo SLO invalid | Broker dùng sai NameID/SessionIndex/signature/binding | Metadata SAML, signing cert, InResponseTo |
| Logout khác nhau ở DEV/PROD | Broker realm, issuer, callback, cookies khác | Per-environment registration/trust |
| OP logout chỉ hủy một client session | Broker notification scope phụ thuộc config | OP client session/rp notification policy |
| Không thấy login prompt sau logout | Upstream có SSO cookie, remember-me hoặc reauthentication policy | Upstream IdP session/step-up settings |

### 18.1. Chẩn đoán theo thứ tự hữu ích

1. **A:** sau POST /logout, HttpSession/SecurityContext local còn không?
2. **B:** browser có được redirect tới **broker end_session_endpoint** không, OP có xác nhận đóng B không?
3. **Downstream:** các RPs khác có nhận front/back-channel notification hợp lệ và invalidate session không?
4. **C:** broker có phát hành upstream logout theo provider config không, upstream có trả outcome không?
5. **Token:** refresh tokens/access tokens/AuthorizedClient store có được cleanup/revoke theo policy không?
6. **Browser:** cookies app/broker/upstream có đúng domain/SameSite/expiry không, có một session khác còn sống không?
7. **UX:** câu thông báo đang phản ánh kết quả đã xác minh hay chỉ giả định vì HTTP 302?

Ghi log bằng **correlation ID, registrationId, issuer, client ID, session-id hash, event type, response status và timestamp**, không ghi raw tokens, session cookies, PII hay full JWT claims. Dùng telemetry từ cả ba tầng khi điều tra chứ không cố xác định một upstream event chỉ từ log của app.

## 19. Thiết kế thông điệp UX và chính sách logout

Một UX an toàn không nên dùng một nút duy nhất mang lời hứa quá rộng nếu kỹ thuật không đáp ứng:

| Tùy chọn UI | Ý nghĩa triển khai tối thiểu | Câu thông báo phù hợp |
| --- | --- | --- |
| **Đăng xuất khỏi ứng dụng** | Local logout A | “Bạn đã đăng xuất khỏi ứng dụng này.” |
| **Đăng xuất khỏi hệ thống SSO** | Local A + RP-Initiated Logout tới broker B, quan sát outcome | “Yêu cầu đăng xuất khỏi SSO đã được gửi.” hoặc xác nhận rõ khi broker báo thành công |
| **Đăng xuất khỏi IdP doanh nghiệp** | Broker upstream logout được hỗ trợ và xử lý | Chỉ xác nhận khi có bằng chứng từ upstream/protocol |
| **Đăng xuất khỏi mọi ứng dụng/thiết bị** | Tất cả OP/RP/device/token paths có cơ chế thu hồi/thông báo phù hợp | Chỉ hứa khi sản phẩm có thiết kế và kiểm chứng mức này |

**Không hiển thị “Đã đăng xuất khỏi tất cả hệ thống” sau một redirect** nếu broker không hỗ trợ upstream logout hoặc downstream notifications chỉ là best-effort. Có thể trình bày hướng dẫn: “Bạn đã đăng xuất khỏi ứng dụng. Phiên đăng nhập của nhà cung cấp danh tính có thể vẫn còn; hãy đăng xuất tại nhà cung cấp nếu cần.”

### 19.1. Chính sách reauthentication

Một số sản phẩm không muốn logout toàn bộ upstream chỉ vì người dùng đóng một app: nhân viên có thể đang dùng nhiều ứng dụng doanh nghiệp và logout upstream sẽ gây gián đoạn. Khi đó **local-only logout là lựa chọn có chủ đích**, có thông báo rõ.

Nếu mục tiêu là **shared device/kiosk** hoặc tài khoản rủi ro cao, có thể yêu cầu:

- OP logout với user confirmation phù hợp.
- Upstream logout nếu IdP hỗ trợ và được phép.
- Reauthentication/step-up với **max_age**, **prompt=login** hoặc chính sách IdP tương ứng trong lần đăng nhập sau.
- Token revocation, session duration ngắn và server-side session invalidation.
- Kiểm tra kết quả cross-browser/multi-device trong scope được cam kết.

**prompt=login** ở lần đăng nhập sau là yêu cầu xác thực lại; nó **không thay thế logout thực sự của các RP hoặc thu hồi tokens cũ**.

## 20. Checklist triển khai

- [ ] Có sơ đồ rõ **app A → OIDC broker B → upstream IdP C**, ai là RP/OP mỗi quan hệ.
- [ ] Phân biệt **local session**, **broker OP session**, **upstream IdP session**, **RP khác** và **access/refresh tokens**.
- [ ] Chính sách UI nêu chính xác phạm vi logout, không hứa toàn federation nếu không hỗ trợ.
- [ ] Spring Security local logout xóa SecurityContext/HttpSession và các session client state theo policy.
- [ ] Nếu cần broker logout, OIDC RP dùng **OidcClientInitiatedLogoutSuccessHandler** hoặc tích hợp tương đương đã kiểm chứng.
- [ ] Broker Discovery công bố **end_session_endpoint** và app dùng đúng issuer/client registration.
- [ ] **id_token_hint** nếu có là token broker cấp cho app; không dùng token upstream sai audience.
- [ ] **post_logout_redirect_uri** được đăng ký exact match, công khai HTTPS, không open redirect.
- [ ] Nếu dùng **state**, RP tạo opaque value đủ entropy/TTL và kiểm tra callback.
- [ ] Đã test browser cookie, SameSite, Secure và trusted reverse proxy/forwarded headers.
- [ ] Đã phân biệt việc OP accepted/logout với việc browser được 302 redirect.
- [ ] Các RP khác có front-channel hoặc back-channel configuration thật, không giả định notification tự động.
- [ ] Nếu dùng front-channel, đã test iframe CSP và third-party cookie restrictions.
- [ ] Nếu dùng back-channel, endpoint nhận **logout_token** và xác minh signature, iss, aud, events, iat, sub/sid, nonce prohibition và replay.
- [ ] Broker map upstream provider/issuer/session với broker session đúng scope, không chỉ dựa email.
- [ ] Broker upstream logout URL/SAML SLO/back-channel đã được bật, thỏa thuận và test cho từng IdP.
- [ ] Upstream SAML logout dùng đúng **SAML LogoutRequest/LogoutResponse**, không nhầm OIDC end_session_endpoint.
- [ ] Có fallback an toàn nếu upstream không hỗ trợ logout hoặc người dùng đóng browser.
- [ ] Đã phân biệt OIDC logout với **RFC 7009 token revocation** và kiểm lifetime JWT offline.
- [ ] Không tự tin OIDC logout sẽ thu hồi mọi access/refresh/offline tokens nếu OP không cam kết.
- [ ] Có multi-session/multi-device policy, đối chiếu sid + issuer/client; không logout nhầm tenant.
- [ ] Test negative cases: forged logout token, wrong iss/aud, missing events/sub/sid, nonce, alg=none, jti replay, wrong redirect, expired session.
- [ ] Không ghi raw ID Token, refresh token, logout_token, cookies hoặc PII vào log/traces.
- [ ] Có monitoring theo tầng A/B/C, ticket/runbook khi một tầng logout thất bại.

## 21. Câu hỏi tự kiểm tra

**1. App Spring đã xóa JSESSIONID mà người dùng vẫn SSO ngay, có phải logout local lỗi không?**

Không nhất thiết. Broker B hoặc upstream C có thể còn SSO session và tạo một phiên app mới. Kiểm từng tầng.

**2. Spring app phải gửi logout đến broker hay upstream IdP?**

Nếu app đăng nhập OIDC **trực tiếp với broker**, app thường gửi **RP-Initiated Logout đến broker OP**. Broker chịu trách nhiệm tích hợp logout với upstream theo cấu hình/protocol.

**3. end_session_endpoint khác authorization_endpoint thế nào?**

authorization_endpoint dùng bắt đầu đăng nhập/authorization; end_session_endpoint để RP yêu cầu OP chấm dứt session. Chúng là các endpoint khác chức năng.

**4. id_token_hint lấy từ đâu?**

Từ **ID Token broker cấp cho chính app RP** ở lần OIDC login trước. Không dùng access token hay upstream ID Token có issuer/audience khác.

**5. post_logout_redirect_uri có được do browser tùy ý chọn không?**

Không. Nó phải khớp exact allowlist đã đăng ký tại OP; nếu không có xác minh hợp lệ, OP không được redirect theo tham số không tin cậy.

**6. OidcClientInitiatedLogoutSuccessHandler đã tự nhận back-channel logout token chưa?**

Không nên suy như vậy. Nó dùng cho **RP-initiated logout**; nhận và xử lý OP-initiated Back-Channel Logout là luồng/endpoint khác cần hỗ trợ riêng.

**7. Broker logout thành công có bảo đảm upstream logout?**

Không. Phụ thuộc upstream Logout URL/SAML SLO/back-channel, cấu hình broker và khả năng IdP, có thể thất bại hay không được hỗ trợ.

**8. Upstream logout trực tiếp có tự xóa app session không?**

Không tự động. Cần upstream→broker notification và broker→app notification hoặc cơ chế session detection phù hợp.

**9. Front-channel và back-channel khác nhau quan trọng nhất ở đâu?**

Front-channel dùng browser/iframe và phụ thuộc cookie/CSP; back-channel gửi server-to-server Logout Token JWT đã ký tới RP endpoint, có thể hoạt động khi browser không còn.

**10. Logout Token có thể là một JWT alg=none hoặc một ID Token mang nonce không?**

Không. Theo Back-Channel Logout, token phải được ký, chứa event marker đúng, có sub/sid, **không có nonce**, và phải xác minh iss/aud/time/replay.

**11. OIDC RP-Initiated Logout có chắc chắn thu hồi mọi JWT access token đang còn hạn không?**

Không. Session logout và token revocation là các cơ chế khác nhau. JWT có thể được resource server chấp nhận tới exp nếu không có kiểm tra trạng thái/thu hồi.

**12. Tại sao người dùng đóng browser lúc logout có thể để RP khác vẫn đăng nhập?**

Front-channel thông báo phụ thuộc browser tiếp tục tải iframe/các trang logout; nếu đóng giữa chừng có thể chưa phát/nhận notification. Cần back-channel hoặc các biện pháp session policy bổ sung.

**13. IdP upstream dùng SAML có thể nhận OIDC id_token_hint để logout không?**

Không. Với SAML SLO, broker phải dùng SAML LogoutRequest/LogoutResponse, NameID/SessionIndex, signing và InResponseTo theo profile.

**14. Khi nào local-only logout là một thiết kế hợp lý?**

Khi UX chỉ muốn thoát một ứng dụng mà không làm gián đoạn các ứng dụng doanh nghiệp khác; phải nói rõ scope, chấp nhận khả năng SSO lại nhanh và quản lý token/session local an toàn.

**15. Vì sao không chỉ dùng email để xử lý back-channel logout multi-tenant?**

Email không phân biệt issuer/provider, có thể tái sử dụng và không phải session key. Cần định danh đã verified: issuer, aud/client, sub/sid và mapping session/tenant.

## 22. Tài liệu chuẩn và tham khảo chính thức

- Spring Security, **OIDC Logout** — OidcClientInitiatedLogoutSuccessHandler, end_session_endpoint, post logout redirect template: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security Javadoc, **OidcClientInitiatedLogoutSuccessHandler**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/web/logout/OidcClientInitiatedLogoutSuccessHandler.html
- Spring Security, **Logout** — local Session/Cookie/SecurityContext logout: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security, **OAuth2 Login** — ClientRegistration và OidcUser: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- OpenID Connect, **RP-Initiated Logout 1.0** — id_token_hint, client_id, state, post_logout_redirect_uri, end_session_endpoint: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect, **Front-Channel Logout 1.0** — browser/iframe, iss và sid, third-party content issues: https://openid.net/specs/openid-connect-frontchannel-1_0.html
- OpenID Connect, **Back-Channel Logout 1.0** — logout_token JWT, events, signature, sub/sid, nonce prohibition và validation: https://openid.net/specs/openid-connect-backchannel-1_0.html
- OpenID Connect, **Session Management 1.0** — OP/RP session state: https://openid.net/specs/openid-connect-session-1_0.html
- IETF, **RFC 7009 OAuth 2.0 Token Revocation** — token revocation khác browser logout: https://www.rfc-editor.org/rfc/rfc7009.html
- Keycloak, **Server Administration Guide**, mục Identity Brokering, OIDC Logout, Client Logout, IdP Logout URL/Backchannel: https://www.keycloak.org/docs/latest/server_admin/
- Keycloak, **OIDC endpoints** — RP-initiated logout và legacy token logout: https://www.keycloak.org/securing-apps/oidc-layers
- OASIS, **SAML 2.0 Profiles**, Single Logout Profile nếu upstream sử dụng SAML: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf

**Kết luận:** trong kiến trúc OIDC có môi giới, **local logout A**, **broker OIDC logout B** và **upstream IdP logout C** là **ba trạng thái riêng**, không phải ba tên gọi cho một thao tác. Spring Security có thể xóa phiên local và dùng **OidcClientInitiatedLogoutSuccessHandler** yêu cầu broker đăng xuất. Từ broker đến IdP upstream lại phụ thuộc **provider configuration, logout protocol và khả năng lan truyền sự kiện**. Để nói “đăng xuất hoàn toàn”, phải kiểm được từng phạm vi được cam kết, bao gồm **session, OIDC front/back-channel, token lifetime/revocation và các ứng dụng liên quan**.