# Token qua reverse proxy

Một client gọi API với `Authorization: Bearer <access-token>`, nhưng request thường **không đi thẳng tới ứng dụng Java**. Nó có thể đi qua CDN, WAF, load balancer, reverse proxy, Kubernetes ingress hoặc API gateway. Các thành phần này có thể kết thúc TLS, đổi đường dẫn, xử lý headers, xác thực token, ghi log, cache hoặc điều hướng request. Mỗi bước đều ảnh hưởng đến **tính bí mật của token, khả năng xác minh và ranh giới tin cậy**.

Ví dụ: trình duyệt gọi `https://api.example.com/orders` với access token hợp lệ. Nếu proxy bỏ `Authorization`, resource server nhận request không có credential và trả `401`. Nếu proxy ghi nguyên header vào log, Bearer token còn hạn có thể bị đánh cắp và phát lại. Nếu API tin `X-User-Id: admin` do client tự khai, kẻ tấn công có thể giả danh user dù phía issuer vẫn phát JWT an toàn.

Trong chương **Token transport** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học giải thích cách vận chuyển JWT và opaque token qua reverse proxy trong OAuth 2.0/OpenID Connect (OIDC), bảo vệ access/refresh token và cookie, kiểm tra issuer–audience–scope, xử lý TLS, forwarded headers, logging/cache và sender-constrained token (DPoP/mTLS).

> **Nguyên tắc:** Reverse proxy là một **ranh giới bảo mật**, không chỉ là thiết bị chuyển tiếp HTTP. Headers do client tự gửi không tự trở thành bằng chứng danh tính; token chỉ được tin khi thành phần có thẩm quyền kiểm tra đầy đủ.

## 1. Reverse proxy nằm ở đâu trong đường đi của token?

**Reverse proxy** nhận kết nối thay cho các server phía sau và chuyển tiếp request tới upstream phù hợp. Các triển khai thực tế thường có nhiều hop:

~~~mermaid
flowchart LR
    C["Browser / mobile / service client"] -->|"HTTPS + Bearer access token"| E["CDN / WAF / edge"]
    E -->|"Kênh tin cậy"| P["Reverse proxy / ingress"]
    P -->|"Kênh tin cậy"| G["API gateway (nếu có)"]
    G -->|"Token hoặc identity assertion"| A["Java resource server"]
    A -->|"Kiểm tra quyền"| DB["Dữ liệu"]
    AS["Authorization server / OP"] -->|"JWKS / introspection"| A
~~~

Các hop có thể được gộp thành một sản phẩm hoặc triển khai riêng. **Không mặc định mọi hop có cùng mức độ tin cậy**: ingress nội bộ, CDN bên thứ ba và API gateway có quyền truy cập, cơ chế logging và khả năng xác thực khác nhau.

| Thành phần | Trách nhiệm | Rủi ro cấu hình sai |
| --- | --- | --- |
| **Client** | Nhận/lưu credential, gửi tới đúng API | Gửi Bearer sai domain, đặt token trong URL |
| **CDN/WAF/edge** | Nhận kết nối, lọc và bảo vệ request | Log token, cache dữ liệu riêng tư |
| **Proxy/ingress** | Chuyển đúng header, host, scheme và route | Bỏ `Authorization`, spoof forwarded headers, lộ token trên HTTP nội bộ |
| **API gateway** | Có thể validate token, áp policy chung | Tin JWT sai audience, phát identity headers không được bảo vệ |
| **Resource server** | Xác thực credential và quyền trên tài nguyên | Tin `X-User-Id` giả, bỏ scope/tenant/ownership |
| **Authorization server** | Phát, kiểm tra trạng thái, thu hồi token, công bố JWKS | Cấp sai audience/scope, bảo vệ refresh token kém |

### 1.1. Đường đi của từng loại token

- **Access token:** dành cho **resource server**, thường được gửi qua `Authorization: Bearer ...`; có thể là JWT hoặc opaque.
- **ID token:** dành cho **OIDC client** để xác minh sự kiện user authentication; không thay access token ở API.
- **Refresh token:** được gửi tới **authorization server/token endpoint** để xin token mới; không chuyển xuống business API.
- **Session cookie:** browser tự gửi theo domain/path/SameSite; thường dùng cho web app/BFF và có yêu cầu CSRF riêng.
- **DPoP proof:** đi cùng DPoP-bound access token, được kiểm tra theo method, URI, hash token và khóa của sender.

Proxy không được “chuyển hóa mục đích” của token chỉ bằng cách thay header. Mỗi credential có **audience, cách xác minh và vòng đời khác nhau**.

## 2. Chuyển tiếp Bearer token đúng giao thức

RFC 6750 mô tả cách điển hình để đưa access token vào HTTP request:

~~~http
GET /api/orders/123 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json
~~~

Khi proxy chuyển token nguyên vẹn, resource server phải:

1. **JWT:** xác minh chữ ký/JWS algorithm allowlist, khóa của issuer đáng tin, `iss`, `aud`, `exp`, `nbf`, loại token/profile và claims theo hợp đồng.
2. **Opaque token:** introspect/lookup qua kênh tin cậy để kiểm tra `active`, audience, scope, principal và trạng thái.
3. **Authorization:** kiểm tra scope, tenant, membership, ownership và policy trên bản ghi thực tế.

### 2.1. Những gì proxy cần bảo toàn hoặc chuẩn hóa

| Thuộc tính | Yêu cầu | Vì sao? |
| --- | --- | --- |
| `Authorization` | Giữ nguyên theo contract, không sửa hoặc đưa vào URL | Resource server cần credential gốc để kiểm tra |
| HTTP method | Không tự ý đổi `GET/POST/PUT/DELETE` | Endpoint policy, DPoP `htm` và semantics |
| External scheme/host/path | Chỉ phục dựng từ nguồn tin cậy | Redirect URI, absolute URLs, DPoP `htu` |
| `Cookie` | Chỉ forward khi route thực sự cần | Tránh rò session và tăng kích thước header |
| Trace/request ID | Có thể bổ sung qua hệ thống tin cậy | Để điều tra, không dùng như credential |
| Request body | Không sửa tùy ý | Tính nhất quán nghiệp vụ và bảo vệ request |

Nginx và các proxy thường forward nhiều HTTP headers theo mặc định, nhưng middleware, auth filters, ingress plugins hoặc policy riêng có thể xóa/chuyển `Authorization`. **Phải thử trên đúng đường đi**, không chỉ gọi trực tiếp API.

### 2.2. Không đưa access token vào query string

~~~text
KHÔNG NÊN:
GET /orders?access_token=<secret> HTTP/1.1

NÊN:
GET /orders HTTP/1.1
Authorization: Bearer <secret>
~~~

URL có thể xuất hiện trong browser history, proxy access logs, referer, analytics và cache keys. RFC 6750 có đề cập URI query nhưng cảnh báo rủi ro; với ứng dụng mới nên **ưu tiên Authorization header qua HTTPS**. Không dùng redirect để chuyển credential sang origin không đáng tin.

## 3. TLS termination và bảo vệ từng hop

Proxy thường kết thúc TLS tại edge rồi chuyển request tới upstream:

~~~text
Mô hình A:
Client -- HTTPS --> Proxy -- HTTP nội bộ --> Java API

Mô hình B:
Client -- HTTPS --> Proxy -- HTTPS/mTLS --> Java API
~~~

Ở mô hình A, `Authorization` có thể đi ở dạng plaintext **trên hop nội bộ**. Một Kubernetes network hoặc private subnet **không tự chứng minh** không thể nghe lén hoặc can thiệp. Với Bearer token, bản sao credential bị thu thập có thể được replay trước khi `exp` hoặc trước khi revocation có hiệu lực.

| Mô hình | Ưu điểm | Lưu ý |
| --- | --- | --- |
| TLS đến edge, HTTP nội bộ | Đơn giản | Phải chấp nhận rủi ro plaintext nội bộ theo threat model; kiểm soát mạng chặt |
| TLS re-encryption đến backend | Bảo vệ token trên hop tiếp theo | Xác minh upstream certificate, CA, SNI và hostname |
| mTLS giữa proxy và backend | Mã hóa + xác thực hai chiều | Không thay user authentication, token validation hay resource authorization |
| TLS passthrough | Backend trực tiếp thấy TLS client gốc | Proxy mất một số chức năng L7; phù hợp khi cần cert gốc |

**Khuyến nghị:** bảo vệ kết nối giữa các thành phần theo threat model, tốt nhất là TLS/mTLS hoặc kênh có tính chất tương đương. Không tắt upstream certificate verification để xử lý nhanh một lỗi triển khai.

### 3.1. HTTPS không tự tạo quyền trên API

TLS chứng minh kết nối tới server/certificate được chấp nhận; nó không chứng minh người gọi được cấp `orders.write`. API vẫn phải xác minh credential, issuer, audience, scope và quyền dữ liệu.

### 3.2. Proxy có thể nhìn thấy secret

Ở điểm kết thúc TLS, proxy có thể đọc Bearer token và cookie. Cần kiểm soát ai có quyền bật packet capture, debug trace, request dump, APM instrumentation, truy cập access/error logs và sao lưu dữ liệu. “HTTPS ở Internet” không bảo vệ token khỏi một proxy bị chiếm quyền.

## 4. Hai mô hình xác thực qua reverse proxy

### 4.1. Proxy chuyển token, resource server tự xác minh

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant P as Reverse proxy
    participant API as Java resource server
    participant AS as Authorization server
    C->>P: HTTPS + Authorization Bearer AT
    P->>API: Forward AT qua kênh bảo vệ
    API->>AS: JWKS hoặc introspection theo cấu hình
    AS-->>API: Key/metadata đáng tin
    API->>API: Validate token, scope, tenant, ownership
    API-->>P: 200 / 401 / 403
    P-->>C: Phản hồi
~~~

