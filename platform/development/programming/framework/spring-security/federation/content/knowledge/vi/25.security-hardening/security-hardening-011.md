# Chống rò rỉ assertion, ticket và token qua URL, log hoặc bộ nhớ đệm trình duyệt

Trong hệ thống **Spring Security federation**, dữ liệu xác thực có thể xuất hiện ở nhiều dạng: **SAML Assertion/SAMLResponse**, **CAS Service Ticket/Proxy Ticket**, **OAuth 2.0 Authorization Code**, **OIDC ID Token**, **OAuth Access Token/Refresh Token**, **session cookie** và các mã liên quan đến phiên đăng nhập. Chúng không giống nhau về mục đích, nhưng điểm chung là **nếu bị đưa vào URL, access log, trace, response cache, browser storage, dump bộ nhớ hoặc dịch vụ bên thứ ba, chúng có thể trở thành nguồn lộ danh tính và chiếm phiên**.

Mục tiêu của bài học không phải “giấu mọi thứ khỏi trình duyệt bằng mọi giá”: một số giao thức **buộc trình duyệt mang một artifact ngắn hạn**. Mục tiêu đúng là **giảm tối đa sự hiện diện của credential trong các bề mặt dễ sao chép, ràng buộc artifact với đúng client/service/phiên, phát hiện và xử lý việc lộ dữ liệu**. Một mã CAS ticket đã dùng xong vẫn cần không bị log; một OAuth authorization code bị lộ có thể được bảo vệ thêm nhờ **PKCE**, nhưng không được dùng PKCE làm lý do lưu cả code vào nhật ký.

Bài thuộc nhóm **Gia cố an toàn**, giải thích từng cơ chế OIDC/OAuth2, SAML2, CAS và hành trình thông tin nhạy cảm qua URL/history/Referer/log/browser cache/Java memory. Có hướng dẫn triển khai cho Spring Security Servlet, lựa chọn response headers, log allowlist, một demo **Java 17 tự biên dịch/chạy**, test matrix, runbook sự cố và nguồn chính thức.

> **Nguyên tắc một câu:** không đặt token có thể sử dụng lại trong URI; không ghi nguyên dữ liệu callback/credential vào log; không cache nội dung xác thực hoặc trang nhạy cảm; sử dụng HTTPS, ràng buộc protocol, TTL ngắn và giới hạn quyền để giảm hậu quả khi một artifact vô tình lộ.

## 1. Phân biệt những thứ cần bảo vệ

| Dữ liệu | Được dùng để làm gì? | Có thể xuất hiện ở đâu? | Rủi ro chính |
| --- | --- | --- | --- |
| **OAuth Authorization Code** | Đổi lấy tokens tại token endpoint | Query `code` trên redirect URI; hoặc `form_post` nếu được hỗ trợ | Kẻ khác thử đổi code trước client; lộ state/redirect flow |
| **OIDC ID Token** | Chứng minh kết quả authentication cho OIDC client | Token endpoint/back-channel với Authorization Code; ở flow khác có thể trên front-channel | PII/claims và identity context bị lộ; nhầm ID Token với access token |
| **OAuth Access Token** | Gọi protected resource/API | `Authorization: Bearer`, token storage, proxy/APM | **Bearer token theft/replay**, API access trong phạm vi scope |
| **Refresh Token** | Xin access token mới | Token endpoint/client secure storage | Lộ lâu dài, kéo dài truy cập dù access token ngắn hạn |
| **SAMLResponse/Assertion** | Chuyển authentication result từ IdP tới SP | HTML form `SAMLResponse`/HTTP POST tới ACS; các bindings khác | Lộ claims, signature data, khả năng replay nếu SP kiểm thiếu |
| **SAML Artifact** | Tham chiếu tới message để đổi qua back-channel | Browser front-channel tùy binding | Artifact bị lấy và đem redeem nếu không ràng buộc/one-time |
| **CAS Service Ticket (ST)** | Chứng minh CAS login cho một service URL | Tham số `ticket=ST-...` trong URL callback | Ticket bị lấy trước SP validation, replay/rò từ access logs |
| **CAS Proxy Ticket/PGT** | Truy cập service hoặc gọi service thay user theo CAS policy | CAS back-channel và ứng dụng được phép delegation | Ủy quyền vượt phạm vi hoặc chiếm phiên downstream |
| **Session cookie** | Giữ browser session tại IdP/SP | Cookie header, cookie jar, HAR, proxy logs | Session hijacking, fixation hoặc tái dùng session cũ |
| **`state`/`nonce`/`RelayState`** | Ràng buộc request/response và navigation theo protocol | Front-channel và state store | Lộ hoặc giả mạo correlation, CSRF/login injection, open redirects |

**Các từ “token”, “ticket” và “assertion” không thay thế nhau.** ID Token chứng minh authentication cho **OIDC client**; Access Token là credential để gọi API; OAuth authorization code là credential ngắn hạn chỉ dùng đổi token; CAS ST bị ràng buộc với service; SAML Assertion mang thông tin xác thực/thuộc tính cho SP xác định. Cơ chế bảo vệ và thời gian sống khác nhau, nhưng **không thứ nào nên bị đưa vào log thô một cách mặc định**.

### Một số ví dụ phải xem là dữ liệu nhạy cảm

~~~text
OAuth callback:
  /login/oauth2/code/corp?code=CODE-EXAMPLE&state=OPAQUE-STATE

CAS callback:
  /login/cas?ticket=ST-EXAMPLE&service=https%3A%2F%2Fportal.example

OAuth API (không nên):
  /api/reports?access_token=TOKEN-EXAMPLE

OAuth API (đúng phương thức bearer thông thường):
  Authorization: Bearer TOKEN-EXAMPLE

SAML POST form field:
  SAMLResponse=<base64 XML with claims and signature>
  RelayState=<opaque correlated application state>

Session:
  Cookie: JSESSIONID=SESSION-EXAMPLE
~~~

Đây là **giá trị giả để phân tích**, không phải credentials có thể dùng thật. **Không copy URL callback, Authorization header hoặc Cookie header thật vào ticket hỗ trợ, chat công khai, ảnh chụp DevTools hoặc công cụ AI ngoài phạm vi được phê duyệt.**

## 2. Dữ liệu xác thực bị rò từ những đường nào?

~~~mermaid
flowchart TD
    A[Browser / IdP / Callback] --> B[URL query / fragment / form body]
    B --> C[Reverse proxy, WAF, CDN, access logs]
    B --> D[Browser history, Referrer, bookmarks]
    B --> E[Third-party JS, images, analytics]
    A --> F[HTTP response, cookies, local browser storage]
    F --> G[Browser cache, Service Worker, backups]
    A --> H[Spring filters, exceptions, APM traces]
    H --> I[Structured logs, heap dumps, crash reports]
    C --> J[Untrusted reader / attacker]
    D --> J
    E --> J
    G --> J
    I --> J
~~~

Cần chú ý ba hệ thống lưu dữ liệu **độc lập**:

1. **Hệ thống mạng/server**: reverse proxy, ingress, WAF, API gateway, CDN, web server access log, APM/tracing, debug logger, centralized logging.
2. **Trình duyệt/thiết bị**: address bar, history, Referer, clipboard, download/export HAR, bfcache/HTTP cache, Web Storage, JavaScript memory, browser extensions.
3. **Ứng dụng/backend**: request/response bodies, exception context, thread-local/MDC, heap dump, trace spans, HTTP client interceptors, token stores, session persistence và backups.

Xóa một entry trong Spring log **không tự xóa bản sao ở ingress**, và `Cache-Control: no-store` **không xóa log đã phát sinh**. Defense-in-depth phải đặt ở mọi nơi dữ liệu thực sự đi qua.

## 3. URL query, browser history và Referer

Một URI như:

~~~http
GET /login/oauth2/code/corp?code=AUTH-CODE&state=OPAQUE HTTP/1.1
Host: portal.example
~~~

có thể được lưu trong browser history, reverse proxy request logs, APM tags, browser sync, screenshot/address bar hoặc bị truyền trong **Referer** khi callback page tải tài nguyên/link khác. RFC 9700 (**OAuth 2.0 Security Best Current Practice**, 2025) mô tả rõ cả **credential leakage qua Referer** và **browser history**.

**Không hiểu sai:** authorization code trong query của OIDC Authorization Code flow **là giao thức hợp lệ** và tồn tại có chủ đích. Điều cần làm là giảm giá trị của code nếu bị lộ (authorization code one-time, short TTL, client binding/PKCE), không kéo dài thời gian phơi nhiễm và không ghi full URI vào logs.

