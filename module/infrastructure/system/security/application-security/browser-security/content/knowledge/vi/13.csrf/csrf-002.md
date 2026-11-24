# CSRF trên cookie authentication: khi trình duyệt tự gửi thông tin đăng nhập

## 1. Vì sao cookie authentication dễ gặp CSRF?

Cookie authentication là mô hình trong đó server cấp một cookie phiên sau khi người dùng đăng nhập. Ở các request tiếp theo, trình duyệt tự đính kèm cookie phù hợp với domain, path, scheme và chính sách cookie. Ứng dụng không cần JavaScript tự đọc cookie rồi thêm vào từng request.

Sự tiện lợi này tạo ra một đặc tính bảo mật quan trọng: **trình duyệt có thể gửi cookie xác thực tới ứng dụng ngay cả khi request được khởi tạo từ một website khác**. Nếu người dùng đang đăng nhập vào ngân hàng tại `https://bank.example` rồi truy cập trang độc hại, trang đó có thể cố khiến trình duyệt gửi request tới ngân hàng. Nếu endpoint thực hiện hành động dựa vào cookie mà không xác minh ý định của người dùng, kẻ tấn công có thể gây ra hành động ngoài ý muốn.

Đó là **Cross-Site Request Forgery (CSRF)** — giả mạo request xuyên site. Kẻ tấn công thường không cần đọc response của ngân hàng; chỉ cần trình duyệt gửi một request đã mang thông tin xác thực và server thực hiện hành động.

Trong module bảo mật trình duyệt, CSRF trên cookie authentication cần được hiểu cùng với SameSite, origin/site, SOP, CORS, form submission, Fetch Metadata, cookie attributes và kiểm tra quyền ở backend.

Sau bài học, bạn có thể:

- Mô tả điều kiện khiến cookie authentication có nguy cơ CSRF.
- Phân biệt CSRF với XSS, CORS và lỗi phân quyền.
- Chọn biện pháp phù hợp: CSRF token, SameSite, kiểm tra Origin/Referer và Fetch Metadata.
- Thiết kế luồng form/API an toàn khi trình duyệt tự gửi cookie.
- Kiểm chứng một request CSRF trong môi trường lab.

## 2. Cơ chế tấn công: trình duyệt gửi cookie thay cho attacker

Giả sử người dùng đã đăng nhập vào:

```text
https://bank.example
Cookie: session=opaque-session-id; Secure; HttpOnly; SameSite=None
```

Người dùng mở một website khác do attacker kiểm soát. Trang này có thể tạo form gửi tới ngân hàng:

```html
<form action="https://bank.example/transfer" method="POST">
  <input type="hidden" name="to" value="attacker-account">
  <input type="hidden" name="amount" value="500">
  <button type="submit">Xem tài liệu</button>
</form>
```

Trong một cuộc tấn công thật, form có thể được submit tự động hoặc được ngụy trang trong giao diện. Nếu cookie phiên được gửi theo chính sách trình duyệt và server chỉ kiểm tra session cookie, ngân hàng có thể hiểu request là do người dùng đã đăng nhập thực hiện.

Luồng tấn công:

```text
Người dùng đăng nhập bank.example
          │
          ▼
Trình duyệt lưu session cookie
          │
          ▼
Người dùng mở evil.example
          │
          │ Form POST tới bank.example/transfer
          ▼
Trình duyệt gửi request tới bank.example
          │
          ├─ Cookie session được đính kèm nếu cookie policy cho phép
          │
          ▼
Server nhận request có session hợp lệ
          │
          ├─ Không có CSRF validation
          ▼
Server thực hiện hành động ngoài ý muốn
```

Trang attacker có thể không đọc được phản hồi do Same-Origin Policy. Điều đó **không ngăn server thực hiện hành động**. CSRF là vấn đề về tính xác thực của ý định request, không phải chỉ là vấn đề đọc response.

## 3. Điều kiện để CSRF xảy ra

Một tình huống CSRF thường có các điều kiện sau:

1. Người dùng đang có phiên đăng nhập hợp lệ với ứng dụng mục tiêu.
2. Trình duyệt tự động gửi thông tin xác thực, thường là cookie session.
3. Attacker có cách khiến trình duyệt gửi request tới endpoint mục tiêu.
4. Endpoint thay đổi trạng thái dựa vào thông tin xác thực mà không kiểm tra thêm ý định/nguồn request.
5. Ứng dụng thiếu biện pháp chống CSRF hiệu quả hoặc cấu hình biện pháp đó sai.

Không phải mọi endpoint đều có cùng mức rủi ro. Request chỉ đọc dữ liệu, không tạo tác dụng phụ, thường không phải mục tiêu CSRF điển hình; tuy nhiên, endpoint GET có side effect là thiết kế nguy hiểm và có thể bị kích hoạt bằng link, ảnh, iframe hoặc prefetch.

### 3.1 Vì sao session cookie không chứng minh ý định?

Cookie cho server biết request gắn với phiên nào. Nó không chứng minh người dùng chủ động nhấn nút hoặc đồng ý với hành động cụ thể. Khi trình duyệt tự gửi cookie, server chỉ biết phiên hợp lệ, không biết request bắt nguồn từ trang nào và người dùng có chủ ý hay không.

Vì vậy, với hành động thay đổi trạng thái, server cần một tín hiệu bổ sung mà trang attacker không thể tự tạo hợp lệ, chẳng hạn CSRF token gắn với phiên, kết hợp kiểm tra nguồn request.

### 3.2 Những hành động thường cần bảo vệ

- Chuyển tiền, đặt hàng, thanh toán hoặc hoàn tiền.
- Đổi email, mật khẩu, số điện thoại hoặc địa chỉ nhận hàng.
- Thêm/xóa người dùng, thay đổi vai trò và quyền.
- Tạo API key, bật tích hợp hoặc thay đổi cài đặt bảo mật.
- Đăng xuất, liên kết tài khoản hoặc chấp thuận một giao dịch.

Ngay cả thao tác ít nhạy cảm như logout cũng có thể bị lợi dụng để gây gián đoạn hoặc phá vỡ luồng bảo mật.

## 4. CSRF khác XSS, SOP và CORS như thế nào?

| Cơ chế/lỗ hổng | Vấn đề chính | Ví dụ |
| --- | --- | --- |
| **CSRF** | Server nhận một request có cookie hợp lệ nhưng request không xuất phát từ ý định hợp lệ của người dùng. | Trang khác gửi form chuyển tiền. |
| **XSS** | Attacker thực thi script trong origin của ứng dụng. | Mã độc chạy trong trang ngân hàng và gọi API bằng quyền trang đó. |
| **SOP** | Giới hạn script đọc dữ liệu của document khác origin. | Trang attacker không đọc được DOM ngân hàng. |
| **CORS** | Server khai báo origin nào được JavaScript đọc response cross-origin. | API cho phép frontend chính đọc JSON. |
| **Authentication** | Xác định request thuộc người dùng/phiên nào. | Session cookie nhận diện tài khoản đã đăng nhập. |
| **Authorization** | Xác định người dùng có quyền thực hiện hành động không. | Chỉ chủ tài khoản mới được đổi thông tin tài khoản. |

SOP và CORS không tự ngăn request CSRF. Một form HTML cross-origin có thể gửi một số request mà không cần preflight. CORS chủ yếu quyết định JavaScript có được đọc response hay không; server vẫn có thể đã xử lý request.

XSS có thể vượt qua nhiều biện pháp CSRF nếu attacker chạy được script trong origin hợp lệ và đọc được CSRF token trong DOM. Vì vậy, CSRF protection và XSS protection cần được triển khai song song.

## 5. Những cách gửi request có thể bị lợi dụng

### 5.1 HTML form

Form là phương thức phổ biến vì trình duyệt có thể gửi request mà không cần JavaScript cross-origin:

```html
<form action="https://app.example.com/settings/email" method="POST">
  <input type="hidden" name="email" value="attacker@example.net">
  <button type="submit">Tiếp tục</button>
</form>
```

Nếu ứng dụng chấp nhận request chỉ dựa vào cookie, attacker có thể lợi dụng hành vi này.

### 5.2 GET request và tài nguyên nhúng

Một trang độc hại có thể khiến browser điều hướng hoặc tải tài nguyên từ endpoint:

```html
<img src="https://app.example.com/account/delete?id=42" alt="">
```

