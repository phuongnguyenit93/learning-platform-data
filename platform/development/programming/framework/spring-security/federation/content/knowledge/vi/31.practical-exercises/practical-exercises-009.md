# Bảo vệ ứng dụng sau gateway xác thực và kiểm chứng chống giả mạo header

> **Module:** Spring Security – federation. **Nhóm:** Thực hành tổng hợp. Bài Knowledge README này xây dựng một tình huống end-to-end: ứng dụng Spring Boot chạy phía sau **authentication gateway** (OIDC/SAML2/enterprise SSO), vừa phải chấp nhận danh tính đã xác minh đúng cách vừa phải **từ chối yêu cầu giả mạo các HTTP identity/forwarding headers**. Phần thực hành có kiến trúc, cấu hình, ví dụ Java 17 chạy độc lập, Spring Security API Resource Server, phương án pre-authentication có giới hạn, NGINX/Cloud Gateway, test matrix, hướng dẫn quan sát và tiêu chí nghiệm thu.

## 1. Mục tiêu và kết luận an ninh

Bạn sẽ biết cách:
1. Chỉ ra ranh giới **browser → gateway → ứng dụng**, phân biệt người dùng cuối với danh tính của chính gateway.
2. Phân biệt **authentication at gateway**, **authentication at backend** và **authorization at resource**.
3. Chọn giữa **JWT access token hoặc JWT nội bộ được backend tự xác minh** và **pre-authenticated identity header**.
4. Xóa/ghi đè mọi `X-Authenticated-*`, `X-Remote-User`, `X-Forwarded-User`, `Forwarded` và `X-Forwarded-*` do client khai.
5. Chặn truy cập trực tiếp vào backend bằng network boundary, firewall/Kubernetes NetworkPolicy và nếu cần mTLS/workload identity.
6. Giữ đúng `iss`, `aud`, `exp`, `nbf`, `sub`, permission scopes và identity/tenant linking.
7. Không biến một chuỗi role trong HTTP header thành `ROLE_ADMIN`.
8. Kiểm tra callback OIDC `redirect_uri`, SAML Assertion Consumer Service, `Destination`, `Recipient` và cookies khi gateway terminate HTTPS.
9. Viết positive/negative tests chứng minh việc gửi forged identity header, bearer token hoặc forwarding header **không** nâng quyền.
10. Đưa hệ thống vào vận hành với metrics, fail-closed behavior, key rotation và release gates.

**Thông điệp quan trọng nhất:** **Gateway đăng nhập thành công không có nghĩa backend được phép tin mọi header của request.** Một header `X-Authenticated-User: admin` là chuỗi text mà client cũng có thể tự gửi. Chỉ khi gateway đã **loại bỏ dữ liệu do client cung cấp**, xác thực người dùng, tạo identity evidence mới và backend **chỉ chấp nhận đường đi/gateway đáng tin** thì dữ liệu đó mới có khả năng trở thành đầu vào cho Spring Security.

## 2. Đề bài thực hành: một cổng SSO, hai tài nguyên

Ứng dụng mẫu:
- Gateway công khai: `https://portal.example.test`.
- Backend Spring Boot riêng tư: `http://orders-api.private:8080`, chỉ gateway được kết nối; trên môi trường yêu cầu zero-trust dùng mTLS giữa hai bên.
- IdP test: `https://identity.example.test`, hỗ trợ OIDC; có thể thay bằng SAML2 IdP tại gateway mà không đổi trust contract của backend.
- API endpoint `GET /api/reports/{id}` yêu cầu `SCOPE_reports.read`.
- API endpoint `POST /api/reports/{id}/approve` yêu cầu business privilege được phê duyệt và tenant ownership.
- User test: `alice-1001`, quyền đọc report tenant-a; `admin-test` có quyền approve theo allowlist.
- Attacker thử gửi `X-Authenticated-User: admin-test` hoặc `X-Authenticated-Roles: ROLE_ADMIN` từ Internet.
- Network policy cấm attacker gọi trực tiếp `orders-api.private:8080`.
- IdP/Gateway có key rotation và logs chứa trace ID, không chứa token hay raw SAMLResponse.

### 2.1. Hai lớp bằng chứng phải tách

**Gateway-to-backend authenticity:** request thực sự đến từ workload gateway đã được cho phép (network ACL/mTLS, không phải `X-Forwarded-For`).

**End-user identity proof:** gateway đã xác minh login và backend nhận được **evidence có thể kiểm** (JWT) hoặc một identity header **chỉ khả dụng qua kênh pre-auth đủ an toàn**.

Một mTLS connection chỉ chứng minh **gateway workload** đang gọi backend, không tự cho biết Alice là ai. Một JWT hợp lệ có thể chứng minh token được IdP/gateway phát cho audience cụ thể; nó không tự kiểm tenant ownership và account activation. Cần cả chain.

## 3. Kiến trúc khuyến nghị: backend kiểm JWT

~~~text
           Browser / API client (UNTRUSTED)
                | HTTPS
                | may send forged identity headers
                v
        Public Gateway / Reverse Proxy
        -----------------------------------------
        Authenticates user via OIDC or SAML2
        Validates state/nonce/SAML signatures
        Sanitizes identity + forwarding headers
        Restricts public hosts, routes, redirects
        Sends approved access token to backend
                | private network or mTLS
                | Authorization: Bearer <signed access token>
                v
          Spring Security Resource Server
          -----------------------------------------
          Validates signed JWT via trusted issuer/JWKS
          Validates exp, nbf, iss, REQUIRED aud
          Maps only allowed scopes/permissions
          Authorizes URL, method, tenant, resource
          Ignores X-Authenticated-* for login
                |
                v
             Business resources
~~~

**Ưu điểm:** Backend không dựa vào `X-Authenticated-User` để tạo Authentication. Nếu ai đó gửi header này cùng một JWT dành cho Alice, identity được xác định bằng **validated token**; raw header không thể đổi subject thành Admin.

**Điều kiện:** Gateway phải thực sự nhận được **access token dành cho backend API**, có audience phù hợp. `TokenRelay` không tự bảo đảm rằng token dành đúng audience; nếu access token chỉ dành cho gateway hoặc một API khác, cần token exchange hoặc gateway phát JWT nội bộ đúng chuẩn, được backend trust theo issuer policy. Không dùng ID Token làm API access token.

### 3.1. Phương án B: gateway phát JWT nội bộ

Gateway đã xác thực SAML2 hoặc OIDC, sau đó một token service được ủy quyền phát **JWT ngắn hạn có audience riêng cho orders-api**:
- `iss`: định danh internal token issuer đã được backend whitelist.
- `sub`: stable identity đã liên kết từ IdP, không dựa email tự khai.
- `aud`: `orders-api`.
- `iat/nbf/exp`: thời gian ngắn và checked clock skew.
- `scope`/permissions: đã được approved theo policy, không copy mọi group gốc.
- `jti`: ID định danh token, phục vụ audit/revocation/replay policy nếu được triển khai.
- `kid`: chỉ chọn key trong trusted issuer JWKS, không tải arbitrary JWK URL.
- `act`/actor chain khi token exchange contract yêu cầu.

Gateway giữ signing private key trong KMS/HSM hoặc secret manager; backend chỉ có issuer/JWKS public verification. Key rotation có overlap/rút key. JWT ký đúng **không thay local account/tenant checks**.

### 3.2. Phương án C: pre-authenticated header có điều kiện

Một số hệ thống cũ dùng:
~~~http
X-Verified-Subject: alice-1001
X-Verified-Issuer: urn:example:trusted-idp
~~~

Spring có `RequestHeaderAuthenticationFilter` và `PreAuthenticatedAuthenticationProvider` để xử lý pre-authentication; đây là **framework**, không phải cơ chế chứng minh header đến từ gateway.

Chỉ chấp nhận kiểu này khi **đồng thời**:
- Gateway xác thực user bằng IdP đã tin.
- Edge xóa incoming identity headers trước auth.
- Gateway tái tạo header từ trusted auth session/result.
- Direct backend access bị chặn kể cả từ workload không được phép.
- Backend xác định gateway workload thực qua mTLS/approved upstream identity hoặc network control đáng tin.
- Header không thể đi qua bypass ingress/service mesh path khác.
- Backend tải entitlements từ approved source và áp policy theo user+issuer+tenant.
- Failure/missing/duplicate headers → fail closed.
- Không trust raw `X-Authenticated-Roles` làm quyền cuối cùng.
- Có regression tests giả mạo sau mỗi change proxy/ingress.

**Khuyến nghị cho hệ thống mới:** Ưu tiên token được ký có audience cụ thể và được backend tự xác minh, cộng network/mTLS, hơn identity header tùy ý. Nếu cơ chế header là yêu cầu legacy, phải có threat model và trust proof ở gateway/network, không chỉ custom servlet filter.

## 4. Phân loại header: metadata và credential không giống nhau

| Header | Mục đích hợp lệ | Có được tự coi là danh tính/role? |
|---|---|---|
| `X-Authenticated-User` | Legacy gateway chuyển danh tính được xác thực | **Không**, nếu thiếu trusted gateway boundary |
| `X-Verified-Subject` | Subject canonical từ trusted auth service | Chỉ qua verified pre-auth channel |
| `X-Remote-User`, `X-Forwarded-User` | Vendor-specific identity propagation | Không tự tin nguồn |
| `X-Authenticated-Roles`, `X-Groups` | Legacy role hints | Không tự cấp ROLE_ADMIN |
| `Authorization: Bearer ...` | Credential access token | Backend phải verify signature/claims/audience |
| `Cookie` | Browser session credential | Gateway verify; không parse thành user từ header thô |
| `Forwarded` (RFC 7239) | Proxy hop info: `for/proto/host` | Không phải credential |
| `X-Forwarded-For` | Effective client IP chain | Không phải identity proof; spoofable |
| `X-Forwarded-Host` | Public host | Phải canonical/allowlisted |
| `X-Forwarded-Proto` | Public HTTPS scheme | Phải do trusted TLS terminator xác nhận |
| `X-Forwarded-Port` | Public port | Không dùng raw để tạo redirect URI |
| `X-Forwarded-Prefix` | Public path prefix | Cần approved routing |
| `X-Request-Id` | Correlation identifier | Không tự tạo trust/authentication |
| `X-Tenant-Id` | Client request context | Cần đối chiếu tenant membership server-side |

