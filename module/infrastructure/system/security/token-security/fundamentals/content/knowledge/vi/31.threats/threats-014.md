# CSRF khi dùng cookie token

Một ứng dụng quản lý hóa đơn dùng access token hoặc session ID trong cookie `HttpOnly`. Người dùng đã đăng nhập vào `https://invoice.example.test` và mở thêm trang của kẻ tấn công. Trang đó gửi một request thay đổi tài khoản tới Invoice API. Trình duyệt có thể **tự đính kèm cookie của Invoice API** vào request, mặc dù người dùng không hề chủ động thực hiện thao tác ở ứng dụng chính.

Đó là bản chất của **Cross-Site Request Forgery (CSRF)**: kẻ tấn công lợi dụng **quyền xác thực được trình duyệt tự động gửi** để kích hoạt thao tác thay mặt nạn nhân. Vấn đề không phải kẻ tấn công biết được giá trị access token; họ có thể **không đọc được cookie `HttpOnly`**, không giải mã JWT, không biết mật khẩu, nhưng vẫn dụ trình duyệt của nạn nhân gửi một yêu cầu có credential.

Trong module **Security Token Security Fundamentals**, bài **“CSRF khi dùng cookie token”** thuộc chương **Threats** làm rõ ranh giới giữa **lưu token an toàn**, **xác thực**, **phân quyền OAuth 2.0/OIDC** và **bảo vệ request**. Trọng tâm gồm: cơ chế gửi cookie tự động (*ambient authority*), `SameSite`/`Secure`/`HttpOnly`, CSRF token, Origin/Fetch Metadata, CORS, Backend For Frontend (BFF), login/logout/refresh CSRF, Java/Spring Security và ma trận kiểm thử.

**Thông điệp quan trọng nhất:** **Đưa JWT vào cookie `HttpOnly` có thể giúp giảm việc JavaScript đọc trộm token, nhưng không tự chống CSRF.** Nếu server chấp nhận cookie làm credential, request thay đổi trạng thái cần một cơ chế chứng minh **yêu cầu xuất phát từ tương tác hợp lệ trong ngữ cảnh ứng dụng**, không chỉ chứng minh có cookie hợp lệ.

## 1. Threat model: attacker có gì và không cần có gì?

Giả sử hệ thống dùng:

~~~text
Ứng dụng chính (victim origin):
  https://invoice.example.test

API:
  POST https://invoice.example.test/api/account/email

Cookie xác thực:
  __Host-session=<opaque-session-id>
  Secure; HttpOnly; SameSite=None; Path=/

Trang do attacker kiểm soát:
  https://evil.invalid
~~~

`SameSite=None; Secure` trong ví dụ cho phép cookie được gửi ở ngữ cảnh cross-site nếu trình duyệt và chính sách cookie cho phép. Ta chọn cấu hình này **để minh họa điều kiện CSRF**, không khuyến nghị dùng `SameSite=None` cho mọi ứng dụng.

Attacker có thể khiến nạn nhân tải HTML:

~~~html
<!doctype html>
<html lang="vi">
<body>
  <form id="change" method="POST"
        action="https://invoice.example.test/api/account/email">
    <input type="hidden" name="newEmail"
           value="attacker-controlled@example.invalid">
  </form>
  <script>
    document.getElementById("change").submit();
  </script>
</body>
</html>
~~~

Trình duyệt cố gửi một HTTP POST đến Invoice API. **Nếu** cookie policy cho phép, browser tự gắn `Cookie: __Host-session=...` vào request tới domain đích:

~~~http
POST /api/account/email HTTP/1.1
Host: invoice.example.test
Origin: https://evil.invalid
Cookie: __Host-session=<browser-sent-session-id>
Content-Type: application/x-www-form-urlencoded

newEmail=attacker-controlled%40example.invalid
~~~

Nếu backend chỉ làm:

~~~text
session = lookup(Cookie["__Host-session"])
if session.isAuthenticated:
    updateEmail(session.user, request.newEmail)
~~~

thao tác có thể thành công **mà không cần attacker đọc response**. Đây là lỗi CSRF. Cơ chế bảo vệ cần đảm bảo những request kiểu này **bị chặn trước khi cập nhật dữ liệu**.

### Những tiền đề để CSRF xảy ra

1. **Nạn nhân có trạng thái xác thực hợp lệ** trong browser đối với ứng dụng đích.
2. **Credential được tự động gửi** theo loại request/ngữ cảnh, thường là cookie; cũng có thể là HTTP authentication khác được browser quản lý.
3. Attacker điều khiển một trang/đường dẫn hoặc cách khiến browser tạo request đến ứng dụng đích.
4. Endpoint đích có **tác động thay đổi trạng thái** hoặc hậu quả bảo mật.
5. Server **không xác thực đủ nguồn gốc/ý định request** hoặc có lỗ hổng trong các lớp phòng vệ.

Nếu cookie là `SameSite=Strict` hoặc `Lax`, một số request từ `evil.invalid` có thể **không mang cookie**, nên ví dụ trên sẽ thất bại ở điều kiện gửi credential. Nhưng ứng dụng vẫn cần đánh giá **sibling subdomain cùng site**, cookie policy thực tế, luồng điều hướng và các endpoint khác; `SameSite` không thay hoàn toàn lớp CSRF protection.

### CSRF không cần lấy được token

| Rủi ro | Attacker cần gì? | Bản chất |
|---|---|---|
| **CSRF cookie-authenticated API** | Khiến browser gửi request kèm credential tự động | **Dùng nhờ** phiên nạn nhân |
| **XSS đánh cắp token từ `localStorage`** | Chạy JavaScript trong origin ứng dụng | Có thể **đọc** token nếu token được lưu ở JS storage |
| **XSS trên ứng dụng có `HttpOnly`** | Chạy JavaScript trong origin ứng dụng | Có thể **gửi yêu cầu cùng origin** dù không đọc cookie; `HttpOnly` không vô hiệu XSS |
| **Bearer token replay** | Có nguyên chuỗi bearer token | Gửi token trực tiếp tới RS, không cần browser nạn nhân |
| **Session fixation** | Ảnh hưởng giá trị session trước/sau login | Buộc phiên liên kết sai danh tính hoặc không rotate |

CSRF, XSS và token replay **có mối liên hệ nhưng là ba threat models khác nhau**. Không thay CSRF token bằng CSP, và không thay chống XSS bằng `SameSite`.

## 2. Tại sao cookie JWT vẫn chịu CSRF?

Một backend có thể phát cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-access=<signed-jwt>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

JWT có thể có chữ ký hợp lệ, `iss`, `aud`, `scope` và `exp` đúng. Những kiểm tra đó chứng minh **token được phát và có quyền gì**; chúng **không chứng minh ai đã chủ động khởi tạo HTTP request hiện tại**.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser có cookie
    participant E as Trang attacker
    participant RS as Invoice API
    U->>B: Đăng nhập Invoice Web trước đó
    RS-->>B: Set-Cookie session/JWT
    U->>E: Vô tình mở evil.invalid
    E-->>B: HTML form / request cross-origin
    B->>RS: Request + cookie (nếu browser cookie policy cho phép)
    RS->>RS: JWT signature/exp/scope đều hợp lệ
    Note over RS: Nếu thiếu CSRF check, request có thể thay đổi dữ liệu
    RS-->>B: Response (attacker không cần đọc)
~~~

**JWT không có “CSRF-proof” mặc định.** Một JWT có `jti` không tự chứng minh request là lần đầu hoặc được user chấp thuận. Nếu token nằm trong cookie, nó được browser gửi theo quy tắc cookie; việc xác thực chữ ký JWT không giải quyết **request provenance**.

### Phân biệt “token trong cookie” và “token trong Authorization header”

| Cách trình token | Có browser tự gửi credential? | CSRF trong mô hình thông thường | Rủi ro bổ sung |
|---|---|---|---|
| **Session ID trong `HttpOnly` cookie** | Có, theo cookie policy | **Có thể có**, cần CSRF defense | Session theft/fixation, XSS vẫn gửi request được |
| **JWT access token trong `HttpOnly` cookie** | Có | **Có thể có**, chữ ký không chặn | Token theft/replay, expiry và revoke |
| **Refresh token trong `HttpOnly` cookie** | Có ở endpoint phù hợp | **Có thể có** tại `/refresh`/grant management | Refresh abuse/rotation races |
| **BFF cookie, BFF giữ access token server-side** | Browser gửi BFF cookie tự động | **Có thể có** ở BFF endpoints | BFF phải chặn CSRF trước khi gọi RS |
| **Access token do JS chủ động thêm `Authorization: Bearer ...`** | Không được browser tự thêm như cookie trong mô hình này | Cross-site form không tự có header đó, giảm vector CSRF cổ điển | JS-readable token có nguy cơ XSS/token theft |
| **DPoP-bound access token trong JS client** | Client chủ động tạo proof và header | Không tự giống cookie ambient auth; cần kiểm kiến trúc | Key theft/XSS/signing oracle và proof replay |

Không có lựa chọn nào “an toàn tuyệt đối”. **BFF + cookie `HttpOnly` + CSRF defense + chống XSS** thường là một phương án cân bằng cho web app có backend; Bearer token trong JS có tradeoff khác về XSS và storage.

## 3. `HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path` có vai trò gì?

Cookie attributes là **lớp phòng vệ quan trọng**, nhưng mỗi attribute giải quyết một mục tiêu khác:

| Thuộc tính | Mục tiêu chính | Có tự chặn CSRF không? |
|---|---|---|
| **`HttpOnly`** | Ngăn JavaScript đọc/ghi cookie qua `document.cookie` | **Không**: browser vẫn tự gửi cookie trong HTTP request |
| **`Secure`** | Chỉ gửi cookie qua HTTPS (với quy tắc browser tương ứng) | **Không**: CSRF có thể xảy ra hoàn toàn trên HTTPS |
| **`SameSite=Strict`** | Hạn chế gửi cookie trong các ngữ cảnh cross-site, kể cả top-level navigation | Giảm vector CSRF, nhưng **same-site cross-origin** và các flow vẫn cần review |
| **`SameSite=Lax`** | Gửi trong ngữ cảnh same-site và một số top-level cross-site navigation với safe methods | Giảm CSRF cross-site POST phổ biến, **không bảo vệ mọi ngữ cảnh** |
| **`SameSite=None; Secure`** | Cho phép cookie ở các ngữ cảnh cross-site nếu browser cho phép | Tạo bề mặt CSRF cao hơn nếu thiếu defense |
| **`Domain`** | Quy định hostname nào được nhận cookie; có thể mở rộng sang subdomains | Scope quá rộng tăng rủi ro cookie injection/sharing |
| **`Path`** | Quy định các path yêu cầu sẽ gửi cookie | **Không** phải access-control boundary |
| **Cookie prefix `__Host-`** | Buộc `Secure`, `Path=/` và **không có `Domain`** ở browser hỗ trợ | Giảm cookie injection từ sibling subdomain; **không tự chống CSRF** |
| **Cookie prefix `__Secure-`** | Buộc `Secure` ở browser hỗ trợ | Không chặn request giả |

