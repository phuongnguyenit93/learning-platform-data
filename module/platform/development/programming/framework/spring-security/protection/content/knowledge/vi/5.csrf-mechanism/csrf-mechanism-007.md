# Phân biệt CSRF token với session ID và access token

## Mục tiêu học tập

Sau bài học thuộc chương **Cơ chế CSRF**, người học có thể:

- Giải thích chính xác ba khái niệm **CSRF token**, **session ID** và **access token** theo chức năng, bên phát hành, bên sử dụng và cách truyền trong HTTP.
- Trả lời ba câu hỏi riêng biệt: **Phiên nào đang gửi yêu cầu?**, **Yêu cầu được phép truy cập tài nguyên nào?**, và **Yêu cầu thay đổi trạng thái này có đáp ứng cơ chế phòng vệ CSRF không?**
- Phân biệt **credential mà trình duyệt tự gửi** với giá trị do một form hoặc JavaScript **chủ động gửi**; hiểu vì sao vị trí lưu/truyền token ảnh hưởng đến nguy cơ CSRF.
- Phân tích các trường hợp access token dạng JWT nằm trong cookie, access token trong header `Authorization`, session cookie và CSRF token trong form/header.
- Không nhầm CSRF token với **cookie xác thực**, token làm mới (`refresh token`), `OAuth state`, hoặc token chống gửi trùng.
- Áp dụng đúng khái niệm khi cấu hình Spring Security **Servlet** và **Reactive/WebFlux** và khi giải thích kết quả kiểm thử `401`/`403`.
- Nhận biết các lỗi thiết kế như dùng session ID làm CSRF token, dùng access token làm CSRF token, đưa secret vào URL hoặc vô hiệu hóa CSRF chỉ vì API được gọi là “JWT/stateless”.

## 1. Ba loại token, ba câu hỏi bảo mật

Giả sử một ứng dụng có endpoint cập nhật địa chỉ giao hàng:

~~~http
POST /account/shipping-address HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SID_A
Content-Type: application/x-www-form-urlencoded

city=HaNoi
~~~

**Session ID** như `SID_A` giúp server tra một phiên đã đăng nhập, chẳng hạn người dùng Alice. Từ phiên này, máy chủ có thể tìm được thông tin về tài khoản, quyền và dữ liệu của phiên.

Trong một kiến trúc khác, API có thể yêu cầu **access token**:

~~~http
PATCH /api/account/shipping-address HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...
Content-Type: application/json

{"city":"HaNoi"}
~~~

Access token là credential mà tài nguyên/API kiểm tra để quyết định có thể xử lý request dưới phạm vi quyền nào. Đối với OAuth 2.0, nó đại diện cho quyền truy cập đã được cấp cho một client theo các scope/claim và chính sách của resource server. Trong triển khai riêng, ứng dụng cũng có thể gọi token dùng cho API của mình là access token.

Cả hai trường hợp vẫn chưa trực tiếp giải đáp: **một request làm thay đổi trạng thái có được trang ứng dụng hợp lệ khởi tạo theo cơ chế chống CSRF hay không?** Nếu trình duyệt có thể tự gửi cookie xác thực trên request do website khác kích hoạt, máy chủ có thể nhận diện đúng người dùng mà vẫn xử lý thao tác giả mạo.

**CSRF token** là giá trị bổ sung để kiểm tra tính hợp lệ của những request như vậy. Nó được client hợp lệ gửi qua **trường form hoặc HTTP header** và được server kiểm chứng theo token dự kiến/ngữ cảnh phù hợp.

> **Ba vai trò không hoán đổi được:** Session ID nhận diện **phiên**; access token cấp/đại diện **quyền gọi API**; CSRF token hỗ trợ xác minh **nguồn hợp lệ của request thay đổi trạng thái** khi trình duyệt tự gửi credential.

CSRF token không chứng minh tuyệt đối “người dùng đã bấm nút”. Nó ngăn một mô hình tấn công cụ thể: trang bên ngoài có thể khiến browser phát request nhưng thường không đọc được token mà ứng dụng phát hành trong origin tin cậy. Nếu có XSS chạy ngay tại origin đích, kẻ tấn công có thể đọc/sử dụng token.

~~~mermaid
flowchart LR
    B[Trình duyệt / HTTP client] -->|Cookie session ID| S[Tra phiên người dùng]
    B -->|Authorization Bearer access token| A[Kiểm tra quyền truy cập API]
    B -->|Form hoặc header CSRF token| C[Kiểm chứng CSRF token]
    S --> D[Kiểm tra bảo mật và xử lý yêu cầu]
    A --> D
    C --> D
~~~

Sơ đồ biểu diễn **ba chức năng**, không có nghĩa mỗi request bắt buộc sử dụng đồng thời cả ba loại token. Một ứng dụng session-based thường dùng session ID và CSRF token; một API bearer-only có thể không sử dụng session cookie.

## 2. Bảng so sánh tổng quát

