# 3.7. OIDC Authorization Code Flow và quá trình thiết lập phiên

Trong một ứng dụng Spring Boot dùng **Spring Security OAuth 2.0/OIDC Client**, việc người dùng bấm nút **Đăng nhập** thường bắt đầu một chuỗi chuyển hướng giữa trình duyệt, ứng dụng và nhà cung cấp định danh. Sau khi nhà cung cấp định danh xác thực người dùng, ứng dụng nhận kết quả OIDC, tạo `Authentication` và thiết lập **phiên đăng nhập cục bộ** để các HTTP request sau đó tiếp tục sử dụng.

Với **OIDC Authorization Code Flow**, trình duyệt chỉ nhận *authorization code* qua redirect. Backend của ứng dụng dùng code đó để đổi lấy ID Token và Access Token qua kết nối trực tiếp đến OpenID Provider (OP). Sau khi ID Token được xác minh, ứng dụng mới tạo trạng thái đăng nhập và quản lý phiên của riêng mình. Đây là ranh giới quan trọng giữa **đăng nhập tại OP** và **đăng nhập vào ứng dụng Spring Boot**.

Bài học lần lượt đi qua luồng giao thức, những dữ liệu Spring Security lưu giữa các request, cách hình thành `SecurityContext`, vai trò của cookie phiên, các cơ chế bảo vệ và những lỗi phổ biến.

## 1. Các bên tham gia và hai loại phiên đăng nhập

Giả sử hệ thống quản lý đơn hàng chạy tại `https://app.example.org` và dùng một OpenID Provider có issuer `https://id.example.org`.

| Thành phần | Công việc trong flow |
|---|---|
| **End User** | Người cần đăng nhập để dùng chức năng đơn hàng. |
| **Trình duyệt (User Agent)** | Truy cập ứng dụng, làm theo redirect, gửi cookie đến đúng miền. |
| **Spring Boot OIDC Client / Relying Party (RP)** | Khởi tạo authorization request, nhận callback, đổi code lấy token, xác thực ID Token và tạo phiên ứng dụng. |
| **OpenID Provider (OP)** | Xác thực người dùng, có thể yêu cầu MFA/consent, phát hành authorization code và token. |
| **Spring Security Servlet Filter Chain** | Xử lý các request liên quan tới đăng nhập và bảo vệ tài nguyên web. |
| **Resource Server / API** (nếu có) | Kiểm tra Access Token và quyền truy cập dữ liệu khi client gọi API. |

Trong quá trình này tồn tại hai phiên khác nhau:

- **Phiên SSO của OP:** thường được OP duy trì bằng cookie trên miền OP. Phiên này giúp OP nhận ra người dùng đã đăng nhập khi một ứng dụng khác chuyển hướng tới.
- **Phiên của ứng dụng Spring Boot:** thường được ứng dụng duy trì bằng HTTP session và một cookie chứa session ID trên miền ứng dụng. Phiên này giúp Spring Security nhận biết người dùng ở các request tiếp theo.

Một người đã đăng nhập tại OP chưa chắc đã có phiên tại ứng dụng. Ngược lại, khi phiên cục bộ còn hợp lệ, ứng dụng có thể tiếp tục nhận diện người dùng mà không liên tục hỏi OP.

### 1.1. Bốn giá trị không thể dùng thay cho nhau

| Giá trị | Được dùng ở bước nào? | Ý nghĩa |
|---|---|---|
| **Authorization Code** | OP trả về callback; backend dùng ở token endpoint. | Giá trị ngắn hạn, thường chỉ sử dụng một lần để đổi lấy token. |
| **ID Token** | OP trả về cho OIDC Client tại token endpoint. | JWT mang thông tin xác thực và danh tính mà client phải xác minh. |
| **Access Token** | Client dùng khi gọi API/Resource Server được cấp quyền. | Token cấp quyền truy cập tài nguyên; không dùng làm ID Token. |
| **Session cookie** | Trình duyệt gửi đến ứng dụng sau login. | Liên kết browser với phiên cục bộ chứa trạng thái đăng nhập của ứng dụng. |

OIDC sử dụng Authorization Code Grant của OAuth 2.0, đồng thời bổ sung yêu cầu danh tính thông qua scope `openid` và ID Token. Vì vậy, một authorization request chỉ có `response_type=code` mà không yêu cầu OIDC không mặc nhiên là một đăng nhập OpenID Connect.

