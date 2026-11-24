# CSRF token: cơ chế, vòng đời và cách triển khai an toàn

## 1. CSRF token là gì?

**Cross-Site Request Forgery (CSRF)** là kiểu tấn công khiến trình duyệt của người dùng gửi một request ngoài ý muốn tới ứng dụng mà người dùng đang đăng nhập. Rủi ro thường xuất hiện khi ứng dụng dựa vào cookie phiên: browser tự động đính kèm cookie phù hợp vào request, kể cả khi request được khởi tạo từ một trang khác.

**CSRF token** là một giá trị khó đoán do ứng dụng tạo và kiểm tra để xác nhận request thay đổi trạng thái đi qua một luồng giao diện hợp lệ của ứng dụng. Token thường được gắn với session hoặc được xác minh bằng một cơ chế mật mã phù hợp. Trang ngoài có thể khiến browser gửi request, nhưng thông thường không thể đọc token hợp lệ từ trang ứng dụng do Same-Origin Policy (SOP) hạn chế việc đọc DOM/response cross-origin.

Ví dụ một biểu mẫu cập nhật email có hidden token:

~~~html
<form method="post" action="/account/email">
  <input type="hidden" name="csrf_token" value="RANDOM_SESSION_BOUND_TOKEN">
  <label>
    Email mới
    <input name="email" type="email" required>
  </label>
  <button type="submit">Cập nhật email</button>
</form>
~~~

Server phải kiểm tra token trước khi thực hiện thay đổi. Nếu request thiếu token, token sai hoặc token không gắn với session hiện tại, server từ chối request.

Bài học thuộc chương **CSRF** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Nội dung tập trung vào nguyên lý token, hai pattern phổ biến (Synchronizer Token và Double-Submit Cookie), cách tạo/luân chuyển/kiểm tra token, tích hợp form và SPA, cũng như các lớp bổ trợ như SameSite, Origin, Fetch Metadata. Mục tiêu là phòng vệ CSRF ở đúng ranh giới mà vẫn hiểu rõ giới hạn khi ứng dụng có XSS, CORS hoặc nhiều subdomain.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao cookie tự động được gửi khiến ứng dụng có nguy cơ CSRF.
2. Phân biệt session ID với CSRF token và nêu được vai trò riêng của từng giá trị.
3. Triển khai tư duy **Synchronizer Token Pattern** cho ứng dụng server-side.
4. Giải thích **Double-Submit Cookie** và vì sao biến thể signed/session-bound an toàn hơn dạng so sánh đơn giản.
5. Chọn vị trí truyền token cho HTML form, AJAX và SPA.
6. Quản lý token qua đăng nhập, logout, session rotation và nhiều tab.
7. Kết hợp token với SameSite, Origin/Referer, Fetch Metadata và CORS mà không nhầm chúng là các cơ chế tương đương.
8. Nhận diện giới hạn của CSRF token khi có XSS hoặc client không phải trình duyệt.
9. Kiểm chứng bằng DevTools trong môi trường thử nghiệm.

## 2. Vì sao CSRF xảy ra?

HTTP không tự gắn request với ý định của người dùng. Với cookie session, browser quản lý cookie và tự gửi khi URL, host/domain, path, Secure và SameSite phù hợp. Trang ngoài có thể tạo một số loại request như form POST hoặc điều hướng mà không cần đọc response.

Ví dụ người dùng đang đăng nhập tại https://bank.example.test. Một trang độc hại có thể hiển thị hoặc tự gửi form:

~~~html
<form action="https://bank.example.test/transfer" method="post">
  <input type="hidden" name="to" value="attacker-account">
  <input type="hidden" name="amount" value="1000">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Nếu browser gửi cookie phiên và server chỉ dựa vào cookie để chấp nhận giao dịch, request có thể được xử lý dù người dùng không chủ động tạo giao dịch đó.

SOP thường ngăn trang ngoài đọc DOM hoặc response nhạy cảm của bank, nhưng **không chặn mọi request cross-origin**. Vì vậy “trang tấn công không đọc được response” không có nghĩa “request không tới server” hoặc “không thể thay đổi dữ liệu”.

### 2.1. Điều kiện thường làm CSRF khả thi

CSRF thường cần sự kết hợp của các điều kiện:

- Nạn nhân có một phiên hợp lệ tại ứng dụng đích.
- Browser tự động đính kèm thông tin xác thực (thường là cookie) vào request phù hợp.
- Ứng dụng có endpoint làm thay đổi trạng thái khi nhận request.
- Server không xác minh request có token/chứng cứ nguồn hợp lệ hoặc không có biện pháp phòng vệ tương đương.
- Kẻ tấn công có thể khiến browser tạo request với nội dung cần thiết.

