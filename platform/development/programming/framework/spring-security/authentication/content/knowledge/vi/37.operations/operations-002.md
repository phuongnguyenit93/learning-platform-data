# Cookie, HTTPS và cấu hình danh tính sau reverse proxy

## 1. Bài toán: người dùng thấy HTTPS nhưng Spring Boot nhận HTTP

Trong triển khai thực tế, ứng dụng Spring Boot/Spring Security thường chạy **phía sau reverse proxy, load balancer, API gateway hoặc Kubernetes ingress**. Trình duyệt gọi một địa chỉ HTTPS công khai, nhưng proxy có thể kết thúc TLS (*TLS termination*) rồi chuyển tiếp HTTP tới backend nội bộ.

~~~text
Browser
  GET https://login.example.test/login
  Cookie: __Host-SESSION=...
          |
          | HTTPS/TLS, public host login.example.test:443
          v
[Ingress / Reverse proxy / Load balancer]
          |
          | HTTP (mạng nội bộ được bảo vệ) hoặc re-encrypted HTTPS
          | Host: app-auth:8080
          | Forwarded / X-Forwarded-* do trusted proxy đặt
          v
[Spring Boot :8080]
  request.scheme     có thể là http
  request.serverName có thể là app-auth
  request.isSecure()  có thể là false nếu không xử lý proxy info
          |
          v
[Spring Security / Servlet session / OAuth2 Login / OIDC]
~~~

Nếu ứng dụng không biết **origin công khai đáng tin** hoặc mặc nhiên tin mọi header do mạng gửi, các lỗi có thể xuất hiện:

- Redirect từ `https://login.example.test` sang `http://app-auth:8080` hoặc tạo URL callback OAuth2 sai.
- Session cookie không có `Secure` vì backend nghĩ request dùng HTTP.
- Header HSTS không xuất hiện như mong đợi vì framework không nhận ra request công khai là HTTPS.
- OIDC `redirect_uri` không khớp URI đã đăng ký với IdP, phát sinh lỗi `redirect_uri_mismatch` hoặc state correlation.
- Password-reset/magic-link email sử dụng hostname do attacker tác động.
- `X-Forwarded-For` bị giả mạo khiến rate limiter/audit ghi sai địa chỉ IP, có thể bypass giới hạn yêu cầu đăng nhập.
- Cookie có `Domain`, `Path` hoặc `SameSite` không phù hợp, gây mất phiên sau SSO, CSRF false positive hoặc cookie bị gửi sang subdomain khác.

**Mục tiêu:** trình duyệt luôn tương tác với một **HTTPS public origin** được quản lý; reverse proxy duy trì đúng trust boundary; Spring Security và cookie/session/OIDC vận hành nhất quán với origin đó.

Bài học tập trung vào **vận hành xác thực**. Cấu hình proxy, Spring Boot và security filters phải được xem như một hệ thống, không chỉ thay một dòng `server.forward-headers-strategy` rồi cho rằng đã xong.

## 2. Phân biệt origin công khai, backend address và danh tính tài khoản

Các khái niệm quan trọng:

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| **Public origin** | `https://login.example.test` | Scheme + host + port mà browser và IdP được phép sử dụng. |
| **External URL / callback** | `https://login.example.test/login/oauth2/code/corp` | URI được IdP/OP gọi lại hoặc browser redirect; cần khớp đăng ký. |
| **Backend destination** | `http://app-auth:8080` | Địa chỉ proxy kết nối tới service, không được lộ như origin ứng dụng. |
| **Request Host** | `Host: login.example.test` | Host trong HTTP request; vẫn là dữ liệu từ client, cần kiểm tra trust. |
| **Forwarded authority/scheme** | `X-Forwarded-Host`, `X-Forwarded-Proto` | Metadata do proxy tin cậy xây dựng, không phải chứng thực người dùng. |
| **Identity issuer** | `https://idp.example.test/realms/corp` | Issuer danh tính trong ID Token/JWT; không đồng nghĩa public origin của ứng dụng. |
| **User identity** | `(iss, sub)` hoặc user ID nội bộ | Danh tính tài khoản, không được suy từ IP, Host, forwarded headers. |
| **Session identity** | Random session ID trong cookie | Khóa tra phiên, không tự cho biết MFA/role còn hợp lệ. |

**Đừng lẫn `Host` hoặc client IP với danh tính người dùng.** `X-Forwarded-User`, `X-Remote-User` hoặc header chứa email chỉ được tin nếu có **một gateway xác thực thật sự**, xóa header do client đưa vào, bảo vệ đường kết nối upstream và có contract danh tính đã kiểm chứng. Reverse proxy thông thường chỉ mang thông tin tuyến mạng, **không phải Identity Provider**.

### Hai sơ đồ nguy cơ

~~~text
Sai:
Internet user -> Host: attacker.test
              -> X-Forwarded-Proto: https
              -> X-Forwarded-Host: attacker.test
              -> Spring blindly trusts forwarded fields
              -> password reset URL, OAuth2 redirect or callback bị đổi host

Đúng:
Internet user -> trusted edge rejects unknown Host
              -> strips inbound Forwarded and X-Forwarded-*
              -> sets fixed/validated public scheme and host
              -> only private proxy-to-backend connection can reach app
              -> Spring consumes trusted metadata
              -> security-critical URLs constrained by canonical origin
~~~

Có thể triển khai nhiều domain/tenant, nhưng hostname tương ứng phải được **xác minh và đưa vào allowlist/mapping authoritative**, không lấy thẳng bất kỳ `Host`/`X-Forwarded-Host` mà client gửi.

## 3. TLS termination: HTTPS ở ngoài không đồng nghĩa bảo mật mọi hop

Trong mô hình TLS tại proxy:

~~~text
Browser --TLS--> Edge --HTTP--> Backend
~~~

`Secure` cookie bảo vệ việc **browser gửi cookie qua HTTPS** đến edge; nó **không mã hóa** dữ liệu giữa edge và backend nếu hop nội bộ là HTTP. Nếu mạng nội bộ được coi là không tin cậy, có nhiều tenant, bị chia sẻ hoặc qua vùng mạng không được bảo vệ, cần **re-encryption HTTPS**, mTLS hoặc cơ chế mạng được phê duyệt thay vì coi "private subnet" là bảo đảm tuyệt đối.

Các yêu cầu vận hành:

1. Chỉ công khai cổng HTTPS cho trang login/callback và các API mang credential; hạn chế/bắt buộc redirect HTTP về HTTPS tại edge.
2. TLS certificate khớp hostname, được gia hạn và kiểm tra; dùng TLS version/cipher theo policy tổ chức.
3. Không cho client Internet kết nối trực tiếp `app-auth:8080` hoặc các cổng admin/actuator nhạy cảm.
4. Giới hạn nguồn network có quyền gửi request đến backend: chỉ ingress/gateway hoặc trusted service identities.
5. Mọi `Forwarded`, `X-Forwarded-*` và identity headers phải được **reset tại ranh giới trust**.
6. Với các đường đi qua proxy/mesh nhiều hop, hiểu nơi TLS kết thúc và proxy nào sở hữu metadata gốc.
7. Kiểm tra request/response logs ở proxy để không ghi Authorization header, cookie, token trong query hoặc form body.

