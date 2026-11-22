# mTLS giữa proxy và ứng dụng và ranh giới bảo vệ đường truyền

> **Chủ đề:** Spring Security – federation. **Nhóm:** Xác thực qua proxy. Bài Knowledge hướng dẫn thiết kế, triển khai và kiểm thử **mutual TLS (mTLS) giữa reverse proxy/ingress/API gateway và ứng dụng Spring Security**. Trọng tâm là phân biệt **độ tin cậy của kết nối proxy → ứng dụng** với **danh tính người dùng cuối**, ranh giới bảo mật sau TLS termination, kiểm tra X.509/PKIX/SAN/EKU, cấu hình NGINX + Spring Boot Java 17+, và điều kiện dùng pre-authentication headers hoặc token đã xác minh mà không tạo đường bypass.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Chỉ ra **mTLS bảo vệ hop nào** khi browser → proxy → app → database và vì sao HTTPS ở browser không tự bảo vệ proxy → app.
2. Phân biệt TLS server authentication, mTLS client authentication, **service/workload identity**, **end-user authentication**, và **authorization trên tenant/tài nguyên**.
3. Cấu hình reverse proxy đóng vai TLS **client** đối với Spring app, còn Spring embedded server yêu cầu certificate từ proxy.
4. Đọc, kiểm tra và định nghĩa đúng **server certificate**, **client certificate**, CA/truststore, certificate chain, SAN, EKU, thời hạn, SNI và các chính sách thu hồi.
5. Hiểu sự khác nhau giữa **mTLS với Spring app** và **X.509 authentication của user tại edge**; không nhầm certificate proxy với certificate người dùng.
6. Chặn truy cập trực tiếp backend, spoofed `X-Forwarded-*`/`X-Authenticated-User`, bypass qua health/management port, sai TLS peer identity hoặc proxy chưa được phê duyệt.
7. Xây một luồng **mTLS + OAuth2 Resource Server JWT**: proxy được xác minh ở tầng TLS, user/token vẫn được Spring xác minh `issuer`, `audience` và `scope`.
8. Biết khi nào có thể dùng `RequestHeaderAuthenticationFilter` trong mô hình trusted pre-auth, cùng các điều kiện bắt buộc trước khi nhận header user.
9. Giải thích trong Java 17 vai trò của các điều kiện kết nối và cấp quyền bằng một console demo có stdout xác định; không giả lập mTLS như cryptographic validation thật.
10. Lập test matrix negative cases, xác nhận fail-closed, certificate rotation, HA, observability và điều tra lỗi giữa nhiều team.

**Quy tắc nền tảng:** **mTLS ở hop proxy → app chứng minh “ai là peer workload phía trước app, và kênh truyền ở hop này có được bảo vệ không?”**. Nó **không tự chứng minh “người dùng cuối là ai, đã được IdP xác thực hay chưa, có được phép đọc dữ liệu tenant X hay không?”**.

## 2. Mô hình mạng và vị trí TLS termination

Ví dụ ứng dụng SaaS chạy sau NGINX hoặc Envoy:

```text
              INTERNET / CLIENT NETWORK
  +---------------------+
  | Browser / API client|
  | TLS client          |
  +----------+----------+
             |
             | HOP 1: HTTPS (TLS)
             | Client checks proxy's public server certificate
             v
  +---------------------+
  | Edge Proxy / LB     |
  | TLS server for HOP 1|
  | TLS client for HOP 2|
  | Auth gateway, WAF   |
  +----------+----------+
             |
             | HOP 2: HTTPS + mTLS
             | Proxy verifies Spring backend server certificate
             | Spring backend verifies PROXY client certificate
             v
  +---------------------+
  | Spring Boot Service |
  | HTTPS :8443         |
  | server.ssl.client-  |
  | auth: need          |
  +----------+----------+
             |
             | HOP 3: DB / message broker / other API
             | Has independent transport & identity policy
             v
  +---------------------+
  | Database / Service B|
  +---------------------+
```

**HOP 1 và HOP 2 là hai phiên TLS khác nhau.** NGINX giải mã yêu cầu HTTP ở proxy (nơi có thể thực hiện WAF, cookie policy, authorization token inspection), rồi mã hóa lại request cho hop tới backend khi cấu hình `proxy_pass https://...`. Backend sẽ nhìn thấy kết nối đến từ proxy, **không nhìn thấy TLS client certificate của browser** trên HOP 1 nếu edge đã terminate TLS.

### 2.1. Các phương án thường gặp

| Mô hình | Browser → proxy | Proxy → ứng dụng | Ý nghĩa bảo mật |
| --- | --- | --- | --- |
| **A. TLS termination + HTTP nội bộ** | HTTPS | HTTP | Nội dung rõ ở hop 2; chỉ phù hợp khi security risk assessment cho phép một mạng tin cậy rất chặt, không phải mTLS |
| **B. TLS termination + HTTPS upstream (one-way)** | HTTPS | HTTPS, proxy xác minh cert server app | Bảo mật hop 2 và định danh app; backend **chưa** xác minh proxy client qua cert |
| **C. TLS termination + mTLS upstream** | HTTPS | HTTPS, hai phía xác minh certificate | Bảo vệ hop 2 và xác thực workload proxy/app; vẫn cần kiểm user |
| **D. TLS passthrough** | HTTPS đi xuyên proxy TCP | TLS session client kết thúc trực tiếp tại app | App có thể thấy client cert browser nếu client trình cert; edge khó xử lý nội dung HTTP; đây **không** là mTLS proxy → app theo nghĩa proxy là TLS client |
| **E. Edge xác thực client bằng mTLS** | Client trình certificate cho edge | Có thể HTTP, HTTPS hoặc mTLS tùy cấu hình | Edge biết client identity ở hop 1, app chỉ biết nếu có cơ chế chuyển thông tin đã tin cậy, hop 2 vẫn phải bảo vệ riêng |
| **F. Service mesh mTLS** | Theo ingress config | Sidecar/mesh tự xác minh workloads giữa nodes | mTLS có thể kết thúc tại sidecar thay vì JVM; app vẫn cần chính sách identity/header/user riêng |

**Không gọi mô hình B là mTLS.** B có HTTPS và backend server certificate validation, nhưng app không đòi chứng thư từ proxy. Ngược lại, nếu backend có `client-auth=need` nhưng proxy không kiểm server certificate (`proxy_ssl_verify off`), hai phía **chưa** thiết lập assurance đủ an toàn: proxy có thể bị chuyển hướng kết nối tới backend giả.

### 2.2. “End-to-end encryption” có nghĩa gì trong các mô hình?

Khi proxy terminate TLS, dữ liệu được giải mã **tại proxy** để xử lý. Hai chặng HTTPS có thể bảo đảm **mã hóa trên đường truyền giữa mỗi cặp peer**, nhưng **không** phải một kết nối TLS liên tục từ browser đến app. Vì thế:

- Người vận hành proxy có quyền xử lý/xem nội dung HTTP sau khi TLS termination; cần bảo vệ cấu hình, memory, logs, admin access và có audit.
- Nếu bắt buộc **không để proxy đọc nội dung ứng dụng**, dùng TLS passthrough hoặc **mã hóa tầng ứng dụng end-to-end** cho dữ liệu đặc biệt theo policy; không gọi hop-by-hop mTLS là end-to-end TLS session.
- TLS HOP 2 không tự bảo vệ dữ liệu khi app gửi sang DB hoặc hàng đợi ở HOP 3; cần TLS/mTLS hoặc bảo vệ riêng cho từng kết nối đó.
- Một trace ở proxy có thể chứa body/request trước khi mã hóa lại; đừng đưa secrets/cookies/token vào access log chỉ vì kết nối network đã mã hóa.

## 3. mTLS xác thực ai? Phân biệt proxy identity và user identity

Trong mTLS proxy→app:

- **App backend là TLS server**: trình X.509 certificate của `backend.internal.example.org`; proxy xác minh CA, SAN/hostname, thời hạn, thuật toán và chính sách.
- **Proxy là TLS client**: trình certificate đại diện cho chính workload proxy, ví dụ SAN `URI:spiffe://corp.example/edge/proxy-a` hoặc `DNS:edge-proxy.internal.example.org`; app xác minh CA/chain, hạn dùng và **identity được phép**.
- **End user** có thể được xác thực ở edge qua SAML/OIDC/CAS, hoặc đưa Bearer access token để backend tự kiểm. User không mặc nhiên là CN hoặc SAN trên **proxy client certificate**.
- **Tenant** là ranh giới dữ liệu/quyền của ứng dụng; không được suy từ hostname nội bộ hoặc việc proxy có một chứng thư hợp lệ.

### 3.1. Công thức 3 lớp

```text
Transport/workload authentication
    mTLS:   trusted proxy workload <--> trusted app workload
                       |
                       v
End-user authentication
    JWT/OIDC/SAML/CAS/verified pre-auth evidence
                       |
                       v
Authorization
    account + tenant + operation + resource + policy
                       |
                       v
Only then return or mutate business data
```

**Ví dụ:** Proxy có cert do Enterprise Proxy CA cấp. Kết nối tới Spring TLS 8443 thành công. Browser lại gửi `X-Authenticated-User: ceo` do tự giả mạo. Nếu edge chuyển tiếp nguyên header và Spring tin header đó, **mTLS vẫn thành công** nhưng user bị mạo danh. Vấn đề là **trust boundary của identity header**, không phải TLS bị bẻ khóa.

### 3.2. Điều gì chứng chỉ mTLS không bảo đảm?

mTLS của proxy **không** chứng minh:

- Browser đã login thành công vào IdP.
- `X-User`/`X-Email` header do proxy xác minh chứ không phải từ client.
- Bearer token có signature/audience đúng.
- User có membership tenant đang yêu cầu.
- Proxy đã thực thi role/permission đúng phiên bản.
- App không có endpoint hoặc listener khác được truy cập trực tiếp.
- Mọi traffic backend/service mesh đều đã được mã hóa.
- Các logs/caches/body trong RAM hoặc dữ liệu lưu trữ luôn được bảo vệ.
- Chứng thư proxy chưa bị lộ private key sau khi phát.
- Một CA tin cậy cấp cert cho proxy **duy nhất** — nhiều workload có thể dùng cùng CA.

**Điểm then chốt:** `client-auth=need` thường yêu cầu client trình **một chứng thư thuộc truststore**. Nếu truststore chứa CA có quyền cấp cert cho hàng trăm workload, việc mTLS thành công chỉ chứng minh cert thuộc nhóm CA tin cậy, **chưa xác định peer là proxy được phép**. Cần chính sách SAN/URI identity, dedicated CA, mTLS ingress allowlist và policy gắn với workload cụ thể.

## 4. Đọc đúng TLS, certificate, PKIX và truststore

| Thuật ngữ | Tại sao quan trọng? | Điều kiện cần kiểm |
| --- | --- | --- |
| **CA / trust anchor** | Nguồn được phép cấp certificate | Chỉ trust CA được quản trị; không trust-all |
| **Certificate chain** | Từ leaf → intermediate → root CA | Chữ ký, Basic Constraints, thời hạn và chuỗi tin cậy |
| **SAN** | Xác nhận DNS/IP/URI identity của peer | Proxy so server SAN đúng backend hostname; app kiểm workload identity của proxy qua policy |
| **Extended Key Usage (EKU)** | Mục đích sử dụng certificate | Server cert phù hợp `serverAuth`, client cert phù hợp `clientAuth` khi profile yêu cầu |
| **Key Usage** | Cách dùng private key | Phù hợp TLS signing/handshake và PKI policy |
| **SNI** | Chọn certificate/virtual host khi TLS client kết nối | Proxy gửi SNI đúng backend hostname nếu cần |
| **Hostname verification** | Chống backend giả có cert cho host khác | Không tắt, không chỉ kiểm CA mà bỏ SAN |
| **Expiration** | Chứng thư chỉ có hiệu lực trong khoảng thời gian | Theo dõi NotBefore/NotAfter, cảnh báo trước hạn |
| **Revocation** | Cert bị thu hồi do khóa lộ/ngừng tin cậy | CRL/OCSP/short-lived cert rotation theo tổ chức; kiểm khả năng triển khai |
| **Truststore** | Chứa CA/cert được phép xác minh peer | Spring backend trust proxy client CA; NGINX trust backend server CA |
| **Keystore** | Chứa certificate và private key **của chính bên** | Spring backend lưu server key; NGINX giữ proxy client key |
| **mTLS handshake** | Hai peer xác minh cert của nhau trước HTTP app | Sai trust/identity phải fail ở tầng TLS |
| **Certificate rotation** | Luân chuyển khóa/CA không gián đoạn | Overlap có kiểm soát, canary, audit, khôi phục |

Không nhầm **TLS server certificate** của Spring backend với signing certificate của SAML IdP, với OAuth2 JWK, hoặc với CAS service ticket. Chúng dùng trong lớp xác minh khác nhau; **một loại chứng thư không thay loại kia**.

### 4.1. Hai truststores thường khác nhau

```text
Proxy NGINX TLS client:
  private key /etc/nginx/certs/proxy-client.key
  certificate /etc/nginx/certs/proxy-client.crt
  trusted CA /etc/nginx/certs/backend-server-ca.pem
                |
                | HTTPS + mTLS
                v
Spring Boot TLS server:
  private key /run/secrets/backend-server.p12
  trusted CA /run/secrets/approved-proxy-client-ca.p12
```

**Hai hướng trust:**

1. NGINX phải **tin đúng backend**. Ngoài TLS, cần `proxy_ssl_verify on` và `proxy_ssl_name`/SNI đúng; NGINX `proxy_ssl_verify` trong nhiều bản mặc định **off** nếu không bật.
2. Spring phải **tin đúng client proxy**. `server.ssl.client-auth=need` yêu cầu certificate, `server.ssl.trust-store` chứa CA dùng để xác minh certificate của proxy, và chính sách workload identity phải tránh tin mọi client được cùng CA cấp.

Nếu chỉ nhập backend CA vào Spring truststore nhưng không nhập proxy CA, Spring không xác minh được proxy. Nếu chỉ thêm proxy CA vào NGINX trust bundle dùng để verify **backend server**, cũng là sai chiều trust.

### 4.2. Có certificate chưa đủ nếu peer identity quá rộng

Trường hợp nguy hiểm:

```text
Spring trusts "Corp-PKI-Root-CA"
CA này cấp cả:
  - edge-proxy-a
  - unrelated-batch-service
  - developer-workstation
Backend không phân biệt SAN/proxy workload
=> tất cả các workload có clientAuth cert hợp lệ từ CA này
   có thể vượt qua TLS client-auth nếu network cho phép.
```

Cải thiện:

- Dùng CA riêng cho **proxy-to-backend** hoặc certificate issuance policy khắt khe theo workload.
- Backend hoặc inbound gateway xác định **allowed proxy identities** dựa trên SAN/URI, leaf thumbprint/pinning có vòng đời thích hợp, hoặc policy service mesh.
- Không coi source IP tự nó là định danh mạnh; dùng network ACL **kết hợp** mTLS identity.
- Không cấp private key giống nhau cho mọi proxy nếu có thể quản lý từng workload identity; xoay/vô hiệu theo từng node.
- Kiểm tra listener/liveness/admin endpoints có cùng chính sách mTLS hay không.

**SAN identity mapping có thể được thực hiện tại TLS terminator**, không nhất thiết trong Spring Security MVC. Nếu mTLS kết thúc tại Envoy sidecar, JVM sẽ không nhận trực tiếp peer certificate gốc; policy workload phải được enforce ở sidecar/gateway và backend chỉ nhận traffic từ sidecar tin cậy. Khi app cần identity của peer, phải thiết kế đường truyền authenticated của identity đó, không tin HTTP header do client tự khai.

## 5. Xác thực người dùng qua proxy: hai mô hình chính

### 5.1. Mô hình A — Backend tự xác minh OAuth2/JWT, mTLS chỉ bảo vệ chặng mạng

```text
Browser -- Bearer access token --> NGINX
  NGINX:
    TLS từ browser; WAF/routing;
    xóa headers identity do browser tự khai;
    mTLS + forward Authorization đến backend
                             |
                             v
  Spring Boot:
    TLS engine verifies NGINX client certificate
    Spring Security validates JWT signature + iss + aud + exp + scopes
    app checks account/tenant/resource authorization
```

**Ưu điểm:** Không cần tin HTTP `X-User` làm danh tính; cả transport peer và user token được kiểm riêng. Đây là lựa chọn minh bạch cho API có OAuth2 access tokens, dễ test/tách trách nhiệm.

**Giới hạn:** Nếu login web là session cookie do proxy quản lý và backend không có token, cần giải pháp khác (pre-auth trusted, token exchange, backend session/BFF). Không tự biến ID Token dùng để login thành Access Token API; Resource Server phải kiểm **access token** dành cho API.

### 5.2. Mô hình B — Proxy xác thực user, Spring tin một header đã được bảo vệ (pre-auth)

```text
Browser -> Edge IdP login / SAML / OIDC / CAS / session
                     |
               proxy validates
                     |
        overwrite canonical X-Verified-User
        canonical identity, issuer, expiry,
        signed assertion or request context
                     |
                mTLS to Spring
                     |
     backend trusts header only from approved
     proxy workload on isolated mTLS listener
                     |
      local user mapping + authorizations
```

Spring có `RequestHeaderAuthenticationFilter` và `PreAuthenticatedAuthenticationProvider` để nạp user details từ **nguồn đã xác thực trước**. Nhưng cần thỏa **đồng thời** các điều kiện:

1. Proxy thực sự hoàn tất xác minh user bằng giao thức/phương thức IdP đã tin và kiểm session/expiry/revocation theo policy.
2. Proxy **xóa tất cả** headers user, groups, roles, issuer, audience và forwarded headers chưa tin từ browser ở ranh giới ngoài; nó **tự đặt lại** header identity chính xác.
3. Spring backend **không thể được kết nối trực tiếp** từ Internet/side-channel/other pod không có mTLS identity được phê duyệt.
4. Backend TLS yêu cầu cert và xác minh đây là **đúng proxy workload**, không chỉ một CA tổ chức rộng.
5. Không có alternate route qua management port, actuator, h2c, plain HTTP listener hoặc gRPC listener bypass.
6. Header có identity key ổn định, issuer/tenant-scope và provenance rõ. Không dùng email/display name/raw `X-Role: ADMIN` như quyền toàn hệ thống.
7. User/session ở edge được ràng buộc với từng request, có expiry/revocation và chống replay khi chuyển ngữ cảnh.
8. Backend tự map verified external identity sang local account và tenant permissions.
9. Có monitoring và test giả mạo `X-Verified-User` từ browser/direct caller.
10. Nếu cần end-to-end user evidence qua nhiều intermediaries, dùng token có **signature + audience + expiry** riêng cho backend; mTLS chở token không làm token tự đáng tin.

**Sai rất phổ biến:** `RequestHeaderAuthenticationFilter.setPrincipalRequestHeader("X-User")` rồi mở backend qua HTTP từ toàn VPC. Bất kỳ caller nội bộ nào đặt `X-User: admin` đều có thể impersonate; việc edge HTTPS/mTLS ở một route khác không cứu được route bypass.

