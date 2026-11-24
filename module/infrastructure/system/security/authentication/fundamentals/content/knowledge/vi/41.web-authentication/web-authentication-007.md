# Cross-site leakage — Ngăn rò rỉ dữ liệu xác thực giữa các website

Người dùng đăng nhập vào một ứng dụng tại accounts.example.com. Sau khi xác thực, ứng dụng chuyển họ tới một trang báo cáo. Trang này tải ảnh, script phân tích và widget hỗ trợ từ các nhà cung cấp bên ngoài. Một URL callback vẫn còn mã authorization trong query string; khi browser tải tài nguyên bên thứ ba, một số thông tin URL có thể xuất hiện trong Referer, log hoặc hệ thống telemetry. Một liên kết khác mở website không tin cậy và có thể làm lộ đường dẫn hiện tại. Cookie được đặt cho toàn bộ domain cha cũng khiến một subdomain ít được bảo vệ có thể tác động tới ranh giới xác thực.

**Cross-site leakage** là việc dữ liệu hoặc tín hiệu nhạy cảm từ một website/origin bị tiết lộ, suy luận hoặc chuyển tới một site/origin khác ngoài phạm vi dự kiến. Dữ liệu có thể là access token, authorization code, session identifier, email, trạng thái đăng nhập, nội dung response hoặc chỉ là tín hiệu cho biết người dùng đã truy cập một tài nguyên cụ thể.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này giúp người học hiểu ranh giới origin/site của trình duyệt, Same-Origin Policy (SOP), CORS, Referer, cookie, browser storage, cache, OAuth/OIDC redirect và các side channel kiểu XS-Leaks. Người học biết cách giảm dữ liệu xác thực xuất hiện trong URL, ngăn tài nguyên bên thứ ba nhận thông tin nhạy cảm, bảo vệ callback, truyền thông điệp giữa cửa sổ an toàn và cấu hình browser security headers. Mục tiêu là giữ dữ liệu xác thực trong đúng trust boundary khi ứng dụng điều hướng, nhúng nội dung hoặc giao tiếp với website khác.

## 1. Cross-site leakage là gì?

Cross-site leakage xảy ra khi một site có thể lấy được dữ liệu hoặc suy luận thông tin về site khác mà thiết kế không chủ định chia sẻ. Không phải mọi trường hợp đều là đọc trực tiếp response. Có thể là:

- **Direct disclosure:** token, code, session ID hoặc PII xuất hiện trong URL, Referer, log hay request gửi tới bên thứ ba.
- **Credential exposure:** cookie hoặc bearer token bị gửi tới host/subdomain không cần nhận chúng.
- **Cross-origin read:** cấu hình CORS cho phép origin không đáng tin đọc response chứa dữ liệu nhạy cảm.
- **Cross-window message leak:** postMessage gửi dữ liệu tới origin không đúng hoặc nhận message không xác minh nguồn.
- **Cache leakage:** response riêng tư được lưu và phục vụ lại trong ngữ cảnh browser/cache không phù hợp.
- **State inference:** site khác suy luận người dùng đã đăng nhập, đã truy cập tài nguyên hoặc có một dữ liệu nào đó thông qua timing, kích thước, trạng thái tải hay hành vi điều hướng.

Cross-site leakage có thể dẫn tới phishing, account enumeration, lộ thông tin cá nhân, đánh cắp token hoặc hỗ trợ một cuộc tấn công chiếm session. Dữ liệu bị rò không nhất thiết là password; một authorization code, session state hay tín hiệu đăng nhập cũng có thể có giá trị.

### 1.1. Phân biệt với XSS và CSRF

| Khái niệm | Vấn đề chính | Ví dụ |
| --- | --- | --- |
| Cross-site leakage | Dữ liệu hoặc tín hiệu từ site A bị tiết lộ/suy luận ở site B | URL callback chứa code bị gửi trong Referer |
| Cross-site scripting (XSS) | Attacker chạy script trong origin đáng tin | Script độc hại đọc token trong localStorage |
| Cross-site request forgery (CSRF) | Browser gửi request có tác dụng tới site đích bằng credential tự động đính kèm | Trang độc hại kích hoạt POST đổi email qua cookie session |
| Clickjacking | Người dùng bị lừa tương tác với UI được nhúng | Trang giả phủ nút trên iframe ngân hàng |
| Open redirect | Website đáng tin chuyển hướng tới đích do attacker kiểm soát | Callback login chuyển code/token tới domain attacker |
| XS-Leaks | Site khác suy luận thông tin qua các side channel của browser | Đo trạng thái load hoặc timing để suy ra người dùng có tài khoản |

Các lớp này có thể kết hợp. XSS có thể đọc dữ liệu cùng origin; CSRF có thể tạo request nhưng không nhất thiết đọc response; cross-site leakage có thể tiết lộ thông tin dù SOP chặn JavaScript đọc body. Một biện pháp như SameSite cookie không thay thế CORS, CSP, URL hygiene hoặc kiểm tra postMessage.

## 2. Origin, site và Same-Origin Policy

