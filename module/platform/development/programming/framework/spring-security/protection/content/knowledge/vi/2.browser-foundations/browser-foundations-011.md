# Mô hình tin cậy giữa trình duyệt, ứng dụng và dịch vụ bên thứ ba

## Mục tiêu và phạm vi

Một ứng dụng Spring Security hiện đại hiếm khi chỉ có một server và một trang HTML. Người dùng có thể truy cập **SPA ở một origin**, gọi **API ở origin khác**, đăng nhập qua **Identity Provider (IdP)**, xem nội dung từ CDN, mở một iframe của đối tác thanh toán và đi qua nhiều **reverse proxy/gateway**. Mỗi lần dữ liệu hoặc quyền đi qua một ranh giới như vậy, cần trả lời: **ai có thể tạo yêu cầu, ai được phép đọc dữ liệu, ai xác thực danh tính và ai có quyền ra quyết định cuối cùng?**

Bài học thuộc chương **Nền tảng trình duyệt** của module **SPRING_SECURITY_HTTP_PROTECTION**, hướng tới áp dụng các lớp phòng vệ HTTP và trình duyệt trong **Spring Security**: **CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session**, trên cả stack **Servlet** và **Reactive/WebFlux**.

Sau bài học, bạn có thể:

1. Vẽ **sơ đồ ranh giới tin cậy (trust boundary)** giữa browser, JavaScript, BFF, API, IdP, CDN, iframe, webhook và proxy.
2. Phân biệt **origin**, **site**, **cùng tổ chức sở hữu** và **được tin cậy** — bốn khái niệm không đồng nghĩa.
3. Đánh giá từng bằng chứng như **cookie, Bearer token, Origin, Sec-Fetch-Site, client IP, chữ ký webhook** theo nguồn gốc và giới hạn của nó.
4. Giải thích trách nhiệm khác nhau của **SOP/CORS, SameSite, CSRF token, CSP, iframe sandbox, TLS/HSTS, authorization và OAuth2/OIDC**.
5. Thiết kế luồng đăng nhập, gọi API và tích hợp dịch vụ bên thứ ba theo nguyên tắc **least privilege**, không chuyển quyền ngoài ý muốn.
6. Cấu hình Spring Security Servlet/WebFlux và thực hiện các bài kiểm thử ranh giới cho request hợp lệ, bị giả mạo, không đủ quyền và thiếu header.
7. Chẩn đoán lỗi triển khai như **OPTIONS 401/403**, cookie không gửi, login callback sai redirect, CORS mở quá rộng, header proxy bị giả và dữ liệu lọt qua iframe.

## 1. Trust boundary là gì và vì sao phải mô hình hóa?

**Ranh giới tin cậy** là chỗ dữ liệu, lệnh hoặc quyền chuyển từ một chủ thể/vùng kiểm soát sang chủ thể/vùng khác. Điều cần bảo vệ không chỉ là bí mật của đường truyền, mà còn là **tính xác thực của chủ thể**, **quyền đối với tài nguyên** và **mục đích sử dụng dữ liệu**.

Ví dụ luồng đặt hàng:

~~~text
Browser có cookie phiên
  → Frontend gửi POST /api/orders
  → Reverse proxy chuyển request
  → Spring Security xác thực session
  → CSRF filter kiểm tra token
  → Authorization kiểm tra quyền tạo đơn
  → OrderService kiểm tra nghiệp vụ
  → Payment provider được yêu cầu thanh toán
~~~

Một quyết định đúng ở một lớp không chứng minh mọi lớp khác đều đúng:

- **TLS** giúp bảo vệ kết nối tới endpoint, không chứng minh người dùng thực sự muốn chuyển tiền.
- **CORS** cho phép JavaScript của origin được khai báo đọc response, không cấp quyền sửa đơn của người khác.
- **CSRF token** giúp kiểm tra ý định request trong một mô hình credential tự gửi, không thay thế phân quyền tài nguyên.
- **JWT có chữ ký hợp lệ** chưa đủ: còn phải kiểm tra issuer, audience, expiration, phạm vi và quyền.
- **Webhook có chữ ký hợp lệ** chưa đủ để bỏ qua xác minh trạng thái giao dịch hoặc chống xử lý trùng.
- **Origin hợp lệ** không có nghĩa request đã được xác thực, và HTTP client ngoài browser có thể tự khai Origin.

Với từng đường truyền, hãy ghi rõ **tài sản cần bảo vệ**, **người có thể điều khiển đầu vào**, **điều kiện tin cậy** và **kiểm tra tại nơi nhận**.

### 1.1. Những tài sản cần xác định

| Tài sản | Ví dụ | Mất an toàn dẫn tới |
| --- | --- | --- |
| **Danh tính** | User ID, session principal, IdP subject | Giả mạo người dùng hoặc nhầm lẫn tài khoản. |
| **Credential** | Session ID, refresh token, access token, API key | Chiếm phiên hoặc gọi API trái phép. |
| **Dữ liệu riêng tư** | Hồ sơ, đơn hàng, địa chỉ, lịch sử giao dịch | Rò rỉ thông tin qua JavaScript, response, logs hoặc cache. |
| **Hành động nghiệp vụ** | Chuyển tiền, đổi email, xóa dữ liệu | CSRF, lạm dụng quyền hoặc xử lý trùng. |
| **Cấu hình tin cậy** | CORS allowlist, redirect URI, key ký token, proxy list | Mở rộng vùng tin cậy ngoài ý muốn. |
| **Thông tin kết nối** | Host, Forwarded, scheme, IP nguồn | Redirect sai, tạo URL độc hại, bỏ qua HTTPS hoặc IP spoofing. |
| **Trạng thái tích hợp** | Payment status, webhook event, callback state | Giả sự kiện, replay hoặc nhầm trạng thái đơn. |

### 1.2. Một sơ đồ tổng quan

Giả sử ứng dụng bán hàng dùng frontend, BFF, IdP, dịch vụ thanh toán và CDN:

~~~mermaid
flowchart LR
    subgraph UA["Thiết bị và browser của người dùng"]
      P["Document app.example.com"]
      JS["JavaScript + cookie jar"]
      P --- JS
    end

    subgraph EDGE["Vùng biên do doanh nghiệp kiểm soát"]
      RP["TLS reverse proxy / gateway"]
      BFF["BFF/session"]
      API["Spring Security API"]
      RP --> BFF
      BFF --> API
    end

    subgraph THIRD["Dịch vụ bên thứ ba"]
      IDP["IdP auth.partner.test"]
      PAY["Payment provider"]
      CDN["CDN scripts/assets"]
    end

    JS -->|"HTTPS request + credentials tùy chính sách"| RP
    JS -->|"Browser redirect / OIDC"| IDP
    CDN -.->|"Script tải vào trang"| P
    API -->|"Server-to-server credential"| PAY
    PAY -.->|"Webhook đã ký"| RP
~~~

Các mũi tên có **mô hình bảo mật khác nhau**:

- Browser đến BFF: thường dùng **session cookie + CSRF**.
- Browser đến IdP: **điều hướng/redirect front-channel** và các tham số ràng buộc flow.
- API đến payment provider: **server-to-server** với credential dành cho service, không tiết lộ vào frontend.
- Payment provider đến webhook: xác minh **chữ ký + freshness/replay + idempotency**, không dựa vào CORS.
- CDN đến trang: tải script bình thường có thể khiến mã chạy với **quyền của document app**, trừ khi được cách ly có chủ đích.

**Một chủ sở hữu doanh nghiệp không có nghĩa mọi origin, subdomain và đối tác đều nên được trao cùng quyền.**

## 2. Origin, site, tổ chức và mức độ tin cậy

### 2.1. Same-origin không đồng nghĩa đã được cấp quyền nghiệp vụ

Với HTTP/HTTPS thông thường:

**Origin = (scheme, host, port)**

~~~text
https://app.example.com             → origin A
https://app.example.com:8443        → origin B
https://api.example.com             → origin C
http://app.example.com              → origin D
~~~

B, C và D đều khác A theo ít nhất một thành phần. **Same-Origin Policy (SOP)** hạn chế mã ở một origin đọc DOM/response của origin khác trong các ngữ cảnh áp dụng.

Nhưng **same-origin không phải authentication**: script XSS trong app.example.com có thể thực thi trong origin của ứng dụng; server vẫn phải kiểm tra session, quyền và nghiệp vụ. SOP là ranh giới browser, không phải danh sách người dùng được phép.

### 2.2. Same-site rộng hơn same-origin

Đối với host thông thường, **schemeful site** được xác định từ scheme và **registrable domain** (theo Public Suffix List). Ví dụ:

~~~text
https://app.example.com  → site https://example.com
https://api.example.com  → site https://example.com
https://evil.example.com → site https://example.com
https://outside.test     → site https://outside.test
http://app.example.com   → site http://example.com
~~~

Ba URL HTTPS đầu là **same-site nhưng khác origin**. Điều đó có ý nghĩa đối với **SameSite cookie**, nhưng không chứng minh evil.example.com là nguồn đáng tin. Subdomain có thể do đối tác vận hành, bị DNS takeover hoặc bị xâm nhập.

| Quan hệ | Đặc điểm | Điều cần ghi nhớ |
| --- | --- | --- |
| **Same-origin** | Cùng scheme, host, port | JavaScript thường có thể đọc response same-origin, nhưng vẫn cần quyền server. |
| **Cross-origin, same-site** | Khác origin, cùng schemeful site | CORS cần thiết để JS đọc response; cookie SameSite có thể đủ điều kiện gửi. |
| **Cross-site** | Khác schemeful site | Có thể có điều hướng/form/tài nguyên nhúng; cookie SameSite và CORS ảnh hưởng theo loại request. |
| **Cùng nhà cung cấp** | Hai endpoint cùng công ty hoặc cloud account | Không tự trở thành cùng origin, cùng site hay cùng mức quyền. |
| **Được trust có điều kiện** | Origin, client ID, service hoặc proxy nằm trong allowlist | Chỉ được trao **quyền và luồng cụ thể**, không phải quyền vô hạn. |

Không tính registrable domain bằng cách lấy “hai nhãn cuối” của hostname: các public suffix như **co.uk** cần cách xử lý chính xác. Port không tham gia phép so site nhưng có tham gia origin.

### 2.3. Mạng nội bộ cũng không mặc định đáng tin

Một dịch vụ ở IP riêng hoặc chạy sau gateway không nên tự bỏ xác thực chỉ vì gọi từ cùng mạng. Phân vùng mạng, mTLS và chính sách firewall hữu ích, nhưng request nội bộ vẫn có thể đến từ máy bị xâm nhập, proxy cấu hình sai hoặc service có quyền quá rộng.

Từng API phải xác định **principal nào được phép gọi**, **audience nào của token**, **scope/role** và **quyền đối với tài nguyên**. Đây là điểm tiếp nối trust boundary từ browser đến hệ thống backend.

## 3. Điều browser quản lý và điều client có thể tự khai

Trong một request, cần biết **header nào mã JavaScript thông thường được phép đặt** và **header nào browser tự tạo**. Nhưng server không nên coi header browser tự tạo là bằng chứng chống giả mạo tuyệt đối, vì client ngoài browser có thể gửi HTTP request tùy ý.

### 3.1. Dấu hiệu nguồn và credential

