# Duy trì cấu hình có thể giải thích bằng mô hình nguy cơ và bằng chứng

## Mục tiêu và bối cảnh

Một cấu hình Spring Security không được xem là an toàn chỉ vì **ứng dụng khởi động thành công**, có một số HTTP security headers, hoặc một lệnh GET trả 200. Cấu hình bảo vệ HTTP và trình duyệt chỉ có thể giải thích, kiểm chứng và duy trì khi người triển khai biết rõ: **đang bảo vệ tài sản nào, chống lại kịch bản nguy cơ nào, ở ranh giới tin cậy nào, với giả định nào và bằng chứng nào cho thấy kiểm soát còn hiệu lực**.

Trong chương **Vận hành và giám sát** của dịch vụ **SPRING_SECURITY_HTTP_PROTECTION**, trọng tâm gồm CSRF, CORS, CSP và security headers, HSTS, HTTP firewall, cookie/session và các khác biệt giữa **Servlet** với **Reactive/WebFlux**. Ứng dụng thực thường nằm sau CDN, ingress, WAF hoặc reverse proxy, nên một policy viết trong **HttpSecurity** hoặc **ServerHttpSecurity** có thể khác policy mà browser thật nhận. Nhiều hệ thống còn phối hợp SPA dùng session cookie, API machine-to-machine dùng Bearer token, OAuth/OIDC callback, WebSocket/STOMP và HTML do CDN phục vụ. Chỉ một thay đổi route matcher, cookie scope hoặc cấu hình proxy có thể làm sai ranh giới bảo mật dù những file cấu hình trông không đổi.

Bài này hướng dẫn cách vận hành một **control–threat–evidence ledger** (sổ liên kết kiểm soát, nguy cơ và bằng chứng), viết security invariants có thể kiểm thử, review ngoại lệ, tổ chức kiểm thử nhiều tầng, theo dõi drift và quyết định rollout/rollback dựa trên bằng chứng. Những ví dụ Java minh họa chủ yếu cho Spring Boot 3.x / Spring Security 6.x và Java 17+, đồng thời chỉ rõ những API thay đổi theo phiên bản. **Không tự chọn phiên bản, repository hay request handler chỉ vì ví dụ này**: mỗi dự án phải kiểm tra dependency BOM và kiểm thử trên stack thực tế.

Sau bài học, người học có thể:

1. Xây dựng threat model từ **tài sản, tác nhân, entry points, trust boundaries, authentication mechanisms, tác động và giả định**.
2. Liên kết từng kiểm soát CSRF/CORS/CSP/HSTS/firewall/session với threat scenario và **security invariant** cụ thể.
3. Phân biệt **cấu hình trong ứng dụng**, **kết quả thực thi ở browser** và **chính sách cuối cùng tại public edge**.
4. Tổ chức **positive tests, negative tests, behavioral browser tests, edge probes và monitoring evidence** cho Servlet và Reactive.
5. Viết cấu hình có phạm vi rõ cho browser cookie-authenticated routes và machine-to-machine Bearer-only routes, không tạo đường xác thực cookie fallback ngoài ý muốn.
6. Lưu quyết định bảo mật với **owner, rationale, nguồn bằng chứng, phạm vi, expiry, residual risk và rollback criteria**.
7. Phân biệt config drift, framework-upgrade regression và incident thật với false positive, mà không suy diễn từ HTTP 400/403 đơn lẻ.
8. Điều chỉnh chính sách theo biến đổi threat model và bằng chứng sau triển khai, không lấy việc “không có báo cáo lỗi” làm bảo đảm an toàn.

## 1. Cấu hình có thể giải thích là cấu hình có lập luận kiểm chứng được

### 1.1. Ba câu hỏi cho mỗi quyết định

Với một dòng như:

~~~java
// Mã minh họa, không đưa vào production khi chưa phân tích route.
csrf(csrf -> csrf.ignoringRequestMatchers("/webhooks/**"))
~~~

Không thể đánh giá nếu chỉ nhìn thấy tên API. Phải trả lời:

- **Vì sao?** Webhook có thực sự không sử dụng browser ambient credentials, chỉ xác thực bằng chữ ký/Bearer được server kiểm tra và không có session-cookie fallback?
- **Phạm vi ở đâu?** Matcher chỉ bao các POST webhook được duyệt, hay vô tình bao toàn bộ controller/browser API?
- **Bằng chứng nào?** Test cho request thiếu chữ ký, chữ ký sai, cookie-only, path variants, method khác, và test không có business side effects.

Nếu chưa có câu trả lời, ngoại lệ này là **lỗ hổng quản trị cấu hình**, dù code vẫn compile.

### 1.2. Sổ liên kết nguy cơ, kiểm soát và bằng chứng

| Thành phần | Câu hỏi trả lời | Ví dụ cụ thể |
| --- | --- | --- |
| Asset | Giá trị nào cần bảo vệ? | Lệnh chuyển tiền, session đăng nhập, dữ liệu cá nhân |
| Actor | Ai có thể khởi phát request? | Browser hợp lệ, web origin khác, bot, đối tác webhook |
| Trust boundary | Ở đâu một nguồn kém tin cậy đi vào hệ thống? | Browser → CDN → gateway → Servlet/WebFlux |
| Threat scenario | Làm sao bị khai thác? | Cross-site POST mang session cookie tự động |
| Control | Cơ chế nào giảm nguy cơ? | CsrfFilter/CsrfWebFilter, SameSite, Origin-aware design |
| Invariant | Điều kiện bảo mật phải luôn đúng? | Unsafe browser POST thiếu token không tạo side effect |
| Evidence | Kiểm chứng ở đâu? | MockMvc/WebTestClient + browser test + database assertion |
| Assumption | Điều gì được tin nhưng cần theo dõi? | Không có cookie fallback ở Bearer-only chain |
| Residual risk | Những gì vẫn chưa được chặn? | XSS trong origin hợp lệ vẫn có thể thao tác như user |
| Owner / expiry | Ai chịu trách nhiệm và xem lại khi nào? | App Security, xem lại trước release/payment integration |

**Control tồn tại không đồng nghĩa invariant được bảo đảm.** Ví dụ, cấu hình CSRF có thể có nhưng securityMatcher không khớp route thực; CSP có thể được Spring phát ở API JSON trong khi HTML nằm tại CDN; HSTS có thể không được browser nhận do TLS termination hoặc thiếu HTTPS response.

### 1.3. Công thức lập luận hữu ích

Một quyết định bảo mật có thể diễn đạt:

~~~text
Vì [threat scenario T] tác động [asset A] tại [boundary B],
hệ thống áp dụng [control C] trong [scope S] với [assumption X].
Điều kiện bắt buộc [invariant I] được kiểm chứng bởi [tests E1/E2]
và theo dõi bởi [production signal M].
Nếu [evidence FAIL / assumption thay đổi], [owner O] phải
[stop rollout / rollback / remediate] trong [decision window].
Nguy cơ còn lại [R] phải được review rõ ràng.
~~~

Mẫu này áp dụng cả cho việc **bật** lẫn **không bật** một kiểm soát. Ví dụ, bỏ CSRF trên endpoint Bearer-only có thể hợp lý nếu xác thực **không dựa trên bất kỳ credential browser auto-send nào**. Nhưng bỏ CSRF vì endpoint “trả JSON”, “stateless” hoặc “dùng JWT” mà JWT nằm trong cookie là lý luận không đủ.

### 1.4. Cấu hình là giả thuyết; kết quả là bằng chứng

Bằng chứng có các mức:

1. **Source/config evidence:** SecurityFilterChain và property được review.
2. **Resolved-runtime evidence:** App thực nạp phiên bản và security chains/matchers nào.
3. **Integration evidence:** HTTP request được filter/handler xử lý như kỳ vọng, kể cả negative case.
4. **Browser evidence:** Cookie, CORS, CSP và redirect có hành vi đúng trong browser mục tiêu.
5. **Public-edge evidence:** Header, TLS/HSTS, WAF/gateway rewrite cuối cùng đến browser.
6. **Operational evidence:** Metrics, synthetic probes, drift checks và incident records theo thời gian.

Không dùng duy nhất một ảnh chụp màn hình config hoặc một curl GET để thay thế tất cả các mức này. Bằng chứng phải có **thời gian, revision và phạm vi hiệu lực**; test PASS ở staging tuần trước không tự chứng minh production hiện tại an toàn.

## 2. Xây threat model từ đường đi request thật

### 2.1. Xác định tài sản và các loại request

Một dịch vụ ví dụ có các nhóm sau:

| Nhóm request | Cơ chế xác thực thực | Tài sản | Nguy cơ liên quan |
| --- | --- | --- | --- |
| SPA tại app.example.com | Session cookie vào browser API | Hồ sơ, thanh toán, tài khoản | CSRF, XSS, session hijack |
| Spring MVC form | Session cookie + form login | Tài khoản, chức năng admin | CSRF, clickjacking, session fixation |
| Mobile/M2M API | Authorization Bearer do client chủ động gửi | API dữ liệu | Token theft, authz, rate abuse |
| Webhook từ provider | Signature/HMAC hoặc mTLS | Event nghiệp vụ | Forgery, replay, parser/matcher confusion |
| WebSocket/STOMP | Handshake/cookie/token theo thiết kế | Realtime commands | Origin misuse, CSRF handshake/message authorization |
| CDN phục vụ HTML | CDN/cache + browser | DOM, scripts, policy tại document | CSP thiếu/sai, asset tampering |
| Gateway/Ingress | Trusted proxy/forwarded headers | Routing, TLS host, canonical path | Host spoofing, path mismatch |
| Admin/Actuator | Network boundary + authn/authz | Secrets và khả năng quản trị | Unauthorized access và config leakage |

**Không suy diễn chỉ từ công nghệ**: M2M có thể gửi cookie vì một HTTP client library; SPA có thể dùng header Bearer thuần; webhook có thể tồn tại một legacy cookie fallback. Threat model phải kiểm chứng **request thực và security chain**.

### 2.2. Sơ đồ ranh giới tin cậy

~~~mermaid
flowchart TD
    A["Browser người dùng"] --> B["Public CDN / HTTPS edge"]
    X["Untrusted web origin / bot"] --> B
    B --> C["Gateway / WAF / reverse proxy"]
    C --> D["Spring Servlet hoặc WebFlux"]
    D --> E["SecurityFilterChain / SecurityWebFilterChain"]
    E --> F["Business API"]
    F --> G["Database / payment system"]
    B --> H["HTML và CSP headers tại CDN"]
    H --> A
    I["M2M client với signed/Bearer request"] --> C
    J["CSP collector / security logs"] <-->|"Events đã scrub"| D
~~~

**Boundary 1: browser và origin.** Cookie có thể được browser tự gửi theo domain/path/SameSite, trong khi CORS quyết định JavaScript ở origin khác có quyền đọc response. CSRF, CORS và cookie policy không thay thế nhau.

**Boundary 2: edge và app.** Proxy có thể thay Host, scheme, URI/encoding hoặc headers. Không tin X-Forwarded-* do client Internet tùy ý đặt; cấu hình trusted proxy và test public HTTPS edge.

**Boundary 3: security chain và handler.** URL normalization, securityMatcher và authorization mapping phải thống nhất; HTTP firewall/canonicalization giúp giảm khả năng các tầng hiểu path khác nhau.

