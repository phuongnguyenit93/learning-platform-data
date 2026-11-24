# DevTools và secret: kiểm tra ứng dụng mà không làm lộ dữ liệu nhạy cảm

Browser Developer Tools (DevTools) giúp lập trình viên quan sát request, response, cookie, storage, JavaScript runtime và hoạt động của trang. Chính khả năng quan sát sâu này khiến DevTools trở thành nơi dễ nhìn thấy secret đang được ứng dụng sử dụng.

Một access token có thể xuất hiện trong Network request headers; session cookie có thể được xem trong Application; API key có thể bị đóng gói trong JavaScript bundle; dữ liệu cá nhân có thể nằm trong Console log, HAR export, heap snapshot hoặc screenshot. Khi sao chép request thành cURL, nội dung có thể mang theo cookie và Authorization header sang terminal, ticket, chat hoặc shell history.

DevTools không tự tạo ra secret và cũng không phải một kho lưu trữ an toàn. Nó làm lộ những dữ liệu mà browser đã nhận, lưu, gửi hoặc tạo trong runtime. Vì vậy, bảo vệ secret phải bắt đầu từ kiến trúc ứng dụng, logging, quyền truy cập thiết bị và quy trình debug.

Bài học này phân tích các bề mặt rò rỉ trong DevTools, cách debug bằng dữ liệu đã che, cách xử lý file HAR và ảnh chụp, rủi ro từ extensions/remote debugging, cùng quy trình phản ứng khi secret đã bị lộ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện secret và dữ liệu nhạy cảm có thể xuất hiện trong DevTools.
- Tìm các vị trí thường làm lộ dữ liệu trong Console, Network, Application, Sources và Memory.
- Hiểu rủi ro khi dùng Copy as cURL, Save all as HAR, copy response, screenshot và heap snapshot.
- Phân biệt secret phía server với cấu hình frontend có thể công khai.
- Thiết kế logging và debug output có redaction.
- Hạn chế rủi ro từ browser extensions, shared profiles và remote debugging.
- Thu thập bằng chứng kỹ thuật mà không phát tán token/cookie.
- Xử lý sự cố lộ secret bằng revoke/rotate, audit và cleanup.
- Thực hành trên tài khoản, token và dữ liệu giả lập.

## 1. Vì sao DevTools liên quan đến secret?

DevTools là bộ công cụ kiểm tra môi trường browser. Tùy browser và phiên bản, các panel có thể cho xem:

- Request URL, query string, request headers và request body.
- Response headers, response body, preview và WebSocket frames.
- Cookie, Local Storage, Session Storage, IndexedDB và Cache Storage.
- JavaScript source, source map, module, closure và runtime variables.
- Console messages, stack trace, network timing và application state.
- Memory snapshot, performance recording và dữ liệu được giữ trong trang.

Nếu ứng dụng gửi bearer token trong header, browser phải có token tại thời điểm tạo request. Nếu ứng dụng lưu dữ liệu trong Local Storage, browser profile phải giữ dữ liệu đó. DevTools có thể quan sát các bề mặt này vì nó phục vụ việc debug.

### 1.1 DevTools không phải ranh giới bảo mật

Người dùng có quyền điều khiển browser profile và thiết bị thường có thể mở DevTools để xem dữ liệu phía client. Không thể bảo vệ secret khỏi chính người đang kiểm soát browser bằng cách ẩn nó khỏi giao diện DevTools.

Cookie có cờ `HttpOnly` không thể được JavaScript trang đọc qua `document.cookie`, nhưng vẫn có thể xuất hiện trong công cụ quản lý cookie của browser dành cho người dùng cục bộ. `HttpOnly` giảm khả năng đánh cắp cookie qua một số XSS; nó không làm cookie vô hình với chủ thiết bị hoặc công cụ quản trị browser.

Tương tự, minify hoặc obfuscate JavaScript không biến API key được nhúng trong bundle thành secret. Người dùng vẫn có thể tải bundle và phân tích nó.

### 1.2 Phân biệt các loại dữ liệu

| Loại dữ liệu | Ví dụ | Cách xử lý |
|---|---|---|
| Credential | Password, session cookie, access/refresh token | Không log; hạn chế lifetime; revoke/rotate khi lộ |
| Secret phía server | Private API key, signing key, database password | Chỉ giữ phía server hoặc secret manager |
| Capability URL | Signed URL, reset link, invitation link | Xem như bearer secret; giới hạn scope và thời hạn |
| Dữ liệu cá nhân | Email, địa chỉ, hồ sơ, thông tin thanh toán | Minimize, mask và hạn chế chia sẻ |
| CSRF token/state | CSRF token, OAuth state, nonce | Không đưa vào log công khai; xử lý theo threat model |
| Public configuration | API base URL, public client ID | Có thể nằm trong bundle nếu thiết kế xác định là public |

Không phải mọi chuỗi trông giống key đều là secret. Hãy xác định quyền mà dữ liệu cấp cho người sở hữu nó, thời hạn, scope và đối tượng có thể sử dụng.

### 1.3 Threat model khi debug

Trước khi mở DevTools, xác định ai có thể nhìn thấy dữ liệu sau khi bạn thu thập:

- Người dùng đang ngồi trước máy.
- Người dùng tiếp theo trên máy dùng chung.
- Browser extension có quyền đọc trang hoặc DevTools.
- Đồng nghiệp nhận screenshot, HAR, cURL hoặc log.
- Hệ thống ticket, chat, cloud drive và công cụ phân tích.
- Process cục bộ hoặc người có quyền truy cập remote debugging port.
- Nhà cung cấp dịch vụ nhận file đính kèm hoặc bản ghi hỗ trợ.

