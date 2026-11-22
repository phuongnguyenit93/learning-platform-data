# 32.1. HTTPS, tên miền công khai và Redirect URI theo môi trường

## 1. Bài toán thực tế: OIDC Login chạy ở local nhưng lỗi sau khi triển khai

Một ứng dụng **Spring Boot + Spring Security OAuth 2.0/OIDC Client** hoạt động bình thường trên máy phát triển:

~~~text
Browser: http://localhost:8080
Login:   GET /oauth2/authorization/company
Callback: http://localhost:8080/login/oauth2/code/company
~~~

Sau khi triển khai lên production, người dùng truy cập:

~~~text
https://portal.example.com
~~~

nhưng ứng dụng Spring Boot thực sự đang chạy sau reverse proxy:

~~~text
Internet browser
     |
     | HTTPS :443
     v
Load balancer / Ingress
     |
     | HTTP :8080 (private network)
     v
Spring Boot application
~~~

Khi người dùng bấm “Đăng nhập bằng Company”, có thể xuất hiện:

- OpenID Provider (OP) báo <code>redirect_uri_mismatch</code>, vì Client sinh callback <code>http://portal-service:8080/login/oauth2/code/company</code> thay vì public HTTPS URL.
- Browser bị redirect tới <code>http://portal.example.com</code> dù người dùng bắt đầu bằng HTTPS.
- OP đã chấp nhận callback nhưng Spring Security không tìm được authorization request vì session cookie không được gửi.
- Staging và production dùng chung Client ID/redirect URIs, vô tình cho phép callback của môi trường này đi sang môi trường kia.
- URL sau logout quay về sai hostname hoặc HTTP.
- Một proxy tin <code>X-Forwarded-Host</code> do attacker gửi, làm ứng dụng phát sinh redirect tới tên miền không tin cậy.

Đây không chỉ là vấn đề “sửa URL”. Nó là ranh giới giữa **HTTPS, public origin, proxy headers, session cookie, OAuth2 authorization request và danh sách Redirect URI mà OP cho phép**.

> **Nguyên tắc chính:** Mỗi môi trường cần một public URL xác định, redirect URI đã đăng ký chính xác tại OP, cấu hình HTTPS/cookie phù hợp và cách xử lý forwarded headers chỉ tin proxy được kiểm soát. Không tắt <code>state</code>, issuer validation hoặc PKCE để né lỗi triển khai.

## 2. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **internal service URL**, **public base URL**, **OAuth2 redirect URI** và **OIDC issuer URI**.
2. Giải thích vì sao HTTPS và tên miền công khai ảnh hưởng trực tiếp tới Authorization Code Flow.
3. Dùng <code>{baseUrl}/login/oauth2/code/{registrationId}</code> đúng bối cảnh Spring Security.
4. Cấu hình redirect URI riêng cho local, staging và production trong cả Portal và OP.
5. Hiểu TLS termination, reverse proxy, <code>Forwarded</code> và <code>X-Forwarded-*</code>, cùng trust boundary của chúng.
6. Cấu hình <code>server.forward-headers-strategy</code> theo hạ tầng mà không mở Host header injection.
7. Cấu hình session cookies <code>Secure</code>, <code>HttpOnly</code>, <code>SameSite</code> cho browser OIDC Login.
8. Xử lý reverse proxy path prefix, nhiều instances, nhiều providers và multi-tenant hostnames.
9. Phân biệt callback <code>redirect_uri</code> với OIDC <code>post_logout_redirect_uri</code>.
10. Kiểm thử Authorization Code Flow qua public ingress và thiết lập runbook khi gặp <code>redirect_uri_mismatch</code>.

## 3. Bốn loại URL không được nhầm lẫn

Xét một triển khai:

~~~text
Public Portal:
    https://portal.example.com

Internal Portal service:
    http://portal-service.namespace.svc.cluster.local:8080

OIDC issuer / OpenID Provider:
    https://login.example-idp.com/realms/company

OAuth2 Redirect URI (registered at OP):
    https://portal.example.com/login/oauth2/code/company
~~~

| Tên | Chủ thể sử dụng | Vai trò | Có nên công khai cho browser? |
|---|---|---|---|
| **Public base URL** | Browser, OP redirect, reverse proxy | Scheme + hostname + port + context path của Portal bên ngoài | Có |
| **Internal service URL** | Proxy/cluster/private network | Địa chỉ backend Spring Boot | Thông thường không |
| **OIDC issuer URI** | Spring Security OIDC Client | Định danh OP, dùng Discovery và kiểm tra ID Token <code>iss</code> | Phải là URL hợp lệ theo cấu hình OP |
| **OAuth2 redirect URI** | OP khi phát authorization response | Browser callback về Client | Có, OP phải cho phép chính xác |
| **Post-logout redirect URI** | OP sau RP-Initiated Logout | Browser quay về Portal sau logout | Có, đăng ký theo OP policy |
| **OAuth2 authorization initiation URI** | Browser gọi tại Portal | Bắt đầu login ở <code>/oauth2/authorization/{registrationId}</code> | Có |

### 3.1. Public origin và base URL

Trong browser security model:

~~~text
origin = scheme + host + port
~~~

Hai địa chỉ:

~~~text
https://portal.example.com
http://portal.example.com
~~~

**khác origin** vì scheme khác nhau. Hai địa chỉ:

~~~text
https://portal.example.com
https://portal.example.com:8443
~~~

**khác origin** vì port khác nhau.

Public base URL có thể bao gồm context path ngoài origin:

~~~text
https://portal.example.com/app
~~~

nếu reverse proxy thực sự phục vụ ứng dụng ở dưới <code>/app</code>.

### 3.2. Redirect URI không phải issuer URI

Sai:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: https://portal.example.com
~~~

nếu OP thật là <code>https://login.example-idp.com/realms/company</code>. Issuer phải chỉ tới **OP**, không phải ứng dụng Client.

Ngược lại, Redirect URI phải trỏ về **Portal callback**, không phải Token Endpoint hay trang login của OP.

### 3.3. Registration ID không phải Client ID

Ví dụ:

~~~yaml
registration:
  company:
    client-id: portal-production
~~~

Trong đó:

~~~text
registrationId = company
client_id      = portal-production
~~~

Mặc định callback path của Spring Security dùng <code>registrationId</code>:

~~~text
/login/oauth2/code/company
~~~

chứ không tự thay <code>company</code> bằng <code>portal-production</code>.

## 4. Authorization Code Flow: nơi Redirect URI được sử dụng

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant B as Browser
    participant Proxy as Public HTTPS Ingress
    participant RP as Spring Security Portal
    participant OP as OpenID Provider

    User->>B: Truy cập https://portal.example.com
    B->>Proxy: GET /oauth2/authorization/company qua HTTPS
    Proxy->>RP: Forward nội bộ qua HTTP + trusted public-origin metadata
    RP->>RP: Tạo OAuth2AuthorizationRequest, state/PKCE/nonce
    RP-->>Proxy: 302 OP /authorize với redirect_uri=https://portal.example.com/login/oauth2/code/company
    Proxy-->>B: Redirect OP
    B->>OP: Authorization request, client_id, redirect_uri, state
    OP->>OP: Kiểm tra Client registration và Redirect URI
    OP-->>B: 302 tới HTTPS callback với code + state
    B->>Proxy: GET /login/oauth2/code/company?code=...&state=... (HTTPS)
    Proxy->>RP: Callback + session cookie
    RP->>RP: Kiểm tra state và authorization request đã lưu
    RP->>OP: Server-to-server Token Request, code + client authentication/PKCE
    OP-->>RP: Tokens
    RP->>RP: Validate ID Token và thiết lập Authentication
    RP-->>B: Redirect về trang được bảo vệ /home
~~~

Một yêu cầu khởi tạo authorization ở OP có thể chứa:

~~~text
response_type=code
client_id=portal-production
scope=openid profile
redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
state=<random-value>
code_challenge=<derived-from-verifier>
code_challenge_method=S256
~~~

<code>state</code>, nonce và PKCE data là dữ liệu bảo mật của một giao dịch authorization, không được hardcode theo môi trường hoặc ghi vào logs ở dạng raw.

## 5. HTTPS là yêu cầu thiết kế, không chỉ là biểu tượng ổ khóa

### 5.1. Vì sao Authorization Code Flow cần HTTPS?

Khi browser được redirect từ OP về Client:

~~~text
https://portal.example.com/login/oauth2/code/company?code=...&state=...
~~~

authorization code là credential ngắn hạn, còn state liên kết flow với browser session. HTTPS bảo vệ đường truyền browser ↔ Portal khỏi việc nghe lén/sửa đổi trên mạng.

HTTPS còn quan trọng với:

- Session cookies.
- Redirect responses.
- CSRF protection của browser session.
- Trang xác nhận account linking, consent hoặc reauthentication.
- API endpoints do BFF/Web app phục vụ.

