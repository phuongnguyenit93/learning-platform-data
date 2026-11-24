# SameSite behavior

**`SameSite`** là thuộc tính của **HTTP cookie** hướng dẫn trình duyệt **khi nào được đính kèm cookie vào một HTTP request xét theo ngữ cảnh same-site hoặc cross-site**. Ba chế độ thường dùng là **`Strict`**, **`Lax`** và **`None`**. Thuộc tính này đặc biệt quan trọng với **session cookie**, các ứng dụng sử dụng cookie-based authentication, và các luồng đăng nhập chuyển hướng qua **OAuth 2.0/OpenID Connect (OIDC)**.

Bài **“SameSite behavior”** thuộc chương **Browser security** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Phạm vi gồm mô hình tin cậy và vòng đời token, sự khác nhau giữa **JWT/opaque token**, **access/refresh/ID token**, xác thực và phân quyền OAuth 2.0/OIDC, claims/scope/audience, lưu trữ token và các biện pháp chống credential bị lộ hoặc phát lại. Bài này tập trung vào **cookie được trình duyệt tự gửi**, không đánh đồng `SameSite` với chữ ký JWT, scope hay việc thu hồi token ở Authorization Server.

> **Nguyên tắc:** `SameSite` là lớp **giảm rủi ro CSRF theo ngữ cảnh site**, không phải tường lửa chung cho mọi request, không phải cơ chế chống XSS và không thể thay thế **CSRF token, kiểm tra `Origin`, phương thức HTTP đúng, xác minh session và kiểm tra audience/scope**. Một cookie có `SameSite=Strict` vẫn có thể bị gửi từ **sibling subdomain cùng site** nhưng khác origin.

## 1. Vì sao `SameSite` tồn tại?

Trình duyệt thường tự đính kèm cookie phù hợp với request, ngay cả khi request được **khởi phát từ một trang khác**. Điều này tiện cho đăng nhập, nhưng tạo ra tấn công **Cross-Site Request Forgery (CSRF)** nếu server nhầm “trình duyệt gửi session cookie” với “người dùng thực sự chủ động thao tác”.

Ví dụ giả định:

- Người dùng đã đăng nhập `https://wallet.example.test` bằng cookie `__Host-session`.
- Người dùng mở trang `https://malicious.example` do attacker kiểm soát.
- Trang đó khiến trình duyệt gửi một form POST tới `https://wallet.example.test/transfers`.
- Nếu session cookie tự được gửi và API **không kiểm tra CSRF/Origin**, server có thể xử lý một giao dịch không do user chủ động cho phép.

`SameSite=Lax` hoặc `Strict` thường **ngăn cookie được gửi trong cross-site POST** như ví dụ. Nhưng nó **không** thay kiểm soát server-side: attacker có thể ở một **sibling subdomain** cùng site, hoặc có thể lợi dụng **GET thực hiện thay đổi trạng thái**, hoặc trình duyệt có chính sách/giới hạn khác nhau.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User Browser
    participant E as malicious.example
    participant W as wallet.example.test

    U->>W: Login hợp lệ
    W-->>U: Set-Cookie: session=...; SameSite=Lax; Secure; HttpOnly
    U->>E: Truy cập trang do attacker quản lý
    E-->>U: HTML form auto-submit tới wallet
    U->>W: Cross-site POST /transfers
    Note over U,W: Cookie Lax thường bị loại khỏi cross-site POST
    W->>W: Kiểm tra session, Origin và CSRF token
    W-->>U: Từ chối request thiếu session/CSRF
~~~

Mục tiêu của `SameSite` là giảm **ambient authority**: trình duyệt không nên tự mang credential cookie vào mọi tình huống cross-site.

## 2. Từ vựng phải phân biệt: site, origin và domain

Cách hiểu đúng phụ thuộc vào việc xác định **same-site** hay **same-origin**.

### Origin

Một **origin** được xác định bởi bộ **scheme + host + port**:

~~~text
https://app.example.test
    scheme = https
    host   = app.example.test
    port   = 443 (mặc định)
~~~

Hai URL chỉ **same-origin** khi scheme, host và port giống nhau. Khác port cũng là **cross-origin** dù cùng hostname.

### Site (schemeful same-site)

Với hành vi cookie hiện đại, **site** thường dựa vào **scheme + registrable domain (eTLD+1)**, có xét **Public Suffix List (PSL)**. Ví dụ:

~~~text
https://app.example.test      -> site: https://example.test
https://api.example.test      -> site: https://example.test
https://blog.example.test     -> site: https://example.test

http://app.example.test       -> site: http://example.test
https://app.other.test        -> site: https://other.test
~~~

`https://app.example.test` và `https://api.example.test` là **same-site nhưng cross-origin**. `http://app.example.test` và `https://app.example.test` khác scheme, nên trong cách tính **schemeful same-site**, chúng là **cross-site** dù hostname giống hệt.

**PSL quan trọng**: với `shop.example.co.uk` và `api.example.co.uk`, registrable domain thường là `example.co.uk`, không phải `co.uk`. Cookie không được tùy ý đặt `Domain=co.uk` chỉ vì cả hai hostname kết thúc bằng chuỗi đó.

### Bảng so sánh

| Trang khởi phát | Đích nhận request | Same-origin? | Same-site? |
|---|---|---|---|
| `https://app.example.test` | `https://app.example.test/api` | **Có** | **Có** |
| `https://app.example.test` | `https://api.example.test` | **Không**, khác host | **Có** |
| `https://app.example.test` | `https://app.example.test:8443` | **Không**, khác port | **Có** |
| `https://app.example.test` | `http://app.example.test` | **Không**, khác scheme | **Không** trong schemeful model |
| `https://app.example.test` | `https://blog.example.test` | **Không** | **Có** |
| `https://app.example.test` | `https://attacker.other.test` | **Không** | **Không** |

Đây là **mô hình giải thích cho origin/site thông thường**. Với `localhost`, địa chỉ IP, opaque origins, sandboxed iframe và chuỗi nested browsing contexts, trình duyệt áp dụng quy tắc đặc thù. Không tự tính site trong JavaScript bằng thao tác cắt hostname theo dấu chấm.

## 3. Cookie được gửi khi thỏa nhiều điều kiện đồng thời

`SameSite` chỉ là **một** trong những bộ lọc cookie. Trình duyệt cân nhắc nhiều điều kiện trước khi gửi:

1. Cookie đã được lưu và **chưa hết hạn** theo `Max-Age`/`Expires`.
2. Request target khớp phạm vi **host-only/Domain** của cookie.
3. Request path phù hợp `Path` (nhưng **Path không phải ranh giới bảo mật**).
4. Cookie `Secure` chỉ được gửi qua kênh an toàn theo quy tắc trình duyệt.
5. Quy tắc **`SameSite`** cho phép request trong ngữ cảnh site hiện tại.
6. **Browser privacy policy**, cookie partition/third-party blocking và storage restrictions có thể tiếp tục hạn chế.
7. Với `fetch`/XHR, còn có **credentials mode** của API trình duyệt.

~~~mermaid
flowchart TD
    A["Browser chuẩn bị HTTP request"] --> B{"Cookie tồn tại và chưa hết hạn?"}
    B -->|"Không"| NO["Không gắn cookie"]
    B -->|"Có"| C{"Domain/host + Path khớp?"}
    C -->|"Không"| NO
    C -->|"Có"| D{"Secure/scheme phù hợp?"}
    D -->|"Không"| NO
    D -->|"Có"| E{"SameSite cho phép ngữ cảnh request?"}
    E -->|"Không"| NO
    E -->|"Có"| F{"Credentials mode/privacy policy cho phép?"}
    F -->|"Không"| NO
    F -->|"Có"| YES["Cookie đủ điều kiện được gửi"]
~~~

Vì vậy, **`SameSite=None` không có nghĩa mọi request chắc chắn mang cookie**; **`SameSite=Lax` không có nghĩa fetch cross-origin tự động có cookie**, và **`HttpOnly` không quyết định SameSite**.

## 4. `SameSite=Strict`: chỉ gửi trong same-site context

Ví dụ cookie:

~~~http
Set-Cookie: __Host-session=<OPAQUE_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=3600
~~~

**`Strict`** yêu cầu request có **same-site context**. Điều đó thường giúp tránh cookie session tự đi theo:

