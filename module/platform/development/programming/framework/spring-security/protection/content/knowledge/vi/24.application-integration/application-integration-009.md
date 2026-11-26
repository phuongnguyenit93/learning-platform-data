# Trang nhúng, popup và tài nguyên bên thứ ba

## Mục tiêu học tập

Bài học thuộc chương **Tích hợp ứng dụng** của module **SPRING_SECURITY_HTTP_PROTECTION**, tập trung vào cách Spring Security phối hợp với những ranh giới bảo mật do trình duyệt thực thi khi ứng dụng nhúng hoặc mở nội dung từ hệ thống khác.

Sau bài học, người học có thể:

- Phân biệt **top-level navigation, iframe/embed, popup/window.opener, script/font/image từ CDN, fetch/XHR và webhook** theo khả năng đọc dữ liệu, gửi cookie, chạy mã và tác động tới origin ứng dụng.
- Thiết kế chính sách **clickjacking protection** với `X-Frame-Options` và **CSP `frame-ancestors`**, hiểu vì sao `frame-src` không thay `frame-ancestors`.
- Cho phép một trang được nhúng vào đối tác **một cách giới hạn theo route/origin** mà không vô hiệu hóa bảo vệ iframe cho toàn bộ ứng dụng.
- Sử dụng **`<iframe sandbox>`, Permissions Policy/`allow`, `referrerpolicy`** và tách origin để giảm quyền nội dung không tin cậy; nêu được giới hạn của sandbox và điều kiện nguy hiểm khi kết hợp `allow-scripts` với `allow-same-origin`.
- Xây dựng trao đổi qua **`window.postMessage`** có kiểm tra `origin`, `source`, schema, loại thông điệp và correlation; tránh gửi secret hoặc nhận lệnh HTML/JS tùy ý.
- Dùng **`noopener`/`noreferrer`** với popup/link thông thường, đồng thời nhận diện ranh giới bảo mật của popup SSO/OAuth cần kênh trả kết quả.
- Phân tích **SameSite, third-party cookie restrictions, cookie partitioning và Storage Access API** trong iframe đăng nhập, widget nhúng, trang thanh toán và các callback federated login.
- Giảm nguy cơ **third-party script/supply-chain compromise** bằng hạn chế nhà cung cấp, CSP, Subresource Integrity (SRI), version pinning, CSP reporting, kiểm nguồn asset và kế hoạch thu hồi.
- Phân biệt **CORS, Same-Origin Policy (SOP), CSP, CORP, COEP, COOP** để tránh cấu hình chồng chéo hoặc vô tình làm hỏng popup/embedded integration.
- Cấu hình và kiểm thử bảo vệ header, CSRF, CORS, frame policy cho **Servlet/Spring MVC và Reactive/WebFlux** bằng `MockMvc`, `WebTestClient`, browser E2E và công cụ Network.
- Chẩn đoán lỗi “Refused to frame”, sandbox block, CORS, CSP, SRI hash mismatch, popup bị chặn, `window.opener` bị tách, cookie không gửi trong iframe và các phản hồi HTTP do proxy gây ra.

## 1. Bối cảnh: tích hợp hệ thống không đồng nghĩa chia sẻ quyền

Một ứng dụng có thể vừa:

1. Hiển thị dashboard của công ty trong iframe ở cổng đối tác.
2. Nhúng video, bản đồ hoặc cổng thanh toán từ nhà cung cấp vào trang của chính ứng dụng.
3. Mở cửa sổ đăng nhập liên kết qua IdP, chờ kết quả để cập nhật giao diện.
4. Tải JavaScript/CSS/font từ CDN và gọi API của bên thứ ba.
5. Nhận webhook server-to-server từ nhà cung cấp thanh toán.

Những thao tác trên trông giống nhau vì đều “làm việc với bên thứ ba”, nhưng có **các ranh giới tin cậy hoàn toàn khác nhau**.

Ví dụ hệ thống:

~~~text
Ứng dụng chính / Spring RP:  https://app.example.com
Đối tác nhúng dashboard:     https://partner.example.net
Widget đặt trong app:       https://widget.vendor.example
Nhà cung cấp định danh:      https://login.identity.example
CDN JavaScript:              https://cdn.vendor.example
Webhook:                     POST /integrations/payment/webhook
~~~

**Không được** coi một domain đã được phép mở iframe là domain được đọc dữ liệu người dùng, gửi lệnh POST, thực thi script trong parent page hoặc xác thực webhook. Mỗi quyền phải được cấp **đúng cơ chế và đúng hướng**.

### 1.1. Sơ đồ các ranh giới

~~~mermaid
flowchart LR
    U[Browser người dùng] --> P[Trang chính tại app.example.com]
    P -->|iframe src| W[Widget tại widget.vendor.example]
    P -->|script src| J[JavaScript CDN của nhà cung cấp]
    P -->|window.open| O[IdP hoặc popup bên ngoài]
    P -->|fetch API| A[API khác origin]
    Partner[Trang partner.example.net] -->|iframe src| E[Trang /embed/report tại Spring app]
    Provider[Payment provider backend] -->|HTTPS webhook| H[Spring webhook endpoint]
~~~

**Câu hỏi bảo mật cần hỏi cho từng mũi tên:**

- Ai **chọn URL**? Có cho nhập domain bất kỳ không?
- Mã của bên thứ ba chạy **trong origin nào**?
- Browser có gửi cookie/session RP hoặc IdP không?
- Ai có thể **đọc response** hoặc thao tác DOM?
- Ai xác minh identity/quyền trên tài nguyên?
- Header/CSRF policy phát ở **document nào**, bởi Spring, reverse proxy hay CDN?
- Khi integration thất bại, chức năng còn an toàn và dữ liệu có bị rò không?

### 1.2. Khái niệm then chốt: nhập mã và nhập giao diện là hai việc khác nhau

Hai đoạn markup:

~~~html
<iframe src="https://widget.vendor.example/chat"></iframe>

<script src="https://cdn.vendor.example/chat.js"
        defer></script>
~~~

không có cùng rủi ro.

- **Iframe khác origin**: nội dung chạy trong browsing context và origin của widget, bị Same-Origin Policy hạn chế đọc DOM của parent. Vẫn cần kiểm framing policy, sandbox, postMessage, cookies, UI overlay, clickjacking và quyền của widget.
- **Script tải từ CDN khác origin**: sau khi được chấp nhận, JavaScript thực thi **trong origin/quyền của trang đã nhúng script**. Nó có thể đọc DOM, lấy CSRF token lộ trong HTML, phát request dưới phiên người dùng và thao tác UI; `HttpOnly` ngăn đọc cookie trực tiếp nhưng **không ngăn script same-origin gửi request**.

Vì vậy một JavaScript bên thứ ba thường đòi **mức độ tin cậy cao hơn nhiều** so với một iframe cross-origin được sandbox phù hợp.

## 2. Origin, site, browsing context và hướng đi của dữ liệu

### 2.1. Origin không phải site

**Origin** của HTTP(S) là tổ hợp **scheme + hostname + port**:

~~~text
https://app.example.com
https://api.example.com
https://app.example.com:8443
http://app.example.com
~~~

Bốn URL trên có những origin khác nhau. Trong khi đó, **site** theo chính sách SameSite hiện đại thường là **schemeful site** — scheme và registrable domain dựa vào Public Suffix List. Hai HTTPS subdomain của cùng registrable domain có thể same-site nhưng cross-origin.

| Cặp URL | Same-origin? | Same-site? | Hệ quả chính |
|---|---|---|---|
| `https://app.example.com` và chính nó | Có | Có | JS cùng origin có thể truy cập cùng DOM theo SOP |
| `https://app.example.com` và `https://api.example.com` | Không | Thường có | Cross-origin fetch cần CORS; cookie vẫn phải đúng Domain/Path |
| `https://app.example.com` và `https://widget.vendor.example` | Không | Không | SOP hạn chế iframe; SameSite/third-party cookies quan trọng |
| `http://app.example.com` và `https://app.example.com` | Không | Khác theo schemeful site | HTTPS/Secure/SameSite có thể đổi hành vi |
| `https://app.example.com` và `https://app.example.com:8443` | Không | Có | Port ảnh hưởng origin, không ảnh hưởng registrable site |

Một cookie **host-only** cho `app.example.com` không tự được gửi sang `api.example.com` dù hai host same-site; `Domain`, `Path`, `Secure`, thời hạn và browser policy phải cùng thỏa.

### 2.2. Những đường đi khác nhau

| Cơ chế | Có navigation không? | JS parent đọc DOM/response đối tác? | Điều kiện quan trọng |
|---|---|---|---|
| `<iframe src="...">` | Tạo browsing context con | Không nếu cross-origin, trừ kênh được cho phép | Parent `frame-src`, child `frame-ancestors`, sandbox, cookies |
| `window.open(url)` | Mở browsing context mới | SOP hạn chế nếu khác origin | Popup blocker, opener/noopener, COOP, OAuth |
| `<script src="...">` | Không | Script chạy bằng quyền **trang nhúng** | CSP `script-src`, SRI, vendor trust |
| `<img src="...">` | Không | Không đọc byte tùy ý chỉ vì ảnh được render | `img-src`, CORS khi xử lý canvas, referrer |
| `<link rel="stylesheet">` | Không | CSS có thể tác động layout/tài nguyên | `style-src`, URL trong CSS, SRI/CORS khi dùng |
| `fetch("https://other/...")` | Không | Bị CORS/response tainting giới hạn | `connect-src`, CORS, credentials |
| HTML `<form action="...">` | Có thể navigate tab/frame | Không cần CORS cho submit navigation | `form-action`, CSRF bên nhận, SameSite |
| Browser top-level `302 Location` | Có | Không cần CORS để điều hướng | Redirect allowlist, protocol tokens |
| Backend webhook POST | Không qua browser | Không áp browser CORS | HMAC/signature, replay/idempotency, network trust |

### 2.3. Same-Origin Policy không thay authorization

SOP ngăn script từ một origin trực tiếp đọc DOM/cookie/response của origin khác trong nhiều ngữ cảnh. Nó **không chứng minh người dùng có quyền xem một file hoặc project**. Nếu widget gọi endpoint Spring `GET /api/projects/99`, backend vẫn phải kiểm principal, tenant và resource ACL; không được dựa vào “iframe khác origin không đọc được” như lớp duy nhất.

Một URL nhúng có thể bị copy/chia sẻ; **`frame-ancestors` chỉ hạn chế browser được phép render nó trong những trang nào**, không cấp hay thu hồi quyền API ở server.

## 3. Threat model: clickjacking, thông điệp giả, script độc hại và dữ liệu rò

### 3.1. Các mục tiêu tấn công

| Nguy cơ | Cách xảy ra | Phòng vệ ưu tiên |
|---|---|---|
| **Clickjacking/UI redressing** | Attacker đặt iframe trong trang giả, che/đè nút | `frame-ancestors`, XFO, UX xác nhận thao tác |
| **Data leak trong embedded page** | Dùng URL ID/secret không kiểm ACL hoặc cache chung | Authentication + object-level authorization, no-store |
| **Cross-origin message spoofing** | Website khác gửi `postMessage` giả lệnh | Kiểm `event.origin`/`source`, schema, nonce/correlation |
| **Popup tabnabbing** | Trang mở thay đổi location của opener | `rel=noopener`, opener policy, COOP khi phù hợp |
| **OAuth popup response injection** | Popup giả báo login success hoặc đưa code/token attacker | State/nonce/PKCE, trusted callback, message verification |
| **Third-party cookie breakage** | Browser không gửi cookie RP/IdP trong iframe | Chọn kiến trúc, Storage Access/partitioning, không bỏ auth |
| **CSRF từ embedded context** | Browser tự gửi credential trên unsafe POST phù hợp cookie policy | Spring CSRF token, method semantics, authorization |
| **Third-party script compromise** | CDN/vendor update chèn JS độc hại vào app origin | Giảm vendor, version pin, CSP/SRI, monitoring |
| **SRI bypass bởi loader động** | File script được pin nhưng tự tải mã khác | CSP strict, dependency audit, không tin chỉ SRI |
| **XSS trong embed content** | Nội dung do user upload chạy cùng RP origin | Origin isolation, sandbox, CSP, sanitization |
| **CORS cấu hình rộng** | API cho origin ngoài đọc credentialed response | Allowlist, credentials policy, auth/ACL |
| **COOP làm mất kênh popup** | Browsing context group tách opener | Kiểm COOP và thiết kế popup flow/fallback |
| **COEP chặn widget** | Cross-origin resource thiếu CORS/CORP opt-in | Xác định nhu cầu isolation, vendor support |
| **Thông tin rò qua Referer** | URL chứa token/PII đi sang third-party asset | Referrer-Policy, token hygiene, không để secret ở URL |
| **Webhook giả** | Attacker tự POST “payment success” tới backend | Signature + timestamp + replay prevention + idempotency |
| **External asset outage** | CDN/IdP/widget lỗi hoặc chậm | Timeouts, graceful fallback, vendor health monitoring |

### 3.2. Clickjacking cụ thể

Attacker xây trang:

~~~html
<div class="decoy">Bấm để nhận phần thưởng</div>
<iframe
  src="https://app.example.com/account/delete"
  class="transparent-overlay"></iframe>
~~~

CSS có thể đặt iframe mờ/đúng vị trí để khiến user **tưởng đang bấm nội dung khác**. Nếu trang được frame, user đã authenticated và hành động nguy hiểm có thể kích hoạt bằng click, đây là UI redressing.

**CSRF token không giải quyết mọi clickjacking**: victim có thể tự tương tác với một trang RP hợp lệ bên trong iframe và trang đó mang CSRF token hợp lệ. Vì vậy cần framing policy trên **response của trang nhạy cảm**, cùng xác nhận thao tác, reauthentication/MFA khi cần.

### 3.3. Khi user là người nhúng nội dung bên thứ ba

Nếu RP là **parent** nhúng một widget, rủi ro khác: widget có thể chèn UI lừa người dùng, nhận dữ liệu qua postMessage, tải tài nguyên từ các origin khác, lạm dụng permission được `allow` cấp, hoặc liên kết tới site lừa đảo. Cần sandbox, hạn chế capability, allowlist provider origin và không đưa secrets vào URL/widget.

### 3.4. Các lớp không được dùng thay thế nhau

- `frame-ancestors` hạn chế **ai được nhúng trang này**.
- `frame-src` hạn chế **trang này được nhúng trang nào**.
- `sandbox` hạn chế quyền một browsing context con.
- SOP kiểm hạn chế truy cập cross-origin của JS.
- CORS kiểm khả năng JS đọc cross-origin response theo policy.
- Spring Security CSRF kiểm unsafe browser requests.
- Authentication/authorization kiểm caller và object.
- SRI kiểm byte tải của **một subresource đã pin**, không kiểm hành vi nghiệp vụ của JS hợp lệ.
- COOP/COEP/CORP giải quyết isolation và chính sách tải tài nguyên, không thay CSP/cookie/token checks.

## 4. CSP `frame-ancestors` và `frame-src`: hướng vào và hướng ra

### 4.1. Hướng vào: ai được phép nhúng document của RP?

Response của **document đang được nhúng**:

~~~http
HTTP/1.1 200 OK
Content-Security-Policy: frame-ancestors 'none'; default-src 'self'; object-src 'none'
~~~

`frame-ancestors 'none'` chỉ thị browser không cho **bất kỳ ancestor nào** đặt document này trong frame. Đây là lựa chọn hợp lý cho trang account, dashboard quản trị, trang chuyển tiền hoặc các màn hình không cần nhúng.

Một app cho phép tự nhúng trong cùng origin:

~~~http
Content-Security-Policy: frame-ancestors 'self'; default-src 'self'; object-src 'none'
~~~

Một **trang riêng** được đối tác nhúng:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://partner.example.net; default-src 'self'; object-src 'none'
~~~

**Lưu ý quan trọng:**

- `frame-ancestors` cần được gửi trong **HTTP CSP response header** của document được nhúng. Đừng kỳ vọng thẻ `<meta http-equiv="Content-Security-Policy">` dùng để đặt `frame-ancestors` có tác dụng tương đương.
- `frame-ancestors` không mặc nhiên kế thừa từ `default-src`; phải khai báo riêng.
- Browser kiểm **chuỗi ancestors**, không chỉ parent ngay sát bên. Một trang đối tác được nhúng tiếp trong frame của attacker có thể bị chặn nếu attacker không được allow.
- Đúng origin bao gồm scheme/host/port; wildcard `https:` hoặc `*` là cho phép rộng, không phải một allowlist đối tác an toàn.
- `frame-ancestors` **không chứng minh** partner đang authenticated và không cấp quyền đọc dữ liệu trong trang RP.

