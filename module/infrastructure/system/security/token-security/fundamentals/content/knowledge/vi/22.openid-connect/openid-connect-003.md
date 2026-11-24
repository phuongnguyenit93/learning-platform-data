# OpenID scope — Phạm vi `openid` trong OpenID Connect

## 1. Scope `openid` đánh dấu ranh giới giữa OAuth 2.0 và OpenID Connect

Trong chương **OpenID Connect** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, bài **OpenID scope** giải thích một chi tiết nhỏ trong request nhưng thay đổi rất lớn về ý nghĩa giao thức: khi client yêu cầu `scope=openid` và OpenID Provider (OP) xử lý yêu cầu đó theo OpenID Connect (OIDC), client đang yêu cầu **xác thực danh tính end-user**, không chỉ xin quyền gọi API như OAuth 2.0 thuần túy.

Ví dụ ứng dụng `sales-dashboard` cần hai kết quả khác nhau:

- **Biết ai đã đăng nhập:** xác minh rằng OP `https://auth.example.test` đã xác thực Alice cho đúng client, từ đó tạo session ứng dụng. OIDC cung cấp **ID token**, trong đó có `iss`, `sub`, `aud` và các claims xác thực cần thiết.
- **Được đọc đơn hàng nào:** dùng **access token** có phạm vi `orders.read`, dành cho `orders-api`, rồi resource server kiểm tra token và quyền nghiệp vụ đối với từng đơn hàng.

Hai mục tiêu có liên quan nhưng **không được trộn làm một**. `openid` không có nghĩa Alice được quyền đọc mọi API, còn `orders.read` không thay thế yêu cầu xác thực user theo OIDC.

> **Nguyên tắc:** `openid` là scope **bắt buộc trong OIDC Authentication Request** để chỉ ra yêu cầu OIDC. Các scope `profile`, `email`, `address`, `phone` xin *các nhóm claims* bổ sung về end-user; chúng **không tự biến access token thành ID token** và không phải quyền truy cập tùy ý vào resource API. API vẫn phải xác minh access token, audience, scope và authorization riêng.

Trong bài, tất cả miền `example.test`, mã định danh và token chỉ để minh họa, không phải endpoint hoặc credential thật.

### Mục tiêu học tập

Sau bài, bạn sẽ:

1. Hiểu chính xác khi nào một authorization request trở thành **OIDC request** nhờ `openid`.
2. Phân biệt **scope chuẩn OIDC**, OAuth API scopes, ID token claims, UserInfo response và consent.
3. Giải thích vì sao xin `email` không có nghĩa chắc chắn nhận `email`, và `offline_access` không bảo đảm có refresh token.
4. Viết Authorization Code + PKCE request có `openid`, nhận và xác minh ID token theo issuer/client/nonce/time, sử dụng UserInfo đúng.
5. Thiết kế định danh user bằng **`iss` + `sub`**, tránh dùng email làm khóa định danh bất biến và tránh lỗi pairwise subject.
6. Áp dụng Java/Spring Security OAuth2 Login, claim mapping, phân tách API access token và kiểm thử các trường hợp sai scope/token/issuer.

## 2. Bốn vai trò và ba loại giá trị dễ bị nhầm

OIDC mở rộng OAuth 2.0, nhưng không bỏ các vai trò:

| Vai trò | Trong đăng nhập `sales-dashboard` | Trách nhiệm |
| --- | --- | --- |
| **End-user / Resource Owner** | Alice | Xác thực tại OP và cấp quyền trong những trường hợp có consent |
| **Relying Party (RP) / OAuth Client** | `sales-dashboard` | Khởi tạo OIDC request, xác minh ID token, tạo session, xin AT nếu cần |
| **OpenID Provider (OP) / Authorization Server** | `https://auth.example.test` | Xác thực Alice, xử lý scope/claims/policy, phát ID token và AT theo flow |
| **Resource Server (RS)** | `orders-api` | Nhận AT đúng audience, kiểm tra issuer, signature/introspection, scope và ACL |

**OpenID Provider** là AS có khả năng OIDC. **Relying Party** chính là client tiêu thụ kết quả xác thực; không phải mọi OAuth client đều là RP nếu nó chỉ dùng OAuth API authorization.

### 2.1. Phân biệt scope, claim và token

| Khái niệm | Ví dụ | Tác dụng | Không được suy diễn |
| --- | --- | --- | --- |
| **Request scope** | `openid profile email orders.read` | Client yêu cầu OIDC, user claims và quyền API | AS đã cấp tất cả quyền được xin |
| **Standard OIDC scope** | `openid` | Kích hoạt OIDC Authentication Request | Được gọi mọi API |
| **OIDC claims-request scope** | `profile`, `email` | Xin công bố nhóm end-user claims | Tất cả claims sẽ luôn có mặt |
| **API scope** | `orders.read` | Xin quyền thao tác được AS/RS định nghĩa | User có quyền đọc mọi object |
| **Claim** | `sub`, `email`, `email_verified` | Dữ liệu/thuộc tính trong ID token hoặc UserInfo theo contract | Claim là OAuth scope |
| **ID token** | JWT có `iss`, `sub`, `aud` | Xác thực end-user cho RP | OAuth AT dành cho RS |
| **Access token (AT)** | JWT hoặc opaque | Credential truy cập UserInfo/RS theo grant/audience | Đương nhiên là ID token |
| **Refresh token (RT)** | Opaque handle tùy AS | Xin AT mới ở token endpoint | Được phát chỉ vì scope `openid` |

### 2.2. Sơ đồ ranh giới

~~~mermaid
flowchart LR
    U["Alice / End-user"] -->|"Đăng nhập và consent nếu cần"| OP["OpenID Provider / AS"]
    RP["sales-dashboard / RP"] -->|"OIDC Authorization Request: openid + scopes"| OP
    OP -->|"ID token: xác thực Alice cho RP"| RP
    OP -->|"AT: theo grant và resource policy"| RP
    RP -->|"ID token validation → local login session"| SESSION["Session của RP"]
    RP -->|"AT aud=orders-api; scope=orders.read"| RS["orders-api / RS"]
    RS -->|"Object / tenant authorization"| DATA["Đơn hàng Alice được phép"]
    RP -.->|"AT dành cho UserInfo nếu hợp lệ"| UI["OP UserInfo Endpoint"]
~~~

ID token và AT có thể được cấp trong cùng một **Authorization Code Flow** sau khi request có `openid`, nhưng **audience/mục đích xác minh của chúng khác nhau**. RP không được gửi ID token đến API và API không được lấy AT như bằng chứng đăng nhập RP khi chưa có validation/context tương ứng.

## 3. Điều kiện `openid` trong Authentication Request

OIDC Core định nghĩa **OpenID Connect Authentication Request** dưới dạng OAuth 2.0 Authorization Request có scope **chứa giá trị `openid`**. Giá trị này được phân biệt đúng từng scope token trong danh sách, không phải substring:

~~~text
scope=openid                  → Yêu cầu OIDC
scope=openid profile          → Yêu cầu OIDC + claims thuộc profile
scope=openid email           → Yêu cầu OIDC + email claims
scope=openid orders.read     → Yêu cầu OIDC + quyền API theo policy
scope=profile email          → Không có openid; không được tự xem là OIDC login
scope=orders.read            → Chỉ yêu cầu OAuth authorization, không OIDC
scope=myopenid               → Không chứa scope "openid" nguyên vẹn
scope=OpenID                 → Không phải scope "openid" (case-sensitive)
~~~

OAuth 2.0 `scope` là **danh sách các scope-token được phân tách bởi dấu cách**, tuân syntax RFC 6749. Trong query/form URL, dấu cách thường được mã hóa `%20` (hoặc `+` theo form encoding). Đừng kiểm tra `scopeString.contains("openid")`: `myopenid` sẽ khớp sai. Hãy parse thành tokens, so chính xác và xét đúng ký tự/case.

### 3.1. `openid` là dấu yêu cầu xác thực, không phải mức quyền

Không nên viết logic:

~~~text
if accessToken.scope contains "openid":
    allow /orders/admin
~~~

`openid` không tương đương quyền `admin`, `user.read`, `orders.read` hoặc một role tự động. Một user đăng nhập hợp lệ có thể không được thao tác bất kỳ đơn hàng nào. Resource server phải dựa trên AT và **API scopes/domain authorization**, không chỉ thấy user đã đăng nhập OIDC.

### 3.2. Không có `openid` thì không kỳ vọng ID token

Request OAuth 2.0 thuần:

~~~http
GET /authorize?response_type=code&client_id=sales-dashboard&scope=orders.read&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&state=<random-state> HTTP/1.1
Host: auth.example.test
~~~

Theo OIDC, request không có scope `openid` không phải OIDC Authentication Request. AS có thể xử lý như OAuth 2.0 request nếu đã hỗ trợ và client đủ điều kiện. **RP không được giả định có `id_token`** chỉ vì AS cũng là OpenID Provider.

Nếu hệ thống muốn đăng nhập người dùng, nó phải gửi `openid` và dùng OIDC validation, không “suy login” chỉ từ việc OAuth token endpoint trả một AT.

### 3.3. OIDC xác thực không thay authentication policy

`openid` không có nghĩa user phải vừa nhập mật khẩu trong mỗi request: OP có thể sử dụng **SSO session** còn hợp lệ. Nếu nghiệp vụ cần xác thực mới hoặc mức bảo đảm cụ thể, RP phải dùng và kiểm tra các tham số/claims như `max_age`, `auth_time`, `prompt=login`, `acr_values` hay `claims` theo OIDC/OP policy. Đây là lớp **authentication freshness/assurance**, độc lập với scope `openid`.

## 4. Những scope chuẩn OIDC ngoài `openid`

OIDC Core mô tả các scope yêu cầu nhóm **Standard Claims** cho end-user:

| Scope | Các claims thường được yêu cầu | Cách hiểu đúng |
| --- | --- | --- |
| **`openid`** | Bật OIDC, ID token có các claims xác thực bắt buộc | Không đồng nghĩa xin tên/email/phone |
| **`profile`** | `name`, `family_name`, `given_name`, `middle_name`, `nickname`, `preferred_username`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo`, `locale`, `updated_at` | Xin thông tin hồ sơ, không bảo đảm tất cả trường có mặt |
| **`email`** | `email`, `email_verified` | Xin email và trạng thái xác minh theo OP; không tự là quyền gửi email hoặc chứng minh sở hữu vĩnh viễn |
| **`address`** | `address` | Xin địa chỉ theo cấu trúc OIDC Standard Claims |
| **`phone`** | `phone_number`, `phone_number_verified` | Xin số điện thoại và trạng thái xác minh theo OP |
| **`offline_access`** | Xin khả năng truy cập khi end-user không còn hiện diện (thường liên quan RT) | **Không tự bảo đảm cấp RT**, có điều kiện consent/response type/policy |

**Đây là các yêu cầu công bố claims, không phải mệnh lệnh bắt OP phải cung cấp mọi claim.** Theo dữ liệu thực tế, cấu hình, consent, data minimization, chính sách quyền riêng tư và kiểu flow, một số claims có thể không có hoặc không có trong **ID token**, mà chỉ có thể lấy ở **UserInfo**.

### 4.1. `openid profile` không bảo đảm có tên hiển thị

RP xin:

~~~text
scope=openid profile
~~~

Nhưng Alice chưa cung cấp tên hoặc OP có policy không tiết lộ tên. RP không được lỗi xác thực chỉ vì `name` trống nếu claim đó không bắt buộc theo profile/contract. Nếu ứng dụng cần một tên hiển thị bắt buộc, cần thiết kế UX nhập bổ sung hoặc hợp đồng claims/chính sách OP, **không ép từ scope thành bảo đảm dữ liệu**.

### 4.2. `openid email` không thay xác minh quyền sở hữu tài khoản

`email` và `email_verified` là hai claims khác nhau. Ví dụ:

~~~json
{
  "sub": "user-742",
  "email": "alice@example.test",
  "email_verified": false
}
~~~

Ứng dụng không được suy rằng email đã được xác minh chỉ vì trường `email` xuất hiện. Kể cả `email_verified=true`, email có thể được đổi/tái sử dụng theo thời gian; nó **không nên** là khóa định danh bất biến hoặc điều kiện duy nhất cho việc link hai tài khoản nhạy cảm thuộc các issuer khác nhau.

### 4.3. `address` là structured claim

OIDC Standard Claim `address` có thể là một JSON object:

~~~json
{
  "address": {
    "formatted": "123 Example Street, Sample City",
    "street_address": "123 Example Street",
    "locality": "Sample City",
    "region": "Sample Region",
    "postal_code": "00000",
    "country": "Exampleland"
  }
}
~~~

Đây chỉ là cấu trúc minh họa. Không dùng `address` scope như quyền được truy cập địa chỉ của **mọi người dùng** trong directory hay hệ thống CRM. Nó chỉ yêu cầu công bố thuộc tính end-user trong OIDC và phải được OP đánh giá consent/policy.

### 4.4. `phone` không phải quyền gửi SMS

`phone_number`, `phone_number_verified` cung cấp thông tin và trạng thái verify do OP biết. Việc RP muốn gửi SMS, thực hiện giao dịch tài chính hoặc dùng số điện thoại làm bằng chứng MFA cần **chính sách và consent riêng**, không mặc định phát sinh từ `openid phone`.

### 4.5. `offline_access` khác refresh-token grant

`offline_access` là một scope **xin quyền truy cập khi user không hiện diện**; RT là **credential** có thể được OP/AS cấp để thực hiện quyền đó. Client xin `offline_access` không được tự tin rằng:

- OP sẽ cấp RT trong mọi grant/client type.
- RT luôn sống vô hạn hoặc không cần rotation/sender constraint.
- RP được tự tăng scopes bằng `grant_type=refresh_token`.
- Logout ở RP tự thu hồi RT tại AS hoặc mọi AT đã phát hành.

Chi tiết consent và response type của `offline_access` sẽ được xem riêng ở mục vòng đời token.

## 5. ID token: kết quả xác thực dành cho Relying Party

Một request OIDC dùng Authorization Code Flow có `openid` thường dẫn đến việc token endpoint trả **ID token** cho RP khi authorization grant thành công. ID token là JWT mô tả **authentication event/subject** trong ngữ cảnh OP và client.

Ví dụ payload minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-742",
  "aud": "sales-dashboard",
  "exp": 1893456000,
  "iat": 1893455700,
  "auth_time": 1893455600,
  "nonce": "example-nonce-for-current-authentication-transaction"
}
~~~

`exp` và `iat` trong ví dụ là UNIX timestamps minh họa, không phải token còn hiệu lực hiện tại. Thời gian thật cần được tạo bởi OP và xác minh với đồng hồ tin cậy.

### 5.1. Các claims cốt lõi

| Claim | Ý nghĩa | Kiểm tra của RP |
| --- | --- | --- |
| `iss` | OP/issuer đã phát hành ID token | Phải bằng **expected issuer** đã cấu hình |
| `sub` | Subject identifier của user theo OP | Phải tồn tại, dùng với issuer làm định danh dài hạn |
| `aud` | ID token dành cho OAuth/OIDC client nào | Phải chứa **client_id của RP** |
| `exp` | Thời gian hết hạn | Từ chối ID token đã hết hạn ngoài skew được cho phép |
| `iat` | Thời gian phát hành | Kiểm tra cú pháp/điều kiện time policy |
| `auth_time` | Thời gian end-user xác thực | Kiểm tra khi `max_age` hoặc policy/claims yêu cầu |
| `nonce` | Giá trị ràng buộc authentication request | So khớp chính xác khi đã gửi/được yêu cầu |
| `azp` | Authorized Party, khi ngữ cảnh/profile yêu cầu | Kiểm tra theo OIDC rules, nhất là trường hợp nhiều audience |
| `acr`/`amr` | Lớp/phương thức authentication do OP mô tả | Chỉ tin theo contract assurance và policy |

RP phải xác minh **chữ ký, issuer, audience, expiry và các điều kiện OIDC có liên quan**; không chỉ decode JWT payload bằng Base64 rồi đọc `sub`. Với những trường hợp OIDC có nhiều giá trị `aud`, RP cũng phải áp quy tắc kiểm tra `azp` theo đặc tả. Không dùng token do issuer khác ký chỉ vì `aud` chứa client ID.

### 5.2. ID token không phải OAuth access token

Giả sử AS phát hành:

~~~text
ID token:
  iss=https://auth.example.test
  aud=sales-dashboard
  sub=user-742

Access token:
  iss=https://auth.example.test
  aud=orders-api
  scope=orders.read
~~~

RP dùng ID token để xác thực Alice và tạo local session. RP dùng AT **dành cho orders-api** để truy cập đơn hàng. `orders-api` không được chấp nhận ID token `aud=sales-dashboard` dù cùng issuer, `sub` và chữ ký đúng. Đây là **token type/audience confusion** nếu RS bỏ qua mục đích của token.

### 5.3. `openid` không tự làm ID token mang đầy đủ hồ sơ

Ngay cả với `scope=openid profile email`, ID token có thể chỉ chứa các claims xác thực thiết yếu. Những profile/email claims được hỗ trợ có thể nằm ở **UserInfo Endpoint**, phụ thuộc flow và OP. Client cần hiểu **claim source** theo hợp đồng thay vì đặt logic “không có `email` trong ID token = OIDC login thất bại”.

## 6. Authorization Code + PKCE với `openid`: toàn bộ đường đi

Đối với web backend/BFF, SPA và native app có browser tương tác, **Authorization Code + PKCE** là lựa chọn nền tảng hiện đại. RP yêu cầu `openid` trong authorization request, **nhận authorization code**, đổi code tại token endpoint và xác minh ID token trước khi xác nhận login.

### 6.1. Luồng OIDC cơ bản

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice / Browser
    participant RP as sales-dashboard / RP
    participant OP as OpenID Provider / AS
    participant UI as UserInfo Endpoint
    participant API as orders-api
    RP->>RP: Tạo state + PKCE S256, nonce nếu dùng
    RP-->>U: Redirect /authorize với scope=openid profile email
    U->>OP: OIDC authorization request
    OP->>U: Login/MFA và consent nếu cần
    U-->>OP: Xác thực + quyết định
    OP-->>U: Redirect về RP với code + state
    U->>RP: Callback code + state
    RP->>RP: Verify state, issuer/transaction, PKCE verifier
    RP->>OP: POST /token: code + code_verifier + client authentication nếu cần
    OP-->>RP: id_token + access_token (+ RT nếu policy)
    RP->>RP: Verify ID token iss, aud, exp, nonce, time
    opt Cần hồ sơ và có token hợp lệ cho UserInfo
        RP->>UI: GET /userinfo Authorization: Bearer AT
        UI-->>RP: sub + claims được phép công bố
        RP->>RP: UserInfo.sub phải khớp ID token.sub
    end
    RP->>RP: Tạo local authenticated session
    opt Có AT riêng dành cho orders-api
        RP->>API: Authorization: Bearer AT aud=orders-api
        API->>API: Verify AT + scope + ACL
    end
~~~

**Không đồng nhất mọi access token trong sơ đồ.** AT phục vụ **UserInfo Endpoint** của OP và AT dành cho **`orders-api`** có thể là những token khác nhau tùy AS, audience và resource-indicator profile. Chỉ gửi mỗi token tới resource mà issuer/policy cho phép. Một request `scope=openid orders.read` không mặc định đảm bảo AS cấp **hai** AT; thiết kế nhiều resource phải được xác nhận với nhà cung cấp.

### 6.2. Authorization request minh họa

~~~http
GET /oauth2/authorize?response_type=code&client_id=sales-dashboard&redirect_uri=https%3A%2F%2Fclient.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&scope=openid%20profile%20email&state=<random-state>&nonce=<random-nonce>&code_challenge=<pkce-s256-challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Các placeholder phải được thay bằng giá trị bảo mật thực: `state` khó đoán, `nonce` theo transaction khi sử dụng, `code_verifier` tạo bằng CSPRNG (43–128 ký tự RFC 7636), `code_challenge` từ SHA-256/Base64url không padding. **Không đưa verifier trong authorization request**; client gửi verifier khi đổi code tại token endpoint.

Các điều kiện:

1. `response_type=code` chọn Authorization Code Flow.
2. `scope` phải **chứa `openid`** nếu muốn OIDC authentication.
3. `client_id` và `redirect_uri` thuộc registration được OP phê duyệt.
4. `state` ràng buộc callback với giao dịch của RP; PKCE ràng buộc code với verifier.
5. `nonce` ràng buộc ID token với authentication request khi gửi/yêu cầu.
6. OP xác thực end-user theo chính sách, đánh giá consent/data release và không tự cấp API scopes ngoài client/user policy.

### 6.3. Callback không phải bằng chứng login hoàn tất

Sau khi user đăng nhập, OP trả:

~~~http
HTTP/1.1 302 Found
Location: https://client.example.test/login/oauth2/code/company?code=<one-time-code>&state=<random-state>
~~~

RP chỉ mới có **authorization code**; chưa nên tạo một authenticated session với `sub` tự khai hay coi `state` là token. RP cần xác minh state/issuer, đổi code dùng đúng PKCE verifier/client authentication và **xác minh ID token** do OP trả. Authorization code có thời hạn ngắn, dùng **một lần**; không gửi lại vô hạn khi response mất do timeout.

### 6.4. Token request

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fclient.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&client_id=sales-dashboard&code_verifier=<original-pkce-verifier>
~~~

Đây là ví dụ dạng **public client** khi không có confidential client authentication. Với backend confidential client, request còn cần phương thức xác thực đã đăng ký: `client_secret_basic`, `private_key_jwt`, mTLS hoặc cơ chế tương ứng; `client_id` trong body không thay một client secret/private key. PKCE không phải bằng chứng user đã consent và cũng không thay xác thực confidential client.

### 6.5. Token response

~~~json
{
  "access_token": "<access-token-issued-by-op>",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "<signed-id-token-for-sales-dashboard>",
  "scope": "openid profile email"
}
~~~

`scope` trong token response chỉ mang tính ví dụ; theo OAuth, nếu phạm vi được cấp khác phạm vi được yêu cầu, AS phải phản ánh phạm vi được cấp. Không xem chuỗi requested scope là quyền thực tế khi OP đã thu hẹp scope hoặc không công bố một số claims. `refresh_token` có thể xuất hiện nếu grant/AS policy cho phép — **`openid` riêng lẻ không bảo đảm có refresh token**.

RP phải xác minh ID token trước khi tạo session. Nếu email/profile claims không có trong ID token, RP có thể lấy từ UserInfo Endpoint nếu provider hỗ trợ và AT đã cấp quyền đó; không tự coi access token là ID token chỉ vì AT trông giống JWT.

## 7. UserInfo Endpoint và sự khác nhau giữa “xin scope” với “nhận claim”

OIDC định nghĩa **UserInfo Endpoint** cung cấp end-user claims khi client trình **access token phù hợp**. Đây là một resource server đặc biệt của OP; nó không phải trang login, không phải token endpoint và không được trả thông tin user chỉ dựa vào một `client_id`.

### 7.1. Request UserInfo

~~~http
GET /userinfo HTTP/1.1
Host: auth.example.test
Authorization: Bearer <access-token-valid-for-userinfo>
Accept: application/json
~~~

Một response minh họa:

~~~json
{
  "sub": "user-742",
  "name": "Alice Nguyen",
  "preferred_username": "alice",
  "email": "alice@example.test",
  "email_verified": true,
  "locale": "vi-VN"
}
~~~

Đây không phải response bắt buộc có tất cả các trường. OP có thể chỉ trả `sub` hoặc các claims đã được phê duyệt. Scope `profile`/`email` là một cách yêu cầu nhóm claims; RP còn có thể dùng `claims` request parameter khi OP hỗ trợ để xin các claims cụ thể.

### 7.2. Quy tắc quan trọng nhất: UserInfo `sub` phải trùng ID token `sub`

OIDC Core yêu cầu RP xác nhận `sub` trong UserInfo Response **trùng chính xác** `sub` trong ID token đã được xác minh thuộc cùng transaction/user. Nếu không khớp, **không được sử dụng** response UserInfo đó.

~~~text
ID token đã verify:
  iss = https://auth.example.test
  sub = user-742

UserInfo response:
  sub = user-999

RP:
  REJECT / do not consume UserInfo
~~~

Đây là cách chặn một lớp **token/response substitution**: nếu UserInfo response thuộc user khác do session/token/cache bị trộn, RP không được âm thầm gán dữ liệu đó cho Alice.

Đừng kiểm tra user bằng cách so email vì email có thể thay đổi hoặc được chia sẻ trong một số mô hình; `sub` trong cùng issuer là định danh ổn định theo contract OIDC. Khi xử lý nhiều issuer, sử dụng cả `iss` và `sub`.

### 7.3. UserInfo có thể trả JWT hoặc JSON theo contract

Thông thường UserInfo response là JSON qua HTTPS, nhưng OIDC cho phép phản hồi được ký/mã hóa theo cấu hình/client registration. Nếu yêu cầu signed/encrypted UserInfo, RP phải **xác minh signature/encryption và claims** đúng profile. Không mặc định mọi response UserInfo là ID token hoặc chấp nhận payload JWT chưa xác minh chỉ vì nhận từ UserInfo URL.

### 7.4. Một UserInfo AT không nhất thiết được gọi API nghiệp vụ

Đây là ví dụ dễ gây lỗi:

~~~text
RP nhận AT từ OIDC Code Flow để gọi OP /userinfo.
RP chuyển cùng AT đến orders-api vì cũng thấy "scope=openid".
orders-api bỏ qua aud và trả dữ liệu.
~~~

Nếu AT chỉ dành cho OP/UserInfo, `orders-api` phải từ chối. Client cần một access token hợp lệ **dành cho orders-api**, có scope `orders.read` theo authorization policy. Có thể dùng Resource Indicators (RFC 8707) hoặc cơ chế AS khác để xác định resource; không tự thêm audience vào JWT hay forward tùy tiện token.

### 7.5. Không cache UserInfo theo email

Một cache kiểu:

~~~text
cache[email] = UserInfoResponse
~~~

có thể trộn dữ liệu giữa users/issuers nếu email trùng, đổi hoặc tái phân bổ. Cache cần được ràng buộc với **expected issuer, subject, session/client và các chính sách data privacy/TTL**; không lưu quá thời gian cần thiết. Nếu scope/consent bị rút, thông tin UserInfo đã cache cũng cần được xử lý theo chính sách lưu trữ và yêu cầu pháp lý liên quan.

## 8. `openid`, ID token và identity: nên dùng khóa `iss` + `sub`

OIDC `sub` định danh end-user trong namespace của issuer. Nếu ứng dụng liên kết đăng nhập với tài khoản nội bộ chỉ bằng `email`, nó có thể gặp **account linking** hoặc **account takeover** khi email đổi, được tái sử dụng hoặc hai OP phát hành cùng email.

### 8.1. Mẫu khóa người dùng

~~~text
ExternalIdentityKey = (issuer, subject)

issuer  = https://auth.example.test
subject = user-742

InternalUserId = lookupExternalIdentity(issuer, subject)
~~~

Chỉ sau khi ID token đã được xác minh, RP mới trích xuất `iss` và `sub` để tạo/tra bản ghi identity. Nếu một RP tin nhiều OP, hai token có `sub=user-742` **nhưng `iss` khác nhau** thường đại diện cho những identity khác nhau.

### 8.2. Public subject và pairwise subject

OIDC hỗ trợ **public** và **pairwise** Subject Identifier types:

| Loại | Đặc điểm | Ảnh hưởng |
| --- | --- | --- |
| **Public subject** | Cùng end-user có thể nhận cùng `sub` từ OP ở nhiều client theo policy | RP có thể nhận cùng định danh khi cùng OP |
| **Pairwise subject** | OP tính subject khác nhau theo **sector identifier** của client | Giảm khả năng liên kết hoạt động user giữa các RPs |

Không dựa vào giả định rằng `sub` của Alice ở `sales-dashboard` sẽ bằng `sub` ở `hr-dashboard` khi OP dùng pairwise subject khác sector. Nếu hai ứng dụng cần chia sẻ identity, phải có cơ chế identity-linking được người dùng/chính sách cho phép, không tự suy cùng người từ email.

### 8.3. Email không được dùng làm primary authentication proof

Một RP có thể dùng `email` đã xác minh cho chức năng thông báo hoặc UX, nhưng:

- Email không nhất thiết được cấp trong response, kể cả đã xin `email`.
- `email_verified` phải được hiểu theo nguồn và thời điểm xác minh của OP.
- Email có thể thay đổi; mapping không được âm thầm đổi người sở hữu tài khoản nội bộ khi email đổi.
- Không tự **merge** hai external identities từ hai issuer khác nhau chỉ vì email giống.
- Nếu liên kết tài khoản nhạy cảm, yêu cầu user hiện diện và chứng minh sở hữu theo luồng link account riêng.

### 8.4. Subject không đồng nghĩa quyền domain

Ngay cả khi `iss` + `sub` đúng Alice, các quyết định như “Alice có quyền hoàn tiền giao dịch 123 không?” thuộc **domain authorization** ở RP/RS. OIDC `openid` không tự khai báo nhóm RBAC/ABAC hay tất cả quyền trên đơn hàng.

Những claims custom như `roles`, `groups`, `tenant_id` có thể được AS/OP cấp theo contract riêng, nhưng **không phải OIDC Core Standard Claims được bảo đảm chỉ nhờ `openid`**. Scope `roles` hoặc `groups` cũng thường là provider-specific, không phải scope chuẩn OIDC Core.

## 9. Xin claims cụ thể bằng `claims` request parameter

Các scope chuẩn `profile`/`email` là cách xin **nhóm claims** tiện lợi, nhưng có thể quá rộng hoặc không diễn tả đúng yêu cầu. OIDC Core định nghĩa tham số `claims` dạng JSON để client có thể yêu cầu **những claims cụ thể trong ID token và/hoặc UserInfo response**, khi OP hỗ trợ.

### 9.1. Ví dụ JSON `claims` (trước khi URL-encode)

~~~json
{
  "id_token": {
    "auth_time": {
      "essential": true
    }
  },
  "userinfo": {
    "given_name": null,
    "family_name": null,
    "email": {
      "essential": true
    },
    "email_verified": null
  }
}
~~~

Trong authorization request thực, JSON này phải được **URL-encode** thành giá trị `claims`. `null` yêu cầu claim nhưng không chỉ định tính bắt buộc/giá trị kỳ vọng; `essential: true` thể hiện claim quan trọng với client. Việc OP có thể đáp ứng, trả lỗi hay bỏ qua một số yêu cầu còn phụ thuộc chuẩn, OP support, consent và chính sách.

### 9.2. `essential` không tự ép OP cung cấp thông tin

Đừng diễn giải rằng một claim được client đánh dấu `essential` sẽ **bắt buộc** xuất hiện dù OP không có dữ liệu hoặc user không đồng ý. OP có thể không đáp ứng được và xử lý theo quy tắc yêu cầu/exception. RP cần kiểm tra dữ liệu thực tế nhận được, có hành vi fallback/từ chối phù hợp **nghiệp vụ**, không tự điền dữ liệu giả để “làm đúng yêu cầu”.

### 9.3. Xin claims cụ thể có thể tốt hơn xin toàn bộ profile

Nếu ứng dụng chỉ cần biết cách xưng hô:

~~~text
Goal: hiển thị given_name
Over-broad request: openid profile email address phone
Targeted request:  openid + claims.userinfo.given_name
~~~

Xin ít dữ liệu hơn giúp giảm privacy exposure, đơn giản hóa consent và hạn chế phạm vi ảnh hưởng nếu dữ liệu user bị lộ. Tuy nhiên, **không phải OP nào cũng hỗ trợ `claims` parameter đầy đủ**; cần kiểm tra provider metadata và contract trước khi phụ thuộc tính năng.

### 9.4. `claims_supported` không phải bảo đảm mọi user đều có claim

OIDC Discovery có thể quảng bá `claims_supported` và `scopes_supported`. Đây là thông tin năng lực theo provider, **không khẳng định** tất cả người dùng đều có dữ liệu cụ thể hoặc chắc chắn claim được phát hành trong mọi token/flow. Consent, scope policy, account completeness và claim-source configuration vẫn ảnh hưởng response.

## 10. Scope `offline_access` và refresh token trong OIDC

`offline_access` là scope chuẩn OIDC dùng khi client cần truy cập tài nguyên trong lúc **end-user không còn chủ động hiện diện**. Ví dụ `sales-dashboard` đồng bộ dữ liệu khi Alice đã đóng tab. Đây là một quyết định có tác động dài hạn, không nên được cấp mặc định cho mọi đăng nhập.

### 10.1. Request minh họa

~~~http
GET /oauth2/authorize?response_type=code&client_id=sales-dashboard&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&scope=openid%20profile%20offline_access&state=<random-state>&code_challenge=<pkce-s256-challenge>&code_challenge_method=S256&prompt=consent HTTP/1.1
Host: auth.example.test
~~~

OIDC Core quy định những điều kiện consent cho `offline_access`. Về nguyên tắc, OP **phải có sự chấp thuận phù hợp** cho offline access; khi chưa có cơ sở consent đã được thiết lập và được pháp lý/chính sách chấp nhận, `prompt=consent` thường được yêu cầu. OIDC Core còn ràng buộc việc xin offline access với **response type có thể trả authorization code** theo flow/profile, trừ những điều kiện ngoại lệ được đặc tả. Trong thực tế, Authorization Code + PKCE là lựa chọn phù hợp cho request có nhu cầu RT.

Không nhầm `prompt=consent` với bằng chứng consent đã được user đồng ý: nó là **yêu cầu hiển thị tương tác**, còn user/OP vẫn có thể từ chối.

### 10.2. Không đồng nhất xin offline access với đã nhận RT

| Tình huống | Kết quả có thể xảy ra |
| --- | --- |
| Client không có quyền RT/offline grant theo registration | OP không cấp RT hoặc trả lỗi theo policy |
| User từ chối offline consent | Không có grant offline; có thể phải dừng luồng hoặc tiếp tục online scope theo contract |
| Client public có rủi ro token theft cao | OP có thể yêu cầu RT rotation/sender constraint/lifetime chặt |
| BFF confidential client có token store bảo vệ | Có thể được cấp RT theo chính sách sau consent |
| User logout/rút consent | Cần revoke RT/grant; local session cleanup riêng |
| RT đã rotate và client dùng lại RT cũ | AS có thể phát hiện reuse và revoke token family |

`offline_access` **không** được đưa đến RS làm bằng chứng quyền đọc đơn hàng. RS vẫn phải kiểm tra AT đúng `aud` và `orders.read`; việc user đồng ý offline access không tăng domain privileges.

### 10.3. Refresh grant nằm ở token endpoint, không ở UserInfo

Nếu OP cấp RT, client xin AT mới:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token>&client_id=sales-dashboard
~~~

Ví dụ trên minh họa public-client-style request; confidential client còn phải xác thực theo registration. **Không gửi RT tới UserInfo hoặc `orders-api`**. Refresh token grant có scope/audience restrictions và vòng đời riêng; nó không tự thực hiện OIDC authentication mới với user hiện diện.

### 10.4. Logout không nhất thiết thu hồi ngay mọi AT

RP logout có thể xóa local session và revoke RT/grant. Tuy nhiên JWT access token được RS xác minh offline vẫn có thể được chấp nhận đến `exp` nếu RS không có denylist/session revocation state. OIDC OP logout, RP logout và OAuth revocation là những cơ chế khác nhau cần phối hợp theo SLA.

## 11. Scope `openid` không chứng minh phiên xác thực còn mới

Khi user truy cập RP, OP có thể sử dụng một SSO session đã tồn tại. Điều này phù hợp với OIDC nếu policy cho phép, nhưng ứng dụng ngân hàng hoặc thao tác nhạy cảm có thể yêu cầu user **vừa xác thực gần đây** hoặc bằng phương thức đủ mạnh.

### 11.1. `auth_time`, `max_age` và `prompt`

| Cơ chế | Mục đích | Cách sử dụng an toàn |
| --- | --- | --- |
| `max_age` | Chỉ định thời gian tối đa tính từ lần user xác thực | Gửi trong Authentication Request; RP kiểm tra `auth_time` được trả theo yêu cầu và ngưỡng |
| `auth_time` | Thời điểm end-user được OP xác thực | Không nhầm với `iat` — thời điểm ID token được phát hành |
| `prompt=login` | Yêu cầu OP thực hiện login lại theo ngữ nghĩa OIDC | Đánh giá cùng chính sách OP, không tự coi login mới là mức MFA mong muốn |
| `prompt=none` | Yêu cầu OP không hiện UI | Nếu cần tương tác/login/consent, nhận lỗi OIDC phù hợp; không bỏ kiểm tra |
| `acr_values` | Xin Authentication Context Class Reference theo thứ tự ưu tiên | Chỉ dùng giá trị và assurance contract OP đã thỏa thuận |
| `acr` / `amr` | Claims mô tả ngữ cảnh/phương thức xác thực | Không xem một chuỗi tùy ý do OP phát là đạt assurance nếu không có policy |

Ví dụ request yêu cầu authentication tương đối mới:

~~~http
GET /authorize?response_type=code&client_id=sales-dashboard&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&scope=openid&state=<random-state>&code_challenge=<s256-challenge>&code_challenge_method=S256&max_age=300 HTTP/1.1
Host: auth.example.test
~~~

Nếu RP yêu cầu `max_age=300`, nó cần kiểm tra `auth_time` theo OIDC và xác định khoảng thời gian cho phép, không chỉ thấy token vừa được mint nên tin là user vừa nhập mật khẩu. Trong một hệ thống rủi ro cao, RP có thể cần step-up MFA và kiểm tra `acr` phù hợp contract.

### 11.2. `iat` không phải thời điểm user đăng nhập

Ví dụ:

~~~text
09:00  Alice login tại OP (auth_time).
12:00  RP mở OIDC request, OP dùng SSO session đang có.
12:00  OP cấp ID token mới (iat).
~~~

`iat=12:00` không tự chứng minh Alice vừa xác thực tại 12:00. Nếu nghiệp vụ cần xác thực trong 5 phút gần đây, phải dùng `max_age`/`auth_time` hoặc chính sách assurance tương ứng. Việc dùng `exp` hoặc `iat` thay `auth_time` là lỗi **authentication freshness**.

### 11.3. `prompt=none` và các lỗi đặc thù

RP có thể gửi `prompt=none` để kiểm tra khả năng SSO không cần tương tác. OP có thể trả `login_required`, `consent_required` hoặc `interaction_required` nếu không thể hoàn thành request âm thầm. RP nên đưa user tới interactive flow hợp lệ nếu cần, không dùng `grant_type=password` hoặc tự bỏ consent để “đăng nhập được”.

Không coi response `login_required` là token không hợp lệ, cũng không tự động mở infinite redirect loop. Phân biệt **authentication request cần tương tác** với **access token hết hạn** và **API quyền không đủ**.

## 12. OIDC Discovery và danh sách scope được hỗ trợ

RP thường cấu hình issuer tin cậy, sau đó lấy **OpenID Provider Configuration** qua discovery endpoint thích hợp:

~~~text
https://auth.example.test/.well-known/openid-configuration
~~~

Metadata response minh họa:

~~~json
{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "userinfo_endpoint": "https://auth.example.test/userinfo",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public", "pairwise"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email", "address", "phone", "offline_access"],
  "claims_supported": ["sub", "name", "email", "email_verified", "auth_time"],
  "claims_parameter_supported": true
}
~~~

Đây là ví dụ **khả năng một OP cụ thể**, không phải mọi OP đều có cùng endpoints/scopes/claims. OIDC Discovery yêu cầu OP công bố những thông tin năng lực cốt lõi và hỗ trợ scope `openid`; một số trường như `claims_parameter_supported` có thể không được công bố, và hành vi mặc định phải được hiểu theo đặc tả/contract.

### 12.1. Metadata chỉ được tin khi gắn đúng issuer

Quy trình:

1. RP bắt đầu từ **issuer do administrator/client registration tin cậy**.
2. RP fetch discovery metadata qua HTTPS, kiểm tra TLS chain và hostname.
3. RP xác minh `issuer` trong metadata **đúng expected issuer**; không tự lấy URL mới từ input attacker.
4. RP lấy authorization/token/JWKS/UserInfo endpoints theo metadata đã được tin.
5. RP ràng buộc `state`, client registration, issuer và nonce/PKCE với authorization transaction.
6. Sau token response, RP xác minh ID token `iss` lại bằng expected issuer.

Không chỉ thấy một HTTPS cert hợp lệ tại `attacker.example.test` rồi dùng metadata từ đó làm OP của Alice. TLS xác minh **đúng host được gọi**, chứ không xác minh host ấy có được phép phát ID token cho hệ thống bạn hay không.

### 12.2. `scopes_supported` là thông tin năng lực, không phải grant

Nếu OP quảng bá:

~~~json
{"scopes_supported": ["openid", "profile", "email"]}
~~~

RP biết có thể yêu cầu các scopes đó; **không suy được** rằng `email` sẽ luôn được cung cấp, mọi client đều được xin nó hoặc user đã consent. Client registration, account data, consent, policy và grant mới quyết định outcome.

### 12.3. Custom scope không phải OIDC Core scope

Một tổ chức có thể thêm `groups`, `roles`, `organization`, `tenant.read`, `api://orders/orders.read` hoặc `orders.read`. Chúng có thể là scope theo **profile riêng/nhà cung cấp**, hoặc OAuth API scope. Không xây thư viện kiểm tra `openid roles` theo giả định `roles` là scope chuẩn luôn dùng được ở mọi OP.