### Host-only cookie và sibling subdomains

Cookie:

~~~http
Set-Cookie: __Host-session=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Là host-only vì không có `Domain`. Điều này giúp tránh một subdomain khác đặt cookie có `Domain=example.test` rồi chiếm cùng tên cookie với prefix `__Host-` ở host đích. **Nhưng khi browser gửi request tới chính `invoice.example.test`, cookie host-only vẫn được gửi đến host đó**, dù request **được khởi tạo từ một trang sibling cùng site**.

Ví dụ:

~~~text
Origin trang attacker:
  https://promo.example.test

Origin API:
  https://invoice.example.test

Same origin?  NO (host khác)
Same site?    Có thể YES (cùng scheme + registrable domain)

Nếu promo.example.test bị takeover:
  SameSite=Strict/Lax có thể vẫn cho cookie của Invoice
  đi kèm request tới invoice.example.test vì request same-site.
~~~

**Same-site khác same-origin.** Với **schemeful same-site**, scheme cũng có vai trò: `https://foo.example.test` và `http://bar.example.test` không nhất thiết được coi same-site. Phân loại site còn phụ thuộc **Public Suffix List**, nên không suy chỉ từ việc các hostname có hậu tố trông giống nhau.

### `SameSite=Lax` và các trường hợp đặc biệt

Với cấu hình **explicit `SameSite=Lax`**, cookie thường **không** được gửi trong **cross-site POST form** ở ngữ cảnh thông thường, nhưng có thể được gửi trong **cross-site top-level navigation dùng safe HTTP method**, điển hình GET. Do đó:

- **GET không được làm thay đổi dữ liệu**; nếu `GET /transfer?amount=...` gây chuyển tiền thì Lax không giải quyết.
- Một browser có thể có chính sách **Lax-by-default** với ngoại lệ tương thích cho cookie mới được tạo khi `SameSite` bị **bỏ trống**, chẳng hạn một số tình huống POST top-level trong cửa sổ ngắn. **Đặt explicit SameSite policy**, không dựa vào browser default.
- Tính năng từ bên thứ ba, iframe và federated login/logout có thể cần cookie exceptions; phải review từng flow và áp CSRF token/Origin verification.
- **Siblings cùng site** vẫn có thể tạo request mà cookie được gửi dù nguồn là **origin khác**.

**Vì vậy, `SameSite` là defense-in-depth, không thay phép kiểm CSRF cho mọi endpoint thay đổi trạng thái.**

## 4. CORS và Same-Origin Policy có ngăn request CSRF không?

Đây là nhầm lẫn phổ biến nhất: **CORS chủ yếu kiểm soát việc JavaScript của origin khác đọc response và một số cross-origin requests cần preflight, không phải lá chắn mặc định ngăn trình duyệt gửi mọi request.**

### HTML form có thể gửi request “đơn giản”

Một trang ngoài có thể tạo HTML form POST với những content types browser cho phép như:

- `application/x-www-form-urlencoded`;
- `multipart/form-data`;
- `text/plain`.

Các request kiểu HTML form **không cần được cấp quyền bằng CORS `Access-Control-Allow-Origin`** để browser bắt đầu gửi. Response có thể bị Same-Origin Policy ngăn attacker đọc, nhưng **side effect đã xảy ra** nếu server chấp nhận cookie.

### JavaScript `fetch` và preflight

~~~javascript
// Chỉ minh họa request cross-origin.
fetch("https://invoice.example.test/api/account/email", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-Token": "attacker-cannot-know-valid-token"
  },
  body: JSON.stringify({
    newEmail: "attacker@example.invalid"
  })
});
~~~

Một request cross-origin có `Content-Type: application/json` hoặc custom header thường cần **CORS preflight**; nếu Invoice API **không cho phép** origin attacker, browser có thể ngăn request chính. Nhưng cần hai điều kiện:

1. API **thực sự chỉ chấp nhận** định dạng/header được bảo vệ, **không** fallback parse form/text/plain hoặc method override thành thao tác nhạy cảm.
2. CORS được cấu hình **allowlist origin cụ thể**, không phản chiếu tùy ý `Origin` hoặc tin mọi `*.example.test` khi có subdomain không đáng tin.

**Không xem “đặt custom header” là tương đương với CSRF token bí mật:** header tự đặt có thể bị gửi từ origin đã được CORS cho phép, XSS, hoặc một client không thuộc browser. Header-based strategy phụ thuộc **trusted origin policy**, còn synchronizer token/signed double-submit cung cấp thêm ràng buộc phiên.

### Vì sao CORS wildcard sai khi dùng credentials?

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Tổ hợp này **không hợp lệ cho credentialed CORS response** trong browser theo quy tắc CORS. Nhưng việc cấu hình sai cũng **không đồng nghĩa các form requests bị chặn**. Nguy hiểm hơn là server **phản chiếu mọi `Origin`** và gửi `Access-Control-Allow-Credentials: true`, khiến JavaScript attacker có thể đọc một số response nhạy cảm khi browser gửi credential theo cookie policy.

### Quy tắc đúng

**CORS và CSRF giải quyết các vấn đề khác nhau**. Dùng CORS allowlist chặt cho cross-origin API thực sự cần thiết, **đồng thời** dùng CSRF defense và kiểm đúng cookie policy ở endpoints xác thực bằng cookie.

## 5. Các endpoint nào cần phòng CSRF?

Một ứng dụng dùng cookie làm credential cần kiểm mọi thao tác có **side effect**, không chỉ endpoint gọi là “transfer”.

| Endpoint/tác vụ | Có tác động trạng thái? | Vấn đề khi thiếu CSRF |
|---|---|---|
| `POST /api/payments` | Có | Lệnh thanh toán trái ý muốn |
| `PUT /api/profile` | Có | Đổi hồ sơ/email/cấu hình |
| `DELETE /api/keys/{id}` | Có | Xóa khóa/API key |
| `POST /api/security/mfa/disable` | Có | Hạ mức bảo vệ tài khoản |
| `POST /api/token/refresh` dùng refresh-cookie | Có | Kích hoạt refresh/rotation, session churn hoặc rò token nếu response/CORS sai |
| `POST /logout` | Có | Logout CSRF hoặc gián đoạn trải nghiệm |
| `POST /login` dùng cookie | Có | Login CSRF, buộc nạn nhân dùng tài khoản attacker |
| OAuth/OIDC callback | Thay đổi trạng thái đăng nhập | Login CSRF, authorization-response mix-up nếu thiếu `state`/issuer binding |
| `GET /export?sendTo=...` nếu gây gửi dữ liệu | **Có nhưng thiết kế HTTP sai** | CSRF qua top-level navigation/ảnh/link |
| `GET /api/invoices` chỉ đọc | Theo thiết kế là không | Vẫn cần chống rò dữ liệu, CORS và authorization; GET tuyệt đối không có side effect nghiệp vụ |

### HTTP safe methods không được gây side effect

`GET`, `HEAD`, `OPTIONS` và `TRACE` được coi là safe methods về ngữ nghĩa HTTP, dù có thể có side effects kỹ thuật như logging. Không dùng `GET /approve`, `GET /logout` hay `GET /delete` để thực hiện **thay đổi nghiệp vụ** khi browser có thể tự điều hướng/tải hình ảnh.

**Không phụ thuộc tên HTTP method nếu gateway hỗ trợ override:** các header như `X-HTTP-Method-Override` hoặc tham số `_method` có thể khiến một POST form biến thành DELETE/PUT ở downstream. Chính sách CSRF phải áp trên **ngữ nghĩa method sau routing/override**, hoặc vô hiệu hóa override không cần thiết.

### “API chỉ nhận JSON” giúp gì?

Chỉ nhận đúng `application/json` và custom header buộc preflight có thể **giảm vector form CSRF**, nếu:

- Reject rõ `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`.
- Không dùng parser tự “đoán JSON” từ body `text/plain`.
- Không cấu hình credentialed CORS cho mọi origin.
- Không có một endpoint khác làm side effect bằng GET/form.

Đây là **một lớp defense**, không thay việc xác minh CSRF token/Origin theo risk policy. BFF có HTML forms vẫn cần cơ chế CSRF phù hợp.

## 6. Mô hình bảo vệ theo nhiều lớp

Một web app dùng cookie nên có nhiều lớp độc lập:

~~~mermaid
flowchart TD
    A["Browser gửi request cookie-authenticated"] --> B{"Method có thể thay đổi trạng thái?"}
    B -- "Không" --> R["Vẫn kiểm session/JWT, iss/aud/scope và quyền đọc"]
    B -- "Có" --> C{"Request context có được phép?<br/>Origin / Fetch Metadata policy"}
    C -- "Không" --> X["403 Forbidden: chặn trước side effect"]
    C -- "Có" --> D{"CSRF token hợp lệ và session-bound?"}
    D -- "Không" --> X
    D -- "Có" --> E{"Cookie/credential hợp lệ?"}
    E -- "Không" --> U["401 / login required"]
    E -- "Có" --> F{"Scope/role/tenant/object authorization?"}
    F -- "Không" --> X
    F -- "Có" --> G["Thực hiện nghiệp vụ, audit/idempotency"]
~~~

Sơ đồ diễn đạt **logic bảo vệ**, không quy định thứ tự implementation bắt buộc trong mọi framework. Các bước cần được thiết kế để **không side effect trước khi tất cả điều kiện đều đạt**. **Không có chuyện CSRF token đúng thì khỏi kiểm scope/audience hoặc quyền dữ liệu.**

### Ba lớp có tác dụng gì?

1. **Cookie attributes:** Giảm bề mặt cookie tự động gửi ngoài site, giới hạn khả năng đọc/cookie injection.
2. **Request provenance + CSRF token:** Giúp server phân biệt request được hình thành trong ngữ cảnh phiên hợp lệ với cross-origin request attacker điều khiển.
3. **Authentication + authorization + transaction checks:** Phải kiểm session/token, OAuth scope/audience, quyền trên object, anti-fraud, idempotency.

**Defense in depth quan trọng** vì có trình duyệt đặc biệt, endpoint legacy, subdomain bị chiếm, redirect flow hoặc một lớp bị cấu hình sai.

## 7. Synchronizer Token Pattern: CSRF token gắn với server session

Đây là cơ chế phổ biến khi ứng dụng có **session state phía server**, chẳng hạn BFF với `HttpSession` hoặc server session store phân tán.

### Luồng cơ bản

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant RP as Invoice Web / BFF
    participant DB as Session Store
    U->>B: Mở trang đổi email
    B->>RP: GET /settings với session cookie
    RP->>DB: Tra session, lấy/sinh CSRF random value
    DB-->>RP: Session + CSRF secret
    RP-->>B: HTML chứa hidden CSRF field (hoặc JSON bootstrap same-origin)
    U->>B: Nhấn Lưu
    B->>RP: POST /settings + session cookie + CSRF field
    RP->>DB: Kiểm CSRF field gắn với session hiện tại
    DB-->>RP: Token match / mismatch
    alt Hợp lệ và authorization đạt
        RP-->>B: Thao tác được thực hiện
    else Thiếu/sai token hoặc quyền
        RP-->>B: 403/401, không có side effect
    end