- Người dùng nhấp link từ `https://news.other.test` đến `https://app.example.test`.
- Form POST trên trang cross-site gửi vào `https://app.example.test`.
- Ảnh/iframe/fetch từ trang cross-site truy cập endpoint của app.

**Nhược điểm UX:** ngay cả **top-level GET navigation** từ site khác tới app cũng có thể **không mang Strict cookie ở request đầu tiên**. Một người đã đăng nhập nhấp link từ email/news có thể thấy một trang dường như chưa xác thực; các request same-site kế tiếp có thể lại mang cookie tùy ngữ cảnh.

### Strict không đồng nghĩa same-origin

Nếu user đang trên `https://blog.example.test` và trang gọi `https://app.example.test`, hai địa chỉ **same-site** mặc dù **cross-origin**. Khi cookie app khớp host/path và những điều kiện khác, `Strict` **không tự loại cookie vì khác subdomain**.

**Do đó Strict không đủ để chặn CSRF từ sibling subdomain không đáng tin.** Muốn ngăn, cần kiểm tra **exact Origin** ở các endpoint có thay đổi trạng thái, CSRF token và chính sách tin cậy giữa các subdomain.

## 5. `SameSite=Lax`: same-site và một phần top-level navigation

Ví dụ:

~~~http
Set-Cookie: __Host-session=<OPAQUE_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=3600
~~~

`Lax` cho phép cookie với:

1. **Same-site requests** đáp ứng các điều kiện cookie khác.
2. Một số **cross-site top-level navigations** dùng **phương thức HTTP an toàn**, phổ biến nhất là **GET** do nhấp link hoặc chuyển hướng điều hướng chính.

`Lax` thông thường **không gửi** cookie cho:

- **Cross-site form POST** (top-level POST là unsafe method).
- Cross-site `fetch()` hoặc XHR không phải top-level navigation.
- Cross-site subresources như `<img>`, `<script>`.
- Cross-site **iframe navigation**, vì không phải top-level browsing context.

### Hai câu dễ nhầm

- “Lax cho phép cross-site GET” — **chỉ trong ngữ cảnh top-level navigation an toàn**, không phải mọi fetch GET, ảnh GET hay iframe GET.
- “Lax chặn mọi CSRF” — **sai**; nếu API có **GET làm thay đổi trạng thái**, một cross-site top-level GET vẫn có thể mang cookie.

**GET/HEAD nên được triển khai an toàn theo HTTP semantics, không dùng để chuyển tiền, xóa tài khoản hay đổi email.** Mọi state-changing action nên dùng phương thức phù hợp, CSRF protection và authorization.

## 6. `SameSite=None`: cho phép cross-site nhưng bắt buộc `Secure`

Ví dụ:

~~~http
Set-Cookie: __Host-oidc-tx=<RANDOM_CORRELATION_ID>; Path=/; Secure; HttpOnly; SameSite=None; Max-Age=300
~~~

`None` **không áp hạn chế gửi cookie dựa trên same-site context**, nên cookie có thể đi theo cross-site POST, iframe, subresource hoặc fetch nếu **các điều kiện cookie, fetch credentials và browser privacy** đều cho phép.

**`SameSite=None` yêu cầu `Secure` trong các trình duyệt hiện đại.** Ví dụ sau không nên sử dụng vì cookie có thể bị trình duyệt từ chối:

~~~http
Set-Cookie: session=demo; SameSite=None; HttpOnly
~~~

`Secure` không tự động tạo HTTPS cho website và **không mã hóa giá trị cookie trong database/local storage**. Ngoại lệ cho `localhost` có thể khác giữa trình duyệt/môi trường dev; cấu hình production phải dùng **HTTPS thực, TLS xác minh hợp lệ**.

### Không mặc định đặt toàn bộ session cookie thành None

`None` mở rộng khả năng gửi session cookie **trong các request do site khác khởi phát**, tăng bề mặt CSRF khi backend không phòng vệ đầy đủ. Chỉ chọn khi **có nhu cầu cross-site rõ ràng**, như OIDC `response_mode=form_post` cần transaction correlation cookie, hoặc widget cross-site được phê duyệt.

Ngay cả với `None; Secure`, trình duyệt có thể **chặn third-party cookies** hoặc partition storage. Nó **không bảo đảm** SSO qua iframe hay tracking cookie hoạt động trên mọi browser.

## 7. Không khai báo SameSite không tương đương `Lax` tường minh

Nếu server đặt:

~~~http
Set-Cookie: __Host-session=<OPAQUE_SESSION_ID>; Path=/; Secure; HttpOnly; Max-Age=3600
~~~

mà **không có `SameSite`**, nhiều trình duyệt áp dụng mặc định **`Lax`**, nhưng **mặc định không phải hợp đồng chung bất biến trên mọi browser**.

Một số browser, đặc biệt trong cơ chế tương thích của Chromium, có **Lax-by-default / Lax-allowing-unsafe**: với cookie **không khai báo SameSite**, **cross-site top-level POST** có thể vẫn mang cookie nếu cookie mới được thiết lập **khoảng hai phút trước đó**.

| Thiết lập | Cross-site top-level POST | Kết luận |
|---|---|---|
| `SameSite=Lax` **tường minh** | Thông thường **không gửi** | Dùng làm policy mong muốn |
| **Omit SameSite** trong browser Lax-by-default | Có thể được gửi trong “recently set cookie” compatibility window | **Không được dựa vào hành vi này** |
| `SameSite=None; Secure` | Có thể gửi nếu browser/policy cho phép | Phải bổ sung CSRF/Origin |
| `SameSite=Strict` | Không gửi trong cross-site context | Có thể ảnh hưởng sign-in/cross-site navigation |

**Không viết business logic dựa vào “mới login dưới 120 giây nên form_post chạy được”**. Đây là đặc điểm triển khai để giảm breakage, không phải thiết kế bảo mật hoặc giao thức OIDC đáng tin cậy.

**Khuyến nghị:** khai báo **`SameSite` tường minh**, rồi kiểm thử cross-site interaction thật trên các browser/versions mục tiêu.

## 8. Ma trận cookie behavior theo ngữ cảnh request

Giả sử cookie thuộc host `https://app.example.test`, các điều kiện **host/path, HTTPS, cookie lifetime và browser privacy** đều thỏa. Với **Lax tường minh**, bảng sau mô tả hành vi thường mong đợi.

| Trang/ngữ cảnh khởi phát | Request đến app | `Strict` | `Lax` | `None; Secure` |
|---|---|---|---|---|
| Same-origin app | `fetch("/api/me")` GET | **Gửi** | **Gửi** | **Gửi** |
| Same-site sibling `https://blog.example.test` | Top-level GET tới app | **Gửi** | **Gửi** | **Gửi** |
| Same-site sibling qua HTTPS | Form POST vào app | **Gửi** | **Gửi** | **Gửi** |
| Cross-site `https://other.test` | Top-level GET vào app | **Không** | **Gửi** | **Gửi** |
| Cross-site `https://other.test` | Top-level form POST vào app | **Không** | **Không** | **Có thể gửi** |
| Cross-site `https://other.test` | `<img src="...">` GET tới app | **Không** | **Không** | **Có thể gửi** |
| Cross-site `https://other.test` | `<iframe src="...">` vào app | **Không** | **Không** | **Có thể gửi** |
| Cross-site `https://other.test` | `fetch()` GET/POST với `credentials: "include"` | **Không** | **Không** | **Có thể gửi** |
| `http://blog.example.test` | Request tới HTTPS app (schemeful khác) | **Không** | Tùy top-level safe navigation | **Có thể gửi** |

**“Có thể gửi”** nghĩa là SameSite không cản, **không cam kết** browser sẽ gửi; còn các điều kiện khác như third-party blocking, partition, Fetch credentials, cookie Domain/Path vẫn cần đúng. Trong thực tế redirect chain, iframe ancestors và browser differences có thể ảnh hưởng tính toán site context; kiểm thử trong browser thật.

## 9. Top-level navigation khác `fetch`, subresource và iframe

Đây là khác biệt quyết định hành vi `Lax`.