Browser dùng origin để cô lập nhiều website. Một origin được xác định bởi bộ ba:

- Scheme: ví dụ HTTPS.
- Host: ví dụ app.example.com.
- Port: ví dụ 443.

Hai URL chỉ cùng origin khi cả ba thành phần khớp theo quy tắc của browser. Vì vậy:

- https://app.example.com và https://app.example.com:443 thường cùng origin.
- http://app.example.com khác https://app.example.com.
- https://api.example.com khác https://app.example.com.
- https://app.example.com khác https://app.example.net.

**Site** là khái niệm rộng hơn origin, thường dựa trên scheme và registrable domain (eTLD+1). Hai subdomain như app.example.com và api.example.com có thể được xem là same-site nhưng vẫn khác origin. Sự khác nhau này quan trọng với SameSite cookie, CORS và SOP.

### 2.1. Same-Origin Policy

SOP giới hạn một document/script đọc dữ liệu từ origin khác. Nó ngăn JavaScript tùy ý truy cập DOM, response hoặc storage của site khác. Nhưng SOP không chặn mọi giao tiếp cross-origin:

- Browser có thể điều hướng tới site khác.
- Trang có thể gửi form hoặc tải ảnh/script theo các quy tắc cho phép.
- Một số resource có thể được nhúng nhưng response không cho script đọc.
- CORS có thể mở quyền đọc response cho origin được server cho phép.
- postMessage cho phép các window giao tiếp nếu ứng dụng chủ động gửi/nhận.

Vì thế, “SOP đang bật” không đồng nghĩa không thể rò rỉ dữ liệu. Một URL nhạy cảm vẫn có thể xuất hiện trong lịch sử, log hoặc Referer ngay cả khi trang ngoài không đọc được response của ứng dụng.

### 2.2. Same-site không đồng nghĩa cùng trust

Một subdomain cũ, môi trường preview, trang marketing hoặc hệ thống upload có thể được vận hành bởi đội khác và có mức bảo vệ yếu hơn. Dù browser coi nó là same-site, không nên tự động tin mọi sibling subdomain.

Ví dụ:

- app.example.com chứa ứng dụng đăng nhập.
- blog.example.com chạy CMS có plugin bên thứ ba.
- uploads.example.com phục vụ nội dung do người dùng tải lên.
- legacy.example.com không còn được cập nhật.

Nếu cookie session được đặt với Domain=.example.com, nhiều subdomain có thể nhận cookie đó. Một subdomain bị compromise có thể làm tăng nguy cơ session exposure hoặc cookie tossing. Ưu tiên host-only cookie và tách ứng dụng có trust level khác nhau sang domain riêng khi phù hợp.

## 3. Các nguồn cross-site leakage trong web authentication

| Nguồn | Dữ liệu có thể lộ | Rủi ro |
| --- | --- | --- |
| Query string/path | Authorization code, token, email, reset identifier | History, Referer, proxy/app log |
| Referer header | URL trang trước, có thể chứa path/query | Website hoặc analytics bên ngoài nhận thông tin |
| Third-party script | DOM, URL, user state và dữ liệu trang theo quyền script | Script vendor bị compromise hoặc thay đổi |
| Browser storage | Token/session metadata | XSS hoặc script cùng origin đọc được |
| Cookie domain rộng | Session cookie gửi tới nhiều subdomain | Subdomain compromise, cookie injection |
| CORS misconfiguration | Response API được origin ngoài đọc | Data exfiltration bằng JavaScript |
| postMessage | Token, user profile hoặc auth result | Gửi sai origin hoặc nhận message giả |
| Redirect/callback | Code, state hoặc token bị chuyển tới host sai | Open redirect, callback leak |
| Browser cache/service worker | Response riêng tư lưu lại | Dùng chung thiết bị, cache key sai, service worker scope rộng |
| Iframe/resource probing | Trạng thái đăng nhập hoặc dữ liệu suy luận | Clickjacking và XS-Leaks |
| Logs/analytics/error reporting | URL, header hoặc form metadata | Credential xuất hiện ngoài trust boundary |
| Download/filename/notification | PII hoặc trạng thái account | Hệ thống bên ngoài lưu metadata |

Phân tích phải xét cả dữ liệu được gửi trực tiếp lẫn dữ liệu có thể suy luận. Không chỉ tìm password trong log; một đường dẫn /users/123 hoặc query chứa email cũng có thể tiết lộ thông tin cá nhân.

## 4. URL, query string và Referer leakage

URL thường xuất hiện ở nhiều nơi: browser history, bookmark, sync, proxy, CDN, WAF, application access log, analytics, crash report và Referer. Vì vậy không nên đặt bí mật bearer hoặc dữ liệu nhạy cảm vào URL nếu có thể tránh.

### 4.1. Không đặt token hoặc secret trong URL

Tránh:

- Access token hoặc refresh token trong query/path.
- Session ID hoặc recovery secret trong URL.
- Password, OTP hoặc API key trong query parameter.
- PII không cần thiết trong redirect URI.

