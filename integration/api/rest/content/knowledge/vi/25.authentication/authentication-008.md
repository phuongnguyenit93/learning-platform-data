# Session cookie, stateless và lựa chọn quản lý phiên

Một nền tảng có web, mobile và API đối tác. Browser tự gửi cookie, mobile dùng bearer token, backend có service identity. Mỗi mô hình có yêu cầu khác nhau về **CSRF, logout, revocation và scale**. Chọn stateless chỉ vì “dễ scale” có thể bỏ sót thu hồi token; dùng cookie mà tắt CSRF cũng nguy hiểm.

Bài thuộc chương **Xác thực** của **INTEGRATION_API_REST**, kết hợp quản lý phiên với REST HTTP, Java/Spring Security, phân quyền, xử lý lỗi và kiểm thử.

## 1. Mục tiêu và khái niệm nền tảng

Sau bài này, bạn có thể:

1. Phân biệt **authentication**, **authorization**, **session**, **cookie**, **bearer token** và **stateless request handling**.
2. Thiết kế luồng **Set-Cookie → Cookie → session lookup → logout**, hiểu thuộc tính **Secure, HttpOnly, SameSite, Path, Domain, Max-Age**.
3. So sánh session tại server với **JWT access token tự xác minh**, **opaque token/introspection** và mô hình **BFF (Backend for Frontend)**.
4. Đánh giá **CSRF, XSS, session fixation, hijacking, replay, token theft, logout và revocation** theo từng phương án.
5. Cấu hình **Spring Security 6 / Spring Boot 3** cho REST API dùng session và API dùng bearer JWT, không trộn chính sách tùy tiện.
6. Quyết định cách scale, quản lý TTL, đổi quyền, rotate/thu hồi credential, đồng thời kiểm thử HTTP/security và tình huống lỗi.

**Xác thực** xác minh danh tính; **phân quyền** kiểm soát thao tác/resource. **Session** là trạng thái một lần đăng nhập; **cookie** là cơ chế browser lưu/gửi giá trị, có thể là session ID hoặc token.

**Stateless** nghĩa là không phải tra session login cho mỗi request, **không xóa** nhu cầu lưu resource, rate limit, refresh token, revocation hay quyền trong DB.

## 2. Quyết định trước khi chọn framework

| Tiêu chí | Cookie session phía server | Bearer JWT tự xác minh | Opaque bearer token |
|---|---|---|---|
| Credential trong request | Cookie chứa session ID | Authorization: Bearer JWT | Authorization: Bearer chuỗi opaque |
| Dữ liệu đăng nhập chủ yếu ở đâu? | Session store trên server | Claims trong token đã ký | Authorization server/store, kiểm qua introspection |
| Kiểm tra mỗi request | Lookup session + policy | Chữ ký, issuer, audience, time, scopes + policy | Gọi introspection hoặc cache kết quả có TTL |
| Thu hồi một login | Thường xóa/invalidate session | Khó thu hồi tức thì nếu chỉ tự xác minh | Thu hồi tại server cấp token, phụ thuộc cache |
| Mở rộng nhiều instance | Shared session store hoặc định tuyến phù hợp | Verify cục bộ, quản lý key | Availability/introspection cache |
| CSRF khi browser | Cần phòng vì cookie tự gửi | Bearer trong Authorization thường không tự gắn; xem lưu trữ | Tương tự bearer, trừ khi đặt opaque token trong cookie |
| Rủi ro trộm credential | Session hijacking | Token replay đến hết hiệu lực | Token replay trước khi hết hạn/thu hồi |
| Điểm mạnh | Logout/revocation rõ; phù hợp web | Ít session lookup; thích hợp API/mobile/service | Thu hồi trung tâm; có thể ẩn claims |
| Chi phí | Session store/expiry/CSRF | Quản lý khóa, TTL, revocation và token leak | Introspection latency/cache/availability |

Web same-origin cần logout nhanh thường hợp cookie session/BFF; mobile/đối tác thường dùng OAuth2/OIDC bearer token; service-to-service dùng client credentials/mTLS. **Cookie người dùng không phải service identity**.

