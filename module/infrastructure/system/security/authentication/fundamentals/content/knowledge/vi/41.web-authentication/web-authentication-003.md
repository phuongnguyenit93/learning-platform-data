# CSRF và authentication

## 1. CSRF là gì?

**Cross-Site Request Forgery (CSRF)** là kiểu tấn công khiến browser của nạn nhân gửi một request ngoài ý muốn tới website mà nạn nhân đang đăng nhập. Vì browser có thể tự động đính kèm cookie session hoặc credential khác, server nhìn thấy request có vẻ đến từ một phiên hợp lệ và thực hiện hành động dưới danh nghĩa nạn nhân.

Ví dụ, người dùng đang đăng nhập vào trang ngân hàng. Attacker dụ họ mở một trang web khác có form tự gửi request chuyển tiền tới ngân hàng. Browser có thể đính kèm cookie session của ngân hàng vào request. Nếu ngân hàng chỉ kiểm tra cookie mà không xác minh request có được khởi tạo từ luồng hợp lệ, giao dịch có thể được thực hiện.

CSRF không nhất thiết đánh cắp password hoặc đọc response. Attacker thường lợi dụng **ambient authority**: browser tự mang credential theo request dựa trên cookie domain, path và SameSite policy. Server nhận được credential hợp lệ nhưng không biết người dùng có chủ ý thực hiện hành động đó hay không.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, CSRF kết nối authentication, session cookie, browser security model, OAuth/OIDC, API authorization và trust boundary. Bảo vệ CSRF cần kiểm tra nguồn gốc request và ý định của luồng tương tác, đặc biệt với các thao tác làm thay đổi trạng thái.

Sau bài học, người học có thể:

- Giải thích vì sao cookie authentication tạo bề mặt CSRF.
- Phân biệt CSRF với XSS, CORS và authentication bypass.
- Nhận diện các điều kiện để CSRF thành công.
- Áp dụng synchronizer token và signed double-submit cookie.
- Kết hợp SameSite, Origin/Referer và Fetch Metadata.
- Bảo vệ login, logout và các thao tác thay đổi trạng thái.
- Hiểu vai trò khác nhau của OAuth state, OIDC nonce và PKCE.
- Phân biệt cookie session với bearer token được client chủ động gắn vào header.
- Kiểm thử CSRF trên form, fetch, iframe, subdomain và WebSocket.

## 2. Vì sao CSRF liên quan tới authentication?

Authentication xác minh credential hoặc session thuộc về principal nào. Khi người dùng đăng nhập, server thường tạo session ID và gửi về browser dưới dạng cookie. Trong những request tiếp theo, browser tự gửi cookie tới domain phù hợp.

Điều này tạo ra một đặc tính tiện lợi nhưng có rủi ro: website nhận cookie có thể không phân biệt request do người dùng chủ động tạo với request do một trang khác khiến browser gửi đi.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant A as Attacker Site
    participant S as Website đã đăng nhập
    U->>B: Đăng nhập Website
    B->>S: POST /login
    S-->>B: Set-Cookie: session
    U->>B: Mở Attacker Site
    A-->>B: Form gửi POST tới Website
    B->>S: POST /transfer + session cookie
    S->>S: Xác minh session
    Note over S: Nếu thiếu CSRF defense,<br/>request có thể bị coi là hợp lệ
    S-->>B: Thực hiện hành động
~~~

Server có thể xác minh session cookie hoàn toàn đúng mà vẫn bị CSRF. Cookie chứng minh browser đang sở hữu session, nhưng không chứng minh người dùng đã chủ động khởi tạo request cụ thể.

### 2.1. Ambient authority

Ambient authority là quyền được browser tự động mang theo khi truy cập một origin hoặc domain. Cookie session là ví dụ phổ biến. Một số credential hoặc cơ chế xác thực tích hợp của browser cũng có thể được tự động gửi trong điều kiện nhất định.

CSRF xuất hiện khi:
- Nạn nhân đã có session hoặc credential hợp lệ.
- Browser tự động gửi credential tới website mục tiêu.
- Attacker có cách khiến browser tạo request tới endpoint thay đổi trạng thái.
- Server không kiểm tra đầy đủ request có xuất phát từ luồng hợp lệ hay không.
- Hành động có thể hoàn tất mà không cần xác nhận độc lập phù hợp.

Không cần attacker đọc response. Việc gửi request và kích hoạt side effect đã có thể đủ để gây thiệt hại.

### 2.2. Ví dụ form HTML

Một trang độc hại có thể chứa form gửi request cross-site:

~~~html
<form action="https://bank.example.test/transfer" method="POST">
  <input type="hidden" name="destination" value="attacker-account">
  <input type="hidden" name="amount" value="5000000">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Đoạn mã chỉ minh họa cơ chế. Nếu browser gửi cookie session và server không có biện pháp chống CSRF, request có thể được xử lý như thao tác của người dùng đã đăng nhập.

### 2.3. Same-Origin Policy không tự ngăn CSRF

Same-Origin Policy (SOP) chủ yếu giới hạn script ở origin này đọc dữ liệu của origin khác. Nó không cấm mọi request cross-origin. HTML form, image, navigation và một số request đơn giản vẫn có thể được gửi.

Vì vậy, việc attacker không đọc được response không đồng nghĩa họ không thể khiến server thực hiện hành động. CSRF defense phải kiểm tra request tại server.

## 3. Điều kiện và bề mặt tấn công

Không phải mọi endpoint đều dễ bị CSRF như nhau. Rủi ro phụ thuộc cách browser gửi credential và cách server xử lý request.

