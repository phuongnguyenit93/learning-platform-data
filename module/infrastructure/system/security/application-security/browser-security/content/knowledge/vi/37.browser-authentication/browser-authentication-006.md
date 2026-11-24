# OIDC state

> **Chương:** Authentication browser
> **Chủ đề:** OIDC state
> **Module:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly. Thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể giải thích state trong OIDC, phân biệt state với nonce và PKCE, lưu transaction theo browser session, xác minh callback và kiểm thử tampering, expiry, replay cùng nhiều tab.

## 1. OIDC state là gì?

OpenID Connect (OIDC) xây dựng lớp xác thực danh tính trên OAuth 2.0. Trong luồng Authorization Code, ứng dụng (Relying Party hoặc OIDC client) chuyển browser tới OpenID Provider (OP) để người dùng đăng nhập và cấp quyền. Sau khi xác thực, OP chuyển browser về redirect URI của ứng dụng cùng authorization response, thường chứa authorization code.

Tham số state là giá trị do client tạo trước khi chuyển browser tới OP. Client gửi giá trị đó trong authorization request; OP phải trả lại nguyên giá trị trong authorization response. Ứng dụng đối chiếu giá trị nhận về với transaction đang chờ để xác định response có thuộc lần đăng nhập mà browser này đã khởi tạo hay không.

Ví dụ rút gọn:

```text
Authorization request:
  response_type=code
  client_id=web-client
  redirect_uri=https://app.example.test/oidc/callback
  scope=openid profile
  state=<random-value>

Authorization response:
  code=<authorization-code>
  state=<same-random-value>
```

Client chỉ tiếp tục xử lý response khi state khớp với transaction còn hiệu lực đã lưu trước đó. Nếu state thiếu, sai, hết hạn hoặc đã được dùng, ứng dụng phải từ chối response và không đổi authorization code lấy token.

State là một correlation value (giá trị liên kết transaction). Nó không chứng minh danh tính người dùng, không thay thế việc xác minh ID token và không phải access token.

## 2. Vì sao cần state?

Browser có thể nhận callback mà không phải do chính browser đó vừa khởi tạo luồng đăng nhập. Attacker có thể tạo authorization response trong một phiên khác rồi tìm cách khiến browser nạn nhân mở callback đó. Nếu ứng dụng chỉ nhìn thấy một authorization code hợp lệ mà không kiểm tra nguồn gốc transaction, có thể xảy ra login CSRF hoặc authorization response injection.

Ví dụ tình huống login CSRF:

1. Attacker đăng nhập vào OP bằng tài khoản của attacker và bắt đầu authorization flow cho ứng dụng.
2. Attacker lấy callback URL chứa authorization code của phiên đó.
3. Attacker tìm cách khiến browser nạn nhân mở callback URL.
4. Nếu ứng dụng chấp nhận code mà không kiểm tra transaction đã được browser nạn nhân khởi tạo, nạn nhân có thể bị đăng nhập vào tài khoản của attacker.
5. Nạn nhân có thể tải lên dữ liệu hoặc nhập thông tin cá nhân trong phiên mà attacker kiểm soát.

Với state được tạo và gắn với browser session trước khi redirect, callback từ flow khác không có state transaction tương ứng trong session của nạn nhân. Ứng dụng từ chối response đó.

State cũng giúp client ghép callback với đúng lần đăng nhập khi có nhiều tab, nhiều issuer hoặc nhiều request xác thực đang chờ. Mỗi authorization request phải có transaction riêng.

### 2.1. State bảo vệ điều gì?

- Liên kết authorization response với yêu cầu đăng nhập đã bắt đầu.
- Giảm nguy cơ login CSRF và unsolicited authorization response.
- Phát hiện callback bị sửa state hoặc được phát lại sau khi transaction đã dùng.
- Giữ đúng ngữ cảnh cho nhiều lần đăng nhập đồng thời.
- Cho phép khôi phục một phần trạng thái giao diện sau redirect, nếu dữ liệu đó được lưu an toàn phía client hoặc server.

State không tự bảo vệ mọi endpoint của ứng dụng khỏi CSRF. Những API dùng cookie để xác thực vẫn cần thiết kế CSRF defense phù hợp. State cũng không ngăn XSS: script chạy trong origin có thể đọc state lưu ở JavaScript storage hoặc thao tác trực tiếp với callback.

