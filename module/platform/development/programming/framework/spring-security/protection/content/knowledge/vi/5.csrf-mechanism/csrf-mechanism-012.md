# Điều kiện đánh giá nguy cơ theo cách lưu và gửi thông tin xác thực

## Mục tiêu học tập

Sau bài học thuộc chương **Cơ chế CSRF**, người học có thể:

- Đánh giá nguy cơ **Cross-Site Request Forgery (CSRF)** từ **cách browser lưu, gửi và sử dụng credential**, thay vì dựa vào tên công nghệ như “JWT”, “stateless”, “REST” hoặc “SPA”.
- Phân biệt **credential do trình duyệt tự gửi** (session cookie, JWT cookie, một số cơ chế HTTP authentication) với **credential do client chủ động gắn** (ví dụ Bearer token trong header `Authorization`).
- Vẽ đường đi **nơi lưu → HTTP request → authentication filter → endpoint** và tìm mọi đường xác thực fallback.
- Xác định bề mặt CSRF ở ứng dụng session, JWT-in-cookie, Bearer-only, BFF, refresh cookie, login/logout, HTTP Basic và ứng dụng đa origin.
- Hiểu giới hạn của `SameSite`, `HttpOnly`, `Secure`, CORS, Same-Origin Policy (SOP), HTTP method, CSP và CSRF token.
- Cấu hình có căn cứ cho **Spring Security Servlet** và **Reactive/WebFlux**, giữ CSRF ở route browser dùng cookie và đánh giá chặt trước khi miễn CSRF ở một API Bearer-only.
- Thiết kế kiểm thử browser thật và các bài kiểm thử `MockMvc`/`WebTestClient` để chứng minh cả **luồng token** và **đường xác thực thực sự**.

## 1. Vì sao “có JWT” chưa trả lời được câu hỏi CSRF?

Giả sử API cập nhật tên hiển thị:

~~~http
POST /api/profile HTTP/1.1
Host: app.example.com
Content-Type: application/json

{"displayName":"Alice"}
~~~

Nếu backend sử dụng JWT, có thể tuyên bố không cần CSRF token không? **Không.** JWT nói về **định dạng token**, không nói browser đưa token vào request như thế nào.

**Kiến trúc A — JWT trong cookie:**

~~~http
POST /api/profile HTTP/1.1
Host: app.example.com
Cookie: ACCESS_TOKEN=eyJ...
Content-Type: application/x-www-form-urlencoded

displayName=Changed
~~~

Nếu browser tự gửi cookie khi trang ngoài kích hoạt request, backend có thể nhận ra một credential hợp lệ mà kẻ tấn công không cần biết giá trị. Nếu server cho phép thao tác và không kiểm chứng nguồn request, nguy cơ **CSRF** vẫn có thể tồn tại, dù JWT được ký và server không lưu session.

**Kiến trúc B — JWT chỉ ở Bearer header do mã client chủ động đặt:**

~~~http
POST /api/profile HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...
Content-Type: application/json

{"displayName":"Alice"}
~~~

Nếu API **chỉ chấp nhận Bearer header** và browser **không tự gắn credential khác** vào request, một form cross-site đơn giản không có khả năng tự chèn access token bí mật vào `Authorization`. Đường tấn công **CSRF truyền thống dựa trên cookie** thường không đáp ứng điều kiện về credential tự gửi. Nhưng API vẫn phải bảo vệ trước XSS, đánh cắp token, scope/role sai, cấu hình CORS yếu và các đường xác thực phụ.

> **Quy tắc:** Đừng hỏi “token có phải JWT không?” trước. Hãy hỏi “browser có tự gửi credential mà server chấp nhận khi attacker kích hoạt request không?”.

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, cách đánh giá theo luồng credential giúp kết hợp đúng CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và quản lý session trên cả **Servlet** lẫn **Reactive**.

## 2. Điều kiện hình thành một rủi ro CSRF

Ở kịch bản CSRF dựa trên phiên/cookie, thường cần các điều kiện:

1. **Có hành động nhạy cảm hoặc thay đổi trạng thái:** chuyển tiền, đổi email, đặt hàng, thay quyền, logout. Login là trường hợp đặc biệt vì bản thân request có thể tạo phiên mới.
2. **Attacker kích hoạt được request đến endpoint:** một form POST, điều hướng GET, nguồn same-site khác origin hoặc một luồng browser được phép. Attacker **không cần đọc response** để tạo tác động.
3. **Credential có thể xuất hiện trong request mà attacker không biết bí mật:** cookie phiên, cookie chứa token, HTTP authentication do browser cache hoặc client certificate theo chính sách trình duyệt.
4. **Endpoint chấp nhận request đó:** phương thức, content type, body và đường xác thực tương thích; không có CSRF token hoặc kiểm tra chống giả mạo hiệu quả.
5. **Các điều kiện browser cho phép đường tấn công:** Cookie `SameSite` có thể chặn một số request, nhưng không bao phủ mọi điều hướng, same-site subdomain hoặc trường hợp không dùng cookie.

Nếu thiếu điều kiện thứ ba trên **tất cả đường xác thực**, nguy cơ CSRF kiểu cookie thường thấp. Tuy nhiên **login CSRF**, OAuth callback và các endpoint tạo/thay đổi trạng thái xác thực cần đánh giá riêng; không áp công thức máy móc.

~~~mermaid
flowchart TD
    A[Endpoint có thay đổi trạng thái?] -->|Không| B[Đánh giá đọc dữ liệu, xác thực, phân quyền và các rủi ro khác]
    A -->|Có| C[Liệt kê mọi credential backend chấp nhận]
    C --> D{Browser có tự gửi ít nhất một credential?}
    D -->|Có| E[Đánh giá request attacker có thể kích hoạt]
    D -->|Không| F[Chứng minh API thực sự bearer-only, không có fallback]
    E --> G{Request có thể tới server với credential?}
    G -->|Có| H[Áp dụng anti-CSRF phù hợp và test]
    G -->|Bị chặn ở một ngữ cảnh| I[Kiểm tra ngữ cảnh khác: same-site, GET, login và browser khác]
    F --> J[Có thể miễn CSRF theo route sau đánh giá; vẫn phải bảo vệ token và quyền]
