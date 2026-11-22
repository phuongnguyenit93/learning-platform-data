# Phân biệt hỗ trợ Servlet, WebFlux và phần mở rộng bên ngoài theo giao thức

> **Chủ đề:** Spring Security – federation. **Nhóm kiến thức:** Nền tảng Spring. Bài này trả lời câu hỏi thực hành: với một giao thức SSO/federation cụ thể, Spring Security hỗ trợ trực tiếp trên **Servlet** hay **WebFlux**, phải thêm **module tích hợp**, hay phải dùng **thư viện/nền tảng bên ngoài**? Nội dung bám theo phân loại và API được tài liệu Spring Security 7.1 trình bày; dự án chạy Spring Security 6.x hoặc phiên bản khác phải kiểm tra lại đúng bản.

## 1. Ba mức "hỗ trợ" phải phân biệt

Cùng nói "Spring hỗ trợ đăng nhập SSO" có thể mang ba ý nghĩa rất khác nhau:

1. **Tính năng tích hợp chính thức trên đúng web stack:** Spring Security cung cấp thành phần xác thực và DSL thích hợp, ví dụ `HttpSecurity.oauth2Login()` hoặc `ServerHttpSecurity.oauth2Login()`. Vẫn cần đăng ký client/IdP và cấu hình mạng.
2. **Module tích hợp chuyên biệt cho Spring Security:** Một artifact cung cấp filter, provider, validator hoặc bộ cấu hình nhưng cần lắp ghép nhiều bean, chẳng hạn các thành phần CAS hoặc Spring Security Kerberos. Module không đồng nghĩa với việc mọi web stack có DSL giống nhau.
3. **Bên ngoài Spring Security ứng dụng:** Identity Provider (IdP), OpenID Provider (OP), CAS Server, KDC/Active Directory, identity broker, reverse proxy đăng nhập hoặc thư viện bên thứ ba. Spring Security có thể **nhận/kiểm** kết quả đăng nhập của một hệ thống đó mà không tự triển khai cả máy chủ giao thức.

Do đó phải trả lời **đủ bốn câu**: (1) ứng dụng là **client/SP/RP**, **API Resource Server** hay **IdP/OP/server**; (2) ứng dụng dùng **Spring MVC/Servlet** hay **Spring WebFlux**; (3) giao thức nào; (4) version Spring Security và artifact nào.

**Ví dụ phân biệt:** `saml2Login()` xác thực người dùng tại **ứng dụng Servlet đóng vai trò SAML Service Provider (SP)**; nó không làm ứng dụng trở thành SAML Identity Provider. `oauth2ResourceServer().jwt()` kiểm access token cho API, không phải chức năng OIDC login hoặc máy chủ phát token. `spring-security-kerberos-web` thêm tích hợp SPNEGO; KDC vẫn ở ngoài.

## 2. Servlet và WebFlux: hai kiến trúc bảo vệ HTTP