**Ưu điểm:** mỗi API có thể kiểm tra đúng audience và policy riêng; không cần tin identity headers tự tạo. **Đổi lại**, token đi qua nhiều hop; cần bảo vệ transport/log và cách cache JWKS/introspection, revocation phù hợp.

### 4.2. Gateway xác minh rồi phát identity assertion

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as API gateway
    participant B as Backend
    C->>G: Bearer access token
    G->>G: Validate cryptography, issuer/audience, policy
    G->>G: Strip identity headers do caller gửi
    G->>B: Signed assertion / protected identity over mTLS
    B->>B: Verify source/assertion + business authorization
    B-->>G: Phản hồi
    G-->>C: Phản hồi
~~~

Mẫu B an toàn **chỉ khi**:

1. Backend **không thể bị gọi trực tiếp** bởi attacker để vượt gateway.
2. Gateway **xóa/ghi đè** `X-User-Id`, `X-Roles`, `X-Tenant-Id`, `X-Authenticated-User` và mọi identity headers do caller tự gửi.
3. Assertion có nguồn xác thực, tính toàn vẹn, audience/recipient, hạn ngắn và các claims đúng hợp đồng; hoặc dùng kết nối gateway–backend xác thực mạnh với policy chặt.
4. Backend xác minh **nguồn và assertion**, không tin một chuỗi header chỉ vì tên nó bắt đầu bằng `X-`.
5. Backend vẫn kiểm tra scope, tenant, ownership, trạng thái tài nguyên và các quy tắc nghiệp vụ.

**Gateway verify token không tự biến mọi header downstream thành đáng tin.** Token exchange, identity assertion và pass-through là các hợp đồng khác nhau; không tự lấy ID token đổi thành access token bằng cách sửa `aud`.

## 5. Khi `Authorization` bị mất ở một hop

Client gửi Bearer nhưng Java backend lại nhận:

~~~http
GET /api/orders HTTP/1.1
Host: orders.internal.example
Accept: application/json
~~~

Khi backend trả `401`, nên chẩn đoán theo thứ tự:

1. Client có gửi `Authorization` cho đúng **API origin** không, hay chỉ mới gửi CORS preflight?
2. CDN/WAF/edge có policy xóa `Authorization` hoặc redirect sang host khác?
3. Reverse proxy có ghi đè header thành rỗng, sai rewrite/routing, hoặc `auth_request` xử lý credential khác hợp đồng?
4. API gateway có **cố ý** xác thực rồi không forward, nhưng backend lại được cấu hình đòi Bearer?
5. Backend có đúng Bearer token resolver và Spring Security filter chain chưa?
6. Có hop nào giới hạn kích thước header, từ chối request trước khi nó đến Java?

**Đừng sửa bằng cách tắt authentication filter**. Đo sự hiện diện và **độ dài** header tại các hop trong môi trường test, không in token thật.

### 5.1. CORS preflight khác request dùng Bearer

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thường **không mang access token**. Proxy/Spring phải xử lý `OPTIONS` và các headers CORS theo chính sách origin/method/header trước khi trình duyệt gửi request thật. **CORS không phải cơ chế xác thực** và không bảo vệ API khỏi non-browser client; API vẫn phải xác minh Bearer token.

### 5.2. Identity headers do caller tự khai không phải bằng chứng

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
X-User-Id: admin
X-Role: super-admin
~~~

Nếu backend dùng các headers trên để tạo `Authentication`, attacker có thể giả mạo. **Chỉ tin** Bearer token đã xác minh hoặc identity assertion có nguồn tin cậy; nếu gateway tạo headers, phải strip giá trị do client gửi và chặn bypass.

## 6. `Forwarded` và `X-Forwarded-*` cần tin ở mức nào?

Backend nhận request nội bộ có thể không biết scheme/host public. Một proxy có thể tạo:

~~~http
Forwarded: for=192.0.2.45;proto=https;host=api.example.com
X-Forwarded-For: 192.0.2.45
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
~~~

Header `Forwarded` có định nghĩa tại **RFC 7239**; `X-Forwarded-*` là quy ước triển khai. **Client cũng có thể tự gửi tất cả những headers này.**

| Header | Mục đích | Nguy cơ nếu tin client |
| --- | --- | --- |
| `Forwarded` | Mô tả `for`, `proto`, `host` qua hops | Tin chuỗi hop giả |
| `X-Forwarded-For` | Client/proxy IP chain | Bypass IP allowlist/rate limit nếu parse sai |
| `X-Forwarded-Proto` | Scheme public | Tạo redirect/cookie policy sai |
| `X-Forwarded-Host` | Host public | Host-header injection, callback/password-reset poisoning |
| `X-Forwarded-Port` | Port public | Sinh absolute URL sai hoặc nới routing |

### 6.1. Ranh giới tin cậy cần có