~~~mermaid
flowchart TD
    A["Request xuất phát từ site KHÁC"] --> B{"Top-level navigation?"}
    B -->|"Có"| C{"HTTP method safe, thường GET?"}
    C -->|"Có"| D["SameSite=Lax có thể được gửi"]
    C -->|"Không, ví dụ POST"| E["SameSite=Lax bị loại"]
    B -->|"Không: fetch, img, iframe..."| E
    A --> F["SameSite=Strict bị loại nếu cross-site"]
    A --> G["SameSite=None không hạn chế theo site, vẫn cần Secure/privacy/credentials"]
~~~

### Một vài tình huống cụ thể

- Nhấp link `https://search.other.test` → `https://app.example.test/account`: đây là **cross-site top-level GET**. Lax có thể đi theo; Strict thường không.
- Trang attacker gắn `<img src="https://app.example.test/delete?id=1">`: **subresource GET**, Lax/Strict không được gửi do cross-site context. Nhưng **endpoint GET có side effect vẫn là bug** kể cả khi cookie bị chặn trong trường hợp này.
- Trang attacker đưa `location.href = "https://app.example.test/delete?id=1"`: **top-level GET**, Lax có thể được gửi. Điều này cho thấy **Lax không bảo vệ unsafe GET**.
- Trang attacker tự gửi HTML `<form method="POST" ...>` tới app: **cross-site top-level POST**, Lax tường minh thường bị loại.
- Một `iframe` bên trong trang cross-site tải app: **iframe navigation**, không phải top-level; Lax thường không được gửi.

**Redirect nuance:** một chuỗi redirect có thể ảnh hưởng method và việc đánh giá cross-site context. HTTP **303** thường chuyển tiếp bằng GET, còn **307/308** giữ nguyên method; **302** có xử lý lịch sử khác nhau. **Không cố thao túng redirect để “đánh lừa SameSite”**; thiết kế authentication flow theo giao thức và test cả redirect chain.

## 10. Same-site không có nghĩa trusted-origin

Rủi ro đáng chú ý là **sibling subdomain takeover hoặc XSS ở một subdomain**.

~~~text
https://app.example.test       // hệ thống thanh toán
https://blog.example.test      // blog/CMS thuộc cùng registrable domain
https://legacy.example.test    // ứng dụng cũ ít được kiểm soát

Cả ba có site:
    https://example.test

Nếu blog bị XSS/subdomain takeover:
    Request từ blog tới app là same-site nhưng cross-origin.
    SameSite=Strict hoặc Lax KHÔNG tự chặn cookie app.
~~~

Attacker có thể khiến browser gửi form POST **từ sibling subdomain**. Cookie `__Host-session` của `app.example.test` vẫn được gắn vào request **tới app** nếu các điều kiện khác thỏa, dù **blog không thể đọc cookie host-only**.

### Biện pháp đúng

1. Kiểm tra **`Origin` chính xác** cho state-changing browser requests, ví dụ chỉ nhận `https://app.example.test`, không nhận mọi `*.example.test`.
2. Dùng **CSRF token** gắn với session hoặc phương án double-submit có ràng buộc mật mã phù hợp.
3. Tách ứng dụng không đáng tin sang **registrable domain khác** khi có thể.
4. Dùng cookie **host-only** (không có `Domain`), `Secure`, `HttpOnly` và prefix `__Host-`.
5. Không khai báo CORS rộng theo wildcard subdomain.
6. Kiểm soát XSS/CSP, subdomain takeover và third-party JavaScript.

**`SameSite=Strict` không định nghĩa trust boundary theo origin.** Đó là một trong những điểm quan trọng nhất khi thiết kế micro-frontends và nhiều ứng dụng dưới cùng domain.

## 11. SameSite, CSRF và XSS là các vấn đề khác nhau

| Rủi ro | Hành vi | SameSite giúp gì? | Còn cần gì? |
|---|---|---|---|
| **Cross-site form CSRF** | Website lạ khiến browser gửi POST có session cookie | Lax/Strict thường ngăn cookie | CSRF token, Origin check, HTTP methods |
| **Same-site sibling CSRF** | Blog bị chiếm gửi POST tới app | **Không đủ**, vì same-site | Exact Origin + CSRF, host isolation |
| **XSS trong chính app** | Script độc hại chạy **same-origin** | **Không ngăn request được xác thực** | Output encoding, CSP, template safety, hạn JS |
| **Cookie theft via JS** | Script đọc `document.cookie` | SameSite **không ngăn** | `HttpOnly` cho session cookie, XSS defenses |
| **CSRF qua unsafe GET** | Attacker mở top-level GET có side effect | Lax **có thể mang cookie** | GET phải safe, CSRF/method policy |
| **Token replay tại RS** | Attacker có Bearer access token rồi gọi API | SameSite **không bảo vệ token trong Authorization header** | Token validation/PoP, audience, revocation |
| **OIDC login CSRF** | Callback của authorization flow không được bind | SameSite chỉ hỗ trợ cookie routing | `state`, PKCE, nonce/issuer/redirect binding |

**`HttpOnly` ngăn JavaScript đọc cookie qua `document.cookie`, nhưng script XSS đang chạy cùng origin vẫn có thể thực hiện `fetch`/form request được browser gắn cookie**. Vì vậy không được tuyên bố “HttpOnly + Strict chặn toàn bộ XSS”.

## 12. `SameSite` khác `Same-Origin Policy` và CORS

Một ví dụ thực tế:

~~~text
Frontend: https://app.example.test
Backend:  https://api.example.test