| Tín hiệu / credential | Ai thường cung cấp trong browser? | Server nên dùng để làm gì? | Không được suy ra |
| --- | --- | --- | --- |
| **Origin** | Browser tính từ ngữ cảnh request. | Kiểm tra CORS và có thể bổ trợ kiểm tra nguồn CSRF. | Đây là danh tính user; HTTP client ngoài browser không giả được. |
| **Referer** | Browser theo referrer policy, có thể bị rút gọn/thiếu. | Tín hiệu bổ sung về nguồn. | Header luôn có hoặc phản ánh đầy đủ URL. |
| **Sec-Fetch-Site/Mode/Dest** | Browser hỗ trợ Fetch Metadata. | Phân loại ngữ cảnh request, bổ trợ resource isolation. | same-site đồng nghĩa an toàn, header không thể bị giả ngoài browser. |
| **Cookie session** | Browser chọn gửi theo cookie policy. | Tra session và xác thực nếu session hợp lệ. | Người dùng chủ động thực hiện mọi request có cookie. |
| **Authorization: Bearer** | Ứng dụng có thể chủ động gắn token; browser còn có các cơ chế auth khác. | Kiểm tra token, issuer/audience/scope/quyền. | Header tồn tại nghĩa là token hợp lệ. |
| **X-Tenant-Id / X-User-Id** | Thường do client hoặc gateway cung cấp. | Dữ liệu gợi ý, hoặc thông tin có nguồn tin cậy được kiểm soát riêng. | Client tự khai đã có quyền của tenant/user đó. |
| **X-Forwarded-For/Proto/Host** | Proxy có thể thêm; client ngoài cũng có thể gửi. | Dùng sau khi xác lập trusted proxy chain. | Cứ có tên X-Forwarded là đáng tin. |

Ví dụ request:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Sec-Fetch-Site: same-site
Cookie: __Host-session=opaque
X-Tenant-Id: tenant-42
Content-Type: application/json

{"productId":42}
~~~

Server phải xác minh session, kiểm tra CSRF cho thao tác thay đổi trạng thái, đối chiếu quyền truy cập tenant-42 và kiểm tra dữ liệu đơn hàng. Một **X-Tenant-Id** không thay được quyền tenant trong security context.

### 3.2. Browser kiểm soát một số header, nhưng không xác thực cho server

Mã JavaScript trong trang thông thường không được tùy ý thay **Cookie, Host, Origin, Content-Length** và các header có tiền tố **Sec-** qua Fetch API. Browser còn kiểm soát việc gửi cookie HttpOnly và những header preflight.

Ngược lại, một HTTP client ngoài browser có thể thử:

~~~bash
curl -i "https://api.example.com/api/me" \
  -H "Origin: https://app.example.com" \
  -H "Sec-Fetch-Site: same-origin" \
  -H "X-Tenant-Id: tenant-admin"
~~~

Client như curl không bị quy tắc **forbidden request headers** của JavaScript website áp dụng theo cách browser áp dụng. Vì vậy **CORS và Fetch Metadata** không phải một cơ chế xác thực dành cho HTTP client nói chung.

### 3.3. Tin theo mức quyền tối thiểu

Một sơ đồ gợi ý:

~~~text
Chứng cứ do browser cung cấp:
  Origin / Sec-Fetch-Site
    → Có thể hỗ trợ chính sách nguồn/CSRF, không xác thực principal

Chứng cứ xác thực:
  Session hợp lệ / OAuth2 access token hợp lệ
    → Xác định principal và những quyền đã cấp

Yêu cầu nghiệp vụ:
  tenantId / orderId / amount
    → Bắt buộc phân quyền theo đối tượng và kiểm tra nghiệp vụ

Kết quả cuối:
  Chỉ thực thi nếu tất cả điều kiện cần đều hợp lệ
~~~

Bảo mật tốt không cố “biến” một header thành bằng chứng thay cho các kiểm tra còn thiếu.

## 4. Ranh giới browser ↔ ứng dụng: session, cookie và CSRF

### 4.1. Cookie là credential browser có thể tự gửi

Server có thể tạo session cookie:

~~~http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie **__Host-** hợp lệ yêu cầu Secure, Path=/ và không có Domain; nó có phạm vi host-only. **HttpOnly** ngăn JavaScript thông thường đọc mã phiên qua document.cookie nhưng không ngăn browser gửi cookie khi đủ điều kiện.

Một request do **website khác** tạo vẫn có thể tới server; liệu cookie có được gửi phụ thuộc SameSite, loại request, URL đích và những điều kiện khác. Browser không biết request nào thật sự được người dùng cho phép thay đổi số dư hoặc xóa đơn hàng.

### 4.2. CORS và CSRF giải quyết hai câu hỏi khác nhau

| Cơ chế | Câu hỏi nó giải quyết | Điều không thay thế |
| --- | --- | --- |
| **CORS** | JavaScript của origin nào được đọc response cross-origin và dùng một số loại request? | Authentication, authorization, CSRF token. |
| **CSRF token** | Request thay đổi trạng thái dựa trên credential tự gửi có đi qua luồng hợp lệ mà ứng dụng cấp token không? | Kiểm tra quyền sở hữu tài nguyên, chống XSS hoàn toàn. |
| **SameSite cookie** | Browser nên gửi cookie trong ngữ cảnh same-site/cross-site nào? | CORS, CSRF token; bảo vệ khỏi subdomain không đáng tin cùng site. |
| **SOP** | Mã từ một origin có được đọc/tương tác dữ liệu của origin khác không? | Không chặn mọi form, điều hướng hoặc request tải tài nguyên. |
| **Authentication** | Request gắn với principal nào? | Không xác nhận mọi hành động có credential đều được user chủ ý thực hiện. |
| **Authorization** | Principal được làm gì với tài nguyên cụ thể? | Không thay thế xác nhận CSRF trong ứng dụng dùng session. |

Ví dụ một form POST từ outside.test:

~~~html
<form action="https://app.example.com/api/orders/42/cancel" method="POST">
  <button type="submit">Gửi</button>
</form>
~~~

Form có thể được browser gửi mà không cần **CORS preflight**, ngay cả khi outside.test không được CORS cho phép đọc phản hồi. Nếu cookie hợp lệ được gửi, server vẫn phải xác minh CSRF token và quyền.

**Không dùng GET cho hành động thay đổi trạng thái**: cookie SameSite=Lax thường được gửi trong điều hướng top-level GET từ site khác. Nếu GET /transfer hoặc GET /logout thực sự làm thay đổi trạng thái, CORS và SameSite không sửa được lỗi thiết kế đó.

### 4.3. SPA khác origin và API dùng cookie

Giả sử frontend ở https://app.example.com, API tại https://api.example.com. Hai host thường **same-site nhưng cross-origin**.

~~~javascript
// Ví dụ ứng dụng đã được phép dùng cookie phiên tại API.
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});

if (!response.ok) {
  throw new Error("Không đọc được hồ sơ: " + response.status);
}
const me = await response.json();
~~~

Để JavaScript đọc response có credentials, API cần trả chính sách CORS phù hợp:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không** dùng Allow-Origin wildcard cùng Allow-Credentials true cho phản hồi cần đọc với credentials. Không phản chiếu mọi Origin rồi bật credentials. Dù CORS đúng, cookie vẫn có thể không gửi vì Domain/Path/Secure/SameSite hoặc chính sách third-party cookie.

### 4.4. Preflight khác request thực

POST JSON kèm header X-CSRF-TOKEN thường tạo OPTIONS preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Preflight **thường không mang cookie phiên**. CORS cần được xử lý trước các bộ lọc có thể chặn OPTIONS do thiếu session. Nhưng khi POST thực được gửi, nó **vẫn phải qua authentication, CSRF token và authorization**.

Chỉ có Allow-Origin hợp lệ ở preflight chưa bảo đảm browser đọc được **response của POST thực**: actual response cũng phải đáp ứng CORS. Một POST có thể đã tạo đơn hàng ở server rồi browser mới chặn JavaScript đọc kết quả. Không retry một giao dịch chỉ vì thấy lỗi CORS.

### 4.5. Backend-for-Frontend (BFF) giảm một số bề mặt rò token

Trong kiến trúc **Backend-for-Frontend**, browser thường chỉ giữ cookie phiên với BFF, còn BFF giữ access token/service credential ở server để gọi backend hoặc dịch vụ khác:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as BFF cùng origin
    participant A as API backend
    B->>F: GET /orders + session cookie
    F->>F: Kiểm tra session / quyền
    F->>A: HTTPS + access token lưu ở server
    A->>A: Validate token audience/scopes
    A-->>F: Dữ liệu được phép
    F-->>B: Response cho user
~~~

Lợi ích: **access token không nhất thiết phải được phơi bày cho JavaScript** hoặc lưu trong localStorage. Nhưng BFF không làm CSRF biến mất: cookie phiên từ browser tới BFF vẫn có thể được tự gửi. Cần giữ **CSRF protection, SameSite, xác thực, phân quyền, session invalidation và TLS**.

Không coi BFF là proxy “chuyển tiếp bất cứ URL nào từ frontend” vì như vậy có thể dẫn tới **SSRF** hoặc mở rộng quyền gọi API ngoài dự kiến.

## 5. Ranh giới trang ứng dụng ↔ script bên thứ ba

Khi HTML của app.example.com nhúng script:

~~~html
<script src="https://cdn.partner.test/widgets/v3/widget.js"></script>
~~~

mã tải từ CDN thường **chạy trong ngữ cảnh của document app.example.com**, không mặc nhiên bị sandbox theo origin cdn.partner.test. Một script hợp lệ hoặc bị xâm nhập có thể truy cập phần DOM/storage mà mã của document được phép truy cập, gọi API cùng origin và thực hiện request theo quyền browser.

Đây là một **quyết định trao quyền thực thi mã**, không chỉ là quyết định tải tài nguyên mạng.

### 5.1. Ba mô hình tích hợp có mức tin cậy khác nhau

| Mô hình | Quyền của bên thứ ba | Khi nào cân nhắc |
| --- | --- | --- |
| **Nhúng script trực tiếp** | Chạy trong document, có thể có quyền rộng của trang. | Chỉ với mã được kiểm soát và tin cậy ở mức tương ứng. |
| **Iframe cross-origin** | Document riêng với SOP; chỉ giao tiếp qua cơ chế được phép. | Widget, thanh toán, biểu mẫu độc lập, nội dung không nên trao quyền DOM. |
| **Server-to-server API** | Không có script chạy trên browser; quyền dựa vào credential service tại backend. | Tích hợp nghiệp vụ cần giữ API key hoặc dữ liệu nhạy cảm ở server. |

Không chọn cách nhúng script trực tiếp chỉ vì dễ triển khai nếu đối tác không cần truy cập DOM của ứng dụng.

### 5.2. Quản trị nguồn script

Biện pháp giảm thiểu:

- Kiểm kê từng script bên thứ ba và **phạm vi dữ liệu thực sự cần**.
- Ghim phiên bản, kiểm soát thay đổi và hạn chế tự cập nhật không kiểm duyệt.
- **Subresource Integrity (SRI)** cho tài nguyên tĩnh nếu phù hợp, để browser kiểm tra nội dung khớp hash đã được chấp thuận.
- **CSP script-src** cho phép những nguồn/mẫu thực thi cần thiết; ưu tiên nonce/hash cho inline script khi thiết kế phù hợp.
- Cân nhắc iframe sandbox thay vì script có toàn quyền khi đối tác chỉ cần render một widget.
- Giám sát lỗi script và hành vi mạng, hạn chế xuất dữ liệu nhạy cảm sang bên thứ ba.

Ví dụ cấu trúc SRI (hash chỉ là placeholder):

~~~html
<script
  src="https://cdn.partner.test/widget/v3/app.js"
  integrity="sha384-REPLACE_WITH_REAL_BASE64_HASH"
  crossorigin="anonymous"></script>
~~~

SRI giúp phát hiện **nội dung tải về khác nội dung đã được pin**, không bảo đảm dependency được chấp thuận ban đầu không chứa hành vi độc hại. Khi chủ động nâng phiên bản và cập nhật hash, vẫn phải review nội dung và trust của nhà cung cấp.

### 5.3. CSP giới hạn tài nguyên, không cấp danh tính

Một chính sách CSP minh họa cho HTML frontend:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; connect-src 'self' https://api.example.com; frame-src https://checkout.partner.test; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Chính sách trên cho phép kết nối API và nhúng iframe checkout từ nguồn được thiết kế, không mặc nhiên cho script từ mọi CDN. Điều chỉnh theo tính năng hợp lệ của ứng dụng. Không mở wildcard hoặc 'unsafe-inline' chỉ để hết lỗi mà không xem xét rủi ro.

