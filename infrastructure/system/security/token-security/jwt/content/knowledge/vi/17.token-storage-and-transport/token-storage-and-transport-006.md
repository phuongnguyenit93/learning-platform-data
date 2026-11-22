# Chống CSRF khi trình duyệt tự động gửi cookie

Khi một ứng dụng dùng cookie để mang JWT hoặc session credential, trình duyệt thường tự đính kèm cookie vào request phù hợp với domain, path, scheme và chính sách SameSite. Đặc tính tiện lợi này tạo ra rủi ro **Cross-Site Request Forgery (CSRF)**: một trang web khác có thể khiến trình duyệt của người dùng đã đăng nhập gửi request đến ứng dụng mục tiêu. Nếu server chỉ kiểm tra cookie hợp lệ mà không xác minh request có xuất phát từ luồng tương tác được phép, attacker có thể khiến người dùng thực hiện hành động ngoài ý muốn.

Bài này thuộc chương **Lưu trữ và truyền** của module **Security - JSON Web Token (JWT)**. Nội dung tập trung vào bảo vệ ứng dụng web dùng cookie tự động gửi credential, áp dụng cho bảo mật JWT nói chung và không phụ thuộc ngôn ngữ lập trình hay framework.

## 1. Mục tiêu và nguyên tắc cốt lõi

Sau bài học, người đọc có thể:

1. Giải thích vì sao cookie chứa JWT vẫn có nguy cơ CSRF dù JWT có chữ ký hợp lệ.
2. Nhận diện điều kiện để một request CSRF thành công.
3. Chọn và kết hợp SameSite, CSRF token, Origin/Referer validation, Fetch Metadata và CORS.
4. Thiết kế Synchronizer Token Pattern hoặc Signed Double-Submit Cookie an toàn.
5. Bảo vệ các endpoint thay đổi trạng thái và luồng đăng nhập/OAuth.
6. Kiểm thử request cross-site, same-site và các trường hợp trình duyệt khác nhau.

**Nguyên tắc chính:** chữ ký JWT chứng minh token được tạo bởi bên giữ khóa tương ứng và nội dung không bị sửa. Chữ ký không chứng minh người dùng chủ động gửi request hiện tại. Nếu trình duyệt tự động gửi cookie, server cần một cơ chế chống CSRF phù hợp với cách ứng dụng truyền credential.

## 2. CSRF là gì?

CSRF xảy ra khi attacker khiến trình duyệt của nạn nhân gửi một request có credential hợp lệ đến ứng dụng mà nạn nhân đang đăng nhập. Trình duyệt có thể tự gắn cookie xác thực vào request, còn server nhìn thấy cookie hợp lệ và xử lý hành động.

Ví dụ:

1. Người dùng đăng nhập vào https://bank.example.test; trình duyệt lưu cookie xác thực.
2. Người dùng mở một trang do attacker kiểm soát trong tab khác.
3. Trang attacker tạo form gửi request đến https://bank.example.test/transfers.
4. Nếu cookie được gửi kèm và server không có kiểm soát CSRF phù hợp, request có thể được xử lý bằng quyền của người dùng.

Attacker thường không cần đọc response của ngân hàng. Chỉ cần server thực hiện hành động như chuyển tiền, đổi email, tạo API key hoặc thay đổi cấu hình là đã có tác động.

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt người dùng
    participant B as Ứng dụng mục tiêu
    participant A as Trang attacker
    U->>B: Đăng nhập, nhận cookie xác thực
    B-->>U: Set-Cookie: auth=...
    U->>A: Mở trang attacker
    A->>U: Form hoặc request cross-site
    U->>B: Request kèm cookie nếu chính sách cookie cho phép
    B->>B: Kiểm tra cookie nhưng thiếu CSRF validation
    B-->>U: Thực hiện thay đổi trạng thái
~~~

Same-Origin Policy thường ngăn trang attacker đọc response của ứng dụng mục tiêu. Tuy nhiên, chính sách này không tự ngăn mọi loại request được gửi đi. Vì thế, “attacker không đọc được response” không đồng nghĩa “attacker không thể gây hành động”.

## 3. Điều kiện để CSRF có thể xảy ra

Một tình huống CSRF thường cần các điều kiện sau:

- **Có credential được trình duyệt gửi tự động:** phổ biến nhất là cookie session hoặc cookie chứa JWT; một số cơ chế xác thực trình duyệt tự quản lý khác cũng có thể có đặc tính tương tự.
- **Người dùng có trạng thái xác thực:** cookie còn hiệu lực và được gửi đến endpoint mục tiêu.
- **Attacker khiến trình duyệt gửi được request:** ví dụ form HTML, navigation hoặc request phù hợp với chính sách CORS/cookie của trình duyệt.
- **Endpoint thực hiện tác động:** request có thể thay đổi dữ liệu, thực hiện giao dịch hoặc kích hoạt thao tác nhạy cảm.
- **Server thiếu kiểm tra nguồn gốc hoặc bằng chứng chống CSRF:** cookie hợp lệ bị coi là đủ để cho phép hành động.

CSRF không đòi hỏi attacker biết JWT, secret hay cookie value. Đây là khác biệt quan trọng giữa CSRF và đánh cắp token.

## 4. Vì sao JWT không tự chống CSRF?

