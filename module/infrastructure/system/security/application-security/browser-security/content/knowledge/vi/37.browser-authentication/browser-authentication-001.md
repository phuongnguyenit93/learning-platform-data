# Browser authentication

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích trình duyệt tham gia vào quá trình xác thực như thế nào và phân biệt authentication với authorization.
- So sánh session cookie, HTTP authentication, bearer token, OAuth 2.0/OpenID Connect và passkey/WebAuthn.
- Chọn cách giữ trạng thái đăng nhập phù hợp với kiến trúc website, SPA hoặc Backend for Frontend (BFF).
- Bảo vệ luồng đăng nhập, callback, refresh, logout và các request sử dụng credential.
- Nhận diện tác động của XSS, CSRF, CORS, SameSite và chính sách cookie bên thứ ba đến xác thực.
- Kiểm thử trạng thái xác thực bằng DevTools và xây dựng checklist bảo mật cho ứng dụng web.

## 1. Browser authentication là gì?

Browser authentication là quá trình ứng dụng web xác minh người đang sử dụng trình duyệt là ai và duy trì trạng thái đã đăng nhập qua các request hoặc lần điều hướng. Trình duyệt cung cấp giao diện nhập thông tin, quản lý cookie, lưu một số credential, thực hiện WebAuthn và gửi request đến máy chủ. Quyết định xác thực cuối cùng phải được kiểm tra ở thành phần server có thẩm quyền.

Một trang web có thể hiển thị tên người dùng hoặc ẩn nút đăng nhập, nhưng những thay đổi giao diện đó không chứng minh request tiếp theo được phép. Người dùng có thể sửa JavaScript, gọi API trực tiếp hoặc thay đổi dữ liệu trong trình duyệt. Server phải kiểm tra credential và trạng thái session trên mọi request cần bảo vệ.

Hai khái niệm cần phân biệt:

- **Authentication (xác thực):** xác minh danh tính của người dùng hoặc client. Ví dụ: người đăng nhập chứng minh quyền kiểm soát tài khoản bằng mật khẩu và passkey.
- **Authorization (ủy quyền):** quyết định danh tính đó được phép thực hiện hành động nào trên tài nguyên nào. Ví dụ: người dùng đã đăng nhập chỉ được xem hồ sơ của chính họ hoặc các tài liệu thuộc tenant của họ.

Đăng nhập thành công không đồng nghĩa có quyền quản trị. Một session hợp lệ chỉ xác nhận danh tính và trạng thái phiên; mỗi API vẫn cần kiểm tra quyền theo resource, action và tenant.

## 2. Các thành phần trong mô hình xác thực

Một ứng dụng web thường có các thành phần sau:

| Thành phần | Vai trò |
| --- | --- |
| Browser UI | Thu thập thông tin đăng nhập, hiển thị trạng thái và khởi tạo thao tác xác thực. |
| Browser credential store | Có thể lưu password đã lưu, passkey hoặc thông tin đăng nhập do người dùng cho phép trình duyệt quản lý. |
| Frontend JavaScript | Gọi endpoint đăng nhập, xử lý callback, cập nhật giao diện và gọi API. Code này chạy trong origin của ứng dụng nên có thể bị ảnh hưởng bởi XSS. |
| Authentication server / Identity Provider (IdP) | Xác minh password, passkey, MFA hoặc credential liên kết; phát hành kết quả xác thực. |
| Session/token service | Duy trì session hoặc phát hành/kiểm tra token. |
| Application API | Xác minh session/token và kiểm tra quyền trước khi trả dữ liệu hoặc thực hiện thay đổi. |

Luồng tổng quát:

```mermaid
sequenceDiagram
  participant U as User
  participant B as Browser
  participant A as Auth server / IdP
  participant API as Application API
  U->>B: Nhập credential hoặc dùng passkey
  B->>A: Gửi yêu cầu xác thực
  A->>A: Xác minh credential và chính sách
  A-->>B: Kết quả đăng nhập / authorization code
  B->>A: Hoàn tất callback hoặc tạo session
  A-->>B: Session cookie hoặc kết quả token
  B->>API: Request kèm credential
  API->>API: Xác minh session/token và quyền
  API-->>B: Dữ liệu được phép truy cập
```

Đây là sơ đồ khái quát. Trong kiến trúc BFF, trình duyệt thường chỉ nhận session cookie của ứng dụng; BFF giữ access token/refresh token ở phía server. Trong SPA thuần, JavaScript có thể trực tiếp nhận access token và gửi nó trong `Authorization` header. Hai cách có bề mặt tấn công và yêu cầu vận hành khác nhau.

## 3. Session cookie: mô hình phổ biến cho website

### 3.1. Session hoạt động như thế nào?

Trong mô hình session truyền thống, server tạo một session ngẫu nhiên sau khi xác thực thành công. Trình duyệt giữ session identifier trong cookie và gửi cookie trong các request phù hợp. Server dùng identifier đó để tra cứu trạng thái session ở kho lưu trữ phía server.

