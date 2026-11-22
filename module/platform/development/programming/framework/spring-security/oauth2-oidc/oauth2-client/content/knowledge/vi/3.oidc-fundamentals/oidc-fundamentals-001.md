# 3.1. OpenID Connect bổ sung lớp xác thực cho OAuth 2.0

**OpenID Connect (OIDC)** là một giao thức định danh xây dựng trên OAuth 2.0. OAuth 2.0 giải quyết việc **ủy quyền truy cập tài nguyên**; OIDC bổ sung cách chuẩn hóa để một ứng dụng **xác thực người dùng đã đăng nhập là ai** thông qua một nhà cung cấp định danh.

Trong hệ sinh thái Spring Security, khác biệt này thể hiện rất rõ: `oauth2Login()` có thể dùng OIDC để đăng nhập người dùng bằng một `OidcUser`; `oauth2Client()` quản lý access token để ứng dụng gọi API; `oauth2ResourceServer()` xác minh access token mà API nhận được. Các vai trò liên quan nhau nhưng không thể thay thế nhau.

## 1. Vấn đề: OAuth 2.0 không tự định nghĩa một giao thức đăng nhập

Giả sử có một ứng dụng quản lý tài liệu muốn người dùng đăng nhập bằng tài khoản của một Identity Provider (IdP).

OAuth 2.0 có thể giúp ứng dụng lấy access token để gọi một API của IdP. Tuy nhiên, chỉ với thông tin “ứng dụng đã nhận được access token”, ứng dụng chưa có một cách chuẩn, thống nhất để kết luận:

- Người dùng cuối được xác thực là ai?
- Ai đưa ra khẳng định về danh tính đó?
- Khẳng định ấy được cấp cho **ứng dụng nào**?
- Người dùng đã đăng nhập khi nào và có yêu cầu xác thực lại không?
- Ứng dụng phải kiểm tra chứng cứ đăng nhập như thế nào?

**Access token** là một chứng chỉ truy cập tài nguyên, được cấp để sử dụng tại **Resource Server**. OAuth 2.0 không bắt buộc access token phải có định dạng JWT, không quy định một bộ claim về danh tính cuối cùng và không bảo đảm rằng client có thể giải mã nội dung token.

Nếu một ứng dụng tự lấy access token rồi suy ra “đã đăng nhập thành công” bằng các quy tắc riêng của từng nhà cung cấp, nó đang triển khai một giao thức đăng nhập tự chế. OIDC chuẩn hóa phần còn thiếu bằng cách định nghĩa **ID Token**, các scope/claim định danh, cách lấy thông tin người dùng và quy tắc kiểm tra token.

> **Phân biệt cốt lõi:** OAuth 2.0 trả lời “Ứng dụng được phép làm gì với tài nguyên?”. OIDC còn trả lời “Nhà cung cấp định danh đã xác thực chủ thể nào cho ứng dụng này?”.

OIDC vẫn dùng những thành phần và luồng ủy quyền của OAuth 2.0, nhưng bổ sung các ràng buộc về định danh. Một OAuth 2.0 Authorization Server **chưa chắc** là OpenID Provider; nó phải hỗ trợ các chức năng OIDC tương ứng.

## 2. Các vai trò trong mô hình OIDC

| Thành phần | Vai trò trong OIDC | Liên hệ với OAuth 2.0 |
|---|---|---|
| **End-User** | Người dùng được xác thực | Thường là Resource Owner trong tình huống đăng nhập, nhưng hai khái niệm không phải lúc nào cũng đồng nhất |
| **Relying Party (RP)** | Ứng dụng tin vào kết quả xác thực do OP đưa ra | Chính là một loại OAuth 2.0 Client |
| **OpenID Provider (OP)** | Xác thực người dùng, phát hành ID Token, có thể cung cấp UserInfo | Là Authorization Server có hỗ trợ OIDC |
| **Resource Server** | Cung cấp dữ liệu/API được bảo vệ bởi access token | Không cần là OP hoặc RP |

Trong một ứng dụng Spring Boot web:

```text
Trình duyệt / End-User
         |
         | mở trang cần đăng nhập
         v
Spring Boot Web App (Relying Party / OAuth2 Client)
         |
         | chuyển hướng đến OpenID Provider
         v
OpenID Provider (Authorization Server + dịch vụ định danh)
         |
         | xác thực người dùng, trả authorization code
         v
Spring Boot đổi code lấy token, kiểm tra ID Token
         |
         | thiết lập phiên ứng dụng
         v
Trình duyệt nhận session cookie
```

Spring Boot có thể tiếp tục dùng **access token** đã được cấp để gọi một Resource Server riêng. Cùng một OP có thể phát cả ID token và access token, nhưng **hai token có người nhận và chức năng khác nhau**.