~~~

CSRF token được sinh bằng **CSPRNG**, khó đoán và gắn với phiên hiện tại. Server gửi token trong HTML `<input type="hidden">` hoặc qua **endpoint đọc same-origin được bảo vệ phù hợp**, browser gửi lại ở **form body** hoặc **custom request header**.

Ví dụ form:

~~~html
<form method="POST" action="/api/account/email">
  <input type="hidden" name="_csrf"
         value="unpredictable-session-bound-csrf-token">
  <label for="email">Email</label>
  <input id="email" name="newEmail" type="email" required>
  <button type="submit">Cập nhật email</button>
</form>
~~~

Kẻ tấn công ở `evil.invalid` có thể tạo form và khiến browser gửi cookie, nhưng **không tự đọc được hidden CSRF value từ Invoice Web** qua Same-Origin Policy nếu không có XSS/CORS leak. Server so sánh CSRF token với giá trị đã gắn phiên, nên request bị từ chối.

### Chỉ đặt token trong cookie có đủ không?

**Không**, nếu server chỉ nhìn thấy cookie và coi đó là CSRF proof. Cookie cũng tự gửi như session cookie. Theo synchronizer pattern, **token mà client phải chủ động đặt vào field/header** là phần chứng minh khác biệt; server đối chiếu với session.

~~~text
BAD:
  if Cookie["session"] valid and Cookie["csrf"] exists:
      allow POST

BETTER:
  verify Cookie["session"]
  verify request.header_or_form["_csrf"]
       against server-side csrf value bound to that session
~~~

### Token nên được tạo, lưu và xoay khi nào?

- Sinh **ít nhất một token đủ ngẫu nhiên cho mỗi session**; một số hệ thống chọn per-request token nếu UX/state handling cho phép.
- **Không dùng giá trị dễ đoán**: timestamp, user ID, email, JWT `sub`, một chuỗi static toàn ứng dụng.
- Gắn token với **session đã được xác thực**, tái sinh khi login/session rotation hoặc đổi tài khoản theo policy.
- Khi logout/invalidate session, CSRF token đi cùng session không được tiếp tục dùng.
- Nếu dùng per-request token, cần xử lý **multi-tab, back button và retry** để không vô tình tạo lỗi UX; không mặc định per-request tốt hơn trong mọi ứng dụng.
- Có thể thêm **token expiry** theo session, nhưng expiry tự nó không thay session binding.

### Không đưa CSRF token vào URL

~~~text
UNSAFE:
  POST /transfer?csrf=secret-value

BETTER:
  POST /transfer
  X-CSRF-Token: unpredictable-value

OR:
  POST body form:
    _csrf=unpredictable-value
~~~

URL/query string dễ đi vào browser history, reverse-proxy logs, analytics và `Referer`. Token cũng không nên xuất hiện trong redirect destination hoặc crash report. **CSRF token là anti-forgery value**, không phải access token để gửi tới Resource Server.

## 8. Double Submit Cookie: vì sao bản “naive” dễ sai?

Khi server không giữ CSRF token trong session, một mẫu thường gặp là **Double Submit Cookie**:

1. Server cấp một cookie mang giá trị CSRF.
2. JavaScript cùng origin đọc cookie CSRF (cookie này có thể **không `HttpOnly`**), rồi gửi cùng giá trị trong header `X-CSRF-Token`.
3. Server so cookie với header.

### Naive double submit

~~~http
POST /api/account/email HTTP/1.1
Host: invoice.example.test
Cookie: __Host-session=<session>; csrf=random-looking-value
X-CSRF-Token: random-looking-value
Content-Type: application/json

{"newEmail":"an@example.test"}
~~~

Nếu server **chỉ kiểm cookie CSRF và header bằng nhau**, một attacker có khả năng **cookie injection** qua subdomain, response splitting, ứng dụng khác dùng chung cookie scope hoặc bug trên một path có thể đặt giá trị attacker chọn, rồi khiến request gửi giá trị tương ứng. Đây là lý do **OWASP ưu tiên signed double-submit cookie gắn với session** khi dùng mẫu này.

### Signed double submit gắn session

Token có thể có cấu trúc minh họa:

~~~text
CSRF token:
  base64url(nonce) "." base64url(HMAC(serverSecret,
                                     sessionBinding || 0x00 || nonce))

Cookie:
  __Host-csrf=<csrf-token>; Path=/; Secure; SameSite=Lax

Request:
  X-CSRF-Token: <same-csrf-token>

Server:
  1. Xác định session từ cookie xác thực, phía server.
  2. So token trong header với cookie theo quy tắc an toàn.
  3. Tự tính HMAC(sessionBinding + nonce) bằng secret server-side.
  4. So MAC constant-time, kiểm cookie scope/Origin theo policy.
  5. Chỉ sau đó tiếp tục kiểm authentication/authorization.
~~~

**Session binding** phải là một giá trị **server-side riêng, khó đoán và ổn định trong phiên**, không phải raw password/access token được đưa vào CSRF value. Có thể dùng session-specific secret/ID nội bộ mà server biết để tính HMAC, **không cần phát giá trị binding ra browser**.

Một attacker có thể tự đặt cookie/header cùng một giá trị, nhưng **không thể tạo HMAC hợp lệ cho session nạn nhân** nếu không biết server secret và session binding. Nếu attacker đã có **XSS cùng origin** hoặc làm lộ server secret/session state, lớp CSRF này có thể bị vượt qua; cần bảo vệ các threat models đó riêng.

### Quy định cookie cho mẫu này

- **Cookie xác thực** `__Host-session` hoặc `__Host-access` vẫn nên là `HttpOnly; Secure`.
- **Cookie CSRF** dùng cho JS đọc có thể **không `HttpOnly`**; điều đó **không cho phép** bỏ bảo vệ XSS. Cookie này **không phải Bearer credential**.
- Ưu tiên `__Host-`, `Path=/`, **không `Domain`**, `Secure` để giảm subdomain cookie injection. Nếu SPA chạy trên origin khác, cần thiết kế CSRF delivery và CORS cụ thể, không nới `Domain` bừa bãi.
- Gắn CSRF token với session và hạn của session; khi user đăng nhập lại hoặc session được rotate, token cũ không còn hợp lệ.
- Không dùng HMAC secret yếu/hardcoded, và có versioning/key rotation cho CSRF signing secret nếu kiến trúc cần.

**Lưu ý:** Một số framework triển khai CSRF cookie theo cách khác hoặc có cơ chế mask token để chống BREACH. Không ghép công thức HMAC tự phát vào framework mà chưa kiểm token handler và threat model; ưu tiên sử dụng thư viện/security framework đã được bảo trì.

## 9. Origin, Referer và Fetch Metadata: lớp kiểm nguồn request

CSRF token là phòng tuyến cốt lõi. **Origin/Referer verification** và **Fetch Metadata headers** tạo lớp phòng vệ bổ sung, đặc biệt hữu ích ở gateway/BFF.

### Kiểm `Origin` theo allowlist chính xác

Ví dụ request hợp lệ:

~~~http
POST /api/account/email HTTP/1.1
Host: invoice.example.test
Origin: https://invoice.example.test
Cookie: __Host-session=<redacted>
X-CSRF-Token: <redacted>
~~~

Browser có thể gửi `Origin` cho các unsafe requests. Server nên so sánh **scheme + host + port** với allowlist trusted origins; không dùng substring:

~~~text
Trusted:
  https://invoice.example.test

UNTRUSTED:
  https://invoice.example.test.evil.invalid
  http://invoice.example.test
  https://promo.example.test
  https://evil.invalid?next=invoice.example.test
~~~

### Không lấy trusted origin từ `Host` tùy ý

Trong hạ tầng reverse proxy, `Host`/`X-Forwarded-Host` có thể do client ảnh hưởng nếu proxy không sanitize. Trusted origin nên lấy từ **cấu hình deployment** hoặc proxy headers chỉ khi **được trusted ingress thiết lập/overwrite và mạng backend bảo vệ**. Một phép kiểm:

~~~text
if Origin == "https://" + request.Host:
    accept
~~~

có thể sai nếu `Host` là giá trị attacker tự điều khiển hoặc proxy/rewrite biến đổi không được kiểm.

### Khi thiếu `Origin`

Origin có thể vắng trong một số ngữ cảnh/clients. `Referer` có thể dùng làm kiểm tra bổ trợ theo policy, nhưng cũng có thể bị ẩn bởi privacy settings/referrer policy. Không tự động chấp nhận **mọi request thiếu cả hai** nếu endpoint dùng cookie và có rủi ro CSRF.

Một chính sách mẫu:

~~~text
For state-changing browser endpoints using cookie auth:
  require valid session-bound CSRF token
  if Origin present: must match trusted origin allowlist
  if Origin absent:
      consider verified Referer as supplemental signal
      otherwise reject or require a stricter, well-defined fallback
~~~

Không thể dựa vào `Origin` để xác thực một client backend không thuộc browser: client như cURL có thể tự đặt header. Origin/Referer là **browser-context defense**, không thay client authentication, token signature hoặc network authorization.

### Fetch Metadata

Trình duyệt hiện đại có thể gửi các header:

~~~http
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
Sec-Fetch-User: ?1
~~~

`Sec-Fetch-Site` có các giá trị như `same-origin`, `same-site`, `cross-site` hoặc `none` theo ngữ cảnh. Một policy thường từ chối **cross-site requests tới state-changing cookie-authenticated endpoints**, trừ những luồng được thiết kế rõ (ví dụ một callback OIDC đã có xác thực state phù hợp).

**Không đồng nhất `same-site` với `same-origin`:** Nếu một sibling subdomain không được tin cậy, `Sec-Fetch-Site: same-site` **không đủ** để cho phép hành động. Dùng exact Origin/CSRF token và xem xét nguy cơ subdomain takeover.

### Fetch Metadata có thay CSRF token không?

Đây là một **lớp defense-in-depth**. Một số clients/browser không gửi các header này; có thể có endpoints cần cross-site navigation hoặc callback; policy phải xác định ngoại lệ chính xác. Không tạo một điều kiện “`Sec-Fetch-Site` thiếu ⇒ tự động allow” rồi dùng nó làm biện pháp duy nhất.

### Redirect chains và các ngoại lệ

OAuth/OIDC login/logout callbacks, payment-provider redirects và một số integrations phải được đánh giá **riêng**, vì cross-site navigation có thể là một phần hợp lệ của protocol. Không mở rộng ngoại lệ cho `/api/**` hoặc mọi POST; dùng **state/nonce, webhook signature, origin/CSRF token hoặc protocol-specific verification** tùy trường hợp.

## 10. CSRF với BFF và SPA: kiến trúc token an toàn không miễn CSRF