Nếu user login thành công nhờ `openid`, không tự đòi role admin từ OIDC `profile`. Muốn dùng RBAC tại API, cần hợp đồng với AS/OP, token claims/SCIM/directory hoặc domain authorization được kiểm soát.

## 13. Phân quyền API: `openid` không phải quyền đọc tài nguyên

Một AS/OP có thể ký nhiều token; tính hợp lệ của chữ ký **không làm mọi token có cùng mục đích**. Trong hệ thống nhiều resource servers, phải kiểm tra:

| Validation ở RS | Câu hỏi |
| --- | --- |
| **Token type/profile** | Đây là OAuth access token được phép dùng tại API, không phải ID token hay RT? |
| **Issuer / signing keys** | Token do AS được API tin tưởng cấp, chữ ký/thuật toán hợp lệ? |
| **Audience** | `aud` có chứa **đúng resource ID** của API này? |
| **Time / status** | `exp`, `nbf` và trạng thái revoke/opaque `active` hợp lệ? |
| **Granted scope** | Token có scope cần thiết như `orders.read` chứ không chỉ `openid`? |
| **Principal/client/actor** | Token mô tả user, service hay delegated actor; contract nào áp dụng? |
| **Domain ACL** | User/service được phép truy cập **đơn hàng cụ thể** và tenant này? |