=> SAME-SITE (https://example.test)
=> CROSS-ORIGIN (khác host)
~~~

Với cookie được server API đặt trên `api.example.test`, `SameSite=Lax` **không cản** request từ frontend sang API vì hai bên same-site. Nhưng `fetch` có **credentials mode mặc định là `same-origin`**, nên request cross-origin đó **không tự gửi cookie**.

Cần chủ đích:

~~~javascript
const response = await fetch(
  "https://api.example.test/account",
  {
    method: "GET",
    credentials: "include" // Cross-origin cookie, nếu policy cho phép.
  }
);

if (!response.ok) {
  throw new Error("Request failed");
}
~~~

Server API có thể phải trả CORS hợp lệ cho frontend được phê duyệt:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không dùng** `Access-Control-Allow-Origin: *` khi trả credentialed CORS response.

### Những điều CORS không làm

- CORS chủ yếu quyết định **script cross-origin có được đọc response và thực hiện các loại request theo cơ chế browser**. Nó **không thay thế CSRF**.
- Một **simple form POST** có thể được browser gửi mà không cần JavaScript đọc response hay preflight theo cách của `fetch`. Server vẫn có thể **thực hiện side effect trước khi script bị chặn đọc response**.
- `credentials: "include"` **không override `SameSite=Lax/Strict`** trong cross-site context, không override cookie expiration/Domain/Path, và không vượt browser third-party cookie blocking.
- CORS có thể cho phép **cross-origin same-site** fetch, nhưng **CSRF Origin policy** phải cho phép một cách có chủ đích, không tự động tin mọi sibling subdomain.

## 13. Cookie `Domain`, `Path`, `Secure` và `HttpOnly`

Ví dụ cookie host-only an toàn cho app:

~~~http
Set-Cookie: __Host-session=<OPAQUE_RANDOM_SESSION_ID>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=3600
~~~

Nếu bỏ `Domain`, cookie là **host-only**: `app.example.test` có thể nhận cookie, `blog.example.test` không được nhận trực tiếp. **Nhưng** browser vẫn có thể gửi cookie đó **tới app** khi request khởi phát từ blog vì same-site.

Nếu cấu hình:

~~~http
Set-Cookie: session=<OPAQUE_ID>; Domain=example.test; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

cookie có thể được gửi tới các subdomain phù hợp như `app.example.test` và `blog.example.test`. Điều đó **làm tăng phạm vi credential**; không nên dùng chỉ để “dễ tích hợp” nếu các ứng dụng có trust level khác nhau. Dấu chấm đầu `Domain=.example.test` là cú pháp cũ, thường được browser bỏ qua; **không tạo ranh giới khác**.

| Thuộc tính | Giới hạn gì? | Không làm được gì? |
|---|---|---|
| `Domain` / host-only | Host nào được nhận cookie | Không xác thực site khởi phát request |
| `Path` | Path nào được browser gắn cookie | **Không** là access control giữa ứng dụng cùng host |
| `Secure` | Gửi qua HTTPS/secure transport theo browser rule | Không ngăn XSS/CSRF, không tự mã hóa cookie |
| `HttpOnly` | JavaScript không đọc cookie trực tiếp | Không ngăn XSS gửi request có cookie |
| `SameSite` | Cross-site request context được phép | Không thay Origin, CSRF token, authz |
| `Max-Age` / `Expires` | Thời hạn cookie client-side | Không tự hủy session server-side hoặc refresh token |

**Không lưu raw refresh token/JWT access token trực tiếp vào cookie chỉ vì đã bật Secure/HttpOnly/SameSite** mà chưa xác định threat model, session binding, rotation, domain, CSRF và lifetime. Một mô hình **BFF session cookie + token được giữ server-side** thường dễ quản trị hơn với ứng dụng web cần truy cập OAuth API.

## 14. Cookie prefix `__Host-` giúp hạn chế domain scoping

Với các browser hỗ trợ cookie prefixes, `__Host-` yêu cầu:

1. Cookie được đặt từ **HTTPS/secure origin**.
2. Có `Secure`.
3. Có `Path=/`.
4. **Không có `Domain`**.

~~~http
Set-Cookie: __Host-session=<OPAQUE_ID>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ví dụ **sai**:

~~~http
Set-Cookie: __Host-session=<OPAQUE_ID>; Domain=example.test; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Browser hỗ trợ prefix sẽ **không chấp nhận** `__Host-` cookie có `Domain`. Điều này giúp phòng một số lỗi cookie injection/overwriting từ subdomain. Nó **không** ngăn same-site requests từ sibling subdomains và không đảm bảo mọi browser cũ thực thi prefix như nhau.

Các prefix khác:

- **`__Secure-`**: yêu cầu `Secure` và secure origin nhưng không cấm `Domain`.
- **`__Host-Http-`** (trên browser hỗ trợ): kết hợp hạn chế `__Host-` với `HttpOnly` để khẳng định cookie đến từ `Set-Cookie`, không từ JavaScript.

**Prefix là defense-in-depth**. Server vẫn phải validate session ID, rotate session sau login/privilege change, có expiration/revocation và áp dụng Origin/CSRF policy.

## 15. OAuth 2.0/OIDC Authorization Code + PKCE: callback GET

Một web app dùng OIDC Authorization Code + PKCE:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant RP as app.example.test
    participant OP as login.idp.other.test

    U->>RP: Bắt đầu đăng nhập
    RP-->>U: Set-Cookie session=...; SameSite=Lax
    RP-->>U: 302 /authorize?client_id=...&state=...&code_challenge=...
    U->>OP: Top-level navigation sang OP
    OP->>U: Login + consent
    OP-->>U: 302 Location: https://app.example.test/callback?code=...&state=...
    U->>RP: Top-level cross-site GET /callback
    Note over U,RP: Lax cookie có thể đi theo GET callback
    RP->>RP: Check state, issuer, redirect URI, PKCE transaction
    RP->>OP: POST /token + code_verifier (server-to-server)
    OP-->>RP: ID token + access token
    RP->>RP: Verify ID token; rotate/create app session
~~~

Với callback **`response_mode=query`** (top-level GET), session/correlation cookie `SameSite=Lax` thường phù hợp, miễn là:

- Cookie có phạm vi host/path đúng và còn hạn.
- Transaction có **`state` ngẫu nhiên** gắn với browser session, có **PKCE S256** và đúng issuer/redirect URI.
- OP callback **không** dựa vào `SameSite` như biện pháp chống login CSRF duy nhất.
- RP xác minh ID token `iss`/`aud`/`exp`/`nonce` khi đã dùng nonce và các yêu cầu OIDC khác.
- Không log authorization code, `code_verifier`, ID/access/refresh token.
- Session ID được **rotate** hoặc tạo mới sau login nếu thích hợp.

**`SameSite=Strict` có thể làm mất correlation/session cookie ngay tại callback cross-site GET**; nếu RP dựa cookie đó để tra `state`, flow có thể thất bại. Đừng tắt `state`/PKCE để “chữa” lỗi cookie.

## 16. OIDC `response_mode=form_post`: callback POST là tình huống khác

Một OP có thể trả kết quả authorization response bằng **form POST** từ trang của OP sang callback của RP.

~~~http
POST /oidc/callback HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded

code=<AUTHORIZATION_CODE>&state=<RANDOM_STATE>
~~~

Khi đây là **cross-site top-level POST** từ OP sang RP:

- `SameSite=Strict`: không gửi cookie session/correlation dựa trên cross-site request.
- `SameSite=Lax` tường minh: thông thường **không gửi** cookie vì POST không phải safe method.
- `SameSite=None; Secure`: cookie **có thể** được gửi theo browser privacy/transport/host rules.

### Thiết kế không phải mở toàn bộ session cookie thành None

Một cách tiếp cận là dùng **cookie giao dịch OIDC riêng**, TTL rất ngắn:

~~~http
Set-Cookie: __Host-oidc-tx=<STRONG_RANDOM_TRANSACTION_ID>; Path=/; Secure; HttpOnly; SameSite=None; Max-Age=300
~~~

Cookie này nên **chỉ dùng để liên kết authorization transaction**, không cấp quyền truy cập API. RP so `state` từ callback với state lưu server-side gắn transaction, xác minh issuer, PKCE và OIDC; sau đó **xóa cookie giao dịch** và tạo/rotate **app session `SameSite=Lax`/`Strict` theo policy**.

**Đối với nhiều tab đăng nhập đồng thời**, một cookie giao dịch tên cố định có thể bị ghi đè; cần transaction ledger/per-state cookie hoặc thiết kế concurrency phù hợp, không lưu một `state` toàn cục dễ bị thay.

**Không bảo đảm chỉ cần `None` là form_post hoạt động trên mọi browser**. Chính sách third-party/privacy, proxy và cách trình duyệt xử lý redirect/form cần kiểm thử. Có thể chọn flow `response_mode=query` nếu phù hợp với OIDC provider và threat model, nhưng không được tự đổi response mode không được registration/profile cho phép.

## 17. `state`, `nonce`, PKCE và SameSite giải quyết các bài toán riêng

| Biện pháp | Ngăn/chặn điều gì? | Không thay được gì? |
|---|---|---|
| **`SameSite`** | Một số request tự kèm cookie khi cross-site | Không xác minh authorization response hay chống XSS |
| **`state`** | Liên kết callback OAuth với authorization transaction của client | Không mã hóa/giữ bí mật access token |
| **PKCE S256** | Ràng buộc authorization code với verifier tại token endpoint | Không thay `state`, issuer và redirect URI policy |
| **OIDC `nonce`** | Ràng buộc ID token/authorization response theo profile | Không thay kiểm tra chữ ký, `iss`/`aud` |
| **Issuer / AS mix-up defense** | Không gửi code tới token endpoint sai hoặc nhận callback từ AS sai | Không thay cookie security |
| **CSRF token/Origin** | Bảo vệ endpoint có state change bằng cookie session | Không thay xác minh token OAuth tại RS |
| **`Secure`/`HttpOnly`** | Bảo vệ transport/cookie read path | Không xác định đúng audience/scope |

**Lỗi phổ biến:** vì callback OIDC cần cookie `SameSite=None`, nhóm phát triển **bật None cho mọi cookie session rồi xóa CSRF middleware**. Điều này mở rộng bề mặt tấn công mà vẫn chưa giải quyết đúng vấn đề: phải **tách cookie giao dịch và session**, giữ state/PKCE, sử dụng Origin/CSRF ở các endpoint ứng dụng.

Không áp Origin check cứng “chỉ cho phép app origin” một cách mù quáng vào **OIDC `form_post` callback**, vì request thực sự đến từ **OP origin tin cậy**. Endpoint callback phải có **policy riêng**, kiểm tra `state` và issuer/PKCE/binding thay cho việc coi mọi cross-origin POST là lỗi hoặc cho phép tất cả POST.

## 18. Token storage: cookie session, BFF và SPA Bearer

Có ba mô hình thường gặp:

| Mô hình | Browser giữ gì? | CSRF có thể xảy ra? | Rủi ro cần quản trị |
|---|---|---|---|
| **BFF/server session** | Opaque **HttpOnly session cookie**, token OAuth giữ server-side | **Có**, vì cookie được gửi tự động | SameSite + CSRF/Origin, session fixation, BFF token vault |
| **SPA dùng access token trong bộ nhớ** | Access token JS-managed, gửi `Authorization: Bearer` rõ ràng | Không theo cùng cơ chế **ambient cookie** nếu API không dùng cookie auth | XSS/token exfiltration, CSP, audience/scope, RT storage |
| **SPA lưu raw JWT/RT trong Web Storage** | Token có thể đọc bằng JavaScript của origin | Cookie SameSite **không bảo vệ token đó** | XSS có thể lấy token; khó revoke/giới hạn lifetime |
| **SPA + backend session cookie** | Tương tự BFF ở browser | **Có** | Cookie policies, CSRF và authz backend |

`SameSite` chỉ áp dụng cho **cookies**. Nó **không hạn chế** một Bearer token đã bị attacker đánh cắp và tự gửi trong `Authorization` header từ máy khác. Token vẫn cần **signature/issuer/audience/scope/expiry**, storage phù hợp, rotation/revocation và sender-constraining nếu cần.

Một BFF giữ refresh token server-side và gửi cho browser **session cookie ngắn hạn, Secure + HttpOnly + Lax** thường giảm nguy cơ token OAuth trực tiếp bị JavaScript trích xuất. Nhưng BFF **vẫn phải chống CSRF**, kiểm soát CORS, session lifetime và object authorization.

## 19. Embedded widgets, third-party cookies và `Partitioned` (CHIPS)

Một ứng dụng có widget:

~~~text
Top-level: https://merchant-a.other.test
Iframe:    https://widget.example.test

Top-level: https://merchant-b.third.test
Iframe:    https://widget.example.test
~~~

Đây là **cross-site embedded contexts**. `SameSite=Lax` không phù hợp nếu widget phải gửi cookie trong iframe cross-site. `SameSite=None; Secure` có thể cho phép ở mức SameSite, nhưng **third-party cookie restrictions** có thể vẫn chặn.

**CHIPS / cookie `Partitioned`** (trong các browser hỗ trợ) lưu cookie theo **top-level site partition key**, giảm chia sẻ một cookie third-party giữa các top-level sites.

~~~http
Set-Cookie: __Host-widget_session=<OPAQUE_ID>; Path=/; Secure; HttpOnly; SameSite=None; Partitioned; Max-Age=900
~~~

- `Partitioned` yêu cầu `Secure`.
- Cookie partition cho merchant A không mặc định giống cookie partition cho merchant B.
- `Partitioned` **không** làm trình duyệt bỏ CORS, không tắt CSRF, không giúp một cookie vượt mọi browser privacy control.
- Không giả định mọi browser hỗ trợ cùng chính sách CHIPS/Storage Access API hoặc một lộ trình chặn third-party cookie thống nhất.
- Với embedded authentication, ưu tiên kiến trúc **top-level OAuth redirect/BFF** nếu có thể thay vì dựa vào silent third-party iframe cookies.

**Không dùng CHIPS như một “cách bật SSO toàn cục”**. Phân vùng cookie có thể khiến đăng nhập **tách riêng theo top-level site**.

## 20. Cấu hình Spring Boot session cookie tường minh

Trong Spring Boot servlet application hỗ trợ các thuộc tính session cookie dưới đây (kiểm tra version và session store thực tế), có thể cấu hình:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-session
        secure: true
        http-only: true
        path: /
        same-site: lax
~~~

**Giả định production:** app được phục vụ qua **HTTPS**, cookie **không có `Domain`**, có session store đáng tin và cấu hình reverse proxy/forwarded headers an toàn.

### Bốn điều phải kiểm tra sau deploy

1. Browser DevTools/Network cho thấy **`Set-Cookie` thực tế** có `SameSite=Lax; Secure; HttpOnly; Path=/` và tên/prefix đúng.
2. Spring Boot/Spring Security/Spring Session hoặc API gateway **không ghi đè** `Set-Cookie` thành giá trị khác.
3. Cookie `__Host-session` không có `Domain` và có `Path=/`, HTTPS.
4. Authenticated API state changes vẫn được **Spring Security CSRF protection** bảo vệ, không chỉ dựa vào Lax.

**Một số reverse proxy TLS termination** có thể khiến backend nghĩ request là HTTP nếu forwarded headers không được cấu hình đúng. Đừng khắc phục bằng cách tắt `Secure` trên cookie production; hãy cấu hình trust proxy và HTTPS theo framework/network topology.

### Spring Security servlet minh họa

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

public class BrowserSecurityConfig {
    @Bean
    SecurityFilterChain browserFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            // Không disable CSRF cho browser cookie sessions:
            .csrf(withDefaults())
            // Chỉ hoạt động khi đã cấu hình OAuth2 Client registration:
            .oauth2Login(withDefaults());

        return http.build();
    }
}
~~~