Một mô hình **Backend For Frontend (BFF)** thường giữ access/refresh token **phía server**, browser chỉ có **session cookie `HttpOnly`**:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser SPA
    participant BFF as BFF
    participant AS as OAuth Authorization Server
    participant RS as Resource Server
    B->>BFF: Request tới API BFF + session cookie + CSRF header
    BFF->>BFF: CSRF validation + session authorization
    BFF->>AS: Refresh access token nếu cần (server-side)
    AS-->>BFF: Access token
    BFF->>RS: Authorization: Bearer access token
    RS->>RS: Validate iss/aud/scope/token status/object permission
    RS-->>BFF: Business response
    BFF-->>B: Response qua same-origin
~~~

BFF giảm rủi ro **browser JavaScript trực tiếp đọc refresh/access tokens**, nhưng cookie BFF được browser tự gửi. Nếu attacker khiến browser gọi `POST /bff/payments` và BFF bỏ qua CSRF validation, BFF có thể **đích thân chuyển access token server-side tới RS** và thực hiện hành động bất hợp pháp.

**Cần chặn CSRF ở nơi cookie được chấp nhận** (BFF) **trước khi BFF gọi downstream RS**. RS vẫn kiểm Bearer token và quyền tài nguyên, nhưng nó không tự biết hành động BFF đang thực hiện có được user chủ động khởi tạo hay không.

### SPA bootstrap CSRF token

Một SPA có thể tải CSRF token qua response same-origin:

~~~http
GET /bff/csrf HTTP/1.1
Host: invoice.example.test
Cookie: __Host-session=<redacted>
~~~

~~~json
{
  "csrfToken": "<random-or-signed-session-bound-value>"
}
~~~

Rồi gửi token trong unsafe request:

~~~javascript
async function updateEmail(newEmail, csrfToken) {
  const response = await fetch("/bff/account/email", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken
    },
    body: JSON.stringify({ newEmail })
  });
  if (!response.ok) {
    throw new Error("Request was rejected");
  }
  return response.json();
}
~~~

Đây là **mã minh họa phía client**, không phải toàn bộ CSRF implementation. Server phải **tự sinh và validate** token theo session, áp Origin/Cookie/CORS policy, kiểm quyền và trả lỗi không có side effect. `GET /bff/csrf` không được để credentialed CORS mở với origin attacker; token response có thể dùng `Cache-Control: no-store`.

### Khi access token chỉ ở browser memory

Nếu JS **chủ động** thêm `Authorization: Bearer A1` vào fetch và server **không chấp nhận cookie làm auth**, một trang attacker ở origin khác không tự có A1 để thêm header. CSRF kiểu cookie không xảy ra theo cùng cơ chế, nhưng:

- XSS trên origin ứng dụng có thể dùng A1 hoặc gửi request được cấp quyền.
- Browser storage/reload/refresh token strategy cần thiết kế.
- Nếu một **endpoint khác** vẫn chấp nhận cookie (ví dụ `/refresh` hoặc `/logout`), endpoint đó vẫn là bề mặt CSRF.
- Nếu backend vô tình cho phép **cả Bearer header lẫn auth cookie**, cần thống nhất security model để không tạo đường bypass CSRF từ cookie.

**Không chọn `localStorage` làm giải pháp “chống CSRF” đơn giản**. Việc chuyển credential sang JS-readable storage đổi threat model sang token exfiltration/XSS, cần đánh giá toàn diện.

## 11. Login CSRF, OAuth/OIDC callback và `state`

**Login CSRF** có thể khiến nạn nhân đăng nhập vào **tài khoản do attacker kiểm soát**, sau đó nạn nhân nhập dữ liệu nhạy cảm vào tài khoản không phải của mình hoặc thực hiện tác vụ trong phiên sai.

### Kịch bản login CSRF

~~~text
1. Attacker tạo phiên đăng nhập cho account attacker.
2. Attacker tìm cách khiến browser nạn nhân thực hiện login callback
   hoặc login POST với credential/session do attacker sắp đặt.
3. Ứng dụng không kiểm state/CSRF/session binding đúng.
4. Browser nạn nhân bị gắn vào tài khoản attacker.
5. Nạn nhân tưởng đó là tài khoản mình và nhập dữ liệu.
~~~

Với **OAuth 2.0 Authorization Code + OIDC**, các lớp bảo vệ bao gồm:

- `state` khó đoán, gắn với **login transaction và browser session**, được kiểm tại callback và consume một lần.
- **PKCE** ràng buộc authorization code với `code_verifier`, giảm nguy cơ stolen code bị đổi; **PKCE không thay hoàn toàn `state` cho mọi CSRF/flow-binding scenarios**.
- **Issuer binding** theo OAuth/OIDC profile, nhất là multi-issuer, để chống AS mix-up/token substitution.
- **Redirect URI** được đăng ký và kiểm đúng; không dùng wildcard/open redirect.
- OIDC `nonce` (khi flow yêu cầu) để ràng buộc ID token với request và chống ID-token replay; **nonce không thay kiểm CSRF cho API business**.
- Kiểm ID token signature, `iss`, `aud`, `exp` và subject theo OIDC, rồi tạo/rotate local RP session an toàn.

### Cookie `SameSite` trong OAuth callback

OIDC front-channel redirect từ OP sang RP có thể là **cross-site top-level navigation**. Với **GET callback** và `SameSite=Lax`, cookie transaction có thể được gửi trong một số điều kiện; với `SameSite=Strict`, cookie cần cho correlation có thể không đến. Một số response-mode/flow dùng **form POST callback**, càng cần thiết kế cookie/session correlation và `state`/nonce phù hợp.

**Không giải quyết callback lỗi bằng cách đặt mọi auth cookie `SameSite=None` mà bỏ CSRF check.** Hãy thiết kế **cookie riêng cho login transaction**, state binding và chính sách phù hợp với response mode/OP thay vì nới rộng toàn bộ session policy.

### Callback không có nghĩa exempt mọi CSRF check

Một OIDC callback được thiết kế **cross-site** có thể cần ngoại lệ với **generic CSRF token middleware**, nhưng phải thay bằng **protocol-specific verification**: `state`, PKCE, issuer binding, one-time code, valid redirect URI, signed ID token khi có. Một exemption:

~~~text
csrf.ignore("/**")
~~~

là quá rộng và sai mục tiêu. Chỉ miễn đúng callback path/method đã phân tích và không biến endpoint này thành nơi user có thể tự chỉ định arbitrary session/token.

## 12. Refresh token cookie, logout và token revocation có CSRF không?

**Có**, tùy kiến trúc. Endpoint dùng cookie xác thực hoặc refresh token cookie có thể bị browser **tự gửi credential** trong cross-site request được phép.

### Refresh cookie CSRF

~~~http
POST /oauth/token/refresh HTTP/1.1
Host: invoice.example.test
Cookie: __Host-refresh=<redacted-refresh-token>
Origin: https://evil.invalid
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
~~~

Nếu `/refresh` cho phép cross-site POST mà không kiểm nguồn request, attacker có thể kích hoạt refresh/rotation dù **không đọc được refresh token**. Hậu quả có thể gồm **session churn**, phát token không mong muốn, gây reuse-detection khi client hợp pháp dùng refresh token cũ, hoặc nghiêm trọng hơn nếu response token bị lộ do CORS/session design sai.

**Refresh endpoint cần CSRF protection và response handling chặt** khi browser tự gửi cookie; không coi refresh token bí mật trong `HttpOnly` là đủ. Nếu browser SPA trực tiếp gọi AS token endpoint, cần tuân OAuth public-client profile và AS CORS/security policy; không tùy tiện dời confidential client secret vào frontend.

### Logout CSRF

Nếu `GET /logout` hủy session, attacker có thể khiến người dùng bị đăng xuất thông qua link/ảnh. Hậu quả thường là **gián đoạn phiên** nhưng có thể dẫn tới workflow security bugs hoặc login-confusion.

Khuyến nghị: **POST logout được bảo vệ CSRF**, invalidate session server-side, xóa cookie đúng name/domain/path; OIDC RP-Initiated/Front-Channel/Back-Channel Logout là **các luồng giao thức riêng** có quy tắc riêng, không nên dùng chung một GET logout không kiểm soát.

### Revocation và việc RS ngừng chấp nhận token là hai bước

Sau logout, BFF có thể gửi **RFC 7009 token revocation** cho refresh token/grant. Đây là **server-to-server** theo client authentication, không tự làm cho mọi RS JWT offline lập tức từ chối access token đã phát. Cần kiểm revoke propagation qua introspection/denylist nếu threat model yêu cầu.

**CSRF token không chống bản sao bearer token bị attacker sử dụng trực tiếp**, và token revocation không tự chứng minh browser request trước đó có được người dùng khởi tạo. Hai lớp bảo vệ bổ sung cho nhau.

## 13. Spring Security 6: bảo vệ CSRF mặc định cho ứng dụng có session

Với ứng dụng **Spring Boot 3.x / Spring Security 6.x** dùng **Servlet, OAuth2 Login/OIDC và session cookie**, Spring Security có CSRF protection tích hợp. Không nên tắt chỉ vì ứng dụng expose REST endpoints.

