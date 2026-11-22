# Thiết kế cookie và địa chỉ callback khi triển khai Spring Security Reactive sau reverse proxy

## 1. Mục tiêu

Khi triển khai ứng dụng **Spring WebFlux + Spring Security Reactive** sau reverse proxy, trình duyệt có thể truy cập `https://login.example.com` trong khi ứng dụng thực tế nhận request tại `http://127.0.0.1:8080`. Sự khác biệt về scheme, host, port và path làm hai phần của luồng đăng nhập dễ hỏng:

1. **Địa chỉ callback OAuth2/OIDC** được dựng thành HTTP nội bộ, sai hostname hoặc sai prefix so với URL đã đăng ký tại Identity Provider (IdP). Hệ quả: `redirect_uri_mismatch`, redirect loop, lỗi `invalid_state` hoặc lỗi đăng nhập gián đoạn.
2. **Cookie phiên** bị cấp với `Secure`, `Path`, `Domain` hoặc `SameSite` không phù hợp. Browser không lưu/gửi cookie khi quay lại callback; server không tìm thấy WebSession lưu yêu cầu OAuth2 trước đó.

Bài này hướng dẫn thiết kế **địa chỉ công khai, forwarded headers, callback, cookie WebSession, CSRF và kiểm thử đường đi thực tế**. Phạm vi là **Reactive/WebFlux**: dùng `WebSession`, `WebSessionIdResolver` và `SecurityWebFilterChain`; không áp các cấu hình chỉ dành cho Servlet như `server.servlet.session.cookie.*`, `CookieSerializer` của HttpSession, `HttpSecurity` hay `ForwardedHeaderFilter` để giải quyết WebFlux.

Sau bài học, cần có thể vẽ lại một lượt đăng nhập đầy đủ, xác định chính xác URL phía browser, cấu hình các phía tương ứng và kiểm tra bằng response headers lẫn trình duyệt thật.

## 2. Phân biệt ba góc nhìn địa chỉ

Xét triển khai không dùng path prefix:

| Thành phần | URL/địa chỉ | Vai trò |
| --- | --- | --- |
| Browser | `https://login.example.com` | Origin công khai, nơi cookie được lưu và callback quay về |
| Reverse proxy (TLS termination) | `login.example.com:443` | Nhận HTTPS, kiểm tra Host, loại header không tin cậy, chuyển tiếp |
| WebFlux upstream | `http://127.0.0.1:8080` | Nhận HTTP nội bộ; không được tự quảng bá URL này ra browser |
| IdP | `https://idp.example.net` | Xác thực người dùng rồi điều hướng browser về callback đã đăng ký |

Luồng chuẩn với registration ID `corporate`:

```text
(1) Browser GET https://login.example.com/oauth2/authorization/corporate
    -> Proxy -> WebFlux (đã nhận thông tin URL công khai qua forwarded headers)
(2) WebFlux lưu OAuth2AuthorizationRequest trong WebSession;
    gửi Set-Cookie cho origin https://login.example.com
    và 302 Location: https://idp.example.net/...?
                  redirect_uri=https%3A%2F%2Flogin.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate
                  &state=<giá trị ngẫu nhiên>
(3) Browser tới IdP; hoàn tất xác thực.
(4) IdP điều hướng browser về:
    GET https://login.example.com/login/oauth2/code/corporate?code=...&state=...
(5) Browser gửi cookie phiên hợp lệ; WebFlux tìm lại authorization request,
    xác minh state, trao đổi code lấy token, hoàn tất xác thực.
```

**Điểm mấu chốt:** `redirect_uri` trong request gửi IdP, endpoint mà Spring Security lắng nghe, URL được đăng ký tại IdP và cookie mà browser gửi khi callback phải khớp thành **một hợp đồng triển khai**. Giá trị `state` phải được đối chiếu với yêu cầu ban đầu; không giải quyết `invalid_state` bằng cách bỏ kiểm tra trạng thái.

## 3. Forwarded headers: khôi phục URL công khai, nhưng chỉ tin proxy

