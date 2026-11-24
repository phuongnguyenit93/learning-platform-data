# Bảo vệ UI consent khỏi giả mạo

## Mục tiêu học tập

Trong chương **Consent** của học phần **Token Security Fundamentals**, **UI consent** là nơi người dùng quyết định có cho một OAuth Client sử dụng những quyền truy cập tài nguyên được mô tả hay không. Trong **Authorization Code + PKCE** hoặc quá trình xác minh **Device Authorization Grant**, giao diện này thường do **Authorization Server (AS)** hoặc **OpenID Provider (OP)** kiểm soát. Đây là điểm nhạy cảm: một lần bấm “Cho phép” có thể khiến AS phát hành authorization grant, rồi phát **access token** và đôi khi **refresh token** cho Client.

**Bảo vệ UI consent khỏi giả mạo** không chỉ là thiết kế nút bấm đẹp hoặc đưa HTTPS vào đường dẫn. Cần chống ít nhất ba nhóm rủi ro: **trang giả mạo AS** lấy mật khẩu/mã; **Client độc hại tận dụng trang AS thật** để lừa người dùng cấp quyền; và **giao diện hoặc request consent bị can thiệp** khiến AS cấp quyền khác điều người dùng đã thấy.

Sau bài này, bạn có thể:

1. Nhận diện **phishing, consent phishing, client impersonation, clickjacking, XSS, CSRF và transaction tampering** trong màn hình xin quyền.
2. Phân biệt **nguồn gốc giao diện (origin)**, **danh tính Client**, **scope/resource được hiển thị** và **authorization grant thực tế**.
3. Thiết kế màn hình AS minh bạch về ứng dụng, nhà phát hành, tài khoản, tenant, API, mục đích, thời hạn và quyền truy cập ngoại tuyến.
4. Ràng buộc quyết định “Cho phép/Từ chối” với **authorization transaction đã được AS xác minh**, thay vì tin các field do browser gửi lại.
5. Áp dụng **CSP `frame-ancestors`, chống clickjacking, form CSRF protection, session cookie, origin checks, HTML escaping và logging redaction** đúng vai trò.
6. Hiểu các biện pháp bổ sung ở **redirect URI, OAuth `state`, PKCE, PAR, JAR, mobile callback và device-code confirmation** mà không coi chúng là vật thay thế consent.
7. Lập ma trận kiểm thử và kế hoạch xử lý sự cố khi người dùng đã cấp quyền cho một Client giả mạo.

## 1. Consent UI là một ranh giới tin cậy

Giả sử **Spend Insights** muốn xem đơn hàng của người dùng trên **Orders API**:

~~~text
Authorization Server: https://auth.example.test
Client ID:            spend-insights-web
Tên hiển thị:         Spend Insights
User:                user-123
Tenant:              tenant-a
Resource:            orders-api
Requested scope:     orders:read
Redirect URI:        https://app.example.test/oauth/callback
~~~

Nếu AS hiển thị:

> “Spend Insights muốn xem các đơn hàng mà tài khoản của bạn được phép truy cập.”

và user chấp thuận, **quyết định được ghi phải áp dụng cho đúng client, user, tenant, resource và scope đó**. Một Client khác không được hưởng consent, và không được cấp quyền `orders:write` chỉ vì form POST bị sửa.

### Bốn điều kiện để một quyết định consent đáng tin

| Điều kiện | Câu hỏi | Nếu thiếu |
|---|---|---|
| **Nguồn gốc UI đáng tin** | User có thực sự tương tác với giao diện do AS hợp lệ kiểm soát không? | Trang giả mạo có thể lấy mật khẩu, mã MFA hoặc đánh lừa người dùng. |
| **Thông tin được hiển thị chính xác** | Client, mục đích, account, resource và scope có phản ánh request đã xác minh không? | Người dùng có thể chấp thuận quyền khác với điều mình nghĩ. |
| **Tương tác không bị cưỡng ép/can thiệp** | UI có bị clickjacking, XSS, CSRF hoặc nội dung không tin cậy tác động không? | Quyết định có thể bị tạo hoặc thay đổi mà user không chủ ý. |
| **Grant gắn đúng transaction/policy** | AS có lưu đúng sự chấp thuận cho đúng ngữ cảnh và giới hạn quyền không? | Một lần bấm đúng có thể bị dùng để phát code/token sai. |

**Login thành công không đồng nghĩa user consent**, và **consent thành công không thay thế authorization tại Resource Server**. Sau khi AS cấp access token, API vẫn phải xác minh issuer, audience, scope, trạng thái token và quyền trên đối tượng cụ thể.

### Hai loại giả mạo dễ bị đánh đồng

1. **Fake AS page:** attacker dựng website có giao diện như `auth.example.test` để chiếm thông tin hoặc dụ người dùng bấm một thao tác không thuộc AS.
2. **Malicious Client + real AS consent:** attacker đăng ký một Client dưới tên/logo giống ứng dụng uy tín, đưa nạn nhân tới **AS thật**, rồi xin quyền nhạy cảm. AS có thể phát token **hợp lệ cho Client của attacker** nếu chính sách đăng ký và consent yếu.

Đối phó loại thứ hai **không chỉ bằng “hãy kiểm tra trang đăng nhập HTTPS”**. Nạn nhân có thể đang ở **đúng domain AS** mà vẫn đang cấp quyền cho một ứng dụng độc hại.

## 2. Mô hình đe dọa: kẻ tấn công kiểm soát được phần nào?

| Bên/ranh giới | Dữ liệu attacker có thể kiểm soát | Hậu quả nếu AS hoặc user tin nhầm |
|---|---|---|
| **Client registration độc hại** | App name, logo, website, privacy URL, redirect URI được xin đăng ký. | Giả danh thương hiệu, khiến người dùng cấp quyền cho Client sai. |
| **Authorization request** | `client_id`, `scope`, `redirect_uri`, `resource` và tham số khác tùy chính sách. | Xin scope rộng, lừa chuyển hướng hoặc trộn giao dịch. |
| **Website khác origin** | HTML/iframe, link, nút phủ trong trang attacker. | Clickjacking hoặc phishing dẫn đến AS thật. |
| **Browser bị chèn nội dung** | Script độc hại khi có XSS, extension độc hại, nội dung bên thứ ba. | Sửa UI, đọc dữ liệu được phép truy cập, kích hoạt thao tác trong phiên. |
| **Form POST từ browser** | Các field do user agent gửi có thể bị thay. | Nâng scope, đổi client, đổi tenant nếu server tin form. |
| **Redirect/callback** | Dữ liệu query, callback đã bị cấy hoặc URI sai nếu cấu hình yếu. | Lộ code, nhận nhầm giao dịch OAuth. |
| **Thiết bị khác của attacker** | Device flow được tạo sẵn, `user_code` và `device_code` của chính attacker. | Dụ user chấp thuận để attacker nhận token. |
| **Log/telemetry/support** | Bản ghi có thể phơi URL, mã, token hoặc thông tin grant. | Token/code bị đánh cắp hoặc thông tin nhạy cảm bị lộ. |

Không phải attacker luôn có thể sửa mọi thành phần cùng lúc. Thiết kế an toàn cần xác định **ranh giới tin cậy riêng**: AS được kiểm soát, Client metadata phải được xét duyệt, browser/form không phải nguồn quyết định grant, và RS không tự tin token chỉ vì đã thấy consent.

### Phân biệt mục tiêu tấn công

~~~mermaid
flowchart TD
    A["Attacker muốn lạm dụng quyền OAuth"] --> B{"Kênh tấn công"}
    B --> C["Fake login/consent origin"]
    B --> D["Client giả danh trên AS thật"]
    B --> E["UI bị phủ/chèn script/CSRF"]
    B --> F["Consent transaction bị sửa"]
    C --> G["Đánh cắp credential hoặc dẫn sang cấp quyền sai"]
    D --> H["Token hợp lệ được cấp cho client độc hại"]
    E --> I["User vô tình phê duyệt hoặc UI bị thay"]
    F --> J["Grant khác request đã hiển thị"]
    G --> K["Dữ liệu hoặc quyền user bị lạm dụng"]
    H --> K
    I --> K
    J --> K
~~~

## 3. Vị trí consent UI trong Authorization Code + PKCE

Màn hình consent thường xuất hiện khi user đã đến AS qua authorization request hợp lệ và **policy yêu cầu quyết định**. Không phải mọi login OIDC đều bắt hiển thị lại consent; có thể có grant đã được duyệt, first-party policy hoặc admin approval. Tuy vậy, AS vẫn phải đưa ra quyết định authorization đúng.

~~~mermaid
sequenceDiagram
    actor U as User
    participant B as Browser
    participant C as OAuth Client/BFF
    participant AS as Authorization Server
    participant RS as Orders API
    U->>B: Chọn kết nối Spend Insights
    B->>C: Bắt đầu OAuth
    C->>C: Tạo state, PKCE verifier/challenge
    C-->>B: Redirect tới AS /authorize
    B->>AS: client_id, redirect_uri, scope, resource, state, challenge
    AS->>AS: Verify client, redirect, user session, tenant/resource policy
    AS-->>U: Consent UI của AS nếu cần
    alt User từ chối
        U->>AS: Chọn Từ chối
        AS-->>B: OAuth error access_denied tới redirect hợp lệ
        B->>C: error + state
        C-->>B: Không kết nối, không nhận quyền
    else User chấp thuận quyền được phép
        U->>AS: Chọn Cho phép
        AS->>AS: Ràng buộc consent với transaction và grant
        AS-->>B: Authorization code + state
        B->>C: Callback
        C->>C: Verify state/session/issuer binding
        C->>AS: POST /token với code + PKCE verifier + client auth nếu cần
        AS-->>C: Access token đúng resource/scope
        C->>RS: Bearer token cho Orders
        RS->>RS: Verify token và quyền owner/tenant
        RS-->>C: Chỉ dữ liệu được phép
    end
