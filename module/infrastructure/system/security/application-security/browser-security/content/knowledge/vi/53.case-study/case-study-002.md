# CSRF qua cookie

Cross-Site Request Forgery (CSRF) xảy ra khi một website hoặc ngữ cảnh khác khiến trình duyệt gửi request tới ứng dụng mà người dùng đang đăng nhập. Nếu ứng dụng dùng cookie để xác thực và browser tự động đính kèm cookie phù hợp, server có thể hiểu nhầm request do attacker khởi tạo là hành động hợp lệ của người dùng.

Điểm quan trọng của case study này là browser có thể gửi một request cross-site dù Same-Origin Policy ngăn trang khởi tạo đọc response. Vì vậy, việc “attacker không đọc được response” không chứng minh rằng thao tác đã bị ngăn. Ứng dụng phải xác minh ý định của request và quyền thực hiện ở server, đồng thời cấu hình cookie và browser policy như các lớp phòng vệ bổ sung.

Bài học thuộc module `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`, tập trung vào ranh giới giữa trình duyệt, origin, cookie và ứng dụng web. Tình huống dùng một ứng dụng ngân hàng giả lập để phân tích CSRF qua cookie, đánh giá SameSite, CSRF token, Origin/Referer, Fetch Metadata và cách kiểm chứng hành vi trong trình duyệt.

## Mục tiêu

Sau bài học, bạn có thể:

- Mô tả cách browser tự động gửi cookie trong request và cách CSRF khai thác hành vi này.
- Phân biệt origin với site, same-origin với same-site và hiểu tác động tới cookie SameSite.
- Tái hiện một lỗi CSRF bằng form cross-site trong lab có kiểm soát.
- Thiết kế CSRF token theo mô hình synchronizer token hoặc signed double-submit cookie.
- Kết hợp kiểm tra Origin/Referer, Fetch Metadata và cookie attributes.
- Phân biệt CSRF với CORS, XSS và lỗi authorization.
- Xây dựng ma trận kiểm thử, đánh giá tác động và xử lý sự cố CSRF.

## 1. Bối cảnh case study

Một ứng dụng ngân hàng giả lập tại `https://bank.example.test` cho phép người dùng đăng nhập và tạo lệnh chuyển tiền. Ứng dụng lưu session ID trong cookie:

```http
Set-Cookie: session=opaque-session-value; Path=/; Secure; HttpOnly
```

Người dùng đăng nhập hợp lệ, browser lưu cookie và tự động gửi cookie tới `bank.example.test` trong các request phù hợp. Endpoint chuyển tiền nhận dữ liệu từ form:

```http
POST /transfer
Cookie: session=opaque-session-value
Content-Type: application/x-www-form-urlencoded

recipient=attacker-account&amount=500
```

Server xác minh session nhưng không yêu cầu CSRF token, không kiểm tra nguồn request và không có lớp phòng vệ bổ sung. Một website khác tại `https://attacker.invalid` dụ người dùng đã đăng nhập mở trang. Trang đó gửi form tới endpoint chuyển tiền. Browser có thể đính kèm cookie phiên của ngân hàng theo chính sách cookie đang áp dụng.

Nếu server chỉ kiểm tra cookie và thực hiện chuyển tiền, thao tác có thể được chấp nhận dù người dùng không chủ ý tạo lệnh đó.

### Tài sản và ranh giới bị khai thác

| Thành phần | Vai trò | Rủi ro |
|---|---|---|
| Cookie phiên | Xác định phiên đăng nhập | Browser tự động gửi cookie theo request context |
| Endpoint `POST /transfer` | Tạo giao dịch | Chấp nhận request thiếu bằng chứng chống giả mạo |
| Trang attacker | Khởi tạo form hoặc request | Không cần đọc response để gây tác dụng phụ |
| Browser | Gửi request và quản lý cookie | Gửi cookie phù hợp với domain, path, Secure và SameSite |
| Same-Origin Policy | Hạn chế đọc dữ liệu cross-origin | Không ngăn mọi form hoặc request cross-site |
| Backend | Xác thực và xử lý giao dịch | Có thể nhầm cookie hợp lệ với ý định hợp lệ |

CSRF là lỗi kết hợp giữa cách browser gửi thông tin xác thực và cách server xử lý request. Cookie có thể hoàn toàn hợp lệ; vấn đề nằm ở việc server không xác minh request có được khởi tạo từ ứng dụng theo cách mong đợi hay không.

## 2. Luồng tấn công

### Trước khi người dùng truy cập trang attacker

Người dùng đăng nhập vào ngân hàng. Browser lưu cookie phiên cho host `bank.example.test`. Khi người dùng mở trang tài khoản, cookie được gửi tới server và session được xác thực.

### Khi người dùng mở trang attacker

Trang attacker có thể chứa form tự submit:

```html
<form
  action="https://bank.example.test/transfer"
  method="POST">
  <input name="recipient" value="attacker-account">
  <input name="amount" value="500">
</form>
<script>
  document.forms[0].submit();
</script>
```