JWT là định dạng token và cơ chế bảo vệ nội dung/chữ ký. CSRF là vấn đề về cách trình duyệt gửi credential và cách server xác định ý định của request. Hai vấn đề nằm ở các lớp khác nhau.

| Cách truyền JWT | Trình duyệt tự động gửi? | Rủi ro CSRF |
| --- | --- | --- |
| JWT trong cookie xác thực | Có, theo cookie scope và SameSite | Có; cần CSRF defenses. |
| JWT trong Authorization: Bearer do JavaScript chủ động gắn | Thông thường không tự gắn vào request cross-site | CSRF cổ điển giảm đáng kể; vẫn phải kiểm soát CORS và XSS. |
| JWT trong query string | Có thể bị gửi qua URL/navigation và dễ rò rỉ | Thiết kế không an toàn; tránh truyền bearer token trong URL. |
| JWT trong form field hoặc hidden field | Phụ thuộc cách ứng dụng gửi | Cần đánh giá cách credential được gắn vào request; không mặc định an toàn. |

Nếu JWT nằm trong cookie HttpOnly, JavaScript của trang không đọc được cookie, nhưng trình duyệt vẫn có thể tự gửi cookie đến server. HttpOnly giúp giảm khả năng XSS đánh cắp cookie qua JavaScript; nó **không phải** biện pháp chống CSRF.

JWT stateless cũng không làm CSRF biến mất. Server vẫn nhận request có cookie hợp lệ và có thể xác minh chữ ký hoàn toàn đúng trước khi thực hiện hành động giả mạo.

## 5. Các kiểu request cross-site có thể kích hoạt

Attacker có thể dùng nhiều cơ chế trình duyệt.

### 5.1. HTML form

Form là ví dụ kinh điển vì trình duyệt có thể gửi request mà không cần JavaScript đọc response:

~~~html
<form action="https://app.example.test/account/email" method="POST">
  <input type="hidden" name="email" value="attacker@example.test">
  <button type="submit">Continue</button>
</form>
~~~

Nếu người dùng đang có cookie đăng nhập và cookie được gửi trong request, server có thể xử lý thao tác đổi email nếu không có CSRF validation.

### 5.2. Navigation hoặc resource request

Một số request điều hướng hoặc tải tài nguyên có thể gửi cookie theo chính sách trình duyệt. Vì vậy, không thiết kế endpoint thay đổi trạng thái bằng GET, ví dụ:

~~~html
<img src="https://app.example.test/account/delete">
~~~

Nếu chỉ cần mở URL đã gây thay đổi dữ liệu, endpoint có thể bị kích hoạt ngoài ý muốn bởi link, preview, crawler hoặc trang attacker.

### 5.3. JavaScript fetch/XHR cross-origin

Attacker có thể thử gửi request bằng fetch hoặc XHR. CORS có thể ngăn một số request cần preflight, nhưng không phải là cơ chế chống CSRF đầy đủ. Một số request đơn giản vẫn có thể được gửi; CORS chủ yếu kiểm soát việc script có được đọc response hay không.

Không xây dựng bảo mật dựa trên giả định rằng mọi request cross-origin đều cần preflight.

## 6. Cookie attributes: lớp phòng vệ đầu tiên

Cookie xác thực nên có thuộc tính hạn chế phạm vi và cách sử dụng:

~~~http
Set-Cookie: __Host-auth=<JWT>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Thuộc tính | Tác dụng | Lưu ý |
| --- | --- | --- |
| Secure | Chỉ gửi cookie qua kết nối bảo mật HTTPS. | Bắt buộc trong production; không bảo vệ khỏi CSRF qua HTTPS. |
| HttpOnly | JavaScript không đọc cookie qua API trình duyệt thông thường. | Giảm nguy cơ đánh cắp cookie qua XSS; không ngăn trình duyệt tự gửi cookie. |
| SameSite=Strict | Hạn chế gửi cookie trong ngữ cảnh cross-site. | Có thể ảnh hưởng luồng đi từ website bên ngoài hoặc callback đăng nhập. |
| SameSite=Lax | Cho phép cookie trong một số điều hướng top-level an toàn, hạn chế nhiều request cross-site khác. | Không chặn mọi CSRF; cần hiểu hành vi browser và phương thức request. |
| SameSite=None | Cho phép cookie được gửi trong ngữ cảnh cross-site. | Phải đi kèm Secure; cần CSRF defenses rõ ràng. |
| Path | Giới hạn path gửi cookie. | Không phải ranh giới bảo mật đáng tin cậy để chống CSRF. |
| Domain | Quy định host/domain nhận cookie. | Bỏ thuộc tính này để tạo host-only cookie nếu không cần chia sẻ subdomain. |

### 6.1. Ưu tiên host-only cookie

Nếu không cần chia sẻ cookie giữa các subdomain, không đặt thuộc tính Domain. Cookie khi đó chỉ được gửi đến host đã tạo cookie.

Ví dụ:

~~~http
Set-Cookie: __Host-auth=<JWT>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix __Host- yêu cầu cookie được đặt với Secure, Path=/ và không có Domain trong các trình duyệt hỗ trợ quy tắc prefix này. Nó giúp giảm một số nguy cơ cookie bị ghi đè từ subdomain.