## 3. State khác nonce và PKCE như thế nào?

Ba cơ chế này thường xuất hiện trong cùng một OIDC Authorization Code Flow, nhưng bảo vệ các liên kết khác nhau:

| Cơ chế | Được tạo ở đâu | Được gửi/kiểm tra ở đâu | Mục đích chính |
|---|---|---|---|
| state | OIDC client | Gửi trong authorization request; so khớp ở callback | Liên kết response với browser transaction, giảm login CSRF và response injection |
| nonce | OIDC client | Gửi trong authorization request; so khớp claim nonce trong ID token | Liên kết ID token với authentication request, giảm replay ID token |
| PKCE code_verifier | OIDC client | Giữ bí mật ở client; gửi verifier tới token endpoint | Chứng minh bên đổi authorization code là client đã khởi tạo request |
| PKCE code_challenge | Tính từ verifier | Gửi trong authorization request; OP lưu để kiểm tra lúc đổi code | Ràng buộc authorization code với verifier |

### 3.1. State không thay nonce

State được trả về trong authorization response. Nonce nằm trong ID token dưới dạng claim và phải được đối chiếu với nonce đã lưu cho đúng transaction sau khi xác minh chữ ký và các claim token.

Một state hợp lệ không chứng minh ID token thuộc đúng authentication request. Nếu client gửi nonce, client phải xác minh nonce trong ID token theo OIDC.

Trong Authorization Code Flow thuần, OIDC Core cho phép nonce là tùy chọn ở một số cấu hình; các profile hoặc chính sách bảo mật của hệ thống có thể yêu cầu nonce. Hãy tuân thủ profile đang triển khai và luôn kiểm tra nonce nếu đã gửi.

### 3.2. State không thay PKCE

PKCE ràng buộc authorization code với code_verifier. Nếu attacker chặn được authorization code nhưng không có verifier tương ứng, token endpoint từ chối việc đổi code.

PKCE đặc biệt quan trọng với public client như SPA và ứng dụng mobile, nơi không thể giữ client secret. Dùng Authorization Code Flow với PKCE cho client hiện đại. State vẫn hữu ích để liên kết transaction và kiểm soát callback, dù PKCE có thể cung cấp một phần bảo vệ CSRF trong những triển khai đáp ứng đúng điều kiện.

### 3.3. Không gộp ba giá trị thành một

Không tái sử dụng state làm nonce hoặc PKCE verifier chỉ để giảm số biến. Mỗi giá trị có ngữ nghĩa, nơi lưu và quy tắc xác minh riêng. Một transaction có thể lưu cả ba cùng redirect context và thời điểm hết hạn, nhưng không nên dùng chúng thay thế nhau.

## 4. Sinh state an toàn

State cần khó đoán để attacker không thể tự tạo callback khớp với transaction đang chờ. Dùng bộ sinh số ngẫu nhiên mật mã (CSPRNG), không dùng timestamp, bộ đếm, Math.random() hoặc dữ liệu người dùng.

Trong browser:

```js
function createState() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);

  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }

  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

const state = createState();
```

Ví dụ tạo 32 byte ngẫu nhiên, tương đương 256 bit entropy trước khi mã hóa Base64URL. Server có thể dùng CSPRNG của nền tảng, ví dụ crypto.randomBytes(32) trong Node.js.

Các nguyên tắc:

- Sinh một state mới cho mỗi authorization request.
- Không tái sử dụng state giữa các lần đăng nhập hoặc giữa các user.
- So khớp chính xác giá trị nhận về; không so sánh prefix hoặc chỉ kiểm tra state có tồn tại.
- Giới hạn thời gian sống của transaction.
- Đánh dấu đã dùng hoặc xóa transaction ngay khi callback hợp lệ được chấp nhận.
- Không đưa PII, email, access token, refresh token hoặc client secret vào state.
- Không dùng state làm nơi chứa redirect URL tùy ý.

State không cần là JWT. Một chuỗi opaque ngẫu nhiên kết hợp với transaction lưu phía server thường đơn giản và dễ thu hồi hơn. Nếu thiết kế self-contained state, phải bảo vệ tính toàn vẹn bằng MAC/chữ ký hoặc mã hóa xác thực, có expiry và ràng buộc với browser session; không tin dữ liệu chỉ vì nó được Base64URL encode.

