# 1.8. Điều kiện nền tảng: HTTP, TLS, session, JWT và Spring Security

Trong một ứng dụng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, thao tác “Đăng nhập bằng nhà cung cấp danh tính” thực chất là sự phối hợp giữa nhiều cơ chế: HTTP chuyển hướng trình duyệt, TLS bảo vệ đường truyền, session duy trì trạng thái người dùng tại ứng dụng, token truyền thông tin và quyền truy cập, còn Spring Security điều phối các bước xác thực và bảo vệ endpoint.

Bài này xây dựng nền tảng để đọc hiểu cấu hình `oauth2Login()`, theo dõi quá trình đăng nhập OIDC và phân biệt những thành phần thường bị nhầm lẫn. Ví dụ sử dụng **Spring Boot 3.x, Spring Security 6.x và ứng dụng Servlet (Spring MVC)**; chi tiết triển khai có thể thay đổi theo phiên bản hoặc nhà cung cấp danh tính.

## 1. Bức tranh tổng thể: ai nói chuyện với ai?

Các vai trò chính:

| Thành phần | Vai trò trong luồng đăng nhập |
| --- | --- |
| **Browser (user agent)** | Gửi HTTP request, nhận redirect, giữ cookie của ứng dụng và của nhà cung cấp danh tính. |
| **Spring application (OAuth 2.0 Client / Relying Party)** | Khởi tạo yêu cầu đăng nhập, nhận authorization code, đổi code lấy token, xác thực thông tin OIDC và tạo phiên đăng nhập tại ứng dụng. |
| **Authorization Server / OpenID Provider (OP)** | Xác thực người dùng, xin/chấp nhận consent khi cần, cấp authorization code và token. |
| **Resource Server / API** | Tiếp nhận access token để bảo vệ tài nguyên; có thể là dịch vụ độc lập với Spring application. |

`OAuth 2.0` cung cấp cơ chế **ủy quyền**: client có thể nhận access token để gọi một API. `OIDC` mở rộng OAuth 2.0 với lớp **xác thực danh tính**, đặc biệt là `ID Token` và các quy tắc kiểm tra nó.

Một luồng phổ biến là **Authorization Code Flow**, thường kết hợp **PKCE (Proof Key for Code Exchange)**:

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng / Browser
    participant C as Spring OAuth2 Client
    participant P as OpenID Provider
    participant A as API / Resource Server
    U->>C: GET /account
    C-->>U: 302 tới trang đăng nhập / điểm bắt đầu OAuth2
    U->>C: GET /oauth2/authorization/demo
    C-->>U: 302 tới authorization endpoint (state, nonce, PKCE)
    U->>P: GET /authorize?... qua HTTPS
    P->>U: Đăng nhập / consent (nếu cần)
    P-->>U: 302 về callback kèm code và state
    U->>C: GET /login/oauth2/code/demo?code=...&state=...
    C->>P: POST /token (code, redirect_uri, PKCE, client auth)
    P-->>C: ID token, access token và thông tin liên quan
    C->>C: Kiểm tra state, ID token; tạo Authentication
    C-->>U: Set-Cookie: JSESSIONID=...; 302 về trang ban đầu
    U->>C: GET /account + Cookie: JSESSIONID=...
    C-->>U: 200 nội dung cho người đã đăng nhập
    opt Ứng dụng gọi API thay mặt người dùng
        C->>A: Authorization: Bearer <access_token>
        A-->>C: Tài nguyên được bảo vệ
    end