Một request chỉ hiển thị trong DevTools vẫn có thể rời khỏi máy qua thao tác copy/export.

## 2. Bản đồ các bề mặt có thể lộ secret

| Khu vực DevTools | Dữ liệu có thể lộ | Rủi ro thường gặp |
|---|---|---|
| Console | Token, object chứa user data, request config, exception | Log quá rộng, copy output |
| Network | Cookie, Authorization, body, query, response, WebSocket | Copy as cURL, HAR, replay |
| Application/Storage | Cookie, Local/Session Storage, IndexedDB, Cache | Token lưu lâu, profile dùng chung |
| Sources | Bundle, source map, env/config, runtime scope | Secret bị build vào frontend, breakpoint |
| Memory/Performance | Heap, closure, request data, user objects | Snapshot/recording chứa dữ liệu |
| Security/Issues | Origin, certificate, policy diagnostics | Chụp ảnh kèm URL hoặc định danh nội bộ |
| DevTools workspace/Overrides | Source hoặc response đã lưu cục bộ | File debug bị đồng bộ/chia sẻ |

Panel và tên menu thay đổi giữa Chrome, Edge, Firefox và Safari. Hãy tập trung vào loại dữ liệu và thao tác export thay vì phụ thuộc một vị trí giao diện cố định.

## 3. Console: log có thể biến thành bản sao của secret

Console hữu ích để xem trạng thái, lỗi và object trong runtime. Rủi ro xuất hiện khi ứng dụng ghi toàn bộ request, response hoặc object người dùng.

### 3.1 Không log toàn bộ request config

Ví dụ không an toàn:

~~~js
console.log("request config", {
  url,
  headers,
  body,
  user
});
~~~

Nếu `headers` chứa Authorization hoặc cookie, `body` có password/PII, log sẽ tạo thêm một bản sao dữ liệu nhạy cảm. Khi bật Preserve log, điều hướng hoặc reload không nhất thiết xóa toàn bộ nội dung đang hiển thị.

Cách tốt hơn là log metadata cần cho chẩn đoán:

~~~js
console.info("API request", {
  route: "/api/profile",
  method: "GET",
  status: 200,
  requestId: "req-test-42",
  durationMs: 84
});
~~~

Không đưa token, cookie, password, full signed URL hoặc body đầy đủ vào message.

### 3.2 Redact theo tên trường và cấu trúc

Một logger có thể che các field nhạy cảm đã biết trước khi ghi:

~~~js
const SENSITIVE_KEYS = new Set([
  "authorization",
  "cookie",
  "set-cookie",
  "password",
  "access_token",
  "refresh_token",
  "api_key",
  "client_secret"
]);

function redactObject(value) {
  if (Array.isArray(value)) {
    return value.map(redactObject);
  }

  if (!value || typeof value !== "object") {
    return value;
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      SENSITIVE_KEYS.has(key.toLowerCase())
        ? "[REDACTED]"
        : redactObject(item)
    ])
  );
}
~~~

Đây chỉ là ví dụ minh họa. Logger production phải xử lý header không phân biệt hoa thường, key lồng sâu, URL query, nested array, form data, binary payload và field alias của hệ thống. Allowlist các trường được phép log thường an toàn hơn việc cố nhận diện mọi secret có thể có.

### 3.3 Console history và object inspection

Khi log object, DevTools có thể giữ tham chiếu object và hiển thị trạng thái khi mở rộng. Hãy tránh log object chứa credential hoặc dữ liệu cá nhân ngay từ đầu; che sau khi log không đảm bảo bản gốc chưa được giữ trong runtime.

Các thao tác như Store as global variable, copy object hoặc evaluate expression có thể tạo thêm tham chiếu hoặc bản sao. Chỉ dùng với dữ liệu giả lập hoặc object đã được lọc.

### 3.4 Self-XSS và paste vào Console

Attacker có thể thuyết phục người dùng dán một đoạn JavaScript vào Console với lời hứa sửa lỗi, mở khóa tính năng hoặc nhận quà. Đoạn mã đó chạy trong context trang đang mở và có thể đọc dữ liệu mà trang có quyền truy cập.

- Không dán lệnh từ chat, issue hoặc website chưa xác minh.
- Đọc và hiểu toàn bộ code trước khi chạy.
- Không chạy snippet trên tài khoản production đang đăng nhập nếu chưa cần thiết.
- Không dùng Console như nơi nhập password, token hoặc private key.
- Không chia sẻ output Console chưa được rà soát.

## 4. Network: nơi secret thường xuất hiện rõ nhất

Network panel cho thấy request và response mà browser thực hiện. Đây là nơi dễ vô tình tiết lộ credential nhất vì nhiều cơ chế xác thực được truyền cùng request.

### 4.1 Request headers

Một request có thể chứa:

~~~http
GET /api/me HTTP/1.1
Authorization: Bearer <ACCESS_TOKEN>
Cookie: session=<SESSION_ID>
X-CSRF-Token: <CSRF_TOKEN>
~~~

Các giá trị trong ví dụ là placeholder. Khi mở request thật, DevTools có thể hiển thị credential hoặc cookie tương ứng. Không chụp ảnh hoặc copy nguyên phần headers vào ticket công khai.

### 4.2 Query string và URL

Một số hệ thống cũ đặt token trong query:

~~~http
GET /download?token=<SIGNED_TOKEN>
~~~

URL có thể xuất hiện trong Network, browser history, server/proxy logs, analytics, screenshot và Referer tùy policy. Tránh đưa access token, reset token hoặc signed secret vào query khi có phương án header/body an toàn hơn. Nếu giao thức bắt buộc dùng capability URL, giới hạn thời hạn, scope và khả năng sử dụng lại.

### 4.3 Request body và response body