Đây là lý do **GET phải là phương thức an toàn về mặt ngữ nghĩa**: không xóa, cập nhật hoặc tạo giao dịch. Các hành động thay đổi trạng thái cần dùng phương thức phù hợp và có CSRF protection. Chỉ đổi GET thành POST vẫn chưa đủ nếu server không xác minh token/nguồn request.

### 5.3 Fetch/XHR cross-origin

JavaScript ở origin khác có thể thử gửi request:

```javascript
fetch("https://app.example.com/api/email", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/x-www-form-urlencoded"
  },
  body: "email=attacker%40example.net"
});
```

Request này có thể thuộc nhóm CORS-safelisted và không cần preflight. Dù JavaScript không đọc được response, request vẫn có thể tới server. CORS không phải biện pháp CSRF độc lập.

Nếu request dùng header tùy chỉnh hoặc Content-Type JSON, preflight có thể xuất hiện. Nhưng chỉ nên coi preflight là một phần của chính sách CORS; server vẫn phải bảo vệ endpoint bằng token hoặc cơ chế chống CSRF thích hợp.

## 6. SameSite cookie: lớp phòng vệ đầu tiên

Thuộc tính `SameSite` điều khiển việc trình duyệt gửi cookie trong các ngữ cảnh same-site và cross-site. Ba giá trị thường gặp:

| Giá trị | Hành vi khái quát | Ứng dụng |
| --- | --- | --- |
| `Strict` | Cookie chỉ được gửi trong ngữ cảnh same-site phù hợp. | Luồng nhạy cảm không cần duy trì cookie qua navigation từ site ngoài. |
| `Lax` | Cho phép cookie trong ngữ cảnh same-site và một số top-level cross-site navigation an toàn, thường là GET. | Lựa chọn mặc định thực tế cho nhiều session cookie. |
| `None` | Cho phép gửi trong ngữ cảnh cross-site nếu các điều kiện khác đáp ứng; cần Secure trên trình duyệt hiện đại. | Một số luồng nhúng/SSO cross-site cần cookie. |

Ví dụ:

```http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Với `SameSite=Lax`, một form POST cross-site thông thường không gửi cookie Lax; nhưng top-level navigation bằng phương thức an toàn như GET có thể gửi cookie. Vì vậy, nếu endpoint GET thay đổi trạng thái, SameSite không cứu được thiết kế đó.

### 6.1 SameSite xét site, không xét origin

`https://evil.example.com` và `https://app.example.com` có thể cùng site nhưng khác origin. Một subdomain bị chiếm quyền vẫn có thể tạo request same-site tới ứng dụng. Do đó, SameSite không thay thế token hoặc kiểm tra Origin.

### 6.2 SameSite=None không có nghĩa cookie luôn được gửi

`SameSite=None; Secure` cho phép cookie được xét trong ngữ cảnh cross-site, nhưng trình duyệt vẫn có thể chặn hoặc phân vùng cookie bên thứ ba theo chính sách quyền riêng tư. Cookie còn cần khớp domain/path và credentials mode của request.

### 6.3 Không phụ thuộc hoàn toàn vào mặc định của browser

Trình duyệt hiện đại thường áp dụng mặc định Lax cho cookie không chỉ định SameSite, nhưng có khác biệt triển khai và một số hành vi tương thích lịch sử. Hãy đặt thuộc tính tường minh theo luồng ứng dụng thay vì dựa vào mặc định. Một số browser từng có ngoại lệ tạm thời cho cookie mới trong một khoảng thời gian ngắn; không dùng ngoại lệ này làm cơ sở thiết kế.

## 7. CSRF token: xác minh ý định của request

Một biện pháp phổ biến là **CSRF token** — giá trị bí mật, khó đoán, được server liên kết với phiên người dùng và yêu cầu client gửi lại khi thực hiện hành động thay đổi trạng thái.

Trang attacker có thể khiến trình duyệt tự gửi cookie, nhưng không thể đọc token từ trang khác origin do SOP. Nếu server yêu cầu token hợp lệ và token không bị lộ qua một kênh khác, request giả mạo sẽ bị từ chối.

### 7.1 Synchronizer token pattern

Server tạo token gắn với session và cung cấp cho trang hợp lệ, ví dụ qua HTML:

```html
<form action="/profile/email" method="POST">
  <input type="hidden" name="_csrf" value="random-session-bound-token">
  <input type="email" name="email">
  <button type="submit">Cập nhật email</button>
</form>
```

Khi nhận POST, server:

1. Xác định session từ cookie.
2. Tìm CSRF token dự kiến gắn với session đó.
3. So sánh token trong request với token server lưu.
4. Chỉ tiếp tục khi token hợp lệ, còn hiệu lực và đúng phiên.

Token nên được tạo bằng nguồn ngẫu nhiên mật mã, không thể suy đoán và được ràng buộc với phiên. Server có thể xoay vòng token khi tạo phiên mới hoặc sau sự kiện bảo mật phù hợp. Không ghi token vào URL vì URL có thể xuất hiện trong history, log và Referer.

### 7.2 CSRF token cho SPA/API

Với SPA, server có thể cung cấp token qua HTML bootstrap hoặc một endpoint cùng origin. Client gửi token trong custom header:

```javascript
const csrfToken = readCsrfTokenFromTrustedBootstrap();

await fetch("/api/profile/email", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken
  },
  body: JSON.stringify({ email: "new@example.com" })
});
```

Server phải kiểm tra header `X-CSRF-Token` và ràng buộc token với session. Form HTML thông thường không thể tự đặt custom header tùy ý; JavaScript từ origin khác sẽ gặp CORS preflight và không thể đọc token cùng origin. Tuy nhiên, cấu hình CORS phải chặt chẽ và endpoint không được chấp nhận một fallback không an toàn.

Không đọc token từ cookie HttpOnly (JavaScript không đọc được) hoặc cho rằng chỉ cần tên header lạ là đủ trong mọi thiết kế. Token phải được xác minh ở server.

### 7.3 Token không phải là authorization

CSRF token chứng minh request có tín hiệu hợp lệ được cấp trong ngữ cảnh ứng dụng. Nó không chứng minh người dùng có quyền chuyển tiền hoặc sửa tài khoản khác. Server vẫn cần kiểm tra quyền trên từng hành động.

## 8. Double-submit cookie pattern

Một cách khác là **double-submit cookie**: server đặt một CSRF token trong cookie và client gửi cùng giá trị đó thêm lần nữa trong body hoặc custom header. Server so sánh hai giá trị.

Mô hình cơ bản:

```text
Cookie:
  csrf_token = random-token

Request:
  Cookie: csrf_token=random-token
  X-CSRF-Token: random-token

Server:
  so sánh cookie token và request token
```

Ví dụ:

```http
Set-Cookie: csrf_token=random-value; Path=/; Secure; SameSite=Lax
```

```javascript
fetch("/api/transfer", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": readCsrfToken()
  },
  body: JSON.stringify({ amount: 100 })
});
```

### 8.1 Không dùng double-submit ngây thơ khi có thể bị cookie injection

Nếu attacker có thể đặt cookie cùng tên qua subdomain hoặc một kênh injection khác, họ có thể cố tạo token mà server sẽ so sánh. Vì vậy, double-submit cookie đơn giản không đủ trong mọi môi trường.

Nên dùng **signed double-submit token** hoặc token được ràng buộc với session: server ký token bằng secret phía server, gắn token với session ID/nonce và xác minh chữ ký cũng như liên kết phiên. Không tin giá trị cookie chỉ vì nó trùng với request header.

Cookie CSRF không nhất thiết phải HttpOnly nếu frontend cần đọc để gửi lại, nhưng phải cân nhắc nguy cơ XSS và cookie injection. Với synchronizer token, có thể giữ token ngoài cookie và cung cấp qua HTML/API cùng origin.

## 9. Kiểm tra Origin và Referer

Server có thể xác minh nguồn của request thay đổi trạng thái bằng header `Origin`, hoặc dùng `Referer` làm tín hiệu dự phòng khi Origin không có theo ngữ cảnh.

Ví dụ chính sách:

```text
Allowed origin:
  https://app.example.com

Unsafe request:
  if Origin exists:
      require exact origin match
  else if Referer exists:
      parse and require exact origin match
  else:
      reject or require another explicit CSRF proof
```