| Điều kiện | Ví dụ |
| --- | --- |
| Credential được gửi tự động | Session cookie, cookie SSO hoặc HTTP authentication được browser quản lý |
| Endpoint có side effect | Chuyển tiền, đổi email, thêm API key, thay đổi quyền |
| Request có thể được khởi tạo cross-site | Form POST, navigation, iframe hoặc request đơn giản |
| Server không xác minh request origin/intent | Chỉ kiểm tra session cookie |
| Không có token hoặc challenge ràng buộc | Request không có CSRF token hợp lệ |
| Browser gửi cookie trong ngữ cảnh đó | SameSite policy cho phép gửi cookie |

Các thao tác thường cần bảo vệ:
- Thay đổi password, email, số điện thoại hoặc recovery method.
- Thêm/xóa passkey, MFA factor hoặc security key.
- Tạo/revoke API key.
- Thay đổi role, permission hoặc membership.
- Tạo giao dịch, thanh toán hoặc chuyển tiền.
- Thay đổi địa chỉ, dữ liệu cá nhân hoặc cấu hình bảo mật.
- Đăng xuất một session hoặc tất cả session.

Endpoint chỉ đọc dữ liệu cũng cần xem xét nếu request làm thay đổi trạng thái phụ, như đánh dấu đã đọc, tiêu thụ token hoặc ghi nhận hành động có ý nghĩa bảo mật.

## 4. CSRF, XSS và CORS khác nhau thế nào?

Ba khái niệm thường bị nhầm:

| Khái niệm | Vấn đề chính | Khả năng thường gặp |
| --- | --- | --- |
| **CSRF** | Browser gửi request ngoài ý muốn kèm credential tự động | Kích hoạt hành động dưới session của nạn nhân |
| **XSS** | Attacker chạy script trong origin đáng tin | Đọc token CSRF, thao tác DOM và gửi request như ứng dụng |
| **CORS** | Server khai báo origin nào được browser cho phép đọc response cross-origin | Kiểm soát quyền đọc response của JavaScript |

XSS có thể phá vỡ nhiều biện pháp CSRF vì script chạy trong origin hợp lệ có thể đọc token CSRF và tạo request hợp lệ. Vì vậy CSRF token không thay thế XSS prevention.

CORS cũng không phải cơ chế authentication. Một request form đơn giản có thể được gửi dù browser không cho attacker đọc response. CORS preflight có thể ngăn một số request JavaScript không đơn giản nếu server không cho phép origin, nhưng không nên dựa riêng vào CORS để bảo vệ mọi endpoint.

## 5. Synchronizer token pattern

**Synchronizer token pattern** là cách bảo vệ CSRF phổ biến cho ứng dụng dùng session server-side. Server tạo một token ngẫu nhiên gắn với session, đưa token tới trang/form hợp lệ và yêu cầu client gửi lại token trong request thay đổi trạng thái.

Quy trình:

1. Người dùng đăng nhập và có session.
2. Server tạo CSRF token khó đoán, gắn với session.
3. Server render token vào form hoặc cung cấp cho frontend qua response cùng origin.
4. Client gửi token trong hidden field hoặc custom request header.
5. Server lấy token dự kiến từ session và so sánh với token request.
6. Nếu token thiếu hoặc không khớp, từ chối request trước khi thực hiện side effect.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Application Server
    B->>S: GET /settings (session cookie)
    S->>S: Resolve session và CSRF token
    S-->>B: HTML/JSON có CSRF token
    B->>S: POST /settings + cookie + CSRF token
    S->>S: Verify session
    S->>S: Compare CSRF token với session
    alt Token hợp lệ
        S->>S: Validate và thực hiện thay đổi
        S-->>B: Success
    else Token sai hoặc thiếu
        S-->>B: Reject request
    end
~~~

### 5.1. Yêu cầu đối với token

CSRF token cần:
- Được sinh bằng CSPRNG.
- Không thể đoán hoặc suy ra từ session ID, user ID hay timestamp.
- Gắn với session hoặc security context cụ thể.
- Được kiểm tra phía server.
- Không được chấp nhận khi thiếu hoặc sai.
- Không xuất hiện trong URL, access log hoặc analytics.
- Được bảo vệ khỏi rò rỉ qua XSS, referrer hoặc script bên thứ ba.

Token có thể ổn định trong vòng đời session hoặc được rotate theo request/transaction. Token per-request có thể giảm một số cửa sổ sử dụng lại nhưng gây khó khăn với nhiều tab, back button và request song song. Chọn semantics nhất quán, có kiểm thử.

### 5.2. Token không phải credential đăng nhập

CSRF token không chứng minh danh tính người dùng và không thay session cookie. Nó là bằng chứng bổ sung cho thấy request được tạo trong ngữ cảnh ứng dụng đã cấp token.

Không dùng CSRF token làm access token, API key hoặc bằng chứng authorization. Người có session hợp lệ vẫn cần được kiểm tra quyền trên resource/action.

### 5.3. Truyền token trong form hoặc header

Với form HTML, token có thể nằm trong hidden field. Với SPA, frontend thường nhận token qua response cùng origin rồi gửi custom header như X-CSRF-Token.

Không đặt token trong query string vì URL có thể bị ghi vào browser history, proxy log, analytics hoặc Referer. Không trả token cho origin không đáng tin thông qua CORS.

## 6. Double-submit cookie pattern

Double-submit cookie pattern dùng hai bản thể hiện của cùng một token:
- Một bản được browser lưu trong cookie.
- Một bản client gửi lại trong request body hoặc custom header.

Server so sánh hai giá trị. Attacker ở origin khác thường không thể đọc cookie do SOP để sao chép token vào header/body. Tuy nhiên, triển khai ngây thơ có thể bị cookie injection nếu attacker kiểm soát subdomain hoặc có thể đặt cookie cùng tên.

### 6.1. Signed double-submit

