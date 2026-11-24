# Hoàn thiện hồ sơ browser security

Một hồ sơ browser security mô tả cách ứng dụng web sử dụng các ranh giới bảo mật của trình duyệt, dữ liệu nào đi qua từng ranh giới, cơ chế nào bảo vệ chúng và bằng chứng nào chứng minh các cơ chế đó hoạt động. Hồ sơ cần đủ rõ để nhóm phát triển, vận hành và bảo mật cùng hiểu origin nào được tin cậy, cookie nào được gửi, tài nguyên nào được tải, iframe nào được nhúng và request nào có thể làm thay đổi dữ liệu.

Bài thực hành tổng hợp này dùng một cửa hàng trực tuyến giả lập. Bạn sẽ lập sơ đồ kiến trúc, kiểm kê origin và dữ liệu, xây dựng threat model, thiết kế kiểm soát, chạy các ca kiểm thử, thu thập bằng chứng và hoàn thiện risk register cùng kế hoạch khắc phục. Kết quả là một hồ sơ có thể dùng trong review bảo mật, kiểm tra trước phát hành và bàn giao vận hành.

Bài học thuộc module `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`, tập trung vào ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web. Bài thực hành tích hợp Same-Origin Policy, CORS, cookie, storage, CSP, Trusted Types, CSRF, clickjacking, iframe sandbox, security headers, service worker và giám sát hành vi thực tế.

## Mục tiêu

Sau bài học, bạn có thể:

- Kiểm kê tài sản, origin, site, browsing context, cookie, storage và luồng dữ liệu của một ứng dụng.
- Vẽ trust boundary và xác định thành phần nào được phép đọc, gửi hoặc thay đổi dữ liệu.
- Xây dựng threat model cho XSS, CSRF, clickjacking, CORS misconfiguration, iframe và nội dung bên thứ ba.
- Thiết kế bộ security controls nhất quán giữa frontend, browser và backend.
- Xây dựng ma trận kiểm thử dương tính, âm tính và kiểm thử hồi quy đa trình duyệt.
- Thu thập bằng chứng có thể tái hiện mà không làm lộ cookie, token hoặc dữ liệu cá nhân.
- Hoàn thiện hồ sơ rủi ro, quyết định chấp nhận rủi ro và kế hoạch remediation.

## 1. Tình huống và phạm vi bài thực hành

Bạn là thành viên nhóm bảo mật được giao review một cửa hàng trực tuyến có trang tài khoản, giỏ hàng, checkout, quản trị nội dung và chức năng xem trước file do người dùng tải lên.

Ứng dụng hiện có các thành phần:

| Thành phần | Host hoặc vị trí | Vai trò |
|---|---|---|
| Web frontend | `https://shop.example.test` | Trang sản phẩm, giỏ hàng, tài khoản và checkout |
| Browser-facing API/BFF | `https://shop.example.test/api/*` | Nhận request từ browser, kiểm tra session và gọi dịch vụ nội bộ |
| Admin portal | `https://admin.example.test` | Quản trị catalog và nội dung |
| Preview nội dung không tin cậy | `https://shop-preview.exampleusercontent.test` | Hiển thị HTML hoặc file do người dùng tải lên |
| Payment provider | `https://pay.partner.invalid` | Cổng thanh toán bên thứ ba |
| Trang kiểm thử cùng site | `https://evil.example.test` | Mô phỏng sibling subdomain không đáng tin cậy trong lab |
| Trang kiểm thử cross-site | `https://attacker.invalid` | Mô phỏng website bên ngoài trong lab |

Các host `.test` và `.invalid` là tên minh họa dành cho môi trường thử nghiệm. Không trỏ chúng tới hệ thống thật hoặc sử dụng dữ liệu production. Khi triển khai lab, dùng DNS local hoặc hosts file và chứng chỉ HTTPS được browser tin cậy.

### Quy tắc nghiệp vụ

- Người dùng đăng nhập bằng session cookie.
- Người dùng có thể cập nhật hồ sơ, địa chỉ giao hàng và tạo đơn hàng.
- Trang checkout chuyển người dùng sang payment provider rồi nhận kết quả qua callback đã xác minh ở backend.
- Quản trị viên có thể chỉnh sửa sản phẩm và nội dung.
- Người dùng có thể tải ảnh, PDF hoặc tài liệu để xem trước.
- Frontend có một số script analytics và widget bên thứ ba.
- Browser cần hỗ trợ các luồng chính trên Chromium, Firefox và WebKit; Safari thực tế được kiểm tra nếu nằm trong phạm vi sản phẩm.

### Giả định và giới hạn

Hồ sơ phải ghi rõ những điều chưa được xác minh. Nếu chưa có bằng chứng về cách cookie được cấu hình, không ghi “cookie an toàn”. Nếu chưa kiểm tra Safari thực tế, không ghi “đã hỗ trợ Safari”. Nếu chưa kiểm tra một endpoint, ghi “chưa kiểm thử” thay vì suy luận từ cấu hình dự kiến.

Chỉ sử dụng tài khoản, host, cookie, file và dữ liệu giả lập do nhóm kiểm soát. Mọi request có tác dụng phụ trong lab phải dùng dữ liệu không có giá trị thực.

## 2. Sản phẩm bàn giao: browser security dossier

Hồ sơ hoàn chỉnh cần có các phần sau:

| Phần | Nội dung | Bằng chứng tối thiểu |
|---|---|---|
| System context | Thành phần, owner, browser và môi trường hỗ trợ | Sơ đồ kiến trúc và mô tả hệ thống |
| Asset inventory | Cookie, token, dữ liệu cá nhân, file và chức năng nhạy cảm | Danh sách tài sản và owner |
| Origin inventory | Scheme, host, port, site, mục đích và mức tin cậy | Bảng origin có kiểm chứng |
| Trust boundary | Browser, frontend, API, iframe, third-party và storage | Sơ đồ luồng dữ liệu |
| Threat model | Threat, attack path, tác động và kiểm soát | Risk register |
| Security controls | Cookie, SOP/CORS, CSP, CSRF, sandbox và headers | Cấu hình thực tế và giải thích |
| Test evidence | Ca kiểm thử, browser, kết quả và bằng chứng | Test matrix và trace đã làm sạch |
| Monitoring | CSP report, server log và cảnh báo | Dashboard hoặc mẫu event |
| Remediation | Người phụ trách, ưu tiên, thời hạn và cách xác minh | Kế hoạch hành động |
| Residual risk | Rủi ro còn lại và người chấp nhận | Quyết định có owner và ngày rà soát |

Một hồ sơ tốt phân biệt ba trạng thái:

- **Designed:** kiểm soát đã được thiết kế hoặc đề xuất.
- **Implemented:** kiểm soát đã được cấu hình trong hệ thống.
- **Verified:** có bằng chứng kiểm thử cho thấy kiểm soát hoạt động trong phạm vi đã ghi.

Không chuyển trạng thái từ Designed sang Verified chỉ vì có một header trong file cấu hình. Phải kiểm tra response thực tế và hành vi browser.

## 3. Kiểm kê tài sản và luồng dữ liệu

### Xác định tài sản cần bảo vệ

Bắt đầu bằng dữ liệu và hành động có giá trị:

| ID | Tài sản | Vị trí hoặc chủ thể | Tác động nếu bị lộ hoặc sửa |
|---|---|---|---|
| AST-01 | Session cookie | Browser và shop backend | Chiếm quyền phiên |
| AST-02 | CSRF token | HTML/SPA state và backend session | Giả mạo request nếu validation sai |
| AST-03 | Hồ sơ người dùng | API và database | Lộ thông tin cá nhân |
| AST-04 | Địa chỉ giao hàng | API và database | Lộ dữ liệu cá nhân, chuyển hướng đơn |
| AST-05 | Giỏ hàng và đơn hàng | Frontend state và backend | Sửa nội dung hoặc tạo giao dịch trái phép |
| AST-06 | Quyền quản trị | Admin portal và backend | Sửa catalog hoặc nội dung trái phép |
| AST-07 | File upload | Object storage và preview origin | Stored XSS, malware hoặc parser abuse |
| AST-08 | Payment state | Backend và payment provider | Giả mạo trạng thái thanh toán |
| AST-09 | Access logs và CSP reports | Monitoring pipeline | Lộ URL, identifier hoặc dữ liệu nhạy cảm |

Ghi owner cho từng tài sản. Ví dụ, team Identity sở hữu session lifecycle, team Commerce sở hữu đơn hàng, team Platform sở hữu reverse proxy và security headers, team Content sở hữu upload/preview.

### Mô tả luồng dữ liệu

Với mỗi chức năng, ghi:

1. Ai khởi tạo hành động?
2. Browser gửi request tới host nào?
3. Cookie hoặc token nào được gửi?
4. Server xác thực và phân quyền ở đâu?
5. Dữ liệu nào được trả về browser?
6. Có iframe, redirect hoặc third-party script tham gia không?
7. Dữ liệu được lưu trong cookie, localStorage, IndexedDB, Cache Storage hay server session?
8. Hành động có làm thay đổi trạng thái không?

Ví dụ luồng cập nhật địa chỉ:

- Người dùng mở trang tài khoản trên `shop.example.test`.
- Frontend gửi `POST /api/profile/address` cùng session cookie và CSRF token.
- BFF xác minh session, CSRF token và quyền sở hữu hồ sơ.
- BFF gọi dịch vụ hồ sơ nội bộ.
- Browser nhận status và dữ liệu đã được giới hạn.
- Server ghi audit event không chứa cookie hoặc token.

Luồng này nên dùng cùng origin cho browser-facing API nếu kiến trúc cho phép. BFF có thể gọi service nội bộ từ server, tránh việc browser phải giữ token dịch vụ hoặc mở CORS rộng cho nhiều backend.

## 4. Kiểm kê origin, site và browsing context

### Bảng origin inventory

Origin gồm scheme, host và port hiệu lực. Site phục vụ các chính sách khác như SameSite cookie và có thể bao gồm nhiều origin khác nhau.

| ID | Origin | Quan hệ | Mức tin cậy | Mục đích |
|---|---|---|---|---|
| ORG-01 | `https://shop.example.test` | Origin chính | Tin cậy theo phạm vi ứng dụng | Frontend và BFF |
| ORG-02 | `https://admin.example.test` | Khác origin, thường cùng site với shop | Tin cậy có điều kiện | Quản trị |
| ORG-03 | `https://evil.example.test` | Khác origin, thường cùng site | Không tin cậy trong lab | Kiểm tra sibling subdomain |
| ORG-04 | `https://shop-preview.exampleusercontent.test` | Khác site | Nội dung không tin cậy | Preview file |
| ORG-05 | `https://pay.partner.invalid` | Cross-site | Bên thứ ba được tích hợp | Thanh toán |
| ORG-06 | `https://attacker.invalid` | Cross-site | Không tin cậy | Kiểm thử CSRF và embed |

Không dùng “cùng domain” như một nhãn bảo mật. `shop.example.test` và `admin.example.test` khác origin dù thường cùng site. Cookie SameSite có thể xem hai host này là same-site trong khi SOP xem chúng là cross-origin.