Request/response body có thể chứa:

- Password hoặc OTP trong luồng xác thực.
- PII trong profile/search/export.
- Refresh token hoặc OAuth code.
- Payment metadata.
- Dữ liệu nghiệp vụ nội bộ.
- Error detail chứa stack trace hoặc identifier.

Dữ liệu không trở nên công khai chỉ vì nó được trả về dưới dạng JSON. Kiểm soát authorization, field minimization và logging ở server vẫn là trách nhiệm của API.

### 4.4 WebSocket và EventStream

WebSocket frames có thể mang access token, session metadata, chat message hoặc dữ liệu người dùng. EventSource/SSE có thể stream event chứa thông tin nhạy cảm. Khi debug, kiểm tra cả frames/events và xem liệu dữ liệu có bị export hoặc ghi lại trong recording hay không.

### 4.5 Copy as cURL và Copy as fetch

Các thao tác sao chép request có thể tạo command chứa:

- Authorization header.
- Cookie.
- CSRF token.
- Query parameter nhạy cảm.
- Request body chứa PII hoặc secret.

Command đó có thể bị lưu trong clipboard manager, shell history, terminal scrollback, issue, chat hoặc script tạm. Nếu cần tái hiện bug, hãy tạo request tối giản với tài khoản test và thay credential bằng placeholder. Không chạy lại một request mutation trên production chỉ vì DevTools đã tạo sẵn lệnh.

### 4.6 Replay, Edit and Resend

Replay request có thể thực hiện hành động thật: tạo đơn, thay đổi email, xóa dữ liệu, gửi thanh toán hoặc rotate credential. Trước khi gửi lại:

1. Xác định method và side effect.
2. Kiểm tra môi trường và tài khoản đang dùng.
3. Thay dữ liệu nhạy cảm bằng fixture khi có thể.
4. Kiểm tra idempotency và khả năng rollback.
5. Không dùng Replay để thử credential của người khác.

### 4.7 HAR export

HAR (HTTP Archive) ghi lại thông tin phiên network để phân tích request timing và nội dung. Tùy công cụ và lựa chọn export, HAR có thể chứa URL, query, headers, cookie, request/response body và dữ liệu cá nhân.

Hãy xem HAR như bản sao có thể chứa credential. Trước khi chia sẻ:

- Chỉ thu thập đúng khoảng thời gian và request cần thiết.
- Dùng tài khoản test, dữ liệu giả và môi trường staging.
- Loại bỏ Authorization, Cookie, Set-Cookie, token, signed URL và PII.
- Rà soát cả query string và body, không chỉ headers.
- Mở file đã làm sạch để xác nhận không còn secret.
- Chia sẻ qua nơi được phê duyệt và giới hạn người nhận.
- Xóa bản tạm và kiểm soát bản sao trong ticket/chat/cloud storage.

Ngay cả khi browser có chế độ export đã loại bỏ một số header nhạy cảm, hãy kiểm tra file thực tế. Redaction tự động có thể không nhận ra token nằm trong custom header, JSON field hoặc URL.

## 5. Application và Storage: dữ liệu tồn tại trong browser profile

Application panel (hoặc Storage Inspector ở Firefox) giúp xem cookie, Local Storage, Session Storage, IndexedDB, Cache Storage và Service Worker. Những nơi này có thể chứa dữ liệu xác thực hoặc dữ liệu cá nhân.

### 5.1 Cookie

Cookie session thường là credential dạng bearer: ai có thể sử dụng cookie hợp lệ có thể hành động như session tương ứng, tùy policy server.

Các thuộc tính quan trọng:

| Thuộc tính | Tác dụng |
|---|---|
| `HttpOnly` | Ngăn JavaScript trang đọc cookie qua document.cookie |
| `Secure` | Chỉ gửi cookie qua kết nối HTTPS |
| `SameSite` | Giới hạn một số ngữ cảnh gửi cookie cross-site |
| `Domain` | Xác định host/domain được nhận cookie |
| `Path` | Giới hạn đường dẫn request phù hợp |
| `Max-Age` / `Expires` | Giới hạn thời gian tồn tại |

DevTools vẫn có thể cho người dùng cục bộ xem cookie trong storage inspector, kể cả cookie HttpOnly. Không chụp ảnh hoặc export giá trị cookie thật. Khi chia sẻ bằng chứng, chỉ hiển thị tên cookie, thuộc tính cần phân tích và giá trị đã che.

### 5.2 Local Storage và Session Storage

Hai loại storage này lưu string theo origin và có thể được đọc bởi JavaScript cùng origin. Nếu ứng dụng đặt access token trong Local Storage, bất kỳ XSS nào chạy trong origin đó có thể đọc token.

- Local Storage tồn tại qua các phiên browser cho đến khi bị xóa.
- Session Storage thường gắn với tab/page session và có vòng đời khác.
- Cả hai đều có thể xem và chỉnh sửa trong DevTools.
- Không lưu password, refresh token dài hạn hoặc secret server-side ở đây.

Dùng storage phù hợp với threat model. Nếu dùng cookie HttpOnly cho session, vẫn cần CSRF protection và cookie flags phù hợp.

### 5.3 IndexedDB

IndexedDB lưu dữ liệu có cấu trúc, blob và object lớn. Nó có thể chứa offline records, profile cache, queued requests hoặc token tùy thiết kế.

Hãy kiểm tra schema và dữ liệu nhạy cảm được lưu. Không giả định IndexedDB khó truy cập hơn Local Storage theo cách có thể bảo vệ secret trước XSS: JavaScript cùng origin có thể gọi API IndexedDB.

### 5.4 Cache Storage và Service Worker