**CSP có hiệu lực cho document nhận policy.** Nếu frontend HTML được phục vụ ở app.example.com, chỉ đặt CSP trên response JSON của api.example.com không tự bảo vệ HTML ở app.example.com.

CSP chỉ là một lớp bảo vệ. Vẫn cần **output encoding đúng ngữ cảnh, safe DOM APIs, sanitization cho HTML được phép, Trusted Types khi hỗ trợ**, kiểm soát dependency và server-side authorization.

## 6. Ranh giới iframe ↔ parent: cách ly và giao tiếp có kiểm soát

Iframe cross-origin thường có **origin riêng** và chịu SOP: mã ở parent không tự đọc được DOM hay storage của iframe khác origin; mã ở iframe cũng không được đọc DOM parent tùy ý.

Nhưng iframe không tự an toàn hoàn toàn. Parent có thể hiển thị nội dung bên thứ ba; các tùy chọn **sandbox, Permissions Policy, frame-src, frame-ancestors và postMessage** quyết định phần nào mức độ tương tác.

### 6.1. Nhúng iframe ở mức quyền tối thiểu

Ví dụ một widget chỉ hiển thị thông tin, không yêu cầu script hoặc form:

~~~html
<iframe
  src="https://widgets.partner.test/receipt-preview"
  sandbox=""
  referrerpolicy="no-referrer"
  title="Xem trước chứng từ">
</iframe>
~~~

**sandbox rỗng** bật một bộ hạn chế mạnh; widget có thể cần các quyền cụ thể hơn để hoạt động. Đừng tự động thêm mọi cờ để “cho chạy được”; chỉ cấp quyền đã được đánh giá.

Một widget có script có thể cần:

~~~html
<iframe
  src="https://widgets.partner.test/widget"
  sandbox="allow-scripts"
  referrerpolicy="strict-origin-when-cross-origin"
  title="Tiện ích đối tác">
</iframe>
~~~

Đây chỉ là ví dụ. Nhiều widget thực tế cần form, popup hoặc tính năng khác; mỗi quyền thêm phải được xem xét. Đặc biệt cẩn trọng với kết hợp **allow-scripts** và **allow-same-origin** khi nội dung nhúng có thể cùng origin với parent, vì có thể làm mất phần lớn lợi ích sandbox trong các tình huống đó.

**Lưu ý quan trọng về opaque origin:** Khi iframe có sandbox="allow-scripts" nhưng **không có allow-same-origin**, document nhúng thường mang **opaque origin**; các message phát ra từ đó có thể xuất hiện với **event.origin là "null"**, thay vì origin URL của iframe. Không xem origin "null" là một nguồn đáng tin; nó không định danh được đối tác. Ví dụ kiểm tra event.origin theo URL ở phần tiếp theo dành cho iframe **được giữ origin thực** (chẳng hạn iframe cross-origin không bị sandbox ép opaque origin). Nếu chọn iframe có opaque origin, phải thiết kế giao thức giao tiếp riêng, giới hạn dữ liệu được trao, kiểm tra event.source cùng cấu trúc message và không gửi secret chỉ dựa trên giá trị "null". Đối với postMessage hướng **đến** opaque origin, không thể dùng URL origin thông thường làm targetOrigin chính xác; mọi lựa chọn dùng wildcard phải được đánh giá nghiêm ngặt và không chuyển dữ liệu nhạy cảm.


### 6.2. postMessage: gửi đúng origin đích

Khi parent muốn giao tiếp với iframe khác origin:

~~~javascript
const targetOrigin = "https://widgets.partner.test";
const iframe = document.querySelector("#partner-frame");

iframe.contentWindow.postMessage(
  { type: "PING", requestId: "req-42" },
  targetOrigin
);
~~~

Dùng **targetOrigin cụ thể** cho thông tin nhạy cảm; không dùng "*" chỉ vì tiện. Ở phía nhận, kiểm tra **event.origin** và **event.source** cùng schema:

~~~javascript
const allowedOrigin = "https://widgets.partner.test";
const expectedWindow = document.querySelector("#partner-frame").contentWindow;

window.addEventListener("message", (event) => {
  if (event.origin !== allowedOrigin) return;
  if (event.source !== expectedWindow) return;

  if (event.data?.type === "STATUS_UPDATED" &&
      typeof event.data.status === "string" &&
      event.data.status.length <= 80) {
    document.querySelector("#status").textContent = event.data.status;
  }
});
~~~

Đây là ví dụ để **parent nhận thông điệp từ iframe** và hiển thị trạng thái text. Nếu ví dụ ở bên iframe, origin và expectedWindow phải được đổi theo đúng vai trò bên gửi/bên nhận. Với dữ liệu nhạy cảm, còn cần xét user session, message correlation và trạng thái giao dịch ở server.

Không dùng **postMessage làm cơ chế cấp quyền duy nhất** cho yêu cầu thay đổi trạng thái: dữ liệu message có thể bị người gửi hợp lệ nhưng bị chiếm quyền gửi sai, hoặc bị phát lại. Server vẫn cần authentication/authorization và kiểm tra nghiệp vụ.

### 6.3. Chính sách cho phép nhúng khác với chính sách nhúng người khác

- **CSP frame-src** trong trang parent giới hạn **những iframe nào parent được tải**.
- **CSP frame-ancestors** trên response của trang đích giới hạn **những trang nào được nhúng trang đích**.
- **X-Frame-Options** là cơ chế cũ để giới hạn việc nhúng tài liệu.
- **Permissions-Policy** có thể hạn chế các tính năng browser được dùng trong tài liệu/iframe theo ngữ cảnh.

Không nhầm frame-src với frame-ancestors. Muốn ngăn trang thanh toán bị **clickjacking**, cần cấu hình frame-ancestors hoặc cơ chế tương ứng tại **chính trang thanh toán**. Parent không thể tự tuyên bố cho phép nhúng một trang nếu trang đích đã từ chối.

### 6.4. Third-party cookie và iframe

Một iframe khác site có thể bị browser hạn chế cookie bên thứ ba, ngay cả khi iframe dùng **SameSite=None; Secure**, tùy chính sách browser và ngữ cảnh. Một số môi trường hỗ trợ **cookie partitioning/CHIPS** hoặc **Storage Access API** với điều kiện riêng.

Đừng dựa vào giả định rằng iframe bên thứ ba luôn nhìn thấy phiên người dùng tại website của nhà cung cấp. Cần kiểm thử trên browser mục tiêu; tránh chuyển token vào query string chỉ để vượt hạn chế cookie vì URL có thể bị lộ qua logs/history/Referer.

## 7. Ranh giới ứng dụng ↔ Identity Provider: OAuth2/OIDC

Khi ứng dụng ủy quyền đăng nhập cho **Identity Provider (IdP)**, nó không được mặc định tin mọi redirect hoặc mọi token được truyền qua browser. Phải xác định **client đăng ký, endpoint IdP, redirect URI, state, PKCE, issuer, audience, thời hạn và user identity**.

Ví dụ:

~~~text
Browser:   https://app.example.com
Backend:   https://app.example.com
IdP:       https://identity.partner.test
Callback:  https://app.example.com/login/oauth2/code/partner
~~~

Giả sử ứng dụng Spring Security đóng vai trò **OAuth2 Client/OIDC Relying Party**, sử dụng authorization code flow. Một luồng đơn giản:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant APP as Ứng dụng Spring (OAuth2 Client)
    participant IDP as IdP bên thứ ba
    B->>APP: Yêu cầu login
    APP->>APP: Tạo state/PKCE và lưu ngữ cảnh flow
    APP-->>B: Redirect tới authorization endpoint
    B->>IDP: Authorization request
    IDP->>IDP: Xác thực user/consent nếu áp dụng
    IDP-->>B: Redirect callback?code=...&state=...
    B->>APP: Callback code + state
    APP->>APP: Xác minh state / ngữ cảnh callback
    APP->>IDP: Back-channel token request với code + PKCE
    IDP-->>APP: Token response
    APP->>APP: Xác minh ID token/issuer/audience/nonce nếu OIDC
    APP-->>B: Thiết lập session ứng dụng
~~~

### 7.1. Front-channel và back-channel không tương đương

- **Front-channel** qua browser: authorization request, redirect và callback. Browser vận chuyển dữ liệu qua các URL, không phải nơi nên giữ client secret.
- **Back-channel** server-to-server: trao đổi authorization code lấy token khi backend giữ trách nhiệm OAuth2 Client; client secret hoặc private key chỉ đặt ở phía đáng tin khi kiểu client cho phép.
- **Session ứng dụng** sau login: ứng dụng có thể tạo cookie phiên độc lập với cookie phiên của IdP. Logout ở ứng dụng và logout khỏi IdP là **hai việc khác nhau** và cần thiết kế theo yêu cầu SSO/single logout.

Đừng gửi access token, refresh token hoặc client secret vào URL callback chỉ để frontend đọc, vì URL có thể xuất hiện trong browser history, log, analytics hoặc Referer.

### 7.2. State, PKCE và nonce bảo vệ các ranh giới khác nhau

| Cơ chế | Vai trò | Không có nghĩa |
| --- | --- | --- |
| **state** | Liên kết authorization response với request mà client đã khởi tạo, hỗ trợ chống login CSRF và tráo flow. | Token đã được ký và có quyền truy cập API. |
| **PKCE** | Ràng buộc authorization code với client đã bắt đầu flow bằng code verifier/challenge. | Không cần kiểm tra redirect URI, token hoặc quyền. |
| **OIDC nonce** | Liên kết ID token với phiên xác thực client khi yêu cầu và xác minh đúng quy tắc. | Có thể bỏ qua state hoặc audience. |
| **redirect URI allowlist** | Ngăn code/token bị đưa tới endpoint tùy ý. | Tự xác thực một callback đã bị sửa nội dung. |
| **ID token validation** | Xác minh issuer, audience, chữ ký, expiry và các điều kiện giao thức. | ID token tự động trở thành access token dùng được cho mọi API. |

**OIDC ID token** phục vụ xác thực user với client. **OAuth2 access token** phục vụ truy cập tài nguyên theo audience/scopes. Không sử dụng ID token như Bearer token cho mọi API chỉ vì nó chứa sub và có chữ ký.

### 7.3. Token hợp lệ về chữ ký vẫn có thể không dành cho ứng dụng

Một access token có chữ ký hợp lệ của IdP nhưng **audience là service khác** không được API orders chấp nhận. Khi kiểm tra token, cần xét:

- **iss (issuer)** đúng nhà phát hành được cấu hình.
- **aud (audience)** bao gồm API mục tiêu theo hợp đồng.
- **exp, nbf và các thời gian liên quan**, với clock skew được quản lý hợp lý.
- **signature/algorithm/key** từ nguồn tin cậy; không tùy tiện chấp nhận algorithm hoặc khóa do client tự chọn.
- **scopes/authorities**, client identity nếu cần.
- **Authorization ở tầng nghiệp vụ**, ví dụ user chỉ được xem đơn thuộc tenant của mình.
- **Revocation/rotation** hoặc chính sách lifetime theo kiểu token thực tế.

Một token có scope **orders:read** không nên được phép gọi endpoint **POST /api/orders/{id}/cancel** chỉ vì Spring Security đã xác minh chữ ký.

### 7.4. Redirect/open redirect là vùng nguy hiểm

Nếu ứng dụng chấp nhận tham số next tùy ý rồi chuyển hướng sau đăng nhập:

~~~text
/login?next=https://untrusted.test
~~~

nó có thể trở thành **open redirect** hoặc hỗ trợ phishing. Không sử dụng URL do người dùng cung cấp làm redirect đích khi chưa qua chính sách chặt chẽ. Nếu cần quay lại trang trước khi đăng nhập, ưu tiên path nội bộ đã kiểm tra hoặc allowlist origin/route thực sự cần.