## 3. OIDC bổ sung những gì lên nền OAuth 2.0?

### 3.1. Scope `openid` đánh dấu yêu cầu OIDC

Trong authorization request, ứng dụng yêu cầu scope `openid` để sử dụng OIDC:

```text
scope=openid profile email
```

Các scope có ý nghĩa khác nhau:

| Scope | Ý nghĩa |
|---|---|
| `openid` | Kích hoạt yêu cầu xác thực OIDC và nhận ID Token theo flow được hỗ trợ |
| `profile` | Xin truy cập các claim hồ sơ tiêu chuẩn, nếu OP cho phép |
| `email` | Xin các claim `email` và `email_verified`, nếu được cung cấp |
| `address` | Xin thông tin địa chỉ theo chuẩn OIDC |
| `phone` | Xin thông tin số điện thoại theo chuẩn OIDC |
| Scope API riêng, ví dụ `orders.read` | Xin quyền truy cập Resource Server; tên/ý nghĩa do hệ thống API xác định |

`openid` **không phải** một quyền nghiệp vụ để đọc hoặc sửa dữ liệu. `profile` và `email` cũng không bảo đảm mọi claim sẽ xuất hiện: kết quả phụ thuộc cấu hình OP, sự đồng ý và chính sách bảo vệ dữ liệu.

Không chỉ vì xuất hiện `openid` mà access token tự động trở thành ID token; ứng dụng phải xử lý đúng từng loại token.

### 3.2. ID Token: chứng cứ xác thực dành cho Relying Party

**ID Token** là một security token ở dạng JWT chứa các claim về sự kiện xác thực và chủ thể. OP thông thường ký JWT bằng khóa riêng để RP có thể kiểm tra tính toàn vẹn và nguồn phát hành.

Các claim quan trọng:

| Claim | Ý nghĩa | Ghi chú |
|---|---|---|
| `iss` | Issuer: định danh của OP phát hành ID token | Phải khớp issuer được RP tin cậy |
| `sub` | Subject: mã định danh người dùng tại OP | Kết hợp với `iss` để lập khóa định danh ổn định |
| `aud` | Audience: client ID của RP nhận ID token | RP phải nằm trong audience |
| `exp` | Thời điểm ID token hết hạn | RP từ chối token đã hết hạn |
| `iat` | Thời điểm token được phát hành | Dùng cho các kiểm tra thời gian theo giao thức |
| `nonce` | Giá trị ràng buộc với yêu cầu xác thực | Nếu RP đã gửi nonce, phải kiểm tra nó trong ID token |
| `auth_time` | Thời điểm người dùng thực sự được xác thực | Quan trọng khi RP yêu cầu `max_age` hoặc xác thực gần đây |
| `acr` | Mức/ngữ cảnh xác thực | Ý nghĩa chính xác tùy thỏa thuận với OP |
| `amr` | Phương thức xác thực đã áp dụng | Ví dụ mật khẩu, MFA; không mặc định tồn tại |
| `azp` | Authorized party | Cần kiểm tra theo quy tắc OIDC, đặc biệt khi có nhiều audience |

Một **JWT payload minh họa** (chưa phải token có thể sử dụng thực tế):

```json
{
  "iss": "https://login.example.org",
  "sub": "user-8c6e4d",
  "aud": "document-web-client",
  "exp": 1924999999,
  "iat": 1924996399,
  "auth_time": 1924996200,
  "nonce": "n-0S6_WzA2Mj"
}
```

Ba phần thường thấy của JWT ký JWS là `header.payload.signature`. Dữ liệu JSON trong payload thường chỉ được **mã hóa Base64URL, không được mã hóa bí mật**. Không đưa mật khẩu, secret hoặc dữ liệu nhạy cảm không cần thiết vào token chỉ vì nó được ký. Nếu OP/RP yêu cầu ID token mã hóa (JWE), đây là khả năng riêng phải được hai phía hỗ trợ và cấu hình.

Từ ví dụ có thể suy ra: OP `https://login.example.org` tuyên bố đã xác thực subject `user-8c6e4d`, và kết quả ấy dành cho RP có client ID `document-web-client`. Ứng dụng **chỉ được tin kết luận này sau khi thực hiện đầy đủ kiểm tra ID token**, không phải sau khi Base64URL decode.

### 3.3. UserInfo Endpoint: lấy claim về người dùng

OIDC định nghĩa **UserInfo Endpoint** để RP nhận các claim được cho phép về End-User. RP gửi **access token** trong `Authorization: Bearer ...` đến UserInfo Endpoint, thường qua HTTPS:

```http
GET /userinfo HTTP/1.1
Host: login.example.org
Authorization: Bearer <access-token>
```

