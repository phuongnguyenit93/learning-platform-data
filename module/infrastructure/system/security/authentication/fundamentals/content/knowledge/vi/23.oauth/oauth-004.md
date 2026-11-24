# Authorization server

## 1. Authorization server là gì?

**Authorization server (AS)** là thành phần trong OAuth 2.0 chịu trách nhiệm cấp authorization grant và phát hành token cho client theo chính sách đã cấu hình. AS kiểm tra client, xác định yêu cầu truy cập, áp dụng quy tắc xác thực/consent khi cần, rồi phát hành access token hoặc credential liên quan để client truy cập resource server.

Trong flow tương tác với người dùng, AS thường phối hợp với hệ thống đăng nhập để xác minh người dùng, xử lý MFA và lấy consent. Tuy nhiên, cần phân biệt hai khái niệm: **OAuth 2.0 là framework ủy quyền**, còn **OpenID Connect (OIDC) bổ sung lớp xác thực danh tính** trên OAuth 2.0. Một authorization server có thể tham gia đăng nhập, nhưng access token OAuth không mặc nhiên là bằng chứng đăng nhập cho client.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, authorization server kết nối credential, password/passkey, MFA, token, session, identity federation và trust boundary. Người học cần hiểu AS nhận yêu cầu từ ai, kiểm tra điều kiện nào, phát hành token cho audience nào và cách resource server xác minh quyền được cấp.

Sau bài học, người học có thể:

- Phân biệt authorization server, resource server, client, resource owner và OpenID Provider.
- Mô tả trách nhiệm và endpoint chính của authorization server.
- Giải thích Authorization Code + PKCE, client credentials và device authorization.
- Phân biệt access token, ID token, refresh token và authorization code.
- Thiết kế client authentication, consent, scope, audience và token lifetime.
- Hiểu discovery, JWKS, introspection, revocation, PAR và sender-constrained token.
- Nhận diện các lỗi authorization server có thể dẫn đến token theft, code injection, mix-up hoặc privilege escalation.

## 2. Các vai trò trong OAuth 2.0

OAuth 2.0 định nghĩa các vai trò phối hợp để client nhận quyền truy cập tài nguyên:

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Resource Owner** | Chủ thể có quyền cấp quyền truy cập tài nguyên; thường là người dùng | Người dùng sở hữu dữ liệu hồ sơ |
| **Client** | Ứng dụng yêu cầu quyền và dùng access token để gọi API | Web app, mobile app hoặc backend |
| **Authorization Server (AS)** | Xác minh authorization request, áp dụng policy và phát hành token | OAuth server/IAM platform |
| **Resource Server (RS)** | Lưu hoặc cung cấp tài nguyên được bảo vệ; kiểm tra access token | API hồ sơ, payment API |

~~~mermaid
flowchart LR
    U[Resource Owner] -->|Cho phép hoặc từ chối| AS[Authorization Server]
    C[Client] -->|Authorization request| AS
    AS -->|Authorization code / token| C
    C -->|Access token| RS[Resource Server]
    RS -->|Protected resource| C
~~~

AS và RS có thể nằm trong cùng một sản phẩm hoặc được vận hành bởi hai hệ thống độc lập. Dù cùng một tổ chức, chúng vẫn có trust boundary và trách nhiệm riêng: AS phát hành token theo policy; RS quyết định token có hợp lệ cho API của mình và principal có quyền thực hiện hành động cụ thể hay không.

### 2.1. Authorization server không đồng nghĩa với resource server

AS không nhất thiết lưu dữ liệu nghiệp vụ. Nó thường quản lý client, authorization grant, consent, session xác thực, khóa ký và token lifecycle. RS nhận token và bảo vệ API hoặc tài nguyên.

Một API không nên tự tin token chỉ vì client nói rằng AS đã cấp. RS phải tự xác minh token hoặc gọi cơ chế introspection đáng tin cậy, kiểm tra issuer, audience, expiry, scope và policy của tài nguyên.

### 2.2. Authorization server và OpenID Provider