Ví dụ response đăng nhập:

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Content-Type: application/json
```

Giá trị cookie nên là một identifier ngẫu nhiên khó đoán, không chứa trực tiếp password, role, dữ liệu cá nhân hoặc thông tin session có thể giải mã mà không cần server. Server giữ thông tin như user ID, thời điểm tạo, thời điểm hết hạn, trạng thái thu hồi và các thuộc tính cần thiết.

Khi browser gọi API cùng origin, cookie được gửi theo quy tắc cookie. Server tra cứu session, kiểm tra session còn hiệu lực, rồi xác định principal để áp dụng authorization.

### 3.2. Thuộc tính cookie bảo mật

| Thuộc tính | Tác dụng |
| --- | --- |
| `Secure` | Chỉ gửi cookie qua kết nối an toàn như HTTPS. Production nên dùng HTTPS cho toàn bộ site. |
| `HttpOnly` | Ngăn JavaScript đọc cookie qua `document.cookie`. XSS vẫn có thể gửi request cùng origin bằng cookie tự động được đính kèm, nhưng không thể đọc trực tiếp giá trị cookie này. |
| `SameSite=Strict` | Hạn chế gửi cookie trong các ngữ cảnh cross-site; có thể ảnh hưởng một số luồng điều hướng từ website ngoài. |
| `SameSite=Lax` | Cho phép cookie trong một số điều hướng top-level an toàn, đồng thời hạn chế nhiều request cross-site khác. Đây là lựa chọn thường gặp cho session cookie. |
| `SameSite=None` | Cho phép gửi trong ngữ cảnh cross-site nếu cookie có `Secure`; vẫn chịu chính sách chặn/phân vùng cookie bên thứ ba của trình duyệt. |
| `Path` | Giới hạn đường dẫn request được gửi cookie. `Path` không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng host. |
| `Domain` | Mở rộng phạm vi cookie đến domain và các subdomain phù hợp. Bỏ `Domain` để tạo host-only cookie nếu không cần chia sẻ. |
| `Max-Age` / `Expires` | Xác định thời hạn cookie ở browser. Session phía server vẫn cần thời hạn và quy tắc thu hồi riêng. |

Với session cookie của ứng dụng chỉ chạy trên một host, có thể dùng tiền tố `__Host-`:

```http
Set-Cookie: __Host-session=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie `__Host-` phải được đặt từ secure origin, có `Path=/` và không được có thuộc tính `Domain`. Quy tắc này giúp ngăn subdomain tạo cookie cùng tên có phạm vi rộng hơn. Nếu ứng dụng cần cookie dùng chung nhiều subdomain, phải chọn thiết kế khác và đánh giá rủi ro của phạm vi domain rộng.

### 3.3. Quản lý vòng đời session

Server cần quản lý session theo các quy tắc rõ ràng:

- Tạo session ID mới sau khi đăng nhập thành công; không nâng cấp một session ID do người dùng kiểm soát từ trạng thái anonymous sang authenticated.
- Xoay session ID sau khi đăng nhập, đổi mật khẩu hoặc thay đổi mức đặc quyền quan trọng để giảm session fixation.
- Áp dụng cả idle timeout và absolute lifetime theo mức độ nhạy cảm của ứng dụng.
- Thu hồi session khi logout, reset mật khẩu, phát hiện rủi ro hoặc quản trị viên khóa tài khoản theo chính sách.
- Giới hạn số session đồng thời nếu nghiệp vụ yêu cầu và cung cấp cách xem/thu hồi thiết bị đã đăng nhập.
- Không ghi session ID hoặc cookie nguyên vẹn vào log, analytics hay báo cáo lỗi.

Xóa cookie trên browser không tự thu hồi session ở server. Ngược lại, thu hồi session ở server khiến cookie cũ không còn hợp lệ dù cookie vẫn tồn tại trong trình duyệt. Logout cần thực hiện cả hai phần.

### 3.4. Password login và biểu mẫu đăng nhập

Biểu mẫu đăng nhập nên gửi password qua HTTPS bằng phương thức POST. Dùng autocomplete semantic để password manager và trình duyệt nhận biết đúng trường:

```html
<form method="post" action="/login">
  <label for="username">Email hoặc tên đăng nhập</label>
  <input
    id="username"
    name="username"
    type="text"
    autocomplete="username"
    required
  >

  <label for="password">Mật khẩu</label>
  <input
    id="password"
    name="password"
    type="password"
    autocomplete="current-password"
    required
  >

  <button type="submit">Đăng nhập</button>
</form>
```

Với biểu mẫu đổi hoặc tạo password mới, dùng `autocomplete="new-password"`. Không vô hiệu hóa password manager hoặc paste chỉ để ép người dùng nhập thủ công; các biện pháp đó thường làm giảm khả năng dùng password mạnh và unique.

