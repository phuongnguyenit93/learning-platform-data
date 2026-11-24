# Token storage: lựa chọn nơi lưu token trong browser

## 1. Token storage là gì?

Ứng dụng web thường dùng token để chứng minh một request thuộc về phiên hoặc danh tính đã được xác thực. Token có thể là access token, refresh token, ID token, opaque session identifier hoặc một credential ngắn hạn khác do hệ thống phát hành.

**Token storage** là cách ứng dụng giữ và sử dụng credential đó giữa các request, lần tải trang và phiên làm việc. Trong browser, lựa chọn nơi lưu token ảnh hưởng trực tiếp tới khả năng chống XSS, CSRF, đánh cắp credential, lạm dụng session và rò rỉ dữ liệu trên thiết bị dùng chung.

Các vị trí thường được cân nhắc gồm JavaScript memory, sessionStorage, localStorage, IndexedDB, cookie do browser quản lý và Backend-for-Frontend (BFF), nơi token OAuth được giữ ở server còn browser chỉ giữ session cookie. Web Crypto hoặc service worker có thể hỗ trợ một số use case, nhưng không tự biến browser thành kho bí mật.

Không có một nơi lưu token an toàn tuyệt đối trước mọi loại tấn công. Người viết ứng dụng phải xác định attacker có thể chạy JavaScript cùng origin hay không, thiết bị có được dùng chung không, request dùng cookie hay bearer token, và credential cần tồn tại bao lâu.

Bài học thuộc chương **Browser token security** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web; nghiên cứu Same-Origin Policy, CORS, XSS, CSRF, CSP, Trusted Types và security headers. Bài này tập trung vào lựa chọn nơi lưu access token, refresh token và session credential trong browser, vòng đời token, OAuth cho public client và cách giảm thiểu rủi ro khi credential bị lộ.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt access token, refresh token, ID token và session cookie.
2. Giải thích vì sao browser application là public client và không thể giữ client secret.
3. So sánh memory, sessionStorage, localStorage, IndexedDB và cookie.
4. Phân tích rủi ro XSS khi token có thể được JavaScript đọc hoặc sử dụng.
5. Phân tích rủi ro CSRF khi browser tự động gửi cookie.
6. Chọn kiến trúc BFF hoặc SPA token handling theo threat model.
7. Áp dụng Authorization Code Flow với PKCE cho browser public client.
8. Quản lý access token expiration, refresh rotation, reuse detection và revocation.
9. Tránh token xuất hiện trong URL, log, telemetry, source map và message không tin cậy.
10. Hiểu giới hạn của mã hóa client-side, Web Crypto và service worker.
11. Thiết kế logout, multi-tab coordination và xử lý session hết hạn.
12. Kiểm tra token storage bằng DevTools và xây dựng checklist production.

## 2. Phân biệt các loại token và credential

Không phải mọi token đều có cùng mục đích hoặc vòng đời.

| Loại | Mục đích | Cách sử dụng |
| --- | --- | --- |
| Access token | Cho phép client gọi resource server trong phạm vi nhất định | Gửi tới API phù hợp, thường qua Authorization: Bearer. |
| Refresh token | Xin access token mới khi access token hết hạn | Chỉ gửi tới authorization server/token endpoint; cần bảo vệ chặt hơn access token. |
| ID token | Mang thông tin xác thực về người dùng trong OpenID Connect | Client kiểm tra theo quy trình OIDC; không dùng thay access token để gọi API. |
| Opaque session ID | Tham chiếu tới session được server quản lý | Thường đặt trong cookie HttpOnly và tra cứu trạng thái ở server. |
| CSRF token | Chứng minh request thay đổi trạng thái đến từ luồng hợp lệ của ứng dụng | Gửi theo cơ chế CSRF đã thiết kế; không dùng làm access token. |
| One-time ticket | Credential ngắn hạn cho một hành động hoặc kết nối cụ thể | Giới hạn audience, thời hạn, số lần sử dụng và phạm vi quyền. |

### 2.1. Access token và refresh token khác nhau

Access token thường có thời hạn ngắn và quyền giới hạn theo audience, scope hoặc resource. Khi hết hạn, client có thể xin token mới theo grant được cấp.

Refresh token thường có giá trị lâu hơn và có thể cấp access token mới. Nếu bị đánh cắp, attacker có thể duy trì quyền truy cập lâu hơn access token hiện tại. Vì vậy, refresh token cần vòng đời, rotation, phát hiện reuse và cơ chế revoke chặt hơn.

Không lưu access token và refresh token như hai chuỗi dữ liệu tương đương. Mỗi loại cần chính sách lưu trữ và xử lý riêng.

### 2.2. ID token không phải credential gọi API

Trong OpenID Connect, ID token là assertion về kết quả xác thực người dùng dành cho client. Nó thường là JWT và có các claim như issuer, subject, audience, expiration và nonce.

Không gửi ID token tới API như thể đó là access token. Resource server cần access token được phát hành cho audience/resource của nó và phải xác minh token theo đúng cơ chế.

### 2.3. JWT không tự động là dữ liệu bí mật

JWT thường có dạng JWS được ký và payload chỉ được Base64URL encode, không phải mã hóa. Người có token thường có thể decode header/payload để đọc claim. Chữ ký giúp xác minh tính toàn vẹn theo thuật toán/khóa được cấu hình; nó không che giấu nội dung.

Không đưa password, private key hoặc dữ liệu cá nhân không cần thiết vào claim. Dù token có opaque hay JWT, hãy coi credential là dữ liệu nhạy cảm và không log giá trị của nó.

## 3. Browser application là public client

JavaScript chạy trong browser được tải xuống thiết bị của người dùng. Người dùng có thể xem bundle, đặt breakpoint, sửa biến và quan sát request. Vì vậy, một ứng dụng browser không thể giữ bí mật một client secret được nhúng trong code.

Trong OAuth, SPA chạy trực tiếp trong browser thường được xem là **public client**. Không đặt client_secret vào JavaScript bundle, biến môi trường được build vào frontend, HTML/runtime config công khai, localStorage, IndexedDB hoặc source map.

Nếu authorization server yêu cầu confidential client authentication, thực hiện phần đó ở backend/BFF. Không giả vờ biến SPA thành confidential client bằng cách obfuscate client secret.