### 2.1. Sơ đồ hai hướng xác thực

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant API as Spring API
    participant S as Session store
    participant AS as Authorization server
    B->>API: POST /login + credential + CSRF (khi cần)
    API->>S: Tạo/rotate session ID
    API-->>B: Set-Cookie: __Host-session=...; Secure; HttpOnly
    B->>API: GET /v1/me + Cookie
    API->>S: Resolve session
    API-->>B: 200 / 401
    Note over B,API: Hướng khác: client API gửi Authorization Bearer
    B->>AS: OAuth2/OIDC authorization flow
    AS-->>B: Access token qua client phù hợp
    B->>API: GET /v1/me + Authorization: Bearer ...
    API->>API: Validate token, quyền và tài nguyên
    API-->>B: 200 / 401 / 403
~~~

Không tự triển khai OAuth2 login trong SPA; cân nhắc **Authorization Code + PKCE** hoặc BFF giữ token ở backend.

## 3. HTTP cookie session: request có trạng thái ở server

### 3.1. Login tạo session ID thay vì nhét hồ sơ vào cookie

Một phiên đăng nhập dựa trên form hoặc endpoint được bảo vệ hợp lệ có thể tạo session trên server rồi gửi:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=s_very_random_opaque; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Content-Type: application/json

{"authenticated":true}
~~~

~~~http
GET /v1/me HTTP/1.1
Host: api.example.test
Cookie: __Host-session=s_very_random_opaque
Accept: application/json
~~~

Server tra session ID để lấy security context, rồi kiểm tra quyền. Cookie nên chứa **ID ngẫu nhiên có entropy cao**, không chứa mật khẩu/PII; **không đưa session ID vào URL/query**.

Prefix **__Host-** cần **Secure, Path=/, không Domain**. Servlet thường dùng **JSESSIONID**; đổi tên phải cấu hình, không chỉ đổi ví dụ.

### 3.2. Các thuộc tính cookie không thay nhau

| Thuộc tính | Tác dụng | Điều không bảo đảm |
|---|---|---|
| **Secure** | Browser chỉ gửi qua HTTPS (với ngoại lệ đặc thù môi trường) | Không chống XSS, CSRF hay server leak |
| **HttpOnly** | JavaScript không đọc cookie qua document.cookie | XSS vẫn có thể gửi request bằng browser |
| **SameSite=Strict** | Hạn chế gửi trong ngữ cảnh cross-site mạnh hơn | Có thể ảnh hưởng luồng chuyển trang/OIDC |
| **SameSite=Lax** | Giảm một số CSRF, thường giữ điều hướng top-level an toàn | Không thay token CSRF cho thao tác đổi trạng thái |
| **SameSite=None** | Cho phép gửi cross-site khi đủ điều kiện | Cần Secure, tăng nhu cầu chống CSRF/chính sách third-party cookies |
| **Path** | Giới hạn đường dẫn gửi cookie | Không tạo ranh giới phân quyền an toàn |
| **Domain** | Quy định host/subdomain nhận cookie | Mở rộng phạm vi có thể tăng rủi ro subdomain |
| **Max-Age/Expires** | Thời gian browser giữ cookie | Không tự xóa session ở server hoặc hủy token |

**SameSite khác same-origin**; origin khác nhau cùng site vẫn cần phân tích CORS/CSRF. Cross-site SSO/iframe cần kiểm thử browser và third-party-cookie policy.

### 3.3. Cookie gửi tự động: nguồn gốc rủi ro CSRF

Vì browser tự đính cookie, trang khác có thể kích hoạt thao tác ghi nếu thiếu CSRF protection. **POST /v1/payments** không an toàn chỉ nhờ cookie.

Các lớp bảo vệ: **CSRF token**, SameSite, Origin/Referer, Fetch Metadata, GET/HEAD an toàn và CORS. Chọn theo mô hình browser/client thực tế.

**CORS không thay CSRF**: browser có thể gửi request dù script không được đọc response.

## 4. Vòng đời server-side session

### 4.1. Tạo phiên, thay ID và hết hạn

Một session cần mô hình vòng đời rõ ràng:

~~~text
ANONYMOUS -> AUTHENTICATED -> ACTIVE
                       |-> IDLE_EXPIRED
                       |-> ABSOLUTE_EXPIRED
                       |-> REVOKED (logout/admin)
                       |-> REPLACED (session rotation)
~~~