Đây là ví dụ trong lab với dữ liệu giả lập. Khi trang được tải, browser có thể gửi POST tới ngân hàng. Việc cookie có được đính kèm hay không phụ thuộc SameSite, site context, chính sách cookie bên thứ ba, loại điều hướng và browser.

Nếu cookie được gửi, server nhận request trong session của người dùng. Trang attacker không cần đọc response. SOP có thể ngăn JavaScript ở attacker đọc DOM hoặc response của ngân hàng, nhưng không đảm bảo request không được gửi.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant A as Attacker site
    participant S as Bank server
    U->>B: Đăng nhập bank.example.test
    B->>S: POST /login
    S-->>B: Set-Cookie session
    U->>B: Mở attacker.invalid
    B->>A: GET trang attacker
    A-->>B: Form POST /transfer
    B->>S: POST /transfer + cookie nếu policy cho phép
    S->>S: Chỉ kiểm tra session, thiếu CSRF validation
    S-->>B: Thực hiện giao dịch
    Note over A,S: Attacker không cần đọc response để gây tác dụng phụ
~~~

### Vì sao SOP không đủ?

SOP chủ yếu giới hạn quyền đọc và tương tác với dữ liệu cross-origin. Một số request cross-origin vẫn được phép gửi, bao gồm navigation và form submission. Nếu server thực hiện hành động chỉ dựa trên cookie, browser có thể gửi thông tin xác thực trong một request mà người dùng không chủ ý tạo.

Cần phân biệt:

- **Request được gửi:** browser đã chuyển request tới server.
- **Cookie được đính kèm:** phụ thuộc cookie scope, SameSite và chính sách browser.
- **Response được đọc:** phụ thuộc SOP/CORS và loại request.
- **Tác dụng phụ được thực hiện:** phụ thuộc xác thực, authorization và CSRF validation phía server.

Bốn trạng thái này không đồng nghĩa với nhau. Một request có thể tới server, mang cookie và gây tác dụng phụ dù trang attacker không đọc được response.

## 3. Origin, site và SameSite trong tình huống CSRF

### Same-origin và same-site khác nhau

Origin gồm scheme, host và port. Site trong SameSite cookie được tính theo scheme và registrable domain theo quy tắc browser.

Ví dụ:

| Trang khởi tạo | Endpoint đích | Quan hệ | Ý nghĩa |
|---|---|---|---|
| `https://bank.example.test` | `https://bank.example.test/transfer` | Same-origin, same-site | Request cùng origin |
| `https://portal.example.test` | `https://bank.example.test/transfer` | Cross-origin nhưng thường same-site | Cookie SameSite có thể vẫn được gửi |
| `https://attacker.invalid` | `https://bank.example.test/transfer` | Cross-site | Cookie chịu quy tắc SameSite và third-party policy |
| `http://portal.example.test` | `https://bank.example.test/transfer` | Khác scheme và khác origin; khác schemeful site | SameSite có thể ngăn cookie |

Một subdomain bị kiểm soát bởi attacker, ví dụ `evil.example.test`, thường cùng site với `bank.example.test` khi cùng scheme, dù hai origin khác nhau. Do đó, SameSite không phải biện pháp bảo vệ đầy đủ trước một sibling subdomain bị xâm nhập hoặc không đáng tin cậy.

Cookie host-only giúp không gửi cookie tới host khác, nhưng không ngăn browser gửi cookie tới chính host ngân hàng khi request đích là `bank.example.test` và được khởi tạo từ sibling subdomain. Phạm vi cookie được xác định theo đích request; SameSite xét site context.

### SameSite=Strict

Cookie `SameSite=Strict` chỉ được gửi trong ngữ cảnh same-site theo quy tắc browser. Nó giảm nhiều request cross-site mang cookie, nhưng có thể ảnh hưởng luồng điều hướng từ website ngoài, SSO hoặc liên kết quay lại sau xác thực.

Strict vẫn không ngăn một sibling subdomain cùng site gửi request tới ứng dụng nếu các điều kiện khác cho phép. Không xem Strict là thay thế cho CSRF token.

### SameSite=Lax

Lax cho phép cookie trong một số ngữ cảnh điều hướng top-level an toàn, thường là GET. Cookie thường không được gửi trong form POST cross-site. Đây là lớp giảm thiểu hữu ích cho cookie phiên, nhưng có các giới hạn:

- GET không được tạo tác dụng phụ. Nếu `GET /transfer` thay đổi số dư, attacker có thể kích hoạt qua navigation.
- Request từ sibling subdomain cùng site có thể vẫn mang cookie.
- Một số browser có hành vi tương thích mặc định khi thuộc tính SameSite không được khai báo; không dựa vào mặc định ngầm.
- Các luồng SSO, redirect và callback cần được kiểm thử thực tế.

Hãy khai báo rõ SameSite và thiết kế endpoint đúng ngữ nghĩa HTTP.

### SameSite=None; Secure

Cookie `SameSite=None; Secure` đủ điều kiện được gửi trong một số ngữ cảnh cross-site nếu các điều kiện khác đáp ứng. Cấu hình này có thể cần cho một số tích hợp nhúng hoặc SSO, nhưng làm tăng yêu cầu về CSRF token và kiểm tra nguồn request. Browser có thể tiếp tục chặn cookie bên thứ ba theo chính sách riêng tư, kể cả khi cookie khai báo None.