Không phải mọi endpoint đều dễ bị CSRF như nhau. Token bearer chỉ được đặt trong một custom header do JavaScript đọc từ nơi khác có thể giảm một số đường tấn công qua form; nhưng nếu token bị lộ, CORS cho phép origin độc hại hoặc có XSS, bảo vệ có thể mất.

### 2.2. Những thao tác cần bảo vệ

Bất kỳ request nào thay đổi trạng thái nghiệp vụ đều cần xem xét CSRF, ví dụ:

- Đổi email, số điện thoại, địa chỉ hoặc mật khẩu.
- Tạo/chỉnh sửa/xóa dữ liệu.
- Đặt hàng, chuyển tiền, tạo giao dịch.
- Liên kết hoặc hủy liên kết tài khoản.
- Bật/tắt MFA, tạo API key hoặc thay đổi quyền.
- Đăng nhập và đăng xuất trong các mô hình có nguy cơ login/logout CSRF.

**GET, HEAD và các phương thức được xem là an toàn không được làm thay đổi trạng thái nghiệp vụ.** Nếu GET /delete-account thực hiện xóa tài khoản, ứng dụng đã phá vỡ một giả định nền tảng mà nhiều cơ chế browser và cache dựa vào.

## 3. CSRF token khác session ID như thế nào?

| Đặc điểm | Session ID | CSRF token |
| --- | --- | --- |
| Mục đích | Xác định session đã được server công nhận | Chứng minh request có token hợp lệ trong luồng ứng dụng |
| Vai trò | Bearer credential để tra cứu phiên | Bằng chứng chống giả mạo request trong mô hình cookie-based |
| Nơi lưu thường gặp | Cookie HttpOnly | Server-side session + HTML/form/JS memory; hoặc pattern double-submit |
| Browser tự gửi? | Có, nếu cookie phù hợp | Thường không tự gửi như session cookie; ứng dụng đưa vào form/body/header |
| Có thay thế nhau? | Không | Không |
| Có chứng minh quyền nghiệp vụ? | Không tự nó | Không |
| XSS có thể vô hiệu hóa bảo vệ? | Có thể thao tác qua session dù không đọc cookie HttpOnly | Có thể đọc token từ DOM/response cùng origin và gửi request hợp lệ |

Session ID và CSRF token nên là hai giá trị khác nhau. Không dùng session ID làm token ẩn trong DOM hoặc làm token mà JavaScript gửi lại. Session ID là credential; nếu lộ có thể chiếm phiên. CSRF token có mục tiêu khác và được kiểm tra theo session.

## 4. Synchronizer Token Pattern

Đây là pattern phổ biến cho ứng dụng có session state phía server.

### 4.1. Cách hoạt động

1. Server tạo một token ngẫu nhiên khi khởi tạo session hoặc khi cần cấp token.
2. Server lưu token trong session record, gắn với đúng session.
3. Server render token vào form HTML hoặc cung cấp qua một endpoint cùng origin.
4. Browser gửi token lại trong body hoặc custom request header khi thực hiện thao tác thay đổi trạng thái.
5. Server tra session từ cookie và so sánh token request với token gắn với session.
6. Nếu thiếu hoặc sai token, server từ chối request trước khi thực hiện nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Application server
    participant DB as Session store

    B->>S: GET /account (cookie session)
    S->>DB: Tra session và CSRF token
    DB-->>S: Session + token
    S-->>B: HTML form chứa hidden CSRF token
    B->>S: POST /account/email + cookie + token
    S->>DB: Tra session theo cookie
    DB-->>S: Session + expected token
    S->>S: So sánh token và kiểm tra quyền
    S-->>B: Cập nhật thành công hoặc từ chối
~~~

### 4.2. Sinh token

Token cần được tạo từ CSPRNG, có entropy đủ lớn và không thể đoán. Ví dụ Node.js:

~~~js
import { randomBytes } from "node:crypto";

const csrfToken = randomBytes(32).toString("base64url");
~~~

32 byte ngẫu nhiên tương ứng 256 bit entropy trước khi encode. Token nên:

- Không suy ra từ user ID, email, timestamp hoặc session ID.
- Không dùng Math.random() hoặc bộ đếm.
- Được gắn với session hiện tại.
- Không xuất hiện trong URL, log hoặc telemetry.
- Được so sánh theo cách phù hợp; dùng thư viện/framework CSRF đã được kiểm chứng khi có thể.

### 4.3. Render vào HTML form

~~~html
<form method="post" action="/profile">
  <input type="hidden" name="csrf_token" value="TOKEN_FROM_SERVER">
  <input type="text" name="displayName">
  <button type="submit">Lưu</button>
</form>
~~~

Token được render bởi server từ session đã xác định. Khi nhận POST, backend đọc token trong body và so với token lưu trong session. Không chấp nhận token do client tự tạo hoặc token thuộc session khác.

### 4.4. Kiểm tra phía server

Pseudocode:

~~~js
async function updateProfile(request, response) {
  const session = await requireAuthenticatedSession(request);

  const supplied = request.body.csrf_token;
  if (typeof supplied !== "string" || supplied.length > 200) {
    throw forbidden("CSRF token missing or invalid");
  }

  if (!constantTimeEqual(supplied, session.csrfToken)) {
    throw forbidden("CSRF token missing or invalid");
  }

  const input = validateProfileInput(request.body);
  await updateProfileForUser(session.userId, input);

  response.redirect("/profile");
}
~~~

Đây là pseudocode minh họa. Hàm so sánh constant-time cần xử lý độ dài an toàn và nên dùng thư viện mật mã phù hợp; không tự viết primitive. Framework CSRF middleware thường đã xử lý token parsing, session binding và so sánh. Không tự triển khai nếu framework có giải pháp chuẩn, được bảo trì và cấu hình đúng.

### 4.5. Token theo session hay theo request?

| Chiến lược | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Token ổn định trong session | Dễ dùng nhiều tab, form mở lâu và Back/Forward | Nếu token bị lộ, có thể dùng trong thời gian session còn hiệu lực. |
| Token riêng cho từng request/nonce | Giới hạn thời gian và phạm vi tái sử dụng | Dễ gây lỗi nhiều tab, request song song, retry và trang Back. |

Với nhiều ứng dụng web, token gắn session là lựa chọn thực tế; cần kết hợp session expiry, rotate, XSS defense và các lớp kiểm tra khác. Token one-time chỉ nên dùng khi quy trình có quản lý trạng thái/đồng bộ rõ ràng.

## 5. Double-Submit Cookie Pattern

Pattern này dùng hai bản sao của một token:

1. Server đặt một cookie chứa CSRF token.
2. Frontend đọc token đó và gửi lại trong body hoặc custom header.
3. Server xác minh giá trị trong request khớp với cookie hoặc chữ ký/token ràng buộc.

Ví dụ SPA:

~~~http
Set-Cookie: __Host-csrf=RANDOM_CSRF_VALUE; Path=/; Secure; SameSite=Lax
~~~

JavaScript cùng origin đọc cookie (nên cookie CSRF không có HttpOnly trong biến thể đọc trực tiếp), rồi gửi:

~~~js
const csrf = readCookie("__Host-csrf");

await fetch("/api/profile", {
  method: "PATCH",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrf
  },
  body: JSON.stringify({ displayName: "An" })
});
~~~

Server so sánh giá trị X-CSRF-Token với cookie hoặc kiểm tra chữ ký. Kẻ tấn công từ origin khác có thể khiến browser gửi cookie tự động, nhưng thông thường không thể đọc cookie/response cùng origin để đặt custom header đúng.

### 5.1. Vì sao double-submit đơn giản có thể yếu?

Một biến thể ngây thơ chỉ kiểm tra cookie và request parameter có cùng giá trị:

~~~text
Cookie: csrf=abc
X-CSRF-Token: abc
~~~

Nếu kẻ tấn công có thể đặt cookie cho domain rộng (cookie injection/tossing qua subdomain yếu, misconfiguration hoặc một đường khác), họ có thể chọn giá trị cookie và gửi cùng giá trị đó trong request. Khi server chỉ kiểm tra equality, token không chứng minh nó được server tin cậy tạo ra hoặc gắn với session.

### 5.2. Signed double-submit và ràng buộc session

Biến thể mạnh hơn dùng token có chữ ký HMAC, ràng buộc với session hiện tại:

- Sinh một nonce ngẫu nhiên.
- Tạo chữ ký từ session binding và nonce bằng secret chỉ server biết.
- Đóng gói token theo format được đặc tả rõ.
- Đặt token vào cookie.
- Client gửi lại token trong custom header/body.
- Server kiểm tra chữ ký, nonce/format và binding với session hiện tại.

Ví dụ khái niệm:

~~~text
token = nonce || HMAC(serverSecret, sessionBinding || nonce)
~~~

Đây là biểu diễn khái niệm, không phải định dạng serialization chuẩn. Không tự ghép chuỗi theo cách mơ hồ hoặc dùng hash không khóa thay HMAC. Nên dùng thư viện/framework đã được kiểm chứng và so sánh chữ ký an toàn.

Cookie double-submit cần được cấu hình scope hẹp. Prefix __Host- giúp browser hỗ trợ yêu cầu Secure, Path=/ và không có Domain, giảm nguy cơ subdomain đặt cookie cùng prefix ở phạm vi rộng. Nhưng prefix không tự xác minh chữ ký hoặc session binding.

### 5.3. Chọn pattern nào?