### Các boundary cần vẽ

- **Origin boundary:** quyết định quyền đọc DOM, storage và response theo SOP/CORS.
- **Site boundary:** ảnh hưởng SameSite và một số chính sách quyền riêng tư.
- **Cookie boundary:** host/domain, path, Secure, HttpOnly và SameSite.
- **Browsing context boundary:** tab, popup, iframe và opener.
- **Storage boundary:** localStorage, sessionStorage, IndexedDB, Cache Storage và partitioning.
- **Process boundary:** renderer sandbox và site isolation do browser triển khai.
- **Network boundary:** request, response, redirect, CORS, CORP và CSP.
- **Application boundary:** authentication, authorization và kiểm tra nghiệp vụ ở backend.

~~~mermaid
flowchart TB
    subgraph Browser["Browser session"]
        subgraph Shop["shop.example.test - trusted app"]
            UI["Frontend DOM / JavaScript"]
            Cookie["Host-only session cookie"]
            State["CSRF token / transient state"]
            BFF["Same-origin BFF /api"]
        end
        subgraph Admin["admin.example.test - separate origin"]
            AdminUI["Admin UI"]
        end
        subgraph Preview["Isolated preview site"]
            FileFrame["Sandboxed preview"]
        end
        Payment["Payment provider page"]
    end
    Services["Internal services / database"]
    Monitoring["Security monitoring"]
    UI --> Cookie
    UI --> State
    UI --> BFF
    BFF --> Services
    AdminUI --> Services
    UI -->|Redirect top-level| Payment
    UI -->|Sandbox / postMessage| FileFrame
    BFF --> Monitoring
    Shop --> Monitoring
~~~

Sơ đồ là mô hình logic. Browser có thể chia process và storage theo cách riêng; không suy luận rằng mỗi hộp tương ứng một process hoặc một vùng lưu trữ vật lý.

### Kiểm tra cookie và storage inventory

Ghi rõ cookie nào được đặt bởi host nào và server nào cần nhận nó:

| Cookie | Host đặt | Thuộc tính dự kiến | Mục đích |
|---|---|---|---|
| `__Host-session` | `shop.example.test` | Secure, HttpOnly, Path=/, SameSite=Lax, không Domain | Session người dùng |
| `__Host-admin-session` | `admin.example.test` | Secure, HttpOnly, Path=/, SameSite=Strict hoặc Lax theo luồng | Session quản trị |
| CSRF token | Session phía server và form/header | Không phải session cookie | Xác minh request thay đổi trạng thái |
| Payment state | Backend | State/nonce có thời hạn | Liên kết callback với phiên checkout |

Cookie không bị cô lập theo port. Prefix `__Host-` yêu cầu Secure, Path=/ và không có Domain trên browser hỗ trợ. Cookie host-only giúp giới hạn host nhận cookie; nó không thay thế CSRF protection trước sibling subdomain.

Ghi rõ dữ liệu nào được lưu trong localStorage hoặc IndexedDB. Không lưu session secret hoặc refresh token dài hạn trong storage mà JavaScript cùng origin có thể đọc nếu kiến trúc có lựa chọn an toàn hơn. Không coi Cache Storage là nơi lưu dữ liệu được authorization lâu dài; cache có thể tồn tại sau khi session thay đổi.

## 5. Threat model tổng hợp

### Xác định attacker và khả năng

| Chủ thể | Khả năng giả định | Không nên mặc định |
|---|---|---|
| Website cross-site | Gửi form/navigation và một số request | Không thể đọc response cross-origin theo mặc định |
| Sibling subdomain bị xâm nhập | Gửi request tới host cùng site, có thể tạo nội dung trên subdomain đó | SameSite sẽ luôn chặn request |
| Script XSS trong shop origin | Chạy trong quyền origin chính, thao tác DOM và gọi API | HttpOnly hoặc SOP sẽ ngăn script cùng origin |
| Third-party script | Chạy với quyền của tài liệu nếu được nhúng trực tiếp | CDN hoặc nhà cung cấp luôn an toàn |
| Người tải file độc hại | Gửi nội dung HTML/SVG hoặc file được parser xử lý | MIME type do client gửi là đáng tin |
| Extension | Có thể đọc/sửa trang theo quyền được cấp | Browser policy áp dụng giống website script |
| Network attacker | Có thể tấn công kết nối không an toàn hoặc hạ cấp nếu cấu hình yếu | HTTPS tự chứng minh nội dung ứng dụng an toàn |

### Attack path và kiểm soát

| ID | Attack path | Tài sản bị ảnh hưởng | Kiểm soát chính |
|---|---|---|---|
| TH-01 | Stored/reflected XSS trong trang sản phẩm | DOM, session và dữ liệu tài khoản | Output encoding, safe DOM, CSP, Trusted Types |
| TH-02 | CSRF tới endpoint cập nhật địa chỉ | Hồ sơ người dùng | Synchronizer token, Origin check, SameSite |
| TH-03 | Clickjacking trang checkout hoặc admin | Hành động nhạy cảm | `frame-ancestors`, X-Frame-Options tương thích |
| TH-04 | CORS allowlist phản chiếu origin tùy ý | Response API theo phiên | Exact allowlist, credentials policy, `Vary: Origin` |
| TH-05 | Sibling subdomain gửi request same-site | Endpoint dùng cookie | CSRF token, Origin validation, Fetch Metadata |
| TH-06 | HTML/SVG upload chạy trong origin chính | Cookie, DOM và dữ liệu shop | Isolated preview origin, sandbox, MIME/nosniff |
| TH-07 | postMessage listener tin message giả | State và hành động frontend | Kiểm tra origin, source và schema |
| TH-08 | Service worker bị thay đổi hoặc cache response cũ | Nội dung trang và state | Scope hẹp, kiểm soát deploy, cache versioning |
| TH-09 | Third-party script bị xâm phạm | DOM và dữ liệu cùng origin | Giảm script, SRI khi phù hợp, CSP, vendor review |
| TH-10 | Redirect/callback thanh toán giả | Payment state và đơn hàng | State/nonce, chữ ký callback, xác minh server-to-server |