Một biến thể an toàn hơn ràng buộc token với session hoặc dữ liệu bí mật server giữ. Ví dụ, token có thể gồm nonce ngẫu nhiên và MAC được tính từ nonce cùng session binding. Server xác minh MAC và binding thay vì chỉ so sánh hai chuỗi.

Không dùng double-submit đơn giản nếu threat model có subdomain không đáng tin hoặc cookie scope rộng. Cookie domain và prefix cần được thiết kế để giảm khả năng sibling subdomain ghi đè.

### 6.2. Khi nào dùng synchronizer hay double-submit?

| Tiêu chí | Synchronizer token | Signed double-submit |
| --- | --- | --- |
| Lưu token | Server gắn token với session | Token có thể tự xác minh bằng MAC/session binding |
| Phụ thuộc session store | Có | Có thể giảm nhu cầu lưu token riêng |
| SPA | Có thể trả token qua endpoint cùng origin | Có thể đọc CSRF cookie và gửi lại |
| Cookie injection | Ít phụ thuộc cookie CSRF | Cần chống cookie injection và binding |
| Độ phức tạp | Cần quản lý token server-side | Cần thiết kế chữ ký/binding đúng |

Chọn theo kiến trúc session, khả năng scale, threat model và framework. Dùng CSRF middleware đã được duy trì nếu có, thay vì tự triển khai cryptography.

## 7. SameSite cookie

Thuộc tính SameSite điều khiển khi nào browser gửi cookie trong request cross-site. Nó là lớp phòng vệ quan trọng vì giảm việc browser tự đính kèm session cookie vào một số request xuất phát từ site khác.

| Giá trị | Hành vi khái quát | Lưu ý |
| --- | --- | --- |
| **Strict** | Hạn chế gửi cookie trong hầu hết ngữ cảnh cross-site | Có thể ảnh hưởng điều hướng quay lại từ IdP hoặc liên kết bên ngoài |
| **Lax** | Cho phép cookie trong một số top-level navigation an toàn, thường là GET; hạn chế nhiều cross-site subrequest và POST | Phù hợp cho nhiều session cookie web thông thường, nhưng cần kiểm tra flow cụ thể |
| **None** | Cho phép cookie trong cross-site context theo policy browser | Phải dùng Secure; chỉ bật khi kiến trúc thực sự cần |

SameSite là một lớp giảm rủi ro, không nên là biện pháp duy nhất cho mọi ứng dụng. Browser behavior có thể khác theo phiên bản và ngữ cảnh; cần kiểm thử trên browser mục tiêu.

### 7.1. Same-site không đồng nghĩa same-origin

Origin gồm scheme, host và port. Site thường dựa trên scheme và registrable domain. Hai subdomain khác origin có thể vẫn được coi là same-site.

Ví dụ, app.example.test và evil.example.test có thể là hai origin khác nhau nhưng cùng site. Nếu subdomain không đáng tin có thể điều khiển browser hoặc đặt cookie domain rộng, SameSite một mình không đủ. Cần kiểm tra Origin, CSRF token và cookie scope.

### 7.2. Cấu hình session cookie

Một cookie session thường nên có các thuộc tính phù hợp như:
- **Secure:** chỉ gửi qua HTTPS.
- **HttpOnly:** JavaScript không đọc trực tiếp session cookie.
- **SameSite=Lax** hoặc **Strict** theo flow.
- Host-only cookie khi có thể; tránh Domain rộng không cần thiết.
- Path phù hợp.
- Session ID ngẫu nhiên, không chứa thông tin cá nhân.
- Rotation sau login và privilege change.

Prefix **__Host-** có thể giúp ràng buộc cookie với host: yêu cầu Secure, Path=/ và không có Domain. Đây là lựa chọn hữu ích cho session cookie nếu tương thích kiến trúc.

HttpOnly bảo vệ cookie khỏi việc JavaScript đọc trực tiếp nhưng **không ngăn CSRF**: browser vẫn gửi cookie theo quy tắc cookie khi request phù hợp.

### 7.3. SameSite=None và SSO

Một số flow federation hoặc embedded application cần cookie trong cross-site context. Nếu dùng SameSite=None; Secure, phải bổ sung CSRF token, Origin validation và các kiểm soát phù hợp. Không hạ SameSite của mọi cookie chỉ để một luồng SSO hoạt động.

OIDC response mode form_post có thể gửi response từ IdP tới RP bằng cross-site POST; cookie Lax có thể không được gửi trong ngữ cảnh đó. Thiết kế cần xử lý correlation state và cookie theo profile một cách có chủ đích, không tắt CSRF defense.

## 8. Origin và Referer validation

Browser thường gửi Origin trong nhiều request có nguồn gốc cross-origin hoặc request có ý nghĩa bảo mật. Referer có thể chứa URL của trang khởi tạo, tùy Referrer-Policy và browser.

Server có thể kiểm tra request thay đổi trạng thái chỉ đến từ origin chính xác đã cấu hình.

### 8.1. Origin check

- So sánh scheme, host và port với allowlist chính xác.
- Không dùng substring như endsWith("example.test") mà không parse hostname đúng.
- Không tin Origin do client không phải browser tự khai như một credential.
- Xử lý header thiếu hoặc null theo policy.
- Không cho phép wildcard origin cho thao tác nhạy cảm.
- Kiểm tra proxy/forwarded host theo cấu hình tin cậy; không lấy host tùy ý từ request để tự tạo allowlist.

Ví dụ, https://app.example.test.attacker.invalid không phải origin hợp lệ chỉ vì chuỗi có chứa app.example.test.

### 8.2. Referer fallback

Một số request hoặc privacy setting có thể không gửi Origin. Referer có thể được dùng làm tín hiệu bổ sung hoặc fallback, nhưng cần parse origin và so khớp chính xác. Nếu cả hai đều thiếu ở endpoint nhạy cảm, có thể từ chối theo policy hoặc yêu cầu cơ chế khác.