- **Session fixation:** đổi ID sau login/nâng mức xác thực.
- **Idle vs absolute timeout:** giới hạn cả thời gian nhàn rỗi và tuổi phiên tối đa nếu cần.
- **Logout:** invalidate server session/security context và xóa cookie; xóa cookie **chưa thu hồi** ID bị đánh cắp.
- **Concurrent sessions:** giới hạn thiết bị/phiên và hỗ trợ logout từng phiên/toàn bộ.
- **Đổi mật khẩu, khóa tài khoản, thay vai trò:** hủy hoặc kiểm tra lại quyền trong phiên.

Session ID là **bearer credential**; không log nó. Login cần chống credential stuffing bằng rate limit, xác thực tăng cường và audit an toàn.

### 4.2. Stateful không đồng nghĩa dữ liệu người dùng nằm trong RAM một node

Khi có nhiều replica, session RAM cục bộ dễ mất hiệu lực khi request sang node khác. Có thể dùng:

- **Shared store** Redis/Spring Session với TTL, HA và serializer phù hợp.
- **Sticky sessions** nhưng cần failover, không thay revocation/độ bền.
- **Stateless token** nếu phù hợp client và giới hạn thu hồi.

Shared store là dependency: outage Redis có thể khiến session lookup thất bại. Đo lookup latency, TTL, active sessions và lỗi; không dùng session ID làm metric label.

## 5. Spring Security: cấu hình REST/web dùng session cookie

Ví dụ **Spring Boot 3 / Security 6 / Java 17** cho **form login stateful**, không phải endpoint JSON. Spring Security mặc định dùng trang đăng nhập và redirect; cần identity store thật.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SessionSecurityConfig {
    @Bean
    SecurityFilterChain sessionChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health").permitAll()
                    .requestMatchers("/web/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                    .sessionFixation(fixation ->
                            fixation.changeSessionId()))
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                    .logoutUrl("/logout")
                    .invalidateHttpSession(true)
                    .clearAuthentication(true)
                    .deleteCookies("__Host-session"));
        return http.build();
    }
}
~~~

**IF_REQUIRED** tạo session khi cần; **changeSessionId()** chống fixation. **CSRF vẫn bật**; logout dùng POST + CSRF, không GET đổi trạng thái.

Form login mặc định dùng **302 redirect**. API muốn 401 JSON hoặc POST JSON session phải cấu hình **AuthenticationEntryPoint/SuccessHandler** và đúng **SecurityContextRepository, rotation, CSRF**; không chỉ lưu username vào HttpSession.

### 5.1. Thiết lập cookie trong Spring Boot

~~~properties
server.servlet.session.cookie.name=__Host-session
server.servlet.session.cookie.path=/
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=20m
~~~

Giả định public **HTTPS**, không đặt cookie Domain theo prefix **__Host-**. Kiểm thử qua TLS-terminating proxy; cấu hình forwarded headers/trust chain phải đúng.

**20 phút** là idle timeout, không phải absolute expiry. Spring Session Redis cần TTL/serializer/namespace đồng nhất; response tài khoản nên **Cache-Control: no-store**.

