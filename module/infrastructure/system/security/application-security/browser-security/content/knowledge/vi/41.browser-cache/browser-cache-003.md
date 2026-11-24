# Private response

## 1. Private response là gì?

**Private response** là HTTP response chứa dữ liệu dành cho một người dùng, một tài khoản hoặc một phiên xác thực cụ thể. Ví dụ: hồ sơ cá nhân, lịch sử đơn hàng, số dư tài khoản, thông tin nhân sự, nội dung hộp thư, kết quả tìm kiếm riêng tư hoặc API trả về quyền và cấu hình của user đang đăng nhập.

Browser có nhiều lớp lưu response: HTTP cache riêng của browser, shared proxy cache, CDN/reverse proxy cache, Service Worker Cache Storage và các kho dữ liệu do ứng dụng tự quản lý. Nếu một response cá nhân bị lưu vào shared cache hoặc được phát lại cho user khác, dữ liệu có thể rò giữa các phiên dù authentication và authorization ở origin server vẫn đúng.

HTTP directive **private** có nghĩa response có thể được lưu trong private cache (chẳng hạn browser cache) nhưng không được lưu trong shared cache theo quy tắc HTTP caching. **private** không có nghĩa nội dung được mã hóa, không ai khác trên thiết bị đọc được, hoặc response tự động bị xóa khi logout.

Khi response nhạy cảm không được lưu ở bất kỳ HTTP cache nào, dùng **Cache-Control: no-store**. Khi muốn browser có thể lưu bản riêng nhưng phải hỏi server trước mỗi lần dùng lại, dùng **Cache-Control: private, no-cache**. Khi cho phép cache riêng trong một khoảng thời gian ngắn, có thể dùng **Cache-Control: private, max-age=...** nếu dữ liệu và nghiệp vụ chấp nhận độ cũ đó.

Bài học này phân tích cách phân loại response, chọn cache policy, tránh rò dữ liệu qua CDN/proxy, xử lý cookie và Authorization header, validator/304, Service Worker, back-forward cache và kiểm chứng thực tế.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt private cache, shared cache, CDN cache, Cache Storage và browser history/BFCache.
2. Giải thích chính xác private, no-store, no-cache, max-age, s-maxage và public.
3. Chọn policy phù hợp cho profile, API, HTML cá nhân, file download và response lỗi.
4. Phát hiện cache key không phân biệt user hoặc cookie.
5. Hiểu vai trò và giới hạn của Vary, ETag, Last-Modified và response 304.
6. Cấu hình origin server, reverse proxy và CDN để bypass response cá nhân.
7. Ngăn Service Worker lưu private response vào Cache Storage.
8. Xử lý logout, account switching và BFCache để không hiển thị dữ liệu cũ.
9. Kiểm thử cache isolation giữa hai tài khoản bằng DevTools.
10. Thiết lập checklist vận hành và giám sát private response.

## 2. Các lớp cache trong browser và trên đường truyền

Không phải mọi nơi lưu response đều tuân theo cùng một cơ chế.

| Lớp lưu trữ | Phạm vi | Ai quyết định? | Rủi ro chính |
| --- | --- | --- | --- |
| Browser HTTP cache | Thường gắn với browser profile/storage partition | HTTP caching directives và browser | Người dùng khác dùng chung profile, dữ liệu stale |
| Private proxy cache | Cache dành cho một user/agent trong một số hệ thống | Proxy implementation và HTTP policy | Cấu hình sai, chia sẻ identity |
| Shared proxy cache | Nhiều người dùng cùng dùng | HTTP directives và cấu hình proxy | Response của user A phát cho user B |
| CDN/reverse proxy cache | Nhiều request qua edge/origin shield | Header và cache rules của CDN | Cache key bỏ qua cookie/authorization |
| Service Worker Cache Storage | Origin và storage partition của browser | JavaScript trong Service Worker | Code tự lưu response private hoặc dùng cache sai account |
| IndexedDB/local storage | Origin/storage partition | Ứng dụng | Dữ liệu cá nhân tồn tại sau logout |
| Back-forward cache (BFCache) | Snapshot document để Back/Forward nhanh | Browser lifecycle và policy | Trang cũ được khôi phục sau logout |

### 2.1. Private cache và shared cache

Private cache dành cho một user agent, thường là browser cache trong profile hiện tại. Shared cache phục vụ nhiều user, ví dụ CDN hoặc forward proxy. **private** ngăn shared cache lưu response theo HTTP caching semantics, nhưng vẫn cho phép private cache lưu nếu response còn fresh.

### 2.2. CDN không phải browser cache

CDN có thể có cấu hình riêng về cache key, cookie forwarding, query string, header và status code. Một CDN có thể được cấu hình bỏ qua hoặc ghi đè một số header từ origin. Vì vậy, response private từ origin vẫn cần được kiểm tra trên đường đi thực tế: edge rule có tôn trọng header không, route API có bị ép cache không, và cache key có chứa đúng các biến thể hay không.

Đối với endpoint trả dữ liệu cá nhân, lựa chọn an toàn thường là tắt shared caching ở CDN/reverse proxy cho route đó và trả Cache-Control: private, no-store từ origin. Chỉ bật shared caching nếu dữ liệu thực sự public hoặc đã được thiết kế thành representation dùng chung không chứa thông tin cá nhân.

### 2.3. Cache Storage khác HTTP cache