Service Worker có thể cache response, request và tài nguyên ứng dụng. Một cache rule quá rộng có thể giữ JSON riêng tư, response xác thực hoặc dữ liệu của user trước đó.

- Chỉ cache route public hoặc dữ liệu offline đã được thiết kế.
- Loại trừ token endpoint và response có credential.
- Tách cache theo user/session nếu sản phẩm thực sự cần cache dữ liệu cá nhân.
- Xóa cache phù hợp khi logout hoặc chuyển account.
- Kiểm tra Service Worker update và version migration.

Xóa Cache Storage không thu hồi token phía server. Nếu credential đã lộ, phải revoke/rotate ở nơi cấp credential.

### 5.5 Xóa dữ liệu khi logout

Logout nên kết hợp server-side session invalidation với cleanup phía client theo thiết kế:

1. Gọi endpoint logout/revoke nếu giao thức hỗ trợ.
2. Xóa cookie/session theo đúng Domain/Path và policy.
3. Xóa token tạm trong memory/storage.
4. Xóa cache user-specific và dữ liệu offline cần loại bỏ.
5. Dừng tác vụ nền hoặc request queue có thể gửi credential cũ.
6. Chuyển UI về trạng thái chưa xác thực.

Không dựa vào nút Clear site data trong DevTools như quy trình logout của sản phẩm. Nút đó là công cụ debug và có thể xóa cả dữ liệu ứng dụng khác của người dùng.

## 6. Sources: bundle, source map và runtime variables

Sources panel cho phép xem source đã tải, đặt breakpoint, xem Scope và điều tra JavaScript runtime. Đây là nơi phát hiện secret bị đóng gói nhầm trong frontend.

### 6.1 Mọi giá trị trong frontend bundle đều có thể công khai

Ví dụ cấu hình build:

~~~js
const API_BASE_URL = "https://api.example.test";
const PUBLIC_CLIENT_ID = "web-client";
const PRIVATE_API_KEY = "sk_live_example_secret";
~~~

`API_BASE_URL` và public client ID có thể là cấu hình công khai theo thiết kế. Private API key không được xuất hiện trong JavaScript bundle, HTML, source map hoặc request frontend.

Các biến môi trường có prefix dành cho frontend framework thường được thay thế vào bundle tại build time. Tên biến có chữ SECRET không làm giá trị trở thành bí mật sau khi đã gửi xuống browser.

### 6.2 Source map có thể tiết lộ nhiều hơn bundle

Source map có thể ánh xạ code minified về source gốc. Nếu map chứa `sourcesContent`, người xem có thể đọc source gốc, comment, tên module và cấu trúc dự án.

Trước khi publish:

- Kiểm tra source map có chứa source nội bộ không cần công khai.
- Không để secret trong source gốc hoặc build config.
- Kiểm soát quyền truy cập source map nếu cần dùng trong error tracking.
- Không coi việc tắt source map là biện pháp bảo vệ secret đã bị bundle hóa.
- Rà soát build artifact và static asset trước release.

Nếu private key từng xuất hiện trong source map public, hãy xem nó như đã lộ và xử lý credential.

### 6.3 Breakpoint và Scope

Khi dừng tại breakpoint, DevTools có thể hiển thị local variables, closure variables, function arguments và object trong scope hiện tại. Token có thể được giữ trong biến tạm dù ứng dụng không lưu nó vào Local Storage.

Không chụp Scope panel hoặc copy object đang chứa credential. Hãy đặt breakpoint trên fixture/test account, hoặc xem các thuộc tính không nhạy cảm đã được lọc.

### 6.4 Watch, Store as global và Snippets

Watch expression và Store as global variable giúp kiểm tra object phức tạp. Chúng cũng có thể tạo thêm tham chiếu tới object chứa dữ liệu nhạy cảm.

Snippets cho phép chạy JavaScript trong context trang. Chỉ chạy snippet do bạn kiểm soát, đã đọc và phù hợp origin hiện tại. Một snippet có thể đọc DOM/storage mà trang có quyền truy cập hoặc gửi request với session đang đăng nhập.

### 6.5 Workspace và Local Overrides

DevTools có thể liên kết workspace với file cục bộ hoặc lưu Local Overrides để thử sửa response. Nội dung được override, source đã chỉnh và response body có thể nằm trong thư mục người dùng.

Không đặt workspace trong thư mục đồng bộ công khai nếu nó chứa dữ liệu thật. Rà soát file override trước khi commit, upload hoặc chia sẻ; không coi nội dung chỉ dùng để debug là vô hại.

## 7. Memory, Performance và bản ghi debug

Memory snapshot và performance recording hữu ích khi tìm memory leak hoặc vấn đề hiệu năng. Chúng có thể ghi lại object đang tồn tại trong runtime.

### 7.1 Heap snapshot

Heap snapshot có thể chứa:

- String token hoặc cookie đã được đọc vào JavaScript.
- Request/response object.
- Profile, message hoặc PII.
- Closure và object graph.
- Dữ liệu form trước khi submit.

Không tạo heap snapshot từ user session thật nếu không cần. Nếu bắt buộc, dùng quy trình bảo vệ artifact tương đương dữ liệu production nhạy cảm: quyền truy cập hạn chế, thời gian lưu ngắn và redaction/cleanup.

### 7.2 Performance recording

Recording có thể bao gồm URL, resource name, script stack, timing và dấu vết tương tác. Query string hoặc tên tài nguyên đôi khi chứa identifier hoặc signed URL.

Thu thập đúng thao tác tái hiện, dùng dữ liệu giả, rà soát nội dung trước khi export và không upload recording nguyên bản vào dịch vụ công khai.

### 7.3 Console/Network log và Preserve log