### 13.1. Tình huống token substitution

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as sales-dashboard / RP
    participant OP as OP
    participant RS as orders-api
    RP->>OP: OIDC Login: scope=openid profile
    OP-->>RP: ID token aud=sales-dashboard + AT UserInfo
    RP->>RS: Authorization: Bearer <id-token> (SAI)
    RS->>RS: Chỉ kiểm tra chữ ký và sub, bỏ token purpose/aud
    RS-->>RP: Có nguy cơ trả dữ liệu trái quyền
    Note over RS: Thiết kế đúng: REJECT ID token và token sai audience
~~~

Nếu một token chỉ có `scope=openid profile` mà API chấp nhận làm `orders.read`, đó là **scope confusion**. Nếu API nhận ID token `aud=sales-dashboard`, đó là **token purpose/audience confusion**. Cả hai không được giải quyết chỉ bằng việc OP hỗ trợ OIDC.

### 13.2. Các phương án tách API access token

Trong thiết kế an toàn, client và AS có thể:

- Cấp một AT **dành cho đúng API** với `aud=orders-api` và `scope=orders.read`, đồng thời nhận ID token dành cho RP.
- Xin token mới cho resource khác bằng một grant/delegation phù hợp; nếu dùng RFC 8693 Token Exchange, AS phải kiểm tra subject/actor/client quyền.
- Dùng profile Resource Indicators (RFC 8707) khi AS hỗ trợ để nêu `resource`, áp allowlist audience.
- Tách AT cho UserInfo và AT cho API khi resource policy yêu cầu.

