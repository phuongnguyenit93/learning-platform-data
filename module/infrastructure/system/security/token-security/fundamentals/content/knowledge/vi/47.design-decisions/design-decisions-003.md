# Chọn cookie hay Authorization header

## 1. Mục tiêu và phạm vi quyết định

Khi một ứng dụng cần gửi thông tin xác thực đến API, hai cách thường gặp là dùng cookie hoặc gửi access token trong HTTP Authorization header. Quyết định này ảnh hưởng trực tiếp đến cách trình duyệt lưu credential, cách request mang credential, nguy cơ CSRF/XSS, cấu hình CORS, khả năng thu hồi token và độ phức tạp khi vận hành.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, lựa chọn cần dựa trên mô hình tin cậy và vòng đời token: ai giữ token, thành phần nào xác thực token, audience/resource nào được gọi, token được lưu bao lâu và điều gì xảy ra khi credential bị đánh cắp. Cookie và Authorization header là hai cách vận chuyển thông tin xác thực; chúng không tự quyết định token là JWT hay opaque, cũng không thay thế việc kiểm tra issuer, audience, expiry, scope và quyền trên tài nguyên.

Sau bài học, người học có thể:

- Phân biệt cookie session, cookie chứa token và Bearer token trong Authorization header.
- Đánh giá CSRF, XSS, CORS và rủi ro lưu trữ token trong browser.
- Chọn mô hình phù hợp cho BFF, SPA, mobile app và service-to-service.
- Thiết kế cookie với Secure, HttpOnly, SameSite, Path và Domain phù hợp.
- Bảo vệ Authorization header và token khỏi log, URL, storage và mã JavaScript không tin cậy.
- Xây dựng kiểm thử cho xác thực, CSRF, CORS, refresh, logout và thu hồi.

## 2. Trước hết: Cookie và Authorization header là hai cơ chế vận chuyển

**Cookie** là cơ chế HTTP để server yêu cầu browser lưu một cặp tên/giá trị và gửi lại theo các quy tắc domain, path, expiry và SameSite. Browser tự động đính kèm cookie phù hợp vào request. Cookie có thể chứa session identifier, opaque token hoặc JWT; cách lưu trữ và chính sách gửi cookie vẫn áp dụng như nhau.

**Authorization header** là header do client chủ động gửi trong từng request. Với OAuth 2.0 Bearer token, hình thức phổ biến là:

~~~http
GET /orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
~~~

Browser không tự động lấy một access token trong local storage rồi thêm Authorization header. Ứng dụng JavaScript phải đọc token từ nơi lưu trữ và gắn header; native/mobile client hoặc service cũng có thể chủ động thêm header bằng HTTP client.

Hai cách không hoàn toàn đối lập. Một ứng dụng browser có thể dùng cookie session để xác thực với Backend for Frontend (BFF), trong khi BFF gửi OAuth access token qua Authorization header đến các API nội bộ. Khi đó browser không cần giữ access token của downstream API.

### 2.1 Phân biệt ba mô hình hay bị gọi chung là cookie authentication

| Mô hình | Browser gửi gì? | Server xác thực thế nào? |
| --- | --- | --- |
| Session cookie | Session ID ngẫu nhiên, thường opaque | Tra cứu session server-side, kiểm tra trạng thái và quyền |
| Token cookie | JWT hoặc opaque access token trong cookie | Validate JWT hoặc introspection/tra cứu token |
| Authorization Bearer | Access token trong Authorization header | Validate JWT hoặc introspection/tra cứu token |

Session cookie không nhất thiết là OAuth access token. Nếu dùng session cookie, server có thể giữ access/refresh token trong kho server-side và browser chỉ giữ session ID. Cách này thường phù hợp với BFF hoặc ứng dụng web server-rendered.

## 3. So sánh cookie và Authorization header