Preserve log giúp giữ thông tin qua navigation để điều tra redirect hoặc request nhiều bước. Khi xong, tắt nếu không còn cần và đóng tab debug. Việc tắt Preserve log không xóa các HAR, screenshot, clipboard hoặc file đã export trước đó.

## 8. Extensions và remote debugging

DevTools hoạt động trong một browser profile có thể được mở rộng bởi extension và công cụ debug từ xa. Một profile chứa session production không nên cài tiện ích tùy tiện hoặc bật cổng điều khiển rộng.

### 8.1 Browser extensions

Extension có quyền phù hợp có thể đọc nội dung trang, tab, request hoặc tương tác với DevTools. Một extension độc hại hoặc bị chiếm quyền có thể thu thập thông tin đang hiển thị trong browser.

- Chỉ cài extension từ nguồn tin cậy và được tổ chức phê duyệt.
- Đọc permission trước khi cài và khi extension yêu cầu thêm quyền.
- Gỡ extension không còn dùng.
- Không dùng profile production để thử extension mới.
- Không cho phép extension đọc mọi site nếu không cần.
- Cập nhật browser và extension từ nguồn chính thức.

### 8.2 Remote debugging và Chrome DevTools Protocol

Remote debugging cho phép công cụ khác điều khiển browser hoặc quan sát target qua protocol. Nếu cổng debug bị bind ra interface mạng, forward qua tunnel không an toàn hoặc để process không tin cậy kết nối, người đó có thể có quyền rất rộng trên browser session.

Rủi ro có thể bao gồm đọc page content, điều khiển tab, quan sát request và thao tác với trạng thái đã đăng nhập.

- Chỉ bật remote debugging khi thực sự cần.
- Giới hạn listener ở loopback hoặc kênh đã được kiểm soát.
- Không expose debugging port ra mạng công cộng.
- Đóng browser/debug process và tunnel sau khi hoàn tất.
- Không attach debugger không rõ nguồn vào profile có session thật.
- Dùng profile test riêng cho automation hoặc remote inspection.

### 8.3 Thiết bị di động và browser remote inspection

Khi debug browser trên điện thoại qua USB hoặc remote target, màn hình DevTools trên máy phát triển có thể hiển thị dữ liệu của phiên mobile. Kiểm tra máy nào đang được tin cậy, ai có thể truy cập máy phát triển và artifact được lưu ở đâu.

Không để điện thoại production đã đăng nhập kết nối lâu dài với máy dùng chung hoặc máy không được quản lý.

### 8.4 Browser profile và thiết bị dùng chung

Profile browser có thể giữ cookie, storage, cache, download, extension và lịch sử. Đăng xuất UI không nhất thiết xóa mọi dữ liệu cục bộ hoặc file debug đã tạo.

Trên thiết bị dùng chung:

- Dùng profile riêng hoặc Guest mode theo policy.
- Không bật sync cá nhân trên profile debug dùng chung.
- Không lưu credential thật trong Snippets, Overrides hoặc workspace.
- Đóng tab và browser profile sau phiên làm việc.
- Đăng xuất và thu hồi session nếu có nghi ngờ người khác đã truy cập.
- Không để HAR, screenshot hoặc cURL command trong thư mục Downloads dùng chung.

## 9. Quy trình debug an toàn

Debug an toàn bắt đầu trước khi mở Network hoặc Console. Mục tiêu là thu thập đủ bằng chứng để giải thích lỗi, đồng thời giới hạn số lượng secret xuất hiện trong artifact.

### 9.1 Chuẩn bị phiên debug

1. Chọn staging hoặc môi trường test nếu có thể.
2. Dùng tài khoản test với dữ liệu giả và quyền tối thiểu.
3. Tạo credential ngắn hạn, scope hẹp và có thể revoke.
4. Đóng tab/profile không liên quan.
5. Tắt extension không cần thiết theo policy.
6. Xác định trước panel, request và khoảng thời gian cần thu thập.
7. Thống nhất nơi lưu artifact và người được phép nhận.

Không dùng production credential chỉ vì lỗi chưa tái hiện được ở staging. Nếu cần điều tra production, giảm phạm vi dữ liệu và dùng quy trình incident/support đã được phê duyệt.

### 9.2 Thu thập ít nhất có thể

Ưu tiên các dữ liệu sau:

- Request ID hoặc correlation ID.
- Timestamp và timezone.
- Route đã loại bỏ identifier nhạy cảm.
- HTTP method và status code.
- Duration, timing và lỗi mạng.
- Tên header hoặc cookie cần kiểm tra, không cần giá trị.
- Phiên bản browser, build và môi trường.
- Mô tả thao tác tái hiện bằng dữ liệu giả.

Chỉ thu thập request/response body khi đó là điều kiện cần để xác định lỗi. Không export toàn bộ session chỉ để chứng minh một status code sai.

### 9.3 Tạo bản sao đã redaction

Nếu cần chia sẻ HAR, screenshot hoặc log:

1. Tạo bản sao làm việc.
2. Che credential, PII, signed URL và identifier.
3. Rà soát cả headers, query, body, response và metadata.
4. Mở artifact đã làm sạch để kiểm tra lần cuối.
5. Lưu bản đã làm sạch ở vị trí được phê duyệt.
6. Hạn chế quyền truy cập và thời gian lưu.
7. Xóa bản gốc/tạm theo chính sách lưu trữ và xử lý sự cố.

Không sửa trực tiếp bản evidence gốc nếu tổ chức cần giữ bằng chứng phục vụ điều tra. Giữ bản gốc trong kho được kiểm soát; tạo bản redacted riêng để chia sẻ.

### 9.4 Bảng xử lý artifact