~~~

**Lưu ý:** “Browser không gửi cookie ở một request tôi vừa thử” không chứng minh endpoint không có rủi ro trên **mọi browser và mọi ngữ cảnh**.

## 3. Tách ba tầng: nơi lưu, đường vận chuyển và backend chấp nhận gì

### 3.1. Nơi lưu credential

Credential có thể được lưu ở:

- **Server-side session store:** Backend lưu phiên; browser chỉ giữ định danh phiên như `JSESSIONID`.
- **Browser cookie:** Có thể chứa session ID, access token JWT, opaque token hoặc refresh token.
- **JavaScript memory:** Token nằm trong state của trang; chỉ được gửi nếu mã client thêm vào request.
- **`localStorage`, `sessionStorage`, `IndexedDB`:** Browser lưu dữ liệu cho script được phép truy cập; **không tự thêm token vào header HTTP**.
- **Browser-managed authentication cache:** HTTP Basic, Digest, Negotiate hoặc cơ chế tương tự có thể được browser tự sử dụng theo ngữ cảnh.
- **BFF (Backend for Frontend):** Browser giữ session cookie của BFF; access token để gọi API thường do BFF quản lý và gắn vào request server-to-server.

Cùng một access token có thể được lưu ở hai nơi khác nhau; quyết định CSRF cần xét **cách token đi vào request**, không chỉ vị trí lưu.

### 3.2. Cách credential xuất hiện trên đường dây

| Nơi lưu/cơ chế | Dấu hiệu trong request | Ai thêm credential? | Bài toán nổi bật |
|---|---|---|---|
| Session cookie | `Cookie: JSESSIONID=...` | **Browser tự gửi** | CSRF cho unsafe request |
| JWT access token trong cookie | `Cookie: ACCESS_TOKEN=...` | **Browser tự gửi** | JWT có chữ ký vẫn có thể bị CSRF |
| Opaque token trong cookie | `Cookie: AUTH=...` | **Browser tự gửi** | Tương tự JWT cookie |
| Access token trong memory | `Authorization: Bearer ...` nếu JS đặt | **Client chủ động** | XSS, đánh cắp token, xác thực quyền |
| Access token trong localStorage | Bearer header nếu JS lấy và đặt | **Client chủ động** | XSS/token theft; không tự tạo cookie CSRF |
| Token trong sessionStorage/IndexedDB | Bearer header nếu code đặt | **Client chủ động** | Khác vòng đời, tương tự memory về vận chuyển |
| HTTP Basic cache | `Authorization: Basic ...` | **Browser có thể tự gửi** | Header Authorization không luôn là thủ công |
| mTLS | Client certificate tại TLS handshake | Client/browser có thể tự trình | Đánh giá credential ở tầng TLS |
| BFF session cookie | `Cookie: BFF_SESSION=...` | **Browser tự gửi** tới BFF | CSRF ở ranh giới browser → BFF |
| Refresh token trong cookie | `Cookie: REFRESH_TOKEN=...` | **Browser tự gửi** tới refresh endpoint | CSRF/token rotation/abuse trên refresh |

`HttpOnly` giúp tránh JavaScript thông thường đọc cookie, **không ngăn browser gửi cookie**.

### 3.3. Server có thể có nhiều đường xác thực cùng lúc

Ví dụ request chứa cả cookie lẫn Bearer:

~~~http
POST /api/orders HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Authorization: Bearer ACCESS_TOKEN_B
~~~

Khi phân tích, phải trả lời:

- Không có Bearer header, cookie phiên có đủ để API xem request là đã đăng nhập không?
- Không có cookie, Bearer header có được chấp nhận không?
- Khi cùng có cả hai, danh tính/quyền của A hay B được sử dụng?
- Endpoint refresh, logout, upload và tài khoản quản trị có áp policy khác không?
- Có custom filter hoặc API gateway đọc cookie rồi gắn header xác thực vào request phía sau không?
- Có một security chain khác được chọn do path/method không?

**Nếu bất kỳ đường fallback nào dùng credential browser tự gửi, không được gọi toàn bộ API là Bearer-only để miễn CSRF.**

## 4. Cookie: tại sao trình duyệt tự gửi credential?

Ví dụ response login:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=random-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ở các request tiếp theo, browser quyết định gửi cookie theo hostname, path, HTTPS và ngữ cảnh site. Trang attacker **không cần biết session ID** để khiến browser thử gửi request tới host đích.

### 4.1. HttpOnly và Secure không phải token chống CSRF

- `HttpOnly`: Hạn chế JavaScript thông thường đọc cookie bằng `document.cookie`, nhưng browser vẫn có thể tự gắn cookie vào request.
- `Secure`: Giới hạn việc gửi cookie qua kết nối an toàn phù hợp, nhưng một request giả mạo đến **HTTPS** vẫn có thể mang cookie.
- `Domain`/host-only: Quyết định cookie áp dụng cho **hostname đích** nào, không chứng minh request được khởi tạo từ origin nào.
- `Path`: Giới hạn đường dẫn nhận cookie, không phải ranh giới bảo mật độc lập giữa các ứng dụng cùng host.
- `SameSite`: Giới hạn một số request theo quan hệ **site**, không hoàn toàn theo **origin**.

### 4.2. Same-site khác same-origin

Trong schemeful same-site, hai URL:

~~~text
https://app.example.com
https://blog.example.com
~~~

có thể thuộc **cùng site** (scheme và registrable domain) nhưng **khác origin** (hostname). Một trang `blog.example.com` bị chiếm quyền có thể tạo POST đến `app.example.com`; cookie của app vẫn có thể được browser gửi tới app với `SameSite=Strict` hoặc `Lax` nếu các điều kiện khác phù hợp.

Trong khi đó, **Same-Origin Policy** thường không cho script ở blog đọc DOM/token của app. Vì vậy CSRF token còn có vai trò quan trọng khi có subdomain cùng site ít tin cậy.