| Tiêu chí | Cookie | Authorization header |
| --- | --- | --- |
| Cách gửi | Browser tự động gửi theo cookie rules | Client chủ động gắn header |
| CSRF | Có rủi ro do credential được gửi tự động; cần SameSite và/hoặc CSRF defenses | Ít chịu CSRF kiểu ambient cookie khi token chỉ được JavaScript/client gắn vào header |
| XSS | HttpOnly ngăn JavaScript đọc cookie, nhưng XSS vẫn có thể gửi request thay người dùng | Nếu token có thể đọc từ JavaScript, XSS có thể lấy token hoặc dùng nó gọi API |
| Lưu trữ | Browser cookie jar quản lý expiry/domain/path/flags | Ứng dụng phải chọn nơi lưu token, thường memory hoặc secure storage |
| Cross-origin | Cần cấu hình credentials, SameSite và CORS phù hợp | Cần CORS cho Authorization header; thường phát sinh preflight |
| Native/mobile | Có cookie jar nhưng quản lý session/cookie giữa API có thể phức tạp | Tự nhiên với HTTP client và secure storage của nền tảng |
| Service-to-service | Ít phổ biến cho bearer credential; có thể dùng cookie trong một số hệ thống legacy | Phù hợp với access token, workload identity và mTLS |
| Thu hồi | Session cookie có thể vô hiệu hóa bằng session store; token cookie cần token revocation/expiry | Tương tự token cookie nếu cùng loại token; header không tự cung cấp cơ chế revoke |
| Khả năng giới hạn phạm vi | Cookie domain/path và SameSite giúp kiểm soát nơi gửi, nhưng không thay audience/scope | Token được gửi tới endpoint do client chọn; server phải kiểm tra audience/scope |
| Nguy cơ log | Cookie/header Cookie có thể bị log | Authorization header có thể bị log |

Không có lựa chọn nào an toàn chỉ nhờ vị trí credential. Cần bảo vệ token, validate token và áp dụng policy ở resource server. Với cookie, phải xử lý CSRF; với token có thể đọc bởi JavaScript, phải giảm nguy cơ XSS và token exfiltration.

## 4. Rủi ro CSRF khi dùng cookie

Cross-Site Request Forgery (CSRF) xảy ra khi trình duyệt của người dùng tự gửi credential hợp lệ đến ứng dụng mà người dùng không chủ ý thực hiện thao tác đó. Cookie phù hợp với domain/path thường được browser tự động đính kèm, nên một trang độc hại có thể tìm cách khiến browser gửi request tới ứng dụng đang đăng nhập.

Ví dụ người dùng đã đăng nhập vào app.example.test. Một trang khác có thể cố gắng gửi form hoặc điều hướng browser tới endpoint thay đổi dữ liệu. Nếu session cookie được gửi tự động và server không kiểm tra CSRF, request có thể được xử lý như hành động của người dùng.

### 4.1 Các lớp phòng vệ CSRF

**SameSite** kiểm soát khi nào browser gửi cookie trong ngữ cảnh cross-site:

- **Strict:** hạn chế gửi cookie trong phần lớn điều hướng/request cross-site; bảo vệ mạnh hơn nhưng có thể ảnh hưởng luồng đăng nhập và liên kết từ site khác.
- **Lax:** cho phép cookie trong một số điều hướng top-level an toàn, thường là lựa chọn cân bằng cho session web.
- **None:** cho phép cookie trong ngữ cảnh cross-site; bắt buộc có Secure và thường cần thiết khi kiến trúc thực sự dùng cookie cross-site.

SameSite là một lớp phòng vệ, không nên được coi là biện pháp CSRF duy nhất cho mọi kiến trúc. Đối với request thay đổi trạng thái, có thể kết hợp:

1. Synchronizer token: server cấp CSRF token gắn với session; client gửi token ở header hoặc field được bảo vệ.
2. Signed double-submit cookie: server kiểm tra giá trị CSRF cookie và request token theo thiết kế có chữ ký/ràng buộc session; không dùng cách so sánh cookie/header đơn giản nếu có thể bị injection.
3. Kiểm tra Origin/Referer theo allowlist khi phù hợp.
4. Chỉ cho phép các HTTP method an toàn như GET/HEAD/OPTIONS không tạo side effect; không thay đổi dữ liệu qua GET.
5. Kiểm tra content type và quy tắc CORS đúng hợp đồng; không dùng CORS thay cho CSRF protection.

