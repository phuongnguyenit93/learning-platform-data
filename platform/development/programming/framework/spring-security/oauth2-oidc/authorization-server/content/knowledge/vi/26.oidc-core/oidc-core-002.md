# OIDC Authorization Code Flow và bộ token được phát hành

## 1. Bối cảnh và mục tiêu

Trong ứng dụng Spring Boot dùng **Spring Security**, **Spring Authorization Server** và **OpenID Connect (OIDC) 1.0**, một tình huống phổ biến là người dùng truy cập web app, được chuyển đến Authorization Server để đăng nhập, sau đó quay lại ứng dụng với phiên đăng nhập đã được thiết lập. Ứng dụng có thể đồng thời nhận access token để gọi Resource Server thay mặt người dùng.

**OIDC Authorization Code Flow** bổ sung lớp xác thực danh tính của OIDC lên OAuth 2.0 Authorization Code Grant. Điểm phân biệt quan trọng là khi request chứa scope `openid` và xử lý đúng OIDC, Token Endpoint trả về **ID Token** cùng **access token**; **refresh token** có thể được phát hành tùy đăng ký client, chính sách và consent.

Đây là bài thuộc chương **OIDC Core và ID Token**, tập trung vào quy trình Authorization Code Flow, ý nghĩa, thời điểm nhận và cách sử dụng an toàn từng token trong Spring Boot.

### 1.1. Câu hỏi bài học giải quyết

- OIDC Authorization Code Flow khác OAuth 2.0 Authorization Code Grant thuần ở điểm nào?
- Browser, Relying Party (RP), Authorization Server/OpenID Provider (OP) và Resource Server làm gì?
- Khi nào nhận authorization code, ID Token, access token và refresh token?
- Vì sao không dùng ID Token để gọi API và không dùng access token như ID Token?
- `state`, `nonce` và PKCE ngăn những nhóm tấn công nào?
- ID Token phải được kiểm tra như thế nào trước khi tạo phiên đăng nhập?
- Cấu hình Spring Authorization Server phát hành đúng bộ token ra sao?
- Spring Security `oauth2Login` xử lý quá trình này như thế nào?
- Cần kiểm thử và vận hành những tình huống sai lệch nào?

### 1.2. Thuật ngữ

| Thuật ngữ | Ý nghĩa trong bài |
|---|---|
| End-User | Người dùng cần được xác thực |
| User Agent | Trình duyệt/ứng dụng điều hướng user |
| RP / OIDC Client | Ứng dụng muốn xác thực user, ví dụ `order-web` |
| OP / AS | OpenID Provider / Authorization Server, ví dụ `auth.example.com` |
| Resource Server | API nhận access token, ví dụ `orders-api` |
| Authorization Code | Grant tạm thời để đổi token ở Token Endpoint |
| ID Token | JWT chứa kết quả xác thực user dành cho RP |
| Access Token | Credential dùng để truy cập protected resource |
| Refresh Token | Credential tùy chọn để xin access token mới |
| Authorization/session | Trạng thái grant và phiên đăng nhập; không phải bản thân các token |

## 2. OAuth 2.0 Code Grant và OIDC Code Flow: giống và khác

OIDC sử dụng cơ chế Authorization Code của OAuth 2.0 nhưng bổ sung chuẩn xác thực user và các yêu cầu kiểm tra ID Token.

| Khía cạnh | OAuth 2.0 Authorization Code | OIDC Authorization Code |
|---|---|---|
| `response_type` | `code` | `code` |
| Scope xác định flow | Scope tài nguyên như `orders.read` | Phải chứa `openid` để yêu cầu OIDC |
| Authorization response | Authorization code (và `state` nếu đã gửi) | Authorization code (và `state` nếu đã gửi) |
| Token response chính | Access token; refresh token nếu có | **Access token + ID Token**; refresh token nếu có |
| Nơi chứa ID Token | Không phải thành phần OAuth 2.0 thuần | **Token Endpoint**, không phải redirect trong Code Flow |
| RP xác thực user | OAuth thuần không định nghĩa ID Token | Dựa trên ID Token hợp lệ theo OIDC |
| Gọi API | Access token | Access token |
| Lấy user claims bổ sung | Không có giao thức chung tương đương OIDC UserInfo | Có thể dùng UserInfo Endpoint |

**Không phải cứ thấy `response_type=code` là đã thực hiện OIDC.** Request phải có `scope=openid`, AS cần bật OIDC và RP phải dùng OIDC-specific validation.

### 2.1. Tại sao chọn Authorization Code Flow?

Trong flow này, Authorization Endpoint trả **code ngắn hạn** qua redirect; ID Token và access token được trả ở **Token Endpoint**. Với confidential web client/BFF, bước trao đổi token có thể diễn ra backend-to-backend và token không phải nằm trong URL redirect của browser.

Điều này tránh đưa token trực tiếp vào URL, giảm lộ qua browser history, referrer hoặc ứng dụng khác so với các flow trả token ở front-channel. Code Flow hiện đại nên kết hợp PKCE, xác thực client khi phù hợp và kiểm tra redirect URI.

Với public client như SPA hoặc mobile app, Token Request có thể phát ra từ môi trường client; khi đó token vẫn hiện diện ở môi trường ứng dụng. **Đặc tính “không đưa token qua authorization redirect” không đồng nghĩa token luôn được giấu khỏi mọi mã JavaScript.**

## 3. Sơ đồ OIDC Authorization Code Flow từ đầu đến cuối

Ví dụ hệ thống có:

- `https://app.example.com`: web application/Relying Party.
- `https://auth.example.com`: OP/Authorization Server.
- `https://orders-api.example.com`: Resource Server.
- Client ID là `order-web` và redirect URI đã đăng ký là `https://app.example.com/login/oauth2/code/order-oidc`.

```mermaid
sequenceDiagram
    autonumber
    actor U as End-User / Browser
    participant RP as Relying Party / order-web
    participant OP as OpenID Provider / auth.example.com
    participant API as Resource Server / orders-api

    U->>RP: Mở trang yêu cầu đăng nhập
    RP->>RP: Tạo state, nonce, PKCE code_verifier/challenge
    RP-->>U: Redirect tới Authorization Endpoint
    U->>OP: GET /oauth2/authorize?response_type=code&scope=openid...
    OP->>U: Yêu cầu đăng nhập nếu cần
    U->>OP: Xác thực user
    OP->>U: Hiển thị consent nếu chính sách yêu cầu
    U->>OP: Chấp thuận
    OP-->>U: 302 tới redirect_uri?code=...&state=...
    U->>RP: Callback chứa code và state
    RP->>RP: Kiểm tra state và correlation
    RP->>OP: POST /oauth2/token + code + code_verifier + client auth
    OP->>OP: Kiểm tra code, redirect_uri, PKCE, client và grant
    OP-->>RP: id_token + access_token (+ refresh_token nếu cấp)
    RP->>RP: Xác minh ID Token; tạo phiên đăng nhập
    RP->>API: Authorization: Bearer access_token
    API->>API: Xác minh token, audience, scope và nghiệp vụ
    API-->>RP: Kết quả API
    RP-->>U: Nội dung ứng dụng
```