1. Định nghĩa danh sách **trusted proxies/hops** theo địa chỉ hoặc kết nối đã xác thực.
2. Tại edge đầu tiên do mình kiểm soát, **loại bỏ các forwarded headers không tin cậy** rồi đặt metadata mới từ connection thực tế.
3. Nếu phía trước có CDN đã được tin, xử lý chuỗi proxy theo đúng danh sách trusted hops; không lấy phần tử đầu `X-Forwarded-For` mà không kiểm tra provenance.
4. Giới hạn **public hosts và schemes** được phép khi tạo redirect URI/OIDC callback hoặc xác minh DPoP.
5. Backend chỉ bật hỗ trợ forwarded headers khi **đường kết nối từ proxy đã được kiểm soát**; chặn đường truy cập trực tiếp từ Internet.

**Lưu ý Nginx:** `$proxy_add_x_forwarded_for` nối giá trị `$remote_addr` vào header `X-Forwarded-For` sẵn có. Nếu client được phép đưa IP giả vào header ban đầu, kết quả có thể chứa IP giả. Ở first trusted edge, cần thay giá trị không tin cậy hoặc xử lý theo trusted-hop policy rõ ràng.

### 6.2. Hệ quả với OAuth redirect

Ứng dụng sau proxy có thể muốn tạo `redirect_uri=https://app.example.com/login/oauth2/code/provider` nhưng tự nhìn thấy `http://internal:8080`. Không giải quyết bằng cách mở wildcard redirect URI ở authorization server hoặc tin `X-Forwarded-Host` tùy ý. Cần cấu hình **public origin cố định**, exact redirect URI và forwarding trust đúng.

## 7. Ví dụ Nginx chuyển tiếp Bearer token

Đoạn sau minh họa **HTTPS reverse proxy ở first trusted edge** chuyển request tới Java API bằng HTTPS. Các đường dẫn/chứng chỉ và upstream là placeholder; ví dụ **không phải cấu hình production đầy đủ**.

~~~nginx
upstream orders_backend {
    server orders.internal.example:8443;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/nginx/tls/edge-fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/edge-key.pem;

    location /api/ {
        proxy_pass https://orders_backend;

        # Public host cố định theo virtual host đã đăng ký.
        proxy_set_header Host api.example.com;
        proxy_set_header X-Forwarded-Host api.example.com;
        proxy_set_header X-Forwarded-Proto https;

        # First trusted edge: không nối XFF do caller tự khai.
        # Nếu có CDN upstream, cần chính sách trusted-hop khác.
        proxy_set_header X-Forwarded-For $remote_addr;

        # Chuyển nguyên credential, không đưa vào URL.
        proxy_set_header Authorization $http_authorization;

        # Verify TLS tới backend, kể cả CA/SNI/hostname.
        proxy_ssl_server_name on;
        proxy_ssl_name orders.internal.example;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate /etc/nginx/tls/upstream-ca.pem;

        # Nếu proxy_cache được bật ở nơi khác, không dùng
        # cache cho request mang Authorization hoặc Cookie.
        proxy_cache_bypass $http_authorization $http_cookie;
        proxy_no_cache     $http_authorization $http_cookie;
    }
}
~~~

### 7.1. Những giới hạn của ví dụ

- `proxy_set_header Authorization $http_authorization` **chỉ chuyển header**, không verify chữ ký, issuer hoặc scope.
- `proxy_ssl_verify on` cần CA đúng, SNI/hostname tương thích, certificate validity; không tắt chỉ vì chứng chỉ sai.
- `X-Forwarded-For $remote_addr` ở first trusted edge là cách **không sao chép IP caller tự khai**. Nếu phía trước còn CDN, `$remote_addr` có thể là IP CDN và cần cấu hình `real_ip` chỉ tin dải CDN đã kiểm chứng.
- `Host`, `X-Forwarded-Host` và `X-Forwarded-Proto` cố định phù hợp một public endpoint. Với nhiều host hợp lệ, dùng mapping/allowlist cụ thể.
- Những proxy headers hoặc custom identity headers khác có thể vẫn được chuyển tiếp; nếu backend tin chúng thì **phải strip/overwrite ở edge** theo trust contract.
- `proxy_cache_bypass` và `proxy_no_cache` không thay `Cache-Control`, cache key hoặc chính sách CDN ở hop khác.
- Logging, TLS policy, rate limits, max header size, timeouts, route integrity và mô hình DPoP/mTLS cần cấu hình/test riêng.

Nếu route Bearer API không dùng cookie, có thể **xem xét không forward `Cookie`** để giảm rò session. Nhưng không được xóa cookie trên route BFF/session cần cookie, CSRF hoặc chính sách đăng nhập.

## 8. Java/Spring Security sau reverse proxy

Với **Spring Boot 3/Spring Security 6**, ứng dụng có thể cần diễn giải forwarded headers để xây public URL:

~~~yaml
# Chỉ bật khi backend nhận qua proxy đáng tin đã strip header giả.
server:
  forward-headers-strategy: framework

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
~~~

`forward-headers-strategy: framework` không tự kiểm tra địa chỉ/kết nối của proxy. **Không bật rồi expose backend trực tiếp ra Internet.** Cấu hình `native` hoặc container-specific có cơ chế trusted proxy riêng; cần kiểm tra hành vi thực tế của Tomcat/Jetty/ingress khi sử dụng.

