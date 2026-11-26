# Theo dõi lỗi CSRF và phân biệt lỗi tích hợp với yêu cầu bất thường

## Mục tiêu và bối cảnh vận hành

Trong chương **Vận hành và giám sát** thuộc dịch vụ **SPRING_SECURITY_HTTP_PROTECTION**, Spring Security bảo vệ HTTP và trình duyệt bằng **CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session**. Một ứng dụng đã bật **CsrfFilter** trên Servlet hoặc **CsrfWebFilter** trên Reactive/WebFlux vẫn cần theo dõi **vì sao request bị từ chối** để vừa ngăn CSRF thật sự, vừa không làm gián đoạn người dùng hợp lệ vì lỗi tích hợp.

Ví dụ, một request từ site lạ không có token và một SPA không làm mới token sau login có thể cùng nhận **403 Forbidden**. Nếu chỉ nhìn số lượng 403 tăng rồi tắt CSRF, lỗi tích hợp có thể biến thành lỗ hổng. Ngược lại, nếu coi mọi 403 là tấn công, đội vận hành có thể bỏ qua lỗi cookie SameSite, preflight CORS, token raw/XOR hoặc mất session sau nâng cấp.

Bài này triển khai quy trình **phân loại → thu tín hiệu an toàn → so sánh baseline → phân tích browser/gateway/filter chain → xử lý sự cố hoặc rollback**. Nội dung áp dụng cho API/SPA, form login, Servlet, Reactive và nhiều instance sau proxy/CDN.

Sau bài học, người học có thể:

1. Phân biệt lỗi **thiếu/sai CSRF token**, authorization 403, authentication 401, CORS preflight, HTTP firewall và gateway rejection.
2. Phân tích token lifecycle qua session, login/logout, deferred token, raw token trong repository và XOR-masked representation.
3. Nhận diện lỗi tích hợp frontend/backend và mẫu lưu lượng bất thường mà **không gán động cơ tấn công từ một request đơn lẻ**.
4. Thiết kế structured events, dashboard và alert với **low-cardinality labels**, không lộ CSRF token, Cookie, JWT hay session ID.
5. Instrument và kiểm thử Servlet/Reactive, nắm giới hạn của 403-only observer và exception-class instrumentation.
6. Xây dựng kịch bản MockMvc, WebTestClient, browser/edge và canary probes để bảo đảm bảo vệ vẫn hiệu lực.
7. Dùng runbook điều tra, phân loại incident, phối hợp vận hành và rollback an toàn.

## 1. HTTP 403 không đồng nghĩa CSRF: phải xác định tầng đưa ra quyết định

CSRF lợi dụng khả năng trình duyệt tự đính kèm **ambient credentials**, thường là cookie phiên, vào request. Với phương thức thay đổi trạng thái, Spring Security yêu cầu một CSRF token mà trang hợp lệ lấy được và **chủ động gửi** qua header hoặc form field.

Một HTTP 403 có thể xuất phát từ nhiều lớp.

| Triệu chứng | Khả năng | Cần xác minh |
| --- | --- | --- |
| **403 do CSRF** | Expected token không có, actual token không khớp hoặc thiếu | CSRF exception category, token lifecycle, repository/handler |
| **403 do authorization** | User đã xác thực nhưng không đủ role/scope/ownership | AccessDeniedException ngoài CSRF, authorization audit |
| **401 Unauthorized** | Không đăng nhập, session/JWT không hợp lệ | AuthenticationEntryPoint, credential state |
| **302 redirect login** | Form-login flow thay vì JSON API response | Location, Accept, security chain |
| **CORS error** | OPTIONS bị 401/403, allow headers/origin sai | Browser Network, OPTIONS và CORS headers |
| **400/RequestRejected** | HTTP firewall, URL decoding/path normalization | Firewall/gateway logs đã scrub |
| **404/405** | Route/method không hợp đồng API | Controller mapping, gateway rewrite |
| **429/503** | Rate limit/WAF/overload | Gateway status, WAF decision |
| **419/440 custom** | Hệ thống riêng báo session/CSRF expiry | Không phải status mặc định Spring Security |

Spring Security **không mặc định dùng 419** cho CSRF expired. Nhiều cấu hình trả **403**. Không viết dashboard với giả định mọi 403 là CsrfFilter hoặc mọi 419 là CSRF.

### 1.1. MissingCsrfTokenException và InvalidCsrfTokenException

Ở Servlet Spring Security thường gặp hai loại:

- **MissingCsrfTokenException**: không có expected CSRF token phù hợp trong repository ở nhánh xử lý request. **Không suy ra chắc chắn** frontend không gửi token.
- **InvalidCsrfTokenException**: actual CSRF token không hợp lệ so với expected (bao gồm trường hợp actual vắng trong khi expected tồn tại).
- **CsrfException**: lớp lỗi CSRF chung, hữu ích để phân loại khác với authorization 403.

Do đó tên metrics nên trung tính: **missing_expected_token**, **invalid_or_missing_actual**. Một Boolean **csrf_header_present** (có/không) có thể bổ trợ, nhưng **không ghi giá trị header**.

Trên Reactive, CsrfWebFilter và cơ chế xử lý exception đi qua các WebFilters/ServerAccessDeniedHandler tùy version. Cần **WebTestClient xác minh đúng handler thực sự nhận lỗi** thay vì assume mọi 403 cùng một đường đi.

### 1.2. Một lỗi từ chối không chứng minh ai là kẻ tấn công

CSRF deny nghĩa là **request không qua được CSRF validation**, không chứng minh động cơ. Một request có CSRF token hợp lệ cũng không chứng minh đủ authorization, không có XSS hay gian lận nghiệp vụ.

Sự kiện vận hành có thể mang:

~~~text
decision=denied
security_control=csrf
reason=invalid_or_missing_actual
confidence=confirmed_by_csrf_handler
suspected_abuse=unknown
~~~

Chỉ nâng nghi vấn dựa trên **nhiều nguồn độc lập**: request pattern, tốc độ, WAF signals, origin context, session state, attempts trên nhiều routes và dữ liệu hành vi. Hạn chế phân loại “attack confirmed” chỉ từ một 403.

## 2. Đường đi request và các điểm quan sát

~~~mermaid
flowchart TD
    A["Browser / SPA"] --> B["CDN, WAF, gateway"]
    B --> C{"Preflight?"}
    C -->|Có| D["CORS processing"]
    C -->|Không| E["Spring Security chain"]
    D --> E
    E --> F{"Unsafe request thuộc CSRF matcher?"}
    F -->|Không| G["Authn, authz và application"]
    F -->|Có| H["Load expected + resolve actual token"]
    H --> I{"Token được chấp nhận?"}
    I -->|Không| J["CSRF denied + safe audit"]
    I -->|Có| G
    J --> K["Response 403"]
    G --> L["Response nghiệp vụ"]
~~~

Thứ tự thực tế tùy security chain, matcher, CORS configuration và framework version; sơ đồ mô tả **trách nhiệm logic**, không cam kết thứ tự filter tuyệt đối.

### 2.1. Bốn nơi phải đối chiếu

1. **Browser:** preflight, response status, cookie bị chặn, fetch credentials mode, token refresh, CSP connect-src, lỗi JS.
2. **Gateway/edge:** method/route template, WAF decision, redirect, path rewrite, CORS headers và release/region.
3. **Spring Security:** CSRF exception category nếu instrument đúng, authentication/authorization decision, security chain và session-present flag.
4. **Nghiệp vụ:** state có bị thay đổi trước khi từ chối không, tỷ lệ hoàn tất login/checkout và request idempotency.

Nếu browser báo CORS error, backend có thể **chưa nhận actual POST**. Nếu gateway phát 403, ứng dụng có thể **không có CsrfException**. Nếu app báo 403, nó không tự cho biết browser có lưu được cookie hay không.

### 2.2. Correlation ID độc lập với token

~~~text
timestamp=...
request_id=req-86b7
release=r52
method=POST
route=/api/orders
status=403
control=csrf
reason=invalid_or_missing_actual
~~~

Correlation ID phải được tạo/quản lý riêng, không dùng CSRF token, JSESSIONID hay JWT làm request ID, metrics label, tracing baggage hoặc log context. Nếu chấp nhận request ID từ client, validate chiều dài và ký tự để tránh log injection hoặc cardinality bùng nổ.

## 3. Lỗi tích hợp hay request bất thường: so pattern, không chỉ một status

### 3.1. Dấu hiệu nghiêng về regression tích hợp

- CSRF 403 tăng **ngay sau frontend/backend/gateway release**.
- Chủ yếu ở **một flow hợp lệ** như POST /api/profile sau login hoặc POST /logout.
- Tập trung ở một client version/browser, còn các phiên bản khác thành công.
- GET /api/csrf không trả token đúng, không materialize deferred token hoặc bị CDN cache.
- SPA tái sử dụng token cũ sau session rotation, login/logout, session timeout, đổi account.
- Header X-CSRF-TOKEN/X-XSRF-TOKEN bị interceptor bỏ qua hoặc gửi sai tên.
- CORS OPTIONS không cho custom header hoặc bị redirect login.
- Cookie session không được browser gửi do SameSite/Secure/Domain/Path/credentials.
- Raw token từ XSRF cookie và XOR-masked request handler không tương thích sau nâng Spring Security.
- Pod A thành công nhưng pod B trả 403 vì session store/config drift.
- Tab cũ giữ token hoặc request GET token đến trễ ghi đè token mới.