### 4.3. Bảng SameSite phổ biến

Giả định cookie có phạm vi host/path và `Secure` phù hợp; browser không áp thêm chặn cookie bên thứ ba:

| Ngữ cảnh | `Strict` | `Lax` | `None; Secure` |
|---|---|---|---|
| POST cùng origin | Thường gửi | Thường gửi | Thường gửi |
| POST khác origin nhưng cùng site | Thường gửi | Thường gửi | Thường gửi |
| Top-level GET từ site khác | Thường không | **Thường gửi** | Có thể gửi |
| Top-level POST từ site khác | Không | Thường không | Có thể gửi |
| Iframe hoặc subresource từ site khác | Không | Thường không | Có thể gửi |
| Cross-site fetch có `credentials: "include"` | Không | Thường không | Có thể gửi nếu browser policy cho phép |

Bảng là mô hình **thường gặp**, không phải hợp đồng cho mọi browser. Cookie không khai báo SameSite có thể chịu ngoại lệ tương thích khác với `SameSite=Lax` khai báo rõ. `SameSite=None` cũng không thắng được chính sách chặn third-party cookie.

**Hệ quả:** `SameSite=Lax` có thể gửi cookie trong **top-level GET cross-site**. Vì vậy **GET phải chỉ đọc**; endpoint `GET /delete-account` hoặc GET logout thực hiện hành động trực tiếp là lỗi thiết kế, và mặc định Spring Security thường không yêu cầu CSRF token với GET.

## 5. Browser có thể tạo request gì mà không biết credential?

### 5.1. Form POST từ trang khác

Một HTML form có thể được gửi mà trang attacker **không cần đọc response**:

~~~html
<!-- Chỉ minh họa kịch bản giả mạo trong môi trường thử nghiệm. -->
<form method="post" action="https://app.example.com/profile/email">
  <input type="hidden" name="email" value="unwanted@example.test">
</form>
~~~

Browser có thể tự gửi cookie theo policy; CORS **không bắt buộc** phải cho phép đọc response để form gửi. Nếu API nhận form body và cookie, thao tác có thể được thực hiện nếu server thiếu bảo vệ CSRF.

Đây là lý do server cần token trong hidden field/header theo đúng ngữ cảnh phiên.

### 5.2. JSON fetch và CORS preflight

~~~javascript
await fetch("https://api.example.com/orders", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ itemId: "book-1" })
});
~~~

Request JavaScript cross-origin dùng JSON thường cần CORS preflight. Nhưng:

- Một HTML form đơn giản có thể gửi POST **không cần preflight**.
- Backend có thể chấp nhận `application/x-www-form-urlencoded`, `text/plain` hoặc `multipart/form-data` ngoài JSON.
- CORS quy định quyền đọc response và một số thao tác browser, **không xác minh CSRF token**.
- `credentials: "include"` không bỏ qua SameSite, Secure hay chính sách chặn cookie.

### 5.3. Authorization do ứng dụng chủ động gắn

~~~javascript
const token = getAccessTokenFromApplicationState();

await fetch("/api/orders", {
  method: "POST",
  headers: {
    Authorization: "Bearer " + token,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ itemId: "book-1" })
});
~~~

`getAccessTokenFromApplicationState()` chỉ là placeholder cho hàm của ứng dụng. Một form HTML ở origin ngoài **không tự biết token hoặc tự chèn Bearer header**. Với API thật sự chỉ chấp nhận Bearer header, nguy cơ CSRF cổ điển dựa trên credential tự gửi thường thấp hơn.

Nhưng **không phải mọi header Authorization đều do JavaScript chủ động đặt**: browser có thể tự gửi HTTP Basic/Digest/Negotiate credential đã cache, tùy chính sách và ngữ cảnh. Bởi vậy cần xác minh cơ chế auth thực tế.

## 6. Nơi lưu access token tạo đánh đổi giữa CSRF và XSS

### 6.1. JWT/opaque access token trong cookie HttpOnly

Cookie access token là **credential tự gửi**. JWT có chữ ký, claim `exp`, `aud` hoặc `iss` không thay đổi cách browser gắn cookie. Server “stateless” vẫn có thể chịu CSRF nếu nhận cookie chứa JWT cho request thay đổi trạng thái.

`HttpOnly` giúp giảm việc JavaScript đọc trực tiếp token nhưng **không ngăn request có cookie**; SameSite cũng không thay hoàn toàn CSRF token.

### 6.2. localStorage, sessionStorage, IndexedDB

Các storage này không tự tạo `Authorization` header; client cần đọc và đặt header. Do đó chúng thường **không tạo cùng đường CSRF dựa vào cookie** khi API chỉ nhận Bearer.

Tuy nhiên script XSS chạy cùng origin có thể đọc/sử dụng credential mà JavaScript hợp lệ truy cập. `sessionStorage` có vòng đời khác `localStorage` nhưng không tự chống XSS. Không kết luận “localStorage là giải pháp tốt nhất” chỉ vì nguy cơ CSRF thấp hơn.

### 6.3. Access token trong memory

Memory-only token cũng không tự được browser gắn vào request. Nhưng:

- XSS cùng origin có thể gọi API qua frontend hoặc dùng các khả năng JS hợp lệ.
- Reload/tab mới có thể mất token, khiến ứng dụng cần cấp lại.
- Nếu cấp lại thông qua một **refresh token cookie**, endpoint refresh có đường credential tự gửi riêng.

**Một hệ thống phải đánh giá từng endpoint**, không phân loại tất cả theo nơi lưu của access token.

### 6.4. HTTP Basic và client certificate

Với HTTP Basic cache hoặc mTLS do browser quản lý, credential có thể được sử dụng mà mã JavaScript không cần trực tiếp gắn token. Nếu attacker kích hoạt được request dưới credential ấy, nguy cơ CSRF có thể tồn tại. SameSite chỉ kiểm soát **cookie**, không kiểm soát mọi cách browser mang credential.

## 7. Các mô hình hỗn hợp dễ bị kết luận sai

