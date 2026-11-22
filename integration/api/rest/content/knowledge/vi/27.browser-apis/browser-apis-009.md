# SameSite cookie, CSRF token và kiểm tra Origin theo mô hình ứng dụng

Một REST API phục vụ trình duyệt có thể xác thực đúng session, phân quyền đúng tài nguyên nhưng vẫn bị lợi dụng để thay đổi dữ liệu nếu người dùng đã đăng nhập truy cập một trang độc hại. Trình duyệt có thể **tự đính kèm cookie** vào request gửi tới API; nếu server chỉ dựa vào cookie để chấp nhận thao tác, trang bên ngoài có thể tìm cách khiến trình duyệt thực hiện hành động mà người dùng không chủ ý. Đây là lớp rủi ro **Cross-Site Request Forgery (CSRF)**.

Trong mô-đun **INTEGRATION_API_REST**, chúng ta thiết kế REST API theo resource, URI, phương thức và mã trạng thái HTTP, kèm hợp đồng dữ liệu rõ ràng. Với chương **API trên trình duyệt**, hợp đồng phải mô tả thêm **cách trình duyệt gửi credential, origin được phép gọi API và cơ chế chống CSRF cho thao tác thay đổi trạng thái**. Cấu hình đúng phụ thuộc vào mô hình ứng dụng; không thể áp một quy tắc cookie hoặc CORS cho tất cả.

## 1. Hiểu đường tấn công trước khi cấu hình

Giả sử người dùng đăng nhập vào `https://api.example.test` bằng session cookie. API có một endpoint cập nhật email:

~~~http
POST /api/v1/profile/email HTTP/1.1
Host: api.example.test
Cookie: __Host-session=<session-id>
Content-Type: application/x-www-form-urlencoded

email=new-address@example.test
~~~

Nếu backend cho phép thay email bằng yêu cầu này mà không xác minh **ý định của người dùng**, một trang tại `https://attacker.test` có thể tạo biểu mẫu gửi tới endpoint:

~~~html
<form method="POST" action="https://api.example.test/api/v1/profile/email">
  <input type="hidden" name="email" value="attacker@example.test">
</form>
<script>document.forms[0].submit();</script>
~~~

Trình duyệt tự quyết định có đính cookie không, dựa trên thuộc tính cookie và bối cảnh request. Trong những cấu hình cho phép cookie đi kèm request xuyên site, server có thể thấy session hợp lệ dù người dùng không hề yêu cầu đổi email. Trang tấn công **không cần đọc được response** để gây tác dụng phụ; vì vậy chặn JavaScript đọc cross-origin bằng CORS chưa đủ để chống CSRF.

Ví dụ trên giả định endpoint chấp nhận `application/x-www-form-urlencoded`. Nếu endpoint chỉ chấp nhận `application/json` và yêu cầu custom header, một biểu mẫu HTML thông thường không gửi được request đúng định dạng; đây là lớp giảm rủi ro hữu ích nhưng vẫn cần chính sách CSRF phù hợp, vì có thể tồn tại endpoint cũ, content type khác hoặc cấu hình CORS quá rộng.

**Mấu chốt:** CSRF lợi dụng credential mà **trình duyệt tự gửi**, điển hình là session cookie, cookie chứa JWT hoặc cookie đăng nhập khác. API chỉ nhận Bearer token được mã JavaScript/chương trình chủ động đặt trong header `Authorization` thường không có cùng cơ chế CSRF truyền thống; nó vẫn phải xử lý XSS, rò token, CORS và phân quyền.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **same-origin** và **same-site**, giải thích hành vi của `SameSite=Strict`, `Lax`, `None`.
2. Thiết kế CSRF token dạng synchronizer token hoặc signed double-submit cookie và chỉ ra điều kiện bảo mật của từng cách.
3. Kết hợp kiểm tra `Origin`, `Referer`, Fetch Metadata và CORS theo lớp phòng vệ.
4. Lựa chọn chính sách cho server-rendered web, same-origin SPA, SPA khác subdomain, SPA cross-site, BFF và REST API dùng Bearer token.
5. Cấu hình Spring Security và kiểm thử request thành công, request thiếu/sai token, origin không hợp lệ và tác dụng phụ bị chặn.

## 2. Same-origin khác same-site

**Origin** được xác định bởi bộ ba `scheme + host + port`. Hai URL chỉ same-origin khi cả ba thành phần tương ứng bằng nhau. **Site** trong cơ chế cookie hiện đại thường xét **scheme + registrable domain** (schemeful same-site); subdomain và port không làm thay đổi site theo cùng cách như origin.

| URL A | URL B | Same-origin? | Same-site? | Lý do |
| --- | --- | --- | --- | --- |
| `https://app.example.test` | `https://app.example.test/profile` | Có | Có | Cùng scheme, host, port mặc định |
| `https://app.example.test` | `https://api.example.test` | Không | Có | Khác subdomain, cùng scheme và registrable domain |
| `https://app.example.test` | `https://app.example.test:8443` | Không | Có | Khác port, vẫn cùng site |
| `http://app.example.test` | `https://app.example.test` | Không | Không theo schemeful same-site | Khác scheme |
| `https://app.example.test` | `https://attacker.test` | Không | Không | Khác registrable domain |

Khi đánh giá site trong thực tế, trình duyệt dùng **Public Suffix List** để xác định registrable domain; không thể luôn suy bằng cách lấy hai nhãn cuối của hostname. Với `localhost`, địa chỉ IP và các miền đặc biệt, hãy kiểm thử trên đúng trình duyệt và môi trường triển khai.