Host-only cookie không thay thế CSRF token. Các trang ở origin khác vẫn có thể khiến browser gửi request đến host mục tiêu nếu các điều kiện cookie và request cho phép.

### 6.2. Không dùng Path như cơ chế cách ly bảo mật

Cookie path chủ yếu điều khiển phạm vi gửi cookie. Nó không phải cơ chế phân quyền endpoint và không ngăn được mọi kiểu tấn công cùng origin. Server vẫn phải kiểm tra authentication, authorization và CSRF cho từng thao tác thay đổi trạng thái.

## 7. SameSite: hiểu đúng Strict, Lax và None

SameSite là một thuộc tính quan trọng để giảm request cross-site có cookie. Tuy nhiên, “site” không đồng nghĩa “origin”.

- **Origin** gồm scheme, host và port.
- **Site** trong cách trình duyệt xét SameSite dựa trên scheme và registrable domain theo quy tắc của trình duyệt.
- Hai subdomain khác origin nhưng có thể được coi là same-site.

Ví dụ https://evil.example.test và https://app.example.test là hai origin khác nhau nhưng thường cùng site. Nếu subdomain attacker kiểm soát được, SameSite không đủ ngăn request từ subdomain đó.

### 7.1. SameSite=Strict

Cookie chỉ được gửi trong ngữ cảnh same-site theo quy tắc trình duyệt. Đây là lựa chọn hạn chế nhất cho cookie xác thực.

Phù hợp khi:

- Ứng dụng không cần duy trì trạng thái đăng nhập khi người dùng đi từ website bên ngoài.
- Không có callback cross-site cần cookie đó.
- Có thể chấp nhận trải nghiệm đăng nhập lại hoặc điều chỉnh luồng điều hướng.

Strict vẫn không thay thế CSRF token/Origin validation cho mọi tình huống same-site, ví dụ subdomain không đáng tin.

### 7.2. SameSite=Lax

Lax thường cho phép cookie trong điều hướng top-level an toàn, chẳng hạn người dùng nhấn link GET từ một site khác. Cookie thường không được gửi trong các request cross-site như form POST.

Đây là mức cân bằng thường dùng cho cookie đăng nhập web. Tuy nhiên:

- Không biến GET thành phương thức an toàn nếu ứng dụng dùng GET để thay đổi trạng thái.
- Không ngăn request từ một origin khác nhưng same-site.
- Hành vi mặc định và tương thích giữa các phiên bản browser có thể khác nhau.
- Một số cơ chế tương thích khi cookie mới được tạo có thể có hành vi đặc biệt; không dựa vào thời gian cookie mới để bảo vệ nghiệp vụ.

### 7.3. SameSite=None

None cho phép cookie được gửi trong ngữ cảnh cross-site và phải đi kèm Secure. Nó thường cần trong một số kiến trúc nhúng, liên domain hoặc luồng xác thực đặc biệt.

Nếu bắt buộc dùng None:

- Dùng CSRF token phù hợp.
- Kiểm tra Origin/Referer cho request thay đổi trạng thái.
- Dùng Fetch Metadata như lớp phòng vệ bổ sung.
- Giới hạn CORS credentialed origins chính xác.
- Giảm scope cookie và bảo vệ endpoint nhạy cảm.

### 7.4. SameSite không phải biện pháp duy nhất

SameSite có thể giảm đáng kể một số CSRF cross-site, nhưng không thay thế kiểm tra CSRF ở server. Nó không bảo vệ đầy đủ trước same-site attacker, XSS, client không tuân thủ cookie policy hoặc các luồng đặc biệt.

## 8. Chọn chiến lược CSRF phù hợp với kiến trúc

| Kiến trúc | Credential tự động gửi | Biện pháp thường phù hợp |
| --- | --- | --- |
| Web app server-rendered dùng session cookie | Có | Synchronizer Token Pattern, SameSite, Origin validation. |
| SPA cùng origin, JWT trong HttpOnly cookie | Có | CSRF token qua response/bootstrap và custom header, SameSite, Origin/Fetch Metadata. |
| SPA khác origin, cookie cross-site | Có nếu cookie policy cho phép | CSRF token, CORS credentials với allowlist chính xác, Origin validation, SameSite=None khi thực sự cần. |
| API chỉ nhận Bearer token trong Authorization header do client chủ động gắn | Không tự động theo cookie | CORS và kiểm soát XSS; đánh giá CSRF nếu còn credential tự động khác. |
| Webhook hoặc machine-to-machine | Thường không dùng browser cookie | Chữ ký request, mTLS hoặc credential riêng; CSRF trình duyệt thường không phải mô hình chính. |

Không áp dụng cùng một cấu hình cookie/token cho mọi client. Hãy xác định browser, native app, service-to-service và webhook là các trust context khác nhau.

## 9. CSRF token: cơ chế chứng minh request thuộc luồng hợp lệ

CSRF token là giá trị khó đoán được server cấp cho client hợp lệ. Client gửi token này trong một phần của request mà trang attacker không thể tự đọc hoặc tạo hợp lệ theo mô hình bảo vệ.

Một thiết kế phổ biến:

1. Người dùng xác thực; server tạo hoặc xác định session context.
2. Server cấp CSRF token gắn với session đó.
3. Trang ứng dụng nhận token qua HTML hoặc API cùng origin.
4. Client gửi token trong hidden form field hoặc custom header khi thực hiện thao tác thay đổi trạng thái.
5. Server so sánh token nhận được với token gắn với session.
6. Nếu thiếu, sai hoặc không thuộc session hiện tại, từ chối request trước khi thay đổi dữ liệu.

CSRF token không phải access token và không thay thế JWT. Nó chứng minh request có một giá trị mà trang attacker không thể lấy được trong điều kiện Same-Origin Policy và các kiểm soát liên quan.

### 9.1. Yêu cầu đối với token

- Sinh bằng CSPRNG, có entropy đủ lớn (thường tối thiểu 128 bit ngẫu nhiên).
- Gắn với session hoặc security context cụ thể.
- Không đặt trong URL, query string hoặc fragment.
- Không log token.
- Kiểm tra chính xác và từ chối khi thiếu hoặc sai.
- Rotate khi đăng nhập, đăng xuất, thay đổi session hoặc nâng quyền.
- Có thể dùng token ổn định theo session để hỗ trợ nhiều tab; tránh single-use token nếu không có cơ chế xử lý request đồng thời rõ ràng.

Không dùng sub, email, timestamp hoặc một chuỗi dễ đoán làm CSRF token.

## 10. Synchronizer Token Pattern

Synchronizer Token Pattern phù hợp với ứng dụng có server-side session hoặc có nơi lưu trạng thái CSRF tương ứng.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Web application
    B->>S: GET trang đã xác thực (cookie session/JWT)
    S->>S: Tạo/lấy CSRF token gắn với session
    S-->>B: HTML/JSON chứa CSRF token
    B->>S: POST thay đổi trạng thái + cookie + CSRF header
    S->>S: Kiểm tra cookie và CSRF token
    alt Token hợp lệ
        S->>S: Thực hiện thao tác sau authorization
        S-->>B: Thành công
    else Token thiếu hoặc sai
        S-->>B: Từ chối request
    end
~~~

### 10.1. Lưu và phân phối token

Server lưu token trong session hoặc store gắn với session ID. Token có thể được nhúng vào HTML server-rendered hoặc trả qua endpoint bootstrap JSON được bảo vệ bằng authentication.

Với SPA cùng origin:

- API bootstrap trả CSRF token sau khi session/cookie đã được xác thực.
- JavaScript lưu token trong memory hoặc state của ứng dụng.
- Mỗi request thay đổi trạng thái gửi token qua custom header, ví dụ X-CSRF-Token.
- Server so sánh với giá trị gắn với session cookie.

Không đặt CSRF token trong URL vì URL có thể đi vào browser history, access log, analytics, referrer hoặc screenshot.

### 10.2. Xử lý session rotation

Khi đăng nhập hoặc nâng quyền, session identifier thường được thay đổi để chống session fixation. CSRF token cần được tạo lại hoặc ràng buộc với session mới. Token cũ không nên tiếp tục được chấp nhận nếu session cũ đã hết hiệu lực.

### 10.3. Stateless JWT có dùng Synchronizer Token được không?

Có thể, nhưng cần nơi lưu trạng thái CSRF hoặc session context tương ứng. “JWT stateless” không có nghĩa toàn bộ hệ thống bắt buộc phải stateless. Nếu kiến trúc không muốn lưu CSRF token phía server, có thể cân nhắc Signed Double-Submit Cookie ở phần tiếp theo.

## 11. Signed Double-Submit Cookie

Double-submit cookie dùng hai bản sao của cùng một CSRF token:

- Một bản được đặt trong cookie mà JavaScript của ứng dụng có thể đọc.
- Một bản được gửi lại trong custom header hoặc request field.

Server kiểm tra hai giá trị khớp nhau. Tuy nhiên, cách double-submit đơn giản có thể bị tấn công cookie injection nếu attacker kiểm soát được subdomain hoặc có cách đặt cookie cho domain cha.

Vì vậy, ưu tiên **Signed Double-Submit Cookie**: token được ký bằng HMAC và ràng buộc với session context.

### 11.1. Luồng tổng quát

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Server
    B->>S: Request đã xác thực bằng cookie JWT
    S->>S: Tạo random nonce và MAC gắn với session
    S-->>B: Set-Cookie csrf=<nonce>.<mac>
    Note over B: JavaScript đọc cookie CSRF
    B->>S: POST + cookie csrf + header X-CSRF-Token
    S->>S: So sánh cookie/header
    S->>S: Kiểm tra MAC và session binding
    S-->>B: Chấp nhận hoặc từ chối
~~~

### 11.2. Token có chữ ký và ràng buộc session

Một dạng khái niệm:

~~~text
random = CSPRNG(32 bytes)
message = session_binding || "." || random
mac = HMAC(csrf_secret, message)
csrf_token = BASE64URL(random) || "." || BASE64URL(mac)
~~~

Trong đó:

- csrf_secret là secret riêng của cơ chế CSRF, được bảo vệ phía server.
- session_binding là định danh session ổn định, không phải một giá trị do request tự khai báo.
- random là nonce ngẫu nhiên.
- Server tái tính MAC và so sánh theo cách an toàn.

Ví dụ này chỉ mô tả cấu trúc; định dạng mã hóa và xử lý byte phải được chuẩn hóa trong triển khai. Không dùng JWT signing key làm csrf_secret.