Các rủi ro cần phân biệt:

- **Query string** được gửi cho server và nhiều reverse proxies; access log mặc định có thể ghi request target đầy đủ.
- **URL fragment** (phần sau `#`) thường **không được HTTP user-agent gửi tới server**, nhưng vẫn nằm trong browser address bar/history, được JavaScript cùng origin đọc và có thể lộ qua extension/XSS hoặc browser-specific behavior. Không coi fragment là secret vault.
- **Referer** có thể chứa URI nguồn theo browser Referrer Policy, especially same-origin; nếu callback chứa code/state và tải third-party tracking script, cần kiểm nguồn rò.
- **`Location` redirects** có thể chuyển nguyên query từ callback sang URL tiếp theo nếu ứng dụng ghép hoặc forward toàn bộ request parameters.
- **Open redirect** trên IdP/client có thể chuyển code/token tới origin của attacker; chỉ cho exact registered redirect URIs.
- **Query parameters thứ cấp** như `next`, `returnUrl`, `RelayState` có thể bị attacker sử dụng để ép redirect ra ngoài nếu thiếu allowlist.

### Referrer Policy không thay protocol validation

Response header phù hợp cho các trang xác thực:

~~~http
Referrer-Policy: no-referrer
Cache-Control: no-store
Pragma: no-cache
Expires: 0
~~~

`no-referrer` hạn chế gửi `Referer` trong những requests phát sinh từ tài liệu. **Không bảo đảm xóa URL khỏi browser history, access logs hoặc third-party script đang chạy trong trang**. Nên tránh third-party subresources trên callback/auto-post pages ngay từ thiết kế, kể cả khi đã đặt header.

**Thứ tự quan trọng:** nếu callback page đã tải analytics trước khi redirect sạch URL, việc sửa bằng JavaScript sau đó có thể quá muộn. Cấu hình server-side callback xử lý code rồi chuyển về một URL ứng dụng **không có credentials** trước khi render dashboard.

## 4. OAuth 2.0/OIDC: bảo vệ Authorization Code flow

Một cấu hình an toàn thông thường cho web app là:

~~~text
1. Browser -> Spring route protected
2. Spring -> IdP /authorize (response_type=code, state, nonce, PKCE)
3. IdP -> Spring callback ?code=...&state=...
4. Spring validates state + authorization request association
5. Spring exchanges code via HTTPS back-channel with the IdP
6. Token endpoint returns tokens to registered client
7. Spring validates OIDC ID Token (iss/aud/exp/nonce/signature)
8. Spring establishes local authenticated session
9. Browser -> clean application URL without code/state
~~~

**Điều kiện kiểm soát code leakage:**

- **Authorization Code + PKCE (S256)**, kể cả khi client là confidential nếu stack hỗ trợ; **không dùng implicit grant** để phát access token trực tiếp qua front-channel trừ tình huống có lý do rất đặc biệt được đánh giá theo RFC 9700.
- **Exact redirect URI matching** với registered redirect URIs; không chấp nhận arbitrary callback URL lấy từ request.
- Code **ngắn hạn, một lần sử dụng**, ràng buộc với client và redirect URI theo OAuth server requirements.
- `state` ngẫu nhiên có entropy phù hợp, ràng buộc request/session, dùng chống CSRF; `nonce` cho OIDC flow khi yêu cầu, gắn kết ID Token với login request.
- Không đặt access token, refresh token, ID Token, PKCE `code_verifier` hoặc client secret vào `state`, `nonce` hay return URL.
- Khi nhiều IdPs, chống mix-up bằng issuer/client association và `iss` trong authorization response nếu cơ chế cung cấp; không đoán issuer từ query do user chọn.
- Không render trang có links/analytics/iframe/third-party resources khi callback còn credential trong address bar.
- Có thể cân nhắc **`response_mode=form_post`** cho authorization response nếu IdP/client hỗ trợ và cấu hình response-mode/session cookies thích hợp; không tự gán nó vào mọi OAuth implementation.
- Sau khi token exchange/validate xong, điều hướng sang trang sạch. Không forward nguyên query callback sang ứng dụng hoặc reverse proxy khác.

**Cần phân biệt:** PKCE bảo vệ việc đổi code khi thiếu `code_verifier`, **không tự ngăn code bị ghi vào access log**, và không bảo vệ khi attacker đã lấy cả session/PKCE verifier hoặc có lỗ hổng XSS trên client. Dùng PKCE cùng các biện pháp phía URL/log.

### Tại sao không dùng OAuth implicit flow?

Các flows phát `access_token` qua URL fragment trong browser thường làm tăng nguy cơ token leak/replay. RFC 9700 khuyên dùng Authorization Code flow hoặc cơ chế không phát access token trong authorization response. Trình duyệt có thể lưu fragment trong history; JavaScript trên origin đọc được; extensions/XSS có thể lấy.

Đừng “sửa” bằng cách chuyển access token từ fragment sang query. Đây là cách **đưa bearer credential vào access log server**.

## 5. Bearer access token: tuyệt đối tránh query string

Ví dụ **không nên**:

~~~http
GET /api/reports?access_token=ACCESS-TOKEN HTTP/1.1
Host: api.example
~~~