Service Worker Cache API là kho do script quản lý. Nó không tự động áp dụng đầy đủ freshness/expiration semantics của HTTP cache; ứng dụng quyết định khi nào put, match, cập nhật và xóa. Đừng cho rằng Cache-Control: no-store tự ngăn một đoạn Service Worker code chủ động gọi cache.put().

### 2.4. BFCache không phải HTTP cache

BFCache giữ snapshot của document để phục hồi nhanh khi người dùng nhấn Back/Forward. Nó có thể khôi phục DOM và trạng thái JavaScript của trang trước đó. Cache-Control: no-store không phải một cơ chế đảm bảo xóa mọi snapshot trong mọi browser/version. Trang nhạy cảm cần xử lý lifecycle khi được restore và xác minh session trước khi hiển thị dữ liệu.

## 3. Chọn Cache-Control cho response riêng tư

Cache-Control là response header chính để mô tả cách HTTP cache lưu và tái sử dụng response. Cần hiểu rõ các directive có ý nghĩa khác nhau.

### 3.1. private

```http
Cache-Control: private
```

private cho phép private cache lưu response, nhưng shared cache không được lưu response đó. Có thể kết hợp với max-age, no-cache hoặc các directive khác để điều khiển freshness/revalidation.

Dùng private khi response có thể được lưu trong browser của user hiện tại nhưng không được chia sẻ qua CDN/proxy. Ví dụ một trang cá nhân ít thay đổi có thể dùng private, max-age=60 nếu chấp nhận tối đa khoảng thời gian stale tương ứng.

private không ngăn JavaScript cùng origin đọc response, không ngăn người dùng mở DevTools, không xóa dữ liệu trên thiết bị dùng chung và không bảo vệ trước XSS.

### 3.2. no-store

```http
Cache-Control: no-store
```

no-store yêu cầu private và shared HTTP cache không lưu request/response tương ứng. Đây là lựa chọn phù hợp cho dữ liệu nhạy cảm như thông tin thanh toán, token, nội dung hồ sơ cần hạn chế lưu hoặc response chứa dữ liệu bí mật theo policy.

no-store không phải secure erase. Nó không thể xóa bản sao đã lưu trước đó, screenshot, clipboard, log, dữ liệu do JavaScript tự ghi vào IndexedDB hoặc Cache Storage, hay mọi snapshot do browser quản lý. Phải kết hợp với cleanup ở application storage và kiểm soát log/telemetry.

### 3.3. no-cache

```http
Cache-Control: no-cache
```

Tên directive dễ gây nhầm: no-cache vẫn cho phép cache lưu response, nhưng cache phải revalidate với server trước khi dùng lại response đã lưu. Nếu server trả 304 Not Modified, cache có thể dùng body đã lưu trước đó cùng metadata được cập nhật.

Dùng no-cache khi muốn browser giữ bản response riêng nhưng cần kiểm tra quyền và freshness với server trước mỗi lần reuse. Với response cá nhân, thường kết hợp private, no-cache để tránh shared cache lưu.

### 3.4. max-age

```http
Cache-Control: private, max-age=60
```

max-age chỉ thời gian response còn fresh tính bằng giây. Trong khoảng này, browser có thể dùng response từ private cache mà không gọi origin. Điều đó có nghĩa nếu session bị revoke hoặc user vừa chuyển account, một response còn fresh có thể vẫn được hiển thị nếu ứng dụng không kiểm tra lại trạng thái.

Chỉ đặt max-age cho private response khi đã đánh giá hậu quả của dữ liệu stale. Với thông tin quyền, trạng thái thanh toán hoặc dữ liệu thay đổi nhanh, chọn thời hạn ngắn hoặc bắt buộc revalidation.

### 3.5. s-maxage

```http
Cache-Control: s-maxage=300
```

s-maxage dành cho shared cache và override max-age/Expires trong shared cache. Không dùng nó cho response cá nhân chỉ để cải thiện hiệu năng. Nếu shared cache được phép lưu response, cần chứng minh representation thực sự an toàn để chia sẻ giữa mọi request khớp cache key.

Không kết hợp private với kỳ vọng shared cache sẽ lưu theo s-maxage; private được dùng để ngăn shared cache lưu response. Hãy thiết kế policy rõ ràng thay vì chồng directive mâu thuẫn.

### 3.6. public

```http
Cache-Control: public, max-age=300
```

public cho phép shared cache lưu response ngay cả trong một số tình huống mà shared cache bình thường bị hạn chế, ví dụ response cho request có Authorization theo điều kiện của HTTP caching specification. Chỉ dùng khi representation thực sự public và không phụ thuộc user/session.

Không thêm public vào response profile chỉ vì muốn CDN cache nhanh hơn. Không giả định Authorization header luôn tự làm cache key an toàn hoặc luôn cấm mọi shared cache.

### 3.7. must-revalidate và max-stale

must-revalidate yêu cầu cache không được dùng response stale nếu không revalidate thành công. Điều này quan trọng với response mà dữ liệu cũ không được dùng khi server không truy cập được.

Không dùng stale fallback cho thông tin quyền, trạng thái account hoặc dữ liệu có thể gây hậu quả khi bị cũ. Các directive liên quan stale phải được chọn theo loại dữ liệu và threat model.

### 3.8. Bảng so sánh nhanh