Phản hồi minh họa:

```json
{
  "sub": "user-8c6e4d",
  "name": "Nguyen An",
  "email": "an@example.org",
  "email_verified": true,
  "picture": "https://images.example.org/avatars/8c6e4d.png"
}
```

**Quan trọng:** `sub` trong kết quả UserInfo **phải trùng** `sub` của ID token mà RP đã xác minh. RP không được nhập nhầm thông tin người dùng khác nếu hai subject không khớp.

Không phải mọi RP đều bắt buộc gọi UserInfo. ID token có thể chứa đủ claim để ứng dụng tạo phiên, hoặc OP có thể cấp thêm claim qua UserInfo theo scope/chính sách. Các claim như `email`, `picture` hay `name` có thể thiếu hoặc thay đổi qua thời gian; chúng không phải định danh tài khoản bất biến.

### 3.4. Discovery và khóa ký công khai

OIDC Discovery cho phép client tìm metadata từ issuer, ví dụ:

```text
GET https://login.example.org/.well-known/openid-configuration
```

Metadata minh họa:

```json
{
  "issuer": "https://login.example.org",
  "authorization_endpoint": "https://login.example.org/oauth2/authorize",
  "token_endpoint": "https://login.example.org/oauth2/token",
  "userinfo_endpoint": "https://login.example.org/userinfo",
  "jwks_uri": "https://login.example.org/.well-known/jwks.json",
  "response_types_supported": ["code"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

RP dùng `jwks_uri` để nhận JSON Web Key Set (JWKS), lựa chọn khóa công khai phù hợp và xác minh chữ ký ID token. Khi OP xoay vòng khóa, thư viện OIDC có thể tải lại JWKS theo cấu hình. **Ứng dụng phải cấu hình issuer tin cậy trước**, sau đó xác minh `issuer` trong metadata và ID token; không lấy URL issuer bất kỳ từ token chưa xác minh để tự động tin cậy.

OIDC Discovery giúp giảm việc cấu hình thủ công URL của từng endpoint và hỗ trợ quản lý khóa tốt hơn. Nếu nhà cung cấp không có metadata discovery, các endpoint và khóa phải được cấu hình theo cách tương thích mà ứng dụng có thể kiểm chứng.

## 4. Luồng đăng nhập OIDC Authorization Code + PKCE

Trong ứng dụng mới, cách phổ biến là **OIDC Authorization Code Flow**, kết hợp **PKCE** để hạn chế nguy cơ một authorization code bị lấy trộm rồi đổi thành token.

### 4.1. Sơ đồ trình tự

```mermaid
sequenceDiagram
    autonumber
    participant U as Trình duyệt / Người dùng
    participant RP as Spring Boot RP
    participant OP as OpenID Provider
    participant API as Resource Server

    U->>RP: GET /account
    RP-->>U: Redirect đến authorization endpoint
    U->>OP: /authorize?scope=openid...&state=...&nonce=...&code_challenge=...
    OP->>U: Xác thực người dùng, xin đồng ý nếu cần
    OP-->>U: Redirect callback?code=...&state=...
    U->>RP: GET /login/oauth2/code/company?code=...&state=...
    RP->>RP: Kiểm tra state từ yêu cầu ban đầu
    RP->>OP: POST /token (code + code_verifier + xác thực client nếu có)
    OP-->>RP: ID token + access token (+ refresh token nếu được cấp)
    RP->>RP: Kiểm tra ID token: issuer, signature, audience, time, nonce...
    opt Cần claim bổ sung
        RP->>OP: GET /userinfo (Bearer access token)
        OP-->>RP: Claims, bao gồm sub khớp ID token
    end
    RP-->>U: Tạo phiên đăng nhập; gửi session cookie
    U->>RP: GET /account (session cookie)
    opt Gọi API thay mặt người dùng
        RP->>API: Bearer access token
        API-->>RP: Dữ liệu đã được API cho phép
    end
    RP-->>U: Trang tài khoản