**Phân biệt:** `X-Forwarded-For` có thể giúp phân tích rate limit; nó không chứng minh user là Alice. `X-Tenant-Id` có thể chỉ tenant mà caller muốn truy cập; nó không chứng minh caller thuộc tenant đó.

### 4.1. Tấn công bằng header spoofing

Một client chưa đăng nhập gửi:
~~~http
GET /api/reports/42 HTTP/1.1
Host: portal.example.test
X-Authenticated-User: admin-test
X-Authenticated-Roles: ROLE_ADMIN
X-Forwarded-For: 10.0.0.1
X-Forwarded-Proto: https
Forwarded: for=10.0.0.1;proto=https;host=internal.example.test
~~~

Nếu gateway copy nguyên headers và backend có code kiểu:
~~~java
String username = request.getHeader("X-Authenticated-User");
// Anti-pattern: treating this raw value as an authenticated user.
~~~

thì attacker có thể mạo danh Admin. Nếu proxy đã **strip/overwrite** và backend còn có signed token validation/mTLS boundary, attack phải thất bại.

### 4.2. Những biến thể còn nguy hiểm

- Header case-insensitivity: `x-authenticated-user` vs `X-Authenticated-User`.
- Duplicates: hai dòng cùng header, parsers lấy first/last hoặc merge khác nhau.
- Underscore vs hyphen normalization ở proxy và application servers.
- `Connection` header có thể liệt kê names hop-by-hop mà một proxy xử lý sai.
- HTTP/2 to HTTP/1 translation với duplicate/invalid pseudoheaders.
- Multi-hop proxy giữ lại một `Forwarded` dù đã xóa `X-Forwarded-Host`.
- Proxy `$proxy_add_x_forwarded_for` append vào chuỗi client fake.
- Request đến backend qua internal Service/POD, bỏ qua edge gateway.
- Header chứa CR/LF/control characters hoặc oversized values gây parser confusion.

**Cần reject/normalize ở gateway chứ không sửa bằng cách thêm chuỗi check ở mỗi controller.**

## 5. Threat model STRIDE tối giản

| Threat | Kịch bản | Security property |
|---|---|---|
| Spoofing | Forged `X-Authenticated-User` | Identity chỉ từ verified token/gateway |
| Tampering | Client sửa `X-Groups` thành Admin | Approved entitlements không từ client |
| Repudiation | XFF giả đổi IP audit | Normalized client IP từ trusted chain |
| Information disclosure | Log Bearer token/SAMLResponse | Redact raw credentials |
| Denial of service | Header dài, duplicate, invalid JWT hàng loạt | Size/rate/time limits |
| Elevation of privilege | User thường gắn `ROLE_ADMIN` | Resource/method/tenant authorization |
| Confused deputy | Gateway token relay dành audience khác | Validate `aud`/token exchange |
| Lateral movement | Pod khác gọi backend private port | NetworkPolicy/mTLS workload identity |
| Replay | Dùng lại bearer token còn hiệu lực | Short TTL, revoke/jti policy cho action rủi ro |
| Session mix-up | Same username từ hai issuers | Namespace theo issuer+subject/tenant |

Chỉ kiểm `403` với một forged header là chưa đủ nếu gateway routing trả 403 vì app đang tắt, không phải vì security filter. Test phải xác nhận **đường hợp lệ vẫn hoạt động** và forged credentials không tạo authenticated principal hoặc quyền.

## 6. Nguồn tin cậy: ai chứng minh điều gì?

Trong một thiết kế được duyệt:
- **Public TLS**: browser đang nói chuyện với gateway đúng hostname.
- **OIDC/SAML2 at gateway**: gateway xác minh trusted IdP keys, issuer, recipient/redirect URI, state/nonce/SAML conditions.
- **Gateway service identity**: mTLS SPIFFE/SVID hoặc certificate/service identity được backend trust; không phải `X-Gateway-Id` do client tự khai.
- **JWT signature**: token ký bởi trusted issuer và claims dành cho backend; mTLS không tự thay signature.
- **Local authorization**: business service kiểm trạng thái account, memberships, resource owner, authorities.
- **Audit**: trace IDs và sanitized token metadata, không log credential.

### 6.1. Authentication ≠ authorization

Nếu Alice có JWT valid với scope `reports.read`:
- `GET /api/reports/42` có thể pass URL-level role.
- Nhưng nếu report 42 thuộc tenant-b còn Alice chỉ thuộc tenant-a, **domain authorization vẫn phải deny**.
- `POST /api/reports/42/approve` phải deny nếu thiếu `reports.approve`, dù login tại gateway thành công.

Không cấu hình `anyRequest().authenticated()` làm toàn bộ security policy cho resource nhạy cảm; nó chỉ bảo đảm một lớp.

### 6.2. Không dùng IP như định danh user

`X-Forwarded-For` có thể bị spoof nếu chain không được gateway xử lý đúng; NAT/CDN/VPN còn làm IP thay đổi. Rate limit theo IP chỉ là một lớp; principal dựa trên verified subject/issuer, không phải địa chỉ IP hoặc Host header.

## 7. Chuẩn bị môi trường lab

Giả định:
- Java 17+ và Spring Boot release tương thích.
- Có test OIDC issuer hoặc test SAML2 IdP phục vụ gateway.
- Có sandbox JWT issuer/JWKS và ít nhất hai test subjects.
- Gateway/router kiểm soát public host, TLS, routing.
- Backend không có public listener; chỉ dùng private network.
- Test group:
  - Alice: `reports.read`, tenant-a.
  - Bob: không có `reports.read`.
  - Approved admin: `reports.approve`, tenant-a.
- API contract:
  - `GET /api/reports/{id}` → cần `SCOPE_reports.read` và ownership.
  - `POST /api/reports/{id}/approve` → cần `SCOPE_reports.approve` và server-side approval policy.

**Không dùng tài khoản, refresh tokens hoặc signing keys production trong lab.** Dùng synthetic users, test keys do sandbox signer kiểm soát; không commit private keys hay đưa bearer tokens vào CI artifacts.

### 7.1. Sơ đồ nguồn dữ liệu

~~~text
IdP trusted subject/issuer
        |
        v
Gateway OIDC/SAML authentication
        |
        +-- Verify login + session
        |
        +-- Access token (aud=orders-api), or controlled token exchange
        |
        v
Backend JwtDecoder (public JWK, iss, aud, exp, nbf)
        |
        v
JwtAuthenticationToken with approved SCOPE_ authorities
        |
        v
Local user lookup (issuer + sub)
        |
        v
Tenant/report policy + HTTP/method security
~~~

Ở nhánh legacy pre-auth, thay `JwtDecoder` bằng verified workload gateway channel và một approved local-user mapper. Nhánh đó **không được dùng hằng số user từ header thô**.

## 8. Cấu hình Spring Boot Resource Server: phương án chính

Trong backend `orders-api`, dùng starter Web/Security/OAuth2 Resource Server. Ví dụ Spring Boot Maven dependencies fragment:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Đây là fragment cho POM được quản lý bởi Spring Boot parent/BOM, **không phải full POM build độc lập**. Version Spring Security/Spring Cloud Gateway phải tương thích với release train tương ứng. Không tự pin OpenSAML/Nimbus dependencies ngoài BOM không có lý do.

### 8.1. Chỉ định trusted issuer và required audience

Tệp `application.yml` của backend lab:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://identity.example.test/issuer"
          audiences:
            - "orders-api"

logging:
  level:
    org.springframework.security: INFO
~~~

**Chú ý:** Đây là issuer hư cấu của lab, phải thay bằng sandbox identity service thật và kết nối TLS/JWKS tin cậy khi chạy full integration. Spring Security Resource Server xác minh signature theo trusted JWK, `iss`, `exp`, `nbf`; cấu hình `audiences` bổ sung expected audience. Không nhận issuer/JWKS URL từ arbitrary JWT claim hoặc request parameter.

Nếu gateway **phát JWT nội bộ**, đặt issuer URI thành **issuer của token service nội bộ**, không phải IdP gốc, và xét token exchange subject/actor trust. Khi một gateway chỉ relay IdP access token, backend phải kiểm audience đã thực sự được IdP phát cho nó.

### 8.2. Spring Security Servlet SecurityFilterChain

