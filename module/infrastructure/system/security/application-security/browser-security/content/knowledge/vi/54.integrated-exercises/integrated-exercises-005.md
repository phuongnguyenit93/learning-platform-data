# Thiết kế CSRF defense

CSRF (Cross-Site Request Forgery) xảy ra khi trình duyệt gửi một yêu cầu có quyền của người dùng đến ứng dụng mà người dùng đã đăng nhập, trong khi yêu cầu đó được kích hoạt từ một trang web khác. Kẻ tấn công thường không cần biết mật khẩu hay đọc được phản hồi. Chỉ cần trình duyệt tự đính kèm cookie phiên vào một yêu cầu làm thay đổi trạng thái là ứng dụng có thể thực hiện hành động ngoài ý muốn.

Thiết kế phòng vệ CSRF vì vậy phải bắt đầu từ cách ứng dụng xác thực người dùng và cách trình duyệt gửi thông tin xác thực. Bài thực hành này xây dựng chính sách cho ứng dụng dùng cookie phiên, sau đó mở rộng sang SPA, API và các luồng điều hướng qua bên thứ ba.

## Mục tiêu

Sau bài này, bạn có thể:

- Mô tả điều kiện để một yêu cầu CSRF thành công và giải thích vì sao Same-Origin Policy không tự ngăn được yêu cầu đó.
- Chọn và triển khai CSRF token phù hợp với ứng dụng dùng session cookie.
- Kết hợp `SameSite`, kiểm tra `Origin`/`Referer`, Fetch Metadata và CORS đúng vai trò.
- Xác định endpoint cần bảo vệ, ngoại lệ có kiểm soát và các trường hợp dễ tạo ra lỗ hổng.
- Xây dựng bộ kiểm thử chứng minh yêu cầu hợp lệ được chấp nhận và yêu cầu giả mạo bị từ chối.

## 1. Xác định mối đe dọa

Giả sử người dùng đăng nhập vào `https://bank.example.com`. Máy chủ cấp cookie phiên:

```http
Set-Cookie: __Host-session=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Người dùng vẫn đang đăng nhập nhưng mở một trang do kẻ tấn công kiểm soát tại `https://attacker.example.com`. Trang đó có thể tạo một form gửi yêu cầu chuyển tiền:

Hai host này khác origin nhưng cùng site. Vì vậy, cookie `SameSite=Lax` vẫn có thể được gửi trong yêu cầu từ subdomain tấn công đến ứng dụng, và `Sec-Fetch-Site` có thể mang giá trị `same-site`. Quy tắc chỉ chặn `cross-site` sẽ không bắt được tình huống này; ứng dụng vẫn cần kiểm tra origin chính xác và CSRF token.

```html
<form action="https://bank.example.com/api/transfers" method="POST">
  <input name="destination" value="attacker-account">
  <input name="amount" value="5000000">
  <button type="submit">Continue</button>
</form>
<script>
  document.forms[0].submit();
</script>
```

Nếu cookie phiên được gửi cùng yêu cầu và máy chủ chỉ kiểm tra cookie, máy chủ có thể hiểu đây là hành động của người dùng đã đăng nhập. Kẻ tấn công không cần đọc phản hồi để gây ra thay đổi.

Same-Origin Policy (SOP) giới hạn cách một origin đọc dữ liệu của origin khác. Nó không cấm mọi trang web khởi tạo yêu cầu cross-origin. Form HTML và một số loại yêu cầu đơn giản vẫn có thể được gửi. CORS cũng chủ yếu điều khiển quyền đọc phản hồi và việc gửi các yêu cầu cần preflight; CORS không tự ngăn form cross-origin gửi một yêu cầu đơn giản.

Một CSRF thường cần đồng thời các điều kiện sau:

1. Trình duyệt có thông tin xác thực gắn với đích, chẳng hạn session cookie.
2. Trình duyệt tự gửi thông tin xác thực đó trong ngữ cảnh yêu cầu do trang khác khởi tạo.
3. Máy chủ chấp nhận yêu cầu mà không xác minh đầy đủ nguồn gốc hoặc ý định của người dùng.
4. Yêu cầu có thể gây ra thay đổi trạng thái hoặc hành động nhạy cảm.

