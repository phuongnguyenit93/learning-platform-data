# Discovery sau reverse proxy, custom domain và môi trường đa issuer

## 1. Vì sao Discovery dễ sai khi triển khai thực tế?

Trong chương **Metadata và Discovery** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này giải quyết một bài toán production: **Authorization Server chạy bên trong Kubernetes, reverse proxy hoặc load balancer, nhưng OAuth 2.0/OIDC clients phải nhìn thấy đúng issuer và endpoint công khai; khi nhiều tenant hoặc custom domain cùng tồn tại, mỗi issuer phải được cách ly rõ ràng**.

Nội dung phục vụ mục tiêu của module: **học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot**.

Ví dụ: Spring Boot lắng nghe nội bộ tại `http://auth-service:9000`, ingress phục vụ public URL `https://login.example.com`. Nếu metadata trả:

~~~json
{
  "issuer": "http://auth-service:9000",
  "token_endpoint": "http://auth-service:9000/oauth2/token",
  "jwks_uri": "http://auth-service:9000/oauth2/jwks"
}
~~~

thì phía client không truy cập được endpoint, issuer không khớp cấu hình an toàn và việc xác minh token có thể thất bại. Sai lầm còn nghiêm trọng hơn nếu server lấy tùy ý giá trị `Host` hoặc `X-Forwarded-Host` để sinh issuer: kẻ tấn công có thể khiến metadata/trust boundary mang tên miền không được kiểm soát.

**Kết quả cần đạt:** hiểu đúng các discovery standard, cấu hình public issuer và reverse proxy, lựa chọn custom domain/multi issuer, thiết kế registry theo issuer, xác minh consistency của metadata/JWT/JWKS, kiểm thử cả trường hợp hostname bị giả mạo và vận hành thay đổi tên miền an toàn.

## 2. Các chuẩn Discovery và sự khác biệt về URL

Hai cơ chế gần nhau nhưng không hoàn toàn đồng nhất:

1. **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** công bố khả năng và các endpoint của OAuth Authorization Server.
2. **OpenID Connect Discovery 1.0 — OpenID Provider Configuration:** công bố metadata của OpenID Provider, bao gồm các endpoint OIDC và khả năng ID Token.

### 2.1. Khi issuer không có path

Giả sử issuer chính thức là:

~~~text
https://login.example.com
~~~

Các URL thường dùng:

| Metadata | URL |
| --- | --- |
| OAuth 2.0 Authorization Server Metadata | `https://login.example.com/.well-known/oauth-authorization-server` |
| OIDC Provider Configuration | `https://login.example.com/.well-known/openid-configuration` |

Trong Spring Authorization Server, endpoint OAuth metadata được cung cấp bởi cơ chế Authorization Server Metadata; OIDC Provider Configuration cần **bật OpenID Connect support**. Không coi việc có `/oauth2/jwks` hoặc `/oauth2/token` là bằng chứng endpoint OIDC discovery đã được bật.

### 2.2. Khi issuer có path

Ví dụ:

~~~text
https://identity.example.com/tenant/acme
~~~

**Cần phân biệt quy tắc xây dựng well-known URL của hai chuẩn:**

| Chuẩn | URL theo quy tắc tương ứng |
| --- | --- |
| RFC 8414 OAuth metadata | `https://identity.example.com/.well-known/oauth-authorization-server/tenant/acme` |
| OIDC Discovery 1.0 | `https://identity.example.com/tenant/acme/.well-known/openid-configuration` |

RFC 8414 chèn well-known path giữa authority và issuer path; OIDC Discovery dùng quy tắc ghép `/.well-known/openid-configuration` sau issuer đã bỏ dấu slash cuối nếu có. Vì các chuẩn và thư viện có quy tắc/khả năng tương thích khác nhau, **không tự suy ra tất cả clients sẽ thử cùng một URL**, đặc biệt với issuer có path. Phải kiểm tra discovery thực tế ở bản Spring Authorization Server và client library đang triển khai.

### 2.3. Metadata URL không nhất thiết trùng issuer

**Issuer** là định danh tin cậy, không phải tên của file metadata. Client truy cập metadata URL để tìm JSON, nhưng phải kiểm tra field `issuer` trong JSON **khớp chính xác issuer mà client dự định tin**. Một website có thể trả JSON hợp lệ tại một URL, nhưng điều đó không đủ để client tự động tin issuer bất kỳ được JSON công bố.

Một redirect từ old discovery URL sang new discovery URL không có nghĩa token đã ký bởi old issuer trở thành token của new issuer. Đây là thay đổi định danh và trust policy cần thiết kế riêng.

## 3. Nội dung metadata cần nhất quán

Ví dụ **OAuth 2.0 Authorization Server Metadata** cho issuer public:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/oauth2/jwks",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "code_challenge_methods_supported": ["S256"],
  "revocation_endpoint": "https://login.example.com/oauth2/revoke",
  "introspection_endpoint": "https://login.example.com/oauth2/introspect"
}
~~~

**Đây là mẫu minh họa**, không cam kết mọi trường/grant/client authentication method đều được framework công bố với giá trị giống mẫu. Chỉ quảng bá các tính năng mà Authorization Server thực sự hỗ trợ và đã cấu hình. Endpoint URL thực tế cũng có thể được tùy chỉnh qua `AuthorizationServerSettings`.

Các field quan trọng:

| Field | Client dùng để làm gì? | Rủi ro khi sai |
| --- | --- | --- |
| `issuer` | Thiết lập danh tính Authorization Server | Nhầm trust domain, token có `iss` không khớp |
| `authorization_endpoint` | Chuyển browser đến flow cấp quyền | Redirect vào host nội bộ/sai tenant |
| `token_endpoint` | Đổi code, refresh hoặc các grant khác | Client gửi credential/code đến host sai |
| `jwks_uri` | Lấy public keys xác minh JWT | Chữ ký không xác minh được hoặc dùng key sai tenant |
| `revocation_endpoint` | Thu hồi token | Logout không có hiệu lực hoặc gửi token nhầm domain |
| `introspection_endpoint` | Kiểm tra trạng thái token | Resource Server nhận sai kết quả active/trust |
| `grant_types_supported` | Biết các grant server công bố | Client suy đoán dùng grant chưa được bật |
| `token_endpoint_auth_methods_supported` | Biết phương pháp client authentication | Client thử secret/JWT/mTLS không tương thích |
| `code_challenge_methods_supported` | Biết PKCE methods | Client dùng method không được hỗ trợ |

### 3.1. OIDC Provider Configuration

Khi bật OpenID Connect, Provider Configuration có thêm các field đặc trưng như:

- `userinfo_endpoint`: endpoint lấy user claims theo quyền được cấp.
- `subject_types_supported`: subject types được hỗ trợ.
- `id_token_signing_alg_values_supported`: thuật toán ký ID Token.
- `end_session_endpoint` khi server hỗ trợ và công bố logout tương ứng.
- `scopes_supported` có thể gồm `openid` và các scopes OIDC được bật.

Một số field cùng tên như `issuer`, `jwks_uri`, `authorization_endpoint` và `token_endpoint` phải nhất quán giữa metadata OAuth/OIDC và với chính token được phát hành.

### 3.2. Discovery không tự cấp quyền

Metadata thường có thể truy cập công khai, nhưng việc công bố một grant hoặc scope **không có nghĩa mọi RegisteredClient được dùng grant/scope đó**. Quyền thực tế vẫn được xét bởi `RegisteredClient`, client authentication, authorization consent và policy nghiệp vụ.