### 3.1. Public key và secret key

Một số hệ thống có publishable key hoặc client ID được thiết kế để xuất hiện ở browser. Chúng không phải private credential, nhưng vẫn cần giới hạn quyền, domain, quota và phạm vi sử dụng theo tài liệu nhà cung cấp.

Phân biệt rõ:
- Client ID/public key: có thể công khai theo thiết kế.
- Client secret/private key/service credential: chỉ giữ ở môi trường server được kiểm soát.
- User access token/refresh token: credential của phiên người dùng, phải bảo vệ dù không phải client secret.

## 4. Threat model cho token trong browser

Trước khi chọn storage, xác định attacker có thể làm gì.

| Threat | Mục tiêu của attacker | Hệ quả |
| --- | --- | --- |
| XSS cùng origin | Đọc token từ storage hoặc sử dụng quyền của trang | Gửi request như người dùng, đánh cắp token nếu đọc được. |
| CSRF | Khiến browser gửi cookie tới server mà người dùng không chủ ý | Thực hiện request thay đổi trạng thái nếu server thiếu phòng vệ. |
| Thiết bị/profile dùng chung | Truy cập browser còn đăng nhập hoặc còn dữ liệu | Dùng lại session hoặc xem dữ liệu tài khoản trước. |
| Malware/extension có quyền rộng | Đọc hoặc sửa dữ liệu trang/browser tùy quyền | Có thể quan sát credential và thao tác phiên. |
| Token rò qua URL/log | Thu thập credential từ history, proxy, analytics hoặc ticket | Replay token cho tới khi hết hạn/revoke. |
| Backend/API authorization yếu | Dùng token hợp lệ gọi tài nguyên vượt quyền | Rò dữ liệu hoặc thay đổi tài nguyên trái phép. |

Không có storage client nào ngăn được malware kiểm soát thiết bị. Mục tiêu thực tế là giảm khả năng script độc lấy credential, giới hạn quyền và thời gian sống của token, đồng thời giữ mọi quyết định authorization ở server.

### 4.1. XSS và CSRF là hai rủi ro khác nhau

XSS cho phép script độc chạy trong origin của ứng dụng. Script đó có thể đọc localStorage/sessionStorage/IndexedDB mà origin được phép truy cập và có thể gửi request trong context của user.

CSRF lợi dụng việc browser tự gửi cookie trong một số request cross-site. Attacker có thể không đọc response nhưng vẫn cố kích hoạt hành động. HttpOnly giúp giảm việc đọc cookie bằng JavaScript nhưng không tự ngăn CSRF.

Thiết kế token storage phải xử lý cả hai threat model, không chọn một thuộc tính cookie rồi coi mọi rủi ro đã được giải quyết.

## 5. So sánh các vị trí lưu token

| Vị trí | JavaScript cùng origin đọc được? | Tồn tại sau reload? | Rủi ro chính |
| --- | --- | --- | --- |
| Memory | Có, khi code có reference | Thường không | XSS có thể lấy hoặc sử dụng token khi trang đang chạy. |
| sessionStorage | Có | Có trong page session | XSS đọc được; tồn tại qua reload và có thể bị lạm dụng trong tab. |
| localStorage | Có | Có, thường lâu dài | XSS đọc được; credential tồn tại lâu trên profile. |
| IndexedDB | Có qua API | Có | XSS cùng origin có thể đọc/ghi; cleanup và lifecycle phức tạp. |
| Cookie HttpOnly | Không qua document.cookie | Theo cookie expiry/session | Browser tự gửi cookie; cần CSRF defense và bảo vệ session phía server. |
| BFF session cookie | Không qua document.cookie nếu HttpOnly | Theo session policy | Giảm token OAuth ở browser; cookie session vẫn cần CSRF defense. |

Bảng này là mô hình tổng quát. Browser policy, partitioning, private browsing, extension và cấu hình ứng dụng có thể làm thay đổi chi tiết. Điểm quan trọng là Web Storage/IndexedDB không có thuộc tính HttpOnly; JavaScript cùng origin có thể truy cập chúng.

## 6. Lưu token trong JavaScript memory

Memory storage giữ token trong biến của ứng dụng, closure hoặc state manager. Ví dụ:

~~~js
let accessToken = null;

function setAccessToken(value) {
  accessToken = value;
}

function getAccessToken() {
  return accessToken;
}
~~~

Ưu điểm:
- Token thường mất khi reload hoặc đóng context.
- Không để credential tồn tại lâu trong localStorage.
- Có thể giới hạn lifetime trong một lần chạy ứng dụng.
- Dễ xóa reference khi logout hoặc hết phiên.

Giới hạn:
- JavaScript cùng origin có thể truy cập token nếu có đường tới biến/API cung cấp token.
- XSS có thể dùng token trực tiếp hoặc gửi request trong context trang.
- Token mất sau reload nên cần cơ chế khôi phục session hoặc đăng nhập lại.
- State có thể bị lộ qua debugger, crash dump hoặc telemetry nếu code ghi log.

### 6.1. Memory không đồng nghĩa an toàn trước XSS

Nếu XSS chạy trong trang, nó có thể thay đổi DOM, gọi các hàm ứng dụng, monkey-patch API hoặc gửi request trong session hiện tại. Việc token không nằm trong localStorage có thể giảm khả năng attacker lấy lại token sau khi trang đã đóng, nhưng không ngăn hành động trái phép khi script độc đang chạy.

Memory storage là một biện pháp giảm persistence, không phải ranh giới chống XSS.

### 6.2. Phù hợp khi nào?

Memory-only access token có thể phù hợp cho SPA có access token ngắn hạn, không cần giữ token qua reload và có luồng tái xác thực phù hợp. Cần kết hợp XSS defense, token scope hẹp, expiry ngắn và refresh strategy được thiết kế riêng.

## 7. sessionStorage

sessionStorage lưu key/value dạng string theo origin và page session/browsing context. Dữ liệu thường còn sau reload tab nhưng mất khi page session kết thúc theo hành vi browser.

Ví dụ dưới đây chỉ minh họa API đọc/ghi; không phải khuyến nghị mặc định để lưu access token:

~~~js
sessionStorage.setItem("access_token", accessToken);

