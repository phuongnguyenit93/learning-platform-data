# Hệ thống cùng phục vụ trình duyệt và client máy–máy

## Mục tiêu học tập

Sau bài học thuộc chương **Tích hợp ứng dụng**, người học có thể:

- Phân tích một hệ thống Spring Security đồng thời phục vụ **người dùng qua trình duyệt** và **client máy–máy (machine-to-machine, M2M)**, thay vì áp một chính sách HTTP/security duy nhất cho mọi request.
- Chỉ ra khác biệt giữa **session cookie do browser tự gửi** và **OAuth2 Bearer access token được tác nhân M2M chủ động gắn**; xác định khi nào phải kiểm soát CSRF.
- Thiết kế các vùng URL/security chain độc lập cho **trang/form/browser API** và **integration API**, tránh sai thứ tự matcher, authentication fallback và đường vòng phân quyền.
- Tích hợp **form login, session fixation protection, CSRF token, logout** cho browser; **client credentials, token validation, scope, audience và quyền trên tài nguyên** cho M2M.
- Cấu hình ví dụ cho cả **Spring Security Servlet/Spring MVC** (`HttpSecurity`/`SecurityFilterChain`) và **Reactive/WebFlux** (`ServerHttpSecurity`/`SecurityWebFilterChain`).
- Phân biệt **CORS, SameSite, CSP, HSTS, HTTP firewall, TLS, proxy header** và **CSRF**; hiểu lớp nào bảo vệ client nào.
- Xác định chính sách lỗi phù hợp: **redirect tới login** cho navigation HTML, nhưng **`401`/`403` với `WWW-Authenticate`** khi cần cho M2M.
- Viết kiểm thử âm/dương chứng minh **cookie-only không xác thực được M2M API**, token Bearer không trở thành session của browser, và POST của browser thiếu/sai CSRF token không gây tác động.
- Xử lý các ca triển khai có **load balancer, shared session store, gateway, OAuth issuer, mTLS, secret rotation và observability**.
- Đề xuất checklist duy trì ranh giới bảo mật khi thêm endpoint, client hoặc phương thức xác thực mới.

## 1. Bài toán tích hợp: hai kiểu client, một ứng dụng

Giả sử một nền tảng quản lý đơn hàng cần đáp ứng đồng thời:

1. **Nhân viên truy cập browser** để xem dashboard, chỉnh hồ sơ, duyệt đơn và đăng xuất. Luồng này dùng trang HTML SSR hoặc SPA và có thể dùng **session cookie**.
2. **Hệ thống đối tác/worker định kỳ** gọi API để gửi trạng thái xử lý đơn. Nó không có người dùng trực tiếp trước màn hình, nên dùng **OAuth2 client credentials grant** để lấy access token, rồi gửi **`Authorization: Bearer ...`** khi gọi Resource Server.

Hai request nhìn giống HTTP nhưng khác nguồn credential:

~~~http
POST /web/profile HTTP/1.1
Host: platform.example.com
Cookie: JSESSIONID=browser-session
Content-Type: application/x-www-form-urlencoded

displayName=Alice&_csrf=token-cua-phien
~~~

~~~http
POST /integrations/jobs HTTP/1.1
Host: platform.example.com
Authorization: Bearer opaque-or-jwt-access-token
Content-Type: application/json

{"externalJobId":"partner-42","state":"DONE"}
~~~

Request thứ nhất dựa vào **ambient credential**: browser tự đính kèm cookie khi chính sách cookie cho phép. Request thứ hai dựa vào **credential do client M2M chủ động đặt** và Resource Server xác minh theo chính sách access token.

Nếu cấu hình `csrf.disable()` toàn ứng dụng vì “API M2M không cần CSRF”, browser POST có thể mất phòng vệ. Nếu bật form login trên mọi endpoint, M2M có thể nhận **redirect 302 về trang login** thay vì lỗi `401` dễ xử lý. Nếu để API M2M chấp nhận `JSESSIONID`, một request cookie-only có thể qua authentication mặc dù thiết kế ban đầu đòi Bearer token.

**Vấn đề trọng tâm:** Hệ thống không chỉ có hai client, mà có **hai mô hình đe dọa và hai hợp đồng xác thực** cùng tồn tại.

### 1.1. Sơ đồ phân vùng