### 3.1. Ba vị trí cần phân biệt

1. **Authorization Endpoint** nhận request từ user agent; sau login và consent, trả authorization **code**, không trực tiếp trả ID Token/access token trong OIDC Code Flow.
2. **Token Endpoint** nhận code cùng xác thực client/PKCE; trả **ID Token + access token** và có thể trả refresh token.
3. **Resource Server** nhận **access token**, xác minh quyền; không dùng ID Token làm credential API.

### 3.2. Authentication và authorization diễn ra ở đâu?

- OP xác thực End-User: password, passkey, MFA, federated identity hoặc cơ chế khác.
- OP đánh giá grant và consent theo policy.
- RP dùng ID Token để xác minh kết quả đăng nhập của user.
- API dùng access token để kiểm tra quyền truy cập resource.
- Service/domain vẫn phải kiểm tra ownership, tenant và authorization nghiệp vụ.

Đăng nhập thành công không đồng nghĩa user được phép truy cập mọi API.

## 4. Bước 1 — RP tạo Authentication Request

RP khởi tạo Authorization Request gửi đến Authorization Endpoint, thường qua HTTP redirect của browser.

Ví dụ minh họa, đã xuống dòng cho dễ đọc:

```http
GET /oauth2/authorize?
    response_type=code
    &client_id=order-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Forder-oidc
    &scope=openid%20profile%20orders.read
    &state=RANDOM_STATE_FOR_THIS_LOGIN
    &nonce=RANDOM_NONCE_FOR_THIS_LOGIN
    &code_challenge=BASE64URL_SHA256_OF_VERIFIER
    &code_challenge_method=S256
HTTP/1.1
Host: auth.example.com
```

Đây là ví dụ logic; trên wire, URI phải được encode chính xác và không chứa xuống dòng tùy tiện.

### 4.1. Các tham số cơ bản

| Tham số | Yêu cầu/ý nghĩa |
|---|---|
| `response_type=code` | Chọn Authorization Code Flow |
| `client_id` | Định danh client đã đăng ký ở OP |
| `redirect_uri` | Callback RP; phải phù hợp giá trị được đăng ký |
| `scope` | Phải có `openid`; có thể thêm `profile`, `email`, API scopes |
| `state` | Giá trị khó đoán để liên kết response với request và chống CSRF/login injection |
| `nonce` | Trong Code Flow là tùy chọn theo OIDC Core, nhưng nên dùng khi có hỗ trợ để liên kết ID Token với login request |
| `code_challenge` | PKCE challenge tính từ verifier |
| `code_challenge_method=S256` | Phương thức PKCE nên dùng |

### 4.2. Vì sao `scope=openid` quan trọng?

Ví dụ:

```text
scope=orders.read
```

chỉ là OAuth scope; nó không yêu cầu OIDC authentication.

Trong khi:

```text
scope=openid profile orders.read
```

yêu cầu OIDC Code Flow cùng quyền API. `profile` có thể cho phép các identity claims theo consent/policy; `orders.read` là quyền truy cập API tự định nghĩa, không phải OIDC standard scope.

### 4.3. `state` phải được tạo và lưu như thế nào?

RP tạo `state` mới, khó đoán bằng CSPRNG cho từng Authentication Request, lưu cùng login transaction trong session hoặc cơ chế tương đương rồi so khớp chính xác khi nhận callback.

Không dùng một state cố định toàn hệ thống, timestamp đoán được hoặc giá trị đến từ query parameter chưa kiểm chứng. RP nên hủy hoặc đánh dấu login transaction đã sử dụng để tránh replay.

### 4.4. `nonce` là tùy chọn, không được nhầm là bắt buộc với Code Flow

OIDC Core định nghĩa `nonce` **OPTIONAL** trong Authorization Code Flow; nó bắt buộc trong một số luồng front-channel khác. Tuy nhiên, RP hiện đại có thể phát nonce và nếu đã phát, RP phải kiểm tra ID Token chứa cùng giá trị.

Nonce khác state:

- State gắn **authorization response** với request đang chờ.
- Nonce gắn **ID Token** với authentication transaction.

Không cho rằng chỉ kiểm tra state là có thể bỏ mọi validation của ID Token.

## 5. PKCE: bảo vệ authorization code

PKCE theo RFC 7636 giảm khả năng dùng authorization code bị chặn hoặc bị đánh cắp, đặc biệt với public client. Best Current Practice hiện đại cũng khuyến nghị PKCE rộng rãi với Authorization Code Flow.

Client sinh `code_verifier` ngẫu nhiên có entropy cao, tính `code_challenge`:

```text
code_challenge = BASE64URL(
    SHA-256(ASCII(code_verifier))
)

code_challenge_method = S256
```

Authorization Request chỉ gửi challenge; RP giữ verifier trong trạng thái giao dịch và gửi verifier ở Token Request.

### 5.1. Vai trò PKCE so với client secret

| Cơ chế | Chứng minh hoặc bảo vệ gì? |
|---|---|
| Client secret / private_key_jwt / mTLS | Xác thực confidential client với Token Endpoint |
| PKCE | Liên kết authorization code với client instance đã khởi tạo request |
| `state` | Liên kết callback với login transaction và chống CSRF |
| `nonce` | Liên kết ID Token với authentication request |

PKCE **không phải** thay thế client authentication của confidential client. Ngược lại, public client không có khả năng giữ client secret không nên nhúng secret vào SPA/mobile.

### 5.2. Tại sao dùng S256?

`plain` không cung cấp mức bảo vệ tương tự khi attacker nhìn được challenge. Nên yêu cầu S256, từ chối downgrade nếu client đã đăng ký policy bắt buộc PKCE.

Code verifier không được đưa vào Authorization Request và không log. Nếu bị lộ cùng code trong thời gian code còn hiệu lực, lợi ích PKCE giảm nghiêm trọng.

## 6. Bước 2 — OP xác thực người dùng và xử lý consent

Khi nhận Authorization Request, OP kiểm tra client, response type, scope, redirect URI, PKCE và các tham số liên quan. Nếu user chưa được xác thực hoặc cần reauthentication, OP chạy cơ chế login (form login, MFA, passkey hoặc identity federation).

**Xác thực người dùng ở OP không đồng nghĩa client có quyền tự động nhận mọi scope.** OP có thể yêu cầu consent và chỉ cấp scopes theo registration, user policy và business rules.

### 6.1. Các tham số OIDC hỗ trợ ngữ cảnh xác thực

| Tham số | Ý nghĩa |
|---|---|
| `prompt=login` | Yêu cầu OP thúc đẩy reauthentication |
| `prompt=none` | Không cho phép tương tác UI; nếu không thể hoàn tất phải trả lỗi phù hợp |
| `prompt=consent` | Yêu cầu prompt consent theo giao thức/policy |
| `max_age` | Tuổi tối đa của phiên xác thực; `max_age=0` tương đương yêu cầu reauthentication |
| `login_hint` | Gợi ý user identifier, không phải bằng chứng danh tính |
| `acr_values` | Yêu cầu mức/ngữ cảnh xác thực theo OP policy |