Không tự sửa JWT payload để thêm `aud=orders-api`: sửa payload làm chữ ký vô hiệu; kể cả ký lại bằng khóa của ứng dụng, token cũng không do AS được RS tin cậy cấp.

### 13.3. Scope chính xác không đồng nghĩa object authorization

~~~text
Alice AT:
  iss = https://auth.example.test
  aud = orders-api
  scope = orders.read

Request: GET /orders/999
Order 999 belongs to tenant shop-b.
Alice belongs to tenant shop-a.

orders-api MUST DENY despite valid issuer/audience/scope.
~~~

`scope` mô tả loại hành động được ủy quyền, còn quyền sở hữu/tenant/ACL thuộc domain. Chẳng hạn `orders.read` của Alice không được xem là wildcard trên tất cả đơn hàng chỉ vì login OP thành công.

## 14. Java/Spring Security: yêu cầu `openid` và xác minh kết quả đăng nhập

Các ví dụ minh họa Spring Boot / Spring Security 6.x. Tên API và behavior của bộ lọc có thể thay đổi theo version; kiểm tra tài liệu chính xác của phiên bản trước khi áp production. **Không viết lại JWT/nonce/PKCE validation thủ công nếu framework đã có giải pháp đúng**.

### 14.1. Cấu hình OAuth2 Login cho backend/BFF

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-op:
            issuer-uri: https://auth.example.test
        registration:
          sales-dashboard:
            provider: company-op
            client-id: sales-dashboard
            client-secret: SECRET_INJECTED_FROM_SECRET_MANAGER
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
~~~

`SECRET_INJECTED_FROM_SECRET_MANAGER` là placeholder cần được thay bằng secret thực sự được inject an toàn, **không commit secret vào YAML hoặc repository**. Đây là **confidential backend client**; SPA/native public client không được nhúng secret rồi khai là confidential.

`openid` làm Spring Security xử lý đăng nhập theo OIDC khi provider/registration hỗ trợ; `profile` và `email` chỉ yêu cầu hồ sơ. Nếu ứng dụng cần `orders.read`, hãy cấu hình **OAuth API authorization** và resource audience phù hợp với AS; không thêm scope vào request rồi tự cho API bỏ qua audience.

### 14.2. SecurityFilterChain OIDC login

~~~java
@Configuration
@EnableWebSecurity
class WebOidcSecurity {
    @Bean
    SecurityFilterChain webChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(Customizer.withDefaults());

        http.logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
~~~

Ví dụ chỉ thiết lập login và local logout cơ bản. Đối với BFF, token cần được giữ **server-side**, browser dùng session cookie `HttpOnly`/`Secure` và `SameSite` phù hợp; bảo vệ CSRF/XSS và kiểm tra origin đối với hành động nhạy cảm. Đoạn `logout()` **không tự chứng minh** OP logout/revoke RT đã được thực hiện; cần thêm integration phù hợp chính sách.

### 14.3. Bật PKCE S256 cho code flow

Với Spring Security phiên bản hỗ trợ:

~~~java
@Bean
OAuth2AuthorizationRequestResolver pkceResolver(
        ClientRegistrationRepository registrations) {

    var resolver = new DefaultOAuth2AuthorizationRequestResolver(
            registrations, "/oauth2/authorization");

    resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

    return resolver;
}
~~~

Tích hợp resolver với `oauth2Login(...authorizationEndpoint(...authorizationRequestResolver(pkceResolver)))` khi cần, và **kiểm tra request thực tế** có `code_challenge_method=S256`. Spring Security có hành vi mặc định khác nhau giữa public/confidential client và từng version; đừng giả định mọi triển khai tự bật S256 cho confidential client.

PKCE bảo vệ **authorization code exchange**, không phải token-purpose validation sau khi đăng nhập. Client vẫn phải xác minh ID token, session/state/nonce và chính sách UserInfo.

### 14.4. Đọc subject và issuer từ OidcUser đã xác minh

~~~java
@GetMapping("/me")
public Map<String, Object> me(
        @AuthenticationPrincipal OidcUser principal) {

    if (principal == null) {
        throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
    }

    OidcIdToken idToken = principal.getIdToken();

    return Map.of(
            "issuer", idToken.getIssuer().toString(),
            "subject", idToken.getSubject(),
            "displayName",
                principal.getFullName() == null
                ? "" : principal.getFullName());
}
~~~

Đoạn code giả định Spring OAuth2 Login đã xác minh ID token, UserInfo và session trước khi tạo `OidcUser`; nếu principal tự dựng từ request, giả định đó **không còn đúng**. Response `/me` minh họa việc lấy identity, không nên công khai `iss`/`sub` cho ứng dụng bên thứ ba ngoài nhu cầu, và không dùng những claims này để tự bỏ qua authorization nghiệp vụ.

### 14.5. Custom OidcUserService: không làm mất validation chuẩn

Nếu cần tạo mapping từ OIDC identity sang user nội bộ:

~~~java
@Bean
OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService(
        ExternalIdentityRepository identities) {

    OidcUserService delegate = new OidcUserService();

    return request -> {
        // Delegate thực hiện OIDC UserInfo handling theo framework.
        OidcUser user = delegate.loadUser(request);
        OidcIdToken idToken = user.getIdToken();

        String issuer = idToken.getIssuer().toString();
        String subject = idToken.getSubject();

        // Không dùng email làm khóa chính, không merge user tự động.
        identities.assertMappedOrApplyOnboardingPolicy(
                issuer, subject);

        return user;
    };
}
~~~

`ExternalIdentityRepository` là domain abstraction giả định. Nếu custom user service trả `OidcUser` mới, phải giữ `sub`/ID token/UserInfo identity và các guarantees của framework; không thay user dựa trên `email` do response khác gửi tới. Ánh xạ user chưa từng gặp phải qua **onboarding policy**, không tự cấp quyền doanh nghiệp chỉ vì OP xác thực hợp lệ.

Để sử dụng bean với `oauth2Login` trong cấu hình phức tạp, cần nối rõ vào `userInfoEndpoint().oidcUserService(...)` theo phiên bản. Không tự override decoder/validator làm mất `iss`/`aud`/time/nonce checks để “tương thích nhiều OP”.

### 14.6. Phân tách resource server API

Một API Spring Resource Server không nên xác thực request bằng ID token của `sales-dashboard`. Cấu hình JWT validator có expected issuer và audience:

~~~java
@Bean
JwtDecoder ordersJwtDecoder() {
    String issuer = "https://auth.example.test";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(issuer)
            .build();

    OAuth2TokenValidator<Jwt> defaultValidator =
            JwtValidators.createDefaultWithIssuer(issuer);
    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "Access token has wrong audience",
                        null));
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    defaultValidator, audience));
    return decoder;
}
~~~

Thêm route authorization:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll());

    http.oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

