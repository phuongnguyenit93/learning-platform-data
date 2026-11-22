# Cơ chế tấn công CSRF và điều kiện trình duyệt tự gửi thông tin xác thực

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích **Cross-Site Request Forgery (CSRF)** là gì, tại sao nó nhắm tới *thẩm quyền của trình duyệt đang đăng nhập* thay vì đánh cắp mật khẩu, và phân biệt CSRF với XSS, CORS, clickjacking.
2. Mô tả đầy đủ các điều kiện cần cho một cuộc tấn công: có thao tác thay đổi trạng thái, trình duyệt nạn nhân có credential được gửi theo request, attacker tạo được một request có hiệu lực, server thiếu một cơ chế xác nhận ý định người dùng.
3. Phân biệt `origin`, `site`, cookie `SameSite=Strict/Lax/None`, domain/path, top-level navigation, form POST và `fetch(..., { credentials: "include" })`; không nhầm **CORS không cho đọc response** với **CORS không cho gửi request**.
4. Chỉ ra vì sao session cookie, HTTP Basic lưu trong trình duyệt, client certificate và token đặt trong cookie có thể dẫn tới CSRF; vì sao Bearer token được JS chủ động gắn trong header thường có threat model khác.
5. Hiểu cơ chế CSRF token đồng bộ (*synchronizer token pattern*) của Spring Security WebFlux: `CsrfWebFilter`, `WebSessionServerCsrfTokenRepository`, `CsrfToken`, `XorServerCsrfTokenRequestAttributeHandler` và bảo vệ HTTP method không an toàn.
6. Xây dựng ví dụ Java 17+ / Spring Boot 3.x với form login, HTML form có CSRF token thật, controller xử lý form reactive và `WebTestClient` kiểm chứng request bị chặn/được phép.
7. Thiết kế phòng thủ nhiều lớp: CSRF token, không thay đổi trạng thái qua GET, SameSite cookie, Origin/Referer/Fetch Metadata, bảo vệ login/logout, chống XSS và không tùy tiện tắt CSRF.

> Phạm vi: Spring Security **WebFlux reactive**. Ví dụ sử dụng `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebSession`, Reactor và `WebTestClient`. Các ví dụ dùng `HttpSecurity`, `HttpSessionCsrfTokenRepository` hoặc Servlet `Filter` thuộc stack Spring MVC/Servlet, không được copy máy móc sang WebFlux.

---

## 1. CSRF là gì?

**CSRF** là cách một trang hay ngữ cảnh mà kẻ tấn công điều khiển khiến **trình duyệt của nạn nhân** gửi request tới ứng dụng khác, lợi dụng credential mà trình duyệt gắn vào request theo cơ chế sẵn có. Nếu server chỉ nhìn cookie/HTTP authentication rồi tin request xuất phát từ ý định của chính người dùng, nó có thể thực hiện thay đổi không mong muốn.

Ví dụ tình huống hợp lệ về mặt mô hình:

- Người dùng đã đăng nhập `https://app.example.test` bằng session cookie.
- Ứng dụng có endpoint `POST /settings/notifications` để đổi thiết lập của tài khoản.
- Người dùng mở một trang ngoài sự kiểm soát của ứng dụng, như `https://attacker.invalid`.
- Trang đó có thể tạo form POST hướng tới `https://app.example.test/settings/notifications`.
- **Nếu** trình duyệt gửi cookie/session hợp lệ cho request đó và server không đòi CSRF token/Origin phù hợp, thao tác có thể chạy dưới danh tính nạn nhân.

Điều kiện **"nếu"** rất quan trọng: ở trình duyệt hiện đại, cookie `SameSite=Lax` hoặc `Strict` thường khiến cross-site POST từ một site khác không mang cookie. Tuy nhiên, cookie `SameSite=None; Secure`, các tình huống cùng **site** nhưng khác **origin**, ngoại lệ triển khai, cookie policy hoặc cơ chế ambient authentication khác có thể thay đổi kết quả. Một mẫu HTML có form **không tự chứng minh** mọi môi trường đều bị tấn công.

### CSRF không nhất thiết đọc được response

Một trang độc hại có thể không xem được tài liệu hoặc body trả về từ ứng dụng đích do **same-origin policy/CORS**. Nhưng để thay đổi trạng thái, attacker thường chỉ cần *gửi* được request; không cần đọc thành công body response.

Ví dụ: nếu một request làm thay đổi lựa chọn thông báo hoặc tạo yêu cầu chuyển khoản, hậu quả nằm ở phía server dù trình duyệt không cho JavaScript của trang khác đọc kết quả.

### Mô hình tấn công khái niệm

```text
Nạn nhân đăng nhập tại app.example.test
   |
   +--> Trình duyệt giữ cookie/session của app
   |
   +--> Nạn nhân mở trang attacker.invalid
                |
                +--> Trang tạo một request tới app.example.test
                |
                +--> Trình duyệt quyết định có gửi cookie/Basic/cert
                       theo URL, SameSite, credentials mode, policy ...
                |
                +--> Server nhận request:
                      - Có credential hợp lệ?
                      - Có CSRF token/Origin được kiểm tra?
                      - HTTP method và dữ liệu có được chấp nhận?
                |
                +--> Nếu tin credential nhưng thiếu kiểm tra ý định:
                       thao tác có thể chạy như nạn nhân
```

Đây là sơ đồ phòng thủ, không phải hướng dẫn tấn công hệ thống thật. Các URL dưới miền `.test` hoặc `.invalid` trong bài chỉ phục vụ ví dụ khái niệm.

## 2. Bốn điều kiện quan trọng để CSRF có tác dụng

Không phải "ứng dụng có cookie" là tự động có lỗ hổng CSRF. Hãy đánh giá đồng thời:

| Điều kiện | Câu hỏi kiểm tra | Nếu không thỏa |
| --- | --- | --- |
| **1. Endpoint có tác động** | Có POST/PUT/PATCH/DELETE làm thay đổi dữ liệu, hoặc GET bị dùng sai để tạo side effect? | Không có thao tác đáng lợi dụng trên request đó |
| **2. Credential được trình duyệt tự gửi** | Cookie phiên, Basic cache, client certificate hay credential tương tự có được đính kèm khi request hướng đến target? | Request có thể là anonymous, không thực hiện được thao tác yêu cầu đăng nhập |
| **3. Attacker tạo được request hợp lệ về mặt cú pháp** | Có thể tạo form/navigation/fetch thỏa method, Content-Type và validation dữ liệu của endpoint? | Server loại request trước bước nghiệp vụ |
| **4. Thiếu rào chắn ràng buộc ý định** | Không có CSRF token hợp lệ, kiểm tra Origin/Fetch Metadata phù hợp hoặc rào chắn chống CSRF đáng tin khác? | Server từ chối dù credential hợp lệ |