~~~

### Điểm phải xác định rõ

- **Client** tạo đề nghị scope, nhưng **không quyết định** scope được cấp.
- **AS** sở hữu trang consent và **ghi nhận quyết định sau khi kiểm tra chính sách**.
- **Authorization code** là giá trị ngắn hạn, một lần, ràng buộc Client/redirect/PKCE, không phải access token.
- **PKCE** bảo vệ code exchange, không chống một Client giả mạo thương hiệu được user chấp thuận.
- **`state`** bảo vệ liên kết callback với lượt khởi tạo tại Client; CSRF của form consent ở AS là một lớp khác.
- **RS** không thấy UI consent; RS chỉ nhận token và dữ liệu ngữ cảnh đã được xác minh.

## 4. Bảo vệ origin: trang consent thật phải thuộc AS đáng tin

**Origin** của trình duyệt là bộ ba **scheme + hostname + port**. Một trang ở `https://auth.example.test` và trang `https://auth-example.test` là **hai origin khác nhau**, dù màu sắc và tên hiển thị gần như giống nhau.

### Các kiểu địa chỉ dễ đánh lừa

~~~text
AS hợp lệ:
    https://auth.example.test/consent

Địa chỉ đáng ngờ:
    http://auth.example.test/consent
    https://auth.example.test.attacker.invalid/consent
    https://auth-example.test/consent
    https://login-example.test/verify
    https://attacker.invalid/redirect?next=https://auth.example.test
~~~

Tất cả host trong bảng là ví dụ. Domain/subdomain gần giống, ký tự Unicode đồng hình (*homograph*), tên thương hiệu trong đường dẫn, icon ổ khóa hoặc logo đẹp **không chứng minh** website thuộc AS được tổ chức chấp thuận.

### Tổ chức vận hành AS nên làm gì?

1. Dùng **domain AS rõ ràng và ổn định**, công bố trong tài liệu/onboarding chính thức.
2. Dùng **HTTPS/TLS được xác minh**; không redirect giao diện consent sang HTTP plaintext.
3. Thiết lập **HSTS** theo chiến lược domain để giảm downgrade sang HTTP; HSTS **không ngăn một domain giả có HTTPS riêng**.
4. Giảm số host có thể đăng nhập/consent; tránh nhiều domain không nhất quán gây khó phân biệt.
5. Không đưa user tới đường dẫn consent nhận **arbitrary redirect destination** từ query.
6. Dùng chính sách URL/branding và kênh thông báo **ngoài trang đang nghi giả** để người dùng xác minh.
7. Khi thay đổi domain AS, triển khai kế hoạch migration/trust update được phê duyệt; không để một Client tự chọn website consent mới.

### User nên kiểm tra điều gì?

User nên bắt đầu từ tính năng mình **tự khởi tạo**, xem domain AS trong trình duyệt hệ điều hành khi có thể và đọc **tên Client/quyền**. Không nhập mật khẩu, OTP, mã khôi phục hoặc `user_code` theo liên kết bất ngờ từ email/chat/call center. Tuy nhiên, user không thể là lớp bảo vệ duy nhất: hệ thống phải chặn các request/Client không hợp lệ **ngay cả khi user bị lừa**.

## 5. Chặn Client giả danh bằng metadata và registration policy

**Consent phishing trên AS thật** thường bắt đầu trước khi user thấy trang consent: attacker cố đưa Client có tên/logo/website giống ứng dụng đáng tin vào hệ thống.

### Tại sao `client_id` chưa đủ?

`client_id` xác định một đăng ký OAuth, nhưng không phải người dùng nào cũng hiểu chuỗi như `app-8f21`. AS thường hiển thị **tên ứng dụng, publisher, logo, website và mô tả scope**. Nếu các thuộc tính này đến từ đầu vào không được kiểm duyệt, attacker có thể dựng UI “Ứng dụng ngân hàng chính thức muốn truy cập…” dù thực tế không có chứng cứ xác minh.

### Metadata minh họa

~~~json
{
  "client_id": "spend-insights-web",
  "client_name": "Spend Insights",
  "logo_uri": "https://assets.example.test/spend-insights-logo.png",
  "client_uri": "https://app.example.test",
  "policy_uri": "https://app.example.test/privacy",
  "redirect_uris": ["https://app.example.test/oauth/callback"],
  "allowed_scopes": ["orders:read"],
  "publisher_status": "verified-by-AS-policy"
}
~~~

**Đây là metadata do ví dụ tự định nghĩa**, không phải toàn bộ schema chuẩn: `allowed_scopes` và `publisher_status` chỉ minh họa chính sách nội bộ của AS, không phải trường bắt buộc trong OAuth Dynamic Client Registration. **Không tự hiện nhãn “Đã xác minh”** chỉ vì client đã gửi chuỗi `publisher_status`.

### Kiểm soát metadata

| Đối tượng | Kịch bản lạm dụng | Kiểm soát |
|---|---|---|
| **`client_name`** | Tên giống ứng dụng khác, ký tự đồng hình, tên “IT Support”. | Chống đăng ký tên gây nhầm lẫn, xác minh publisher đối với app nhạy cảm. |
| **`logo_uri`** | Logo giả, URL nội bộ gây SSRF, SVG/script không tin cậy. | Proxy ảnh/kiểm tra nguồn an toàn, sanitize, content type và giới hạn kích thước. |
| **`client_uri`/`policy_uri`** | Link dẫn đến phishing website. | URL validation, hiển thị domain rõ, kiểm duyệt theo chính sách. |
| **`redirect_uri`** | Chuyển authorization code sang host attacker. | Đăng ký/so khớp chính xác theo OAuth profile, chặn open redirect. |
| **Publisher badge** | Attacker tự khai “verified”. | Badge chỉ do AS xác minh và cấp, tách khỏi self-declared metadata. |
| **Client category** | App ít tin cậy xin scope rủi ro cao. | Review/risk-based policy, admin approval hoặc từ chối. |

**Client registration là ranh giới bảo mật**, không chỉ là bước tạo cấu hình. Việc AS chấp nhận một Client chưa biết không có nghĩa user phải tin Client ấy. Một số hệ thống cần phân biệt first-party, ứng dụng đối tác đã được xác minh và ứng dụng bên thứ ba chưa xác minh.

### Tránh “logo là bằng chứng”

Logo, favicon, màu chủ đạo hoặc tên có từ “official” **không là chứng cứ độc lập**. Khi hiển thị ứng dụng, AS nên cung cấp định danh/publisher có thể xác minh; nếu chưa xác minh, nói rõ tình trạng thay vì trang trí bằng biểu tượng đáng tin giả.

## 6. Hiển thị scope và resource đúng quyền được xin

Không để mô tả scope đến từ tham số tùy ý kiểu:

~~~text
GET /consent?client_name=Trusted Bank
    &display_scope=Read only
    &actual_scope=payments:refund
~~~

Nếu backend tin các text đã được browser/Client gửi để dựng trang hoặc ghi grant, user có thể thấy “Chỉ đọc” nhưng token thực tế có `payments:refund`.

### Bảng hiển thị theo hợp đồng quyền

| Scope/resource | Mô tả cho người dùng | Mức rủi ro ví dụ |
|---|---|---|
| `orders:read` / Orders API | Xem các đơn hàng mà bạn được phép đọc. | Có thể chứa thông tin cá nhân. |
| `orders:write` / Orders API | Tạo/chỉnh sửa đơn theo quyền tài khoản. | Có thể thay đổi dữ liệu. |
| `payments:refund` / Billing API | Yêu cầu hoàn tiền theo chính sách. | Nhạy cảm, cần phê duyệt mạnh. |
| `reports:export` / Reports API | Xuất dữ liệu báo cáo được cấp quyền. | Nguy cơ đưa dữ liệu ra ngoài. |
| `offline_access` theo OIDC | Cho ứng dụng duy trì quyền truy cập khi bạn không trực tiếp dùng ứng dụng. | Quyền dài hạn; phụ thuộc profile và refresh token policy. |

Mô tả trên chỉ minh họa; **tên scope không tự định nghĩa toàn bộ quyền**. AS/RS phải có mapping đáng tin từ **scope + resource + policy** đến hành động thực tế. Không đưa một scope tên `read` của API A sang nghĩa quyền đọc của API B.

### Consent UI nên hiện những ngữ cảnh nào?

~~~text
Ứng dụng yêu cầu: Spend Insights
Nhà phát hành:    Publisher đã được AS xác minh theo trạng thái thực tế
Tài khoản:        user-123
Tổ chức:          tenant-a
Tài nguyên:       Orders API

Ứng dụng muốn:
  ✓ Xem các đơn hàng mà bạn được phép đọc  (orders:read)