**OpenID Provider (OP)** là authorization server hỗ trợ OIDC. OIDC thêm ID token và các quy tắc xác thực danh tính, ví dụ issuer, subject, audience, nonce, authentication time và claims.

- OAuth access token được dùng để truy cập resource server.
- OIDC ID token được gửi tới client để xác nhận kết quả xác thực theo OIDC.
- Không dùng ID token thay access token khi gọi API.
- Không diễn giải mọi OAuth access token như bằng chứng user đã đăng nhập.

Một hệ thống có thể hỗ trợ OAuth mà không hỗ trợ OIDC. Khi cần đăng nhập người dùng và nhận thông tin danh tính có cấu trúc, client nên dùng OIDC hoặc một giao thức xác thực phù hợp.

## 3. Trách nhiệm chính của authorization server

AS cần thực hiện một chuỗi quyết định có kiểm soát:

1. Nhận authorization request hoặc token request qua endpoint phù hợp.
2. Xác định client và kiểm tra client có được phép dùng flow, redirect URI, scope và resource được yêu cầu không.
3. Với flow có người dùng, xác minh người dùng qua credential và policy hiện hành; có thể yêu cầu MFA hoặc step-up.
4. Xác định resource owner có quyền cấp grant hay không.
5. Hiển thị và xử lý consent khi policy yêu cầu.
6. Phát hành authorization code hoặc token có phạm vi, audience và thời hạn phù hợp.
7. Quản lý refresh, revoke, introspection và trạng thái grant theo khả năng.
8. Bảo vệ signing keys, client credentials, session và dữ liệu consent.
9. Ghi audit, phát hiện lạm dụng và cung cấp cơ chế vận hành/recovery.
10. Công bố metadata và public keys để client/resource server cấu hình và xác minh.

Không phải flow nào cũng có màn hình consent. Client nội bộ hoặc quyền đã được admin phê duyệt có thể dùng policy consent khác; nhưng việc bỏ qua consent phải là quyết định quản trị có chủ đích, không phải mặc định cấp mọi scope.

## 4. Các endpoint thường gặp

Một authorization server có thể công bố các endpoint sau. Đường dẫn thực tế do issuer quy định và cần lấy từ metadata đáng tin cậy.

| Endpoint | Mục đích | Ai thường gọi |
| --- | --- | --- |
| **Authorization endpoint** | Bắt đầu flow tương tác; xử lý login, consent và trả authorization response | Browser/client qua user-agent |
| **Token endpoint** | Đổi authorization code hoặc grant khác lấy token; refresh token | Client |
| **JWKS URI** | Công bố public keys dùng xác minh JWT/assertion | Client, RS hoặc thư viện xác minh |
| **Introspection endpoint** | Kiểm tra trạng thái token, thường trả active, scope, subject, audience và metadata | Resource server hoặc gateway được phép |
| **Revocation endpoint** | Yêu cầu thu hồi token hoặc grant theo policy | Client |
| **Pushed Authorization Request (PAR) endpoint** | Nhận authorization parameters qua back-channel và trả request URI | Client |
| **Device authorization endpoint** | Khởi tạo device authorization flow cho thiết bị hạn chế nhập liệu | Device client |
| **Metadata/discovery endpoint** | Công bố issuer, endpoint, grant, response type, key và capability | Client/RS/admin tooling |

Không phải AS nào cũng hỗ trợ mọi endpoint hoặc extension. Client không nên ghép URL endpoint bằng suy đoán từ domain; hãy dùng metadata/discovery hoặc cấu hình được phê duyệt, sau đó kiểm tra issuer.

### 4.1. Discovery và metadata

OAuth Authorization Server Metadata được mô tả trong RFC 8414; OIDC Discovery cung cấp metadata cho OpenID Provider. Metadata có thể công bố:

- Issuer.
- Authorization endpoint và token endpoint.
- JWKS URI.
- Introspection/revocation endpoint nếu có.
- Grant types và response types được hỗ trợ.
- Token endpoint authentication methods.
- PKCE methods hoặc capability liên quan khi được công bố.
- Signing algorithms và các thông tin policy.