**Không suy rằng ứng dụng cần tự bind port 443** khi HTTPS terminate tại gateway. Spring Boot có thể tiếp tục nghe HTTP nội bộ nhưng phải được bảo vệ đường mạng và nhận đúng external scheme sau khi xác minh nguồn proxy.

## 4. Những header forwarded cần nhận diện

**RFC 7239 `Forwarded`** là dạng chuẩn:

~~~http
Forwarded: for=192.0.2.20;proto=https;host=login.example.test
~~~

Các header de facto thường gặp:

~~~http
X-Forwarded-For: 192.0.2.20
X-Forwarded-Proto: https
X-Forwarded-Host: login.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /auth
~~~

Ý nghĩa:

- `for` / `X-Forwarded-For`: mô tả client hoặc chuỗi intermediary network hops. **Không tự chứng minh user identity**.
- `proto` / `X-Forwarded-Proto`: scheme của request trước proxy, thường là `https`.
- `host` / `X-Forwarded-Host`: public host mà proxy đã kiểm soát.
- `X-Forwarded-Port`: public port, có thể khác backend `8080`.
- `X-Forwarded-Prefix`: external path prefix nếu gateway rewrite URI. Không phải lúc nào cũng cần.

Ví dụ browser gọi `https://login.example.test/auth/login`, gateway strip `/auth` và chuyển `/login` vào backend. Nếu app tạo redirect `/login/oauth2/code/corp` không tính prefix, callback sẽ thiếu `/auth`. Nhưng **tin vào prefix do attacker gửi** có thể dẫn đến redirect/path poisoning; chỉ dùng khi proxy đã chuẩn hóa và app có contract path rõ ràng.

### Không để hai bộ header mâu thuẫn

Spring Framework có thể hỗ trợ cả `Forwarded` và `X-Forwarded-*`. Nếu edge chỉ xóa `X-Forwarded-Host` nhưng quên `Forwarded: host=attacker.test`, một component có thể đọc bộ khác và tạo URL sai.

**Biên tin cậy phải xóa/ghi đè cả hai họ header**, dù sản phẩm chỉ dùng một loại. Xác minh danh sách header lạ/legacy, duplicate header, nhiều giá trị comma-separated và cách CDN/LB merge headers. Không cố gắng sửa bằng cách "ưu tiên header nào hợp lý" ở từng controller.

## 5. Cách Spring Boot xử lý forwarded headers

Trong Spring Boot 3.x, property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Các mode có ý nghĩa:

| Giá trị | Hành vi | Khi nào cân nhắc |
|---|---|---|
| `none` | Không sử dụng forwarded headers làm thông tin origin của request. | Backend public trực tiếp hoặc không có trusted proxy metadata. |
| `native` | Dùng hỗ trợ của container/server như Tomcat `RemoteIpValve`. | Proxy gửi những headers cơ bản được native server hỗ trợ; cần giới hạn trusted proxies. |
| `framework` | Dùng Spring Framework `ForwardedHeaderFilter` (Servlet) hoặc `ForwardedHeaderTransformer` (reactive). | Cần xử lý forwarded host/proto/port/prefix theo framework. |

**`framework` không tự xác thực rằng người gửi header là proxy tin cậy.** Nếu client truy cập backend trực tiếp hoặc edge không strip headers do client cung cấp, bật `framework` có thể biến dữ liệu tự khai thành scheme/host được server tin.

Với `native`, container có cấu hình proxy trust và cách parse riêng. Với Tomcat, kiểm tra các thuộc tính `server.tomcat.remoteip.*`, nhất là danh sách internal/trusted proxies. Đừng đặt cấu hình tin mọi proxy chỉ để test hoạt động; giới hạn theo topology thật.

### Mẹo với Tomcat context-root redirect

Theo Spring Boot embedded server docs, khi TLS terminate tại proxy và dùng Tomcat, có trường hợp nên đặt:

~~~yaml
server:
  tomcat:
    redirect-context-root: false
~~~

Điều này giúp forwarded proto được xử lý trước các redirect ở context root. Không sửa property đó một cách mù quáng nếu không dùng Tomcat hoặc ứng dụng không có hiện tượng redirect context root; xác minh request path và order của valves/filters.

### Không đăng ký trùng filter

Nếu đã dùng `server.forward-headers-strategy=framework`, thường **không cần** tự tạo thêm `ForwardedHeaderFilter` bean/filter registration thứ hai. Nếu vừa native vừa framework xử lý cùng headers theo nhiều lớp, có thể sinh kết quả khó đoán. Chọn một chiến lược rõ, kiểm thử request scheme/host/port và redirect thật.

## 6. Trust boundary quan trọng hơn property trong application.yml

Tài liệu Spring Framework cảnh báo: không có cách an toàn để ứng dụng tự biết `Forwarded`/`X-Forwarded-*` có thực sự được tạo bởi proxy hay do client gửi, nếu biên network không kiểm soát. Biện pháp gốc là:

1. **Edge gateway xóa** các header forwarded do client gửi từ Internet.
2. **Edge ghi lại** giá trị origin/IP có nguồn tin cậy, sau khi kiểm tra hostname và listener TLS.
3. Mọi proxy trung gian chỉ nhận và forward theo hợp đồng topology, không để client tùy ý thêm giá trị trước mắt.
4. Backend chỉ mở network ingress cho những proxy đã cho phép.
5. Ứng dụng vẫn **giới hạn các security-critical absolute URLs** theo canonical allowlist, không dựa toàn bộ vào forwarded host.

Một chính sách đơn giản cho **single-domain login application**:

~~~text
publicScheme = https
publicHost   = login.example.test
publicPort   = 443

Edge:
  reject unknown Host/SNI
  X-Forwarded-Proto := https
  X-Forwarded-Host  := login.example.test
  X-Forwarded-Port  := 443
  Forwarded         := remove or trusted normalized value

Backend:
  reachable only from ingress
  Spring reconstructs external origin from sanitized headers
  security links generated from canonical configured origin
~~~

Trong môi trường nhiều tenant với custom domains, thay `publicHost` cố định bằng mapping đã xác minh theo tenant/host, không phải passthrough.

**Đặc biệt:** có thể dùng `ForwardedHeaderFilter` ở chế độ `removeOnly` khi muốn bỏ metadata không tin và không dùng nó để xây request, theo tài liệu Spring Framework. Không cần tự viết Servlet filter regex chỉ để parse `Forwarded`.