Không cho phép:
  ✗ Chỉnh sửa hoặc xóa đơn
  ✗ Hoàn tiền

Thời gian/duy trì truy cập:
  Theo grant và chính sách được hiển thị riêng khi cần.

Bạn có thể quản lý ứng dụng đã kết nối tại cài đặt tài khoản.

[Từ chối]               [Cho phép đọc đơn hàng]
~~~

Đây là bản nháp nội dung UI; không khẳng định publisher ví dụ đã được xác minh trong một AS có thật.

### Tránh dùng consent để bỏ qua chính sách

Giả sử:

~~~text
Client requested scopes = {orders:read, orders:write, payments:refund}
Client allowed scopes   = {orders:read, orders:write}
Tenant allowed scopes   = {orders:read}
User entitlement        = {orders:read, orders:write}
User approved           = {orders:read}

Maximum granted scope:
  orders:read
~~~

AS phải **từ chối hoặc cấp scope hẹp hơn theo policy/profile**; không cấp quyền vượt registration, entitlement hoặc quyết định user. Nếu hệ thống không hỗ trợ partial consent, không tạo checkbox giả mà thực tế vẫn cấp toàn bộ scope.

## 7. Chống HTML injection và XSS trên trang consent

Trang consent đôi khi hiển thị metadata của Client: tên, mô tả, domain, đường dẫn privacy hoặc logo. Những dữ liệu này **không phải mã HTML đáng tin**.

### Ví dụ tấn công

~~~html
<!-- ANTI-PATTERN: client_name do Client tự khai bị chèn như HTML. -->
<div class="client-name">
  <img src=x onerror="/* attacker-controlled JavaScript */">
</div>
~~~

Nếu template server hoặc frontend gắn chuỗi không tin cậy vào `innerHTML`, script có thể chạy **trong origin của AS** nếu CSP/sanitization thất bại. Một XSS trong trang consent có thể sửa text scope, kích hoạt form, thao túng DOM hoặc đọc dữ liệu mà script trong origin được phép tiếp cận.

### Cách giảm nguy cơ

1. **HTML-escape theo ngữ cảnh** mọi chuỗi từ Client registry, request, user profile và external metadata.
2. Ưu tiên **text node/`textContent`** thay vì `innerHTML` cho tên/mô tả.
3. Không đưa raw Client-provided Markdown/HTML vào consent page; nếu sản phẩm bắt buộc rich text, dùng sanitizer được bảo trì và allowlist rất hẹp.
4. Dùng **Content Security Policy (CSP)** hạn chế script, frame, base URI và form action; CSP là lớp phòng thủ bổ sung, không thay escaping.
5. Tránh inline event handlers và script từ domain không tin cậy.
6. Giới hạn/sanitize `logo_uri`, loại nội dung nguy hiểm, kích thước và các URL không được phép; cân nhắc image proxy an toàn.
7. Chống **stored XSS** từ Client metadata đã đăng ký trước đó và **reflected XSS** từ query params.
8. Kiểm thử các trường hợp ký tự đặc biệt, HTML entities, Unicode, nested tags và tình huống DOM update sau API fetch.

### Render text thay vì HTML

~~~javascript
// Ví dụ frontend thuần; clientInfo đến từ backend AS đã xác minh.
const nameNode = document.querySelector("#client-name");
nameNode.textContent = clientInfo.displayName;

// Tránh:
// nameNode.innerHTML = clientInfo.displayName;
~~~

**Không có đoạn JavaScript này là hệ thống tự đủ an toàn**; backend vẫn phải kiểm soát nguồn metadata và quyền, và trang cần CSP, CSRF, session management. Một extension độc hại hoặc trình duyệt bị chiếm có thể nằm ngoài mô hình bảo vệ web thông thường.

## 8. Chống clickjacking bằng chính sách frame

**Clickjacking** xảy ra khi attacker nhúng trang consent AS vào iframe/khung hoặc phủ lớp giao diện khiến user **tưởng mình bấm một nút vô hại**, nhưng click thực tế rơi vào “Cho phép” ở trang AS.

### Kịch bản

~~~text
https://promo.attacker.invalid
  └── Nội dung giả: "Bấm để nhận ưu đãi"
      └── iframe consent thật từ https://auth.example.test
          (trong suốt/đè lệch vị trí)

User click -> có thể trúng nút Allow của AS.
~~~

### Header nên xem xét cho UI consent

~~~http
HTTP/1.1 200 OK
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
X-Frame-Options: DENY
Cache-Control: no-store
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
~~~

**Ví dụ policy cần điều chỉnh theo tài nguyên/JavaScript thật**: khi dùng script nonce, ảnh qua CDN tin cậy hoặc tài nguyên khác, CSP phải được thiết kế và kiểm thử. `frame-ancestors 'none'` chặn trang consent **bị nhúng bởi origin khác**, còn `X-Frame-Options: DENY` hỗ trợ các client cũ hơn; không phải tất cả browser xử lý hai cơ chế giống nhau.

### Những sai lầm thường gặp

- `frame-src 'none'` **không thay** `frame-ancestors 'none'`: thuộc tính thứ nhất kiểm soát frame **do trang của ta tải**, thuộc tính thứ hai kiểm soát **ai được nhúng trang của ta**.
- CSS `pointer-events`, thêm một lớp overlay hoặc JavaScript frame-busting **không là thay thế đáng tin** cho header chống iframe.
- Chặn iframe không thay **CSRF protection**: trang attacker vẫn có thể thử gửi request cross-site nếu backend thiếu bảo vệ.
- `SameSite` cookie giúp giảm một số luồng cross-site, nhưng không tự chứng minh user đã chủ động nhấn “Cho phép”.

### Nếu sản phẩm cần nhúng consent vào iframe?

Mặc định nên **không nhúng** trang consent/login nhạy cảm. Nếu một luồng nhúng là yêu cầu bắt buộc, cần **đánh giá threat model**, allowlist frame ancestor cụ thể, bảo vệ message channel, kiểm soát origin và tương tác user. Không dùng `frame-ancestors *` hoặc bỏ header chỉ để một portal bất kỳ hoạt động.

## 9. CSRF tại form consent khác `state` ở OAuth Client

Hai lớp thường bị nhầm:

| Lớp | Ranh giới | Mục tiêu |
|---|---|---|
| **`state` ở Client** | Authorization request của Client ↔ callback của AS. | Gắn callback với giao dịch đang chờ; chống các dạng OAuth login CSRF/response injection. |
| **CSRF protection của trang AS** | Browser có session AS ↔ hành động POST “Allow/Deny”. | Chặn website bên ngoài kích hoạt quyết định consent trái ý trong phiên AS. |

**Client kiểm tra `state` không cứu được một AS đã bị CSRF ở form Allow.** Ngược lại, form AS có CSRF token đúng không thay việc Client kiểm tra state và PKCE khi nhận authorization code.

### Anti-pattern

~~~http
GET /consent/approve?client_id=spend-insights-web&scope=orders%3Aread HTTP/1.1
Host: auth.example.test
Cookie: as_session=<SESSION>
~~~

Nếu một request GET làm thay đổi grant, attacker có thể dụ browser tải URL bằng link/image/prefetch hoặc thủ thuật tương tự. **Không dùng GET để tạo quyết định đồng ý**.

### Mô hình an toàn hơn

~~~http
POST /consent/decision HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Origin: https://auth.example.test
Cookie: as_session=<SESSION_COOKIE>

transaction_id=<OPAQUE_TRANSACTION_REFERENCE>&csrf_token=<CSRF_TOKEN_BOUND_TO_AS_SESSION>&decision=approve
~~~

Mẫu HTTP chỉ minh họa. CSRF token, cookie, transaction reference **không phải user-provided proof độc lập**: backend phải so chúng với session/server state tin cậy. Origin/Referer validation phù hợp có thể bổ sung nhưng không luôn đủ/thay CSRF token trong mọi browser/profile. **SameSite cookie** cũng chỉ là một lớp.

### Các điều kiện khi xử lý POST

1. Session AS đã xác thực user đủ mức yêu cầu.
2. **CSRF token hợp lệ** theo cơ chế AS đã cấu hình; kiểm tra Origin/Sec-Fetch-* nếu dùng theo policy.
3. Transaction reference tồn tại, còn hạn, chưa xử lý và thuộc **đúng phiên/user**.
4. Client, redirect URI, resource, tenant, requested scopes lấy từ **transaction đã xác minh**, không được tùy ý thay bởi form.
5. Decision chỉ là **approve/deny** hoặc lựa chọn scope được phép, không là “grant admin”.
6. Ghi quyết định **atomically**; ngăn dùng lại giao dịch để mở rộng grant.

## 10. Ràng buộc giao diện với authorization transaction phía AS

Lỗ hổng nguy hiểm là UI hiển thị dữ liệu một giao dịch nhưng endpoint ghi grant lại tin tham số gửi từ browser hoặc Client. Ví dụ user thấy `orders:read` nhưng form có thể bị sửa thành `payments:refund`.

### Mô hình transaction đáng tin

~~~yaml
# Schema minh họa nội bộ, không phải định dạng chuẩn OAuth.
transaction_id: t-opaque-random
status: pending
expires_at: short_expiry
authenticated_subject: user-123
tenant_id: tenant-a
client_id: spend-insights-web
redirect_uri: https://app.example.test/oauth/callback
issuer: https://auth.example.test
response_type: code
pkce_code_challenge: "<S256_CHALLENGE>"
requested_resource: orders-api
requested_scopes:
  - orders:read