### Đánh giá khả năng và tác động

Dùng thang điểm nhất quán của tổ chức. Nếu chưa có chuẩn nội bộ, có thể dùng ma trận minh họa:

- Likelihood: 1 = hiếm, 2 = khó xảy ra, 3 = có thể, 4 = dễ xảy ra, 5 = rất dễ xảy ra.
- Impact: 1 = thấp, 2 = hạn chế, 3 = đáng kể, 4 = nghiêm trọng, 5 = rất nghiêm trọng.
- Risk score = Likelihood × Impact.

| Điểm | Mức tham khảo | Hành động |
|---|---|---|
| 1–4 | Thấp | Theo dõi và xử lý theo lịch |
| 5–9 | Trung bình | Có owner và thời hạn |
| 10–16 | Cao | Ưu tiên remediation trước phát hành nếu liên quan dữ liệu nhạy cảm |
| 17–25 | Rất cao | Chặn phát hành hoặc áp dụng biện pháp giảm thiểu khẩn cấp theo quy trình |

Điểm số chỉ là công cụ ưu tiên. Một rủi ro có impact rất cao không nên được xem nhẹ chỉ vì likelihood chưa rõ. Ghi cả mức độ tin cậy của đánh giá và giả định còn thiếu.

## 6. Thiết kế bộ kiểm soát

### Session cookie và session lifecycle

Cookie session của shop nên host-only, Secure, HttpOnly và SameSite phù hợp với luồng nghiệp vụ:

~~~http
Set-Cookie: __Host-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Yêu cầu thiết kế:

- Không đặt Domain nếu không cần chia sẻ cookie giữa subdomain.
- Xoay session ID sau đăng nhập và khi thay đổi privilege.
- Hủy session phía server khi logout hoặc hết hạn.
- Không ghi giá trị cookie vào log, trace hoặc frontend telemetry.
- Cấu hình thời hạn idle và absolute lifetime theo threat model.
- Kiểm tra hành vi redirect và SSO nếu SameSite ảnh hưởng luồng.

Admin portal nên có session và chính sách xác thực riêng phù hợp với mức đặc quyền cao hơn. Không chia sẻ session cookie giữa shop và admin chỉ vì hai host cùng site.

### CSRF protection

Với request thay đổi trạng thái sử dụng cookie session:

- Dùng synchronizer token gắn với session.
- Kiểm tra token trước khi thực hiện tác dụng phụ.
- Kiểm tra Origin chính xác; dùng Referer fallback theo chính sách.
- Dùng Fetch Metadata như defense in depth.
- Khai báo SameSite rõ ràng.
- Không thực hiện tác dụng phụ qua GET.
- Kiểm tra authorization và dữ liệu ở backend.

Ví dụ kiểm tra Origin:

~~~js
const trustedOrigin = "https://shop.example.test";

function requireTrustedOrigin(req, res, next) {
  const origin = req.get("Origin");

  if (origin !== trustedOrigin) {
    return res.sendStatus(403);
  }

  next();
}
~~~

Đây là một lớp kiểm soát minh họa. Endpoint thực tế cần xử lý rõ các request thiếu Origin, Referer và client không phải browser. Origin không phải bằng chứng xác thực người dùng; session, CSRF token và authorization vẫn cần thiết.

### CORS cho browser-facing API

Kiến trúc đề xuất dùng BFF cùng origin tại `/api`, nên browser không cần CORS cho các request chính tới API. Nếu có endpoint cross-origin thật sự cần cho một client web, cấu hình allowlist cụ thể:

~~~http
Access-Control-Allow-Origin: https://admin.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không phản chiếu mọi Origin. Không dùng wildcard khi response cần credentials. Chỉ cho phép method và header cần thiết. Kiểm tra preflight và request chính; nhớ rằng request đơn giản có thể tới server dù browser không expose response cho JavaScript.

### CSP và Trusted Types

Một policy khởi đầu cho trang shop có thể trông như sau:

~~~http
Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self' 'nonce-{RANDOM_PER_RESPONSE}'; style-src 'self' 'nonce-{RANDOM_PER_RESPONSE}'; img-src 'self' https://images.example-cdn.test; connect-src 'self'; font-src 'self'; frame-src https://pay.partner.invalid; upgrade-insecure-requests
~~~

Đây là ví dụ cần điều chỉnh theo tài nguyên thực tế. Nonce phải được sinh ngẫu nhiên cho mỗi response và gắn vào đúng script/style được phép. Không dùng chuỗi placeholder làm nonce production. Nếu checkout chuyển hướng top-level sang payment provider, không cần mở `frame-src` cho provider nếu không nhúng provider trong iframe.

Với browser và ứng dụng hỗ trợ Trusted Types, có thể cân nhắc:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types shop-app
~~~

Trusted Types giúp kiểm soát một số DOM injection sink. Cần xác minh browser mục tiêu hỗ trợ và thiết kế fallback an toàn. Nó không thay thế output encoding, safe DOM API hoặc kiểm thử XSS.