~~~mermaid
flowchart LR
    A["app.example.test<br/>Frontend SPA"] -->|"Cross-origin, same-site"| B["api.example.test<br/>REST API"]
    C["attacker.test<br/>Trang ngoài"] -->|"Cross-site"| B
    B -->|"Cookie của api.example.test"| D["Session trên server"]
~~~

Sự khác biệt này quan trọng: `SameSite=Lax` có thể cho phép trình duyệt gửi cookie đến `api.example.test` khi JavaScript đang chạy tại `app.example.test`, vì hai host **cùng site**; nhưng request JavaScript vẫn là **cross-origin** và cần CORS nếu frontend muốn đọc response. Ngược lại, một subdomain bị chiếm quyền cũng có thể same-site với API. Do đó **SameSite không ngăn mọi kịch bản xuất phát từ một origin kém tin cậy trong cùng site**.

## 3. Chọn thuộc tính cookie theo ranh giới thực tế

Ví dụ session cookie dành riêng cho host phát hành:

~~~http
Set-Cookie: __Host-session=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `Secure` yêu cầu cookie được gửi qua kết nối an toàn theo quy tắc của trình duyệt; ở production vẫn phải bắt buộc HTTPS và xác minh chứng chỉ đúng.
- `HttpOnly` ngăn mã JavaScript đọc trực tiếp cookie qua `document.cookie`; nó không ngăn XSS thực hiện request thay mặt người dùng đang đăng nhập.
- `Path=/` áp dụng cookie trên toàn bộ path của host. `Path` không phải ranh giới phân quyền và không ngăn ứng dụng cùng origin đọc/gửi request.
- Tiền tố `__Host-` trên trình duyệt hỗ trợ yêu cầu `Secure`, `Path=/` và **không có `Domain`**, giúp cookie là **host-only**; không được tạo cookie này cho cả miền cha.
- `SameSite` quyết định những bối cảnh **cross-site** được đính kèm cookie; nó không thay thế CSRF token và Origin check.

### 3.1. Strict, Lax và None

| Thuộc tính | Hành vi chính | Khi cân nhắc |
| --- | --- | --- |
| `SameSite=Strict` | Không gửi cookie trong các request được xem là cross-site, kể cả điều hướng tới trang bằng liên kết từ site khác | Tác vụ nhạy cảm hoặc ứng dụng có thể chấp nhận trải nghiệm điều hướng bị ảnh hưởng |
| `SameSite=Lax` | Gửi cookie trong bối cảnh same-site và một số điều hướng top-level cross-site bằng phương thức an toàn, điển hình `GET` | Giá trị khởi đầu phổ biến cho session web |
| `SameSite=None; Secure` | Cho phép cookie được gửi trong ngữ cảnh cross-site nếu chính sách trình duyệt cho phép | Khi có nhu cầu thực sự về cookie third-party/cross-site, với CSRF token và Origin chặt chẽ |

Không viết ứng dụng dựa vào giả định rằng cookie không khai báo `SameSite` luôn hành xử giống `Lax` ở mọi browser. Một số trình duyệt có hành vi mặc định khác nhau, và một số có cơ chế tương thích tạm thời cho cookie **mới được tạo** trong điều hướng `POST` top-level. Hãy đặt thuộc tính tường minh và kiểm thử các browser được hỗ trợ.

Hãy giữ mọi `GET`, `HEAD` và phương thức HTTP được định nghĩa an toàn **không thay đổi trạng thái nghiệp vụ**. `Lax` vẫn cho phép cookie trong một số điều hướng top-level GET cross-site. Nếu `GET /api/v1/accounts/42/close` lại khóa tài khoản, thuộc tính Lax không cứu được thiết kế này. Các thao tác thay đổi dữ liệu phải dùng phương thức phù hợp như `POST`, `PUT`, `PATCH` hoặc `DELETE` và được bảo vệ CSRF khi phụ thuộc cookie.

`SameSite=None` không bảo đảm cookie third-party luôn hoạt động: browser, chính sách quyền riêng tư, chế độ ẩn danh hoặc phân vùng cookie có thể hạn chế/chặn việc gửi. Với SPA và API ở hai registrable domain khác nhau, cân nhắc **Backend for Frontend (BFF) cùng origin với frontend** trước khi chọn kiến trúc dựa vào third-party cookie.

### 3.2. Vòng đời session cookie

Cookie cần được phát hành qua HTTPS, có thời gian sống hợp lý, session được luân chuyển khi đăng nhập/tăng quyền, vô hiệu hóa khi logout hoặc khi phát hiện rủi ro. Khi thay thế cookie, dùng cùng name/path/domain phù hợp để tránh cookie cũ còn tồn tại. Một cookie `__Host-` không dùng `Domain`; nhờ vậy subdomain khác không thể đặt cookie thay cho đúng host theo quy tắc prefix của browser hỗ trợ.

Không đưa JWT hoặc session ID vào URL, log, error response hoặc trang chứa script của bên thứ ba. JWT nằm trong cookie vẫn là credential **tự đính kèm** của browser nên vẫn phải xét CSRF; JWT nằm trong `Authorization: Bearer ...` do ứng dụng chủ động gắn có threat model khác, nhưng nếu lưu trong `localStorage` thì lỗ hổng XSS có thể đọc token.

## 4. CSRF token: chứng minh ý định của request

CSRF token là giá trị khó đoán mà phía tấn công ở site khác không thể tự tạo hoặc lấy bằng các cơ chế web bình thường. Server yêu cầu token trong request thay đổi trạng thái, kiểm tra token trước khi thực hiện nghiệp vụ và từ chối nếu thiếu/sai.

### 4.1. Synchronizer token pattern cho session server-side

Đây là phương án phù hợp khi backend có session trên server:

1. Sau khi tạo session, server gắn với session một giá trị CSRF token đủ ngẫu nhiên; token có thể được đưa ra qua HTML form, response JSON từ endpoint riêng hoặc thẻ meta của trang cùng origin.
2. Frontend gửi token trong body của form hoặc custom header như `X-CSRF-TOKEN` trên `POST`/`PUT`/`PATCH`/`DELETE`.
3. Server so token với giá trị gắn **đúng session hiện hành** trước khi gọi service nghiệp vụ. Token thiếu, sai hoặc không thuộc session phải trả `403 Forbidden`.
4. Khi phiên đăng nhập đổi hoặc hết hạn, xử lý việc làm mới CSRF token phù hợp với cơ chế session, đặc biệt sau login/logout. Frontend có thể cần gọi lại endpoint lấy token mới.

Ví dụ trao đổi, giả định frontend `https://app.example.test` được phép gọi API ở `https://api.example.test`:

~~~http
GET /api/v1/csrf HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Cookie: __Host-session=<session-id>

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin

{"headerName":"X-CSRF-TOKEN","token":"<opaque-token>"}
~~~

Tiếp theo:

~~~http
POST /api/v1/profile/email HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Cookie: __Host-session=<session-id>
Content-Type: application/json
X-CSRF-TOKEN: <opaque-token>

{"email":"new-address@example.test"}

HTTP/1.1 204 No Content
~~~

Trong ví dụ, `<session-id>` và `<opaque-token>` là ký hiệu minh họa, không phải secret thật. Đáp ứng `204` có nghĩa cập nhật thành công và không có body. Lấy token bằng `GET` là hợp lý nếu endpoint chỉ tạo/đọc token bảo vệ session và không thực hiện nghiệp vụ nhạy cảm; phải tránh lưu cache phản hồi chứa token hoặc để origin không được cấp phép đọc token.

**Không gửi token CSRF trong URL/query string**: URL có thể xuất hiện ở history, Referer, proxy và log. Không ghi token vào audit log hay error body. Token phải đủ khó đoán và được kiểm tra bằng cách không rò thông tin qua so sánh hoặc thông báo lỗi; nó không phải thay thế cho xác thực, phân quyền và kiểm tra đối tượng/tenant.

### 4.2. Double-submit cookie cho trường hợp không lưu CSRF token trên server

Một phương án khác là gửi token CSRF qua cookie dễ đọc bởi JavaScript và yêu cầu client **lặp lại token** trong header. Server so sánh hai giá trị. Tuy nhiên, cách **naive double-submit** chỉ so sánh cookie với header có thể dễ bị lỗi khi kẻ tấn công kiểm soát một subdomain có thể chèn cookie, hoặc khi ứng dụng không ràng buộc token với danh tính phiên.

Nếu dùng stateless double-submit, ưu tiên **signed double-submit**: token chứa nonce ngẫu nhiên và MAC được tạo bằng khóa bí mật phía server, **ràng buộc với một định danh session đã được xác thực**. Server kiểm chữ ký/MAC, ràng buộc session và so sánh giá trị được gửi qua header với cookie; không chấp nhận token do client tự tạo chỉ vì hai giá trị trùng nhau. Khóa ký phải được bảo vệ, hỗ trợ xoay vòng và không gửi xuống client. Tránh dùng PII hoặc một chuỗi session ID công khai làm vật thay thế bí mật khóa ký.

Ví dụ cookie token có thể đọc được:

~~~http
Set-Cookie: XSRF-TOKEN=<signed-token>; Path=/; Secure; SameSite=Lax
~~~

Cookie này thường **không có `HttpOnly`** nếu SPA đọc nó để đặt vào header. Đây là **cookie token CSRF**, không phải cookie đăng nhập: cookie session vẫn cần `HttpOnly`. Đọc cookie token bằng JavaScript chỉ thực hiện được nếu domain/path của cookie cho phép; SPA ở `app.example.test` **không đọc được** cookie host-only do `api.example.test` đặt. Khi frontend và API khác origin, nên cấp token qua một endpoint JSON với CORS được giới hạn, hoặc thiết kế BFF/same-origin phù hợp. Không mở rộng `Domain` của cookie session chỉ để frontend có thể đọc.

Trong Spring Security, `CookieCsrfTokenRepository.withHttpOnlyFalse()` hỗ trợ mô hình cookie token phía client. Đây là một **cấu phần** của giải pháp, không tự bảo đảm signed double-submit hay ràng buộc token với session. Nếu muốn signed double-submit đúng nghĩa, phải tự thiết kế/kiểm chứng repository và validator phù hợp hoặc dùng cơ chế đã được bảo mật kiểm duyệt. Với Spring Security 6, khi dùng cookie token trong SPA, cần hiểu cơ chế **deferred token**, **BREACH/XOR token masking** và cách đọc raw token từ header; không nên sao chép cấu hình dành cho phiên bản/framework khác mà không kiểm thử luồng login/logout và request sau đăng nhập.

### 4.3. Bảo vệ những request nào?

CSRF protection nên áp dụng cho mọi thao tác **không an toàn** theo ngữ nghĩa HTTP: thông thường `POST`, `PUT`, `PATCH`, `DELETE`; các phương thức tùy biến tạo tác dụng phụ cũng phải được bảo vệ. Server phải giữ các phương thức an toàn như `GET`/`HEAD` không thay đổi trạng thái nghiệp vụ. Với `OPTIONS` preflight, frontend chưa thực hiện nghiệp vụ nên không yêu cầu CSRF token cho preflight; request thật vẫn phải vượt kiểm tra token và quyền.