| Directive | Có thể lưu? | Có thể dùng lại mà không hỏi origin? | Shared cache |
| --- | --- | --- | --- |
| private | Private cache có thể lưu | Nếu còn fresh | Không được lưu |
| no-store | Không lưu theo HTTP cache | Không | Không |
| no-cache | Có thể lưu | Phải revalidate trước khi reuse | Có thể lưu nếu không bị directive khác cấm |
| private, no-cache | Private cache có thể lưu | Phải revalidate | Không được lưu |
| private, max-age=60 | Private cache có thể lưu | Có trong 60 giây freshness | Không được lưu |
| public, max-age=300 | Có thể lưu | Có trong thời gian fresh | Có thể lưu |
| s-maxage=300 | Có thể lưu nếu policy cho phép | Shared cache dùng freshness này | Có thể lưu |

### 3.9. Các policy thường dùng

| Loại response | Policy gợi ý | Lý do |
| --- | --- | --- |
| Profile/API nhạy cảm | private, no-store | Không muốn HTTP cache giữ dữ liệu |
| Profile có thể cache nhưng phải kiểm tra session mỗi lần | private, no-cache | Lưu riêng và revalidate |
| Dashboard cá nhân chấp nhận stale ngắn | private, max-age=30 hoặc thời hạn phù hợp | Cân bằng hiệu năng và freshness |
| Login/callback/token response | no-store | Hạn chế lưu credential và response authentication |
| Public static asset có version trong URL | public, max-age=31536000, immutable | Nội dung bất biến, dùng chung an toàn |
| Public catalog không cá nhân hóa | public, s-maxage=300 theo CDN policy | Cho phép shared cache |
| Response có dữ liệu theo cookie/session | private, no-store thường là mặc định an toàn | Tránh phụ thuộc cache key phức tạp |

Đây là điểm xuất phát; policy cuối cùng phải theo phân loại dữ liệu và khả năng của CDN/browser mục tiêu.

## 4. Cache key và nguy cơ lộ response giữa người dùng

HTTP cache thường dùng request method và target URI làm cơ sở nhận diện response, sau đó Vary chỉ định thêm request header nào tạo ra representation khác. CDN có thể thêm quy tắc riêng cho cookie, query, host hoặc header. Nếu cache key không phân biệt hai người dùng mà response lại phụ thuộc danh tính, user B có thể nhận response đã tạo cho user A.

### 4.1. Lỗi cache key bỏ qua cookie

Giả sử cả hai request cùng URL:

```http
GET /api/profile HTTP/1.1
Host: app.example.com
Cookie: session=SESSION_ALICE
```

và:

```http
GET /api/profile HTTP/1.1
Host: app.example.com
Cookie: session=SESSION_BOB
```

Nếu CDN cache theo URL nhưng bỏ qua cookie/session, response của Alice có thể được trả cho Bob. Authentication tại origin không cứu được tình huống khi CDN trả cache hit mà không gọi origin.

### 4.2. Không dựa vào Vary Cookie để sửa thiết kế cache riêng tư

Có thể thấy cấu hình:

```http
Vary: Cookie
```

Vary: Cookie yêu cầu HTTP cache phân biệt representation theo giá trị Cookie. Tuy nhiên cookie thường lớn, thay đổi thường xuyên và có nhiều cookie không liên quan; điều này tạo nhiều cache variant và dễ bị cấu hình CDN bỏ qua. Nó cũng không biến dữ liệu cá nhân thành dữ liệu public an toàn.

Với response phụ thuộc session, lựa chọn đơn giản và an toàn thường là private, no-store cùng CDN bypass. Nếu có yêu cầu cache đặc biệt, cần thiết kế cache key có identity rõ ràng, kiểm soát truy cập và kiểm thử end-to-end; không dựa vào một header Vary duy nhất.

### 4.3. Vary Authorization

Vary: Authorization có thể phân biệt request header Authorization trong HTTP cache tuân thủ Vary. Nhưng không phải CDN nào cũng cache hoặc đưa Authorization vào cache key theo mặc định. Một số hệ thống bỏ qua header này hoặc có custom cache policy.

Không dùng Vary: Authorization làm biện pháp duy nhất để cách ly response nhạy cảm. Với API cá nhân, tắt shared cache và trả private, no-store.

### 4.4. Set-Cookie không tự cấm cache

Response có Set-Cookie không mặc nhiên bị HTTP cache cấm lưu. Không giả định cookie tự động làm response private hoặc no-store. Hãy đặt Cache-Control rõ ràng trên response có session hoặc dữ liệu cá nhân, và kiểm tra behavior của CDN/proxy.

### 4.5. Query string và cache key

Nếu dữ liệu cá nhân được chọn qua query parameter, ví dụ /invoice?id=123, cần đảm bảo cache key giữ nguyên query cần thiết. CDN có thể cấu hình bỏ qua một số query parameter để tăng hit ratio. Không đưa access token, session ID hoặc secret vào URL; URL có thể đi vào history, Referer, log và cache key.

### 4.6. Vary Origin trong response CORS động

Nếu server trả Access-Control-Allow-Origin dựa trên request Origin, response phải có Vary: Origin để cache phân biệt các biến thể. Nhưng với private response, Vary: Origin không thay private, no-store hoặc CDN bypass. CORS quyết định browser có expose response cho script hay không; cache isolation là một bài toán khác.

## 5. Authorization header và quy tắc shared cache

HTTP caching specification có quy tắc đặc biệt cho request chứa Authorization. Shared cache không được reuse response cho request đó trừ khi response có directive cho phép theo chuẩn, chẳng hạn public, s-maxage hoặc must-revalidate trong các điều kiện tương ứng.