### 11.3. Vì sao cần ràng buộc session?

Nếu MAC chỉ ký một nonce mà không gắn với session, token có thể bị chuyển từ một phiên người dùng sang phiên khác trong một số tình huống cookie injection hoặc token confusion. Binding làm token chỉ hợp lệ trong session tương ứng.

Nếu JWT mang một claim session identifier ổn định, server có thể dùng giá trị đó làm binding sau khi JWT đã được xác minh. Không dùng riêng sub nếu một người dùng có nhiều phiên độc lập. Nếu không có session binding đáng tin, hãy dùng Synchronizer Token Pattern hoặc bổ sung session context phù hợp.

### 11.4. Double-submit cookie đơn giản có giới hạn gì?

Không nên chỉ kiểm tra:

~~~text
cookie_csrf == request_header_csrf
~~~

Attacker có thể tìm cách đặt cookie từ subdomain, response injection hoặc cấu hình Domain quá rộng. Nếu attacker kiểm soát được giá trị cookie và gửi cùng giá trị trong request, phép so sánh đơn thuần không chứng minh token được server phát hành cho session hợp lệ.

Signed/session-bound double-submit giúp chống giả mạo cookie theo mô hình này. Cookie CSRF phải được thiết kế để JavaScript đọc được nếu dùng header pattern; cookie xác thực vẫn nên là HttpOnly.

## 12. Custom request header và CORS

Với SPA, một custom header như X-CSRF-Token hoặc X-Requested-With có thể là tín hiệu chống CSRF. Browser không cho một HTML form thông thường tự đặt custom header tùy ý. Request cross-origin có custom header thường cần CORS preflight trước khi gửi request thực tế.

Tuy nhiên, custom header chỉ hữu ích khi server:

- Yêu cầu header đó trên mọi endpoint thay đổi trạng thái.
- Kiểm tra token trong header theo cơ chế đã thiết kế.
- Không có fallback cho phép form hoặc request không header thực hiện cùng hành động.
- Cấu hình CORS chặt chẽ.

### 12.1. CORS không tự thay thế CSRF defense

CORS chủ yếu quyết định JavaScript ở origin khác có được phép đọc response và, với preflight, có được phép gửi một số loại request hay không. Form HTML và các request đơn giản có thể được gửi mà không cần preflight; server vẫn có thể thực hiện side effect trước khi browser chặn việc đọc response.

Do đó:

- Không bật CORS rộng rồi coi đó là CSRF protection.
- Không phản chiếu tùy ý header Origin vào Access-Control-Allow-Origin.
- Không kết hợp Access-Control-Allow-Credentials: true với wildcard origin.
- Dùng allowlist origin chính xác, bao gồm scheme, host và port.
- Chỉ cho phép methods/headers cần thiết.
- Dùng Vary: Origin khi response thay đổi theo Origin.

### 12.2. Credentialed CORS cho SPA khác origin

Nếu SPA ở https://ui.example.test gọi API https://api.example.test bằng cookie:

- Client phải gửi request ở chế độ credentials phù hợp.
- API phải trả Access-Control-Allow-Origin đúng origin đã cho phép.
- API phải bật Access-Control-Allow-Credentials: true khi cần.
- Cookie phải có thuộc tính phù hợp với cross-site/same-site deployment.
- API vẫn cần CSRF token và/hoặc Origin validation.

Hai host khác nhau có thể cùng site nhưng khác origin. CORS kiểm soát origin; SameSite xét site. Đừng nhầm hai khái niệm khi thiết kế cookie và allowlist.

## 13. Kiểm tra Origin và Referer

Với request thay đổi trạng thái, server có thể kiểm tra header Origin và khi cần dùng Referer làm tín hiệu bổ sung.

### 13.1. Kiểm tra Origin chính xác

Origin gồm scheme, host và port. So sánh với allowlist đã cấu hình:

~~~text
Allowed:
https://app.example.test

Reject:
http://app.example.test
https://app.example.test.attacker.test
https://app.example.test:8443
https://attacker.example.test
~~~

Không dùng phép kiểm tra chuỗi kiểu startsWith, endsWith hoặc chỉ so hostname một cách thiếu kiểm soát. Không lấy origin mong đợi từ header do request cung cấp.

### 13.2. Khi Origin thiếu hoặc là null

Một số request không có Origin hoặc có Origin: null, tùy loại client, browser, sandbox hoặc privacy policy. Với endpoint nhạy cảm:

- Ưu tiên từ chối nếu Origin thiếu và không có fallback được thiết kế.
- Có thể kiểm tra Referer nếu policy cho phép và header có mặt.
- Không chấp nhận null như một origin đáng tin mặc định.
- Nếu cần hỗ trợ client không phải browser, thiết kế authentication path riêng thay vì nới lỏng browser endpoint.

### 13.3. Referer fallback

Nếu Origin không có, có thể dùng Referer để xác định origin nguồn bằng cách parse URL và so sánh scheme/host/port. Không so khớp chuỗi tùy tiện. Referer có thể bị lược bỏ bởi browser hoặc Referrer-Policy; vì vậy đây là tín hiệu bổ sung và phải có policy rõ khi thiếu.

Origin/Referer validation có thể chặn nhiều CSRF cross-origin nhưng không đủ chống same-site attacker nếu allowlist quá rộng hoặc có subdomain không đáng tin.

