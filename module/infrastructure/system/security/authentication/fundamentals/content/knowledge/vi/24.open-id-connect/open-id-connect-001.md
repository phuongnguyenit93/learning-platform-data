# OpenID Connect là gì? — Lớp xác thực danh tính trên OAuth 2.0

> **Chương:** OpenID Connect  
> **Chủ đề:** OpenID Connect là gì  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giới thiệu OpenID Connect (OIDC), các vai trò và luồng giao thức, ID Token, claim, xác minh token, quản lý phiên và các ranh giới tin cậy khi tích hợp đăng nhập liên kết.

## 1. OpenID Connect là gì?

**OpenID Connect (OIDC)** là một lớp định danh (identity layer) được xây dựng trên OAuth 2.0. OIDC cho phép một ứng dụng biết kết quả xác thực của người dùng từ một nhà cung cấp danh tính (OpenID Provider, OP) theo một giao thức có cấu trúc, đồng thời nhận các claim về subject và ngữ cảnh đăng nhập theo phạm vi được yêu cầu.

Ví dụ, Mai truy cập nền tảng học tập và chọn “Đăng nhập bằng tài khoản trường”. Nền tảng học tập chuyển trình duyệt tới OpenID Provider của trường. Người dùng xác thực bằng passkey hoặc phương thức được trường hỗ trợ. Sau đó, OP trả authorization code về callback đã đăng ký. Nền tảng học tập đổi code tại token endpoint, xác minh ID Token, ánh xạ danh tính sang account nội bộ rồi tạo session cục bộ.

OIDC giải quyết câu hỏi **“Người dùng đã được xác thực là subject nào tại issuer nào?”**. OAuth 2.0 chủ yếu giải quyết câu hỏi **“Client được phép truy cập tài nguyên nào, trong phạm vi nào?”**. OIDC dùng các cơ chế OAuth 2.0 để thực hiện flow, nhưng bổ sung định dạng và quy tắc xác thực danh tính, trong đó quan trọng nhất là ID Token.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt OIDC với OAuth 2.0 và hiểu vai trò của ID Token, Access Token.
2. Nhận diện OP, RP, client, user agent, authorization endpoint, token endpoint và UserInfo endpoint.
3. Mô tả Authorization Code Flow với PKCE và các bước xác minh callback.
4. Kiểm tra ID Token: chữ ký, issuer, audience, thời hạn, nonce và claim liên quan.
5. Hiểu Discovery, JWKS, signing key rotation và thuật toán được phép.
6. Phân biệt scope, claim, UserInfo và dữ liệu profile.
7. Ánh xạ danh tính ngoài vào account nội bộ bằng issuer + subject.
8. Đánh giá authentication context, MFA, auth_time, session và logout.
9. Nhận diện token substitution, code interception, login CSRF, open redirect, issuer mix-up và các lỗi triển khai thường gặp.

## 2. OIDC khác OAuth 2.0 như thế nào?

OAuth 2.0 là framework ủy quyền. Nó cho phép client nhận access token để gọi resource server theo scope và audience được cấp. OAuth 2.0 tự thân không định nghĩa một cách chuẩn hóa để client xác minh danh tính người dùng cuối.

OIDC bổ sung các thành phần xác thực, bao gồm:
- Scope `openid` để yêu cầu một OIDC authentication request.
- **ID Token** chứa các claim về lần xác thực và subject.
- Quy tắc xác minh issuer, audience, signature, thời gian và nonce.
- UserInfo endpoint để lấy các claim profile bổ sung khi được cấp quyền.
- Discovery metadata và các quy tắc cấu hình OpenID Provider.
- Các tham số và claim phục vụ xác thực mới hoặc yêu cầu ngữ cảnh xác thực.

| Khía cạnh | OAuth 2.0 | OpenID Connect |
| --- | --- | --- |
| Mục tiêu chính | Ủy quyền truy cập tài nguyên | Xác thực danh tính và có thể dùng quyền OAuth để gọi API |
| Token cốt lõi | Access Token | ID Token; thường có thể có Access Token |
| Subject người dùng | Không có chuẩn identity chung chỉ từ OAuth | ID Token có `sub` trong phạm vi `iss` |
| Scope | Diễn tả quyền truy cập theo authorization server | Có scope `openid` và có thể thêm scope profile/email |
| UserInfo | Không phải endpoint bắt buộc của OAuth core | Endpoint OIDC tiêu chuẩn tùy claim được cấp |
| Xác minh đăng nhập | Không nên suy ra chỉ từ access token | Theo quy tắc OIDC cho ID Token và authentication response |

**Không dùng Access Token bất kỳ như bằng chứng đăng nhập.** Access Token có thể là opaque token, hoặc JWT dành cho một API. Resource server kiểm tra token theo audience và scope của nó; client dùng ID Token theo OIDC để xác nhận kết quả authentication cho chính client đó.

