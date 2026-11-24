# Double-submit cookie: phòng vệ CSRF bằng cookie và request token

> **Chương:** CSRF  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Double-submit cookie** là một mẫu phòng vệ Cross-Site Request Forgery (CSRF): server đặt một token trong cookie, sau đó yêu cầu client gửi lại cùng token trong một phần khác của request, thường là custom header hoặc field của form. Server chỉ xử lý thao tác thay đổi trạng thái nếu hai giá trị khớp và token hợp lệ.

Mẫu này tận dụng việc trình duyệt tự gửi cookie theo phạm vi phù hợp, trong khi trang khác origin không thể đọc cookie của ứng dụng để sao chép token vào header. Tuy nhiên, cách triển khai ngây thơ có thể bị vượt qua nếu kẻ tấn công chèn cookie cùng tên từ sibling subdomain hoặc kiểm soát được giá trị cookie. Vì vậy, hệ thống hiện đại nên dùng **signed double-submit token gắn với phiên đăng nhập**, giới hạn cookie bằng prefix __Host-, và kết hợp các lớp kiểm tra request khác.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích CSRF và nguyên lý double-submit cookie.
2. Phân biệt naïve double-submit với signed/session-bound double-submit.
3. Thiết kế luồng cookie token có thể đọc bởi JavaScript và request token được gửi trong custom header.
4. Giải thích vì sao HttpOnly, SameSite, CORS và SOP không thay thế hoàn toàn CSRF token.
5. Nhận diện cookie injection/tossing và duplicate cookie có thể phá vỡ double-submit ngây thơ.
6. Tạo token có HMAC gắn với session, kiểm tra bằng so sánh an toàn và từ chối token sai định dạng.
7. Quản lý token khi đăng nhập, xoay session, logout và thay đổi quyền.
8. Kiểm chứng luồng double-submit bằng DevTools và Node.js trong môi trường cục bộ.

## 1. CSRF và lý do cần token

### 1.1 Trình duyệt tự gửi credential

Giả sử người dùng đăng nhập vào https://bank.example. Browser lưu session cookie:

~~~http
Set-Cookie: __Host-session=RANDOM_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Khi người dùng truy cập một trang độc hại khác, trang đó có thể cố khiến browser gửi request đến bank:

~~~html
<form action="https://bank.example/transfer" method="POST">
  <input type="hidden" name="to" value="attacker">
  <input type="hidden" name="amount" value="1000">
  <button>Continue</button>
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Nếu cookie được gửi kèm và server chỉ dựa vào session cookie để xác thực, server có thể hiểu nhầm request do người dùng chủ động thực hiện. Đây là CSRF: kẻ tấn công lợi dụng **credential tự động được browser đính kèm** để kích hoạt thao tác mà người dùng không mong muốn.

SameSite giúp hạn chế một số trường hợp, nhưng không giải quyết mọi luồng, đặc biệt với request same-site từ sibling subdomain, cookie SameSite=None, endpoint legacy hoặc những kiến trúc cần điều hướng cross-site hợp lệ.

### 1.2 SOP không ngăn mọi request cross-origin

Same-Origin Policy thường ngăn JavaScript ở trang ngoài đọc response hoặc DOM của bank. Nhưng SOP không cấm mọi form submission hay navigation cross-origin. Một request có thể đến server dù script ở trang ngoài không đọc được response.

Do đó, không thể kết luận “CORS chặn đọc response nên CSRF không xảy ra”. Server phải kiểm tra request thay đổi trạng thái bằng cơ chế chống CSRF phù hợp.

### 1.3 Token CSRF chứng minh request có quyền truy cập token

Một trang khác origin không thể tùy ý đọc nội dung cookie của bank qua JavaScript do SOP. Nếu ứng dụng yêu cầu request chứa thêm một token chỉ trang hợp lệ mới lấy được, trang tấn công khó tạo request hợp lệ.

Với double-submit cookie, token được gửi ở hai nơi:

- Cookie do server đặt và browser tự đính kèm.
- Header hoặc form field do JavaScript của ứng dụng chủ động thêm.

Server kiểm tra hai giá trị giống nhau, sau đó xác minh token theo thiết kế. Cookie session xác định phiên đăng nhập; CSRF token chứng minh request có quyền lấy/đưa token theo origin ứng dụng.