## 7. Ví dụ Nginx ingress cho một public login origin

Đoạn minh họa sau giả định **Nginx trực tiếp nhận HTTPS từ browser**, là biên tin cậy đầu tiên, host duy nhất `login.example.test` và backend có hostname nội bộ `app-auth`.

~~~nginx
# Minh họa kiến trúc; điều chỉnh certificate, limits và networking
# theo môi trường triển khai, không sao chép nguyên cho production.
server {
    listen 443 ssl;
    server_name login.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        # Single canonical external host:
        proxy_set_header Host              login.example.test;
        proxy_set_header X-Forwarded-Host  login.example.test;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port  443;

        # Nginx này là trusted edge đầu tiên:
        proxy_set_header X-Forwarded-For   $remote_addr;

        # Không chuyển Forwarded hoặc prefix do client tự gửi:
        proxy_set_header Forwarded          "";
        proxy_set_header X-Forwarded-Prefix "";

        proxy_pass http://app-auth:8080;
    }
}
~~~

Đây **chưa phải Nginx config hoàn chỉnh**: cần default host/SNI rejection, HTTP→HTTPS redirect chính sách, TLS hardening, rate limits, request-size limits, logging redaction, timeout/upstream health và kiểm soát firewall. Nginx phải có default server không cho unknown Host đi vào application. Với topology có CDN/LB trước Nginx, `$remote_addr` có thể là IP của CDN, không phải browser; thiết lập `real_ip`/trusted proxy chain chính xác rồi chọn client IP sau chuẩn hóa.

**Không dùng `proxy_set_header Host $http_host` hoặc chuyển `X-Forwarded-Host $http_x_forwarded_host`** ở edge trước khi kiểm tra và allowlist. Chúng có thể chứa giá trị do client gửi. Ngay cả `$host` phải được đặt trong một server block đã có cơ chế reject unknown host rõ ràng.

Nếu deployment chọn header chuẩn RFC `Forwarded` thay vì `X-Forwarded-*`, chỉ tạo giá trị đã chuẩn hóa từ edge. Đảm bảo các intermediary không sinh hai nguồn sự thật mâu thuẫn.

## 8. Một cấu hình Spring Boot Servlet minh họa

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
  servlet:
    session:
      timeout: 30m
      tracking-modes: cookie
      cookie:
        name: "__Host-JSESSIONID"
        secure: true
        http-only: true
        same-site: lax
        path: "/"

spring:
  application:
    name: login-portal
~~~

Giải thích:

- `port: 8080` là backend internal listener, không có nghĩa website public là HTTP.
- `forward-headers-strategy: framework` reconstruct request scheme/host/port **sau khi proxy đã sanitize**.
- `session.timeout` thường là idle timeout, **không tự tạo absolute session lifetime**.
- `tracking-modes: cookie` tránh truyền session ID qua URL nếu container có hỗ trợ rewrite; cần test với phiên bản Servlet container thực.
- Cookie `__Host-JSESSIONID` có `Secure; Path=/`, **không đặt Domain**; đáp ứng quy tắc prefix `__Host-` trong browser hỗ trợ.
- `HttpOnly` ngăn JS trực tiếp đọc cookie, nhưng **không chặn CSRF hoặc XSS thao tác thay user**.
- `SameSite=Lax` là lựa chọn ví dụ thích hợp cho nhiều web-login redirect dạng top-level GET; không tự đúng cho mọi OIDC/SAML flow.

**Phạm vi ví dụ:** những property trên áp dụng chủ yếu cho embedded Servlet session cookie. Nếu dùng **Spring Session** hoặc custom `CookieSerializer`, cơ chế phát cookie có thể khác; cần xem phần riêng bên dưới. Nếu ứng dụng chạy sau proxy path prefix `/auth` hoặc có nhiều web apps dùng cùng host, quy tắc `__Host-...; Path=/` có thể gây va chạm cookie name: phải thiết kế isolation bằng host/name riêng.

Không bật các property ở môi trường HTTP localhost rồi mặc nhiên mong browser nhận cookie `Secure` trên mọi trình duyệt; production và local profile nên phân biệt.

## 9. Hiểu đúng `Set-Cookie` và tác dụng từng thuộc tính

Ví dụ response sau đăng nhập:

~~~http
HTTP/1.1 302 Found
Location: /dashboard
Set-Cookie: __Host-JSESSIONID=s7R4X8p9; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Giá trị cookie trên chỉ là **ví dụ giả**, không phải session ID thực.

| Thuộc tính | Bảo vệ hoặc ảnh hưởng gì? | Không thay thế được gì? |
|---|---|---|
| `Secure` | Browser chỉ gửi cookie trên kết nối HTTPS (với ngoại lệ hành vi localhost). | Không mã hóa HTTP giữa proxy và backend; không chặn JS nếu thiếu HttpOnly. |
| `HttpOnly` | `document.cookie` không đọc/ghi trực tiếp được cookie trong browser hỗ trợ. | Không tự chặn CSRF, XSS request được phép hay ăn cắp session ở server. |
| `SameSite=Strict` | Giảm gửi cookie trong nhiều ngữ cảnh cross-site. | Có thể làm vỡ navigation/OIDC callback hợp lệ; không thay toàn bộ CSRF. |
| `SameSite=Lax` | Gửi cookie trong same-site và một số top-level cross-site navigation an toàn. | Không bảo đảm cookie đi kèm cross-site POST callback/form_post. |
| `SameSite=None` | Cho phép cross-site cookie contexts khi browser hỗ trợ; phải có `Secure`. | Không vượt qua mọi third-party-cookie blocking/browser privacy policy. |
| `Domain` | Cho phép cookie tới host chỉ định và các subdomain hợp lệ. | Không là ranh giới chặn XSS ở sibling subdomains; mở rộng scope. |
| `Path` | Chỉ gửi cookie tới các request path khớp. | **Không phải** biện pháp security isolation chống mã ở path khác đọc/ghi. |
| `Max-Age`/`Expires` | Điều khiển cookie persistence trong browser. | Không tự revoke server-side session hoặc bảo đảm phiên có absolute timeout. |
| `Partitioned` | Cookie theo mô hình partitioned storage trên browser hỗ trợ. | Không phải giải pháp universal cho SSO; cần `Secure` và compatibility tests. |

Nếu không khai báo `Domain`, browser tạo **host-only cookie**, thường hạn chế phạm vi hơn `Domain=example.test`. Với login service riêng, tránh chia session cookie cho toàn bộ `*.example.test` trừ khi kiến trúc và threat model đòi hỏi thật sự.

**Không ghi token/password vào cookie tên khác với ý nghĩa session nhưng thiếu kiểm soát.** Cookie value chứa session identifier vẫn là credential; reverse proxy access logs và error telemetry không được ghi `Cookie`/`Set-Cookie` raw.

