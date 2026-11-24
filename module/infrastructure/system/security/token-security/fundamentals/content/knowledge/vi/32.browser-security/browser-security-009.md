# History và token URL

## 1. Vì sao URL và lịch sử trình duyệt là ranh giới bảo mật của token?

Trong chương **Browser security** thuộc module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, bài **History và token URL** tập trung vào một câu hỏi thực tế: **Điều gì xảy ra khi authorization code, access token, ID token, refresh token hoặc một credential khôi phục phiên xuất hiện trong URL mà trình duyệt mở?**

Ví dụ nhân viên Alice đăng nhập `employee-portal` qua OAuth 2.0/OpenID Connect (OIDC). Authorization Server (AS) có thể đưa trình duyệt về ứng dụng bằng:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.test/login/oauth2/code/company?code=<authorization-code>&state=<random-state>
~~~

Đây là **Authorization Code Flow**: authorization code nằm trong **query** của callback URL, được client dùng để đổi token **một lần** qua back channel. Nó không phải access token cho API, nhưng vẫn là **credential nhạy cảm, có thời hạn ngắn**. Nếu URL callback bị ghi trong access logs, được gửi tới analytics, bị copy/paste hoặc được lưu trong browser history, code có thể bị lộ. **PKCE S256** làm code bị đánh cắp khó đổi thành token hơn nếu attacker không có `code_verifier`; **không** làm URL chứa code trở nên công khai an toàn.

Một anti-pattern nguy hiểm hơn:

~~~text
https://portal.example.test/dashboard?access_token=<bearer-access-token>
~~~

Access token thường trực tiếp cấp quyền gọi Resource Server (RS). Nếu nó xuất hiện trong query URL, nhiều thành phần có thể giữ bản sao: browser history, reverse proxy, CDN/WAF, server logs, performance monitoring, Referer trong những điều kiện nhất định, link được chia sẻ, screenshots hoặc browser extensions. Khi kẻ tấn công lấy được bearer token chưa hết hạn và chưa bị thu hồi, họ có thể **replay** nó tại RS nếu không có sender constraint và các biện pháp khác.

> **Nguyên tắc:** **Không đưa OAuth access token, refresh token hoặc ID token vào URL chỉ để tiện điều hướng ứng dụng.** Authorization Code Flow có thể mang **code ngắn hạn** qua redirect query theo giao thức, nhưng cần **state, PKCE, client/redirect/issuer binding, xử lý nhanh, dọn URL và hạn chế kênh rò**. Việc xóa URL bằng JavaScript **sau khi rò** không thể thu hồi dữ liệu đã nằm trong network logs hay lịch sử hệ thống khác.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt phần **query**, **fragment**, **path**, **authority** của URL và biết phần nào được gửi lên HTTP server.
2. Mô tả nơi token/code có thể rò từ **browser history, address bar, Referer, redirects, proxy logs, analytics, browser restoration, third-party scripts và copy/paste**.
3. Giải thích vì sao **OAuth Implicit Flow** trả token qua fragment có rủi ro hơn **Authorization Code + PKCE**, và phân biệt fragment với query.
4. Thiết kế callback **Code + PKCE** có `state`/issuer/nonce và xử lý URL sạch mà không gửi token vào JavaScript third party.
5. Áp dụng `history.replaceState`, `location.replace`, `Referrer-Policy`, `Cache-Control`, redirect URI allowlist và Content Security Policy (**CSP**) đúng mục đích, hiểu giới hạn từng biện pháp.
6. Chọn kiến trúc **BFF + session cookie** hoặc browser-based OAuth client theo threat model, không hiểu `HttpOnly` là loại bỏ mọi XSS/CSRF.
7. Viết ví dụ Java/Spring Security và kiểm thử end-to-end bằng browser thật cho các đường rò credential.

Mọi hostname `example.test`, mã token, đường dẫn và trạng thái minh họa trong bài là dữ liệu giả, không phải credential hoặc URL production.

## 2. Giải phẫu URL: query không giống fragment

Xem URL:

~~~text
https://portal.example.test/callback?code=C1&state=S1#panel=summary
|---- scheme ----|------ authority ------|--- path --|--- query ---|fragment|
~~~

| Thành phần | Ví dụ | Ai thường nhìn thấy? | Rủi ro khi chứa credential |
| --- | --- | --- | --- |
| **Scheme** | `https` | Browser, network endpoints | Không chứa token; cần HTTPS bảo vệ transport |
| **Authority / host** | `portal.example.test` | DNS, TLS/SNI và mạng ở mức phù hợp | Không đặt credential trong hostname/userinfo |
| **Path** | `/callback/token123` | Browser, HTTP request target, proxy/server logs | Token trong path **vẫn dễ bị log/history/share** |
| **Query** | `?code=C1&state=S1` | Browser và request-target gửi tới origin; nhiều lớp proxy/logs | Rò code/token nếu giữ quá lâu hoặc gửi bên thứ ba |
| **Fragment** | `#access_token=AT1` | Browser và JavaScript; **không được gửi trong HTTP request target** | Vẫn hiện ở address bar/history/JS/extension và client telemetry |

### 2.1. Query được gửi ở HTTP request

Với:

~~~text
https://portal.example.test/callback?code=C1&state=S1
~~~

Browser thường gửi tới origin:

~~~http
GET /callback?code=C1&state=S1 HTTP/1.1
Host: portal.example.test
~~~

Do đó, **reverse proxy, WAF, load balancer, backend access log, APM và packet capture tại điểm giải mã TLS** có thể nhìn thấy query nếu chúng ghi request-target. HTTPS **không** ngăn server hoặc reverse proxy do ứng dụng vận hành nhìn thấy URL được gửi tới chính nó. Ngăn ghi raw query/có redaction và giới hạn truy cập logs là yêu cầu khác với TLS.

### 2.2. Fragment không được gửi trong HTTP request target

Với:

~~~text
https://portal.example.test/callback#access_token=AT1&token_type=Bearer
~~~

Browser gửi tới origin **chỉ**:

~~~http
GET /callback HTTP/1.1
Host: portal.example.test
~~~

Fragment `#...` **không** đi cùng request-target HTTP và cũng không được truyền dưới dạng fragment trong header `Referer` chuẩn. **Tuy nhiên**, JavaScript chạy ở document đó có thể đọc `window.location.hash`; fragment có thể hiện ở address bar, history, browser restore, screenshots, extensions và bị JavaScript hoặc analytics cố ý gửi tới máy chủ. Vì thế câu “fragment không lên server, nên an toàn để chứa AT” là **sai**.

### 2.3. URL trong browser history không phải chỉ history API

“History” có thể đề cập nhiều thứ khác nhau:

- **Navigation/session history**: các entries do người dùng mở, redirect hoặc `pushState`/`replaceState` tạo hoặc thay đổi.
- **Browser history database**: dữ liệu history có thể được browser lưu/đồng bộ tùy sản phẩm/cấu hình; không nhất thiết tương ứng một-một với tab/session entries.
- **Back/forward cache (bfcache)**: browser có thể giữ trạng thái document/snapshot cho Back/Forward navigation; tùy browser, headers và điều kiện.
- **Session restore**: browser khôi phục tabs/URL sau crash/restart.
- **Autocomplete/bookmarks/share**: URL còn tồn tại trong thao tác người dùng, clipboard và bản lưu khác.
- **Service worker/Cache API**: scripts do origin kiểm soát có thể intercept/cache request theo thiết kế; không phải cùng nghĩa với HTTP cache hay history.

**`history.replaceState` chủ yếu thay URL của entry hiện tại trong session history**; nó không xóa access logs đã ghi, mọi history/sync bản sao, screenshot, analytics, token đã lộ hay bfcache snapshot đã tạo trước đó.

### 2.4. Không đưa credential vào mọi phần URL

Các biến thể đều có vấn đề:

~~~text
BAD: https://api.example.test/orders?access_token=AT1
BAD: https://api.example.test/access/AT1/orders
BAD: https://AT1@api.example.test/orders
BAD: https://portal.example.test/#refresh_token=RT1
BAD: https://portal.example.test/callback#id_token=ID1
~~~

Với access token khi gọi API, lựa chọn HTTP phổ biến được RFC 6750 khuyến nghị là:

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-for-orders-api>
~~~

**Header cũng là bí mật**: TLS, request logging redaction, token storage, sender constraints và audience validation vẫn cần. Đặt AT trong header không chứng minh client không bị XSS hay server không log `Authorization`.

## 3. OAuth/OIDC có thể đưa gì vào redirect URL?

### 3.1. So sánh các response modes và token types

| OAuth/OIDC flow/response | Dữ liệu trả qua browser | Vị trí thường gặp | Điều cần biết |
| --- | --- | --- | --- |
| **Authorization Code** | `code`, `state` (và `iss` khi áp dụng) | Query của registered redirect URI, hoặc `form_post` theo response mode | Code chỉ đổi một lần, short TTL, PKCE/redirect/client binding |
| **Implicit** (legacy) | `access_token`, `token_type`, `expires_in` và có thể OIDC `id_token` | URL fragment khi response mode `fragment` | Token nằm trong front channel, bị exposed cho browser JS; không nên chọn cho thiết kế mới |
| **OIDC Hybrid** (legacy/đặc thù) | Code cùng ID token/AT theo `response_type` | Fragment hoặc `form_post` theo profile | Token/purpose/`c_hash`, `at_hash`/nonce validations phức tạp |
| **`response_mode=form_post`** | Code/response parameters qua form POST tới RP | HTTP POST body của redirect callback | Giảm rò qua URL/history nhưng vẫn cần TLS, CSRF/state, no-store và log redaction |
| **Token endpoint** | AT/RT/ID token qua back channel | HTTPS response body cho OAuth client | Không tự chuyển tokens vào navigation URLs |
| **`post_logout_redirect_uri`** | `state` nếu RP-Initiated Logout dùng | Callback URL/query sau OP logout | Không đưa RT/AT/ID token vào logout redirect URL |

Nhiều hệ thống dùng **Authorization Code + PKCE** làm luồng mới; với browser-based apps, phải xem cả **token nơi được giữ sau exchange**. Code+PKCE chống code interception, **không tự chặn** XSS đánh cắp token đã ở JavaScript memory/storage.

### 3.2. Access token và refresh token phải ở đúng ranh giới

- **Authorization code**: phát tại AS authorization endpoint, quay về client callback, đổi tại AS token endpoint, không gửi tới RS.
- **Access token**: client trình tới RS, thường bằng `Authorization: Bearer`; RS kiểm issuer/audience/expiry/scope và ACL.
- **Refresh token**: client dùng ở AS token endpoint để lấy AT mới; có rotation/sender constraint/revocation policy, **không** đặt trong URL hoặc chuyển tới RS.
- **ID token OIDC**: RP dùng để xác thực user theo `iss`, `aud=client_id`, `nonce` khi áp dụng, không làm OAuth API bearer token.

Một anti-pattern:

~~~javascript
// KHÔNG làm: ghép access token vào URL điều hướng.
window.location.href =
    "/dashboard?access_token=" + accessToken;
~~~

Nó làm AT hiện trong URL/history và có thể gửi qua HTTP. **Không** sửa bằng cách chỉ `encodeURIComponent(accessToken)`: encoding giúp đúng cú pháp, **không mã hóa bảo mật**.

### 3.3. Giải pháp URL-based token cho password reset khác OAuth AT

Một link khôi phục mật khẩu hay xác minh email thường **cố ý** chứa một **one-time action token** ngắn hạn trong URL. Đây là một bài toán khác:

~~~text
https://account.example.test/reset?code=<one-time-recovery-token>
~~~

Nó vẫn phải có **entropy, short TTL, single-use, purpose/recipient binding, no-store/referrer policy, no third-party scripts và log redaction**; sau khi xác nhận nên chuyển sang URL sạch. **Không** lấy sự tồn tại của reset link để biện minh đưa **OAuth bearer AT/RT** lên query URL.

## 4. Authorization Code + PKCE: vòng đời URL an toàn hơn

### 4.1. Luồng chuẩn

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice / Browser
    participant C as employee-portal / Client
    participant AS as Authorization Server / OP
    participant RS as orders-api / RS
    C->>C: Create state, PKCE verifier and challenge (+ OIDC nonce)
    C-->>U: Redirect to trusted /authorize
    U->>AS: code_challenge=S256, state, client_id, redirect_uri
    AS->>AS: Authenticate, apply policy/consent
    AS-->>U: Redirect to registered callback?code=C1&state=S1
    U->>C: GET callback with one-time code C1
    C->>C: Check state/issuer, retrieve original verifier
    C->>AS: POST /token with code C1 and original verifier
    AS->>AS: Validate client, redirect, PKCE and single-use code
    AS-->>C: AT (+ ID token/RT as permitted)
    C-->>U: Redirect to clean /home URL
    C->>RS: API request using AT (not code, not URL query)
    RS->>RS: Validate AT issuer/audience/expiry/scope and ACL
~~~

Authorization code thường được đưa qua query của browser callback. Nhưng điểm khác biệt lớn với Implicit Flow là **AT không cần nằm trong navigation URL**. Với server-side OAuth client/BFF, token exchange và token storage nằm tại backend; browser chỉ mang session cookie thích hợp.

### 4.2. Điều kiện bắt buộc quanh callback

1. **Trusted AS**: client biết issuer, authorization/token endpoints từ registration/discovery đã verify, không từ URL attacker.
2. **Registered redirect URI**: AS so chính xác theo profile; không wildcard/open redirect đưa code ra host lạ.
3. **`state`**: client ràng buộc callback vào transaction/browser để chống login CSRF/mix-up.
4. **PKCE `S256`**: AS lưu `code_challenge` và yêu cầu original `code_verifier` tại token endpoint.
5. **Client binding**: code gắn đúng client; confidential client authentication khi được đăng ký.
6. **Single-use code**: AS từ chối code đã redeemed, expired, sai client/redirect/PKCE.
7. **OIDC ID token validation**: RP kiểm chữ ký, `iss`, `aud`, `exp`, `nonce` và `azp` khi áp dụng.
8. **Clean navigation**: sau callback, chuyển đến route không còn `code`/`state` và không log raw callback URL.