Các trường hợp dễ bỏ sót là login CSRF (ép trình duyệt đăng nhập vào tài khoản do kẻ tấn công kiểm soát), logout CSRF, thay đổi email, duyệt giao dịch, upload/import, refresh token dựa trên cookie, tạo job, endpoint GraphQL có mutation qua POST, và WebSocket handshake sử dụng cookie. Với WebSocket, **Origin của handshake** và quyền trên từng message phải được xét riêng; SameSite/CSRF token ở HTTP không tự động phân quyền tất cả thông điệp sau khi kết nối.

## 5. Origin, Referer, Fetch Metadata và CORS: phân vai rõ ràng

### 5.1. Kiểm tra Origin trên thao tác có tác dụng phụ

Trình duyệt thường gửi header `Origin` cho các request `POST`/Fetch/CORS nhất định, giúp server biết **origin khởi phát yêu cầu**. Với endpoint dùng session cookie, có thể so sánh với danh sách **origin chính xác được phép**, chẳng hạn:

~~~text
https://app.example.test
https://api.example.test
~~~

Không chấp nhận bằng kiểm tra tiền tố như `startsWith("https://app.example.test")`, vì `https://app.example.test.attacker.test` sẽ lọt qua. So sánh phải xét cả scheme, hostname và port; không đánh đồng `http://` với `https://`, không tin `Origin: null` một cách mặc định. Chỉ lấy allowed origin từ cấu hình đáng tin, không suy từ `Host` hoặc `X-Forwarded-Host` chưa được proxy làm sạch.

Với **request có Origin và origin sai**, server nên trả `403` trước khi thay đổi dữ liệu. Với **request thiếu Origin**, có thể dùng `Referer` để kiểm tra nguồn nếu chính sách cho phép, nhưng header này cũng có thể vắng mặt vì privacy policy/proxy. Quy tắc phải được xác định rõ: hệ thống có thể yêu cầu origin bắt buộc cho endpoint browser nhạy cảm, hoặc vẫn chấp nhận request thiếu origin **chỉ khi có CSRF token hợp lệ và các điều kiện bảo mật khác**. Không dùng “không có Origin” làm mặc định tin tưởng.

Kiểm tra `Origin` là **lớp hỗ trợ chống CSRF cho browser**; nó không chứng minh danh tính người dùng hay chống được caller không phải browser, vì HTTP client như cURL có thể tự đặt header. Xác thực và phân quyền vẫn là bắt buộc.

### 5.2. Fetch Metadata làm lớp phòng vệ bổ sung

Những trình duyệt hỗ trợ gửi các header như:

~~~http
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
~~~

Backend có thể áp dụng policy từ chối request thay đổi trạng thái có `Sec-Fetch-Site: cross-site` nếu không nằm trong ngoại lệ đã định nghĩa. Tuy nhiên, `same-site` **không có nghĩa mọi subdomain đều đáng tin**, và một số browser/caller không gửi Fetch Metadata. Vì vậy, Fetch Metadata chỉ bổ sung cho CSRF token và Origin policy. Đừng vô tình chặn OAuth callback, luồng thanh toán hoặc webhook hợp lệ mà chưa phân tích đường gọi; những luồng này cần cơ chế xác thực/chống giả mạo riêng.

### 5.3. CORS quyết định quyền **đọc** cross-origin trong browser

CORS cho phép server công bố những origin có quyền đọc response hoặc gửi request có preflight. Nó khác với CSRF:

- Một HTML form đơn giản có thể gửi request cross-origin **mà không cần server cho phép đọc response**.
- Một số Fetch request có header/mime không đơn giản buộc browser preflight; nếu CORS không cho phép, browser thường không gửi request thật. Đừng dựa vào việc này làm chính sách CSRF duy nhất.
- Header `Access-Control-Allow-Origin` không trao quyền truy cập tài nguyên trên server; backend vẫn phải xác thực session/Bearer token và kiểm tra permission.
- Khi dùng cookie cross-origin, phía client cần `credentials: "include"` và backend cần `Access-Control-Allow-Credentials: true` cùng một **origin cụ thể** trong `Access-Control-Allow-Origin`. Không kết hợp wildcard `*` với credential.

Ví dụ CORS cho SPA tại `https://app.example.test`:

~~~http
OPTIONS /api/v1/profile/email HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: content-type,x-csrf-token
Vary: Origin
~~~

`OPTIONS` là request preflight; browser không gửi session credential cho preflight theo giao thức CORS. Server cần xử lý preflight **trước khi đòi authentication/CSRF token cho request nghiệp vụ**. Với response phụ thuộc `Origin`, phải cấu hình `Vary: Origin`; các framework có thể thêm `Vary: Access-Control-Request-Method` và `Vary: Access-Control-Request-Headers`. Không phản chiếu bừa origin từ header request; hạn chế CORS bằng allowlist và kiểm thử origin lạ, origin `null` và origin sai scheme/port.

## 6. Chọn giải pháp theo mô hình ứng dụng