```

Sơ đồ cho thấy **authorization code**, **token** và **session cookie** xuất hiện ở những chặng khác nhau. Chúng không thể dùng thay thế cho nhau.

## 2. HTTP: request, response, header, cookie và redirect

### 2.1. HTTP là giao thức request–response

Trình duyệt gửi một request; máy chủ trả lại response. Mỗi request mang phương thức, đường dẫn, header và có thể có body. HTTP không tự ghi nhớ “request trước thuộc về ai”; sự liên tục phải được tạo bằng cookie, session hoặc credential đính kèm mỗi request.

Các phương thức thường gặp trong OIDC client:

| Phương thức | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `GET` | `GET /oauth2/authorization/demo` | Bắt đầu đăng nhập và điều hướng trình duyệt. |
| `GET` | `GET /login/oauth2/code/demo?code=...&state=...` | Nhận callback với authorization code khi sử dụng response mode `query`. |
| `POST` | `POST /oauth2/token` hoặc token endpoint của OP | Client trao đổi authorization code lấy token bằng giao tiếp back-channel. |
| `POST` | `POST /logout` | Thực hiện logout phía ứng dụng trong cấu hình Spring Security thường dùng với CSRF. |
| `GET` / `POST` | Gọi API đã bảo vệ | Gửi access token qua header `Authorization` nếu sử dụng Bearer token. |

**HTTP status** rất quan trọng khi debug:

- `200 OK`: request được xử lý thành công; tự nó không chứng minh rằng người dùng đã được xác thực.
- `302 Found` hoặc `303 See Other`: phản hồi yêu cầu chuyển hướng; browser đọc header `Location` rồi tạo request mới.
- `400 Bad Request`: tham số thiếu/sai hoặc yêu cầu OAuth không hợp lệ.
- `401 Unauthorized`: request thiếu hoặc có credential không hợp lệ, thường gặp ở API dùng Bearer token.
- `403 Forbidden`: request đã được nhận diện nhưng không đủ quyền; cũng có thể do kiểm tra CSRF thất bại.
- `5xx`: lỗi xử lý phía máy chủ hoặc hạ tầng.

Với một endpoint HTML cần đăng nhập, Spring Security thường khởi động quá trình login bằng **redirect**. Với một API cấu hình theo Bearer token, phản hồi thường là `401`. Hành vi cụ thể phụ thuộc `SecurityFilterChain` và `AuthenticationEntryPoint`.

### 2.2. Redirect là những request HTTP riêng biệt

Ví dụ giản lược (giá trị và URL chỉ để minh họa):

```http
GET /oauth2/authorization/demo HTTP/1.1
Host: app.example.com

HTTP/1.1 302 Found
Location: https://idp.example.com/authorize?response_type=code&client_id=demo-client&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fdemo&scope=openid%20profile&state=RANDOM_STATE&code_challenge=CHALLENGE&code_challenge_method=S256
```

Sau khi người dùng đăng nhập tại OP:

```http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/demo?code=ONE_TIME_CODE&state=RANDOM_STATE
```

Trình duyệt mới là bên truy cập URL trong `Location`. Còn việc đổi `code` lấy token thường là **HTTP POST từ backend Spring tới OP**, không đi qua JavaScript trong trình duyệt đối với ứng dụng web server-side.

Một request đổi code điển hình sử dụng `Content-Type: application/x-www-form-urlencoded` và các tham số `grant_type=authorization_code`, `code`, `redirect_uri`, `code_verifier` (nếu dùng PKCE). Confidential client còn phải xác thực với token endpoint bằng cách được OP hỗ trợ, ví dụ `client_secret_basic`. Không đặt `client_secret` trong URL hoặc mã JavaScript công khai.

### 2.3. Header, query string và cookie không cùng chức năng

- **Query string** chứa tham số của authorization request/callback, chẳng hạn `code` và `state`. URL có thể bị lưu trong browser history, access log hoặc hệ thống theo dõi; tránh đưa access token hoặc client secret vào URL.
- **`Authorization: Bearer ...`** thường mang access token khi ứng dụng gọi API. Bearer token hoạt động theo nguyên tắc ai sở hữu token hợp lệ thì có thể sử dụng nó trong phạm vi được cấp.
- **`Cookie`** mang mã nhận diện session của *ứng dụng đích*. Cookie của `idp.example.com` không tự trở thành cookie của `app.example.com` vì browser áp dụng quy tắc domain, path và chính sách cookie.
- **`Set-Cookie`** là header response để server yêu cầu browser lưu/cập nhật cookie.
- **`Cache-Control: no-store`** phù hợp cho response chứa thông tin nhạy cảm như token và nhiều trang có dữ liệu cá nhân. Việc thiết lập còn phụ thuộc loại endpoint và chính sách cache.

**`redirect_uri` phải được đăng ký và khớp với cấu hình OP** theo quy tắc của nhà cung cấp. Khác scheme (`http`/`https`), hostname, cổng, path hoặc dấu `/` có thể khiến yêu cầu bị từ chối. Trong Spring Security, đường dẫn callback mặc định của OAuth 2.0 login là `/login/oauth2/code/{registrationId}`.

## 3. TLS/HTTPS: bảo vệ đường truyền và danh tính máy chủ

HTTPS là HTTP chạy trên **TLS (Transport Layer Security)**. Khi browser kết nối đến `https://app.example.com` hoặc backend kết nối token endpoint qua HTTPS, TLS có ba tác dụng chính:

1. **Bảo mật nội dung trên đường truyền**: bên nghe lén thông thường không đọc được cookie, code, token hay nội dung request/response.
2. **Toàn vẹn dữ liệu truyền tải**: giảm nguy cơ bị sửa nội dung khi truyền.
3. **Xác thực máy chủ**: client xác minh chứng chỉ và hostname để biết mình đang kết nối đến đúng server được tin cậy.

TLS **không thay thế** việc xác thực `ID Token`, kiểm tra quyền API, bảo vệ dữ liệu đã lưu trên máy chủ, hay quản lý session. Một JWT được ký sai vẫn là JWT không đáng tin cậy dù được truyền qua HTTPS.

### 3.1. Chứng chỉ, trust chain và kiểm tra hostname

TLS client kiểm tra thời hạn chứng chỉ, chuỗi chứng chỉ đến CA tin cậy và hostname. Những lỗi như chứng chỉ hết hạn, tên miền không khớp, CA không được tin cậy, hoặc chặn TLS sai cấu hình có thể làm OAuth login dừng ngay trước khi nhận token.

Không “khắc phục” bằng cách tắt xác minh chứng chỉ hoặc cho HTTP client chấp nhận mọi hostname. Nếu môi trường nội bộ dùng CA riêng, hãy cấu hình trust store đúng cách.

### 3.2. HTTPS tại reverse proxy / load balancer

Ứng dụng Spring có thể chạy HTTP nội bộ sau reverse proxy kết thúc TLS. Khi đó cần bảo đảm:

- Browser vẫn sử dụng HTTPS đối với domain công khai; proxy chuyển tiếp header và scheme một cách nhất quán.
- Ứng dụng suy ra đúng **external base URL** khi tạo `redirect_uri`. Header như `Forwarded` hoặc `X-Forwarded-Proto` chỉ nên được tin cậy nếu đến từ proxy được kiểm soát.
- Session cookie có cờ `Secure` để browser không gửi nó trên kết nối HTTP công khai.
- Các callback OIDC, đường dẫn và hostname công khai khớp với cấu hình ở OP.

Có thể dùng `server.forward-headers-strategy` của Spring Boot theo cách triển khai proxy, nhưng phải cấu hình proxy tin cậy tương ứng. Production thông thường dùng HTTPS toàn bộ đường truy cập công khai; ngoại lệ HTTP loopback cho môi trường phát triển phải được kiểm soát riêng.

## 4. Session và cookie: duy trì đăng nhập sau callback

### 4.1. Session giải bài toán HTTP không ghi nhớ trạng thái

Sau khi xác thực OIDC thành công, Spring Security có thể đặt `Authentication` vào `SecurityContext` và duy trì nó qua các request bằng **HTTP session**. Browser nhận một **session ID**, thường dưới dạng cookie `JSESSIONID` khi dùng servlet container mặc định.

```http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=RANDOM_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
Location: /account
```

Ở request sau:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=RANDOM_SESSION_ID
```

Server dùng session ID để tìm phiên liên quan đến người dùng. **Cookie thông thường chỉ chứa mã phiên**, không phải ID Token hay access token. Dữ liệu `SecurityContext` và, tùy cơ chế lưu trữ, thông tin OAuth authorized client nằm phía server.

Session của ứng dụng, session đăng nhập tại OP và thời hạn của access token là **ba vòng đời độc lập**. Hết hạn session ứng dụng không có nghĩa người dùng đã đăng xuất khỏi OP; hết hạn access token không nhất thiết làm session ứng dụng hết hạn.

### 4.2. Các thuộc tính cookie cần hiểu

| Thuộc tính | Công dụng | Lưu ý |
| --- | --- | --- |
| `Secure` | Chỉ gửi cookie trên kết nối HTTPS (ngoại lệ loopback tùy browser). | Nên bật với môi trường triển khai HTTPS. |
| `HttpOnly` | JavaScript trong browser không đọc trực tiếp cookie. | Giảm rủi ro đánh cắp cookie qua một số dạng XSS, không loại bỏ XSS. |
| `SameSite=Lax` | Giới hạn việc gửi cookie trong các ngữ cảnh cross-site. | Thường phù hợp với OIDC callback dạng top-level GET; cần đánh giá callback `form_post`. |
| `SameSite=Strict` | Hạn chế cross-site mạnh hơn. | Có thể làm callback/chuyển hướng đăng nhập thiếu cookie. |
| `SameSite=None` | Cho phép cookie trong ngữ cảnh cross-site được hỗ trợ. | Phải dùng kèm `Secure`; cần cân nhắc CSRF và chính sách browser. |
| `Path` / `Domain` | Giới hạn URL/host nhận cookie. | Nên dùng phạm vi hẹp cần thiết; tránh chia sẻ cookie sang subdomain không liên quan. |
| `Max-Age` / `Expires` | Xác định vòng đời cookie ở browser. | Không đồng nghĩa với session timeout phía server. |

Spring Boot có thể cấu hình cookie session cho ứng dụng HTTPS:

```yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Đây là thiết lập minh họa; cấu hình cuối cùng phải xét topology proxy, callback method và chính sách cookie tại môi trường chạy.