### 4.2 CORS không phải CSRF protection

CORS quyết định JavaScript ở origin khác có được đọc response hoặc thực hiện một số loại request hay không. Một form HTML đơn giản vẫn có thể gửi một số request cross-site mà không cần được phép đọc response. Vì vậy, chỉ cấu hình CORS không bảo đảm cookie-authenticated endpoint không bị CSRF.

Nếu dùng credentialed CORS, không dùng wildcard origin. Server phải trả origin cụ thể đã được allowlist và bật Access-Control-Allow-Credentials khi cần. Không phản chiếu bất kỳ Origin nào từ request. Preflight có thể giới hạn request có custom header, nhưng không phải ranh giới bảo mật duy nhất.

## 5. Rủi ro XSS và nơi lưu token

Cross-Site Scripting (XSS) cho phép mã JavaScript không tin cậy chạy trong origin của ứng dụng. Nếu access token nằm trong localStorage hoặc biến JavaScript có thể đọc, XSS có thể lấy token và gửi ra ngoài. Nếu token nằm trong HttpOnly cookie, JavaScript không thể đọc trực tiếp giá trị cookie, nhưng XSS vẫn có thể gửi request cùng cookie từ browser của nạn nhân.

| Nơi lưu | JavaScript đọc được? | Đặc điểm/rủi ro |
| --- | --- | --- |
| localStorage | Có | Tồn tại qua phiên browser; XSS có thể đọc và exfiltrate |
| sessionStorage | Có | Gắn với tab/session; vẫn đọc được khi XSS chạy cùng origin |
| JavaScript memory | Có trong runtime | Giảm persistence sau reload/đóng tab; XSS đang chạy vẫn có thể truy cập hoặc sử dụng |
| HttpOnly cookie | Không đọc bằng JavaScript | Giảm token theft qua đọc cookie; vẫn có CSRF và XSS request abuse |
| Server-side session/BFF | Token không nằm trong browser | Giảm exposure của OAuth token; cần bảo vệ session cookie và BFF |
| Native secure storage | Phụ thuộc nền tảng/API | Dùng Keychain/Keystore hoặc secure storage tương đương; bảo vệ thiết bị và process vẫn quan trọng |

Không có nơi lưu nào chống được mọi dạng XSS. Bảo vệ XSS gồm output encoding, tránh unsafe DOM sinks, sanitization đúng ngữ cảnh, Content Security Policy, kiểm soát dependency và giảm quyền của script. HttpOnly giúp ngăn đọc cookie, nhưng không làm cho ứng dụng miễn nhiễm XSS.

Không lưu access token hoặc refresh token trong URL query, fragment dùng như transport, analytics event, crash report hay log. URL thường bị lưu trong browser history, proxy, referrer hoặc access log. Dùng Authorization header hoặc cookie theo kiến trúc đã chọn.

## 6. Khi nào chọn cookie?

Cookie phù hợp khi browser là client chính và ứng dụng có thể kiểm soát server-side session hoặc BFF.

### 6.1 Ứng dụng web server-rendered

Ứng dụng web truyền thống thường dùng session cookie:

- Server tạo session sau khi người dùng đăng nhập.
- Browser nhận cookie chứa session identifier ngẫu nhiên.
- Cookie được đặt HttpOnly, Secure và SameSite phù hợp.
- Server lưu session state và liên kết với danh tính đã xác thực.
- Logout hoặc incident có thể vô hiệu hóa session server-side.

Ví dụ header:

~~~http
Set-Cookie: __Host-app_session=RANDOM_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Tiền tố __Host- yêu cầu Secure, Path=/ và không có Domain attribute theo quy tắc cookie prefix của browser hỗ trợ. Điều này giúp cookie bị giới hạn ở host tạo nó. Nếu không dùng prefix, vẫn nên ưu tiên host-only cookie bằng cách bỏ Domain khi không cần chia sẻ giữa subdomain.