### Clickjacking và iframe

Nếu shop không cần được nhúng, đặt:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Nếu một route cụ thể cần được nhúng, chỉ cho phép origin đối tác đã xác minh qua `frame-ancestors`. Không mở toàn bộ site cho mọi frame.

Preview file nên được phục vụ từ site riêng như `exampleusercontent.test`, không dùng origin shop. Dùng iframe sandbox với quyền tối thiểu:

~~~html
<iframe
  src="https://shop-preview.exampleusercontent.test/file/preview-001"
  sandbox=""
  referrerpolicy="no-referrer"
  title="File preview">
</iframe>
~~~

Nếu cần script trong preview, chỉ cấp `allow-scripts` sau khi đánh giá; không kết hợp `allow-scripts` và `allow-same-origin` cho nội dung không tin cậy cùng origin ứng dụng. Không gửi session cookie của shop tới preview host.

### Security headers bổ sung

| Header | Giá trị tham khảo | Mục đích |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` khi toàn bộ subdomain đã sẵn sàng HTTPS | Giảm downgrade về HTTP |
| `X-Content-Type-Options` | `nosniff` | Giảm MIME sniffing ngoài ý muốn |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Giảm dữ liệu referrer gửi ra ngoài |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` nếu không cần | Giới hạn API thiết bị |
| `Cross-Origin-Opener-Policy` | `same-origin` nếu tương thích | Cô lập opener/browsing context |
| `Cross-Origin-Embedder-Policy` | `require-corp` nếu cần cross-origin isolation | Yêu cầu tài nguyên cross-origin đáp ứng chính sách |
| `Cross-Origin-Resource-Policy` | `same-origin` cho tài nguyên nhạy cảm phù hợp | Hạn chế nhúng tài nguyên từ ngữ cảnh khác |

Không bật COEP một cách máy móc. Nó có thể làm hỏng image, font, script hoặc worker cross-origin nếu CDN chưa cấu hình CORS/CORP phù hợp. HSTS `includeSubDomains` chỉ bật khi tất cả subdomain liên quan đã sẵn sàng HTTPS và được quản lý.

## 7. Thiết kế kiểm soát cho các tích hợp đặc biệt

### Payment provider

Ưu tiên chuyển hướng top-level tới payment provider thay vì nhúng trang thanh toán nếu nghiệp vụ cho phép. Backend tạo payment intent, liên kết với order ID và state ngẫu nhiên có thời hạn. Khi browser quay lại, backend xác minh state và lấy trạng thái giao dịch từ kênh server-to-server hoặc xác minh chữ ký theo giao thức provider.

Không tin query parameter `status=success` do browser gửi. Không coi việc browser quay về trang success là bằng chứng đã thanh toán.

### File upload và preview

- Kiểm tra file ở server, không tin Content-Type do client gửi.
- Kiểm tra kích thước, loại file và chữ ký định dạng phù hợp.
- Không phục vụ HTML/SVG không tin cậy từ origin shop.
- Dùng attachment cho loại file không cần render inline.
- Nếu preview, dùng origin riêng, CSP và sandbox.
- Giới hạn parser, thời gian và tài nguyên xử lý.
- Không cho preview truy cập cookie hoặc API nhạy cảm của shop.

### postMessage

Nếu widget hoặc iframe cần giao tiếp, thiết kế schema message hẹp:

~~~js
const trustedFrameOrigin = "https://pay.partner.invalid";
const frame = document.querySelector("#payment-frame");

window.addEventListener("message", (event) => {
  if (event.origin !== trustedFrameOrigin) return;
  if (event.source !== frame.contentWindow) return;

  const data = event.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return;
  if (data.type !== "PAYMENT_UI_READY") return;

  notifyPaymentUiReady();
});
~~~

Không nhận lệnh chung như `EXECUTE`, `NAVIGATE` hoặc dữ liệu tùy ý. Không cho message quyết định trạng thái thanh toán hoặc authorization; backend phải xác minh giao dịch.

### Service worker và cache

Nếu shop dùng service worker:

- Đăng ký worker từ origin chính trong secure context.
- Giữ scope nhỏ và kiểm soát đường dẫn script.
- Không cache response chứa dữ liệu cá nhân hoặc trạng thái tài khoản nếu không có chiến lược rõ.
- Xóa hoặc vô hiệu hóa cache phù hợp khi logout.
- Đảm bảo update không giữ worker cũ ngoài dự kiến.
- Không xem cache hit là bằng chứng session còn hợp lệ.
- Kiểm tra worker control và cache version sau deploy.

## 8. Xây dựng ma trận kiểm thử tổng hợp

Mỗi ca cần có ID, mục tiêu, điều kiện, bước tái hiện, kỳ vọng, thực tế, browser/version, bằng chứng và trạng thái. Chia thành nhóm để dễ chạy theo thay đổi.

### Origin, SOP và CORS

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| BR-01 | Origin khác scheme, host hoặc port đọc DOM shop | SOP chặn |
| BR-02 | Sibling subdomain truy cập DOM shop | SOP chặn dù thường cùng site |
| BR-03 | Origin được allowlist đọc API | Chỉ response được phép được expose |
| BR-04 | Origin lạ đọc API | JavaScript không đọc response |
| BR-05 | CORS credentials kết hợp wildcard | Browser từ chối expose response |
| BR-06 | Request đơn giản có tác dụng phụ | Backend vẫn kiểm tra CSRF và authorization |
| BR-07 | Preflight method/header không được cho phép | Request chính không được gửi theo luồng preflight đó |