| Mô hình | Credential trình duyệt gửi | Cấu hình ưu tiên | Chống CSRF |
| --- | --- | --- | --- |
| Trang HTML render từ server, session cookie | Cookie tự đính kèm cùng origin | `Secure`, `HttpOnly`, `SameSite=Lax` hoặc `Strict` tùy UX | Synchronizer token trong form + Origin check với thao tác nhạy cảm |
| SPA và API **same-origin** | Session cookie tự đính kèm | Host-only cookie, HTTPS; không cần CORS giữa các request same-origin | Token qua endpoint JSON/header + Origin/Fetch Metadata khi phù hợp |
| SPA `app.example.test` → API `api.example.test` | Cookie của API khi `credentials: include`; cross-origin nhưng same-site | Host-only cookie của API + `SameSite=Lax`; CORS allowlist có credential | CSRF token qua JSON endpoint, exact Origin check; không trông chờ SameSite vì subdomain cùng site |
| SPA ở site khác hẳn API | Cookie cross-site cần `SameSite=None; Secure`, có thể bị browser chặn | Cân nhắc BFF/same-origin; nếu buộc dùng cookie cross-site, kiểm tra browser support | CSRF token + Origin allowlist, và kiểm thử third-party cookie restrictions |
| BFF cùng origin với frontend | Browser chỉ gửi session cookie tới BFF; BFF giữ token gọi API phía server | Cookie host-only ở BFF, HTTPS, session và secret phía server | BFF kiểm tra CSRF; API nội bộ kiểm tra token dịch vụ, permission |
| Public REST API/Java client/mobile dùng Bearer trong `Authorization` | Không tự đính kèm cookie nếu client không dùng cookie | HTTPS, token đúng audience/scope, CORS nếu browser dùng API | Thường không cần CSRF truyền thống cho Bearer-only; vẫn cần XSS/token hygiene và phân quyền |

Trong ứng dụng lai, **phân loại theo endpoint và cơ chế credential thực tế**, không chỉ theo tên “REST API”. Ví dụ `/api/v1/me` dùng session cookie cần CSRF khi cập nhật dữ liệu, trong khi `/api/v1/jobs/callback` nhận webhook ký HMAC có threat model khác. Nếu API hỗ trợ **cả cookie và Bearer** trên cùng endpoint, cần đảm bảo không tồn tại đường bỏ qua CSRF khi browser vẫn có thể xác thực bằng cookie. Với OAuth/OIDC redirect login, `state` và PKCE giải quyết những vấn đề trong luồng ủy quyền; chúng **không thay thế** CSRF token cho mọi thao tác ứng dụng sau đăng nhập.

### 6.1. Frontend Fetch của SPA dùng cookie

Ví dụ JavaScript chạy ở `https://app.example.test`, gọi API trên cùng site nhưng khác origin:

~~~javascript
const API = "https://api.example.test";

// Lấy CSRF token; session cookie được trình duyệt gửi tới host API.
const tokenResponse = await fetch(API + "/api/v1/csrf", {
  credentials: "include",
  cache: "no-store"
});
if (!tokenResponse.ok) throw new Error("Không lấy được CSRF token");
const { headerName, token } = await tokenResponse.json();

const updateResponse = await fetch(API + "/api/v1/profile/email", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [headerName]: token
  },
  body: JSON.stringify({ email: "new-address@example.test" })
});
if (!updateResponse.ok) throw new Error("Cập nhật thất bại");
~~~

Ở môi trường production cần xử lý lỗi 401/403, phiên hết hạn và token được xoay vòng; sau login/logout, frontend có thể phải lấy token mới. Không đưa token vào URL hoặc log, và không cho origin lạ đọc endpoint lấy token. `credentials: "include"` chỉ yêu cầu browser gửi credential **nếu chính sách cookie cho phép**; nó không thể vượt `SameSite` hoặc chính sách chặn cookie bên thứ ba.

## 7. Cấu hình mẫu với Spring Security 6 / Spring Boot 3

Ví dụ sau minh họa API dùng **server-side HTTP session**, không dùng JWT Bearer cho các endpoint browser. Spring Security mặc định có cơ chế synchronizer CSRF token với `HttpSessionCsrfTokenRepository`. Chúng ta giữ CSRF bật, expose token qua endpoint JSON, cho phép SPA một origin cụ thể và bổ sung kiểm tra Origin cho request thay đổi trạng thái. Các kiểu dịch vụ nghiệp vụ là giả định của ứng dụng.

### 7.1. Cấu hình cookie session tại production

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-session
        secure: true
        http-only: true
        same-site: lax
        path: /
~~~

Cấu hình này giả định ứng dụng/ingress bảo đảm HTTPS và **không đặt thuộc tính Domain** cho session cookie. Nếu app ở sau TLS terminator, phải cấu hình trusted forwarded headers/network boundary đúng cách để nhận diện secure request. Khi SPA và API ở các subdomain khác nhau, cookie host-only của API vẫn được gửi tới API nếu request đáp ứng SameSite và `credentials: "include"`; SPA không cần đọc giá trị session cookie.

### 7.2. Filter chain cho session cookie, CSRF và CORS

~~~java
@Configuration
@EnableWebSecurity
public class BrowserSecurityConfig {

    @Bean
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .csrf(Customizer.withDefaults()) // Không tắt CSRF khi dùng cookie.
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/v1/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/v1/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .addFilterBefore(new UnsafeOriginFilter(), CsrfFilter.class)
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.test"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }
}
~~~

Trong file Java cần import các lớp tương ứng của Spring Security, Spring Web CORS và `java.util.List`. `formLogin` chỉ minh họa cơ chế đăng nhập bằng form; nếu ứng dụng dùng JSON login/OIDC, phần xác thực cần được cấu hình riêng **nhưng CSRF phải tiếp tục bảo vệ endpoint đăng nhập và các thao tác dùng cookie**. Quy tắc `anyRequest().authenticated()` chưa đủ cho tác vụ có quyền cao: thêm `hasAuthority`/`@PreAuthorize` và kiểm soát object/tenant tương ứng.

Spring Security 6 có cơ chế **deferred CSRF token** và **XOR/BREACH token masking** mặc định. Khi controller trả token dưới dạng JSON, frontend nên dùng đúng token được server cung cấp và gửi lại qua header mà `CsrfToken` chỉ định. Sau khi login/logout, Spring Security có thể xóa token cũ; client cần fetch token mới. Không tự vô hiệu hóa masking hoặc cache token xuyên session chỉ vì một bài kiểm thử đầu tiên thất bại.