Không đặt SameSite=None chỉ để khắc phục lỗi đăng nhập iframe mà chưa đánh giá luồng, threat model và fallback.

### Bảng so sánh

| Cấu hình | Cross-site top-level GET | Cross-site form POST | Sibling subdomain cùng site |
|---|---|---|---|
| Strict | Thường không gửi cookie | Không gửi cookie | Có thể gửi |
| Lax | Có thể gửi trong điều hướng top-level an toàn | Thường không gửi | Có thể gửi |
| None; Secure | Có thể gửi nếu browser cho phép third-party cookie | Có thể gửi nếu browser cho phép | Có thể gửi |
| Không khai báo | Phụ thuộc mặc định browser và phiên bản | Thường xử lý như Lax trong browser hiện đại, có thể có ngoại lệ tương thích | Có thể gửi |

Bảng này mô tả xu hướng chung, không thay thế kiểm thử trên browser mục tiêu. Chính sách third-party cookie, partitioning và các ngoại lệ tương thích có thể làm thay đổi kết quả.

## 4. Tái hiện lỗi trong lab

### Chuẩn bị fixture

Dùng hai site thử nghiệm do nhóm kiểm soát:

- `https://bank.example.test`: ứng dụng giả lập có login và endpoint transfer.
- `https://attacker.invalid`: trang gửi form cross-site.

Tạo tài khoản và số dư giả lập. Cookie phiên chỉ dùng trong lab. Dùng HTTPS với chứng chỉ được browser tin cậy để kiểm tra Secure cookie và SameSite.

### Endpoint dễ bị CSRF

Ví dụ minh họa một route chỉ kiểm tra session:

```js
app.post("/transfer", requireLogin, async (req, res) => {
  const { recipient, amount } = req.body;

  await createTransfer({
    userId: req.session.userId,
    recipient,
    amount: Number(amount)
  });

  res.status(200).send("Transfer accepted");
});
```

Route này thiếu CSRF validation. Trong ứng dụng thật, còn cần kiểm tra recipient, amount, giới hạn giao dịch, authorization và các điều kiện nghiệp vụ. Không dùng code này cho production.

### Kiểm chứng

1. Đăng nhập vào bank trong browser context lab.
2. Xác nhận cookie phiên tồn tại và thuộc host bank.
3. Mở trang attacker trong cùng browser context.
4. Gửi form POST tới endpoint transfer.
5. Kiểm tra Network xem request có được gửi và cookie có xuất hiện không.
6. Kiểm tra log server và trạng thái giao dịch giả lập.
7. Xác nhận trang attacker không đọc được response hoặc DOM bank theo SOP.

Nếu cookie không được gửi do SameSite hoặc browser chặn third-party cookie, test này chưa chứng minh endpoint đã chống CSRF. Tạm thời thay đổi cấu hình cookie trong lab để tái hiện request mang cookie; sau đó triển khai CSRF validation và kiểm tra lại. Chỉ thay đổi cookie trong fixture kiểm thử do nhóm kiểm soát.

### Dùng DevTools để phân tích

Trong Network panel, kiểm tra:

- Request URL, method và Content-Type.
- Initiator và frame tạo request.
- Request Cookie có session cookie hay không.
- Header Origin, Referer và Sec-Fetch-Site nếu browser gửi.
- Response status và redirect.
- Log server xác nhận session nào đã xử lý request.
- Trạng thái dữ liệu sau request.

Không dựa riêng vào Console. CORS error hoặc việc trang attacker không đọc được response không cho biết server có thực hiện tác dụng phụ hay không.

## 5. Phòng vệ chính: CSRF token

CSRF token là giá trị khó đoán do server tạo và liên kết với session hoặc ngữ cảnh xác thực. Ứng dụng yêu cầu client gửi token trong request thay đổi trạng thái. Trang attacker không thể đọc token từ trang đích do SOP, vì vậy không thể tạo request hợp lệ nếu token được kiểm tra đúng.

Token không thay thế xác thực hoặc authorization. Server vẫn phải xác minh session, quyền và dữ liệu nghiệp vụ.

### Synchronizer token pattern

Với ứng dụng server-rendered, mô hình phổ biến là:

1. Server tạo token ngẫu nhiên khi tạo session hoặc khi cần.
2. Server lưu token trong session phía server.
3. Server đưa token vào form hoặc response HTML.
4. Client gửi lại token trong hidden field hoặc custom header khi thực hiện thao tác thay đổi trạng thái.
5. Server so sánh token nhận được với token trong session.
6. Nếu thiếu hoặc sai token, server từ chối request.

Token phải khó đoán, gắn với session và không được đưa vào URL. Không log token hoặc chia sẻ nó qua referrer.

### Ví dụ tạo và kiểm tra token

Ví dụ dưới đây dùng Express session và Node.js crypto. Giả định middleware session đã được cấu hình và body parser được đặt trước route:

```js
import { randomBytes, timingSafeEqual } from "node:crypto";

function getCsrfToken(req) {
  if (!req.session.csrfToken) {
    req.session.csrfToken = randomBytes(32).toString("base64url");
  }
  return req.session.csrfToken;
}

function csrfTokenMatches(expected, supplied) {
  if (typeof expected !== "string" || typeof supplied !== "string") {
    return false;
  }

  if (!/^[A-Za-z0-9_-]{43}$/.test(supplied)) {
    return false;
  }

  const expectedBytes = Buffer.from(expected);
  const suppliedBytes = Buffer.from(supplied);

  if (expectedBytes.length !== suppliedBytes.length) {
    return false;
  }

  return timingSafeEqual(expectedBytes, suppliedBytes);
}

function requireCsrfToken(req, res, next) {
  const supplied =
    req.body?._csrf ?? req.get("X-CSRF-Token");

  if (!csrfTokenMatches(req.session?.csrfToken, supplied)) {
    return res.sendStatus(403);
  }

  next();
}
```

Token 32 byte được mã hóa Base64URL có 43 ký tự. Kiểm tra định dạng và độ dài trước khi dùng `timingSafeEqual` để tránh lỗi do hai buffer có độ dài khác nhau. Trong ứng dụng thực tế, dùng thư viện CSRF đã được duy trì nếu framework cung cấp giải pháp phù hợp; kiểm tra cách thư viện quản lý session, rotation và multi-tab.

### Đưa token vào form

Route GET tạo token và render form:

```js
app.get("/transfer", requireLogin, (req, res) => {
  res.render("transfer", {
    csrfToken: getCsrfToken(req)
  });
});
```

Template form:

```html
<form method="POST" action="/transfer">
  <input type="hidden" name="_csrf" value="<%= csrfToken %>">
  <label>
    Người nhận
    <input name="recipient" required>
  </label>
  <label>
    Số tiền
    <input name="amount" type="number" min="1" required>
  </label>
  <button type="submit">Xác nhận</button>
</form>
```

Ví dụ dùng cú pháp EJS `<%=` để escape giá trị. Template engine thực tế phải được cấu hình auto-escape đúng; không chèn token hoặc dữ liệu người dùng vào HTML thô.

Route POST kiểm tra token trước khi thực hiện tác dụng phụ:

```js
app.post(
  "/transfer",
  requireLogin,
  requireCsrfToken,
  async (req, res) => {
    const amount = Number(req.body.amount);

    if (!Number.isFinite(amount) || amount <= 0) {
      return res.sendStatus(400);
    }

    await createTransfer({
      userId: req.session.userId,
      recipient: req.body.recipient,
      amount
    });

    res.sendStatus(204);
  }
);
```

Kiểm tra CSRF phải xảy ra trước khi thực hiện thao tác. Kiểm tra số tiền, người nhận và quyền giao dịch vẫn cần thực hiện độc lập.

### CSRF token trong SPA

Với SPA, server có thể đưa token vào HTML ban đầu hoặc cung cấp qua endpoint cùng origin yêu cầu session hợp lệ. Client gửi token trong custom header:

```js
const csrfToken = document
  .querySelector('meta[name="csrf-token"]')
  ?.getAttribute("content");

await fetch("/api/profile/email", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken
  },
  body: JSON.stringify({ email: "new@example.test" })
});
```

Custom header khiến request cross-origin cần preflight trong nhiều trường hợp, nhưng không nên dùng preflight như lớp bảo vệ duy nhất. Server vẫn phải xác minh token. Nếu XSS chạy trong origin chính, script độc hại có thể đọc token và gửi request; CSRF token không thay thế phòng vệ XSS.

### Rotation và vòng đời token

Token nên được gắn với session. Khi đăng nhập, đổi quyền, nâng cấp privilege hoặc tái tạo session ID, hãy xoay token cùng với ranh giới xác thực. Không giữ token của session cũ sau khi session đã được regenerate.

Nếu token được tạo cho mỗi request, nhiều tab hoặc form mở đồng thời có thể gây lỗi khi token cũ bị vô hiệu hóa quá sớm. Cân nhắc token theo session hoặc tập token có thời hạn, tùy yêu cầu. Dù chọn cách nào, token phải được ràng buộc đúng session và không được chấp nhận lại ở session khác.

## 6. Các lớp phòng vệ bổ sung

### Cookie attributes

Cookie phiên nên có các thuộc tính phù hợp:

```http
Set-Cookie: __Host-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

- `Secure`: chỉ gửi cookie qua kết nối bảo mật theo quy tắc browser.
- `HttpOnly`: không cho JavaScript đọc cookie qua document.cookie.
- `SameSite=Lax`: giảm cookie trong nhiều request cross-site.
- `__Host-`: yêu cầu Secure, Path=/ và không có Domain trên browser hỗ trợ prefix.

Không khai báo Domain nếu ứng dụng không cần chia sẻ cookie với subdomain. Tuy nhiên, host-only cookie không tự ngăn CSRF từ sibling subdomain vì request đích vẫn là host đặt cookie.

### Kiểm tra Origin

Với request thay đổi trạng thái từ browser, header Origin thường cho biết origin khởi tạo request. Server có thể so sánh chính xác với allowlist:

```js
const APP_ORIGIN = "https://bank.example.test";