## 10. Cookie prefix `__Host-` và `__Secure-`

MDN mô tả cookie prefixes được browser hỗ trợ để tăng tính ràng buộc:

- `__Secure-name`: phải được set qua HTTPS và có `Secure`.
- `__Host-name`: phải được set qua HTTPS, có `Secure`, `Path=/` và **không có `Domain`**. Điều này buộc cookie chỉ thuộc host đã phát hành và phạm vi path toàn host.
- Các prefix mới hơn như `__Http-` hoặc `__Host-Http-` có thêm yêu cầu `HttpOnly` ở browser hỗ trợ; cần kiểm tra compatibility nếu chọn.

Ví dụ phù hợp:

~~~http
Set-Cookie: __Host-SESSION=opaque123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ví dụ **không phù hợp**:

~~~http
Set-Cookie: __Host-SESSION=opaque123; Domain=example.test; Path=/; Secure
Set-Cookie: __Host-SESSION=opaque123; Path=/auth; Secure
Set-Cookie: __Host-SESSION=opaque123; Path=/; HttpOnly
~~~

Ba dòng sai tương ứng vì có Domain, Path không phải `/`, thiếu Secure. Browser có thể từ chối hoàn toàn cookie thay vì "sửa cho đúng". Khi một ứng dụng bị log out liên tục sau deploy, hãy kiểm tra DevTools xem `Set-Cookie` bị browser reject vì prefix rules hay không.

**Không dùng `__Host-` khi buộc phải có cookie `Path=/auth` hoặc `Domain=...`.** Có thể chọn cookie khác với scope đã xem xét, hoặc tách authentication origin thành hostname riêng để áp quy tắc prefix an toàn hơn.

## 11. Spring Session: cookie serializer và nhiều replicas

Với **Spring Session Redis/JDBC**, session ID cookie thường được phát hành/quản lý qua Spring Session. Tùy cấu hình, cookie name mặc định có thể là `SESSION` thay vì servlet `JSESSIONID`. Nếu dùng Spring Session, chỉ chỉnh `server.servlet.session.cookie.*` có thể **không tạo ra header kỳ vọng** nếu Spring Session serializer đang điều khiển cookie.

Ví dụ custom serializer trong Spring Boot 3.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("__Host-SESSION");
        serializer.setCookiePath("/");
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("Lax");
        // Không setDomainName: giữ cookie host-only.
        return serializer;
    }
}
~~~

Đây là **mã tích hợp** cần Spring Session dependency/config, không phải chương trình Java độc lập. Cần xác nhận Spring Session version, custom CookieSerializer bean khác và môi trường mạng. Khi dùng `__Host-SESSION`, browser chỉ chấp nhận cookie nếu response thực gửi qua HTTPS và header có đúng `Secure`, `Path=/` và không Domain.

Với nhiều replicas:

- Dùng session repository chia sẻ hoặc session affinity theo kiến trúc, nhưng session affinity không thay cơ chế revoke all.
- Đảm bảo mọi replica dùng **cùng cookie name, serializer policy, session store và context path logic**.
- Cookie logout phải xóa đúng **name, Path và Domain** đã dùng trước đó, nếu không browser giữ cookie cũ.
- Thay cookie name đột ngột có thể khiến phiên cũ không được tìm lại; triển khai migration/rollback có kế hoạch.
- Session store TTL, idle timeout, absolute expiry và account/security epoch check phải được thiết kế riêng.

**Một cookie được phát đúng cờ không bảo đảm session server-side không bị chiếm quyền hoặc vẫn hợp lệ sau password reset.** Cần session rotation, logout/revocation và authorization checks.

## 12. SameSite và callback OAuth2/OIDC/SAML

Một vấn đề thường gặp: user bắt đầu login ở `https://login.example.test`, ứng dụng lưu OAuth2 authorization request và `state` trong HTTP session, rồi redirect browser sang IdP. Khi IdP gọi lại callback, browser cần gửi cookie session tương ứng để Spring Security ghép kết quả.

~~~text
GET /oauth2/authorization/corp
  -> create state/nonce and store authorization request
  -> browser redirects to https://idp.example.test

IdP:
  -> authenticates user
  -> redirects back to https://login.example.test/login/oauth2/code/corp
       ?code=...&state=...

Browser:
  -> sends appropriate session cookie?
Spring OAuth2LoginAuthenticationFilter:
  -> finds matching authorization request/state
  -> validates flow / exchanges code
  -> creates local Authentication/session
~~~

**`SameSite=Lax`** thường phù hợp với callback bằng **top-level cross-site GET navigation**. Nhưng nếu flow dùng `response_mode=form_post` hoặc SAML POST binding từ IdP, cookie với Lax có thể không được gửi trên cross-site POST, gây lỗi state/relay-state hoặc mất phiên. `SameSite=Strict` thường càng hạn chế.

Nếu buộc dùng `SameSite=None; Secure` cho một số cookie phục vụ federation, phải đánh giá:

1. Chỉ cookie nào cần cross-site behavior; không tự mở rộng tất cả cookies.
2. Có CSRF token/Origin checks và state/nonce bảo vệ callback đủ mạnh.
3. Browser có chính sách third-party cookie blocking làm flow vẫn hỏng hay không.
4. IdP thực dùng redirect GET, form POST, iframe hoặc hybrid flow nào.
5. Cookie partitioning/first-party contexts và fallback phù hợp.
6. Session cookies cần HttpOnly dù response mode khác nhau; không hạ bảo mật vì lỗi SSO.

**Không tắt CSRF toàn ứng dụng để chữa lỗi SameSite.** `state` của OAuth2 và CSRF token của các POST form là những cơ chế liên quan nhưng khác purpose; cần hiểu luồng thật.

## 13. OIDC redirect URI phải là public HTTPS URL chính xác

Spring Security OAuth2 Login thường dùng redirect URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Ví dụ:

~~~text
External URL: https://login.example.test
Registration ID: corp
Redirect URI: https://login.example.test/login/oauth2/code/corp
~~~

IdP thường yêu cầu URI đã đăng ký **khớp chính xác** với redirect URI khi authorization code flow diễn ra. Nếu Spring xây `http://app-auth:8080/login/oauth2/code/corp` hoặc `http://login.example.test/...`, login có thể bị từ chối ngay tại IdP.

Ví dụ YAML chỉ thể hiện đường callback; **không phải toàn bộ client registration**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

Ứng dụng thực còn cần client ID, client secret/cơ chế client authentication thích hợp, provider issuer/authorization/token endpoints, scopes, state, nonce và PKCE theo loại client/policy.

### Hai chiến lược hình thành public base URL

**Cách A – trusted forwarded origin:** cấu hình edge chuẩn hóa headers, Boot xử lý forwarded info và Spring tạo `{baseUrl}` từ request. Phù hợp khi topology vững và cần nhiều host/prefix.