Trong thực tế có thể còn có quyền account, trạng thái session, phân quyền theo tài nguyên, giới hạn tần suất và xác thực lại giao dịch. **CSRF bypass ý định của user, không tự nâng role.** Một nạn nhân không có quyền ADMIN không thể bị biến thành ADMIN chỉ qua một form CSRF nếu server kiểm tra quyền chính xác.

### Điều kiện không phải một phần của CSRF

- Attacker **không cần biết password** nếu browser tự mang credential.
- Attacker **không cần đánh cắp session cookie** để tạo CSRF. Đánh cắp cookie là một dạng session hijacking khác.
- Attacker **không cần đọc response**; hành động ghi dữ liệu có thể đã xảy ra.
- Attacker không được giả định có thể đặt tùy ý header `Authorization` hoặc `X-CSRF-TOKEN` trên cross-site HTML form. Đó là lợi ích của token/header không tự gắn.
- CSRF không thay thế XSS: một lỗi XSS ở chính ứng dụng có thể chạy script same-origin, đọc token mà script được phép tiếp cận và vượt qua một số biện pháp CSRF.

## 3. Trình duyệt "tự gửi" credential nào?

Có nhiều loại credential, không phải loại nào cũng giống cookie.

### 3.1. Session cookie và WebSession

Khi ứng dụng có session-based authentication, sau login browser thường giữ cookie chứa **session ID**, không phải raw password. Khi gửi request phù hợp tới server, browser có thể tự đính cookie dựa trên Domain, Path, Secure, SameSite và chính sách cookie.

Spring WebFlux thường dùng cookie `SESSION` cho `WebSession` mặc định, nhưng tên này có thể cấu hình và có thể khác khi dùng Spring Session. Đừng mặc định tên là `JSESSIONID` như ở Servlet.

Quan trọng: browser đính cookie căn cứ vào **đích request và cookie rules**, không căn cứ vào việc trang nguồn có tin cậy hay không. Cookie còn hợp lệ không chứng minh user chủ động bấm một nút trong ứng dụng đích.

### 3.2. HTTP Basic được trình duyệt lưu

Với HTTP Basic, browser có thể cache credential cho một vùng bảo vệ và tự gửi lại thông tin Authorization trong các request phù hợp. Vì thế **HTTP Basic chạy trong trình duyệt không mặc nhiên miễn nhiễm CSRF**. Nguy cơ phụ thuộc browser, cơ chế auth, phạm vi credential và request.

Một API chỉ được gọi bởi non-browser client chủ động thiết lập `Authorization` mỗi lần thường có mô hình khác. Nhưng đừng suy từ "dùng Basic" sang "không thể CSRF" nếu có trình duyệt và Basic credentials cached.

### 3.3. TLS client certificate và cơ chế ambient khác

Nếu browser đã chọn client certificate cho kết nối mTLS và có thể tự dùng lại cert khi kết nối đến target, credential cũng có thể đi cùng request mà trang attacker không biết private key. Tương tự, một số cơ chế tự gắn credential ở network/browser layer cần được đánh giá trong threat model.

### 3.4. JWT/refresh token đặt trong cookie

JWT không tự động chống CSRF chỉ vì là token "stateless". Nếu server tin JWT được gửi **trong cookie**, và browser tự đính cookie trong request cross-site theo policy, request vẫn có thể mang authentication hợp lệ.

Ngược lại, nếu frontend chỉ giữ Bearer token trong bộ nhớ và chủ động đặt:

```javascript
fetch("/api/profile", {
  headers: { Authorization: "Bearer " + accessToken }
});
```

thì trang cross-site thông thường không biết `accessToken` để tự tạo header giống vậy. Đây là tình huống nguy cơ classic CSRF **thường thấp hơn**, nhưng vẫn phải bảo vệ chống XSS, token leakage, CORS sai, refresh token cookie và các cơ chế credential khác. Đừng kết luận "SPA/JWT luôn an toàn với CSRF".

### Bảng so sánh

| Kiểu xác thực | Browser có thể tự gửi? | Hàm ý với CSRF |
| --- | --- | --- |
| Session cookie | Có, nếu cookie rules cho phép | Cần CSRF protection cho unsafe actions |
| JWT trong HttpOnly cookie | Có, nếu cookie rules cho phép | Vẫn phải đánh giá CSRF |
| HTTP Basic cached trong browser | Có thể | Không coi Basic là mặc định an toàn |
| mTLS client certificate của browser | Có thể | CSRF vẫn là một rủi ro cần phân tích |
| Bearer header do JS đáng tin gắn từ memory | Không tự động từ trang attacker | Classic CSRF ít thuận lợi hơn; XSS/token theft là rủi ro khác |
| API key chỉ server-to-server biết | Không thuộc credential browser | Thường không chịu dạng browser CSRF truyền thống |

## 4. Same-origin và same-site là hai khái niệm khác nhau

Để biết cookie có được gửi hay không, phải phân biệt **origin** với **site**.

**Origin** gồm *scheme + host + port*. Ví dụ:

- `https://app.example.test` và `https://api.example.test`: khác origin.
- `https://app.example.test:443` và `https://app.example.test:8443`: khác origin.
- `https://app.example.test` và `http://app.example.test`: khác origin.

**Site** trong cookie `SameSite` thường xét scheme và registrable domain (*schemeful same-site*). Ví dụ:

- `https://app.example.test` và `https://evil.example.test`: có thể **cùng site** nhưng **khác origin**.
- `https://app.example.test` và `https://attacker.invalid`: **khác site**.
- `http://app.example.test` và `https://app.example.test`: khác site theo schemeful same-site.

Các ví dụ miền có thể phụ thuộc public suffix list; ở production cần xem domain thật và policy của trình duyệt, không đánh giá theo việc hostname có vẻ "giống nhau".

**Hệ quả:** `SameSite=Strict` hoặc `Lax` bảo vệ nhiều tình huống khác *site*, nhưng **không phải cơ chế chặn mọi request khác *origin***. Một sibling subdomain dưới cùng site bị chiếm quyền có thể phát sinh request same-site tới ứng dụng chính. Vì vậy SameSite không thể thay thế hoàn toàn CSRF token/Origin verification.

### Cookie domain/path

Cookie host-only được gửi tới host đã phát cookie, không tới mọi subdomain. Cookie có `Domain=example.test` có phạm vi rộng hơn. Nhưng khi một trang từ `evil.example.test` gửi request **tới `app.example.test`**, browser chọn cookie dựa trên **request destination app.example.test**, không phải tự gửi cookie cho trang evil. Do đó host-only cookie của app vẫn có thể đi đến app trong request do sibling subdomain khởi xướng, nếu SameSite và các điều kiện khác cho phép.

Thuộc tính `Path` quyết định request path phù hợp; nó không phải ranh giới bảo mật giữa ứng dụng có thể tự chọn request path. Dùng host-only cookie, prefix `__Host-` khi phù hợp, Secure/HttpOnly/SameSite và domain tối thiểu để giảm phạm vi rủi ro.