### 7.3. Endpoint cấp CSRF token và endpoint cập nhật

~~~java
@RestController
class BrowserApiController {
    private final ProfileService profiles;

    BrowserApiController(ProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/api/v1/csrf")
    ResponseEntity<Map<String, String>> csrf(CsrfToken csrfToken) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", csrfToken.getHeaderName(),
                "token", csrfToken.getToken()));
    }

    @PostMapping("/api/v1/profile/email")
    ResponseEntity<Void> changeEmail(
            Authentication authentication,
            @RequestBody ChangeEmailRequest body) {
        profiles.changeEmail(authentication.getName(), body.email());
        return ResponseEntity.noContent().build();
    }
}

record ChangeEmailRequest(String email) {}
~~~

`ProfileService` là service ứng dụng cần triển khai, có kiểm tra quyền sửa hồ sơ của principal và validate địa chỉ email. `CsrfToken` được Spring Security đưa vào request để controller có thể trả token; `CacheControl.noStore()` yêu cầu cache tuân thủ chuẩn không lưu response. Chỉ cấp token cho những origin được tin tưởng và không cấp quyền đọc cross-origin tùy ý. Nếu endpoint được phép gọi trước login, quy trình xác thực vẫn phải bảo vệ login CSRF và phát token mới khi session authentication thay đổi.

### 7.4. Kiểm tra Origin bổ sung

Đoạn filter sau chỉ minh họa policy **deny khi Origin có mặt nhưng không thuộc allowlist**. Nó không thay thế CSRF token; request thiếu Origin vẫn phải đi qua `CsrfFilter` và có token hợp lệ. Tùy nghiệp vụ, có thể từ chối hoàn toàn unsafe request thiếu Origin nếu tất cả client hợp lệ đều gửi Origin.

~~~java
public final class UnsafeOriginFilter extends OncePerRequestFilter {
    private static final Set<String> ALLOWED = Set.of(
        "https://app.example.test",
        "https://api.example.test"
    );
    private static final Set<String> SAFE = Set.of("GET", "HEAD", "OPTIONS");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        String origin = request.getHeader("Origin");
        boolean unsafe = !SAFE.contains(request.getMethod());

        if (unsafe && origin != null && !ALLOWED.contains(origin)) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN);
            return;
        }
        chain.doFilter(request, response);
    }
}
~~~

Thêm import `jakarta.servlet.*`, `jakarta.servlet.http.*`, `org.springframework.web.filter.OncePerRequestFilter`, `java.io.IOException` và `java.util.Set` theo phiên bản Spring Boot 3. Filter chỉ nên được đăng ký **một lần** trong chain áp dụng cho các browser endpoint; nếu tách nhiều `SecurityFilterChain`, phải kiểm tra `securityMatcher` và thứ tự để không tạo đường đi qua chain khác nới lỏng hơn. Nếu ứng dụng có caller máy chủ không dùng cookie, tách chính sách Bearer/API-key rõ ràng thay vì bỏ CSRF rộng rãi cho mọi URL.

Ví dụ bộ filter không tự xác minh `Origin` của các HTTP client không phải browser; vẫn cần authn/authz. Trong production, danh sách origin phải lấy từ cấu hình được quản lý và được kiểm chứng, không nhận từ tham số request. Đừng cho origin dạng `null` hoặc origin chưa được xét duyệt tự đi qua.

## 8. Mã trạng thái và xử lý lỗi

| Trường hợp | HTTP thường dùng | Lưu ý |
| --- | --- | --- |
| Chưa có session hợp lệ / chưa đăng nhập | `401 Unauthorized` cho API JSON, hoặc redirect login khi giao diện form chủ đích | `formLogin` mặc định có thể redirect; SPA nên xác định rõ hợp đồng lỗi |
| Có session nhưng CSRF token thiếu/sai | `403 Forbidden` | Không thực thi thao tác; tránh tiết lộ token server |
| Origin hiện diện nhưng không thuộc allowlist | `403 Forbidden` | Từ chối trước khi thay đổi dữ liệu |
| Token hợp lệ nhưng không có permission nghiệp vụ | `403 Forbidden` | CSRF token không cấp quyền |
| Có quyền nhưng resource không thuộc phạm vi đối tượng/tenant | `403` hoặc `404` theo chính sách nhất quán | Kiểm tra trước tác dụng phụ |
| Request hợp lệ, cập nhật thành công không trả body | `204 No Content` | Phản ánh thao tác nghiệp vụ thành công |
| Session hết hạn giữa lúc SPA lấy và gửi token | `401` hoặc `403` theo cơ chế xác thực/CSRF | Frontend làm mới phiên/token bằng flow an toàn; không retry ghi vô hạn |

Một response lỗi cho CSRF thiếu:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/forbidden",
  "title": "Forbidden",
  "status": 403,
  "detail": "Yêu cầu không được chấp nhận."
}
~~~

Định dạng này minh họa Problem Details; Spring có thể trả response khác nếu chưa cấu hình `AccessDeniedHandler` hay `AuthenticationEntryPoint` riêng. Không dùng `200 OK` cho request bị từ chối, không để trang lỗi chứa token, session ID hoặc stack trace. Với endpoint giao dịch tài chính/đơn hàng, ngoài CSRF còn cần idempotency và ràng buộc trạng thái nghiệp vụ để chống tạo yêu cầu trùng khi retry.

## 9. Kiểm thử HTTP, Spring và browser