### 5.3. `X-Forwarded-For` và `X-Authenticated-User` không cùng ý nghĩa

- `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` mô tả đường đi/URL ban đầu; **không phải identity claim của người dùng đã được xác thực**.
- `X-Authenticated-User`, `X-Verified-User` chỉ an toàn khi một trusted auth proxy đã tạo header sau login, xóa dữ liệu giả từ client và hop tới backend đã được bảo vệ.
- `X-Forwarded-Client-Cert` (XFCC) có thể chứa certificate information mà edge gửi. Nó **chỉ là một HTTP header** đối với backend nếu TLS đã terminate ở edge. Phải strip/overwrite và ràng buộc với peer trust; không tin một chuỗi base64 certificate từ client như client-certificate proof.
- `X-SSL-Client-Cert` hoặc `X-Client-Cert` từ edge không phải mặc định được Spring Security hiểu là TLS client cert đã được web container verify; tùy proxy contract và trust boundary.

**Điểm kỹ thuật:** `ForwardedHeaderFilter` của Spring có thể chuẩn hóa thông tin URL/scheme/host cho request, nhưng **không thay thế** việc edge xóa forwarded headers do người dùng đặt và **không** xác minh mTLS peer. Khi edge là trust boundary, nó phải xóa cả `Forwarded` và nhóm `X-Forwarded-*` từ client rồi ghi lại theo topology.

## 6. NGINX → Spring Boot: cấu hình mTLS thực tế theo từng hop

### 6.1. Bộ giả định có thể kiểm thử

```text
Public URL (browser -> NGINX):
  https://portal.example.org/api/reports

NGINX edge TLS listener:
  443; public certificate for portal.example.org

Backend Spring Boot TLS listener:
  https://backend.internal.example.org:8443

Backend X.509 server certificate:
  SAN DNS:backend.internal.example.org

NGINX X.509 client certificate:
  SAN DNS:edge-proxy.internal.example.org
  EKU clientAuth

Spring accepts proxy certificates:
  issued by dedicated Proxy-Client-CA
  plus allowed proxy workload identity

User token audience:
  api://reports (example only)

User token issuer:
  https://idp.example.org/realms/work
```

Tất cả domain/paths/keys ở đây chỉ để học tập; chúng **không tồn tại như một triển khai có thể hoạt động** nếu chưa cấu hình DNS, TLS, CA, IdP và network đúng. Mỗi file certificate/private key phải được cấp/mount bởi hệ quản lý secrets, **không** đưa vào repository.

### 6.2. NGINX làm TLS client đến upstream

File **fragment** `/etc/nginx/conf.d/portal.conf`, ghép vào NGINX có `http` config thực tế và các files đã được quản trị cấp:

```nginx
server {
    listen 443 ssl;
    server_name portal.example.org;

    # HOP 1: browser --> edge (server TLS)
    ssl_certificate     /etc/nginx/tls/public-fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/public-private.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    # HOP 2: edge --> backend (mTLS)
    location /api/ {
        proxy_pass https://backend.internal.example.org:8443;

        # Backend TLS server identity verification:
        proxy_ssl_server_name on;
        proxy_ssl_name backend.internal.example.org;
        proxy_ssl_verify on;
        proxy_ssl_verify_depth 3;
        proxy_ssl_trusted_certificate
            /etc/nginx/tls/backend-server-ca.pem;

        # NGINX client certificate sent to backend:
        proxy_ssl_certificate
            /etc/nginx/tls/edge-proxy-client.crt;
        proxy_ssl_certificate_key
            /etc/nginx/tls/edge-proxy-client.key;

        proxy_ssl_protocols TLSv1.2 TLSv1.3;

        # External clients may not claim these identities.
        proxy_set_header X-Verified-User "";
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Forwarded-Client-Cert "";
        proxy_set_header X-SSL-Client-Cert "";

        # Recreate canonical forwarded metadata at trusted edge.
        proxy_set_header Host portal.example.org;
        proxy_set_header X-Forwarded-Host portal.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Forwarded "";

        # For MODEL A only: pass user Access Token to Spring.
        proxy_set_header Authorization $http_authorization;
        proxy_pass_request_headers on;

        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
```

**Giải thích mTLS:**

- `proxy_pass https://...` bật TLS phía NGINX khi kết nối backend. Chỉ dùng `http://...` ở đây **không** là TLS upstream.
- `proxy_ssl_verify on` rất quan trọng; NGINX `ngx_http_proxy_module` có default `proxy_ssl_verify off`. Không được bỏ nếu yêu cầu backend authentication.
- `proxy_ssl_trusted_certificate` là CA để NGINX kiểm **backend server certificate**. Không nhầm với CA cấp client cert cho proxy.
- `proxy_ssl_name` và `proxy_ssl_server_name on` giúp NGINX gửi SNI và verify đúng hostname backend; không đặt host thành chuỗi do browser chọn.
- `proxy_ssl_certificate` và `proxy_ssl_certificate_key` cung cấp **NGINX client identity** khi Spring backend yêu cầu cert.
- `X-Verified-User ""` và các directive tương tự **không forward header** identity của browser trong model A; app không lấy user identity từ những headers ấy.
- `Authorization $http_authorization` chỉ có ý nghĩa vì Spring API **tự xác minh JWT**. Không nên chuyển browser cookie/tokens vô tội vạ tới backend khác.
- `X-Forwarded-For $remote_addr` ở trusted edge đặt IP mà NGINX trực tiếp nhìn thấy; nếu trước NGINX có LB được tin, phải thiết kế `real_ip`/hops đúng thay vì copy chuỗi IP do client giả.
- `proxy_pass_request_headers on` mặc định; bản mẫu làm rõ rằng **header stripping** chỉ kiểm một số header phổ biến. Trong production, dùng allowlist/normalized headers hoặc thêm chính sách bỏ các tên headers có thể bị abuse (`X-User`, `X-Role`, `X-Forwarded-Email`, ...). **Không coi danh sách bốn header mẫu là đầy đủ cho mọi hệ thống.**
- `proxy_pass` không có URI suffix (chỉ host:port) giúp giữ path `/api/...` theo routing phổ biến; nếu thêm `/` hoặc prefix, NGINX thay đổi path matching, cần regression test.
- Cấu hình edge nên giới hạn HTTP methods, request/body size, rate limit, timeouts, cipher suites, key permissions và log redaction theo policy.

**Cảnh báo:** Việc đặt `ssl_verify_client on` ở `server` block **của NGINX public listener** chỉ yêu cầu browser/client của **HOP 1** trình certificate. Nó **không** làm backend Spring yêu cầu NGINX client cert và **không** thay `proxy_ssl_certificate` của HOP 2. Đây là hai chiều mTLS khác nhau.

### 6.3. NGINX phải xác minh server certificate, không chỉ gửi client certificate

Một cấu hình nhìn có vẻ đã “mTLS” nhưng chưa đủ:

```nginx
location /api/ {
  proxy_pass https://backend.internal.example.org:8443;
  proxy_ssl_certificate /etc/nginx/tls/edge-proxy-client.crt;
  proxy_ssl_certificate_key /etc/nginx/tls/edge-proxy-client.key;
  # proxy_ssl_verify vẫn OFF theo default => không xác minh backend!
}
```

Phần thiếu là **server verification**: `proxy_ssl_verify on`, trusted CA và expected SNI/SAN. Nếu client NGINX không verify server, attacker trên đường mạng/DNS/ingress có thể trình cert không đáng tin và nhận request/tokens, dù client certificate phía proxy có tồn tại.

Thực hành: `nginx -t` kiểm syntax trước reload, nhưng **không chứng minh** handshake/PKIX thực sự đúng. Cần negative tests với cert sai SAN, CA lạ, expired, backend giả và chỉ chấp nhận route thành công khi NGINX verify đúng.

## 7. Spring Boot: embedded TLS server yêu cầu client certificate của proxy

Ví dụ **Spring Boot 3.x/Java 17+** chạy HTTPS trực tiếp tại port `8443`, nhận requests từ edge NGINX. File `src/main/resources/application.yml`:

```yaml
server:
  address: 0.0.0.0
  port: 8443
  ssl:
    enabled: true
    key-store: "file:/run/secrets/backend-server.p12"
    key-store-type: PKCS12
    key-store-password: "${BACKEND_KEYSTORE_PASSWORD}"
    key-alias: "backend"
    trust-store: "file:/run/secrets/proxy-client-cas.p12"
    trust-store-type: PKCS12
    trust-store-password: "${PROXY_TRUSTSTORE_PASSWORD}"
    client-auth: need
    enabled-protocols: TLSv1.2,TLSv1.3
  forward-headers-strategy: framework

app:
  auth:
    issuer-uri: "https://idp.example.org/realms/work"
    audience: "api://reports"
```

**Điểm cần hiểu:**

- `key-store` chứa **server certificate + private key** của Spring backend, SAN phải khớp `backend.internal.example.org` mà NGINX verify.
- `trust-store` chứa **CA/trust anchors tin NGINX client certificate**, không phải public cert của chính backend. Nên giới hạn CA dành riêng cho proxy workloads khi có thể.
- `client-auth: need` bắt buộc TLS client trình certificate hợp lệ. `want` là tùy chọn/không tương đương: request có thể handshake thành công **không có cert**, vì vậy không phù hợp nếu mục tiêu là cưỡng chế mTLS cho mọi request.
- `enabled-protocols` giới hạn phiên bản TLS; kiểm Tomcat/Jetty/Undertow và Java runtime hỗ trợ thực tế.
- Giá trị password lấy từ environment/secret manager, **không commit plaintext** vào YAML. App process cần quyền file read với keystore/truststore, không để public.
- `forward-headers-strategy: framework` chỉ điều chỉnh cách xử lý forwarded headers sau trusted edge; **không** yêu cầu client cert hoặc kiểm issuer/token. Edge phải xóa/thiết lập headers chính xác.
- Nếu backend chỉ nghe trên private interface thay vì `0.0.0.0`, hãy cấu hình `server.address` phù hợp; `0.0.0.0` chỉ có nghĩa bind mọi interfaces, **không thay** firewall/Kubernetes NetworkPolicy. Trên Kubernetes cluster nên chỉ public Service/Ingress ở edge, chặn backend 8443 từ caller không được phép.
- `/actuator/health` hay management listener khác không được tự miễn chính sách mTLS khi có rủi ro security; nếu probe không thể trình cert, cân nhắc probe ở sidecar/localhost hoặc management interface tách biệt và bị cô lập.