**Cách B – canonical origin cấu hình:** với login service chỉ có một hostname, dùng public origin/redirect URI đã cấu hình cố định hoặc allowlist. Có thể giảm nguy cơ host-header poisoning cho liên kết nhạy cảm.

Hai cách có thể bổ trợ. Ngay cả khi `server.forward-headers-strategy=framework` đang hoạt động, **password-reset link, email verification link, OAuth2 callback và post-login redirects** vẫn nên có origin policy được xác minh, không nối trực tiếp từ một header client tùy ý.

### Issuer không phải callback origin

- Application public origin: `https://login.example.test`.
- IdP issuer: `https://idp.example.test/realms/corp`.
- API audience: định danh resource server theo contract.

Đừng thay issuer JWT bằng public host của ứng dụng chỉ vì đã sửa proxy scheme. Resource server phải kiểm issuer/signature/audience/expiry theo IdP/AS được tin. `redirect_uri` được chọn cho OIDC client khác với `issuer-uri` của token validation.

## 14. Host header injection và link có credential

Một lỗi nghiêm trọng là xây email hoặc redirect từ request host không đáng tin:

~~~java
// Mẫu KHÔNG nên dùng cho security-critical links:
String resetUrl = request.getScheme() + "://"
        + request.getServerName()
        + "/recovery/reset?token=" + rawToken;
~~~

Nếu `getServerName()` được hình thành từ `Host` hoặc forwarded host không được kiểm soát, attacker có thể khiến email mang token thật nhưng trỏ tới domain của họ. Phương pháp an toàn hơn là **public origin được cấu hình cố định** hoặc host mapping do tenant đã xác minh.

Ví dụ Spring component:

~~~java
import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PublicIdentityUrls {
    private final URI publicOrigin;

    public PublicIdentityUrls(
            @Value("https://login.example.test") String publicOriginText) {
        this.publicOrigin = URI.create(publicOriginText);
    }

    public URI recoveryPage() {
        return publicOrigin.resolve("/recovery/reset");
    }

    public URI oauth2Callback() {
        return publicOrigin.resolve("/login/oauth2/code/corp");
    }
}
~~~

Đây là **integration snippet** cố tình dùng constant origin cho ví dụ; production có thể cấu hình externalized value với validation lúc startup. Nếu dùng OAuth2 registration redirect URI template khác, phải đồng bộ với chính sách này.

**Không truyền raw recovery token qua một open redirect** hoặc `returnTo` tùy ý. Không để URL redirect tới domain attacker chỉ vì query param `next=https://evil.test`. Validate allowlist exact origin và paths cần thiết; dùng relative redirects khi có thể.

Kể cả HTTPS cũng không ngăn token lộ qua reverse-proxy access log nếu token xuất hiện trong request query. Cần log redaction cho recovery endpoints và lifetime/single-use policies riêng.

## 15. HSTS, HTTPS redirects và response security headers

**HTTP Strict Transport Security (HSTS)** yêu cầu browser ưu tiên HTTPS cho host đã được ghi nhận. Ví dụ:

~~~http
Strict-Transport-Security: max-age=31536000
~~~

Nếu đã đánh giá đủ toàn bộ subdomains:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Cẩn trọng với `includeSubDomains` và `preload`: chúng có tác động đến cả subdomains, cần chắc chắn mọi subdomain liên quan đã có HTTPS ổn định và quy trình rollback. HSTS **chỉ có hiệu lực khi được browser nhận từ HTTPS response hợp lệ**, không chữa một lần truy cập HTTP đầu tiên nếu host chưa được preload/ghi nhận.

Theo tài liệu Spring Security, HSTS nằm trong cơ chế security response headers, thông thường gắn cho HTTPS requests. Khi reverse proxy terminate TLS nhưng backend coi request là HTTP, có thể xuất hiện HSTS không được phát như dự kiến. Có thể xử lý ở edge hoặc cấu hình forwarded scheme đáng tin để framework nhận `isSecure()` đúng.

**Không chồng chéo header**: nếu proxy và Spring cùng đặt HSTS với policy khác nhau, behavior khó kiểm soát. Chọn owner rõ ràng, test response ngoài edge thực.

Bổ sung:

- Redirect HTTP→HTTPS tại edge cho web login và callback; kiểm tra thứ tự redirect và URL chuẩn.
- `Content-Security-Policy` cho trang login/recovery giúp giảm XSS; cấu hình theo frontend.
- `Referrer-Policy` phù hợp để hạn token/URL nhạy cảm đi trong Referer; trang recovery có thể dùng `no-referrer`.
- `Cache-Control: no-store` cho trang/response mang dữ liệu nhạy cảm.
- Không disable toàn bộ mặc định security headers chỉ để sửa một HSTS/iframe issue.

## 16. CSRF, CORS và cookie có credentials

Trong web app sử dụng **session cookie**, browser tự gửi cookie khi request phù hợp scope. Điều này mở rủi ro **Cross-Site Request Forgery** nếu endpoint thay đổi trạng thái mà không xác minh ý định người dùng.

- `HttpOnly` **không** chặn CSRF: browser vẫn tự đính cookie vào request.
- `Secure` bảo vệ HTTP transport, **không** là token CSRF.
- `SameSite` giảm một số cross-site cases nhưng **không thay** CSRF tokens và Origin/Referer checks theo security policy.
- OAuth2 `state` giúp bảo vệ correlation/cross-site request confusion trong login flow; không phải CSRF token universal cho mọi endpoint nghiệp vụ.

Một Spring Security Servlet config minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        // Giữ CSRF mặc định; không gọi csrf.disable().
        return http.build();
    }
}
~~~

Đây là snippet tích hợp, cần client registration và các endpoint thực. `oauth2Login()` không tự quyết định cookie `SameSite` hay proxy trust. Phải kiểm tra login callback và logout POST thật.

### Cross-origin SPA gọi API

Nếu `https://app.example.test` dùng JavaScript gọi `https://api.example.test` với cookie authentication:

- `fetch(..., { credentials: "include" })` có thể cần thiết.
- Server CORS phải allowlist **origin cụ thể**, không dùng wildcard `*` cùng credentials.
- Browser chỉ nhận/sử dụng cookie theo Domain, Path, SameSite và HTTPS policy.
- **CORS không là cơ chế xác thực** và không thay CSRF; một origin được allowlist chưa đồng nghĩa user có quyền.
- Cross-origin khác cross-site: cùng eTLD+1 dưới HTTPS có thể được xét same-site trong các tình huống nhất định, nhưng vẫn cần kiểm tra chính sách browser và các ngữ cảnh iframe/third-party.