## 5. Lưu transaction trước khi redirect

Trước khi chuyển browser tới OP, client cần lưu state và các dữ liệu cần cho callback. Transaction có thể gồm:

| Trường | Mục đích |
|---|---|
| state | Khóa ngẫu nhiên để tìm transaction |
| createdAt / expiresAt | Giới hạn thời gian sống |
| browserSessionId | Ràng buộc transaction với browser session |
| issuer | OP dự kiến cho transaction |
| redirectUri | Redirect URI đã đăng ký và được chọn |
| codeVerifier | PKCE verifier, nếu dùng |
| nonce | Nonce đã gửi trong OIDC request, nếu dùng |
| returnTo | Route nội bộ đã kiểm tra allowlist để quay về sau đăng nhập |

Không cần gửi toàn bộ transaction cho browser. Với BFF, lưu transaction phía server và liên kết với session cookie. Browser chỉ mang session cookie và state đi qua redirect.

### 5.1. BFF hoặc server-rendered application

Mẫu thường dùng:

1. Browser gọi endpoint /login của ứng dụng.
2. Server tạo state ngẫu nhiên và transaction, lưu vào session store.
3. Server trả redirect tới authorization endpoint của OP, kèm state.
4. OP xác thực người dùng và redirect về callback cùng state.
5. Server đọc session cookie, tìm transaction theo state trong đúng session.
6. Server kiểm tra expiry, issuer/response và consume transaction một lần.
7. Chỉ sau khi state hợp lệ, server tiếp tục đổi code và xác minh ID token.

Transaction nên được lưu trong session store có tính nhất quán. Nếu hệ thống chạy nhiều instance, không lưu pending state trong memory riêng của một process vì callback có thể tới instance khác. Dùng shared session store hoặc cơ chế lưu transaction dùng chung có thao tác consume nguyên tử.

### 5.2. SPA

SPA cần giữ state qua lần điều hướng rời origin ứng dụng rồi quay lại. Một lựa chọn thường dùng là sessionStorage, lưu transaction theo state:

```js
function saveTransaction(state, transaction) {
  sessionStorage.setItem(
    'oidc.tx.' + state,
    JSON.stringify(transaction)
  );
}

function consumeTransaction(state) {
  const key = 'oidc.tx.' + state;
  const raw = sessionStorage.getItem(key);
  if (!raw) return null;

  sessionStorage.removeItem(key);
  return JSON.parse(raw);
}
```

sessionStorage thường được phân vùng theo tab và origin, phù hợp hơn một biến global khi có nhiều tab. Tuy nhiên, nó vẫn đọc được bởi JavaScript cùng origin; XSS có thể lấy state và các dữ liệu transaction lưu tại đó. Không lưu client secret hoặc token dài hạn trong transaction storage.

Nếu callback mở trong popup hoặc tab mới, cần thiết kế rõ transaction được chia sẻ thế nào. Không giả định sessionStorage của popup luôn giống tab mở nó; quan hệ opener và cách browser tạo browsing context có thể ảnh hưởng việc khởi tạo storage. Có thể dùng server-side transaction hoặc cơ chế message có kiểm tra origin và source.

### 5.3. Không dùng một state global cho mọi tab

Mẫu sau dễ gây lỗi:

```js
// Không phù hợp khi nhiều lần đăng nhập có thể chạy đồng thời.
sessionStorage.setItem('oidc_state', state);
```

Nếu người dùng mở hai tab đăng nhập gần nhau, tab thứ hai ghi đè state của tab thứ nhất. Khi callback quay về, transaction đầu tiên không còn khớp hoặc có thể bị ghép nhầm.

Dùng khóa riêng cho từng state hoặc map transaction phía server. Mỗi callback phải consume đúng transaction của nó.

## 6. Xử lý callback và xác minh state

Callback là ranh giới bảo mật quan trọng. Không xử lý authorization code trước khi kiểm tra state.

Quy trình:

1. Đọc state từ authorization response theo response mode đã cấu hình.
2. Tìm transaction đang chờ trong đúng browser session hoặc tab context.
3. So sánh chính xác state nhận về với khóa transaction.
4. Kiểm tra transaction chưa hết hạn và chưa được dùng.
5. Consume transaction theo thao tác nguyên tử để callback lặp không thể dùng lại.
6. Nếu response là error, xử lý lỗi sau khi state đã được xác minh.
7. Nếu response có code, tiếp tục đổi code bằng đúng redirect URI và PKCE verifier của transaction.
8. Xác minh ID token và các điều kiện OIDC trước khi tạo phiên đăng nhập.