CSRF không đồng nghĩa với XSS. CSRF lợi dụng quyền xác thực mà trình duyệt tự gửi; XSS cho phép mã không tin cậy chạy trong origin của ứng dụng. Một lỗ hổng XSS thường có thể vượt qua các biện pháp CSRF vì script cùng origin có thể đọc token và gửi yêu cầu hợp lệ. Do đó, CSRF defense cần đi cùng các biện pháp chống XSS như output encoding, CSP và Trusted Types.

## 2. Phân loại yêu cầu cần bảo vệ

Hãy lập danh sách endpoint trước khi viết middleware. Mọi yêu cầu có thể thay đổi trạng thái phải dùng phương thức không an toàn và đi qua kiểm tra CSRF khi xác thực bằng cookie.

| Nhóm yêu cầu | Ví dụ | Chính sách |
|---|---|---|
| Đọc dữ liệu | `GET /profile`, `GET /transfers` | Không tạo thay đổi trạng thái; không dùng CSRF token để hợp thức hóa thao tác ghi qua GET |
| Tạo hoặc cập nhật | `POST /transfers`, `PATCH /profile` | Bắt buộc xác thực CSRF |
| Xóa hoặc thay đổi quyền | `DELETE /devices/123`, `POST /users/123/roles` | Bắt buộc xác thực CSRF và kiểm tra quyền truy cập |
| Đăng xuất | `POST /logout` | Bảo vệ CSRF để trang khác không thể ép người dùng đăng xuất |
| Đăng nhập | `POST /login` | Cân nhắc login CSRF; dùng token trước xác thực và luân chuyển session sau đăng nhập |
| Callback từ nhà cung cấp | OAuth callback, thanh toán, webhook | Dùng cơ chế xác minh riêng của giao thức; không tạo ngoại lệ bỏ qua kiểm tra một cách tổng quát |

`GET`, `HEAD` và `OPTIONS` phải giữ ngữ nghĩa an toàn: không chuyển tiền, xóa dữ liệu, thay đổi email, cấp quyền hoặc đăng xuất. Nếu một endpoint ghi dữ liệu qua GET, trình duyệt, crawler, preview bot hoặc liên kết được nhúng có thể kích hoạt hành động đó mà không có ý định rõ ràng của người dùng. Đổi phương thức sang POST là bước cần thiết nhưng chưa đủ; POST vẫn phải được bảo vệ.

## 3. Thiết kế phòng vệ nhiều lớp

Một chính sách thực tế thường kết hợp các lớp sau:

| Lớp | Cách hoạt động | Vai trò và giới hạn |
|---|---|---|
| CSRF token | Máy chủ phát token khó đoán và kiểm tra token trong yêu cầu ghi | Lớp xác minh ý định chính cho ứng dụng dùng cookie phiên |
| `SameSite` cookie | Giới hạn ngữ cảnh cross-site được gửi cookie | Giảm bề mặt tấn công; không thay thế token, đặc biệt khi có subdomain cùng site hoặc luồng cross-site hợp lệ |
| `Origin`/`Referer` | So sánh origin nguồn với origin ứng dụng được cấu hình | Chặn yêu cầu có nguồn không tin cậy; phải so sánh origin chính xác |
| Fetch Metadata | Dựa trên `Sec-Fetch-Site` và các header liên quan | Nhận diện yêu cầu cross-site mà không cần suy đoán từ URL |
| Header tùy chỉnh và CORS chặt | Yêu cầu client gửi header như `X-CSRF-Token` | Khiến form HTML thông thường không thể tạo yêu cầu tương đương; CORS sai cấu hình vẫn có thể mở đường cho script khác origin |
| Kiểm soát phương thức và kiểu nội dung | Chỉ chấp nhận phương thức, content type đúng hợp đồng API | Giảm các đường gửi yêu cầu ngoài dự kiến; không phải lớp xác thực độc lập |