Server phải xử lý password an toàn: lưu password dưới dạng hash chậm chuyên dụng như Argon2id (hoặc thuật toán phù hợp theo nền tảng), dùng salt riêng cho từng password và cấu hình chi phí phù hợp. Không mã hóa reversible hoặc lưu plaintext. Không ghi password vào log, trace, analytics hay thông báo lỗi. Áp dụng rate limit và phát hiện credential stuffing; thông báo lỗi đăng nhập nên tránh tiết lộ tài khoản có tồn tại hay không. Quy trình reset password cần token ngẫu nhiên, thời hạn ngắn, dùng một lần và thu hồi các session theo policy sau khi reset. Biểu mẫu đăng nhập cũng cần được đánh giá login CSRF: attacker có thể khiến nạn nhân đăng nhập vào tài khoản do attacker kiểm soát, làm nạn nhân vô tình nhập dữ liệu vào tài khoản đó. Dùng token giao dịch/pre-auth session và kiểm tra `Origin` hoặc Fetch Metadata theo policy phù hợp.

Trình duyệt có thể lưu và tự điền password, nhưng việc tự điền không thay thế xác thực ở server. Ứng dụng cũng không nên tự đọc password đã lưu từ password manager hoặc đưa password vào Web Storage để duy trì trạng thái đăng nhập.

### 3.5. Cookie và Fetch credentials mode

Fetch API có thuộc tính `credentials` điều khiển việc gửi credential như cookie trong request và xử lý `Set-Cookie` ở response:

| Giá trị | Hành vi |
| --- | --- |
| `omit` | Không gửi credential và không xử lý credential từ response theo request này. |
| `same-origin` | Chỉ gửi credential cho request cùng origin. Đây là mặc định của Fetch API. |
| `include` | Cho phép gửi credential cả khi request cross-origin; cookie vẫn chịu `SameSite`, Secure, third-party cookie blocking và storage partitioning. |

Ví dụ request cross-origin có cookie:

```js
const response = await fetch("https://api.example.net/me", {
  credentials: "include"
});
```

API phải cấu hình CORS với `Access-Control-Allow-Credentials: true` và `Access-Control-Allow-Origin` là origin cụ thể; không thể dùng wildcard `*` cho response có credential. Với XHR, cơ chế tương ứng là `withCredentials = true`. Những cấu hình này chỉ điều khiển credential và quyền đọc response của browser; server vẫn cần xác minh session, authorization và CSRF.

## 4. HTTP authentication

HTTP định nghĩa các cơ chế xác thực như Basic và Digest. Với HTTP Basic, server trả challenge `WWW-Authenticate`; browser có thể hiển thị hộp thoại yêu cầu username/password và gửi credential trong header `Authorization` ở request tiếp theo.