| Tiêu chí | Session ID | Access token | CSRF token |
|---|---|---|---|
| **Mục đích chính** | Tra cứu hoặc định danh phiên người dùng/ứng dụng | Chứng minh quyền truy cập API/tài nguyên theo mô hình xác thực/ủy quyền | Kiểm tra request thay đổi trạng thái có mang giá trị do luồng hợp lệ cung cấp |
| **Bên phát hành** | Hệ thống quản lý phiên | Authorization server hoặc hệ thống phát credential cho API | Ứng dụng/cơ chế bảo vệ CSRF |
| **Bên kiểm tra** | Session infrastructure, authentication/security context | Resource server hoặc tầng xác thực token | CSRF filter/repository/request handler |
| **Quan hệ với người dùng** | Gắn với **một phiên**, thường chứa ngữ cảnh đã xác thực | Có thể đại diện người dùng, client, hoặc quyền ủy quyền; tùy luồng | Thường gắn với **phiên/ngữ cảnh** cần bảo vệ, hoặc được xác minh theo chính sách cookie/token |
| **Hình thức điển hình** | Chuỗi khó đoán, ví dụ cookie `JSESSIONID`/`SESSION` | Chuỗi opaque hoặc JWT; không bắt buộc là JWT | Chuỗi ngẫu nhiên, có thể được mask hoặc ký tùy mô hình |
| **Cách gửi thường gặp** | Cookie do browser tự đính kèm | Header `Authorization: Bearer ...`; cũng có ứng dụng đặt trong cookie | Hidden field `_csrf` hoặc header `X-CSRF-TOKEN`/`X-XSRF-TOKEN` |
| **Bí mật cần bảo vệ?** | **Có, rất nhạy cảm** vì nắm được SID hợp lệ có thể chiếm phiên | **Có, rất nhạy cảm** vì ai cầm bearer token hợp lệ có thể dùng quyền của nó | **Có**, để không bị trang ngoài lấy/đoán; nhưng không phải credential đăng nhập độc lập |
| **Hết hạn/vô hiệu hóa** | Theo vòng đời phiên; thay session ID, logout, timeout | Theo `exp`/thời hạn, thu hồi, chính sách phát hành và kiểm chứng | Theo vòng đời repository/phiên và các sự kiện như đăng nhập, đăng xuất, thay token |
| **Có tự chống CSRF?** | **Không** | **Không theo bản chất token**; cách vận chuyển có thể khiến CSRF khó/khả thi | Là thành phần **trực tiếp của cơ chế chống CSRF** |
| **Có thay thế xác thực/phân quyền?** | Có thể tham gia nhận diện ngữ cảnh xác thực; bản thân chuỗi không phải kiểm tra quyền nghiệp vụ | Là credential dùng khi kiểm tra xác thực/phạm vi quyền của API | **Không** |

Một chuỗi có thể đều được gọi là “token”, nhưng **tên gọi không quyết định công dụng**. Phải xác định rõ nó được phát ra từ đâu, được client gửi bằng cách nào, server kiểm chứng điều gì và quyền nào được cấp sau khi kiểm chứng.

## 3. Session ID: khóa tra cứu phiên, không phải token CSRF

### 3.1. Session ID hoạt động như thế nào?

Với một ứng dụng server-rendered sử dụng Spring MVC và servlet session, quá trình thường gồm:

1. Browser gửi thông tin đăng nhập đến ứng dụng.
2. Sau khi xác thực, ứng dụng duy trì ngữ cảnh của người dùng trong cơ chế quản lý phiên.
3. Browser được gắn session cookie, thường là `JSESSIONID` ở Servlet container, tùy cấu hình.
4. Ở request sau, browser **tự chọn và gửi cookie** nếu hostname, đường dẫn, giao thức và chính sách cookie phù hợp.
5. Server dùng session ID để tìm session, rồi tra thông tin xác thực/quyền theo cơ chế Spring Security đang dùng.

Minh họa:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=sid-random-opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

~~~http
GET /profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=sid-random-opaque
~~~

`Secure` giới hạn truyền cookie trên kết nối an toàn phù hợp; `HttpOnly` ngăn JavaScript thông thường đọc cookie bằng `document.cookie`; `SameSite` hạn chế một số ngữ cảnh cross-site. **Các thuộc tính này không biến session cookie thành CSRF token.**

### 3.2. Vì sao session ID không chứng minh ý định gửi request?

Một website ngoài có thể gây ra request đến ứng dụng bằng HTML form, liên kết hoặc điều hướng. Browser vẫn có thể tự gửi session cookie đến ứng dụng đích **nếu chính sách cookie cho phép request đó**. Website ngoài không cần biết chuỗi session ID để tạo request mang session của nạn nhân.

Một ví dụ kịch bản phụ thuộc điều kiện cookie:

~~~html
<form method="post" action="https://app.example.com/profile/email">
  <input type="hidden" name="email" value="attacker@example.test">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Nếu request mang session cookie và server không yêu cầu CSRF token, thao tác đổi email có thể bị thực hiện dưới danh tính nạn nhân.

Lưu ý: cookie `SameSite=Lax` thường **không** được gửi trong cross-site form POST. Không thể khẳng định mọi form từ website khác đều khai thác được. Muốn xác nhận cần xem cookie thực sự có mặt trong request, endpoint có chấp nhận request đó và server có kiểm tra CSRF hay không. Các trường hợp `SameSite=None; Secure`, request same-site cross-origin hoặc các ngoại lệ/chính sách trình duyệt khác cần được đánh giá riêng.

### 3.3. Dùng session ID làm CSRF token có an toàn không?

**Không nên.** Có hai vấn đề độc lập:

- **Chuyển một credential xác thực sang vị trí dễ lộ:** Nếu server render `JSESSIONID` vào hidden field, HTML/DOM và các cơ chế ghi nhận request có thể làm lộ session ID. Kẻ tấn công lấy được session ID có thể trực tiếp chiếm quyền phiên nếu không có bảo vệ bổ sung.
- **Không tách biệt mục đích và vòng đời:** Session ID là credential để xác thực phiên; CSRF token cần một cơ chế phát hành/kiểm chứng chuyên dụng. Trộn chúng làm khó cô lập bí mật, luân phiên giá trị và chẩn đoán sự cố.

Ví dụ **không được áp dụng**:

~~~html
<!-- Thiết kế sai: làm lộ session ID như một CSRF token -->
<input type="hidden" name="_csrf" value="JSESSIONID_VALUE">
~~~

Một CSRF token theo session nên được sinh **độc lập và khó đoán**, lưu gắn với session phía server, rồi đưa một biểu diễn của token vào form/header. Không được lấy session ID thô làm giá trị được public cho form.

### 3.4. Session fixation khác CSRF

**Session fixation** là tình huống kẻ tấn công khiến nạn nhân sử dụng một định danh phiên mà attacker đã biết/kiểm soát; sau khi nạn nhân đăng nhập, kẻ tấn công có thể lợi dụng phiên đó trong một số cấu hình yếu. Phòng vệ thường liên quan đến **đổi session ID khi xác thực**, tránh nhận session ID không đáng tin cậy và quản lý cookie/session đúng cách.

**CSRF** lợi dụng việc browser tự gửi credential cho một request không được người dùng chủ động tạo từ ứng dụng. Đổi session ID khi đăng nhập là cần thiết cho một số mối đe dọa, nhưng **không thay thế CSRF token** trên các request thay đổi trạng thái.