```

### 4.2. Những bước quan trọng

1. **RP khởi tạo yêu cầu:** tạo `state` ngẫu nhiên; có thể tạo `nonce`; khi dùng PKCE thì tạo `code_verifier` và dẫn xuất `code_challenge` bằng `S256`. Những giá trị cần thiết được liên kết với phiên/yêu cầu đang chờ.
2. **Chuyển hướng đến OP:** gửi `client_id`, `redirect_uri`, `response_type=code`, `scope=openid ...`, `state`, `nonce` (nếu sử dụng) và `code_challenge`.
3. **OP xác thực:** OP quyết định cách xác thực người dùng (mật khẩu, MFA, passkey, liên kết IdP khác…), xử lý consent và redirect đến URI đã đăng ký.
4. **RP nhận code:** kiểm tra `state`; không dùng code nếu callback không tương ứng với một yêu cầu đang chờ hợp lệ.
5. **Đổi code lấy token:** gửi `code_verifier` cùng code đến token endpoint; confidential client còn xác thực bằng credential đã đăng ký. Authorization Server kiểm tra PKCE, client và redirect URI.
6. **Xác minh kết quả OIDC:** RP xác minh ID token, đối chiếu nonce nếu có, có thể lấy UserInfo rồi xác minh `sub`.
7. **Tạo phiên ứng dụng:** RP ánh xạ `(iss, sub)` vào tài khoản nội bộ và quyết định chính sách truy cập tại ứng dụng.

Một authorization request minh họa (các giá trị `state`, `nonce` và challenge chỉ là placeholder):

```http
GET /oauth2/authorize?response_type=code
    &client_id=document-web-client
    &redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany
    &scope=openid%20profile%20email
    &state=<cryptographically-random-state>
    &nonce=<cryptographically-random-nonce>
    &code_challenge=<base64url-sha256-verifier>
    &code_challenge_method=S256 HTTP/1.1
Host: login.example.org
```

Token endpoint có thể trả về phản hồi có cấu trúc như sau (token là ký hiệu minh họa, không có giá trị sử dụng):

```json
{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "id_token": "<signed-oidc-id-token>",
  "scope": "openid profile email"
}
```

**Refresh token** có thể được cấp theo chính sách OP, loại ứng dụng, scope và consent; OIDC không bảo đảm mọi lần đăng nhập đều nhận refresh token. Thời hạn truy cập API, thời hạn ID token và thời hạn session web cũng **không bắt buộc bằng nhau**.

### 4.3. State, nonce và PKCE giải quyết các rủi ro khác nhau

| Thành phần | Điều được ràng buộc hoặc kiểm tra | Vai trò thực tế |
|---|---|---|
| `state` | Kết quả redirect thuộc đúng yêu cầu RP đã khởi tạo | Chống login CSRF/nhầm callback và liên kết phản hồi |
| `nonce` | ID token gắn với yêu cầu xác thực ban đầu | Giúp phát hiện replay hoặc nhầm ID token; kiểm tra khi đã gửi |
| `code_verifier` / PKCE | Người đổi authorization code nắm verifier từ yêu cầu ban đầu | Giảm rủi ro bị đổi code bởi tác nhân đã chặn lấy code |
| Client authentication | Client chứng minh credential đã đăng ký, nếu là confidential client | Bảo vệ token endpoint trước hành vi giả danh client |
| ID token validation | OP, chữ ký, người nhận, thời hạn và các điều kiện xác thực | Xác minh khẳng định đăng nhập trước khi tạo phiên |

**Không thay thế lẫn nhau:** có PKCE không có nghĩa được bỏ qua việc xác minh ID token; có client secret không khiến `state` trở nên vô ích; có `nonce` không thay thế kiểm tra audience hoặc chữ ký.

## 5. Ba loại token thường xuất hiện và ý nghĩa của chúng

| Token | Người nhận/chức năng chính | Cách sử dụng hợp lệ | Điều cần tránh |
|---|---|---|---|
| **ID Token** | RP; chứng minh sự kiện xác thực End-User | RP xác minh và lấy subject, thông tin xác thực | Gửi làm bearer token tới API |
| **Access Token** | Resource Server/API hoặc UserInfo | Gắn vào `Authorization: Bearer ...` để truy cập tài nguyên được cấp quyền | Dùng làm chứng cứ đăng nhập vào RP nếu không có giao thức xác thực phù hợp |
| **Refresh Token** | OAuth client; xin access token mới khi được cho phép | Giữ ở nơi bảo vệ, dùng tại token endpoint | Đưa vào URL, log hoặc lưu giữ không kiểm soát |

Một ID token là JWT, nhưng **không phải JWT nào cũng là ID token**. Access token có thể là JWT hoặc opaque token; nếu access token là JWT, claim `aud` thường chỉ API mục tiêu, còn `aud` của ID token phải bao gồm **OAuth client ID của RP**.

Ví dụ: nếu token có `aud=orders-api` và được gửi tới `https://api.example.org`, Spring API phải xem nó là access token dành cho API. Đừng nhận token đó như bằng chứng đăng nhập tương đương ID token có `aud=document-web-client`.

Tương tự, **xác thực thành công** không đồng nghĩa **được phép truy cập mọi tài nguyên**. Sau khi tin cậy ID token, RP vẫn phải xác định người dùng có tài khoản hợp lệ, thuộc tổ chức đúng, có vai trò/permission cần thiết và có được phép truy cập tài nguyên cụ thể hay không.