Ví dụ challenge:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Internal tools"
```

Request sau đó có dạng:

```http
GET /reports HTTP/1.1
Authorization: Basic dXNlcjpwYXNzd29yZA==
```

Giá trị Basic chỉ là Base64 của chuỗi `username:password`, không phải mã hóa. Phải dùng HTTPS để bảo vệ credential trên đường truyền. Basic authentication còn có nhược điểm về trải nghiệm đăng xuất, quản lý credential và tích hợp MFA; không nên tự xem nó là session management hoàn chỉnh.

Digest authentication tránh gửi password dạng Basic nhưng có giới hạn tương thích và không thay thế các hệ thống xác thực hiện đại. Với ứng dụng web mới, session cookie, OIDC hoặc passkey thường phù hợp hơn. Không triển khai cơ chế HTTP authentication mà không đánh giá hành vi cache credential và khả năng logout của browser mục tiêu.

## 5. Token-based authentication

### 5.1. Bearer token

Với bearer token, ai sở hữu token có thể sử dụng token theo quyền và thời hạn được cấp. SPA có thể gửi access token qua header:

```js
const response = await fetch("https://api.example.com/me", {
  headers: {
    Authorization: `Bearer ${accessToken}`
  }
});
```

Server phải xác minh chữ ký hoặc tra cứu token theo cơ chế đã chọn, kiểm tra issuer/audience, thời hạn, scope/permission và trạng thái thu hồi nếu hệ thống hỗ trợ. Không chấp nhận token chỉ vì payload trông giống JSON hợp lệ.

Với request cross-origin, `Authorization` là header không thuộc nhóm CORS-safelisted. Browser thường gửi preflight `OPTIONS`; API cần cho phép origin và header phù hợp qua CORS. CORS chỉ quyết định JavaScript có được đọc response hay không, không thay thế xác thực token hoặc authorization.

### 5.2. JWT không phải dữ liệu bí mật

JWT thường có dạng ba phần được mã hóa Base64URL: header, payload và signature. Trong JWT ký số phổ biến, payload có thể được đọc bởi người sở hữu token. Không đặt password, secret hoặc dữ liệu cá nhân không cần thiết vào claim. Chữ ký giúp phát hiện token bị sửa; nó không mã hóa payload.

Khi xác minh JWT, server cần kiểm tra thuật toán được phép, chữ ký, `iss`, `aud`, `exp`, `nbf` nếu có, và các claim cần thiết theo policy. Không chọn thuật toán dựa trên giá trị do token không tin cậy cung cấp mà không có allowlist. Với JWT chứa quyền, cần tính đến thời gian quyền bị thu hồi và thời hạn token; token tự chứa thường khó thu hồi tức thời nếu không có denylist, introspection hoặc thời hạn ngắn.

### 5.3. Lưu token ở đâu?

Không có vị trí lưu token nào miễn nhiễm với XSS. Cần chọn kiến trúc dựa trên khả năng và hậu quả khi JavaScript của origin bị thực thi trái phép.

| Cách lưu | Đặc điểm và rủi ro |
| --- | --- |
| JavaScript memory | Token biến mất khi context bị hủy/reload, giảm thời gian tồn tại lâu dài. XSS đang chạy vẫn có thể đọc token hoặc gọi API thay người dùng. |
| `localStorage` | Dễ dùng và tồn tại qua lần tải lại, nhưng mọi JavaScript cùng origin có thể đọc; token có thể tồn tại lâu trên thiết bị dùng chung. Không nên lưu refresh token dài hạn ở đây. |
| `sessionStorage` | Thường gắn với tab/browsing context và bị xóa khi context kết thúc; JavaScript cùng origin vẫn đọc được. Không bảo vệ khỏi XSS. |
| IndexedDB | Hỗ trợ dữ liệu có cấu trúc và bất đồng bộ, nhưng cùng origin JavaScript có thể truy cập; không phải kho bí mật chống XSS. |
| HttpOnly cookie | JavaScript không đọc được giá trị cookie, nhưng browser tự gửi cookie theo phạm vi và chính sách. Cần chống CSRF và quản lý session phía server. |
| BFF giữ token phía server | Browser giữ session cookie của BFF; access/refresh token được lưu phía server. Giảm khả năng JavaScript lấy token OAuth, nhưng vẫn cần chống XSS và CSRF vì XSS có thể gọi BFF bằng session của người dùng. |

Nếu dùng SPA trực tiếp với OAuth token, thường nên giữ access token trong memory và dùng refresh token rotation hoặc cơ chế sender-constrained phù hợp theo hướng dẫn của IdP. Nếu sản phẩm có backend, mô hình BFF thường giảm lượng credential có thể truy cập từ JavaScript. Không lưu secret client hoặc private key dài hạn trong bundle frontend; mọi người dùng có thể tải và phân tích bundle.

## 6. OAuth 2.0 và OpenID Connect trong trình duyệt

OAuth 2.0 là framework ủy quyền truy cập tài nguyên. OpenID Connect (OIDC) bổ sung lớp xác thực danh tính dựa trên OAuth 2.0 và cung cấp ID Token. Vì vậy, khi ứng dụng cần đăng nhập người dùng qua một Identity Provider, OIDC thường là giao thức phù hợp.

### 6.1. Authorization Code Flow với PKCE

Đối với ứng dụng browser public client, luồng thường được khuyến nghị là Authorization Code Flow với PKCE. SPA không thể giữ client secret an toàn vì mã chạy ở thiết bị người dùng.

Các bước khái quát:

1. SPA hoặc BFF transaction manager tạo `state`, `nonce` (khi dùng OIDC) và cặp PKCE `code_verifier`/`code_challenge` bằng bộ sinh số ngẫu nhiên mật mã, rồi ràng buộc chúng với giao dịch đăng nhập đang chờ.
2. Browser chuyển hướng người dùng đến authorization endpoint của IdP, gửi `client_id`, `redirect_uri`, `response_type=code`, `scope`, `state`, `nonce` và `code_challenge`.
3. Người dùng xác thực với IdP và cấp quyền theo yêu cầu.
4. IdP chuyển hướng về `redirect_uri` đã đăng ký cùng authorization code và `state`.
5. Ứng dụng so sánh `state` với giá trị đã lưu cho giao dịch đăng nhập; nếu không khớp thì dừng luồng.
6. Client/BFF đổi code tại token endpoint cùng `code_verifier`; IdP xác minh PKCE.
7. Với OIDC, ứng dụng xác minh ID Token, bao gồm chữ ký, issuer, audience, thời hạn, nonce và các kiểm tra liên quan.
8. Ứng dụng tạo session cục bộ hoặc duy trì token theo kiến trúc đã chọn.

```mermaid
sequenceDiagram
  participant B as Browser / App
  participant I as Identity Provider
  participant R as Application / BFF
  B->>B: Tạo state, nonce, code_verifier
  B->>I: Authorization request + code_challenge
  I->>I: Xác thực người dùng
  I-->>B: Redirect với code + state
  B->>B: Kiểm tra state
  B->>R: Gửi code / callback
  R->>I: Token request + code_verifier
  I-->>R: ID token / access token
  R->>R: Xác minh token và tạo session
  R-->>B: Session cookie