Tệp `ApiSecurityConfig.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            // Only for an API using Bearer JWT, never browser cookies.
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(a -> a
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports/*/approve")
                    .hasAuthority("SCOPE_reports.approve")
                .anyRequest().denyAll())
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(a -> a.anyRequest().denyAll())
            .build();
    }
}
~~~

**Cảnh báo về CSRF:** `csrf(AbstractHttpConfigurer::disable)` ở **chain chuyên biệt /api/** được thiết kế cho stateless API chỉ chấp nhận `Authorization: Bearer`, không dùng session cookie/browser auto-submitted credentials. Nếu backend cũng dùng cookie auth, form hoặc mixed SSO, **không sao chép dòng này**; cần CSRF protection theo threat model. HTTP matcher và path pattern syntax tùy Spring Security/Servlet release, kiểm với real tests.

**Một chi tiết về matcher ordering:** `GET /api/reports/**` và `POST /api/reports/*/approve` là rules ở URL layer; tenant/owner phải được kiểm ở service/method. Unknown methods trong API default deny. Nếu route thật có `/api/reports/list`, `/api/reports/42/export`, chính sách phải được thiết kế tường minh.

### 8.3. JWT: scope không tự là business role

Resource Server mặc định thường map OAuth2 scopes thành `SCOPE_*` authorities, ví dụ:
~~~text
scope="reports.read" -> SCOPE_reports.read
scope="reports.approve" -> SCOPE_reports.approve
~~~

Không coi `OIDC_USER`, `SCOPE_profile`, `X-Authenticated-Roles: ROLE_ADMIN` là đồng nghĩa quyền duyệt report. Với JWT custom claim `roles`, chỉ map theo approved issuer và role allowlist, kết hợp local entitlement/tenant check.

### 8.4. Thêm kiểm nghiệp vụ ở service

Một lớp business service có thể dùng `@PreAuthorize` để thêm quyền và kiểm resource owner:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public ReportDto viewReport(String reportId, String userId) {
    // Load report from trusted database.
    // Check that userId is allowed to access report's tenant.
    // Return only data authorized for this user.
    return reportRepository.loadAuthorized(reportId, userId);
}
~~~

Đây là **fragment Spring service**, chưa có imports/domain types nên không phải Java standalone. Với multi-tenant, `userId` ở đây phải lấy từ validated Authentication + approved local identity link, **không tin query param userId hay X-Tenant-Id**. Bật `@EnableMethodSecurity` và kiểm AOP proxy thực sự thực thi annotation. Query repository phải enforce tenant membership/ownership, không chỉ lọc frontend.

## 9. Chỉ chấp nhận header identity qua gateway pre-auth có kiểm soát

Spring Security có pre-authentication APIs cho hệ enterprise SSO:
- `RequestHeaderAuthenticationFilter` lấy principal từ HTTP request header.
- `PreAuthenticatedAuthenticationProvider` cùng UserDetailsService map principal sang authorities.
- Container-authenticated user principal, X.509 auth cũng là những dạng preauth khác.

**Framework không tự chứng minh một request header đến từ trusted gateway.** Một cấu hình kiểu này:
~~~java
// Unsafe as a complete security solution on its own:
RequestHeaderAuthenticationFilter filter =
        new RequestHeaderAuthenticationFilter();
filter.setPrincipalRequestHeader("X-Authenticated-User");
~~~

chỉ hướng dẫn filter đọc một header, **chưa xác minh gateway identity**. Nếu backend có thể nhận request trực tiếp, attacker gửi `X-Authenticated-User: admin` sẽ bị mạo danh. Không triển khai fragment này nếu chưa có approved edge/network/mTLS trust boundary và UserDetailsService policy.

### 9.1. Điều kiện tối thiểu để dùng legacy identity header

| Layer | Kiểm soát | Test |
|---|---|---|
| Public gateway | Login via validated OIDC/SAML2 | Invalid IdP signature/nonce bị reject |
| Header sanitization | Strip identity headers do client gửi | Forged user/groups không tới app |
| Auth service | Chỉ phát verified stable subject | Anonymous request không có subject |
| Transport | Backend chỉ nhận gateway workload | Direct pod/backend IP request bị block |
| mTLS khi cần | Client certificate/service identity approved | Wrong gateway cert bị reject |
| Spring pre-auth | No missing principal fallback | Header trống/duplicate fail |
| User lookup | Subject+issuer → approved local account | Unknown/inactive user fail |
| Authorization | Group/tenant/resource policy | No role escalation |
| Observability | Trace và denial reason an toàn | Không leak session/token |

### 9.2. Gateway-derived subject khác browser-supplied subject

Nếu browser gửi `X-Verified-Subject: admin-test`, gateway phải **xóa** nó trước khi truy vấn auth service và dựng header mới. Dữ liệu mới có thể lấy từ:
- Verified OIDC session `iss+sub`.
- Verified SAML2 Assertion NameID/persistent attribute + IdP issuer.
- Enterprise identity broker đã xác minh ticket/token.
- Local approved user mapping service.

**Không dùng giá trị do browser gửi** làm input tin cậy chỉ vì gateway đã đổi tên header thành `X-Verified-Subject`.

### 9.3. Pre-auth không tự xác định permission

Header chỉ chứa tên user mà không có verified entitlement contract sẽ không cho biết quyền nào được cấp. Spring có thể dùng `UserDetailsService` hoặc approved directory/DB để tải authorities. Nếu header mang groups, phải ràng buộc với gateway identity proof và allowlist mapping; tránh chuyển nguyên `X-Roles: ADMIN` sang `ROLE_ADMIN`.

## 10. Edge NGINX: xóa header giả trước khi dựng header nội bộ

Ví dụ này dành cho topology **NGINX trực tiếp terminate public TLS**, yêu cầu authentication qua internal auth service, rồi chuyển request tới backend private. Đường dẫn auth service và header response phải được thay bằng **giao thức đã triển khai/kiểm thử của nhà cung cấp auth**, không coi NGINX tự xác thực OIDC token.

~~~nginx
server {
    listen 443 ssl;
    server_name portal.example.test;

    ssl_certificate     /etc/nginx/tls/public.crt;
    ssl_certificate_key /etc/nginx/tls/public.key;

    location = /_auth {
        internal;

        proxy_pass http://auth-service.private:9000/check;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";

        proxy_set_header Host auth-service.private;
        proxy_set_header X-Original-URI $request_uri;

        # Avoid sending a client-supplied identity marker to auth service.
        proxy_set_header X-Verified-Subject "";
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Authenticated-Roles "";
    }

    location / {
        auth_request /_auth;
        auth_request_set $verified_subject
            $upstream_http_x_verified_subject;

        proxy_pass http://orders-api.private:8080;

        # Backend must never see client-injected identity headers.
        proxy_set_header X-Verified-Subject $verified_subject;
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Authenticated-Roles "";
        proxy_set_header X-Remote-User "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header X-Groups "";

        # Fixed approved public origin; no raw $http_host.
        proxy_set_header Host portal.example.test;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host portal.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Prefix "";

        # Header pre-auth variant: do not relay client Bearer token.
        proxy_set_header Authorization "";
    }
}
~~~

**Đây là cấu hình minh họa cho legacy pre-auth variant**, **không** phải cách relay JWT trong phần 8. Nếu chọn JWT route, gateway phải xuất hiện `Authorization: Bearer <approved access token>` có nguồn authenticated token service và audience backend. Không giữ `Authorization` của browser nguyên vẹn khi chính sách yêu cầu gateway issue/token exchange.

**Điều kiện để ví dụ an toàn:**
- NGINX public TLS listener chỉ nhận hostname đã phê duyệt; unknown Host/SNI phải reject.
- Auth service `/check` thực sự xác minh session/token và trả header verified subject từ internal response, không echo header client.
- `auth_request` từ chối/redirect anonymous theo documented error flow; không auto-authenticate khi auth service down.
- NGINX và auth-service chỉ truy cập trong approved network; auth subrequest có session cookie/token đúng contract.
- NGINX backend route chỉ tới service private; firewall/Kubernetes policy không cho bypass gateway.
- `$remote_addr` là observed client peer **chỉ khi NGINX là public edge TLS terminator**; nếu sau CDN/LB, phải xác thực trusted upstream real-IP config và xử lý hop đúng.
- NGINX mặc định xử lý hop-by-hop headers theo module, nhưng phải review vendor-specific identity/forwarded headers, duplicate cases và proxies phía trước.
- Pre-auth path cần gateway-to-backend service identity, lý tưởng mTLS; NGINX sample không tự triển khai mTLS.
- **Không sử dụng giá trị X-Verified-Subject này làm principal nếu không có toàn bộ trust boundary nói trên.**

### 10.1. Tách header sanitation khỏi auth service decision

Luồng đúng:
~~~text
Client untrusted headers
     |
     v
Gateway rejects unknown Host / malformed request
     |
     v
Remove all inbound identity/forwarding markers
     |
     v
Authenticate via trusted auth service / IdP
     |
     v
Derive canonical verified subject (not raw input)
     |
     v
Attach internal identity data or backend token
     |
     v
Private authenticated connection to backend
~~~

Một NGINX `proxy_set_header X-Verified-Subject $http_x_verified_subject;` là sai vì nó chỉ **đổi tên/sao chép** giá trị do client gửi. Để review, tìm mọi `$http_x_authenticated_*`, `$http_x_remote_user`, `$http_authorization` và biến từ inbound request đã được dùng làm trusted identity.

### 10.2. Auth service availability

Khi auth service timeout/5xx:
- Gateway phải fail closed cho protected routes.
- Không sử dụng last-known principal từ request cũ làm fallback.
- Không tự cho guest/anonymous truy cập resources được bảo vệ.
- Có alert cho authentication dependency.
- Cache only authenticated decisions với TTL/revocation policy rõ, ràng buộc session/token, không key cache chỉ theo URL hoặc IP.

## 11. Spring Cloud Gateway: TokenRelay và limitations

Spring Cloud Gateway có `TokenRelay` filter để lấy OAuth2 access token từ một authenticated OAuth2 client và chuyển tới downstream service.

Ví dụ config theo Spring Cloud Gateway **Server WebFlux** release hỗ trợ schema này:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: "http://orders-api.private:8080"
              predicates:
                - Path=/api/reports/**
              filters:
                - TokenRelay=
~~~

Đây là một **route fragment**. Phải có Spring Cloud Gateway release/BOM phù hợp, OAuth2 client configuration, authenticated user context và authorized client service theo docs. `TokenRelay=` không có nghĩa gateway đã tự phát access token mới đúng audience; nếu relay token dành gateway mà backend yêu cầu `aud=orders-api`, backend **phải reject**. Khi cần token exchange, thiết kế theo OAuth 2.0 Token Exchange/profile được IdP hỗ trợ hoặc sử dụng dedicated internal issuer, không chỉ đổi header.

### 11.1. Gateway filter configuration chưa phải trust boundary

- Dù TokenRelay hoạt động, phải strip client-injected identity headers.
- Route predicates không thay backend NetworkPolicy.
- API Resource Server vẫn kiểm JWT issuer, audience, signature, exp/nbf.
- Nếu gateway cũng nhận Bearer token từ client, policy phải rõ: validate client token trước hay dùng token của authenticated session; không nhầm hai principals.
- CORS headers và HTTP forwarded metadata cũng cần sanitize.
- Spring Cloud Gateway Server MVC và WebFlux có classes/filter configs khác nhau. Đọc đúng docs release, không copy snippet WebFlux vào Servlet MVC.

### 11.2. Khi không relay access token

Nếu gateway đăng nhập user qua SAML2:
- Browser có gateway session sau verified XMLDSig Assertion.
- Gateway có thể phát nội bộ một JWT với trusted internal issuer/aud.
- Backend verify JWT và local entitlement.
- Không gửi nguyên raw SAMLResponse dưới `X-SAMLResponse` để backend parse tùy tiện.
- Nếu backend thật sự là SAML SP riêng, nó cần đúng RelyingPartyRegistration/trusted IdP signing cert, Audience/Recipient/Destination và request context; không tự nhầm với gateway SAML login.

## 12. Forwarded headers: public origin không phải principal

Spring Framework `ForwardedHeaderFilter`/WebFlux `ForwardedHeaderTransformer` giúp diễn giải public scheme/host/port sau proxy, nhưng **không tự xác minh nguồn header**. Theo Spring docs, tại edge of trust phải loại bỏ inbound cả chuẩn `Forwarded` và `X-Forwarded-*`, sau đó proxy tạo giá trị đáng tin.

Spring Boot property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Chỉ bật khi:
- Backend không thể bị gọi bypass gateway.
- Gateway sanitize incoming `Forwarded` và `X-Forwarded-*`.
- Public origin được approved.
- Không có double handling giữa container valve và framework filter.
- Version Servlet/WebFlux framework có behavior phù hợp.

Nếu không có trusted proxy boundary, dùng `none`/`removeOnly` hoặc canonical URLs được cấu hình tĩnh, thay vì chấp nhận request-controlled `X-Forwarded-Host`.

### 12.1. Host spoofing ảnh hưởng federation callbacks

OIDC:
~~~text
Expected redirect_uri:
https://portal.example.test/login/oauth2/code/staff
~~~

Attacker gửi:
~~~http
X-Forwarded-Host: attacker.invalid
X-Forwarded-Proto: https
~~~

Nếu framework tin giá trị này, nó có thể tạo redirect URI/absolute links sai. IdP có thể chặn vì registered redirect URI exact mismatch; **đừng dựa vào IdP chặn để xem proxy là an toàn**. Gateway phải canonical host và backend/ClientRegistration không được trust arbitrary host.

SAML2:
~~~text
Expected ACS:
https://portal.example.test/login/saml2/sso/staff
~~~

SP metadata, `Response.Destination` và `SubjectConfirmationData.Recipient` phải nhất quán với public ACS. Không tắt checks khi gặp scheme/host mismatch; sửa trusted forwarding/canonical URL.

### 12.2. X-Forwarded-For và spoofed IP

Một attacker gửi:
~~~http
X-Forwarded-For: 127.0.0.1
~~~

Nếu gateway chỉ append observed IP:
~~~http
X-Forwarded-For: 127.0.0.1, 198.51.100.42
~~~

thì phần tử đầu có thể giả. Trình suy luận trusted chain phải xác định **raw socket peer** và hop trusted từ phải sang trái, không mặc định `split(",")[0]`. Proxy IP allowlist phải chính xác, không trust toàn bộ dải private IP. Dù lấy đúng effective IP, cũng không dùng IP như authenticated user identity.

## 13. Java 17 standalone: thấy rõ lỗi tin header

Tệp `GatewayHeaderBoundaryDemo.java` chạy độc lập trên JDK 17. Nó mô phỏng:
- Browser có thể gửi header nhận dạng giả.
- Gateway có một **trusted session identity** sau khi auth service xác thực (được mô phỏng bằng dữ liệu server-side, không do request header).
- Gateway tạo một `InternalRequest` mới chỉ chứa subject verified và connection identity.
- Backend từ chối direct peer lạ hoặc header không có verified subject.
- Business roles được server-side allowlist, không từ `X-Authenticated-Roles`.

~~~java
import java.util.Map;
import java.util.Set;

public class GatewayHeaderBoundaryDemo {

    record BrowserRequest(
            Map<String, String> clientHeaders,
            String verifiedSessionSubject) {
    }

    record InternalRequest(
            String workloadPeerIdentity,
            String verifiedSubject) {
    }

    static InternalRequest routeThroughTrustedGateway(
            BrowserRequest browser) {

        // The verifiedSessionSubject is a SERVER-SIDE result
        // of OIDC/SAML authentication, never an HTTP input.
        return new InternalRequest(
                "spiffe://lab/gateway",
                browser.verifiedSessionSubject());
    }

    static String backendDecision(InternalRequest request) {
        if (!"spiffe://lab/gateway".equals(
                request.workloadPeerIdentity())) {
            return "DENY_UNTRUSTED_GATEWAY";
        }

        String subject = request.verifiedSubject();
        if (subject == null || subject.isBlank()) {
            return "DENY_NO_AUTHENTICATED_SUBJECT";
        }

        Map<String, Set<String>> approvedRoles = Map.of(
                "alice-1001", Set.of("ROLE_REPORT_VIEW"),
                "admin-test", Set.of(
                        "ROLE_REPORT_VIEW", "ROLE_REPORT_APPROVE"));

        Set<String> roles = approvedRoles.get(subject);
        if (roles == null) {
            return "DENY_UNKNOWN_LOCAL_USER";
        }

        if (roles.contains("ROLE_REPORT_APPROVE")) {
            return "ALLOW_APPROVE:" + subject;
        }
        return "ALLOW_VIEW:" + subject;
    }

    public static void main(String[] args) {
        BrowserRequest anonymousAttacker = new BrowserRequest(
                Map.of(
                        "X-Authenticated-User", "admin-test",
                        "X-Authenticated-Roles", "ROLE_ADMIN"),
                null);

        BrowserRequest aliceWithForgedRole = new BrowserRequest(
                Map.of(
                        "X-Authenticated-User", "admin-test",
                        "X-Authenticated-Roles", "ROLE_ADMIN"),
                "alice-1001");

        BrowserRequest approvedAdmin = new BrowserRequest(
                Map.of(), "admin-test");

        InternalRequest directAttacker =
                new InternalRequest(
                        "spiffe://lab/attacker",
                        "admin-test");

        System.out.println("spoofed-anonymous=" +
                backendDecision(routeThroughTrustedGateway(
                        anonymousAttacker)));
        System.out.println("spoofed-role=" +
                backendDecision(routeThroughTrustedGateway(
                        aliceWithForgedRole)));
        System.out.println("approved-admin=" +
                backendDecision(routeThroughTrustedGateway(
                        approvedAdmin)));
        System.out.println("direct-peer=" +
                backendDecision(directAttacker));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac GatewayHeaderBoundaryDemo.java
java GatewayHeaderBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
spoofed-anonymous=DENY_NO_AUTHENTICATED_SUBJECT
spoofed-role=ALLOW_VIEW:alice-1001
approved-admin=ALLOW_APPROVE:admin-test
direct-peer=DENY_UNTRUSTED_GATEWAY
~~~

**Giải thích:**
- Attacker gửi tên Admin nhưng chưa login, gateway không biến header thành verified session subject, backend deny.
- Alice đăng nhập thật nhưng gửi role giả; backend chỉ dùng verified subject Alice và server-side mapping, không cấp quyền approve.
- Approved Admin có entitlement đúng được phép approve trong mô hình giản lược.
- Request từ workload identity khác gateway bị reject.

**Giới hạn quan trọng:** `verifiedSessionSubject` và `workloadPeerIdentity` là giá trị mô phỏng nội bộ **không được nhận từ client JSON/header**. Mã chưa có TLS/mTLS/SPIFFE verification, không validate OIDC/SAML, không kiểm tenant/resource/expired session. Nó là **mô hình trust invariants**, không phải implementation production. Mã này không chứng minh một HTTP proxy thật đã strip headers; cần integration tests riêng.

## 14. Java 17 standalone: ký internal assertion để chống sửa và dùng sai audience

Trong mô hình token nội bộ, public-key signature giúp backend xác minh nội dung. Java 17 hỗ trợ Ed25519 trong JCA; demo sau dùng một **opaque canonical string** để minh họa ký và kiểm `issuer/audience/time/jti`. **Nó không phải JWT/JOSE/JWS và không được dùng để tạo proprietary production authentication protocol**. Production nên dùng OAuth2/JWT chuẩn với thư viện đã được kiểm định, đúng claim normalization và trust rules.

Tệp `GatewayAssertionSignatureDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.util.HashSet;
import java.util.Set;

