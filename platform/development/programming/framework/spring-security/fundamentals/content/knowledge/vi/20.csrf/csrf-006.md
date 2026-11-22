# Token CSRF khác với cookie phiên và access token

## 1. Mục tiêu và phạm vi

Bài học thuộc **CSRF** trong **Spring Security - fundamentals**. Ba giá trị có thể cùng xuất hiện trong ứng dụng web nhưng có **mục đích, vị trí lưu trữ và cơ chế kiểm tra hoàn toàn khác nhau**:

- **CSRF token:** một giá trị chống giả mạo yêu cầu; trình duyệt phải chủ động gửi nó qua tham số form hoặc header do ứng dụng kiểm soát, còn server kiểm tra nó so với giá trị được trông đợi.
- **Session cookie (thường là `JSESSIONID`):** trình duyệt tự gửi một định danh phiên để server tìm lại `HttpSession` và trạng thái xác thực.
- **Access token (thường là Bearer/OAuth2 token):** credential giúp resource server xác thực hoặc xác minh quyền truy cập API theo issuer, scope, audience và thời hạn.

Sau bài học, bạn có thể:

1. Nêu rõ vì sao **CSRF token không phải cookie đăng nhập**, và vì sao **access token không phải CSRF token**.
2. Mô tả cách một yêu cầu giả mạo có thể mang session cookie hợp lệ nhưng thiếu CSRF token phù hợp.
3. Hiểu cơ chế `CsrfFilter`, `CsrfTokenRepository`, `HttpSessionCsrfTokenRepository` và `CookieCsrfTokenRepository` của Spring Security Servlet.
4. Phân biệt trường hợp token gửi qua **hidden form field**, **request header** hoặc chỉ **cookie**, và giải thích tại sao chỉ gửi cookie không đủ để chống CSRF.
5. Nhận biết hành vi Spring Security 6: **deferred CSRF token**, giá trị biểu diễn có **BREACH protection** và yêu cầu làm mới token sau đăng nhập/đăng xuất.
6. Lựa chọn chính sách CSRF cho ứng dụng session-based, SPA và bearer-token API theo cách browser thực sự gửi credentials.
7. Chạy ví dụ Java 17+/Spring Boot 3.5.x với login session, `GET /csrf`, POST thay đổi trạng thái, rồi dùng `MockMvc` xác minh tình huống thiếu/sai/đúng CSRF token.
8. Phát hiện các lỗi phổ biến: tắt CSRF trên ứng dụng cookie login, đặt token vào URL, dùng `SameSite`/CORS làm biện pháp duy nhất, nhầm mã lỗi 401 và 403, hoặc coi CSRF token là bằng chứng danh tính.

**Phạm vi thực hành:** Spring MVC/Servlet với `HttpSecurity`, `SecurityFilterChain` và form login. Spring WebFlux dùng `ServerHttpSecurity` cùng các thành phần reactive tương ứng; không trộn API Servlet và WebFlux trong cùng ví dụ.

## 2. Ba “token” trả lời ba câu hỏi khác nhau

| Giá trị | Câu hỏi mà server cần trả lời | Được tạo/kiểm tra điển hình |
| --- | --- | --- |
| **CSRF token** | “Yêu cầu thay đổi trạng thái có mang bằng chứng chống giả mạo phù hợp với ngữ cảnh của ứng dụng không?” | `CsrfTokenRepository` + `CsrfFilter` |
| **Session cookie** | “Cookie này trỏ tới phiên server nào, và phiên đó đã đăng nhập với danh tính nào?” | Servlet container, `HttpSession`, `SecurityContextRepository` |
| **Access token** | “Credential này được issuer tin cậy cấp cho ai/client nào, quyền nào, resource nào và còn hợp lệ không?” | OAuth2 Resource Server / JWT decoder / opaque introspection |

Hình dung một ứng dụng ngân hàng dùng form login:

```text
Browser của Alice                     Server
  Cookie: JSESSIONID=xyz       ────> Tìm session xyz, khôi phục Authentication=Alice
  X-CSRF-TOKEN: abc...         ────> So sánh CSRF token với giá trị được trông đợi
  POST /transfer               ────> Kiểm tra cả authorization + nghiệp vụ
```

Ở đây **cả hai điều kiện đều cần**:

- Có session đăng nhập hợp lệ **không có nghĩa** POST được phép nếu thiếu CSRF token.
- Có CSRF token hợp lệ **không có nghĩa** người gọi đã đăng nhập hoặc được phép chuyển tiền.
- Bước tiếp theo vẫn phải kiểm tra số dư, owner tài khoản, hạn mức, tenant, người thụ hưởng và các quy tắc nghiệp vụ.

Với API OAuth2:

```text
Client ─── Authorization: Bearer ACCESS_TOKEN ───> Resource Server
       │                                           │
       │                                  Kiểm tra token/issuer/
       │                                  scope/audience/expiration
       │                                           │
       └────────────── 200 / 401 / 403 <──────────┘
```

Một access token được trình duyệt **chủ động** gắn vào header bằng JavaScript không có cùng tính chất “tự động gửi” như session cookie. Tuy vậy, **nếu access token được lưu trong cookie và browser tự gửi**, hệ thống vẫn có thể cần chống CSRF. Định dạng JWT hay opaque không tự quyết định có CSRF hay không.

## 3. CSRF là một cuộc tấn công vào hành vi tự gửi credentials

**Cross-Site Request Forgery (CSRF)** xảy ra khi một site độc hại khiến trình duyệt của nạn nhân gửi request thay đổi trạng thái đến site đích, trong khi trình duyệt **tự gửi credentials** đã có cho site đích (theo quy tắc cookie/browser). Server có thể nhìn thấy một session hợp lệ nhưng request đó **không do giao diện hợp lệ của ứng dụng chủ động tạo**.

Ví dụ tình huống:

1. Alice đang đăng nhập vào `https://bank.example.test`; browser giữ cookie phiên hợp lệ.
2. Alice mở một site không tin cậy. Site này tạo một form HTML và tìm cách gửi `POST` tới một endpoint thay đổi thông tin ở ngân hàng.
3. Tùy cookie `SameSite`, browser context, top-level navigation và các biện pháp khác, request có thể mang session cookie ngân hàng dù form đến từ site khác.
4. Nếu backend chỉ kiểm tra session đã đăng nhập mà không có biện pháp CSRF phù hợp, thao tác có thể được thực hiện dưới danh tính Alice.
5. Nếu backend yêu cầu CSRF token nằm trong request header/form field mà site độc hại không thể đọc/suy ra, request giả mạo bị từ chối.

**SOP/CORS không đủ một mình.** Same-Origin Policy thường chặn site khác **đọc response**. Nó không đồng nghĩa mọi cross-origin request đều bị ngăn **gửi**; HTML form có thể tạo request mà không cần đọc kết quả. CORS quyết định những quyền cross-origin liên quan nhưng không thay token CSRF hoặc các biện pháp tương đương. Việc browser có gửi cookie phụ thuộc `SameSite`, third-party cookie settings, loại request và tình huống cụ thể; đừng mặc định mọi cross-site POST đều mang cookie.