### 8.1. Resource server phải kiểm tra JWT độc lập

Ví dụ `JwtDecoder` xác minh issuer, audience và thời gian theo cấu hình trusted key, kết hợp `SCOPE_` authority:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
public class OrdersApiSecurity {
    private static final String ISSUER = "https://auth.example.com";
    private static final String AUDIENCE =
        "https://api.example.com/orders";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://auth.example.com/.well-known/jwks.json")
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience() != null &&
                    jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null)
            );
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audience
        ));
        return decoder;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> {}))
            .build();
    }
}
~~~

**Không coi đây là cấu hình production trọn vẹn:** còn phải ràng buộc algorithm và key policy, token type/profile, claims bắt buộc, tenant/ownership, revocation và CSRF khi có credential tự gửi. Java API không được hạ chuẩn validation chỉ để workaround lỗi proxy.

### 8.2. Opaque token qua cùng reverse proxy

Với opaque access token, proxy chuyển `Authorization` theo cùng cách, nhưng API dùng token introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: <secret-from-protected-configuration>
~~~

Trong dự án thật, secret phải lấy từ **secret manager hoặc cấu hình được bảo vệ**, không commit plaintext trong repo. Introspection yêu cầu TLS và xác thực API với AS; resource server vẫn kiểm tra audience, scope, principal, trạng thái `active` và quyền trên tài nguyên.

## 9. Không dùng `X-Forwarded-For` làm quyền user/tenant

`X-Forwarded-For` hỗ trợ rate limiting hoặc phân tích sự cố, nhưng **IP không phải danh tính user**. `X-Forwarded-Host` hỗ trợ phục dựng URL, nhưng không chứng minh quyền trên organization.

Ví dụ:

~~~http
GET /api/tenants/globex/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer <token-for-acme>
X-Forwarded-For: 10.0.0.1
X-User-Id: admin
~~~

API phải từ chối nếu token không được cấp cho Globex hoặc user không sở hữu order 42. Truy vấn dữ liệu nên ràng buộc tenant từ **nguồn đã xác minh**:

~~~sql
SELECT *
FROM orders
WHERE order_id = :order_id
  AND tenant_id = :verified_tenant_id;
~~~

`:verified_tenant_id` không được lấy từ `X-Tenant-Id` hay URL của client rồi coi là quyền. Mismatch phải bị từ chối, kể cả Bearer token hợp lệ về chữ ký.

## 10. DPoP qua proxy: method/URL có thể bị rewrite

**DPoP (RFC 9449)** ràng buộc access token với khóa public/private và dùng **proof JWT theo request**. Ví dụ payload minh họa:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.com/orders/123",
  "iat": 1800000000,
  "jti": "unique-proof-id-001",
  "ath": "<base64url-sha256-of-access-token>"
}
~~~

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.com
Authorization: DPoP <dpop-bound-access-token>
DPoP: <signed-proof-jwt>
~~~

Proxy có thể nhận public URL `https://api.example.com/orders/123` rồi rewrite nội bộ thành `http://orders:8080/internal/orders/123`. Nếu nơi xác minh DPoP so `htu` với **URL nội bộ**, proof hợp lệ sẽ bị từ chối. Nếu nơi xác minh tin spoofed `X-Forwarded-Host` từ client, attacker có thể thay bối cảnh kiểm tra.

**Thiết kế đúng:**

1. Xác định **bên xác minh DPoP**: gateway tin cậy hay resource server.
2. Dùng **external request URI chuẩn hóa và tin cậy** cho `htu`, phương thức thực cho `htm`; tuân quy tắc so URI của RFC 9449.
3. Verify chữ ký DPoP proof, `iat`, `jti` chưa reuse, `ath` khớp access token, nonce nếu server yêu cầu.
4. So thumbprint khóa của proof với `cnf.jkt`/confirmation đáng tin của access token.
5. Không fallback thành **Bearer thuần** nếu DPoP-bound token không có proof hoặc sender binding sai.

**Access-token JWT signature và DPoP proof signature là hai kiểm tra khác nhau.** Chuyển header `DPoP` qua proxy không có nghĩa đã chống replay; cần replay cache và kiểm tra key binding đúng.

## 11. mTLS-bound token qua TLS termination

Với **mTLS-bound access token (RFC 8705)**, token có thể gắn với thumbprint chứng chỉ client, chẳng hạn `cnf["x5t#S256"]`. Resource server phải xác minh chứng chỉ client tương ứng đã được xác thực.

Nếu TLS client kết thúc tại gateway, backend **không trực tiếp thấy chứng chỉ gốc**. Header:

~~~http
X-SSL-Client-Cert: <certificate-information>
~~~

**không đáng tin nếu caller Internet có thể tự gửi**. Gateway phải strip header giả, tự xác minh client cert và truyền kết quả bằng kênh/identity assertion đáng tin. Backend cần kiểm tra nguồn/assertion. **mTLS giữa gateway và backend** chỉ xác thực quan hệ gateway–backend, không tự chứng minh end-user client có certificate-bound token hợp lệ.