public class GatewayAssertionSignatureDemo {

    record Assertion(
            String issuer,
            String subject,
            String audience,
            long notBefore,
            long expires,
            String jti) {

        byte[] canonical() {
            String value = issuer + "|" + subject + "|" +
                    audience + "|" + notBefore + "|" +
                    expires + "|" + jti;
            return value.getBytes(StandardCharsets.UTF_8);
        }
    }

    static byte[] sign(Assertion a, KeyPair key) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(key.getPrivate());
        signer.update(a.canonical());
        return signer.sign();
    }

    static boolean signatureValid(
            Assertion a, byte[] signed, PublicKey trusted)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trusted);
        verifier.update(a.canonical());
        return verifier.verify(signed);
    }

    static String validate(
            Assertion a, byte[] signed, PublicKey trusted,
            long now, Set<String> seen) throws Exception {

        if (!signatureValid(a, signed, trusted)) {
            return "REJECT_SIGNATURE";
        }
        if (!"gateway-issuer-lab".equals(a.issuer())) {
            return "REJECT_ISSUER";
        }
        if (!"orders-api".equals(a.audience())) {
            return "REJECT_AUDIENCE";
        }
        if (now < a.notBefore() || now >= a.expires()) {
            return "REJECT_TIME";
        }
        if (!seen.add(a.jti())) {
            return "REJECT_REPLAY";
        }
        return "ACCEPT:" + a.subject();
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair gatewayKey = generator.generateKeyPair();
        KeyPair attackerKey = generator.generateKeyPair();

        long now = 1_800_000_000L;
        Assertion valid = new Assertion(
                "gateway-issuer-lab", "alice-1001",
                "orders-api", now - 10, now + 60, "id-001");

        byte[] trustedSig = sign(valid, gatewayKey);
        Set<String> seen = new HashSet<>();

        System.out.println("valid=" + validate(
                valid, trustedSig, gatewayKey.getPublic(),
                now, seen));
        System.out.println("replay=" + validate(
                valid, trustedSig, gatewayKey.getPublic(),
                now, seen));

        Assertion altered = new Assertion(
                valid.issuer(), "admin-test",
                valid.audience(), valid.notBefore(),
                valid.expires(), "id-002");
        System.out.println("tampered=" + validate(
                altered, trustedSig, gatewayKey.getPublic(),
                now, new HashSet<>()));

        Assertion wrongAudience = new Assertion(
                "gateway-issuer-lab", "alice-1001",
                "other-api", now - 10, now + 60, "id-003");
        System.out.println("audience=" + validate(
                wrongAudience, sign(wrongAudience, gatewayKey),
                gatewayKey.getPublic(), now, new HashSet<>()));

        Assertion expired = new Assertion(
                "gateway-issuer-lab", "alice-1001",
                "orders-api", now - 100, now - 1, "id-004");
        System.out.println("expired=" + validate(
                expired, sign(expired, gatewayKey),
                gatewayKey.getPublic(), now, new HashSet<>()));

        System.out.println("wrong-signer=" + validate(
                valid, sign(valid, attackerKey),
                gatewayKey.getPublic(), now, new HashSet<>()));
    }
}
~~~