Đây là **giả thuyết**, không phải kết luận. Một tác nhân độc hại cũng có thể gây lưu lượng trùng thời điểm deploy; cần kiểm tra browser, code, revision và lịch sử trạng thái.

### 3.2. Dấu hiệu cần điều tra như lưu lượng bất thường

- Nhiều unsafe requests tới nhiều endpoints không có flow GET/bootstrap liên quan.
- Thử các route lỗi thời, admin paths, path encoding lạ hoặc nhiều methods không đúng contract.
- CSRF deny xuất hiện cùng 401/403 authorization, RequestRejectedException và WAF alerts.
- Tần suất request cao, lặp lại sau khi bị từ chối, automation fingerprints.
- Origin hoặc Referer không phải trusted browser app; **các header này có thể vắng hoặc giả mạo**, không dùng một mình để kết luận.
- Nhiều request không có session/cookie nhưng vẫn thử POST hàng loạt.
- Bất thường theo route group/region/client class, không giống pattern một frontend release.

**Không dùng IP, quốc gia hoặc User-Agent đơn lẻ làm thước đo hành vi**: NAT/proxy và client libraries gây false positives; attacker có thể thay chúng.

### 3.3. Ma trận phân loại để triage

| Quan sát | Giả thuyết ưu tiên | Kiểm tra tiếp |
| --- | --- | --- |
| 403 sau SPA release, một route | Frontend token bootstrap/interceptor | GET token, POST header presence, version |
| 403 sau login/logout | CSRF/session rotation | Test flow login → token mới → unsafe POST |
| 403 chỉ trên trình duyệt cụ thể | SameSite/third-party cookie | DevTools cookie blocked reason |
| 403 khác nhau giữa pods | Session/config drift | Revision, session storage và routing |
| OPTIONS 401, POST không thấy | CORS filter/preflight | OPTIONS không cookie, allow headers |
| CSRF đúng nhưng 403 | Authorization không đủ | Role/scope/object ownership |
| 403 rải nhiều routes và tốc độ lớn | Có thể probing/automation | Request classes, WAF, side effects |
| 403 sau idle dài | Session expiry, tab stale | TTL, refresh và multi-tab |
| Webhook máy-máy 403 CSRF | Sai security boundary | Xem signature/Bearer-only, cookie fallback |
| POST thiếu CSRF vẫn tạo dữ liệu | Bypass nghiêm trọng | Dừng rollout, kiểm chain/matcher và DB |

### 3.4. Đánh giá theo baseline và cohort

Một số chỉ số cần so sánh **trước/sau release**, giữa canary/control, theo route và client:

~~~text
before:
  csrf_denied_rate(/api/profile) = thấp
  valid_post_success_rate = ổn định

after:
  csrf_denied_rate(/api/profile) = tăng nhanh
  valid_post_success_rate = giảm
  frontend_release = r52
  other_routes = ít thay đổi
~~~

Tình huống minh họa này **nghiêng về integration regression**; chưa thể kết luận cho đến khi xác nhận nguyên nhân ở token/CSRF handler/cookie/browser. Nếu 403 tăng nhưng valid POST success không đổi và bị từ chối ở các route scanning, đó có thể là dấu hiệu phòng vệ đang hoạt động đúng.

## 4. Vòng đời token và các lỗi sau đăng nhập, đăng xuất

### 4.1. Session-backed và cookie-backed token

| Repository hoặc stack | Nơi expected token được duy trì | Nguồn mismatch cần điều tra |
| --- | --- | --- |
| **HttpSessionCsrfTokenRepository** (Servlet) | Server-side HttpSession | Session timeout, login session rotation, đổi pod không chia session |
| **CookieCsrfTokenRepository** (Servlet) | Cookie do browser giữ | XSRF cookie host/path/scope, frontend không đọc được, raw/header mismatch |
| **WebSessionServerCsrfTokenRepository** (WebFlux) | Reactive WebSession | WebSession expiry, distributed state, token Mono chưa materialize |
| **CookieServerCsrfTokenRepository** (WebFlux) | Reactive cookie | Cookie scope/HttpOnly/frontend contract |
| **Custom repository** | Tùy triển khai | Token signing, serialization, TTL, key rotation, multi-instance consistency |

CSRF token **không phải cookie đăng nhập độc lập**. Dù token lộ riêng lẻ không tự tạo được authenticated session, nó vẫn là thành phần bảo vệ cần không được đưa vào log, URL hoặc cache công khai.

### 4.2. Luồng token A → B → C quanh login/logout

~~~mermaid
sequenceDiagram
    autonumber
    participant SPA as SPA
    participant SEC as Spring Security
    participant REP as Session/CSRF repository
    SPA->>SEC: GET /api/csrf anonymous
    SEC->>REP: Materialize expected token A
    SEC-->>SPA: Token A + no-store
    SPA->>SEC: POST login, cookie, token A
    SEC->>REP: Authentication success, có thể clear token A
    SEC-->>SPA: Session/auth transition
    SPA->>SEC: GET /api/csrf authenticated
    SEC->>REP: Materialize token B
    SEC-->>SPA: Token B + no-store
    SPA->>SEC: POST /api/orders với token B
    SEC-->>SPA: Kết quả theo CSRF + authz
    SPA->>SEC: POST logout với token B
    SEC->>REP: Logout, có thể clear token B
    SPA->>SEC: GET /api/csrf anonymous nếu cần
    SEC-->>SPA: Token C
~~~

Trong Servlet, **CsrfAuthenticationStrategy** và **CsrfLogoutHandler** tham gia xóa token ở các luồng authentication/logout tiêu chuẩn. Do đó frontend phải lấy **token mới sau auth transition**; không xóa token trước khi gửi POST logout nếu logout cần token hiện tại.

Không đưa token A/B/C thật vào APM, log hoặc test report. Chỉ ghi **token_refresh_attempted**, **token_refresh_success**, stage anonymous/authenticated và **session_present** dạng Boolean khi cần.

### 4.3. Deferred token, XOR masking và sai hợp đồng SPA

Spring Security 6.x hỗ trợ **deferred CSRF token loading**: controller GET /api/csrf cần truy cập token để materialize theo repository. Trên Servlet, **XorCsrfTokenRequestAttributeHandler** có thể trình bày token dạng masked nhằm giảm một số tấn công nén response như BREACH.

Một SPA đọc **raw XSRF-TOKEN cookie** thường cần request handler xử lý raw header, trong khi HTML form hoặc JSON bootstrap có thể được cấp representation masked. Không thể chỉ xem hai chuỗi khác nhau rồi kết luận token bị giả mạo.

Dấu hiệu đặc trưng:

- GET token 200, cookie và header đều có, nhưng POST **invalid** đồng loạt sau upgrade Spring Security.
- Form SSR POST thành công còn SPA POST thất bại, hoặc ngược lại.
- Một request handler kỳ vọng raw header nhưng frontend gửi token masked JSON.
- Deferred token chưa được truy cập nên cookie XSRF mong đợi chưa xuất hiện.
- Frontend gửi tên header khác repository/request handler contract.

**Kiểm tra cấu hình** CsrfTokenRepository/ServerCsrfTokenRepository, CsrfTokenRequestHandler tương ứng, headerName, lifecycle và integration tests cùng cookie session. Không cần in expected/actual token để debug.

### 4.4. Multi-tab và race condition

Một số vấn đề không tái lập qua một request đơn:

- Tab A logout, tab B vẫn dùng token B đã cũ trong memory.
- GET token A phát trước login nhưng response đến muộn, ghi đè token B.
- Một request POST khởi động trong lúc session được rotate.
- Một SPA tự retry POST nguy hiểm sau 403 hoặc timeout; request trước có thể đã tạo side effect.
- Hai môi trường frontend release khác nhau chia session cookie nhưng có cách gửi token khác nhau.

Giải pháp: quản lý **epoch/generation** theo auth transition, lấy token mới khi login/logout xác nhận, đồng bộ trạng thái tabs khi cần, không tự retry mutation không idempotent. Metrics nên ghi **client release, auth stage và refresh outcome**, không có token text.

## 5. Cookie, CORS, CSP, gateway: lỗi tích hợp trông giống CSRF

### 5.1. Browser cookie + CSRF request hợp lệ

Một SPA ở app.example.com gọi API ở api.example.com theo session cookie:

~~~http
GET /api/csrf HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: JSESSIONID=<synthetic-session>
~~~

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Cache-Control: no-store
Content-Type: application/json

{"headerName":"X-CSRF-TOKEN","token":"<synthetic-token>"}
~~~

SPA nhận token (JSON hoặc XSRF cookie theo kiến trúc) rồi chủ động gửi CSRF header trong **unsafe request với cùng session**. Các giá trị là ký hiệu, không phải credential thực.

### 5.2. Browser CORS preflight không mang cookie như POST

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Nếu OPTIONS bị 401/403, redirect login, hoặc Allow-Headers thiếu CSRF header, browser có thể **không phát POST thực**. Khi đó lỗi frontend “không POST được vì CSRF” thực ra xuất phát từ **CORS**.

CORS phải xử lý preflight **trước authentication** theo Spring Security integration. Dùng **exact trusted origin** với credentialed browser, không mở wildcard Allow-Origin cùng Allow-Credentials true. Preflight thành công cũng **không chứng minh CSRF đang bật** trên POST — cần negative test riêng.

### 5.3. Session cookie không đến được server