Nếu session cookie chỉ dùng cho login host, tránh chia sang API bằng `Domain=.example.test` trừ khi đó là yêu cầu kiến trúc đã xem xét rủi ro subdomain takeover và session fixation. Token-based API/BFF có thể là lựa chọn khác cho ranh giới khác origin.

## 17. Client IP, rate limit và giả mạo forwarded headers

Ứng dụng xác thực thường giới hạn số lần thử login theo IP và account identifier. Nếu đọc:

~~~java
request.getHeader("X-Forwarded-For")
~~~

rồi lấy phần tử đầu tiên làm IP thực mà **không có trust boundary**, attacker có thể gửi IP tùy ý hoặc danh sách comma-separated để né rate limiter và làm sai audit.

Một chain thực:

~~~text
Browser IP A
   -> CDN IP B
   -> Load balancer IP C
   -> Nginx ingress IP D
   -> Spring Boot IP E
~~~

`X-Forwarded-For` có thể chứa nhiều IP. Vị trí nào được coi là client IP phụ thuộc **những proxy nào được tin và quy tắc append/overwrite**. Không có một quy tắc "luôn lấy IP đầu tiên" đúng cho mọi chuỗi proxies.

Chiến lược:

1. Dùng edge/gateway chuẩn hóa client IP từ peer/network information và trusted chain.
2. Strip/overwrite inbound `Forwarded`/`X-Forwarded-For`, không cho browser tự đưa chain giả.
3. Cấu hình `RemoteIpValve`/trusted proxies theo container nếu dùng native.
4. App rate limiter nhận IP đã được xác định đáng tin theo contract, cùng user/tenant/global limits.
5. Áp quota cho identifier tồn tại và không tồn tại để tránh account enumeration.
6. Không coi IP là identity: NAT, VPN, IPv6 privacy address, mobile networks và proxies thay đổi.

**Một cấu hình forwarded header sai không chỉ gây redirect sai; nó có thể trực tiếp làm vô hiệu giới hạn login và tạo audit sai sự thật.**

## 18. Path prefix, multi-app host và callback URL

Giả sử public app ở `https://login.example.test/auth`, nhưng gateway strip `/auth` trước backend:

~~~text
Browser: GET /auth/oauth2/authorization/corp
Proxy:   GET /oauth2/authorization/corp to backend
Backend: wants to redirect to /auth/login/oauth2/code/corp
~~~

Nếu Spring không biết prefix, nó có thể tạo callback thiếu `/auth`. Nếu `X-Forwarded-Prefix` bị attacker sửa, redirect có thể bị poison. Kiểm tra:

- Gateway có thật sự strip prefix không? Hay chỉ forward nguyên path?
- Spring app có `server.servlet.context-path` riêng không?
- `X-Forwarded-Prefix` được edge đặt và sanitize chưa?
- OIDC registration redirect URI tại IdP đã bao gồm prefix chính xác chưa?
- Session cookie `Path` có bao phủ callback path không?
- Nếu dùng `__Host-SESSION`, cookie phải `Path=/` nên có thể va chạm với ứng dụng khác cùng host; cân nhắc tách subdomain.
- Các relative redirects và absolute redirects có dùng cùng policy public base URL không?
- Spring Security filter-chain matchers có bao phủ **backend path sau rewrite** không?

**Không đồng thời cấu hình context path và forward prefix giống nhau nếu điều đó tạo doubled prefix** (`/auth/auth/...`). Kiểm tra bằng yêu cầu thực từ browser qua edge và xem `Location` chính xác.

## 19. WebFlux và forwarded headers

Với **Spring WebFlux reactive**, thay vì Servlet `ForwardedHeaderFilter`, Spring Framework sử dụng cơ chế `ForwardedHeaderTransformer`. Spring Boot property `server.forward-headers-strategy=framework` có thể cấu hình hỗ trợ tương ứng theo stack.

Cookie reactive cũng có các properties `server.reactive.session.cookie.*` theo Spring Boot phiên bản hỗ trợ. Đừng copy `server.servlet.session.cookie.*` rồi mặc định chúng điều khiển WebFlux session.

Ví dụ mô hình:

~~~yaml
server:
  forward-headers-strategy: framework
  reactive:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Đoạn này là ví dụ cấu hình **reactive session cookie**, không dùng cùng Servlet session config ở phần 8. Nếu ứng dụng thêm Spring Session reactive hoặc gateway tự phát cookie, kiểm tra bộ serializer/response thực tế.

Với WebFlux, các filter/authorization WebFilter khác với Servlet SecurityFilterChain. Nhưng **nguyên tắc không đổi**: trusted proxy boundary, HTTPS public origin, cookie flags, canonical redirect URI, issuer validation và CSRF/cross-site compatibility.

## 20. Kiểm thử cookie và HTTPS qua reverse proxy

Một test chỉ gọi controller trực tiếp ở localhost **không đủ**; cần end-to-end từ public domain qua proxy, đồng thời test filter/config trong ứng dụng.

### Bộ test quan trọng

| Case | Kỳ vọng |
|---|---|
| `https://login.example.test/login` | TLS certificate đúng hostname; không có mixed-content; page hợp lệ. |
| HTTP request công khai | Redirect theo policy tới canonical HTTPS; không lộ backend URL. |
| Login success qua edge | `Set-Cookie` có `Secure; HttpOnly` và `SameSite` đúng, Domain/Path phù hợp. |
| Cookie `__Host-SESSION` | Có Secure, Path=/, không Domain; browser chấp nhận. |
| Backend only sees HTTP | Request reconstructed scheme thành https nếu trusted strategy đúng. |
| Unknown `Host: attacker.test` | Edge reject hoặc route tới safe default, không phản chiếu vào absolute redirect. |
| Forged `X-Forwarded-Host: attacker.test` | Edge xóa/ghi đè; `Location` vẫn dùng allowed host. |
| Forged `Forwarded: proto=http;host=attacker.test` | Edge xóa; app không dùng giá trị giả. |
| Forged `X-Forwarded-For` | Audit/rate limiter không nhận IP do client tự bịa. |
| OAuth2 redirect | `redirect_uri` chính xác public HTTPS callback đã đăng ký. |
| OIDC callback top-level GET | Session correlation/`state` thành công với SameSite policy. |
| OIDC/SAML form POST callback | Cookie được gửi/chặn đúng chính sách đã thiết kế; không tự suy Lax đủ. |
| Callback với wrong state/nonce | Authentication bị từ chối; không tạo session mới. |
| User session expired | Cookie cũ không hồi sinh server-side session. |
| POST không có CSRF token | Bị từ chối theo chính sách web session. |
| Session cookie có SameSite=None nhưng không Secure | Browser có thể reject; test phải phát hiện. |
| Nhiều replicas | Cookie/session store hoạt động nhất quán, logout/revoke cross-node. |
| HSTS từ HTTPS | Header xuất hiện đúng ở public response, owner một nơi. |
| Path-prefix routing | `Location`, callback, cookie Path và backend handler đều chính xác. |
| Proxy upstream unavailable | Không redirect loop; lỗi được trả có kiểm soát, không lộ internal topology. |
| Access logs | Không chứa Cookie, Authorization, raw tokens/OTP, host poisoning strings. |