**Đây là cấu hình minh họa**, không phải cả hệ thống đăng nhập: phải cấu hình OAuth client/redirect URI, OIDC state/PKCE, authorization, cookie handling và exception policy. Nếu API dùng **Bearer-only** hoàn toàn và không dựa vào cookie, CSRF policy có thể khác; không copy một dòng `csrf().disable()` cho toàn bộ ứng dụng mixed browser/API.

## 21. Java/Spring: phát và xóa một host-only session cookie tùy chỉnh

Nếu ứng dụng **tự quản lý custom session ID** (không dùng cookie do framework Session Repository tự quản), `ResponseCookie` giúp cấu hình tường minh:

~~~java
import java.time.Duration;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;

public final class SessionCookieExample {
    private static final String NAME = "__Host-session";

    // sessionId phải là opaque random ID được backend phát an toàn,
    // đã tạo state server-side. Không nhận từ client input.
    public static void setSessionCookie(
            HttpServletResponse response,
            String serverGeneratedSessionId
    ) {
        ResponseCookie cookie = ResponseCookie.from(
                    NAME, serverGeneratedSessionId)
                .secure(true)
                .httpOnly(true)
                .path("/")
                .sameSite("Lax")
                .maxAge(Duration.ofHours(1))
                // Không gọi .domain(...), bắt buộc host-only.
                .build();

        response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
        response.setHeader("Cache-Control", "no-store");
    }

    public static void clearSessionCookie(
            HttpServletResponse response
    ) {
        ResponseCookie expired = ResponseCookie.from(NAME, "")
                .secure(true)
                .httpOnly(true)
                .path("/")
                .sameSite("Lax")
                .maxAge(Duration.ZERO)
                .build();

        response.addHeader(
                HttpHeaders.SET_COOKIE,
                expired.toString()
        );
        // Cần invalidate server-side session nữa.
    }

    private SessionCookieExample() {}
}
~~~

**Không gọi cả code này và Spring Session tạo cookie trùng tên**. Chọn **một** session manager làm chủ. `clearSessionCookie` chỉ xóa cookie phù hợp trong browser hiện tại; nó **không tự revoke session trên backend, RT family tại AS, hay JWT access token ở Resource Server**.

### Nhấn mạnh token lifecycle

Khi logout/login/password change, hệ thống cần xác định:

- Phiên server-side nào bị revoke, liệu session ID đã rotate chưa.
- Refresh token/grant có bị revoke theo RFC 7009 hoặc AS policy không.
- JWT access token đã phát có được RS thấy trạng thái revoke hay vẫn hợp lệ tới `exp`.
- Cookie `SameSite` chỉ tác động **browser gửi cookie**, **không** làm thay đổi `active`/`exp`/`aud` của token.

## 22. Frontend `fetch`: credentials, CORS và CSRF token

Khi app `https://app.example.test` gọi API `https://api.example.test` bằng **session cookie host của API**, hai origin là khác nhau nhưng same-site. Client phải chủ đích dùng `credentials:"include"` nếu muốn browser gửi cookie phù hợp:

~~~javascript
async function updateProfile(profile, csrfTokenFromServer) {
  const response = await fetch(
    "https://api.example.test/account/profile",
    {
      method: "POST",
      mode: "cors",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        // CSRF token phải do backend cung cấp qua kênh đáng tin.
        "X-CSRF-Token": csrfTokenFromServer
      },
      body: JSON.stringify(profile)
    }
  );

  if (!response.ok) {
    throw new Error("Profile update rejected");
  }
  return await response.json();
}
~~~