Đặc biệt, bearer token trong URL dễ bị copy, lưu lịch sử và gửi tới hệ thống khác. Fragment (#...) không được gửi trong HTTP request như query string, nhưng JavaScript trên trang vẫn có thể đọc fragment; nó cũng có thể xuất hiện trong browser history, crash/telemetry hoặc bị script cùng origin lấy.

Ưu tiên:

- Gửi credential qua Authorization header hoặc cookie được bảo vệ theo đúng mô hình.
- Với form nhạy cảm, dùng POST body qua HTTPS và không log body chứa secret.
- Với OAuth/OIDC, dùng Authorization Code Flow + PKCE và trao đổi code qua back-channel.
- Sau khi xử lý callback, redirect sang URL sạch không còn code/state nhạy cảm.
- Không đưa token vào HTML, DOM, data attribute hoặc JavaScript global.

### 4.2. Referer header

Khi browser tải tài nguyên hoặc điều hướng, nó có thể gửi Referer cho đích đến. Chính sách hiện đại thường giới hạn thông tin khi đi cross-origin, nhưng ứng dụng không nên dựa vào mặc định vì cấu hình, browser, embedded webview hoặc legacy client có thể khác nhau.

Ví dụ một trang:

https://accounts.example.com/oauth/callback?code=secret-code&state=opaque-state

Nếu trang callback tải script/image từ analytics.vendor.test, Referer có thể tiết lộ origin hoặc một phần URL tùy Referrer Policy. Dù code thường được bảo vệ bởi PKCE và dùng một lần, không nên để nó xuất hiện ở nơi không cần thiết.

Đặt policy rõ ràng:

~~~http
Referrer-Policy: no-referrer
Cache-Control: no-store
Pragma: no-cache
~~~

Với liên kết cụ thể mở tab mới, có thể dùng rel="noopener noreferrer" khi phù hợp. no-referrer giảm thông tin Referer gửi đi; noopener ngăn trang mới điều khiển opener. Cần hiểu hai mục đích khác nhau.

### 4.3. Redirect tới URL sạch

Callback nên:

1. Nhận code/state qua endpoint đã đăng ký.
2. Xác minh state và transaction phía server.
3. Trao đổi code qua back-channel với token endpoint.
4. Xóa transaction callback khỏi trạng thái pending.
5. Chuyển browser tới route sạch không chứa code/token.
6. Trả header no-store/no-referrer và không tải third-party resource trước khi URL được làm sạch.

Redirect không tự xóa URL khỏi browser history trong mọi trường hợp, nhưng giúp tránh các request tiếp theo tiếp tục mang callback URL làm Referer. Hạn chế log URL ở edge/proxy và application layer.

## 5. OAuth/OIDC callback và leakage

OAuth/OIDC có nhiều tham số bảo vệ transaction, nhưng ứng dụng vẫn phải xử lý response cẩn thận.

### 5.1. Authorization Code Flow + PKCE

Với public client như SPA/mobile, dùng Authorization Code Flow với PKCE. Authorization server trả authorization code tới redirect URI đã đăng ký. Client hoặc backend trao đổi code bằng code verifier. Code có thời hạn ngắn và chỉ dùng một lần.

Kiểm soát:

- Exact redirect URI allowlist; không dùng wildcard rộng hoặc redirect do query parameter tùy ý.
- Sinh state ngẫu nhiên, ràng buộc với browser transaction và kiểm tra ở callback.
- Sinh PKCE code_verifier ngẫu nhiên; chỉ gửi code_challenge trong authorization request.
- Dùng nonce cho OIDC ID token và kiểm tra nonce ở response.
- Trao đổi code tại token endpoint qua back-channel; không đưa access/refresh token vào redirect URL.
- Làm sạch callback URL sau khi hoàn tất.
- Không tải analytics, quảng cáo hoặc script bên thứ ba trên callback page.
- Không log query string callback chứa code/state.

PKCE giảm nguy cơ code interception; state chống login CSRF/response mix-up theo transaction; nonce ràng buộc ID token với authentication request. Chúng có vai trò khác nhau và không nên bỏ một cơ chế chỉ vì đã bật cơ chế khác.

### 5.2. Tránh implicit flow và token trong fragment

Implicit flow từng trả access token trực tiếp trong URL fragment. Mặc dù fragment không gửi trong HTTP request tới server, script cùng origin có thể đọc được và token có thể rò qua XSS, extension hoặc browser state. Với ứng dụng mới, ưu tiên Authorization Code + PKCE theo OAuth Security Best Current Practice.

### 5.3. Open redirect

Một callback hoặc route sau login không được redirect tới URL tùy ý do client cung cấp. Nếu attacker có thể khiến authorization response được chuyển tiếp tới domain của họ, code hoặc thông tin transaction có thể bị lộ.

- Dùng redirect URI exact match đã đăng ký.
- Với return path nội bộ, chuẩn hóa và allowlist route.
- Từ chối scheme/host ngoài dự kiến, protocol-relative URL và encoded bypass.
- Không dùng URL do Referer hoặc query parameter làm đích redirect tin cậy.
- Kiểm thử double encoding, Unicode hostname và nested redirect.

## 6. Cookie và ranh giới domain

Cookie có thể tự động được browser gửi theo domain/path/secure/samesite rules. Cấu hình cookie quyết định subdomain và cross-site request nào có thể mang session.

### 6.1. Host-only cookie

Nếu bỏ thuộc tính Domain, cookie là host-only và chỉ được gửi tới host đã đặt nó. Tránh đặt Domain=.example.com cho session cookie nếu không thật sự cần chia sẻ giữa subdomain.

Cookie session có thể dùng:

~~~http
Set-Cookie: __Host-session=<opaque-random-value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix __Host- yêu cầu Secure, Path=/ và không có Domain trong browser hỗ trợ; điều này giúp giảm cookie injection từ sibling subdomain. Cookie value phải là opaque, ngẫu nhiên và không chứa PII.

### 6.2. Secure, HttpOnly và SameSite

- **Secure:** chỉ gửi cookie qua HTTPS.
- **HttpOnly:** JavaScript không đọc trực tiếp cookie qua document.cookie; giảm khả năng XSS lấy raw session cookie nhưng không ngăn XSS thực hiện request cùng origin.
- **SameSite=Strict:** hạn chế cookie trong cross-site request; có thể ảnh hưởng login/SSO navigation.
- **SameSite=Lax:** cho phép một số top-level safe navigation; thường là lựa chọn cân bằng cho session cookie.
- **SameSite=None; Secure:** cho phép cookie trong cross-site context khi cần, nhưng phải có lý do và CSRF defense phù hợp.

SameSite dựa trên site chứ không phải origin. Một subdomain cùng registrable domain có thể vẫn là same-site. Vì vậy, SameSite không thay thế host-only cookie, CSRF token, Origin/Fetch Metadata validation hoặc trust boundary.

### 6.3. Cookie tossing và sibling subdomain

Một subdomain không tin cậy có thể cố đặt cookie cùng tên với Domain cha hoặc tạo cookie trùng tên/path. Ứng dụng cần:

- Ưu tiên host-only cookie và prefix __Host-.
- Không dùng tên cookie mơ hồ hoặc phụ thuộc thứ tự cookie trùng tên.
- Không tin cookie domain rộng được tạo bởi mọi sibling host.
- Tách upload/user-generated content sang site riêng khi có thể.
- Thu hồi và rotate session sau sự cố subdomain.

## 7. Browser storage và token exposure

### 7.1. localStorage và sessionStorage

Web Storage được phân tách theo origin, nhưng mọi script cùng origin có thể truy cập. Nếu access token nằm trong localStorage, XSS có thể đọc và gửi token ra ngoài. sessionStorage có lifetime gắn với tab/session hơn, nhưng vẫn đọc được bởi script cùng origin và có thể bị lộ qua XSS.

Không có một nơi lưu token hoàn toàn an toàn trước XSS. Lựa chọn storage phải theo threat model:

- Với web app có backend, cân nhắc Backend-for-Frontend (BFF): browser giữ session cookie HttpOnly, backend giữ access/refresh token và gọi API thay client.
- Nếu SPA giữ access token, giảm lifetime, scope, audience và bảo vệ chặt CSP/XSS; tránh lưu refresh token dài hạn trong JavaScript-accessible storage.
- Không lưu session ID hoặc bearer token trong IndexedDB, Cache API hoặc service worker chỉ vì chúng “khó nhìn thấy”.
- Không serialize credential vào Redux/state persistence, URL, crash report hoặc client analytics.

### 7.2. IndexedDB, Cache API và Service Worker

IndexedDB và Cache API vẫn thuộc origin storage và có thể được script cùng origin truy cập. Service worker có thể intercept request và giữ response trong cache. Nếu service worker bị thay thế bởi script độc hại hoặc cache policy sai, dữ liệu riêng tư có thể được giữ lại sau logout.

Kiểm soát:

- Không cache response chứa credential hoặc dữ liệu nhạy cảm nếu không cần.
- Dùng Cache-Control: no-store cho response authentication/callback/sensitive.
- Thiết kế logout để xóa session server-side và cache/token client-side phù hợp.
- Giới hạn service worker scope; review script update và deployment.
- Không để service worker cũ tiếp tục phục vụ trang đăng nhập hoặc callback lỗi thời.
- Không cache API response riêng tư bằng cache key thiếu tenant/user context.

### 7.3. BFF pattern

Trong BFF, browser gọi backend-for-frontend cùng origin bằng session cookie. BFF giữ OAuth tokens phía server và gọi API upstream. Điều này giảm token xuất hiện trong JavaScript/browser storage, nhưng BFF phải bảo vệ session cookie, CSRF, SSRF, token cache và upstream authorization.

~~~mermaid
flowchart LR
    B[Browser] -->|Host-only HttpOnly session cookie| F[BFF]
    F -->|Server-side access token| A[API / Resource server]
    F --> I[Authorization server]
    B -. không giữ refresh token .-> F
~~~

BFF không loại bỏ XSS: script độc hại cùng origin vẫn có thể gọi endpoint BFF bằng session của người dùng và đọc response mà browser cho phép. Cần CSP, output encoding, CSRF controls, reauthentication và authorization như bình thường.

## 8. CORS và dữ liệu API

CORS là cơ chế cho phép server khai báo origin nào được browser cho phép đọc response cross-origin. CORS không phải authentication, không ngăn mọi cross-origin request và không bảo vệ server khỏi non-browser client.

### 8.1. Cấu hình an toàn

Với API chứa dữ liệu nhạy cảm:

- Chỉ allowlist origin cụ thể, scheme/host/port chính xác.
- Không phản chiếu Origin tùy ý rồi trả Access-Control-Allow-Origin.
- Không dùng wildcard * cùng Access-Control-Allow-Credentials: true.
- Chỉ bật credentials khi cần và có CSRF defense.
- Chỉ expose các response header cần thiết.
- Giới hạn methods và request headers.
- Xử lý Origin: null một cách thận trọng; không allowlist rộng.
- Trả Vary: Origin khi response thay đổi theo Origin để cache không trộn kết quả.

Ví dụ policy cho một frontend được phép:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Authorization, Content-Type, X-CSRF-Token
Vary: Origin
~~~

Chỉ dùng Access-Control-Allow-Credentials khi browser cần gửi cookie hoặc credential mode. Khi bật, origin phải là origin tin cậy cụ thể; không echo bất kỳ Origin nào mà request cung cấp.

### 8.2. Vì sao CORS không chặn CSRF?

Một form HTML cross-site có thể gửi một số loại request tới site đích dù JavaScript của trang gửi không đọc được response. Nếu browser tự đính kèm cookie session, server vẫn có thể thực hiện hành động. Do đó:

- Dùng CSRF token cho state-changing request khi cookie là credential.
- Kiểm tra Origin/Referer theo policy.
- Dùng Fetch Metadata headers như Sec-Fetch-Site để bổ sung defense.
- Cấu hình SameSite cookie phù hợp.
- Không thực hiện thay đổi trạng thái qua GET.

CORS chủ yếu kiểm soát việc script đọc response; nó không thay thế CSRF protection.

## 9. postMessage và giao tiếp giữa window/iframe

postMessage cho phép hai browsing context giao tiếp cross-origin. Đây là cơ chế hữu ích cho popup login, embedded identity provider hoặc iframe, nhưng có thể làm lộ token nếu target origin quá rộng hoặc message receiver tin dữ liệu không xác minh.

### 9.1. Gửi message an toàn

- Dùng targetOrigin cụ thể, ví dụ https://app.example.com, không dùng * cho dữ liệu nhạy cảm.
- Chỉ gửi tối thiểu thông tin cần thiết; không gửi refresh token hoặc session secret nếu không bắt buộc.
- Không dùng wildcard vì window có thể điều hướng sang origin khác trước lúc message được gửi.

~~~javascript
const target = new URL("https://app.example.com");
popup.postMessage(
  { type: "AUTH_COMPLETE", transactionId: "opaque-tx-ref" },
  target.origin
);
~~~

### 9.2. Nhận message an toàn

- Kiểm tra event.origin exact match.
- Kiểm tra event.source là window/iframe mong đợi.
- Validate schema, type, length và transaction state.
- Kiểm tra message thuộc transaction hiện tại và chỉ xử lý một lần.
- Không tin origin string do message payload tự khai.
- Không đưa access token vào message nếu chỉ cần báo callback đã hoàn tất; backend có thể hoàn tất exchange bằng back-channel.

~~~javascript
window.addEventListener("message", (event) => {
  if (event.origin !== "https://id.example.org") return;
  if (event.source !== expectedIdentityPopup) return;
  if (!event.data || event.data.type !== "AUTH_COMPLETE") return;
  if (typeof event.data.transactionId !== "string") return;
  if (event.data.transactionId !== pendingTransactionId) return;

  completePendingLogin(event.data.transactionId);
});
~~~

Đoạn code là ví dụ minh họa; production cần xử lý popup lifecycle, replay, timeout, origin configuration theo environment và không coi message đơn lẻ là bằng chứng xác thực. Server vẫn xác minh state/code/token theo protocol.

## 10. XS-Leaks và suy luận trạng thái xác thực

XS-Leaks (Cross-Site Leaks) là nhóm kỹ thuật suy luận dữ liệu cross-origin qua side channel, dù SOP không cho đọc trực tiếp response. Attacker có thể quan sát:

- Thời gian tải resource.
- Resource có load, redirect hay lỗi.
- Kích thước response hoặc khác biệt rendering.
- Sự tồn tại của iframe/window hoặc navigation.
- Cache behavior và các trạng thái browser.
- Sự khác nhau trong phản ứng của endpoint khi user đăng nhập hoặc chưa đăng nhập.

Ví dụ, một site độc hại nhúng endpoint profile vào iframe rồi đo sự kiện load/timing để suy luận người dùng đã đăng nhập. Nó có thể không đọc được profile nhưng vẫn biết trạng thái authentication.

### 10.1. Giảm XS-Leaks

- Dùng COOP để cô lập browsing context và giảm khả năng liên kết opener.
- Dùng CORP/CORS phù hợp để kiểm soát việc resource được nhúng/đọc.
- Dùng CSP frame-ancestors hoặc X-Frame-Options để ngăn nhúng trang nhạy cảm.
- Tránh response khác biệt rõ rệt theo account existence nếu endpoint công khai.
- Giảm side effect và timing variation không cần thiết.
- Dùng Fetch Metadata để phân biệt cross-site navigation/resource request khi phù hợp.
- Không để endpoint kiểm tra trạng thái account trả response dễ suy luận cho anonymous caller.
- Phân vùng cache và không cache dữ liệu nhạy cảm công khai.

Không phải mọi timing difference đều có thể loại bỏ. Cần ưu tiên endpoint chứa thông tin nhạy cảm, đánh giá attacker có thể quan sát tín hiệu nào và giảm độ phân biệt có ý nghĩa.

## 11. Browser security headers và isolation

Các header sau giúp giảm một số đường leakage:

| Header | Vai trò | Lưu ý |
| --- | --- | --- |
| Referrer-Policy | Giới hạn thông tin Referer được gửi | no-referrer phù hợp trang callback/secret-bearing |
| Cache-Control | Điều khiển cache | no-store cho response xác thực/nhạy cảm |
| Content-Security-Policy | Giới hạn script/resource/frame | Giảm XSS và third-party resource exposure |
| X-Frame-Options / CSP frame-ancestors | Kiểm soát nhúng trang | Ưu tiên CSP frame-ancestors cho policy hiện đại |
| Cross-Origin-Opener-Policy (COOP) | Cô lập browsing context group | Có thể ảnh hưởng popup/SSO; kiểm thử flow |
| Cross-Origin-Resource-Policy (CORP) | Giới hạn site/origin nào được tải resource | Chọn same-origin/same-site/cross-origin theo nhu cầu |
| Cross-Origin-Embedder-Policy (COEP) | Yêu cầu tài nguyên cross-origin được phép embed | Có thể ảnh hưởng tích hợp third-party |
| X-Content-Type-Options | Ngăn MIME sniffing | Dùng nosniff |
| Permissions-Policy | Giới hạn browser features | Không thay authentication, nhưng giảm bề mặt |

Ví dụ header cho trang nhạy cảm:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{random}'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
~~~

Nonce CSP phải được sinh mới cho từng response và gắn đúng với script được phép. Không copy nonce cố định vào template. CSP không sửa được logic XSS nếu policy quá rộng hoặc nonce bị tái sử dụng.

### 11.1. COOP/COEP và popup authentication

COOP có thể cô lập trang khỏi browsing context group khác, giúp hạn chế opener-based leakage. Nhưng cấu hình quá nghiêm có thể làm popup OAuth/SSO mất liên kết window.opener hoặc phá flow callback dùng postMessage. Thiết kế phải chọn mô hình popup/redirect rõ ràng, kiểm thử các browser mục tiêu và không hạ policy toàn site chỉ để sửa một integration không được kiểm soát.

## 12. Third-party scripts, analytics và supply chain

Script bên thứ ba chạy trong document có thể truy cập DOM và dữ liệu mà origin đó cho phép. Một analytics tag, chat widget, A/B testing script hoặc tag manager bị compromise có thể đọc URL, nội dung trang và form state.

Trên trang login, MFA, recovery và OAuth callback:

- Không tải script quảng cáo, analytics hoặc widget không thiết yếu.
- Nếu cần analytics, chỉ gửi event tối thiểu, không gửi URL query, email, token hoặc form field.
- Dùng CSP allowlist/nonce và hạn chế script-src.
- Dùng Subresource Integrity (SRI) cho tài nguyên static bên ngoài khi phù hợp.
- Pin version, review quyền vendor và có quy trình tắt script khẩn cấp.
- Không đưa secret vào dataLayer, global JavaScript object hoặc DOM attribute.
- Tách trang nhạy cảm khỏi tag manager chung nếu không thể kiểm soát tag.

SRI giúp phát hiện nội dung resource bị thay đổi so với hash mong đợi, nhưng không giải quyết script vendor hợp lệ có quyền quá rộng hoặc lỗ hổng logic trong script.

## 13. Cache, browser history và logout

Response chứa thông tin authentication hoặc dữ liệu riêng tư cần có cache policy phù hợp. Browser cache, shared proxy và service worker có thể lưu response ngoài ý muốn.

### 13.1. Cache control

- Dùng Cache-Control: no-store cho login page, callback, token response, recovery page và response chứa dữ liệu nhạy cảm khi không cần cache.
- Với dữ liệu cá nhân cần cache riêng, dùng private và policy có thời hạn ngắn, đồng thời cache key phải phản ánh đúng user/tenant.
- Không dựa vào Pragma: no-cache một mình cho HTTP hiện đại; cấu hình Cache-Control rõ.
- Đảm bảo CDN không cache response xác thực theo URL chung hoặc bỏ qua Vary.
- Không cache redirect callback chứa code/token.

### 13.2. Logout

Logout cần:

1. Thu hồi hoặc vô hiệu hóa session phía server.
2. Xóa cookie bằng cùng name/path/domain attributes đã dùng khi set.
3. Xóa token khỏi memory/storage phía client theo mô hình ứng dụng.
4. Xóa cache/service worker entry chứa dữ liệu nhạy cảm khi cần.
5. Điều hướng tới trang sạch, không mang token hoặc session identifier.
6. Xử lý IdP logout/federated session theo protocol nếu có.

Xóa cookie ở browser nhưng không revoke session server-side có thể để session cũ tiếp tục dùng được nếu cookie bị đánh cắp. Ngược lại, revoke session nhưng không xóa browser state có thể gây lỗi trải nghiệm hoặc lộ dữ liệu trong UI cũ.

## 14. Java/Spring: cấu hình response và callback an toàn

Ví dụ dưới đây minh họa một số thiết lập server-side. Tên API có thể thay đổi theo phiên bản Spring; hãy dùng security framework được duy trì và kiểm thử với deployment thực tế.

### 14.1. Security headers và cookie session

~~~java
http
    .headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
            .policyDirectives(
                "default-src 'self'; object-src 'none'; base-uri 'none'; " +
                "frame-ancestors 'none'; form-action 'self'"
            )
        )
        .referrerPolicy(referrer -> referrer
            .policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER)
        )
        .frameOptions(frame -> frame.deny())
    )
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
    );