Quy tắc này là lớp bảo vệ bổ sung, không phải thiết kế cache isolation cho ứng dụng. CDN có thể có cấu hình riêng, và response dựa trên cookie session không giống response dựa trên Authorization header. Luôn chủ động trả Cache-Control: private, no-store cho endpoint user-specific.

### 5.1. Request Authorization không làm response tự động private ở mọi lớp

Browser private cache có thể lưu response theo policy. Shared cache cần tuân thủ các giới hạn của HTTP spec, nhưng cấu hình tùy chỉnh có thể thay đổi behavior. Đừng suy luận chỉ từ việc request có Bearer token rằng response chắc chắn không được cache ở edge.

### 5.2. Không cache response đăng nhập và token

Các endpoint sau nên có policy rõ ràng, thường là Cache-Control: no-store:

- Token endpoint trả access/refresh/ID token.
- Login callback chứa authorization code hoặc dữ liệu xác thực.
- Session creation/rotation endpoint.
- Logout và revocation response.
- API trả credential, recovery code hoặc secret.
- Error response có chứa dữ liệu cá nhân hay trạng thái account nhạy cảm.

Đồng thời redaction query/body/header nhạy cảm trong access log, tracing, analytics và error reporting.

## 6. Cookie, authentication và response riêng tư

### 6.1. Cookie không phải cache directive

Cookie điều khiển browser gửi thông tin session tới server. Cookie flags như HttpOnly, Secure, SameSite, Path và Domain không thay thế Cache-Control.

- HttpOnly hạn chế JavaScript đọc cookie.
- Secure giới hạn gửi cookie qua HTTPS.
- SameSite kiểm soát một số ngữ cảnh gửi cookie cross-site.
- Path/Domain quyết định phạm vi cookie.
- Cache-Control quyết định HTTP cache có thể lưu/reuse response.

Một response được xác thực bằng cookie vẫn có thể bị cache nếu header và cache configuration cho phép.

### 6.2. Response cá nhân nên có policy ngay từ origin

Ví dụ API profile:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
Vary: Accept-Encoding

{"displayName":"Alice","email":"alice@example.test"}
```

Không cần thêm Vary: Cookie nếu response không được cache. Đặt policy ngay tại application/origin để proxy trung gian nhìn thấy và tuân thủ; CDN vẫn cần cấu hình bypass phù hợp.

### 6.3. 401 và 403 cũng cần cache policy

Response lỗi có thể chứa thông tin account, quyền, tenant hoặc lý do từ chối. Một số status có thể được cache heuristic nếu không có directive ngăn cản. Đặt Cache-Control: no-store hoặc policy phù hợp trên cả response lỗi của route nhạy cảm.

### 6.4. Redirect cũng có thể bị cache

Một redirect từ endpoint private sang trang khác có thể bị cache tùy status và header. Không để redirect phụ thuộc session/account bị cache shared. Đặt cache policy cho response 302/303/307/308 của authentication và account flow, và kiểm tra header của redirect chứ không chỉ response cuối.

## 7. Validator: ETag, Last-Modified và 304

Validator cho phép cache kiểm tra response đã lưu còn hợp lệ hay chưa. Chúng hữu ích để giảm truyền dữ liệu, nhưng với private response cần gắn validator với đúng user và xác thực trước khi trả 304.

### 7.1. ETag

Server có thể trả:

```http
HTTP/1.1 200 OK
ETag: "profile-alice-v7"
Cache-Control: private, no-cache
Content-Type: application/json
```

Lần sau browser gửi conditional request:

```http
GET /api/profile HTTP/1.1
If-None-Match: "profile-alice-v7"
Cookie: session=...
```

Nếu representation chưa đổi và user vẫn được phép đọc, server trả:

```http
HTTP/1.1 304 Not Modified
ETag: "profile-alice-v7"
Cache-Control: private, no-cache
```

Browser có thể dùng body đã lưu trong private cache. Response 304 không mang body; nó cho phép cache reuse representation cũ.

### 7.2. Xác thực trước khi trả 304

Với private endpoint, server phải xác thực session và authorization trước khi quyết định trả 304. Nếu session Alice bị revoke nhưng server chỉ so ETag và trả 304, browser có thể tiếp tục dùng body profile Alice đã cache mà không nhận response 401.

Thứ tự đúng là: xác thực principal hiện tại, kiểm tra quyền với resource, xác định representation/version của đúng principal, sau đó mới đánh giá conditional header và trả 304 hoặc 200. Nếu không còn quyền, trả 401/403 với cache policy thích hợp; không trả 304.

### 7.3. Validator không được chia sẻ nhầm giữa user

Không dùng một ETag toàn cục cho resource mà representation phụ thuộc user nếu server không phân biệt identity. ETag phải tương ứng representation được phép dùng cho principal hiện tại. Không nhúng email, user ID hoặc secret vào ETag dạng dễ đoán; validator nên là opaque value.

### 7.4. Last-Modified

Last-Modified dùng thời gian sửa đổi làm validator. Độ phân giải thời gian có thể thấp và không đủ phân biệt nhiều thay đổi gần nhau. Với private response, vẫn phải xác thực và authorize trước khi trả 304. Không dùng timestamp client làm nguồn quyết định.

### 7.5. 304 không có nghĩa server không cần kiểm tra quyền

304 là một response HTTP của server sau khi nhận conditional request. Nó không phải tín hiệu rằng browser có thể bỏ qua authentication. Nếu server không kiểm tra session/quyền ở mỗi lần revalidation, response cũ có thể sống lâu hơn quyền truy cập.

## 8. Service Worker và Cache Storage

### 8.1. Cache API là kho do ứng dụng điều khiển

Service Worker có thể chủ động lưu bất kỳ response phù hợp nào vào Cache Storage bằng cache.put(). Không giả định browser tự từ chối lưu response vì có Cache-Control: private hoặc no-store. Code worker phải phân loại request và response trước khi lưu.

### 8.2. Bypass private endpoint

Ví dụ Service Worker chỉ cache app shell/public assets và passthrough các endpoint account:

```js
const PUBLIC_CACHE = "public-shell-v3";

