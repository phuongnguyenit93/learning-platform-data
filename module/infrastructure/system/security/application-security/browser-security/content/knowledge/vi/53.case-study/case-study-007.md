# Case triển khai CSP: đưa Content Security Policy vào ứng dụng web đang vận hành

> **Chương:** Case study  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

Bài toán thực tế của case study là một ứng dụng SaaS đã vận hành nhiều năm, có trang HTML server-rendered, một số script inline, thư viện JavaScript cũ, API riêng, CDN, widget thanh toán và video nhúng. Đội phát triển muốn triển khai **Content Security Policy (CSP)** để giảm khả năng khai thác XSS và kiểm soát nơi trình duyệt được phép tải hoặc thực thi tài nguyên.

Nếu bật một policy nghiêm ngặt ngay lập tức, các luồng đang hoạt động có thể hỏng: script inline không chạy, widget không tải, API bị chặn hoặc style động biến mất. Nếu giữ policy quá rộng để tránh lỗi, CSP không còn nhiều giá trị bảo vệ. Case này triển khai theo từng giai đoạn: lập inventory, bật Report-Only, xử lý vi phạm, xây policy theo nonce/hash, kiểm thử, enforce theo canary, theo dõi và chuẩn bị rollback.

CSP là lớp phòng vệ phía browser. Nó làm giảm khả năng một injection trở thành XSS có thể thực thi, giới hạn nguồn tài nguyên và giúp phát hiện những hành vi không mong muốn. CSP **không thay thế** output encoding, safe DOM APIs, sanitization, authorization hoặc kiểm thử bảo mật. Một script hợp lệ được phép chạy vẫn có thể chứa bug hoặc bị compromise.

## Mục tiêu học tập

Sau case study, người học có thể:

1. Xác định tài nguyên và luồng nghiệp vụ cần đưa vào CSP.
2. Phân biệt Content-Security-Policy và Content-Security-Policy-Report-Only.
3. Thiết kế policy theo nguyên tắc default deny và allowlist tối thiểu.
4. Dùng nonce theo từng response hoặc hash cho inline code bất biến.
5. Hiểu vai trò và rủi ro của strict-dynamic.
6. Di chuyển inline event handler, eval và style inline sang mô hình an toàn.
7. Kiểm soát script bên thứ ba bằng nonce, SRI và quản lý dependency.
8. Cấu hình reporting, lọc nhiễu và tránh report storm.
9. Triển khai CSP ở application server, reverse proxy hoặc edge mà không lệch header với HTML.
10. Rollout theo môi trường, route và nhóm người dùng; có tiêu chí rollback.
11. Kiểm thử các directive quan trọng bằng browser DevTools và test tự động.
12. Đánh giá kết quả sau triển khai bằng số liệu và các tiêu chí bảo mật cụ thể.

## 1. Bối cảnh dự án

### 1.1 Hệ thống giả định

Ứng dụng có các thành phần:

| Thành phần | Origin ví dụ | Vai trò |
|---|---|---|
| Web application | https://app.example.com | HTML, JavaScript, CSS và session cookie |
| API | https://api.example.com | REST API và dữ liệu ứng dụng |
| Static CDN | https://static.example.net | Bundle JS, CSS, font và ảnh |
| Identity provider | https://login.example-idp.net | Đăng nhập OIDC/SAML redirect |
| Payment provider | https://checkout.payments.example | Hosted checkout hoặc payment frame |
| Video provider | https://player.video.example | Video nhúng |
| Error reporting | https://reports.example.com | Nhận CSP và client error reports |

Đây là các origin minh họa. Khi áp dụng vào hệ thống thật, phải thay bằng origin đã được xác minh từ Network panel, cấu hình deploy và hợp đồng tích hợp. Không đưa wildcard chỉ để làm hết lỗi Console.

### 1.2 Hiện trạng trước dự án

Ứng dụng đang có:

- Inline script trong một số template cũ.
- Inline event handler như onclick và onsubmit.
- Một số thư viện dùng eval hoặc Function constructor trong development.
- Style attribute do component cũ tạo ra.
- Script bên thứ ba được tải từ nhiều hostname.
- API request đi tới nhiều subdomain.
- Widget thanh toán và video được nhúng bằng iframe.
- Một số route có nội dung HTML do người dùng tạo.
- HTML được cache ở CDN trong khi nonce chưa được thiết kế.
- Logging chưa phân biệt vi phạm CSP do code ứng dụng và do extension/browser plugin.

Mục tiêu không phải chỉ làm cho CSP header xuất hiện. Mục tiêu là xây một policy có thể enforce mà không phá luồng nghiệp vụ, đồng thời giảm bề mặt XSS.

### 1.3 Phạm vi và giả định

Case này giả định:

- Ứng dụng chính chạy HTTPS.
- HTML được render ở server bằng Express và template EJS trong ví dụ.
- Static bundle được build trước khi deploy.
- API và các dịch vụ bên ngoài có origin xác định.
- Có quyền thay đổi response headers ở application server hoặc edge.
- Có thể triển khai canary theo route hoặc nhóm người dùng.
- Có một endpoint reporting nội bộ.

Nếu hệ thống dùng SPA thuần static, reverse proxy hoặc CDN edge rendering, giữ nguyên nguyên tắc nonce/header đồng bộ và chuyển ví dụ middleware sang lớp tạo HTML/response tương ứng.

## 2. Threat model và mục tiêu CSP

### 2.1 CSP bảo vệ điều gì?

CSP cho browser biết nguồn nào được phép thực thi script, tải style, ảnh, font, frame, worker, kết nối mạng và một số loại tài nguyên khác. Khi policy được enforce, browser chặn các hành vi vi phạm và có thể gửi report.

Trong case này, mục tiêu gồm:

- Chặn script inline không được cấp nonce/hash.
- Chặn inline event handler.
- Chặn eval và Function constructor nếu không có yêu cầu hợp lệ.
- Chỉ cho script được tải từ nguồn đã kiểm soát.
- Giới hạn API endpoint trong connect-src.
- Chỉ cho phép frame từ payment/video provider cần thiết.
- Chặn plugin/object không còn dùng.
- Chặn base URL bị thay đổi bởi nội dung injection.
- Chặn form gửi tới origin không mong muốn.
- Ngăn website khác nhúng ứng dụng nếu không có use case hợp lệ.
- Thu thập báo cáo vi phạm để phát hiện tài nguyên chưa được inventory.

### 2.2 CSP không giải quyết điều gì?

CSP không bảo đảm:

- Dữ liệu đầu vào đã được validate.
- HTML output đã được encode đúng context.
- Người dùng có quyền truy cập API.
- Script bên thứ ba không có bug hoặc không bị compromise.
- Cookie không thể bị replay.
- CSRF được ngăn hoàn toàn.
- Server không có lỗ hổng injection.
- Browser extension độc hại không thể can thiệp.
- Mọi browser cũ đều thực thi directive giống nhau.

CSP là defense in depth. Nếu một attacker có thể chạy script đã được nonce hoặc hash cho phép, CSP không thể phân biệt script tốt và hành vi độc hại bên trong script đó.

### 2.3 Security requirements

| ID | Yêu cầu | Cách xác minh |
|---|---|---|
| CSP-01 | Không có script inline không được cấp quyền | Console và report không còn vi phạm hợp lệ |
| CSP-02 | Không dùng unsafe-eval trong production | Bundle production không gọi eval/Function |
| CSP-03 | Script chỉ đến từ nguồn cần thiết | Inventory và policy review |
| CSP-04 | API chỉ kết nối endpoint cần thiết | Network panel và connect-src tests |
| CSP-05 | Frame chỉ nhúng provider đã duyệt | frame-src và kiểm thử luồng |
| CSP-06 | Ứng dụng không bị nhúng trái phép | frame-ancestors |
| CSP-07 | Nonce không bị tái sử dụng giữa response | Kiểm tra header và HTML nhiều request |
| CSP-08 | Report endpoint không bị abuse | Schema validation, size limit, rate limit |
| CSP-09 | CSP không làm hỏng login, payment và core journeys | E2E tests và canary |
| CSP-10 | Rollback không xóa các security headers khác | Kiểm thử config và response headers |

