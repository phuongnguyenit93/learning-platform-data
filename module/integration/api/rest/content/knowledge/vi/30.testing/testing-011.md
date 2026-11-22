# Kiểm thử CORS, CSRF và token không hợp lệ

## 1. Bài toán: cùng một 403 nhưng ba lý do hoàn toàn khác

Một REST API bán hàng được gọi từ SPA trên **https://app.example.com** tới **https://api.example.com**. Trình duyệt báo *CORS error*, trong khi curl gọi cùng URL nhận **200 OK**. Một request POST khác trả **403 Forbidden** vì thiếu CSRF token; một request nữa trả **401 Unauthorized** vì JWT hết hạn. Nếu đội ngũ chỉ kiểm “status không phải 200” thì không biết phần nào hoạt động đúng và có thể vô tình bỏ qua đường tấn công thực tế.

Ba cơ chế cần được kiểm thử **độc lập và kết hợp**:

- **CORS:** Browser có được phép gửi một số request cross-origin qua preflight và cho script đọc response không? Server phản hồi các header Access-Control-* nào cho origin đáng tin và origin lạ?
- **CSRF:** Một request dùng **session cookie hoặc credential được browser tự gửi** có bị từ chối khi thiếu/sai CSRF token trước lúc thay đổi trạng thái không?
- **Token không hợp lệ:** Resource server có từ chối Bearer access token sai chữ ký, hết hạn, issuer/audience không đúng hoặc thiếu quyền không? **401 khác 403** như thế nào?

Bài thuộc chương **Kiểm thử**, module **INTEGRATION_API_REST**, nơi người học thiết kế REST theo resource/URI, method/status HTTP, hợp đồng dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền và xử lý lỗi với Java/Spring. Trọng tâm bài là **chiến lược kiểm thử có bằng chứng ở HTTP boundary và browser**, không viết lại toàn bộ kiến thức CORS, OAuth hay CSRF.

**Mục tiêu:** thiết lập fixture rõ ranh giới bảo mật, viết MockMvc/JUnit test cho CORS/CSRF, kiểm JWT decoder thực sự (không nhầm mock authentication với chữ ký thật), xác nhận không có side effect khi request bị từ chối, và chạy một ma trận regression ở CI.

## 2. Thiết kế fixture: kiểm chính xác lớp bảo vệ nào

Giả sử một ứng dụng Spring Boot 3.x/Spring Security 6 (Servlet MVC) có hai nhóm endpoint:

| Nhóm route | Credential | Ví dụ | CSRF | Quyền |
| --- | --- | --- | --- | --- |
| **/browser/** | Session cookie do browser tự gửi | POST /browser/orders/{id}/cancel | **Bật** cho unsafe methods | User phải sở hữu order. |
| **/bearer/** | Access token đặt rõ trong Authorization: Bearer | GET /bearer/orders/{id} | Có thể tắt **chỉ nếu thật sự không nhận ambient browser credential** | Token có audience/scope đúng, rồi kiểm owner/tenant. |

Mỗi test cần biết kết quả từ lớp nào:

~~~mermaid
flowchart TD
    R["HTTP request"] --> C{"CORS origin/preflight?"}
    C -->|Rejected| X["CORS denial: no permission to read/call"]
    C -->|Allowed/not applicable| A{"Authenticated?"}
    A -->|No| U["401 hoặc redirect login theo entry point"]
    A -->|Yes| S{"CSRF required and token valid?"}
    S -->|No| F["403; no side effect"]
    S -->|Yes| P{"Scope/resource permission?"}
    P -->|No| D["403/404 theo policy"]
    P -->|Yes| H["Controller + domain service"]
~~~

Sơ đồ là **cách lập test**, không khẳng định thứ tự filter trong mọi cấu hình: trong Spring Security, CSRF check có thể xảy ra trước một số bước authentication. Vì vậy một request **vừa thiếu credential vừa thiếu CSRF** có thể nhận status khác tùy chain. **Để test từng nguyên nhân, giữ các điều kiện còn lại hợp lệ**: muốn kiểm CSRF thì đưa vào một principal đã đăng nhập; muốn kiểm JWT thì gọi GET safe không đòi CSRF.

### 2.1. Đầu ra cần khẳng định trong test

Với request bị từ chối, ngoài status, kiểm tra:

1. **Không có side effect**: service cancel không được gọi; số hàng DB/trạng thái order không đổi.
2. **Header có ý nghĩa**: Access-Control-Allow-Origin, WWW-Authenticate, Content-Type khi có body, Vary khi cần.
3. **Không lộ dữ liệu**: response không có token/session, stack trace, internal SQL/tenant data.
4. **Không lách qua route khác**: OPTIONS được xử lý preflight đúng, GET không làm thay đổi nghiệp vụ, wildcard path không bỏ qua security chain.
5. **Kết quả trên browser**: network request/response, cookie policy và khả năng JS đọc response phải được quan sát; **curl và MockMvc không phải browser**.

## 3. Test CORS: phân biệt preflight và actual response

Hai địa chỉ **https://app.example.com** và **https://api.example.com** là **cross-origin** vì khác host, dù thường **same-site** theo schemeful SameSite. CORS là chính sách browser dựa trên **origin = scheme + host + port**; không đồng nghĩa SameSite/cookie policy.

### 3.1. Preflight được chấp nhận

Request OPTIONS do browser phát trước một cross-origin POST JSON có custom CSRF header có thể giống:

~~~http
OPTIONS /browser/orders/11111111-1111-4111-8111-111111111111/cancel HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Phản hồi hợp lệ theo cấu hình minh họa:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Vary: Origin
~~~

Giá trị/cách sắp xếp header thực tế do framework và chính sách quyết định. **Preflight không cần session cookie hoặc CSRF token**; phải được xử lý trước khi authentication cản trở OPTIONS. Test nên kiểm **ACAO đúng origin** và method/headers được phép, không bắt thứ tự chuỗi Allow-Methods cứng nhắc nếu không cần.

### 3.2. Origin lạ và request đơn giản

~~~http
OPTIONS /browser/orders/11111111-1111-4111-8111-111111111111/cancel HTTP/1.1
Host: api.example.com
Origin: https://attacker.example.net
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Server CORS filter có thể trả **403 Invalid CORS request** hoặc một phản hồi **không cấp Access-Control-Allow-Origin**. Browser phải không được phép dùng response như đã được cấp CORS; **không nên coi status 403 là cơ chế duy nhất** vì các server có thể biểu diễn denial khác.

**Điều không được suy ra:** “Origin lạ không đọc được response ⇒ không thể gây side effect”. HTML form với content type đơn giản có thể gửi cross-site POST **mà không cần CORS permission**; nếu browser đính kèm credential, **CSRF token vẫn phải chặn mutation**.

### 3.3. Credentialed CORS không được dùng wildcard

Với **credentials: include**, không dùng **Access-Control-Allow-Origin: *** cùng **Access-Control-Allow-Credentials: true**. Phải trả origin cụ thể được allowlist; nếu phản hồi được cache dùng chung, **Vary: Origin** giúp phân biệt variant. Nếu API không dùng cookie/credentials thì có thể có cấu hình CORS khác, nhưng đó không phải bằng chứng được phép bỏ authorization hay chống XSS.

Browser có thể chặn cookie third-party ngay cả khi CORS đúng. Vì vậy test phải phân biệt **CORS thất bại**, **cookie không được gửi** và **server auth/CSRF từ chối**. CORS chính xác không làm SameSite=None, Secure hoặc third-party cookie policies tự hoạt động.

## 4. Spring MVC fixture để kiểm CORS và CSRF với session

Đây là cấu hình minh họa. Trong một ứng dụng thật, nên đặt **/browser/** và **/bearer/** ở hai security chains rõ ràng, không đăng ký hai chains cạnh tranh cùng route.

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class BrowserSecurityConfig {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PATCH", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/browser/**", cors);
        return source;
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http)
            throws Exception {
        return http
                .securityMatcher("/browser/**")
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

**Giả định:** authentication cho nhóm /browser/** được thiết lập bởi session login flow/application khác. Bản chain này chỉ minh họa **CORS + CSRF + authorization**, chưa cấu hình màn hình login. Trong môi trường có form login, unauthenticated request có thể redirect 302; nếu ứng dụng công bố API JSON trả 401, cần cấu hình entry point riêng. **Không tắt CSRF chỉ vì client dùng JSON**.

Một controller đủ nhỏ để test:

~~~java
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record CancelCommand(String reason) {}

interface OrderCancelService {
    void cancelAuthorized(String actor, UUID id, String reason);
}

@RestController
@RequestMapping("/browser/orders")
class BrowserOrderController {
    private final OrderCancelService service;

    BrowserOrderController(OrderCancelService service) {
        this.service = service;
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancel(
            @PathVariable UUID id,
            @RequestBody CancelCommand request,
            Authentication authentication) {
        service.cancelAuthorized(
                authentication.getName(), id, request.reason());
        return ResponseEntity.noContent().build();
    }
}
~~~

Service phải kiểm **tenant, ownership, trạng thái đơn, concurrency và authorization**, dù CSRF token đúng. Test chỉ tập trung vào filter nếu dùng fake service; test nghiệp vụ phải chạy service/DB thật. Controller nên có validation cho reason và exception mapping/Problem Details khi tích hợp đầy đủ.

## 5. MockMvc: kiểm CORS preflight và actual request

Sử dụng **spring-boot-starter-test** và **spring-security-test** cùng Spring Boot/Spring Security. Các test dưới đây giả định application context chỉ có một cấu hình CORS của phần 4 và controller/service mock tương ứng.

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BrowserCorsCsrfIT {
    private static final String TRUSTED = "https://app.example.com";
    private static final UUID ORDER_ID =
            UUID.fromString("11111111-1111-4111-8111-111111111111");

    @Autowired MockMvc mvc;
    @MockBean OrderCancelService cancelService;

    @Test
    void allowedPreflightDoesNotRequireSessionOrCsrf() throws Exception {
        mvc.perform(options("/browser/orders/{id}/cancel", ORDER_ID)
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));

        verifyNoInteractions(cancelService);
    }

    @Test
    void untrustedPreflightCannotGainCorsPermission() throws Exception {
        mvc.perform(options("/browser/orders/{id}/cancel", ORDER_ID)
                .header(HttpHeaders.ORIGIN, "https://attacker.example.net")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));

        verifyNoInteractions(cancelService);
    }

    @Test
    void permittedOriginStillNeedsCsrfOnPost() throws Exception {
        mvc.perform(post("/browser/orders/{id}/cancel", ORDER_ID)
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"requested\"}"))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED));

        verifyNoInteractions(cancelService);
    }

    @Test
    void correctCsrfAndAuthorizedPrincipalAllowMutation()
            throws Exception {
        mvc.perform(post("/browser/orders/{id}/cancel", ORDER_ID)
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"requested\"}"))
            .andExpect(status().isNoContent())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED));

        verify(cancelService).cancelAuthorized(
                "alice", ORDER_ID, "requested");
    }

    @Test
    void invalidCsrfHeaderIsRejectedBeforeService()
            throws Exception {
        mvc.perform(post("/browser/orders/{id}/cancel", ORDER_ID)
                .with(user("alice"))
                .with(csrf().useInvalidToken().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"requested\"}"))
            .andExpect(status().isForbidden());

        verifyNoInteractions(cancelService);
    }
}
~~~

**Fixture:** Spring Boot 3.x dùng **@MockBean** trong ví dụ; các phiên bản Spring Framework/Boot mới có **@MockitoBean**, cần chọn annotation hỗ trợ ở dự án thật. Mock tự reset giữa các test theo cấu hình thông thường. **with(user("alice"))** tạo principal giả cho phép cô lập CSRF/CORS; **không phải kiểm thử login hoặc cookie của browser thật**. **with(csrf())** cũng là token giả đúng cấu hình test, không chứng minh vòng đời token phía SPA. Nếu CORS filter được cấu hình trả denial khác 403, test origin lạ nên khẳng định trọng tâm **không cấp quyền CORS** theo contract và kiểm hành vi browser riêng.

### 5.1. Test thêm các biến thể bắt buộc

- **Allowed origin nhưng method không cho phép:** OPTIONS xin method TRACE → không nhận Allow-Methods chứa TRACE.
- **Allowed origin nhưng custom header không cho phép:** preflight xin X-Admin-Override → không được cấp header.
- **Origin đúng hostname nhưng sai scheme/port:** http://app.example.com hoặc https://app.example.com:8443 → không nhận ACAO nếu không nằm trong allowlist.
- **Actual request:** GET/POST hợp lệ phải có ACAO chính xác và **Vary: Origin** khi response có thể cache; không dùng wildcard cho credentialed response.
- **Không có Origin:** request từ backend/non-browser không cần CORS permission; vẫn phải qua authentication, CSRF và business permission của chính route.

Một test **chỉ khẳng định header trên preflight** không chứng minh actual response được thiết lập đúng. Test **chỉ gửi curl OPTIONS** không chứng minh browser gửi cookie hoặc JS đọc response được.

## 6. Test CSRF: thiếu, sai, đúng và vòng đời phiên

CSRF kiểm một thuộc tính khác authentication: browser có thể tự gửi **SESSION** cookie, nhưng một trang không tin cậy không được có CSRF token gắn phiên. Với Spring Security, **unsafe methods** như POST/PATCH/PUT/DELETE được kiểm; GET/HEAD/OPTIONS được coi là safe theo mặc định, vì vậy application **không được dùng GET để thực thi command**.

### 6.1. Bốn trường hợp không được bỏ

| Request (đã login) | Token | Kỳ vọng |
| --- | --- | --- |
| POST /browser/orders/{id}/cancel | Thiếu | **403**, domain service không chạy. |
| POST tương tự | Token sai hoặc thuộc phiên khác | **403**, không mutation. |
| POST tương tự | Token đúng | Đi tới authorization/domain; **204** nếu order được phép và hợp lệ. |
| GET /browser/orders/{id} | Không có CSRF token | Không bị từ chối **chỉ vì thiếu CSRF**; vẫn cần authentication/quyền. |

Với test DB thật, đọc trạng thái order trước/sau hai nhánh bị chặn; **status 403 không đủ** nếu một filter/handler gây side effect trước khi trả lỗi. Trong test MockMvc ở phần 5, **verifyNoInteractions(cancelService)** chỉ chứng minh controller service không bị gọi; integration test DB mạnh hơn.

### 6.2. Session rotation, logout và SPA token

Quy trình browser cần kiểm:

1. Login và lấy token qua form hoặc endpoint cung cấp CSRF token từ **cùng origin/allowlisted origin**; response gắn phiên nên **Cache-Control: no-store**.
2. Gửi cookie hợp lệ cùng token: POST đi qua CSRF filter, rồi bị áp domain authorization.
3. Logout/login lại hoặc session hết hạn: **token của phiên cũ không được chấp nhận** theo cách repository/handler cấu hình; SPA tải token mới.
4. Xác minh **session cookie Secure, HttpOnly, SameSite**, Domain/Path và TLS; CSRF token không nằm trong URL, log, CDN cache hoặc response CORS cho origin lạ.

**Spring Security 6** mặc định có **deferred CSRF token** và cách xử lý token **masked**; nếu SPA đọc token từ cookie, cần cấu hình **CookieCsrfTokenRepository và SpaCsrfTokenRequestHandler** tương thích phiên bản, không chỉ bật **withHttpOnlyFalse()** rồi giả định token đã đi đúng. Test bằng browser/HTTP response thật để phát hiện lỗi masked-vs-plain token.

### 6.3. Origin/Fetch Metadata chỉ là lớp bổ sung

Các header **Origin**, **Referer**, **Sec-Fetch-Site**, **Sec-Fetch-Mode** có thể hỗ trợ chính sách từ chối unsafe cross-site request. Nhưng một subdomain bị chiếm quyền thường vẫn **same-site** với API; **SameSite=Lax** có thể gửi cookie trong top-level safe navigation; Fetch Metadata có thể thiếu ở browser cũ. Test cả **cross-site** và **cross-origin same-site** nếu trust boundary có subdomains, thay vì kết luận “SameSite đã chống CSRF”.

Một HTML form **application/x-www-form-urlencoded** từ origin lạ có thể được browser gửi mà không cần CORS preflight. Nếu cookie được đính kèm, server **phải từ chối do thiếu CSRF token**. Đừng cho phép form POST bypass CSRF chỉ vì API chủ yếu nhận JSON.

## 7. Bearer resource server: phân loại lỗi token trước khi test

**Kiểm chữ ký JWT, kiểm claims và kiểm quyền tài nguyên là ba lớp riêng**. Resource server phải chấp nhận access token từ issuer đáng tin, dành cho audience API, còn hiệu lực, có scope phù hợp; sau đó domain service mới quyết định quyền trên một order cụ thể.

| Điều kiện token/request | HTTP dự kiến | Lý do và lớp kiểm |
| --- | --- | --- |
| Không có Bearer credential ở protected endpoint | **401**, Bearer challenge | Chưa xác thực. |
| Malformed token, chữ ký sai, thuật toán không cho phép | **401**, thường invalid_token | Không xác minh được token. |
| **exp** đã hết; **nbf** chưa tới | **401** | Token chưa/không còn hiệu lực theo clock skew policy. |
| **iss** sai, **aud** không chứa API được cấp token | **401** | Token không thuộc trust boundary hoặc không dành cho API này. |
| ID token của web client bị dùng như access token | **401** nếu kiểm aud/token profile phù hợp | Chống token substitution. |
| Token hợp lệ, thiếu **orders.read** | **403**, có thể insufficient_scope | Authenticated nhưng thiếu authority. |
| Có orders.read nhưng order thuộc tenant khác | **403/404** theo policy | Quyền nghiệp vụ trên object, không phải chữ ký. |
| Token và quyền đúng, resource tồn tại | **200** và representation đúng | Cả hai lớp đều thông qua. |

Nếu dùng **opaque token**, kiểm bằng introspection: active=false, expired/revoked hoặc introspection không thể xác minh phải bị từ chối; kiểm audience/scope theo response từ AS đã được cấu hình. Không lấy string trông giống JWT làm bằng chứng là access token hợp lệ.

### 7.1. Cấu hình Bearer chain tách khỏi session

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BearerSecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain bearerChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/bearer/**")
                .sessionManagement(s -> s.sessionCreationPolicy(
                        SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/bearer/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth -> oauth.jwt(
                        Customizer.withDefaults()))
                .build();
    }
}
~~~

**Điều kiện của ví dụ:** /bearer/** không nhận session/Basic/browser-managed credentials và **JwtDecoder được cấu hình** kiểm issuer, audience, signature, exp/nbf. Tắt CSRF **chỉ trong chain này**, không tắt ở **/browser/**. Không để wildcard matcher khiến session route lọt vào chain Bearer-only. Khi app có cả hai chain, kiểm thứ tự @Order và matcher bằng integration test.

Spring Security mặc định có thể ánh xạ scope trong JWT thành authority **SCOPE_orders.read**. Chỉ số status HTTP không chứng minh quyền đối tượng; controller/service phải tự kiểm tenant/owner. **Không tắt JWT validation để test dễ hơn**; có thể dùng auth giả trong các test phân quyền thuần túy, nhưng cần test decoder thật ở lớp khác.

## 8. MockMvc: test authorization khi đã có một principal hợp lệ

Spring Security Test cung cấp **jwt()** request post-processor để tạo **JwtAuthenticationToken giả**. Nó hữu ích để test route scope và domain service, nhưng **bỏ qua chữ ký, exp, nbf, issuer và audience**. Đừng đặt tên test “rejectsExpiredJwt” khi thực chất chỉ dùng **with(jwt())** với một claim hết hạn; test đó có thể vẫn cho request qua.

Ví dụ fixture có controller **GET /bearer/orders/{id}**:

~~~java
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record OrderResponse(UUID id, String status) {}
interface OrderReadService {
    OrderResponse findAuthorized(String subject, UUID id);
}

@RestController
@RequestMapping("/bearer/orders")
class BearerOrderController {
    private final OrderReadService service;
    BearerOrderController(OrderReadService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderResponse> get(
            @PathVariable UUID id, Authentication authentication) {
        return ResponseEntity.ok(
                service.findAuthorized(authentication.getName(), id));
    }
}
~~~

Kiểm SecurityFilterChain với token giả đã xác thực:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BearerScopeIT {
    @Autowired MockMvc mvc;
    @MockBean OrderReadService orderReadService;

    @Test
    void noBearerIsUnauthorized() throws Exception {
        mvc.perform(get("/bearer/orders/11111111-1111-4111-8111-111111111111"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));
        verifyNoInteractions(orderReadService);
    }

    @Test
    void authenticatedWithoutReadScopeIsForbidden() throws Exception {
        mvc.perform(get("/bearer/orders/11111111-1111-4111-8111-111111111111")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
        verifyNoInteractions(orderReadService);
    }
}
~~~

Đây là test **status 401 khi thiếu token** và **403 khi authority không đủ**. Nó **chưa test cryptography**. Test token invalid cần gửi Bearer string thật qua Authorization header cùng một JwtDecoder/AS test được cấu hình, không thay việc ấy bằng jwt(). Trong application context dùng JWT resource server, có thể cần fake/JWKS decoder test cấu hình sẵn để context khởi tạo mà không gọi issuer production.

### 8.1. Quyền object/tenant phải test ở service và DB

Để test BOLA, tạo hai order thuộc hai tenant, hai principal có scope **orders.read**. Token của tenant A yêu cầu order tenant B phải trả **403 hoặc 404** theo chính sách, không chứa order B. **Không mock repository luôn trả order A**: test đó không chứng minh predicate tenant trên query. Đừng suy rằng có authority SCOPE_orders.read thì mọi order đều đọc được.

### 8.2. Đừng trộn test OAuth JWT với CSRF session

Một **GET Bearer** thiếu token có thể nhận 401; một **POST session** thiếu CSRF nhận 403 trước service. Nếu dùng một chain duy nhất chấp nhận cả cookie và Bearer, phải xác định rõ điều kiện nào được miễn CSRF, tại sao an toàn và kiểm từng nhánh. **Kiểu token (JWT vs opaque) không quyết định rủi ro CSRF**; cách browser tự gửi credential mới quyết định.

## 9. JwtDecoder thật: kiểm chữ ký, issuer, audience và thời gian

Để chứng minh token sai bị từ chối, hãy tạo **cặp khóa RSA chỉ dùng cho test**, ký JWT bằng private key thử nghiệm rồi giải mã/xác minh bằng public key được trust. Không kết nối tới issuer production, không hard-code production secret và không dùng test post-processor **jwt()** trong test này.

### 9.1. JUnit kiểm cryptography và claims

Ví dụ Spring Security OAuth2 JOSE + Nimbus JOSE JWT (có trong stack Resource Server JWT):

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.*;

import static org.junit.jupiter.api.Assertions.*;

class AccessTokenDecoderTest {
    private static final String ISSUER =
            "https://issuer.test.example/realms/shop";

    private static KeyPair newRsaKey() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static NimbusJwtDecoder decoder(KeyPair trustedKey) {
        NimbusJwtDecoder result = NimbusJwtDecoder
                .withPublicKey((RSAPublicKey) trustedKey.getPublic())
                .build();
        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                                "Wrong token audience", null));
        result.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(ISSUER),
                        audience));
        return result;
    }

    private static String signed(
            KeyPair signingKey, String issuer, String audience,
            Instant expiresAt) throws Exception {
        var claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject("alice")
                .audience(audience)
                .issueTime(Date.from(Instant.now().minusSeconds(10)))
                .expirationTime(Date.from(expiresAt))
                .claim("scope", "orders.read")
                .build();
        SignedJWT token = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .type(JOSEObjectType.JWT).build(),
                claims);
        token.sign(new RSASSASigner(
                (RSAPrivateKey) signingKey.getPrivate()));
        return token.serialize();
    }

    @Test
    void acceptsValidSignatureIssuerAudienceAndLifetime()
            throws Exception {
        KeyPair trusted = newRsaKey();
        String token = signed(trusted, ISSUER,
                "orders-api", Instant.now().plusSeconds(300));
        assertEquals("alice", decoder(trusted).decode(token).getSubject());
    }

    @Test
    void rejectsSignatureFromUntrustedKey() throws Exception {
        KeyPair trusted = newRsaKey();
        String forged = signed(newRsaKey(), ISSUER,
                "orders-api", Instant.now().plusSeconds(300));
        assertThrows(JwtException.class,
                () -> decoder(trusted).decode(forged));
    }

    @Test
    void rejectsWrongAudienceAndIssuer() throws Exception {
        KeyPair trusted = newRsaKey();
        var verifier = decoder(trusted);
        String wrongAudience = signed(trusted, ISSUER,
                "other-api", Instant.now().plusSeconds(300));
        String wrongIssuer = signed(trusted,
                "https://untrusted.test.example",
                "orders-api", Instant.now().plusSeconds(300));
        assertThrows(JwtException.class,
                () -> verifier.decode(wrongAudience));
        assertThrows(JwtException.class,
                () -> verifier.decode(wrongIssuer));
    }

    @Test
    void rejectsExpiredToken() throws Exception {
        KeyPair trusted = newRsaKey();
        String expired = signed(trusted, ISSUER,
                "orders-api", Instant.now().minusSeconds(300));
        assertThrows(JwtException.class,
                () -> decoder(trusted).decode(expired));
    }
}
~~~

**Điểm kiểm chứng:** signed JWT có chữ ký nhưng **sai audience** vẫn bị từ chối; JWT đúng issuer/audience nhưng chữ ký từ **khóa lạ** cũng bị từ chối. Token hết hạn hơn nhiều phút để tránh kết quả không ổn định do clock skew nhỏ. Test thêm **nbf tương lai**, token malformed, JWT alg không được phép và **ID token dành cho web client** theo profile thực tế của authorization server.

Trong ứng dụng, JwtDecoder cần kiểm **issuer và audience**: một số cấu hình chỉ đặt issuer URI nhưng **không tự kiểm audience của Orders API**. Nếu resource server chỉ kiểm chữ ký/issuer/exp thì test wrongAudience sẽ phát hiện thiếu validator quan trọng. Với opaque token, thay test cryptography bằng introspection stub kiểm **active=false, audience/scope sai, AS timeout và fail-closed**.

### 9.2. Nối JwtDecoder thật vào HTTP integration test

Test decoder unit chứng minh validation, nhưng chưa chứng minh **BearerTokenAuthenticationFilter** chuyển lỗi thành 401 đúng. Một integration fixture nên inject **JwtDecoder tin public key test** vào Spring context, gửi JWT ký thật qua HTTP header:

~~~java
// Trong @SpringBootTest có JwtDecoder test tin public key của fixture.
mvc.perform(get("/bearer/orders/{id}", orderId)
        .header("Authorization", "Bearer " + invalidSignedToken))
    .andExpect(status().isUnauthorized())
    .andExpect(header().exists("WWW-Authenticate"));
~~~

**Snippet** phụ thuộc biến **mvc, orderId, invalidSignedToken** từ fixture tích hợp. JWT hợp lệ nhưng thiếu authority cần test trả 403; token hợp lệ đủ scope nhưng khác tenant phải test ở domain service/DB. **Không dùng mock JwtDecoder luôn trả token thành công** để tuyên bố đã test chữ ký/issuer/exp.

### 9.3. Chú ý challenge và lỗi hiển thị

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
~~~

Bearer challenge có thể có error khi token không hợp lệ; thiếu token có thể chỉ có **WWW-Authenticate: Bearer** mà không kèm error. **403 insufficient_scope** có thể kèm Bearer challenge mô tả scope, nhưng không nhất thiết có cùng body như 401. Kiểm status/headers theo **security entry point/AccessDeniedHandler đã cấu hình**, không bắt message text nội bộ của thư viện làm contract. Không đưa token raw, key, claim bí mật hoặc stack trace vào Problem Details/log.

## 10. Browser-level test: vì sao MockMvc và curl chưa đủ?

**MockMvc** kiểm Spring filters/controller mà không chạy chính sách cookie hay CORS enforcement của một browser thật. **curl** có thể gửi bất kỳ Origin/cookie/header nào và luôn đọc response bất kể Access-Control-Allow-Origin. Với các lỗi “chỉ xảy ra trên trình duyệt”, cần kiểm thử trên browser thực bằng Playwright, Selenium/WebDriver hoặc quy trình kiểm thử thủ công trên staging được phép.

### 10.1. Hai origin test và ba kiểu request

Chuẩn bị:

- **https://app.example.com**: SPA được tin cậy, có CORS allowlist từ API.
- **https://attacker.example.net**: trang giả lập origin không tin cậy, **không** được nằm trong allowlist.
- **https://api.example.com**: API session cookie và endpoint Bearer được tách rõ.

Với mỗi origin, quan sát **request có được gửi không, có cookie không, response có đọc được bằng JS không, và DB có mutation không**. Dùng dữ liệu test giả, không dùng đơn hàng thật.

| Thử nghiệm browser | Quan sát quan trọng |
| --- | --- |
| SPA tin cậy fetch GET cross-origin với credentials include | CORS cho JS đọc response; cookie chỉ đi nếu Domain/SameSite/Secure/browser policy cho phép. |
| SPA tin cậy fetch POST JSON + X-CSRF-TOKEN hợp lệ | Preflight thông qua, actual POST chạy, service kiểm quyền và chỉ mutation đúng order. |
| SPA tin cậy POST thiếu hoặc sai CSRF token | Có thể qua CORS nhưng server từ chối **403**, DB không đổi. |
| Origin lạ fetch POST JSON + custom header | Preflight không cấp CORS permission; browser không được phép gửi non-simple actual request sau đó. |
| Origin lạ dùng HTML form POST đơn giản | Browser có thể gửi POST; nếu ambient credential đi theo thì **server CSRF vẫn chặn**. |
| Origin lạ cố fetch GET và đọc response | JS không được đọc nếu CORS từ chối, nhưng không lấy đó làm bằng chứng auth/domain đúng. |
| Same-site subdomain nhưng cross-origin | Không mặc định trusted chỉ vì SameSite; kiểm CORS/Origin và CSRF token riêng. |

**Đừng chỉ kết luận từ dòng chữ “CORS blocked” trong DevTools.** Một actual request kiểu form có thể đã tới server. Test phải đối chiếu **access log đã redacted, trace ID và trạng thái DB sau request**. Nếu cookie không được gửi do SameSite hoặc third-party-cookie policy, test chưa chứng minh được CSRF filter hoạt động; cần một fixture có session credential thực sự được gửi.

### 10.2. Một lệnh kiểm tra header, không thay browser test

~~~bash
curl -i -X OPTIONS \
  'https://api.example.com/browser/orders/11111111-1111-4111-8111-111111111111/cancel' \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

Lệnh trên chỉ phục vụ quan sát HTTP/CORS **trên môi trường được phép**. Curl không thực thi SameSite, không tự áp CORS và không chứng minh có cookie/CSRF token trong browser. Không đưa session cookie hoặc access token production vào lịch sử terminal hay log test.

## 11. Ma trận regression và chống test false-positive

| Mã | Mục tiêu | Tầng test | Điều khẳng định |
| --- | --- | --- | --- |
| R01 | Preflight origin cho phép, method/header hợp lệ | MockMvc + browser | ACAO cụ thể, credentials đúng, preflight thành công không cần login/CSRF. |
| R02 | Origin, scheme, port hoặc method không được phép | MockMvc + browser | Không cấp quyền CORS; browser không đọc/gửi non-simple actual request. |
| R03 | Actual response của origin hợp lệ | MockMvc | ACAO, Vary và nội dung đúng contract. |
| R04 | HTML form gửi POST không có CSRF token | Browser + DB | Không có side effect dù CORS không bảo vệ form. |
| R05 | Session POST không token hoặc token sai | MockMvc + DB | 403, service không chạy/DB không đổi. |
| R06 | Session POST token đúng | MockMvc + service/DB | Qua CSRF, vẫn phải kiểm owner/tenant; thành công theo contract. |
| R07 | GET safe không có CSRF token | MockMvc | Không tạo mutation; authentication/authorization vẫn chạy. |
| R08 | Login/logout/session rotation | Browser | Token cũ không vượt chính sách vòng đời; cookie flags đúng. |
| R09 | Bearer token không có hoặc malformed | MockMvc với decoder thật | 401, Bearer challenge, không vào domain service. |
| R10 | JWT chữ ký/alg/iss/aud sai; exp/nbf không hợp lệ | Decoder + HTTP integration | Không nhận token; response theo contract. |
| R11 | JWT hợp lệ, thiếu scope | MockMvc | 403 do thiếu authority; không gọi service. |
| R12 | JWT hợp lệ, đúng scope nhưng sai tenant | Service/DB + HTTP | 403/404, không lộ resource. |
| R13 | Opaque introspection active=false/timeout | AS stub + HTTP | Không fail open; status/challenge theo policy. |
| R14 | CORS/CSRF/Authorization chạy đồng thời | Browser end-to-end | Không có cấu hình chain/order làm bypass kiểm soát còn lại. |

### 11.1. Những false-positive phổ biến

**“Test CORS pass vì OPTIONS trả 200.”** OPTIONS không có ACAO hợp lệ hoặc allow headers/methods sai thì browser vẫn không cho dùng request. Hãy kiểm cả response headers và browser behavior.

**“Test CSRF pass vì POST trả 403.”** Có thể 403 do thiếu quyền hoặc CORS từ chối trước khi vào CSRF filter. Đưa vào **principal có quyền**, origin hợp lệ, chỉ thay đổi CSRF token; kiểm không side effect.

**“Test token expiry pass vì đặt exp quá khứ trong jwt().”** Test post-processor có thể tạo Authentication giả và **bỏ qua decoder**. Dùng JWT ký thực với decoder thật và gửi Authorization header.

**“Token hợp lệ nên 200 là đủ.”** Có thể đã bỏ qua audience, tenant hoặc scope; cần negative tests phân biệt các quyền và đưa tài nguyên thuộc người khác vào fixture.

**“Swagger UI gọi được nên mọi browser đều gọi được.”** Swagger có origin, authentication flow và cookie state khác frontend production. Test đúng scheme/host/port và browser configuration của ứng dụng.

### 11.2. Tổ chức chạy trong CI

- **Nhanh, mỗi pull request:** pure validator/unit tests, Spring MockMvc CORS/CSRF/scope; không gọi issuer hoặc database production.
- **Integration khi thay đổi security/config:** DB fixture, token ký RSA thử nghiệm, JwtDecoder thực, opaque introspection stub, lỗi expiry/issuer/audience, tenant data.
- **Browser/security regression:** app/API chạy bằng HTTPS trên hai hoặc nhiều test origins, cookie policy, preflight, session rotation, cross-site form, kiểm side effects.
- **Trước triển khai:** rà soát CORS allowlist, cookie Domain/SameSite/Secure, public endpoints, login redirect, CSRF exemptions, proxy Forwarded headers, token issuer/JWKS/audience và test tích hợp gateway.

Chạy test với **đồng hồ và key material ổn định**; tránh token hết hạn chỉ vài mili giây gây flaky. Nếu test cần port/TLS, tạo môi trường cô lập và dọn fixture sau chạy. Không gọi AS production, không sử dụng session thật trong automated security tests.

## 12. Bài tập: ba kết quả lỗi trên cùng Orders API

**Tình huống:** SPA ở **https://app.example.com**, Orders API ở **https://api.example.com** có hai nhánh: **/browser/orders** nhận session cookie và **/bearer/orders** nhận access token. Kết quả thử nghiệm hiện tại:

1. Preflight từ app.example.com tới /browser/orders trả 401.
2. Preflight từ attacker.example.net được trả **Access-Control-Allow-Origin: *** và **Access-Control-Allow-Credentials: true**.
3. POST có session hợp lệ, không CSRF token nhưng vẫn hủy được order.
4. Token JWT có aud=other-api vẫn đọc được /bearer/orders.
5. Token đúng issuer/audience nhưng thiếu orders.read trả 200.

**Yêu cầu:** (a) Chỉ ra lỗi ở từng lớp và cách sửa, (b) viết tối thiểu sáu test phủ cả allow/deny, (c) giải thích vì sao jwt() không chứng minh audience validation, (d) nêu khi nào nên dùng 401, 403 và 404, (e) đề xuất cách kiểm kết quả browser khác kết quả MockMvc.

**Hướng giải:** preflight phải được CORS xử lý trước authentication; chỉ allowlist **https://app.example.com** với credentials, không wildcard. Session route phải bật CSRF và từ chối thiếu/sai token trước side effect. JwtDecoder cần validator **aud=orders-api**, issuer, thời hạn và chữ ký; scope orders.read bắt buộc ở GET, sau đó domain service kiểm tenant. Test CORS hợp lệ/bị từ chối, CSRF thiếu/sai/đúng, JWT sai aud/chữ ký/exp, đúng JWT thiếu scope, object khác tenant. **401** cho không xác thực/token không hợp lệ; **403** cho thiếu quyền hoặc CSRF (phân biệt nguyên nhân trong log); **404** theo policy che sự tồn tại resource. Browser test phải kiểm cookie thực sự được gửi, JS có được đọc response và DB có thay đổi không.