### 4.3. Session fixation, CSRF và lưu session đa máy chủ

- **Session fixation**: kẻ tấn công cố buộc nạn nhân dùng một session ID đã biết. Spring Security có cơ chế bảo vệ session fixation trong quá trình đăng nhập, thường thay đổi session ID sau xác thực.
- **CSRF (Cross-Site Request Forgery)**: browser tự gửi session cookie khi gọi ứng dụng, vì vậy request thay đổi trạng thái (POST/PUT/PATCH/DELETE) cần biện pháp chống CSRF thích hợp. `SameSite` hỗ trợ nhưng không thay thế hoàn toàn CSRF token. Đừng vô hiệu hóa `csrf` chỉ để xử lý lỗi `403` mà chưa tìm nguyên nhân.
- **Đăng xuất**: logout ứng dụng thường xóa `SecurityContext`/session và cookie liên quan; logout đồng bộ với OP là một luồng khác, có thể cần OIDC RP-Initiated Logout.
- **Nhiều instance**: nếu session ở bộ nhớ một JVM, request chuyển sang instance khác có thể bị mất phiên. Có thể cân nhắc sticky sessions hoặc kho session dùng chung như Spring Session + Redis.
- **Session timeout**: ứng dụng nên có giới hạn thời gian phù hợp và kiểm soát các thông tin đã cấp quyền, kể cả access/refresh token lưu ở backend.

## 5. JWT: cấu trúc, chữ ký và điều kiện tin cậy

**JWT (JSON Web Token)** là một định dạng token chứa tập hợp **claims** (các thông tin như chủ thể, issuer, audience, thời hạn). JWT không phải là tên của giao thức đăng nhập: OAuth 2.0 và OIDC quy định **token được cấp/dùng để làm gì**; JWT mô tả **một cách biểu diễn token**.

Một JWT được ký dưới dạng compact JWS thường có ba phần ngăn bởi dấu chấm:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Ví dụ phần header và payload **sau khi giải mã**, chỉ mang tính minh họa:

```json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "JWT"
}
```

```json
{
  "iss": "https://idp.example.com",
  "sub": "user-123",
  "aud": "demo-client",
  "iat": 1794816000,
  "exp": 1794819600,
  "nonce": "random-nonce-from-login"
}
```

Ở đây `iss` là issuer, `sub` là định danh chủ thể tại issuer, `aud` là bên nhận dự kiến, `iat` là thời điểm phát hành và `exp` là thời điểm hết hạn. `nonce` gắn ID Token với yêu cầu xác thực OIDC khi client đã gửi nonce. Giá trị timestamp chỉ để minh họa, không phải token thật có thể sử dụng.

**Base64URL là mã hóa biểu diễn, không phải mã hóa bí mật.** Người có JWT ký dạng JWS thường có thể đọc header và payload; chỉ chữ ký bảo đảm tính toàn vẹn và nguồn phát hành khi được xác minh đúng. JWT dạng JWE có thể được mã hóa, cấu trúc compact thường gồm năm phần; không nên mặc định mọi JWT đều được mã hóa.

### 5.1. Những kiểm tra bắt buộc theo ngữ cảnh

Khi một thành phần nhận JWT, việc **giải mã chuỗi** chưa đủ để tin cậy nội dung. Các kiểm tra gồm:

1. **Chữ ký và thuật toán**: xác minh chữ ký bằng key tin cậy và thuật toán được phép, không chấp nhận `alg: none` hay để token tự quyết định chính sách thuật toán.
2. **Issuer (`iss`)**: token phải do đúng nhà cung cấp đã cấu hình phát hành.
3. **Audience (`aud`)**: token phải dành cho đúng client (ID Token) hoặc API (access token) nhận nó.
4. **Thời gian (`exp`, `nbf`, `iat`)**: kiểm tra còn hiệu lực và các ràng buộc thời gian thích hợp; dùng clock skew nhỏ, có kiểm soát.
5. **Claims theo mục đích**: với OIDC ID Token có thể gồm `nonce`, `azp` và các yêu cầu xác thực khác; với access token cần đánh giá scope/authority và chính sách API.