Không yêu cầu full Referer path phải giống nhau; mục tiêu thường là xác minh origin. Cũng không log toàn bộ Referer nếu URL có thể chứa dữ liệu nhạy cảm.

### 8.3. Origin check không thay token

Origin validation giúp xác định trang khởi tạo request trong browser context. Nó không xác thực user, không thay session và không chứng minh quyền trên resource. Một request same-origin vẫn có thể được gửi bởi XSS hoặc script độc hại chạy trong origin hợp lệ.

Kết hợp Origin với CSRF token và XSS prevention.

## 9. Fetch Metadata headers

Browser hiện đại có thể gửi các header như:
- **Sec-Fetch-Site:** quan hệ site của request, ví dụ same-origin, same-site, cross-site hoặc none.
- **Sec-Fetch-Mode:** loại request mode.
- **Sec-Fetch-Dest:** destination context, ví dụ document, image hoặc empty.
- **Sec-Fetch-User:** dấu hiệu navigation được user kích hoạt trong một số trường hợp.

Server có thể dùng Fetch Metadata để từ chối request cross-site không phù hợp, đặc biệt với endpoint thay đổi trạng thái.

Ví dụ policy khái niệm:

~~~text
if request.method changes_state:
    if Sec-Fetch-Site == "cross-site":
        reject unless an explicitly reviewed flow requires it
~~~

Đây chỉ là policy minh họa. Một số luồng hợp lệ như callback từ IdP hoặc payment provider có thể là cross-site. Cần allowlist endpoint/flow cụ thể, kiểm tra state/token và không mở rộng ngoại lệ cho toàn bộ ứng dụng.

Fetch Metadata là lớp phòng vệ bổ sung. Không giả định mọi client đều gửi header này; non-browser client có thể không có. Không cho request thiếu header tự động qua nếu endpoint yêu cầu CSRF protection khác.

## 10. CORS, preflight và custom request headers

CORS kiểm soát việc JavaScript ở origin khác có được đọc response hay không. Với request không đơn giản, browser thường gửi preflight OPTIONS trước khi gửi request thực tế. Một custom header như X-CSRF-Token có thể khiến request cần preflight.

Điều này hữu ích khi:
- API chỉ chấp nhận custom header cho thao tác thay đổi trạng thái.
- CORS allowlist chỉ cho origin tin cậy.
- Server từ chối request không có header bắt buộc.
- Server không phản hồi preflight cho origin độc hại.

Nhưng CORS không phải CSRF defense đầy đủ:
- HTML form vẫn có thể gửi một số request đơn giản.
- Request đơn giản có thể được gửi dù attacker không đọc được response.
- Access-Control-Allow-Origin: * hoặc phản chiếu Origin tùy tiện có thể mở rộng quyền đọc.
- Access-Control-Allow-Credentials: true kết hợp origin validation sai có thể làm lộ dữ liệu.
- CORS không bảo vệ endpoint không dùng browser.

Không dùng Content-Type: application/json như biện pháp duy nhất. Nếu endpoint vẫn chấp nhận application/x-www-form-urlencoded, multipart/form-data hoặc text/plain cho cùng action, attacker có thể dùng form. Hãy kiểm tra content type ở server và yêu cầu CSRF token/origin policy.

## 11. Bảo vệ các HTTP method và endpoint thay đổi trạng thái

GET, HEAD và OPTIONS được kỳ vọng là safe methods theo semantics HTTP. Không thực hiện hành động nghiệp vụ thay đổi trạng thái qua GET.

Không tạo endpoint kiểu:
- GET /logout để xóa session.
- GET /change-email?email=...
- GET /delete-account?id=...
- GET /transfer?...

Dùng POST, PUT, PATCH hoặc DELETE theo semantics API, và áp dụng CSRF protection cho request có side effect khi credential được browser tự động gửi.

Đổi HTTP method không tự ngăn CSRF. Form có thể gửi POST; cần token/origin/SameSite và policy phù hợp.

### 11.1. Idempotency không phải CSRF defense

Idempotency giúp tránh thực hiện side effect lặp khi retry. Nó không chứng minh người dùng chủ động gửi request. Một request CSRF có idempotency key hợp lệ vẫn có thể thực hiện hành động một lần.

### 11.2. Confirmation dialog không đủ

Một trang xác nhận có thể cải thiện UX nhưng không phải bằng chứng bảo mật nếu attacker có thể tự gửi request bỏ qua trang đó. Với hành động rủi ro cao, yêu cầu step-up hoặc transaction confirmation được server xác minh và ràng buộc với nội dung giao dịch.

## 12. Login CSRF

CSRF không chỉ xảy ra sau khi người dùng đã đăng nhập. **Login CSRF** khiến browser nạn nhân đăng nhập vào tài khoản do attacker kiểm soát.

Ví dụ:
1. Attacker đăng nhập vào website bằng tài khoản của chính họ.
2. Attacker tạo hoặc gửi một login request đã được chuẩn bị.
3. Nạn nhân mở trang độc hại khiến browser gửi request tới endpoint login.
4. Browser nạn nhân trở thành session của tài khoản attacker.
5. Nạn nhân nhập thông tin cá nhân hoặc tạo dữ liệu trong tài khoản đó.
6. Attacker đăng nhập lại và xem dữ liệu được lưu vào account của họ.

Biện pháp:
- CSRF token cho login form.
- Origin/Referer validation.
- Fetch Metadata phù hợp.
- Session rotation sau authentication.
- Với federation, ràng buộc response với authorization request.
- Không tự động chấp nhận account hoặc identity context do caller gửi.

Login endpoint cũng là endpoint thay đổi trạng thái session và cần được bảo vệ.

## 13. Logout CSRF và thao tác quản lý tài khoản