## 3. Giai đoạn 1 — Inventory tài nguyên trước khi viết policy

### 3.1 Thu thập từ nhiều nguồn

Không viết CSP chỉ dựa trên danh sách hostname mà developer nhớ. Lập inventory bằng:

- Browser DevTools Network khi chạy các user journey.
- Console violations từ CSP Report-Only.
- Source code search cho script, style, iframe, fetch, WebSocket và worker.
- Build manifest và dependency list.
- Reverse proxy/CDN logs ở mức metadata phù hợp.
- Tài liệu tích hợp của payment, identity, video và analytics.
- Kiểm thử các route hiếm: admin, upload, export, support, onboarding và error pages.

Chạy test trên profile sạch để tránh cache hoặc service worker che khuất request. Bao gồm cả trạng thái đăng nhập, chưa đăng nhập, user có quyền khác nhau và các luồng lỗi.

### 3.2 Resource inventory mẫu

| Resource | Destination | Origin cần thiết | Quyết định |
|---|---|---|---|
| App bundle | script | self/static CDN | Cho phép self và CDN đã duyệt |
| Inline bootstrap | script | document response | Chuyển sang nonce |
| Inline event handler | script attribute | document | Refactor thành addEventListener |
| App stylesheet | style | self/static CDN | Cho phép self/CDN |
| Dynamic style element | style | document | Chuyển sang nonce hoặc CSS class |
| User avatar | image | self/image CDN | Allowlist host hoặc proxy ảnh |
| API calls | connect | api.example.com | Chỉ cho phép API origin |
| WebSocket | connect | wss://api.example.com | Cho phép WSS endpoint cần thiết |
| Payment iframe | frame | checkout provider | Cho phép đúng origin |
| Video iframe | frame | video provider | Cho phép đúng origin |
| Worker | worker | self | Cho phép self nếu ứng dụng dùng |
| Font | font | self/static CDN | Allowlist nguồn font |
| Object/embed | object | none | Chặn nếu không còn nhu cầu |

### 3.3 Phân biệt resource load với redirect

Một request có thể redirect sang origin khác. CSP được áp dụng theo loại resource và quy tắc của directive tương ứng. Ghi nhận cả URL ban đầu và URL cuối cùng trong Network panel. Đừng chỉ thêm origin đầu tiên rồi bỏ qua redirect chain.

Đặc biệt kiểm tra:

- Login redirect qua identity provider.
- Payment redirect.
- CDN redirect sang storage host.
- Image proxy redirect.
- API redirect hoặc WebSocket handshake.

### 3.4 Không biến report thành allowlist tự động

Report chỉ là tín hiệu. Một violation có thể đến từ:

- Code ứng dụng chưa được inventory.
- Extension hoặc password manager.
- Browser plugin.
- Nội dung user-generated.
- Scanner hoặc test harness.
- Attacker thử injection.
- Một trang lỗi hoặc route ít được dùng.

Không tự động thêm mọi blocked-uri vào policy. Mỗi nguồn phải có owner, mục đích, dữ liệu được tải và quyết định chấp nhận rủi ro.

## 4. Giai đoạn 2 — Thiết kế policy theo nguyên tắc default deny

### 4.1 Bắt đầu bằng default-src 'none'

Một policy có thể bắt đầu từ:

~~~http
default-src 'none';
base-uri 'none';
object-src 'none';
frame-ancestors 'none';
form-action 'self';
script-src 'self';
style-src 'self';
img-src 'self';
font-src 'self';
connect-src 'self';
frame-src 'none';
worker-src 'self';
manifest-src 'self'
~~~

default-src là fallback cho nhiều fetch directive. Directive cụ thể sẽ ghi đè fallback của nó. Một số directive như base-uri, form-action và frame-ancestors không fallback theo default-src; cần khai báo rõ.

### 4.2 Policy đích cho ứng dụng giả định

Sau khi inventory và refactor, policy enforce mẫu có thể là:

~~~http
Content-Security-Policy:
  default-src 'none';
  base-uri 'none';
  object-src 'none';
  frame-ancestors 'none';
  form-action 'self';
  script-src 'nonce-{RANDOM_NONCE}' 'strict-dynamic' 'self' https://static.example.net;
  script-src-attr 'none';
  style-src 'self' 'nonce-{RANDOM_NONCE}' https://static.example.net;
  style-src-attr 'none';
  img-src 'self' https://images.example.net data: blob:;
  font-src 'self' https://static.example.net;
  connect-src 'self' https://api.example.com wss://api.example.com https://reports.example.com;
  frame-src https://checkout.payments.example https://player.video.example;
  worker-src 'self';
  manifest-src 'self';
  media-src 'self' https://media.example.net;
  upgrade-insecure-requests;
  require-trusted-types-for 'script';
  trusted-types app-html
~~~

Đây là policy minh họa. Chỉ giữ data:, blob:, media-src hoặc các origin bên ngoài khi inventory chứng minh ứng dụng cần. Nếu không dùng video, payment frame, WebSocket hoặc Trusted Types, bỏ directive/nguồn tương ứng.

Các dòng xuống hàng trong ví dụ chỉ để dễ đọc. Khi gửi qua HTTP, toàn bộ directive phải được nối thành một giá trị header duy nhất, phân tách bằng dấu chấm phẩy; không gửi newline bên trong header value.

### 4.3 Ý nghĩa của các directive quan trọng

| Directive | Mục đích | Quyết định trong case |
|---|---|---|
| default-src | Fallback cho fetch directives | none |
| script-src | Nguồn script được thực thi | Nonce, strict-dynamic và fallback tối thiểu |
| script-src-attr | Inline event handler attributes | none |
| style-src | Nguồn stylesheet và style element | self, nonce, CDN cần thiết |
| style-src-attr | Inline style attributes | none |
| img-src | Nguồn ảnh | self và image host |
| font-src | Nguồn font | self và static CDN |
| connect-src | fetch, XHR, WebSocket, EventSource và kết nối tương ứng | API/report origins |
| frame-src | Nguồn iframe mà trang được nhúng | Payment/video |
| frame-ancestors | Ai được phép nhúng trang này | none nếu không có embedding use case |
| form-action | Đích submit form | self hoặc endpoint được duyệt |
| base-uri | URL cơ sở của document | none |
| object-src | plugin/object/embed | none |
| worker-src | Worker, SharedWorker và ServiceWorker script sources | self |
| manifest-src | Web app manifest | self |
| media-src | Audio/video resource | self và media host |
| upgrade-insecure-requests | Yêu cầu browser nâng URL resource HTTP lên HTTPS khi phù hợp | Chỉ bật sau khi kiểm tra toàn bộ dependency |

### 4.4 frame-src và frame-ancestors không thay thế nhau

- frame-src kiểm soát trang hiện tại được phép tải iframe từ đâu.
- frame-ancestors kiểm soát origin nào được phép nhúng trang hiện tại.

Ví dụ, app có thể nhúng payment provider bằng frame-src nhưng vẫn không cho website khác nhúng chính app bằng frame-ancestors 'none'.

frame-ancestors phải được gửi qua HTTP response header. Không dựa vào meta CSP để thiết lập directive này.

### 4.5 form-action và base-uri phải được khai báo riêng

form-action giới hạn đích form submission. base-uri giới hạn URL cơ sở mà element base có thể đặt. default-src không thay thế hai directive này.