### Cookie, CSRF và session

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| BR-08 | Session cookie thiếu CSRF token | Request thay đổi trạng thái bị từ chối |
| BR-09 | CSRF token đúng trong session | Request được chấp nhận nếu authorization hợp lệ |
| BR-10 | Token thuộc session khác | Bị từ chối |
| BR-11 | Request từ sibling subdomain cùng site | Origin/token validation ngăn giả mạo |
| BR-12 | GET kích hoạt thay đổi dữ liệu | Không có tác dụng phụ |
| BR-13 | Cookie HttpOnly | JavaScript không đọc được cookie |
| BR-14 | Cookie Secure qua HTTP | Không được gửi theo quy tắc Secure |
| BR-15 | Logout và session rotation | Session cũ không còn được chấp nhận |
| BR-16 | SameSite trong top-level navigation và iframe | Hành vi đúng policy đã ghi |

### XSS, CSP và clickjacking

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| BR-17 | Inline script không có nonce/hash | CSP enforce chặn |
| BR-18 | Script từ host ngoài allowlist | Bị chặn |
| BR-19 | DOM sink nhận string không tin cậy | Safe API/Trusted Types ngăn injection theo thiết kế |
| BR-20 | Origin không được phép nhúng shop | `frame-ancestors` chặn |
| BR-21 | CSP Report-Only ghi nhận vi phạm | Report được tạo; policy đó không chặn |
| BR-22 | Dashboard hiển thị CSP report | Dữ liệu được encode và giảm thiểu |

### Iframe, file và tích hợp

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| BR-23 | Preview origin khác site | Không đọc cookie hoặc DOM shop |
| BR-24 | Iframe sandbox không cấp script | Script preview không chạy |
| BR-25 | postMessage từ origin lạ | Listener bỏ qua |
| BR-26 | postMessage đúng origin nhưng sai source/schema | Listener từ chối |
| BR-27 | File HTML/SVG do user upload | Không thực thi trong origin shop |
| BR-28 | Payment callback có state sai | Backend từ chối |
| BR-29 | Cache sau logout | Không hiển thị dữ liệu tài khoản cũ |
| BR-30 | Service worker update | Worker và cache theo version dự kiến |

### Browser và nền tảng

| ID | Môi trường | Phạm vi |
|---|---|---|
| BR-31 | Chromium desktop | Bộ test chính |
| BR-32 | Firefox desktop | SOP, CORS, cookie, CSP |
| BR-33 | WebKit automation | Engine-specific behavior |
| BR-34 | Safari thực tế nếu hỗ trợ | Cookie, storage, permission, iframe |
| BR-35 | Mobile browser nếu hỗ trợ | Điều hướng, viewport, cookie và quyền |
| BR-36 | Profile private/third-party cookie restricted | Storage partitioning và luồng đăng nhập |

Không phải mọi ca đều cần chạy trên mọi tổ hợp. Xác định test tier: smoke trên cả engine sau thay đổi bảo mật, regression đầy đủ trước release, và manual/device test cho những tính năng phụ thuộc nền tảng.

## 9. Thu thập bằng chứng

Bằng chứng phải cho reviewer biết ca test chạy ở đâu, điều kiện nào, thao tác gì và kết quả nào chứng minh kết luận.

### Bộ bằng chứng tối thiểu

| Loại | Nội dung | Cách làm sạch |
|---|---|---|
| HTTP response headers | CSP, CORS, cookie policy và security headers | Không đính kèm Set-Cookie value |
| Network trace | Request URL, method, status và header liên quan | Xóa Cookie, Authorization và query nhạy cảm |
| Console | CSP violation và browser exception | Loại nội dung có thể chứa token hoặc dữ liệu cá nhân |
| Screenshot | Trạng thái UI và thông báo lỗi | Che email, địa chỉ, order ID thật |
| Server log | CSRF validation, authorization và kết quả nghiệp vụ | Dùng request ID giả danh hóa |
| Browser metadata | Tên, version, engine và hệ điều hành | Chỉ thu thập mức cần thiết |
| Test output | Expected/actual, assertion và test ID | Không in token/cookie hoặc raw payload |

### Quy tắc evidence

- Dùng dữ liệu giả lập và tài khoản kiểm thử.
- Không lưu session cookie, CSRF token, access token hoặc password trong artifact.
- Che query string có thể chứa email, order ID hoặc state.
- Không đính kèm raw CSP report nếu chưa loại dữ liệu nhạy cảm.
- Ghi timestamp và timezone.
- Ghi commit/build ID để liên kết với release.
- Ghi rõ test chạy tự động hay thủ công.
- Ghi rõ môi trường chưa được kiểm tra.

### Ví dụ evidence record

| Trường | Giá trị mẫu |
|---|---|
| Test ID | BR-08 |
| Build | `web-2026.11.22.1` |
| Browser | Chromium, phiên bản ghi từ test runner |
| Origin nguồn | `https://attacker.invalid` |
| Origin đích | `https://shop.example.test` |
| Điều kiện | Đã đăng nhập bằng tài khoản lab |
| Hành động | Gửi form POST thiếu CSRF token |
| Kỳ vọng | Backend trả 403, không tạo thay đổi |
| Thực tế | Ghi status và kết quả từ server |
| Bằng chứng | Network trace đã làm sạch và request ID |
| Trạng thái | Pass / Fail / Blocked / Not run |

Không ghi một ca là Pass chỉ vì trang không hiển thị lỗi. Cần xác minh trạng thái backend hoặc response phù hợp.

## 10. Giám sát và vận hành

### CSP violation reporting

Dùng Report-Only để quan sát policy mới trước khi enforce. Ví dụ cấu hình báo cáo:

~~~http
Reporting-Endpoints: csp="https://shop.example.test/csp-reports"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-to csp; report-uri /csp-reports
~~~

Endpoint báo cáo phải:

- Giới hạn body size và số report mỗi request.
- Hỗ trợ định dạng mà browser mục tiêu gửi.
- Validate JSON, chuẩn hóa trường và giới hạn độ dài.
- Loại query/fragment nhạy cảm trước khi lưu.
- Không fetch `blocked-uri` hoặc render report như HTML.
- Rate limit và xử lý bất đồng bộ.
- Theo dõi parse error, dropped report và queue latency.

Không tự động thêm host trong CSP report vào allowlist. Mỗi nguồn cần được xác minh và review.

### Log security events

Theo dõi các event tổng hợp:

- CSRF rejection theo route và lý do.
- CORS deny và preflight failure.
- CSP violation theo policy ID, directive và release.
- Clickjacking hoặc iframe block trong test/telemetry phù hợp.
- Session rotation, logout và authentication failure.
- File preview rejection và MIME mismatch.
- Service worker/cache version mismatch.

Không log giá trị cookie, token, Authorization header hoặc body nhạy cảm. Dùng request ID và correlation ID đã giả danh hóa.

### Alerting

Cảnh báo theo thay đổi có ý nghĩa:

- CSRF rejection tăng đột biến trên route nhạy cảm.
- CSP violation mới xuất hiện sau release.
- Origin ngoài allowlist cố đọc API hoặc tạo request thay đổi trạng thái.
- Endpoint report lỗi kéo dài.
- File preview có hành vi hoặc loại MIME không mong đợi.
- Cache cũ tiếp tục phục vụ dữ liệu sau logout.

Không cảnh báo chỉ vì số CSP report bằng 0. Pipeline báo cáo có thể không hoạt động hoặc browser không gửi report. Có health check riêng cho endpoint.

## 11. Kế hoạch remediation và risk register

Mỗi phát hiện cần có owner, mức độ, deadline, biện pháp tạm thời, thay đổi lâu dài và cách xác minh.

| ID | Phát hiện mẫu | Mức tham khảo | Remediation | Bằng chứng đóng |
|---|---|---|---|---|
| R-01 | Endpoint thay đổi trạng thái thiếu CSRF token | Cao | Thêm token, Origin và Fetch Metadata check | Test BR-08 đến BR-12 |
| R-02 | CSP cho phép unsafe-inline không có lý do | Cao | Refactor inline script, dùng nonce/hash | Test BR-17, BR-19 |
| R-03 | Preview file cùng origin shop | Rất cao | Tách preview sang site riêng và sandbox | Test BR-23 đến BR-27 |
| R-04 | CORS phản chiếu Origin tùy ý | Cao | Exact allowlist, credentials policy | Test BR-03 đến BR-07 |
| R-05 | Admin và shop dùng chung cookie Domain rộng | Cao | Tách host-only session cookie | Test BR-13 đến BR-16 |
| R-06 | Không có CSP report pipeline | Trung bình | Thêm endpoint, parser, dashboard và alert | Test BR-21, BR-22 |

### Risk register template

| Trường | Nội dung |
|---|---|
| Finding ID | Mã phát hiện duy nhất |
| Asset | Tài sản bị ảnh hưởng |
| Threat | Kịch bản tấn công |
| Boundary | Ranh giới bị vượt hoặc cấu hình sai |
| Likelihood | Điểm và lý do |
| Impact | Điểm và lý do |
| Risk score | Likelihood × Impact hoặc phương pháp tổ chức |
| Existing control | Kiểm soát hiện tại và trạng thái |
| Remediation | Hành động cụ thể |
| Owner | Người/nhóm chịu trách nhiệm |
| Due date | Hạn xử lý |
| Verification | Test ID và bằng chứng đóng |
| Residual risk | Rủi ro còn lại |
| Acceptance | Người chấp nhận, lý do và ngày review |

Không đóng finding chỉ vì đã merge code. Cần chạy lại test và kiểm tra cấu hình được triển khai thực tế. Nếu chấp nhận rủi ro, ghi rõ phạm vi, thời hạn, người phê duyệt và trigger để đánh giá lại.

## 12. Quy trình review trước phát hành

### Gate 1: Architecture

- Origin inventory có owner và mục đích.
- Cookie scope phù hợp với kiến trúc.
- Third-party script và iframe có trust boundary rõ.
- Upload/preview được cách ly.
- API có authentication và authorization phía server.

### Gate 2: Security controls

- CSP và security headers được kiểm tra trên response thực tế.
- CSRF protection áp dụng cho mọi thao tác thay đổi trạng thái dùng cookie.
- CORS chỉ cho origin cần thiết.
- Cookie có Secure, HttpOnly và SameSite phù hợp.
- postMessage xác minh origin, source và schema.
- Service worker và cache có lifecycle rõ ràng.

### Gate 3: Verification

- Ma trận kiểm thử có trạng thái Pass/Fail/Blocked/Not run.
- Test chạy trên engine mục tiêu.
- Safari/device test hoàn tất nếu nằm trong phạm vi.
- Bằng chứng đã được làm sạch.
- Finding mức cao có remediation hoặc quyết định chấp nhận rủi ro.

### Gate 4: Operations

- CSP report endpoint có health check.
- CSRF/CORS/security event có metric phù hợp.
- Owner nhận alert và biết quy trình phản ứng.
- Có kế hoạch rollback security policy đã review.
- Hồ sơ có ngày cập nhật và người chịu trách nhiệm.