### 7.1. API vừa chấp nhận Bearer vừa chấp nhận session cookie

Nếu SPA thường gửi `Authorization: Bearer ...` nhưng backend có thể fallback sang `JSESSIONID` khi không có Bearer, attacker có thể cố tạo request **chỉ mang cookie**.

Phải test trực tiếp cookie-only POST không có Bearer. Nếu backend vẫn xác thực và thực hiện thay đổi, API còn **bề mặt CSRF**. Đừng chỉ nhìn request “happy path” của SPA rồi miễn CSRF toàn bộ `/api/**`.

### 7.2. BFF: Bearer ở backend không loại CSRF tại browser

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant F as BFF
    participant A as Resource API

    U->>B: Bấm lưu
    B->>F: POST + BFF_SESSION cookie + CSRF token
    F->>F: Xác thực phiên và kiểm tra CSRF
    F->>A: POST + Authorization Bearer access token
    A-->>F: Response
    F-->>B: Response
~~~

Ở đây browser **không cần thấy access token**. BFF giữ credential cho API, nhưng browser vẫn tự gửi session cookie **tới BFF**. BFF phải đánh giá CSRF cho request browser → BFF, dù API nội bộ phía sau là Bearer-only.

### 7.3. Refresh token cookie và access token memory

Một SPA có thể dùng Bearer header cho `POST /api/orders` nhưng `POST /auth/refresh` dùng cookie `REFRESH_TOKEN` để cấp lại access token. Dù API nghiệp vụ không chịu CSRF kiểu cookie, **refresh endpoint có luồng credential khác**.

Cần đánh giá: request refresh có thể bị kích hoạt từ site ngoài không; rotation/extension session có tác động gì; SOP/CORS có chặn đọc token mới không; có kiểm tra Origin/CSRF token/Fetch Metadata phù hợp không; cookie SameSite, rate limit và chính sách thu hồi ra sao.

Attacker không nhất thiết đọc được access token mới chỉ vì đã kích hoạt refresh; nhưng cũng không thể bỏ toàn bộ nguy cơ chỉ vì response không đọc được.

### 7.4. Login và logout có tính đặc biệt

- **Login CSRF:** `POST /login` có thể **tạo session đã xác thực**, thậm chí khi trước đó chưa có session đăng nhập. Attacker có thể cố ép nạn nhân đăng nhập vào tài khoản attacker. Vì vậy không miễn CSRF cho login chỉ với lập luận “chưa có cookie xác thực”.
- **Logout CSRF:** `GET /logout` trực tiếp đăng xuất là thiết kế nguy hiểm, nhất là với top-level GET mang cookie `SameSite=Lax`. Dùng POST có token theo luồng bảo vệ mặc định.
- **OAuth callback:** `state`/PKCE/nonce là cơ chế phù hợp với luồng ủy quyền/đăng nhập; không thay CSRF token cho POST nghiệp vụ sau đó.

### 7.5. API gateway và reverse proxy

Một gateway có thể đọc cookie đăng nhập ở phía ngoài và gắn một header user/Bearer xuống backend. Backend nhìn thấy header, nhưng **browser → gateway** vẫn dùng cookie tự gửi. CSRF phải được kiểm soát ở ranh giới thực sự nhận browser request, hoặc qua biện pháp bảo vệ end-to-end thích hợp. Không đánh giá chỉ theo HTTP header giữa hai service nội bộ.

## 8. HTTP method, request body và khả năng kích hoạt thao tác

Spring Security thường không yêu cầu CSRF token với `GET`, `HEAD`, `OPTIONS` và `TRACE` vì chúng được coi là **safe methods**. Mọi endpoint GET phải giữ ngữ nghĩa chỉ đọc.

| Endpoint | Phương thức | Rủi ro cần xem |
|---|---|---|
| `GET /profile` | GET chỉ đọc | Xác thực/phân quyền và rò rỉ dữ liệu |
| `GET /orders/123/approve` | GET thay trạng thái nếu handler duyệt đơn | **Lỗi thiết kế**; Lax có thể gửi cookie trong top-level GET |
| `POST /profile/email` | POST thay trạng thái | CSRF khi có credential tự gửi |
| `PUT /profile` | PUT idempotent nhưng vẫn thay trạng thái | CSRF khi có ambient credential |
| `DELETE /saved-cards/7` | DELETE thay trạng thái | CSRF, authorization và xác nhận phù hợp |
| `POST /login` | POST tạo phiên | Login CSRF dù chưa có session xác thực |
| `POST /auth/refresh` | POST cấp/luân phiên token | Cookie refresh, token abuse và chống giả mạo |

Một endpoint “chỉ hỗ trợ JSON” cũng cần kiểm tra **server thực tế nhận những content type nào**. Form cross-site có thể gửi `application/x-www-form-urlencoded`, `text/plain` hoặc multipart. `Content-Type: application/json` trong frontend không chứng minh server sẽ từ chối mọi kiểu khác.

`PUT` và `DELETE` có thể **idempotent** nhưng không **safe**, nên không được miễn CSRF vì idempotency.

## 9. Mẫu phiếu đánh giá nguy cơ theo từng request

| Trường | Ví dụ cần ghi cụ thể |
|---|---|
| Đích và phương thức | `POST /api/profile` |
| Tác động | Đổi tên/email người dùng |
| Những đường xác thực được chấp nhận | Cookie session, Bearer header hoặc cả hai |
| Nơi lưu credential | Cookie, memory, localStorage, BFF |
| Ai thêm credential vào HTTP request? | Browser tự gửi / JavaScript đặt / proxy chuyển đổi |
| Request attacker có thể kích hoạt | Form POST, top-level GET, same-site cross-origin |
| Content type backend thực sự chấp nhận | Form, JSON, multipart, text/plain |
| Cookie policy | SameSite, Secure, HttpOnly, Domain, Path |
| Kiểm tra CSRF server | Repository, request handler, Origin/Fetch Metadata |
| Authentication fallback | Cookie-only, Basic auth, SSO, API gateway |
| Kết luận | Bật CSRF, hoặc miễn theo phạm vi đã chứng minh |
| Regression test | Cookie-only thiếu token; token sai phiên; Bearer-only từ chối cookie |