Trong production, phải bổ sung **access-token profile/type validation**, thuật toán JWS được phép, issuer/JWKS trust, principal type và object-level ACL. `SCOPE_orders.read` là mapping Spring mặc định thường gặp; custom claim formats cần converter có chủ đích. `openid` không thay `orders.read`, và cả hai cũng không thay quyền trên từng order.

## 15. Threat model: scope và OIDC claims bị sử dụng sai

### 15.1. Token substitution: lấy ID token làm quyền API

Một RP có ID token `aud=sales-dashboard` từ OP, rồi gửi:

~~~http
GET /orders/123 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <id-token-for-sales-dashboard>
~~~

Nếu `orders-api` chỉ kiểm tra chữ ký, issuer và `sub` mà bỏ qua token type/audience, API có thể nhận **authentication assertion dành cho RP** làm authorization credential. Giải pháp: RS từ chối ID token, chỉ chấp nhận AT theo token profile đã thỏa thuận, đúng `aud`/scope/ACL. Token được OP ký không tự cấp mọi resource authorization.

### 15.2. Account linking bằng email gây chiếm tài khoản

Hai OpenID Providers khác nhau:

~~~text
OP-A:
  iss = https://auth-a.example.test
  sub = user-A
  email = alice@example.test

OP-B:
  iss = https://auth-b.example.test
  sub = attacker-B
  email = alice@example.test
~~~

Nếu RP chỉ tìm user nội bộ theo email rồi gắn cả hai external identities vào cùng tài khoản, attacker có thể lợi dụng cấu hình OP thứ hai hoặc dữ liệu email chưa xác minh. Phòng vệ: dùng **`(iss, sub)`** làm external identity key, xác minh đúng issuer/registration, không tự merge bằng email và thực hiện account-linking có user proof/policy riêng.

### 15.3. Login CSRF và session mix-up

Attacker có thể cố đưa RP một OIDC callback thuộc **authorization transaction khác**, khiến browser user bị gắn session sai. Chỉ có `scope=openid` không chặn được. RP cần `state` đủ ngẫu nhiên, transaction-bound, PKCE, nonce khi dùng, exact redirect registration và issuer/mix-up defense.

Với nhiều OP, không lấy `iss`/`token_endpoint` từ query callback chưa được xác minh rồi gửi code/verifier tới host lạ. `state` phải trỏ về **expected issuer** và registration đã khởi tạo.

### 15.4. OP discovery/JWKS injection

Một JWT chưa xác minh có JOSE header `jku=https://attacker.example.test/keys`. Nếu RP tải khóa ở đó chỉ vì URL HTTPS có cert hợp lệ, attacker có thể kiểm soát key mà RP tin. Cần **issuer/JWKS URL được cấu hình từ trusted OP metadata** và policy thuật toán cụ thể; không tạo key trust từ nội dung token chưa xác minh.

Discovery JSON có HTTPS không có nghĩa **mọi issuer** được phép đăng nhập. Phải so metadata `issuer` với configured expected issuer và allowlist các OP được phê duyệt.

### 15.5. Claim injection và profile over-trust

Một ứng dụng đọc `email_verified=true` hoặc `groups=["admin"]` từ:

- Request header do browser tự gửi.
- UserInfo JSON lấy từ host không tin.
- JWT ID token chỉ được decode mà không verify signature.
- Query parameter `email` hoặc `role` trong callback.

...rồi tự cấp quyền quản trị. Đây là **claim trust confusion**. Chỉ các claims đến từ OP đã xác minh, theo issuer/token/profile và consent policy, mới được dùng trong quyết định được phép. Với `groups`/`roles` custom, cần mapping/validation chính xác và vẫn thực thi domain authorization.

### 15.6. Over-scoping và quyền riêng tư

RP chỉ cần hiển thị tên nhưng xin:

~~~text
scope=openid profile email address phone offline_access
~~~

Nó đang xin nhiều dữ liệu cá nhân và quyền truy cập dài hạn không cần thiết. Điều này tăng rủi ro khi bị XSS, log leak, database compromise hoặc nhân viên truy cập dữ liệu không hợp lệ.

Giải pháp:

1. Chỉ xin `openid` cho mục tiêu đăng nhập tối thiểu.
2. Xin `profile`/`email` khi thực sự cần trường dữ liệu liên quan và user đã hiểu.
3. Có thể dùng `claims` parameter để yêu cầu một claim cụ thể thay vì toàn bộ nhóm.
4. Không xin `offline_access` chỉ để tránh user phải đăng nhập lại khi không có nghiệp vụ offline.
5. Có data retention, consent withdrawal, encryption và access controls cho profile claims đã lưu.

### 15.7. `email_verified` không phải authorization level

Một người dùng có email verified không tự là:

- Nhân viên nội bộ hoặc thành viên tenant doanh nghiệp.
- Chủ tài khoản ngân hàng hoặc số điện thoại đang sở hữu.
- Người đã vượt MFA/step-up tại thời điểm hiện tại.
- Người được quản trị viên cho phép thao tác đặc quyền.

Nếu RP cần kiểm tra organization membership, phải dựa trên **contract tổ chức** như issuer/tenant directory/claims được phê duyệt và policy cụ thể. Không cấp role admin chỉ vì email kết thúc bằng một domain khi issuer không có bảo đảm quản lý domain tương ứng.

### 15.8. Scope string parsing sai

Không dùng:

~~~java
// KHÔNG DÙNG cho authorization:
boolean grantedOpenId = scopeString.contains("openid");
boolean grantedAdmin = scopeString.contains("admin");
~~~

`myopenid` có thể bị hiểu sai thành `openid`; `notadmin` có thể bị hiểu thành `admin`. Dùng parser scope-token theo RFC 6749 và so sánh **phần tử chính xác**, có phân biệt chữ hoa/chữ thường. Với AT đến RS, ưu tiên scopes đã được AS cấp và framework xác minh (hoặc introspection metadata), không lấy query-requested scope do client tự khai.

### 15.9. Authorization freshness và người dùng đã bị khóa

Alice bị khóa tài khoản tại 10:01; ID token mint ở 10:00 còn hạn tới 10:10, local session RP có thể còn sống. Nếu RP dùng `openid` và `exp` để suy “Alice vẫn hoạt động”, có thể bỏ qua account disable/step-up. Cần session lifecycle và user-status/domain checks theo SLA; access token JWT offline có thể còn hợp lệ đến `exp` nếu không có cơ chế revoke/denylist.

### 15.10. Token leakage dù dùng TLS

HTTPS bảo vệ đường truyền nếu certificate/hostname validation đúng, nhưng không bảo vệ token sau khi:

- Gateway log `Authorization: Bearer ...`.
- Browser JavaScript bị XSS đọc AT/RT trong `localStorage`.
- Native app ghi RT vào plaintext file/backup.
- Developer đưa ID token/claims vào analytics hoặc error report.
- RP gửi token tới redirect URL do attacker điều khiển.

Áp token storage phù hợp client type, BFF khi cần giảm RT exposure ở browser, CSRF defense, XSS mitigation, log redaction, AT TTL và DPoP/mTLS sender constraint khi risk phù hợp. **PKCE và `openid` không phải biện pháp chống replay bearer token sau issuance.**

## 16. Ma trận kiểm thử OIDC scope và bảo mật (50 ca)

Bộ test nên có một OP test với nhiều client registrations, một hoặc hai RPs, OIDC Discovery/JWKS test, UserInfo Endpoint và ít nhất một API như `orders-api`. Tạo token/keys **chỉ cho môi trường test**; không in raw AT/RT/ID token thật ra CI logs.

| ID | Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| O01 | Request `scope=openid`, Code + PKCE, client/grant hợp lệ | OP hoàn tất OIDC flow; RP nhận và verify ID token |
| O02 | Request `scope=openid profile email`, user có claims, consent/policy cho phép | OP có thể trả profile/email qua ID token/UserInfo theo contract |
| O03 | Request chỉ `scope=profile email` | **Không** tự coi là OIDC Authentication Request, không mặc định ID token |
| O04 | Request chỉ `scope=orders.read` | OAuth authorization không phải OIDC login |
| O05 | Request `scope=myopenid` hoặc `OpenID` | Không khớp `openid` nguyên vẹn |
| O06 | `scope=openid` được gửi nhưng redirect URI chưa đăng ký | OP từ chối, không gửi code đến URI lạ |
| O07 | `state` callback không khớp transaction | RP từ chối login/callback |
| O08 | PKCE `code_verifier` sai hoặc thiếu | Token endpoint từ chối; không cấp token |
| O09 | Authorization code đã sử dụng | OP không redeem thành công lần thứ hai |
| O10 | Confidential client có client authentication sai | OP từ chối, dù PKCE đúng |
| O11 | Public client không có client secret nhưng dùng PKCE đúng | Được xử lý theo public-client registration |
| O12 | ID token có `iss` là OP khác ngoài allowlist | RP từ chối dù `sub`/email giống |
| O13 | ID token đúng issuer nhưng signature sai | RP từ chối |
| O14 | ID token `aud` không chứa `client_id` của RP | RP từ chối |
| O15 | ID token quá hạn `exp` | RP từ chối |
| O16 | ID token thiếu claim bắt buộc `sub` hoặc `iat` | RP từ chối theo OIDC validation |
| O17 | Request có `nonce` nhưng ID token chứa nonce khác | RP từ chối |
| O18 | ID token có nhiều audiences và thiếu/`azp` sai theo quy tắc áp dụng | RP từ chối |
| O19 | `max_age=300` nhưng `auth_time` cũ vượt policy | RP từ chối hoặc yêu cầu tương tác lại |
| O20 | RP dùng `iat` thay `auth_time` để kết luận login mới | Test phát hiện authentication freshness bypass |
| O21 | `prompt=none` nhưng chưa có SSO session | OP trả `login_required` hoặc lỗi interaction phù hợp |
| O22 | `profile` được xin nhưng `name` không có | RP có UX/contract xử lý thiếu claim; không tự giả danh |
| O23 | `email` xuất hiện nhưng `email_verified=false` | RP không giả định email đã xác minh |
| O24 | `email` không được trả dù đã xin `email` | RP tuân claim release/consent policy, không tự điền |
| O25 | `address` là JSON object hợp lệ | RP đọc structured claim, không coi như quyền API |
| O26 | `phone` được xin nhưng OP không có phone | RP xử lý thiếu claim, không coi login thất bại nếu không bắt buộc |
| O27 | UserInfo response `sub` khớp ID token `sub` | RP có thể dùng claims được phép |
| O28 | UserInfo `sub=user-B` còn ID token `sub=user-A` | RP **không dùng** UserInfo response |
| O29 | UserInfo response không có `sub` | RP từ chối dùng response như UserInfo hợp lệ |
| O30 | UserInfo AT sai/expired hoặc không được phép tại UserInfo | UserInfo từ chối theo OAuth token policy |
| O31 | UserInfo URL từ một issuer khác hoặc do user chỉ định | RP không chuyển AT tới endpoint chưa tin |
| O32 | UserInfo được ký nhưng signature sai theo contract | RP từ chối khi signed UserInfo được yêu cầu |
| O33 | `claims` JSON yêu cầu `auth_time` thiết yếu và OP hỗ trợ | OP xử lý theo policy, RP kiểm tra response thật |
| O34 | RP đánh dấu `email` essential nhưng OP không có email | RP xử lý thiếu claim/lỗi; không tự bịa giá trị |
| O35 | OP quảng bá `scopes_supported` có `email` nhưng user không consent | Không được tiết lộ email trái consent/policy |
| O36 | RP xin `offline_access` nhưng thiếu consent/policy | Không mặc định cấp refresh token |
| O37 | RP được cấp RT và refresh đúng client binding | AS cấp token mới trong giới hạn grant |
| O38 | RT bị revoke hoặc reused sau rotation | AS từ chối/reuse-detect theo policy |
| O39 | User logout RP nhưng AT JWT cũ còn hạn | RS thực thi TTL/revocation SLA đã thiết kế |
| O40 | ID token `aud=sales-dashboard` gửi làm bearer tới `orders-api` | RS từ chối token type/audience |
| O41 | AT đúng signature nhưng `aud=UserInfo` gửi tới orders | RS từ chối sai resource |
| O42 | AT `aud=orders-api`, `orders.read` nhưng order khác tenant | RS từ chối theo object ACL |
| O43 | AT có `scope=openid` nhưng không có `orders.read` | RS từ chối API authorization |
| O44 | Client gửi `X-User: alice` mà token principal khác | RS không thay user từ untrusted header |
| O45 | Hai OP có cùng `sub` nhưng `iss` khác | RP lưu hai external identities tách biệt |
| O46 | OP dùng pairwise `sub` khác giữa hai RP sectors | Không tự merge identity chỉ vì email giống |
| O47 | User đổi email, `sub` giữ ổn định | RP không tạo/chiếm user account sai vì email mới |
| O48 | Token issuer/JWKS URL lấy từ `jku` attacker | RP/RS không sử dụng untrusted JWK source |
| O49 | Multi-AS callback thuộc issuer khác transaction | RP từ chối mix-up, không gửi code/PKCE verifier sang AS khác |
| O50 | Gateway/analytics ghi ID token, RT, UserInfo PII hoặc Basic auth | Redaction/privacy tests phát hiện vi phạm |