Tương tự, metadata có `jwks_uri` không tự làm JWKSource trở thành đáng tin nếu client/Resource Server không kiểm tra issuer, signature algorithm và key suitability.

## 4. Ranh giới giữa public origin và địa chỉ nội bộ

Hệ thống triển khai thực tế thường có nhiều địa chỉ:

~~~mermaid
flowchart LR
    C["Browser / OAuth Client"] -->|"HTTPS https://login.example.com"| LB["Trusted Ingress / Reverse Proxy"]
    LB -->|"HTTP hoặc TLS nội bộ<br/>auth-service:9000"| AS["Spring Boot Authorization Server"]
    AS -->|"DB / Key Store"| S["Authorization Store + JWK source"]
    LB -.->|"Forwarded/X-Forwarded-* đã được làm sạch"| AS
~~~

| Thành phần | Giá trị ví dụ | Có được dùng làm issuer public? |
| --- | --- | --- |
| External scheme | `https` | Có |
| External host | `login.example.com` | Có, nếu được phê duyệt |
| External port | `443` (thường ẩn) | Có, khi issuer cần port đặc biệt |
| Internal service | `auth-service` | Không |
| Internal port | `9000` | Không |
| Pod IP | `10.10.4.12` | Không |
| Namespace/cluster DNS | `auth-service.security.svc` | Không |

**Issuer không nên phụ thuộc tên Pod/Service hay header mà caller bên ngoài điều khiển.** Với một public issuer ổn định, cấu hình tường minh giúp tránh metadata thay đổi khi restart, scale hoặc thay ingress.

## 5. Cấu hình một issuer cố định trong Spring Authorization Server

Với public domain duy nhất, cấu hình `AuthorizationServerSettings` tường minh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
public class PublicIssuerConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://login.example.com")
                .build();
    }
}
~~~

Khi issuer được cấu hình như trên, mục tiêu là bảo đảm metadata và claim `iss` trong token đều là `https://login.example.com`, không bị thay bởi `http://auth-service:9000`.

Spring Authorization Server có thể suy ra issuer từ request khi không cấu hình cố định, theo ngữ cảnh phiên bản. Điều đó hữu ích trong một số tình huống hoặc multi issuer, nhưng **không nên để host/proxy không được kiểm soát quyết định trust domain**. Với single issuer production, sử dụng issuer cố định và kiểm tra đầu ra là giải pháp dễ kiểm toán hơn.

### 5.1. Bật OIDC discovery khi cần

Ví dụ cấu hình phần Authorization Server filter chain theo Spring Security/Spring Authorization Server 1.x có API tương ứng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()));

    // Thêm authentication/entry point và các bean cần thiết trong ứng dụng thật.
    return http.build();
}
~~~

Đây là **đoạn cấu hình tối thiểu có chủ đích**, không phải toàn bộ ứng dụng Authorization Server sẵn sàng production. Ứng dụng còn cần đăng ký `RegisteredClientRepository`, `OAuth2AuthorizationService`, signing keys/JWKSource, login chain và cấu hình user authentication. `oidc(Customizer.withDefaults())` là điểm bật hỗ trợ OIDC; không bật OIDC chỉ để tạo metadata OAuth2 nếu ứng dụng không cung cấp OIDC.

### 5.2. Issuer và endpoint tùy chỉnh phải cùng domain

Nếu cần đổi Token Endpoint hoặc JWK Set Endpoint, sử dụng `AuthorizationServerSettings` theo nhu cầu:

~~~java
AuthorizationServerSettings settings =
        AuthorizationServerSettings.builder()
                .issuer("https://login.example.com")
                .authorizationEndpoint("/oauth2/authorize")
                .tokenEndpoint("/oauth2/token")
                .jwkSetEndpoint("/oauth2/jwks")
                .tokenRevocationEndpoint("/oauth2/revoke")
                .tokenIntrospectionEndpoint("/oauth2/introspect")
                .build();
~~~

Các path trong ví dụ là minh họa theo defaults phổ biến. Khi đổi path, hãy kiểm tra sự tương thích với ingress rewrite, discovery, HTTP security matcher, clients và Resource Servers. Không thay URL chỉ trong metadata JSON mà để filter chain tiếp tục lắng nghe đường dẫn cũ.

## 6. Reverse proxy và Forwarded headers

Proxy có thể nhận HTTPS ở ngoài nhưng kết nối HTTP tới Spring Boot bên trong. Nếu không xử lý forwarded headers, ứng dụng có thể cho rằng scheme là `http`, host là `auth-service` và port là `9000`.

Các header thường gặp:

~~~http
Forwarded: proto=https;host=login.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: login.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /auth
~~~

`Forwarded` là header chuẩn RFC 7239; `X-Forwarded-*` là các header phổ biến do proxy cung cấp. Giá trị chỉ đáng tin nếu được **trusted ingress xác minh, xóa giá trị do client tự gửi, rồi tạo lại**. Header tự nó không có chữ ký và không chứng minh nguồn tin cậy.

### 6.1. Spring Boot forwarded-header strategy

Ví dụ khi ứng dụng đặt sau proxy tin cậy và cần Spring xử lý scheme/host/port:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

`framework` thường sử dụng cơ chế xử lý forwarded headers của Spring, ví dụ `ForwardedHeaderFilter` trong ứng dụng Servlet. Tùy môi trường có thể dùng chiến lược `native` để container xử lý forwarded headers. **Chiến lược nào đúng phải được kiểm tra với embedded server, ingress và Spring Boot version thực tế.**

| Chiến lược | Ý nghĩa tổng quát | Điều cần kiểm thử |
| --- | --- | --- |
| `none` | Không dùng forwarded headers cho request origin | Ứng dụng có tự tạo HTTP URL nội bộ không? |
| `native` | Dùng tính năng container native khi khả dụng | Proxy trust, host, scheme và path prefix được xử lý đúng không? |
| `framework` | Dùng cơ chế Spring xử lý Forwarded/X-Forwarded-* | Header được làm sạch chưa, prefix được áp dụng nhất quán chưa? |

Không cấu hình cả proxy và application theo cách khiến scheme/host/prefix bị **áp dụng hai lần**. Cũng không dùng ForwardedHeaderFilter để làm “biện pháp bảo mật” cho header do bên ngoài tự gửi. Nó là cơ chế diễn giải request, **không phải bộ xác thực proxy**.

### 6.2. Quy tắc tại ingress

Ingress/reverse proxy nên:

1. Chỉ nhận các hostname/public routes nằm trong allowlist và có TLS certificate phù hợp.
2. **Xóa** Forwarded/X-Forwarded-* (hoặc metadata tương đương) do Internet client gửi.
3. Tạo hoặc ghi đè các header đó từ kết nối TLS/public request đã kiểm tra.
4. Chỉ cho backend nhận traffic từ proxy được phép; chặn truy cập trực tiếp bỏ qua ingress.
5. Bảo vệ kênh proxy → backend phù hợp threat model, thường dùng network policy và TLS/mTLS nội bộ.
6. Đồng bộ quy tắc path rewrite, redirect và forwarded prefix.
7. Không chấp nhận host ngẫu nhiên rồi để backend tạo issuer cho host đó.

**Không có cấu hình `server.forward-headers-strategy` nào tự thực hiện đầy đủ bảy bước này.** Những bước này thuộc trách nhiệm của hạ tầng ingress và security policy.

### 6.3. Cẩn thận với Host header injection