## 14. Fetch Metadata headers

Browser hiện đại có thể gửi các header như:

- Sec-Fetch-Site: same-origin, same-site, cross-site hoặc none.
- Sec-Fetch-Mode: cách request được khởi tạo, ví dụ navigate, cors, no-cors.
- Sec-Fetch-Dest: đích của request, ví dụ document, image, empty.

Server có thể dùng chúng làm lớp phòng vệ bổ sung:

| Giá trị Sec-Fetch-Site | Xử lý tham khảo cho endpoint thay đổi trạng thái |
| --- | --- |
| same-origin | Có thể tiếp tục kiểm tra CSRF token và authorization. |
| same-site | Không mặc định tin; đánh giá subdomain và trust boundary. |
| cross-site | Thường từ chối với endpoint nhạy cảm, trừ luồng cross-site đã được thiết kế rõ. |
| none | Có thể là user-initiated navigation; phải xét method và endpoint. |
| Header thiếu | Dùng fallback như CSRF token và Origin validation. |

Không chỉ dựa vào Fetch Metadata vì client cũ, native client hoặc intermediary có thể không gửi header. Không tin header Sec-* do client không phải browser tự khai báo như bằng chứng duy nhất; kết hợp với CSRF token, cookie policy và Origin checks.

## 15. Safe methods và thiết kế endpoint

Theo ngữ nghĩa HTTP, các method an toàn như GET, HEAD và OPTIONS không được dùng để yêu cầu thay đổi trạng thái nghiệp vụ. Endpoint thay đổi dữ liệu nên dùng method phù hợp như POST, PUT, PATCH hoặc DELETE và áp dụng CSRF protection.

Ví dụ:

| Hành động | Thiết kế phù hợp |
| --- | --- |
| Xem thông tin tài khoản | GET |
| Tạo giao dịch | POST |
| Đổi email | PATCH hoặc POST |
| Xóa API key | DELETE hoặc POST theo contract |
| Đăng xuất | POST hoặc luồng có kiểm soát CSRF |

Không tạo endpoint như GET /logout, GET /transfer?to=..., GET /delete-account. Một crawler, preview bot, prefetcher hoặc link attacker có thể kích hoạt GET mà không có ý định thay đổi trạng thái từ người dùng.

CSRF protection phải được áp dụng cho mọi thao tác có side effect, kể cả logout, thay đổi thông tin bảo mật, thêm thiết bị tin cậy và tạo/thu hồi credential.

## 16. Login CSRF và luồng OAuth/OIDC

CSRF có thể xảy ra trước cả khi người dùng đã đăng nhập vào ứng dụng mục tiêu. **Login CSRF** là khi attacker khiến trình duyệt nạn nhân đăng nhập vào tài khoản do attacker kiểm soát hoặc gắn một phiên xác thực sai với trình duyệt nạn nhân.

### 16.1. OAuth state

Trong Authorization Code Flow, client tạo giá trị state khó đoán, gắn với giao dịch đăng nhập của browser và kiểm tra lại khi nhận callback. Điều này giúp chống callback bị giả mạo hoặc gắn nhầm với một authorization request khác.

State phải được ràng buộc với browser transaction/session đang chờ; không chấp nhận một giá trị tùy ý chỉ vì callback có tham số state.

### 16.2. OpenID Connect nonce

OIDC nonce được tạo cho authentication request và kiểm tra trong ID Token để ràng buộc token với request đó, giúp chống replay và nhầm lẫn response. Nonce có mục đích riêng; không dùng nó thay cho CSRF token của mọi API.

### 16.3. PKCE

PKCE ràng buộc authorization code với code verifier của client và giảm nguy cơ code interception. Trong một số cấu hình client, PKCE cũng cung cấp bảo vệ chống CSRF theo điều kiện của OAuth Security BCP. Tuy nhiên, vẫn phải thiết kế và kiểm tra state/transaction binding theo profile và threat model; PKCE không thay thế CSRF defense cho các endpoint web dùng cookie thông thường.

## 17. Kết hợp các lớp phòng vệ

Không nên phụ thuộc vào một cơ chế duy nhất. Một cấu hình thực tế có thể kết hợp:

1. Cookie xác thực Secure, HttpOnly, host-only và SameSite=Lax hoặc Strict theo nhu cầu.
2. CSRF token cho mọi request thay đổi trạng thái.
3. Custom header cho SPA và kiểm tra token phía server.
4. Origin/Referer allowlist cho browser request.
5. Fetch Metadata để chặn request cross-site rõ ràng.
6. CORS allowlist chặt nếu frontend và API khác origin.
7. Không dùng GET cho thao tác thay đổi trạng thái.
8. Authentication và authorization độc lập với CSRF validation.

~~~mermaid
flowchart TD
    A["Nhận request"] --> B["Xác định endpoint và method"]
    B --> C{"Có thay đổi trạng thái?"}
    C -- Không --> D["Authentication và policy thông thường"]
    C -- Có --> E["Kiểm tra cookie/session credential"]
    E --> F["Kiểm tra Origin / Referer"]
    F --> G["Kiểm tra Fetch Metadata"]
    G --> H["Kiểm tra CSRF token / custom header"]
    H --> I{"Các kiểm tra đạt?"}
    I -- Không --> X["Từ chối, ghi reason code an toàn"]
    I -- Có --> J["Xác minh JWT và authorization"]
    J --> K{"Token và quyền hợp lệ?"}
    K -- Không --> X
    K -- Có --> L["Thực hiện side effect"]