Chỉ kiểm tra rằng response chứa `SameSite=Lax` là **chưa đủ**. Cần chứng minh request từ origin lạ thiếu token không tạo tác dụng phụ, request hợp lệ hoạt động và CORS không phát quyền đọc token sai nơi.

### 9.1. Ma trận kiểm thử

| Điều kiện request | Kỳ vọng | Bất biến cần chứng minh |
| --- | --- | --- |
| Đã đăng nhập, `POST` thiếu CSRF token | `403` | Email/DB không đổi |
| Đã đăng nhập, token sai hoặc của session khác | `403` | Không tạo sự kiện, job, message |
| Đã đăng nhập, token đúng, Origin được phép | `204` với endpoint ví dụ | Chỉ thay dữ liệu đúng tài khoản |
| Token đúng nhưng Origin hiện diện và sai | `403` với `UnsafeOriginFilter` | Không có cập nhật |
| Không có session hợp lệ, token bất kỳ | `401` hoặc redirect login tùy API | Không cập nhật |
| `OPTIONS` preflight từ origin được phép | Cho phép theo CORS, không cần CSRF | Không thực thi nghiệp vụ |
| Preflight và request thực tế từ origin lạ | Không cấp quyền CORS, hoặc bị từ chối tại backend | Không có tác dụng phụ |
| Cookie `SameSite=Lax`, điều hướng cross-site GET | Có thể đính cookie theo quy tắc browser | GET không thay đổi trạng thái |
| SPA khác subdomain nhưng same-site | Cookie được gửi khi hợp lệ; CORS đúng origin | CSRF token vẫn bắt buộc |
| Session đổi sau login/logout | Client nhận token mới; token cũ bị xử lý đúng | Không chấp nhận thao tác sai phiên |

### 9.2. Ví dụ kiểm thử Spring Security Test