Ví dụ logic server-side:

```js
async function handleOidcCallback(req, res) {
  const state = req.query.state;
  if (typeof state !== 'string' || state.length === 0) {
    return res.status(400).send('Missing state');
  }

  const transaction = await transactionStore.consume({
    sessionId: req.session.id,
    state,
  });

  if (!transaction || transaction.expiresAt <= Date.now()) {
    return res.status(400).send('Invalid or expired state');
  }

  if (req.query.error) {
    return handleAuthorizationError(req.query.error);
  }

  if (typeof req.query.code !== 'string') {
    return res.status(400).send('Missing authorization code');
  }

  return exchangeCodeAndValidateTokens({
    code: req.query.code,
    redirectUri: transaction.redirectUri,
    codeVerifier: transaction.codeVerifier,
    expectedNonce: transaction.nonce,
    expectedIssuer: transaction.issuer,
  });
}
```

Đây là pseudocode thể hiện thứ tự kiểm tra, không phải API framework hoàn chỉnh. transactionStore.consume() cần bảo đảm state được lấy và đánh dấu đã dùng trong một thao tác nguyên tử. Với request đồng thời hoặc callback replay, chỉ một request được nhận transaction.

### 6.1. Xác minh cả error response

OP có thể trả error=access_denied hoặc lỗi khác thay vì authorization code. Client vẫn phải xác minh state trước khi hiển thị lỗi hay hoàn tất transaction.

Nếu không kiểm tra state trong nhánh error, attacker có thể kích hoạt callback giả để làm hỏng hoặc kết thúc nhầm một transaction đăng nhập đang chờ.

### 6.2. State thiếu hoặc không hợp lệ

Khi state thiếu, không khớp, hết hạn hoặc đã được consume:

- Từ chối callback.
- Không đổi authorization code lấy token.
- Không tạo hoặc thay đổi phiên đăng nhập.
- Ghi nhận sự kiện ở mức an toàn, không ghi nguyên callback URL chứa code/state.
- Hiển thị thông báo chung như “Phiên đăng nhập không hợp lệ hoặc đã hết hạn”.
- Cho phép người dùng bắt đầu một authorization request mới.

Không tự động bỏ qua state để “cứu” trải nghiệm đăng nhập. Việc fallback sang xử lý code không có state làm mất cơ chế liên kết transaction.

## 7. Expiry, one-time use và replay

State nên có thời hạn ngắn, đủ cho người dùng hoàn tất thao tác đăng nhập nhưng không giữ transaction vô thời hạn. TTL cụ thể tùy UX, chính sách và thời gian xác thực của OP; không có một giá trị duy nhất phù hợp mọi hệ thống.

Các kiểm soát cần có:

- expiresAt được kiểm tra ở callback, không chỉ xóa bằng timer phía client.
- Transaction được consume ngay khi callback hợp lệ được chấp nhận.
- Callback lặp với cùng state phải thất bại.
- Dọn transaction hết hạn định kỳ ở server store.
- Giới hạn số transaction pending trong mỗi session để tránh lạm dụng tài nguyên.
- Với hệ thống phân tán, thao tác consume phải atomic/shared để hai instance không cùng chấp nhận một state.

Không chỉ xóa state sau khi token exchange thành công. Hãy consume trước khi xử lý code để hai callback song song không cùng sử dụng transaction. Nếu bước đổi code thất bại do mạng, người dùng có thể bắt đầu authorization request mới thay vì tái sử dụng state đã consume.

## 8. Nhiều tab, nhiều issuer và response mode

### 8.1. Nhiều tab đăng nhập đồng thời

Mỗi tab có thể bắt đầu một transaction riêng. Nếu dùng server session, lưu một tập transaction pending trong session, khóa theo state. Nếu dùng SPA, dùng khóa riêng trong sessionStorage hoặc transaction manager phù hợp.

Không dùng một cặp biến currentState/currentNonce toàn cục để đại diện mọi tab. Callback đến sau phải tìm đúng transaction dựa trên state nhận được.

### 8.2. Nhiều OpenID Provider