const token = sessionStorage.getItem("access_token");
~~~

Ưu điểm:
- Không tồn tại lâu như localStorage trong nhiều luồng sử dụng.
- Có thể giữ state qua reload trong tab.
- Dễ xóa khi kết thúc flow hoặc logout.

Rủi ro:
- JavaScript cùng origin đọc được.
- XSS có thể đọc và exfiltrate token.
- Token có thể tồn tại lâu hơn dự kiến nếu tab/session được restore.
- Không phải vault hoặc cơ chế mã hóa.
- Không tự đồng bộ an toàn giữa các tab.

### 7.1. sessionStorage không phải bảo vệ XSS

Nếu script độc chạy cùng origin, nó có thể gọi sessionStorage.getItem(). Không nên đặt refresh token dài hạn trong sessionStorage chỉ vì dữ liệu được giới hạn theo tab.

### 7.2. Trường hợp dùng hợp lý

sessionStorage có thể lưu state không phải secret, chẳng hạn bước wizard hoặc transaction state ngắn hạn. Với credential, chỉ dùng khi threat model chấp nhận JavaScript access và đã có biện pháp giảm thiểu phù hợp.

## 8. localStorage

localStorage giữ dữ liệu theo origin qua nhiều lần tải trang và thường qua lần đóng/mở browser profile. Ví dụ dưới đây minh họa API; việc lưu access token ở localStorage làm token có thể bị mọi script cùng origin đọc và không được ưu tiên cho credential nhạy cảm.

~~~js
localStorage.setItem("access_token", accessToken);

const token = localStorage.getItem("access_token");
~~~

Điểm thuận tiện là mọi tab cùng origin có thể truy cập dữ liệu, nhưng đây cũng là rủi ro:
- XSS có thể đọc token.
- Token tồn tại lâu hơn một page session.
- Browser profile dùng chung có thể giữ credential sau khi user rời máy.
- Code bên thứ ba chạy cùng origin có thể truy cập storage.
- Dữ liệu có thể bị sửa hoặc xóa bởi người kiểm soát browser.

### 8.1. Không lưu refresh token dài hạn trong localStorage

Refresh token thường có quyền cấp access token mới và giá trị cao khi bị đánh cắp. Đưa refresh token dài hạn vào localStorage tạo một mục tiêu dễ đọc cho bất kỳ script cùng origin nào.

Ưu tiên BFF giữ refresh token ở server hoặc một thiết kế authorization provider có rotation/reuse detection và giới hạn rõ ràng. Nếu sản phẩm buộc phải lưu token ở browser, phải công khai giới hạn XSS, giảm lifetime/scope và có khả năng revoke nhanh.

### 8.2. Xóa key không thu hồi token

~~~js
localStorage.removeItem("access_token");
~~~

Thao tác này chỉ xóa bản sao trong browser storage. Nếu attacker đã sao chép token, token có thể còn dùng được cho tới khi hết hạn hoặc server/provider revoke. Logout phải có phần server-side invalidation phù hợp.

## 9. IndexedDB và các kho lưu trữ khác

IndexedDB phù hợp dữ liệu có cấu trúc, dung lượng lớn và thao tác bất đồng bộ. Ứng dụng có thể lưu token ở đây, nhưng về bảo mật, IndexedDB vẫn có thể được JavaScript cùng origin truy cập.

Cache Storage và OPFS cũng không phải nơi cất credential bí mật:
- Cache Storage chứa Request/Response và có thể giữ dữ liệu nhạy cảm ngoài dự kiến.
- OPFS lưu file riêng cho origin nhưng không chống được script cùng origin có quyền truy cập.
- Service worker có thể đọc dữ liệu mà origin được phép và xử lý request trong background event.

Không chọn IndexedDB chỉ vì nó “khó xem hơn” localStorage. DevTools có thể hiển thị các kho này và XSS vẫn có thể truy cập bằng API tương ứng.

### 9.1. Phân vùng dữ liệu không thay authorization

Nếu lưu record theo user ID hoặc tenant ID, phải xác minh user hiện tại trước khi đọc/ghi. Client có thể sửa key, namespace hoặc record. Server vẫn kiểm tra quyền với mọi resource.

### 9.2. Cleanup khi đổi tài khoản

Khi logout hoặc chuyển user:
- Xóa token và dữ liệu phiên theo namespace.
- Dọn cache response chứa dữ liệu riêng tư.
- Đóng connection/worker liên quan nếu cần.
- Giữ bản nháp chưa đồng bộ cho tới khi có chính sách rõ ràng.
- Không coi việc xóa IndexedDB là thu hồi token ở authorization server.

## 10. Cookie HttpOnly và session credential

Cookie là cơ chế browser-managed. Browser tự gửi cookie phù hợp theo domain, path, secure transport, SameSite và credentials policy.

Ví dụ session cookie:

~~~http
Set-Cookie: __Host-session=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Thuộc tính:
- Secure: chỉ gửi cookie qua secure transport theo quy tắc browser.
- HttpOnly: JavaScript trang không đọc cookie qua document.cookie.
- SameSite=Lax: hạn chế một số request cross-site mang cookie; cần đánh giá luồng điều hướng và tích hợp.
- __Host- prefix: yêu cầu Secure, Path=/ và không có Domain attribute trong browser hỗ trợ, giúp giới hạn cookie ở host.

Cookie nên chứa opaque session identifier có entropy cao, không phải thông tin profile hoặc dữ liệu nghiệp vụ. Server giữ session state và có thể revoke session.

### 10.1. HttpOnly giảm đọc token, không chặn mọi XSS

HttpOnly ngăn JavaScript đọc giá trị cookie trực tiếp. Nhưng XSS vẫn có thể gọi API cùng origin; browser có thể tự đính kèm cookie và script có thể đọc response mà user được phép đọc.

Vì vậy HttpOnly giảm nguy cơ exfiltration credential qua document.cookie, nhưng không thay XSS prevention, CSRF defense hoặc server authorization.

### 10.2. Cookie và CSRF

Vì browser tự động gửi cookie trong request phù hợp, server phải bảo vệ endpoint thay đổi trạng thái khỏi CSRF.