```

`state`, `nonce` và PKCE giải quyết các rủi ro khác nhau:

- `state` gắn callback với giao dịch đăng nhập do browser khởi tạo, giúp chống login CSRF và một số kiểu response injection.
- `nonce` liên kết ID Token với yêu cầu OIDC ban đầu, giúp phát hiện token bị phát lại hoặc đưa nhầm vào phiên.
- PKCE ràng buộc authorization code với client đã khởi tạo giao dịch, giảm nguy cơ code bị chặn rồi đổi ở client khác.

Các giá trị cần được tạo bằng cryptographic random generator, gắn với đúng giao dịch, hết hạn và chỉ dùng một lần. Không dùng `Math.random()` để tạo state, nonce, verifier hoặc session identifier.

### 6.2. Redirect URI và callback

Đăng ký redirect URI chính xác tại IdP. Tránh wildcard rộng hoặc redirect dựa trên URL tùy ý do query string cung cấp. Callback cần kiểm tra `state`, xử lý lỗi, từ chối code đã dùng và không ghi code/token vào log. Sau khi xử lý callback, điều hướng đến URL nội bộ đã allowlist để tránh open redirect.

Nếu callback dùng cross-site POST (`response_mode=form_post`), cookie giao dịch có thể chịu ảnh hưởng của `SameSite`. Cần thiết kế cookie/transaction state phù hợp với response mode và thử nghiệm trên các browser mục tiêu; không hạ toàn bộ session cookie xuống `SameSite=None` chỉ để sửa callback.

### 6.3. Tránh Implicit Flow và password grant

Implicit Flow từng được dùng cho SPA nhưng không còn là lựa chọn khuyến nghị cho ứng dụng mới. Authorization Code Flow với PKCE cung cấp cách xử lý code an toàn hơn. Resource Owner Password Credentials grant (password grant) cũng không phù hợp cho ứng dụng browser hiện đại vì buộc ứng dụng nhận trực tiếp password người dùng và không hỗ trợ đầy đủ các luồng xác thực tương tác như MFA, passkey hoặc đăng nhập liên kết.

Không tự xây dựng giao thức OAuth/OIDC bằng cách ghép URL và token thủ công. Dùng thư viện được duy trì, cấu hình đúng issuer, audience, redirect URI và kiểm tra bảo mật theo tài liệu của IdP.

## 7. Passkey và Web Authentication (WebAuthn)

Passkey cho phép người dùng xác thực bằng credential mật mã gắn với website, thường được đồng bộ qua hệ sinh thái thiết bị hoặc lưu trong authenticator. WebAuthn là API trình duyệt để đăng ký và sử dụng public-key credential. Private key không được gửi cho website; server lưu public key và xác minh chữ ký trong lần đăng nhập.

WebAuthn cần secure context (thường là HTTPS; `localhost` được hỗ trợ cho phát triển) và credential được ràng buộc với relying party ID (RP ID) hợp lệ cho origin hiện tại. RP ID thường là hostname của website hoặc domain cha hợp lệ theo quy tắc WebAuthn; không thể dùng một RP ID tùy ý ở domain khác.

### 7.1. Đăng ký passkey

Luồng đăng ký khái quát:

1. Người dùng đã có session hoặc trải qua bước xác minh danh tính phù hợp.
2. Server tạo challenge ngẫu nhiên, ngắn hạn và gắn với user cùng phiên đăng ký.
3. Browser gọi `navigator.credentials.create()` với `publicKey` options do server cung cấp.
4. Authenticator tạo cặp khóa cho credential và trả về attestation object; mức xác minh attestation phụ thuộc policy của ứng dụng.
5. Browser gửi kết quả về server.
6. Server xác minh challenge, origin, RP ID hash, loại credential, flags và chính sách attestation nếu có; sau đó lưu credential ID và public key.

### 7.2. Đăng nhập bằng passkey

Luồng xác thực thường dùng `navigator.credentials.get()`:

```js
const optionsResponse = await fetch("/api/webauthn/authentication-options", {
  method: "POST",
  credentials: "same-origin",
  headers: { "Content-Type": "application/json" }
});

const publicKeyOptions = await optionsResponse.json();
publicKeyOptions.challenge = decodeBase64Url(publicKeyOptions.challenge);
publicKeyOptions.allowCredentials = publicKeyOptions.allowCredentials?.map(
  (item) => ({ ...item, id: decodeBase64Url(item.id) })
);

const assertion = await navigator.credentials.get({
  publicKey: publicKeyOptions
});