Nếu client hỗ trợ nhiều issuer, transaction cần ghi lại issuer dự kiến. Callback phải được ràng buộc với issuer đó; không chọn token endpoint dựa trên dữ liệu không tin cậy trong callback.

Để giảm authorization server mix-up, dùng redirect URI riêng cho từng issuer khi kiến trúc hỗ trợ hoặc xác minh tham số issuer trong authorization response theo profile/protocol đang triển khai. State không thay thế issuer validation.

### 8.3. response_mode query và form_post

Với response mode query, OP thường redirect browser bằng GET và state/code xuất hiện trong query string. Với form_post, browser gửi form POST tới callback và state/code nằm trong request body.

Khác biệt này ảnh hưởng cookie SameSite:

| Response mode | Request tới callback | Lưu ý session cookie |
|---|---|---|
| query | Top-level navigation GET | Cookie SameSite=Lax thường được gửi trong top-level safe navigation theo quy tắc browser |
| form_post | Cross-site POST | Cookie SameSite=Lax thường không được gửi cho cross-site POST; cần thiết kế session correlation và cookie policy phù hợp |

Không đổi cookie thành SameSite=None một cách máy móc. Nếu cần cross-site POST callback, phải đánh giá Secure, browser behavior, CSRF controls và cách ràng buộc transaction. SameSite=Strict có thể khiến session cookie không xuất hiện khi browser quay về từ OP.

## 9. Rò rỉ state và open redirect

State thường đi qua URL. Dù nó không phải access token, giá trị này vẫn có thể lộ qua:

- Access log của reverse proxy, web server hoặc CDN.
- Browser history và bản ghi điều hướng.
- Analytics, error reporting hoặc công cụ giám sát URL.
- Header Referer khi callback tải tài nguyên hoặc điều hướng sang trang khác.
- Screenshot, log debug hoặc URL được người dùng sao chép.

Giảm nguy cơ:

- Không ghi toàn bộ callback URL; redact code, state và các tham số xác thực.
- Đặt Cache-Control: no-store cho callback response.
- Đặt Referrer-Policy: no-referrer trên callback page.
- Không tải script, ảnh, font hoặc analytics bên thứ ba trên callback page trước khi xử lý xong.
- Sau khi xác minh và xử lý callback, điều hướng tới URL sạch không chứa code/state.
- Không đưa state hoặc authorization code vào telemetry.

### 9.1. Không nhúng return URL tùy ý vào state

Ứng dụng đôi khi muốn đưa người dùng về trang ban đầu sau đăng nhập. Không dùng state như:

```js
// Không an toàn: giá trị do client kiểm soát có thể thành open redirect.
const state = JSON.stringify({
  returnTo: new URLSearchParams(location.search).get('returnTo'),
});
```

Attacker có thể lợi dụng returnTo trỏ tới website ngoài hoặc URL nguy hiểm. Thay vào đó, lưu một route nội bộ đã allowlist trong transaction phía server:

```js
const allowedRoutes = new Set([
  '/dashboard',
  '/settings',
  '/orders',
]);

function safeReturnPath(candidate) {
  return allowedRoutes.has(candidate) ? candidate : '/dashboard';
}
```

State nên tiếp tục là giá trị ngẫu nhiên opaque. Dữ liệu điều hướng được lưu riêng và chỉ sử dụng sau khi callback được xác minh.

## 10. Các lỗi triển khai thường gặp

| Triệu chứng/lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Callback luôn báo state mismatch | State bị ghi đè bởi tab khác hoặc session cookie không trở lại | Lưu transaction theo từng state và kiểm tra cookie/SameSite/response mode |
| Đăng nhập thành công nhưng callback không tìm thấy state | SPA lưu trong memory rồi mất khi redirect | Dùng sessionStorage cùng tab hoặc server-side transaction |
| Callback bị chấp nhận dù state đã dùng | Không consume transaction hoặc chỉ kiểm tra state tồn tại | Consume nguyên tử và one-time use |
| State dễ đoán | Dùng timestamp, Math.random hoặc bộ đếm | Dùng CSPRNG với entropy đủ lớn |
| Login CSRF vẫn xảy ra | Không ràng buộc state với browser session | Lưu transaction trong đúng session/tab và kiểm tra callback |
| Hai tab nhận nhầm transaction | Dùng một state global | Dùng map theo state cho từng authorization request |
| Error callback làm mất transaction khác | Nhánh error không xác minh state hoặc xóa global state | Xác minh state trước khi xử lý cả success và error |
| Callback sau thời gian dài vẫn được chấp nhận | Không kiểm tra expiry ở server | Kiểm tra expiresAt và dọn pending transaction |
| State xuất hiện trong log | Ghi full URL hoặc request query | Redact code/state và giới hạn log callback |
| Login redirect sang website ngoài | Tin return URL nằm trong state | Lưu route allowlist riêng, không tin URL từ callback |
| Nhiều issuer bị trộn lẫn | Chọn token endpoint theo callback không được xác minh | Ràng buộc issuer với transaction và xác minh issuer response |