Nếu không có use case cho base element, base-uri 'none' là lựa chọn chặt chẽ. Nếu form chỉ submit về ứng dụng, dùng form-action 'self'.

### 4.6 Tránh wildcard và scheme rộng

Hạn chế:

~~~http
script-src *;
connect-src *;
img-src * data: blob:;
~~~

Wildcard có thể cho phép nhiều host ngoài dự kiến. Nếu buộc phải hỗ trợ CDN hoặc subdomain động, thiết kế một proxy hoặc origin tài nguyên chuyên dụng có allowlist rõ ràng thay vì mở mọi host.

Không dùng http: hoặc https: như một nguồn chung nếu có thể chỉ định hostname. Tránh thêm *.example.com nếu một vài host cụ thể là đủ.

## 5. Giai đoạn 3 — Chọn nonce hay hash cho script

### 5.1 Nonce theo từng response

Nonce là giá trị ngẫu nhiên khó đoán, được tạo cho mỗi response HTML. Cùng nonce phải xuất hiện trong CSP header và các script/style element được cho phép trong HTML response đó.

Ví dụ:

~~~http
Content-Security-Policy: script-src 'nonce-r4nd0mValue' 'strict-dynamic' 'self'
~~~

~~~html
<script nonce="r4nd0mValue">
  window.appConfig = { version: "2026.11" };
</script>
~~~

Nonce phải:

- Được tạo bằng CSPRNG.
- Đủ entropy; dùng ít nhất 128 bit ngẫu nhiên cho nonce.
- Mới cho mỗi response HTML.
- Không lấy từ query string, cookie hoặc input người dùng.
- Không dùng lại giữa user/session/request.
- Không xuất hiện trong log hoặc telemetry không cần thiết.
- Không bị CDN cache làm lệch header và HTML.

Nonce không phải secret lâu dài, nhưng phải khó đoán trong thời gian response có hiệu lực.

### 5.2 Hash cho inline code bất biến

Hash source phù hợp với inline script nhỏ, cố định và không thay đổi theo response:

~~~http
Content-Security-Policy: script-src 'sha256-{BASE64_HASH}'
~~~

Hash được tính trên đúng bytes của nội dung script. Thay đổi whitespace, ký tự xuống dòng hoặc nội dung đều làm hash khác. Khi deploy code mới, phải cập nhật hash đồng bộ.

Hash phù hợp khi:

- Inline script là static và ít thay đổi.
- Có build pipeline tính hash tự động.
- Không cần nhúng dữ liệu per-user vào inline script.
- Team có quy trình review khi hash thay đổi.

Không dùng hash cho script động chứa dữ liệu người dùng. Trước khi đưa dữ liệu vào DOM, vẫn cần encode/sanitize theo context.

### 5.3 Không trộn nonce và hash tùy tiện

Có thể dùng cả nonce và hash trong một directive, nhưng cần hiểu chính xác mỗi nguồn cho phép phần tử nào. Hãy duy trì policy có thể review và build pipeline kiểm chứng nguồn được cấp quyền.

Không thêm unsafe-inline để "tạm thời chạy được". Browser hỗ trợ nonce/hash sẽ bỏ qua unsafe-inline trong directive tương ứng khi nonce/hash có mặt, nhưng browser cũ có thể vẫn hiểu unsafe-inline và cho phép inline code. Vì vậy, không giữ nguồn yếu này trong production policy.

## 6. Giai đoạn 4 — Refactor ứng dụng cũ để tương thích CSP

### 6.1 Thay inline event handler bằng addEventListener

Trước:

~~~html
<button onclick="saveProfile()">Lưu</button>
<form onsubmit="return validateForm()">
~~~

Sau:

~~~html
<button id="save-profile" type="button">Lưu</button>
<form id="profile-form">
~~~

~~~js
document.querySelector("#save-profile")
  .addEventListener("click", saveProfile);

document.querySelector("#profile-form")
  .addEventListener("submit", event => {
    if (!validateForm()) {
      event.preventDefault();
    }
  });
~~~

script bên ngoài được tải từ nguồn cho phép hoặc script element có nonce. Không dùng eval để tái tạo event handler từ string.

### 6.2 Di chuyển inline script sang bundle

Trước:

~~~html
<script>
  initializeDashboard();
</script>
~~~

Sau:

~~~html
<script src="/assets/dashboard.js" defer></script>
~~~

Nếu inline bootstrap thực sự cần thiết, cấp nonce cho đúng script element. Không cấp nonce cho mọi script bằng cách tự động thay toàn bộ HTML mà không review nguồn tạo markup.

### 6.3 Loại bỏ eval và Function constructor

Các pattern cần tìm:

~~~js
eval(userExpression);
new Function("return " + source)();
setTimeout("refreshDashboard()", 1000);
~~~

Thay bằng function reference hoặc parser có grammar rõ ràng:

~~~js
setTimeout(refreshDashboard, 1000);
~~~

Nếu ứng dụng dùng template compiler hoặc development tool cần eval, tạo build production không dùng đường code đó. Không thêm unsafe-eval vào policy production chỉ để hỗ trợ development server.

### 6.4 Xử lý style attribute

Trước:

~~~html
<div style="display:none" id="panel">Nội dung</div>
~~~

Sau:

~~~html
<div class="panel-hidden" id="panel">Nội dung</div>
~~~

~~~css
.panel-hidden {
  display: none;
}
~~~

~~~js
document.querySelector("#panel").classList.remove("panel-hidden");
~~~

style-src-attr 'none' giúp chặn inline style attribute. Nếu component framework sinh style attribute, cấu hình lại renderer hoặc thay bằng class/CSS variable có kiểm soát.

### 6.5 CSS-in-JS và style element động

Một số CSS-in-JS runtime tạo style element trong document. Có thể cấu hình thư viện để gắn nonce cho style element. Nonce phải đến từ response hiện tại và không được hardcode trong bundle.

Không giả định nonce trên script tự động cấp quyền cho style element. script-src và style-src là các directive riêng.

### 6.6 HTML do người dùng tạo

Nếu sản phẩm hỗ trợ rich text:

- Sanitize bằng thư viện chuyên dụng với allowlist element/attribute.
- Chặn script, event handler và URL scheme nguy hiểm.
- Render trong vùng và context phù hợp.
- Không dùng CSP như sanitizer.
- Cân nhắc origin riêng hoặc sandbox cho nội dung có độ tin cậy thấp.
- Kiểm tra link, image và embedded resource theo policy.

CSP có thể chặn một số payload thực thi nhưng không biến HTML chưa sanitize thành dữ liệu an toàn.

## 7. Giai đoạn 5 — Script loader, strict-dynamic và third-party

### 7.1 strict-dynamic hoạt động như thế nào?

Với browser hỗ trợ CSP3, strict-dynamic cho phép trust từ script element có nonce hoặc hash lan sang script được script đáng tin đó tải động theo quy tắc CSP. Khi strict-dynamic được hỗ trợ, host allowlist và scheme source trong script-src có thể bị bỏ qua cho quyết định tải script theo cơ chế này.

Ví dụ:

~~~http
Content-Security-Policy: script-src 'nonce-{RANDOM_NONCE}' 'strict-dynamic' 'self' https://static.example.net
~~~

Các browser cũ không hỗ trợ strict-dynamic có thể dùng 'self' và host source làm fallback. Vì vậy, policy cần kiểm tra theo browser support mục tiêu.

### 7.2 Root loader trở thành thành phần tin cậy

Nếu một script có nonce tạo script element từ URL do attacker kiểm soát, strict-dynamic có thể mở rộng trust tới script độc hại. Loader phải:

- Chỉ nhận URL từ allowlist cấu hình.
- Không nối input người dùng trực tiếp vào script.src.
- Không nhận module name tùy ý từ query string.
- Xác minh dependency và version.
- Dùng SRI khi phù hợp.
- Có owner và quy trình review cho mọi script được tải động.