## 2. Nguyên lý double-submit cookie

### 2.1 Hai bản sao của một token

Server tạo token ngẫu nhiên và trả cookie:

~~~http
Set-Cookie: __Host-csrf=RANDOM_CSRF_TOKEN; Path=/; Secure; SameSite=Lax
~~~

Cookie CSRF **không đặt HttpOnly** trong mẫu SPA phổ biến, vì JavaScript cùng origin cần đọc token để thêm vào request header. Cookie session vẫn phải HttpOnly.

Client đọc cookie rồi gửi lại:

~~~js
function readCookie(name) {
  const prefix = name + '=';
  const item = document.cookie
    .split('; ')
    .find(part => part.startsWith(prefix));

  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

async function updateProfile(payload) {
  const token = readCookie('__Host-csrf');
  if (!token) throw new Error('Missing CSRF token');

  return fetch('/api/profile', {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': token
    },
    body: JSON.stringify(payload)
  });
}
~~~

Khi browser gửi request, cookie __Host-csrf tự đi kèm; JavaScript gửi thêm header X-CSRF-Token. Server so sánh hai giá trị.

### 2.2 Luồng xử lý

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Ứng dụng cùng origin
    participant S as Server
    B->>A: Tải trang ứng dụng
    A->>S: GET trang / endpoint cấp token
    S-->>B: Set-Cookie __Host-csrf=TOKEN
    Note over B: Cookie được lưu; JS cùng origin đọc được
    B->>S: PATCH /api/profile
    Note over B,S: Cookie __Host-csrf tự gửi<br/>Header X-CSRF-Token do JS thêm
    S->>S: Kiểm tra session, cookie token và header token
    alt Token hợp lệ
        S-->>B: Thực hiện thao tác
    else Thiếu hoặc sai token
        S-->>B: 403 Forbidden
    end
~~~

### 2.3 Vì sao phải gửi token ở hai vị trí?

Nếu server chỉ kiểm tra cookie, browser tự gửi cookie cho request cross-site theo chính sách cookie và CSRF vẫn có thể xảy ra. Nếu server yêu cầu thêm header hoặc field chứa cùng token, trang ngoài thường không thể đọc cookie để lấy giá trị đó.

Đối với custom header cross-origin, browser thường cần CORS preflight; nhưng không nên lấy preflight làm lớp bảo vệ duy nhất. Cần cấu hình CORS chặt chẽ và server vẫn xác minh CSRF token.

## 3. Naïve double-submit cookie

### 3.1 Cách triển khai cơ bản

Mẫu đơn giản tạo token ngẫu nhiên, đặt cookie và yêu cầu client gửi lại token:

~~~http
Set-Cookie: csrf_token=RANDOM_VALUE; Path=/; Secure; SameSite=Lax
~~~

Server:

~~~js
function verifyNaiveDoubleSubmit(req) {
  const cookieToken = req.cookies.csrf_token;
  const requestToken = req.get('X-CSRF-Token');

  return Boolean(cookieToken) &&
    Boolean(requestToken) &&
    cookieToken === requestToken;
}
~~~

Cách này dễ triển khai nhưng có một giả định quan trọng: **attacker không thể đặt hoặc ghi đè cookie token của ứng dụng**.

### 3.2 Cookie injection phá giả định đó

Nếu ứng dụng dùng cookie tên csrf_token có Domain rộng, sibling subdomain có thể đặt cookie cùng tên:

~~~http
Set-Cookie: csrf_token=ATTACKER_KNOWN_VALUE; Domain=example.com; Path=/; Secure; SameSite=Lax
~~~

Browser có thể gửi cả cookie hợp lệ và cookie do attacker đặt tới ứng dụng. Nếu server/parser chọn giá trị do attacker kiểm soát, attacker có thể biết trước giá trị cần gửi trong header.

Trong một số thiết kế, kẻ tấn công có thể ép browser gửi cookie token đã biết và tạo request chứa cùng giá trị. Khi đó kiểm tra “cookie token == header token” không chứng minh token được server cấp cho phiên người dùng.

Các nguyên nhân phổ biến:

- Cookie CSRF có Domain=example.com trong khi sibling subdomain không đáng tin.
- Parser chọn first/last khi có cookie trùng tên.
- Server không ràng buộc token với session hiện tại.
- Ứng dụng tin cookie token chỉ vì browser gửi nó.
- Cấu hình CORS/credentials cho phép origin không đáng tin đọc response hoặc lấy token.

### 3.3 Cookie host-only giảm bề mặt

Không khai báo Domain để tạo cookie host-only. Với cookie CSRF có thể đọc bởi JavaScript, dùng prefix __Host- khi triển khai trên HTTPS:

~~~http
Set-Cookie: __Host-csrf=RANDOM_VALUE; Path=/; Secure; SameSite=Lax
~~~

__Host- yêu cầu Secure, Path=/ và không có Domain. Sibling subdomain không thể đặt một domain cookie __Host-csrf cho parent domain trong browser hỗ trợ prefix. Nếu sibling bỏ Domain, cookie chỉ thuộc host sibling và không được gửi đến app host.

Prefix này giúp giảm cookie tossing nhưng không tự xác minh token và không thay thế kiểm tra server.

## 4. Signed double-submit cookie gắn với session

### 4.1 Vì sao cần chữ ký?

Để chống cookie injection, token nên chứa một thành phần xác thực bằng khóa bí mật chỉ server biết. Chữ ký cần gắn với **session hiện tại**, không chỉ ký một nonce tùy ý.

Một thiết kế phổ biến:

~~~text
nonce      = random 256-bit value
signature  = HMAC-SHA-256(server_secret, session_id || separator || nonce)
token      = base64url(nonce) + "." + base64url(signature)
~~~

Server kiểm tra:

1. Có session hợp lệ và đã xác thực không?
2. Cookie CSRF và request token có cùng giá trị không?
3. Token có đúng cấu trúc và độ dài không?
4. Chữ ký HMAC có hợp lệ với session hiện tại không?

Nếu attacker tự đặt một nonce và biết giá trị đó, họ vẫn không thể tạo chữ ký hợp lệ nếu không biết server secret. Token gắn với session nên chữ ký lấy từ phiên khác cũng không dùng được cho phiên nạn nhân.

### 4.2 Tạo token với Node.js crypto

Ví dụ helper minh họa:

~~~js
import {
  createHmac,
  randomBytes,
  timingSafeEqual
} from 'node:crypto';

const csrfSecret = process.env.CSRF_HMAC_SECRET;

if (!csrfSecret || Buffer.byteLength(csrfSecret) < 32) {
  throw new Error('CSRF_HMAC_SECRET must contain at least 32 bytes');
}

function signCsrfNonce(sessionId, nonce) {
  return createHmac('sha256', csrfSecret)
    .update(sessionId, 'utf8')
    .update('\0')
    .update(nonce, 'utf8')
    .digest();
}

function createCsrfToken(sessionId) {
  const nonce = randomBytes(32).toString('base64url');
  const signature = signCsrfNonce(sessionId, nonce)
    .toString('base64url');

  return nonce + '.' + signature;
}
~~~

Nonce có 256 bit entropy từ bộ sinh số ngẫu nhiên mật mã. Secret HMAC cần được quản lý như secret server: lưu trong secret manager hoặc biến môi trường được bảo vệ, không hardcode vào source, không gửi xuống browser và có quy trình rotation.

Dấu phân cách null byte làm rõ ranh giới giữa session ID và nonce khi tạo dữ liệu ký. Trong triển khai thực tế, cần version token nếu có kế hoạch thay đổi format/secret.

### 4.3 Xác minh token

~~~js
function verifyCsrfToken(sessionId, token) {
  if (typeof token !== 'string') return false;

  const parts = token.split('.');
  if (parts.length !== 2) return false;

  const [nonce, encodedSignature] = parts;

  // 32-byte base64url không padding có 43 ký tự.
  if (!/^[A-Za-z0-9_-]{43}$/.test(nonce)) return false;
  if (!/^[A-Za-z0-9_-]{43}$/.test(encodedSignature)) return false;

  const received = Buffer.from(encodedSignature, 'base64url');
  const expected = signCsrfNonce(sessionId, nonce);

  if (received.length !== expected.length) return false;
  return timingSafeEqual(received, expected);
}
~~~