await fetch("/api/webauthn/authenticate", {
  method: "POST",
  credentials: "same-origin",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(encodeAssertion(assertion))
});
```

Đoạn code chỉ minh họa việc trao đổi dữ liệu; `decodeBase64Url()` và `encodeAssertion()` cần chuyển đổi đúng các trường binary theo chuẩn WebAuthn. Không tự xác minh chữ ký trong frontend. Server phải xác minh challenge chưa dùng, origin chính xác, RP ID hash, chữ ký bằng public key đã đăng ký, credential ID và các cờ user presence/user verification theo policy.

WebAuthn ràng buộc credential với origin và RP ID, giúp chống phishing tốt hơn password truyền thống. Tuy nhiên, server vẫn phải xác thực kết quả đúng chuẩn và gắn credential với đúng tài khoản. Challenge phải ngẫu nhiên, ngắn hạn, lưu phía server và chỉ chấp nhận một lần. Không tái sử dụng challenge giữa nhiều phiên đăng nhập.

### 7.3. MFA và user verification

Passkey có thể dùng xác thực cục bộ bằng PIN, sinh trắc học hoặc cơ chế mở khóa thiết bị. Tùy authenticator, cờ `userVerified` thể hiện người dùng đã được xác minh tại authenticator. Ứng dụng cần xác định thao tác nào yêu cầu user verification hoặc step-up authentication, ví dụ đổi thông tin thanh toán hay thêm phương thức đăng nhập mới.

MFA dựa trên SMS có thể giúp tăng bảo vệ so với password đơn lẻ nhưng dễ bị tấn công SIM swap và phishing. TOTP cũng có thể bị phishing thời gian thực. Passkey/WebAuthn có khả năng chống phishing tốt hơn vì credential gắn với RP ID/origin, nhưng cần quy trình khôi phục tài khoản và quản lý thiết bị dự phòng an toàn.

## 8. CSRF và xác thực dựa trên cookie

CSRF xảy ra khi trình duyệt tự gửi credential (thường là cookie) đến website đích trong khi request được khởi tạo từ một site khác. Attacker có thể khiến browser gửi request thay đổi trạng thái mà người dùng không chủ ý thực hiện.

Một số biện pháp cần phối hợp:

- Đặt cookie session `SameSite=Lax` hoặc `Strict` nếu luồng sản phẩm cho phép; dùng `Secure` và `HttpOnly`.
- Dùng CSRF token cho request thay đổi trạng thái theo mô hình phù hợp. Token phải được ràng buộc với session và kiểm tra phía server.
- Kiểm tra `Origin` và/hoặc Fetch Metadata như `Sec-Fetch-Site` ở server cho endpoint nhạy cảm; xử lý client không gửi header theo policy rõ ràng.
- Không dùng GET cho thao tác thay đổi dữ liệu.
- Yêu cầu xác nhận lại hoặc step-up authentication cho hành động rủi ro cao.
- Không coi CORS là biện pháp chống CSRF. CORS chủ yếu quyết định script cross-origin có đọc được response; request đơn giản vẫn có thể đến server.

Ví dụ request thay đổi trạng thái với CSRF token:

```js
await fetch("/api/profile/email", {
  method: "PATCH",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken
  },
  body: JSON.stringify({ email: "new-address@example.com" })
});
```

Server phải xác minh token, session, quyền và dữ liệu đầu vào. Không chấp nhận chỉ vì request có header `X-CSRF-Token`; phải so sánh với token hợp lệ gắn với session. Header tùy chỉnh có thể khiến cross-origin fetch cần preflight, nhưng đây chỉ là thuộc tính của request và không thay thế xác minh token phía server.

## 9. XSS và credential trong browser

XSS cho phép mã JavaScript không tin cậy chạy trong origin của ứng dụng. Khi XSS xảy ra, attacker có thể đọc dữ liệu mà JavaScript truy cập được, thay đổi giao diện, gọi API thay người dùng và đánh cắp token lưu trong Web Storage hoặc memory. `HttpOnly` bảo vệ giá trị cookie khỏi việc đọc trực tiếp, nhưng không ngăn script độc hại thực hiện request cùng origin bằng cookie tự động đính kèm.

Giảm rủi ro XSS bằng cách:

- Encode output theo đúng ngữ cảnh HTML, attribute, URL, CSS và JavaScript.
- Tránh `innerHTML`, `document.write`, `eval` và các sink thực thi khi có API an toàn hơn.
- Dùng Content Security Policy với nonce/hash và hạn chế nguồn script.
- Cân nhắc Trusted Types cho DOM sink nguy hiểm trên trình duyệt hỗ trợ.
- Kiểm soát dependency, script bên thứ ba và quyền triển khai asset.
- Không lưu refresh token hoặc secret dài hạn trong `localStorage`.
- Giới hạn thời hạn token/session và cung cấp quy trình thu hồi.

Không nên tuyên bố rằng dùng HttpOnly cookie làm XSS không còn nguy hiểm. XSS vẫn có thể thao tác giao diện và gọi API mà người dùng hiện tại có quyền gọi. Phòng chống XSS là yêu cầu độc lập với cách lưu session.

## 10. Cookie bên thứ ba và đăng nhập trong iframe

Một số ứng dụng nhúng trang đăng nhập hoặc nội dung xác thực từ domain khác trong iframe. Cookie bên thứ ba ngày càng bị giới hạn hoặc phân vùng bởi trình duyệt. Vì vậy, flow dựa trên việc iframe luôn đọc được cookie IdP có thể không hoạt động ổn định.

Các hướng thiết kế nên xem xét:

- Dùng top-level redirect đến IdP rồi quay lại callback đã đăng ký.
- Dùng popup khi trải nghiệm sản phẩm yêu cầu, kiểm tra `postMessage` theo origin chính xác và kiểm soát opener/window reference.
- Dùng BFF để quản lý token phía server và giữ session cookie cùng site cho ứng dụng.
- Nếu thật sự cần nhúng cross-site, đánh giá Storage Access API và các cơ chế partitioned storage theo hỗ trợ trình duyệt; không giả định người dùng luôn cấp quyền.
- Không dùng `postMessage(..., "*")` để chuyển token hoặc dữ liệu xác thực. Receiver cần kiểm tra `event.origin`, `event.source` và schema.

Khi dùng popup, callback cần xác minh đúng cửa sổ mở luồng và kiểm tra `state`. Không nhận authorization code hoặc token từ bất kỳ cửa sổ nào chỉ vì message có đúng cấu trúc.

## 11. Logout, refresh và thu hồi credential

Logout cần kết thúc session phía server và xóa trạng thái phía browser. Ví dụ với cookie session:

```js
async function logout() {
  const response = await fetch("/api/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRF-Token": readCsrfToken()
    }
  });

  if (!response.ok) {
    throw new Error("Logout was not confirmed by the server.");
  }

  clearInMemoryUserState();
  clearAccountSpecificCaches();
  window.location.replace("/login");
}
```

Server cần thu hồi session và gửi cookie hết hạn với cùng tên, path và domain như cookie ban đầu. Với cookie `__Host-session`, ví dụ:

```http
Set-Cookie: __Host-session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