Khi tích hợp IdP, callback URL phải được đăng ký đúng với nhà cung cấp và gắn với luồng OAuth2 Client cụ thể. Không “cho CORS wildcard” tại callback để chữa lỗi redirect: **OIDC login flow dựa trên điều hướng và xác minh giao thức**, không phải mọi bước đều là XHR cần CORS.

### 7.5. Cookie IdP và cookie ứng dụng là hai phiên độc lập

Người dùng có thể đăng xuất khỏi app.example.com nhưng vẫn còn phiên tại identity.partner.test; lần login tiếp có thể được IdP xác thực lại nhanh mà không cần nhập mật khẩu, tùy chính sách. Ngược lại, phiên IdP hết hạn không nhất thiết lập tức vô hiệu hóa session ứng dụng.

Thiết kế cần xác định:

1. Logout chỉ khỏi ứng dụng hay cả IdP?
2. Có front-channel/back-channel logout mà IdP hỗ trợ hay không?
3. Session ứng dụng có giới hạn tối đa độc lập với IdP không?
4. Các access/refresh token server đang giữ có được thu hồi hoặc xóa theo chính sách không?
5. Khi tài khoản ở IdP bị vô hiệu hóa, bao lâu ứng dụng cập nhật quyền?

Không dựa vào việc browser xóa một cookie để khẳng định **mọi phiên liên quan trên các dịch vụ đã bị thu hồi**.

## 8. Ranh giới backend ↔ dịch vụ bên thứ ba

Khi ứng dụng cần gọi hệ thống thanh toán, giao hàng, CRM, email hoặc API dữ liệu nhạy cảm, hãy xác định rõ **vị trí giữ credential** và **quyền của token/service account**.

### 8.1. Không đưa service API key vào JavaScript browser

Ví dụ cấu hình không nên làm:

~~~javascript
// KHÔNG LÀM: service key nhạy cảm nằm trong bundle frontend.
const API_KEY = "server-secret-example";
await fetch("https://payments.partner.test/charge", {
  headers: { "X-API-KEY": API_KEY }
});
~~~

Mọi dữ liệu giao cho JavaScript hoặc bundle tải xuống browser có thể bị người dùng/đối thủ có quyền truy cập trang trích xuất. Minify hoặc làm rối mã **không giữ bí mật được key**.

Luồng phù hợp hơn:

~~~text
Browser → POST /api/orders (session + CSRF + quyền)
   → Spring API kiểm tra nghiệp vụ, giá tiền server-side
      → Server gọi provider qua HTTPS bằng credential riêng
         → Provider xác thực credential và thực hiện chức năng hạn chế
      → Server đối chiếu trạng thái và ghi giao dịch
   → Browser nhận trạng thái đã được phép
~~~

Frontend không được tự cung cấp **giá tiền cuối cùng, quyền truy cập provider hoặc service API key** làm dữ kiện đáng tin. Backend cần lấy giá/điều kiện giao dịch từ nguồn server đáng tin và tính lại trước khi gọi provider.

### 8.2. Service credential không phải session người dùng

Một service account có thể có quyền gọi provider, nhưng không nên được phép thực hiện mọi hành động đại diện người dùng nếu không có **ngữ cảnh ủy quyền** tương ứng.

Một số mô hình:

| Mô hình | Khi thích hợp | Ranh giới phải kiểm tra |
| --- | --- | --- |
| **OAuth2 client credentials** | Service gọi service theo danh tính ứng dụng. | Scope/audience và quyền của service, không coi đây là user consent. |
| **On-behalf-of/token exchange** | Backend gọi service thay mặt user khi giao thức/hạ tầng hỗ trợ. | Ràng buộc user, client, audience và quyền được ủy quyền. |
| **mTLS** | Xác thực kết nối client-service trong mạng kiểm soát. | Danh tính chứng chỉ, vòng đời chứng chỉ, vẫn cần authorization theo API. |
| **API key riêng cho service** | Tích hợp nhà cung cấp có hỗ trợ key. | Lưu bí mật tại server, scope tối thiểu, rotation, audit, không lộ log. |

**Không chuyển tiếp nguyên xi cookie phiên của browser** tới một API đối tác ngoài tổ chức. Cookie session do ứng dụng cấp thường không có ý nghĩa với provider và có thể vô tình tiết lộ credential.

### 8.3. Server-to-server không cần browser CORS

Ví dụ backend dùng WebClient gọi API provider:

~~~java
import org.springframework.web.reactive.function.client.WebClient;

class PaymentGatewayClient {
    private final WebClient webClient;

    PaymentGatewayClient(WebClient.Builder builder, String paymentBaseUrl) {
        this.webClient = builder.baseUrl(paymentBaseUrl).build();
    }

    // Phương thức minh họa; credential phải được cấu hình an toàn
    // tại backend và gắn theo hợp đồng provider.
}
~~~

Một WebClient chạy trên server **không bị browser SOP/CORS chặn**. Thêm Access-Control-Allow-Origin vào provider không giải quyết quyền service-to-service. Điều cần kiểm soát là **TLS, xác thực provider, timeouts, retry/idempotency, kiểm tra response, quyền và lưu bí mật**.

Không truyền base URL tùy ý từ người dùng vào WebClient. Nếu endpoint backend nhận URL hoặc hostname do client chỉ định rồi tự tải tài nguyên, phải đánh giá **Server-Side Request Forgery (SSRF)**.

### 8.4. SSRF: backend có quyền mạng rộng hơn browser

Một endpoint kiểu:

~~~text
GET /api/preview?url=https://somewhere.example
~~~

nếu cho backend lấy bất kỳ URL do client cung cấp, có thể bị lạm dụng để truy cập **metadata service, nội bộ doanh nghiệp hoặc endpoint quản trị** mà browser ngoài mạng không truy cập được.

Các biện pháp:

- Dùng allowlist nguồn/host và loại URL theo mục đích nghiệp vụ, không cho tùy ý gọi mọi địa chỉ.
- Chặn truy cập dải IP loopback, link-local, private hoặc địa chỉ nội bộ khi kiến trúc không cho phép; chú ý DNS resolution và redirect.
- Tắt hoặc kiểm soát redirect, giao thức không phải HTTP/HTTPS, port, IPv6 và DNS rebinding.
- Áp dụng network egress policy tại hạ tầng, không chỉ kiểm tra chuỗi URL.
- Kiểm soát response size, timeout, content type và không đưa thông tin trả về từ nội bộ ra browser.
- Không coi một yêu cầu là an toàn chỉ vì URL đã được JavaScript validate trước khi gửi tới backend.

Không có một phép kiểm tra chuỗi hostname duy nhất đủ chống mọi biến thể SSRF.

### 8.5. Webhook là request từ service, không phải browser

Provider thường thông báo sự kiện bằng HTTP POST đến endpoint webhook của ứng dụng:

~~~http
POST /webhooks/payment HTTP/1.1
Host: app.example.com
Content-Type: application/json
X-Provider-Signature: provider-specific-signature
X-Provider-Timestamp: provider-specific-timestamp

{"eventId":"evt-42","type":"payment.succeeded","orderId":"o-42"}
~~~

**Header và payload trên chỉ minh họa**; mỗi provider có hợp đồng xác thực webhook riêng. Một webhook hợp lệ cần được kiểm tra dựa trên:

1. **Chữ ký/HMAC hoặc cơ chế xác thực thực sự của provider**, trên đúng **raw request body** và trường dữ liệu provider quy định.
2. **Freshness/timestamp** và chống replay nếu giao thức hỗ trợ.
3. **Event ID / idempotency** để tránh xử lý một sự kiện nhiều lần.
4. **Trạng thái nghiệp vụ**: chỉ cho phép chuyển trạng thái đơn theo quy tắc hợp lệ, xác minh đơn và số tiền/tiền tệ.
5. Khi cần, **truy vấn lại provider qua kênh server-to-server đã xác thực** cho sự kiện nhạy cảm hoặc bất thường.
6. Log/audit không chứa bí mật, signature đầy đủ hoặc dữ liệu cá nhân ngoài nhu cầu.

Không dựa vào **Origin, Referer hoặc CORS** để xác thực webhook. Provider gửi server-to-server, không phải JavaScript chịu SOP. IP allowlist có thể bổ sung nhưng không thay thế chữ ký khi nhà cung cấp hỗ trợ xác minh sự kiện.

### 8.6. CSRF cho webhook cần quyết định theo cơ chế xác thực