## 2. Chuẩn bị trước khi flow bắt đầu

Ứng dụng phải được đăng ký làm client tại OP. Một cấu hình server-side confidential client điển hình có:

| Thuộc tính | Ý nghĩa |
|---|---|
| `client_id` | Định danh ứng dụng tại OP; không phải secret. |
| `client_secret` hoặc cơ chế xác thực client khác | Dùng để backend chứng minh danh tính tại token endpoint khi phù hợp. |
| `redirect_uri` | URL callback mà OP được phép chuyển trình duyệt về. |
| `scope` | Cần `openid` để yêu cầu OIDC; có thể thêm `profile`, `email`. |
| `issuer-uri` | Định danh OP đáng tin cậy, dùng trong cấu hình và xác minh token. |
| Authorization endpoint | Endpoint tại OP nhận yêu cầu xác thực/cấp code qua trình duyệt. |
| Token endpoint | Endpoint tại OP nhận code từ backend và cấp token. |
| JWKS / signing key metadata | Thông tin cần thiết để xác minh chữ ký ID Token. |

OIDC Discovery cho phép client khám phá metadata của issuer, ví dụ từ `.well-known/openid-configuration` theo quy tắc đường dẫn issuer. Không lấy issuer hoặc endpoint từ tham số tùy ý trong URL người dùng gửi. Redirect URI mà ứng dụng thực sự tạo ra phải phù hợp URL được đăng ký tại OP, bao gồm scheme, host, path và các ràng buộc khác theo chính sách OP.

Với Spring Security Servlet và một registration tên `company`, hai đường dẫn mặc định quan trọng là:

- `/oauth2/authorization/company`: bắt đầu đăng nhập với registration này.
- `/login/oauth2/code/company`: callback xử lý authorization code hoặc lỗi từ OP.

Đường dẫn đầu thuộc client, dù nó có thể chuyển hướng người dùng tới trang login trước. Đường dẫn callback cũng thuộc **ứng dụng**, không phải token endpoint của OP.

## 3. Toàn bộ OIDC Authorization Code Flow

Sơ đồ sau mô tả ứng dụng web dùng backend Spring Boot quản lý session:

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant C as Spring Security OIDC Client
    participant I as OpenID Provider

    B->>C: GET /orders (chưa có Authentication)
    C->>C: Lưu request ban đầu nếu cần
    C-->>B: Redirect sang trang login / oauth2 authorization
    B->>C: GET /oauth2/authorization/company
    C->>C: Sinh state, nonce, PKCE verifier nếu dùng
    C->>C: Lưu authorization request để đối chiếu
    C-->>B: 302 tới authorization endpoint của OP
    B->>I: GET /authorize?response_type=code&scope=openid...
    I->>I: Xác thực, MFA/consent theo chính sách
    I-->>B: 302 redirect_uri?code=...&state=...
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Xác minh state; lấy yêu cầu gốc
    C->>I: POST token endpoint với code và ràng buộc cần thiết
    I->>I: Xác minh code/client/PKCE
    I-->>C: ID Token, Access Token và token tùy chọn
    C->>C: Xác minh ID Token; tạo OidcUser/Authentication
    C->>C: Thiết lập và lưu SecurityContext trong phiên
    C-->>B: Set-Cookie session (nếu cần), redirect /orders
    B->>C: GET /orders kèm cookie phiên
    C->>C: Khôi phục Authentication, kiểm tra quyền
    C-->>B: Nội dung được phép truy cập
```

Luồng này có ba chặng giao tiếp khác nhau: **trình duyệt ↔ ứng dụng**, **trình duyệt ↔ OP**, rồi **backend ứng dụng ↔ token endpoint OP**. Trao đổi token thuộc chặng cuối; ID Token và Access Token không được đưa vào URL redirect của trình duyệt trong flow server-side đúng chuẩn.

## 4. Bước 1: người dùng vào tài nguyên yêu cầu xác thực

Người dùng mở `GET /orders` khi chưa đăng nhập. Spring Security nhận thấy request không có `Authentication` phù hợp và bắt đầu cơ chế xác thực được cấu hình.

Với `oauth2Login()` mặc định, ứng dụng có thể đưa người dùng tới trang login hiển thị liên kết của các OAuth2 Client registrations, hoặc có thể dùng nút đăng nhập riêng đưa thẳng tới `/oauth2/authorization/company`. Khi dùng `RequestCache`, Spring Security có thể lưu URL người dùng định xem để quay về sau login.

Điểm dễ nhầm: **HTTP session có thể được tạo trước khi xác thực thành công**. Client cần nơi lưu request ban đầu và trạng thái giao thức để kiểm tra callback về sau. Có cookie session lúc này không có nghĩa người dùng đã được xác thực.

### 4.1. Spring tạo authorization request

Khi nhận `GET /oauth2/authorization/company`, Spring Security dựa vào `ClientRegistration` để dựng authorization request và chuyển hướng tới authorization endpoint OP.

Ví dụ biểu diễn URL, với giá trị minh họa được rút gọn:

```text
https://id.example.org/authorize
  ?response_type=code
  &client_id=order-web
  &redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany
  &scope=openid%20profile%20email
  &state=s_7c9...
  &nonce=n_4e2...
  &code_challenge=Kq_...
  &code_challenge_method=S256