## 3. Các vai trò trong OIDC

| Thành phần | Tên OIDC/OAuth | Vai trò |
| --- | --- | --- |
| Người dùng | End-User | Người thực hiện đăng nhập. |
| OpenID Provider | OP / Authorization Server | Xác thực người dùng, phát hành ID Token và token theo flow. |
| Relying Party | RP / OAuth Client | Ứng dụng yêu cầu xác thực và tiêu thụ kết quả OIDC. |
| User Agent | Browser hoặc native user agent | Chuyển hướng giữa RP và OP; không phải nguồn tự xác nhận token. |
| Resource Server | API | Nhận Access Token và kiểm tra quyền/audience của API. |
| Discovery document | Provider metadata | Công bố issuer, endpoints, JWKS URI và capabilities. |
| JWKS endpoint | JSON Web Key Set | Cung cấp public keys để RP xác minh chữ ký token. |

~~~mermaid
flowchart LR
    U["End-User"] --> B["Browser / User Agent"]
    B -->|"Authorization request"| OP["OpenID Provider"]
    OP -->|"Authentication"| U
    OP -->|"Code / ID Token"| B
    B -->|"Callback"| RP["Relying Party"]
    RP -->|"Token request"| OP
    OP -->|"ID Token + Access Token"| RP
    RP -->|"Access Token"| API["Resource Server"]
    RP --> S["Local session"]
~~~

OP chịu trách nhiệm xác thực theo chính sách của mình. RP chịu trách nhiệm xác minh kết quả, ánh xạ subject, quyết định tạo session và phân quyền ứng dụng. Resource Server kiểm tra Access Token dành cho API; nó không nên tin rằng một client đã xác minh ID Token thay cho việc kiểm tra token của API.

## 4. ID Token, Access Token và Refresh Token

Ba loại token có mục đích khác nhau.

### ID Token

ID Token là bằng chứng có cấu trúc về một sự kiện xác thực OIDC, được phát hành cho client/RP. ID Token thường là JWT ký số, chứa các claim như:

- `iss`: issuer đã phát hành token.
- `sub`: định danh subject trong phạm vi issuer.
- `aud`: audience, phải bao gồm client ID của RP.
- `exp`: thời điểm hết hạn.
- `iat`: thời điểm phát hành.
- `auth_time`: thời điểm người dùng được xác thực, nếu được yêu cầu/phát hành.
- `nonce`: giá trị ràng buộc với authentication request, nếu RP gửi nonce.
- `acr`, `amr`: ngữ cảnh/phương thức xác thực nếu OP cung cấp theo hợp đồng.

ID Token dành cho RP đã được nêu trong audience. Không gửi ID Token cho API như Access Token trừ khi một giao thức riêng định nghĩa rõ việc đó.

### Access Token

Access Token là credential được dùng để gọi resource server. Nó có thể là JWT hoặc opaque string. Audience, scope và chính sách phát hành xác định API nào được phép chấp nhận token. Client không nên tự diễn giải mọi Access Token như profile hoặc identity assertion.

### Refresh Token

Refresh Token được dùng tại token endpoint để xin token mới theo policy. Nó thường nhạy cảm hơn Access Token do thời hạn và khả năng cấp token tiếp theo. Cần lưu trữ an toàn, rotation hoặc sender constraint khi được hỗ trợ, phát hiện reuse và thu hồi token family theo chính sách.

| Token | Người tiêu thụ chính | Mục đích |
| --- | --- | --- |
| ID Token | RP/client | Xác nhận subject và kết quả authentication |
| Access Token | Resource Server | Truy cập API theo audience/scope |
| Refresh Token | Token Endpoint | Xin token mới khi đủ điều kiện |

## 5. Scope và claim trong OIDC

Một OIDC authentication request cần có scope `openid`. Các scope tiêu chuẩn khác có thể yêu cầu nhóm claim profile:

| Scope | Claim thường liên quan |
| --- | --- |
| `openid` | Bắt buộc để yêu cầu OIDC authentication |
| `profile` | name, given_name, family_name, picture, locale, zoneinfo và các claim profile khác |
| `email` | email, email_verified |
| `address` | address |
| `phone` | phone_number, phone_number_verified |
| `offline_access` | Có thể yêu cầu Refresh Token theo điều kiện và policy của OP |

Scope cho biết client yêu cầu loại quyền/claim nào; OP có thể chỉ cấp một phần theo consent, policy hoặc dữ liệu sẵn có. Không được giả định yêu cầu `email` đồng nghĩa chắc chắn nhận email, hoặc `email_verified=true` có nghĩa RP có thể tự cấp membership.

### Claim là gì?