So sánh phải chính xác cả scheme, host và port. Không dùng `includes("example.com")` hoặc kiểm tra hậu tố đơn giản. Một origin như `https://app.example.com.attacker.test` không phải origin được phép.

### 9.1 Origin không phải danh tính người dùng

Header Origin là tín hiệu do trình duyệt gửi trong những ngữ cảnh phù hợp. Nó giúp server kiểm tra request có xuất phát từ origin được mong đợi hay không, nhưng không thay authentication hoặc authorization. Với client không phải trình duyệt, header có thể bị tự đặt; vì vậy server vẫn phải kiểm tra session/token và quyền.

### 9.2 Referer có thể bị rút gọn hoặc vắng mặt

Referrer-Policy có thể làm giảm thông tin trong Referer; một số ngữ cảnh có thể không gửi header này. Nếu dùng Referer làm fallback, hãy parse URL và so sánh origin chính xác, không tìm chuỗi con. Với request nhạy cảm mà không có Origin/Referer, cần một quy tắc fail-closed hoặc yêu cầu CSRF token rõ ràng.

## 10. Fetch Metadata: Sec-Fetch-Site và các header liên quan

Trình duyệt hiện đại có thể gửi **Fetch Metadata request headers** để mô tả ngữ cảnh khởi tạo request. Header hữu ích cho CSRF là `Sec-Fetch-Site`:

| Giá trị | Ý nghĩa khái quát |
| --- | --- |
| `same-origin` | Request cùng origin với document khởi tạo. |
| `same-site` | Khác origin nhưng cùng site. |
| `cross-site` | Khởi tạo từ site khác. |
| `none` | Request không có site nguồn thông thường, ví dụ điều hướng do người dùng trực tiếp khởi tạo trong một số ngữ cảnh. |

Server có thể áp dụng quy tắc cho endpoint thay đổi trạng thái:

```javascript
function rejectCrossSiteUnsafeRequest(req, res, next) {
  const safeMethods = new Set(["GET", "HEAD", "OPTIONS"]);
  const fetchSite = req.get("Sec-Fetch-Site");

  if (!safeMethods.has(req.method) && fetchSite === "cross-site") {
    return res.sendStatus(403);
  }

  next();
}
```

Đây là ví dụ đơn giản. Ứng dụng có thể cần cho phép một số luồng cross-site hợp lệ như callback đăng nhập hoặc thanh toán. Hãy xây dựng ngoại lệ theo route và xác minh thêm token/trạng thái nghiệp vụ, không tạo ngoại lệ rộng cho toàn bộ API.

### 10.1 Same-site không luôn đáng tin

`Sec-Fetch-Site: same-site` có thể đến từ một subdomain khác origin. Nếu subdomain có thể bị chiếm quyền hoặc chứa nội dung không tin cậy, không nên tự động coi mọi request same-site là an toàn. Có thể kết hợp kiểm tra Origin chính xác và CSRF token.

### 10.2 Không phải client nào cũng gửi Fetch Metadata

Client cũ, một số môi trường nhúng hoặc công cụ không phải browser có thể không gửi các header này. Đừng xử lý việc thiếu `Sec-Fetch-Site` như bằng chứng request hợp lệ. Dùng CSRF token và kiểm tra Origin/Referer như các lớp phù hợp, đồng thời xác định chính sách fallback rõ ràng.

## 11. CORS không phải biện pháp chống CSRF

Một nhầm lẫn phổ biến là cho rằng API không bật CORS thì website khác không thể gửi request. Điều đó sai:

- HTML form có thể gửi một số request cross-origin mà không cần CORS preflight.
- Một số request GET hoặc request safelisted có thể được gửi trước khi browser kiểm tra response.
- CORS chủ yếu kiểm soát JavaScript có được đọc response hay không.
- Server có thể thực hiện hành động trước khi browser quyết định không cho script đọc response.

Ví dụ request form-encoded:

```html
<form action="https://app.example.com/api/settings" method="POST">
  <input name="timezone" value="UTC">
  <button type="submit">Gửi</button>
</form>
```

Ngay cả khi response không có `Access-Control-Allow-Origin`, request có thể đã tới server. Vì vậy, **không dùng “tắt CORS” như giải pháp CSRF**.