### 7.3 Ví dụ loader có allowlist

~~~js
const approvedModules = new Map([
  ["charts", "/assets/charts.js"],
  ["editor", "/assets/editor.js"]
]);

function loadApprovedModule(name) {
  const source = approvedModules.get(name);

  if (!source) {
    throw new TypeError("Module không được phép");
  }

  const script = document.createElement("script");
  script.src = source;
  script.async = true;

  document.head.append(script);
}
~~~

Không truyền tên module tùy ý từ server response hoặc URL nếu chưa validate. Nếu dùng dynamic import, áp dụng cùng nguyên tắc allowlist và review dependency graph.

### 7.4 Subresource Integrity cho script tĩnh bên thứ ba

Ví dụ:

~~~html
<script
  nonce="RESPONSE_NONCE"
  src="https://static.example.net/vendor/library-4.2.1.min.js"
  integrity="sha384-BASE64_HASH_FROM_BUILD"
  crossorigin="anonymous"></script>
~~~

SRI kiểm tra bytes tải về có khớp hash đã khai báo không. Với cross-origin resource, server cần CORS response phù hợp để SRI hoạt động. Trong policy có strict-dynamic, script tĩnh này cũng cần nonce/hash hoặc phải được một script root đáng tin tải động; host allowlist có thể bị bỏ qua ở browser hỗ trợ strict-dynamic.

SRI phù hợp với asset version cố định. Nó không thay thế CSP, dependency review hoặc quy trình cập nhật hash. Nếu attacker kiểm soát cả source code và HTML deploy, họ có thể thay cả script lẫn integrity hash; bảo vệ pipeline phát hành vẫn cần thiết.

### 7.5 Kiểm soát tag manager và analytics

Tag manager có thể tải script động từ nhiều nguồn. Cần quyết định:

- Có thực sự cần tag manager trên mọi route không?
- Ai có quyền publish tag?
- Có approval và audit log không?
- Có thể giới hạn tag manager vào route ít nhạy cảm không?
- Script được tải có SRI hoặc version pin không?
- Có cách tắt nhanh khi provider bị compromise không?

Một nonce cấp cho tag manager có thể biến nó thành root of trust. Chỉ cấp nonce sau khi đánh giá quyền publish và khả năng kiểm soát tag.

## 8. Giai đoạn 6 — Kiểm soát frame, form và kết nối

### 8.1 Payment iframe

Ví dụ policy:

~~~http
frame-src https://checkout.payments.example;
form-action 'self' https://checkout.payments.example;
~~~

Chỉ thêm form destination nếu luồng thanh toán thực sự submit form tới provider. Nếu payment flow redirect top-level, kiểm thử redirect và form submission riêng.

Không nhầm frame-src với frame-ancestors. Cũng không nhầm CSP với Permissions Policy của iframe.

### 8.2 Video iframe

~~~http
frame-src https://player.video.example;
~~~

Video provider có thể cần thêm connect-src, img-src hoặc media-src tùy cách player hoạt động. Lập inventory từ Network và tài liệu provider, chỉ thêm directive cần thiết.

### 8.3 API, WebSocket và EventSource

~~~http
connect-src 'self' https://api.example.com wss://api.example.com https://reports.example.com;
~~~

connect-src kiểm soát các kết nối script-initiated như fetch, XHR, WebSocket và EventSource. Một API mới hoặc WebSocket endpoint chưa được khai báo có thể bị browser chặn dù CORS phía server cho phép.

CSP và CORS là hai kiểm tra độc lập:

- CSP quyết định trang có được phép khởi tạo kết nối tới đích.
- CORS quyết định script có được đọc response cross-origin theo chính sách server.
- Request có thể bị CSP chặn trước khi đến server; hoặc request đến server nhưng response không đọc được do CORS.

### 8.4 Form submission

form-action giới hạn đích form submit. Không dựa vào default-src để thay thế. Nếu ứng dụng dùng SSO hoặc payment POST, thêm chính xác endpoint cần thiết và kiểm thử cả lỗi lẫn thành công.

### 8.5 frame-ancestors cho chống clickjacking

Nếu ứng dụng không cần được nhúng:

~~~http
frame-ancestors 'none';
~~~

Nếu chỉ cho phép same-origin:

~~~http
frame-ancestors 'self';
~~~

Nếu cần một portal cụ thể, liệt kê origin chính xác. frame-ancestors là header-level directive và phải được cấu hình tại response HTML. Có thể duy trì X-Frame-Options cho browser cũ theo yêu cầu tương thích, nhưng không dùng hai cơ chế với giá trị mâu thuẫn.

## 9. Giai đoạn 7 — Trusted Types và DOM XSS

### 9.1 Vì sao CSP script-src chưa đủ?

script-src giới hạn nơi browser tải/thực thi script, nhưng không đảm bảo ứng dụng không đưa chuỗi không tin cậy vào innerHTML hoặc các injection sink khác. Một DOM XSS có thể xảy ra qua các sink được phép nếu ứng dụng xử lý dữ liệu sai.

### 9.2 Bật Trusted Types theo giai đoạn

Sau khi inventory DOM sinks và thư viện tương thích, có thể thêm:

~~~http
require-trusted-types-for 'script';
trusted-types app-html;
~~~

Directive này yêu cầu các sink được hỗ trợ nhận Trusted Type phù hợp thay vì string tùy ý. Tên policy được phép có thể giới hạn bằng trusted-types.

### 9.3 Policy phải sanitize thật sự

Ví dụ minh họa với DOMPurify:

~~~js
const appHtmlPolicy = trustedTypes.createPolicy("app-html", {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true }
    });
  }
});
~~~

~~~js
target.innerHTML = appHtmlPolicy.createHTML(untrustedHtml);
~~~

Trusted Types không tự sanitize. Nếu policy trả nguyên input, hoặc sanitizer được cấu hình quá rộng, bảo vệ bị mất. Ưu tiên textContent khi không cần rich HTML.

### 9.4 Kiểm thử browser support

Trusted Types enforcement chưa đồng đều ở mọi browser. Có thể triển khai progressive enhancement:

- Browser hỗ trợ enforcement: bật directive và sửa violation.
- Browser chưa hỗ trợ: vẫn dùng safe sink và sanitizer trong code.
- Không dựa vào Trusted Types như lớp bảo vệ duy nhất.
- Kiểm thử bundle và third-party library trước khi enforce.

## 10. Giai đoạn 8 — Reporting và triage

### 10.1 Report-Only không chặn resource

Header:

~~~http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; report-uri /csp-report
~~~

Report-Only cho browser đánh giá policy và gửi report khi vi phạm, nhưng không chặn tài nguyên theo policy đó. Nó phù hợp để quan sát trước khi enforce.

Không gửi hai header policy khác nhau rồi giả định policy Report-Only ghi đè policy enforce. Nếu response có Content-Security-Policy và Content-Security-Policy-Report-Only, policy enforce vẫn chặn theo quy tắc của nó; Report-Only chỉ bổ sung báo cáo.

### 10.2 Reporting API và report-uri fallback

Có thể cấu hình endpoint hiện đại:

~~~http
Reporting-Endpoints: csp-endpoint="https://reports.example.com/csp"
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; report-to csp-endpoint; report-uri /csp-report
~~~

report-to sử dụng reporting endpoint group. report-uri là cơ chế cũ nhưng vẫn có ích làm fallback cho browser chưa hỗ trợ Reporting API tương ứng. Kiểm tra browser matrix trước khi phụ thuộc vào một cơ chế duy nhất.

### 10.3 Report không phải log đáng tin tuyệt đối

Report do browser gửi nhưng dữ liệu bên trong vẫn cần xem là input không tin cậy. Attacker có thể tạo nhiều violation, gửi dữ liệu lớn hoặc cố đưa chuỗi đánh lừa vào dashboard.