Ví dụ request độc hại:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: attacker.example
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

Nếu server phản ánh `attacker.example` vào `issuer`, `authorization_endpoint` hoặc `jwks_uri`, client có thể bị chuyển tới endpoint không đáng tin. Hệ thống phải từ chối host không nằm trong allowlist ở ingress/app trước khi tạo metadata. Với single issuer, issuer cố định hạn chế đáng kể rủi ro này nhưng vẫn cần host routing an toàn.

## 7. Context path, prefix và rewrite

Có hai kiến trúc phổ biến cần phân biệt:

### 7.1. External path và internal path giống nhau

~~~text
Public:   https://login.example.com/oauth2/token
Internal: http://auth-service:9000/oauth2/token
~~~

Đây thường là mô hình đơn giản nhất. Ingress chỉ thay scheme/host/port, không cần đổi path; `AuthorizationServerSettings` có thể giữ path mặc định.

### 7.2. External prefix khác internal path

~~~text
Public:   https://id.example.com/auth/oauth2/token
Internal: http://auth-service:9000/oauth2/token
~~~

Trong mô hình này, proxy strip `/auth` khi chuyển tiếp, đồng thời metadata phải công bố URL có `/auth` đúng theo public contract. `X-Forwarded-Prefix` có thể hỗ trợ nhưng hiệu quả thực tế phụ thuộc filter/container/route và phiên bản.

Một sự cố điển hình:

- Browser gọi `https://id.example.com/auth/oauth2/authorize`.
- Metadata lại báo `https://id.example.com/oauth2/token`.
- Ingress chỉ route `/auth/**` đến Authorization Server.
- Authorization Code Flow thất bại ở bước đổi code.

**Không sửa bằng cách cho phép public mọi path không kiểm soát.** Hãy quyết định rõ path ownership, proxy rewrite, base URL và security matcher; sau đó test đúng URL public.

### 7.3. Issuer path khác proxy prefix

Issuer có path, ví dụ `https://id.example.com/tenant/acme`, là **thành phần danh tính** theo chuẩn OAuth/OIDC. Proxy prefix `/auth` là **chi tiết routing**. Chúng có thể cùng xuất hiện nhưng không nên tự đồng nhất.

| Yếu tố | Ví dụ | Vai trò |
| --- | --- | --- |
| Issuer | `https://id.example.com/tenant/acme` | Định danh Authorization Server/tenant |
| External route prefix | `/auth` | Vị trí ứng dụng qua ingress |
| Internal servlet context path | `/` | Mount point nội bộ |
| Token Endpoint | `https://id.example.com/auth/tenant/acme/oauth2/token` nếu được thiết kế và hỗ trợ | URL client thực sự gọi |

Nếu một deployment không thể công bố issuer/metadata/endpoint nhất quán khi dùng prefix, cân nhắc **dùng hostname riêng** thay vì rewrite phức tạp.

## 8. Custom domain: alias hay issuer mới?

Giả sử một tenant muốn dùng:

~~~text
https://login.customer.example
~~~

thay vì domain chung:

~~~text
https://login.saas.example
~~~

Có hai lựa chọn kiến trúc rất khác nhau.

### 8.1. Custom domain chỉ là điểm vào, issuer vẫn cố định

Client có thể truy cập domain tùy biến nhưng token vẫn có `iss=https://login.saas.example` và discovery trả issuer tương ứng. Đây có thể là **alias/routing** hợp lệ nếu client discovery và trust contract được thiết kế rõ, nhưng dễ gây hiểu nhầm nếu client tự coi custom domain là issuer.

Không đưa hostname alias vào field `issuer` chỉ vì request đến alias. Cần một **canonical issuer** và hướng dẫn client luôn dùng issuer đó để xác minh token.

### 8.2. Custom domain trở thành issuer thực sự

Khi yêu cầu rằng `iss=https://login.customer.example`, đó là **một issuer riêng**. Cần:

- TLS certificate hợp lệ cho custom domain (bao gồm kế hoạch renew/revoke).
- DNS/CNAME, domain ownership verification và allowlist host.
- Metadata trả đúng issuer trên domain đó.
- Các endpoint và `jwks_uri` phù hợp domain/tenant.
- Keys và authorization data gắn với issuer/tenant theo chính sách.
- Resource Server/clients xác minh exact issuer tương ứng.
- Cơ chế tránh tenant A mượn domain hoặc metadata của tenant B.

**Custom domain không chỉ là vấn đề CNAME.** Đó có thể là thay đổi security identity ảnh hưởng token validation, logout, redirect URIs và OAuth client registration.

### 8.3. Đừng tự động tin domain vừa được nhập trong trang quản trị

Khi tenant đăng ký custom domain, cần xác thực quyền sở hữu domain, cấu hình chứng thư, allowlist, chính sách takeover khi DNS đổi và quy trình chuyển ownership. **Không phát token dưới issuer chưa được phê duyệt**, chỉ vì request HTTP mang tên miền đó.

## 9. Mô hình đa issuer: tên miền riêng hoặc path tenant

Một hệ thống đa tenant có thể dùng các issuer:

~~~text
https://auth.example.com/tenant/acme
https://auth.example.com/tenant/zen
~~~

hoặc:

~~~text
https://login.acme.example.com
https://login.zen.example.com
~~~

Mỗi issuer là một **trust domain**. Nó cần mapping tường minh tới tenant, registered clients, authorization records và thông tin signing keys theo kiến trúc.

### 9.1. So sánh hai mô hình

| Mô hình | Ưu điểm | Rủi ro/đánh đổi |
| --- | --- | --- |
| Single issuer cho tất cả tenants | Đơn giản cho clients/JWKS, vận hành tập trung | Phân tách tenant chủ yếu bằng claim, DB và policy; blast radius rộng |
| Nhiều issuer dưới cùng host bằng path | Giữ một domain, phân biệt issuer theo path | Quy tắc discovery path khác chuẩn, routing và data lookup phức tạp |
| Nhiều issuer qua subdomain/custom domain | Ranh giới hostname rõ, branding tốt | TLS/DNS, onboarding, host allowlist và certificate lifecycle nhiều hơn |
| Mỗi issuer một deployment | Cách ly keys, data, cấu hình mạnh | Chi phí vận hành và deployment cao hơn |

Không có phương án mặc định tốt nhất cho mọi hệ thống; quan trọng là ranh giới issuer được thể hiện **nhất quán từ metadata đến token và Resource Server**.

### 9.2. Spring Authorization Server và multiple issuers

Spring Authorization Server các phiên bản có hỗ trợ multi issuer cho phép bật tính năng nhiều issuer trên cùng host, ví dụ với `AuthorizationServerSettings`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class MultiIssuerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .multipleIssuersAllowed(true)
                .build();
    }
}
~~~

**Điều kiện:** chỉ sử dụng API nếu phiên bản Spring Authorization Server đang chạy có `multipleIssuersAllowed` và mô hình request routing tương thích. Khi bật multi issuer, cần cung cấp các component **tenant-aware**; chỉ bật flag mà dùng chung mọi repository/keys không thể tự tạo isolation.

Đừng vừa cấu hình issuer cố định như `https://login.example.com` cho mọi request vừa kỳ vọng metadata tự trở thành `https://login.example.com/tenant/acme`. Cần lựa chọn rõ static single issuer hoặc dynamic multi issuer và kiểm thử contract.

### 9.3. Cách ly thành phần theo issuer