```

| Tham số | Mục đích |
|---|---|
| `response_type=code` | Chọn Authorization Code Flow. |
| `client_id` | Nói cho OP biết client nào yêu cầu. |
| `redirect_uri` | Xác định URL callback được phép. |
| `scope` | `openid` kích hoạt ngữ nghĩa OIDC; scope khác yêu cầu thông tin/quyền bổ sung. |
| `state` | Ràng buộc authorization response với request do client khởi tạo, nhằm chống callback giả mạo và nhầm phiên. |
| `nonce` | Ràng buộc ID Token với yêu cầu OIDC khi nonce được gửi. |
| `code_challenge` và `code_challenge_method` | Phần công khai của PKCE để bảo vệ giai đoạn trao đổi code. |

Các tham số `nonce` và `code_challenge` xuất hiện khi client sử dụng/cấu hình cơ chế tương ứng; không nên giả định chúng luôn xuất hiện trong mọi loại client. Nếu cần chứng minh hệ thống dùng PKCE, kiểm tra authorization request thực tế và cách token request gửi verifier.

### 4.2. Tại sao phải lưu request gốc?

Trình duyệt sẽ rời ứng dụng, tới OP và trở về ở **một HTTP request khác**. Client phải nhớ ít nhất dữ liệu cần thiết để xác minh callback thuộc đúng yêu cầu khởi tạo trước đó.

Trong Spring Security Servlet, `OAuth2AuthorizationRequestRedirectFilter` phụ trách khởi tạo/chuyển hướng, còn `AuthorizationRequestRepository` lưu authorization request. Với cấu hình thường gặp, `HttpSessionOAuth2AuthorizationRequestRepository` dùng HTTP session để lưu request này.

Những thông tin cần liên kết gồm `state` và, khi áp dụng, `nonce` và `code_verifier`. Vì vậy, mất cookie/session giữa hai lần chuyển hướng thường gây lỗi `state` hoặc lỗi thiếu trạng thái PKCE. Không nên sửa lỗi bằng cách tắt đối chiếu `state`.

### 4.3. PKCE ràng buộc authorization code như thế nào?

PKCE (*Proof Key for Code Exchange*) vận hành theo ba bước:

1. Client tạo một `code_verifier` ngẫu nhiên đủ mạnh và giữ riêng cho lần đăng nhập đó.
2. Client tạo `code_challenge`, thông thường bằng `BASE64URL(SHA256(ASCII(code_verifier)))` theo phương pháp `S256`, rồi gửi challenge khi xin authorization code.
3. Khi đổi code, backend gửi lại `code_verifier`. OP so sánh verifier với challenge đã gắn với code.

Kẻ chỉ chặn được authorization code nhưng không có verifier sẽ khó đổi code lấy token. PKCE đặc biệt cần thiết cho public client, đồng thời có lợi cho confidential client khi được OP và ứng dụng hỗ trợ. PKCE không thay việc kiểm tra `state` hoặc xác minh ID Token.

## 5. Bước 2: OP xác thực và chuyển trình duyệt trở lại

Trình duyệt mở authorization endpoint trên miền của OP. Tại đây OP có thể:

- Xác thực ngay nếu phiên SSO hiện có đủ điều kiện.
- Yêu cầu mật khẩu, passkey, MFA hoặc phương thức xác thực khác.
- Hiển thị màn hình consent nếu chính sách yêu cầu.
- Từ chối đăng nhập khi người dùng hoặc client không đáp ứng điều kiện.

Khi chấp nhận yêu cầu, OP cấp authorization code ngắn hạn, gắn với client và điều kiện của authorization request. Browser thường nhận redirect:

```http
HTTP/1.1 302 Found
Location: https://app.example.org/login/oauth2/code/company?code=abc...&state=s_7c9...
```

Authorization code **không phải** một phiên đã đăng nhập, cũng không phải ID Token. Code có thời hạn ngắn, thông thường chỉ được sử dụng một lần, và phải được đổi tại token endpoint theo các ràng buộc của OP.

Nếu yêu cầu bị từ chối, OP có thể trả các tham số như `error=access_denied` và `state` qua callback. Client phải xử lý đường thất bại; không tạo `Authentication` thành công.

Không đặt code, token hoặc callback URL đầy đủ chứa code vào log, ticket hỗ trợ, analytics URL hay thông báo lỗi công khai.

## 6. Bước 3: Spring Security xử lý callback

Với endpoint mặc định, `OAuth2LoginAuthenticationFilter` xử lý `/login/oauth2/code/{registrationId}`. Phần logic xác thực OAuth/OIDC cần tìm request gốc và kiểm tra `state` trước khi chấp nhận kết quả callback.

Nếu callback hợp lệ, backend gửi POST tới token endpoint của OP. Một request mang tính minh họa:

```http
POST /token HTTP/1.1
Host: id.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication-value>