Chạy:

~~~bash
javac GatewayAssertionSignatureDemo.java
java GatewayAssertionSignatureDemo
~~~

**Stdout chính xác:**

~~~text
valid=ACCEPT:alice-1001
replay=REJECT_REPLAY
tampered=REJECT_SIGNATURE
audience=REJECT_AUDIENCE
expired=REJECT_TIME
wrong-signer=REJECT_SIGNATURE
~~~

**Giới hạn:**
- `canonical()` dùng delimiter text tự phát minh, **có thể bị ambiguity/injection** nếu input cho chứa dấu `|`. Vì vậy nó **chỉ là bài tập Ed25519**, không phải thiết kế token production.
- JWT production phải có JOSE canonical serialization/alg/key validation, exact issuer/audience, timestamp claims và signed payload đúng thư viện.
- Không dùng một in-memory `HashSet` làm distributed replay cache. JWT bearer có thể được tái sử dụng trong lifetime hợp lệ; `jti` không tự chặn replay nếu không có state/cache hoặc DPoP/mTLS-bound token policy.
- `now` cố định giúp stdout lặp lại, không phải wall clock thực để xác minh token sản xuất.
- Private key được tạo ngẫu nhiên, chỉ gateway giữ trong mô hình; backend cần trusted public key, không nhận nó từ unverified JWT header `jwk/jku`.
- Kiểm audience/time sau signature bảo đảm phép thử `wrongAudience` có chữ ký đúng nhưng bị reject bởi policy; sửa payload sau signing thành `admin-test` khiến signature fail.

## 15. Khi nào backend được tin mạng và khi nào cần mTLS?

Trong môi trường đơn giản, Security Group/Firewall/NetworkPolicy giới hạn chỉ ingress gateway IP/Pod labels tới backend giúp giảm bề mặt tấn công. Nhưng:
- Pod labels có thể bị thao tác nếu RBAC cho phép deploy workload khác mang label đó.
- IP pod có thể đổi; CIDR toàn bộ cluster quá rộng.
- Service mesh sidecars có thể tạo một hop mới cần nhận dạng riêng.
- Internal network không tự ngăn lateral movement từ compromised workload.

Vì thế trên hệ nhạy cảm nên dùng:
1. **mTLS giữa gateway và backend** với verified gateway client certificate/workload identity.
2. Approved SPIFFE ID/service identity hoặc certificate subject/extension được quản trị.
3. Kết hợp network ACL như defense in depth.
4. JWT token đã được backend verify để tách end-user identity khỏi workload gateway identity.

**Không dùng `X-Gateway-Authenticated: true` hoặc `X-Client-Cert: ...` do browser gửi làm chứng cứ.** Nếu TLS termination gateway chuyển mTLS client cert info qua HTTP header, phải có trusted translation contract, header stripping và source authentication, nếu không attacker có thể giả.

### 15.1. Direct backend bypass test

Một test phải chứng minh request từ workload không nằm trong trusted gateway principal/network:
~~~text
untrusted-pod -> orders-api.private:8080
Expected: network connection denied OR mTLS handshake denied
~~~

Nếu nhận HTTP 401 từ backend, JWT validation có thể vẫn bảo vệ user; nhưng **điều kiện “backend chỉ nhận gateway traffic” đã không đạt**. Test network layer và application layer tách riêng.

## 16. Role mapping và tenant separation

Một JWT hợp lệ có:
~~~json
{
  "iss": "https://identity.example.test/issuer",
  "sub": "alice-1001",
  "aud": ["orders-api"],
  "scope": "reports.read",
  "tenant": "tenant-a"
}
~~~

Đây là **payload minh họa**, không phải JWT thật (không có header/signature). Spring JwtDecoder phải verify trước khi các claims được sử dụng. Claim `tenant` có thể thể hiện session context nhưng cần đối chiếu local memberships; một user có quyền tenant-a không được đọc report tenant-b chỉ vì đổi URL.

### 16.1. Nguyên tắc allowlist

- `reports.read` → `SCOPE_reports.read` khi JWT từ approved issuer, đúng audience.
- `reports.approve` → `SCOPE_reports.approve` chỉ nếu token issued theo policy và account vẫn đủ quyền.
- `ROLE_REPORT_ADMIN` chỉ gán từ approved server-side entitlements, không từ `X-Roles` của browser.
- `iss + sub` là identity namespace trong OIDC, không auto merge theo email.
- Với SAML2 gateway, `IdP entityID + stable NameID/qualifier` hoặc approved persistent identifier được map vào local account.
- Không tự tin `X-Tenant-Id`; tenant requested must match authorized tenant.
- Việc user đã login tại gateway không tự là `ROLE_ADMIN` trong backend.

### 16.2. Distinguish HTTP policy và domain policy

HTTP:
~~~text
GET /api/reports/42
Required: SCOPE_reports.read
JWT: valid, has SCOPE_reports.read
=> HTTP authorization may pass
~~~

Domain:
~~~text
Report 42 tenant = tenant-b
Alice approved tenant = tenant-a
=> Domain check denies even if HTTP scope passes
~~~

Cả hai phải có test riêng. Nếu API chỉ kiểm JWT signature và thiếu resource authorization, gateway có thể vô tình trở thành “confused deputy” xử lý dữ liệu tenant khác.

## 17. Header spoofing tests: hướng dẫn chạy lab

Trong môi trường lab được ủy quyền, chuẩn bị:
- Public gateway URL.
- Backend private address.
- Test identities/tokens do sandbox issuer phát.
- Session cookie dành cho browser, test JWT hợp lệ/không hợp lệ riêng.
- A/B identity roles và tenant resources.
- Có thể xem sanitized gateway logs và backend audit events qua trace ID.

### 17.1. Không-authenticated request giả Admin

~~~bash
curl -i \
  -H 'X-Authenticated-User: admin-test' \
  -H 'X-Authenticated-Roles: ROLE_ADMIN' \
  -H 'X-Verified-Subject: admin-test' \
  https://portal.example.test/api/reports/42
~~~

Kỳ vọng:
- Nếu gateway là browser SSO: redirect tới IdP hoặc reject/challenge.
- Nếu gateway là bearer API: 401/403 theo chain.
- **Không** có authenticated backend principal Admin hoặc báo cáo nhạy cảm trả ra.
- Nếu app nhận request, sanitized logs cho thấy headers giả đã được loại bỏ.
- Không assert một HTTP status cố định áp cho mọi gateway; **assert no privilege/granted resource**.

### 17.2. Authenticated Alice giả role Admin

Trong một E2E test harness có **session Alice hợp lệ**, gửi:
~~~http
GET /api/reports/42 HTTP/1.1
Host: portal.example.test
Cookie: session-cookie-issued-to-Alice
X-Authenticated-User: admin-test
X-Authenticated-Roles: ROLE_ADMIN
X-Tenant-Id: tenant-b
~~~

Đây là **hình dạng HTTP minh họa**; cookie hợp lệ phải do sandbox gateway tự cấp, không dùng literal text trên mạng thật. Kỳ vọng:
- Backend identity vẫn Alice.
- Không tự nâng `ROLE_ADMIN`.
- Request tenant-b bị deny nếu Alice không có membership.
- Nếu Alice sở hữu report tenant-a, GET hợp lệ vẫn pass khi sử dụng đúng token/route.

### 17.3. Direct-backend spoof

Từ pod/test network **không được phép**:
~~~bash
curl -i \
  -H 'X-Verified-Subject: admin-test' \
  -H 'X-Authenticated-Roles: ROLE_ADMIN' \
  http://orders-api.private:8080/api/reports/42
~~~

Kỳ vọng ở network: connection blocked/mTLS denied. Nếu port vẫn reachable, backend JWT validation phải từ chối request không Bearer token, nhưng **đó chỉ là defense in depth; network boundary cần sửa**.

### 17.4. Forged Forwarded/X-Forwarded-*

~~~bash
curl -i \
  -H 'Forwarded: for=127.0.0.1;proto=http;host=attacker.invalid' \
  -H 'X-Forwarded-For: 127.0.0.1' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: attacker.invalid' \
  -H 'X-Forwarded-Port: 8080' \
  https://portal.example.test/api/reports/42
~~~