Các thành phần thường cần thiết kế theo issuer:

- `RegisteredClientRepository`: client registration của từng tenant.
- `OAuth2AuthorizationService`: authorization và token state thuộc tenant tương ứng.
- `OAuth2AuthorizationConsentService`: consent của user–client đúng tenant.
- `JWKSource<SecurityContext>` và signing key policy: keys riêng theo issuer khi muốn cách ly cryptographic.
- `JwtDecoder` và validation policy liên quan, nhất là khi hỗ trợ OIDC/UserInfo/introspection.
- User authentication, identities, login branding, session/tenant mapping và audit.

Không mặc định một client_id giống nhau ở hai tenant là cùng một client. Dữ liệu phải được namespace theo issuer hoặc tenant ID. Nếu keys được chia sẻ vì lý do vận hành, sự chia sẻ đó phải có threat model, key rotation và blast-radius analysis riêng.

## 10. Issuer registry: allowlist thay vì phản chiếu Host

Một thiết kế an toàn gồm hai bước:

1. **Proxy xác định public host/path hợp lệ**; app không nhận host tùy ý.
2. **Issuer registry bên server** ánh xạ exact issuer đã phê duyệt tới tenant configuration.

Ví dụ Java 17 cho registry thuần, độc lập HTTP:

~~~java
import java.util.Map;
import java.util.Objects;

public final class ApprovedIssuerRegistry<T> {

    private final Map<String, T> byIssuer;

    public ApprovedIssuerRegistry(Map<String, T> registeredIssuers) {
        this.byIssuer = Map.copyOf(registeredIssuers);
    }

    public T requireIssuer(String issuer) {
        Objects.requireNonNull(issuer, "issuer");
        T component = byIssuer.get(issuer);
        if (component == null) {
            throw new IllegalArgumentException("Unapproved issuer");
        }
        return component;
    }
}
~~~

Cách dùng:

~~~java
ApprovedIssuerRegistry<TenantComponents> registry =
        new ApprovedIssuerRegistry<>(Map.of(
                "https://auth.example.com/tenant/acme", acmeComponents,
                "https://auth.example.com/tenant/zen", zenComponents));

// Issuer phải được giải quyết từ request theo cấu hình tin cậy,
// rồi đối chiếu allowlist trước khi chọn tenant components.
TenantComponents components = registry.requireIssuer(resolvedIssuer);
~~~

`TenantComponents` là kiểu dữ liệu ứng dụng tự định nghĩa; `resolvedIssuer` phải đến từ một resolver đáng tin, không phải raw `Host` hoặc query parameter. Registry này chỉ minh họa nguyên tắc **exact issuer allowlist**, chưa phải một multi-tenant authorization server hoàn chỉnh.

### 10.1. Spring Authorization Server context

Khi request đang nằm trong SecurityFilterChain xử lý Authorization Server, context có thể cung cấp issuer cho các component:

~~~java
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;

AuthorizationServerContext serverContext =
        AuthorizationServerContextHolder.getContext();
String issuer = serverContext.getIssuer();

TenantComponents tenant =
        approvedIssuerRegistry.requireIssuer(issuer);
~~~

Đây là đoạn minh họa **bên trong một component/provider chạy trong request context**. Không gọi `AuthorizationServerContextHolder` từ thread nền hoặc code khởi động rồi giả định nó luôn có context. Cần xử lý context null, startup paths và bất kỳ tenant resolution nào ngoài request một cách tường minh.

### 10.2. Không chọn tenant chỉ từ token chưa xác minh

Trong introspection, token exchange hoặc Resource Server, không decode JWT rồi tin ngay `iss` của token để chọn bất kỳ JWKS URL nào được token đưa ra. Thay vào đó, chỉ chọn giữa các issuer **đã nằm trong registry được phê duyệt**, rồi xác minh signature, algorithm, audience, thời gian và trạng thái.

Một token do issuer Acme ký không được chấp nhận trong tenant Zen chỉ vì hai issuer cùng host, cùng key hoặc có claim `sub` giống nhau.

## 11. Routing metadata, OAuth endpoints và JWKS theo tenant

Một tenant không chỉ cần một JSON `issuer` khác. Clients phải có **đường đi hoàn chỉnh** đến Authorization Endpoint, Token Endpoint, JWKS, Introspection và Revocation của đúng issuer, và các route đó phải truy cập được qua public TLS domain.

Giả sử tổ chức chọn issuer có path:

~~~text
Tenant Acme issuer: https://auth.example.com/tenant/acme
Tenant Zen  issuer: https://auth.example.com/tenant/zen
~~~

**Thiết kế URL minh họa**:

| Thành phần | Acme | Zen |
| --- | --- | --- |
| Issuer | `https://auth.example.com/tenant/acme` | `https://auth.example.com/tenant/zen` |
| OAuth metadata RFC 8414 | `https://auth.example.com/.well-known/oauth-authorization-server/tenant/acme` | `https://auth.example.com/.well-known/oauth-authorization-server/tenant/zen` |
| OIDC metadata | `https://auth.example.com/tenant/acme/.well-known/openid-configuration` | `https://auth.example.com/tenant/zen/.well-known/openid-configuration` |
| Authorization Endpoint | `https://auth.example.com/tenant/acme/oauth2/authorize` | `https://auth.example.com/tenant/zen/oauth2/authorize` |
| Token Endpoint | `https://auth.example.com/tenant/acme/oauth2/token` | `https://auth.example.com/tenant/zen/oauth2/token` |
| JWK Set Endpoint | `https://auth.example.com/tenant/acme/oauth2/jwks` | `https://auth.example.com/tenant/zen/oauth2/jwks` |

**Quan trọng:** đây là **hợp đồng URL mục tiêu do kiến trúc tự chọn**, không phải lời khẳng định một bản Spring Authorization Server sẽ mặc định lắng nghe mọi path trong bảng. Đặc biệt quy tắc well-known, path-based multi issuer và proxy rewriting phải được xác minh với phiên bản/thành phần đang dùng. Nếu triển khai không thể duy trì các endpoint nhất quán, nên chọn route đơn giản hơn hoặc tách deployment.

### 11.1. Cần ánh xạ cùng issuer ở mọi endpoint

Một request tới `/tenant/acme/oauth2/token` không được rơi sang `RegisteredClientRepository` của Zen vì filter/repository dùng shared singleton không chọn tenant. Tương tự:

- Authorization Code cấp ở Acme phải được đổi tại Token Endpoint thuộc issuer Acme.
- `redirect_uri` của client phải được đăng ký đúng tenant.
- Authorization/consent của Acme không được lookup/ghi dưới tenant Zen.
- JWKS Acme không được âm thầm trả key của Zen nếu policy yêu cầu key isolation.
- Introspection/revocation phải kiểm tra client và token cùng trust domain.

### 11.2. Cách định tuyến an toàn

~~~mermaid
flowchart TD
    A["HTTPS request đến trusted ingress"] --> B{"Public host/path có trong allowlist?"}
    B -->|Không| X["404 / 400, không tạo issuer"]
    B -->|Có| C["Route đến Authorization Server"]
    C --> D["Resolver xác định exact issuer"]
    D --> E{"Issuer tồn tại trong registry?"}
    E -->|Không| Y["Từ chối, audit request"]
    E -->|Có| F["Chọn tenant repositories và key policy"]
    F --> G["Xử lý discovery / authorize / token / JWKS"]
    G --> H["Kiểm tra response issuer và endpoint URL"]
~~~

