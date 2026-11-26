# Kiểm thử hồi quy sau thay đổi frontend hoặc thư viện bên thứ ba

## Mục tiêu và tình huống vận hành

Trong chương **Vận hành và giám sát** thuộc dịch vụ **SPRING_SECURITY_HTTP_PROTECTION**, nhiệm vụ không chỉ là thiết lập Spring Security một lần, mà còn **chứng minh các lớp phòng vệ HTTP và trình duyệt vẫn có hiệu lực sau mỗi lần thay frontend, bundler, browser SDK, CDN hoặc thư viện bên thứ ba**.

Ví dụ, một SPA nâng cấp HTTP client library khiến header CSRF không còn được tự động gửi; thư viện đăng nhập đổi cách sử dụng cookie hoặc redirect; payment SDK yêu cầu thêm iframe/script origin; một thư viện UI chuyển sang CSS-in-JS hoặc dynamic import khiến CSP Enforce chặn tài nguyên; service worker mới tiếp tục phục vụ app shell cũ trong khi backend đã rotate token. Các tình huống này có thể biểu hiện bằng **HTTP 403, lỗi CORS trên browser, trang trắng, checkout thất bại hoặc vòng lặp đăng nhập**, mặc dù Spring Security source code không đổi.

Bài học này trình bày cách thiết kế **regression contract** trước thay đổi, liên kết **thay đổi → mô hình nguy cơ → security invariant → positive/negative tests → bằng chứng ở browser/edge → rollout/rollback**, áp dụng cho:

- **Servlet:** HttpSecurity, SecurityFilterChain, CsrfFilter, CORS, CSP/security headers, StrictHttpFirewall, HttpSession.
- **Reactive/WebFlux:** ServerHttpSecurity, SecurityWebFilterChain, CsrfWebFilter, CorsWebFilter/Reactive CORS, WebSession.
- **Browser/frontend:** fetch/Axios, SPA/SSR, bundler/runtime chunk, service worker, payment/login SDK, CSP, SameSite/cookie policy, E2E.
- **Hạ tầng:** CDN, WAF, gateway, HTTPS/HSTS, static HTML host, asset caching, source maps và observability.

Các ví dụ hướng tới **Spring Boot 3.x / Spring Security 6.x / Java 17+** và Playwright Test; hãy kiểm tra chính xác versions đang pin trước khi dùng. **Không đánh đồng “không lỗi build” với “bảo vệ còn hiệu lực”**, hoặc “không nhận CSP violation report” với “CSP không bị phá”.

Sau bài học, người học có thể:

1. Lập **change impact inventory** cho cả direct, transitive dependencies, remote scripts, iframes, service workers và CDN-hosted assets.
2. Viết invariant có thể test về **CSRF, CORS, CSP, HSTS, security headers, session/cookies, authorization và HTTP firewall**.
3. Phân biệt test library contract, MockMvc/WebTestClient, real server, browser E2E và public-edge probes; biết giới hạn từng loại bằng chứng.
4. Kiểm thử SPA CSRF token qua **bootstrap → login → refresh → mutation → logout**, đặc biệt raw/XOR, deferred token và multi-tab.
5. Xác minh browser credentialed CORS/preflight, cookie scope/SameSite/Secure và redirects sau khi HTTP client hoặc auth SDK đổi.
6. Đánh giá **CSP nonce/hash/strict-dynamic, SRI, dynamic scripts, iframe/form-action/connect-src** khi tích hợp nhà cung cấp mới.
7. Kiểm thử trên **Servlet lẫn Reactive** mà không nhầm StrictHttpFirewall của Servlet với WebFlux parser.
8. Tạo CI/CD gates, canary monitoring, rollback plan và incident runbooks không làm yếu phòng vệ.
9. Ghi lại bằng chứng mà **không log CSRF token, session cookie, JWT, raw CSP report hay dữ liệu cá nhân**.

## 1. Thế nào là một security regression do thay đổi frontend?

### 1.1. Không đổi backend vẫn có thể làm mất bảo vệ

Một số ví dụ cụ thể:

| Thay đổi | Regression nhìn thấy | Rủi ro bảo mật có thể bị bỏ sót |
| --- | --- | --- |
| HTTP client bỏ X-XSRF-TOKEN interceptor | POST cookie-auth 403 | Dev chọn tắt CSRF thay vì sửa client |
| Auth SDK đổi login/logout callback | First POST sau login 403 | Token chưa refresh hoặc cookie/session sai |
| SPA chuyển API sang subdomain khác | Browser CORS error | CORS phản chiếu mọi Origin để sửa nhanh |
| Bundler chuyển sang dynamic import | JS chunk bị CSP chặn | Thêm script-src * / unsafe-inline |
| Payment SDK chèn iframe/script | Checkout thất bại | Mở quá rộng frame-src, script-src, connect-src |
| CDN đổi host static assets | CSS/JS không tải | CSP trusted origins lỗi hoặc integrity drift |
| UI library dùng eval/inline style | CSP violation | Vô hiệu unsafe-eval/unsafe-inline protections |
| Service worker giữ app shell cũ | Frontend cũ gọi API contract mới | Token/interceptor/version mismatch |
| CDN/proxy rewrite path | 400/404/403 theo route | SecurityMatcher/firewall/authorization mismatch |
| Thư viện upload đổi content type | Preflight OPTIONS mới | CORS cho phép wildcard headers/origin vô hạn |
| Auth SDK đổi SameSite hoặc redirect host | Login loop, session mất | Cookie scope hoặc forwarded-host trust sai |
| Thêm browser telemetry SDK | Security logs hoặc APM chứa URLs/tokens | Rò PII/credential qua third-party |
| Thư viện routing đổi URL encoding | Một số links 400 | Nới StrictHttpFirewall mù quáng |
| Framework upgrade thay CSRF request handler | SPA gửi raw token nhưng handler cần XOR | Bỏ CSRF để sửa 403 |

Không phải trường hợp nào cũng là **lỗ hổng đã khai thác**. Regression có thể là **fail-closed gây gián đoạn** (ví dụ CSP chặn payment hợp lệ), hoặc **fail-open làm yếu phòng vệ** (ví dụ bỏ CSRF, nới Origin, allowlist CSP wildcard). Cả hai phải có test và mức ưu tiên xử lý.

### 1.2. Bốn kết quả phải kiểm đồng thời

Một lần thay đổi chỉ đạt khi:

1. **Functionality:** Các luồng hợp lệ — đăng nhập, thanh toán, hồ sơ, logout, upload, WebSocket nếu có — vẫn hoạt động.
2. **Security enforcement:** Các request/script/origin trái phép vẫn bị từ chối, không có side effect.
3. **Policy correctness:** Header/cookie/CORS/CSP/CSRF/firewall thực tế trên đúng response/route/stack vẫn khớp thiết kế.
4. **Observability/privacy:** Các tín hiệu vẫn được thu an toàn và không chứa token/PII; collector, dashboard, synthetic probes hoạt động.

Chỉ chạy unit tests hoặc chỉ quan sát tỷ lệ HTTP 200 là không đủ. Một cấu hình **permitAll** hoặc **csrf.disable()** có thể làm happy-path E2E xanh nhưng loại bỏ bất biến bảo mật.

### 1.3. Threat model tối thiểu cho thay đổi

Với mỗi thay đổi, trả lời:

~~~text
Change ID: FE-2026-042
Old -> New: HTTP client version / auth SDK / payment script
Affected origins: app.example.com, api.example.com
Affected flows: anonymous CSRF bootstrap, login, profile POST, logout
Credentials: JSESSIONID cookie tự gửi + CSRF header do JS chủ động đặt
Trust boundaries: Browser -> CDN -> API gateway -> Spring Security
Threats: forged mutation, cross-origin data disclosure, XSS,
         script supply-chain compromise, session mismatch
Required invariants:
  - unsafe POST thiếu CSRF -> denied/no side effect
  - trusted preflight -> pass; untrusted origin -> no credentialed access
  - CSP untrusted script -> blocked
  - session cookie -> Secure + HttpOnly, scope đúng
Evidence: unit + integration + browser + public-edge
Owner: frontend + application security + platform
Rollback: frontend asset/release + compatible backend/edge policy
~~~

Threat model không yêu cầu tạo file mới trong bài học này. Đây là **mẫu nội dung thực hành**. Điều quan trọng là biết browser có **ambient credentials** hay không; một JSON API hoặc “JWT” **không mặc định miễn CSRF** nếu JWT/session nằm trong cookie.

## 2. Kiểm kê thay đổi và chuỗi phụ thuộc trước khi chạy test

### 2.1. Những loại thay đổi cần đưa vào phạm vi

- **JavaScript trực tiếp:** framework, React/Vue/Angular libraries, HTTP clients, authentication SDK, payment SDK, editor, charting, analytics.
- **Transitive dependencies:** package lockfile diff, bundler plugins, polyfills, CSS processors, runtime chunks.
- **Remote third-party code:** script tải qua CDN, tag manager, analytics pixel, dynamic script loader, widgets.
- **Iframe và form interactions:** payment, identity provider, captcha, embedded support, cross-origin redirects.
- **Browser storage:** cookies, sessionStorage/localStorage, service workers, Cache Storage, indexedDB.
- **Runtime delivery:** immutable asset URLs, cache-control, deployment revision, CDN routing và HTML headers.
- **Backend liên quan:** Spring Security request handler/repository, security chain matcher, response headers, session store.
- **Gateway/WAF:** Origin/header allowlist, TLS termination, encoded path rewrite và HTTP method handling.

Một thay đổi “chỉ frontend” vẫn có thể yêu cầu thay **CORS allowlist tại API**, **CSP trên HTML origin**, hoặc **cookie policy tại gateway**. Không chốt phạm vi chỉ theo repository nhận PR.

### 2.2. Artifact và bằng chứng provenance

| Thành phần | Cần ghi trong change record | Không dùng thay evidence |
| --- | --- | --- |
| Dependency lockfile | Package + resolved version + integrity metadata | Khẳng định code tự động an toàn |
| Software BOM (SBOM) | Direct/transitive packages, license/provenance | Bỏ qua runtime remote scripts |
| Frontend build | Commit/artifact digest/bundle revision | Local dev build thay production artifact |
| Remote script/iframe | Vendor, exact origins, integration purpose | Allowlist host vô hạn theo vendor |
| CSP policy | Enforce/Report-Only version ở HTML origin | Header CSP nằm ở API JSON |
| Gateway/CORS | Allowed origins/headers/methods revision | Cấu hình source chưa deploy |
| Spring Security | Resolved BOM, chains/repository/handler | Giả định framework mặc định giữ nguyên |
| Session/cookie | Attributes, TTL, domain/path, auth transitions | Set-Cookie có mặt đồng nghĩa browser đã gửi |
| Test evidence | Env, browser, commit/release, positive+negative results | Một HTTP 200 hoặc screenshot thiếu ngữ cảnh |

Không lưu password, CSRF token, JWT, session IDs hoặc user PII trong evidence bundles, HAR, screenshots, console logs, SBOM metadata hoặc CI artifacts.

### 2.3. Supply-chain review không thay browser regression tests

Quét SCA/CVE, dependency freshness, lockfile verification, provenance, signatures hoặc SBOM giúp giảm rủi ro supply chain, **nhưng không chứng minh** CSP, CORS, CSRF hay cookies còn hoạt động. Ngược lại, browser E2E pass cũng **không chứng minh** dependency không bị trojan hoặc không có vulnerability đã biết.

Hai hướng đánh giá phải song song:

1. **Trustworthiness:** Có thể chấp nhận dependency/vendor/bundle này theo policy không?
2. **Behavioral compatibility:** Sau khi chạy, browser và Spring Security còn thực thi đúng security invariants không?

Remote scripts có thể cập nhật không qua lockfile của app. Ghi rõ **version pin/asset digest/URL policy** và thay đổi không được kiểm soát của tag managers.

## 3. Viết regression invariants từ control, không chỉ từ tính năng