Logout CSRF có thể khiến browser nạn nhân đăng xuất ngoài ý muốn. Tác động có thể chỉ là gián đoạn, nhưng trong một số flow có thể gây nhầm lẫn hoặc hỗ trợ các cuộc tấn công khác.

Dùng POST hoặc một phương thức thay đổi trạng thái có CSRF protection cho logout. Không dùng GET để kết thúc session. Nếu logout được khởi tạo từ IdP hoặc SSO, tuân thủ giao thức và xác minh logout request/token đúng profile.

Các thao tác nhạy cảm hơn cần kiểm soát mạnh:
- Thêm hoặc xóa passkey/MFA.
- Thay đổi email/phone recovery.
- Đổi password.
- Tạo hoặc thu hồi API key.
- Thay đổi payment destination.
- Thay đổi role, quyền hoặc tenant membership.

Với các hành động này, CSRF token là một lớp; có thể cần reauthentication, step-up, notification và transaction binding.

## 14. OAuth 2.0 và OpenID Connect: state, nonce và PKCE

OAuth/OIDC có các cơ chế riêng để ràng buộc authorization response với request ban đầu. Không gộp chúng thành một token chung vì mỗi cơ chế bảo vệ một phần khác nhau.

| Cơ chế | Vai trò chính | Ràng buộc |
| --- | --- | --- |
| **state** | Correlate authorization response với request khởi tạo và chống CSRF trong redirect flow | Giá trị ngẫu nhiên, gắn với browser/client transaction |
| **nonce** | Ràng buộc ID token với authentication request và giảm replay/injection | Nonce gửi trong request, kiểm tra trong ID token |
| **PKCE** | Ràng buộc authorization code với client instance đã tạo code verifier | Code challenge ở request, verifier ở token exchange |
| **redirect_uri** | Giới hạn nơi authorization response được gửi | Exact registered URI theo profile |

### 14.1. State

Client tạo state ngẫu nhiên khó đoán, lưu gắn với browser/session transaction rồi gửi trong authorization request. Khi callback trở về, client so sánh state nhận được với giá trị đã lưu. Nếu thiếu hoặc không khớp, từ chối response.

Không dùng một state cố định cho mọi login. Không chấp nhận state do callback tự chọn mà không có bản đối chiếu từ transaction ban đầu. Tránh đặt thông tin cá nhân hoặc secret vào state; có thể dùng opaque random value tham chiếu state server-side.

### 14.2. Nonce

Trong OIDC, nonce được gửi trong Authentication Request và phải được so khớp với claim nonce trong ID Token khi flow yêu cầu. Nó giúp ràng buộc ID Token với request cụ thể và chống một số dạng replay/token injection.

Nonce không thay state trong mọi flow và không thay PKCE. Client phải kiểm tra chữ ký, issuer, audience, expiry và các claim OIDC khác theo profile.

### 14.3. PKCE

PKCE tạo code verifier bí mật ngẫu nhiên và gửi code challenge trong authorization request. Khi đổi authorization code lấy token, client gửi verifier. Authorization server kiểm tra verifier tương ứng.

PKCE giúp chống authorization code interception và trong các cấu hình hiện đại có thể góp phần chống CSRF nếu được triển khai đúng theo profile. Tuy nhiên, client vẫn cần quản lý transaction/correlation state và tuân thủ hướng dẫn bảo mật OAuth/OIDC hiện hành. Không tự bỏ state hoặc nonce chỉ vì đã bật PKCE mà chưa đánh giá flow và thư viện.

### 14.4. Cookie SameSite trong callback

OIDC callback có thể là top-level GET hoặc cross-site POST tùy response mode. SameSite=Lax thường phù hợp với top-level safe navigation nhưng có thể không gửi cookie trong cross-site POST như form_post.

Client cần thiết kế correlation transaction sao cho callback vẫn được kiểm tra an toàn. Có thể dùng cookie tạm phù hợp với flow, state server-side và token binding; mọi ngoại lệ SameSite phải có phạm vi hẹp, Secure và thời hạn ngắn. Không tắt CSRF validation ở callback.

## 15. API dùng bearer token trong Authorization header

CSRF thường ít áp dụng hơn với API mà JavaScript chủ động gắn bearer token vào header Authorization, vì browser không tự động gắn token đó vào request cross-site giống cookie session.

Tuy nhiên, điều này phụ thuộc cách lưu và gửi token:
- Nếu access token được lưu trong cookie, request vẫn có thể bị CSRF.
- Nếu token nằm trong localStorage/sessionStorage, XSS có thể đọc và đánh cắp token.
- Nếu token nằm trong memory, XSS vẫn có thể thao tác ứng dụng hoặc gọi API trong context hiện tại.
- Nếu API chấp nhận cookie fallback, CSRF vẫn có thể tồn tại.
- Nếu browser tự động gửi HTTP authentication hoặc client certificate, cần đánh giá ambient credential behavior.

Không kết luận "dùng JWT là không cần CSRF". JWT là định dạng; câu hỏi quan trọng là credential có được browser tự động gửi hay không và server có chấp nhận nó ở đâu.

### 15.1. SPA và cookie session

SPA dùng cookie session vẫn cần CSRF protection. Một pattern thường dùng:
1. Server cấp session cookie HttpOnly, Secure và SameSite phù hợp.
2. Server cung cấp CSRF token qua endpoint cùng origin.
3. SPA lưu token trong memory và gửi custom header cho request thay đổi trạng thái.
4. Server kiểm tra token, session và Origin/Fetch Metadata.
5. CORS chỉ cho phép origin thực sự cần thiết.

Không cho phép arbitrary origin đọc CSRF token endpoint. Không đặt session cookie Domain rộng hơn cần thiết.

### 15.2. Backend-for-Frontend