Không dùng một điểm số tổng hợp để che lấp một finding nghiêm trọng. Release gate phải xem xét cả tác động, bằng chứng và residual risk.

## 13. Thực hành tổng hợp

Hoàn thiện dossier cho ứng dụng shop giả lập theo các bước sau.

### Phần A: System context và asset inventory

1. Ghi thành phần frontend, BFF, admin, preview, payment và monitoring.
2. Liệt kê session cookie, CSRF token, hồ sơ, đơn hàng, file upload và payment state.
3. Gán owner và mức độ nhạy cảm cho từng tài sản.
4. Mô tả ít nhất ba luồng dữ liệu: cập nhật hồ sơ, checkout và preview file.

### Phần B: Origin và trust boundary

1. Điền origin inventory với scheme, host, port, site, purpose và trust level.
2. Đánh dấu các cặp cùng site nhưng khác origin.
3. Ghi cookie nào được gửi tới host nào.
4. Xác định vùng storage và khả năng partitioning.
5. Vẽ sơ đồ browser, backend, iframe, payment và third-party.

### Phần C: Threat model

1. Viết ít nhất sáu attack path.
2. Nêu tài sản, attacker capability và boundary liên quan.
3. Đánh giá likelihood, impact và confidence.
4. Chọn ba rủi ro cần remediation trước.
5. Nêu giả định cần xác minh bằng test.

### Phần D: Security controls

1. Đề xuất session cookie host-only và SameSite.
2. Thiết kế CSRF token và Origin validation.
3. Định nghĩa CORS allowlist hoặc giải thích vì sao BFF cùng origin loại bỏ nhu cầu CORS.
4. Viết CSP phù hợp với tài nguyên đã kiểm kê.
5. Định nghĩa frame-ancestors, iframe sandbox và postMessage schema.
6. Đề xuất security headers, service worker và cache policy.
7. Xác định fallback khi browser không hỗ trợ Trusted Types hoặc có chính sách chặn third-party cookie.

### Phần E: Kiểm thử và bằng chứng

1. Chọn test case trong ma trận BR-01 đến BR-36.
2. Chạy trên môi trường lab và browser mục tiêu.
3. Ghi expected/actual, request ID và evidence đã làm sạch.
4. Phân loại Pass, Fail, Blocked hoặc Not run.
5. Tạo finding cho mỗi lỗi có tác động thực tế.

### Phần F: Monitoring và remediation

1. Định nghĩa event cho CSP, CSRF, CORS và file preview.
2. Xác định trường log được phép thu thập và trường phải loại bỏ.
3. Đặt alert threshold và owner.
4. Điền risk register.
5. Lập remediation plan theo ưu tiên.
6. Viết quyết định release: Ready, Ready with accepted risk hoặc Not ready, kèm bằng chứng.

### Bảng kết quả cuối bài

| Hạng mục | Trạng thái | Bằng chứng hoặc ghi chú |
|---|---|---|
| Asset inventory | | |
| Origin inventory | | |
| Trust boundary diagram | | |
| Threat model | | |
| Cookie/session design | | |
| CSRF/CORS controls | | |
| CSP/Trusted Types | | |
| Iframe/file isolation | | |
| Security headers | | |
| Browser test matrix | | |
| Monitoring/alerting | | |
| Risk register | | |
| Remediation owners | | |
| Residual risk approval | | |
| Release decision | | |

## 14. Tiêu chí hoàn thành

Hồ sơ được xem là hoàn chỉnh khi:

- Mỗi origin có owner, mục đích, trust level và quan hệ site được ghi rõ.
- Cookie và storage được ánh xạ tới host, context và dữ liệu sử dụng.
- Các luồng nhạy cảm có threat model và server-side controls.
- CORS, CSRF, CSP, iframe và file preview có cấu hình hoặc quyết định thiết kế được ghi nhận.
- Mỗi finding có mức độ, owner, remediation và cách xác minh.
- Test evidence ghi browser/version và không chứa secret.
- Các ca chưa chạy được đánh dấu rõ; không giả định là Pass.
- Residual risk có người chấp nhận và thời điểm review.
- Release decision dựa trên bằng chứng và mức rủi ro còn lại.

Nếu một phần chưa có dữ liệu, hồ sơ vẫn có thể được bàn giao với trạng thái chưa xác minh và hành động tiếp theo. Không đánh dấu hoàn tất giả tạo bằng cách điền kết quả dự kiến vào cột thực tế.

## 15. Ghi nhớ

- Browser security là hệ thống nhiều boundary: process, site, origin, browsing context, cookie, storage và network.
- Origin gồm scheme, host và port; site có thể gom nhiều origin và ảnh hưởng SameSite.
- SOP hạn chế đọc dữ liệu cross-origin; CORS mở quyền đọc response có kiểm soát.
- Cookie được gửi theo host/domain, path, Secure, HttpOnly, SameSite và browser policy; cookie không cô lập theo port.
- CSRF cần token và kiểm tra request ở server; CORS hoặc SameSite đơn lẻ không đủ.
- XSS có thể chạy với quyền của origin bị ảnh hưởng; CSP và Trusted Types là lớp giảm thiểu cùng với output encoding.
- Clickjacking cần được kiểm soát bằng frame-ancestors và cấu hình iframe phù hợp.
- Nội dung không tin cậy cần origin riêng, sandbox và xử lý file an toàn.
- Evidence phải có thể tái hiện, được làm sạch và liên kết với browser/build cụ thể.
- Hồ sơ bảo mật chỉ có giá trị khi phân biệt rõ Designed, Implemented và Verified, đồng thời ghi nhận residual risk có owner.