Claim là một thuộc tính về subject hoặc authentication event. Ví dụ:
- `sub` là định danh subject.
- `email` là địa chỉ email.
- `email_verified` là trạng thái xác minh email theo semantics của OP.
- `name` là tên hiển thị.
- `auth_time` là thời điểm xác thực.
- `acr` và `amr` mô tả authentication context/method theo cách OP định nghĩa hoặc đã thỏa thuận.

RP nên yêu cầu và lưu tối thiểu các claim cần thiết. Claim profile có thể là dữ liệu cá nhân; cần kiểm soát quyền truy cập, retention và mục đích sử dụng.

## 6. Discovery và cấu hình OpenID Provider

OIDC Discovery cho phép RP tìm metadata của OP từ issuer đã biết. Metadata thường công bố:
- `issuer`;
- `authorization_endpoint`;
- `token_endpoint`;
- `userinfo_endpoint`;
- `jwks_uri`;
- supported response types, subject types, signing algorithms, scopes và capabilities khác.

Ví dụ metadata rút gọn:

~~~json
{
  "issuer": "https://id.example.edu",
  "authorization_endpoint": "https://id.example.edu/authorize",
  "token_endpoint": "https://id.example.edu/token",
  "userinfo_endpoint": "https://id.example.edu/userinfo",
  "jwks_uri": "https://id.example.edu/.well-known/jwks.json",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public", "pairwise"],
  "id_token_signing_alg_values_supported": ["RS256", "ES256"]
}
~~~

Đây là dữ liệu minh họa. RP phải lấy metadata từ issuer đã được cấu hình và xác minh rằng trường `issuer` trong document khớp chính xác issuer mong đợi. Không nhận issuer URL tùy ý từ query string hoặc người dùng rồi tự động tải metadata; cách đó có thể tạo SSRF, issuer mix-up hoặc tin một OP giả.

### Cấu hình tin cậy

Một cấu hình RP thường cần:
- issuer chính xác;
- client ID;
- client authentication method và secret/private key nếu là confidential client;
- redirect URI được đăng ký;
- danh sách signing algorithm được phép;
- endpoint và JWKS cache policy;
- scope/claim tối thiểu;
- policy về auth_time, acr/amr, session và logout.

Client secret hoặc private key phải nằm trong secret manager hoặc kho bí mật được bảo vệ, không đưa vào source code, browser bundle hoặc log.

## 7. JWKS và xác minh khóa ký

OP thường công bố public signing keys tại `jwks_uri`. RP dùng các key này để xác minh chữ ký ID Token. JWKS có thể chứa nhiều key trong giai đoạn rotation.

Các trường thường gặp:
- `kid`: key ID dùng để chọn key tương ứng.
- `kty`: loại khóa.
- `use`: mục đích sử dụng nếu có.
- `alg`: thuật toán nếu có.
- `n`, `e` cho RSA hoặc các tham số public key phù hợp với loại khóa.

RP cần:
1. Chỉ tải JWKS từ URI trong metadata của issuer tin cậy.
2. Chọn key phù hợp với `kid` và thuật toán được cấu hình.
3. Xác minh chữ ký bằng thư viện JWT/OIDC đáng tin cậy.
4. Không chấp nhận thuật toán ngoài allowlist hoặc thuật toán do token tự chọn trái policy.
5. Cache JWKS có thời hạn; refresh có giới hạn khi gặp kid chưa biết.
6. Hỗ trợ rotation có kiểm soát và có quy trình xử lý key compromise.

Nếu `kid` không tìm thấy, RP có thể refresh JWKS theo policy rồi thử lại một lần có giới hạn. Không tải URL key tùy ý từ JWT header. Khi OP xoay khóa, key cũ có thể cần giữ trong một giai đoạn để xác minh token đã phát hành nhưng chưa hết hạn. Khi key bị compromise, cần quy trình khẩn cấp để ngừng tin key và xử lý session/token bị ảnh hưởng.

## 8. Authorization Code Flow với PKCE

**Authorization Code Flow** là flow phổ biến cho ứng dụng web và native app hiện đại. Browser nhận authorization code ngắn hạn; RP đổi code tại token endpoint qua back channel. PKCE ràng buộc code với client đã khởi tạo giao dịch, giúp giảm nguy cơ code interception.

~~~mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant RP as Relying Party
    participant OP as OpenID Provider
    U->>B: Chọn đăng nhập
    B->>RP: Bắt đầu login
    RP->>RP: Tạo state, nonce, code_verifier
    RP-->>B: Redirect + code_challenge
    B->>OP: Authorization request (scope=openid)
    OP->>U: Xác thực / MFA
    U->>OP: Hoàn tất xác thực
    OP-->>B: Redirect callback + code + state
    B->>RP: Callback
    RP->>RP: Kiểm tra state và pending transaction
    RP->>OP: Token request + code_verifier
    OP-->>RP: ID Token + Access Token
    RP->>RP: Verify ID Token, map identity
    RP->>RP: Tạo local session