Kỳ vọng:
- Proxy reject hoặc reconstruct approved public metadata.
- Backend không sử dụng fake `127.0.0.1` để bypass rate limit.
- Redirect/links/ACS không chứa `attacker.invalid`.
- Nếu Host virtual routing không hợp lệ, request fail closed.
- Không dùng forwarding data làm identity.

### 17.5. Duplicates và case variations

Một robust integration suite cần thử:
- `X-Authenticated-User: alice-1001` và dòng thứ hai `X-Authenticated-User: admin-test`.
- lowercase `x-authenticated-user`, mixed casing.
- `X_Authenticated_User` nếu gateway/container normalize underscore.
- Cả `Forwarded` và `X-Forwarded-Host` với host khác nhau.
- `Connection: X-Authenticated-User` và hop-by-hop handling.
- Header values chứa comma, whitespace, Unicode hoặc control characters bị parser reject.
- HTTP/2 requests qua gateway→HTTP/1 backend.
- Dài bất thường, count vượt header size limits.

Expected: request bị reject hoặc normalized theo policy nhưng **không tạo user/role không được approved**. Không dựa vào một library chọn first header trong khi library khác chọn last.

## 18. Bearer token tests: signed nhưng vẫn có thể bị từ chối

| Ca | JWT signature | iss | aud | time | Expected |
|---|---|---|---|---|---|
| Valid Alice | valid | approved | orders-api | valid | Authenticated + scopes được map |
| Tampered payload | invalid | arbitrary | arbitrary | arbitrary | 401/invalid token |
| Wrong issuer | valid under other issuer | wrong | orders-api | valid | Reject issuer/trust |
| Wrong audience | valid | approved | another-api | valid | Reject audience |
| Expired | valid | approved | orders-api | expired | Reject time |
| nbf future | valid | approved | orders-api | not yet valid | Reject time |
| alg none/weak | not approved | any | any | any | Reject algorithm |
| Unknown kid | no approved key | approved claim | orders-api | valid | Reject unknown signer |
| Client-provided jku | untrusted URL | arbitrary | orders-api | valid | No arbitrary JWKS fetch |
| Missing required scope | valid | approved | orders-api | valid | 403 authorization |
| Scope approve but wrong tenant | valid | approved | orders-api | valid | Domain deny |
| Relay token meant for gateway | valid | approved | gateway | valid | Reject at orders-api |
| Revoked/expired user session | may still be cryptographically valid | approved | orders-api | valid | Apply revocation/recheck policy |
| Replayed bearer within TTL | valid | approved | orders-api | valid | Policy-dependent: bearer alone is replayable |

**Không nói JWT tự chống replay vì có `jti`.** JWT bearer by design có thể được trình lại trong hiệu lực; nếu cần proof-of-possession hoặc replay cache, thiết kế DPoP/mTLS-bound token/JTI registry và test riêng.

### 18.1. Verify token theo backend, không dựa vào gateway logs

Một gateway có thể log "authenticated Alice", nhưng backend vẫn phải xác minh token được gửi đến nó. Không nhận một JSON flag do gateway/client tự khai:
~~~json
{"authenticated":true,"role":"ADMIN"}
~~~

Đây không phải JWT verification proof. Nếu đã có verified gateway session, cần token relay đúng audience hoặc pre-auth kênh đã bảo vệ.

## 19. SAML2/OIDC tại gateway: đừng nhầm với backend authorization

### 19.1. OIDC

Gateway dùng Authorization Code flow/PKCE theo client policy:
1. Gửi AuthorizationRequest với state/nonce.
2. IdP kiểm user.
3. Gateway nhận code qua registered redirect URI.
4. Gateway đổi code lấy tokens, kiểm ID Token issuer/audience/signature/nonce.
5. Gateway tạo session user.
6. Gateway relay đúng access token hoặc issue internal JWT theo hợp đồng.
7. Backend verify backend token; sau đó local role/tenant authorization.

Không chuyển ID Token thành access token cho backend nếu protocol không cho. Không cho request header tự chọn issuer/client secret/JWKS.

### 19.2. SAML2

Gateway đóng vai SP trước IdP:
1. AuthnRequest và request state được lưu khi SP-initiated.
2. IdP gửi SAMLResponse tới đúng gateway ACS.
3. Gateway xác minh trusted XMLDSig, issuer, Audience, Destination, Recipient, Conditions, InResponseTo và SubjectConfirmation.
4. Gateway dùng **validated Assertion** để tạo canonical user identity.
5. Gateway issue internal token/secure preauth evidence.
6. Backend verify nội bộ, map approved local account and permissions.

Không Base64-decode raw SAMLResponse rồi chèn NameID vào `X-Authenticated-User` **trước** khi OpenSAML/Spring provider hoàn tất validation. Không được verify signed Assertion A nhưng lấy attributes từ unsigned Assertion B (XML Signature Wrapping).

### 19.3. CAS/Kerberos/LDAP

Các gateway enterprise có thể validate CAS service ticket, Kerberos SPNEGO hoặc LDAP bind; thành công chỉ chứng minh một external principal trong realm/issuer scope. Backend tiếp tục cần stable identity mapping và resource permissions; không tự nhận HTTP `REMOTE_USER` từ client khi chưa có preauth trust.

## 20. CSRF, CORS, session và logout trong mô hình gateway

### 20.1. Gateway dùng browser cookies

Nếu gateway lưu SSO session bằng cookie:
- Cookie nên có Secure, HttpOnly, SameSite policy đúng flow.
- Thực thi CSRF protection cho state-changing browser actions hoặc cơ chế tương đương theo design.
- OAuth2/OIDC state/nonce và SAML InResponseTo không được tắt để tránh login loops.
- Logout cần invalidate gateway session và backend propagated state/token nếu policy có revocation.
- Return URL/RelayState phải allowlist, không open redirect.

### 20.2. Backend stateless bearer API

Nếu backend không dùng cookies, chỉ nhận Bearer token:
- Không cần server-side browser session để authenticate API.
- Spring Security resource server filter kiểm bearer mỗi request.
- CSRF configuration có thể được thu hẹp riêng API chain theo threat model, không tắt cho những browser endpoints khác.
- CORS preflight phải được xử lý đúng và không cấp API access cho Origin không approved.
- Session JWT audience/issuer không phụ thuộc raw `X-Forwarded-Proto`.
- Revocation có thể cần riêng nếu token bị đánh cắp.

### 20.3. HTTP errors không phải một mã cố định

- Anonymous browser → 302 tới gateway IdP/login.
- Invalid/missing API Bearer token → thường 401/challenge.
- Valid authentication nhưng thiếu permission → thường 403.
- Missing CSRF token trên cookie-auth POST → có thể 403.
- NetworkPolicy/mTLS failure → request không tới ứng dụng, không có Spring HTTP status.
- Gateway WAF rejection → gateway trả 403 trước backend.

Một QA suite tốt kiểm **đúng layer** thay vì chỉ so HTTP 200/401/403.

## 21. Docker/Kubernetes network controls

### 21.1. Docker/test topology

Một Compose lab có thể dùng hai networks:
~~~text
public_net: browser/test client -> gateway (published TLS only)
private_net: gateway -> orders-api, auth-service, token-issuer
orders-api: no published ports on host
auth-service: no public ports
~~~

Không để `ports: "8080:8080"` trên backend production nếu mục tiêu là gateway-only ingress. Trong Docker Compose, bỏ host port publishing là điều kiện cần nhưng phải kiểm network attachments/host privileges và access từ containers khác.

### 21.2. Kubernetes NetworkPolicy

Ý tưởng:
- Namespace `api` mặc định deny ingress cho orders-api.
- Allow ingress tới orders-api port 8080 chỉ từ Pods thuộc gateway namespace có labels đã phê duyệt.
- RBAC không cho arbitrary workload giả nhãn ingress.
- Egress từ gateway chỉ tới required auth/token/JWKS services.
- API service không có NodePort/LoadBalancer public ngoài dự kiến.
- Service mesh mTLS policy yêu cầu gateway principal đúng.
- Health probes được thiết kế qua approved control plane mà không mở toàn API.
- NetworkPolicy enforcement phụ thuộc CNI, namespace labels và actual traffic path.

Một skeleton Kubernetes policy minh họa nguyên tắc:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-api-only-gateway
  namespace: api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: gateway
          podSelector:
            matchLabels:
              app: trusted-gateway
      ports:
        - protocol: TCP
          port: 8080
~~~

Đây là **chính sách mẫu**: kiểm namespace labels, cluster CNI, ambient/service mesh, gateway Pods và RBAC. Một NetworkPolicy không tự mã hóa traffic hay kiểm actual gateway workload cryptographically; kết hợp mTLS khi cần.

## 22. Kiểm thử với Spring Security MockMvc

Test policy business riêng bằng `SecurityMockMvcRequestPostProcessors.jwt()`/`user()`:

~~~java
// Fragment in a Spring Boot JUnit/MockMvc test with matching routes.
mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile"))))
    .andExpect(status().isForbidden());
~~~

**Các điều kiện:** cần controller route, imports và approved test data, report 42 thuộc tenant của mock principal. Đây là test **authorization**, không kiểm signed JWT/JWKS `JwtDecoder` thật — helper `jwt()` có thể bypass decode/signature. Do đó, thêm integration tests dùng **JWT có chữ ký thật** từ sandbox issuer và trỏ backend tới trusted test JWKS.

### 22.1. Test forged headers với MockMvc

~~~java
// Fragment: verifies app ignores raw identity header under JWT policy.
mvc.perform(get("/api/reports/42")
        .header("X-Authenticated-User", "admin-test")
        .header("X-Authenticated-Roles", "ROLE_ADMIN"))
    .andExpect(status().isUnauthorized());
~~~

Với API chain chỉ Bearer, expected 401 thường đúng, nhưng status có thể thay theo handler. Điều quan trọng: raw headers **không** tạo authenticated principal. MockMvc test này **không** chứng minh NGINX strip headers hoặc direct backend NetworkPolicy chặn; cần test qua gateway thật.