Ở API/gateway cần cấu hình CORS **allowlist exact origin**, chỉ cho methods/headers cần thiết, cho phép credentials khi đúng nhu cầu, và **CSRF/Origin validation** trong middleware:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Allow-Methods: GET, POST
Vary: Origin
~~~

**Chú ý:**

- Request JSON với custom header có thể được preflight; server cần xử lý `OPTIONS` theo CORS policy.
- **Preflight thành công không thay CSRF token** cho ứng dụng cookie auth. Một simple request như HTML form có thể không cần preflight nhưng vẫn gây side effect nếu backend yếu.
- `HttpOnly` session cookie **không cần** và **không được** đọc bằng `document.cookie`. CSRF token là một credential/anti-CSRF value **riêng**, có thể được backend phát an toàn qua HTML/meta tag/JSON endpoint theo framework.
- Không lấy `csrfTokenFromServer` từ query string hay origin lạ rồi tin nó.
- Nếu gọi API thật sự **cross-site**, `SameSite=Lax` sẽ không được gửi cho `fetch`, dù credentials include và CORS allow. Phải thiết kế lại topology/session hoặc có nhu cầu rõ cho `None; Secure`.

## 23. CSRF defense-in-depth: Origin, token và Fetch Metadata

Với một endpoint cookie-authenticated như `POST /account/change-email`, một tầng bảo vệ chắc chắn thường gồm:

1. Kiểm tra **HTTP method** và semantic: `GET` không thực hiện mutation.
2. Kiểm tra **session** hợp lệ, chưa revoke và quyền user/tenant/object.
3. Kiểm tra **CSRF token** theo framework (synchronizer token hoặc signed double-submit được bind session).
4. Xác minh **`Origin` exact match** với các origin frontend được phê duyệt cho các request browser state-changing; áp dụng policy cho trường hợp Origin vắng mặt.
5. Dùng **`Sec-Fetch-Site`** và Fetch Metadata headers như lớp phụ, từ chối cross-site unsafe requests không thuộc callback/flow được phê duyệt.
6. Giữ **`SameSite=Lax`/`Strict`** theo UX và không mở rộng `None` bừa bãi.
7. Không cho phép sibling subdomains không đáng tin tự động vượt Origin policy.

Ví dụ logic high-level:

~~~text
if request.method in {POST, PUT, PATCH, DELETE}:
    require authenticated server-side session
    require valid CSRF token bound to this session
    require Origin == one of explicitly allowed origins
        (or apply documented legacy/non-browser fallback)
    if Sec-Fetch-Site == "cross-site":
        reject unless request is an explicitly modeled
        protocol callback with its own state/binding checks
    enforce user/tenant/object authorization

perform change only after all checks pass
~~~

**`Sec-Fetch-Site` không tự đồng nhất với Origin**: nó thường có giá trị `same-origin`, `same-site`, `cross-site` hoặc `none`. Một malicious sibling subdomain có thể hiển thị **`same-site`**, nên không được “allow toàn bộ `same-site` requests” đối với state-changing browser APIs.

**Headers có thể vắng mặt** (legacy clients, một số non-browser integrations). Không tự chấp nhận tất cả vì thiếu header; định nghĩa fallback theo endpoint type, authentication model và CSRF contract. Các browser headers cũng không phải chữ ký và có thể bị giả trong non-browser requests, nên **không** thay authentication/authorization.

## 24. Threat modeling: SameSite chặn gì, không chặn gì?

| Tình huống | Điều attacker kiểm soát | SameSite có tác dụng? | Kiểm soát quyết định |
|---|---|---|---|
| **A. Cross-site form POST** | Trang `https://evil.other.test`, user đang login app | Lax/Strict thường không gửi cookie | CSRF token, Origin |
| **B. Cross-site top-level GET** | Link/redirect tới GET mutation | Lax vẫn có thể gửi | Không mutation bằng GET |
| **C. Same-site sibling CSRF** | XSS/takeover `blog.example.test` | Strict/Lax **không đủ** | Exact Origin + CSRF |
| **D. Same-origin XSS** | Script chạy trong `app.example.test` | SameSite không ngăn | XSS/CSP, encode, hạn quyền |
| **E. Cross-site iframe** | Site ngoài nhúng widget | Lax/Strict thường chặn cookie | None+Secure khi cần, CHIPS, origin checks |
| **F. OAuth callback GET** | Redirect OP→RP | Lax thường đi theo top-level GET | State, PKCE, issuer, session binding |
| **G. OIDC form_post** | Form POST OP→RP | Lax có thể không đi theo | Dedicated None+Secure transaction cookie, flow checks |
| **H. Bearer stolen token** | Attacker có AT raw | SameSite không áp vào header | Audience, expiry, PoP, revoke |
| **I. JWT ID-as-access confusion** | Token khác purpose nhưng cùng issuer | SameSite không giải quyết | `typ`, `iss`, `aud`, token use |
| **J. Third-party cookie blocking** | Privacy settings/browser | None không đảm bảo gửi | Top-level flow, CHIPS khi phù hợp, test browser |
| **K. Session fixation** | Attacker cố đặt session cookie | Prefix hỗ trợ, SameSite chưa đủ | Server session rotation + cookie host-only |
| **L. Logout CSRF** | Site khác gửi logout URL | Lax GET có thể gửi | Logout POST + CSRF hoặc protocol flow đúng |
| **M. Cross-origin fetch** | Frontend ở sibling subdomain | SameSite có thể cho phép | Fetch credentials + CORS + Origin |
| **N. Http→HTTPS scheme mismatch** | Site cùng registrable domain khác scheme | Schemeful same-site tính cross-site | HTTPS end-to-end + expected origins |

**Đối với OIDC login CSRF**, attacker có thể tìm cách ép nạn nhân đăng nhập vào **tài khoản của attacker** nếu RP không bind authorization response với giao dịch do browser nạn nhân khởi tạo. `SameSite` không chứng minh `state` hợp lệ; luôn cần chống login CSRF ở OAuth/OIDC layer.

## 25. Case study: CMS cùng site khiến `Strict` không đủ

Giả sử công ty vận hành:

~~~text
https://pay.example.test
    /settings/payout
    Session cookie: __Host-session; SameSite=Strict

https://blog.example.test
    CMS do team marketing quản lý,
    cho phép cài plugin bên thứ ba.
~~~

Một plugin CMS bị XSS cho phép attacker điều khiển trang `blog.example.test`. Vì cùng scheme và registrable domain, hai ứng dụng là **same-site**.

### Đường tấn công khi backend chỉ dựa SameSite

1. User đăng nhập `pay.example.test`; trình duyệt lưu session cookie host-only Strict.
2. User mở `blog.example.test` và trang độc hại dựng HTML form POST tới `https://pay.example.test/settings/payout`.
3. Request đến **pay.example.test** với ngữ cảnh **same-site**; cookie host-only của pay **có thể được gửi** dù blog **không đọc được cookie**.
4. Backend pay chỉ kiểm tra cookie và `SameSite=Strict`, **không kiểm tra Origin/CSRF**.
5. Nếu không có object/step-up authorization phù hợp, payout settings có thể bị sửa trái ý user.

### Đường phòng vệ

1. Cookie pay là **host-only `__Host-session`, `Secure; HttpOnly; SameSite=Strict`**.
2. `POST /settings/payout` yêu cầu **`Origin: https://pay.example.test`**, không nhận `https://blog.example.test`.
3. Endpoint yêu cầu **CSRF token đúng session** và recent reauthentication cho payout settings.
4. Nếu có frontend hợp lệ ở origin khác, đưa origin vào allowlist **theo trường hợp cụ thể**, không wildcard cả registrable domain.
5. Browser Fetch Metadata cùng app telemetry giúp nhận biết request suspicious `Sec-Fetch-Site: same-site` nhưng **không thay Origin**.
6. API kiểm tra tenant/user permissions, audit và cảnh báo thay đổi.
7. Tách CMS không đáng tin sang **site khác** nếu kiến trúc có thể làm được.

**Kết luận case:** “Strict cookie” là một lớp tốt nhưng **ranh giới site rộng hơn ranh giới origin**. Cấu trúc subdomain là **quyết định an ninh**, không chỉ cấu hình DNS.