### 13.1. BFF hoặc server-rendered application

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class CookieAuthenticatedSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            // Với Servlet session web apps, giữ CSRF protection.
            .csrf(withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
~~~

Trong ví dụ, **Spring Security bảo vệ unsafe methods** theo matcher mặc định, thường `POST`/`PUT`/`PATCH`/`DELETE`. `GET`/`HEAD`/`OPTIONS`/`TRACE` được coi safe, vì vậy **không được thực hiện nghiệp vụ thay đổi dữ liệu bằng GET**.

**Đoạn code không phải toàn bộ cấu hình production**: cần OAuth2 client registration, trusted issuer/JWKS, proxy/HTTPS/cookie configuration, authorization rules, session storage, risk policy và testing. Việc gọi `.oauth2Login()` không tự xử lý access-token revocation hoặc audience validation tại downstream RS.

### 13.2. HTML form với CSRF token do framework cung cấp

Nếu dùng Thymeleaf/Spring MVC, một form có thể gửi CSRF parameter theo framework:

~~~html
<form th:action="@{/api/account/email}" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <label for="newEmail">Email mới</label>
  <input id="newEmail" name="newEmail" type="email" required>
  <button type="submit">Lưu</button>
</form>
~~~

Đây là cú pháp Thymeleaf sử dụng request attribute do Spring Security cung cấp: `${_csrf.parameterName}` và `${_csrf.token}`. Server không nên tự sinh một token từ `userId` hoặc `sessionId` dễ đoán mà không qua repository/handler đã được kiểm chứng.

**Tình huống âm tính:** Xóa hidden field, sửa token hoặc dùng token từ session khác → framework phải **từ chối trước khi controller thực thi thay đổi dữ liệu**.

### 13.3. SPA dùng cookie CSRF: lưu ý Spring Security 6

Với SPA muốn JavaScript đọc CSRF token trong cookie để gửi ở header, framework có:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

// Tư liệu minh họa một thành phần:
var repository = CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

Đặt CSRF cookie `HttpOnly=false` cho mục đích JavaScript đọc **không có nghĩa cookie xác thực cũng được phép đọc**. Auth/session/refresh token vẫn cần storage policy riêng, thường `HttpOnly`.

**Đặc biệt:** Trong Spring Security 6, CSRF token có thể được **deferred-load** và **mask (XOR) để giảm rủi ro BREACH**. Một SPA gửi **raw cookie token** trong header có thể cần **CSRF request handler phù hợp kiểu SPA** theo Spring Security reference của phiên bản đang sử dụng. **Chỉ cấu hình `CookieCsrfTokenRepository.withHttpOnlyFalse()` mà không xem handler/token loading có thể gây lỗi `403`**. Ưu tiên triển khai theo hướng dẫn framework hiện hành và test cả token bootstrap, login, logout, token rotation, reload và multi-tab.

### 13.4. Có được disable CSRF cho API không?

**Chỉ khi API thực sự không dựa vào credential browser tự gửi hoặc có giao thức thay thế được review.** Ví dụ:

- Một backend API chỉ nhận **`Authorization: Bearer ...` do client chủ động gửi**, không chấp nhận cookie/session làm auth, có thể có mô hình CSRF khác với browser BFF.
- Một **webhook** từ nhà cung cấp dùng HMAC signature/mTLS và không có browser session cookie có thể cần CSRF exception **chỉ cho endpoint đó**, đồng thời bắt buộc xác minh webhook signature, timestamp/replay theo contract.
- Một **OIDC callback** có `state`/PKCE/issuer binding riêng có thể cần exemption **đúng path/method** nếu generic middleware xung đột với cross-site response mode.

Không dùng:

~~~java
// SAI nếu ứng dụng vẫn dựa vào session/refresh cookie.
http.csrf(csrf -> csrf.disable());
~~~

chỉ vì “ứng dụng là REST API” hoặc “JWT đã ký rồi”. **Câu hỏi quyết định là browser có tự gửi credential tới endpoint không?**

## 14. Java 17: minh họa signed double-submit cookie gắn với phiên

Ví dụ dưới đây cho thấy cách tạo và kiểm một **CSRF value có HMAC ràng buộc vào session-side secret**, phù hợp với giải thích ở mục 8. Đây là **mô hình kỹ thuật tự chứa**, **không thay Spring Security CSRF repository/handler trong production**.

Giả định:

- Server có **HMAC secret mạnh**, quản lý bởi secret manager/KMS và không đưa vào client.
- Mỗi RP session có một **sessionBinding bí mật ngẫu nhiên**, server giữ trong session store; không phải raw session cookie hoặc email.
- Browser nhận cùng một CSRF token ở **cookie host-only** và gửi **bản sao chủ động** qua `X-CSRF-Token`.
- Session đã được xác thực, unsafe request được kiểm Origin/CORS/cookie policy riêng.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class SessionBoundCsrf {
    private static final SecureRandom RNG = new SecureRandom();
    private static final Base64.Encoder ENC =
        Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DEC =
        Base64.getUrlDecoder();

    private static final byte[] LABEL =
        "csrf-double-submit-v1".getBytes(StandardCharsets.US_ASCII);
    private static final int NONCE_BYTES = 16;
    private static final int HMAC_BYTES = 32; // HMAC-SHA-256

    // Server-side HMAC key và sessionBinding KHÔNG được gửi tới browser.
    static String issue(byte[] serverKey, byte[] sessionBinding)
            throws Exception {
        requireKeys(serverKey, sessionBinding);

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        byte[] mac = hmac(serverKey, sessionBinding, nonce);

        return ENC.encodeToString(nonce) + "." +
               ENC.encodeToString(mac);
    }

    static boolean valid(
            byte[] serverKey,
            byte[] sessionBinding,
            String csrfCookie,
            String csrfHeader) {
        if (serverKey == null || serverKey.length < 32 ||
            sessionBinding == null || sessionBinding.length < 16 ||
            csrfCookie == null || csrfHeader == null ||
            csrfCookie.length() > 256 || csrfHeader.length() > 256) {
            return false;
        }

        // Bản sao CHỦ ĐỘNG trong header phải khớp cookie CSRF.
        if (!MessageDigest.isEqual(
                csrfCookie.getBytes(StandardCharsets.US_ASCII),
                csrfHeader.getBytes(StandardCharsets.US_ASCII))) {
            return false;
        }

        String[] parts = csrfHeader.split("\\.", -1);
        if (parts.length != 2) return false;

        try {
            byte[] nonce = DEC.decode(parts[0]);
            byte[] providedMac = DEC.decode(parts[1]);
            if (nonce.length != NONCE_BYTES ||
                providedMac.length != HMAC_BYTES) {
                return false;
            }
            byte[] expectedMac =
                hmac(serverKey, sessionBinding, nonce);
            return MessageDigest.isEqual(providedMac, expectedMac);
        } catch (Exception invalidToken) {
            // Không cho request tiếp tục khi token sai/malformed.
            return false;
        }
    }

    private static byte[] hmac(
            byte[] serverKey, byte[] binding, byte[] nonce)
            throws Exception {
        // Length prefix loại bỏ ambiguity giữa các field.
        ByteBuffer payload = ByteBuffer.allocate(
            LABEL.length + 1 + Integer.BYTES +
            binding.length + nonce.length);
        payload.put(LABEL);
        payload.put((byte) 0);
        payload.putInt(binding.length);
        payload.put(binding);
        payload.put(nonce);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(serverKey, "HmacSHA256"));
        return mac.doFinal(payload.array());
    }

    private static void requireKeys(
            byte[] serverKey, byte[] binding) {
        if (serverKey == null || serverKey.length < 32 ||
            binding == null || binding.length < 16) {
            throw new IllegalArgumentException("Invalid secret material");
        }
    }

    private SessionBoundCsrf() {}
}
~~~

### Điều gì làm ví dụ này chống được naive double-submit?

Trong naive double-submit, attacker có thể **chọn một giá trị** và đặt cả cookie lẫn header nếu khai thác được cookie injection hoặc origin được nới lỏng. Ở mẫu HMAC:

~~~text
Victim session:
  binding = random server-side B_victim

Attacker picks:
  nonce = N_attacker

Attacker cannot compute:
  HMAC(serverSecret, B_victim || N_attacker)

Even if attacker makes cookie/header equal:
  valid() rejects forged MAC.
~~~

Nếu attacker **đã có token CSRF hợp lệ của chính session nạn nhân** qua XSS hoặc response leak, hệ thống cần xử lý như **session-origin compromise**; HMAC không giải quyết XSS.

### Những điều production còn phải thực hiện

1. **Validate request method, Origin/Fetch Metadata và Authorization** ở middleware; `valid()` chỉ kiểm một CSRF artifact.
2. Dùng cookie `__Host-csrf` với `Secure; Path=/` và không `Domain`; không để các proxy/backend chồng nhiều cookie cùng tên mà parser chọn tùy tiện.
3. Auth cookie và refresh cookie phải có `HttpOnly` phù hợp; CSRF cookie có thể JS-readable nhưng **không chứa token xác thực**.
4. `sessionBinding` được lưu/chia sẻ giữa replicas, **rotate** khi session đổi chủ thể hoặc logout; không nên raw session ID/credential trong CSRF value.
5. HMAC key có versioning và rotation; trong giai đoạn đổi key, chỉ cho phép các key versions đã review và giới hạn thời hạn.
6. Không log CSRF token, session binding, server HMAC key hoặc raw bearer/refresh tokens. Không đưa chúng vào query string.
7. Thiết lập CSRF token TTL theo session/lifecycle; server có thể thêm issuance timestamp có MAC nếu chính sách yêu cầu expiry độc lập.
8. Giới hạn input size, nội dung, encoding, chặn malformed/duplicate headers và cookie injection.
9. HMAC value phải được truyền đúng context bằng **custom header** cho SPA hoặc form field đã review; đừng chỉ xem cookie có mặt.
10. **Ưu tiên Spring Security/OWASP-reviewed implementation**. Đoạn code giúp hiểu HMAC session binding, không thay kiểm thử mật mã, integration và security framework.

### Cookie và header nên xuất hiện thế nào?

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: __Host-csrf=<signed-csrf-value>; Path=/; Secure; SameSite=Lax
Cache-Control: no-store
~~~

Client dùng JavaScript same-origin gửi:

~~~http
POST /api/account/email HTTP/1.1
Host: invoice.example.test
Cookie: __Host-session=<opaque>; __Host-csrf=<signed-csrf-value>
Origin: https://invoice.example.test
X-CSRF-Token: <signed-csrf-value>
Content-Type: application/json

{"newEmail":"new@example.test"}
~~~

Backend kiểm **HMAC/session binding**, không chỉ cookie/header equality; sau đó kiểm quyền người dùng. Token không cần được gửi cho RS downstream: BFF có thể dùng OAuth access token server-side riêng.

## 15. Những tình huống CSRF dễ bị bỏ qua trong hệ thống OAuth 2.0/OIDC

### 15.1. “JWT đã ký và scope hẹp” nhưng cookie tự gửi

~~~text
Cookie:
  __Host-access=valid signed JWT
JWT:
  iss=https://auth.example.test
  aud=invoice-api
  scope=invoice:write
  exp=soon

Browser cross-site POST:
  cookie automatically attached under matching browser policy

RS:
  JWT verified -> no CSRF check -> write succeeds
~~~

**JWT signature, scope và short lifetime không chứng minh user chủ động nhấn nút trong ứng dụng.** CSRF vẫn khả thi trong phần thời hạn token có quyền tương ứng.

### 15.2. Browser gửi cookie tới BFF; BFF dùng Bearer tới RS

Nếu BFF chỉ kiểm session cookie rồi gọi API bằng access token ở server, **BFF chính là điểm cần chặn CSRF**. Không chuyển trách nhiệm cho RS bằng cách nói “RS không dùng cookie”. RS có thể thấy mọi request đều đến từ BFF được ủy quyền; nó không biết cross-site browser có điều khiển thao tác hay không.

### 15.3. API hỗ trợ cả Bearer header và cookie

~~~text
Path A:
  Authorization: Bearer <token> -> JWT validation

Path B:
  Cookie: __Host-access=<token> -> JWT validation

Developer:
  "API only uses JWT, so CSRF disabled."
~~~

Đây là **sai lầm kiến trúc**: JWT trong cookie vẫn là **ambient auth**. Nếu API quyết định credential từ cookie khi không có header, request cross-site có thể đi qua Path B. Cần policy **credential priority, rejecting ambiguous credentials, CSRF protection cho cookie path** và test từng phương thức.

### 15.4. Subdomain bị chiếm

Một subdomain `promo.example.test` bị attacker kiểm soát có thể **same-site** với `invoice.example.test`. `SameSite=Strict` không chặn mọi request từ sibling same-site. Nếu auth cookie sử dụng `Domain=example.test`, attacker còn có thể có thêm khả năng cookie injection/overwriting tùy browser và scope.

Phòng vệ: auth cookie host-only với `__Host-`, exact Origin check, session-bound CSRF token, giới hạn CORS và quản trị DNS/subdomain takeover.

### 15.5. JSON endpoint chấp nhận `text/plain`

Một API quảng bá “chỉ JSON” nhưng backend lại parse mọi body thành JSON (kể cả `text/plain`) có thể bị HTML form tạo **simple request** mà không cần preflight. Test bằng chính form POST/các content types browser cho phép, không chỉ kiểm request có `Content-Type: application/json`.