Client phải kiểm tra issuer trong metadata khớp với issuer đã cấu hình/được tin. Không lấy metadata từ một URL do request không đáng tin cung cấp rồi tự động gửi authorization code hoặc client secret tới endpoint vừa nhận.

## 5. Authorization Code flow và PKCE

**Authorization Code** là flow phổ biến cho đăng nhập người dùng và delegated authorization. Client chuyển browser tới AS; sau khi người dùng xác thực và cấp quyền theo policy, AS trả một authorization code qua redirect URI. Client đổi code tại token endpoint để lấy token.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant B as Browser
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>C: Bắt đầu đăng nhập / truy cập tính năng
    C->>C: Tạo state, PKCE verifier và challenge
    C->>B: Redirect tới authorization endpoint
    B->>AS: Authorization request
    AS->>U: Xác thực và consent nếu cần
    U->>AS: Hoàn tất policy
    AS-->>B: Redirect URI + authorization code + state
    B->>C: Callback
    C->>C: Kiểm tra state
    C->>AS: Code + redirect_uri + code_verifier
    AS->>AS: Kiểm tra code, client, redirect và PKCE
    AS-->>C: Access token (+ ID token nếu OIDC)
    C->>RS: API request + access token
    RS->>RS: Xác minh token và authorization
    RS-->>C: Protected resource
~~~

### 5.1. PKCE

PKCE (Proof Key for Code Exchange) ràng buộc authorization code với một giao dịch do client khởi tạo:

1. Client tạo code_verifier ngẫu nhiên và đủ mạnh.
2. Client tính code_challenge, thường dùng phương thức S256.
3. Authorization request mang code_challenge và code_challenge_method.
4. Khi đổi code, client gửi code_verifier.
5. AS tính lại challenge và chỉ chấp nhận nếu khớp với challenge gắn với code.

PKCE giảm nguy cơ kẻ tấn công chặn authorization code rồi đổi code đó. Không dùng plain nếu S256 được hỗ trợ. PKCE không thay redirect URI validation, state, issuer validation hoặc OIDC nonce.

### 5.2. State và nonce

- **State** được client tạo để liên kết callback với authorization transaction, hỗ trợ chống CSRF/login CSRF.
- **Nonce** trong OIDC liên kết ID token với authentication request.
- **PKCE** ràng buộc authorization code với client transaction.

Ba cơ chế có mục đích khác nhau. Không bỏ state chỉ vì đã dùng PKCE nếu implementation và threat model yêu cầu state; cũng không bỏ nonce trong OIDC flow khi profile yêu cầu.

### 5.3. Authorization code phải dùng một lần

Authorization code là credential ngắn hạn, không phải access token. AS cần:

- Ràng buộc code với client, redirect URI và PKCE challenge.
- Đặt thời hạn ngắn.
- Tiêu thụ code theo thao tác nguyên tử để không thể đổi hai lần.
- Từ chối code đã dùng, hết hạn, sai client hoặc sai redirect URI.
- Không ghi code vào log hoặc analytics.
- Tránh để code rò qua referrer, browser history hoặc URL logging không cần thiết.

Client cũng cần bảo vệ callback và không điều hướng code sang URL bên thứ ba.

## 6. Những grant khác và phạm vi sử dụng

AS có thể hỗ trợ nhiều grant. Mỗi grant đại diện một cách client chứng minh quyền đổi lấy token.

| Grant | Dùng cho | Điều cần kiểm soát |
| --- | --- | --- |
| **authorization_code** | Người dùng tương tác, delegated access | Redirect URI, state, PKCE, code one-time |
| **client_credentials** | Service-to-service, không đại diện resource owner | Client authentication, scope/audience tối thiểu, secret/key lifecycle |
| **device_code** | Thiết bị khó nhập liệu như TV/CLI | User code, device code, polling interval, expiry và phishing-resistant UX |
| **refresh_token** | Đổi refresh token lấy access token mới | Rotation/reuse detection hoặc sender constraint, expiry, revoke |
| **token exchange** | Đổi token theo trust domain hoặc audience khác khi AS hỗ trợ | Subject/actor token, audience, delegation policy và scope |
| **implicit** | Flow cũ trả token qua browser front-channel | Không khuyến nghị cho ứng dụng mới |
| **resource owner password credentials** | Client trực tiếp nhận password của user | Không nên dùng cho flow mới; client không nên thu mật khẩu user |