Với OAuth/OIDC, logout cục bộ và logout tại IdP là hai việc khác nhau. Ứng dụng cần xác định có gọi end-session endpoint hay không, cách xử lý post-logout redirect và cách thu hồi refresh token. Không xóa cookie cục bộ rồi tuyên bố token ở IdP đã bị thu hồi.

Nếu dùng refresh token, nên áp dụng rotation và phát hiện reuse theo khả năng của IdP. Khi refresh token bị dùng lại trái phép, server có thể thu hồi token family hoặc session theo policy. Access token ngắn hạn giúp giới hạn khoảng thời gian sử dụng khi bị lộ; hệ thống vẫn cần xử lý quyền bị thu hồi và refresh thất bại.

Đăng xuất trên một tab cần đồng bộ trạng thái với các tab khác. Có thể dùng `BroadcastChannel` hoặc sự kiện `storage` để yêu cầu tab khác xóa state và điều hướng. Đây chỉ là đồng bộ giao diện; server vẫn phải từ chối session đã thu hồi.

## 12. Security headers và cache cho trang xác thực

Trang đăng nhập và callback thường xử lý dữ liệu nhạy cảm. Cân nhắc các header phù hợp:

```http
Cache-Control: no-store
Referrer-Policy: strict-origin-when-cross-origin
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Đây là cấu hình minh họa. CSP phải điều chỉnh theo IdP, CDN, inline script và kiến trúc thực tế; ưu tiên nonce/hash cho inline script cần thiết. `frame-ancestors 'none'` phù hợp nếu trang không được phép nhúng; nếu cần nhúng, hãy allowlist origin cụ thể và đánh giá clickjacking. HSTS `includeSubDomains` chỉ nên bật khi toàn bộ subdomain sẵn sàng HTTPS.

Callback chứa authorization code, state hoặc thông tin lỗi không nên bị cache ở shared cache. Tránh đưa token vào URL fragment/query ngoài yêu cầu của giao thức và không gửi URL callback nhạy cảm đến analytics. Làm sạch URL sau khi xử lý code nếu luồng yêu cầu, đồng thời bảo đảm log phía server đã che dữ liệu nhạy cảm.

## 13. Kiểm thử browser authentication

Hãy dùng tài khoản thử và môi trường staging/local. Không dùng token hoặc password production trong DevTools, ảnh chụp hay báo cáo.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Session fixation | Ghi session ID trước login rồi đăng nhập. | Server cấp session ID mới sau khi xác thực. |
| Cookie attributes | Xem `Set-Cookie` trong Network/Application. | Session cookie có `Secure`, `HttpOnly`, `SameSite` và phạm vi host/path phù hợp. |
| Session hết hạn | Đợi idle timeout hoặc dùng session test đã hết hạn. | API riêng tư từ chối request và frontend xử lý trạng thái đăng nhập hết hạn. |
| Logout | Logout rồi replay cookie cũ trong môi trường lab. | Server từ chối session cũ; browser nhận cookie hết hạn. |
| CSRF | Thử request thay đổi trạng thái từ origin lab khác. | Server từ chối request không có token/Origin hợp lệ theo policy. |
| XSS trong vùng thử | Chèn payload kiểm thử vào nội dung hiển thị. | Payload được encode/chặn; không thể đọc credential hoặc thực hiện action trái phép. |
| Token storage | Kiểm tra Local Storage, Session Storage, IndexedDB và memory. | Không có secret dài hạn được lưu ngoài thiết kế đã phê duyệt. |
| OIDC callback | Thử state sai, code hết hạn, redirect URI khác và nonce không khớp. | Callback từ chối giao dịch không hợp lệ. |
| PKCE | Thử đổi code với verifier sai hoặc code đã dùng. | Token endpoint từ chối yêu cầu. |
| WebAuthn | Thử challenge cũ, origin sai hoặc credential không thuộc user. | Server từ chối assertion không hợp lệ. |
| Multi-tab logout | Mở hai tab, logout ở một tab. | Tab còn lại reset UI; API từ chối session đã thu hồi. |
| Cookie bên thứ ba | Kiểm tra flow trong browser chặn third-party cookies. | Luồng đăng nhập có fallback top-level redirect hoặc thiết kế tương thích. |

### 13.1. Quan sát bằng DevTools

Trong tab Network, chọn request đăng nhập, callback, refresh và logout. Kiểm tra status, redirect chain, `Set-Cookie`, request cookie, `Authorization`, cache header và lỗi CORS. Trong Application/Storage, kiểm tra cookie và Web Storage; nhớ rằng DevTools có thể hiển thị thông tin nhạy cảm mà JavaScript không đọc được, chẳng hạn cookie `HttpOnly`.

Trong Console, quan sát lỗi WebAuthn, CORS, CSP và JavaScript. Với WebAuthn, kiểm tra origin/RP ID mà ứng dụng sử dụng và trạng thái challenge ở server log. Với OIDC, dùng log đã redact để đối chiếu state/nonce theo giao dịch, không ghi raw code hoặc token.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ ẩn nội dung sau logout ở frontend | Session phía server vẫn có thể còn hiệu lực. | Thu hồi session ở server và yêu cầu API xác minh lại. |
| Lưu refresh token dài hạn trong `localStorage` | XSS có thể đọc và lấy token. | Ưu tiên BFF/HttpOnly session hoặc kiến trúc token có kiểm soát và rotation. |
| Cho rằng HttpOnly cookie ngăn mọi tác động của XSS | Script độc hại vẫn có thể gọi API bằng cookie tự động gửi. | Phòng chống XSS, CSP/Trusted Types và authorization server-side. |
| Dùng CORS để chống CSRF | Request đơn giản vẫn có thể đến server và tạo side effect. | CSRF token, SameSite, Origin/Fetch Metadata và kiểm tra quyền. |
| Dùng JWT mà không kiểm tra `iss`, `aud`, `exp` | Token không dành cho API hoặc đã hết hạn vẫn có thể bị chấp nhận. | Xác minh chữ ký và toàn bộ claim theo policy. |
| Bỏ qua `state` hoặc PKCE trong OIDC | Có thể bị login CSRF, code injection hoặc code interception. | Dùng Authorization Code + PKCE và kiểm tra state/nonce. |
| Tin payload JWT đã Base64URL là bí mật | Claim có thể bị người sở hữu token đọc. | Không đặt secret vào payload; dùng mã hóa riêng nếu thực sự cần và đúng chuẩn. |
| Tin browser đã xác minh passkey thay server | Client có thể gửi assertion giả hoặc challenge cũ. | Server xác minh challenge, origin, RP ID, chữ ký và credential. |
| Chỉ xóa cookie khi logout | Session server hoặc refresh token có thể còn hiệu lực. | Thu hồi session/token và hết hạn cookie. |
| Đăng nhập trong iframe luôn hoạt động | Third-party cookie blocking có thể làm mất trạng thái IdP. | Ưu tiên top-level redirect/BFF và kiểm thử trên browser mục tiêu. |

## 15. Bài thực hành

Hãy xây dựng một ứng dụng demo có trang đăng nhập, một API riêng tư và hai cách xác thực để so sánh. Dùng tài khoản giả và môi trường local/staging.

1. Triển khai session cookie với `Secure`, `HttpOnly`, `SameSite` phù hợp; tạo session ID mới sau login.
2. Bảo vệ một API `/api/me` bằng session và kiểm tra authorization ở server.
3. Thêm endpoint logout để thu hồi session và hết hạn cookie; thử replay cookie cũ.
4. Tạo một SPA demo dùng Authorization Code + PKCE với IdP thử nghiệm hoặc môi trường sandbox. Kiểm tra state, nonce, redirect URI và verifier.
5. Đăng ký và đăng nhập bằng WebAuthn/passkey; thử challenge hết hạn hoặc assertion sai.
6. Tạo một request thay đổi trạng thái và kiểm tra CSRF token cùng SameSite bằng trang lab khác origin.
7. Thử XSS trong nội dung được render ở môi trường kiểm thử; quan sát khác biệt giữa cookie HttpOnly và token trong Web Storage.
8. Mở hai tab, logout ở một tab và kiểm tra đồng bộ trạng thái cùng việc server từ chối session cũ.
9. Ghi lại cookie attributes, Network trace và kết quả kiểm thử sau khi che credential.

Hoàn thành bài thực hành khi bạn giải thích được browser giữ và gửi credential theo cơ chế nào, server xác minh danh tính và quyền ở đâu, cách lựa chọn session/token/passkey phù hợp với kiến trúc, và những lớp bảo vệ nào cần thiết để giảm XSS, CSRF, token theft cùng lỗi callback.