timingSafeEqual giúp so sánh chữ ký với thời gian ít phụ thuộc dữ liệu hơn so với so sánh chuỗi thông thường. Phải kiểm tra độ dài trước vì hàm yêu cầu hai buffer cùng độ dài.

Token được ràng buộc với session ID. Nếu session đổi sau đăng nhập, logout/login hoặc rotation, token cũ không còn hợp lệ với session mới.

### 4.4 So sánh cookie token với request token

Server cần lấy đúng một cookie CSRF và đúng một header token. Ví dụ logic:

~~~js
function constantTimeStringEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;

  const left = Buffer.from(a, 'utf8');
  const right = Buffer.from(b, 'utf8');

  if (left.length !== right.length) return false;
  return timingSafeEqual(left, right);
}

function getUniqueCookieValue(rawHeader, expectedName) {
  const values = [];

  for (const part of (rawHeader || '').split(';')) {
    const item = part.trim();
    const separator = item.indexOf('=');
    if (separator < 0) continue;

    const name = item.slice(0, separator).trim();
    const value = item.slice(separator + 1).trim();
    if (name === expectedName) values.push(value);
  }

  // Token base64url không chứa dấu chấm phẩy; từ chối thiếu hoặc trùng.
  return values.length === 1 ? values[0] : null;
}

function verifyDoubleSubmit(req) {
  const sessionId = req.session?.id;
  if (!sessionId) return false;

  const cookieToken = getUniqueCookieValue(
    req.headers.cookie,
    '__Host-csrf'
  );
  const headerToken = req.get('X-CSRF-Token');

  if (!constantTimeStringEqual(cookieToken, headerToken)) {
    return false;
  }

  return verifyCsrfToken(sessionId, cookieToken);
}
~~~

Helper trên minh họa kiểm tra đúng một cookie token có định dạng base64url; production nên dùng parser cookie đã được kiểm tra và quy định rõ hành vi duplicate. Session vẫn phải được xác thực trước khi kiểm tra token. Không âm thầm lấy first/last.

Với form truyền thống, token có thể được gửi trong hidden field thay cho custom header. Server vẫn kiểm tra giá trị field với cookie và xác minh chữ ký. Không chấp nhận token qua query string vì URL có thể bị ghi vào history, log hoặc referrer.

## 5. Cookie CSRF và cookie session nên có thuộc tính khác nhau

### 5.1 Session cookie thường cần HttpOnly

Ví dụ:

~~~http
Set-Cookie: __Host-session=OPAQUE_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Session cookie chứa credential nên JavaScript không cần đọc trực tiếp. HttpOnly giảm khả năng XSS trích xuất session ID, dù XSS vẫn có thể thực hiện request cùng origin bằng quyền của người dùng.

### 5.2 CSRF cookie thường cần đọc được bởi JavaScript

Với double-submit SPA, JavaScript cần đọc token cookie để gửi trong header. Vì vậy cookie CSRF thường **không có HttpOnly**:

~~~http
Set-Cookie: __Host-csrf=SIGNED_TOKEN; Path=/; Secure; SameSite=Lax
~~~

Token không phải session credential và không nên cấp quyền truy cập tài khoản nếu đứng một mình. Nó là một bằng chứng chống CSRF gắn với session.

Nếu yêu cầu bảo mật không cho phép JavaScript đọc token cookie, dùng synchronizer token hoặc endpoint cấp token để trả token trong response body/meta tag và lưu trong bộ nhớ của ứng dụng; đừng cố đọc cookie HttpOnly bằng JavaScript.

### 5.3 SameSite hỗ trợ nhưng không thay thế token

| Thuộc tính | Vai trò | Giới hạn |
|---|---|---|
| SameSite=Strict | Hạn chế cookie trong nhiều ngữ cảnh cross-site | Có thể ảnh hưởng luồng liên kết/SSO; sibling subdomain cùng site không bị coi là cross-site |
| SameSite=Lax | Cho phép một số top-level navigation an toàn như GET | Không chặn mọi CSRF, đặc biệt GET có tác dụng phụ |
| SameSite=None; Secure | Cho phép cookie trong ngữ cảnh cross-site khi browser cho phép | Mở rộng bề mặt CSRF; third-party cookie có thể bị chặn |
| Secure | Chỉ gửi cookie qua kết nối an toàn theo quy tắc browser | Không chống CSRF |
| HttpOnly | Ngăn JavaScript đọc session cookie | Không ngăn request do XSS khởi tạo |