grant_type=authorization_code&
code=abc...&
redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=<original-verifier-if-PKCE-was-used>
```

Cách client xác thực tại token endpoint có thể là HTTP Basic, POST body, private key JWT, mTLS hoặc phương thức khác theo registration; ví dụ chỉ thể hiện một phương án. Public client không dựa vào secret nhúng trong ứng dụng để bảo vệ token exchange. Khi dùng PKCE, `code_verifier` phải là giá trị đã sinh cho authorization request ban đầu.

OP kiểm tra code hợp lệ, chưa dùng, chưa hết hạn, được phát hành cho đúng client, redirect URI phù hợp và verifier khớp khi có PKCE. Sau đó OP trả token:

```json
{
  "access_token": "eyJ...or-opaque-value",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email",
  "id_token": "eyJ..."
}
```

`refresh_token` có thể được cấp thêm theo điều kiện của OP; không mặc định mọi flow đều có refresh token. Access Token có thể là JWT hoặc opaque token. Token endpoint có thể trả lỗi, ví dụ `invalid_grant` nếu code đã dùng hoặc không thỏa điều kiện; khi đó client chưa có cơ sở để tạo phiên đăng nhập thành công.

### Callback và token endpoint khác nhau

| Endpoint | Thuộc hệ thống | Ai gọi? | Dữ liệu chính |
|---|---|---|---|
| `/login/oauth2/code/company` | Ứng dụng | Browser sau redirect | `code`, `state` hoặc lỗi. |
| `/token` (theo metadata OP) | OpenID Provider | Backend ứng dụng | Authorization code, redirect URI, client authentication, PKCE verifier nếu có. |
| `/orders` | Ứng dụng | Browser sau login | Cookie phiên cục bộ. |

Đối với OIDC Authorization Code Flow server-side, ID Token được backend nhận tại token endpoint, không phải được browser mang về trong callback URL.

## 7. Bước 4: xác minh ID Token trước khi tạo Authentication

ID Token là JWT được OP phát hành cho OIDC Client. Payload ví dụ:

```json
{
  "iss": "https://id.example.org",
  "sub": "user-94831",
  "aud": "order-web",
  "exp": 1760000300,
  "iat": 1760000000,
  "nonce": "n_4e2..."
}
```

Các timestamp chỉ để minh họa cấu trúc claim, không phải token còn thời hạn ở thời điểm đọc.

Ứng dụng **không được chỉ giải mã JWT rồi tin nội dung**. Những kiểm tra cần thiết theo OIDC bao gồm:

| Điều kiện | Điều client phải xác định |
|---|---|
| Chữ ký / khóa / thuật toán | ID Token hợp lệ theo cơ chế ký và khóa do OP tin cậy công bố, phù hợp thuật toán được phép. |
| `iss` | Khớp issuer đáng tin cậy của client registration. |
| `aud` | Chứa `client_id` nhận token; xử lý `azp` khi yêu cầu OIDC áp dụng. |
| `exp` và thời gian | Token chưa hết hạn và thỏa điều kiện thời gian thích hợp; kiểm tra `iat` và những claim liên quan khi cần. |
| `nonce` | Phù hợp với nonce ban đầu nếu client đã đưa nonce vào authorization request. |
| `auth_time`, `acr`, `amr` nếu áp dụng | Đáp ứng chính sách về thời điểm hoặc mức xác thực, chẳng hạn khi ứng dụng yêu cầu xác thực lại. |

Trong flow `oauth2Login()` với scope `openid`, Spring Security có các thành phần OIDC xử lý token, tạo principal `OidcUser` và trả về `Authentication` sau khi xác minh thành công. Ứng dụng phải cấu hình đúng issuer, registration và chính sách; không bỏ các bước xác minh khi tùy biến.

OP có thể cung cấp thêm **UserInfo endpoint**. Nếu client truy vấn UserInfo, kết quả phải được ràng buộc với cùng `sub` trong ID Token theo OIDC; không được ghép thông tin của hai người dùng khác nhau.

### 7.1. Identity không tự động là authorization

Các claim `iss` và `sub` thường là cơ sở tốt để liên kết danh tính với hồ sơ nội bộ. Cặp **`(issuer, subject)`** đáng tin cậy hơn email làm khóa lâu dài vì email có thể đổi hoặc tái sử dụng.

Ngay cả khi ID Token hợp lệ, ứng dụng vẫn phải kiểm tra quyền đọc, tạo, sửa, duyệt dữ liệu. `Authentication` có principal và authorities phục vụ kiểm soát truy cập, nhưng quyền nghiệp vụ có thể cần ánh xạ nhóm từ OP, kiểm tra role nội bộ hoặc quy tắc theo từng tài nguyên.

**ID Token dành cho OIDC Client; Access Token dành cho Resource Server.** Không chuyển ID Token sang API để làm bearer token, và không giả định Access Token chứa claim đủ để xác thực đăng nhập OIDC cho client.

## 8. Bước 5: tạo SecurityContext và phiên Spring Security

Sau khi OIDC authentication provider xác thực thành công, Spring Security có một `Authentication` mô tả người dùng đã đăng nhập. Tầng bảo mật thiết lập `SecurityContext` cho request hiện tại và lưu ngữ cảnh theo `SecurityContextRepository` được cấu hình để các request sau khôi phục lại.

Đây là **bước thiết lập phiên ứng dụng**. Nó diễn ra sau khi backend trao đổi code và xác minh kết quả OIDC; bản thân việc nhận callback không làm session trở thành một phiên xác thực hợp lệ.

### 8.1. Các thành phần Spring Security liên quan

| Thành phần | Vai trò |
|---|---|
| `OAuth2AuthorizationRequestRedirectFilter` | Tạo/chuyển hướng authorization request tới OP. |
| `AuthorizationRequestRepository` | Lưu authorization request để đối chiếu tại callback; mặc định thông dụng là `HttpSessionOAuth2AuthorizationRequestRepository`. |
| `OAuth2LoginAuthenticationFilter` | Nhận callback authorization code và kích hoạt quy trình xác thực login. |
| OAuth/OIDC authentication providers | Đổi code lấy token, kiểm tra kết quả và tạo principal/authentication phù hợp. |
| `SecurityContextHolder` | Chứa `SecurityContext` trong phạm vi xử lý request hiện tại. |
| `SecurityContextRepository` | Lưu/khôi phục `SecurityContext` giữa các request; có thể sử dụng HTTP session. |
| `RequestCache` và authentication success handler | Ghi nhớ URL đã yêu cầu và điều hướng người dùng sau đăng nhập. |
| `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` | Quản lý OAuth 2.0 authorized client và token dùng khi gọi downstream API; là trách nhiệm lưu trữ khác với `SecurityContext`. |

Một trình tự điển hình sau khi xác minh ID Token thành công:

1. Spring Security xây dựng `OidcUser` (ID Token và có thể có UserInfo) cùng tập authorities.
2. Authentication provider trả về `Authentication` đã xác thực.
3. Spring Security lưu `SecurityContext` bằng repository phù hợp để các HTTP request tiếp theo khôi phục trạng thái người dùng.
4. Bộ xử lý session áp dụng chính sách bảo vệ session fixation và các giới hạn session đã cấu hình.
5. Success handler redirect tới URL được lưu trong request cache hoặc trang mặc định.
6. Browser tiếp tục gửi cookie phiên ứng dụng; request tới ứng dụng được kiểm tra dựa trên authentication đã khôi phục.

HTTP session có thể đã được tạo **trước** khi người dùng hoàn tất đăng nhập để lưu authorization request hoặc URL dự định truy cập. Khi đăng nhập thành công, cơ chế bảo vệ **session fixation** có thể thay đổi session ID. Vì vậy, phải phân biệt việc có một HTTP session với việc session đó chứa `SecurityContext` đã xác thực.

### 8.2. Cookie phiên và request kế tiếp

Phản hồi sau đăng nhập có thể tương tự:

```http
HTTP/1.1 302 Found
Location: /orders
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Đây là header minh họa; thuộc tính cookie thực tế phụ thuộc servlet container, proxy và cấu hình phiên. `JSESSIONID` chỉ là mã nhận diện phiên, không phải OIDC ID Token hoặc Access Token. Ứng dụng có thể chọn tên cookie khác.