~~~

### Các bước triển khai

1. RP tạo `state` ngẫu nhiên, `nonce` ngẫu nhiên và PKCE `code_verifier`.
2. RP lưu chúng trong một pending transaction ngắn hạn, gắn với browser/session khởi tạo.
3. RP tính `code_challenge` theo PKCE S256 và chuyển browser tới authorization endpoint.
4. Authorization request gồm client_id, redirect_uri chính xác, response_type=code, scope có openid, state, nonce, code_challenge và code_challenge_method=S256.
5. OP xác thực người dùng và có thể yêu cầu MFA/step-up.
6. OP chuyển browser về redirect URI với authorization code và state.
7. RP xác minh state, browser transaction, expiry và trạng thái chưa dùng.
8. RP gửi code, redirect_uri và code_verifier tới token endpoint; confidential client còn xác thực client theo cấu hình.
9. RP xác minh ID Token và các điều kiện OIDC.
10. RP ánh xạ subject sang account nội bộ rồi tạo local session mới.

### PKCE không thay thế các kiểm tra khác

PKCE giảm nguy cơ authorization code bị đánh cắp rồi đổi bởi một bên không có code verifier. Nó không thay thế:
- kiểm tra state và giao dịch browser;
- kiểm tra nonce trong ID Token;
- redirect URI chính xác;
- client authentication đối với confidential client;
- xác minh chữ ký, issuer, audience và thời gian của ID Token.

Dùng Authorization Code Flow với PKCE S256 cho public clients; confidential clients cũng nên dùng PKCE khi phù hợp với cấu hình và khuyến nghị bảo mật hiện hành. Không dùng implicit flow mới cho ứng dụng hiện đại nếu không có lý do tương thích được đánh giá rõ.

## 9. State, nonce và PKCE bảo vệ các rủi ro khác nhau

Ba giá trị thường bị gộp làm một, nhưng chúng có vai trò riêng:

| Giá trị | Được tạo bởi | Được kiểm tra ở đâu? | Mục tiêu |
| --- | --- | --- | --- |
| `state` | RP | Callback | Ràng buộc response với browser transaction, chống login CSRF/correlation lỗi. |
| `nonce` | RP | ID Token | Ràng buộc ID Token với authentication request, giảm token replay/substitution. |
| `code_verifier` | RP | Token endpoint qua PKCE | Chứng minh bên đổi code sở hữu verifier gắn với authorization request. |
| `code_challenge` | RP | Authorization endpoint | Cam kết verifier trước khi code được phát hành. |

Các giá trị cần đủ ngẫu nhiên, gắn với đúng giao dịch và hết hạn. Không dùng một state/nonce cố định cho mọi người dùng. Callback phải consume giao dịch pending theo cách nguyên tử hoặc có kiểm soát để cùng response không được dùng lặp.

### Redirect URI và open redirect

Redirect URI phải khớp chính xác với URI đã đăng ký tại OP theo quy tắc giao thức. Không dùng wildcard rộng, prefix matching hoặc tham số `next` do client truyền mà không allowlist. Open redirect có thể khiến code hoặc response bị chuyển sang domain attacker.

## 10. Xác minh ID Token: không chỉ decode JWT

ID Token là dữ liệu có chữ ký; decode payload chỉ giúp đọc nội dung, không chứng minh token hợp lệ. RP phải xác minh chữ ký và mọi claim bắt buộc theo OIDC.

| Kiểm tra | Yêu cầu |
| --- | --- |
| Signature | Xác minh chữ ký bằng public key thuộc issuer tin cậy. |
| Algorithm | Nằm trong allowlist; không tin lựa chọn thuật toán tùy ý từ token. |
| `iss` | Khớp chính xác issuer đã cấu hình. |
| `aud` | Có client ID của RP trong audience. |
| `azp` | Nếu có thì phải phù hợp client; khi aud có nhiều giá trị, kiểm tra authorized party theo quy tắc OIDC. |
| `exp` | Token chưa hết hạn, có clock-skew policy giới hạn. |
| `iat` | Thời điểm phát hành hợp lý theo policy. |
| `sub` | Có mặt và được dùng làm subject trong phạm vi issuer. |
| `nonce` | Nếu RP gửi nonce, claim phải khớp giao dịch pending. |
| `auth_time` | Kiểm tra khi RP yêu cầu xác thực mới hoặc policy cần freshness. |

Tùy flow và claim được phát hành, RP còn có thể cần kiểm tra các giá trị như `at_hash` hoặc `c_hash` theo quy tắc OIDC tương ứng. Không tự bỏ qua một kiểm tra chỉ vì thư viện đã parse JWT thành công; dùng thư viện OIDC có quy trình validation đầy đủ.

### Issuer và audience là ranh giới quan trọng