Các service mesh có thể có `X-Forwarded-Client-Cert` hoặc metadata tương tự: cần hiểu **hop nào tạo, hop nào xóa và ai được tin**, không lấy tên header làm quyền.

## 12. BFF, cookie và refresh token qua proxy

Với **Backend for Frontend (BFF)**, trình duyệt thường không nhận OAuth access/refresh token. Nó chỉ gửi **session cookie** tới BFF; BFF giữ OAuth credential phía server và gọi API.

~~~http
GET /dashboard/orders HTTP/1.1
Host: app.example.com
Cookie: __Host-app-session=<opaque-session-id>
~~~

~~~http
Set-Cookie: __Host-app-session=<random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Proxy cần tôn trọng cookie flags, public scheme và route; **không bỏ `Secure` chỉ vì proxy → backend dùng HTTP nội bộ**.

**`HttpOnly` không tự chống CSRF**: browser vẫn gửi cookie trong request phù hợp. Cần `SameSite` đúng policy, CSRF token/Origin checks cho thao tác thay đổi dữ liệu, session rotation/fixation protection và object authorization.

**Refresh token thuộc token endpoint của AS**, không thuộc business API. BFF hoặc OAuth client phải bảo vệ refresh token và luồng rotation/revocation riêng; proxy cần định tuyến `/oauth2/token`, `/userinfo` và business endpoints đúng trust boundaries.

## 13. Caching, redirect và logging ở các hop

### 13.1. Không shared-cache response riêng tư

Nếu CDN cache `GET /orders` của user A rồi trả lại cho user B, hệ thống đã rò dữ liệu mặc dù cả hai token đều hợp lệ. Với dữ liệu cá nhân/nhạy cảm:

~~~http
HTTP/1.1 200 OK
Cache-Control: private, no-store
Content-Type: application/json
~~~

`private` ngăn shared cache lưu response; `no-store` yêu cầu không lưu. Cần **kiểm tra cấu hình CDN/proxy thực tế**; không mặc định Authorization header luôn được mọi custom cache xử lý đúng. Nếu bắt buộc cache, cache keys và policy phải ràng buộc user/tenant/resource, có đánh giá bảo mật riêng.

### 13.2. Redirect và Bearer token

Proxy có thể trả redirect từ `api.example.com` sang host khác. HTTP client có cách xử lý `Authorization` khác nhau khi redirect; một số loại bỏ khi cross-origin, client tự viết có thể tiếp tục gửi.

- Tránh redirect không cần thiết trên route mang credential.
- Không chuyển `Authorization` sang origin không tin cậy; cấu hình client kiểm soát redirect.
- Không xây `Location` dựa trên `Host` hoặc `X-Forwarded-Host` chưa kiểm soát.
- Với request ghi dữ liệu, hiểu semantics `301/302/307/308` và áp idempotency khi retry.

### 13.3. Redact log, tracing và APM

**Không ghi nguyên** `Authorization`, `Cookie`, `Set-Cookie`, `DPoP`, refresh token, authorization code hoặc client secret vào access/error logs, tracing spans, WAF samples và exception reports.

Event vận hành an toàn hơn:

~~~json
{
  "request_id": "req-18ac",
  "route": "/api/orders",
  "status": 401,
  "auth_error": "invalid_token",
  "issuer_alias": "auth-primary",
  "authorization_present": true,
  "authorization_header_bytes": 1640,
  "proxy_hop": "ingress"
}
~~~

Các giá trị chỉ để minh họa. Nếu cần correlate cùng token, dùng **HMAC fingerprint với audit key riêng được bảo vệ** hoặc identifier theo chính sách, không log token thô hoặc vài ký tự đầu của token. Cấu hình redaction **ở mọi hop**, kể cả CDN/WAF/ingress.

## 14. Kích thước header và các lỗi transport

JWT chứa quá nhiều `groups`/`roles` có thể dài hàng KiB. Tổng `Authorization`, cookies và trace headers có thể vượt giới hạn của một hop **trước khi đến Java API**.

| Phản hồi/tín hiệu | Ý nghĩa cần phân biệt |
| --- | --- |
| `431 Request Header Fields Too Large` | Một header hoặc tổng headers vượt ngưỡng proxy/server |
| `400 Bad Request` | Có thể là cú pháp/header size, tùy triển khai |
| `414 URI Too Long` | URL quá dài, có thể vì nhúng token vào query |
| `401 Unauthorized` | Credential thiếu, sai hoặc bị từ chối |
| `403 Forbidden` | Credential hợp lệ về mặt authentication nhưng không có quyền |
| `502/503` | Lỗi upstream, TLS, routing hoặc availability |

**Không có giới hạn header chung cho mọi thiết bị.** HTTP/2/3 có nén headers (HPACK/QPACK) nhưng vẫn có giới hạn danh sách field sau giải nén. Kiểm tra **per-header và aggregate** qua từng hop. Ưu tiên giảm claims dư thừa, token ngắn và thiết kế BFF/opaque phù hợp trước khi tăng giới hạn proxy quá rộng.

## 15. Khi gateway và backend bất đồng validation