validated_policy_version: v18
consent_ui_version: v6
~~~

Giá trị `transaction_id` được dùng tra cứu trạng thái đáng tin; **không cần truyền toàn bộ nội dung và quyền vào browser**. Nếu dùng token giao dịch stateless, phải bảo vệ toàn vẹn/chống replay, TTL và ràng buộc session với khóa được quản lý an toàn.

### Luồng xử lý đúng

~~~mermaid
flowchart TD
    A["/authorize request"] --> B["AS xác minh client + redirect + scope + policy"]
    B --> C["Lưu authorization transaction tin cậy"]
    C --> D["Render consent từ metadata/policy đã xác minh"]
    D --> E["Browser gửi quyết định + CSRF + transaction reference"]
    E --> F{"Session/CSRF/transaction còn hợp lệ?"}
    F -- Không --> X["Từ chối, không cấp grant"]
    F -- Có --> G["AS re-check client, tenant, resource, scope và lựa chọn"]
    G --> H{"Quyền có hợp lệ?"}
    H -- Không --> X
    H -- Có --> I["Atomically mark approved/denied"]
    I --> J{"approved?"}
    J -- Không --> K["OAuth access_denied nếu redirect hợp lệ"]
    J -- Có --> L["Phát authorization code bound to grant/PKCE/client"]
~~~

### Nếu người dùng mở nhiều tab

~~~text
Tab A: transaction TA, scope orders:read
Tab B: transaction TB, scope reports:export

Không được:
  dùng cùng một biến global "currentConsentTransaction"
  rồi lấy scope của TB khi user bấm Allow trên tab A.

Phải:
  mỗi form trỏ transaction riêng
  mỗi transaction gắn đúng session/user/client/tenant
  bảo vệ TTL, concurrency và one-time decision
~~~

### Scope có thể đổi giữa lúc hiển thị và bấm

Nếu tenant admin chặn Client hoặc thu hồi entitlement sau khi AS render consent nhưng trước khi user bấm Allow, AS cần **kiểm tra lại policy tại thời điểm quyết định** hoặc dùng versioned policy với quy tắc xử lý thay đổi rõ ràng. Không coi màn hình cũ là bằng chứng quyền hiện hành.

## 11. Không tin các tham số form để cấp grant

### Một request bị sửa

~~~http
POST /consent/decision HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Cookie: as_session=<SESSION_COOKIE>

transaction_id=t-opaque-random&csrf_token=<TOKEN>&decision=approve&client_id=attacker-client&scope=orders%3Aread%20payments%3Arefund&tenant_id=tenant-b
~~~

Ngay cả khi `csrf_token` hợp lệ, **Client ID, scope, tenant do browser gửi không có quyền thay transaction gốc**. AS nên bỏ qua/từ chối các field ngoài hợp đồng và **chỉ cấp quyền được xác định từ transaction + policy hiện hành + lựa chọn consent hợp lệ**.

### Mã giả cho Authorization Server

~~~text
handleConsentDecision(request, asSession):
    require authenticated(asSession)
    require validCsrf(request.csrfToken, asSession)

    tx = trustedTransactionStore.load(request.transactionId)
    if tx missing or expired or not pending:
        reject
    if tx.subject != asSession.subject:
        reject
    if tx.tenant != asSession.tenant:
        reject

    client = clientRegistry.find(tx.clientId)
    if client missing, disabled or tx.redirectUri not allowed:
        reject

    policy = evaluateCurrentPolicy(
        subject=asSession.subject,
        tenant=tx.tenant,
        client=client,
        resource=tx.requestedResource,
        requestedScopes=tx.requestedScopes
    )
    if policy denies:
        reject

    if request.decision == "deny":
        atomicallyCompleteAsDenied(tx)
        return oauthAccessDeniedToVerifiedRedirect(tx)

    if request.decision != "approve":
        reject

    # Chỉ cho chọn scope thuộc transaction đã xác minh.
    approvedScopes = validateSelectedScopes(request.selectedScopes)
    if not approvedScopes subsetOf tx.requestedScopes:
        reject
    if not approvedScopes subsetOf policy.allowedScopes:
        reject
    if approvedScopes empty and policy.requiresNonEmptyGrant:
        reject

    if not atomicallyCompleteAsApproved(tx, approvedScopes):
        reject duplicate_decision

    saveAuthorizationGrant(
        tx.subject, tx.tenant, tx.clientId,
        tx.requestedResource, approvedScopes
    )
    return issueOneTimeCodeBoundTo(
        tx.clientId, tx.redirectUri, tx.pkceChallenge,
        tx.subject, tx.tenant, tx.requestedResource,
        approvedScopes
    )
~~~

Đây là **pseudocode**, không phải Authorization Server hoàn chỉnh. Việc ghi grant, đánh dấu transaction và phát authorization code phải có **semantics nguyên tử/khôi phục lỗi phù hợp** để không tạo grant lệch trạng thái khi một bước lỗi. Nếu hệ thống chỉ có kiểu consent **all-or-nothing**, `approvedScopes` phải được lấy từ toàn bộ phạm vi hợp lệ đã cho phép hoặc từ chối rõ ràng, không tự giả định browser đã chọn subset.

## 12. Redirect URI và callback: đừng để “trang thật” đưa code sai nơi

AS sau consent thường **redirect browser** tới Client kèm authorization code hoặc lỗi OAuth. Nếu redirect URI sai, code có thể lọt vào site attacker dù UI consent ở AS hoàn toàn thật.

### Anti-pattern: redirect tùy ý

~~~text
/authorize?client_id=shop-web
          &redirect_uri=https://attacker.invalid/receive-code
          &scope=orders:read
~~~

Nếu AS không so khớp redirect URI với registration theo quy tắc profile, attacker có thể nhận code. **Chính sách xác minh redirect URI phải chạy trước khi AS phát response**, kể cả response lỗi.

### Các lớp phòng vệ

1. Client đăng ký **redirect URI chính xác** theo chính sách OAuth/profile; giới hạn wildcard/open redirect.
2. AS xác minh `client_id`, `redirect_uri`, `response_type` và grant trước khi xem xét phát code.
3. Nếu Client/redirect URI **không hợp lệ hoặc không đáng tin**, AS **không redirect authorization response tới URL đó**.
4. Client kiểm tra `state`, session/transaction và issuer (theo profile/RFC 9207 nếu dùng) tại callback.
5. Authorization Code + **PKCE S256** và code binding giúp giảm code interception/substitution.
6. Không để callback `/oauth/callback?next=<untrusted-url>` trở thành open redirect khiến code hoặc session bị tiết lộ.
7. Hạn chế `Referrer-Policy` và logging URL mang code; không đưa code/token vào analytics.

### Những gì PKCE không giải quyết

PKCE có thể khiến người chỉ đánh cắp authorization code **khó đổi code thành token** nếu không có verifier. Nhưng PKCE **không xác thực nội dung UI consent**, không kiểm duyệt nhà phát hành Client và không chứng minh người dùng đã hiểu scope. Vì vậy vẫn cần Client registration policy và giao diện đáng tin.

## 13. PAR và JAR: bảo vệ authorization request nhưng không thay consent

Trong môi trường yêu cầu độ toàn vẹn mạnh hơn, AS và Client có thể hỗ trợ:

- **Pushed Authorization Requests (PAR, RFC 9126):** Client đẩy authorization request qua back channel đã bảo vệ tới AS và nhận `request_uri` tham chiếu, giảm việc mang nhiều tham số nhạy cảm qua browser.
- **JWT-Secured Authorization Request (JAR, RFC 9101):** Authorization request được đóng thành Request Object JWT, có thể được ký để bảo vệ tính toàn vẹn và nguồn request theo profile/registration.

### Sơ đồ khái niệm PAR

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant B as Browser
    C->>AS: POST PAR: client + scope/resource/redirect và auth nếu bắt buộc
    AS->>AS: Verify request/registration/policy
    AS-->>C: request_uri do AS phát + expires_in
    C-->>B: Redirect /authorize?client_id=...&request_uri=...
    B->>AS: Mở authorization endpoint
    AS->>AS: Resolve request_uri tới request đã lưu
    AS-->>B: Xác thực user/consent theo request đáng tin
~~~

**PAR/JAR giúp giảm sửa tham số và một số dạng injection**, nhưng không tự chứng minh Client đáng tin. Một Client độc hại có thể tạo **PAR/JAR hợp lệ cho chính nó** và vẫn lừa người dùng qua tên/logo hoặc scope quá rộng nếu AS bỏ registration policy.

### Khi dùng PAR/JAR cần nhớ

| Kiểm soát | Tại sao vẫn cần? |
|---|---|
| Client registration và redirect validation | Request Object hợp lệ chưa bảo đảm redirect URI được phép. |
| AS/tenant scope policy | Client có thể ký yêu cầu vượt allowed scopes. |
| Consent UI từ dữ liệu đã xác minh | Browser không được tự thay quyền được hiển thị. |
| Form CSRF và transaction binding | Ký authorization request không bảo vệ mọi POST “Allow”. |
| PKCE và callback state | Các rủi ro code exchange/response substitution còn riêng. |
| RS authorization | Một token phát từ request có integrity vẫn phải đúng audience/object quyền. |