function isPrivateEndpoint(url) {
  return (
    url.pathname.startsWith("/api/account/") ||
    url.pathname.startsWith("/api/private/") ||
    url.pathname.startsWith("/session/") ||
    url.pathname.startsWith("/auth/")
  );
}

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  if (isPrivateEndpoint(url)) {
    event.respondWith(fetch(request, { cache: "no-store" }));
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith((async () => {
      const cache = await caches.open(PUBLIC_CACHE);
      const cached = await cache.match(request);
      if (cached) return cached;

      const response = await fetch(request);
      if (response.ok && response.type === "basic") {
        await cache.put(request, response.clone());
      }
      return response;
    })());
  }
});
```

Allowlist/denylist route phải phù hợp với API thực tế. Đừng chỉ dựa vào tên path nếu ứng dụng có endpoint riêng tư ở path khác hoặc query parameter làm thay đổi dữ liệu. Khi chưa chắc response public, không cache.

### 8.3. Không đưa private response vào cache chung

Không làm như sau với endpoint user-specific:

```js
const response = await fetch("/api/account/profile");
const cache = await caches.open("app-cache");
await cache.put("/api/account/profile", response.clone());
```

Cache name cố định có thể còn tồn tại khi user logout hoặc account khác đăng nhập. Nếu nghiệp vụ thật sự cần offline private data, phải thiết kế account namespace, encryption/threat model, retention, cleanup, authorization khi đọc và không đồng bộ queue bằng account khác. Đó là bài toán offline data riêng, không phải lý do để cache mọi response.

### 8.4. fetch cache mode và Cache Storage khác nhau

fetch(request, { cache: "no-store" }) điều khiển tương tác của request với HTTP cache. Nó không tự xóa response đã có trong Cache Storage và không ngăn một đoạn worker khác gọi caches.match(). Phải bảo đảm routing private endpoint không đọc hoặc ghi Cache Storage.

## 9. CDN và reverse proxy: cấu hình đường đi

### 9.1. Bypass cache cho route riêng tư

Với endpoint như /api/account/, /profile, /billing/ hoặc /session/, cấu hình CDN/reverse proxy không cache response. Tên route chỉ là ví dụ; policy cần dựa trên phân loại dữ liệu, không chỉ path.

Các nguyên tắc:

- Bypass cache cho authenticated/private routes.
- Không bỏ qua Cache-Control: private hoặc no-store ở edge.
- Không ép cache response 200 chỉ vì muốn tăng hit ratio.
- Không bỏ qua cookie/Authorization khỏi cache key rồi vẫn cache response cá nhân.
- Không cache response lỗi nhạy cảm.
- Kiểm tra origin response và edge response riêng biệt.
- Purge cache khi phát hiện dữ liệu cá nhân đã bị cache sai.

### 9.2. Nginx reverse proxy minh họa

```nginx
location ^~ /api/account/ {
    proxy_pass http://app_upstream;

    proxy_cache off;
    proxy_no_cache 1;
    proxy_cache_bypass 1;

    add_header Cache-Control "private, no-store" always;
}
```

Cấu hình trên minh họa bypass cache ở Nginx cho route riêng tư. add_header ... always giúp header xuất hiện cả trên nhiều response lỗi; cần phối hợp với upstream để tránh duplicate/conflicting Cache-Control. Nếu Nginx không phải cache layer duy nhất, vẫn phải cấu hình CDN/edge tương ứng.

### 9.3. Kiểm tra CDN response

Quan sát các header như Age, Via, X-Cache, CF-Cache-Status hoặc header riêng của nhà cung cấp nếu có. Chúng giúp nhận diện HIT/MISS/BYPASS nhưng không phải chuẩn thống nhất. Đối chiếu response body bằng hai account test và kiểm tra request có thật sự đi tới origin hay không.

### 9.4. Không purge bằng URL duy nhất nếu cache key có biến thể

Nếu CDN đã cache response sai, purge theo URL có thể không xóa mọi biến thể nếu cache key còn query, header, cookie hoặc host. Làm theo công cụ purge của nhà cung cấp, xác định toàn bộ cache key liên quan và đánh giá liệu dữ liệu đã được phục vụ cho user khác hay chưa. Nếu nghi có lộ dữ liệu, xử lý như sự cố bảo mật và revoke credential/session khi cần.

## 10. Header strategy theo loại response

Một policy nhất quán nên xuất phát từ phân loại dữ liệu và yêu cầu freshness.

| Response | Header gợi ý | Lưu ý |
| --- | --- | --- |
| Trang đăng nhập | Cache-Control: no-store | Tránh lưu form, nonce và trạng thái auth |
| OAuth/OIDC callback | Cache-Control: no-store, Referrer-Policy: no-referrer | Không cache code/state; làm sạch URL |
| Token endpoint | Cache-Control: no-store, Pragma: no-cache nếu cần tương thích cũ | Không log body chứa token |
| Profile JSON | Cache-Control: private, no-store | Phù hợp khi dữ liệu nhạy cảm |
| Dashboard cá nhân cần revalidate | Cache-Control: private, no-cache | Server kiểm tra auth trước 304 |
| Public JavaScript/CSS có hash | Cache-Control: public, max-age=31536000, immutable | Chỉ dùng URL content-hashed |
| Public image/catalog | Cache-Control: public, s-maxage=300 | Chỉ khi không cá nhân hóa |
| Response 401/403 có thông tin account | Cache-Control: no-store | Tránh lưu lỗi nhạy cảm |
| File riêng tư | Cache-Control: private, no-store hoặc policy riêng đã đánh giá | Kiểm soát download và shared cache |

Không có một header duy nhất giải quyết mọi loại lưu trữ. Cache-Control áp dụng cho HTTP caches; Cache Storage, IndexedDB, BFCache, browser extension và log cần biện pháp riêng.

## 11. Logout, account switching và cache lifecycle

### 11.1. Logout không tự xóa browser HTTP cache

Server revoke session và expire cookie không nhất thiết xóa bản response đã cache ở browser. Với response private, max-age, browser có thể vẫn dùng bản fresh trong một số tình huống. Với response private, no-cache, browser cần revalidate; server phải từ chối nếu session không còn hợp lệ.

Với dữ liệu đặc biệt nhạy cảm, dùng no-store từ đầu. Không chờ đến logout mới kỳ vọng browser xóa hết bản cache.

### 11.2. Account switching

Nếu cùng browser profile đăng nhập lần lượt Alice rồi Bob:

- Xóa user state và local cache namespace của Alice.
- Dừng request/refresh còn thuộc Alice.
- Không để response đến muộn của Alice ghi vào UI sau khi Bob đăng nhập.
- Không dùng cache key chung cho dữ liệu riêng tư.
- Revalidate session trước khi hiển thị page snapshot được restore.
- Không resume outbox/draft của Alice bằng session Bob.

### 11.3. Clear-Site-Data

Một số browser hỗ trợ response header Clear-Site-Data để yêu cầu xóa một số loại dữ liệu theo origin:

```http
Clear-Site-Data: "cache", "cookies", "storage"
```

Header này có phạm vi rộng, có thể xóa dữ liệu của các tính năng khác trên cùng origin và có khác biệt hỗ trợ giữa browser. Không dùng như nút xóa dữ liệu theo từng account; chỉ áp dụng khi hiểu rõ tác động, scope và khả năng tương thích. Nó không thay thế server-side revocation.

### 11.4. BFCache và page restore

Trang có thể được khôi phục khi Back/Forward mà không tạo request navigation mới. Dùng pageshow để phát hiện restore và kiểm tra session trước khi render nội dung nhạy cảm:

```js
window.addEventListener("pageshow", async event => {
  if (!event.persisted) return;

  const response = await fetch("/session/status", {
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    clearPrivateAppState();
    window.location.replace("/login");
  }
});
```

Endpoint session status cần trả response no-store, xác thực session hiện tại và không tiết lộ thông tin nhạy cảm. Trong ứng dụng thật, tránh flash dữ liệu cũ trước khi kiểm tra hoàn tất; có thể che nội dung private cho tới khi session được xác minh.

## 12. Ví dụ cấu hình response ở application server

### 12.1. Express: response riêng tư không cache

```js
app.get("/api/account/profile", requireSession, async (req, res, next) => {
  try {
    const profile = await loadProfileForUser(req.user.id);

    res.set("Cache-Control", "private, no-store");
    res.set("Vary", "Accept-Encoding");
    res.set("Content-Type", "application/json");
    res.json(profile);
  } catch (error) {
    next(error);
  }
});
```

requireSession phải xác thực session; loadProfileForUser phải truy vấn theo principal đã xác thực. Không nhận user ID từ query rồi trả profile mà bỏ qua ownership check.

### 12.2. Express: private response cần revalidation

```js
app.get("/api/account/summary", requireSession, async (req, res, next) => {
  try {
    const summary = await loadSummaryForUser(req.user.id);
    const etag = createOpaqueUserScopedEtag(req.user.id, summary.version);

    res.set("Cache-Control", "private, no-cache");
    res.set("ETag", etag);

    if (req.fresh) {
      return res.status(304).end();
    }

    res.json(summary);
  } catch (error) {
    next(error);
  }
});
```

Đây là ví dụ khái niệm: middleware/framework phải được cấu hình để tính conditional response đúng và chỉ sau khi xác thực/authorization. createOpaqueUserScopedEtag đại diện cho helper tạo validator phù hợp với representation và user; không dùng hàm chưa định nghĩa như code copy-paste hoàn chỉnh. Nếu cần triển khai thực tế, dùng cơ chế ETag của framework và xác minh thứ tự middleware.

### 12.3. Xử lý lỗi với cache policy

```js
function privateApiError(res, status, message) {
  res.set("Cache-Control", "no-store");
  res.status(status).json({ error: message });
}

// Ví dụ sau khi middleware đã xác minh request:
app.get("/api/account/private-report", requireSession, async (req, res) => {
  const report = await loadReport(req.user.id);

  if (!report) {
    return privateApiError(res, 404, "Không tìm thấy báo cáo.");
  }

  res.set("Cache-Control", "private, no-store");
  res.json(report);
});
```

Áp dụng cache policy cho cả error path. Không đưa stack trace, session ID hoặc chi tiết token vào error response.

## 13. Thực hành: kiểm tra private response bằng hai account

Lab dùng một ứng dụng staging/local có hai tài khoản thử nghiệm. Mục tiêu là xác minh response của Alice không bao giờ được trả cho Bob qua browser cache, Service Worker hoặc CDN.

### 13.1. Chuẩn bị

- Hai tài khoản test độc lập: Alice và Bob.
- Hai browser profile riêng hoặc hai cửa sổ private độc lập.
- DevTools Network với Preserve log.
- Endpoint profile trả về marker khác nhau cho mỗi account.
- CDN/reverse proxy staging nếu cần kiểm tra edge cache.
- Không dùng dữ liệu thật hoặc token production.

### 13.2. Kiểm tra response header

Đăng nhập Alice và gọi endpoint profile. Kiểm tra:

1. Response có Cache-Control: private, no-store nếu policy yêu cầu không lưu.
2. Không có public hoặc s-maxage bất ngờ.
3. CDN báo BYPASS/DYNAMIC hoặc không có cache hit cho route private.
4. Response 401/403 cũng có cache policy phù hợp.
5. Không có Age/HIT thể hiện response cá nhân được shared cache phục vụ.
6. Service Worker không gọi cache.put() cho endpoint private.

Nếu policy là private, no-cache, kiểm tra browser gửi If-None-Match/If-Modified-Since và server xác thực trước khi trả 304.

### 13.3. Kiểm tra cache isolation

1. Đăng nhập Alice ở profile A và tải /api/account/profile.
2. Ghi lại marker response, ví dụ user=alice-test.
3. Đăng xuất Alice và đăng nhập Bob theo cùng endpoint.
4. Xác minh Bob nhận user=bob-test, không nhận body Alice.
5. Thử reload, Back/Forward và mở tab mới.
6. Kiểm tra Cache Storage và IndexedDB không chứa response riêng của Alice.
7. Nếu CDN có staging cache, lặp lại qua cùng edge host và xác minh không có HIT dùng chéo account.

Không chỉ dựa vào việc hai profile khác nhau; shared CDN cache có thể phục vụ hai profile qua cùng edge. Cần test đường đi có CDN khi production sử dụng CDN.

### 13.4. Kiểm tra revalidation và 304

Với endpoint dùng private, no-cache:

- Gọi lần đầu để nhận 200 và ETag.
- Gọi lần hai để browser gửi conditional header.
- Xác minh server kiểm tra session/authorization trước khi trả 304.
- Revoke session Alice rồi gửi lại conditional request.
- Kết quả mong muốn là 401/403 với no-store, không phải 304.
- Đăng nhập Bob và xác minh ETag/representation không tái sử dụng body Alice.

### 13.5. Thử cấu hình sai trong staging

Nếu có môi trường thử nghiệm được phép, tạo một route demo cố ý bỏ qua cookie khỏi cache key và bật shared cache. Dùng hai tài khoản test để quan sát nguy cơ response cross-user, sau đó sửa bằng bypass + private, no-store và purge toàn bộ variant. Không thực hiện trên production hoặc dữ liệu người dùng thật.

## 14. Ma trận kiểm thử private response

| Mã | Tình huống | Kết quả mong muốn |
| --- | --- | --- |
| CACHE-PR-01 | Profile trả private, no-store | Browser/shared HTTP cache không lưu response |
| CACHE-PR-02 | Profile trả private, no-cache | Private cache revalidate trước khi reuse |
| CACHE-PR-03 | Profile trả private, max-age=60 | Chỉ private cache được reuse trong freshness window |
| CACHE-PR-04 | Private response đi qua CDN | CDN bypass/không lưu response |
| CACHE-PR-05 | CDN cache key bỏ qua cookie | Kiểm thử phát hiện và cấu hình bị từ chối |
| CACHE-PR-06 | User Alice gọi profile | Chỉ nhận dữ liệu Alice |
| CACHE-PR-07 | User Bob gọi cùng URL | Không nhận response của Alice |
| CACHE-PR-08 | Response có Set-Cookie | Cache policy vẫn được cấu hình rõ |
| CACHE-PR-09 | Request có Authorization | Không dựa vào header này để giả định cache an toàn |
| CACHE-PR-10 | Response có Vary: Cookie | Không coi Vary là thay thế private/no-store |
| CACHE-PR-11 | CORS origin thay đổi | Dynamic ACAO có Vary: Origin |
| CACHE-PR-12 | Conditional request với ETag | Server xác thực trước khi trả 304 |
| CACHE-PR-13 | Session bị revoke rồi revalidate | Trả 401/403 no-store, không trả 304 |
| CACHE-PR-14 | ETag giữa hai user khác nhau | Không dùng validator gây reuse nhầm representation |
| CACHE-PR-15 | Response 401/403 | Có cache policy ngăn lưu thông tin nhạy cảm |
| CACHE-PR-16 | Private redirect 302/303 | Không bị shared cache lưu và phát lại chéo user |
| CACHE-PR-17 | Service Worker xử lý private GET | Không đọc/ghi Cache Storage cho route private |
| CACHE-PR-18 | Cache Storage có public app shell | Public asset vẫn hoạt động sau logout |
| CACHE-PR-19 | Logout rồi account switch | Local private state của account cũ được dọn |
| CACHE-PR-20 | BFCache restore sau logout | Session được xác minh trước khi hiển thị dữ liệu |
| CACHE-PR-21 | Clear-Site-Data | Chỉ dùng khi hiểu scope và tác động origin-wide |
| CACHE-PR-22 | CDN có Age/HIT | Không xuất hiện cache hit cho response cá nhân |
| CACHE-PR-23 | CDN có custom cache rule | Rule không override private/no-store |
| CACHE-PR-24 | Purge sau sự cố cache leak | Xóa mọi cache variant liên quan |
| CACHE-PR-25 | Response token/login/callback | Có no-store và không log credential |
| CACHE-PR-26 | Network offline với private response | Không hiển thị dữ liệu stale trái policy |
| CACHE-PR-27 | Query string thay đổi representation | Cache key không bỏ query có ý nghĩa |
| CACHE-PR-28 | Browser dùng chung profile | Không xem private cache là vault bảo vệ nhiều OS user |
| CACHE-PR-29 | Response private được lưu trong IndexedDB | Cleanup/retention theo account policy |
| CACHE-PR-30 | Origin server trả cache header đúng nhưng CDN sửa | Kiểm tra edge response phát hiện khác biệt |

## 15. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| private nghĩa là không được cache ở đâu | Private cache vẫn có thể lưu; shared cache không được lưu |
| no-cache nghĩa là không lưu | Có thể lưu nhưng phải revalidate trước khi reuse |
| no-store xóa mọi bản sao đã tồn tại | Chỉ yêu cầu cache không lưu response hiện tại; không secure erase |
| Có Set-Cookie thì response tự động không cache | Set-Cookie không thay Cache-Control |
| Request có Authorization thì CDN luôn bypass | Cần hiểu HTTP rule và CDN configuration thực tế |
| Vary: Cookie luôn cách ly user | CDN có thể bỏ qua cookie; Vary không thay private policy |
| Vary: Authorization đủ an toàn | Không đảm bảo CDN dùng Authorization trong cache key |
| CORS ngăn shared cache leak | CORS kiểm soát response exposure ở browser, không thay cache isolation |
| Xóa cookie đồng nghĩa cache response mất | HTTP cache và cookie store là hai cơ chế khác nhau |
| Logout tự xóa BFCache | Phải xử lý page restore và xác minh session |
| Cache API tự tuân thủ no-store | Service Worker code phải chủ động không lưu |
| Origin trả private là đủ | CDN/reverse proxy có thể có rule ghi đè; phải kiểm tra edge |
| 304 không cần authentication vì không có body | Browser dùng lại body cũ; server phải xác thực trước khi trả 304 |
| Response lỗi không cần cache policy | 401/403/redirect có thể bị cache tùy status và header |
| Private cache là vault trên máy dùng chung | Người dùng cùng browser profile có thể truy cập dữ liệu đã lưu |

## 16. Checklist triển khai

- [ ] Phân loại response public, private và secret.
- [ ] Mặc định private, no-store cho API/HTML chứa dữ liệu nhạy cảm khi không cần cache.
- [ ] Dùng private, no-cache khi cần private cache nhưng phải revalidate.
- [ ] Chỉ đặt private, max-age khi chấp nhận freshness window cụ thể.
- [ ] Không dùng public hoặc s-maxage cho representation cá nhân.
- [ ] Đặt cache policy cho 200, 3xx, 401, 403 và error path.
- [ ] Không giả định Set-Cookie tự cấm cache.
- [ ] Bypass CDN/reverse proxy cache cho authenticated routes.
- [ ] Xác minh CDN không bỏ qua Cache-Control hoặc cache key theo URL duy nhất.
- [ ] Không dựa vào Vary Cookie/Authorization để bảo vệ private response.
- [ ] Dùng Vary Origin khi ACAO được chọn động, nhưng vẫn giữ private policy.
- [ ] Xác thực và authorize trước khi trả 304.
- [ ] Không tái sử dụng ETag/body giữa các principal khác nhau.
- [ ] Service Worker không match/put private endpoint vào Cache Storage.
- [ ] Dọn IndexedDB, Cache Storage và user state theo account khi logout.
- [ ] Kiểm tra BFCache restore trước khi hiển thị dữ liệu nhạy cảm.
- [ ] Không đưa token/session secret vào URL, log, analytics hoặc cache key.
- [ ] Test bằng hai account và qua đúng CDN/reverse proxy production path.
- [ ] Có quy trình purge toàn bộ cache variant khi xảy ra cache leak.
- [ ] Không coi Cache-Control là biện pháp thay thế authentication/authorization.

### Ghi nhớ

**Private response phải được bảo vệ ở mọi lớp có thể lưu hoặc phát lại response.** private ngăn shared cache nhưng vẫn cho browser cache lưu; no-cache yêu cầu revalidation; no-store yêu cầu HTTP cache không lưu. CDN cache key, cookie, Authorization, Vary và Set-Cookie cần được đánh giá theo cấu hình thực tế. Server phải xác thực trước khi trả 304; Service Worker phải tự tránh lưu private response; logout cần xử lý browser storage và BFCache. Hãy kiểm thử bằng hai account qua toàn bộ đường đi từ browser tới CDN và origin.