### 22.2. Test GET và POST khác CSRF

Khi browser session và cookies được dùng:
- GET có thể pass.
- POST không CSRF bị 403.
- POST với CSRF đúng nhưng thiếu scope cũng có thể 403, song ở authorization layer.
- Không thêm ROLE_ADMIN để sửa CSRF.
- Với stateless bearer API riêng, CSRF behavior theo threat model đã được review.

## 23. CI pipeline kiểm chứng thực tế

~~~text
1. Build gateway/backend with pinned dependencies
2. Start isolated IdP or trusted test JWT issuer
3. Generate signing keypair only for test and publish public JWKS
4. Start private backend with issuer+audience validation
5. Start gateway with valid TLS and header sanitation
6. Assert gateway→backend path and direct-backend deny
7. Run authenticated Alice and approved Admin positive tests
8. Send forged identity/role/tenant headers
9. Send Forwarded/X-Forwarded-* spoof/duplicate variants
10. Send invalid/expired/wrong-audience JWTs
11. Run SAML/OIDC callback, session and logout tests
12. Assert principal/tenant/authority at backend without leaking tokens
13. Audit logs, traces and key handling
14. Publish sanitized JUnit reports; clean secrets and sessions
15. Fail release if privilege escalation or bypass is observed
~~~

### 23.1. CI hardening

- Test keys không trùng production.
- Không đưa private signing keys vào repo, container layers hoặc CI public artifacts.
- Không log full JWT, Authorization header, cookies, SAMLResponse hoặc ID Token.
- Restrict test issuer/JWKS và auth service tới private lab.
- E2E with synthetic identities only.
- Test auth service 5xx/timeouts fail closed, không trust cached anonymous header.
- Feature flags không được tắt signature validation ở production.
- Release pipeline diff/review gateway routes, NGINX headers, NetworkPolicy và Spring SecurityFilterChain cùng một change set.

## 24. Ma trận kiểm thử tổng hợp

| ID | Thử nghiệm | Kỳ vọng an toàn |
|---|---|---|
| G01 | Alice login gateway OIDC hợp lệ | Gateway tạo verified session |
| G02 | Alice SAML Response chữ ký trusted | Gateway nhận đúng stable subject |
| G03 | SAML signature/Issuer/Audience sai | Gateway từ chối login |
| G04 | OIDC nonce/state/PKCE sai | Gateway từ chối login |
| G05 | Anonymous gửi X-Authenticated-User Admin | Không có Admin Authentication |
| G06 | Alice gửi X-Authenticated-Roles ADMIN | Không có role elevation |
| G07 | Client gửi X-Verified-Subject admin-test | Gateway ignore/replace |
| G08 | Duplicate identity headers khác nhau | Reject hoặc sanitize; không admin |
| G09 | Mixed-case identity headers | Không bypass |
| G10 | Underscore/hyphen header ambiguity | Reject/normalize |
| G11 | Client gửi Connection: X-Authenticated-User | No proxy bypass |
| G12 | Long/malformed identity header | Bounded fail-closed |
| G13 | Direct backend connection từ untrusted pod | Network deny |
| G14 | Wrong mTLS gateway identity | Handshake/access deny |
| G15 | Valid gateway mTLS nhưng no user credential | API reject user auth |
| G16 | Forged X-Forwarded-Host attacker.invalid | Canonical host preserved |
| G17 | Forged Forwarded proto/http | Public HTTPS preserved |
| G18 | Forged XFF=127.0.0.1 | No IP allowlist bypass |
| G19 | Conflicting Forwarded/XFH | Reject/normalize |
| G20 | Multi-hop trusted proxy chain | Correct origin/IP interpretation |
| J01 | Signed JWT iss/aud/exp/nbf valid | Backend authenticated |
| J02 | Wrong JWT signature | Reject |
| J03 | Wrong issuer | Reject |
| J04 | Wrong audience even with valid signature | Reject |
| J05 | Expired token | Reject |
| J06 | nbf future | Reject |
| J07 | Unknown kid/jku external | No untrusted key acceptance |
| J08 | Valid Alice token + forged Admin headers | Identity remains Alice |
| J09 | Token only for gateway, not backend | Reject wrong audience |
| J10 | Token valid but missing read scope | Deny read |
| J11 | Approved read scope, other tenant resource | Domain deny |
| J12 | Approved approve scope, local account inactive | Deny |
| J13 | Rotated JWT signing key overlap | Accept only approved key phase |
| J14 | Revoked signing key | Reject after trust removal |
| J15 | Replayed bearer token | Handle under documented replay policy |
| S01 | SAML Destination/Recipient mismatch | Gateway reject assertion |
| S02 | SAML signed A, unsigned Assertion B | Never consume B attributes |
| S03 | IdP initiated when disabled | Reject unsolicited login |
| S04 | SAML → internal JWT subject mapping | Correct issuer+stable subject |
| S05 | OIDC → internal JWT subject mapping | Correct iss+sub |
| B01 | Browser session cookie lost after redirect | No anonymous privilege |
| B02 | Browser CSRF missing on state-changing POST | Reject |
| B03 | CORS preflight blocked | Diagnose as CORS, not role |
| B04 | OAuth2 redirect_uri influenced by forged Host | No attacker redirect |
| B05 | Auth service unavailable | Protected routes fail closed |
| B06 | Gateway restart/rollout across pods | Sessions and trust maintained |
| B07 | Wrong tenant from URL/header | Domain deny |
| B08 | Logs show raw token/private key | Security regression; block release |
| B09 | Header spoof result only MockMvc passing | Not enough: gateway E2E required |
| B10 | Unknown API route/method | Deny by default |

**Cách đánh giá:** Với các negative tests phải chứng minh **không có authenticated Admin principal và không có tài nguyên bị lộ**, không chỉ một HTTP code. Test cũng cần ít nhất một positive request được phép để tránh “mọi request đều bị chặn” mà tưởng security đã đúng.

## 25. Kế hoạch quan sát và vận hành

Các sự kiện nên phân loại:
- Gateway login success/failure theo OIDC/SAML2 registration.
- Gateway rejected inbound identity headers.
- Gateway auth-service timeout/unavailable.
- Direct-backend/mTLS unauthorized service identity.
- Backend invalid JWT signature/issuer/audience/time.
- Backend authorization denied do scope/tenant.
- Proxy forwarded header conflict/invalid Host.
- Session cookie/callback correlation errors.
- Unexpected elevated authority grants.
- Key rotation/JWKS refresh and certificate changes.

### 25.1. Logging không lộ dữ liệu

Một log mẫu đã sanitize:
~~~text
trace=gw-01 stage=gateway-auth result=SUCCESS protocol=OIDC
trace=api-02 stage=jwt-validation result=ACCEPT issuer=trusted-lab
trace=api-02 stage=authorization result=DENY reason=TENANT_MISMATCH
trace=gw-03 stage=header-sanitization result=DROP_UNTRUSTED_IDENTITY
trace=gw-04 stage=auth-service result=UNAVAILABLE action=FAIL_CLOSED
~~~

Đây là format đề xuất, không phải log tự động của Spring. **Không log raw Authorization Bearer, SAMLResponse, session cookies, ID Token, private keys hoặc full claims**. Token fingerprints, trace IDs và user pseudonyms phải được quản lý theo privacy policy. Tránh metrics labels high-cardinality như raw IP, host, subject hoặc XFF contents.

### 25.2. Metrics và alert

Đề xuất:
- `gateway_authn_success_total`.
- `gateway_authn_failure_total`.
- `identity_header_spoof_rejected_total`.
- `backend_invalid_jwt_total{reason}`.
- `backend_authz_denied_total{policy}`.
- `backend_mtls_rejected_total`.
- `gateway_auth_service_unavailable_total`.
- `proxy_header_conflict_total`.
- `unexpected_privileged_grants_total`.

Tên này là **metrics tùy triển khai**, không mặc định framework. Tăng 403 là bình thường nếu có attacker probes; cần so ratio với user requests và cảnh báo unexpected privileged access hơn là mục tiêu 403=0.

## 26. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Header Admin từ client biến thành user Admin | Gateway echo client header | Strip/overwrite, fix auth service contract |
| Preauth app bị truy cập trực tiếp | Backend port/NetworkPolicy mở | Block direct path và mTLS |
| JWT hợp lệ tại gateway nhưng backend 401 | Audience khác, issuer/JWKS sai | Token exchange/issuer+aud config |
| JWT signature pass nhưng backend 403 | Scope/tenant/role thiếu | Authz mapper/domain policy |
| OIDC login loop | Session/cookie/state/proxy mismatch | Check SameSite, redirect_uri, trusted origin |
| SAML Recipient mismatch | Gateway ACS public URL sai | Fix Forwarded/metadata, không bỏ validator |
| Test header fake IP được ghi là localhost | XFF parsing tin first hop | Normalize trusted chain |
| Service mesh bypass | Internal workload can access API | Service identity and sidecar policy |
| Unknown kid vẫn accepted | Dynamic JWK trust sai | Pin issuer and JWKS |
| Browser sends both Cookie and Bearer | Identity ambiguity | Explicit priority/policy, tests |
| No JWT for backend after SAML login | Gateway chưa issue/exchange token | Internal token service |
| Header forged bị 403 do CSRF | Chưa kiểm đúng auth layer | Add valid CSRF test to isolate authz |
| Proxy returns 403 without backend logs | Gateway/WAF rejected request | Check gateway traces |
| One node sees different user/roles | Session/cache/config drift | Compare deployment revision and key sets |
| JWT issuer valid nhưng tenant wrong | Local identity link sai | Issuer+sub and membership check |
| Empty X-Verified-Subject yields anonymous | Preauth defaults not fail-closed | Require principal and reject |
| SAML signature valid but wrong user | Converter/XSW issue | Verify protected Assertion provenance |
| Production trusts test issuer | Misconfigured secrets/JWKS | Block release and rotate trust |
| CSRF disabled accidentally on browser routes | Mixed chain scope wrong | Separate stateless/browsers chains |
| TokenRelay passes token for another API | Missing audience validation | Reject/token exchange |
| Auth service down but cached user remains | Fallback/caching misdesign | Fail closed/revocation-aware cache |