RFC 6750 đã lưu ý phương thức URI query có nguy cơ bị log; RFC 9700 cập nhật yêu cầu hiện đại mạnh hơn: **clients MUST NOT truyền access token bằng URI query parameter theo RFC 6750 `2.3**. Bearer token nên được gửi trong HTTP `Authorization` header, bảo vệ bằng HTTPS:

~~~http
GET /api/reports HTTP/1.1
Host: api.example
Authorization: Bearer ACCESS-TOKEN
~~~

**Nhưng header không tự an toàn:** WAF/full request dump, application interceptors, APM auto-instrumentation, proxy debug hoặc HAR vẫn có thể thu thập `Authorization`. Hãy scrub/không capture headers nhạy cảm tại mọi điểm thu thập. Không cho phép `Cookie`/`Set-Cookie` xuất hiện trong log thô.

Token scopes, audience, expiration và sender-constraining là lớp giảm hậu quả khi mất cắp:
- Validate token `iss`, `aud`, signature, `exp` và scopes phù hợp tại resource server.
- Ưu tiên quyền tối thiểu và short-lived access tokens.
- Dùng mTLS sender-constrained tokens hoặc DPoP khi hệ thống hỗ trợ và threat model phù hợp.
- Dùng **refresh token rotation** hoặc ràng buộc với client/device nếu là public clients; quản lý reuse detection theo IdP implementation.
- Không trao ID Token cho API như Access Token: đó là token với **audience và mục đích khác**.

**Một bearer token đã bị lộ có thể vẫn có hiệu lực tới expiration hoặc revoke**, dù API đã bật HTTPS và `no-store`. Cần có incident response và thời gian sống hợp lý.

## 6. SAML 2.0: POST binding không phải secret storage

Trong **SAML HTTP POST binding**, IdP thường tạo một HTML form với hidden field:

~~~html
<form method="post" action="https://sp.example/saml2/acs">
  <input type="hidden" name="SAMLResponse" value="BASE64-XML-EXAMPLE">
  <input type="hidden" name="RelayState" value="OPAQUE-STATE">
  <button type="submit">Continue</button>
</form>
~~~

Form được browser gửi theo HTTP POST tới **Assertion Consumer Service (ACS)**. `SAMLResponse` có thể chứa Assertion, subject identifiers, attributes, timestamps và XML signature. **Hidden input không có nghĩa giá trị được mã hóa hoặc bí mật đối với browser**: DevTools, browser extensions, scripts trên IdP form page, network capture ở endpoints và WAF/request-body logging vẫn có thể quan sát.

OASIS SAML Technical Overview mô tả flow auto-submit POST với form field `SAMLResponse` và `RelayState`. Rủi ro không nằm ở việc dùng POST đúng chuẩn mà ở **log body, cache form, third-party scripts, kiểm Assertion thiếu và lưu nội dung nhạy cảm lâu hơn cần thiết**.

Các yêu cầu:

1. Dùng HTTPS và kiểm certificate chain/host ở IdP/SP.
2. Không ghi `SAMLResponse`, decoded Assertion XML, signed XML fragments, NameID nhạy cảm hoặc full attributes vào application logs.
3. IdP HTML auto-submit page có `Cache-Control: no-store` và không có third-party scripts/analytics, CSP phù hợp với cách submit.
4. SP kiểm **issuer, signature, Destination, Recipient, InResponseTo, AudienceRestriction, Conditions/SubjectConfirmationData timestamps**, expected binding và replay cache theo profile.
5. Chỉ dùng attributes thật sự cần; kiểm data minimization ngay từ IdP.
6. Sau SP xử lý xong SAMLResponse, trả về clean URL/dashboard; không echo response body hoặc params sang HTML/error page.
7. Cẩn thận với `RelayState`: thông thường là opaque correlation state; không tự tạo open redirect bằng `Location: {RelayState}`.
8. SAML Artifact binding có thể giảm lượng assertion đi trong front-channel bằng cách gửi artifact rồi truy xuất message qua back-channel; **artifact vẫn là một credential tham chiếu có giá trị** và cần one-time redemption, audience/binding/TLS, không được log bừa.

**SAML Assertion đã được ký vẫn có thể chứa PII bí mật**. Chữ ký bảo đảm tính toàn vẹn/xuất xứ khi validate đúng; **không có nghĩa Assertion được mã hóa**. Nếu yêu cầu bí mật nội dung trước browser/intermediaries, dùng **SAML XML Encryption**/encrypted assertions theo profile và khóa SP phù hợp; encryption không thay signature/audience/replay checks.

## 7. CAS: ticket trong URL là thực tế giao thức cần quản lý

Trong CAS web SSO cổ điển, sau khi user đăng nhập, CAS redirect browser tới **service URL** với tham số `ticket`:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example/login/cas?ticket=ST-FAKE-EXAMPLE
~~~

Spring Security `CasAuthenticationFilter` theo Javadoc có default processing URL `/login/cas`, nhận opaque service ticket trong request parameter `ticket`, rồi dùng `CasAuthenticationProvider` và CAS ticket validator để xác minh với CAS server. Ticket phải được **ràng buộc với service URL** và là artifact một lần dùng theo protocol; không được sử dụng làm password lưu lâu dài.

Rủi ro:

- Browser history/URL chứa `ST-...` trong lúc redirect.
- Ingress/web server access log ghi nguyên `/login/cas?ticket=ST-...`.
- APM logger hoặc error handler log `request.getQueryString()`.
- Browser Referer từ trang đang giữ ticket đến một origin khác.
- Redirect sau login vô tình chép ticket sang `returnUrl` hoặc link trong HTML.
- Ticket validation failure ghi nguyên ticket vào exception/log.
- CAS Proxy Ticket/Proxy-Granting Ticket có quyền downstream khác ST, cần bảo vệ theo delegation policy.

Cách giảm thiểu:

1. **Không log query string** của callback CAS ở gateway, access logs, Spring, tracing.
2. Cấu hình `ServiceProperties.getService()`/callback URL khớp chính xác với dịch vụ mà ticket được phát, không nhận ticket dành cho service khác.
3. Ticket validation qua back-channel HTTPS, kiểm CAS server trust và TLS; one-time validation, tránh chấp nhận replay.
4. Khi đã validate, điều hướng browser về **clean application URL** không giữ `ticket`. Với các Spring/CAS versions khác nhau cần test flow thực, không giả định filter tự xóa browser history theo mọi cấu hình.
5. Set cache/no-referrer headers cho callback và error pages; không chứa token trong HTML hoặc diagnostics.
6. Không copy ticket sang session attribute/log/URL như cách “lưu chứng cứ đăng nhập”. Chỉ giữ identity/session cần thiết.
7. Với CAS PGT/PT, bổ sung checks cho delegated service, callback, receiver key và scope; tuyệt đối không log token vào network dashboards.

**Quan trọng:** CAS ticket query là một phần của flow; không thể đơn giản “từ chối mọi query params” trên `/login/cas` mà vẫn thực hiện CAS classic. Phải bảo vệ endpoint cụ thể và xử lý ticket đúng một lần rồi chuyển sang URL sạch.

## 8. Bảng so sánh bề mặt rò theo giao thức

| Cơ chế | Front-channel được mong đợi | Dữ liệu cần tránh trong logs | Hậu kiểm đặc thù |
| --- | --- | --- | --- |
| OIDC Authorization Code | `code` và `state` ở redirect callback (hoặc form_post nếu hỗ trợ) | Code/state, raw redirect URI, authorization/token response | PKCE, exact redirect URI, state, nonce, iss/aud/signature |
| OAuth bearer API | Không có bearer token trong URI | Authorization, cookies, access/refresh tokens, body | Audience, scopes, expiry, sender constraint |
| SAML2 POST | `SAMLResponse` ở form body, `RelayState` | Decoded XML, base64 response, NameID, attributes | Issuer, signature, audience, recipient, timestamp, replay |
| SAML Artifact | Artifact ở front-channel theo binding | Artifact, SOAP exchange details | One-time artifact resolution, mutual trust/TLS |
| CAS ST | `ticket` trong query | Ticket, raw request target, validation responses | Service binding, one-time validation, clean redirect |
| CAS PT/PGT | Thường back-channel/delegation contexts | Proxy/PGT tokens, callback sensitive payload | Delegation restrictions and valid target |
| IdP/SP session | Cookie trên HTTPS requests | Cookie, Set-Cookie, server session identifiers | HttpOnly/Secure/SameSite, rotation, logout/revocation |

Đừng áp dụng cùng một regex log scrub làm biện pháp duy nhất cho mọi thứ. **SAMLResponse thường nằm trong POST body**, bearer ở `Authorization`, CAS ST ở query, session ID ở `Cookie`; mỗi nguồn cần **chính sách chặn thu thập** riêng.

## 9. HTTP cache, CDN/proxy cache và browser Back

Spring Security theo tài liệu hiện hành mặc định thêm một số response headers nhằm tránh cache nội dung nhạy cảm:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

Cần hiểu:

- **`no-store`** yêu cầu cache không lưu request/response; là chỉ dẫn mạnh cho auth callback, token-bearing error response và trang chứa dữ liệu riêng.
- **`no-cache`** không có nghĩa “không lưu”: HTTP cache có thể lưu và phải revalidate trước khi dùng. Vì thế `no-cache` đơn lẻ không thay `no-store`.
- **`private`** giới hạn lưu ở private cache, **không đảm bảo browser không giữ**. Không dùng `private` một mình cho nội dung cực nhạy cảm.
- **`max-age=0, must-revalidate`** hỗ trợ kiểm freshness, nhưng `no-store` vẫn là tín hiệu quan trọng nhất.
- **`Pragma: no-cache`** và `Expires: 0` hỗ trợ compatibility với hệ thống cũ; không thay `Cache-Control` hiện đại.
- **`Vary: Authorization`/`Vary: Cookie`** có thể cần trong kịch bản caching được duyệt, nhưng **không nên coi Vary là thay thế no-store** cho auth responses.

**Spring Security có thể không ghi đè Cache-Control nếu ứng dụng tự set response header**; servlet controllers, CDN, framework khác và reverse proxy có thể chỉnh. Không được kết luận đã an toàn chỉ vì security dependency tồn tại. Kiểm header trên **response thực tế sau tất cả proxies**.

### Browser Back/Forward Cache (bfcache)

`no-store` giúp hạn chế HTTP caching, nhưng không nên tuyên bố mọi browser phiên bản đều loại bỏ history snapshot/bfcache hoặc vùng nhớ JavaScript trong mọi điều kiện. Hành vi browser thay đổi; trang nhạy cảm cần **session authorization ở mỗi request/restore được thiết kế**, không chỉ dựa vào một header và kỳ vọng nút Back luôn rỗng.

### Caching ở CDN/ingress

Token callback và trang riêng tư không được biến thành public cached object. Tránh:
- CDN cache `/login/oauth2/code/*`, `/login/cas`, `/login/saml2/sso/*`.
- Reverse proxy cache 302 authentication redirects có credential.
- Shared cache dựa vào URL mà không xét session/user.
- Cache key chứa query secrets rồi xuất hiện trong CDN analytics/control plane.
- Edge debug logs có raw response body từ SAML auto-post page.

**Cần cấu hình cả origin và edge**: no-store response, skip-store auth routes, redact logs, kiểm bằng thực nghiệm từ browser và multiple users.

## 10. Referrer-Policy, HSTS, CSP và cookies

Một bộ bảo vệ cơ bản cho auth pages và sensitive endpoints:

~~~http
Referrer-Policy: no-referrer
Cache-Control: no-store
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'none'
~~~

**Không copy CSP trên sang mọi ứng dụng khi chưa kiểm**: nếu SAML IdP cần auto-submit script inline, CSP `script-src`/nonce/hash phù hợp là điều bắt buộc; không dùng `unsafe-inline` bừa bãi. HSTS chỉ phát trên HTTPS, `includeSubDomains` phải tính đến tất cả subdomains thật. HSTS không xóa dữ liệu đã ghi log.

### Session cookie

Cookie chứa session identifier nên có:
- **`Secure`**: chỉ gửi qua HTTPS.
- **`HttpOnly`**: JavaScript không đọc giá trị cookie qua `document.cookie` (không ngăn XSS gọi API bằng cookie tự gửi).
- **`SameSite`** theo SSO flow thực: `Lax` thường tương thích với top-level GET callback, nhưng **SAML cross-site POST ACS** có thể cần `SameSite=None; Secure` hoặc state/cookie-handling khác; `Strict` không phải lựa chọn mặc định cho mọi SSO.
- Domain/Path tối thiểu, tránh cookie phát cho nhiều subdomains không liên quan; cân nhắc prefix **`__Host-`** khi đáp ứng quy tắc Secure, Path=/, không Domain.
- Session fixation protection, session rotation, timeout và logout/invalidation phù hợp.

**HttpOnly không tương đương chống CSRF và không ngăn request tự động gửi cookie**. Phân tích CSRF, same-site/cross-site callback, logout và cookie session cụ thể. Không lưu session IDs vào URLs (URL rewriting như `;jsessionid=...`) khi có thể dùng cookie an toàn; trong Spring/Servlet container cần disable URL-based session tracking nếu không cần.

## 11. localStorage, sessionStorage, IndexedDB và Service Worker

Các browser storage APIs khác nhau:

| Nơi lưu | Browser JavaScript có đọc không? | Rủi ro |
| --- | --- | --- |
| `localStorage` | Có, cùng origin | XSS lấy token, persists sau đóng tab |
| `sessionStorage` | Có, cùng tab/context | XSS vẫn lấy được; không là kho bí mật |
| `IndexedDB` | Có theo origin permissions | Dữ liệu persist, Service Worker/script truy cập tùy policy |
| Cookie **HttpOnly** | JavaScript không đọc cookie value | CSRF/same-site, XSS vẫn có thể gửi authenticated requests |
| JavaScript in-memory variable | Script cùng execution context có thể tiếp cận tùy architecture | XSS hoặc extension có thể thao tác, mất khi reload |
| Server-side token store/BFF | Browser chỉ giữ session cookie | Giảm browser token exposure, nhưng backend store và session vẫn phải bảo vệ |

OWASP HTML5/Session Management guidance khuyến cáo **không lưu authentication tokens, refresh tokens hoặc session IDs trong Web Storage** vì XSS cùng origin có thể lấy được. `sessionStorage` không phải “safe version” của `localStorage`.

Đối với **Spring MVC web application** dùng Authorization Code flow, ưu tiên server-side session/token management khi kiến trúc phù hợp. Với SPA/browser-based clients, đánh giá **Backend-for-Frontend (BFF)**, PKCE, CSP, Trusted Types, dependency security và token lifecycle; không gửi refresh token dài hạn vào JS runtime chỉ vì thư viện hỗ trợ.

### Service Worker/Cache API

Service Worker có thể intercept requests và Cache API có thể lưu responses nếu ứng dụng chủ động code như vậy. HTTP `Cache-Control: no-store` **không thay thế việc kiểm logic của Service Worker Cache API**; không cache login callbacks hoặc API chứa PII/token. Khi logout, thiết kế xóa dữ liệu phía client phù hợp, nhưng **không thể đảm bảo xóa hết mọi bản sao trong screenshot, browser history, analytics hoặc cloud backups**.

### Browser extensions và export HAR

HAR thường chứa full request URLs, headers, cookies và đôi khi POST bodies. Nếu developer gửi một HAR từ login callback, nó có thể chứa CAS ticket, SAMLResponse, OAuth code/state hoặc Authorization header. **Không tải HAR raw lên issue tracker công khai**. Chỉ xuất trong môi trường kiểm soát, dùng redaction đã kiểm, đặt quyền truy cập và thời gian lưu ngắn.

## 12. Log và APM: không chỉ Spring application.log

Những lớp dễ vô tình log credentials:

| Lớp | Nguồn chứa secret | Cần thay đổi |
| --- | --- | --- |
| Nginx/Apache/ingress | `$request`, `$request_uri` gồm query | Dùng path-only, log route/method/status; bỏ query trên auth routes |
| Load balancer/CDN | Request URI, headers, cache keys, debug dumps | Route exclusion, field redaction, hạn chế retention |
| WAF | Request/response body capture, anomaly samples | Không log raw `SAMLResponse`, Authorization, Cookie |
| Spring MVC | `getRequestURL()` + `getQueryString()`, request parameter dumps | Log canonical route/endpoint ID và outcome |
| Spring Security | DEBUG/TRACE, exception details | Chỉ bật có thời hạn; không log credentials/tokens |
| HTTP clients | Token requests/responses từ RestClient/WebClient | Mask Authorization, client_secret, refresh_token, tokens |
| APM/tracing | HTTP `url.full`, span attributes, baggage, custom tags | Omit query/headers/body; scrub trước khi export |
| Centralized logging/SIEM | Raw logs từ nhiều tầng | Ingestion rules, encryption, access control, retention |
| Error reporters | Exception local variables, request bodies, breadcrumbs | Disable sensitive captures, review PII scrub |
| Heap/thread dumps | Access/refresh tokens, Assertion XML, cookies | Restrict dump access; avoid attaching to tickets |

**Cảnh báo:** regex redaction chạy **sau** khi full token đã được gửi sang exporter có thể quá muộn. Ưu tiên **không thu thập trường nhạy cảm ngay từ nguồn** (data minimization) và dùng **allowlist** những dữ liệu được phép ghi.

### Danh sách trường an toàn hơn để audit

~~~text
time=2026-11-07T03:00:00Z
event=AUTH_CALLBACK
protocol=OIDC
endpoint=oidc_callback
method=GET
result=SUCCESS
duration_ms=47
correlation_id=nonsecret-random-id
provider_key=corp_idp
principal_link_id=approved-internal-id (nếu thực sự cần và được phép)
~~~

Không ghi:

~~~text
?code=...&state=...
?ticket=...
SAMLResponse=...
Authorization: Bearer ...
Cookie: JSESSIONID=...
Set-Cookie: ...
refresh_token=...
client_secret=...
full ID Token/JWT, NameID/Assertion XML, password
~~~

**`correlation_id`** phải là identifier ngẫu nhiên riêng cho audit/trace, không tái sử dụng bearer credential hoặc trực tiếp ghi `state`/ticket vào đó. Nếu cần phân biệt token trong điều tra, dùng một **mã tham chiếu không thể dùng để xác thực**, có ràng buộc/retention và bảo vệ, thay vì raw token hay hash không keyed của token low entropy.

## 13. Quy tắc logging theo allowlist, không phải regex cố cứu mọi thứ

**Anti-pattern:**

~~~java
// KHÔNG làm trong Spring filter/controller:
log.info("auth callback uri={}", request.getRequestURI()
        + "?" + request.getQueryString());
log.debug("SAMLResponse={}", request.getParameter("SAMLResponse"));
log.info("Authorization={}", request.getHeader("Authorization"));
log.error("authentication failed, request={}", request);
~~~

Một vài API/`toString()` có thể kèm dữ liệu nhạy cảm. Log message chứa mã code/ticket có thể bị sao chép vào APM exception events dù sau đó app không lưu riêng.

**Cách an toàn hơn về nguyên tắc:**

~~~text
input: HTTP request with untrusted URL/headers/body
derive:
  route identifier from a FIXED set of known callback routes
  method from fixed allowlist
  high-level result code
  duration
  independent correlation ID
discard for logging:
  full request-target, query, fragments, POST parameters
  Authorization/Cookie/Set-Cookie, token responses
  SAML XML/NameID, exception parameter dumps
output:
  structured audit event with only approved fields
~~~

Không ghi **full raw path** nếu path có thể chứa bearer token, user ID/PII hoặc path traversal payload; dùng **route template/registered endpoint key**. Không dùng `request.getParameterMap()` làm structured logging vì nó gồm cả OAuth code/state, CAS ticket và SAMLResponse.

### Loggers/frameworks cần kiểm

- Embedded Tomcat `AccessLogValve`, Jetty/Undertow access logs.
- Spring Boot actuator HTTP exchanges/observability tags.
- Spring Security DEBUG/TRACE, OAuth2 client/Resource Server/SAML logs.
- Spring MVC request/response logging filters và Servlet filters tự viết.
- WebClient/RestTemplate wire logging, Reactor Netty HTTP wiretap.
- Nginx `$request` vs `$uri`: `$request` thường chứa full request-target/query; `$uri` thường chỉ path nhưng còn có thể là user input, cần phân loại. **Không giả định đổi biến là đủ** nếu một agent khác log URL đầy đủ.
- WAF/mod_security request-body logging; SAML POST payload có thể nằm trong body.
- OpenTelemetry `url.full`, `http.request.header.authorization`, baggage, exception attributes và collectors.
- Error trackers (Sentry, Rollbar, crash dumps), CI test artifacts, load-testing captures.

**Bảo vệ pipeline logging**: principle of least privilege, encryption at rest/transit, retention, segregated audit access, logging health alerts và secret scanning trên sample synthetic flows. Không upload logs thô chứa credentials sang vendor bên ngoài mà thiếu data handling agreement và scrub.

## 14. Spring Security Servlet: response headers cho auth endpoints

Spring Security hiện hành có response security headers mặc định, gồm một tập **Cache-Control/Pragma/Expires** chặn caching. Bạn có thể khai báo rõ **Referrer-Policy** cho application:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

@Configuration
public class FederationSecurityHeaders {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .headers(headers -> headers
                .cacheControl(Customizer.withDefaults())
                .referrerPolicy(ref -> ref.policy(
                    ReferrerPolicyHeaderWriter
                      .ReferrerPolicy.NO_REFERRER)))
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là **cấu hình Spring Security Servlet fragment**, cần Spring Security OAuth2 Client/Boot dependencies và ClientRegistration hợp lệ. **Không** chạy trực tiếp bằng `javac`. Dòng Spring Security đang dùng có thể thay đổi API names/lambdas, hãy kiểm docs và dependency tree; khi ứng dụng dùng **SAML hoặc CAS** phải thêm đúng authentication chain/provider tương ứng thay vì copy `oauth2Login` rồi coi đó là toàn bộ federation configuration.

**Điểm quan trọng về filter chain:** callback login được filter xử lý trước khi app controller render trang. Vì thế headers cần áp trên **tất cả response paths**, gồm success, failure, redirects, static auto-submit, error, exception và requests bên ngoài Spring Security chain nếu có. Nếu đã khai báo override `Cache-Control` ở MVC/proxy, hãy test response thực thay vì dựa vào mặc định.

### Response header không tự ngăn logging

Không có một `http.headers(...)` option nào xóa raw `code`/`ticket` khỏi access logs đã ghi trước khi request đến Spring. Phải cấu hình logging riêng cho ingress/proxy/APM và application.

### Callback response nên làm gì?

Sau authentication đã kiểm:
1. Tạo/cập nhật application security context theo cơ chế Spring, session fixation protection và cookie flags.
2. **303 See Other** hoặc redirect phù hợp đến **clean application URL** không kèm code, ticket, SAMLResponse, state.
3. Không render trang template chứa original callback URI trong link, form, script, history hoặc `<base>`.
4. Không thêm third-party resources vào trang callback/error, hạn chế Referrer.
5. Không đưa raw exception cause/body vào error pages.

**Cẩn trọng:** không tự viết một filter redirect trước authentication để xóa `ticket`/`code` khi Spring chưa validate; nếu chuyển quá sớm, bạn làm mất callback data và phá login. Dựa trên authentication success handler/filter và protocol implementation tương ứng.

## 15. OAuth2 Login và SAML/CAS endpoints cần nhận diện đúng

Các endpoint Spring Security có thể khác theo phiên bản/config:

~~~text
OIDC/OAuth login start:
  /oauth2/authorization/{registrationId}

OIDC/OAuth callback (Spring Security Servlet default):
  /login/oauth2/code/{registrationId}

SAML2 SP ACS (phổ biến):
  /login/saml2/sso/{registrationId}

CAS filter processing URL (Spring CAS Javadoc default):
  /login/cas
~~~

Không bảo vệ bằng một regex “mọi đường chứa `/login`” rồi bỏ qua callbacks custom, reverse proxy rewrites, aliases hoặc query. **Danh sách endpoint thực** phải đến từ ứng dụng và IdP/SP metadata/callback configuration.

Ví dụ rò dữ liệu:
- Nginx access log dùng request line trên `/login/cas?ticket=...`.
- Spring filter debug in `request.getQueryString()` tại `/login/oauth2/code/corp`.
- WAF ghi POST `SAMLResponse` lên sự kiện chặn request.
- Application error page echo `RelayState` hoặc query `redirect_uri`.
- OAuth client library log HTTP token response chứa `refresh_token`.
- Frontend analytics gửi full `location.href` khi URL còn `code`/`state`.
- API GET request tự gắn `access_token` vào URL.

Hãy kiểm **route và kiểu dữ liệu riêng**, không chỉ thay access log format của Spring.

## 16. Java 17 độc lập: logging bằng route allowlist thay vì raw URL

Mục tiêu ví dụ: mô phỏng một callback OAuth/CAS/SAML và sinh audit event **không chứa query/token**. Code dùng **`java.net.URI`** và allowlist những route cố định; không đọc request body, Authorization headers hay cookies vào log. Không kết nối với IdP, **không thực hiện authentication** và **không phải sanitizer production**: mục đích là hiểu phương pháp **chỉ log dữ liệu được phép**.

Tạo file **`AuthUrlSafeAuditDemo.java`**:

~~~java
import java.net.URI;

public final class AuthUrlSafeAuditDemo {

    enum Outcome { OK, REJECTED }

    static String route(URI uri) {
        return switch (uri.getPath()) {
            case "/login/cas" -> "CAS";
            case "/login/oauth2/code/corp" -> "OIDC";
            case "/login/saml2/sso/corp" -> "SAML";
            default -> "OTHER";
        };
    }

    static String safeMethod(String method) {
        return switch (method) {
            case "GET" -> "GET";
            case "POST" -> "POST";
            default -> "OTHER";
        };
    }

    static String event(String method, URI uri, Outcome result) {
        return "event=auth_callback route=" + route(uri)
                + " method=" + safeMethod(method)
                + " status=" + result;
    }

    public static void main(String[] args) {
        URI cas = URI.create(
            "https://portal.example/login/cas"
            + "?ticket=ST-EXAMPLE-SECRET&service=portal");

        URI oidc = URI.create(
            "https://portal.example/login/oauth2/code/corp"
            + "?code=AUTH-CODE-EXAMPLE&state=OPAQUE");

        URI saml = URI.create(
            "https://portal.example/login/saml2/sso/corp");

        String casLog = event("GET", cas, Outcome.OK);
        String oidcLog = event("GET", oidc, Outcome.OK);
        String samlLog = event("POST", saml, Outcome.REJECTED);

        System.out.println(casLog);
        System.out.println(oidcLog);
        System.out.println(samlLog);

        String allLogs = casLog + "\n" + oidcLog + "\n" + samlLog;
        boolean excludesSecrets =
                !allLogs.contains("ST-EXAMPLE-SECRET")
                && !allLogs.contains("AUTH-CODE-EXAMPLE")
                && !allLogs.contains("OPAQUE");

        System.out.println("No sample credentials in logs: "
                + excludesSecrets);

        System.out.println("CAS callback has query: "
                + (cas.getRawQuery() != null));

        System.out.println("SAML body not logged: "
                + !samlLog.contains("SAMLResponse"));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac AuthUrlSafeAuditDemo.java
java AuthUrlSafeAuditDemo
~~~

**Stdout chính xác:**

~~~text
event=auth_callback route=CAS method=GET status=OK
event=auth_callback route=OIDC method=GET status=OK
event=auth_callback route=SAML method=POST status=REJECTED
No sample credentials in logs: true
CAS callback has query: true
SAML body not logged: true
~~~

Giải thích:

- `URI.create` chứa **giá trị giả**, mô phỏng browser URL có CAS ticket và OAuth code; chương trình không in `uri.toString()`.
- Hàm `route` chỉ trả **nhãn endpoint cố định**, không đưa raw path hoặc query string vào log. Một đường không nằm allowlist được gắn `OTHER`.
- `safeMethod` chỉ cho GET/POST, không in HTTP method string bất thường do attacker gửi.
- `Outcome` là enum giới hạn trạng thái; không log ngoại lệ chứa token.
- `No sample credentials in logs: true` khẳng định output từ **hàm demo** không chứa các mã giả được đặt trong hai URIs. Không có nghĩa hệ thống thực không log ở proxy/APM.
- `CAS callback has query: true` chứng tỏ callback hợp lệ vẫn có URL query, nên test **không thể chỉ chặn mọi query**.
- `SAML body not logged: true` chỉ là ví dụ không đưa body vào hàm; **không chứng minh WAF/Tomcat/APM của một server thật không lưu SAMLResponse**.

**Không dùng ví dụ để bỏ kiểm `Authorization`/`SAMLResponse` của framework**: phải giữ protocol validation đầy đủ. Hàm audit chỉ được gọi **sau khi đã định nghĩa các audit fields không chứa secret**.

## 17. Tích hợp audit log an toàn ở Spring Security

Một app thật nên thiết kế audit event trong authentication success/failure handlers hoặc một service riêng, với **ít fields và key cố định**:

~~~java
// Pseudocode fragment: cần bean logger và event model theo ứng dụng.
String protocol = "OIDC";   // từ registrationId đã cấu hình
String endpoint = "oidc_callback"; // static route ID
String outcome = "SUCCESS"; // high-level enum

auditLogger.info("protocol={} endpoint={} outcome={}",
        protocol, endpoint, outcome);

// Không làm:
// logger.info("callback={}", request.getRequestURL());
// logger.info("query={}", request.getQueryString());
// logger.info("parameters={}", request.getParameterMap());
// logger.info("idToken={}", oidcUser.getIdToken().getTokenValue());
~~~

Trong hệ thống đa IdP, chỉ log **registration ID nội bộ đã biết**, không dump full issuer access token, `userinfo` JSON hoặc SAML XML. Nếu cần audit user identity, lưu **internal user ID** sau khi validation và data access policy cho log, không cần raw OIDC `sub`/NameID/email nếu không có lý do.

### Exception và lỗi auth

- Log `errorCode=INVALID_SIGNATURE`, `errorCode=EXPIRED_TOKEN`, `errorCode=CAS_TICKET_REPLAY` ở dạng enum nội bộ.
- Không gửi `AuthenticationException.getMessage()` nguyên văn nếu provider có thể nối token/request vào message.
- Chỉ hiển thị generic login error cho browser, dùng correlation ID độc lập để support.
- Không log toàn bộ `Saml2AuthenticationToken`, `OAuth2AuthenticationToken`, `BearerTokenAuthentication` hoặc credential-bearing properties qua `toString()` nếu chưa biết semantics.

**Redaction tại SIEM là lớp cuối, không thay việc từ chối thu thập**. Với performance traces, chỉ truyền high-level outcome/provider ID/duration mà không truyền full `url.full` trên auth callback.

## 18. URL “sạch” và lịch sử trình duyệt: làm khi nào?

Sơ đồ đúng cho callback có code/ticket:

~~~text
Browser:
  /login/oauth2/code/corp?code=...&state=...
      -> Spring validates callback
      -> exchange code once
      -> creates authenticated session
      -> redirects 303/302 to /reports (no query tokens)

Final browser URL:
  https://portal.example/reports
~~~

Việc redirect sạch giúp **không giữ code/ticket trong URL trang ứng dụng**. Tuy nhiên browser history hoặc logs có thể vẫn lưu URL callback ban đầu. Vì vậy **không dựa vào redirect đơn lẻ**; phải kết hợp giảm TTL/one-time, PKCE, Referrer-Policy, log exclusion và cache controls.

### JavaScript history.replaceState dùng được không?

Trong SPA, `history.replaceState({}, "", "/app")` có thể loại query/fragment khỏi **URL hiện tại** sau khi callback đã được parse và xử lý hợp lệ, nhưng:
- JavaScript đã chạy tức là credential có thể từng tồn tại trong runtime.
- Không xóa raw URLs khỏi proxy logs, old history/sync records, browser extensions hoặc analytics phát trước cleanup.
- Không kiểm được token signature/issuer chỉ nhờ replaceState.
- Phải tránh phá `state`/`nonce` validation hoặc callback processing.

Với Spring MVC server-side OIDC/CAS, ưu tiên xử lý callback **ở server** rồi redirect sạch trước khi render, không cần chuyển raw credentials tới JavaScript.

## 19. Phòng chống leak từ HTML, analytics, redirects và error pages

Các tình huống nhỏ dễ bị bỏ sót:

1. **Analytics capture full URL:** `window.location.href` trên trang callback mang `code`/`state` và được gửi cho analytics vendor. Ngăn script chạy trên callback; cấu hình exclude query parameters và kiểm dữ liệu thật đã gửi.
2. **Error page echo raw URL:** “Login failed on /login/cas?ticket=...” làm xuất hiện ticket trong HTML, hỗ trợ screenshot và cache.
3. **Redirect giữ query:** `Location: /home?ticket=...` vô tình duy trì credential.
4. **Open redirect:** IdP/SP nhận `returnUrl=https://attacker.example` rồi redirect sau callback mang state/token trong query.
5. **Referer sang third party:** trang callback có image/script/link ngoài domain khi browser vẫn có code.
6. **Exception diagnostics:** SAML XML được hiển thị ra trang lỗi cho end-user để “dễ debug”.
7. **PDF/CSV export:** ứng dụng đưa token/NameID vào metadata/file name/QR code mà không có lý do.
8. **Copy/paste support ticket:** developer chụp address bar hoặc HAR chứa callback full URL.
9. **Browser autofill/extension:** extension có khả năng đọc URL/forms theo quyền đã cấp.
10. **Link previews/chat apps:** user chia sẻ callback link chứa CAS ticket hay OAuth code; preview bot có thể truy cập, làm rò hoặc làm ticket one-time bị tiêu thụ.

**Nguyên tắc:** callback endpoint nên là **điểm xử lý giao thức thuần**, không render third-party UI; error pages chỉ hiển thị mã lỗi tổng quát và đường trở lại login.

## 20. Java memory, thread dumps, heap dumps và secret lifecycle

Trong Spring/Java backend, token có thể tồn tại trong:
- `OAuth2AuthorizedClient`, `OAuth2AccessToken` và refresh token stores.
- `OidcIdToken`/`OidcUser`, Spring SecurityContext/HTTP session.
- `Saml2Authentication`/credential objects có Assertion XML hoặc attributes.
- CAS ticket validation payloads.
- HTTP client request/response buffers, Netty ByteBuf, servlet request params.
- Thread locals/MDC, exception cause chains, temporary strings, heap dump và crash report.

Không có cách thực tế đảm bảo Java `String` chứa một credential được “zeroize” ngay: immutable strings và GC có thể giữ dữ liệu tới khi bộ nhớ được thu hồi. Vì vậy:

- **Hạn chế sao chép credential** sang temporary strings/DTO/logging/JSON.
- Không giữ raw Assertion/ticket/code lâu hơn cần để validate.
- Chỉ lưu token ở approved credential store được mã hóa và giới hạn access, có rotation/TTL.
- Không giữ raw tokens trong MDC, `ThreadLocal`, business events, analytics payloads.
- Hạn chế quyền đọc heap dumps, core dumps, thread dumps, crash artifacts và backup/snapshot.
- Không bật `-XX:+HeapDumpOnOutOfMemoryError` lên một volume/world-readable hoặc auto-upload ra issue tracker mà chưa có policy.
- Có retention, encryption, key rotation và access audit cho observability/artifacts.
- Khi test, dùng fake tokens và đừng capture raw production traces.

**Không có thiết kế bảo mật nào nên dựa vào “token ở RAM nên an toàn tuyệt đối”.** XSS, RCE, memory dumps hoặc server compromise có thể lấy token; scope/TTL/audience và secret management vẫn cần.

## 21. Lỗi cấu hình và cách chẩn đoán

| Triệu chứng | Khả năng gây rò | Hướng sửa |
| --- | --- | --- |
| Ingress access logs có `?ticket=ST-...` | Log request target/query | Chuyển sang route/URI path-only; scrub mọi ingress |
| APM trace span chứa `code=...` | `url.full` hoặc tags tự động | Drop query/headers/body trước export |
| SAML XML xuất hiện trong WAF events | Request body sampling | Disable/redact SAMLResponse capture với rule phù hợp |
| Browser Back cho thấy trang trước logout | HTTP cache/bfcache/session policy | no-store + session invalidation + browser restore tests |
| Tokens xuất hiện trong localStorage | Frontend token persistence | BFF/HttpOnly cookie hoặc architecture giảm JS exposure |
| User gửi screenshot URL có CAS ticket | Address bar/history | Xử lý one-time + redirect clean + support policy |
| API dùng `?access_token=...` | Bearer query URI | Thay Authorization header qua HTTPS |
| Audit ghi ID Token và email đầy đủ | Incorrect logging design | Route/outcome allowlist + PII minimization |
| App 302 sang external redirect URL chứa state | Open redirect/returnUrl misuse | Validate target relative path/strict allowlist |
| “no-cache” nhưng browser giữ sensitive data | Thiếu no-store hoặc cache layer khác | Add no-store, kiểm CDN/Service Worker |
| Login callback có third-party tracking script | Referrer/JS execution | Remove third-party resources trên callback |
| XSS trên SPA đọc token | Web Storage/JS token access | CSP, XSS defense, BFF/token handling |
| Spring defaults có nhưng response vẫn cache | Controller/proxy override headers | Kiểm final response tại edge, sửa override |
| TLS tắt verify để debug | MITM có thể đọc credentials | PKIX truststore/hostname đúng |
| SAML Assertion có chữ ký nhưng lộ attributes | Signature không mã hóa | Minimization, SAML Encryption nếu cần |
| CAS ticket validation đúng nhưng logs chứa raw ticket | Đường logging riêng | Audit allowlist + ingress scrubbing |
| Logout không ngăn token còn sống | Token/session revoke khác nhau | Token TTL, revocation, backend checks |

**Không coi một kiểm thử HTTP 200 là đủ**. Test phải quan sát đúng trace/log/caching/history boundaries, đồng thời bảo đảm protocol login vẫn thành công và replay bị từ chối.

## 22. Ma trận kiểm thử chống rò cho từng giao thức

| Nhóm | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| OAuth callback | `code`/`state` ở URL callback | Protocol xử lý thành công, không xuất hiện trong logs/APM |
| PKCE | Code bị lấy nhưng thiếu verifier | Token endpoint từ chối exchange trái phép |
| Replay code | Đổi cùng code lần hai | Từ chối (one-time) |
| OAuth implicit | Access token trong fragment | Không bật legacy flow thiếu justification |
| API | Bearer token trong query | Client không gửi kiểu này; resource policy reject/disable |
| API | Authorization header hợp lệ | API validate issuer/audience/scope/expiry |
| OIDC tokens | Raw ID/refresh tokens | Không vào logs, JS analytics, URL, error pages |
| Multiple IdPs | Code từ IdP A đến callback B | Mix-up checks từ chối |
| Redirect target | External URL được ép qua query | Không có open redirect |
| CAS ST | `ticket` query tại callback | Ticket validate one-time, không bị log ở ingress/app |
| CAS replay | Dùng lại ST đã được validate | CAS reject |
| CAS service mismatch | ST phát cho service khác | SP/CAS reject |
| CAS proxy ticket | PT/PGT ở downstream contexts | Không log, phạm vi delegation được hạn chế |
| SAML POST | SAMLResponse hidden form | Browser POST qua TLS, ACS verify đầy đủ |
| SAML XML log | WAF debug body capture | Không xuất raw Assertion/NameID vào logs |
| SAML replay | Assertion ID đã dùng | Replay cache/validity reject |
| SAML wrong audience | Assertion cho SP khác | Reject |
| SAML Artifact | Đổi artifact lại lần hai | Reject/resolve theo profile |
| Cache auth pages | Cache-Control response | no-store, Pragma/Expires theo policy |
| Browser Back | Logout rồi Back | Không hiển thị/chấp nhận session data sai policy |
| CDN cache | User A và B cùng URL | Không reuse private auth/sensitive response |
| Referer | Callback tải external resources | Không gửi URL chứa code/ticket/state |
| Analytics | `location.href` trên callback | Query sanitized hoặc không có third party |
| Header logs | Authorization/Cookie/Set-Cookie | Redacted/omitted toàn bộ pipeline |
| HAR export | Raw trace login | Không phân phối ngoài hệ thống được phê duyệt |
| Browser storage | localStorage/sessionStorage/IndexedDB | Không chứa long-lived credentials theo policy |
| XSS | Script độc có thể chạy | CSP + XSS protection, không cấp quyền token dễ lấy |
| Session cookie | Flags và SameSite phù hợp callback | Secure/HttpOnly/SameSite, không session ID URL |
| Heap dump | App memory diagnostic | Restricted, encrypted, TTL, no public attachment |
| Failure handler | Auth exception có details | Chỉ error code/correlation ID, không token XML |
| Log redaction regression | New fields, query alias/encoded params | Allowlist vẫn không chứa credential |
| Load balancer config drift | Một node còn log full query | Automated config check phát hiện |
| Token issuer/key rollover | Thay khóa IdP | RP verify đúng, không fallback bỏ signature |
| Incident exercise | Có token giả được đưa vào logs | Alert/triage/revocation/purge thực thi được |

### Dùng synthetic credentials trong kiểm thử

Không dùng production bearer tokens để “xem log có giữ secret không”. Hãy tạo các mã giả có tiền tố dễ nhận diện như `TEST-CAS-ST-DO-NOT-USE`, gửi qua **test infrastructure được phép**, kiểm log của ingress/app/APM/SIEM bằng quy trình phù hợp. Sau đó đảm bảo test data không bị hiểu nhầm là token thật hay bị gửi vào alert vendors ngoài phạm vi.

Trên Spring MockMvc, có thể kiểm:
- Cache headers của protected response và callback failure.
- Referrer-Policy của response trước redirect và sau login.
- Không redirect user tới arbitrary external URL.
- Authentication success/failure không echo credentials.
- Structured audit event không chứa callback parameters.

**MockMvc không test được Nginx/WAF/Cloud CDN hoặc browser history**. Cần end-to-end tests quan sát các lớp này riêng.

## 23. Quy trình kiểm tra thực tế theo tầng

1. **Lập sơ đồ credential flow**: OIDC code/token endpoint, SAML POST/Artifact, CAS ST/PGT, cookies.
2. **Định nghĩa secret classification** cho mỗi field: bearer, one-time ticket, correlation state, PII.
3. **Kiểm callback endpoints** và proxy rewrites/IdP metadata; loại mọi đường không cần thiết.
4. **Kiểm URL/query logging** tại ingress, LB, CDN, web server và app.
5. **Kiểm POST body logging** tại WAF, reverse proxies và error reporting cho SAML.
6. **Kiểm HTTP client wire logs** tại token/CAS validation back-channels.
7. **Kiểm response headers** trên các auth/PII routes sau toàn bộ proxies; no-store/no-referrer.
8. **Kiểm frontend**: analytics, third-party scripts, history handling, Service Workers, browser storage.
9. **Kiểm Spring framework flows**: state, nonce, PKCE, signature, audience, service binding, replay.
10. **Kiểm Java memory/artifacts**: dumps, exception payloads, session/token stores, MDC, APM spans.
11. **Test user A/B** tránh cached private data được chia sẻ; test Back/logout.
12. **Test negative cases**: replay, wrong audience, token in query, open redirect, forged SAML/expired CAS ST.
13. **Thử incident runbook** với synthetic tokens, log discovery, revoke, purge và audit.
14. **Ghi ownership**: network/platform, IdP/IAM, app, security monitoring, support processes.

Bất kỳ thay đổi lớn về APM agent, reverse proxy log format, CDN rules, Spring Security upgrade hoặc SSO protocol binding nên chạy lại một phần kiểm thử trên.

## 24. Khi đã lộ token/assertion/ticket: ứng cứu sự cố

Nếu phát hiện raw credential trong log, trace, ticket hỗ trợ hoặc browser storage **không chỉ xóa dòng log**. Thực hiện:

1. **Đánh giá phạm vi**: loại credential (access vs refresh, CAS ST, SAML Assertion, session cookie), issuer, audience, TTL, quyền và người có khả năng đọc.
2. **Ngăn nguồn rò tiếp diễn**: tắt raw query/body/header capture hoặc chặn pipeline; giữ evidence phù hợp pháp lý/audit.
3. **Thu hồi**: revoke tokens/refresh tokens nếu provider hỗ trợ; invalidate affected sessions, rotate client/service secrets khi cần. Với codes/tickets one-time, xác minh chúng đã bị dùng hay hết hạn và vẫn kiểm khả năng replay/misissuance.
4. **Kiểm access logs/API usage**: tìm dấu hiệu abuse theo identity, audience, IP/device và scope đã được duyệt, không phát tán credential trong lúc điều tra.
5. **Kiểm bản sao**: ingress logs, SIEM, APM, WAF, debug artifacts, screenshots, browser sync, backups, support tools, third-party processors.
6. **Purge/redact** theo retention/incident policy; không tuyên bố đã xóa mọi bản sao ở thiết bị người dùng nếu không chứng minh được.
7. **Đánh giá ảnh hưởng cá nhân và pháp lý**: SAML/ID Token chứa PII có thể cần quy trình thông báo riêng; không coi “one-time token hết hạn” là chắc chắn không có disclosure.
8. **Sửa thiết kế**: log allowlist, SSO callback isolation, cache controls, key/token rotation và automated regression tests.
9. **Document lessons learned** và cập nhật contract giữa IdP, app, proxy và logging platform.

**Không đăng lại mã token thật để hỏi support**. Khi cần chứng cứ, dùng correlation ID độc lập và thông tin time window đã được tối thiểu hóa.

## 25. Những câu hỏi thường gặp

**Hỏi:** OIDC Authorization Code trong query có phải lỗi bảo mật không?

**Đáp:** Không tự nó là lỗi: redirect query là flow chuẩn. Rủi ro là code có thể vào logs/history/Referer; giảm bằng PKCE, state, short TTL, exact redirect URI, redirect sạch, no-referrer và log scrubbing.

**Hỏi:** Đưa access token vào URL fragment có an toàn vì server không thấy `#`?

**Đáp:** Không. Fragment thường không gửi tới server, nhưng có trong browser/JS/history và có thể bị lấy bởi XSS/extensions. RFC 9700 không khuyến khích implicit grant phát access token qua front-channel.

**Hỏi:** SAMLResponse nằm trong hidden form, có nghĩa được mã hóa không?

**Đáp:** Không. Base64 là encoding, không phải encryption. Chữ ký chống sửa đổi nếu verify đúng; để giấu attributes khỏi browser/intermediaries cần cân nhắc encrypted assertions theo threat model.

**Hỏi:** CAS ticket vốn có `ticket` trong URL, phải tắt CAS không?

**Đáp:** Không. Hãy thực hiện đúng CAS service-ticket validation one-time/service binding, bỏ query khỏi logs, no-store/no-referrer, rồi chuyển đến clean URL. Không ghi lại ticket hoặc giữ nó trong application link.

**Hỏi:** Có `Cache-Control: no-store` là xóa được browser history không?

**Đáp:** Không. Nó chỉ điều khiển HTTP caching theo semantics, không phải lệnh xóa history, screenshot, APM logs hoặc Service Worker storage.

**Hỏi:** Dùng `Authorization: Bearer` có cần che log nữa không?

**Đáp:** Có. WAF/proxy/APM có thể ghi headers. Không thu thập Authorization, Cookie, Set-Cookie và token response body vào logs.

**Hỏi:** Có thể hash token và log để hỗ trợ debug không?

**Đáp:** Cần đánh giá tính tái định danh và độ đoán được của artifact. Ưu tiên event ID độc lập; nếu bắt buộc cần stable marker, dùng HMAC có secret và retention/access controls, không raw SHA trên low-entropy tokens một cách tùy tiện.

**Hỏi:** SameSite=Strict luôn tốt cho SSO?

**Đáp:** Không. Cross-site SAML POST ACS có thể cần SameSite=None; Secure hoặc cơ chế session-state khác, trong khi OIDC GET callback hay dùng Lax. Kiểm thực tế cùng CSRF và session rules; không hạ bảo mật một cách mù quáng.

**Hỏi:** Log của Spring đã sạch, còn cần kiểm gì?

**Đáp:** Ingress, CDN, load balancer, WAF, HTTP client wire logs, APM, centralized log collectors, browser analytics, HAR và crash/heap dumps.

## 26. Checklist để nghiệm thu

- [ ] Phân loại rõ OAuth code, ID/Access/Refresh Token, SAML Response/Artifact, CAS ST/PT/PGT, session cookies.
- [ ] Không đưa access token/refresh token vào URI query hoặc fragment để “tiện chia sẻ”.
- [ ] OIDC Authorization Code flow có PKCE, state/nonce, exact redirect, code one-time.
- [ ] Không bật legacy implicit token-in-browser flow thiếu đánh giá rủi ro.
- [ ] Không log nguyên callback URI/query ở Spring, ingress, CDN, WAF/APM.
- [ ] Không log POST body `SAMLResponse`, decoded Assertion, NameID/PII.
- [ ] CAS service tickets validate one-time và ràng buộc service URL.
- [ ] SAML signatures, audience, destination, recipient, timestamps, replay được kiểm.
- [ ] Token issuers, signatures, audiences, scopes và expirations được xác minh.
- [ ] Auth callback/error pages không dùng third-party analytics/scripts hoặc echo params.
- [ ] `Referrer-Policy: no-referrer` dùng trên các trang phù hợp.
- [ ] `Cache-Control: no-store` và compatibility headers áp đúng auth/private responses.
- [ ] Không cache auth callbacks/PII pages tại shared CDN/proxy.
- [ ] Cookie Secure/HttpOnly/SameSite phù hợp GET/POST federation callbacks.
- [ ] Không dùng URL rewriting chứa JSESSIONID hoặc session ID query.
- [ ] Browser storage không giữ long-lived tokens/session IDs theo policy.
- [ ] Service Worker Cache API không lưu token/PII auth data.
- [ ] Logs chỉ có route ID/method/result/correlation ID không chứa user credentials.
- [ ] Không log `Authorization`, `Cookie`, `Set-Cookie` hoặc HTTP client token responses.
- [ ] Dump/trace/HAR/crash reports có hạn chế quyền/retention và redaction.
- [ ] Sau login, browser được chuyển đến clean URL không có auth artifact.
- [ ] User A/B, Back/logout, Referer, redirect và cache regression tests đã PASS.
- [ ] Có test ngăn open redirect, code replay, CAS ST replay và SAML Assertion replay.
- [ ] Có incident runbook revoke/purge/notify/rotate và ownership rõ.
- [ ] Kiểm lại sau Spring/IdP/ingress/observability upgrades.

## 27. Tài liệu chính thức tham khảo

1. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth code/access token leakage qua Referer/history, PKCE, exact redirect URI, implicit flow và countermeasures.
2. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer via Authorization và nguy cơ query parameters.
3. [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): code challenge/verifier để chống authorization code interception.
4. [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): defaults Cache-Control/Pragma/Expires/HSTS và chính sách cache.
5. [Spring Security — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): Spring header configuration/overrides.
6. [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): redirect endpoint `/login/oauth2/code/*`.
7. [Spring Security — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): CAS `ticket` parameter, service URL and default `/login/cas`.
8. [OASIS — SAML V2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html): HTTP POST binding, SAMLResponse hidden form và ACS processing.
9. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): không log session IDs, access tokens, passwords và dữ liệu nhạy cảm.
10. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): browser Web Storage, session cookies, logout và session risks.
11. [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): localStorage/sessionStorage và XSS.
12. [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control): semantics no-store/no-cache/private.
13. [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): no-referrer và leak prevention.
14. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure/HttpOnly/SameSite cookie attributes.
15. [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verify bearer token, issuer, JWT claims và authorities.

**Ghi nhớ cuối bài:** dữ liệu xác thực phải đi đúng **kênh, thời gian sống và đối tượng nhận**; tránh biến callback URL, log, browser storage hay heap dump thành kho credential ngoài ý muốn. Với **OIDC**, dùng Authorization Code + PKCE và bảo vệ callback; với **SAML**, bảo vệ POST body, XML/claims và replay; với **CAS**, chấp nhận ticket trên URL đúng giao thức nhưng không lưu/log và phải validate một lần. Ở Spring và hạ tầng, dùng **log allowlist, no-store, no-referrer, HTTPS, session cookie an toàn, clean redirects, limited token retention và negative tests toàn tuyến**.