Request tiếp theo:

```http
GET /orders HTTP/1.1
Host: app.example.org
Cookie: JSESSIONID=<opaque-session-id>
```

Spring Security lấy `SecurityContext` tương ứng từ nơi lưu trữ, xác định principal/authorities và đánh giá quy tắc truy cập trước khi request đến controller. Nếu phiên đã hết hạn hoặc không còn trạng thái xác thực, người dùng cần thực hiện flow đăng nhập phù hợp lần nữa.

Cookie session của **ứng dụng** gửi về `app.example.org`; cookie SSO của **OP** gửi về miền của OP theo thuộc tính cookie riêng. Không lấy cookie OP làm session ID của ứng dụng.

### 8.3. Vòng đời token khác vòng đời phiên

Giả sử OP phát ID Token hết hạn sau 5 phút, còn HTTP session của ứng dụng hết hạn sau 30 phút.

ID Token phải hợp lệ khi client dùng để xác minh đăng nhập. Sau khi phiên ứng dụng được thiết lập, các request bình thường có thể sử dụng `SecurityContext` còn hiệu lực theo chính sách session, không nhất thiết phải kiểm tra lại ID Token hay chuyển qua OP sau mỗi 5 phút.

Trong khi đó, nếu backend cần gọi API bằng Access Token, token đó phải còn hợp lệ theo API và có thể cần cơ chế làm mới. Refresh Token, nếu có, được quản lý theo chính sách OP và cách lưu `OAuth2AuthorizedClient`. Không nên giả định mọi Access Token đều nằm trong `SecurityContext` hoặc mọi token được lưu trực tiếp vào cookie trình duyệt.