### 6.1. Client credentials không phải user login

Client credentials grant cấp token cho chính client/service. Token đại diện workload hoặc client identity, không phải người dùng cuối. Không đưa user ID do client tự gửi vào token rồi coi đó là user đã xác thực.

Nếu service cần thực hiện hành động thay mặt user, dùng flow delegated phù hợp hoặc token exchange theo policy; không giả lập user bằng client credentials.

### 6.2. Device authorization flow

Device flow dành cho thiết bị có giới hạn nhập liệu. Thiết bị nhận device_code và user_code, hiển thị URL cùng mã cho người dùng. Người dùng dùng thiết bị khác để đăng nhập tại AS và xác nhận yêu cầu. Thiết bị polling token endpoint theo khoảng thời gian được chỉ định.

AS phải giới hạn thời gian, tốc độ polling và số lần thử; user code cần đủ khó đoán trong phạm vi thời hạn. Trang xác nhận cần hiển thị thông tin client và quyền đang yêu cầu để người dùng tránh nhập mã vào trang giả. Không cho thiết bị polling dồn dập hoặc đổi device code nhiều lần ngoài policy.

## 7. Authentication, consent và policy tại authorization server

Trong flow người dùng, AS thường kết hợp authentication service với authorization policy:

- **Authentication:** xác minh người dùng bằng password, passkey, MFA, certificate hoặc IdP liên kết.
- **Session:** duy trì trạng thái đăng nhập tại AS; session này khác session của client.
- **Consent:** ghi nhận user/admin đồng ý cấp quyền nếu policy yêu cầu.
- **Authorization policy:** quyết định client có được yêu cầu scope/resource nào và user có quyền cấp hay không.
- **Step-up:** yêu cầu xác thực mạnh hơn hoặc gần đây hơn trước khi cấp quyền nhạy cảm.

AS có thể yêu cầu reauthentication khi người dùng đăng nhập lâu trước đó, khi truy cập dữ liệu nhạy cảm hoặc khi policy yêu cầu một mức assurance cụ thể. Với OIDC, các tham số như max_age, acr_values và claims có thể tham gia yêu cầu authentication context; OP phải xử lý theo khả năng và profile đã công bố.

Không nhầm “user đã đăng nhập tại IdP” với “user đã chấp thuận mọi scope”. SSO session có thể giúp bỏ qua việc nhập credential lại, nhưng authorization và consent vẫn cần được áp dụng cho client/resource cụ thể.

## 8. Scope, audience và quyền được cấp

**Scope** mô tả nhóm quyền hoặc thông tin mà client yêu cầu. **Audience** xác định resource server hoặc recipient mà token hướng tới. Hai yếu tố này giúp giới hạn token.

Ví dụ một authorization request:

~~~http
GET /authorize?
  response_type=code&
  client_id=portal-web&
  redirect_uri=https%3A%2F%2Fportal.example.test%2Fcallback&
  scope=openid%20profile%20orders.read&
  state=random-state&
  code_challenge=challenge-value&
  code_challenge_method=S256
~~~

Đây là ví dụ giản lược; request thực tế cần URL encoding, nonce khi OIDC yêu cầu và các tham số theo profile.

AS không nên cấp tất cả scope chỉ vì client yêu cầu. Cần kiểm tra:

- Client đã được đăng ký và cho phép scope đó chưa?
- User hoặc admin có quyền cấp scope không?
- Consent đã có và còn hiệu lực không?
- Scope có phù hợp resource/audience không?
- Có cần step-up/MFA cho quyền nhạy cảm không?
- Scope được cấp thực tế có cần thu hẹp so với yêu cầu không?

RS phải kiểm tra audience của token đúng API mình phục vụ. Một token dành cho API A không được chấp nhận tại API B chỉ vì cùng issuer đã ký token.

## 9. Access token, refresh token và ID token