## 6. Xác minh ID Token đúng cách

RP không thể chỉ giải mã JWT rồi tin `email` hoặc `sub`. Việc xác minh bao gồm nhiều lớp, thường được thực hiện bởi thư viện OIDC được duy trì tốt:

1. **Issuer đáng tin cậy:** `iss` trong token phải bằng issuer OP đã cấu hình; metadata discovery phải nhất quán với issuer.
2. **Chữ ký và thuật toán:** xác minh chữ ký bằng khóa phù hợp từ JWKS của OP, với thuật toán được phép theo client registration/chính sách; không chấp nhận thuật toán hoặc khóa không đáng tin cậy chỉ vì token tự khai báo.
3. **Audience:** `aud` phải chứa `client_id` của RP. Nếu `aud` có nhiều phần tử, kiểm tra `azp` theo yêu cầu của OIDC; nếu `azp` hiện diện, kiểm tra nó tương ứng với client đang nhận token.
4. **Thời gian:** từ chối token hết hạn qua `exp`, xem xét `iat`, chênh lệch đồng hồ cho phép và `auth_time` khi có yêu cầu xác thực gần đây.
5. **Nonce:** nếu yêu cầu xác thực gửi `nonce`, phải so khớp giá trị trong ID token với nonce đã liên kết cùng yêu cầu.
6. **Điều kiện theo flow:** kiểm tra các hash claim như `at_hash`/`c_hash` khi giao thức/flow và các tham số yêu cầu; không áp đặt máy móc quy tắc của hybrid flow cho code flow đơn thuần.
7. **UserInfo subject:** nếu gọi UserInfo, `sub` trong phản hồi phải đúng bằng `sub` trong ID token đã xác minh.
8. **Ngữ cảnh ứng dụng:** ánh xạ `(iss, sub)` đến tài khoản; kiểm tra trạng thái hoạt động, tenant, vai trò và chính sách truy cập.

Thư viện Spring Security thường xử lý các phép kiểm tra OIDC cốt lõi của luồng đăng nhập khi được cấu hình đúng issuer/registration. Tuy nhiên, **quy tắc nghiệp vụ** như chỉ cho phép email thuộc doanh nghiệp, yêu cầu MFA với hành động nhạy cảm, hoặc chỉ cho phép tài khoản đã được duyệt thuộc trách nhiệm ứng dụng.

### 6.1. Vì sao `sub` quan trọng hơn `email`?

OIDC định nghĩa `sub` là subject identifier của người dùng tại một issuer. Email và tên hiển thị có thể đổi, trùng hoặc chưa được xác minh.

Một khóa tài khoản liên kết nên dựa trên cặp:

```text
(identity_issuer, identity_subject)
=
("https://login.example.org", "user-8c6e4d")
```

`sub` chỉ cần ổn định **trong phạm vi issuer và chính sách định danh liên quan**; với **pairwise subject identifiers**, cùng một người dùng có thể có subject khác nhau ở các RP/sector. Không giả định hai ID token từ issuer khác nhau mà có `sub` giống nhau đại diện cho cùng một người.

`email_verified=true` có thể hữu ích trong một chính sách liên kết tài khoản được thiết kế cẩn thận, nhưng không tự cấp quyền sở hữu mọi tài khoản dùng email đó ở ứng dụng.

### 6.2. Xác thực mới hay đang dùng lại phiên SSO?

OP có thể đã có phiên đăng nhập và không yêu cầu người dùng nhập lại mật khẩu. Khi RP yêu cầu xác thực gần đây, có thể sử dụng các tham số OIDC như:

- `max_age`: giới hạn thời gian kể từ lần xác thực cuối cùng; nếu yêu cầu, RP phải kiểm tra `auth_time` trong ID token.
- `prompt=login`: yêu cầu OP xác thực lại theo semantics của OP.
- `prompt=none`: yêu cầu OP không hiển thị giao diện; OP có thể trả lỗi `login_required` hoặc `interaction_required` nếu không thể đáp ứng âm thầm.
- `acr_values` và claim `acr`: có thể hỗ trợ yêu cầu mức/ngữ cảnh xác thực khi OP và RP thống nhất ý nghĩa.

Việc ID token hợp lệ **không tự đảm bảo MFA đã diễn ra**. Chỉ kết luận như vậy khi OP công bố thông tin đáng tin cậy (ví dụ `acr`/`amr` theo hợp đồng tích hợp) và RP có chính sách kiểm tra rõ ràng.

## 7. Tích hợp OIDC Login trong Spring Security

### 7.1. Spring Boot web application đóng vai Relying Party

Ví dụ ứng dụng Spring MVC render giao diện tại server và sử dụng một OP có hỗ trợ discovery.