## 11. Thực hành: lab OIDC state với Node.js

Lab dùng Node.js built-in và một authorization endpoint giả trên cùng origin. Mục tiêu là kiểm tra state matching, tampering, expiry, replay và nhiều transaction trong cùng browser session.

Đây là lab mô phỏng cơ chế liên kết transaction. Nó **không phải OpenID Provider thật**: không xác thực người dùng, không phát ID token, không đổi authorization code và không triển khai PKCE. Trong hệ thống thật, OP nằm ở issuer riêng và client phải xác minh ID token cùng toàn bộ quy tắc OIDC.

### Bước 1 — Tạo file oidc-state-lab.cjs

```js
const http = require('node:http');
const { randomBytes } = require('node:crypto');

const sessions = new Map();
const SESSION_COOKIE = 'oidc_lab_session';
const STATE_TTL_MS = 5 * 60 * 1000;

function readCookies(req) {
  const result = {};
  for (const part of (req.headers.cookie || '').split(';')) {
    const index = part.indexOf('=');
    if (index < 0) continue;
    const name = part.slice(0, index).trim();
    const value = part.slice(index + 1).trim();
    result[name] = value;
  }
  return result;
}

function getOrCreateSession(req, res) {
  const cookies = readCookies(req);
  let id = cookies[SESSION_COOKIE];
  let session = id ? sessions.get(id) : null;

  if (!session) {
    id = randomBytes(32).toString('base64url');
    session = { pending: new Map() };
    sessions.set(id, session);
    // Lab dùng HTTP localhost nên cookie demo không có Secure.
    // Production phải dùng HTTPS và thêm thuộc tính Secure.
    res.setHeader(
      'Set-Cookie',
      SESSION_COOKIE + '=' + id + '; Path=/; HttpOnly; SameSite=Lax'
    );
  }

  return { id, session };
}

function htmlPage(title, body) {
  return '<!doctype html><html lang="vi"><head>' +
    '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<title>' + title + '</title></head><body>' +
    '<h1>' + title + '</h1>' + body + '</body></html>';
}

function sendHtml(res, status, html) {
  res.writeHead(status, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
  });
  res.end(html);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:3000');

  if (req.method !== 'GET') {
    res.writeHead(405, { 'Content-Type': 'text/plain; charset=utf-8' });
    return res.end('Method not allowed');
  }

  if (url.pathname === '/') {
    return sendHtml(res, 200, htmlPage('OIDC state lab', [
      '<p>Lab dùng state giả để minh họa correlation, tampering, expiry và replay.</p>',
      '<p><a href="/login">Bắt đầu authorization transaction mới</a></p>',
      '<p>Mở liên kết đăng nhập trong nhiều tab để tạo các state độc lập.</p>',
    ].join('')));
  }

  if (url.pathname === '/login') {
    const { session } = getOrCreateSession(req, res);
    const state = randomBytes(32).toString('base64url');
    session.pending.set(state, {
      createdAt: Date.now(),
      expiresAt: Date.now() + STATE_TTL_MS,
    });

    const location = '/mock-op?state=' + encodeURIComponent(state);
    res.writeHead(302, {
      Location: location,
      'Cache-Control': 'no-store',
      'Referrer-Policy': 'no-referrer',
    });
    return res.end();
  }

  if (url.pathname === '/mock-op') {
    const state = url.searchParams.get('state') || '';
    const encodedState = encodeURIComponent(state);
    const success = '/callback?code=demo-code&state=' + encodedState;
    const error = '/callback?error=access_denied&state=' + encodedState;
    const tampered = '/callback?code=demo-code&state=' +
      encodeURIComponent(state + 'tampered');

    return sendHtml(res, 200, htmlPage('Mock authorization endpoint', [
      '<p>Chọn response để thử callback. Endpoint này chỉ mô phỏng OP.</p>',
      '<ul>',
      '<li><a href="' + success + '">Trả code và state hợp lệ</a></li>',
      '<li><a href="' + tampered + '">Sửa state trước khi callback</a></li>',
      '<li><a href="' + error + '">Trả error=access_denied cùng state hợp lệ</a></li>',
      '</ul>',
      '<p><a href="/">Quay lại trang lab</a></p>',
    ].join('')));
  }

  if (url.pathname === '/callback') {
    const { session } = getOrCreateSession(req, res);
    const state = url.searchParams.get('state');

    if (!state) {
      return sendHtml(res, 400, htmlPage('Callback rejected', '<p>Missing state.</p>'));
    }

    const transaction = session.pending.get(state);
    if (!transaction) {
      return sendHtml(res, 400, htmlPage(
        'Callback rejected',
        '<p>Invalid, unknown, or already consumed state. No code was accepted.</p>'
      ));
    }

    if (transaction.expiresAt <= Date.now()) {
      session.pending.delete(state);
      return sendHtml(res, 400, htmlPage(
        'Callback rejected',
        '<p>State transaction expired. Start a new login.</p>'
      ));
    }

    // Consume trước khi xử lý code/error để callback replay không dùng lại được.
    session.pending.delete(state);

    const providerError = url.searchParams.get('error');
    if (providerError) {
      return sendHtml(res, 200, htmlPage(
        'Authorization canceled',
        '<p>State matched and transaction consumed. Provider returned an authorization error.</p>'
      ));
    }

    const code = url.searchParams.get('code');
    if (!code) {
      return sendHtml(res, 400, htmlPage(
        'Callback rejected',
        '<p>State matched but authorization code is missing.</p>'
      ));
    }

    return sendHtml(res, 200, htmlPage(
      'State accepted',
      '<p>State matched this browser session and was consumed once.</p>' +
      '<p>The mock code was not exchanged for tokens.</p>' +
      '<p><a href="/">Return to lab</a></p>'
    ));
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not found');
});

server.listen(3000, 'localhost', () => {
  console.log('Open http://localhost:3000');
});
```