Backend-for-Frontend (BFF) có thể giữ access/refresh token ở server và dùng session cookie HttpOnly cho browser. Cách này giảm việc token OAuth xuất hiện trong JavaScript, nhưng browser vẫn gửi cookie session tự động nên BFF endpoint thay đổi trạng thái vẫn cần CSRF defense.

## 16. WebSocket và các giao thức browser khác

WebSocket handshake bắt đầu bằng HTTP request và browser có thể gửi cookie session. Một trang độc hại có thể cố mở WebSocket tới server khác trong khi browser mang cookie của nạn nhân.

Server nên kiểm tra:
- Origin chính xác theo allowlist.
- Authentication/session hợp lệ.
- Authorization cho channel/topic/resource.
- CSRF-like origin restrictions trước khi upgrade.
- Rate limit và giới hạn số connection.
- Không tin query parameter làm credential nếu có thể lộ trong log.

Origin check quan trọng vì browser JavaScript không thể tùy ý đặt Origin thành giá trị khác. Tuy nhiên, non-browser client có thể tự khai header; vì vậy vẫn cần authentication thực sự.

Các giao thức khác như WebRTC signaling, event stream hoặc browser-based RPC cũng cần đánh giá liệu credential có được gửi tự động và request có thể được khởi tạo cross-site hay không.

## 17. XSS có thể vượt qua CSRF defense

CSRF token bảo vệ request được tạo từ origin khác. Nếu attacker chạy JavaScript trong origin của ứng dụng thông qua XSS, script có thể:
- Đọc CSRF token trong DOM hoặc response mà ứng dụng hợp lệ đọc được.
- Gửi request với custom header.
- Dùng session cookie mà không cần đọc HttpOnly cookie.
- Thay đổi dữ liệu giao diện hoặc đánh lừa người dùng xác nhận.
- Thực hiện hành động trong quyền của session hiện tại.

Vì vậy:
- Output encode theo context.
- Sanitize HTML không tin cậy.
- Dùng CSP phù hợp.
- Hạn chế third-party script.
- Tránh unsafe-inline và eval nếu có thể.
- Dùng Trusted Types khi phù hợp.
- Bảo vệ dependency và template.
- Không đưa CSRF token vào nơi script bên thứ ba có thể đọc.

HttpOnly giảm khả năng đánh cắp cookie qua JavaScript nhưng không ngăn script XSS gửi request dưới session. CSRF defense và XSS defense phải được triển khai cùng nhau.

## 18. Framework và middleware

Framework web thường có CSRF middleware, nhưng cần bật và cấu hình đúng. Không giả định mọi route tự được bảo vệ.