| Điều kiện kiến trúc | Pattern thường phù hợp |
| --- | --- |
| Server-side session store | Synchronizer Token thường đơn giản và rõ ràng. |
| SPA cần token qua cookie + custom header | Signed/session-bound Double-Submit hoặc endpoint bootstrap token cùng origin. |
| Không có server-side session nhưng có khóa ký và token binding rõ | Signed Double-Submit có thể phù hợp. |
| Nhiều subdomain không cùng mức tin cậy | Tránh cookie Domain rộng; ưu tiên host-only, session binding và kiểm tra Origin. |
| Ứng dụng đã có framework CSRF middleware | Ưu tiên dùng middleware chuẩn thay vì tự viết pattern mới. |

Không có một pattern tốt nhất cho mọi ứng dụng. Chọn theo session architecture, threat model, khả năng quản lý secret và hành vi browser.

## 6. Đưa CSRF token vào form, AJAX và SPA

### 6.1. HTML form truyền thống

Server render hidden input:

~~~html
<form method="post" action="/account/address">
  <input type="hidden" name="_csrf" value="SERVER_GENERATED_TOKEN">
  <input name="street" autocomplete="street-address">
  <button type="submit">Lưu địa chỉ</button>
</form>
~~~

Backend kiểm tra token trước khi cập nhật. Với form nhiều bước, mỗi trang phải nhận token hợp lệ; khi session rotate, token phải được cập nhật hoặc server phải có chính sách chuyển tiếp được thiết kế rõ.

### 6.2. AJAX/Fetch cùng origin

Có thể render token vào meta tag:

~~~html
<meta name="csrf-token" content="SERVER_GENERATED_TOKEN">
~~~

JavaScript đọc và gửi trong header:

~~~js
const csrf = document
  .querySelector('meta[name="csrf-token"]')
  .getAttribute("content");

await fetch("/api/settings", {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrf
  },
  body: JSON.stringify({ theme: "dark" })
});
~~~

Token không được đưa vào URL. Khi server nhận request, middleware kiểm tra session và token trước khi chạy handler nghiệp vụ.

### 6.3. SPA lấy token từ endpoint bootstrap

SPA có thể tải một endpoint cùng origin:

~~~js
const tokenResponse = await fetch("/api/csrf-token", {
  credentials: "same-origin",
  cache: "no-store"
});

if (!tokenResponse.ok) {
  throw new Error("Không lấy được CSRF token");
}

const { csrfToken } = await tokenResponse.json();
~~~

Sau đó giữ token trong memory và gắn vào mọi request thay đổi trạng thái:

~~~js
await fetch("/api/profile", {
  method: "PATCH",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken
  },
  body: JSON.stringify({ displayName: "An" })
});
~~~

Endpoint bootstrap phải kiểm tra session hoặc cấp token gắn với session ẩn danh theo thiết kế. Không cache token dùng chung giữa người dùng; response nên có Cache-Control: no-store khi phù hợp. Không đặt token vào localStorage nếu không cần; XSS có thể đọc dữ liệu trong đó.

### 6.4. Header custom và preflight

Custom header như X-CSRF-Token không thuộc nhóm CORS-safelisted request headers. Khi gửi cross-origin, nó thường kích hoạt preflight. HTML form thông thường không thể tự đặt custom header tùy ý.

Đây là một lớp hữu ích trong thiết kế API, nhưng **không được coi là biện pháp duy nhất**:

- Nếu server mở CORS credentialed cho origin độc hại, JavaScript từ origin đó có thể được phép gửi custom header sau preflight.
- Nếu có XSS trong origin tin cậy, script độc có thể đọc token và gửi header.
- Client ngoài browser có thể tự tạo header; backend vẫn cần authentication/authorization.
- API vẫn phải validate method, content type, body và quyền.

## 7. Token lifecycle: tạo, rotate, hết hạn và thu hồi

CSRF token phải có vòng đời nhất quán với session.

### 7.1. Tạo token

- Tạo bằng CSPRNG hoặc cơ chế HMAC đã được kiểm chứng.
- Gắn với session/pre-auth session phù hợp.
- Không dùng user ID, timestamp, email, session ID hoặc giá trị đoán được.
- Đảm bảo token không bị tái sử dụng giữa session khác.

### 7.2. Rotate token

Cân nhắc rotate khi:

- Session ID rotate sau đăng nhập.
- Người dùng hoàn thành MFA hoặc step-up authentication.
- Session được nâng quyền.
- User đổi mật khẩu hoặc có sự kiện bảo mật quan trọng.
- Server phát hiện token hoặc session có thể bị lộ.

Khi rotate, tránh tạo trạng thái mà các tab đang mở không thể hoạt động bất ngờ. Có thể cấp token mới qua response/endpoint bootstrap; server có thể hỗ trợ token cũ trong một khoảng chuyển tiếp ngắn nếu threat model và implementation cho phép, nhưng không giữ token cũ vô thời hạn.

### 7.3. Hết hạn và revoke

Khi session hết hạn hoặc bị revoke, token gắn session cũng phải mất hiệu lực. Không cho phép token cũ tự tạo lại session hoặc gia hạn một session đã bị thu hồi.