Một checklist như vậy giúp team không đánh đồng “token được lưu ở đâu” với “credential có tự xuất hiện trên một request do attacker kích hoạt hay không”.

## 10. Spring Security Servlet: web session và API Bearer-only là hai ranh giới khác nhau

### 10.1. Web dùng cookie: giữ CSRF mặc định

Trong ứng dụng Spring MVC, session ID thường nằm trong cookie `JSESSIONID` và được browser tự đính kèm. `CsrfFilter` cần kiểm tra các unsafe requests theo token repository/handler. Ví dụ cấu hình web session:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class WebSessionSecurityConfig {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**", "/login").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository()))
            .build();
    }
}
~~~

`HttpSessionCsrfTokenRepository` lưu expected token theo phiên; `CsrfTokenRequestHandler` nhận submitted token qua form hoặc header phù hợp. Đây không phải một cơ chế xác thực mới: **cookie session xác định phiên**, còn **token CSRF kiểm tra request thay đổi trạng thái**.

Form mẫu:

~~~html
<form action="/web/profile" method="post">
  <label for="displayName">Tên hiển thị</label>
  <input id="displayName" name="displayName" required>
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Lưu</button>
</form>
~~~

Token được render từ Spring Security; không dùng session ID làm CSRF token, không hardcode token trong template. Trong một số tích hợp Thymeleaf, `th:action` có thể tự bổ sung hidden CSRF field; cần xem HTML cuối để tránh nhân đôi.

### 10.2. Chỉ miễn CSRF cho API đã chứng minh Bearer-only

Nếu kiến trúc có **hai nhóm độc lập**:

- `/api/**` **chỉ** nhận Bearer access token trong header `Authorization` do client chủ động gắn; không chấp nhận session, cookie JWT, HTTP Basic hoặc proxy-cookie SSO;
- Các route web còn lại dùng cookie session và form login;