~~~

Cookie session cần được cấu hình Secure, HttpOnly, SameSite và host-only theo deployment. Ví dụ cấu hình ứng dụng có thể đặt cookie name với prefix __Host-, Path=/, Secure và không có Domain. Không copy cấu hình mẫu mà bỏ qua yêu cầu HTTPS, SSO và CSRF của hệ thống.

### 14.2. Làm sạch callback URL

Pseudocode controller:

~~~java
ResponseEntity<Void> oauthCallback(
        String code,
        String state,
        HttpServletRequest request) {

    PendingAuthTransaction tx =
        transactionStore.findByBrowserSessionAndState(
            request, state
        );
    if (tx == null || tx.isExpired() || tx.isConsumed()) {
        return ResponseEntity.status(401).build();
    }

    TokenResponse tokens = oauthClient.exchangeCode(
        code,
        tx.codeVerifier(),
        tx.redirectUri()
    );

    oidcValidator.validate(tokens.idToken(), tx.nonce());
    sessionService.createAuthenticatedSession(tx.subject(), tokens);
    transactionStore.consume(tx.id());

    return ResponseEntity.status(303)
        .header("Cache-Control", "no-store")
        .header("Referrer-Policy", "no-referrer")
        .location(URI.create("/app/home"))
        .build();
}
~~~