Các lớp phòng vệ thường phối hợp:
- SameSite cookie phù hợp.
- CSRF token cho request state-changing khi kiến trúc yêu cầu.
- Kiểm tra Origin và/hoặc Fetch Metadata ở server.
- Không dùng GET cho thao tác thay đổi trạng thái.
- Kiểm tra content type và schema.
- Xác thực/authorization ở backend.

CORS không phải biện pháp CSRF. Một request có thể tới server dù attacker không đọc được response.

### 10.3. Xóa cookie đúng scope

Để hết hạn cookie, server gửi Set-Cookie với cùng tên và phạm vi Domain/Path phù hợp, đặt Max-Age=0 hoặc Expires trong quá khứ:

~~~http
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

JavaScript không thể xóa cookie HttpOnly trực tiếp. Server cần gửi response xóa cookie; đồng thời thu hồi session phía server.

## 11. BFF: giữ OAuth token ở backend

**Backend-for-Frontend (BFF)** là một backend dành riêng cho frontend. Browser đăng nhập qua BFF và nhận session cookie; BFF giữ access token/refresh token OAuth ở server, gọi resource API thay cho browser.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as BFF
    participant A as Authorization Server
    participant R as Resource API
    B->>F: Bắt đầu đăng nhập
    F->>A: Authorization Code Flow
    A-->>F: Authorization code
    F->>A: Đổi code + client authentication
    A-->>F: Access token + refresh token
    F-->>B: Session cookie HttpOnly
    B->>F: Request ứng dụng + session cookie
    F->>F: Xác minh session
    F->>R: API request bằng access token
    R-->>F: Resource response
    F-->>B: Response đã lọc
~~~

Ưu điểm:
- OAuth access/refresh token không cần lưu trong JavaScript browser.
- Client secret có thể giữ ở backend confidential client.
- BFF có thể giới hạn API và lọc dữ liệu trước khi trả về browser.
- Token rotation/revocation được tập trung ở server.

Chi phí:
- Cần backend session và hạ tầng vận hành.
- BFF phải bảo vệ cookie session khỏi CSRF.
- Cần quản lý session scale, timeout và logout.
- Browser vẫn nhận dữ liệu mà UI cần; BFF không giấu response khỏi người dùng kiểm soát browser.

### 11.1. Session cookie vẫn cần CSRF defense

BFF giảm việc đưa OAuth token tới browser nhưng cookie session vẫn tự động được gửi theo policy. BFF cần SameSite phù hợp, CSRF token/Origin checks và thiết kế endpoint an toàn.

### 11.2. Khi nào BFF phù hợp?

BFF thường là lựa chọn mạnh cho ứng dụng có dữ liệu nhạy cảm, refresh token giá trị cao, nhiều API backend hoặc yêu cầu kiểm soát session tập trung. Nó không phải yêu cầu bắt buộc cho mọi SPA, nhưng cần cân nhắc trước khi chọn lưu refresh token dài hạn trong JavaScript storage.

## 12. SPA trực tiếp gọi API

Một SPA có thể là OAuth public client và gọi resource API trực tiếp bằng access token. Trong mô hình này:
- Dùng Authorization Code Flow với PKCE.
- Không có client_secret trong browser.
- Lưu access token trong memory nếu có thể.
- Giữ access token ngắn hạn, scope/audience tối thiểu.
- Thiết kế refresh token theo chính sách provider, rotation/reuse detection và khả năng revoke.
- Phòng vệ XSS nghiêm túc.
- Chỉ gửi token tới API origin đã allowlist.

Ví dụ gửi access token:

~~~js
const response = await fetch("https://api.example.test/profile", {
  headers: {
    Authorization: "Bearer " + accessToken,
    Accept: "application/json"
  }
});
~~~

Không gắn bearer token tự động vào mọi URL do component hoặc user input cung cấp. Interceptor phải xác minh destination origin trước khi thêm Authorization header.

### 12.1. Không gửi token sang origin tùy ý

~~~js
function authorizedApiFetch(input, init = {}) {
  const url = new URL(input, window.location.href);
  const apiOrigin = "https://api.example.test";

  if (url.origin !== apiOrigin || url.protocol !== "https:") {
    throw new TypeError("Không gửi token tới origin ngoài allowlist");
  }

  const headers = new Headers(init.headers);
  headers.set("Authorization", "Bearer " + accessToken);

  return fetch(url, { ...init, headers });
}
~~~

Ví dụ minh họa allowlist một origin. Nếu có nhiều API, dùng map cấu hình rõ ràng theo audience/resource. Không để URL từ query string, postMessage hoặc localStorage quyết định nơi nhận token.

## 13. OAuth Authorization Code Flow với PKCE

SPA/browser là public client nên luồng hiện đại thường dùng Authorization Code Flow với PKCE. PKCE ràng buộc authorization code với một verifier mà client giữ trong quá trình authorization, giúp giảm nguy cơ code bị chặn giữa đường bị đổi bởi client khác.

Luồng khái quát:
1. Client tạo code_verifier ngẫu nhiên có entropy phù hợp.
2. Client tính code_challenge (thường S256).
3. Browser điều hướng tới authorization endpoint với response_type=code, client_id, redirect_uri, scope, state và code_challenge.
4. Authorization server xác thực user và consent theo policy.
5. Server redirect về redirect_uri với authorization code và state.
6. Client xác minh state, sau đó gửi code cùng code_verifier tới token endpoint.
7. Authorization server xác minh PKCE và phát token.

### 13.1. Các tham số cần bảo vệ

- redirect_uri: khớp chính xác URI đã đăng ký; tránh wildcard rộng.
- state: ràng buộc response với request authorization do client khởi tạo và chống login CSRF.
- code_verifier: giữ bí mật trong thời gian flow; không đưa vào URL/log.
- code_challenge_method: ưu tiên S256; không dùng plain nếu có thể.
- issuer/authorization server: xác minh đúng issuer để giảm mix-up.
- nonce: dùng trong OpenID Connect khi cần ràng buộc ID token với authentication request.

PKCE không phải cơ chế lưu trữ token sau khi nhận. Nó bảo vệ authorization code exchange. Sau callback, access/refresh token vẫn cần storage strategy riêng.

### 13.2. Lưu state và code_verifier tạm thời