| Artifact | Có thể chứa | Trước khi chia sẻ |
|---|---|---|
| Screenshot | URL, account, cookie UI, PII, notification | Crop và che kín bằng vùng opaque, kiểm tra ảnh đã flatten |
| HAR | Headers, cookies, query, body, response | Redact toàn bộ trường nhạy cảm và mở kiểm tra |
| cURL/fetch copy | Authorization, cookie, CSRF token, body | Thay credential bằng placeholder; không đưa vào shell history |
| Console log | Object, token, PII, stack context | Dùng log metadata hoặc redacted copy |
| Heap snapshot | String và object runtime | Tránh tạo từ production; lưu như artifact nhạy cảm |
| Source map | Source code, comment, path, embedded source | Kiểm tra sourcesContent và quyền truy cập |
| Performance trace | URL, stack, interaction, resource | Giảm phạm vi ghi và rà soát trước export |
| Local Overrides/workspace | Response hoặc source đã sửa | Rà soát file trước commit/sync/share |

### 9.5 Screenshot và ảnh chụp màn hình

Một screenshot tưởng như chỉ có status code có thể chứa URL đầy đủ, tên tài khoản, tab khác, bookmark, notification hoặc token trong query.

- Đóng tab không liên quan và ẩn notification.
- Không chụp URL có secret.
- Dùng vùng che đặc hoàn toàn thay vì blur nhẹ.
- Flatten/export ảnh sau khi che để loại bỏ layer có thể chỉnh lại.
- Mở ảnh đã xuất để kiểm tra các góc và metadata hiển thị.
- Không dùng screenshot để thay thế HAR đã được làm sạch khi cần phân tích protocol.

### 9.6 Copy cURL an toàn

Không dán cURL được sao chép nguyên trạng vào issue hoặc chat. Tạo request tối giản với placeholder:

~~~bash
curl -i https://api.example.test/api/profile \
  -H "Authorization: Bearer <REDACTED_TEST_TOKEN>" \
  -H "Accept: application/json"
~~~

Thay placeholder bằng credential test chỉ trong môi trường được phép. Nếu phải chạy command với secret thật, dùng cơ chế credential an toàn của hệ thống và tránh lưu vào shell history, script, process arguments hoặc terminal transcript. Cách truyền secret an toàn tùy shell và hệ điều hành; đừng giả định biến môi trường luôn an toàn trong mọi môi trường.

## 10. Ngăn secret lọt vào frontend và debug output

### 10.1 Phân loại key theo khả năng công khai

Một số API có public client identifier hoặc browser key được thiết kế để xuất hiện phía client. Chúng vẫn cần giới hạn theo domain, API, quota và quyền.

Private API key, signing key, database credential và server-to-server secret phải ở backend hoặc secret manager. Nếu browser cần gọi dịch vụ cần secret, backend/BFF thực hiện request thay browser và chỉ trả dữ liệu đã được phép.

### 10.2 Không đóng gói secret vào build

Kiểm tra:

- Source code và frontend environment variables.
- Build-time replacement và bundler define.
- HTML bootstrap/config endpoint.
- JavaScript chunk và lazy-loaded module.
- Source map và sourcesContent.
- Static JSON config và manifest.
- Error message, comment và debug flag.

Nếu secret xuất hiện trong bundle hoặc source map đã public, xóa khỏi source là chưa đủ. Hãy revoke/rotate credential và build lại artifact sạch.

### 10.3 Logging theo allowlist

Thiết kế log theo danh sách trường được phép, ví dụ:

~~~js
function logApiResult(result) {
  logger.info("api_result", {
    requestId: result.requestId,
    route: result.route,
    method: result.method,
    status: result.status,
    durationMs: result.durationMs
  });
}
~~~

Không serialize toàn bộ request/response object. Redaction là lớp phòng vệ bổ sung; allowlist giúp tránh log nhầm field mới được thêm sau này.

### 10.4 Không để error response làm lộ secret

Error message không nên chứa:

- Authorization header hoặc cookie.
- Full URL có signed token.
- Password/reset token.
- Database connection string.
- Private filesystem path.
- Stack trace production.
- Nội dung request body nhạy cảm.

Trả client một mã lỗi/correlation ID; lưu chi tiết cần thiết trong log server đã được kiểm soát và redact.

### 10.5 Kiểm tra artifact trong CI/CD

Có thể thêm secret scanning cho repository và build output. Quy trình nên:

- Quét source, config và generated bundle.
- Dùng pattern/entropy detection kết hợp allowlist có review.
- Chặn build khi phát hiện credential thật.
- Tránh in giá trị secret vào CI log khi scanner phát hiện.
- Rà soát false positive và exception có người chịu trách nhiệm.
- Kiểm tra artifact sau build, không chỉ source tree.

Secret scanner giảm xác suất lỗi nhưng không chứng minh bundle an toàn tuyệt đối. Cần giữ nguyên nguyên tắc không đưa server secret vào browser.

## 11. Khi phát hiện secret trong DevTools hoặc artifact

Xem secret đã xuất hiện trong screenshot, HAR, Console, cURL, bundle hoặc source map là một sự cố tiềm ẩn. Việc xóa file không thu hồi quyền mà credential đã cấp.

### 11.1 Phân loại và giới hạn phạm vi

Xác định:

- Loại secret: session cookie, access token, refresh token, API key, signed URL, OAuth code hay password.
- Credential còn hiệu lực hay đã hết hạn.
- Scope, audience, tenant và quyền được cấp.
- Nơi đã xuất hiện: browser, clipboard, HAR, ticket, chat, CI log, cloud drive hoặc source map.
- Ai có thể truy cập artifact và có thể đã tải bản sao hay chưa.
- Có dấu hiệu sử dụng trái phép trong audit log hay không.