Khi tích hợp:
- Xác định route nào dùng cookie/session authentication.
- Bật CSRF middleware cho mọi unsafe method phù hợp.
- Kiểm tra form, AJAX, multipart upload và API route.
- Cấu hình cookie SameSite/Secure/HttpOnly.
- Xác định endpoint exemption hẹp cho webhook hoặc callback được xác minh bằng cơ chế riêng.
- Không miễn CSRF toàn bộ /api/* chỉ vì route có tên API.
- Test middleware với reverse proxy và subdomain.
- Kiểm tra CSRF token rotation sau login/logout/session renewal.

Webhook server-to-server có thể không dùng cookie browser và thường xác thực bằng signature, nhưng phải có verifier riêng; exemption không có nghĩa endpoint được public không kiểm tra.

### 18.1. Đừng tự tạo exemption rộng

Một số endpoint có thể cần cross-site POST hợp lệ, như callback từ payment provider hoặc identity provider. Hãy:
- Xác minh signature/state/assertion theo giao thức.
- Giới hạn route và method.
- Kiểm tra issuer/audience/transaction.
- Dùng replay protection.
- Ghi audit.
- Không mở exemption cho các endpoint khác.

## 19. Logging, monitoring và response

CSRF event có thể chỉ ra form hoặc origin đáng ngờ, token mismatch, cookie policy không tương thích hoặc một XSS đang khai thác ứng dụng.

Nên ghi:
- Endpoint và method.
- Origin/Sec-Fetch-Site đã giảm nhạy cảm.
- CSRF validation result/reason code.
- Session reference đã pseudonymize.
- Tenant/client và correlation ID.
- Thời điểm và kết quả.
- Tỷ lệ token mismatch theo browser/version.

Không log CSRF token, session cookie, Authorization header hoặc body nhạy cảm. Referer có thể chứa query string và dữ liệu nhạy cảm; chỉ lưu origin hoặc thông tin tối thiểu cần thiết.

Khi phát hiện CSRF:
1. Xác định endpoint và side effect đã xảy ra.
2. Kiểm tra session và account bị ảnh hưởng.
3. Thu hồi session hoặc credential nếu có dấu hiệu compromise.
4. Đảo giao dịch theo business recovery policy khi có thể.
5. Sửa token/origin/SameSite policy.
6. Kiểm tra XSS, subdomain takeover và cookie injection.
7. Thông báo người dùng/owner theo incident policy.
8. Thêm regression tests.

## 20. Threat model và lỗi thường gặp

| Mối đe dọa/lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| **Chỉ kiểm tra session cookie** | Request CSRF được coi là hợp lệ | CSRF token và origin/context checks |
| **State-changing GET** | Link hoặc image có thể kích hoạt side effect | Dùng unsafe method và CSRF validation |
| **CSRF token không gắn session** | Token bị tái sử dụng giữa account/session | Synchronizer token hoặc signed binding |
| **Double-submit không chữ ký** | Cookie injection qua subdomain có thể vượt kiểm tra | Signed double-submit và cookie host-only |
| **SameSite=None không Secure** | Cookie cross-site có thể bị browser từ chối hoặc cấu hình yếu | SameSite=None; Secure chỉ khi cần |
| **Tin SameSite là đủ** | Subdomain same-site hoặc flow đặc biệt vẫn có rủi ro | Token, Origin và Fetch Metadata |
| **CORS wildcard/reflect origin** | Origin không tin cậy có thể đọc response hoặc dùng credential | Exact allowlist và credential policy |
| **Origin substring check** | Origin giả chứa domain hợp lệ được chấp nhận | Parse và so khớp scheme/host/port chính xác |
| **Không kiểm tra login CSRF** | Browser nạn nhân bị đăng nhập vào account attacker | Login CSRF token và transaction correlation |
| **Logout qua GET** | Attacker ép người dùng logout | POST với CSRF protection |
| **OIDC state không kiểm tra** | Callback có thể bị gắn sai transaction | State ngẫu nhiên, server-side correlation |
| **Nhầm state, nonce và PKCE** | Thiếu một lớp bảo vệ của flow | Triển khai đúng semantics từng cơ chế |
| **XSS** | Script cùng origin đọc token và gửi request | XSS prevention, CSP và dependency security |
| **Cookie Domain quá rộng** | Subdomain không tin cậy có thể ảnh hưởng cookie | Host-only/__Host- cookie khi phù hợp |
| **CSRF middleware exemption rộng** | Route nhạy cảm bị bỏ bảo vệ | Exemption theo endpoint và verifier riêng |
| **BFF dùng cookie nhưng không CSRF** | Browser gửi session tự động | CSRF token và origin checks |
| **WebSocket thiếu Origin check** | Browser có thể mở connection ngoài ý muốn | Origin allowlist và session authorization |
| **Log token/session** | Credential hoặc session bị lộ | Redaction và access control |

## 21. Ví dụ: thay đổi email recovery

Một người dùng đã đăng nhập muốn đổi email recovery. Đây là thao tác nhạy cảm vì email mới có thể trở thành kênh lấy lại tài khoản.

Flow an toàn có thể:

1. Browser gửi request tải form cùng session cookie.
2. Server cung cấp CSRF token gắn với session.
3. Người dùng nhập email mới.
4. Browser gửi POST cùng cookie, CSRF token và Origin.
5. Server kiểm tra session, CSRF token, Origin và account state.
6. Server yêu cầu reauthentication/step-up theo risk policy.
7. Server tạo pending change và gửi verification tới email mới.
8. Server thông báo tới kênh cũ đã xác minh.
9. Chỉ sau khi email mới được xác minh và policy hoàn tất, hệ thống mới chuyển trạng thái recovery contact.
10. Audit ghi actor, thời điểm và kết quả, không ghi token hoặc secret.

~~~mermaid
flowchart TD
    A[User mở trang security settings] --> B[Server cấp CSRF token gắn session]
    B --> C[User nhập email mới]
    C --> D[POST + cookie + token + Origin]
    D --> E{Session, token và origin hợp lệ?}
    E -- Không --> X[Reject]
    E -- Có --> F[Reauthentication / step-up]
    F --> G{Assurance đạt?}
    G -- Không --> X
    G -- Có --> H[Tạo pending email change]
    H --> I[Xác minh email mới và thông báo kênh cũ]
    I --> J[Hoàn tất theo policy và audit]
~~~

Nếu attacker chỉ có thể khiến browser gửi POST nhưng không biết CSRF token, request sẽ bị từ chối. Nếu attacker có XSS trong origin, token có thể bị đọc hoặc sử dụng; vì vậy ví dụ này vẫn cần XSS prevention.

## 22. Kiểm thử CSRF và authentication

| Test case | Kết quả mong đợi |
| --- | --- |
| POST thay đổi trạng thái không có CSRF token | Từ chối |
| Token sai hoặc thuộc session khác | Từ chối |
| Token hợp lệ cùng session | Tiếp tục authentication/authorization |
| GET endpoint thay đổi dữ liệu | Không tồn tại hoặc không tạo side effect |
| Cross-site form POST với cookie | Bị token/origin/SameSite policy chặn |
| Cross-site simple request | Không tạo side effect dù response không đọc được |
| Origin giả dạng bằng suffix | Từ chối |
| Origin thiếu trên endpoint nhạy cảm | Xử lý theo policy nghiêm ngặt |
| Referer fallback khác origin | Từ chối |
| Sec-Fetch-Site cross-site | Block hoặc đi qua ngoại lệ hẹp đã review |
| SameSite=Lax với top-level GET | Kiểm tra flow hoạt động và không tạo side effect |
| SameSite=Strict với link ngoài | Kiểm tra UX/callback theo thiết kế |
| SameSite=None | Chỉ hoạt động cùng Secure và CSRF defense bổ sung |
| Subdomain không tin cậy | Không thể ghi đè session cookie hoặc giả CSRF token |
| Login CSRF | Không thể ép browser đăng nhập vào account attacker |
| Logout CSRF | Request cross-site không thể logout trái phép |
| OIDC state không khớp | Callback bị từ chối |
| OIDC nonce không khớp | ID token bị từ chối |
| PKCE verifier sai | Token exchange thất bại |
| BFF cookie session | Unsafe request vẫn yêu cầu CSRF token |
| Bearer token chỉ trong Authorization header | Kiểm tra không có cookie fallback/ambient credential |
| XSS simulation | Xác nhận XSS có thể vượt CSRF và cần lớp phòng vệ riêng |
| WebSocket từ origin lạ | Handshake bị từ chối |
| Webhook cross-site | Chỉ chấp nhận sau signature/event verification |
| CSRF token trong URL/log | Không xuất hiện |
| Audit inspection | Có reason code nhưng không có cookie/token thô |

### 22.1. Kiểm thử trên browser thực

CSRF phụ thuộc browser cookie behavior. Kiểm thử trên các browser và phiên bản được hỗ trợ:
- SameSite defaults.
- Top-level navigation và cross-site POST.
- Iframe và third-party cookie restrictions.
- Redirect từ IdP/payment provider.
- Subdomain cùng site nhưng khác origin.
- Cookie prefix và Domain/Path.
- Browser privacy mode.
- SPA fetch credentials và CORS preflight.

Không chỉ test bằng curl vì curl không mô phỏng chính xác việc browser tự động gửi cookie và thực thi Same-Origin Policy.

## 23. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| API có dùng ambient credential? | Cookie/HTTP auth được xác định rõ |
| Unsafe methods có CSRF protection? | POST/PUT/PATCH/DELETE được kiểm tra |
| GET có thật sự safe? | Không thay đổi trạng thái nghiệp vụ |
| Token có gắn session? | Random, server-verified và không thể đoán |
| Double-submit có chống injection? | Signed/session-bound nếu dùng |
| Cookie có cấu hình phù hợp? | Secure, HttpOnly, SameSite và host-only |
| Origin/Referer được so khớp chính xác? | Scheme, host, port và fallback rõ |
| Fetch Metadata có được dùng hợp lý? | Cross-site unsafe request bị kiểm soát |
| CORS có allowlist hẹp? | Không wildcard/reflect origin tùy tiện |
| Login/logout được bảo vệ? | Có CSRF defense và flow correlation |
| OAuth/OIDC có đủ state/nonce/PKCE? | Semantics từng cơ chế được kiểm tra |
| BFF có CSRF defense? | Cookie session không bị bỏ bảo vệ |
| Bearer token có thực sự non-ambient? | Không nằm trong cookie hoặc fallback |
| XSS defense có đủ? | CSP, output encoding và dependency review |
| WebSocket kiểm tra Origin? | Origin allowlist và authorization |
| Exemption có hẹp? | Webhook/IdP callback có verifier riêng |
| Audit không lộ secret? | Không log token, cookie hoặc CSRF value |
| Có test browser thực? | Form, iframe, redirect, subdomain và SameSite |

### Tình huống tự kiểm tra

**Tình huống 1:** Người dùng đăng nhập hợp lệ và browser gửi session cookie trong request. Có đủ bằng chứng để kết luận người dùng chủ động thực hiện request không?

**Trả lời:** Không. Cookie chứng minh browser có session; CSRF token và kiểm tra origin/context giúp xác minh request được khởi tạo từ luồng hợp lệ.

**Tình huống 2:** Attacker không đọc được response do Same-Origin Policy. Họ có thể vẫn gây CSRF không?

**Trả lời:** Có. Form hoặc request đơn giản vẫn có thể được gửi và kích hoạt side effect dù attacker không đọc response.

**Tình huống 3:** Cookie session có HttpOnly. CSRF đã được ngăn chưa?

**Trả lời:** Chưa. HttpOnly ngăn JavaScript đọc cookie; browser vẫn tự gửi cookie theo cookie policy.

**Tình huống 4:** Ứng dụng dùng SameSite=Lax. Có thể bỏ CSRF token ở mọi endpoint không?

**Trả lời:** Không. SameSite là lớp bổ sung; top-level navigation, subdomain cùng site và flow đặc biệt vẫn cần được đánh giá. Endpoint nhạy cảm nên có token/origin defense.

**Tình huống 5:** API chỉ cho phép CORS từ frontend chính thức. Có thể bỏ CSRF token cho cookie session không?

**Trả lời:** Không. CORS chủ yếu kiểm soát đọc response; form request đơn giản có thể vẫn được gửi. Cookie-authenticated unsafe endpoint cần CSRF defense.

**Tình huống 6:** SPA dùng bearer token trong Authorization header và không gửi cookie. Rủi ro CSRF có giống cookie session không?

**Trả lời:** Thường thấp hơn vì browser không tự đính kèm header bearer token vào request cross-site. Tuy nhiên, nếu token nằm trong cookie hoặc API có cookie fallback thì CSRF vẫn áp dụng; XSS vẫn là rủi ro lớn.

**Tình huống 7:** OIDC flow đã dùng PKCE. Có thể bỏ qua kiểm tra state và nonce mà không xem xét profile không?

**Trả lời:** Không. PKCE, state và nonce có semantics khác nhau. Phải triển khai theo flow, thư viện và hướng dẫn OAuth/OIDC hiện hành; không bỏ kiểm tra correlation hoặc ID token binding tùy tiện.

**Tình huống 8:** Một subdomain cùng site bị attacker kiểm soát. SameSite có bảo vệ hoàn toàn session cookie không?

**Trả lời:** Không. Same-site khác same-origin. Cần host-only cookie, token, Origin validation và kiểm soát subdomain.

## 24. Ghi nhớ

**CSRF lợi dụng việc browser tự động gửi credential để khiến server thực hiện request ngoài ý muốn dưới một session hợp lệ.** Session cookie xác minh trạng thái đăng nhập nhưng không chứng minh ý định của người dùng cho từng thao tác. Bảo vệ cần CSRF token gắn với session hoặc signed double-submit, SameSite phù hợp, Origin/Referer validation và Fetch Metadata cho unsafe requests.

CORS và Same-Origin Policy không tự ngăn mọi request cross-site; HttpOnly cũng không ngăn browser gửi cookie. Login, logout, account recovery và thay đổi credential đều cần được bảo vệ. Với OAuth/OIDC, state, nonce và PKCE có vai trò riêng và phải được kiểm tra theo protocol. Bearer token được client chủ động gắn trong Authorization header thường giảm CSRF nếu không có ambient cookie, nhưng vẫn cần bảo vệ khỏi XSS và token theft. Kết hợp CSRF defense với XSS prevention, authentication assurance, authorization và kiểm thử trên browser thực để giữ trust boundary an toàn.