### Ví dụ về request giả mạo

```http
POST /account/email HTTP/1.1
Host: bank.example.test
Cookie: JSESSIONID=SESSION_ID

email=attacker%40example.test
```

Đây chỉ là **mô phỏng HTTP**, không phải lệnh thực thi. Nó cho thấy session cookie có thể xác định người dùng nhưng request thiếu tham số/header CSRF. Một ứng dụng bảo vệ tốt sẽ chặn trước khi cập nhật email. Ví dụ không chứng minh một browser cụ thể chắc chắn gửi cookie trong mọi cấu hình SameSite.

## 4. Token CSRF là gì và vì sao phải gửi “chủ động”?

Trong **synchronizer token pattern**, server tạo token khó đoán, liên hệ với ngữ cảnh phiên và lưu giá trị được trông đợi phía server (điển hình trong session). Một trang hoặc client hợp lệ được phép nhận token qua phản hồi từ ứng dụng và đặt token đó vào phần request **không do browser tự chèn**:

- Hidden input `_csrf` của HTML form.
- Header `X-CSRF-TOKEN` hoặc header được cấu hình tương đương khi JavaScript gọi API.
- Một cơ chế tương đương được thiết kế cẩn thận theo chính sách server.

Request hợp lệ minh họa:

```http
POST /account/email HTTP/1.1
Host: bank.example.test
Cookie: JSESSIONID=SESSION_ID
Content-Type: application/x-www-form-urlencoded

email=alice%40example.test&_csrf=UNPREDICTABLE_TOKEN
```

**Điểm quyết định:** site ngoài không được biết token hợp lệ của phiên và không thể đơn giản làm browser tự thêm đúng `_csrf`/`X-CSRF-TOKEN`. Server so sánh giá trị do client chủ động gửi với giá trị kỳ vọng; nếu thiếu/sai, request bị chặn.

**Nếu chỉ gửi token trong cookie thì chưa đủ.** Browser vốn tự thêm cookie; nếu “chống CSRF” chỉ kiểm tra có cookie nào đó, site độc hại cũng có thể lợi dụng cookie tự gửi. Ngay cả ở mô hình double-submit-cookie, client phải **đọc/nhận một giá trị token rồi chủ động gửi thêm ở header hoặc form field**, và server kiểm tra sự ràng buộc giữa các giá trị. Không thể thay cách này bằng “có cookie XSRF-TOKEN thì cho qua”.

### Token phải bí mật tới mức nào?

CSRF token cần khó đoán và không bị site ngoài lấy được. Không đặt vào URL query vì URL có thể đi vào lịch sử, proxy logs, analytics, `Referer` hoặc ảnh chụp màn hình. Không log token đầy đủ. Nếu ứng dụng có XSS cùng origin, script độc hại có thể đọc hoặc sử dụng CSRF token theo context; do đó **CSRF protection không thay thế chống XSS**.

CSRF token **không phải one-time password mặc định**: token theo session có thể được dùng lại cho nhiều POST cho đến khi bị rotate/invalidated theo policy. Nó không phải idempotency key, không chống replay bởi một actor đã kiểm soát session, và không chứng minh một giao dịch cụ thể được người dùng đồng ý.

## 5. Session cookie khác CSRF token ở đâu?

Với form login Spring Security điển hình, server lưu `SecurityContext` trong `HttpSession` để tái sử dụng qua nhiều HTTP requests. Browser chỉ cầm định danh `JSESSIONID`:

```text
Browser                              Server
┌──────────────────────────┐        ┌──────────────────────────────┐
│ Cookie JSESSIONID=xyz    │───────>│ Session xyz                  │
│                          │        │  ├─ SecurityContext          │
│ Hidden/header CSRF token │───────>│  │  └─ Authentication=Alice   │
│ từ trang/ứng dụng hợp lệ  │        │  └─ CSRF expected token       │
└──────────────────────────┘        └──────────────────────────────┘
```

| Thuộc tính | Session cookie `JSESSIONID` | CSRF token |
| --- | --- | --- |
| Mục đích | Chỉ ra phiên cần tra cứu | Chứng minh request có token chống giả mạo được mong đợi |
| Ai gửi? | Browser **tự gửi** theo cookie scope | App phải chủ động đặt ở form field/header |
| Ai tạo? | Container/session manager | `CsrfTokenRepository` |
| Giá trị có chứa user/role? | Thường chỉ là ID mờ | Không nên chứa danh tính/secret nghiệp vụ |
| Server kiểm tra gì? | Session còn hợp lệ, security context/Authentication | Token được cung cấp có đúng token kỳ vọng của context không |
| Có đủ để truy cập API? | Chỉ đủ cho authentication khi session hợp lệ; còn authorization | Không, riêng CSRF token không xác thực người dùng |
| Có tự bảo vệ CSRF? | Không | Có ích khi kết hợp đúng với ngữ cảnh credentials tự gửi |
| Sau logout? | Session bị invalidate; cookie cleanup tùy cấu hình | Token liên quan thường bị clear/invalidated |
| Có thể có ở anonymous? | Có thể có session trước khi đăng nhập | **Có**: trang login cũng cần CSRF token |

**Khác biệt quan trọng:** một ứng dụng có thể cấp CSRF token **trước khi người dùng đăng nhập** để bảo vệ `POST /login`. Điều này chứng minh CSRF token **không tương đương quyền truy cập** và không phải bằng chứng rằng người nhận token là Alice/Bob.

### Một cookie CSRF vẫn là “cookie” nhưng không phải session cookie

Khi dùng `CookieCsrfTokenRepository`, Spring Security có thể đưa giá trị CSRF token vào cookie `XSRF-TOKEN`. Cookie này khác cookie phiên `JSESSIONID`:

- `JSESSIONID`: trỏ tới session server dùng cho login.
- `XSRF-TOKEN`: mang CSRF token theo repository đã chọn; JavaScript có thể cần đọc để gửi lại bằng `X-XSRF-TOKEN`.
- Server vẫn kiểm tra token gửi chủ động qua header/form field tương ứng, **không chỉ sự tồn tại của cookie `XSRF-TOKEN`**.
- `XSRF-TOKEN` **không** tự chứng minh Authentication hợp lệ, và không thay credential session hoặc access token.

Không nên suy luận cookie nào có chữ “token” đều dùng để đăng nhập.

## 6. Access token khác hai giá trị trên ra sao?