Đây là pseudocode. Production cần kiểm tra state constant-time hoặc theo cách an toàn của framework, issuer/audience/signature/nonce của ID token, PKCE verifier, exact redirect URI, transaction binding, CSRF và one-time consume nguyên tử. Không log code, state, token response hoặc URL callback đầy đủ. Tốt nhất dùng OAuth2/OIDC client support đã được duy trì thay vì tự triển khai protocol.

### 14.3. CORS allowlist

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("https://app.example.com"));
config.setAllowedMethods(List.of("GET", "POST"));
config.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-CSRF-Token"));
config.setAllowCredentials(true);
config.setMaxAge(600L);
~~~

Chỉ bật allowCredentials nếu thực sự cần browser gửi cookie/credential. Không kết hợp wildcard origin với credentials; cần thêm Vary: Origin khi response phụ thuộc origin. CSRF vẫn phải được xử lý riêng.

## 15. Kiểm thử cross-site leakage

Kiểm thử cần quan sát cả network, browser storage, history, Referer, cache và log. Dùng browser profile thử nghiệm và dữ liệu giả; không dùng token production hoặc account thật.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| OAuth callback chứa code/state | Không tải third-party resource trước khi xử lý; URL được làm sạch |
| Callback URL điều hướng sang origin ngoài | Từ chối theo exact redirect allowlist |
| Callback page tải analytics script | Không có third-party script trên trang nhạy cảm |
| Referer từ trang chứa token | Policy no-referrer không gửi URL nhạy cảm |
| Link mở tab mới | Không cho trang đích điều khiển opener; Referer bị giới hạn theo policy |
| Session cookie | Secure, HttpOnly, SameSite và host-only; không gửi qua HTTP |
| Sibling subdomain bị kiểm soát | Không nhận session cookie host-only; không thể cookie-toss session __Host- |
| API trả CORS cho origin lạ | Browser không được phép đọc response |
| CORS có credentials | Chỉ origin allowlist cụ thể, không echo origin tùy ý |
| Origin: null | Từ chối trừ trường hợp được policy phê duyệt rõ |
| postMessage từ origin lạ | Receiver bỏ qua |
| postMessage từ window không mong đợi | Receiver bỏ qua |
| postMessage có transaction ID cũ | Từ chối replay |
| Token trong localStorage | XSS test cho thấy script cùng origin có thể đọc; kiến trúc đánh giá BFF/mitigation |
| Sensitive response được cache | Cache-Control và CDN policy ngăn lưu ngoài ý muốn |
| Service worker giữ response private | Logout/cache cleanup xử lý theo policy |
| Cross-site form gửi mutation | CSRF protection từ chối |
| Trang login bị nhúng iframe | frame-ancestors/X-Frame-Options chặn nếu không được phép |
| XS-Leak probing trạng thái login | Không tiết lộ dữ liệu nhạy cảm qua khác biệt dễ quan sát |
| Direct API request ngoài browser | Authentication/authorization vẫn được kiểm tra; không dựa vào CORS |
| Log/analytics/tracing | Không có raw token, code, session ID hoặc PII không cần thiết |
| Logout | Session server-side bị revoke và browser state được dọn phù hợp |