Token là lớp xác minh chính. `SameSite`, kiểm tra nguồn và Fetch Metadata bổ sung tín hiệu độc lập, giúp chặn sớm các yêu cầu giả mạo và phát hiện cấu hình sai.

### 3.1. Cấu hình cookie phiên

Với ứng dụng thông thường, cookie phiên nên có các thuộc tính:

```http
Set-Cookie: __Host-session=<opaque-value>; Path=/; Secure; HttpOnly; SameSite=Lax
```

- `Secure` chỉ gửi cookie qua HTTPS.
- `HttpOnly` ngăn JavaScript đọc trực tiếp giá trị cookie phiên.
- `SameSite=Lax` thường phù hợp với ứng dụng web có điều hướng từ liên kết bên ngoài nhưng không cần cookie trong phần lớn yêu cầu nhúng cross-site.
- Tiền tố `__Host-` yêu cầu cookie có `Secure`, `Path=/` và không có thuộc tính `Domain`; điều này giúp cookie chỉ thuộc host đã đặt nó.

`SameSite=Strict` hạn chế gửi cookie trong nhiều điều hướng bắt đầu từ site khác, nhưng có thể làm gián đoạn trải nghiệm quay lại ứng dụng sau đăng nhập liên kết ngoài. `SameSite=None` cho phép cookie được gửi trong ngữ cảnh cross-site và bắt buộc đi kèm `Secure`; chỉ dùng khi kiến trúc thực sự cần, chẳng hạn một số luồng nhúng hoặc tích hợp. Khi dùng `None`, token và kiểm tra nguồn càng quan trọng.

`SameSite` dựa trên khái niệm site, không phải origin. Hai host như `app.example.com` và `untrusted.example.com` có thể được xem là cùng site nhưng vẫn khác origin. Vì vậy, không được xem `Sec-Fetch-Site: same-site` hoặc cookie `SameSite` là bằng chứng rằng yêu cầu đến từ đúng ứng dụng. Hãy kiểm tra origin chính xác và giới hạn cookie bằng host phù hợp.

### 3.2. Synchronizer token pattern cho session phía máy chủ

Đây là lựa chọn phù hợp khi máy chủ quản lý session. Máy chủ tạo một token ngẫu nhiên bằng bộ sinh số ngẫu nhiên mật mã, gắn token với session đã xác thực và chỉ chấp nhận yêu cầu ghi khi client gửi lại token đó.

Luồng xử lý:

1. Sau khi tạo session, máy chủ sinh token đủ mạnh, ví dụ 32 byte ngẫu nhiên, rồi lưu token trong session.
2. Với trang HTML, máy chủ đặt token vào hidden input hoặc một phần dữ liệu trang chỉ origin của ứng dụng đọc được.
3. Với SPA, client lấy token qua endpoint cùng origin, ví dụ `GET /api/csrf-token`; phản hồi đặt `Cache-Control: no-store`.
4. Client gửi token trong hidden field hoặc header `X-CSRF-Token` khi thực hiện POST, PUT, PATCH hay DELETE.
5. Middleware lấy token từ đúng vị trí đã quy định, so sánh với token trong session và từ chối nếu thiếu hoặc không khớp.

Ví dụ form HTML:

```html
<form action="/profile/email" method="POST">
  <input type="hidden" name="_csrf" value="<token-do-may-chu-cap>">
  <input type="email" name="email" required>
  <button type="submit">Cập nhật email</button>
</form>
```

Ví dụ SPA gửi yêu cầu:

```javascript
const response = await fetch("/api/profile/email", {
  method: "PATCH",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": csrfToken
  },
  body: JSON.stringify({ email: "new@example.com" })
});
```

Token phải khó đoán, gắn với session và được kiểm tra ở máy chủ. Không dùng giá trị cố định, timestamp, user ID hay token chỉ được mã hóa bằng Base64. Không đặt token trong URL vì URL có thể xuất hiện trong lịch sử trình duyệt, log máy chủ hoặc header `Referer`. Không ghi token vào log. Với SPA, có thể giữ token trong bộ nhớ của ứng dụng; tránh lưu bền vững nếu không cần thiết.