Endpoint cần:

- Giới hạn body size.
- Rate limit và sampling.
- Validate content type và schema.
- Giới hạn độ dài blocked-uri, document-uri, source-file và line number.
- Không render report bằng innerHTML.
- Không tự động thêm blocked-uri vào allowlist.
- Loại bỏ query/fragment nhạy cảm trước khi lưu nếu có thể.
- Có retention và access control.

### 10.4 Triage report theo nguồn

| Nhóm report | Cách xử lý |
|---|---|
| Inline script do app tạo | Refactor hoặc cấp nonce/hash đúng phần tử |
| Inline event handler | Chuyển sang addEventListener |
| Script từ CDN đã duyệt | Kiểm tra URL/redirect, SRI và directive |
| Script từ hostname chưa biết | Xác minh owner, dependency và lý do tải |
| Extension/browser plugin | Đánh dấu noise, không thêm vào policy |
| Injection attempt | Ghi nhận security signal, kiểm tra route và input source |
| Report thiếu thông tin | Đối chiếu browser/version và reproduce thủ công |

### 10.5 Phân biệt report từ code lỗi và attack

Một blocked-uri lạ có thể là injection attempt, extension hoặc code hợp lệ chưa được inventory. Kết hợp:

- Route và user journey.
- Release/build identifier.
- Browser family/version.
- Thời điểm và tần suất.
- Source file/line nếu có.
- Request ID hoặc correlation ID.
- Các sự kiện XSS/WAF khác.

Không kết luận có XSS chỉ từ một report. Cũng không bỏ qua report lặp lại trên một route nhạy cảm.

## 11. Giai đoạn 9 — Triển khai ở application server

### 11.1 Express middleware tạo nonce theo response

Ví dụ dùng Node.js và Express:

~~~js
import crypto from "node:crypto";

function createCspMiddleware() {
  return function cspMiddleware(req, res, next) {
    const nonce = crypto.randomBytes(16).toString("base64");

    res.locals.cspNonce = nonce;
    res.setHeader("Cache-Control", "no-store");

    const policy = [
      "default-src 'none'",
      "base-uri 'none'",
      "object-src 'none'",
      "frame-ancestors 'none'",
      "form-action 'self'",
      "script-src 'nonce-" + nonce + "' 'strict-dynamic' 'self' https://static.example.net",
      "script-src-attr 'none'",
      "style-src 'self' 'nonce-" + nonce + "' https://static.example.net",
      "style-src-attr 'none'",
      "img-src 'self' https://images.example.net data:",
      "font-src 'self' https://static.example.net",
      "connect-src 'self' https://api.example.com wss://api.example.com",
      "frame-src https://checkout.payments.example https://player.video.example",
      "worker-src 'self'",
      "manifest-src 'self'",
      "media-src 'self' https://media.example.net",
      "upgrade-insecure-requests"
    ].join("; ");

    res.setHeader("Content-Security-Policy-Report-Only", policy);
    next();
  };
}
~~~

Ở giai đoạn đầu, middleware đặt Report-Only. Khi đã đủ điều kiện enforce, đổi tên header thành Content-Security-Policy qua release/configuration có kiểm soát. Không gửi đồng thời policy enforce cũ và policy Report-Only mới rồi giả định chúng thay thế nhau.

### 11.2 Gắn nonce vào template

Ví dụ EJS:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Dashboard</title>
  <script nonce="<%= cspNonce %>">
    window.appConfig = { version: "2026.11" };
  </script>
  <script nonce="<%= cspNonce %>" src="/assets/bootstrap.js" defer></script>
</head>
<body>
  <main id="app"></main>
</body>
</html>
~~~

EJS escape giá trị theo mặc định với cú pháp <%= ... %>. Không dùng cú pháp unescaped cho dữ liệu người dùng. Nonce chỉ nên đến từ middleware server, không lấy từ request parameter.

### 11.3 Không cache HTML chứa nonce theo cách dùng chung

Nếu CDN cache HTML và CSP header như một cặp tĩnh, nonce có thể bị tái sử dụng cho nhiều người dùng hoặc bị lệch giữa header và body. Các lựa chọn:

- Không cache HTML chứa nonce ở shared cache; dùng Cache-Control: no-store hoặc private theo thiết kế.
- Dùng edge middleware tạo nonce mới và cập nhật cả header lẫn markup cho từng response.
- Dùng hash-based policy cho trang static với inline code bất biến.
- Tách dữ liệu động ra API và giữ HTML shell không có inline script.

Nếu CDN biến đổi HTML, phải kiểm thử response cuối cùng mà browser nhận, không chỉ response từ origin server.

### 11.4 Tránh ghi nonce vào log

Không ghi toàn bộ CSP header nếu log được chia sẻ rộng hoặc lưu lâu. Nếu cần debug, ghi policy version và release ID; không cần lưu nonce. Nonce là giá trị per-response và không nên xuất hiện trong telemetry.

### 11.5 Reporting endpoint middleware

Ví dụ route Express có giới hạn kích thước:

~~~js
app.post(
  "/csp-report",
  express.text({
    type: ["application/csp-report", "application/reports+json"],
    limit: "16kb"
  }),
  (req, res) => {
    const raw = typeof req.body === "string" ? req.body : "";

    let parsed;

    try {
      parsed = JSON.parse(raw);
    } catch {
      return res.sendStatus(400);
    }

    // Legacy report-uri sends an object; Reporting API sends an array.
    // Validate each item, truncate fields, redact URL query/hash,
    // rate-limit and store as untrusted telemetry.
    const records = Array.isArray(parsed) ? parsed : [parsed];

    for (const record of records) {
      if (
        record === null ||
        typeof record !== "object" ||
        Array.isArray(record)
      ) {
        continue;
      }

      recordCspReportSafely(record);
    }

    return res.sendStatus(204);
  }
);
~~~

Trong production, xác nhận parser tương thích định dạng legacy và Reporting API của browser mục tiêu. Không ghi raw report không giới hạn và không đưa trực tiếp report fields vào HTML dashboard.

## 12. Giai đoạn 10 — Triển khai ở reverse proxy hoặc edge

### 12.1 Nginx static policy

Nếu HTML static không dùng nonce, có thể đặt policy hash-based hoặc không có inline code:

~~~nginx
add_header Content-Security-Policy "default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self' https://static.example.net; style-src 'self'; img-src 'self' https://images.example.net; connect-src 'self' https://api.example.com; font-src 'self' https://static.example.net" always;
~~~

Không dùng cấu hình này nếu trang thực tế còn inline script/style cần nonce/hash. Header phải được kiểm tra trên mọi status code và route cần bảo vệ.

### 12.2 Tránh header trùng hoặc bị ghi đè

Một số tầng có thể cùng thêm CSP:

- Application server.
- Reverse proxy.
- CDN.
- API gateway.
- Ingress controller.

Nhiều Content-Security-Policy enforce headers thường được áp dụng đồng thời theo hướng hạn chế giao nhau, không phải policy sau ghi đè policy trước. Một header thứ hai có thể làm trang bị chặn nhiều hơn dự kiến. Chọn một nơi quản lý policy chính hoặc có quy tắc hợp nhất rõ ràng.

Kiểm tra response headers cuối cùng trong browser Network panel. Không chỉ kiểm tra file config.

### 12.3 Meta CSP chỉ dành cho trường hợp hạn chế

Meta CSP có thể hữu ích với một số trang static đơn giản, nhưng không thay thế response header đầy đủ. Một số directive không được hỗ trợ trong meta, trong đó có frame-ancestors, report-uri và sandbox. Với ứng dụng production, ưu tiên HTTP response header để kiểm soát đầy đủ và nhất quán.

## 13. Giai đoạn 11 — Rollout từ Report-Only sang Enforce