Khai báo dependencies bằng Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Cấu hình `application.yml`:

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
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Ở OP cần đăng ký client confidential có `client_id`, phương thức xác thực và redirect URI chính xác, ví dụ:

```text
https://app.example.org/login/oauth2/code/company
```

Giá trị `OIDC_ISSUER_URI` là issuer được tin cậy do OP công bố, ví dụ `https://login.example.org`; khi discovery tương thích, Spring Security truy xuất metadata và các khóa xác minh từ issuer này. Giữ `client-secret` ở backend (secret manager hoặc môi trường chạy), không lưu trong frontend hoặc commit vào source.

**Vì sao scope `openid` quan trọng?** Với registration yêu cầu `openid`, Spring Security nhận biết đây là đăng nhập OIDC và xử lý principal theo OIDC (thường là `OidcUser`). Nếu client chỉ xin các scope OAuth thuần và không có `openid`, không thể suy luận rằng RP có ID token OIDC.

Cấu hình bảo vệ trang:

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
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Mặc định, trang yêu cầu xác thực sẽ kích hoạt luồng đăng nhập phù hợp; có thể chủ động truy cập:

```text
GET /oauth2/authorization/company
```

Sau callback thành công, Spring Security xác thực ID token và gắn principal OIDC vào `SecurityContext`, thường kết hợp với HTTP session cho web app. Trình duyệt nhận **session cookie**; ID token không cần được đưa ra JavaScript.

**Về PKCE:** Authorization Code + PKCE là thực hành bảo mật tốt cả khi có client authentication. Với client confidential, việc tự bật PKCE có thể cần một `OAuth2AuthorizationRequestResolver` được cấu hình customizer `OAuth2AuthorizationRequestCustomizers.withPkce()` tùy phiên bản Spring Security; không nên giả định mọi cấu hình và phiên bản đều bật PKCE giống nhau. OP phải hỗ trợ `S256` tương ứng.

### 7.2. Lấy thông tin người dùng đã đăng nhập qua `OidcUser`

Ví dụ endpoint chỉ trả về subject và vài claim để hiển thị, **không trả token ra browser**:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    public record CurrentUser(
        String issuer,
        String subject,
        String displayName,
        String email
    ) {}

    @GetMapping("/me")
    public CurrentUser me(@AuthenticationPrincipal OidcUser user) {
        return new CurrentUser(
            user.getIdToken().getIssuer().toString(),
            user.getSubject(),
            user.getFullName(),
            user.getEmail()
        );
    }
}
```

`OidcUser` cung cấp các thông tin như `getIdToken()`, `getUserInfo()` và claim accessor; dữ liệu từ UserInfo chỉ có khi được OP cung cấp và được Spring Security lấy về. Những giá trị như `name` và `email` có thể là `null`, nên giao diện phải chấp nhận thiếu claim. `getSubject()` là định danh từ OP, **không phải ID tự động của bảng users nội bộ**.

Để ứng dụng có vai trò/permission riêng, nên ánh xạ principal OIDC sang tài khoản nội bộ và cấp authorization dựa trên chính sách ứng dụng. Không mặc định dùng scope `openid`, `profile` hoặc `email` làm quyền quản trị.

### 7.3. OIDC Login và gọi downstream API là hai bước riêng

Sau đăng nhập, ứng dụng Spring có thể có access token trong thông tin authorized client; dùng `OAuth2AuthorizedClient` hoặc `OAuth2AuthorizedClientManager` để quản lý token khi gọi API.

```text
RP Spring Boot:
  1. ID token -> xác thực người dùng cho phiên đăng nhập
  2. Access token -> gửi trong Authorization: Bearer ... khi gọi API
  3. Session cookie -> duy trì phiên trình duyệt với RP

API Spring Boot:
  1. Nhận Bearer access token
  2. Xác minh token bằng Resource Server
  3. Kiểm tra audience và scope/permission trước khi trả dữ liệu