### 4.3. Code trong query không phải lý do bỏ các biện pháp chống leak

PKCE chỉ giảm rủi ro khi attacker **không có original verifier**. Nếu attacker có quyền đọc browser JS memory, session transaction, HTTP client log hoặc token endpoint request đầy đủ, họ có thể đánh cắp code **và** verifier. Vì vậy:

- Hạn chế scripts và external resources trên callback.
- Không ghi `code`/`state`/`code_verifier` vào telemetry.
- Không biến callback thành open redirect.
- Sử dụng HTTPS và TLS validation cho AS, RP và API.
- Tránh hiển thị trang callback chứa third-party analytics trước khi xử lý.
- Không retry `POST /token` với code cũ vô hạn sau mất response; code là credential **one-time**.

### 4.4. URL sạch sau callback

Một server-side RP có thể:

~~~http
HTTP/1.1 303 See Other
Location: /home
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Tức là client nhận callback, xác minh state, đổi code/thiết lập session rồi redirect đến `/home`. **Redirect không xóa các bản log đã ghi**; với session history, có thể còn history entries/ghi nhận browser khác tùy navigation behavior. Vì thế vẫn cần **redact logs, referrer controls và tránh third-party resources ở callback**.

### 4.5. Một lỗi khi dùng `replaceState` quá sớm

Nếu browser app tự xóa `code` khỏi URL trước khi **đọc và liên kết** nó với saved `state`/PKCE transaction, reload sẽ không thể hoàn tất exchange. Nếu server-side `oauth2Login` của Spring đang xử lý callback, frontend JavaScript **không nên** chen vào xóa query trước khi server xử lý. Hãy định nghĩa đúng bên sở hữu callback:

~~~text
BFF/Server OAuth client: server owns callback and token exchange.
SPA OAuth client: client JS owns callback, needs safe early URL cleanup.
~~~

Hai chiến lược có điểm chung là **không giữ code/token trong địa chỉ ứng dụng sau khi callback hoàn tất**, nhưng thứ tự và nơi lưu transaction khác nhau.

## 5. Legacy Implicit Flow và fragment: “không lên server” không đồng nghĩa an toàn

### 5.1. Vì sao Implicit Flow từng dùng fragment?

OAuth 2.0 Implicit Grant (legacy) có thể trả access token thẳng về browser:

~~~text
https://portal.example.test/callback#access_token=AT1&token_type=Bearer&expires_in=300&state=S1
~~~

Browser gửi HTTP request đến `/callback` **không kèm fragment**. JavaScript phía page đọc `location.hash` và lấy AT để gọi API. Thiết kế này tránh token endpoint exchange nhưng **đưa bearer AT lên browser front channel**, nơi JavaScript và các thành phần browser-side có thể nhìn thấy.

### 5.2. Những đường rò dù fragment không gửi HTTP

| Đường rò | Fragment có thể bị ảnh hưởng? | Diễn giải |
| --- | --- | --- |
| JavaScript chạy cùng origin/page | **Có** | `window.location.hash`/`document.URL` có thể được đọc và gửi ra ngoài |
| Third-party script được nhúng | **Có** | Script chạy trong document có cùng quyền DOM/URL như script first-party |
| Browser address bar/history/session restore | **Có thể** | URL chứa fragment có thể còn được lưu/hiển thị |
| Copy link, screenshot, screen sharing | **Có** | Người dùng có thể tự công bố toàn bộ URL |
| Browser extensions có quyền phù hợp | **Có thể** | Extensions có thể quan sát URL/document tùy quyền/browser |
| HTTP request-target tới origin | **Không** | Fragment không được gửi trong request line |
| Header `Referer` chuẩn | **Không gồm fragment** | User agent phải bỏ fragment khi tạo Referer |
| Analytics/telemetry JS | **Có** | JS có thể đọc URL đầy đủ rồi gửi bằng request riêng |
| CSP/referrer policy | **Giảm một số đường**, không chặn JS đã được cấp quyền | CSP là defense-in-depth, không cách ly third-party script đã chạy |

### 5.3. Fragment không được gửi qua HTTP, nhưng redirects vẫn cần kiểm tra

Một browser navigation có thể đi qua nhiều `Location` redirects và document URLs; việc fragment được giữ/thay thế khi resolve redirect phụ thuộc URL/HTTP semantics và browser behavior. **Không** dựa vào giả định “redirect sẽ luôn tự xóa fragment”; phải kiểm thử chính xác browser/redirect chain của hệ thống. Quan trọng hơn, **không phát bearer AT vào fragment ngay từ đầu** nếu thiết kế có thể dùng Authorization Code + PKCE.

### 5.4. Vì sao không chọn Implicit Flow cho hệ thống mới?

Các khuyến nghị bảo mật OAuth hiện đại ưu tiên **Authorization Code + PKCE**, kể cả với browser-based public clients:

- AT được phát qua token endpoint, không phải authorization response front channel.
- PKCE ràng buộc code với verifier; code chỉ dùng một lần.
- AS có nhiều cơ hội kiểm client/redirect/grant policy tại token endpoint.
- Dễ dùng refresh-token rotation/sender-constrained strategy phù hợp hơn.
- Giảm một số đường rò AT qua history/URL, dù **không loại bỏ XSS** hoặc token theft trong SPA.

Không “nâng cấp” Implicit bằng cách đổi tên `access_token` thành `t` trong fragment. Chỉ rename key không cải thiện nơi credential bị phơi.

### 5.5. OIDC Hybrid / `form_post`

OIDC Hybrid Flow có thể đưa ID token hoặc AT vào authorization response theo `response_type`/`response_mode` đã đăng ký. `response_mode=form_post` chuyển params bằng HTTP POST body thay query/fragment; nó **giảm rủi ro history/URL** nhưng không có nghĩa request body sẽ không bị ghi trong APM/logs hoặc không cần `state`/`nonce`/token validation.

Khi client xử lý form post, callback cần bảo vệ HTTPS, content type/body size, transaction binding và không log raw form fields. Đừng tự chuyển response modes mà không kiểm AS/RP tương thích và security profile.

## 6. Browser history, Back/Forward, bfcache và session restore

### 6.1. Có những “bản sao URL” nằm ngoài ứng dụng

Giả sử browser từng điều hướng đến:

~~~text
https://portal.example.test/callback?code=C1&state=S1
~~~

Ứng dụng có thể xử lý code, redirect đến `/home` và không còn hiển thị URL cũ. Tuy nhiên, không thể khẳng định mọi dấu vết của callback đã biến mất:

- Reverse proxy có thể đã ghi `GET /callback?code=C1&state=S1`.
- Browser có thể giữ dấu vết navigation/history hoặc session restore khác nhau theo phiên bản/cấu hình.
- Extension hoặc analytics đã quan sát full URL trước khi chuyển.
- Browser có thể chụp UI/thumbnail, hoặc người dùng copy URL trước cleanup.
- Crash report hoặc web performance instrumentation có thể giữ request URL.
- Người dùng quay lại bằng Back, mở bookmark hoặc lịch sử đồng bộ tạo request mới với **code đã dùng**.

Đừng dùng **history cleanup** làm biện pháp thay cho **code single-use, PKCE và short expiry** ở AS. Một callback có code đã dùng lại phải bị token endpoint từ chối; không cấp bộ AT/RT mới chỉ vì browser Back navigation.

### 6.2. `history.pushState` và `history.replaceState` khác nhau

| API | Tác động đến session history | Khi xử lý URL nhạy cảm |
| --- | --- | --- |
| `history.pushState(state, "", url)` | **Thêm** một history entry mới | Không phù hợp để “xóa” token ở entry cũ; Back có thể trở lại entry chứa credential |
| `history.replaceState(state, "", url)` | **Thay** URL/state của entry hiện tại, không thêm entry | Hữu ích để làm sạch callback URL trong SPA sau khi lấy params cần thiết |
| `location.assign(url)` | Điều hướng và thường tạo history entry mới | Back có thể đi tới URL callback cũ tùy flow |
| `location.replace(url)` | Điều hướng thay entry hiện tại, không tạo entry quay về như `assign` | Phù hợp khi chuyển khỏi callback đến route sạch ở browser |
| Server `302`/`303` redirect | Browser thực hiện navigation do server chỉ định | Giảm thời gian callback ở màn hình, nhưng không xóa proxy logs hoặc mọi dấu history |

**`pushState` để “che” một URL có AT không phải cleanup**: nó có thể để URL nhạy cảm ở entry trước, người dùng Back sẽ thấy lại. `replaceState` hữu ích, nhưng chỉ thao tác **entry hiện tại**, cùng origin rules và không đảm bảo xóa mọi bản copy.

### 6.3. Back-button sau logout

Ví dụ Alice mở trang `/payroll` với dữ liệu nhạy cảm, bấm Logout rồi Back. Browser có thể hiển thị **ảnh/DOM cũ** trong một khoảng thời gian dù server-side session đã bị invalidated. Điều cần bảo đảm:

1. **Server session/authorized client token store** bị vô hiệu hóa theo logout policy; request mới không có quyền.
2. Nội dung nhạy cảm được trả với cache policy phù hợp (ví dụ `Cache-Control: no-store`) và không bị shared proxy cache ngoài ý muốn.
3. Với ứng dụng SPA, `pageshow`/navigation visibility và authorization revalidation có thể dùng để **cải thiện UI/privacy** khi quay lại trang; không dùng client-side event làm authorization boundary.
4. Không hứa mọi browser sẽ **không bao giờ** hiển thị snapshot cũ sau Back; bfcache và browser versions có hành vi khác nhau.

### 6.4. bfcache khác HTTP cache

**Back/forward cache (bfcache)** có thể giữ trạng thái document trong bộ nhớ để khôi phục nhanh; **HTTP cache** giữ HTTP responses theo caching rules. `Cache-Control: no-store` giúp chống lưu nội dung nhạy cảm trong HTTP caches, nhưng việc nó ảnh hưởng bfcache có **chi tiết phụ thuộc browser/version/chính sách**, và hành vi hiện đại có thể thay đổi.

Không viết security requirement:

~~~text
Cache-Control: no-store → Back cannot ever show old DOM.
~~~

Thay vào đó, kết hợp:

- Không để credential trong document URL.
- Server/API authorization trên **mỗi request mới**.
- No-store cho dữ liệu/session-sensitive responses khi thích hợp.
- UI reset/reauth khi restore/page show theo app policy.
- E2E tests trên browser mục tiêu, kể cả sau logout.

### 6.5. `pageshow` và `event.persisted`

Ví dụ UI **defense-in-depth**, không phải authentication enforcement:

~~~javascript
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    // This document was restored from a back-forward cache
    // in a browser that reports the event as persisted.
    // Re-check server-side session before displaying sensitive data.
    window.location.replace("/session-status");
  }
});
~~~

Đoạn này chỉ minh họa: route `/session-status` phải có logic server xác thực thật, không được trả data nhạy cảm trước khi revalidation, và ứng dụng phải xử lý cả restore path không kích hoạt `persisted` theo kỳ vọng. Với bfcache snapshot, JS có thể chạy **sau khi browser hiển thị nội dung một khoảnh khắc**; với yêu cầu privacy rất chặt, cần thiết kế UI không chứa bí mật bền trong DOM, hoặc che nội dung khi pagehide theo threat model. Không dựa vào JS để “thu hồi AT đã bị lộ”.

### 6.6. Browser sync, bookmarks và shared device

Người dùng có thể:

- Bookmark/copy URL callback còn `code`.
- Gửi link vào email/chat/ticket trước khi URL sạch.
- Đồng bộ history giữa thiết bị theo cấu hình browser.
- Dùng máy tính công cộng, browser profile chung hoặc thiết bị bị cài extension độc hại.

Các bản sao URL này không nằm trong quyền xóa tuyệt đối của web app. Với token đã đưa vào URL, hãy coi nó **có khả năng bị lộ** và thiết kế TTL, one-time use, sender binding và revocation tương ứng. Không thể hứa “đã gọi `replaceState` nên mọi thiết bị đã quên token”.

## 7. Referer/Referrer-Policy: rò query khác với rò fragment

### 7.1. Khi nào trang callback gửi URL trước đó?

Một document tại:

~~~text
https://portal.example.test/callback?code=C1&state=S1
~~~

nếu tải thêm script/image/link, browser có thể tạo `Referer` header cho request tiếp theo **theo referrer policy, destination và browser rules**. Tên HTTP header được viết lịch sử là **`Referer`** (một chữ `r` bị thiếu), còn response header điều khiển là **`Referrer-Policy`**.

Ví dụ nguy hiểm khi policy cho phép full same-origin referrer:

~~~http
GET /assets/app.js HTTP/1.1
Host: portal.example.test
Referer: https://portal.example.test/callback?code=C1&state=S1
~~~

Nếu asset server/CDN log `Referer` hoặc analytics JS đọc `document.location.href` rồi gửi đi, authorization code có thể rò.

### 7.2. Cross-origin không phải lúc nào cũng nhận full query

Policy mặc định được nhiều browser hiện đại sử dụng là `strict-origin-when-cross-origin`:

- **Same-origin request**: có thể gửi full URL (không fragment) làm Referer.
- **Cross-origin HTTPS → HTTPS**: thường chỉ gửi **origin**, không query/path.
- **HTTPS → HTTP downgrade**: không gửi Referer theo policy này.

Do đó, **không được khẳng định mọi cross-origin request luôn làm lộ full query**. Nhưng cũng **không được dựa vào mặc định browser**: ứng dụng có thể cấu hình `unsafe-url`, browser cũ có behavior khác, hoặc JavaScript analytics có thể gửi full URL **bằng request body**, hoàn toàn vượt ngoài cơ chế Referer.

### 7.3. Các chính sách thường gặp