Không dùng fallback “không tìm thấy tenant thì trả metadata tenant mặc định”. Fallback có thể khiến token, keys hoặc client credentials của nhiều tenant bị xử lý chung.

### 11.3. Multi issuer có nhất thiết phải có multi key?

Không bắt buộc mọi trường hợp đều có bộ khóa riêng, nhưng **key separation theo issuer** thường giảm blast radius và giảm nguy cơ verifier cấu hình lỏng chấp nhận token chéo tenant. Nếu chia sẻ signing key, Resource Server vẫn phải kiểm tra `iss` chính xác, audience và policy tenant. Khóa giống nhau không làm hai issuer trở thành cùng một trust domain.

## 12. JWK Set URI và vòng đời khóa sau proxy

Trường `jwks_uri` trong metadata chỉ đến **public keys** mà clients/Resource Servers sử dụng để xác minh token hoặc ID Token theo hợp đồng.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client / Resource Server
    participant P as Public HTTPS Ingress
    participant AS as Authorization Server
    C->>P: GET /.well-known/openid-configuration
    P->>AS: Forward metadata request đã chuẩn hóa
    AS-->>P: JSON issuer + jwks_uri public
    P-->>C: JSON metadata
    C->>P: GET /oauth2/jwks
    P->>AS: Forward JWK request
    AS-->>C: JWK Set chứa public keys
    C->>C: Chọn key theo kid/alg và verify token
~~~

### 12.1. Không đưa URL hoặc khóa nội bộ vào metadata

Sai:

~~~json
{
  "issuer": "https://login.example.com",
  "jwks_uri": "http://auth-service:9000/oauth2/jwks"
}
~~~

Đúng theo public contract mẫu:

~~~json
{
  "issuer": "https://login.example.com",
  "jwks_uri": "https://login.example.com/oauth2/jwks"
}
~~~

Nếu vì proxy path prefix mà URL là `https://login.example.com/auth/oauth2/jwks`, phải bảo đảm ingress thực sự phục vụ path này. Không công bố `jwks_uri` nội bộ rồi yêu cầu clients “biết cách rewrite”.

### 12.2. Public JWK Set không chứa private key

JWKS công khai chỉ chứa public key material cần thiết. Với RSA, JWK có thể có `kty`, `n`, `e`, `kid`, `alg`, `use`; **không có** private exponent `d` hoặc các private parameters. Với EC, không đưa private scalar. Private keys được lưu trong keystore/HSM/KMS hoặc secret storage phù hợp, theo thiết kế signing service.

### 12.3. Key rotation trong môi trường nhiều issuer

Khi xoay signing key:

1. Xuất bản public key mới tại JWKS tương ứng trước khi phát token ký bằng key mới nếu cần cho caching clients.
2. Bắt đầu ký token mới bằng key mới với `kid` phù hợp.
3. Giữ public key cũ cho đến khi token cũ hết hạn và cache clients có thể xác minh chúng.
4. Chỉ sau khi hết cửa sổ đó mới bỏ key cũ khỏi JWKS, trừ khi security incident yêu cầu vô hiệu khẩn cấp.
5. Theo dõi lỗi `unknown kid`, issuer mismatch, algorithm mismatch và cache stale.

Với nhiều issuer, cần biết key thuộc issuer nào. **Không chọn key trên toàn hệ thống chỉ dựa vào `kid` mà bỏ qua issuer**; `kid` không phải định danh toàn cục duy nhất giữa mọi tenant.

### 12.4. Caching và CDN

Metadata và JWKS thường được cache. Khi đặt CDN trước discovery:

- Cache key phải phân biệt hostname, path và các thành phần cần thiết để không trộn tenants.
- Không cache response metadata của Acme rồi trả cho Zen.
- Cache headers, ETag và TTL phải phù hợp quy trình key rotation.
- Purge cache phải hoạt động theo issuer/tenant, không chỉ theo một endpoint chung.
- Với issuer custom domain, validate CDN/proxy origin routing, TLS cert và host-based cache key.

Không cache token/introspection response cùng chiến lược công khai của metadata/JWKS; các endpoint credential cần mức bảo vệ hoàn toàn khác.

## 13. Hợp đồng với OAuth2 Client và Resource Server

### 13.1. OAuth2 Client nên cấu hình từ issuer đáng tin

OIDC Client thường có cấu hình `issuer-uri` hoặc discovery URL để tìm authorization/token/JWKS endpoints. Quan trọng:

1. Client phải có **expected issuer** từ cấu hình tin cậy, không lấy issuer do người dùng bất kỳ nhập rồi tin ngay.
2. Sau discovery, field `issuer` phải khớp expected issuer.
3. Client dùng URL endpoint được metadata công bố **chỉ sau khi metadata được xác thực theo trust policy**.
4. Nếu client hỗ trợ OAuth AS Metadata và OIDC Provider Configuration, cần chọn đúng loại metadata/profile.
5. Không hard-code Token Endpoint cho một tenant rồi dùng ID Token/authorization của tenant khác.

### 13.2. Spring Security Resource Server cấu hình issuer

Ví dụ một Resource Server chỉ chấp nhận token do Acme phát hành:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/tenant/acme
~~~

Spring Security dùng issuer để khám phá public keys/JWK Set và xác minh `iss` theo cấu hình, với khả năng lookup và well-known routes tùy phiên bản. Cần kiểm tra Resource Server thực tế hỗ trợ URL discovery cho issuer có path theo route đã chọn.

**Vẫn phải kiểm tra audience.** Cấu hình `issuer-uri` không tự bảo đảm token được phát cho đúng API. Ví dụ Orders API chỉ nhận `aud=orders-api`.

### 13.3. Validator audience

Ví dụ thành phần kiểm tra audience trong Spring Security:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    if (jwt.getAudience().contains("orders-api")) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Invalid audience", null));
};
~~~

Đây là đoạn cấu hình **thành phần validator**, không phải `JwtDecoder` hoặc `SecurityFilterChain` hoàn chỉnh. Trong ứng dụng cần kết hợp nó với validators mặc định cho issuer/thời gian (không được thay thế toàn bộ validators bằng audience-only validator). Phải từ chối token sai issuer ngay cả khi chữ ký được xác minh bằng cùng một key.

### 13.4. Nhiều issuer ở Resource Server

Resource Server nhận token từ Acme và Zen cần bộ issuer allowlist và validator cụ thể cho từng issuer, có thể dùng `JwtIssuerAuthenticationManagerResolver` hoặc resolver tương đương của Spring Security với trusted issuers.

Mẫu tư duy:

~~~text
Incoming Access Token
  -> Resolve candidate issuer (chưa coi là trusted)
  -> Lookup exact issuer trong trusted allowlist
  -> Chọn JwtDecoder/keys/validators của issuer đó
  -> Verify signature, iss, aud, exp, nbf, token type
  -> Tenant/resource authorization
  -> Accept hoặc reject
~~~

**Issuer claim đọc trước khi verify chỉ có thể dùng làm gợi ý chọn giữa các cấu hình đã tin cậy**, không được dùng làm URL động để fetch JWKS từ mạng. Nếu registry không có issuer đó, từ chối ngay.

## 14. Metadata có thể bị lợi dụng như thế nào?

### 14.1. Host header injection và issuer spoofing

Attacker gửi `X-Forwarded-Host: evil.invalid`. Nếu ingress giữ nguyên và ứng dụng dùng header để sinh issuer, metadata có thể chứa domain do attacker kiểm soát. Giảm rủi ro bằng:

- Public Host allowlist ở proxy và ứng dụng.
- Xóa/ghi đè các forwarded headers từ nguồn không đáng tin.
- Issuer cố định cho single issuer.
- Registry exact issuer cho multi issuer.
- Không phản chiếu trực tiếp header vào token claim `iss` hoặc metadata URLs.

### 14.2. SSRF qua dynamic issuer / jwks_uri

Client/Resource Server không nên tự động fetch discovery hoặc JWKS từ `iss` chưa xác minh, nhất là khi URI có thể trỏ đến localhost, cloud metadata endpoint hoặc private network. Một bộ issuer đã phê duyệt cần ràng buộc metadata/JWKS destination, HTTPS/TLS validation và policy DNS/network egress.

### 14.3. Cross-tenant metadata cache poisoning

Nếu CDN cache chỉ theo path mà bỏ Host, metadata custom domain A có thể được trả cho B. Nếu tenant resolver fallback về default, một request sai prefix có thể lấy JWKS của tenant khác. Cần cache key đầy đủ, exact host/path routing và test các trường hợp âm tính.

### 14.4. Open redirect qua authorization endpoint

Discovery có thể đưa client tới Authorization Endpoint, nhưng `redirect_uri` vẫn phải được validate chính xác theo RegisteredClient và grant. Không dùng query parameter bất kỳ để quyết định callback. Tương tự, `post_logout_redirect_uri` cần được kiểm tra theo OIDC logout profile.

### 14.5. Discovery công khai nhưng không phải “public mọi thứ”

Well-known metadata và public JWKS có thể được phép `GET` không cần login, nhưng:

- Không lộ private keys, client secrets, passwords hoặc dữ liệu người dùng.
- Không quảng bá endpoint quản trị chưa có authentication.
- Token/Introspection/Revocation endpoints vẫn có quy tắc bảo mật độc lập.
- CORS và CSRF phải cấu hình theo loại endpoint và browser flow, không dùng `permitAll()` bừa bãi trên toàn server.
- Không đưa URL private management, actuator hoặc internal health endpoint vào metadata.

## 15. Kiểm thử trực tiếp từ public ingress

### 15.1. Kiểm tra metadata HTTPS

~~~bash
curl -i 'https://login.example.com/.well-known/oauth-authorization-server'
~~~

Khi có OIDC:

~~~bash
curl -i 'https://login.example.com/.well-known/openid-configuration'
~~~

Kiểm tra:

- HTTP 200, JSON parse được và đúng content type.
- Field `issuer` đúng public issuer mong đợi.
- Không có `http://auth-service`, `localhost`, Pod IP hoặc internal port.
- Token/JWKS/Authorization/Revocation/Introspection URLs dùng đúng public TLS domain/path.
- `jwks_uri` truy cập được, chỉ công bố public keys.

Không dùng `curl -k` để bỏ xác minh TLS trong acceptance test: như vậy sẽ che lỗi certificate/custom domain.

### 15.2. Dùng jq để kiểm tra các trường cơ bản

~~~bash
curl --silent --show-error \
  'https://login.example.com/.well-known/oauth-authorization-server' |
  jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri, revocation_endpoint}'
~~~

Đoạn shell yêu cầu cài `jq`. Đây là test đọc metadata, không gửi credential. Khi triển khai CI, nên assert **giá trị chính xác** thay vì chỉ in JSON để quan sát.

### 15.3. Kiểm thử custom domain trước khi đổi DNS chính thức

Giả sử IP của ingress test được xác định và doanh nghiệp kiểm soát domain. Có thể dùng `curl --resolve` để ép kết nối tới một IP trong khi giữ hostname/SNI:

~~~bash
curl --resolve 'login.customer.example:443:203.0.113.25' \
  'https://login.customer.example/.well-known/openid-configuration'
~~~

IP `203.0.113.25` là **địa chỉ ví dụ**, không phải địa chỉ hệ thống thật. Cách này giúp kiểm tra public TLS certificate, host routing và metadata theo domain trước khi DNS rollout. Không dùng tùy chọn `--insecure` để che lỗi certificate.

### 15.4. Test path-based issuer theo chuẩn

Ví dụ issuer `https://auth.example.com/tenant/acme`:

~~~bash
curl -i \
  'https://auth.example.com/.well-known/oauth-authorization-server/tenant/acme'

curl -i \
  'https://auth.example.com/tenant/acme/.well-known/openid-configuration'
~~~

Nếu ứng dụng không đáp ứng route này, phải xác định liệu thư viện/phiên bản hoặc reverse proxy có cung cấp biến thể well-known URL khác theo profile hay không. **Không sửa expected issuer để khớp một URL tình cờ trả HTTP 200**; cần giải quyết contract chuẩn, client compatibility và routing một cách có chủ đích.

### 15.5. Test Host/X-Forwarded-Host không đáng tin

Ở ingress test, gửi request có header giả:

~~~bash
curl -i \
  -H 'X-Forwarded-Host: attacker.invalid' \
  -H 'X-Forwarded-Proto: http' \
  'https://login.example.com/.well-known/oauth-authorization-server'
~~~

Kỳ vọng: metadata vẫn dùng `https://login.example.com` hoặc request bị chặn bởi policy; **không bao giờ** sinh `issuer=https://attacker.invalid` hoặc endpoint sử dụng scheme `http` do attacker gửi. Đồng thời test một giá trị Host hoàn toàn không có trong allowlist.

## 16. Integration test với Spring Security và MockMvc

MockMvc hữu ích để kiểm tra contract ở tầng ứng dụng, nhưng **không thay được test end-to-end qua ingress**. Proxy strip/add forwarded headers và TLS/SNI cần test ở môi trường triển khai gần production.

### 16.1. Test issuer cố định

Ví dụ JUnit 5 / Spring Boot test dùng Authorization Server đã được cấu hình:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationMetadataIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void metadataUsesPublicIssuerRatherThanInternalHost() throws Exception {
        mvc.perform(get("/.well-known/oauth-authorization-server")
                    .header("Host", "auth-service:9000"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.issuer")
                    .value("https://login.example.com"))
            .andExpect(jsonPath("$.token_endpoint")
                    .value("https://login.example.com/oauth2/token"))
            .andExpect(jsonPath("$.jwks_uri")
                    .value("https://login.example.com/oauth2/jwks"));
    }
}
~~~

**Điều kiện fixture:** Authorization Server bean `AuthorizationServerSettings` dùng public issuer, security filter chains đã bật metadata endpoint và JWKSource đã được đăng ký. Test này chứng minh response theo cấu hình trong JVM, không chứng minh ingress TLS/Host filtering đã đúng.

### 16.2. Test OIDC chỉ khi đã bật OIDC

Nếu ứng dụng bật `oidc(Customizer.withDefaults())`, bổ sung:

~~~java
@Test
void oidcConfigurationKeepsIssuerConsistent() throws Exception {
    mvc.perform(get("/.well-known/openid-configuration"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.issuer")
                .value("https://login.example.com"))
        .andExpect(jsonPath("$.jwks_uri")
                .value("https://login.example.com/oauth2/jwks"));
}
~~~

Đây là method minh họa đặt trong test class tương ứng; `MockMvc` và static imports giống ví dụ trước. Không copy nó vào project chưa bật OIDC rồi coi HTTP 404 là lỗi của OAuth 2.0 metadata.

### 16.3. Multi issuer test phải xác minh data isolation

Không chỉ assert `issuer` khác nhau. Test thêm:

1. Acme client chỉ nằm trong Acme repository.
2. Authorization Code/Refresh Token của Acme không dùng được ở Zen.
3. `JWKS` Acme và Zen trả đúng public keys theo chính sách key separation.
4. Resource Server Zen từ chối JWT của Acme, dù có cùng `aud` hoặc `sub`.
5. Revocation/Introspection không tìm hoặc xử lý token chéo tenant.
6. Sai issuer path không được fallback sang tenant mặc định.
7. Custom domain chưa được phê duyệt bị chặn trước khi sinh metadata.

## 17. Ma trận kiểm thử Discovery trong production

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 1 | Single issuer sau proxy HTTPS | Metadata chứa issuer và endpoints public HTTPS |
| 2 | Backend nội bộ dùng HTTP | Không lộ internal scheme/host/port trong metadata |
| 3 | Well-known OAuth RFC 8414 | Trả JSON đúng issuer, endpoint và metadata schema |
| 4 | OIDC được bật | Well-known OIDC trả JSON hợp lệ, issuer khớp |
| 5 | OIDC không bật | Không quảng bá OIDC capability giả |
| 6 | Proxy ghi đè Forwarded headers | Host/scheme chính xác theo public request |
| 7 | Client tự gửi X-Forwarded-Host giả | Không phản ánh attacker domain |
| 8 | Unknown Host/SNI | Bị chặn hoặc route sang trang an toàn, không phát issuer |
| 9 | External path prefix /auth | Endpoint URL công bố có prefix phù hợp route thực tế |
| 10 | Proxy strip prefix | Client vẫn gọi Token Endpoint và JWKS thành công |
| 11 | Issuer có path theo RFC 8414 | Well-known URL và field issuer đúng quy tắc |
| 12 | Issuer có path theo OIDC Discovery | Well-known OIDC URL và field issuer đúng |
| 13 | Custom domain được duyệt | TLS certificate/SNI, issuer và endpoint URLs nhất quán |
| 14 | Custom domain chưa verify | Không được dùng làm issuer |
| 15 | Acme metadata request | Không nhận issuer/keys/endpoint của Zen |
| 16 | Unknown issuer path | Từ chối, không fallback |
| 17 | Key rotation | `jwks_uri` chứa key mới và cũ theo kế hoạch |
| 18 | JWKS qua CDN | Cache tách issuer/host; không trả key sai tenant |
| 19 | Resource Server chỉ tin Acme | Từ chối token Zen |
| 20 | Token signature đúng nhưng aud sai | Resource Server từ chối |
| 21 | Redirect URI khác RegisteredClient | Authorization request bị từ chối |
| 22 | Introspection/Revocation cross tenant | Không tiết lộ/đụng vào token tenant khác |
| 23 | Issuer đổi domain | Clients/Resource Servers không vô tình chấp nhận cả hai như một |
| 24 | Backend bị gọi trực tiếp bỏ qua ingress | Network policy hoặc app routing chặn |
| 25 | Proxy/cache có nhiều node | Metadata, route và key policy nhất quán |

**Tiêu chí PASS:** test cần kiểm tra cả response JSON, khả năng gọi endpoint thực tế và kiểm tra signature/issuer/audience trên token đã phát hành. Chỉ thấy HTTP 200 tại well-known endpoint là chưa đủ.

## 18. Chẩn đoán lỗi phổ biến

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Metadata issuer là `http://localhost:9000` | Chưa đặt public issuer hoặc proxy headers sai | Đặt `AuthorizationServerSettings.issuer` và kiểm tra forwarded policy |
| Endpoint URL chứa port nội bộ | App không hiểu external origin | Kiểm tra ingress/Forwarded headers và metadata |
| OIDC discovery 404 | OIDC chưa bật hoặc route sai | Kiểm tra `oidc(...)` và security matcher |
| OAuth metadata 404 nhưng OIDC hoạt động | Well-known path/router mapping khác chuẩn | Kiểm tra RFC 8414 path và proxy routing |
| OAuth Client báo issuer mismatch | Field `issuer` không khớp expected issuer | Sửa contract issuer, không tắt issuer validation |
| Authorization Code đổi token bị 404 | Token Endpoint công bố sai public prefix | Kiểm tra rewrite và metadata |
| Redirect sang `http` sau login | Proxy header/scheme không đúng | Kiểm tra trusted proto, app redirect và HSTS/TLS |
| JWT kid không có ở JWKS | JWKS sai tenant hoặc rotation/cache stale | Kiểm tra `jwks_uri` và publishing keys |
| Token được ký hợp lệ nhưng API trả 401 | `iss`/`aud` hoặc clock sai | Xác minh trusted issuer và audience |
| Custom domain chỉ lỗi ở một số client | DNS/SNI/TLS cert hoặc discovery URI profile | Kiểm tra certificate, domain verification và client SDK |
| Acme metadata lẫn Zen | Tenant routing fallback, shared cache hoặc registry sai | Tắt fallback, sửa cache key, test isolation |
| Same issuer lúc là http lúc là https | Header bị tin/ghi đè không nhất quán | Chuẩn hóa proxy headers, static issuer hoặc exact allowlist |
| Một node trả metadata khác node còn lại | Config/keys/registry không đồng bộ | Kiểm tra rollout, registry version và cache |

### 18.1. Cách điều tra có thứ tự

1. Ghi lại expected issuer từ cấu hình client đáng tin.
2. Từ **ngoài ingress**, gọi well-known URL đúng chuẩn.
3. So sánh `issuer` chính xác, không so hostname gần giống.
4. Kiểm tra các endpoint URL và `jwks_uri` có thể truy cập trên HTTPS.
5. Nếu issuer có path, xác định chuẩn discovery mà client đang dùng.
6. Kiểm tra host/forwarded header handling và proxy rewrite.
7. Xác minh JWT `iss`, `aud`, `kid`, `exp` từ token test không chứa dữ liệu thật.
8. Kiểm tra Resource Server có trusted issuers và keys tương ứng.
9. Với multi issuer, kiểm tra tenant registry, data/keys, cache và routing.
10. Sửa cấu hình và chạy lại cả integration test lẫn end-to-end qua proxy.

Không xử lý issuer mismatch bằng cách tắt validator `iss` hoặc chấp nhận wildcard host: đó là phá vỡ trust boundary OAuth/OIDC.

## 19. Thay đổi custom domain/issuer an toàn

### 19.1. Thay đổi domain không chỉ là đổi DNS

Nếu issuer cũ là `https://login.old.example` và issuer mới là `https://login.new.example`, một Access Token cũ với `iss=https://login.old.example` không tự trở thành token của issuer mới. Client/Resource Server có thể phải tin hai issuer trong thời gian chuyển tiếp, nhưng phải có **chính sách và thời hạn rõ ràng**, không chấp nhận vô thời hạn.

### 19.2. Kế hoạch migration

1. **Inventory:** liệt kê clients, Resource Servers, redirect URIs, logout URIs, JWKS consumers và token lifetimes.
2. **Verify domain:** xác thực ownership, DNS, TLS certificate, SNI và routing.
3. **Publish metadata:** issuer mới có discovery/endpoint URL đúng, JWK Set hợp lệ.
4. **Create tenant/issuer registry entry:** tenant data, signing keys, RegisteredClients và consent mapping theo chính sách.
5. **Test before rollout:** chạy full suite bao gồm code flow, refresh, introspection, revocation, OIDC UserInfo và logout nếu dùng.
6. **Update clients/Resource Servers:** bổ sung issuer mới một cách có kiểm soát, không tắt issuer validation.
7. **Cutover:** chuyển traffic/registrations sang issuer mới; token mới phải mang `iss` mới.
8. **Drain old issuer:** cho token cũ hết hạn hoặc revoke theo policy, kiểm soát refresh và session migration.
9. **Remove old trust:** đóng endpoint/key/issuer cũ khi hoàn thành transition và thông báo rõ.
10. **Audit/rollback:** lưu change record, monitor issuer mismatch và có cách rollback không chấp nhận token sai trust domain.

### 19.3. Rollback có thể phải khôi phục issuer

Nếu đã phát token với issuer mới, việc rollback traffic về issuer cũ không đồng nghĩa token mới được chấp nhận tại mọi API. Có thể cần tiếp tục phục vụ issuer mới một thời gian để người dùng đăng nhập lại hoặc token hết hạn. Đừng đổi field `issuer` trong metadata liên tục để “chạy qua lại” giữa hai domain.

### 19.4. Lưu ý nhiều issuer và key compromise

Khi signing key của một tenant bị lộ, key separation giúp giới hạn phạm vi ảnh hưởng. Nếu cả hai issuer dùng chung key, sự cố có thể buộc luân chuyển trust của nhiều tenant. Runbook phải ghi rõ issuer → keys → active tokens → affected Resource Servers và kế hoạch publish JWKS/revoke.

## 20. Checklist thiết kế và vận hành

1. **Issuer là hợp đồng:** chọn canonical issuer ổn định, exact string; không suy ra từ raw Host.
2. **Well-known URLs:** xác minh RFC 8414/OIDC Discovery đặc biệt khi issuer có path.
3. **Metadata fields:** issuer, endpoints, `jwks_uri` và capabilities phản ánh cấu hình thực tế.
4. **Public URL:** không công bố localhost/service DNS/pod IP/internal ports.
5. **Reverse proxy:** chỉ tin forwarded headers từ trusted ingress và strip header bên ngoài.
6. **Prefix/rewrite:** kiểm thử public route sau login, code exchange, JWKS, introspection/revocation.
7. **OIDC:** chỉ công bố Provider Configuration khi OIDC được bật đúng.
8. **Custom domain:** xác minh ownership, DNS/TLS/SNI, issuer mapping và domain lifecycle.
9. **Multiple issuers:** có allowlist chính xác, không dynamic accept-all/fallback.
10. **Tenant isolation:** repositories/authorization/consent/client registry và keys tuân thủ trust boundary.
11. **Resource Server:** validate JWT signature, issuer, audience, thời gian và policy tenant.
12. **JWKS:** chỉ public keys, key rotation/caching theo issuer, không dùng key sai tenant.
13. **Cache:** metadata/JWKS không lẫn host hoặc tenant; cache purge có quy trình.
14. **SSRF/Host injection:** không fetch JWKS từ issuer không được duyệt hoặc reflect host giả.
15. **Testing:** cả MockMvc, HTTP qua ingress, custom domain và multi-issuer negative cases.
16. **Migration:** có kế hoạch chuyển domain/issuer, key rollover và token đang còn hạn.
17. **Observability:** đo lỗi metadata, issuer mismatch, unknown kid, endpoint URL mismatch.
18. **Privacy:** không ghi authorization code, Access Token, client secret hoặc token response thô vào log.

## 21. Bài tập thực hành và câu hỏi ôn tập

**Bài tập A — Proxy mismatch.** Backend chạy `http://auth-service:9000`, public URL là `https://login.example.com`. Metadata trả internal issuer. Viết cấu hình `AuthorizationServerSettings` và mô tả test chứng minh `iss` của JWT và metadata trùng nhau.

**Bài tập B — Discovery path.** Issuer là `https://auth.example.com/tenant/acme`. Tính URL RFC 8414 và OIDC Provider Configuration, giải thích vì sao hai chuẩn có thể không trùng path.

**Bài tập C — Host injection.** Proxy chuyển nguyên `X-Forwarded-Host` từ client. Attacker gửi `attacker.invalid`. Hãy nêu cách khai thác và bốn bước hạ tầng/ứng dụng để ngăn phản chiếu issuer.

**Bài tập D — External prefix.** Public Token Endpoint là `https://id.example.com/auth/oauth2/token`, backend chỉ nhận `/oauth2/token`. Thiết kế ingress rewrite, forwarded prefix và những assertions cần có trong metadata test.

**Bài tập E — Custom domain.** Tenant Acme muốn `https://login.acme.example` làm issuer chính thức. Liệt kê những thành phần phải đổi: domain ownership, TLS, metadata, JWT issuer, JWKS, clients, Resource Servers và rollback.

**Bài tập F — Multi issuer.** Acme và Zen dùng cùng host nhưng path issuer khác nhau. Viết issuer registry exact-match và test một authorization của Acme không thể đổi code ở Token Endpoint Zen.

**Bài tập G — Keys.** Một Resource Server chỉ tin issuer Acme nhưng thấy JWT Zen có cùng `kid` và cùng public key. Giải thích vì sao vẫn phải từ chối.

**Bài tập H — CDN.** Hai custom domains dùng chung path `/.well-known/openid-configuration`. Thiết kế cache key và test chống cross-tenant metadata contamination.

**Câu hỏi tự đánh giá:**

1. `issuer` khác metadata URL ở điểm nào?
2. OAuth 2.0 Authorization Server Metadata và OIDC Discovery có quy tắc URL giống nhau khi issuer có path không?
3. Vì sao issuer cần khớp chính xác giữa metadata và token `iss`?
4. `jwks_uri` có được trỏ tới Pod IP hoặc service DNS nội bộ không?
5. `server.forward-headers-strategy=framework` có tự bảo vệ trước Host header injection không?
6. Tại sao proxy cần xóa và ghi đè `X-Forwarded-*` từ request bên ngoài?
7. Khi nào custom domain chỉ là alias, khi nào trở thành issuer mới?
8. Vì sao bật `multipleIssuersAllowed(true)` chưa đủ để tạo multi-tenant isolation?
9. Những repository nào cần tenant-awareness?
10. Resource Server chọn key theo issuer và `kid` ra sao?
11. Vì sao không nên tự tải JWKS từ `iss` chưa được tin?
12. Nếu JWT cũ còn hạn khi đổi issuer, làm sao xử lý migration?
13. Vì sao metadata discovery HTTP 200 chưa đủ để kết luận Authorization Code Flow hoạt động?
14. Những lỗi nào có thể do prefix rewrite hoặc CDN cache gây ra?

## 22. Tài liệu tham khảo

- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8414, Section 3 — Obtaining Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414#section-3)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html)
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/reference/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Multitenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)

**Ghi nhớ:** Discovery là **hợp đồng nhận diện và định tuyến được dùng để xây trust**, không phải JSON trang trí. Sau reverse proxy, `issuer` và mọi endpoint phải dùng public HTTPS domain/path chính xác; forwarded headers chỉ được tin qua proxy được kiểm soát. Custom domain trở thành issuer chỉ khi toàn bộ metadata, token, keys và clients/Resource Servers cùng tuân thủ danh tính mới. Trong môi trường đa issuer, luôn có exact issuer allowlist, tenant-aware storage/keys/policies và kiểm thử cách ly; không chấp nhận issuer động từ Host/header và không tắt kiểm tra `iss` để che lỗi cấu hình.