Khi request có `max_age`, ID Token trả về phải có `auth_time` theo OIDC Core. Không tự đặt `auth_time` bằng `iat` của token: thời điểm user đăng nhập có thể sớm hơn thời điểm phát token.

### 6.2. Consent và scopes được cấp

OP chỉ cấp scope nằm trong chính sách được phép. Nếu người dùng từ chối, OP có thể redirect lỗi như `access_denied`. Không trả code thành công rồi phát token vượt scope user/client đã được cấp.

Nếu client yêu cầu scope khác phạm vi đăng ký, OP phải xử lý theo policy và giao thức; không mặc định “scope nào client gửi cũng được”.

## 7. Bước 3 — OP trả authorization code qua callback

Sau login và consent thành công, OP chuyển browser về redirect URI đã đăng ký:

```http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/order-oidc?code=ONE_TIME_AUTHORIZATION_CODE&state=RANDOM_STATE_FOR_THIS_LOGIN
Cache-Control: no-store
```

Với response type `code` mặc định, code và state nằm trong **query component** của redirect URI. Cách response mode khác cần được cấu hình rõ nếu sử dụng.

### 7.1. Authorization code là grant tạm thời, không phải token API

Authorization code:

- Có thời hạn ngắn.
- Chỉ được dùng một lần.
- Được ràng buộc với client, redirect URI và PKCE challenge.
- Được đổi ở Token Endpoint.
- Không mang ngữ nghĩa “caller có quyền đọc order” để API trực tiếp chấp nhận.

Không gọi Resource Server với `Authorization: Bearer <authorization-code>`.

### 7.2. RP phải kiểm tra callback

RP thực hiện tối thiểu:

1. Kiểm tra callback khớp giao dịch login đang chờ.
2. So khớp `state` với giá trị đã phát.
3. Nếu có `error` thì xử lý theo giao thức, không tiếp tục đổi token.
4. Xác nhận có authorization code hợp lệ về mặt cấu trúc và không rỗng.
5. Lấy `code_verifier` gắn với chính transaction đó.
6. Gửi code trực tiếp tới Token Endpoint của OP tin cậy.
7. Đánh dấu transaction đã sử dụng.

Không đưa code vào log, analytics URL, link ngoài hoặc referrer. Dù code ngắn hạn và được PKCE bảo vệ, vẫn phải bảo mật nó.

## 8. Bước 4 — RP đổi code tại Token Endpoint

Với confidential web client, backend gửi HTTP POST tới Token Endpoint qua TLS:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_REGISTERED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=ONE_TIME_AUTHORIZATION_CODE
&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Forder-oidc
&code_verifier=ORIGINAL_CODE_VERIFIER
```

Đây là minh họa form URL-encoded. Các dòng có dấu `&` ghép thành một body chuẩn; không gửi code qua query string của Token Endpoint.

### 8.1. Các kiểm tra quan trọng ở OP

| Kiểm tra | Lý do |
|---|---|
| Client authentication nếu là confidential client | Bảo đảm đúng client đang đổi code |
| `grant_type=authorization_code` | Chọn đúng grant |
| Code còn hạn, chưa dùng và tồn tại | Ngăn replay code |
| Code thuộc đúng client | Ngăn token theft giữa client |
| `redirect_uri` phù hợp code/request | Ngăn đổi code với callback khác |
| `code_verifier` khớp PKCE challenge | Ngăn code interception |
| Consent, subject và scope còn hợp lệ theo policy | Không phát token trái grant |
| TLS và rate limit | Giảm lộ credential và brute force |

Nếu code đã được dùng lại, OP phải từ chối; theo OAuth, khi phát hiện code reuse, có thể cần thu hồi các token liên quan theo chính sách/chuẩn áp dụng.

### 8.2. Confidential client và public client

Confidential client thường dùng `client_secret_basic`, `private_key_jwt` hoặc mTLS để xác thực. Public SPA/mobile client không có client secret đáng tin, dùng `ClientAuthenticationMethod.NONE` và PKCE; không nên đặt client secret trong JavaScript hoặc binary rồi coi nó là bí mật.

Không nhầm private key của client authentication với PKCE verifier. Chúng bảo vệ các bề mặt khác nhau.

## 9. Bước 5 — Token Endpoint trả bộ token

Một OIDC Code Flow thành công trả **ID Token** và **access token** trong Token Response, cùng thông tin OAuth và có thể có refresh token:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile orders.read",
  "id_token": "SIGNED_ID_TOKEN_JWT",
  "refresh_token": "OPTIONAL_REFRESH_TOKEN_VALUE"
}
```

`refresh_token` trong JSON trên **chỉ minh họa trường hợp OP thực sự cấp refresh token**. Nếu OP không cấp, trường này phải được bỏ khỏi response; không tự điền chuỗi rỗng rồi coi là hợp lệ.

### 9.1. Trường nào bắt buộc?

| Trường | Quy tắc/ý nghĩa |
|---|---|
| `access_token` | Có trong Token Response thành công |
| `token_type` | OAuth token type, thường là `Bearer`; với sender-constrained token có thể khác |
| `id_token` | **Bắt buộc trong OIDC Authorization Code Flow** |
| `expires_in` | Thời hạn access token, theo giây; khuyến nghị trả |
| `scope` | Có thể xuất hiện theo OAuth contract, đặc biệt khi khác scope request |
| `refresh_token` | Tùy chọn, phụ thuộc policy và grant của client |

Không nhầm `expires_in` với thời gian sống của ID Token hoặc refresh token. ID Token có claim `exp` riêng; refresh token được quản lý theo TTL/rotation/revocation của nó.

### 9.2. Vì sao không có token trong authorization redirect?

Với `response_type=code`, authorization response chuyển qua browser chỉ chứa code (và state/error). Token được trả bởi Token Endpoint sau một yêu cầu riêng, thường backend-to-backend ở confidential RP. Đó là khác biệt cốt lõi với Implicit/Hybrid Flow.

## 10. ID Token — kết quả xác thực dành cho Relying Party

**ID Token là một JWT** mô tả kết quả xác thực End-User do OP đưa cho RP. ID Token dành cho **client/RP**, không dành cho Resource Server.