### 3.1. Ý nghĩa

Proxy có thể chuyển HTTP nội bộ và cung cấp thông tin ban đầu bằng `Forwarded` (chuẩn RFC 7239) hoặc nhóm `X-Forwarded-*`:

| Header | Ví dụ | Mục đích |
| --- | --- | --- |
| `X-Forwarded-Proto` | `https` | Scheme gốc tại browser |
| `X-Forwarded-Host` | `login.example.com` | Host công khai |
| `X-Forwarded-Port` | `443` | Port công khai |
| `X-Forwarded-Prefix` | `/portal` | Prefix public nếu proxy thay đổi đường dẫn |
| `X-Forwarded-For` | `203.0.113.10` | Chuỗi địa chỉ proxy/client, phục vụ logging/rule khi đã xác lập trust |
| `Forwarded` | `for=203.0.113.10;proto=https;host=login.example.com` | Dạng chuẩn thay thế nhóm X-Forwarded |

Khi Spring hiểu đúng những header này, việc dựng URL tự tham chiếu, redirect và `{baseUrl}` của OAuth2 có thể dùng scheme/host/port/path công khai.

Trong **Spring Boot 3.x với WebFlux**, cấu hình điển hình:

```yaml
server:
  forward-headers-strategy: framework
```

Ở reactive stack, chiến lược `FRAMEWORK` sử dụng `ForwardedHeaderTransformer`; đừng dùng Servlet `ForwardedHeaderFilter`. `NATIVE` có thể xử lý một phần header ở web server, nhưng khả năng xử lý prefix và cách diễn giải khác nhau giữa server; kiểm chứng thực tế nếu chọn phương án đó. Tránh đồng thời tự tạo transformer xử lý lại cùng header khi Boot đã cấu hình sẵn.

### 3.2. Ranh giới tin cậy là điều kiện bảo mật

Giả sử client tùy ý gửi:

```http
GET /oauth2/authorization/corporate HTTP/1.1
Host: login.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
Forwarded: host=attacker.example;proto=https
```

Nếu upstream tin mù quáng những header do Internet gửi tới, nó có thể xây `redirect_uri` hoặc URL tuyệt đối dùng host của kẻ tấn công. Vì thế:

- Proxy **đầu biên tin cậy** phải xóa/ghi đè mọi `Forwarded` và `X-Forwarded-*` đến từ client trước khi gửi upstream, kể cả khi ứng dụng dự định chỉ đọc một biến thể. Cấu hình nhiều hop phải xác định rõ hop nào được tin và ai chịu trách nhiệm chuẩn hóa.
- Upstream chỉ được truy cập từ proxy qua mạng riêng, firewall hoặc service policy; không mở port nội bộ ra Internet để client đi vòng.
- Proxy chỉ chấp nhận các `Host` hợp lệ; không phản chiếu host chưa được xác thực vào `X-Forwarded-Host`. Với callback đăng nhập, cân nhắc allowlist chính xác domain public.
- Không đặt `server.forward-headers-strategy: framework` trên một upstream public mà không có trust boundary. Bật xử lý header chỉ an toàn khi nguồn header được kiểm soát.

### 3.3. Nginx minh họa cho deployment không có prefix