**Access token** do Authorization Server hoặc hệ thống xác thực được tin cậy phát hành cho quyền truy cập tài nguyên, không chỉ cho một form trong session web. Nó thường được gửi theo:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
```

Resource Server xác minh issuer/signature/expiry/audience/scopes hoặc introspect opaque token tùy cấu hình. Sau đó, nó còn kiểm tra owner/tenant/role theo chính sách endpoint.

So sánh:

| Khái niệm | Access token | CSRF token |
| --- | --- | --- |
| Cấp bởi | Authorization Server/IdP hoặc hệ thống được thiết kế tương ứng | Ứng dụng hoặc `CsrfTokenRepository` |
| Chứng minh | Quyền sử dụng API trong phạm vi token | Token chống giả mạo của request phù hợp context |
| Có thể mang claims? | JWT có claims như `sub`/`aud`/`scope`; opaque cần xác minh ngoài | Thường là giá trị khó đoán, không chứa claims về quyền |
| Được trình bày ở đâu? | `Authorization: Bearer ...` thường gặp | `_csrf` hoặc `X-CSRF-TOKEN`/`X-XSRF-TOKEN` |
| Có giá trị cho xác thực? | Có thể dùng để xác thực Bearer request | **Không** |
| Có giá trị thay cho chống CSRF? | Không tự động; phụ thuộc việc browser có tự gửi credentials | Có khi triển khai đúng mẫu chống CSRF |
| Rủi ro nếu lộ | Bị dùng như credential cho tới expiry/revocation | Kẻ tấn công có thể vượt lớp CSRF cho context tương ứng |
| Lưu ở client | Cần thiết kế cẩn trọng theo client và threat model | Có thể ở HTML/page state, session hoặc cookie tùy repository |

### JWT có thay CSRF token không?

**Không.** Một JWT access token có chữ ký hợp lệ chứng minh issuer và claims, không chứng minh request do giao diện hợp lệ chủ động tạo. Nếu JWT đặt trong cookie và tự gửi, request giả mạo vẫn có thể mang JWT cookie đó.

Ngược lại, nếu browser JavaScript đính kèm Bearer token rõ ràng trong `Authorization` header, site khác thường không thể đơn giản làm browser tự gắn Bearer token đó vào form cross-site. Khi API không dùng bất kỳ **ambient credential** nào có thể tự gửi, CSRF threat model thường khác với session-cookie. Tuy nhiên vẫn cần bảo vệ XSS, token theft, CORS, replay, scope và các hành động nhạy cảm. **Không dùng khẩu hiệu “JWT thì luôn tắt CSRF”.**

### OAuth2 access token và refresh token cũng khác

**Refresh token** dùng để xin access token mới ở Authorization Server, có chính sách lưu trữ/rotation/revoke riêng. Nó không phải CSRF token. Một browser SPA có thể có access/refresh tokens hoặc dùng BFF/session; chọn đúng biện pháp phụ thuộc cách xác thực **được truyền vào request**.

## 7. Các mẫu triển khai chống CSRF

### 7.1. Synchronizer token pattern — thường cho session-based web

1. Server lưu token kỳ vọng trong session.
2. Trang web nhận token dưới dạng thuộc tính trong HTML/form hoặc JSON/header từ endpoint phù hợp.
3. Request POST/PUT/PATCH/DELETE mang token trong `_csrf` hoặc header do ứng dụng tạo.
4. `CsrfFilter` so token được nộp với token kỳ vọng; request thiếu/sai bị 403.

Mẫu này gắn tốt với `HttpSession` và form login. Với Spring Security Servlet mặc định, `HttpSessionCsrfTokenRepository` lưu token kỳ vọng trong session.

### 7.2. CookieCsrfTokenRepository — giá trị CSRF ở cookie, client gửi lại

Cấu hình minh họa:

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
);
```

Đây là **fragment**, cần import `org.springframework.security.web.csrf.CookieCsrfTokenRepository` và nằm trong một `SecurityFilterChain` thực tế.

Với repository này, cookie thường tên `XSRF-TOKEN`, giá trị gửi lại trong header `X-XSRF-TOKEN` hoặc parameter `_csrf`.

**Lưu ý đặc biệt với Spring Security 6:** mặc định `XorCsrfTokenRequestAttributeHandler` tạo giá trị biểu diễn có random masking để chống BREACH. Một SPA đọc **raw token từ cookie** và gửi lại trong header không tự tương thích với quy trình giải mã token của handler XOR mặc định. Tài liệu Spring Security có **cấu hình SPA `CsrfTokenRequestHandler` tùy biến** để xử lý raw token từ header và masked token từ form. Không chỉ thêm `withHttpOnlyFalse()` rồi kết luận SPA đã hoạt động đúng; phải dùng cấu hình handler phù hợp và kiểm thử request thật.

`withHttpOnlyFalse()` cho phép JavaScript đọc cookie CSRF và tạo header. Điều đó **không có nghĩa** tắt HttpOnly cho cookie đăng nhập `JSESSIONID`. Đừng làm cookie phiên có thể đọc bởi script chỉ để thuận tiện cho CSRF.

### 7.3. Signed double-submit cookie

Trong một số kiến trúc không muốn lưu token CSRF ở server, client nhận một cookie CSRF được ký và **gắn với session/context** bằng HMAC, rồi gửi bản sao token qua header/form. Server xác minh cấu trúc, HMAC và sự ràng buộc context.

**Không làm bản double-submit ngây thơ** chỉ so “cookie và header bằng nhau” mà không chống cookie injection/bên thứ ba kiểm soát subdomain. OWASP khuyến nghị mẫu **signed double-submit cookie** có session binding khi chọn hướng này.

**Phân biệt:** `CookieCsrfTokenRepository` là API Spring lưu/đọc token từ cookie theo contract của framework. Nó không tự chứng minh rằng toàn bộ triển khai của bạn đáp ứng **signed double-submit HMAC gắn session** như OWASP khuyến nghị. Nếu yêu cầu chống cookie injection mạnh, thiết kế/triển khai theo threat model và kiểm toán security.

### 7.4. Kiểm tra Origin/Referer/Fetch Metadata

`Origin`, `Referer`, `Sec-Fetch-Site`, `Sec-Fetch-Mode` có thể giúp nhận diện cross-site requests và áp dụng chính sách *defense in depth*. Chúng có giới hạn về browser, proxy, redirects và trường hợp header vắng mặt; không nên thay thế mọi biện pháp CSRF chỉ với một câu lệnh.

Cookie `SameSite=Lax` hoặc `Strict` cũng giúp giảm một số request cross-site được gửi kèm cookie, nhưng **same-site không phải luôn same-origin** và subdomain vẫn có thể liên quan. CSRF token, Origin/Fetch Metadata và SameSite nên được xem là các lớp bảo vệ phối hợp.

## 8. Cơ chế Spring Security 6: CsrfFilter, repository và request handler

Đối với Servlet, các thành phần chính:

| Thành phần | Trách nhiệm |
| --- | --- |
| `CsrfFilter` | Xác định request cần CSRF protection và so token |
| `CsrfTokenRepository` | Tạo, lưu và nạp token kỳ vọng |
| `HttpSessionCsrfTokenRepository` | Lưu token kỳ vọng vào `HttpSession` (mặc định phổ biến) |
| `CookieCsrfTokenRepository` | Lưu/nạp CSRF token qua cookie |
| `CsrfTokenRequestHandler` | Làm token có thể truy cập trong request và giải quyết giá trị thực client gửi |
| `XorCsrfTokenRequestAttributeHandler` | Handler mặc định Spring Security 6 với random masking chống BREACH |
| `CsrfAuthenticationStrategy` | Clear token cũ khi xác thực thành công trong luồng liên quan |
| `CsrfLogoutHandler` | Clear token cũ khi logout |
| `AccessDeniedHandler` | Xử lý thiếu/sai token thường thành 403 |