### 4.2. Hướng ra: parent được tải iframe từ origin nào?

Response của **trang parent RP**:

~~~http
Content-Security-Policy: default-src 'self'; frame-src 'self' https://widget.vendor.example; object-src 'none'
~~~

`frame-src` hạn chế destinations của iframe do **document parent** tạo. Nó **không cho phép widget/vendor nhúng ngược lại parent RP**. Bên widget vẫn có thể gửi `frame-ancestors` để giới hạn ai được nhúng widget.

### 4.3. Cặp kiểm tra độc lập

Giả định `app.example.com` nhúng `widget.vendor.example`:

~~~text
Parent app:
  CSP frame-src https://widget.vendor.example
  → cho phép tạo iframe tới widget

Child widget:
  CSP frame-ancestors https://app.example.com
  → cho phép parent app hiển thị widget

Nếu một trong hai policy chặn → iframe không render
dù bên còn lại đã cho phép.
~~~

Khi ứng dụng của bạn được nhúng vào đối tác, chiều kiểm đổi ngược: **đối tác là parent**, còn Spring app là child. Spring response `frame-ancestors` là nơi cần cấu hình.

### 4.4. `frame-src`, `child-src` và `default-src`

Trong CSP hiện đại, `frame-src` là directive chuyên biệt cho nguồn iframe. Nếu nó vắng, browser có các quy tắc fallback tới `child-src` và `default-src` theo phiên bản CSP; tránh dựa vào fallback mơ hồ. Khai báo `frame-src` rõ ràng khi trang chủ động nhúng partner.

`connect-src` giới hạn fetch/XHR/WebSocket, `script-src` giới hạn scripts, `img-src` giới hạn ảnh, `font-src` cho fonts, `form-action` giới hạn form submission destinations và `frame-ancestors` giới hạn ancestors. **Không dùng một directive để thay quyền của directive khác.**

## 5. X-Frame-Options và CSP: hai cơ chế chống clickjacking

### 5.1. Các giá trị X-Frame-Options còn hữu dụng

`X-Frame-Options` (XFO) là response header có các chế độ phổ biến:

~~~http
X-Frame-Options: DENY
~~~

~~~http
X-Frame-Options: SAMEORIGIN
~~~

- **`DENY`**: ngăn document được render trong frame.
- **`SAMEORIGIN`**: cho phép framing cùng origin theo hành vi browser; không cho nhúng từ partner khác origin.
- **`ALLOW-FROM`** đã lỗi thời, không được hỗ trợ nhất quán trong browser hiện đại; **không** dùng để cấp allowlist đối tác.

`frame-ancestors` trong CSP cung cấp origin allowlist linh hoạt hơn. Khi policy CSP `frame-ancestors` được browser hỗ trợ và thực thi, tiêu chuẩn hiện đại quy định nó **ưu tiên so với XFO**; tuy nhiên browser cũ/cấu hình đặc thù có thể khác. Vì vậy không nên tạo hai header **mâu thuẫn** rồi kỳ vọng mọi browser chọn như nhau.

### 5.2. Mặc định Spring Security và route ngoại lệ

Spring Security Servlet thường gửi `X-Frame-Options: DENY` theo mặc định của security response headers, nên một dashboard không thể nhúng có thể bị chặn ngay cả khi chưa cấu hình CSP. Đây là **hành vi bảo vệ hữu ích**; chỉ thay đổi khi sản phẩm thực sự cần embedding.

**Không nên:**

~~~java
// Mọi trang (bao gồm /account, /admin) đều mất XFO:
http.headers(headers ->
    headers.frameOptions(frame -> frame.disable()));
~~~

Đoạn này tự nó không tạo CSP thay thế và có thể làm mở clickjacking cho toàn bộ ứng dụng.

**Nên:** chỉ áp chính sách riêng lên route cần nhúng, đồng thời bảo vệ những trang còn lại bằng `frame-ancestors 'none'`/XFO DENY.

### 5.3. Ma trận ý định và header

| Ý định | CSP ở document | XFO tương ứng | Ghi chú |
|---|---|---|---|
| Cấm mọi embedding | `frame-ancestors 'none'` | `DENY` | Phù hợp mặc định trang nhạy cảm |
| Chỉ tự nhúng cùng origin | `frame-ancestors 'self'` | `SAMEORIGIN` | Không tự mở cho các subdomain khác origin |
| Cho partner có origin rõ | `frame-ancestors 'self' https://partner.example.net` | **Không phát XFO chặn partner** trên route này | Chỉ áp cho URL chuyên biệt, cân nhắc browser không hỗ trợ CSP |
| Trang public không cần auth nhưng vẫn không được frame | `frame-ancestors 'none'` | `DENY` | Public không đồng nghĩa cần frame |
| Widget của vendor được embed trong app | `frame-ancestors` thuộc **vendor response** | XFO thuộc vendor | Parent Spring chỉ kiểm outbound `frame-src` |

### 5.4. Cẩn thận khi cùng route phục vụ HTML và JSON

Một API `/embed/report.json` trả JSON có thể không cần framing; nhưng nó vẫn cần authentication/authorization đúng, content type chính xác và `nosniff`. Không “giải quyết clickjacking” bằng việc tùy tiện thay toàn bộ API sang public hoặc chấp nhận mọi origin. Chỉ route HTML dự định embed mới cần policy cho phép partner.

## 6. Thiết kế trang nhúng an toàn cho đối tác

Giả sử portal `https://partner.example.net` cần hiển thị báo cáo `https://app.example.com/embed/report/42`.

### 6.1. Tách route/khả năng khỏi trang nghiệp vụ chính

~~~text
App chính:
  GET /account
  GET /admin
  GET /reports/42
  → chống framing, có nav/chức năng nhạy cảm

Trang embed:
  GET /embed/report/42
  → giao diện read-only tối giản
  → allowlist parent origin rõ ràng
  → vẫn kiểm quyền read đối với report 42
~~~

Không dùng chung HTML có nút delete/admin với trang embed chỉ vì “đối tác cần xem một bảng”. Nếu việc nhúng không thực sự cần thao tác, cố ý thiết kế **read-only** và không cấp chức năng mutation.

### 6.2. CSP ở response của /embed/report/42

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; frame-ancestors 'self' https://partner.example.net; object-src 'none'; base-uri 'self'; form-action 'self'
Cache-Control: no-store
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
~~~

Cần kiểm response **không có XFO DENY mâu thuẫn** nếu target là một partner khác origin và có yêu cầu hỗ trợ browser cũ. `form-action 'self'` không cho phép tùy ý submit form tới partner; `script-src 'self'` tránh dùng script bên ngoài nếu không cần.

### 6.3. Framing allowlist không thay user authorization

CSP `frame-ancestors https://partner.example.net` chỉ kiểm browser rendering, **không** chứng minh iframe request do đúng user được phép đọc. Nếu URL chứa report ID của Alice, một user Bob biết URL vẫn không được download report nếu không có ACL.

Các hướng phổ biến:

- Người dùng đã đăng nhập RP trong **top-level context**, sau đó iframe đến RP: cần kiểm cookie trong third-party context có thực gửi hay không.
- Một **embed token/capability** do backend cấp sau authorization: giới hạn tenant, report ID, audience/origin khi cần, TTL, quyền read và khả năng thu hồi. Không dựa vào một ID dễ đoán hoặc URL có token tồn tại vô hạn.
- Một backend-to-backend integration trao đổi scoped token và cấp view session phía RP: tránh đặt client secret ở HTML hoặc trong `iframe src`.

Trong mọi mô hình, **backend của RP phải kiểm quyền trên report 42**; `Origin`, `Referer` và CSP không được dùng như cơ chế chứng minh principal duy nhất.

### 6.4. Token trong iframe URL có thể bị lộ

~~~html
<!-- Kém an toàn nếu token sống lâu/đọc quá rộng -->
<iframe src="https://app.example.com/embed/report/42?token=LONG_LIVED_SECRET">
</iframe>
~~~

Các token trong URL có thể xuất hiện tại browser history, proxy logs, server logs, analytics, screenshots và tickets. Nếu phải dùng capability trong URL vì hạn chế giao tiếp khác origin, nó nên **ngắn hạn, tối thiểu quyền, ràng buộc đúng resource/version, HTTPS, không cache**, và được quản lý/thu hồi có chủ đích. Có thể dùng bước trao đổi server-side/token exchange cho một cookie scoped khi browser context cho phép; không giả định third-party cookie luôn hoạt động.

### 6.5. Chống cache sai người dùng/tenant

Trang embed có thể hiển thị dữ liệu nhạy cảm. Mặc định `Cache-Control: no-store` hữu ích khi quyền truy cập thay đổi thường xuyên. Nếu dùng CDN/edge cache, phải phân biệt cache key/authorization đúng theo principal/tenant và tránh public caching khiến user khác thấy report.

### 6.6. Chỉ truyền dữ liệu tối thiểu sang parent

Nếu partner cần biết chiều cao iframe để resize, có thể dùng postMessage gửi **chiều cao** hoặc trạng thái vô hại. Không gửi toàn bộ JSON báo cáo, CSRF token, session ID hoặc access token sang parent nếu hợp đồng không yêu cầu và chưa có quyền dữ liệu riêng.

Một parent được phép frame không đương nhiên được cấp quyền đọc toàn bộ nội dung iframe qua JavaScript.

## 7. Iframe sandbox, allow và referrerpolicy

### 7.1. Sandbox hạn chế quyền của content

Ví dụ parent nhúng một widget chỉ cần hiển thị và giao tiếp qua message:

~~~html
<iframe
  id="partnerWidget"
  src="https://widget.vendor.example/panel"
  title="Bảng điều khiển đối tác"
  sandbox="allow-scripts"
  referrerpolicy="no-referrer"
  loading="lazy">
</iframe>
~~~

Khi bật `sandbox`, browser áp các hạn chế lên browsing context con. Chỉ thêm những `allow-*` token **được nghiệp vụ chứng minh cần thiết**. `sandbox="allow-scripts"` cho script chạy nhưng không tự cấp same-origin access; sandbox có thể tạo **opaque origin**, ảnh hưởng cookies/storage/postMessage origin behavior theo token được cấp.

### 7.2. Nguy hiểm của allow-scripts + allow-same-origin

Nếu iframe chứa **nội dung không tin cậy nhưng cùng origin với parent**, việc kết hợp:

~~~html
<!-- Tránh áp cho nội dung same-origin không tin cậy -->
<iframe
  src="/untrusted-page"
  sandbox="allow-scripts allow-same-origin">
</iframe>
~~~

có thể làm sandbox kém hiệu lực: script same-origin trong iframe có thể có khả năng thay đổi thuộc tính sandbox của element cha rồi điều hướng/reload trong một số hoàn cảnh. **Không dùng tổ hợp này như ranh giới cô lập tin cậy** cho HTML user-generated cùng RP origin. Tách nội dung không tin cậy sang **origin chuyên biệt** và hạn chế quyền ở server.

Với iframe cross-origin của vendor, cho cả `allow-scripts` và `allow-same-origin` không tự biến nó thành same-origin với parent, nhưng vẫn cấp nhiều quyền cho vendor origin. Chỉ bật nếu thật sự cần cookie/storage/functionality và đã đánh giá provider.

### 7.3. Những sandbox tokens cần đánh giá

| Token/thuộc tính | Mở quyền gì? | Điều kiện cân nhắc |
|---|---|---|
| `sandbox` không token | Hạn chế tối đa nhiều khả năng | Widget tĩnh, không cần script/form/navigation |
| `allow-scripts` | Cho chạy script trong child | Widget cần tương tác, vẫn giới hạn origin |
| `allow-forms` | Cho form submission từ child | Payment/login flows cần submit; kiểm CSRF bên nhận |
| `allow-same-origin` | Giữ origin thông thường thay opaque origin | Chỉ khi cần storage/cookies và content đủ tin cậy |
| `allow-popups` | Cho mở popup | Payment/OAuth UI cần popup, vẫn có popup policies |
| `allow-popups-to-escape-sandbox` | Popup mới không kế thừa sandbox restrictions | Có thể cần external login; cân nhắc rủi ro |
| `allow-top-navigation-by-user-activation` | Child có thể điều hướng top page khi user kích hoạt | Chỉ khi UX cần và child đáng tin |
| `allow-downloads` | Cho download từ sandboxed frame | Chỉ nếu chức năng thực sự cần |
| `allow="camera; microphone"` | Permissions Policy ủy quyền một số tính năng | Chỉ origin/provider cụ thể, tối thiểu quyền |

Không phải token nào cũng được mọi browser hỗ trợ giống nhau. `allow` của iframe và response `Permissions-Policy` **phối hợp**, không tự cấp quyền nếu top-level policy hoặc browser/user permission chặn.

### 7.4. Iframe title và accessibility cũng liên quan vận hành

Cung cấp `title` có ý nghĩa, không tạo overlay vô hình khiến user không biết họ đang thao tác với nguồn nào; hiển thị nhãn nhà cung cấp khi phù hợp. `loading="lazy"` giảm chi phí tải nhưng không là security boundary.

### 7.5. Referrer-Policy hạn chế dữ liệu URL đi sang vendor

Khi trang RP có query chứa campaign, document ID hoặc token tạm, việc tải iframe/script/image từ third party có thể phát `Referer` theo policy. `referrerpolicy="no-referrer"` trên iframe hoặc response `Referrer-Policy: strict-origin-when-cross-origin` / `no-referrer` có thể giảm rò URL.

**Không coi Referrer-Policy là cách bảo vệ secret duy nhất**: tránh đặt access/session/refresh token dài hạn trong URL ngay từ đầu.

## 8. postMessage: kênh liên lạc có kiểm tra hai chiều

### 8.1. Vì sao cần postMessage?

SOP ngăn parent trực tiếp đọc `iframe.contentWindow.document` của trang khác origin. Nhưng đôi khi parent chỉ cần hỏi widget “đã sẵn sàng chưa?” hoặc nhận chiều cao để resize. `window.postMessage` hỗ trợ trao đổi thông điệp có kiểm soát giữa browsing contexts.

**Rủi ro:** Bất kỳ window được phép liên lạc theo cơ chế browser đều có thể cố gửi message. Nếu handler tin mọi `event.data` hoặc dùng `event.origin.includes("vendor.example")`, attacker có thể giả source hoặc dùng domain nhìn giống.

### 8.2. Parent gửi message với targetOrigin chính xác

~~~html
<iframe
  id="reportWidget"
  src="https://widget.vendor.example/report"
  title="Báo cáo nhà cung cấp">
</iframe>
~~~

~~~javascript
const childOrigin = "https://widget.vendor.example";
const frame = document.getElementById("reportWidget");
const requestId = crypto.randomUUID();

frame.addEventListener("load", () => {
  frame.contentWindow?.postMessage({
    version: 1,
    type: "INIT",
    requestId
  }, childOrigin);  // Không dùng "*" khi biết origin đích.
});

window.addEventListener("message", (event) => {
  if (event.origin !== childOrigin) return;
  if (event.source !== frame.contentWindow) return;

  const msg = event.data;
  if (!msg || typeof msg !== "object") return;
  if (msg.version !== 1 || msg.type !== "RESIZE") return;
  if (msg.requestId !== requestId) return;

  // Giới hạn shape/range: không nhét vào innerHTML.
  if (!Number.isSafeInteger(msg.height)) return;
  if (msg.height < 120 || msg.height > 1200) return;

  frame.style.height = `${msg.height}px`;
});
~~~

Ví dụ này chỉ xử lý **resize**, không nhận HTML, JavaScript, token hoặc URL arbitrary. `event.origin` phải so **bằng tuyệt đối** với origin allowlist (bao gồm scheme/host/port); `event.source` phải khớp đúng cửa sổ iframe hiện hành. `requestId` là correlation của một lần init, không nên coi nó là authorization secret.

### 8.3. Child xác minh origin của parent

Code phía widget (do vendor quản lý, mô tả hợp đồng phía child):

~~~javascript
const allowedParent = "https://app.example.com";

window.addEventListener("message", (event) => {
  if (event.origin !== allowedParent) return;
  if (event.source !== window.parent) return;

  const msg = event.data;
  if (!msg || typeof msg !== "object") return;
  if (msg.version !== 1 || msg.type !== "INIT") return;
  if (typeof msg.requestId !== "string") return;
  if (msg.requestId.length > 128) return;

  const boundedHeight = Math.min(
    1200, Math.max(120, document.documentElement.scrollHeight)
  );

  window.parent.postMessage({
    version: 1,
    type: "RESIZE",
    requestId: msg.requestId,
    height: boundedHeight
  }, allowedParent);
});
~~~

