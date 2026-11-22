# Địa chỉ công khai, HTTPS và callback khi ứng dụng nằm sau reverse proxy

> **Module:** Spring Security – federation. **Chủ đề cha:** Triển khai và vận hành. **Vấn đề:** Một ứng dụng Spring Boot/Spring Security chạy nội bộ ở `http://127.0.0.1:8080` hoặc `http://portal-service:8080` nhưng người dùng và Identity Provider (IdP) chỉ thấy `https://portal.example.org`. Nếu reverse proxy, Spring và IdP không nhất quán về **scheme, host, port, path và callback**, SAML2, OAuth2/OIDC, CAS và Kerberos/SPNEGO có thể thất bại dù credential và chữ ký đúng. Bài viết thiết kế chuẩn public origin, ranh giới tin cậy của `Forwarded`/`X-Forwarded-*`, TLS termination, URL cố định và kế hoạch kiểm chứng. Ví dụ dành cho **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x, Nginx**; cần điều chỉnh cho kiến trúc thật và test trên môi trường HTTPS có IdP sandbox.

## 1. Kết quả cần đạt

Sau bài học, bạn phải có khả năng:

1. Phân biệt **public URL** mà browser/IdP nhìn thấy với **internal URL** của servlet container, và giải thích vì sao Spring có thể sinh `http://portal-service:8080/...` sai.
2. Vẽ được luồng **Browser → Edge/TLS → Reverse proxy → Spring Security → IdP → callback → Spring Security** kèm các ranh giới trust.
3. Định nghĩa **một canonical public origin** gồm scheme/host/port và một policy rõ cho context path; không xây URI bằng `Host` hay `X-Forwarded-Host` tùy ý từ Internet.
4. Cấu hình proxy **loại bỏ/ghi đè Forwarded/X-Forwarded*** do client gửi, chỉ chấp nhận headers do proxy được tin cậy đặt, và giới hạn truy cập trực tiếp vào backend.
5. Cấu hình `server.forward-headers-strategy=framework` hoặc `native` đúng ngữ cảnh; hiểu `ForwardedHeaderFilter` và tránh xử lý headers hai lần.
6. Kiểm **OAuth2/OIDC redirect_uri** `{baseUrl}/login/oauth2/code/{registrationId}`, `state`, PKCE và `nonce` sau khi triển khai HTTPS.
7. Kiểm **SAML2 Entity ID, ACS URL, SLO callback, metadata**, `Destination`/`Recipient`/`Audience` và chữ ký khi nằm sau proxy.
8. Kiểm **CAS service identifier, pgtUrl HTTPS callback**; phân biệt callback CAS với OIDC và SAML.
9. Kiểm **Kerberos/SPNEGO HTTP/FQDN** và `WWW-Authenticate: Negotiate` qua edge proxy, không nhầm host nội bộ với SPN.
10. Xử lý **TLS termination, HTTPS backhaul/mTLS, HSTS, cookie Secure/HttpOnly/SameSite, CSRF, session affinity/shared state, multi-node**.
11. Chạy **Java 17 standalone** để kiểm allowlist callback URL, phân biệt origin/path/URI-shape failures và in stdout chính xác.
12. Thiết kế preflight/test matrix/rollout/rollback, theo dõi redirects và lỗi callback mà **không log SAML assertions, authorization codes, tokens hay session cookies**.

**Kiến thức nền:** HTTP request/response/redirect, TLS/X.509, reverse proxy/load balancer, Spring MVC request URL, Spring Security login endpoints, OAuth2 Authorization Code, SAML2 SP/IdP, CAS service tickets, Kerberos SPN, Docker/Kubernetes network.

## 2. Bài toán: URL public khác URL nội bộ

Kiến trúc ví dụ:

~~~text
Browser / IdP
       |
       | HTTPS https://portal.example.org
       | TLS cert CN/SAN=portal.example.org
       v
[Nginx / LB / Ingress]   <-- TRUST BOUNDARY 1
       |
       | HTTP http://portal-service:8080
       | Host / Forwarded / X-Forwarded-* do proxy đặt
       v
[Spring Boot JVM]        <-- TRUST BOUNDARY 2
       |
       +-- OAuth2 authorization request
       |     -> redirect_uri=https://portal.example.org/login/oauth2/code/corporate
       |
       +-- SAML AuthnRequest / SP metadata
       |     -> ACS=https://portal.example.org/login/saml2/sso/corporate
       |     -> SLO=https://portal.example.org/logout/saml2/slo
       |
       +-- CAS service validation
       |     -> service=https://portal.example.org/login/cas
       |
       +-- SPNEGO Negotiate
             -> HTTP/portal.example.org@EXAMPLE.ORG
~~~

**Điều người dùng/IdP phải thấy:** `https://portal.example.org`. **Điều JVM có thể thấy nếu cấu hình sai:** `http://portal-service:8080`. Nếu ứng dụng dùng request-derived base URL mà không xử lý reverse proxy đúng, nó có thể sinh:

~~~text
Sai:
  OAuth redirect_uri=http://portal-service:8080/login/oauth2/code/corporate
  SAML ACS=http://portal-service:8080/login/saml2/sso/corporate
  SAML SP entityID=http://portal-service:8080/saml2/service-provider-metadata/corporate
  CAS service=http://portal-service:8080/login/cas
  Location: http://portal-service:8080/login

Đúng:
  OAuth redirect_uri=https://portal.example.org/login/oauth2/code/corporate
  SAML ACS=https://portal.example.org/login/saml2/sso/corporate
  SAML SP entityID=https://portal.example.org/saml2/service-provider-metadata/corporate
  CAS service=https://portal.example.org/login/cas
  Location: https://portal.example.org/login
~~~

Chữ ký SAML và TLS certificate có thể hoàn toàn hợp lệ nhưng IdP vẫn reject vì **URI mismatch**. Cũng có trường hợp IdP cho login thành công nhưng browser không quay lại được callback nội bộ, dẫn tới vòng 302/401. **Không chữa bằng cách mở internal hostname ra Internet hoặc nới IdP redirect allowlist thành wildcard.**

### 2.1. Từ vựng phải dùng nhất quán

| Thuật ngữ | Ví dụ | Có nghĩa gì? |
| --- | --- | --- |
| Public origin | `https://portal.example.org` | Scheme + host + hiệu lực port; địa chỉ đáng tin đã phê duyệt |
| Public base URL | `https://portal.example.org` hoặc `https://portal.example.org/app` | Origin cộng đường dẫn prefix nếu ứng dụng được publish dưới prefix |
| Internal backend | `http://portal-service:8080` | Địa chỉ proxy gọi JVM, **không** đăng ký với IdP |
| External callback | `https://portal.example.org/login/oauth2/code/corporate` | URL IdP/authorization server chuyển browser về |
| SAML ACS | `https://portal.example.org/login/saml2/sso/corporate` | SP nhận SAMLResponse |
| SAML SLO | `https://portal.example.org/logout/saml2/slo` | SP nhận SAML LogoutRequest/LogoutResponse |
| CAS service | `https://portal.example.org/login/cas` | Identifier chính xác được CAS server kiểm với ticket |
| CAS PGT callback | `https://portal.example.org/login/cas/proxyreceptor` | HTTPS server-to-server CAS→SP để gửi PGT |
| Kerberos SPN | `HTTP/portal.example.org@EXAMPLE.ORG` | Danh tính Kerberos ứng với public hostname, không phải URL |
| IdP issuer | `https://idp.example.org/realms/corporate` | Identifier của IdP/OP; không phải public origin của Portal |

**Entity ID SAML có thể là URN**, ví dụ `urn:portal:prod:sp`, không bắt buộc là URL. Tuy nhiên Entity ID phải **ổn định và trùng chính xác** giữa SP và IdP; ACS/SLO vẫn phải là public endpoint đúng. Với Spring SAML2 default, entity ID thường lấy từ template `{baseUrl}/saml2/service-provider-metadata/{registrationId}`, nên sai public base URL có thể khiến **cả Entity ID lẫn ACS** thay đổi ngoài ý muốn.

## 3. Chuẩn hóa canonical public origin trước khi cấu hình

Một hợp đồng được phê duyệt cho môi trường production:

~~~text
Environment: prod
Canonical public scheme: https
Canonical public host: portal.example.org
Canonical port: 443 (ngầm định, không viết :443 khi registry dùng URI không port)
Canonical base path: / (không prefix)
Application internal host: portal-service
Application internal port: 8080
Trusted edge proxy: ingress/proxy group có mạng/identity được quản trị
OAuth2 callback: /login/oauth2/code/corporate
SAML ACS: /login/saml2/sso/corporate
SAML SLO: /logout/saml2/slo
CAS service: /login/cas
CAS PGT receptor: /login/cas/proxyreceptor
Kerberos service principal: HTTP/portal.example.org@EXAMPLE.ORG
~~~

Với các hệ thống khác: `https://portal-stg.example.org` và `https://portal-dev.example.org` phải là **registrations tách biệt**, keys/clients/metadata/environment khác nhau. Không đăng ký production client với redirect URI `http://localhost:8080` chỉ để test nếu policy không cho phép. Không trộn SAML Entity ID/certificate của staging với prod.

**Nguyên tắc URI:**