Một JWT có chữ ký hợp lệ vẫn có thể không dành cho RP hiện tại. Ví dụ, ID Token được phát hành cho client B không được chấp nhận tại client A chỉ vì cả hai dùng cùng OP. Audience mismatch phải dẫn tới từ chối.

Không chuẩn hóa issuer tùy tiện bằng cách bỏ path, đổi scheme hoặc so sánh chuỗi con. So sánh theo quy tắc chính xác của giao thức và issuer đã cấu hình.

## 11. UserInfo endpoint

UserInfo endpoint cung cấp claim về End-User khi RP gọi bằng Access Token hợp lệ. Đây là endpoint protected resource của OP.

Ví dụ request:

~~~http
GET /userinfo HTTP/1.1
Host: id.example.edu
Authorization: Bearer <access-token>
~~~

Response minh họa:

~~~json
{
  "sub": "student-00982",
  "name": "Mai Nguyen",
  "email": "mai@example.edu",
  "email_verified": true
}
~~~

RP cần:
- gửi Access Token qua kênh bảo vệ;
- kiểm tra response theo giao thức và cấu hình;
- so sánh `sub` trong UserInfo với `sub` của ID Token;
- chỉ sử dụng claim cần thiết;
- không coi email_verified là bằng chứng membership hoặc quyền truy cập.

Nếu UserInfo trả về subject khác ID Token, RP phải từ chối kết quả và điều tra. Không ghép profile từ UserInfo với một account khác chỉ dựa trên email.

## 12. Subject và ánh xạ account nội bộ

OIDC xác định subject bằng cặp **issuer + subject**:

~~~text
(iss, sub)
  = danh tính federation trong phạm vi OP
~~~

`sub` chỉ có ý nghĩa trong phạm vi issuer. Hai OP khác nhau có thể phát hành cùng chuỗi sub cho hai người khác nhau. Một người cũng có thể có sub khác nhau tại các OP khác nhau. Subject type có thể là public hoặc pairwise; pairwise subject giúp hạn chế liên kết hoạt động của người dùng giữa các client.

Một bảng mapping minh họa:

~~~sql
CREATE TABLE federated_identities (
    id UUID PRIMARY KEY,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    account_id UUID NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL,
    UNIQUE (issuer, subject)
);
~~~

Không dùng email làm khóa duy nhất cho federation identity. Email có thể đổi, được tái cấp, chưa xác minh hoặc trùng giữa nhiều issuer.

### Account linking

Khi liên kết OP mới với account hiện có:
1. Yêu cầu người dùng đang có session account nội bộ ở mức tin cậy phù hợp.
2. Có thể yêu cầu step-up bằng authenticator hiện tại.
3. Khởi tạo OIDC transaction mới với state/nonce/PKCE riêng.
4. Xác minh ID Token và lấy cặp issuer + subject.
5. Kiểm tra identity chưa gắn với account khác.
6. Áp dụng policy xác nhận cả account hiện tại và identity mới khi cần.
7. Ghi audit và thông báo thay đổi qua kênh tin cậy.

Không tự động merge hai account chỉ vì email giống nhau.

## 13. Authentication freshness và assurance

OIDC có thể truyền ngữ cảnh xác thực, nhưng RP phải hiểu semantics mà OP đã công bố hoặc thỏa thuận.

- `auth_time`: thời điểm người dùng được xác thực; không phải thời điểm token được phát hành.
- `acr`: Authentication Context Class Reference, lớp/ngữ cảnh xác thực theo định nghĩa của OP.
- `amr`: Authentication Methods References, phương thức xác thực theo từ vựng/semantics của OP.
- `max_age`: tham số RP có thể dùng để yêu cầu authentication freshness.
- `prompt`: tham số điều khiển hành vi xác thực/consent theo OIDC, ví dụ yêu cầu tương tác hoặc chọn account trong các trường hợp hỗ trợ.
- `acr_values`: có thể yêu cầu một authentication context cụ thể nếu OP hỗ trợ.

Không mặc định `amr` có chuỗi “mfa” đồng nghĩa đạt MFA mạnh hoặc chống phishing. Password + SMS và passkey/WebAuthn có đặc tính khác nhau. RP cần hợp đồng rõ với OP về ý nghĩa acr/amr, cách xác minh UV, authenticator và recovery.

Ví dụ, một API quản trị yêu cầu xác thực trong vòng 5 phút. RP kiểm tra auth_time của ID Token đã xác minh. Nếu quá cũ, RP yêu cầu reauthentication hoặc step-up. Việc browser redirect qua OP và nhận token mới không tự chứng minh người dùng vừa xác thực lại nếu OP dùng lại session cũ mà không đáp ứng max_age/policy.

## 14. Tạo session cục bộ sau OIDC

Sau khi ID Token hợp lệ và identity được ánh xạ, RP thường tạo local session riêng. Không dùng ID Token làm session cookie hoặc coi Access Token là local session ID.