Đoạn `location` dưới đây giả định TLS đã được cấu hình trong `server` chạy `listen 443 ssl` với `server_name login.example.com`, và Nginx là reverse proxy tin cậy ở biên. Đây là phần location, **không phải toàn bộ file Nginx có thể chạy độc lập**:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;

    # Đặt rõ public host/scheme sau khi proxy đã kiểm tra host.
    proxy_set_header Host login.example.com;
    proxy_set_header X-Forwarded-Host login.example.com;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;

    # Nginx là edge ở ví dụ này: không nhận chuỗi XFF do client tự khai.
    proxy_set_header X-Forwarded-For $remote_addr;

    # Loại bỏ biến thể khác do client có thể tự thêm.
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Prefix "";
}
```

Nếu TLS kết thúc tại load balancer trước Nginx, `https` ở dòng trên chỉ đúng khi **load balancer thực sự bảo đảm kết nối gốc là HTTPS**; phải thiết kế trust chain phù hợp và chặn truy cập HTTP sai đường, không lấy bừa `$http_x_forwarded_proto` từ Internet. Cấu hình thực còn phải có certificate, rule HTTP→HTTPS, rule Host không hợp lệ và giới hạn truy cập upstream.

## 4. Thiết kế callback OAuth2/OIDC

### 4.1. Endpoint mặc định

Spring Security Reactive dùng endpoint khởi tạo:

`GET /oauth2/authorization/{registrationId}`

Và callback mặc định:

`/login/oauth2/code/{registrationId}`

Mẫu `redirect-uri` mặc định cho OAuth2 Login là:

`{baseUrl}/login/oauth2/code/{registrationId}`

Trong ví dụ, `{baseUrl}` phải là `https://login.example.com`, không phải `http://127.0.0.1:8080`. Đăng ký chính xác tại IdP:

`https://login.example.com/login/oauth2/code/corporate`

`redirect_uri` là địa chỉ **IdP gửi code về**, khác với “trang chủ sau đăng nhập thành công” và khác với OAuth2 `authorization-uri`/`token-uri` của IdP. Đừng sửa `redirect_uri` chỉ để chuyển người dùng sang trang đích sau login; dùng success handler/saved request theo nhu cầu nghiệp vụ.

### 4.2. Cấu hình Spring Boot mẫu

Tệp `application.yml` (đoạn cấu hình ứng dụng WebFlux, ví dụ IdP có OIDC discovery hợp lệ):

```yaml
server:
  port: 8080
  forward-headers-strategy: framework

spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corporate:
            issuer-uri: https://idp.example.net/realms/corporate
```

`client-id` và `client-secret` ở đây là biến môi trường; không ghi secret thật vào YAML hoặc Git. `issuer-uri` phải thay bằng issuer thực do IdP công bố và phải khớp chính xác metadata/certificate thực tế. Chỉ thêm `openid` khi IdP hỗ trợ OIDC.

Lớp Security tối giản, độc lập với chi tiết IdP:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/actuator/health").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

`pathMatchers("/actuator/health")` chỉ là minh họa cho health endpoint nếu ứng dụng có Actuator; xác minh policy thực trước khi public route. Khi dùng session-cookie-based login, CSRF protection mặc định của Spring Security vẫn cần được duy trì cho request thay đổi trạng thái.

### 4.3. Nếu thực sự đổi đường dẫn callback

Ví dụ muốn callback `/auth/callback/{registrationId}` **bên trong ứng dụng**. Phải đổi **đồng bộ** cả matcher của OAuth2 Login và registration:

```java
.oauth2Login(oauth2 -> oauth2
    .authenticationMatcher(
        new PathPatternParserServerWebExchangeMatcher(
            "/auth/callback/{registrationId}")))
```

với import:

```java
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
```

và trong YAML:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
```

Sau đó đăng ký `https://login.example.com/auth/callback/corporate` tại IdP. Hai đoạn trên là **các thay đổi bổ sung trong cấu hình đã có**, không phải chương trình hoàn chỉnh. Nếu chỉ thay `redirect-uri` mà quên matcher, callback sẽ đến một đường dẫn Spring Security không xử lý như authorization response.

## 5. Chọn cookie WebSession an toàn cho trình duyệt

Cookie phiên WebFlux chứa **session ID**, không phải mặc định chứa toàn bộ `Authentication` hoặc token của IdP. Session data được quản lý phía server; khi triển khai nhiều instance cần lưu trữ/phân phối session phù hợp, chẳng hạn Spring Session Reactive với Redis, thay vì mặc định trông chờ mọi request quay về đúng một pod.

### 5.1. Thuộc tính cookie và tác dụng