function hasTrustedOrigin(req) {
  const origin = req.get("Origin");
  return origin === APP_ORIGIN;
}
```

So sánh origin chính xác gồm scheme, host và port. Không dùng `includes`, `endsWith` hoặc regex không ràng buộc hostname. Những giá trị như `https://bank.example.test.attacker.invalid` không phải origin tin cậy. Giá trị `null` cũng không được tự động cho phép.

Một số request hoặc client có thể thiếu Origin. Với endpoint cookie-authenticated thay đổi trạng thái, có thể dùng Referer làm fallback bằng cách parse URL và so sánh `url.origin`. Nếu cả hai header đều thiếu, chính sách cho browser app nên từ chối request nhạy cảm hoặc yêu cầu cơ chế xác thực riêng. Không suy ra nguồn tin cậy từ Host hoặc X-Forwarded-Host nếu proxy chưa được cấu hình tin cậy.

Origin check là một lớp phòng vệ hữu ích, nhưng request từ non-browser client có thể tự đặt header. Nó không phải bằng chứng xác thực người dùng; session và authorization vẫn cần kiểm tra.

### Kiểm tra Referer

Referer có thể bị rút gọn hoặc không được gửi theo Referrer-Policy, privacy settings hay điều kiện điều hướng. Nếu dùng làm fallback:

1. Parse giá trị bằng URL API.
2. So sánh origin chính xác.
3. Từ chối URL không hợp lệ hoặc không có origin.
4. Không log toàn bộ path/query nếu có thể chứa dữ liệu nhạy cảm.

Không so khớp chuỗi Referer bằng prefix. Một URL bắt đầu bằng chuỗi trusted domain vẫn có thể trỏ tới host attacker.

### Fetch Metadata

Browser hiện đại có thể gửi các header như:

- `Sec-Fetch-Site`: `same-origin`, `same-site`, `cross-site` hoặc `none`.
- `Sec-Fetch-Mode`: loại chế độ request.
- `Sec-Fetch-Dest`: đích như document, image hoặc empty.

Với endpoint thay đổi trạng thái, có thể từ chối request có `Sec-Fetch-Site: cross-site` nếu nghiệp vụ không cần cross-site:

```js
function rejectCrossSiteUnsafeRequest(req, res, next) {
  const safeMethods = new Set(["GET", "HEAD", "OPTIONS"]);

  if (safeMethods.has(req.method)) return next();

  if (req.get("Sec-Fetch-Site") === "cross-site") {
    return res.sendStatus(403);
  }

  next();
}
```

Đây là lớp phòng vệ bổ sung. `same-site` không đồng nghĩa `same-origin`; một sibling subdomain không đáng tin cậy có thể được browser phân loại same-site. Vì vậy, vẫn cần token và Origin check. Với browser hoặc client không gửi Fetch Metadata, phải có cơ chế CSRF khác.

### CORS và custom header

CORS kiểm soát việc JavaScript cross-origin đọc response và trong một số trường hợp có thể ngăn request chính sau preflight thất bại. Nhưng form HTML và một số request đơn giản vẫn có thể gửi mà không cần preflight.

Nếu SPA dùng custom header như `X-CSRF-Token`, chỉ cho phép origin được duyệt trong CORS, không phản chiếu Origin tùy ý và không bật credentials cho mọi origin. Cấu hình CORS không thay thế việc xác minh token ở server.

## 7. Ví dụ middleware kết hợp nhiều lớp

Đoạn minh họa dưới đây kết hợp Origin/Referer, Fetch Metadata và synchronizer token. Nó giả định body parser, session middleware và xác thực đã chạy trước:

```js
const APP_ORIGIN = "https://bank.example.test";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function hasTrustedOriginOrReferer(req) {
  const origin = req.get("Origin");

  if (origin !== undefined) {
    return origin === APP_ORIGIN;
  }

  const referer = req.get("Referer");
  if (!referer) return false;

  try {
    return new URL(referer).origin === APP_ORIGIN;
  } catch {
    return false;
  }
}

function csrfGuard(req, res, next) {
  if (SAFE_METHODS.has(req.method)) return next();

  if (req.get("Sec-Fetch-Site") === "cross-site") {
    return res.sendStatus(403);
  }

  if (!hasTrustedOriginOrReferer(req)) {
    return res.sendStatus(403);
  }

  const supplied =
    req.body?._csrf ?? req.get("X-CSRF-Token");

  if (!csrfTokenMatches(req.session?.csrfToken, supplied)) {
    return res.sendStatus(403);
  }

  next();
}
```

Trong ứng dụng thực tế, cấu hình phương thức an toàn phải khớp với routing và semantics của API. Endpoint GET/HEAD không được thay đổi trạng thái. OPTIONS chỉ nên xử lý preflight và không thực hiện nghiệp vụ. Nếu ứng dụng cần request cross-site hợp lệ, thiết kế luồng riêng với xác thực và CSRF controls rõ ràng.