## 26. Troubleshooting SameSite trên browser thật

| Hiện tượng | Nguyên nhân có thể | Bước kiểm tra phù hợp |
|---|---|---|
| Cookie không gửi sau login qua OP | `Strict` không đi cùng cross-site GET callback | Xem DevTools Cookies/SameSite; cân nhắc Lax + state/PKCE |
| OIDC `form_post` mất session/state | Callback cross-site POST với Lax | Dedicated transaction `None;Secure`, callback binding |
| `SameSite=None` cookie bị browser reject | Quên `Secure` hoặc HTTP production | HTTPS + Secure; kiểm tra cookie rejection reason |
| SPA gọi sibling API không có cookie | Cross-origin fetch mặc định `credentials:"same-origin"` | `credentials:"include"` + CORS policy |
| CORS blocked dù API trả 200 | Credentials cùng `Access-Control-Allow-Origin:*` hoặc thiếu ACAC | Dùng exact origin, `Access-Control-Allow-Credentials:true` |
| Cookie có None vẫn mất trong iframe | Browser third-party blocking/storage partition | Test browser privacy; CHIPS/top-level flow khi cần |
| Strict cookie vẫn gửi từ blog sibling | Same-site khác same-origin | Exact Origin/CSRF, không chỉ Strict |
| Lax cookie gửi trên cross-site GET | Top-level safe navigation được Lax cho phép | GET không mutation, CSRF policy |
| Mới login rồi cross-site POST vẫn có cookie | Cookie **omitted SameSite** kích hoạt Lax-allowing-unsafe ở một số browser | Đặt explicit Lax, không rely 2-minute exception |
| Session cookie bị leak tới subdomains | `Domain=example.test` | Host-only + `__Host-`, bỏ Domain |
| Browser báo `__Host-` cookie invalid | Có Domain, thiếu Secure hoặc Path=/ | Sửa prefix constraints |
| Cookie `Secure` không set sau TLS proxy | Backend/proxy HTTPS metadata sai, response thực tế HTTP | Cấu hình TLS, trusted forwarded headers |
| Cookie vẫn dùng được sau logout | Server chưa revoke session, browser giữ credential | Server-side revoke; cookie deletion khớp Name/Path/Domain |
| CSRF fail cho request hợp lệ | CSRF token sai phiên, Origin config sai | Điều tra theo transaction, không disable CSRF toàn site |
| Chạy được Chrome, lỗi Safari/Firefox | Browser cookie/privacy behaviors khác | Test tương thích và tránh assumption 3PC |
| Redirect GET/POST cho kết quả khác | 303/307/308, initiator context, nested frames | Network waterfall, target method/Origin/initiator |

### Checklist DevTools/Network

- **Request URL, initiator/origin và HTTP method**, top-level hay iframe/fetch.
- Header **`Cookie`** thực sự gửi tới server; cookie bị loại vì lý do gì theo DevTools.
- Header **`Set-Cookie`** thực tế (không chỉ application YAML), `SameSite`, `Secure`, `HttpOnly`, `Domain`, `Path`, lifetime.
- Trình duyệt **third-party cookie settings**, partition key, iframe context và storage restrictions.
- `Origin`, `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest` cùng response CORS.
- OAuth/OIDC callback `state`/issuer/redirect binding và response mode, **không ghi raw code/token vào logs**.
- Session đã thực sự tồn tại, chưa revoke và server đã kiểm tra CSRF/authorization.

**Không xuất HAR production chứa raw session cookie, ID/access/refresh token, authorization code hay OAuth client secret vào ticket/chat công khai**. Dùng staging với credential canary và redaction trước khi chia sẻ.

## 27. Ma trận kiểm thử SameSite behavior

| Test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| **T1 — Strict same-origin** | App gửi POST trong chính origin | Cookie Strict đủ điều kiện, CSRF vẫn chạy |
| **T2 — Lax same-origin** | App GET/POST nội bộ | Cookie Lax đủ điều kiện |
| **T3 — None same-origin** | Cookie None;Secure ở app | Cookie đủ điều kiện nếu các policies khác cho |
| **T4 — Strict cross-site GET** | Link external→app top-level GET | Strict không được gửi |
| **T5 — Lax cross-site GET** | Link external→app top-level GET | Lax có thể được gửi |
| **T6 — Lax cross-site POST** | External HTML form POST→app | Explicit Lax không gửi |
| **T7 — Strict cross-site POST** | External form POST→app | Strict không gửi |
| **T8 — None cross-site POST** | None;Secure session cookie | Có thể gửi, nhưng server reject khi CSRF/Origin fail |
| **T9 — Lax cross-site image** | External `<img>` GET→app | Lax không gửi |
| **T10 — Lax cross-site iframe** | External iframe→app | Lax không gửi |
| **T11 — None third-party iframe** | None;Secure cookie | Có thể gửi hoặc bị 3PC/privacy policy chặn |
| **T12 — Schemeful site** | http sibling→https app | Cross-site theo schemeful model |
| **T13 — Same-site sibling POST** | https blog sibling→https app | Strict/Lax có thể gửi; CSRF/Origin từ chối |
| **T14 — Same-site cross-origin fetch** | app→api sibling, mặc định credentials | Không tự gửi cross-origin cookie |
| **T15 — Fetch credentials include** | app→api sibling, `include` | Cookie eligible theo SameSite, CORS còn áp dụng |
| **T16 — Cross-site fetch with Lax** | other.test→app `include` | Lax không gửi |
| **T17 — Cross-site fetch with None** | other.test→app `include` | Có thể gửi; CORS/CSRF/privacy áp dụng |
| **T18 — CORS wildcard with credentials** | ACAO `*` và ACAC true | JS không đọc response credentialed |
| **T19 — Exact CORS origin** | ACAO chính xác frontend trusted | JS đọc response nếu các kiểm tra khác cho |
| **T20 — Omitted SameSite** | Cookie không khai báo attribute | Kiểm tra default Lax theo browser, không assume đồng nhất |
| **T21 — Lax POST 2-minute nuance** | Cookie omitted SameSite mới đặt, cross-site POST | Quan sát exception browser nếu có; explicit Lax không dựa vào nó |
| **T22 — None without Secure** | Set-Cookie None nhưng thiếu Secure | Browser hiện đại từ chối/suppress cookie |
| **T23 — Secure only over HTTPS** | Cookie Secure trên HTTP production | Không dùng, HTTPS bắt buộc |
| **T24 — HttpOnly JS access** | Script đọc `document.cookie` | Không đọc được session cookie HttpOnly |
| **T25 — HttpOnly XSS request** | Script same-origin thực hiện POST | Cookie vẫn có thể được gửi; CSRF/XSS mitigations |
| **T26 — Host-only cookie** | `Domain` bỏ trống | Cookie gửi đúng host đích, không trực tiếp sang sibling |
| **T27 — Domain-scoped cookie** | `Domain=example.test` | Có thể tới subdomains, cần audit rủi ro |
| **T28 — __Host valid** | Secure; Path=/; no Domain | Browser hỗ trợ prefix chấp nhận |
| **T29 — __Host invalid** | Có Domain hoặc thiếu Path=/ | Browser hỗ trợ prefix từ chối |
| **T30 — Path not authz** | Cookie `Path=/admin` | Không coi Path là bảo vệ server-side |
| **T31 — GET mutation CSRF** | Cross-site top-level GET gọi endpoint thay dữ liệu | Test bắt lỗi thiết kế, chuyển mutation sang POST + CSRF |
| **T32 — Logout via GET** | External link kích hoạt logout | Không dùng unsafe GET để logout; dùng POST/CSRF |
| **T33 — OAuth callback query** | AS redirect top-level GET về RP | Lax cookie có thể gửi; `state`/PKCE/issuer PASS |
| **T34 — OAuth callback Strict** | Strict session cookie trên cross-site GET | Có thể mất correlation; không tắt `state` để workaround |
| **T35 — OIDC form_post Lax** | Cross-site top-level POST callback | Lax thiếu; flow cần transaction policy đúng |
| **T36 — OIDC form_post None** | Dedicated None;Secure correlation cookie | State/nonce/PKCE verify, tx cookie xóa sau dùng |
| **T37 — OIDC forged state** | Callback `state` do attacker tạo | RP từ chối dù cookie có mặt |
| **T38 — Concurrent OIDC tabs** | Hai login transactions trên browser | Không overwrite global state/cookie làm mix-up |
| **T39 — PKCE verifier theft** | Có code nhưng verifier không khớp | AS token endpoint từ chối |
| **T40 — Bearer token theft** | Attacker có access token trong header | SameSite không bảo vệ; RS cần token/PoP policy |
| **T41 — JWT audience** | ID token hoặc AT wrong `aud` tới API | RS từ chối, không nhầm cookie/session |
| **T42 — Refresh token in BFF** | Browser chỉ có opaque session ID | Không thấy raw RT/AT trong cookie/browser JS |
| **T43 — Session server revoke** | Logout/password change, cookie chưa hết hạn | Backend từ chối session cũ |
| **T44 — Cross-subdomain Origin** | POST có `Origin: https://blog.example.test` | Reject nếu only app origin allowed |
| **T45 — Fetch Metadata sibling** | `Sec-Fetch-Site: same-site` từ blog | Không tự xem là trusted origin |
| **T46 — Fetch Metadata missing** | Legacy/non-browser request | Áp documented fallback/CSRF policy, không auto allow |
| **T47 — Third-party cookie blocked** | Browser privacy chặn None cookie | Flow graceful, không tắt CSRF/TLS để “sửa” |
| **T48 — Partitioned CHIPS** | Widget chạy dưới hai top-level sites | Session cookie phân vùng, không tự share |
| **T49 — Browser compatibility** | Chromium/Firefox/WebKit và mobile browsers | Test behavior theo versions hỗ trợ, không mặc định đồng nhất |
| **T50 — Proxy config** | TLS offload ghi đè Set-Cookie | Browser vẫn thấy Secure;HttpOnly;SameSite đúng |
| **T51 — Redirect chain** | 302/303/307/308 trong auth flow | Kiểm tra method/site context thực tế, không rely trick |
| **T52 — Audit redaction** | Canary cookie/AT trong staging HAR/APM | Không lộ raw credentials trong logs/traces |
| **T53 — Unsafe cross-site origin** | CSRF token thiếu dù SameSite=None | Server từ chối |
| **T54 — Expired cookie** | Max-Age quá hạn | Browser không gửi dù SameSite cho phép |
| **T55 — Cookie deleted client only** | Xóa cookie nhưng server session/RT còn | Kiểm thử chứng minh cần revoke server-side |
| **T56 — Subdomain takeover** | Untrusted sibling gửi request same-site | Exact Origin + CSRF vẫn chặn |