| Thuộc tính | Khuyến nghị cho đăng nhập dạng top-level redirect GET | Vì sao |
| --- | --- | --- |
| `Secure` | `true` trên public HTTPS | Browser chỉ gửi cookie qua HTTPS; phải dựa trên public scheme |
| `HttpOnly` | `true` | JavaScript không đọc được session ID qua `document.cookie` |
| `SameSite` | Thường chọn `Lax`, xác minh luồng IdP cụ thể | Cho phép cookie với navigation top-level GET từ IdP quay lại; giảm nhiều trường hợp CSRF |
| `Path` | `/` khi ứng dụng ở root, hoặc public prefix hẹp hơn khi phù hợp | Browser chỉ gửi cookie đến path khớp; callback phải nằm trong scope |
| `Domain` | **Không đặt** nếu chỉ một host public | Host-only cookie, giảm rủi ro chia sẻ sang subdomain |
| `Max-Age`/`Expires` | Chọn theo vòng đời đăng nhập; có thể dùng session cookie | Thời gian giữ cookie khác timeout của session phía server |
| Cookie name | Chọn tên riêng, kiểm soát xung đột | Tránh ứng dụng khác trên cùng host ghi đè cookie |

`SameSite=Strict` thường làm cookie **không được gửi** khi người dùng điều hướng từ site IdP sang callback; OAuth2 có thể mất authorization request/state. `SameSite=Lax` phù hợp luồng redirect callback **GET top-level** thông thường. Với response mode callback **POST cross-site** (chẳng hạn OIDC `form_post`), `Lax` thường chặn cookie; `SameSite=None; Secure` có thể cần thiết nhưng yêu cầu thêm đánh giá CSRF, browser third-party-cookie policy và **khả năng tiếp nhận POST của integration cụ thể**. Không đổi sang `None` chỉ vì muốn khắc phục nhanh lỗi login.

**Tên `__Host-APP_SESSION`:** browser hỗ trợ cookie prefix sẽ yêu cầu `Secure`, `Path=/` và **không có `Domain`. Prefix này rất phù hợp ứng dụng root-path, một domain công khai. Với cookie `Path=/portal`, không dùng `__Host-` (do vi phạm `Path=/`); có thể chọn `__Secure-APP_SESSION` và vẫn bỏ `Domain`.

### 5.2. Java 17+: cấu hình cookie cho WebFlux

Tệp `src/main/java/example/security/SessionCookieConfig.java`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration(proxyBeanMethods = false)
public class SessionCookieConfig {

    @Bean
    public WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver = new CookieWebSessionIdResolver();
        resolver.setCookieName("__Host-APP_SESSION");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax"));
        return resolver;
    }
}
```

Đoạn này chạy trong Spring WebFlux khi có bean configuration được component scan hoặc import. Nó không yêu cầu `javax.servlet.http.Cookie`, `jakarta.servlet.http.HttpSession` hoặc Servlet cookie filter. **Môi trường local HTTP:** cookie `Secure` có thể khiến test qua `http://127.0.0.1` không giữ được phiên (chính sách localhost của browser khác nhau); sử dụng HTTPS local hoặc profile test riêng có kiểm soát, không bỏ `Secure` khỏi cấu hình production.

Response HTTPS kỳ vọng (giá trị ID chỉ minh họa):