~~~mermaid
flowchart LR
    B[Trình duyệt của nhân viên] -->|HTTPS + session cookie + CSRF với POST| E[Public HTTPS edge]
    M[Partner worker / CLI] -->|HTTPS + Bearer access token| E
    E -->|/web/**, /login, /logout| W[Browser security chain]
    E -->|/integrations/**| A[M2M resource-server chain]
    W --> S[(Session store)]
    A --> I[JWT decoder / Token introspection]
    W --> D[Domain services và database]
    A --> D
    M -->|client_credentials| AS[Authorization Server]
    AS -->|Access token scoped cho API| M
~~~

Sơ đồ minh họa **hai security chains trong cùng Spring application**. Chúng có thể được triển khai thành hai dịch vụ tách biệt nếu mức độ cách ly/hạ tầng yêu cầu; nguyên tắc credential và ranh giới browser–M2M không đổi.

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, kiến trúc này là điểm giao của **CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session** trên cả Servlet lẫn Reactive. Không một lớp bảo vệ duy nhất giải quyết toàn bộ hệ thống.

### 1.2. Xác định từng client trước khi viết cấu hình

| Thuộc tính | Browser người dùng | M2M client |
|---|---|---|
| Chủ thể | Người dùng cuối với role/authority | Ứng dụng/dịch vụ/partner với client identity |
| Credential thường gặp | `JSESSIONID` hoặc `SESSION` cookie | `Authorization: Bearer access_token` |
| Ai gửi credential? | Browser **tự gắn cookie** theo policy | SDK/CLI/service **chủ động gắn header** |
| Cấp credential | Form login, OIDC web login, BFF session | OAuth2 client credentials hoặc cơ chế workload identity tương ứng |
| Chống CSRF | Quan trọng với unsafe requests dùng cookie | Thường không cần CSRF dạng cookie **nếu thực sự bearer-only** |
| Khi chưa xác thực | HTML redirect login hoặc API `401` theo loại request | `401` kèm Bearer challenge khi phù hợp |
| Khi thiếu quyền | Trang lỗi `403` hoặc response API | `403`; có thể kèm `insufficient_scope` |
| Thời gian sống | Session timeout, login/logout, session fixation | Access token TTL, secret rotation, token revocation |
| Browser CORS | Có nếu JS gọi khác origin | Không cần CORS cho client HTTP không chạy trong browser |
| Phân quyền nghiệp vụ | User và tài nguyên của user/tenant | Client/service, scopes, partner/tenant resources |

### 1.3. Một session cookie không phải Bearer token

**Session ID** chỉ giúp server tìm phiên và `SecurityContext` theo cấu hình. Không render session ID thành hidden field, không dùng làm CSRF token, không đưa nó vào header Bearer như một access token.

Ngược lại, một JWT có chữ ký **đặt trong cookie HttpOnly** vẫn là **credential được browser tự gửi**, nên không trở thành mô hình bearer-only chỉ vì định dạng token là JWT hoặc API đặt stateless.

## 2. Threat model: tại sao không dùng một quy tắc CSRF chung?

### 2.1. Browser có nguy cơ CSRF khi tự gửi cookie

Giả sử nhân viên Alice đang đăng nhập `https://platform.example.com`. Nếu một trang khác khiến browser gửi:

~~~http
POST /web/profile HTTP/1.1
Host: platform.example.com
Cookie: JSESSIONID=SESSION_ALICE
Content-Type: application/x-www-form-urlencoded

displayName=AttackerChosen
~~~

cookie có thể được tự gửi tùy SameSite/ngữ cảnh. Nếu server chấp nhận POST và không kiểm CSRF token, một hành động giả mạo có thể được thực hiện dưới phiên Alice.

Tại `/web/**`, lớp CSRF nên yêu cầu **submitted token** từ form/header khớp **expected token** được repository quản lý theo phiên/ngữ cảnh.

### 2.2. M2M bearer-only có mô hình CSRF khác

Một máy đối tác gửi:

~~~http
POST /integrations/jobs HTTP/1.1
Host: platform.example.com
Authorization: Bearer ACCESS_TOKEN_PARTNER_42
Content-Type: application/json

{"externalJobId":"partner-42","state":"DONE"}
~~~

Một website bên ngoài thông thường không biết `ACCESS_TOKEN_PARTNER_42` và không thể khiến browser tự lấy token của worker rồi thêm header đó.

**Có thể miễn kiểm tra CSRF cho nhóm route này** nếu hệ thống đã chứng minh tất cả điều kiện:

- Route M2M **chỉ** chấp nhận Bearer access token do client đặt.
- **Không** chấp nhận session cookie, JWT cookie, Basic auth tự gửi, client certificate của browser hoặc SSO gateway tự phục hồi phiên dưới cùng route.
- Security chain có matcher rõ ràng và không có filter khác xử lý cookie trước/sau bằng cơ chế auth phụ.
- Không có endpoint browser-auth như `/integrations/refresh` vô tình nằm trong vùng đã miễn CSRF.
- Token bắt buộc có issuer/audience/scope/client identity đúng và được phân quyền theo resource.
- Test **cookie-only request** bị từ chối, trong khi **Bearer hợp lệ** mới được phép.

**Tắt CSRF không làm token Bearer an toàn hơn.** Rủi ro chính chuyển sang **đánh cắp token, replay, lộ client secret, sai issuer/audience/scope và object-level authorization**.

### 2.3. Bảng kết hợp credential và cơ chế phù hợp

| Request | Credential backend thực sự nhận | CSRF trên unsafe request? | Lý do |
|---|---|---|---|
| Browser form POST | Session cookie | **Có** | Browser tự gửi cookie |
| SPA cùng origin gọi browser API | Session cookie + JSON | **Có** | JSON không tự loại CSRF |
| SPA cross-origin nhưng cùng site | Session cookie + CORS | **Có** | CORS không thay CSRF |
| Browser gửi JWT qua cookie | JWT cookie HttpOnly | **Cần đánh giá và thường có** | Cookie vẫn ambient |
| M2M dùng Bearer header duy nhất | Header do service chủ động gắn | **Thường không cần kiểu cookie** | Không có cookie/browser credential fallback |
| SPA gọi bearer-only API | Bearer do JS chủ động gắn | **Có thể miễn nếu chứng minh bearer-only** | Không tự gửi access token từ JS memory |
| M2M API cũng chấp nhận cookie | Bearer **hoặc** session cookie | **Không đủ điều kiện miễn chung** | Có đường ambient credential |
| Browser→BFF→M2M API | Cookie browser→BFF, Bearer BFF→API | **Có tại BFF** | Upstream Bearer không loại CSRF tại browser entry |
| Refresh endpoint dùng refresh cookie | Refresh token cookie | **Cần đánh giá riêng** | Cookie tự gửi, tác động đến token lifecycle |
| API dùng HTTP Basic trên browser | Basic được browser nhớ/gửi trong một số ngữ cảnh | **Cần đánh giá** | Header Authorization không chứng minh client tự quyết định |

### 2.4. CORS không thay CSRF hoặc authentication

**CORS** quyết định JavaScript ở origin ngoài có được browser cho phép đọc response và dùng một số kiểu request cross-origin hay không. Một HTML form có thể **gửi request** mà không cần được CORS cho phép đọc response.

Nếu M2M là client HTTP server-to-server, **CORS của browser không bảo vệ API trước client đó**. Nếu kẻ tấn công có Bearer token bị lộ, họ có thể gọi API bằng cURL mà không cần Origin được CORS allowlist.

### 2.5. XSS vẫn có thể vượt ý định của CSRF

Một script độc hại thực thi **trong origin browser hợp lệ** có thể đọc CSRF token từ HTML/endpoint cho client hợp lệ rồi gọi endpoint dưới phiên người dùng. Vì vậy CSRF token không thay **output encoding, CSP, DOM sanitization, dependency hygiene và phân quyền theo resource**.

## 3. Thiết kế URL contract để hai nhóm không chồng lấn

Bài sử dụng **hai vùng chức năng rõ ràng**:

| Public endpoint | Client | Authentication | CSRF policy |
|---|---|---|---|
| `GET /login` | Browser | Cho phép anonymous đọc trang login | Không yêu cầu token trên GET |
| `POST /login` | Browser | Form authentication | **Bắt buộc CSRF** |
| `GET /web/profile` | Browser | Session cookie | GET chỉ đọc |
| `POST /web/profile` | Browser | Session cookie | **Bắt buộc CSRF** |
| `POST /logout` | Browser | Session cookie | **Bắt buộc CSRF** |
| `GET /assets/**` | Browser | Anonymous đọc asset | GET chỉ đọc |
| `POST /integrations/jobs` | M2M | Chỉ OAuth Bearer token, `SCOPE_jobs:write` | Có thể miễn khi bearer-only được chứng minh |
| `GET /integrations/jobs/{id}` | M2M | Chỉ OAuth Bearer token, `SCOPE_jobs:read` | GET chỉ đọc |
| `GET /integrations/health` | Nội bộ theo policy | Không công khai mặc định | Tách health/actuator khỏi route nghiệp vụ |
| `POST /web/api/profile` (nếu có SPA) | Browser JS | Cookie session | **Bắt buộc CSRF header** |

Không có quy tắc “API JSON là stateless” chỉ từ path tên `/api`. **Route và cách credential được chấp nhận** mới quyết định chính sách.

### 3.1. Vì sao nên tách route thay vì cho cùng endpoint nhận hai auth kiểu?

Một controller `POST /orders` vừa nhận `JSESSIONID`, vừa nhận Bearer token làm khó:

- Xác định **authentication nào thắng** nếu request gửi cả cookie và Bearer;
- Truy nguyên lỗi 401/403 hay redirect;
- Biết nơi nào CSRF phải được áp;
- Đặt quota/audit cho user vs machine principal;
- Giải thích quyền theo user hay client;
- Đảm bảo Spring Security chain phù hợp với gateway/proxy rewrite.

Một hệ thống có thể **cố ý** cho hai nhóm dùng chung endpoint, nhưng khi đó phải thiết kế **quy tắc lựa chọn credential và chống downgrade** rất rõ, có test cả kết hợp cookie+header. Trong bài này, tách `/web/**` và `/integrations/**` giúp thiết kế dễ kiểm chứng hơn.

### 3.2. Đặt fail-closed cho URL ngoài thiết kế

Route **không thuộc `/integrations/**`** không nên tình cờ được Resource Server chain xử lý và miễn CSRF. Một fallback web chain có thể yêu cầu authentication hoặc một deny-all chain riêng cho những URL không công khai.

**Sai lầm phổ biến:** Dùng `securityMatcher("/**")` ở chain M2M ưu tiên trước, rồi kỳ vọng chain browser ở phía sau vẫn được chạy. Trong Spring Security, **chỉ chain phù hợp đầu tiên được chọn** trên mỗi request; chain tiếp theo không được ghép thêm để “bù” CSRF.

## 4. Luồng trình duyệt: session, form, CSRF và logout

### 4.1. Trình tự chuẩn

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant B as Browser
    participant S as Browser Security Chain
    participant R as Session + CSRF repository
    participant C as Web Controller/Service

    B->>S: GET /login
    S->>R: Tạo/tải token cho phiên ban đầu
    S-->>B: HTML login form + CSRF token
    U->>B: Điền username/password
    B->>S: POST /login + cookie + submitted CSRF
    S->>R: Đối chiếu expected vs submitted
    S->>S: Authentication, chống session fixation
    S-->>B: Redirect + session cookie hiện hành
    B->>S: GET /web/profile + cookie
    S->>C: Đọc hồ sơ theo principal Alice
    C-->>B: HTML form + CSRF token phù hợp
    B->>S: POST /web/profile + cookie + token
    S->>R: CSRF validation
    S->>C: Authorization, cập nhật có transaction
    C-->>B: Redirect tới GET (PRG)
    B->>S: POST /logout + cookie + CSRF
    S->>S: Logout và dọn phiên/authentication
    S-->>B: Redirect login theo policy
~~~

Giữ ý nghĩa của method:

- **GET** chỉ đọc hoặc render form; không tạo ra tác động nghiệp vụ như xóa đơn/đăng xuất ngay.
- **POST/PUT/PATCH/DELETE** xử lý thay đổi trạng thái và được CSRF filter kiểm tra theo matcher mặc định hoặc cấu hình.
- **POST login** vẫn có thể yêu cầu CSRF dù user **chưa đăng nhập** (login CSRF).
- **POST logout** cần token nếu ứng dụng dùng browser session; `GET /logout` có thể hiển thị xác nhận chứ không tự đăng xuất.
- **Post/Redirect/Get (PRG)** giúp tránh resubmit do Refresh, nhưng **không thay CSRF hoặc idempotency key**.

### 4.2. Session cookie và CSRF token không giống nhau

~~~http
Set-Cookie: JSESSIONID=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `JSESSIONID` là **credential tra phiên**, browser gửi tự động khi policy cho phép.
- `HttpOnly` hạn chế JavaScript đọc session ID, **không ngăn browser gửi cookie**.
- `SameSite=Lax/Strict` giảm nhiều ngữ cảnh cross-site nhưng không loại mọi trường hợp (đặc biệt same-site cross-origin); nó **không thay CSRF token**.
- CSRF token có thể được đưa vào **hidden form field** hoặc custom HTTP header; không đưa session ID vào form.

### 4.3. Khi browser dùng SPA thay HTML form

Với `fetch("/web/api/profile", {...})` sử dụng session cookie, SPA cần chủ động gửi token:

~~~javascript
const response = await fetch("/web/api/profile", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfTokenFromApp
  },
  body: JSON.stringify({ displayName: "Alice" })
});
~~~

`csrfTokenFromApp` phải được cấp từ repository/request handler qua HTML, meta tag hoặc endpoint JSON phù hợp, **không tự đoán token**. Với Spring Security Servlet, biểu diễn token gửi cho form có thể **XOR-masked**; SPA/cookie raw token có thể cần handler riêng theo version. Không giải quyết mismatch bằng cách tắt CSRF ở cả hệ thống.

Nếu frontend khác origin, browser còn phải tuân theo **CORS** và `fetch.credentials`; việc có CORS không làm CSRF biến mất khi authentication dựa vào cookie.

## 5. Luồng M2M: client credentials → access token → Resource Server

### 5.1. Không có browser user trong grant này

Trong OAuth 2.0 **client credentials grant**, một confidential client được Authorization Server xác thực và cấp access token để hoạt động theo **quyền của chính client**, không phải vì một nhân viên đang đăng nhập trang web.

~~~mermaid
sequenceDiagram
    participant M as Partner Worker
    participant AS as Authorization Server
    participant API as Spring Resource Server
    participant D as Job Service/Database

    M->>AS: POST token endpoint, grant_type=client_credentials
    AS->>AS: Xác thực client, kiểm policy, audience và scopes
    AS-->>M: access_token + expires_in + token_type Bearer
    M->>API: POST /integrations/jobs + Bearer token
    API->>API: Xác minh issuer/signature/audience/expiry
    API->>API: Kiểm tra SCOPE_jobs:write và client identity
    API->>D: Authorization theo partner/job, validate và ghi
    D-->>API: Kết quả
    API-->>M: 2xx hoặc lỗi máy có thể xử lý
~~~

**Lưu ý:** Spring Security OAuth2 Resource Server chỉ **kiểm tra** access token được gửi vào API; nó không mặc định là **Authorization Server** và không tự sinh token từ client credentials. Authorization Server có thể là sản phẩm/dịch vụ riêng được tin cậy.

### 5.2. Ví dụ request đến token endpoint

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_OF_CLIENT_ID_AND_SECRET

grant_type=client_credentials&scope=jobs%3Awrite
~~~

Đây là **minh họa của một phương thức client authentication tại Authorization Server**; token endpoint cũng có thể yêu cầu private_key_jwt hoặc mTLS tùy provider. `Authorization: Basic` trong request **server→Authorization Server** không chứng minh một Resource API cho browser có thể miễn CSRF nếu nó chấp nhận Basic auth.

Response:

~~~json
{
  "access_token": "opaque-access-token-value",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "jobs:write"
}
~~~

Token format có thể là opaque hoặc JWT; **không suy ra** chỉ từ trường `access_token`. Token này phải được cấp với **audience** cho Resource API, scope tối thiểu và TTL phù hợp.

### 5.3. Partner worker chủ động thêm Bearer

~~~http
POST /integrations/jobs HTTP/1.1
Host: platform.example.com
Authorization: Bearer opaque-access-token-value
Content-Type: application/json
Idempotency-Key: job-event-42

{"externalJobId":"42","state":"DONE"}
~~~

`Idempotency-Key` là một cơ chế ứng dụng tùy chọn để tránh tác động trùng khi client retry; nó **không phải CSRF token** và Resource Server không tự cung cấp đúng-once processing chỉ vì có header này.

Client M2M nên:

- Giữ **client credentials và access token** ở secret store/process memory theo chính sách, không hardcode vào repository;
- Sử dụng HTTPS/TLS verification, không ghi Bearer token vào request/response logs;
- Cache access token trong thời gian hợp lý, chủ động lấy token mới trước expiry theo policy;
- Xử lý `401` (token không được chấp nhận), `403` (thiếu scope/permission), `429`/`503` theo backoff có giới hạn;
- Không retry thao tác không idempotent mù quáng;
- Bảo vệ quyền theo **client/partner/tenant** và object-level authorization.

### 5.4. Không gán M2M client thành user tùy tiện

Với grant type `client_credentials`, token có thể có claim `client_id`, `azp` hoặc `sub` tùy Authorization Server. Không **giả định `sub` luôn là user hoặc luôn bằng client_id`**. Resource Server nên:

1. Xác minh token đến từ issuer tin cậy, dành cho audience đúng;
2. Đọc client identity từ claim được provider bảo đảm qua cấu hình;
3. Map client vào partner/service account được cấp quyền;
4. Kiểm tra partner đó có quyền trên `externalJobId`/tenant hay không;
5. Audit theo **client identity và tác động**, không tạo ra “người dùng Alice” nếu không có delegation hợp lệ.

Khi M2M thật sự thực hiện hành động **thay mặt user**, cần một **mô hình delegation/token exchange** có bằng chứng quyền riêng, không tự thêm userId vào JSON rồi coi đó là danh tính.

## 6. Phân vùng bảo mật theo nguồn credential, không theo Content-Type

Những suy luận sau **không đủ**:

- “Request có `Content-Type: application/json` nên không có CSRF.” Sai: browser vẫn có thể gửi cookie và server có thể nhận các request tương đương.
- “JWT là stateless nên không có CSRF.” Sai nếu JWT được đặt trong cookie.
- “M2M dùng `Authorization` nên không cần kiểm chứng token.” Sai: Bearer có thể hết hạn, bị đánh cắp, sai audience/scope.
- “CORS đã khóa origin nên POST không thể bị giả mạo.” Sai: CORS không chặn tất cả HTTP requests hoặc non-browser clients.
- “Có `SessionCreationPolicy.STATELESS` là chứng minh không có cookie fallback.” Chưa đủ nếu custom filter/gateway vẫn xác thực cookie.
- “Một request có Bearer header thì được bỏ qua CSRF ở mọi route.” Sai nếu route browser vẫn có thể xác thực bằng cookie.

**Nguyên tắc triển khai:** Tách theo `securityMatcher` và xác định rõ **một authentication entry point + credential contract** cho mỗi vùng, rồi kiểm thử toàn bộ trường hợp credential bị thiếu, sai, trùng hoặc rơi vào vùng khác.

## 7. Ma trận thiết kế trước khi code

| Thuộc tính | Browser chain | M2M Resource Server chain |
|---|---|---|
| URL | `/login`, `/logout`, `/web/**`, `/assets/**` | `/integrations/**` |
| Authentication | Form login hoặc browser SSO → session | OAuth2 Bearer access token |
| Authentication storage | `HttpSession`/`WebSession` | Không lưu security context vào browser session |
| CSRF | **Bật** với unsafe requests | Có thể **miễn** vì bearer-only đã chứng minh |
| Form login/HTTP Basic | Form login có kiểm soát | Tắt form login và HTTP Basic |
| JWT/opaque validation | Không mặc định là auth của browser | Issuer, signature/active, audience, timestamps, scopes |
| Authorization | Role + quyền user/tenant | Scope + quyền client/partner/tenant |
| Lỗi thiếu auth | Redirect login cho HTML hoặc 401 cho browser API | **401 Bearer** |
| Lỗi thiếu quyền | `403`/UI error | **403**, có thể Bearer insufficient_scope |
| CORS | Nếu SPA/browser JS khác origin | Thường không cần cho M2M HTTP clients |
| Session cookie | `Secure; HttpOnly; SameSite` phù hợp | Không dùng để authenticate |
| Audit | User identity + session context đã khử bí mật | Client identity + partner + token metadata đã khử bí mật |
| Testing | GET form → POST token đúng/thiếu/sai → logout | Bearer hợp lệ/không/khác audience/scope; cookie-only fail |

## 8. Servlet/Spring MVC: hai SecurityFilterChain không chồng lấn

### 8.1. Dependency và giả thiết

Ví dụ dưới đây dùng Spring Boot với Servlet MVC và Spring Security hiện đại, với những nhóm dependency tương ứng:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-oauth2-resource-server
spring-boot-starter-thymeleaf
spring-security-test                       (test scope)
spring-boot-starter-test                   (test scope)
~~~

Dùng version do Spring Boot BOM quản lý; tránh tự ghép các phiên bản Spring Security không tương thích. Ví dụ chưa cung cấp user store/password encoder thật; ứng dụng cần `UserDetailsService` hoặc authentication provider, cùng integration service và database của riêng nó.

**Security contract:**

- `/integrations/**`: **M2M Resource Server** kiểm Bearer JWT, không chấp nhận form login/Basic/session cookie.
- Các đường còn lại: **Browser chain** với form login, session cookie, CSRF cho unsafe request; route ngoài dự kiến phải có authentication/authorization hoặc deny theo policy.
- Một request chỉ đi qua **chain đầu tiên có matcher phù hợp**, không chạy cả hai liên tiếp.

### 8.2. Chain M2M ưu tiên cao và có phạm vi hẹp

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletHybridSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain machineToMachine(HttpSecurity http)
            throws Exception {

        return http
            .securityMatcher("/integrations/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/integrations/jobs")
                    .hasAuthority("SCOPE_jobs:write")
                .requestMatchers(HttpMethod.GET, "/integrations/jobs/**")
                    .hasAuthority("SCOPE_jobs:read")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))

            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)

            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))

            // Chỉ miễn khi chain này thật sự bearer-only.
            .csrf(AbstractHttpConfigurer::disable)

            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/assets/**", "/css/**", "/error"
                ).permitAll()
                .requestMatchers("/web/**").authenticated()
                // Không để URL mới tự động mở công khai.
                .anyRequest().authenticated()
            )
            .formLogin(login -> login
                .loginPage("/login")
                .defaultSuccessUrl("/web/profile", false)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
            )
            // CSRF bật cho browser POST/PUT/PATCH/DELETE.
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Ý nghĩa của từng quyết định:**

1. `@Order(1)` + `securityMatcher("/integrations/**")` khiến M2M requests chọn chain Bearer-only trước.
2. `/integrations/jobs` cần `SCOPE_jobs:write` cho POST; các method/path chưa dự kiến bị `denyAll()` thay vì chỉ cần Bearer bất kỳ.
3. `SessionCreationPolicy.STATELESS` ngăn chain này dùng session để khôi phục/lưu SecurityContext giữa request. Điều kiện bearer-only còn cần **audit custom filters/gateway**, không chỉ thuộc tính này.
4. `formLogin`, `httpBasic` và `logout` bị tắt ở **M2M chain** để tránh redirect/login/Basic auth hoặc logout endpoint lọt vào vùng integration.
5. `oauth2ResourceServer(...jwt)` sử dụng `JwtDecoder` được cấu hình. Spring không tự phát JWT tại Resource Server.
6. Chỉ M2M chain dùng `csrf(...disable)`; browser chain vẫn giữ CSRF. **Không copy disable vào browser chain**.
7. Browser chain không có `securityMatcher` nên là **fallback** cho URL không thuộc M2M chain. Để public health/actuator hoặc static endpoints, cần matcher/management-port policy minh bạch và test.
8. `.anyRequest().authenticated()` ở browser chain không thay authorization nghiệp vụ; controller/service vẫn cần kiểm tra user được thao tác trên resource cụ thể.
9. Nếu app có thêm Servlet Filter custom chạy ngoài Spring Security hoặc reverse proxy tự xác thực cookie, vẫn phải đánh giá **đường credential được chấp nhận**.

**Một lưu ý về chain order:** `requestMatchers` trong `authorizeHttpRequests` chỉ quyết định quyền **sau khi một chain đã được chọn**. Nó **không** thay `securityMatcher`. Đặt `@Order(2)` trước chain M2M và không giới hạn browser matcher có thể khiến request integration rơi vào form-login/session chain.

### 8.3. Không nên bật CORS chỉ vì có M2M

Các client như batch worker, CLI và server-to-server HTTP library **không cần** CORS của browser để gọi Resource API. Mẫu M2M ở trên không bắt buộc bật `http.cors()`.

Nếu một **SPA thật sự** sẽ gọi `/integrations/**` bằng Bearer header từ origin khác, đó là một client browser bổ sung: cần CORS allowlist và preflight trên chain M2M, đồng thời kiểm soát token trong browser và XSS. Đừng bật `Access-Control-Allow-Origin: *` hay phản chiếu mọi Origin chỉ vì đối tác HTTP không gửi header Origin.

## 9. Cấu hình Resource Server JWT cho client M2M

### 9.1. Issuer và khóa tin cậy

Một Spring Boot Resource Server có thể nhận issuer URI qua YAML:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/platform
~~~

URI ở đây là ví dụ; phải thay bằng **issuer thật được quản trị**. Resource Server sẽ sử dụng `JwtDecoder` phù hợp để xác minh chữ ký theo khóa tin cậy của issuer và các điều kiện token mặc định/được cấu hình.

**Cần bổ sung audience validation cho Resource API** theo API/phiên bản đang dùng. Token có chữ ký hợp lệ nhưng được cấp cho **API khác** không được dùng để gọi `/integrations/jobs`.

### 9.2. Những trường cần xác minh

| Claim/kiểm chứng | Yêu cầu |
|---|---|
| `iss` | Issuer đúng Authorization Server đáng tin |
| Signature/JWK/alg | Chữ ký hợp lệ; thuật toán/khóa đúng trust policy; key rotation |
| `aud` | Chứa định danh **Resource API** của platform |
| `exp` và `nbf` | Token còn hiệu lực trong cửa sổ thời gian phù hợp |
| `scope` hoặc `scp` | Quyền được cấp cho đúng operation |
| `client_id`/`azp`/`sub` | Xác định **client M2M** theo hợp đồng issuer, không giả định luôn là user |
| Token type/use | Chỉ nhận access token phù hợp, không dùng OIDC ID token làm API token |
| Tenant/partner binding | Client chỉ tác động tài nguyên được cấp quyền |
| Revocation/policy | Đánh giá TTL, thu hồi, introspection nếu cần |

### 9.3. Tùy biến JwtDecoder với audience validator

Ví dụ nếu Resource Server được cấu hình bằng trusted JWK Set URL, kết hợp issuer/timestamps và audience validator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class MachineJwtValidationConfig {

    private static final String ISSUER =
        "https://auth.example.com/realms/platform";

    private static final String JWKS =
        "https://auth.example.com/realms/platform/protocol/openid-connect/certs";

    private static final String AUDIENCE = "platform-integration-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token không dành cho integration API",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));

        return decoder;
    }
}
~~~

Đây là **phương án tùy biến bean decoder**, không phải mã cần thêm nếu cấu hình audience validation bằng properties/API khác của phiên bản đang dùng đã đủ. Khi thêm bean `JwtDecoder`, cần hiểu nó có thể thay thế lựa chọn decoder do auto-configuration tạo; không cấu hình nhiều nguồn JWT cạnh tranh rồi đoán cái nào đang được dùng.

**Không hardcode issuer/JWKS trong project production**; đưa vào cấu hình môi trường tin cậy và kiểm soát thay đổi. Không tải khóa ký theo một URL `jku` hay `iss` do chính token chưa xác minh tự quyết định mà không có trusted allowlist; đó có thể gây token confusion hoặc SSRF.

### 9.4. SCOPE_* không thay phân quyền theo partner

Spring Security Resource Server thường map scopes JWT từ các claim chuẩn như `scope`/`scp` thành authority dạng `SCOPE_jobs:write` tùy converter. Nhưng token có `jobs:write` không đồng nghĩa client được ghi trạng thái của **mọi job**.

Service phải so:

- Client identity đến từ **claim đã được issuer bảo đảm**;
- Partner/tenant của job và client;
- Loại operation client được quyền thực hiện;
- Idempotency/ordering/tính nhất quán của event;
- Quota, rate limit và audit trên danh tính M2M.

Nếu issuer dùng claim scope riêng hoặc mapping khác, cần cấu hình `JwtAuthenticationConverter` theo hợp đồng issuer và **kiểm thử authority thực**.

### 9.5. Khi chọn opaque access token

Một Authorization Server có thể phát **opaque token** thay vì JWT. Khi đó Resource Server sử dụng introspection và dữ liệu trả về từ Authorization Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Trong M2M security chain, thay:

~~~java
.oauth2ResourceServer(oauth -> oauth
    .jwt(Customizer.withDefaults()))
~~~

bằng:

~~~java
.oauth2ResourceServer(oauth -> oauth
    .opaqueToken(Customizer.withDefaults()))
~~~

Đó là **hai lựa chọn khác nhau theo định dạng/hợp đồng token**. `client-secret` dùng cho introspection phải lấy từ secret manager/environment đúng cách, không lưu plaintext vào Git. Resource Server cần xác minh token `active`, thời hạn/scope/audience theo introspection contract, tránh cache stale revocation không kiểm soát.

`Introspection` là cuộc gọi backend→Authorization Server, không phải CORS browser.

## 10. Servlet browser: render form có CSRF token

### 10.1. GET login tùy chỉnh

Khi `formLogin(login -> login.loginPage("/login"))` được đặt, ứng dụng cần cung cấp trang GET login:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class LoginController {

    @GetMapping("/login")
    String login() {
        return "auth/login"; // templates/auth/login.html
    }
}
~~~

Không tạo `@PostMapping("/login")` cạnh tranh với `UsernamePasswordAuthenticationFilter` nếu dùng formLogin processing URL mặc định. Form login POST sẽ do Spring Security xử lý; `permitAll` không có nghĩa miễn CSRF.

### 10.2. Thymeleaf form login

~~~html
<!-- templates/auth/login.html -->
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng nhập</title>
</head>
<body>
  <h1>Đăng nhập hệ thống</h1>

  <p th:if="${param.error}">Tài khoản hoặc mật khẩu không hợp lệ.</p>
  <p th:if="${param.logout}">Bạn đã đăng xuất.</p>

  <form action="/login" method="post">
    <label for="username">Tài khoản</label>
    <input id="username" name="username"
           autocomplete="username" required>

    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password" required>

    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">

    <button type="submit">Đăng nhập</button>
  </form>
</body>
</html>
~~~

`_csrf` là request attribute theo Spring Security MVC integration. Token khi render có thể được **XOR-masked**; không so sánh token HTML với raw expected token trong HttpSession theo cách đơn giản và không tự tạo token từ session ID.

Nếu sử dụng `th:action="@{/login}"` với Spring/Thymeleaf integration, CSRF hidden field **có thể được auto-insert** bởi request data value processor. Kiểm tra HTML cuối cùng để không gửi hai field `_csrf` trùng nhau. Khi ứng dụng deploy dưới context path `/portal`, URL cố định `/login` có thể sai; ưu tiên cơ chế URL theo context path và kiểm tra auto-insertion.

### 10.3. Controller form hồ sơ của user

~~~java
import java.security.Principal;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
class BrowserProfileController {

    private final BrowserProfileService profiles;

    BrowserProfileController(BrowserProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/web/profile")
    String form(Principal principal, Model model) {
        model.addAttribute(
            "displayName", profiles.displayNameOf(principal.getName()));
        return "web/profile";
    }

    @PostMapping("/web/profile")
    String update(Principal principal,
                  @RequestParam String displayName) {

        profiles.updateIfAuthorized(
            principal.getName(), displayName);

        return "redirect:/web/profile"; // Post/Redirect/Get
    }
}
~~~

`BrowserProfileService` là **service giả định của ứng dụng**, cần validation, database, kiểm tra object-level authorization, transaction và audit. Không tin `username` do client tự đưa trong form để quyết định user; ví dụ lấy principal do SecurityContext xác thực.

Trang `web/profile.html`:

~~~html
<form action="/web/profile" method="post">
  <label for="displayName">Tên hiển thị</label>
  <input id="displayName" name="displayName"
         th:value="${displayName}" required>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Lưu</button>
</form>

<form action="/logout" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Đăng xuất</button>
</form>
~~~

**Bảo mật UI:** Dùng auto-escaping như `th:text`/escaped attributes, không render input người dùng bằng HTML không escape. Mọi thao tác ghi phải có xác nhận quyền trên server, không chỉ ẩn nút theo role trong template.

### 10.4. Session fixation, timeout và logout

Một ứng dụng form login thường có cơ chế **session fixation protection** khi xác thực; session ID có thể đổi ở ranh giới login. CSRF token trước login cũng có thể bị xóa và cấp lại.

Với nhiều tab, tab A logout còn tab B vẫn giữ form/token cũ: POST từ tab B có thể bị `401`/redirect hoặc `403` theo trạng thái phiên. Đây có thể là hành vi an toàn đúng; UI nên có đường reload/đăng nhập lại, **không tắt CSRF để phục vụ form cũ**.

Nếu dùng remember-me/OIDC/SSO, local logout chưa chắc thu hồi mọi phiên hoặc access token ở IdP/partner; xác định rõ logout scope theo kiến trúc.

## 11. Servlet controller M2M và object-level authorization

M2M API có thể trả JSON thay vì view HTML. Mẫu controller dưới đây giả định token đã qua Bearer authentication trong chain `/integrations/**`:

~~~java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.*;

@RestController
class PartnerJobApi {

    private final PartnerJobService jobs;

    PartnerJobApi(PartnerJobService jobs) {
        this.jobs = jobs;
    }

    record JobUpdate(String externalJobId, String state) {}

    @PostMapping("/integrations/jobs")
    ResponseEntity<Map<String, String>> submit(
            JwtAuthenticationToken authentication,
            @RequestBody JobUpdate input) {

        String clientId = authentication.getToken()
            .getClaimAsString("client_id");

        if (clientId == null || clientId.isBlank()) {
            // App yêu cầu claim theo hợp đồng issuer.
            return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        }

        if (input.externalJobId() == null
                || input.externalJobId().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        // Service kiểm tra mapping client -> partner -> job.
        String receipt = jobs.applyIfAuthorized(
            clientId, input.externalJobId(), input.state());

        return ResponseEntity.status(HttpStatus.ACCEPTED)
            .body(Map.of("receiptId", receipt));
    }
}
~~~

**Điều kiện:** `JwtAuthenticationToken` áp dụng khi M2M chain dùng JWT. Nếu chọn opaque token, principal/claims API khác: phải đọc client identity từ `OAuth2AuthenticatedPrincipal`/token introspection theo hợp đồng, không cast sang JWT.

**Quan trọng:** Ví dụ dùng claim `client_id` do **issuer bảo đảm và decoder đã xác minh**. Một số issuer dùng `azp`/`sub` cho client credentials; cần map rõ và test, không suy luận clientId từ JSON request.

`PartnerJobService` cần implement validation, partner isolation, replay/idempotency, trạng thái hợp lệ và audit. **Không tin clientId do request body gửi**, kể cả đã có access token hợp lệ.

### 11.1. Máy không phải user của browser

Trong `client_credentials` grant, không có danh tính Alice “đang thao tác màn hình” trừ khi giao thức delegation rõ ràng. Audit nên phân biệt:

~~~text
Actor type: MACHINE
Client ID: partner-worker-42
Partner: partner-42
Operation: submit-job-state
Resource: job-42
Token scope: jobs:write
Outcome: allowed/denied
~~~

và:

~~~text
Actor type: HUMAN
User ID: alice
Session auth: web-login
Operation: edit-profile
Outcome: allowed/denied
~~~

Không log access token/session ID thô và không đưa claims nhạy cảm vào telemetry không có kiểm soát.

## 12. M2M OAuth2 client: cách lấy access token đúng nơi

### 12.1. ClientRegistration nằm ở phía gọi API

Trong một dịch vụ worker Java dùng Spring Security OAuth2 Client, cấu hình grant `client_credentials` có thể là:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          platform-partner:
            provider: platform-issuer
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: jobs:write
        provider:
          platform-issuer:
            token-uri: https://auth.example.com/oauth2/token
~~~

**Đây là cấu hình của M2M client**, không phải cấu hình nhận Bearer token của Resource Server. Giá trị `PARTNER_CLIENT_SECRET` phải đến từ secret manager hoặc môi trường an toàn, không commit vào Git. Các ví dụ dùng placeholder `${...}` trong source tài liệu sẽ được thay bằng cấu hình biến môi trường thực tại project.

### 12.2. Spring Security OAuth2AuthorizedClientManager cho service

Ví dụ với OAuth2 Client API không phụ thuộc Servlet request:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

@Configuration
class PartnerClientCredentialsConfig {

    @Bean
    OAuth2AuthorizedClientManager partnerAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService clients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, clients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Đây là code dành cho **client worker Spring application**, cần thêm `spring-boot-starter-oauth2-client` hoặc dependency OAuth2 Client phù hợp, không phải bean cần nhét vào Resource Server chỉ để kiểm chứng token.

### 12.3. Lấy token và gửi HTTP request

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

class PartnerTokenSupplier {

    private final OAuth2AuthorizedClientManager manager;

    PartnerTokenSupplier(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String currentToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("platform-partner")
                .principal("partner-batch-service")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null || client.getAccessToken() == null) {
            throw new IllegalStateException(
                "Không được cấp access token cho worker");
        }

        return client.getAccessToken().getTokenValue();
    }
}
~~~

`principal("partner-batch-service")` ở đây là **key quản lý authorized client của service**, không tự khẳng định đó là người dùng Alice. Client credential vẫn được xác thực bởi Authorization Server theo registration.

Một lời gọi Java HTTP client minh họa:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

class PartnerApiCaller {

    private final PartnerTokenSupplier tokenSupplier;
    private final HttpClient http = HttpClient.newHttpClient();

    PartnerApiCaller(PartnerTokenSupplier tokenSupplier) {
        this.tokenSupplier = tokenSupplier;
    }

    int sendJobState(String jobId) throws Exception {
        // Mẫu đơn giản; ứng dụng thật dùng JSON serializer,
        // input validation và idempotency key.
        String json = "{\"externalJobId\":\"" + jobId
            + "\",\"state\":\"DONE\"}";

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://platform.example.com/integrations/jobs"))
            .header("Authorization",
                "Bearer " + tokenSupplier.currentToken())
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json))
            .build();

        HttpResponse<Void> response = http.send(
            request, HttpResponse.BodyHandlers.discarding());

        return response.statusCode();
    }
}
~~~

**Lưu ý demo:** Không tự nối chuỗi JSON từ input bên ngoài trong production; dùng JSON serializer và validate dữ liệu. Với retry, network failure, token expiry và secret rotation, thêm policy/backoff/observability có kiểm soát. Tránh gửi Bearer token tới origin không tin cậy hoặc theo redirect bất ngờ.

### 12.4. Token lifecycle và retry

| Tình huống | Hành động của M2M client |
|---|---|
| Token gần hết hạn | Xin/cấp token mới theo OAuth2 Client manager/provider policy |
| Token invalid/expired, API 401 | Làm rõ lỗi issuer/token và làm mới tối đa theo policy, không loop vô hạn |
| Không đủ scope, API 403 | Không lặp request với cùng quyền; sửa policy/cấp scope theo quy trình |
| API trả 429/503 | Retry có backoff, jitter, retry budget và idempotency |
| Kết nối timeout sau POST | Không biết server đã ghi hay chưa; dùng idempotency key nếu nghiệp vụ cần |
| Client secret rotation | Quản lý secret ở store; deploy/rotate an toàn, tránh outage |
| Access token bị lộ | Thu hồi/rotate theo provider, giảm scope/TTL, kiểm tra audit |
| M2M không còn quyền của partner | Thu hồi mapping và kiểm tra resource authorization, không chỉ đợi JWT hết hạn |

## 13. Reactive/WebFlux: hai SecurityWebFilterChain cùng một ứng dụng

### 13.1. Đừng sao chép Servlet classes vào WebFlux

Cùng một threat model browser/M2M, nhưng cơ chế thực thi có API khác:

| Trách nhiệm | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| URL matcher chain | `securityMatcher(...)` | `securityMatcher(ServerWebExchangeMatcher)` |
| Session | `HttpSession` | `WebSession` |
| Session-based CSRF | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| CSRF filter | `CsrfFilter` | `CsrfWebFilter` |
| Authentication context persistence | Servlet `SecurityContextRepository` | Reactive `ServerSecurityContextRepository` |
| JWT validator | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque validation | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Test | `MockMvc` | `WebTestClient` |

Trình duyệt vẫn tự gắn cookie cho đường browser và máy M2M vẫn tự đặt Bearer header. Dùng Reactor/Netty không tự loại CSRF, cũng không tự làm JWT audience validation.

### 13.2. M2M WebFilterChain: không lưu browser session

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
class ReactiveHybridSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain integrations(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/integrations/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.POST, "/integrations/jobs")
                    .hasAuthority("SCOPE_jobs:write")
                .pathMatchers(HttpMethod.GET, "/integrations/jobs/**")
                    .hasAuthority("SCOPE_jobs:read")
                .anyExchange().denyAll()
            )
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .logout(ServerHttpSecurity.LogoutSpec::disable)
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            // Chỉ trên đường M2M Bearer-only đã được chứng minh.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browser(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/login", "/assets/**", "/error").permitAll()
                .pathMatchers("/web/**").authenticated()
                .anyExchange().authenticated()
            )
            .formLogin(login -> login.loginPage("/login"))
            .logout(Customizer.withDefaults())
            .csrf(csrf -> csrf.csrfTokenRepository(
                new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
~~~

**Cần chú ý:**

- Browser chain được đặt sau chain `/integrations/**` và giữ CSRF. Mọi WebSession cookie login chỉ được dùng cho browser route theo policy.
- `NoOpServerSecurityContextRepository` không lưu M2M authentication vào WebSession; token được xác thực trên request hiện hành.
- `oauth2ResourceServer().jwt()` cần `ReactiveJwtDecoder` tin cậy với issuer/audience/expiry/algorithm policy; properties không tự thay object-level authorization.
- Không tự thêm `CookieServerCsrfTokenRepository` vào M2M chain. Nếu browser SPA dùng cookie repository cho `/web/api/**`, cần cấu hình request handler/raw token có chủ đích trong **browser chain**.
- Nếu project có nhiều `SecurityWebFilterChain`, test @Order và matcher trên **URL thực tế sau proxy**. Route ngoài thiết kế không nên mở công khai.
- Logout behavior với WebSession có thể khác Servlet. Nếu yêu cầu **invalidate toàn WebSession**, dùng handler/policy phù hợp (ví dụ `WebSessionServerLogoutHandler`) và xác minh sau logout; không mặc nhiên khẳng định logout luôn xóa mọi state.
- Các class trong code là dành cho **WebFlux**, không đặt song song trong cùng ứng dụng chạy Servlet để rồi không rõ loại chain nào xử lý.

### 13.3. JWT validation cho Reactive

Trong project WebFlux, có thể dùng issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/platform
~~~

Nếu cần audience validator riêng, dùng `ReactiveJwtDecoder` và validator phù hợp, ví dụ `NimbusReactiveJwtDecoder` với trusted JWKS + `JwtValidators.createDefaultWithIssuer` và `OAuth2TokenValidator<Jwt>`. Khi tạo bean decoder tùy biến, phải biết nó thay/ghi đè auto configuration ở phạm vi nào.

Nếu issuer phát opaque token, thay cấu hình JWT trong Resource Server chain bằng `opaqueToken(...)` cùng `ReactiveOpaqueTokenIntrospector` tin cậy; không giả định opaque token có ba phần JWT để parse.

### 13.4. WebFlux form login GET: token reactive được resolve

Trong các cấu hình `CsrfWebFilter` phổ biến, exchange chứa `Mono<CsrfToken>`. GET login có thể đưa token đã resolve vào model:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveLoginController {

    @GetMapping("/login")
    Mono<Rendering> login(ServerWebExchange exchange) {
        Mono<CsrfToken> publisher =
            exchange.getAttribute(CsrfToken.class.getName());

        return publisher.map(token ->
            Rendering.view("auth/login")
                .modelAttribute("_csrf", token)
                .build());
    }
}
~~~

Đây là ví dụ dựa trên exchange attribute do `CsrfWebFilter` cung cấp. Khi dùng custom handler hoặc Spring version khác, kiểm tra API để đảm bảo token được cấp cho template. **Không gọi `block()` trên publisher trong reactive controller**.

Template có thể dùng hidden `_csrf` như Servlet; token vẫn phải thuộc đúng WebSession/request handler.

### 13.5. WebFlux form GET và POST dùng WebSession

Một service reactive giả định:

~~~java
interface ReactiveBrowserProfileService {
    reactor.core.publisher.Mono<String> displayNameOf(String username);
    reactor.core.publisher.Mono<Void> updateIfAuthorized(
        String username, String displayName);
}
~~~

Controller minh họa:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveBrowserProfileController {

    private final ReactiveBrowserProfileService profiles;

    ReactiveBrowserProfileController(
            ReactiveBrowserProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/web/profile")
    Mono<Rendering> view(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf =
            exchange.getAttribute(CsrfToken.class.getName());

        return Mono.zip(exchange.getPrincipal(), csrf)
            .flatMap(pair -> profiles
                .displayNameOf(pair.getT1().getName())
                .map(name -> Rendering.view("web/profile")
                    .modelAttribute("displayName", name)
                    .modelAttribute("_csrf", pair.getT2())
                    .build()));
    }

    @PostMapping("/web/profile")
    Mono<String> update(ServerWebExchange exchange) {
        // WebFlux xử lý form data qua ServerWebExchange.
        return Mono.zip(
                exchange.getPrincipal(),
                exchange.getFormData())
            .flatMap(pair -> {
                String name = pair.getT2().getFirst("displayName");

                if (name == null || name.isBlank()) {
                    return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Tên không hợp lệ"));
                }

                return profiles.updateIfAuthorized(
                    pair.getT1().getName(), name);
            })
            .thenReturn("redirect:/web/profile");
    }
}
~~~

Một chi tiết đáng lưu ý: với WebFlux, để đọc `application/x-www-form-urlencoded` body, `exchange.getFormData()` là API minh bạch cho request form; không sao chép mọi giả định `@RequestParam` từ Spring MVC sang WebFlux. CSRF web filter đã xác minh submitted token trước khi controller được gọi.

`ReactiveBrowserProfileService` phải được triển khai bằng data access phù hợp; tránh gọi JDBC blocking trên event-loop. Phân quyền theo user/tenant vẫn ở service.

## 14. WebFlux M2M controller theo client identity

Với JWT Resource Server chain, WebFlux có thể lấy authenticated principal từ `ServerWebExchange`:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
class ReactivePartnerJobApi {

    private final ReactivePartnerJobService jobs;

    ReactivePartnerJobApi(ReactivePartnerJobService jobs) {
        this.jobs = jobs;
    }

    record JobUpdate(String externalJobId, String state) {}

    @PostMapping("/integrations/jobs")
    Mono<ResponseEntity<Map<String, String>>> submit(
            ServerWebExchange exchange,
            @RequestBody Mono<JobUpdate> input) {

        return Mono.zip(exchange.getPrincipal(), input)
            .flatMap(pair -> {
                JwtAuthenticationToken authentication =
                    (JwtAuthenticationToken) pair.getT1();

                String clientId = authentication.getToken()
                    .getClaimAsString("client_id");

                if (clientId == null || clientId.isBlank()) {
                    return Mono.error(new ResponseStatusException(
                        HttpStatus.FORBIDDEN, "Client identity thiếu"));
                }

                JobUpdate update = pair.getT2();
                if (update.externalJobId() == null
                        || update.externalJobId().isBlank()) {
                    return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "externalJobId bắt buộc"));
                }

                return jobs.applyIfAuthorized(
                        clientId,
                        update.externalJobId(),
                        update.state())
                    .map(receipt -> ResponseEntity
                        .status(HttpStatus.ACCEPTED)
                        .body(Map.of("receiptId", receipt)));
            });
    }
}
~~~

`ReactivePartnerJobService` giả định trả `Mono<String>`; cần validate state, partner/job ownership, idempotency và transactional semantics phù hợp. Với opaque token, kiểu authentication/principal khác: không cast cố định sang `JwtAuthenticationToken`.

**Tuyệt đối không dùng `clientId` do request JSON tự khai để bỏ qua claim đã được Authorization Server xác thực.** `client_id` có thể không phải tên claim của mọi issuer; thiết kế adapter rõ ràng nếu hỗ trợ nhiều issuer.

## 15. Browser CORS, M2M và reverse proxy

### 15.1. Có cần CORS cho M2M không?

**Không, nếu client là service/CLI/native HTTP library.** CORS là chính sách thực thi bởi browser khi JavaScript gọi tài nguyên khác origin. Server-to-server client có thể gọi API trực tiếp với Bearer header không chịu browser CORS.

Nhưng nếu hệ thống cũng có SPA gọi **browser session API** ở origin khác:

~~~text
SPA: https://spa.example.com
Browser API: https://platform.example.com/web/api/profile
~~~

thì browser API cần CORS allowlist, preflight, `credentials:"include"` và cookie policy phù hợp; **vẫn cần CSRF token** trên POST vì session cookie là credential tự gửi.

CORS configuration không được khiến M2M route nhận thêm session cookie như một authentication method.

### 15.2. Ví dụ Servlet CORS chỉ cho browser API (nếu cần)

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class BrowserApiCorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cfg = new CorsConfiguration();
        cfg.setAllowedOrigins(List.of("https://spa.example.com"));
        cfg.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        cfg.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN"));
        cfg.setAllowCredentials(true);
        cfg.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/web/api/**", cfg);
        return source;
    }
}
~~~

Để sử dụng nó, thêm `.cors(Customizer.withDefaults())` vào **browser chain** tương ứng, không nhất thiết vào M2M chain. Preflight phải được CORS xử lý trước yêu cầu session authentication. Nếu SPA/API khác site, phải đánh giá `SameSite=None; Secure` và **third-party cookie blocking**, không chỉ CORS.

**Không** dùng `Access-Control-Allow-Origin: *` với `Access-Control-Allow-Credentials: true`. Không phản chiếu mọi Origin; server chỉ cho những frontend có kiểm soát được đọc response/CSRF token theo policy.

### 15.3. Đối với SPA cùng origin, đơn giản hơn

Nếu HTML/assets và `/web/api/**` cùng `https://platform.example.com` qua reverse proxy, `fetch("/web/api/...")` thường **không cần CORS**, nhưng vẫn phải gửi CSRF token trong header khi POST dựa trên session cookie.

M2M `/integrations/**` vẫn dùng Bearer token từ client chủ động gửi. Có thể có cùng hostname public nhưng **route, chain, credential** vẫn cần tách.

### 15.4. Reverse proxy phải giữ hợp đồng đường dẫn

~~~mermaid
flowchart LR
    B[Browser] --> P[HTTPS reverse proxy]
    M[M2M service] --> P
    P -->|/web/**, /login, /logout| W[Browser chain]
    P -->|/integrations/**| I[Bearer-only chain]
    P -->|/assets/**| S[Static assets]
~~~

Khi triển khai Nginx/gateway:

- Không tự rewrite `/integrations/jobs` thành `/jobs` nếu Spring matcher/route mong đợi `/integrations/**`.
- Không thêm `Authorization` từ session cookie vào M2M path trừ khi gateway/BFF **đã được thiết kế và bảo vệ ranh giới browser**.
- Không gỡ `Authorization` header do M2M gửi, không ghi raw token vào access logs.
- Chỉ tin `Forwarded`/`X-Forwarded-*` từ proxy đáng tin cậy; không nhận trực tiếp spoofed host/scheme từ Internet.
- Xác minh backend không bị truy cập thẳng qua cổng nội bộ từ Internet để bỏ qua TLS/WAF/gateway policy.
- Nếu upstream route tách sang dịch vụ khác, giữ việc kiểm chứng access token/authorization tại Resource Server hoặc gateway đáng tin cậy theo kiến trúc; không tin request chỉ vì xuất phát từ mạng nội bộ.
- Có thể áp **rate limit riêng** cho browser session và M2M client; phân biệt user/partner trong audit.

### 15.5. Một ví dụ Nginx URL routing giản lược

~~~nginx
# Chỉ minh họa định tuyến; production cần TLS, timeouts, WAF,
# headers, logging policy và upstream health phù hợp.
server {
    listen 443 ssl;
    server_name platform.example.com;

    ssl_certificate     /etc/ssl/example/platform.crt;
    ssl_certificate_key /etc/ssl/example/platform.key;

    location /integrations/ {
        proxy_pass http://spring-platform:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }

    location /web/ {
        proxy_pass http://spring-platform:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }

    location /login {
        proxy_pass http://spring-platform:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /logout {
        proxy_pass http://spring-platform:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
~~~

**Đây không phải cấu hình proxy đầy đủ.** Mẫu `proxy_pass http://spring-platform:8080;` không có URI suffix giúp giữ đường dẫn public theo dạng minh họa. Nếu viết `proxy_pass .../;` trong `location /integrations/`, Nginx có thể **thay prefix** gây route/matcher lệch.

CORS preflight (nếu có) vẫn phải tới browser security configuration thích hợp, không bị redirect login. Việc proxy thêm/xóa Cookie/Authorization phải được kiểm tra theo từng nhóm route.

## 16. Cookie, CSP, HSTS và HTTP firewall trong hệ thống hỗn hợp

### 16.1. Cookie phiên browser

Cookie session ví dụ:

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `Secure` yêu cầu HTTPS đúng giữa browser và edge.
- `HttpOnly` giảm rủi ro JS đọc trực tiếp session ID nhưng browser vẫn tự gắn cookie.
- `SameSite=Lax/Strict` giới hạn các ngữ cảnh cookie cross-site, **không thay CSRF**.
- `Domain` host-only khi không có Domain phù hợp nếu chỉ một host cần cookie; không mở rộng tới mọi subdomain để “giải quyết” nhầm lỗi.
- `Path` cần khớp URL public; không phải ranh giới authorization mạnh giữa các app cùng host.

Nếu Servlet app dùng Spring Boot và tạo cookie bằng Servlet container, có thể cấu hình ví dụ:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Nếu dùng Spring Session/custom serializer hoặc WebFlux WebSession, phải cấu hình **nơi thực sự phát cookie**, kiểm tra response `Set-Cookie` sau proxy.

### 16.2. HSTS, HTTPS và TLS cho cả browser/M2M

- Browser public host nên dùng HTTPS và có thể phát `Strict-Transport-Security` theo chính sách; `includeSubDomains`/preload chỉ khi toàn phạm vi host đã sẵn sàng.
- M2M client phải **xác minh server certificate**. HSTS là chính sách browser, không phải bằng chứng mọi M2M HTTP library sẽ tuân theo HSTS.
- Nếu client credentials hay Bearer token truyền qua HTTP, kẻ nghe lén có thể đánh cắp token; luôn dùng TLS.
- Đối với partner nhạy cảm, xem xét **mTLS, DPoP hoặc sender-constrained token** phù hợp với Authorization Server; không tự tuyên bố token Bearer đã chống replay.
- Reverse proxy terminate TLS cần chuyển scheme/host đúng và không lộ secrets trong logs.

### 16.3. CSP và XSS thuộc phía browser

Nếu browser HTML do Spring/Thymeleaf render hoặc Nginx phục vụ, CSP cần nằm trên **HTML response đó**.

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Ví dụ này là **định hướng**; chính sách production cần điều chỉnh theo tài nguyên frontend, nonce/hash/Trusted Types khi phù hợp. CSP không thay escaping/sanitization, session/CSRF hoặc quyền trên tài nguyên.

Nếu SPA khác origin gọi browser API, CSP trên SPA cần `connect-src` cho API origin; API vẫn phải cấu hình CORS riêng. CSP chỉ có trên JSON M2M response **không tự bảo vệ HTML browser**.

### 16.4. Security headers của M2M API

Một API JSON không trình bày HTML vẫn có các nghĩa vụ response:

- `Cache-Control: no-store` hoặc policy private phù hợp với dữ liệu nhạy cảm;
- `Content-Type: application/json` đúng và `X-Content-Type-Options: nosniff` khi phù hợp;
- `WWW-Authenticate: Bearer ...` trong lỗi xác thực/quyền theo RFC 6750;
- Hạn chế thông tin lỗi, không echo JWT/opaque token;
- Không vô ý trả HTML login redirect cho worker;
- Không để proxy/CDN cache response private và trộn dữ liệu giữa partners.

Không xem CSP/X-Frame-Options trên JSON là thay thế cho JWT validation, issuer/audience/scope hay object-level authorization.

### 16.5. HTTP firewall và chain matching

HTTP firewall giúp tránh một số request/path bất thường trước khi matcher xử lý. Proxy path rewrite, encoded slashes, semicolons, duplicate slashes hoặc host forwarding có thể khiến chain/endpoint bị chọn sai.

**Đừng nới lỏng `StrictHttpFirewall` toàn cục** để sửa route client gửi sai. Hãy chuẩn hóa URL contract, kiểm tra phương thức/path được phép và thêm regression test cho request boundary.

## 17. Nguyên tắc lỗi và observability của hai nhóm

| Tình huống | Browser chain | M2M chain |
|---|---|---|
| Chưa đăng nhập | Redirect `/login` cho HTML, 401 cho browser API nếu được cấu hình | `401 Unauthorized` Bearer |
| Auth hợp lệ nhưng thiếu quyền | `403` hoặc UI error | `403 Forbidden` |
| CSRF thiếu/sai trên POST | Thường `403` và không side effect | Không kiểm CSRF ở chain bearer-only đã chứng minh |
| JWT sai issuer/audience/expiry | Không dùng JWT làm browser auth trong ví dụ | `401` |
| Token đủ scope nhưng sai partner/job | Kiểm quyền user nếu endpoint browser | `403`/`404` theo resource authorization |
| CORS preflight | Phải xử lý trước auth nếu SPA khác origin | Không cần trừ khi M2M route cũng phục vụ browser |
| Logout | POST với CSRF, dọn browser session | M2M không có browser logout; xoay/thu hồi token/secret theo OAuth |
| Thông tin trong log | User/session metadata đã mask | Client ID/partner/correlation ID, không log Bearer |

**Không** ghi toàn bộ `Cookie`, `Set-Cookie`, `Authorization`, `X-CSRF-TOKEN`, access token, refresh token hoặc client secret vào logs, tracing hay support tickets. Trường metadata hữu ích hơn là chain được chọn, method/path, principal type (HUMAN/MACHINE), authentication outcome, scope failure và request correlation ID.

## 18. Ma trận kiểm thử: chứng minh hai đường bảo mật không lẫn nhau

### 18.1. Ca kiểm thử tối thiểu theo endpoint

| ID | Đường request | Credential và token | Kết quả kỳ vọng |
|---|---|---|---|
| **HY-01** | `GET /login` | Chưa xác thực | HTML login có CSRF token |
| **HY-02** | `POST /login` | Credentials hợp lệ + CSRF token đúng | Login thành công theo policy |
| **HY-03** | `POST /login` | Credentials hợp lệ nhưng thiếu/sai CSRF | Bị từ chối, không tạo phiên xác thực |
| **HY-04** | `GET /web/profile` | Session browser hợp lệ | Trả trang đúng user, không đổi dữ liệu |
| **HY-05** | `POST /web/profile` | Session browser + CSRF đúng | Qua CSRF, cập nhật nếu đủ quyền |
| **HY-06** | `POST /web/profile` | Session browser nhưng thiếu CSRF | `403`, **không có side effect** |
| **HY-07** | `POST /web/profile` | Session browser + CSRF sai | `403`, không có side effect |
| **HY-08** | `POST /logout` | Session browser + CSRF đúng | Logout và bảo đảm session cũ không còn authenticated |
| **HY-09** | `POST /logout` | Session browser nhưng thiếu CSRF | Bị từ chối, không logout |
| **HY-10** | `POST /integrations/jobs` | Bearer JWT hợp lệ + scope write | Qua Resource Server, xử lý theo partner |
| **HY-11** | `POST /integrations/jobs` | Không có Bearer | `401`, không tạo job |
| **HY-12** | `POST /integrations/jobs` | **Chỉ có session cookie hợp lệ** của browser | **`401`/không được xác thực**, không tạo job |
| **HY-13** | `POST /integrations/jobs` | Bearer hợp lệ **và** cookie browser bất kỳ | Quyền xác định theo Bearer client; không nâng quyền bằng session |
| **HY-14** | `POST /integrations/jobs` | JWT sai signature/issuer/audience/expiry | `401`, không có side effect |
| **HY-15** | `POST /integrations/jobs` | JWT đúng nhưng thiếu `jobs:write` | `403`, không tạo job |
| **HY-16** | `POST /integrations/jobs` | JWT đủ scope, client không sở hữu job | `403`/`404` theo policy, không có side effect |
| **HY-17** | `POST /web/profile` | Chỉ Bearer token M2M, **không session browser** | Không được nhận như user đã login |
| **HY-18** | `GET /integrations/jobs/{id}` | Bearer đủ scope đọc, đúng partner | Trả dữ liệu được phép |
| **HY-19** | `GET /integrations/jobs/{id}` | Bearer partner A, resource partner B | Từ chối, không lộ dữ liệu |
| **HY-20** | Một route không khai báo | Cookie hoặc Bearer không đúng vùng | Không bị mở công khai/không rơi chain sai |
| **HY-21** | `OPTIONS /web/api/**` nếu SPA khác origin | Preflight không có cookie | CORS được xử lý theo allowlist trước auth |
| **HY-22** | `OPTIONS /integrations/**` từ browser | Chưa được cấp CORS nếu không có client-browser contract | Không hiểu CORS là authentication |
| **HY-23** | M2M request sau rotation | Access token mới/old expired | Token cũ không hợp lệ, token mới đúng policy |
| **HY-24** | Browser form mở lâu qua logout/login lại | CSRF token cũ + session đã thay | Từ chối an toàn, không ghi dữ liệu |
| **HY-25** | Retry M2M POST với cùng idempotency key | Bearer hợp lệ, event lặp | Theo thiết kế idempotency, không ghi trùng |
| **HY-26** | API qua reverse proxy | Public path/headers chuẩn | Chọn đúng chain, auth/CSRF policy giữ nguyên |

**Ca HY-12 và HY-17 là hai phép thử ranh giới cốt lõi.** Chúng bảo đảm không thể dùng session của browser để thực hiện quyền của machine và không thể dùng machine token như một login phiên người dùng.

### 18.2. Kết quả âm phải gồm side-effect assertion

Với những request bị từ chối, đừng dừng tại `401`/`403`.

~~~text
Trước: partnerJobs.count("partner-42") = 12
Gửi POST /integrations/jobs với cookie browser, không Bearer
HTTP: 401 theo M2M chain
Sau: partnerJobs.count("partner-42") = 12
Event: không có JobSubmitted
Audit success: không có
~~~

Với browser:

~~~text
Trước: profile(Alice).displayName = "Alice"
Gửi POST /web/profile với session Alice, thiếu _csrf
HTTP: 403 theo browser CSRF policy
Sau: profile(Alice).displayName = "Alice"
Event: không có ProfileChanged
~~~

Bộ kiểm thử nên dùng data fixture riêng cho từng test và kiểm tra DB/event store sau request; một filter không nên cho controller ghi dữ liệu rồi mới trả lỗi.

## 19. MockMvc: hai chain trong Servlet test

### 19.1. Positive M2M POST bằng `jwt()` test helper

`spring-security-test` cho phép tạo mock authenticated JWT principal cho `MockMvc`. Ví dụ dưới đây giả định `PartnerJobService` được cấu hình fake/test để chấp nhận job và trả receipt, controller `/integrations/jobs` trả `202 Accepted`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HybridMachineServletTests {

    @Autowired MockMvc mvc;

    @Test
    void machineBearerWithScopeCanPostWithoutCsrfToken()
            throws Exception {

        mvc.perform(post("/integrations/jobs")
                .with(jwt()
                    .jwt(j -> j
                        .subject("partner-worker")
                        .claim("client_id", "partner-worker-42"))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_jobs:write")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"externalJobId\":\"42\","
                    + "\"state\":\"DONE\"}"))
            .andExpect(status().isAccepted());
    }

    @Test
    void missingBearerIsUnauthorized() throws Exception {
        mvc.perform(post("/integrations/jobs")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"externalJobId\":\"42\","
                    + "\"state\":\"DONE\"}"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void bearerWithoutWriteScopeIsForbidden() throws Exception {
        mvc.perform(post("/integrations/jobs")
                .with(jwt()
                    .jwt(j -> j
                        .subject("partner-worker")
                        .claim("client_id", "partner-worker-42"))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_jobs:read")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"externalJobId\":\"42\","
                    + "\"state\":\"DONE\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Giới hạn quan trọng:** `with(jwt())` gắn mock JWT principal và authorities trong test; nó **không chạy cryptographic verification** của một access token thực qua JWKs/issuer/audience/expiry. Vì vậy bài test này chứng minh rule scope và khả năng route không yêu cầu CSRF, **chưa chứng minh JWT decoder được cấu hình đúng**.

### 19.2. Cookie-only M2M phải bị từ chối

Test đơn giản với cookie giả:

~~~java
import jakarta.servlet.http.Cookie;

@Test
void randomSessionCookieDoesNotAuthenticateMachineApi()
        throws Exception {

    mvc.perform(post("/integrations/jobs")
            .cookie(new Cookie("JSESSIONID", "not-a-real-session"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"externalJobId\":\"42\","
                + "\"state\":\"DONE\"}"))
        .andExpect(status().isUnauthorized());
}
~~~

Test này cần đặt **trong class có `MockMvc mvc`**. Nó chỉ kiểm tra **cookie giả** không được chấp nhận. Test quan trọng hơn phải dùng **browser session đã đăng nhập thật**.

Có thể mô phỏng một `HttpSession` chứa SecurityContext của browser để kiểm tra chính sách stateless:

~~~java
import java.util.List;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Test
void machineChainIgnoresBrowserSessionAuthentication()
        throws Exception {

    SecurityContext browserContext =
        SecurityContextHolder.createEmptyContext();

    browserContext.setAuthentication(
        new UsernamePasswordAuthenticationToken(
            "alice",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        ));

    MockHttpSession loggedInBrowserSession = new MockHttpSession();
    loggedInBrowserSession.setAttribute(
        HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY,
        browserContext);

    mvc.perform(post("/integrations/jobs")
            .session(loggedInBrowserSession)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"externalJobId\":\"42\","
                + "\"state\":\"DONE\"}"))
        .andExpect(status().isUnauthorized());
}
~~~

Đây là **kiểm thử mô phỏng một valid SecurityContext**, không phải browser login/password end-to-end. Nó chỉ có ý nghĩa nếu `SecurityFilterChain` M2M thật sự hoạt động trong `MockMvc` và `SessionCreationPolicy.STATELESS` được áp.

**Tầng tích hợp cần có:** Đăng nhập browser qua `POST /login` **thật** với user fixture, ghi nhận session cookie server cấp, rồi gọi `/integrations/jobs` chỉ bằng cookie đó và không Bearer. Request phải bị từ chối; kiểm tra cả dữ liệu nghiệp vụ.

### 19.3. Browser POST thiếu/sai CSRF vẫn phải bị từ chối

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;

@SpringBootTest
@AutoConfigureMockMvc
class HybridBrowserServletTests {

    @Autowired org.springframework.test.web.servlet.MockMvc mvc;

    @Test
    void browserPostWithCorrectCsrfGoesThrough() throws Exception {
        mvc.perform(post("/web/profile")
                .with(user("alice"))
                .with(csrf())
                .param("displayName", "Alice New"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/web/profile"));
    }

    @Test
    void browserPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/web/profile")
                .with(user("alice"))
                .param("displayName", "Must Not Save"))
            .andExpect(status().isForbidden());
    }

    @Test
    void browserPostWithWrongCsrfIsRejected() throws Exception {
        mvc.perform(post("/web/profile")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("displayName", "Must Not Save"))
            .andExpect(status().isForbidden());
    }
}
~~~

`with(user("alice"))` là mock user, giúp tách lỗi CSRF khỏi việc chưa login. Helper `with(csrf())` không chứng minh HTML thực sự render token đúng hay cookie được browser lưu. Thêm test GET login/profile → lấy token HTML thật → POST cùng session để kiểm tra trọn vòng.

### 19.4. Test Bearer không tự xác thực browser chain

Với browser `/web/profile`, một request **chỉ có Bearer token M2M** nhưng không có session user nên **không được xem là đã login browser**:

~~~text
POST /web/profile
Authorization: Bearer <machine-token>
Content-Type: application/x-www-form-urlencoded

displayName=Changed&_csrf=some-token

Kỳ vọng:
  - Không thực hiện cập nhật dưới quyền máy như user;
  - Có thể bị redirect login/403 theo browser chain;
  - Không tạo hoặc nâng cấp phiên browser từ machine token.
~~~

Trong test thực, token chỉ dùng Bearer header, **không thêm `with(user())`**, tránh tự cấp principal vào request rồi kết luận sai.

### 19.5. Kiểm thử signed JWT thật để bao phủ decoder

Ngoài `with(jwt())`, cần có HTTP integration test:

- JWT được ký bởi **test issuer/JWKS** tương ứng trusted config;
- Claim `iss` đúng/sai, `aud` đúng/sai, `exp` còn/hết hạn, `scope` đủ/thiếu;
- Resource Server nhận **actual `Authorization: Bearer ...`**;
- Token sai chữ ký/bị sửa phải `401`;
- Token từ issuer khác không được chấp nhận dù chữ ký của một test key khác hợp lệ;
- Token đúng issuer nhưng sai audience phải bị từ chối;
- Token đã xác thực nhưng thiếu scope/partner permission phải `403` hoặc policy tương ứng.

Có thể dùng test Authorization Server, token signer test, hoặc mock `JwtDecoder` để kiểm tra filter/response path. **Mock decoder không chứng minh chữ ký thực được kiểm tra**; chọn tầng test theo mục tiêu.

## 20. Reactive WebTestClient: phân tách M2M và browser

### 20.1. M2M request bằng `mockJwt()`

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class HybridReactiveMachineTests {

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void machineCanSubmitWithWriteScope() {
        client().mutateWith(mockJwt()
                .jwt(jwt -> jwt
                    .subject("partner-worker")
                    .claim("client_id", "partner-worker-42"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_jobs:write")))
            .post().uri("/integrations/jobs")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"externalJobId\":\"42\","
                + "\"state\":\"DONE\"}")
            .exchange()
            .expectStatus().isAccepted();
    }

    @Test
    void noBearerFails() {
        client()
            .post().uri("/integrations/jobs")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"externalJobId\":\"42\","
                + "\"state\":\"DONE\"}")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongScopeFails() {
        client().mutateWith(mockJwt()
                .jwt(jwt -> jwt
                    .subject("partner-worker")
                    .claim("client_id", "partner-worker-42"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_jobs:read")))
            .post().uri("/integrations/jobs")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"externalJobId\":\"42\","
                + "\"state\":\"DONE\"}")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Ví dụ giả định reactive M2M controller `/integrations/jobs` trả `202 Accepted` và fake service có kết quả phù hợp. `mockJwt()` không chứng minh `ReactiveJwtDecoder`/audience/issuer được dùng như production.

### 20.2. Browser WebSession POST phải giữ CSRF

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class HybridReactiveBrowserTests {

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void browserFormWithTokenCanRedirect() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/web/profile")
            .body(BodyInserters
                .fromFormData("displayName", "Alice New"))
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void browserFormWithoutTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/web/profile")
            .body(BodyInserters
                .fromFormData("displayName", "Must Not Save"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Để kiểm tra WebSession browser **thật**, cần GET trang login lấy token và cookie, POST login với đúng cookie/token, rồi gửi POST vào `/web/profile`. Nếu test chỉ `mockUser()`, nó không xác minh session fixation, login/logout hay cookie policy.

### 20.3. Reactive cookie-only M2M boundary

Một test tích hợp thực tế:

~~~text
1. Client A: GET /login -> cookie SESSION=A và CSRF token
2. Client A: POST /login -> xác thực browser session A'
3. Client A: GET /web/profile -> confirm authenticated
4. Client A: POST /integrations/jobs chỉ có Cookie: SESSION=A'
   không Authorization header
   -> 401, không tạo job
5. Client B: POST /integrations/jobs với Bearer JWT hợp lệ
   không cookie -> 202 theo quyền partner
6. Client B: POST với JWT sai audience -> 401
7. Client B: POST với JWT đúng thiếu scope -> 403
~~~

`WebTestClient` bind-to-context là HTTP test client, **không phải browser**; giữ cookie giữa các request cần được thực hiện tường minh. Muốn thử SameSite/browser auto-send hay CORS, dùng browser automation với public HTTPS origin thật.

## 21. Integration end-to-end trên public endpoint

### 21.1. Bài thử đồng thời hai client

Trong môi trường được phép (dữ liệu giả, tài khoản test):

**Nhánh browser**

1. Mở `GET /login` và xác minh HTML form có CSRF token thực.
2. Đăng nhập với test user, theo redirect và kiểm tra session cookie `Secure; HttpOnly; SameSite` phù hợp.
3. GET `/web/profile` với session hiện hành, nhận form CSRF token sau login.
4. POST cập nhật có token, kiểm tra PRG và dữ liệu thay đổi đúng.
5. POST thiếu/sai token với cùng session, kiểm tra `403` và dữ liệu không đổi.
6. POST logout hợp lệ; request sau logout phải không còn được xác thực.
7. Mở form cũ từ tab khác rồi submit, kiểm tra server không chấp nhận token/phiên đã vô hiệu hóa.

**Nhánh M2M**

1. Worker test dùng client credentials xin access token từ test Authorization Server.
2. Gọi `POST /integrations/jobs` bằng **Bearer header thật** và không cookie.
3. Xác minh token issuer/audience/scope/partner identity hợp lệ và response theo hợp đồng.
4. Thử thiếu Bearer, JWT bị sửa, hết hạn, sai audience, sai scope.
5. Thử chỉ có **browser session cookie thật**; M2M không được xác thực.
6. Thử Bearer hợp lệ kèm cookie browser không liên quan; quyền phải xác định theo machine token, không nâng quyền bằng cookie.
7. Kiểm tra dữ liệu/event khi request bị từ chối.
8. Thử key rotation và client credential rotation trong môi trường test theo chính sách provider.

**Nhánh proxy/hạ tầng**

1. Request qua **HTTPS public URL**, không chỉ localhost upstream.
2. Kiểm tra route `/web/**` và `/integrations/**` được forward nguyên vẹn.
3. Kiểm tra redirect login không xuất hiện với M2M 401.
4. Kiểm tra `WWW-Authenticate`, `Cache-Control` và response errors đúng.
5. Đảm bảo log/proxy không lưu raw `Authorization`, `Cookie`, `Set-Cookie` hoặc CSRF token.
6. Khi scale nhiều node, browser session vẫn nhất quán; M2M JWT validation và JWKS rotation đồng nhất.

### 21.2. Hai trạng thái không được lẫn lộn

~~~text
Browser đang login Alice:
  GET /web/profile + cookie => qua browser chain
  POST /integrations/jobs + cookie only => KHÔNG được authenticated

Partner worker đang có Bearer:
  POST /integrations/jobs + Bearer => qua M2M chain
  POST /web/profile + Bearer only => KHÔNG được thành user Alice
~~~

**Đây là bài kiểm thử giá trị nhất** khi có hai hệ thống authentication trong cùng một ứng dụng.

### 21.3. Tránh giả lập sai hành vi browser

- cURL có thể gửi cookie bằng tay kể cả khi `SameSite` khiến browser thật không gửi; phù hợp để kiểm tra **server-side chain**, không chứng minh browser policy.
- `MockMvc` `with(user())` và `WebTestClient` `mockUser()` không chứng minh form login/session cookies thật.
- `with(jwt())`/`mockJwt()` không xác minh cryptographic JWT signature và audience validator thật.
- Browser automation không thể tự chứng minh token validation cryptographic nếu nó chỉ sử dụng một token do provider cấp; cần kết hợp HTTP integration/token issuer test.
- Một status 401/403 là cần nhưng chưa đủ; nên kiểm tra **không có side effect** và **không lộ dữ liệu giữa partner/user**.

## 22. Các tình huống khó trong production

### 22.1. M2M token bị lộ nhưng không có CSRF

Bearer token là credential có thể bị dùng lại bởi ai sở hữu nó trong thời gian hiệu lực, trừ khi có sender-constraining phù hợp. Nếu token lộ qua logs/CI/chat, attacker có thể gọi Resource API **trực tiếp**, không cần browser CSRF.

Biện pháp phòng vệ:

- Access token TTL ngắn, scopes/audience tối thiểu;
- Client secret rotation, secret manager, tránh log token;
- Rate limiting, anomaly detection và partner-level quota;
- Token revocation/introspection khi cần;
- mTLS/DPoP sender-constrained tokens với hỗ trợ đầy đủ từ issuer/resource server nếu yêu cầu cao.

Không “bật CSRF token” lên M2M API rồi coi đó là đã khắc phục token theft; cần bảo vệ credential đúng nguyên nhân.

### 22.2. Authentication fallback do SSO gateway

Giả sử gateway đứng trước Spring và làm:

~~~text
Browser mang SESSION cookie -> Gateway xác thực user
-> Gateway phát Authorization: Bearer <internal-token>
-> Spring /integrations/** nhận Bearer
~~~

Spring có thể chỉ thấy Bearer header, nhưng **điểm vào browser→gateway vẫn dùng cookie tự gửi**. Nếu gateway cho browser POST tới integrations path và tự nâng thành internal Bearer, việc miễn CSRF tại Resource Server **không đủ**.

Cần chống CSRF hoặc khóa/route riêng tại browser-facing gateway/BFF. Nếu M2M route không dành cho browser, **không cho gateway chuyển browser session thành M2M credential**.

### 22.3. Nhiều node browser session nhưng M2M stateless

~~~mermaid
flowchart LR
    B[Browser cookie] --> L[Load Balancer]
    M[M2M Bearer] --> L
    L --> A[Spring node A]
    L --> C[Spring node B]
    A --> STORE[(Shared session store)]
    C --> STORE
    A --> AS[Trusted JWKS/introspection]
    C --> AS
~~~

Browser chain cần session store/affinity nhất quán: nếu token CSRF và SecurityContext nằm ở node A mà POST đến node B không tìm thấy session, có thể trả `403`/redirect login ngẫu nhiên.

M2M chain stateless không cần browser session store để authenticate nhưng cần decoder/JWKS cache/introspection tin cậy và khả năng xử lý key rotation trên các node. Không sửa lỗi session bằng `csrf.disable()`.

### 22.4. Cookie session scope với cùng public host

Nếu browser và M2M route cùng `platform.example.com`, browser có thể **tự gửi cookie** tới `/integrations/**` nếu `Path=/`. Điều này **không tự tạo CSRF** nếu M2M chain **kiên quyết bỏ qua cookie và chỉ nhận Bearer**.

Tuy nhiên, cookie vẫn được truyền ở HTTP request và có thể xuất hiện trong proxy logs nếu cấu hình kém. Có thể cân nhắc cookie `Path=/web` nếu toàn bộ browser authentication/login/logout đã được thiết kế phù hợp; **Path không phải ranh giới authorization** và có thể gây vấn đề với `/login`/`/logout`. Không chỉ sửa Path rồi bỏ test cookie-only fallback.

### 22.5. Thêm một route mới làm thay đổi threat model

Một nhóm phát triển thêm:

~~~text
POST /integrations/oauth/refresh
Cookie: REFRESH_TOKEN=...
~~~

vào vùng M2M `/integrations/**` đã `csrf.disable()`. Đây là **thay đổi kiến trúc lớn**: endpoint mới dùng credential cookie tự gửi, không thỏa giả định bearer-only.

Cần:

1. Chuyển route sang vùng browser/session riêng và bảo vệ CSRF, hoặc
2. Thiết kế explicit origin/CSRF/refresh-token policy thích hợp và matcher riêng;
3. Kiểm thử login/refresh lifecycle, cookie scope, SameSite, Origin/Fetch Metadata nếu dùng;
4. Cập nhật threat model của mọi security chain.

Không được thừa kế `csrf.disable()` chỉ vì route mới có prefix `/integrations`.

## 23. Chẩn đoán lỗi khi browser và M2M dùng chung hệ thống

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| M2M nhận `302 Location: /login` | Request rơi vào browser chain thay vì Resource Server chain | Kiểm tra `@Order`, `securityMatcher`, proxy path rewrite |
| Browser POST `/web/profile` không cần CSRF vẫn thành công | CSRF bị tắt toàn app hoặc request đi qua M2M chain | Xem matcher/CSRF config và kiểm tra no-side-effects |
| M2M chỉ gửi cookie browser mà vẫn cập nhật job | Có session auth fallback/gateway biến cookie thành Bearer | Audit toàn bộ authentication sources và chain; test valid cookie-only |
| M2M không Bearer trả `403` thay vì `401` | Sai entry point/authorization chain hoặc request bị chặn ở lớp khác | Xem filter chain, exception, Bearer `WWW-Authenticate` |
| Bearer hợp lệ nhưng trả `401` | JWT issuer/audience/signature/expiry/JWK không khớp, token malformed | Kiểm tra decoder/validator không log token thật |
| Bearer hợp lệ nhưng trả `403` | Thiếu `SCOPE_jobs:write` hoặc client không được phép thao tác job | Kiểm tra authority mapping, clientId/partner ownership |
| M2M gửi token JWT được ký đúng nhưng API khác vẫn chấp nhận | Chưa xác minh `aud`/token usage | Bổ sung audience validator và test wrong audience |
| Browser đăng nhập xong liên tục quay về login | Session cookie không được lưu/gửi hoặc SecurityContext không persist | DevTools Cookie/Set-Cookie, Secure/SameSite/Path, session store |
| Browser POST sau login `403` | CSRF token cũ bị invalidated hoặc form/header gửi sai | GET form/token mới trong session hiện hành; kiểm tra XOR masking |
| Browser `GET /logout` làm logout ngay | Logout bị tùy chỉnh thành GET có side effect | Chuyển thành POST với CSRF hoặc trang xác nhận |
| Browser nhiều tab POST form cũ `403` | Tab khác logout/login hoặc session expired | Cung cấp UX reload/re-login, không tắt CSRF |
| M2M nhận HTML login thay vì JSON 401 | Form login/default entry point đang xử lý M2M | Tách chain, tắt formLogin ở M2M, kiểm tra path |
| CORS preflight `OPTIONS` bị `401` | Authentication yêu cầu trước CORS hoặc route sai | CORS source/integration trước auth, preflight không cần Bearer |
| CORS error dù M2M cURL thành công | M2M HTTP client không chịu browser CORS | Chỉ cấu hình CORS nếu có browser JS client thật |
| JWT scope có `jobs:write` nhưng thiếu authority | Issuer dùng claim khác hoặc converter không map đúng | Kiểm tra claim `scope`/`scp` và `JwtAuthenticationConverter` |
| Token client_credentials xuất hiện như user Alice | Sai mapping principal/delegation, dùng clientId như userId | Phân biệt MACHINE/HUMAN, ràng buộc partner rõ ràng |
| 401/403 bị trả thành 200 HTML ở proxy | SPA fallback hoặc custom error page rewrite | Không rewrite integration API response thành index.html |
| Token xuất hiện trong access logs/trace | Gateway bật logging headers hoặc client log debug | Redact `Authorization` và secrets, giảm retention |
| Cookie phiên bị gửi tới `/integrations/**` | Cookie `Path=/` cùng host | Không sao nếu chain hoàn toàn bỏ qua; xác minh không auth fallback |
| POST M2M bị xử lý hai lần khi retry timeout | Không có idempotency/retry policy | Dùng idempotency key, transaction/unique constraint |
| Browser `403` ngẫu nhiên khi scale | Session/expected CSRF token không chia sẻ giữa nodes | Kiểm tra session store/sticky session, TTL và serializer |
| M2M JWT `401` ngẫu nhiên khi rotate key | JWKS cache hoặc clock skew không nhất quán | Kiểm tra issuer metadata, key rotation, clocks và caches |
| HTTP Basic M2M hoạt động ngoài ý muốn | Chain bật `httpBasic` hoặc gateway auth fallback | Tắt Basic ở bearer-only chain và test |
| `GET /integrations/health` bị public | Route health/management policy mặc định quá rộng | Tách actuator/health, network access và security matcher |
| M2M qua proxy 404 nhưng upstream chạy | Proxy strip prefix `/integrations`, chain mismatch | So public URI với URI backend nhận |
| API web nhận Bearer token làm login user | Có jwt filter dùng chung browser route | Tách chain và test Bearer-only trên browser không nâng quyền |
| Refresh endpoint cookie mới bị miễn CSRF | Đặt dưới matcher M2M quá rộng | Chuyển route/đánh giá lại ambient credential |
| HSTS/CSP chỉ có trên API, không trên HTML | HTML được phục vụ bởi proxy/CDN khác Spring | Thêm header tại nơi phát tài liệu browser thực |
| Browser bị clickjacking | Không có `frame-ancestors`/frame policy trên HTML | Áp CSP/headers thích hợp, không thay CSRF |

### 23.1. Quy trình chẩn đoán theo từng request

~~~text
Bước 1: Xác định HTTP method và URL sau proxy.
Bước 2: Xác định SecurityFilterChain / SecurityWebFilterChain được chọn.
Bước 3: Xác định credential thật:
    - Cookie browser?
    - Bearer header?
    - Cả hai?
    - Không có?
Bước 4: Xác định client mong đợi:
    - Browser HUMAN -> session + CSRF
    - M2M MACHINE -> Bearer + scope/partner
Bước 5: Kiểm tra authentication kết quả:
    - Thiếu/sai -> 401/redirect theo đúng contract
    - Hợp lệ nhưng thiếu quyền -> 403/404 theo policy
Bước 6: Với browser unsafe request, kiểm tra CSRF token
        và repository/session tương ứng.
Bước 7: Kiểm tra dữ liệu và event có bị thay đổi ngoài ý muốn không.
Bước 8: Kiểm tra cookie/headers/proxy, sau đó regression hai chain.
~~~

**Không dùng riêng HTTP status để xác định nguyên nhân.** Một `403` có thể do CSRF, authorization hay gateway policy. Xem exception class, chain và request metadata đã được khử bí mật.

## 24. Checklist triển khai an toàn

| Hạng mục | Điều kiện chấp nhận |
|---|---|
| **Phân nhóm URL** | Browser và M2M có matcher rõ ràng, dễ audit |
| **Thứ tự chain** | M2M matcher hẹp ở order ưu tiên; browser fallback bảo vệ URL khác |
| **Browser auth** | Form/OIDC session được xác thực, chống session fixation |
| **Browser CSRF** | Login/logout và mọi unsafe browser request được kiểm tra token |
| **Browser cookie** | `Secure`, `HttpOnly`, `SameSite`, host/path đúng và HTTPS |
| **Browser GET** | Không có side effect, kể cả GET logout |
| **M2M auth** | Chỉ Bearer header ở integration chain; cookie-only không được nhận |
| **M2M stateless** | Không dùng HttpSession/WebSession để khôi phục Resource Server authentication |
| **JWT trust** | Signature, issuer, audience, `exp`/`nbf`/JWK và thuật toán được kiểm tra |
| **Opaque trust** | Introspection từ nguồn đáng tin, active/audience/scope policy đúng |
| **Client identity** | Map `client_id`/`sub` theo hợp đồng issuer; không giả làm human |
| **Authorization** | Scope endpoint và partner/tenant/object-level permission |
| **Client credentials** | Secret manager, rotation, không hardcode và không log |
| **Token lifecycle** | TTL, refresh/re-acquire, key rotation và revocation policy rõ |
| **Retry/idempotency** | Có backoff và idempotency theo nghiệp vụ M2M |
| **CORS** | Chỉ áp khi có browser JS cross-origin, preflight không đòi credentials |
| **CSP** | Đặt trên HTML browser thực, XSS/DOM sinks được kiểm soát |
| **HSTS/TLS** | HTTPS công khai, M2M xác minh certificate |
| **HTTP firewall** | URL/path policy không bị nới lỏng vô cớ |
| **Reverse proxy** | Giữ route/method/header, chặn direct backend access |
| **Session store** | Ổn định trên multi-node đối với browser |
| **Response contract** | Browser redirect hợp lý; M2M 401/403/Bearer challenge |
| **No sensitive logs** | Cookie, Authorization, CSRF token và secret đều được redact |
| **Tests** | Browser CSRF + M2M token validation + hai chiều no-fallback |
| **No side effects** | Mọi 401/403 không tạo transaction/event nghiệp vụ |
| **Review thay đổi** | Thêm auth method/cookie/route bắt buộc đánh giá lại CSRF |

## 25. Bài tập thực hành có hướng dẫn

### Bài tập 1 — Vẽ ranh giới xác thực

Một platform có:

~~~text
GET  /login
POST /login
GET  /web/dashboard
POST /web/approve-order
POST /integrations/report
POST /integrations/token-refresh
~~~

`/integrations/report` chỉ nhận Bearer access token của worker. `/integrations/token-refresh` lại dùng refresh cookie của browser.

**Câu hỏi:** Có thể viết `securityMatcher("/integrations/**").csrf(disable)` không?

**Gợi ý đáp án:** Không nên áp chung khi refresh endpoint dựa vào cookie browser. Cần tách `/integrations/report` thành vùng bearer-only, còn refresh cookie sang vùng có anti-CSRF/Origin và token lifecycle rõ. Thiết kế matcher không được dựa chỉ vào tên prefix.

### Bài tập 2 — Cookie browser có thể gọi M2M API?

Trình duyệt đã đăng nhập Alice, nhận `JSESSIONID` hợp lệ. Một script gửi `POST /integrations/jobs` không Bearer, browser tự gắn cookie.

**Câu hỏi:** Điều gì phải xảy ra?

**Gợi ý đáp án:** Integration chain không được xác thực Alice bằng session cookie; request phải bị từ chối, thường `401`, không ghi job. Nếu thành công, hệ thống có authentication fallback hoặc chọn sai chain; quyết định miễn CSRF chưa có cơ sở.

### Bài tập 3 — JWT sai audience nhưng đúng chữ ký

Access token được issuer phát cho `inventory-api`, có `SCOPE_jobs:write`, signature hợp lệ. Client dùng token gọi `/integrations/jobs` của `platform-integration-api`.

**Gợi ý đáp án:** Resource Server cần từ chối do `aud` không chứa target resource, thường trả `401`. Scope đúng không được phép vượt điều kiện audience. Thêm test JWT wrong audience bằng test issuer/decoder có validator thật.

### Bài tập 4 — Browser POST bị 403 sau login

User login thành công nhưng form được mở trước login vẫn gửi CSRF token cũ, server trả `403`.

**Gợi ý đáp án:** Xem vòng đời session/token; authentication có thể đổi session ID hoặc invalidate expected CSRF token. Tải lại form/token theo phiên mới; không tắt CSRF. Nếu nhiều node, kiểm tra session store.

### Bài tập 5 — M2M bị 302 HTML login

Một worker gọi `POST /integrations/jobs` với Bearer hợp lệ nhưng nhận `302 /login`. Trước đó local test controller trực tiếp pass.

**Gợi ý đáp án:** Kiểm tra URL public/upstream và order/matcher; request có thể rơi vào browser chain hoặc proxy rewrite path. M2M endpoint cần Resource Server entry point chứ không dùng form login redirect.

### Bài tập 6 — Đối tác thao tác nhầm job của tenant khác

Partner A có token hợp lệ với `jobs:write` nhưng dùng ID của job thuộc Partner B. Controller chỉ kiểm scope và lưu.

**Gợi ý đáp án:** Đây là lỗi **object-level authorization/tenant isolation**, không phải CSRF hay chữ ký JWT. Service cần ràng buộc client identity → partner → job, ngăn ghi và kiểm thử no-side-effects.

### Bài tập 7 — M2M retry và giao dịch lặp

Worker POST trạng thái job, không nhận được response do timeout và retry. Server đã xử lý request đầu nhưng tạo hai records khi nhận request hai.

**Gợi ý đáp án:** Thiết kế idempotency key, unique constraints, xử lý duplicate event và retry budget. CSRF token không giải quyết vấn đề idempotency.

### Bài tập 8 — OAuth2 client_credentials trong ứng dụng Spring

Viết service worker dùng `OAuth2AuthorizedClientManager` để lấy access token từ provider và gọi `POST /integrations/jobs`.

**Tiêu chí đạt:** Client secret đọc từ secret manager/config môi trường, token chỉ đặt trong Bearer header, HTTPS được xác minh, không log token, có policy expiry/401/403 và test provider/token response.

## 26. Câu hỏi tự đánh giá

**Câu 1.** Vì sao không nên tắt CSRF toàn ứng dụng khi có một M2M API dùng Bearer token?

**Đáp án:** Vì các route browser vẫn có thể xác thực bằng session cookie được browser tự gửi. Ngoại lệ CSRF cần được giới hạn cho route **thực sự bearer-only**, không áp lên login, logout, form POST hoặc refresh-cookie endpoints.

**Câu 2.** `SecurityFilterChain` và `SecurityWebFilterChain` khác nhau thế nào?

**Đáp án:** Chúng thuộc hai stack: Servlet/Spring MVC dùng `HttpSecurity` và `SecurityFilterChain`; Reactive/WebFlux dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Cả hai đều chọn chain theo matcher, nhưng API/session/filter khác nhau.

**Câu 3.** Nếu hai chains match cùng request thì Spring Security ghép cả hai lại không?

**Đáp án:** Không. Spring Security chọn **chain phù hợp đầu tiên** theo thứ tự áp dụng. Vì thế order và `securityMatcher` phải được thiết kế rõ; một browser chain quá rộng ở đầu có thể lấy mất M2M request.

**Câu 4.** Cookie `JSESSIONID` hợp lệ có thể xác thực được `/integrations/jobs` không?

**Đáp án:** Không, nếu thiết kế thật sự bearer-only. Phải test cookie-only không tạo authentication trong M2M chain. Nếu cookie được chấp nhận, cần loại fallback hoặc đánh giá CSRF ở đường browser.

**Câu 5.** Một JWT của partner có chữ ký hợp lệ và scope `jobs:write`. Vì sao vẫn cần kiểm tra `aud`?

**Đáp án:** Chữ ký chỉ chứng minh token phát từ nguồn ký tin cậy; audience xác định token dành cho Resource API nào. Không kiểm `aud` có thể cho token cấp cho API khác bị dùng sai.

**Câu 6.** `client_credentials` grant đại diện cho ai?

**Đáp án:** Thường đại diện cho **client/dịch vụ** trong quyền được cấp cho client, không mặc nhiên đại diện cho một user đang dùng browser. Token claims cần được map thành machine client identity theo hợp đồng issuer.

**Câu 7.** Có phải mọi `Authorization` header đều làm CSRF không còn liên quan?

**Đáp án:** Không. Browser có thể tự gửi HTTP Basic credentials, gateway có thể chuyển cookie thành Bearer. Cần xác định ai gửi credential và server thực sự chấp nhận những loại nào.

**Câu 8.** Một worker gọi API qua cURL nhưng browser CORS không allowlist origin worker. API có cần sửa CORS không?

**Đáp án:** Không. cURL/server-to-server HTTP client không chịu CORS của browser. M2M dựa vào HTTPS, access token, scope và authorization, không dựa vào Origin header.

**Câu 9.** Tại sao `with(jwt())` và `mockJwt()` chưa đủ kiểm thử chữ ký JWT?

**Đáp án:** Helper tạo mock authentication trong test, không đưa token thật qua decoder/issuer/JWKS. Cần HTTP integration với JWT test signer hoặc test decoder/validator thực để chứng minh validation.

**Câu 10.** Khi API nhận Bearer đúng và cookie của browser cùng lúc, quyền nên xác định thế nào?

**Đáp án:** Trong vùng M2M bearer-only, quyền phải xác định theo **Bearer client identity**; cookie không được nâng quyền hoặc thay principal. Test kết hợp cả hai credential để phát hiện đường fallback/precedence không mong muốn.

**Câu 11.** Có nên lưu access token/client secret trong application log khi chẩn đoán 401 không?

**Đáp án:** Không. Log chain, issuer/audience mismatch type, scope failure, request ID và outcome đã khử nhạy cảm; tránh log token/secret thô.

**Câu 12.** Nếu browser và M2M cùng hostname public, có cần tách ứng dụng thành hai process để an toàn không?

**Đáp án:** Không bắt buộc. Có thể tách bằng route/security chains với isolation được kiểm thử. Tách process/host có thể tăng defence-in-depth và giảm coupling, nhưng không tự sửa auth fallback/gateway/authorization sai.

**Câu 13.** Một POST của browser có session cookie nhưng không CSRF token bị 403. Có nên dùng session fixation protection để thay CSRF?

**Đáp án:** Không. Session fixation protection giảm nguy cơ attacker cố định session ID trước login; CSRF token kiểm chứng unsafe request có cookie. Hai cơ chế bổ trợ, không thay thế nhau.

**Câu 14.** Một M2M partner đã có `SCOPE_jobs:write`, vì sao vẫn không được ghi job của tenant khác?

**Đáp án:** Scope cho phép loại thao tác, không cho phép vượt object-level authorization. Server phải kiểm tra client/partner/tenant ownership cho từng job.

**Câu 15.** Một redirect login HTML trả về M2M client thiếu Bearer có phải response hợp lý nhất không?

**Đáp án:** Không. M2M client thường cần `401 Unauthorized` cùng Bearer challenge theo policy; redirect HTML báo hiệu endpoint rơi vào sai chain hoặc entry point không phù hợp.

## Kết luận

Một hệ thống **cùng phục vụ trình duyệt và client máy–máy** không thể coi mọi request là một loại “web request” giống nhau. **Browser** thường có session cookie được tự gắn khi điều kiện cho phép, nên unsafe requests như login, cập nhật hồ sơ và logout phải được bảo vệ bằng CSRF token, đồng thời cần session fixation protection, cookie `Secure/HttpOnly/SameSite` và phân quyền theo user. **Client M2M** chủ động gắn `Authorization: Bearer` từ OAuth2 client credentials, cần JWT/opaque token validation, issuer/audience/expiry, scopes, client identity, object-level authorization, secret rotation và chống replay/abuse theo threat model.

Trên **Spring Security Servlet**, hãy dùng `SecurityFilterChain`/`HttpSecurity` tách vùng `/integrations/**` với browser fallback; trên **Reactive/WebFlux**, dùng `SecurityWebFilterChain`/`ServerHttpSecurity` và WebSession/CSRF filter tương ứng. **Miễn CSRF chỉ nên giới hạn trong M2M bearer-only chain sau khi đã chứng minh không có cookie/Basic/gateway fallback**; web chain vẫn phải giữ CSRF.

CORS, CSP, HSTS, HTTP firewall, reverse proxy và HTTPS là những lớp bổ sung: CORS có ích cho JavaScript browser khác origin, nhưng không giới hạn cURL/worker; CSP và output encoding giảm XSS trên HTML; HSTS/TLS bảo vệ kết nối; HTTP firewall và route matching giúp giữ chain chính xác.

**Bằng chứng quan trọng nhất là các ca kiểm thử ranh giới:** cookie session browser hợp lệ **không gọi được** M2M API khi thiếu Bearer; Bearer token M2M **không tự tạo** phiên user browser; request browser thiếu/sai CSRF **không ghi dữ liệu**; access token sai issuer/audience/scope/partner permission bị từ chối và không có side effects. Đó là cách áp dụng nhất quán các lớp phòng vệ của module **SPRING_SECURITY_HTTP_PROTECTION** khi hệ thống phục vụ nhiều loại client cùng lúc.

## Tài liệu tham khảo

- [Spring Security — Multiple HttpSecurity Instances (Servlet)](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances): nhiều security chains và request matcher.
- [Spring Security — OAuth2 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): Bearer authentication, JWT decoder, claims và scope authorities.
- [Spring Security — OAuth2 Resource Server Opaque Tokens (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): token introspection.
- [Spring Security — OAuth2 Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): Reactive JWT validation và authentication.
- [Spring Security — OAuth2 Resource Server Opaque Tokens (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): Reactive introspection.
- [Spring Security — Servlet CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token, form login/logout và HttpSession repositories.
- [Spring Security — WebFlux CSRF Protection](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `CsrfWebFilter` và WebSession token.
- [Spring Security — Servlet CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS trước authentication.
- [Spring Security — Reactive CORS Integration](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): WebFlux CORS.
- [Spring Security — Servlet HTTP Security Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): CSP, HSTS và browser headers.
- [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `OAuth2AuthorizedClientManager` và client credentials.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): `client_credentials` grant.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, lỗi và bảo mật token.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT validation, audience và algorithm confusion.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): threat model, synchronizer token, SameSite và defense in depth.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): Bearer, JWT, access control và vận hành API an toàn.