## 5. Cookie SameSite=Strict, Lax, None và các giới hạn

| SameSite | Cross-site form POST thường gửi cookie? | Cross-site top-level GET navigation thường gửi cookie? | Nhận xét |
| --- | --- | --- | --- |
| `Strict` | Không | Không | Chặt hơn nhưng có thể ảnh hưởng đăng nhập từ link ngoài |
| `Lax` | Thông thường **không** | **Có** với safe top-level navigation | Không bảo vệ endpoint thay đổi trạng thái qua GET |
| `None; Secure` | Có thể, tùy third-party cookie policy/browser | Có thể | Phù hợp một số luồng cross-site nhưng cần phòng thủ CSRF đầy đủ |
| Không khai báo SameSite | Phụ thuộc browser; nhiều browser áp dụng default Lax | Phụ thuộc browser | Không coi hành vi mặc định là contract ổn định |

**Ngoại lệ cần biết:** một số browser áp dụng biến thể "Lax-allowing-unsafe" cho cookie mới tạo gần đây khi thiếu thuộc tính SameSite tường minh. Đừng dựa trên giả định mọi POST cross-site luôn bị chặn chỉ vì cookie thiếu cấu hình.

**SameSite chỉ là lớp bổ sung**, không nên dùng làm kiểm soát duy nhất. Thao tác thay đổi trạng thái qua GET có thể bị lợi dụng dù cookie Lax vì browser gửi cookie với top-level navigation GET. Nếu cùng site nhưng khác origin, SameSite còn cho phép cookie theo ngữ nghĩa site.

### Ví dụ GET thay đổi dữ liệu là nguy hiểm

Giả sử ứng dụng sai thiết kế:

```http
GET /account/delete?confirm=true HTTP/1.1
Host: app.example.test
Cookie: SESSION=...
```

Một link điều hướng top-level từ site khác có thể mang cookie Lax và kích hoạt thay đổi. Đây là **anti-pattern**, không phải endpoint nên xây dựng. Đưa hành động thay đổi dữ liệu sang POST/DELETE, kiểm tra CSRF tương ứng, xác thực quyền và có bước xác nhận/reauthentication nếu rủi ro cao.

**Nguyên tắc HTTP:** GET, HEAD, OPTIONS, TRACE được xem là safe theo mô hình CSRF mặc định, nên ứng dụng không được âm thầm biến chúng thành lệnh ghi, xóa hoặc chuyển tiền. "Safe" là nghĩa vụ của app, không chỉ là nhãn method.

## 6. HTML form, navigation và fetch có hành vi khác nhau

### 6.1. HTML form cross-origin

Trình duyệt cho phép trang A tạo một HTML form với `action` hướng tới trang B và gửi bằng POST. Form có thể dùng content type thông dụng như `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`; các biểu mẫu truyền thống **không cần có quyền JavaScript đọc response của B**.

Một minh họa về request bị giả mạo, dùng miền giả định, **không nhắm hệ thống thật**:

```html
<!-- Chỉ là ví dụ phòng thủ về việc form có thể gửi sang origin khác -->
<form method="post"
      action="https://app.example.test/settings/notifications">
  <input type="hidden" name="enabled" value="false">
  <button type="submit">Tiếp tục</button>
</form>
```

Điều này chỉ có thể dẫn đến thay đổi nếu credential được gửi theo browser policy, endpoint chấp nhận form và server thiếu kiểm tra CSRF/Origin phù hợp. Kẻ tấn công không mặc nhiên đọc được response hoặc tự đặt CSRF token hợp lệ.

### 6.2. fetch() và credential mode

Với Fetch API, chế độ credential mặc định là `same-origin`; cross-origin `fetch` thông thường **không gửi cookie/HTTP credentials** nếu không chỉ định.

```javascript
// JavaScript thuộc một origin bất kỳ (minh họa browser API):
fetch("https://api.example.test/settings", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ enabled: false })
});
```

- `credentials: "include"` yêu cầu browser gửi credential được phép, nhưng **không vượt qua** SameSite, third-party cookie blocking hoặc cookie Domain/Path/Secure.
- `Content-Type: application/json` thường khiến cross-origin fetch thực hiện **CORS preflight** trước request thật. Nếu preflight không được chấp thuận, browser có thể không gửi actual request.
- Form-encoded hoặc các *simple requests* có thể được gửi mà không có preflight; đừng suy ra từ JSON/fetch rằng mọi CSRF bị chặn.
- CORS quyết định quyền JS truy cập phản hồi và một phần điều kiện gửi preflighted request; không phải biện pháp thay thế CSRF chung.

### 6.3. Tại sao "chúng tôi đã bật CORS" không đủ?

CORS là chính sách trình duyệt về cách scripts từ origin khác truy cập tài nguyên. CORS không phải authorization backend và không biến một request form-based đã được gửi thành vô hại. Nếu API cho phép cookie và unsafe operation bằng form/simple request, server vẫn phải xác minh tính hợp lệ của thay đổi.

**Phân biệt:**

| Phát biểu | Đúng/sai |
| --- | --- |
| "CORS có thể ngăn JS từ trang khác đọc response" | Đúng theo policy và điều kiện |
| "Nếu CORS không cho đọc response thì request không thể có side effect" | **Sai** |
| "Mọi POST cross-site đều cần preflight" | **Sai** |
| "fetch credentials include sẽ bỏ qua SameSite" | **Sai** |
| "Nếu browser không tự gửi credential mà attacker không có token, classic CSRF khó xảy ra" | Đúng với điều kiện không có ambient credential khác |
| "Server vẫn phải kiểm tra authorization cho mọi request" | Đúng, CSRF không thay authentication/authorization |

## 7. Cơ chế CSRF token đồng bộ (*Synchronizer Token Pattern*)

Ý tưởng: server sinh một token ngẫu nhiên khó đoán, ràng buộc với phiên hoặc ngữ cảnh phù hợp. Ứng dụng trả token cho trang đáng tin, rồi yêu cầu client gửi lại token **ở vị trí mà browser không tự thêm vào mọi request cross-site**, ví dụ hidden form field hoặc request header.

Quy trình:

```text
Browser đã đăng nhập
   |
   | GET trang form từ app thật
   v
Server phát/giữ expected CSRF token của phiên
   |
   | HTML có hidden field _csrf hoặc JS đọc meta
   v
Browser gửi POST với:
   - cookie/session (browser có thể tự gắn)
   - _csrf / X-CSRF-TOKEN (trang đáng tin đưa vào)
   |
   v
CsrfWebFilter đối chiếu actual token với expected token
   |
   +--> Hợp lệ: request tiếp tục authentication/authorization/controller
   +--> Thiếu/sai: từ chối, thường 403
```

Một trang attacker khác origin có thể cố gửi form với cookie nhưng **không có expected token hợp lệ**. Same-origin policy ngăn attacker thông thường đọc HTML của origin đích để lấy token. Vì vậy server không chỉ hỏi "cookie đúng không?" mà còn hỏi "request có dữ liệu chống giả mạo được server cấp không?".