Một API chỉ nhận JSON và custom header có thể giảm bề mặt request form đơn giản, nhưng không thay thế token/Origin validation. Nếu cho phép CORS từ origin attacker và cho credentials, chính sách đó có thể làm tăng rủi ro đọc dữ liệu hoặc gửi request tùy cấu hình.

## 12. Thiết kế endpoint và cookie an toàn

Một mô hình bảo vệ thực tế nên kết hợp nhiều lớp:

| Lớp | Cách áp dụng | Mục đích |
| --- | --- | --- |
| Cookie | `Secure`, `HttpOnly`, `SameSite=Lax/Strict` phù hợp; host-only khi có thể. | Giảm việc lộ và gửi cookie trong ngữ cảnh không cần thiết. |
| CSRF token | Synchronizer token hoặc signed/session-bound double-submit. | Xác minh request đến từ luồng ứng dụng hợp lệ. |
| Origin/Referer | So sánh chính xác origin của unsafe request. | Phát hiện request được khởi tạo từ site không được phép. |
| Fetch Metadata | Chặn cross-site unsafe request theo route. | Thêm tín hiệu về ngữ cảnh khởi tạo. |
| HTTP semantics | GET/HEAD không thay đổi trạng thái. | Giảm request thay đổi trạng thái có thể bị kích hoạt bằng navigation/tài nguyên. |
| Authorization | Kiểm tra quyền trên từng tài nguyên/hành động. | Ngăn người dùng hợp lệ thực hiện hành động ngoài quyền. |
| XSS prevention | Output encoding, DOM API an toàn, CSP, Trusted Types. | Ngăn attacker chạy script trong origin tin cậy và lấy token. |

### 12.1 Ví dụ flow xử lý server

Với một endpoint thay đổi email:

```text
POST /account/email
   │
   ├─ Xác thực session cookie
   ├─ Kiểm tra user có quyền sửa tài khoản
   ├─ Kiểm tra Origin/Referer theo allowlist
   ├─ Kiểm tra Fetch Metadata nếu được gửi
   ├─ Xác minh CSRF token gắn với session
   ├─ Validate email và yêu cầu nghiệp vụ
   └─ Cập nhật dữ liệu
```

Thứ tự cụ thể có thể khác theo framework, nhưng server không được thực hiện side effect trước khi hoàn tất các kiểm tra cần thiết. Với các hành động có rủi ro cao, cân nhắc xác nhận lại bằng mật khẩu, MFA hoặc bước xác nhận giao dịch.

## 13. Bài thực hành: mô phỏng và chặn CSRF

Thực hiện trong hai ứng dụng local do bạn kiểm soát:

- Ứng dụng mục tiêu: `http://localhost:3000`.
- Trang attacker mô phỏng: `http://localhost:4000`.

Dùng tài khoản thử nghiệm và dữ liệu giả. Mục tiêu là quan sát browser gửi cookie và cách server từ chối request thiếu token.

### 13.1 Tạo endpoint lab không có CSRF protection

Ở ứng dụng mục tiêu, tạo form đổi trạng thái thử nghiệm và endpoint POST chỉ kiểm tra session cookie. Đăng nhập bằng tài khoản lab, sau đó mở trang attacker và submit form tới endpoint mục tiêu. Quan sát Network để xác định cookie có được gửi hay không theo thuộc tính SameSite và môi trường browser.

Ví dụ form mô phỏng:

```html
<form action="http://localhost:3000/lab/change-setting" method="POST">
  <input type="hidden" name="value" value="attacker-controlled">
  <button type="submit">Thử gửi request</button>
</form>
```

Vì `localhost:3000` và `localhost:4000` khác origin nhưng thường cùng site, kết quả cookie có thể khác với tấn công cross-site thực tế. Hãy ghi nhận cả origin và site; có thể dùng hai hostname lab khác nhau để thử cross-site, nhưng cần cấu hình loopback/HTTPS phù hợp.

### 13.2 Bật CSRF token

Server tạo token gắn với session và render vào form:

```html
<form action="/lab/change-setting" method="POST">
  <input type="hidden" name="_csrf" value="session-bound-random-token">
  <input type="hidden" name="value" value="new-value">
  <button type="submit">Cập nhật</button>
</form>
```