| `Referrer-Policy` | Hành vi khái quát | Với OAuth callback |
| --- | --- | --- |
| `no-referrer` | Không gửi Referer | Lựa chọn chặt cho callback chứa code/state |
| `same-origin` | Chỉ gửi Referer cho request cùng origin; thường full URL | Vẫn có thể lộ query vào same-origin logs |
| `origin` | Chỉ gửi scheme/host/port, không path/query | Giảm leak URL nhưng vẫn tiết lộ origin |
| `strict-origin-when-cross-origin` | Full URL same-origin; origin cross-origin khi secure; không downgrade | Mặc định phổ biến, chưa đủ để chặn mọi same-origin query leak |
| `unsafe-url` | Có thể gửi full URL rộng hơn, không gồm fragment | **Không phù hợp** cho trang chứa OAuth code |

**Khuyến nghị:** Trang OAuth callback có thể dùng `Referrer-Policy: no-referrer`, và không tải tài nguyên không cần thiết trước khi xử lý callback. Với toàn app, lựa chọn policy theo privacy/UX và threat model; callback thường có yêu cầu nghiêm ngặt hơn.

### 7.4. `Referer` không bao gồm fragment

Nếu URL:

~~~text
https://portal.example.test/callback#access_token=AT1
~~~

browser không gửi `#access_token=AT1` trong header `Referer` chuẩn. **Tuy nhiên**, JS có thể gửi fragment ra ngoài:

~~~javascript
// Anti-pattern: leaking full URL, including a fragment token.
sendAnalyticsEvent({
  page_url: window.location.href
});
~~~

Vì thế **Referrer-Policy không ngăn script đã chạy đọc `location.href`**. Một third-party analytics SDK có thể gửi full page URL kèm fragment do chính script thực hiện.

### 7.5. `rel=noreferrer` và CSP có bổ sung nhưng không thay mọi thứ

Liên kết đến trang khác:

~~~html
<a href="https://docs.example.test/help"
   rel="noreferrer noopener">Trợ giúp</a>
~~~

`noreferrer` giúp tránh gửi referrer trên navigation đó; `noopener` giảm rủi ro tab mới điều khiển opener. Nhưng một page callback OAuth tốt nhất **không hiển thị link/tải third-party script trước khi xử lý code**. CSP có thể giảm script injection/exfiltration; không thay OAuth state/PKCE và không làm an toàn một script không tin cậy đã được cho chạy.

## 8. Redirect chains, open redirects và URL parser khác nhau

### 8.1. Token/code có thể rò qua một registered redirect URI không an toàn

AS chỉ chấp nhận:

~~~text
https://portal.example.test/oauth/callback
~~~

Nhưng RP lại triển khai:

~~~text
/oauth/callback?next=https://attacker.example.test/collect
~~~

nếu callback chuyển hướng sang `next` mà vô tình **giữ code/state** trong URL mới, attacker có thể lấy authorization code. Đặc biệt nguy hiểm nếu RP cho phép wildcard redirect prefix hoặc open redirect tại chính registered redirect URI.

### 8.2. Ví dụ anti-pattern redirect mang nguyên query

~~~java
// VULNERABLE: do not use with callback credential-bearing URLs.
String next = request.getParameter("next");
response.sendRedirect(next + "?" + request.getQueryString());
~~~

Attacker có thể kiểm `next` và nhận query chứa `code`/`state`. Thậm chí khi không ghép query, open redirect còn gây phishing hoặc làm mất issuer/transaction context. Không tin `returnTo`/`next` do browser tự khai để chuyển hướng có credential.

### 8.3. Xác thực đúng redirect URI

Authorization Server nên:

- Đăng ký redirect URI **chính xác** cho client/response type, theo ngoại lệ được chuẩn hóa nếu có (ví dụ native loopback port).
- Dùng HTTPS cho web apps; native app theo RFC 8252 app-link/private-use/loopback profile.
- Không dùng wildcard host/path hoặc substring matching tùy ý.
- Chặn redirects sang URL attacker, scheme `javascript:`, credentials trong userinfo, URL parser ambiguity và double-encoding bypass.
- Ràng buộc code với `client_id`, `redirect_uri`, PKCE và issuer đã dùng trong authorization request.

Một registered redirect URI **không tự bảo vệ** nếu ứng dụng tại đó làm open redirect hoặc tải third-party resources trước khi code được xử lý.

### 8.4. Redirect của HTTP client dùng AT

Không chỉ browser callback. API client/BFF gửi:

~~~http
Authorization: Bearer <access-token>
~~~

đến service A; server trả `302 Location: https://attacker.example.test`. Nếu HTTP client **tự forward Authorization header sang host khác**, AT có thể bị lộ. Sử dụng HTTP client có redirect policy an toàn, không forward credentials qua cross-origin redirects, giới hạn outbound hosts và áp TLS/hostname validation.

### 8.5. `location.replace` không sửa open redirect

Một frontend:

~~~javascript
window.location.replace(userProvidedNextUrl);
~~~

vẫn có thể đưa browser đến attacker origin. `replace` chỉ thay entry lịch sử, **không xác minh URL**. Trước navigation cần chọn destination từ allowlist/same-origin safe relative path; không suy “không có Back nên an toàn”.

### 8.6. Fragments và redirect resolution

Theo URL/HTTP redirect rules, fragment handling khi một `Location` không chứa fragment có thể dẫn đến việc fragment cũ được giữ trong URL đích trong một số trường hợp chuẩn; browser/SDK behavior cần test. Nếu flow dùng legacy fragment token, việc điều hướng qua URL mới **không đương nhiên xóa fragment**. Biện pháp ưu tiên là không phát AT qua fragment và làm sạch URL hiện tại trước các navigations khác.

### 8.7. `state` và OIDC issuer binding chống code injection

Ngay cả khi redirect URI đã đăng ký, attacker có thể cố gắng chèn code/response của authorization transaction khác vào callback. RP phải xác minh:

~~~text
state → original browser authorization transaction
transaction → expected AS issuer, client registration and redirect
transaction → original PKCE verifier and OIDC nonce (if used)
AS → authorization code single-use/client/redirect/PKCE checks
OIDC → verified ID token issuer/audience/nonce/time claims
~~~

Không chỉ xóa query rồi tạo session theo `code`/`sub` tự khai. URL cleanup là **privacy mitigation**, không phải authentication validation.

## 9. URL rò qua hệ sinh thái logs, analytics và observability

### 9.1. Một callback có thể đi qua nhiều lớp ghi log

~~~mermaid
flowchart LR
    B["Browser address bar"] --> CDN["CDN / WAF"]
    CDN --> LB["Load balancer / reverse proxy"]
    LB --> APP["Web app / callback"]
    APP --> APM["APM / tracing / error collector"]
    APP --> ANA["Analytics / frontend SDK"]
    CDN --> LOG["Access logs"]
    LB --> LOG
    APP --> LOG
    B --> HIST["History, copy/share, extensions"]
~~~

Không phải mọi lớp **đều** ghi token mặc định; rủi ro xuất hiện **khi cấu hình log/request capture ghi raw URL hoặc JavaScript tự gửi URL**. Xác định đường dữ liệu thực tế, không dựa vào suy đoán chung “có HTTPS nên không ai thấy”.

### 9.2. Query tokens và proxy access log

Một Nginx log format có thể ghi:

~~~text
GET /callback?code=C1&state=S1 HTTP/1.1
~~~

và một Java/Spring app có thể ghi:

~~~java
// Anti-pattern: logs OAuth credentials.
log.info("Request URI: {}?{}",
        request.getRequestURI(),
        request.getQueryString());
~~~

**Không** dùng raw request query string làm correlation ID. Cần:

- Cấu hình log chỉ ghi safe path hoặc sanitized query.
- Redact keys `code`, `state`, `access_token`, `id_token`, `refresh_token`, `code_verifier` và `client_secret`.
- Áp redaction cả tại CDN, WAF, ingress, reverse proxy, app, APM, browser analytics và debug HTTP clients.
- Không ghi token response body hoặc `Authorization` headers.
- Bảo vệ retention/access của logs có thể đã chứa credential; xử lý như security incident nếu có lộ.

### 9.3. Analytics SDK có thể vượt qua Referrer-Policy

Ví dụ nguy hiểm:

~~~javascript
analytics.track("page_view", {
  url: document.URL
});
~~~

`document.URL` có thể bao gồm query và fragment. `Referrer-Policy: no-referrer` chỉ điều khiển **Referer**, không cấm script gửi `document.URL` qua một POST riêng. Nhiều SDK cho phép **URL scrubbing** hoặc tự loại bỏ query/fragment, nhưng phải **kiểm thử payload mạng thật**.

### 9.4. Error reporting và crash dumps

Khi xử lý token callback lỗi:

~~~text
Error: invalid_grant at
https://portal.example.test/callback?code=C1&state=S1
~~~

nếu exception reporter tự đính kèm URL, C1 đi vào hệ thống hỗ trợ thứ ba. Nên:

- Thay URL bằng route template `/callback` hoặc origin/path đã scrub.
- Dùng correlation ID riêng cho OAuth transaction.
- Chỉ ghi reason code `STATE_MISMATCH`, `PKCE_ERROR` hoặc `INVALID_GRANT` (không raw secrets).
- Giới hạn retention/permissions và kiểm tra integration của error SDK.

### 9.5. Logs của token endpoint cũng nhạy cảm

Chuyển từ Implicit sang Code+PKCE không đủ nếu token endpoint log:

~~~text
grant_type=authorization_code&code=C1&code_verifier=V1
~~~

hoặc HTTP response chứa AT/RT. Back-channel đi qua TLS nhưng **AS, proxy và ứng dụng** vẫn phải redaction. PKCE verifier lộ cùng code làm mất protection against interception. Với confidential client, client secret/private-key JWT cũng cần bảo vệ.

### 9.6. Một quy tắc audit hữu ích

~~~json
{
  "event": "oauth_callback_received",
  "decision": "VALID_STATE",
  "client_registration": "employee-portal",
  "issuer_ref": "company-op",
  "callback_route": "/login/oauth2/code/company",
  "correlation_id": "opaque-event-id",
  "query_redacted": true
}
~~~

Đây là schema minh họa, **không** phải chuẩn OAuth. Không ghi raw code/state/verifier hoặc token value. Nếu cần so sánh events từ cùng transaction, dùng protected random reference hoặc HMAC fingerprint với retention ngắn, tránh đưa credential ra logs.

## 10. Browser scripts, extensions, service workers và clipboard

### 10.1. XSS có thể đọc URL và token trong JavaScript

Nếu access token nằm trong `window.location.hash` hoặc JavaScript storage, một XSS/script độc hại cùng origin có thể đọc nó. `Content-Security-Policy`, output encoding, Trusted Types khi phù hợp, dependency hardening và tránh third-party scripts giúp giảm rủi ro, nhưng **không thay** server-side authorization/token binding. Không giả định “fragment ẩn với backend” đồng nghĩa ẩn với JavaScript.

### 10.2. Third-party scripts có quyền đọc document URL

Khi ứng dụng nhúng:

~~~html
<script src="https://analytics.example.test/sdk.js"></script>
~~~

script thường chạy **trong origin/document của ứng dụng** và có thể gọi `window.location.href`, không được sandbox chỉ vì file JS tải từ host khác. Với OAuth callback, **tránh chạy các scripts không cần thiết trước khi dọn URL**; dùng CSP và privacy review để kiểm soát nguồn scripts.

### 10.3. Browser extensions và thiết bị bị compromise

Một extension được cấp quyền thích hợp có thể quan sát URL hoặc nội dung trang. Web app không thể chặn tuyệt đối extension độc hại đã được người dùng cấp quyền hoặc malware trên thiết bị. Vì vậy giảm **token exposure duration**, dùng scope/audience/TTL hẹp, không đặt RT ở URL, cân nhắc BFF/sender constraint, và hỗ trợ revoke khi nghi credential theft.

### 10.4. Service worker và browser storage

Service worker của origin có thể intercept fetches và tham gia caching theo phạm vi đăng ký. Nếu developer vô tình cache OAuth callback, token endpoint response hoặc HTML chứa credential, có thể giữ dữ liệu quá lâu. Cần:

- Không cache callback/auth/token responses một cách không có chủ đích.
- Phân tách Cache API keys/content theo user/session và tránh lưu bearer credentials.
- Clear caches phù hợp khi logout, nhưng biết rằng xóa cache **không revoke token ở AS**.
- Service worker scripts cần security review vì một script bị compromise có thể duy trì access trong origin.

### 10.5. Clipboard, share UI và screenshot

Một nút “Copy page link” dùng:

~~~javascript
navigator.clipboard.writeText(window.location.href);
~~~

có thể copy cả `?code=C1` hoặc `#access_token=AT1`. Thay bằng **canonical clean URL** được ứng dụng xây dựng từ trusted route, không chứa credential. Trong khi callback chưa hoàn tất, tốt hơn **không có nút share** và không tải full app shell/analytics.

### 10.6. `window.name` và `postMessage`

Không dùng `window.name` hoặc `postMessage("*", token)` để chuyển bearer tokens giữa windows/origins. Cơ chế này có ranh giới origin/navigation khác, có thể bị lộ nếu code không kiểm sender/target origin:

~~~javascript
// Anti-pattern: sends token to any origin receiving message.
otherWindow.postMessage({ accessToken }, "*");
~~~

Nếu một popup OAuth integration cần messaging, hãy dùng **target origin cố định**, kiểm `event.origin`/`event.source`/transaction state, và chỉ gửi **data tối thiểu không chứa bearer credential** khi có thể. Khuyến nghị Code+PKCE và backend-mediated session thay vì giao AT qua cross-window messages tùy ý.

## 11. History API và JavaScript callback cleanup đúng cách

### 11.1. Một callback SPA cần xử lý gì?

Với browser-based OAuth client nhận Authorization Code Flow:

~~~text
1. Browser lands on registered /oauth/callback?code=C1&state=S1.
2. Callback code runs before analytics/third-party scripts.
3. Capture code/state in memory and check source/transaction context.
4. Clean URL using history.replaceState (no new history entry).
5. Validate state, issuer/PKCE transaction and perform code exchange.
6. Validate returned token(s) according to OAuth/OIDC profile.
7. Navigate to clean application route.
~~~

**Thứ tự 3–5** cần được thiết kế cẩn thận. Có thể đọc minimal parameters rồi **làm sạch URL thật sớm**, trước network/token exchange để giảm thời gian query được JS khác nhìn thấy, nhưng phải đảm bảo **transaction context còn trong protected store**; nếu trang reload giữa chừng, user có thể phải bắt đầu authorization mới. Không giữ code trong URL đến khi mọi API request chạy xong chỉ để tiện debug.

### 11.2. Ví dụ JavaScript tối giản để dọn URL

~~~javascript
// Browser SPA callback: demonstration of URL hygiene only.
// Run before initializing analytics, third-party scripts or app shell.
function captureAndCleanOAuthCallback() {
  const current = new URL(window.location.href);
  if (current.origin !== window.location.origin ||
      current.pathname !== "/oauth/callback") {
    throw new Error("Unexpected callback location");
  }

  const code = current.searchParams.get("code");
  const state = current.searchParams.get("state");
  const authorizationError = current.searchParams.get("error");

  // Replace current session-history entry with a stable clean URL.
  // This does NOT remove any server/proxy logs that already exist.
  window.history.replaceState(
    null,
    document.title,
    "/oauth/callback"
  );

  return { code, state, authorizationError };
}

const callback = captureAndCleanOAuthCallback();
// Next: verify original state/issuer transaction and obtain original
// PKCE verifier, then exchange the code at the registered AS endpoint.
// Do NOT log callback.code, callback.state or the verifier.
~~~

Điểm đúng của ví dụ:

- Đọc code/state vào bộ nhớ trước khi xóa query.
- Dùng URL **ổn định, same-origin** thay cho ghép token vào URL mới.
- Không tạo thêm history entry chứa credential bằng `pushState`.
- Không render/analytics/log các giá trị credential.

Điểm **chưa được làm** trong snippet là **OAuth authentication**: `state` chưa được so với transaction, chưa check issuer/redirect/PKCE, chưa gọi token endpoint, chưa validate OIDC ID token hoặc xử lý errors. **Đừng copy riêng snippet rồi coi ứng dụng đăng nhập an toàn**.

### 11.3. Transaction storage của SPA phải phù hợp threat model

Một SPA thường cần lưu original PKCE verifier và OAuth `state` giữa lần khởi tạo `/authorize` và callback. Các lựa chọn:

| Nơi lưu | Lợi ích | Giới hạn |
| --- | --- | --- |
| **In-memory JavaScript state** | Giảm persistent storage | Full-page redirect có thể làm mất memory, cần kiến trúc phù hợp |
| **`sessionStorage`** | Theo tab/origin; thuận tiện qua OAuth redirect | Same-origin JavaScript/XSS có thể đọc; một số browser restore/tab semantics phức tạp |
| **`localStorage`** | Dễ truy cập qua nhiều tabs | Persistent và same-origin JS/XSS có thể đọc; không phải nơi lý tưởng để giữ long-lived bearer/RT |
| **HttpOnly Secure cookie + BFF** | JS không trực tiếp đọc server tokens | CSRF/session riding/XSS actions vẫn có thể xảy ra; cần backend và session protections |
| **Dedicated encrypted server session/transaction store** | Giảm credential exposure tại browser | Cần CSRF protection, integrity/availability, session binding và cleanup |

`sessionStorage` không tự chứng minh code/verifier bí mật với XSS; `HttpOnly` không bảo vệ API khỏi XSS gửi request bằng browser đã authenticated. Chọn theo browser constraints, public/confidential client profile và policy token storage.

### 11.4. Validate state trước khi trao đổi code

Sau khi capture:

~~~text
if authorizationError:
    verify transaction state and handle OAuth error safely
else:
    require code and state are present in expected response mode
    find transaction keyed by protected random state
    require transaction is not expired/consumed
    require issuer/client/redirect match registered values
    obtain original code_verifier (do not generate a new one)
    atomically consume transaction where needed
    POST code + verifier to trusted AS token endpoint over HTTPS
    verify token response and OIDC ID token as required
    create authenticated application state
~~~

Nếu `state` sai, không gọi token endpoint “thử cho biết code của ai”. Nếu callback báo `error=access_denied`, không log full URL hoặc state; hiển thị thông báo chung phù hợp. Error parameters cũng có thể chứa thông tin riêng tư/attacker-controlled text và nên được scrub khỏi URL.

### 11.5. Không tự dùng `location.hash` cho token mới

Đoạn anti-pattern:

~~~javascript
const token = new URLSearchParams(
  window.location.hash.substring(1)
).get("access_token");

localStorage.setItem("token", token);
window.history.replaceState(null, "", "/");
~~~

Nó **đang xử lý legacy implicit token**: AT đã xuất hiện trong browser URL, được JS đọc và giữ trong persistent storage. `replaceState` giảm exposure của history entry hiện tại nhưng **không xóa rủi ro đã xảy ra** hoặc rủi ro XSS lấy AT từ `localStorage`. Migrate sang Code+PKCE và cân nhắc BFF tùy product/risk, không coi snippet này là khuyến nghị.

### 11.6. Khi `replaceState` không được phép hoặc thất bại

History API có **same-origin restrictions**, browser state/privacy policies và có thể throw khi URL không hợp lệ. Không catch exception rồi fallback:

~~~javascript
// Anti-pattern: never append credentials to a new route as fallback.
window.location.href = "/home?token=" + token;
~~~

Khi cleanup không thành công, tránh render third-party resources/analytics, thông báo hoặc chuyển tới route sạch bằng cơ chế an toàn như `location.replace("/home")` nếu transaction handling cho phép. **Không** dùng attacker-controlled next URL.

### 11.7. Không đưa ID token/AT vào React Router/Vue Router state query

Ví dụ:

~~~javascript
// Anti-pattern: token can leak through route/router/history handling.
router.push({
  path: "/dashboard",
  query: { access_token: accessToken }
});
~~~

Ngay cả khi UI framework ẩn query khỏi components, browser URL/history vẫn có thể chứa token. Giữ token ở đúng security context, không trong route state, link props, DOM dataset, window globals hoặc query string. Với BFF, client routing thường chỉ cần session cookie.

## 12. BFF và session cookie: giảm việc browser phải giữ OAuth tokens

### 12.1. Browser-based client trực tiếp so với Backend-for-Frontend

**SPA public client tự giữ tokens:**

~~~text
Browser SPA
  → /authorize with Code+PKCE
  ← authorization code in callback
  → AS /token with verifier
  ← access token (possibly refresh token)
  → API using Authorization: Bearer AT
~~~

Browser JavaScript cần xử lý AT và có thể RT; XSS/scripts độc hại có thể đọc hoặc sử dụng token tùy vị trí lưu. CORS/token endpoint accessibility và public-client PKCE policies phải được AS hỗ trợ.

**BFF/confidential web client:**

~~~text
Browser ── session cookie ──> BFF
                 BFF ── OAuth Code+PKCE ──> AS
                 BFF <── AT/RT ──────────── AS
                 BFF ── Authorization: Bearer AT ──> API
Browser <── app data/session-authenticated responses ── BFF
~~~

AT/RT được BFF lưu ở server-side secure token/authorized-client store, không cần đưa vào browser `location.href`, JS storage hoặc HTML. Đây là **giảm bề mặt exfiltration của raw AT/RT**, không phải loại bỏ toàn bộ rủi ro XSS, CSRF, session theft hay confused deputy.

### 12.2. Cookie là credential của ứng dụng, không phải OAuth AT

Trong BFF:

~~~http
Set-Cookie: __Host-portal-session=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ví dụ sử dụng prefix `__Host-` khi cookie đáp ứng yêu cầu: **Secure**, `Path=/`, không có `Domain`; browser support/prefix semantics cần kiểm. BFF map session ID đến authenticated user và authorized-client token store phía server.

| Thuộc tính | Bảo vệ gì? | Không bảo vệ gì? |
| --- | --- | --- |
| `Secure` | Cookie chỉ gửi qua HTTPS trong ngữ cảnh phù hợp | XSS dùng session để gửi request tới cùng origin |
| `HttpOnly` | JavaScript thông thường không đọc trực tiếp cookie value | XSS gửi authenticated requests hoặc đọc data API cùng origin |
| `SameSite=Lax/Strict` | Hạn chế một số cross-site cookie sends/CSRF | Mọi CSRF scenarios, same-site subdomain threats hoặc XSS |
| `Path=/` và no `Domain` với `__Host-` | Giảm scope/subdomain cookie overriding | Session fixation do server logic, bugs ở backend |
| Server-side session invalidation | Ngăn reuse session ID cũ sau logout | OAuth AT/RT bị đánh cắp độc lập vẫn active tại AS/RS |

### 12.3. BFF không miễn CSRF

Với cookie tự gửi, attacker có thể lừa browser thực hiện request cross-site nếu defenses thiếu. Cần:

- **CSRF token** hoặc Origin/Referer checks phù hợp endpoint/architecture.
- `SameSite` cookie policy được test cross-site.
- CORS chặt, không kết hợp wildcard origin với credentials.
- Chỉ dùng POST/PUT/PATCH/DELETE cho state-changing actions; tránh GET mutate.
- Chống XSS và CSP, vì XSS cùng origin có thể thao tác dưới danh nghĩa user.

**`HttpOnly` làm token ít bị đọc trực tiếp hơn, không ngăn attacker gửi request đã authenticated trong browser của nạn nhân**.

### 12.4. BFF cũng phải xử lý OAuth callback có code trong query

Mặc dù AT/RT ở server, authorization code vẫn có thể đi qua:

~~~text
GET /login/oauth2/code/company?code=C1&state=S1
~~~

Do đó:

- Ingress/backend access logs vẫn phải scrub `code`/`state`.
- Callback không render third-party resources hoặc analytics.
- Spring/security stack xử lý state/PKCE/issuer đúng, rồi redirect route sạch.
- `Referrer-Policy: no-referrer` hoặc policy chặt phù hợp callback.
- Không nhúng access token/ID token vào redirect sau login hoặc vào front-end bootstrap JSON.

### 12.5. BFF token cache và multi-user isolation

Không lưu AT trong singleton:

~~~java
// Anti-pattern: wrong user's AT may be reused by another browser.
private static String latestAccessToken;
~~~

Token store phải phân vùng theo **client registration, issuer, principal/user/service, tenant, resource/audience, scopes và grant/session** khi thích hợp. Mọi request BFF đến API vẫn cần object-level authorization. URL sạch **không** làm an toàn một token cache dùng chung Alice/Bob.

### 12.6. Logout và browser history

Khi logout BFF, hủy **server session** và dọn protected token store; theo AS policy có thể revoke RT/grant. Browser Back có thể hiển thị snapshot cũ, nên protected API phải reject session cũ; có thể dùng no-store/UX restore revalidation. **Xóa cookie không tự thu hồi AT JWT đã phát và còn hạn**, đặc biệt nếu attacker đã lấy AT từ logs trước đó.

## 13. Spring Security: OAuth2 Login, cache/referrer headers và session cookie

### 13.1. OAuth2/OIDC confidential client registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-op:
            issuer-uri: https://auth.example.test
        registration:
          employee-portal:
            provider: company-op
            client-id: employee-portal
            client-secret: INJECT_FROM_SECRET_MANAGER
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

**`INJECT_FROM_SECRET_MANAGER` là placeholder**, không đưa secret thật vào repository. Đây là ví dụ backend confidential OAuth client; SPA/native public client không có static client secret bảo mật và cần Code+PKCE theo public-client profile. `same-site: lax` chỉ là lựa chọn minh họa, phải xét callback mode, cookie domain, CSRF và browser constraints.

### 13.2. SecurityFilterChain mẫu

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

@Configuration
class BrowserSecurityConfiguration {

    @Bean
    SecurityFilterChain browserSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(Customizer.withDefaults());

        // Keep CSRF protection for cookie-based browser sessions.
        http.csrf(Customizer.withDefaults());

        http.headers(headers -> headers
                .referrerPolicy(policy -> policy.policy(
                        ReferrerPolicyHeaderWriter
                                .ReferrerPolicy.NO_REFERRER))
                .cacheControl(Customizer.withDefaults()));