## 14. Bảo vệ trang consent trên mobile và native app

Ứng dụng mobile đôi khi mở màn hình đăng nhập/consent trong **in-app WebView** do chính ứng dụng điều khiển. Nếu WebView cho phép app đọc nội dung trang hoặc chèn script, user khó kiểm chứng đang ở AS thật và credential có thể bị thu thập.

### Hướng thực hành

- Với native OAuth Client, dùng **external user-agent/system browser** theo **RFC 8252** và profile liên quan, không dựng form password/consent riêng trong app để thay AS.
- Dùng **Authorization Code + PKCE** cho public native Client; client secret nhúng trong binary không là bí mật đáng tin.
- Kiểm tra redirect URI/app links/universal links theo cơ chế nền tảng; tránh custom scheme dễ bị app khác chiếm nếu cấu hình yếu.
- Nếu dùng browser tab do nền tảng cung cấp, không cho Client sửa nội dung consent hoặc giả thanh địa chỉ.
- Thận trọng với các modal giả website, link deep link từ email/chat và các popup phủ lên browser.
- Sau callback, kiểm tra `state`, issuer/transaction và ID/access token theo đúng profile.

### UI giả bằng native overlay

Attacker có thể tạo **màn hình native có giao diện giống consent của AS** mà thực tế không tải website AS, khiến user nhập mật khẩu/OTP hoặc bấm “Approve” trong app độc hại. AS nên **không yêu cầu user cấp quyền bằng thao tác tại giao diện do Client tự vẽ rồi coi là consent đáng tin**.

Không thể phòng mọi thiết bị đã bị root/malware/overlay permission abuse chỉ bằng mã web; cần kết hợp nền tảng, quản lý thiết bị, thông báo rủi ro và khả năng thu hồi token.

## 15. Device authorization: QR và mã hợp lệ vẫn có thể bị lừa

Trong **OAuth Device Authorization Grant (RFC 8628)**, TV/thiết bị hạn chế nhập liệu hiển thị **`user_code`** và `verification_uri`; người dùng vào AS bằng điện thoại/laptop để xác minh và consent.

~~~text
TV:
  Mở https://auth.example.test/activate
  Nhập mã ABCD-EFGH

Điện thoại:
  Mở trang AS thật, nhập/xác nhận mã
  Đọc Client/thiết bị/resource/scope rồi chọn Allow/Deny
~~~

### Kịch bản device-code phishing

1. Attacker tạo device authorization request cho **thiết bị của attacker**.
2. AS trả `user_code` và `device_code` cho attacker.
3. Attacker gửi `user_code` cho nạn nhân và giả làm hỗ trợ kỹ thuật: “Hãy đăng nhập website này và nhập mã để bảo vệ tài khoản”.
4. Nạn nhân vào **AS thật**, đăng nhập, nhập mã và chấp thuận scope.
5. Attacker **poll token endpoint bằng device code của mình**, có thể nhận access token hợp lệ.

**Website AS thật và mã có thật không bảo đảm đây là thiết bị của nạn nhân.** Biện pháp quan trọng là người dùng **chỉ phê duyệt transaction mình chủ động khởi tạo**, AS hiển thị Client và phạm vi rõ ràng, có xác nhận mã/thiết bị và chống brute force.

### QR / `verification_uri_complete`

QR có thể chứa URL đầy đủ với `user_code`, giúp bớt nhập liệu; tuy nhiên:

- AS nên có bước **đối chiếu/khẳng định mã và thiết bị** phù hợp, không biến việc scan QR thành đồng ý tự động.
- Không đưa **`device_code`** (credential cho polling) vào QR hoặc màn hình công khai.
- Không tin tên thiết bị do Client tự gửi là **bằng chứng định danh thiết bị mạnh**.
- Hạn chế user-code guessing, TTL, rate limit và xử lý `authorization_pending`/`slow_down`/`access_denied`/`expired_token` theo RFC 8628.
- Với TV dùng chung, phải mô tả quyền offline/refresh token và có cách unlink/revoke trên account.

## 16. Consent đối với ứng dụng nội bộ và admin approval

Không phải mọi user có thể tự cấp mọi scope cho mọi Client. Với môi trường nhiều tenant:

| Trường hợp | Điều kiện quyết định |
|---|---|
| **First-party app** đã được tổ chức kiểm soát | AS có thể có policy không hiện consent lại; vẫn kiểm tra grant/resource/quyền. |
| **Third-party app** xin quyền đọc dữ liệu cá nhân | Cần thông tin Client rõ và user consent nếu policy yêu cầu. |
| **App chưa xác minh** xin scope nhạy cảm | Có thể cần review hoặc bị chặn trước khi user thấy màn hình. |
| **Admin consent tenant A** | Admin phải thực sự có quyền phê duyệt **tenant A**; không tác động mặc định tenant B. |
| **Quyền tài chính/quản trị rủi ro cao** | Có thể đòi step-up authentication/MFA và phê duyệt riêng. |
| **Grant đã thu hồi hoặc scope vừa mở rộng** | Không tự tái sử dụng consent cũ. |

### Đừng dùng danh hiệu “admin” để lừa user

Một Client có tên `Tenant Admin Security Update` không được AS tự coi là hệ thống quản trị. Identity/role của publisher và quyền phê duyệt phải được quản lý **ngoài self-declared client name**.

### Consent không phải quy trình phê duyệt toàn năng

User consent là một điều kiện trong policy, **không thay**:

- Client registration/verification.
- Tenant/organization policy.
- Quyền user trên dữ liệu.
- Phê duyệt admin khi bắt buộc.
- Kiểm tra ràng buộc issuer, audience, scope và token tại RS.

Một người dùng có role admin cũng không thể bằng một cú bấm biến Client được đăng ký `orders:read` thành ứng dụng có `payments:refund`.

## 17. Thiết kế trải nghiệm khó bị lừa mà vẫn dễ dùng

Bảo mật UX không có nghĩa nhét một trang dài khó đọc rồi yêu cầu người dùng bấm cho xong. Cần ưu tiên **thông tin quyết định** và tránh các mẫu giao diện khiến quyền nhạy cảm bị che giấu.

### Những nguyên tắc UX

1. **Danh tính thật:** tên ứng dụng rõ, publisher đã được kiểm tra theo trạng thái thực; phân biệt app chưa xác minh.
2. **Đúng tài khoản và tenant:** hiển thị account đang đăng nhập; user có thể chọn lại nếu nhầm.
3. **Quyền bằng động từ dễ hiểu:** xem, chỉnh sửa, xóa, xuất, hoàn tiền; không chỉ chuỗi scope.
4. **Hiển thị resource/API hoặc nhóm dữ liệu:** “Đơn hàng” khác “Thanh toán”.
5. **Quyền nhạy cảm nổi bật:** làm rõ hành động ảnh hưởng tài chính, xuất dữ liệu, quản trị hoặc duy trì truy cập lâu dài.
6. **Từ chối có thể tìm thấy:** không giấu nút Deny, không đe dọa user sẽ mất tài khoản nếu từ chối quyền không bắt buộc.
7. **Không mặc định tick quyền rộng:** chỉ cấp quyền user thực sự chấp thuận trong hệ thống hỗ trợ granular consent.
8. **Incremental consent:** xin thêm quyền đúng lúc feature cần, cho biết quyền **mới** khác quyền đã cấp thế nào.
9. **Giải thích cách thu hồi:** đường dẫn quản lý ứng dụng đã kết nối, phiên thiết bị và quyền offline.
10. **Accessibility:** nhãn nút rõ cho screen reader, focus order hợp lý, tương phản đủ, không dựa duy nhất vào màu hoặc animation.
11. **Không tạo click fatigue:** xin consent lặp đi lặp lại thiếu lý do làm user mất cảnh giác.
12. **Không tự chấp thuận bằng im lặng:** hết timeout, đóng tab hoặc lỗi network không được thành “approve”.

### Mẫu tốt và mẫu nguy hiểm

| Tình huống | Mẫu nguy hiểm | Mẫu tốt |
|---|---|---|
| Xin quyền đọc và hoàn tiền | “Ứng dụng muốn cải thiện trải nghiệm”. | Nêu riêng **đọc đơn** và **hoàn tiền**. |
| User từ chối | Nút Deny nhỏ/ẩn, hiển thị đe dọa. | Nút rõ, xử lý từ chối như kết quả bình thường. |
| App chưa xác minh | Tự gắn biểu tượng verified do Client khai. | Thông báo trạng thái kiểm tra thực tế. |
| Xin thêm scope | Hiện lại danh sách dài không nêu thay đổi. | Chỉ rõ **quyền vừa được yêu cầu bổ sung**. |
| Refresh/offline access | “Ghi nhớ đăng nhập” nhưng không mô tả token dài hạn. | Giải thích ứng dụng còn truy cập khi user không có mặt, thời hạn/revoke. |
| Kết nối thiết bị mới | Auto-approve sau khi scan QR. | Xác nhận ứng dụng/mã/thiết bị, consent khi cần. |

### Consent có phải là “đồng ý pháp lý” không?

OAuth consent là quyết định **ủy quyền kỹ thuật**, không tự đảm bảo đã đáp ứng mọi yêu cầu pháp lý về xử lý dữ liệu cá nhân. Một hệ thống phải đánh giá riêng quyền riêng tư, mục đích sử dụng, lưu trữ, xóa dữ liệu và nghĩa vụ pháp lý theo bối cảnh.