Cần nhớ: `event.source` chỉ liên kết window, **không chứng minh user đã đăng nhập** hoặc được cấp quyền trên báo cáo. Các lệnh thay đổi dữ liệu phải đi qua backend authorization/CSRF hoặc capability protocol riêng.

### 8.4. Checklist message handler

- Xác định rõ danh sách origins theo **scheme, hostname, port**; không dùng substring, suffix đơn giản hoặc `*`.
- Khi nhận, kiểm cả `event.origin` và `event.source` đúng frame/popup đang được mong đợi.
- Message là **untrusted input**: validate type/version/schema/length, allowlist action, tránh prototype-pollution-prone merges.
- Kiểm correlation/nonce/transaction ID khi hợp đồng nhiều phiên/requests; có timeout/cleanup listeners.
- Không dùng `innerHTML`, `eval` hoặc tạo script/URL từ message ngoài kiểm soát.
- Không post session ID, CSRF token, access/refresh token hay báo cáo riêng tư trừ khi có threat model và kênh được authorize.
- Nếu sandbox tạo opaque origin, `event.origin` có thể là `"null"`; đừng mặc định tin tất cả origin `"null"`. Thiết kế giao thức với origin isolation rõ, có thể cần host widget không sandbox opaque hoặc cơ chế capability đã giới hạn.
- Nếu frame điều hướng sang origin khác, gửi lại chỉ khi origin/session đã được xác minh; không giữ tham chiếu window rồi tin luôn nội dung mới.
- Listener phải được tháo khi component unmount hoặc popup đóng để tránh stale handlers.

## 9. SameSite và cookie trong trang nhúng

### 9.1. Cross-site iframe không tương đương top-level navigation

Giả định browser đang xem trang `https://partner.example.net`, trong đó có iframe `https://app.example.com/embed/report/42`. Từ góc nhìn cookie của RP, request iframe có ngữ cảnh **cross-site embedded**, không phải top-level navigation.

| Cookie RP | Cross-site iframe request | Cross-site top-level GET navigation | Nhận xét |
|---|---|---|---|
| `SameSite=Strict` | Thường không gửi | Thường không gửi khi đi từ site khác | Có thể làm flow iframe/deep-link mất session |
| `SameSite=Lax` | Thường không gửi | Có thể gửi theo safe GET | Hợp nhiều OAuth callback GET, không hợp iframe cookie |
| `SameSite=None; Secure` | Có thể gửi nếu browser cho phép | Có thể gửi | Không vượt được mọi third-party cookie blocks |
| Cookie `Partitioned` theo CHIPS khi được hỗ trợ | Có thể có cookie riêng theo top-level site/partition | Phụ thuộc thiết kế partition | Không tương đương SSO session chung nhiều site |

Không được nói “đã bật `SameSite=None` thì iframe chắc chắn đăng nhập được”. Browser có thể chặn hoặc partition third-party cookies tùy cấu hình/privacy model.

### 9.2. Cookie attribute không phải authorization

Một cookie có `SameSite=None; Secure; HttpOnly` chỉ quyết định **khi nào browser có thể gửi nó**. Backend vẫn phải xác thực session và kiểm user có quyền đọc report trong iframe. Khi cookie RP không được gửi, **không** bỏ authentication để “cho widget chạy”.

### 9.3. Third-party cookie partitioning và CHIPS

Cookie có thuộc tính `Partitioned` trong những browser hỗ trợ có thể được lưu theo **top-level site partition**, giúp một service iframe giữ trạng thái riêng trong các trang top-level khác nhau. Tuy nhiên:

- Hỗ trợ và hành vi tùy browser/version.
- Cookie partition của parent A không đương nhiên chia sẻ với parent B.
- Không được coi partitioned cookie là phiên SSO toàn cục.
- `Secure` là điều kiện quan trọng đối với `Partitioned` theo hỗ trợ browser.
- Cần kiểm CSRF/authorization như bình thường đối với request nhận cookie.
- Nếu ứng dụng dùng Spring Session, phải kiểm khả năng serializer/set-cookie hỗ trợ thuộc tính cần thiết trên version thật.

### 9.4. Storage Access API không phải phím tắt bỏ bảo mật

Một số browser cung cấp **Storage Access API** để embedded content xin quyền truy cập cookie/storage chưa partition trong điều kiện hạn chế (thường có yêu cầu tương tác người dùng và chính sách browser). Nó không bảo đảm luôn được chấp nhận và không bỏ qua SameSite/authorization.

Không nên xây một hệ thống “chỉ login được khi third-party cookies luôn mở” mà không có fallback top-level navigation hoặc mô hình embed token/server-side authorization thích hợp.

### 9.5. OAuth/OIDC và silent SSO trong iframe

IdP session cookie có thể hoạt động khi IdP là **top-level** site, nhưng bị chặn trong **hidden iframe silent login**. Đây không phải bằng chứng `state`/`nonce`/PKCE sai. Đừng sửa bằng cách bỏ protocol validation; cân nhắc **Authorization Code + PKCE qua top-level redirect**, BFF/session design, hoặc SDK/IdP flow được hỗ trợ theo privacy constraints.

## 10. Popup, window.opener và reverse tabnabbing

### 10.1. Popup là browsing context mới, không tự được tin cậy

Khi một trang dùng `window.open` hoặc `<a target="_blank">`, trình duyệt có thể tạo cửa sổ/tab mới. Nếu trang mới có tham chiếu `window.opener`, nó có thể có một số khả năng tương tác với opener ngay cả khi **SOP ngăn đọc DOM cross-origin**. Một rủi ro cổ điển là **reverse tabnabbing**: trang không tin cậy khiến opener chuyển sang trang giả mạo.

Với đường dẫn bên ngoài chỉ để người dùng xem:

~~~html
<a href="https://help.vendor.example"
   target="_blank"
   rel="noopener noreferrer">
  Mở hướng dẫn nhà cung cấp
</a>
~~~

`noopener` cắt quan hệ opener; `noreferrer` còn hạn chế Referer và thường ngụ ý noopener. Các browser hiện đại có thể mặc định implicit noopener cho một số `target="_blank"` links, nhưng khai báo rõ giúp mã dễ review.

JavaScript:

~~~javascript
// Popup bên ngoài không cần nói chuyện với parent:
window.open(
  "https://help.vendor.example",
  "_blank",
  "noopener,noreferrer"
);
~~~

Nếu popup được mở từ user interaction hợp lệ, browser có khả năng cho phép; popup mở tự động ngoài user activation có thể bị chặn.

### 10.2. Vì sao “thêm noopener cho mọi popup” có thể phá SSO?

Một số luồng OAuth/OIDC popup dùng:

~~~text
Parent RP/SPA
   -> window.open(authorization URL)
   -> IdP login trong popup
   -> popup callback về RP origin
   -> callback gửi postMessage thành công cho parent
~~~

Muốn popup callback gửi `window.opener.postMessage(...)`, **opener phải tồn tại**. Nếu dùng `noopener`, `window.opener` thường là `null`, kênh này không còn. Nhưng bỏ noopener vô điều kiện lại làm tăng bề mặt opener exposure trong lúc popup đang ở IdP/các origin trung gian.

**Lựa chọn an toàn hơn:** ưu tiên **top-level redirect** khi nghiệp vụ cho phép; nếu popup là bắt buộc, thiết kế handshake được kiểm soát, thông điệp tối thiểu, giới hạn origin và kiểm COOP/browser behavior. Đừng dùng popup như cách bỏ state/nonce/PKCE của OAuth.

### 10.3. COOP có thể thay đổi window.opener

Response header **Cross-Origin-Opener-Policy (COOP)** có thể đưa top-level documents vào những browsing context groups tách biệt.

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

COOP `same-origin` tăng cường isolation giữa documents khác origin nhưng có thể làm **mất/bị tách tham chiếu opener** khi popup điều hướng qua IdP. Chọn policy nào còn phải xét version/browser, COOP của cả opener và popup, và nhu cầu cross-origin isolation của trang.

Có các giá trị như `same-origin-allow-popups` được thiết kế cho một số tương tác popup, nhưng **không nên mặc định nó luôn phục hồi kênh OAuth popup trên mọi browser/provider**. Test vòng đời: RP mở popup → IdP → RP callback → message → đóng popup, cùng chính sách thật của các origins.

### 10.4. Popup không cấp quyền đọc dữ liệu qua origin khác

Giả sử parent đang ở `app.example.com`, popup đang ở `login.identity.example`. Parent không được đọc DOM hoặc cookies của IdP chỉ vì parent mở cửa sổ. Nếu code dùng vòng lặp đọc `popup.location.href`, cross-origin access có thể ném `SecurityError`; không dùng exception swallowing rồi bỏ validation để né.

Chỉ khi popup **điều hướng trở về callback thuộc RP origin** mới có thể thực thi trang callback cùng origin theo SOP, và callback đó vẫn cần server-side OAuth state/nonce/PKCE checks trước khi tuyên bố login thành công.

## 11. OAuth/OIDC qua popup: phân chia quyền giữa parent, callback và IdP

### 11.1. Luồng bảo mật khuyến nghị

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant P as Parent RP page
    participant W as Login popup
    participant IDP as OIDC provider
    participant BFF as Spring OAuth2 Login RP

    U->>P: Bấm Login
    P->>W: window.open(RP start-login URL)
    W->>BFF: GET /oauth2/authorization/corporate
    BFF->>BFF: Tạo state, nonce, PKCE nếu cấu hình
    BFF-->>W: 302 IdP authorize URL
    W->>IDP: Login/MFA/consent
    IDP-->>W: Redirect code+state về RP callback
    W->>BFF: GET /login/oauth2/code/corporate?code=...&state=...
    BFF->>BFF: So expected request, code exchange, validate ID token
    BFF-->>W: Set/update RP session; redirect đến RP popup-complete page
    W->>P: postMessage LOGIN_COMPLETE, không gửi raw token
    P->>BFF: GET /api/me để xác minh session mới
    BFF-->>P: User summary theo authz
~~~

**Điểm chủ chốt:** Popup callback **không được tự quyết định login pass chỉ vì có code query**; Spring/BFF kiểm state, PKCE, nonce, issuer/audience/chữ ký trước. Parent chỉ nhận một **notification** và phải truy vấn lại server để xác minh session hiện hành.

### 11.2. Trang callback hoàn tất gửi thông báo tối thiểu

Giả định server đã hoàn tất token validation, thiết lập session và điều hướng đến **trang cùng origin** như `/auth/popup-complete`. JavaScript trên trang này có thể:

~~~javascript
// Chỉ chạy trên https://app.example.com/auth/popup-complete,
// sau khi RP server đã xác thực/commit session.
const parentOrigin = "https://app.example.com";

if (window.opener && !window.opener.closed) {
  window.opener.postMessage({
    type: "LOGIN_COMPLETE",
    version: 1
  }, parentOrigin);
}

window.close();
~~~

Không gửi `code`, ID token, access token, refresh token, CSRF token hay session ID sang parent qua message.

Parent:

~~~javascript
let loginPopup = null;

document.getElementById("loginButton")
  .addEventListener("click", () => {
    loginPopup = window.open(
      "/oauth2/authorization/corporate",
      "corporate-login",
      "width=520,height=660"
    );
    if (!loginPopup) {
      // Popup bị chặn: fallback top-level redirect theo UX.
      window.location.assign("/oauth2/authorization/corporate");
    }
  });

window.addEventListener("message", async (event) => {
  if (event.origin !== window.location.origin) return;
  if (event.source !== loginPopup) return;

  const msg = event.data;
  if (!msg || msg.version !== 1 ||
      msg.type !== "LOGIN_COMPLETE") return;

  // Chỉ coi message là tín hiệu; backend mới quyết định auth.
  const response = await fetch("/api/me", {
    credentials: "same-origin",
    cache: "no-store"
  });
  if (response.ok) {
    // Cập nhật UI dựa trên JSON đã qua authorization.
    window.location.reload();
  }
});
~~~

Đây là **mẫu minh họa**, không phải OAuth popup adapter hoàn chỉnh. Khi production cần bổ sung **transaction correlation** do parent giữ, cleanup listener/reference khi hủy, popup close/timeout, xử lý request session không đồng bộ và kiểm COOP có cắt opener không.

### 11.3. Message từ chính origin vẫn phải kiểm transaction

Kiểm `event.origin === location.origin` giúp ngăn source từ site ngoài, nhưng nếu một tab/cửa sổ cùng origin khác gửi thông điệp, chỉ origin chưa đủ. Kiểm `event.source === loginPopup` và một **transaction ID/session-bound state** theo hợp đồng nếu có nhiều login attempts hoặc nhiều tab.

Không dùng “message đã báo success” làm bằng chứng ứng dụng được phép thao tác; parent phải gọi `/api/me` hoặc một endpoint status đã authenticated, vì message có thể đến trễ hoặc session đã thay đổi.

### 11.4. Browser session cookie trong popup

Popup là top-level browsing context khi login tại IdP, nên cookie IdP có thể có hành vi khác so với **iframe silent SSO**. Sau callback về RP, cookie của RP phải có Domain/Path/Secure/SameSite phù hợp; session persistence và rotation cần test.

Nếu popup và parent dùng cùng browser cookie jar, response sau callback có thể ảnh hưởng session của parent. Nhưng đừng giả định mọi browser profile/partition mode lưu cookie giống nhau; cần browser E2E.

### 11.5. Popup blocker và fallback

Thường `window.open` phải được gọi trực tiếp trong handler user gesture; nếu chờ một `await fetch(...)` trước khi mở cửa sổ, popup có thể bị chặn. Có thể mở một cửa sổ chờ trong user activation rồi điều hướng sau, nhưng không biến một URL do attacker cung cấp thành popup destination.

Khi popup bị chặn hoặc COOP tách opener, có **fallback top-level redirect**; đừng cố bỏ CSP/COOP rộng rãi mà chưa phân tích ranh giới.

## 12. Tài nguyên bên thứ ba: script, style, font, image và WebSocket

### 12.1. Ma trận quyền theo loại tài nguyên

| Resource | CSP directive thường liên quan | Rủi ro quan trọng |
|---|---|---|
| External `<script src>` | `script-src`/`script-src-elem` | Chạy với quyền origin RP; supply-chain/XSS |
| External stylesheet | `style-src`/`style-src-elem` | CSS injection/UI manipulation, asset requests |
| External font | `font-src` | Tải nguồn không mong muốn/availability/privacy |
| External image | `img-src` | Tracking pixels, Referer/URL leakage |
| AJAX/fetch/WebSocket | `connect-src` | Exfiltration tới endpoint attacker, CORS khi đọc |
| External iframe | `frame-src` | UI deception, cookies, sandbox/message |
| External form destination | `form-action` | Gửi form/PII tới site không được duyệt |
| Worker/service worker | `worker-src`, scope/origin policy | Script worker độc hại, long-lived behavior |
| Plugin/object content | `object-src` | Legacy active content; nên `'none'` |
| Base URL modification | `base-uri` | Thay ý nghĩa relative URLs; thường `'self'` hoặc `'none'` |

**Một `script-src` allowlist chứa origin vendor là cấp phép cho code vendor chạy trong origin RP**, không chỉ cấp quyền tải một file tĩnh.

### 12.2. JavaScript bên thứ ba có thể làm gì?

Script tải qua:

~~~html
<script src="https://cdn.vendor.example/analytics.js" defer></script>
~~~

sau khi được trình duyệt cho phép, có thể:

- Đọc/ghi DOM mà trang RP có quyền truy cập;
- Đọc CSRF token trong HTML/JS state hoặc dữ liệu hiển thị;
- Gửi request same-origin bằng session cookie (dù JS không đọc được `HttpOnly` cookie);
- Đưa dữ liệu ra domain mà CSP `connect-src` hoặc resource directives cho phép;
- Tạo iframe/popup, thay link hoặc UI nếu CSP/Trusted Types/DOM policy cho phép;
- Tác động tracking và quyền riêng tư của user.

**Do vậy, không coi external script là an toàn chỉ vì nó tới từ CDN có HTTPS.** HTTPS bảo vệ đường truyền và xác thực host, không bảo đảm code của vendor/phiên bản tương lai không bị thay đổi.

### 12.3. Tối thiểu hóa vendor permissions

- Chỉ tích hợp vendors có nhu cầu nghiệp vụ và quy trình review.
- Ưu tiên **iframe cross-origin** thay vì script chạy trong RP khi chức năng có thể đóng gói.
- Khi phải dùng script, pin version cố định, dùng CSP/SRI khi tương thích, không cho auto-upgrade tùy ý.
- Không cho vendor script chạm token/session/authentication objects nếu tránh được.
- Giới hạn outbound connections `connect-src`, forms `form-action` và images `img-src` phù hợp.
- Có kế hoạch vô hiệu hóa một vendor nhanh chóng (feature flag, emergency CSP policy, CDN fallback).
- Theo dõi CSP violation reports, vendor updates, console errors và availability, không log PII vào report endpoint.