Thời hạn phiên ứng dụng, phiên SSO, ID Token, Access Token và Refresh Token là **các thời hạn độc lập**. Với thao tác nhạy cảm, ứng dụng có thể cần xác thực lại hoặc kiểm tra thời điểm xác thực theo chính sách riêng.

## 9. Triển khai Spring Boot với `oauth2Login()`

### 9.1. Dependency

Ví dụ Gradle trong dự án Spring Boot:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
```

Không cần bật Resource Server nếu bài toán chỉ là login web; API nhận bearer token là một vai trò khác và cần `oauth2ResourceServer()` khi hệ thống có yêu cầu đó.

### 9.2. Client registration và session timeout

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: https://id.example.org

server:
  servlet:
    session:
      timeout: 30m
```

Cấu hình dành cho một server-side confidential client được OP hỗ trợ. Giá trị `OIDC_CLIENT_ID` và `OIDC_CLIENT_SECRET` lấy từ biến môi trường/secret manager tại runtime; không hardcode secret trong source hoặc build frontend.

- `registration.company` liên kết với `/oauth2/authorization/company`.
- `redirect-uri` trỏ tới callback mà Spring Security xử lý; URL thực tế phải đúng URI OP cho phép.
- `scope: openid` làm yêu cầu trở thành OIDC; `profile`, `email` là tùy chọn theo IdP.
- `issuer-uri` cho phép Spring Security nhận metadata issuer và thông tin xác minh phù hợp.

Nếu ứng dụng đứng sau load balancer hoặc reverse proxy, phải bảo đảm URL public được sinh đúng scheme, host, path; chỉ tin forwarded headers từ proxy đã được kiểm soát. Sai URL công khai thường gây `redirect_uri_mismatch` hoặc vòng lặp chuyển hướng.