Trong SPA, browser phải giữ state và code_verifier qua lần điều hướng tới authorization server rồi quay lại redirect URI. Một lựa chọn phổ biến là lưu transaction ngắn hạn trong sessionStorage, gắn với tab và xóa ngay sau khi callback được xác minh:

~~~js
sessionStorage.setItem("oauth_transaction", JSON.stringify({
  state,
  codeVerifier,
  createdAt: Date.now()
}));

// Ở callback: đọc transaction, so sánh state, đổi code bằng codeVerifier,
// rồi xóa transaction dù thành công hay thất bại.
const rawTransaction = sessionStorage.getItem("oauth_transaction");
sessionStorage.removeItem("oauth_transaction");
~~~

Đây là dữ liệu tạm của một authorization transaction, không phải nơi lưu access token hoặc refresh token lâu dài. sessionStorage vẫn đọc được bởi JavaScript cùng origin; nếu XSS xảy ra trong lúc flow đang chạy, verifier có thể bị lộ. Dùng thư viện OAuth/OIDC đã được kiểm thử để xử lý callback, state, PKCE verifier, issuer và lỗi một cách nhất quán; đặt thời hạn ngắn và không ghi transaction vào log.

### 13.3. Tránh Implicit Flow cho ứng dụng mới

Implicit Flow từng trả access token trực tiếp qua front-channel. Token có thể xuất hiện trong URL fragment và các bề mặt client khác. Với ứng dụng mới, dùng Authorization Code Flow với PKCE theo OAuth security best practices và hướng dẫn của authorization server.

Không chuyển token qua query string hoặc fragment để tiện callback. Authorization code ngắn hạn là credential khác với access token và cần được đổi theo đúng flow.

## 14. Access token lifetime, scope và audience

Giảm hậu quả nếu token bị lộ bằng cách giới hạn:
- Lifetime: access token có thời hạn ngắn phù hợp.
- Scope: chỉ cấp quyền cần thiết.
- Audience/resource: chỉ dùng cho API dự kiến.
- Subject/tenant: ràng buộc user và tenant phù hợp.
- Token type: xác minh đúng loại token.
- Revocation: có khả năng vô hiệu hóa khi cần.

Không dùng một access token có quyền admin rộng cho toàn bộ frontend. API phải kiểm tra issuer, audience, expiration, signature/introspection và quyền theo endpoint.

### 14.1. JWT decode không phải validate

Client có thể decode JWT để đọc claim phục vụ UI, nhưng không thể dựa vào decode đó để chứng minh token hợp lệ. Server/resource API cần xác minh chữ ký hoặc introspection, issuer, audience, expiration, not-before và policy tương ứng.

Không cho phép client tự sửa claim role hoặc scope rồi coi nó là quyền thật.

### 14.2. Không lưu claim dư thừa

JWT có thể chứa PII hoặc metadata. Payload thường đọc được nếu chỉ ký. Giữ claim tối thiểu và không đưa dữ liệu nhạy cảm không cần thiết vào token; token có thể xuất hiện trong nhiều thành phần debug/log nếu hệ thống xử lý sai.

## 15. Refresh token rotation và reuse detection

Nếu authorization server cấp refresh token cho public client, cần có cơ chế giảm rủi ro token bị sao chép. Một mô hình phổ biến là **refresh token rotation**: mỗi lần refresh thành công, server cấp refresh token mới và vô hiệu hóa token cũ.

Nếu token cũ đã bị dùng lại sau khi rotation, server có thể phát hiện dấu hiệu reuse và revoke token family/session theo policy.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as Browser client
    participant A as Authorization Server
    C->>A: Refresh token R1
    A->>A: Kiểm tra R1 và trạng thái family
    A-->>C: Access token mới + refresh token R2
    A->>A: Vô hiệu hóa R1
    Note over C,A: Nếu R1 bị dùng lại, áp dụng reuse detection/revoke policy
~~~

### 15.1. Race condition khi nhiều tab refresh

Nếu hai tab cùng dùng một refresh token rotation family, cả hai có thể gửi token cũ gần như đồng thời. Một request thành công xoay sang token mới; request còn lại có thể bị coi là reuse và làm revoke cả family tùy provider.

Cần single-flight refresh ở phạm vi phù hợp, đồng bộ tab hoặc dùng BFF tập trung refresh ở server. Không broadcast giá trị refresh token qua BroadcastChannel nếu không thật sự cần và chưa đánh giá threat model.

### 15.2. Rotation không thay XSS defense

Nếu XSS chạy trong SPA, script có thể sử dụng token đang có hoặc kích hoạt refresh flow. Rotation giúp phát hiện một số tình huống replay token đã bị sao chép; nó không ngăn script độc hoạt động trong phiên hiện tại.

## 16. Web Crypto và mã hóa token ở client

Ứng dụng đôi khi mã hóa token trước khi lưu localStorage/IndexedDB. Tuy nhiên, nếu JavaScript cùng origin có thể lấy key hoặc yêu cầu ứng dụng giải mã, XSS cũng có thể làm tương tự.

Web Crypto API có thể tạo CryptoKey không exportable:

~~~js
const key = await crypto.subtle.generateKey(
  {
    name: "AES-GCM",
    length: 256
  },
  false,
  ["encrypt", "decrypt"]
);
~~~

extractable=false hạn chế xuất key ra dạng raw/JWK theo API. Điều này hữu ích cho một số threat model, nhưng không tự bảo vệ khỏi XSS đang chạy trong origin có quyền sử dụng key để decrypt.

### 16.1. Mã hóa client-side cần threat model cụ thể

Mã hóa local storage có thể giảm một số rủi ro khi dữ liệu file bị sao chép offline mà không có key. Nhưng nếu key được lưu cạnh ciphertext hoặc được lấy tự động từ cùng JavaScript context, attacker cùng origin có thể truy cập quy trình giải mã.

Không mô tả mã hóa bằng key trong bundle là biện pháp chống XSS. Muốn bảo vệ dữ liệu khỏi chủ thiết bị hoặc malware, cần mô hình khóa và nền tảng riêng; browser web thông thường có giới hạn rõ.

### 16.2. WebAuthn không phải token storage

WebAuthn/passkey dùng credential public-key gắn với authenticator để xác thực. Nó có thể giảm nhu cầu giữ password hoặc secret lâu dài, nhưng không biến localStorage thành vault và không thay thiết kế session/access token sau đăng nhập.