### 15.6. “Có custom header là an toàn”

Nếu API CORS cho phép `https://*.example.test` và một sibling subdomain bị chiếm, attacker có thể dùng JS gửi custom header tới API với credentials nếu browser cookie policy cho phép. **Custom header không tự có tính bí mật**; cần Origin allowlist chặt và CSRF token ràng buộc session.

### 15.7. CSRF token bị cache chung

Nếu CDN/shared proxy cache HTML chứa CSRF token của session A rồi trả cho session B, sẽ có lỗi UX hoặc tệ hơn là **token sharing/leakage**. HTML bootstrap và CSRF-token JSON response phải có policy caching phù hợp (`Cache-Control: no-store` cho dữ liệu nhạy cảm), không chia sẻ token giữa users/tenants.

### 15.8. “Logout mọi nơi” và RFC 7009

CSRF trên `/logout` có thể khiến user bị đăng xuất không mong muốn; CSRF trên endpoint revoke/refresh có thể thay đổi grant state. Ngược lại, khi user logout thật, **access token đã sao chép** có thể vẫn gọi API tới expiry/revoke propagation. Cần kiểm CSRF, logout session, revoke grant/token và RS validation như **các ranh giới riêng**.

### 15.9. Cross-site OAuth callback được miễn quá rộng

Để OIDC redirect hoạt động, developer cho phép toàn bộ `/auth/**` bỏ CSRF, nhưng sau đó thêm `POST /auth/delete-sessions` trong cùng namespace. Đây là cách mở một endpoint nguy hiểm. CSRF exception phải **chỉ đúng callback path/method**, với `state`/issuer/PKCE và validation protocol riêng; không cho “mọi auth endpoint” bypass.

### 15.10. Webhook và native client

Một webhook server-to-server dùng HMAC/mTLS và **không dùng browser cookie** không có cùng threat model CSRF. Nhưng nó vẫn có **request forgery/replay** riêng: giả webhook signature, gửi lại event `jti`/timestamp, SSRF... Tương tự, ứng dụng native thường không dùng browser cookie theo cùng cách; nếu dùng embedded WebView/shared cookies thì lại có bề mặt browser-origin.

**Đừng áp CSRF token cho mọi request bất kể kiến trúc**, và cũng đừng bỏ CSRF chỉ vì tên endpoint là API. Quyết định theo **credential transport và trust boundary**.

## 16. Thiết kế tham chiếu: Invoice Web, BFF và Payment API

Giả định hệ thống:

~~~text
Trusted browser origin:
  https://invoice.example.test

Untrusted but same-site origin:
  https://promo.example.test

Authorization Server:
  https://auth.example.test

BFF:
  Invoice Web backend at invoice.example.test
  Cookie: __Host-session (HttpOnly, Secure, SameSite=Lax)
  CSRF: session-bound synchronizer token

Payment Resource Server:
  https://payments.example.test
  Access token from BFF Authorization: Bearer A1
  Expected aud=payments-api
  Required scope=payment:create
~~~

### Request hợp lệ

~~~mermaid
sequenceDiagram
    autonumber
    actor U as An
    participant B as Invoice Browser
    participant BFF as Invoice BFF
    participant RS as Payment API
    U->>B: Mở form thanh toán
    B->>BFF: GET /pay (session cookie)
    BFF-->>B: HTML kèm CSRF token theo session
    U->>B: Xem và xác nhận số tiền, người nhận
    B->>BFF: POST /bff/payments + session cookie + CSRF token
    BFF->>BFF: Validate CSRF, Origin, session và policy
    BFF->>RS: Bearer A1 + transaction payload
    RS->>RS: Validate token issuer/aud/scope/expiry và quyền nguồn tiền
    RS->>RS: Idempotency + payment state/transaction checks
    RS-->>BFF: Kết quả
    BFF-->>B: Kết quả thanh toán
~~~

**Điểm quan trọng:** BFF kiểm CSRF để xác định **browser request được tạo trong ngữ cảnh app**; Payment API kiểm token và quyền nghiệp vụ để quyết định **A1 có quyền xử lý giao dịch này**. Hai tầng bổ sung nhau.

### Request CSRF bị chặn

~~~mermaid
sequenceDiagram
    autonumber
    participant E as promo.example.test bị takeover
    participant B as Browser nạn nhân
    participant BFF as Invoice BFF
    participant RS as Payment API
    E-->>B: HTML form POST /bff/payments
    B->>BFF: Cookie session + form data, không có CSRF token đúng
    Note over B,BFF: SameSite có thể xem là same-site
    BFF->>BFF: Origin khác allowlist và/hoặc CSRF token sai
    BFF-->>B: 403 Forbidden
    Note over BFF,RS: Không có request downstream tới Payment API
~~~

Attacker có thể **không đọc được response** và vẫn thực hiện được form POST. Defense cần bảo đảm **Payment API chưa được gọi** khi BFF phát hiện thiếu CSRF token, thay vì BFF gửi request rồi chỉ che response.

### Cần kiểm cả nghiệp vụ thanh toán

Ngay cả khi request có CSRF token hợp lệ, hệ thống vẫn cần:

- **Phân quyền:** An có quyền đối với tài khoản nguồn và beneficiary.
- **Transaction binding:** Amount/currency/beneficiary không bị thay sau khi user xác nhận.
- **Idempotency:** Retry cùng payment intent không tạo hai lần thanh toán.
- **Step-up:** Nếu rủi ro cao, OIDC `auth_time`/ACR và reauthentication policy được kiểm độc lập.
- **Access token:** `iss`, `aud`, `exp`, `scope` và sender binding/revocation theo thiết kế.

CSRF token **không thay chữ ký phê duyệt giao dịch**, không chống mọi XSS và không chứng minh user thực sự nhìn thấy số tiền nào nếu UI/app đã bị compromise.

## 17. Ma trận kiểm thử CSRF khi dùng cookie token

Môi trường giả định:

~~~text
Victim:
  https://invoice.example.test
  __Host-session cookie: Secure, HttpOnly, SameSite=Lax
  CSRF token: tied to RP session, submitted in header/form

Attacker:
  https://evil.invalid (cross-site)
  https://promo.example.test (same-site, cross-origin)

Sensitive endpoint:
  POST /bff/payments
  POST /api/account/email
  POST /bff/token/refresh
  POST /logout

Guard:
  CSRF token validation + Origin/Fetch Metadata policy
  authentication + authorization + business checks
~~~

| Ca kiểm thử | Input/tình huống | Kết quả kỳ vọng |
|---|---|---|
| **Request hợp lệ** | Same-origin POST, session cookie và CSRF token đúng | Qua CSRF, tiếp tục authorization |
| **Không có cookie xác thực** | POST chứa CSRF token nhưng thiếu session | 401/deny, không thực hiện thao tác |
| **Thiếu CSRF token** | Cookie session hợp lệ, POST không có token | 403, không side effect |
| **CSRF token sai** | Session hợp lệ, header sai token | 403 |
| **CSRF token từ user khác** | Token từ session B gửi cùng cookie session A | 403, phải có session binding |
| **CSRF token cũ sau logout** | Session A đã invalidate | 401/403, không chấp nhận session/token cũ |
| **Đăng nhập tài khoản khác cùng browser** | CSRF token của session cũ dùng với phiên mới | 403, token/session rotation có hiệu lực |
| **CSRF token thiếu entropy** | Dựa vào `userId`/timestamp dễ đoán | Test an toàn không đạt; dùng CSPRNG |
| **HMAC server secret sai** | Token do attacker tự ký | 403 |
| **Naive double-submit cookie injection** | Attacker đặt cookie/header cùng chuỗi tự chọn | Server không được allow; signed+session-bound HMAC chặn |
| **CSRF cookie bị chồng tên** | Hai cookie cùng name/path/domain khác nhau | Xử lý nhất quán/reject ambiguous, không chọn giá trị attacker |
| **`__Host-` cookie không có Secure** | Browser hỗ trợ prefix từ chối cookie | Test cookie setup không đạt |
| **`__Host-` cookie có Domain** | Cố mở scope sang `example.test` | Browser hỗ trợ prefix từ chối; sửa configuration |
| **Cookie Auth chỉ `HttpOnly`** | POST cross-site khi cookie vẫn được gửi | Không coi HttpOnly là CSRF defense |
| **Cookie Auth chỉ `Secure`** | POST cross-site HTTPS | Không coi Secure là CSRF defense |
| **`SameSite=None; Secure`** | Trang `evil.invalid` submit form | Cookie có thể được gửi; CSRF guard phải từ chối |
| **Explicit `SameSite=Lax` cross-site POST** | `evil.invalid` submit form POST | Browser chuẩn thường không gửi cookie; CSRF guard vẫn có |
| **`SameSite=Lax` cross-site GET** | Attacker dẫn user vào `GET /delete` | Endpoint phải không có side effect, hoặc thiết kế lại |
| **`SameSite=Strict` từ sibling** | `promo.example.test` submit request | Không chỉ dựa SameSite; exact Origin/token guard |
| **Same-site nhưng khác origin** | `promo.example.test` gọi Invoice API | CSRF/Origin policy phải coi là origin không đáng tin |
| **Scheme khác nhau** | `http://promo...` → `https://invoice...` | Test schemeful same-site, Secure/TLS và redirect policy |
| **HTML form urlencoded** | Attacker gửi form POST | Nếu cookie được gửi, request vẫn tới server; guard chặn |
| **HTML form multipart** | Attacker gửi multipart POST | Không bypass CSRF bằng content type |
| **HTML form text/plain** | Backend lỡ parse nội dung như JSON | Reject unsupported content type hoặc CSRF guard |
| **API chỉ cho JSON** | Text/plain chứa chuỗi giống JSON | Không auto-parse thành state-changing command |
| **Request JSON với preflight** | Cross-site `fetch` tự đặt custom header | CORS chỉ allow trusted origins; không bypass CSRF |
| **CORS phản chiếu Origin** | Server trả ACAO bằng bất kỳ origin | Test fail, sửa CORS allowlist |
| **CORS credentials quá rộng** | Evil origin được phép đọc credentialed response | Security test fail, tránh data/CSRF token leaks |
| **CORS chặn response nhưng request đã chạy** | Cross-origin form gửi thành công | Test phải kiểm side effect, không chỉ `fetch` báo CORS error |
| **Origin đúng** | `Origin=https://invoice.example.test` | Qua Origin check, **vẫn** kiểm CSRF token |
| **Origin có host suffix giả** | `invoice.example.test.evil.invalid` | Reject exact origin |
| **Origin sai scheme** | `http://invoice.example.test` | Reject nếu trusted origin yêu cầu HTTPS |
| **Origin `null`** | Sandboxed iframe hoặc context đặc biệt | Reject/áp policy rõ, không mặc định tin |
| **Thiếu Origin** | User agent không gửi Origin | Áp policy fallback rõ, vẫn bắt buộc CSRF token |
| **Referer bị ẩn** | Referrer-Policy cắt Referer | Không fail-open nếu thiếu cả nguồn và proof |
| **Host giả** | Client đặt `Host`/forwarded header bất thường | Trusted origin không được suy từ input chưa sanitize |
| **`Sec-Fetch-Site: cross-site`** | Cookie-authenticated unsafe POST | Reject trừ protocol exception hợp lệ và kiểm riêng |
| **`Sec-Fetch-Site: same-site` từ sibling** | Sibling origin không tin cậy | Không allow chỉ vì same-site |
| **Fetch Metadata vắng** | Client/browser cũ | Dùng CSRF/Origin fallback, không để trống security |
| **GET gây side effect** | `GET /payments/approve` | Test phải fail; chuyển sang unsafe method có bảo vệ |
| **Method override** | POST `_method=DELETE` | Phải kiểm effective method hoặc disable override |
| **Login CSRF** | Attacker cố ép session người dùng sang tài khoản attacker | `state`/session binding/login CSRF check chặn |
| **OAuth `state` sai** | Callback có state không thuộc transaction | Reject, không tạo RP session |
| **OAuth `state` replay** | Callback hợp lệ bị dùng lại | Reject one-time state, code exchange one-time |
| **PKCE verifier sai** | Code còn hạn nhưng không khớp verifier | Token endpoint reject, không nhầm CSRF của API |
| **OIDC nonce sai** | ID token không khớp nonce của transaction | Reject theo flow/profile |
| **Callback issuer mix-up** | Response từ OP B trong transaction OP A | Reject bằng issuer binding/profile |
| **OIDC form POST callback** | Cross-site legitimate POST từ OP | Ngoại lệ chỉ đúng callback + state/issuer/PKCE checks |
| **Wildcard OAuth callback exemption** | Generic ignore `/auth/**` | Test fail nếu endpoint business trong path được miễn |
| **Refresh cookie CSRF** | Cross-site POST `/refresh` với cookie tự gửi | Reject nếu thiếu CSRF/protocol proof |
| **Refresh token rotation race** | Hai POST refresh cùng session | Phân biệt legitimate concurrency và abuse; atomic family policy |
| **Logout GET** | Trang attacker gắn link/ảnh `/logout` | Không được hủy phiên qua GET không bảo vệ |
| **Logout POST thiếu CSRF** | Cookie session hợp lệ, không có anti-forgery token | Reject theo browser endpoint policy |
| **BFF downstream leak** | CSRF bị phát hiện sau khi BFF đã gọi RS | Test fail; guard phải trước side effect |
| **JWT signature hợp lệ** | Cookie chứa JWT `iss/aud/scope/exp` đúng | Vẫn yêu cầu CSRF ở state-changing cookie route |
| **Access token hết hạn** | CSRF đúng nhưng JWT `exp` đã qua | Reject, CSRF không thay authentication |
| **Sai audience/scope** | CSRF đúng, bearer không dành Invoice API | Reject theo OAuth authorization |
| **Cross-tenant request** | Cookie/CSRF đúng nhưng invoice thuộc tenant khác | Reject theo object-level authorization |
| **BFF app có XSS** | Attacker JS chạy trong origin ứng dụng | CSRF token có thể bị lợi dụng; cần chống XSS riêng |
| **CSRF token bị log** | Proxy ghi hidden/header token | Redaction test fail |
| **CSRF token cache chung** | CDN trả token session A cho B | No shared cache, token/session isolation |
| **Safari/Firefox/Chrome privacy modes** | Third-party cookie/chính sách khác nhau | Chạy browser integration tests; không suy từ một browser |
| **Iframe/clickjacking** | Attacker chồng UI để dụ click | Có CSP frame-ancestors/anti-clickjacking riêng |
| **Webhook có chữ ký** | Server-to-server POST không có browser cookie | CSRF exception đúng path; verify webhook HMAC/mTLS/replay |
| **Mobile WebView** | App dùng shared cookie store | Đánh giá CSRF như browser context nếu cookie tự gửi |