Local session nên:
- gắn với internal account ID;
- lưu issuer + subject đã xác minh;
- lưu auth_time và authentication context nếu policy cần;
- có session ID ngẫu nhiên, opaque và rotate sau đăng nhập;
- có idle timeout, absolute timeout và revoke;
- có tenant/membership context đã xác minh nếu session tenant-scoped;
- dùng cookie Secure, HttpOnly và SameSite phù hợp;
- có CSRF protection cho request thay đổi trạng thái.

OIDC session tại OP và session tại RP là hai trạng thái độc lập. Người dùng logout khỏi RP không nhất thiết đã logout khỏi OP hoặc các RP khác. Tương tự, token refresh không phải một lần xác thực mới và không tự cập nhật auth_time.

## 15. Refresh Token và bảo vệ vòng đời token

Refresh Token có thể cho phép client tiếp tục lấy Access Token sau khi Access Token hết hạn. OP có thể phát Refresh Token khi policy, scope, consent và loại client đáp ứng điều kiện.

Kiểm soát:
- lưu Refresh Token trong kho an toàn, tránh local storage không phù hợp với threat model;
- dùng rotation hoặc sender-constrained token nếu OP hỗ trợ;
- phát hiện reuse của token cũ và xử lý token family theo policy;
- thu hồi khi logout, account deprovision hoặc phát hiện compromise;
- giới hạn scope, audience và thời gian;
- không gửi Refresh Token tới resource server;
- không ghi token vào log, analytics hoặc URL.

Đối với browser-based application, kiến trúc BFF (Backend for Frontend) có thể giữ token ở backend và chỉ cấp cookie session cho browser, giảm việc phơi bày token OAuth trong JavaScript. Cần lựa chọn theo kiến trúc, threat model và hướng dẫn bảo mật hiện hành.

## 16. Logout trong OIDC

OIDC phân biệt local RP logout với logout tại OP và các cơ chế phối hợp.

- **Local logout:** RP thu hồi local session và xóa cookie.
- **RP-Initiated Logout:** RP điều hướng tới OP logout endpoint theo metadata/cấu hình để yêu cầu kết thúc OP session.
- **Front-channel logout:** OP phối hợp thông báo tới RP thông qua browser.
- **Back-channel logout:** OP gửi logout token trực tiếp tới endpoint backend của RP theo profile hỗ trợ.

Logout token/event phải được xác minh theo giao thức, bao gồm issuer, audience, signature, event claim, thời hạn và session correlation phù hợp. RP cần ánh xạ đúng sid/sub tới local session, chống replay và xử lý idempotently. Không thu hồi mọi session có cùng chuỗi sub nếu chưa kiểm tra issuer và phạm vi.

Không giả định mọi OP/RP hỗ trợ đầy đủ mọi kiểu logout. Local logout vẫn cần hoạt động độc lập; session có thời hạn hữu hạn để giảm tác động khi một RP không nhận logout event.

## 17. Các kiểu tấn công và lỗi OIDC thường gặp

| Lỗi/tấn công | Cách xảy ra | Phòng vệ |
| --- | --- | --- |
| Code interception | Attacker lấy authorization code từ redirect | Authorization Code + PKCE, TLS, code ngắn hạn, redirect URI chính xác. |
| Login CSRF | Browser nạn nhân bị gắn với giao dịch login của attacker | State, browser-bound transaction và callback validation. |
| ID Token replay/substitution | Dùng token từ giao dịch khác | Nonce, audience, issuer, expiry và giao dịch pending. |
| Issuer mix-up | RP nhầm OP đã phát hành response | Issuer cấu hình rõ, ràng buộc giao dịch và kiểm tra iss chính xác. |
| Audience confusion | Token phát cho client khác được chấp nhận | Kiểm tra aud và azp khi áp dụng. |
| Algorithm confusion | RP chấp nhận thuật toán không được phép | Algorithm allowlist và thư viện xác minh chuẩn. |
| JWKS injection | RP lấy key từ URL tùy ý trong token | Chỉ dùng jwks_uri từ metadata issuer tin cậy. |
| Open redirect | Redirect URI/return URL chuyển code tới attacker | Exact redirect URI và allowlist route. |
| Account-linking takeover | Gộp account theo email trùng | Mapping issuer + subject, reauthentication và audit. |
| Claim privilege escalation | Claim group/role được tin trực tiếp | Allowlist mapping và authorization nội bộ. |
| Refresh token theft/reuse | Token dài hạn bị đánh cắp và dùng lại | Secure storage, rotation, reuse detection và revoke. |
| Token dùng sai mục đích | Dùng Access Token thay ID Token hoặc ngược lại | Kiểm tra token type, audience và endpoint phù hợp. |
| Stale authentication | Token mới nhưng auth_time cũ | Kiểm tra auth_time/max_age và yêu cầu step-up. |
| SSO logout không đồng bộ | RP giữ session sau khi OP logout | Logout protocol, local expiry, deprovision và revoke policy. |