## 13. Checklist trước khi kết luận “security tests pass”

- [ ] CORS: kiểm **preflight và actual response**, đúng scheme/host/port, method/header, credentials, Vary; không wildcard cho credentialed CORS.
- [ ] CSRF: **session/cookie unsafe methods** bắt buộc token, test thiếu/sai/đúng; GET không làm command.
- [ ] Test từ origin lạ bằng **HTML form** và browser thực, không chỉ fetch preflight.
- [ ] Cookie flags **Secure/HttpOnly/SameSite/Domain/Path** và vòng đời token sau login/logout được kiểm.
- [ ] Bearer-only stateless route và browser-session route có **security chain/matcher riêng**, không miễn CSRF sai phạm vi.
- [ ] Bearer/JWT: test malformed, bad signature, issuer, audience, exp/nbf bằng **decoder thật**; không dùng jwt() giả để chứng minh cryptography.
- [ ] Token hợp lệ nhưng thiếu scope → **403**; đủ scope nhưng sai tenant → **403/404**, không lộ nội dung.
- [ ] Có **WWW-Authenticate** phù hợp ở 401; không rò token/stack trace/PII qua error response hoặc logs.
- [ ] Mọi negative test quan trọng xác minh **service không chạy hoặc dữ liệu DB không đổi**.
- [ ] CI có test unit/MockMvc/decoder, tích hợp DB/AS stub và browser HTTPS đúng ranh giới.

**Kết luận:** kiểm thử CORS, CSRF và token không hợp lệ không thể quy về một phép kiểm “200 hay 403”. Cần **chứng minh đúng trust boundary** ở từng lớp: browser có thể đọc/gửi request hợp lệ theo CORS, unsafe cookie request phải có CSRF token, Bearer token phải được xác minh thật về chữ ký và claims, rồi mỗi actor chỉ được tác động tới tài nguyên có quyền. **MockMvc, decoder integration test và browser test bổ sung cho nhau**, không thay thế nhau.