Không sao chép middleware này mà bỏ qua việc cấu hình session, token lifecycle, reverse proxy, logging và CORS. Dùng thư viện CSRF đã được duy trì khi phù hợp với framework và kiểm tra kỹ cấu hình.

## 8. Double-submit cookie pattern

Một kiến trúc khác là double-submit cookie: server đặt một token riêng trong cookie và yêu cầu client gửi cùng giá trị trong header hoặc body. Server so sánh hai giá trị. Vì attacker cross-site không đọc được cookie của target origin theo SOP, attacker thường không thể tự thêm giá trị đúng vào request.

Mẫu đơn giản chỉ so sánh cookie với body có thể gặp vấn đề nếu attacker kiểm soát được subdomain và có thể gây cookie injection hoặc cookie tossing. Để an toàn hơn:

- Dùng cookie host-only với prefix `__Host-` nếu phù hợp.
- Dùng token có chữ ký HMAC hoặc ràng buộc với session.
- Kiểm tra chữ ký và session binding phía server.
- Không cho phép subdomain không tin cậy đặt cookie Domain rộng.
- Xoay token khi session thay đổi.

Synchronizer token thường dễ hiểu hơn khi server có session state. Double-submit có thể phù hợp với một số kiến trúc stateless hoặc SPA, nhưng cần triển khai biến thể được thiết kế đúng; không dùng phép so sánh hai giá trị cookie/body một cách đơn giản mà không đánh giá cookie injection.

## 9. Các tình huống dễ bỏ sót

### GET làm thay đổi trạng thái

Nếu `GET /transfer?recipient=...` hoặc `GET /delete-account` thực hiện tác dụng phụ, attacker có thể kích hoạt bằng image, link hoặc navigation. Browser thường cho phép điều hướng GET cross-site và cookie Lax có thể được gửi trong một số ngữ cảnh top-level.

Mọi thao tác thay đổi trạng thái phải dùng method phù hợp như POST/PUT/PATCH/DELETE và có CSRF validation. GET chỉ nên đọc dữ liệu và không thay đổi trạng thái.

### Sibling subdomain bị xâm nhập

Một ứng dụng marketing tại `https://promo.example.test` có thể được triển khai độc lập hoặc dùng hệ thống CMS khác. Nếu subdomain này bị xâm nhập, attacker có thể gửi request tới `https://bank.example.test`. Hai origin khác nhau nhưng thường cùng site, nên SameSite không đủ để chặn.

Phòng vệ gồm token, Origin check chính xác, Fetch Metadata, tách host và không chia sẻ cookie Domain rộng nếu không cần.

### Login CSRF

CSRF không chỉ xảy ra sau khi người dùng đăng nhập. Attacker có thể khiến browser gửi request đăng nhập bằng tài khoản do attacker kiểm soát. Người dùng sau đó tiếp tục thao tác và vô tình đưa dữ liệu vào tài khoản attacker.

Luồng login cần chống request giả mạo, xoay session ID sau khi xác thực và bảo đảm người dùng biết tài khoản nào đang hoạt động. Logout và các thao tác thay đổi thông tin xác thực cũng cần được bảo vệ khỏi CSRF.

### CORS cấu hình quá rộng

Nếu server phản chiếu Origin tùy ý và cho phép credentials, trang attacker có thể đọc response chứa dữ liệu theo phiên trong những browser và điều kiện phù hợp. Đây là vấn đề CORS có thể làm tăng tác động, đồng thời không loại bỏ yêu cầu CSRF validation.

Allowlist phải so sánh origin đầy đủ. Khi response thay đổi theo Origin, cân nhắc `Vary: Origin` để cache không phục vụ nhầm response.

### XSS và CSRF token

Nếu XSS chạy trong origin ngân hàng, script có thể đọc token trong DOM hoặc gọi endpoint lấy token cùng origin. CSRF token không chống lại script đã chạy với quyền của ứng dụng. Cần phòng vệ XSS bằng output encoding, API DOM an toàn, CSP và Trusted Types phù hợp.

### Non-browser clients

Một client tự viết có thể giả mạo Origin, Referer hoặc Fetch Metadata. Các header này là tín hiệu về request context của browser, không phải danh tính người dùng. Endpoint vẫn phải xác thực session/token và authorization. Nếu API được dùng bởi mobile app hoặc service-to-service, thiết kế cơ chế xác thực riêng thay vì nới lỏng CSRF cho mọi request.

## 10. Kết quả điều tra và khắc phục case study

Giả sử nhóm bảo mật phát hiện endpoint transfer chấp nhận POST có cookie nhưng không có token. Nhóm tái hiện trong lab và xác nhận server thực hiện giao dịch giả lập.