Khi so sánh token, dùng phép so sánh an toàn thời gian nếu nền tảng cung cấp. Luân chuyển session ID và token sau đăng nhập, đăng xuất hoặc thay đổi mức đặc quyền. Không nhất thiết tạo token mới cho từng request: token theo session dễ triển khai với nhiều tab và thao tác quay lại trang. Nếu chọn token theo request, phải xử lý rõ trường hợp nhiều tab, gửi lại request và back/forward cache.

### 3.3. Double-submit cookie cho kiến trúc stateless

Nếu máy chủ không lưu trạng thái CSRF trong session, có thể dùng double-submit cookie. Máy chủ đặt một token trong cookie và yêu cầu client gửi cùng giá trị đó trong header hoặc body. Máy chủ so sánh hai giá trị.

Ví dụ:

```http
Set-Cookie: __Host-csrf=<nonce.signature>; Path=/; Secure; SameSite=Lax
```

Client đọc cookie CSRF (cookie này không đặt `HttpOnly` nếu JavaScript cần đọc) và gửi lại trong `X-CSRF-Token`. Máy chủ kiểm tra giá trị header trùng với cookie, đồng thời xác minh chữ ký HMAC của token. Chữ ký nên ràng buộc nonce với session hoặc ngữ cảnh xác thực bằng khóa bí mật chỉ máy chủ biết.

Không dùng double-submit ngây thơ chỉ so sánh hai chuỗi nếu kẻ tấn công có khả năng đặt cookie qua subdomain không tin cậy, cookie injection hoặc một đường ghi cookie khác. Khi đó, kẻ tấn công có thể chọn trước giá trị cookie và gửi cùng giá trị trong yêu cầu giả mạo. Token có chữ ký và ràng buộc với session làm giảm rủi ro này. Cookie `__Host-` cần được đặt đúng các điều kiện `Secure`, `Path=/` và không có `Domain`.

Double-submit và synchronizer token là hai thiết kế khác nhau. Chọn một cách có chủ đích theo khả năng lưu session, cách client lấy token và mô hình tin cậy của domain. Không phát token ở cookie rồi cho rằng chỉ riêng cookie đó đã chống được CSRF.

### 3.4. Kiểm tra Origin và Referer

Với yêu cầu ghi từ trình duyệt, kiểm tra header `Origin` và dùng `Referer` làm phương án dự phòng khi `Origin` không có. So sánh bộ ba scheme, host và port với origin chính thức đã cấu hình, ví dụ `https://bank.example.com`.

Quy tắc kiểm tra:

- Phân tích header bằng bộ phân tích URL chuẩn, sau đó so sánh origin đã chuẩn hóa.
- Từ chối origin không khớp, origin `null` và các giá trị không phân tích được.
- Không dùng kiểm tra chuỗi con như `endsWith("example.com")`, `includes("bank.example.com")` hoặc so khớp prefix. Các cách này dễ chấp nhận host giả như `bank.example.com.attacker.net`.
- Không lấy origin kỳ vọng trực tiếp từ header `Host` hoặc `X-Forwarded-Host` do client gửi. Dùng cấu hình đáng tin cậy; nếu đứng sau reverse proxy, chỉ tin header do proxy được kiểm soát ghi lại.
- Nếu cả `Origin` và `Referer` đều vắng mặt trên endpoint trình duyệt dùng cookie phiên, chính sách nghiêm ngặt nên từ chối. Nếu cần hỗ trợ client không phải trình duyệt, hãy thiết kế cơ chế xác thực riêng cho client đó thay vì mở rộng ngoại lệ cho endpoint cookie.

`Referer` có thể bị rút gọn hoặc loại bỏ bởi chính sách riêng tư. Vì vậy, kiểm tra nguồn không thay thế CSRF token. Cần xác định rõ hành vi khi thiếu header và kiểm thử trên các trình duyệt, proxy và luồng điều hướng mà sản phẩm hỗ trợ.

### 3.5. Dùng Fetch Metadata

Trình duyệt hiện đại có thể gửi các header như:

```http
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
```