Với token dùng chữ ký bất đối xứng, OP thường công bố **JWKS (JSON Web Key Set)** ở endpoint được khai báo trong metadata. Header `kid` giúp chọn key tương ứng trong bộ key được tin cậy. Key có thể được xoay vòng; ứng dụng cần xử lý cập nhật key nhưng **không** tùy tiện tải key từ URL do token chưa xác minh tự chỉ định.

### 5.2. Access token, ID token, refresh token và session cookie

| Dữ liệu | Ai phát hành/quản lý? | Dùng để làm gì? | Thường trình ở đâu? |
| --- | --- | --- | --- |
| **Authorization code** | Authorization Server | Đổi một lần lấy token ở token endpoint. | Callback về client, thường qua query string. |
| **Access token** | Authorization Server | Cho phép truy cập tài nguyên trong phạm vi được cấp. | Header `Authorization: Bearer ...` khi gọi API. |
| **ID Token** | OpenID Provider | Khẳng định sự kiện xác thực và danh tính người dùng cho OIDC Client. | Client nhận qua token endpoint và xác thực tại bước login. |
| **Refresh token** | Authorization Server (nếu được cấp) | Xin access token mới theo chính sách OP. | Back-channel của client, cần lưu bảo mật. |
| **Session ID** | Ứng dụng web / session store | Tìm phiên đăng nhập của ứng dụng. | Cookie browser gửi về ứng dụng. |

Điều cần nhớ:

- **Access token không nhất thiết là JWT**; có nhà cung cấp dùng opaque token. API có thể xác minh JWT tại chỗ hoặc gọi introspection endpoint theo loại token và cấu hình.
- **ID Token thường là JWT** nhưng **không phải access token**: API không nên chấp nhận ID Token chỉ vì chữ ký hợp lệ.
- **Refresh token** rất nhạy cảm; không giả định nó là JWT và không để lộ nó cho browser khi không có lý do thiết kế phù hợp.
- **Session cookie** có thể đủ cho browser truy cập website đã login, nhưng bản thân nó không phải bearer access token để gọi một API OAuth2 khác.

## 6. `state`, `nonce` và PKCE: ba giá trị có nhiệm vụ riêng

Ba cơ chế thường cùng xuất hiện trong một authorization request:

| Giá trị | Được tạo/gửi khi nào? | Kiểm tra/chức năng |
| --- | --- | --- |
| **`state`** | Client tạo khi bắt đầu login, gửi tới authorization endpoint. | Callback phải trả về đúng `state`; giúp liên kết response với yêu cầu đã khởi tạo và chống login CSRF. |
| **`nonce`** | OIDC Client gửi trong authorization request khi sử dụng nonce. | OP đưa nonce vào ID Token; client kiểm tra đúng giá trị đã gửi để chống replay và gắn token với phiên xác thực. |
| **`code_verifier` / `code_challenge` (PKCE)** | Client tạo secret ngẫu nhiên, gửi challenge ở authorization request; giữ verifier để gửi ở token request. | OP kiểm tra phép biến đổi của verifier khớp challenge; authorization code bị chặn sẽ khó bị đổi lấy token bởi bên khác. |

Với `code_challenge_method=S256`:

```text
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
```

`state` **không** thay cho PKCE; `nonce` **không** thay cho `state`. Trong ứng dụng Servlet Spring Security, yêu cầu ủy quyền và `state` thường được lưu tạm trong HTTP session qua `AuthorizationRequestRepository`; nếu session cookie biến mất trước callback, kiểm tra callback có thể thất bại.

Spring Security hỗ trợ PKCE trong OAuth 2.0 Client; quy tắc kích hoạt cụ thể phụ thuộc kiểu client và cấu hình. Với Authorization Code Flow hiện đại, nên sử dụng PKCE ngay cả khi client là confidential khi OP hỗ trợ.

## 7. Spring Security kết nối các lớp này như thế nào?

### 7.1. Security filter chain trong ứng dụng Servlet

Trong Spring MVC, request đi qua **Servlet Filter** trước khi tới controller. Spring Security dùng `FilterChainProxy` và một hoặc nhiều `SecurityFilterChain` để xác định yêu cầu nào phải xác thực và cơ chế nào được áp dụng.

