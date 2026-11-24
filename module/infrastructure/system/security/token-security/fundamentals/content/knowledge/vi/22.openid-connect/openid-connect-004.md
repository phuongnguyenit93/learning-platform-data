# UserInfo endpoint

Một ứng dụng web sử dụng **OpenID Connect (OIDC)** để đăng nhập người dùng. Sau khi **Authorization Code + PKCE** thành công, OIDC Client nhận một **ID token** để xác minh danh tính người dùng và một **access token** được Authorization Server/OpenID Provider (OP) cấp. Ứng dụng muốn hiển thị tên, ảnh đại diện và email của người dùng, nên gọi **UserInfo endpoint**.

Phần dễ nhầm là: *“Vì UserInfo trả về email và tên, chỉ cần gọi UserInfo rồi coi mọi trường là bằng chứng xác thực và phân quyền.”* Cách hiểu này thiếu an toàn. **UserInfo là một OAuth 2.0 Protected Resource**, nhận access token hợp lệ và trả về **claims về End-User** theo scope, quyền đã được cấp và chính sách của OP. Nó không tự thay thế **ID token validation**, không chứng minh người dùng vừa tương tác tại thời điểm API được gọi, không mặc định có mọi thuộc tính, và không chứng minh quyền đọc/sửa mọi tài nguyên nghiệp vụ.

Đặc biệt, theo **OpenID Connect Core 1.0**, OIDC Client **PHẢI kiểm `sub` trong UserInfo Response khớp chính xác `sub` trong ID token**; nếu khác nhau, **không được sử dụng** các giá trị UserInfo đó. Đây là ràng buộc thiết yếu để tránh ứng dụng gắn thông tin của **người dùng A** vào phiên đăng nhập của **người dùng B**.

Bài nằm trong chương **OpenID Connect** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là mô hình tin cậy giữa Client, OP và Resource Server, vòng đời ID/access/refresh token, JWT/opaque token, claims, scope, audience, lưu trữ an toàn, thu hồi token và phòng chống lộ hoặc phát lại bearer credential.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài học, bạn có thể:

1. Định nghĩa **UserInfo endpoint** và giải thích vì sao nó là một **OAuth 2.0 Protected Resource** trong kiến trúc OIDC.
2. Phân biệt vai trò của **ID token**, **access token**, **refresh token** và **UserInfo Response**.
3. Mô tả luồng Authorization Code + PKCE/OIDC: xác thực, đổi code, kiểm ID token, gọi UserInfo và gắn claims đúng người dùng.
4. Tìm endpoint qua **OIDC Discovery**, không tự tin URL do caller truyền vào.
5. Gửi HTTP GET hoặc POST với **Bearer access token**, xử lý thành công, token hết hạn và quyền thiếu.
6. Hiểu các **Standard Claims** như `sub`, `name`, `email`, `email_verified`, `picture`, `locale`, `address` và khi nào chúng có thể vắng mặt.
7. Thực hiện phép kiểm **UserInfo `sub` == ID token `sub`** và nhận diện nhầm issuer, token substitution, account confusion.
8. Phân tích `openid`, `profile`, `email`, `address`, `phone`, tham số `claims` và chính sách consent/minimization.
9. Phân biệt UserInfo Response dạng **JSON thường** với dạng **JWT đã ký/mã hóa** khi hai bên đăng ký đúng profile.
10. Áp dụng bảo mật endpoint phía OP và phía OIDC Client, có ví dụ HTTP, Java, bảng kiểm thử và checklist triển khai.

## 2. UserInfo endpoint là gì?

Theo **OpenID Connect Core 1.0, `5.3**, UserInfo endpoint là **OAuth 2.0 Protected Resource** trả về các **Claims về Authenticated End-User** khi nhận một access token được phát qua OpenID Connect Authentication.

Nói theo ngữ cảnh:

- **OpenID Provider (OP)** xác thực người dùng và cung cấp OIDC endpoints.
- **OIDC Client/Relying Party (RP)** nhận ID token để xác minh kết quả đăng nhập; nếu muốn thuộc tính hồ sơ, nó có thể gọi UserInfo.
- **UserInfo endpoint** là một Resource Server chuyên cung cấp claims về End-User theo token và chính sách.
- **Access token** là credential để gọi UserInfo, **không phải ID token** và không phải refresh token.
- **UserInfo Response** chứa các thuộc tính được cung cấp; `sub` là điểm liên kết với người dùng đã được xác thực trong ID token.

### 2.1. Các bên trong kiến trúc

| Vai trò/thành phần | Ví dụ | Trách nhiệm |
|---|---|---|
| **End-User / Resource Owner** | `user-742` | Người đăng nhập và có thể cho phép client truy cập hồ sơ theo chính sách. |
| **OIDC Client / Relying Party** | `shop-web` hoặc `shop-bff` | Xác minh ID token, gọi UserInfo bằng access token, sử dụng claims an toàn. |
| **OpenID Provider (OP)** | `https://login.example.com` | Xác thực user; là AS và công bố UserInfo endpoint. |
| **Authorization Endpoint** | `/authorize` | Luồng user authentication/authorization. |
| **Token Endpoint** | `/token` | Đổi authorization code, cấp ID/access/refresh token theo policy. |
| **UserInfo Endpoint** | `/userinfo` | Nhận access token, trả claims về user đúng grant/token. |
| **Ứng dụng nghiệp vụ/Resource Server khác** | `orders-api` | Kiểm access token dành cho API và quyền trên đơn hàng; **không được thay bằng việc đọc UserInfo**. |

**Một sản phẩm có thể gộp OP, Authorization Server và UserInfo endpoint trên cùng domain**, nhưng ranh giới giao thức vẫn khác nhau. UserInfo nhận bearer access token và trả claims; token endpoint mới đổi code/refresh; resource API kiểm quyền nghiệp vụ độc lập.

### 2.2. Những điều UserInfo không làm

- Không cấp một kết quả đăng nhập mới chỉ vì ai đó gửi được bearer token.
- Không đổi refresh token thành access token.
- Không trả mật khẩu, private key, client secret hay danh sách mọi quyền admin.
- Không bảo đảm client luôn nhận toàn bộ tên, email, địa chỉ, điện thoại.
- Không tự chứng minh email là khóa định danh ổn định hoặc một người sở hữu mọi tài nguyên.
- Không tự thay thế việc xác minh ID token, CSRF/PKCE/state trong login hoặc authorization tại API.
- Không có nghĩa một access token hợp lệ ở UserInfo cũng hợp lệ ở mọi Resource Server khác.

## 3. ID token, access token, refresh token và UserInfo: phân vai

| Thành phần | Ai sử dụng/kiểm | Mục đích | Không được sử dụng thay cho |
|---|---|---|---|
| **OIDC ID token** | **OIDC Client** | Kết quả xác thực về End-User, với issuer/subject/audience/time và claims theo OIDC. | Access token gọi UserInfo hoặc API. |
| **OAuth access token** | **UserInfo endpoint hoặc Resource Server đúng mục đích** | Credential truy cập một protected resource được phép. | Bằng chứng đăng nhập mới; quyền với mọi API. |
| **OAuth refresh token** | **Token endpoint của AS/OP** | Xin access token mới trong giới hạn grant/client/policy khi được cấp. | Token gửi UserInfo/RS. |
| **UserInfo Response** | **OIDC Client** | Các claims về End-User gắn với ID token, dùng hiển thị/đồng bộ profile theo policy. | ID token validation hoặc kiểm quyền trên bản ghi. |
| **BFF session cookie** | Browser ↔ BFF | Tra phiên ứng dụng phía server. | Access token OAuth tại UserInfo. |

### 3.1. So sánh hai đối tượng nhận bằng `aud`

ID token minh họa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "shop-web",
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

`aud=shop-web` vì ID token **dành cho OIDC Client**. Nó **không phải credential** để gọi UserInfo.

Access token JWT minh họa theo profile của OP:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "userinfo",
  "client_id": "shop-web",
  "scope": "openid profile email",
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

`aud=userinfo` trong ví dụ là **một lựa chọn cấu hình minh họa**, không phải audience bắt buộc của mọi OP. Một số OP phát opaque access token hoặc có profile audience khác; UserInfo endpoint phải xác minh token **được chấp nhận cho chính protected resource đó** theo thiết kế của OP.

**Không tự gắn `aud=orders-api` vào access token UserInfo** hoặc dùng ID token `aud=shop-web` làm token đọc profile chỉ vì có cùng `sub`.

### 3.2. UserInfo Response không nhất thiết có `aud`

Với response JSON thông thường:

~~~json
{
  "sub": "user-742",
  "name": "Nguyen Minh Anh",
  "picture": "https://images.example.com/avatar/user-742.png",
  "email": "minh.anh@example.net",
  "email_verified": true
}
~~~

Đây là **claims trả về trong HTTP response**, không phải bản thân access token hay ID token. JSON này có thể không có `iss`/`aud`; tính tin cậy được thiết lập qua **HTTPS, endpoint OP đã tin, access token được dùng, và phép so khớp `sub` với ID token đã xác minh**. Nếu dùng JWT UserInfo Response, các kiểm tra chữ ký/issuer/audience khác được áp dụng theo profile.

## 4. Luồng Authorization Code + PKCE và vị trí UserInfo

~~~mermaid
sequenceDiagram
    autonumber
    actor U as End-User
    participant B as Browser
    participant C as OIDC Client / BFF
    participant OP as OpenID Provider
    participant UI as UserInfo Endpoint
    participant API as Orders Resource Server

    U->>B: Chọn đăng nhập
    B->>C: GET /login
    C->>C: Tạo state, PKCE verifier, nonce nếu cần
    C-->>B: Redirect tới OP /authorize, scope=openid profile email
    B->>OP: Authorization request
    OP->>U: Xác thực và consent theo policy
    U-->>OP: Hoàn tất tương tác
    OP-->>B: Redirect về client kèm authorization code
    B->>C: Callback code + state
    C->>C: Kiểm state, issuer/transaction binding
    C->>OP: POST /token, code + PKCE + client auth nếu confidential
    OP-->>C: ID token + access token (+ refresh nếu được cấp)
    C->>C: Verify ID token theo OIDC
    C->>UI: GET /userinfo, Bearer access token
    UI-->>C: JSON/JWT claims, có sub
    C->>C: Assert UserInfo.sub == IDToken.sub
    C-->>B: Phiên ứng dụng và profile hiển thị phù hợp
    C->>API: Access token riêng cho Orders API nếu được cấp
    API->>API: Kiểm aud, scope và quyền trên đơn hàng