Cookie session vẫn cần CSRF defense cho request thay đổi trạng thái. Server cũng cần rotate session ID sau đăng nhập hoặc thay đổi đặc quyền để giảm session fixation, đặt idle/absolute timeout và revoke session khi logout hoặc phát hiện compromise.

### 6.2 SPA dùng Backend for Frontend (BFF)

Với SPA, BFF có thể giữ OAuth access/refresh token ở server-side. Browser chỉ giữ session cookie HttpOnly/Secure/SameSite; BFF xác thực session rồi gọi downstream API bằng Authorization Bearer header.

~~~mermaid
sequenceDiagram
    participant B as Browser SPA
    participant F as Backend for Frontend
    participant A as Authorization Server
    participant R as Resource API
    B->>F: Request + HttpOnly session cookie
    F->>F: Validate session and CSRF
    F->>A: Authorization Code + PKCE flow (server side)
    A-->>F: Access/refresh token
    F->>F: Store tokens server-side
    F->>R: Authorization: Bearer access token
    R-->>F: API response
    F-->>B: Application response
~~~

Ưu điểm:

- OAuth tokens không cần được expose cho JavaScript của browser.
- BFF có thể giữ refresh token, thực hiện refresh rotation và quản lý logout/revocation.
- Browser chỉ cần session cookie và CSRF protection.
- Downstream token có thể được giới hạn audience/scope theo từng API.

Đổi lại, BFF phải quản lý session store, scale, CSRF, cookie và availability. BFF không loại bỏ XSS; script độc hại vẫn có thể gửi request qua session của người dùng. Cần kiểm tra Origin/CSRF và giới hạn hành động.

### 6.3 Cookie chứa access token

Có thể đặt access token trực tiếp trong HttpOnly cookie, nhưng cần đánh giá kỹ:

- Cookie được browser tự động gửi theo domain/path/SameSite, vì vậy CSRF vẫn là rủi ro.
- Cookie size có giới hạn và JWT lớn có thể vượt giới hạn header/cookie.
- Cookie domain quá rộng có thể làm credential được gửi đến nhiều subdomain.
- Resource server phải validate token như bình thường: signature/introspection, issuer, audience, expiry và scope.
- Logout/revoke phải xử lý token đã phát hành; xóa cookie ở browser không tự vô hiệu hóa token phía server.

Nếu dùng cookie chứa access token, phải có CSRF defense và chính sách thu hồi rõ ràng. HttpOnly không thay thế kiểm soát authorization ở API.

## 7. Khi nào chọn Authorization header?

Authorization header phù hợp khi client chủ động kiểm soát HTTP request và có nơi lưu credential phù hợp.

### 7.1 SPA gọi API trực tiếp

SPA có thể lấy access token qua Authorization Code Flow với PKCE và gửi:

~~~http
GET /profile HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
~~~

Vì browser JavaScript chủ động gắn header, credential không tự động được gửi trong các request cross-site như cookie. Điều này giảm CSRF kiểu ambient credential, nhưng cần CORS cho origin/header được phép. XSS vẫn có thể đọc token nếu token nằm trong nơi JavaScript truy cập được hoặc gọi API bằng token đang ở memory.

Nếu SPA giữ access token trong memory, thời gian tồn tại thường ngắn hơn localStorage, nhưng reload có thể yêu cầu lấy token lại. Không nên tự động chuyển sang localStorage chỉ để giữ token qua reload mà chưa đánh giá nguy cơ XSS và refresh token.

Refresh token cho public browser client cần tuân thủ chính sách bảo vệ hiện hành, chẳng hạn refresh token rotation hoặc sender-constrained token khi được hỗ trợ, cùng reuse detection và giới hạn thời gian. Không đặt refresh token dài hạn vào localStorage như một giải pháp mặc định.

### 7.2 Native/mobile client

Mobile app thường dùng Authorization header với access token:

- Lấy token bằng Authorization Code + PKCE qua external user-agent/browser khi phù hợp.
- Lưu refresh token trong Keychain/Android Keystore hoặc cơ chế secure storage của nền tảng.
- Giữ access token trong memory nếu có thể và chỉ gửi tới API có audience phù hợp.
- Không hardcode client secret trong ứng dụng native; public client không thể giữ secret tĩnh.
- Dùng TLS và kiểm tra certificate theo chính sách nền tảng.

Cookie jar có thể hữu ích trong một số luồng webview hoặc hệ thống legacy, nhưng cần quản lý chia sẻ cookie giữa browser/webview/native HTTP stack. Authorization header thường dễ kiểm soát hơn cho API call từ mobile app.

### 7.3 Service-to-service

Với workload/service-to-service, Authorization header Bearer token thường phù hợp:

- Workload identity xác thực với authorization server hoặc STS.
- Token có audience/resource và scope giới hạn cho service đích.
- Service gửi access token trong Authorization header qua TLS.
- Resource server kiểm tra issuer, signature/introspection, expiry, audience và scope.
- Có thể kết hợp mTLS hoặc sender-constrained token để giảm nguy cơ bearer token bị đánh cắp.

Không dùng cookie session người dùng để thay thế workload identity nếu không có thiết kế rõ ràng. Không chia sẻ một token hoặc client credential giữa nhiều workload không cùng ranh giới tin cậy.

## 8. Cookie flags và cấu hình thực tế

Với session cookie hoặc token cookie, cần xem xét:

| Attribute | Mục đích | Khuyến nghị |
| --- | --- | --- |
| Secure | Chỉ gửi qua HTTPS | Bật trong môi trường production |
| HttpOnly | Ngăn JavaScript đọc cookie | Bật cho session/access/refresh credential |
| SameSite | Hạn chế gửi cookie cross-site | Chọn Strict/Lax/None theo luồng; None phải có Secure |
| Path | Giới hạn path nhận cookie | Thường dùng / cho session toàn ứng dụng; không xem đây là ranh giới bảo mật mạnh |
| Domain | Chia sẻ cookie giữa host/subdomain | Bỏ Domain nếu không cần chia sẻ; ưu tiên host-only |
| Expires/Max-Age | Thời hạn cookie ở browser | Phù hợp với session/token lifecycle và policy logout |

Ví dụ Spring Boot/Spring Security có thể cấu hình session cookie qua application properties:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-app_session
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

Hãy xác nhận phiên bản Spring Boot và container hỗ trợ các thuộc tính cấu hình tương ứng. Cookie prefix __Host- yêu cầu không có Domain; nếu cấu hình framework tự thêm Domain, prefix sẽ không hợp lệ. Không copy cấu hình production vào local HTTP vì Secure cookie cần HTTPS để hoạt động đúng.

Với cookie cross-site, SameSite=None; Secure thường cần thiết, nhưng phải cân nhắc third-party cookie restrictions của browser. Không thiết kế hệ thống phụ thuộc vào cookie cross-site mà không kiểm thử trên browser mục tiêu. Có thể ưu tiên cùng-site deployment hoặc BFF để giảm phụ thuộc vào third-party cookies.

## 9. CORS và CSRF theo từng mô hình

| Mô hình | CORS | CSRF |
| --- | --- | --- |
| Same-origin web + session cookie | Thường không cần CORS | Có; dùng SameSite và CSRF token/Origin validation phù hợp |
| SPA cross-origin + cookie session | Credentials và allowlist origin cụ thể | Có; CORS không thay CSRF defense |
| SPA cross-origin + Authorization header | Cho phép origin và Authorization header; preflight thường xảy ra | Ít rủi ro CSRF ambient-cookie; vẫn cần chống XSS và bảo vệ token |
| Mobile/native + Authorization header | Không áp dụng browser CORS | Thường không có CSRF browser; vẫn cần xác thực, authorization và bảo vệ credential |
| BFF same-site + session cookie | Thường không cần CORS giữa browser và BFF | Có; BFF phải xác minh CSRF/Origin |