Payload minh họa:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "order-web",
  "exp": 1794825600,
  "iat": 1794825300,
  "auth_time": 1794825000,
  "nonce": "RANDOM_NONCE_FOR_THIS_LOGIN",
  "acr": "urn:example:loa:2"
}
```

Đây là payload ví dụ; ID Token trên wire được ký thành JWT JWS và có thể được mã hóa nếu RP/OP cấu hình JWE theo profile. Các con số thời gian chỉ minh họa NumericDate.

### 10.1. Claims bắt buộc

| Claim | Ý nghĩa | Kiểm tra ở RP |
|---|---|---|
| `iss` | Issuer của OP | Khớp issuer tin cậy đã cấu hình |
| `sub` | Subject identifier của End-User | Không rỗng, ổn định theo semantics của OP |
| `aud` | Audience của token | Phải chứa `client_id` của RP |
| `exp` | Thời điểm ID Token hết hiệu lực | Chưa hết hạn theo clock skew nhỏ |
| `iat` | Thời điểm token được phát hành | Giá trị hợp lệ theo policy |

### 10.2. Các claims theo điều kiện

| Claim | Điều kiện/ý nghĩa |
|---|---|
| `nonce` | Nếu Authorization Request có nonce, RP phải kiểm tra đúng giá trị trong ID Token |
| `auth_time` | Bắt buộc khi request dùng `max_age` hoặc khi được yêu cầu theo chuẩn; là thời điểm xác thực user |
| `acr` | Authentication Context Class Reference; chỉ tin nếu OP đã định nghĩa semantics |
| `amr` | Authentication Methods References; mô tả phương pháp xác thực khi được cung cấp |
| `azp` | Authorized party; cần kiểm tra theo quy tắc khi có nhiều audience hoặc claim hiện diện |
| `at_hash` | Hash access token; là tùy chọn trong Code Flow, xác minh nếu được sử dụng theo profile/policy |
| `email`, `name` | Identity/profile claims tùy scope, consent và policy; không được bảo đảm luôn có |

### 10.3. Audience của ID Token là RP, không phải API

Ví dụ:

```text
ID Token:
aud = "order-web"

Access Token:
aud = "https://orders-api.example.com"   (nếu token profile có aud)
```

ID Token chứng minh user được OP xác thực cho RP `order-web`. Nó không phải credential để `orders-api` chấp nhận. Một API chỉ nên nhận access token được cấp cho API đó và theo token profile tương ứng.

### 10.4. `sub` không phải email

`sub` là subject identifier do issuer định nghĩa. Không giả định nó là username/email, không lấy email làm primary key nếu email có thể thay đổi. OIDC có public hoặc pairwise subject identifiers; RP cần lưu identity theo cặp `(iss, sub)` để tránh trùng subject giữa nhiều issuer.

## 11. Access Token — quyền gọi Resource Server

**Access token** được client trình tới protected resource. Nó không phải bằng chứng đăng nhập dành cho RP; semantics của nó là cấp quyền truy cập tài nguyên.

Ví dụ:

```http
GET /orders/123 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
```

RS phải xác minh token theo loại token AS phát hành:

- **JWT access token:** xác minh chữ ký, issuer, audience, expiry và claims/profile, ví dụ RFC 9068 nếu được áp dụng.
- **Opaque access token:** gọi Introspection Endpoint theo RFC 7662.
- **Sender-constrained token:** xác minh thêm ràng buộc mTLS/DPoP như profile yêu cầu.

### 11.1. Access token có thể là JWT hoặc opaque

OIDC Core không ép mọi access token phải là JWT. Trong Spring Authorization Server, `OAuth2TokenFormat.SELF_CONTAINED` thường chọn JWT access token, trong khi `OAuth2TokenFormat.REFERENCE` chọn reference/opaque token theo cấu hình.

ID Token là JWT có quy tắc OIDC; access token có định dạng theo policy và token profile của AS.

### 11.2. Scope là coarse-grained authorization

Ví dụ access token có scope `orders.read`. RS có thể ánh xạ thành authority `SCOPE_orders.read` nhưng vẫn cần kiểm tra:

- User có sở hữu order này không?
- Order thuộc tenant nào?
- Resource state có cho phép thao tác không?
- Client có quyền truy cập chính Resource Server này không?

Không dựa vào `active=true` hoặc chữ ký hợp lệ để bỏ qua authorization theo nghiệp vụ.

## 12. Refresh Token — có thể có, không phải mặc định

Refresh token cho phép client xin access token mới mà không cần chuyển End-User qua toàn bộ login/consent flow. Tuy nhiên, **OIDC Authorization Code Flow không bắt buộc OP phải phát refresh token**.

Việc cấp refresh token phụ thuộc:

- Client đã đăng ký `refresh_token` grant hay chưa.
- Client type và cơ chế bảo vệ refresh token.
- Consent/offline access policy.
- Security posture của OP.
- Token settings và policy cấp quyền.

### 12.1. `offline_access` không tự bảo đảm refresh token

OIDC định nghĩa scope `offline_access` để yêu cầu access khi user không hiện diện. Với offline access, OP phải thực thi consent theo các điều kiện OIDC Core; `prompt=consent` thường được yêu cầu trừ khi có căn cứ xử lý khác theo chuẩn.

**Chỉ thêm `offline_access` vào scope không bảo đảm refresh token sẽ được cấp.** OP có thể từ chối hoặc bỏ qua yêu cầu nếu điều kiện chưa được thỏa mãn.

### 12.2. Refresh Token Grant

Ví dụ request khi có refresh token hợp lệ:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE
```

Response có access token mới, có thể có refresh token mới nếu server áp dụng rotation. Với OIDC, refresh response có thể chứa ID Token theo quy tắc OIDC; không được giả định luôn có ID Token mới trong mọi refresh response.

### 12.3. Rotation và reuse detection

Với confidential web client, refresh token nên được lưu ở storage phía server đã được bảo vệ. Với public client, đặc biệt SPA/mobile, cần xem xét rotation hoặc sender constraint, reuse detection, expiry và cơ chế thu hồi phù hợp OAuth Security BCP.

Không log refresh token, không gửi nó vào URL, không trả nó cho browser nếu kiến trúc BFF có thể giữ token phía server. Token cũ bị dùng lại sau rotation cần được xử lý theo threat model.

## 13. Authorization Code, ID Token, Access Token, Refresh Token và session

Bốn giá trị không thể dùng thay thế nhau:

| Thành phần | Ai nhận? | Dùng để làm gì? | Lifetime/đặc điểm |
|---|---|---|---|
| Authorization code | RP callback qua browser | Đổi tại Token Endpoint | Rất ngắn, dùng một lần |
| ID Token | OIDC RP | Xác minh kết quả xác thực user | JWT có `exp` riêng |
| Access token | Resource Server khi client gọi API | Cấp quyền API | JWT/opaque, có TTL, scope/audience |
| Refresh token | OAuth client được cấp phép | Xin access token mới | Tùy chọn; rotation/revocation |
| RP session cookie | Browser và RP | Duy trì phiên đăng nhập ứng dụng | Phụ thuộc session policy, không phải token OAuth |
| OP login session | Browser và OP | Nhớ trạng thái xác thực tại OP | Độc lập tương đối với RP session/token |

### 13.1. ID Token hết hạn có làm RP session kết thúc ngay?

Không nhất thiết. ID Token `exp` mô tả tính hợp lệ khi RP xác minh token, không tự định nghĩa TTL của session cookie do RP phát hành. RP session được quản lý theo authentication/session policy của ứng dụng.

Tuy nhiên, ứng dụng không được dùng ID Token đã hết hạn như credential đang hợp lệ để phát sinh xác thực mới. SLO, session invalidation, reauthentication và logout phải được thiết kế nhất quán.

### 13.2. Logout cũng không đơn giản là xóa access token

Logout ở RP có thể cần xóa session local, thu hồi refresh token khi phù hợp và sử dụng cơ chế OIDC RP-Initiated Logout / Session Management nếu được hỗ trợ. Xóa cookie của RP không tự vô hiệu hóa mọi access token đã phát hành.