```text
Browser / HTTP request
    |
    v
Servlet container
    |
    v
springSecurityFilterChain (FilterChainProxy)
    |-- tải SecurityContext phù hợp
    |-- đọc cookie / nhận OAuth2 callback / xác thực credential
    |-- xử lý CSRF và các kiểm tra bảo vệ khác
    |-- kiểm tra quyền truy cập URL
    v
DispatcherServlet -> Controller
    |
    v
HTTP response (redirect / 200 / 401 / 403 ...)
```

Các khái niệm nên phân biệt:

- **`SecurityFilterChain`**: tập quy tắc bảo mật cho request, khai báo bằng bean.
- **`Authentication`**: đối tượng mô tả principal, authorities và trạng thái xác thực.
- **`SecurityContext` / `SecurityContextHolder`**: nơi Spring Security giữ `Authentication` trong lúc xử lý request; cơ chế repository giúp lưu/khôi phục bối cảnh giữa các request.
- **`AuthenticationManager` / `AuthenticationProvider`**: phối hợp hoặc thực hiện xác thực theo từng cơ chế.
- **`AuthenticationEntryPoint`**: quyết định cách bắt đầu xác thực với request chưa login, ví dụ redirect tới trang đăng nhập hay trả `401`.
- **`Authorization`**: bước quyết định principal hiện tại có được truy cập tài nguyên hay không. Authentication (xác thực “ai”) khác Authorization (kiểm tra “được làm gì”).

Không nên hiểu rằng mọi request đều gọi OP để xác thực lại. Sau callback đăng nhập thành công, ứng dụng web thường khôi phục `SecurityContext` từ session.

### 7.2. Phân biệt ba nhóm chức năng OAuth2 của Spring Security

| Cấu hình Spring Security | Trường hợp sử dụng | Request/token trọng tâm |
| --- | --- | --- |
| `oauth2Login()` | Người dùng đăng nhập website bằng OP. | Browser redirect, code callback, ID Token, ứng dụng tạo phiên đăng nhập. |
| `oauth2Client()` | Ứng dụng gọi API thay mặt người dùng hoặc dùng client credentials. | Quản lý authorized client, lấy và dùng access token cho request đi ra. |
| `oauth2ResourceServer()` | API của ứng dụng nhận Bearer token từ caller. | Xác minh token của request đi vào, áp dụng scope/authority và chính sách API. |

Một ứng dụng có thể đóng nhiều vai trò, nhưng **không nên mặc định** rằng bật `oauth2Login()` sẽ khiến endpoint API tự xác minh Bearer token. Đó là cơ chế riêng của resource server.

### 7.3. Các endpoint mặc định của `oauth2Login()`

Ở cấu hình mặc định, với client registration ID là `demo`:

| URL | Filter liên quan | Vai trò |
| --- | --- | --- |
| `/oauth2/authorization/demo` | `OAuth2AuthorizationRequestRedirectFilter` | Tạo authorization request và redirect browser đến OP. |
| `/login/oauth2/code/demo` | `OAuth2LoginAuthenticationFilter` | Nhận callback, kiểm tra yêu cầu đăng nhập và thực hiện trao đổi code. |
| `/login` | Cơ chế trang đăng nhập của Spring Security | Có thể là trang login mặc định với liên kết tới OAuth2 provider, tùy cấu hình. |

Khi xử lý OIDC, Spring Security xác thực ID Token và tạo principal như `OidcUser`. Nếu không có scope `openid`, việc đăng nhập bằng OAuth 2.0 thông thường có thể dùng `OAuth2User` thay vì OIDC principal.

## 8. Ví dụ cấu hình một OIDC Client cơ bản

Giả sử ứng dụng Spring Boot cung cấp website có endpoint `/account` và OP công bố discovery metadata theo OIDC. Ứng dụng chạy ở `https://app.example.com`; `demo` là tên registration do chúng ta chọn.

### 8.1. Dependency

Với Maven sử dụng dependency management của Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

Starter này tích hợp các thành phần cho OAuth 2.0 Client và OAuth 2.0 Login. Nếu ứng dụng dùng Thymeleaf, Spring MVC hoặc template engine khác thì thêm dependency tương ứng cho phần giao diện.

### 8.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          demo-provider:
            issuer-uri: https://idp.example.com

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Trong đó:

- `registration.demo` là client registration; `demo-provider` trỏ tới thông tin OP.
- `issuer-uri` phải là issuer thật do OP công bố. Spring dùng discovery metadata khi OP hỗ trợ; URL `https://idp.example.com` ở đây chỉ là tên miền ví dụ.
- Scope `openid` kích hoạt khả năng đăng nhập OIDC. Scope `profile` và `email` yêu cầu thêm claims theo chính sách của OP; không phải mọi provider đều trả mọi claim.
- `{baseUrl}` và `{registrationId}` là placeholder mà Spring Security xử lý trong redirect URI, không phải biến môi trường.
- `OIDC_CLIENT_ID` và `OIDC_CLIENT_SECRET` được nạp từ môi trường hoặc secret store. **Không commit client secret vào Git.**
- `redirect-uri` cần đăng ký tương ứng ở OP và chạy đúng external URL sau proxy.