### 16.1. Test phân biệt OIDC với OAuth

Tạo **hai client requests** với cùng issuer, redirect, client auth và PKCE:

~~~text
Test A:
  scope = "orders.read"
  expected = OAuth authorization response, không suy id_token/login theo OIDC

Test B:
  scope = "openid"
  expected = OIDC Authentication Request, Code Flow có ID token khi grant hợp lệ
~~~

Không thay đổi cả redirect URI, client type, session và AS ở hai test rồi kết luận do `openid`: hãy cô lập điều kiện. Nếu AS có behavior riêng ngoài chuẩn, ghi rõ extension/profile chứ không biến nó thành quy tắc chung của OIDC.

### 16.2. Test ID token validation phải có token dương

Một RP test luôn từ chối vì JWKS không truy cập được **không chứng minh** nó đang kiểm tra `aud`, `iss`, `nonce` hay `azp` đúng. Chuẩn bị token:

~~~text
IDT1: valid signature, iss=trusted, aud=RP, exp hợp lệ
      → login được khi state/nonce/flow hợp lệ.

IDT2: giống IDT1 nhưng aud=other-RP
      → từ chối do audience.

IDT3: giống IDT1 nhưng iss=untrusted
      → từ chối do issuer.

IDT4: giống IDT1 nhưng nonce=wrong
      → từ chối do nonce khi đã yêu cầu.
~~~

Tương tự, test UserInfo `sub` mismatch cần chắc chắn HTTP request UserInfo **đã được xác thực** bằng AT hợp lệ và response đúng format; nếu UserInfo luôn 401 vì token sai thì chưa kiểm chứng `sub` check.

### 16.3. Test pairwise subject và liên kết tài khoản

Tạo hai registration có cùng sector và khác sector theo khả năng OP test:

~~~text
Same user, same OP, pairwise same sector:
  expected sub follows OP pairwise policy.

Same user, same OP, different sectors:
  sub may differ — no automatic cross-RP merge.

Same email, different issuers:
  external identities must remain distinct unless user links them
  through a separately-authorized process.
~~~

Không viết test cứng “tất cả OP phải trả pairwise sub khác” vì OP có thể dùng public subject. Điều phải đảm bảo là **RP không dựa trên email làm khóa xác thực bất biến** và tuân theo `subject_types_supported`/client registration contract.

### 16.4. Test scope consent và quyền riêng tư

Với user chỉ có tên hiển thị, không có phone/address:

1. RP xin `openid` và không bị buộc tiết lộ contact PII ngoài nhu cầu.
2. RP xin `openid profile` và hoạt động khi một số profile claims thiếu.
3. RP xin `openid phone` nhưng OP không có phone; RP không tự điền số giả.
4. RP xin `openid email` nhưng user từ chối công bố email; OP tuân policy.
5. RP xin `offline_access` không có consent thích hợp; RT không được tự cấp.
6. Sau consent withdrawal, cache UserInfo/RT được xử lý đúng chính sách.

Kiểm tra **logs, traces, analytics, caches, database exports và crash reports**, không chỉ HTTP response. Nơi chứa claims cá nhân cũng cần có scope/retention policy, encryption và audit phù hợp.

## 17. Năm tình huống áp dụng trong hệ thống thực tế

### Tình huống A: Client xin `profile email` nhưng không nhận ID token

Ứng dụng Java đăng ký với OP, gửi Authorization Code Flow:

~~~text
response_type = code
scope = profile email
~~~

Sau khi đổi code, AS trả OAuth access token nhưng không trả ID token. Developer cho rằng OP lỗi vì metadata công bố hỗ trợ `profile` và `email`.

**Chẩn đoán:** Request **không có `openid`**, nên không phải OIDC Authentication Request. `profile`/`email` không tự yêu cầu xác thực user. Đừng suy ID token luôn xuất hiện chỉ vì provider là OP có hỗ trợ OIDC.

**Giải pháp:** Đối với đăng nhập, gửi `scope=openid profile email` và các tham số Code+PKCE, state/nonce theo client policy; RP xác minh ID token trước khi tạo session. Nếu cần quyền `orders.read`, thiết kế API authorization/audience riêng, không lấy `profile` thay scope nghiệp vụ.

### Tình huống B: UserInfo trả `sub` khác nhưng email giống

`sales-dashboard` xác minh ID token của Alice:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice-742",
  "aud": "sales-dashboard"
}
~~~

Đây là phần claims minh họa, không phải ID token JWT đầy đủ. Sau đó hệ thống lấy UserInfo bằng AT nhưng cache/proxy trả response:

~~~json
{
  "sub": "bob-991",
  "email": "alice@example.test"
}
~~~

**Chẩn đoán:** UserInfo data thuộc một subject khác. Email giống **không hợp thức hóa** response. Lỗi có thể đến từ token/session mixing hoặc cache key thiếu subject/issuer.

**Giải pháp:** RP phải so sánh chính xác UserInfo `sub` với ID token `sub`, **không sử dụng response** khi khác. Kiểm tra UserInfo AT và cache key, session isolation, issuer binding, log correlation an toàn và không làm user mapping chỉ bằng email.

### Tình huống C: Ứng dụng xin `openid email` rồi tự cấp quyền nhân viên

Một ứng dụng quản trị nhận:

~~~json
{
  "sub": "external-user-39",
  "email": "manager@company.example.test",
  "email_verified": true
}
~~~

Developer gán `ROLE_ADMIN` cho mọi email có đuôi `@company.example.test`.

**Chẩn đoán:** OIDC `email` chỉ yêu cầu claim và `email_verified` phản ánh xác minh email theo OP; **không phải bằng chứng membership/authorization trong tenant**. Nếu OP đăng ký cho người ngoài hoặc domain có email bị tái phân bổ, logic này có thể cấp quyền sai.

**Giải pháp:** Dùng `iss` + `sub` làm external identity key, áp policy quản trị nhân sự/directory/tenant/roles có nguồn tin cậy, kiểm tra account status và cấp quyền theo mapping được phê duyệt. Không tự nâng quyền từ một scope/claim hồ sơ.

### Tình huống D: User muốn đồng bộ nền và RT bị lộ

Web SPA xin:

~~~text
scope=openid profile email offline_access
~~~

OP cấp RT theo policy. SPA lưu RT không bảo vệ; một script XSS lấy RT và dùng token endpoint để xin AT mới cả khi Alice đóng browser.

**Chẩn đoán:** `offline_access` xin khả năng truy cập khi user không hiện diện, nhưng **không làm RT an toàn hơn**. PKCE khi cấp token ban đầu không chặn attacker dùng RT đã bị đánh cắp.

**Giải pháp:** Chỉ xin `offline_access` khi cần, ưu tiên BFF nếu phù hợp, quản lý RT bằng rotation/sender constraint và revocation, hạn chế lifespan và scopes/audience, thực hiện XSS defense/log redaction và có quy trình logout/incident response. Không giả định xóa local storage đã vô hiệu bản sao RT bên ngoài.

### Tình huống E: Người dùng đã login nhưng thao tác yêu cầu xác thực mới

Alice đăng nhập tại OP lúc 08:00. Đến 16:00, RP nhận một ID token mới thông qua SSO rồi cho Alice thay đổi thông tin thanh toán nhạy cảm; ứng dụng chỉ dựa vào `iat` của token phát hành lúc 16:00.

**Chẩn đoán:** `iat` không phản ánh thời điểm user vừa xác thực; OP có thể tái sử dụng SSO session. `openid` là yêu cầu OIDC, không tự yêu cầu login mới hoặc MFA.