Không đưa authorization code, client secret hoặc tokens vào URL HTTP công khai.

### 5.2. TLS có thể kết thúc ở proxy

Có hai mô hình:

~~~text
A. End-to-end TLS:
Browser --HTTPS--> Ingress --HTTPS/mTLS--> Spring Boot

B. TLS termination:
Browser --HTTPS--> Ingress --HTTP on trusted private network--> Spring Boot
~~~

Mô hình B có thể chấp nhận theo kiến trúc mạng/trust policy; nhưng:

- Proxy phải thiết lập chính xác public scheme/host/port.
- Kênh ingress → app phải nằm trong trust boundary được bảo vệ.
- Không phơi HTTP backend trực tiếp ra Internet.
- Cần cân nhắc TLS/mTLS nội bộ khi yêu cầu compliance, zero-trust hoặc multi-tenant cluster.
- Browser vẫn phải nhận HTTPS redirect, không bị app trả URL nội bộ hoặc downgrade HTTP.

### 5.3. TLS certificate và hostname

Certificate của public ingress phải hợp lệ cho tên miền browser dùng:

~~~text
portal.example.com
~~~

Kiểm tra:

1. Chuỗi chứng chỉ tin cậy.
2. Subject Alternative Name (SAN) chứa đúng hostname.
3. Chứng chỉ chưa hết hạn.
4. TLS protocols/ciphers theo policy.
5. Gia hạn tự động có giám sát.

Tương tự, JVM của Portal phải **tin cậy TLS certificate của OP Token/Discovery/JWKS endpoints**. Không dùng <code>trust-all</code> HTTP client chỉ vì một chứng chỉ ở staging không hợp lệ.

### 5.4. HSTS

HSTS giúp browser chỉ dùng HTTPS cho host đã học chính sách:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Nhưng <code>includeSubDomains</code> chỉ nên bật khi **mọi subdomain nằm trong phạm vi đều sẵn sàng HTTPS**. <code>preload</code> có điều kiện vận hành nghiêm ngặt; không bật chỉ để “an toàn hơn” khi chưa kiểm kê toàn bộ domain.

Trong Spring Security, HSTS có thể được bật theo defaults cho HTTPS requests tùy configuration. Đừng dựa vào behavior của app khi TLS terminate tại proxy mà Spring Boot vẫn hiểu request là HTTP; phải cấu hình nhận biết scheme đúng và kiểm tra response thực từ public ingress.

## 6. Redirect URI matching: chính xác đến scheme, host, port và path

Với OAuth2 Authorization Code Flow, OP phải xác minh Redirect URI theo registration và yêu cầu security profile. Với redirect URIs đã đăng ký đầy đủ, tiêu chuẩn bảo mật hiện đại ưu tiên **exact string matching** theo các ngoại lệ đặc thù, ví dụ port động cho loopback redirect của native apps.

Cho OP registration:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

Các URL sau **không được tùy tiện xem là tương đương**:

| Redirect URI được gửi | Khác biệt | Có nên OP chấp nhận? |
|---|---|---|
| <code>https://portal.example.com/login/oauth2/code/company</code> | Khớp registration | Có |
| <code>http://portal.example.com/login/oauth2/code/company</code> | Sai scheme | Không |
| <code>https://portal.internal/login/oauth2/code/company</code> | Sai host | Không |
| <code>https://portal.example.com:8443/login/oauth2/code/company</code> | Sai port | Không nếu chưa đăng ký |
| <code>https://portal.example.com/app/login/oauth2/code/company</code> | Thêm path prefix | Không nếu chưa đăng ký |
| <code>https://portal.example.com/login/oauth2/code/partner</code> | Sai registration callback | Không nếu chưa đăng ký |
| <code>https://staging.portal.example.com/login/oauth2/code/company</code> | Khác môi trường | Không nếu chưa đăng ký |
| <code>https://portal.example.com/login/oauth2/code/company/</code> | Trailing slash | Không nếu registration khác chuỗi |

### 6.1. Không dùng wildcard để né redirect_uri_mismatch

Ví dụ cấu hình quá rộng:

~~~text
https://*.example.com/*
~~~

hoặc:

~~~text
https://portal.example.com/*
~~~

có thể mở đường chuyển authorization code tới những host/path do attacker kiểm soát, nhất là khi tồn tại subdomain takeover, open redirect hoặc route có thể thay đổi đích. Tránh wildcard khi có thể sử dụng **exact redirect URIs** cho từng environment.

### 6.2. Fragment không phải nơi nhận authorization code

Không khai báo:

~~~text
https://portal.example.com/login/oauth2/code/company#callback
~~~

làm Redirect URI cho Authorization Code Flow. URI fragments có semantics browser riêng, không được gửi lên server như path/query của HTTP request; OAuth2 Redirect URI registration không được chứa fragment theo quy tắc giao thức.

### 6.3. Query trong registered redirect URI

Một số providers cho phép query cố định trong Redirect URI theo quy tắc và chính sách riêng. Nhưng không dùng query chứa token, session ID hoặc dữ liệu tenant do browser kiểm soát để “động hóa” callback.

Thông tin nghiệp vụ để khôi phục navigation sau login có thể được lưu server-side cùng authorization transaction hoặc SavedRequest; <code>state</code> phải tiếp tục được bảo vệ tính toàn vẹn và chống CSRF.

## 7. Spring Security mặc định dựng Redirect URI ra sao?

Trong Spring Boot OAuth2 Client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-production
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://login.example-idp.com/realms/company
~~~

Với request có public origin:

~~~text
https://portal.example.com
~~~

và <code>registrationId=company</code>, template tạo:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

### 7.1. Các placeholders quan trọng

Spring Security hỗ trợ redirect URI template variables như:

~~~text
{baseScheme}
{baseHost}
{basePort}
{basePath}
{baseUrl}
{registrationId}
~~~

<code>{baseUrl}</code> phản ánh phần URL của request mà framework coi là external base URL, sau khi áp dụng forwarded header handling thích hợp. Nó không tự biết tên miền production nếu request đi qua proxy mà thiếu hoặc sai forwarding metadata.

### 7.2. Default callback endpoint

Servlet OAuth2 Login mặc định nhận callback dạng:

~~~text
GET /login/oauth2/code/{registrationId}
~~~

và initiation:

~~~text
GET /oauth2/authorization/{registrationId}
~~~

Nếu tùy biến base URI của <code>OAuth2LoginAuthenticationFilter</code> hoặc authorization request resolver, phải đồng bộ:

1. <code>ClientRegistration.redirectUri</code>.
2. OP redirect URI allowlist.
3. Callback processing matcher/filter.
4. Reverse proxy path mapping.
5. Tests cho tất cả environments.