**Boundary 4: app và observability.** CSRF token, JWT, session cookie, URL query và CSP script samples không được mặc định xuất hiện trong logs, metrics hoặc APM. Dữ liệu CSP reports là input không tin cậy.

### 2.3. Đánh giá nguy cơ bằng giả định và hậu quả

Không cần lập một bảng điểm “nguy cơ bằng xác suất × tác động” giả chính xác. Có thể dùng mức **high/medium/low** kèm lý do:

| Kịch bản | Hậu quả | Điều kiện khai thác | Priorities |
| --- | --- | --- | --- |
| Browser cookie-auth POST thiếu CSRF | Thao tác ngoài ý muốn | Cookie được gửi tự động, route cho mutation | Cao cho lệnh nhạy cảm |
| CDN HTML không có CSP | XSS có phạm vi rộng hơn khi bug tồn tại | Có injection/trusted script bị compromise | Cao, nhưng CSP không thay output encoding |
| Credentialed CORS phản chiếu Origin | Cross-origin đọc dữ liệu authenticated | Browser gửi cookie, backend trả allow origin tùy ý | Cao |
| HTTP firewall nới encoded slash không test | Authorization matcher bypass | Các tầng decode khác nhau | Cao khi route phân quyền theo path |
| HSTS thiếu ở HTTPS origin | Downgrade risk lần truy cập chưa được bảo vệ | Mạng/redirect không an toàn | Tùy bối cảnh và domain |
| CSP report chứa token trong log | Disclosure qua monitoring | Query/sample chứa secret và pipeline raw logging | Cao nếu có credential thật |
| Session không rotate sau login | Session fixation | Attacker kiểm soát pre-login session identifier | Cao tùy auth flow |
| CORS OPTIONS sai một header | Hỏng một SPA flow | Preflight bị chặn | Chủ yếu availability/integration |

Mục đích là **giải thích thứ tự ưu tiên và residual risk**, không tạo nhãn “secure” chỉ bằng việc đủ bộ header.

## 3. Thiết kế security invariants trước khi viết DSL

### 3.1. Invariant là điều kiện quan sát được

Một invariant tốt có **route scope rõ, điều kiện thử, kết quả bảo mật và nơi kiểm chứng**.

~~~text
ID: BROWSER-CSRF-001
WHEN:
  request = POST /api/orders
  authentication = cookie session hợp lệ
  CSRF header/form token = thiếu hoặc sai
MUST:
  status = denied theo contract
  order side effect = none
  security event = csrf_denied (nếu instrument)
EVIDENCE:
  MockMvc / WebTestClient + DB assertion + browser E2E
~~~

Điều này tốt hơn yêu cầu mơ hồ như **“ứng dụng phải có CSRF”**. Test phải bảo đảm khi request bị chặn **không có side effect**, chứ không chỉ so HTTP status.

### 3.2. Invariant catalog cho HTTP/browser protection

| ID | Invariant bắt buộc | Test tối thiểu |
| --- | --- | --- |
| CSRF-01 | Unsafe cookie-authenticated mutation không token bị chặn | POST/PATCH/DELETE negative; DB state unchanged |
| CSRF-02 | Login/logout token refresh hợp lệ với repository/handler | Bootstrap → login → refresh → POST |
| CORS-01 | Credentialed CORS chỉ cho explicit trusted origins | Trusted/untrusted OPTIONS + browser fetch |
| CORS-02 | OPTIONS preflight không bị redirect authentication | No-cookie preflight ở public edge |
| CSP-01 | HTML document thật có Enforce baseline đúng | Browser + edge response header |
| CSP-02 | Inline script fixture không được phép bị CSP chặn | Browser E2E; report-only behavior test riêng |
| HEADERS-01 | Frame embedding không được phép bị ngăn theo policy | iframe browser test, frame-ancestors |
| HSTS-01 | Public HTTPS origin phát HSTS được duyệt | HTTPS edge probe; không kiểm từ HTTP |
| FIREWALL-01 | Path/method bất thường không bypass chain matcher | StrictHttpFirewall + real-server negative |
| AUTHZ-01 | Token CSRF đúng không cấp quyền nghiệp vụ | Wrong role/scope/object ID test |
| SESSION-01 | Session ID/token lifecycle đúng auth transitions | Login/logout/session fixation test |
| COOKIE-01 | Session cookie có Secure/HttpOnly/SameSite/Path phù hợp | Browser Storage/response testing |
| M2M-01 | M2M chain không nhận cookie-only identity fallback | Negative cookie-only + Bearer tests |
| LOG-01 | Không có JWT/CSRF/session secrets trong logs/traces | Synthetic canary kiểm mọi sinks |
| DRIFT-01 | Policy revision tương thích trên app/edge/regions | Multi-region synthetic checks |

Trong một module dùng Servlet lẫn Reactive, **cùng một invariant có thể cần hai implementations và hai bộ test**. Không lấy việc HttpSecurity hoạt động làm bằng chứng ServerHttpSecurity tương đương về mọi mặt.

### 3.3. Đánh giá false positives và false negatives

- **False positive:** Test báo sai rằng policy yếu vì browser extension hoặc WAF test trên một route không thuộc scope.
- **False negative:** Test chỉ thấy header tồn tại nhưng không kiểm nội dung/hành vi; hoặc mock đã bypass filter chain.
- **Coverage gap:** Không test error pages, OAuth callbacks, CDN-served HTML hoặc sessions sau logout.
- **Observation gap:** CSP reports bằng 0 vì collector outage hoặc browser không gửi, chứ không phải CSP không có vi phạm.

Mỗi invariant cần ít nhất một **positive test** cho luồng hợp lệ và một **negative test** cho luồng bị cấm. Một policy từ chối tất cả requests có thể trông “an toàn” nhưng phá sản phẩm; một policy cho phép tất cả có thể làm test happy path xanh.

## 4. Viết control register và Architecture Decision Record

### 4.1. Tài liệu nhỏ, nhưng đủ truy vết và review

Một control register có thể do đội phát triển lưu cùng mã nguồn dưới dạng versioned document hoặc IaC. Ở đây chỉ minh họa **cấu trúc**, không yêu cầu tạo thêm file ngoài bài học.

~~~yaml
controlId: BROWSER-CSRF-001
title: Bảo vệ mutation bằng session cookie
owner: app-security
scope:
  origins:
    - https://app.example.com
  routes:
    - POST /api/browser/orders
    - PATCH /api/browser/profile
threat:
  scenario: Cross-site request tự mang session cookie
  asset: User orders and profile
  boundary: Browser to session-authenticated API
control:
  servlet: CsrfFilter with version-pinned repository and handler
  reactive: CsrfWebFilter with version-pinned repository
  assumptions:
    - Session cookie là ambient credential
    - Unsafe business routes được matching vào đúng chain
  residualRisk:
    - XSS trên trusted origin có thể thao tác như user
invariants:
  - Unsafe request thiếu hoặc sai token bị từ chối
  - Không tạo đơn hàng hoặc thay hồ sơ khi bị từ chối
evidence:
  - kind: integration-test
    id: csrf-negative-mutation
  - kind: browser-e2e
    id: login-refresh-first-post
  - kind: edge-probe
    id: browser-api-cookie-contract
decision:
  rationale: Chặn forged mutations mà browser cookie tự xác thực
  reviewer: security-owner
  reviewOn: authentication-mechanism-change
  exceptionExpiry: null
rollback:
  trigger: CSRF negative test FAIL hoặc lỗi diện rộng first POST
  restore: known-good app and frontend artifact pair
~~~

**Không đặt token, password, private key, raw Cookie, JWT, session ID hoặc PII vào control register**. Tài liệu này giữ reasoning và **đường dẫn logic đến bằng chứng**, không phải kho dữ liệu nhạy cảm.

### 4.2. Evidence record độc lập với lời mô tả

Mỗi lần chạy có thể ghi một record như:

~~~json
{
  "controlId": "BROWSER-CSRF-001",
  "invariantId": "CSRF-01",
  "testId": "csrf-negative-mutation",
  "environment": "staging",
  "applicationRevision": "build-r84",
  "springSecurityRevision": "6.x-pinned-by-bom",
  "edgePolicyRevision": "edge-v12",
  "outcome": "PASS",
  "observedAt": "example-timestamp",
  "owner": "app-security"
}
~~~

Giá trị version/date trong ví dụ **chỉ minh họa**. Trong triển khai thực, phải ghi resolved dependencies **chính xác**, build digest và thời điểm có ý nghĩa. Evidence record không có request payload thật, token hoặc identity người dùng.

Bằng chứng PASS cần trả lời: **kiểm thử nào, môi trường nào, đúng policy revision nào và đạt invariant nào?** Một test PASS với CSRF mock helper có thể chứng minh DSL filter logic nhưng chưa chứng minh login cookie trong browser; cần phân cấp evidence.

### 4.3. ADR cho quyết định đánh đổi

Một **Architecture Decision Record** tối thiểu nên gồm:

1. **Context:** Hệ thống đang dùng cookie, Bearer, SSR, SPA hay CDN-hosted HTML?
2. **Threat:** Bypass/CSRF/XSS/clickjacking/hardening nào được xử lý?
3. **Options:** Giữ default, cấu hình chặt hơn, chuyển kiến trúc BFF, bỏ dependency hoặc ngoại lệ có giới hạn.
4. **Decision:** Chọn policy, scope theo route/origin/stack, giải thích lý do.
5. **Expected effect:** Các request hợp lệ vẫn thành công, nguồn không tin cậy bị chặn.
6. **Evidence:** Danh sách security negative tests, browser tests, edge checks và operational signals.
7. **Residual risk:** Điều control không phòng được, chẳng hạn CSP không thay output encoding và CSRF không thay authorization.
8. **Exception conditions:** Owner, approver, expiry, sunset/migration plan, rollback.
9. **Revisit trigger:** Release major, đổi cách xác thực, thêm third-party script, đổi gateway, thay security dependencies.

### 4.4. Ngoại lệ là khoản nợ bảo mật cần hết hạn

Ví dụ một đối tác thanh toán yêu cầu iframe trên trang checkout: thêm **frame-src đúng host được duyệt và đúng HTML route** có thể có cơ sở. Nhưng không nên chuyển toàn ứng dụng sang frame-src * hoặc script-src 'unsafe-inline' vô hạn.

Mỗi ngoại lệ phải có:

| Thuộc tính | Ví dụ |
| --- | --- |
| Phạm vi | Chỉ HTML /checkout; không áp toàn origin nếu không cần |
| Lý do | Payment SDK cần frame của provider X |
| Asset/threat | Checkout integrity và clickjacking/XSS |
| Tài liệu nguồn | Vendor integration contract đã review |
| Owner | Payments team + security reviewer |
| Expiry | Trước kỳ review hoặc provider SDK migration |
| Evidence | Browser E2E payment sandbox + blocked untrusted frame |
| Rollback | CSP candidate trước đó + frontend artifact tương ứng |

Tránh dựa trên report count để tự thêm wildcard hoặc temporary exception không có owner. **Ngoại lệ cần được đánh giá lại khi giả định hoặc vendor thay đổi**, không biến thành định nghĩa mới của “mặc định an toàn”.

## 5. Servlet: minh họa cấu hình tách đúng browser cookie và Bearer-only