### 13.1 Kế hoạch rollout mẫu

| Giai đoạn | Phạm vi | Hoạt động | Điều kiện chuyển tiếp |
|---|---|---|---|
| 0. Inventory | Staging và production quan sát | Thu thập resource graph, không đổi behavior | Owner và purpose của nguồn đã biết |
| 1. Report-Only | Staging | Bật policy mục tiêu và report endpoint | Core journeys chạy được, report đã phân loại |
| 2. Report-Only | 5% production traffic | Theo dõi vi phạm và lỗi UI | Không có violation hợp lệ chưa xử lý ở route trọng yếu |
| 3. Enforce canary | Internal users/1-5% traffic | Bật policy cho nhóm nhỏ | Login, payment, API, upload, admin smoke tests pass |
| 4. Enforce rộng | 25%, 50%, 100% | Mở rộng theo từng đợt | Error rate và conversion không tăng bất thường |
| 5. Hardening | Toàn bộ production | Loại bỏ nguồn fallback không cần, cân nhắc Trusted Types | Policy được review và có owner |

Các tỷ lệ chỉ là ví dụ. Chọn canary theo năng lực rollout, traffic và mức độ quan trọng của ứng dụng.

### 13.2 Tiêu chí trước khi enforce

- Không còn inline handler hợp lệ chưa refactor.
- Không còn eval/unsafe-eval trong production bundle.
- Tất cả script/style inline cần thiết có nonce/hash.
- Third-party script có owner và mục đích.
- API, WebSocket, iframe và worker được inventory.
- Report endpoint đã kiểm thử rate limit và schema.
- Core E2E tests pass.
- Có rollback config và người trực vận hành.
- Header thực tế không bị proxy/CDN ghi đè ngoài ý muốn.
- Nonce mới cho mỗi response và header/HTML khớp.

### 13.3 Theo dõi trong canary

Theo dõi:

- CSP violation rate theo directive, route, browser và release.
- JavaScript error rate.
- Failed resource loads.
- Login success rate.
- Payment completion rate.
- API failure rate.
- Conversion và task completion.
- Report endpoint volume và 4xx/5xx.
- Số report từ nguồn chưa phân loại.
- Số request bị chặn có liên quan core journey.

Không dùng tổng số report đơn lẻ làm tiêu chí duy nhất; một extension có thể tạo nhiều noise, trong khi một violation ở payment route có thể rất quan trọng dù số lượng nhỏ.

### 13.4 Điều kiện rollback

Rollback hoặc tạm dừng rollout nếu:

- Login hoặc payment bị hỏng trên browser được hỗ trợ.
- Một route trọng yếu bị chặn resource hợp lệ.
- CSP header sai nonce hoặc nonce bị cache/reuse.
- Policy chặn API/worker thiết yếu.
- Report volume tạo tải hoặc làm lộ dữ liệu.
- Nhiều lỗi runtime mới xuất hiện trùng thời điểm enforce.

Rollback có thể quay về Report-Only trong thời gian khắc phục. Không xóa CSP hoàn toàn nếu có thể giữ policy an toàn đang hoạt động; không rollback các header độc lập như HSTS hoặc nosniff nếu không liên quan.

## 14. Kiểm thử và xác minh bằng DevTools

### 14.1 Kiểm tra response header

Trong DevTools → Network → chọn document:

- Xác nhận có đúng một policy enforce dự kiến.
- Xác nhận policy Report-Only nếu đang rollout.
- Xác nhận Reporting-Endpoints nếu dùng report-to.
- Xác nhận response sau redirect và cache.
- Xác nhận HTML có nonce trùng với header.
- Xác nhận nonce thay đổi giữa hai response độc lập.

Dùng curl để kiểm tra header:

~~~bash
curl -sSI https://app.example.com/
~~~

curl chỉ xem header; nó không thực thi CSP. Browser mới là nơi xác minh behavior thực tế.

### 14.2 Kiểm tra nonce per-response

Tải cùng route hai lần, lấy nonce từ header và HTML. Kết quả mong đợi:

- Nonce trong header request A khớp script element của HTML A.
- Nonce trong header request B khớp HTML B.
- Nonce A khác nonce B.
- Cache không trả HTML A cùng header B hoặc ngược lại.
- Nonce không xuất hiện trong URL hoặc log.

### 14.3 Kiểm tra inline script bị chặn

Trong staging, thêm một script inline không nonce vào fixture test. Khi enforce:

- Browser ghi CSP violation.
- Script không chạy.
- Script có nonce hợp lệ vẫn chạy.
- Inline event handler bị chặn khi script-src-attr 'none' hoặc policy tương ứng có hiệu lực.

Chỉ thực hiện trên trang test được kiểm soát. Không đưa payload thực thi vào production user input.

### 14.4 Kiểm tra connect-src và frame-src

- Gọi API origin đã duyệt: request được phép tới bước CORS/server.
- Gọi endpoint không nằm allowlist: browser chặn do CSP.
- Nhúng payment/video origin đã duyệt: frame tải được.
- Nhúng origin lạ: browser chặn theo frame-src.
- Thử WebSocket tới WSS endpoint đúng và sai.
- Kiểm tra Network và Console để phân biệt CSP block với CORS failure.

### 14.5 Kiểm tra frame-ancestors

Từ một test page trên origin khác, thử nhúng app. Nếu frame-ancestors 'none', browser phải chặn việc nhúng. Kiểm tra Console và response header của document được nhúng.

Không dùng meta CSP để test frame-ancestors. Phải cấu hình response header.

### 14.6 Kiểm tra nhiều policy

Nếu app server và proxy cùng gửi CSP, quan sát tất cả response headers. Policy enforce bổ sung thường làm hạn chế hơn. Một nguồn có thể tải được theo policy A nhưng bị policy B chặn.

Tìm vị trí phát header ở từng tầng và hợp nhất về một policy có owner.

## 15. Lab: Report-Only và Enforce trên localhost

Lab Node.js không cần package ngoài. Nó tạo response HTML có nonce, một inline script cố ý không có nonce, một inline event handler và script external same-origin. Chọn mode report-only để quan sát report mà không chặn, sau đó chuyển enforce để thấy browser chặn phần không được cấp quyền.

Lab không chứa payload lấy cookie hoặc dữ liệu thật. Chỉ dùng trên localhost.

### 15.1 Cấu trúc thư mục

~~~text
csp-deployment-lab/
  server.mjs
  public/
    app.js
~~~

### 15.2 Tạo server.mjs