Lược đồ:

```text
HTTP POST /api/counter
   ├─ Browser tự gửi Cookie JSESSIONID=...
   ├─ Browser/app chủ động gửi _csrf hoặc X-CSRF-TOKEN
   │
   ▼
CsrfFilter
   ├─ Xem method có cần CSRF?
   │     ├─ GET/HEAD/OPTIONS/TRACE thường không
   │     └─ POST/PUT/PATCH/DELETE thường có
   │
   ├─ Lấy CsrfToken kỳ vọng từ CsrfTokenRepository
   ├─ Đọc token người gọi nộp bằng CsrfTokenRequestHandler
   ├─ So sánh
   │     ├─ Thiếu/sai → 403, không gọi endpoint thay đổi trạng thái
   │     └─ Hợp lệ → cho filter chain tiếp tục
   │
   ▼
Authentication / Authorization / Controller / Service
   ├─ Anonymous/không đủ quyền → chặn tiếp
   └─ Đủ quyền → xử lý nghiệp vụ
```

Thứ tự filter thực tế có thể có nhiều filter/điểm xử lý khác. Sơ đồ minh họa **hai điều kiện độc lập**, không phải lời khẳng định CSRF luôn xảy ra ngay trước mọi authentication trong tất cả cấu hình custom.

### 8.1. Request nào được kiểm tra?

Spring Security mặc định yêu cầu CSRF cho các HTTP methods *unsafe* (thường **POST, PUT, PATCH, DELETE**) và không yêu cầu cho **GET, HEAD, OPTIONS, TRACE**. Vì vậy, **GET không được thay đổi dữ liệu hoặc tạo side effect nhạy cảm**. Nếu bạn viết endpoint `GET /delete-account` để xóa tài khoản, CSRF filter mặc định có thể không bảo vệ vì method GET được xem là safe.

Cũng không nên tự viết cấu hình `csrf(csrf -> csrf.disable())` cho toàn ứng dụng vì một endpoint JSON “trông như API”. Nếu vẫn dùng session cookie/refresh cookie cho browser, có thể tồn tại CSRF.

### 8.2. Deferred token trong Spring Security 6

Spring Security 6 trì hoãn nạp CSRF token khi chưa cần thiết, tránh buộc session được tải cho mọi GET đơn giản. Khi một trang cần render token hoặc một unsafe request cần xác minh, token được load/materialize.

Hệ quả:

- Không giả định mọi GET `/public` tạo session hoặc cookie CSRF.
- Một endpoint `GET /csrf` có thể được chủ động gọi khi frontend cần lấy token.
- Khi token được render trong HTML form hoặc JSON, hệ thống có thể tạo/lưu token theo repository.

### 8.3. BREACH protection: token thấy ở HTML có thể đổi dù session không đổi

`XorCsrfTokenRequestAttributeHandler` có thể biểu diễn token dưới dạng **masked/encoded với randomness mỗi request**. Do đó token nhìn thấy trong hidden field có thể thay đổi giữa các lần render, trong khi token kỳ vọng nội bộ vẫn được lưu trong session.

**Đừng kiểm thử bằng cách buộc chuỗi `_csrf` ở hai trang phải giống hệt nhau.** Điều cần kiểm tra là token được lấy từ response hợp lệ có được server chấp nhận khi gửi lại đúng cách.

Với SPA dùng cookie token dạng raw, cần handler đúng cách (mục 7.2). Đây là một bẫy migration từ Spring Security 5 sang 6.

### 8.4. Khi login hoặc logout, cần token mới

Sau authentication thành công, `CsrfAuthenticationStrategy` clear token cũ trong những flow tương ứng. `CsrfLogoutHandler` cũng clear token khi logout. Frontend không nên giữ mã token cũ trong memory rồi tiếp tục POST mà không làm mới.

Nếu ứng dụng có endpoint `GET /csrf`, client có thể gọi lại **sau login** và **sau logout** để lấy token mới. Với form login server-rendered, trang mới thường cung cấp token theo context hiện hành. Nếu SPA nhìn thấy 403 CSRF sau login, kiểm tra vòng đời token trước khi “sửa” bằng cách tắt CSRF.

### 8.5. CSRF bị chặn thường là 403

Khi token thiếu hoặc sai, `CsrfFilter` gây `AccessDeniedException` được xử lý qua `AccessDeniedHandler` (mặc định thường là **403 Forbidden**). Đây không phải lỗi “mật khẩu sai” hay “thiếu role” nhất thiết. Cần phân loại nguyên nhân qua logging/observability an toàn.

Nếu không có credentials nhưng đã gửi CSRF token hợp lệ, request vẫn có thể bị chuyển đến login hoặc trả 401 tùy cơ chế xác thực. **CSRF hợp lệ không cấp quyền.**

## 9. Ví dụ Java 17 runnable: cookie phiên, endpoint CSRF và POST thay đổi dữ liệu

Bài lab sử dụng **Java 17+**, **Spring Boot 3.5.12**, **Spring Security 6.x**, **Gradle 8.4+**. Một tài khoản demo đăng nhập bằng form và session cookie; API thay đổi một bộ đếm **riêng cho người dùng đó**.

- `GET /public`: không cần login.
- `GET /csrf`: cho phép client hợp lệ lấy token phục vụ form/request; endpoint có thể tạo session để lưu token ngay cả khi anonymous.
- `GET /account`: yêu cầu login; phản hồi `hello alice`.
- `GET /api/counter`: yêu cầu login và trả bộ đếm.
- `POST /api/counter`: yêu cầu login **và** token CSRF hợp lệ; tăng bộ đếm.
- `POST /login`/`POST /logout`: để Spring Security xử lý với CSRF protection mặc định.

**Bộ đếm chỉ là dữ liệu demo trong bộ nhớ**. Nó cho thấy rõ rằng request bị 403 không được phép gây thay đổi trạng thái; ứng dụng thật cần database, authorization đối với tài nguyên và kiểm soát giao dịch.

### 9.1. Cấu trúc dự án