Không paste secret vào báo cáo sự cố chỉ để mô tả nó. Dùng tên credential, fingerprint đã che hoặc ID do hệ thống quản lý.

### 11.2 Revoke hoặc rotate trước khi cleanup

Tùy loại credential:

| Loại | Hành động ưu tiên |
|---|---|
| Session cookie | Invalidate session phía server; yêu cầu đăng nhập lại |
| Access token | Revoke nếu hỗ trợ hoặc chờ expiry theo policy; đánh giá quyền đã cấp |
| Refresh token | Revoke token/family và xử lý rotation/reuse theo hệ thống |
| API key | Disable key cũ, phát key mới với scope tối thiểu |
| Signing/private key | Rotate key, cập nhật verifier/consumer và đánh giá chữ ký đã phát |
| Signed URL | Revoke nếu hỗ trợ, giảm TTL hoặc vô hiệu object/link |
| Password | Reset theo quy trình; kiểm tra reuse và session liên quan |
| OAuth authorization code | Để hết hiệu lực/revoke flow nếu có; kiểm tra redirect/client binding |

Không phải hệ thống nào cũng hỗ trợ revoke ngay mọi loại token. Nếu không thể revoke, giảm thời hạn hoặc quyền, giám sát việc sử dụng và áp dụng biện pháp thay thế theo quy trình vận hành.

### 11.3 Audit và xác định tác động

Kiểm tra audit log, auth log và API usage trong khoảng thời gian credential có thể bị lộ. Tìm các dấu hiệu như IP/region bất thường, user agent mới, quyền truy cập dữ liệu ngoài dự kiến, token reuse hoặc hành động không do chủ tài khoản thực hiện.

Giữ evidence gốc trong kho có quyền truy cập hạn chế. Không chỉnh sửa hoặc phát tán bản gốc qua chat thông thường.

### 11.4 Cleanup các bản sao

Sau khi credential đã được revoke/rotate và evidence cần thiết được bảo toàn:

- Xóa artifact khỏi ticket/chat/cloud drive theo retention policy.
- Thu hồi quyền truy cập và link chia sẻ.
- Xóa clipboard manager history hoặc file tạm nếu có thể và được phép.
- Xóa HAR, screenshot, cURL transcript và heap snapshot khỏi thư mục cá nhân.
- Gỡ secret khỏi source/build/source map và phát hành artifact mới.
- Làm sạch CI log hoặc kho log theo khả năng và quy trình tổ chức.
- Kiểm tra các bản sao đã được tải xuống; không giả định xóa bản gốc xóa được bản sao.

### 11.5 Thông báo và ghi nhận

Báo cho người phụ trách security/incident response theo quy trình tổ chức. Ghi nhận thời điểm, loại credential, scope, hành động revoke/rotate, artifact liên quan và kết quả audit. Chỉ đưa thông tin đã che vào ticket chia sẻ rộng.

Không kết luận “đã an toàn” chỉ vì file HAR hoặc screenshot đã bị xóa; cần xác nhận credential cũ không còn quyền sử dụng hoặc đã hết hiệu lực.

## 12. Bài thực hành

Chỉ dùng môi trường lab, tài khoản test và giá trị giả như `TEST_ACCESS_TOKEN_DO_NOT_USE`. Không dùng credential production.

### Bài 1: Tìm bề mặt lộ dữ liệu trong Network

Tạo endpoint lab trả một request ID và một header giả. Mở Network, xác định request URL, headers, body và response. Ghi lại tên trường cần kiểm tra nhưng không copy giá trị.

### Bài 2: Phân biệt cookie flags

Dùng hai cookie test: một cookie HttpOnly và một cookie không HttpOnly. So sánh khả năng đọc bằng document.cookie với khả năng quan sát trong storage inspector. Giải thích vì sao HttpOnly không phải cơ chế che cookie khỏi chủ thiết bị.

### Bài 3: Redact Console log

Tạo object chứa các field giả như access_token, password và displayName. Áp dụng logger allowlist hoặc redaction helper. Xác nhận output chỉ còn metadata cần thiết.

### Bài 4: HAR có dữ liệu giả

Ghi lại một request lab, export HAR và kiểm tra headers, query, body và response. Tạo bản redacted, mở lại và xác nhận token/PII giả đã được loại bỏ. Xóa artifact lab sau khi hoàn thành.

### Bài 5: Source map và frontend build

Tạo bundle demo với cấu hình public và một marker giả không có giá trị truy cập. Kiểm tra bundle/source map để thấy dữ liệu nào người dùng có thể tải. Xác nhận không đưa private key thật vào build.

### Bài 6: Screenshot review

Chụp ảnh Network panel với URL và account giả. Che vùng nhạy cảm bằng opaque rectangle, flatten ảnh và mở file kết quả. Kiểm tra URL bar, tab, profile, notification và phần panel còn sót.

### Bài 7: Remote debugging boundary

Trong browser/profile lab, kiểm tra cách remote debugging được bật và địa chỉ listener. Xác nhận không có listener public; tắt debugging và đóng process/tunnel sau thử nghiệm. Không attach vào browser profile chứa session production.

### Bài 8: Incident tabletop

Giả lập HAR có test token được upload nhầm vào ticket. Viết quy trình: xác định scope, revoke/rotate token test, kiểm tra access log, thu hồi link, xóa bản sao theo policy và ghi nhận kết quả. Không đưa token vào bản báo cáo.

## 13. Checklist DevTools và secret

Trước khi debug:

- [ ] Chọn staging/test và tài khoản test khi có thể.
- [ ] Dùng credential ngắn hạn, scope hẹp và có thể revoke.
- [ ] Xác định panel và request tối thiểu cần quan sát.
- [ ] Kiểm tra extension và browser profile đang sử dụng.
- [ ] Không dùng shared profile có session production nếu không cần.