### 5.2. Kiểm tra quyền ở method và resource

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderReader {
    private final OrderRepository orders;

    public OrderReader(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('orders:read')")
    public OrderView findVisibleOrder(String orderId, Actor actor) {
        return orders.findByIdAndTenantIdAndOwnerId(
                    orderId, actor.tenantId(), actor.userId())
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Mẫu cần **@EnableMethodSecurity**, repository/DTO/Actor và principal resolver. Authority kiểm tra chức năng, query theo tenant/owner chống **BOLA/IDOR**; vai trò thay đổi cần cập nhật quyền hoặc invalidate session.

## 6. CSRF, session fixation và các nhầm lẫn bảo mật phổ biến

### 6.1. Vì sao HttpOnly + SameSite chưa đủ cho write API?

**HttpOnly** không ngăn XSS gửi request cùng origin. **SameSite** không chặn mọi kịch bản same-site khác origin; cookie-backed POST/PUT/PATCH/DELETE cần CSRF protection.

Một mô hình phổ biến: server tạo **CSRF token gắn với session**; form hoặc SPA gửi giá trị đó trong body/header; server xác minh token cho phương thức không an toàn. Ví dụ:

~~~http
POST /v1/profile HTTP/1.1
Host: app.example.test
Cookie: __Host-session=s_opaque
Content-Type: application/json
X-CSRF-TOKEN: token-issued-for-this-session

{"displayName":"An"}
~~~

Với SPA, có thể cung cấp CSRF token qua endpoint GET cùng origin (sau xác thực hoặc theo thiết kế token), rồi giữ trong bộ nhớ client và gửi header. Nếu dùng **CookieCsrfTokenRepository.withHttpOnlyFalse()** cho SPA, token trong cookie sẽ đọc được bằng JavaScript theo thiết kế **nhưng session cookie vẫn phải HttpOnly**; cần tính đến Spring Security 6 **deferred CSRF token/BREACH masking** và cấu hình request handler tương thích, không chỉ copy một snippet. Một **XSS** nghiêm trọng vẫn có thể đọc CSRF token và thực hiện tác vụ trong quyền nạn nhân, nên **output encoding, CSP và XSS prevention** vẫn bắt buộc.

**Origin/Referer validation** là lớp hỗ trợ, cần chính sách rõ về request thiếu header và proxy. **Content-Type: application/json** hoặc CORS preflight không được xem là chống CSRF tuyệt đối khi cùng ứng dụng có các endpoint/cơ chế gửi khác.

### 6.2. Một số phản ví dụ cần tránh

| Sai lầm | Vì sao sai | Cách đúng |
|---|---|---|
| “Cookie có HttpOnly nên không có CSRF” | Browser vẫn tự gửi cookie | CSRF token + SameSite + kiểm tra origin |
| “CORS chặn mọi request từ website xấu” | CORS chủ yếu điều khiển quyền đọc response của script | Đánh giá request thực, không tắt CSRF |
| “Đã logout bằng xóa cookie thì token cũ chết” | Session tại server có thể còn | Invalidate server session và cookie |
| “Cookie Secure chống XSS” | Secure chỉ giới hạn đường truyền | CSP, sanitize/output encoding, authz |
| “Không đưa session ID vào response JSON thì không ai lấy được” | Cookie có thể bị lấy qua malware, proxy/log lỗi | HTTPS, HttpOnly, hạn TTL, tránh log |
| “Session ID khó đoán nên không cần kiểm tra owner” | Caller hợp lệ vẫn có thể đoán resource ID khác | Kiểm tra quyền từng tài nguyên |

### 6.3. Cross-origin request có cookie

Nếu frontend khác origin gọi API cookie-based và muốn browser gửi cookie, **fetch** có thể cần cấu hình **credentials: include**. Server phải trả CORS cho **origin cụ thể được phép** cùng **Access-Control-Allow-Credentials: true**, không kết hợp wildcard Allow-Origin với credentials. Cần kiểm soát CSRF, SameSite và third-party-cookie policies độc lập; không phải mọi browser đều gửi cookie cross-site theo ý ứng dụng.

Ở kiến trúc có thể chọn **BFF same-origin**, frontend chỉ gọi backend cùng origin; BFF dùng session cookie bảo vệ browser và giữ OAuth access/refresh token ở server. Mô hình này giảm việc JavaScript trực tiếp giữ bearer token, nhưng **không loại bỏ** CSRF, XSS hay nhu cầu kiểm tra quyền ở BFF và API phía sau.

## 7. Stateless bearer access token trong REST API

Một API mobile/đối tác thường nhận OAuth2 access token:

~~~http
GET /v1/orders/o-918 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...redacted...
Accept: application/json
~~~

Server không cần tra **HTTP session đăng nhập**, nhưng phải validate token: **signature/key**, thuật toán chấp nhận, **issuer**, **audience**, **exp/nbf**, scopes và các policy cần thiết. Không tin nội dung JWT chỉ vì base64 decode được; JWT **có chữ ký không đồng nghĩa được mã hóa**, nên không đặt PII hoặc secret trong claims.

### 7.1. Spring Security OAuth2 Resource Server

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class StatelessApiSecurity {
    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session ->
                    session.sessionCreationPolicy(
                            SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable());
        return http.build();
    }
}
~~~

Ví dụ này là cấu hình **cho một API riêng chỉ nhận bearer token qua Authorization**, không nhận cookie-based authentication để ghi dữ liệu, không dùng browser session. **Chỉ trong tiền đề đó** mới có thể tắt CSRF có chủ đích; nếu một endpoint vẫn nhận cookie tự gửi, cần đánh giá CSRF riêng. Nên có exception handling để API trả **401/403 + Problem Details** nhất quán, thay vì dựa vào HTML redirect login.

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.test/realms/shop
~~~

Issuer discovery/JWKS cần TLS, availability, cache key và cấu hình đúng nhà phát hành. **Bắt buộc kiểm tra audience** cho API đích bằng validator tương ứng (ngoài các kiểm tra chuẩn của issuer/resource server, tùy cấu hình/phiên bản); không mặc nhiên một token ký đúng bởi issuer là token được cấp cho service này. Cần thu hẹp thuật toán/nguồn key tin cậy, không chấp nhận algorithm do attacker tự chọn hoặc ký JWT bằng shared secret hardcoded trong source.

### 7.2. 401, 403 và trạng thái phiên

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Nếu token không có, hết hạn, sai chữ ký, sai issuer/audience hoặc bị từ chối, API có thể trả **401** với **WWW-Authenticate** thích hợp. Token hợp lệ nhưng thiếu quyền thường là **403 Forbidden**; scope không đủ có thể được diễn đạt qua Bearer challenge theo chuẩn áp dụng. Đừng phản chiếu lý do quá chi tiết như danh sách user, trạng thái tài khoản riêng hoặc raw token vào response.

**Session cookie API không nhất thiết phát Bearer challenge**; form-login mặc định có thể redirect **302** đến trang đăng nhập, trong khi REST API thường muốn **401 JSON**. Đây là quyết định hợp đồng theo **kiểu client**, không đơn giản là “Spring trả gì mặc định”.

### 7.3. Có JWT vẫn phải kiểm tra quyền theo tài nguyên

~~~java
@GetMapping("/v1/orders/{id}")
public ResponseEntity<OrderView> get(
        @PathVariable String id,
        @AuthenticationPrincipal Jwt jwt) {
    String tenant = tenantResolver.resolveValidated(jwt);
    String user = subjectResolver.resolveValidated(jwt);
    OrderView view = orderService.findVisible(tenant, user, id);
    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(view);
}
~~~

Đoạn controller minh họa cần imports, validator/resolvers và service cụ thể; **claims tenant/user phải được xác thực nguồn phát hành và semantics**, không lấy tenant từ query string. **SCOPE_orders:read** chỉ cấp quyền gọi loại operation; service phải lọc **tenant, chủ sở hữu và trạng thái** của đơn. Không xem “bearer token valid” là cho phép mọi order ID.

## 8. Logout, refresh token và thu hồi quyền trong hệ stateless

Một JWT access token tự xác minh thường còn hợp lệ tới **exp** nếu chữ ký/claims đúng. Xóa token trên thiết bị **không bắt buộc vô hiệu hóa bản sao đã bị đánh cắp**. “Logout” của client và “revocation có hiệu lực ở mọi API node” là hai yêu cầu khác nhau.

| Giải pháp | Hiệu lực thu hồi | Đổi lại |
|---|---|---|
| Access token **TTL ngắn** | Giới hạn cửa sổ replay, chưa thu hồi tức thời | Refresh thường xuyên hơn, clock skew |
| **Denylist** theo jti/token hash | Có thể chặn trước exp khi mọi node tra danh sách | Lưu/tra trạng thái, availability và TTL |
| **Token version** / session epoch theo user | Chặn token cũ sau khi đổi version nếu API kiểm tra | DB/cache lookup; không còn stateless hoàn toàn |
| **Opaque token + introspection** | Authorization server có thể đánh dấu inactive | Độ trễ, cache và dependency |
| **Key rotation** | Cần cho vòng đời khóa và sự cố phạm vi rộng | Có thể vô hiệu hóa nhiều token; rollout phức tạp |
| **Giữ credential tại BFF** | Browser chỉ có session cookie, backend kiểm soát refresh | BFF/session store là stateful |

**Refresh token** có tuổi thọ dài hơn access token và thường phải được giữ an toàn ở client phù hợp, có chính sách **rotation/reuse detection** và thu hồi theo thiết bị. Với public client/native app, dùng OAuth2/OIDC flow phù hợp cùng system browser/secure storage; không tự phát refresh token bằng một endpoint không kiểm soát. Với browser app, **BFF** có thể giữ refresh token ở backend; không mặc định lưu refresh token trong **localStorage** vì XSS có thể đọc được.

Nếu refresh token bị lấy cắp, rotation và phát hiện reuse giúp kích hoạt thu hồi token family theo chính sách. Mọi giải pháp vẫn phải xác định **logout một thiết bị** hay **logout tất cả**, cách tác động lên active access tokens và độ trễ chấp nhận của việc thu hồi.

### 8.1. JWT ký hợp lệ nhưng quyền đã bị giảm

Giả sử quyền ADMIN bị gỡ lúc 10:00, access token phát lúc 09:55 còn sống đến 10:10. Nếu API chỉ tin claim role trong JWT, quyền cũ có thể tiếp tục hiệu lực trong thời gian đó. Các lựa chọn: access token ngắn hạn, gọi hệ phân quyền tại request nhạy cảm, dùng token version hoặc denylist; chọn theo **yêu cầu thu hồi, độ trễ và tính sẵn sàng**. Đối với resource nhạy cảm, **scope token không thay resource authorization**.

### 8.2. Logout HTTP và cache

~~~http
POST /v1/session/logout HTTP/1.1
Host: app.example.test
Cookie: __Host-session=s_opaque
X-CSRF-TOKEN: token-valid
~~~

~~~http
HTTP/1.1 204 No Content
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Đây là **hợp đồng logout API tự thiết kế**, không phải response mặc định của Spring formLogin. Server phải invalidate phiên ở store **trước hoặc cùng luồng xử lý phù hợp**, và cookie xóa phải khớp **name/path/domain** với cookie đã đặt. **204 không có body**. Với bearer-only API, không giả định endpoint logout bằng cách xóa cookie có thể thu hồi mọi access token đã phát.

## 9. Ma trận chọn phương án theo loại client

| Bối cảnh | Phương án ưu tiên đánh giá | Câu hỏi phải trả lời |
|---|---|---|
| Web same-origin, tài khoản người dùng | **Cookie session** | CSRF, fixation, idle/absolute TTL, logout, HA session store |
| SPA có OAuth/OIDC | **BFF cookie session** hoặc Authorization Code + PKCE theo client | Token exposure, CORS, SameSite, callback và refresh |
| Mobile/native | **OAuth2 access token** với secure storage | Refresh rotation, device logout, offline/revocation |
| API đối tác | **Bearer token** theo chuẩn với audience/scope | Tenant scope, rotation, rate limit, token revocation |
| Service-to-service | **Client credentials/mTLS/workload identity** | Service identity, key/secret rotation, least privilege |
| Cần thu hồi tức thời từng phiên | **Server session hoặc opaque/introspection** | Store latency, outage behavior, cache staleness |
| Cần kiểm tra quyền ở từng bản ghi | Bất kỳ mô hình nào **+ domain authz** | BOLA, owner/tenant, caching, trạng thái resource |

**Không trộn hai nguồn danh tính trong một endpoint mà thiếu chính sách**: nếu vừa chấp nhận session cookie vừa chấp nhận Authorization bearer, cần quyết định credential nào được ưu tiên, CSRF có còn cần thiết, cách phân quyền và error handling. Một cách triển khai rõ hơn là **tách security filter chain theo nhóm route** hoặc tách BFF và API resource server thành các service độc lập.

**Chọn stateful không đồng nghĩa không mở rộng được**, và **stateless không đồng nghĩa bảo mật hơn**. Chi phí lựa chọn nằm ở trải nghiệm client, yêu cầu logout/revocation và độ phức tạp vận hành, không chỉ số request mỗi giây.

## 10. Kiểm thử HTTP và bảo mật với Spring

| Test | Session cookie | Bearer stateless |
|---|---|---|
| Request không credential | API 401 hoặc web redirect theo contract | 401 + WWW-Authenticate thích hợp |
| Có credential hợp lệ | Resolve đúng session và user | Validate JWT issuer/audience/signature/time |
| Thiếu quyền | 403 hoặc 404 che tài nguyên | 403 hoặc 404 che tài nguyên |
| Cookie/JWT của tenant A truy cập B | Bị từ chối, không rò body/Link | Tương tự, kiểm tra service query |
| POST thiếu CSRF | **403** với cookie session cần CSRF | Không áp dụng nếu bearer-only header và không có cookie auth |
| Session fixation | ID đổi sau login | Không áp dụng session cookie, nhưng vẫn chống token theft |
| Logout và replay | Session cũ không dùng lại được | Token cũ có thể dùng tới exp nếu chưa có revocation |
| Expired session/token | Yêu cầu login lại | 401, refresh theo flow an toàn |
| Nhiều replica / store outage | Fail-closed và error policy rõ | JWKS/identity dependency và key cache |
| Cross-origin browser | CORS credentials + SameSite + CSRF | CORS cho Authorization, chống XSS/token leak |

Ví dụ **MockMvc + spring-security-test** kiểm tra CSRF cho form-login session chain ở mục 5:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionCsrfTest {
    @Autowired MockMvc mvc;

    @Test
    void logoutWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/logout").with(user("demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithCsrfPassesSecurityCheck() throws Exception {
        mvc.perform(post("/logout")
                .with(user("demo"))
                .with(csrf()))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

Mẫu test giả định Spring context/session chain được cấu hình, cần imports JUnit/Spring test. Test thứ hai kiểm tra luồng logout mặc định dạng redirect, **không chứng minh một JSON logout API đã được triển khai**. Test fixation cần login thật qua form, so sánh session ID trước/sau và kiểm tra ID cũ không còn dùng được.

Với resource server, **MockMvc .with(jwt())** có thể kiểm tra authority/route nhưng **bỏ qua validation chữ ký/issuer thực** theo test support. Để xác minh crypto và policy, cần integration test với JWT ký bằng khóa test hợp lệ, **issuer/audience/JWKS giả lập**, token hết hạn, sai audience, sai signature và key rotation. Không lấy một unit test có mock Authentication làm bằng chứng xác thực production an toàn.

## 11. Bài tập thực hành

Một nền tảng đặt hàng có web admin cùng origin, mobile app và API đối tác. Web phải **logout tất cả thiết bị ngay sau khi tài khoản bị khóa**; mobile cho phép offline ngắn; đối tác dùng token có scope riêng. Hệ thống chạy bốn replica và có CDN trước API.

Hãy: **(1)** chọn mô hình cho từng client; **(2)** thiết kế Set-Cookie với Secure/HttpOnly/SameSite, TTL và invalidation; **(3)** nêu cách bảo vệ CSRF; **(4)** thiết kế JWT audience/scope/TTL và revocation khi khóa tài khoản; **(5)** xử lý GET/POST khi user A truy cập order B; **(6)** lập ít nhất sáu test security, bao gồm logout/replay và cross-origin.

**Gợi ý:** web dùng cookie session/BFF + shared session store và cơ chế hủy tất cả session theo user khi khóa; mobile dùng OAuth2/OIDC access token ngắn và refresh rotation với yêu cầu thu hồi rõ; đối tác dùng token riêng có audience/scope. Cả ba vẫn phải kiểm tra ownership/tenant, không trả data qua shared cache sai phạm vi. Xác định **độ trễ thu hồi** chấp nhận được thay vì hứa “JWT logout tức thì” khi API chỉ verify chữ ký offline.

## 12. Checklist và tham khảo

- [ ] Xác định loại client, ranh giới tin cậy, auth vs authz trước khi chọn session/token.
- [ ] Cookie có Secure/HttpOnly/SameSite/Path, cookie prefix và HTTPS đúng triển khai.
- [ ] Cookie-backed write có CSRF; ngăn session fixation/hijacking, logout invalidate server.
- [ ] JWT kiểm tra signature, issuer, audience, time, scope; TTL và key rotation có policy.
- [ ] Có kế hoạch thu hồi token, logout nhiều thiết bị, refresh rotation và đổi quyền.
- [ ] Kiểm tra tenant/owner cho từng resource; 401/403/404 không rò thông tin.
- [ ] Thử browser/proxy/CDN, CSRF, fixation, replay, expiry, cross-origin và multi-node.

Tham khảo: **Spring Security Servlet Authentication/Session Management**, https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html; **Spring Security CSRF**, https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html; **Spring OAuth2 Resource Server JWT**, https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html; **OWASP Session Management Cheat Sheet**, https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html; **OWASP CSRF Prevention Cheat Sheet**, https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html; **RFC 6750 Bearer Token Usage**, https://www.rfc-editor.org/rfc/rfc6750.html.

**Kết luận:** **Session cookie và stateless bearer token không đối lập về chất lượng bảo mật**; chúng phân bố trách nhiệm lưu trạng thái, CSRF và revocation khác nhau. Hãy chọn theo loại client, yêu cầu logout, ranh giới xác thực, khả năng vận hành và độ trễ thu hồi quyền, đồng thời luôn kiểm tra **authorization trên từng resource**.