- **Scheme:** HTTPS cho browser/IdP-facing URLs. `http://` nội bộ chỉ hợp lệ sau một trust boundary được bảo vệ; không phát tán vào metadata hay redirects.
- **Host:** FQDN lowercase/canonical do tổ chức sở hữu. Không suy host từ input browser mà không kiểm allowed hosts; tránh IDN homograph, dấu chấm cuối, ký tự bất thường, suffix match và IP literal tùy ý.
- **Port:** default 443 thường được viết không có `:443`; một số IdP so URI **theo chuỗi** và coi port/encoding/path khác là mismatch. Chọn chính xác một dạng đã đăng ký.
- **Path:** phân biệt `/login/oauth2/code/corporate`, `/login/saml2/sso/corporate` và `/logout/saml2/slo`. Trailing slash/case/percent encoding có thể gây mismatch.
- **Query:** callback của OAuth2 có `?code=...&state=...` khi IdP trả về; **registered redirect_uri** chỉ chứa cơ sở được phê duyệt, không nhận `next=evil` hay URI do user nhập. SAML POST callback nhận form `SAMLResponse`, không cho user tạo tùy ý `Recipient`.
- **Fragment:** không dùng fragment làm nơi truyền authorization codes/callback server-side nếu framework flow đang dùng Authorization Code.
- **Public path prefix:** nếu publish ở `/portal` nhưng container chạy root `/`, xử lý prefix phải được thiết kế **một lần**, tránh double-prefix hoặc mất prefix.

### 3.1. Đừng “tự sửa” URL bằng replace chuỗi

**Sai:**

~~~java
// Ví dụ anti-pattern: thay http -> https theo chuỗi quá đơn giản.
String callback = request.getRequestURL().toString()
        .replace("http://", "https://");
~~~

Nếu host đã là `internal-host:8080`, cách trên sinh `https://internal-host:8080` vẫn sai. Nếu request có `Host` attacker-controlled, sẽ sinh callback/redirect đến attacker. Hơn nữa scheme thay đổi không tự sửa `port`, `context-path`, `forwarded prefix` hoặc IdP allowlist.

**Đúng về nguyên tắc:** Dùng **canonical public base URL trong cấu hình** hoặc request-derived URL chỉ sau một reverse proxy **được tin cậy, đã ghi đè forwarded headers và kiểm Host**. Spring Security URI templates `{baseUrl}` chỉ là công cụ xây URL; tính tin cậy của giá trị resolved vẫn do topology bảo đảm.

## 4. Forwarded headers: rất hữu ích và cũng rất nguy hiểm

Khi TLS terminate tại reverse proxy, JVM nhận request nội bộ với `scheme=http`, `serverName=portal-service`, `serverPort=8080`. Reverse proxy có thể truyền ý nghĩa public thông qua:

~~~http
Host: portal.example.org
X-Forwarded-Proto: https
X-Forwarded-Host: portal.example.org
X-Forwarded-Port: 443
X-Forwarded-For: 192.0.2.40
~~~

Hoặc theo RFC 7239:

~~~http
Forwarded: for=192.0.2.40;proto=https;host=portal.example.org
~~~

**Nhưng:** Client Internet **cũng có thể tự gửi** những header đó. Vì vậy không được cấu hình Spring “trust X-Forwarded-Host của mọi request” trong khi backend vẫn mở trực tiếp hoặc edge chỉ append những gì client đã gửi.

### 4.1. Trust boundary hai lớp

~~~text
Attacker browser:
  GET /oauth2/authorization/corporate
  Host: portal.example.org
  X-Forwarded-Host: evil.example
  X-Forwarded-Proto: http

Edge proxy an toàn:
  - kiểm public host hợp lệ
  - xóa Forwarded, X-Forwarded-* do client cung cấp
  - tự đặt X-Forwarded-Host = portal.example.org
  - tự đặt X-Forwarded-Proto = https
  - tự đặt X-Forwarded-Port = 443
  - chỉ forward tới backend mạng riêng

Spring:
  - chỉ thấy headers do edge quản trị
  - resolve {baseUrl} là https://portal.example.org
  - phát đúng callback URL
~~~

**Nếu edge không scrub:** Một số cấu hình `ForwardedHeaderFilter` sẽ diễn giải `X-Forwarded-Host: evil.example` như host public và app có thể sinh `Location: https://evil.example/...`, OAuth2 `redirect_uri` sai, password reset poisoning, cache poisoning hoặc open redirects. Có trường hợp IdP reject ngay; có trường hợp attacker lợi dụng các URL khác trong ứng dụng. Không dựa vào IdP strict URI matching để thay host validation.

### 4.2. Header precedence và chain nhiều proxy

Nhiều layers có thể tạo headers:

~~~text
Browser → CDN → LB → Nginx ingress → JVM

Forwarded: for=...;host=...;proto=...
X-Forwarded-For: client, CDN, LB
X-Forwarded-Host: ...
X-Forwarded-Proto: ...
~~~

Quyết định **một nơi** sở hữu canonical public scheme/host/port và các lớp tin cậy tiếp theo. Edge Internet phải loại bỏ headers ngoài trust; các proxy sau chỉ tin predecessor đã xác thực/quản trị. Nếu cả `Forwarded` và `X-Forwarded-*` được gửi mà mâu thuẫn, các framework có thể ưu tiên khác nhau, gây chuyển hướng sai/Host spoofing. Hãy thống nhất hoặc xóa một bộ, không để hai giá trị bất đồng.

`X-Forwarded-For` là IP chain; thứ tự và client IP thực chỉ đáng tin nếu biết danh sách proxies được phép. Không lấy phần tử đầu để làm authorization/rate-limit/anti-abuse khi client có thể giả mạo. Với Nginx `real_ip`, chỉ trust `set_real_ip_from` của upstream đã biết; đừng để `0.0.0.0/0` thành trusted proxy list.

### 4.3. Spring Framework ForwardedHeaderFilter

`ForwardedHeaderFilter` có nhiệm vụ tạo request wrapper để các thành phần Spring có thể thấy scheme/host/port từ `Forwarded` hoặc `X-Forwarded-*` và loại bỏ headers sau khi xử lý. Nó **không xác thực độ tin cậy của proxy nguồn**; Spring Framework docs yêu cầu edge proxy xóa những headers từ Internet và đặt header mới. Filter có thể cấu hình `removeOnly` khi muốn **bỏ forwarded headers mà không sử dụng giá trị**.

**Bẫy:** Không vừa bật container native forwarding, vừa đặt thủ công một `ForwardedHeaderFilter` khác mà không hiểu filter order và semantics. Tránh multiple sources of truth khiến request scheme/host bị rewrite hai lần.

## 5. Spring Boot 3.5: chọn một forwarded-header strategy

Spring Boot có property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các hướng:

| Strategy | Cách làm | Khi nào cân nhắc |
| --- | --- | --- |
| `none` | Không dùng forwarded headers để thay request URL | App dùng fixed canonical URLs hoặc không có trusted reverse proxy; không phụ thuộc request-derived baseUrl |
| `native` | Container/server xử lý headers bằng cơ chế native (ví dụ Tomcat RemoteIpValve khi Boot setup) | Platform chuẩn hóa/trust proxy ở container layer, hiểu behavior với `X-Forwarded-*` |
| `framework` | Spring dùng `ForwardedHeaderFilter` (Servlet) hoặc tương ứng WebFlux | Cần Spring resolve URL theo trusted edge headers, hỗ trợ scheme/host/prefix theo semantics framework |

**Dùng `framework` trong ví dụ này** vì có Nginx quản trị, backend không mở Internet, edge ghi đè forwarded headers và Spring Security dựa trên `{baseUrl}`. Không khẳng định `framework` tự chặn spoofed Forwarded. Với ứng dụng cần nhiều proxies/headers phức tạp, chuẩn hóa ở edge và test actual backend scheme/host/port là bắt buộc.

### 5.1. application.yml cho servlet app

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

**Giải thích:** `server.port=8080` là backend port; không phải public port. `secure=true` cho session cookie giúp bảo đảm browser chỉ gửi qua HTTPS (TLS termination vẫn được tính ở client side). `http-only=true` giảm truy cập bằng JavaScript. `same-site=lax` phù hợp nhiều app OIDC Authorization Code GET callback nhưng **có thể không phù hợp với SAML HTTP-POST cross-site ACS**. Bài sẽ chỉ cách test và đặt cookie policy đúng ở mục 12. Không đưa actuator endpoints nhạy cảm ra Internet; `health/info` cũng cần xem exposure.

**Không tự đặt:**
- `server.forward-headers-strategy=framework` và `native` đồng thời (property chỉ có một value).
- Một `ForwardedHeaderFilter` bean riêng với cùng mục đích nếu Boot đã cấu hình, trừ khi bạn kiểm filter chain và có yêu cầu rõ.
- `trustAllForwardedHeaders=true` do app tự nghĩ ra; đó không phải property chuẩn bảo đảm trust.
- `X-Forwarded-Proto: https` ở browser để “ép Spring hiểu HTTPS”.

### 5.2. Xác nhận bằng request diagnostics an toàn

Trong sandbox, một `HandlerInterceptor`/controller kiểm chứng có thể in:

~~~text
request.getScheme()     -> https
request.getServerName() -> portal.example.org
request.getServerPort() -> 443
request.isSecure()      -> true
public app base URL     -> https://portal.example.org
~~~

Chỉ hiển thị tại test environment hoặc endpoint đã bảo vệ; không đưa request headers/cookies hay info nội bộ lên public diagnostic page. Sau khi xác định đúng, **tắt endpoint diagnostics**. Nhớ rằng `getRequestURL()` có thể chứa actual request path; đừng dùng nó làm redirect_uri template nếu path đang là `/oauth2/authorization/corporate`.

### 5.3. Trusted proxy không có nghĩa tin header trọn vẹn