### Kiểm tra `curl` từ bên ngoài

~~~bash
# Kiểm TLS/headers trên edge. Không dùng -k ở production tests.
curl -I https://login.example.test/login

# Kiểm HTTP -> HTTPS; không tự động follow redirect:
curl -I http://login.example.test/login

# Gửi forged forwarded host để xác minh edge sanitize:
curl -I https://login.example.test/login \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'Forwarded: for=192.0.2.200;proto=http;host=attacker.example.test'
~~~

Các lệnh chỉ chạy khi hostname thuộc môi trường mà bạn được phép kiểm thử. Test không nên làm lộ cookie/token thật; dùng session test account và không dump Authorization headers trong CI log. Với `curl -I` (HEAD), không phải mọi login flow đều có handler HEAD giống GET/POST; muốn xem OAuth2 authorize redirect, dùng GET an toàn với test fixtures và cookie jar có quản lý.

Với `Set-Cookie`, dùng DevTools **Network/Application** xem lý do cookie bị reject: Domain mismatch, SameSite=None thiếu Secure, prefix `__Host-` không đủ điều kiện, HTTPS/HTTP mismatch hoặc browser storage policy. **Đọc header từ server không đủ để biết browser có lưu cookie thành công.**

## 21. Java 17 chạy độc lập: public origin đáng tin và cookie flags

Ví dụ sau **chạy bằng JDK 17 Standard Library**, không dùng Spring, minh họa hai điều:

1. Xây callback URL từ **canonical public origin**, không bị thay đổi bởi `Host`/`X-Forwarded-Host` do phía request giả mạo.
2. Tạo mẫu session cookie với `Secure; HttpOnly; SameSite=Lax; Path=/`, không `Domain`.

Chương trình chỉ là minh họa **origin policy và header format**; nó không phải HTTP server, reverse-proxy parser, cookie serializer production hoặc OAuth2 provider.

~~~java
import java.net.URI;

public class ProxyIdentitySafetyDemo {
    private static final URI PUBLIC_ORIGIN =
            URI.create("https://login.example.test");

    record IncomingRequest(
            String host, String forwardedHost, String forwardedProto) {}

    static String callback(IncomingRequest ignoredUntrustedRequest) {
        // Security-critical URL uses a configured, trusted origin.
        return PUBLIC_ORIGIN
                .resolve("/login/oauth2/code/corp")
                .toString();
    }