~~~

**UserInfo được gọi sau khi có access token phù hợp**, không phải là bước bắt buộc để chứng minh một lần đăng nhập trong mọi ứng dụng. OIDC Client có thể đủ thông tin từ ID token và không cần gọi UserInfo nếu không cần claims bổ sung.

### 4.1. Những gì phải xảy ra trước khi dùng UserInfo

1. Client bắt đầu authorization transaction với `state` và PKCE, dùng redirect URI/issuer đã cấu hình; OIDC `nonce` theo luồng và profile khi áp dụng.
2. OP xác thực người dùng và cấp authorization code trong phạm vi được phép.
3. Client kiểm `state`, issuer/redirect binding rồi đổi code tại token endpoint bằng `code_verifier`; confidential client xác thực theo method đã đăng ký.
4. Client xác minh **ID token** theo OIDC: chữ ký/thuật toán, `iss`, `aud`, thời hạn, `nonce` nếu áp dụng và các điều kiện khác của flow.
5. Client lấy **access token** từ token response phù hợp và gọi UserInfo theo endpoint OP đã tin.
6. Client xác minh UserInfo Response và **đối chiếu `sub` chính xác** với ID token đã xác minh.
7. Chỉ sau đó mới liên kết các profile claims với user/session đã đăng nhập.

### 4.2. Lỗi nếu UserInfo tự “đăng nhập” cho client

Nếu một ứng dụng nhận access token do browser tự cung cấp, gọi một URL có tên `userinfo` rồi dùng `email` trả về để tạo authenticated session mà **không xác minh issuer, token purpose, ID token và `sub` binding**, ứng dụng có thể gặp **login confusion/account linking**.

UserInfo là nguồn bổ sung claims trong **OIDC authentication context hợp lệ**, không phải bất kỳ API nào trả JSON tên người dùng.

## 5. Tìm UserInfo endpoint qua OIDC Discovery

OIDC Client nên biết rõ **issuer của OP mà nó tin** và các endpoint thuộc issuer đó. Với **OpenID Connect Discovery**, OP thường công bố metadata tại:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: login.example.com
Accept: application/json
~~~

Một document minh họa:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "userinfo_endpoint": "https://login.example.com/oidc/userinfo",
  "jwks_uri": "https://login.example.com/oauth2/jwks",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public", "pairwise"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email", "address", "phone"],
  "claims_supported": [
    "sub", "name", "preferred_username",
    "picture", "email", "email_verified", "locale", "updated_at"
  ]
}
~~~

**Đây là metadata minh họa, không phải mô tả một nhà cung cấp cụ thể.** Các thuộc tính `scopes_supported`/`claims_supported` có thể vắng mặt; việc liệt kê trong metadata không bảo đảm mọi claim sẽ được trả cho mọi user/client.

### 5.1. Xác minh metadata, không chỉ tìm chuỗi kết thúc bằng `/userinfo`

Client cần:

- Bắt đầu từ **issuer tin cậy** theo cấu hình/tenant registration, không từ URL tự khai trong request.
- Tải metadata qua HTTPS, kiểm TLS certificate và hostname.
- Xác minh trường `issuer` **khớp chính xác** issuer đã mong đợi theo quy tắc OIDC.
- Chỉ chấp nhận `userinfo_endpoint` đáng tin theo chính sách SSRF/egress của ứng dụng; không tự gửi access token tới hostname bất kỳ.
- Đồng bộ issuer và endpoint với authorization transaction, đặc biệt khi ứng dụng tích hợp nhiều OP.
- Tránh redirect tự động khi HTTP client gửi bearer token đến URL khác; không để header `Authorization` rơi sang origin không tin.
- Không suy ra `userinfo_endpoint = issuer + "/userinfo"` trong mọi provider.

### 5.2. Multi-OP và issuer mix-up

Giả sử một ứng dụng hỗ trợ `login-a.example.com` và `login-b.example.com`. Một ID token của OP A không được dùng để liên kết UserInfo response từ OP B, dù email giống nhau.

Ràng buộc session:

~~~text
login_transaction:
  expected_issuer = https://login-a.example.com
  client_id       = shop-web-a
  state_reference = ...
  id_token_sub    = user-742
  userinfo_uri    = trusted metadata from issuer A
~~~

**Không lấy UserInfo URL từ input browser hoặc nội dung ID token chưa xác minh**. Client chỉ gọi endpoint của OP đã xác minh trong chính authorization transaction đó.

## 6. HTTP request tới UserInfo: GET, POST và Bearer token

Theo OIDC Core, UserInfo endpoint **hỗ trợ HTTP GET và HTTP POST**. Client gửi access token theo cơ chế **OAuth 2.0 Bearer Token Usage (RFC 6750)**; thực hành an toàn phổ biến là **Authorization: Bearer** qua HTTPS.

### 6.1. HTTP GET được khuyến nghị khi cần lấy claims

~~~http
GET /oidc/userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_USERINFO_EXAMPLE
Accept: application/json
~~~

Một response JSON minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "sub": "user-742",
  "name": "Nguyen Minh Anh",
  "email": "minh.anh@example.net",
  "email_verified": true,
  "locale": "vi-VN"
}
~~~

Bearer token trong ví dụ là **chuỗi giả**. Không dùng giá trị thật trong tài liệu, log, URL hoặc screenshot. Response metadata/cache policy phải phù hợp chính sách privacy và tiêu chuẩn HTTP; client cần tránh cache nhầm giữa người dùng.

### 6.2. HTTP POST cũng hợp lệ

~~~http
POST /oidc/userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_USERINFO_EXAMPLE
Accept: application/json
Content-Length: 0
~~~

Không nên mặc định “UserInfo chỉ GET” nếu viết một OP chuẩn OIDC. Dù client chọn GET hay POST, **điều quyết định là bearer token hợp lệ và được phép cho UserInfo**, không phải method có vẻ giống đăng nhập.

### 6.3. Không đặt access token trong query string

**Tránh:**

~~~http
GET /oidc/userinfo?access_token=SECRET_REAL_TOKEN HTTP/1.1
Host: login.example.com
~~~

Token trong URL có thể bị rò qua access logs, tracing, browser history, referrer, proxy, analytics hoặc email. **RFC 6750** mô tả nhiều cách truyền bearer token, nhưng query parameter có nguy cơ lộ cao và không nên dùng khi đã có Authorization header.

Không gửi refresh token tới UserInfo. Nếu access token hết hạn, client phải xử lý qua **token endpoint** theo grant và policy, không dùng refresh token làm bearer thay thế.

### 6.4. Kết nối và nguồn token phải đúng ranh giới

- UserInfo **chỉ** qua TLS/HTTPS với endpoint đã tin, không tắt certificate/hostname validation.
- Access token dùng để gọi endpoint này phải là token từ **authorization transaction/authorized-client state phù hợp**, không lấy từ URL người dùng.
- Không chuyển tiếp ID token hoặc client assertion thay cho access token.
- Không tự thêm bearer token vào mọi HTTP request của một shared client nếu có khả năng gọi đến host khác.
- Xác định token lifetime và policy với provider; UserInfo có thể trả `401` khi access token hết hạn dù session browser còn tồn tại.

## 7. UserInfo Response: `sub` và các Standard Claims

Một UserInfo JSON response điển hình:

~~~json
{
  "sub": "user-742",
  "name": "Nguyen Minh Anh",
  "given_name": "Minh Anh",
  "family_name": "Nguyen",
  "preferred_username": "minhanh",
  "profile": "https://profiles.example.com/minhanh",
  "picture": "https://images.example.com/avatar/user-742.png",
  "website": "https://example.net",
  "email": "minh.anh@example.net",
  "email_verified": true,
  "gender": "female",
  "birthdate": "1996-04-17",
  "zoneinfo": "Asia/Ho_Chi_Minh",
  "locale": "vi-VN",
  "phone_number": "+84 9xx xxx xxx",
  "phone_number_verified": false,
  "address": {
    "formatted": "Ho Chi Minh City, Viet Nam",
    "country": "Viet Nam"
  },
  "updated_at": 1893452400
}
~~~

Đây là **bản minh họa tổng hợp nhiều claims** để học cách đọc. Hầu hết ứng dụng không nên yêu cầu mọi claim trong ví dụ, nhất là birthdate, phone và address, nếu không có mục đích được phép.

### 7.1. Các nhóm Standard Claims cần nhận diện

| Claim | Kiểu/ý nghĩa | Lưu ý sử dụng |
|---|---|---|
| `sub` | String, subject identifier do OP cấp. | **Bắt buộc** trong UserInfo response; phải khớp chính xác với ID token `sub`. |
| `name` | String, tên hiển thị đầy đủ. | Có thể thay đổi; không làm khóa định danh. |
| `given_name`, `family_name`, `middle_name` | String, các thành phần tên. | Có thể không phù hợp mọi văn hóa và có thể vắng mặt. |
| `nickname`, `preferred_username` | String, biệt danh/username ưu tiên. | Không mặc định duy nhất, ổn định hoặc đã được xác minh. |
| `profile`, `picture`, `website` | URL dạng string. | Là dữ liệu hồ sơ, không mặc định an toàn để fetch hoặc render HTML. |
| `email` | String, địa chỉ email. | Có thể thay đổi/tái sử dụng; không làm primary identity key. |
| `email_verified` | Boolean, trạng thái xác minh email theo OP. | Phụ thuộc tiêu chí OP, **không phải MFA, proof of ownership hiện tại hoặc authorization**. |
| `gender`, `birthdate` | String theo profile. | Dữ liệu cá nhân có thể nhạy cảm; chỉ yêu cầu khi thật cần. |
| `zoneinfo`, `locale` | String, múi giờ và ngôn ngữ ưu tiên. | Có thể dùng hiển thị; cần fallback và validation. |
| `phone_number` | String, số điện thoại. | Không dùng làm khóa tài khoản bất biến. |
| `phone_number_verified` | Boolean, trạng thái xác minh điện thoại. | Không suy ra user vừa sở hữu thiết bị hoặc đã MFA cho giao dịch này. |
| `address` | JSON object với các thành phần địa chỉ theo OIDC. | Có thể cần bảo vệ privacy và giới hạn retention. |
| `updated_at` | Number, timestamp của thông tin user theo OP. | Không phải `auth_time` hoặc `iat` của ID token. |

### 7.2. `sub` khác email, username và số điện thoại

Nếu `user-742` đổi email từ `old@example.net` sang `new@example.net`, `sub` theo cùng issuer/subject policy vẫn là định danh OIDC ổn định của user theo hợp đồng. Nếu ứng dụng dùng email làm khóa liên kết tài khoản, thay đổi/tái sử dụng email có thể tạo **account takeover/account confusion**.