### 12.4. External image không đồng nghĩa đơn giản “chỉ là ảnh”

Ảnh có thể dùng làm tracking pixel và request chứa `Referer`. SVG/HTML không tin cậy được phục vụ cùng RP origin có thể tạo active content nếu bị render sai ngữ cảnh/headers; không phục vụ user uploads như HTML/SVG inline cùng app origin tùy tiện.

`X-Content-Type-Options: nosniff`, đúng `Content-Type` và `Content-Disposition` là defense-in-depth, nhưng không thay content validation/origin isolation.

## 13. CSP cho trang có tài nguyên bên thứ ba

### 13.1. Bắt đầu bằng inventory rồi viết policy

Ví dụ ứng dụng thực sự dùng:

- Script first-party từ `'self'`;
- Một widget iframe từ `https://widget.vendor.example`;
- Ảnh từ `'self'` và CDN ảnh được duyệt;
- API first-party và một analytics endpoint;
- Không dùng objects/plugins;
- Không submit forms ra ngoài.

Policy **minh họa**:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://images.vendor.example; font-src 'self'; connect-src 'self' https://metrics.vendor.example; frame-src https://widget.vendor.example; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'
~~~

Đây là CSP dành cho **trang RP parent**, không tự cho phép widget nhúng RP. Để **partner nhúng route /embed/**, cần CSP khác trên document /embed/** với `frame-ancestors` allowlist riêng.

### 13.2. CSP allowlist rộng có thể che giấu lỗ hổng

**Không nên:**

~~~http
Content-Security-Policy: default-src * 'unsafe-inline' 'unsafe-eval'; frame-src *; connect-src *
~~~

Policy gần như mất khả năng kiểm nguồn/tác dụng chống nhiều dạng XSS/exfiltration. `'unsafe-inline'` cho scripts tùy ý trong ngữ cảnh CSP phù hợp và `'unsafe-eval'` mở những eval-like operations nguy hiểm.

Một CSP bảo vệ tốt phải tương thích thực tế với frontend build và được test trên browser, không chỉ có một header “trông đã bật”.

### 13.3. Nonce và hash cho inline scripts

Khi ứng dụng cần một inline script được kiểm soát, có thể tạo **nonce mới cho từng response** bằng nguồn ngẫu nhiên tốt rồi truyền cùng giá trị vào HTTP CSP header và thẻ script:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-FRESH_RANDOM_VALUE'; object-src 'none'; base-uri 'self'
~~~

~~~html
<script nonce="FRESH_RANDOM_VALUE">
  // Mã đã qua review; không đưa input user chưa escape vào đây.
</script>
~~~

**Hai chuỗi ở ví dụ phải được server sinh động cho từng response, không hardcode** và không dùng một nonce cố định trong `application.yml`. Cần CSP templating/response header integration tương ứng Servlet hoặc Reactive; cache HTML phải được thiết kế để nonce header và body không bị lệch.

### 13.4. Hash chính xác khác nonce động

Một inline script bất biến có thể dùng CSP `'sha256-...'` tương ứng bytes chính xác. SRI dùng hash cho **external subresource bytes**; CSP hash cho inline script/style có semantics khác. Không đưa một giá trị hash minh họa vào production rồi bỏ qua mismatch.

### 13.5. Chạy ở chế độ báo cáo trước khi enforce

Trong giai đoạn chuyển đổi, có thể dùng:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; frame-src https://widget.vendor.example
~~~

Report-Only hữu ích để quan sát vi phạm mà không chặn tất cả tính năng ngay. Nhưng **không xem Report-Only là enforcement**. Khi policy ổn, chuyển sang `Content-Security-Policy` thật, áp chính sách frame-ancestors trên responses cần bảo vệ và tiếp tục giám sát.

CSP reports có thể chứa URLs/source snippets có thông tin nhạy cảm; collection endpoint và retention phải bảo vệ dữ liệu, tránh gửi báo cáo bảo mật của user tới vendor không được phê duyệt.

## 14. Subresource Integrity (SRI), version pinning và giới hạn

### 14.1. SRI kiểm tra byte của một external asset

Ví dụ một script version-pinned:

~~~html
<script
  src="https://cdn.vendor.example/v3/widget.min.js"
  integrity="sha384-BASE64_DIGEST_OF_THE_ACTUAL_FILE"
  crossorigin="anonymous"
  defer>
</script>
~~~

**`BASE64_DIGEST_OF_THE_ACTUAL_FILE` chỉ là ký hiệu minh họa**; phải thay bằng digest tính từ bytes asset thực được duyệt. Nếu CDN thay đổi bytes, browser có thể từ chối tải khi hash không khớp.

Với resource cross-origin sử dụng SRI, cần xét **CORS-enabled fetch**, ví dụ `crossorigin="anonymous"` và phía CDN trả `Access-Control-Allow-Origin` phù hợp. Nếu không, browser có thể chặn vì không có điều kiện xác minh/integrity phù hợp.

### 14.2. Cách sinh digest có thể tái lập

Ví dụ ở môi trường build có OpenSSL:

~~~bash
openssl dgst -sha384 -binary widget.min.js | openssl base64 -A
~~~

Sau đó ghép prefix `sha384-` với Base64 output, lưu/khóa version asset qua pipeline và verify trong CI. Không tải một file thay đổi tự động ở URL không version rồi coi SRI pin “tự cập nhật”.

### 14.3. SRI chưa giải quyết toàn bộ supply chain

- SRI bảo đảm file khớp **hash đã chấp nhận**, không bảo đảm nội dung của file đó không độc hại.
- Script đã được pin vẫn có thể tạo dynamic import/fetch/subresource requests; cần CSP/network controls và audit.
- Third-party script có thể đọc/sửa DOM/call APIs theo quyền RP. SRI **không sandbox** script.
- Khi vendor release phiên bản mới, phải review/recompute digest, không bỏ SRI để tránh failure.
- Một iframe là mô hình isolation khác; SRI của script tag không tự áp cho mọi document iframe/redirect.
- Nếu vendor inject script qua tag manager, phải review cả **tag manager và các tags/scripts được phép tải động**; allowlist một manager có thể mở cả chuỗi scripts khác.

### 14.4. Nên chuyển script vendor thành iframe khi nào?

Nếu widget chỉ cần hiển thị một biểu đồ/biểu mẫu riêng và có API postMessage tối thiểu, iframe cross-origin với `frame-src`/sandbox/cookie policy phù hợp thường giảm việc code vendor chạy trong RP origin. Tuy nhiên iframe cũng có chi phí về UX, tracking, accessibility, CSP, cookies/3PC và permission prompts. Đây là **tradeoff thiết kế**, không phải thay script bằng iframe là tự nhiên an toàn trong mọi trường hợp.

## 15. CORS, CORP, COEP và COOP: bốn chính sách khác nhau

### 15.1. Ma trận ranh giới

| Cơ chế | Được đặt ở đâu? | Mục tiêu chính | Không thay thế |
|---|---|---|---|
| **CORS** | Resource/API response, preflight | Cho phép JavaScript từ origin khác đọc response theo điều kiện | Authentication, CSRF, `frame-ancestors` |
| **CORP** (`Cross-Origin-Resource-Policy`) | Resource response | Giới hạn một số **no-cors** cross-origin/cross-site resource loads | CORS authorization, object-level ACL |
| **COEP** (`Cross-Origin-Embedder-Policy`) | Document response | Buộc embedded cross-origin resources opt-in theo CORS/CORP hoặc dùng chế độ được hỗ trợ | CSP, CSRF, login/session |
| **COOP** (`Cross-Origin-Opener-Policy`) | Document response | Kiểm browsing context group/opener isolation | OAuth state, postMessage validation |
| **CSP `frame-src`** | Document parent response | Kiểm nguồn iframe parent tải | CORP/COEP, child frame-ancestors |
| **CSP `frame-ancestors`** | Document child response | Kiểm origins được nhúng child | Authentication hoặc widget script policy |

Một response có thể dùng nhiều cơ chế, nhưng phải biết **mỗi cơ chế hoạt động trên loại request nào**.

### 15.2. CORS là quyền đọc response của browser JS, không là quyền login

Ví dụ SPA tại `https://app.example.com` gọi:

~~~javascript
const result = await fetch("https://api.example.com/me", {
  credentials: "include"
});
~~~

API khác origin phải trả CORS policy phù hợp để JavaScript đọc response. Nếu cho credentialed request, không dùng wildcard `Access-Control-Allow-Origin: *` với `Access-Control-Allow-Credentials: true`; allowlist exact origin tin cậy, methods/headers/credentials đúng.

**CORS không ngăn mọi cross-origin request được gửi**: browser có thể gửi simple requests/form/navigation mà không cho script đọc response. Chính vì vậy CORS không thay CSRF khi API dùng session cookie.

### 15.3. CORP ngăn resource bị nhúng kiểu no-cors ngoài policy

Ví dụ ảnh/asset nội bộ chỉ dành cho cùng origin:

~~~http
Cross-Origin-Resource-Policy: same-origin
~~~

Một asset dùng nội bộ trên các subdomain cùng site có thể cân nhắc `same-site`; asset muốn dùng rộng có thể đặt `cross-origin` theo threat model. CORP không phải chữ ký quyền truy cập và không giải quyết rò dữ liệu nếu endpoint đã được cấu hình cho phép trả private content.

**Không nhầm CORP với CSP frame-ancestors**: một dùng để điều chỉnh cách resource được tải theo cross-origin embedding context, một dùng để kiểm **ai được phép frame document**.

### 15.4. COEP có thể chặn tài nguyên vendor không opt-in

~~~http
Cross-Origin-Embedder-Policy: require-corp
~~~

Đây là một cơ chế giúp cross-origin isolation, yêu cầu cross-origin subresources được cho phép theo CORS/CORP tương ứng. Nếu vendor script/image/iframe không hợp tác, chúng có thể không tải được.

Các dự án dùng tính năng như `SharedArrayBuffer` trong secure, cross-origin isolated context có thể cần COOP+COEP phù hợp. Nhưng **không bật COEP toàn app chỉ để tăng điểm “security headers”** khi ứng dụng có nhiều widgets/CDNs chưa sẵn sàng.

Một số browser hỗ trợ `credentialless` trong COEP với semantics riêng; không giả định nó cấp quyền truy cập cookie hoặc sửa đăng nhập iframe.

### 15.5. COOP và popup OAuth có tradeoff

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

có thể tách `window.opener` giữa tài liệu khác origin. Với popup SSO, popup đi qua IdP origin khác RP, nên kênh opener có thể bị gián đoạn. `same-origin-allow-popups` có thể phù hợp với một số luồng nhưng phải kiểm browser/provider; nó không phải “bật là OAuth popup chạy”.

Nếu cần **crossOriginIsolated** để sử dụng API đặc biệt, tách trang tính toán/worker sang origin/route có header phù hợp thay vì phá login flow của toàn bộ RP một cách vô ý.

### 15.6. Khi cần cross-origin isolation, test đầy đủ mọi asset

~~~text
Document RP:
  COOP: same-origin
  COEP: require-corp
Assets:
  script từ CDN: có CORS/opt-in đúng?
  image từ vendor: CORP/CORS?
  iframe partner: chính sách hai bên?
  popup OAuth: opener còn không?
  websocket: connect-src/authorization?
~~~

Nếu một asset bị chặn, dùng Network/Console và response headers để xác định COEP/CORP/CORS/CSP nào chặn; không mở `*` đồng loạt. Việc sửa cần phối hợp với vendor hoặc thay asset host, không giả định chỉ Spring Security filter có thể điều khiển response của CDN bên ngoài.

## 16. Spring Security Servlet: default deny và ngoại lệ nhúng theo route

### 16.1. Cấu hình hai SecurityFilterChain rõ ràng

Ví dụ Spring MVC/Servlet có:

- `/embed/**`: chỉ trang HTML read-only được đối tác `https://partner.example.net` nhúng; vẫn yêu cầu authentication và ACL nội bộ.
- Các route còn lại: không cho frame từ bất kỳ parent nào.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletEmbeddingSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain embeddedPage(HttpSecurity http)
            throws Exception {

        return http
            .securityMatcher("/embed/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .headers(headers -> headers
                // Chỉ route /embed/** không phát XFO DENY.
                // CSP frame-ancestors kiểm parent allowlist.
                .frameOptions(frame -> frame.disable())
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "frame-ancestors 'self' " +
                        "https://partner.example.net; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "form-action 'self'"
                    )
                )
            )
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserPages(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .headers(headers -> headers
                .frameOptions(frame -> frame.deny())
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "frame-ancestors 'none'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'"
                    )
                )
            )
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Các điều kiện để ví dụ có ý nghĩa:**

- Hai chains là **một phương án minh họa**, không gắn đồng thời với một bộ chains khác có matcher/order xung đột.
- Chỉ **chain đầu tiên** match một request được áp dụng. `/embed/**` phải được đặt cụ thể trước `anyRequest`.
- `frameOptions.disable()` ở embed chain chỉ loại **XFO writer trên route đó**, **không** có nghĩa vô hiệu hóa CSP hoặc Spring CSRF; CSP `frame-ancestors` ở đó là cơ chế giới hạn parent.
- Với browser cũ không hỗ trợ CSP `frame-ancestors`, route embed có thể thiếu XFO fallback tương đương. Cần xác định browser support contract, không “mở route nhúng” cho trình duyệt không được hỗ trợ.
- Authenticated mới chỉ kiểm user có phiên; controller/service còn phải kiểm `reportId` và tenant/ACL. Với cross-site iframe, cookie session Lax có thể **không được gửi** nên phải thiết kế phương thức auth phù hợp, không tắt authentication.
- Cấu hình CSP theo route có thể cần thêm nguồn assets/frames thực; đừng thêm wildcard chỉ vì giao diện đang thiếu một font.

### 16.2. Controller trả trang embed theo ID và ACL

~~~java
import java.security.Principal;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@Controller
class ReportEmbedController {

    private final ReportAccessService reports;

    ReportEmbedController(ReportAccessService reports) {
        this.reports = reports;
    }

    @GetMapping("/embed/report/{id}")
    String report(@PathVariable String id,
                  Principal principal,
                  Model model) {

        // Service phải xác minh principal có quyền read ID/tenant.
        ReportSummary safeSummary =
            reports.findAuthorizedSummary(principal, id);

        model.addAttribute("report", safeSummary);
        return "embed/report";
    }
}
~~~

`ReportAccessService` và `ReportSummary` là **thành phần ứng dụng phải triển khai**; controller minh họa không tự xác minh token/password/cookie và không chứng minh dữ liệu đã được escape an toàn.

Template phải escape dữ liệu đầu ra, không gắn raw HTML do user cung cấp bằng `th:utext` hoặc `innerHTML`. Nếu widget chỉ cần read-only, không render form xóa/sửa admin.

### 16.3. Khi không cần nhúng, giữ cấu hình đơn giản

Nếu toàn bộ ứng dụng không hỗ trợ framing, không cần hai chains. Có thể giữ Spring Security default XFO DENY và thêm CSP `frame-ancestors 'none'` ở HTML responses cần bảo vệ.

**Không mặc định sửa thành SAMEORIGIN** chỉ vì có một iframe tại parent RP trỏ tới widget vendor **khác origin**. Khi RP là parent, vấn đề thường nằm ở `frame-src` của RP và `frame-ancestors` của widget vendor, không phải XFO của RP.

### 16.4. CORS không được mở tự động khi cho phép frame

Việc cho `https://partner.example.net` trong `frame-ancestors` **không tự cấp** quyền `Access-Control-Allow-Origin` để partner JavaScript đọc `/api/reports/42`. Nếu app cũng cần API cross-origin, thiết kế CORS allowlist, authentication, CSRF/credential model và object-level ACL **riêng biệt**.

### 16.5. XFO/CSP có thể bị CDN hoặc proxy thay

Spring có thể phát CSP đúng nhưng Nginx/CDN thêm `X-Frame-Options: DENY` trên mọi response; hoặc proxy strip CSP khiến route embed mở hơn dự kiến. Kiểm **HTTP response cuối cùng tại public URL**, không chỉ test controller bên trong Spring.

Khi một policy thay đổi, test cả `/account`, `/admin`, `/embed/report/42`, error responses và redirect/login pages, không chỉ happy path.

## 17. Spring WebFlux: SecurityWebFilterChain và framing policy

### 17.1. Reactive tương ứng

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
class ReactiveEmbeddingSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain embed(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/embed/**"))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .headers(headers -> headers
                .frameOptions(frame -> frame.disable())
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; " +
                    "frame-ancestors 'self' " +
                    "https://partner.example.net; " +
                    "object-src 'none'; " +
                    "base-uri 'self'"
                ))
            )
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain web(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/login", "/assets/**").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .headers(headers -> headers
                // Reactive default frame-options mode is DENY.
                .frameOptions(Customizer.withDefaults())
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; " +
                    "frame-ancestors 'none'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'"
                ))
            )
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Các method DSL/config có thể khác giữa các **Spring Security versions**; cần compile/test với version thật và xác minh header wire-level, đặc biệt việc tắt XFO trong route embed. Ý nghĩa bảo vệ là: reactive chain cho `/embed/**` riêng, browser pages còn lại cấm framing, CSRF tiếp tục bật khi dùng WebSession cookie.

### 17.2. WebSession và cross-site iframe

WebFlux dùng `WebSession`, có thể qua `CookieWebSessionIdResolver`/Spring Session. Cookie `SameSite=Lax` thông thường không đi trong cross-site iframe như khi top-level GET. Vì vậy một trang embed được CSP cho phép vẫn có thể redirect login hoặc bị 401.

Không chữa bằng:

~~~java
// Không tắt toàn bộ security cho route nhúng:
.authorizeExchange(auth -> auth.anyExchange().permitAll())
~~~

trừ khi sản phẩm **cố ý công khai nội dung không nhạy cảm** và đã đánh giá tương ứng. Trang private cần authentication mechanism được browser/hạ tầng hỗ trợ cùng ACL.

### 17.3. Reactive controller ví dụ

~~~java
import java.security.Principal;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.reactive.result.view.Rendering;

import reactor.core.publisher.Mono;

@Controller
class ReactiveReportEmbedController {

    private final ReactiveReportAccessService reports;

    ReactiveReportEmbedController(
            ReactiveReportAccessService reports) {
        this.reports = reports;
    }

    @GetMapping("/embed/report/{id}")
    Mono<Rendering> report(@PathVariable String id,
                           Mono<Principal> principal) {

        return principal
            .flatMap(user -> reports.findAuthorizedSummary(user, id))
            .map(summary -> Rendering.view("embed/report")
                .modelAttribute("report", summary)
                .build());
    }
}
~~~

`ReactiveReportAccessService` là service giả định **phải** xác thực user/tenant/report và trả publisher không blocking. Không tin chỉ `authenticated()` của route đã cấp quyền đọc report ID.

### 17.4. Không trộn Servlet và Reactive filter APIs

- Servlet dùng `HttpSecurity`, `SecurityFilterChain`, `CsrfFilter` và Servlet response headers.
- WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `CsrfWebFilter` và WebFilter/ServerWebExchange APIs.
- Không copy Servlet `OncePerRequestFilter` vào WebFlux để gắn CSP header; dùng `WebFilter` hoặc reactive response integration khi cần dynamic policy.
- Test trong `WebTestClient` chỉ xác minh server headers/auth, **không** chứng minh browser thực thi CSP/frame policy.

## 18. CSP theo route và dynamic nonce: tránh xung đột header

### 18.1. Static policy phù hợp khi không có inline script động

Các ví dụ `headers().contentSecurityPolicy(...policyDirectives(...))` ở trên dùng **chuỗi CSP tĩnh**. Chúng phù hợp khi JS/CSS được đóng gói thành assets được duyệt, hoặc policy không yêu cầu nonce khác nhau cho từng response.

### 18.2. Dynamic nonce không thể hardcode trong application.yml

Khi một HTML document cần inline scripts, CSP có thể dùng nonce ngẫu nhiên **mỗi response**:

~~~text
1. Server sinh nonce N bằng secure random cho HTML response này.
2. Server đưa CSP header:
   script-src 'self' 'nonce-N'; object-src 'none'; ...
3. HTML renderer gắn nonce=N cho đúng các inline scripts đã review.
4. HTML/CSP response header gửi cùng nhau, tránh cache lệch nonce.
5. Response sau sinh N mới, không reuse toàn phiên.
~~~

Với Spring Servlet, có thể tạo nonce trong filter/interceptor/templating layer và phát header tương ứng; với WebFlux, dùng WebFilter/ServerWebExchange và reactive view model. **Không phát hai CSP headers mâu thuẫn một cách vô tình** khi Spring Security header writer và filter custom cùng ghi response. Kết hợp directives theo thiết kế rõ, test browser thật.

### 18.3. CSP không thay output escaping và sanitization

Ngay cả khi có nonce, render raw attacker string vào script hoặc chèn trusted script cho một widget không tin cậy vẫn có thể gây XSS. Tiếp tục dùng contextual output encoding, input validation, tránh `innerHTML` nguy hiểm và đánh giá Trusted Types khi ứng dụng cần defense-in-depth DOM XSS.

### 18.4. CSP với nhiều origins phải được version-control

Không nối string từ `?partnerOrigin=...` vào `frame-ancestors` hoặc `frame-src` mà không validate. Nếu nhiều tenants/partners có origins khác nhau, policy phải đến từ **allowlist đã quản trị**, không phải request headers như `Origin` hoặc `Referer`.

Nếu allowlist thay theo tenant, test response CSP với nhiều tenants để không cho partner A nhúng báo cáo tenant B. **Framing allowlist không tự kiểm dữ liệu**, nên ACL vẫn là điều kiện tách biệt.

## 19. Tích hợp thanh toán, định danh, CAPTCHA và webhook

### 19.1. Hosted payment page và hosted fields

Một luồng thanh toán có thể dùng:

- **Top-level redirect** tới trang thanh toán được host bởi provider;
- **Iframe hosted fields** cho một số trường nhạy cảm;
- **JavaScript SDK** của provider nhúng trong app;
- **Webhook server-to-server** để thông báo trạng thái giao dịch.

Những phương án này có bề mặt bảo mật khác nhau. Nếu ứng dụng muốn giảm phạm vi xử lý dữ liệu thẻ thanh toán, mô hình hosted fields có thể giúp dữ liệu được nhập vào **iframe do provider sở hữu**, thay vì đi qua JavaScript/HTTP endpoint của RP. Tuy nhiên phải thực hiện theo **hợp đồng tích hợp và tiêu chuẩn thanh toán thực tế**; không tự khẳng định chỉ cần iframe là đạt mọi yêu cầu tuân thủ.

### 19.2. Payment iframe cần hai policy song song

Parent RP:

~~~http
Content-Security-Policy: frame-src 'self' https://checkout.payment.example; form-action 'self' https://checkout.payment.example; object-src 'none'
~~~

Provider child phải cho phép parent theo chính sách framing của provider, đồng thời child có session/credential/allow attributes phù hợp. Nếu dùng iframe sandbox, cần xem provider có cần `allow-forms`, `allow-scripts`, popup hoặc top-level navigation theo user activation hay không. **Không tắt sandbox hoặc CSP toàn app chỉ vì một chức năng checkout gặp lỗi.**

### 19.3. Payment success redirect không chứng minh giao dịch đã hoàn thành

Một URL như:

~~~text
GET /payments/return?order=123&status=success
~~~

do browser gọi không phải bằng chứng đáng tin rằng provider đã thu tiền. Client có thể tự chỉnh query hoặc nhấn back/reload. Server phải xác minh trạng thái qua API/provider signature/webhook có kiểm chứng và đối chiếu **order ID, amount, currency, merchant, version, idempotency**.

Tương tự với OAuth popup: `LOGIN_COMPLETE` trong postMessage chỉ là một **tín hiệu UI**, không phải bằng chứng authentication độc lập.

### 19.4. Webhook POST không phải browser POST dùng cookie

Ví dụ provider backend gọi:

~~~http
POST /integrations/payments/webhook HTTP/1.1
Host: app.example.com
Content-Type: application/json
X-Provider-Signature: SIGNATURE_OVER_RAW_BODY
X-Provider-Timestamp: 1800000000

{"eventId":"evt-123","type":"payment.succeeded","orderId":"123"}
~~~

Giá trị header là **hợp đồng giả định**, không phải chuẩn áp dụng cho mọi provider. Vì webhook không được browser gửi bằng ambient session cookie, có thể cân nhắc **miễn Spring CSRF chỉ trên đúng webhook path/method**.

Tuy nhiên không thể chỉ làm:

~~~java
.csrf(csrf -> csrf.ignoringRequestMatchers("/integrations/**"))
~~~

vì có thể vô tình miễn CSRF cho nhiều endpoints browser hoặc API khác. Mẫu matcher cần **hẹp**, và server phải dùng phương thức xác minh riêng của provider:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

// Chỉ một POST webhook có giao thức chữ ký riêng:
var paymentWebhook = new AntPathRequestMatcher(
    "/integrations/payments/webhook", "POST");

// Trích đoạn HttpSecurity:
// .csrf(csrf -> csrf.ignoringRequestMatchers(paymentWebhook))
~~~

**Chỉ dùng** khi đã triển khai xác minh signature/HMAC trên **raw request body**, timestamp tolerance, chống replay bằng event ID, verify provider identity/config và xử lý idempotent. Không tin chỉ IP allowlist, query `status=success`, hoặc một field do client gửi; hỗ trợ provider có thể còn yêu cầu mTLS/IP restrictions.

### 19.5. Đối chiếu ba loại callback

| Callback | Tới từ đâu? | Chống giả mạo bằng gì? | Điều cần tránh |
|---|---|---|---|
| OAuth/OIDC authorization callback | Browser navigation từ IdP | `state`, PKCE, OIDC nonce/token validation theo flow | Bỏ state để popup chạy |
| Payment browser return | Browser sau checkout | Không tin status query; server xác minh giao dịch | Cập nhật đơn hàng chỉ dựa vào query |
| Payment webhook | Provider backend → Spring API | HMAC/signature, timestamp, replay/idempotency, provider keys | Public POST không signature vì “đã miễn CSRF” |
| Browser business POST | Browser đã đăng nhập session | Spring CSRF token + authentication/authorization | Miễn CSRF toàn app vì có webhook |

### 19.6. CAPTCHA và widget định danh bên thứ ba

Một CAPTCHA script/iframe có thể gửi telemetry, load resource mới, cần CSP script/frame/connect allowlist. **CAPTCHA result token** do browser gửi cần **server-side verification** với provider; không được coi chỉ việc widget được render là bot đã bị chặn.

Nếu IdP cung cấp embedded login iframe, phải kiểm **IdP có cho phép framing không**, browser third-party cookie policy và yêu cầu chống phishing/clickjacking. Không cố vượt `frame-ancestors 'none'` hoặc XFO DENY của IdP bằng proxy HTML/strip header: điều đó phá mô hình tin cậy và có thể vi phạm hợp đồng.

## 20. Security headers và vị trí tạo response

### 20.1. Bảng ownership

| Response | Chủ thể phát header | Điều cần kiểm |
|---|---|---|
| HTML chính của RP | Spring MVC/WebFlux, CDN hoặc reverse proxy | CSP, frame-ancestors, XFO, HSTS, Referrer-Policy |
| HTML `/embed/report` của RP | Spring/edge route embed | CSP partner allowlist, bỏ XFO xung đột, authz và no-store |
| Iframe widget của vendor | **Vendor** | Vendor frame-ancestors/XFO, cookies, CSP, sandbox compatibility |
| JavaScript/CDN external asset | **CDN/vendor** | CORS cho SRI, Content-Type, cache/integrity |
| API JSON của RP | Spring API | CORS nếu JS cross-origin, authentication, CSRF, nosniff |
| OAuth popup callback/complete | Spring RP | Auth transaction validation, CSP, referrer, no-store, opener behavior |
| Payment webhook | Spring API | Signature/replay/idempotency, CSRF exception chỉ đúng endpoint |
| 403/404/413 do edge | Proxy/WAF | Giữ status, không che thành 200/HTML; header/CORS theo yêu cầu |
| Isolated untrusted content host | Content server/CDN | CSP, CORP/COEP theo threat model, không dùng app session cookies |

**Spring Security headers không tự đi theo response của CDN/vendor**. Nếu browser tải thẳng `https://widget.vendor.example`, bạn không thể “thêm `frame-ancestors` cho vendor” chỉ bằng cấu hình header writer ở RP.

### 20.2. X-Content-Type-Options và Content-Disposition

~~~http
X-Content-Type-Options: nosniff
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="report.pdf"
~~~

Khi download file không tin cậy, `attachment`, đúng Content-Type, `nosniff` và tách origin giúp giảm rủi ro browser tự thực thi nội dung. Đây không phải lý do bỏ validation/AV hay object-level ACL.

### 20.3. Referrer-Policy và Permissions-Policy

~~~http
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
~~~

Tùy app có thể cần policy khác, nhất là widget được phép camera/microphone/geolocation. Không cấp mọi permission cho tất cả origins chỉ để chữa lỗi một vendor; cân nhắc `iframe allow` cùng policy document và user permission.

`Referrer-Policy` giúp hạn chế URL/path/query được gửi khi tải resource bên thứ ba, nhưng không thay quản lý token/cookie/query data đúng từ đầu.

### 20.4. HSTS, cache và proxy

- `Strict-Transport-Security` thường ở public HTTPS response; cân nhắc `includeSubDomains`/preload chỉ khi toàn bộ hạ tầng đáp ứng.
- Trang embed riêng tư có thể dùng `Cache-Control: no-store` để tránh shared caching sai user/tenant.
- Nếu proxy strip CSP hoặc thêm XFO DENY ở mọi route, trang embed có thể hỏng dù Spring đúng; kiểm response wire-level từ **public domain**.
- Nếu proxy sai `X-Forwarded-Proto`/`Host`, OAuth popup callback có thể bị redirect sang host/scheme sai, cookie Secure/host-only không đi theo.

### 20.5. Fetch Metadata và CSRF policy có thể ảnh hưởng embed

Một filter kiểm `Sec-Fetch-Site` có thể chặn mọi cross-site request. Nhưng một iframe được cho phép của partner **chính là cross-site subdocument navigation**. Nếu sản phẩm chủ đích cho partner embed, chính sách Fetch Metadata cần có **ngoại lệ có chủ đích cho đúng read-only embed route**, rồi vẫn kiểm authentication/ACL/session/tenant.

Không cho phép mọi cross-site POST chỉ vì iframe GET được mở. Business POST vẫn cần CSRF token và authorization.

## 21. MockMvc: kiểm frame headers và CSRF trên Servlet

### 21.1. Test contract và dữ liệu fixture

Giả định ứng dụng dùng hai chains ở mục 16, có:

- `GET /account` trả 200 cho user đã login;
- `GET /embed/report/42` trả 200 nếu fake `ReportAccessService` cho phép;
- `POST /embed/report/42/action` là thao tác unsafe để kiểm CSRF, không được thực thi nếu thiếu token.

Sử dụng `spring-security-test`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletFramingSecurityTests {

    @Autowired MockMvc mvc;

    @Test
    void accountCannotBeFramed() throws Exception {
        mvc.perform(get("/account").with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("frame-ancestors 'none'")));
    }

    @Test
    void embedPageHasNarrowPartnerAllowlist() throws Exception {
        mvc.perform(get("/embed/report/42")
                .with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString(
                    "frame-ancestors 'self' " +
                    "https://partner.example.net")))
            .andExpect(header().doesNotExist("X-Frame-Options"));
    }

    @Test
    void unsafeEmbedPostStillRequiresCsrf() throws Exception {
        mvc.perform(post("/embed/report/42/action")
                .with(user("alice")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Phạm vi:** Những test này kiểm **header được Spring phát và `CsrfFilter` theo chain**, không chứng minh browser có render iframe thật. Nếu project dùng OAuth2 Login, thay `with(user(...))` bằng test principal phù hợp; security matcher có thể cần cấu hình trùng route thật.

### 21.2. Kiểm route không bị mở rộng

Thêm các trường hợp:

~~~text
GET /account   -> frame-ancestors 'none', XFO DENY
GET /admin     -> frame-ancestors 'none', XFO DENY
GET /embed/report/42 -> chỉ partner allowlist, không XFO xung đột
GET /embed/report/42 với Bob không quyền -> 403/404 theo contract
POST /embed/report/42/action không _csrf -> 403, không side effect
POST /embed/report/42/action có _csrf nhưng Bob không quyền -> 403/404
~~~

Nếu request từ parent partner không gửi session cookie do SameSite, server có thể trả redirect tới login/401. **Không thêm `permitAll()` để test “iframe render” xanh**. Auth vào iframe là một bài toán riêng.

### 21.3. MockMvc không giả lập CSP enforcement hoặc SOP

`MockMvc` không có browser layout engine, không thực thi iframe sandbox, postMessage, popup blocker, COOP/COEP hoặc SRI. Nó cũng có thể gửi cookie thủ công dù browser thật sẽ chặn.

Do đó **header assertions là cần nhưng không đủ**. Phải chạy browser E2E trên ít nhất những origin/cookie policies được sản phẩm hỗ trợ.

## 22. WebTestClient: Reactive response headers và CSRF

### 22.1. Kiểm chain của WebFlux

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveFramingSecurityTests {

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void accountBlocksAllFraming() {
        client().mutateWith(mockUser("alice"))
            .get().uri("/account")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueMatches(
                "Content-Security-Policy",
                ".*frame-ancestors 'none'.*")
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY");
    }

    @Test
    void embedPageAllowsOnlyTrustedPartner() {
        client().mutateWith(mockUser("alice"))
            .get().uri("/embed/report/42")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueMatches(
                "Content-Security-Policy",
                ".*frame-ancestors 'self' " +
                "https://partner[.]example[.]net.*")
            .expectHeader().doesNotExist("X-Frame-Options");
    }
}
~~~

Tương tự Servlet, test cần controller/service fixture trả đúng response; các expectations không tự chứng minh browser cho phép parent partner render.

### 22.2. Unsafe requests trong embedded session vẫn cần CSRF

Thêm method vào test class:

~~~java
@Test
void unsafeEmbeddedPostWithoutCsrfIsForbidden() {
    client().mutateWith(mockUser("alice"))
        .post().uri("/embed/report/42/action")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Khi muốn kiểm positive path, dùng `SecurityMockServerConfigurers.csrf()` và một fixture `POST` thực, nhưng vẫn kiểm **authorization trên report ID**. CSRF pass không đồng nghĩa Alice có quyền xóa/sửa báo cáo của Bob.

### 22.3. Kiểm proxy/CDN cuối đường

Khi production đặt Spring WebFlux sau ingress hoặc CDN, `WebTestClient` bind-to-context chỉ nhìn internal filter chain. Cần integration HTTP tới **public HTTPS endpoint** để phát hiện proxy thêm/chỉnh XFO/CSP, cache headers, cookies hoặc redirect URI.

### 22.4. Không tự ép iframe chạy trên COEP

Một unit test thấy header `Cross-Origin-Embedder-Policy: require-corp` không chứng minh widget vendor đáp ứng CORP/CORS. Cần browser Network/Console test với **bytes/headers thật của vendor**, và có kế hoạch fallback nếu provider chưa hỗ trợ.

## 23. Kiểm thử trình duyệt E2E: iframe, popup, message và script thực

### 23.1. Chuẩn bị môi trường nhiều origin

Môi trường HTTPS giả lập:

~~~text
RP / Spring:        https://app.example.test
Partner parent:     https://partner.other.test
Vendor widget:      https://widget.vendor.test
Vendor CDN:         https://cdn.vendor.test
OIDC provider:      https://login.identity.test
Malicious parent:   https://attacker.other.test
~~~

Các hostname chỉ là ví dụ; cần DNS/hosts/certificates hoặc local test HTTPS proxy phù hợp. Đảm bảo partner, attacker và RP thực sự ở **những site khác nhau** nếu muốn kiểm cookie SameSite/third-party cookie behavior.

Test browser ở đây phải chạy cùng các chính sách privacy hỗ trợ của sản phẩm; test với một browser profile mặc định không đủ chứng minh mọi cấu hình third-party cookie.

### 23.2. Dùng Playwright kiểm HTTP headers qua public URL

Ví dụ JavaScript/Playwright test (giả định server test chạy và có fixture auth phù hợp):

~~~javascript
import { test, expect } from "@playwright/test";

test("account response cấm framing", async ({ request }) => {
  // Request context cần authenticated storageState nếu endpoint private.
  const response = await request.get(
    "https://app.example.test/account"
  );

  expect(response.status()).toBe(200);
  const headers = response.headers();

  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["content-security-policy"])
    .toContain("frame-ancestors 'none'");
});

test("embed response có allowlist đối tác riêng", async ({ request }) => {
  const response = await request.get(
    "https://app.example.test/embed/report/42"
  );

  expect(response.status()).toBe(200);
  const headers = response.headers();

  expect(headers["content-security-policy"])
    .toContain("https://partner.other.test");
  expect(headers["content-security-policy"])
    .toContain("frame-ancestors");
  expect(headers["x-frame-options"]).toBeUndefined();
});
~~~

**Điều kiện test:** CSP allowlist trong môi trường test phải trùng origin partner test (ví dụ override `partner.example.net` bằng `partner.other.test` qua profile); controller phải trả HTML 200 với test identity. Request API của Playwright **chỉ kiểm headers**, chưa kiểm browser enforcement. Muốn kiểm clickjacking thực, thêm pages ở parent partner và attacker.

### 23.3. Test browser thực sự chặn iframe

Test thủ công/automation theo chuỗi:

1. Trên `attacker.other.test`, tạo trang chứa `<iframe src="https://app.example.test/account">`.
2. Browser phải chặn rendering trang account theo `frame-ancestors 'none'`/XFO, quan sát Console có thông báo từ chối framing.
3. Trên `partner.other.test`, nhúng `/embed/report/42` với tài khoản đủ quyền hoặc cơ chế embed auth đã thiết kế; browser được phép render nếu CSP allowlist và policy khác cho phép.
4. Trên `attacker.other.test`, nhúng `/embed/report/42`; browser phải chặn theo `frame-ancestors` dù attacker biết URL.
5. Kiểm một iframe nhiều tầng: attacker nhúng partner, partner nhúng embed; nếu attacker không nằm trong allowlist ancestors, child RP phải bị chặn.
6. Với user Bob/tenant B, ngay cả khi partner được phép frame và cookie/token hợp lệ về hình thức, backend không trả báo cáo của Alice/tenant A.

**Không dùng `iframe.contentDocument === null` làm bằng chứng duy nhất**: ngay cả iframe cross-origin hợp lệ cũng thường không thể đọc DOM do SOP. Cần kết hợp browser Console/Network, accessible rendering, securitypolicyviolation events khi có và các trạng thái UI/fixtures.

### 23.4. Test sandbox và permissions

Dùng widget fixture có nút:

- Gửi postMessage resize;
- Cố mở popup;
- Cố submit form;
- Cố điều hướng top-level;
- Cố truy cập cookies/storage;
- Cố gọi camera/geolocation khi không có quyền.

Lần lượt bật/tắt `sandbox` tokens và iframe `allow` theo policy, xác minh **chỉ tính năng được cấp mới hoạt động**. Với content same-origin không tin cậy, không dùng `allow-scripts allow-same-origin` làm bằng chứng cô lập an toàn.

### 23.5. Test postMessage giả và đổi origin giữa chừng

- Gửi message đúng `type/version/requestId/height` từ đúng iframe origin: parent thay đổi chiều cao trong range.
- Gửi message cùng data từ một window khác origin: bị bỏ qua.
- Gửi message từ cùng origin nhưng **không phải iframe window reference**: bị bỏ qua.
- Gửi `height="10000px; background:red"`, object, số âm hoặc NaN: bị bỏ qua.
- Gửi `type="EXECUTE_SCRIPT"` hoặc HTML string: handler không có action nào xử lý.
- Điều hướng iframe tới origin khác rồi thử gửi message: không được tin.
- Dùng iframe sandbox opaque origin trả `event.origin="null"`: không dùng wildcard trust để “chữa” lỗi.
- Lặp khi component unmount/remount: không còn listener cũ làm cập nhật nhầm iframe.

**Kiểm thử side effect**: một message độc hại không được gây POST, đổi route sang attacker site, làm lộ DOM data hoặc tạo popup ngoài chính sách.

### 23.6. Test popup và OAuth/OIDC

Chạy browser E2E với test IdP:

1. Bấm nút login, popup mở trong user activation; nếu bị chặn, fallback top-level redirect.
2. Popup chuyển RP → IdP → RP callback; Spring kiểm state/PKCE/nonce như flow thật.
3. Popup-complete gửi **notification không chứa token** về parent.
4. Parent kiểm `event.origin` và `event.source`, rồi gọi `/api/me` để xác nhận session; chỉ lúc đó mới hiển thị “đã đăng nhập”.
5. Popup giả gửi `LOGIN_COMPLETE` từ origin ngoài hoặc window khác: không làm parent đổi authenticated UI.
6. Đổi COOP policy để kiểm opener có bị tách; nếu bị tách, app dùng fallback an toàn, không vô hiệu hóa protocol checks.
7. Sau logout/session expiry, message cũ không phục hồi trạng thái authenticated.
8. Xác minh browser state/cookies khi popup bị đóng sớm, nhiều popup hoặc nhiều tab đồng thời.

### 23.7. Test external scripts và SRI

Trong môi trường kiểm soát:

- Giữ asset bytes đúng hash: browser tải script và chức năng hoạt động.
- Thay một byte asset nhưng giữ `integrity` cũ: browser chặn script, hiển thị SRI error; chức năng không được tự động bỏ `integrity`.
- Bỏ response CORS cần thiết cho cross-origin SRI resource: quan sát browser từ chối theo CORS/integrity policy.
- Cho loader script cố tải asset từ domain ngoài `script-src`: CSP chặn.
- Cho widget iframe cố fetch ngoài `connect-src` của document widget/parent tương ứng: kiểm bên sở hữu CSP.
- Tắt CDN: app có graceful degradation và không rơi vào “tự download JS từ URL bất kỳ” không được duyệt.

### 23.8. Cookie và Storage Access trong iframe

Trên browser profile có third-party cookies bị hạn chế:

1. Login RP ở top-level, kiểm cookie `Secure; HttpOnly; SameSite`.
2. Mở trang partner và iframe RP: ghi nhận cookie RP có/không được gửi trong **iframe request**.
3. Đổi cookie Lax/None (với Secure) ở môi trường test: phân biệt SameSite điều kiện với browser 3PC restrictions.
4. Nếu dùng partitioned cookies/Storage Access API, kiểm partition/key và khả năng browser xin quyền; không assume browser nào cũng hỗ trợ.
5. Nếu không có credential, RP phải từ chối private report hoặc hướng đến top-level auth flow, **không tự công khai báo cáo**.
6. Kiểm CSRF của POST trong embedded context nếu flow thật cho phép cookie.
7. Kiểm phản hồi login/redirect khi được đặt trong iframe: IdP có thể cấm framing, và đó là yêu cầu cần tôn trọng.

### 23.9. Bảo vệ test artifacts

HAR, Playwright traces, video và screenshots có thể chứa session cookies, code/state/ID token, dữ liệu thanh toán, thông tin người dùng và URL capability. Chỉ dùng test identities, redact secrets trước khi lưu/chia sẻ, giới hạn retention và không gửi log production đầy đủ sang vendor.

## 24. Ma trận kiểm thử phòng vệ HTTP cho embedded integrations

| ID | Tình huống | Mong đợi |
|---|---|---|
| **EM-01** | Parent attacker nhúng `/account` | Bị chặn bằng frame-ancestors/XFO |
| **EM-02** | Parent same-origin nhúng trang cấm frame | Bị chặn nếu policy `'none'` |
| **EM-03** | Parent partner nhúng đúng `/embed/report/42` | Rendering cho phép theo CSP nếu auth hợp lệ |
| **EM-04** | Parent attacker nhúng `/embed/report/42` | CSP chặn |
| **EM-05** | Attacker → partner → RP iframe nested | Không bypass ancestor chain |
| **EM-06** | XFO DENY còn trên embed route | Phát hiện xung đột, không coi config pass |
| **EM-07** | `frame-ancestors` được khai trong meta thay HTTP header | Không coi là enforcement hợp lệ |
| **EM-08** | Parent `frame-src` không allow widget | Browser chặn iframe vendor |
| **EM-09** | Vendor child `frame-ancestors` không allow RP | Browser chặn iframe dù parent cho phép |
| **EM-10** | User không quyền biết URL/ID báo cáo | Backend 403/404, không lộ dữ liệu |
| **EM-11** | Cookie RP Lax trong cross-site iframe | Không giả định browser gửi cookie |
| **EM-12** | Cookie RP None/Secure và 3PC block | Fail closed; không bỏ auth |
| **EM-13** | Partitioned cookie trong hai top-level sites | Không trộn session/partition |
| **EM-14** | Sandbox child cố top-navigation không user activation | Bị chặn theo policy |
| **EM-15** | Sandbox child cố mở popup khi không allow | Bị chặn |
| **EM-16** | Same-origin untrusted frame có allow-scripts + allow-same-origin | Bị coi là thiết kế isolation không đủ |
| **EM-17** | postMessage đúng origin/source/type | Xử lý đúng action allowlisted |
| **EM-18** | postMessage giả từ origin khác | Không xử lý |
| **EM-19** | postMessage từ window khác cùng origin | Không xử lý khi source sai |
| **EM-20** | postMessage có HTML/script injection | Không eval/innerHTML, không thực thi |
| **EM-21** | postMessage height ngoài range | Bỏ qua |
| **EM-22** | Popup ngoài có noopener | Không giữ opener reference không cần |
| **EM-23** | OAuth popup callback báo success giả | Parent không coi là authenticated |
| **EM-24** | COOP tách opener trong popup login | Fallback an toàn, không bỏ state/PKCE |
| **EM-25** | OAuth popup code/state sai | RP không login |
| **EM-26** | Third-party script đúng bytes SRI | Browser có thể tải nếu CSP/CORS đủ |
| **EM-27** | Third-party script bytes đổi nhưng hash cũ | Browser chặn |
| **EM-28** | Third-party script tự tải domain ngoài CSP | Browser chặn request tương ứng |
| **EM-29** | CORS wildcard + credentials | Browser không cho credentialed JS đọc response theo policy |
| **EM-30** | COEP require-corp với vendor chưa opt-in | Fail có chẩn đoán; không mở policy tùy tiện |
| **EM-31** | CORP same-origin trên private resource | Cross-origin no-cors embed bị hạn chế |
| **EM-32** | iframe GET được cho phép, browser POST thiếu CSRF | POST vẫn bị chặn |
| **EM-33** | POST có CSRF đúng nhưng user sai tenant | Object-level authorization chặn |
| **EM-34** | Payment return query status=success giả | Không tự đánh dấu order paid |
| **EM-35** | Webhook không có signature hợp lệ | Reject, không update order |
| **EM-36** | Webhook ký hợp lệ nhưng replay event ID | Idempotent, không update hai lần |
| **EM-37** | CAPTCHA widget render nhưng result token giả | Server verification reject |
| **EM-38** | Browser login iframe bị IdP XFO/CSP deny | Không strip header; đổi flow được hỗ trợ |
| **EM-39** | External iframe URL chứa access token dài hạn | Bị đánh giá không đạt, đổi capability policy |
| **EM-40** | CDN/proxy thay XFO/CSP route embed | Integration public HTTP test phát hiện |
| **EM-41** | CSP Report-Only không chặn script độc hại | Không coi Report-Only là enforcement |
| **EM-42** | Trang admin lỗi vẫn bị frame | Xác minh headers/error paths để không bypass |
| **EM-43** | GET download file riêng tư qua iframe | Vẫn kiểm ACL, download policy, không cache sai |
| **EM-44** | Third-party image nhận Referer nhạy cảm | Referrer-Policy bảo vệ, không đặt token ở URL |
| **EM-45** | Popup login session đã expired nhưng message đến muộn | Parent gọi backend và không xác thực nhầm |
| **EM-46** | Fetch Metadata chặn mọi cross-site GET | Có ngoại lệ hẹp cho embed read-only được duyệt |
| **EM-47** | Browser cookie là host-only sai host callback | Không bỏ authentication/state để chữa lỗi |
| **EM-48** | Trusted partner origin có wildcard subdomain | Kiểm phạm vi và tránh cho subdomain attacker kiểm soát |
| **EM-49** | Trang user-generated HTML trên app origin trong iframe | Không được chạy với quyền origin RP |
| **EM-50** | Vendor script bị vô hiệu hóa | App có fallback, không chấp nhận domain thay thế bất kỳ |

### 24.1. Kiểm tra trạng thái cuối thay vì chỉ status

Với clickjacking/iframe, test HTTP 200 của `/account` **không chứng minh** browser đã hiển thị hay chặn; cần kiểm browser enforcement. Với webhook, `403`/`401` không đủ nếu database đã bị cập nhật trước khi verify signature.

Ví dụ:

~~~text
Trước:
  order 42 = PENDING
Gửi:
  POST /integrations/payments/webhook
  chữ ký không hợp lệ, body payment.succeeded
Sau:
  order 42 vẫn PENDING
  không phát event Paid
  không gửi email xác nhận.
~~~

Với message giả:

~~~text
Trước:
  parent chưa đăng nhập
Gửi:
  LOGIN_COMPLETE từ origin không tin cậy
Sau:
  không chuyển sang authenticated UI
  không lưu token/cookie do message cung cấp
  không gọi API mutate.
~~~

### 24.2. Negative test về quyền iframe

~~~text
Alice, tenant-A:
  GET /embed/report/F1 -> 200 (khi auth phù hợp)
Bob, tenant-B:
  GET /embed/report/F1 -> 403/404
Attacker parent:
  iframe /embed/report/F1 -> browser chặn framing theo CSP

Ba trường hợp kiểm ba điều khác nhau:
  user auth + ACL,
  parent framing allowlist,
  browser enforcement.
~~~

CSP không thay ACL và ACL không tự chống clickjacking. Hai điều kiện phải **đồng thời đúng**.

## 25. Chẩn đoán sự cố theo thông báo browser và HTTP

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/thao tác đúng |
|---|---|---|
| “Refused to frame ... X-Frame-Options DENY” | Child response có XFO DENY | Kiểm response **child**, có cần nhúng hay phải giữ deny |
| “Violates frame-ancestors” | Child CSP không cho parent/ancestor | So exact origin, nested ancestor chain và child HTTP header |
| Parent CSP “frame-src” chặn widget | Parent không allow target | Chỉnh `frame-src` của parent khi vendor được duyệt |
| Đã allow `frame-src` nhưng widget vẫn không hiện | Child XFO/frame-ancestors/sandbox/COEP chặn | Kiểm cả hai response và Console |
| `<meta>` CSP không chặn framing | frame-ancestors không có hiệu lực tương đương trong meta | Đặt CSP trong HTTP response |
| Trang embed ở partner hiện login hoặc 401 | RP cookie Lax/3PC không gửi, auth thiếu | Kiểm Cookie Network, SameSite, auth architecture |
| SameSite=None nhưng iframe vẫn mất session | Browser chặn third-party cookies | Cân nhắc top-level login/Storage Access/partitioning/token design |
| Widget không thể submit form | Sandbox thiếu `allow-forms` hoặc CSP form-action | Chỉ mở quyền thực sự cần, validate form phía nhận |
| Widget không thể mở popup | Sandbox/allow-popups, popup blocker | Kiểm user activation, sandbox và UX fallback |
| Iframe script không dùng storage | Sandbox opaque origin hoặc 3PC | Kiểm `allow-same-origin`/browser policy, không mở thiếu review |
| postMessage không đến | Target origin sai, iframe chưa load, COOP/opener | Kiểm origin thật, load/lifecycle và window reference |
| postMessage từ attacker được xử lý | Không kiểm origin/source/schema | Sửa handler, thêm negative tests |
| Popup luôn `window.opener === null` | noopener/COOP tách group | Xác định có cần opener không, fallback nếu không |
| OAuth popup báo success nhưng parent chưa login | Message đến trước session persist hoặc session cookie sai | Parent gọi `/api/me`, kiểm cookie/auth callback |
| Popup bị chặn | Mở ngoài user activation | Mở trong click handler, top-level fallback |
| SRI “Failed to find a valid digest” | Asset bytes đổi/hash sai | Pin đúng file/version và tính lại digest sau review |
| SRI/CORS error từ CDN | Thiếu cross-origin CORS opt-in cho integrity | Chỉnh CDN CORS/`crossorigin` phù hợp, không bỏ SRI |
| CSP script-src chặn CDN | Origin/script hash/nonce chưa được phép | Review asset, cập nhật CSP tối thiểu |
| CSP Report-Only thấy lỗi nhưng trang vẫn chạy | Policy đang ở chế độ chỉ báo cáo | Chuyển enforce sau khi đánh giá đầy đủ |
| COEP chặn ảnh/script/iframe vendor | Resource chưa có CORP/CORS opt-in | Làm việc với vendor, cân nhắc isolation design |
| COOP làm popup login mất opener | Browsing context isolation | Kiểm policy/browser và fallback, không bỏ OAuth validation |
| CSP connect-src chặn analytics | Endpoint không allowlist | Cân nhắc privacy/risk trước khi cho phép |
| iframe bị browser lỗi permissions | `allow`/Permissions-Policy/user permission | Cấp tối thiểu quyền cần thiết, giữ denied mặc định |
| `403` khi POST trong embedded view | CSRF token missing/sai hoặc authz | Kiểm CsrfFilter, cookie/session và business ACL |
| CORS error trên API bên thứ ba | JS cross-origin fetch chưa được allow | Kiểm preflight/CORS; không dùng làm “sửa iframe” |
| Browser trả 200 HTML SPA thay JSON | Proxy fallback chặn API route | Sửa routing/status tại proxy |
| Payment return success nhưng order còn pending | Webhook/API confirmation chưa verified | Không tin query, đối chiếu provider events |
| Webhook trả 403 CSRF | CSRF filter chặn POST server-to-server | Exception hẹp + chữ ký/replay/idempotency |
| Payment webhook giả được xử lý | Thiếu signature/amount/order checks | Ngăn và audit, không chỉ IP allowlist |
| Embed report Alice hiện cho Bob | BOLA/IDOR hoặc cache wrong tenant | Resource ACL/no-store/cache key |
| Chỉ production bị frame deny | CDN/ingress thêm XFO/header khác | So response public edge và internal Spring |
| CSS/JS của embed thiếu trên prod | CSP default-src/style-src/script-src hoặc proxy paths | Network/Console, policy đúng route |
| Header `frame-ancestors 'self'` nhưng partner khác subdomain bị chặn | Same-origin khác same-site | Thêm exact trusted origin nếu thật sự cần |
| XFO `SAMEORIGIN` bị hiểu là cho tất cả subdomains | Sai khái niệm origin | So scheme/hostname/port |
| Trang có token trong URL rồi vendor nhận Referer | Referrer-Policy hoặc URL secret design yếu | Không dùng token dài hạn trong URL, giảm referrer |
| Browser chặn IdP login trong iframe | IdP intentionally denies framing | Dùng provider-supported top-level flow |
| CSP frame ancestor cho partner A nhưng attacker A-subdomain nhúng được | Allowlist quá rộng | Siết exact origins, xem subdomain takeover |

### 25.1. Trình tự kiểm tra “iframe trắng”

~~~text
1. URL iframe có trả HTML đúng ở top-level không?
2. Parent có CSP frame-src allow iframe URL không?
3. Child có XFO và CSP frame-ancestors như thế nào?
4. Có nested ancestor không nằm trong allowlist không?
5. Iframe sandbox có chặn script/form/navigation cần thiết?
6. Browser có gửi session cookie cần cho child không?
7. Backend có trả 200/401/403/redirect/SPA fallback khác dự kiến?
8. Có COEP/CORP/COOP/CORS conflict không?
9. JavaScript trong child có lỗi CSP/SRI/postMessage không?
10. Có cache/proxy thêm/bớt headers so với Spring nội bộ không?
11. Quyền user/tenant/report có đúng không?
12. Sau negative test, dữ liệu và session có giữ nguyên không?
~~~

### 25.2. Trình tự kiểm tra “popup OAuth không báo thành công”

~~~text
1. window.open được gọi trong user click? Có bị popup blocker?
2. Popup đi đúng start-login URL do RP quản lý?
3. IdP authorize/redirect URI có hợp lệ, không bị sai host/proxy?
4. Spring OAuth callback so state/PKCE/nonce và tạo session thành công?
5. Popup đã về origin RP trên /auth/popup-complete chưa?
6. COOP/noopener có làm window.opener null?
7. Parent listener có kiểm event.origin, event.source và schema đúng?
8. Parent có gọi backend /api/me thay vì tin message?
9. Cookie Session Secure/SameSite/Domain/Path và rotation đúng?
10. Đã thử fallback top-level redirect khi popup thất bại chưa?
~~~

**Không** giải quyết cả danh sách bằng cách vô hiệu hóa CSP, COOP, CSRF hoặc OAuth state/nonce/PKCE. Mỗi symptom thuộc một cơ chế riêng.

## 26. Checklist triển khai production

| Chủ đề | Điều kiện đạt trước khi phát hành |
|---|---|
| **Bản đồ origin/site** | Danh sách RP, partner, IdP, widget, CDN, APIs, webhook và chính sách cookie |
| **Mục đích nhúng** | Biết trang nào là parent, trang nào là child, dữ liệu nào thật sự cần |
| **Default frame protection** | Trang account/admin/checkout nhạy cảm không cho framing |
| **XFO và CSP** | `X-Frame-Options` và `frame-ancestors` nhất quán theo route/browser support |
| **Partner allowlist** | Exact origin, không dùng `*`/wildcard subdomain không cần thiết |
| **Outbound iframes** | Parent có `frame-src` chỉ cho các vendors đã duyệt |
| **Nested frame** | Kiểm toàn ancestor chain, không chỉ parent gần nhất |
| **Authorization** | User/tenant/report ACL tại Spring service, không tin CSP hoặc Origin để cấp quyền |
| **Embed page scope** | Route/read-only UI riêng, không vô ý mang admin buttons vào widget |
| **Cache** | No-store hoặc thiết kế cache theo identity/tenant/version, không shared leak |
| **Cookie** | Secure, HttpOnly, SameSite, Domain/Path; test cross-site iframe/3PC |
| **Cookie alternatives** | Nếu browser chặn third-party cookie, có top-level auth/capability flow an toàn |
| **Sandbox** | Tối thiểu tokens; không dùng allow-scripts+allow-same-origin cho same-origin untrusted content |
| **Permissions** | Camera/microphone/geolocation… denied mặc định, chỉ mở khi hợp đồng rõ |
| **postMessage send** | `targetOrigin` đúng exact origin; không gửi secrets/PII quá mức |
| **postMessage receive** | Kiểm `event.origin`, `event.source`, version, schema, size và transaction |
| **Popup external links** | Dùng noopener/noreferrer nếu không cần kênh opener |
| **Popup SSO** | State/nonce/PKCE, trusted RP callback, no tokens in message, backend recheck |
| **COOP** | Kiểm ảnh hưởng đến popup/opener khi bật isolation |
| **COEP/CORP** | Chỉ bật khi vendors opt in theo resource requirements |
| **Third-party scripts** | Inventory, pin version, SRI/CSP, review code, emergency kill switch |
| **CSP** | script-src, frame-src, frame-ancestors, connect-src, img-src, style-src, form-action được tách rõ |
| **Dynamic CSP nonce** | Secure random per-response, HTML/header đồng bộ, cache không lệch |
| **SRI** | Digest từ artifact review, crossorigin/CORS đúng, không auto-disable khi mismatch |
| **CORS** | Origin allowlist cho JS fetch; không dùng như proxy auth hoặc framing permission |
| **CSRF** | Browser cookie-auth unsafe POST vẫn kiểm token, kể cả từ embedded context |
| **Webhook** | Chỉ exemption hẹp, signature/raw bytes/timestamp/replay/idempotency |
| **Payment return** | Không tin query success, xác minh với provider backend |
| **CAPTCHA** | Token result được server-side verify; widget render không là bằng chứng |
| **Redirects** | Không open redirect, callback HTTPS exact host/URI qua trusted proxy |
| **HTTP headers** | HSTS, nosniff, referrer, cache, permissions được phát tại đúng owner |
| **Network logs** | Không lộ code/token/session, capability URL, card data hoặc PII |
| **Browser E2E** | Test parent/child/attacker origins, SameSite/3PC, popup và asset loading |
| **Error paths** | Headers và authz vẫn đúng với 401/403/404/redirect/5xx |
| **Operations** | Monitor CSP violations, vendor outages, signed URL leaks và rollback changes |

### 26.1. Mẫu bảng review đối tác

~~~text
Integration ID: vendor-report-42
Use case: Embed read-only report
Parent origin: https://partner.example.net
Child origin: https://app.example.com
Child route: /embed/report/{id}
Auth model: session / scoped capability / backend exchange
Is cross-site third-party cookie required? yes/no
Data classification: private / public / tenant-restricted
Object ACL provider: internal ReportAccessService
CSP parent frame-src:
CSP child frame-ancestors:
X-Frame-Options child:
Sandbox tokens:
Permissions Policy / iframe allow:
postMessage message types + schemas + targetOrigin:
Script/CDN assets + SRI/version:
COOP/COEP/CORP requirements:
Referrer/cache policy:
Token/session/code logging redaction:
Browser test coverage:
Vendor incident contact:
Feature flag / emergency disable:
~~~

Mẫu này giúp review **mối liên hệ giữa hai phía** thay vì chỉ hỏi “đã có X-Frame-Options chưa?”. Không lưu các secret hay token thực vào checklist.

### 26.2. Khi tính năng cần cả embed và popup

Một trang đối tác có iframe RP; iframe RP muốn mở popup IdP. Có thể va chạm **nhiều lớp cùng lúc**:

1. Partner `frame-src` cho phép RP?
2. RP child `frame-ancestors` có cho partner?
3. Iframe `sandbox` có `allow-popups` và các quyền cần thiết?
4. Popup blocker/user activation có cho mở?
5. IdP có cho callback đúng public RP URL?
6. COOP của RP/IdP có tách opener?
7. RP cookie session trong iframe/popup có hoạt động với SameSite/browser 3PC?
8. OAuth state/nonce/PKCE có được kiểm đầy đủ?
9. Callback chỉ gửi signal tối thiểu và parent có xác minh message không?
10. Báo cáo sau login có ACL đúng và không bị cache trộn tenant?

Nếu một yêu cầu bị chặn bởi chính sách bảo mật có chủ đích, **không nên mở toàn bộ các policy**. Có thể chọn top-level login trước khi vào embed, hoặc thay widget bằng một trang có capability rõ ràng theo domain business.

## 27. Bài tập thực hành có hướng dẫn giải

### Bài 1 — Trang admin bị lồng vào website giả

Ứng dụng có `GET /admin/delete-user` hiển thị nút xác nhận. Attacker nhúng URL này vào một iframe trong trang “nhận quà”, dùng overlay để người dùng click.

**Yêu cầu:** Chỉ ra vì sao CSRF token không đủ.

**Gợi ý giải:** Người dùng có thể thực sự bấm trên trang RP hợp lệ trong iframe, form của trang đó có CSRF token đúng. Cần `frame-ancestors 'none'`/XFO DENY trên trang admin, UI confirmation và authorization/reauthentication theo nghiệp vụ.

### Bài 2 — Nhầm frame-src và frame-ancestors

Spring RP muốn nhúng iframe video từ `https://video.vendor.example`. Developer thay `X-Frame-Options` trên RP từ DENY sang SAMEORIGIN nhưng video vẫn bị chặn.

**Gợi ý:** RP là parent, cần kiểm parent `frame-src` có allow video không và child/vendor `frame-ancestors` có cho RP không. XFO của RP bảo vệ RP **khi bị nhúng**, không cấp quyền nhúng video vendor.

### Bài 3 — Partner được frame nhưng không được đọc báo cáo của Bob

Trang partner đã nằm trong allowlist `frame-ancestors` cho `/embed/report/{id}`. Alice và Bob có hai report khác tenant, nhưng controller chỉ kiểm `authenticated()` và đọc ID trực tiếp.

**Gợi ý:** Đây là BOLA/IDOR. Header chỉ quyết định framing, không cấp quyền dữ liệu; service phải kiểm principal/tenant/resource ACL trước khi render, và cache không được lộ qua shared CDN.

### Bài 4 — postMessage kiểm Origin sai

Handler dùng:

~~~javascript
if (event.origin.includes("trusted.example")) {
  document.querySelector("#status").innerHTML = event.data.html;
}
~~~

**Gợi ý:** `includes` có thể cho domain giống `evil-trusted.example.attacker.invalid` qua; `innerHTML` với input ngoài tạo nguy cơ DOM XSS. So exact origin/source, kiểm schema/action allowlist, dùng `textContent` hoặc API rendering an toàn và không chấp nhận HTML tùy ý.

### Bài 5 — Sandbox cùng origin không đủ cô lập

Parent nhúng trang HTML do người dùng upload dưới `/uploads/page.html` và đặt `sandbox="allow-scripts allow-same-origin"` để tiện lưu cookie.

**Gợi ý:** Tổ hợp đó không phải isolation boundary an toàn cho same-origin untrusted content. Đổi sang origin chuyên biệt không chia sẻ RP cookie, CSP/sandbox chặt, không render active content cùng RP origin; áp validation/Content-Disposition cho file tải xuống.

### Bài 6 — Popup OAuth mất opener

Ứng dụng thêm `rel=noopener`/`COOP: same-origin` cho mọi trang. Popup vẫn hoàn tất OIDC login nhưng `window.opener === null`, parent không nhận `LOGIN_COMPLETE`.

**Gợi ý:** Tách opener là hành vi bảo vệ có thể xung đột popup handshake. Kiểm COOP/noopener và thiết kế fallback top-level redirect hoặc kênh trao đổi đã review; **không bỏ state, nonce, PKCE** hoặc gửi ID token qua query để chữa.

### Bài 7 — SRI không còn khớp sau CDN release

`widget.min.js` ở URL v3 được cập nhật nội dung nhưng HTML vẫn giữ integrity hash cũ. Browser không tải script.

**Gợi ý:** Đây là hoạt động bảo vệ SRI. Pin asset version/bytes, review release rồi cập nhật digest trong build; không bỏ `integrity` hoặc mở script-src mọi origin để tiện deploy.

### Bài 8 — Script vendor và HttpOnly cookie

Developer cho rằng vendor analytics script không thể gây yêu cầu đổi email vì cookie `HttpOnly`.

**Gợi ý:** HttpOnly ngăn JS đọc cookie, nhưng script chạy trong origin của RP có thể phát same-origin request mà browser tự đính kèm cookie và có thể đọc CSRF token/DOM. Cần giảm trust/scope vendor script, CSP/SRI, kiểm business authorization và chống XSS.

### Bài 9 — SameSite=Lax iframe mất session

Một partner nhúng iframe báo cáo riêng tư. User đã đăng nhập RP ở tab khác, nhưng iframe trả 401. Developer đề xuất `permitAll()` trên toàn `/embed/**`.

**Gợi ý:** Lax cookie thường không đi cross-site iframe. Không bỏ auth; thiết kế top-level authentication, token/capability có scope/TTL và ACL, hoặc giải pháp browser cookie partition/Storage Access có hỗ trợ/đánh giá. Test trên browsers thật.

### Bài 10 — Payment webhook bị coi là CSRF

Provider gửi POST server-to-server không có Spring CSRF token, nhận 403. Developer tắt CSRF toàn ứng dụng.

**Gợi ý:** CSRF exception chỉ cho **đúng webhook POST endpoint** được bảo vệ bằng provider signature/timestamp/replay/idempotency. Browser forms/account/delete vẫn cần Spring CSRF. Payment return query không được coi là bằng chứng paid.

### Bài 11 — COEP làm tất cả ảnh CDN biến mất

Team bật `Cross-Origin-Embedder-Policy: require-corp` để dùng tính năng cần cross-origin isolation, nhưng CDN/vendor image không có CORS/CORP opt-in.

**Gợi ý:** Cần vendor/server asset opt-in hoặc thiết kế khác: host asset hợp lệ, dùng CORS/CORP phù hợp, tách isolation route nếu có thể. Không bỏ mọi CSP/COEP một cách mù quáng; xác minh yêu cầu bảo mật/tính năng.

### Bài 12 — Báo cáo CSP chỉ ghi nhận nhưng không chặn

Production gửi `Content-Security-Policy-Report-Only`, thấy report về script lạ nhưng script vẫn chạy.

**Gợi ý:** Report-Only chỉ quan sát; chuyển sang enforcement sau khi fix vi phạm thật và test. Báo cáo có thể chứa URLs nhạy cảm, cần privacy/retention controls.

### Bài 13 — Nested iframe đi qua trang đối tác

`frame-ancestors https://partner.example.net` cho phép partner nhúng RP. Nhưng attacker nhúng parent partner vào iframe của mình, khiến RP thành nested grandchild.

**Gợi ý:** Browser đánh giá **mọi ancestors** đối với `frame-ancestors`. Nếu attacker origin không được allow, RP bị chặn. Kiểm browser E2E, không chỉ test immediate parent.

### Bài 14 — Third-party image rò thông tin

Trang RP chứa URL `/account?sessionToken=SECRET` và tải `<img src="https://tracking.vendor.example/pixel">`.

**Gợi ý:** Đừng đưa session/access token vào URL; dùng Referrer-Policy phù hợp để hạn chế Referer, kiểm analytics/tracking privacy và cookie policy. `img-src` không ngăn vendor thu thập telemetry đã được browser gửi nếu cho phép.

### Bài 15 — Video iframe được phép nhưng postMessage chứa access token

Parent gửi `postMessage({type:"INIT", accessToken: "Bearer ..." }, "*")` vào vendor iframe cho “tiện”.

**Gợi ý:** Không gửi credential/tokens qua message nếu không có authorization channel được review. Dùng exact `targetOrigin`, hạn chế payload, backend exchange/capability có scope và TTL khi cần; parent phải kiểm source/origin khi nhận.

## 28. Câu hỏi tự đánh giá

**Câu 1.** Header nào hạn chế một trang RP được nhúng bởi origin nào?

**Đáp án:** CSP `frame-ancestors` trên response của **document RP được nhúng**. `X-Frame-Options` có DENY/SAMEORIGIN nhưng không cấp được allowlist partner linh hoạt như CSP.

**Câu 2.** `frame-src` và `frame-ancestors` khác nhau thế nào?

**Đáp án:** `frame-src` kiểm nguồn iframe mà **trang parent tải**; `frame-ancestors` kiểm các **ancestors được phép frame child document**. Hai chiều kiểm độc lập.

**Câu 3.** Vì sao không dùng `X-Frame-Options: ALLOW-FROM https://partner.example` để cấp quyền?

**Đáp án:** ALLOW-FROM lỗi thời/không được browser hiện đại hỗ trợ nhất quán. Dùng CSP `frame-ancestors` exact origin trên route được nhúng; tránh XFO xung đột và xác định browser support contract.

**Câu 4.** Một trang được cho phép nhúng bằng frame-ancestors có tự được đọc dữ liệu private không?

**Đáp án:** Không. CSP chỉ kiểm rendering, còn backend phải xác thực principal và kiểm object/tenant ACL.

**Câu 5.** Khi iframe vendor khác origin, parent có thể đọc DOM của child bằng `contentWindow.document` không?

**Đáp án:** Thông thường không, do Same-Origin Policy. Dùng postMessage cho hợp đồng trao đổi tối thiểu được kiểm origin/source/schema.

**Câu 6.** Vì sao `event.origin.includes("vendor.example")` không đủ an toàn?

**Đáp án:** Substring có thể khớp domain attacker; phải so exact origin (scheme, hostname, port), kiểm `event.source` và shape/action/transaction.

**Câu 7.** Có nên gửi CSRF token hoặc session cookie sang iframe vendor qua postMessage không?

**Đáp án:** Không mặc định. Đó là secret/credential hoặc token nhạy cảm của RP; nếu integration cần dữ liệu, dùng cơ chế cấp quyền riêng có scope/TTL và threat model.

**Câu 8.** Nguy hiểm gì với iframe same-origin untrusted content và `allow-scripts allow-same-origin`?

**Đáp án:** Sandbox có thể mất tác dụng cô lập khi script chạy với quyền same-origin và tương tác với parent/sandbox element. Tách nội dung sang origin riêng, không cấp đồng thời hai quyền một cách tùy tiện.

**Câu 9.** `SameSite=Lax` có tự gửi cookie trong cross-site iframe không?

**Đáp án:** Thông thường không, dù có thể gửi trên top-level cross-site safe GET. Còn cần thỏa Domain/Path/Secure và browser privacy policy.

**Câu 10.** `SameSite=None; Secure` bảo đảm third-party iframe cookies hoạt động trên mọi browser chứ?

**Đáp án:** Không. Third-party cookie blocking/partitioning vẫn có thể áp; cần kiểm browser thật và có fallback/kiến trúc auth phù hợp.

**Câu 11.** Một external `<script src>` chạy dưới quyền origin nào?

**Đáp án:** Dưới quyền origin **document đã nhúng script**, không được sandbox chỉ vì file JS được tải từ CDN khác origin.

**Câu 12.** SRI bảo vệ điều gì và chưa bảo vệ điều gì?

**Đáp án:** SRI so bytes tải với digest đã pin; nó không bảo đảm code đã duyệt không có bug/malware, không sandbox script và không tự kiểm dependency tải động.

**Câu 13.** Khi dùng SRI cross-origin, cần xét gì thêm?

**Đáp án:** `crossorigin` và CORS-enabled resource response theo browser, cùng đúng bytes/hash/version. CDN đổi file mà hash cũ thì browser chặn là hành vi đúng.

**Câu 14.** Popup link ngoài không cần callback nên dùng thuộc tính gì?

**Đáp án:** `rel="noopener noreferrer"` cho `target="_blank"` khi phù hợp, hoặc `window.open` với noopener/noreferrer, để giảm opener/tabnabbing và Referer leakage.

**Câu 15.** Vì sao popup OAuth có thể không dùng noopener như link thông thường?

**Đáp án:** Một số flow cần `window.opener.postMessage` từ same-origin completion page. Noopener/COOP có thể làm kênh đó biến mất; cần thiết kế kênh/fallback riêng và vẫn kiểm OAuth state/nonce/PKCE.

**Câu 16.** Parent nhận `LOGIN_COMPLETE` từ popup có nên tự coi đã đăng nhập không?

**Đáp án:** Không. Kiểm event.origin/source và gọi endpoint RP authenticated như `/api/me` để xác minh session sau server-side OAuth validation.

**Câu 17.** CORS có cấp quyền nhúng iframe không?

**Đáp án:** Không. Parent `frame-src` và child `frame-ancestors`/XFO mới liên quan tới framing; CORS liên quan chủ yếu tới JS cross-origin response reading.

**Câu 18.** COOP khác COEP thế nào?

**Đáp án:** COOP điều chỉnh opener/browsing context isolation; COEP yêu cầu subresources cross-origin opt-in theo cơ chế được hỗ trợ. Cả hai không thay authentication/CSRF.

**Câu 19.** CORP có phải user authorization của file không?

**Đáp án:** Không. CORP giới hạn một số cross-origin no-cors resource loads; backend vẫn phải kiểm user/tenant/file ACL.

**Câu 20.** Vì sao một webhook có thể miễn CSRF nhưng không được để public POST không bảo vệ?

**Đáp án:** Webhook là server-to-server nên thường không có browser session cookie; có thể miễn CSRF đúng endpoint, nhưng phải verify signature, timestamp, replay/idempotency và quyền nhà cung cấp.

**Câu 21.** Browser return từ cổng thanh toán có status=success có thể cập nhật order thành paid ngay không?

**Đáp án:** Không. Tham số browser có thể bị sửa; server cần xác minh giao dịch qua provider API/webhook đáng tin và đối chiếu order/amount/currency.

**Câu 22.** CSP Report-Only khác CSP enforce như thế nào?

**Đáp án:** Report-Only thu thập thông tin vi phạm, không bảo đảm chặn. Enforcement bằng `Content-Security-Policy` thực tế và test browser.

**Câu 23.** Vì sao cấu hình XFO/CSP cần kiểm trên public URL thay vì chỉ Spring response nội bộ?

**Đáp án:** Proxy/CDN có thể thêm, bỏ hoặc đổi headers, redirect/cookie và cache policy; browser thực thi **response cuối cùng** nhận được.

**Câu 24.** Một user có CSRF token hợp lệ có mặc nhiên được xóa report khác tenant không?

**Đáp án:** Không. CSRF bảo vệ request giả mạo, không cấp business authorization; phải kiểm ACL theo report/tenant.

**Câu 25.** Cách phân biệt iframe bị CSP chặn với iframe tải thành công nhưng không có cookie?

**Đáp án:** Kiểm Console/Network: CSP/XFO framing violation thường chặn rendering; thiếu cookie có thể khiến server trả 401/302/login HTML. Cần xem response headers child, Cookie request, SameSite/3PC và auth route.

## Kết luận

**Trang nhúng, popup và tài nguyên bên thứ ba** kết hợp nhiều lớp phòng vệ HTTP/trình duyệt khác nhau. Một **iframe** có origin riêng và thường bị SOP hạn chế DOM access; **script tải từ CDN** lại thực thi bằng quyền của trang đã nhúng; **popup** có browsing-context/opener behavior riêng; **webhook** là server-to-server và không chịu browser CORS/CSRF theo cùng threat model.

Trong Spring Security:

- Giữ **X-Frame-Options DENY** và CSP `frame-ancestors 'none'` cho các trang không cần nhúng, nhất là account/admin. Khi cần partner nhúng, tạo **route chuyên biệt** với CSP `frame-ancestors` exact-origin allowlist và không phát XFO xung đột ở route đó.
- Khi RP là **parent** nhúng widget, kiểm `frame-src` của parent và `frame-ancestors`/XFO của **widget child**, rồi mới xét sandbox, Permissions Policy, SameSite/third-party cookies và message protocol.
- Với `postMessage`, chỉ xử lý nguồn có `event.origin`/`event.source` khớp, schema/action được allowlist, không thực thi HTML/script do message cung cấp hay truyền credentials dài hạn.
- Với popup OAuth/OIDC, dùng state/nonce/PKCE và server-side callback validation; parent chỉ nhận notification và xác minh session với backend. Noopener và COOP tăng isolation nhưng có thể phá kênh opener, vì vậy cần kiểm browser và fallback.
- Với third-party assets, kiểm inventory vendor, CSP, SRI/version pinning, CORS/CORP/COEP/COOP đúng cơ chế; không bật `*` hoặc tắt headers toàn app để chữa một vendor.
- Với iframe dùng session cookie, **SameSite=Lax không bảo đảm cookie đến embedded third-party context**. Không hạ authentication hoặc CSRF để iframe “chạy”; thiết kế auth/session/capability riêng và luôn kiểm object-level authorization.
- Với payment webhook, có thể miễn Spring CSRF **chỉ đúng protocol POST endpoint**, nhưng chữ ký, chống replay và idempotency là bắt buộc.

Trên **Servlet/Spring MVC**, cấu hình `SecurityFilterChain`/`HttpSecurity` và kiểm thử `MockMvc`; trên **Reactive/WebFlux**, dùng `SecurityWebFilterChain`/`ServerHttpSecurity` và `WebTestClient`. Cả hai chỉ chứng minh server phát đúng headers và filters hoạt động; **browser E2E tại public origin** mới kiểm thêm clickjacking protection, sandbox, popup, SameSite và subresource enforcement.

Nguyên tắc của **SPRING_SECURITY_HTTP_PROTECTION** trong chương **Tích hợp ứng dụng** là: **chỉ mở quyền nhúng, tương tác và tải resource đúng chỗ cần, với quyền nhỏ nhất có thể kiểm chứng; không thay xác thực và phân quyền bằng chính sách trình duyệt**.

## Tài liệu tham khảo

- [Spring Security — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): X-Frame-Options, CSP, HSTS và response header configuration.
- [Spring Security — Reactive Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): Reactive header writers và SecurityWebFilterChain.
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token với browser session và unsafe requests.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CsrfWebFilter/WebSession.
- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS preflight, filter ordering và browser credentials.
- [MDN — Content-Security-Policy: frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors): ai được phép nhúng document.
- [MDN — Content-Security-Policy: frame-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-src): nguồn iframe được phép tải.
- [MDN — X-Frame-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Frame-Options): DENY, SAMEORIGIN và hạn chế ALLOW-FROM.
- [MDN — HTML iframe element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe): sandbox, allow, loading và referrerpolicy.
- [MDN — Window.postMessage](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage): targetOrigin, event.origin/source và security notes.
- [MDN — Window.open](https://developer.mozilla.org/en-US/docs/Web/API/Window/open): popup, opener và browsing context.
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): script-src, nonce/hash, reporting và directives.
- [MDN — Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity): integrity digest và crossorigin/CORS.
- [MDN — Cross-Origin-Opener-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy): COOP và opener/browsing context isolation.
- [MDN — Cross-Origin-Embedder-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy): COEP và embedded resources.
- [MDN — Cross-Origin-Resource-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Resource-Policy): CORP và no-cors resource loads.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): SameSite, Secure, Partitioned và cookie scope.
- [MDN — Storage Access API](https://developer.mozilla.org/en-US/docs/Web/API/Storage_Access_API): giới hạn truy cập storage trong third-party contexts.
- [MDN — Permissions Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy): kiểm quyền browser capabilities.
- [OWASP — Clickjacking Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html): frame-ancestors, XFO và UI redressing.
- [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): postMessage và web platform security.
- [OWASP — Third Party JavaScript Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html): supply-chain risk và vendor controls.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF, SameSite và defense-in-depth.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP safe methods và response semantics.