`Sec-Fetch-Site` cho biết quan hệ giữa origin khởi tạo và đích: `same-origin`, `same-site`, `cross-site` hoặc `none`. Với endpoint thay đổi trạng thái dùng cookie, có thể từ chối ngay yêu cầu có `Sec-Fetch-Site: cross-site`. Với `same-site`, vẫn cần kiểm tra `Origin` vì subdomain khác có thể không đáng tin cậy. Với `none` hoặc khi header vắng mặt, áp dụng chính sách tương thích đã xác định; không mặc định coi đó là yêu cầu an toàn.

Fetch Metadata là lớp bổ sung vì không phải mọi client đều gửi header này. Client cũ, công cụ tự động hoặc một số luồng đặc biệt có thể không có. Token và kiểm tra nguồn vẫn là nền tảng.

## 4. Middleware kiểm tra CSRF

Đặt kiểm tra ở lớp dùng chung trước khi controller thực hiện tác dụng phụ. Mọi đường vào cùng một thao tác ghi phải đi qua chính sách này, kể cả route HTML, API, tác vụ quản trị và endpoint phụ.

Pseudocode cho ứng dụng dùng session cookie và synchronizer token:

```text
SAFE_METHODS = { GET, HEAD, OPTIONS }

csrfGuard(request):
    if request.method in SAFE_METHODS:
        continue

    session = requireAuthenticatedSession(request)

    if request.header("Sec-Fetch-Site") == "cross-site":
        reject(403)

    source = request.header("Origin")
    if source is absent:
        source = originOf(request.header("Referer"))

    if source is absent or source != CONFIGURED_APP_ORIGIN:
        reject(403)

    suppliedToken = request.header("X-CSRF-Token")
    if suppliedToken is absent and request.isHtmlForm:
        suppliedToken = request.formField("_csrf")

    if suppliedToken is absent:
        reject(403)

    if not constantTimeEqual(suppliedToken, session.csrfToken):
        reject(403)

    continue
```

Đây là logic minh họa; khi triển khai cần dùng API session, request parser và phép so sánh an toàn của framework đang dùng. Chỉ đọc token từ những vị trí được hợp đồng endpoint cho phép. Không tự động chấp nhận token từ query string. Middleware phải chạy sau bước có thể đọc body form nhưng trước mọi thay đổi trạng thái. Với JSON API, ưu tiên header tùy chỉnh để tránh phải phân tích body chỉ nhằm tìm token.

Đừng bỏ qua CSRF theo tên phương thức hoặc URL một cách rộng. Nếu một route thực sự là callback từ hệ thống ngoài, xác minh chữ ký, state, nonce hoặc bằng chứng giao thức tương ứng tại route đó. Ghi rõ lý do ngoại lệ, giới hạn chính xác endpoint và có kiểm thử riêng.

## 5. CORS và header tùy chỉnh trong SPA

SPA dùng cookie phiên có thể yêu cầu mọi request ghi gửi `X-CSRF-Token`. Một form HTML cross-origin không thể tự đặt header tùy chỉnh này. Một script cross-origin muốn gửi header đó sẽ cần CORS preflight; máy chủ chỉ cho phép origin đáng tin cậy.