### Bước 2 — Chạy lab

```sh
node oidc-state-lab.cjs
```

Mở http://localhost:3000. Nếu cổng 3000 đang được sử dụng, đổi cổng trong server và URL base dùng trong new URL().

Lab dùng cookie session HttpOnly; SameSite=Lax để ràng buộc pending state với browser session. Do chạy HTTP trên localhost, cookie demo bỏ Secure; production phải dùng HTTPS và thêm Secure.

### Bước 3 — Callback hợp lệ

1. Nhấn **Bắt đầu authorization transaction mới**.
2. Server tạo state ngẫu nhiên, lưu transaction trong session và redirect tới mock OP.
3. Chọn **Trả code và state hợp lệ**.
4. Callback tìm thấy state trong đúng session, kiểm tra expiry và consume transaction.
5. Trang hiển thị State accepted.

### Bước 4 — Tampering và replay

1. Bắt đầu một transaction mới.
2. Ở mock OP, chọn **Sửa state trước khi callback**.
3. Callback phải trả HTTP 400 vì state không khớp transaction đang chờ.
4. Quay lại mock OP của transaction hợp lệ và chọn success.
5. Sau khi state được chấp nhận, tải lại callback URL cũ. Lần thứ hai phải bị từ chối vì transaction đã consume.

### Bước 5 — Error response vẫn phải có state hợp lệ

1. Bắt đầu một transaction mới.
2. Chọn **Trả error=access_denied cùng state hợp lệ**.
3. Lab xác minh và consume state trước khi hiển thị thông báo người dùng từ chối.
4. Thử sửa state ở error callback bằng cách chỉnh URL; callback phải bị từ chối.

### Bước 6 — Nhiều transaction

Mở trang lab trong hai tab hoặc mở hai liên kết đăng nhập riêng. Mỗi lần /login tạo state mới và lưu một entry riêng trong cùng session. Hoàn tất callback theo thứ tự bất kỳ; mỗi state chỉ consume transaction của chính nó.