### 5.1. Hai authentication mechanisms phải có boundary rõ

Mô hình ở đây có:

- **/api/m2m/** chỉ dùng OAuth2 Resource Server với Bearer token **do client chủ động gửi**, không có cookie fallback.
- Các trang HTML và **/api/browser/** dùng session cookie/form login; unsafe requests phải đi qua CSRF.
- Một **fallback deny** cho request không khớp policy cấp quyền, không để endpoint mới trở thành public không chủ đích.

Ví dụ Spring Security Servlet, **mang tính hướng dẫn**, cần bổ sung OAuth2 JWT decoder, authentication provider, HTTPS, session/cookie properties và endpoint handlers phù hợp ứng dụng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletProtectionPolicies {

    @Bean
    @Order(1)
    SecurityFilterChain m2mBearerOnly(HttpSecurity http)
            throws Exception {

        return http
            .securityMatcher("/api/m2m/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserSession(HttpSecurity http)
            throws Exception {

        return http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "frame-ancestors 'none'; " +
                        "form-action 'self'")))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/assets/**", "/error").permitAll()
                .requestMatchers("/api/browser/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

**Điều kiện bảo mật then chốt:** Tắt CSRF ở chain Bearer-only **chỉ có cơ sở** khi API này **không chấp nhận bất kỳ browser ambient credential nào**, kể cả session cookie/refresh cookie được sử dụng để xác thực request. Cần test cookie-only request bị từ chối, không chỉ nhìn SessionCreationPolicy.STATELESS. Nếu JSON Web Token nằm trong cookie, tính chất stateless **không loại bỏ CSRF threat**.

CSP trong code này chỉ áp dụng **response mà chain Servlet phát**, không tự áp lên HTML được CDN ở host khác trả. Policy script-src 'self' là baseline minh họa và có thể chưa phù hợp SPA thật dùng nonce/hash, payment, OAuth popup hoặc external scripts. Phải review nguồn theo threat model.

### 5.2. CORS là một control khác CSRF

Với SPA ở https://app.example.com gọi API cookie ở https://api.example.com, cấu hình CORS allowlist cần **exact origins**, methods và headers:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource browserCors() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of(
        "https://app.example.com"));
    config.setAllowedMethods(List.of(
        "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of(
        "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration(
        "/api/browser/**", config);
    return source;
}
~~~

Các domain là **ví dụ**, không phải allowlist khuyến nghị cho hệ thống khác. Đối với browser credentialed CORS, không kết hợp **Access-Control-Allow-Origin: *** với **Allow-Credentials: true**. Đừng tự phản chiếu bất kỳ Origin nào từ client.

**Positive evidence:** OPTIONS trusted Origin được CORS xử lý và browser gửi actual POST với cookie+CSRF token phù hợp.

**Negative evidence:** OPTIONS từ untrusted Origin không cấp credentialed access; actual POST thiếu/sai CSRF vẫn bị từ chối dù OPTIONS trusted. Preflight và CSRF là **hai kiểm soát độc lập**.

### 5.3. CSRF repository và request handler phải có hợp đồng

Spring Security Servlet có các lựa chọn **HttpSessionCsrfTokenRepository** và **CookieCsrfTokenRepository**. Với SPA đọc raw XSRF cookie và gửi header X-XSRF-TOKEN, phải kiểm tra cách **CsrfTokenRequestHandler** xử lý token raw so với token **XOR-masked**.

Trên Spring Security **6.x**, không giả định có DSL **csrf.spa()**: API helper này xuất hiện ở dòng hỗ trợ tương ứng từ **7.0 Servlet**, cần xác nhận đúng dependency version. Khi ở 6.x, dùng cấu hình SPA handler thích hợp đã được kiểm thử, không tắt CSRF hoặc thay handler mặc định vô căn cứ.

Sau authentication/logout, token được lưu có thể bị clear và SPA cần **bootstrap token mới**. Contract evidence phải bao gồm:

~~~text
GET token anonymous -> unsafe login submit with valid token
authentication success -> token invalidated/rotated as designed
GET token authenticated -> unsafe business POST accepted
unsafe POST without token -> denied + no side effect
logout with active token -> transition -> new anonymous token if needed
~~~

Một 403 sau login có thể là stale token/CSRF handler mismatch, không phải bằng chứng tấn công. Không sửa bằng csrf.disable() hoặc ignoringRequestMatchers("/api/browser/**").

### 5.4. Session, cookie, HSTS và trusted proxy

Policy cần mô tả tối thiểu:

- Session cookie có **Secure, HttpOnly, SameSite, Path/Domain** phù hợp.
- Authenticated session lifecycle và **session fixation protection** (session ID rotation theo auth flow) đã test.
- Session store giữa pods/regions đúng topology và expiry policy.
- **HSTS** xuất hiện trên **public HTTPS response**, không đánh giá từ HTTP localhost hoặc giả lập scheme khi proxy chưa được kiểm soát.
- Reverse proxy chỉ truyền/trust X-Forwarded-Proto/Host từ **trusted ingress**; không dùng header tự khai từ Internet làm bằng chứng TLS.
- CSP **frame-ancestors, object-src, base-uri, form-action** được review theo HTML origin và auth flows.
- Các security headers mặc định của Spring Security được duy trì trừ khi có quyết định có kiểm chứng; **không bật CSP là một lựa chọn cần giải thích**, vì CSP không được tự phát trong mọi cấu hình.

Đừng đặt SameSite=None trên mọi cookie chỉ để chữa một lỗi CORS; nó có hậu quả riêng và thường cần Secure trong browser hiện đại. Đừng đặt HSTS includeSubDomains/preload khi chưa kiểm kê các subdomains còn dùng HTTP hoặc chưa có kế hoạch vận hành dài hạn.

## 6. WebFlux/Reactive: cùng invariant, khác DSL và HTTP semantics

### 6.1. Boundary theo SecurityWebFilterChain

WebFlux dùng **ServerHttpSecurity**, **SecurityWebFilterChain**, **ServerWebExchange**, **WebSession** và **CsrfWebFilter**. Không copy Servlet HttpSecurity, HttpServletRequest hay StrictHttpFirewall thành cấu hình Reactive.

Một mô hình tách Bearer-only và browser routes:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
@Order(1)
SecurityWebFilterChain reactiveBearerOnly(
        ServerHttpSecurity http) {

    return http
        .securityMatcher(ServerWebExchangeMatchers.pathMatchers(
            "/api/m2m/**"))
        .securityContextRepository(
            NoOpServerSecurityContextRepository.getInstance())
        .csrf(csrf -> csrf.disable())
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain reactiveBrowser(
        ServerHttpSecurity http) {

    return http
        .csrf(Customizer.withDefaults())
        .headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'self'; " +
                    "script-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "frame-ancestors 'none'")))
        .authorizeExchange(auth -> auth
            .pathMatchers("/", "/login", "/assets/**").permitAll()
            .pathMatchers("/api/browser/**").authenticated()
            .anyExchange().denyAll())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Đây là **đoạn cấu hình mẫu**, không phải một WebFlux application hoàn chỉnh: authentication provider, JWT decoder, session, CORS, CSRF token bootstrap và routing phải được bổ sung theo kiến trúc thật. Với cùng tên host/path, **chạy test chain selection** để chứng minh cookie-only request không được xác thực ở Bearer-only chain.

Nếu hệ thống là Reactive API không phục vụ HTML, CSP phải được phát tại **origin trả HTML**, không phải chỉ ở JSON WebFlux response. HTTP headers và session behavior cuối cùng vẫn cần kiểm chứng qua gateway/proxy.

### 6.2. Reactive CSRF và deferred token

Trên WebFlux, CSRF repository có thể dùng **WebSessionServerCsrfTokenRepository** hoặc **CookieServerCsrfTokenRepository**. Một GET bootstrap có thể cần truy cập **Mono<CsrfToken>** từ exchange để materialize token; không gọi **block()** trên event loop.

Một security invariant:

~~~text
Protected WebFlux POST with WebSession cookie:
  without CSRF token -> 403/no mutation
  with wrong CSRF token -> denied/no mutation
  with matching token -> permitted to reach authorization
  with matching token but insufficient role -> 403 authorization
~~~

Chú ý 403 authorization không đồng nghĩa CSRF, và token đúng không cấp quyền thao tác.

### 6.3. CORS Reactive không lấy cấu hình Servlet

WebFlux có **CorsWebFilter** và cấu hình Reactive CORS riêng. Đối với credentialed requests, vẫn phải áp exact trusted origins, allowed methods/headers và test **OPTIONS không gửi Cookie**, rồi actual request dùng cookie và CSRF token. Các beans Servlet như UrlBasedCorsConfigurationSource của Spring MVC **không tự chứng minh WebFlux có chính sách tương đương**.

### 6.4. HTTP firewall cũng khác stack

**StrictHttpFirewall** thuộc Servlet và FilterChainProxy; WebFlux đi qua Reactor Netty/Reactive HTTP parser, gateway và các WebFilters/routing. Không gọi mọi HTTP 400 WebFlux là RequestRejectedException từ StrictHttpFirewall. Khi threat model nói về encoded path, backslash, semicolon hoặc double encoding, evidence cần bao gồm **real server và gateway tests** của từng stack.

## 7. CSP và security headers: chứng minh browser áp dụng đúng policy

### 7.1. Threat model của CSP không chỉ là một danh sách host

CSP giảm khả năng thực thi một số loại mã hoặc tải tài nguyên trái phép khi có lỗ hổng injection. Nó **không thay output encoding, template escaping, DOM sanitization hoặc dependency integrity**. Script đã được CSP cho phép vẫn có quyền truy cập DOM theo khả năng của page, nên whitelist một script bên thứ ba là **quyết định tin cậy**, không chỉ sửa lỗi tài nguyên.

Một policy mẫu cho HTML không cần inline scripts:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'
~~~

**Không sao chép policy này cho mọi app**: thanh toán cần frame, OAuth/OIDC login có thể redirect/form submit khác host, SPA có connect-src API khác origin, WebSocket cần wss và CSS-in-JS có yêu cầu riêng. Phải kiểm kê **document routes, trusted scripts, styles, connect targets, frames, forms, workers và runtime bundler**.

### 7.2. Policy candidate: Report-Only trước, Enforce sau

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-uri /__security/csp-report
~~~

Ở đây **Enforce baseline** vẫn hoạt động, trong khi **Report-Only candidate** quan sát tác động của script-src chặt hơn. Browser có thể nhận **cả hai headers**. Không được nhầm Report-Only thành Enforce hoặc vô tình phát **hai Enforce policies** khác nhau rồi cho rằng cái sau ghi đè cái trước.

Một rollout nên có các giai đoạn:

1. Inventory nguồn tài nguyên trong các user flows thực.
2. Phát candidate **Report-Only** với report collector đã kiểm soát dữ liệu.
3. Phân loại reports thành dependency hợp lệ, app regression, extension noise và nguồn chưa tin cậy.
4. Sửa nguồn nguyên nhân ở code/build hoặc thêm ngoại lệ cụ thể có owner.
5. Bật **Enforce trên staging**, chạy browser E2E và negative script fixture.
6. Canary production trên routes/cohorts có thể định tuyến ổn định.
7. So JS errors, login/checkout success và CSP block rates với control.
8. Promote Enforce khi security+business gates PASS; có rollback cho CDN/HTML artifact/header policy.

**Report count = 0 không chứng minh policy an toàn**, bởi browser có thể không hỗ trợ reporting, collector có thể lỗi hoặc reports bị privacy settings chặn. Phải có synthetic canary tests và browser execution tests.

### 7.3. Nonce, hash và script lifecycle

Với HTML có inline scripts thật sự cần thiết, các lựa chọn:

- Chuyển mã sang **external JavaScript** cùng origin nếu có thể.
- Dùng **nonce CSPRNG mới theo từng response HTML** và khớp CSP header với script element. Nonce không được hardcode trong build artifact tĩnh hoặc shared-cache lâu dài.
- Dùng **hash** nếu nội dung script inline bất biến và hash được tạo từ đúng bytes/build artifact.
- Refactor onclick/onload inline event handlers thành addEventListener; nonce trên một script tag không tự cấp quyền cho inline event attributes.
- Gỡ eval/new Function khỏi production bundler khi có thể; đừng bật 'unsafe-eval' chỉ vì một dependency cũ.
- Dùng strict-dynamic, Trusted Types và SRI **theo browser support và threat model**, không xem chúng là thay thế cho kiểm duyệt trusted code.

Một invariant có thể kiểm:

~~~text
CSP-01:
  allowed application JS bundle -> executes
  inline script without approved nonce/hash -> blocked
  payment iframe on /checkout -> operates if reviewed
  unapproved frame/script origin -> blocked
  config has object-src 'none' and frame-ancestors per policy
  evidence -> staging browser + public HTTPS document headers
~~~

Không dựa duy nhất vào việc HTTP GET trả 200: HTML vẫn có thể trả 200 trong khi browser chặn toàn bộ JS chính.

### 7.4. Clickjacking, form action và nội dung được nhúng

**frame-ancestors** kiểm soát những parent origins được phép **nhúng document đang phục vụ**, trong khi **frame-src** kiểm soát **document hiện tại tải frame nào**. Trộn hai directive có thể làm team cấp sai quyền.

- Nếu app không bao giờ được nhúng, dùng frame-ancestors 'none' theo threat model.
- Nếu có nội dung được một đối tác nhúng, chỉ allowlist parent origins cụ thể, không wildcard tùy tiện.
- **X-Frame-Options** là lớp hỗ trợ legacy browser nhưng không biểu đạt đầy đủ allowlist phức tạp; kiểm tra compatibility.
- form-action có thể ảnh hưởng login/SSO/payment form. Một policy quá chặt có thể phá flow hợp lệ.
- Error pages, logout pages và HTML do gateway phục vụ cũng cần policy tương ứng.

**Evidence:** Test iframe từ trusted/untrusted parent, test payment sandbox và inspect header ở **response HTML có khả năng được nhúng**, không chỉ ở API fetch.

### 7.5. Báo cáo CSP cũng thuộc threat model bảo vệ dữ liệu

Một CSP report có thể chứa **document URI, blocked URI, referrer, original policy và script sample**, thậm chí URL có token hoặc dữ liệu cá nhân. Collector phải:

- Giới hạn request bytes, JSON depth, số reports và rate ở edge/server.
- Chấp nhận report-uri legacy và Reporting API format phù hợp browser mục tiêu.
- Chuẩn hóa route/source/directive thành nhãn hữu hạn **trước khi persist**.
- Không log raw report, Cookie, JWT, CSRF/XSRF token hoặc script sample.
- Không tự động cập nhật CSP allowlist từ reports do client không tin cậy gửi.
- Chỉ miễn CSRF **đúng POST collector** khi collector không dùng business session/auth; giữ CSRF cho các mutation còn lại.
- Ghi policy version/owner/review dates mà không đưa session ID vào reporting URL.

**CSP reporting là observability, không phải cơ chế xác thực người gửi và không phải browser enforcement.** Một attacker có thể gửi báo cáo giả để tăng counters hoặc gây tải.

## 8. Cookie, HSTS, CORS và proxy: mô hình nguy cơ theo ranh giới origin

### 8.1. CORS không phải bảo vệ CSRF

Browser CORS chủ yếu điều khiển **cross-origin JavaScript có quyền đọc response hay không** và kiểm soát một số loại request qua preflight. Nó không phải authorization; một cross-site form có thể gửi request trong các bối cảnh cookie policy cho phép mà không cần đọc response.

Một threat model đầy đủ cần xem:

~~~text
Request có thể gửi cookie/session tự động?
  Có -> CSRF protection cho unsafe mutation cần được đánh giá.
JavaScript khác origin có thể đọc credentialed response?
  Chỉ nếu CORS policy cho phép chính xác.
Origin nào phục vụ HTML và origin nào phục vụ JSON API?
  Có thể khác, nhưng cùng site chưa chắc cùng origin.
Cookie SameSite, Secure, Domain và Path?
  Quyết định browser thực tế gửi cookie trong ngữ cảnh nào.
~~~

Một preflight:

~~~http
OPTIONS /api/browser/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

không nên bị redirect tới login chỉ vì thiếu Cookie. Nếu OPTIONS bị chặn, browser có thể **không gửi actual POST**. Gắn nhãn lỗi này là MissingCsrfTokenException khi không có POST là sai chẩn đoán.

### 8.2. HSTS là quyết định phạm vi domain và vận hành HTTPS

HSTS chỉ được browser chấp nhận khi nhận qua **HTTPS hợp lệ**, và browser có thể ghi nhớ chính sách trong thời gian dài. Một ví dụ header:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Không áp dụng mặc định includeSubDomains hoặc preload khi chưa kiểm kê tất cả subdomains và khả năng phục vụ HTTPS tương ứng. Cần phân biệt:

- **Public HTTPS edge** và app có thể chạy HTTP nội bộ sau TLS termination.
- Browser chỉ thấy HSTS tại origin response cuối; một test ở localhost/HTTP không đủ.
- HSTS áp dụng cho domain scope, không giải quyết mixed authentication, CORS hoặc CSRF.
- max-age lớn tạo **rủi ro vận hành và rollback khó khăn**; thay đổi cần approval và kế hoạch lâu dài.
- Reverse proxy phải sanitize/điều khiển Forwarded/X-Forwarded-* từ clients không tin cậy.

**Invariant:** Public HTTPS response của HTML và API origins cần HSTS đúng policy trong phạm vi đã quyết định; redirect từ HTTP sang HTTPS hoạt động đúng; không có Host spoofing hoặc redirect sang host lạ.

### 8.3. Cookie design theo authentication threat

| Thuộc tính/cơ chế | Lý do | Bằng chứng |
| --- | --- | --- |
| Secure | Không gửi session cookie qua HTTP thường | Browser Network và HTTPS edge |
| HttpOnly | JavaScript không đọc session cookie | Cookie inspector + DOM/script negative |
| SameSite | Giảm một số bối cảnh cross-site cookie sending | Browser cross-site flow tests |
| Domain/Path | Giới hạn host/path nhận cookie | Browser cookie jar và request headers |
| Expiry/session TTL | Hạn chế phiên tồn tại không kiểm soát | Session expiry/relogin tests |
| Session ID rotation | Giảm session fixation risk | Login transition tests |
| Session store consistency | Không mất state giữa pods | Multi-instance tests |
| Logout invalidation | Kết thúc server-side session/token đúng | Logout → reused cookie denied |

HttpOnly không chặn mọi XSS: script độc hại chạy trong origin có thể gửi authenticated request dù không đọc cookie. SameSite không thay CSRF token khi threat model vẫn có nguy cơ. **JWT lưu trong cookie vẫn là ambient credential**, không miễn CSRF chỉ vì token format là JWT.

### 8.4. Same-site, cross-origin và cookie XSRF

Ví dụ **app.example.com** và **api.example.com** là **hai origins khác nhau** nhưng có thể thuộc **cùng site** theo schemeful site rules. JavaScript ở app.example.com không đọc được cookie host-only trên api.example.com chỉ vì cùng site. Nếu SPA dùng **CookieCsrfTokenRepository** và đọc cookie XSRF từ document.cookie, phải thiết kế rõ cookie Domain/Path và khả năng frontend đọc được **CSRF cookie** mà không mở HttpOnly session cookie.

Các mô hình thay thế gồm:

- **Same-origin BFF** để browser gọi API cùng origin, giảm complexity CORS/cookie.
- JSON **GET /api/csrf** trả token sau khi materialize, Cache-Control no-store.
- Cookie-to-header contract với request handler phù hợp raw/XOR token representations.
- Non-browser API dùng header Bearer và không dựa ambient cookie.

Không đẩy CSRF token vào URL, access logs hoặc shared cache. Với JSON token bootstrap cross-origin, credentials và CORS cần cùng chính sách an toàn.

### 8.5. Chẩn đoán lỗi qua các lớp độc lập

| Triệu chứng | Cần kiểm tra trước | Tránh kết luận vội |
| --- | --- | --- |
| SPA POST 403 sau login | Token mới sau authentication, cookie/session rotation | “Bị tấn công CSRF” |
| Browser chỉ thấy CORS error | OPTIONS, Allow-Headers, Origin, gateway | “Spring CSRF từ chối POST” |
| GET CSRF token thất bại | CSP connect-src, CORS, cache/no-store, route | “Token repo hỏng” |
| Session cookie không gửi | SameSite/Secure/Domain/Path, third-party blocking | “Authorization bị sai” |
| HTTPS public không có HSTS | CDN/ingress owner, redirect và TLS config | “Spring app chắc chắn thiếu code” |
| Authorization 403 với CSRF token đúng | Role/scope/object ownership | “CSRF token invalid” |
| CSP blocks payment iframe | frame-src, frame-ancestors và vendor sandbox | “CORS không cho thanh toán” |

**Không tắt CSRF/CORS/CSP/HSTS để làm đèn 403 biến mất**. Phải xác định tầng đưa ra quyết định và sửa đúng nguyên nhân.

## 9. HTTP firewall và URL normalization là rủi ro về cách diễn giải path

### 9.1. Servlet StrictHttpFirewall bảo vệ sự nhất quán request matching

Spring Security Servlet sử dụng **HttpFirewall** tại **FilterChainProxy**; **StrictHttpFirewall** có thể từ chối các biểu diễn URL, methods, host/header không được chấp nhận. Điều này giảm nguy cơ proxy, Servlet container, security matcher và MVC handler hiểu các path theo những cách khác nhau.

Nhóm cần kiểm:

- Encoded slash/backslash hoặc percent encoding khác thường.
- Semicolon/matrix params, dot segments và nhiều dấu phân tách.
- Chuỗi có control characters hoặc path normalization mơ hồ.
- Unsupported methods như TRACE theo policy.
- Host spoofing và forwarded-header trust boundary.
- SecurityMatcher phân tuyến browser cookie chain và Bearer-only chain.

Một request bị firewall từ chối có thể phát sinh **RequestRejectedException trước MVC controller**. Không trông chờ @ControllerAdvice thấy mọi rejection. Cũng không đánh đồng **HTTP 400 tổng** với confirmed Spring firewall event: gateway hoặc Servlet container có thể chặn trước ứng dụng.

### 9.2. Đánh đổi khi nới firewall

Thấy một legacy client gặp 400 khi URL chứa semicolon **không phải lý do đủ để bật setAllowSemicolon(true) toàn cục**. Tương tự với encoded slash hoặc backslash. Phải:

1. Chứng minh case đến Spring firewall hay bị proxy/container reject.
2. Định nghĩa canonical path và path parameter semantics thực tế.
3. Xác minh securityMatcher/authorization và MVC mapping cùng hiểu một route.
4. Đánh giá đổi client contract hoặc chuyển dữ liệu sang query/body trước khi nới.
5. Viết negative tests cho path variants nguy hiểm và authorization bypass.
6. Ghi exception phạm vi hẹp, owner, approver, sunset và rollback trigger.
7. Test qua **real gateway + Servlet connector**, không chỉ MockMvc.
8. Giữ metrics **source-aware**: WAF, connector, Spring firewall, authorization và CSRF là các nhóm khác nhau.

Nếu một URL bị gateway decode trước khi đến ứng dụng, StrictHttpFirewall có thể **không còn thấy raw encoded representation**; test cần đi qua đúng public topology.

### 9.3. WebFlux không có cùng HttpFirewall Servlet

Đối với Reactive, kiểm tra **Reactor Netty/HTTP server parser, WebFlux routing, Gateway WebFilters và SecurityWebFilterChain**. Không dùng lớp StrictHttpFirewall của Servlet như lời giải cho WebFlux. Dù cùng một invariant “không cho path variant bypass authorization”, đường triển khai và bằng chứng khác nhau.

### 9.4. Không để monitoring tạo một lỗ hổng mới

RequestRejectedException có thể chứa raw request URI hoặc control characters trong message. Không log nguyên exception.getMessage(), query, Cookie, Authorization, CSRF token hay user-supplied Host. Dùng reason categories hữu hạn **confirmed/unclassified**, route group và release. Với CSP reports, áp cùng data minimization và input limits.

Một API bị firewall reject **không chứng minh request là tấn công**, vì lỗi client/gateway vẫn có thể tạo URL sai. Một API pass firewall **không chứng minh được cấp quyền**: authorization, CSRF, validation và business invariants vẫn phải tiếp tục.

## 10. Ma trận bằng chứng đa tầng: test đúng thứ cần chứng minh

### 10.1. Quy tắc “đúng tầng, đúng điều kiện, đúng kết quả”

| Bằng chứng | Chứng minh tốt | Không thể chứng minh một mình |
| --- | --- | --- |
| Unit test policy normalizer | Logic parser, route grouping, allowed values | Gateway/browser thật |
| Spring Test MockMvc | Servlet FilterChainProxy, CSRF/authz, headers của app | CDN headers, SameSite browser enforcement |
| WebTestClient | Reactive filters, CSRF/authz, CORS WebFlux | Servlet StrictHttpFirewall, Netty raw parser khi in-memory |
| Embedded real server | HTTP parsing + app security integration | Public CDN/WAF rewrite |
| Browser E2E | Cookie/CORS/CSP/HSTS hành vi trong browser mục tiêu | Mọi browser, mọi region, server incident |
| Public-edge HTTPS probe | CSP/HSTS/redirect/Host trên response cuối | User business authorization |
| Synthetic negative probe | Rejected request theo contract | Tất cả biến thể tấn công |
| Production metrics | Thay đổi theo release/route/region | Động cơ attacker hoặc nguyên nhân chỉ từ status |
| Source review / ADR | Rationale, scope, assumptions và owner | Runtime hay browser thực hiện đúng |

**Một test code xanh không bằng chứng một cách tự động cho public-edge invariant.** Ví dụ, MockMvc thấy Content-Security-Policy nhưng CDN trả HTML mà không có header. Ngược lại, một browser nhận CSP đúng vẫn không chứng minh Spring CsrfFilter đang hoạt động.

### 10.2. Bằng chứng cần cả positive và negative

Ví dụ control CORS:

~~~text
POSITIVE:
  origin = https://app.example.com
  method = POST
  requested header = x-csrf-token
  preflight -> cho phép theo policy
  actual cookie-auth POST với CSRF -> hoàn tất nghiệp vụ

NEGATIVE:
  origin = https://untrusted.example.net
  credentialed preflight -> không được cấp CORS access
  actual cookie-auth POST thiếu CSRF -> bị chặn
  business state -> không đổi
~~~

Ví dụ control CSP:

~~~text
POSITIVE:
  frontend JS bundle đã review -> thực thi
  approved payment iframe -> hoạt động trên /checkout

NEGATIVE:
  script fixture inline không nonce/hash -> bị Enforce chặn
  untrusted frame/script origin -> không được chạy/tải
  policy baseline -> object-src 'none', frame-ancestors theo thiết kế
~~~

**False positive phổ biến:** chỉ viết negative test rồi thấy mọi request bị chặn, kể cả request hợp lệ. **False negative phổ biến:** chỉ test status 200, trong khi security header mất hoặc data mutation xảy ra trước 403. Vì vậy hai chiều là bắt buộc.

### 10.3. Chứng minh security chain thực sự được chọn

Một chính sách có thể có CSRF trong browser SecurityFilterChain nhưng route /api/browser/orders bị gateway rewrite thành /api/m2m/orders. Nếu matched vào Bearer-only chain có CSRF disabled, threat model bị vi phạm.

Bộ case cần:

| Request | Expected chain | Expected result |
| --- | --- | --- |
| GET /login | Browser | Public login page theo policy |
| POST /login thiếu CSRF | Browser | Denied |
| POST /api/browser/orders với session, thiếu CSRF | Browser | Denied, no mutation |
| POST /api/browser/orders với session, token đúng | Browser | Authz/business validation tiếp tục |
| POST /api/m2m/jobs chỉ Cookie | Bearer-only | Unauthorized |
| POST /api/m2m/jobs với Bearer hợp lệ | Bearer-only | Đến đúng authorization/handler |
| POST /api/browser/orders với Bearer nhưng không session | Browser | Không tự bypass CSRF theo chính sách |
| Unexpected /internal/** route | Fallback | Deny, không thành public |
| Encoded path hoặc separator variant | Firewall/authorized chain | Không rơi sang chain có quyền yếu hơn |
| POST /api/m2m/jobs có cookie nhưng không Bearer | Bearer-only | Cookie không thay được Bearer |

**Request matcher phải kiểm sau proxy rewrite**. Một Test Slice mock có thể chạy qua security chain nhưng không tái hiện path canonicalization ở gateway. Dùng real server/edge tests cho những biến thể có nguy cơ cao.

## 11. Servlet: MockMvc test kiểm tra cấu hình, không chỉ trả 200

Các ví dụ bên dưới dùng **spring-security-test**, Spring Boot 3 và class có **MockMvc mvc** được wire với Spring Security. Giả định các routes thật đã được dựng: /api/browser/orders dùng session; /api/m2m/jobs yêu cầu Bearer; /api/browser/csrf là endpoint token bootstrap nếu ứng dụng có. Cần điều chỉnh expected status theo business controller và authorization thật.

### 11.1. Cookie browser POST phải qua CSRF

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BrowserCsrfInvariantTests {

    @Autowired MockMvc mvc;

    @Test
    void cookieAuthenticatedPostWithoutCsrfIsDenied()
            throws Exception {
        mvc.perform(post("/api/browser/orders")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndAuthorizationCanReachBusinessHandler()
            throws Exception {
        mvc.perform(post("/api/browser/orders")
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Đây là **kiểm thử filter behavior**, không tự chứng minh login/cookie thật; helper user() tạo test security context. Phải thêm assertion về **số đơn hàng không tăng** ở case denied, và integration test với real session cookie/token lifecycle cho browser. Nếu Alice không có quyền hoặc controller trả 201, test positive cần điều chỉnh theo hợp đồng nhưng không được đổi thành permitAll để làm test xanh.

### 11.2. Bearer-only chain không chấp nhận cookie fallback

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;

// Đoạn trong class có MockMvc mvc và route M2M thật.
@Test
void sessionCookieAloneCannotAuthenticateM2m()
        throws Exception {
    mvc.perform(post("/api/m2m/jobs")
            .cookie(new Cookie("JSESSIONID", "synthetic-cookie")))
        .andExpect(status().isUnauthorized());
}

@Test
void validBearerSecurityContextReachesM2mHandler()
        throws Exception {
    mvc.perform(post("/api/m2m/jobs")
            .with(jwt()))
        .andExpect(status().is2xxSuccessful());
}
~~~

**Quan trọng:** jwt() là test helper, **không chứng minh JWT signature, issuer, audience và expiry verification** của production decoder. Test với signed token thật và resource-server configuration trong integration suite. Case cookie-only phải không được xác thực ngay cả khi client gửi cookie từ một browser login session.

### 11.3. Kiểm tra headers do Servlet tạo

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Đoạn thân test trong app có GET / trả HTML.
mvc.perform(get("/"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("object-src 'none'")))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("frame-ancestors 'none'")));
~~~

Test header **không chứng minh CSP được browser thực thi**, và không áp cho HTML ở CDN riêng. HSTS có thể chỉ được viết trên request được Spring coi là HTTPS; vì vậy dùng **HTTPS public-edge probe** để chứng minh HSTS thực thay vì ép MockHttpServletRequest scheme rồi xem đó là bằng chứng cuối.

### 11.4. CORS preflight có origin được duyệt

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mvc.perform(options("/api/browser/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers",
            "content-type,x-csrf-token"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://app.example.com"));
~~~

Preflight không cần browser session cookie. Bổ sung negative test cho **untrusted Origin**, chứng minh không có credentialed browser access. CORS cho phép preflight không đồng nghĩa unsafe POST được bỏ CSRF.

### 11.5. Login/logout và SPA token representation cần full-flow test

~~~text
1. GET /api/browser/csrf -> token materialized + no-store.
2. POST /login with current token + session cookie.
3. After login success -> GET fresh CSRF token.
4. POST /api/browser/orders with same session and new token -> success.
5. POST same route without token -> denied/no mutation.
6. POST /logout with current token -> logout/session transition.
7. Stale token after logout -> rejected or requires new auth flow.
8. Multi-tab and session-expiry behavior -> defined client recovery.
~~~

**Không in token trong CI logs.** Với Spring Security 6.x, phân biệt **raw cookie token** và **XOR-masked request attribute token**; tests phải dùng repository/handler thật của app. Một frontend POST 403 ngay sau login thường là token stale hoặc session mismatch, không phải lý do tự động tắt CSRF.

## 12. WebFlux: WebTestClient và kiểm chứng behavior đa chain

### 12.1. CsrfWebFilter vẫn hoạt động trên cookie browser route

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import java.util.Map;

// Đoạn trong WebFlux test context với WebTestClient.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/browser/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice"))
    .mutateWith(csrf())
    .post().uri("/api/browser/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Bổ sung integration tests dùng real **WebSession cookie**, authentication success/logout và CSRF token bootstrap. Spring Security test helpers không xác minh browser SameSite/CORS hay session ID rotation.

### 12.2. Bearer-only route cần kiểm tra cookie-only không được authenticate

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import java.util.Map;

// Không mutateWith(mockUser()) vì test này cần kiểm chứng
// cookie-only không tạo authentication context trong M2M chain.
webTestClient.post().uri("/api/m2m/jobs")
    .cookie("SESSION", "synthetic-cookie")
    .bodyValue(Map.of("job", "demo"))
    .exchange()
    .expectStatus().isUnauthorized();

webTestClient.mutateWith(mockJwt())
    .post().uri("/api/m2m/jobs")
    .bodyValue(Map.of("job", "demo"))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Cookie name/session policy phải đổi theo WebFlux app thật. mockJwt() **không thay test xác thực chữ ký JWT thực**; còn route handler phải tồn tại và user/test claims có quyền tương ứng.

### 12.3. Reactive CORS và policy headers

~~~java
import org.springframework.http.HttpHeaders;

// GET HTML được WebFlux app thực sự phục vụ.
webTestClient.get().uri("/")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches(
        "Content-Security-Policy",
        ".*object-src 'none'.*");

// OPTIONS trusted Origin cho browser API.
webTestClient.options().uri("/api/browser/orders")
    .header(HttpHeaders.ORIGIN, "https://app.example.com")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
        "content-type,x-csrf-token")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://app.example.com");
~~~

Phải cấu hình **Reactive CORS source** thật để OPTIONS pass; sample ở phần 6 không cấu hình nguồn CORS. Test header chỉ áp lên **HTML do WebFlux phục vụ**, không suy ra HTML/CDN khác đã được bảo vệ.

### 12.4. HTTP parser và WebFlux tests không phải Servlet firewall tests

Nếu một URI chứa semicolon, encoded slash hoặc double encoding:

- WebTestClient in-memory có thể không tái hiện raw request-target giống Reactor Netty.
- Reactor Netty có thể reject trước ServerWebExchange.
- WebFlux gateway có thể rewrite URL trước application.
- Servlet StrictHttpFirewall có semantics khác.

Vì vậy invariant về path matcher cần thêm **real HTTP server + gateway synthetic probes**, không tự diễn giải 400 từ WebFlux là RequestRejectedException của Servlet.

## 13. Bằng chứng ở production: telemetry an toàn, định nghĩa đo lường và độ tin cậy

### 13.1. Tách kết quả HTTP khỏi lý do từ chối đã xác nhận

Một request 403 có thể do **CsrfFilter, AuthorizationFilter, WAF hoặc gateway**. Một request 400 có thể do **StrictHttpFirewall, HTTP parser hoặc JSON validation**. CSP violation report có thể do browser gửi, do extension, hoặc bị client giả lập.

Do đó không thiết kế một counter duy nhất tên security_attacks_total lấy từ toàn bộ 400/403. Thay vào đó:

~~~text
http_requests_total
  source=http-server | edge-gateway
  status_class=2xx | 3xx | 4xx | 5xx

http_security_decisions_total
  control=csrf | authorization | authentication | firewall | cors | waf
  decision=allow | deny | error
  reason=bounded_reason_code
  evidence_level=confirmed | inferred | unclassified
~~~

Tên trên là **schema đề xuất**, không phải metric mặc định của Spring Security. Tập nhãn phải hữu hạn, được review theo thực tế. **reason=invalid_csrf** chỉ được dùng khi handler thật xác nhận CSRF exception, không gán cho mọi 403.

### 13.2. Cấu trúc một audit event an toàn

~~~json
{
  "event": "http.security.decision",
  "layer": "spring-security-servlet",
  "control": "csrf",
  "decision": "denied",
  "reason": "invalid_or_missing_actual",
  "routeGroup": "orders",
  "methodClass": "UNSAFE",
  "statusClass": "4xx",
  "release": "build-r84",
  "policyRevision": "csrf-v3",
  "requestId": "req-8e5a"
}
~~~

Các giá trị **routeGroup, reason, policyRevision** phải đến từ mapping và config đã được review. Không dùng raw path/userId/query làm route group. Request ID dùng để nối logs/traces **có phân quyền**, không dùng làm metric label.

Không lưu:

- CSRF token thực hoặc token masked/XOR, Cookie/JSESSIONID, Authorization/JWT, refresh token.
- HTTP request/response body chứa password, PII hoặc business payload.
- CSP script-sample, document URL/query/referrer, original-policy nhận từ report không tin cậy.
- RequestRejectedException.getMessage() với raw request URI/encoded input.
- Origin/Host/User-Agent thô được client điều khiển làm metric label.
- IP/user ID/session ID vào Prometheus dimensions.
- Traces baggage chứa user credential hoặc request body.

**Data minimization phải nằm trước khi truyền dữ liệu tới APM/SIEM**, không chỉ là việc ẩn cột ở dashboard. Nếu parser bị lỗi, exception logger vẫn không được dump raw report/body.

### 13.3. Các chỉ số cần có để bảo vệ được lý luận

| Control/invariant | Production signal | Chú ý diễn giải |
| --- | --- | --- |
| CSRF-01 | Confirmed CSRF deny rate theo route/release | Một spike có thể là regression hoặc probing |
| CORS-01 | OPTIONS failure theo trusted/untrusted origin class | Preflight fail không phải POST CSRF deny |
| CSP-01 | CSP Enforce header contract PASS ở HTML HTTPS edge | Không chỉ test API JSON CSP |
| CSP-02 | Synthetic browser negative script fixture PASS | Report-Only không chặn khi không có baseline Enforce |
| HSTS-01 | HTTPS edge HSTS policy version/pass | HSTS chỉ có hiệu lực sau HTTPS, browser cache quan trọng |
| FIREWALL-01 | Confirmed firewall deny và path probe PASS | 400 từ container/WAF không có nghĩa Spring firewall reject |
| AUTHZ-01 | Deny by policy group + negative object access tests | CSRF token đúng không cấp quyền dữ liệu |
| SESSION-01 | Login/logout/first unsafe POST completion | Cookie policy có thể khác giữa browsers |
| M2M-01 | Cookie-only request synthetic deny | Không gắn nhãn Bearer-only nếu cookie fallback còn |
| LOG-01 | Redaction synthetic canary PASS cho mọi sink | Dashboards ẩn dữ liệu không đủ nếu APM vẫn chứa |
| DRIFT-01 | Policy revision ở edge/app/region đồng nhất | Một vùng có thể còn cấu hình cũ |

### 13.4. Tỷ lệ có mẫu số và phân biệt mục đích

Ví dụ:

\[
\text{CSRF deny rate} =
\frac{\text{Unsafe requests bị CsrfFilter/CsrfWebFilter từ chối}}
{\text{Unsafe requests thực sự đi vào CSRF-protected routes}}
\]

Một tỷ lệ chỉ có ý nghĩa nếu biết **mẫu số**. Đếm toàn bộ CDN requests làm mẫu số có thể che giấu lỗi một route nhỏ; đếm chỉ session lỗi có thể phóng đại. Cần so **route group, release, browser family và user-flow success** cùng sample size.

Với CSP, **số CSP reports không phải số XSS attacks**: browser reporting support khác nhau, extension noise, collector outage, sampling và report forgery làm số lượng biến dạng. Cần browser E2E, client errors và CSP header contract kèm theo.

### 13.5. Data retention và độ mới của evidence

Một chứng cứ ghi PASS phải có:

- Build/release artifact revision thật.
- Resolved Spring Security dependency/Java/runtime version.
- Security policy revision, origin/route scope và stack Servlet/Reactive.
- Test ID + expected invariant + result.
- Environment, observed-at timestamp và nguồn phát.
- Owner, reviewer, hiệu lực và lý do cần chạy lại.
- Link đến aggregate/synthetic evidence, **không chứa token/session của người dùng**.

Khi thay đổi CDN/proxy, dependency, authentication mechanism hoặc browser behavior, **bằng chứng cũ có thể không còn áp dụng**. Thiết kế lịch chạy lại các invariants quan trọng và báo **evidence stale/unknown** thay vì tiếp tục hiển thị PASS từ nhiều tháng trước.

## 14. Quản lý thay đổi: config provenance, exceptions và policy drift

### 14.1. Provenance của policy phải truy được đến từng layer

Một request có thể nhận policy từ nhiều nơi:

~~~mermaid
flowchart LR
    A["Git ADR + threat model"] --> B["Application config"]
    A --> C["CDN / WAF / ingress policy"]
    B --> D["Spring Security resolved chains"]
    C --> E["Public HTTPS edge"]
    D --> E
    E --> F["Browser runtime behavior"]
    F --> G["Synthetic probes + metrics"]
    G --> H["Review / risk register"]
~~~

**Source of truth** không chỉ là YAML application.properties. Nó phải chứa **ai quyết định, vì sao, có scope nào, policy được deploy qua những tầng nào và bằng chứng cuối đã thấy ở đâu**.

Cần đối chiếu:

1. Code review và branch/commit đã được phê duyệt.
2. Artifact digest/dependency lock hoặc BOM.
3. Runtime-resolved security chain order và filter presence.
4. CDN/ingress/WAF policy revision.
5. Browser HTML origin response headers.
6. Synthetic security probes kết hợp business E2E.
7. Các exceptions còn hiệu lực/đã hết hạn và risk acceptance.

### 14.2. Cấu hình không được lùi về mức yếu khi thiếu biến

Anti-pattern:

~~~java
// ANTI-PATTERN: thiếu config có thể làm bảo vệ bị bỏ.
boolean csrfEnabled =
    Boolean.parseBoolean(System.getenv("CSRF_ENABLED"));

// Nếu thiếu biến, nhiều runtime cho giá trị false.
// Không thiết kế disabled là default ngoài ý muốn.
~~~

Thay bằng **typed configuration có validation fail-fast**, ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.http-protection")
public record HttpProtectionPolicy(
    String mode,
    String revision
) {
    public HttpProtectionPolicy {
        if (!"enforce".equals(mode)
                && !"report-only".equals(mode)) {
            throw new IllegalArgumentException(
                "Unsupported protection mode");
        }
        if (revision == null || revision.isBlank()) {
            throw new IllegalArgumentException(
                "Policy revision is required");
        }
    }
}
~~~

Đây là **ví dụ validation cho một policy có mode** (phù hợp CSP transition), **không áp một công tắc report-only cho toàn CSRF/authorization/firewall**. Các kiểm soát như CSRF không có khái niệm Report-Only tương đương CSP; đừng tạo biến chung **securityMode=report-only** rồi vô tình tắt enforcement ở mọi lớp.

Trong production, cần validate cả giá trị directives, trusted origins, URL matchers, token repository, session/cookie policy và các cặp config không hợp lệ. Một String check đơn giản không thay policy linter/threat review.

### 14.3. Linter và policy diff trong CI

Một security policy gate có thể áp các rule:

| Rule | Kết quả khi vi phạm |
| --- | --- |
| Browser cookie-auth API chuyển sang csrf.disable() | Fail hoặc bắt buộc security review có test |
| CORS Allow-Origin wildcard với credentials | Fail |
| New securityMatcher làm route chuyển sang weaker chain | Fail negative matchers test |
| CSP Enforce mất object-src/base-uri/frame-ancestors cần thiết | Fail header contract |
| CSP bật unsafe-inline/eval không có ngoại lệ có hạn | Block promotion |
| HSTS includeSubDomains/preload thay đổi không có domain inventory | Security approval bắt buộc |
| StrictHttpFirewall nới encoded separators/semicolon | Negative authorization suite và review bắt buộc |
| Session cookie mất Secure/HttpOnly | Fail browser/edge tests |
| JWT cookie fallback xuất hiện trong Bearer-only chain | Fail cookie-only test |
| HTTP security logs bắt đầu ghi raw headers/body/tokens | Fail synthetic canary redaction |
| Public HTTPS edge mất CSP/HSTS dù source code còn | Fail edge contract |
| Exception quá expiry hoặc thiếu owner | Fail promotion hoặc yêu cầu renewal có phê duyệt |

Một linter cần kiểm **resolved config hoặc deploy artifact** khi có thể, không chỉ grep source. Ví dụ, một CSP header có thể được gateway thêm hoặc strip ngoài JVM.

### 14.4. Policy drift không chỉ là khác file cấu hình

Các kiểu drift:

- Pod A và pod B chạy các **Spring Security minor versions** hoặc CSRF handlers khác.
- Browser HTML CDN còn CSP Enforce revision cũ, app đã dùng bản mới.
- Một region ingress mất HSTS hoặc sửa CORS Allow-Headers.
- Canary ở production vô tình bật Report-Only thay Enforce.
- Một route chuyển từ session cookie auth sang Bearer/cookie hybrid nhưng threat model chưa cập nhật.
- Một service dùng **StrictHttpFirewall** được nới nhưng service khác không.
- Session store hoặc key rotation khác giữa pods khiến CSRF/session errors tăng.
- Vendor payment/captcha đổi host mà không review allowlist.

Không đo drift chỉ bằng cách so **application.yaml**. Cần synthetic probes ở edge/regions, resolved dependency fingerprints và runtime chain-selection tests.

### 14.5. Evidence gate cho rollout/canary

~~~text
GATE 1: Threat model + scope / assumptions được review
GATE 2: Config/linter + resolved dependency / policy revision PASS
GATE 3: Security negative tests + no side effects PASS
GATE 4: Positive browser/API business flows PASS
GATE 5: Public HTTPS CSP/HSTS/CORS/cookie contract PASS
GATE 6: Canary/control monitored, legitimate SLO stable
GATE 7: No telemetry secret leaks, rollback ready
PROMOTE: chỉ khi gates quan trọng PASS
STOP: khi invariant bị phá, auth/checkout nghiêm trọng FAIL,
      hoặc policy drift tăng blast radius
~~~

**Không dùng số lượng cảnh báo bằng 0 làm điều kiện duy nhất**. Nếu CSP collector mất kết nối, reports bằng 0 là thiếu quan sát. Nếu traffic bot làm 403 tăng, không mặc định rollout làm suy yếu cấu hình. Quyết định cần bằng chứng từ cả **security tests** và **luồng người dùng hợp lệ**.

### 14.6. Rollback cũng phải có mô hình nguy cơ

Một rollback chỉ đổi JAR có thể chưa sửa sự cố nếu frontend bundle/CDN CSP, CORS policy hoặc gateway rewrite còn ở revision mới. Ngược lại, rollback cookie/session implementation có thể khiến **browser sessions còn lại** có token/cookie incompatible.

Cần lưu **known-good tuple**:

~~~text
frontend-html-revision
application-artifact-digest
spring-security-bom-revision
security-policy-revision
gateway-waf-cdn-policy-revision
session-cookie-storage-policy
synthetic-evidence-bundle
~~~

Sau rollback, chạy lại cả:

- Legitimate login → token refresh → unsafe business POST.
- Unsafe POST thiếu CSRF bị chặn, không side effect.
- Bearer-only route không chấp nhận cookie-only.
- CSP Enforce/browser fixture, HSTS/CORS at public HTTPS edge.
- URL normalization negative tests và authz across chains.
- Telemetry không lưu credentials.

**Rollback thành công không đồng nghĩa pod healthy**. Nó phải khôi phục những invariants quan trọng và user flows phù hợp.

## 15. Runbook: ra quyết định từ evidence thay vì phản ứng với mã lỗi

### 15.1. Runbook A — Sau release, SPA login được nhưng first POST 403

**Quan sát:** Tỷ lệ POST đầu tiên sau login thành công giảm; tổng CSRF 403 tăng.

1. Xác minh request đi đến **CsrfFilter/CsrfWebFilter** hay bị gateway/WAF/authorization chặn; không phân loại chỉ từ status.
2. So frontend/backend release, CSRF repository và token request handler resolved configuration.
3. Kiểm tra GET CSRF bootstrap đã **materialize token**, có no-store và cùng session cookie với POST không.
4. Kiểm tra auth success có làm clear token cũ không, SPA có lấy token mới trước POST không.
5. Với cookie-to-header, xem **raw XSRF cookie vs XOR-masked representation**, header name và cookie scope.
6. Kiểm tra CORS preflight có thành công; nếu browser không phát actual POST, đó không phải CSRF deny ở POST.
7. Tái hiện bằng test account và browser thật, không in CSRF token/session ID vào ticket.
8. Nếu flow trọng yếu bị ảnh hưởng, stop canary hoặc rollback **frontend+backend/policy tuple** tương thích.
9. Chạy lại negative POST thiếu token và positive POST hợp lệ; không “sửa” bằng csrf.disable().
10. Cập nhật evidence record và ADR nếu architecture/assumption đã thay đổi.

**Kết luận được phép:** “Có regression trong vòng đời hoặc contract CSRF của flow X” sau khi đã có bằng chứng. Không gắn nhãn “CSRF attack” cho user hợp lệ chỉ vì 403.

### 15.2. Runbook B — HTTP 403 tăng nhưng login/checkout không bị ảnh hưởng

1. Tách confirmed CSRF denials, authorization denials và WAF/gateway 403.
2. Nhìn route groups, methods, status class, release và security decision categories **đã scrub**.
3. So với baseline và security synthetic probes, tránh dựa trên IP/User-Agent đơn lẻ.
4. Nếu request bất thường bị firewall/WAF chặn và user flows vẫn ổn định, **không tự động nới firewall hoặc tắt CSRF**.
5. Nếu logs chứa request-target raw, không bật verbose logging rộng rãi để thu thêm; dùng controlled staging reproducer.
6. Kiểm tra rate limit/availability impact, bot patterns và false positive ở client hợp lệ.
7. Ghi tình trạng **suspected abuse / unclassified / integration regression** theo bằng chứng, không khẳng định động cơ không được chứng minh.

### 15.3. Runbook C — MockMvc thấy CSP nhưng browser public không nhận

**Quan sát:** App test có CSP Enforce, browser HTML response không có hoặc có header khác.

1. Xác định **HTML origin** thật: Spring MVC, WebFlux, frontend CDN hay gateway.
2. Kiểm tra headers ở public HTTPS document, không chỉ JSON API.
3. Kiểm tra CDN/ingress có strip, append hoặc cache policy cũ không.
4. Tìm **hai Enforce policies** vô tình áp đồng thời hoặc nhầm Enforce thành Report-Only.
5. So frontend bundle, nonce/hash và policy revision cùng một release.
6. Chạy browser fixture chứng minh unapproved inline script bị chặn; test legitimate checkout/SSO.
7. Fix ở layer sở hữu HTML header; rollout canary có synthetic edge probes.
8. Không mở unsafe-inline/script-src wildcard chỉ để giảm báo cáo.

### 15.4. Runbook D — HSTS hoặc cookies sai sau TLS termination

1. Quan sát public HTTPS response và redirect từ HTTP, không kết luận từ scheme nội bộ.
2. Kiểm tra trusted forwarded headers; X-Forwarded-Proto/Host từ Internet phải được sanitize.
3. Kiểm tra Set-Cookie Secure/HttpOnly/SameSite/Domain/Path sau proxy.
4. Đánh giá scope includeSubDomains/preload **trước** khi tăng HSTS max-age.
5. Dùng browser target để kiểm chứng HSTS/cookie behavior, không chỉ curl.
6. Nếu login loop do cookie scope, sửa đúng cookie/proxy; không tắt CSRF/CORS để đi vòng.
7. Ghi rủi ro rollback: HSTS browser cache còn hiệu lực trong thời gian đã công bố.

### 15.5. Runbook E — Encoded path bất ngờ vượt authorization matcher

**Đây là nguy cơ có thể nghiêm trọng.**

1. Stop rollout hoặc cô lập deployment khi negative test phát hiện path variant chạm được route đáng ra bị chặn.
2. Xác minh tầng nào decode/rewrite và **canonical path** mỗi tầng hiểu.
3. So Servlet StrictHttpFirewall, securityMatcher, MVC mapping và gateway.
4. Với WebFlux, xem Netty parser, WebFilters và SecurityWebFilterChain, không áp Servlet assumptions.
5. Không chỉ chặn một payload string rồi bỏ qua các variants hoặc route khác.
6. Khôi phục known-good firewall/gateway/security chain policy; chạy negative authorization và CSRF side-effect tests.
7. Xem dữ liệu đã có side effect trái phép hay chưa, phối hợp security incident response nếu cần.
8. Ghi case thành regression suite có định nghĩa scope/risk và bằng chứng rõ.

### 15.6. Runbook F — CSP collector hoặc HTTP logs lưu thông tin phiên

1. Hạn chế nguồn ghi raw payload và quyền đọc APM/SIEM, không chia sẻ token vào ticket/chat.
2. Xác định đã lưu **CSRF token riêng**, JSESSIONID, refresh JWT, Authorization header, reset token hay PII.
3. Đánh giá phạm vi: CDN/WAF, app logs, traces, queues/DLQ, backups, vendor exports.
4. Nếu credential phiên hoặc JWT bị lộ, làm theo incident policy về invalidation/rotation, **không đồng nhất mọi token CSRF lộ với chiếm quyền tài khoản**.
5. Sửa bằng **allowlist schema và scrub trước persistence**; giữ route group/control/reason/release.
6. Chạy synthetic canary ở staging để xác minh các sinks không còn chứa chuỗi secret giả.
7. Thực hiện retention/deletion theo owner và nghĩa vụ áp dụng; không tuyên bố đã xóa mọi bản sao khi chưa kiểm kê.
8. Bổ sung LOG-01 vào canary gate và review trường hợp verbose logging tái phát.

### 15.7. Runbook G — Một pod/region có CSP, CORS hoặc CSRF khác

1. Dùng multi-region probes và config fingerprints **không chứa secrets**.
2. So application artifact/BOM/CSRF handler, gateway/CORS/CSP rules và session repository.
3. Xác minh request route và security chain chọn thực tế, đặc biệt cookie/Bearer boundaries.
4. Cô lập nhóm instance có chính sách **yếu hơn** hoặc tạo user outage, tùy blast radius.
5. Redeploy config bất biến từ pipeline; không sửa production thủ công rồi không ghi vào source of truth.
6. Rerun browser E2E, edge header probes, CSRF/authz negative tests và session flow.
7. Đánh dấu evidence cũ không còn hiệu lực khi policy revision đổi.

### 15.8. Runbook H — Có ngoại lệ đã hết hạn nhưng chưa thể gỡ ngay

1. Xác minh chủ sở hữu, reason ban đầu, routes/assets còn phụ thuộc không.
2. Đo compatibility qua staging/browser E2E; không mặc định ngoại lệ còn cần.
3. Nếu cần gia hạn, ghi **residual risk, expiry mới, reviewer và test**; không gia hạn tự động vô hạn.
4. Đề xuất migration: sửa client URLs, self-host scripts, chuyển BFF, bỏ deprecated SDK.
5. Gỡ exception trên canary; quan sát positive flows và negative security tests.
6. Nếu không có owner hoặc không thể chứng minh phạm vi, ngăn promote ngoại lệ mới và escalate quyết định.

### 15.9. Cây quyết định triage

~~~mermaid
flowchart TD
    A["Security anomaly sau change"] --> B{"Invariant bảo mật bị phá?"}
    B -->|Có| C["Stop rollout, cô lập, rollback và điều tra"]
    B -->|Chưa rõ| D["Xác định source/layer và kiểm tra evidence"]
    B -->|Không| E{"Luồng user hợp lệ bị ảnh hưởng?"}
    E -->|Có| F["Reproduce / rollback tương thích"]
    E -->|Không| G["Classify abuse/noise, tiếp tục quan sát"]
    D --> H["Security negative + positive probes"]
    H --> B
    C --> I["Verify fixed invariant + no side effect"]
    F --> I
    G --> J["Update ledger, thresholds và review dates"]
    I --> J
~~~

**Nguyên tắc:** Một anomaly có thể do **hai nguyên nhân cùng lúc**, ví dụ bot scanning làm 403 tăng trong khi frontend update tạo lỗi CSRF. Không ép mọi tín hiệu vào một giả thuyết khi có nhiều lớp quan sát.

## 16. Bài tập tình huống và tiêu chí chấm bằng chứng

### 16.1. Bài A — Vẽ threat model cho một SPA có API dùng cookie

Tạo bảng **asset → actor → entry point → trust boundary → threat → control → invariant → evidence** cho login, profile update, payment và logout.

**Đạt khi:**

- Phân biệt same-origin và same-site.
- Xác định session cookie là ambient credential và cần đánh giá CSRF.
- Có positive/negative CSRF tests và session lifecycle tests.
- Có CORS preflight test với exact trusted Origin.
- Nêu residual risk nếu có XSS trên trusted origin.

### 16.2. Bài B — Review một quyết định bỏ CSRF

Giả sử nhóm đề xuất:

~~~java
csrf(csrf -> csrf.disable())
~~~

với lý do API trả JSON và dùng JWT. Xây **decision record** chứng minh token được gửi bằng Bearer header hay nằm trong cookie; kiểm tra cookie fallback và refresh-cookie authentication.

**Đạt khi:** Không chấp nhận JSON/stateless/JWT như lý do tự động miễn CSRF; có route/method scope và cookie-only negative test.

### 16.3. Bài C — Có CSP nhưng browser vẫn chạy inline script không được phép

Kiểm tra CSP Enforce vs Report-Only, nonce/hash và actual HTML origin. Dùng một fixture harmless ở staging và browser E2E để chứng minh enforcement.

**Đạt khi:** Không chỉ nhìn header tồn tại; xác định chính sách nào thực thi và ở response document nào. Không mở unsafe-inline để làm test xanh.

### 16.4. Bài D — HSTS policy thay đổi tại CDN

Đội sản phẩm muốn bật includeSubDomains và preload với max-age lớn. Lập domain inventory, rollback risk, HTTPS public probes và decision review.

**Đạt khi:** Xác định được subdomains dùng HTTP, người chịu trách nhiệm và phạm vi browser caching. Không kết luận HSTS đúng bằng curl HTTP.

### 16.5. Bài E — Legacy client dùng semicolon/encoded slash

Client gặp HTTP 400 sau gateway migration. Tái hiện qua gateway → Servlet container → StrictHttpFirewall, so normalized paths và securityMatcher. Đề xuất sửa URL contract hoặc exception có scope/expiry.

**Đạt khi:** Có negative tests chứng minh không path-authz bypass và không tắt firewall chung chỉ để giảm HTTP 400.

### 16.6. Bài F — WebFlux và Servlet trong cùng hệ thống

Một gateway Reactive đứng trước Servlet backend; một WebFlux API khác dùng WebSession. Thiết kế test riêng cho Reactive CORS/CSRF, Servlet firewall/CSRF và public edge.

**Đạt khi:** Không copy HttpSecurity/StrictHttpFirewall sang WebFlux; phân biệt WebTestClient in-memory với real server parser.

### 16.7. Bài G — Tạo sổ kiểm soát có thể kiểm toán

Chọn ba controls: **CSRF, CSP và HTTP firewall**. Viết mỗi record gồm asset, boundary, scenario, invariant, evidence ID, policy revision, owner, residual risk, revisit trigger và rollback.

**Đạt khi:** Mỗi control có ít nhất một positive và một negative test; bằng chứng không chứa secrets hoặc raw user request data.

### 16.8. Bài H — CORS và CSRF cùng lỗi sau release

Browser báo CORS error; server không thấy POST, nhưng có OPTIONS 401. Sau sửa OPTIONS, POST lại 403 vì token cũ.

**Đạt khi:** Phân loại **hai lỗi khác nhau**, sửa CORS trước rồi token refresh; không gán OPTIONS 401 thành MissingCsrfTokenException.

### 16.9. Bài I — Production CSP reports bằng 0

Collector đã ngừng hoạt động khi rollout Enforce, nhưng dashboard chỉ hiển thị “0 violations”.

**Đạt khi:** Có synthetic report canary, browser execution fixture và collector availability monitor; không tuyên bố an toàn khi không có tín hiệu.

### 16.10. Bài J — Cấu hình lệch trên nhiều vùng

Region A phục vụ SPA HTML từ CDN có CSP Enforce, region B chỉ có Report-Only và backend phiên bản CSRF handler khác. Lập rollout gate.

**Đạt khi:** So policy revisions, cookie/session flows, CSP browser tests và rollback known-good tuple; không chỉ so application.properties.

### 16.11. Bài K — Thiết kế threat-aware alerting

Tạo dashboard riêng cho confirmed CSRF deny, authz 403, firewall 400, WAF 403, CSP violations và login/checkout success.

**Đạt khi:** Dùng low-cardinality labels, mẫu số đúng, so release/canary và không suy luận attacker chỉ từ IP hoặc 403 count.

### 16.12. Bài L — Security exception có thời hạn

Một đối tác yêu cầu CSP frame-src mới và CORS origin mới trong 60 ngày. Soạn ADR, test cross-origin legitimate/untrusted và kế hoạch sunset.

**Đạt khi:** Không mở wildcard credentialed CORS, có owner/expiry và review khi đối tác thay SDK. Thiếu bằng chứng thì không promote policy.

## 17. Checklist phát hành và các nguyên tắc cốt lõi

### 17.1. Checklist control–threat–evidence

| Hạng mục | Tiêu chí PASS |
| --- | --- |
| **Scope** | Tài sản, actors, origins, routes và trust boundaries có mô tả |
| **Authentication** | Browser cookie, Bearer-only, webhook và session fallbacks đã được kiểm |
| **Threat scenario** | Mỗi exception/control có nguy cơ và rationale cụ thể |
| **Security invariant** | Có điều kiện test được và kỳ vọng side effects |
| **Control register** | Owner, revision, assumptions, residual risk và revisit trigger |
| **CSRF** | Cookie-auth unsafe mutation thiếu/sai token bị chặn; auth transitions đúng |
| **CORS** | Trusted preflight hoạt động, untrusted credentialed access không được cấp |
| **CSP** | Enforce/Report-Only rõ ràng, đúng HTML origin, nonce/hash và sources được review |
| **Security headers** | Browser clickjacking, base-uri, object-src và form-action theo threat model |
| **HSTS/TLS** | Public HTTPS và domain scope có bằng chứng, không tin forwarded headers không kiểm |
| **Cookie/session** | Secure, HttpOnly, SameSite, session fixation/rotation/expiry phù hợp |
| **HTTP firewall** | Path variants/methods không bypass SecurityFilterChain và authz |
| **Servlet** | SecurityFilterChain ordering, request handler/repository và MockMvc tests PASS |
| **Reactive** | SecurityWebFilterChain, WebSession/CsrfWebFilter và WebTestClient tests PASS |
| **Proxy/CDN** | Edge rewrites, headers, TLS, cache, Host và route policy tương thích |
| **Evidence** | Positive+negative tests, browser E2E, public probes đúng revisions |
| **Metrics** | Source-aware reasons, low-cardinality labels, legitimate flow SLO |
| **Privacy** | Không log Cookie/JWT/CSRF/URL query, CSP samples hoặc raw request body |
| **Exceptions** | Được review, có scope, owner, expiry, fallback/rollback |
| **Drift** | App/BOM/edge/region revisions đồng nhất và được theo dõi |
| **Rollout** | Canary gates định nghĩa PASS/FAIL, có owner dừng triển khai |
| **Rollback** | Known-good tuple và security invariants được kiểm lại |
| **Post-deploy** | Synthetic monitoring, stale evidence detection và review cadence |

### 17.2. Mười bốn nguyên tắc cần ghi nhớ

1. **Cấu hình có thể giải thích bắt đầu từ threat model**, không bắt đầu bằng một danh sách annotations hoặc headers.
2. **Một control cần security invariant có thể kiểm thử**, không chỉ một flag được bật.
3. **Ranh giới xác thực thực tế quyết định CSRF threat**, không phải nhãn JSON, REST, JWT hay stateless.
4. **Cookie, CORS và CSRF giải quyết các vấn đề khác nhau**; không thay thế cho nhau.
5. **CSP phải có trên HTML document origin**, không chỉ ở backend JSON; Report-Only không thực thi như Enforce.
6. **HSTS và cookie behavior phải được kiểm tại public HTTPS/browser**, đặc biệt khi có TLS termination.
7. **Servlet StrictHttpFirewall và WebFlux HTTP parser khác nhau**; cùng mục tiêu, khác bằng chứng.
8. **Authorization luôn độc lập với CSRF và HTTP firewall**; token đúng không cấp quyền dữ liệu.
9. **Bảo mật là kết quả quan sát được** từ app, browser và edge, không chỉ mã cấu hình trong repository.
10. **Bằng chứng phải có thời điểm, revision, scope và owner**; khi giả định thay đổi, bằng chứng cũ có thể stale.
11. **Positive tests và negative tests đi cùng nhau** để tránh vừa bypass bảo vệ vừa outage người dùng.
12. **Log và reports không được trở thành kho credential/PII**; dữ liệu được giảm trước khi lưu hoặc truyền sang APM.
13. **Ngoại lệ phải có phạm vi, owner, expiry, residual risk và rollback**; không tự gia hạn qua nhiều release.
14. **Rollout/rollback dựa trên security invariants cùng business SLO**, không chỉ số lỗi 400/403 hoặc CSP reports.

**Kết luận:** Duy trì cấu hình Spring Security HTTP có thể giải thích là duy trì một **chuỗi suy luận và kiểm chứng**: tài sản → trust boundary → threat scenario → policy/control → invariant → evidence → quyết định thay đổi → giám sát drift. Khi mỗi liên kết đều có owner và bằng chứng đúng tầng, đội phát triển có thể bảo vệ Servlet, Reactive và browser mà vẫn chủ động xử lý ngoại lệ, nâng cấp framework, thay CDN hoặc tích hợp bên thứ ba **không biến việc sửa lỗi thành mở lỗ hổng mới**.

## Tài liệu tham khảo chính thức và bổ trợ

- [Spring Security — Servlet Exploits: CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — Reactive Exploits: CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — Servlet HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security — Reactive HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Security — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/firewall.html)
- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security — Servlet Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/index.html)
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [OWASP — Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html)
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [OWASP — Cross Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)