Không chỉ sửa YAML Redirect URI sang <code>/auth/callback</code> mà giữ Spring Security callback filter ở <code>/login/oauth2/code/*</code>.

### 7.3. Vì sao {baseUrl} bị sai?

Nếu app thấy request:

~~~text
scheme=http
host=portal-service
port=8080
~~~

thì <code>{baseUrl}</code> có thể thành:

~~~text
http://portal-service:8080
~~~

dù browser đang ở <code>https://portal.example.com</code>. Phải sửa **trusted forwarded headers/public base URL** hoặc quyết định cấu hình callback cố định theo môi trường — không cần nới wildcard tại OP.

## 8. Cấu hình riêng local, staging và production

Một ma trận thực tế:

| Thuộc tính | Local | Staging | Production |
|---|---|---|---|
| Public Portal | <code>http://localhost:8080</code> | <code>https://portal.staging.example.com</code> | <code>https://portal.example.com</code> |
| Issuer | <code>http://localhost:18081/realms/it</code> | <code>https://sso.staging.example.com/realms/company</code> | <code>https://sso.example.com/realms/company</code> |
| Client ID | <code>portal-local</code> | <code>portal-staging</code> | <code>portal-production</code> |
| Client secret | Test-only | Staging secret store | Production secret store |
| Redirect URI | <code>http://localhost:8080/login/oauth2/code/company</code> | <code>https://portal.staging.example.com/login/oauth2/code/company</code> | <code>https://portal.example.com/login/oauth2/code/company</code> |
| Session cookie Secure | Phụ thuộc HTTP local | <code>true</code> | <code>true</code> |
| TLS cert | Local exception | Staging TLS cert | Production TLS cert |
| Dữ liệu người dùng | Giả/test | Test/staging account | Production identities |

### 8.1. Tại sao nên tách ClientRegistration tại OP?

Một Client ID/secret dùng chung staging/production có thể gây:

- Cross-environment redirect allowlist lớn và khó kiểm soát.
- Test hoặc lỗi staging ảnh hưởng production grants.
- Secret rotation của staging gây outage production.
- Lẫn identity/consent/refresh token policies.
- Khó audit callback nào thuộc environment nào.

**Khuyến nghị:** Tách client registration và secrets ít nhất giữa staging và production. Với provider hỗ trợ realms/tenants riêng, có thể tách cả issuer, users và policies.

### 8.2. Không chia sẻ production credentials trong local tests

Local nên dùng OP container/sandbox, Client ID và tài khoản test. Không copy <code>client_secret</code>, refresh tokens hay private keys production vào developer laptop chỉ để tái hiện login.

### 8.3. Redirect URI riêng từng environment

Khi người dùng chọn login từ staging:

~~~text
authorization request:
  client_id=portal-staging
  redirect_uri=https://portal.staging.example.com/login/oauth2/code/company
~~~

Khi từ production:

~~~text
authorization request:
  client_id=portal-production
  redirect_uri=https://portal.example.com/login/oauth2/code/company
~~~

OP registration tương ứng phải allow đúng URL. Không dựa trên quy ước “OP tự đoán staging qua hostname”.

## 9. Spring Boot profiles và biến môi trường

### 9.1. Một mẫu cấu hình dùng biến môi trường

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Giải thích:

- <code>OIDC_CLIENT_ID</code>, <code>OIDC_CLIENT_SECRET</code>, <code>OIDC_ISSUER_URI</code> được inject theo environment.
- <code>redirect-uri</code> dùng public base URL của request, sau khi xử lý headers đúng trust boundary.
- <code>server.forward-headers-strategy=framework</code> là **một lựa chọn** cho hạ tầng proxy được kiểm soát, không phải cấu hình cần bật trên mọi ứng dụng.
- Session cookie <code>Secure=true</code> hợp lý cho staging/production HTTPS. Với HTTP local thuần, cần dùng profile riêng hoặc HTTPS local test.
- <code>same-site=lax</code> thường tương thích top-level GET callback; với <code>response_mode=form_post</code> cần đánh giá khác.

**Không đưa client secret vào <code>application.yml</code> production lưu trong Git.** Sử dụng secret store của môi trường và giới hạn quyền đọc.

### 9.2. application-local.yml

Với HTTP localhost:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: none
  servlet:
    session:
      cookie:
        secure: false
        http-only: true
        same-site: lax

spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: http://localhost:18081/realms/it
        registration:
          company:
            client-id: portal-local
            client-secret: local-test-only-secret
~~~

Ở đây các giá trị chỉ dùng trong một local OP test/realm cô lập. **HTTP localhost là ngoại lệ phát triển có kiểm soát**, không phải lý do cho phép production redirect URI dùng HTTP. Đừng đưa profile local vào artifact production ở trạng thái active.

### 9.3. application-staging.yml và application-prod.yml

Hai profiles có thể chia sẻ template nhưng khác <code>OIDC_ISSUER_URI</code>, Client ID, secrets, public hosts và cookie/TLS policies. Nên giữ secrets trong environment/secret manager hơn là chép thẳng vào profile files.

Trong deployment pipeline, validate cấu hình trước khi cho traffic:

~~~text
activeProfile=prod
publicBaseUrl=https://portal.example.com
oidcRegistrationId=company
issuer=https://sso.example.com/realms/company
redirectUri=https://portal.example.com/login/oauth2/code/company
~~~

Chỉ log những giá trị không nhạy cảm; không log client secret, authorization code, state, nonce hoặc token.

## 10. Forwarded headers: cầu nối giữa HTTPS bên ngoài và HTTP nội bộ

Reverse proxy thường truyền thông tin:

~~~http
Host: portal.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: portal.example.com
X-Forwarded-Port: 443
X-Forwarded-For: 203.0.113.10
~~~

Hoặc header theo RFC 7239:

~~~http
Forwarded: for=203.0.113.10;proto=https;host=portal.example.com
~~~

<code>203.0.113.10</code> là địa chỉ ví dụ. Các headers trên mô tả request **mà proxy đã xử lý**.

### 10.1. Tác dụng

Khi backend trực tiếp nhận HTTP ở port 8080, những thông tin từ proxy giúp framework biết browser đã truy cập bằng HTTPS trên public host.

Điều này có thể ảnh hưởng:

- <code>request.getScheme()</code>.
- <code>request.isSecure()</code>.
- <code>request.getServerName()</code> và port.
- Redirect URL được Spring Security sinh ra.
- Absolute links, Location headers và URL building.
- Cookie/security behavior dựa trên scheme.

### 10.2. Trust boundary rất quan trọng

Nếu một client ngoài Internet tự gửi:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

và backend tin header này, <code>{baseUrl}</code> có thể bị nhiễm:

~~~text
https://attacker.example
~~~

Đây là rủi ro Host header/forwarded header injection, có thể dẫn tới bad redirects, poisoning, hoặc ảnh hưởng authorization redirect URI generation.

**Không bật trust mọi X-Forwarded-* headers từ bất kỳ IP nào.**

### 10.3. Mô hình tin cậy đúng

Một kiến trúc an toàn hơn:

~~~text
Untrusted browser
    |
    v
Trusted edge proxy:
  - Chỉ phục vụ known hostnames
  - Loại bỏ/ghi đè forwarded headers do client gửi
  - Thiết lập scheme/host/port từ kết nối đã xác minh
    |
    v
Private application network:
  - Chỉ edge proxy được kết nối tới app
  - App sử dụng forwarded metadata đã được proxy làm sạch
~~~

Nếu có **nhiều proxy hops**, phải xác định rõ proxy nào set/append/strip từng header. Header chain không được mù quáng tin giá trị ngoài cùng chưa xác thực.

### 10.4. server.forward-headers-strategy

Trong Spring Boot 3.x, một số lựa chọn:

| Giá trị | Ý nghĩa | Sử dụng khi |
|---|---|---|
| <code>none</code> | Không tự xử lý forwarded headers qua Boot strategy | Backend trực tiếp phục vụ public traffic hoặc có xử lý tùy biến khác |
| <code>native</code> | Dùng khả năng native của web server/container | Hạ tầng/container hỗ trợ và cấu hình rõ trusted proxies |
| <code>framework</code> | Dùng hỗ trợ ở tầng Spring Framework | Muốn Spring nhận forwarded headers trong môi trường proxy tin cậy |

Ví dụ:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Với Servlet, Spring có <code>ForwardedHeaderFilter</code> hoặc cơ chế tương ứng do Boot auto-configuration cung cấp; với Reactive có các mechanisms phù hợp WebFlux.

**Không đồng thời bật nhiều bộ xử lý Forwarded khác nhau mà chưa kiểm tra**, vì việc double-processing hoặc proxy trust sai có thể tạo scheme/host/path không mong muốn.

### 10.5. native không có nghĩa tự tin mọi client

Khi dùng <code>native</code> với Tomcat hoặc server khác, cần cấu hình proxy trust/IP ranges hợp lệ theo container/version. Không chỉ bật <code>native</code> rồi giả định requests trực tiếp từ Internet không thể làm giả forwarded headers.

## 11. Reverse proxy NGINX: cấu hình minh họa

Giả sử public host:

~~~text
portal.example.com
~~~

và Spring Boot chạy:

~~~text
http://127.0.0.1:8080
~~~

Một cấu hình **rút gọn, chỉ để hiểu trust boundary**:

~~~nginx
# Default server trong cấu hình thực tế nên từ chối unknown hosts.
server {
    listen 443 ssl;
    server_name portal.example.com;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;

        proxy_set_header Host portal.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host portal.example.com;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;

        # Không forward một RFC 7239 Forwarded header do client tự gửi.
        proxy_set_header Forwarded "";
    }
}
~~~

Đây **không phải file NGINX production hoàn chỉnh**: còn cần HTTP-to-HTTPS redirect, default-server reject, TLS policy, proxy timeouts, limits và giám sát. Đặc biệt, nếu proxy nằm sau một edge load balancer khác, giá trị <code>https</code> và <code>$remote_addr</code> phải được suy ra từ **trusted hops** thật, không hardcode sai.

### 11.1. Vì sao set Host cố định trong ví dụ?

<code>Host</code> là dữ liệu client có thể gửi. Dùng một hostname đã allowlist ở edge giúp tránh việc request lạ tới virtual host này mang Host tùy ý rồi được ứng dụng dùng làm public base.

Khi phục vụ **nhiều hostnames** bằng một ingress, cần virtual host routing/allowlist tường minh; không sao chép cấu hình host cố định cho tất cả tenants.

### 11.2. Tránh public access trực tiếp tới backend

Nếu attacker có thể gọi:

~~~text
http://public-ip:8080/
~~~

và tự đặt <code>X-Forwarded-Host</code>, ứng dụng có thể tin vào metadata giả. Backend cần bind private interface, firewall/security groups hoặc Kubernetes NetworkPolicy phù hợp.

### 11.3. Proxy không sửa authorization code

Proxy chỉ forward callback request; nó không được:

- Trích xuất code và đổi với OP thay cho Spring Security Client nếu kiến trúc không chủ đích.
- Ghi raw callback URL chứa <code>code</code>/<code>state</code> vào shared logs không kiểm soát.
- Bỏ query parameters của callback.
- Tự thay <code>state</code> hay <code>redirect_uri</code>.

## 12. Kubernetes Ingress và service port

Ví dụ Ingress đơn giản:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: portal
  namespace: portal-prod
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - portal.example.com
      secretName: portal-tls
  rules:
    - host: portal.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: portal-service
                port:
                  number: 8080
~~~

Giả định:

~~~text
Ingress: TLS :443 for portal.example.com
Service: portal-service:8080
Pod:     Spring Boot :8080
~~~

Cần cấu hình Ingress controller để:

1. Chỉ nhận host <code>portal.example.com</code> theo rules.
2. Quản lý TLS cert cho host này.
3. Thiết lập forwarded scheme/host/port đúng.
4. Loại bỏ/ghi đè inbound forwarded headers không tin cậy.
5. Không mở ứng dụng trực tiếp ra Internet ngoài ingress.

**Ingress manifest không tự bảo đảm mọi controller xử lý forwarded headers giống nhau.** Trao đổi với đội platform để biết trusted proxy chain, ingressClass và các annotations phù hợp với controller/version.

### 12.1. X-Forwarded-Prefix và app dưới /portal

Nếu bên ngoài:

~~~text
https://example.com/portal
~~~

nhưng backend phục vụ tại root:

~~~text
http://portal-service:8080/
~~~

thì proxy có thể strip <code>/portal</code> trước khi forward. Tùy kiến trúc, có thể cần:

~~~text
X-Forwarded-Prefix: /portal
~~~

và Spring Boot strategy xử lý đúng prefix, hoặc cấu hình <code>server.servlet.context-path=/portal</code> nếu backend thực sự phục vụ dưới path đó.

**Không cấu hình cả hai cách sao cho prefix bị nhân đôi.**

Callback public đúng có thể là:

~~~text
https://example.com/portal/login/oauth2/code/company
~~~

Trong khi callback route nội bộ vẫn là:

~~~text
/login/oauth2/code/company
~~~

Nếu app/ingress lắp ghép sai:

~~~text
https://example.com/portal/portal/login/oauth2/code/company
~~~

OP sẽ từ chối redirect URI hoặc browser callback đi vào 404.

### 12.2. Path rewrite phải giữ query string

Authorization response qua browser thường:

~~~text
/login/oauth2/code/company?code=C&state=S
~~~

Nếu rewrite drop query string, Spring Security không thể tìm state/code và login sẽ thất bại. Test cả public request và backend route, không chỉ test health endpoint.

## 13. Cookies: HTTPS, Secure, HttpOnly và SameSite

Spring Security OAuth2 Login thường dựa trên browser session để lưu authorization request và sau đó SecurityContext.

### 13.1. Cấu hình baseline cho HTTPS Portal

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Giải thích:

- **Secure:** browser chỉ gửi cookie qua HTTPS (ngoại lệ/behavior riêng của localhost và browser cần được test, không dùng làm production assumption).
- **HttpOnly:** JavaScript không trực tiếp đọc cookie; giảm một số rủi ro lộ session qua script.
- **SameSite=Lax:** thường cho phép session cookie trong top-level cross-site GET navigation từ OP về Portal.

**Không thuộc tính cookie nào thay thế OAuth2 <code>state</code>, PKCE hoặc CSRF protection cho POST nghiệp vụ.**

### 13.2. GET callback và SameSite=Lax

Một flow điển hình:

~~~text
Browser: Portal → OP → top-level GET callback Portal
~~~

Cookie <code>SameSite=Lax</code> thường được gửi khi browser quay về Portal bằng top-level GET navigation. Nhờ vậy Spring Security có thể khôi phục authorization request trong session và so sánh <code>state</code>.

### 13.3. OIDC response_mode=form_post

Với:

~~~text
response_mode=form_post
~~~

OP có thể đưa authorization response về Portal qua **cross-site POST**. <code>SameSite=Lax</code> thường không gửi session cookie trong trường hợp này, dẫn đến:

~~~text
authorization_request_not_found
invalid_state
~~~

Có thể cần <code>SameSite=None; Secure</code> hoặc một flow/correlation design khác. Nhưng:

- <code>SameSite=None</code> làm browser gửi cookie trong nhiều ngữ cảnh cross-site hơn.
- CSRF protection cho browser POST nghiệp vụ vẫn phải bật.
- Spring Security version có thể cần xử lý/CSRF matcher riêng cho POST callback.
- Không mặc định rằng chỉ đổi cookie sang None là đủ để hỗ trợ <code>form_post</code>.

### 13.4. Domain và Path

Cookie nên có phạm vi đủ hẹp:

~~~text
Host: portal.example.com
Path: /
~~~

Không tự dùng:

~~~text
Domain=.example.com
~~~

khi các subdomains không cùng trust boundary. Sibling subdomain bị chiếm quyền có thể ảnh hưởng cookie domain-wide.

Nếu Portal chạy dưới <code>/portal</code>, cần xem cookie Path/context/session strategy và callback path. Đừng mặc định cookie Path ở <code>/app</code> được browser gửi tới callback nằm ngoài path đó.

### 13.5. Cookie persistence trong cluster

Nếu HTTP session được lưu in-memory trên node A, callback vào node B có thể không tìm thấy authorization request dù browser gửi cookie đúng. Spring Session Redis/JDBC hoặc session affinity theo kiến trúc cần được thiết kế. **Cấu hình HTTPS đúng không giải quyết storage state phân tán**.

## 14. Authorization request, state và proxy trust

Khi user bắt đầu:

~~~text
GET /oauth2/authorization/company
~~~

Spring Security tạo <code>OAuth2AuthorizationRequest</code> và lưu trong repository (thường session-based trên Servlet).

Authorization request có các thuộc tính:

~~~text
authorizationUri
clientId
redirectUri
scopes
state
attributes (nonce, PKCE, registration context khi áp dụng)
~~~

### 14.1. Redirect URI injection không phải lỗi UI thuần túy

Nếu attacker ép backend dựng redirect URI dựa trên Host/forwarded headers chưa tin cậy:

~~~text
Host: attacker.example
X-Forwarded-Proto: https
~~~

Client có thể gửi authorization request về OP với redirect_uri sai. OP đăng ký strict URI có thể chặn, nhưng không nên coi OP là defense duy nhất. Phải enforce allowed hosts tại ingress và backend theo security policy.

### 14.2. Không cho user chọn redirect URI tùy ý

Không tạo endpoint:

~~~text
/oauth2/authorization/company?redirect_uri=https://attacker.example
~~~

và tin query parameter này để override authorized redirect URI của ClientRegistration. Nếu cần callback theo tenant/environment, dùng allowlisted mappings phía server, không cho browser tự chọn arbitrary host.

### 14.3. Không dùng state làm nơi chuyển toàn bộ URL bí mật

<code>state</code> phải giúp correlate callback, không phải chỗ bỏ access token, session ID, client secret hoặc PII. Nếu lưu return path, nên dùng server-side SavedRequest/transaction mapping và validation chống open redirect.

## 15. Issuer và public OP hostname cũng cần nhất quán

Portal:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: https://sso.example.com/realms/company
~~~

OP Discovery:

~~~text
https://sso.example.com/realms/company/.well-known/openid-configuration
~~~

phải có issuer:

~~~json
{
  "issuer": "https://sso.example.com/realms/company"
}
~~~

ID Token sau login phải có <code>iss</code> khớp issuer đã được Client tin cậy.

### 15.1. Không dùng internal issuer trong một nơi, public issuer nơi khác

Sai:

~~~text
Spring issuer-uri:
    http://keycloak:8080/realms/company

Discovery issuer:
    https://sso.example.com/realms/company

ID Token iss:
    https://sso.example.com/realms/company
~~~

Vấn đề không giải quyết được bằng cách tắt issuer validation. OP cần công bố canonical issuer phù hợp và backend phải truy cập Discovery/Token/JWKS endpoints theo trust/network config.

### 15.2. Backend URL khác issuer được không?

Một số OP hỗ trợ các endpoint nội bộ riêng trong khi issuer public giữ nguyên. Việc này phải được hỗ trợ rõ theo OP metadata/security profile và Spring Security client configuration; không tự rewrite issuer hoặc bỏ validation.

### 15.3. Không cho browser cung cấp issuer động

Nếu ứng dụng hỗ trợ nhiều tenants/providers, không lấy trực tiếp:

~~~text
?issuer=https://unknown.example
~~~

để Client gọi Discovery/JWKS không kiểm soát. Ngoài OAuth mix-up, đây còn có thể là SSRF/supply-chain trust issue. Dùng allowlist <code>ClientRegistration</code> hoặc trusted tenant registry có quy trình onboarding/chấp thuận.

## 16. Nhiều providers và nhiều Redirect URIs

Ví dụ Portal hỗ trợ hai OP:

~~~text
Registration ID: company
Issuer: https://sso.company.example/realms/workforce
Callback: https://portal.example.com/login/oauth2/code/company

Registration ID: partner
Issuer: https://login.partner.example/oidc
Callback: https://portal.example.com/login/oauth2/code/partner
~~~

Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid]
        provider:
          company:
            issuer-uri: https://sso.company.example/realms/workforce
          partner:
            issuer-uri: https://login.partner.example/oidc
~~~

### 16.1. Mỗi OP cần đăng ký đúng callback

Company OP chỉ cần allow callback <code>/company</code>; Partner OP chỉ cần allow callback <code>/partner</code> theo registration của chúng.

Không đăng ký một wildcard <code>/login/oauth2/code/*</code> để cho mọi providers cùng redirect vào bất cứ route nào.

### 16.2. Rủi ro OAuth mix-up

Nếu callback của Provider A bị xử lý như Provider B, ứng dụng có thể gửi authorization code/token credentials tới sai Token Endpoint. Cần giữ binding giữa:

~~~text
state ↔ authorization request ↔ registrationId ↔ issuer ↔ token endpoint
~~~

và OIDC validation <code>iss</code>, <code>aud</code>, nonce theo flow. RFC 9207 mô tả issuer identification để giảm mix-up cho OAuth2 authorization responses khi profile/provider hỗ trợ.

### 16.3. Đổi provider không đồng nghĩa đổi public URL

Public Portal có thể là một hostname cho nhiều OP. Ngược lại, mỗi môi trường có thể có nhiều public hostnames; cần mapping có chủ đích và registration allowlists, không đoán provider từ một header tùy ý.

## 17. Multi-tenant và nhiều public hostnames

SaaS Portal có:

~~~text
https://tenant-a.portal.example.com
https://tenant-b.portal.example.com
~~~

Nếu cùng một OIDC ClientRegistration dùng <code>{baseUrl}</code>, callback có thể thay đổi theo request hostname.

### 17.1. Bài toán

OP có thể chỉ cho phép một danh sách Redirect URIs cố định, trong khi tenants được tạo động. Không giải quyết bằng:

~~~text
https://*.portal.example.com/login/oauth2/code/company
~~~

khi policy/security không cho phép wildcard.

### 17.2. Những kiến trúc khả thi

**Phương án A — Callback hostname tập trung**

~~~text
All tenants
   ↓
https://auth.portal.example.com/login/oauth2/code/company
   ↓
Server-side transaction/tenant mapping
   ↓
Redirect về tenant được phép sau login
~~~

Ưu điểm: một Redirect URI đăng ký cố định. Nhưng cần thiết kế cookie/session/cross-site correlation, tenant trust, return URL validation và không chuyển authorization code/token giữa các tenant origins thiếu kiểm soát.

**Phương án B — ClientRegistration/Redirect URI theo tenant đã onboard**

Mỗi tenant dùng registration/URI được tạo và phê duyệt phía server. Cần tự động hóa quản lý OP registration và lifecycle, không cho user tự nhập arbitrary issuer/callback.

**Phương án C — Tách tenants bằng realm/issuer hoặc deployment**

Phù hợp môi trường có yêu cầu isolation cao, chi phí vận hành lớn hơn.

### 17.3. Host validation

Trước khi tạo redirect:

1. Resolve hostname từ proxy đã được tin cậy.
2. Tra tenant mapping tại backend.
3. Chỉ chấp nhận host đã được xác minh sở hữu và allowlisted.
4. Chọn ClientRegistration/issuer đúng tenant.
5. Lưu transaction binding tới session/state.
6. Sau callback, xác minh issuer/sub/tenant và return target.

Không dùng email domain tự khai báo hoặc request Host đơn lẻ làm bằng chứng tenant ownership.

## 18. OIDC logout và post_logout_redirect_uri theo môi trường

Khi Portal sử dụng **RP-Initiated Logout**, browser có thể được chuyển tới OP:

~~~text
https://sso.example.com/realms/company/protocol/openid-connect/logout
~~~

rồi OP đưa browser về Portal:

~~~text
https://portal.example.com/login?logout
~~~

URL này thường được truyền qua <code>post_logout_redirect_uri</code> và có thể cần được đăng ký/allowlist riêng tại OP.

### 18.1. Logout URL khác login callback

Hai URL thường là:

~~~text
Login redirect_uri:
  https://portal.example.com/login/oauth2/code/company

Post-logout redirect URI:
  https://portal.example.com/login?logout
~~~

Đừng đăng ký post-logout URL vào login callback allowlist rồi coi là đủ; OP có thể có cơ chế xác minh riêng.

### 18.2. Spring Security Servlet handler

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalOidcLogoutConfig {

    @Bean
    SecurityFilterChain portalChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        var handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        handler.setPostLogoutRedirectUri(
            "{baseUrl}/login?logout");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout ->
                logout.logoutSuccessHandler(handler));

        return http.build();
    }
}
~~~

Đây là **SecurityFilterChain thay thế cho một chain login đơn giản**, không phải cấu hình chồng lên một chain khác có cùng matcher. API có thể thay đổi theo Spring Security version; dùng docs của phiên bản cụ thể.

### 18.3. Local logout và OP logout khác nhau

Local <code>POST /logout</code> có CSRF chỉ kết thúc Portal session theo handlers đã cấu hình. RP-Initiated Logout yêu cầu OP kết thúc SSO session và có thể dùng <code>id_token_hint</code> cùng những parameters theo OP profile.

OP logout behavior, post-logout redirect URI registration và browser SSO cookies cần được test trên provider đang dùng.

### 18.4. Reverse proxy ảnh hưởng logout tương tự login

Nếu <code>{baseUrl}</code> bị suy ra là:

~~~text
http://portal-service:8080
~~~

thì <code>post_logout_redirect_uri</code> cũng có thể sai. Cần xử lý public scheme/host/prefix thống nhất ở cả login và logout.

## 19. Session, CSRF và cookie khi thay đổi hostname

### 19.1. www và non-www

Nếu người dùng vào:

~~~text
https://www.portal.example.com
~~~

nhưng OP chỉ đăng ký:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

thì cần có một **canonical host redirect trước khi bắt đầu OAuth2 flow**, hoặc đăng ký/cấu hình chính xác từng host theo security policy.

Đừng:

~~~text
Begin state under www.portal.example.com
Callback to portal.example.com
~~~

rồi kỳ vọng host-only session cookie từ <code>www</code> được gửi sang apex host.

### 19.2. Session cookie scope

Host-only cookie:

~~~text
portal.example.com
~~~

không tự dùng được tại:

~~~text
staging.portal.example.com
~~~

Đây là điều tốt cho isolation giữa environments. Không mở rộng cookie Domain chỉ để dùng chung session production/staging.

### 19.3. Spring Session qua nhiều instances

Một request initiation vào instance A, callback vào B cần cùng session/authorization request state. Shared Redis/JDBC-backed Spring Session hoặc sticky sessions theo kiến trúc là một giải pháp.

Nhưng:

- Shared session không thay exact redirect URI validation.
- TLS đúng không tự đồng bộ state.
- X-Forwarded-Host đúng không thay Spring Security OAuth2AuthorizationRequestRepository.

## 20. Kịch bản kiến trúc: direct HTTPS so với proxy HTTPS

### 20.1. Direct HTTPS tại Spring Boot

Nếu app trực tiếp phục vụ HTTPS:

~~~text
Browser → https://portal.example.com:443 → Spring Boot TLS
~~~

thì server cần keystore/certificate hợp lệ và public host resolution đúng. <code>server.forward-headers-strategy=none</code> có thể phù hợp nếu không có proxy và app không tin forwarded headers.

Ưu điểm: ít lớp chuyển scheme. Nhược điểm: application phải quản lý TLS termination/cert lifecycle hoặc dùng web server hỗ trợ.

### 20.2. TLS terminate tại ingress

Nếu:

~~~text
Browser → HTTPS ingress → HTTP Pod
~~~

thì Spring Boot cần trusted forwarded headers hoặc cơ chế public-base-url mapping đúng. Không set <code>server.ssl.enabled=true</code> trong Pod một cách máy móc nếu ingress đang <code>proxy_pass http://...</code> tới backend; protocol giữa ingress và Pod phải khớp.

### 20.3. TLS re-encrypt

Nếu:

~~~text
Browser → HTTPS ingress → HTTPS Pod
~~~

thì app và ingress cần trust/certificate cho hop nội bộ, đồng thời public host/port vẫn có thể khác host/port trong Pod. Forwarded metadata vẫn có ý nghĩa cho public URL generation.

## 21. Kiểm thử Redirect URI trước khi đưa lên production

Một test cần xác minh cả:

1. Trang Portal được browser truy cập qua public HTTPS host.
2. Authorization initiation response redirect tới đúng OP.
3. Query parameter <code>redirect_uri</code> trong OP authorization URL đúng callback HTTPS public.
4. OP registration cho phép URI đó.
5. Browser quay về callback đúng host/path/query.
6. Session cookie tồn tại và state correlation hợp lệ.
7. Token exchange đúng OP, ID Token issuer/audience/nonce validation hợp lệ.
8. Login success handler đưa user tới target an toàn.

### 21.1. Kiểm tra thủ công với browser DevTools

Trong môi trường staging đã kiểm soát:

~~~text
1. Truy cập https://portal.staging.example.com
2. Mở Network tab
3. Bấm Login
4. Xem 302 Location đến OP Authorization Endpoint
5. Kiểm tra client_id và redirect_uri (không sao chép code/state)
6. Login tài khoản staging
7. Xác nhận callback HTTPS đúng host và path
8. Xác nhận browser session được duy trì
9. Thử logout và post-logout redirect
~~~

**Tránh chia sẻ HAR hoặc screenshot có authorization code, state, ID Token, session cookies** trong ticket công khai. Nếu cần artifacts, làm redaction.

### 21.2. curl chỉ xác minh một phần

Có thể xem TLS/headers hoặc Discovery:

~~~powershell
curl.exe -I https://portal.staging.example.com/login
curl.exe -I https://sso.staging.example.com/realms/company/.well-known/openid-configuration
~~~

Nhưng <code>curl -I</code> gửi HEAD và không đi qua browser session/Authorization Code Flow. Không coi kết quả HTTP 200/302 ở health/login page là bằng chứng OIDC callback đúng.

### 21.3. Kiểm tra redirect_uri được sinh ra

Một GET initiation:

~~~text
https://portal.staging.example.com/oauth2/authorization/company
~~~

có thể trả:

~~~http
HTTP/1.1 302 Found
Location: https://sso.staging.example.com/.../auth?response_type=code&client_id=portal-staging&redirect_uri=https%3A%2F%2Fportal.staging.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany&state=...
~~~

Trong test tự động, parse URL/URL-encoded query và so sánh <code>redirect_uri</code> như một URI. Không assert bằng cách grep raw URL mà dễ sai do percent encoding và thứ tự query parameters.

## 22. MockMvc test forwarded headers và URL generation

MockMvc có thể kiểm tra URL mà Spring Security sinh ra **nếu TestApplicationContext đã thực sự bật xử lý forwarded headers tương ứng**.

Ví dụ cấu hình test:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Test skeleton:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PublicRedirectUriTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginUsesExternalHttpsHost() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/oauth2/authorization/company")
                    // Trusted proxy context trong test,
                    // không có nghĩa ngoài Internet được set headers này.
                    .header("X-Forwarded-Proto", "https")
                    .header("X-Forwarded-Host",
                        "portal.staging.example.com")
                    .header("X-Forwarded-Port", "443"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = result.getResponse().getHeader("Location");
        assertNotNull(location);

        // Parse authorization URL và giải mã redirect_uri
        // rồi assert giá trị:
        // https://portal.staging.example.com/login/oauth2/code/company
        // Đừng so raw query vì thứ tự param/encoding có thể thay đổi.
        assertTrue(location.contains("redirect_uri="));
    }
}
~~~

**Giới hạn của skeleton:** Test cần <code>ClientRegistrationRepository</code> test hợp lệ, OP issuer/authorization endpoint metadata được cung cấp; TestContext phải thực sự đăng ký <code>ForwardedHeaderFilter</code> hoặc cơ chế tương đương. Một test chỉ set headers nhưng không bật filter sẽ không mô phỏng production.

### 22.1. Đối chiếu với test không có forwarded headers

Có thể thực hiện hai trường hợp:

| Input request mô phỏng | Expected base URL |
|---|---|
| HTTP internal, không có trusted forwarding | Internal URL hoặc URL backend trực tiếp |
| HTTP internal, trusted <code>X-Forwarded-Proto=https</code>, <code>X-Forwarded-Host=portal.staging.example.com</code> | HTTPS staging public URL |

Test cũng nên xem khi port=443 thì URL không bị chèn <code>:8080</code>.

### 22.2. Security test cho forged headers

Một test **chỉ gửi <code>X-Forwarded-Host: attacker.example</code> tới MockMvc** không đủ chứng minh ingress an toàn; nếu framework tin header, test có thể cố tình tạo URI sai.

Để xác minh security boundary, cần **deployment integration test đi qua trusted edge proxy**:

1. Client gửi malicious forwarded headers.
2. Ingress strip/overwrite theo policy.
3. Spring app nhìn thấy allowed public hostname.
4. OP authorization request không chứa attacker host.

Đây là bài kiểm thử của **proxy + application**, không chỉ riêng một filter.

## 23. Tích hợp OP test và xác minh callback

MockMvc có thể kiểm tra initiation, nhưng một OIDC flow đầy đủ cần OP/stub đáng tin:

~~~text
Portal request
    ↓
Authorization request & state stored
    ↓
OP authorization endpoint
    ↓
Callback code + matching state
    ↓
Token Endpoint exchange
    ↓
ID Token signature, issuer/audience/nonce validation
    ↓
Authenticated session
~~~

Trong staging integration test:

- Dùng test accounts, không dùng production users.
- Đăng ký HTTPS Redirect URI đúng staging hostname.
- Dùng đúng Client ID/secret staging.
- Bảo vệ HTTP session/state.
- Kiểm tra Principal <code>(iss, sub)</code> được xác minh.
- Kiểm tra browser nhận cookie <code>Secure</code>/<code>HttpOnly</code> phù hợp.
- Kiểm tra cả success handler và failure handler.

**Không** dùng <code>mockMvc.perform(get("/private").with(oidcLogin()))</code> rồi kết luận Redirect URI, proxy hoặc ID Token đã được kiểm thử. <code>oidcLogin()</code> giả lập Authentication, không chạy authorization-code callback.

## 24. Triển khai nhiều instance: HTTPS đúng nhưng callback vẫn lỗi

Kubernetes:

~~~text
Browser
  |
HTTPS Ingress
  |
  +--> Instance A
  |
  +--> Instance B
           |
        Shared session store (nếu có)
~~~

Một flow:

~~~text
GET /oauth2/authorization/company → A tạo state=S1 trong session
GET /login/oauth2/code/company?state=S1 → B nhận callback
~~~

Nếu B không đọc được session/authorization request của A, login báo:

~~~text
authorization_request_not_found
invalid_state
~~~

Điều này khác <code>redirect_uri_mismatch</code>. Những vấn đề độc lập:

| Lớp | Lỗi |
|---|---|
| Public URL/forwarded headers | Redirect URI sai scheme/host/port |
| OP registration | Redirect URI không được allow |
| Session cookie | Browser không mang cookie về callback |
| Session store | Node B không đọc state của node A |
| OAuth request repository | Authorization request bị mất/ghi đè |
| Token Endpoint | Code expired/reused hoặc PKCE/client authentication sai |

Không “sửa” lỗi state missing bằng cách bỏ kiểm tra state. Dùng Spring Session hoặc điều phối session phù hợp với HA requirements.

## 25. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/khắc phục |
|---|---|---|
| OP báo <code>redirect_uri_mismatch</code> | URI khác registration | So sánh exact scheme/host/port/path với OP |
| Redirect URI là <code>http://portal-service:8080</code> | App không nhận trusted forwarded scheme/host | Kiểm tra ingress headers + Boot strategy |
| Redirect URI là <code>http://portal.example.com</code> | X-Forwarded-Proto sai/mất | Kiểm tra TLS termination và proxy |
| Redirect URI có <code>:8080</code> công khai | X-Forwarded-Port hoặc URI synthesis sai | Kiểm tra port mapping/header |
| Callback bị 404 | App callback filter/path hoặc ingress rewrite sai | Kiểm tra callback path và context prefix |
| Callback tới <code>/portal/portal/login...</code> | Prefix áp dụng hai lần | Chọn context-path hoặc X-Forwarded-Prefix hợp lý |
| Browser đi từ www sang apex và mất session | Cookie host-only khác hostname | Canonical host trước initiation |
| Callback <code>authorization_request_not_found</code> | Cookie/session/repository missing | SameSite, session store, load balancer |
| Callback GET state mismatch | Bắt đầu flow khác session/multi-tab | Không bỏ state; điều tra correlation |
| Form-post callback state missing | SameSite=Lax chặn cross-site POST cookie | Thiết kế None; Secure hoặc flow phù hợp; narrow CSRF |
| Callback trả <code>invalid_grant</code> | Code expiry/reuse, PKCE/redirect mismatch | Token request và OP logs, không retry code mãi |
| ID Token issuer mismatch | Internal/public OP host khác | Discovery issuer và <code>iss</code> exact |
| JWKS TLS failure | JVM không trust OP certificate | Truststore và certificate chain |
| HSTS không xuất hiện | App tưởng request là HTTP hoặc proxy override | Kiểm tra header từ public HTTPS ingress |
| Session cookie không có Secure | Cookie config/proxy secure-request detection | Kiểm tra Set-Cookie từ public route |
| Staging login đưa về production | Dùng chung Client ID/URI sai | Tách ClientRegistration/OP allowlist |
| Logout quay về HTTP | <code>post_logout_redirect_uri</code> dùng base URL sai | Forwarded headers và OP logout registration |
| Tenant A callback tới Tenant B | Host/tenant mapping không chặt | Trusted host allowlist, state/issuer binding |
| Unexpected 302 tới attacker domain | Untrusted Host/forwarded-header injection | Ingress sanitize, allowed hosts |
| Browser báo “too many redirects” | HTTPS canonicalization, proxy scheme/cookie config | Quan sát redirect chain, ingress ↔ app |
| Chỉ node A login được | Session local/secret drift | Shared sessions và config đồng nhất |

### 25.1. Quy trình điều tra thực tế

~~~mermaid
flowchart TD
    A["OIDC Login thất bại ở staging/prod"] --> B{"Browser tới đúng HTTPS Portal host?"}
    B -->|Không| C["DNS, TLS cert, canonical host, ingress routing"]
    B -->|Có| D{"Authorization request redirect_uri đúng?"}
    D -->|Không| E["Forwarded headers, Boot strategy, prefix, environment config"]
    D -->|Có| F{"OP cho phép chính xác redirect_uri?"}
    F -->|Không| G["OP client registration / exact redirect allowlist"]
    F -->|Có| H{"Callback tới đúng host/path và còn cookie?"}
    H -->|Không| I["Ingress rewrite, SameSite, Secure, Domain/Path"]
    H -->|Có| J{"Spring tìm thấy state/authorization request?"}
    J -->|Không| K["Session store, multi-instance, OAuth2 repository"]
    J -->|Có| L{"Token exchange + OIDC ID Token validation thành công?"}
    L -->|Không| M["PKCE, code lifetime, issuer, client auth, JWKS"]
    L -->|Có| N["Success handler / saved request / business authorization"]
~~~

### 25.2. Log gì, không log gì?

Có thể log:

~~~text
environment=staging
registrationId=company
publicHost=portal.staging.example.com
externalScheme=https
redirectUriTemplate={baseUrl}/login/oauth2/code/{registrationId}
redirectUriHost=portal.staging.example.com
stateRepositoryFound=true
oauth2ErrorCategory=invalid_grant
correlationId=...
~~~

Không log:

~~~text
authorization_code
state thật
nonce thật
code_verifier
access_token / refresh_token / id_token
client_secret
session_cookie
client_assertion
~~~

Đặc biệt, một HTTP access log chứa **full callback query** có thể làm lộ <code>code</code>/<code>state</code>. Hãy cấu hình proxy/app logging redaction và hạn chế artifact retention.

## 26. Runbook khi chuẩn bị go-live

### 26.1. Trước triển khai

1. **DNS:** public host trỏ đúng ingress/load balancer.
2. **TLS:** certificate khớp public hostname, có expiry monitoring.
3. **Canonical URL:** chọn dứt khoát www/apex, context path và HTTPS.
4. **Edge trust:** proxy chỉ chấp nhận known hosts, strip/overwrite forwarded headers.
5. **Backend exposure:** service/private port không mở trực tiếp ra Internet.
6. **Boot strategy:** chọn <code>none/native/framework</code> phù hợp hạ tầng, tránh xử lý forwarded hai lần.
7. **OIDC registration:** Client ID/secret/issuer/redirect URI riêng cho environment.
8. **OP allowlist:** exact login callback URI và logout callback nếu áp dụng.
9. **Session cookies:** Secure, HttpOnly, SameSite và Domain/Path đúng.
10. **Session store:** HA nếu nhiều instances.
11. **OAuth security:** state, PKCE, nonce, issuer/audience/signature validation bật.
12. **Logs:** không chứa code/state/tokens/cookies/secrets.

### 26.2. Sau triển khai

1. Truy cập public HTTPS URL từ browser thực.
2. Xác minh HSTS và TLS cert theo policy.
3. Bấm login, đọc <code>redirect_uri</code> trong Authorization Endpoint redirect.
4. Xác minh đúng ClientRegistration/OP issuer.
5. Dùng test account của environment, không dùng production data ngoài quy trình được phép.
6. Kiểm tra callback public HTTPS và session cookie.
7. Kiểm tra ID Token validation và login success.
8. Kiểm tra access tới protected route sau login.
9. Kiểm tra logout POST/CSRF và OP logout nếu áp dụng.
10. Kiểm tra multi-instance callback cross-node.
11. Kiểm tra người dùng từ URL www/alias có canonicalize đúng trước login.
12. Quan sát metrics <code>redirect_uri_mismatch</code>, state missing, invalid_grant và login failure rates.

### 26.3. Rollback/rotation

Khi đổi public hostname hoặc ClientRegistration:

- Thêm OP redirect registration mới bằng quy trình kiểm soát trước cutover.
- Chạy smoke test theo public host mới.
- Xác định behavior của session cookies cũ khi host đổi.
- Không giữ wildcard/old callback không cần thiết vô thời hạn.
- Có kế hoạch thu hồi client secret và redirect URI của host cũ sau khi hết thời gian chuyển tiếp.
- Không đổi <code>issuer-uri</code> một cách tùy tiện: issuer thay đổi có thể đồng nghĩa một trust domain mới và ảnh hưởng tài khoản đã liên kết.

## 27. Các bài tập tình huống

### Bài 1 — Scheme sai sau TLS termination

Portal public là <code>https://portal.example.com</code>, Spring Boot backend nghe HTTP 8080. Authorization redirect URI lại là <code>http://portal-service:8080/login/oauth2/code/company</code>.

**Hỏi:** Root cause nằm ở đâu?

**Gợi ý đáp án:** Backend dùng internal origin vì thiếu/sai trusted forwarded metadata hoặc cấu hình base URL. Cần sửa proxy và Boot strategy, không nới OP wildcard.

### Bài 2 — Đổi từ localhost sang staging

Local callback là:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

Staging dùng:

~~~text
https://portal.staging.example.com/login/oauth2/code/company
~~~

**Hỏi:** Có nên sử dụng cùng Client ID/secret?

**Đáp án:** Nên tách OP registration và credentials staging khỏi local/production. Đăng ký callback staging chính xác, không dùng secret production ở local.

### Bài 3 — Issuer khác callback

~~~text
issuer=https://sso.example.com/realms/company
redirect_uri=https://portal.example.com/login/oauth2/code/company
~~~

**Hỏi:** Đây có phải lỗi không?

**Đáp án:** Không. Issuer thuộc OP, redirect URI thuộc Portal Client; chúng thường ở hai host khác nhau.

### Bài 4 — Host header injection

Attacker gửi <code>X-Forwarded-Host: attacker.example</code> đến public ingress.

**Hỏi:** Tầng nào cần xử lý?

**Đáp án:** Trusted edge proxy phải strip/overwrite untrusted forwarded headers và chỉ phục vụ known hosts; backend chỉ tin metadata từ trusted network. Kiểm thử phải đi qua ingress, không chỉ MockMvc.

### Bài 5 — Prefix bị lặp

Public callback thành:

~~~text
https://example.com/portal/portal/login/oauth2/code/company
~~~

**Đáp án:** Có thể vừa cấu hình context-path <code>/portal</code> vừa áp dụng <code>X-Forwarded-Prefix=/portal</code> khi proxy đã rewrite. Cần chọn một mapping nhất quán và đăng ký đúng OP URI.

### Bài 6 — Sai port

OP cho callback HTTPS mặc định 443, nhưng Client gửi URL có <code>:8080</code>.

**Đáp án:** Kiểm tra <code>X-Forwarded-Port</code>, <code>Forwarded</code> và scheme/port normalization của Boot/server. Không thêm port 8080 vào allowlist production.

### Bài 7 — Form-post callback

Browser cross-site POST callback nhưng không gửi session cookie <code>SameSite=Lax</code>.

**Đáp án:** Cần xem response_mode support, SameSite=None; Secure hoặc thiết kế correlation khác, đồng thời giữ CSRF protection nghiệp vụ và state validation.

### Bài 8 — Callback mất state qua hai nodes

Initiation ở A, callback ở B, cả hai dùng cùng public HTTPS host.

**Đáp án:** Độ đúng của public URL không tự chia sẻ session. Kiểm tra Spring Session/affinity/cookie/authorization request repository; không tắt state.

### Bài 9 — OP issuer sai

Spring cấu hình:

~~~text
https://sso.example.com/realms/company
~~~

nhưng ID Token có <code>iss=http://keycloak:8080/realms/company</code>.

**Đáp án:** Sửa canonical issuer/OP hostname metadata. Không bỏ ID Token issuer validation.

### Bài 10 — www vs apex

User bắt đầu login từ <code>www.portal.example.com</code>, callback về <code>portal.example.com</code> và mất session.

**Đáp án:** Canonicalize host trước initiation hoặc thiết kế cookie/redirect URLs có chủ đích; không mở rộng cookie Domain thiếu kiểm soát.

### Bài 11 — GET localhost

**Hỏi:** Vì sao có thể dùng <code>http://localhost</code> trong một local test nhưng không thể coi HTTP public redirect URI là production-safe?

**Đáp án:** Localhost test thuộc trust boundary phát triển; production browser traffic đi qua mạng không tin cậy cần HTTPS. Các ngoại lệ loopback trong OAuth native apps cũng không phải giấy phép cho mọi web Client chạy HTTP.

### Bài 12 — RP-Initiated Logout sai URL

Login thành công qua HTTPS nhưng logout redirect về <code>http://portal-service:8080/login?logout</code>.

**Đáp án:** <code>post_logout_redirect_uri</code> cũng phụ thuộc public base URL. Kiểm tra OIDC logout handler, proxy metadata và OP registration.

### Bài 13 — Wildcard redirect URI

Một đồng đội đề nghị <code>https://*.example.com/*</code> cho mọi environment.

**Đáp án:** Không nên. Nó mở rộng bề mặt chuyển authorization code khi có attacker-controlled subdomain/open redirect. Dùng exact URIs hoặc quy trình đăng ký tự động cho từng environment/tenant.

### Bài 14 — Tắt security validation để test pass

Callback báo <code>invalid_state</code>, nhóm muốn bỏ state check.

**Đáp án:** Không. Điều tra cookie, SameSite, session store, callback host/path, authorization repository và concurrency; bỏ state tạo rủi ro login CSRF.

### Bài 15 — Test MockMvc xanh

Một test:

~~~java
mockMvc.perform(get("/reports").with(oidcLogin()));
~~~

thành công.

**Hỏi:** Có chứng minh TLS ingress, Redirect URI và Token Endpoint hoạt động không?

**Đáp án:** Không. <code>oidcLogin()</code> chỉ tạo principal giả trong request test, không chạy browser/OP code flow.

### Bài 16 — Tách môi trường

Production và staging hiện cùng dùng Client ID và secret.

**Yêu cầu:** Lập kế hoạch tách.

**Gợi ý:** Tạo OP registration staging mới, secret riêng, exact callback, test staging login, sau đó loại staging URI khỏi production registration. Theo dõi OAuth errors và không đổi issuer production bất ngờ.

### Bài 17 — Multi-tenant callback

Có hàng trăm tenant hostnames, OP không chấp nhận wildcard redirect.

**Đáp án:** Cân nhắc callback hostname tập trung với server-side tenant/state binding hoặc dynamic registration được phê duyệt, không dùng arbitrary browser return URL.

### Bài 18 — Go-live runbook

Thiết kế checklist cho:

~~~text
Production portal:
  https://portal.example.com

OP issuer:
  https://sso.example.com/realms/company

Internal service:
  http://portal-service:8080
~~~

**Đáp án yêu cầu:** Nêu DNS/cert, ingress trusted headers, Boot forwarded strategy, ClientRegistration/secret, exact redirect URI, Secure/HttpOnly/SameSite cookie, session storage, OP callback allowlist, browser E2E login/logout và log redaction.

### Bài 19 — Thực hành triển khai

1. Dựng Spring Boot Servlet OAuth2/OIDC Client với registration <code>company</code>.
2. Tạo OP test và client riêng cho local/staging.
3. Cấu hình callback template <code>{baseUrl}/login/oauth2/code/{registrationId}</code>.
4. Dựng reverse proxy TLS ở hostname staging test.
5. Từ browser HTTPS, xác minh Authorization Endpoint redirect chứa HTTPS public URI.
6. Gửi Host/X-Forwarded-Host giả qua ingress và kiểm tra headers bị sanitize.
7. Test strict Redirect URI registration (URI sai bị OP từ chối).
8. Test callback code/state/session thành công.
9. Test session cookie flags qua browser DevTools.
10. Test callback state missing khi session bị xóa và xác minh fail closed.
11. Test logout post-logout redirect URI.
12. Test hai instances với shared session store.
13. Test app dưới path prefix <code>/portal</code>.
14. Ghi lại runbook/correlation ID, không thu raw code/state/token/cookies.

## 28. Tổng kết

- **Public base URL** thuộc Portal/browser, **internal URL** thuộc proxy/cluster, còn **issuer URI** thuộc OP. Ba khái niệm này không thay thế nhau.
- Spring Security dùng Redirect URI template như <code>{baseUrl}/login/oauth2/code/{registrationId}</code>; <code>{baseUrl}</code> chỉ đúng khi request origin được framework nhận biết chính xác.
- **HTTPS là bắt buộc trong production web login** để bảo vệ authorization responses, session cookies và browser traffic. HTTP localhost có thể dùng cho local test trong phạm vi kiểm soát.
- OP nên đăng ký **exact Redirect URI theo environment**, phân biệt scheme, host, port, path, registration ID và prefix; tránh wildcard rộng.
- Staging và production nên có ClientRegistration/Client ID/secrets riêng; không chép production credentials sang local.
- Khi TLS terminate tại ingress, Spring Boot phải hiểu **public HTTPS scheme/host/port** qua cơ chế forwarded headers hoặc public URL mapping đã được kiểm soát.
- <code>Forwarded</code>/<code>X-Forwarded-*</code> là **dữ liệu không tin cậy nếu đến trực tiếp từ Internet**. Edge proxy phải strip/overwrite client-supplied values và giới hạn allowed hosts; backend không nên public trực tiếp.
- <code>server.forward-headers-strategy</code> có các lựa chọn <code>none</code>, <code>native</code>, <code>framework</code>; chọn theo container/ingress trust model, không bật chồng nhiều cơ chế.
- Nếu app có <code>context-path</code> hoặc <code>X-Forwarded-Prefix</code>, phải tránh prefix bị lặp và đảm bảo public callback path khớp OP allowlist.
- Session cookie <code>Secure</code>, <code>HttpOnly</code>, <code>SameSite</code> và Domain/Path phải phù hợp browser flow; GET callback khác <code>form_post</code> callback.
- Issuer Discovery và ID Token <code>iss</code> phải khớp issuer tin cậy. Không dùng internal OP hostname để bỏ issuer validation hoặc trộn providers.
- Với nhiều providers/tenants, giữ binding giữa <code>state</code>, ClientRegistration, issuer và redirect URI; không cho browser chọn arbitrary callback/issuer.
- <code>post_logout_redirect_uri</code> phục vụ RP-Initiated Logout và cần cấu hình/allowlist riêng theo environment.
- Callback lỗi có thể do URL/proxy, cookie, session store, state, Token Endpoint hoặc ID Token validation. Cần phân loại đúng trước khi thay cấu hình.
- Kiểm thử phải đi qua **public HTTPS ingress và OP thật/stub phù hợp**; MockMvc <code>oidcLogin()</code> không chứng minh Redirect URI hay TLS đang đúng.
- Go-live cần kiểm tra DNS/cert, exact callback, proxy trust, cookie, session HA, login/logout E2E, metrics và redaction của credentials.

### Tài liệu tham khảo

- **Spring Security Reference — OAuth2 Login (Servlet):** authorization initiation, ClientRegistration, Redirect URI template, callback và state.
- **Spring Security Reference — OAuth2 Client:** grant types, authorized clients và provider configuration.
- **Spring Security Reference — OIDC Login and Logout:** ID Token issuer validation, RP-Initiated Logout và post-logout redirect.
- **Spring Boot Reference — Embedded Web Servers / Behind a Front-end Proxy:** <code>server.forward-headers-strategy</code>, scheme/host/port và reverse proxies.
- **Spring Framework Reference — ForwardedHeaderFilter / Forwarded Headers:** request origin reconstruction và removing untrusted headers.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization code redirect URI, state và redirect restrictions.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code interception mitigation.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer-based mix-up protection.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** Redirect URI exact matching, HTTPS, mix-up và Authorization Code security.
- **RFC 7239 — Forwarded HTTP Extension:** standardized <code>Forwarded</code> header syntax và proxy metadata.
- **OpenID Connect Core 1.0:** ID Token, nonce, issuer/audience validation và Authorization Code Flow.
- **OpenID Connect Discovery 1.0:** issuer, authorization/token/JWKS endpoints.
- **OpenID Connect RP-Initiated Logout 1.0:** <code>post_logout_redirect_uri</code> và OP logout.
- **OWASP Unvalidated Redirects and Forwards Cheat Sheet:** allowed redirect targets, open redirect defenses.
- **OWASP Session Management Cheat Sheet:** Secure, HttpOnly, SameSite, Domain/Path, session lifecycle.
- **OWASP Transport Layer Security Cheat Sheet:** certificates, trusted TLS, HSTS và downgrade prevention.