Không đặt SameSite=None chỉ để “sửa” lỗi cookie mà không hiểu luồng cross-site. Đánh giá yêu cầu SSO, iframe, thanh toán và chính sách third-party cookie.

## 6. CORS, Origin và Fetch Metadata là lớp bổ trợ

### 6.1 Custom header và CORS

Custom header như X-CSRF-Token không phải header safelisted của CORS. Nếu JavaScript từ origin khác cố gửi header này, browser thường thực hiện preflight. API chỉ nên cho phép origin frontend chính xác trong CORS allowlist.

Ví dụ response preflight:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng wildcard origin khi request có credentials. Không phản chiếu tùy tiện Origin. CORS không thay token vì form HTML và các request navigation khác vẫn có thể được gửi mà không cần quyền đọc response.

### 6.2 Kiểm tra Origin

Với endpoint thay đổi trạng thái, server có thể kiểm tra Origin nếu header có mặt:

- Chấp nhận origin chính xác thuộc allowlist frontend.
- Từ chối origin không hợp lệ hoặc không mong muốn.
- Xác định rõ cách xử lý khi header thiếu hoặc có giá trị null.
- Không dùng suffix/prefix string check.
- Không coi Origin là authentication; client ngoài browser có thể giả mạo header.

Với request từ opaque origin, header có thể serialize thành null. Không allowlist null để cho phép một widget hay iframe cụ thể; nhiều ngữ cảnh opaque khác nhau cũng có thể mang giá trị này.

### 6.3 Fetch Metadata

Các header Sec-Fetch-Site, Sec-Fetch-Mode, Sec-Fetch-Dest giúp server nhận biết ngữ cảnh request. Ví dụ endpoint nhạy cảm có thể từ chối một số request cross-site không phù hợp với chức năng.

Nhưng Fetch Metadata có thể vắng ở client cũ hoặc request không phải browser; nó không thay thế CSRF token, xác thực và phân quyền. Xác định allowlist luồng hợp lệ như callback đăng nhập, thanh toán hoặc form bên ngoài trước khi áp dụng chính sách chặn.

## 7. Các trường hợp dễ triển khai sai

### 7.1 Đặt Domain rộng cho CSRF cookie

Cookie csrf_token có Domain=example.com khiến sibling subdomain có thể đặt cookie cùng tên. Dùng host-only và prefix __Host- để giới hạn phạm vi.

### 7.2 Dùng token cố định hoặc có thể đoán

Token như csrf=123, username, timestamp hoặc giá trị hardcode không cung cấp tính ngẫu nhiên cần thiết. Dùng nonce mật mã đủ entropy hoặc token được ký với server secret và gắn session.

### 7.3 Chỉ so sánh hai giá trị mà không xác thực nguồn gốc

Naïve double-submit chỉ kiểm tra cookie/header bằng nhau. Nếu attacker có thể đặt cookie, họ có thể gửi lại cùng giá trị. Signed/session-bound token giúp kiểm tra token do server tạo cho đúng session.

### 7.4 Parser chọn một cookie khi có duplicate

Hai cookie cùng tên có thể xuất hiện trong raw header. Server không nhận được Domain/Path để phân biệt. Từ chối duplicate CSRF cookie và session cookie; không dựa vào thứ tự.

### 7.5 Bật CORS quá rộng

Cho phép mọi origin có credentials hoặc phản chiếu Origin có thể làm origin không đáng tin đọc token/response. Chỉ cho phép frontend chính xác, kiểm tra preflight và không dùng Access-Control-Allow-Origin: * với credentials.

### 7.6 Nghĩ HttpOnly cho CSRF cookie là an toàn hơn