Để thử expiry nhanh, tạm đổi STATE_TTL_MS thành 1000, bắt đầu transaction rồi đợi hơn một giây trước khi callback. Khôi phục TTL năm phút sau khi kiểm tra.

Lab giữ session và transaction trong memory của một Node process, nên restart server sẽ xóa toàn bộ transaction. Đây là giới hạn có chủ đích của ví dụ local; production cần shared session/transaction store và consume nguyên tử.

## 12. Checklist triển khai OIDC state

- [ ] Mỗi authorization request có state ngẫu nhiên mới từ CSPRNG.
- [ ] State có entropy đủ lớn và không thể dự đoán.
- [ ] Transaction được lưu trước khi redirect tới OP.
- [ ] State được ràng buộc với browser session hoặc đúng tab context.
- [ ] Mỗi state có expiry và được kiểm tra ở callback.
- [ ] Callback so khớp state chính xác; thiếu hoặc sai state phải bị từ chối.
- [ ] State được consume một lần bằng thao tác atomic/shared.
- [ ] Cả success response và error response đều phải xác minh state.
- [ ] Callback không đổi code lấy token trước khi state hợp lệ.
- [ ] State, nonce và PKCE verifier được quản lý như các giá trị riêng.
- [ ] ID token được xác minh chữ ký, issuer, audience, expiry và nonce khi đã gửi.
- [ ] Issuer được ràng buộc với transaction để giảm mix-up.
- [ ] Nhiều tab dùng nhiều transaction, không ghi đè một state global.
- [ ] Return path được allowlist và lưu riêng, không tin URL trong state.
- [ ] Callback URL, code và state được redact khỏi log/analytics.
- [ ] Callback response dùng no-store và referrer policy phù hợp.
- [ ] Cookie SameSite được kiểm tra theo response mode query hoặc form_post.
- [ ] Hệ thống phân tán dùng store chung và consume có tính nguyên tử.
- [ ] Logout/expiry dọn transaction pending mà không ảnh hưởng transaction khác.

## 13. Câu hỏi tự kiểm tra

**1.** OIDC state được tạo ở thời điểm nào?  
**Trả lời:** Client tạo state mới trước khi redirect browser tới authorization endpoint và lưu transaction tương ứng.

**2.** OP phải làm gì với state?  
**Trả lời:** Trả lại nguyên giá trị state trong authorization response để client đối chiếu callback.

**3.** State giúp giảm loại tấn công nào?  
**Trả lời:** Login CSRF và unsolicited/forged authorization response bằng cách ràng buộc callback với transaction do browser đã khởi tạo.

**4.** State khác nonce thế nào?  
**Trả lời:** State được so khớp ở authorization response; nonce được so khớp với claim nonce trong ID token.

**5.** PKCE code_verifier bảo vệ điều gì?  
**Trả lời:** Chỉ client giữ verifier tương ứng mới đổi được authorization code đã gắn với code challenge.

**6.** Vì sao state phải khó đoán?  
**Trả lời:** Attacker không thể dễ dàng tạo callback có state trùng transaction đang chờ của nạn nhân.

**7.** Vì sao phải consume state một lần?  
**Trả lời:** Ngăn callback replay hoặc hai request đồng thời cùng dùng một transaction.

**8.** Error response có cần kiểm tra state không?  
**Trả lời:** Có. Phải xác minh state trước khi xử lý error để không cho callback giả kết thúc nhầm transaction.

**9.** Vì sao không nên dùng một biến state global cho mọi tab?  
**Trả lời:** Một lần đăng nhập có thể ghi đè state của lần khác; lưu transaction riêng theo state để xử lý callback đúng.

**10.** State có thay thế xác minh ID token không?  
**Trả lời:** Không. Client vẫn phải xác minh chữ ký, issuer, audience, expiry và nonce theo OIDC profile đang dùng.

## Tổng kết

OIDC state là giá trị ngẫu nhiên do client tạo cho từng authorization request và đối chiếu lại ở callback. Nó liên kết authorization response với transaction đã khởi tạo trong đúng browser session, giúp giảm login CSRF, callback injection và replay. Hãy lưu transaction theo từng state, ràng buộc với session/tab, đặt expiry, consume một lần và xác minh cả success lẫn error response trước khi xử lý code. State không thay nonce, PKCE, issuer validation hay việc xác minh ID token; callback và dữ liệu URL cũng cần được bảo vệ khỏi log, referrer và open redirect.