~~~js
import { createServer } from "node:http";
import { randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";

const appOrigin = "http://localhost:3000";
const appJs = new URL("./public/app.js", import.meta.url);

function send(res, status, contentType, body, headers = {}) {
  res.writeHead(status, {
    "Content-Type": contentType,
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    ...headers
  });
  res.end(body);
}

async function readBody(req, maxBytes = 16 * 1024) {
  const chunks = [];
  let size = 0;
  let tooLarge = false;

  for await (const chunk of req) {
    size += chunk.length;

    if (size > maxBytes) {
      tooLarge = true;
      continue;
    }

    if (!tooLarge) chunks.push(chunk);
  }

  return tooLarge ? null : Buffer.concat(chunks).toString("utf8");
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || "/", appOrigin);

  if (req.method === "POST" && url.pathname === "/csp-report") {
    const contentType = String(req.headers["content-type"] || "").toLowerCase();

    if (!contentType.startsWith("application/csp-report") &&
        !contentType.startsWith("application/json")) {
      return send(res, 415, "text/plain; charset=utf-8", "Unsupported content type");
    }

    let raw;

    try {
      raw = await readBody(req);
    } catch {
      return send(res, 413, "text/plain; charset=utf-8", "Too large");
    }

    if (raw === null) {
      return send(res, 413, "text/plain; charset=utf-8", "Too large");
    }

    let parsed;

    try {
      parsed = JSON.parse(raw);
    } catch {
      return send(res, 400, "text/plain; charset=utf-8", "Invalid JSON");
    }

    if (
      parsed === null ||
      typeof parsed !== "object" ||
      Array.isArray(parsed)
    ) {
      return send(res, 400, "text/plain; charset=utf-8", "Invalid report shape");
    }

    // Report payload is untrusted: log only bounded metadata.
    const report = parsed["csp-report"] || parsed;
    const safe = {
      documentUri: typeof report["document-uri"] === "string"
        ? report["document-uri"].slice(0, 200)
        : null,
      violatedDirective: typeof report["violated-directive"] === "string"
        ? report["violated-directive"].slice(0, 100)
        : null,
      blockedUri: typeof report["blocked-uri"] === "string"
        ? report["blocked-uri"].slice(0, 200)
        : null
    };

    console.log("[csp-report]", JSON.stringify(safe));
    return send(res, 204, "text/plain; charset=utf-8", "");
  }

  if (req.method !== "GET") {
    return send(res, 405, "text/plain; charset=utf-8", "Method not allowed", {
      "Allow": "GET"
    });
  }

  if (url.pathname === "/app.js") {
    try {
      const body = await readFile(appJs);
      return send(
        res,
        200,
        "text/javascript; charset=utf-8",
        body
      );
    } catch {
      return send(res, 500, "text/plain; charset=utf-8", "Cannot read app.js");
    }
  }

  if (url.pathname !== "/") {
    return send(res, 404, "text/plain; charset=utf-8", "Not found");
  }

  const nonce = randomBytes(16).toString("base64");
  const mode = url.searchParams.get("mode") === "enforce"
    ? "enforce"
    : "report-only";

  const policy = [
    "default-src 'none'",
    "base-uri 'none'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "script-src 'self' 'nonce-" + nonce + "'",
    "script-src-attr 'none'",
    "style-src 'self'",
    "img-src 'self'",
    "connect-src 'self'"
  ].join("; ");

  const headerName = mode === "enforce"
    ? "Content-Security-Policy"
    : "Content-Security-Policy-Report-Only";

  const html = [
    "<!doctype html>",
    '<html lang="vi">',
    "<head>",
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    "<title>CSP deployment lab</title>",
    '<script nonce="' + nonce + '" src="/app.js" defer></script>',
    "</head>",
    "<body>",
    "<h1>CSP deployment lab</h1>",
    '<p id="status">External script chưa chạy.</p>',
    '<button id="safe-button" type="button">Event listener hợp lệ</button>',
    '<button id="inline-button" onclick="document.body.dataset.inline = \'ran\'">Inline handler bị policy chặn</button>',
    "<script>document.body.dataset.unsafeInline = 'ran';</script>",
    '<script nonce="' + nonce + '">document.body.dataset.nonceScript = "ran";</script>',
    "</body>",
    "</html>"
  ].join("\n");

  return send(res, 200, "text/html; charset=utf-8", html, {
    [headerName]: policy + "; report-uri /csp-report"
  });
});

server.listen(3000, "localhost", () => {
  console.log("CSP lab: http://localhost:3000/?mode=report-only");
});
~~~

### 15.3 Tạo public/app.js

~~~js
const status = document.querySelector("#status");

status.textContent = "External script đã chạy.";

document.querySelector("#safe-button").addEventListener("click", () => {
  status.textContent = "Event listener từ script được phép đã chạy.";
});

document.querySelector("#inline-button").addEventListener("click", () => {
  status.textContent =
    "External listener chạy; inline onclick vẫn bị CSP enforce chặn.";
});
~~~

### 15.4 Chạy lab ở Report-Only

Từ thư mục csp-deployment-lab:

~~~bash
node server.mjs
~~~

Mở:

~~~text
http://localhost:3000/?mode=report-only
~~~

Quan sát:

- External app.js chạy.
- Inline script không nonce vẫn chạy vì policy đang ở Report-Only.
- Inline onclick vẫn hoạt động nhưng browser gửi CSP report.
- Inline script có nonce chạy.
- Terminal ghi metadata report đã giới hạn.

Report-Only không chặn hành vi. Nó chỉ cho biết những gì sẽ bị chặn nếu cùng policy được enforce.

### 15.5 Chuyển sang Enforce

Mở:

~~~text
http://localhost:3000/?mode=enforce
~~~

Kết quả mong đợi:

- External app.js chạy vì 'self' được phép.
- Inline script không nonce bị chặn.
- Inline onclick bị chặn do script-src-attr 'none'.
- Inline script có nonce chạy.
- Browser ghi violation trong Console; report endpoint có thể nhận report tùy browser hỗ trợ report-uri.

Bấm hai nút. Nút safe hoạt động. Nút inline vẫn có external event listener để cập nhật status, nhưng thuộc tính onclick bị chặn.

### 15.6 Kiểm tra nonce thay đổi

Reload hai lần. Trong DevTools:

1. Xem response CSP header.
2. Xem nonce của script element được cấp quyền.
3. So sánh giữa hai response.
4. Xác nhận header và HTML của cùng response khớp nhau.
5. Xác nhận nonce khác nhau giữa hai lần reload.

### 15.7 Dọn lab

Dừng server bằng Ctrl+C. Không đưa policy demo nguyên xi vào production; hãy thay bằng resource inventory và rollout thực tế.

## 16. Chẩn đoán lỗi triển khai CSP

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Trang trắng sau enforce | Script bootstrap bị chặn | Kiểm tra script-src, nonce và bundle |
| Inline script chạy ở Report-Only | Đây là behavior dự kiến | Chuyển sang Enforce sau khi triage |
| Nonce script vẫn bị chặn | Nonce header và HTML lệch hoặc cache | Kiểm tra cùng response, CDN và template |
| Nonce giống nhau giữa nhiều response | Shared cache hoặc nonce generation sai | Tạo nonce per response hoặc dùng hash |
| Widget thanh toán không tải | frame-src thiếu provider hoặc redirect origin | Inventory frame/network chain và thêm origin chính xác |
| API bị chặn trước khi gửi | connect-src thiếu endpoint | Kiểm tra CSP Console; không sửa CORS thay cho CSP |
| API gửi được nhưng JS không đọc response | CORS server chưa cho phép | Kiểm tra Access-Control-Allow-Origin |
| Font bị chặn | font-src thiếu CDN | Thêm đúng font origin sau inventory |
| Style biến mất | style-src/style-src-attr chặn inline style | Refactor sang CSS class hoặc nonce style element |
| CSS-in-JS lỗi | Style element động thiếu nonce | Cấu hình thư viện nhận nonce theo response |
| Script bên thứ ba không chạy | CSP/SRI/CORS hoặc redirect | Kiểm tra cả ba lớp và version asset |
| strict-dynamic không hoạt động như kỳ vọng | Browser không hỗ trợ hoặc loader không có nonce/hash | Kiểm tra CSP3 support và root script |
| frame-ancestors không có tác dụng | Đặt trong meta CSP hoặc header bị ghi đè | Gửi HTTP response header |
| Report endpoint quá tải | Report storm, extension hoặc scanner | Rate limit, sampling, grouping và lọc noise |
| Nhiều CSP headers cùng tồn tại | App/proxy/CDN cùng thêm policy | Hợp nhất policy và kiểm tra response cuối |
| Development hoạt động, production lỗi | Dev server cần eval/HMR hoặc origin khác | Build production và inventory đúng environment |

## 17. Ma trận kiểm thử và tiêu chí nghiệm thu