| Loại | Mục đích | Ai sử dụng/xác minh |
| --- | --- | --- |
| **Authorization code** | Credential ngắn hạn để đổi token | Client gửi tới token endpoint; AS tiêu thụ một lần |
| **Access token** | Cho phép client gọi resource server trong phạm vi được cấp | Client gửi; RS xác minh hoặc introspect |
| **Refresh token** | Đổi lấy access token mới mà không cần chạy lại toàn bộ authorization flow | Client gửi tới AS; AS xác minh và quản lý vòng đời |
| **ID token** | Khẳng định sự kiện xác thực và claims về subject cho OIDC client | OIDC client xác minh |

Access token có thể là opaque token hoặc JWT. Với opaque token, RS thường dùng introspection hoặc tra cứu trạng thái qua hệ thống tin cậy. Với JWT, RS xác minh chữ ký, issuer, audience, expiry, token type và claims cần thiết.

Không đưa dữ liệu cá nhân dư thừa vào token. Token thường được truyền qua nhiều thành phần, có thể xuất hiện trong memory, log hoặc telemetry nếu triển khai kém. Dùng claim tối thiểu và thời hạn phù hợp.

### 9.1. Token lifetime

Access token nên có thời hạn tương xứng với rủi ro và khả năng revoke. Token sống lâu giảm tần suất refresh nhưng tăng cửa sổ nếu bị đánh cắp. Token quá ngắn có thể làm tăng tải refresh và phụ thuộc vào AS.

Refresh token thường có vòng đời dài hơn access token và cần bảo vệ nghiêm ngặt. Với public client, nên áp dụng refresh token rotation hoặc sender-constrained refresh token theo policy; phát hiện reuse có thể kích hoạt thu hồi token family hoặc session liên quan.

## 10. Refresh token và thu hồi grant

Khi client dùng refresh token, AS phải xác minh token thuộc client, còn hiệu lực, chưa bị revoke và vẫn được phép dùng. AS có thể áp dụng:

- Rotation: mỗi lần refresh phát hành refresh token mới và vô hiệu token cũ.
- Reuse detection: phát hiện token cũ được dùng lại sau rotation.
- Sender constraint: ràng buộc token với khóa/client khi profile hỗ trợ.
- Absolute lifetime và inactivity timeout.
- Revoke theo client, user, session, grant hoặc security event.
- Yêu cầu reauthentication/MFA khi rủi ro hoặc policy thay đổi.

Nếu refresh token bị đánh cắp, attacker có thể duy trì quyền truy cập sau khi access token ngắn hạn hết hạn. Do đó, refresh token không nên lưu trong nơi public JavaScript dễ đọc nếu có kiến trúc BFF/session cookie phù hợp hơn. Mobile app cần dùng secure storage theo khả năng nền tảng.

## 11. Token format và ký token

AS có thể phát hành opaque access token hoặc JWT. Với JWT, AS ký token bằng private key; RS xác minh bằng public key tương ứng từ JWKS hoặc trust configuration.

Một JWT access token có thể có các claim khái niệm:

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "service-or-user-subject",
  "aud": "orders-api",
  "exp": 1795323900,
  "iat": 1795323000,
  "scope": "orders.read",
  "client_id": "portal-web"
}
~~~

Đây là ví dụ minh họa, không phải schema bắt buộc. Cấu trúc claim phụ thuộc token profile, AS và RS.

### 11.1. JWKS và key rotation

JWKS công bố public keys để bên nhận xác minh chữ ký JWT. AS cần bảo vệ private signing key, quản lý key ID, thuật toán và rotation.

- Private key chỉ được truy cập bởi thành phần ký được cấp quyền.
- Public JWKS được phân phối qua HTTPS và issuer đã cấu hình.
- Key ID phải định danh duy nhất trong tập key.
- RS chỉ chấp nhận thuật toán theo allowlist; không tin thuật toán tùy ý trong token header.
- Khi rotate, công bố key mới trước khi dùng, duy trì overlap phù hợp với token lifetime/cache rồi ngừng key cũ.
- Khi key bị compromise, cần emergency rotation và đánh giá token đã phát hành trong khoảng ảnh hưởng.