```

Một REST API kiểm tra JWT access token dùng `spring-boot-starter-oauth2-resource-server` và `oauth2ResourceServer().jwt()` với issuer/audience đúng. API **không** dùng `oauth2Login()` chỉ để kiểm tra bearer token, và **không** chấp nhận ID token thay access token.

Nếu SPA gọi API trực tiếp, SPA thường là **public client** thực hiện OIDC Authorization Code + PKCE; Spring API chỉ làm Resource Server. Nếu SPA giao tiếp qua backend BFF, backend có thể là confidential RP và giữ token server-side.

### 7.4. Khi nào tùy biến OIDC user service?

Spring Security có các lớp như `OidcUserService` và các hook xử lý xác thực thành công. Có thể cần tùy biến để:

- Liên kết `(iss, sub)` đến người dùng trong cơ sở dữ liệu ứng dụng.
- Yêu cầu người dùng đã được mời hoặc được kích hoạt.
- Nạp role/permission nghiệp vụ từ nguồn nội bộ.
- Kiểm tra điều kiện đặc thù như tổ chức, tenant, mức xác thực và quyền truy cập.

Hãy tách rạch ròi hai việc:

- **Protocol validation:** xác minh ID token, issuer, signature, audience, nonce… do thành phần OIDC đảm trách.
- **Business authorization:** xác định principal có quyền vào nhóm, tenant, trang quản trị hoặc dữ liệu cụ thể nào.

Không lấy một claim tùy ý chưa được xác minh làm vai trò `ROLE_ADMIN`. Cũng không liên kết tài khoản bằng email một cách mặc định mà thiếu chính sách nhận diện và chứng minh sở hữu phù hợp.

## 8. Phiên OIDC, đăng xuất và thời hạn token

Có thể tồn tại **nhiều phiên khác nhau**:

1. **Phiên ứng dụng tại RP**: session cookie do Spring Boot tạo để duy trì trạng thái đăng nhập.
2. **Phiên SSO tại OP**: người dùng có thể đã đăng nhập trên IdP và được dùng lại phiên cho RP khác.
3. **Vòng đời token**: ID token, access token và refresh token có thời hạn/chính sách riêng.

Khi người dùng nhấn **Logout** tại RP, xóa phiên Spring **không nhất thiết** xóa phiên SSO tại OP. Nếu OP hỗ trợ **RP-Initiated Logout**, ứng dụng có thể phối hợp chuyển hướng đến endpoint đăng xuất của OP, dùng cơ chế tương thích như `OidcClientInitiatedLogoutSuccessHandler` trong Spring Security và cấu hình `post_logout_redirect_uri` chính xác.

Không mặc định có “đăng xuất toàn hệ thống” chỉ vì một phía xóa cookie. Các phương thức front-channel/back-channel logout, khả năng thu hồi refresh token và chính sách session do hệ thống tích hợp hỗ trợ cần được xem xét riêng.

Một access token hết hạn cũng không đồng nghĩa session ứng dụng phải hết hạn ngay; session tồn tại bao lâu là quyết định của RP. Ngược lại, session còn hiệu lực không có nghĩa access token đã cấp vẫn được Resource Server chấp nhận. Thiết kế ứng dụng phải điều phối những vòng đời này, nhất là khi có refresh token.

## 9. Bảo mật OIDC trong ứng dụng thực tế

### 9.1. Phân ranh nơi tin cậy

| Biên tin cậy | Điều phải bảo vệ |
|---|---|
| Browser ↔ RP | HTTPS, session cookie `Secure`/`HttpOnly`, `SameSite` phù hợp và CSRF |
| RP ↔ OP | Issuer/metadata tin cậy, TLS, redirect URI chuẩn, client authentication khi có |
| Authorization callback | `state` và ràng buộc yêu cầu, nonce nếu gửi, code + PKCE |
| OP → RP qua ID token | Chữ ký, thuật toán, issuer, audience, thời gian, nonce |
| RP ↔ UserInfo | Access token phù hợp, HTTPS, `sub` đồng nhất với ID token |
| RP ↔ API | Access token đúng audience/scope, quyền tài nguyên tại API |

Với SPA, tránh phơi lộ access/refresh token trong URL, log, analytics hoặc nơi JavaScript bên thứ ba có thể lấy được. Với BFF, giữ token ở backend giúp giảm khả năng JavaScript trực tiếp đọc token, nhưng không loại bỏ tác động của XSS hoặc CSRF lên phiên trình duyệt.

### 9.2. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách tiếp cận phù hợp |
|---|---|---|
| “OAuth 2.0 đã có access token nên đủ để đăng nhập” | Không có hợp đồng xác thực người dùng thống nhất | Dùng OIDC, yêu cầu `openid` và kiểm tra ID token |
| “JWT decode được nghĩa là token hợp lệ” | Có thể nhận token giả, sai issuer hoặc audience | Dùng thư viện kiểm tra chữ ký và đầy đủ claim bắt buộc |
| Gửi ID token để gọi REST API | Sai người nhận/mục đích và nguy cơ nhận token nhầm | API nhận access token dành cho API |
| Dùng `email` làm khóa định danh duy nhất | Email có thể thay đổi, không được xác minh hoặc tái sử dụng | Lưu khóa `(iss, sub)`; liên kết email theo chính sách riêng |
| Đồng nhất “đăng nhập” với “có quyền admin” | Có thể cấp quyền quá mức | Tách authentication khỏi business authorization |
| Bỏ kiểm tra `state`/`nonce` khi triển khai thủ công | Dễ chấp nhận callback/token nhầm ngữ cảnh hoặc bị replay | Dùng thư viện OIDC đáng tin cậy và giữ ràng buộc yêu cầu |
| Giả định OP đã thực hiện MFA | Mức xác thực có thể thấp hơn yêu cầu nghiệp vụ | Thỏa thuận `acr`/`amr`/`max_age` và kiểm tra phù hợp |
| Kỳ vọng đăng xuất RP tự xóa phiên OP | Người dùng vẫn có thể SSO khi quay lại | Thiết kế logout tích hợp OP nếu cần |
| Đưa `client_secret` của server vào SPA | Secret bị lộ cho người dùng cuối | SPA public client + PKCE hoặc BFF confidential client |
| Dùng claim `roles` tùy ý từ token chưa xác minh | Nguy cơ leo thang đặc quyền | Xác minh issuer/token và ánh xạ quyền có kiểm soát |

## 10. Ví dụ xuyên suốt: đăng nhập vào hệ thống quản lý tài liệu

Giả sử một hệ thống có ba thành phần:

- `https://app.example.org`: Spring Boot MVC đóng vai OIDC RP.
- `https://login.example.org`: OpenID Provider do doanh nghiệp quản lý.
- `https://api.example.org`: API tài liệu đóng vai OAuth Resource Server.