Double-submit SPA cần JavaScript đọc cookie token để đưa vào header. Nếu đặt HttpOnly, JS không đọc được; luồng sẽ không hoạt động. Session cookie vẫn phải HttpOnly. Nếu không muốn JS đọc cookie, chọn synchronizer token hoặc endpoint cấp token.

### 7.7 CSRF token không bảo vệ khỏi XSS

Nếu attacker có script chạy trong origin ứng dụng, script đó có thể đọc CSRF cookie, gọi endpoint lấy token hoặc gửi request với token hợp lệ. Cần phòng XSS bằng output encoding, sanitizer, CSP, Trusted Types khi phù hợp và kiểm soát dữ liệu DOM.

## 8. Vòng đời token

### 8.1 Cấp token

Có thể cấp token cùng trang HTML hoặc qua endpoint same-origin:

~~~http
GET /api/csrf-token HTTP/1.1
Host: app.example.com
Cookie: __Host-session=...
~~~

Server xác thực session, tạo hoặc lấy token gắn với session và trả cookie __Host-csrf. Nếu trả token trong body, đặt cache policy phù hợp, ví dụ Cache-Control: no-store, và tránh cache chung cho nhiều người dùng.

### 8.2 Khi đăng nhập và nâng quyền

Sau khi đăng nhập thành công, server nên xoay session ID. CSRF token cần được tạo lại hoặc được ký theo session ID mới. Không giữ token gắn với session trước xác thực rồi tái sử dụng cho session đã đăng nhập.

Tương tự, khi đổi tài khoản, đổi quyền hoặc tái xác thực, hãy cân nhắc rotate token và session theo chính sách.

### 8.3 Khi logout

Logout cần thu hồi session phía server và xóa cả cookie session lẫn CSRF cookie với đúng scope:

~~~http
Set-Cookie: __Host-session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: __Host-csrf=; Max-Age=0; Path=/; Secure; SameSite=Lax
~~~

Không thể chỉ xóa cookie CSRF rồi giữ session cũ mà gọi đó là logout. Nếu server còn chấp nhận session ID, request tiếp theo vẫn có thể được xác thực.

### 8.4 Nhiều tab và token rotation

Nếu token được rotate sau mỗi request, các tab có thể giữ token cũ và request hợp lệ bị từ chối. Cân nhắc token ổn định trong vòng đời session, grace period có kiểm soát hoặc cơ chế refresh token CSRF. Không hy sinh ràng buộc session để tránh lỗi đồng bộ.

## 9. Thực hành: kiểm tra signed double-submit bằng Node.js

Bài lab này dùng Node.js crypto, không cần package bên ngoài. Nó minh họa tạo token, xác minh token, kiểm tra token gắn session và phát hiện cookie/header mismatch. Không dùng secret hoặc session thật.

### 9.1 Tạo file double-submit-lab.mjs

~~~js
import {
  createHmac,
  randomBytes,
  timingSafeEqual
} from 'node:crypto';

const secret = randomBytes(32);

function sign(sessionId, nonce) {
  return createHmac('sha256', secret)
    .update(sessionId, 'utf8')
    .update('\0')
    .update(nonce, 'utf8')
    .digest();
}

function createToken(sessionId) {
  const nonce = randomBytes(32).toString('base64url');
  const mac = sign(sessionId, nonce).toString('base64url');
  return nonce + '.' + mac;
}

function verifyToken(sessionId, token) {
  if (typeof token !== 'string') return false;

  const parts = token.split('.');
  if (parts.length !== 2) return false;

  const [nonce, encodedMac] = parts;
  if (!/^[A-Za-z0-9_-]{43}$/.test(nonce)) return false;
  if (!/^[A-Za-z0-9_-]{43}$/.test(encodedMac)) return false;

  const supplied = Buffer.from(encodedMac, 'base64url');
  const expected = sign(sessionId, nonce);

  if (supplied.length !== expected.length) return false;
  return timingSafeEqual(supplied, expected);
}

function equalToken(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;

  const left = Buffer.from(a, 'utf8');
  const right = Buffer.from(b, 'utf8');
  if (left.length !== right.length) return false;

  return timingSafeEqual(left, right);
}

const sessionA = 'demo-session-A';
const sessionB = 'demo-session-B';
const tokenA = createToken(sessionA);