### Test bằng trình duyệt thật, không chỉ cURL

Một HTTP client như cURL **không có cùng cookie/SameSite/SOP/CORS behavior** như browser. Cần test:

~~~text
Browser integration test:
  1. Login to invoice.example.test.
  2. Visit evil.invalid origin in second tab.
  3. Submit urlencoded/multipart/text-plain forms.
  4. Observe actual browser Cookie header behavior.
  5. Assert Invoice API state did NOT change.
  6. Repeat with promo.example.test (same-site, cross-origin).
  7. Test with SameSite=Lax, Strict and None profiles.
  8. Verify CSRF guard rejects missing/wrong/session-mismatched token.
  9. Verify legitimate SPA/form requests still work.
 10. Verify logout, refresh and OAuth callback separately.
~~~

Không cần log raw session cookie để kiểm; dùng **correlation ID, server-side request test marker và kiểm database state** đã được quyền truy cập. Test quan trọng nhất là **không có side effect**, không chỉ response status.

## 18. Vận hành: logging, giám sát và xử lý sự cố CSRF

### Metrics nên đo

| Chỉ số | Điều cần biết | Không nên lưu |
|---|---|---|
| `csrf_rejected_total` theo route/method/reason | Lượng request không có/sai token | Raw CSRF token hoặc session ID |
| `origin_mismatch_total` | Cross-origin attempts và lỗi app config | Raw arbitrary Origin làm metric label |
| `fetch_metadata_block_total` | Request cross-site bị chặn | Thông tin người dùng/PII trong label |
| `csrf_success_by_endpoint` | Luồng hợp lệ còn hoạt động | Token value trong logs |
| `oauth_state_validation_failure_total` | Login CSRF/flow mix-up hoặc cookie issues | Full authorization code/state |
| `refresh_csrf_reject_total` | Refresh cookie bị kích hoạt sai nguồn | Refresh token |
| `session_rotation_total` | Login/logout/session regeneration | Raw cookie |
| `cors_preflight_denied_total` | Origin/method/header không được phép | Arbitrary attacker-controlled Origin làm label vô hạn |
| `proxy_host_validation_error_total` | Host/forwarded-header configuration sai | Proxy credentials |
| `bff_downstream_request_after_csrf_failure_total` | BFF có bug thực hiện side effect trước khi chặn | Access token |

**Không log** raw `Authorization`, `Cookie`, `Set-Cookie`, `X-CSRF-Token`, OAuth `state`, `nonce`, authorization code hoặc refresh token trong APM/error reports. Log cần đủ để điều tra **sự kiện** (request ID, route, policy decision), không tái tạo credential.

### Nếu phát hiện CSRF thành công

1. **Ngăn thao tác nguy hiểm:** Vô hiệu/bảo vệ endpoint, tắt legacy GET side effects hoặc bắt buộc CSRF check tại gateway/BFF.
2. **Xác minh sự kiện thực tế:** Kiểm audit giao dịch, thay đổi dữ liệu và những requests có Origin/Fetch Metadata bất thường; không suy toàn bộ từ CORS lỗi ở client.
3. **Khắc phục side effects:** Hủy giao dịch hoặc rollback theo business policy, báo user khi thích hợp.
4. **Kiểm cookie/CORS:** `SameSite`, `Domain`, `Path`, `HttpOnly`, `Secure`, exact origin allowlist và subdomain ownership.
5. **Kiểm CSRF token lifecycle:** Entropy, session binding, rotation, CDN cache, token disclosure và correct middleware order.
6. **Xử lý session/token:** Invalidate compromised sessions, revoke grants/tokens nếu xuất hiện token theft, kiểm RS revocation propagation.
7. **Rà XSS/subdomain takeover:** Nếu attacker đã chạy script cùng origin, CSRF token không phải biện pháp khắc phục duy nhất.
8. **Viết regression tests:** Browser end-to-end, API authz, OIDC callbacks, refresh/logout, multi-region session store.

### Security SLO và tradeoff

CSRF protection nên **fail closed trước khi có side effect**. Nếu session store/CSRF token validator không sẵn sàng, không cho unsafe request qua chỉ để tăng availability. Một chiến lược fallback cần được security review; đối với payment/security settings, **không có CSRF proof hợp lệ thì không thực hiện**.

### Dữ liệu đầu vào luôn chưa được tin

Ngoài token, attacker có thể điều khiển `Origin` ở non-browser clients, `Referer` trong một số công cụ, URL/query, method override và body. Browser JS bị giới hạn trong một số header bởi user agent, nhưng **server vẫn phải kiểm session-bound CSRF token và authorization**, không tin một header đơn độc như quyền admin.

## 19. Bài tập tình huống: BFF dùng cookie JWT và subdomain bị takeover

Công ty có các thành phần:

~~~text
Invoice Web / BFF:
  https://invoice.example.test

Marketing landing page:
  https://promo.example.test

Authorization Server:
  https://auth.example.test

Payment API:
  https://payments.example.test

Invoice session:
  __Host-session=<opaque>
  Secure; HttpOnly; SameSite=Strict; Path=/

CSRF token:
  __Host-csrf=<signed-session-bound-value>
  Secure; SameSite=Strict; Path=/

Invoice BFF POST /bff/payments:
  dùng session cookie để xác định user;
  nếu hợp lệ, BFF dùng access token server-side để gọi Payment API.

Sự cố:
  promo.example.test bị attacker takeover.
~~~

Attacker kiểm soát trang `promo.example.test`, cố gửi form POST vào `invoice.example.test/bff/payments` để chuyển tiền. Do cùng scheme và registrable domain, browser có thể phân loại request là **same-site nhưng cross-origin**.

**Câu 1. `SameSite=Strict` có bảo đảm browser không gửi Invoice session cookie khi trang promo gửi request không?**

**Không.** `SameSite` được đánh giá theo **site**, không phải chính xác **origin**. Hai subdomains cùng site có thể khiến cookie vẫn được gửi tới hostname đích, dù trang nguồn là origin khác.

**Câu 2. Vì cookie có `HttpOnly`, attacker trên promo không đọc được session cookie. CSRF đã bị chặn chưa?**

**Chưa đủ.** CSRF không cần đọc cookie: attacker chỉ cần browser tự gửi cookie trong request tới Invoice BFF nếu cookie policy cho phép.

**Câu 3. Cookie dùng prefix `__Host-` có tác dụng gì?**

Giúp áp host-only cookie, `Secure` và `Path=/`; giảm khả năng sibling subdomain đặt cookie cho host nạn nhân. Nhưng **không tự ngăn** trang sibling tạo request mà browser gửi host-only cookie của Invoice tới Invoice endpoint.

**Câu 4. Có thể dựa `Sec-Fetch-Site: same-site` để cho request qua không?**

**Không nên**, nếu sibling subdomain không thuộc cùng trust boundary. Cần exact Origin allowlist, CSRF token gắn session và các kiểm soát khác.

**Câu 5. Nếu attacker tạo form POST `application/x-www-form-urlencoded` và BFF chỉ cấu hình CORS cho Invoice origin, request có đến BFF không?**

**Có thể.** HTML form thường có thể tạo cross-origin request mà không cần CORS permission để browser **gửi**. CORS chủ yếu kiểm việc JavaScript đọc response/preflight; không thay CSRF check.