Trong ứng dụng có controller `POST /api/v1/profile/email` và `UnsafeOriginFilter` ở trên:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BrowserCsrfIT {
    @Autowired MockMvc mvc;

    @Test
    void missingCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/v1/profile/email")
                .with(user("alice"))
                .header("Origin", "https://app.example.test")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"new@example.test\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validTokenAndTrustedOriginAreAccepted() throws Exception {
        mvc.perform(post("/api/v1/profile/email")
                .with(user("alice"))
                .with(csrf())
                .header("Origin", "https://app.example.test")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"new@example.test\"}"))
            .andExpect(status().isNoContent());
    }

    @Test
    void invalidTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/v1/profile/email")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .header("Origin", "https://app.example.test")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"new@example.test\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void untrustedOriginIsForbiddenEvenWithToken() throws Exception {
        mvc.perform(post("/api/v1/profile/email")
                .with(user("alice"))
                .with(csrf())
                .header("Origin", "https://attacker.test")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"new@example.test\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ cần `spring-security-test` và static import tương ứng của MockMvc, SecurityMockMvcRequestPostProcessors, JUnit và các kiểu HTTP. Bài test thành công giả định `ProfileService` được cung cấp trong test context với dữ liệu phù hợp. Cần thêm assert trạng thái DB hoặc verify không gọi service cho test bị từ chối; **kiểm tra mã HTTP đơn thuần không chứng minh chắc chắn không có tác dụng phụ**. Không mock toàn bộ filter hoặc vô hiệu hóa Spring Security trong test.

`with(csrf())` tạo token cho MockMvc mà không mô phỏng toàn bộ hành vi cookie/Origin thật của browser. Vì vậy hãy kiểm thử thêm bằng Playwright/Cypress hoặc trình duyệt thực để xác minh `SameSite`, `Secure`, `HttpOnly`, `credentials: "include"` và các kịch bản cross-site. Dùng các hostname và HTTPS gần giống production; giả định từ `localhost` có thể cho kết quả sai về schemeful site hoặc đặc tính cookie. Các test riêng nên kiểm tra login/logout xoay vòng token, origin cùng site nhưng khác subdomain, token của session khác và việc không lộ token qua CORS/cache.

### 9.3. Kiểm tra bằng cURL

Ví dụ kiểm tra backend từ chối khi thiếu CSRF token (không thêm token thật vào lịch sử shell hoặc log công khai):

~~~bash
curl -i -X POST https://api.example.test/api/v1/profile/email \
  -H "Origin: https://app.example.test" \
  -H "Content-Type: application/json" \
  -H "Cookie: __Host-session=<test-session-id>" \
  --data '{"email":"new@example.test"}'
~~~

Với session test hợp lệ nhưng **thiếu token**, kỳ vọng `403` và không có thay đổi dữ liệu. Một test khác gửi token hợp lệ và `Origin: https://attacker.test` cũng phải bị từ chối theo policy ví dụ. Lưu ý cURL có thể tự đặt header `Origin` và không thực thi quy tắc SameSite như browser: cURL kiểm thử **kiểm soát phía server**, còn SameSite/CORS cần test trên browser thật.

## 10. Các lỗi triển khai hay gặp

1. **Chỉ có SameSite mà không có token:** bỏ sót kịch bản cùng site khác origin, điều hướng GET thay đổi trạng thái, cấu hình cookie không đồng nhất hoặc browser có chính sách khác nhau.
2. **Tin CORS là cơ chế chống CSRF duy nhất:** request từ form HTML có thể tạo tác dụng phụ dù JavaScript của attacker không đọc được response.
3. **Dùng `SameSite=None` để sửa lỗi cookie mà không đánh giá browser:** cookie có thể vẫn bị hạn chế; token/Origin policy yếu đi và ứng dụng không hoạt động ổn định.
4. **Chỉ so sánh cookie token với header:** naive double-submit không ràng buộc session hoặc có cookie injection từ subdomain có thể bị phá vỡ.
5. **Mở CORS cho mọi subdomain:** subdomain do nhóm khác hoặc bên ngoài kiểm soát có thể đọc CSRF token/session data nếu cấu hình credential sai.
6. **Tắt toàn bộ CSRF vì REST được gọi bằng JSON:** một số endpoint vẫn dùng cookie, form login, multipart/form-data, endpoint cũ hoặc logout.
7. **Bỏ token vào query string:** token bị lộ qua log, Referer và history; server/caching cũng có thể lưu lại.
8. **Đánh đồng CSRF token với phân quyền:** token hợp lệ chỉ là một điều kiện chấp nhận request, không chứng minh quyền cập nhật đối tượng.
9. **Kiểm tra Origin theo chuỗi tiền tố hoặc tin forwarded header:** dễ chấp nhận domain giả hoặc cấu hình proxy bị spoof.
10. **Không kiểm tra sau login/logout:** token cũ/phiên cũ có thể gây lỗi hoặc hành vi không mong muốn; SPA cần flow refresh token rõ ràng.

## 11. Bài tập thực hành

**Bài tập 1 — Phân loại site/origin.** Cho ba URL `https://app.shop.example.test`, `https://api.shop.example.test` và `https://help.example.test:8443`. Hãy xác định cặp nào same-origin/same-site theo schemeful site, rồi giải thích vì sao CORS vẫn cần cho request JS từ `app` tới `api`. Giả sử một subdomain thuộc nhà cung cấp thứ ba bị chiếm quyền: liệu `SameSite=Strict` tự bảo vệ API trước nguồn đó không?

**Bài tập 2 — Thiết kế theo kiến trúc.** Một nhóm phát triển có bốn client: (a) HTML server-rendered dùng session; (b) SPA và API khác subdomain nhưng cùng site; (c) SPA chạy trên miền bên thứ ba; (d) Java CLI gửi Bearer token. Lập bảng cookie, CORS, token, Origin policy và kịch bản test cho từng client. Chỉ ra nơi nào nên dùng BFF và lý do.

**Bài tập 3 — Sửa lỗ hổng.** Đoạn mã sau chỉ dựa vào session:

~~~java
@PostMapping("/api/v1/orders/{id}/approve")
ResponseEntity<Void> approve(@PathVariable UUID id) {
    orderService.approve(id);
    return ResponseEntity.noContent().build();
}
~~~

Hãy bổ sung xác thực, kiểm tra permission `orders.approve`, kiểm soát quyền theo đối tượng và CSRF cho session cookie. Viết test chứng minh request thiếu token hoặc có Origin lạ không thể phê duyệt đơn; test hợp lệ chỉ phê duyệt đơn thuộc phạm vi người gọi. Không dùng `GET` để phê duyệt.

**Bài tập 4 — Xây quy trình kiểm thử end-to-end.** Trên Spring Boot 3, triển khai `GET /api/v1/csrf` và `POST /api/v1/profile/email`. Cấu hình session cookie host-only với `SameSite=Lax`, CORS allowlist cho `https://app.example.test` và Origin filter. Dùng MockMvc kiểm tra thiếu/sai token, Origin không đúng, request thành công. Dùng browser automation chứng minh cookie không đọc được qua JavaScript khi có `HttpOnly`, vẫn tự gửi đúng host, và cookie/CSRF không bị bypass từ `https://attacker.test`.

### Tiêu chí hoàn thành

Lời giải đạt yêu cầu khi (1) phân biệt đúng site và origin; (2) giải thích chính xác credential tự đính kèm trong từng mô hình; (3) có CSRF token gắn đúng session hoặc cơ chế ký/ràng buộc phù hợp; (4) Origin/CORS được áp dụng theo allowlist chính xác và không thay thế authn/authz; (5) test chứng minh request bị từ chối không tạo tác dụng phụ; và (6) luồng login/logout/token refresh được xử lý nhất quán.

## 12. Checklist cho code review

- [ ] Tất cả endpoint sử dụng cookie xác thực đã được kiểm kê; những thao tác thay đổi trạng thái dùng HTTP method phù hợp.
- [ ] Session cookie có `Secure`, `HttpOnly`, `SameSite` tường minh, thời gian sống phù hợp và không bị mở `Domain` ngoài chủ đích.
- [ ] CSRF token khó đoán, ràng buộc phiên/được ký đúng cách, không lộ qua URL/log/cache và được làm mới khi cần.
- [ ] Request unsafe thiếu/sai token bị từ chối **trước** khi cập nhật DB, gửi message hoặc gọi service ngoài.
- [ ] Origin policy so sánh chính xác scheme, host, port; có quy định rõ cho Origin vắng mặt/`null` và trusted proxy.
- [ ] CORS không phản chiếu origin tùy ý; credential chỉ cho origin đã duyệt; preflight được xử lý trước authentication nghiệp vụ.
- [ ] SPA khác subdomain đã kiểm thử SameSite và CORS độc lập; cross-site cookie có phương án tương thích browser hoặc BFF.
- [ ] Kiểm thử bao phủ login/logout, token rotation, CSRF sai session, subdomain cùng site nhưng không đáng tin, Origin giả và tác dụng phụ.

**Điểm cần nhớ:** **SameSite** kiểm soát khi nào browser gửi cookie theo *site*; **CSRF token** chứng minh request thao tác xuất phát từ luồng ứng dụng hợp lệ; **Origin check** xác định nguồn browser dự kiến; **CORS** giới hạn quyền đọc cross-origin. Kết hợp chúng theo mô hình session, SPA, BFF hay Bearer API mới tạo được hàng rào nhất quán cho REST API chạy trong trình duyệt.