### 9.3. HTTP security configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Với cấu hình này, `/orders` yêu cầu người dùng đã đăng nhập còn `/public/**` cho truy cập công khai. Lối vào `/oauth2/authorization/company` và callback do các thành phần OAuth2 Login của Spring Security đảm nhiệm.

Không nên cấu hình toàn bộ ứng dụng web thành `SessionCreationPolicy.STATELESS` rồi kỳ vọng mặc định của `oauth2Login()` vẫn lưu authorization request và session đăng nhập. Muốn thiết kế stateless phải chủ động xây dựng cơ chế bảo vệ và lưu trạng thái phù hợp.

### 9.4. Đọc principal đã được xác thực

```java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
```

Sau OIDC login, `@AuthenticationPrincipal` lấy principal của request đang được Spring Security quản lý. Trong hệ thống thật, có thể dùng `(issuer, subject)` để tra cứu hồ sơ ứng dụng rồi kiểm tra quyền theo nghiệp vụ.

Không tự viết controller tại `/login/oauth2/code/company` để đọc authorization code rồi giải mã JWT thủ công khi các bộ lọc mặc định đang đảm nhiệm flow. Nếu cần tùy biến login page, success handler, authorization request resolver hoặc nơi lưu authorized client, nên dùng extension point của Spring Security và giữ nguyên các bước xác minh bắt buộc.

## 10. Các cơ chế bảo vệ khác nhau trong một flow

| Cơ chế | Công việc bảo vệ | Không thay thế được |
|---|---|---|
| `state` | Liên kết authorization response với yêu cầu đăng nhập do client khởi tạo. | Xác minh ID Token, PKCE hoặc CSRF protection của các form nghiệp vụ. |
| `nonce` | Ràng buộc ID Token với authorization request OIDC khi nonce được gửi. | `state`, PKCE hoặc phân quyền. |
| PKCE | Bảo vệ giai đoạn đổi authorization code bằng verifier bí mật của từng request. | Kiểm tra issuer/audience và bảo vệ session cookie. |
| Client authentication | Xác thực confidential client tại token endpoint. | PKCE dành cho public client hoặc kiểm tra ID Token. |
| Xác minh ID Token | Kiểm tra nguồn phát hành và tính hợp lệ của thông tin xác thực OIDC. | Kiểm tra quyền nghiệp vụ trên từng tài nguyên. |
| Session fixation protection | Giảm khả năng chiếm phiên khi session ID bị gán từ trước. | CSRF/XSS protection. |
| CSRF protection | Bảo vệ các request thay đổi trạng thái sử dụng cookie phiên. | `state` của callback OIDC. |
| HTTPS và cookie settings | Bảo vệ đường truyền và giảm lộ cookie phiên. | Xác minh token hoặc kiểm soát truy cập. |

Cookie thường cần `Secure`, `HttpOnly` và `SameSite` phù hợp với cách callback hoạt động. Ví dụ redirect GET OIDC thường có thể hoạt động với `SameSite=Lax`, nhưng response mode khác hoặc cấu trúc domain phức tạp cần đánh giá riêng. Không vô hiệu CSRF toàn ứng dụng chỉ để làm callback OIDC chạy được.

Đừng ghi raw authorization code, Access Token, ID Token, Refresh Token, client secret, `code_verifier` hay session cookie vào log. Khi điều tra vấn đề, log mã lỗi, correlation ID an toàn, điểm bắt đầu/kết thúc flow và kết quả xác minh phù hợp.

## 11. Các tình huống lỗi và nơi cần kiểm tra

### 11.1. Callback có `state` không khớp hoặc bị thiếu

Nguyên nhân thường là authorization request không còn trong session, cookie bị chặn, session hết hạn, cookie sai domain/path, thay đổi host qua proxy hoặc người dùng tạo nhiều luồng đăng nhập song song. Đầu tiên hãy xem **phía OIDC Client** có khôi phục được authorization request đúng với callback hay không.

Không bỏ kiểm tra `state` để làm lỗi biến mất.

### 11.2. Đã nhập mật khẩu tại OP nhưng token endpoint trả `invalid_grant`

Code có thể hết hạn, bị dùng lại, không khớp redirect URI hoặc không có PKCE verifier phù hợp. Đây là lỗi ở **giai đoạn backend trao đổi code**, dù người dùng đã xác thực thành công tại OP. Kiểm tra chính sách và metadata token endpoint mà không in code/verifier vào log.

### 11.3. Token đã nhận nhưng OIDC login thất bại