### 8.3. `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

Đoạn cấu hình cho phép tài nguyên công khai, yêu cầu login đối với phần còn lại và bật các cơ chế OIDC/OAuth2 Client. **Không tắt CSRF** trong ví dụ website dùng session. Spring Security xử lý nhiều chi tiết như authorization request, callback và SecurityContext qua các thành phần đã cấu hình.

Controller có thể đọc principal sau khi người dùng đã đăng nhập:

```java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/account")
    public Map<String, String> account(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "subject", user.getSubject(),
            "displayName", user.getFullName() != null
                ? user.getFullName() : "(chưa cung cấp)"
        );
    }
}
```

Ví dụ chỉ dành cho phiên đăng nhập **OIDC** có `OidcUser`. Không nên trả nguyên ID Token, access token, refresh token hoặc mọi claim ra response chỉ để kiểm tra đăng nhập. Trong thực tế, chỉ trả các dữ liệu mà giao diện cần và người dùng được quyền xem.

Khi client cần gọi API ngoài, thành phần **`OAuth2AuthorizedClient`** liên kết client registration, principal và access token được cấp. Ứng dụng có thể tích hợp với `OAuth2AuthorizedClientManager` hoặc cơ chế hỗ trợ tương ứng. Việc gọi API có access token không làm cookie session trở thành access token.

## 9. Lần theo một request từ khi chưa login đến khi đã login

Giả sử người dùng mở `https://app.example.com/account`:

1. **Browser → Spring:** gửi `GET /account` mà chưa có session đăng nhập hợp lệ. Spring Security xác định URL cần xác thực, rồi dẫn người dùng tới login.
2. **Browser → Spring:** mở `/oauth2/authorization/demo`. Spring tạo authorization request, lưu dữ liệu tương quan (ví dụ `state` và PKCE) và gửi `302` tới OP qua HTTPS.
3. **Browser → OP:** người dùng đăng nhập tại OP; client Spring không nhận mật khẩu OP. OP quyết định có yêu cầu consent hay không.
4. **OP → Browser → Spring:** OP redirect browser về callback kèm `code` và `state`. Spring dùng dữ liệu lưu lúc khởi tạo để xác minh callback tương ứng.
5. **Spring → OP:** backend gọi token endpoint bằng HTTPS, xác thực client khi cần và gửi `code_verifier` nếu dùng PKCE. OP trả token sau khi kiểm tra.
6. **Spring:** xác minh ID Token theo OIDC (ví dụ chữ ký, issuer, audience, hạn dùng và nonce phù hợp), tạo `Authentication`, áp dụng xử lý session đăng nhập, rồi chuyển hướng người dùng về trang đã yêu cầu.
7. **Browser → Spring:** gửi session cookie trong request tiếp theo. Spring khôi phục thông tin đăng nhập và cho phép truy cập `/account`.
8. **Nếu cần gọi API:** Spring lấy authorized client/access token phù hợp rồi gọi API qua HTTPS. API tự kiểm tra access token và quyền của nó.

Bước 4 có kiểm tra `state`, bước 5 có PKCE và bước 6 có xác minh ID Token. Đây là ba lớp bảo vệ phục vụ những mối đe dọa khác nhau.

## 10. Những lỗi hay gặp và cách xác định đúng lớp

| Triệu chứng | Lớp nên kiểm tra | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| OP báo `redirect_uri_mismatch` / `invalid_redirect_uri` | HTTP redirect, client registration, proxy | So chính xác scheme, host, port, path, slash và callback URL đã đăng ký. |
| Callback báo `invalid_state` hoặc không tìm thấy authorization request | Session/cookie, callback, load balancer | Kiểm tra session cookie có được gửi lại, SameSite, domain/path, timeout và chia sẻ session giữa instance. |
| Backend báo lỗi SSL handshake / certificate | TLS và trust store | Kiểm tra CA, hostname, hiệu lực chứng chỉ, URL OP và cấu hình proxy. |
| `401` khi gọi API bằng Bearer token | Resource server / token | Xác minh issuer, audience, signature, hạn dùng và cách gửi header `Authorization`. |
| `403` khi POST biểu mẫu | Authorization hoặc CSRF | Xem log từ chối quyền và CSRF token trước khi đổi cấu hình bảo mật. |
| Đăng nhập thành công nhưng request sau lại chưa login | Cookie/session | Kiểm tra `Secure`, domain/path, browser gửi cookie, session store và session timeout. |
| ID Token bị từ chối | OIDC/JWT | Kiểm tra issuer, client ID/audience, JWKS/key rotation, nonce và đồng hồ hệ thống. |
| Login được nhưng gọi API bị từ chối | OAuth2 access token | Kiểm tra access token được gửi cho đúng API, scopes/roles và audience; không dùng ID Token thay thế. |
| Login lặp lại sau proxy HTTPS | External URL / forwarded headers | Kiểm tra app có nhận diện đúng `https` và callback public URL hay không. |