## 17. Service worker không phải kho bí mật

Service worker chạy trong origin và có thể xử lý fetch/push/background events theo browser lifecycle. Nó có thể giữ state trong memory hoặc dùng IndexedDB/Cache Storage, nhưng các kho đó vẫn thuộc origin và có thể bị script cùng origin truy cập theo quyền.

Không chuyển refresh token vào service worker rồi kết luận XSS không thể sử dụng token. Service worker cũng có thể bị thay thế qua update lifecycle nếu đường phát hành worker không được bảo vệ.

Dùng service worker cho offline/cache/push theo nhu cầu; giữ credential theo kiến trúc session/BFF hoặc storage strategy đã đánh giá.

## 18. Không đặt token trong URL, DOM hoặc log

Token không nên xuất hiện trong query string, URL fragment, link chia sẻ/redirect target, HTML attribute, hidden input, DOM dataset, console log, exception message, analytics, telemetry, crash report, server/proxy access log, screenshot, support ticket, postMessage tới origin không tin cậy hoặc cache response không cần thiết.

URL có thể được lưu trong history, Referer theo policy, proxy log và monitoring. Nếu token đã xuất hiện trong URL/log, coi là credential có khả năng bị lộ và đánh giá revoke/rotation.

### 18.1. Không log Authorization

Middleware và observability pipeline cần redaction các header như Authorization, Cookie và Set-Cookie. Không log nguyên request/response mặc định.

Dùng request ID không mang quyền truy cập để correlation. Nếu cần điều tra token, dùng token fingerprint/identifier được thiết kế riêng và không thể dùng làm credential.

### 18.2. postMessage và token handoff

Nếu nhiều window trao đổi kết quả authorization, kiểm tra event.origin chính xác, event.source mong đợi và schema message. Dùng targetOrigin cụ thể thay vì wildcard. Không gửi token tới mọi window hoặc chấp nhận message chứa token từ origin tùy ý.

## 19. Gọi API và bảo vệ bearer token

Khi dùng access token trong Authorization header:

~~~js
const response = await fetch("https://api.example.test/orders", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
~~~

Cần:
- Chỉ gửi qua HTTPS.
- Giới hạn origin/audience.
- Không tự động gắn token vào mọi request.
- Không chuyển token qua redirect ngoài dự kiến.
- Redact Authorization ở log/proxy.
- Kiểm tra scope và quyền ở resource server.
- Không để response chứa dữ liệu user khác.

CORS cần cho browser đọc response cross-origin, nhưng CORS không xác thực token hoặc quyết định user có quyền truy cập record. Resource server phải kiểm tra token trên mỗi request.

### 19.1. Redirect và credential leakage

Nếu request có Authorization và bị redirect tới origin khác, không giả định mọi browser/client xử lý credential giống nhau. Tránh redirect API sang host không nằm trong allowlist; thiết kế endpoint trả response rõ ràng và kiểm tra redirect chain trong DevTools.

Không tự theo URL redirect do server hoặc user input cung cấp khi token có thể bị gửi tới đích ngoài dự kiến.

## 20. Token refresh và xử lý 401

Khi access token hết hạn, API có thể trả 401. Client cần phân biệt access token hết hạn, session đã bị revoke, audience/scope không hợp lệ, token malformed hoặc backend đang có lỗi xác thực.

Một chiến lược phổ biến:
1. Nhận 401 từ request cần xác thực.
2. Kiểm tra request có được phép retry và refresh chưa được thử cho request này.
3. Thực hiện một refresh operation duy nhất nếu session còn hợp lệ.
4. Lưu token mới theo strategy.
5. Retry request ban đầu tối đa một lần nếu body có thể phát lại.
6. Nếu refresh thất bại, xóa client state, chuyển tới login và xử lý server session.
7. Không retry vòng lặp khi API tiếp tục trả 401.

### 20.1. Không refresh request không idempotent mù quáng

Một POST có thể đã được server xử lý trước khi client nhận 401 từ một lớp proxy hoặc response bất thường. Retry phải dựa trên API contract, idempotency key và khả năng replay body.

### 20.2. Single-flight refresh

Trong một tab, dùng Promise dùng chung để nhiều request cùng chờ một refresh operation thay vì gửi nhiều refresh token song song. Với nhiều tab, BFF tập trung refresh ở server thường đơn giản hơn; nếu SPA tự phối hợp, chỉ broadcast trạng thái “đã refresh” hoặc “đăng xuất”, tránh broadcast token nếu không cần.

## 21. Logout, revoke và hết hạn session

Logout có ba phần khác nhau:

1. **Server-side revoke:** vô hiệu hóa session hoặc refresh token theo thiết kế.
2. **Browser cleanup:** xóa token trong memory/storage và hết hạn cookie bằng response server.
3. **UI/session coordination:** cập nhật tab khác, đóng WebSocket và xóa dữ liệu cache nhạy cảm.

Xóa localStorage hoặc đóng tab không tự revoke token đã bị sao chép. Hết hạn cookie không tự thu hồi refresh token nếu authorization server vẫn chấp nhận nó.

### 21.1. Logout từ mọi thiết bị

Nếu sản phẩm hỗ trợ “đăng xuất mọi thiết bị”, backend cần quản lý session/token family theo user/device và revoke ở server. Clear site data trên một browser chỉ xóa dữ liệu profile hiện tại; nó không tác động thiết bị khác.

### 21.2. Đồng bộ logout giữa tab

Có thể dùng BroadcastChannel để thông báo trạng thái logout:

~~~js
const channel = new BroadcastChannel("auth-events");

channel.postMessage({ type: "LOGOUT" });

channel.addEventListener("message", (event) => {
  if (event.data?.type === "LOGOUT") {
    clearInMemoryAuthState();
    showSignedOutUI();
  }
});
~~~

Message này chỉ là tín hiệu UI. Tab nhận được vẫn phải xác minh session/server khi cần; không coi BroadcastChannel là nguồn xác thực.

## 22. CORS, cookie và credentials mode

Khi dùng cookie cho API cross-origin, Fetch có thể cần credentials: "include" và server phải cấu hình CORS credentials đúng:

~~~js
const response = await fetch("https://api.example.test/profile", {
  credentials: "include"
});
~~~

Server cần:
- Access-Control-Allow-Origin là origin cụ thể, không phải *.
- Access-Control-Allow-Credentials: true.
- Vary: Origin khi response thay đổi theo Origin.
- Cấu hình cookie Domain/Path/Secure/SameSite phù hợp.
- CSRF defense cho request thay đổi trạng thái.

Third-party cookie restrictions và storage partitioning có thể vẫn ngăn cookie trong một số context. Không giả định credentials: include bảo đảm cookie luôn được gửi.

### 22.1. Bearer token và CORS

Nếu SPA gửi Authorization header tới API khác origin, request có thể cần preflight. Server phải cho phép header đó qua Access-Control-Allow-Headers và origin frontend qua Access-Control-Allow-Origin.

CORS chỉ quyết định browser có chia sẻ response cho script hay không. Nó không thay token validation, authorization hoặc CSRF defense.

## 23. CSP, Trusted Types và giảm rủi ro XSS

Vì JavaScript cùng origin có thể đọc Web Storage và sử dụng token trong memory, phòng vệ XSS là điều kiện quan trọng của SPA token storage.

Các lớp giảm rủi ro:
- Output encoding đúng ngữ cảnh.
- Dùng textContent và safe DOM APIs.
- Tránh innerHTML với dữ liệu không tin cậy.
- CSP với nonce/hash và nguồn script tối thiểu.
- Trusted Types cho sink DOM injection khi browser hỗ trợ.
- Kiểm soát dependency và third-party script.
- Không dùng eval hoặc dynamic code generation nếu không cần.
- Cập nhật thư viện và rà soát supply chain.
- Authorization và scope tối thiểu ở API.

CSP/Trusted Types giảm một số đường XSS nhưng không bảo đảm không có XSS. Không dùng chúng để hợp thức hóa việc lưu refresh token dài hạn trong localStorage.

### 23.1. HttpOnly và XSS

HttpOnly giảm khả năng script đọc cookie session. Tuy nhiên, script độc vẫn có thể thực hiện request cùng origin và browser tự đính kèm cookie. Vì vậy, kết hợp HttpOnly với XSS prevention, CSRF defense, reauthentication cho hành động nhạy cảm và server-side authorization.

## 24. Quyết định kiến trúc: nên chọn cách nào?

| Kiến trúc | Token ở đâu? | Khi phù hợp | Rủi ro/công việc cần xử lý |
| --- | --- | --- | --- |
| BFF + session cookie | OAuth token ở backend; browser giữ opaque HttpOnly cookie | Ứng dụng nhạy cảm, muốn tránh token trong JavaScript | Cần BFF, CSRF defense, session management và scale. |
| SPA + access token memory | Access token trong JS memory; refresh qua flow phù hợp | SPA public client, token ngắn hạn và chấp nhận đăng nhập lại khi reload | XSS vẫn sử dụng token trong runtime; refresh coordination phức tạp. |
| SPA + sessionStorage | Token trong tab session | Chỉ khi yêu cầu sản phẩm/threat model chấp nhận JS-readable storage | XSS đọc được; session restore và tab lifecycle cần đánh giá. |
| SPA + localStorage | Token tồn tại lâu theo origin | Chỉ cân nhắc khi đã chấp nhận rủi ro XSS/persistence và có kiểm soát chặt | Rủi ro exfiltration và token tồn tại lâu; không ưu tiên cho refresh token. |
| SPA + IndexedDB | Token trong database origin | Không tạo lợi thế chống XSS so với Web Storage | API phức tạp hơn nhưng vẫn JS-readable. |

Không có câu trả lời duy nhất cho mọi ứng dụng. Với ứng dụng có dữ liệu nhạy cảm hoặc refresh token giá trị cao, bắt đầu bằng đánh giá BFF thường là lựa chọn đáng xem xét. Nếu chọn SPA trực tiếp, giữ token ngắn hạn trong memory khi có thể, giới hạn scope/audience và đầu tư vào XSS defense.

## 25. Kiểm tra token storage bằng DevTools

Trong môi trường test:
1. Mở DevTools → Application/Storage.
2. Kiểm tra Cookies và thuộc tính HttpOnly, Secure, SameSite, Domain, Path.
3. Kiểm tra localStorage và sessionStorage.
4. Kiểm tra IndexedDB và Cache Storage.
5. Mở Network và xem Authorization/Cookie headers mà không sao chép giá trị secret.
6. Tìm token trong URL, response body, console log và source map.
7. Reload trang và xác định credential nào còn tồn tại.
8. Logout và xác minh server revoke cùng browser cleanup.
9. Mở tab thứ hai để kiểm tra refresh race và logout coordination.
10. Dùng profile test và token giả; không đưa credential thật vào screenshot hoặc ticket.

### 25.1. Kiểm tra XSS impact trong lab

Trong ứng dụng demo do bạn kiểm soát, dùng payload vô hại để chứng minh script cùng origin có thể đọc localStorage/sessionStorage và gọi API test. Sau đó so sánh với cookie HttpOnly: script không đọc được giá trị cookie qua document.cookie, nhưng request same-origin vẫn có thể được browser gửi cookie.

Không thử payload trên website hoặc tài khoản không được phép.

### 25.2. Kiểm tra rotation/reuse

Với authorization server staging:
- Cấp refresh token test.
- Refresh một lần và nhận token mới.
- Thử dùng lại token cũ theo quy trình lab được provider cho phép.
- Quan sát reuse detection/revocation event.
- Xác minh client xử lý session invalidation và yêu cầu đăng nhập lại.

Không thử replay refresh token production. Token reuse test có thể revoke cả session/token family.

## 26. Các sai lầm thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “localStorage an toàn vì chỉ domain của mình truy cập.” | **Sai** | XSS hoặc script bên thứ ba chạy cùng origin có thể đọc. |
| “sessionStorage không thể bị XSS lấy.” | **Sai** | JavaScript cùng origin vẫn đọc được. |
| “IndexedDB an toàn hơn localStorage trước XSS.” | **Sai** | Cả hai đều truy cập được bởi script cùng origin. |
| “Mã hóa token bằng key trong bundle sẽ bảo vệ token.” | **Sai** | XSS có thể lấy key hoặc gọi chính quy trình giải mã. |
| “HttpOnly cookie ngăn mọi hành động của XSS.” | **Sai** | XSS vẫn có thể gọi API và browser gửi cookie. |
| “SameSite thay thế CSRF token trong mọi ứng dụng.” | **Sai** | Cần đánh giá site context, browser support và request design. |
| “CORS ngăn CSRF.” | **Sai** | CORS chủ yếu kiểm soát đọc response; request vẫn có thể được gửi. |
| “SPA có thể giấu client_secret bằng obfuscation.” | **Sai** | Bundle được tải tới browser và có thể kiểm tra. |
| “JWT payload đã ký nên không ai đọc được.” | **Sai** | JWS thường chỉ ký; payload có thể decode. |
| “ID token có thể dùng thay access token.” | **Sai** | Audience và mục đích của hai token khác nhau. |
| “Xóa token khỏi storage là revoke token.” | **Sai** | Server/provider phải thu hồi hoặc chờ token hết hạn. |
| “Refresh token rotation ngăn mọi XSS.” | **Sai** | XSS có thể sử dụng token trong phiên hiện tại. |
| “Service worker là vault an toàn cho token.” | **Sai** | Worker và storage của nó vẫn thuộc trust boundary của origin. |
| “Web Crypto non-extractable key chống được mọi script độc.” | **Sai** | Script cùng origin có thể gọi thao tác crypto mà ứng dụng được phép. |
| “WSS/HTTPS làm token an toàn nếu lưu ở localStorage.” | **Sai** | TLS bảo vệ đường truyền, không ngăn XSS đọc storage. |
| “BroadcastChannel có thể dùng để xác thực tab.” | **Sai** | Message là tín hiệu phối hợp, không phải bằng chứng session hợp lệ. |
| “Logout ở một tab tự revoke mọi thiết bị.” | **Sai** | Backend phải quản lý và revoke session/token ở server. |

## 27. Checklist review Token storage

- [ ] Phân loại access token, refresh token, ID token và session identifier.
- [ ] Xác định browser app là public client; không nhúng client_secret.
- [ ] Đánh giá BFF trước khi đưa refresh token dài hạn vào JavaScript storage.
- [ ] Nếu dùng SPA, ưu tiên access token ngắn hạn trong memory khi phù hợp.
- [ ] Không coi localStorage, sessionStorage hoặc IndexedDB là vault chống XSS.
- [ ] Không đặt token trong URL, fragment, DOM, console, telemetry hoặc source map.
- [ ] Giới hạn access token theo expiry, scope và audience.
- [ ] Dùng Authorization Code Flow với PKCE cho browser public client.
- [ ] Xác minh state, redirect URI, issuer và nonce theo flow.
- [ ] Có refresh rotation/reuse detection nếu provider hỗ trợ refresh token cho public client.
- [ ] Xử lý refresh race giữa request và tab.
- [ ] Không retry POST hoặc refresh vô hạn.
- [ ] Nếu dùng cookie, đặt Secure, HttpOnly và SameSite phù hợp.
- [ ] Cân nhắc __Host- cookie với Path=/ và không Domain khi phù hợp.
- [ ] Bảo vệ cookie-authenticated state-changing request khỏi CSRF.
- [ ] Kiểm tra Origin/Fetch Metadata ở server theo threat model.
- [ ] Không coi CORS là authentication, authorization hoặc CSRF defense.
- [ ] Chỉ gửi bearer token tới HTTPS origin đã allowlist.
- [ ] Redact Authorization, Cookie, Set-Cookie và token khỏi logs.
- [ ] Phòng vệ XSS bằng output encoding, safe DOM, CSP và Trusted Types khi phù hợp.
- [ ] Không dựa vào mã hóa client-side hoặc service worker để chống XSS.
- [ ] Revoke session/token phía server khi logout hoặc compromise.
- [ ] Xóa credential phía client và cookie đúng scope sau logout.
- [ ] Đồng bộ logout giữa tab mà không broadcast secret.
- [ ] Kiểm tra dữ liệu còn lại trong cache, IndexedDB và Web Storage.
- [ ] Test token expiration, refresh, reuse, revocation và multi-tab.
- [ ] Dùng DevTools với dữ liệu giả và không lưu credential trong báo cáo.

## 28. Tổng kết

Token storage là quyết định kiến trúc về nơi credential tồn tại, ai có thể đọc hoặc sử dụng nó và trong bao lâu. Memory giảm persistence nhưng không ngăn XSS sử dụng token khi trang đang chạy. localStorage, sessionStorage và IndexedDB đều có thể bị JavaScript cùng origin truy cập. HttpOnly cookie giảm khả năng đọc cookie bằng script nhưng browser tự gửi cookie nên cần CSRF defense.

Với ứng dụng nhạy cảm, BFF giữ OAuth token ở backend và dùng session cookie HttpOnly là một mô hình đáng cân nhắc. Nếu SPA gọi API trực tiếp, hãy dùng Authorization Code Flow với PKCE, access token ngắn hạn, scope/audience tối thiểu, storage có chủ đích và refresh token rotation/reuse detection theo khả năng provider. Không nhúng client secret vào frontend.

Ba nguyên tắc cần nhớ:

1. **Chọn storage theo threat model:** phân biệt XSS với CSRF; không có Web Storage hoặc IndexedDB nào tạo ranh giới chống script cùng origin.
2. **Giảm giá trị credential:** giữ token ngắn hạn, scope hẹp, audience đúng; bảo vệ refresh token bằng rotation, reuse detection và revoke.
3. **Cưỡng chế ở server:** cookie, CORS, CSP và client state không thay authentication, authorization, CSRF defense hoặc server-side session revocation.

Khi review token storage, hãy hỏi: **token nào đang được lưu, JavaScript nào có thể đọc hoặc sử dụng nó, credential tồn tại bao lâu, browser có tự gửi cookie không, XSS/CSRF được xử lý ra sao, refresh token có rotation/reuse detection không, và logout đã revoke phía server lẫn dọn browser state chưa?** Trả lời rõ những câu hỏi này giúp chọn kiến trúc token phù hợp và giảm hậu quả khi browser context bị xâm nhập.