RS không được tải JWKS từ URL do token header tự khai rồi tin key vừa tải. JWKS URI phải gắn với issuer đã được tin cậy và metadata đã xác minh.

### 11.2. Opaque token và introspection

Opaque token không mang claims có thể tự xác minh tại RS. RS gửi token tới introspection endpoint được bảo vệ để hỏi AS token còn active hay không và thuộc subject/client/scope/audience nào.

Introspection giúp kiểm tra trạng thái gần hiện tại và hỗ trợ revoke, nhưng tạo phụ thuộc availability/latency của AS. RS nên bảo vệ endpoint, cache có giới hạn phù hợp và không log token thô. Cache quá lâu có thể khiến token đã revoke vẫn được chấp nhận.

## 12. Introspection và revocation

Hai cơ chế có vai trò khác nhau:

- **Introspection:** RS hỏi AS về trạng thái token tại thời điểm kiểm tra. AS có thể trả active và metadata token theo policy.
- **Revocation:** client hoặc hệ thống được phép yêu cầu AS vô hiệu token/grant.

Revocation endpoint không có nghĩa mọi RS biết ngay token đã bị thu hồi. Với JWT tự xác minh, RS có thể tiếp tục chấp nhận token đến khi hết hạn nếu không có denylist, introspection hoặc cơ chế cập nhật trạng thái. Thiết kế cần cân bằng độ trễ revoke và khả năng hoạt động khi AS không sẵn sàng.

AS nên hỗ trợ quy trình thu hồi theo các sự kiện như user logout, password reset, user disable, refresh token reuse, client compromise hoặc admin revoke consent. RS cần có policy xử lý token hết hạn, không hợp lệ, issuer/audience sai và introspection unavailable.

## 13. Pushed Authorization Requests (PAR)

PAR cho phép client gửi authorization parameters tới AS qua back-channel trước. AS trả một request URI ngắn hạn; client sau đó chuyển browser tới authorization endpoint với request URI đó.

Lợi ích:

- Giảm việc đưa toàn bộ authorization parameters nhạy cảm vào front-channel URL.
- AS có thể xác minh client và kiểm tra request trước khi browser được chuyển hướng.
- Hạn chế một số kiểu request tampering và hỗ trợ policy kiểm soát chặt hơn.
- Có thể kết hợp với signed request objects theo profile hỗ trợ.

PAR không thay PKCE, redirect URI validation, state hoặc các kiểm tra token. Request URI phải ngắn hạn, gắn với client và chỉ dùng theo policy; AS cần từ chối URI hết hạn hoặc bị dùng sai client.

## 14. Client authentication tại token endpoint

Confidential client phải xác thực khi gọi token endpoint theo phương thức đã đăng ký. Các lựa chọn thường gặp:

| Phương thức | Đặc điểm | Rủi ro/kiểm soát |
| --- | --- | --- |
| **client_secret_basic** | Client gửi secret qua HTTP Basic trên TLS | Secret cần bảo vệ, rotation và redaction log |
| **client_secret_post** | Client gửi secret trong body | Tránh log request body; chỉ dùng theo policy |
| **private_key_jwt** | Client ký JWT assertion bằng private key | Quản lý JWKS, assertion lifetime, audience và replay |
| **mTLS** | Client xác thực bằng certificate trong TLS | PKI, certificate mapping, renewal/revoke |
| **none** | Public client không dùng secret tại token endpoint | PKCE và redirect binding đặc biệt quan trọng |

AS phải gắn client với phương thức đã đăng ký, kiểm tra đúng credential và không cho client tự hạ xuống phương thức yếu hơn. Không nhận client secret trong URL.

Public client không thể bảo vệ secret tĩnh nhúng trong browser/mobile. Dùng Authorization Code + PKCE và các cơ chế bảo vệ token phù hợp môi trường.

## 15. Sender-constrained token: mTLS và DPoP

Bearer access token có thể được sử dụng bởi bất kỳ bên nào nắm giữ token. Nếu token bị lộ, attacker có thể replay tới RS trong thời hạn token và phạm vi quyền.

**Sender-constrained token** gắn token với bằng chứng kiểm soát một khóa hoặc client identity:

- **mTLS-bound access token:** token gắn với certificate/client key; RS xác minh client certificate phù hợp với token.
- **DPoP:** client tạo proof JWT ký bằng private key, ràng buộc với HTTP method, URI và token theo profile; RS kiểm tra proof và chống replay theo cơ chế yêu cầu.

Các cơ chế này giảm rủi ro token bị đánh cắp rồi dùng từ một client khác, nhưng không bảo vệ nếu attacker kiểm soát cả client và private key hoặc có thể dùng thiết bị hợp lệ làm proxy. Vẫn cần TLS, key protection, nonce/replay controls và authorization.

## 16. Threat model cho authorization server

| Mối đe dọa | Cách xảy ra | Kiểm soát trọng tâm |
| --- | --- | --- |
| **Authorization code interception** | Code bị lộ ở browser, redirect hoặc log | PKCE, TLS, redirect URI exact match, code one-time |
| **Open redirect** | Redirect URI hoặc callback chuyển response sang domain attacker | Exact allowlist, không wildcard rộng |
| **Login CSRF** | Attacker gắn session/authorization response của họ vào browser nạn nhân | State, browser transaction binding, PKCE |
| **Authorization server mix-up** | Client nhầm issuer/AS trong môi trường nhiều IdP | Issuer validation, issuer identification và cấu hình endpoint cố định |
| **Token substitution** | Token sai audience/purpose được chấp nhận | Validate iss, aud, exp, type, scope và token profile |
| **Refresh token theft** | Token dài hạn bị lấy từ storage/log | Rotation, sender constraint, secure storage, revoke/reuse detection |
| **Client secret compromise** | Secret bị lộ trong app, CI, log hoặc repository | Public/confidential classification, secret manager, rotation |
| **Signing key compromise** | Attacker ký token giả | HSM/KMS, access control, rotation khẩn cấp, audit |
| **Consent phishing** | Người dùng bị dụ cấp scope rộng cho app giả | Hiển thị client/owner/scope rõ, admin policy và revoke |
| **Scope escalation** | AS cấp scope client không được phép hoặc RS hiểu sai | Scope allowlist, audience binding, least privilege |
| **Device flow phishing** | Attacker dụ user nhập code trên trang giả | Hiển thị client và quyền, code entropy, expiry và rate limit |
| **PAR/request URI replay** | Request URI bị lộ hoặc dùng sai client | TTL, client binding, one-time/defined use policy |
| **Introspection abuse** | Attacker dùng endpoint để dò token | Client auth, rate limit, response tối thiểu |
| **JWKS confusion** | RS tin key từ URL không đáng tin hoặc alg yếu | Issuer-bound metadata, allowlist và key rotation |
| **Tenant confusion** | Token hoặc consent bị dùng sai tenant | Issuer/tenant/audience binding và authorization |

## 17. Thiết kế và vận hành authorization server an toàn

Một số nguyên tắc cần duy trì:

1. Ưu tiên Authorization Code + PKCE cho đăng nhập tương tác.
2. Không dùng implicit grant hoặc Resource Owner Password Credentials cho ứng dụng mới.
3. Xác thực client tại token endpoint theo loại client và phương thức đăng ký.
4. Exact-match redirect URI; kiểm tra issuer, state, nonce và PKCE theo flow.
5. Phát hành token với scope, audience và thời hạn tối thiểu.
6. Bảo vệ refresh token và signing key; có rotation, revoke và incident procedure.
7. Dùng MFA/step-up theo rủi ro, nhưng giữ rõ authentication policy với authorization policy.
8. Tách tenant và môi trường; không dùng chung client secret/signing key tùy tiện.
9. Bảo vệ admin console, registration API, consent management và metadata.
10. Giám sát bất thường: code failure, refresh reuse, token issuance spike, consent changes, key rotation và client abuse.
11. Giữ đồng hồ hệ thống đồng bộ để xử lý expiry, nonce và assertion.
12. Kiểm thử cả happy path lẫn negative path trước khi enable production.