| Cấu hình/trạng thái | Tác động có thể thấy |
| --- | --- |
| **Secure** | Cookie HTTPS có thể không đến một endpoint HTTP sai scheme |
| **HttpOnly** | Đúng cho session cookie; JS không cần và không được đọc JSESSIONID |
| **SameSite** | Cross-site vs same-site quyết định một số bối cảnh browser tự gửi cookie |
| **Domain/Path** | Cookie host-only API không đọc được ở SPA hostname khác |
| **Fetch credentials include** | Thiếu có thể làm request cross-origin không gửi cookie |
| **Third-party cookie policy** | Browser có thể chặn dù Set-Cookie xuất hiện trong response |
| **Expiry/rotation** | Session hết hạn/đổi ID, frontend giữ token cũ |
| **Multiple pods** | Session không được chia sẻ, cookie signing/session config khác revision |

**Khác origin không đồng nghĩa khác site.** CORS và SameSite giải quyết hai vấn đề khác nhau. Một response có Set-Cookie không chứng minh browser thật sự lưu/gửi cookie; dùng DevTools **Network/Storage và blocked reason**.

### 5.4. Header, proxy và CDN có thể thay failure mode

| Thành phần | Lỗi hay gặp | Triệu chứng |
| --- | --- | --- |
| **CSP connect-src** | Chặn GET CSRF bootstrap | SPA không nhận token; console báo CSP, không phải CSRF 403 |
| **HSTS/TLS redirect** | Sai HTTPS host/scheme sau reverse proxy | Secure cookie bị mất, login loop |
| **HTTP firewall** | Reject URL chứa encoding bất thường | 400/403 trước controller |
| **WAF/gateway** | Chặn unsafe route hoặc OPTIONS | 403 từ edge, Spring không nhận request |
| **CDN caching** | Cache GET /api/csrf theo URL, không theo phiên | Token mismatch/rò response nhạy cảm |
| **SecurityFilterChain matcher** | Route trúng chain Bearer-only thay vì cookie chain | CSRF thiếu hoặc yêu cầu sai nơi |
| **Authorization** | Role/scope không đủ | 403 dù CSRF token đúng |
| **Session store** | Node A/B có state khác | Lỗi chỉ xuất hiện khi chuyển pod |

Với TLS termination cần kiểm tra **trusted forwarded headers**, Set-Cookie Secure/Domain/Path và HSTS trên public HTTPS edge; **không tin X-Forwarded-Proto/Host do client ngoài internet tự gửi**.

Nếu frontend HTML được serve từ CDN, CSP của document cần ở **HTML origin**. CSP response JSON API không tự bảo vệ HTML đó; ngược lại một CSP sai connect-src trên HTML có thể làm GET token thất bại trước khi chạm CSRF filter.

## 6. Structured audit không tiết lộ token hoặc credential

### 6.1. Event schema tối thiểu

Một sự kiện có thể chứa:

~~~json
{
  "event": "http.security.denied",
  "control": "csrf",
  "reason": "invalid_or_missing_actual",
  "httpMethod": "POST",
  "route": "/api/orders",
  "status": 403,
  "requestId": "req-8a3c",
  "environment": "prod",
  "release": "r52",
  "chain": "browser-cookie",
  "authPresent": true,
  "sessionPresent": true,
  "csrfHeaderPresent": false,
  "clientClass": "spa",
  "outcome": "denied"
}
~~~

Đây là **schema đề xuất**, không phải event mặc định của Spring Security. Những field như **authPresent/sessionPresent/headerPresent** chỉ mang Boolean; chúng không phải bằng chứng tuyệt đối về browser identity hoặc nguyên nhân. Tránh cố ghi đầy đủ thông tin user để phân loại lỗi.

### 6.2. Những dữ liệu không được lưu

| Dữ liệu | Lý do tránh ghi |
| --- | --- |
| Actual/expected raw hoặc XOR CSRF token | Giá trị bảo vệ request theo phiên, có thể bị lạm dụng trong ngữ cảnh phù hợp |
| JSESSIONID, Cookie header | Session credential |
| Authorization Bearer/JWT/refresh token | Credential có thể bị sử dụng trực tiếp |
| Request/response body | Có thể chứa mật khẩu, CSRF, PII, dữ liệu nghiệp vụ |
| Full URL query/fragment | Có thể chứa token, email, dữ liệu nhạy cảm |
| Raw Origin/Referer bất kỳ | Có thể lộ URL hoặc tạo cardinality lớn |
| Raw exception message/stack dump chứa request | Có thể lộ dữ liệu chưa scrub |
| CSP report raw script sample | Có thể chứa code hoặc dữ liệu cá nhân |
| CSRF token hash công khai | Không mặc định an toàn: có thể tạo tracking identifier hoặc kiểm tra token đoán được |

Không log “token prefix” hoặc “last four characters” chỉ để hỗ trợ debug. **Biết header có mặt, loại repository, stage và request correlation thường đã đủ** cho các câu hỏi tích hợp.

### 6.3. Logging allowlist thay vì redaction muộn

~~~text
timestamp=...
requestId=req-8a3c
method=POST
routeTemplate=/api/orders
status=403
securityControl=csrf
reason=invalid_or_missing_actual
release=r52
~~~

Không ghi:

~~~text
cookie=JSESSIONID=...
csrfExpected=...
csrfProvided=...
headers={Authorization: Bearer ..., X-CSRF-TOKEN: ...}
requestBody={"_csrf":"..."}
url=/orders?csrf=...
~~~

**Ưu tiên allowlist** fields được phép gửi sang logging/APM hơn là dump mọi thứ rồi filter vài tên field. Redaction phải đặt **trước khi dữ liệu truyền sang bên thứ ba**; Cache-Control no-store không ngăn APM đọc request/response body.

### 6.4. Tránh đo sai do logger/handler vị trí không phù hợp

Một filter chỉ nhìn **response status == 403** có thể đếm **CSRF, authorization và gateway errors** chung vào một nhóm. Muốn biết đúng **MissingCsrfTokenException/InvalidCsrfTokenException**, cần instrument tại **chính đường CsrfFilter/CsrfWebFilter từ chối**, hoặc handler đã được xác minh thực sự nhận exception đó.

Một AccessDeniedHandler dành cho authorization có thể **không** tự động nhìn thấy mọi CSRF exception nếu CSRF filter có handler nội bộ hoặc filter order khác. Trên Reactive, Mono error path có thể được một WebFilter khác chuyển thành response; phải test từng trường hợp.

**Quy tắc đo lường:** Ghi 403 tổng trong một counter, ghi **csrf_denied_confirmed** chỉ khi có bằng chứng filter/exception đủ tin cậy. Không cộng hai lần cùng một event vào tổng.

## 7. Metrics và dashboard: đo tín hiệu, không đo token

### 7.1. Các metrics tự định nghĩa

~~~text
http_security_denials_total{
  environment="prod",
  route_group="orders",
  control="csrf",
  reason="invalid_or_missing_actual",
  release="r52"
}

http_security_denials_total{
  environment="prod",
  route_group="admin",
  control="authorization",
  reason="insufficient_role",
  release="r52"
}

csrf_bootstrap_requests_total{
  environment="prod",
  outcome="success",
  auth_stage="authenticated",
  client_class="spa"
}

csrf_browser_flow_outcome_total{
  environment="prod",
  flow="login_to_post",
  outcome="success",
  release="r52"
}
~~~

Tên metrics chỉ là **gợi ý để tự instrument/ghi từ observability**, không phải mặc định của Spring Security/Micrometer. Cần map phù hợp phiên bản thực, tránh phát metric per token.

### 7.2. Low-cardinality dimensions nên có

- Environment, workload/region group và release revision hữu hạn.
- HTTP method và **route template/group**, không raw path có user ID.
- Decision: success/denied/error.
- Control: csrf/authentication/authorization/cors/firewall/gateway.
- Reason category ổn định: missing_expected, invalid_actual, authz_denied, cors_preflight_failed.
- Client class: SPA/mobile SSR/test (do chính ứng dụng phân loại, không tin một chuỗi tự khai từ client).
- Auth stage: anonymous/authenticated/unknown, không chứa user identity.
- Browser family ở mức hữu hạn nếu có telemetry đã được chuẩn hóa.

**Không dùng** IP thô, UUID phiên, request ID, user ID, JWT, Origin bất kỳ hoặc token làm metric label vì cardinality và dữ liệu nhạy cảm. Request ID có thể nằm trong audit logs có kiểm soát để điều tra, không phải Prometheus dimension.

### 7.3. Dashboard theo hành trình nghiệp vụ

Một dashboard thực dụng nên cho thấy:

1. **Tổng request unsafe và tỷ lệ bị CSRF từ chối** theo route/release; nhớ mẫu số chỉ tính request phù hợp.
2. **MISSING_EXPECTED vs INVALID_ACTUAL** theo thời gian; không đoán nguyên nhân header từ tên exception.
3. Tỷ lệ **GET /api/csrf thành công** và lỗi sau login/logout.
4. **OPTIONS preflight** thành công ở trusted origins; phân biệt lỗi do browser không gửi POST.
5. **Session expiry/login success** và tỷ lệ flow login → first unsafe POST.
6. **Authorization 403** tách riêng, tránh một biểu đồ 403 trộn mọi tầng.
7. **WAF/HTTP firewall decisions**, request rejected theo route group và vùng.
8. **Canary vs control**: valid POST success, frontend errors, CSRF denied.
9. **Pod/config revisions**: drift của CSRF repository/handler/session store.
10. **Security negative probes**: POST thiếu token vẫn bị từ chối và không side effect.