```http
Set-Cookie: __Host-APP_SESSION=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Không thêm `Domain=.example.com` vì sẽ vi phạm quy tắc `__Host-` và mở rộng phạm vi cookie. `Secure`/**`HttpOnly`**/`SameSite` phải kiểm bằng **header được gửi cho browser**, không chỉ nhìn annotation Java.

### 5.3. Cookie phiên khác cookie CSRF

Spring Security Reactive mặc định lưu expected CSRF token trong `WebSession` qua `WebSessionServerCsrfTokenRepository`. Nếu frontend cần đọc CSRF token trong cookie để đưa vào header, có thể cấu hình `CookieServerCsrfTokenRepository`; lựa chọn `withHttpOnlyFalse()` cho cookie CSRF là **trường hợp riêng** để JavaScript đọc token, **không dùng cho cookie session ID**.

```java
// Chỉ là đoạn cấu hình khi frontend thực sự cần mô hình cookie CSRF.
.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
```

Cần import `org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository`. Không dùng `SameSite` như lớp bảo vệ CSRF duy nhất; luôn giữ đối chiếu token cho thao tác có side effect, xác định origin/cross-origin policy, và áp dụng state/nonce/PKCE khi giao thức cần. Cookie phiên `HttpOnly` không cản browser tự gửi cookie đến server.

## 6. Prefix công khai và quy tắc khớp Path

Một deployment khác có URL công khai `https://login.example.com/portal`, nhưng reverse proxy **cắt `/portal`** trước khi forward tới WebFlux root:

| Điểm đi qua | URL |
| --- | --- |
| Browser bắt đầu login | `https://login.example.com/portal/oauth2/authorization/corporate` |
| Proxy chuyển lên ứng dụng | `http://127.0.0.1:8080/oauth2/authorization/corporate` |
| Header của proxy | `X-Forwarded-Proto: https`, `X-Forwarded-Host: login.example.com`, `X-Forwarded-Prefix: /portal` |
| Callback public cần đăng ký | `https://login.example.com/portal/login/oauth2/code/corporate` |
| Path ứng dụng nhận sau proxy | `/login/oauth2/code/corporate` |

`{baseUrl}` phải phản ánh prefix công khai khi transformer và proxy nhất quán. Nếu app thực sự đã có base path `/portal` và proxy vẫn giữ path đó, **không vô tình cộng prefix hai lần** bằng cách vừa set base path vừa rewrite/forward prefix mà chưa kiểm test.

Nếu chọn cookie path `/portal`, browser gửi lại cookie cho `/portal/login/oauth2/code/corporate`, nhưng không cho `/login/oauth2/code/corporate`. Sự khác biệt là **browser xét URL công khai**, không biết đường dẫn upstream. Một cấu hình cookie hạn chế đường dẫn có thể dùng:

```java
// Chỉ thay bean WebSessionIdResolver ở mục 5; không khai báo bean thứ hai.
resolver.setCookieName("__Secure-APP_SESSION");
resolver.addCookieInitializer(cookie -> cookie
        .path("/portal")
        .secure(true)
        .httpOnly(true)
        .sameSite("Lax"));
```

Đây là ví dụ **thay thế** cho `__Host-APP_SESSION` khi cần `Path=/portal`, không dùng đồng thời cả hai tên. Nếu nhiều ứng dụng cùng host ở các prefix khác nhau, cân nhắc cookie name/path riêng để ngăn đụng session; host-only cookie không tự cách ly ứng dụng theo path nếu dùng `Path=/`.

## 7. Session phía server, nhiều replica và logout

WebSession có thể chứa thông tin phục vụ correlation của OAuth2 Authorization Code flow. Với nhiều instance sau load balancer:

- Sau bước 1, request callback có thể đến **replica khác**. Nếu session chỉ nằm trong memory của instance đầu tiên, callback thất bại dù cookie đúng và redirect URI đúng.
- Sử dụng Spring Session Reactive + kho session dùng chung khi yêu cầu đăng nhập không phụ thuộc stickiness; xác định TTL, encryption/network access, session serialization/versioning và cách thu hồi.
- Cookie là “vé tra cứu session”, không đảm bảo dữ liệu session tồn tại vĩnh viễn. `Max-Age` của cookie dài hơn TTL trên server sẽ dẫn đến cookie cũ nhưng session đã hết hạn.
- Sau logout, phải vô hiệu hóa session và xóa cookie tương ứng (cùng name, path, domain khi áp dụng); kiểm lại browser. Với OIDC logout, phân biệt local logout và IdP logout/callback hậu đăng xuất.
- Giảm rủi ro session fixation bằng việc dùng cơ chế quản lý session/authentication chuẩn và chính sách đổi session ID khi phù hợp với phiên bản/config thực tế; không tự tạo session ID từ tên người dùng hoặc lưu token nhạy cảm trong giá trị cookie.