## 18. Security headers, cookie và session cho trang consent

Một màn hình consent an toàn cần các lớp triển khai ở web server/browser ngoài điều kiện OAuth.

### Header minh họa có thể dùng

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Cache-Control: no-store
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Strict-Transport-Security: max-age=31536000
~~~

Đây là một **điểm khởi đầu minh họa**, cần điều chỉnh theo static assets/CDN và luồng của AS. `Strict-Transport-Security` phải được cấu hình cẩn trọng ở đúng HTTPS host, kèm đánh giá preload/subdomain nếu định sử dụng. Một số nội dung như nonce-based CSP cần tạo nonce **mới cho từng response**.

### Cookie session của AS

~~~http
Set-Cookie: as_session=<OPAQUE_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **Secure:** browser chỉ gửi cookie qua kênh an toàn thích hợp.
- **HttpOnly:** giảm khả năng JavaScript đọc cookie; không ngăn XSS thực hiện request trong phiên.
- **SameSite:** giảm một số tình huống cross-site request; chọn `Lax`/`Strict` phù hợp với luồng redirect OAuth, không thay CSRF token.
- **Session ID rotation:** sau login/step-up phù hợp để giảm session fixation.
- **Session expiration:** consent transaction và session không được sống vô thời hạn.

### Chống cache và rò rỉ tham số

Trang consent có thể hiển thị tên account, tenant, Client và request scopes. `Cache-Control: no-store` giúp giảm lưu nội dung nhạy cảm trong browser/proxy cache. `Referrer-Policy: no-referrer` giảm lộ URL khi user theo link; tuy nhiên **không thay** việc tránh đưa token/code/credential vào URL hoặc external resources.

## 19. Spring Security: bảo vệ UI consent ở tầng web

Một Authorization Server có thể dùng Spring Security để đặt **CSRF và security headers** cho endpoint trang consent. Đoạn sau là **minh họa cấu hình web security**, không tự triển khai toàn bộ OAuth 2.0 Authorization Server hay quyết định grant.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ConsentPageSecurity {

    @Bean
    SecurityFilterChain consentSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/consent/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            // Giữ CSRF protection cho POST quyết định consent.
            .csrf(csrf -> {})
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'none'; "
                    + "script-src 'self'; "
                    + "style-src 'self'; "
                    + "img-src 'self'; "
                    + "form-action 'self'; "
                    + "base-uri 'none'; "
                    + "object-src 'none'; "
                    + "frame-ancestors 'none'"))
                .frameOptions(frame -> frame.deny()));
        return http.build();
    }
}
~~~

**Cảnh báo về phạm vi cấu hình:** `.securityMatcher("/consent/**")` chỉ bảo vệ các URL khớp pattern và filter chain tương ứng, **không tự bảo vệ mọi URL login/authorize/token endpoint**. Một AS thật cần security filter chains phù hợp cho các endpoint khác, session management, cookie settings, form rendering, CSRF token repository và transaction integrity.

### Có cần disable CSRF cho OAuth không?

Không tùy tiện dùng:

~~~java
// ANTI-PATTERN: không tắt toàn bộ CSRF chỉ vì đây là OAuth.
// http.csrf(csrf -> csrf.disable());
~~~

Token endpoint (machine-to-machine) và browser form consent có **threat model khác nhau**; một AS có thể có cấu hình CSRF khác cho từng endpoint theo framework, nhưng **POST chấp thuận của browser** cần bảo vệ tương ứng. Phải xác minh form nhận CSRF token và security chain thực sự áp dụng.

### Controller xử lý lựa chọn

Không dùng:

~~~java
// ANTI-PATTERN
// @PostMapping("/consent/approve")
// String approve(@RequestParam String clientId,
//                @RequestParam String scope) {
//     saveGrant(currentUser(), clientId, scope); // Sai: tin form.
// }
~~~

Controller nên chỉ nhận **transaction reference** và lựa chọn; service phía AS lấy **client/redirect/scope/resource/user/tenant từ transaction đáng tin** rồi revalidate policy và ghi grant atomically. Không nên coi client ID/tenant trên form là nguồn danh tính.

## 20. Java: policy check trên transaction đã xác minh

Đoạn Java sau minh họa phần **quyết định được phép ghi** sau khi framework đã xử lý session/CSRF và AS đã tải transaction tin cậy. Nó **không thay framework Authorization Server**, không giải quyết persistence/atomicity hay toàn bộ OAuth error handling.

~~~java
import java.util.Collections;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

record VerifiedConsentTransaction(
    String transactionId,
    String authenticatedSubject,
    String tenantId,
    String registeredClientId,
    String audience,
    Set<String> requestedScopes,
    boolean pending
) {}

record CurrentConsentPolicy(
    boolean clientActive,
    Set<String> clientAllowedScopes,
    Set<String> userEntitledScopes,
    Set<String> tenantAllowedScopes,
    Set<String> resourceSupportedScopes
) {}

final class ConsentDecisionPolicy {
    static Set<String> checkApproval(
            VerifiedConsentTransaction tx,
            CurrentConsentPolicy policy,
            String sessionSubject,
            String sessionTenant,
            Set<String> selectedScopes) {

        if (tx == null || policy == null || !tx.pending()
                || tx.transactionId() == null
                || tx.registeredClientId() == null
                || tx.audience() == null
                || !policy.clientActive()
                || !Objects.equals(tx.authenticatedSubject(), sessionSubject)
                || !Objects.equals(tx.tenantId(), sessionTenant)
                || tx.requestedScopes() == null
                || policy.clientAllowedScopes() == null
                || policy.userEntitledScopes() == null
                || policy.tenantAllowedScopes() == null
                || policy.resourceSupportedScopes() == null
                || selectedScopes == null
                || selectedScopes.isEmpty()) {
            return Collections.emptySet();
        }

        if (!tx.requestedScopes().containsAll(selectedScopes)
                || !policy.clientAllowedScopes().containsAll(selectedScopes)
                || !policy.userEntitledScopes().containsAll(selectedScopes)
                || !policy.tenantAllowedScopes().containsAll(selectedScopes)
                || !policy.resourceSupportedScopes().containsAll(selectedScopes)) {
            return Collections.emptySet();
        }
        return Collections.unmodifiableSet(new HashSet<>(selectedScopes));
    }
}
~~~

### Diễn giải

Điều kiện đủ ở trên **chỉ là một phần của policy**:

- `VerifiedConsentTransaction` phải do AS lấy từ **store đáng tin** và kiểm tra hết hạn, session binding, CSRF, redirect URI, PKCE challenge, issuer và tình trạng đã xử lý trước khi gọi logic này.
- `CurrentConsentPolicy` phải được tính từ **client registry/tenant/user entitlement**, không từ body do Client gửi.
- `selectedScopes` chỉ là lựa chọn được user gửi; nếu không hỗ trợ partial consent, AS phải áp dụng contract all-or-nothing.
- Trả tập rỗng biểu thị **không có approval hợp lệ** trong ví dụ, không phải lời mời phát token không scope.
- Việc **lưu grant, tiêu thụ transaction và phát authorization code** cần thiết kế nhất quán/atomic ở tầng AS.
- Quyền đọc một order cụ thể vẫn do RS kiểm tra trên **owner/tenant/status của dữ liệu thật**.

### Ví dụ policy cho dữ liệu tại Resource Server

~~~text
Trusted access token:
  iss = https://auth.example.test
  aud = orders-api
  scope = orders:read
  sub = user-123
  tenant = tenant-a

Requested order:
  id = order-999
  owner = user-999
  tenant = tenant-b

=> DENY nếu thiếu quyền cross-tenant/owner override hợp lệ,
   dù người dùng đã bấm Allow và JWT có chữ ký đúng.
~~~

## 21. Quyền offline, thu hồi consent và xử lý khi đã bị lừa

### Vì sao refresh token là điểm cần nói rõ trên UI?

Một app chỉ đọc dữ liệu trong một phiên ngắn khác với app có thể tiếp tục truy cập khi user không còn ở trước màn hình. Với **OIDC `offline_access`** khi được hỗ trợ, Client có thể xin khả năng truy cập ngoại tuyến; **AS không bắt buộc cấp refresh token chỉ vì Client xin scope đó**.

Nếu hệ thống cho phép truy cập dài hạn, UI phải diễn giải mục đích, khả năng rút quyền và điều kiện phù hợp. Refresh token:

- Chỉ dùng tại **AS token endpoint**, không trình cho RS.
- Phải được lưu trữ an toàn; với public Client cần rotation/sender-constraining theo BCP/profile phù hợp.
- Không cấp thêm scope ngoài grant và policy đã phê duyệt.
- Cần được thu hồi khi grant/device bị revoke theo cơ chế hệ thống.

### User đã chấp thuận một Client giả mạo: làm gì?