Trong khi debug:

- [ ] Không log toàn bộ request/response hoặc object người dùng.
- [ ] Không copy cookie, Authorization header, password hoặc token.
- [ ] Không chạy snippet/paste code chưa xác minh trong Console.
- [ ] Kiểm tra side effect trước Replay/Edit and Resend.
- [ ] Không bật Preserve log hoặc recording lâu hơn cần thiết.
- [ ] Không tạo heap snapshot từ production trừ khi quy trình cho phép.

Khi thu thập artifact:

- [ ] Xem HAR, cURL, screenshot, source map và heap snapshot là dữ liệu nhạy cảm.
- [ ] Redact URL query, headers, body, response và metadata.
- [ ] Kiểm tra file sau redaction bằng cách mở lại.
- [ ] Dùng opaque mask và flatten screenshot.
- [ ] Chia sẻ qua nơi được phê duyệt, giới hạn người nhận và thời gian lưu.
- [ ] Không đưa artifact nguyên bản vào chat/ticket công khai.

Trong ứng dụng và pipeline:

- [ ] Không có private API key/signing key trong frontend bundle.
- [ ] Source map không chứa secret hoặc source nội bộ không được phép công khai.
- [ ] Cookie có HttpOnly/Secure/SameSite phù hợp.
- [ ] Token không được lưu lâu trong JavaScript-accessible storage nếu không cần.
- [ ] Logger dùng allowlist và redaction.
- [ ] Error response không lộ secret hoặc stack trace.
- [ ] CI quét source và build artifacts, không in secret ra log.
- [ ] Cache/Service Worker không giữ credential hoặc dữ liệu riêng tư ngoài policy.

Khi phát hiện lộ secret:

- [ ] Phân loại credential và xác định scope/expiry.
- [ ] Revoke/rotate hoặc vô hiệu hóa credential cũ.
- [ ] Kiểm tra audit log và hoạt động đáng ngờ.
- [ ] Bảo toàn evidence gốc trong kho hạn chế.
- [ ] Thu hồi link và dọn các bản sao theo policy.
- [ ] Phát hành lại bundle/config sạch nếu cần.
- [ ] Ghi nhận incident bằng dữ liệu đã che.
- [ ] Xác nhận credential cũ không còn sử dụng được.

## 14. Câu hỏi tự kiểm tra

**1. Vì sao DevTools có thể hiển thị secret?**

Vì browser đã nhận, lưu hoặc sử dụng dữ liệu đó trong request, response, storage hay runtime. DevTools quan sát các bề mặt này để phục vụ debug.

**2. HttpOnly có làm cookie vô hình trong DevTools không?**

Không. HttpOnly ngăn JavaScript trang đọc cookie qua document.cookie, nhưng người dùng cục bộ vẫn có thể xem cookie trong công cụ quản lý browser.

**3. Vì sao Copy as cURL có rủi ro?**

Command có thể mang theo cookie, Authorization, CSRF token và body. Khi paste, dữ liệu có thể đi vào shell history, terminal log, ticket hoặc chat.

**4. HAR có thể chứa những gì?**

URL, query, headers, cookie, request/response body và metadata của phiên network. Phải rà soát toàn bộ trước khi chia sẻ.

**5. Có thể giấu API secret bằng cách minify JavaScript không?**

Không. Bundle và source map được gửi xuống browser có thể được tải và phân tích. Secret phía server phải ở backend/secret manager.

**6. Heap snapshot có nhạy cảm không?**

Có. Nó có thể giữ string token, object user và dữ liệu runtime. Hãy hạn chế tạo, lưu và chia sẻ snapshot.

**7. Vì sao không nên dán snippet lạ vào Console?**

Snippet chạy trong context trang đang mở và có thể đọc dữ liệu hoặc gửi request bằng quyền của phiên hiện tại.

**8. Remote debugging port bị expose có rủi ro gì?**

Người có thể kết nối protocol có thể điều khiển hoặc quan sát browser target và phiên đã đăng nhập. Giới hạn listener và tắt sau khi dùng.

**9. Nếu secret đã xuất hiện trong screenshot/HAR thì làm gì trước?**

Xác định loại và scope, revoke/rotate credential hoặc vô hiệu hóa nó, sau đó audit việc sử dụng và cleanup các bản sao.

**10. Xóa HAR có đủ để kết thúc sự cố không?**

Không. Bản sao có thể đã được tải xuống và credential vẫn có thể còn hiệu lực. Cần xử lý credential, kiểm tra phạm vi truy cập và xác nhận tác động.

## Ghi nhớ

DevTools cho thấy những gì browser đang gửi, nhận, lưu và giữ trong runtime. Hãy coi Network export, Console output, storage, source map, heap snapshot, screenshot và cURL copy là artifact có thể chứa secret. Dùng tài khoản test, log allowlist, redaction đã kiểm tra, chia sẻ có kiểm soát và revoke/rotate credential ngay khi phát hiện lộ.

## Tài liệu tham khảo

- [Chrome DevTools: Console](https://developer.chrome.com/docs/devtools/console/)
- [Chrome DevTools: Network](https://developer.chrome.com/docs/devtools/network/)
- [Chrome DevTools: Application](https://developer.chrome.com/docs/devtools/application/)
- [Chrome DevTools: Sources](https://developer.chrome.com/docs/devtools/sources/)
- [Chrome DevTools: Memory](https://developer.chrome.com/docs/devtools/memory-problems/)
- [Chrome DevTools: Remote Debugging](https://developer.chrome.com/docs/devtools/remote-debugging/)
- [MDN: HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies)
- [MDN: Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API)
- [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP: Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