thì có thể dùng **hai `SecurityFilterChain` có thứ tự rõ ràng**, ví dụ dưới đây.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SplitServletSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            // CHỈ sau khi kiểm chứng toàn bộ /api/** là bearer-only.
            .csrf(csrf -> csrf.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserWeb(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**", "/login").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Đọc cấu hình cho đúng:**

- Đây là **cấu hình thay thế** ví dụ một chain ở mục 10.1; không bật đồng thời hai class ví dụ trong một ứng dụng.
- Cần dependency Resource Server và cấu hình JWT decoder/issuer/JWK phù hợp; đoạn mã không tự tạo Identity Provider.
- `SessionCreationPolicy.STATELESS` **không tự chứng minh** các custom filter, gateway hoặc đường xác thực phụ không nhận cookie. Phải kiểm tra toàn bộ luồng auth.
- Nếu `/api/auth/refresh`, `/api/logout` hoặc một BFF endpoint **dùng cookie**, không được để chúng vô tình nằm trong vùng `.csrf(...disable())` chung. Cần thiết kế chain/matcher khác hoặc giữ CSRF thích hợp cho những route đó.
- `@Order` và `securityMatcher` quyết định filter chain nào nhận request; kiểm thử các URL dễ bị chồng lấn.
- Không lấy `csrf.disable()` từ ví dụ bearer-only rồi áp lên toàn bộ web.

### 10.3. Khi backend nhận JWT từ cookie

Nếu một authentication filter tự đọc `Cookie: ACCESS_TOKEN=...` rồi xác minh JWT, nó đã tạo một **đường xác thực do browser tự gửi**. Dù JWT có chữ ký và server không dùng `HttpSession`, không được áp kết luận bearer-only ở trên.

Khi cần token cho SPA gửi JSON, có thể dùng synchronizer token, cookie token repository hoặc cơ chế khác phù hợp với mô hình đe dọa. Với `CookieCsrfTokenRepository` và SPA, phải chú ý `X-XSRF-TOKEN`, cookie scope, XOR masking/raw token và khả năng cookie injection; một repository cookie thường **không tự triển khai signed double-submit HMAC ràng buộc phiên**.

## 11. Spring Security Reactive/WebFlux: cùng một tiêu chí rủi ro

### 11.1. WebSession là một credential tự gửi ở phía browser

Ứng dụng Reactive có thể lưu thông tin phiên trong `WebSession`; browser giữ session cookie phù hợp resolver. Cookie đó vẫn là **ambient credential**.

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
class WebFluxSessionSecurityConfig {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/assets/**", "/login").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
~~~

`CsrfWebFilter` kiểm tra submitted token cho unsafe request theo cấu hình. API reactive hay MVC đều chịu cùng quy tắc browser cookie; **đổi sang Mono/Flux không thay mô hình CSRF**.

### 11.2. Một API reactive Bearer-only có thể có security chain riêng

Với cùng những điều kiện bearer-only nghiêm ngặt ở Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
class SplitWebFluxSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            // Chỉ đúng nếu tất cả route được bảo vệ là bearer-only.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browserWeb(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/assets/**", "/login").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Không dùng đồng thời** cấu hình ví dụ ở mục 11.1 và cấu hình hai chain này trong một ứng dụng mà không thiết kế rõ việc kết hợp. Cần JWT decoder/issuer và chính sách token thực; quan trọng nhất là chứng minh cookie-only request **không được chấp nhận** bởi `/api/**`.

Nếu một gateway hoặc BFF nhận cookie rồi gắn Bearer xuống API, phải bảo vệ **điểm vào nhận cookie**. Backend Bearer-only không xóa rủi ro phía browser.

## 12. Những lớp bảo vệ bổ sung, không được nhầm chức năng

### 12.1. CSRF token gắn đúng ngữ cảnh

Các mẫu phổ biến:

- **Synchronizer token:** Server tạo token khó đoán, lưu theo `HttpSession`/`WebSession`; form/header gửi token để đối chiếu với expected của đúng phiên.
- **Double-submit cookie:** Client đọc token từ cookie CSRF rồi gửi bản sao qua header/form. Cần xem cookie injection và cookie scope; biến thể mạnh có chữ ký **HMAC ràng buộc phiên**.
- **Token masked/XOR:** Biểu diễn token trong HTML có thể được che để giảm một số kênh rò rỉ như BREACH. Masking **không phải HMAC signature** và không thay CSRF repository.

Cookie xác thực `HttpOnly` và cookie CSRF mà SPA cần đọc có thể có chính sách JavaScript-access khác nhau. Không làm cookie xác thực đọc được chỉ vì muốn JS lấy CSRF token.

### 12.2. Origin, Referer và Fetch Metadata

Có thể kết hợp thêm các kiểm tra như:

- `Origin`: Nhận diện origin nguồn trên những request có header này.
- `Referer`: Có thể cung cấp ngữ cảnh nguồn nhưng chịu ảnh hưởng của referrer policy/browser và các tình huống thiếu header.
- `Sec-Fetch-Site`: Một header Fetch Metadata thường có các giá trị `same-origin`, `same-site`, `cross-site`, `none`; có thể dùng để loại bớt request cross-site không mong muốn.

Những kiểm tra này cần **chính sách rõ ràng cho header thiếu**, bảo vệ các origin tin cậy cụ thể, và xử lý ngoại lệ chính đáng như OAuth callback, webhook hoặc client không phải browser. Same-site **không tự đáng tin**, vì một subdomain khác origin có thể ít được bảo vệ.

Đừng dùng Fetch Metadata như lời hứa bảo vệ tuyệt đối thay CSRF token; nó không ngăn XSS cùng origin và còn phụ thuộc browser support.

### 12.3. CORS không thay CSRF

CORS kiểm soát việc JavaScript khác origin được đọc response và một số request có preflight. Nó **không nhất thiết chặn việc form HTML cross-site gửi POST** có tác động đến server.

Nếu API sử dụng cookie, một `POST` không có token vẫn phải bị server từ chối ngay cả khi website ngoài không được đọc response. Với CORS credentialed response, không dùng wildcard `Access-Control-Allow-Origin: *` để cấp quyền tùy tiện.

### 12.4. SameSite, CSP, HSTS và HTTP firewall

| Cơ chế | Đóng góp | Giới hạn |
|---|---|---|
| `SameSite` | Giảm gửi cookie cross-site trong nhiều tình huống | Same-site khác origin, GET và ngoại lệ browser |
| `HttpOnly` | Giảm nguy cơ JS đọc cookie | Browser vẫn có thể gửi cookie; XSS cùng origin vẫn gọi API |
| `Secure` và HSTS | Hỗ trợ kết nối an toàn và giảm hạ cấp HTTP | Không chứng minh POST do UI hợp lệ tạo |
| CSP/chống XSS | Giảm nguy cơ script không tin cậy thực thi trong origin | Không tự thay kiểm tra CSRF từ origin ngoài |
| HTTP firewall | Giúp chuẩn hóa/chặn những request hoặc URL bất thường theo chính sách | Không xác nhận một request có token CSRF hợp lệ |
| Authentication/authorization | Xác định danh tính, scope và quyền nghiệp vụ | Không tự phân biệt request từ UI hợp lệ khi credential tự gửi |
| CSRF token | Kiểm tra bằng chứng theo phiên/ngữ cảnh server tin cậy | Không thay XSS defense, xác thực, phân quyền |

Các lớp phải được kiểm thử theo **mục tiêu riêng**, không suy đoán lớp này bù cho mọi lỗi của lớp khác.

## 13. Ma trận kiểm thử rủi ro theo credential

| Ca thử | Credential | CSRF token | Kỳ vọng theo mô hình đã nêu |
|---|---|---|---|
| Web POST có session cookie | Cookie phiên hợp lệ | Thiếu | Bị CSRF filter từ chối |
| Web POST có session cookie | Cookie phiên hợp lệ | Đúng | Qua bước CSRF, vẫn phải đủ quyền |
| Web POST có session cookie | Cookie phiên hợp lệ | Sai hoặc của phiên khác | Bị từ chối |
| POST từ subdomain same-site | Browser có thể gửi cookie | Thiếu | Bị từ chối bởi CSRF |
| API Bearer-only POST | Bearer header hợp lệ | Không có | Chỉ hợp lệ nếu policy miễn CSRF đã được chứng minh cho route |
| API được tuyên bố Bearer-only | **Chỉ có session cookie** | Không có | **Không được xác thực bằng cookie** |
| Refresh endpoint có cookie | Refresh cookie tự gửi | Thiếu | Phải theo chính sách chống giả mạo riêng được thiết kế |
| POST login từ trang ngoài | Có thể chưa có credential phiên | Thiếu | Không được tạo session ngoài ý muốn |
| GET chỉ đọc | Có hoặc không có cookie | Không có | Không có side effect nghiệp vụ |
| GET trực tiếp xóa hoặc logout | Cookie có thể gửi với Lax | Không có | Lỗi thiết kế cần sửa |
| API hỗn hợp Bearer/cookie | Cookie fallback | Thiếu | Không được cho thao tác ghi đi qua nếu bỏ token |
| API Basic browser-managed | Credential có thể tự gửi | Thiếu | Đánh giá và kiểm tra chống giả mạo theo ambient credential |

**Phạm vi kiểm thử:** Đừng chỉ kiểm tra status code. Với thao tác có tác động, xác minh **dữ liệu có thay đổi không**, security context nào được sử dụng, phiên đã bị thay hay chưa, token của phiên khác có được chấp nhận không.

## 14. MockMvc: kiểm chứng lớp CSRF ở ứng dụng Servlet

Giả định ứng dụng đã có route `POST /web/profile` trả `204 No Content` khi hợp lệ và security filter chain hoạt động. Với `spring-security-test`:

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
class CredentialTransportServletTests {

    @Autowired MockMvc mvc;

    @Test
    void missingTokenRejectedForWebPost() throws Exception {
        mvc.perform(post("/web/profile")
                .with(user("alice"))
                .param("displayName", "Alice"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenRejectedForWebPost() throws Exception {
        mvc.perform(post("/web/profile")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("displayName", "Alice"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validTokenPassesCsrfLayer() throws Exception {
        mvc.perform(post("/web/profile")
                .with(user("alice"))
                .with(csrf())
                .param("displayName", "Alice"))
            .andExpect(status().isNoContent());
    }
}
~~~

**Giới hạn:** `with(user("alice"))` mô phỏng authentication; `with(csrf())` tạo token hợp lệ cho test. Những helper này **không chứng minh** browser thực sự gửi cookie/CSRF token như thế nào, hoặc route Bearer-only đã từ chối cookie auth fallback.

Bài test bổ sung bắt buộc cho `/api/**` Bearer-only:

1. Đăng nhập vào web **thật** để lấy session cookie.
2. POST tới API chỉ với cookie phiên, **không có Authorization header**.
3. Xác nhận API **không thực hiện thao tác dưới phiên web** (status có thể phụ thuộc entry point, nhưng không được thành công).
4. Gửi token JWT Bearer thật với issuer/audience/scope hợp lệ, kiểm tra đường được chấp nhận và chính sách quyền.
5. Thử Bearer hết hạn, sai audience, thiếu scope và request chỉ có cookie.
6. Thêm test đường refresh/login/logout/cookie-based API để bảo đảm không bị matcher bearer-only vô tình miễn CSRF.

`with(jwt())` có thể hữu ích để mock principal trong Spring Security Test, nhưng **không thay kiểm thử HTTP thật** về cách token được giải mã và backend có nhận cookie fallback không.

## 15. WebTestClient: kiểm chứng lớp CSRF ở Reactive/WebFlux

Với `spring-security-test` và một endpoint WebFlux `POST /web/profile` trả `204`:

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
class CredentialTransportReactiveTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void webPostWithoutTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/web/profile")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void webPostWithTokenPassesCsrfLayer() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/web/profile")
            .exchange()
            .expectStatus().isNoContent();
    }
}
~~~

Ví dụ giả định route được triển khai phù hợp (không yêu cầu body, hoặc test đã cung cấp body) và user có quyền. Đây là test **server CSRF web filter**, không phải browser simulation.

Nếu WebFlux cũng có Bearer-only API, cần **E2E test đường cookie-only** giống Servlet. `mockUser()` hay `mockJwt()` có thể mô phỏng trạng thái auth, không chứng minh token/cookie thật được xử lý đúng ở mạng.

## 16. Kiểm thử trong trình duyệt và chẩn đoán xung đột

### 16.1. Quy trình quan sát trình duyệt

Trong môi trường thử nghiệm được phép:

1. **Ghi nhận Set-Cookie** khi login: cookie name, `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`.
2. **Quan sát request thật của SPA:** Có header `Authorization` không? Có cookie phiên được gửi cùng request dù SPA không cần không?
3. **Tạo request từ origin khác cùng site:** Ví dụ `https://blog.example.test` → `https://app.example.test`. Kiểm tra browser có gửi cookie và server có từ chối POST thiếu token không.
4. **Tạo request từ origin khác site:** Ví dụ `https://attacker.other.test`. Quan sát top-level GET, form POST và policy cookie; không suy diễn từ một browser duy nhất.
5. **Thử API Bearer-only không có Bearer:** Chỉ dùng cookie session có thật và xác nhận backend không fallback.
6. **Kiểm tra refresh/login/logout:** Bỏ token/Origin phù hợp, thử rotation, phiên cũ và truy cập sau logout.
7. **Thử token sai phiên:** Token A với cookie phiên B phải bị từ chối khi thiết kế dùng token theo phiên.
8. **Phân biệt browser block với server block:** CORS preflight không qua, cookie bị SameSite loại, CSRF `403` và thiếu quyền đều là các tầng khác nhau.

Các hostname trên chỉ là mô hình: cần cấu hình DNS/hosts và chứng chỉ HTTPS cho môi trường thử nghiệm. cURL/Postman có thể tự viết header `Cookie` theo ý mình, **không tái hiện thuật toán SameSite của browser**.

### 16.2. Bảng chẩn đoán

| Hiện tượng | Không nên kết luận vội | Cách xác minh |
|---|---|---|
| API dùng JWT và `403` | “JWT không cần CSRF” | Token qua cookie hay Bearer? Chain nào kiểm tra CSRF? |
| SPA `401` khi gọi API khác origin | “CSRF filter chặn” | Browser có gửi cookie? `credentials`, SameSite và CORS? |
| POST có cookie nhưng `403` | “Thiếu phân quyền” | Kiểm tra submitted CSRF token, repository, phiên và authorization |
| CORS preflight lỗi | “Server CSRF tốt” | POST có đến server không? Form đơn giản có đường khác không? |
| Cookie `HttpOnly` không hiện trong JS | “Browser không có cookie” | Kiểm tra HTTP Cookie header trong Network |
| `SameSite=Strict` vẫn gửi cookie từ subdomain | “Browser lỗi” | Hai origin có thể **same-site** |
| `csrf()` test pass | “Không tồn tại đường cookie fallback” | Test request thật không Bearer, chỉ cookie |
| API `SessionCreationPolicy.STATELESS` | “Không thể CSRF” | Custom cookie auth, gateway hoặc JWT-cookie có tồn tại không? |
| API hậu login POST đầu tiên `403` | “Phải tắt CSRF” | Token cũ bị xóa/rotate; SPA đã nhận token mới chưa? |
| Cookie refresh bị chặn cross-site | “Token hỏng” | SameSite, third-party cookie policy, HTTPS và Origin/CORS |
| GET thực hiện thay đổi trạng thái | “Lax đã chặn site ngoài” | Chuyển GET sang phương thức ghi, test link/navigation |
| JWT Bearer đúng nhưng vẫn bị từ chối | “CSRF gây mọi lỗi 403” | Scope, audience, role, policy resource và CSRF chain |

Không log đầy đủ session ID, access token hay CSRF token trong quá trình gỡ lỗi; chỉ ghi nhận có/không credential, đường xác thực, chain, phương thức, endpoint và loại lỗi thích hợp.

## 17. Quyết định miễn CSRF có điều kiện

Trước khi miễn CSRF cho một API, cần có bằng chứng:

- **Danh sách route cụ thể** được xem là Bearer-only, không dùng wildcard vượt cả login/logout/refresh/BFF.
- Backend chỉ xác thực bằng credential **không tự được browser gắn** vào request do site ngoài kích hoạt.
- Không có session cookie, JWT cookie, HTTP Basic cache, client certificate auto-auth hoặc gateway SSO cookie fallback được chấp nhận trên route đó.
- Test **cookie-only** request không thể thực hiện thao tác, kể cả khi browser đã có session hợp lệ.
- Test token Bearer thật được kiểm chứng về issuer, audience, thời hạn, scope/quyền và thu hồi nếu cần.
- CORS, XSS/CSP, token storage và log sanitization vẫn được kiểm soát.
- Có tiêu chí **đánh giá lại khi kiến trúc thay đổi**, nhất là khi thêm refresh cookie, đổi cách lưu token hoặc thêm SSO/gateway.

Nếu không chắc tất cả điều kiện trên đúng, **không dùng một câu “API của chúng ta stateless nên disable CSRF” làm quyết định cuối cùng**.

## 18. Tình huống tự đánh giá

**Tình huống A — JWT ở cookie HttpOnly.** API xác minh JWT cookie và không dùng session store. Có cần đánh giá CSRF?

**Đáp án:** Có. Browser có thể tự gửi cookie JWT, nên stateless và chữ ký JWT không loại nguy cơ CSRF.

**Tình huống B — Access token ở localStorage.** SPA thêm Bearer header; API chỉ chấp nhận Bearer. Có thể xem đây là cookie CSRF truyền thống không?

**Đáp án:** Thường không, nếu thật sự không có đường ambient credential. Nhưng token trong localStorage dễ chịu rủi ro XSS/đánh cắp; vẫn cần phòng vệ khác.

**Tình huống C — BFF lưu OAuth access token server-side.** Browser dùng cookie phiên BFF. Ranh giới nào cần bảo vệ CSRF?

**Đáp án:** Browser → BFF. API Bearer-only phía sau không thay vấn đề BFF nhận cookie được browser tự gửi.

**Tình huống D — Refresh token cookie.** API nghiệp vụ chỉ nhận Bearer header, nhưng `POST /auth/refresh` dùng HttpOnly cookie.

**Đáp án:** Đánh giá riêng endpoint refresh với mô hình CSRF/Origin/Fetch Metadata và token rotation. Không miễn toàn bộ vì các API nghiệp vụ dùng Bearer.

**Tình huống E — API vừa Bearer vừa cookie.** Frontend luôn gửi Bearer, còn backend chấp nhận cookie nếu header thiếu.

**Đáp án:** Vẫn có đường CSRF cookie fallback; phải loại bỏ đường fallback hoặc bảo vệ nó phù hợp.

**Tình huống F — Cookie Strict giữa hai subdomain.** Form từ subdomain bị chiếm quyền gửi POST tới app cùng site. Có chắc cookie bị chặn không?

**Đáp án:** Không. Same-site không đồng nghĩa same-origin; cookie có thể được gửi, nhưng SOP thường vẫn ngăn đọc CSRF token của origin đích.

**Tình huống G — HTTP Basic.** Browser ghi nhớ Basic authentication và tự gửi trong request tới server. Có thể coi mọi Authorization header là do SPA chủ động tạo không?

**Đáp án:** Không. Browser-managed Basic là một dạng credential có thể tự gửi; cần đánh giá CSRF tương ứng.

**Tình huống H — GET đổi mật khẩu hoặc logout.** Cookie Lax thường không gửi cross-site POST. Đường GET có an toàn vì vậy không?

**Đáp án:** Không. Top-level GET cross-site vẫn có thể mang cookie Lax; GET phải chỉ đọc, còn thao tác có tác động dùng phương thức phù hợp và CSRF token.

## Kết luận

**Nguy cơ CSRF phụ thuộc vào cách credential được gửi và được server chấp nhận, không phụ thuộc vào tên token hay framework.** Session ID trong cookie, JWT trong cookie, refresh token cookie, HTTP auth tự gửi hoặc session cookie của BFF đều có thể tạo đường tấn công khi browser mang credential cho request không được khởi tạo từ luồng tin cậy. Bearer access token **chỉ** được client chủ động gắn có mô hình khác, nhưng điều đó phải được kiểm chứng **trên từng endpoint và mọi authentication fallback**.

Với **Spring Security Servlet** (`CsrfFilter`, `SecurityFilterChain`, `HttpSession`) và **Reactive/WebFlux** (`CsrfWebFilter`, `SecurityWebFilterChain`, `WebSession`), giữ CSRF cho đường browser dùng credential tự gửi; chỉ miễn theo phạm vi Bearer-only đã chứng minh bằng test thực tế. SameSite, CORS, CSP, HSTS, HTTP firewall, session security và token storage tạo thêm các lớp bảo vệ nhưng không thay bước đánh giá riêng từng luồng.

Khi lập được bản đồ **nơi lưu → HTTP request → credential được chấp nhận → tác động nghiệp vụ → chính sách CSRF**, nhóm phát triển có thể giải thích một endpoint cần CSRF token vì sao, điều kiện nào cho phép một ngoại lệ và kiểm thử nào chứng minh quyết định ấy vẫn đúng.

## Tài liệu tham khảo

- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): mô hình tấn công, synchronizer token, double-submit token và các biện pháp bổ trợ.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): quan hệ với XSS và ranh giới script cùng origin.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): `SameSite`, `Secure`, `HttpOnly` và phạm vi cookie.
- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): bộ lọc CSRF, token repository, request handler.
- [Spring Security — CSRF Protection (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): xử lý CSRF trong Reactive stack.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): định nghĩa safe methods và idempotency.