Khi debug lỗi sau callback, luôn kiểm **cùng session ID đã được thiết lập và gửi lại hay chưa**, sau đó mới kiểm session store/state. Không log session ID nguyên văn, authorization code, ID token, access token, client secret hay cookie nguyên văn.

## 8. Chứng minh luồng đúng bằng test nhiều cấp

### 8.1. Kiểm đơn vị: forwarded URL và thuộc tính cookie

Ví dụ JUnit 5, Java 17+, chạy với Spring Boot 3.x/Spring Framework tương thích. Dùng đúng `SessionCookieConfig` ở mục 5 để test contract đã định. Tệp `src/test/java/example/security/ProxyCookieContractTest.java`:

```java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseCookie;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

import static org.junit.jupiter.api.Assertions.*;

class ProxyCookieContractTest {

    @Test
    void forwardedRequestCarriesPublicOrigin() {
        ServerHttpRequest upstream = MockServerHttpRequest
                .get("http://127.0.0.1:8080/oauth2/authorization/corporate")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "login.example.com")
                .header("X-Forwarded-Port", "443")
                .build();

        ServerHttpRequest publicView =
                new ForwardedHeaderTransformer().apply(upstream);

        assertEquals("https", publicView.getURI().getScheme());
        assertEquals("login.example.com", publicView.getURI().getHost());
        assertEquals("/oauth2/authorization/corporate",
                publicView.getURI().getPath());
        assertFalse(publicView.getHeaders().containsKey("X-Forwarded-Host"));
    }

    @Test
    void webSessionCookieHasRequiredBrowserAttributes() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("https://login.example.com/").build());

        new SessionCookieConfig().webSessionIdResolver()
                .setSessionId(exchange, "test-opaque-id");

        ResponseCookie cookie = exchange.getResponse().getCookies()
                .getFirst("__Host-APP_SESSION");

        assertNotNull(cookie);
        assertTrue(cookie.isSecure());
        assertTrue(cookie.isHttpOnly());
        assertEquals("Lax", cookie.getSameSite());
        assertEquals("/", cookie.getPath());
        assertNull(cookie.getDomain());
    }
}
```

Đây là test **unit** xác nhận transformer và cookie resolver xử lý input dự định; nó **không thể chứng minh** Nginx đã loại header giả mạo hoặc IdP đã chấp nhận callback. `ForwardedHeaderTransformer()` không tự xác thực nguồn header: trust boundary vẫn thuộc proxy/network. Trên phiên bản Spring Framework mới hơn có thay đổi constructor/chế độ chọn biến thể header; cần đối chiếu Javadoc ứng với phiên bản build.

Dependencies Gradle Groovy điển hình, ghép vào build đã có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Chạy:

```bash
./gradlew test --tests 'example.security.ProxyCookieContractTest'
```

Trên Windows dùng `gradlew.bat`. Các test unit dự kiến **PASS**, nhưng không có stdout ứng dụng bắt buộc; test sẽ thất bại nếu thuộc tính/URL không khớp. Cấu hình issuer/secret thật chỉ cần cho integration chạy ứng dụng, không cần cho phép thử unit nói trên.

### 8.2. Kiểm bằng HTTP từ bên ngoài proxy

Từ máy có thể truy cập HTTPS và DNS công khai, dùng GET để xem redirect mà **không tự động đi theo**:

```bash
curl -sS -D - -o /dev/null \
  https://login.example.com/oauth2/authorization/corporate
```

Tùy cấu hình, phản hồi thường là 302 đến IdP. Kiểm:

1. `Location` dẫn tới đúng authorization endpoint của IdP và có `redirect_uri` sau giải mã chính xác là `https://login.example.com/login/oauth2/code/corporate`. Không chứa `localhost`, `127.0.0.1`, HTTP nội bộ, port `8080` hoặc path sai.
2. `Set-Cookie` khi ứng dụng tạo session có tên/path/`Secure`/`HttpOnly`/`SameSite` dự kiến. Không giả định mọi response đều luôn cấp cookie; theo dõi response thực tạo phiên.
3. Thử browser thật trong luồng login; DevTools → Network/Cookies xem cookie có được **chấp nhận** khi `Set-Cookie` được phát ra và có được **gửi lại** ở request callback. Ghi lại lý do browser chặn cookie (wrong path, SameSite, Secure, blocked third-party cookie).
4. Callback thành công và landing page xác thực đúng user. Dùng hai browser profile độc lập để phát hiện session/cookie scope collision.
5. Nếu có nhiều replica, lặp lại login khi callback đi sang replica khác; xác nhận session store dùng chung, TTL và invalidation.

Đặc biệt, `curl` **không mô phỏng đầy đủ chính sách cookie/redirect cross-site của browser**. Không dùng việc `curl` thành công để khẳng định `SameSite=Strict` không gây lỗi.

### 8.3. Test an ninh với forwarded headers giả

Tạo request đi vào **public proxy**, cố ý thêm `X-Forwarded-Host: attacker.invalid` và `Forwarded: host=attacker.invalid;proto=http`. Kỳ vọng ứng dụng vẫn tạo redirect URI về domain đã cho phép, hoặc proxy từ chối request; không bao giờ tạo callback tới attacker. Chỉ tiến hành trên môi trường có quyền kiểm thử, không gửi dữ liệu OAuth2 thật sang hostname ngoài allowlist. Nếu upstream có thể truy cập trực tiếp, kiểm quy tắc mạng chặn điều đó trước khi chạy kiểm thử.

## 9. Bộ tình huống cần xác nhận trước production

| Tình huống | Kỳ vọng quan sát |
| --- | --- |
| HTTPS public → HTTP upstream | `Location`/`redirect_uri` dùng HTTPS public; cookie phiên có `Secure` |
| Callback cross-site GET từ IdP | Cookie `SameSite=Lax` vẫn gửi trong điều hướng top-level; `state` khớp |
| Callback cross-site POST / `form_post` | Thiết kế riêng: browser cookie policy + khả năng Spring Security tiếp nhận POST + CSRF/state |
| Public path `/portal` bị proxy strip | `redirect_uri` chứa `/portal` đúng một lần; cookie `Path` chứa callback public |
| Hai host public khác nhau | Mỗi host có callback đã đăng ký; cookie mặc định host-only, không rò sang host khác |
| Hai ứng dụng cùng một host | Cookie name/path không xung đột; không lấy nhầm phiên |
| Hai replica | Callback qua replica khác vẫn đọc được authorization request nếu dùng session store chung |
| Header do client giả mạo | Proxy loại hoặc ghi đè, URL dựng ra không bị attacker kiểm soát |
| Session hết hạn giữa chừng | Login fail có kiểm soát, không bypass `state` hoặc tạo authenticated session không hợp lệ |
| Logout sau login | Session bị hủy và cookie không thể truy cập tài nguyên cũ |
| CORS/cross-origin SPA | Cookie `SameSite`, `Secure`, credentials và CORS policy nhất quán; CSRF vẫn được áp dụng |
| Refresh/relogin | Không sinh redirect loop; session lifecycle/callback vẫn ổn định |

Với SPA gọi API bằng cross-origin `fetch`, `credentials: "include"` cùng CORS `Access-Control-Allow-Credentials` và danh sách origin cụ thể có thể cần thiết; nhưng **cross-origin** và **cross-site** là hai khái niệm khác nhau. Không dùng `Access-Control-Allow-Origin: *` với credentials. Đây là bài toán tách khỏi redirect top-level của OAuth2.