```text
csrf-three-values-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/csrfvalues/
    │   ├── CsrfValuesApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/com/example/csrfvalues/
        └── CsrfSeparationTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'csrf-three-values-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Vì ứng dụng dùng Spring, phải có các dependencies trên classpath. Dùng Gradle/Wrapper, không chỉ chạy `javac` và `java` trần khi thiếu thư viện.

### 9.2. Class khởi động

**`src/main/java/com/example/csrfvalues/CsrfValuesApplication.java`**

```java
package com.example.csrfvalues;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfValuesApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfValuesApplication.class, args);
    }
}
```

### 9.3. SecurityFilterChain: không tắt CSRF

**`src/main/java/com/example/csrfvalues/SecurityConfiguration.java`**

```java
package com.example.csrfvalues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public", "/csrf")
                    .permitAll()
                .requestMatchers("/account", "/api/counter")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout.permitAll())
            .csrf(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
```

Giải thích:

1. CSRF protection **được giữ mặc định**, dòng `.csrf(withDefaults())` chỉ viết tường minh. Với POST từ browser dùng session cookie, `CsrfFilter` phải kiểm tra token.
2. `GET /csrf` được mở để một client chưa login có thể lấy token cho **`POST /login`**. Điều này **không tạo Authentication**; nó chỉ tạo/đọc token CSRF. Với một site production, kiểm soát CORS/Origin, caching và độ nhạy cảm của response phù hợp.
3. `/account` và `/api/counter` cần authenticated; một CSRF token không đủ để vượt qua requirement này.
4. Form login dùng `HttpSession` và session cookie trong Servlet container; `BCryptPasswordEncoder` băm mật khẩu demo khi tạo user store. Mật khẩu `alice123` chỉ để học, không dùng trong môi trường thật.
5. `/login` và `/logout` do Spring Security filters xử lý. Với CSRF mặc định, các POST này cũng cần token hợp lệ; không cần tự tạo controller tương ứng.
6. `anyRequest().denyAll()` là fallback cho các route chưa phân loại, không tự làm GET an toàn nếu controller có side effects.
7. Không thêm OAuth2 Resource Server vào demo này vì mục tiêu là **tách CSRF token khỏi session cookie**. Phần access token ở mục 6 và 11 là đối chiếu lý thuyết; không tuyên bố demo đã cấp JWT/Bearer token.

**Không triển khai demo trực tiếp ra Internet:** chưa có HTTPS, production identity store, hạn mức request, audit và nhiều bảo vệ cần thiết.

### 9.4. Controller: trả CSRF token, đọc và tăng bộ đếm

**`src/main/java/com/example/csrfvalues/DemoController.java`**

```java
package com.example.csrfvalues;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ConcurrentHashMap<String, AtomicInteger> counters =
        new ConcurrentHashMap<>();

    private AtomicInteger counterFor(Principal principal) {
        return counters.computeIfAbsent(
            principal.getName(), name -> new AtomicInteger()
        );
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/api/counter")
    public Map<String, Object> current(Principal principal) {
        return Map.of(
            "user", principal.getName(),
            "counter", counterFor(principal).get()
        );
    }

    @PostMapping("/api/counter")
    public Map<String, Object> increment(Principal principal) {
        return Map.of(
            "user", principal.getName(),
            "counter", counterFor(principal).incrementAndGet()
        );
    }
}
```

Spring Security cung cấp `CsrfTokenArgumentResolver` cho `CsrfToken` trong controller Servlet, nên `GET /csrf` có thể trả JSON kiểu:

```json
{
  "parameterName": "_csrf",
  "headerName": "X-CSRF-TOKEN",
  "token": "GIA_TRI_NGAU_NHIEN_CUA_SESSION"
}
```

Giá trị ở đây chỉ là **ví dụ về cấu trúc**, không phải token hợp lệ để copy. Token thực được framework sinh ra và có thể được masked/encoded khác nhau giữa các response theo cơ chế Spring Security 6.

Không trả `JSESSIONID`, `SecurityContext`, password, access token hoặc các thông tin nội bộ trong `GET /csrf`. Endpoint này có thể dùng no-store cache policy và yêu cầu client gọi lại sau login/logout. Một API production có thể thiết kế endpoint CSRF phù hợp hơn với frontend; ví dụ chỉ tập trung vào kiến thức.

### 9.5. Chạy và quan sát

Yêu cầu: JDK 17+, Gradle 8.4+ tương thích và cổng 8080 rảnh. Tại thư mục `csrf-three-values-demo`:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle Wrapper tương thích, thay bằng `./gradlew test` / `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat test` / `gradlew.bat bootRun` (Windows).

Mở browser tới `http://localhost:8080/account`, đăng nhập với `alice` / `alice123` qua form mặc định.

- Sau login, `GET /account` trả body `hello alice`.
- `GET /api/counter` trả JSON kiểu `{"user":"alice","counter":0}` nếu đây là lần đọc đầu và chưa có POST nào thành công.
- Gửi `POST /api/counter` mà chỉ dựa trên cookie session **không kèm CSRF token** sẽ bị **403**, bộ đếm không tăng.
- Gửi POST có cùng cookie session **và CSRF token hợp lệ** trong `X-CSRF-TOKEN` hoặc tham số `_csrf` sẽ trả 200 và tăng bộ đếm.
- Gửi token CSRF nhưng **không có phiên đăng nhập hợp lệ** vẫn không cấp quyền POST, vì HTTP rule yêu cầu authenticated.

Cách mô phỏng qua browser DevTools cần giữ đúng session cookie và lấy token **sau khi đăng nhập**. Nếu nhận 403 vì token stale, tải lại `/csrf`; đừng tắt CSRF. Với cookie có `HttpOnly`, JavaScript browser không đọc trực tiếp `JSESSIONID` nhưng browser gửi cookie theo scope. Đó chính là lý do site cần lớp CSRF riêng cho request thay đổi trạng thái.

### 9.6. Các request HTTP minh họa

**Cùng session cookie, thiếu CSRF token:**

```http
POST /api/counter HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=SESSION_ID

```

Kỳ vọng **403 Forbidden** theo cấu hình demo. Session cookie trong ví dụ là ký hiệu, không phải credential thật.

**Cùng session cookie, có CSRF token:**

```http
POST /api/counter HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=SESSION_ID
X-CSRF-TOKEN: CSRF_TOKEN_FROM_CURRENT_SESSION

```

Kỳ vọng **200 OK** nếu session đã đăng nhập và token có hiệu lực. Không thể copy `CSRF_TOKEN_FROM_CURRENT_SESSION` như chuỗi literal; phải dùng token thật của context hiện hành.

**Chỉ CSRF token mà không có session đăng nhập:**

```http
POST /api/counter HTTP/1.1
Host: localhost:8080
X-CSRF-TOKEN: SOME_TOKEN

```

Dù giả định token có thể được xác minh trong một context anonymous, yêu cầu vẫn **không có Authentication của Alice**. Spring form-login thường redirect đến `/login`, không có lý do gì cho phép thay đổi dữ liệu.

### 9.7. Kiểm thử tự động với Spring Security Test và MockMvc

**`src/test/java/com/example/csrfvalues/CsrfSeparationTests.java`**

```java
package com.example.csrfvalues;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfSeparationTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loginAlice() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("alice123")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void publicEndpointNeedsNoLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void csrfTokenEndpointIsAvailableBeforeLogin() throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.parameterName").value("_csrf"))
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isNotEmpty());
    }

    @Test
    @WithMockUser(username = "alice")
    void sessionAuthenticationWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/counter"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void invalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/counter").with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice")
    void validCsrfWithAuthenticationIsAllowed() throws Exception {
        mvc.perform(post("/api/counter").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"))
            .andExpect(jsonPath("$.counter").isNumber());
    }

    @Test
    void csrfTokenAloneDoesNotAuthenticateUser() throws Exception {
        mvc.perform(post("/api/counter").with(csrf()))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "alice123"))
            .andExpect(status().isForbidden());
    }

    @Test
    void realLoginSessionStillNeedsCsrfForUnsafeRequest()
            throws Exception {
        MockHttpSession session = loginAlice();

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));

        mvc.perform(post("/api/counter").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/counter").session(session).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void logoutRequiresCsrfEvenWithLoggedInSession()
            throws Exception {
        MockHttpSession session = loginAlice();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk());

        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Ý nghĩa kiểm thử:**

- `@WithMockUser` dựng security context hợp lệ cho một test, **không mô phỏng cookie `JSESSIONID` từ browser thật**. Nhờ vậy hai test thiếu/sai token tách bạch **authentication** và **CSRF protection**.
- `csrf()` của `spring-security-test` tạo/mang CSRF token phù hợp cho request MockMvc, giúp kiểm thử nhánh thành công; `csrf().useInvalidToken()` kiểm tra nhánh từ chối.
- `formLogin()` gửi request đăng nhập có CSRF hợp lệ; session được trả từ request sau login mô phỏng tính tái sử dụng của `HttpSession`.
- `realLoginSessionStillNeedsCsrfForUnsafeRequest` là phép thử quan trọng nhất: **có phiên xác thực vẫn bị 403 nếu thiếu CSRF token**, và cùng session được phép khi có token.
- `csrfTokenAloneDoesNotAuthenticateUser` chứng minh chiều ngược lại: **có CSRF token nhưng chưa login không được thay đổi dữ liệu**.
- `logoutRequiresCsrfEvenWithLoggedInSession` chỉ ra logout cũng là thao tác nhạy cảm được CSRF protection bảo vệ.
- Các test so status và dữ liệu trả về, không ép chuỗi token ngẫu nhiên phải cố định.
- Bài test này **không thay thế** kiểm chứng browser thực về cookie `Secure`/`SameSite`, CORS, token masking, TLS hoặc chính sách access token. Cần integration/security tests riêng cho các tình huống đó.

## 10. Câu hỏi thường gặp: vì sao có cookie rồi vẫn cần token CSRF?

Vì chính browser tự gửi cookie. Nếu cookie đủ để biết user là Alice, site khác có thể lợi dụng browser làm “máy gửi request dưới danh tính Alice” trong các tình huống cookies được gửi kèm.

CSRF token đặt trong **form field/header không tự gửi** làm tăng yêu cầu: site khác không thể đơn giản tạo một request có token chính xác. Nó không xác thực danh tính — chỉ bảo vệ tính hợp lệ của **nguồn tạo request trong ngữ cảnh cookie authentication** theo threat model.

### Vì sao CSRF token không thể thay thế access token?

Nếu client chỉ mang `X-CSRF-TOKEN` mà không có session cookie hay bearer credentials, Resource Server chưa biết user nào được cấp quyền và không thể dựa vào token CSRF để suy ra `sub`/`roles`/`scope`.

Một CSRF token rơi vào tay kẻ tấn công có thể hỗ trợ giả mạo request **nếu kết hợp** với các điều kiện khác, nhưng nó **không phải** OAuth2 access token. Không chấp nhận giá trị `_csrf` trong `Authorization: Bearer` hoặc làm identity provider chỉ từ token CSRF.

### Vì sao access token không tự thay thế CSRF token?

Bởi access token trả lời “credential có hợp lệ không?”. Nếu browser tự gửi credential đó (ví dụ JWT ở cookie) thì nguy cơ request cross-site vẫn tồn tại. Dù dùng JWT có chữ ký, backend vẫn cần chính sách chống CSRF phù hợp với cách browser gửi credentials.

### Lấy CSRF token qua GET có mất tác dụng không?

Không nhất thiết. Ứng dụng hợp lệ cùng origin cần cách lấy token để tạo POST sau đó. Trong synchronizer token pattern, token có thể được đưa vào HTML form hoặc trả qua `GET /csrf`. Kẻ tấn công ở cross-origin thường không được đọc response của ứng dụng nếu SOP/CORS được cấu hình đúng, và không thể đoán token ngẫu nhiên.

Nhưng nếu CORS mở quá rộng **kèm credentials**, XSS cùng origin, token bị log hoặc endpoint CSRF bị công bố qua một kênh không an toàn, bảo vệ có thể bị suy yếu. Cần giữ response `/csrf` riêng tư theo threat model, tránh caching không phù hợp và không nhầm “permitAll” với “cho origin ngoài đọc dữ liệu”.

### Cookie XSRF-TOKEN có phải cookie phiên không?

Không. Nó là nơi lưu token CSRF khi dùng `CookieCsrfTokenRepository`. Cookie phiên `JSESSIONID` thường dùng để trỏ đến `HttpSession` chứa trạng thái đăng nhập. Hai cookie có tên, chức năng, thuộc tính `HttpOnly` và chính sách vòng đời riêng. Một SPA có thể đọc cookie CSRF nhưng vẫn **không** được đọc cookie phiên HttpOnly.

## 11. Sau khi đăng nhập, đăng xuất hoặc session hết hạn

### Khi login thành công

- Session ID có thể được thay đổi để chống session fixation.
- Spring Security có thể clear CSRF token cũ thông qua `CsrfAuthenticationStrategy`.
- Một frontend giữ token cũ đã nhận từ trang login có thể gặp 403 khi POST sau login.
- Với ứng dụng HTML server-rendered, trang mới cần nhận token phù hợp. Với SPA, nên chủ động gọi lại endpoint `/csrf` sau authentication success.

**Không dựa vào tính cố định của token:** raw expected token, masked token biểu diễn trong HTML và token sau login là các khái niệm có thể khác nhau.

### Khi logout

- Spring Security mặc định bảo vệ `POST /logout` bằng CSRF khi CSRF bật.
- `CsrfLogoutHandler` clear token liên quan, các logout handlers khác có thể invalidate `HttpSession` và clear `SecurityContext`.
- Token trước logout không nên được frontend tiếp tục dùng khi khởi tạo session mới.
- Logout session web **không tự revoke access token JWT/refresh token** đã phát ở một IdP; cần cơ chế revoke/SSO logout tương ứng.

### Khi session timeout

- Browser có thể vẫn giữ cookie `JSESSIONID` cũ nhưng session phía server đã hết.
- Token CSRF kỳ vọng trong `HttpSession` cũng không còn, nên POST từ tab cũ có thể bị **403 Missing/Invalid CSRF** trước khi user thấy login redirect.
- UI nên xử lý tình huống này bằng cách yêu cầu login lại và lấy token mới, không gán mọi 403 cho “thiếu role”.
- Một request GET tới form/login page có thể tạo token mới tùy cấu hình; cần kiểm tra đúng session và không gửi token cũ trên phiên mới.

### Giới hạn của “token rotation”

Spring Security có thể làm mới/clear token vào những sự kiện bảo mật như login/logout. Điều đó khác với cơ chế **CSRF token dùng một lần cho mỗi request**; không suy luận cứ có BREACH masking thay đổi là token server-side đã rotate mỗi request. Và không được dựa CSRF token để chống gửi lại giao dịch đã được xác thực; dùng idempotency key hoặc transaction authorization thích hợp.

## 12. Lỗi HTTP 401, 403 và quyền nghiệp vụ

| Tình huống | Cách xử lý điển hình trong demo | Ý nghĩa |
| --- | --- | --- |
| `GET /account` không có session | 302 về `/login` | Chưa xác thực cho form login |
| `GET /account` có session hợp lệ | 200 | Qua authentication |
| `GET /csrf` khi chưa login | 200 + CSRF token | Chỉ nhận token, không nhận quyền user |
| `POST /api/counter` có session nhưng thiếu `_csrf`/header | 403 | CSRF filter chặn |
| `POST /api/counter` có session nhưng sai CSRF token | 403 | CSRF filter chặn |
| `POST /api/counter` có session và CSRF hợp lệ | 200 | Qua cả CSRF và authentication |
| `POST /api/counter` có CSRF nhưng chưa login | 302 về `/login` với form login | CSRF không xác thực user |
| `POST /login` thiếu CSRF | 403 | Không phải “mật khẩu sai” |
| `POST /logout` thiếu CSRF | 403 | Không được logout |
| `GET /api/counter` đã login | 200 | GET thường không cần CSRF nếu không thay đổi trạng thái |

Đây là bảng **cho cấu hình demo ở mục 9**. Ứng dụng OAuth2 Resource Server/HTTP Basic có thể trả **401** thay vì redirect về form login. Khi user có danh tính nhưng không có quyền trên tài nguyên, **403** có thể do authorization chứ không phải CSRF; cần biết filter/exception nào thực sự chặn.

**Không đưa mã lỗi “CSRF invalid” cùng raw token ra response công khai** nếu khiến lộ bí mật; logging nội bộ nên tránh in token đầy đủ. Với API JSON, có thể xử lý lỗi theo contract ổn định nhưng đừng che vấn đề security bằng cách tự retry POST nhiều lần.

## 13. Khi nào nên giữ hoặc bỏ CSRF protection?

| Kiến trúc | Browser tự gửi credentials? | Định hướng |
| --- | --- | --- |
| Form login + session cookie | Có | **Giữ CSRF protection** cho unsafe methods |
| Server-rendered MVC + session cookie | Có | **Giữ CSRF**; form có hidden token |
| SPA + session cookie/BFF cookie | Có | **Giữ CSRF**; thiết kế endpoint/token header và handler SPA phù hợp |
| SPA lưu JWT trong cookie HttpOnly và cookie tự gửi | Có | **Vẫn có nguy cơ CSRF**; chọn biện pháp phù hợp |
| API chỉ có bearer token được client chủ động thêm ở Authorization header | Thường không theo cách cookie | Có thể đánh giá không cần CSRF cho endpoint đó nếu không có ambient credentials và threat model cho phép |
| Service-to-service mTLS/bearer không qua browser | Không theo cách browser cookie | Thường CSRF không phải nguy cơ chính; vẫn bảo vệ authn/authz/token replay |
| Ứng dụng hỗn hợp cookie + bearer | Có, ở một số routes | Cấu hình theo **SecurityFilterChain** hoặc matcher thật; không tắt global tùy tiện |

Một API có tên “REST” hoặc trả JSON không khiến credentials mất tính tự gửi. Nếu ứng dụng cho browser cookie session truy cập API JSON, CSRF vẫn có thể áp dụng.

**Thận trọng với cơ chế Basic authentication trong browser:** trình duyệt có thể tự gửi/ghi nhớ Basic credentials theo origin/realm. Một API dùng HTTP Basic không nhất thiết tránh được CSRF chỉ vì credentials nằm ở Authorization header. Phân tích cách client phát header trên request cross-site.

### Trường hợp chia nhiều SecurityFilterChain

Có thể có chain browser dùng form login + CSRF, chain API dùng bearer-only stateless theo policy khác. `securityMatcher` quyết định chain nào xử lý request; `@Order` cần cấu hình chain đặc thù trước chain tổng quát. Khi bỏ CSRF cho một chain, phải chứng minh chain đó không chấp nhận browser ambient credentials và không có endpoints cần bảo vệ CSRF. Không lẫn sự chọn chain đầu tiên với `requestMatchers` authorization bên trong chain.

**Không bỏ CSRF ở `POST /login` hoặc `POST /logout`** mà chưa phân tích login/logout CSRF. Spring Security mặc định bảo vệ các yêu cầu này trong Servlet.

## 14. Checklist bảo vệ triển khai thực tế

1. **Xác định credential thực:** session cookie, access token header, bearer trong cookie, Basic browser hay phối hợp.
2. **Phân loại unsafe operations:** POST/PUT/PATCH/DELETE và bảo đảm không có GET gây side effect nhạy cảm.
3. **Đặt CSRF token ở đúng chỗ:** token do client nộp nằm trong form field hoặc header, không chỉ trong cookie và không trong URL query.
4. **Giữ token khó đoán, không lộ qua log/cache/analytics:** tránh render sang origin ngoài hoặc đưa vào `Referer`.
5. **Lưu expected token đúng repository:** HttpSession, cookie hoặc custom HMAC được thiết kế/kiểm toán; đừng gộp với session ID.
6. **Nếu dùng SPA Spring Security 6:** kiểm tra XOR/BREACH handler, raw cookie header và việc lấy token sau login/logout.
7. **Cookie session:** `Secure`, `HttpOnly`, `SameSite`, scope `Path`/`Domain` đúng. SameSite là lớp bổ sung, không phải toàn bộ giải pháp.
8. **CORS/Origin/Fetch Metadata:** cấu hình theo trusted origins; không kết hợp wildcard với credentials bừa bãi.
9. **Phân biệt 401 với 403:** CSRF failure, authentication failure, authorization failure có nhánh khác nhau.
10. **Cân nhắc XSS:** chống script injection, escaping, CSP, dependency hygiene; CSRF token không bảo vệ khi attacker chạy được code cùng origin.
11. **Kiểm thử negative:** có session nhưng thiếu token; sai token; token hợp lệ nhưng anonymous; token stale sau logout/login.
12. **Kiểm tra quyền ở service:** CSRF token không chứng minh owner/tenant/role và không thay authorization.
13. **Test browser thật:** cookie flags, SameSite, subdomain, SSO, reverse proxy, CSRF token generation, login/logout flows.
14. **Không hard-code token:** generate từ framework, ràng buộc đúng context, rotate/expire theo policy.
15. **Không tự tuyên bố mọi trường hợp đều an toàn:** kiểm thử chính xác các browser, path, cookies và cơ chế auth mà ứng dụng đang hỗ trợ.

## 15. Bài tập tình huống có lời giải

**Câu 1.** Alice có `JSESSIONID` hợp lệ. Vì sao POST thiếu CSRF token vẫn có thể bị 403?

**Đáp án:** cookie chỉ khôi phục Authentication của Alice; nó không chứng minh request được trang hợp lệ tạo ra. `CsrfFilter` yêu cầu giá trị CSRF do client chủ động nộp phù hợp session và chặn nếu thiếu.

**Câu 2.** Một request chỉ mang header `X-CSRF-TOKEN` hợp lệ nhưng không có session đăng nhập. Nó được tự động phép cập nhật dữ liệu không?

**Đáp án:** không. CSRF token không xác thực user; backend vẫn cần Authentication và authorization riêng. Trong form login, thường redirect về `/login` nếu CSRF check đã qua.

**Câu 3.** Có thể dùng giá trị `JSESSIONID` làm `_csrf` không?

**Đáp án:** không. Nếu sao chép session ID làm CSRF token, bạn biến một định danh credential nhạy cảm thành dữ liệu cần đưa vào HTML/request, tạo nguy cơ lộ phiên và phá vỡ ranh giới trách nhiệm. Dùng token CSRF độc lập do framework tạo.

**Câu 4.** Nếu cookie `XSRF-TOKEN` được browser tự gửi, tại sao còn cần header `X-XSRF-TOKEN`?

**Đáp án:** vì cookie tự gửi không phân biệt request giả mạo; header do ứng dụng cùng origin tạo có thể chứng minh client có khả năng đọc/nhận token, rồi server xác minh. Với Spring Security 6, cần request handler phù hợp với dạng raw/masked token.

**Câu 5.** Vì sao JWT trong cookie không tự loại bỏ CSRF?

**Đáp án:** vì browser có thể tự gửi cookie JWT trong request cross-site theo scope/SameSite; API có thể xử lý request dưới danh tính người dùng mà attacker không cần đọc JWT. CSRF phụ thuộc *cách gửi credential*, không phụ thuộc *định dạng JWT*.

**Câu 6.** Một SPA tự gắn `Authorization: Bearer ...` header và API không dùng cookie login. Có nhất thiết bật CSRF như form login không?

**Đáp án:** có thể không cần với threat model phù hợp vì browser không tự biết cách thêm header chứa token của SPA vào request từ origin khác. Nhưng vẫn cần xem Basic auth, refresh-cookie endpoints, XSS, CORS và các đường auth khác; không áp dụng kết luận cho mọi route.

**Câu 7.** Vì sao token từ form HTML ở hai GET khác nhau có thể không giống nhau trong Spring Security 6?

**Đáp án:** `XorCsrfTokenRequestAttributeHandler` tạo giá trị hiển thị có random masking nhằm chống BREACH. Không nên suy luận expected raw token/session đã bị đổi mỗi request.

**Câu 8.** Vì sao SPA có thể bị 403 ngay sau login dù trước login đã lấy CSRF token?

**Đáp án:** token cũ có thể đã bị `CsrfAuthenticationStrategy` clear sau authentication. SPA cần lấy token mới sau login, dùng handler thích hợp và gửi đúng header.

**Câu 9.** Nếu server cho phép `GET /delete-account` xóa tài khoản, CSRF filter mặc định có chặn request đó không?

**Đáp án:** không thể dựa vào nó vì GET được xem là safe và thường không yêu cầu CSRF. Phải sửa API để thao tác thay đổi trạng thái dùng unsafe method phù hợp và authorization/CSRF đúng cách.

**Câu 10.** Vì sao SameSite cookie và CORS không phải biện pháp CSRF duy nhất?

**Đáp án:** SameSite có giới hạn theo browser và khái niệm same-site; CORS phần lớn kiểm soát chia sẻ/đọc response, không ngăn mọi form/request được gửi. CSRF token hoặc biện pháp tương đương phù hợp cần được đánh giá trong threat model.

**Câu 11.** Nếu access token hợp lệ với scope `orders.read`, có chắc được phép đọc đơn hàng của user khác không?

**Đáp án:** không. Access token chứng minh credential/scope theo issuer, còn quyền owner/tenant trên từng resource phải được service kiểm tra. CSRF token cũng không thể thay chính sách đó.

**Câu 12.** Token CSRF được giữ trong cookie readable bằng JavaScript có nghĩa phải tắt `HttpOnly` cho session cookie không?

**Đáp án:** không. `withHttpOnlyFalse()` ở `CookieCsrfTokenRepository` chỉ dành cho cookie CSRF nếu frontend cần đọc nó. Session cookie nên tiếp tục dùng HttpOnly khi phù hợp.

**Câu 13.** Khi session hết, browser vẫn gửi cookie và token từ tab cũ, chuyện gì có thể xảy ra?

**Đáp án:** server không còn expected token/Authentication của phiên cũ nên unsafe request có thể bị 403. Frontend cần đồng bộ trạng thái login, lấy token mới và để người dùng xác thực lại.

**Câu 14.** CSRF token có thể thay thế idempotency key ngăn bấm nút chuyển tiền hai lần không?

**Đáp án:** không. CSRF token thường được dùng lại trong phiên, chỉ chống giả mạo request. Chống giao dịch trùng lặp cần idempotency/transaction controls riêng.

## 16. Tóm tắt cuối bài

- **Session cookie** trả lời “request này thuộc phiên xác thực nào?”; browser có thể **tự gửi** cookie.
- **CSRF token** trả lời “unsafe request có mang bằng chứng chống giả mạo phù hợp không?”; app phải **chủ động gửi** token qua header/form field; token không phải danh tính hoặc quyền.
- **Access token** là credential cho API, có scopes/audience/expiry và cần kiểm tra ở Resource Server; không tự thay CSRF token khi được browser tự gửi trong cookie.
- Spring Security Servlet dùng `CsrfFilter` và `CsrfTokenRepository`; mặc định thường là `HttpSessionCsrfTokenRepository`, còn `CookieCsrfTokenRepository` là phương án khác.
- **Spring Security 6** có deferred loading và `XorCsrfTokenRequestAttributeHandler` chống BREACH; SPA đọc raw cookie token cần handler phù hợp.
- **CSRF và Authentication là hai lớp độc lập:** có phiên mà thiếu CSRF → có thể 403; có CSRF mà không login → vẫn không có quyền.
- **Login/logout và các unsafe methods** cần được bảo vệ phù hợp; frontend có thể phải lấy token mới sau login/logout/session timeout.
- **CSRF phụ thuộc cách browser gửi credentials**, không phụ thuộc tên cookie, JWT hay việc endpoint trả JSON.
- Giữ CSRF protection, SameSite, cookie flags, CORS/Origin/Fetch Metadata, chống XSS và authorization theo tài nguyên như các lớp bảo vệ phối hợp.
- Dùng bài test để kiểm tra cả trường hợp được phép lẫn bị từ chối; với production còn cần kiểm tra browser và hạ tầng thật.

## Tài liệu tham khảo

- Spring Security — CSRF Servlet, repositories, deferred tokens, BREACH, SPA, /csrf endpoint và tests: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — CSRF overview và synchronizer token pattern: https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
- Spring Security — Spring Security 6 CSRF migration: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/exploits.html
- Spring Security — MockMvc CSRF testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Form login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — Logout and CSRF: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- OWASP — Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