### 7.4. Nhiều tab và request song song

Token per-session thường thuận tiện hơn cho nhiều tab. Với token one-time, cần xử lý request song song, retry, back button và form mở lâu. Nếu server chỉ chấp nhận một token duy nhất đã bị tiêu thụ ở tab khác, trải nghiệm có thể lỗi dù user hợp lệ.

Thiết kế token lifecycle phải được kiểm thử cùng browser history, multi-tab và session rotation.

## 8. Login CSRF và logout CSRF

CSRF có thể xảy ra trước khi user đăng nhập hoặc khi đăng xuất.

### 8.1. Login CSRF

Kẻ tấn công có thể khiến browser đăng nhập vào tài khoản do kẻ tấn công kiểm soát. Nạn nhân sau đó có thể nhập dữ liệu cá nhân hoặc thông tin thanh toán vào tài khoản sai.

Phòng vệ:

- Bảo vệ endpoint login bằng pre-auth CSRF token hoặc cơ chế chống login CSRF tương đương.
- Kiểm tra Origin/Fetch Metadata phù hợp.
- Không chấp nhận luồng login tự động chỉ dựa trên form từ origin không tin cậy.
- Rotate session ID khi đăng nhập thành công.
- Hiển thị rõ tài khoản đang đăng nhập khi cần.

### 8.2. Logout CSRF

Nếu GET /logout hoặc một request không có token có thể logout người dùng, trang ngoài có thể khiến browser điều hướng tới endpoint đó. Logout CSRF thường ít nghiêm trọng hơn thay đổi tài chính nhưng có thể gây gián đoạn, phá quy trình hoặc hỗ trợ các chuỗi tấn công khác.

Dùng POST/DELETE theo hợp đồng API, CSRF token và kiểm tra nguồn request phù hợp; không để GET thay đổi trạng thái phiên.

## 9. SameSite, Origin và Fetch Metadata: lớp phòng vệ bổ sung

CSRF token nên được kết hợp với những tín hiệu khác, đặc biệt với ứng dụng cookie-based.

### 9.1. SameSite

Cookie session có thể đặt:

~~~http
Set-Cookie: __Host-session=OPAQUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- Strict hạn chế cookie trong ngữ cảnh same-site chặt hơn, có thể ảnh hưởng link từ ngoài và SSO.
- Lax thường cho phép một số điều hướng top-level cross-site dùng method an toàn; GET không được đổi trạng thái.
- None; Secure cho phép một số tích hợp cross-site nếu browser policy cho phép, nhưng cần xem xét CSRF kỹ hơn.

SameSite xét **site**, không phải origin. Một subdomain bị chiếm quyền có thể same-site với ứng dụng chính dù cross-origin. Do đó SameSite là lớp giảm rủi ro, không thay token trong mọi trường hợp.

### 9.2. Kiểm tra Origin

Với request thay đổi trạng thái, server có thể kiểm tra Origin theo allowlist chính xác:

~~~http
Origin: https://app.example.test
~~~

So sánh đầy đủ scheme, host và port. Không dùng kiểm tra includes("example.test") hoặc hậu tố chuỗi thiếu ranh giới; các host như app.example.test.attacker.test không được coi là app.example.test.

Header Origin có thể vắng mặt trong một số request/bối cảnh hoặc có giá trị đặc biệt. Xác định fallback phù hợp, thường cân nhắc Referer đã parse, và từ chối an toàn với endpoint nhạy cảm nếu không thể xác minh theo policy. Không xem Origin là authentication: client ngoài browser có thể tự gửi header này.

### 9.3. Referer

Referer có thể cung cấp URL nguồn của request. Nếu dùng làm fallback, parse URL và so origin chính xác; không so chuỗi thô. Referrer-Policy có thể làm header bị rút gọn hoặc không gửi, vì vậy cần định nghĩa rõ trường hợp thiếu.

Không dùng Referer làm bằng chứng danh tính hoặc quyền nghiệp vụ.

### 9.4. Fetch Metadata

Browser hiện đại có thể gửi các header như:

~~~http
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
~~~

Sec-Fetch-Site thường cho biết quan hệ giữa initiator và target: same-origin, same-site, cross-site hoặc none. Server có thể dùng Fetch Metadata để từ chối một số request cross-site tới endpoint nhạy cảm, đặc biệt các request không an toàn.

Ví dụ policy khái niệm:

- Cho phép request same-origin.
- Với same-site, chỉ cho phép nếu toàn bộ subdomain trong threat model được tin cậy hoặc có token hợp lệ.
- Từ chối cross-site cho endpoint thay đổi trạng thái, trừ luồng tích hợp được thiết kế riêng.
- Xử lý none và header vắng mặt theo chính sách cụ thể, không chặn mù quáng mọi trường hợp.