**Câu 6. BFF dùng access token trong server memory để gọi Payment API. Có thể nói Payment API không dùng cookie nên toàn hệ thống không có CSRF không?**

**Không.** Browser → BFF vẫn xác thực bằng cookie tự động gửi. BFF phải kiểm CSRF **trước khi** phát downstream request. Payment API kiểm access token và quyền nghiệp vụ riêng.

**Câu 7. Attacker biết một CSRF token của chính tài khoản attacker, có dùng nó với session của An được không?**

**Không**, nếu CSRF token được **ký HMAC và ràng buộc vào session của An** hoặc là synchronizer token lưu trong session. Token của session khác không khớp binding.

**Câu 8. Nếu BFF chỉ kiểm `Cookie.csrf == X-CSRF-Token` mà không kiểm HMAC/session binding, có rủi ro gì?**

Đó là naive double-submit. Khi attacker có **cookie injection** hoặc một origin được phép gửi header không đúng policy, họ có thể đặt một cặp giá trị bằng nhau không thuộc phiên. Cần signed double-submit có session binding hoặc synchronizer token.

**Câu 9. User bấm logout nhưng refresh token còn trong cookie và endpoint `/refresh` thiếu CSRF guard. Có thể có chuyện gì?**

Nếu cookie/endpoint vẫn còn hiệu lực, attacker có thể kích hoạt refresh/rotation hoặc gây session churn, và nếu CORS/response/storage còn lỗi có thể dẫn tới rủi ro nghiêm trọng hơn. Logout phải invalidate session, xóa cookie đúng scope, revoke token/grant theo policy và bảo vệ endpoint refresh.

**Câu 10. Nếu JWT cookie còn `exp` 30 giây, có đủ an toàn cho chuyển tiền không?**

**Không.** Attacker có thể tạo request ngay lập tức. TTL ngắn chỉ thu hẹp replay window, không chặn CSRF. Cần token/Origin check, transaction binding, scope, ownership và idempotency.

**Câu 11. Nếu Invoice Web có XSS, signed CSRF token có cứu được không?**

**Không thể bảo đảm.** Script chạy cùng origin có thể lấy CSRF value từ DOM/cookie readable hoặc gửi same-origin requests qua browser có cookie auth. Cần chống XSS/CSP, input/output encoding, dependency security và session controls.

**Câu 12. OAuth `state` hợp lệ trong lần đăng nhập có giúp các POST đổi email sau đó tự chống CSRF không?**

**Không.** `state` ràng buộc **một OAuth authorization transaction**. Sau khi login, các unsafe requests đến BFF cần CSRF protection riêng và authorization checks. Không dùng `state` làm CSRF token lâu dài cho mọi nghiệp vụ.

**Câu 13. Nếu request có CSRF token đúng nhưng user không có `payment:create` scope thì xử lý thế nào?**

**Từ chối.** CSRF proof chỉ nói request có ngữ cảnh phiên phù hợp; nó không cấp scope/role. Payment API vẫn phải kiểm issuer, audience, scope và quyền thao tác cụ thể.

**Câu 14. Nếu user gửi cùng một request thanh toán hợp lệ hai lần vì bấm liên tiếp, CSRF token có ngăn double payment không?**

**Không.** CSRF token có thể hợp lệ ở cả hai request. Payment service cần **idempotency key**, business transaction state và giới hạn thực thi một lần theo payment intent.

**Câu 15. Có thể xử lý bằng cách đưa access token từ cookie sang `localStorage` không?**

Không nên làm đơn giản như vậy. Nếu client tự đặt Bearer header và API không dùng cookie, vector CSRF cổ điển có thể giảm, nhưng **JS-readable token có rủi ro bị đánh cắp bởi XSS**. Nên so sánh kiến trúc BFF + HttpOnly cookie + CSRF token với token-in-memory/sender-constrained approaches theo threat model thay vì chỉ chuyển nơi lưu.

## 20. Checklist production: CSRF với cookie token

1. **Kiểm credential transport:** Endpoint có chấp nhận session, access token JWT hoặc refresh token từ cookie tự động gửi không?
2. **Nhận diện mọi unsafe endpoints:** POST/PUT/PATCH/DELETE, login, logout, refresh, revoke, bảo mật tài khoản và business actions?
3. **GET không có side effect nghiệp vụ:** Không xác nhận thanh toán, xóa tài khoản hay logout qua GET?
4. **Cookie auth có `Secure; HttpOnly`:** Bảo vệ transport và JavaScript access, nhưng **không coi đó là CSRF proof**?
5. **SameSite được cấu hình explicit:** `Strict`/`Lax`/`None; Secure` theo luồng thật, không dựa browser default?
6. **Hiểu same-site vs same-origin:** Sibling subdomain được coi là trusted hay attacker-controlled; không tin `same-site` nếu không đủ?
7. **Host-only cookie/prefix:** Ưu tiên `__Host-` với `Path=/; Secure`, không `Domain` cho credential khi phù hợp?
8. **CSRF synchronizer token:** Token CSPRNG ràng buộc session, trong form field/header, server validate trước side effect?
9. **Hoặc signed double-submit đúng:** HMAC có session binding, so cookie/header và MAC, không dùng naive equality-only?
10. **CSRF token lifecycle:** Sinh/rotate khi login, đổi chủ thể/session, logout; expiry và multi-tab/back-button đã test?
11. **Không lộ CSRF token:** Không truyền qua URL, Referer, logs, CDN/shared cache, analytics hoặc unsafe CORS?
12. **Origin allowlist exact:** So scheme/host/port với trusted config; không substring/suffix hoặc phản chiếu arbitrary Origin?
13. **Proxy trust đúng:** `Host`/`Forwarded`/`X-Forwarded-*` được sanitize bởi trusted ingress, không dùng giá trị attacker tự gửi?
14. **Origin/Referer missing policy:** Có quy tắc fallback rõ mà không fail-open với cookie unsafe requests?
15. **Fetch Metadata defense:** Block cross-site unsafe requests khi không có lý do hợp lệ; không cho sibling same-site tự động tin cậy?
16. **CORS chặt:** Không reflect arbitrary Origin với credentials, kiểm preflight, methods/headers và cache Vary đúng theo kiến trúc?
17. **Content-Type nghiêm:** Không parse `text/plain`/form/multipart như JSON lén; không có đường method override bỏ check?
18. **Spring Security CSRF bật khi dùng session cookie:** Không disable chỉ vì API trả JSON/JWT; cấu hình matcher đúng?
19. **SPA token handler đúng phiên bản:** Nếu dùng `CookieCsrfTokenRepository`, tính đến deferred/masked CSRF token, raw header và bootstrap?
20. **BFF guard trước downstream:** Không gọi Resource Server hoặc thực hiện DB write trước khi CSRF token/Origin/session valid?
21. **OAuth/OIDC login CSRF:** `state` per transaction + PKCE + issuer binding + redirect URI/nonce/profile validation?
22. **Callback exemption rất hẹp:** Chỉ path/method cần thiết, có protocol checks tương đương; không ignore toàn bộ `/auth/**`?
23. **Refresh/logout CSRF:** Các endpoints dùng cookie tự động gửi có anti-forgery defense phù hợp?
24. **Authn/authz vẫn độc lập:** JWT signature/`iss`/`aud`/`exp`/scope, tenant/owner/object và risk policy được kiểm?
25. **CSRF không thay idempotency:** Payments/orders có idempotency key, transaction confirmation và anti-fraud riêng?
26. **Chống XSS song song:** HttpOnly không ngăn script same-origin gửi request, CSP/encoding/Trusted Types khi phù hợp?
27. **Test nhiều browser/context:** SameSite, third-party cookie blocking, top-level navigation, forms, subdomains, iframe, redirects và multi-tab?
28. **Bảo vệ monitoring:** Đo CSRF rejects/Origin mismatch/state failures, không log cookie, JWT, CSRF token hoặc PII không cần?
29. **Có runbook incident:** Khi phát hiện CSRF, khóa endpoint, xác minh side effects, xử lý giao dịch, revoke/rotate session/token nếu cần?
30. **Đánh giá lại sau thay kiến trúc:** Chuyển từ SPA Bearer sang BFF cookie, thêm refresh cookie hoặc mở CORS mới phải làm lại threat model?

**Ghi nhớ:** **CSRF xảy ra khi browser tự gửi cookie xác thực trong một request do bên khác điều khiển.** Cookie `HttpOnly`, chữ ký JWT và HTTPS **không tự chứng minh request được người dùng chủ động khởi tạo**. `SameSite` giảm nhiều trường hợp CSRF nhưng **same-site không đồng nghĩa same-origin**, đặc biệt với subdomain không tin cậy. Khi dùng cookie token/session, hãy kết hợp **synchronizer CSRF token hoặc signed double-submit ràng buộc phiên**, Origin/Fetch Metadata/CORS policy chặt, cookie attributes phù hợp và **kiểm authorization trước side effect**. OAuth `state` bảo vệ login transaction, còn business endpoints, refresh và logout có **CSRF requirements riêng**.

### Chuẩn và tài liệu tham khảo

- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet:** synchronizer token, signed double-submit cookie, Origin/Referer validation, SameSite, defense-in-depth và CSRF test patterns.
- **OWASP Session Management Cheat Sheet:** cookie `Secure`/`HttpOnly`/`SameSite`, session lifecycle, fixation và logout.
- **OWASP HTML5 Security Cheat Sheet / XSS Prevention Cheat Sheet:** giới hạn của browser storage, XSS và bảo vệ các token trong JavaScript.
- **OWASP OAuth 2.0 Cheat Sheet:** PKCE, `state`, issuer mix-up, token handling và OAuth security.
- **RFC 6265 và RFC 6265bis (HTTP State Management Mechanism):** cookie scope/attributes, Domain/Path/SameSite và hành vi browser; kiểm phiên bản tiêu chuẩn/trình duyệt áp dụng thực tế.
- **RFC 9110 — HTTP Semantics:** safe methods, idempotency và ý nghĩa các HTTP methods.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** OAuth clients, authorization code, state, access/refresh tokens và request validation.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** ràng buộc authorization code với verifier; chống code interception, không thay CSRF defense cho mọi API.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer binding chống authorization server mix-up.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** OAuth threat model, token theft, redirect/callback/CSRF và refresh token security.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer transport, token theft/replay và Resource Server validation.
- **RFC 7009 — OAuth 2.0 Token Revocation:** khác với browser session logout hoặc CSRF protection.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm trạng thái access token opaque/reference; không tự chứng minh browser request provenance.
- **OpenID Connect Core 1.0:** OIDC `state`/`nonce`, ID token validation và authentication session binding.
- **Spring Security Reference — CSRF Protection:** `CsrfFilter`, `CsrfTokenRepository`, `CookieCsrfTokenRepository`, XOR/masked CSRF tokens, SPA integration và Spring Security 6 configuration.
- **Fetch Metadata Request Headers (W3C/Web Platform documentation):** `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest` và resource isolation policy.
- **MDN Web Docs — Set-Cookie, SameSite cookies, CORS và Fetch API:** browser behavior, cross-origin credentials và cookie restrictions.