~~~

Thứ tự thực tế có thể khác để tối ưu hiệu năng, nhưng không được thực hiện side effect trước khi hoàn tất authentication, CSRF validation và authorization cần thiết. Với token invalid hoặc dependency xác minh không khả dụng, không cho request tiếp tục.

## 18. Pseudocode kiểm tra CSRF cho cookie-authenticated request

Pseudocode tổng quát:

~~~text
function handleRequest(request):
    route = resolveRoute(request)

    if route.changesState:
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            reject("unsafe state-changing method design")

        session = authenticateCookieCredential(request.cookies)
        if session is invalid:
            rejectAuthentication()

        if not originAllowed(request.origin, configuredOrigins):
            rejectCsrf()

        if fetchMetadataIndicatesCrossSite(request):
            rejectCsrf()

        csrfToken = readCsrfHeaderOrFormField(request)
        if not verifyCsrfToken(session, csrfToken):
            rejectCsrf()

        authorization = authorize(session, route.requiredPermission)
        if authorization is denied:
            rejectForbidden()

        executeStateChange()
        return success()

    return handleReadOnlyRequestWithNormalAuthenticationAndAuthorization()
~~~

Đây là mô hình khái niệm. Endpoint thực tế cần xác định rõ method, cookie scope, Origin policy, CSRF token format, session binding và các ngoại lệ giao thức. Không tạo ngoại lệ rộng cho toàn bộ route chỉ vì một endpoint có callback cross-site.

## 19. Xử lý lỗi CSRF và quan sát vận hành

Khi CSRF validation thất bại:

- Từ chối request trước side effect.
- Trả response chung như 403 Forbidden hoặc error code của API đã công bố.
- Không tiết lộ CSRF token mong đợi, session identifier hoặc chi tiết MAC.
- Ghi reason code nội bộ, ví dụ CSRF_TOKEN_MISSING, CSRF_TOKEN_INVALID, CSRF_ORIGIN_REJECTED hoặc CSRF_FETCH_METADATA_REJECTED.
- Không ghi cookie xác thực, CSRF token hoặc toàn bộ request body vào log.
- Có request ID để liên hệ với log và trace.

Một số lỗi CSRF có thể do client lỗi, token stale sau session rotation hoặc cấu hình frontend/API sai. Theo dõi tỷ lệ lỗi theo route, client profile và origin profile đã được chuẩn hóa. Không dùng raw Origin hoặc session ID làm metric label không giới hạn.

Nếu CSRF failures tăng đột biến từ một origin hoặc một route, kiểm tra khả năng tấn công, cấu hình CORS, SameSite rollout và thay đổi frontend. Không tự động nới lỏng CSRF validation để làm giảm lỗi.

## 20. Kiểm thử CSRF

Kiểm thử cần bao gồm cả cross-site, same-site, browser navigation và các thay đổi cookie.

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Request POST hợp lệ từ ứng dụng, cookie và CSRF token đúng | Chấp nhận nếu authentication/authorization hợp lệ. |
| Request POST thiếu CSRF token | Từ chối trước side effect. |
| CSRF token sai hoặc không gắn với session | Từ chối. |
| Cookie xác thực hợp lệ nhưng request đến từ origin lạ | Từ chối theo Origin policy. |
| Request cross-site có Sec-Fetch-Site: cross-site | Từ chối với endpoint nhạy cảm theo policy. |
| Request từ subdomain same-site không đáng tin | Origin/token policy vẫn chặn. |
| Cookie SameSite=Lax trong cross-site form POST | Không dựa riêng vào cookie behavior; CSRF check vẫn phải bảo vệ. |
| Cookie SameSite=None; Secure | CSRF token và Origin validation vẫn được áp dụng. |
| GET cố thay đổi dữ liệu | Endpoint không thực hiện side effect. |
| Session đổi sau đăng nhập/nâng quyền | CSRF token cũ không được chấp nhận nếu binding đã đổi. |
| CORS nhận Origin không nằm trong allowlist | Không cấp quyền credentialed CORS. |
| Request không có Origin/Referer | Xử lý theo fallback policy đã định, không mặc định tin. |
| OAuth callback có state không khớp | Từ chối transaction. |
| OIDC ID Token có nonce không khớp | Từ chối authentication response. |

### 20.1. Kiểm tra browser thực tế

Hành vi cookie có thể khác theo browser, phiên bản, privacy setting và chính sách third-party cookie. Kiểm thử tối thiểu:

- SameSite Strict, Lax và None.
- Top-level navigation GET và cross-site form POST.
- Same-origin, same-site khác origin và cross-site.
- Cookie host-only so với cookie có Domain.
- Browser chặn third-party cookie.
- Callback OAuth/OIDC từ identity provider.

Không suy ra toàn bộ bảo mật chỉ từ một lần thử trên localhost hoặc một browser.