### 3.1. Ma trận threat–control–test

| Security control | Invariant bắt buộc | Positive test | Negative test |
| --- | --- | --- | --- |
| **CSRF** | Cookie-auth unsafe mutation đòi token hợp lệ | Login → token mới → POST | POST thiếu/sai/stale token không side effect |
| **CORS** | Chỉ trusted origins được đọc credentialed response | Trusted OPTIONS + actual Fetch | Untrusted Origin không được cấp allow-credentials |
| **CSP script** | Chỉ nguồn/script đã review được chạy | Bundle và SDK hợp lệ hoạt động | Unapproved inline/external script bị chặn |
| **CSP frame** | Frame/embedding theo scope approved | Payment iframe chạy ở checkout | Untrusted iframe/parent bị chặn |
| **CSP connect** | Fetch/XHR/WebSocket tới nguồn đã duyệt | API/WebSocket hoạt động | Untrusted connect-src bị ngăn |
| **Security headers** | Document không thể bị clickjacking | Normal navigation hoạt động | Iframe embedding bị chặn theo frame-ancestors |
| **HSTS** | Browser nhận HSTS policy qua HTTPS hợp lệ | Public HTTPS header đúng | HTTP downgrade test theo contract, không false TLS |
| **Session cookies** | Session cookie Secure/HttpOnly/SameSite đúng | Login rồi API call có phiên | Cookie-only Bearer-chain không xác thực |
| **Authorization** | Role/scope/object ownership vẫn enforce | Đúng quyền + token hợp lệ | Sai quyền dù token CSRF đúng bị chặn |
| **HTTP firewall** | Encoded paths không bypass matcher | Normal routes hợp lệ | Path/method variants không bypass chain |
| **Logging privacy** | Token/PII không rơi vào telemetry | Reduced audit events | Canary secret không xuất hiện trong logs/traces |
| **Availability** | Legitimate flows không bị security policy chặn nhầm | Browser E2E checkout/login | Khác browser/network vẫn có contract |
| **Cache** | Session-specific token/HTML nonce không shared-cache sai | Bootstrap token đúng phiên | Hai test sessions không nhận chung token |

### 3.2. Security invariant phải có trạng thái nghiệp vụ

Ví dụ:

~~~text
CSRF-ORDER-001
Given: session-cookie authenticated client
When: POST /api/browser/orders không có CSRF token
Then:
  HTTP status theo contract là denied (thường 403)
  No order created; no payment authorization
  No retry side effect
  CSRF denial được ghi nhận nếu instrumentation có bằng chứng
~~~

Nếu chỉ assert HTTP 403, một side effect có thể đã xảy ra **trước khi lỗi được trả** trong bug orchestration khác. Test transaction/storage hoặc mock side-effect sink để chứng minh không có mutation khi bị deny.

### 3.3. Bằng chứng nhiều tầng cho cùng một invariant

~~~mermaid
flowchart LR
    A["Dependency / frontend PR"] --> B["Static contract + unit tests"]
    B --> C["MockMvc / WebTestClient security tests"]
    C --> D["Real server + gateway"]
    D --> E["Browser E2E theo engines"]
    E --> F["Canary + public HTTPS edge"]
    F --> G{"Security + business gates PASS?"}
    G -->|Có| H["Promote"]
    G -->|Không| I["Stop / rollback / investigate"]
~~~

MockMvc giúp kiểm tra **Servlet filters** nhưng không tái hiện mọi cookie/CORS/CSP browser behavior. WebTestClient giúp kiểm tra **Reactive filters** nhưng không thể được gọi là test **Servlet StrictHttpFirewall**. Browser E2E mới thực thi CSP/SameSite, song không thay signature validation và kiểm thử business authorization ở server.

## 4. Chiến lược test pyramid và môi trường tái lập

### 4.1. Năm tầng test có trách nhiệm riêng

| Tầng | Chi phí | Đầu vào/đích | Chỉ nên kết luận |
| --- | --- | --- | --- |
| Unit/contract | Thấp | Token helper, SDK adapter, route mapping | Client logic đúng với giả định |
| Spring integration | Trung bình | MockMvc hoặc WebTestClient | Chain, CSRF/CORS/authz xử lý đúng |
| Embedded real server | Trung bình | HTTP parser, cookie jar, app + session | Server semantics và middleware |
| Browser E2E | Cao hơn | Chromium/Firefox/WebKit, user flows | Browser enforcement và UX |
| Public-edge synthetic/canary | Cao hơn | HTTPS/CDN/WAF/gateway/cache | Artifact/policy ở production-like edge |

Không chạy mọi biến thể trên mọi PR nếu không cần; hãy lập **fast PR suite + focused change-impact suite + nightly full browser matrix + pre-promotion canary**. Nhưng những thay đổi làm yếu security boundaries phải có **negative tests trước merge**.

### 4.2. Phiên bản và môi trường test phải ổn định

Trong CI nên pin và ghi:

- Node/package manager/bundler versions; **lockfile immutable install**.
- Java + Spring Boot + Spring Security resolved dependency versions.
- Browser test engines/Playwright version (được pin hoặc chạy theo lịch).
- Backend app/image digest và frontend asset digest.
- CSP policy revision tại **HTML serving origin** và CORS/cookie policy tại API.
- Edge routing/WAF config revision, session store mode và TLS setup.
- Third-party vendor sandbox version/endpoint hoặc synthetic fixture mapping.

Nếu test E2E cố định mocks trả lời bằng contract cũ, nhưng production SDK thay behavior, suite có thể PASS giả. Cần **ít nhất một vendor sandbox/contract smoke** và browser test qua **real public-edge-like topology** trước promote.

### 4.3. Tách kiểm thử deterministic và vendor-live

- **Contract mocks/fixtures:** Deterministic, chạy nhanh trên PR, test các lỗi/timeout, không cần vendor thật.
- **Vendor sandbox:** Kiểm tra handshake, iframe, redirect, CSP source, CORS/cookie và error paths theo môi trường sandbox.
- **Real-browser smoke:** Chạy trên staging CDN/HTTPS với bundle chuẩn deploy, không chỉ localhost.
- **Production synthetic (có giới hạn):** Không tạo thanh toán thật hoặc thay dữ liệu user; dùng synthetic test account và endpoints an toàn.
- **Negative security probes:** Cố tình gửi request thiếu token, untrusted origins/frames/scripts, xác minh không side effect.

Không yêu cầu chạy fuzz HTTP hoặc tải vendor script từ môi trường sản xuất mà không có scope được duyệt. Mọi synthetic request có ID và phạm vi test rõ, không chứa credential thật trong log hoặc report.

## 5. CSRF regression sau nâng cấp SPA, HTTP client hoặc auth SDK

### 5.1. Tại sao một bản nâng frontend làm CSRF fail?

Khi browser sử dụng **session cookie**, cookie có thể được tự động gửi trên request thuộc scope của nó. CSRF token tạo thêm điều kiện cho unsafe request; frontend thường lấy token từ **CSRF bootstrap JSON hoặc XSRF cookie**, rồi chủ động gắn vào **header**.

Các lỗi điển hình:

- Chuyển Axios/fetch wrapper làm mất tự động thêm **X-CSRF-TOKEN/X-XSRF-TOKEN**.
- Đổi domain API khiến frontend không còn đọc được XSRF cookie **host-only** hoặc request không gửi session cookie.
- SDK auth giữ token cũ sau login/logout **dù Spring Security đã clear expected token**.
- SPA gọi unsafe POST trước khi GET CSRF bootstrap materialize token.
- Spring Security 6.x dùng **XorCsrfTokenRequestAttributeHandler** cho token masked/BREACH protection, trong khi SPA lấy **raw** token từ cookie; thiếu handler tương thích.
- Frontend/service worker cache JSON token / HTML có nonce cho phiên khác, hoặc trả token stale.
- Multi-tab logout/refresh race khiến tab giữ token cũ.
- Client tự retry non-idempotent POST sau 403 hoặc timeout, gây nguy cơ side effects trùng.

**Không tắt CSRF để sửa UI 403.** Cần hiểu repository, request handler, authentication transitions và cookie/session boundary.

### 5.2. Raw, XOR-masked và deferred token

Trong Spring Security Servlet 6.x:

- **CsrfTokenRepository** quản lý expected token: ví dụ HttpSessionCsrfTokenRepository hoặc CookieCsrfTokenRepository.
- **CsrfTokenRequestHandler** cung cấp token trong request attributes và resolve actual token từ header/form.
- **XorCsrfTokenRequestAttributeHandler** mặc định hỗ trợ masked representation để giảm một số nguy cơ như BREACH trong response nén.
- **CsrfTokenRequestAttributeHandler** xử lý plain/raw header khi hợp đồng SPA yêu cầu.
- **Deferred token loading**: GET route không tự đảm bảo cookie/token được tạo nếu handler/controller không thực sự truy cập token.
- **CsrfAuthenticationStrategy và CsrfLogoutHandler** có thể xóa token cũ khi login/logout; frontend cần lấy token mới.

Tham khảo cách xây **SpaCsrfTokenRequestHandler** hỗ trợ plain header/XOR form trong tài liệu Spring Security 6.5. Không tự suy diễn **csrf.spa()** có ở 6.x; DSL trợ giúp nằm ở dòng hỗ trợ tương ứng như 7.x Servlet, phải xác minh đúng BOM.

~~~text
CSR-SPA-01:
  frontend sends raw XSRF cookie value in X-XSRF-TOKEN
  configured handler resolves that header as raw
  SSR form _csrf (if used) still accepts masked token
  protected POST without/wrong token -> denied/no mutation
  cookie/session/token refreshed after auth transition
~~~

Không log raw/XOR token để debug mismatch; test hành vi và config version.

### 5.3. Vòng đời cần test khi auth SDK thay

~~~mermaid
sequenceDiagram
    autonumber
    participant F as SPA Frontend
    participant S as Spring Security
    participant R as CSRF repo / session
    F->>S: GET /api/browser/csrf anonymous
    S->>R: Materialize token A
    S-->>F: Token A, no-store
    F->>S: POST /login + session cookie + token A
    S->>R: Authentication may clear token A
    S-->>F: Login success / session transition
    F->>S: GET /api/browser/csrf authenticated
    S->>R: Materialize token B
    S-->>F: Token B, no-store
    F->>S: POST /api/browser/orders + token B
    S-->>F: Result based on CSRF + authorization
    F->>S: POST /logout + token B
    S->>R: Logout invalidates old token
    F->>S: GET CSRF bootstrap if anonymous flow needs
    S-->>F: Token C
~~~

Token A/B/C là **ký hiệu**, không phải credential thật. Trình tự cụ thể phụ thuộc auth mechanism/repository; test full flow trên **cùng browser cookie jar** thay vì tạo token rời rạc.

### 5.4. Fetch client chủ động gửi header

~~~javascript
// Ví dụ API trả JSON token theo same-origin BFF.
// Endpoint, auth state và retry cần tùy biến theo ứng dụng.
// Không log giá trị token.
let csrfCache = null;

async function loadCsrfToken() {
  const response = await fetch("/api/browser/csrf", {
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("CSRF bootstrap failed");
  const result = await response.json();
  if (!result.headerName || !result.token) {
    throw new Error("Unexpected CSRF contract");
  }
  csrfCache = { headerName: result.headerName, token: result.token };
}

async function createOrder(order) {
  if (!csrfCache) await loadCsrfToken();
  const response = await fetch("/api/browser/orders", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrfCache.headerName]: csrfCache.token
    },
    body: JSON.stringify(order)
  });

  // Không retry non-idempotent POST tự động vì 403.
  if (response.status === 403) {
    throw new Error("Request forbidden; inspect auth/CSRF flow");
  }
  if (!response.ok) throw new Error("Order failed");
  return response.json();
}

// Sau auth transition cần clear token và bootstrap lại.
function onAuthenticationTransition() {
  csrfCache = null;
  return loadCsrfToken();
}
~~~