| ID | Kiểm thử | Kết quả mong đợi |
|---|---|---|
| CSP-T01 | Header Report-Only được gửi | Browser báo violation nhưng không chặn |
| CSP-T02 | Header Enforce được gửi | Violation bị chặn |
| CSP-T03 | Nonce khớp giữa header và HTML | Script nonce chạy |
| CSP-T04 | Nonce khác giữa hai response | Không tái sử dụng nonce |
| CSP-T05 | Inline script không nonce | Bị chặn khi enforce |
| CSP-T06 | Inline event handler | Bị chặn |
| CSP-T07 | External script self | Chạy |
| CSP-T08 | Script từ origin ngoài allowlist | Bị chặn nếu không có trust/nonce phù hợp |
| CSP-T09 | Dynamic loader với allowlist | Chỉ tải module đã duyệt |
| CSP-T10 | eval/Function trong production | Không có đường thực thi |
| CSP-T11 | Style attribute | Bị chặn theo style-src-attr |
| CSP-T12 | Style element có nonce | Chạy nếu policy cho phép |
| CSP-T13 | Image từ origin hợp lệ | Tải thành công |
| CSP-T14 | Image từ origin lạ | Bị chặn |
| CSP-T15 | API connect-src hợp lệ | Request được phép khởi tạo |
| CSP-T16 | API connect-src không hợp lệ | Browser chặn |
| CSP-T17 | API CORS không hợp lệ | Phân biệt với CSP block |
| CSP-T18 | Payment frame | Chỉ provider đã duyệt được tải |
| CSP-T19 | frame-ancestors none | Trang không bị site khác nhúng |
| CSP-T20 | form-action | Form chỉ submit tới đích được phép |
| CSP-T21 | base-uri none | Base URL injection không thay đổi base |
| CSP-T22 | object-src none | Plugin/object bị chặn |
| CSP-T23 | Worker source | Worker chỉ tải từ nguồn được phép |
| CSP-T24 | CSP report schema | Endpoint validate và giới hạn field |
| CSP-T25 | Report storm | Rate limit/sampling hoạt động |
| CSP-T26 | Header trùng ở proxy và app | Response cuối có policy đúng dự kiến |
| CSP-T27 | CDN cache HTML | Header/HTML nonce đồng bộ và không reuse |
| CSP-T28 | Browser cũ | Fallback được kiểm tra theo support matrix |
| CSP-T29 | Trusted Types | DOM sink không nhận string tùy ý ở browser hỗ trợ |
| CSP-T30 | Core user journey | Login, payment, upload và admin flow vẫn hoạt động |

### 17.1 Tiêu chí nghiệm thu

Chỉ kết thúc rollout khi:

- Không còn CSP violation hợp lệ ảnh hưởng core journey.
- Các nguồn script được owner phê duyệt.
- Không có unsafe-inline/unsafe-eval trong production policy nếu không có exception được phê duyệt.
- Nonce được tạo per response và không bị cache reuse.
- Payment, identity, API, upload và admin journeys pass.
- Report endpoint có rate limit và không lưu dữ liệu nhạy cảm.
- Có dashboard và alert theo directive/route/release.
- Có rollback procedure đã diễn tập.
- Policy có owner và quy trình review khi thêm dependency.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không bật CSP enforce ngay với ứng dụng legacy?

**Đáp án:** Inline script, event handler, style và third-party dependency có thể bị chặn làm hỏng luồng. Report-Only giúp inventory và triage trước khi enforce.

**Câu 2.** Report-Only có chặn resource không?

**Đáp án:** Không. Nó đánh giá policy và gửi report; browser vẫn tải/thực thi theo policy enforce hiện có.

**Câu 3.** Nonce phải được tạo như thế nào?

**Đáp án:** Bằng CSPRNG, có entropy đủ lớn và mới cho từng response HTML. Nonce trong header phải khớp phần tử được cấp quyền trong cùng response.

**Câu 4.** Vì sao cache HTML có nonce cần cẩn trọng?

**Đáp án:** Cache có thể tái sử dụng nonce hoặc làm lệch header với body. Cần no-store/private hoặc edge injection per response, hay dùng hash cho nội dung tĩnh.

**Câu 5.** strict-dynamic có ý nghĩa gì?

**Đáp án:** Nó cho phép trust từ script có nonce/hash lan sang script được script đáng tin tải động theo quy tắc CSP3. Root loader vì vậy phải được kiểm soát nghiêm.

**Câu 6.** frame-src và frame-ancestors khác nhau thế nào?

**Đáp án:** frame-src giới hạn iframe mà trang tải; frame-ancestors giới hạn website được phép nhúng trang hiện tại.

**Câu 7.** CSP có thay thế CORS không?

**Đáp án:** Không. CSP kiểm soát trang có thể khởi tạo kết nối/tải resource tới đâu; CORS quyết định script có được đọc response cross-origin.

**Câu 8.** SRI và CSP có thay thế nhau không?

**Đáp án:** Không. CSP kiểm soát nguồn/điều kiện tải và thực thi; SRI xác minh bytes của tài nguyên khớp hash đã khai báo.

**Câu 9.** Trusted Types có tự sanitize HTML không?

**Đáp án:** Không. Trusted Types ép sink nhận trusted value; policy phải dùng sanitizer và allowlist đúng.

**Câu 10.** Vì sao không tự động thêm blocked-uri vào CSP?

**Đáp án:** Report có thể đến từ extension, scanner, injection hoặc nguồn chưa được duyệt. Mỗi nguồn phải được xác minh mục đích và owner trước khi allowlist.

## 19. Checklist vận hành CSP

### Trước triển khai

- [ ] Inventory script, style, image, font, API, frame, worker và media.
- [ ] Xác định owner và mục đích của từng third-party origin.
- [ ] Refactor inline handler và unsafe DOM sink.
- [ ] Xóa eval/unsafe-eval khỏi production bundle.
- [ ] Chọn nonce hay hash cho từng inline script/style.
- [ ] Kiểm tra CSP ở response cuối từ CDN/proxy.
- [ ] Thiết kế report endpoint có validation, rate limit và redaction.
- [ ] Có E2E tests cho login, payment, upload và admin.

### Trong rollout

- [ ] Bắt đầu bằng Report-Only.
- [ ] Theo dõi đủ user journey và browser mục tiêu.
- [ ] Phân loại report theo route, directive, source và release.
- [ ] Không auto-allowlist blocked-uri.
- [ ] Enforce canary theo nhóm người dùng/route.
- [ ] Theo dõi conversion, JS errors và API failures.
- [ ] Có người trực và rollback config.
- [ ] Kiểm tra nonce per response và cache behavior.

### Sau triển khai

- [ ] Duy trì policy owner và change review.
- [ ] Xóa source fallback không còn cần.
- [ ] Kiểm tra dependency/third-party định kỳ.
- [ ] Kiểm tra report storm và false positives.
- [ ] Theo dõi browser compatibility.
- [ ] Cân nhắc Trusted Types sau khi DOM sink inventory hoàn tất.
- [ ] Kiểm thử regression khi thêm route, widget hoặc CDN.
- [ ] Diễn tập rollback và incident response khi script provider bị compromise.

**Ghi nhớ:** Triển khai CSP thành công là một quá trình thay đổi ứng dụng và vận hành, không chỉ thêm một header. Inventory chính xác, Report-Only có triage, nonce/hash được quản lý đúng, policy tối thiểu, rollout có đo lường và rollback sẵn sàng sẽ giúp chuyển từ quan sát sang enforcement mà không làm mất các luồng nghiệp vụ quan trọng.

## Tài liệu tham khảo

- [W3C — Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
- [MDN — CSP: script-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src)
- [MDN — CSP: style-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src)
- [MDN — CSP: frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors)
- [MDN — CSP: Content-Security-Policy-Report-Only](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy-Report-Only)
- [MDN — Subresource Integrity](https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity)
- [W3C — Trusted Types](https://www.w3.org/TR/trusted-types/)
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [MDN — Reporting API](https://developer.mozilla.org/en-US/docs/Web/API/Reporting_API)