Fetch Metadata là lớp bổ sung; browser cũ hoặc client ngoài browser có thể không gửi. Backend vẫn cần CSRF token và authorization theo mô hình ứng dụng.

## 10. CORS không thay thế CSRF token

CORS chủ yếu kiểm soát JavaScript ở origin khác có được **đọc response** hay không. Nó không chặn mọi form submission hoặc request cross-origin.

Ví dụ trang ngoài có thể gửi form POST với content type form:

~~~html
<form action="https://app.example.test/account/email" method="post">
  <input name="email" value="attacker@example.test">
  <button>Submit</button>
</form>
~~~

Nếu endpoint chấp nhận form và chỉ kiểm tra cookie, CSRF có thể vẫn xảy ra dù response không đọc được.

Custom header có thể khiến browser preflight và ngăn form HTML đơn giản tạo cùng request; nhưng nếu server cho phép origin tấn công qua CORS credentialed, hoặc có XSS trong origin được phép, lớp bảo vệ đó không còn đáng tin.

**Không dùng cấu hình CORS làm CSRF defense duy nhất.** Cần token hoặc một thiết kế chống CSRF đã được kiểm chứng, SameSite và kiểm tra backend.

## 11. CSRF token không chống XSS

CSRF token được thiết kế để chống trang ngoài giả mạo request trong khi không đọc được token hợp lệ từ origin ứng dụng. Nhưng XSS chạy ngay trong origin tin cậy có thể đọc token từ DOM/response cùng origin và gửi request có token.

Ví dụ:

~~~js
const token = document
  .querySelector('meta[name="csrf-token"]')
  .content;

await fetch("/api/change-email", {
  method: "POST",
  headers: { "X-CSRF-Token": token },
  body: new URLSearchParams({ email: "attacker@example.test" })
});
~~~

Nếu script độc đã thực thi trong trang, nó có thể dùng token và session của người dùng. Do đó cần:

- Ngăn DOM XSS bằng text sink, encode/sanitize đúng context.
- Dùng CSP, nonce/hash và Trusted Types khi phù hợp.
- Giảm script bên thứ ba và tách widget ít tin cậy.
- Kiểm tra authorization, xác thực lại và xác nhận giao dịch cho hành động nhạy cảm.

CSRF token không phải giải pháp cho mọi hành động của mã độc trong browser.

## 12. Những trường hợp cần threat model riêng

### 12.1. API chỉ dùng bearer token trong Authorization

Nếu token chỉ được JavaScript thêm vào header và không được browser tự động gửi, mô hình CSRF khác cookie session. Một trang ngoài không thể tự đọc token trong memory của origin ứng dụng do SOP, và HTML form không thể tùy ý đặt Authorization header.

Tuy nhiên:

- XSS có thể lấy token hoặc gọi API trong context của ứng dụng.
- CORS cấu hình quá rộng có thể cho phép origin ngoài gửi request với header nếu họ có token.
- Token lưu trong localStorage dễ bị XSS đọc.
- Backend vẫn cần xác thực và authorization.

Không áp dụng máy móc CSRF token cookie-based cho mọi API; đánh giá cách credential được gửi và khả năng browser tự gắn credential.

### 12.2. WebSocket

WebSocket handshake không dùng CORS preflight như fetch. Nếu browser gửi cookie khi mở WebSocket, server cần kiểm tra Origin theo allowlist, xác thực phiên và phân quyền từng channel/message. CSRF token hoặc cơ chế chống cross-site WebSocket hijacking có thể cần tùy thiết kế.

### 12.3. OAuth/OIDC callback

OAuth dùng tham số state để ràng buộc authorization response với yêu cầu đăng nhập đã khởi tạo từ client và giảm nguy cơ login CSRF/response injection. State cần khó đoán, gắn với user-agent/session hoặc transaction tương ứng và được kiểm tra khi callback. PKCE bảo vệ authorization code exchange trước một số kiểu interception; không bỏ qua việc kiểm tra state theo flow và thư viện OIDC an toàn.

Không nhầm OAuth state với CSRF token của mọi endpoint ứng dụng. Chúng có phạm vi và vòng đời riêng.

## 13. Những lỗi triển khai thường gặp