Ví dụ cấu hình CORS cho một frontend cụ thể:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Vary: Origin
```

Khi bật credentials, không dùng `Access-Control-Allow-Origin: *`. Chỉ phản hồi với origin nằm trong allowlist được cấu hình, không phản chiếu tùy ý giá trị `Origin` do client gửi. Giới hạn method và header theo nhu cầu thật.

Header tùy chỉnh và CORS chặt giúp bảo vệ API browser-based, nhưng không biến CORS thành cơ chế CSRF duy nhất. CORS không ngăn mọi yêu cầu đơn giản; form có thể gửi `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`. Nếu endpoint chỉ nhận JSON, hãy kiểm tra chính xác `Content-Type` và từ chối các kiểu không hỗ trợ. Tuy nhiên, kiểm tra content type cũng chỉ là lớp phụ: token và kiểm tra nguồn vẫn cần thiết.

Nếu API chỉ xác thực bằng bearer token trong header `Authorization` và trình duyệt không tự đính kèm token đó, rủi ro CSRF kiểu cookie giảm đáng kể. Khi đó, cần quản lý token và chống XSS cẩn thận. Nếu bearer token được đặt trong cookie, nó lại trở thành thông tin xác thực tự động gửi và cần CSRF defense.

## 6. Các luồng đặc biệt

### Đăng nhập và đăng xuất

Login CSRF có thể khiến nạn nhân bị đăng nhập vào tài khoản do kẻ tấn công kiểm soát. Nếu ứng dụng có form đăng nhập dựa trên cookie, hãy cấp token cho phiên chưa xác thực hoặc một trạng thái pre-authentication. Sau đăng nhập, tạo session ID mới và token mới để tránh session fixation. Endpoint đăng xuất nên dùng POST và kiểm tra CSRF.

### OAuth và đăng nhập liên kết

OAuth callback là một luồng có chuyển hướng qua domain của nhà cung cấp. Không bỏ qua CSRF cho toàn bộ callback hoặc toàn bộ nhóm `/auth/*`. Dùng `state` ngẫu nhiên, ràng buộc với giao dịch đăng nhập của trình duyệt, xác minh chính xác khi callback quay lại; dùng PKCE cho authorization code flow và kiểm tra redirect URI chính xác. Nếu có OIDC, xác minh thêm `nonce` theo luồng đã thiết kế. Kiểm thử cả callback GET lẫn POST tùy response mode.

### Thanh toán và webhook

Webhook server-to-server thường không dùng session cookie của người dùng. Xác minh chữ ký trên raw request body, timestamp và cơ chế chống replay theo tài liệu nhà cung cấp. Callback thanh toán chạy trong trình duyệt lại là một loại luồng khác: không tin dữ liệu do browser gửi để xác nhận thanh toán; đối chiếu trạng thái giao dịch ở máy chủ với nhà cung cấp.

## 7. Kiểm thử chính sách

Hãy kiểm thử bằng hai origin: ứng dụng hợp lệ và một trang giả mạo. Dùng tài khoản thử nghiệm, dữ liệu có thể khôi phục và kiểm tra cả phản hồi HTTP lẫn trạng thái cuối cùng trong cơ sở dữ liệu.

| Tình huống | Kỳ vọng |
|---|---|
| POST cùng origin có session và token hợp lệ | Được chấp nhận nếu người dùng có quyền |
| POST thiếu token | Bị từ chối với `403` hoặc lỗi CSRF tương đương |
| POST có token sai hoặc token của session khác | Bị từ chối |
| Form từ origin tấn công gửi POST kèm cookie phiên | Bị từ chối; không có thay đổi trạng thái |
| Yêu cầu có `Origin` không khớp | Bị từ chối |
| Yêu cầu cross-site có `Sec-Fetch-Site: cross-site` | Bị từ chối trên endpoint ghi dùng cookie |
| Yêu cầu ghi dùng `GET` | Không tồn tại hoặc không gây thay đổi trạng thái |
| SPA gửi header token với CORS origin hợp lệ | Được xử lý theo xác thực và phân quyền |
| Script từ origin không nằm trong allowlist gửi preflight | Preflight không được cấp quyền; request ghi không được thực hiện |
| Session được tạo mới sau đăng nhập | Session ID và CSRF token cũ không còn được chấp nhận |
| Origin và Referer cùng vắng mặt | Theo chính sách đã định; endpoint browser dùng cookie nên từ chối |

Kiểm thử thêm các tình huống biên: hai tab cùng session, token hết hạn, back/forward, session timeout, subdomain không tin cậy, trình duyệt không gửi Fetch Metadata, reverse proxy và luồng đăng nhập từ nhà cung cấp ngoài. Một bài kiểm thử chỉ xác nhận status `403` là chưa đủ; cần xác minh hành động nhạy cảm thực sự không xảy ra.

## 8. Vận hành và xử lý sự cố

Ghi nhận số lượng yêu cầu bị từ chối theo endpoint và lý do như thiếu token, token không hợp lệ, origin không khớp hoặc Fetch Metadata báo cross-site. Không ghi cookie phiên, CSRF token hay dữ liệu nhạy cảm vào log. Theo dõi tỷ lệ từ chối tăng đột biến sau khi thay đổi domain, proxy, cookie hoặc luồng đăng nhập để phát hiện cấu hình sai.

Khi triển khai trên hệ thống đang hoạt động, có thể thu thập log chẩn đoán cho các kiểm tra nguồn và Fetch Metadata trước khi bật chặn nếu cần đánh giá tương thích. CSRF token trên endpoint ghi phải được thực thi trước khi endpoint gây tác dụng phụ. Khi chuyển sang enforcement, kiểm tra dashboard lỗi và các luồng tích hợp quan trọng. Không tạo chế độ bỏ qua toàn cục chỉ để khắc phục một callback cụ thể.

CSRF defense cũng cần được xem lại khi thêm subdomain, frontend mới, iframe, SSO, cổng thanh toán, reverse proxy hoặc cơ chế xác thực mới. Mỗi thay đổi có thể làm đổi origin tin cậy, cách cookie được gửi hoặc đường đi của request.

## 9. Bài thực hành tổng hợp

Thiết kế phòng vệ cho ứng dụng quản lý tài khoản có các chức năng cập nhật email, đổi mật khẩu, tạo API key, chuyển tiền và đăng xuất. Ứng dụng có giao diện HTML cho một số trang, một SPA cùng origin gọi JSON API và dùng session cookie.

Thực hiện các bước sau:

1. Liệt kê endpoint và phân loại phương thức an toàn/không an toàn. Chuyển mọi thao tác ghi đang dùng GET sang phương thức phù hợp.
2. Chọn thuộc tính cookie phiên. Giải thích lựa chọn `Lax`, `Strict` hoặc `None` dựa trên luồng điều hướng thực tế.
3. Chọn synchronizer token hay signed double-submit cho từng nhóm endpoint; mô tả cách cấp, lưu, gửi, kiểm tra và luân chuyển token.
4. Viết chính sách kiểm tra `Origin`/`Referer` và `Sec-Fetch-Site`, bao gồm cách xử lý header vắng mặt và subdomain.
5. Định nghĩa CORS allowlist cho SPA, method và header được phép. Chứng minh vì sao CORS không thay thế token.
6. Xác định cách bảo vệ login, logout, OAuth callback và webhook mà không tạo ngoại lệ quá rộng.
7. Viết test case cho ít nhất các tình huống trong bảng kiểm thử và xác minh không có thay đổi dữ liệu khi yêu cầu bị từ chối.

**Sản phẩm cần bàn giao:** sơ đồ luồng request, bảng endpoint và chính sách, cấu hình cookie/CORS mẫu, pseudocode middleware, cùng kết quả kiểm thử dương tính và âm tính.

### Tiêu chí hoàn thành

- Mọi endpoint thay đổi trạng thái dùng cookie phiên đều đi qua một chính sách CSRF thống nhất.
- Token có entropy đủ mạnh, gắn với phiên hoặc được ký và ràng buộc đúng; token thiếu/sai đều bị từ chối.
- Cookie có thuộc tính phù hợp; chính sách SameSite được giải thích theo luồng sản phẩm.
- Origin được so sánh chính xác; Fetch Metadata và CORS được dùng đúng vai trò.
- Không có thao tác ghi qua GET hoặc ngoại lệ bỏ qua kiểm tra không có lý do rõ ràng.
- Bộ kiểm thử chứng minh cả yêu cầu hợp lệ lẫn yêu cầu giả mạo và kiểm tra trạng thái dữ liệu sau phản hồi.

Một thiết kế tốt phải trả lời được ba câu hỏi cho từng endpoint: trình duyệt gửi thông tin xác thực nào, điều gì chứng minh yêu cầu xuất phát từ ứng dụng hợp lệ, và máy chủ từ chối yêu cầu ở đâu trước khi có tác dụng phụ. Khi ba câu trả lời này rõ ràng và được kiểm thử, CSRF defense có thể được duy trì như một chính sách nhất quán thay vì một tập hợp ngoại lệ rời rạc.