Ngay cả khi client chỉ đi qua Nginx, phải:
- Giới hạn public `Host`/SNI thành các FQDN approved.
- Bỏ client-supplied `Forwarded` và `X-Forwarded-*`, ghi đè chính xác.
- Ngăn direct access vào backend service via public IP, NodePort, exposed pod port hay alternate LB.
- Bảo vệ Kubernetes ingress config và service mesh policies khỏi untrusted edits.
- Kiểm logging/redaction và egress of redirects.
- Chỉ dùng published origin theo environment allowlist, không tùy biến host theo user input.

## 6. Nginx ở biên: cấu hình mẫu kiểm soát public Host

Ví dụ cùng-host test: Nginx nhận `https://portal.example.org` và proxy đến `127.0.0.1:8080`. Trong Kubernetes, sửa upstream thành ClusterIP/internal address đã được NetworkPolicy bảo vệ.

~~~nginx
# Ví dụ minh họa Nginx server blocks; thiết lập TLS ciphers,
# stapling, certificate renewal, access logs theo policy thật.

server {
    listen 80;
    server_name portal.example.org;
    return 308 https://portal.example.org$request_uri;
}

server {
    listen 443 ssl;
    server_name portal.example.org;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    # Optional khi mọi nội dung/subdomain đã HTTPS hoàn toàn.
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8080;

        # Canonical public host: không lấy từ header attacker.
        proxy_set_header Host              portal.example.org;
        proxy_set_header X-Forwarded-Host  portal.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port  443;

        # Mẫu một trusted edge, giữ remote_addr của kết nối đến Nginx.
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Real-IP         $remote_addr;

        # Không chuyển bản Forwarded do client gửi.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Prefix "";

        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
~~~

**Phạm vi mẫu:**
- Nginx `server_name` không tự đảm bảo từ chối mọi hostname lạ nếu đây là virtual host/default server: cần một **default/catch-all vhost** có policy reject unknown hosts và TLS SNI/Host routing phù hợp. Test bằng `Host: evil.example` để đảm bảo request không được routed vào Portal rồi tạo callback sai.
- `$remote_addr` ở Nginx là peer trực tiếp. Nếu CDN/LB đứng trước Nginx, nó là IP LB/CDN, **không phải** end user; điều chỉnh trusted IP chain bằng `real_ip` allowlist, không dùng `proxy_add_x_forwarded_for` nếu bạn chưa scrub input chain.
- `proxy_pass http://127.0.0.1:8080` chỉ hợp lý khi Nginx và JVM cùng host. Khi chúng khác host, cân nhắc TLS backhaul hoặc mTLS; không để HTTP unencrypted trên mạng chia sẻ.
- HSTS phải được duyệt cho hostname/subdomains hiện đang dùng; `includeSubDomains`/`preload` là quyết định tác động rộng, không bật theo ví dụ khi subdomain chưa sẵn sàng.
- `return 308` ở port 80 phù hợp chuyển HTTP→HTTPS với method preservation, nhưng không dùng redirect HTTP cho SAML POST callbacks đã gửi nhầm host/scheme. **Đăng ký IdP callback trực tiếp là HTTPS** để browser không phải redirect POST và mất body/cookies.
- Certificate/key path ở Nginx là TLS key cho public host, **khác** với SAML SP signing key, CAS PGT credentials hay Kerberos keytab.

### 6.1. “X-Forwarded-Host = $host” có đủ an toàn?

Chỉ khi vhost/edge đã kiểm **$host thuộc allowlist**. Nếu Nginx default vhost nhận arbitrary `Host` và gán `X-Forwarded-Host=$host`, attacker có thể đẩy `evil.example` vào Spring dù Spring chỉ nhận traffic từ “trusted Nginx”. Để minh họa, config trên đặt **literal** `portal.example.org`. Trong nhiều môi trường dùng nhiều host được phép, hãy dùng map/route allowlist được review, không chấp nhận mọi value từ user input.

### 6.2. Chuỗi CDN→ALB→Ingress

Nếu có nhiều hops, cần nêu rõ:
1. Public TLS terminate tại layer nào?
2. Layer nào nhận/loại bỏ client-supplied forwarded headers?
3. Layer nào điền canonical `proto/host/port/prefix`?
4. Internal hop nào có identity được tin cậy?
5. Container native hay Spring framework consumes headers?
6. Có bypass path nào đi thẳng tới service không?

Hãy test from outside Internet và from inside cluster với untrusted pod: direct backend request không được ép URL sinh ra bằng forged headers. “Spring nhận forwarded headers” chỉ là xử lý format; nó không biết edge nào thật nếu network policy và proxy config không enforce.

## 7. OAuth2 / OIDC: redirect_uri là hợp đồng chính xác

Spring Security OAuth2 Login trong Servlet stack thường có:

~~~text
Start authorization:
  GET https://portal.example.org/oauth2/authorization/corporate

Registered redirect URI:
  https://portal.example.org/login/oauth2/code/corporate

Default Spring template:
  {baseUrl}/login/oauth2/code/{registrationId}

Internal backend:
  http://portal-service:8080
~~~

Flow:

~~~text
Browser -> Portal /oauth2/authorization/corporate
Portal -> 302 IdP /authorize
  client_id=...
  redirect_uri=https://portal.example.org/login/oauth2/code/corporate
  state=...
  code_challenge=... (PKCE khi cấu hình/được dùng)
  nonce=... (OIDC request khi áp dụng)

Browser -> IdP login/consent
IdP -> Browser redirect:
  https://portal.example.org/login/oauth2/code/corporate
    ?code=[redacted]
    &state=[redacted]

Portal:
  validates state/correlated authorization request
  exchanges code over TLS, validates tokens/issuer/audience/nonce
  sets secure application session
~~~

**Lỗi điển hình:** IdP hiển thị `redirect_uri_mismatch` vì Spring sinh `http://portal-service:8080/...` hoặc `http://portal.example.org/...` (sai scheme). Đừng sửa bằng cách đăng ký `http://portal-service:8080` tại IdP, nới wildcard hoặc tắt verification; hãy sửa public URL/trusted forwarding.

### 7.1. Spring Boot OAuth2 client config (fragment)

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: portal-web
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.org/realms/corporate
~~~

**Giải thích:** Đây là fragment cần IdP/Authorization Server thật và secret injected từ secret manager; **không** có credential thật. `issuer-uri` là identifier để khám phá/xác minh OP/IdP, không phải Portal public URL. `redirect-uri` là client redirect URI; IdP phải đăng ký đúng chuỗi. `{baseUrl}` do Spring giải từ trusted request/public config. Nếu dùng Spring Authorization Server/tenant domain khác, xác định provider metadata/JWKS/TLS theo issuer; không đổi `issuer-uri` thành Portal host.

**Không đồng nhất redirect_uri và token endpoint:** Browser callback đến Portal; backend Portal gọi IdP token endpoint **server-to-server**. Backend có thể ở private network; callback không phải token endpoint. Không đưa client secret vào browser hoặc logs.

### 7.2. Những vấn đề ngoài URL

- **`state`:** buộc callback với authorization request của browser/session; không bỏ state check khi callback về node khác.
- **PKCE:** dùng khi được cấu hình/được provider hỗ trợ, đặc biệt public clients; URL không thay thế code challenge/verifier.
- **OIDC `nonce`:** khi dùng OIDC yêu cầu/kiểm nonce theo flow; callback đúng host chưa chứng minh ID Token hợp lệ.
- **`iss`, `aud`, `exp`, signature/JWKS:** vẫn phải được kiểm đầy đủ sau code exchange.
- **Open redirect:** không đưa user-provided `returnUrl` thành `redirect_uri` và không redirect browser tới arbitrary domain sau login.
- **Multi-tenant:** `registrationId=corporate` phải map IdP/client cụ thể đã phê duyệt; không chọn authorization server host từ `X-Forwarded-Host` hoặc query param.
- **Session cookie:** cross-site front-channel callback thường là GET; SameSite Lax thường cho top-level GET, nhưng SAML POST khác.
- **Codes/tokens:** không ghi full `code`, `state`, `id_token` vào access logs/analytics/Referer; hạn chế callback caching và leakage.

### 7.3. Bảng positive/negative OAuth2/OIDC

| Test | Expected |
| --- | --- |
| Đến từ public HTTPS, normal proxy headers | Authorization request có `redirect_uri=https://portal.example.org/login/oauth2/code/corporate` |
| Edge không gửi X-Forwarded-Proto | Test phát hiện Spring sinh `http://...`; không “approve” sai URI |
| Client gửi forged `X-Forwarded-Host: evil.example` | Edge scrub; Spring vẫn dùng approved host |
| Callback sai path | Không được xử lý bởi login filter đúng registration |
| Callback wrong `state` | Reject; không tạo session authenticated |
| Callback missing `code`/error response | Xử lý failure, không tin login thành công |
| Callback đến node khác, request state chỉ lưu node A | Detect correlation failure, xử lý session store/affinity |
| Cookie SameSite policy cản callback | Test browser thật, cân bằng HTTPS/CSRF |
| IdP có redirect allowlist chính xác | Không nhận http/private/evil URI |
| IdP issuer/JWKS sai | Token validation reject, không giảm kiểm chữ ký |

## 8. SAML2: Entity ID, ACS, SLO và metadata phải dùng public values

Spring Security SAML2 Service Provider thường có:
- **Default SP Entity ID:** `{baseUrl}/saml2/service-provider-metadata/{registrationId}`.
- **ACS:** `/login/saml2/sso/{registrationId}` theo registration/default matcher.
- **Metadata publication:** `/saml2/metadata/{registrationId}` hoặc `/saml2/service-provider-metadata/{registrationId}` tùy DSL/version, cần bật `saml2Metadata()` khi cần.
- **SLO listener:** `/logout/saml2/slo` trong Spring SAML2 logout khi được cấu hình/bật.

Một IdP có thể yêu cầu SP issuer/entity ID **giữ nguyên qua tất cả deployments**, trong khi browser URL thay đổi. Nếu thay entity ID từ `urn:portal:prod:sp` thành `https://portal.example.org/...`, phải xem đó là **thay identity federation**, không chỉ sửa reverse proxy. Phối hợp metadata và trust registry của IdP.

### 8.1. Luồng AuthnRequest và SAMLResponse qua proxy

~~~text
Browser -> https://portal.example.org/saml2/authenticate/corporate
SP -> AuthnRequest:
  Issuer = https://portal.example.org/saml2/service-provider-metadata/corporate
  AssertionConsumerServiceURL = https://portal.example.org/login/saml2/sso/corporate
  Destination = https://idp.example.org/sso

IdP -> Browser HTTP-POST:
  https://portal.example.org/login/saml2/sso/corporate
  form SAMLResponse=[redacted] RelayState=[redacted]

SP validates:
  trusted IdP signature
  expected Issuer
  Destination / Recipient = public ACS expected by registration
  AudienceRestriction includes expected SP Entity ID
  InResponseTo matches pending AuthnRequest (SP-initiated)
  time conditions / replay protections / registered ACS
~~~

**Các trường không phải cùng một URI:**
- `AuthnRequest.Destination`: endpoint SSO của **IdP**.
- `AuthnRequest.Issuer`: **SP entity ID**.
- `AssertionConsumerServiceURL`: browser sẽ POST SAMLResponse đến **SP public ACS**.
- `SAMLResponse.Destination` và `SubjectConfirmationData.Recipient`: thường là **SP ACS public URL**, cần khớp registration.
- `AudienceRestriction`: **SP entity ID**, có thể là URN.
- `InResponseTo`: request ID; không phải URL.
- `RelayState`: binding/correlation; không được biến thành open redirect hoặc chọn IdP không tin cậy.

Nếu reverse proxy làm `Recipient=http://portal-service:8080/login/saml2/sso/corporate` trong SP expected configuration nhưng IdP gửi `https://portal.example.org/...`, Spring có thể reject SAMLResponse **dù chữ ký hợp lệ**. Đừng bỏ Recipient/Destination/Audience validation để pass.

### 8.2. Cấu hình Spring Boot SAML (fragment)

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://portal.example.org/saml2/service-provider-metadata/corporate"
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
            singlelogout:
              url: "https://portal.example.org/logout/saml2/slo"
~~~

Fragment này cần module `spring-security-saml2-service-provider`, test IdP metadata, registration và signing/decryption credentials phù hợp. `singlelogout.url` chỉ định SLO callback **tại SP**; **không phải** IdP SLO URL. SLO thường yêu cầu SP PKCS#8 signing private key và X.509 certificate được IdP trust. Nếu hệ thống không dùng SLO, không cần bật giả một endpoint để “đủ metadata”.

**ACS:** Mặc định có thể được giải từ public base URL/path của request. Nếu IdP cần **đường dẫn cố định**, cấu hình `RelyingPartyRegistration`/Boot properties cho Assertion Consumer Service Location phù hợp và verify actual generated metadata; không suy rằng `entity-id` tự đặt ACS. Metadata sau deployment là **nguồn kiểm chứng**; so full URI, không chỉ hostname.

### 8.3. SLO khi có TLS terminate / browser POST

- User RP-initiated SLO gửi LogoutRequest tới IdP; IdP sau đó POST signed LogoutResponse về `https://portal.example.org/logout/saml2/slo`.
- IdP-initiated SLO gửi signed LogoutRequest tới cùng public callback; SP validate rồi trả signed LogoutResponse tới IdP.
- Cross-site HTTP-POST binding đòi browser chuyển form/cookies đúng; `SameSite=Lax` có thể **không** gửi session cookie trên cross-site POST, dẫn đến mất pending SLO state.
- Test `InResponseTo`/LogoutRequestRepository, không bỏ correlation khi session cookie mất.
- Một 308/301 chuyển từ HTTP sang HTTPS ở callback có thể gây binding/POST issues; cấu hình IdP trực tiếp tới **HTTPS public SLO URL**.
- Không log raw `SAMLRequest`/`SAMLResponse`, NameID hoặc signed XML trong nginx access logs/APM.

### 8.4. SAML metadata sau proxy

Kiểm metadata mà IdP đăng ký:

~~~text
Expected EntityDescriptor entityID:
  https://portal.example.org/saml2/service-provider-metadata/corporate

Expected SPSSODescriptor / AssertionConsumerService Location:
  https://portal.example.org/login/saml2/sso/corporate

If SLO supported, SingleLogoutService Location:
  https://portal.example.org/logout/saml2/slo

No internal:
  http://portal-service:8080
  http://127.0.0.1:8080
  http://portal-pod-7.internal
~~~

Những Location/EntityID là ví dụ dựa trên registration được cấu hình; đừng coi `/saml2/metadata/...` chính là `entityID`. Trước khi phát metadata cho IdP production, kiểm đúng SAML binding, signed requests expectation, certificates và public URLs theo profile.

### 8.5. Test SAML callback sai do forwarded headers

| Case | Expected |
| --- | --- |
| Spring generated metadata có internal host | QA fail, sửa trusted forwarding/canonical baseURL |
| AuthnRequest ACS sai port/scheme | IdP reject hoặc browser fail; không nới IdP trust |
| IdP SAMLResponse Recipient public nhưng SP expected private | Spring reject; sửa registration |
| SAMLResponse signed bởi IdP lạ | Reject bất kể public URL |
| SAML Assertion Audience là Entity ID khác | Reject, không đổi audience check thành wildcard |
| Wrong `InResponseTo` | Reject; không bỏ request correlation |
| SAML POST callback không có cookie do SameSite | Điều chỉnh cookie/session strategy, không bypass signature |
| IdP-initiated SLO từ host sai/destination sai | Reject |
| Có nhiều registrations ở cùng public origin | Match đúng `registrationId`/issuer; không dùng Host từ user để chọn tenant |
| URL public thay đổi trong migration | IdP/SP metadata/cert/ACS/SLO cập nhật theo change plan |

## 9. CAS: service identifier và PGT callback càng cần HTTPS chính xác

Central Authentication Service (CAS) thường cấp **Service Ticket (ST)** ràng buộc với `service` đã dùng khi browser được đưa tới CAS login:

~~~text
Browser:
  https://portal.example.org/private

Portal redirect:
  https://cas.example.org/cas/login
    ?service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas

CAS redirects:
  https://portal.example.org/login/cas?ticket=ST-...

Portal validates:
  https://cas.example.org/cas/serviceValidate
    ?ticket=ST-...
    &service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas
~~~

Nếu Portal lúc redirect dùng public `https://portal.example.org/login/cas` nhưng lúc validate ST lại dùng internal `http://portal-service:8080/login/cas`, CAS có thể từ chối vì **service không khớp**. CAS ST là one-time/target-bound, không thể “bỏ validate service” để sửa.

### 9.1. ServiceProperties phải ổn định

Spring Security CAS có `ServiceProperties.service` dùng làm identifier cho CAS service callback. Khi ứng dụng sau proxy, cấu hình phải **khớp với public URL IdP/CAS đã đăng ký**; không phụ thuộc random internal Host.

~~~java
// Spring Security CAS fragment, cần module CAS tương thích.
import org.springframework.security.cas.ServiceProperties;

ServiceProperties service = new ServiceProperties();
service.setService("https://portal.example.org/login/cas");
service.setSendRenew(false);
~~~

Fragment trên **không** phải một ứng dụng chạy độc lập: còn cần CAS filter, entry point, authentication provider, ticket validator, CAS Server URLs và service registry. Không dùng `ServiceProperties.service=http://localhost:8080/...` trong production.

### 9.2. CAS Proxy PGT callback là một trust boundary khác

Nếu Portal cần xin Proxy-Granting Ticket (PGT) để gọi Reports thay user:

~~~text
Portal validates ST at CAS /serviceValidate:
  service=https://portal.example.org/login/cas
  pgtUrl=https://portal.example.org/login/cas/proxyreceptor

CAS Server --HTTPS GET--> Portal PGT callback:
  /login/cas/proxyreceptor?pgtId=...&pgtIou=...

Portal correlates PGTIOU, secures PGT in storage
Portal /proxy(PGT,targetService=Reports)
Reports /proxyValidate(PT,service=Reports)
~~~

**Khác OAuth2:** CAS Server chủ động **server-to-server HTTPS GET** tới `pgtUrl` để chuyển PGT/PGTIOU. Nó phải truy cập public/reachable HTTPS callback, kiểm certificate và chính sách callback/SP registry. Nếu edge proxy chỉ cho browser hoặc chặn CAS Server outbound, ST login có thể được nhưng PGT acquisition fail. Nếu redirect HTTP→HTTPS ngay trên PGT receptor, có thể làm callback validation fail; cấu hình ngay URL HTTPS đúng.

**Không dùng query parameter `pgtUrl` do browser chọn**: CAS gọi URL chủ động, có nguy cơ SSRF/secret exfiltration nếu registry và callback allowlist sai. Không log `pgtId`/`pgtIou` trong ingress access logs, APM traces hoặc exception. Backend phải verify TLS PKIX/hostname; tuyệt đối không dùng trust-all để “fix proxy”.

### 9.3. CAS validation và request URL

CAS client có thể dùng `ServiceAuthenticationDetailsSource`/request URL trong một số stateless flows. Kiểm service identity sau proxy ở **cả thời điểm phát login redirect, ST validation, PT validation và PGT callback**. Không suy rằng property proxy đã fix OAuth2 nên CAS tự động đúng; CAS module có thể có `service` cấu hình cố định và behavior riêng.

## 10. Kerberos/SPNEGO: hostname public là cơ sở HTTP SPN

HTTP Negotiate không giống redirect-based SAML/OIDC/CAS callback. Browser thường xin Kerberos service ticket cho **public FQDN**:

~~~text
Browser URL:
  https://portal.example.org/private

Kerberos SPN:
  HTTP/portal.example.org@EXAMPLE.ORG

Not:
  HTTP/portal-service:8080@EXAMPLE.ORG
  HTTP/portal-pod-7.internal@EXAMPLE.ORG
  https://portal.example.org/private@EXAMPLE.ORG
~~~

Nếu Nginx **chỉ proxy HTTP headers**, nó phải chuyển `WWW-Authenticate: Negotiate` từ Spring tới browser và `Authorization: Negotiate ...` từ browser tới Spring. Java acceptor dùng keytab có SPN `HTTP/portal.example.org@EXAMPLE.ORG`; việc Spring backend nghe HTTP/8080 **không** làm SPN chuyển thành Pod hostname.

Nếu Nginx/ingress **tự thực hiện Kerberos authentication**, backend không nên tự kỳ vọng raw SPNEGO token; cần thiết kế identity propagation với mTLS/trusted headers, strip injected `X-User` và application authorization. Hai mô hình phải được phân biệt trước khi debug 401 loop.

### 10.1. Lỗi và kiểm tra SPN

| Hiện tượng | Chẩn đoán |
| --- | --- |
| Không có `WWW-Authenticate: Negotiate` | Entry point/filter chain/ingress challenge sai |
| Có challenge nhưng browser không gửi `Authorization` | Browser integrated auth allowlist, TGT, KDC, VPN, proxy |
| Browser gửi token, ingress không forward | Proxy strips Authorization |
| KDC báo `KDC_ERR_S_PRINCIPAL_UNKNOWN` | Public SPN chưa đăng ký hoặc DNS/realm sai |
| `KRB_AP_ERR_MODIFIED` | Java keytab/SPN/key version/enctype không khớp ticket |
| `GSSException` channel binding mismatch | TLS termination và Extended Protection/CBT policy không tương thích |
| Java GSS pass nhưng Spring 403 | Business authorization/roles/tenant |

Không sửa `HTTP/SPN` thành tên nội bộ để khớp `serverName` của JVM. Phải tìm **actual SPN client đã xin từ KDC** và so với keytab/AD registration. Các khác biệt CNAME, load balancer, URL aliases có thể khiến client xin service ticket cho hostname khác. TLS termination có thể tác động Kerberos Extended Protection / channel binding; **không tắt EPA** hoặc bật NTLM fallback bừa bãi.

## 11. URL path prefix và reverse proxy rewrite: ca khó hơn đổi scheme

Giả sử public URL là `https://portal.example.org/app` nhưng Spring chạy ở `http://portal-service:8080/`.

Có ba cách thiết kế, **chọn một**:

**Cách A – cùng path nội bộ và public:** Servlet context path là `/app`, proxy forward `/app/...` giữ nguyên; IdP callback có `/app/login/oauth2/code/corporate`. Ưu điểm dễ đối chiếu, nhưng cần kiểm mapping `server.servlet.context-path`, actuator, cookies và router.

**Cách B – proxy strip prefix:** Nginx nhận `/app/...` rồi forward backend `/...`. Nếu Spring sinh redirect tuyệt đối thì phải biết external prefix thông qua **trusted `X-Forwarded-Prefix: /app`**/framework strategy hoặc fixed base URL. Cần kiểm Spring/Boot version thực tế, vì `X-Forwarded-Prefix` là extension có thể được các components dùng khác nhau. Không append prefix ở cả proxy và Java.

**Cách C – cố định public URLs trong federation registration:** Đặt Entity ID/ACS, OAuth redirect URI, CAS service và SLO URLs trực tiếp dưới `https://portal.example.org/app/...`; dùng public callback path contract và trusted ingress rewrite. Cách này giảm phụ thuộc request-derived scheme/host nhưng vẫn phải kiểm routing/cookies/CSRF.

### 11.1. Ma trận prefix tránh double-path

| Public URL | Backend URL | App sees externally | Đúng? |
| --- | --- | --- | --- |
| `/app/login/oauth2/code/corporate` | `/app/login/oauth2/code/corporate` | `/app/login/oauth2/code/corporate` | Đúng nếu app context path=/app |
| `/app/login/oauth2/code/corporate` | `/login/oauth2/code/corporate` | `/app/login/oauth2/code/corporate` | Đúng nếu trusted prefix được xử lý một lần |
| `/app/login/oauth2/code/corporate` | `/login/oauth2/code/corporate` | `/login/oauth2/code/corporate` | Sai, mất prefix |
| `/app/login/oauth2/code/corporate` | `/app/login/oauth2/code/corporate` | `/app/app/login/oauth2/code/corporate` | Sai, prefix hai lần |

**Kiểm cả outbound và inbound**: URL do Spring phát ra tới IdP có thể đúng nhưng proxy rewrite chiều callback bị sai (404 hoặc filter không match). Với SAML ACS HTTP POST, một `301/302` từ `/app/login/saml2/sso` tới `/login/saml2/sso` có thể làm mất body hoặc session cookie. Fix route, không dựa vào redirect để bù sai path.

### 11.2. Đổi context path không phải chỉ đổi YAML

Khi chuyển Portal từ `https://portal.example.org` sang `https://portal.example.org/app`:
- OAuth IdP allowlist redirect_uri phải đổi.
- SAML ACS/SLO locations và (nếu entity ID URL-based) SP identity phải được IdP chấp thuận.
- CAS serviceId và pgtUrl callback phải đổi.
- Cookies Path và CSRF form action phải đúng.
- Load balancer health check, login success redirect, static assets, reverse proxy rewrites phải đổi.
- Links/emails/bookmarks có thể cần migration; không phát 302 cho signed SAML POST callback như cách khắc phục chính.
- Nếu có SPNEGO, hostname không đổi nên SPN HTTP thường giữ nguyên; thay path không tự thay SPN.

## 12. HTTPS: TLS termination, backhaul và browser cookies

### 12.1. TLS termination ở edge

**TLS terminate ở LB/ingress:**

~~~text
Browser ── HTTPS ──> Edge Nginx
                          |
                          | HTTP (chỉ private same-host network)
                          v
                      Spring JVM
~~~

Mô hình có thể chấp nhận theo threat model khi backend HTTP chỉ trên loopback/private isolated network, không cho untrusted tenants sniff/inject, có network policy/firewall. Nhưng **HTTPS của browser không chứng minh backhaul đã mã hóa**; nếu proxy→JVM qua shared datacenter network, nên dùng TLS/mTLS.

**Full TLS/mTLS:**

~~~text
Browser ── HTTPS ──> Edge
                       |
                       | HTTPS or mTLS
                       v
                    Spring JVM
~~~

Ở đây phải quản lý certificates/trust chain ở cả hai hops. Kể cả backend HTTPS, Spring vẫn cần canonical public host/port vì backend có thể thấy `https://portal-service.internal:8443` chứ không phải `https://portal.example.org`.

### 12.2. TLS/redirect security checklist

- Public cert hợp lệ (CN/SAN trùng FQDN), đúng chain/trust store, tự động gia hạn và cảnh báo expiry.
- TLS versions/ciphers theo policy (thường TLS 1.2+/1.3), không tắt hostname verification trong IdP/CAS callbacks.
- HTTP port 80 chỉ redirect tới **canonical HTTPS host**; unknown Host không được dùng làm `Location`.
- HSTS trên hostname khi đã sẵn sàng. Không bật preload/includeSubDomains tùy tiện.
- Proxy→backend TLS/mTLS nếu là network không đủ cách ly; ingress/controller certificate rotation/identity được quản trị.
- Không cho client truy cập trực tiếp backend để bypass TLS, header scrub, WAF, rate limits hoặc auth.
- Không expose TLS private key trong app logs/config repos; SAML signing key và CAS keytab là secrets khác.
- Không cache login callbacks/SAML responses, `code`, `state` hay `SAMLResponse` ở reverse proxy.
- Xác định port/canonical URL trong metadata và các redirect; `:443` so với no-port phải nhất quán.

### 12.3. Browser session cookie Secure, HttpOnly, SameSite

| Thuộc tính | Gợi ý | Vì sao |
| --- | --- | --- |
| `Secure` | **true** trên public HTTPS | Không gửi session cookie trên HTTP |
| `HttpOnly` | **true** | JavaScript không đọc session cookie trực tiếp |
| `SameSite=Lax` | Thường phù hợp nhiều OAuth2 redirect GET | Cross-site top-level GET có thể gửi cookie |
| `SameSite=None; Secure` | Có thể cần với SAML HTTP-POST từ IdP | Cross-site POST thường không gửi Lax/Strict session cookie |
| `Path` | Khớp public app prefix | Callback và login pages thấy đúng cookie |
| `Domain` | Ưu tiên host-only nếu không cần shared subdomains | Giảm cookie scope |
| TTL/Session rotation | Theo risk policy | Chống stale/fixation và token misuse |

**SAML HTTP-POST lưu ý:** IdP gửi `SAMLResponse` POST qua browser tới ACS. Browser xem đây là cross-site request; nếu session cookie `SameSite=Lax`, cookie có thể không được gửi, Spring không tìm thấy pending AuthnRequest/`InResponseTo` và phát 401/invalid response. **Không tắt CSRF toàn app** để “giải quyết”; cấu hình cookie/context phù hợp và để Spring SAML validator kiểm chữ ký/issuer/recipient/audience/timestamp. Có thể phải dùng `SameSite=None; Secure` cho session cookie của ứng dụng SAML tùy browser/topology và đảm bảo CSRF cho các endpoints không phải protocol.

**OAuth2 Authorization Code:** callback thường là top-level GET nên Lax có thể hoạt động, nhưng kiểm actual browser `state` repository và cookie behavior. Một số deployments dùng response_mode=form_post hoặc iframe/front-channel; cookie policy phải theo actual callback binding, không chỉ theo tên giao thức.

**Session affinity:** Nhiều instances có thể cần shared session store hoặc sticky sessions; nếu request login ở Pod A, callback đến Pod B mà session/state repository chỉ in-memory, OAuth `state` hoặc SAML `InResponseTo` có thể fail. **Không bỏ state/correlation** để fix. Dùng Spring Session/Redis hoặc repository thiết kế phù hợp, tập trung vào privacy/TTL/secure serialization và infra.

### 12.4. CSRF với federation callbacks

User POST thay đổi trạng thái (profile, logout, payment) cần CSRF. Một số **SAML protocol endpoints** nhận POST từ IdP không có CSRF token của SP; Spring SAML filters dùng signature/trust/destination/replay checks thay vì browser form CSRF. Exemption nếu cần phải **rất hẹp** (đúng endpoint/binding) và không biến thành `csrf.disable()` toàn ứng dụng.

OAuth2 redirect GET phải xác minh `state` (và OIDC nonce/PKCE tương ứng), không coi allowed redirect URI là bảo vệ đầy đủ. CAS service ticket validation ràng buộc exact service và one-time; Kerberos JGSS validation ràng buộc service principal. Header trust không thay các protocol-specific security checks.

## 13. Java 17 standalone: kiểm canonical public callback allowlist

Mã **độc lập, biên dịch/chạy được trên JDK 17** để kiểm policy URIs khi viết deployment tests. Nó **không tạo OAuth/SAML/CAS tokens**, không validate SAML assertion và không đọc request HTTP thực. Tester cung cấp candidate URL được dựng trong unit test; ứng dụng production phải lấy canonical origin từ trusted config và giao phó authentication cho Spring Security.

**Tệp `PublicCallbackPolicyDemo.java`:**

~~~java
import java.net.URI;
import java.util.Map;

public class PublicCallbackPolicyDemo {

    static final String PUBLIC_HOST = "portal.example.org";

    static final Map<String, String> APPROVED_PATHS = Map.of(
        "OIDC", "/login/oauth2/code/corporate",
        "SAML_ACS", "/login/saml2/sso/corporate",
        "SAML_SLO", "/logout/saml2/slo",
        "CAS_ST", "/login/cas",
        "CAS_PGT", "/login/cas/proxyreceptor"
    );

    static String validate(String flow, String candidate) {
        String expectedPath = APPROVED_PATHS.get(flow);
        if (expectedPath == null) {
            return "DENY_UNKNOWN_FLOW";
        }

        URI uri;
        try {
            uri = URI.create(candidate);
        } catch (IllegalArgumentException e) {
            return "DENY_MALFORMED_URI";
        }

        if (!uri.isAbsolute()
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getQuery() != null
                || uri.getFragment() != null) {
            return "DENY_URI_SHAPE";
        }

        boolean originIsPublic =
            "https".equalsIgnoreCase(uri.getScheme())
            && PUBLIC_HOST.equalsIgnoreCase(uri.getHost())
            && (uri.getPort() == -1 || uri.getPort() == 443);

        if (!originIsPublic) {
            return "DENY_ORIGIN";
        }
        if (!expectedPath.equals(uri.getRawPath())) {
            return "DENY_PATH";
        }
        return "ALLOW_PUBLIC_CALLBACK";
    }

    static void check(String label, String flow, String url) {
        System.out.println(label + "=" + validate(flow, url));
    }

    public static void main(String[] args) {
        check("oidcOK", "OIDC",
            "https://portal.example.org/login/oauth2/code/corporate");
        check("samlOK", "SAML_ACS",
            "https://portal.example.org/login/saml2/sso/corporate");
        check("casPgtOK", "CAS_PGT",
            "https://portal.example.org/login/cas/proxyreceptor");
        check("internalHost", "OIDC",
            "http://portal-service:8080/login/oauth2/code/corporate");
        check("insecureScheme", "OIDC",
            "http://portal.example.org/login/oauth2/code/corporate");
        check("attackerHost", "OIDC",
            "https://evil.example.org/login/oauth2/code/corporate");
        check("wrongPort", "OIDC",
            "https://portal.example.org:8443/login/oauth2/code/corporate");
        check("wrongPath", "SAML_SLO",
            "https://portal.example.org/logout/saml2/other");
        check("unexpectedQuery", "CAS_ST",
            "https://portal.example.org/login/cas?next=evil");
        check("userinfo", "OIDC",
            "https://user@portal.example.org/login/oauth2/code/corporate");
        check("unknownFlow", "NTLM",
            "https://portal.example.org/login/cas");
        check("malformed", "OIDC", "bad url with spaces");
    }
}
~~~

**Chạy:**

~~~bash
javac PublicCallbackPolicyDemo.java
java PublicCallbackPolicyDemo
~~~

**Stdout chính xác:**

~~~text
oidcOK=ALLOW_PUBLIC_CALLBACK
samlOK=ALLOW_PUBLIC_CALLBACK
casPgtOK=ALLOW_PUBLIC_CALLBACK
internalHost=DENY_ORIGIN
insecureScheme=DENY_ORIGIN
attackerHost=DENY_ORIGIN
wrongPort=DENY_ORIGIN
wrongPath=DENY_PATH
unexpectedQuery=DENY_URI_SHAPE
userinfo=DENY_URI_SHAPE
unknownFlow=DENY_UNKNOWN_FLOW
malformed=DENY_MALFORMED_URI
~~~

**Giải thích các ca:**

1. OIDC, SAML ACS và CAS PGT callbacks đúng origin/path đều được cho phép.
2. Internal hostname, HTTP scheme, attacker hostname hoặc port 8443 chưa được phê duyệt → `DENY_ORIGIN`.
3. SAML SLO sai path → `DENY_PATH`.
4. Candidate có unexpected query hoặc user-info → `DENY_URI_SHAPE`; registered redirect_uri/service identifier không được tùy ý mang query dữ liệu nghiệp vụ.
5. Unknown flow và URI malformed bị từ chối.
6. Mã dùng `getRawPath()` để tránh coi percent-encoded path khác là tương đương một cách ngầm; với production, còn cần canonical URL parsing/IDNA/IPv6, normalization và policy cả prefix/ports được phê duyệt.

**Giới hạn quan trọng:** URI trong HTTP `redirect_uri` từ IdP **có thể nhận `?code=...&state=...` khi browser callback thực tế**. Demo đang validate **registered/base callback URL** trước khi thêm response parameters, nên từ chối unexpected query là đúng cho policy này. Không dùng demo để từ chối mọi OAuth callback GET có `code`/`state`. Với SAML HTTP-POST, dữ liệu response nằm trong form body. Đừng gọi `validate` với untrusted headers rồi sử dụng kết quả để cấp user authentication; đó là phạm vi của protocol validators.

### 13.1. Nâng demo thành integration assertion

Từ Spring MockMvc/IdP sandbox hãy thu **callback URL đã generate**, không thay request auth result bằng mock bool. So với canonical allowlist:
- OAuth2: parse `redirect_uri` trong outbound Authorization Request tại test IdP, so exact registered URI.
- SAML2: đọc actual generated SP metadata/`AuthnRequest.AssertionConsumerServiceURL`, so public ACS/entity ID.
- CAS: so `service` ở login redirect và ST validation, cùng approved PGT callback.
- SPNEGO: so SPN trong actual client KDC ticket metadata với keytab, không thể kiểm chỉ bằng callback policy.
- Browser: IdP trả tới callback, session/correlation/security validation thành công.
- Attack test: forged `Forwarded`/`X-Forwarded-Host` vẫn không thay generated URL.

## 14. Lệnh kiểm chứng không tiết lộ secrets

### 14.1. Chỉ kiểm HTTP headers/public scheme

Trong staging/canonical test domain:

~~~bash
# Không dùng -k để bỏ TLS peer verification.
# Không dùng -v/--trace với SAMLResponse/code/cookies thật.
curl -sSI https://portal.example.org/

# Quan sát Location header khi truy cập protected URL.
curl -sS -D /dev/stderr -o /dev/null \
  --max-redirs 0 https://portal.example.org/private
~~~

**Lưu ý:** `curl --head` gửi HEAD, một số routes có behavior khác GET; cần kiểm GET khi endpoint/matcher khác. `-D` sẽ in response headers, không dùng khi response có `Set-Cookie` hoặc `Location` chứa sensitive code/state thật nếu terminal/logs không được bảo vệ. Trong sandbox, hãy redact cookies, authorization codes, `SAMLRequest`/`SAMLResponse` và `RelayState` trước khi lưu output.

### 14.2. Kiểm Host header spoofing từ bên ngoài

Chỉ trong lab thuộc quyền quản trị, có test:

~~~bash
# Request cố ý mang Host lạ; expect edge từ chối.
curl --resolve portal.example.org:443:192.0.2.15 \
  -H 'Host: evil.example' \
  --max-redirs 0 \
  -sSI https://portal.example.org/
~~~

`192.0.2.15` là địa chỉ tài liệu RFC 5737, **không phải IP dịch vụ thật**, nên chỉ là mô tả lệnh; thay bằng IP staging đã được cấp quyền. **Expected:** default/catch-all vhost reject hoặc route isolation; không tạo `Location`/metadata chứa `evil.example`. Không thử vào hạ tầng không được phép.

Một test khác đưa forged headers từ Internet:

~~~bash
curl --resolve portal.example.org:443:192.0.2.15 \
  -H 'X-Forwarded-Host: evil.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: for=192.0.2.9;proto=http;host=evil.example' \
  --max-redirs 0 \
  -sSI https://portal.example.org/
~~~

**Expected:** edge scrub và Spring vẫn sinh URLs trong canonical `https://portal.example.org`. Test cần kết hợp **capture outbound OAuth2/SAML/CAS URL** để chứng minh, không chỉ assert 200. Nếu origin response không có redirect, kiểm metadata/diagnostic test endpoint được bảo vệ thay vì suy ra thành công.

### 14.3. SAML metadata và OIDC OAuth request

Khi `saml2Metadata()` được bật, kiểm:
- `EntityDescriptor.entityID` và `AssertionConsumerService.Location` không chứa internal IP/hostname.
- `SingleLogoutService.Location` nếu bật SLO là HTTPS public.
- Certificates được công bố đúng SP public cert, private key không lộ.
- Entity ID không thay đổi giữa pods/restarts.
- IdP sandbox import đúng metadata và phát Assertion Destination/Recipient/Audience tương ứng.

Với OAuth2, capture **outbound Authorization Request** và kiểm:
- `redirect_uri` có public HTTPS canonical URI.
- `state` được phát và được validate ở callback, PKCE/nonce khi dùng.
- Authorization endpoint/issuer là IdP đã được phê duyệt.
- Không phát callback với IP nội bộ, Host header attacker, relative path sai hoặc port 8080.
- Callback code exchange qua HTTPS, không log code/secret/token.

### 14.4. CAS và Kerberos

CAS:
- Quan sát `service` ở `/login` redirect và ở `/serviceValidate` → phải **khớp exact**.
- CAS callback `/login/cas?ticket=...` đúng public HTTPS, ticket one-time.
- Nếu dùng proxy CAS, server-to-server `pgtUrl` reachable bằng HTTPS với trust certificate và không bị ingress chặn.
- Không in ST/PGT/PGTIOU trong logs.

Kerberos:
- Test SPN `HTTP/portal.example.org@EXAMPLE.ORG` bằng KDC/client logs đã sanitized.
- `401 WWW-Authenticate: Negotiate`/`Authorization: Negotiate` được edge forward đúng (chỉ log presence).
- SPN unique và keytab KVNO/enctype đúng service account.
- TLS channel binding/EPA policy tương thích termination; không tắt security để chữa lỗi 401.

## 15. Ma trận kiểm thử positive/negative

| ID | Điều kiện | Expected |
| --- | --- | --- |
| P01 | HTTPS public request qua trusted edge | Spring thấy scheme=https, host=portal.example.org, port=443 |
| P02 | HTTP port 80 | Redirect tới canonical HTTPS host; không host injection |
| P03 | Browser forged X-Forwarded-Host | Edge overwrite, generated URLs không đổi |
| P04 | Browser forged Forwarded RFC7239 | Edge strip, generated URLs không đổi |
| P05 | Unknown Host tới public edge | Reject/isolated, không phục vụ Portal callbacks |
| P06 | Direct backend request từ untrusted client/pod | NetworkPolicy/firewall reject |
| P07 | Nginx gửi conflicting Forwarded/X-Forwarded | Test phát hiện, sửa thành một canonical source |
| P08 | Framework và native cùng xử lý headers | Phát hiện duplicate/double rewrite |
| P09 | Nginx upstream HTTP nội bộ | Không phát internal URL ra browser/IdP |
| P10 | Nginx upstream HTTPS/mTLS | Cert/trust và canonical public URL đều đúng |
| O01 | OAuth2 authorization request | `redirect_uri` chính xác public HTTPS |
| O02 | OAuth2 redirect URI http | IdP reject, sửa forwarded config |
| O03 | OAuth2 wrong registrationId/path | No unauthorized login |
| O04 | OAuth callback wrong state | Reject, không tạo authenticated session |
| O05 | Callback khác node mất state | Shared repository/session/affinity, không bỏ state |
| O06 | `issuer-uri` wrong provider | Token validation reject |
| O07 | Forged Host changes OAuth redirect | Security QA FAIL, edge reject/sanitize |
| O08 | OAuth after prefix migration | IdP URI allowlist cập nhật đúng /app |
| S01 | SAML metadata published | EntityID, ACS, SLO public correct |
| S02 | SAML AuthnRequest | ACS public, Issuer SP đúng, IdP Destination đúng |
| S03 | SAML Response correct signature/Recipient/Audience | Login pass theo role policy |
| S04 | SAML Response Recipient internal/private | Reject, sửa registration |
| S05 | SAML wrong Audience/Entity ID | Reject, không wildcard |
| S06 | IdP-initiated SAML POST to ACS | Chọn correct registration/trusted issuer |
| S07 | SAML HTTP-POST SameSite=Lax loses session | Detect correlation failure; cookie policy fix |
| S08 | SAML LogoutResponse callback after RP SLO | Verify signature/InResponseTo, no bypass |
| S09 | SAML callback redirected http→https | Test fail và sửa IdP public HTTPS URL trực tiếp |
| S10 | SP metadata contains Pod hostname | QA FAIL |
| C01 | CAS login redirect service | Exact public `https://portal.example.org/login/cas` |
| C02 | CAS /serviceValidate service | Match service used at login; otherwise reject |
| C03 | CAS pgtUrl callback | Public HTTPS, certificate trust, registered URL |
| C04 | CAS PGT receptor exposed to untrusted client | Reject unauthenticated/malformed callback; no secret leak |
| C05 | CAS PT targetService after proxy | Target-bound and exact validation at B |
| K01 | Kerberos browser ticket SPN | `HTTP/portal.example.org`, not Pod hostname |
| K02 | Ingress strips Authorization Negotiate | Fail closed; repair header forwarding |
| K03 | Browser uses alias/CNAME | SPN mapping/keytab matches actual host |
| K04 | TLS channel binding mismatch | Diagnose EPA/CBT, no blanket disable |
| T01 | Session cookie Secure/HttpOnly | Browser sends only HTTPS, not JavaScript-readable |
| T02 | SAML POST SameSite=None; Secure when necessary | Callback retains required session state |
| T03 | OAuth top-level GET with Lax | State correlation works in real browser |
| T04 | Pod A emits auth request, Pod B gets callback | Shared state or safe failure |
| T05 | Context path /app dropped or doubled | Detect via callback/metadata, fix once |
| T06 | HTTP Host with unexpected :8080 or :8443 | No unapproved callback URL |
| T07 | SAML/CAS/OAuth logs contain secrets | QA FAIL, redact/rotate/incident |
| T08 | Expired TLS certificate at ingress | TLS fail, alert/renew; no trust-all fallback |

### 15.1. Tách đúng nguyên nhân

- **OAuth2 redirect_uri_mismatch**: đầu tiên kiểm generated URL, URI IdP allowlist, edge trusted forwarding và path/port; chưa cần reset client secret.
- **OAuth2 invalid_state**: callback path/host/cookie SameSite/session repository/node; chưa cần bỏ `state`.
- **SAML Destination/Recipient mismatch**: public SP callback, metadata và reverse proxy; không bỏ signature/Recipient/Audience validation.
- **SAML bad signature**: kiểm signer/key/trust riêng, không quy ngay cho Host.
- **CAS INVALID_SERVICE**: so exact `service` strings ở login/validation, Port/Prefix/Encoding; không cấp ST mới bừa.
- **CAS proxy PGT callback fail**: kiểm HTTPS/cert/reachability/callback policy; không truyền PGT qua browser.
- **SPNEGO 401**: 401 challenge/client token/KDC SPN/keytab/CBT; public hostname ảnh hưởng SPN, nhưng OIDC callback logic không áp dụng.
- **HTTP 403 sau login thành công**: business authorization/roles/tenant; không sửa reverse proxy hoặc IdP URI.
- **Redirect loop HTTP↔HTTPS**: double SSL redirect, proxy không truyền proto đúng hoặc app chưa trust edge, có thể kết hợp session cookies không Secure.
- **Chỉ một Pod lỗi**: config/secret version/session/cookie drift, không đổi IdP toàn hệ thống ngay.

## 16. Troubleshooting theo triệu chứng

| Triệu chứng | Khả năng | Cần xác minh |
| --- | --- | --- |
| Browser thấy `Location: http://portal-service:8080` | Spring không nhận public host/proto | Proxy-set headers và forward strategy |
| IdP báo `redirect_uri_mismatch` | URL sai scheme/host/port/path | Outbound `redirect_uri` vs registry |
| OAuth callback đến đúng URL nhưng invalid_state | Session cookie/multi-node state mất | Cookie SameSite/Path, shared session store |
| IdP chỉ có http callback | IdP registry chưa cập nhật | Dùng canonical HTTPS callback |
| SAML metadata có IP nội bộ | `{baseUrl}` resolved sai | EntityID/ACS/SLO config và proxy headers |
| SAML Response Recipient mismatch | SP expected/private vs IdP public ACS | SAML registration/metadata |
| SAML Response Audience mismatch | Entity ID khác metadata | Ổn định SP identity, không bypass |
| SAML SLO POST fail từ IdP | Cookie SameSite/CSRF/HTTPS callback | Đúng protocol listener, SAML validation |
| CAS ST `INVALID_SERVICE` | `service` ở hai phía khác nhau | So exact strings, URL encoding |
| CAS PGT không được cấp | pgtUrl HTTPS/TLS/callback unreachable | IdP/CAS Server callback logs và trust |
| SPNEGO KDC_ERR_S_PRINCIPAL_UNKNOWN | Kerberos SPN chưa đăng ký | Public FQDN/AD registry |
| SPNEGO KRB_AP_ERR_MODIFIED | Keytab không khớp ticket | SPN owner/KVNO/enctype |
| Nginx gửi request tới backend nhưng Spring 404 | Prefix strip/rewrite sai | Proxy path vs servlet context path |
| Browser 401/302 loop sau HTTPS | Session cookie/redirect scheme sai | Secure/SameSite/Forwarded headers |
| One Pod pass, another fail | Config/secret/session mismatch | Node/pod-level diagnostics |
| Unknown Host được phản chiếu vào Location | Host header injection/open redirect | Catch-all host rejection và canonical config |
| Open redirect sau login via `returnUrl` | Arbitrary user input | Return URL allowlist / relative paths only |
| Callback signed SAML đến 400 sau proxy deploy | Binding/Destination/CSRF/proxy path | Compare metadata and actual callbacks |
| 308 from callback before Spring | IdP gửi HTTP thay vì HTTPS | Fix IdP registry, no redirect workaround |
| Proxy `X-Forwarded-For` client IP sai | Multi-hop IP chain trust config | Known proxies/real_ip policy |

**Thứ tự chẩn đoán:** ① Public URL scheme/host/path → ② edge host allowlist/header scrubbing → ③ JVM request scheme/port/context path → ④ IdP registered callback/metadata → ⑤ browser cookie/state → ⑥ protocol cryptographic validation → ⑦ authorization. Không bỏ các lớp bảo vệ trước chỉ để test bước sau.

## 17. Quy trình triển khai production an toàn

### 17.1. Trước khi deploy

1. **Chốt canonical origin** cho mỗi môi trường (prod/staging/dev) và từng tenant/registration.
2. **Liệt kê từng callback** OAuth2/OIDC, SAML ACS/SLO, CAS service/PGT; Kerberos SPN; đánh dấu ai sở hữu config (Platform, IAM, App, Security).
3. **Cập nhật IdP/CAS/SP metadata** trên sandbox và chuẩn bị public cert/keys trust theo process; không xóa old registration trước cutover nếu còn legitimate traffic.
4. **Thiết kế edge trust:** host allowlist, forwarded header overwrite, backend private ingress, TLS and optional mTLS.
5. **Chọn một Spring forwarding mode** (framework/native/none), có integration test về generated URLs.
6. **Kiểm prefix**: public path, proxy rewrite, servlet context, asset paths và cookie Path.
7. **Kiểm cookies** theo actual SAML POST vs OAuth GET, CSRF, session affinity/shared state.
8. **Chuẩn bị runbook rollback:** IdP allowlists/metadata, DNS, proxy config, key rollout, session expiry and redirect behaviors.
9. **Bật observability an toàn:** log aliases, outcomes, request IDs (hashed/redacted), error types, không ghi bearer params.
10. **Kiểm trực tiếp các luồng** từ browser/IdP sandbox, không coi unit tests enough.

### 17.2. During rollout

- Canary một nhóm Pod/traffic và xác minh generated redirect/metadata public đúng.
- Giám sát 401/403, OAuth2 `redirect_uri_mismatch`/`invalid_state`, SAML Destination/Recipient/correlation errors, CAS `INVALID_SERVICE`/PGT failure, Negotiate failure.
- Theo dõi redirects theo host/port/path, không chỉ HTTP status totals.
- Test signed SAML POST cross-site trên browser thật; kiểm session cookie attachment mà không log raw cookies.
- Test Host/X-Forwarded spoof từ sandbox, xác nhận edge không phản chiếu untrusted values.
- Test callback qua node khác; nếu state mất, giữ fail-closed và dừng rollout.
- Không để canary và prod dùng hai Entity IDs cùng một registration khi IdP không hỗ trợ migration đó.
- Thử external clients qua CDN/LB và internal backend direct (direct phải bị chặn hoặc ignore malicious headers).

### 17.3. Sau rollout

- Metadata/IdP registry và actual URLs nhất quán; có test định kỳ phát hiện config drift.
- TLS certificate expiry monitor, HSTS behavior, redirect loop monitor.
- Key rotation/SAML signing cert, CAS PGT trust và Kerberos keytab quản lý độc lập theo policy.
- Session store/cookie attributes/cluster settings được audit khi số Pod tăng.
- Proxy request logs được sanitize; không chứa `code`/`state`/`SAMLRequest`/`ticket=ST-...`/`pgtId`.
- Có trang hỗ trợ local vs federated logout đúng phạm vi, không hứa logout mọi thiết bị nếu không có session revocation.
- Không giữ debug endpoints/extra open actuator hoặc temporary header dumps sau khi điều tra.

## 18. Bài tập thực hành

**Bài A – vẽ trust boundary.** Với browser public HTTPS, Nginx và Spring HTTP/8080, vẽ hai URL, chú thích ở đâu TLS kết thúc, ai ghi Forwarded headers và chỗ nào chặn direct backend. Vì sao forwarded header tự gửi từ Internet không đáng tin?

**Bài B – redirect URI OIDC.** Spring gửi `redirect_uri=http://portal-service:8080/login/oauth2/code/corporate`. Hãy chỉ ra 3 lớp config cần kiểm (edge, Spring, IdP). Viết expected URI và cách test không lộ authorization code.

**Bài C – SAML metadata.** IdP đăng ký ACS `https://portal.example.org/login/saml2/sso/corporate` nhưng SP tính `http://portal-service:8080/...`. Nêu validator nào có thể fail, và sửa căn nguyên mà không tắt signature/recipient/audience checks.

**Bài D – Host spoof.** Browser gửi `Forwarded: proto=http;host=evil.example` và `X-Forwarded-Host: evil.example`. Đề xuất cấu hình edge và negative tests để callback vẫn là `https://portal.example.org`.

**Bài E – CAS.** CAS login redirect `service=https://portal.example.org/login/cas` nhưng validation dùng `service=http://portal-service:8080/login/cas`. Dự đoán kết quả, đề xuất `ServiceProperties.service` và test PGT callback HTTPS.

**Bài F – Kerberos.** Public URL `https://portal.example.org`, Nginx proxy tới `portal-pod.internal`. SPN nào client xin? Vì sao `HTTP/portal-pod.internal` trong keytab thường sai? Kiểm `WWW-Authenticate`/`Authorization` header forwarding.

**Bài G – Java 17.** Chạy `PublicCallbackPolicyDemo.java`, đối chiếu 12 stdout lines. Thêm test trailing slash và encoded path để xem expected allowlist behavior; nêu giới hạn của URI-only demo.

**Bài H – SameSite.** SAML POST callback không gửi JSESSIONID nhưng OAuth GET callback bình thường. Giải thích SameSite Lax/None; đề xuất test cookie Secure/CSRF, không tắt SAML signature hoặc OAuth `state`.

**Bài I – prefix.** App publish `/app`, ingress strip prefix trước khi forward. Cho ví dụ URL public/backend và thiết kế không double-prefix khi Spring sinh metadata, callback và cookie Path.

**Bài J – multi-node.** OAuth authorization request ở Pod A, IdP callback vào Pod B, nhận `invalid_state`. Thiết kế shared session/repository và tests; không bỏ state.

**Bài K – TLS termination.** Client→Nginx HTTPS, Nginx→Pod HTTP qua shared cluster. Phân tích threat model và điều kiện cần mTLS, HSTS, certificate renewal, network policy.

**Bài L – runbook.** Viết một check list 10 bước cho migration từ `https://portal-old.example.org` sang `https://portal.example.org`, gồm IdP registrations/SAML entity identity/CAS service/Kerberos SPN/proxy headers/TLS/cookies/rollback.

**Tiêu chí đạt:** Người học có thể thiết kế **canonical public scheme + host + port + prefix**, dựng proxy trust boundary, cấu hình Spring forwarding đúng một lần, đối chiếu OAuth redirect URI/SAML ACS+SLO+EntityID/CAS service+PGT/Kerberos SPN, hoàn thành E2E test HTTPS/browser/IdP và chống Host-header injection.

## 19. Tham khảo chính thức

- Spring Framework – ForwardedHeaderFilter và security consideration: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Boot 3.5 – Running Behind a Front-end Proxy Server (`server.forward-headers-strategy`): https://docs.spring.io/spring-boot/3.5/reference/how-to/webserver.html
- Spring Security – OAuth2 Login Core Configuration, default `{baseUrl}/login/oauth2/code/{registrationId}`: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html
- Spring Security – OAuth2 Login Advanced Configuration / Redirection Endpoint: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html
- Spring Security – OAuth2 Client Authorization Grants, URI template variables: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorization-grants.html
- Spring Security – SAML2 Login Overview, default EntityID/ACS, metadata: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security – SAML2 Metadata: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html
- Spring Security – SAML2 Single Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security – CAS Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/cas.html
- Spring Security Kerberos – SPNEGO integration: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- RFC 7239 – Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- RFC 6749 – OAuth2 Authorization Framework, redirect_uri: https://www.rfc-editor.org/rfc/rfc6749
- RFC 9700 – OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- OASIS SAML 2.0 Core, Bindings, Metadata: https://docs.oasis-open.org/security/saml/v2.0/
- OWASP – Unvalidated Redirects and Forwards Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
- OWASP – HTTP Security Response Headers Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- OWASP – Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