1. **Token cố định trong source code:** mọi user/session dùng cùng một giá trị, attacker có thể biết trước.
2. **Token dự đoán được:** tạo từ timestamp, user ID hoặc Math.random().
3. **Không gắn token với session:** token của user A được chấp nhận trong session user B.
4. **Chỉ kiểm tra ở frontend:** attacker bỏ qua JavaScript và gửi request trực tiếp.
5. **Chỉ kiểm tra cookie tồn tại:** cookie là credential tự động, không chứng minh ý định request.
6. **Đặt token trong query hoặc fragment:** token dễ vào history, logs, analytics hoặc link được chia sẻ.
7. **Double-submit equality không chữ ký:** có thể yếu nếu attacker chèn được cookie cùng domain.
8. **Cho phép CORS credentialed quá rộng:** origin độc hại có thể lấy token hoặc gửi request tùy chính sách.
9. **Dùng SameSite thay mọi lớp:** subdomain same-site và một số luồng điều hướng vẫn cần phân tích.
10. **Không rotate sau login/MFA:** session fixation hoặc token pre-auth còn hiệu lực.
11. **Token one-time không xử lý nhiều tab:** request hợp lệ bị từ chối ngẫu nhiên.
12. **GET thay đổi trạng thái:** mở đường CSRF qua image, link, prefetch hoặc navigation.
13. **Không bảo vệ login/logout:** vẫn có thể xảy ra login CSRF hoặc logout CSRF.
14. **Tin token khi có XSS:** mã độc cùng origin có thể đọc và dùng token.
15. **Log token:** làm lộ token trong hệ thống giám sát và tạo đường replay trong session.

## 14. Thực hành A — Synchronizer token với form

Thực hiện trong ứng dụng local/staging do bạn kiểm soát. Tạo một form cập nhật profile có hidden token do server cấp:

~~~html
<form method="post" action="/demo/profile">
  <input type="hidden" name="csrf_token" value="TOKEN_FROM_SERVER">
  <input name="displayName" value="An">
  <button type="submit">Lưu</button>
</form>
~~~

Trong DevTools → **Network**:

1. Gửi form hợp lệ; xem Request Payload/Form Data có csrf_token.
2. Xóa token hoặc thay một ký tự rồi gửi lại trong môi trường test.
3. Server phải từ chối request thiếu/sai token trước khi cập nhật.
4. Thử token của session khác; server cũng phải từ chối.
5. Xác minh response lỗi không tiết lộ token mong đợi hoặc session secret.

**Kết luận:** Token phải khớp session hiện tại, và backend mới là nơi quyết định request hợp lệ.

## 15. Thực hành B — SPA custom header

Trên frontend local, lấy CSRF token từ endpoint bootstrap cùng origin:

~~~js
const result = await fetch("/api/csrf-token", {
  cache: "no-store",
  credentials: "same-origin"
});
const { csrfToken } = await result.json();
~~~

Gửi request thay đổi trạng thái:

~~~js
await fetch("/api/profile", {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken
  },
  body: JSON.stringify({ displayName: "An" })
});
~~~

Quan sát:

- Header custom được gửi trong request.
- Server từ chối khi thiếu token hoặc token sai.
- Token không nằm trong URL.
- Endpoint bootstrap không bị cache dùng chung giữa các session.
- Session ID vẫn nằm trong cookie phù hợp, không được chuyển sang body/query.

Nếu frontend và API khác origin, kiểm tra preflight và CORS allowlist; không mở CORS credentialed cho origin không tin cậy.

## 16. Thực hành C — Kiểm tra SameSite và Origin/Fetch Metadata

Dùng hai site thử nghiệm do bạn kiểm soát, một ứng dụng đích và một trang nguồn khác site. Chỉ thử endpoint không gây tác động thật.

1. Đặt session cookie demo với SameSite=Lax.
2. Từ trang nguồn, tạo một form POST tới endpoint test.
3. Trong Network, kiểm tra request có được gửi và cookie có đi kèm hay không.
4. Đổi sang SameSite=Strict và lặp lại.
5. Kiểm tra request headers Origin, Referer (nếu có) và Sec-Fetch-Site.
6. Thử chính sách server từ chối cross-site unsafe request.
7. Đảm bảo request thiếu token vẫn bị từ chối, ngay cả khi tín hiệu Origin/SameSite có vẻ hợp lệ.

**Kết luận:** Cookie policy và request metadata là lớp bổ sung; token vẫn được server xác minh theo session.

## 17. Thực hành D — Mô phỏng nhiều tab và rotation

Trong môi trường thử nghiệm:

1. Mở hai tab cùng session và tải form chứa token.
2. Rotate session hoặc CSRF token ở tab thứ nhất.
3. Gửi form cũ ở tab thứ hai.
4. Quan sát ứng dụng từ chối, refresh token hoặc yêu cầu tải lại form theo thiết kế.
5. Thử Back/Forward và request song song để phát hiện token lifecycle lỗi.

Nếu dùng token one-time, kiểm tra request đồng thời và retry. Nếu dùng token per-session, kiểm tra token cũ bị vô hiệu hóa đúng lúc session rotate.

## 18. Checklist review CSRF token