Một webhook không mang session cookie user và dùng chữ ký độc lập có threat model **khác với form POST có session**. Có thể cấu hình **ngoại lệ CSRF hẹp** cho đúng endpoint webhook, **sau khi** đã triển khai xác minh chữ ký, timestamp, replay và idempotency. Không tắt CSRF trên toàn bộ /api/** hoặc toàn ứng dụng chỉ vì một webhook cần nhận POST.

Cần phân biệt:

- **Webhook endpoint**: xác thực bằng secret/chữ ký service, không tin cookie browser.
- **User-facing API**: xác thực user/session hoặc access token, phân quyền đối tượng, có CSRF khi credential tự gửi.
- **Public status/read-only endpoint**: có thể không dùng session, nhưng vẫn cần giới hạn dữ liệu và chống lạm dụng.

## 9. Ranh giới reverse proxy/gateway ↔ Spring Security

Trong production, nhiều triển khai có đường đi:

~~~text
Browser --HTTPS--> Reverse Proxy / WAF
                     |
                     | HTTP hoặc HTTPS nội bộ
                     v
                  Spring Boot
~~~

Proxy có thể terminate TLS, định tuyến URL, kiểm soát host và chuyển tiếp thông tin connection. Spring Boot ở sau proxy cần biết scheme/host bên ngoài để tạo redirect hoặc cookie phù hợp, nhưng **chỉ nên tin thông tin do proxy đáng tin cung cấp**.

### 9.1. Forwarded và X-Forwarded-* là dữ liệu cần kiểm soát nguồn

Ví dụ:

~~~http
Forwarded: for=198.51.100.10;proto=https;host=app.example.com
X-Forwarded-For: 198.51.100.10
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
~~~

Nếu client có thể tự đặt những header này và proxy chuyển tiếp mà không loại bỏ/ghi đè, backend có thể tin nhầm:

- **Scheme** là HTTPS dù request ban đầu không đi qua TLS.
- **Host** do attacker chọn, ảnh hưởng redirect, URL trong email hoặc callback.
- **IP** do attacker tự khai, ảnh hưởng rate limiting hoặc IP allowlist.
- Những thông tin khác phục vụ kiểm tra nguồn hoặc cấu hình cookie.

Nguyên tắc: **xác lập danh sách proxy tin cậy, chặn truy cập trực tiếp backend khi cần và làm sạch header ở biên**.

### 9.2. Host header không phải bằng chứng sở hữu tên miền

Header **Host** thuộc phần định tuyến của HTTP/1.1; HTTP/2 và HTTP/3 có dạng authority thích hợp. Browser thường tạo giá trị tương ứng URL, nhưng HTTP client trực tiếp có thể gửi Host do nó chọn.

Nếu server dùng Host không kiểm soát để sinh URL reset mật khẩu:

~~~text
https://{request-host}/reset?token=...
~~~

một host không đáng tin có thể gây **Host header poisoning**. Cần xác định những public host hợp lệ từ cấu hình/edge tin cậy, không dựa tùy ý vào request header.

### 9.3. HTTPS và HSTS

**TLS** bảo vệ tính bí mật/toàn vẹn kết nối với endpoint đã được xác thực theo cơ chế TLS. **HSTS** hướng dẫn browser ưu tiên HTTPS khi đã biết policy của host.

Ví dụ response qua HTTPS:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

**includeSubDomains** chỉ dùng sau khi xác minh mọi subdomain liên quan đều hỗ trợ HTTPS, vì có thể làm hỏng dịch vụ HTTP hợp lệ chưa được nâng cấp. HSTS không bảo vệ một HTTP client không tuân thủ chính sách browser hoặc chứng minh user có quyền; nó cũng không thay CSRF, authorization hay bảo vệ token.

Với proxy terminate TLS, phải bảo đảm **đường tới backend có ranh giới mạng phù hợp**, header forwarding được tin cậy và cookie Secure/redirect URL phản ánh scheme bên ngoài một cách đúng đắn.

### 9.4. HTTP firewall và xử lý request không chuẩn

Spring Security có HTTP firewall để lọc hoặc chuẩn hóa những request không hợp lệ/tìm cách lách ranh giới URL theo cấu hình và stack. Nhưng **HTTP firewall không tự thay thế WAF, kiểm soát proxy, xác thực hoặc phân quyền**.

Cẩn trọng với:

- URL/path có ký tự mã hóa bất thường hoặc phân tách không nhất quán.
- Sự không thống nhất về method/path giữa proxy và backend.
- Header trùng lặp hoặc dạng request có thể gây **HTTP request smuggling** nếu các tầng phân tích framing khác nhau.
- OPTIONS preflight bị chặn ở gateway trước khi đến cấu hình CORS.
- Redirect HTTP↔HTTPS hoặc chuyển host khiến cookie/CORS và callback khác dự kiến.

Không mở rộng HTTP firewall tùy tiện chỉ để cho một URL bất thường đi qua. Hãy xác định nguyên nhân và bảo đảm **mọi tầng nhìn request theo cùng một cách**.

### 9.5. Một ví dụ forwarded header trong Spring Boot

Trong môi trường có proxy tin cậy và đã làm sạch các header liên quan, Spring Boot có thể cấu hình:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Đây chỉ là lựa chọn xử lý forwarded headers, **không phải cơ chế tự xác minh proxy**. Trước khi bật ở production, cần ràng buộc đường kết nối, cấu hình proxy, host allowlist và loại bỏ header do client bên ngoài tự đặt.

## 10. Bản đồ security headers và ranh giới chúng điều khiển

| Cơ chế | Ranh giới chính | Ví dụ tình huống |
| --- | --- | --- |
| **SOP** | Quyền mã từ origin A đọc/điều khiển dữ liệu của origin B | JavaScript ngoài không tự đọc DOM tài khoản ở ứng dụng. |
| **CORS** | Server cấp quyền đọc response cross-origin cho JavaScript | Frontend SPA đọc JSON API khác origin. |
| **CSP script-src** | Những nguồn và cách chạy script được phép trong document | Giới hạn script inline/CDN và giảm rủi ro XSS. |
| **CSP connect-src** | Những đích được browser cho phép kết nối từ document | Chỉ cho SPA fetch đúng API và dịch vụ đã duyệt. |
| **CSP frame-src** | Document được phép tải iframe từ đâu | Parent chỉ nhúng checkout provider được duyệt. |
| **CSP frame-ancestors** | Những parent nào được nhúng document này | Trang tài khoản không bị iframe ở website tùy ý. |
| **X-Frame-Options** | Chính sách chống nhúng phiên bản cũ | Hạn chế clickjacking trên trang phù hợp. |
| **CORP** | Giới hạn một số request cross-origin tải tài nguyên ở chế độ no-cors | Tài nguyên riêng tư không nên bị nhúng từ site ngoài. |
| **COOP/COEP** | Cách ly browsing context và yêu cầu tài nguyên cross-origin cho một số chế độ | Ứng dụng cần mức cross-origin isolation cụ thể. |
| **Referrer-Policy** | Mức thông tin nguồn được truyền qua Referer | Tránh rò đường dẫn/giá trị nhạy cảm sang đối tác. |
| **Permissions-Policy** | Quyền sử dụng một số tính năng browser | Widget không cần camera hoặc microphone. |
| **HSTS** | Chính sách HTTPS cho host trên browser đã nhận HSTS | Hạn chế truy cập HTTP ngoài ý muốn. |
| **X-Content-Type-Options: nosniff** | Hạn chế suy diễn MIME type ở một số loại tài nguyên | Giảm xử lý nội dung sai kiểu dẫn tới script không mong muốn. |
| **Cookie Secure/HttpOnly/SameSite** | Cách cookie được lưu/đọc/gửi | Thu hẹp rủi ro lộ session/CSRF theo ngữ cảnh. |
| **CSRF token** | Kiểm tra thao tác thay đổi trạng thái khi credential tự gửi | Form POST không mong muốn từ site ngoài bị từ chối. |
| **Authentication/authorization** | Danh tính và quyền tại nơi nhận | User có token hợp lệ vẫn không sửa đơn người khác. |

Các cơ chế không hoán đổi cho nhau. Ví dụ:

- CORS cho phép đọc JSON **không chứng minh** người dùng có quyền xem đơn hàng đó.
- CSP frame-src trên parent **không thay** frame-ancestors trên trang được nhúng.
- HSTS bảo vệ lựa chọn HTTPS, **không ngăn** một script XSS trong trang.
- HttpOnly bảo vệ cookie khỏi document.cookie, **không cản** mã cùng origin gọi API bằng phiên.
- CORP/COOP/COEP có thể ảnh hưởng tích hợp browser, nhưng **không thay CSRF token**.

## 11. Sổ tay quyết định mức tin cậy theo từng luồng

Để tránh thiết kế theo cảm tính, lập **trust contract** cho từng đường đi:

| Luồng | Ai là nguồn có thể không đáng tin? | Bằng chứng cần xác minh | Hành động cho phép |
| --- | --- | --- | --- |
| Browser → BFF đọc hồ sơ | Browser/client, input URL | Session hợp lệ, quyền truy cập hồ sơ, phương thức GET | Đọc đúng hồ sơ của principal. |
| Browser → API đổi mật khẩu | Browser, script, website khác | Session, CSRF, quyền, xác thực lại khi cần, password policy | Đổi đúng tài khoản hợp lệ. |
| SPA → API khác origin | Browser origin và user | CORS allowlist + session/token + CSRF nếu áp dụng + authorization | Cấp response cho origin được phép và user đủ quyền. |
| HTML frontend → CDN script | CDN/dependency | Nguồn tin cậy, pin version, SRI/CSP khi dùng | Thực thi mã đã được duyệt. |
| Parent → iframe partner | Bên thứ ba | Origin/sandbox/permissions, postMessage schema | Hiển thị widget, không trao DOM/secret không cần thiết. |
| App → IdP login | Redirect/front-channel, IdP response | state, PKCE, nonce khi OIDC, issuer/audience/chữ ký/expiry | Xác thực user và tạo session ứng dụng. |
| Backend → payment provider | Service config và dữ liệu giao dịch | TLS, service credential, allowlist URL, validation số tiền | Chỉ yêu cầu giao dịch được phép. |
| Payment webhook → backend | HTTP client ngoài, có thể giả mạo | Signature, raw body, timestamp, event ID, trạng thái provider | Cập nhật trạng thái giao dịch theo máy trạng thái nghiệp vụ. |
| Proxy → Spring Boot | Proxy headers/client spoofing | Trusted proxy chain, host allowlist, TLS boundary | Chấp nhận đúng scheme/host/IP được xác lập. |
| Service A → Service B | Service có thể bị chiếm quyền | mTLS/token audience/scope, authorization theo service | Thực hiện thao tác có scope tối thiểu. |

Trong review, mỗi dòng nên có chủ sở hữu, test âm tính và cách phát hiện thất bại. **“Tin đối tác”** chỉ có nghĩa khi được chuyển thành các điều kiện kỹ thuật có thể kiểm chứng và giới hạn.
## 12. Spring Security Servlet: thực thi ranh giới browser ↔ API

Ví dụ cho **Spring Security 6.x trên Servlet/Spring MVC**, với các giả định:

- Frontend tại **https://app.example.com** được phép gọi API tại origin khác bằng CORS.
- Ứng dụng sử dụng **session cookie** cho các request người dùng, nên **giữ CSRF protection**.
- API chứa **/api/** và chỉ mở các method/header cần dùng.
- Trang HTML do ứng dụng phục vụ phải có **CSP** do chính nơi cung cấp HTML thiết lập.
- Một webhook có chữ ký dùng **đường dẫn riêng**, không dựa vào phiên browser hoặc CORS.

### 12.1. SecurityFilterChain cho session/CORS/CSP

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletTrustBoundarySecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(
                                        "default-src 'self'; " +
                                        "script-src 'self'; " +
                                        "connect-src 'self' https://api.example.com; " +
                                        "object-src 'none'; " +
                                        "base-uri 'self'; " +
                                        "frame-ancestors 'none'; " +
                                        "form-action 'self'")))
                // Giữ CSRF mặc định cho ứng dụng session/cookie.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN", "Authorization"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

**Ý nghĩa theo trust boundary:**

1. **CORS** chỉ cho origin được liệt kê đọc response cross-origin. Server vẫn xác thực mọi request được bảo vệ.
2. **CSRF** mặc định áp dụng cho method thay đổi trạng thái trong session-based application. Giữ nó thay vì tắt vì SPA hoặc frontend khác origin.
3. **CSP** giới hạn nguồn script, kết nối, đối tượng được nhúng và nhúng chính trang đó theo policy. Nó không xác nhận user đã đăng nhập.
4. **formLogin** là ví dụ cơ chế xác thực của ứng dụng; không đồng nghĩa ứng dụng đã tích hợp OIDC hay bất kỳ IdP nào.
5. **CORS /api/** không tự mở webhook hoặc mọi tài nguyên khác trong hệ thống.
6. **Max-Age** là preflight cache lifetime theo phản hồi server, browser có thể áp dụng giới hạn riêng.

Một chi tiết triển khai quan trọng: nếu **HTML frontend nằm tại một web server khác** và Spring chỉ phục vụ API JSON, CSP ở API **không bảo vệ trực tiếp document HTML của frontend**. Cần đặt CSP trên **response HTML của app.example.com** hoặc cấu hình edge tương ứng.

Đoạn code giả định authentication provider/session đã được cấu hình theo nhu cầu. Không chứa cơ chế cấp CSRF token cho SPA, quyền chi tiết trên từng resource, HTTPS reverse proxy hay đăng ký IdP; chúng phải được bổ sung theo kiến trúc.

### 12.2. Cookie/session Servlet

Một ví dụ Spring Boot 3.x cho session cookie của ứng dụng:

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        name: __Host-session
        path: /
        secure: true
        http-only: true
        same-site: lax
~~~

Các giá trị là **ví dụ**, không phải chính sách thời gian sống bắt buộc. Với tiền tố **__Host-**, browser yêu cầu cookie có **Secure, Path=/** và **không có Domain**. Nếu ứng dụng phục vụ HTTP trong môi trường phát triển, cần cấu hình khác thay vì tắt HTTPS cookie policy của production.

**HttpOnly** ngăn JavaScript thông thường đọc session ID; nó không ngăn mã XSS cùng origin gọi API hoặc ngăn browser gửi cookie khi có CSRF. Cần phòng vệ XSS, CSRF, timeout và session invalidation tương ứng.

### 12.3. OAuth2/OIDC login là một lựa chọn bổ sung, không phải CORS

Nếu ứng dụng muốn đăng nhập qua IdP, có thể sử dụng **oauth2Login** của Spring Security thay cho form login, sau khi đã đăng ký client và redirect URI phù hợp:

~~~java
// Minh họa một phần bên trong HttpSecurity configuration:
http.oauth2Login(Customizer.withDefaults());
~~~

Cần có **spring-security-oauth2-client** và thông tin client/provider tương ứng: issuer URI hoặc endpoints, client ID, secret khi loại client cần, redirect URI được IdP cho phép và scope. Đăng ký các giá trị này bằng secret management và cấu hình môi trường, không commit client secret vào repository.

Spring Security hỗ trợ nhiều phần của authorization code flow, state và OIDC token validation theo cấu hình; ứng dụng vẫn cần kiểm tra đúng phiên bản, client registration, logout, chính sách session và quyền nghiệp vụ. **Không dùng CORS wildcard hoặc bỏ qua callback validation chỉ để login thành công.**

### 12.4. CSRF token endpoint cho SPA dùng session

Với Spring MVC, một endpoint minh họa có thể expose token từ cơ chế CSRF hiện hành:

~~~java
import java.util.Map;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenController {

    @GetMapping("/api/csrf")
    Map<String, String> csrf(CsrfToken token) {
        return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken());
    }
}
~~~

Dựa vào cấu hình Spring Security, token có thể được cấp/lưu theo repository và cách xử lý **deferred/masked CSRF token**. Phải kiểm tra cách frontend nhận và gửi token phù hợp. Không tự tạo một chuỗi ngẫu nhiên ở JavaScript rồi giả định server sẽ chấp nhận.

Endpoint chứa token không nên được cache ngoài ý muốn và **không mở đọc cho mọi origin với credentials**. Hãy đánh giá nhu cầu endpoint cần authentication và gắn token với phiên theo mô hình đã chọn.

Ví dụ frontend hợp lệ:

~~~javascript
const tokenResponse = await fetch("https://api.example.com/api/csrf", {
  credentials: "include"
});
if (!tokenResponse.ok) throw new Error("Không lấy được CSRF token");

const csrf = await tokenResponse.json();

const response = await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({ productId: 42, quantity: 1 })
});

if (!response.ok) {
  throw new Error("Tạo đơn bị từ chối: " + response.status);
}
~~~

Trong môi trường có **CORS và session cookie** phù hợp, bước POST JSON/custom header thường đi qua OPTIONS preflight. **Preflight đạt không miễn CSRF**; request thực vẫn phải được Spring Security kiểm tra.

### 12.5. Tách ranh giới webhook thay vì tắt CSRF toàn API

Khi nhận webhook, nếu endpoint được xác thực bằng chữ ký provider độc lập và không sử dụng session cookie browser, có thể định nghĩa **ngoại lệ CSRF hẹp**:

~~~java
// Ví dụ một thay đổi có điều kiện trong HttpSecurity:
http.csrf(csrf -> csrf
        .ignoringRequestMatchers("/webhooks/provider"));
~~~

Đây **chỉ là phần CSRF matcher**, không phải hệ thống webhook hoàn chỉnh. Một webhook cần được phép đi tới bộ xác minh chữ ký (ví dụ một chain/route riêng), đồng thời bị từ chối nếu chữ ký không hợp lệ; còn API người dùng vẫn phải xác thực và có CSRF theo chính sách.

**Không dùng permitAll đơn thuần như kết luận “webhook an toàn”**. permitAll chỉ có nghĩa Spring Security authorization không chặn yêu cầu tại matcher đó; **bộ xác minh webhook** vẫn phải kiểm tra raw body, signature, timestamp, chống replay và nghiệp vụ.

Nếu không cần webhook, không thêm ngoại lệ CSRF nào. Chỉ cấu hình ngoại lệ khi có endpoint và cơ chế xác thực service thực tế.

### 12.6. Controller webhook phải kiểm tra trước khi cập nhật dữ liệu

Một giao diện minh họa việc xử lý:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
class PaymentWebhookController {
    private final ProviderWebhookVerifier verifier;
    private final PaymentEventService paymentEvents;

    PaymentWebhookController(
            ProviderWebhookVerifier verifier,
            PaymentEventService paymentEvents) {
        this.verifier = verifier;
        this.paymentEvents = paymentEvents;
    }

    @PostMapping("/webhooks/provider")
    ResponseEntity<Void> receive(
            @RequestBody byte[] rawBody,
            @RequestHeader("X-Provider-Signature") String signature,
            @RequestHeader("X-Provider-Timestamp") String timestamp) {

        // Phải dùng thuật toán/chuỗi ký đúng đặc tả provider.
        verifier.verifyOrThrow(rawBody, signature, timestamp);

        // Service còn phải deduplicate, kiểm tra order/amount/status.
        paymentEvents.processVerifiedEvent(rawBody);
        return ResponseEntity.noContent().build();
    }
}
~~~

**ProviderWebhookVerifier và PaymentEventService** là abstraction do ứng dụng triển khai, không phải class dựng sẵn của Spring. Mẫu này minh họa **thứ tự kiểm tra**, không tự cung cấp HMAC verifier hợp lệ: phải dựa vào tài liệu ký webhook của provider, đặc biệt cách tính chữ ký trên raw bytes, timestamp và cách mã hóa signature.

Tốt hơn là ghi nhận event ID và xử lý **idempotent** cùng giao dịch/queue theo thiết kế, vì provider có thể retry webhook và gửi sự kiện không đúng thứ tự.

## 13. Spring Security Reactive/WebFlux: giữ các ranh giới tương tự

Browser không thay đổi cách áp dụng SOP/CORS/cookie/CSP chỉ vì backend dùng Reactive. Spring Security WebFlux dùng **ServerHttpSecurity**, **SecurityWebFilterChain** và CORS classes trong gói **reactive**.

### 13.1. Cấu hình WebFlux với session và CORS

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveTrustBoundarySecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .authorizeExchange(auth -> auth
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(
                                        "default-src 'self'; " +
                                        "script-src 'self'; " +
                                        "connect-src 'self' https://api.example.com; " +
                                        "object-src 'none'; " +
                                        "base-uri 'self'; " +
                                        "frame-ancestors 'none'; " +
                                        "form-action 'self'")))
                // CSRF mặc định giữ nguyên cho cookie/WebSession.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN", "Authorization"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Đây là lựa chọn **thay thế cho cấu hình Servlet**, không dùng đồng thời chỉ để có đủ hai framework.

Điểm tương đồng:

- Phải hạn chế origin/method/header CORS đúng nhu cầu.
- OPTIONS preflight thường không mang session cookie, nên CORS phải được xử lý trước filter có thể chặn vì không xác thực.
- CSRF vẫn quan trọng khi browser tự gửi cookie/WebSession cho thao tác thay đổi trạng thái.
- CSP và các security headers phải gắn với **response của document HTML** thực sự được browser tải.
- Webhook service-to-service cần xác minh riêng, không dựa vào CORS.

Điểm khác:

- WebFlux sử dụng **WebSession** và reactive security filters.
- CORS source thuộc **org.springframework.web.cors.reactive**, không phải Servlet source.
- Cách cấp CSRF token và session repository có thể sử dụng publisher bất đồng bộ.
- Không dùng trực tiếp HttpSession hoặc HttpServletRequest trong reactive stack.

### 13.2. Cookie WebSession trên HTTPS

Một ví dụ cấu hình cookie ID của WebSession:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class ReactiveCookieConfig {
    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("__Host-session");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax"));
        return resolver;
    }
}
~~~

Đây là cookie của **WebSession** trên WebFlux, không phải JSESSIONID cấu hình bằng server.servlet.session.* của Servlet. Nếu ứng dụng dùng Spring Session Reactive hoặc đã có WebSessionIdResolver tùy chỉnh, cần xác định đúng chủ sở hữu bean để tránh thiết lập mâu thuẫn.

**Không đánh đồng cookie expiry với server-side session validity**. WebSessionStore/session repository có timeout và chính sách riêng; logout cần vô hiệu hóa session server-side theo đúng cơ chế.

### 13.3. OAuth2 login và Resource Server trên WebFlux có nhiệm vụ riêng

Khi WebFlux là OAuth2 Client hỗ trợ đăng nhập browser, có thể xem xét **oauth2Login** sau khi đăng ký client/provider đúng quy tắc. Khi WebFlux là API Resource Server nhận Bearer token, sử dụng **oauth2ResourceServer** và validator token phù hợp.

Đây là **hai vai trò khác nhau**. Một ứng dụng có thể đảm nhiệm cả hai nhưng phải thiết kế rõ chain, endpoint, cookie/session, token audience và CSRF. Không vì API là Resource Server mà tự động vô hiệu hóa CSRF trên tất cả endpoint có cookie đăng nhập.

Ví dụ cấu hình Resource Server trong một chain độc lập (minh họa):

~~~java
// Bên trong một SecurityWebFilterChain dành riêng cho token API:
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Cần có cấu hình decoder/issuer/JWK source và validator **audience** cùng các điều kiện khác. Mẫu trên không tự chứng minh mọi access token có chữ ký đều có quyền gọi API. Đối với endpoint nhạy cảm, cần kiểm tra **scope/authority và quyền trên đối tượng**.

### 13.4. Đọc header WebFlux không phải chứng minh quyền

Trong một handler/filter reactive có **ServerWebExchange exchange**:

~~~java
String origin = exchange.getRequest()
        .getHeaders().getFirst("Origin");
String fetchSite = exchange.getRequest()
        .getHeaders().getFirst("Sec-Fetch-Site");
String tenantId = exchange.getRequest()
        .getHeaders().getFirst("X-Tenant-Id");
~~~

Các giá trị trên chỉ là **dữ liệu request quan sát được**. Principal phải đến từ Spring Security authentication; tenantId phải được phân quyền theo user đã xác thực. Không dùng **Sec-Fetch-Site: same-origin** để bỏ qua authorization, vì client ngoài browser có thể tự khai header đó.
## 14. Kiểm thử ranh giới tin cậy từ browser đến server

Để đánh giá một hệ thống, không đủ thử “đăng nhập thành công” và “API trả 200”. Cần kiểm tra **request từ nguồn không được phép**, **credential thiếu hoặc sai**, **token đúng nhưng không đủ quyền**, **preflight**, **redirect**, **iframe** và **các tầng proxy**.

Chỉ chạy trên **môi trường và tài nguyên bạn có quyền kiểm thử**; sử dụng dữ liệu giả và endpoint không gây thanh toán, xóa hoặc gửi thư thật.

### 14.1. Ma trận kiểm thử theo lớp

| Tình huống | Điều cần quan sát | Kết quả kỳ vọng theo trust contract |
| --- | --- | --- |
| Frontend chính thức đọc JSON API. | Origin, Cookie/Authorization, CORS response. | Chỉ origin hợp lệ và user đủ quyền đọc được dữ liệu. |
| Frontend không nằm trong allowlist. | OPTIONS/actual response và thông báo browser. | Không được CORS cấp quyền đọc dữ liệu có credentials. |
| Origin chứa chuỗi ví dụ example.com nhưng không phải origin được phép. | Access-Control-Allow-Origin. | Không được thông qua bằng substring match. |
| GET cross-origin với Authorization. | OPTIONS và Access-Control-Request-Headers. | Preflight xét Authorization; API vẫn xác thực token thực. |
| POST cross-origin có session nhưng không CSRF. | Request thực và security log. | Bị CSRF protection từ chối trước thay đổi nghiệp vụ. |
| POST có CSRF nhưng user thiếu quyền. | HTTP status và trạng thái tài nguyên. | Bị authorization từ chối. |
| Request từ subdomain same-site không đáng tin. | Sec-Fetch-Site, Origin, cookie. | Không được coi same-site là bằng chứng tin cậy đầy đủ. |
| Trang ngoài cố nhúng trang tài khoản. | frame-ancestors/X-Frame-Options và Console. | Trang nhạy cảm không được nhúng nếu chính sách cấm. |
| postMessage từ origin không cho phép. | event.origin/source và UI state. | Message bị bỏ qua, không cập nhật dữ liệu nhạy cảm. |
| OAuth callback sai state hoặc redirect URI. | Authentication flow. | Không tạo session user từ callback không liên kết flow hợp lệ. |
| Token có chữ ký đúng nhưng audience khác. | JWT validator, response API. | API từ chối token không dành cho mình. |
| Webhook với signature sai hoặc event trùng. | Chữ ký, event log và business state. | Không cập nhật sai; event hợp lệ được xử lý idempotent. |
| Proxy nhận Forwarded từ client giả. | Host/Proto/IP Spring nhìn thấy. | Client không thể điều khiển kết quả tin cậy do proxy cung cấp. |
| CSP chặn nguồn script chưa duyệt. | HTML response và Console CSP. | Script không được chạy trong document khi policy không cho phép. |

### 14.2. DevTools: quan sát cả preflight và actual request

Tại **https://app.example.com**, với API **https://api.example.com**, dùng request GET và POST trong môi trường test:

~~~javascript
const readResponse = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
console.log("GET status", readResponse.status);

// csrfToken phải được ứng dụng cấp theo cơ chế CSRF thật.
const writeResponse = await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42, quantity: 1 })
});
console.log("POST status", writeResponse.status);
~~~

Trong **Network/Console/Application → Cookies**:

1. Xác định **URL khởi tạo**, origin trang và URL đích có redirect hay không.
2. Xem **OPTIONS preflight** có diễn ra, có Origin, Access-Control-Request-Method/Headers nào, trả status nào.
3. Xem request thực **có được gửi** không; Cookie và Authorization có như dự kiến không.
4. Xem response thực có **Access-Control-Allow-Origin**, Allow-Credentials và Vary hợp lệ không.
5. Kiểm tra **401/403 ở server** có do session, CSRF hay quyền không; đừng kết luận mọi lỗi bị browser che là CORS.
6. Kiểm tra **Cookie SameSite, Secure, HttpOnly, Domain/Path** và lý do browser chặn cookie.
7. Nếu CSP báo lỗi, xem **CSP của document HTML frontend**, không chỉ header trên response JSON.

**Không retry POST thanh toán hoặc tạo đơn ngay khi fetch báo lỗi CORS**. Server có thể đã thực hiện giao dịch nhưng browser từ chối đọc response. Kiểm tra trạng thái đơn và cơ chế idempotency trước.

### 14.3. curl kiểm tra CORS policy, nhưng không thực thi SOP

Trong môi trường test, mô phỏng preflight được phép:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Thử origin không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com.attacker.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Địa chỉ **app.example.com.attacker.test** là một origin **khác** với app.example.com, không được vượt qua allowlist chỉ vì chứa chuỗi example.com. Response của origin không được phép **không được cấp CORS access** theo chính sách ứng dụng; status từ chối cụ thể tùy tầng xử lý.

**curl không thực thi SOP, CORS, SameSite hoặc hành vi cookie bên thứ ba như browser**. Nó chỉ cho thấy HTTP response thực từ server. Dùng thêm browser thật để kiểm tra end-to-end.

### 14.4. Kiểm tra callback IdP và redirect

Trong môi trường tích hợp IdP dành cho test:

- Login bình thường từ app và xác minh **state/PKCE/nonce** theo flow được cấu hình.
- Kiểm tra callback thiếu hoặc sai state không được tạo session.
- Kiểm tra **redirect URI** không thể đổi sang host tùy ý bằng input client.
- Kiểm tra ID token từ issuer khác, audience khác hoặc hết hạn bị từ chối.
- Xác minh session của app vẫn bị thu hồi theo chính sách logout kể cả nếu browser còn session tại IdP.
- Quan sát link đăng nhập trở lại: đừng suy ra IdP tự login lại nghĩa là app đã không hủy phiên.

Không đưa client secret hoặc access token vào DevTools screenshot/log chia sẻ công khai. Các luồng kiểm thử token giả phải chạy trên test IdP/issuer được bạn kiểm soát, không trên production của đối tác.

### 14.5. Kiểm tra webhook

Với một **test event** do provider hoặc test harness được phép tạo:

1. Xác minh **chữ ký hợp lệ trên raw body** được chấp nhận.
2. Sửa một byte body sau ký trong môi trường test: request phải bị từ chối bởi verifier.
3. Dùng timestamp đã quá hạn theo chính sách: request không được xử lý nếu giao thức hỗ trợ kiểm tra freshness.
4. Gửi lại cùng event ID: ứng dụng không được xử lý giao dịch nhiều lần.
5. Xác minh sự kiện sai order ID hoặc số tiền không làm thay đổi đơn của người khác.
6. Kiểm tra webhook không thể được gọi hợp lệ chỉ bằng cookie browser/Origin/CORS header.
7. Kiểm tra webhook route đã được bảo vệ trong network/routing hợp lý và có cơ chế chống abuse.

Không viết signature verifier dựa trên cách tự đoán header của provider. Cần dùng **tài liệu đặc tả và dữ liệu test chuẩn** của provider khi triển khai.

### 14.6. MockMvc: CSRF và authorization là hai điều kiện độc lập

Trong Servlet, có thể dùng **spring-security-test**. Ví dụ dưới đây giả định endpoint **POST /api/orders** tồn tại, principal test có quyền tạo đơn khi được xác thực và có CSRF hợp lệ:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class TrustBoundaryMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void postWithInvalidCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("tester"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"productId\":42}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidCsrfMayProceed() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("tester"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"productId\":42}"))
            .andExpect(status().isCreated());
    }
}
~~~

**201 Created là ví dụ kỳ vọng theo controller test**, không bảo đảm cho mọi ứng dụng. Test thực còn cần trường hợp user không có quyền dù token CSRF hợp lệ, request thuộc tenant khác và xác minh dữ liệu không thay đổi sau các trường hợp từ chối.

### 14.7. WebTestClient: nguyên tắc tương tự trên WebFlux

Ví dụ minh họa trong một bài test có **webTestClient** đã cấu hình ứng dụng và security filter chain:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

webTestClient
    .mutateWith(mockUser("tester"))
    .post().uri("/api/orders/42/cancel")
    .exchange()
    .expectStatus().isForbidden();

webTestClient
    .mutateWith(mockUser("tester"))
    .mutateWith(csrf())
    .post().uri("/api/orders/42/cancel")
    .exchange()
    .expectStatus().isNoContent();
~~~

Đây là **đoạn minh họa** và giả định endpoint trả 204 nếu user có quyền, đã vượt CSRF và điều kiện nghiệp vụ. Không coi csrf() trong test là cách client production tự sinh token hợp lệ.

### 14.8. Đối chiếu 401, 403, CORS, CSP và redirect

| Triệu chứng | Ranh giới đáng kiểm tra | Việc nên làm |
| --- | --- | --- |
| Browser có cookie nhưng API trả 401. | Cookie không gửi, session server hết hạn, token sai hoặc chain auth. | Kiểm tra Network Cookie, session store, auth logs. |
| POST có cookie nhưng trả 403. | CSRF token, quyền hoặc nghiệp vụ. | Đọc log filter/authorization, không tắt CSRF vội. |
| OPTIONS trả 401/403, POST không xuất hiện. | CORS filter/gateway chặn preflight. | Kiểm tra thứ tự CORS, Origin, method/header allowlist. |
| POST trả 200/201 nhưng frontend báo CORS. | Actual response CORS hoặc proxy thay header. | Kiểm tra response thực và dữ liệu nghiệp vụ, tránh retry trùng. |
| CORS đúng nhưng browser không gọi được API. | CSP connect-src, Mixed Content, DNS/TLS, redirect. | Xem Console, request URL và headers document. |
| Browser chặn iframe. | frame-ancestors, X-Frame-Options, sandbox. | Kiểm tra policy tại parent và trang được nhúng. |
| Callback IdP bị từ chối. | state, PKCE, redirect URI, nonce/token validation, session. | Kiểm tra flow và cấu hình client registration. |
| API từ chối token có chữ ký hợp lệ. | audience, issuer, scope, user entitlement. | Kiểm tra claims/validator và quyền thật của token. |
| Webhook bị từ chối. | Chữ ký, raw body, timestamp, event ID, route policy. | So với provider contract, không mở CORS để sửa. |
| Redirect sai host hoặc Secure cookie sai. | Trusted Forwarded/Host, TLS reverse proxy. | Kiểm tra edge/proxy config và header đầu vào. |

## 15. Bài tập tình huống: xác định ranh giới bị vượt qua

### Tình huống A — Cùng công ty, khác origin

Công ty vận hành **https://app.example.com** và **https://api.example.com**. Frontend gọi API nhưng browser báo CORS. Một thành viên nói cùng công ty nên browser phải cho đọc response. Đúng không?

**Đáp án:** Không. CORS dựa trên quan hệ origin và chính sách server, không dựa vào chủ sở hữu doanh nghiệp. Hai hostname khác nhau là cross-origin; API cần cấp quyền CORS phù hợp cho frontend, đồng thời xác thực/phân quyền người dùng.

### Tình huống B — Subdomain cùng site nhưng không đáng tin

Một cộng tác viên vận hành **https://blog.example.com**, API là **https://api.example.com**. API xem Sec-Fetch-Site: same-site là bằng chứng tin cậy và không kiểm tra CSRF. Có vấn đề gì?

**Đáp án:** Same-site không đồng nghĩa same-origin hoặc cùng mức tin cậy. Blog có thể bị chiếm quyền. Cần CSRF protection, giới hạn Origin/CORS khi thích hợp và kiểm tra quyền theo user.

### Tình huống C — Script CDN cần đọc DOM?

Website nhúng một script chatbot từ CDN của đối tác. Đối tác chỉ cần hiển thị khung chat, nhưng script chạy trực tiếp trong trang có thể đọc DOM và dữ liệu phía client. Nên xem xét gì?

**Đáp án:** Đây là quyết định **trao quyền JavaScript**. Cân nhắc tích hợp iframe cross-origin sandbox phù hợp, giới hạn postMessage, dùng CSP/SRI khi thích hợp và chỉ trao dữ liệu tối thiểu.

### Tình huống D — Cookie HttpOnly là đủ?

Ứng dụng dùng session cookie Secure và HttpOnly. Có mã độc XSS chạy trong document. Có thể kết luận script không làm gì nguy hiểm vì không đọc được session ID không?

**Đáp án:** Không. Script có thể gọi API bằng phiên đang hoạt động và đọc response hợp lệ theo quyền document. Cần xử lý XSS ở nguồn, CSP, kiểm soát script và phân quyền server-side.

### Tình huống E — CORS wildcard cho API có cookie

API trả Access-Control-Allow-Origin: * đồng thời Allow-Credentials: true. Frontend dùng credentials: include. Browser có cho JavaScript đọc response không?

**Đáp án:** Không. CORS credentialed response không chấp nhận wildcard Allow-Origin. Server cần allowlist origin cụ thể, và vẫn bảo vệ session/CSRF/phân quyền.

### Tình huống F — Form POST không có preflight

Trang ngoài chứa form POST tới endpoint thay đổi địa chỉ giao hàng của user. Browser không làm OPTIONS. CORS API chỉ cho frontend chính thức. Có thể bỏ CSRF không?

**Đáp án:** Không. HTML form có thể gửi request mà không cần preflight; CORS không chặn mọi request có tác dụng phụ. Cần CSRF token và quyền server-side khi dùng cookie/session.

### Tình huống G — OAuth callback thiếu state

Ứng dụng nhận callback đăng nhập từ IdP với authorization code nhưng state không khớp flow đang lưu. Có nên trao đổi code để đăng nhập vì IdP có vẻ uy tín?

**Đáp án:** Không. Callback phải được ràng buộc với request khởi tạo. State không khớp cần bị từ chối theo giao thức; sau đó còn phải xác minh token, issuer, audience và những điều kiện OIDC.

### Tình huống H — ID token dùng để gọi mọi API

Frontend nhận OIDC ID token hợp lệ rồi dùng nó làm Bearer token cho API thanh toán. API có nên chấp nhận chỉ vì token được IdP ký không?

**Đáp án:** Không. ID token phục vụ việc xác thực user với client. API cần token có **đúng loại, audience, scope và quyền** theo hợp đồng; chữ ký hợp lệ không tự cấp quyền truy cập tài nguyên.

### Tình huống I — Client secret nằm trong bundle

Đội frontend đưa payment-provider API key vào file JavaScript đã minify và nghĩ người dùng không thấy. Có an toàn không?

**Đáp án:** Không. Bundle tải xuống browser có thể bị đọc/giải mã. Credential dành cho service phải nằm ở backend/secret store; browser gọi endpoint của ứng dụng và server quyết định có thực hiện thao tác không.

### Tình huống J — Webhook có Origin đúng

Endpoint webhook nhận POST với Origin trông giống provider, nhưng không có chữ ký. Có thể xác nhận webhook hợp lệ không?

**Đáp án:** Không. Webhook là HTTP server-to-server; Origin có thể vắng hoặc bị giả. Phải xác minh chữ ký/cơ chế xác thực provider, timestamp và chống replay theo hợp đồng.

### Tình huống K — Webhook lặp sự kiện

Provider gửi lại cùng eventId do timeout, backend ghi nhận hai lần thanh toán hoàn tất và cộng điểm hai lần. Sai ở đâu?

**Đáp án:** Thiếu **idempotency/deduplication** trong xử lý webhook. Chữ ký hợp lệ không có nghĩa sự kiện chỉ xuất hiện một lần. Cần xác định event ID và chuyển trạng thái nghiệp vụ có kiểm soát.

### Tình huống L — X-Forwarded-Proto do client tự đặt

Backend dùng X-Forwarded-Proto: https từ mọi request để sinh URL nhạy cảm, dù request có thể kết nối trực tiếp không qua proxy. Có đúng không?

**Đáp án:** Không. Client ngoài có thể tự đặt header. Chỉ tin forwarded headers từ proxy xác định được và đã làm sạch/ghi đè các header không tin cậy.

### Tình huống M — postMessage từ origin khác

Parent nhận event.data.status từ mọi origin và dùng innerHTML để hiển thị. Vì dữ liệu đến qua postMessage nên an toàn?

**Đáp án:** Không. Cần kiểm tra event.origin, event.source, schema và dùng textContent/DOM API an toàn. postMessage không tự xác thực quyền thay đổi dữ liệu ở backend.

### Tình huống N — Iframe bị từ chối nhúng

Frontend đã thêm frame-src cho phép checkout.partner.test nhưng browser vẫn từ chối nhúng checkout. Tại sao?

**Đáp án:** Parent cho phép tải iframe không bảo đảm trang checkout cho phép bị nhúng. Cần kiểm tra **frame-ancestors/X-Frame-Options của response trang checkout**, sandbox, browser policy và hợp đồng nhà cung cấp.

### Tình huống O — Service A mang token dành cho Service B

Một access token có chữ ký đúng nhưng audience chỉ dành cho inventory API; orders API nhận token đó và cấp dữ liệu vì chữ ký hợp lệ. Thiết kế này đúng không?

**Đáp án:** Sai. Resource Server phải xác minh audience và scope/quyền phù hợp với chính nó. Bỏ kiểm tra audience tạo nguy cơ dùng token cho sai mục đích.

### Tình huống P — BFF tải URL do browser chỉ định

BFF nhận URL tuyệt đối từ frontend và tải dữ liệu để tạo preview. Endpoint có nguy cơ gì?

**Đáp án:** **SSRF**, vì backend có thể truy cập mạng/tài nguyên mà browser ngoài không truy cập được. Cần allowlist đích, kiểm soát DNS/IP/redirect/port, egress policy và giới hạn response.

### Tình huống Q — CSP chỉ được đặt ở API JSON

HTML frontend nằm ở app.example.com, còn API JSON ở api.example.com. Đội backend đặt CSP script-src chặt chẽ trên JSON và khẳng định HTML của SPA đã được bảo vệ XSS. Đúng không?

**Đáp án:** Không. CSP bảo vệ document nhận policy. Cần đặt CSP phù hợp trên **response HTML của origin phục vụ frontend**; CSP JSON của API không tự chuyển sang document khác origin.

### Tình huống R — Cookie SameSite=None cho iframe

Đối tác yêu cầu iframe hoạt động cross-site, backend đặt cookie SameSite=None; Secure. Có chắc browser sẽ gửi cookie và iframe đăng nhập thành công trên mọi trình duyệt không?

**Đáp án:** Không. Browser còn có chính sách third-party cookie, partitioning và storage access riêng. Cần kiểm thử trên browser mục tiêu và thiết kế fallback hợp lệ, không đưa credential vào URL để lách chính sách.

### Tình huống S — User hợp lệ nhưng không thuộc tenant

User có session hợp lệ, CSRF token đúng, CORS origin đúng và X-Tenant-Id trỏ tới tenant của người khác. Backend có được trả dữ liệu tenant đó không?

**Đáp án:** Không. CORS, session và CSRF không tự chứng minh quyền tenant. Server phải đối chiếu principal và quyền truy cập **tài nguyên/tenant cụ thể**, bỏ qua mọi đặc quyền client tự khai.

### Tình huống T — Login xong nhưng HSTS khiến dịch vụ phụ lỗi

Hệ thống bật HSTS includeSubDomains rồi một subdomain cũ chỉ hỗ trợ HTTP không còn truy cập được. Có nên cho rằng browser bị lỗi CORS?

**Đáp án:** Không. Đây là tác động của chính sách HTTPS/HSTS, khác CORS. Cần kiểm kê mọi subdomain trước khi bật includeSubDomains và chuyển các dịch vụ hợp lệ sang HTTPS phù hợp.

## 16. Checklist threat modeling và review triển khai

### 16.1. Vẽ mô hình dữ liệu và quyền

- [ ] Liệt kê **origin và site** của frontend, API, BFF, IdP, CDN, iframe đối tác, webhook và reverse proxy.
- [ ] Ghi rõ **ai kiểm soát** từng host, endpoint, script và credential.
- [ ] Vẽ luồng **browser-to-server**, **server-to-server**, **redirect front-channel** và **webhook callback** riêng biệt.
- [ ] Với mỗi luồng, ghi tài sản nhạy cảm, dữ liệu đầu vào có thể giả và **nơi quyết định quyền cuối cùng**.
- [ ] Đánh giá subdomain same-site do đối tác điều khiển hoặc có thể bị takeover.
- [ ] Gán mức quyền tối thiểu, thời gian sống và cơ chế rotation/revocation cho từng credential.

### 16.2. Kiểm tra browser và frontend

- [ ] HTML frontend có CSP phù hợp trên đúng origin/document, có kế hoạch quản lý script bên thứ ba.
- [ ] Không tin DOM input, URL query/hash, postMessage hoặc localStorage làm dữ liệu cấp quyền.
- [ ] Script bên thứ ba được kiểm soát; iframe/sandbox và postMessage dùng origin/schema rõ ràng.
- [ ] Cookie session có Secure/HttpOnly/SameSite/Path/Domain phù hợp và session server-side timeout/revocation.
- [ ] CORS cấp quyền theo allowlist origin/method/header cụ thể; không phản chiếu mọi Origin khi dùng credentials.
- [ ] CSRF token được cấp và kiểm tra cho unsafe method dựa trên cookie/session.
- [ ] GET/HEAD chỉ truy vấn; không hủy đơn, đổi mật khẩu, logout hoặc thực hiện tác vụ nghiệp vụ.
- [ ] Trang nhạy cảm có frame-ancestors/X-Frame-Options theo nhu cầu và các header bảo mật khác.
- [ ] Dữ liệu riêng tư trong response/cache/service worker không bị tồn tại hoặc lộ ngoài chính sách.

### 16.3. Kiểm tra backend và tích hợp bên thứ ba

- [ ] Authentication trả một principal tin cậy; authorization kiểm tra theo từng endpoint/tài nguyên.
- [ ] OAuth2/OIDC login dùng state, PKCE và ID token validation thích hợp; redirect URI hạn chế.
- [ ] API Resource Server kiểm tra issuer, audience, expiry, scopes và quyền chi tiết.
- [ ] Service credential không xuất hiện trong bundle frontend, HTML, URL, client log hoặc localStorage không cần thiết.
- [ ] Backend outbound có allowlist/network egress policy để chống SSRF khi URL chịu ảnh hưởng client.
- [ ] Webhook kiểm tra signature, raw body, freshness, replay, idempotency và chuyển trạng thái nghiệp vụ hợp lệ.
- [ ] Trusted proxy chain được xác định, Forwarded/Host không do client tùy ý quyết định.
- [ ] HTTPS/HSTS, cookie Secure, CSP và redirects hoạt động nhất quán qua gateway.
- [ ] HTTP firewall, proxy và backend có cách hiểu method/path/headers nhất quán, không nới rộng để né lỗi.

### 16.4. Chấp nhận hệ thống bằng test âm tính

- [ ] Browser từ origin không được phép không đọc được response credentialed cross-origin.
- [ ] POST thiếu/sai CSRF token bị từ chối trước khi thay đổi dữ liệu.
- [ ] POST có CSRF token hợp lệ nhưng user thiếu quyền vẫn bị từ chối.
- [ ] OAuth callback thiếu/sai state, token sai audience hoặc hết hạn bị từ chối.
- [ ] Webhook signature sai, timestamp cũ và event trùng không gây cập nhật sai.
- [ ] Proxy header do client tự đặt không vượt được trust boundary.
- [ ] Iframe/postMessage từ origin không được phép không điều khiển được giao diện nhạy cảm.
- [ ] Logout thu hồi session/token theo chính sách, không chỉ ẩn giao diện.
- [ ] Khi CORS/CSP chặn response, kiểm tra server **đã xử lý request thực hay chưa** trước khi retry.
- [ ] Có log quan sát nguyên nhân nhưng không làm lộ session ID, access token, signature hoặc dữ liệu cá nhân ngoài cần thiết.

## 17. Ghi nhớ

1. **Trust boundary không trùng hoàn toàn với ranh giới mạng, origin hay tên miền công ty.** Mỗi chủ thể và mỗi đường truyền cần điều kiện tin cậy riêng.
2. **Browser có thể tự gửi cookie** nhưng điều đó không chứng minh ý định của user; **CSRF token** và authorization bảo vệ thao tác thay đổi trạng thái theo mô hình xác thực sử dụng.
3. **SOP/CORS** giới hạn quyền đọc response cross-origin của JavaScript; chúng không thay server authentication và không ngăn mọi form/điều hướng có tác dụng phụ.
4. **Script bên thứ ba nhúng trực tiếp** có thể chạy với quyền document; iframe cross-origin và sandbox thường tạo ranh giới cách ly tốt hơn khi dùng đúng cách.
5. **CSP script-src/connect-src/frame-src/frame-ancestors** điều khiển các ranh giới khác nhau. CSP phải nằm trên **response của document cần bảo vệ**.
6. **OAuth2/OIDC** cần state, PKCE, nonce khi áp dụng, đúng redirect URI, issuer và audience; **ID token không phải access token cho mọi API**.
7. **Service-to-service** dùng credential riêng và không bị browser CORS chi phối. Giữ API secrets ở backend, giới hạn scope và chống SSRF.
8. **Webhook** phải xác minh chữ ký/cơ chế provider, freshness và idempotency; không dùng Origin, Referer hay CORS làm bằng chứng xác thực webhook.
9. **Forwarded/X-Forwarded-*** chỉ được tin từ proxy đã xác lập và làm sạch, không lấy trực tiếp header do client tự khai làm host/scheme/IP đáng tin.
10. Với **Spring Security Servlet và WebFlux**, chọn đúng API bảo mật, giữ CSRF cho session/cookie, cấu hình CORS/CSP theo đúng nơi cần áp dụng và kiểm thử cả những request **bị từ chối**.
11. Một hệ thống được coi là có trust model rõ ràng khi người vận hành có thể giải thích cho mỗi request: **ai khởi tạo, credential nào được gửi, nơi nào xác thực, nơi nào phân quyền và vì sao dữ liệu được phép rời khỏi ranh giới đó**.