| Giai đoạn | Bằng chứng | Kết luận |
|---|---|---|
| Xác minh session | Browser có cookie phiên hợp lệ | Người dùng đang đăng nhập |
| Tạo request từ attacker | Form cross-site POST tới endpoint | Attacker có thể khởi tạo request |
| Quan sát Network | Request tới server; cookie có thể được đính kèm tùy policy | SOP không ngăn request |
| Kiểm tra response | Attacker không đọc được response | Không loại bỏ tác dụng phụ |
| Kiểm tra backend | Chỉ kiểm tra session, không kiểm tra CSRF token | Request giả mạo được chấp nhận |
| Thêm CSRF token | Request thiếu hoặc sai token bị từ chối | Lớp kiểm soát chính hoạt động |
| Thêm Origin/Fetch Metadata | Request cross-site bị từ chối sớm | Defense in depth |
| Kiểm tra lại SameSite | Cookie Lax giảm một số cross-site POST | Cookie policy hỗ trợ, không thay thế token |

### Hành động khắc phục

1. Thêm synchronizer token cho mọi thao tác thay đổi trạng thái dùng cookie session.
2. Đổi cookie phiên sang `Secure; HttpOnly; SameSite=Lax` nếu luồng nghiệp vụ cho phép; cân nhắc prefix `__Host-`.
3. Kiểm tra Origin chính xác và Referer fallback theo chính sách.
4. Từ chối request unsafe có Fetch Metadata cross-site khi phù hợp.
5. Bảo đảm GET/HEAD không thực hiện tác dụng phụ.
6. Kiểm tra authorization và dữ liệu giao dịch ở server.
7. Rà soát CORS allowlist, không phản chiếu Origin tùy ý.
8. Thêm test hồi quy cho browser, sibling subdomain và luồng đăng nhập.
9. Theo dõi lỗi 403 CSRF và các dấu hiệu request bất thường mà không log token/cookie.
10. Xoay session ID và CSRF token tại ranh giới đăng nhập hoặc thay đổi privilege.

### Xác minh sau khắc phục

- Request hợp lệ từ trang bank có token đúng được chấp nhận.
- Request thiếu token hoặc token sai bị từ chối.
- Token từ session khác không được chấp nhận.
- Request cross-site không có token không tạo tác dụng phụ.
- Request same-site từ sibling subdomain vẫn bị kiểm tra token và Origin.
- Cookie được gửi đúng theo SameSite và chính sách browser.
- Luồng SSO/redirect hợp lệ vẫn hoạt động theo thiết kế.
- GET không thay đổi trạng thái.
- Người dùng không bị mất dữ liệu khi request bị từ chối.

Không kết luận đã khắc phục chỉ vì browser không gửi cookie trong một cấu hình. Phải chứng minh server từ chối request giả mạo ngay cả khi request có session cookie hợp lệ.

## 11. Ma trận kiểm thử CSRF qua cookie

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| CSRF-01 | POST cùng origin, token đúng | Được chấp nhận nếu authorization hợp lệ |
| CSRF-02 | POST cross-site thiếu token | Bị từ chối |
| CSRF-03 | POST token sai | Bị từ chối |
| CSRF-04 | Token thuộc session khác | Bị từ chối |
| CSRF-05 | Token bị phát lại sau khi session rotate | Bị từ chối |
| CSRF-06 | Form cross-site với SameSite=Lax | Cookie thường không được gửi trong POST cross-site; server vẫn cần token |
| CSRF-07 | Top-level GET cross-site | Không được tạo tác dụng phụ |
| CSRF-08 | Request từ sibling subdomain cùng site | Origin/token validation phải ngăn request giả mạo |
| CSRF-09 | Origin không nằm trong allowlist | Bị từ chối |
| CSRF-10 | Origin là null hoặc malformed | Bị từ chối theo chính sách |
| CSRF-11 | Thiếu Origin và Referer trên thao tác nhạy cảm | Bị từ chối hoặc đi qua cơ chế riêng được thiết kế rõ |
| CSRF-12 | Fetch Metadata là cross-site | Bị từ chối với request unsafe nếu policy áp dụng |
| CSRF-13 | Cookie HttpOnly | JavaScript không đọc được cookie |
| CSRF-14 | Cookie Secure qua HTTP | Không được gửi theo quy tắc Secure |
| CSRF-15 | SameSite=None; Secure trong browser chặn third-party cookie | Ứng dụng xử lý luồng thiếu cookie an toàn |
| CSRF-16 | Login CSRF | Session không bị gắn vào tài khoản attacker ngoài ý muốn |
| CSRF-17 | CORS allowlist | Chỉ origin hợp lệ đọc response; CSRF token vẫn được xác minh |
| CSRF-18 | XSS trong origin chính | Đánh giá riêng vì XSS có thể đọc token và vượt lớp CSRF |

Chạy ma trận trên Chromium, Firefox và WebKit, đồng thời kiểm tra Safari thực tế nếu sản phẩm hỗ trợ. Ghi lại browser/version, cookie attributes, origin nguồn/đích, request method, request headers, token state, kết quả server và trạng thái dữ liệu.

## 12. Giám sát và xử lý sự cố

### Log cần có

Có thể ghi nhận các trường sau:

- Route và method.
- Kết quả CSRF validation: pass/fail và lý do tổng quát.
- Origin đã chuẩn hóa hoặc nhãn origin category.
- Fetch Metadata nếu có.
- Browser family/version ở mức cần thiết.
- Request ID và session correlation ID đã giả danh hóa.
- Thời điểm, release và kết quả nghiệp vụ.