**Giới hạn:** Property keys tương ứng Spring Boot server SSL config và có thể khác theo version. Nếu dùng Spring Boot SSL Bundles có thể thay key-store/trust-store bằng `server.ssl.bundle` và bundle config, nhưng đừng trộn hai cách cấu hình mà không xác minh behavior. Ví dụ trên là **fragment trong ứng dụng Spring Boot**, không có các chứng thư thực nên không thể tự chạy thành công chỉ bằng cách copy.

### 7.1. Vì sao `client-auth=need` chưa phải toàn bộ identity policy?

Nếu truststore `proxy-client-cas.p12` tin một CA phát cert cho **nhiều service accounts**, TLS handshake của một service không phải edge proxy cũng có thể được chấp nhận. Trong production cần **thêm policy nhận diện peer proxy**, ví dụ:

- CA giới hạn duy nhất cho edge-proxy workload và quy trình issuance nghiêm;
- exact SAN URI/DNS allowlist của proxy kèm cert expiry/revocation;
- certificate identity enforcement ở ingress/sidecar hoặc app container có kiểm soát;
- network allowlist để loại caller không thể tới backend TLS port;
- mTLS workload registry/service mesh policy theo service account;
- tự động rotate cert nhanh, audit issuance và private-key access.

Không lấy `X-Forwarded-Host`, `X-Proxy-Identity` hay `X-Client-Cert` do client tự gửi làm bằng chứng chính cho việc đã xác minh **peer certificate** ở TLS engine. Đó chỉ là thông tin bổ sung nếu được tạo, ký/ràng buộc bởi một gateway thực sự đáng tin.

## 8. Spring Security application: giữ authentication của user tách khỏi mTLS

Mục này chọn **mô hình A**: backend API có TLS client authentication ở web server, còn Spring Security tự xác minh **OAuth2 access token JWT** do IdP phát cho API. Không dùng `RequestHeaderAuthenticationFilter` cho user trong ví dụ, để tránh rủi ro giả mạo identity header.

### 8.1. Maven dependencies

Trong ứng dụng Spring Boot có parent/BOM tương thích, thêm **fragment** `pom.xml`:

```xml
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
</dependencies>
```

Project cần build plugin/Java version/IdP/JWK endpoint đúng, và CA/cert thật. `spring-boot-starter-oauth2-resource-server` chỉ xử lý user access tokens, **không tự mở TLS hoặc cấp certificate cho proxy**.

### 8.2. SecurityFilterChain và JWT audience validator

File `src/main/java/com/example/proxysecurity/ApiSecurityConfig.java`:

```java
package com.example.proxysecurity;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    JwtDecoder jwtDecoder(
        @Value("${app.auth.issuer-uri}") String issuer,
        @Value("${app.auth.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "Access token audience is not this API",
                null);
            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audienceValidator));

        return decoder;
    }

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

**Đọc rõ hai đường xác minh:**

1. Trước khi HTTP request tới Spring filter chain, embedded server/Tomcat đã phải chấp nhận **TLS client certificate** của NGINX vì `client-auth=need`. Nếu cert sai/thiếu, HTTP controller không được gọi.
2. Với `/api/**` không public, `oauth2ResourceServer` xác minh JWT signature/JWK, issuer, `exp/nbf` và audience; sau đó mới tạo Spring `Authentication`. Token không phải dành cho API thì bị từ chối ngay cả khi proxy mTLS hợp lệ.
3. `JwtValidators.createDefaultWithIssuer` áp dụng issuer/time validations, còn `audienceValidator` yêu cầu đúng resource audience. Hai điều kiện đều phải đạt.
4. `.anyRequest().authenticated()` mới chứng minh JWT xác thực; application phải **thêm authorization tenant/role/resource** trong service/data layer, không trả dữ liệu business cho mọi user đã login.
5. `/api/health` được `permitAll` trong Spring chỉ có nghĩa nó không yêu cầu JWT. **TLS mTLS vẫn chạy trước**, do đó probe không có client cert vẫn bị từ chối handshake. Cần thiết kế health probe đáp ứng điều này.
6. Đoạn `SecurityFilterChain` chỉ match `/api/**`; production phải có chain cho những URL khác hoặc deny-by-default/actuator policy riêng. Đừng đưa `/admin/**` ra ngoài tất cả filter chains vì quên cấu hình.
7. `sessionCreationPolicy(STATELESS)` phù hợp REST bearer token; không biến browser SAML/OIDC session thành token API tự động.
8. Spring Security/Boot versions phải được build/test cùng BOM. Đây là **Spring class** cần dependencies, không chạy trực tiếp bằng `javac`.
9. Khi dùng ID Token từ OIDC browser login thay cho access token, app phải từ chối nếu policy Resource Server đòi **access token cho audience API**. Một ID Token có audience đúng client login thường không phải audience API, nên validator sẽ phát hiện.
10. Nếu access token của tổ chức dùng dạng **opaque**, cấu hình introspection và xác minh resource audience/scopes khác JWT; không decode giả.

### 8.3. Controller thử authentication, không cấp quyền theo cert proxy

File `src/main/java/com/example/proxysecurity/ProxySecurityApplication.java`:

```java
package com.example.proxysecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxySecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxySecurityApplication.class, args);
    }
}
```

File `src/main/java/com/example/proxysecurity/ApiController.java`:

```java
package com.example.proxysecurity;

import java.util.Map;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/health")
    public Map<String, String> health() {
        return Map.of("status", "ready");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(JwtAuthenticationToken token) {
        return Map.of(
            "authentication", "JWT_VALIDATED",
            "subject", token.getToken().getSubject());
    }
}
```

Ở staging đã có IdP, HTTPS backend keypair, NGINX client cert và truststore, `GET /api/me` với token đúng issuer/audience có thể thành công. Nếu NGINX có client cert đúng nhưng không forward Authorization header, Spring trả `401`; **đây là hành vi đúng** cho user-authenticated API. Nếu người dùng đưa token giả/sai audience, Spring cũng từ chối dù mTLS handshake đã qua.

**Đây không phải nguồn tài nguyên nhạy cảm đầy đủ.** Production không nên hiển thị subject tràn lan; cần tenant authorization, scopes, audit, replay/revocation, WAF/rate limit, bảo vệ keys, session/cookie (nếu có) theo nghiệp vụ.

## 9. Vì sao không nên bật `x509()` để coi proxy certificate là danh tính người dùng?

Spring Security có cấu hình:

```java
// Ví dụ riêng dành cho kết nối mà TLS client cert thực sự
// đại diện cho account/actor muốn authenticate.
http.x509(Customizer.withDefaults());
```

Cơ chế này trích client certificate từ servlet TLS attributes, ánh xạ principal và authorities (theo profile/bean configuration). Nếu **client certificate ở hop proxy → app là chứng thư của NGINX**, việc bật `x509()` có thể khiến Spring xác thực **NGINX như một principal**, không phải người dùng browser.

Nếu ứng dụng muốn:

- xác thực **proxy workload**: dùng backend `client-auth=need` kết hợp allowed proxy workload identity ở TLS/mesh/gateway;
- xác thực **end user mTLS trực tiếp**: cần client user certificate thật sự được giao tới TLS endpoint mà Spring đang chạy (ví dụ TLS passthrough), hoặc cơ chế được bảo vệ để chuyển dữ liệu cert user từ edge với contract rõ;
- xác thực **end user đã login ở proxy**: dùng pre-auth headers có bảo vệ hoặc token downstream được ký và ràng buộc audience/session;
- xác thực **API caller bằng Bearer access token**: dùng OAuth2 Resource Server như mục 8.

**Không có một annotation/call Spring Security nào tự đưa identity user từ TLS session của browser qua một proxy đã terminate TLS mà không có giao thức chuyển giao identity có trust.**

## 10. Trusted pre-authentication headers: khi nào được phép?

Spring Security hỗ trợ `RequestHeaderAuthenticationFilter` (pre-auth) và `PreAuthenticatedAuthenticationProvider`. Chúng giả định **một hệ thống bên ngoài đã hoàn thành xác thực** và app chỉ **nhận principal** qua request header do hệ thống đó tạo.

Trong mô hình này, **mTLS là hàng rào transport** quan trọng giữa proxy và app, nhưng cần nhiều điều kiện bổ sung.

### 10.1. Quy trình bắt buộc trước khi tin một header

```text
Client sends:
  X-Verified-User: admin       (UNTRUSTED)
  X-Forwarded-For: 127.0.0.1  (UNTRUSTED)
  Authorization: (optional)
                    |
                    v
At trusted edge:
  1. Strip ALL identity/assertion/forwarded headers from client
  2. Verify user login with OIDC/SAML/CAS, account/session/expiry
  3. Canonicalize issuer+subject and verified tenant intent
  4. Create canonical X-Verified-User (or signed internal token)
  5. Enforce HTTPS+mTLS to backend; verify backend SAN
                    |
                    v
At Spring backend:
  6. Require accepted proxy client cert (TLS)
  7. Enforce proxy certificate SAN/workload allowlist and network policy
  8. Reject direct/non-proxy paths or missing verified identity
  9. Map identity to local account; check role/tenant/resource
 10. Record audit decision (not raw credentials)
```

Nếu thiếu bước **(1)** hoặc **(6–8)**, user có thể đưa `X-Verified-User: admin` trực tiếp qua browser hoặc một service nội bộ và trở thành admin. Nếu thiếu bước **(2)**, proxy chỉ là HTTP router, không phải auth proxy. Nếu thiếu bước **(9)**, identity từ một IdP có thể đọc dữ liệu sai tenant.

### 10.2. Header-based auth và authorization của Spring

Một chuỗi như `X-Verified-User: alice` nếu đã xác minh qua trusted proxy vẫn chỉ là **định danh**, không tự là role. Application phải nạp `UserDetails`/authorities từ local data hoặc có policy mapping đã phê duyệt theo issuer.

Tránh:

```java
// SAI: tự tin bất cứ X-Role nào người dùng có thể cung cấp
String role = request.getHeader("X-Role");
grantRole(role);
```

Nên:

```text
Verified external identity = (source issuer, stable subject)
Local mapping               = accountId
Tenant membership           = (accountId, tenantId, status)
Authorization               = (accountId, tenantId, action, resource)
```

Nếu proxy chứng minh user là `alice` nhưng app không có account hoặc user bị disabled, **fail closed**; không auto-provision `ROLE_ADMIN`. Nếu phải hỗ trợ multiple IdPs, identity key **bao gồm issuer**, không chỉ email.

### 10.3. Khi người dùng và proxy đều dùng client certificates

Một edge đôi khi yêu cầu **browser/client mTLS** ở HOP 1 và dùng **proxy mTLS** ở HOP 2. Khi đó có **hai chứng thư khác nhau**:

- `ClientUserCert`: user hoặc machine client → edge, trình trong TLS HOP 1.
- `ProxyWorkloadCert`: edge → Spring, trình trong TLS HOP 2.

Backend khi đọc servlet `jakarta.servlet.request.X509Certificate` từ TLS HOP 2 thường nhận **ProxyWorkloadCert**, không phải `ClientUserCert`. Edge có thể truyền thông tin client user cert qua header đặc biệt sau khi đã verify, nhưng cần bảo vệ header, tenant mapping, expiry, revocation và chống injection. **Header raw chứa PEM certificate không chứng minh client sở hữu private key**; phải tin kết quả xác thực client certificate **do edge** thực hiện, hoặc dùng một signed assertion binding mạnh.

## 11. Kiểm soát network: không được đi vòng qua proxy

Một lỗi triển khai nghiêm trọng là edge NGINX áp OIDC/mTLS/headers đúng, nhưng Kubernetes Service `NodePort` hoặc Spring port `8080` vẫn mở cho các pods khác truy cập trực tiếp.

```text
Intended:
  Browser -> NGINX (identity verified) -> mTLS -> Spring

Attacker route:
  Other Pod -> http://spring-service:8080
               Header: X-Verified-User: admin
               -> Spring trusts header (INCORRECT)
```

Hệ thống có thể bị bypass ngay cả khi edge certificate hợp lệ vì request **không đi qua edge**. Để chặn:

1. Spring service chỉ bind TLS port đã bảo vệ, không chạy thêm HTTP listener public.
2. Kubernetes NetworkPolicy/SG/firewall giới hạn inbound theo **edge proxy/sidecar identities** và ports cần thiết.
3. App/service cluster route/Ingress rules không cho external truy cập thẳng backend Service/NodePort/LoadBalancer.
4. Nếu có admin/actuator/management listener khác, policy network/mTLS/authorization riêng, không tạo bypass.
5. Không có “internal VIP” vô tình được accept như trusted proxy khi request không có mTLS certificate.
6. Container/pod network interfaces và loopback debug endpoints được rà soát.
7. Mỗi network segment có **deny-by-default** và ngoại lệ được kiểm thử, không chỉ một bảng “allowed CIDR” quá rộng.
8. Khi TLS terminate ở sidecar Envoy, app JVM có thể nghe HTTP localhost nhưng phải hạn chế tuyệt đối đường đi sidecar → app (loopback namespace, policy, iptables/service mesh config); xác minh không có pod khác connect được app listener.
9. Load balancers/health checks nếu cần quyền riêng phải định nghĩa explicit paths và transport trust, không tạo “health bypass all”.
10. Không bỏ egress policies: một workload nội bộ bị xâm nhập có thể thử SSRF hoặc gọi backend qua chặng không có gateway.

**mTLS chứng minh peer kết nối qua một đường TLS**, nhưng không tự bảo đảm **mọi request tới app bắt buộc đi qua đường đó**. Đường bypass là lỗi kiến trúc, không phải TLS cipher yếu.

## 12. TLS ở service mesh: biết chính xác proxy đang đứng ở đâu

Nếu Kubernetes có sidecar Envoy/Istio/Linkerd:

```text
Incoming request
  -> ingress gateway
  -> [mTLS] sidecar of pod Spring
  -> [often localhost/plain HTTP] Spring JVM
```

Trong mô hình này, **mTLS có thể kết thúc tại sidecar**, không phải Spring embedded Tomcat. Do đó:

- `server.ssl.client-auth=need` trong Spring có thể **không được dùng** cho traffic sidecar→JVM nếu sidecar gửi HTTP loopback.
- Peer workload certificate được Envoy/Istio kiểm, không phải servlet certificate attribute.
- Cần NetworkPolicy/sidecar interception rules và không cho direct pod-IP/port bypass mTLS sidecar.
- Cần rõ **certificate SAN URI/workload identity** do service mesh phát, trust domain, workload selectors và authorization policies.
- Một mesh chạy `PERMISSIVE` mTLS trong quá trình migration có thể cho cả plaintext traffic; **không được báo “mTLS enforced”** khi vẫn còn đường plaintext.
- Service-to-service JWT/user authorization vẫn cần ở app hoặc ext-authz gateway, không chỉ mTLS workloads.

**Đừng cấu hình mTLS cùng lúc ở mọi lớp mà không hiểu ai terminate và ai kiểm certificate.** Hai lớp TLS chồng nhau có thể hợp lệ nhưng làm truststore, SNI, hostname và debugging phức tạp. Vẽ sơ đồ từng TLS handshake từ nơi bắt đầu đến nơi kết thúc trước khi bật chính sách.

### 12.1. Khi Envoy thực hiện upstream mTLS

Envoy có `UpstreamTlsContext` để cấp client certificate cho upstream và `validation_context.trusted_ca` cùng SAN matcher/auto SNI validation để kiểm server identity. Tương tự, backend/sidecar có `DownstreamTlsContext.require_client_certificate` và trusted CA/policy để yêu cầu identity của Envoy peer.

Cần cấu hình explicit CA + SAN validation; các tài liệu Envoy cảnh báo **upstream server certificate validation không tự bật** nếu thiếu validation context. Không suy rằng chỉ vì transport socket tên `tls` thì Envoy đang kiểm backend certificate, hoặc rằng certificate từ một CA tin cậy đủ để map đúng workload.

## 13. Lỗi chứng thư và các dấu hiệu chẩn đoán

| Triệu chứng | Hop/lớp nghi vấn | Cách kiểm |
| --- | --- | --- |
| Browser báo certificate không hợp lệ | HOP 1 browser→proxy | Public cert, SAN `portal.example.org`, chain/expiry |
| NGINX trả 502 khi gọi backend | HOP 2 proxy→Spring | Upstream TLS handshake, cert client, proxy_ssl_verify, backend logs |
| NGINX báo `upstream SSL certificate verify error` | Proxy xác minh backend cert | `proxy_ssl_trusted_certificate`, CA chain, SAN, SNI, expiry |
| Spring/Tomcat báo client cert required | Backend TLS handshake | `client-auth=need`, NGINX `proxy_ssl_certificate` và private key |
| Spring báo `PKIX path building failed` | Backend không tin proxy cert | Proxy CA, truststore chain, EKU/validity |
| NGINX handshake không gửi client cert | Proxy config | Missing proxy_ssl_certificate/key hoặc certificate không khớp key |
| SAN không khớp `backend.internal.example.org` | Backend TLS certificate | Cấp cert đúng hostname; `proxy_ssl_name`/SNI chính xác |
| TLS OK nhưng user `401` | End-user authentication | Token/issuer/audience/expiry hoặc pre-auth principal thiếu |
| TLS OK, user `403` | Authorization | Tenant/roles/object ownership, proxy allowed identity policy |
| Một node backend bị lỗi | HA cert/secret/truststore mismatch | So versions, keystore alias/SAN, CA, rollout |
| Proxy vẫn cho backend cert bất kỳ | `proxy_ssl_verify` chưa bật | Bật verify và test CA lạ, không disable TLS |
| Proxy có CA đúng nhưng kết nối nhầm backend | Hostname/SAN không kiểm | Expected SAN/SNI, DNS/routing/mesh policy |
| mTLS handshake thành công từ service lạ | Trust CA quá rộng hoặc thiếu SAN allowlist | Workload identity match/NetworkPolicy/CA scope |
| JWT hợp lệ nhưng API từ chối | `aud` khác API hoặc scope/tenant policy thiếu | Decode token **đã verify**, kiểm issuer/audience/scopes |
| Client tự gửi `X-Verified-User=admin` vẫn login | Header spoofing/edge không strip | Edge xóa/ghi lại headers, backend chỉ trusted mTLS |
| Quên `Forwarded` và chỉ xóa `X-Forwarded-*` | Header bypass theo chuẩn RFC | Xóa cả hai hệ header tại edge |
| URL callback OAuth2/SAML chuyển về HTTP | Forwarded proto/host sai | Trusted proxy forwarding/canonical app URL, cookie Secure |
| Health không qua được | Probe không có client cert | Thiết kế dedicated TLS probe/sidecar/local management path |
| Lỗi sau certificate rotation | Truststore/cert versions chưa đồng bộ | Dual trust có kiểm soát, canary, rollback |
| Quá tải handshake | Connection pooling/rotation/protocol | Quan sát TLS handshakes, session reuse, timeout/limits |
| Client cert bị thu hồi vẫn được nhận | Revocation policy chưa hoạt động | CA/CRL/OCSP hoặc short-lived cert và workload policy |
| Browser logout nhưng backend vẫn trả 200 | Local session/token chưa revoke | Session expiry, token revocation, authz policy; mTLS không logout user |

**Chẩn đoán phải biết “ai là TLS client ở hop đang lỗi”**. Nếu NGINX không tin Spring cert, sửa **NGINX trust** và Spring server cert. Nếu Spring không tin proxy cert, sửa **Spring trust** và NGINX client cert. Không import bừa tất cả CA vào cả hai hệ thống.

## 14. Lệnh kiểm thử TLS/mTLS an toàn

**Chỉ chạy trong staging/lab mà bạn có quyền quản trị**. Các tên file giả định được cấp qua secret distribution, không phải hướng dẫn phát hành certificate không có CA được phê duyệt.

### 14.1. Đọc certificate server và chain từ phía NGINX

```bash
openssl s_client \
  -connect backend.internal.example.org:8443 \
  -servername backend.internal.example.org \
  -CAfile backend-server-ca.pem \
  -verify_return_error </dev/null
```

Khi backend yêu cầu client certificate, command **không có cert** có thể thất bại handshake dù CA/SAN server đúng. Để thử đầy đủ, dùng:

```bash
openssl s_client \
  -connect backend.internal.example.org:8443 \
  -servername backend.internal.example.org \
  -cert edge-proxy-client.crt \
  -key edge-proxy-client.key \
  -CAfile backend-server-ca.pem \
  -verify_return_error </dev/null
```

Kiểm TLS handshake và certificate chain/Verify return code, nhưng **không** in private key. Đường gọi `openssl s_client` không tự kiểm endpoint application JWT/tenant authorization, và tùy phiên bản OpenSSL cách kiểm hostname cần thêm `-verify_hostname backend.internal.example.org`; nên bổ sung khi test:

```bash
openssl s_client \
  -connect backend.internal.example.org:8443 \
  -servername backend.internal.example.org \
  -verify_hostname backend.internal.example.org \
  -cert edge-proxy-client.crt \
  -key edge-proxy-client.key \
  -CAfile backend-server-ca.pem \
  -verify_return_error </dev/null
```

Nếu OpenSSL báo `Verify return code: 0 (ok)` nhưng request của NGINX vẫn 502, đừng kết luận mTLS OK toàn bộ: kiểm application HTTP, client identity policy, reverse proxy route, network MTU/timeouts và JWT. OpenSSL sử dụng truststore riêng, không đại diện cho NGINX/truststore JVM trừ khi đã cấu hình cùng nguồn CA.

### 14.2. curl vào backend với và không có client cert

```bash
# Positive transport: trusted proxy certificate in test.
curl -i \
  --cacert backend-server-ca.pem \
  --cert edge-proxy-client.crt \
  --key edge-proxy-client.key \
  https://backend.internal.example.org:8443/api/health

# Negative transport: NO client certificate.
curl -i \
  --cacert backend-server-ca.pem \
  https://backend.internal.example.org:8443/api/health
```

Kỳ vọng: lệnh đầu có thể nhận HTTP 200 nếu backend health được Spring `permitAll` **và cert đúng**, lệnh sau phải không vượt qua client-cert requirement. Tùy TLS 1.2/1.3, curl có thể báo handshake failure, connection closed, TLS alert hoặc HTTP 400 từ container; **điều quan trọng là request không được xử lý thành authenticated/authorized request**.

Một test riêng cần dùng cert do CA khác ký (dù có SAN đẹp) và một cert trusted CA nhưng identity không thuộc allowed proxy list; cả hai phải bị từ chối theo trust policy, không chỉ vì lack of cert.

### 14.3. Test user authentication vẫn độc lập

```bash
curl -i \
  --cacert backend-server-ca.pem \
  --cert edge-proxy-client.crt \
  --key edge-proxy-client.key \
  https://backend.internal.example.org:8443/api/me
```

Kỳ vọng: TLS mTLS có thể pass, nhưng `/api/me` yêu cầu JWT nên nhận `401 Unauthorized` khi không có Bearer access token.

Khi có **access token test được phát hợp lệ**:

```bash
curl -i \
  --cacert backend-server-ca.pem \
  --cert edge-proxy-client.crt \
  --key edge-proxy-client.key \
  -H "Authorization: Bearer TEST_ACCESS_TOKEN" \
  https://backend.internal.example.org:8443/api/me
```

`TEST_ACCESS_TOKEN` chỉ là ký hiệu minh họa, **không phải token thật**; lệnh sẽ 401 nếu không thay bằng token hợp lệ từ IdP test có issuer/audience đúng. Trong script thực, đọc secret từ cơ chế an toàn, tránh đưa token vào shell history, process list, CI output hay bản chụp màn hình.

**Tuyệt đối không dùng `curl -k`/`--insecure` hoặc TrustManager trust-all để khiến test báo 200.** Cách đó vô hiệu hóa bước kiểm server identity của TLS client, làm mất điều đang kiểm.

### 14.4. NGINX syntax, log và độ sâu kiểm thử

```bash
nginx -t
```

Đây là kiểm tra syntax/conventions, **không** đảm bảo private key/cert/truststore thật sự đọc được trong runtime hoặc verify backend SAN thành công. Sau reload config có approval, dùng staging request qua edge và kiểm NGINX upstream TLS status, backend cert peer policy, Spring logs đã redacted, authz decisions.

**Đừng log raw `Authorization`, cookies, certificate private keys hoặc PII trong audit.** Nên log IDs/fingerprint SHA-256 của cert đã được approve, SAN identity, TLS version, policy decision, correlation/trace IDs và HTTP status — theo retention/sensitivity policy.

## 15. Java 17 chạy độc lập: chứng minh mTLS không thay authentication user

Console demo sau **không triển khai TLS, PKIX, JWT decoder hay mạng thật**. Nó mô phỏng **logic quyết định đã có kết quả verified từ các thành phần bảo mật đáng tin**, để thấy các điều kiện **mTLS peer**, **user token** và **tenant authorization** được kiểm độc lập. Mọi biến `verified` chỉ là fixture **trong test**; không lấy boolean từ HTTP header/browser.

File `ProxyMtlsBoundaryDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public final class ProxyMtlsBoundaryDemo {

    enum Decision {
        ALLOW,
        DENY_TRANSPORT,
        DENY_PROXY_IDENTITY,
        DENY_USER_AUTHENTICATION,
        DENY_TENANT
    }

    record Evidence(
        boolean tlsPeerValidated,
        String proxyWorkloadIdentity,
        boolean userTokenValidated,
        String localAccountId,
        String requestedTenantId
    ) { }

    private static final Set<String> ALLOWED_PROXIES =
        Set.of("spiffe://corp.example/edge/portal-proxy");

    private static final Map<String, Set<String>> MEMBERSHIPS =
        Map.of("acct-42", Set.of("org-red"));

    static Decision decide(Evidence evidence) {
        if (evidence == null || !evidence.tlsPeerValidated()) {
            return Decision.DENY_TRANSPORT;
        }

        if (!ALLOWED_PROXIES.contains(
                evidence.proxyWorkloadIdentity())) {
            return Decision.DENY_PROXY_IDENTITY;
        }

        if (!evidence.userTokenValidated()
                || evidence.localAccountId() == null) {
            return Decision.DENY_USER_AUTHENTICATION;
        }

        Set<String> tenants = MEMBERSHIPS.getOrDefault(
            evidence.localAccountId(), Set.of());

        if (!tenants.contains(evidence.requestedTenantId())) {
            return Decision.DENY_TENANT;
        }

        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        Evidence good = new Evidence(
            true,
            "spiffe://corp.example/edge/portal-proxy",
            true, "acct-42", "org-red");

        Evidence noMtls = new Evidence(
            false,
            "spiffe://corp.example/edge/portal-proxy",
            true, "acct-42", "org-red");

        Evidence rogueProxy = new Evidence(
            true,
            "spiffe://corp.example/other-workload",
            true, "acct-42", "org-red");

        Evidence noUserToken = new Evidence(
            true,
            "spiffe://corp.example/edge/portal-proxy",
            false, "acct-42", "org-red");

        Evidence wrongTenant = new Evidence(
            true,
            "spiffe://corp.example/edge/portal-proxy",
            true, "acct-42", "org-blue");

        System.out.println("good=" + decide(good));
        System.out.println("noMtls=" + decide(noMtls));
        System.out.println("rogueProxy=" + decide(rogueProxy));
        System.out.println("noUserToken=" + decide(noUserToken));
        System.out.println("wrongTenant=" + decide(wrongTenant));
        System.out.println("null=" + decide(null));
    }
}
```

Chạy với JDK 17+, không cần Spring:

```bash
javac --release 17 ProxyMtlsBoundaryDemo.java
java ProxyMtlsBoundaryDemo
```

Stdout **xác định**:

```text
good=ALLOW
noMtls=DENY_TRANSPORT
rogueProxy=DENY_PROXY_IDENTITY
noUserToken=DENY_USER_AUTHENTICATION
wrongTenant=DENY_TENANT
null=DENY_TRANSPORT
```

**Giải thích:**

- `good` chỉ đạt khi **cả ba lớp** transport/workload, user authentication và tenant membership đều hợp lệ.
- `noMtls` bị từ chối ngay cả khi user đã có token, vì security contract yêu cầu đi qua trusted proxy TLS.
- `rogueProxy` có thể đã ký client cert từ một CA tin cậy nhưng **workload identity không được phép**.
- `noUserToken` cho thấy mTLS không biến một browser chưa login thành authenticated user.
- `wrongTenant` cho thấy identity cả hai lớp đúng vẫn không cấp quyền cho một tổ chức mà user không thuộc.
- `null` là input không có evidence, fail closed.

**Không dùng class này làm implementation mTLS/JWT thật.** `tlsPeerValidated` phải đến từ TLS/PKIX engine; proxy identity phải do TLS terminator/service mesh xác minh SAN; `userTokenValidated` từ Spring OAuth2 Resource Server/IdP validation; membership từ authoritative database/service. Bất kỳ giá trị boolean nào do browser gửi đều **không** được dùng như evidence.

## 16. Ma trận kiểm thử tích hợp đầy đủ

Các ca âm cần môi trường staging có CA/chứng thư kiểm thử, network policy và backend TLS listener thật. Không dùng cert/key production để cố tình tạo negative tests.

| Test case | Input hoặc cấu hình | Kết quả mong đợi |
| --- | --- | --- |
| **Happy path** | Browser HTTPS edge, NGINX mTLS backend với correct SAN/CA và valid user access token/tenant | 200 đúng tài nguyên/role |
| **HOP 1 only HTTPS** | Backend cấu hình HTTP, không mTLS | Không đáp ứng yêu cầu; báo fail security acceptance |
| **HOP 2 one-way TLS** | Backend HTTPS nhưng `client-auth: none` | Không chứng minh proxy client; fail mTLS requirement |
| **No client certificate** | Truy cập TLS 8443 không trình cert | TLS handshake/connection rejected; không vào app |
| **Untrusted client CA** | Cert proxy do CA lạ cấp | Từ chối |
| **Expired proxy cert** | Cert client hết hạn | Từ chối theo PKIX/time policy |
| **Not-yet-valid client cert** | NotBefore tương lai | Từ chối |
| **Wrong client EKU** | Client cert không phù hợp clientAuth profile | Từ chối theo TLS/PKI policy |
| **Trusted CA, wrong proxy SAN** | Other service dùng cert cùng CA | Từ chối bởi allowed proxy identity policy |
| **Wrong backend server SAN** | NGINX kết nối hostname A, cert của B | NGINX từ chối; không disable proxy_ssl_verify |
| **Untrusted backend server CA** | Backend cert CA không nằm trong NGINX trust bundle | NGINX từ chối/502 |
| **NGINX proxy_ssl_verify off** | Chỉ gửi client cert mà không xác minh backend | Fail configuration/security acceptance |
| **SNI mismatch** | Proxy upstream không gửi đúng SNI | TLS verify fail hoặc route sai; sửa SNI |
| **Proxy cert/key không khớp** | Key trong NGINX không khớp cert | Handshake/config fail |
| **Client spoof identity header** | Browser tự gửi `X-Verified-User=admin` | Edge strip, app không nâng identity |
| **Forwarded header spoof** | Browser gửi `Forwarded: host=evil...` hoặc XFH | Edge strip/overwrite; callback/host/authorization không đổi |
| **Direct backend API** | Bypass NGINX từ pod/host lạ | Network/TLS peer deny, không đến controller |
| **Internal workload có cert cùng CA** | Service không nằm trong proxy allowlist | Từ chối theo peer identity |
| **mTLS success, no access token** | Valid proxy cert, không Bearer JWT | Spring trả 401 cho `/api/me` |
| **mTLS success, invalid JWT signature** | Token giả hoặc ký key khác | 401 |
| **mTLS success, wrong JWT issuer** | Signed token từ issuer chưa được cho phép | 401 |
| **mTLS success, wrong JWT audience** | Token có aud cho API khác | 401 |
| **mTLS success, expired JWT** | `exp` quá hạn | 401 |
| **mTLS success, wrong tenant** | User authenticated, không có membership resource tenant | 403/404, không tiết lộ dữ liệu |
| **mTLS success, privilege collision** | Client gửi header `X-Role=ADMIN` | Không nâng quyền; app dùng verified policies |
| **Actuator/management alternate port** | Port khác lộ public không có cert policy | Fail security acceptance; cô lập/đóng |
| **LB direct routing** | DNS/vip tới pod backend bỏ ingress | Fail security acceptance; deny-by-default |
| **TLS 1.0/1.1 client** | Chỉ hỗ trợ phiên bản yếu | TLS negotiation bị từ chối |
| **Certificate rotation** | Roll CA/cert NGINX và backend có overlap hợp lệ | Không mở trust rộng; traffic khỏe sau cutover |
| **Compromised cert** | Proxy client private key bị lộ | Revoke/rotate, kiểm alert, không tiếp tục trust |
| **Health probe without client cert** | `/api/health` permitAll nhưng TLS need | Probe thất bại ở TLS; cấu hình probe phù hợp |
| **Service mesh permissive traffic** | Policy chấp nhận plaintext bên cạnh mTLS | Không được đánh dấu mTLS enforced |
| **Token forwarded to wrong upstream** | NGINX nhầm `proxy_pass` host/routing | Server SAN verification chặn host khác; audit policy |
| **Direct user cert mistaken as proxy cert** | Client user cert không trong allowlist proxy | Từ chối workload trust |
| **Failover another proxy** | Proxy B dùng cert SAN/CA chưa được phê duyệt | Không vào backend cho tới khi authorized identity policy |
| **Time drift** | Certificate NotBefore/After/validation clock lệch | Fail TLS; sửa NTP thay vì bỏ time validation |
| **Private key readable by non-service account** | Permission lỗi trong container | Fail operational security acceptance |
| **Authorization after successful mTLS+JWT** | User thiếu role/record permission | Deny, không coi certificate là role |

**Pass criterion cho mTLS:** Không chỉ browser nhìn thấy HTTP 200, và không chỉ `curl --cert` chạy được. Phải chứng minh backend **thật sự đòi client cert**, proxy **thật sự verify server cert/SAN**, peer workload identity đúng allowlist và request **không thể** đi qua đường bypass. Sau đó mới kiểm user/tenant business authorization.

## 17. Quy trình vận hành certificate rotation và sự cố

### 17.1. Rotation không gián đoạn có kiểm soát

```text
T0: Cũ đã được approved:
  proxy client cert P_old, backend server cert S_old,
  CA trust anchors / identity policies hợp lệ.

T1: Chuẩn bị:
  phát hành P_new và S_new với SAN/EKU/chain đúng,
  kiểm private keys, trust policies và telemetry.

T2: Chuyển trust:
  backend trust new proxy CA/identity nếu cần;
  NGINX trust new backend server CA nếu cần;
  chỉ overlap cũ+mới trong cửa sổ ngắn theo policy.

T3: Canary:
  một proxy→một backend node dùng cert mới;
  test mTLS + issuer/audience/tenant, reject cert lạ.

T4: Deploy:
  roll từng node/proxy, theo dõi TLS errors, 401, 403, 502.

T5: Thu hồi:
  loại certificate/CA/identity cũ khỏi trust policy,
  revoke nếu compromise, kiểm không còn client dùng cũ.

T6: Audit:
  lưu fingerprint, issuer, SAN, expired date, ticket,
  change owner, policy version và kết quả negative tests.
```

Nếu CA cấp client cert thay đổi, **Spring truststore** phải được cập nhật trước khi proxy đổi certificate. Nếu CA cấp backend server cert thay đổi, **NGINX proxy_ssl_trusted_certificate** phải cập nhật trước khi Spring deploy server cert mới. Luôn kiểm cả chiều **proxy tin backend** và **backend tin proxy**.

Nếu key/cert bị lộ, không chỉ gia hạn thời gian. Phải xử lý incident: revoke/rotate, khóa workload bị xâm nhập, rà soát requests/logs, giảm quyền và thực hiện revalidation các sessions/tokens liên quan theo mức độ rủi ro.

### 17.2. Tín hiệu giám sát hữu ích

Theo dõi, tránh log secrets:

- Tỷ lệ TLS handshake success/fail theo hop, protocol/cipher và lỗi X509/PKIX.
- Mốc hết hạn certificate, fingerprint, issuer, SAN/workload ID và truststore/policy version.
- `502/503/504` ở NGINX khi upstream SSL verify/connection fail; phân biệt với `401/403` của Spring.
- Các attempt tới backend không có cert hoặc cert CA/SAN lạ.
- Traffic đi trực tiếp tới backend port ngoài allowlist.
- JWT authentication failures theo issuer/audience/exp/revocation (không log raw JWT).
- Unauthorized tenant/resource operations, denied header spoof attempts, invalid forwarded hosts.
- Sự khác nhau giữa cert lỗi một pod và cert lỗi toàn cluster.
- CPU/latency do TLS handshake và reuse/connection pooling.
- Stale sessions khi user logout/role change và service mesh policy drift.

**Logging:** Được phép ghi sanitized certificate subject/SAN/fingerprint/CA và route/policy decision có kiểm soát. Không ghi TLS private keys, full client cert PEM nếu không cần, Authorization Bearer values, session cookies, SAMLResponse, ID Tokens, OIDC authorization code hoặc PII không cần thiết.

## 18. Câu hỏi tự kiểm tra kèm đáp án

**Câu 1.** Browser dùng HTTPS đến NGINX. NGINX dùng `proxy_pass http://backend:8080`. Có phải mTLS end-to-end không?

**Đáp án:** Không. HOP 2 là HTTP plaintext; HOP 1 HTTPS chấm dứt tại NGINX. Phải bật HTTPS/mTLS giữa proxy và backend nếu policy yêu cầu.

**Câu 2.** NGINX có `proxy_ssl_certificate`/`proxy_ssl_certificate_key` nhưng không bật `proxy_ssl_verify on`. Có đủ an toàn không?

**Đáp án:** Không. NGINX gửi client cert cho upstream nhưng chưa verify backend server cert/SAN theo mTLS two-way trust. Bật `proxy_ssl_verify on`, cấu hình CA, expected hostname/SNI và test certificate giả.

**Câu 3.** Spring `server.ssl.client-auth: want` có đảm bảo mọi request phải có client cert không?

**Đáp án:** Không. `want` yêu cầu tùy chọn, client có thể không cung cấp cert. Với mTLS bắt buộc, dùng `need` và cấu hình truststore/allowed proxy identity.

**Câu 4.** Mọi service có certificate do Corporate CA cấp đều kết nối được đến Spring backend; team tuyên bố chỉ NGINX được vào. Có đúng không?

**Đáp án:** Chưa đủ. Trust CA rộng không phân biệt proxy identity. Cần allowed SAN/URI workload policy, dedicated CA, network segmentation/ACL và test cert của service lạ.

**Câu 5.** Browser gửi `X-Authenticated-User: admin` vào proxy; proxy vẫn chuyển tiếp nguyên header và backend tin. mTLS có chặn được impersonation không?

**Đáp án:** Không. mTLS chứng minh proxy workload ở hop 2, không chứng minh user header. Proxy phải strip/overwrite headers sau khi xác thực user; backend chỉ nhận từ route/trust boundary đúng và kiểm quyền.

**Câu 6.** Backend Spring bật `http.x509()`, TLS client cert của kết nối proxy→app là cert NGINX. Spring xác thực ai?

**Đáp án:** Chứng thư TLS mà backend nhìn thấy thường là **NGINX workload**, không phải người dùng browser. End-user auth phải có token/pre-auth evidence riêng.

**Câu 7.** Proxy mTLS thành công nhưng không có Bearer token, `/api/me` trả 401. Đây là lỗi mTLS?

**Đáp án:** Không nhất thiết. Đây là yêu cầu user authentication riêng; TLS peer đã qua nhưng resource server đòi access token có issuer/audience đúng.

**Câu 8.** App có mTLS ở 8443 nhưng còn HTTP 8080 accessible từ pods khác. Có thể tuyên bố mTLS enforced không?

**Đáp án:** Không. Caller có thể bypass bằng HTTP listener. Phải đóng/cô lập 8080, network deny-by-default, kiểm mọi route/management port.

**Câu 9.** Mesh Envoy thực hiện mTLS giữa gateway và sidecar, nhưng sidecar gọi app qua HTTP localhost. Có cần đặt `server.ssl.client-auth: need` ở Spring không?

**Đáp án:** Không mặc định; mTLS kết thúc ở sidecar, phải kiểm mesh policy, sidecar→app isolation và tránh bypass. Nếu yêu cầu TLS trực tiếp tới JVM thì cấu hình TLS/mTLS riêng; mô hình không tự tương đương.

**Câu 10.** App chỉ kiểm mTLS proxy identity, user được login ở IdP nhưng chưa được phân quyền tenant. Có được mở mọi báo cáo không?

**Đáp án:** Không. Sau user authentication còn membership/role/resource object authorization. mTLS proxy không tự cấp business permission.

## 19. Checklist nghiệm thu trước production

- [ ] Vẽ sơ đồ HOP 1 browser→edge, HOP 2 edge→app, HOP 3 app→services; đánh dấu rõ nơi TLS terminate và nơi dữ liệu được giải mã.
- [ ] HOP 2 bắt buộc HTTPS + **mutual certificate authentication**, không chỉ `proxy_pass https` một chiều.
- [ ] NGINX/Envoy kiểm backend server certificate: CA, SAN/hostname, SNI, validity, policy; không để `proxy_ssl_verify off`.
- [ ] NGINX gửi client cert/key dành riêng cho proxy workload; key được bảo vệ, có rotation và owner.
- [ ] Spring `client-auth=need` + truststore tin client CA được phê duyệt; không dùng `want` nếu yêu cầu bắt buộc.
- [ ] Có allowed workload identity SAN/URI/CA policy hoặc chuyên biệt dedicated CA và network ACL; không accept bất cứ cert từ CA rộng.
- [ ] Proxy/sidecar không để lộ HTTP direct backend listener, alternate management ports hoặc NodePort bypass.
- [ ] Edge strip/overwrite tất cả user identity headers và `Forwarded`/`X-Forwarded-*` của caller không tin; app không dùng raw header tự khai.
- [ ] Nếu dùng `RequestHeaderAuthenticationFilter`, có hợp đồng pre-auth rõ, account mapping và session expiration/revocation.
- [ ] Nếu dùng OAuth2 Resource Server, backend validate access token issuer, signature/JWK, audience, expiry, scope; không dùng ID Token sai audience.
- [ ] X.509 principal ở Spring được hiểu là **client peer của hop đến JVM**, không tự là browser user khi TLS terminate tại proxy.
- [ ] User/tenant/resource authorization độc lập với mTLS; có tests spoof email/role/header và cross-tenant.
- [ ] Chứng thư chứa SAN/EKU và chain phù hợp, còn hiệu lực; clock/NTP đồng bộ.
- [ ] Truststore và keystore hai chiều khác nhiệm vụ, mật khẩu/keys không nằm trong repo/container image/log.
- [ ] Certificate issuance/rotation/revocation và trust overlap được kiểm soát, có canary và rollback.
- [ ] Verify tất cả NGINX pods/Spring nodes dùng cert/CA/policy version tương thích.
- [ ] Health probes, actuator/management, gRPC/websocket và background service traffic có transport trust tương xứng.
- [ ] Service mesh không ở chế độ permissive nếu yêu cầu mTLS enforced; policy reject plaintext đã được test.
- [ ] Tests kiểm missing cert, wrong CA/SAN, expired cert, wrong EKU, identity spoof, wrong JWT aud/iss, direct backend route và role/tenant deny.
- [ ] TLS/private key/Authorization/cookies không xuất hiện trong access logs/traces; audit chỉ có metadata cần thiết.
- [ ] Monitoring có SSL handshake failures, 502 upstream, 401 auth, 403 authz, cert expiry/rotation và traffic bypass attempts.
- [ ] Có runbook phân biệt 4 nguồn lỗi: TLS HOP 1, TLS/mTLS HOP 2, user authentication, business authorization.
- [ ] Áp dụng least privilege và deny-by-default ở network, trust policy, client certificate issuance, JWT audience và tenant authorization.

**Kết luận:** Trong mô hình **xác thực qua proxy**, **mTLS giữa proxy và ứng dụng** cung cấp xác thực hai chiều **workload** và bảo vệ **đường truyền đúng chặng proxy → app**. Nó **không** khôi phục một TLS session xuyên suốt từ browser đã bị terminate tại proxy, không mặc nhiên chuyển danh tính browser sang Spring, và không cấp quyền business. Cấu hình đúng phải có **NGINX xác minh backend cert + trình proxy client cert**, **Spring yêu cầu và xác minh client cert**, **khóa mọi đường bypass**, và một cơ chế **end-user authentication/authorization riêng** (JWT được xác minh tại backend hoặc pre-auth headers với trust contract nghiêm). Chỉ khi tất cả lớp đó đạt, hệ thống mới có thể chấp nhận request vào tài nguyên được bảo vệ.

## 20. Tài liệu tham khảo chính thức

1. [NGINX – Securing HTTP Traffic to Upstream Servers](https://docs.nginx.com/nginx/admin-guide/security-controls/securing-http-traffic-upstream/): `proxy_ssl_certificate`, `proxy_ssl_certificate_key`, `proxy_ssl_trusted_certificate` và `proxy_ssl_verify`.
2. [NGINX – ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): defaults `proxy_ssl_verify off`, `proxy_ssl_server_name off` và `proxy_ssl_name` dùng cho SNI/hostname.
3. [Spring Boot – Common Application Properties: server.ssl](https://docs.spring.io/spring-boot/appendix/application-properties/): `server.ssl.client-auth`, `key-store`, `trust-store`, `enabled-protocols`.
4. [Spring Boot – SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): TLS configuration và SSL bundles cho server/client.
5. [Spring Security – X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): TLS client certificate, principal mapping và Spring `x509()`.
6. [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `NimbusJwtDecoder`, validation issuer/audience và `SecurityFilterChain`.
7. [Spring Security – AbstractPreAuthenticatedProcessingFilter API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): external preauthentication và giả định trách nhiệm về header principal.
8. [Spring Framework – ForwardedHeaderFilter and Security Considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): chỉ tin forwarded headers từ trusted proxy, xóa chuẩn `Forwarded` và `X-Forwarded-*` từ edge.
9. [Envoy – Securing Envoy, Upstream/Downstream TLS](https://www.envoyproxy.io/docs/envoy/latest/start/quick-start/securing): `UpstreamTlsContext`, `DownstreamTlsContext.require_client_certificate`, trust CA và SAN.
10. [OWASP – TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS/mTLS, certificate validation và cipher policies.
11. [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): identity verification và authentication boundary.
12. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default, least privilege và resource authorization sau authentication.
13. [NIST SP 800-207 – Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): không tin mặc định mạng nội bộ, kết hợp workload identity và policy access.
14. [RFC 8446 – TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS handshake, certificate authentication và confidentiality/integrity của channel.
15. [RFC 5280 – PKIX Certificate Path Validation](https://www.rfc-editor.org/rfc/rfc5280): X.509 certificate chain, validity, extensions và trust anchors.