Khóa liên kết được sử dụng phổ biến:

~~~text
external_identity_key = (trusted_issuer, verified_sub)
~~~

Đối với pairwise subject identifiers, `sub` có thể khác nhau giữa clients/sector identifiers; không tự ghép tài khoản khác ứng dụng chỉ vì tên/email khớp. Một hệ thống hỗ trợ nhiều issuer **không** chỉ lấy `sub` đơn lẻ làm global user ID.

### 7.3. Claims có thể vắng mặt hoặc là null

`profile`, `email`, `phone_number` và các field khác **không được mặc định luôn có**. OP có thể chỉ trả một tập con do:

- User không có thông tin đó.
- Client không yêu cầu scope/claims liên quan.
- User/admin không cấp quyền hoặc chính sách riêng tư từ chối.
- OP không hỗ trợ claim hoặc cung cấp theo nguồn dữ liệu khác.
- Dữ liệu chưa được xác minh, đã bị xóa, không đúng đối tượng nhận.

Client nên chấp nhận thiếu field, dùng fallback hiển thị an toàn và không tự suy diễn `email_verified=true` nếu claim vắng mặt.

### 7.4. Tên và URL hồ sơ là dữ liệu không đáng tin để render

Dù UserInfo đến từ OP đã tin, các giá trị `name`, `profile`, `picture` có thể chứa dữ liệu do user quản lý. Khi hiển thị trong HTML, phải **output encode**; nếu hiển thị ảnh/URL, cần chính sách an toàn cho URL và tải từ domain phù hợp, chống XSS/SSRF/HTML injection.

**Tin nguồn xác thực không đồng nghĩa mọi chuỗi dữ liệu từ nguồn đó an toàn cho mọi sink.**

## 8. Quy tắc bắt buộc: UserInfo `sub` phải khớp ID token `sub`

Đây là kiểm tra đặc biệt quan trọng được OIDC Core quy định cho client:

> Giá trị `sub` trong UserInfo Response **phải được xác minh là khớp chính xác** giá trị `sub` trong ID token. Nếu không khớp, **không được dùng** các giá trị của UserInfo Response.

### 8.1. Ví dụ hợp lệ

ID token đã xác minh:

~~~json
{
  "iss": "https://login.example.com",
  "aud": "shop-web",
  "sub": "user-742",
  "exp": 1893453000,
  "iat": 1893452400
}
~~~

UserInfo trả:

~~~json
{
  "sub": "user-742",
  "name": "Minh Anh",
  "email": "minh.anh@example.net"
}
~~~

Client có thể dùng profile claims theo ứng dụng sau khi đã kiểm endpoint/token/response, **vì `sub` khớp chính xác** với user đã được xác thực ở ID token.

### 8.2. Ví dụ không hợp lệ

ID token `sub=user-742`, UserInfo:

~~~json
{
  "sub": "admin-001",
  "name": "System Administrator",
  "email": "admin@example.net"
}
~~~

**Bắt buộc từ chối các UserInfo claims**. Không “sửa” bằng cách:

- Đổi session principal từ `user-742` sang `admin-001`.
- Giữ user ban đầu nhưng chấp nhận email/role của `admin-001`.
- So sánh chỉ phần email hoặc username thay cho `sub`.
- Coi hai subject bằng nhau vì khác chữ hoa/chữ thường hoặc vì normalize chuỗi tùy ý.
- Fallback qua UserInfo endpoint của issuer khác cho đến khi tìm được email khớp.

### 8.3. So khớp chính xác, không normalize

~~~text
ID Token sub:    "user-742"
UserInfo sub:    "user-742"        -> MATCH

ID Token sub:    "User-742"
UserInfo sub:    "user-742"        -> MISMATCH

ID Token sub:    "user-742"
UserInfo sub:    " user-742 "      -> MISMATCH

ID Token sub:    "user-742"
UserInfo sub:    "user-742-extra"  -> MISMATCH
~~~

Không cắt khoảng trắng, lowercase, bỏ dấu, so prefix/contains, hay map `sub` sang email để “cứu” response. Nếu OP thực sự lỗi, xử lý theo incident/trust policy, không làm lỏng subject binding trong client.

### 8.4. Tại sao kiểm `sub` khi đã có HTTPS?

HTTPS chứng minh kênh kết nối đến endpoint đã tin và bảo vệ response trên đường truyền. Nó **không tự chứng minh response thuộc đúng End-User** của session khi có khả năng:

- Access token của **user B** bị dùng nhầm trong phiên user A do token store/cache bug.
- Concurrent requests ghép sai authorized client/grant reference.
- Provider hoặc proxy cấu hình sai user context.
- Token response hoặc UserInfo data bị hoán đổi giữa tenants/clients.
- Client vô tình dùng UserInfo endpoint của một issuer khác.

Phép kiểm `sub` là rào chắn cuối tránh **subject confusion**. Nó bổ sung các kiểm tra issuer, audience, token validity và authorization transaction, chứ không thay chúng.

## 9. Không dùng UserInfo để thay authorization

Giả sử user có:

~~~text
ID token:
  iss = https://login.example.com
  sub = user-742
  aud = shop-web

UserInfo:
  sub = user-742
  email = minh.anh@example.net
  email_verified = true

Orders API request:
  GET /tenants/tenant-anpha/orders/99
~~~

UserInfo xác nhận thông tin profile gắn với user này theo OP. Nó **không** nói user-742 thuộc tenant Anpha, có scope `orders:read`, được xem order-99 hoặc được phê duyệt hoàn tiền.

Resource Server vẫn phải kiểm:

1. **Access token dành cho Orders API**, đúng issuer/audience, còn hiệu lực và token purpose.
2. `scope`/permissions do AS phát, theo hợp đồng RS.
3. Tenant membership và vai trò trong **tenant đích**.
4. Ownership, ACL hoặc object-level policy trên **order-99**.
5. Trạng thái nghiệp vụ, yêu cầu step-up/reauthentication cho thao tác nhạy cảm nếu cần.

### 9.1. `email_verified=true` không cấp quyền admin

Một email thuộc domain doanh nghiệp hoặc `email_verified=true` **không** tự cấp quyền truy cập vào dữ liệu của doanh nghiệp. Domain email có thể không phải membership/role và có thể thay đổi. Nếu hệ thống dùng domain làm một tín hiệu onboarding, vẫn phải có policy cấp quyền/tenant độc lập và các bước xác minh thích hợp.

### 9.2. UserInfo là claims API, không phải “admin API”

UserInfo tiêu chuẩn trả về claims theo quyền đã cấp cho client. Nó **không** được mặc định cho client:

- Đổi mật khẩu người dùng.
- Quản trị user/role/tenant.
- Đọc dữ liệu mọi tài khoản.
- Thực hiện hành động ở API khác chỉ vì `scope=openid`.
- Truy vấn thông tin về user tùy ý bằng `?sub=target_user`.

Các chức năng quản trị danh tính thường là **API riêng, quyền riêng, audience riêng và chính sách khác**. Không mở rộng UserInfo thành “tìm mọi user” dựa vào client ID và bearer token chung.

## 10. Scope, `claims` parameter và consent quyết định dữ liệu UserInfo

Trong OIDC, các scope phổ biến liên quan UserInfo gồm `openid`, `profile`, `email`, `address` và `phone`. **Scope được yêu cầu** không đồng nghĩa **mọi claim thuộc nhóm đó luôn được trả về**.

### 10.1. Authorization request minh họa

~~~http
GET /oauth2/authorize?response_type=code&
  client_id=shop-web&
  redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
  scope=openid%20profile%20email&
  state=TRANSACTION_STATE_EXAMPLE&
  code_challenge=S256_CHALLENGE_EXAMPLE&
  code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

Request được xuống dòng để dễ hiểu; khi chạy thực phải URL-encode hợp lệ thành một URL HTTPS. `openid` phân biệt yêu cầu **OIDC authentication** với một yêu cầu OAuth thuần. `profile` và `email` xin nhóm claims tương ứng khi OP cho phép. `state` và PKCE thuộc bảo vệ authorization flow, **không phải scopes cho UserInfo**.

**Không nên xin `address`/`phone`/`birthdate` nếu ứng dụng chỉ hiển thị tên và avatar**. Chọn phạm vi tối thiểu, xác định mục đích xử lý và retention trước khi xin thêm dữ liệu cá nhân.

### 10.2. Ý nghĩa của từng scope