## 14. Xác minh ID Token trước khi tạo phiên đăng nhập

Đây là bước không được bỏ qua. RP không được chỉ Base64URL-decode payload rồi tin các claims.

### 14.1. Checklist validation

1. Nhận token qua kênh Token Endpoint được tin cậy; bảo vệ TLS.
2. Parse ID Token JWT theo thuật toán và định dạng đã đăng ký.
3. Xác minh chữ ký JWS bằng khóa phù hợp với issuer/client registration (hoặc giải mã trước nếu có JWE).
4. Kiểm tra `iss` khớp issuer của OP đã cấu hình.
5. Kiểm tra `aud` chứa `client_id` của RP.
6. Kiểm tra `azp` khi xuất hiện hoặc khi multi-audience theo OIDC Core.
7. Kiểm tra `exp` chưa hết hạn; `iat` hợp lệ theo policy.
8. Nếu gửi `nonce`, xác minh claim nonce trùng login transaction.
9. Nếu gửi `max_age`, kiểm tra `auth_time` và điều kiện reauthentication.
10. Kiểm tra các điều kiện bổ sung của profile như `acr`, `at_hash` nếu áp dụng.
11. Liên kết identity theo `(iss, sub)` và chỉ sau đó hoàn tất authentication ở RP.

OIDC Core có quy tắc riêng cho một số signing algorithms và client authentication context. Không tự viết logic “chỉ chấp nhận RS256” cho mọi RP nếu client registration thỏa thuận thuật toán khác; hãy dùng allowlist theo client/issuer và thư viện OIDC chuẩn.

### 14.2. Không tin alg/key URL từ token tùy ý

RP không được tải `jku` hoặc `x5u` từ JWT do attacker gửi rồi tin khóa đó. Public keys phải đến từ JWK Set URI được cấu hình hoặc discovery của issuer đáng tin.

Bảo vệ chống `alg=none`/algorithm confusion, kiểm tra `kid` như key selector trong trust store, không coi `kid` là nguồn trust.

### 14.3. Kiểm tra nonce và state ở hai điểm khác nhau

- `state`: RP kiểm tra khi browser trở về callback, trước khi đổi code.
- `nonce`: RP kiểm tra sau khi nhận và xác minh ID Token, khi nonce đã được gửi trong request.

Nếu dùng nonce, giữ nonce cùng login transaction và xóa sau khi hoàn tất. Không bỏ kiểm tra nonce chỉ vì ID Token có chữ ký hợp lệ.

### 14.4. Trường hợp ID Token có `at_hash`

Trong Authorization Code Flow, `at_hash` là tùy chọn. Nếu profile/OP đưa claim này và RP sử dụng validation theo chuẩn, RP có thể kiểm tra hash của access token theo thuật toán ký ID Token. Không nhầm `at_hash` với chữ ký hoặc với claim `ath` của DPoP.

## 15. UserInfo Endpoint và claims danh tính bổ sung

Nếu RP cần thêm user claims, nó có thể gọi **OIDC UserInfo Endpoint** bằng access token được cấp cho mục đích đó, theo contract OP.

Ví dụ:

```http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
```

Response minh họa:

```json
{
  "sub": "user-42",
  "preferred_username": "user42",
  "name": "User Example"
}
```

### 15.1. Ràng buộc `sub`

RP phải kiểm tra `sub` trong UserInfo Response **khớp chính xác** `sub` của ID Token đã xác minh. Nếu không khớp, tuyệt đối không kết hợp claims vì có thể trộn dữ liệu hai user.

### 15.2. `profile` và `email` không bảo đảm mọi claim luôn xuất hiện

Scope cho phép yêu cầu loại dữ liệu theo OIDC, nhưng nội dung thực trả về phụ thuộc OP, consent, identity source và policy. Không giả định `email_verified=true` chỉ vì có email; kiểm tra giá trị và semantics từng claim.

Không sao chép tất cả UserInfo claims vào JWT access token nếu API không cần; hạn chế PII và data minimization.

## 16. Cấu hình Spring Authorization Server bật OIDC

Spring Authorization Server/Spring Security Authorization Server cung cấp OIDC configurer, nhưng **OIDC không mặc định bật trong cấu hình tối thiểu**. Cần chủ động bật khi muốn phát ID Token theo OIDC Code Flow và hỗ trợ OIDC endpoints.

### 16.1. Với cấu hình Spring Security Authorization Server thế hệ mới

Các dòng Spring Security mới tích hợp Authorization Server DSL; mô hình cấu hình như sau:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .oauth2AuthorizationServer(authorizationServer -> {
            http.securityMatcher(
                authorizationServer.getEndpointsMatcher());
            authorizationServer.oidc(Customizer.withDefaults());
        })
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .exceptionHandling(exceptions -> exceptions
            .defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}
```

Đây là khung code theo cấu hình mới; import và các bean hạ tầng được lược bớt. Cần thêm user authentication chain, RegisteredClientRepository, OAuth2AuthorizationService, signer/JWK, issuer và các service tùy môi trường. Với UserInfo endpoint có yêu cầu dùng JWT authentication, cần cấu hình Resource Server/JwtDecoder tương ứng.

### 16.2. Với dòng Spring Authorization Server 1.x

Trong nhiều dự án Spring Boot cũ hơn, có thể dùng API configurer:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .exceptionHandling(exceptions -> exceptions
            .defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}
```

**Chọn đúng một cách cấu hình phù hợp dependency đang dùng**; không trộn API của các phiên bản. Không sao chép code của Spring Security 7 vào dự án SAS 1.x mà không kiểm tra compatibility.

### 16.3. User authentication chain riêng

Authorization Code Flow yêu cầu End-User được xác thực. Ví dụ ứng dụng AS có chain cho form login:

```java
@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
```

Chain này bổ sung cơ chế đăng nhập user; production có thể dùng MFA, WebAuthn/passkey hoặc federation. Đừng nhầm đăng nhập End-User ở OP với client authentication tại Token Endpoint.

### 16.4. JWK, JwtDecoder và issuer

OIDC ID Token được ký và RP cần public key/JWKS tin cậy. OP nên cấu hình `JWKSource<SecurityContext>` với signing key bảo vệ trong key store/KMS, và issuer ổn định:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .build();
}

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
```

Bean `JwtDecoder` đặc biệt cần thiết cho OIDC UserInfo endpoint và một số OIDC endpoint khác theo cấu hình framework. Không dùng signing key mới ngẫu nhiên mỗi lần khởi động production mà không có key rotation strategy; token cũ sẽ không được xác minh nếu public key tương ứng biến mất.

### 16.5. Các OIDC endpoints

Khi bật OIDC, OP thường công bố:

| Endpoint | Chức năng |
|---|---|
| `/.well-known/openid-configuration` | Provider Configuration Discovery |
| `/oauth2/authorize` | Authorization Request, login/consent |
| `/oauth2/token` | Đổi code thành token |
| `/oauth2/jwks` | Public keys để RP xác minh JWT |
| `/userinfo` | Trả identity claims theo access token |
| OIDC Logout endpoint | Phối hợp logout nếu cấu hình/hỗ trợ |
| OIDC Client Registration | Tùy chọn; không mặc định bật ở mọi phiên bản |

URI thực tế phụ thuộc AuthorizationServerSettings và cấu hình issuer/endpoint. Không hard-code mọi URL chỉ từ tên controller; đọc OIDC discovery metadata của OP.

## 17. RegisteredClient cho OIDC Authorization Code

Để client được thực hiện flow, cần `RegisteredClient` với authorization code, redirect URI, client authentication method, scope `openid` và token settings.

Ví dụ confidential BFF:

```java
RegisteredClient orderWeb = RegisteredClient
    .withId(UUID.randomUUID().toString())
    .clientId("order-web")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(
        AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri(
        "https://app.example.com/login/oauth2/code/order-oidc")
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .scope("orders.read")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .authorizationCodeTimeToLive(Duration.ofMinutes(3))
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build())
    .build();