console.log('valid for A:', verifyToken(sessionA, tokenA));
console.log('valid for B:', verifyToken(sessionB, tokenA));
console.log('cookie/header equal:', equalToken(tokenA, tokenA));
console.log('mismatched value:', equalToken(tokenA, tokenA + 'x'));

const attackerToken = createToken('attacker-session');
console.log('attacker token valid for victim session:',
  verifyToken(sessionA, attackerToken));
~~~

Chạy:

~~~bash
node double-submit-lab.mjs
~~~

Kết quả mong đợi:

~~~text
valid for A: true
valid for B: false
cookie/header equal: true
mismatched value: false
attacker token valid for victim session: false
~~~

### 9.2 Điều cần quan sát

- Token hợp lệ với session A nhưng không hợp lệ với session B.
- Thay một ký tự của token khiến chữ ký không còn hợp lệ.
- Hai giá trị cookie/header phải khớp chính xác.
- Token do session attacker tạo không thể dùng với session nạn nhân.
- Secret chỉ tồn tại phía server; không đưa secret vào cookie hoặc JavaScript.

### 9.3 Kiểm thử luồng browser

Trong ứng dụng thử nghiệm do mình kiểm soát:

1. Đăng nhập bằng tài khoản demo và quan sát cookie __Host-session cùng __Host-csrf.
2. Kiểm tra cookie session có HttpOnly; cookie CSRF có thể đọc bởi JavaScript nhưng không có Domain.
3. Gửi một request PATCH hợp lệ và xác nhận header X-CSRF-Token khớp cookie.
4. Bỏ header hoặc sửa một ký tự token; server phải trả 403 và không thay đổi dữ liệu.
5. Gửi cookie CSRF trùng tên; server phải từ chối request nhập nhằng.
6. Đăng xuất, xác nhận session bị revoke và cả hai cookie bị xóa đúng scope.
7. Thử request từ một origin ngoài allowlist; xác minh CORS, Origin check và CSRF middleware hoạt động theo đúng chính sách.

Không dùng extension tắt SOP/CORS và không thử trên tài khoản hoặc hệ thống của người khác.

## 10. Chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Request SPA luôn 403 CSRF | Cookie token không đọc được, header thiếu hoặc stale | Kiểm tra cookie scope, JS đọc token và header request |
| Cookie token và header khác nhau | Nhiều tab, token rotation, parser duplicate hoặc encode không thống nhất | Dùng một format token, quy định rotation và từ chối duplicate |
| Naïve double-submit bị bypass | Attacker có thể chèn cookie cùng tên | Dùng host-only __Host- và signed token gắn session |
| Cookie CSRF không được lưu | Prefix __Host- thiếu Secure/Path=/ hoặc có Domain | Tuân thủ yêu cầu prefix và HTTPS |
| CORS preflight thất bại | Origin/method/header không nằm trong allowlist | Cho phép đúng frontend, method và header cần thiết |
| SameSite không ngăn request sibling | Sibling cùng site | Kiểm tra origin và token; không dùng SameSite như ranh giới subdomain |
| Token cũ còn sau login | Token không gắn session mới hoặc không rotate | Tạo token sau login/rotation và bind vào session mới |
| Logout nhưng request cũ vẫn thành công | Session chưa revoke phía server | Revoke session; cookie deletion chỉ là bước client |
| XSS vẫn thực hiện request hợp lệ | CSRF không bảo vệ khỏi script cùng origin | Phòng XSS bằng encoding, CSP, Trusted Types và sanitizer |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Double-submit cookie yêu cầu server kiểm tra những gì?

**Đáp án:** Cookie token và token gửi trong header/form field phải khớp; với thiết kế signed double-submit, token còn phải có chữ ký hợp lệ gắn với session hiện tại.

**Câu 2.** Vì sao chỉ kiểm tra cookieToken === headerToken có thể không đủ?

**Đáp án:** Nếu attacker chèn được cookie cùng tên và biết giá trị, họ có thể gửi lại cùng giá trị trong header. Cần cookie host-only/prefix phù hợp và token được ký, ràng buộc session.

**Câu 3.** Vì sao CSRF cookie trong SPA thường không có HttpOnly?