### 7.4. Tỷ lệ phải có mẫu số và định nghĩa

Không đánh giá từ số tuyệt đối 403. Ví dụ:

\[
\text{CSRF deny rate} =
\frac{\text{Unsafe requests bị CSRF filter từ chối}}
{\text{Unsafe requests vào CSRF-protected routes}}
\]

Nếu ở lớp edge chỉ đếm toàn bộ requests mà không phân biệt protected routes, mẫu số có thể sai. Một canary nhận rất ít request sẽ có tỷ lệ dao động mạnh; cần confidence/traffic minimum và độ trễ dữ liệu phù hợp.

Với SPA, nên quan sát thêm:

\[
\text{First POST success after login} =
\frac{\text{Login sessions có first unsafe POST thành công}}
{\text{Login sessions thực sự thực hiện first unsafe POST}}
\]

Đây là **định nghĩa product telemetry theo phiên đã ẩn danh/aggregate**, không yêu cầu log session IDs trong metrics. Dùng event correlation an toàn theo chính sách dữ liệu nội bộ, tránh biến nó thành khả năng theo dõi danh tính không cần thiết.

### 7.5. Không mặc định 403 tăng nghĩa là phải giảm bảo vệ

Một đợt bot scanning có thể làm 403/WAF rejections tăng trong khi legitimate flow success ổn định. Một regression có thể làm 403 tăng ít nhưng phá một bước thanh toán có doanh thu lớn. **Alert nên kết hợp baseline, traffic quality, route criticality, release timing và hành vi user hợp lệ**.

## 8. Servlet: quan sát status 403 và phân loại đúng tại CSRF denial handler

Các ví dụ dùng **Spring Boot 3.x, Spring Security 6.x và Java 17+**. Trên Boot 3, Servlet APIs nằm trong **jakarta.servlet**. Mục tiêu là minh họa hai tầng đo **khác nhau**: 403 tổng hợp và CSRF exception đã xác nhận.

### 8.1. Observer cho mọi status 403 — không gắn nhãn CSRF

~~~java
import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

final class ForbiddenStatusObserver extends OncePerRequestFilter {

    private static final Logger LOG =
        LoggerFactory.getLogger(ForbiddenStatusObserver.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        chain.doFilter(request, response);

        if (response.getStatus() == 403) {
            // Không log requestURI, query, headers hay body.
            LOG.info("http_denied status=403 method={}",
                request.getMethod());
        }
    }
}
~~~

Observer này có thể được đặt **trước CsrfFilter** để bao một phần security chain:

~~~java
import org.springframework.security.config.Customizer;
import org.springframework.security.web.csrf.CsrfFilter;

// Đoạn nằm trong cấu hình HttpSecurity của browser chain.
http
    .csrf(Customizer.withDefaults())
    .addFilterBefore(
        new ForbiddenStatusObserver(), CsrfFilter.class);
~~~

**Điều phải hiểu:** 403 từ observer là **403 tổng hợp**, bao gồm authorization hoặc xử lý khác ở phía dưới chain. Không đặt tên metric là csrf_invalid chỉ vì status 403. Ngoài ra, response do gateway/WAF phát **trước Spring app** không vào observer. Với một số đường error dispatch/filter order, observer có thể không nhìn được status cuối; kiểm tra bằng integration tests.

Trong production nên dùng instrumentation chuẩn của hệ thống HTTP/observability nếu có, thay vì tự tạo filter cho mọi request mà không đánh giá hiệu năng, double count và async dispatch.

### 8.2. Phân loại CsrfException tại chính CSRF denial path

Để có độ tin cậy cao hơn, một **AccessDeniedHandler dùng bởi CsrfFilter thực tế** có thể phân biệt Missing/Invalid. Đây là ví dụ handler **độc lập**, chưa phải cấu hình tự động gắn cho mọi filter.

~~~java
import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.access.AccessDeniedHandlerImpl;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.security.web.csrf.InvalidCsrfTokenException;
import org.springframework.security.web.csrf.MissingCsrfTokenException;

final class SafeCsrfDeniedHandler implements AccessDeniedHandler {

    private static final Logger LOG =
        LoggerFactory.getLogger(SafeCsrfDeniedHandler.class);

    private final AccessDeniedHandler delegate =
        new AccessDeniedHandlerImpl();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException denied)
            throws IOException, ServletException {

        if (denied instanceof CsrfException) {
            String reason = "other_csrf";
            if (denied instanceof MissingCsrfTokenException) {
                reason = "missing_expected";
            } else if (denied instanceof InvalidCsrfTokenException) {
                reason = "invalid_or_missing_actual";
            }

            boolean headerPresent =
                request.getHeader("X-CSRF-TOKEN") != null
                || request.getHeader("X-XSRF-TOKEN") != null;

            LOG.warn(
                "control=csrf decision=denied reason={} method={} " +
                "sessionPresent={} csrfHeaderPresent={}",
                reason,
                request.getMethod(),
                request.getSession(false) != null,
                headerPresent);
        }

        // Dùng xử lý 403 tương thích thay vì phản hồi chứa token.
        delegate.handle(request, response, denied);
    }
}
~~~

**Không tự động giả định ExceptionTranslationFilter.accessDeniedHandler đã xử lý mọi CsrfException.** CsrfFilter có thể sử dụng AccessDeniedHandler của chính nó; nếu tự tạo một CsrfFilter, API **CsrfFilter#setAccessDeniedHandler** cho phép gắn handler, nhưng phải tránh tạo **hai CsrfFilter** khi DSL CSRF mặc định đã bật. Cách tích hợp với HttpSecurity/DSL phiên bản thực cần được kiểm tra và ghi thành test: **missing expected và invalid actual thực sự gọi SafeCsrfDeniedHandler**, chứ không chỉ bean tồn tại.

**Không thay thế cấu hình bảo mật production chỉ để đo số liệu**. Nếu framework/phiên bản chưa cung cấp extension point phù hợp, giữ status-only metrics trung tính và bổ sung testing/observations có kiểm soát; đừng đọc/ghi expected token từ repository trong filter tùy tiện.

### 8.3. Vì sao không log raw URL ngay cả trong CSRF deny?

Tránh:

~~~java
// ANTI-PATTERN: query và path có thể mang dữ liệu nhạy cảm.
logger.warn("CSRF rejected request url={}",
    request.getRequestURL());

// ANTI-PATTERN: có thể chứa JSESSIONID/JWT/CSRF header.
logger.warn("Headers={}", allRequestHeaders);

// ANTI-PATTERN: không cần token để phân loại lỗi.
logger.warn("Actual={} Expected={}", actualToken, expectedToken);
~~~

Một CSRF exception có thể xuất hiện **trước MVC handler mapping**, khi đó route template có thể chưa được xác định. Nếu muốn gắn route group, dùng **allowlist nhóm path tĩnh** trong telemetry (ví dụ orders, profile, login, other), không tự ghi raw servletPath/query ra logs. Nhóm này **chỉ dành cho metrics**, không thay authorization/securityMatcher.

### 8.4. Trả error response đúng hợp đồng mà không tiết lộ chi tiết

Ví dụ một JSON response dùng cho browser API:

~~~json
{
  "error": "REQUEST_FORBIDDEN",
  "requestId": "req-86b7"
}
~~~

Client có thể nhận thông tin tổng quát “request forbidden”, trong khi audit nội bộ (được bảo vệ quyền) chứa category đã scrub. Không trả **expected CSRF token, raw token hoặc session ID** trong response 403. Client không nên tự retry mọi POST/PATCH khi gặp 403; cần phân loại trước và dùng idempotency guarantees.

### 8.5. Những nơi có thể bỏ sót sự kiện

- Gateway/WAF trả 403 trước Spring.
- CORS preflight OPTIONS không đi tới unsafe POST.
- Authorization 403 đi qua handler khác CSRF.
- Exception bị servlet container/error dispatch xử lý ở đường riêng.
- Một SecurityFilterChain khác nhận route.
- Async/error dispatch dẫn đến duplicate events nếu filter không kiểm soát.
- Một số endpoint bị bỏ CSRF có chủ đích (webhook machine-to-machine, report collector) nên không phát CSRF denial dù nhận POST thiếu token.

Do đó cần so **HTTP 403 tổng**, **confirmed CSRF denied**, **authorization denied** và **edge denied** như bốn nhóm có nguồn độc lập. Không cộng bừa chúng thành một “attack counter”.

## 9. Reactive/WebFlux: phân tách HTTP outcome và CsrfWebFilter exception

Trên WebFlux sử dụng **ServerHttpSecurity, SecurityWebFilterChain, CsrfWebFilter, ServerWebExchange và WebSession**. Không copy HttpServletRequest, servlet filter hoặc StrictHttpFirewall vào Reactive app.

### 9.1. WebFilter đếm status 403 tổng hợp

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
final class ReactiveForbiddenObserver implements WebFilter {

    private static final Logger LOG =
        LoggerFactory.getLogger(ReactiveForbiddenObserver.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return chain.filter(exchange).doFinally(signal -> {
            HttpStatusCode code =
                exchange.getResponse().getStatusCode();

            if (code != null && code.value() == 403) {
                LOG.info(
                    "reactive_http_denied status=403 method={}",
                    exchange.getRequest().getMethod());
            }
        });
    }
}
~~~

**Chức năng chỉ là thống kê 403**, không phân biệt CSRF/authorization. Một số exception có thể được xử lý ngoài WebFilter chain hoặc status được đặt sau callback, nên cần test end-to-end theo ứng dụng; không mặc định observer thấy 100% request/edge responses. Tránh cả **doOnError** dump Throwable và request body khi điều tra.