### Tình huống thực hành

Một ứng dụng dùng OAuth/OIDC. Sau login, authorization server redirect về /callback?code=...&state=.... Trang callback tải analytics.js và chat-widget.js trước khi backend xử lý code. Sau đó ứng dụng lưu access token trong localStorage. Session cookie đặt Domain=.example.com để dùng chung cho app.example.com và blog.example.com. CORS phản chiếu mọi Origin và cho phép credentials. Backend chỉ tin X-User-Id do gateway chuyển tiếp mà không xác thực gateway-to-upstream.

**Yêu cầu:** xác định đường leakage và thiết kế lại.

**Hướng phân tích:**

1. Callback page không tải third-party script; xử lý code ở back-channel, kiểm tra state/nonce/PKCE và redirect tới URL sạch.
2. Đặt no-referrer và no-store; redaction query string ở CDN, proxy, application log và analytics.
3. Cân nhắc BFF để giữ access/refresh token phía server; nếu SPA giữ access token, giảm TTL/scope và bảo vệ XSS nghiêm ngặt.
4. Đổi cookie sang host-only __Host- cookie với Secure, HttpOnly, SameSite phù hợp; không chia sẻ session với blog subdomain.
5. CORS dùng exact origin allowlist; credentials chỉ bật khi cần và CSRF được bảo vệ riêng.
6. Gateway strip identity header do client gửi, xác minh token đầy đủ và truyền principal qua kênh mTLS/workload identity.
7. Backend xác minh gateway identity, không tin header từ nguồn bất kỳ, và vẫn kiểm tra quyền theo resource/tenant.
8. Bổ sung kiểm thử Referer, history, storage, cache, CORS, postMessage, direct upstream access và log redaction.