## 10. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân nên kiểm tra đầu tiên | Cách sửa đúng hướng |
| --- | --- | --- |
| IdP báo `redirect_uri_mismatch` | Wrong scheme/host/port/prefix; URI đăng ký chưa khớp | Xác nhận `Location`/`redirect_uri` sau giải mã và sửa proxy/registration đồng bộ |
| Redirect quay về `http://127.0.0.1:8080` | Upstream chưa xử lý forwarded headers | Kiểm proxy gửi header đúng, `forward-headers-strategy` và trust boundary |
| `invalid_state` hoặc callback login lại | Browser không gửi cookie / session mất / nhiều replica khác store | Kiểm `Set-Cookie`, Request Cookie, SameSite, Path, TTL và session store |
| Cookie xuất hiện trong header nhưng browser không lưu | `Secure` trên HTTP không phù hợp, `__Host-` sai Path/Domain, policy browser | Kiểm DevTools blocked reason, cấu hình HTTPS và cookie attributes |
| Chỉ lỗi khi có `/portal` | Mismatch prefix, double prefix, cookie path hoặc IdP redirect URI | Vẽ mapping public ↔ upstream cho cả start và callback; chỉnh đúng một lần |
| Đăng nhập xong lại chuyển vòng về IdP | Cookie phiên không tồn tại sau redirect hoặc security state không được lưu | So sánh cookie sent/received và kiểm response chain/session ID |
| Đăng nhập ở app B làm mất phiên app A | Hai app dùng cookie cùng tên, path/domain chồng lấn | Đặt tên riêng/Path phù hợp hoặc tách host |
| Chỉ lỗi khi scale nhiều pod | WebSession lưu cục bộ | Dùng Spring Session Reactive + session store chia sẻ, kiểm rollout |

Đừng sửa bằng cách **bỏ kiểm tra `state`, tắt CSRF, đặt `SameSite=None` cho mọi cookie, dùng `Domain=.example.com` vô điều kiện hoặc tin mọi forwarded header**. Những thay đổi này có thể che giấu lỗi cấu hình mà mở rộng rủi ro bảo mật.

## 11. Checklist triển khai và tiêu chí nghiệm thu

- [ ] Ghi rõ **public scheme/host/port/path** và internal scheme/host/port/path của mỗi route.
- [ ] Reverse proxy có allowlist Host, TLS, firewall upstream và cơ chế loại/ghi đè cả `Forwarded` và `X-Forwarded-*` từ client.
- [ ] Spring WebFlux đã xử lý forwarded headers theo phiên bản framework; không dùng nhầm Servlet filter.
- [ ] `redirect-uri` của client và callback listener khớp hoàn toàn với URL đăng ký ở IdP, bao gồm prefix và registrationId.
- [ ] Cookie phiên được kiểm từ response thực tế: `Secure`, `HttpOnly`, `SameSite`, `Path`, không có `Domain` ngoài chủ đích.
- [ ] Browser gửi lại cookie tại OAuth2 callback trong response mode thực tế; `state`/nonce/PKCE và session correlation vẫn được xác minh.
- [ ] CSRF protection cho request thay đổi trạng thái vẫn bật; phân biệt CSRF token cookie và session cookie.
- [ ] Các replica chia sẻ session nếu deployment cần; kiểm TTL, logout, cookie clearing, rollover.
- [ ] Test unit, test qua public proxy, test browser, test giả forwarded host và test nhiều replica đều có kết quả mong đợi.
- [ ] Log đủ request ID, URL public đã chuẩn hóa và lý do authentication failure đã lọc thông tin nhạy cảm; không log mã `code`, token, cookie, client secret hoặc session ID nguyên văn.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.configure-behind-a-proxy).
- [Spring Security Reactive — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html).
- [Spring Security Reactive — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html).
- [Spring Security Reactive — OAuth2 Client Authorization Grants / Authorization Request Repository](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html).
- [Spring Security Reactive — CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html).
- [Spring Session — WebFlux Custom Cookie](https://docs.spring.io/spring-session/reference/3.2/guides/boot-webflux-custom-cookie.html) và [WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html).
- [Spring Framework — CookieWebSessionIdResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html).
- [MDN — Set-Cookie, SameSite, Secure, HttpOnly và cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).