Nếu dùng Micrometer/Observations đã có sẵn để đếm HTTP statuses, không nên tạo thêm counter trùng. Dùng webfilter ở đây để minh họa **vị trí** và giới hạn của telemetry, không phải khuyến nghị luôn instrument bằng filter thủ công.

### 9.2. Phân loại AccessDeniedException tại đường Reactive được xác minh

Một **ServerAccessDeniedHandler** là một extension point cho một số đường 403 của WebFlux:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class ReactiveDeniedAuditHandler
        implements ServerAccessDeniedHandler {

    private static final Logger LOG =
        LoggerFactory.getLogger(ReactiveDeniedAuditHandler.class);

    private final ServerAccessDeniedHandler delegate =
        new HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN);

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange,
            AccessDeniedException denied) {

        if (denied instanceof CsrfException) {
            LOG.warn("control=csrf decision=denied method={}",
                exchange.getRequest().getMethod());
        }
        return delegate.handle(exchange, denied);
    }
}
~~~

Ví dụ ở trên **không tự gắn handler vào CsrfWebFilter**. Nếu cấu hình exceptionHandling trong ServerHttpSecurity để dùng handler, vẫn phải test liệu CsrfWebFilter từ chối đi qua handler đó ở **version đang triển khai**. Không được tuyên bố quan sát chính xác CSRF chỉ vì một ServerAccessDeniedHandler bean đã tạo thành công.

Một giải pháp đặc thù version có thể phải instrument ở **security WebFilter exception path** hoặc dùng audit/observation framework phù hợp. Tránh cài custom WebFilter tự so sánh token vì có nguy cơ làm thay đổi CSRF logic và raw/XOR semantics.

### 9.3. Deferred Mono<CsrfToken> và WebSession

Một WebFlux GET bootstrap thường truy cập attribute kiểu **Mono<CsrfToken>** từ ServerWebExchange và **materialize token trong response pipeline**:

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
class ReactiveCsrfBootstrapController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> bootstrap(
            ServerWebExchange exchange) {

        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "CSRF WebFilter is not configured"));
        }

        return tokenMono.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken())));
    }
}
~~~

**Không gọi block()** trên reactive request thread để lấy token. GET bootstrap trả token theo WebSession, nhưng **response body chứa token không được log** hoặc chia sẻ qua cache.

### 9.4. Reactivity, sampling và thứ tự events

Một chuỗi Reactor có thể hoàn tất khác request/response blocking. Hãy xác minh:

- Response status được đo đúng sau security filter handling.
- Request bị cancel/timeout không bị đếm là completed 403 giả.
- Một lỗi không bị double-count giữa WebFilter, global exception handler và HTTP server observations.
- Metrics không kích hoạt blocking operations trong event loop.
- CORS preflight và error responses từ gateway được tính ở nguồn phù hợp.
- Trace correlation dùng request ID an toàn, không dựa vào thread-local request object một cách mặc định.

## 10. Ranh giới cookie-authenticated browser và Bearer-only API

### 10.1. Khi nào route thực sự có rủi ro CSRF?

**Bearer token chỉ được JavaScript chủ động gắn trong Authorization header**, không dựa vào cookie browser auto-send, thường có threat model khác một API dùng cookie phiên. Tuy nhiên:

- Nếu backend cho phép **JSESSIONID hoặc refresh cookie** xác thực một unsafe route, cần đánh giá CSRF.
- JWT được lưu trong **cookie** vẫn có tính ambient credential; “JWT” không tự có nghĩa stateless hoặc miễn CSRF.
- Một API nhận **cả Bearer header và session cookie** có thể bị CSRF ở fallback cookie branch nếu không phân ranh rõ.
- Webhook machine-to-machine dùng HMAC/signature hoặc Bearer-only có thể có ngoại lệ CSRF hẹp; authentication/authorization riêng vẫn bắt buộc.
- Endpoint báo cáo CSP hoặc machine-to-machine cần exempt **đúng path/method** nếu không gửi CSRF; không loại bỏ CsrfFilter trên toàn application.

### 10.2. Nhiều SecurityFilterChain có thể khiến mọi phép đo sai

Ví dụ kiến trúc:

~~~text
/api/browser/**  -> session cookie + CsrfFilter + CORS
/api/mobile/**   -> OAuth2 Resource Server, Bearer-only
/webhooks/**     -> signature verification, no ambient cookie auth
/actuator/**     -> private management network/auth
~~~

Những route này cần **securityMatcher và ordering** có test. Một POST mobile trả 403 không tự động là “lỗi CSRF”; một POST browser **không bị CSRF chặn** có thể là lỗ hổng nghiêm trọng nếu match nhầm mobile chain.

Trên Servlet và WebFlux, bộ lọc/chain khác nhau nhưng cùng yêu cầu kiểm tra:

1. Cookie browser auth chỉ được dùng ở chain được bảo vệ CSRF.
2. Bearer-only route không có implicit cookie fallback.
3. Đúng CORS origin/headers cho browser flow.
4. Authorization dựa trên role/scope/ownership sau khi CSRF pass.
5. Error response có status và audit category đúng.
6. GET bootstrap token và POST được bảo vệ dùng repository/request handler tương thích.
7. Không có đường bypass do proxy rewrite hoặc HTTP firewall relaxation.

### 10.3. Không tự động refresh rồi retry mọi 403

Một SPA có thể retry GET token khi một request bị 403 do CSRF **đã xác minh**, nhưng **POST/PUT/PATCH/DELETE không idempotent** không nên được phát lại tự động mà không biết side effects. Một 403 còn có thể là thiếu quyền; refresh token không giải quyết authorization.

Tốt hơn là trả error code ổn định, phân loại nội bộ, hiển thị lỗi cho người dùng và chỉ retry khi **có giao thức idempotency hoặc thao tác đã được chứng minh an toàn**. Không đưa expected CSRF token mới vào response lỗi hoặc log để “giúp frontend tự sửa”.

## 11. Kiểm thử Servlet/MockMvc: từ 403 đến nguyên nhân có thể tái lập

Ví dụ dùng Spring Boot 3, Spring Security 6.x và **spring-security-test**, giả định ứng dụng có route **POST /api/orders** dùng session cookie/CSRF và user Alice có quyền tạo đơn hàng. Các đoạn code chỉ kiểm chứng điều kiện được nêu; controller, repository và business validation thật phải được cấu hình trong project.

### 11.1. Unsafe POST không có token phải bị từ chối

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
class ServletCsrfMonitoringRegressionTests {

    @Autowired MockMvc mvc;

    @Test
    void postWithoutCsrfMustBeForbidden() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfStillNeedsUserPermission() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

**Đặt assertion database trong trường hợp bị 403** để chứng minh đơn hàng không được tạo. Nếu mock Alice không có quyền hoặc payload sai thì request có CSRF đúng vẫn có thể trả 403/400; cần test authorization/business validation riêng. Hai helper user() và csrf() **không tái hiện login/session rotation thật**.

Mục tiêu monitoring của test: observer 403 tổng có sự kiện, còn **confirmed CSRF counter** phải có sự kiện chỉ khi handler thực tế được gắn đúng. Nếu chỉ thêm một bean SafeCsrfDeniedHandler nhưng chưa wire vào CsrfFilter, request 403 vẫn xảy ra mà event CSRF riêng có thể không xuất hiện.

### 11.2. Endpoint bootstrap token trên Servlet

Một endpoint GET dành cho SPA dùng session-backed repository có thể trả token JSON và không cache:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletCsrfBootstrapController {

    record CsrfPayload(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<CsrfPayload> bootstrap(
            HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException(
                "CSRF filter is not configured");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfPayload(
                token.getHeaderName(), token.getToken()));
    }
}
~~~

Đọc **getToken()** materialize deferred token. Tùy repository/request handler, token trình bày qua attribute có thể masked. Không log body JSON hoặc cache nó chung giữa sessions.

### 11.3. Dùng session thực từ GET bootstrap cho POST

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

// Đoạn thân test trong class có MockMvc mvc.
@Test
void realBootstrapTokenWorksWithSameSession() throws Exception {
    MvcResult boot = mvc.perform(get("/api/csrf"))
        .andExpect(status().isOk())
        .andReturn();

    String json = boot.getResponse().getContentAsString();
    String headerName = JsonPath.read(json, "$.headerName");
    String token = JsonPath.read(json, "$.token");
    MockHttpSession session =
        (MockHttpSession) boot.getRequest().getSession(false);

    if (session == null) {
        throw new AssertionError("Expected CSRF session");
    }

    mvc.perform(post("/api/orders")
            .session(session)
            .with(user("alice"))
            .header(headerName, token)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"sku\":\"P100\",\"quantity\":1}"))
        .andExpect(status().is2xxSuccessful());
}
~~~

Giả định **HttpSessionCsrfTokenRepository** và đúng Servlet request handler. Nếu CookieCsrfTokenRepository được dùng, cần tái hiện đúng cookie jar và raw/XOR header contract. **Không bật MockMvc print()** cho response chứa token trong CI logs.

Bài test này chứng minh token GET/POST cùng session hoạt động, **không kiểm chứng login thật** chỉ bởi user("alice"). Cần full integration test login → token mới → POST, logout → token mới và multi-tab nếu ứng dụng dùng những flows đó.

### 11.4. CORS preflight phải được test độc lập

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Test thuộc class có mvc, app có exact origin CORS source.
mvc.perform(options("/api/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers",
            "content-type,x-csrf-token"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://app.example.com"));
~~~

Preflight test **không gửi session cookie**. Nếu OPTIONS fail, browser có thể không gửi POST; không đếm OPTIONS 403 đó thành lỗi missing CSRF ở POST. Test Origin ngoài allowlist phải không được cấp quyền đọc credentialed response.

### 11.5. Kiểm thử event phân loại, không chỉ HTTP response

Cần bổ sung assertions trên metrics/audit trong project thực:

| Tình huống | HTTP mong đợi | Audit category được kiểm chứng |
| --- | --- | --- |
| POST cookie-auth không actual token, expected đã tồn tại | 403 | CSRF invalid/missing actual |
| POST expected token không còn sau session timeout | 403 hoặc auth flow khác theo contract | CSRF missing expected hoặc authentication/session outcome |
| POST token đúng nhưng role không đủ | 403 | authorization denied, **không** tăng confirmed CSRF counter |
| POST token đúng và đủ quyền | 2xx | success, không tăng deny count |
| OPTIONS trusted Origin | 2xx | CORS preflight, không tính unsafe CSRF deny |
| Request bị WAF trước app | 403 edge | WAF deny, Spring CSRF event không có |
| Route Bearer-only thực | Theo auth contract | Không tạo false-positive CSRF deny |

Không cứng hóa expected exception cho **mọi trường hợp** nếu framework/repository quyết định nhánh khác; hãy verify bằng test gắn với version đang pin và điều chỉnh category mapping theo kết quả đã hiểu. Điều bất biến là **không tạo side effect khi security denied**.

## 12. WebTestClient: kiểm thử CSRF, WebSession và status trên Reactive

### 12.1. CsrfWebFilter từ chối unsafe request không token

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn test trong WebFlux context có WebTestClient và POST route thật.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Cần import java.util.Map trong test hoàn chỉnh. Helpers mockUser()/csrf() là **test-only**, không kiểm tra WebSession cookie thật hoặc JavaScript bootstrap. Khi xác nhận metrics, observer chỉ nhìn status 403 phải được đặt tên tổng quát, còn CsrfException confirmed phải đến từ handler path được WebTestClient thực sự thực thi.

### 12.2. Reactive GET token cùng WebSession

Ví dụ Reactive controller materialize Mono<CsrfToken>:

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
class ReactiveCsrfBootstrapController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> bootstrap(
            ServerWebExchange exchange) {
        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "CSRF WebFilter not configured"));
        }
        return tokenMono.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken())));
    }
}
~~~

Không gọi block() trong Reactive controller. Sử dụng **test client duy trì cookie/WebSession qua GET và POST** để xác minh một cách end-to-end, bao gồm token sau login/logout và cookie-based repository nếu dùng.

### 12.3. Kiểm tra no-store và preflight trên WebFlux

~~~java
import org.springframework.http.HttpHeaders;

// Đoạn thân test trong WebFlux test context có CORS exact origins.
webTestClient.get().uri("/api/csrf")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches(
        HttpHeaders.CACHE_CONTROL, ".*no-store.*");

webTestClient.options().uri("/api/orders")
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

CORS source Reactive phải được cấu hình cho đúng origin/path/method/headers. Mock WebTestClient không tự chứng minh browser SameSite policy hoặc CDN headers thật; cần thêm browser/edge tests.

### 12.4. Không tự biến 403 thành CSRF khi filter không gửi exception tới handler

Dùng hai test riêng:

1. WebTestClient unsafe request thiếu/sai CSRF, ghi nhận **expected confirmed CSRF event** nếu handler có đường nối.
2. WebTestClient với token đúng nhưng user không có quyền, ghi nhận **authorization denied event**, không tăng CSRF confirmed.

Nếu hai test đều tạo cùng category “csrf”, instrumentation đang **gán nhãn sai**. Nếu cả hai chỉ tăng HTTP 403 tổng, đó là đo **chưa đủ chi tiết**, không phải thất bại CSRF protection; không sửa bằng cách log token.

## 13. Browser và edge integration tests: xác định request có thật sự tới filter

### 13.1. Ma trận request cần có trước production

| Kịch bản | Dấu hiệu quan sát | Phải chứng minh |
| --- | --- | --- |
| Anonymous GET /api/csrf | Response JSON, cookie nếu repository cần | Token bootstrap, no-store |
| GET token sau login | Session/cookie transition | Token hiện hành sử dụng được |
| Unsafe POST thiếu header | Browser request thực | 403, không side effect |
| Unsafe POST token sai | Invalid CSRF | 403, category đúng |
| Unsafe POST token đúng, role thiếu | Authorization denied | 403 ngoài CSRF |
| Unsafe POST token đúng, đủ quyền | Thành công | Không phát CSRF deny |
| OPTIONS trusted Origin | Không Cookie, đúng method/headers | Preflight không bị auth chặn |
| OPTIONS untrusted Origin | CORS policy | Không cấp credentialed browser access |
| Cookie blocked trong browser | DevTools Storage/Network | Lý do SameSite/Secure/third-party |
| Session timeout | Auth state + token stale | Luồng refresh/relogin rõ ràng |
| Login/logout và multi-tab | Token rotate/invalidated | Không dùng token cũ bất ngờ |
| Pod A/B và canary/control | CSRF denied theo revision | Không có session/config drift |
| CDN cache GET token | Age/X-Cache và hai sessions giả | Không shared-cache token |
| Webhook Bearer/signature | Security chain riêng | CSRF exception không bắt nhầm machine-to-machine |
| HTTP firewall unusual path | 400/RequestRejected | Không bypass matcher/authorization |
| WAF deny trước app | Edge event | Không tạo fake CsrfException từ ứng dụng |
| CSP connect-src failure | Browser console | Không nhầm network blocked với CSRF 403 |

### 13.2. Browser DevTools quan sát đúng bản chất

- **Network**: có OPTIONS trước POST không, OPTIONS status/headers là gì?
- **Request Headers**: có tên CSRF header không; **không copy giá trị** vào ticket.
- **Cookies**: session cookie được gửi hay bị browser chặn? Set-Cookie xuất hiện nhưng không lưu vì sao?
- **Response Headers**: Cache-Control no-store cho token, CORS exact origin, redirect Location đúng HTTPS.
- **Console**: CSP connect-src chặn token bootstrap hay frontend JS error?
- **Initiator**: request xuất phát từ flow hợp lệ nào, interceptor nào?
- **Application/Storage**: cookie Secure/HttpOnly/SameSite/Domain/Path thực tế.
- **Browser version**: có giới hạn third-party cookie hoặc WebView riêng không?

Không dùng curl/Postman thành công để kết luận browser CORS/SameSite/CSP đúng. Curl không thực thi các hạn chế này theo cách browser.

### 13.3. Edge trace và request sampling

Một request có thể đi qua CDN/WAF/gateway rồi bị 403 **trước khi tới Spring**. Để phân biệt, dùng request ID an toàn và metadata:

~~~text
edge:
  requestId=req-86b7
  routeGroup=orders
  decision=allow
  statusForwarded=403

spring:
  requestId=req-86b7
  control=csrf
  reason=invalid_or_missing_actual
  status=403
~~~

Hoặc:

~~~text
edge:
  requestId=req-86b8
  routeGroup=orders
  decision=waf_denied
  status=403

spring:
  no matching request event
~~~

Mẫu thứ hai **gợi ý** edge đã chặn, nhưng vẫn cần tính đến sampling/drop logs; absence of log không phải bằng chứng tuyệt đối rằng request chưa tới Spring. Dùng gateway counters/trace propagation và synthetic requests để xác minh.

### 13.4. Tách token/session thật khỏi tài liệu điều tra

Khi xuất HAR, screenshot, browser logs hoặc network traces, cần **redact Cookie, Authorization, CSRF/XSRF headers, request/response body, query secrets** trước khi chia sẻ. Không dán token thật vào issue để “chứng minh mismatch”; người phụ trách có thể tái hiện với account test, event class và request ID.

## 14. Alerting và rollout gates: không để fix tích hợp làm yếu phòng vệ

### 14.1. Những tình huống nên chặn rollout ngay

- POST browser cookie-auth không token mà vẫn được xử lý và **tạo side effect**.
- SecurityFilterChain matcher hoặc CsrfConfigurer vô tình bỏ qua CSRF trên route browser cần bảo vệ.
- Credentialed CORS mở wildcard/phản chiếu untrusted Origin.
- Session cookie production mất Secure/HttpOnly hoặc bị phát sang host/path ngoài policy.
- GET CSRF bootstrap không còn no-store và bị shared cache.
- Frontend release làm phần lớn login → first POST thất bại, đặc biệt ở flow trọng yếu.
- Telemetry mới bắt đầu log raw CSRF token/JSESSIONID/JWT.
- One-pod config drift làm route quan trọng bị bypass CSRF.

### 14.2. Khi nào không nên mở incident chỉ vì 403 tăng?

Nếu traffic WAF/CSRF-denied tăng từ các route scanning, còn **legitimate user-flow success**, security negative tests và policy invariants vẫn đạt, có thể là hệ thống phòng vệ đang hoạt động bình thường. Cần phân loại traffic và điều chỉnh alert theo baseline, không tắt CsrfFilter.

Ngược lại, một tỷ lệ lỗi tổng thấp nhưng tập trung ở thanh toán/MFA của user hợp lệ có thể đáng ưu tiên rất cao. Các ngưỡng phải tính theo **flow criticality, release timing, baseline và số request đủ lớn**, không có một threshold đúng cho mọi công ty.

### 14.3. Gate theo tầng

~~~mermaid
flowchart LR
    A["Build + security unit tests"] --> B["Staging browser/edge"]
    B --> C["Canary một phần"]
    C --> D["CSRF negative/positive probes"]
    D --> E["Metrics 403 theo category + UX"]
    E --> F{"Bảo vệ và user flows PASS?"}
    F -->|Có| G["Rollout rộng"]
    F -->|Không| H["Stop, triage, rollback"]
    G --> I["Drift + monitoring định kỳ"]
    H --> J["Khôi phục artifact + config + edge policy"]
    J --> D
~~~

Trong deployment record lưu **artifact digest, Spring Security dependency revision, CSRF repository/handler policy, config revision, gateway/CDN revision và frontend release**. Không lưu token hay secret values vào manifest.

### 14.4. Rollback phải xét trạng thái browser/session

Rollback Java artifact nhưng để lại frontend build mới hoặc CDN header rules cũ có thể không giải quyết lỗi. Một migration repository/handler có thể khiến **token cũ** không còn hợp lệ; phải thiết kế refresh/relogin rõ ràng. **HSTS browser cache**, CORS preflight cache và service worker/cached SPA shell cũng có thể giữ behavior cũ sau deploy.

Sau rollback, test GET token → POST hợp lệ, POST không token bị chặn, login/logout và cookie scope trên browser thật. **Không đánh dấu rollback thành công chỉ vì pod HEALTHY**.

## 15. Runbook điều tra sự cố và quy trình phối hợp

### 15.1. Runbook A — CSRF 403 tăng ngay sau deploy frontend/backend

**Dấu hiệu:** Người dùng hợp lệ gặp nhiều 403 ở một form/SPA route ngay sau phát hành, tỷ lệ hoàn tất workflow giảm.

1. **Ghim mốc thời gian**: frontend release, backend artifact, Spring Security/BOM, gateway/CDN config và active profiles.
2. Phân tách **confirmed CSRF** với authorization 403 và gateway denied. Không dùng một biểu đồ 403 tổng làm bằng chứng.
3. So tỷ lệ lỗi theo **route, client release, browser family, canary/control và pod**.
4. Xem GET /api/csrf trước POST có thành công và **no-store** không; cookie/session có được giữ cùng request không.
5. Kiểm tra frontend gửi **đúng tên CSRF header** và token mode raw/XOR tương thích repository/request handler.
6. Tái hiện với **test account và browser DevTools**, không cần token production thật.
7. Chạy POST thiếu token để chứng minh CSRF vẫn chặn; chạy POST token đúng với authz đúng để chứng minh chức năng.
8. Nếu regression ảnh hưởng nhiều user, **stop rollout/rollback cặp frontend + backend/config tương thích**.
9. Sau remediation, chạy lại canary, theo dõi valid-flow success và audit category; ghi nguyên nhân gốc vào postmortem.

**Không sửa bằng csrf.disable() hoặc ignoringRequestMatchers("/api/**")**. Điều này làm 403 giảm nhưng có thể mở lỗ hổng.

### 15.2. Runbook B — 403 chỉ sau login/logout hoặc khi đổi account

**Dấu hiệu:** Login thành công, nhưng POST đầu tiên hoặc logout tiếp theo bị 403; refresh browser có thể “sửa tạm”.

1. Xác minh **POST login có token trước login** và session cookie đang hợp lệ.
2. Kiểm tra sau thành công **CsrfAuthenticationStrategy/CsrfLogoutHandler** có xóa token cũ như thiết kế không.
3. Kiểm tra frontend có **clear stale token và GET token mới** sau auth transition.
4. Đối chiếu request race: GET token cũ đến muộn, multi-tab logout hoặc chuyển account.
5. Kiểm tra session ID rotation/session fixation protection có làm cookie jar thay đổi không.
6. Nếu dùng SPA memory token, sử dụng **epoch** để loại response bootstrap cũ và đồng bộ tabs phù hợp.
7. Test login → GET token B → POST → POST logout với token B → GET token C; ghi **trạng thái**, không ghi token strings.
8. Không retry POST không idempotent chỉ để vượt 403.

### 15.3. Runbook C — “CSRF lỗi” nhưng thực ra CORS preflight không qua

**Dấu hiệu:** Browser console báo CORS/preflight failure; server thấy OPTIONS 401/403, không thấy POST tương ứng.

1. Gửi OPTIONS **không Cookie** trong staging/public edge với Origin, Access-Control-Request-Method và Access-Control-Request-Headers phù hợp.
2. Kiểm tra exact Access-Control-Allow-Origin, Allow-Methods, Allow-Headers và Allow-Credentials.
3. Kiểm tra CorsFilter/CorsWebFilter chạy trước authentication và gateway không redirect OPTIONS đến login.
4. Đối chiếu API origin, frontend origin, request method và CSRF header name sau deploy.
5. Tái hiện **actual POST** sau khi preflight đúng; lúc này mới đánh giá CsrfFilter.
6. Test untrusted Origin vẫn không có credentialed access; không mở wildcard làm “fix”.
7. Thêm CORS preflight regression cho login/logout/refresh endpoints ngoài /api/** nếu SPA gọi chúng cross-origin.

### 15.4. Runbook D — 403 tập trung ở một browser hoặc sau idle dài

**Dấu hiệu:** Safari/WebView hoặc tab mở lâu gặp 403, browser desktop khác bình thường.

1. Quan sát cookie blocked reason, Secure/HttpOnly/SameSite/Domain/Path trong DevTools.
2. Phân biệt same-origin và same-site; kiểm tra third-party cookie policy của browser.
3. Xem request fetch có **credentials include** và backend CORS có Allow-Credentials cho exact origin không.
4. Kiểm tra session timeout, CSRF token trong memory và logic refresh sau idle.
5. Thử chuyển tab/logout/tái đăng nhập và nhiều phiên đồng thời.
6. Kiểm tra CSP connect-src không chặn token bootstrap.
7. Nếu phải đổi cookie architecture, đánh giá an toàn toàn flow và rollout có canary; không bỏ HttpOnly cho session.

### 15.5. Runbook E — 403 không đều giữa nhiều pods/regions

**Dấu hiệu:** Request hợp lệ thành công lần này nhưng 403 lần khác, đặc biệt khi load balancing.

1. Phân chia tỷ lệ 403 theo **release, region, workload, pod group**, tránh metric per pod ID cardinality quá lớn nếu cluster động.
2. So config fingerprint **không chứa secrets**, token repository và request handler version.
3. Kiểm tra HttpSession/WebSession store, sticky routing, session expiry và cookie signing keys.
4. Xác minh gateway path rewrite hay securityMatcher có khác giữa các revisions không.
5. Tái hiện với **hai test sessions tách biệt**, không dùng real session token trong logs.
6. Nếu một nhóm instance có cấu hình yếu hơn hoặc không bảo vệ CSRF, cô lập canary/rollback theo policy.
7. Sau khi đồng bộ artifact + config + edge rules, test session/token xuyên pods và kiểm tra lại dashboard.

### 15.6. Runbook F — 403 tăng mạnh trên nhiều route, nghi traffic bất thường

**Dấu hiệu:** Nhiều unsafe paths không bình thường bị CSRF denial, kèm 401/authorization denial hoặc WAF signals.

1. Xác nhận traffic xuất hiện **trên tầng nào** và có user flow hợp lệ bị ảnh hưởng không.
2. Dùng route group, method, request rate theo time window, WAF rule class và auth status. Không cần copy headers/token thô.
3. Phân biệt internet scanners và integration clients gọi sai: có release/change timeline hoặc pattern chuẩn của một đối tác hợp lệ không?
4. Kiểm tra **negative test POST thiếu CSRF vẫn bị chặn**, không có database side effects.
5. Nếu cần giảm tải, cân nhắc rate limits/WAF/bot mitigation có review, không dùng disable CSRF.
6. Theo dõi false positives và tác động tới người dùng ở NAT hoặc mạng doanh nghiệp.
7. Chỉ phân loại **suspected abuse** khi có nhiều bằng chứng; kích hoạt incident response nếu có dấu hiệu bypass, credential leak hoặc thành công trái phép.

### 15.7. Runbook G — 403 từ gateway/WAF hoặc firewall, không có CsrfException

1. Đối chiếu request ID giữa **edge và Spring**; xem có edge deny event không.
2. Kiểm tra status/Location/response signature của WAF, reverse proxy hoặc container.
3. Với path encoding bất thường, so gateway normalization, **StrictHttpFirewall** (Servlet), security matcher và MVC mapping.
4. Đảm bảo redirect HTTPS, forwarded headers được sanitize từ trusted proxy.
5. Chạy test đường đi qua public edge và app direct; không chỉ curl localhost.
6. Không nới StrictHttpFirewall hoặc bỏ HTTP filters để giảm số lượng 403 khi chưa đánh giá bypass.
7. Nếu có xung đột trong ingress, sửa đúng layer/owner và thêm regression tests.

### 15.8. Runbook H — CSRF token hoặc session credential lộ trong telemetry

**Dấu hiệu:** Một sự kiện debug/HTTP dump chứa JSESSIONID, raw/XOR CSRF token, Bearer token, query secret hoặc response JSON token.

1. Hạn chế truy cập, tạm dừng logging/body capture gây lộ **trước khi gửi tiếp lên APM**.
2. Không copy nguyên payload ra ticket, email hoặc kênh chat.
3. Xác định loại credential/token, phạm vi truy cập và thời điểm lộ.
4. Nếu session/JWT/refresh token cũng bị lộ, thực hiện quy trình credential/session revocation/rotation theo mức độ.
5. Với CSRF token đơn lẻ, đánh giá session binding và TTL; không khẳng định mọi leak đều tương đương chiếm tài khoản.
6. Nếu CDN đã cache token response, sửa no-store/edge bypass và purge/invalidate cache.
7. Làm việc với owner logs/APM về retention, xóa dữ liệu và nghĩa vụ bảo mật.
8. Dùng **synthetic canary trong staging** để kiểm chứng redaction, đồng thời giữ được metadata audit hữu ích.

### 15.9. Cây quyết định rút gọn

~~~mermaid
flowchart TD
    A["Browser/app ghi nhận 403"] --> B{"Request đến Spring?"}
    B -->|Chưa rõ / không| C["Kiểm tra gateway, WAF, CORS OPTIONS"]
    B -->|Có| D{"Confirmed CsrfException?"}
    D -->|Không| E["Authorization/authentication/firewall/other"]
    D -->|Có| F{"Nhiều user hợp lệ sau release?"}
    F -->|Có| G["Kiểm tra token lifecycle, cookie, raw-XOR, revision"]
    F -->|Không| H["Đối chiếu baseline, WAF, route patterns"]
    G --> I["Reproduce + safe canary, sửa hoặc rollback"]
    H --> J["Triage suspected abuse, false positives"]
    I --> K["Negative tests + user-flow success PASS"]
    J --> K
    C --> K
    E --> K
~~~

Không biến cây quyết định thành hệ thống phán đoán tự động duy nhất. Một incident thực có thể gồm **nhiều lỗi đồng thời**, ví dụ CORS preflight lỗi trên SPA và bot scan làm 403 tăng cùng lúc.

## 16. Bài tập thực hành

**Bài A — Phân biệt 403:** Tạo endpoint Servlet cookie-auth và hai request: POST thiếu CSRF, POST CSRF đúng nhưng user thiếu quyền. Quan sát status đều 403 nhưng phân loại reason khác, không log token.

**Bài B — Missing vs invalid:** Dùng session-backed repository, thử không có expected token so với actual token không đúng. Kiểm tra category do Spring Security thực sự tạo ở phiên bản đang pin; nêu lý do **MissingCsrfTokenException không tương đương luôn “thiếu header”**.

**Bài C — SPA sau login:** Mô phỏng login → token bị clear → frontend dùng token cũ, sau đó sửa bằng GET bootstrap token mới. Xem first POST success rate trước/sau.

**Bài D — Multi-tab race:** Mở hai tabs cùng session; logout từ tab A, POST từ tab B. Thiết kế thông báo trạng thái auth và epoch guard cho token refresh.

**Bài E — Cookie/CORS:** SPA app.example.com, API api.example.com. Kiểm tra OPTIONS không Cookie, Fetch credentials, SameSite và cookie host-only. Không dùng wildcard credentials.

**Bài F — Raw/XOR:** Cho frontend gửi raw XSRF cookie trong khi server request handler kỳ vọng masked token; viết test tái hiện 403 rồi sửa contract; không in token trong CI log.

**Bài G — Metrics low-cardinality:** Thiết kế dashboards cho CSRF/authorization/WAF denials, route template và release. Giải thích vì sao IP hoặc session ID không được dùng làm Prometheus label.

**Bài H — Servlet audit:** Gắn status-only filter và CSRF denial handler trên đúng đường xử lý. Kiểm tra không đếm authorization 403 là CSRF confirmed và không double-count.

**Bài I — WebFlux parity:** Tạo WebTestClient tests cho CsrfWebFilter missing/valid token, WebSession expiry và safe metrics. Đảm bảo handler thực sự nhìn thấy exception trước khi báo confirmed CSRF.

**Bài J — Gateway/WAF:** Cho một request bị edge chặn trước Spring. Dùng request ID chứng minh phải giữ số đếm edge riêng; không suy luận thiếu app log là thiếu tấn công.

**Bài K — Canary regression:** Frontend release bỏ CSRF header trên POST /api/profile. Thiết kế canary stop gate dựa trên valid-flow success và confirmed CSRF denials; không “fix” bằng csrf.disable().

**Bài L — Session store drift:** Để staging có hai pods cấu hình session repository khác nhau. Xác minh 403 chỉ ở pod sai và giải pháp nhất quán sau rollback.

**Bài M — Log privacy:** Bơm synthetic canary ở staging, kiểm tra logs/APM/traces không thu CSRF/Cookie/Authorization/body, chỉ giữ reason category và request ID.

**Bài N — Phản ứng sự cố:** Tạo một bảng triage trong đó cùng lúc có bot scanner gây hàng nghìn 403 và một lỗi thanh toán hợp lệ sau deploy. Chọn ưu tiên theo nguy cơ và tác động, không chỉ số đếm.

## 17. Checklist phát hành, giám sát và xử lý sự cố

### 17.1. Checklist triển khai

| Nhóm kiểm soát | Tiêu chí PASS |
| --- | --- |
| **Bản đồ route** | Biết route cookie-auth cần CSRF và Bearer-only route không có cookie fallback |
| **Filter chain** | Servlet/Reactive chain đúng matcher/order, không bỏ qua CSRF ngoài chủ đích |
| **Token bootstrap** | GET /api/csrf trả token phù hợp repository/handler, no-store |
| **Token lifecycle** | Login/logout/session timeout yêu cầu token mới khi thích hợp |
| **Raw/XOR contract** | SPA cookie raw, JSON masked, handler và header name khớp nhau |
| **CSRF negative test** | POST thiếu/sai token bị chặn và **không có side effect** |
| **Authorization** | POST token đúng nhưng user thiếu quyền vẫn bị chặn |
| **CORS** | Trusted preflight không cookie thành công; untrusted Origin không được credentialed access |
| **Cookie/session** | Secure/HttpOnly/SameSite/Domain/Path và session store đúng deployment |
| **HTTP firewall/gateway** | URL normalization không bypass matcher và edge denies được đo riêng |
| **CSP/HSTS** | Không chặn token bootstrap ngoài ý muốn, TLS/redirect/cookie đúng |
| **Servlet monitoring** | Status-only counter không gắn nhãn CSRF; confirmed handler được test thực |
| **Reactive monitoring** | WebFilter status và CsrfException path được phân loại riêng |
| **Metrics** | Low-cardinality labels, không chứa IP/token/session/JWT/raw URL |
| **Audit/logs** | No raw headers/body, reason category và request ID an toàn |
| **Dashboards** | Theo route/release/client class, so valid-flow success và baseline |
| **Canary** | Có stop/rollback gate cho bypass CSRF hoặc integration regression |
| **Rollback** | Artifact, frontend, config, gateway/CDN policy known-good được xác định |
| **Incident response** | Có runbooks cho integration, abuse traffic, session, CORS và data leak |

### 17.2. Mười hai nguyên tắc cốt lõi

1. **Không phải mọi 403 đều là CSRF**. Phải xác minh tầng từ chối và reason.
2. **MissingCsrfTokenException không luôn có nghĩa frontend thiếu header**; cần hiểu expected/actual token context.
3. **Lỗi CSRF không chứng minh động cơ tấn công**; kết luận dựa trên nhiều tín hiệu độc lập.
4. **CSRF token có vòng đời theo session/auth**, có thể đổi sau login/logout và không nên được giữ stale trong SPA.
5. **Raw cookie token, XOR-masked representation và deferred loading** cần một hợp đồng nhất quán giữa frontend và server.
6. **CORS preflight không phải POST CSRF**, browser có thể chưa gửi actual request nếu OPTIONS thất bại.
7. **SameSite/CORS/CSP/HSTS/firewall là lớp khác nhau**; chẩn đoán từng lớp, không tắt để chữa lỗi chung.
8. **Status-only 403 observer không được gắn nhãn confirmed CSRF**; phân loại exception chỉ khi handler có bằng chứng.
9. **Không log CSRF token, Cookie, JWT hay request body**; dùng route template, category, revision và request ID.
10. **So canary/control, baseline và business-flow success**, không chỉ số lượng request bị chặn.
11. **POST thiếu token phải bị từ chối không side effect**, ngay cả khi hệ thống đang bị tấn công hay gặp regression.
12. **Rollback và remediation không được làm yếu bảo vệ**: khôi phục artifact/config/frontend/edge policy đồng bộ và chạy negative tests sau sửa.

**Kết luận:** Giám sát CSRF hiệu quả không phải là dựng một đồ thị HTTP 403. Đó là khả năng **nhận diện đường từ chối thật, giải thích token/session lifecycle, so sánh dữ liệu theo release và client, nhận diện giao thoa giữa CORS, CSP, gateway, authorization và CSRF**, rồi ra quyết định vận hành bảo toàn cả an toàn lẫn chức năng. Khi thiếu/sai token và request bất thường được phân loại bằng audit an toàn, tests nhiều tầng và runbooks, đội vận hành có thể sửa lỗi tích hợp mà không mở ra đường bypass CSRF.

## Tài liệu tham khảo chính thức và bổ trợ

- [Spring Security 6.5 — Servlet CSRF, SPA và request handlers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Servlet CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — Reactive CORS](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/firewall.html)
- [Spring Security 6.5 — Servlet HTTP Security Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — Reactive HTTP Security Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Boot — Actuator and Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)