```

Đây là bean/model snippet, chưa phải cấu hình AS chạy độc lập. Các giá trị TTL và redirect URI chỉ minh họa. Credential phải đến từ secret manager; `PasswordEncoder` phải tương thích client authentication provider.

### 17.1. Ý nghĩa từng phần

| Cấu hình | Tác động |
|---|---|
| `authorization_code` | Client được thực hiện code grant |
| `refresh_token` | Client được phép xin token mới bằng refresh grant; chưa bảo đảm refresh token sẽ được cấp |
| `redirectUri(...)` | Callback chính xác được OP công nhận |
| `scope(OidcScopes.OPENID)` | Client được phép yêu cầu OIDC |
| `requireProofKey(true)` | Bắt buộc PKCE cho code flow của client |
| `requireAuthorizationConsent(true)` | OP cần xử lý consent theo cài đặt |
| `authorizationCodeTimeToLive` | TTL của code |
| `accessTokenTimeToLive` | TTL access token |
| `refreshTokenTimeToLive` | TTL refresh token nếu cấp |
| `reuseRefreshTokens(false)` | Yêu cầu refresh token rotation theo cơ chế framework |

### 17.2. Client public khác client confidential

Với public SPA/mobile:

- Dùng `ClientAuthenticationMethod.NONE` thay vì secret.
- Bắt buộc PKCE S256 theo policy.
- Đăng ký redirect URI phù hợp app type.
- Không hard-code shared secret trong client bundle.
- Kiểm tra khả năng cấp refresh token và các ràng buộc bảo mật của phiên bản/OP.
- Không dùng ví dụ confidential client ở trên cho SPA bằng cách bê nguyên secret.

### 17.3. Ký ID Token và tùy biến claims

Spring Authorization Server cung cấp `OAuth2TokenCustomizer<JwtEncodingContext>` để thêm claims được phép vào JWT, nhưng cần tách ID Token với access token:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> idTokenCustomizer() {
    return context -> {
        if (!OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            return;
        }

        // Chỉ bổ sung claims đã được policy cho phép và lấy từ
        // identity source đáng tin; không tự ý sửa iss, sub, aud, exp.
    };
}
```

Đoạn code minh họa điểm mở rộng. Một bean customizer duy nhất có thể cần xử lý cả access token và ID token tùy cấu hình; đừng tạo nhiều bean cùng generic type và nghĩ framework tự hợp nhất chúng.

Không chèn email, phone, tenant role hoặc auth_time do client tự gửi. ID Token phải giữ semantics OIDC, đặc biệt `iss`, `sub`, `aud`, `exp`, `iat` và nonce/auth_time theo điều kiện.

## 18. Cấu hình Relying Party bằng Spring Security oauth2Login

Ở phía RP (ứng dụng web client), Spring Security `oauth2Login` xử lý Authorization Code Flow và các bước OIDC khi scope có `openid`.

Ví dụ Spring Boot properties:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          order-oidc:
            provider: local-op
            client-id: order-web
            client-secret: SECRET_INJECTED_FROM_SECURE_CONFIGURATION
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,orders.read
        provider:
          local-op:
            issuer-uri: https://auth.example.com
```

Giá trị `SECRET_INJECTED_FROM_SECURE_CONFIGURATION` chỉ là placeholder, không phải secret dùng production. Nên inject biến/secret thực khi deploy.

### 18.1. Bật OIDC login

```java
@Bean
SecurityFilterChain relyingPartySecurity(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/", "/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());

    return http.build();
}
```

Với `scope` chứa `openid`, Spring Security sử dụng các thành phần OIDC khi xử lý login, validate ID Token và tạo OIDC principal. RP không cần tự tạo controller đổi code bằng HTTP client nếu đã dùng oauth2Login theo đúng mô hình.

### 18.2. URL khởi tạo và callback

Theo cấu hình mặc định Spring Security servlet:

```text
GET /oauth2/authorization/order-oidc
     |
     v
Redirect tới OP Authorization Endpoint

GET /login/oauth2/code/order-oidc?code=...&state=...
     |
     v