**Quan trọng:** khi viết automated test, **dùng browser thật** (Playwright/WebDriver hoặc tương đương) cho cookie inclusion. Unit test chỉ mock header không chứng minh hành vi thực tế của cookie jar, top-level navigation, iframe, schemeful-site hay browser privacy policy.

## 28. Checklist production và tài liệu chuẩn

### Checklist ra quyết định

1. **Định nghĩa login/session topology**: app cùng origin, sibling API cross-origin same-site, BFF hay third-party embedded widget.
2. **Phân loại cookie theo mục đích**: app session, OIDC correlation, CSRF token, widget/analytics; không buộc mọi cookie có cùng SameSite.
3. **Khai báo SameSite tường minh**, ưu tiên `Lax` cho session website nếu UX/flow cho phép; dùng Strict cho use case không cần external top-level navigation.
4. **Chỉ dùng `None; Secure` khi có nhu cầu cross-site rõ**; phòng vệ CSRF/Origin chặt và kiểm thử privacy blocking.
5. **Bật HTTPS/TLS**, `Secure`, `HttpOnly` cho session credentials; không dùng HTTP production.
6. **Ưu tiên cookie host-only `__Host-`**, `Path=/` và không `Domain` cho app session nhạy cảm.
7. **Không coi Path hoặc Domain là ACL**, không coi sibling subdomains tự động đáng tin.
8. **Dùng CSRF token/Origin checks** với state-changing cookie-authenticated requests, kể cả SameSite Strict.
9. **Không mutation bằng GET**, kể cả logout, đổi mật khẩu, chuyển tiền, reset MFA.
10. **Xác định exact trusted origins** cho CORS, không dùng wildcard với credentials, và kiểm tra `Sec-Fetch-Site` như lớp phụ.
11. **Với fetch cross-origin same-site**, cân nhắc `credentials:"include"`, CORS allowlist và CSRF; đừng nhầm SameSite với origin.
12. **Giữ OAuth/OIDC state + PKCE S256 + issuer/redirect binding**, không làm yếu flow để khắc phục cookie bị chặn.
13. **Kiểm thử `response_mode=query` vs `form_post`** và dùng cookie giao dịch phù hợp, TTL nhỏ, single-use.
14. **Không coi `SameSite` là token revocation**; vẫn cần server session invalidation/AS revocation/RS audience-scope checks.
15. **Bảo vệ chống XSS** bằng output encoding, framework auto-escaping, CSP, hạn third-party scripts và secret exposure.
16. **Không đặt raw RT ở localStorage vì “đã có SameSite cookie”**; SameSite không bảo vệ Web Storage.
17. **Thiết kế CHIPS/Partitioned** khi thật sự cần embedded third-party cookie và browsers hỗ trợ; fallback an toàn khi chặn.
18. **Kiểm tra Set-Cookie sau CDN/reverse proxy**, cookie prefix, HTTPS và header rewriting.
19. **Dùng tests nhiều browser/iframe/redirect/sibling subdomain**, có trường hợp âm tính CSRF trên cả cross-site và same-site.
20. **Đo telemetry không lộ secrets**: cookie rejection reason, CORS/CSRF denies, OIDC callback failures, không log raw session/AT/RT/code.
21. **Quản lý tuổi thọ và logout**: xóa cookie trong browser chỉ một phần; phải revoke session server-side và RT family khi policy yêu cầu.
22. **Ghi chính xác user-facing guarantee**: “đã logout” không đồng nghĩa mọi JWT access token offline lập tức hết hạn tại mọi RS.

### Tài liệu chuẩn và hướng dẫn triển khai

- [MDN — Set-Cookie: SameSite, Secure, HttpOnly, Domain, cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): cơ chế cookie và lưu ý `Lax-by-default`.
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): cookie scope, session security và SameSite.
- [MDN — Third-party cookies](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies): browser privacy và hạn chế third-party cookie.
- [MDN — Fetch credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch): `credentials:"include"` và SameSite/CORS.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): credentialed CORS, preflight, origin và hạn chế của CORS.
- [MDN — Cookies Having Independent Partitioned State (CHIPS)](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Privacy_sandbox/Partitioned_cookies): `Partitioned` và cookie partitioning.
- [HTTPWG — Cookies draft (RFC 6265bis)](https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html): quy tắc cookie/SameSite theo đặc tả cập nhật.
- [web.dev — Schemeful Same-Site](https://web.dev/articles/schemeful-samesite): site scheme, registrable domain và khác origin.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, signed double-submit, Origin, Fetch Metadata và SameSite.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie flags, session fixation, revocation và rotation.
- [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): Web Storage/JS risks và browser security.
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): OAuth CSRF/redirect/token security.
- [PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636): binding code với verifier trong Authorization Code Flow.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `state`/`nonce`, ID token và code flow.
- [OpenID Connect Form Post Response Mode 1.0](https://openid.net/specs/oauth-v2-form-post-response-mode-1_0.html): authorization response qua cross-site POST.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF trong browser session apps.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/): server session cookie config theo phiên bản.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách Bearer access token được trình đến Resource Server.

**Kết luận:** `SameSite` điều khiển **việc browser gửi cookie trong same-site/cross-site request context**; nó không xác minh user, token JWT hay quyền API. **`Strict`** hạn chế cross-site mạnh hơn nhưng có thể phá external navigation/login callback; **`Lax`** thường cân bằng cho website session nhờ cho phép **top-level safe navigation**; **`None; Secure`** cần cho một số cross-site flow nhưng tạo thêm bề mặt CSRF và vẫn phụ thuộc browser privacy. Để an toàn, phải **phân biệt site với origin, kiểm tra CSRF/Origin, giới hạn cookie Domain, bảo vệ XSS, ràng buộc OAuth/OIDC state/PKCE và thực thi revocation/authorization trên backend**.