**Đáp án:** JavaScript cùng origin cần đọc token để thêm vào custom header. Session cookie vẫn nên HttpOnly. Nếu không muốn JS đọc cookie, dùng synchronizer token hoặc endpoint cấp token.

**Câu 4.** Có nên đặt Domain=example.com cho cookie CSRF của app.example.com không?

**Đáp án:** Không nếu không cần chia sẻ. Domain rộng cho phép sibling subdomain đặt cookie cùng tên. Ưu tiên host-only và prefix __Host-.

**Câu 5.** __Secure-csrf có bảo đảm host-only không?

**Đáp án:** Không. __Secure- yêu cầu Secure nhưng vẫn cho phép Domain. __Host- mới yêu cầu Secure, Path=/ và cấm Domain.

**Câu 6.** Signed double-submit gắn token với session bằng cách nào?

**Đáp án:** Server tạo nonce ngẫu nhiên và HMAC trên session ID cùng nonce. Server xác minh chữ ký bằng secret riêng; token từ session khác không hợp lệ.

**Câu 7.** SameSite=Strict có làm CSRF token không cần thiết trong mọi ứng dụng không?

**Đáp án:** Không. Sibling subdomain có thể cùng site; còn có luồng xác thực, cookie None, endpoint legacy và request khác. Phòng vệ cần xét kiến trúc và endpoint cụ thể.

**Câu 8.** CORS preflight có thay thế CSRF token không?

**Đáp án:** Không. Form/navigation cross-origin có thể gửi request mà không cần quyền đọc response. Preflight chỉ áp dụng cho các request CORS cần preflight.

**Câu 9.** Vì sao cần rotate token sau khi đăng nhập?

**Đáp án:** Session thường thay đổi sau xác thực. Token gắn session cũ không nên được tái sử dụng cho phiên mới; rotate ngăn việc dùng token trước xác thực trong phiên đã đăng nhập.

**Câu 10.** CSRF token có ngăn XSS không?

**Đáp án:** Không. Script chạy cùng origin có thể đọc token và gửi request hợp lệ. Cần phòng XSS riêng bằng output encoding, CSP, Trusted Types và sanitizer.

## 12. Checklist triển khai

Trước khi phát hành double-submit cookie, hãy kiểm tra:

1. **Cookie scope:** CSRF cookie host-only, không Domain; ưu tiên prefix __Host- trên HTTPS.
2. **Session binding:** dùng signed double-submit với HMAC/session binding hoặc synchronizer token phù hợp.
3. **Entropy:** nonce lấy từ CSPRNG, đủ độ dài; secret HMAC chỉ lưu phía server.
4. **Duplicate handling:** từ chối cookie token hoặc session cookie trùng tên; không chọn first/last.
5. **Cookie flags:** session cookie có Secure, HttpOnly, SameSite phù hợp; CSRF cookie chỉ bỏ HttpOnly khi cần JS đọc.
6. **Request transport:** gửi token trong custom header hoặc form field; tránh query string.
7. **Server validation:** kiểm tra session, cookie/header equality, HMAC và quyền nghiệp vụ trước khi thay đổi trạng thái.
8. **Origin/CORS:** allowlist chính xác; không tin Origin null; không phản chiếu Origin tùy ý.
9. **Fetch Metadata/SameSite:** dùng làm lớp bổ trợ và xác định các luồng hợp lệ.
10. **Lifecycle:** rotate token sau login/session rotation; revoke session khi logout; xóa cookie đúng scope.
11. **XSS:** hiểu rằng XSS có thể vượt qua CSRF token; phòng XSS độc lập.
12. **Testing:** kiểm tra thiếu token, sai token, token session khác, duplicate cookie, cross-origin request và logout.

**Ghi nhớ:** Double-submit cookie chỉ an toàn khi token không thể bị attacker tự đặt hoặc dự đoán. Hãy dùng **cookie host-only __Host-**, token ngẫu nhiên được **ký và ràng buộc với session**, từ chối duplicate, và kiểm tra ở server. SameSite, CORS, Origin và Fetch Metadata hỗ trợ phòng vệ nhưng không thay thế xác minh token và phân quyền.

## Tài liệu tham khảo

- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265)
- [MDN — Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)