Gateway có thể chấp nhận chữ ký nhưng API trả `401` vì sai `aud`, hoặc API trả `403` do thiếu scope/ownership. Không vội kết luận proxy “làm hỏng token”.

| Gateway | Backend | Nguyên nhân khả dĩ |
| --- | --- | --- |
| Pass-through | `401` | Token thiếu/sai/expired hoặc header bị mất |
| Chấp nhận JWT signature | `401` | Gateway thiếu issuer/audience/type validation |
| Xác minh token | `403` | Business scope/tenant/ownership chưa đạt |
| DPoP verified ở một hop | `401` hop khác | Public URL khác URL rewrite nội bộ |
| Phát identity header | Backend không chấp nhận | Thiếu trusted-source assertion hoặc mTLS |
| Proxy trả `431` | Không có application log | Header bị chặn trước API |

Trình tự điều tra:

1. Gắn request ID qua các hop và xác định **hop đầu tiên** trả lỗi.
2. Xem loại lỗi: transport vs authentication vs authorization.
3. Ghi **có/không `Authorization` và độ dài**; không ghi token.
4. Đối chiếu issuer alias, audience match, algorithm/signature status, thời hạn, token type dưới dạng metadata đã lọc.
5. Kiểm tra sanitize forwarded/identity headers và đường bypass proxy.
6. Kiểm tra scope, tenant, ownership ở backend; test lại qua **đúng route thực**.

Đừng sửa lỗi bằng cách tắt JWT decoder, bỏ `aud`, tắt CSRF bừa bãi hoặc tin `X-User-Id`.

## 16. Tình huống thực tế

**Tình huống A — Client có token, backend luôn trả 401.** Proxy cấu hình `Authorization` thành chuỗi rỗng. API không nhận Bearer.

**Phân tích:** lỗi vận chuyển credential, không phải RSA key. Kiểm tra từng hop và header-presence không lộ token; khôi phục forwarding theo contract.

**Tình huống B — JWT hợp lệ nhưng API B trả 401.** Access token có `aud=orders-api`, request được gateway chuyển tới `payments-api`.

**Phân tích:** Payments API phải từ chối sai audience. Gateway routing hoặc AS scope/resource configuration cần sửa; không bỏ kiểm tra `aud`.

**Tình huống C — Reset-password URL trỏ attacker domain.** Proxy/backend tin `X-Forwarded-Host` do client gửi để sinh links.

**Phân tích:** Host-header injection. Cố định canonical origin, strip spoofed forwarding và kiểm thử redirect/URL generation.

**Tình huống D — DPoP proof thất bại dù khóa đúng.** Gateway rewrite `/orders/123` thành `/internal/orders/123`, API so `htu` với URL nội bộ.

**Phân tích:** cần external URI đáng tin theo RFC 9449; không giải quyết bằng cách bỏ `htu` validation.

**Tình huống E — Admin của tenant Acme đọc dữ liệu Globex.** Gateway verify access token nhưng backend tin `X-Tenant-Id` và tìm order chỉ theo ID.

**Phân tích:** thiếu object authorization và header trust. Backend phải so tenant token/assertion với tenant sở hữu record.

**Tình huống F — JWT hiện trong WAF logs.** WAF sample lưu đầy đủ request headers khi chặn request.

**Phân tích:** WAF trở thành nguồn lộ credential; cần redaction, quyền truy cập logs, retention, thu hồi token/grant bị ảnh hưởng và điều tra replay.

## 17. Bộ kiểm thử tích hợp

| Test case | Kỳ vọng |
| --- | --- |
| Bearer token hợp lệ đi qua mọi hop | API nhận đúng credential và áp quyền |
| Một proxy chủ động bỏ `Authorization` | `401`, xác định đúng hop |
| JWT sai signature/algorithm/issuer/audience/exp | API từ chối |
| ID token gửi thay access token | API từ chối sai type/audience |
| Opaque token `active=false` | Từ chối qua introspection |
| Refresh token đưa vào business API | Không được coi là access token |
| Caller giả `X-User-Id: admin` | Proxy strip, backend không cấp quyền |
| Caller giả `X-Forwarded-Host` | Không thay public URL/redirect |
| Caller giả `X-Forwarded-For` | Không bypass policy nhờ IP giả |
| Gọi backend qua port trực tiếp | Bị chặn hoặc vẫn cần authentication thật |
| Chứng chỉ upstream sai/không được tin | Proxy không bỏ TLS verification |
| CDN có cache, hai user gọi cùng path | Không lộ response riêng tư |
| Headers lớn hơn giới hạn hop | Trả lỗi transport phù hợp, không log token |
| Browser gửi CORS `OPTIONS` không có token | Xử lý preflight đúng |
| DPoP proof public URI, proxy rewrite path | So `htu` bằng URL external tin cậy |
| DPoP-bound access token gửi như Bearer thuần | Từ chối sender binding |
| mTLS-bound token với header cert giả | Không được chấp nhận |
| Token đúng scope nhưng khác tenant | API từ chối theo resource policy |
| Redirect sang host ngoài allowlist | Không gửi Bearer sang host đó |
| BFF session cookie qua TLS termination | `Secure`, CSRF, session hoạt động đúng |
| Log/tracing ở mọi hop | Không có raw credential |