1. Cho user **ngắt kết nối ứng dụng đã cấp quyền**, xác định đúng Client registration, scope, resource, tenant và thời điểm.
2. AS vô hiệu **grant/refresh token** liên quan và xem xét thu hồi access token đã cấp.
3. Nếu Client độc hại, **chặn/khóa registration** và kiểm tra các grant của người dùng khác bị ảnh hưởng.
4. Xem log AS **token issuance**, API access, data export và hoạt động nhạy cảm; không log raw token/secret vào báo cáo.
5. Đánh giá **JWT access token còn hạn**: nếu RS chỉ verify chữ ký/`exp` offline, việc revoke grant ở AS **không tự làm token cũ vô hiệu tức thời**.
6. Sử dụng introspection/denylist/policy state, TTL ngắn hoặc cơ chế RS nhận thông báo thu hồi theo kiến trúc và mức rủi ro.
7. Thông báo user bằng kênh chính thức, sửa quy trình client verification/UI và bổ sung cảnh báo.

### Phân biệt các hành động

| Hành động | Điều có thể thay đổi | Không được tự suy |
|---|---|---|
| **Đóng tab consent** | Kết thúc tương tác đang xem. | Không phải approve; không tự thu hồi grant trước đó. |
| **Bấm Deny** | Từ chối authorization transaction hiện tại. | Không nhất thiết xóa consent cũ khác. |
| **Logout RP** | Kết thúc session phía Client. | Không tự thu hồi access/refresh token ở AS. |
| **Logout OP/AS** | Kết thúc phiên xác thực phía OP. | Không mặc định hủy grant mọi Client. |
| **Revoke/disconnect Client** | Thu hồi grant/refresh token theo chính sách. | Không tự invalidate mọi JWT đã phát nếu RS verify offline. |
| **Block Client registration** | Chặn giao dịch/issuance mới của Client theo policy. | Không tự xóa dữ liệu Client đã tải về trước đó. |

## 22. Audit, telemetry và phát hiện giả mạo

Một hệ thống không thể chỉ dựa vào user tự báo cáo. AS nên có telemetry giúp tìm **request scope bất thường, app giả danh, tỉ lệ approve/deny và nhiều giao dịch bị lỗi**.

### Sự kiện an toàn để ghi nhận

~~~json
{
  "event": "oauth.consent.decision",
  "authorization_server": "https://auth.example.test",
  "client_id": "spend-insights-web",
  "client_review_state": "approved",
  "resource": "orders-api",
  "requested_scope_count": 1,
  "granted_scope_count": 1,
  "tenant": "tenant-a",
  "decision": "approved",
  "policy_version": "v18",
  "correlation_id": "corr-example-123"
}
~~~

Mẫu audit không bắt buộc chứa đầy đủ user identifier, scope values hoặc device metadata; mức dữ liệu ghi phải phù hợp chính sách quyền riêng tư. Nếu cần ghi `sub`, tenant hoặc các thuộc tính nhận dạng phục vụ điều tra, phải kiểm soát quyền truy cập và thời hạn lưu.

### Tín hiệu đáng theo dõi

- Nhiều Client có tên/logo **gần giống** cùng một ứng dụng đã được xác minh.
- Client vừa đăng ký đột ngột xin `payments:refund`, `reports:export` hoặc `offline_access` ở số lượng lớn.
- Tỉ lệ **consent approval** tăng bất thường sau chiến dịch email/tin nhắn.
- Người dùng báo nhận link/mã device khi họ **không chủ động kết nối**.
- Nhiều authorization request có `redirect_uri` sai, `state` không khớp, Client metadata bị thay nhanh.
- Thất bại CSRF, frame violation/CSP reporting, XSS attempts, form post không thuộc transaction.
- API nhận nhiều access token của Client mới với scope nhạy cảm hoặc các yêu cầu dữ liệu vượt tenant.

### Tránh biến audit thành nguồn lộ token

Không log:

~~~text
Authorization: Bearer <ACCESS_TOKEN>
Authorization: Basic <CLIENT_CREDENTIALS>
refresh_token=<REFRESH_TOKEN>
code=<AUTHORIZATION_CODE>
device_code=<DEVICE_CODE>
Cookie: as_session=<SESSION>
CSRF raw token / PKCE raw verifier
~~~

Chỉ log trạng thái kiểm tra, mã lỗi, fingerprint/version **không dùng để xác thực**, client ID, policy decision và correlation ID theo nhu cầu.

## 23. Ma trận kiểm thử bảo vệ UI consent

Giả sử AS đáng tin là `https://auth.example.test`, Client `spend-insights-web` được đăng ký xin `orders:read` cho `orders-api` trong tenant A, user `user-123` chưa consent cho Client mới.

| Trường hợp | Kỳ vọng | Mục tiêu kiểm tra |
|---|---|---|
| Client hợp lệ, resource/scope đúng, session user đúng | AS có thể hiển thị consent đã xác minh. | Luồng cơ bản. |
| Client ID không tồn tại | AS từ chối; không render app “đã xác minh”. | Registration trust. |
| Client disabled vẫn gửi authorization request | AS không cấp quyền. | Registration lifecycle. |
| App mới đặt tên giống ứng dụng tài chính đã xác minh | Review/block hoặc hiển thị trạng thái chưa xác minh theo policy. | Client impersonation. |
| Client tự gửi publisher_status=verified | AS không hiển thị badge nếu không tự xác minh. | Metadata trust. |
| Logo URI trỏ IP metadata/internal | Không fetch tùy ý, có chống SSRF. | Image metadata safety. |
| Client name chứa HTML/script | UI escape/sanitize; không thực thi script. | Stored/reflected XSS. |
| Trang attacker đặt consent trong iframe | Browser chặn bằng `frame-ancestors`/XFO đúng policy. | Clickjacking defense. |
| CSP chỉ có `frame-src` mà thiếu `frame-ancestors` | Test phát hiện thiếu bảo vệ chống nhúng. | Phân biệt CSP directives. |
| Form Allow được gửi bằng GET | Không thay đổi grant; hệ thống phải sửa thiết kế. | Safe HTTP semantics. |
| POST consent thiếu CSRF token hợp lệ | AS từ chối. | CSRF defense. |
| POST có CSRF đúng nhưng transaction không thuộc session user | AS từ chối. | Transaction/user binding. |
| Form POST đổi client ID sang attacker-client | Không đổi client của transaction. | Không tin field browser. |
| Form POST thêm scope `payments:refund` | Không cấp quyền được cấy vào. | Scope integrity. |
| Form POST đổi tenant A thành tenant B | Không đổi tenant/grant; từ chối nếu mâu thuẫn. | Tenant isolation. |
| User đang xem consent thì tenant admin cấm app | Không cấp grant trái policy mới. | Revalidate current policy. |
| User bấm Deny | Trả `access_denied` nếu callback hợp lệ; không cấp grant mới. | Denial respected. |
| User đóng tab/timeout mà không bấm | Không tự approve. | No implicit consent. |
| Submit Allow hai lần đồng thời | Một quyết định hợp lệ; không phát thêm grant/code ngoài policy. | Atomicity/replay. |
| Hai tab với scope khác nhau | Mỗi tab dùng đúng transaction. | Multi-tab isolation. |
| Client redirect URI chưa đăng ký | AS không phát response tới URI đó. | Code leakage prevention. |
| Callback Client nhận `state` sai | Client từ chối response. | OAuth response binding. |
| Authorization code từ giao dịch khác + PKCE verifier sai | AS từ chối đổi code. | Code injection prevention. |
| Client có PAR/JAR hợp lệ nhưng xin scope ngoài policy | AS không cấp scope bị cấm. | Request integrity khác authorization. |
| User dùng app trong native WebView thu password | Đánh giá fail theo mô hình native OAuth được áp dụng. | Browser trust boundary. |
| Device flow mã từ người lạ, user chưa khởi tạo | UX/hướng dẫn và policy phải chống consent phishing. | User-initiated pairing. |
| QR `verification_uri_complete` dẫn đến consent không đối chiếu mã | Test đánh giá rủi ro remote phishing. | Device confirmation. |
| UI ghi “chỉ đọc” nhưng AS grant cả write | Test thất bại. | UI-to-grant consistency. |
| OIDC `prompt=none` khi bắt buộc consent mới | Trả lỗi phù hợp, không tự approve. | No-UI không bypass. |
| Consent cũ của tenant A dùng tại tenant B | Không tái sử dụng vô điều kiện. | Grant context binding. |
| User đã revoke grant, Client dùng refresh token cũ | AS từ chối refresh theo trạng thái. | Revocation. |
| JWT access token còn hạn sau revoke, RS chỉ verify offline | Xác nhận giới hạn revocation; không tuyên bố chặn ngay. | Token lifecycle realism. |
| Access token `aud=billing-api` gửi Orders | Orders từ chối. | Audience check. |
| Access token `scope=orders:read` nhưng order khác tenant | Orders từ chối. | Object-level authorization. |
| BFF bật CSRF cho consent nhưng tắt ở toàn bộ app | Kiểm thử phát hiện endpoint/cookie khác còn rủi ro. | Security chain coverage. |
| Trang consent tải script từ CDN không được kiểm soát | CSP/asset security test phát hiện và giới hạn. | Supply-chain/XSS risk. |
| Logs chứa raw code/token/session cookie | Test thất bại; redaction trước telemetry. | Secret leakage prevention. |
| AS nhận hàng loạt Client tên tương tự | Rate limit/review/cảnh báo theo chính sách. | Detect impersonation patterns. |

**Kiểm thử cần liên kết kết quả của UI với grant/token thực sự tại AS và dữ liệu tại RS.** Một ảnh chụp trang consent “trông đúng” không chứng minh callback hợp lệ, policy đúng hoặc bearer token không bị phát lại.