Không ghi giá trị cookie, CSRF token, Authorization header hoặc body nhạy cảm. Không đưa toàn bộ Referer/query vào log nếu có thể chứa dữ liệu cá nhân.

### Phát hiện bất thường

Theo dõi:

- Tỷ lệ CSRF rejection tăng đột biến.
- Nhiều request thay đổi trạng thái từ origin không mong đợi.
- Request thiếu token trên route nhạy cảm.
- Request có token không hợp lệ hoặc token thuộc session khác.
- Giao dịch được tạo từ route không có tương tác UI tương ứng.
- Sai khác theo browser hoặc release sau khi đổi cookie policy.

Một đợt 403 có thể do frontend không gửi token sau deploy hoặc session rotation bị lỗi. Cần so sánh release, route, browser và request context trước khi kết luận có tấn công.

### Khi xác nhận có khai thác

1. Xác định endpoint và loại tác dụng phụ.
2. Xác định khoảng thời gian, session bị ảnh hưởng và dữ liệu đã thay đổi.
3. Chặn hoặc yêu cầu CSRF validation cho route dễ bị khai thác.
4. Thu hồi hoặc xoay session nếu có dấu hiệu lạm dụng phiên.
5. Đối soát giao dịch và khôi phục dữ liệu theo quy trình nghiệp vụ.
6. Giữ bằng chứng đã giảm thiểu dữ liệu; không lưu cookie/token thô.
7. Thêm regression test và theo dõi sau triển khai.

CSRF thường không làm lộ response cho attacker. Vì vậy, log server và lịch sử tác dụng phụ có thể quan trọng hơn dữ liệu phía client khi điều tra.

## 13. Thực hành

Dùng lab bank và attacker do nhóm kiểm soát. Tạo tài khoản, cookie và giao dịch giả lập. Không chạy form thử nghiệm trên website thật.

### Phần A: Tái hiện lỗi

1. Cấu hình endpoint POST chỉ kiểm tra session.
2. Đăng nhập và xác nhận cookie được lưu.
3. Tạo form auto-submit trên attacker origin.
4. Gửi request và quan sát Network, cookie và log server.
5. Ghi nhận liệu giao dịch giả lập có được tạo hay không.

### Phần B: Thử nghiệm SameSite

Lặp lại với cookie `Strict`, `Lax` và `None; Secure`. Kiểm tra form POST cross-site, top-level GET và request từ sibling subdomain cùng site. Ghi lại browser và version vì chính sách có thể khác nhau.

### Phần C: Bổ sung phòng vệ

1. Thêm synchronizer token gắn với session.
2. Thêm Origin validation với exact allowlist.
3. Thêm Fetch Metadata check cho request unsafe.
4. Đặt cookie Secure, HttpOnly và SameSite phù hợp.
5. Chuyển mọi thao tác thay đổi trạng thái khỏi GET.
6. Kiểm tra authorization và dữ liệu ở server.

### Phần D: Chạy regression test

Chạy các ca CSRF-01 tới CSRF-18. Đảm bảo request hợp lệ vẫn hoạt động và request giả mạo bị từ chối. Thử session rotation, nhiều tab, thiếu header và browser không hỗ trợ Fetch Metadata.

Hoàn thiện bảng kết quả:

| Trường | Giá trị |
|---|---|
| Browser/engine/version | |
| Origin nguồn | |
| Origin đích | |
| Cookie attributes | |
| Method và Content-Type | |
| Origin/Referer/Fetch Metadata | |
| CSRF token state | |
| Kết quả server | |
| Tác dụng phụ có xảy ra không | |
| Bằng chứng | |
| Kết luận | |

Cuối cùng, xóa tài khoản, cookie và dữ liệu giao dịch giả lập khỏi lab.

## 14. Ghi nhớ

- CSRF khai thác việc browser tự động gửi cookie xác thực trong request mà người dùng không chủ ý khởi tạo.
- SOP ngăn nhiều thao tác đọc cross-origin nhưng không chặn mọi request form hoặc navigation.
- Không đọc được response không có nghĩa server chưa nhận request hoặc chưa thực hiện tác dụng phụ.
- SameSite dựa trên site context, không phải origin; sibling subdomain có thể cùng site nhưng khác origin.
- SameSite=Lax giảm nhiều cross-site POST nhưng không bảo vệ mọi tình huống; GET không được thay đổi trạng thái.
- CSRF token phải khó đoán, gắn với session, được kiểm tra phía server và không đặt trong URL.
- Origin/Referer và Fetch Metadata là lớp phòng vệ bổ sung; so sánh origin chính xác và không xem chúng là xác thực.
- CORS không thay thế CSRF validation; form đơn giản vẫn có thể gửi request.
- Cookie Secure, HttpOnly, SameSite và prefix __Host- giảm rủi ro theo các cách khác nhau.
- XSS trong origin chính có thể đọc CSRF token; phòng vệ XSS vẫn cần thiết.
- Kiểm thử phải chứng minh server từ chối request giả mạo ngay cả khi browser gửi kèm session cookie.