ID Token có thể sai `iss`, `aud`, chữ ký, `exp`, `nonce` hoặc vi phạm điều kiện xác minh khác. Dù token có trường `name` hoặc `email` dễ đọc, client vẫn phải từ chối tạo `Authentication` nếu kết quả không hợp lệ.

### 11.4. Login xong bị redirect quay lại login liên tục

Thường liên quan đến cookie phiên, mất `SecurityContext`, cấu hình repository hoặc hạ tầng nhiều instance không chia sẻ đúng session. Hãy phân biệt **session dùng giữ authorization request** với **session sau xác thực**; cần truy vết cả hai chặng.

Nếu ứng dụng chạy trên nhiều node, nơi lưu session và authorization request phải nhất quán giữa các node, qua cơ chế session chia sẻ hoặc định tuyến phù hợp. Nơi lưu `OAuth2AuthorizedClient` cũng cần được thiết kế tương ứng nếu ứng dụng dùng Access Token gọi API.

### 11.5. Trình duyệt đã login nhưng endpoint trả 403

`Authentication` tồn tại không có nghĩa người dùng được làm tất cả. Kiểm tra authority mapping, role ứng dụng và quyền theo dữ liệu. Đây là sự khác biệt giữa authentication và authorization.

### 11.6. UI đã login nhưng API bên ngoài trả 401

Phiên web sử dụng session cookie, còn API nhận Access Token. Client phải dùng Access Token hợp lệ, dành cho đúng API; Resource Server kiểm tra chữ ký/introspection, audience, scope và chính sách truy cập của mình. Gửi ID Token thay Access Token không phải cách sửa hợp lệ.

### 11.7. Đăng xuất rồi đăng nhập lại không cần mật khẩu

Ứng dụng có thể đã xóa local session nhưng phiên SSO tại OP vẫn còn. Khi browser chuyển đến OP, OP xác thực bằng phiên SSO đã tồn tại. Nếu muốn đăng xuất đồng bộ, phải thiết kế OIDC logout theo khả năng của OP và quy tắc riêng của các ứng dụng.

### 11.8. Đăng nhập nhiều tab, trình duyệt từ chối cookie, hoặc callback từ môi trường khác

Mỗi authorization response phải liên kết tới authorization request đang còn hiệu lực. Thiết kế lưu state phù hợp cho truy cập song song và kiểm thử cookie theo môi trường thật. Không giả định cùng `state` hoặc cùng `nonce` dùng lại được cho nhiều lần login.

## 12. Cách quan sát và hiểu một lần đăng nhập

Khi dùng công cụ Network của browser cùng log phía server trong môi trường phát triển, có thể lần theo thứ tự:

1. Người dùng truy cập tài nguyên bị bảo vệ; ứng dụng chuyển đến login/authorization entry point.
2. Client gửi browser tới OP với `response_type=code`, scope `openid` và các giá trị bảo vệ phù hợp.
3. Người dùng xác thực hoặc được OP nhận diện từ phiên SSO.
4. OP chuyển về callback với code và state, hoặc trả lỗi.
5. Backend trao đổi code tại token endpoint và nhận ID Token/Access Token.
6. Client xác minh ID Token, tạo `OidcUser` và `Authentication`.
7. Spring Security lưu `SecurityContext` trong cơ chế session đã cấu hình, sau đó redirect đến URL yêu cầu ban đầu.
8. Browser gửi session cookie ở request tiếp theo; ứng dụng khôi phục danh tính và kiểm tra quyền.

Không chụp hoặc chia sẻ URL callback chứa code, header Authorization hoặc cookie phiên thật. Với log Spring Security, chỉ bật mức đủ phục vụ chẩn đoán và hạn chế log nhạy cảm trong production.

### Tài liệu chuẩn để đọc sâu thêm

- [OpenID Connect Core 1.0 — Authorization Code Flow](https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowAuth)
- [OAuth 2.0 RFC 6749 — Authorization Code Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.1)
- [OAuth 2.0 PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [Spring Security — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Session Management (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)

Authorization Code chỉ nối giai đoạn OP xác thực người dùng với bước backend nhận token. **Phiên đăng nhập của ứng dụng** được hình thành khi OIDC Client xác minh kết quả, tạo `Authentication`, lưu `SecurityContext` và duy trì session cookie cho những request sau. Phân biệt rõ các bước này giúp triển khai luồng OIDC an toàn và xử lý đúng các lỗi liên quan đến state, token, phiên và SSO.