### Token khác cookie như thế nào?

Cookie session thường được browser tự đính vào request. Nếu bạn chỉ phát một **cookie CSRF** và kiểm tra sự hiện diện của chính cookie đó mà không yêu cầu một giá trị độc lập trong header/form, attacker vẫn có thể dựa vào browser gửi cookie. Với double-submit cookie, server phải kiểm tra **cookie so với token submit qua header/form**, và mô hình mạnh hơn ràng buộc token với session (signed/session-bound double submit) để chống cookie injection.

Không đặt token CSRF cố định trong HTML được cache công khai cho mọi người. Không đặt token ở URL không cần thiết vì URL dễ xuất hiện trong log, lịch sử browser và Referer. Token phải được xử lý theo cơ chế repository và vòng đời phiên của framework.

## 8. Spring Security WebFlux mặc định bảo vệ CSRF như thế nào?

Trong Spring Security 6.x WebFlux:

- `CsrfWebFilter` được Spring Security cấu hình khi CSRF đang bật (mặc định).
- Các **unsafe HTTP methods** như POST, PUT, PATCH, DELETE cần token theo matcher mặc định; các phương thức safe (GET/HEAD/OPTIONS/TRACE) thường được bỏ qua bước kiểm tra token.
- Repository mặc định là `WebSessionServerCsrfTokenRepository`: expected token được lưu trong `WebSession`.
- Từ Spring Security 6.0, `XorServerCsrfTokenRequestAttributeHandler` được dùng mặc định để mask giá trị token gửi ra nhằm giảm rủi ro BREACH. Giá trị token HTML có thể khác mã lưu trong repository vì được xử lý bởi request handler; không tự viết so sánh thủ công.
- Token được cung cấp như `Mono<CsrfToken>` trong thuộc tính của `ServerWebExchange` với key `CsrfToken.class.getName()`. Tính lazy nghĩa là view/controller phải truy cập/subcribe publisher thích hợp nếu cần render token.
- Mặc định form login/logout của Spring Security WebFlux cũng yêu cầu CSRF cho POST. Login CSRF và logout CSRF là các mối đe dọa riêng, không chỉ các API cập nhật dữ liệu.
- Với SPA/JSON, token thường cần gửi trong HTTP header như `X-CSRF-TOKEN`/`X-XSRF-TOKEN` tùy repository/handler, thay vì chỉ dựa vào form field.

**Trong bài thực hành, ta giữ CSRF mặc định. Không "sửa" lỗi HTTP 403 bằng `csrf.disable()`.**

### Vì sao GET /login vẫn được xem mà POST /login cần token?

GET chỉ lấy form; POST gửi credential và tạo/đổi trạng thái đăng nhập. Login CSRF có thể ép browser nạn nhân đăng nhập vào account do attacker kiểm soát rồi thực hiện hành động theo account đó, gây nhầm lẫn danh tính hoặc lộ dữ liệu vào account attacker. Vì vậy Spring Security yêu cầu token cho POST login theo mặc định.

Logout CSRF tương tự: một request giả có thể ép nạn nhân bị đăng xuất, làm gián đoạn công việc hoặc phục vụ chuỗi tấn công khác. `LogoutWebFilter` mặc định xử lý POST thay vì biến GET link thành logout ngay.

### CSRF khác Authorization

Một request có CSRF token **hợp lệ** vẫn cần authentication và authorization. Token chứng minh request có thể có ý định hợp lệ trong ngữ cảnh phiên; nó không thay thế role, ownership, rate limiting hoặc xác minh dữ liệu. Ngược lại, user đã đăng nhập và có role vẫn có thể bị 403 nếu POST thiếu CSRF.

## 9. Ví dụ ứng dụng Java 17+ Spring Boot WebFlux: giữ CSRF mặc định

Ví dụ dưới đây mô phỏng thay đổi một thiết lập (bật/tắt thông báo). Dữ liệu chỉ lưu trong **AtomicInteger** để dễ xác minh có side effect hay không; không phải mô hình lưu dữ liệu nhiều người dùng ở production.

### 9.1. Dependencies và cấu trúc project

Với project Gradle đã khai báo Spring Boot plugin và quản lý phiên bản dependencies, cần:

**`build.gradle`** (khối dependencies):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Không thêm `spring-boot-starter-web` cho demo thuần reactive: nếu MVC và WebFlux cùng có trên classpath, Spring Boot thường chọn Servlet. Dự án dùng Java 17+, tương thích bản Spring Boot 3.x và Spring Security 6.x.

Các file:

```text
src/main/java/example/csrf/
    CsrfDemoApplication.java
    SecurityConfiguration.java
    SettingsFormController.java
    SettingsController.java
src/main/resources/templates/
    settings-form.html
src/test/java/example/csrf/
    CsrfWebFluxTest.java
```

### 9.2. Main class

**`src/main/java/example/csrf/CsrfDemoApplication.java`**:

```java
package example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
```

### 9.3. SecurityWebFilterChain và user demo

**`src/main/java/example/csrf/SecurityConfiguration.java`**:

```java
package example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("local-test-password"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .anyExchange().authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .httpBasic(basic -> basic.disable())
                .build();
    }
}
```

- `@EnableWebFluxSecurity` là security cho WebFlux, không phải Servlet `HttpSecurity`.
- `formLogin(Customizer.withDefaults())` cung cấp trang login mặc định tại `GET /login` và xử lý `POST /login`.
- `httpBasic(basic -> basic.disable())` giúp demo nhất quán với session cookie/form login thay vì HTTP Basic prompt; điều này **không** tắt CSRF.
- `anyExchange().authenticated()` bảo vệ trang form thiết lập và endpoint cập nhật; `GET /public/ping` là endpoint công khai.
- **Không có lời gọi `csrf.disable()`**: CSRF WebFilter vẫn kiểm tra unsafe requests.
- Người dùng có mật khẩu mẫu chỉ phục vụ localhost/test. Production phải lấy user từ nguồn được quản lý, lưu password hash mạnh và dùng HTTPS.

### 9.4. Trang form GET và token do Spring phát

Để bảo đảm token được chuyển đến template, controller lấy `Mono<CsrfToken>` mà `CsrfWebFilter` đặt trong `ServerWebExchange`.

**`src/main/java/example/csrf/SettingsFormController.java`**:

```java
package example.csrf;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.reactive.result.view.Rendering;
import reactor.core.publisher.Mono;

@Controller
public class SettingsFormController {

    @GetMapping("/settings-form")
    public Mono<Rendering> form(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        return token.map(csrf -> Rendering.view("settings-form")
                .modelAttribute("_csrf", csrf)
                .build());
    }
}
```

Controller trả publisher để Spring subscribe trong request. Không gọi `block()`, không tự tạo token giả và không gửi token này trong link query string.