## 16. Câu hỏi tự kiểm tra

1. **Cross-site leakage là gì?** Dữ liệu hoặc tín hiệu từ một site/origin bị tiết lộ hay suy luận ở site/origin khác ngoài phạm vi dự kiến.
2. **SOP có ngăn mọi cross-origin request không?** Không. Nó chủ yếu giới hạn đọc dữ liệu; navigation, form và một số resource request vẫn có thể xảy ra.
3. **Same-site có nghĩa cùng origin không?** Không. Hai subdomain có thể same-site nhưng khác origin.
4. **Vì sao không đặt access token trong URL?** URL có thể xuất hiện trong history, Referer, proxy log, analytics và telemetry.
5. **CORS có thay CSRF protection không?** Không. CORS kiểm soát đọc response cross-origin; CSRF cần bảo vệ request có tác dụng dùng cookie.
6. **HttpOnly ngăn được điều gì và không ngăn được gì?** Nó ngăn JavaScript đọc cookie trực tiếp, nhưng không ngăn XSS gửi request cùng origin bằng session của nạn nhân.
7. **Vì sao host-only cookie tốt hơn Domain rộng?** Nó giới hạn host nhận cookie và giảm rủi ro từ sibling subdomain.
8. **postMessage cần kiểm tra gì?** Exact origin, source window, schema, transaction và trạng thái one-time.
9. **BFF loại bỏ XSS không?** Không. Nó giảm token trong JavaScript storage nhưng XSS vẫn có thể gọi BFF bằng session hiện tại.
10. **Vì sao callback OAuth cần URL sạch?** Giảm khả năng code/state xuất hiện trong Referer, history, log và request tiếp theo.

**Ghi nhớ:** Cross-site leakage không chỉ là lộ token; trạng thái đăng nhập và tín hiệu về dữ liệu cũng có thể bị suy luận. Giữ credential khỏi URL và Referer, dùng callback OAuth/OIDC có state/nonce/PKCE, cookie host-only, CORS allowlist, postMessage exact-origin, cache policy và browser isolation headers. Không nhầm SOP/CORS/SameSite với authentication hay CSRF defense; bảo vệ cả chặng client, gateway và backend, đồng thời kiểm tra log, analytics và third-party scripts.