Khi nhận request, server yêu cầu `_csrf` khớp token của session. Gửi lại form giả mạo từ trang attacker nhưng không có token hợp lệ; server phải từ chối và không cập nhật dữ liệu.

### 13.3 Bổ sung kiểm tra Origin và Fetch Metadata

Với POST từ trang attacker, kiểm tra:

- `Origin` có phải `http://localhost:3000` không?
- `Sec-Fetch-Site` có giá trị `same-site` hay `cross-site`?
- Server có từ chối request không hợp lệ trước khi thực hiện thay đổi không?

Không chỉ dựa vào `same-site` để tin request, vì hai cổng localhost có thể cùng site nhưng khác origin.

### 13.4 Thử thay đổi SameSite

Thử cookie phiên với `SameSite=Lax` và `SameSite=None; Secure` trong môi trường HTTPS phù hợp. Quan sát cookie trong request cross-site POST và top-level navigation GET. Kết quả phụ thuộc browser, secure context, chính sách cookie bên thứ ba và thiết lập lab.

Không dùng GET để cập nhật trạng thái trong bất kỳ biến thể thử nghiệm nào. Khi kết thúc, khôi phục cấu hình an toàn và xóa dữ liệu phiên lab.

## 14. Checklist triển khai CSRF cho cookie authentication

- [ ] Cookie session có `Secure`, `HttpOnly` và SameSite phù hợp.
- [ ] Cookie host-only được ưu tiên nếu không cần chia sẻ subdomain.
- [ ] GET/HEAD không tạo hoặc thay đổi trạng thái.
- [ ] Tất cả unsafe methods (POST/PUT/PATCH/DELETE và hành động tương đương) được bảo vệ.
- [ ] CSRF token khó đoán và được gắn với session hoặc được ký/session-bound.
- [ ] Token được kiểm tra ở server trước mọi side effect.
- [ ] Origin/Referer được so sánh chính xác, không dùng substring.
- [ ] Fetch Metadata được dùng như lớp bổ sung với fallback rõ ràng.
- [ ] CORS allowlist không cấp credentials cho origin không tin cậy.
- [ ] Same-site subdomain và luồng callback bên ngoài đã được đánh giá.
- [ ] XSS được phòng vệ vì XSS có thể lấy token hoặc thao tác trong origin hợp lệ.
- [ ] Hành động nhạy cảm có authorization và xác nhận bổ sung khi cần.

## 15. Câu hỏi tự kiểm tra

1. Vì sao browser có thể gửi cookie phiên khi request được khởi tạo từ một trang khác?
2. Attacker có cần đọc response để khai thác CSRF không?
3. Vì sao SOP và CORS không tự ngăn HTML form gửi request?
4. SameSite=Lax hạn chế loại request nào và vì sao GET vẫn phải không có side effect?
5. Vì sao same-site nhưng cross-origin subdomain vẫn có thể là nguồn CSRF?
6. Synchronizer token khác double-submit cookie ở cách lưu và xác minh như thế nào?
7. Vì sao double-submit cookie ngây thơ có thể gặp cookie injection?
8. Khi nào server nên kiểm tra Origin, Referer và Sec-Fetch-Site?
9. Vì sao CSRF token không thay thế authorization?
10. XSS ảnh hưởng thế nào tới hiệu quả của CSRF token?

## 16. Tổng kết

CSRF trên cookie authentication xảy ra vì trình duyệt tự gửi cookie phiên phù hợp với request, kể cả khi request được khởi tạo từ một site khác. Attacker có thể khiến trình duyệt gửi form, navigation hoặc request cross-origin; server có thể thực hiện hành động dù SOP/CORS không cho attacker đọc response.

Phòng vệ cần nhiều lớp: cookie Secure/HttpOnly/SameSite phù hợp, CSRF token gắn với session hoặc signed double-submit, kiểm tra Origin/Referer chính xác, Fetch Metadata, quy tắc GET không thay đổi trạng thái và authorization ở backend. CORS không phải CSRF protection; XSS có thể làm suy yếu token defense nên phải được xử lý song song. Hãy kiểm thử request thực tế trong trình duyệt và xác nhận server từ chối request giả mạo trước khi có bất kỳ side effect nào.