**Giải pháp:** RP yêu cầu `max_age` phù hợp, kiểm tra `auth_time`, sử dụng step-up/chính sách `acr`/`amr` đã thỏa thuận và kiểm tra authorization domain trước khi thực hiện thao tác. Với hành động nhạy cảm, không dựa vào “ID token vừa phát hành” như bằng chứng authentication freshness.

## 18. Checklist triển khai `openid` và OIDC scope

### 18.1. OIDC Authentication Request

1. **Đúng mục đích:** Client có cần xác thực end-user hay chỉ xin OAuth access token cho API?
2. **Đúng scope:** Request đăng nhập có chứa `openid` nguyên vẹn, đúng case và phân tách space-delimited scopes?
3. **Least privilege:** Chỉ xin `profile`/`email`/`address`/`phone` khi có mục đích rõ; không xin toàn bộ PII theo mặc định?
4. **Offline access:** Chỉ xin `offline_access` khi cần truy cập khi user vắng mặt, có consent/policy thích hợp?
5. **Đúng OP:** Trusted issuer/discovery/JWKS/token/UserInfo endpoints được cấu hình và verify TLS/issuer?
6. **Code flow:** Authorization Code + PKCE S256 được bật, redirect URI đăng ký chặt và callback kiểm tra `state`?
7. **Nonce/mix-up:** Nonce khi dùng/được yêu cầu, expected issuer và transaction binding được xác minh?
8. **Auth freshness:** Có yêu cầu `max_age`/`auth_time` hoặc `acr` khi nghiệp vụ cần user xác thực gần đây/mức assurance?

### 18.2. ID token và UserInfo

9. **ID token:** RP verify signature/alg/keys, `iss`, `sub`, `aud`, `exp`, `iat` và `azp`/`nonce`/`auth_time` khi áp dụng?
10. **Token purpose:** RP dùng ID token để tạo session, không gửi ID token như AT tới API?
11. **External identity:** Định danh RP bằng `(issuer, subject)` thay vì email đơn lẻ?
12. **Pairwise subject:** RP không tự suy `sub` giống nhau ở các sector/issuers?
13. **UserInfo:** UserInfo endpoint và AT phải thuộc trust context phù hợp; RP so sánh UserInfo `sub` **khớp ID token `sub`**?
14. **Claim release:** Ứng dụng chịu được các profile/email/phone/address claims thiếu theo contract?
15. **Claim verification:** Phân biệt `email` và `email_verified`, không dùng contact claim như RBAC/tenant proof?
16. **Claims parameter:** Khi dùng `claims`/`essential`, kiểm tra OP hỗ trợ và không tự giả định dữ liệu buộc được phát?

### 18.3. OAuth API authorization và token lifecycle

17. **Audience:** RS chỉ chấp nhận AT có expected `aud` của chính mình?
18. **Scope:** `openid` không cấp quyền `orders.read` hoặc quyền quản trị; API dùng granted scope đúng action?
19. **Domain ACL:** Token hợp lệ vẫn phải kiểm tra tenant/owner/role/record constraints?
20. **Token format:** JWT signature/JWKS hoặc opaque introspection từ AS tin cậy, với thời hạn/revocation policy?
21. **Refresh:** RT chỉ gửi AS token endpoint; rotation, replay detection, single-flight và revocation khi có RT?
22. **Logout:** RP session, OP session, RT/grant và AT còn hạn được xử lý theo những cơ chế/SLA khác nhau?
23. **Sender constraint:** Nếu dùng DPoP/mTLS-bound AT, RS kiểm tra proof/certificate binding ngoài scope/audience?

### 18.4. Vận hành và kiểm thử

24. **Secure transport:** HTTPS đúng certificate/hostname, không có trust-all, không forward token/secret sang host lạ?
25. **PII minimization:** Consent, scope, retention, encryption, data access audit cho claims cá nhân đã lưu?
26. **Logs:** Không xuất raw ID token, AT/RT, authorization code, PKCE verifier, client secret, UserInfo PII vào logs/traces?
27. **Negative tests:** Có đủ test thiếu `openid`, sai issuer/aud/nonce, UserInfo sub mismatch, email linking, offline consent và API token confusion?
28. **Positive tests:** Mỗi negative test có control flow hợp lệ để chứng minh validation đúng, không phải hệ thống “luôn 401” vì JWKS/TLS lỗi?

## 19. Câu hỏi tự kiểm tra

**Câu 1. Vì sao `scope=openid` khác `scope=profile`?**

`openid` là dấu bắt buộc của **OIDC Authentication Request**. `profile` xin một nhóm end-user claims và **không tự** biến OAuth request thành OIDC. Đăng nhập OIDC cần `openid` cùng flow và token validation phù hợp.

**Câu 2. `openid` có cấp `orders.read` cho resource server không?**

Không. `openid` phục vụ OIDC authentication. Quyền API cần OAuth access token dành cho đúng resource, granted scope như `orders.read` và domain authorization ở RS.

**Câu 3. Xin `openid profile email` có bắt buộc ID token chứa `name`, `email` không?**

Không. Các scope yêu cầu nhóm claims; dữ liệu có thể được trả qua UserInfo hoặc ID token tùy OP/flow/consent, và có thể vắng mặt. RP phải xử lý thiếu claims theo contract.

**Câu 4. Để biết user nào đã đăng nhập, nên dùng `email` hay `iss` + `sub`?**

Ưu tiên **`(iss, sub)`** sau khi ID token được xác minh. Email có thể đổi hoặc trùng giữa issuers; `email_verified` không làm email thành định danh bất biến.

**Câu 5. Một UserInfo Response có `sub` khác ID token nhưng cùng email. Có được dùng không?**

Không. RP phải từ chối sử dụng UserInfo Response nếu `sub` không khớp chính xác ID token `sub` của session.

**Câu 6. `scope=openid offline_access` có bảo đảm nhận refresh token không?**

Không. OP/AS còn áp consent, client registration, grant/response type và security policy. RT có lifetime, rotation/sender constraint và revocation độc lập.

**Câu 7. Khi ID token chứa `email_verified=true`, có thể tự gán role nhân viên hay admin không?**

Không. Đây là thông tin xác minh email theo OP, không phải quyền công ty/domain. RBAC/tenant cần nguồn và chính sách authorization được phê duyệt.

**Câu 8. `max_age` có tác dụng gì?**

Nó yêu cầu độ mới tối đa của end-user authentication. RP phải kiểm tra `auth_time`/ngữ nghĩa OIDC phù hợp, không dùng `iat` của ID token như thời gian user vừa login.

**Câu 9. Nếu chỉ thấy `iat` vừa mới cập nhật, có chắc user vừa vượt MFA không?**

Không. ID token có thể được cấp từ SSO session cũ. Để đảm bảo MFA/freshness, cần contract assurance `acr`/`amr` và thời điểm `auth_time`/`max_age`, tùy hệ thống.

**Câu 10. Có thể gửi ID token OIDC làm bearer token tới API vì ID token cũng là JWT ký đúng không?**

Không. ID token có `aud` là RP/client, không phải API. RS phải yêu cầu OAuth AT đúng purpose, issuer, audience, scope, time và ACL.

**Câu 11. Khi `scopes_supported` có `email`, có chắc mọi user đều có email?**

Không. Đây chỉ là metadata năng lực; OP có thể không có dữ liệu hoặc không công bố vì consent/policy. RP phải xử lý claim vắng mặt.

**Câu 12. Pairwise `sub` có ý nghĩa gì?**

OP có thể tạo `sub` khác nhau giữa các clients/sector identifiers để giảm khả năng cross-RP correlation. RP không được ghép identity giữa các sectors chỉ bằng `sub` hoặc email theo suy đoán.

**Câu 13. Vì sao cần kiểm tra `aud` ở RS dù ID token/AT đều do cùng OP cấp?**

Một issuer có thể cấp token cho nhiều recipients. `aud` ngăn token dành cho UserInfo/client/API A được chấp nhận tại API B, giảm token-substitution và confused-deputy risk.

**Câu 14. `claims` request parameter có ép OP cung cấp `email` ngay cả khi user từ chối không?**

Không. `claims`/`essential` biểu diễn yêu cầu của client; OP vẫn phải áp data availability, consent và policy. Client phải kiểm tra kết quả thực tế và xử lý lỗi/thiếu claim đúng cách.

**Câu 15. Mỗi lần dùng `openid` có bắt end-user nhập lại mật khẩu không?**

Không. OP có thể dùng session đã xác thực; nếu cần freshness/step-up, RP phải chỉ định và xác minh `max_age`/`auth_time` hoặc assurance policy riêng.

## 20. Tài liệu chuẩn tham khảo

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): Authentication Request, scope `openid`, Standard Claims, `claims`, ID token, UserInfo, offline access và validation rules.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): `.well-known/openid-configuration`, issuer, JWKS, `scopes_supported`, `claims_supported` và endpoint metadata.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): `scope` syntax/semantics, authorization grants, client/AS/RS roles, access/refresh tokens.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE `S256` cho Authorization Code Flow.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth security BCP, chống token replay, refresh rotation, tránh ROPC/implicit.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, `exp`, `iat` và JWT claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): token type/algorithm/key confusion và hướng dẫn JWT validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): phân biệt JWT OAuth AT và OIDC ID token theo token profile.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): giới hạn resource/audience khi xin AT.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): xin token cho resource/actor khác theo AS authorization.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh opaque access token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi RT/AT và grants theo policy.
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705) và [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) và [Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): phân biệt OP/RP logout với token revocation.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC login, client registration, OidcUser và ID token validation.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): quản lý authorized client và outbound AT.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/JWKS, audience và scope validation.

**Điểm cần ghi nhớ:** **`openid` là scope bắt buộc báo cho OpenID Provider rằng client đang yêu cầu OIDC authentication.** Các scope `profile`, `email`, `address`, `phone` chỉ xin nhóm user claims; `offline_access` xin quyền truy cập khi user không hiện diện nhưng không tự bảo đảm RT. **ID token** được RP xác minh để nhận diện end-user theo **`iss` + `sub`**, còn **UserInfo** phải có `sub` trùng ID token và có thể thiếu các claims đã yêu cầu. **Access token** phục vụ OAuth resource authorization với audience/scope/ACL riêng; không dùng ID token hay `openid` để vượt quyền API. Triển khai an toàn cần Code+PKCE, expected issuer, state/nonce/ID-token validation, consent và data minimization, authentication freshness, token lifecycle và kiểm tra quyền ở resource server.