Không bật **Access-Control-Allow-Origin: *** cùng **Access-Control-Allow-Credentials: true**. Khi cần cookie credentials, trả origin cụ thể đã được allowlist và Vary: Origin phù hợp. Không phản chiếu Origin bất kỳ.

Nếu API chỉ chấp nhận Authorization header, hãy cân nhắc từ chối các request browser không có header xác thực phù hợp và không dựa vào cookie ambient credential. Nếu ứng dụng đồng thời hỗ trợ cookie và header, phải định nghĩa precedence rõ ràng để tránh một request bị xác thực bằng credential ngoài dự kiến.

## 10. Decision matrix: chọn theo loại client

| Bối cảnh | Lựa chọn thường phù hợp | Lý do/chú ý |
| --- | --- | --- |
| Web server-rendered, same-origin | Session cookie | Browser session tự nhiên; cần CSRF defense và session management |
| SPA + BFF | HttpOnly session cookie tới BFF; Bearer header từ BFF tới API | OAuth token ở server-side, browser giữ session |
| SPA gọi resource API trực tiếp | Authorization header với access token ngắn hạn | Client chủ động gửi; cần bảo vệ token khỏi XSS và CORS đúng |
| Native/mobile app | Authorization header | HTTP client chủ động; token lưu trong secure storage |
| Service-to-service | Authorization header Bearer token, có thể kèm mTLS | Hợp với workload identity, audience/scope và tự động hóa |
| Legacy app yêu cầu cookie-based SSO | Cookie session | Tích hợp thuận tiện; kiểm soát CSRF, domain và logout |
| API nhận cả browser và machine client | Định nghĩa rõ từng auth mechanism hoặc tách endpoint/client | Tránh fallback mơ hồ và credential confusion |

### 10.1 Cây quyết định

~~~mermaid
flowchart TD
    A[Chọn cách gửi credential] --> B{Client là browser?}
    B -->|Không| H[Authorization header]
    B -->|Có| C{Có BFF hoặc server-side session?}
    C -->|Có| D[HttpOnly Secure session cookie tới BFF]
    D --> E[BFF giữ OAuth tokens server-side]
    E --> H
    C -->|Không| F{SPA gọi API trực tiếp?}
    F -->|Có| G[Bearer token trong Authorization header]
    G --> I[Token memory + XSS/CORS controls]
    F -->|Không| J[Session cookie cho web app]
    J --> K[CSRF defense + SameSite]
~~~

Đây là hướng dẫn định hướng, không phải luật tuyệt đối. Ràng buộc browser, domain, identity provider, API gateway, mobile platform, compliance và năng lực vận hành có thể làm thay đổi lựa chọn. Quyết định cuối phải ghi rõ threat model và cách kiểm chứng.

## 11. Logout, refresh và thu hồi token

Xóa cookie hoặc xóa token ở client chỉ xóa bản sao client đang giữ. Nó không nhất thiết thu hồi access token đã phát hành:

- Với session cookie, server-side session có thể bị invalidate; cookie phía browser cũng cần expire.
- Với token cookie, xóa cookie không làm JWT/opaque token tự mất hiệu lực ở resource server.
- Với Authorization header, xóa token trong memory/storage ngăn client gửi lại nhưng token bị sao chép vẫn có thể dùng đến khi hết hạn hoặc bị revoke.
- Refresh token cần revoke/rotation theo issuer policy; logout nên xử lý cả session và token family nếu ứng dụng có lưu giữ.

Một luồng logout có thể:

1. Xác thực session/client hiện tại.
2. Gọi revocation endpoint cho refresh token hoặc token cần thu hồi nếu authorization server hỗ trợ.
3. Xóa token server-side và invalidate session.
4. Gửi Set-Cookie với cùng name/path/domain scope và Max-Age=0/Expires đã qua để browser xóa cookie.
5. Xóa access token trong memory ở SPA/mobile.
6. Xác nhận logout và xử lý IdP session theo yêu cầu OIDC nếu có.