Spring Security xử lý callback và Token Request
```

Đừng đổi redirect URI ở OP mà quên cập nhật ClientRegistration của RP. Redirect URI phải được so khớp chính xác theo policy.

### 18.3. OIDC user trong Spring

Sau login, Spring Security thường cung cấp `OidcUser`. Controller minh họa:

```java
@GetMapping("/me")
Map<String, String> currentUser(
        @AuthenticationPrincipal OidcUser user) {

    return Map.of(
        "issuer", user.getIssuer().toString(),
        "subject", user.getSubject(),
        "name", user.getFullName() != null
            ? user.getFullName()
            : user.getSubject());
}
```

Đây là output tối thiểu minh họa; không trả nguyên ID Token hoặc claims nhạy cảm ra response. `OidcUser.getFullName()` có thể null, nên có fallback.

### 18.4. Spring Security giúp nhưng không thay toàn bộ security review

Dù oauth2Login quản lý nhiều bước chuẩn, ứng dụng vẫn cần:

- Bảo vệ session cookie và CSRF của business endpoints.
- Quản lý token storage/retention.
- Cấu hình issuer và redirect URI chính xác.
- Hạn chế scopes và xử lý consent.
- Định nghĩa local user mapping theo issuer/subject.
- Kiểm tra tenant/authorization nghiệp vụ.
- Giám sát lỗi callback và token exchange.

## 19. OIDC Discovery và các kiểm tra issuer

OIDC Provider Configuration ở `/.well-known/openid-configuration` giúp RP nhận metadata như:

```json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "userinfo_endpoint": "https://auth.example.com/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"]
}
```

Đây chỉ là ví dụ rút gọn, **không phải response discovery đầy đủ** hay cam kết endpoint path của mọi OP. Với issuer và public key, dùng metadata OP thật và kiểm tra TLS/trust.

### 19.1. Vì sao issuer phải khớp chính xác?

RP cần so sánh claim `iss` của ID Token với issuer đã cấu hình. Không kiểm tra “host chứa auth.example.com” hoặc chấp nhận arbitrary issuer do token tự khai; điều đó có thể dẫn đến issuer confusion.

Trong multi-issuer ứng dụng phải có mapping từng client registration tới issuer/JWKS rõ ràng. Không dùng một JWK Set cho mọi issuer trừ khi đã có trust contract chặt chẽ.

### 19.2. Key rotation

OP cần công bố public signing keys qua JWKS. Khi rotation:

1. Thêm public key mới vào JWKS trước khi phát token ký bằng key mới.
2. Đảm bảo RP có thể cập nhật JWKS cache.
3. Bắt đầu ký ID Token mới bằng key mới.
4. Giữ public key cũ đủ lâu để ID Token còn hợp lệ được xác minh trong overlap.
5. Chỉ loại bỏ khóa cũ sau khi xem xét TTL, cache và rollback.

Không bỏ public key cũ ngay khi chuyển signer nếu RP vẫn còn ID Token hợp lệ cần xác minh.

## 20. Những hiểu lầm thường gặp về bộ token

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “OAuth code flow luôn trả ID Token” | Chỉ OIDC flow yêu cầu `openid` mới có ID Token theo chuẩn |
| “Authorization code là access token tạm” | Code là grant để đổi token, không phải credential API |
| “ID Token là JWT nên API có thể dùng nó” | ID Token dành cho RP; API nhận access token |
| “Access token luôn là JWT” | Có thể JWT hoặc opaque |
| “Refresh token được cấp trong mọi OIDC login” | Tùy client/grant/consent/security policy |
| “`offline_access` bảo đảm có refresh token” | Chỉ là yêu cầu; OP có thể từ chối/bỏ qua theo chuẩn |
| “ID Token có `email` thì email là định danh chính” | Nên nhận diện bằng `(iss, sub)` |
| “Login thành công nghĩa là có mọi scope” | API vẫn kiểm tra scope, audience và domain permission |
| “State và nonce là cùng một thứ” | State liên kết callback, nonce liên kết ID Token với request |
| “PKCE thay thế client secret cho confidential app” | PKCE và client authentication bảo vệ các bề mặt khác nhau |
| “ID Token luôn đi qua browser URL” | Trong Code Flow, ID Token được trả từ Token Endpoint |
| “ID Token `exp` chính là RP session TTL” | RP session có lifetime và policy riêng |
| “Chỉ decode JWT là đã validate” | Phải xác minh chữ ký, issuer, audience, time và nonce |
| “Spring bật OIDC mặc định cho AS” | Phải bật OIDC configurer khi dùng cấu hình AS tối thiểu |
| “Refresh token mới nghĩa token cũ chắc chắn bị revoke” | Phụ thuộc rotation/reuse policy và trạng thái server |

## 21. Các rủi ro bảo mật và biện pháp

### 21.1. Authorization code interception/replay

**Rủi ro:** attacker lấy code từ callback URL rồi đổi token.

**Bảo vệ:** PKCE S256, client authentication khi phù hợp, code TTL ngắn và single-use, redirect URI chính xác, không log code; từ chối code reuse.

### 21.2. Login CSRF và authorization response injection

**Rủi ro:** callback của một login transaction bị ghép vào session khác khiến user đăng nhập nhầm tài khoản.

**Bảo vệ:** state khó đoán, lưu đúng transaction, xác minh chính xác, không tái sử dụng state; nonce khi sử dụng, kiểm tra ID Token.

### 21.3. Open redirect và redirect URI manipulation

**Rủi ro:** client đăng ký hoặc xử lý redirect URI quá lỏng, attacker chuyển code tới domain do họ kiểm soát.

**Bảo vệ:** đăng ký redirect URI chính xác, hạn chế wildcard, không cho caller tự điều khiển `redirect_uri` hoặc `returnUrl` không được kiểm tra.

### 21.4. Token substitution và ID Token-as-access-token

**Rủi ro:** API chấp nhận ID Token vì cùng issuer/signing key, hoặc RP tin JWT không đúng audience.

**Bảo vệ:** RP validate ID Token audience là client ID; RS validate access token audience là API và token type/profile; không đổi vai trò token.

### 21.5. Client secret và refresh token leakage

**Rủi ro:** shared secret trong SPA, refresh token trong localStorage không có threat model, access token trong log.

**Bảo vệ:** BFF/server-side storage nếu phù hợp, secret manager, TLS, secure HttpOnly/SameSite cookies cho RP session, rotation, least privilege, redaction.

### 21.6. Discovery/JWKS trust confusion

**Rủi ro:** RP đọc issuer/JWKS URI từ token hoặc input tùy ý và tải khóa attacker.

**Bảo vệ:** cấu hình issuer tin cậy, xác minh discovery metadata, JWKS từ OP đã xác nhận; không cho JWT tự chọn key source qua URL.

### 21.7. XSS và session theft

OIDC Code Flow không vô hiệu hóa XSS, CSRF nghiệp vụ, session fixation hoặc cookie theft. Bảo vệ RP application bằng CSP phù hợp, output encoding, CSRF protection, cookie policy, session rotation sau login, rate limiting và monitoring.

## 22. Ma trận kiểm thử OIDC Authorization Code Flow

### 22.1. Test Authorization Request và callback

| Ca | Input/hành vi | Kết quả mong đợi |
|---|---|---|
| OIDC login hợp lệ | `scope=openid`, `response_type=code` | Nhận code, đổi thành ID/access token |
| Thiếu `openid` | OAuth-only request | Không coi response như OIDC login |
| Client ID không đăng ký | Client lạ | Authorization request bị từ chối |
| Redirect URI sai | Domain/path khác đăng ký | Bị từ chối |
| Scope không được cấp | Client yêu cầu ngoài policy | Từ chối hoặc giới hạn đúng chuẩn |
| State không khớp | Callback giả | RP từ chối |
| Thiếu state khi RP đã phát | Callback không liên kết | RP từ chối |
| Callback có error | `access_denied` hoặc lỗi login | Không đổi code |
| Code đã được dùng | Replay Token Request | Bị từ chối |
| Code hết hạn | Đổi code sau TTL | Bị từ chối |
| PKCE verifier sai | Challenge không khớp | Token Request bị từ chối |
| Dùng `plain` trái policy | PKCE downgrade | Bị từ chối |
| Client secret sai | Confidential client | Token Request bị từ chối |
| `nonce` đã phát nhưng ID Token thiếu/sai | Replay/substitution | RP từ chối ID Token |

### 22.2. Test Token Response và ID Token

| Ca | Kết quả mong đợi |
|---|---|
| Token Response Code Flow thiếu `id_token` | RP không coi là OIDC login thành công |
| ID Token sai chữ ký | RP từ chối |
| ID Token sai `iss` | RP từ chối |
| ID Token sai `aud` | RP từ chối |
| ID Token hết hạn | RP từ chối |
| ID Token có `iat` bất thường | Xử lý theo validation policy |
| `nonce` không khớp | RP từ chối |
| Có `max_age` nhưng thiếu/sai `auth_time` | RP từ chối theo yêu cầu OIDC |
| ID Token `sub=user-1`, UserInfo `sub=user-2` | RP không kết hợp claims |
| ID Token hợp lệ, access token sai audience API | RS từ chối |
| ID Token hợp lệ, access token thiếu scope | RS trả 403 |
| Không có refresh token | RP vẫn login được nếu ID/access hợp lệ |
| Refresh token được rotation | Test token cũ và mới theo policy |
| JWKS key rotation | RP xác minh token ký bằng key hợp lệ trong overlap |

### 22.3. Test với Spring Security

- Dùng `MockMvc`/HTTP integration test cho authorization endpoint, callback, token endpoint và SecurityFilterChain.
- Kiểm tra phiên chưa đăng nhập được redirect tới login đúng cách.
- Kiểm tra `oauth2Login` tạo OIDC principal từ ID Token hợp lệ.
- Kiểm tra callback sai state/nonce không tạo SecurityContext authenticated.
- Kiểm tra `RegisteredClient` enforce redirect URI và PKCE policy.
- Kiểm tra access token được gửi tới RS, không gửi ID Token.
- Kiểm tra OIDC scope và claims tối thiểu.
- Kiểm tra refresh token chỉ phát khi được phép.
- Kiểm tra consent persistence và scope thay đổi.
- Kiểm tra từng lỗi OAuth/OIDC không để lộ raw token/secret trong log.

Không chỉ unit test customizer bean rồi kết luận end-to-end flow đúng. Integration test phải đi qua các filter/provider thực tế.

## 23. Vận hành và observability

### 23.1. Metrics hữu ích

- Authorization request và callback success/failure theo client đã chuẩn hóa.
- Lỗi state mismatch, PKCE failure, redirect URI mismatch và code reuse.
- Token Endpoint latency, ID/access/refresh issuance errors.
- Login/consent latency, MFA prompt rate, user authentication failures.
- JWK signing/validation failures, `kid` unknown và key rotation rollout.
- `401` ở API do audience/expiry/type; `403` do scope.
- Refresh token rotation/reuse detection, revocation latency.
- Session login/logout events và số session tồn tại theo chính sách.

Không đưa code, access/ID/refresh token, nonce, state hoặc client secret vào metric labels hay logs.

### 23.2. Audit mẫu

Có thể ghi:

```text
OIDC_AUTHORIZATION_REQUEST_ACCEPTED
END_USER_AUTHENTICATED
OIDC_CONSENT_GRANTED
AUTHORIZATION_CODE_ISSUED
AUTHORIZATION_CODE_REDEEMED
OIDC_ID_TOKEN_ISSUED
ACCESS_TOKEN_ISSUED
REFRESH_TOKEN_ISSUED
OIDC_LOGIN_COMPLETED
OIDC_LOGIN_REJECTED
```

Audit nên có correlation ID, client ID, issuer, grant type, outcome, timestamp và user identifier đã pseudonymize nếu cần. Không ghi token raw hoặc code verifier.

### 23.3. Runbook khi login OIDC lỗi hàng loạt

1. Kiểm tra issuer trong discovery metadata và ID Token `iss`.
2. Kiểm tra authorization/token endpoint URL và TLS.
3. Kiểm tra redirect URI đăng ký có khớp RP callback.
4. Kiểm tra client authentication và secret/key rotation.
5. Kiểm tra state/nonce session storage, đặc biệt multi-instance RP.
6. Kiểm tra PKCE challenge/verifier bị mất do session/state store.
7. Kiểm tra signing key/JWKS, cache và `kid` mới.
8. Kiểm tra clock drift và ID Token `exp`/`iat`.
9. Kiểm tra OP user authentication/consent store.
10. Kiểm tra browser cookie SameSite/Secure, proxy forwarded headers và callback scheme.

Không sửa lỗi bằng cách tắt ID Token signature/audience/nonce validation hoặc cho redirect URI wildcard.

## 24. Checklist triển khai production

- [ ] OIDC Authorization Code Flow dùng `response_type=code` và scope chứa `openid`.
- [ ] RP lưu `state`, PKCE verifier và nonce (nếu dùng) theo từng login transaction.
- [ ] PKCE S256 được bật và code verifier được kiểm tra tại Token Endpoint.
- [ ] Redirect URI được đăng ký/chọn chính xác, không open redirect.
- [ ] OP xác thực End-User và xử lý consent đúng policy.
- [ ] Authorization code ngắn hạn, một lần, ràng buộc client/redirect/PKCE.
- [ ] Token Endpoint có client authentication đúng loại client.
- [ ] Token Response có ID Token và access token; refresh token chỉ khi đủ điều kiện.
- [ ] RP xác minh chữ ký, `iss`, `aud`, `exp`, `iat`, nonce/auth_time khi áp dụng.
- [ ] RP nhận diện user theo `(iss, sub)`; không coi email là subject mặc định.
- [ ] RS chỉ chấp nhận access token và kiểm tra audience/scope/expiry theo token profile.
- [ ] Không dùng ID Token làm bearer credential API.
- [ ] Refresh token được bảo vệ, giới hạn TTL và rotation/revocation theo policy.
- [ ] Spring Authorization Server đã bật OIDC configurer đúng phiên bản.
- [ ] OP có JWK source, issuer ổn định và key rotation plan.
- [ ] RP dùng `oauth2Login`/OIDC client implementation phù hợp và kiểm tra callback.
- [ ] RP session cookie được bảo vệ, không nhầm session TTL với ID Token TTL.
- [ ] UserInfo `sub` được so khớp ID Token `sub` nếu RP gọi endpoint.
- [ ] Có test state/nonce/PKCE/code replay, ID Token validation và access token audience.
- [ ] Có monitoring, audit và redaction cho mọi credential/token.

### Kiến thức cốt lõi

**OIDC Authorization Code Flow** sử dụng Authorization Code Grant của OAuth 2.0 để xác thực End-User và cấp token một cách tách bạch. Browser nhận **authorization code** qua redirect; RP đổi code tại Token Endpoint để nhận **ID Token + access token**, và **refresh token chỉ khi OP cho phép**.

**ID Token** là JWT chứa kết quả xác thực dành cho RP, cần được kiểm tra chữ ký, issuer, audience, thời hạn và nonce khi có. **Access token** dành cho Resource Server, được xác minh theo scope, audience và policy API; nó có thể là JWT hoặc opaque. **Refresh token** phục vụ xin token mới và có yêu cầu bảo vệ/rotation riêng. Authorization code, token và session cookie không thay thế vai trò của nhau.

Trong Spring Authorization Server, bật OIDC, đăng ký client đúng grant/scopes/redirect/PKCE, cấu hình issuer/JWKS và bảo vệ Token Endpoint. Ở Spring Security RP, dùng `oauth2Login` để xử lý Authorization Code Flow và OIDC ID Token validation. Hệ thống chỉ an toàn khi client, OP và RS thực thi cùng một hợp đồng giao thức rõ ràng.

## 25. Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Authorization Code Flow](https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowAuth)
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
- [OpenID Connect Core 1.0 — Offline Access](https://openid.net/specs/openid-connect-core-1_0.html#OfflineAccess)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [Spring Security — Authorization Server Configuration Model](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/configuration-model.html)
- [Spring Security — Authorization Server Getting Started](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/getting-started.html)
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — OAuth2 Authorization Code Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Authorization Server — Configuration Model (1.x)](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