| Scope | Nhóm thông tin thường liên quan | Điểm cần nhớ |
|---|---|---|
| `openid` | Kích hoạt OpenID Connect; yêu cầu ID token theo flow. | Không tự bảo đảm tên/email/phone được trả. |
| `profile` | `name`, `family_name`, `given_name`, `middle_name`, `nickname`, `preferred_username`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo`, `locale`, `updated_at`. | OP có thể chỉ trả một phần, tùy user và chính sách. |
| `email` | `email`, `email_verified`. | Không tự bảo đảm email có hoặc `email_verified=true`. |
| `address` | `address` object. | Thông tin cá nhân; cân nhắc nhu cầu chính đáng. |
| `phone` | `phone_number`, `phone_number_verified`. | Không dùng số điện thoại như user ID bất biến. |

Bảng cho biết **nhóm claims tiêu chuẩn** theo OIDC, không phải nghĩa vụ OP bắt buộc trả đủ. `scope` do AS cấp còn có thể bị thu hẹp; cần kiểm response token thực tế và policy.

### 10.3. OIDC `claims` parameter

Khi OP hỗ trợ, OIDC cho phép chỉ rõ claims muốn nhận trong **ID Token** hoặc **UserInfo Response**. Ví dụ cấu trúc JSON của `claims` request parameter:

~~~json
{
  "userinfo": {
    "given_name": null,
    "family_name": null,
    "email": {
      "essential": true
    }
  },
  "id_token": {
    "auth_time": {
      "essential": true
    }
  }
}
~~~

Client sẽ **URL-encode toàn bộ JSON** thành tham số `claims` ở authorization request theo OIDC; không gửi nguyên đối tượng này như header tới UserInfo endpoint. `essential` là yêu cầu mức độ thiết yếu trong việc xử lý claims theo OIDC, **không phải cách cưỡng ép OP tiết lộ dữ liệu trái consent/policy**.

Một claim có thể không có hoặc không được cấp dù client yêu cầu; ứng dụng phải xử lý lỗi/thiếu field theo hợp đồng OP. Không nâng quyền hay vô hiệu policy để “đáp ứng essential”.

### 10.4. Consent không đồng nghĩa mọi dữ liệu được phép dùng vô hạn

Người dùng có thể thấy màn hình cho phép một client đọc thông tin hồ sơ. Nhưng OP/AS vẫn phải kiểm:

- Client registration, grant và đối tượng nhận.
- Những scope/claims được chấp nhận và user/organizational policy.
- Consent hợp lệ khi cần, cùng khả năng rút quyền.
- Dữ liệu thực có thể chia sẻ và mức độ xác minh.
- Chính sách bảo vệ quyền riêng tư, thời hạn lưu trữ và mục đích sử dụng.

**Không dùng UserInfo để vượt quyền:** nếu một client chỉ được `openid profile`, không được “thử” truy vấn số điện thoại hoặc địa chỉ người khác bằng cách thêm `?sub=...` hay `?scope=phone` vào UserInfo request.

### 10.5. `offline_access` và refresh token là chuyện khác

OIDC `offline_access` có thể liên quan việc xin refresh token theo chính sách OP. Nó **không tự là một nhóm UserInfo claims** và không làm UserInfo cho phép client lấy dữ liệu của tất cả người dùng sau khi browser đóng.

Nếu được cấp refresh token, client có thể xin access token mới tại **token endpoint**, sau đó gọi UserInfo khi access token mới được phép. OP có thể đã thu hồi consent, scope hoặc quyền trong thời gian đó.

## 11. Phản hồi UserInfo dạng JSON, signed JWT hoặc encrypted JWT

Không phải mọi UserInfo response đều có cùng hình thức. OIDC Core cho phép **JSON response thường** hoặc response **JWT được ký và/hoặc mã hóa** theo registration và cấu hình của OP/Client.

### 11.1. Trường hợp phổ biến: JSON qua HTTPS

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "sub": "user-742",
  "name": "Nguyen Minh Anh",
  "email": "minh.anh@example.net"
}
~~~

Với JSON thường, client **không có chữ ký JWS riêng của response để kiểm**. Nguồn tin cậy đến từ **TLS endpoint đã được xác minh**, bearer token gửi tới đúng OP, và quan trọng nhất là **`sub` phải khớp ID token**. JSON được nhận từ một HTTP endpoint bất kỳ không đủ để xác thực user.

### 11.2. Signed UserInfo Response

Một client có thể đăng ký cơ chế **signed UserInfo Response** thông qua metadata/profile, ví dụ `userinfo_signed_response_alg` phù hợp. OP trả claims dưới dạng một **JWT có chữ ký**; client cần kiểm JWS và các điều kiện theo OIDC trước khi dùng claims.

Ví dụ payload để giải thích (không phải JWT đã ký):

~~~json
{
  "iss": "https://login.example.com",
  "aud": "shop-web",
  "sub": "user-742",
  "name": "Nguyen Minh Anh",
  "email": "minh.anh@example.net"
}
~~~

Các bước chính:

1. Chỉ chấp nhận signed response nếu **đã được thỏa thuận qua registration/profile**; không tin `alg` tùy ý.
2. Xác minh chữ ký bằng khóa OP được tin cậy và thuật toán đã đăng ký, không tự tải key từ URL bất kỳ trong JWT header.
3. Kiểm `iss`, `aud` và các claims cần thiết đúng quy tắc **UserInfo signed response**, không nhầm `aud` của response với audience của **access token**.
4. Nếu response/profile có thời hạn, kiểm thời gian đúng ngữ nghĩa.
5. **Vẫn phải so sánh `sub` với ID token `sub` chính xác**, ngay cả khi JWS signature hợp lệ.

**Một signed UserInfo JWT không tự là ID token.** Nó có mục đích khác và không được dùng để gọi API như access token.

### 11.3. Encrypted UserInfo Response

Nếu client/OP đăng ký encrypted response (ví dụ `userinfo_encrypted_response_alg` và `userinfo_encrypted_response_enc` theo profile), OP có thể mã hóa claims để chỉ client dự kiến có thể đọc. Ứng dụng cần:

- Có key thích hợp để giải mã và quản lý private key an toàn.
- Kiểm cấu hình thuật toán mã hóa/khóa được cho phép; từ chối format bất ngờ.
- Nếu response **vừa ký vừa mã hóa**, giải mã và xác minh chữ ký nội bộ theo thứ tự/hồ sơ phù hợp.
- Không xem “giải mã thành công” đồng nghĩa signature/issuer/subject đã được xác minh.
- So khớp `sub` với ID token trước khi dùng dữ liệu.

Với các response có chữ ký/mã hóa, HTTP `Content-Type` thường là `application/jwt` theo OIDC. Một JSON parser thuần không thể xử lý đúng JWT Compact Serialization, nên OIDC Client phải biết và áp dụng response mode đã được cấu hình.

### 11.4. Không chấp nhận thuật toán hoặc nguồn khóa tùy ý

JWT UserInfo Response vẫn có các nguy cơ của JWT thông thường: `alg=none`, algorithm/key confusion, `kid` giả, `jku`/`x5u` trỏ URL không tin, nested JWT xử lý sai và response bị dùng chéo mục đích.

**JWT signature hợp lệ từ issuer khác cũng không đủ.** Client phải gắn response vào **đúng OP, đúng client và đúng user của phiên**.

## 12. Kiểm tra bảo mật ở phía UserInfo endpoint của OP

UserInfo không chỉ là một controller trả JSON. Vì nó là protected resource, OP phải thực thi chính sách khi nhận **access token**.

### 12.1. Chuỗi kiểm tra tối thiểu

~~~mermaid
flowchart TD
    A[Client gọi UserInfo qua HTTPS] --> B{Có access token theo Bearer scheme?}
    B -- Không --> R[401 hoặc OAuth Bearer error phù hợp]
    B -- Có --> C{Token hợp lệ cho UserInfo?}
    C -- Không --> R
    C -- Có --> D{Issuer, client, audience/resource, expiry và trạng thái hợp lệ?}
    D -- Không --> R
    D -- Có --> E{Grant/scopes/consent cho phép claims nào?}
    E -- Không đủ --> F[Giới hạn claims hoặc lỗi policy phù hợp]
    E -- Đủ --> G[Tra hồ sơ của subject token]
    G --> H[Áp data minimization, privacy và response policy]
    H --> I[Trả JSON hoặc JWT theo registration, luôn có sub]
~~~

Luồng thực tế có thể chia các validation giữa Authorization Server, API gateway, token introspection và UserInfo application. **Không được bỏ một ranh giới bảo mật cần thiết chỉ vì endpoint nằm cùng máy với OP**.

### 12.2. Token validation

Với **JWT access token**, endpoint kiểm:

- Issuer và public signing key/trust source; chữ ký/thuật toán.
- Token purpose/profile là access token, không phải ID token hoặc refresh token.
- Audience/resource binding **theo hợp đồng UserInfo của OP**; không giả định mọi OP dùng `aud=userinfo`.
- `exp`, `nbf`, các ràng buộc thời gian và trạng thái/revocation nếu có.
- Client/grant/context và scopes được phép đọc claims.
- Sender proof/binding nếu token là DPoP/mTLS bound theo profile hỗ trợ.

Với **opaque access token**, endpoint lookup token hoặc introspection qua thành phần tin cậy, kiểm `active`/client/subject/scopes/expiry và policy. `active=true` không thay các kiểm resource/scope còn lại.

### 12.3. Xác định subject từ token, không từ input caller

**Sai:**

~~~text
GET /userinfo?sub=admin-001
Authorization: Bearer <TOKEN_OF_user-742>

server:
  return findUser(request.sub)
~~~

**Đúng theo nguyên tắc:**

~~~text
token = validateAccessToken(request)
subject = token.boundAuthenticatedEndUser
allowedClaims = policy.allowedClaims(token.client, token.scopes, token.grant)
return subjectProfile(subject).project(allowedClaims, include="sub")
~~~

Lấy End-User từ **token/grant được AS xác minh**, không từ `user_id`/`sub` query, custom header hoặc body. Một admin API đọc người dùng khác cần authentication/authorization contract **riêng**, không “nâng cấp” UserInfo.

### 12.4. Không trả mọi claim chỉ vì token có `openid`

Giới hạn claims theo scope/claims request/consent/policy. Tránh trả số điện thoại, ngày sinh, địa chỉ hoặc role/entitlement nội bộ không được yêu cầu. Các trường nhạy cảm nên có audit/retention tương ứng.

`scope=openid` liên quan OIDC authentication, **không phải wildcard “read all PII”**.

### 12.5. Chống rò rỉ qua cache, log và lỗi

- Hạn chế cache dữ liệu cá nhân giữa users/clients/tenants; không dùng một cache key chỉ gồm path `/userinfo`.
- Nếu cache tại edge, phải áp response header và cache key theo user/credential đúng mô hình; mặc định không cache công khai.
- Không log raw `Authorization: Bearer`, access token, ID token, UserInfo body nhạy cảm hoặc JWT profile đầy đủ.
- Dùng rate limiting, anomaly detection, TLS, timeouts và giới hạn response size.
- Không trả lỗi chi tiết “địa chỉ email của subject này” khi token sai.

### 12.6. Sender-constrained tokens không tự thay user consent

DPoP/mTLS có thể hạn chế việc một bản sao token bị dùng mà không có proof/khóa, nhưng vẫn phải kiểm **grant, subject, scope, privacy policy**. Việc client có khóa không tự cho nó quyền lấy UserInfo của mọi user.

## 13. Tích hợp phía Client: ví dụ Java 17 và Jackson

Ví dụ dưới đây minh họa một **BFF/server-side OIDC Client** đã:

- Xác minh **ID token trước đó** theo chuẩn OIDC.
- Có `verifiedIdTokenSub` từ ID token đã xác minh, không từ browser body.
- Có access token lấy từ authorized-client state hợp lệ.
- Được cấu hình **UserInfo URI tĩnh đáng tin** từ issuer metadata đã xác minh.
- Đang làm việc với **JSON UserInfo Response**, không phải signed/encrypted JWT mode.

### 13.1. Java HTTP client kiểm JSON và `sub`

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;

public final class OidcUserInfoClient {
    // Lấy URI từ issuer metadata đã kiểm, không từ request của browser.
    private static final URI TRUSTED_USERINFO_URI =
        URI.create("https://login.example.com/oidc/userinfo");

    private final HttpClient http = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

    private final ObjectMapper mapper = new ObjectMapper();

    public UserProfile fetch(
            String accessToken,
            String verifiedIdTokenSub
    ) throws IOException, InterruptedException {

        if (accessToken == null || accessToken.isBlank() ||
                verifiedIdTokenSub == null || verifiedIdTokenSub.isBlank()) {
            throw new SecurityException("missing_oidc_context");
        }

        HttpRequest request = HttpRequest.newBuilder(TRUSTED_USERINFO_URI)
            .GET()
            .timeout(Duration.ofSeconds(5))
            .header("Authorization", "Bearer " + accessToken)
            .header("Accept", "application/json")
            .build();

        HttpResponse<String> response = http.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        if (response.statusCode() != 200) {
            // Không log Authorization header, token hoặc response body.
            throw new SecurityException("userinfo_unavailable");
        }

        String contentType = response.headers()
            .firstValue("Content-Type")
            .orElse("")
            .toLowerCase(Locale.ROOT);

        if (!contentType.startsWith("application/json")) {
            throw new SecurityException("unexpected_userinfo_format");
        }

        JsonNode body = mapper.readTree(response.body());
        JsonNode subject = body.path("sub");

        // Điểm mấu chốt của OIDC: EXACT sub binding.
        if (!subject.isTextual() ||
                !subject.textValue().equals(verifiedIdTokenSub)) {
            throw new SecurityException("userinfo_subject_mismatch");
        }

        JsonNode emailVerified = body.path("email_verified");
        boolean verified = emailVerified.isBoolean()
            && emailVerified.booleanValue();

        String displayName = body.path("name").isTextual()
            ? body.path("name").textValue() : null;

        String email = body.path("email").isTextual()
            ? body.path("email").textValue() : null;

        return new UserProfile(
            verifiedIdTokenSub, displayName, email, verified
        );
    }

    public record UserProfile(
        String subject,
        String displayName,
        String email,
        boolean emailVerified
    ) {}
}
~~~

**Những giới hạn có chủ ý của ví dụ:**

1. `verifiedIdTokenSub` phải đến từ **ID token đã xác minh đầy đủ** và cùng login transaction. Hàm này **không** tự validate ID token hay issuer.
2. Chỉ xử lý `application/json`. Nếu provider đăng ký signed/encrypted UserInfo JWT, phải dùng validator/crypto phù hợp thay vì tự thêm một nhánh parser tùy tiện.
3. `BodyHandlers.ofString` chưa giới hạn kích thước response; production cần **response size cap**, content handling, circuit breaker và timeout/rate control.
4. HTTPS/trusted host được cố định trong ví dụ; production đọc metadata từ issuer đã tin và áp chống SSRF/redirect. Client được cấu hình **không tự follow redirects**.
5. Method không xử lý token refresh, OIDC login correlation, mTLS/DPoP proof hoặc cache; các phần đó thuộc authorized-client/session design.
6. Email/name là **dữ liệu profile**, không được dùng trực tiếp để gán quyền hoặc tự động liên kết tài khoản khác issuer.
7. Không log access token, response body, hoặc câu trả lời chứa PII trong audit error.

**Ưu tiên OIDC client library được bảo trì** thay vì tự viết security-critical parsing/validation bằng HTTP client. Code giúp người học nhận diện **đúng điểm kiểm `sub`** và ranh giới dữ liệu.

### 13.2. Giữ hai khóa: danh tính và thông tin hiển thị

Ứng dụng có thể lưu:

~~~text
principal_identity:
  issuer       = https://login.example.com
  subject      = user-742

display_profile:
  name         = Nguyen Minh Anh
  email        = minh.anh@example.net
  verified     = true
  last_synced  = 2026-11-23T00:00:00Z
~~~

Khi email đổi, không nên tạo account mới nếu `(iss, sub)` vẫn là cùng user. Khi UserInfo thiếu email, đừng xóa/đặt `email_verified=true` không có căn cứ; áp dụng quy tắc đồng bộ/profile riêng.

## 14. Spring Security OAuth2 Login / OIDC UserInfo

Trong ứng dụng Spring Security, có thể dùng **OAuth2 Login** với OIDC Provider và client registration tương ứng. Spring cung cấp các thành phần như **OidcUserService** và **OidcUser** để làm việc với ID token/UserInfo.

### 14.1. SecurityFilterChain minh họa

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đoạn code **không tự cấu hình OP**: ứng dụng còn cần client registration đúng issuer/client ID/secret nếu confidential, redirect URI, scopes và các dependency Spring OAuth2 Client. Không tắt CSRF chỉ vì BFF gửi JSON; browser session cookie có threat model CSRF riêng.

### 14.2. Đọc thông tin OIDC principal

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class ProfileController {

    @GetMapping("/profile")
    public Map<String, Object> profile(
            @AuthenticationPrincipal OidcUser oidcUser) {

        // ID token đã được xác minh trong OIDC login flow.
        String stableSubject = oidcUser.getIdToken().getSubject();

        // Chỉ hiển thị một tập thông tin tối thiểu.
        return Map.of(
            "subject", stableSubject,
            "displayName", oidcUser.getFullName() == null
                ? "" : oidcUser.getFullName()
        );
    }
}
~~~

**Điều cần xem xét khi dùng Spring:**

- Spring có thể lấy UserInfo theo token/scopes/registration/behavior của phiên bản cụ thể; không giả định mọi login luôn gọi UserInfo.
- `OidcUser` có thể tổng hợp claims từ ID token và UserInfo. Khi cần phân biệt nguồn và độ tin cậy của claim, truy cập `getIdToken()`/`getUserInfo()` và kiểm contract của thư viện.
- Framework OIDC cần xác minh ID token và **ràng buộc UserInfo `sub` với ID token**; nếu custom user service/mapper thay thế, không vô tình bỏ lớp kiểm này.
- Không expose `OidcUser.getIdToken().getTokenValue()`, access token hoặc refresh token cho browser.
- `getFullName()` chỉ là dữ liệu hiển thị; không dùng làm khóa tài khoản hoặc quyền.

### 14.3. Khi cần tùy chỉnh OidcUserService

Nếu ứng dụng cần bổ sung dữ liệu domain từ database, luồng phù hợp là:

~~~text
OIDC login verified
  -> verified ID token (iss, sub)
  -> UserInfo retrieved/validated if needed
  -> resolve local account by trusted (iss, sub)
  -> query local tenant membership/roles from authoritative store
  -> construct application principal/authorities under policy
~~~

**Không lấy `email_verified` hay `preferred_username` từ UserInfo rồi tự cấp role admin**. Mapping local user/tenant authorization phải có dữ liệu tin cậy và lifecycle riêng, không chỉ là phép nối email.

Nếu dùng custom OIDC user service, hãy kiểm API và hành vi theo Spring Security version thực tế, bao gồm token request, UserInfo sub validation và claims merging; đừng tự viết HTTP calls và bỏ qua OIDC validators mà framework đang cung cấp.

## 15. Cache, dữ liệu thay đổi và vòng đời UserInfo

Dữ liệu hồ sơ có thể thay đổi mà không cần người dùng đăng nhập lại, ví dụ đổi avatar, tên, email hoặc phone. Nhưng UserInfo không phải real-time stream, và **OP không cam kết một cơ chế đồng bộ tất cả dữ liệu cho mọi client**.

### 15.1. Có nên gọi UserInfo mỗi API request?

Thường **không**. Việc gọi UserInfo mỗi request để “xác thực lại user” có thể:

- Gây độ trễ và phụ thuộc sẵn sàng của OP.
- Tăng chi phí mạng/rate limit.
- Làm lan truyền dữ liệu cá nhân không cần thiết.
- Không tăng mức assurance của user (không có authentication event mới).
- Không thay thế authorization của API.

Ứng dụng có thể lấy profile ở login, refresh theo TTL đã chọn hoặc cập nhật khi người dùng sửa hồ sơ, tùy nhu cầu. Dùng **server-side cache theo đúng principal/issuer/client** và policy bảo mật thông tin.

### 15.2. Cache key phải phân biệt danh tính

**Sai:**

~~~text
cacheKey = "/userinfo"
cacheKey = email
cacheKey = sub only, across all issuers
~~~

**An toàn hơn theo kiến trúc:**

~~~text
cacheKey = (trusted_issuer, verified_sub, client_or_audience_context)
cacheTTL = policy-defined duration
cacheInvalidation = profile update / logout / consent change if applicable
~~~

`client_or_audience_context` trong cache key cần phù hợp thiết kế vì hai clients có thể được trả **những tập claims khác nhau** theo consent. Cùng `sub` không đảm bảo cùng quyền xem dữ liệu hoặc cùng pairwise subject context.

### 15.3. Cập nhật email không phải bằng chứng identity mới

Nếu UserInfo trả email khác lần trước, client phải xử lý cập nhật profile theo policy. Không tự merge sang tài khoản local khác chỉ vì email mới trùng một tài khoản đã có; liên kết tài khoản cần authentication/ownership checks riêng để tránh takeover.

### 15.4. Logout, revoke và token expiry

- **Logout BFF session**: hủy session phía ứng dụng; không tự bảo đảm mọi access token tại OP bị revoke.
- **Access token hết hạn**: UserInfo có thể trả `401 invalid_token`; client có thể refresh nếu grant/policy cho phép.
- **Refresh token bị revoke**: không xin được access token mới; cần reauthorization/reauthentication theo policy.
- **Consent bị rút**: OP có thể ngừng cấp claims hoặc token theo chính sách; cache của client phải có invalidation/TTL phù hợp.
- **Email/role đổi**: không suy ra JWT cũ tự cập nhật. Role/tenant authorization nên kiểm nguồn thẩm quyền của ứng dụng/RS.

**Không dùng UserInfo refresh như cơ chế đảm bảo session user luôn còn MFA hợp lệ**. Nếu cần MFA mới, xem xét OIDC `auth_time`, `acr`/`amr` và step-up/reauthentication theo policy.

## 16. Xử lý lỗi UserInfo và phân biệt với lỗi token endpoint

UserInfo là **protected resource**, do đó các phản hồi lỗi khi gọi UserInfo thường tuân theo cơ chế **OAuth 2.0 Bearer Token Usage (RFC 6750)**. Đừng nhầm chúng với `invalid_grant` hoặc `invalid_client` xuất hiện khi gọi token endpoint.

### 16.1. Access token hết hạn hoặc không hợp lệ

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="userinfo", error="invalid_token"
Cache-Control: no-store
~~~

Điều này có thể do access token hết hạn, đã revoke, sai issuer/resource, không hợp lệ hoặc không được OP chấp nhận. Client nên:

1. Kiểm rằng request đã gửi tới đúng **trusted UserInfo endpoint**.
2. Không log raw bearer token hoặc đưa token vào error message.
3. Nếu authorized-client grant cho phép, cân nhắc **refresh access token tại token endpoint**, không phải ở UserInfo.
4. Chỉ thử lại theo retry policy có giới hạn; nếu grant bị revoke, yêu cầu reauthorization/login khi phù hợp.
5. Không fallback sang gửi ID token, refresh token hoặc client secret làm bearer.

### 16.2. Access token không đủ quyền

Một phản hồi khi token còn hợp lệ nhưng thiếu quyền theo RFC 6750 có thể là:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="userinfo", error="insufficient_scope"
Cache-Control: no-store
~~~

**Không tự nâng scope bằng cách nối thêm vào HTTP UserInfo request**; quyền đến từ authorization/grant/consent tại OP. Nếu cần claims mới, bắt đầu authorization flow xin quyền theo quy định và policy. Nhiều OP chỉ trả subset claims thay vì lỗi `insufficient_scope`, nên client **không được mặc định mọi field luôn có**.

### 16.3. Bảng lỗi và phản ứng an toàn

| Sự kiện | Cách xử lý hợp lý | Điều không được làm |
|---|---|---|
| `401 invalid_token` | Kiểm grant/access token, refresh hoặc yêu cầu auth lại nếu policy cho phép. | Thay bằng ID token hoặc retry vô hạn. |
| `403 insufficient_scope` | Xin quyền hợp lệ qua authorization flow khi có nhu cầu thật. | Bỏ consent hoặc gọi admin API bằng token cũ. |
| TLS/hostname validation thất bại | Dừng request, điều tra cấu hình/issuer. | Tắt certificate validation. |
| UserInfo trả redirect HTTP 3xx | Chỉ xử lý theo trusted endpoint policy; tránh leak Authorization. | Tự động follow URL lạ cùng bearer token. |
| JSON sai định dạng/thiếu `sub` | Từ chối response. | Dùng email làm subject thay thế. |
| `sub` UserInfo khác ID token | Từ chối toàn bộ UserInfo claims, audit lỗi subject binding. | Đổi session user theo response. |
| `Content-Type` khác định dạng đã đăng ký | Dừng, xử lý theo response profile đã cấu hình. | Thử parse JWT bất kỳ hoặc bỏ signature verification. |
| HTTP `429`/rate limit | Backoff/circuit breaker theo chính sách. | Spam lại endpoint, làm lộ access token qua log. |
| HTTP `5xx`/timeout | Có thể retry có giới hạn với kiểm token lifetime/OP health. | Chấp nhận dữ liệu của user khác từ cache chung. |
| Claim `email` không có | Hiển thị fallback hoặc yêu cầu thông tin theo UX policy. | Đặt email giả rồi coi đã xác minh. |

### 16.4. Đừng dùng UserInfo để bắt buộc user đăng nhập lại mỗi request

UserInfo có thể không sẵn sàng khi OP gặp sự cố, dù session BFF và resource access token khác còn hợp lệ. Ứng dụng phải có **degradation policy** rõ: ví dụ cho hiển thị profile cache hợp lệ trong cửa sổ được phép nhưng không cấp quyền mới; với thao tác nhạy cảm, yêu cầu state/reauth khi policy đòi.

Không coi lỗi fetch avatar hoặc tên người dùng là lý do để âm thầm chuyển principal sang tài khoản khác.

## 17. Threat model: sai lầm phổ biến khi triển khai UserInfo

| Sai lầm/tấn công | Ví dụ | Hậu quả | Biện pháp |
|---|---|---|---|
| **Bỏ so khớp `sub`** | ID token A nhưng UserInfo B. | Gắn email/role của B vào session A. | So khớp chính xác `sub`, từ chối toàn response khi khác. |
| **Dùng email làm subject** | Đăng nhập bằng `email` thay `(iss,sub)`. | Account confusion/takeover khi email đổi/tái cấp. | Identity key theo issuer và verified subject. |
| **Nhầm ID token với access token** | Gửi ID token làm Bearer vào UserInfo. | Token confusion, dùng sai audience/purpose. | OP/RS kiểm token type và audience; client dùng access token. |
| **Sai OP/issuer** | Token/URL của OP A nhưng session OP B. | Trộn người dùng giữa nhà cung cấp. | Discovery/issuer binding, verified ID token, UserInfo URI đúng OP. |
| **Token store sai principal** | Cùng cache key cho hai sessions. | User A lấy UserInfo của B. | Authorized-client state theo grant/session; `sub` check. |
| **Bearer token trong query** | `/userinfo?access_token=...`. | Rò token qua logs/referrer/proxy. | `Authorization: Bearer` qua HTTPS. |
| **Không kiểm signature của signed response** | Parser đọc JWT UserInfo bất kỳ. | Attacker tạo claims giả. | Verify JWS bằng keys/alg/profile đã đăng ký. |
| **Nhầm JSON với JWT** | Phản hồi `application/jwt` được parse như JSON. | Bỏ validation hoặc lỗi đăng nhập. | Response mode/Content-Type đã đăng ký. |
| **Trust `jku`/`x5u` tùy ý** | JWT header trỏ public key attacker. | Key confusion/JWT forgery. | Chỉ dùng trusted issuer keys, algorithm allowlist. |
| **UserInfo làm authorization engine** | `email_verified=true` tự cấp admin. | Vượt quyền tenant/resource. | UserInfo cho profile; role/membership từ authoritative policy. |
| **Scope thừa** | Client xin `phone address` chỉ để hiển thị avatar. | Thu thập PII không cần thiết. | Data minimization và consent. |
| **Mọi claim được coi luôn có** | App crash khi thiếu `email`. | Lỗi login/UX và fallback không an toàn. | Nullable parsing, type validation, fallback. |
| **Dữ liệu từ profile gây XSS** | Render `name` như HTML. | XSS trong phiên người dùng. | Output encoding, CSP, URL validation. |
| **Ảnh/URL profile gây SSRF** | Backend tự tải URL `picture` tùy ý. | Truy cập tài nguyên nội bộ. | Safe URL proxy/allowlist, network egress policy. |
| **Cache profile chung** | CDN cache `/userinfo` không theo user/token. | Lộ PII giữa users/clients. | No public cache, user/client-scoped cache. |
| **HTTP client follow redirect với Bearer** | 302 sang host attacker. | Access token disclosure. | Trusted endpoint, no cross-origin auth forwarding. |
| **Tin `email_verified` là MFA** | Cho chuyển tiền vì email đã xác minh. | Bypass step-up authentication. | Kiểm `auth_time`/`acr`/`amr` và policy xác thực mới. |
| **Không phân biệt profile và permissions** | UserInfo có `role=admin` từ custom claim không kiểm. | Privilege escalation. | Trusted issuer/claim policy và authorization độc lập. |
| **Ghi UserInfo response vào log** | HTTP client debug ghi email, phone. | Lộ PII và liên kết danh tính. | Field-level allowlist/redaction, retention/RBAC. |
| **Không giới hạn response size** | OP/proxy bị compromise trả JSON cực lớn. | Memory exhaustion hoặc DoS. | Size cap, timeout, parser constraints, rate limits. |

### 17.1. Bearer token bị đánh cắp không chứng minh user hiện diện

Nếu attacker có access token còn hạn dùng cho UserInfo, attacker có thể thử đọc claims tương ứng tại OP. `sub` được trả đúng **không chứng minh user vừa đăng nhập trước request của attacker**; nó chỉ nói token được OP liên kết với subject nào.

Bảo vệ token bằng:

- Access-token TTL hợp lý, scope và audience tối thiểu.
- HTTPS, bảo vệ authorized-client store, tránh `localStorage` chứa token dài hạn không cần thiết trong browser.
- BFF với server-side tokens khi phù hợp, cookie `Secure`/`HttpOnly`/`SameSite` và CSRF/XSS defense.
- Sender-constrained token như **DPoP/mTLS** khi OP/client hỗ trợ đúng profile; UserInfo endpoint phải kiểm proof nếu có.
- Revocation/state checks và phát hiện bất thường khi token bị lộ.

**Token có chữ ký hợp lệ vẫn có thể bị phát lại nếu là bearer token và bị đánh cắp**. Chữ ký không chứng minh người gửi hiện tại sở hữu thiết bị gốc.

### 17.2. OIDC Client không được tin mọi URL trong profile

`picture`, `website` và `profile` là dữ liệu được trả về, **không phải endpoint tin cậy để gửi bearer token**. Tuyệt đối không gửi UserInfo access token đến `picture` URL để “lấy ảnh”. Nếu backend tải ảnh, có thể cần proxy chuyên dụng với SSRF defense, giới hạn kích thước/file type và không gửi Authorization headers.

### 17.3. Claims không mang quyền vĩnh viễn

Một custom claim `groups` hay `roles` nếu OP trả trong UserInfo có thể cũ, thiếu hoặc chỉ là thông tin hồ sơ. Nếu ứng dụng dùng làm authorization, phải có **hợp đồng claim được ký/xác minh, issuer chính xác, cách cập nhật/thu hồi, mapping tenant và kiểm dữ liệu hiện hành**. Không tự gán quyền bằng email/username hay một nhóm tùy ý trong JSON.

## 18. Nâng cao: Aggregated và Distributed Claims

OIDC Core định nghĩa cơ chế **Aggregated Claims** và **Distributed Claims** trong các profile hỗ trợ, cho phép claims đến từ một nguồn khác thay vì chỉ nằm trực tiếp trong UserInfo Response.

### 18.1. Ví dụ cấu trúc Aggregated Claims

Một response minh họa:

~~~json
{
  "sub": "user-742",
  "name": "Nguyen Minh Anh",
  "_claim_names": {
    "email": "src1"
  },
  "_claim_sources": {
    "src1": {
      "JWT": "SIGNED_AGGREGATED_CLAIMS_EXAMPLE"
    }
  }
}
~~~

`_claim_names` ánh xạ tên claim tới một source; `_claim_sources` cung cấp metadata của source. Đây **không phải một `email` string trực tiếp**. Client chỉ xử lý nếu hỗ trợ profile này và đã triển khai validation của nguồn/response JWT tương ứng.

### 18.2. Distributed Claims và nguy cơ SSRF/token leakage

Với distributed claims, một source có thể có endpoint để client truy vấn thêm. Nếu client tự lấy URL và gửi credentials từ UserInfo response hoặc browser đến **bất kỳ hostname nào**:

- Có nguy cơ **SSRF** đến mạng nội bộ, metadata services hoặc tài nguyên private.
- Có thể làm lộ access token được dùng cho nguồn claims.
- Có thể trộn claims từ issuer/source chưa được tin.
- Có thể chấp nhận `sub` hoặc attributes của người khác.

Cần áp **source trust policy**, TLS, URL allowlist/egress restrictions, scope/consent và xác minh response/binding đúng đặc tả. **Không tự động follow mọi `endpoint` hoặc gửi UserInfo bearer token đến URL thứ ba**.

### 18.3. Khi nào cần?

Đa số ứng dụng CRUD dùng OIDC login chỉ cần `sub` và một vài claims hồ sơ; không cần hỗ trợ aggregated/distributed claims. Chỉ triển khai khi OP/profile thực sự yêu cầu và có library/threat model đủ đáp ứng.

**Sự phức tạp tăng không đồng nghĩa xác thực mạnh hơn.** Điều quan trọng vẫn là verified ID token, subject binding và authorization tách biệt.

## 19. Tình huống thực tế: ứng dụng SaaS nhiều tenant

Một ứng dụng quản lý đơn hàng `shop-web` có người dùng `user-742`. User đã được xác thực tại OP và sử dụng ứng dụng ở tenant Beta.

~~~text
OP issuer:
  https://login.example.com

OIDC Client:
  shop-web

Verified ID token:
  iss = https://login.example.com
  aud = shop-web
  sub = user-742

UserInfo endpoint:
  https://login.example.com/oidc/userinfo

UserInfo Response:
  sub = user-742
  name = Minh Anh
  email = minh.anh@example.net
  email_verified = true

Local application authorization:
  tenant-beta: orders.viewer
  tenant-anpha: no membership

Orders API access token:
  aud = orders-api
  scope = orders:read
~~~

### 19.1. Vào trang hồ sơ

Client có thể hiển thị tên/email sau khi kiểm ID token và `sub` UserInfo khớp. Nếu email đổi nhưng `(iss,sub)` không đổi, đó vẫn là cùng OIDC identity theo hợp đồng; profile có thể được đồng bộ lại.

### 19.2. Vào đơn hàng Beta

Orders Resource Server kiểm access token, tenant Beta membership, scope và quyền với bản ghi. UserInfo **không phải chỗ cấp phép đọc đơn**.

### 19.3. Thay tenant trong URL

Nếu browser đổi `/tenants/beta/orders` thành `/tenants/anpha/orders`, UserInfo `email_verified=true` hay `sub=user-742` **không cho phép truy cập tenant Anpha**. API phải từ chối nếu policy không cấp membership.

### 19.4. Đăng nhập lại bằng OP khác nhưng cùng email

Nếu issuer B trả `sub=user-999`, email cũng là `minh.anh@example.net`, ứng dụng không được tự ghép hai OIDC identities làm một tài khoản. Cần **account linking flow riêng**, xác thực ownership và có audit.

### 19.5. OP thay chính sách cung cấp email

Nếu hôm nay UserInfo chỉ trả `sub` và `name`, ứng dụng không được fail-open bằng cách lấy email từ một phiên khác hoặc tự gắn `email_verified=true`. Tùy UX, có thể hiển thị hồ sơ thiếu email và yêu cầu người dùng cung cấp/xác minh theo ứng dụng.

## 20. Ma trận kiểm thử OIDC UserInfo

Các tests cần bao phủ **OIDC Client**, **UserInfo Resource Server** và **authorization backend**. Mỗi test nên dùng dữ liệu giả riêng, token mới đúng profile và **không reuse phiên/token từ case khác** làm sai kết quả.

### 20.1. Client validation tests

| Tình huống | Kết quả mong đợi |
|---|---|
| ID token hợp lệ, UserInfo JSON `sub` đúng | Client có thể sử dụng các claims được cấp. |
| UserInfo thiếu `sub` | Từ chối response, không thay bằng email. |
| UserInfo `sub` khác ID token `sub` | Từ chối **toàn bộ** UserInfo claims. |
| `sub` chỉ khác chữ hoa/chữ thường | Từ chối vì không khớp chính xác. |
| `sub` có khoảng trắng đầu/cuối khác nhau | Từ chối, không tự normalize. |
| ID token chưa verify signature/issuer/audience | Không dùng UserInfo làm bằng chứng đăng nhập thay thế. |
| ID token từ OP A, UserInfo từ OP B | Từ chối mix-up và không gửi token sang OP sai. |
| Token thuộc user B nhưng session user A | So khớp `sub` phát hiện và chặn gắn sai claims. |
| UserInfo email đổi, `sub` giữ nguyên | Giữ identity key, cập nhật profile theo policy. |
| Cùng email nhưng `(iss,sub)` khác | Không tự link tài khoản. |
| `email_verified` thiếu | Không mặc định là `true`. |
| `email_verified` là string `"true"` thay vì boolean | Xử lý dữ liệu sai kiểu theo schema, không coi là true. |
| Claim `name` hoặc `picture` chứa payload HTML/URL nguy hiểm | Output encode/URL policy chặn XSS/SSRF. |
| JSON quá lớn/độ sâu quá mức | Giới hạn size/parser, không làm cạn tài nguyên. |
| Response Content-Type khác JSON mode đã đăng ký | Từ chối hoặc xử lý theo JWT mode đúng cấu hình. |
| Signed UserInfo JWT sai chữ ký | Từ chối. |
| Signed JWT `iss`/`aud` không khớp | Từ chối. |
| Signed JWT có `alg=none` ngoài allowlist | Từ chối. |
| Encrypted JWT giải mã được nhưng signature không hợp lệ khi bắt buộc | Từ chối. |
| Signed UserInfo JWT đúng chữ ký nhưng `sub` khác ID token | Vẫn từ chối UserInfo claims. |
| UserInfo endpoint trả 302 sang attacker origin | Không chuyển bearer token sang host mới. |

### 20.2. UserInfo endpoint security tests

| Tình huống | Kết quả mong đợi |
|---|---|
| Không có access token | `401`/Bearer challenge theo policy. |
| Access token ngẫu nhiên/không hợp lệ | `invalid_token`, không trả claims. |
| Access token hết hạn/revoked | Từ chối theo state/expiry policy. |
| ID token được gửi như bearer | Từ chối sai token purpose/audience. |
| Refresh token được gửi làm bearer | Từ chối. |
| Access token dành cho `orders-api` | Từ chối ở UserInfo nếu không được phép theo OP resource policy. |
| Access token đúng UserInfo nhưng thiếu consent/scope cần thiết | Chỉ trả subset được phép hoặc lỗi policy phù hợp. |
| Access token user A + `?sub=user-B` | Không trả hồ sơ B. |
| Access token user A + `X-User-Id=user-B` | Không thay subject. |
| Bearer token của client B nhưng cache chung client A | Không rò claims giữa clients. |
| Claim ngoài scope, ví dụ phone khi chỉ có `openid` | Không tiết lộ dữ liệu không được phép. |
| Signed response đăng ký cho client A bị dùng ở client B | Không được chấp nhận nhầm audience/client. |
| Sender-bound token thiếu DPoP/mTLS proof khi yêu cầu | Từ chối. |
| CORS request từ origin không được phép | Không mở truy cập browser ngoài policy; CORS không thay bearer auth. |
| UserInfo GET và POST hợp lệ | OP xử lý cả hai method theo OIDC profile. |
| Request vượt rate limit | Throttling theo policy, không lộ token trong logs. |

### 20.3. Authorization/API tests

| Tình huống | Kết quả mong đợi |
|---|---|
| UserInfo trả `email_verified=true` nhưng user không có role admin | Không cấp role admin. |
| UserInfo đúng `sub` nhưng user không thuộc tenant Anpha | Orders API từ chối truy cập Anpha. |
| Scope `openid profile email`, không có `orders:read` | Không cho gọi Orders API chỉ nhờ UserInfo. |
| UserInfo `name` chứa chữ “administrator” | Không gán quyền theo text. |
| UserInfo được fetch thành công nhưng access token Orders hết hạn | Orders API kiểm token riêng và từ chối khi hết hạn. |
| OP session còn nhưng BFF session đã logout | BFF không nhận cookie cũ và không dùng cached profile để cho quyền. |
| User bị gỡ khỏi tenant sau login | RS kiểm policy/state theo cam kết, không tin cache UserInfo như quyền hiện tại. |

### 20.4. Pseudocode kiểm subject binding

~~~text
test "userinfo subject must exactly match verified ID token":
    verifiedIdToken = makeVerifiedIdToken(
        issuer = trustedIssuer,
        audience = registeredClientId,
        sub = "user-742"
    )

    goodResponse = fetchUserInfoWithMatchingAccessToken()
    assert goodResponse.sub == "user-742"
    assert client.acceptsUserInfo(goodResponse, verifiedIdToken)

    wrongResponse = {sub:"user-999", email:"admin@example.net"}
    assert client.rejectsEntireUserInfo(wrongResponse, verifiedIdToken)

    missingSubject = {email:"minh.anh@example.net"}
    assert client.rejectsEntireUserInfo(missingSubject, verifiedIdToken)

    caseChanged = {sub:"User-742"}
    assert client.rejectsEntireUserInfo(caseChanged, verifiedIdToken)

test "userinfo cannot authorize another tenant":
    idToken.sub = "user-742"
    userinfo.sub = "user-742"
    localMembership = {"tenant-beta":"viewer"}
    token.scope = "orders:read"

    assert GET("/tenants/tenant-anpha/orders/99") is denied
~~~

Đây là pseudocode. Trong integration tests thật, phải có token/JWS signatures và endpoint response hợp lệ theo test issuer, kiểm HTTP status/response headers, không chỉ mock một hàm parser bỏ qua các bước xác thực.

## 21. Bài thực hành và câu hỏi tình huống

### 21.1. Bài 1 — Ghép UserInfo với ID token

OIDC Client `shop-web` đã xác minh ID token:

~~~json
{
  "iss": "https://login.example.com",
  "aud": "shop-web",
  "sub": "user-742",
  "iat": 1893452400,
  "exp": 1893453000
}
~~~

Client lần lượt nhận các UserInfo Response:

~~~json
{"sub":"user-742","name":"Minh Anh","email":"minh.anh@example.net"}
~~~

~~~json
{"sub":"User-742","name":"Minh Anh"}
~~~

~~~json
{"name":"Minh Anh","email":"minh.anh@example.net"}
~~~

**Câu hỏi:** Response nào có thể được sử dụng nếu endpoint, token và response validation khác đều hợp lệ?

**Đáp án:** Chỉ response đầu tiên có `sub` khớp chính xác. Response thứ hai khác chữ hoa/chữ thường; response thứ ba thiếu `sub`. **Không dùng email, tên hoặc cách normalize tùy ý để thay subject binding**.

### 21.2. Bài 2 — `email_verified` có làm user thành admin?

Một UserInfo Response cho user:

~~~json
{
  "sub": "user-742",
  "email": "minh.anh@company.example",
  "email_verified": true
}
~~~

Ứng dụng thấy domain `company.example` rồi tự cấp `TENANT_ADMIN`.

**Đáp án:** Đây là lỗi authorization. `email_verified` phản ánh xác minh email theo OP; nó **không chứng minh user là tenant admin, không là MFA và không là một authorization grant**. Quyền phải được kiểm từ nguồn có thẩm quyền của tenant/resource.

### 21.3. Bài 3 — Chọn đúng token

~~~text
Token A: ID token JWT, aud=shop-web, sub=user-742
Token B: Access token được cấp cho UserInfo, có thể opaque
Token C: Refresh token nằm trong backend authorized-client store
~~~

**Câu hỏi và đáp án:**

1. **Gửi token nào tới UserInfo?** Token B, nếu hợp lệ cho UserInfo theo OP policy.
2. **Dùng token nào xin access token mới?** Token C tại **token endpoint** khi grant cho phép.
3. **Client dùng token nào để xác minh authentication?** ID token A, sau khi kiểm theo OIDC.
4. **Gửi token B đến Orders API được không?** Không tự động; cần access token đúng audience/scope của Orders API.
5. **Có thể dùng UserInfo response thay ID token không?** Không; UserInfo bổ sung profile claims và cần subject binding với ID token.

### 21.4. Bài 4 — Đúng `sub` nhưng response format sai

Client đã đăng ký yêu cầu **signed UserInfo JWT**. OP trả `application/json` không có JWS, nhưng `sub` vẫn đúng.

**Đáp án:** Không tự downgrade sang JSON unsigned khi security contract yêu cầu signed response. Phải kiểm response mode, chữ ký/issuer/audience và `sub` binding. Nếu provider thay đổi cấu hình, cần đánh giá và sửa registration theo quy trình chứ không bỏ qua validation để cho đăng nhập thành công.

### 21.5. Bài 5 — Cache dùng chung giữa hai user

~~~text
Session A:
  verified ID token sub=user-101
  authorized-client reference A

Session B:
  verified ID token sub=user-202
  authorized-client reference B

Bug:
  cacheKey = "shop-web"
  session A nhận UserInfo của user-202 từ cache.
~~~

**Đáp án:** Client bắt buộc từ chối UserInfo vì `sub` khác. Sửa token/cache repository để phân biệt issuer, subject, client và consent context; không chỉ đổi tên user hiển thị mà vẫn giữ email/claims của user B. Thêm concurrency tests cho các login sessions.

### 21.6. Bài 6 — Same user, wrong tenant

~~~text
ID token:
  sub=user-742
  aud=shop-web

UserInfo:
  sub=user-742
  email_verified=true

Local permissions:
  tenant-beta  = viewer
  tenant-anpha = no membership
~~~

**Câu hỏi:** UserInfo hợp lệ có cho phép truy cập `/tenants/tenant-anpha/orders/99` không?

**Đáp án:** Không. Orders API phải kiểm access token dành cho Orders, scope và membership/ownership/ACL tại tenant Anpha. UserInfo không thay Resource Server authorization.

### 21.7. Bài 7 — Thiết kế một BFF dùng OIDC

Ứng dụng chỉ cần hiển thị tên, avatar và email. Hãy lập bản thiết kế trả lời:

1. Scope tối thiểu nào nên xin, trong điều kiện OP hỗ trợ?
2. Có thể tìm UserInfo URL từ nguồn nào, cần kiểm issuer/HTTPS như thế nào?
3. Khi nào client kiểm ID token, và khi nào so sánh UserInfo `sub`?
4. Cache profile nên có key/TTL và invalidation nào?
5. Backend có cần fetch `picture` URL không, và có rủi ro SSRF nào?
6. Nếu OP không trả email, UI và dữ liệu tài khoản xử lý thế nào?
7. Khi token hết hạn nhưng BFF session vẫn active, ứng dụng phản ứng ra sao?
8. Những negative tests nào chứng minh token user B không bị gắn vào session A?

**Gợi ý:** Cân nhắc `openid profile email` khi cần thiết; Authorization Code + PKCE, metadata issuer tin cậy, OIDC ID token verification, exact subject binding, privacy-aware cache, xử lý thiếu claim, token refresh theo grant và authorization API độc lập.

## 22. Checklist triển khai UserInfo an toàn

- [ ] Nhận diện UserInfo là **OAuth 2.0 Protected Resource**, không phải một token endpoint hoặc nguồn tự xác thực user độc lập.
- [ ] OIDC Client có flow authentication hợp lệ (thường Authorization Code + PKCE), `state`/issuer binding và ID token validation.
- [ ] Phân biệt rõ **ID token**, access token dành cho UserInfo, refresh token và browser/BFF session.
- [ ] Không gửi ID token, refresh token, client assertion hoặc client secret làm bearer tới UserInfo.
- [ ] Lấy `userinfo_endpoint` từ metadata của **trusted issuer**, kiểm TLS/hostname và ngăn SSRF/redirect token leakage.
- [ ] Không tự suy ra path của mọi OP bằng cách nối `/userinfo`.
- [ ] Gửi access token qua **`Authorization: Bearer` và HTTPS**, không đưa vào query string.
- [ ] OP UserInfo hỗ trợ GET/POST theo OIDC và kiểm access token theo profile/issuer/resource/scopes.
- [ ] OP luôn liên kết hồ sơ với **subject của token/grant đã xác minh**, không với `?sub=...` do caller gửi.
- [ ] UserInfo response có `sub` và Client **so khớp chính xác** với `sub` trong ID token đã xác minh.
- [ ] Nếu `sub` thiếu hoặc khác nhau, client **từ chối toàn bộ UserInfo claims**.
- [ ] Không normalize `sub`, không thay bằng email, preferred_username hoặc phone.
- [ ] Identity key dùng trusted issuer và verified subject; account linking giữa issuers có flow riêng.
- [ ] Không mặc định claim `name`, `email`, `picture`, `phone_number` hay `email_verified` luôn có.
- [ ] Kiểm kiểu claim; thiếu `email_verified` không được suy thành `true`.
- [ ] Chỉ yêu cầu scope/claims tối thiểu; `openid` không trao quyền đọc mọi thông tin cá nhân.
- [ ] Có chính sách consent, rút quyền, retention và data minimization.
- [ ] Với signed/encrypted UserInfo JWT, xác minh response mode, chữ ký, issuer, audience, algorithms/keys và decrypt đúng profile.
- [ ] Không downgrade từ signed UserInfo response sang unsigned JSON khi hợp đồng đã yêu cầu ký.
- [ ] Không lấy UserInfo `email_verified` hoặc custom groups/roles làm quyền admin nếu chưa có authorization contract đáng tin.
- [ ] Resource Server nghiệp vụ vẫn kiểm `iss`, `aud`, `exp`, `scope`, token purpose và tenant/object-level policy riêng.
- [ ] Với browser/BFF, bảo vệ session bằng cookie phù hợp, CSRF/XSS prevention và server-side token storage.
- [ ] UserInfo client có timeout, response size cap, không follow redirect lạ với bearer và retry policy có giới hạn.
- [ ] Cache claims theo issuer, subject, client/claims context, TTL và invalidation phù hợp.
- [ ] Không ghi raw access token, ID token, UserInfo PII, Authorization headers hoặc JWT response vào telemetry.
- [ ] Nếu có aggregated/distributed claims, xác minh nguồn và chống SSRF/credential forwarding.
- [ ] Có tests thiếu `sub`, sai `sub`, nhầm issuer, sai token, thiếu claims, JWT không hợp lệ, cache mix-up và tenant authorization.
- [ ] Khi không đủ bằng chứng về subject/trust, hệ thống **fail closed** và không thay authenticated principal bằng dữ liệu UserInfo.

**Ghi nhớ:** **UserInfo endpoint** là một **OAuth 2.0 Protected Resource** trong OIDC, nơi Client dùng access token hợp lệ để lấy claims về End-User. **ID token xác minh authentication ở OIDC Client; UserInfo bổ sung profile claims; Resource Server nghiệp vụ quyết định quyền trên từng tài nguyên.** Phép kiểm bắt buộc là **UserInfo `sub` phải khớp chính xác ID token `sub`**. Đừng dùng email/profile làm bằng chứng quyền, đừng gửi bearer tới URL không tin và đừng bỏ kiểm authorization chỉ vì UserInfo trả `200 OK`.

## 23. Tài liệu chuẩn và nguồn tham khảo

- **OpenID Connect Core 1.0:** `3.1` Authorization Code Flow, `5.1` Standard Claims, `5.3` UserInfo Endpoint (request, response, subject binding), `5.4` scope/claims mapping, `5.5` claims request parameter và `5.6` Aggregated/Distributed Claims.
- **OpenID Connect Discovery 1.0:** `issuer`, `userinfo_endpoint`, `jwks_uri`, `scopes_supported` và claims/endpoint metadata.
- **OpenID Connect Dynamic Client Registration 1.0:** `userinfo_signed_response_alg`, `userinfo_encrypted_response_alg` và `userinfo_encrypted_response_enc`.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** OAuth roles, authorization code, access/refresh token, grants và scopes.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer Authorization header, `invalid_token`, `insufficient_scope` và bearer token handling.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** ràng buộc authorization code và code verifier/challenge.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp`, `iat`.
- **RFC 8725 — JSON Web Token Best Current Practices:** chống algorithm/key confusion, issuer/audience validation và token substitution.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access JWT và Resource Server validation, khác OIDC ID token/JWT UserInfo.
- **RFC 7662 — OAuth 2.0 Token Introspection:** opaque access token và `active` metadata.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token/grant tại Authorization Server.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource/audience targeting, hạn chế token được dùng ở đâu.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ OAuth authorization flows và token bị đánh cắp/phát lại.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer binding và chống mix-up.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained tokens.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS và certificate-bound access tokens.
- **OWASP OAuth 2.0 Cheat Sheet / Session Management Cheat Sheet:** bảo vệ login, browser session, CSRF/XSS và token storage.
- **OWASP API Security Top 10:** Broken Object Level Authorization và authorization độc lập với profile claims.
- **Spring Security Reference — OAuth2 Login/OpenID Connect:** `OidcUserService`, `OidcUser`, client registration và authority mapping.