## 18. Giả mã xử lý OIDC callback ở RP

Ví dụ Java dưới đây chỉ minh họa thứ tự trách nhiệm. Phần xác minh token phải được thực hiện bởi thư viện OIDC đã được kiểm chứng:

~~~java
LoginResult completeOidcLogin(Callback callback, BrowserSession browser) {
    PendingLogin pending =
        pendingLoginStore.requireActive(browser, callback.state());

    // Kiểm tra state và transaction trước khi đổi code.
    if (!constantTimeEquals(callback.state(), pending.state())) {
        throw genericLoginFailure();
    }

    TokenResponse tokens = oidcClient.exchangeCode(
        pending.issuerConfig(),
        callback.code(),
        pending.redirectUri(),
        pending.pkceCodeVerifier());

    VerifiedIdToken idToken = idTokenVerifier.verify(
        tokens.idToken(),
        pending.expectedIssuer(),
        pending.clientId(),
        pending.nonce(),
        allowedSigningAlgorithms());

    FederatedIdentity identity =
        new FederatedIdentity(idToken.issuer(), idToken.subject());

    Account account = identityStore.requireMappedAccount(identity);
    accountPolicy.requireActive(account);

    pendingLoginStore.consumeAtomically(pending.id());

    return sessionService.createFreshSession(
        account.id(),
        identity.issuer(),
        identity.subject(),
        idToken.authenticatedAt(),
        idToken.authenticationContext());
}
~~~

Trong production cần bổ sung:
- xử lý authorization error và code exchange failure;
- kiểm tra redirect URI đã đăng ký, không lấy từ callback;
- xác minh đầy đủ chữ ký, issuer, audience, thời gian, nonce và claim theo OIDC;
- kiểm tra account, tenant và membership gần thời điểm commit;
- consume pending transaction nguyên tử;
- rotate session ID và tạo local session riêng;
- không log code, ID Token, Access Token, Refresh Token hoặc session cookie.

## 19. Kiểm thử bảo mật OIDC

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Authorization Code Flow hợp lệ với PKCE S256 | Đổi code, xác minh ID Token và tạo session. |
| Thiếu scope openid | Không xử lý response như OIDC authentication. |
| State sai hoặc không có pending transaction | Từ chối callback. |
| Nonce không khớp | Từ chối ID Token. |
| Code đã dùng hoặc hết hạn | Token endpoint từ chối; RP không tạo session. |
| PKCE verifier sai | Code exchange thất bại. |
| Redirect URI khác cấu hình | Từ chối. |
| ID Token signature sai | Từ chối. |
| Issuer khác issuer đã cấu hình | Từ chối. |
| Audience không chứa client ID | Từ chối. |
| azp không phù hợp khi áp dụng | Từ chối. |
| ID Token hết hạn | Từ chối. |
| Nonce bị replay từ giao dịch khác | Từ chối. |
| kid không có trong JWKS | Refresh có giới hạn; vẫn không xác minh được thì từ chối. |
| Thuật toán ngoài allowlist | Từ chối. |
| UserInfo sub khác ID Token sub | Từ chối dữ liệu UserInfo. |
| Access Token gửi vào nơi cần ID Token | Từ chối do sai mục đích/audience. |
| Cùng sub nhưng issuer khác | Không gộp account. |
| Email trùng account nội bộ | Không tự động link. |
| auth_time quá cũ cho policy | Yêu cầu reauthentication/step-up hoặc từ chối. |
| acr/amr không đáp ứng yêu cầu phishing resistance | Không nâng assurance. |
| Refresh Token reuse | Phát hiện và xử lý token family theo policy. |
| Logout token sai issuer/audience/signature | Không revoke session. |
| Logout event hợp lệ lặp lại | Xử lý idempotently. |
| Callback lỗi | Không tạo account, membership hoặc session ngoài ý muốn. |

### Kiểm thử negative path

Không chỉ kiểm tra đăng nhập thành công. Hãy thay từng trường `iss`, `aud`, `nonce`, `state`, `redirect_uri`, `kid`, `alg`, `exp` và subject mapping. Mỗi response không hợp lệ phải bị từ chối trước khi tạo session hoặc cấp quyền. Kiểm tra side effect để bảo đảm callback sai không tạo account, thêm membership hay thay đổi role.

## 20. Vận hành, giám sát và quyền riêng tư

Các chỉ số hữu ích:
- tỷ lệ login thành công/thất bại theo issuer và client;
- lỗi state, nonce, PKCE, signature, issuer, audience và token expiry;
- số lần refresh token reuse hoặc revoke;
- JWKS refresh failure, tuổi cache và key rotation;
- tỷ lệ step-up theo acr/amr và kết quả xác thực;
- lỗi UserInfo hoặc subject mismatch;
- số account linking/unlinking và deprovisioning;
- số local session bị revoke sau logout hoặc sự kiện IdP.