- [ ] Xác định endpoint nào thay đổi trạng thái; không để GET/HEAD thực hiện nghiệp vụ nhạy cảm.
- [ ] Xác định credential browser tự gửi (cookie, HTTP auth, client certificate) và threat model CSRF.
- [ ] Dùng Synchronizer Token hoặc Double-Submit đã được thiết kế/kiểm chứng; ưu tiên framework middleware phù hợp.
- [ ] Token khó đoán, sinh bằng CSPRNG hoặc cơ chế ký/HMAC chuẩn; không dùng Math.random/timestamp.
- [ ] Token được gắn với session/pre-auth session và không dùng chung giữa người dùng.
- [ ] Kiểm tra token ở backend trước khi thực hiện nghiệp vụ.
- [ ] Không dùng session ID làm CSRF token.
- [ ] Không đặt token trong URL, query, fragment, log hoặc analytics.
- [ ] Với double-submit, tránh equality ngây thơ; cân nhắc signed/session-bound token và cookie host-only.
- [ ] Cấu hình cookie session Secure, HttpOnly, SameSite và scope hẹp.
- [ ] Kết hợp Origin/Referer và Fetch Metadata theo policy; so origin chính xác.
- [ ] Không coi CORS hoặc custom header là bảo vệ duy nhất.
- [ ] Rotate token/session sau login, MFA, step-up và thay đổi quyền theo thiết kế.
- [ ] Xử lý token expiry, logout, revoke, nhiều tab và Back/Forward.
- [ ] Có login CSRF/logout CSRF protection khi phù hợp.
- [ ] Chống XSS; CSRF token không ngăn script độc cùng origin.
- [ ] Request thực tế vẫn qua authentication, authorization, ownership và validation.
- [ ] Không log token hoặc cookie bí mật.
- [ ] Kiểm thử trên browser mục tiêu bằng DevTools và log server.

## 19. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “SOP chặn mọi request cross-site.” | **Sai** | Nhiều form, navigation và tài nguyên vẫn có thể tạo request. |
| “Không đọc được response nghĩa là không có CSRF.” | **Sai** | CSRF có thể chỉ cần request được thực hiện. |
| “Session ID và CSRF token là một.” | **Sai** | Một giá trị xác định phiên, giá trị kia chống giả mạo request. |
| “Token chỉ cần kiểm tra ở JavaScript.” | **Sai** | Backend phải xác minh trước khi đổi trạng thái. |
| “Token trong hidden input không thể bị lộ.” | **Sai** | XSS hoặc script cùng origin có thể đọc DOM. |
| “HttpOnly loại bỏ CSRF.” | **Sai** | Browser vẫn tự gửi cookie HttpOnly. |
| “SameSite luôn thay thế CSRF token.” | **Sai** | Cần xét subdomain same-site, luồng đăng nhập và browser policy. |
| “CORS là CSRF defense.” | **Sai** | CORS chủ yếu kiểm soát đọc response, không chặn mọi request. |
| “Double-submit chỉ cần so hai chuỗi bằng nhau.” | **Chưa đủ** | Cookie injection có thể làm pattern ngây thơ mất tác dụng; cần binding/chữ ký phù hợp. |
| “Token one-time luôn an toàn và dễ dùng hơn.” | **Sai** | Có thể gây lỗi nhiều tab, retry và request song song. |
| “GET có thể đổi trạng thái nếu có token.” | **Sai** | Safe methods không được dùng cho thay đổi trạng thái nghiệp vụ. |
| “CSRF token ngăn XSS.” | **Sai** | XSS cùng origin có thể lấy token và dùng session. |
| “OAuth state và CSRF token ứng dụng luôn thay thế nhau.” | **Sai** | Chúng có phạm vi và vòng đời riêng. |

## 20. Tổng kết

CSRF token là bằng chứng request được tạo qua một luồng ứng dụng phù hợp trong bối cảnh browser tự động gửi cookie. Với Synchronizer Token, server lưu token gắn session và render/cấp token cho client. Với Double-Submit, browser gửi lại token qua cookie và body/header; biến thể signed/session-bound giúp giảm nguy cơ cookie injection.

Ba nguyên tắc cần nhớ:

1. **Token phải khó đoán và gắn với phiên:** tạo bằng CSPRNG hoặc cơ chế mật mã chuẩn, không dùng session ID, không để token xuất hiện trong URL/log.
2. **Backend là nơi xác minh:** kiểm tra token trên mọi request thay đổi trạng thái; kết hợp SameSite, Origin/Referer, Fetch Metadata và CORS theo vai trò riêng.
3. **CSRF không phải XSS:** script độc chạy cùng origin có thể đọc token và thao tác trong session. Cần phòng XSS, phân quyền backend và yêu cầu xác thực lại cho hành động nhạy cảm.

Khi review một endpoint, hãy hỏi: **browser tự gửi credential nào, token được tạo và gắn với session ra sao, request nào phải có token, server kiểm tra trước bước nào, và điều gì xảy ra khi session rotate hoặc bị revoke?** Trả lời rõ các câu hỏi này giúp bảo vệ hành động thay đổi trạng thái thay vì chỉ dựa vào cookie hoặc một header có vẻ đáng tin.