| Tiêu chí | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Đầu vào HTTP | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange`, publisher của Reactor |
| Chuỗi security | `SecurityFilterChain`, `FilterChainProxy` và servlet `Filter` | `SecurityWebFilterChain`, `WebFilterChainProxy` và `WebFilter` |
| DSL cấu hình | `HttpSecurity` với `authorizeHttpRequests` | `ServerHttpSecurity` với `authorizeExchange` |
| Principal / context | `SecurityContextHolder` và ngữ cảnh theo request/thread theo cơ chế framework | `ReactiveSecurityContextHolder` trong **Reactor Context** |
| Đăng nhập OIDC/OAuth2 | `oauth2Login`, `ClientRegistrationRepository` | `oauth2Login`, `ReactiveClientRegistrationRepository` |
| API Bearer JWT | `JwtDecoder`, `oauth2ResourceServer` | `ReactiveJwtDecoder`, `oauth2ResourceServer` |
| Kiểm thử security | `MockMvc` và `spring-security-test` | `WebTestClient` và `spring-security-test` |
| Rủi ro khi dùng API sai stack | Servlet `Filter` không tự chạy trong reactive chain | `WebFilter` không tự chạy trong servlet filter chain |

**Quan trọng:** Cùng có phương thức tên `oauth2Login` không có nghĩa hai stack chia sẻ mọi class và extension point. Ví dụ API servlet dùng `AuthenticationSuccessHandler` và filter servlet tương ứng; reactive dùng `ServerAuthenticationSuccessHandler` và `WebFilter`. Một filter CAS viết cho `HttpServletRequest` không thể chỉ thêm vào `SecurityWebFilterChain`.

Thêm dependency `spring-webflux` để dùng **WebClient** trong một ứng dụng MVC **không tự chuyển** phía server thành WebFlux. Khi có đồng thời các starter Spring MVC và WebFlux, Spring Boot thông thường ưu tiên MVC nếu không có cấu hình thay đổi loại ứng dụng; xác định stack server thực tế bằng dependency, kiểu application và security chain đã được tạo.

### Mốc phiên bản

Từ **Spring Security 7**, Spring Authorization Server và Spring Security Kerberos được đưa vào hệ sinh thái Spring Security chính; vẫn có artifact chức năng tương ứng và cấu hình riêng. Với Spring Security **6.x**, cần đối chiếu tài liệu nhánh 6.x vì artifact, API hoặc cơ chế tích hợp có thể khác. Nội dung bên dưới gọi "chính thức" theo **tài liệu/API của Spring Security 7.1**, không có nghĩa mọi giải pháp bên thứ ba đã được chứng nhận tương thích mọi phiên bản.

## 3. Ma trận hỗ trợ theo giao thức và vai trò

Ký hiệu: **Có** = Spring Security có API/tính năng chính thức cho stack đó; **Module** = có module chuyên dụng với bước cấu hình tích hợp; **Ngoài/Tự xây** = cần broker, reverse proxy, adapter hoặc code tùy chỉnh, không có DSL tương đương được tài liệu stack đó cung cấp.

| Giao thức / vai trò | Servlet (Spring MVC) | WebFlux reactive | Bên ngoài / phạm vi trách nhiệm |
|---|---|---|---|
| **OIDC Login (RP)** | **Có**: `oauth2Login`; OAuth2 Client | **Có**: `oauth2Login`; Reactive OAuth2 Client | Cần OP/IdP phát ID Token; cấu hình issuer, client, redirect URI |
| **OAuth2 Client** gọi API | **Có**: `oauth2Client`, authorized-client manager | **Có**: `oauth2Client`, reactive authorized-client manager | Cần Authorization Server/token endpoint |
| **OAuth2 Resource Server** JWT/opaque | **Có**: `oauth2ResourceServer` | **Có**: `oauth2ResourceServer` | Cần issuer/JWKS hoặc introspection server; đây là kiểm token API |
| **OAuth2/OIDC Authorization Server** | **Module/chức năng server chuyên biệt** trên Servlet | **Không có nhánh WebFlux tương đương trong tài liệu chính thức hiện hành** | Spring Authorization Server / OP bên ngoài; không nhầm RP với OP |
| **SAML 2.0 SP (login)** | **Có**, module `spring-security-saml2-service-provider`, `saml2Login` | **Ngoài/Tự xây**; không có `ServerHttpSecurity.saml2Login` tương đương | Cần SAML IdP và metadata/chứng thư/ACS; broker nếu app WebFlux |
| **SAML IdP** | Không phải chức năng `saml2Login` của Spring Security SP | Không có chức năng IdP SAML từ `oauth2Login` | Dùng IdP như Keycloak, AD FS, Entra ID, Apereo CAS khi có hỗ trợ SAML |
| **CAS protocol (service)** | **Module/tích hợp Servlet**: `spring-security-cas` và CAS client ticket validator | **Ngoài/Tự xây**; không có CAS DSL reactive tương đương trong reference | Cần CAS Server, đăng ký `service`, xác minh Service Ticket |
| **Kerberos/SPNEGO vào web app** | **Module**: Spring Security Kerberos (7.x: `spring-security-kerberos-core/web`) kết nối servlet filter/provider | **Ngoài/Tự xây**; không có WebFlux SPNEGO DSL tương đương | Cần KDC/AD, SPN, keytab, cấu hình browser/proxy |
| **Xác thực AD/LDAP qua username/password** | Các provider/tích hợp danh bạ tương ứng | Có thể tích hợp reactive auth/LDAP theo API/phương án được hỗ trợ | **LDAP không mặc định là Kerberos/SSO** |
| **Broker chuyển SAML/CAS/Kerberos → OIDC** | App **OIDC RP** bằng `oauth2Login` | App **OIDC RP** bằng `oauth2Login` | Broker xử lý giao thức upstream và phát token OIDC cho app |

**Cách đọc ma trận:** "Có OIDC trên WebFlux" không kéo theo "có SAML/CAS/Kerberos native trên WebFlux"; "SAML module chạy trong JVM" không kéo theo "SAML filter chạy được như reactive `WebFilter`"; "Spring Security có Authorization Server" không kéo theo "một ứng dụng đã dùng `oauth2Login` có thể cấp ID Token cho ứng dụng khác".

## 4. OpenID Connect/OAuth2: trường hợp hỗ trợ trên cả hai stack

### 4.1. Phân biệt ba vai trò OAuth2/OIDC

- **OIDC Relying Party (RP):** ứng dụng web chuyển trình duyệt đến OP, nhận authorization code, đổi token, kiểm **ID Token** và tạo phiên người dùng. Cả Servlet và WebFlux đều có `oauth2Login`.
- **OAuth2 Client:** ứng dụng xin/giữ access token để gọi resource server khác. Cả hai stack có `oauth2Client`; API/manager là phiên bản synchronous hoặc reactive.
- **OAuth2 Resource Server:** backend nhận `Authorization: Bearer ...` và **kiểm access token** theo issuer, signature, audience, expiry và quyền. Cả hai stack có `oauth2ResourceServer` với JWT hoặc opaque-token introspection.

`id_token` là bằng chứng định danh **dành cho RP**; không tự dùng như access token gọi API. Với OIDC Login, nên dùng Authorization Code + PKCE khi phù hợp; kiểm `state`, redirect URI đã đăng ký, ID Token, issuer/audience và xử lý session/logout rõ ràng.

### 4.2. Ví dụ Servlet — cấu hình OIDC và SAML SP

Đoạn Java sau là **một class Spring Security cấu hình trong dự án Spring Boot Servlet**, có thể biên dịch khi đã thêm dependency phù hợp. Cần ít nhất `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client` và `spring-security-saml2-service-provider` tương thích với Spring Boot hiện tại. Muốn đăng nhập thực cần cấu hình cả OIDC client và SAML relying party hợp lệ (xem mục 5).

Tệp `src/main/java/com/example/security/ServletSsoSecurity.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletSsoSecurity {

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Vì sao đúng stack:** `HttpSecurity` tạo `SecurityFilterChain` chạy với Servlet `Filter`. `oauth2Login` dùng OAuth2/OIDC client registration; `saml2Login` dùng SAML relying-party registration. Đây là hai lựa chọn xác thực khác nhau và đều có thể dẫn về một `Authentication` để ứng dụng phân quyền. Việc ghép cả hai vào một ứng dụng có thể dẫn đến trang chọn cơ chế login; hành vi chính xác phụ thuộc số lượng registration và login page.

### 4.3. Ví dụ WebFlux — OIDC và API Bearer JWT

Đoạn sau thuộc **một dự án WebFlux riêng**, không bỏ chung class Servlet ở trên. Dependency thường là `spring-boot-starter-webflux`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client` và `spring-boot-starter-oauth2-resource-server`.

Tệp `src/main/java/com/example/security/ReactiveSsoSecurity.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSsoSecurity {

    @Bean
    SecurityWebFilterChain appSecurity(ServerHttpSecurity http) {
        http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/public", "/error").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Vì sao đúng stack:** `ServerHttpSecurity` cấu hình `SecurityWebFilterChain` thay cho Servlet filter. `oauth2Login` bảo vệ yêu cầu của người dùng qua OP; `oauth2ResourceServer().jwt()` kiểm Bearer token của API. Với cùng một đường dẫn, cần kiểm tra cơ chế chọn `AuthenticationEntryPoint` (redirect HTML hay HTTP 401) để không vô tình redirect client API; thường tách chain cho `/api/**` và phần web.

Ví dụ cấu hình OIDC client (dùng cho **một** trong hai project; ở WebFlux Boot tạo reactive client registration):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: demo-client-id
            client-secret: REPLACE_USING_SECRET_MANAGER
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: https://login.example.org/realms/corp
~~~

Muốn dùng JWT Resource Server như ở ví dụ WebFlux trên, thêm cấu hình issuer của **access token API**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/corp
~~~

Hai khối YAML trên **là các đoạn bổ sung trong cùng cây cấu hình**, cần hợp nhất dưới nút `spring.security.oauth2` nếu đặt trong một tệp. Các domain/ID/secret đều là ví dụ; lưu secret qua secret manager/biến môi trường, không commit giá trị thật. Kiểm audience cho API nếu issuer/JWT mặc định chưa kiểm điều kiện ứng dụng yêu cầu.

Lệnh chạy dự án Maven Boot có Maven Wrapper (mỗi project đã khai báo dependency đúng):

~~~bash
./mvnw spring-boot:run
~~~

Không có stdout/danh tính cố định: login thực phụ thuộc OP, đăng ký client, tài khoản, mạng và chính sách IdP. Nếu app không có client registration hợp lệ, gọi `oauth2Login` không đủ để hoàn thành luồng đăng nhập.

### 4.4. Khác biệt lớp và extension point thường gặp

| Nhu cầu | Servlet | WebFlux |
|---|---|---|
| Chuỗi bảo vệ | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Khai báo request rule | `authorizeHttpRequests` / `requestMatchers` | `authorizeExchange` / `pathMatchers` |
| OAuth2 registration | `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| Quản lý authorized client | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Client HTTP tiêu biểu | `RestClient` hoặc `WebClient` phù hợp cấu hình | `WebClient` reactive |
| Context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Filter mở rộng | `OncePerRequestFilter`/Servlet `Filter` | `WebFilter`, reactive authentication manager |

Đối tượng chung như `Authentication` hoặc `GrantedAuthority` **không** chứng minh integration có thể dùng chéo stack; điểm nối HTTP, persistence/security context và kiểu xử lý async/reactive vẫn khác.

## 5. SAML 2.0: hỗ trợ SP chính thức ở Servlet

### 5.1. Vùng được Spring Security giải quyết

Spring Security SAML 2.0 hướng tới **Service Provider (SP/Relying Party) cho web SSO**. Thư viện `spring-security-saml2-service-provider` cung cấp luồng SAML HTTP-Redirect/POST, giải mã/kiểm SAML Response, quản lý `RelyingPartyRegistration`, metadata SP và cơ chế login/logout khi cấu hình.

Các thành phần dễ nhận diện:

- `HttpSecurity.saml2Login(Customizer.withDefaults())`.
- `RelyingPartyRegistrationRepository` lưu cấu hình SP ↔ IdP.
- `Saml2WebSsoAuthenticationRequestFilter` chuẩn bị `AuthnRequest`.
- `Saml2WebSsoAuthenticationFilter` nhận response tại ACS.
- Tích hợp OpenSAML phục vụ xử lý XML/signature/assertion.

Cấu hình Spring Boot mẫu, phải thay metadata đúng IdP và đăng ký SP tại đó:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp-saml:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
~~~

Endpoint mặc định có thể gồm `/saml2/authenticate/{registrationId}` và `/login/saml2/sso/{registrationId}`; endpoint metadata SP cần bật tính năng `saml2Metadata` theo cấu hình. Cần đối chiếu ACS URL/entity ID, certificate và proxy URL.

### 5.2. Những điều Spring Security không tự đảm nhiệm

- **Không phải SAML IdP**: cần IdP bên ngoài xác thực người dùng và ký assertion.
- **Không tự tin cậy mọi IdP**: phải quản lý metadata, signing keys/certificates, issuer/audience/recipient, thời hạn assertion, chống replay và rotation.
- **Không có `ServerHttpSecurity.saml2Login()` tương đương trong tài liệu WebFlux 7.1**. Thêm SAML service provider JAR vào ứng dụng WebFlux không biến servlet `Saml2WebSsoAuthenticationFilter` thành `WebFilter`.
- **Không mặc nhiên có single logout toàn hệ thống**: kiểm SLO/phiên local/IdP theo khả năng và cấu hình của cả hai đầu.

Nếu **web app thuần WebFlux** phải dùng SAML IdP của đối tác, lộ trình thường ít rủi ro hơn là cho **broker** tin IdP SAML và phát OIDC cho WebFlux, hoặc dùng một **ứng dụng Servlet SAML SP chuyên biệt** làm tầng xác thực rồi phát hành credential riêng có kiểm chứng cho downstream. Tự viết reactive SAML SP đòi hỏi xử lý chuẩn XML Security, state, signature/response/cert và SLO đầy đủ; không nên xem đây là một filter chuyển kiểu đơn giản.

## 6. CAS: tích hợp Service Ticket ở Servlet; CAS Server là hệ thống riêng

**CAS protocol** khác OIDC và SAML: service nhận một **Service Ticket (ST)** trên callback; backend xác minh ticket với CAS Server qua HTTPS và đúng `service` URL, thường ST dùng một lần.

Trên Servlet, Spring Security có tích hợp CAS qua module/thành phần:

- `CasAuthenticationEntryPoint`: chuyển trình duyệt đến trang đăng nhập CAS.
- `CasAuthenticationFilter`: nhận callback có `ticket`.
- `CasAuthenticationProvider`: phối hợp `TicketValidator` với thư viện CAS Client.
- `ServiceProperties`: định nghĩa URL dịch vụ phải khớp khi validate.
- `Cas20ServiceTicketValidator`/proxy validator từ thư viện tương thích khi cần.

Luồng cơ bản:

~~~text
Servlet app ----redirect----> CAS Server /login?service=...
Browser <---SSO cookie------> CAS Server
CAS Server ----ST---------> Browser ----ticket----> Servlet callback
Servlet backend ----HTTPS validation (ticket + service)---> CAS Server
Servlet app <--------CAS response (user/attributes)---------
Servlet app tạo Authentication + session riêng
~~~

**Hạn chế của WebFlux:** tài liệu WebFlux chính thức không có DSL `casLogin` hoặc filter reactive tương ứng. `CasAuthenticationFilter` phụ thuộc servlet request/filter contract; không cắm trực tiếp vào `ServerHttpSecurity`. Có thể dùng adapter bên thứ ba **nếu được xác minh hỗ trợ WebFlux và bản CAS protocol tương ứng**, hoặc đưa CAS Server/broker cấp OIDC cho reactive app. CAS Server hiện đại có thể cung cấp OIDC/SAML thông qua module của **chính CAS Server**; sự tồn tại module đó **không biến CAS protocol thành OIDC**.

**Cần kiểm:** service URL trùng chính xác, ticket không tái dùng, TLS, session/logout, CAS proxy ticket nếu có (chỉ cho phép proxy tin cậy), và mapping authorities. Một ứng dụng chỉ dùng OAuth2 client không xác minh CAS ST theo CAS protocol.

## 7. Kerberos/SPNEGO: module đặc biệt cho Servlet và hạ tầng domain

Kerberos là giao thức ticket dựa trên **KDC**, TGT, service ticket, realm và principal. Với HTTP SSO, **SPNEGO/Negotiate** mang thông tin Kerberos trong HTTP authorization exchange. Ứng dụng thường nhận `Authorization: Negotiate ...`; server cần service principal như `HTTP/app.example.org@EXAMPLE.ORG` và khóa phù hợp (keytab).

Trong Spring Security 7.x, Kerberos là phần của hệ sinh thái Spring Security với artifact:

~~~xml
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
~~~

Khai báo phiên bản bằng BOM/dependency management Spring Security/Boot tương thích. Ví dụ những lớp tích hợp: `SpnegoAuthenticationProcessingFilter`, `SpnegoEntryPoint`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`. Các lớp liên quan **Servlet security filter/AuthenticationProvider**, cần lắp filter vào chain, cấu hình service principal/keytab và kết nối realm thực; không có "chỉ bật `kerberosLogin()` là đủ" trong DSL chính.

Với Spring Security 6.x, Kerberos từng là **extension với tọa độ và chu kỳ phiên bản riêng**; khi nâng lên 7.x cần đối chiếu mục migration/giới thiệu Kerberos. Một số ví dụ tài liệu cũ sử dụng cú pháp cấu hình `.and()` hoặc API đã đổi; tránh copy nguyên vào project mới mà không biên dịch trên dependency đang khóa.

**WebFlux:** tài liệu chính thức không cung cấp cặp `ServerHttpSecurity.kerberosLogin`/reactive SPNEGO filter tương đương. Một số giải pháp triển khai giao thức ở reverse proxy/gateway chạy trước WebFlux rồi chuyển danh tính qua token/claim được bảo vệ; hoặc broker lấy Kerberos ở upstream và phát OIDC. Chuyển tự do header `X-User: alice` từ client internet vào app **không được xem là xác thực**: proxy phải xóa header giả từ client, xác thực nguồn kết nối upstream, ký/ràng buộc claim hoặc dùng mTLS/token phù hợp.

Các điều kiện tích hợp Kerberos bắt buộc thuộc hệ thống: KDC/AD, DNS, SPN, keytab, encryption types, đồng bộ thời gian, trình duyệt cho phép Negotiate và trust realm. Spring Security không tạo KDC hoặc sửa cấu hình domain giúp bạn.

## 8. Ngoài phần mềm lõi: IdP, Authorization Server, broker và third-party adapter

### 8.1. Vai trò server khác vai trò client

| Vai trò | Ai chịu trách nhiệm | Spring Security đóng góp |
|---|---|---|
| **SAML IdP** | IdP chuyên dụng ký assertion và quản lý phiên SSO | Servlet SAML SP **tiêu thụ** assertion đã xác minh |
| **OIDC OP / OAuth Authorization Server** | Hệ thống phát authorization code, ID/access token, public keys | Servlet có **Spring Security Authorization Server** khi dựng server, hoặc chọn OP ngoài; cả Servlet và WebFlux có client/resource-server |
| **CAS Server** | Cấp/kiểm ticket, giữ TGC/TGT, chính sách SSO | Servlet CAS integration là **service consumer** |
| **Kerberos KDC** | Cấp TGT/service tickets, quản trị principal | Servlet Kerberos integration **tiếp nhận/kiểm** Kerberos/SPNEGO khi được cấu hình |
| **Identity broker** | Ánh xạ upstream SAML/CAS/Kerberos sang downstream OIDC/SAML theo chính sách | App sử dụng giao thức downstream đã có support trên stack |
| **Provisioning / SCIM** | Đồng bộ tài khoản và lifecycle | Đăng nhập được không đồng nghĩa tự cấp/xóa tài khoản đúng thời điểm |

Spring Security Authorization Server cung cấp chức năng server OAuth2/OIDC theo **Servlet** và có dependency độc lập; đừng nhầm với `spring-boot-starter-oauth2-client`, `spring-boot-starter-oauth2-resource-server` hoặc `spring-security-saml2-service-provider`. Một ứng dụng WebFlux cần OP có thể đăng nhập vào **Authorization Server chạy riêng ở Servlet** hoặc dịch vụ IdP bên ngoài; WebFlux app vẫn là RP.

### 8.2. Khi nào dùng thư viện ngoài?

Một adapter bên ngoài chỉ đáng chọn sau khi xác định rõ:

1. Có hỗ trợ **đúng framework** (Servlet `Filter` hay WebFlux `WebFilter`) và **đúng phiên bản** Spring Framework/Security/Boot.
2. Tính năng thực sự hỗ trợ **vai trò** mong muốn (SAML SP hay IdP; CAS ticket validator hay CAS Server; Kerberos acceptor hay Kerberos client).
3. Kiểm tra signing/cert/nonce/replay/redirect/issuer/audience và security context tích hợp đúng.
4. Hỗ trợ session, CSRF, logout, MFA, error path và logging; cơ chế nâng cấp/patch được duy trì.
5. Không chặn event loop bằng network/disk/JAAS call blocking trong reactive chain; nếu không tránh được thì kiến trúc offload/gateway cần được đánh giá tải và kiểm soát timeout.
6. Có kiểm thử tích hợp end-to-end với IdP thật và kiểm thử negative path, không chỉ "build thành công".

Tuyệt đối không gọi "Spring Security native reactive SAML/CAS/Kerberos" chỉ vì một starter tùy biến hoặc bên thứ ba đưa ra class cùng tên.

## 9. Ba kiến trúc tham khảo và cách chọn

### A. Servlet monolith dùng SAML của đối tác

~~~text
Browser -> Spring MVC + SAML SP -> SAML IdP
              |
              +-> HttpSecurity.saml2Login()
              +-> RelyingPartyRegistration/metadata + ACS
              +-> Authentication -> service authorization
~~~

**Chọn khi:** yêu cầu SAML trực tiếp, ứng dụng đã là Spring MVC/Servlet, cần ACS/metadata/SLO. **Tránh hiểu nhầm:** sử dụng OpenSAML vẫn phải có SAML IdP tin cậy.

### B. WebFlux app dùng OIDC trực tiếp

~~~text
Browser -> WebFlux app -> OIDC Provider
                 |
                 +-> SecurityWebFilterChain.oauth2Login()
                 +-> ReactiveClientRegistrationRepository
                 +-> Session/security context trong reactive flow

HTTP API client -> WebFlux API -> oauth2ResourceServer().jwt()
                                  -> ReactiveJwtDecoder / authorities
~~~

**Chọn khi:** IdP hỗ trợ OIDC và ứng dụng là WebFlux, API cần Bearer token. Tách chính sách session-login và Bearer API theo endpoint, tránh chuyển API client về trang đăng nhập tương tác.

### C. Nhiều giao thức legacy đi qua broker

~~~text
Windows workstation --Kerberos/SPNEGO--+
                                      |
Partner SAML IdP -----SAML------------+--> Identity Broker / Gateway
                                      |       |
Legacy CAS Server ----CAS-------------+       +--> OIDC OP endpoints
                                              |
                                              +--> Spring MVC OIDC RP
                                              +--> Spring WebFlux OIDC RP
                                              +--> Resource Server APIs
~~~

**Chọn khi:** có nhiều nguồn danh tính và nhiều ứng dụng (đặc biệt có WebFlux). Broker **phát credential mới** có issuer/audience/key/lifetime rõ ràng; không tái dùng SAML assertion hay CAS ST như Bearer token của API. Gateway phải bảo vệ downstream trước header giả, giữ đúng trust boundary, session/logout và audit.

## 10. Quy trình quyết định cho một ứng dụng mới

Bắt đầu bằng **giao thức thực tế từ nhà cung cấp danh tính**, sau đó áp dụng cây quyết định:

1. **Ứng dụng là OIDC client hay OAuth2 Resource Server?** Cả Servlet và WebFlux có hỗ trợ chính thức. Chọn theo kiến trúc web, không theo giao thức.
2. **Ứng dụng cần nhận SAML Response trực tiếp?** Servlet SP là lựa chọn được Spring Security document; WebFlux nên ưu tiên broker/Servlet facade nếu tổ chức có lựa chọn.
3. **Ứng dụng legacy bắt buộc nhận CAS ST?** Dùng tích hợp Servlet CAS; WebFlux cần phương án ngoài/cầu nối được kiểm chứng.
4. **Bắt buộc HTTP Kerberos Negotiate?** Với Servlet cân nhắc Kerberos module + hạ tầng; với WebFlux cân nhắc gateway/IdP broker và kiểm trust.
5. **Ứng dụng phải làm SAML IdP, CAS Server, KDC hoặc OIDC OP?** Đó là **vai trò server riêng**, không suy ra từ việc app có login/client. Chọn IdP/CAS/KDC/Authorization Server đúng mục đích.
6. **Có thể chọn một giao thức downstream dùng chung?** OIDC thường thuận tiện cho Spring MVC và WebFlux; đánh giá điều kiện khách hàng, security team và quản trị lifecycle.

**Đừng chọn WebFlux chỉ vì "SSO nhanh hơn"**: tần suất chuyển hướng browser, truy cập OP, JWK fetching, backend session và signature verification có chi phí riêng; hiệu năng network/reactive tùy workload. WebFlux phù hợp khi toàn ứng dụng cần xử lý I/O reactive, đồng thời cần thư viện bảo mật tương thích.

## 11. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường thấy | Hướng khắc phục |
|---|---|---|
| `Cannot resolve method saml2Login` trên `ServerHttpSecurity` | Dùng API reactive, SAML login DSL dành cho Servlet | Chọn Servlet SP hoặc broker SAML→OIDC |
| `CasAuthenticationFilter` không gắn được vào WebFlux | CAS filter triển khai Servlet `Filter` | Dùng Servlet CAS module hoặc reactive adapter/gateway đã kiểm chứng |
| `SpnegoAuthenticationProcessingFilter` không xử lý `ServerWebExchange` | Kerberos web integration dựa trên Servlet | Dùng integration đúng stack hoặc xử lý Negotiate upstream |
| App Spring MVC cấu hình `SecurityWebFilterChain` nhưng không chạy | Stack server là Servlet | Dùng `SecurityFilterChain` + `HttpSecurity` |
| App WebFlux khai báo `SecurityFilterChain` Servlet | Sai chain type; thiếu cấu hình WebFlux bảo vệ route | Dùng `SecurityWebFilterChain` + `ServerHttpSecurity` |
| Thêm `spring-webflux` rồi tưởng SAML Servlet chuyển thành reactive | `WebClient` là thư viện HTTP client, không đổi server runtime | Kiểm tra app type/chain trên runtime, không suy luận theo dependency lẻ |
| API nhận OIDC `id_token` làm Bearer token | Nhầm xác thực RP với ủy quyền API | Resource Server kiểm **access token** có audience/scope hợp lệ |
| Token JWT xác minh chữ ký nhưng vẫn bị sai quyền | Chưa validate issuer/audience/role mapping | Bổ sung validator, giới hạn tenant/scope và quyền nội bộ |
| CAS ticket hợp lệ nhưng service validation thất bại | URL `service` lệch scheme/host/path hoặc ST đã dùng | Khớp URL chính xác, chỉ validate ST một lần |
| Kerberos lặp 401 Negotiate | SPN/keytab/KVNO/DNS/realm/browser/clock sai | Kiểm tra KDC, ticket, SPN, keytab, trust và HTTP headers |
| WebFlux đứng/hết throughput khi xác thực | Adapter ngoài gọi blocking I/O trực tiếp trong event loop | Dùng integration reactive thực hoặc chuyển verification sang gateway/worker pool phù hợp |
| Logout tại app nhưng vẫn login lại ngay | IdP/CAS/Kerberos upstream còn phiên/ticket | Thiết kế local vs provider logout và kiểm đủ các bên |

## 12. Checklist kiểm thử/đánh giá tích hợp

### 12.1. Kiểm dependency và API trước khi chạy

- Ghi lại phiên bản **Java, Spring Boot, Spring Framework, Spring Security** và platform Maven/Gradle.
- Tìm đúng loại chain/HTTP DSL: `SecurityFilterChain/HttpSecurity` hay `SecurityWebFilterChain/ServerHttpSecurity`.
- Kiểm artifact **theo vai trò**: OAuth2 client/resource server, SAML service provider, CAS, Kerberos core/web; đừng sao chép phụ thuộc Spring 6 sang Spring 7 mà không kiểm phiên bản.
- Xác minh nơi cung cấp **IdP/OP/CAS Server/KDC** và ai quản lý metadata, issuer, khóa/chứng thư, domain và cấp tài khoản.
- Không nhầm API client `WebClient` với ứng dụng server WebFlux.

### 12.2. Kiểm hành vi xác thực và phân quyền

- **Đường thành công:** redirect/challenge đúng, xác thực tại hệ thống ngoài, callback có state/ticket/response đúng; principal và roles được ánh xạ chính xác.
- **Đường lỗi:** issuer/audience sai, token/assertion hết hạn, signature không hợp lệ, replay, CAS ST dùng lại, SPN/keytab sai, redirect/ACS/service URL lệch đều bị từ chối.
- **API:** Bearer token sai audience/scope trả 401/403 phù hợp; user session web không tự cấp quyền gọi mọi API.
- **Session/logout:** kiểm local session, IdP SSO session, refresh-token expiry, SAML/CAS logout nếu có, ticket Windows còn tồn tại và tình trạng tài khoản đã bị khóa.
- **Proxy:** kiểm TLS, forwarded headers tin cậy, Host/external URL, không chấp nhận identity headers do client tự gửi.
- **WebFlux:** test concurrent load và block detection khi dùng adapter ngoài; không thực hiện network blocking trên event loop.

Công cụ test quen thuộc: `spring-security-test` cùng `MockMvc` cho Servlet và `WebTestClient` cho WebFlux. Mock authentication/JWT giúp test rule ứng dụng nhưng **không thay được integration test thực** với IdP, SAML metadata, CAS Server hoặc Kerberos KDC.

## 13. Nhớ nhanh bằng ba quy tắc

1. **Xác định stack trước:** `HttpSecurity` → Servlet; `ServerHttpSecurity` → WebFlux. Không trộn filter, security context hoặc manager cho hai stack.
2. **Xác định vai trò:** OAuth2 client/Resource Server/Authorization Server khác nhau; SAML SP khác SAML IdP; CAS service khác CAS Server; Kerberos HTTP acceptor khác KDC.
3. **Xác định mức support:** OIDC/OAuth2 client & resource server có ở cả hai stack; SAML SP và CAS tập trung Servlet; Kerberos SPNEGO dùng module servlet chuyên biệt. Với WebFlux và các giao thức legacy, cân nhắc broker/gateway hoặc adapter reactive được kiểm chứng.

## 14. Tài liệu chính thức dùng kiểm tra

Nguồn tham khảo ưu tiên theo **đúng nhánh version** trước khi viết code sản xuất:

- Spring Security Reference – Servlet: https://docs.spring.io/spring-security/reference/servlet/index.html
- Spring Security Reference – Reactive/WebFlux: https://docs.spring.io/spring-security/reference/reactive/index.html
- Servlet OAuth2 Client/Login/Resource Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/
- Reactive OAuth2 Client/Login/Resource Server: https://docs.spring.io/spring-security/reference/reactive/oauth2/
- API `HttpSecurity`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
- API `ServerHttpSecurity`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Servlet SAML2: https://docs.spring.io/spring-security/reference/servlet/saml2/index.html
- Servlet CAS Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Servlet Kerberos: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Spring Security 7 What's New (Kerberos/Authorization Server modules): https://docs.spring.io/spring-security/reference/7.0/whats-new.html
- Spring Security Authorization Server: https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/getting-started.html

**Lưu ý tính thời điểm:** matrix phản ánh API/tài liệu Spring Security 7.1 tại thời điểm biên soạn. Khi bảo trì hoặc nâng bản, đối chiếu JavaDoc và reference của **phiên bản cài thật**; hỗ trợ từ adapter bên ngoài không phải cam kết từ Spring Security.