Code này áp cho **same-origin**. Với SPA app.example.com gọi API api.example.com cần **credentials: "include"**, CORS đúng, token bootstrap phù hợp; không mặc định cookie host-only của API có thể được JS ở app host đọc. Session cookie phải giữ HttpOnly. Với SDK auth mới, callback sau login phải được gọi khi auth/session response đã hoàn tất; một GET token cũ tới muộn không được ghi đè token mới.

### 5.5. Race, cache và idempotency

- POST đầu tiên phát trước bootstrap → 403.
- Bootstrap A bắt đầu khi anonymous, login tạo B, A đến muộn → stale token.
- Tab A logout, Tab B giữ token cũ → 403 hợp lệ.
- Frontend tự retry POST sau network timeout, request đầu đã có side effect → mutation trùng.
- Service worker offline cache có thể phục vụ JS cũ hoặc token bootstrap sai revision.

Thiết kế **generation/epoch** theo auth state; clear cache sau login/logout, loại response bootstrap từ epoch cũ. Không tự retry unsafe request khi không có **idempotency key/contract** và business side-effect guarantees.

## 6. Servlet: cấu hình đối chứng và MockMvc regression tests

### 6.1. Browser SecurityFilterChain phải có CSRF và quyền độc lập

Ví dụ Servlet Spring Security 6.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BrowserSessionSecurity {
    @Bean
    SecurityFilterChain browserChain(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/browser/**", "/login", "/logout")
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/api/browser/csrf", "/login").permitAll()
                .requestMatchers("/api/browser/**").authenticated()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

**Đây là chain một phần**, chưa có JWT Bearer chain, fallback deny, login/logout matcher chi tiết, custom SPA handler hoặc token repository. Những routes không được chain này match cần được bảo vệ bằng **chain khác**. Nhiều SecurityFilterChain đòi test **chain selection** trước/sau frontend router và gateway rewrites.

### 6.2. CSRF bootstrap materialize token trên Servlet

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletCsrfBootstrap {
    record TokenContract(String headerName, String token) {}

    @GetMapping("/api/browser/csrf")
    ResponseEntity<TokenContract> read(HttpServletRequest req) {
        CsrfToken token = (CsrfToken) req.getAttribute(
            CsrfToken.class.getName());
        if (token == null) {
            throw new IllegalStateException("CSRF not configured");
        }
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new TokenContract(
                token.getHeaderName(), token.getToken()));
    }
}
~~~

Đây là **JSON bootstrap**; token trong attribute có thể ở dạng masked tùy request handler. SPA dùng cookie-to-header raw cần test riêng và có thể cần custom SPA request handler. **Không log token** trong CI/APM hoặc cache response chung giữa sessions.

### 6.3. MockMvc negative/positive CSRF tests

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
class BrowserApiCsrfRegressionTests {
    @Autowired MockMvc mvc;

    @Test
    void missingTokenIsDenied() throws Exception {
        mvc.perform(post("/api/browser/orders")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenIsDenied() throws Exception {
        mvc.perform(post("/api/browser/orders")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void matchingTokenAndPermissionAllowOrder()
            throws Exception {
        mvc.perform(post("/api/browser/orders")
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\"}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Test giả định Alice được phép tạo đơn, handler trả 2xx. **Bổ sung assertion database/side-effect**: case bị deny không tạo đơn hàng. user() và csrf() là test helpers, không kiểm tra cookie jar/session rotation hay auth SDK ngoài browser.

### 6.4. Cookie-only không được xác thực trong Bearer-only chain

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import jakarta.servlet.http.Cookie;

// Test trong ứng dụng có M2M Bearer-only chain.
mvc.perform(post("/api/m2m/jobs")
        .cookie(new Cookie("JSESSIONID", "synthetic-test-id")))
    .andExpect(status().isUnauthorized());

mvc.perform(post("/api/m2m/jobs").with(jwt()))
    .andExpect(status().is2xxSuccessful());
~~~

Helper jwt() không kiểm chữ ký JWT thật; integration cần xác minh issuer/audience/expiry và decoder thật. STATELESS không tự chứng minh cookie fallback bị cấm: phải test route **không nhận cookie-only credentials**.

### 6.5. Preflight regression trên Servlet

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Giả định CorsConfigurationSource cho trusted Origin đã được setup.
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

Test thêm untrusted Origin, không cấp credentialed cross-origin access. OPTIONS **không có session cookie như POST**; CORS phải xử lý preflight trước authentication. Nếu browser không phát actual POST do preflight fail, đó không phải CSRF POST failure.

## 7. Reactive/WebFlux: WebTestClient chứng minh các invariant tương ứng

### 7.1. SecurityWebFilterChain thuộc stack khác Servlet

Reactive sử dụng **ServerHttpSecurity, SecurityWebFilterChain, CsrfWebFilter, WebSession, ServerWebExchange**. Không sao chép HttpServletRequest, Servlet RequestMatcher hoặc StrictHttpFirewall vào WebFlux.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
SecurityWebFilterChain reactiveBrowserChain(
        ServerHttpSecurity http) {
    return http
        .securityMatcher(ServerWebExchangeMatchers.pathMatchers(
            "/api/browser/**", "/login", "/logout"))
        .csrf(Customizer.withDefaults())
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/browser/csrf", "/login").permitAll()
            .pathMatchers("/api/browser/**").authenticated()
            .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Ví dụ chỉ là **browser chain một phần**: cần Reactive CORS config, auth provider, WebSession repository, M2M Bearer-only chain và fallback route policy phù hợp. Đừng cho rằng chỉ vì HttpSecurity có CSRF thì WebFlux tương đương về cookie/token behavior.

### 7.2. WebTestClient negative/positive CSRF

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import java.util.Map;

// Trong WebFlux integration test context có WebTestClient.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/browser/orders")
    .bodyValue(Map.of("sku", "P100"))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice"))
    .mutateWith(csrf())
    .post().uri("/api/browser/orders")
    .bodyValue(Map.of("sku", "P100"))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Cũng assert **không có side effects** khi request bị deny. Helper mockUser/csrf không kiểm tra browser SameSite, real WebSession cookie, auth redirects hoặc login/logout. Thêm integration tests duy trì WebSession qua full flow.

### 7.3. Reactive CSRF bootstrap không block

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfBootstrap {

    @GetMapping("/api/browser/csrf")
    Mono<ResponseEntity<Map<String, String>>> read(
            ServerWebExchange exchange) {
        Mono<CsrfToken> token = exchange.getAttribute(
            CsrfToken.class.getName());
        if (token == null) {
            return Mono.error(new IllegalStateException(
                "Reactive CSRF not configured"));
        }
        return token.map(t -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", t.getHeaderName(),
                "token", t.getToken())));
    }
}
~~~

Test JSON response no-store và token contract. **Không gọi block()** trong Reactive controller. CookieServerCsrfTokenRepository hoặc WebSessionServerCsrfTokenRepository, handler và client contract phải được kiểm tra trên phiên bản thực.

### 7.4. Reactive CORS và matcher evidence

CORS trên WebFlux cần **Reactive CorsConfigurationSource/CorsWebFilter** phù hợp, không chỉ bean Servlet. Test:

1. OPTIONS trusted Origin + requested method/headers được chấp nhận.
2. OPTIONS untrusted Origin không được credentialed access.
3. Actual cookie-auth POST thiếu/sai token bị deny.
4. POST token đúng và quyền đúng hoạt động.
5. Route M2M chỉ Cookie không xác thực được bằng Bearer.
6. Route sau gateway rewrite khớp đúng SecurityWebFilterChain.

Các lỗi **HTTP parser của Reactor Netty** không tự động tạo Servlet RequestRejectedException; khi SDK router/URL encoder đổi, thêm real HTTP server/gateway tests.

## 8. CORS, cookie và session: chỉ browser mới thể hiện đầy đủ

### 8.1. Preflight là một request độc lập

Sau khi frontend thêm Content-Type: application/json hoặc X-CSRF-TOKEN vào cross-origin request, browser có thể gửi:

~~~http
OPTIONS /api/browser/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

**Preflight không đính kèm cookie phiên như actual POST.** Nếu gateway/Spring yêu cầu đăng nhập cho OPTIONS, browser có thể **không gửi POST**; không gán mọi lỗi CORS thành CSRF POST deny.

### 8.2. Credentialed CORS dùng allowlist cụ thể

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Vary: Origin
~~~

Đây là response minh họa; headers thực tế phải theo preflight method/header contract. Không dùng **Access-Control-Allow-Origin: *** với Allow-Credentials true, không phản chiếu Origin tùy ý. Nếu CDN cache responses theo Origin, cần xem **Vary: Origin** và chính sách cache.

### 8.3. Cookie policy thay đổi theo browser và SDK

| Kiểm soát | Hồi quy thường gặp | Bằng chứng |
| --- | --- | --- |
| Secure | API scheme/forwarded proto sai | Browser Network + HTTPS edge |
| HttpOnly | SDK đòi JS đọc session cookie | Không bỏ HttpOnly, thiết kế SDK lại |
| SameSite | Redirect/iframe cross-site đổi | Cookie blocked reasons trong browser |
| Domain/Path | API đổi host, XSRF cookie host-only không đọc được | Storage + request headers |
| fetch credentials | HTTP client không gửi cookie cross-origin | Actual POST Request Headers, backend session |
| Third-party cookie blocking | Iframe SDK login/auth session lỗi | Browser engine+mode, fallback flow |
| Session timeout/rotation | Tab lâu dùng state cũ | Login, idle, logout, multi-tab test |
| Service worker/cache | App shell/token bootstrap stale | Warm vs clean context testing |
| CDN Set-Cookie rewrite | Cookie scope khác config backend | Public HTTPS response + cookie jar |

**Same-origin khác same-site.** app.example.com và api.example.com có thể cùng site nhưng khác origin; JavaScript ở app host không được mặc định đọc cookie host-only của API host. Session cookie **giữ HttpOnly**; một JS-readable XSRF cookie (nếu contract yêu cầu) không đồng nghĩa session cookie cũng được mở HttpOnly.

### 8.4. Kiểm thử riêng cho ba loại client

1. **SSR/form login:** hidden form token dùng request attribute/handler phù hợp, submit form thành công.
2. **SPA cookie-auth:** JavaScript gửi CSRF header hợp đồng, login/logout refresh, cookie scope và same-site/cross-origin đúng.
3. **Bearer-only M2M:** Authorization do client chủ động gửi, route không chấp nhận cookie-only credentials.

Nếu auth SDK mới đưa JWT vào **cookie** hoặc backend bắt đầu nhận refresh-cookie/session fallback, **threat model thay đổi**: phải đánh giá lại CSRF thay vì dựa trên chữ “JWT” hay “stateless”.

### 8.5. Browser E2E phải phân biệt cookie blocked với CORS denied

Quan sát DevTools/Playwright:

- Có **OPTIONS** trước POST không? OPTIONS status, Allow-Origin/Headers/Methods?
- Actual POST có xảy ra không? Nếu không, backend không thể có CSRF POST event.
- Cookie thực có được gửi? Nếu browser bỏ cookie, blocked reason/SameSite/Secure/third-party policy là gì?
- Frontend có thực sự gắn **tên** CSRF header hợp lệ? **Không ghi giá trị**.
- CSP connect-src có chặn GET CSRF bootstrap trước khi gửi hay không?
- Login redirect có thay origin/scheme và Set-Cookie domain/path không?
- Service worker có phục vụ bundle cũ hoặc cached response token không?

Một lệnh curl/Postman pass **không chứng minh** CORS, SameSite, CSP hoặc third-party cookies hoạt động; những công cụ đó không áp cùng browser security policies.

## 9. CSP regression khi SDK, bundler, scripts hoặc iframes thay đổi

### 9.1. Chính sách CSP phải được kiểm trên HTML origin

CSP tác động tới **browser document**. Nếu HTML SPA được phục vụ từ CDN, cấu hình Content-Security-Policy trên API JSON của Spring **không tự bảo vệ HTML đó**. Test cần xem actual response HTML ở public HTTPS edge; đồng thời có thể có Spring Security security headers trên các response mà Spring thật sự phục vụ.

Một baseline minh họa:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'
~~~

Đây không phải policy áp dụng nguyên vẹn cho mọi SPA. Một payment SDK cần **frame-src, connect-src, script-src, img-src**, OAuth/OIDC form có thể cần **form-action** khác và WebSocket cần **connect-src wss**. Mỗi mở rộng phải có **nguồn, route scope, owner và kiểm thử negative**.

### 9.2. Bảng impact cho thư viện bên thứ ba

| Thay đổi thư viện | CSP directive có thể liên quan | Regression test |
| --- | --- | --- |
| SDK tải file JS mới từ CDN | script-src, SRI, crossorigin | Script hợp lệ load, untrusted script blocked |
| Bundler đổi runtime chunks | script-src, dynamic import, caching | Lazy route load trên clean/warm context |
| Analytics SDK thêm beacon/fetch | connect-src, img-src | Chỉ approved telemetry endpoints hoạt động |
| Payment widget nhúng iframe | frame-src; frame-ancestors của trang được nhúng | Trusted payment frame chạy, untrusted frame bị ngăn |
| Authentication SDK đổi form POST/redirect | form-action, navigate flows, cookie | OAuth/login redirect hợp lệ, untrusted action không |
| UI editor inject inline style | style-src, style-src-attr | Component render đúng, policy không mở toàn cục |
| SDK dùng inline handlers hoặc eval | script-src-attr, unsafe-eval | Refactor/upgrade; không chấp nhận unsafe-inline/eval vô điều kiện |
| Web worker / WASM loader | worker-src, script-src; browser-specific eval rules | Worker hợp lệ khởi tạo, nguồn khác bị chặn |
| Font/icon CDN mới | font-src, img-src, style-src | Fonts/icons load đúng mà không wildcard |
| OAuth/social iframe login | frame-src, cookie third-party policy | Browser hỗ trợ/cấm đúng, fallback rõ |
| Service worker change | worker-src, caching, app shell | SW registration + update; rollback test |
| Third-party CSS background image | style-src, img-src | Asset đúng và policy không mở dữ liệu |
| Dynamic script injection | script-src, nonce/hash, strict-dynamic | Chỉ bootstrap tin cậy được cấp khả năng tải theo policy |

Một policy cho phép **mọi HTTPS source** hoặc 'unsafe-inline' để sửa lỗi vendor có thể giảm an toàn đáng kể. Cân nhắc self-host, pin phiên bản, iframe sandbox phù hợp, BFF, hoặc thay thư viện.

### 9.3. Nonce, hash và cache là một hợp đồng triển khai

Nếu HTML dùng inline script với CSP nonce:

~~~http
Content-Security-Policy: script-src 'nonce-<fresh-per-response-value>'; object-src 'none'; base-uri 'self'
~~~

Markup cùng response:

~~~html
<script nonce="<same-fresh-per-response-value>">
  window.startApplication();
</script>
~~~

Các placeholder trong ví dụ **không phải nonce thật**. Khi triển khai phải dùng CSPRNG tạo **nonce mới theo từng response HTML**, gắn đúng cả header và script element. Không hardcode nonce trong bundle hoặc chia sẻ một HTML đã render nonce qua CDN cache cho nhiều người. Một bản bundler mới có thể chuyển từ external scripts sang inline bootstrap làm policy trước đó không còn phù hợp; đó là **change impact cần review**.

Với **hash-based CSP**, hash phải khớp **nội dung thực/bytes** của script được cấp quyền. Khi bundler/minifier thay nội dung, hash cũ có thể fail. Hash có thể phù hợp đoạn inline bất biến nhưng cần build pipeline sinh/cập nhật chính xác.

**Không dùng dynamic nonce mà chỉ thay value trong JavaScript**, vì CSP được browser áp từ response header. Phải test trên actual HTML bytes + header của cùng response qua CDN/gateway.

### 9.4. strict-dynamic và vấn đề trust propagation

Trong CSP3, **strict-dynamic** có thể mở rộng sự tin cậy từ một script đã có nonce/hash hợp lệ sang các scripts nó chủ động tải theo cách được browser hỗ trợ. Điều này giúp một số bundlers/third-party loaders hoạt động mà không liệt kê mọi host; **đồng thời làm tăng quyền của trusted bootstrap code**.

Regression review cần trả lời:

- Script bootstrap đã được review và có thể bị third-party remote update không?
- Loader có cho nội dung không tin cậy quyết định script URL không?
- CSP source allowlist fallback cho browsers không hỗ trợ strict-dynamic có phù hợp không?
- Dynamic imports / non-parser-inserted scripts được browser xử lý theo policy thực như thế nào?
- Untrusted script fixture có bị chặn trên browser mục tiêu hay không?

**strict-dynamic không làm thư viện bên thứ ba trở nên an toàn**. Nếu trusted script bị compromise, nó có thể tải mã độc theo quyền mà policy trao. Đánh giá trust/supply-chain độc lập với CSP syntax.

### 9.5. SRI giúp pin bytes chứ không thay CSP

Với external script tĩnh, **Subresource Integrity (SRI)** có thể giúp browser từ chối nội dung không khớp digest đã duyệt:

~~~html
<script
  src="https://static.example.com/vendor/widget-v1.js"
  integrity="sha384-<build-generated-digest>"
  crossorigin="anonymous"
  defer
></script>
~~~

Digest là **placeholder**, không phải giá trị thực dùng được. Build phải sinh digest từ **bytes được phân phối**. Khi vendor/CDN đổi nội dung mà URL không đổi, browser có thể từ chối load — đây là **fail-closed hợp lệ**, cần thay đổi phiên bản một cách có kiểm soát.

Với cross-origin scripts/styles, kiểm tra **CORS requirements** liên quan đến SRI và crossorigin; test trên public CDN thật. SRI không bảo vệ tất cả runtime dynamically loaded code nếu integration không gắn integrity/dùng cơ chế phù hợp; cũng không chặn code độc hại **đã nằm trong artifact được duyệt**.

Một regression suite phải thử:

1. Digest đúng, asset hợp lệ tải và component hoạt động.
2. Digest sai/asset bị thay bằng synthetic corrupted version, script bị browser từ chối.
3. CDN cache/proxy không âm thầm đổi bytes/content-encoding theo cách làm sai integrity validation.
4. Source chính xác vẫn thuộc CSP script-src policy; SRI không thay CSP.
5. Không ghi full vendor script/content vào logs hoặc CI artifacts nếu không cần.

### 9.6. CSP Report-Only khác Enforce

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-uri /__security/csp-report
~~~

Một Report-Only candidate **chỉ báo cáo** vi phạm của chính nó, không ngăn resource (trừ khi một **Enforce policy khác** đang chặn). Regression suite cần test:

- **Enforce:** inline script fixture không có nonce/hash thật sự bị chặn.
- **Report-Only:** candidate tạo report nhưng không chặn khi không có Enforce baseline tương ứng.
- **Two headers:** Enforce hiện hành và candidate Report-Only cùng có hiệu lực riêng; không tạo nhầm hai Enforce headers.
- **Collector:** có đủ Content-Type application/csp-report/report-uri và Reporting API application/reports+json nếu browser mục tiêu dùng report-to.
- **Privacy:** không lưu documentURL/blockedURL/referrer/script sample hoặc Cookie/Authorization nguyên dạng.

CSP reports là **dữ liệu không tin cậy** và có thể bị client giả; số report bằng 0 không chứng minh CSP an toàn khi collector/browser không gửi. Dùng **browser execution fixture + collector canary** để có bằng chứng.

## 10. Third-party integration: giảm quyền thay vì thêm wildcard

### 10.1. Đánh giá nhà cung cấp theo bề mặt tấn công

Một script bên thứ ba chạy trong document origin có thể tương tác DOM và gọi APIs theo quyền browser. Dù cookie session có HttpOnly, **malicious script cùng origin vẫn có thể gửi requests thay user**. Đây là lý do CSRF protection không giải quyết XSS và CSP cũng không bảo đảm trusted scripts là vô hại.

Đối với mỗi integration, yêu cầu:

| Câu hỏi | Lựa chọn giảm nguy cơ |
| --- | --- |
| Cần chạy script trong DOM chính? | Cân nhắc iframe sandbox hoặc server-side integration |
| Vendor cập nhật asset remote không kiểm soát? | Pin version, SRI hoặc self-host khi license/architecture cho phép |
| Script cần access token/cookie? | Không đưa secrets vào config JavaScript; tối thiểu quyền |
| Vendor cần connect tới bao nhiêu hosts? | Allowlist exact origins, route-scoped policy nếu có thể |
| Iframe cần quyền gì? | Sandbox tokens tối thiểu, postMessage origin validation |
| Vendor gửi dữ liệu gì ra ngoài? | Data-flow inventory và privacy review |
| Browser bị chặn third-party cookies? | Thiết kế redirect/BFF/first-party flow phù hợp |
| CSP chặn inline/eval? | Nâng SDK/refactor thay vì unsafe-inline/eval |
| Có dependency injection/tag manager? | Review quyền của loader và runtime dependencies |
| Vendor outage? | Timeout, fallbacks và fail-closed/fail-safe theo tác động |

### 10.2. postMessage giữa iframe và ứng dụng

Một SDK iframe có thể dùng window.postMessage để báo kết quả. Regression sau nâng cấp phải kiểm **origin validation** và schema:

~~~javascript
// Đoạn minh họa, phải kết hợp validation và state machine thật.
const approvedOrigin = "https://pay.example.net";

window.addEventListener("message", (event) => {
  if (event.origin !== approvedOrigin) return;
  if (!event.data || event.data.type !== "PAYMENT_RESULT") return;

  // Không tin event.data chỉ vì origin khớp.
  // Kiểm tra schema, correlation ID, expected state;
  // đối chiếu kết quả thanh toán với server-side provider API.
  const { status } = event.data;
  if (status !== "SUCCESS" && status !== "FAILED") return;
  handlePaymentUiStatus(status);
});
~~~

Hàm handlePaymentUiStatus là **placeholder ứng dụng tự định nghĩa**. **Không lấy postMessage làm bằng chứng thanh toán đã hoàn tất**; server phải xác minh payment result với nguồn tin cậy. Kiểm thử message từ **untrusted origin** và message sai schema không thay đổi state.

Khi dùng targetOrigin để gửi message, luôn dùng **exact approved origin** khi có thể, không mặc định '*' để “tương thích SDK mới”. Thay đổi SDK làm đổi iframe origin phải đi qua security review.

### 10.3. iframe sandbox và frame-ancestors có vai trò khác nhau

- **frame-src** (document cha) quyết định iframe có thể tải **nguồn nào**.
- **frame-ancestors** (document bị nhúng) quyết định **trang nào có thể nhúng document đó**.
- **sandbox** trên iframe hạn chế tập quyền của nội dung được nhúng, có thể được nới bằng tokens được duyệt.
- **X-Frame-Options** là cơ chế clickjacking legacy trên response bị nhúng, không thay mọi trường hợp CSP frame-ancestors.
- **CORS** không tự điều khiển iframe embedding hoặc postMessage trust; mỗi lớp có semantics riêng.

Một cập nhật payment widget có thể cần frame-src mới, nhưng không tự cấp quyền cho trang bất kỳ nhúng admin HTML. Test trusted parent và untrusted parent riêng với trusted frame và untrusted frame.

### 10.4. Quản lý scripts theo chính sách và supply chain

Một dependency do tag manager load có thể thay mà không có PR. Không coi việc chỉ ghi phiên bản trong package-lock.json là đủ. Cần:

- Inventory remote script URLs, source origins và owner.
- Contract về update/versioning, change notice và rollback của vendor.
- CSP Enforce + negative fixtures và optional SRI/self-host theo khả năng.
- Monitoring JS errors, asset failures, unexpected CSP violations và network call destinations ở mức **source classes**.
- Deadline review ngoại lệ và con đường bỏ vendor nếu rủi ro không còn chấp nhận được.
- Không tự cập nhật CSP allowlist từ báo cáo bị client giả mạo.

## 11. HSTS, security headers, HTTP firewall và CDN sau thay đổi thư viện

### 11.1. Header response có thể thay ở CDN dù Spring không đổi

Một SPA upgrade có thể đi kèm deploy mới ở CDN, đổi HTML cache key hoặc route đến một khác origin. Header bảo vệ phải kiểm trên **đúng response HTML cuối**:

| Control | Nơi quan sát | Regression có thể thấy |
| --- | --- | --- |
| Content-Security-Policy | Public HTTPS HTML document | Bị strip, nhân đôi Enforce, report-only nhầm |
| Strict-Transport-Security | Public HTTPS origin | Mất HSTS hoặc thay max-age |
| X-Content-Type-Options | Static assets và API theo contract | MIME sniffing protection mất |
| Referrer-Policy | HTML/redirect responses | Rò URL referrer quá mức |
| frame-ancestors/X-Frame-Options | HTML document nhạy cảm | Clickjacking hoặc nhúng sai |
| Cache-Control | HTML, token bootstrap, authenticated APIs | Stale app shell/session token hoặc shared cache |
| Set-Cookie | Auth response qua gateway | Domain/Path/Secure/HttpOnly/SameSite bị rewrite |

**Không dùng một request HTTP localhost để chứng minh HSTS ở public HTTPS edge**. HSTS chỉ được browser xử lý trên secure transport; thời hạn max-age có hệ quả lâu dài và includeSubDomains/preload phải có domain inventory/approval.

### 11.2. Caching, service worker và bản frontend không đồng bộ

Các trạng thái test:

~~~text
A. Fresh browser context, empty cache, release N
B. Warm context + existing service worker, upgrade N -> N+1
C. Background tab old bundle + server N+1
D. CDN partial rollout: HTML N+1, JS chunk N
E. User logs in before upgrade, logs out after upgrade
F. Login response rotates session; stale offline app retries POST
~~~

Đừng chỉ test clean browser. **Warm reload**, offline/online, tab restore và service worker activation có thể làm thay đổi thứ tự tải assets, token state hoặc request destinations.

Trong Playwright, **serviceWorkers: "block"** hữu ích để network interception deterministic, nhưng **nếu ứng dụng thật dùng service worker thì cần suite riêng để test nó**. HAR interception có giới hạn với requests bị service worker xử lý; không coi mock-network pass là production cache behavior.

### 11.3. URL encoding và HTTP firewall

Frontend router hoặc URL library đổi cách encode slash, semicolon, percent, backslash hoặc path parameters. Trên Servlet, **StrictHttpFirewall** có thể từ chối request qua **RequestRejectedException** trước MVC controller. Một code-change “sửa” bằng **setAllowUrlEncodedSlash(true)** hoặc **setAllowSemicolon(true)** phải được xem là security policy exception và kiểm tra authorization matcher bypass.

Khi test:

1. Dùng **synthetic URL cases** đã được duyệt; không ghi raw user URLs.
2. So normal route success và encoded/dot segment variants rejected theo contract.
3. Kiểm tra **gateway → Servlet container → FilterChainProxy → controller** xử lý path nhất quán.
4. Nếu có nhiều SecurityFilterChains, encoded variant không được nhảy sang chain yếu hơn.
5. Với WebFlux, test HTTP server/parser/gateway và SecurityWebFilterChain; **không coi nó dùng Servlet StrictHttpFirewall**.
6. Không mặc định mọi HTTP 400/403 là firewall: WAF, JSON validation, CSRF và authorization cũng có thể trả errors tương tự.
7. Không nới parser/firewall toàn hệ thống chỉ để một client cũ hết lỗi; ưu tiên sửa URL contract.

### 11.4. Third-party SDK không được làm thay đổi HTTP method semantics

Một SDK có thể dùng POST form redirect, PUT/PATCH, method override headers hoặc content-type khác. Review:

- HTTP method, Content-Type và headers nào mới khiến preflight?
- Request có phải mutation cần CSRF không?
- Authorization/policy của endpoint có kiểm method đúng không?
- Gateway/WAF có rewrite method/path hoặc chặn TRACE không?
- Một HTTP status 405/400 có phải lỗi route contract chứ không phải “firewall bảo vệ CSRF”?
- Retry policy có tạo duplicate side effects không?
- Synthetic negative tests có đảm bảo không đi qua security chain sai không?

## 12. Browser E2E với Playwright: kiểm chứng hành vi thực

### 12.1. Kiến trúc môi trường test

Một browser regression suite cần:

- **Frontend HTML** qua HTTPS/CDN/proxy tương đương production.
- **Backend Servlet hoặc WebFlux** với CSRF/session/security chains thực.
- **Synthetic accounts và test records**, không user/payment thật.
- **Vendor sandbox** cho payment/OIDC, phân biệt contract mocks và vendor-live.
- **Browser engines** Chromium, Firefox, WebKit có version/revision cụ thể.
- **Evidence scrub**: không xuất Cookie, Authorization, CSRF token hoặc URL chứa PII vào shared traces/HAR.
- **Policy revision**: frontend build, backend, CSP/CORS, cookies, service worker, CDN/gateway.

### 12.2. Cấu hình Playwright Test minh họa

~~~typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e/security",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.STAGING_APP_URL ??
      "https://staging-app.example.com",
    ignoreHTTPSErrors: false,
    trace: "off",
    screenshot: "off",
    video: "off"
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } }
  ]
});
~~~

Đây là cấu hình minh họa, không khuyến nghị luôn tắt trace. Traces/screenshots/video **có thể chứa credentials, token, URL PII**; khi cần debug thì chỉ bật có kiểm soát, account test, retention và quyền truy cập theo policy.

Trong các test cần route/HAR mocking deterministic, Playwright có thể **chặn service workers** bằng cấu hình serviceWorkers: "block". Nhưng nếu ứng dụng thật dùng service worker, phải có **suite riêng bật service worker** để test cache, update và offline.

### 12.3. Positive E2E login và first POST

~~~typescript
import { test, expect } from "@playwright/test";

// Staging login và order form thật. Không in credentials/token.
test("login and first order POST still work", async ({ page }) => {
  await page.goto("/login");

  await page.getByLabel("Email").fill("test-user@example.com");
  await page.getByLabel("Password").fill(
    process.env.E2E_TEST_PASSWORD ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByTestId("user-menu")).toBeVisible();

  await page.goto("/orders/new");
  await page.getByLabel("SKU").fill("P100");
  await page.getByLabel("Quantity").fill("1");
  await page.getByRole("button", { name: "Create order" }).click();

  await expect(page.getByTestId("order-created")).toBeVisible();
});
~~~

Dùng account test trong staging và mật khẩu từ CI secret manager. Test này chứng minh **positive flow**, không chứng minh CSRF vẫn enforce: cần **negative MockMvc/WebTestClient + real browser/API test** cho POST thiếu/sai token và business side-effect assertion. Không dùng screenshot hoặc network trace chứa credentials làm artifact mặc định.

### 12.4. CSP Enforce test phải dùng fixture nằm trong HTML thật

Để kiểm chứng inline script bị CSP chặn, tạo một **staging-only document** được serve với CSP Enforce:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>CSP regression fixture</title>
</head>
<body>
  <div id="fixture-ready">CSP fixture</div>
  <script>
    // Không nonce/hash; chỉ nằm ở test route.
    window.__UNAPPROVED_SCRIPT_EXECUTED__ = true;
  </script>
</body>
</html>
~~~

Playwright test:

~~~typescript
import { test, expect } from "@playwright/test";

test("unapproved inline script cannot execute", async ({ page }) => {
  await page.goto("/__test/csp-inline", {
    waitUntil: "domcontentloaded"
  });

  await expect(page.locator("#fixture-ready")).toBeVisible();

  const executed = await page.evaluate(
    () => Boolean((window as any).__UNAPPROVED_SCRIPT_EXECUTED__)
  );
  expect(executed).toBe(false);
});
~~~

**Không dùng page.evaluate để inject script làm CSP negative fixture**: automation context có thể khác parser-inserted script. Đoạn page.evaluate ở đây **chỉ đọc flag đã được fixture HTML thiết lập hoặc không**, nên kiểm đúng hành vi script từ document. Với **Report-Only**, script có thể chạy trừ khi baseline Enforce khác chặn, vì vậy test phải tách hai chính sách.

### 12.5. Header contract trên public HTML response

~~~typescript
import { test, expect } from "@playwright/test";

test("public HTML has approved CSP baseline", async ({ page }) => {
  const response = await page.goto("/");
  expect(response).not.toBeNull();

  const headers = (response as NonNullable<typeof response>).headers();
  const csp = headers["content-security-policy"] ?? "";

  expect(csp).toContain("object-src 'none'");
  expect(csp).toContain("base-uri 'self'");
  expect(csp).toContain("frame-ancestors 'none'");
});
~~~

Nếu / redirect, test phải trỏ tới **đúng HTML document**. Header tồn tại chưa chứng minh enforcement; kết hợp negative fixture. Một API JSON cùng domain phát CSP không thay thế policy trên HTML được CDN serve ở host khác.

### 12.6. Có header CSRF mà không lưu giá trị token

~~~typescript
import { test, expect } from "@playwright/test";

test("browser sends CSRF header name", async ({ page }) => {
  let headerNamePresent = false;

  page.on("request", (request) => {
    if (request.method() !== "POST") return;
    if (!new URL(request.url()).pathname.endsWith(
        "/api/browser/orders")) return;

    // Chỉ lưu Boolean; không log hoặc attach headers.
    const names = Object.keys(request.headers())
      .map((name) => name.toLowerCase());
    headerNamePresent = names.includes("x-csrf-token")
      || names.includes("x-xsrf-token");
  });

  // Cần đăng nhập và chuẩn bị order flow thật trong staging.
  await page.goto("/orders/new");
  await page.getByRole("button", { name: "Create order" }).click();

  await expect(page.getByTestId("order-created")).toBeVisible();
  expect(headerNamePresent).toBe(true);
});
~~~

Snippet giả định user đã login và form hợp lệ; trong project thật thêm fixture/setup state thích hợp. Nó chỉ xác minh **tên header tồn tại**, không tự chứng minh token khớp expected token ở server. Không print toàn bộ request.headers() ra console.

### 12.7. Payment SDK browser E2E và postMessage

Regression suite cho iframe payment nên:

- Trusted provider iframe được load theo CSP **frame-src**, untrusted frame bị chặn.
- Third-party cookie restrictions của browser không tạo login/payment loop; fallback được kiểm tra.
- postMessage từ **untrusted origin** hoặc sai schema không thay đổi app state.
- Ứng dụng không coi client postMessage SUCCESS là kết quả thanh toán đã xác nhận; backend phải kiểm tra provider.
- Vendor timeout/error và retry/idempotency không tạo duplicate side effects.
- Khi SDK chuyển domain, không thêm wildcard CSP/CORS mà chưa review.
- Vendor sandbox smoke phải tách contract mock tests để thấy integration drift.

### 12.8. Service worker, cache và rollback tests

~~~text
Clean browser:
  New HTML + new bundle -> CSRF/CORS/CSP flows PASS

Warm browser:
  Old service worker + cached assets -> update safe

Two tabs:
  Tab A old session/token, Tab B login/logout -> state consistent

Partial CDN deploy:
  HTML revision N+1 + stale chunk N -> recovery defined

Offline/online:
  No stale CSRF bootstrap replay; unsafe POST not blindly retried

Rollback:
  Known-good HTML/bundle/CDN policy remains fetchable
~~~

Test cả **service worker enabled và disabled** nếu production sử dụng SW. HAR mocks có thể không nhìn thấy requests do SW intercept; không coi mock-network PASS là bằng chứng production cache đúng.

## 13. Ma trận tương thích browser, session, frontend/backend và nhà cung cấp

### 13.1. Không chạy toàn bộ Cartesian product một cách máy móc

Số tổ hợp browser × device × auth × SDK × region × cache × frontend/backend versions tăng rất nhanh. Dựa trên threat model và blast radius để ưu tiên:

| Dimension | Giá trị cần có | Khi mở rộng |
| --- | --- | --- |
| Browser engine | Chromium, Firefox, WebKit | Vendor dùng API đặc thù hoặc Safari/WebView lỗi |
| Auth state | Anonymous, authenticated, expired, logged out | Auth SDK, session policy thay đổi |
| Session mechanism | Cookie browser, Bearer-only | HTTP client, hybrid auth changes |
| Frontend cache | Clean, warm SW, stale tab | Bundler/SW/CDN changes |
| Frontend revision | Old, new, rollback candidate | Rolling deploy và canary |
| Backend revision | Old/current, canary/new | Spring Security/API contract changes |
| Third-party | Mock, vendor sandbox, forced error | Payment/login widget updates |
| Origin | Same-origin, trusted cross-origin, untrusted | CORS/frame/redirect changes |
| CSP | Enforce baseline, Report-Only candidate | Script/iframe changes |
| Network | Fast, slow, offline → online | Retry/token refresh changes |
| Gateway | Direct real server, public HTTPS edge | Path/Host/TLS rewrites |
| Region | Main, canary region | CDN/edge config drift |
| Authorization | User with/without role/object access | Changes to shared UI/API routes |

**Pairwise coverage** giảm chi phí phần ít rủi ro. Những tổ hợp quan trọng cần test cụ thể: **new frontend + old backend**, **old frontend + new backend**, **old tab + logout**, **vendor SDK + CSP Enforce**, **service worker stale + login**, **untrusted Origin + credentials**.

### 13.2. Backward compatibility window quyết định trước deploy

Trong rolling deploy, browser có thể giữ frontend revision cũ hàng giờ sau khi API mới phát hành:

~~~text
Front-end N -> Back-end N: PASS
Front-end N+1 -> Back-end N: PASS nếu rollout không atomic
Front-end N -> Back-end N+1: PASS khi old tabs còn sống
Front-end N+1 -> Back-end N+1: PASS
Rollback Front-end N -> Back-end N: PASS
~~~

Nếu không thể hỗ trợ cửa sổ tương thích, cần **version negotiation hoặc safe hard-refresh/relogin strategy**, có bằng chứng không mất dữ liệu đang nhập. Không giải quyết incompatibility bằng cách mở CORS tùy ý hoặc tắt CSRF.

### 13.3. Bằng chứng có scope, build và policy revision

~~~json
{
  "testId": "csrf-first-post-after-login",
  "frontendBuild": "web-r52",
  "backendBuild": "api-r88",
  "browserEngine": "chromium",
  "springSecurityVersion": "resolved-build-version",
  "cspPolicyRevision": "csp-v11",
  "edgePolicyRevision": "edge-v6",
  "environment": "staging",
  "outcome": "PASS"
}
~~~

Trong CI thật phải ghi **resolved version/digest** chính xác thay placeholder. Không đính kèm token, cookie, HAR đầy đủ, request body hoặc email user. Test PASS không có version/revision dễ trở thành bằng chứng lỗi thời.

### 13.4. Một screenshot chưa chứng minh bảo mật

Ảnh checkout “thành công” chưa chứng minh untrusted script/frame bị CSP chặn, POST không token bị deny, authorization đúng, CORS untrusted Origin không được đọc response, hoặc cookie/HTTPS policy đúng. Mỗi evidence record phải gắn **invariant ID, environment, revision, positive/negative result và owner**.

## 14. Privacy-safe telemetry sau frontend hoặc SDK upgrade

### 14.1. HTTP status khác confirmed security reason

Một **403** có thể do CSRF, authorization, WAF hoặc gateway. **400** có thể do StrictHttpFirewall, Servlet container, JSON parser hay request validation. CSP violation report có thể do browser, extension hoặc client giả gửi.

Không nên có counter security_attacks_total sinh từ mọi 400/403. Tách:

~~~text
http_requests_total
  source=edge | application
  status_class=2xx | 3xx | 4xx | 5xx

http_security_decisions_total
  control=csrf | authn | authz | firewall | cors | waf
  reason=finite_reason_code
  decision=allowed | denied | error
  evidence=confirmed | inferred | unclassified

browser_flow_outcomes_total
  flow=login | first_post | checkout | logout
  result=success | failure
  frontend_revision=...
~~~

Đây là **đề xuất metric schema**, không phải metrics mặc định Spring Security. Chỉ gắn **confirmed CSRF** khi có dữ liệu từ đúng CsrfFilter/CsrfWebFilter rejection path; nếu chỉ biết status=403, dùng reason unclassified.

### 14.2. CSP reports và HTTP debug logs có thể chứa secrets

Báo cáo CSP có thể chứa:

- document-uri/documentURL và blocked-uri/blockedURL với query/ID.
- referrer, original-policy và source-file.
- script-sample/sample khi bật report-sample.
- user-agent, status/line/column có thể hỗ trợ fingerprint.
- Payload giả do non-browser clients gửi.

Security logs còn có thể chứa **CSRF token, JSESSIONID, Authorization/JWT, refresh token, email/password, raw body**.

Không lưu raw report. Collector nên **giới hạn body/batch/nesting/rate**, chỉ lưu **route group, directive, source class, disposition, trusted policy revision** trước khi gửi sang metrics/logs. Không in exception.getMessage() của RequestRejectedException vì có thể chứa raw URI.

**Không mặc định hash token/PII** để coi là dữ liệu an toàn; hash vẫn có thể là tracking identifier. Không dùng user ID, IP, request ID, full URL/query hoặc untrusted Origin/Host làm Prometheus label.

### 14.3. Dashboard cần gắn revision deploy

Theo dõi:

1. **Login success, first unsafe POST success, checkout success** theo frontend/backend revision.
2. **Confirmed CSRF deny rate** theo route group và auth stage; không suy diễn malicious từ một request.
3. **CORS preflight success/failure** theo allowed-origin class và header/method group.
4. **CSP Enforce vs Report-Only violations** theo directive/source class.
5. **Asset load/SRI/CSP failures** của JS chunks và vendor SDK theo frontend build.
6. **Session/cookie errors**: logout loops, expiry, browser family.
7. **Authorization**, **firewall** và **WAF** rejects riêng.
8. **Public HTTPS header contract**: CSP, HSTS, cookie attributes và Cache-Control.
9. **Collector health**: ingestion/drop, parser errors và rate limits.
10. **Synthetic negative probe PASS/FAIL** cùng legitimate business flow success.
11. **Policy/config drift** giữa canary/control, CDN regions, gateway và Spring Security BOM.

Không đồng nhất **CSP reports tăng = XSS attacks tăng**; reports có thể do thay scripts, extension noise hoặc report forgery.

### 14.4. Tỷ lệ có mẫu số phù hợp

Ví dụ:

\[
\text{CSRF deny rate}
=
\frac{\text{unsafe protected requests bị CSRF filter từ chối}}
{\text{unsafe requests đến protected routes}}
\]

Nếu lấy tổng CDN requests (bao gồm static assets, OPTIONS, WAF rejects) làm mẫu số, một route bị lỗi có thể bị che. Cần biết sampling rate và sample size khi so canary/control.

Một upgrade có thể làm **403 tăng do scanning** nhưng checkout vẫn khỏe, hoặc **403 tăng nhẹ** mà ảnh hưởng toàn bộ người dùng WebKit ở bước thanh toán. Alert phải xem **route criticality + user-flow SLO**, không chỉ số lượng lỗi.

### 14.5. Synthetic privacy canary

Trong staging, tạo một chuỗi secret **giả** như CANARY_DO_NOT_PERSIST trong query và script sample của synthetic CSP report; kiểm tra:

- Logs gateway/WAF, app, background queue, retry/DLQ và APM.
- Trace attributes/baggage, metrics exemplars.
- CI/test attachments, HAR, screenshots và vendor monitoring.
- Dashboard exports hoặc object storage theo quy trình test.

Nếu canary xuất hiện ngoài vùng memory được phép, gate **FAIL** và sửa trước production rollout. Không cố tình gửi JWT, JSESSIONID hoặc CSRF token thật vào telemetry để thử redaction.

## 15. CI/CD gates, canary và rollback sau frontend/SDK upgrade

### 15.1. Pipeline đi từ change impact đến evidence

~~~mermaid
flowchart TD
    A["Frontend / third-party dependency change"] --> B["Lockfile, asset/vendor inventory"]
    B --> C["SCA + provenance + static contract tests"]
    C --> D["MockMvc / WebTestClient security negative tests"]
    D --> E["Real HTTP server + gateway contract"]
    E --> F["Browser E2E clean/warm/auth/vendor"]
    F --> G["Public HTTPS CSP/CORS/HSTS/cookie probes"]
    G --> H["Canary + synthetic security tests + business metrics"]
    H --> I{"Security và business gates PASS?"}
    I -->|Có| J["Promote"]
    I -->|Không| K["Stop / investigate / rollback"]
    J --> L["Post-release drift monitoring"]
~~~

Một pipeline có thể có các nhóm stage:

~~~yaml
stages:
  - dependency-provenance
  - frontend-contract-and-unit
  - spring-security-integration
  - browser-e2e-fast
  - real-server-and-edge
  - vendor-sandbox-smoke
  - canary-security-and-business-probes
  - promote-or-rollback
~~~

Đây là **pseudocode CI**, không phải cú pháp hoàn chỉnh cho một CI provider. Trong dự án thật, mỗi stage cần commands/permissions/artifact policies/secrets được duyệt. Các tình huống rủi ro cao phải chạy negative tests **trước merge**, không chỉ hậu kiểm production.

### 15.2. Security stop gates bắt buộc

Dừng hoặc rollback nếu:

- Cookie-auth browser POST **thiếu CSRF mà vẫn tạo side effect**.
- Bearer-only route bắt đầu chấp nhận **cookie-only credentials** trái thiết kế.
- Credentialed CORS cấp access cho **untrusted Origin**.
- CSP Enforce trên public HTML mất hẳn hoặc untrusted inline/external script fixture được chạy.
- SDK hợp lệ bị CSP chặn khiến **login/checkout critical flow** thất bại hàng loạt.
- Session cookie mất Secure/HttpOnly hoặc scope bị thay đổi không được review.
- URL encoded/path normalization variants **bypass authorization/SecurityFilterChain**.
- HSTS/CSP/cookie policy ở public edge khác revision đã phê duyệt.
- Token hoặc PII xuất hiện trong logs/APM/CSP report storage.
- Service worker hoặc rollback làm browser stale gọi API không tương thích ở flow nhạy cảm.
- Session/token rotation hoặc auth redirects tạo fail rate vượt gate với baseline/sample đủ.

Không nhất thiết rollback chỉ vì **CSP Report-Only warnings** tăng nếu đã xác minh noise và Enforce/business contracts đều đạt. Nhưng một **negative security invariant FAIL** đủ để ngăn promote, không đợi tỷ lệ 403.

### 15.3. Canary phải có positive lẫn negative probes

| Security | Business |
| --- | --- |
| CSRF negative synthetic POST vẫn deny | First POST sau login vẫn thành công |
| Unapproved CSP fixture vẫn blocked | JS bundle/payment SDK hoạt động |
| Trusted/untrusted CORS contract đúng | SPA data loading không CORS error |
| Session cookie attrs vẫn đúng | Login/logout không loop |
| HTTP firewall path variant bị reject | Link routing bình thường hoạt động |
| Security logs không lưu tokens/PII | API latency/error budget đạt |
| Public HTTPS headers/policy revision đúng | Static assets/load time ổn định |

Canary có control cohort và mốc quan sát phù hợp browser diversity. **Bất biến bảo mật bị phá đã được xác nhận** là điều kiện dừng ngay; với UX degradation cần xét user impact, confidence và thresholds đã quyết định trước rollout.

### 15.4. Rollback là một bộ phiên bản tương thích

~~~text
frontend_HTML_build
javascript_chunk_manifest_and_SRI
service_worker_version
backend_artifact_and_spring_security_BOM
CSRF_repository_and_request_handler
CSP_Enforce_and_Report_Only_policy_revision
CORS_session_cookie_policy
gateway_WAF_CDN_routing_revision
vendor_sdk_version_or_known_good_endpoint
synthetic_evidence_bundle
~~~

Rollback chỉ Java backend khi CDN HTML/service worker/CSP còn bản mới có thể không khắc phục. Rollback frontend khi backend mới thay token contract có thể làm 403 tăng thêm. Sau rollback, chạy lại **positive user flow**, **negative CSRF/authz/CSP probes**, cookies/CORS trên browser và public HTTPS edge. Pod healthy không đủ.

### 15.5. Ngoại lệ third-party phải có scope và thời hạn

Nếu vendor SDK tạm cần CSP host mới, frame-src hoặc CORS origin:

- Ghi rõ vendor, purpose, trust boundary, exact origin, route scope và owner.
- Chỉ dùng **bounded allowlist**, không wildcard để làm request hết lỗi.
- Có expiry, sunset plan và rollback artifact/policy.
- Có positive/negative browser test và vendor sandbox evidence.
- Theo dõi CSP Enforce violations và legitimate flow rates sau canary.
- Review lại khi SDK/domain thay đổi; không gia hạn tự động vô hạn.

CSP reports là low-trust input, không đủ để tự thêm host vào allowlist.

## 16. Runbook chẩn đoán hồi quy sau frontend/SDK release

### 16.1. Runbook A — Login thành công nhưng first POST 403

**Dấu hiệu:** Sau nâng HTTP client/auth SDK, POST đầu tiên sau login thường 403.

1. Xác minh **đúng tầng từ chối**: CsrfFilter/CsrfWebFilter, authorization hoặc WAF/gateway. 403 không tự khẳng định CSRF.
2. So frontend/backend release, CSRF repository/request handler và session cookie policy.
3. Kiểm tra GET token bootstrap có thành công, materialize token, Cache-Control no-store và cùng session không.
4. Kiểm tra login/logout có clear token cũ, SPA có lấy token mới sau auth transition không.
5. Kiểm tra raw XSRF cookie vs XOR-masked handler, tên header và host/path cookie.
6. Kiểm tra OPTIONS preflight; nếu actual POST không được phát thì lỗi CORS không phải POST CSRF.
7. Tái hiện bằng staging test user, không in token/cookie vào ticket.
8. Nếu luồng trọng yếu bị ảnh hưởng, stop rollout hoặc rollback known-good frontend/backend tuple.
9. Chạy lại **POST thiếu/sai token bị chặn/no side effect** và legitimate POST success.
10. Gắn regression test vào CI để chặn tái diễn.

### 16.2. Runbook B — CSP chặn payment SDK hoặc dynamic chunks

1. Kiểm tra CSP Enforce và Report-Only tại **HTML document origin**, không chỉ API response.
2. Xem script/frame/connect/style directive nào gây block; phân biệt extension noise.
3. So frontend build/bundler/vendor revision với CSP policy version.
4. Với nonce/hash, kiểm đúng response HTML và CSP header cùng revision; không tái sử dụng nonce trên cached HTML.
5. Nếu SRI fail, kiểm asset bytes/digest và CDN caching, không xóa integrity mù quáng.
6. Chạy browser sandbox payment positive flow và untrusted script/frame negative fixture.
7. Ưu tiên self-host/version pin/refactor nguồn; chỉ allowlist exact host đã review khi cần.
8. Không thêm unsafe-inline, unsafe-eval hoặc wildcard để “cứu” SDK mà chưa threat review.
9. Rollback frontend/CSP/vendor tuple tương thích nếu checkout outage.
10. Xác minh lại collector không lưu raw URLs/sample, dashboard không nhầm Report-Only thành Enforce.

### 16.3. Runbook C — Browser báo CORS error sau đổi HTTP client

1. Xác minh có OPTIONS trước POST không, preflight status và allow headers cụ thể.
2. OPTIONS **không mang session cookie**, nên auth redirect hoặc 401 trên OPTIONS là dấu hiệu CORS/filter order.
3. So Origin của frontend, API origin, content-type/custom headers mới.
4. Kiểm CORS allowlist ở đúng Servlet/Reactive stack và ở public gateway, không chỉ bean khác stack.
5. Kiểm credentials include/same-origin mode của frontend; cookie blocked reasons.
6. Khi OPTIONS pass, test actual POST có cookie và CSRF token đúng.
7. Negative test untrusted Origin vẫn không được credentialed access.
8. Không bật wildcard Allow-Origin với credentials hoặc tắt CSRF.
9. Thêm real-browser contract test cho HTTP client version mới.

### 16.4. Runbook D — Lỗi chỉ ở một browser hoặc sau idle dài

1. Phân nhóm browser family, frontend build, route group và auth stage.
2. Xem SameSite, Secure, Domain/Path, third-party cookie policies ở browser thực.
3. Kiểm session timeout, token refresh, multi-tab logout và history restore.
4. So service worker app shell warm vs fresh, stale chunks và offline recovery.
5. Kiểm CSP connect-src/SRI load failures nếu bootstrap token không chạy.
6. Không kết luận từ Postman/curl đã thành công: chúng không thực thi browser CSP/CORS/SameSite.
7. Reproduce bằng clean/warm browser contexts và phiên bản thực.
8. Nếu regression gây outage, rollback frontend/SW/edge policy tương thích, không mở cookie scope không cần.

### 16.5. Runbook E — Third-party script đổi host hoặc remote asset

1. Ghi chính xác vendor, integration purpose, remote asset version/URL và policy revision.
2. Đánh giá dependency trust/provenance và vendor change notice.
3. Kiểm CSP source, script nonce/hash, strict-dynamic, SRI và CORS asset response.
4. Kiểm script mới có mở kết nối, iframe hoặc form action chưa được review không.
5. Test legitimate SDK flow và blocked untrusted resource.
6. Không tự thêm host từ CSP reports; payload có thể bị giả.
7. Nếu thiếu kiểm soát phiên bản, cân nhắc self-host/version pin, sandbox hoặc tách origin.
8. Thực hiện security review trước khi mở CSP/CORS; có owner/expiry và rollback.

### 16.6. Runbook F — CDN/WAF/path rewrite khác giữa các regions

1. So frontend/CDN asset manifest, HSTS/CSP headers, gateway route revision và Spring Security BOM.
2. Kiểm đúng HTML origin, HTTPS scheme và X-Forwarded-* trusted proxy boundary.
3. Tái hiện synthetic request qua public edge và direct real server.
4. Với Servlet, kiểm StrictHttpFirewall, RequestRejectedException và SecurityFilterChain matching.
5. Với WebFlux, xem Reactor Netty/server parser, WebFilters và gateway routing, không gọi là Servlet firewall.
6. Kiểm URL encoded/semicolon variants không bypass authz/CSRF.
7. Nếu canary region có policy yếu hơn, cô lập và khôi phục known-good config.
8. Sau sửa, chạy edge synthetic probes, login/checkout và security negative tests trên các regions.

### 16.7. Runbook G — Security telemetry bắt đầu lưu token hoặc PII

1. Giới hạn nguồn ghi raw request/report/headers và quyền truy cập APM/SIEM ngay.
2. Không copy secret thật vào chat/ticket; dùng request ID đã scrub.
3. Xác định loại dữ liệu: CSRF token, JSESSIONID, JWT/refresh token, reset link, personal URL/script sample.
4. Kiểm ingress/WAF, app logs, traces, queue/DLQ, backups và vendor exports.
5. Nếu session/JWT credentials bị lộ, thực hiện revocation/rotation theo incident policy; không coi mọi CSRF token riêng lẻ tương đương account takeover.
6. Sửa logging bằng output allowlist, request-body capture off và privacy-safe CSP collector.
7. Kiểm retention/xóa ở từng sink và synthetic canary test.
8. Bổ sung privacy regression gate cho SDK hoặc monitoring library vừa nâng.

### 16.8. Runbook H — Regression suite PASS nhưng production vẫn lỗi

1. Xác minh suite test đúng **artifact/revision/HTML origin** production đã deploy.
2. Tìm mocks bỏ qua vendor-live behavior, network intercept không thấy service worker, browser khác version hoặc dữ liệu test quá đơn giản.
3. Đối chiếu actual gateway/CDN/CSP/CORS/cookie headers ở public edge.
4. Kiểm old frontend tabs/new backend rolling deploy compatibility.
5. Kiểm telemetry có sampling/drop, collector outage hoặc sai reason classification không.
6. Tạo synthetic repro cố định trong staging theo đường public-edge-like, không dump credentials thật.
7. Thêm **đúng test bị thiếu**, không tăng số lượng assertions ngẫu nhiên.
8. Sửa nguyên nhân, kiểm positive/negative invariants rồi mới promote lại.

### 16.9. Cây quyết định nhanh

~~~mermaid
flowchart TD
    A["Regression sau frontend/SDK change"] --> B{"Security negative invariant fail?"}
    B -->|Có| C["Stop rollout / contain / rollback"]
    B -->|Không| D{"Legitimate browser flow fail?"}
    D -->|Có| E["Reproduce, inspect CORS/CSP/CSRF/cookie layer"]
    D -->|Không| F{"External report/error spike?"}
    F -->|Có| G["Classify CSP reports, WAF, scanners, telemetry health"]
    F -->|Không| H["Continue canary + drift monitoring"]
    E --> I["Fix specific contract and re-run positive/negative tests"]
    G --> I
    C --> I
    I --> J["Update change-impact evidence and owner"]
~~~

Không biến biểu đồ thành máy phán đoán “attack confirmed” dựa trên một HTTP status. Một release có thể vừa tạo lỗi CSRF cho user hợp lệ, vừa trùng thời điểm bị bot scanning làm WAF/403 tăng.

## 17. Bài tập thực hành và tiêu chí nghiệm thu

### 17.1. Bài A — Nâng HTTP client nhưng CSRF header biến mất

**Đề:** Một SPA dùng session cookie đổi thư viện fetch wrapper. Login vẫn thành công nhưng POST /api/browser/orders 403.

**Thực hiện:**

1. Xác định browser có gửi actual POST hay bị CORS preflight chặn.
2. Kiểm tên CSRF header có mặt, không in giá trị token.
3. Kiểm session cookie, raw/XOR request handler và token bootstrap.
4. Viết MockMvc/WebTestClient negative test POST thiếu token.
5. Viết browser positive test login → first POST.
6. Tách regression từ missing/stale token và authorization deny.

**Đạt khi:** Sửa frontend/contract thay vì disable CSRF; POST thiếu token bị chặn, POST hợp lệ thành công và không có side effect ở nhánh deny.

### 17.2. Bài B — Auth SDK đổi login redirect

**Đề:** SDK mới chuyển qua cross-site redirect, browser mất session hoặc không refresh token sau authentication.

**Thực hiện:** Kiểm SameSite/Secure/Domain/Path và trusted proxy, chạy browser Chromium/Firefox/WebKit, test auth session transition, token B sau login và logout/multi-tab.

**Đạt khi:** Có bằng chứng cookie thật được gửi, frontend token refresh đúng thời điểm, session fixations đã được xử lý và không mở HttpOnly trên JSESSIONID.

### 17.3. Bài C — Thư viện UI bắt đầu dùng inline script

**Đề:** Sau nâng UI library, CSP Enforce chặn bootstrap code, dev muốn bật unsafe-inline.

**Thực hiện:** Xây HTML fixture staging, test inline script không nonce/hash bị chặn, refactor sang external script hoặc nonce/hash phù hợp, kiểm login/checkout positive.

**Đạt khi:** Không mở unsafe-inline toàn origin; có positive và negative CSP browser evidence sau sửa.

### 17.4. Bài D — Vendor SDK đổi CDN URL

**Đề:** Payment SDK tải asset từ host mới, integrity không còn khớp.

**Thực hiện:** Kiểm phiên bản/digest/provenance và HTTP asset response, cập nhật SRI từ bytes được duyệt nếu cần, test CSP script-src/frame-src/connect-src và vendor sandbox.

**Đạt khi:** Trusted SDK load, corrupted synthetic asset không load, không thêm wildcard hosts và có owner/rollback.

### 17.5. Bài E — Iframe provider đổi origin và postMessage contract

**Đề:** Payment iframe chuyển origin và field trong message thay đổi.

**Thực hiện:** Test frame-src allowlist, message origin/schema validation, mock untrusted message và server-side verification của payment state.

**Đạt khi:** UI không coi postMessage SUCCESS là server payment success; untrusted origin không đổi trạng thái; production vendor sandbox flow hợp lệ.

### 17.6. Bài F — SPA chuyển API sang subdomain khác

**Đề:** App ở app.example.com chuyển API từ cùng origin sang api.example.com.

**Thực hiện:** Thiết lập exact CORS origin/method/headers/credentials, browser fetch credentials include, token bootstrap và cookie Domain/Path; test OPTIONS không Cookie, actual POST có CSRF.

**Đạt khi:** Trusted origin hoạt động; untrusted origin không được credentialed access; cookie host-only không bị giả định JS đọc chéo host.

### 17.7. Bài G — Service worker cache bundle cũ

**Đề:** Một tab mở lâu dùng JS build N, backend đã N+1; app shell offline cache tạo CSRF 403 và chunk 404.

**Thực hiện:** Test clean/warm Playwright contexts, SW enabled/disabled, cache update, token epoch, frontend/backend compatibility và rollback.

**Đạt khi:** Có recovery strategy không làm mất side effects/không retry unsafe POST mù quáng; không dùng HAR mock PASS thay SW-live test.

### 17.8. Bài H — Backend Servlet và WebFlux chạy song song

**Đề:** Gateway Reactive đứng trước Servlet session API, một WebFlux endpoint khác dùng WebSession. SDK URL encoder bắt đầu dùng semicolon.

**Thực hiện:** Unit StrictHttpFirewall, real Servlet container + gateway tests, WebTestClient CSRF, real Netty parser tests và SecurityFilterChain selection.

**Đạt khi:** Không lẫn Servlet RequestRejectedException với WebFlux parser; encoded path không bypass authorization và normal route vẫn hoạt động.

### 17.9. Bài I — CORS preflight và CSRF lỗi đồng thời

**Đề:** Browser OPTIONS 401 do gateway, sau sửa OPTIONS thì POST 403 vì token stale.

**Thực hiện:** Triage theo từng request; sửa preflight/filter order trước, sau đó token refresh; viết test hai nhánh riêng.

**Đạt khi:** Không gắn nhãn preflight 401 là CSRF denial, không tắt CsrfFilter; browser positive flow và CSRF negative test đều PASS.

### 17.10. Bài J — Browser báo CSP violations nhưng collector im lặng

**Đề:** Chuyển Report-Only sang Enforce sau nâng payment SDK, collector không nhận reports.

**Thực hiện:** Kiểm HTML policy headers/report-uri/report-to/Reporting-Endpoints, browser support và collector health; tạo staging script fixture và synthetic report.

**Đạt khi:** Không coi reports=0 là an toàn; đo được browser script execution blocked và legitimate payment flow riêng.

### 17.11. Bài K — Log leak sau nâng monitoring SDK

**Đề:** HTTP instrumentation mới ghi request headers và CSP sample có CSRF token/PII vào APM.

**Thực hiện:** Chặn capture nguồn, phân loại dữ liệu, kiểm queue/exports/backups, viết synthetic canary redaction test và retention workflow.

**Đạt khi:** Chỉ lưu control/reason/route group/release; không CSRF/JSESSIONID/JWT/raw URL/script sample trong sinks. Không cần gửi credential thật vào test.

### 17.12. Bài L — Canary release của auth SDK lỗi trên WebKit

**Đề:** Chromium/Firefox pass nhưng WebKit có login loop trong iframe bên thứ ba.

**Thực hiện:** Xem cookie blocked reason, third-party cookie policy, cross-site redirect, SameSite và postMessage; so versions/canary.

**Đạt khi:** Có workaround/architecture an toàn hoặc rollback, không mở cookie security attrs một cách thiếu review.

### 17.13. Bài M — Build tương thích old/new revisions

**Đề:** Backend N+1 rollout dần, frontend N có service worker giữ app trong 24 giờ, N+1 thêm header mới.

**Thực hiện:** Viết contract matrix N/N+1, safe fallback và forced refresh khi không tương thích, test both old/new frontend against both backend versions.

**Đạt khi:** Không mở CORS/CSRF để hỗ trợ version cũ; biết lúc nào phải hiển thị re-login/hard refresh và đảm bảo pending data an toàn.

### 17.14. Bài N — Thiết kế security regression gate

**Đề:** Một PR nâng payment SDK, auth client và bundler cùng lúc.

**Thực hiện:** Tạo risk matrix từ change inventory, ưu tiên critical E2E flows, CI stages, negative CSRF/CSP/CORS tests, vendor smoke, canary criteria và rollback tuple.

**Đạt khi:** Có owner cho từng gate, PASS/FAIL measurable, không chỉ một test tên “checkout works”.

### 17.15. Bài O — Simulate path-normalization bypass trong staging được phép

**Đề:** Frontend routing library đổi cách encode path; một securityMatcher chọn nhầm Bearer-only chain.

**Thực hiện:** Dùng synthetic encoded path cases có scope, test gateway/Servlet/Reactive routing, authz negative tests, business side effects.

**Đạt khi:** Không mở StrictHttpFirewall bừa bãi; chứng minh không có đường match vào chain yếu hơn, route bình thường vẫn pass.

## 18. Checklist phát hành và nguyên tắc vận hành

### 18.1. Checklist trước merge và promotion

| Nhóm kiểm soát | Điều kiện PASS |
| --- | --- |
| **Scope/version** | Lockfile/BOM, vendor/script origins, frontend + backend + edge revisions được ghi |
| **Threat model** | Change impact theo assets, origins, credentials, trust boundaries được review |
| **Positive E2E** | Login, first POST, logout, checkout và các flows phụ thuộc SDK hợp lệ |
| **CSRF negative** | Cookie-auth unsafe mutation thiếu/sai token bị chặn và không side effect |
| **CSRF lifecycle** | Bootstrap, login/logout refresh, raw/XOR handler và multi-tab/idle được kiểm |
| **CORS preflight** | Trusted OPTIONS pass không Cookie, untrusted Origin không được credentialed access |
| **Cookie/session** | Secure, HttpOnly, SameSite, Domain/Path, credentials mode đúng browser |
| **Bearer boundary** | M2M/Bearer-only không chấp nhận cookie-only fallback trái thiết kế |
| **CSP Enforce** | HTML public origin có policy đúng và untrusted script fixture bị block |
| **CSP Report-Only** | Candidate không bị hiểu nhầm thành Enforce, collector health được kiểm |
| **Dynamic assets** | Bundle lazy imports, CDN chunks, nonce/hash, SRI và worker source hoạt động |
| **Third-party** | Vendor sandbox, iframe origin, postMessage validation và fallback có bằng chứng |
| **HSTS/headers** | Public HTTPS document/cache/session headers đúng revision |
| **HTTP firewall** | Servlet StrictHttpFirewall và gateway parser không tạo authz matcher bypass |
| **Reactive parity** | WebTestClient/WebSession/CORS/Netty checks theo stack thật, không mượn Servlet tests |
| **Service worker** | Clean + warm + offline/online + rollback behavior có test |
| **Version skew** | Old/new frontend và backend combinations đạt compatibility window |
| **Security telemetry** | 400/403 reasons phân lớp, metrics low-cardinality, không log tokens/PII |
| **Browser matrix** | Chromium/Firefox/WebKit theo rủi ro và device-specific flows |
| **CDN/WAF** | Public edge probes và region/revision drift checks PASS |
| **Canary** | Positive business flows và negative security probes cùng PASS |
| **Rollback** | Known-good app/frontend/SW/vendor/CSP/CORS/edge tuple sẵn sàng |
| **Exceptions** | Exact scope, owner, expiry, residual risk và evidence được phê duyệt |
| **Post-deploy** | Alert, owner triage, monitoring cadence và evidence freshness rõ |

### 18.2. Mười lăm nguyên tắc cốt lõi

1. **Một thay đổi frontend hoặc SDK có thể làm mất bảo vệ ở backend/browser** dù không sửa Spring Security.
2. **Thay đổi phải có dependency/vendor inventory và threat impact**, không chỉ changelog UI.
3. **Một happy-path E2E test PASS không chứng minh bảo mật**; mỗi control cần negative invariant.
4. **CSRF phụ thuộc authentication credentials thực**, không phụ thuộc tên JSON, REST, JWT hoặc stateless.
5. **Token mới sau login/logout và raw/XOR request handler** phải nằm trong regression contract của SPA.
6. **CORS preflight khác actual POST**, không dùng lỗi OPTIONS để kết luận CsrfFilter đã từ chối POST.
7. **Same-origin, same-site và third-party cookie policy khác nhau**; phải kiểm trong browser.
8. **CSP trên HTML origin mới có ý nghĩa cho HTML**, không chỉ CSP header trên JSON API.
9. **Report-Only không thay Enforce**, reporting volume không phải số tấn công đã xác nhận.
10. **Nonce/hash/SRI phải gắn với bytes và HTML response đúng phiên bản**, nhất là qua CDN.
11. **Third-party script cùng origin là một trust decision**, CSP không làm mã đã được cấp phép tự nhiên an toàn.
12. **Servlet StrictHttpFirewall và WebFlux parser khác nhau**, phải test đúng tầng real server/gateway.
13. **Service worker và stale tabs tạo version skew**, nên test clean/warm/offline/rollback chứ không chỉ refresh sạch.
14. **Không đưa Cookie/JWT/CSRF token và CSP report raw vào logs/APM**, kể cả khi debug regression.
15. **Canary/rollback phải bảo toàn cả security invariants và user-flow SLO**, không chỉ làm HTTP 403 biến mất.

**Kết luận:** Kiểm thử hồi quy sau thay đổi frontend hoặc thư viện bên thứ ba là quy trình **inventory → threat model → invariant → positive+negative tests → browser và public-edge evidence → canary → rollback/drift monitoring**. Khi giữ nguyên chuỗi kiểm chứng đó, đội phát triển có thể nâng SDK, bundler và browser integrations mà vẫn duy trì CSRF, CORS, CSP, HSTS, HTTP firewall và session protection trong Spring Security Servlet lẫn Reactive. Không nên sửa lỗi tích hợp bằng cách giảm mức bảo vệ khi chưa xác định đúng tầng bị tác động.

## Tài liệu tham khảo chính thức và bổ trợ

- [Spring Security 6.5 — Servlet CSRF và SPA integration](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Servlet CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — Reactive CORS](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — Servlet Security Headers/CSP/HSTS](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — Reactive Security Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Security 6.5 — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/firewall.html)
- [Spring Security 6.5 — Servlet Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [Spring Security 6.5 — Reactive Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html)
- [Playwright — Writing Tests](https://playwright.dev/docs/writing-tests)
- [Playwright — Browser Context](https://playwright.dev/docs/api/class-browsercontext)
- [Playwright — Service Workers](https://playwright.dev/docs/service-workers)
- [Playwright — Network Mocking](https://playwright.dev/docs/mock)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
- [MDN — CSP implementation guidance](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/CSP)
- [MDN — Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [OWASP — Third Party JavaScript Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)