## 4. Access token: credential cho API, không mặc nhiên là CSRF token

### 4.1. Access token không bắt buộc là JWT

Một access token có thể có dạng:

- **Opaque token:** Chuỗi không cần mang dữ liệu có thể đọc/giải mã từ phía client; resource server xác minh theo cơ chế phù hợp (chẳng hạn introspection).
- **JWT access token:** Token có cấu trúc JSON Web Token và được ký, chứa các claim như `iss`, `aud`, `exp`, `scope`/`scp` tùy hệ thống.

Cả hai đều là **credential cho API**. Chữ ký JWT (nếu có) chỉ cho phép bên kiểm chứng xác định tính toàn vẹn/nguồn phát hành và các điều kiện claim; nó **không tự đảm bảo request HTTP không bị CSRF**.

Ví dụ token được gửi qua header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Resource server kiểm tra token theo cấu hình rồi xác định quyền truy cập. Token có thể đại diện cho một người dùng, một service/client hoặc một phiên ủy quyền; không nhất thiết mọi access token đều gắn với một browser session.

### 4.2. Điểm mấu chốt: ai đặt access token vào HTTP request?

**Trường hợp A — client chủ động gắn Bearer header:**

~~~javascript
const accessToken = getAccessTokenFromTrustedClientState();

await fetch("/api/orders", {
  method: "POST",
  headers: {
    "Authorization": "Bearer " + accessToken,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ productId: "P123", quantity: 1 })
});
~~~

Trong mô hình này, browser **không tự gắn** access token của ứng dụng vào mọi form/điều hướng; chính mã client hợp lệ thêm header `Authorization`. Một website ngoài thường không có token để làm như vậy, và form HTML không tự tạo header bearer.

**Kết luận có điều kiện:** Nếu API **chỉ** chấp nhận credential này, không có cookie/session/Basic hoặc credential tự gửi nào khác được chấp nhận, nguy cơ **CSRF truyền thống dựa trên credential tự gửi** thường thấp hơn. Tuy nhiên vẫn phải bảo vệ khỏi XSS, đánh cắp bearer token, CORS cấu hình sai, cấp quyền quá rộng và các đường xác thực khác.

**Trường hợp B — cùng access token nhưng được đặt trong cookie:**

~~~http
HTTP/1.1 200 OK
Set-Cookie: ACCESS_TOKEN=jwt-or-opaque-value; Path=/; Secure; HttpOnly; SameSite=None
~~~

Nếu API kiểm tra cookie `ACCESS_TOKEN` làm credential, trình duyệt có thể **tự gửi cookie** trên request đủ điều kiện. Khi đó một trang ngoài có thể kích hoạt request mang credential, ngay cả khi token bên trong cookie là JWT hợp lệ được ký.

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Cookie: ACCESS_TOKEN=jwt-or-opaque-value
Content-Type: application/x-www-form-urlencoded

productId=P123&quantity=1
~~~

Khi cookie được gửi và endpoint chấp nhận request đơn giản có tác động, **nguy cơ CSRF vẫn tồn tại nếu không có bảo vệ thích hợp**. `HttpOnly` ngăn JavaScript đọc cookie nhưng không ngăn browser tự gửi nó.

> **Không kết luận “API dùng JWT là không cần CSRF”.** Hỏi chính xác: *Token được browser tự gửi bằng cookie hay được mã client chủ động thêm vào header? Backend chấp nhận những đường xác thực nào?*

### 4.3. “Stateless” không đồng nghĩa “CSRF-free”

Một ứng dụng có thể không lưu `HttpSession`, chỉ kiểm chứng chữ ký JWT từ cookie và gọi kiến trúc đó là **stateless**. Điều này mô tả **cách server quản lý trạng thái xác thực**, không thay đổi việc browser tự đính kèm cookie.

| Kiến trúc | Credential thực tế | Cần đánh giá CSRF? |
|---|---|---|
| Spring MVC dùng session cookie | `JSESSIONID` gửi tự động | **Có**, nhất là request thay đổi trạng thái |
| WebFlux dùng WebSession cookie | `SESSION` hoặc cookie theo cấu hình gửi tự động | **Có** |
| REST API kiểm chứng JWT từ cookie | Cookie chứa access token gửi tự động | **Có** |
| REST API chỉ nhận bearer token trong `Authorization` do client gắn | Không có credential browser tự gửi | **Thường không chịu CSRF kiểu cookie**, sau khi xác minh mọi đường xác thực |
| API chấp nhận đồng thời `Authorization` và cookie | Ít nhất một đường xác thực tự gửi | **Có**, đối với đường dùng cookie |
| API dùng HTTP Basic được browser lưu/tự gắn | Browser có thể tự mang credential | **Cần đánh giá** theo hành vi browser và server |

Khả năng **không** bị CSRF truyền thống trong kiến trúc bearer-header **không có nghĩa nên dùng localStorage làm nơi lưu access token**. Token có thể bị lấy qua XSS nếu được lưu ở nơi script truy cập. Lựa chọn kiến trúc phải cân nhắc đồng thời CSRF, XSS, quản lý phiên, thời hạn và cách thu hồi token.

### 4.4. Resource server vẫn phải kiểm chứng access token

Dù lựa chọn chống CSRF như thế nào, resource server vẫn cần kiểm tra access token: nguồn phát hành, chữ ký/khả năng xác minh, thời hạn, audience, scope/authority, chính sách quyền và trạng thái thu hồi nếu áp dụng.

CSRF token **không** thể thay các kiểm tra này. Một request có CSRF token hợp lệ nhưng không có access token được API yêu cầu vẫn không có quyền truy cập. Ngược lại, access token hợp lệ gửi trong cookie vẫn không thay CSRF token ở mô hình dựa trên cookie.

## 5. CSRF token: bằng chứng bổ sung cho request thay đổi trạng thái

### 5.1. Cơ chế đồng bộ theo phiên

Một cơ chế phổ biến là **Synchronizer Token Pattern**:

1. Ứng dụng phát một token ngẫu nhiên độc lập với session ID.
2. Server lưu token kỳ vọng trong `HttpSession` hoặc `WebSession`.
3. Trang hợp lệ lấy biểu diễn token qua HTML hoặc một kênh phù hợp.
4. Khi gửi `POST`, `PUT`, `PATCH`, `DELETE`, client chủ động đưa token vào form parameter hoặc header.
5. Spring Security so token gửi lên với expected token của **đúng phiên request** và từ chối nếu thiếu/sai.

Minh họa:

~~~text
Session A:
    sessionId = SID_A      <-- credential xác thực/tra phiên (browser gửi cookie)
    principal = Alice
    csrfToken = CSRF_A     <-- token kỳ vọng lưu phía server

GET /profile/edit (dùng SID_A)
    Trả HTML form chứa CSRF_A hoặc dạng masked của CSRF_A

POST /profile/email (dùng SID_A)
    Cookie: JSESSIONID=SID_A
    Form: _csrf=CSRF_A
    Server: submitted khớp expected của Session A --> qua bước CSRF
~~~

Nếu request mang cookie `SID_A` nhưng CSRF token `CSRF_B` của phiên khác, server phải từ chối. Việc attacker mở một phiên riêng để lấy CSRF token của họ **không** được giúp họ gửi request hợp lệ cho phiên nạn nhân.

### 5.2. Token theo cookie (double-submit) có khác session ID không?

Một số ứng dụng SPA sử dụng một cookie **dành riêng cho CSRF**, thường tên `XSRF-TOKEN`. JavaScript cùng origin đọc giá trị này và gửi lại qua header `X-XSRF-TOKEN`.

~~~http
POST /api/preferences HTTP/1.1
Cookie: ACCESS_TOKEN=...; XSRF-TOKEN=csrf-value
X-XSRF-TOKEN: csrf-value
Content-Type: application/json

{"theme":"dark"}
~~~

Có hai cookie ở đây với **hai mục đích**:

- `ACCESS_TOKEN` là credential xác thực, có thể được browser tự đính kèm.
- `XSRF-TOKEN` là dữ liệu tham gia **kiểm chứng CSRF**; client còn phải gửi bản sao **chủ động** qua header.

Một repository kiểu double-submit đơn giản chỉ so bản sao cookie và header. Vì token cookie có thể chịu **cookie injection** trong một số cấu hình domain/subdomain, giải pháp mạnh có thể dùng **HMAC ký và ràng buộc token vào phiên**. Không nhầm một `CookieCsrfTokenRepository` tiêu chuẩn với việc server đã tự kiểm chứng HMAC gắn phiên.

**Cookie CSRF không phải session cookie** dù cả hai đều là cookie; chức năng và quy tắc kiểm chứng của chúng hoàn toàn khác.

### 5.3. Vì sao CSRF token không phải credential đăng nhập?

Một attacker biết một CSRF token **không tự động** có được session hoặc access token tương ứng. Nếu họ chỉ gửi:

~~~http
POST /profile/email HTTP/1.1
X-CSRF-TOKEN: A_VALID_CSRF_TOKEN
Content-Type: application/json

{"email":"attacker@example.test"}
~~~

mà không có phiên hoặc credential xác thực phù hợp, CSRF token không cho họ đặc quyền đổi email cho Alice. **Token CSRF hợp lệ chỉ vượt qua một bước kiểm tra; xác thực và phân quyền vẫn là trách nhiệm riêng.**

Tuy nhiên, để giảm nguy cơ kẻ tấn công phối hợp với một phiên đã được tự gửi, CSRF token vẫn cần bảo vệ khỏi bị lộ qua XSS, URL, log hoặc chia sẻ nhầm với bên thứ ba.

### 5.4. Token không nhất thiết có cùng định dạng khi phát và khi kiểm chứng

Trong các cấu hình Spring Security hiện đại, request handler có thể **mask token bằng XOR** khi đưa ra HTML nhằm giảm một số kênh rò rỉ khi nén phản hồi (BREACH). Client gửi lại giá trị đã mask; handler giải mã về token gốc rồi so với expected token.

~~~text
Raw CSRF token lưu trong session: R

Render form lần 1 --> masked(R, random1) = M1
Render form lần 2 --> masked(R, random2) = M2

M1 khác M2 nhưng vẫn có thể đại diện cho cùng R.
Handler giải mã M1 hoặc M2 trước khi xác minh R.
~~~

Điều đó **không** biến token CSRF thành session ID, không tạo access token, và không có nghĩa token gốc nhất thiết đổi sau mỗi GET.

## 6. So sánh kênh truyền: khi nào CSRF thực sự khả thi?

### 6.1. Cookie tự động và header chủ động

| Request | Browser tự đính kèm gì? | Client phải chủ động cung cấp gì? | Hệ quả |
|---|---|---|---|
| Form POST cùng origin dùng session | Cookie phiên nếu đủ điều kiện | CSRF token ở hidden field | CSRF filter xác minh token cùng phiên |
| Form POST từ website ngoài | Cookie phiên **nếu chính sách cho phép** | Attacker thường không có CSRF token hợp lệ | Phòng vệ CSRF từ chối nếu thiếu/sai |
| `fetch` của SPA với bearer header | Cookie nếu có và `credentials` phù hợp | Access token trong `Authorization`; có thể thêm CSRF token nếu dùng credential tự gửi | Tùy cơ chế xác thực thực tế |
| API dùng access token trong cookie | Cookie xác thực có thể tự gửi | CSRF token trong form/header nếu endpoint cần bảo vệ | JWT trong cookie không tự loại CSRF |
| API chỉ nhận Bearer header do app gắn | Không tự gửi bearer cho form ngoài origin | Bearer token chỉ client hợp lệ biết | CSRF truyền thống khó thực hiện nếu không có credential tự gửi khác |

Với `fetch`, `credentials: "include"` không vượt qua `SameSite`, `Secure` hoặc chính sách cookie của browser. Với form HTML đơn giản, trang ngoài có thể tạo request cross-site mà không cần CORS cho phép đọc phản hồi.

### 6.2. SameSite hỗ trợ nhưng không thay thế token