**`src/main/resources/templates/settings-form.html`**:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Thiết lập thông báo</title>
</head>
<body>
<main>
    <h1>Thay đổi thiết lập thông báo</h1>
    <form method="post" action="/settings/notifications">
        <label for="enabled">Nhận thông báo?</label>
        <select id="enabled" name="enabled">
            <option value="true">Có</option>
            <option value="false">Không</option>
        </select>
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <button type="submit">Lưu</button>
    </form>
</main>
</body>
</html>
```

Ở đây cố ý dùng `action="/settings/notifications"` thay vì `th:action` để minh họa **một hidden input CSRF rõ ràng** qua model. Nếu dùng `th:action` với Spring/Thymeleaf CSRF integration, engine có thể tự chèn token; tránh render hai input trùng tên và kiểm tra HTML cuối cùng. Đối với deployment có context path, form action phải được tạo đúng base path (ví dụ dùng URL expression của Thymeleaf). Không hardcode literal token hay copy token từ một session sang session khác.

Khi browser GET `/settings-form` từ ứng dụng thật, server render HTML có token hợp lệ và browser duy trì cookie session phù hợp. Một form do trang attacker tự tạo không thể đoán đúng token trong phiên này.

### 9.5. Endpoint thay đổi trạng thái và quan sát side effect

**`src/main/java/example/csrf/SettingsController.java`**:

```java
package example.csrf;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class SettingsController {

    private final AtomicInteger acceptedChanges = new AtomicInteger();

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/settings/status")
    public Mono<String> status() {
        return Mono.fromSupplier(
                () -> "updates=" + acceptedChanges.get());
    }

    @PostMapping(
            path = "/settings/notifications",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> change(ServerWebExchange exchange) {
        return exchange.getFormData().map(form -> {
            String enabled = form.getFirst("enabled");
            if (!"true".equals(enabled) && !"false".equals(enabled)) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "enabled must be true or false");
            }
            acceptedChanges.incrementAndGet();
            return "notifications=" + enabled;
        });
    }

    // Dùng để kiểm chứng dữ liệu mô phỏng trong test cùng package.
    void resetForTests() {
        acceptedChanges.set(0);
    }

    int updateCount() {
        return acceptedChanges.get();
    }
}
```

**Lưu ý về WebFlux:** `ServerWebExchange.getFormData()` trả `Mono<MultiValueMap<String,String>>`. Đó là cách rõ ràng để lấy field `enabled` trong **form body**. Không nhầm rằng `@RequestParam` trong WebFlux tự đọc form-encoded body giống mọi trường hợp Servlet MVC; ở WebFlux nó chủ yếu làm việc với request query parameters. Bài này dùng `getFormData()` để tránh mơ hồ.

`acceptedChanges` chỉ là **counter dùng chung trong RAM để minh họa side effect**, không phải bảng cấu hình theo user. Một hệ thống thật cần lưu theo user ID/tenant và kiểm tra owner/authorization trong service hoặc database; CSRF token **không thay thế phân quyền theo tài nguyên**.

### 9.6. Khi nào controller được gọi?

Nếu request POST:

- **Không có CSRF token**: `CsrfWebFilter` từ chối trước, `change(...)` **không** tăng counter.
- **Có token hợp lệ nhưng chưa đăng nhập**: authentication/authorization từ chối hoặc redirect về login, `change(...)` không được ghi dữ liệu.
- **Đã đăng nhập, token hợp lệ, form hợp lệ**: request qua security chain, counter tăng 1.
- **Đã đăng nhập, token hợp lệ nhưng `enabled` không hợp lệ**: controller trả 400, không tăng counter.
- **GET /settings/status**: không thay đổi counter, chỉ hiển thị giá trị.

Đây là điểm có thể kiểm chứng. Browser tự gửi cookie chỉ làm request có danh tính; token và authorization còn quyết định có chạy hành động hay không.

## 10. Kiểm thử bằng WebTestClient: CSRF thiếu, hợp lệ và side effect

Spring Security Test hỗ trợ `WebTestClient` bằng `springSecurity()`, `mockUser(...)` và `csrf()`. Test dưới đây dựng mock server từ ApplicationContext để gọi WebFlux security filters và controller, **không cần mở port thật**.

**`src/test/java/example/csrf/CsrfWebFluxTest.java`**:

```java
package example.csrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CsrfWebFluxTest {

    @Autowired ApplicationContext context;
    @Autowired SettingsController settings;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        settings.resetForTests();
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicGetDoesNotNeedCsrf() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousProtectedGetRedirectsToLogin() {
        client.get().uri("/settings/status")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().valueMatches("Location", ".*login.*");
    }

    @Test
    void authenticatedSafeGetNeedsNoCsrf() {
        client.mutateWith(mockUser("learner"))
                .get().uri("/settings/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("updates=0");
    }

    @Test
    void defaultLoginPageExists() {
        client.get().uri("/login")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> assertTrue(html.contains("username")));
    }

    @Test
    void customFormContainsCsrfInput() {
        client.mutateWith(mockUser("learner"))
                .get().uri("/settings-form")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> assertTrue(html.contains("name=\"_csrf\"")));
    }

    @Test
    void authenticatedPostWithoutCsrfIsBlocked() {
        client.mutateWith(mockUser("learner"))
                .post().uri("/settings/notifications")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("enabled", "false"))
                .exchange()
                .expectStatus().isForbidden();

        assertEquals(0, settings.updateCount());
    }

    @Test
    void authenticatedPostWithCsrfChangesState() {
        client.mutateWith(mockUser("learner"))
                .mutateWith(csrf())
                .post().uri("/settings/notifications")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("enabled", "false"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("notifications=false");

        assertEquals(1, settings.updateCount());
    }

    @Test
    void invalidFormIsRejectedEvenWithCsrf() {
        client.mutateWith(mockUser("learner"))
                .mutateWith(csrf())
                .post().uri("/settings/notifications")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("enabled", "invalid"))
                .exchange()
                .expectStatus().isBadRequest();

        assertEquals(0, settings.updateCount());
    }

    @Test
    void loginPostWithoutCsrfIsBlocked() {
        client.post().uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "learner")
                        .with("password", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void loginPostWithCsrfCanAuthenticate() {
        client.mutateWith(csrf())
                .post().uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "learner")
                        .with("password", "local-test-password"))
                .exchange()
                .expectStatus().is3xxRedirection();
    }
}
```

Chạy từ thư mục project có Gradle Wrapper:

```bash
./gradlew test --tests example.csrf.CsrfWebFluxTest
```

PowerShell:

```powershell
.\gradlew.bat test --tests example.csrf.CsrfWebFluxTest
```

**Kết quả kỳ vọng:** 10 test PASS khi project có các file và dependencies tương thích. Đây là dự kiến từ mã ví dụ, **không phải** bằng chứng đã chạy test trong workspace.

### Những gì đã được và chưa được kiểm chứng

- Các test GET cho thấy phương thức an toàn không cần CSRF token và endpoint protected vẫn yêu cầu authentication.
- Test POST không có token với `mockUser` chứng minh **authentication không thay CSRF**; 403 và counter 0 cho thấy controller không thực thi side effect.
- Test POST có `csrf()` chứng minh token hợp lệ cùng authentication cho phép cập nhật.
- Test login POST không có CSRF cho thấy **login cũng là unsafe action**.
- `mockUser(...)` là Authentication giả lập trong test, **không có nghĩa trình duyệt thật đã tự đính cookie**. Muốn chứng minh cookie/SameSite behavior phải thực hiện browser integration test dưới origin/site được kiểm soát.
- `csrf()` của Spring Security Test cung cấp CSRF hợp lệ cho mock request; test không kiểm chứng giá trị token random hay session storage đúng byte-for-byte.
- Các test dùng một context và counter chung, chạy tuần tự theo mặc định. Nếu bật parallel tests, cần cô lập instance/test state hoặc tránh reset counter chia sẻ.

## 11. Kiểm thử browser thật: xác minh khi nào cookie tự đi

Để kiểm tra điều kiện auto-sending, lập một **môi trường thử nghiệm thuộc quyền quản lý của bạn**, với ứng dụng chính và một origin khác hoặc cùng-site khác-origin. Không thử trên tài khoản hay hệ thống bên thứ ba.

Kịch bản phòng thủ:

1. Truy cập ứng dụng chính qua HTTPS, đăng nhập bằng browser thật.
2. Mở DevTools → Application/Storage → Cookies, quan sát **tên**, `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite` của cookie; không chia sẻ raw cookie value.
3. Tại origin test khác, dùng form POST mô phỏng gửi vào endpoint thử nghiệm không nhạy cảm của **chính hệ thống test**.
4. Trong DevTools → Network, kiểm tra request có được gửi hay không, cookie có được đính theo SameSite/domain/path/chính sách browser hay không; tránh xuất HAR chứa credential.
5. Bật Spring Security CSRF: POST thiếu token phải bị từ chối, dù browser có gắn cookie.
6. Gửi POST từ form thật của ứng dụng có token: cho phép khi đã login và đủ quyền.
7. Lặp lại với origin khác nhưng cùng site (sibling subdomain test) để thấy SameSite không tương đương same-origin.
8. Kiểm tra request GET không gây thay đổi dữ liệu; nếu có, sửa thiết kế endpoint.

**Đừng chỉ nhìn thấy HTTP 403 rồi kết luận cookie đã được gửi.** 403 có thể đến từ CSRF trước bước xác thực. Cần kiểm tra điều kiện gửi credential một cách riêng biệt, và kiểm soát dữ liệu test không nhạy cảm.

### Bảng quan sát browser theo tình huống

| Nguồn -> đích | Cookie | Kiểu request | Kỳ vọng phổ biến |
| --- | --- | --- | --- |
| Cùng origin, đã login | Cookie hợp lệ | POST form thật + CSRF token | Có thể đi qua cả authentication và CSRF |
| Khác site, cookie Strict | Cookie Strict thường không đi | Form POST | Thường thiếu session, ngoài ra CSRF vẫn bảo vệ |
| Khác site, cookie Lax | Cookie Lax thường không đi | Form POST | Nhiều browser chặn ambient credential; ngoại lệ phụ thuộc policy |
| Khác site, cookie Lax | Cookie Lax có thể đi | Top-level GET | Cực kỳ nguy hiểm nếu GET làm thay đổi trạng thái |
| Khác site, cookie None; Secure | Cookie có thể đi nếu browser cho phép | Form POST | CSRF token phải chặn request giả |
| Khác origin nhưng cùng site | Cookie có thể đi | Form POST | SameSite không chặn chỉ vì origin khác |
| Cross-origin fetch, mặc định | Thường không gồm cross-origin credential | `fetch()` | Credential mode mặc định `same-origin` |
| Cross-origin fetch, include | Cookie chỉ đi nếu policy cho phép | `fetch(... credentials:"include")` | Không vượt SameSite/third-party blocking |

Đây là các quy tắc phổ biến, không phải cam kết mọi browser/embedded webview/policy đều hoạt động giống nhau. Kết quả còn phụ thuộc redirect, scheme, cookie set-time, domain, third-party cookie restrictions và cách server tiếp nhận request.

## 12. Origin, Referer và Fetch Metadata: phòng thủ bổ sung

Một yêu cầu CSRF có thể được ngăn thêm bằng cách kiểm tra nguồn request:

- `Origin` cho biết origin phát sinh request trong nhiều loại request hiện đại. Server có thể yêu cầu nó khớp **origin được tin cậy** cho thao tác thay đổi trạng thái.
- `Referer` có thể giúp kiểm tra nguồn khi phù hợp, nhưng có thể bị thiếu do privacy/referrer policy; không nên bỏ qua mọi yêu cầu có header không tồn tại mà không có policy rõ ràng.
- `Sec-Fetch-Site` phân biệt `same-origin`, `same-site`, `cross-site`, `none` ở browser hỗ trợ. `Sec-Fetch-Mode`/`Sec-Fetch-Dest` giúp định nghĩa chính sách chặn cross-site unsafe navigation/fetch có chủ đích.
- Các header Fetch Metadata là **defense-in-depth** và cần xử lý client cũ, browser limitations, proxy và các integration được phép.
- Nếu có nhu cầu cross-origin hợp lệ (ví dụ SSO hoặc embedded app), cần allowlist cụ thể, test đầy đủ và không dựa vào wildcard origin tùy tiện.

**Không thay token bằng "chỉ kiểm tra Referer chứa tên miền" theo phép substring**: chuỗi có thể gây nhầm domain (ví dụ `app.example.test.attacker.invalid`). Khi kiểm tra Origin, phải parse scheme/host/port và so khớp origin chính xác; bảo đảm reverse proxy/forwarded headers được cấu hình tin cậy.

## 13. SPA, JSON API và CookieServerCsrfTokenRepository

Với SPA sử dụng session cookie, browser có thể gửi `fetch` cùng cookie. JavaScript tin cậy của ứng dụng cần có cách nhận token và đưa vào header, thường là `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` theo cấu hình.

Trong Spring Security WebFlux, có thể thay repository bằng `CookieServerCsrfTokenRepository` cho pattern SPA phù hợp. Tuy nhiên:

1. Cookie CSRF có thể được client-side JavaScript đọc nếu cấu hình HttpOnly tương ứng; điều đó là **đánh đổi**, không phải cấu hình mặc định nên bật khắp hệ thống.
2. Đặc tả SameSite, Secure, Path, Domain và trusted origin phải được xem xét cùng nhau.
3. Từ Spring Security 6.x, default `XorServerCsrfTokenRequestAttributeHandler` xử lý token dùng cho HTML/BREACH. Token raw trong cookie và token masked trong form/header có thể cần xử lý theo đúng request handler; **không chỉ đổi repository và mong mọi SPA tự hoạt động**.
4. Nếu frontend dùng Bearer token trong header mà **không có cookie/Basic/mTLS tự gửi**, classic browser CSRF có thể không áp dụng cùng cách; đừng vô hiệu hóa CSRF khi hệ thống vẫn phát session cookie hoặc refresh token cookie dùng được cho unsafe endpoints.
5. Tránh tạo endpoint công khai `GET /csrf` nhưng trả token/cookie với CORS quá rộng khiến website attacker đọc được token. CSRF token không phải API key, nhưng nếu bị tiết lộ cross-origin thì mất tác dụng phòng thủ.
6. Khi token hết hạn hoặc session timeout, UI có thể gặp 403; cần cách làm mới token/login có kiểm soát, không tắt CSRF hoặc trả lại default permit.

### Ví dụ conceptual fetch hợp lệ từ chính origin

```javascript
// Chạy từ JavaScript tin cậy được tải bởi ứng dụng của bạn.
// csrfToken được backend phát và frontend nhận qua kênh hợp lệ.
fetch("/api/settings", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ theme: "dark" })
});
```

Đây là **đoạn minh họa**, không độc lập chạy được: biến `csrfToken` và endpoint `/api/settings` chưa được định nghĩa trong project demo. Với API JSON, phải chọn repository/handler để backend xác nhận đúng header; tránh copy ví dụ form-encoded mà không đổi theo kiến trúc SPA.

## 14. Các trường hợp đặc biệt: login, logout, upload và GET sai semantics

### 14.1. Login CSRF

Tấn công login CSRF có thể ép trình duyệt nạn nhân đăng nhập vào tài khoản khác. Đây không phải lúc nào cũng làm attacker chiếm account nạn nhân, nhưng có thể khiến nạn nhân thao tác và lưu thông tin dưới account attacker. Vì login thay đổi authentication state, `POST /login` cần token. Spring Security WebFlux mặc định xử lý điều này khi CSRF bật.

### 14.2. Logout CSRF

Nếu logout được cho phép bằng GET, attacker có thể dùng navigation/image/link để làm người dùng bị đăng xuất. Default logout WebFlux yêu cầu `POST /logout` và CSRF. Không đổi matcher sang GET chỉ để có nút logout dễ viết; dùng form POST hoặc JavaScript của ứng dụng gửi POST kèm token.

### 14.3. Multipart upload

Multipart body đôi khi được xử lý/ghi ra file tạm trước khi kiểm tra CSRF token trong body. Với JavaScript có thể gửi token trong header để giảm rủi ro. Spring Security WebFlux có tùy chọn `tokenFromMultipartDataEnabled(true)` khi cần lấy token từ multipart body, nhưng phải cân nhắc tác động và kiểm tra permission/upload limits. Không giả định việc bật multipart CSRF không có chi phí xử lý body.

### 14.4. GET gây thay đổi trạng thái

Đây là lỗi thiết kế gây thiệt hại bất chấp CSRF filter mặc định vì safe methods thường bỏ qua token. Cách sửa là **thay đổi HTTP method và semantics**, không chỉ gắn thêm một token vào URL GET. Không dùng GET để xóa account, chuyển tiền, reset password hoặc cấp quyền.

### 14.5. Stateless không có nghĩa là miễn nhiễm

Một JWT chứa đủ trạng thái được lưu trong cookie vẫn có thể tự gửi đến backend. Hệ thống "stateless" nhưng dùng JWT cookie vẫn cần đánh giá CSRF. Tính stateless của server không quyết định browser gửi credential hay không; **cách credential được đưa vào request** mới là yếu tố chính.

## 15. Khi nào nên tùy chỉnh CSRF trong Spring Security WebFlux?

### 15.1. Giữ mặc định cho browser app

Nếu app có form login, cookie session và những request thay đổi trạng thái, **giữ CSRF mặc định** là lựa chọn khởi đầu. Template cần đưa token đúng vào form/header. Kiểm thử 403 với missing token và success với actual token.

### 15.2. Bỏ qua một endpoint đặc biệt

Một số webhook machine-to-machine hoặc endpoint xác thực bằng chữ ký riêng **không dùng browser cookies** có thể không cần CSRF token. Có thể cấu hình `ServerHttpSecurity.CsrfSpec.requireCsrfProtectionMatcher(...)` với matcher phù hợp, nhưng phải chứng minh rằng không có ambient credentials và không vô tình bỏ cả nhóm endpoint browser-facing.

Đừng copy một matcher `permitAll` làm căn cứ để bỏ CSRF: public endpoint cũng có thể thay đổi trạng thái. Cần threat model và integration tests riêng.

### 15.3. Tắt hoàn toàn CSRF chỉ khi threat model cho phép

Một API chỉ phục vụ non-browser clients, xác thực bằng Bearer token **chỉ từ header được client chủ động cung cấp**, không có session/cookie/Basic tự gửi, có thể chọn tắt CSRF sau đánh giá rủi ro. Điều đó không áp dụng chung cho WebFlux hoặc mọi REST API; đặc biệt nếu sau này thêm browser auth, login hoặc refresh cookie, giả định cũ có thể không còn đúng.

Cấu hình `.csrf(csrf -> csrf.disable())` xóa rào chắn CSRF của framework, nên chỉ dùng có lý do, review, tài liệu và test. Trong **demo chính không sử dụng** lệnh này.

## 16. Các lỗi thường gặp

| Hiện tượng hoặc niềm tin sai | Vấn đề | Hướng sửa |
| --- | --- | --- |
| "Có CORS nên không bị CSRF" | Browser có thể gửi form/simple request dù script không đọc response | Dùng CSRF token/Origin và safe HTTP methods |
| "JWT thì không CSRF" | JWT trong cookie vẫn được browser tự gửi | Phân biệt token cookie với Bearer header |
| "Basic Auth thì không CSRF" | Browser có thể tự đính Basic credentials đã cache | Đánh giá ambient Basic trong browser |
| "SameSite=Lax chặn mọi CSRF" | Cross-site top-level GET có cookie; cùng-site khác-origin vẫn có thể gửi | Không đổi trạng thái qua GET; giữ token |
| "SameSite bảo vệ mọi subdomain" | Same-site khác origin có thể gửi cookie tới target | Origin/CSRF token, quản lý subdomain |
| "Tắt CSRF vì POST nhận 403" | Bỏ tuyến phòng thủ thay vì sửa form | GET token, giữ cookie, gửi hidden field/header đúng |
| "CSRF token giống session cookie" | Cookie tự gắn, token cần được gửi qua trường/header không tự gắn | Synchronizer token pattern |
| "Đã authenticated thì POST phải qua" | Authentication không chứng minh ý định thực hiện POST | Yêu cầu CSRF cho unsafe methods |
| "Mọi cross-origin fetch đều gửi cookie" | Fetch default `same-origin` | Hiểu credential mode, cookie policy |
| "credentials include vượt được SameSite" | Browser vẫn áp SameSite/third-party cookie policy | Đánh giá cookie attributes |
| "Cứ JSON là miễn nhiễm CSRF" | Content-Type validation hoặc route sai, form polyglot, CORS lỗi có thể phá giả định | Strict Content-Type, token/Origin, test request thật |
| "GET xóa dữ liệu nhưng vẫn an toàn" | CSRF filter thường bỏ qua GET | Dùng unsafe method đúng và token |
| "Chỉ kiểm tra Referer chứa chuỗi domain" | Có thể bị nhầm hostname, header thiếu | So khớp Origin chính xác và policy fallback rõ |
| "Dùng `CookieServerCsrfTokenRepository` rồi là xong" | Raw/masked token, header, cookie flags phải tương thích | Cấu hình SPA theo Spring Security version |
| "Token phải có trong query URL" | Rò rỉ qua log, history, Referer | Dùng form body hoặc header |
| "Form khác origin không thể POST" | HTML form có thể gửi request mà không đọc response | Dựa vào token/Origin và authz thay vì CORS |
| "Chỉ cần test HTTP 403 là biết cookie không được gửi" | 403 có thể là do CSRF trước auth | Kiểm tra request cookies/credentials riêng |
| "CSRF protection thay thế authorization" | Có token không đồng nghĩa được phép sửa tài nguyên | Vẫn kiểm tra role/owner/tenant |
| "XSS không liên quan" | XSS cùng origin có thể lạm dụng token và credential | Chống XSS, CSP, output encoding |
| "Cookie HttpOnly chặn CSRF" | HttpOnly chỉ cấm JS đọc cookie, browser vẫn gửi nó | HttpOnly + CSRF token + SameSite |

## 17. Checklist triển khai an toàn

1. **Kiểm kê hành động thay đổi trạng thái**: POST/PUT/PATCH/DELETE và đặc biệt GET có side effect cần sửa.
2. **Phân loại mọi nguồn authentication**: session, Basic, JWT cookie, refresh token cookie, client certificate, custom cookie. Xác định cái gì browser tự gửi.
3. **Xác định origin/site/cookie settings**: Domain, Path, Secure, HttpOnly, SameSite, TLS proxy và policy trình duyệt mục tiêu.
4. **Giữ CSRF token** cho unsafe requests có ambient credentials. Đảm bảo form/meta/header nhận token qua kênh đáng tin, token ràng buộc phiên và không lộ cross-origin.
5. **Kiểm tra login/logout** cũng cần CSRF, không cho GET làm logout.
6. **Phòng thủ nhiều lớp**: SameSite, Origin/Referer khi đáng tin, Fetch Metadata, validation Content-Type, rate limiting cho thao tác nhạy cảm.
7. **Authentication/authorization vẫn đầy đủ**: token hợp lệ không thay thế check owner/tenant/role.
8. **Không để cross-origin đọc token**: review CORS, token endpoint, CDN/template cache, lỗi XSS và việc chia sẻ session.
9. **Kiểm thử browser và WebTestClient**: GET safe, POST thiếu token, token sai, token hợp lệ, anonymous, session timeout và browser cookie policy.
10. **Giám sát và xử lý lỗi**: phân biệt `CsrfException`/403 với password sai/403 do role, không log raw token/cookie/password, có correlation ID.
11. **Kiểm thử nhiều môi trường**: reverse proxy, HTTPS, subdomain, nhiều instance/session store, SPA cross-origin hợp lệ.
12. **Review khi thay authentication**: chuyển từ Bearer-only sang cookie hoặc bật form login có thể làm threat model CSRF thay đổi hoàn toàn.

## 18. Câu hỏi và bài tập tự luyện

1. Nạn nhân có session cookie `SameSite=Strict`, đang ở `attacker.invalid`. Khi trang gửi cross-site POST tới app, cookie có đi không? Điều gì xảy ra nếu attacker kiểm soát subdomain **cùng site**?
2. Một ngân hàng dùng `GET /transfer?amount=100` để chuyển tiền. Tại sao `SameSite=Lax` vẫn có thể không bảo vệ?
3. Một SPA gọi API bằng `Authorization: Bearer ...` lưu trong memory, không dùng cookie hoặc Basic. Giải thích vì sao classic CSRF khác một SPA lưu JWT trong HttpOnly cookie.
4. Viết test `WebTestClient` gửi POST đã `mockUser` nhưng **không có `csrf()`**: assert 403 và không xảy ra side effect.
5. Dùng `csrf()` trong test, assert POST được xử lý. Vì sao test này không chứng minh browser cross-site gửi cookie?
6. Mở form Thymeleaf trong demo, xem hidden `_csrf` có được render và session cookie có phù hợp. Sau đó bỏ hidden field trong môi trường test: kết quả?
7. Tạo một trang test khác origin, gửi form tới endpoint **chỉ dùng cho demo** và so sánh browser cookie settings Strict/Lax/None. Ghi nhận Site, Origin và method.
8. Thêm endpoint `POST /admin/settings` yêu cầu ADMIN. Đưa token hợp lệ nhưng đăng nhập USER; chứng minh CSRF không bypass authorization.
9. Mô phỏng session timeout: token trên form cũ không còn hợp lệ; thiết kế cách UI thông báo và lấy form/token mới an toàn.
10. Nếu chuyển app sang nhiều instance và WebSession được chia sẻ qua backend, xác định nơi CSRF expected token được giữ và ảnh hưởng của session invalidation.
11. Thêm Fetch Metadata policy vào môi trường thử nghiệm, test same-origin, same-site, cross-site và client không gửi header. Đừng coi header duy nhất là giải pháp.
12. Viết một tài liệu threat model ngắn nêu rõ: credential tự gửi? Unsafe action nào? Browser nào? CSRF token ở đâu? Cookie và CORS thế nào? Trạng thái deny và logging ra sao?

## Tổng kết

**CSRF chỉ phát huy khi browser có thể gửi credential hợp lệ tới ứng dụng mà không cần sự hợp tác của trang gốc, và server nhầm "request có danh tính" với "người dùng có ý định thực hiện hành động".** Cần nhìn đồng thời bốn điều kiện: hành động có tác động, ambient credential được gửi, request giả có thể được tạo, và thiếu kiểm tra CSRF/nguồn phù hợp.

Trong Spring Security WebFlux, cách phòng thủ phổ biến là **giữ `CsrfWebFilter` mặc định**, để expected token trong WebSession, render actual token ở form hoặc header, và từ chối unsafe requests thiếu token. CORS, SameSite, HttpOnly, JWT hay HTTPS đều có vai trò riêng nhưng không thay thế toàn bộ kiểm tra CSRF. Test phải xác nhận không chỉ HTTP status mà còn **không có side effect** khi CSRF thất bại.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — CSRF cho WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — CSRF và trình duyệt tự gửi credential](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — Testing WebFlux / WebTestClient](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security — Testing CSRF trong WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html)
- [MDN — CSRF](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF)
- [MDN — Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