AS là hạ tầng bảo mật trọng yếu. Quyền quản trị AS, signing key và registration store thường có tác động rộng; cần phân quyền tối thiểu, audit không thể sửa tùy tiện và quy trình phục hồi khi hệ thống hoặc khóa ký gặp sự cố.

## 18. Checklist review authorization server

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Vai trò AS và RS có tách rõ? | Có hợp đồng token và trust boundary |
| Issuer có cố định và được tin? | Discovery/JWKS gắn với issuer đã cấu hình |
| Client được phân loại đúng? | Public client dùng PKCE, confidential client xác thực tại token endpoint |
| Redirect URI có exact match? | Không wildcard/open redirect |
| Authorization Code có one-time và TTL ngắn? | Có client/redirect/PKCE binding |
| State, nonce và issuer được kiểm tra? | Mỗi cơ chế dùng đúng mục đích |
| Grant types có tối thiểu? | Không bật flow lỗi thời không cần thiết |
| Scope/audience có giới hạn? | Least privilege, RS-specific audience |
| Token type có phân biệt? | ID token không dùng thay access token |
| Refresh token có bảo vệ? | Rotation/reuse detection, expiry và revoke |
| JWKS/signing key có lifecycle? | Private key bảo vệ, public key rotation và emergency plan |
| Introspection/revocation được bảo vệ? | Client auth, rate limit, cache policy rõ |
| Consent có minh bạch? | Client và scope hiển thị rõ, revoke được |
| Device/PAR flow có chống lạm dụng? | Binding, TTL, polling/rate limit |
| Sender constraint có cần? | Đánh giá DPoP/mTLS theo threat model |
| Logging có an toàn? | Không log code, secret, token thô hoặc private key |
| Có negative tests? | Sai issuer/audience, replay, expired, redirect mismatch, key revoke |

### Tình huống tự kiểm tra

**Tình huống 1:** Client nhận access token từ AS. Có thể dùng token đó để chứng minh người dùng đã đăng nhập với client không?

**Trả lời:** Không mặc nhiên. Access token dành cho resource server. Nếu cần kết quả xác thực người dùng trong OIDC, client kiểm tra ID token theo OIDC.

**Tình huống 2:** Một SPA được cấp client secret và dùng secret đó để gọi token endpoint. Có thể xem SPA là confidential client không?

**Trả lời:** Không. Secret trong browser có thể bị trích xuất. SPA là public client và nên dùng Authorization Code + PKCE.

**Tình huống 3:** RS xác minh chữ ký JWT nhưng bỏ qua audience. Rủi ro là gì?

**Trả lời:** Token được phát hành cho API/client khác có thể bị dùng sai nơi. RS phải kiểm tra audience và token purpose.

**Tình huống 4:** AS dùng refresh token rotation. Một refresh token cũ đã bị thay thế xuất hiện lần nữa. Nên làm gì?

**Trả lời:** Đây có thể là dấu hiệu token theft/replay. AS cần áp dụng reuse detection, thu hồi token family/session theo policy và ghi audit.

**Tình huống 5:** Client credentials token chứa sub là service account. Có thể coi đó là người dùng đã đăng nhập không?

**Trả lời:** Không. Token đại diện client/workload. Nếu cần user delegation, phải dùng flow hoặc token exchange có ràng buộc subject/actor phù hợp.

## 19. Ghi nhớ

**Authorization server là nơi áp dụng policy và phát hành token trong OAuth 2.0.** Nó xác định client, kiểm tra flow/redirect, xác thực user hoặc client theo trường hợp, xử lý consent và scope, rồi cấp token cho resource server phù hợp. OIDC bổ sung ID token và quy tắc xác thực danh tính; OAuth access token không tự trở thành bằng chứng đăng nhập cho client.

Một AS an toàn cần Authorization Code + PKCE, redirect URI chính xác, state/nonce/issuer validation, client authentication đúng loại, token scope/audience/lifetime tối thiểu, refresh rotation, key management, introspection/revocation và audit. Resource server vẫn phải tự xác minh token và authorization. Bảo vệ toàn bộ vòng đời từ đăng ký client, authorization request, token issuance đến refresh, revoke và incident response.