- `SameSite=Strict` thường loại cookie khỏi request cross-site.
- `SameSite=Lax` thường không gửi cookie với cross-site form POST, nhưng có thể gửi ở **top-level navigation GET** an toàn.
- `SameSite=None; Secure` cho phép cookie trong nhiều ngữ cảnh cross-site nếu các chính sách browser khác cho phép.
- Hai subdomain có thể **khác origin nhưng cùng site**. SameSite không phải phép kiểm tra origin.

Bởi vậy, endpoint `GET /delete-account` làm thay đổi trạng thái vẫn là thiết kế nguy hiểm; GET có thể được mở bởi một liên kết từ site khác trong những hoàn cảnh cookie `Lax` được gửi. Không trông chờ CSRF filter chặn `GET` vì Spring Security mặc định xem GET là phương thức an toàn.

### 6.3. CORS không cấp hoặc tạo CSRF token

CORS quy định điều kiện JavaScript ở một origin có thể đọc phản hồi và thực hiện những yêu cầu cần preflight. Nó **không thay việc server xác minh CSRF token** khi nhận POST dựa trên cookie tự động.

Ngay cả khi JavaScript của website tấn công không được đọc phản hồi, một form POST có thể đã được gửi và server có thể đã xử lý nó. Ngược lại, request `fetch` có header `Authorization` tự đặt hoặc header CSRF tùy chỉnh trong cross-origin JavaScript có thể phát sinh preflight; thiết kế CORS phải được đánh giá riêng.

## 7. Spring Security Servlet: vai trò của từng token trong cấu hình

### 7.1. Ứng dụng form login với HttpSession

Với Spring Security Servlet, các thành phần có vai trò khác nhau:

- `HttpSession` và session cookie cho phép tra ngữ cảnh phiên của người dùng.
- `CsrfFilter` áp dụng kiểm tra CSRF cho request thuộc phạm vi bảo vệ.
- `HttpSessionCsrfTokenRepository` quản lý token CSRF **riêng**, lưu theo session.
- `CsrfTokenRequestHandler` đọc submitted token qua form/header và xử lý biểu diễn token.

Cấu hình minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class ServletSessionSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository()))
            .build();
    }
}
~~~

`HttpSessionCsrfTokenRepository` làm rõ nguồn expected token trong phiên; CSRF trong cấu hình web điển hình được bật mặc định, nên có thể không cần khai báo repository tường minh.

Tại thời điểm browser gửi POST:

~~~http
POST /profile/email HTTP/1.1
Cookie: JSESSIONID=SID_A
Content-Type: application/x-www-form-urlencoded

email=new@example.test&_csrf=CSRF_A_OR_MASKED_VALUE
~~~

Spring Security dùng session cookie để xác định session A; dùng repository/handler để kiểm tra CSRF token. Controller chỉ xử lý sau khi request vượt bước bảo vệ, ngoài những kiểm tra khác.

### 7.2. Hiển thị CSRF token mà không làm lộ session ID

Trong template Thymeleaf được Spring Security cấp request attribute `_csrf`:

~~~html
<!-- HTML template -->
<form method="post" action="/profile/email">
  <label for="email">Email mới</label>
  <input id="email" name="email" type="email" required>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Lưu</button>
</form>
~~~

Template sử dụng **CSRF token** do framework cung cấp; **không** lấy `JSESSIONID` hoặc access token từ cookie để điền vào hidden field.

Trong các tích hợp có `th:action` hoặc request data value processor, framework có thể tự thêm CSRF hidden field; kiểm tra HTML sau khi render để tránh nhân đôi trường. Ví dụ dùng `action` tĩnh nhằm minh họa việc chèn thủ công.

### 7.3. Resource server nhận Bearer token

Một API chỉ chấp nhận bearer token trong header có thể cấu hình resource server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BearerOnlySecurity {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt())
            .build();
    }
}
~~~

Đây chỉ là **minh họa cấu hình resource server**; yêu cầu thêm cấu hình decoder/issuer/JWK phù hợp để chạy. Cấu hình trên **không tự vô hiệu hóa CSRF**. Spring Security vẫn có thể đòi CSRF token trên POST, tùy security chain đang áp dụng.

Nếu API thực sự **chỉ** xác thực bằng bearer header do client chủ động đặt và không dùng credential browser tự gửi, nhóm triển khai có thể quyết định miễn CSRF **trong phạm vi API đó** sau khi đánh giá mô hình đe dọa. Không được suy luận rằng chỉ cần gọi `oauth2ResourceServer(...jwt())` là tự loại mọi nguy cơ CSRF.

Ví dụ với một API độc lập, nếu đã xác minh các điều kiện trên, có thể chủ động cấu hình:

~~~java
// Chỉ áp dụng cho chain /api/** đã được đánh giá là Bearer-only.
http.csrf(csrf -> csrf.disable());
~~~

Dòng này chỉ là **một lựa chọn có điều kiện**, không phải khuyến nghị tắt CSRF toàn ứng dụng. Nếu cùng chain nhận cookie đăng nhập hoặc HTTP Basic do browser tự gửi, phải xem lại thiết kế ngay.

### 7.4. Nếu API nhận access token từ cookie

Nếu ứng dụng tự viết bộ lọc đọc JWT từ `Cookie: ACCESS_TOKEN=...` để xác thực API, nó đã biến access token thành **credential tự gửi**. Bộ lọc xác thực JWT không đủ làm CSRF token; vẫn cần cơ chế chống CSRF cho request thay đổi trạng thái.

Phải kiểm tra các trường hợp API nhận **cả** bearer header và cookie: trang ngoài có thể nhắm vào đường cookie dù frontend bình thường chủ yếu dùng header.

## 8. Spring Security Reactive/WebFlux: cùng mục đích, API khác

Trong WebFlux:

- `WebSession` có thể được nhận diện bằng cookie phiên phù hợp với cấu hình reactive.
- `CsrfWebFilter` áp dụng kiểm tra CSRF.
- `WebSessionServerCsrfTokenRepository` lưu expected CSRF token theo WebSession.
- `ServerHttpSecurity` dùng để cấu hình security chain cho WebFlux.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
class ReactiveSessionSecurity {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/assets/**").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
~~~

Nếu WebFlux làm resource server bearer JWT thay vì dùng WebSession, mô hình đe dọa cũng phụ thuộc vào **cách bearer token được đưa vào request**. Một access token được kiểm chứng qua header `Authorization` do client tự gắn khác với cùng token được browser gửi trong cookie.

### 8.1. Cần lấy CSRF token trong reactive view

Trong một luồng WebFlux có `CsrfWebFilter`, token có thể được cung cấp dưới dạng `Mono<CsrfToken>` ở exchange attribute. Controller/view có thể giải quyết Mono rồi đưa token vào template, tùy cách tích hợp với view engine:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveProfilePage {

    @GetMapping("/profile/edit")
    Mono<Rendering> edit(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf = exchange.getAttribute(
                CsrfToken.class.getName());

        return csrf.map(value -> Rendering.view("profile/edit")
            .modelAttribute("_csrf", value)
            .build());
    }
}
~~~

Ví dụ giả định security web filter đã gắn `Mono<CsrfToken>` vào exchange. Trong ứng dụng thực tế có thể có tích hợp view tự động; điều cần giữ là **form nhận CSRF token**, không nhận WebSession ID hoặc bearer access token để thay thế.

## 9. Vòng đời và rủi ro rò rỉ: ba loại token cần bảo vệ khác nhau

### 9.1. Vòng đời điển hình

| Sự kiện | Session ID | Access token | CSRF token |
|---|---|---|---|
| **Đăng nhập** | Có thể tạo mới/đổi định danh phiên để tránh session fixation | Có thể được phát theo luồng xác thực/ủy quyền riêng | Có thể được sinh mới hoặc token trước xác thực bị xóa tùy cấu hình |
| **Gọi API liên tục** | Thường giữ đến khi phiên đổi/hết hạn | Có hiệu lực đến hết hạn/thu hồi; có thể được phát token mới | Token theo phiên có thể được sử dụng lại; masked output có thể thay đổi mỗi lần render |
| **Đăng xuất** | Session thường bị hủy hoặc mất ngữ cảnh xác thực | Cần xem chính sách thu hồi/hết hạn: logout phiên web không tự thu hồi mọi access token | Token gắn phiên có thể mất hiệu lực khi session hết hạn/xóa token |
| **Mở hai tab cùng phiên** | Thường chung session cookie | Tùy lưu token của client | Có thể chung token gốc nếu theo session |
| **Đổi mật khẩu/thu hồi quyền** | Phụ thuộc chính sách vô hiệu hóa phiên | Phụ thuộc `exp`/thu hồi/introspection và chính sách server | Không thay thế bất cứ chính sách vô hiệu hóa credential nào |

Không suy ra rằng thao tác logout trong một giao diện luôn **thu hồi mọi access token** do hệ thống từng phát. Đây là hai cơ chế vòng đời tách biệt và có thể cần chính sách thu hồi riêng.

### 9.2. Đặt token ở đâu và nguy cơ nào xuất hiện?

| Nơi/đường truyền | Session ID | Access token | CSRF token |
|---|---|---|---|
| Cookie `HttpOnly; Secure` | Thường phù hợp với cookie phiên | Có thể dùng, nhưng browser tự gửi và phải đánh giá CSRF | Có thể dùng nếu trang có **kênh khác** lấy token cho form/header |
| Cookie đọc được qua JavaScript | Không nên dùng cho session credential nhạy cảm | Dễ chịu rủi ro lộ token do XSS; cần cân nhắc kỹ | Có thể cần cho mẫu SPA đọc cookie `XSRF-TOKEN` |
| Header `Authorization` | Không phải cách điển hình của session cookie | Rất phổ biến cho Bearer access token | Không phải nơi nên “nhét” access token vào để gọi là CSRF |
| Header `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` | **Không nên gửi SID tại đây để làm CSRF** | **Không nên gửi bearer access token ở đây làm CSRF** | Kênh truyền phổ biến cho CSRF token |
| Hidden field trong HTML form | **Không đưa session ID vào đây** | **Không nhúng access token vào đây** | Kênh truyền phổ biến nếu được render đúng |
| URL/query string | Tránh vì dễ lộ credential | Tránh vì dễ lộ token | Tránh vì token có thể lộ qua log, lịch sử, `Referer` |

Một access token là bearer credential cần được bảo vệ rất chặt. Một CSRF token không độc lập xác thực người dùng, nhưng nếu bị lộ có thể giúp attacker vượt một lớp bảo vệ trong khi browser tự gửi cookie phiên. Vì vậy **cả ba đều không nên được ghi thẳng vào log hay telemetry**.

### 9.3. CSRF token không chống XSS

Nếu attacker có khả năng chạy JavaScript trong origin của ứng dụng (XSS), họ có thể dùng session browser hiện tại để gửi request, đọc CSRF token từ form/DOM hoặc cookie được phép đọc, và thực hiện thao tác hợp lệ dưới góc nhìn CSRF filter.

CSRF token là lớp bảo vệ chống yêu cầu giả mạo **từ origin khác không truy cập được token**; nó không làm mất nhu cầu CSP, mã hóa đầu ra, kiểm soát script và bảo vệ phiên. Đây là lý do module **SPRING_SECURITY_HTTP_PROTECTION** nghiên cứu nhiều lớp bảo vệ HTTP và trình duyệt cùng nhau.

## 10. Các token khác không nên nhầm

### 10.1. Refresh token

**Refresh token** dùng để yêu cầu authorization server cấp access token mới theo cơ chế cấp quyền tương ứng. Nó không phải access token dùng trực tiếp để gọi mọi resource API, cũng không phải CSRF token.

Nếu refresh token được lưu trong cookie tự gửi và endpoint refresh có tác động hoặc cấp credential, cần đánh giá CSRF và ràng buộc nguồn request phù hợp. Tên gọi “refresh” không khiến cơ chế cookie tự động biến mất.

### 10.2. OAuth `state` và PKCE

Trong nhiều luồng OAuth 2.0/OpenID Connect dùng trình duyệt, tham số `state` liên kết **authorization request** với **authorization response** và giúp chống CSRF/tráo luồng đăng nhập tại callback. Nó có mục đích riêng và vòng đời theo **một lần ủy quyền**.

- `state` không phải access token dùng gọi API.
- `state` không phải session ID.
- `state` cũng không phải CSRF token cho tất cả POST nghiệp vụ sau đăng nhập.
- **PKCE** ràng buộc authorization code với client khởi tạo nhờ `code_verifier`/`code_challenge`, giải quyết một lớp rủi ro khác; không tự thay toàn bộ kiểm tra CSRF trên form nghiệp vụ.

Một ứng dụng có thể cần **cả** kiểm tra `state`/PKCE cho OAuth callback lẫn CSRF token cho POST chỉnh sửa dữ liệu.

### 10.3. Idempotency key và nonce chống gửi trùng

Một API thanh toán có thể nhận `Idempotency-Key` để ngăn xử lý trùng khi client retry cùng một thao tác. Chìa khóa này không tự phân biệt request đến từ một website giả mạo; ngược lại CSRF token không bảo đảm request được xử lý đúng một lần.

Hai cơ chế phục vụ **rủi ro khác nhau**, có thể phối hợp trên một request có tác động tài chính.

## 11. Kiểm thử để phân biệt đúng lớp bảo mật

### 11.1. Ma trận thực nghiệm

Giả sử ứng dụng có phiên A đã xác thực và lưu CSRF token A:

| Request | Session/Access credential | CSRF token | Kết quả lý giải |
|---|---|---|---|
| POST hợp lệ của A | Session A | Token A | Qua bước CSRF; cần thêm phân quyền/validation |
| POST giả mạo mang cookie A | Session A do browser tự gửi | Không có token | Bị từ chối bởi CSRF nếu chain bảo vệ đúng |
| POST mang cookie A | Session A | Token B của phiên khác | Bị từ chối nếu token dự kiến gắn theo phiên |
| POST chỉ có CSRF token A | Không có credential đăng nhập | Token A | Không tự cấp quyền để đổi dữ liệu A |
| API Bearer-only có access token hợp lệ | `Authorization: Bearer ...` | Không có token CSRF | Tùy chính sách CSRF của API, **không** suy ra token bearer là CSRF token |
| API JWT trong cookie | Cookie JWT tự gửi | Không có token CSRF | Có thể bị CSRF nếu browser gửi cookie và server bỏ kiểm tra |
| POST có token đúng nhưng không đủ quyền | Session/access token hợp lệ | Token đúng | Có thể qua CSRF nhưng bị authorization từ chối |

Status HTTP có thể bị ảnh hưởng bởi cơ chế login redirect, authentication entry point, access-denied handler và filter order. Một phản hồi `403` không tự chứng minh do CSRF; `401` cũng không thay cho kiểm tra CSRF.

### 11.2. Kiểm thử Spring Security Servlet bằng MockMvc

Với một endpoint `POST /profile/email` đã tồn tại, được bảo vệ bởi `SecurityFilterChain` và trả `204 No Content` khi cập nhật hợp lệ, có thể kiểm thử:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfVsSessionTests {

    @Autowired MockMvc mvc;

    @Test
    void authenticatedSessionDoesNotReplaceCsrfToken() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfTokenPassesCsrfCheck() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf())
                .param("email", "new@example.test"))
            .andExpect(status().isNoContent());
    }

    @Test
    void wrongCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }
}
~~~

Ở đây `with(user("alice"))` là **mock authentication** phục vụ test, không nhất thiết tạo phiên/cookie giống trình duyệt thật. `with(csrf())` tạo token phù hợp cho cơ chế test; nó không kiểm tra toàn bộ quá trình browser đọc form. Để chứng minh token gắn đúng session, cần thêm test tích hợp tạo **hai session độc lập** và thử hoán đổi token A/B.

### 11.3. Kiểm thử Reactive bằng WebTestClient

Với `spring-security-test` và Spring Security được gắn vào `WebTestClient`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveCsrfVsSessionTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void authenticationWithoutCsrfTokenIsInsufficient() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/profile/email")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void csrfTokenPassesCsrfLayer() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/profile/email")
            .exchange()
            .expectStatus().isNoContent();
    }
}
~~~

Ví dụ giả định WebFlux có endpoint thích hợp, không cần body hoặc nhận body phù hợp, trả `204` và mock user được cấp quyền. Với ứng dụng thực, thêm request body/content type và điều chỉnh assertion theo kết quả nghiệp vụ. Các test minh họa rằng **mock user không thay thế CSRF token**; chúng không chứng minh luồng access token trong `Authorization` hoặc session thật.

### 11.4. Kiểm thử trình duyệt để phân biệt credential tự gửi

Với môi trường được phép, mở DevTools và thực hiện:

1. Đăng nhập để xem `Set-Cookie`, xác định cookie **session** hoặc **access token** có đang được server dùng để xác thực không.
2. Mở form hợp lệ, xem có hidden `_csrf` hoặc metadata/header CSRF theo cách ứng dụng thiết kế không.
3. Submit, đối chiếu request có cả **credential** lẫn **CSRF token** không; kiểm tra server xử lý đúng.
4. Bỏ CSRF token, giữ nguyên credential; xác nhận request thay đổi trạng thái bị chặn.
5. Dùng CSRF token từ phiên khác; xác nhận token không thể tái sử dụng cho phiên hiện tại khi thiết kế yêu cầu ràng buộc phiên.
6. Dùng chỉ CSRF token mà bỏ credential; xác nhận token không tự biến thành quyền đăng nhập/ủy quyền.
7. Nếu API dùng bearer header, kiểm tra chính xác **bên nào thêm `Authorization`**; nếu cùng token nằm trong cookie, kiểm tra cookie có tự được browser gửi cross-site không.
8. Phân biệt lỗi CORS preflight, cookie bị loại vì SameSite, thiếu CSRF token và thiếu quyền API.

HTTP client như cURL/Postman có thể tự thêm bất kỳ `Cookie` hoặc header nào, rất hữu ích để kiểm tra server nhưng **không tự chứng minh** browser sẽ gửi cookie tương tự từ một website ngoài.

## 12. Các nhầm lẫn phổ biến và cách sửa

| Phát biểu | Đánh giá và cách hiểu đúng |
|---|---|
| “`JSESSIONID` đã khó đoán nên dùng nó làm CSRF token được.” | **Sai thiết kế.** Session ID là credential xác thực rất nhạy cảm, nên không đưa nó vào form/DOM để kiểm chứng CSRF. |
| “Access token là JWT có chữ ký nên tự chống CSRF.” | **Sai.** JWT có chữ ký xác minh tính toàn vẹn/issuer; nếu nằm trong cookie browser tự gửi vẫn có nguy cơ CSRF. |
| “API không lưu session nên chắc chắn không có CSRF.” | **Sai.** JWT trong cookie hoặc Basic do browser tự gửi vẫn cần đánh giá CSRF. |
| “CSRF token hợp lệ nghĩa là user đã được xác thực.” | **Sai.** Token CSRF không thay authentication/authorization. |
| “Cứ có header `Authorization` là đã chống CSRF.” | **Không đủ.** Phải biết header được client chủ động gắn, API có nhận credential tự động khác không và chính sách CSRF đang áp dụng. |
| “`HttpOnly` giúp token trong cookie không bị CSRF.” | **Sai.** HttpOnly ngăn JavaScript đọc cookie, không ngăn cookie tự được gửi. |
| “`SameSite=Lax` chặn mọi CSRF.” | **Sai.** Còn điều hướng GET, same-site cross-origin và đặc tính cookie/browser khác. |
| “CORS không cho đọc phản hồi thì không có CSRF.” | **Sai.** Form cross-site đơn giản vẫn có thể gửi request và gây tác động. |
| “CSRF token thay thế được CSP/chống XSS.” | **Sai.** XSS trong origin ứng dụng có thể đọc hoặc dùng token hợp lệ. |
| “OAuth `state` là access token.” | **Sai.** `state` liên kết authorization request/response; access token dùng để cấp quyền gọi API. |
| “`Idempotency-Key` là CSRF token.” | **Sai.** Nó thường dùng để ngăn xử lý trùng, không xác minh nguồn request theo mô hình CSRF. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Một form POST hợp lệ có cookie `JSESSIONID=SID_A` và trường `_csrf=T_A`. Giá trị nào xác định phiên và giá trị nào giúp kiểm chứng CSRF?

**Đáp án:** `SID_A` tra phiên; `T_A` là submitted CSRF token để server đối chiếu với expected token của phiên A. Hai giá trị có hai nhiệm vụ tách biệt.

**Câu 2.** API kiểm chứng JWT trong `Authorization` do JavaScript hợp lệ gắn. Trang ngoài gửi form POST nhưng không có header bearer. Đây có phải CSRF truyền thống chỉ vì server dùng JWT không?

**Đáp án:** Không đủ điều kiện để kết luận có CSRF. Nếu API chỉ chấp nhận bearer header và trình duyệt không tự gắn credential đó cho form ngoài origin, đường CSRF dựa vào credential tự gửi khó thực hiện. Vẫn cần đánh giá mọi đường xác thực và chống XSS/đánh cắp token.

**Câu 3.** Cùng JWT được đặt trong cookie `HttpOnly; Secure; SameSite=None` và API dùng cookie đó để xác thực POST. Nguy cơ thay đổi như thế nào?

**Đáp án:** Browser có thể tự gửi cookie JWT trong những ngữ cảnh cross-site được phép. Nếu trang ngoài kích hoạt request hợp lệ về định dạng và API không có cơ chế chống CSRF, vẫn có nguy cơ CSRF. `HttpOnly` không thay vấn đề này.

**Câu 4.** API trả `403` khi gửi POST với cookie đăng nhập hợp lệ, nhưng thiếu trường `_csrf`. Điều đó có tự chứng minh user thiếu quyền không?

**Đáp án:** Không. `403` có thể do filter CSRF chặn trước khi đến authorization/logic nghiệp vụ. Cần xem security chain, thông báo lỗi thích hợp và thử request có token hợp lệ.

**Câu 5.** Token CSRF trong hai lần render HTML có chuỗi khác nhau nhưng cả hai POST hợp lệ. Có chắc session ID hoặc access token đã được luân phiên không?

**Đáp án:** Không. CSRF token có thể được XOR/mask với ngẫu nhiên khác nhau trong từng response, trong khi token gốc, session ID và access token không thay đổi.

**Câu 6.** Ứng dụng dùng OAuth redirect với `state`, sau đó cho phép chỉnh sửa hồ sơ bằng form. Có thể bỏ CSRF token ở form vì đã kiểm tra `state` trong callback không?

**Đáp án:** Không. `state` bảo vệ một bước trong luồng ủy quyền. POST chỉnh sửa hồ sơ dùng cookie tự gửi vẫn cần cơ chế chống CSRF thích hợp.

## Kết luận

**Session ID**, **access token** và **CSRF token** có những vai trò khác nhau dù đều được gọi là “token”. Session ID giúp tra một **phiên**; access token là **credential để resource server kiểm tra quyền truy cập**; CSRF token là **giá trị được client chủ động gửi để server kiểm chứng request thay đổi trạng thái**. Một token không tự thay thế nhiệm vụ của token còn lại.

Trong Spring Security, điều kiện quan trọng nhất khi đánh giá CSRF là **credential có được browser tự đính kèm hay không**. Cookie phiên và cookie chứa JWT đều có thể tạo tiền đề CSRF khi request phù hợp chính sách cookie; bearer token được mã client tự gắn vào `Authorization` có mô hình đe dọa khác. Với **Servlet**, CSRF được kiểm tra qua `CsrfFilter` và token repository/request handler; với **Reactive/WebFlux**, các vai trò tương ứng ở `CsrfWebFilter` và `ServerCsrfTokenRepository`. Cần giữ đúng sự phân biệt này khi cấu hình, kiểm thử và chẩn đoán tương tác giữa CSRF, CORS, CSP, HSTS, security headers, HTTP firewall và bảo vệ session trong module **SPRING_SECURITY_HTTP_PROTECTION**.