## 27. Anti-patterns nghiêm trọng

1. Chỉ có code `request.getHeader("X-Authenticated-User")` rồi tạo Authentication mà không kiểm gateway.
2. Gán role từ `X-Authenticated-Roles` hoặc `X-Groups` do browser gửi.
3. Backend public, nhưng tin rằng “gateway đã login hết rồi”.
4. Dùng `X-Forwarded-For: 127.0.0.1` để coi request là local admin.
5. Bật `server.forward-headers-strategy: framework` khi backend vẫn mở trực tiếp.
6. Strip `X-Forwarded-Host` mà bỏ qua `Forwarded` chuẩn.
7. Proxy dùng raw `$http_x_authenticated_user` để tạo trusted subject header.
8. Proxy dùng `$proxy_add_x_forwarded_for` ở public edge mà không sanitize client XFF.
9. Gateway TokenRelay mà backend không kiểm `aud`.
10. Dùng OIDC ID Token thay OAuth2 access token để gọi API.
11. Tin JWT do token tự chỉ `jku`/arbitrary issuer URL.
12. Cấp `ROLE_ADMIN` khi nhận `groups=["Admin"]` mà không approved mapping.
13. Dựa vào HTTP `X-Tenant-Id` để quyết định tenant membership.
14. Tắt SAML signature/Recipient/Destination khi proxy đổi hostname.
15. Tắt OIDC state/nonce chỉ vì cookie sau gateway bị lỗi.
16. Tắt CSRF toàn browser SSO để làm POST pass.
17. Không chống header duplicates/case/underscore ambiguity.
18. Coi mTLS gateway service identity là end-user authentication tự động.
19. Coi JWT có `jti` là đã có replay protection mặc định.
20. Chỉ test MockMvc với mocked user rồi gọi là kiểm header spoofing E2E.
21. Tự phát minh custom signed headers/token format trong production.
22. Cho auth-service outage thành anonymous fallback ở protected endpoint.
23. In raw tokens/SAML XML/cookies vào application logs.
24. Đánh giá an toàn chỉ bằng 401/403 mà không có positive path.
25. Xóa backend authorization vì “gateway đã xử lý permissions”.

## 28. Checklist triển khai cuối

- [ ] Public gateway hostname/TLS/SNI đã approved và unknown hosts bị reject.
- [ ] Gateway xác minh OIDC/SAML2/CAS/Kerberos theo đúng trusted IdP contract.
- [ ] Gateway loại bỏ inbound identity headers ở edge trước auth.
- [ ] Gateway loại bỏ/normalize `Forwarded` và `X-Forwarded-*` đầu vào.
- [ ] Duplicates/case/underscore/hop-by-hop spoofing được kiểm.
- [ ] Backend không có public NodePort/LoadBalancer/direct port.
- [ ] Kubernetes/Docker/Firewall chỉ cho trusted gateway workload.
- [ ] mTLS workload identity được kiểm ở environments cần zero-trust.
- [ ] Đã chọn rõ JWT/token exchange hay legacy preauth header, không trộn.
- [ ] Với JWT: backend verify signature, trusted issuer/JWKS, `aud`, `exp`, `nbf`.
- [ ] Với JWT: `TokenRelay` chỉ dùng token có audience backend hoặc exchange.
- [ ] Với legacy header: verified subject chỉ xuất từ auth service, không browser.
- [ ] Với legacy header: no missing-principal fallback và authorities allowlisted.
- [ ] Không có token nội bộ tự tạo không tuân JOSE/JWT chuẩn.
- [ ] Local identity namespace gồm issuer/realm và stable subject.
- [ ] Scope/roles mapping không tự cấp elevated privileges.
- [ ] Tenant/resource owner policy chạy ở backend.
- [ ] Public OIDC redirect_uri và SAML ACS/Destination/Recipient chính xác.
- [ ] Proxy forwarding không ảnh hưởng authn/tenant trust.
- [ ] CSRF/Session/SameSite đúng browser-vs-bearer architecture.
- [ ] Positive valid Alice và approved admin tests pass.
- [ ] Anonymous và authenticated forged-role tests deny elevation.
- [ ] Direct backend bypass test deny ở network/mTLS.
- [ ] Wrong issuer/aud/key/expiry JWT tests deny.
- [ ] Full gateway E2E header spoof/duplicate/Forwarded tests pass.
- [ ] Spring MockMvc tests không bị dùng thay real crypto/ingress tests.
- [ ] Key rotation/revocation policy và JWKS cache đã test.
- [ ] Auth service timeout/error fail closed.
- [ ] Secrets/tokens không xuất hiện trong source/logs/artifacts.
- [ ] Có owner, monitoring, incident playbook, canary và rollback.
- [ ] Không bỏ Spring Security validators để làm một request test pass.

## 29. Câu hỏi ôn tập

1. **Gateway login thành công có bảo đảm backend an toàn không?** Không nếu backend tin header giả hoặc bỏ authorization.
2. **X-Authenticated-User có là credential không?** Không, là text; chỉ có giá trị preauth khi protected trust boundary bảo đảm nguồn.
3. **Sự khác biệt giữa mTLS gateway identity và JWT user identity?** mTLS chứng minh workload, JWT user token chứng minh subject/issuer/audience và claims.
4. **Tại sao cần strip header trước khi auth?** Để giá trị do browser khai không được xem như kết quả đã xác minh.
5. **Có thể trust X-Forwarded-For để cấp ROLE_ADMIN không?** Không.
6. **JWT cần kiểm gì ngoài signature?** Trusted issuer, audience, expiry/not-before, scope/policy và subject.
7. **TokenRelay tự đổi audience token?** Không.
8. **Khi nào dùng token exchange?** Khi token nguồn không dành cho backend resource.
9. **Có thể dùng OIDC ID Token như access token API?** Không theo mặc định; mục đích/protocol khác.
10. **SAML Gateway xác minh gì trước khi phát subject?** Signed Assertion/Response, issuer, audience, recipient/destination, conditions, correlation.
11. **SAML NameID lấy từ raw XML trước validation có nguy hiểm không?** Có, identity spoof/XSW.
12. **Nếu user có reports.read nhưng report của tenant khác?** Domain authorization deny.
13. **Nếu request header admin fake nhưng JWT là Alice?** Backend phải giữ Alice.
14. **Nếu backend bị gọi trực tiếp từ pod khác và trả 401?** JWT defense có hiệu quả nhưng network boundary gateway-only chưa đạt.
15. **Có thể tin mọi IP private như gateway?** Không.
16. **Vì sao cần kiểm duplicate identity headers?** Proxy và servlet parser có thể chọn giá trị khác nhau.
17. **ForwardedHeaderFilter tự xác minh proxy trusted không?** Không.
18. **Cách bảo vệ public origin?** Gateway strip/reconstruct forwarding metadata + exact host allowlist.
19. **Tại sao không tắt CSRF cho mọi route?** Browser session/cookie flows vẫn có CSRF risk.
20. **JWT jti tự ngăn replay?** Không, cần cache/revocation or proof-of-possession policy.
21. **Có nên tự thiết kế text-signing protocol trong production?** Không, dùng JWT/JOSE chuẩn và thư viện được kiểm định.
22. **MockMvc jwt() có verify chữ ký thật?** Không, mock authorization context.
23. **Test gateway end-to-end phải chứng minh gì?** Forged headers không đổi identity/roles và valid path vẫn hoạt động.
24. **Metrics quan trọng?** Spoof rejection, invalid token reasons, authz deny, gateway auth availability.
25. **Khi auth service down phải làm gì?** Fail closed.
26. **Trong multi-IdP, trùng email có là cùng user không?** Không, cần issuer+stable subject link được duyệt.
27. **Khi signed JWT wrong audience nhưng đúng issuer?** Reject.
28. **Vì sao backend cần authz dù gateway đã xác thực?** Resource/tenant permission không đồng nghĩa login.
29. **Cần kiểm gì khi gateway thay ingress controller?** Header sanitization, network trust, callback origins, cookies, JWT/token exchange và regression E2E.
30. **Quy tắc tổng kết?** Không tin raw header; verify nguồn gateway lẫn end-user evidence, và enforce backend resource policy.

## 30. Nguồn tham khảo

- Spring Security – Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security – Servlet Architecture and SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – OAuth2 Resource Server JWT (issuer, audience, scope): https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – SAML2 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Framework – ForwardedHeaderFilter security considerations: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Boot – Reverse Proxy/Forward Headers: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Cloud Gateway – TokenRelay (WebFlux): https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html
- IETF RFC 7239 – Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- IETF RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- IETF RFC 8693 – OAuth 2.0 Token Exchange: https://www.rfc-editor.org/rfc/rfc8693
- OWASP – Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Session Management: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP – HTTP Security Headers: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- NGINX – proxy_set_header: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- Kubernetes – Network Policies: https://kubernetes.io/docs/concepts/services-networking/network-policies/

**Tổng kết:** Bảo vệ ứng dụng Spring Security phía sau authentication gateway là **thực hành kết hợp cả protocol authentication, network trust, header sanitization, backend token validation và resource authorization**. Không bao giờ tạo Authentication chỉ vì thấy `X-Authenticated-User` trong HTTP request. Phương án ưu tiên là gateway gửi **access token/JWT đúng audience** và backend verify chữ ký, issuer, exp/nbf cùng scopes, trong khi NetworkPolicy/mTLS chống bypass gateway; với legacy pre-auth cần đường truyền/workload identity được kiểm soát và header được tạo lại sau xác thực. Một hệ thống chỉ được nghiệm thu khi **valid users vẫn truy cập đúng tài nguyên, headers giả không nâng quyền, direct backend traffic bị chặn, wrong tokens bị reject và không có secrets lộ qua log/CI**.