Nên có **integration test qua proxy thật hoặc cấu hình tương đương production**. Mock `JwtDecoder` trong Java unit test không chứng minh ingress đã forward token, sanitize headers hoặc xác minh TLS upstream.

## 18. Các sai lầm cần tránh

| Ngộ nhận | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| “HTTPS ngoài Internet là đủ.” | HTTP nội bộ có thể lộ Bearer token | Bảo vệ mọi hop theo threat model |
| “Proxy gọi được backend là user hợp lệ.” | Kết nối không chứng minh user/role | Validate token/assertion và resource policy |
| “`X-Forwarded-For` chắc chắn là IP user.” | Có thể bị spoof hoặc parse sai | Trusted-hop policy và strip headers |
| “`X-User-Id` đến từ proxy thì tin.” | Caller có thể tự gửi nếu không strip/khóa bypass | Xác minh nguồn/assertion |
| “Gateway verify chữ ký thì khỏi kiểm tra `aud`.” | Token API khác vẫn ký đúng | Ràng buộc issuer/audience/type |
| “Cookie `HttpOnly` làm POST an toàn.” | Browser vẫn tự gửi cookie | CSRF và authorization |
| “DPoP chỉ cần verify signature.” | Proof còn phải khớp method/URL/token/nonce | Kiểm tra `htu`, `htm`, `ath`, `jti`, binding |
| “Bật forwarded header support là tự an toàn.” | Framework không tự kiểm chứng mọi proxy | Chỉ tin hop được kiểm soát |
| “JWT hợp lệ có thể shared-cache mọi response.” | Rò dữ liệu giữa user/tenant | Tách cache hoặc `private/no-store` |
| “Tăng header limit giải quyết mọi lỗi 401.” | 401 có thể là sai token/credential mất | Phân loại lỗi và tìm hop |

## 19. Checklist production

1. **Vẽ đường đi:** client → CDN/WAF → proxy → gateway → API; ghi rõ trust, TLS và trách nhiệm từng hop.
2. **Phân loại credential:** access token/ID token/refresh token/session cookie/DPoP proof/mTLS cert có mục đích khác nhau.
3. **Bảo vệ TLS:** xác minh upstream CA/SNI/hostname, network segmentation và quyền vận hành proxy.
4. **Forward đúng `Authorization`:** không bỏ/sửa, không chuyển sang URL; nếu gateway kết thúc authentication, phát assertion đáng tin.
5. **Sanitize forwarded/identity headers:** `Forwarded`, `X-Forwarded-*`, `X-User-Id`, `X-Roles`, cert headers; chặn bypass.
6. **Cố định public origin và OAuth redirects:** tránh Host injection và callback poisoning.
7. **Giữ token validation:** algorithm/key, `iss`, `aud`, `exp`, `nbf`, type/profile hoặc opaque `active`.
8. **Giữ resource authorization:** scope, tenant, membership, ownership, business state và revocation policy.
9. **DPoP/mTLS đúng binding:** external URI/certificate được lấy từ nguồn tin cậy.
10. **Bảo vệ cookie và CSRF** với BFF/session; không chuyển refresh token tới API tài nguyên.
11. **Redact logs và caching:** không lưu credential, không shared-cache dữ liệu cá nhân; quản lý trace/metrics an toàn.
12. **Có giới hạn vận hành:** header size, timeouts, rate limiting, JWKS/introspection cache.
13. **Test đúng production route:** CORS, header loss/spoof, 401/403/431, TLS upstream, redirect và DPoP rewrite.
14. **Có quy trình ứng phó leak:** revoke token/grant/session phù hợp, điều tra hệ thống logs và giảm replay.

## 20. Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): vận chuyển Bearer token, lỗi và nguy cơ credential leak.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP fields, authentication, redirects và status codes.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): cache response và `Cache-Control`.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): `Forwarded`, `for`, `proto`, `host`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): validation access token JWT.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh opaque token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof JWT, `htu`/`htm`, replay và sender binding.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound access tokens.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): giảm rủi ro OAuth và bảo vệ token.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, issuer và claims.
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/reference/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server): forwarded headers khi triển khai sau proxy.
- [OWASP HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): thực hành bảo mật HTTP headers.

**Ghi nhớ:** **Token qua reverse proxy vẫn là credential cần được bảo vệ và xác minh tại ranh giới tin cậy.** Hãy giữ `Authorization` đúng hợp đồng, bảo vệ mọi hop bằng TLS/kênh phù hợp, chỉ tin forwarded/identity headers từ proxy được kiểm soát, chống lộ token qua log/cache/redirect và kiểm tra DPoP/mTLS đúng ngữ cảnh. Dù gateway hay API làm nơi xác thực, quyết định truy cập cuối cùng phải tuân **issuer, audience, thời hạn, scope, tenant và quyền trên tài nguyên**.