        http.logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
~~~

**Giới hạn của snippet:**

- Đây là Java/Spring Security servlet-style ví dụ; hãy kiểm tra API/chained DSL theo phiên bản thật.
- `oauth2Login` triển khai callback processing, state correlation và token exchange qua framework; **không** tạo thêm MVC callback trùng `/login/oauth2/code/{registrationId}` để exchange code lần nữa.
- `Referrer-Policy: no-referrer` áp rộng cho các responses qua chain; thực tế có thể chọn scope/routing khác theo ứng dụng. Kiểm tra HTTP headers của **callback 302/303, error pages và HTML**.
- `cacheControl` của Spring có defaults/behavior theo phiên bản; verify **`Cache-Control: no-store`** trên các responses chứa thông tin nhạy cảm, không suy tự động mọi static assets cũng phải no-store.
- `deleteCookies("JSESSIONID")` không thay server-side session invalidation hoặc việc xóa cookie tên/path/domain khác. `HttpOnly`/`Secure`/`SameSite` cần xác minh Set-Cookie thực.
- Bật CSRF là defense-in-depth cho cookie session, nhưng cần request/cookie/origin policy phù hợp và kiểm tra các state-changing routes.

### 13.3. Xử lý callback bằng Spring filter thay vì tự viết manual

Spring Security OAuth2 Login thường có route callback:

~~~text
/login/oauth2/code/{registrationId}
~~~

Framework có thể dùng `OAuth2AuthorizationRequestRepository`/session để lưu original authorization request, state và thông tin PKCE phù hợp. **Không tự viết một `@GetMapping` cùng callback URL** rồi lấy `code`, gọi token endpoint, và redirect mang `access_token`. Cần cấu hình PKCE cho client/profile/version đúng và xác minh authorization request thực tế có `code_challenge_method=S256`.

### 13.4. URL sau login không nên mang token/subject

Bad success handler:

~~~java
// Anti-pattern: never send tokens via browser URL.
response.sendRedirect(
    "/dashboard?access_token=" + accessToken);
~~~

Good về mặt URL hygiene:

~~~java
response.setHeader("Cache-Control", "no-store");
response.setHeader("Referrer-Policy", "no-referrer");
response.sendRedirect("/dashboard");
~~~

Đoạn good chỉ minh họa **redirect path sạch**, không thay framework OIDC authentication success handler, session policy hay callback state validation. Nếu app cần return-to path, chỉ dùng protected/same-origin allowlist; không tin arbitrary `next` từ query, và không lặp lại callback `?code=...` làm landing URL.

### 13.5. Callback/response headers

Một callback 302/303 mong muốn:

~~~http
HTTP/1.1 303 See Other
Location: /dashboard
Cache-Control: no-store
Pragma: no-cache
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
~~~

Đây là **minh họa**; CSP cần thiết kế theo script/style/connect/frame dependencies của app, không copy literal gây lỗi UI rồi tắt CSP. `Pragma` là header legacy hỗ trợ các caches cũ, không thay `Cache-Control` hiện đại.

### 13.6. Resource Server riêng vẫn kiểm AT

Ngay cả khi browser URL đã sạch và token ở BFF, `orders-api` vẫn phải kiểm OAuth access token **`iss`, `aud=orders-api`, `exp`, token purpose, scope và object/tenant ACL**. Với opaque token, RS dùng trusted introspection và `active`/audience contract; với JWT ký JWS, RS dùng trusted JWKS và validators. **Browser history hygiene không phải API authorization**.

## 14. Special-purpose URL tokens: signed link, reset link, magic link

### 14.1. Không thể nói “mọi URL có token là luôn sai” mà bỏ ngữ cảnh

Một ứng dụng đôi khi **cần truyền một credential dùng một lần qua link**, ví dụ:

- Email verification link.
- Password reset link.
- Invitation acceptance link.
- Magic login link/transaction challenge.
- Một signed download URL có hạn hẹp.

Đây không phải lý do dùng OAuth AT/RT/ID token như query parameter. Security contract của **action token trong link** phải **hẹp và có thể thu hồi/tiêu thụ**, còn OAuth AT thường đại diện quyền API rộng hơn.

### 14.2. Quy tắc cho one-time action link

| Điều kiện | Vì sao |
| --- | --- |
| Entropy cao, không đoán được | Chống brute force/credential guessing |
| Short TTL | Giảm window khi link bị forward/history/leak |
| Single-use/atomic consume | Link đã dùng không được replay để đổi password/login lần nữa |
| Purpose binding | Token reset password không dùng để verify email hay truy cập API |
| User/account/tenant binding | Không tráo link của Alice cho Bob hoặc tenant khác |
| HTTPS, trusted host, exact route | Tránh downgrade/phishing/open redirect |
| No-store, Referrer-Policy chặt và no third-party scripts | Hạn chế history/log/Referer/JS exposure |
| URL cleanup sau khi mở | Tránh giữ action code trong page URL lâu |
| Rate limiting/monitoring | Giảm thử code và phát hiện abuse |
| Không auto-consume với unsafe side effect chỉ vì GET preview | Tránh link scanner/mail preview tự kích hoạt hành động nhạy cảm |

### 14.3. Link scanners và prefetch

Email security scanners hoặc messaging clients có thể **mở URL trước người dùng** để kiểm an toàn. Nếu một `GET /reset?token=...` **lập tức đổi mật khẩu, login hoặc tiêu thụ token không cho user thực hiện**, scanner có thể làm hỏng flow hoặc gây tác dụng không mong muốn.

Thiết kế thường:

1. GET link chỉ xác minh sơ bộ và hiển thị trang hành động với CSRF/session controls phù hợp.
2. Người dùng có hành động có chủ ý (POST/confirmation) để **consume token atomically**.
3. Sau consume, redirect đến URL sạch; không gửi credential qua form action URL.

Không áp máy móc cho mọi loại one-time link: phải đánh giá link security, abuse/DoS và product UX.

### 14.4. Presigned download URL là bearer-like credential

~~~text
https://files.example.test/download/report.csv?signature=<short-lived-signature>&expires=...
~~~

Một presigned URL có thể được chấp nhận nếu storage provider dùng cơ chế signature, scope hẹp, short TTL, method/resource binding, audit và không dùng được ngoài intent. **Ai có URL trong khoảng hạn có thể truy cập** theo signed URL policy; đây là bearer-like link.

Vì thế:

- Hạn sử dụng và resource/method/quyền thật hẹp; one-time hoặc revocation nếu system hỗ trợ.
- Không dùng một signed URL cho API admin hoặc nhúng RT/AT vào query.
- Không đưa signed links vào analytics/referrer/logs/support tickets.
- Kiểm Content-Disposition/content-type để tránh active content injection.
- Hạn chế link sharing và đánh giá CDN cache/private response behavior.

### 14.5. WebSocket và streaming URLs

Một số browser APIs không cho set custom HTTP Authorization header tùy cách kết nối, khiến developer muốn:

~~~text
wss://stream.example.test/events?access_token=<oauth-at>
~~~

Đây vẫn là URL có credential trong browser/history/proxy/WebSocket handshake logs. Các lựa chọn cần threat-model:

- Dùng same-origin BFF/session cookie cho WebSocket handshake với Origin/CSRF-like controls và authenticated server session.
- Trao đổi OAuth AT (qua HTTPS POST authenticated) lấy **one-time, short-lived, narrowly scoped connection ticket** dành đúng WebSocket endpoint, kiểm/consume tại handshake và không dùng như AT API.
- Không tái sử dụng RT/ID token hoặc full-scope bearer AT trong query.
- Redact handshake URLs và giới hạn lifetime/attempts/replay.

Browser WebSocket cookies và cross-origin behavior khác fetch; cần kiểm `Origin`/cookie session và server authorization, không tự tin “wss là đủ”.

### 14.6. Query token trong image, PDF, video URLs

~~~html
<img src="/private/avatar?token=AT1">
<video src="/videos/payroll?access_token=AT2"></video>
~~~

Các media URLs có thể bị cache, log, copy, preview, CDN fetch hoặc gửi làm Referer trong điều kiện khác. Nên phục vụ media qua authenticated BFF/session/cookies phù hợp hoặc presigned resource-specific URLs cực ngắn nếu kiến trúc yêu cầu. **Không** đặt general-purpose OAuth bearer AT vào `src`.

## 15. Quy trình phản ứng khi phát hiện token/code từng nằm trong URL

### 15.1. Phân loại credential đã lộ

Đầu tiên xác định chính xác **cái gì** xuất hiện trong URL, **ở nơi nào** và **bao lâu**:

| Credential | Khả năng lạm dụng khi bị lộ | Hành động ưu tiên |
| --- | --- | --- |
| Authorization code đã dùng | Không thể đổi lần nữa nếu AS single-use; vẫn là dấu hiệu cấu hình rò | Xác minh PKCE/verifier và code reuse, rà soát logs |
| Authorization code chưa dùng | Attacker có thể cố đổi nếu có verifier/client auth | Chặn leak, giám sát replay, cân nhắc hủy transaction/grant theo AS policy |
| OAuth bearer AT | Có thể gọi RS cho đến khi hết hạn/revoked nếu không sender-bound | Revoke/denylist/status-check theo SLA, giới hạn scope/audience |
| OAuth RT | Có thể xin AT mới theo AS/client binding/rotation policy | **Ưu tiên revoke RT/grant/family**, rotate khi cần, kiểm refresh reuse |
| OIDC ID token | Lộ authentication claims, có nguy cơ cross-token misuse ở ứng dụng lỗi | Chặn disclosure, kiểm RP/token-type validation, expire/issuer policy và privacy response |
| Password reset/magic link | Có thể chiếm quy trình thay đổi password/login nếu còn hiệu lực | Invalidate one-time code, phát lại link qua kênh bảo vệ và yêu cầu confirmation |
| Presigned download URL | Có thể lấy đúng resource đã ký trong window còn hạn | Thu hồi/rotate key/signature theo provider, giảm TTL/scope, kiểm download audit |

**Không** kết luận ID token “không phải AT nên không nhạy cảm”; nó chứa user claims và có thể bị dùng sai ở những hệ thống mắc token substitution. Mức độ incident dựa vào token audience/purpose/TTL/issuer/actual exposure, không chỉ tên query param.

### 15.2. Xác định các đường rò

Một điều tra có thể cần rà:

~~~text
Browser and page:
  - callback URL/history/restore
  - analytics SDK page_view payloads
  - third-party scripts and error reporting
  - service worker/cache/browser storage

Infrastructure:
  - CDN, WAF, ingress, reverse proxy and load balancer logs
  - application request logging and exception traces
  - APM, tracing spans, telemetry vendors
  - token endpoint request/response logging

Human/tooling:
  - copied URLs in chat/email/support tickets
  - screenshots, exports and browser extensions
  - shared workstations and browser sync
~~~

Không đọc/copy raw credential thêm vào ticket để điều tra; dùng controlled incident tooling, token fingerprints và correlation IDs an toàn.

### 15.3. Containment và revocation theo token type

Ví dụ timeline:

~~~text
T0   Security detects access_token in query URL.
T1   Disable route/feature that generates tokenized URL.
T2   Determine issuer, audience, client/grant and exposed logs.
T3   Revoke access/refresh tokens or grants as AS supports.
T4   Check RS acceptance: JWT offline vs opaque introspection cache.
T5   Purge/quarantine exposed logs/caches under approved controls.
T6   Deploy URL hygiene, redaction, no-referrer and E2E tests.
T7   Verify no further token-bearing URLs or outgoing telemetry.
~~~

Với JWT AT được RS xác minh offline, việc thu hồi grant tại AS **không tự làm JWT đã ký hết hiệu lực**; cần TTL/denylist/domain state checks theo security SLA. Với opaque introspection, positive-cache TTL và AS replication có thể làm revocation chậm. Đừng tuyên bố “mọi token đã bị xóa” chỉ vì đã gọi `history.replaceState` hoặc xóa cookie.

### 15.4. Forensic evidence và data minimization

Điều tra cần bằng chứng nhưng không nên phát tán thêm credential:

- Dùng token fingerprint/HMAC hash thay raw bearer trong incident ticket.
- Khoanh vùng log slices theo correlation ID và thời gian, phân quyền đọc chặt.
- Nếu bắt buộc lưu raw credential làm bằng chứng theo chính sách, tách ở restricted evidence storage, không đưa vào tracker/chat chung.
- Xác định người đã truy cập logs, SaaS analytics hoặc link (khi có dữ liệu), không giả định mọi leak đã bị khai thác.
- Retain/purge theo privacy/security/legal requirements của tổ chức và thông báo đúng mức nếu có incident.

### 15.5. Regression controls sau sự cố

Thêm automated tests:

1. Không OAuth AT/RT/ID token trong `Location` response.
2. Không token trong `window.location.search`/`hash` sau callback processing.
3. Access log không chứa `code`/`code_verifier` hoặc raw token.
4. Analytics/error requests không có full callback URL.
5. `Referer` không mang query/fragment credentials theo callback policy.
6. Browser Back/restore không cho request mới bằng credential đã consumed.
7. Token replay/revocation path đáp ứng SLA đã phê duyệt.
8. Không open redirect/token forwarding sang untrusted host.

**Không coi một test frontend “URL trống sau 100 ms” là đủ**. Credential có thể đã đi qua proxy logs trước khi JavaScript chạy, hoặc analytics chạy ở 10 ms đầu.

## 16. Bảy tình huống thực tế: nguyên nhân và cách sửa

### Tình huống A: Access token xuất hiện trong query của trang dashboard

**Bối cảnh:** Một ứng dụng web sau OAuth login redirect:

~~~text
/dashboard?access_token=eyJ...
~~~

Nó dùng query để truyền token giữa backend và frontend. Sau đó người dùng copy URL gửi đồng nghiệp, proxy lưu raw query, token bị replay tại `orders-api`.

**Nguyên nhân:** Dùng navigation URL làm token transport; bearer AT đi vào history, logs, link sharing và có thể Referer.

**Sửa:** Không phát AT vào URL. Với BFF, lưu AT/RT ở protected server-side authorized-client store và dùng session cookie; nếu SPA trực tiếp dùng OAuth, lấy AT qua Code+PKCE token endpoint rồi quản lý token tại client security context thích hợp, không query/hash. Revoke AT/RT đã lộ theo scope/expiry policy.

### Tình huống B: `#access_token` không lên server nhưng vẫn bị lộ

**Bối cảnh:** Legacy SPA dùng Implicit Flow. URL sau login:

~~~text
/callback#access_token=AT1&token_type=Bearer
~~~

Analytics SDK chạy trước callback handler, đọc `window.location.href` rồi gửi page URL đến vendor qua HTTPS.

**Nguyên nhân:** Fragment không xuất hiện trong HTTP request-target hay Referer chuẩn, nhưng **JavaScript đã đọc và gửi nó**. HTTPS bảo vệ kênh đến analytics vendor, không ngăn vendor nhận dữ liệu.

**Sửa:** Migrate sang Authorization Code + PKCE; callback bootstrap tối thiểu không third-party script, xử lý URL sạch sớm và audit analytics payloads. Kiểm tra AT từng lộ và revoke nếu còn hiệu lực; **không chỉ thêm `Referrer-Policy`** vì nó không cấm JS gửi full URL.

### Tình huống C: Browser Back hiển thị thông tin HR sau logout

**Bối cảnh:** Alice logout portal, BFF invalidates session đúng. Khi nhấn Back, browser phục hồi snapshot cũ hiển thị hồ sơ nhân viên; gọi API mới thì 401.

**Nguyên nhân:** UI snapshot/bfcache chưa được kiểm soát, **không nhất thiết** là session còn sống. HTTP cache, bfcache và render state khác nhau.

**Sửa:** Trả no-store cho content nhạy cảm, thiết kế revalidate/reset UI khi restore và hạn chế giữ PII trong DOM; **server authorization** phải từ chối session cũ. Test Back/bfcache trên browser thật và không hứa no-store luôn vô hiệu bfcache ở mọi version.

### Tình huống D: Authorization code rò từ Referer cùng origin

**Bối cảnh:** BFF callback `/oauth/callback?code=C1&state=S1` render template tải `/assets/app.js` trước khi exchange. Same-origin request có:

~~~http
Referer: https://portal.example.test/oauth/callback?code=C1&state=S1
~~~

Asset proxy log header `Referer`, code bị ghi ở kho log khác.

**Nguyên nhân:** Referrer policy mặc định có thể gửi full URL **cho same-origin requests**; callback chứa code được render như một app page.

**Sửa:** Callback backend xử lý và redirect không render app shell; set `Referrer-Policy: no-referrer`, scrub Referer/request-target logs và dùng Code+PKCE/state. Không chỉ dựa vào cross-origin default policy.

### Tình huống E: Redirect URI thành open redirect làm lộ code

**Bối cảnh:** Client đăng ký `/oauth/callback` nhưng endpoint nhận `next=https://attacker.example.test` và redirect giữ nguyên `?code=...` tới next.

**Nguyên nhân:** Ứng dụng có open redirect ở đường nhận credential. AS registration đúng vẫn không chặn ứng dụng tự mang code đến attacker.

**Sửa:** Bỏ arbitrary destination, không forward original query khi redirect, chỉ chọn URL sạch từ allowlist, strict redirect URI matching ở AS, validate `state`/PKCE/issuer. Test URL encoding và redirects cross-origin.

### Tình huống F: Spring OAuth2 Login xong nhưng callback URL còn trong analytics logs

**Bối cảnh:** Ứng dụng dùng `oauth2Login` đúng và chuyển về `/home` sạch. Tuy nhiên WAF ghi `GET /login/oauth2/code/company?code=...&state=...` trước khi request đến Spring.

**Nguyên nhân:** Ứng dụng xử lý OAuth đúng nhưng **lớp ingress đã ghi credential**. Success handler không thể xóa bản log đó.

**Sửa:** Redact ở WAF/ingress/APM, hạn chế người xem logs, thiết lập retention phù hợp; giữ PKCE code one-time và kiểm replay. Không “fix” bằng việc tắt state hoặc gửi code ở một query key khó đoán.

### Tình huống G: Password reset link bị email scanner mở trước

**Bối cảnh:** Email reset link chứa one-time code. Một security scanner mở URL GET để kiểm link, server **consume code ngay lập tức**, người dùng nhận link hết hiệu lực trước khi tương tác.

**Nguyên nhân:** GET link preview có side effect làm hủy credential; không phân biệt **link access** với **user confirmation**.

**Sửa:** Dùng GET hiển thị form/challenge mà chưa thực hiện tác vụ nhạy cảm; POST có CSRF/transaction binding và atomic consume khi user xác nhận. Short TTL, no-store/no-referrer/no-third-party, clean URL và không dùng reset code như OAuth AT.

## 17. Ma trận kiểm thử History và token URL (80 ca)

Hãy thử trên **browser thật** (Chromium, Firefox, WebKit/Safari theo nhóm người dùng mục tiêu) cùng **AS/OP test**, OAuth client test, BFF/SPA test, Resource Server và ingress logging test. Dùng **fake tokens/authorization codes** có giá trị vô hại, không đưa production bearer/RT vào test network captures hoặc screenshots. Test theo **nhóm bề mặt rò**; một unit test kiểm `replaceState` không đủ thay cho network/analytics/back-button tests.

| ID | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| H01 | Server-side Code+PKCE login hợp lệ | Client đổi code một lần, tạo session, browser tới clean route |
| H02 | SPA Code+PKCE callback hợp lệ | SPA capture code/state, URL sạch sớm, verifier đúng, AT không vào URL |
| H03 | OAuth callback `?code=C1&state=S1` tới origin | HTTP request-target **có query**; ingress policy redact log |
| H04 | Legacy implicit `#access_token=AT1` tới origin | HTTP request-target **không có fragment** |
| H05 | JS trên callback đọc `window.location.hash` | Test chứng minh fragment accessible; dùng để phát hiện leak surface |
| H06 | Callback chứa code, `Referrer-Policy: no-referrer` | Follow-up resource requests không gửi `Referer` |
| H07 | Callback same-origin resource với default strict-origin-when-cross-origin | Test xác nhận full same-origin Referer có thể bao gồm query |
| H08 | HTTPS callback sang external HTTPS dưới strict-origin-when-cross-origin | Full query không xuất hiện trong Referer cross-origin theo policy |
| H09 | Legacy callback fragment, browser gửi Referer | Fragment không nằm trong Referer chuẩn |
| H10 | Analytics JS đọc `document.URL` ở trang có fragment AT | Test phát hiện AT trong analytics payload nếu SDK không scrub |
| H11 | Analytics JS đọc `location.href` ở trang callback code | Test phát hiện code/state leak nếu chạy trước cleanup |
| H12 | Callback bootstrap không nhúng analytics trước cleanup | Không có outbound analytics request chứa raw code/fragment |
| H13 | `history.replaceState` thay callback query bằng URL sạch | Current entry URL sạch, không tạo một entry mới |
| H14 | `history.pushState` được dùng để “xóa” code | Negative test phát hiện old entry còn qua Back |
| H15 | `location.replace` đến route sạch sau callback | Không dùng arbitrary attacker destination, không giữ token query |
| H16 | `history.replaceState` với cross-origin URL | Browser từ chối theo same-origin restrictions |
| H17 | URL cleanup code chạy sau khi third-party script đã lấy URL | Test chứng minh cleanup **không thu hồi** data đã gửi |
| H18 | SPA reload giữa lúc đã clean URL nhưng chưa token exchange | Hệ thống khởi tạo lại flow an toàn, không tự tái dùng code |
| H19 | Callback `state` sai/thiếu | RP/SPA không exchange code hoặc tạo authenticated session |
| H20 | OAuth authorization response `iss` sai expected AS trong multi-issuer | RP từ chối issuer mix-up |
| H21 | PKCE verifier không khớp stored S256 challenge | AS từ chối code exchange |
| H22 | Authorization code C1 đã redeemed, Back/refresh callback C1 | AS từ chối replay; RP không mint token lần hai |
| H23 | Browser double-click/reload callback rất nhanh | RP transaction single-flight và AS single-use |
| H24 | Callback `code` từ client khác | AS từ chối client/redirect binding |
| H25 | Callback redirect URI không khớp registration | AS từ chối; không wildcard/open redirect bypass |
| H26 | App success handler đưa AT vào `?access_token=...` | Security regression phải phát hiện; route không được đưa token vào URL |
| H27 | App success handler đưa ID token vào URL fragment | Security regression phát hiện ID token exposure |
| H28 | App đưa RT vào `location.search`, `location.hash` hoặc path | Security regression chặn; RT không lên browser URL |
| H29 | App dùng `encodeURIComponent(AT)` trong query | Vẫn bị coi là credential leak; encoding không giải quyết |
| H30 | App dùng URL path `/download/AT` thay query | Vẫn leak surface ở HTTP request-target/logs |
| H31 | App dùng `userinfo@host` trong URL cho bearer | Không làm credential transport hợp lệ |
| H32 | Browser autocomplete/bookmark/copy chứa OAuth callback | UX/cleanup policy giảm exposure; AS code vẫn one-time/short TTL |
| H33 | Browser session restore sau crash tại callback | Không tự tạo session sai, không mint token từ expired/used code |
| H34 | Browser Back sau logout hiển thị snapshot cũ | Server API/session vẫn từ chối; UI revalidation/privacy test |
| H35 | bfcache restore phát `pageshow.persisted` | UI reset/revalidate theo app policy, không dùng event làm authz |
| H36 | Browser khác không báo `persisted` như kỳ vọng | Server authz vẫn là nguồn quyền |
| H37 | Protected response có `Cache-Control: no-store` | HTTP/shared cache không giữ nội dung nhạy cảm trái policy |
| H38 | Có no-store nhưng browser vẫn hồi sinh snapshot bfcache theo behavior/version | Không claim no-store xóa mọi UI history; test browser-specific |
| H39 | `Referrer-Policy: unsafe-url` trên OAuth callback | Test phải phát hiện nguy cơ full query leak |
| H40 | `Referrer-Policy: same-origin` trên callback | Kiểm tra same-origin resource request vẫn có thể mang query trong Referer |
| H41 | `rel=noreferrer noopener` trên link ngoài callback | Link không gửi referrer theo policy; tab mới không dùng opener |
| H42 | Client script gọi `postMessage({AT}, "*")` | Test phát hiện credential leak, không dùng wildcard recipient |
| H43 | Trusted popup messaging thiếu `event.origin`/`event.source` | Reject untrusted message, không nhận code/token theo nguồn lạ |
| H44 | Third-party script chạy trong same-origin page | Test threat model cho thấy script có thể đọc URL/DOM, CSP/source review cần |
| H45 | XSS vào callback trước URL cleanup | Test/secure coding ngăn đọc code/state/token; chống script injection |
| H46 | Browser extension có quyền đọc URL | Không giả định JS/fragment private khỏi extension; TTL/revoke threat model |
| H47 | Service worker cache callback request có `?code=...` | Cache config không lưu hoặc chia sẻ secret-bearing request |
| H48 | Service worker cache token endpoint response | Bị chặn bởi caching policy; không lộ AT/RT qua Cache API |
| H49 | Shared CDN cache protected HTML với user-specific data | Không trả Alice data cho Bob qua shared cache |
| H50 | Ingress/reverse proxy logs raw OAuth `code` | Redaction test phải phát hiện và sửa |
| H51 | Ingress ghi `Referer` chứa `?code=C1` | Log scrub `Referer`/query nhạy cảm |
| H52 | APM capture token endpoint `code_verifier` | Redaction: verifier/secret không xuất hiện trong traces |
| H53 | Error reporter gửi full callback URL | Error SDK scrub route và fields; không gửi code/state |
| H54 | Analytics page_view gửi full URL sau callback cleanup | Không mang credential; kiểm network thật |
| H55 | Browser clipboard “Copy link” trước cleanup | Không cho copy raw credential-bearing URL; chỉ canonical URL khi hợp lệ |
| H56 | Browser screenshot/export bị lộ URL | UX giảm URL exposure, incident controls khi đã rò |
| H57 | Registered redirect URI có `next=https://attacker.example.test` | Không forward code/state/AT tới attacker |
| H58 | `next` double encoding hoặc scheme-relative URL `//attacker...` | Allowlist/parser từ chối bypass |
| H59 | Client nhận `Location` từ API host lạ khi gửi AT | HTTP client không forward `Authorization` cross-origin |
| H60 | Multi-AS RP chọn token endpoint từ browser query | Reject; chỉ dùng trusted issuer registration |
| H61 | Legacy Implicit Flow trả `access_token` trong fragment | Security review phát hiện flow legacy; migration Code+PKCE |
| H62 | OIDC hybrid/form_post nhận code/ID token qua POST | Không có token trong URL; vẫn verify state/nonce/issuer/body logging |
| H63 | Token endpoint trả AT/RT, proxy ghi response body | Redaction/no-store policy phát hiện và ngăn |
| H64 | BFF session cookie có `Secure`/`HttpOnly` đúng | Browser nhận cookie bảo vệ phù hợp |
| H65 | Session cookie `SameSite` không phù hợp callback mode | E2E test phát hiện login loop/missing transaction |
| H66 | BFF session cookie có prefix `__Host-` đúng attributes | Browser enforce prefix semantics nơi hỗ trợ |
| H67 | BFF cookie session, CSRF POST thiếu token | Server từ chối state-changing request |
| H68 | XSS cùng origin gửi authenticated request dù cookie HttpOnly | Test chứng minh HttpOnly không thay XSS/CSRF defenses |
| H69 | BFF token cache dùng một `latestToken` chung user | Security test phát hiện cross-user/tenant token substitution |
| H70 | Logout local BFF session, refresh token còn tại AS | Test phân biệt local logout với AS token revocation |
| H71 | Password reset GET bị mail scanner mở | Không tự consume code hoặc đổi mật khẩu chỉ do GET preview |
| H72 | Reset code chưa dùng hết TTL được mở bởi đúng user | User xác nhận action qua protected POST; consume atomic một lần |
| H73 | Password reset link đã dùng/expired bị mở lại | Không thực hiện thêm action |
| H74 | Magic link/reset code trong Referer/third-party script payload | No-referrer/no-third-party/redaction protections có hiệu lực |
| H75 | Presigned download URL quá rộng/TTL dài | Policy test chặn blast radius, audit sharing |
| H76 | Presigned URL hết hạn hoặc sai method/resource | Storage/provider reject |
| H77 | WebSocket query chứa long-lived OAuth AT | Security regression phát hiện; dùng BFF/session hoặc short-lived ticket |
| H78 | WebSocket one-time connection ticket được dùng lại | Server từ chối replay và kiểm target/TTL/session |
| H79 | Token/code đã lộ và bị revoke, RS JWT verify offline | Test xác minh revocation lag theo RS policy/TTL/denylist |
| H80 | Production metrics/logs chứa raw AT/RT/ID token, `state`, PKCE verifier hoặc PII | Security redaction test phát hiện và chặn |

### 17.1. Positive control trước các negative tests

Một negative test “Code ở history không được dùng lại” chỉ hữu ích nếu **lần đổi code đầu tiên thật sự thành công**:

~~~text
Positive:
  Create C1 from expected AS and client with PKCE S256.
  Callback state and issuer valid.
  Token endpoint issues AT once.
  Browser ends on clean /dashboard.

Negative:
  Navigate back/reload C1 callback URL.
  AS returns invalid_grant (one-time code used).
  RP does not issue a second AT/RT, does not login wrong user.
~~~

Nếu cả hai lần đều fail vì issuer URI sai, chưa chứng minh replay protection hoặc URL hygiene.

### 17.2. Test Referer cần phân biệt same-origin và cross-origin

~~~text
Start at:
  https://portal.example.test/callback?code=TEST_CODE

Test A: no-referrer policy:
  fetch same-origin /assets/app.js
  expect no Referer header

Test B: strict-origin-when-cross-origin policy:
  fetch same-origin /assets/app.js
  full callback URL may be present as Referer

Test C: strict-origin-when-cross-origin policy:
  fetch https://analytics.example.test/pixel
  expect only origin, not full query, as Referer

Test D: analytics JS explicitly sends location.href:
  despite Referrer-Policy, request body may contain full URL.
~~~

**Đọc network requests/headers đã gửi thật** trên browser target; đừng dùng giả định “Referrer-Policy no-referrer đã bật” từ config file mà không test callback/error response headers.

### 17.3. Test history API và Back navigation

~~~text
1. Browser lands on /oauth/callback?code=C1&state=S1.
2. SPA captures parameters and calls replaceState to clean /oauth/callback.
3. Ensure current location.search does not contain code/state.
4. Navigate to /dashboard without adding token query/fragment.
5. Use Back/Forward and inspect page URL/session behavior.
6. Check old C1 cannot be used for fresh token issuance.
7. Verify proxy/access/analytics logs never captured raw secrets.
~~~

Đừng mong browser history UI, internal sync/restore và `history.replaceState` luôn có semantics identical trên mọi browser; test trên phiên bản được hỗ trợ. Quan trọng hơn, code phải **one-time/short TTL** và không có AT/RT trong URL.

### 17.4. Test callback **trước** khi analytics chạy

Một Playwright-like pseudotest:

~~~javascript
// Pseudocode: use fake test credentials only.
const browser = await launchTestBrowser();
const page = await browser.newPage();
const suspicious = [];

page.on("request", (req) => {
  const u = new URL(req.url());
  // Do NOT store raw code/token values in test logs.
  const observedSensitiveQuery =
      ["access_token", "refresh_token", "id_token"]
          .some((name) => u.searchParams.has(name));
  const observedFragmentLikePayload =
      req.postData()?.includes("TEST_AT_FRAGMENT") ?? false;
  if (observedSensitiveQuery || observedFragmentLikePayload) {
    suspicious.push({ host: u.host, path: u.pathname });
  }
});

await page.goto("https://portal.example.test/test-login");
await performTestOidcLogin(page);
await expect(page).toHaveURL(/\/dashboard$/);
expect(suspicious).toEqual([]);
~~~

Đây là **pseudocode**, không phải script chạy được ngay; `launchTestBrowser` và `performTestOidcLogin` là test harness giả định. Trong test thật, **không log raw URL/postData**, nhưng nên kiểm payload của analytics/Error SDK và Referer headers bằng instrumentation an toàn. Token endpoint requests có thể chứa authorization code/verifier trong **request body** theo OAuth; test cần phân biệt **expected authorized-channel traffic** với leakage đến **untrusted endpoints/logs**.

### 17.5. Test sau logout: API server, không chỉ giao diện

~~~text
Login → GET /payroll succeeds for Alice.
Logout → BFF invalidates server session and clears token store.
Back → browser may display cached/snapshot UI.
New GET /api/payroll using old session → rejected.
~~~

Không chỉ assert `document.body` có dòng “Đã đăng xuất”. Một UI sạch không chứng minh bearer AT bị AS revoke; một snapshot cũ chưa chắc chứng minh server session còn hiệu lực. Kiểm **both** bằng browser và server request.

### 17.6. Test one-time links bị scanner truy cập

~~~text
Generate password-reset token R1 with short TTL.
Simulate email scanner GET /reset?code=R1.
Assert R1 is not consumed and no password change occurs.
User opens link and submits protected confirmation POST.
Assert R1 is consumed once; password change only once.
Repeat GET/POST with R1 → rejected.
~~~

Ngoài functional tests, inspect response headers, query redaction, no third-party scripts và history cleanup. Đây là **password reset token lifecycle**, không được dùng R1 làm OAuth AT.

## 18. Giám sát và quy trình chuyển đổi an toàn khỏi token URL

### 18.1. Chỉ số phát hiện credential nằm trong URL

| Metric minh họa | Đo gì? | Lưu ý bảo mật |
| --- | --- | --- |
| `browser_oauth_callback_total` | Số callbacks theo issuer/client/response mode | Không log code/state raw |
| `oauth_url_sensitive_parameter_detected_total` | Request có key như `access_token`/`refresh_token` trong query/path | Chỉ ghi **reason/route**; không ghi value |
| `oauth_callback_url_cleanup_failure_total` | `replaceState`/redirect cleanup thất bại | Phân biệt app/browser versions |
| `oauth_callback_state_invalid_total` | Callback không khớp transaction | Phát hiện mix-up/CSRF hoặc session state bug |
| `oauth_authorization_code_reuse_total` | Code bị đổi lại sau lần đầu | AS single-use, Back/retry/malicious replay |
| `browser_token_in_analytics_total` | Phát hiện token markers ở outbound analytics test/telemetry | Dùng fake test markers/controlled scanner, không thu raw token |
| `browser_referrer_sensitive_query_total` | Referrer chứa các sensitive query keys | Scrub trước metric aggregation |
| `browser_bfcache_session_restore_total` | Lượt trang được restore theo browser support | Không suy từ số lượng này rằng data đã bị lộ |
| `session_reuse_after_logout_total` | Session ID cũ bị thử dùng | Server authz phải từ chối |
| `token_revocation_visibility_seconds` | Từ revoke ở AS đến RS reject AT | Phụ thuộc JWT/opaque/cache/TTL |
| `presigned_url_expired_access_total` | Truy cập signed links đã hết hạn | Dùng cho resource-specific URL policy |

Các metrics là **ví dụ thiết kế**, không phải tên metric chuẩn của Spring hay OAuth. Không đưa JWT claims, `sub`/email, code, verifier, raw URL hoặc session ID vào metric labels. Hãy sử dụng route templates, registered issuer/client IDs, reason codes và correlation IDs không bí mật.

### 18.2. Alert hữu ích

Một số alerts đáng cân nhắc:

- Browser app bắt đầu phát `?access_token=...` hoặc `#refresh_token=...` sau deployment.
- Callback URLs có raw query xuất hiện trong WAF/APM/error logs sau khi bật tracing.
- Thời lượng từ callback đến URL cleanup tăng bất thường do script/error trước bootstrap.
- Reused authorization codes tăng sau khi gateway bật automatic retry.
- OAuth callback nhận request từ unregistered redirect hoặc `state` không khớp tăng.
- Số analytics requests có URL chứa `code`/`id_token`/`access_token` trong synthetic test vượt 0.
- Token đã revoked tiếp tục được RS chấp nhận ngoài freshness SLA.
- Protected pages được served từ shared cache giữa users hoặc BFF session invalidation không lan tới mọi replicas.

**Định nghĩa alert trên hành vi và ranh giới**, không giám sát bằng cách gom raw token vào dashboard.

### 18.3. Quy trình migration từ Implicit Flow

Giả sử một SPA hiện dùng `response_type=token` và AT được trả qua fragment.

1. **Inventory** toàn bộ OAuth clients, callback routes, AS profiles, redirect URIs, scopes, AT/RT TTL và APIs.
2. **Đăng ký Authorization Code + PKCE** cho browser public client hoặc chọn BFF/confidential backend khi phù hợp threat model.
3. **AS** yêu cầu PKCE S256, strict redirect URI, state/issuer binding, short-lived one-time code.
4. **Browser callback** xử lý code/state an toàn, bỏ external scripts/analytics trước cleanup.
5. **Token endpoint** phát AT đúng recipient/audience, với public client CORS/client authentication settings tương ứng.
6. **Token storage** theo browser/BFF architecture: không mang AT/RT qua route, JS URL hoặc full app URL.
7. **Logs** tại AS, WAF, ingress, proxy, application, analytics và error reporter được scrub.
8. **CSP/headers** và callback no-store/no-referrer được kiểm thực tế.
9. **Negative tests**: wrong state/verifier/issuer, duplicate callback, Back/history, analytics leak, bearer replay/RT storage.
10. **Canary/rollback** không được khôi phục Implicit Flow hoặc nhúng AT vào URL như “temporary fallback” khi Code+PKCE gặp lỗi.

Một ứng dụng có thể giữ Implicit Flow tạm thời vì compatibility với một hệ thống cũ. Khi đó cần **risk acceptance có thời hạn, kế hoạch migration và controls bổ sung**, không gọi fragment “an toàn tương đương back-channel token delivery”.

### 18.4. Quy trình migration từ query bearer token sang BFF

~~~text
Before:
  Login response → /dashboard?access_token=AT
  Browser JS → API using AT.

After:
  Browser → BFF Code+PKCE/AS
  BFF stores AT/RT server-side
  Browser receives session cookie only
  Browser → BFF authenticated requests
  BFF → API with audience-bound AT in Authorization header
~~~

Lưu ý security change khi migration:

- BFF trở thành trust boundary có thể lưu RT/AT; cần server token store encryption/access control.
- Session cookie cần `Secure`, `HttpOnly`, `SameSite` phù hợp, CSRF protections và session fixation control.
- BFF token cache phải phân tách user/session/tenant/resource.
- Session logout/revocation phải có semantics rõ; browser Back/bfcache vẫn cần test.
- Cross-origin API architecture có thể đổi; đánh giá CORS, cookies, WAF và audit.

### 18.5. Chặn phát sinh URL chứa credential ngay trong code review

Patterns cần gắn warning:

~~~text
redirect("/dashboard?token=" + value)
window.location.href = "...?access_token=" + token
router.push({ query: { access_token: ... } })
document.location.hash = "refresh_token=" + rt
<img src={"/private?token=" + accessToken} />
<a href={"/download?jwt=" + accessToken} />
postMessage({ token: accessToken }, "*")
log.info("url={}", request.getRequestURL()+query)
~~~

Static grep/lint rules giúp phát hiện, nhưng **không thể hiểu hết** indirect URL builders, encrypted token param names, SDK redirects, presigned URLs, request logging và cache. Kết hợp code review, browser E2E tests và network payload inspection.

### 18.6. Bảo mật không chỉ là “ẩn URL”

Một trang có URL sạch nhưng:

- AT đang nằm trong localStorage,
- ID token đang ở DOM attribute,
- RT bị gửi trong telemetry,
- session cookie bị XSS session riding,
- gateway forward token sai audience,
- server-side token cache dùng chung users,

thì vẫn chưa an toàn. **History hygiene là một lớp trong token-security lifecycle**: cần AS issuance, RS claims validation, client storage, revocation, replay prevention, CSP, CSRF và domain authorization phù hợp.

## 19. Checklist production: Browser history và token URL

### 19.1. OAuth/OIDC protocol

1. **Flow:** Có dùng **Authorization Code + PKCE S256** thay Implicit cho ứng dụng mới khi profile hỗ trợ?
2. **Redirect:** Registered redirect URI có strict matching/HTTPS phù hợp và không open redirect?
3. **State:** Callback được gắn vào original browser authorization transaction bằng `state`?
4. **PKCE:** Verifier gốc được client lưu bảo vệ, không nằm trong authorization URL/logs?
5. **Issuer:** Multi-AS RP không lấy token endpoint từ browser/untrusted issuer input; OIDC/response issuer binding đúng?
6. **OIDC:** RP verify ID token `iss`, `aud`, `exp`/`nonce` và `azp` khi áp dụng?
7. **Single-use:** Authorization code short TTL và chỉ redeem thành công một lần, kể cả retry/Back?
8. **Purpose:** AT/RT/ID token không bị dùng lẫn nhau, RS chỉ chấp nhận đúng AT audience/scope?
9. **Resources:** AT issued đúng resource/audience, scopes và client/tenant policy, không dùng một bearer token cho mọi API?

### 19.2. URL, history, navigation và browser lifecycle

10. **AT trong URL:** Không có OAuth bearer AT ở query, path, fragment, userinfo hoặc route params?
11. **RT trong URL:** Không có refresh token trong browser navigation, logout URI, image/video src hoặc download link?
12. **ID token:** Không đưa ID token vào app URLs/analytics; OIDC logout hint cần riêng security review nếu dùng?
13. **Callback cleanup:** SPA đọc minimal response rồi `replaceState`/clean navigate sớm trước analytics?
14. **Server callback:** BFF/Spring callback xử lý code server-side và redirect route sạch, không lặp `?code=...`?
15. **History API:** Không dùng `pushState` để giấu một entry có credential; `replaceState` không bị hiểu là xóa mọi log/history?
16. **Back/Forward:** Browser Back/Forward sau login/logout không tạo session sai hoặc token mới từ code đã dùng?
17. **Session restore:** Có test crash/reopen tab chứa callback URL và expired/consumed code?
18. **bfcache:** UI nhạy cảm có revalidation/reset khi restore, server authz vẫn enforce kể cả có snapshot cũ?
19. **Copy/share:** Nút share/bookmark/copy lấy canonical clean URL, không copy callback/token URL?
20. **Redirect chains:** Không có URL parser/double-encoding/`next`/`returnTo` bypass mang credential sang attacker origin?

### 19.3. Referrer, caching, scripts và observability

21. **Referrer-Policy:** Callback/test pages có policy phù hợp (thường `no-referrer`), đã test same-origin/cross-origin requests?
22. **Fragment:** Nhóm phát triển hiểu fragment **không** vào HTTP request/Referer nhưng có thể bị JS/history đọc?
23. **No-store:** Responses chứa credential/PII có cache headers đúng và không bị shared cache sai?
24. **CSP:** Script sources/cross-origin messaging được giới hạn, XSS controls được kiểm?
25. **Early scripts:** Callback không load third-party SDK trước URL cleanup; analytics không thu raw `location.href`?
26. **Service worker:** Không cache callback/token responses hoặc dùng offline cache chung users?
27. **Ingress:** WAF/CDN/load balancer/reverse proxy logs đã scrub request query và Referer nhạy cảm?
28. **Application logs:** Không log raw `getQueryString()`, `Authorization`, tokens, code/verifier hoặc RT?
29. **APM/errors:** Traces, error reporters, browser telemetry và crash dumps không ghi full callback URL/body?
30. **Retention:** Historical leaked logs/tickets/analytics có access restrictions và cleanup/incident plan?
31. **Header tests:** `Referrer-Policy`/`Cache-Control`/`Set-Cookie` được kiểm trên **responses thực tế**, không chỉ có config?

### 19.4. Sessions, BFF và API

32. **BFF:** Nếu dùng, AT/RT lưu protected server-side, không đưa ra JS/HTML/navigation?
33. **Cookie flags:** Cookie session `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain` được thiết kế/test phù hợp?
34. **CSRF:** State-changing browser requests có CSRF/Origin defenses; không xem SameSite/HttpOnly là đủ?
35. **Session isolation:** Token cache phân vùng user, tenant, client/issuer, audience/resource, scope, grant?
36. **Logout:** Hủy server session thật; RT/grant revocation theo policy riêng, không suy URL cleanup = revoke?
37. **RS:** Kiểm JWT/opaque AT issuer, signature/`active`, audience, expiry, scope và domain ACL?
38. **AT leak:** Có cơ chế revoke/denylist/status check hoặc TTL phù hợp khi AT còn hạn nhưng bị lộ?
39. **Redirect clients:** HTTP clients không forward bearer `Authorization` sang untrusted redirect host?
40. **Extensions/shared devices:** Threat model xét browser extensions/history sync/clipboard và privacy sensitivity?

### 19.5. One-time links và kiểm thử

41. **Reset/magic links:** Short TTL, entropy, one-time, purpose/user binding, no-store/referrer policy?
42. **Mail scanning:** GET preview không tự thực hiện unsafe action hoặc consume reset code làm hỏng flow?
43. **Signed URLs:** Presigned links hẹp scope/method/resource/expiry, không dùng full OAuth AT làm signature query?
44. **WebSocket:** Không đưa long-lived bearer AT vào handshake URL; có one-time ticket/BFF alternative nếu cần?
45. **Browser matrix:** E2E tests trên browsers được hỗ trợ cho callbacks, Referer, Back/bfcache, restore và logout?
46. **Network leak tests:** Có test khẳng định **không** credential tới analytics/APM/untrusted endpoints?
47. **Positive controls:** Test valid Code+PKCE thành công trước khi test token leak/replay/sai state?
48. **Incident drills:** Khi token URL leak, có playbook xác định exposure, revoke và kiểm RS revocation freshness?
49. **Migration:** Không fallback sang Implicit hoặc `?access_token=...` chỉ để chữa lỗi compatibility?
50. **Security ownership:** AS, RP/BFF, RS, ingress, analytics và SRE đều biết họ chịu trách nhiệm đoạn nào của URL/token lifecycle?

## 20. Câu hỏi tự kiểm tra, tài liệu chuẩn và kết luận

### 20.1. Hai mươi câu hỏi tự kiểm tra

**Câu 1. Query và fragment trong URL khác nhau thế nào khi browser gửi request?**

**Query** là một phần request-target tới origin và có thể xuất hiện trong proxy/server logs; **fragment** không được gửi trong HTTP request-target, nhưng browser/JavaScript/history vẫn có thể đọc. Cả hai đều không phải nơi an toàn để lưu bearer AT/RT.

**Câu 2. Nếu `#access_token` không gửi lên server, tại sao Implicit Flow vẫn rủi ro?**

Vì fragment hiện ở browser URL và JavaScript `location.hash`/`location.href` có thể đọc. Third-party scripts, analytics, XSS, browser extensions, copy/share và session restore có thể làm lộ AT. Với hệ thống mới, ưu tiên Code+PKCE.

**Câu 3. `Referrer-Policy: no-referrer` có ngăn JavaScript gửi full URL tới analytics không?**

**Không.** Nó kiểm header HTTP `Referer` của navigation/requests theo policy; script đã chạy vẫn có thể đọc `window.location.href` và gửi bằng POST/fetch riêng. Cần callback không third-party scripts trước cleanup, CSP và URL scrubbing ở telemetry.

**Câu 4. Browser có gửi fragment trong `Referer` header chuẩn không?**

**Không.** Fragment phải bị loại khỏi Referer. Nhưng điều này không khiến fragment ẩn khỏi same-origin JavaScript, browser history hoặc analytics tự đọc URL.

**Câu 5. Với `strict-origin-when-cross-origin`, request HTTPS tới origin khác có luôn lộ full callback query không?**

**Không.** Trong trường hợp HTTPS→HTTPS cross-origin theo policy này, thường chỉ **origin** được gửi. Same-origin requests vẫn có thể gửi full URL; browser policy/custom scripts khác vẫn có thể tạo leak. Không dựa vào một mặc định để bỏ no-referrer trên callback.

**Câu 6. Tại sao Authorization Code + PKCE vẫn có `code` trong callback URL?**

Authorization Code Flow đưa **short-lived, one-time code** qua browser redirect rồi đổi token qua token endpoint, ràng buộc client/redirect/PKCE. AT không cần ở navigation URL. Code vẫn phải được bảo vệ khỏi logs/referrer/open redirects và cleanup.

**Câu 7. Nếu authorization code đã dùng, có thể coi callback query rò là không cần xử lý?**

Không. AS phải reject reuse, nhưng leak cho thấy hạ tầng có thể đang ghi **state, verifier, AT/RT hoặc request metadata** khác. Cần kiểm đường rò, redaction, code replay telemetry và exposure thực tế.

**Câu 8. `history.replaceState` làm gì?**

Nó thay URL/state của **session-history entry hiện tại** mà không thêm entry mới. Hữu ích để làm sạch callback URL trong SPA, nhưng không xóa server/proxy logs, mọi browser sync/history bản sao hoặc credential đã gửi tới analytics.

**Câu 9. Tại sao `history.pushState` không phù hợp để “xóa” token query?**

Vì nó thêm một entry mới; entry cũ có thể vẫn chứa token và được mở lại bằng Back. Dùng `replaceState`/clean navigation phù hợp, không để AT/RT vào URL ban đầu.

**Câu 10. `location.replace("/home")` có ngăn open redirect không?**

Không. `replace` chỉ ảnh hưởng navigation history entry. Nếu destination do user nhập là attacker URL, đó vẫn có thể là open redirect/phishing. Chọn destination từ same-origin safe paths/allowlist.

**Câu 11. `Cache-Control: no-store` có bảo đảm browser Back không bao giờ hiển thị trang nhạy cảm cũ không?**

Không bảo đảm trên mọi browser/version vì **bfcache** và HTTP cache khác nhau. No-store vẫn quan trọng, nhưng cần server-side session invalidation/API authz, UI revalidation và test browser cụ thể.

**Câu 12. Tại sao một OIDC callback không nên tải analytics trước khi xử lý?**

Analytics SDK có thể đọc full URL chứa `code`/`state` hoặc fragment token và gửi đi trước cleanup. Callback nên tối giản, xử lý transaction, làm sạch URL rồi mới render phần ứng dụng cần thiết.

**Câu 13. HttpOnly session cookie trong BFF có loại bỏ mọi XSS risk không?**

Không. HttpOnly ngăn JS đọc cookie value trực tiếp, nhưng XSS vẫn có thể gửi authenticated requests và đọc data cùng origin. Cần CSP, output encoding, CSRF/Origin defenses, domain ACL và token store isolation.

**Câu 14. BFF có làm authorization code biến mất khỏi browser redirect không?**

Không. BFF vẫn nhận `code`/`state` ở callback query theo Code Flow; khác biệt là **AT/RT ở server**, không chuyển ra JavaScript/URL. Logs tại ingress/backend vẫn phải scrub callback query.

**Câu 15. Nếu Spring `oauth2Login` đúng, còn cần cấu hình WAF log redaction không?**

Có. WAF/proxy có thể ghi request URL **trước khi Spring filter xử lý**. Success handler redirect sạch không xóa log đã tồn tại. Cần defense-in-depth trên mọi hop.

**Câu 16. Password reset token trong URL có bị cấm giống OAuth AT không?**

Đó là use case khác: one-time action link có thể cần URL, nhưng phải short TTL, purpose/user binding, atomic single-use, no-store/no-referrer, log redaction và user confirmation. Không biến reset link thành general-purpose bearer access token.

**Câu 17. Email security scanner mở reset link bằng GET có thể gây lỗi gì?**

Nếu server consume token hoặc thay password ngay khi GET, scanner có thể thực hiện action trước user và làm link hết hiệu lực. Thiết kế GET an toàn, POST/confirmation để consume theo policy.

**Câu 18. Presigned download URL có thể xem như bearer credential không?**

Có. Trong window còn hạn, ai giữ URL có thể truy cập theo signature/resource policy. Giới hạn TTL, object/method/permission scope và audit; không dùng OAuth AT/RT full-scope làm query token.

**Câu 19. Dùng `Authorization: Bearer` trong API request đã giải quyết hoàn toàn token theft chưa?**

Không. Header tốt hơn query URL cho transport theo OAuth, nhưng AT vẫn cần TLS, log redaction, safe client storage, issuer/audience/scope validation, revocation và sender constraint nếu yêu cầu.

**Câu 20. Khi phát hiện AT từng xuất hiện trong history/log, bước ưu tiên là gì?**

Xác định token type/issuer/audience/TTL và phạm vi exposure; ngăn tạo URL mới có token, revoke/denylist/state-check theo AS/RS policy, kiểm logs/analytics/referrer/caches, rồi thêm regression tests. **Xóa URL hiện tại không tự thu hồi bearer token đã lộ.**

### 20.2. Tiêu chuẩn và tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code, Implicit Grant lịch sử, redirect URI, authorization response và token endpoint.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, form/query token transport, nguy cơ URL query và token leakage; query usage không được khuyến khích.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `code_challenge` và S256; chống authorization code interception.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth browser flows, authorization code security, redirect URI/issuer protections, refresh-token replay và bearer risk.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): External browser, registered native redirect URI, PKCE và URI-scheme considerations.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): Authorization response `iss`, issuer binding và mix-up mitigations.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): Requesting resource-bound AT và audience restriction.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Cross-JWT confusion, issuer/audience/type validation và JWT transport risk considerations.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT AT audience/type/claims, không thay access-token storage/URL hygiene.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Opaque AT active status, metadata và revocation-state freshness.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Thu hồi AT/RT tại AS, khác việc xóa browser history.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449), [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705): Sender-constrained AT giảm một số rủi ro replay khi token bị lộ.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, `nonce`, `state`/`response_mode`, OIDC code/hybrid flows và UserInfo.
- [OAuth 2.0 Multiple Response Type Encoding Practices](https://openid.net/specs/oauth-v2-multiple-response-types-1_0.html): `query` và `fragment` response modes, quy tắc mã hóa cho response types.
- [OAuth 2.0 Form Post Response Mode](https://openid.net/specs/oauth-v2-form-post-response-mode-1_0.html): `form_post` đưa authorization response parameters về client qua HTML form POST thay URL query/fragment.
- [W3C Referrer Policy](https://www.w3.org/TR/referrer-policy/): Header `Referrer-Policy`, `no-referrer`, `strict-origin-when-cross-origin` và cách tạo `Referer`.
- [WHATWG HTML — Session history / Navigation APIs](https://html.spec.whatwg.org/multipage/nav-history-apis.html): Navigation history, `pushState`/`replaceState` semantics.
- [MDN — History.replaceState()](https://developer.mozilla.org/en-US/docs/Web/API/History/replaceState): Same-origin restrictions, thay entry history hiện tại.
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy): Các chính sách gửi `Referer` và giới hạn.
- [web.dev — Back/forward cache](https://web.dev/articles/bfcache): bfcache khác HTTP cache, browser lifecycle và kiểm thử.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth redirect, PKCE, browser/client protections.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): Cookie flags, session lifecycle/logout và browser cache concerns.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): URL reset tokens, single use, short expiry, no-referrer và safe flow.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): Registered client, authorization redirect/callback và token exchange.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): Cache controls, Referrer-Policy/CSP và headers behavior.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): Browser cookie-based CSRF protections.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): Server-side session invalidation và cookie cleanup.
- [Spring Security — Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): JWT/opaque AT verification và resource authorization.

**Điểm cần ghi nhớ:** **Browser URL không phải nơi lưu hoặc vận chuyển OAuth bearer access token, refresh token hay ID token chỉ để điều hướng ứng dụng.** Query/path được gửi tới HTTP origin và thường có nguy cơ xuất hiện trong logs; **fragment không nằm trong request-target hay `Referer` chuẩn, nhưng vẫn hiện ở browser/JavaScript/history**. Code Flow có thể đưa **authorization code một lần, ngắn hạn** qua callback URL: cần **PKCE S256, `state`/issuer/client/redirect binding, xử lý nhanh và làm sạch URL**. `history.replaceState`, `location.replace`, `Referrer-Policy: no-referrer` và `Cache-Control: no-store` giúp giảm exposure nhưng **không xóa mọi dấu vết hoặc thu hồi credential đã lộ**; Back/bfcache/analytics/third-party scripts còn có các giới hạn riêng. **BFF + HttpOnly Secure SameSite cookie** có thể giảm raw AT/RT xuất hiện ở browser nhưng vẫn cần CSRF/XSS/session controls. Phòng vệ đầy đủ đòi hỏi **URL hygiene + log redaction + token lifecycle/revocation + RS audience/scope/ACL + kiểm thử browser thực tế**.