Log nên chứa correlation ID, issuer ID đã cấu hình, client ID, reason code và account ID nội bộ sau khi xác định. Không log authorization code, raw ID/access/refresh token, client secret, private key hoặc cookie. Claim profile có thể là dữ liệu cá nhân; chỉ yêu cầu và lưu phần cần thiết, giới hạn retention và quyền truy cập.

## 21. Bài tập tình huống

Một nền tảng học tập kết nối với hai OpenID Provider: trường Đại học A và nhà cung cấp SSO của doanh nghiệp B. Cả hai có thể phát hành người dùng với email giống nhau. Ứng dụng hiện chỉ decode JWT, tìm account bằng email, không kiểm tra audience hoặc nonce và dùng Access Token làm cookie đăng nhập.

**Yêu cầu:**

1. Giải thích vì sao decode JWT không phải xác minh token.
2. Phân biệt ID Token và Access Token trong luồng này.
3. Thiết kế Authorization Code Flow với PKCE, state và nonce.
4. Xác định những claim và chữ ký cần kiểm tra trước khi tạo session.
5. Thiết kế bảng mapping identity theo issuer + subject.
6. Đề xuất cách xử lý email trùng và account linking.
7. Mô tả kiểm tra tenant/membership và authentication assurance.

**Hướng phân tích:** RP dùng Authorization Code + PKCE; callback kiểm tra state, đổi code và xác minh ID Token bằng JWKS của issuer đã cấu hình. Kiểm tra iss, aud, exp, iat, nonce, sub và azp khi áp dụng. Dùng (iss, sub) để tìm account; email chỉ là claim profile, không tự động merge. Access Token chỉ được gửi tới resource server theo audience/scope. Sau authentication, RP tạo local session riêng và kiểm tra tenant/membership, authorization và auth_time/acr/amr theo policy.

## 22. Checklist review

- [ ] RP phân biệt OIDC authentication với OAuth 2.0 delegated authorization.
- [ ] Authorization request có scope openid và flow phù hợp.
- [ ] Dùng Authorization Code Flow với PKCE S256 cho client phù hợp.
- [ ] State, nonce và PKCE verifier được tạo ngẫu nhiên, gắn transaction và hết hạn.
- [ ] Redirect URI khớp chính xác cấu hình, không có open redirect.
- [ ] Discovery metadata gắn với issuer đã quản trị; không nhận issuer tùy ý.
- [ ] JWKS chỉ được lấy từ metadata tin cậy, có cache và key rotation policy.
- [ ] ID Token được xác minh chữ ký, algorithm, iss, aud, azp khi áp dụng, exp, iat, sub và nonce.
- [ ] auth_time/acr/amr được kiểm tra khi policy yêu cầu freshness/assurance.
- [ ] ID Token và Access Token được dùng đúng mục đích.
- [ ] UserInfo sub khớp ID Token sub trước khi dùng claim.
- [ ] Scope/claim được tối thiểu hóa; email không được dùng làm khóa federation duy nhất.
- [ ] Identity mapping theo issuer + subject; account linking cần reauthentication và audit.
- [ ] RP tạo local session riêng, có rotation, expiry và revocation.
- [ ] Refresh Token được bảo vệ, rotation/reuse detection và revoke theo policy.
- [ ] Logout event được xác minh và ánh xạ đúng issuer/session.
- [ ] Tenant, membership và authorization được kiểm tra độc lập sau authentication.
- [ ] Log không chứa code, token, secret, private key hoặc session cookie.
- [ ] Có negative tests cho state, nonce, issuer, audience, key rotation, replay và account linking.

## 23. Ghi nhớ

**OpenID Connect bổ sung lớp xác thực danh tính trên OAuth 2.0.** ID Token cho RP biết subject nào đã được xác thực bởi issuer nào và trong ngữ cảnh được phát hành; Access Token dành cho resource server để truy cập API. RP phải dùng Authorization Code Flow với PKCE phù hợp, ràng buộc giao dịch bằng state/nonce, xác minh chữ ký và claim của ID Token, ánh xạ identity bằng issuer + subject rồi tạo session cục bộ riêng.

Một token có chữ ký hợp lệ chưa chắc dành cho RP hiện tại; email trùng chưa chắc là cùng account; redirect qua IdP chưa chắc là xác thực mới. Khi review, hãy hỏi: **RP tin issuer nào? Code và callback có gắn đúng giao dịch không? ID Token có đúng audience, nonce và thời hạn không? Subject được ánh xạ ra account nào? Claim MFA có semantics gì? Session và token cũ được thu hồi thế nào khi account hoặc trust key thay đổi?**