**Lưu ý khi ghi log:** có thể log request ID, registration ID, status, thời gian xử lý và thông tin lỗi đã lược bỏ dữ liệu nhạy cảm. Tránh ghi toàn bộ URL callback chứa code, header `Authorization`, token, session ID, client secret hoặc dữ liệu người dùng nhạy cảm.

## 11. Tự kiểm tra hiểu biết

**Tình huống A:** Browser đăng nhập thành công vào website, nhận cookie `JSESSIONID`. Sau đó một service khác gọi API chỉ bằng giá trị cookie đó.

- API có tự chấp nhận cookie không? **Không thể suy ra như vậy.** Một API cấu hình theo OAuth2 Resource Server thường đòi Bearer access token có issuer/audience/quyền hợp lệ. Cookie session chỉ có ý nghĩa với hệ thống sở hữu session và cơ chế chia sẻ phiên được thiết kế rõ ràng.

**Tình huống B:** Một ID Token có payload đọc được và ghi `"role": "admin"`.

- Có thể tin ngay role đó không? **Không.** Phải xác minh chữ ký và các claims bắt buộc, đồng thời xác định liệu claim đó có được nguồn danh tính và chính sách ứng dụng cho phép dùng để phân quyền hay không. ID Token không tự động cấp quyền gọi API.

**Tình huống C:** Callback OIDC chạy dưới HTTPS nhưng Spring báo `invalid_state`.

- Có phải TLS hỏng không? **Chưa chắc.** HTTPS có thể hoàn toàn đúng trong khi session chứa authorization request không được tìm lại do cookie, load balancer, timeout hoặc browser policy.

**Tình huống D:** Access token được cấp 10 phút, session website sống 30 phút.

- Người dùng có phải tự động bị đăng xuất sau 10 phút không? **Không nhất thiết.** Session đăng nhập và access token có vòng đời khác nhau. Khi cần gọi API sau lúc access token hết hạn, ứng dụng cần cơ chế lấy token mới phù hợp hoặc yêu cầu đăng nhập lại theo chính sách.

## 12. Ghi nhớ các ranh giới tin cậy

- **HTTP** định nghĩa cách browser, client, OP và API trao đổi request, redirect, header và cookie.
- **TLS** bảo vệ dữ liệu khi truyền, đồng thời giúp xác minh endpoint đang giao tiếp.
- **Session** giúp ứng dụng Spring nhận lại người dùng đã đăng nhập qua nhiều request.
- **JWT** biểu diễn claims có thể được ký; phải xác minh token theo **mục đích sử dụng**.
- **Spring Security** kết nối các cơ chế trên bằng filter chain, authentication, authorization và tích hợp OAuth2/OIDC.
- **OAuth2 access token** dùng cho truy cập tài nguyên, **OIDC ID Token** dùng cho thông tin xác thực của client, còn **session cookie** dành cho trạng thái đăng nhập ở ứng dụng web.

Khi đọc một lỗi hoặc thiết kế một endpoint mới, trước hết hãy xác định: **ai gửi request, ai nhận request, đang dùng credential nào, và thành phần nào phải xác minh credential đó**. Đây là cách tiếp cận hữu ích trước khi đi sâu vào các bước xây dựng một Spring Security OIDC Client thực tế.

### Tài liệu chuẩn để tra cứu thêm

- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110)
- [TLS 1.3 — RFC 8446](https://www.rfc-editor.org/rfc/rfc8446)
- [HTTP State Management Mechanism (Cookies) — RFC 6265](https://www.rfc-editor.org/rfc/rfc6265)
- [JSON Web Token — RFC 7519](https://www.rfc-editor.org/rfc/rfc7519)
- [Proof Key for Code Exchange — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security Reference: OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