## 21. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Nghĩ JWT có chữ ký nên không cần CSRF | Cookie vẫn được browser tự gửi; attacker không cần biết token. | Dùng CSRF defense cho cookie-authenticated state changes. |
| Nghĩ HttpOnly chống CSRF | Cookie vẫn được gửi tự động. | Kết hợp SameSite, CSRF token và Origin checks. |
| Chỉ dựa vào SameSite | Same-site subdomain, luồng đặc biệt hoặc browser khác có thể tạo khoảng trống. | Defense-in-depth. |
| Chỉ so cookie CSRF với header CSRF | Cookie injection có thể giả mạo double-submit đơn giản. | Dùng synchronizer token hoặc signed/session-bound double-submit. |
| Chỉ dựa vào CORS | Request đơn giản/form vẫn có thể gây side effect dù response không đọc được. | CSRF token và Origin validation. |
| Cho GET thay đổi trạng thái | Link, image, crawler hoặc prefetch có thể kích hoạt hành động. | Dùng method không an toàn theo HTTP semantics và CSRF validation. |
| Đặt cookie Domain quá rộng | Subdomain có thể ảnh hưởng cookie hoặc tạo cookie injection. | Ưu tiên host-only cookie và prefix __Host- khi phù hợp. |
| Dùng CSRF token dễ đoán hoặc chung cho mọi user | Attacker có thể tạo hoặc tái sử dụng token. | Token ngẫu nhiên, session-bound và rotate đúng lúc. |
| Đặt CSRF token trong URL | Rò rỉ qua history, log, analytics và referrer. | Gửi qua header hoặc request body. |
| Bỏ CSRF cho mọi endpoint vì có một OAuth callback | Tạo ngoại lệ quá rộng. | Xử lý callback theo state/transaction riêng và giữ CSRF cho API khác. |
| Dùng sub đơn thuần làm session binding | Các session khác nhau của cùng user có thể dùng chung binding. | Dùng session identifier riêng hoặc synchronizer token. |
| Dùng JWT signing secret làm CSRF HMAC secret | Ghép hai miền mật mã và tăng phạm vi ảnh hưởng. | Secret CSRF riêng, purpose-specific. |

## 22. Checklist triển khai

**Cookie và credential**

- [ ] Cookie xác thực có Secure và HttpOnly.
- [ ] SameSite được chọn theo luồng browser thực tế; không mặc định dùng None.
- [ ] Ưu tiên host-only cookie; tránh Domain rộng nếu không cần.
- [ ] Dùng __Host- khi phù hợp với yêu cầu Secure, Path=/ và không có Domain.
- [ ] Không truyền bearer token trong URL.

**CSRF validation**

- [ ] Mọi request thay đổi trạng thái có CSRF protection.
- [ ] Dùng Synchronizer Token hoặc Signed Double-Submit session-bound phù hợp kiến trúc.
- [ ] Token đủ ngẫu nhiên, gắn session và rotate khi session thay đổi.
- [ ] Không dùng double-submit đơn giản mà thiếu cookie-injection protection.
- [ ] Kiểm tra Origin/Referer và Fetch Metadata theo policy.
- [ ] CORS credentialed chỉ cho phép origin cụ thể.
- [ ] GET/HEAD/OPTIONS không thực hiện side effect.

**JWT và luồng xác thực**

- [ ] JWT cookie vẫn được xác minh chữ ký, issuer, audience, thời hạn và profile.
- [ ] CSRF validation không bị nhầm với JWT validation hoặc authorization.
- [ ] OAuth callback kiểm tra state và OIDC kiểm tra nonce theo profile.
- [ ] PKCE được triển khai đúng và không bị xem là thay thế mọi CSRF defense.

**Vận hành và kiểm thử**

- [ ] CSRF failure bị từ chối trước side effect.
- [ ] Log không chứa JWT, cookie hoặc CSRF token.
- [ ] Có metrics và cảnh báo theo route/origin profile đã chuẩn hóa.
- [ ] Kiểm thử cross-site, same-site, subdomain và browser behavior.
- [ ] Có runbook khi CSRF failures tăng đột biến hoặc cookie policy thay đổi.

## 23. Tài liệu chuẩn tham khảo

- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): Synchronizer Token, Double-Submit Cookie, SameSite, Origin và Fetch Metadata.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): cookie, Domain, Path và cơ chế quản lý trạng thái HTTP.
- [RFC 6265bis — Cookies: HTTP State Management Mechanism](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/): các thuộc tính cookie hiện đại, bao gồm SameSite; cần kiểm tra trạng thái phiên bản chuẩn khi triển khai.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa method an toàn và semantics HTTP.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): tham số state trong authorization request/response.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): PKCE và code verifier/challenge.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ authorization flow và CSRF trong OAuth.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): nonce và kiểm tra ID Token.
- [Fetch Metadata Request Headers](https://www.w3.org/TR/fetch-metadata/): Sec-Fetch-Site, Sec-Fetch-Mode và Sec-Fetch-Dest.

**Ghi nhớ:** cookie xác thực được browser tự gửi nên JWT hợp lệ không chứng minh request có ý định hợp lệ. Dùng SameSite làm lớp giảm rủi ro, CSRF token gắn session để xác nhận request, Origin/Fetch Metadata để kiểm tra nguồn và CORS để giới hạn truy cập cross-origin. Bảo vệ mọi thao tác thay đổi trạng thái trước khi thực hiện side effect.