    static boolean allowedOrigin(String value) {
        try {
            URI uri = URI.create(value);
            String scheme = uri.getScheme();
            String host = uri.getHost();
            String path = uri.getRawPath();

            return scheme != null
                    && "https".equalsIgnoreCase(scheme)
                    && host != null
                    && "login.example.test".equalsIgnoreCase(host)
                    && uri.getPort() == -1
                    && uri.getRawUserInfo() == null
                    && uri.getRawQuery() == null
                    && uri.getRawFragment() == null
                    && (path == null || path.isEmpty()
                        || "/".equals(path));
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    static String sessionCookie(String demoValue) {
        if (!demoValue.matches("[A-Za-z0-9_-]{16,64}")) {
            throw new IllegalArgumentException("invalid demo value");
        }
        return "__Host-SESSION=" + demoValue
                + "; Path=/; Secure; HttpOnly; SameSite=Lax";
    }

    public static void main(String[] args) {
        IncomingRequest forged = new IncomingRequest(
                "attacker.example.test",
                "attacker.example.test",
                "http");

        System.out.println("callback: " + callback(forged));
        System.out.println("canonical origin allowed: "
                + allowedOrigin("https://login.example.test"));
        System.out.println("evil host allowed: "
                + allowedOrigin("https://login.example.test.evil.test"));
        System.out.println("http origin allowed: "
                + allowedOrigin("http://login.example.test"));

        String cookie = sessionCookie("demoSessionId_123456");
        System.out.println("cookie attributes: "
                + cookie.substring(cookie.indexOf(';') + 2));
    }
}
~~~

Lưu tên `ProxyIdentitySafetyDemo.java`, chạy trên JDK 17+:

~~~bash
javac ProxyIdentitySafetyDemo.java
java ProxyIdentitySafetyDemo
~~~

**Stdout chính xác:**

~~~text
callback: https://login.example.test/login/oauth2/code/corp
canonical origin allowed: true
evil host allowed: false
http origin allowed: false
cookie attributes: Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Dù record `IncomingRequest` chứa các giá trị giả mạo, callback không đổi vì public origin được cấu hình. `allowedOrigin` là validator tối thiểu minh họa cho **một root origin cố định**, không phải thư viện chuẩn hóa URL toàn diện: ứng dụng production cần contract cho port 443, IDNA/hostname normalization, tenant mapping, paths, suffix bypass, redirect URIs và URL encoding theo threat model.

`sessionCookie()` chỉ tạo mẫu header; **session ID demo không đủ mạnh để làm credential production**. Trong app thật, để Servlet container hoặc Spring Session tạo session IDs bằng CSPRNG và quản lý cookie/serialization. Không copy method này để thay authentication/session framework.

## 22. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xác minh / khắc phục |
|---|---|---|
| Login redirect sang `http://app-auth:8080` | Chưa áp forwarded proto/host hoặc proxy sai. | Xem `Location` qua edge, trusted headers và Boot strategy. |
| OAuth2 `redirect_uri_mismatch` | Callback URL sai scheme/host/port/prefix. | So chính xác URI trên authorize request với registration ở IdP. |
| SSO quay về rồi báo state not found | Session cookie không gửi ở callback, Path/SameSite sai, session store khác node. | DevTools Cookies, `SameSite` vs response mode, session repository. |
| Cookie bị browser bỏ | `Secure` thiếu, prefix `__Host-` sai Domain/Path, HTTP origin hoặc browser policy. | DevTools lý do cookie rejection. |
| HSTS vắng mặt | Backend nghĩ request HTTP hoặc edge không set; header config disabled. | Kiểm response thực qua HTTPS, forwarded strategy, owner HSTS. |
| Login redirect loop | Mismatch scheme/port, session cookie không được giữ, proxy redirect rules lặp. | Trace chuỗi `Location`, kiểm TLS edge và cookie. |
| CSRF `403` sau login | Cookie session/CSRF token không khớp, proxy path rewrite, cross-site POST. | Kiểm token repository, SameSite, method, POST origin. |
| Rate limit bị bypass | Tin `X-Forwarded-For` do client tự gửi. | Test forged IP qua edge, cấu hình trusted proxies. |
| Magic-link trỏ attacker host | Host-header/Forwarded host poisoning. | Kiểm canonical origin và request host validation. |
| App nhiều replica mất login | Session local, cookie serializer khác nhau, sticky sessions sai. | Dùng shared store/đúng topology và integration test. |
| Một subdomain đọc/chèn session cookie | `Domain` quá rộng hoặc subdomain compromise. | Dùng host-only/`__Host-` và isolate login origin. |
| Cookie vẫn còn sau logout | Sai name/Domain/Path ở delete hoặc server-side session chưa invalidate. | Đối chiếu Set-Cookie logout và session store. |
| CORS bật nhưng cookie không được gửi | Sai credentials mode/SameSite/Domain hoặc wildcard origin. | Browser network logs, explicit origins, CSRF plan. |
| External callback thiếu `/auth` | Proxy strip prefix, Boot không biết forwarded prefix. | So browser URL, backend URI và IdP callback. |
| Internal hostname lộ trong HTML/email | Self URL dựng từ internal request scheme/host. | Cấu hình canonical base URL và test absolute links. |

Khi chẩn đoán, hãy thu thập **an toàn**: scheme/host/port, route template, status, header names/flags, request ID và trace qua proxy; **không** log full session cookie, authorization code, access token, password hoặc OTP. Nếu cần reproducible test, dùng tài khoản/test tokens giả trong môi trường riêng.

## 23. Checklist đưa vào production

### Edge / mạng / TLS

- [ ] Public login origin chạy HTTPS với certificate hợp lệ; HTTP bị xử lý theo policy.
- [ ] Backend chỉ nhận kết nối từ trusted proxies/services; bảo vệ hop proxy→backend.
- [ ] Proxy biên strip/overwrite **cả `Forwarded` và `X-Forwarded-*`** từ client.
- [ ] Unknown Host/SNI bị reject hoặc đưa tới safe default, không đi vào auth app.
- [ ] Chuỗi CDN/LB/ingress có policy rõ ai được tin, ai đặt client IP, host, proto, port và prefix.
- [ ] Không log cookies, Authorization headers, raw recovery tokens hay sensitive query/body.
- [ ] HSTS owner và scope (`includeSubDomains`/`preload`) được phê duyệt.

### Spring Boot / Spring Security

- [ ] Chọn `server.forward-headers-strategy` theo topology: `none`, `native` hoặc `framework`.
- [ ] Nếu Tomcat TLS-terminating proxy có redirect context-root issue, kiểm tra `server.tomcat.redirect-context-root=false`.
- [ ] Không đăng ký trùng ForwardedHeaderFilter/RemoteIpValve mà thiếu lý do rõ.
- [ ] Security-critical absolute URLs dùng canonical origin hoặc validated allowlist.
- [ ] OIDC `redirect_uri` đúng public scheme/host/port/prefix; IdP issuer/audience vẫn được validate riêng.
- [ ] Security filter chain không bị bypass vì proxy path rewrite.
- [ ] Session cookie thực có Secure, HttpOnly, SameSite, Path/Domain theo policy.
- [ ] `__Host-` cookie không Domain, Path=/ và Secure; browser thực chấp nhận.
- [ ] Với Spring Session, CookieSerializer và session store config được kiểm tra trực tiếp.
- [ ] Session rotation, timeout, logout/revocation và MFA freshness không bị bỏ qua.

### Browser / federation / CSRF

- [ ] Test OIDC top-level GET và mọi form_post/SAML POST callback được hỗ trợ.
- [ ] SameSite=Lax/Strict/None được chọn theo request context, không theo thói quen.
- [ ] Session/CSRF cookies có chính sách khác nhau khi SPA cần đọc CSRF token.
- [ ] CSRF protection không bị disable blanket vì lỗi callback.
- [ ] CORS allowlist origin cụ thể nếu dùng credentials; không coi CORS là authentication.
- [ ] Cookie không bị chia rộng tới subdomain khác khi không cần.
- [ ] Login/recovery pages có CSP, Referrer-Policy và no-store phù hợp.

### Kiểm thử / giám sát

- [ ] Test forged Host, Forwarded và X-Forwarded-* qua **public edge**.
- [ ] Test redirect, session cookies, HSTS, OAuth2 callback, logout và nhiều replicas.
- [ ] Test rate-limit IP sau trusted proxy normalization; không tin IP client tự khai.
- [ ] Test host/prefix changes qua CDN/ingress và browser version khác nhau.
- [ ] Audit có correlation ID, policy version, outcome nhưng không lưu credential.
- [ ] Có runbook khôi phục khi cookie flags, proxy headers hoặc redirect URI thay đổi.

## 24. Kết luận

**Triển khai Spring Security sau reverse proxy an toàn đòi hỏi hai sự thật được phân tách đúng:** browser nói chuyện với **public HTTPS origin**, còn Spring Boot có thể ở backend HTTP và chỉ nên dùng **forwarded metadata do proxy đáng tin tạo ra**.

Ba nhóm kiểm soát phải đi cùng nhau:

1. **Trust boundary:** edge xác minh Host/SNI, loại bỏ header giả, đặt lại proto/host/port/IP và giới hạn backend ingress.
2. **Cookie/session:** `Secure`, `HttpOnly`, `SameSite`, host-only/`__Host-`, scope/Path đúng; server-side session revocation, CSRF và session store vẫn là các lớp riêng.
3. **Identity and redirects:** OIDC/OAuth2 callback, login/recovery links và mọi URL chứa credential phải dùng public HTTPS origin được kiểm soát; IdP issuer và identity claim không được suy từ proxy headers.

Một dòng `server.forward-headers-strategy=framework` có thể sửa redirect nhưng **không phải cơ chế xác thực proxy**. Cách làm đúng là xem **proxy, Spring Security, browser cookies và IdP** như một luồng tin cậy liên tục; kiểm thử từ Internet edge tới backend thay vì chỉ nhìn unit test của controller.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Embedded Web Servers / Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): forwarded headers, NATIVE/FRAMEWORK và Tomcat redirect context root.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `server.forward-headers-strategy` và Servlet/Reactive session cookie properties.
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): trust boundary, stripping, forwarded headers và removeOnly.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): HSTS, security headers và default behavior.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): client registration, authorization endpoint và redirect URI.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF trong web session flows.
- [Spring Session — API and CookieSerializer](https://docs.spring.io/spring-session/reference/api.html): Spring Session cookie serialization và multi-node sessions.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure, HttpOnly, SameSite, Domain, Path, cookie prefixes và Partitioned.
- [MDN — Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): cookie scope, security prefixes và browser behavior.
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security): HSTS scope, HTTPS và browser behavior.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html): syntax và semantics của `Forwarded`.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html): mô hình cookie nền tảng.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-final.html): issuer/redirect URI/state/nonce và ID Token semantics.