Không tuyên bố logout đã thu hồi mọi access token nếu hệ thống chỉ xóa cookie/local state. Với JWT được validate offline, revoke tức thời thường cần denylist, introspection, token version hoặc thời hạn ngắn kết hợp cơ chế phù hợp.

## 12. Kiểm thử bảo mật cho quyết định cookie/header

Kiểm thử phải bao phủ cả request hợp lệ và các cách lạm dụng credential:

| ID | Kịch bản | Kết quả kỳ vọng |
| --- | --- | --- |
| AUTH-01 | Session cookie hợp lệ, request same-origin | Được xác thực theo session |
| AUTH-02 | Cookie thiếu hoặc session hết hạn | Bị yêu cầu xác thực lại |
| AUTH-03 | Cookie session thiếu CSRF token trên POST | Bị từ chối |
| AUTH-04 | CSRF token sai hoặc thuộc session khác | Bị từ chối |
| AUTH-05 | Request cross-site gửi cookie với SameSite policy | Cookie được gửi/chặn đúng theo browser và policy |
| AUTH-06 | Origin không nằm allowlist trong credentialed CORS | Không được cấp CORS access |
| AUTH-07 | Authorization Bearer token hợp lệ | Được xác thực nếu issuer/audience/expiry hợp lệ |
| AUTH-08 | Authorization token hết hạn hoặc chữ ký sai | 401 theo hợp đồng |
| AUTH-09 | Bearer token thiếu scope | 403/insufficient_scope theo hợp đồng |
| AUTH-10 | Request không có Authorization nhưng có cookie không được endpoint chấp nhận | Không được fallback xác thực ngoài policy |
| AUTH-11 | XSS test marker được gửi trong request | Token không xuất hiện trong DOM/log; CSP và output encoding được kiểm tra |
| AUTH-12 | Authorization/Cookie header đi qua logging pipeline | Credential được redact hoàn toàn |
| AUTH-13 | Logout session cookie | Server-side session bị invalidate và browser cookie bị xóa |
| AUTH-14 | Logout khi access token đã bị sao chép | Token cũ bị revoke hoặc chỉ còn hiệu lực theo giới hạn được công bố |
| AUTH-15 | Refresh token rotation và reuse | Token family xử lý đúng policy; reuse bị phát hiện |
| AUTH-16 | Cookie Domain quá rộng hoặc Path sai | Test phát hiện cookie gửi tới host/path ngoài dự kiến |

Kiểm thử browser nên dùng automation chạy trên browser thật hoặc browser engine mục tiêu để xác nhận SameSite, Secure, CORS, preflight và cookie behavior. MockMvc có thể kiểm tra server-side CSRF/security filter, nhưng không mô phỏng đầy đủ quy tắc cookie của browser.

### 12.1 Kiểm tra CSRF với Spring Security

Ví dụ MockMvc cho endpoint thay đổi trạng thái:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void rejectsPostWithoutCsrfToken() throws Exception {
    mockMvc.perform(post("/profile/email")
            .session(validSession))
        .andExpect(status().isForbidden());
}

@Test
void acceptsPostWithValidCsrfToken() throws Exception {
    mockMvc.perform(post("/profile/email")
            .session(validSession)
            .with(csrf()))
        .andExpect(status().isOk());
}
~~~

Đoạn code giả định ứng dụng đã bật Spring Security CSRF và có fixture session hợp lệ. Status thực tế có thể được exception handler chuẩn hóa khác. Test này xác minh server-side CSRF behavior; cần browser test riêng cho SameSite và CORS.

### 12.2 Kiểm tra Authorization header

Với API Bearer, test cần xác minh:

- Không nhận token từ query parameter hoặc request body ngoài hợp đồng.
- Token được gửi đúng trong Authorization header.
- Resource server validate issuer, signature/introspection, audience, expiry và scope.
- Header không xuất hiện trong application log, reverse proxy log, trace hoặc error report.
- CORS chỉ cho phép origin và header cần thiết.