Khi nhân viên truy cập trang tài liệu:

1. RP đưa trình duyệt đến OP với `scope=openid profile email` và dữ liệu ràng buộc yêu cầu.
2. Người dùng xác thực tại OP. OP trả authorization code, RP đổi code lấy ID token và access token.
3. RP xác minh ID token có `iss=https://login.example.org`, `aud=document-web-client`, chữ ký/thời gian hợp lệ và nonce phù hợp nếu đã gửi.
4. RP ánh xạ `(iss, sub)` vào nhân viên nội bộ, kiểm tra tài khoản đang hoạt động và tạo session.
5. Khi tải danh sách tài liệu, RP gửi **access token** đến API. API xác minh token cho chính audience và scope tương ứng, rồi kiểm tra quyền trên từng tài liệu.
6. Khi người dùng đăng xuất, RP xóa session và cân nhắc gọi logout endpoint OP nếu muốn kết thúc phiên SSO tương ứng.

Nếu RP nhận được một ID token có `sub` hợp lệ nhưng tài khoản nội bộ bị vô hiệu hóa, **RP vẫn từ chối truy cập ứng dụng** theo chính sách. Đó là ví dụ cho thấy **OIDC chứng minh danh tính; ứng dụng quyết định quyền sử dụng hệ thống**.

## 11. Cách ghi nhớ ranh giới OAuth 2.0 và OIDC

| Câu hỏi | Thành phần trả lời |
|---|---|
| Ai được IdP xác thực, và bằng chứng xác thực được phát cho ứng dụng nào? | **OIDC ID token** sau khi RP xác minh |
| Ứng dụng được gọi API nào và với scope gì? | **OAuth 2.0 access token** và chính sách của Resource Server |
| Tên, email, ảnh của người dùng lấy từ đâu? | Các **OIDC claims** trong ID token/UserInfo, nếu OP cấp |
| Người dùng có được xem tài liệu của phòng ban khác không? | **Authorization nghiệp vụ** do ứng dụng/API thực thi |
| Tại sao Spring MVC nhớ người đã đăng nhập giữa các request? | **Session/cookie của Spring Security**, với thời hạn độc lập token |
| Làm thế nào RP biết OP đáng tin cậy và ID token hợp lệ? | **Issuer, discovery, JWKS và OIDC token validation** |

**Kết luận:** OpenID Connect biến OAuth 2.0 thành nền tảng đăng nhập có thể liên thông bằng cách thêm **ID token**, chuẩn hóa claim danh tính, UserInfo, discovery và quy tắc xác minh. Khi áp dụng với Spring Security, hãy để **OIDC Login** thiết lập principal và phiên người dùng, để **OAuth2 Client** quản lý token cho lời gọi API, và để **Resource Server** xác thực access token cũng như thực thi quyền truy cập tài nguyên.

## 12. Tham khảo chuẩn và tài liệu triển khai

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): định nghĩa RP, OP, ID Token, UserInfo, flow và kiểm tra token.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): metadata discovery, issuer và thông tin khóa.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): khung ủy quyền mà OIDC xây dựng trên đó.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE cho Authorization Code.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): các khuyến nghị an toàn hiện đại cho OAuth/OIDC.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): đăng nhập với OAuth 2.0/OIDC trong ứng dụng Servlet.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized client và token cho lời gọi downstream.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): bảo vệ API dựa trên access token.