## 24. Tình huống tự luyện

**Tình huống A — Website có HTTPS và logo đúng.** User nhận link tới một trang có biểu tượng khóa và logo AS, nhưng host là `auth-example.test`. Có được xem là AS hợp lệ không?

**Giải thích:** Không thể suy ra từ HTTPS/logo. TLS bảo vệ kết nối tới **host đang truy cập**, không chứng minh host đó là AS được tổ chức tin cậy. Cần domain đúng đã được công bố/kiểm chứng.

**Tình huống B — Trang AS thật nhưng Client giả danh.** User vào đúng `auth.example.test` và thấy Client “Official HR Security” xin quyền xuất báo cáo. Vì sao vẫn nguy hiểm?

**Giải thích:** Client có thể do attacker đăng ký, dùng tên/biểu tượng giả. AS phải kiểm tra registration, publisher verification và scope policy; user cần biết **ai nhận quyền**, không chỉ website xác thực user.

**Tình huống C — Form bị sửa.** Trang hiển thị `orders:read`, nhưng browser POST thêm `payments:refund`. Nếu CSRF token hợp lệ, AS có thể cấp không?

**Giải thích:** Không. CSRF chỉ là một điều kiện. AS phải đối chiếu approved scope với **transaction gốc và policy hiện hành**, không tin dữ liệu browser.

**Tình huống D — Iframe hợp lệ?** Portal đối tác muốn nhúng trang consent vào iframe và yêu cầu AS bỏ `frame-ancestors`. Có nên đồng ý ngay?

**Giải thích:** Không. Clickjacking có thể khiến user bấm Allow ngoài ý muốn. Mặc định chặn framing; ngoại lệ cần phân tích threat model và allowlist nguồn nhúng với biện pháp bổ sung.

**Tình huống E — `state` đã đủ CSRF?** BFF dùng `state` đúng ở callback, nhưng endpoint `POST /consent/decision` của AS không kiểm tra CSRF/session binding. Có an toàn không?

**Giải thích:** Không. `state` ở Client bảo vệ callback; AS vẫn cần bảo vệ hành động consent trong phiên user.

**Tình huống F — PAR/JAR có nghĩa ứng dụng đáng tin?** Client độc hại gửi Request Object JAR được ký đúng khóa của chính nó. AS có thể bỏ kiểm tra scope và hiển thị “trusted app” không?

**Giải thích:** Không. Request integrity chỉ chứng minh request không bị sửa/nguồn theo đăng ký, không tự phê duyệt publisher, resource hoặc quyền.

**Tình huống G — User từ chối.** Một Client nhận `access_denied` và thử lại âm thầm với Client Credentials grant của service có quyền rộng để xem đơn user. Điều gì sai?

**Giải thích:** Đây là bypass mô hình authorization và nguy cơ confused deputy. User đã từ chối cấp delegated grant; service token không tự cho phép tiết lộ dữ liệu cho user/Client đó.

**Tình huống H — XSS qua tên ứng dụng.** Client name chứa `<img onerror=...>` rồi backend render trực tiếp. Nếu browser chạy script, tác động là gì?

**Giải thích:** Script chạy trong origin AS có thể thay nội dung hoặc thao túng form theo quyền của session. Cần escaping/sanitization, CSP, kiểm soát metadata và giảm quyền script.

**Tình huống I — Hai tab consent.** User mở một tab cho `orders:read`, tab khác cho `reports:export`. AS lưu một biến toàn cục `currentConsent` rồi cấp quyền của tab thứ hai khi user approve tab thứ nhất. Cần sửa?

**Giải thích:** Mỗi transaction phải có ID/trạng thái riêng gắn session, client, scope và TTL. Không dùng global state hay chọn transaction mới nhất tùy tiện.

**Tình huống J — Device flow từ cuộc gọi giả.** Người lạ gửi mã `ABCD-EFGH` và yêu cầu user mở AS thật. User chưa ghép nối TV. Có nhập không?

**Giải thích:** Không. Mã có thể thuộc flow của attacker; nhập và consent có thể cấp token cho thiết bị attacker. Chỉ phê duyệt giao dịch tự khởi tạo và đối chiếu mã trên thiết bị thật.

**Tình huống K — Consent đã revoke, token còn hạn.** User disconnect Client nhưng access token JWT còn 10 phút; RS chỉ verify signature/`exp`. Token có thể dùng tiếp không?

**Giải thích:** Có thể. AS revoke grant không tự xóa bản sao JWT offline. Cần TTL, RS state/introspection/denylist hoặc cơ chế thu hồi phù hợp.

**Tình huống L — Đã consent scope nhưng order sai chủ.** Token có `aud=orders-api` và `scope=orders:read`, nhưng người dùng đọc order của tenant khác. RS có phải trả dữ liệu vì user đã bấm Allow?

**Giải thích:** Không. Consent giới hạn quyền Client đề nghị, RS vẫn kiểm tra owner/tenant trên bản ghi. Một scope hợp lệ không tương đương object authorization.

## Checklist bảo vệ UI consent khỏi giả mạo

1. **Nguồn gốc AS rõ:** trusted issuer và HTTPS domain cố định, bảo vệ TLS/HSTS theo bối cảnh; không tin trang giả vì logo hoặc ổ khóa.
2. **Client registration đáng tin:** xem xét tên/logo/publisher/redirect URI, chống homograph/app impersonation và scope nhạy cảm.
3. **Không tin metadata tự khai:** badge verified chỉ do AS cấp; scope labels dựa trên hợp đồng AS/RS; sanitize external URLs/images.
4. **Render UI từ transaction đáng tin:** client, subject, tenant, resource, scopes, issuer/redirect/PKCE context đã được AS xác minh.
5. **Hiển thị quyền thật:** hành động đọc/ghi/xóa/xuất, quyền offline và resource, khác biệt giữa scope cũ và scope xin thêm.
6. **Cung cấp Deny rõ ràng:** không dark pattern, không im lặng tự approve; hỗ trợ accessibility và quyền rút consent.
7. **Chặn XSS/HTML injection:** context-appropriate escaping, textContent, sanitization khi cần, CSP và hạn chế third-party scripts.
8. **Chặn clickjacking:** `frame-ancestors 'none'` hoặc allowlist kiểm soát, X-Frame-Options phù hợp; không dùng `frame-src` làm thay thế.
9. **Bảo vệ form Allow/Deny:** POST + CSRF/session binding/Origin checks theo policy, không thay đổi grant bằng GET.
10. **Ràng buộc transaction một lần:** user, tenant, client, redirect, resource, requested/approved scope, TTL, anti-replay/atomicity.
11. **Không nâng quyền từ form:** AS revalidate policy; chỉ cấp subset hợp lệ hoặc từ chối đúng profile; không tin `client_id`, `scope`, `tenant_id` browser gửi lại.
12. **Bảo vệ OAuth response:** registered redirect URI, state/issuer binding, Authorization Code + PKCE, không redirect lỗi/code tới URI chưa xác minh.
13. **Dùng PAR/JAR khi phù hợp:** giảm authorization request tampering, nhưng vẫn phải kiểm tra Client và consent.
14. **Native/device flow đúng chuẩn:** system browser + PKCE cho native; xác nhận user code/thiết bị/Client trên AS với device grant.
15. **Admin/tenant policy:** chỉ người có thẩm quyền phê duyệt scope phù hợp; không dùng tên app “admin” làm trust signal.
16. **Bảo vệ token sau grant:** đúng access/refresh/ID token, TTL, scope/audience, bảo vệ lưu trữ, thu hồi và sender binding khi cần.
17. **RS vẫn kiểm tra dữ liệu:** issuer, chữ ký/introspection, audience, token type, scope và owner/tenant/object.
18. **Audit và incident:** theo dõi client impersonation, consent anomalies, CSRF/XSS/frame violations; redaction code/token/secret.
19. **Kiểm thử negative paths:** fake origin, malicious metadata, iframe, CSRF, tampered scope, multi-tab, redirect injection, device phishing, revoke và BOLA.

## Ghi nhớ

**Màn hình consent chỉ đáng tin khi nguồn gốc UI, danh tính Client, nội dung quyền và giao dịch cấp grant đều được kiểm soát.** Có hai bẫy lớn: **website AS giả** có thể đánh lừa user, và **Client giả danh trên AS thật** có thể nhận token hợp lệ nếu registration/consent policy yếu. AS cần trình bày **đúng Client, account/tenant, resource, scope, quyền dài hạn**, chặn clickjacking/XSS/CSRF, gắn form approval với **authorization transaction đã xác minh** và không nâng scope từ tham số browser. Redirect URI, `state`, PKCE, PAR/JAR, device-code confirmation giúp bảo vệ những đoạn giao thức riêng nhưng **không thay sự chấp thuận có ý thức và policy tại AS**. Sau consent, **access token vẫn phải đúng issuer/audience/scope và Resource Server vẫn phải phân quyền trên từng đối tượng**; thu hồi consent/grant cũng cần gắn với vòng đời refresh/access token và các biện pháp chống replay.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628)
- [RFC 9101 — JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101)
- [RFC 9126 — Pushed Authorization Requests (PAR)](https://www.rfc-editor.org/rfc/rfc9126)
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [OpenID Connect Core 1.0 — Consent, prompt và offline_access](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP — OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Clickjacking Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html)
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