Không ghi token thật vào test fixture. Dùng token giả hoặc token test ngắn hạn từ authorization server thử nghiệm và redact toàn bộ credential trong test report.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Đặt access token trong cookie nhưng không có CSRF defense | Browser tự gửi token cross-site | SameSite, CSRF token và Origin validation |
| Dùng localStorage cho refresh token dài hạn | XSS có thể lấy credential bền vững | BFF/server-side token storage hoặc secure refresh design |
| Nghĩ HttpOnly chặn mọi XSS | Script độc hại vẫn có thể gọi API bằng cookie | CSP, output encoding, CSRF và authorization |
| Nghĩ CORS ngăn CSRF | Form/navigation có thể gửi request mà không đọc response | CSRF protection độc lập |
| Cookie Domain đặt quá rộng | Credential được gửi đến nhiều subdomain | Host-only cookie, __Host- prefix khi phù hợp |
| SameSite=None nhưng thiếu Secure | Cookie không đáp ứng yêu cầu browser | Bật Secure và HTTPS |
| Dùng wildcard CORS với credentials | Mở rộng origin trust không kiểm soát | Allowlist origin cụ thể |
| Chỉ xóa cookie khi logout | Token server-side vẫn có thể còn hiệu lực | Invalidate session và revoke token theo policy |
| API chấp nhận cả cookie lẫn header nhưng không có precedence | Credential confusion/fallback ngoài dự kiến | Quy định rõ auth mechanism theo endpoint |
| Log toàn bộ request headers | Token/cookie bị lộ trong log | Redaction allowlist và test logging pipeline |
| Dùng ID token để gọi API | Nhầm token xác thực client với access token | Resource API chỉ chấp nhận access token phù hợp |

## 14. Checklist ra quyết định

- [ ] Đã xác định loại client: browser web, SPA, BFF, native/mobile hay workload.
- [ ] Đã xác định browser có tự động gửi credential hay client chủ động gắn header.
- [ ] Đã phân biệt session cookie với cookie chứa access token.
- [ ] Nếu dùng cookie, có Secure, HttpOnly, SameSite và Domain/Path phù hợp.
- [ ] Cookie-authenticated state-changing request có CSRF protection.
- [ ] CORS chỉ cho origin cụ thể; không dùng wildcard với credentials.
- [ ] Nếu dùng Authorization header, token được lưu ở nơi phù hợp và không bị XSS dễ dàng lấy cắp.
- [ ] Không lưu token trong URL, log, analytics, crash report hoặc CI output.
- [ ] Resource server validate issuer, signature/introspection, audience, expiry và scope.
- [ ] BFF không expose OAuth access/refresh token cho JavaScript khi không cần thiết.
- [ ] Refresh token rotation/reuse detection và logout/revocation có thiết kế rõ.
- [ ] Có test CSRF, XSS-related controls, CORS, SameSite, expiry, scope, logout và redaction.
- [ ] Threat model ghi rõ rủi ro còn lại và cách vận hành khi token bị lộ.

## Tài liệu tham khảo

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách truyền access token trong Authorization header và các lưu ý bảo vệ bearer credential.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị hiện hành về bảo vệ OAuth clients, token và flow.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access token, refresh token, scope và authorization flow.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ authorization code flow cho public clients.
- **RFC 6265 — HTTP State Management Mechanism:** cookie storage và các thuộc tính cookie; browser behavior hiện đại còn phụ thuộc cập nhật và triển khai của user agent.
- **OWASP Cheat Sheet Series — CSRF Prevention:** các biện pháp chống Cross-Site Request Forgery.
- **OWASP Cheat Sheet Series — Session Management:** session identifier, cookie flags, rotation và logout.

Lựa chọn cookie hay Authorization header cần xuất phát từ loại client và threat model. Cookie phù hợp với browser session/BFF khi có CSRF defense và cookie flags đúng; Authorization header phù hợp với client chủ động gửi Bearer token như SPA gọi API trực tiếp, mobile và service-to-service. Dù chọn cách nào, token vẫn cần được bảo vệ, giới hạn audience/scope, kiểm tra tại resource server và quản lý thu hồi theo vòng đời.
