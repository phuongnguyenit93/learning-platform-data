# Token substitution

## 1. Token substitution là gì và nguy hiểm ở đâu?

Trong chương **Threats** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, **token substitution** là họ tấn công trong đó một bên đưa **token hợp lệ về mặt kỹ thuật nhưng được phát hành cho mục đích, đối tượng nhận, client, issuer, principal hoặc ngữ cảnh khác** vào nơi đang chờ một token khác. Nếu bên nhận chỉ xác minh một vài thuộc tính như chữ ký, thời hạn hoặc `active=true`, nó có thể **đánh đồng hai token không có cùng quyền**.

Ví dụ một tổ chức vận hành:

~~~text
Authorization Server (AS): https://auth.example.test
OAuth Client:              employee-portal
Resource Server A:         hr-api
Resource Server B:         payroll-api
~~~

AS cấp token:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["hr-api"],
  "client_id": "employee-portal",
  "scope": "hr.profile.read",
  "exp": 1893456000
}
~~~

Đây là **JWT payload minh họa**, không phải JWT hoàn chỉnh đã ký. Khi token được gửi đến `payroll-api`, API B **phải từ chối** vì `aud` dành cho `hr-api`, dù token có chữ ký hợp lệ và cùng issuer. Nếu payroll chỉ dùng một câu lệnh “signature valid, expiry valid → allow”, nó đã biến credential cho HR thành credential dùng ở payroll: **cross-resource token substitution**.

Một ví dụ khác: Relying Party (RP) nhận **OIDC ID token** có `aud=web-client` để đăng nhập, rồi đưa ID token đó đến API như **OAuth access token**. Nếu API chấp nhận, nó đang bị **cross-token-type confusion**. Hệ thống cũng có thể nhầm token của **Alice với Bob**, tenant A với tenant B, client A với client B, hoặc token từ issuer không được phép với issuer tin cậy.

> **Nguyên tắc trung tâm:** Token không chỉ cần *hợp lệ*; nó phải **hợp lệ cho đúng nơi nhận, mục đích, principal và thao tác đang yêu cầu**. **Signature valid** hoặc **introspection `active=true`** là điều kiện cần trong những cơ chế tương ứng nhưng **không đủ** để cho phép API hay đăng nhập.

### Mục tiêu bài học

Sau bài, bạn có thể:

1. Phân biệt **token substitution**, **token replay**, **token theft**, **authorization code injection** và **confused deputy**.
2. Nhận biết những ranh giới **issuer (`iss`), recipient (`aud`), token type/profile (`typ`), client (`client_id`/`azp`), subject (`sub`), scope, tenant/resource**.
3. Giải thích vì sao **ID token, access token, refresh token, client assertion và DPoP proof không thể thay thế nhau**.
4. Thiết kế OAuth/OIDC validation với JWT ký số, opaque introspection và multi-issuer/multi-resource systems.
5. Hiểu cách **RFC 8707 Resource Indicators, RFC 8693 Token Exchange, sender-constrained AT (DPoP/mTLS)** hỗ trợ nhưng không thay thế audience/authorization checks.
6. Cấu hình Java/Spring Security Resource Server, OIDC client và kiểm thử negative cases chống substitution.

Các miền `example.test`, JWT claims, IDs và token trong ví dụ đều là **dữ liệu giả định**, không phải hệ thống hoặc credential production.

## 2. Phân biệt token substitution với replay và các tấn công gần giống

| Khái niệm | Hành động của attacker | Lỗi hệ thống bị khai thác | Ví dụ |
| --- | --- | --- | --- |
| **Token substitution** | Dùng token A thay token B mà bên nhận cần | Không ràng buộc đúng **mục đích/recipient/context** | AT `aud=hr-api` được payroll chấp nhận |
| **Bearer token replay** | Gửi lại **cùng một token** vốn được chấp nhận trước đó | Bearer credential bị sao chép, không sender-bound hoặc chưa revoked | AT của Alice bị đánh cắp và gửi lặp đến HR API |
| **Authorization code replay** | Đổi lại **cùng authorization code** | AS không bảo đảm code **single-use** | Code C1 được đổi thành hai bộ AT/RT |
| **Authorization code injection / login CSRF** | Đưa code của transaction khác vào callback của victim | RP thiếu `state`/PKCE/issuer binding | Alice bị đăng nhập vào account attacker |
| **Token theft** | Đánh cắp AT/RT/ID token hoặc proof key | Lộ credential ở logs/XSS/proxy/storage | RT bị lấy từ browser local storage |
| **Confused deputy** | Dụ một thành phần có quyền thực hiện thao tác trái ý định policy | Service sử dụng authority sai người/recipient | API gateway dùng service-admin AT để xử lý yêu cầu không được Alice phép |
| **Cross-JWT confusion** | Trình một JWT đúng chữ ký nhưng sai loại JWT | Validator dùng chung, không kiểm type/purpose | ID token được chấp nhận như OAuth AT |

Các loại tấn công **có thể đồng thời xảy ra**. Attacker có thể đánh cắp AT dành cho `hr-api` rồi **replay** nó tại `payroll-api`; phần **replay** là gửi lại credential, phần **substitution** là đưa credential sai audience vào hệ thống nhận.

### 2.1. Một token “đúng chữ ký” vẫn có thể sai ngữ cảnh

Giả sử hai JSON Web Tokens cùng được ký bởi AS `https://auth.example.test`:

~~~text
JWT A:
  typ = at+jwt
  aud = orders-api
  scope = orders.read

JWT B:
  typ = JWT
  aud = sales-dashboard
  purpose = OIDC ID token
~~~

Nếu `orders-api` chỉ verify `iss` + chữ ký, nó có thể nhận JWT B, dù B dành cho **RP đăng nhập**, không phải resource server.

### 2.2. “Có scope” chưa chắc “đúng nơi”

Hai API có thể cùng tên scope `read` hoặc `profile.read`:

~~~text
AT1: aud=inventory-api, scope=read
AT2: aud=finance-api,   scope=read
~~~

Scope không tự định danh resource. Resource server cần kiểm **audience và scope cùng nhau**, sau đó kiểm quyền dữ liệu/tenant. Không cho `finance-api` nhận AT1 chỉ vì chuỗi `read` giống nhau.

### 2.3. “Token từ OP của công ty” không phải giấy thông hành chung

Một authorization server/OpenID Provider có thể phát nhiều loại JWT cho nhiều consumers: ID token, OAuth AT, client assertion, logout token, JWT-based security event, v.v. **Cùng issuer hoặc cùng signing key không hợp nhất các mục đích này**. RFC 8725 gọi vấn đề này là **cross-JWT confusion** và khuyến nghị thiết kế validation rules loại trừ lẫn nhau.

## 3. Mô hình tin cậy: ai cấp, ai nhận, ai được hành động?

~~~mermaid
flowchart LR
    U["Alice / Resource Owner"] -->|"Login, consent/policy"| AS["Authorization Server / OP"]
    CL["employee-portal / OAuth Client"] -->|"Authorization Code + PKCE"| AS
    AS -->|"ID token: aud=employee-portal"| CL
    AS -->|"Access token: aud=hr-api"| CL
    CL -->|"Bearer AT"| HR["hr-api / Resource Server"]
    CL -.->|"WRONG: same AT"| PAY["payroll-api / Resource Server"]
    HR -->|"iss, aud, scope, typ, ACL"| HROK["HR action authorized"]
    PAY -->|"aud mismatch: reject"| NOPAY["No payroll access"]
~~~

Một **token trust decision** có nhiều tầng:

| Tầng | Câu hỏi bắt buộc | Bên trả lời |
| --- | --- | --- |
| **Issuer trust** | Token do **AS nào** phát hành, có nằm trong allowlist của ứng dụng không? | RP hoặc RS |
| **Cryptographic/state validity** | JWT ký đúng key/alg hay opaque token `active=true` từ AS đáng tin? | RP/RS, JWKS hoặc introspection |
| **Token purpose** | Đây là **API access token**, hay ID token/RT/client assertion/logout token? | RP/RS theo profile |
| **Recipient binding** | Token dành cho **chính RP/client hoặc RS** này? | RP/RS qua `aud`/resource contract |
| **Client/actor binding** | Token được cấp cho client nào, có actor/delegation đúng không? | AS + RP/RS policy |
| **Principal binding** | Token đại diện user/service nào và đúng login/session/request không? | RP/RS, app authz |
| **Permission binding** | Granted scopes/roles và tenant/object ACL có cho phép hành động cụ thể? | RS/domain authorization |
| **Freshness/revocation** | Token còn hạn, chưa bị chặn theo policy và có sender proof nếu bắt buộc? | RS/AS/status service |

**Không được dừng ở tầng chữ ký hoặc `active`** rồi kết luận authorization đã xong.

### 3.1. Các thành phần không được tin lẫn nhau mặc định

Một API gateway có thể terminate TLS và verify token, nhưng downstream vẫn cần policy tin cậy theo kiến trúc: audience dành cho **gateway hay từng API**, headers identity có được ký/bảo vệ hay không, service-to-service transport, issuer allowlist và object ACL. **“Cùng VPC” hoặc “cùng công ty” không thay verification.**

### 3.2. Quy tắc “ràng buộc đúng chiều”

Token được phát từ AS **cho một audience**. Bên nhận cần chứng minh:

\[
\text{expectedRecipient} \in \text{token.aud}
\]

khi profile sử dụng `aud`. Chiều đúng là **RS biết expected audience của mình trước**, rồi so với claim đã xác minh. Không lấy `aud` trong token làm cấu hình để quyết định API nào là expected recipient.

Tương tự, RS biết **trusted issuer** từ configuration; không tin `iss` chưa xác minh để tự tải JWKS/introspection URL tùy ý.

### 3.3. Chủ thể trong token khác quyền với từng bản ghi

Một AT có thể có:

~~~json
{
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "company-a"
}
~~~

Ngay cả sau khi ký/`active`, `orders-api` vẫn phải kiểm Alice có được đọc **order 1299** không, order thuộc tenant nào, và quyền bị rút/đổi chưa. Token substitution đôi khi biểu hiện ở mức **principal/object context** chứ không chỉ giữa các API.

## 4. Cross-resource access token substitution: nguồn gốc confused deputy

### 4.1. Attack trace kinh điển

~~~mermaid
sequenceDiagram
    autonumber
    participant CL as Malicious/compromised Client
    participant AS as Trusted AS
    participant HR as hr-api
    participant PAY as payroll-api
    CL->>AS: Valid OAuth grant for resource hr-api
    AS-->>CL: AT-HR: aud=hr-api, scope=hr.profile.read
    CL->>HR: GET /me with AT-HR
    HR-->>CL: Authorized HR data
    CL->>PAY: GET /payroll with AT-HR (substitution)
    PAY->>PAY: BAD: verify JWS signature + expiry only
    PAY-->>CL: Unauthorized payroll data
~~~

**Lỗi:** payroll tin **issuer key** nhưng không ràng buộc **recipient**. Nếu client có một token hợp lệ ở đâu đó, nó có thể mang token tới các APIs cùng issuer và thử quyền.

**Bảo vệ đúng:**

~~~text
payroll-api expected issuer  = https://auth.example.test
payroll-api expected audience = payroll-api
payroll-api required scope    = payroll.read
payroll-api domain ACL        = verified HR/payroll entitlement
~~~

Token `aud=hr-api` phải nhận `401 invalid_token` hoặc kết quả từ chối tương ứng ở token validation layer. Nếu AT đúng audience nhưng thiếu scope `payroll.read`, RS thường trả `403 insufficient_scope` theo RFC 6750; nếu scope đúng nhưng sai owner/tenant, RS vẫn từ chối theo domain policy.

### 4.2. Audience là ngăn cách *resource*, không phải tên thương mại

Hệ thống có thể có API aliases hoặc logical audiences:

~~~text
Inventory API expected audience = https://api.example.test/inventory
Payroll API expected audience   = https://api.example.test/payroll
~~~

Một `aud` cụ thể có thể là URI hay identifier theo AS/RS contract; **không suy rằng tất cả phải là hostname thật**. Kiểm tra **exact equality/membership theo profile**; không dùng `startsWith("https://api.example.test")`, domain suffix, regex quá rộng hoặc scope thay audience.

### 4.3. Token có nhiều audiences

AT có thể chứa:

~~~json
{"aud":["hr-api","employee-profile-api"]}
~~~

Nếu AS chủ động phát multi-audience token và cả hai APIs được phép, mỗi RS có thể xác minh mình nằm trong danh sách. Tuy nhiên, việc phát token cho **quá nhiều audiences** làm tăng blast radius nếu token lộ và giảm hiệu quả audience restriction. Security BCP khuyến nghị **recipient restriction**; khi có thể, xin token **audience hẹp** theo resource.

Một attacker không được tự viết `aud` vào token request để được cấp thêm tài nguyên; AS phải kiểm **client registration, grant, user/domain policy** và allowed resources.

### 4.4. RFC 8707 Resource Indicators

Trong OAuth, client có thể chỉ rõ resource mục tiêu khi AS hỗ trợ **RFC 8707**:

~~~http
GET /oauth2/authorize?response_type=code&client_id=employee-portal&scope=orders.read&resource=https%3A%2F%2Fapi.example.test%2Forders&state=<random-state>&code_challenge=<s256-challenge>&code_challenge_method=S256&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback HTTP/1.1
Host: auth.example.test
~~~

AS đánh giá resource được yêu cầu so với client/user policy, rồi phát AT có audience/resource binding phù hợp. `resource` là **đề nghị của client**, không phải quyền tự cấp audience tùy ý. RS đối chiếu `aud` thực tế với expected audience, **không** tin rằng client đã gửi resource request đúng.

### 4.5. Bẫy “one token for all microservices”

Một gateway nhận AT `aud=api-gateway` rồi forward nguyên token tới `payments-service`, `hr-service` và `inventory-service`. Nếu downstream chỉ tin gateway network, cần làm rõ liệu API services có **được phép coi gateway là recipient/authorization enforcement point** hay không. Các rủi ro:

- Dịch vụ downstream bị expose trực tiếp mà thiếu authentication.
- Gateway gửi token intended for one API tới API khác.
- Client đưa header `X-User`/`X-Scope` giả để impersonate gateway.
- Một token có quyền quá rộng bị lộ có thể truy cập nhiều services.

Hướng khắc phục là **mô hình trust rõ**: gateway verify expected audience và route policy; downstream nhận **internal service-bound token hoặc signed/trusted identity context**, có mTLS/network controls; khi cần delegation, AS phát **đúng token cho downstream** qua token exchange. Không giải quyết bằng cách bỏ mọi audience check.

## 5. Cross-token-type substitution: ID token, access token, refresh token và assertion

### 5.1. ID token OIDC không phải API access token

OIDC login có thể cấp ID token:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": "employee-portal",
  "exp": 1893456000,
  "iat": 1893455700,
  "nonce": "login-nonce-73"
}
~~~

**RP `employee-portal`** dùng ID token **đã được xác minh** để nhận diện Alice trong phiên login. **`orders-api`** không được chấp nhận ID token như AT, kể cả:

- Chữ ký của OP đúng.
- `sub` là Alice.
- Token có `exp` chưa hết.
- RP và RS cùng sử dụng JWKS của OP.

ID token có `aud` là **OAuth client/RP**, trong khi OAuth AT phải dành cho **resource API**. Nhận ID token như AT có thể làm lộ authentication assertion, bỏ qua scope/resource grants và tạo đường nâng quyền.

### 5.2. Refresh token không được dùng tại RS

Refresh token là credential để client xin AT mới tại **token endpoint của AS**. Nó có thể là opaque hoặc JWT theo AS; định dạng không thay mục đích. Resource server phải từ chối RT trong `Authorization: Bearer <refresh-token>`.

Nếu RS gọi introspection và AS trả một response có `active=true` cho RT, **RS vẫn không được coi RT là access token**. Đúng token **purpose** phải được ràng buộc trong AS introspection contract và RS validation.

### 5.3. Client assertion (`private_key_jwt`) không phải AT

Một confidential client có thể xác thực tại token endpoint bằng JWT assertion:

~~~json
{
  "iss": "client-service-1",
  "sub": "client-service-1",
  "aud": "https://auth.example.test/oauth2/token",
  "exp": 1893456000,
  "jti": "client-auth-assertion-1"
}
~~~

Assertion này chứng minh **client authentication** cho AS theo profile phù hợp, **không** cấp quyền gọi `orders-api`. Nếu RS cùng tin một số signing keys và chỉ nhìn chữ ký, nó có thể nhận client assertion như OAuth AT. Phải kiểm **issuer profile, token type, audience, scope và principal semantics**; JWT signature valid không thay AT authorization.

### 5.4. Logout Token/DPoP proof cũng không phải AT

- **OIDC Back-Channel Logout Token** là JWT event thông báo RP kết thúc session, có event claim riêng; không dùng làm bearer AT.
- **DPoP proof** là JWT chứng minh người gọi đang giữ một khóa và bind HTTP method/URI theo DPoP profile; nó **không** là access token cấp scopes.
- **Access token có `cnf`** biểu thị sender constraint cần kiểm cùng proof/certificate, không phải một DPoP proof độc lập là đủ.

Một parser chung có thể decode cả bốn, nhưng **validation profiles phải tách**: keys/issuers/typ/aud/required claims và endpoints khác nhau.

### 5.5. RFC 8725 và `typ`: explicit typing giảm cross-JWT confusion

JWT Best Current Practices (RFC 8725) khuyến nghị **explicit typing** và validation rules phân biệt cho các JWT application contexts. OAuth JWT access-token profile **RFC 9068** dùng header:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "as-key-2026"
}
~~~

Với profile sử dụng `at+jwt`, RS phải verify type theo profile, **không chỉ dựa vào ba đoạn Base64url**. Nhưng `typ=at+jwt` do attacker đặt trong header **chưa được xác minh**; phải verify JWS + trusted issuer/key rồi mới tin toàn bộ token. Không coi `typ` một mình thay audience/scope validation.

**Cẩn trọng tương thích:** Không phải mọi AS đều phát JWT AT theo RFC 9068 hoặc dùng `typ=at+jwt`. Nếu contract cho legacy JWT AT có type khác, cần profile validator riêng có **những điều kiện loại trừ ID token/client assertions một cách chắc chắn**; đừng tự bỏ type checks hoặc ngầm chấp nhận mọi JWT được OP ký.

## 6. Token substitution trong OIDC login: nhận đúng người và đúng phiên

Khi một Relying Party (RP) thực hiện OIDC Authorization Code Flow, token substitution không chỉ nhắm tới API; nó còn có thể làm RP **gắn session của user này vào kết quả xác thực của user khác** hoặc nhầm OP issuer.

### 6.1. ID token bị tráo giữa hai authorization transactions

Giả sử Alice và Bob cùng đăng nhập:

~~~text
Transaction T-A:
  state=S-A; nonce=N-A; expected issuer=OP-A
  ID token I-A: sub=alice, nonce=N-A, aud=client-X

Transaction T-B:
  state=S-B; nonce=N-B; expected issuer=OP-A
  ID token I-B: sub=bob, nonce=N-B, aud=client-X
~~~

Nếu RP nhận callback của T-A nhưng tạo login session bằng I-B chỉ vì chữ ký hợp lệ và `aud=client-X`, nó đã bị **ID-token substitution/session mix-up**. RP cần:

- Ràng buộc callback vào browser authorization transaction bằng `state`, và kiểm issuer theo flow/mix-up protection.
- Bảo vệ `code_verifier` đúng transaction; AS kiểm PKCE và code binding.
- Kiểm **ID token signature, `iss`, `aud`, `exp`, `iat` và `nonce` khi đã gửi/yêu cầu** cùng những điều kiện OIDC liên quan (`azp`, `auth_time`...).
- Tạo session theo **`(iss, sub)` đã xác minh**, không theo email từ response ngoài.

Lưu ý: `nonce` trong OIDC Authorization Code Flow có thể là optional theo một số trường hợp của Core, nhưng nếu RP **đã gửi nonce** thì phải kiểm đúng khi ID token trả về. Một policy có thể yêu cầu nonce cho mọi login; không gỡ kiểm nonce chỉ vì flow là code+PKCE.

### 6.2. `state`, PKCE và nonce giải quyết ba việc khác nhau

| Cơ chế | Ngăn chủ yếu | Không thay thế |
| --- | --- | --- |
| OAuth `state` | Callback/login CSRF, transaction mix-up tại RP | ID token cryptographic validation |
| PKCE `S256` | Code interception/redeem bởi bên không có verifier | ID token issuer/audience/nonce checks |
| OIDC `nonce` | Token replay/substitution vào authentication transaction | AS authorization code single-use |
| OIDC `iss` validation | Token đến từ đúng OP | Đúng user session/tenant/role |
| `aud`/`azp` khi áp dụng | Token dành cho đúng RP/client | Token có còn session-bound hoặc user có role không |

Một implementation chỉ so `nonce` nhưng bỏ `iss` có thể nhận token từ issuer lạ cùng cấu trúc. Một implementation chỉ so `state` nhưng không verify ID token signature cũng không an toàn. **Phải có chuỗi xác minh đầy đủ**.

### 6.3. `azp` và nhiều audiences trong ID token

OIDC ID token có thể có `aud` dạng array. Nếu nhiều audiences, OIDC Core có các quy tắc liên quan **`azp` (authorized party)**. RP không nên:

~~~text
if (aud contains "some-client-in-company") allow login;
~~~

Mà phải so với **client_id chính mình** và kiểm `azp` khi OIDC profile yêu cầu, cùng issuer/signature/time/nonce. `azp` **không phải scope** và không cho phép RP dùng ID token của client B tại client A.

### 6.4. UserInfo `sub` substitution

RP đã xác minh ID token:

~~~json
{"iss":"https://auth.example.test","sub":"alice","aud":"employee-portal"}
~~~

Sau đó gọi UserInfo bằng OAuth AT nhưng do cache key thiếu user/AT, nhận:

~~~json
{"sub":"bob","email":"alice@example.test"}
~~~

**OIDC RP bắt buộc so UserInfo `sub` khớp chính xác với ID token `sub`** và **không dùng UserInfo response** khi khác. Email giống nhau không đủ; email có thể đổi, bị tái sử dụng hoặc không được xác minh như identity key. Cần cache UserInfo ràng buộc issuer/subject/token/session và áp data-minimization policy.

### 6.5. Account linking bằng email là substitution theo danh tính

Một RP cho phép “Đăng nhập bằng công ty” từ nhiều issuers. Nó dùng email làm khóa và ghép tài khoản:

~~~text
OP-A: iss=A, sub=alice-123, email=manager@example.test
OP-B: iss=B, sub=unknown-999, email=manager@example.test
→ RP gộp vào cùng local admin account.
~~~

Nếu OP-B không được tin để chứng minh quyền sở hữu tài khoản tại OP-A, attacker có thể **substitute identity** bằng claims superficially giống nhau. Key external identity nên dùng **`(issuer, subject)`** đã verify; account linking yêu cầu proof/approval độc lập, không tự suy từ email hoặc `email_verified`. Role/tenant cũng phải đến từ nguồn được phê duyệt, không từ text claims tùy ý.

### 6.6. Authorization response mix-up

RP hỗ trợ OP-A và OP-B nhưng callback không ràng buộc expected issuer và client registration theo `state`. Attacker khiến RP gửi code/PKCE verifier dành cho OP-A sang **token endpoint của OP-B**; OP-B có thể thu credential hoặc trả token khác ý định.

Defense:

1. Mapping `state → expected issuer, client registration, redirect, verifier, nonce`.
2. Đối chiếu authorization response `iss` khi RFC 9207/profile yêu cầu hoặc có hỗ trợ.
3. Chỉ gọi **trusted token endpoint** của registration gốc.
4. Xác minh ID token `iss`, `aud`, `nonce` theo transaction.
5. Không thử tuần tự nhiều OP endpoints khi token exchange lỗi.

Đây là **mix-up/token-substitution related threat**, không được giải quyết bằng việc “cả hai OP đều được công ty chấp nhận” nếu policy phân biệt tenant/client/identity.

## 7. Multi-issuer, JWKS và algorithm confusion

### 7.1. Kịch bản `kid` giống nhau giữa hai issuers

~~~text
Issuer A: https://auth-a.example.test  → JWKS { kid: "key-1", key: A }
Issuer B: https://auth-b.example.test  → JWKS { kid: "key-1", key: B }
JWT B:    iss = B, kid = "key-1", aud = orders-api
~~~

Nếu một validator ghép mọi keys thành `Map<kid, PublicKey>` toàn cục, `kid` collision có thể chọn sai key hoặc kết hợp issuer/trust boundary không đúng. **Key ID không phải định danh toàn cục**; nó có ý nghĩa trong **trusted issuer/key set** và phải đi cùng configured algorithm policies.

### 7.2. Không lấy JWKS URI từ token chưa verify

Attacker gửi JWT header:

~~~json
{
  "alg": "RS256",
  "kid": "attacker-key",
  "jku": "https://attacker.example.test/jwks"
}
~~~

Nếu API tự tải `jku` rồi dùng public key của attacker, attacker có thể tạo JWT `iss`/`aud`/`scope` tùy ý và qua chữ ký. Đây là **key trust/SSRF flaw**, có thể trở thành token substitution vì một attacker-signed token được chấp nhận như AS token.

RS phải có:

- Danh sách **expected issuers** và **JWKS endpoints đã được cấu hình/phê duyệt**.
- Kết nối HTTPS đúng chứng chỉ và hostname cho JWKS.
- **Algorithm allowlist**, không theo `alg` tự chọn; không chấp nhận `none` cho signed JWT AT.
- Key selection trong **issuer-specific trust set**; không cho `kid` thay issuer.
- Validation profile phù hợp `typ`, `aud` và claims, ngay cả sau khi signature valid.

### 7.3. Multiple trusted issuers không có nghĩa issuer nào cũng cấp mọi resource

Một API có thể chấp nhận AT từ AS nội bộ và AS đối tác:

~~~text
Issuer internal:
  allowed audiences = [orders-api]
  allowed scopes    = [orders.read, orders.write]

Issuer partner:
  allowed audiences = [orders-api]
  allowed scopes    = [orders.read]
  authorized client types = partner integrations
~~~

Nếu validator chỉ kiểm token issuer thuộc {internal, partner} rồi cho mọi `orders.write`, partner có thể dùng token có claim tương tự để nâng quyền. Cần policy **issuer × audience × scope × client × tenant**; không ghép claim semantics giữa issuers khi chưa có hợp đồng ánh xạ.

### 7.4. Algorithm confusion và type confusion khác nhau nhưng cộng hưởng

- **Algorithm confusion:** parser dùng sai thuật toán/khóa, khiến chữ ký giả mạo có thể được chấp nhận.
- **Token-type confusion:** parser verify đúng chữ ký nhưng sử dụng JWT không đúng mục đích.
- **Issuer confusion:** token ký hợp lệ bởi issuer B nhưng API yêu cầu issuer A.

Một validator an toàn phải chặn **cả ba**; sửa `typ` mà vẫn follow untrusted `jku` không đủ, và khóa đúng mà bỏ `aud` cũng không đủ.

### 7.5. Rotation/compromise không được làm fail-open

Khi AS rotate signing keys, RS tải trusted JWKS mới có kiểm soát. Token có `kid` lạ khi JWKS endpoint đang outage phải **bị từ chối nếu không thể verify bằng khóa tin cậy**, không được fallback “mọi token từ IP nội bộ đều tin”.

Khi key bị compromise, token substitution/forgery trở nên nguy hiểm hơn; cần incident plan rút key, revoke/denylist tokens theo policy và kiểm tra audience/type/issuer sau rotate. **Key rotation không thay account, tenant hoặc object authorization**.

## 8. Token substitution qua subject, client, tenant và quyền nghiệp vụ

### 8.1. Subject mismatch: token của Bob dùng trong phiên Alice

Một BFF có server-side token cache sai:

~~~text
cacheKey = "orders-api"
cacheValue = access token for Bob
~~~

Khi Alice gửi request, BFF lấy token của Bob và gọi orders. RS verify token hợp lệ và trả dữ liệu của Bob; ứng dụng có thể hiển thị data sai user. Đây là **cross-user token substitution** do cache/session binding thiếu. Đừng chỉ tập trung attacker gửi token trực tiếp: **hệ thống nội bộ cũng có thể tự tráo token**.

Cache key cần phản ánh **issuer, client/authorized-client registration, subject/actor, session/tenant, resource/audience, scopes, grant/version**, tùy loại token. Token cache phải được bảo vệ, không chứa raw bearer tokens trong metric labels.

### 8.2. Tenant substitution

~~~text
AT:
  iss = trusted AS
  sub = alice
  aud = orders-api
  scope = orders.read
  tenant_id = company-a

Request:
  GET /tenants/company-b/orders
~~~

Nếu RS chỉ kiểm `scope=orders.read` mà không enforce tenant của token/principal đối với **order records thực tế**, Alice có thể đọc tenant B. Token không thể tự được “đổi tenant” bằng query/header:

~~~http
X-Tenant-Id: company-b
~~~

chỉ vì client gửi. Tenant context phải đến từ verified token/trusted session/domain mapping, và RS xác minh object owner/tenant bằng data store. **Token hợp lệ ở tenant A không tự cấp quyền tenant B.**

### 8.3. Client substitution và machine identity

AS cấp AT:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "service-inventory-worker",
  "client_id": "inventory-sync",
  "aud": ["inventory-api"],
  "scope": "inventory.write"
}
~~~

Đó có thể là **Client Credentials** token cho service, không mang một end-user Alice. Nếu backend nhận token này như **user-delegated token** và cho phép hành động “thay Alice”, đó là confused deputy. RS phải hiểu **token grant/principal model** theo AS contract và domain authorization.

Không tự hiểu `client_id` là user, `sub` luôn là người, hoặc service AT là quyền admin phổ quát.

### 8.4. Same subject không đồng nghĩa cùng authority

Một người Alice có thể nhận:

~~~text
AT1: client=employee-portal, scope=profile.read, aud=hr-api
AT2: client=finance-console, scope=invoice.approve, aud=finance-api
~~~

`sub` giống nhau không làm AT1 có quyền `invoice.approve`. AuthZ phụ thuộc **token grant context, resource, scopes, client type/role/actor và domain policy**.

### 8.5. Token exchange không được làm mất ranh giới actor/subject

Ở hệ thống microservices, service A nhận user AT `aud=service-a` rồi cần gọi service B. **Không** forward nguyên AT đó như thể `aud=service-b`. Khi cần bảo toàn delegation/actor, xem xét **OAuth 2.0 Token Exchange (RFC 8693)**:

~~~text
Incoming:
  Alice AT -> service-a, aud=service-a

Token exchange request by service-a to trusted AS:
  subject_token = Alice's token
  requested resource/audience = service-b
  actor/client context = service-a (when profile supports)

Outgoing:
  New AT -> service-b
  aud=service-b
  scope constrained by policy
  subject/actor preserved and validated as agreed
~~~

Token exchange **không tự động cấp quyền**: AS phải kiểm client actor, subject token, target resource, allowed scopes và anti-delegation escalation. RS B vẫn kiểm token type, issuer, audience, scope và ACL/actor semantics.

### 8.6. Identity mapping và pairwise subject

OIDC có thể dùng **pairwise `sub`** khiến cùng user có `sub` khác nhau giữa sectors/RPs. Không tự ghép identities ở các issuers/sectors chỉ bằng email hoặc giá trị `sub` tương tự. Một mapping sai có thể dẫn đến token substitution giữa users hoặc accounts đã từng được cấp cùng email.

## 9. Opaque token và RFC 7662 introspection: `active=true` chưa đủ

### 9.1. Introspection có thể trả metadata khác nhau theo caller

Một RS có thể gửi opaque AT tới AS theo **RFC 7662**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <authorized-resource-server-credential>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>&token_type_hint=access_token
~~~

Response minh họa:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "client_id": "employee-portal",
  "sub": "alice",
  "token_type": "Bearer",
  "aud": ["hr-api"],
  "scope": "hr.profile.read",
  "exp": 1893456000
}
~~~

`active` là trường **bắt buộc** của RFC 7662 response; `iss`, `aud`, `scope`, `sub` và các metadata khác là **tùy chọn theo AS/token/caller contract**. `active=true` có nghĩa token được AS coi active theo ngữ cảnh introspection, **không chứng minh** token dành cho RS đang hỏi hay client có quyền object.

### 9.2. Introspection substitution

~~~text
Token T1:
  AS knows aud=hr-api, scope=hr.profile.read.

payments-api:
  Introspects T1 with overprivileged RS credentials.
  AS returns {"active":true, "aud":["hr-api"], ...}.

BAD payments-api:
  if active then allow /payments.
~~~

Vì payments bỏ `aud`, nó chấp nhận token sai resource dù không có JWT local validation. **Opaque format không tự bảo vệ chống cross-resource token substitution**.

### 9.3. Nếu `aud` không có trong introspection response

Theo RFC 7662, AS không bắt buộc trả `aud`. Có hai cách tiếp cận bảo mật **khi contract thực sự cho phép**:

1. **AS trả `aud`/resource metadata** và RS kiểm expected recipient.
2. **AS ràng buộc introspection caller vào resource**: chỉ trả `active=true` cho RS khi token thuộc đúng resource mà caller được phép hỏi; RS identity/credential được bảo vệ và behavior đã kiểm thử.

Nếu AS trả `active=true` cho mọi token cùng issuer mà không có `aud` hoặc caller-to-resource binding đáng tin, RS **không có bằng chứng** token dành cho mình; phải fail closed hoặc sửa AS contract. Không dùng `scope` cùng tên làm audience substitute.

### 9.4. `token_type_hint` là hint, không chứng minh purpose

`token_type_hint=access_token` trong introspection request chỉ giúp AS chọn tra cứu. Attacker có thể gửi RT với hint `access_token`. AS/RS phải tự phân biệt loại token thực tế; RS không được chấp nhận RT chỉ vì response `active=true` mà thiếu purpose contract.

### 9.5. Introspection cache cũng có thể gây substitution

Nếu shared cache dùng key:

~~~text
cache[token_fingerprint] → active=true, principal=alice
~~~

mà không phân biệt **issuer, authorized RS caller, expected audience, token purpose và policy version**, kết quả introspection tại HR có thể bị reuse tại payroll. Cache nên phân vùng theo trust context và bảo vệ token fingerprint/raw response; positive status TTL phải bị chặn bởi expiry và revocation freshness budget.

### 9.6. Fail closed khi AS không reachable

Nếu TLS handshake/certificate validation, client authentication, timeout hoặc introspection response schema lỗi:

- Không tự cho `active=true` hoặc bỏ audience check.
- Dùng previously approved cache **chỉ khi vẫn nằm trong freshness/expiry/security budget**, không stale vô hạn.
- Với high-risk routes cần live validation, trả lỗi service/không cung cấp dữ liệu khi không thể xác minh.
- Không thử introspection tuần tự ở AS lạ với cùng raw token và RS secret.

## 10. Sender-constrained tokens giảm replay nhưng không tự sửa substitution

### 10.1. DPoP (RFC 9449)

DPoP ràng buộc access token với một public key; client gửi DPoP proof JWT chứng minh possession và bind method/URI/token theo profile. Resource server kiểm:

- AT được AS phát với `cnf.jkt` (hoặc metadata binding phù hợp) đến public key của holder.
- DPoP proof signature/key khớp token binding.
- `htm`, `htu`, `iat`, `jti` và nonce khi được yêu cầu; `ath` khi proof dùng cùng AT theo profile.
- Replay cache/time window cho proof và audience/scope/token purpose của AT.

**Không suy** “DPoP proof đúng → AT dành cho mọi API”. Một proof cho `payments-api` không làm AT `aud=hr-api` hợp lệ ở payments; RS vẫn phải kiểm `aud`, issuer, scope và ACL.

### 10.2. Mutual TLS certificate-bound AT (RFC 8705)

Với mTLS, AS có thể gắn token với client certificate (`cnf.x5t#S256` cho JWT AT hoặc introspection metadata). RS phải xác minh TLS client certificate thực tế và binding:

~~~text
AT.cnf["x5t#S256"] == BASE64URL(SHA256(DER(client certificate)))
~~~

Việc TLS client authentication thành công **không tự chứng minh audience/scope**. Một token dành cho payroll vẫn không dùng được ở HR dù cùng certificate holder. Nếu TLS terminate tại gateway/mesh, chain-of-trust để đưa chứng thư đến RS phải được bảo vệ; không tin header `X-Client-Cert` do client tự gửi.

### 10.3. Sender constraint khác user/tenant ownership

DPoP/mTLS chứng minh **bên gọi giữ khóa/chứng thư** gắn với token, không chứng minh caller có quyền đọc bản ghi Bob hoặc truy cập tenant khác. RS vẫn kiểm domain ACL. Nếu attacker đánh cắp cả token và private key, proof-of-possession cũng có thể bị mạo danh; cần storage/rotation/revocation controls.

### 10.4. PKCE cũng không phải audience restriction

PKCE `S256` bảo vệ **authorization code exchange** tại AS. Sau khi đã nhận AT, việc client gửi nó tới **sai RS** không được PKCE chặn. Cần **audience/resource binding**, token type checks và API authorization. Không ghi “hệ thống đã có PKCE nên không thể bị token substitution”.

## 11. Java/Spring Security: Resource Server JWT chống token substitution

Đối với `orders-api` nhận **JWT access token ký JWS**, ít nhất cần:

1. **Trusted issuer** cố định/allowlisted.
2. JWKS/algorithm trust và **chữ ký** hợp lệ.
3. **`aud`** đúng resource.
4. **Token purpose/profile**, ví dụ `typ=at+jwt` nếu AS tuân RFC 9068.
5. `exp`, `nbf`, `iat` khi được profile yêu cầu và clock skew hợp lý.
6. **Granted scopes** của API và domain ACL độc lập.

### 11.1. Cấu hình issuer cơ bản

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Trong các phiên bản Spring Security hỗ trợ, cấu hình `issuer-uri` giúp Resource Server phát hiện JWKS theo trusted issuer và verify các điều kiện mặc định tương ứng. **Không tự suy rằng `issuer-uri` một mình đã kiểm audience và phân biệt JWT AT với OIDC ID token**; phải thêm validator/profile policy rõ.

### 11.2. Validator `iss` + `aud` và token purpose

Ví dụ Java/Spring Security 6.x theo contract **AS phát JWT AT chuẩn RFC 9068**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersTokenValidation {
    private static final String ISSUER =
            "https://auth.example.test";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder ordersJwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(
                        "https://auth.example.test/oauth2/jwks")
                // Spring versions supporting this flag:
                // let custom validator enforce the AT "typ".
                .validateType(false)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Wrong audience for orders-api",
                                null));

        OAuth2TokenValidator<Jwt> accessTokenType = jwt -> {
            Object typ = jwt.getHeaders().get("typ");
            boolean isAtJwt =
                    "at+jwt".equals(typ)
                    || "application/at+jwt".equals(typ);
            return isAtJwt
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Wrong JWT token type",
                                    null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience, accessTokenType));
        return decoder;
    }
}
~~~

**Điểm quan trọng của ví dụ:**

- `JwtValidators.createDefaultWithIssuer` xử lý các claims chuẩn theo Spring implementation/version, **không thay** audience hoặc token-purpose policy.
- `getAudience().contains("orders-api")` kiểm **recipient membership chính xác**, không substring/hostname prefix.
- `typ` chỉ được tin **sau khi JWT được signature-verified** bởi decoder. Khi thư viện có built-in type verification, phải cấu hình sao cho lớp type check chấp nhận **đúng RFC 9068 AT types** và custom validator được chạy.
- `validateType(false)` là **API phụ thuộc phiên bản Spring Security/Nimbus**; một số phiên bản không có hoặc xử lý typ khác. Cần đối chiếu tài liệu đúng phiên bản, điều chỉnh builder/type verifier, và tích hợp test thật cho ID token rejection. **Không tắt type validation rồi bỏ luôn custom check.**
- Đây là ví dụ policy, chưa phải toàn bộ RFC 9068 validator. Với AT theo chuẩn RFC 9068, còn cần kiểm **required claims/format/alg/`client_id`/lifetime** theo profile và trust agreement, đồng thời lựa chọn allowed JWS algorithms phù hợp.

Nếu AS đang phát **legacy JWT AT không có `typ=at+jwt`**, phải thiết kế validator **riêng cho loại token đó** với tiêu chí mutually exclusive với ID token và các JWT khác. Không gộp tất cả tokens bằng một bộ tiêu chí yếu.

### 11.3. Chỉ cấp quyền từ granted scope trong token đã xác minh

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain ordersSecurityFilterChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/v1/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll());

    http.oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

Đây là API skeleton: cần điều chỉnh CSRF/session/error handling theo kiến trúc và phiên bản Spring. Khi access token đã verify có `scope="orders.read"`, Spring JWT authorities mapping phổ biến tạo `SCOPE_orders.read`. Tuy nhiên, phải kiểm **schema/claim-to-authorities mapping** theo issuer/profile; tuyệt đối không lấy quyền từ query `?scope=orders.write`, raw unverified JWT payload hoặc `X-Roles` do client gửi.

### 11.4. Object-level authorization chống cross-user/tenant

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderPolicy.canRead(authentication, #orderId)")
public OrderView getOrder(String orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();
    return OrderView.from(order);
}
~~~

`orderPolicy`, `orderRepository`, `OrderView` là domain abstractions được triển khai riêng. Cần bật `@EnableMethodSecurity`, bảo đảm Spring phát hiện tên tham số `orderId`, và policy đọc **verified principal/tenant/client/actor** cùng **tenant của order từ database**.

Không dùng:

~~~java
// Anti-pattern: scope alone is not object authorization.
if (jwt.getClaimAsString("scope").contains("orders.read")) {
    return orderRepository.findById(orderId).orElseThrow();
}
~~~

Vì `contains` có thể substring-match `myorders.read` và không kiểm owner/tenant. Parse scope thành **tập quyền chính xác**, rồi áp ACL riêng.

### 11.5. Multi-issuer token validation

Nếu `orders-api` hỗ trợ nhiều AS, nên có **trusted issuer registry**:

~~~text
orders-api trusted issuers:
  internal-as:
    issuer=https://auth.example.test
    allowed audience=orders-api
    allowed scopes=[orders.read, orders.write]
    allowed algorithms=[RS256]  (example)

  partner-as:
    issuer=https://partner-id.example.test
    allowed audience=orders-api
    allowed scopes=[orders.read]
    allowed client policy=[approved-partner-clients]
~~~

Đây là **pseudoconfiguration**, không phải file Spring nạp trực tiếp. Nếu dùng Spring `JwtIssuerAuthenticationManagerResolver` hoặc cấu hình đa decoder, **chỉ cho phép** issuer thuộc registry; **không** dùng issuer bất kỳ trong JWT chưa verify để tự discover endpoint rồi tin nó. Sau khi chọn decoder tương ứng từ allowlist, verify chữ ký và `iss` trong token cùng audience/type/permission policy của issuer đó.

### 11.6. Negative test thiết yếu cho decoder

Phải có **positive control**:

~~~text
JWT AT valid:
  signed by trusted AS,
  iss=expected,
  aud=orders-api,
  typ=at+jwt,
  exp valid,
  scope=orders.read
  → token layer ACCEPT, then object ACL.
~~~

Sau đó thay **một** thuộc tính:

~~~text
Same signer, aud=hr-api       → reject audience mismatch.
Same signer, typ=JWT ID token → reject token type/purpose.
Same claims, attacker key     → reject signature/trust.
Same issuer/aud, exp past     → reject expiry.
Same token, other tenant obj  → reject ACL.
~~~

Nếu cả positive và negative đều bị 401 vì JWKS unavailable, test **chưa chứng minh** audience/type validator đúng.

## 12. Java/Spring Security: opaque introspection chống substitution

### 12.1. Cấu hình trusted endpoint/RS credentials

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: orders-api-resource-server
          client-secret: INJECTED_RS_INTROSPECTION_SECRET
~~~

`INJECTED_RS_INTROSPECTION_SECRET` là placeholder; RS credential phải lấy từ secret manager, không commit vào repository/log. AS giới hạn **caller được phép introspect tokens**, và RS chỉ tin HTTPS endpoint đã cấu hình, không dùng `iss`/URL do client cung cấp.

### 12.2. Bật opaque token introspection

~~~java
@Bean
SecurityFilterChain ordersOpaqueFilterChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/v1/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll());
    http.oauth2ResourceServer(oauth ->
            oauth.opaqueToken(Customizer.withDefaults()));
    return http.build();
}
~~~

Đây là cấu hình **thay thế** JWT `ordersSecurityFilterChain` ở mục 11, **không** copy cả hai vào cùng matcher để tranh chấp. Một token dạng opaque không có chữ ký JWT để resource server tự kiểm; Spring introspector hỏi AS và xây principal/authorities theo response/profile.

### 12.3. Bắt buộc audience theo introspection contract

Ví dụ **decorator** sau giả định AS trả `iss` và `aud` trong active introspection response:

~~~java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class ResourceBoundIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    ResourceBoundIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal p =
                delegate.introspect(token); // Delegate validates active.

        Object issuer = p.getAttribute("iss");
        Object audience = p.getAttribute("aud");

        if (!"https://auth.example.test".equals(issuer)
                || !audienceContains(audience, "orders-api")) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error(
                            "invalid_token",
                            "Introspection token resource mismatch",
                            null));
        }
        return p;
    }

    private boolean audienceContains(
            Object raw, String expected) {
        if (raw instanceof String s) {
            return expected.equals(s);
        }
        if (raw instanceof Collection<?> list) {
            return list.contains(expected);
        }
        return false;
    }
}
~~~

Có thể kết nối với `NimbusOpaqueTokenIntrospector` hoặc một delegate phù hợp phiên bản Spring:

~~~java
@Bean
OpaqueTokenIntrospector resourceBoundIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
        String uri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
        String rsId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
        String rsSecret) {

    OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(uri, rsId, rsSecret);
    return new ResourceBoundIntrospector(delegate);
}
~~~

Đây là Java/Spring 6.x **minh họa**, cần imports `@Bean`, `@Value` và class introspector, đúng dependency/version. Trong một số phiên bản Spring, builder/API của introspector thay đổi; phải kiểm tài liệu runtime. Cũng cần validate **token purpose, `scope`, `exp`/`nbf` theo contract** và identity/tenant domain ACL; decorator trên **chỉ** minh họa `iss`/`aud`.

**Chú ý chuẩn RFC 7662:** `iss`, `aud` là **metadata tùy chọn**; yêu cầu chúng ở đây là **contract bảo mật riêng của orders-api**. Nếu AS không trả nhưng đảm bảo chỉ `active=true` cho đúng RS resource (RS-specific caller restriction), có thể triển khai policy khác **đã kiểm thử**. Nếu không có cả metadata lẫn caller binding, không bỏ audience restriction chỉ để hết lỗi.

### 12.4. Không dùng `active=true` rồi tạo quyền giả

Đoạn sai:

~~~java
// Vulnerable design; do not deploy.
if (response.active()) {
    return principalWithAllScopes();
}
~~~

Đúng hơn: chỉ map **granted scopes** trong response được AS xác thực; so `aud`/resource/purpose rồi áp route permission và ACL. Nếu AS trả `scope="orders.read"`, API không được thêm `orders.write` bằng role default “trusted internal client”.

### 12.5. Stale cache và trust context

Một cache introspection có `active=true` cho token A khi được `orders-api` hỏi **không** được đem tái sử dụng cho `payroll-api`. Cache key/value cần ràng buộc:

~~~text
AS issuer and introspection endpoint identity
authenticated RS caller identity
expected resource/audience
token fingerprint (protected; not raw log key)
token purpose and relevant profile/version
positive status TTL <= token exp and revocation budget
~~~

Phân vùng cache trust context và bảo vệ token fingerprint tránh leakage; xử lý AS outage fail closed, không thử AS khác để tìm response `active=true`.

## 13. Java/Spring OIDC client: tránh tráo ID token và principal

### 13.1. Đăng ký đúng OIDC provider/client

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-op:
            issuer-uri: https://auth.example.test
        registration:
          employee-portal:
            provider: company-op
            client-id: employee-portal
            client-secret: INJECT_FROM_SECRET_MANAGER
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
~~~

Spring Security `oauth2Login` hỗ trợ OIDC login và ID-token validation theo cấu hình/phiên bản. Chỉ dùng **expected issuer** từ trusted registration; không tự tạo dynamic issuer/redirect từ user email hoặc browser query.

### 13.2. RP session key từ `iss` + `sub` đã xác minh

~~~java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

record ExternalIdentity(String issuer, String subject) {}

ExternalIdentity externalIdentity(OidcUser user) {
    String issuer = user.getIdToken()
            .getIssuer().toString();
    String subject = user.getIdToken().getSubject();
    return new ExternalIdentity(issuer, subject);
}
~~~

`OidcUser` phải đến từ Spring OIDC authentication pipeline **đã verify ID token**; không tạo thủ công từ unverified request. `(iss, sub)` giúp tránh trùng ID giữa OPs; nếu hệ thống cho phép account linking, cần verification/approval riêng thay vì tự ghép bằng `email`.

### 13.3. Kiểm UserInfo `sub` khi tích hợp tùy chỉnh

Nếu RP có custom UserInfo HTTP client/cache ngoài Spring provider, luôn kiểm:

~~~java
String expectedSub = verifiedIdToken.getSubject();
String userInfoSub = userInfoClaims.get("sub");

if (!expectedSub.equals(userInfoSub)) {
    throw new SecurityException(
            "UserInfo subject does not match ID token");
}
~~~

Các biến là **domain data đã được parse từ nguồn tin cậy**. Ví dụ này chỉ minh họa kiểm `sub`; API còn phải bảo vệ UserInfo endpoint/AT, TLS, issuer/session binding, consent và cache key. Không dùng email trùng nhau làm ngoại lệ để chấp nhận `sub` sai.

### 13.4. Không đưa ID token vào API `Authorization`

Một BFF có thể lưu cả ID token và OAuth AT. Khi gọi `orders-api`:

~~~text
GOOD:
  Authorization: Bearer <access-token-for-orders-api>

BAD:
  Authorization: Bearer <OIDC-ID-token-for-employee-portal>
~~~

Ứng dụng cần xác định **token store theo purpose/audience**, không đặt một field `jwt` toàn cục dùng cho mọi outbound request. Các HTTP clients nên chọn token thông qua **resource-specific authorized-client manager**/mapping thay vì luôn lấy `idToken.getTokenValue()`.

### 13.5. Các route khác nhau cần token khác nhau

~~~text
GET /orders:
  outgoing aud = orders-api, scope=orders.read

GET /payments:
  outgoing aud = payments-api, scope=payments.read

GET /userinfo:
  outgoing access token bound to UserInfo endpoint/OP contract
~~~

Không dùng ID token hoặc UserInfo AT cho mọi API chỉ vì cùng OP. Nếu AS hỗ trợ resource indicators/token exchange, client yêu cầu đúng resource và AS áp grants/consent policy.

## 14. Phòng chống substitution từ lúc AS phát token

Resource Server là nơi cuối cùng phải từ chối token sai recipient, nhưng **Authorization Server** có thể giảm đáng kể khả năng token bị dùng nhầm bằng cách phát hành token **đúng mục đích, audience hẹp và grants rõ ràng**.

### 14.1. Một authorization grant không cấp quyền cho mọi resource

AS nhận authorization request:

~~~text
client_id = employee-portal
requested_scope = orders.read
requested_resource = https://api.example.test/orders
authenticated_user = alice
tenant = company-a
~~~

AS phải đánh giá:

- Client registration có được xin `orders.read` tại `orders-api` không?
- Alice (hoặc service principal) có quyền yêu cầu delegated scope đó không?
- Consent/admin approval/tenant policy có cho mục đích này không?
- Resource indicator có thuộc danh sách AS tin và allowed audience không?
- Có cần sender constraint, MFA/step-up, TTL hạn chế hoặc token exchange không?

Kết quả ví dụ:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "client_id": "employee-portal",
  "scope": "orders.read",
  "tenant_id": "company-a",
  "exp": 1893456000
}
~~~

AS không phát:

~~~json
{"aud":["orders-api","payments-api","admin-api"],"scope":"*"}
~~~

chỉ vì tất cả APIs cùng thuộc một tổ chức. Nếu business thật sự cần multi-audience/scope rộng, phải có threat model và policy explicit, không dùng nó làm mặc định.

### 14.2. Định nghĩa token profiles loại trừ lẫn nhau

Trong AS design nên có bảng:

| Token profile | Bên nhận | Required binding | Không được dùng ở |
| --- | --- | --- | --- |
| OIDC **ID token** | RP có `client_id` đã đăng ký | `iss`, `sub`, `aud=client_id`, time, `nonce` khi dùng | OAuth resource API |
| OAuth **JWT AT** | Một hoặc vài RS được AS cho phép | `iss`, `aud=resource`, `typ=at+jwt` theo RFC 9068, scope, expiry | RP thay ID token, AS client auth |
| OAuth **opaque AT** | RS xác minh qua trusted introspection | `active` + issuer/aud/purpose/scopes theo contract | Endpoint không có resource binding |
| OAuth **RT** | AS token endpoint | Client/grant/session/token-family binding, rotation/revocation | RS hoặc browser logout URL |
| **Client assertion JWT** | AS token endpoint | Client identity + token endpoint audience + lifetime/`jti` | Resource API |
| **Logout Token** | RP back-channel logout endpoint | OP issuer + RP audience + logout event + replay control | API business endpoint |

Profile separation có thể dùng **explicit JWT typing, distinct keys/keysets khi phù hợp, distinct endpoints, required claims và riêng validators**. Nếu cùng signing key được sử dụng cho nhiều token types, điều đó càng làm **purpose checks** quan trọng; không giải quyết bằng một `verifySignature()` chung.

### 14.3. Spring Authorization Server minh họa audience issuance

Trong Spring Authorization Server, một `OAuth2TokenCustomizer<JwtEncodingContext>` có thể đặt claims cho **JWT access token**. Ví dụ ý tưởng sau sử dụng domain policy do tổ chức triển khai để chọn audience:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> tokenAudienceCustomizer(
        ApprovedResourcePolicy policy) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType())) {
            return; // Do not rewrite ID tokens as access tokens.
        }

        String resourceAudience = policy.resolveApprovedAudience(
                context.getRegisteredClient(),
                context.getPrincipal(),
                context.getAuthorizedScopes(),
                context.getAuthorizationGrantType());

        context.getClaims().audience(
                List.of(resourceAudience));
        context.getJwsHeader().type("at+jwt");
    };
}
~~~

`ApprovedResourcePolicy` là **component nghiệp vụ minh họa phải được tự triển khai**, không phải API có sẵn của Spring. Nó **không được** lấy audience trực tiếp từ một field do caller nhập rồi trả lại không kiểm. Nó phải áp client registration, requested resource đã được AS verify, tenant/subject/actor và approved scope mapping. Code còn phụ thuộc **phiên bản Spring Authorization Server** và `JwtGenerator` đang sử dụng; cần kiểm framework type/header builders, token-specific customizers và tích hợp test.

**Không** dùng cùng customizer viết `typ=at+jwt` cho ID token: ID token có profile và recipient riêng. Một issuer phát sai `typ` hoặc `aud` có thể tạo token substitution vulnerability ngay từ nguồn.

### 14.4. Opaque AT cũng cần resource binding tại AS

Nếu AS phát opaque AT cho `orders-api`, metadata server-side vẫn phải chứa `client_id`, granted scope, subject, resource/audience, expiry, revocation state và token purpose. Introspection theo caller `orders-resource-server` phải trả **đủ chứng cứ** (metadata hoặc AS-authorized RS context) để RS không nhận token của `payments-api`.

Opaque token giấu claims khỏi bên cầm token, **không loại bỏ yêu cầu thiết kế audience**.

### 14.5. Token exchange phải hạn chế delegation escalation

Trong RFC 8693 Token Exchange, AS nhận `subject_token` và có thể `actor_token`/requested target resource theo profile. Không vì service A có token hợp lệ ở input mà AS tự cấp token `aud=admin-api`/`scope=admin.write`. AS phải:

~~~text
require subject token verified, correct issuer/type/audience semantics
require requesting client/service identity authorized for exchange
require actor/subject delegation contract (if applicable)
require target audience/resource is allowed for that client and subject
require output scope cannot exceed approved delegation policy
issue token with correct purpose, audience, actor/subject claims
record audit of who acted for whom, to which resource
~~~

Nếu không có user delegation/actor proof, dùng app-only token theo **policy riêng** và không báo đó là Alice đã consent. Một service account mạnh không phải “token substitution fallback” khi user token bị RS từ chối.

### 14.6. Tách key sets hay dùng `typ`?

**Distinct keys/keysets** có thể làm cross-profile substitution khó hơn, nhưng không phải mọi AS bắt buộc có key riêng theo token purpose. Dù chọn thiết kế nào, **recipient validator vẫn phải kiểm type/audience/issuer/scope**. Chỉ đổi keyset mà bỏ `aud` có thể gây cross-resource substitution giữa các APIs cùng keyset.

### 14.7. Token TTL và revocation không thay audience

Một AT `exp` trong 2 phút vẫn không thể dùng tại API sai. Một opaque AT `active=true` sau introspection cũng không thể dùng tại API sai. TTL/revocation kiểm **khi nào credential còn hợp lệ**, còn audience/type kiểm **nơi và mục đích credential được dùng**; cần cả hai.

## 15. Gateway, service mesh và cache: những nơi thường tự tráo token

### 15.1. Sai mẫu: gateway kiểm chữ ký rồi forward raw token không đổi

~~~text
Browser/client → API Gateway → hr-service
                         └──→ payroll-service

Gateway receives AT with aud=hr-api.
Gateway checks only iss/signature.
Gateway forwards AT to payroll-service.
Payroll trusts gateway and ignores aud/scope.
~~~

Rủi ro này vẫn tồn tại dù gateway và services giao tiếp qua TLS. TLS đảm bảo hop transport, **không** thay nội dung authority của AT.

### 15.2. Hai kiến trúc an toàn hơn

**Phương án A — mỗi RS xác minh AT cuối cùng:**

~~~text
Gateway verifies/filters request as needed.
Service-A verifies AT intended for Service-A.
Service-B verifies AT intended for Service-B.
AS issues audience-restricted ATs.
~~~

**Phương án B — gateway làm security enforcement point có chứng thực riêng:**

~~~text
Gateway verifies external AT audience, scope and route policy.
Gateway invokes downstream using authenticated service identity
or a new internal audience-bound delegated token.
Downstream verifies gateway identity/claims over protected trust link.
Downstream applies object/tenant ACL.
~~~

Phương án B chỉ an toàn khi có **threat model rõ**, gateway-to-service trust/headers bảo vệ, policy propagation, service isolation và không thể bypass gateway bằng đường trực tiếp. Header `X-User-Id` do browser tự gửi không được tin.

### 15.3. HTTP headers và certificate forwarding

Khi mTLS terminate tại gateway, downstream có thể nhận principal/cert fingerprint qua metadata/header. Nếu request có:

~~~http
X-Client-Cert: <attacker-selected-cert>
X-Authenticated-User: admin
X-Tenant: company-b
~~~

và downstream tin header do client đưa vào, attacker có thể thực hiện **identity/token-binding substitution**. Gateway phải **xóa/overwrite untrusted headers**, truyền identity qua channel authenticated/integrity-protected hoặc internal signed assertion theo contract; downstream chỉ tin header đến từ network/identity boundary đã được kiểm soát.

### 15.4. Token cache key sai có thể tráo người dùng

Sai:

~~~java
// Anti-pattern: all users share one token for orders-api.
Map<String, String> tokenCache = new HashMap<>();
tokenCache.put("orders-api", aliceAccessToken);
// Later Bob's session gets Alice's token.
~~~

Đúng về nguyên tắc: authorized-client/token store phải có **tenant, user/service subject, issuer, client registration, resource/audience, granted scopes và grant/session identity** làm một phần partition key khi cần. Không dùng global singleton “lastToken” cho toàn app hoặc một Redis key chỉ theo `scope`.

### 15.5. Retry/job queues và token swap

Một job queue có message:

~~~json
{
  "job_id": "job-1009",
  "tenant_id": "company-a",
  "user_ref": "alice",
  "target_api": "orders-api"
}
~~~

Worker không nên lấy **AT mới nhất của process** rồi gọi API. Nó cần xác định authorization context của job **đã được phê duyệt**, đúng actor/tenant/resource/scopes và token store isolation. Nếu job chạy sau khi user logout hoặc grant bị revoke, phải đánh giá policy/RT lifecycle; không mượn token của user khác để giữ job chạy.

### 15.6. Service mesh identity không thay OAuth token audience

SPIFFE/mTLS workload identity giúp chứng minh Pod/service đang gọi, nhưng không chứng minh Alice cho phép xem orders hay AT dành cho đúng resource. Mesh authorization có thể bổ sung trust layer; OAuth token purpose/audience và domain ACL vẫn cần nếu API hỗ trợ user-delegated operations.

### 15.7. Bảo vệ token khi được trao đổi hoặc proxy

- Chỉ gửi AT tới HTTPS host/resource đã được phê duyệt, không tự follow redirects mang theo Authorization tới host khác.
- Không ghi AT/ID token/RT vào request logs, HTTP traces, crash dumps, URLs hoặc analytics.
- Hạn chế caching raw token responses ở shared/CDN/proxy.
- Tách outbound HTTP clients theo resource/registration hoặc xác minh **selected AT audience** trước gửi.
- Khi token bị revoke hoặc account switch, invalidate cache đúng user/grant/tenant, không lấy token cũ cho phiên mới.

## 16. Sáu tình huống khai thác cụ thể và cách chẩn đoán

### Tình huống A: Nhầm ID token thành OAuth access token

**Bối cảnh:** Alice đăng nhập `employee-portal` bằng OIDC. RP có ID token `aud=employee-portal` và AT `aud=orders-api`. Một lập trình viên gọi:

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <OIDC-ID-token>
~~~

`orders-api` chỉ verify OP signature/expiry, rồi cho phép.

**Nguyên nhân:** Cross-token-type substitution: JWT authentication assertion bị dùng như API authorization credential.

**Sửa:** RS yêu cầu **OAuth AT profile**, expected audience và scope; RP outbound client phải dùng AT đúng resource. Thêm test “valid ID token but rejected at API” ngay cả khi ID token/AT cùng issuer và signing key.

### Tình huống B: AT từ HR được dùng tại payroll

**Bối cảnh:** Client có `hr.profile.read` và AT `aud=hr-api`. Nó gửi token đó tới `payroll-api`. Payroll verify chữ ký, nhìn claim `sub=alice` rồi tự suy Alice đã xác thực nên cho xem lương.

**Nguyên nhân:** Cross-resource token substitution/confused deputy; `sub` và signature không chứng minh recipient/authorization.

**Sửa:** Payroll kiểm `aud=payroll-api`, `scope=payroll.read` và payroll-specific role/tenant/object policy. AS phát token audience hẹp, client xin token mới qua approved grant/resource.

### Tình huống C: OIDC UserInfo trả Bob cho phiên Alice

**Bối cảnh:** RP dùng UserInfo cache theo một global access token pool. ID token cho Alice có `sub=alice` nhưng UserInfo response trả `sub=bob`. Vì email giống nhau, RP vẫn gộp profile vào session Alice.

**Nguyên nhân:** Subject substitution do session cache lỗi và bỏ OIDC UserInfo `sub` match.

**Sửa:** So UserInfo `sub` **bằng chính xác** ID token `sub`, từ chối response mismatched; cache theo issuer/subject/grant/session, không dùng email làm identity key. Kiểm privacy controls vì PII Bob đã có thể bị leak.

### Tình huống D: Opaque introspection trả active nhưng sai audience

**Bối cảnh:** `payments-api` gửi opaque token T1 đến AS. AS trả:

~~~json
{"active":true,"aud":["inventory-api"],"scope":"read"}
~~~

Payments kiểm `active` rồi cho phép `GET /payments`.

**Nguyên nhân:** RS thiếu audience/resource contract. Opaque token không tự tránh token substitution.

**Sửa:** RS kiểm `aud`/scope/type chính xác hoặc AS introspection phải ràng buộc RS caller với resource. Thêm negative test sai audience có cùng `active=true`.

### Tình huống E: Gateway chuyển user AT thành service-admin permission

**Bối cảnh:** Alice yêu cầu cập nhật một invoice nhưng user token của cô ấy không có `invoice.approve`. Gateway dùng `client_credentials` token `finance.admin` của mình để gọi downstream, dựa trên ý tưởng “gateway là first-party trusted”.

**Nguyên nhân:** Confused deputy và actor/principal substitution. Service authority bị dùng thay quyền delegated user.

**Sửa:** Không fallback app-only admin khi user thiếu quyền. Nếu cần delegation, dùng RFC 8693 Token Exchange hoặc policy-approved on-behalf-of model với actor/subject rõ, audience/service restriction và domain authorization.

### Tình huống F: Partner issuer được tin nhưng scopes bị gộp sai

**Bối cảnh:** API chấp nhận AS-Internal và AS-Partner. Token partner ký đúng `iss=partner` và `aud=orders-api`, nhưng partner chỉ được quyền `orders.read`. Một JWT `scope=orders.write` từ partner được API chấp nhận vì validator tin “scope trông hợp lệ”.

**Nguyên nhân:** Issuer trust bị hiểu thành quyền tự do cấp mọi scopes; policy không ràng buộc **issuer × client × scope/resource**.

**Sửa:** API áp issuer-specific scope/actor/tenant policy, AS integration contract và tests. Nếu partner không được phép cấp write scope, từ chối ngay cả khi claim đã ký đúng bởi key của partner.

## 17. Ma trận kiểm thử token substitution (75 ca)

Thiết lập test environment có:

- **Hai Authorization Servers/OpenID Providers**: AS-Internal và AS-Partner, keys/JWKS khác nhau; một case `kid` cố tình trùng.
- **Hai OAuth resource servers**: `orders-api` và `payments-api` cùng một AS trust context, thêm `hr-api` hoặc logical resource tương đương.
- **Hai OIDC clients/RPs**: `employee-portal` và `partner-portal`, hai browser authorization transactions `state`/`nonce` độc lập.
- JWT AT theo RFC 9068, OIDC ID token, opaque AT, RT, client assertion, logout token, DPoP proof và mTLS-bound token **chỉ cho test**.
- Người dùng Alice/Bob, tenants company-a/company-b, service principal, token exchange/gateway path.
- Test signer/key store, fake clock, programmable AS introspection, cache store và controllable network failure.

Đếm **token validation result** riêng với **domain authorization result**. Test sai audience cần một token **ký đúng và còn hạn**; nếu test bị 401 chỉ vì signer sai/JWKS unreachable, nó **không chứng minh audience check hoạt động**.

| ID | Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| S01 | JWT AT ký đúng, `iss=trusted`, `aud=orders-api`, `typ=at+jwt`, scope `orders.read` | Token layer **chấp nhận**, sau đó kiểm object ACL |
| S02 | Chính AT hợp lệ S01 được gửi đến `payments-api` | Payments **từ chối wrong audience** |
| S03 | AT `aud=payments-api`, scope `orders.read`, gửi orders | Orders từ chối; scope không thay audience |
| S04 | AT ký đúng nhưng thiếu `aud` khi profile yêu cầu | RS từ chối |
| S05 | AT `aud=["orders-api","payments-api"]` được AS chủ động cho phép | Mỗi RS kiểm chính mình trong array, không auto accept API thứ ba |
| S06 | AT `aud=["orders-api"]` đến `order-service-evil` có prefix tương tự | Từ chối; exact match, không substring/prefix |
| S07 | AT `aud=https://api.example.test/orders` đến `/payments` | Từ chối nếu expected recipient khác |
| S08 | API dùng `startsWith("api.example.test")` thay exact match | Test phải phát hiện acceptance sai audience |
| S09 | AT đúng issuer/audience nhưng `scope=orders.read`; gọi write | 403/insufficient_scope theo policy |
| S10 | AT `scope=myorders.read` tại route đòi `orders.read` | Không substring-match scope |
| S11 | AT đúng aud/scope nhưng user không sở hữu order | Object ACL từ chối |
| S12 | AT đúng aud/scope nhưng order thuộc tenant B, token tenant A | Tenant ACL từ chối |
| S13 | Caller tự gửi `X-Tenant: company-b` để override token tenant A | Không thay trusted tenant policy |
| S14 | AT user Alice được đặt nhầm vào cache phiên Bob | Test phát hiện cross-user token substitution |
| S15 | Hai clients khác nhau cùng subject Alice nhưng token khác audience/scopes | Không gộp quyền chỉ dựa `sub` |
| S16 | Client Credentials AT của service được gửi tới user-only route | Từ chối nếu domain yêu cầu delegated user identity |
| S17 | ID token OIDC đúng issuer/signature, `aud=employee-portal` gửi tới orders | RS từ chối wrong token type/purpose |
| S18 | ID token có `typ=JWT`, còn hạn, ký cùng AS JWT AT | RFC 9068 RS validator từ chối |
| S19 | Refresh token dạng opaque còn active gửi làm bearer tới API | RS từ chối wrong token purpose |
| S20 | Refresh token là JWT ký đúng được gửi tới RS | RS không nhận như OAuth AT |
| S21 | JWT client assertion có `aud=AS token endpoint` đến orders | RS từ chối dù signature đúng |
| S22 | OIDC Back-Channel Logout Token đến business API | RS từ chối token event/purpose |
| S23 | DPoP proof JWT được gửi như Bearer AT | RS không coi proof là access token |
| S24 | JWT `typ=at+jwt` do attacker khai nhưng signature sai | Reject cryptographic validation |
| S25 | JWT AT đúng signer, header `typ=JWT` khi profile bắt buộc RFC 9068 | Reject token type/profile |
| S26 | JWT AT đúng signer, `typ=application/at+jwt` theo profile cho phép | Chấp nhận type nếu các checks còn lại đúng |
| S27 | JWT `alg=none` | Reject signed AT profile |
| S28 | JWT thay `alg` sang thuật toán không allowlist | Reject, không algorithm confusion |
| S29 | JWT attacker ký với key không nằm trusted JWKS | Reject |
| S30 | JWT header `jku=https://attacker.example.test/jwks` | RS không tải key attacker |
| S31 | JWT `kid` giống trusted key ID nhưng key thuộc issuer khác | Không cross-issuer key reuse |
| S32 | JWT ký bởi AS-Partner nhưng `iss=AS-Internal` | Reject key/issuer mismatch |
| S33 | JWT ký hợp lệ AS-Partner và `aud=orders-api`, scope `orders.write` chưa được partner ủy quyền | Reject issuer-specific scope policy |
| S34 | JWT AS-Partner có scope `orders.read` và client/tenant được phép | Positive control thành công theo partner policy |
| S35 | Unknown `iss` trong JWT và untrusted discovery URL | Không tự discover rồi tin issuer; fail closed |
| S36 | Token `kid` mới, trusted JWKS tạm outage | Reject nếu không verify được khóa tin cậy |
| S37 | JWT `exp` trong quá khứ | Reject expiry dù issuer/aud đúng |
| S38 | JWT `nbf` trong tương lai | Reject before-not-valid |
| S39 | JWT `iat` quá bất thường theo AS profile policy | Reject nếu vi phạm configured lifetime/iat controls |
| S40 | OIDC RP login nhận ID token đúng `iss`, `aud=client-X`, nonce của transaction X | RP có thể tạo session sau tất cả validation |
| S41 | ID token của Bob/transaction B thay vào callback Alice/transaction A | Reject nonce/state/session binding |
| S42 | RP gửi nonce N-A, ID token trả nonce N-B | Reject |
| S43 | Multi-issuer callback của OP-B đi vào transaction expected OP-A | Reject issuer/mix-up |
| S44 | ID token có `aud` không chứa client ID của RP | Reject |
| S45 | ID token có multiple aud và `azp` sai theo OIDC rule | Reject theo OIDC profile |
| S46 | ID token ký đúng OP nhưng `exp` đã hết hạn | Reject login |
| S47 | UserInfo `sub=bob` trong session ID token `sub=alice` | RP từ chối UserInfo response |
| S48 | UserInfo `sub` khớp nhưng email claim bị thiếu | RP xử lý thiếu claim, không suy quyền |
| S49 | OP-B email giống OP-A, khác `(iss, sub)` | Không tự liên kết/chiếm local account |
| S50 | Pairwise `sub` thay đổi theo sector/client | Không gộp identity bằng suy đoán email/sub |
| S51 | Opaque AT active=true, `aud=orders-api` và scope đúng | Orders chấp nhận token layer, rồi ACL |
| S52 | Opaque AT active=true, `aud=payments-api` gửi orders | Orders reject wrong audience |
| S53 | Introspection active=true nhưng thiếu `aud` theo contract bắt buộc | RS từ chối thiếu bằng chứng recipient |
| S54 | AS có RS-specific introspection binding, aud không trả | RS chấp nhận **chỉ khi** contract/positive-negative tests chứng minh caller-to-resource restriction |
| S55 | Introspection HTTP 200 `active=false` | RS từ chối |
| S56 | Introspection trả `active` là string `"true"` hoặc malformed JSON | RS từ chối schema sai |
| S57 | RS introspection credentials sai, AS trả 401 | Fail closed, không auto active=true |
| S58 | AS introspection timeout/TLS certificate sai | Fail closed theo cache freshness policy |
| S59 | RT được introspect với `token_type_hint=access_token` | Không tự coi RT là AT |
| S60 | Shared cache reused introspection `active=true` từ HR sang payments | Test phát hiện trust-context cache poisoning |
| S61 | User/client grant bị revoke nhưng stale positive cache còn | Chặn khi TTL/freshness budget hết; đo SLA |
| S62 | Client request `resource=payments-api` nhưng registration chỉ cho orders | AS từ chối resource escalation |
| S63 | AS phát AT `aud=orders-api`, scope đúng từ approved resource request | Positive grant/token issuance |
| S64 | AS vô tình phát `aud=*`/all-APIs từ client request tùy ý | Test policy thất bại; chặn blanket audience |
| S65 | Service A forward raw AT `aud=service-a` tới service B | Service B từ chối, không trusted network bypass |
| S66 | Token Exchange cấp AT mới `aud=service-b` theo actor/subject policy | Service B nhận nếu scope/ACL/issuer đúng |
| S67 | Token Exchange xin `admin.write` vượt subject/client grant | AS từ chối privilege escalation |
| S68 | Gateway nhận spoofed `X-Authenticated-User: admin` từ browser | Gateway strip/overwrite, downstream không tin untrusted header |
| S69 | DPoP-bound AT + proof đúng `htm`/`htu`/key nhưng AT wrong audience | RS từ chối |
| S70 | DPoP AT có `cnf.jkt` không khớp proof key | RS từ chối sender binding |
| S71 | DPoP proof `jti` bị replay trong window | RS chặn proof replay theo policy |
| S72 | mTLS-bound AT đúng aud nhưng certificate fingerprint sai | RS từ chối sender binding |
| S73 | mTLS certificate đúng fingerprint nhưng AT `aud=other-api` | RS từ chối audience |
| S74 | PKCE S256 hợp lệ nhưng client gửi AT đã cấp tới wrong resource | Wrong resource RS từ chối; PKCE không thay aud |
| S75 | API logs/metrics chứa raw ID token/AT/RT/Authorization hoặc UserInfo PII | Security test phải phát hiện và khắc phục |

### 17.1. Cặp positive/negative để chứng minh expected audience

~~~text
Test setup:
  Trusted issuer = AS-A.
  Signing key = trusted K-A.
  Token purpose = JWT AT (typ=at+jwt).
  Clock = fixed, token not expired.
  Scope = orders.read.

Positive:
  aud=orders-api -> accepted at token validation layer.

Negative:
  Same claims and signer; change ONLY aud=payments-api.
  -> orders-api must reject.
~~~

Nếu cả hai case bị từ chối vì issuer misconfigured, test không chứng minh audience validator. Nếu cả hai case được chấp nhận, API bị **token substitution vulnerability**.

### 17.2. Cặp positive/negative để chứng minh token purpose

~~~text
Positive:
  JWT AT signed by trusted AS, typ=at+jwt,
  aud=orders-api, scope=orders.read.
  → token layer ACCEPT.

Negative:
  OIDC ID token signed by the SAME AS/key,
  aud=employee-portal, purpose=authentication.
  → orders-api REJECT.

Negative:
  JWT client assertion signed by an allowed client key,
  aud=AS token endpoint.
  → orders-api REJECT.
~~~

Chỉ kiểm signature theo cùng JWKS mà bỏ audience/type là lỗi. Các loại JWT có thể dùng trust/key stores khác nhau, nhưng test phải chứng minh **intended profile validation** thay vì chỉ lỗi parse.

### 17.3. Cặp positive/negative opaque introspection

~~~text
AT-O:
  active=true, aud=orders-api, scope=orders.read
  → accepted at orders token layer.

AT-P:
  active=true, aud=payments-api, scope=payments.read
  → rejected at orders token layer.

AT-R:
  active=false
  → rejected everywhere.
~~~

**Test AS with missing `aud`**: Nếu AS contract bảo đảm RS-specific `active`, test introspection token payments bằng **orders RS credentials** phải trả inactive/không đủ thông tin. Nếu AS trả active cho payments mà orders không có audience metadata, contract yếu và cần sửa.

### 17.4. Test OIDC session mix-up qua hai browser transactions

~~~text
Start T-A for Alice:
  state=S-A, nonce=N-A, issuer=AS-A, client=portal
Start T-B for Bob:
  state=S-B, nonce=N-B, issuer=AS-A, client=portal

Positive:
  Callback A + verified ID token A with nonce N-A
  → authenticate Alice.

Negative:
  Callback A + verified ID token B with nonce N-B
  → reject token/session mismatch.

Negative:
  Callback A + ID token from AS-B
  → reject wrong issuer.
~~~

Không dùng chỉ `sub` khớp làm bằng chứng ID token thuộc đúng login transaction. Test với state/PKCE/nonce đúng từng tầng để biết chính xác validator nào đã từ chối.

### 17.5. Test gateway và delegation

~~~text
Service A receives: AT aud=service-a, scope=read.
Service A tries:    forward original AT to service-b.
Expected:           Service B rejects wrong audience.

Service A exchanges token with trusted AS for service-b.
AS checks subject/actor/target/scope policy.
New AT aud=service-b, scope constrained.
Expected:           Service B accepts token layer,
                    then evaluates its own ACL.
~~~

Thêm test service A **không được mượn service-admin token** để bypass user denial và test headers identity do browser giả mạo không được tin. API gateway/mTLS/service mesh không tự tạo audience rộng hơn.

### 17.6. Test matrix cần kiểm cả fail-closed

Khi JWKS timeout, introspection outage hoặc policy store unavailable:

- Không tự chấp nhận unverified JWT/opaque token.
- Không đổi sang issuer khác ngẫu nhiên.
- Không tự bỏ `aud` hoặc `typ` để giảm tỷ lệ 401.
- Không dùng cached user B token để phục vụ user A.
- Không trả dữ liệu nhạy cảm; HTTP có thể 401 hoặc 503 tùy nguồn lỗi và API contract.

Không đánh đồng “không xác minh được vì hạ tầng lỗi” với “token đã được AS xác minh là sai”, nhưng **cả hai đều không cho phép hành động**.

## 18. Vận hành: phát hiện substitution và kiểm soát thay đổi trust boundary

Token substitution không phải lúc nào cũng xuất hiện như tấn công rõ ràng. Nó có thể là **bug token cache**, một deployment gateway đổi audience mapping, hoặc lỗi tích hợp AS mới. Vì vậy, cần telemetry **đủ phân biệt lý do từ chối** mà không ghi secret.

### 18.1. Những metrics nên có

| Metric minh họa | Ý nghĩa | Tín hiệu hành động |
| --- | --- | --- |
| `token_validation_invalid_audience_total` | AT tới API sai recipient | Cross-resource forwarding, client config drift hoặc attack |
| `token_validation_wrong_type_total` | ID token/RT/assertion bị dùng như AT | Cross-JWT confusion, client bug |
| `token_validation_wrong_issuer_total` | Token từ issuer lạ hoặc chưa được resource approve | AS mix-up, trust registry sai |
| `token_validation_signature_error_total` | Chữ ký/algorithm/key không đúng | Forgery, key rotation issue, parser config |
| `token_validation_expired_total` | AT hết hạn | Clock skew, stale token cache hoặc user behavior |
| `token_introspection_active_false_total` | Opaque token inactive | Revocation, expiry, token theft/replay |
| `token_introspection_wrong_resource_total` | Introspection active nhưng metadata sai resource | AS contract hoặc caller binding flaw |
| `oidc_nonce_mismatch_total` | ID token không thuộc login transaction | Session mix-up, token injection |
| `oidc_userinfo_sub_mismatch_total` | UserInfo subject không khớp verified ID token | Cache/session leakage, OP integration bug |
| `cross_tenant_access_denied_total` | User/token tìm cách truy cập khác tenant | Tenant isolation được thực thi; xem pattern |
| `service_token_in_user_route_denied_total` | App-only authority xuất hiện ở route đòi delegated user | Confused-deputy regression |
| `dpop_proof_binding_error_total` | Proof key/HTM/HTU/ATH không khớp AT | Stolen token/proof misuse |
| `mtls_token_binding_error_total` | Client cert fingerprint không khớp token `cnf` | Proxy header/cert substitution |
| `jwks_unknown_kid_total` | Key id chưa có trong trusted issuer set | Rotation mới hoặc token giả |
| `token_cache_subject_mismatch_total` | Outbound token không khớp principal session/job | Cache isolation/severe privacy incident |

Tên metrics trên là **tên ví dụ**, không phải endpoint/framework metric chuẩn. Tránh labels chứa raw AT/RT/ID token, email, `sub` cá nhân, scopes dài tùy ý hoặc `jti` cardinality cực cao. Có thể dùng **issuer registration ID, API route, reason code, policy version và opaque correlation ID**; bảo vệ data retention/audit access.

### 18.2. Phân biệt dấu hiệu tấn công với integration bug

| Dấu hiệu | Khả năng lỗi tích hợp | Khả năng tấn công |
| --- | --- | --- |
| Nhiều request wrong audience sau một deploy BFF | BFF chọn sai authorized client/token | Attacker thử token từ API khác |
| ID token xuất hiện ở API endpoints | Developer nhầm ID token với AT | Credential substitution cố ý |
| `kid` unknown tăng cùng lúc key rotation | JWKS cache chưa refresh | Attacker thử keys/`jku` lạ |
| UserInfo `sub` không khớp | Cache key thiếu subject hoặc response mix-up | Token/session hijacking |
| Partner issuer cấp scope write bất thường | AS mapping contract drift | Partner client cố nâng quyền |
| DPoP proof key mismatch liên tục | Client key lifecycle bug | Token/key theft hoặc replay |
| Cross-tenant denial tăng | Sai tenant routing sau deploy | Enumeration/exfiltration attempt |

**Không xác định động cơ từ một HTTP 401.** Dù là bug hay attacker, token validation phải **fail closed**; chỉ khác mức cảnh báo, hỗ trợ khách hàng và incident escalation.

### 18.3. Audit một quyết định từ chối an toàn

~~~json
{
  "event": "resource_token_validation",
  "decision": "DENY",
  "reason": "AUDIENCE_MISMATCH",
  "resource": "orders-api",
  "trusted_issuer_ref": "internal-as",
  "claimed_issuer_ref": "internal-as",
  "token_profile": "jwt-at",
  "expected_audience": "orders-api",
  "policy_version": "2026.11",
  "correlation_id": "<opaque-request-correlation>"
}
~~~

JSON này là **application audit mẫu**, không phải OAuth standardized response. Không log `Authorization`, decoded JWT payload đầy đủ, ID token, opaque token, RT, session cookie, DPoP private key hoặc UserInfo PII.

Với token chưa được verify, **đừng coi `iss`/`aud` claim là sự thật trong audit**; nếu cần ghi tín hiệu, phải đánh dấu rõ là *untrusted claimed value* hoặc dùng normalized/hashed labels an toàn. Không ghi attacker-controlled URL trực tiếp làm metric label.

### 18.4. Quy trình ứng phó khi phát hiện token substitution

1. **Chặn tiếp tục sử dụng** ở affected RS: sửa validation/route policy, fail closed, tắt insecure fallback.
2. Phân loại loại token đã bị nhận sai: AT sai audience, ID token như AT, opaque token active sai resource, token khác user/tenant hoặc issuer lạ.
3. Xác định khoảng thời gian, clients, issuers, audiences, token profiles, records/tenants bị ảnh hưởng thông qua **audit metadata đã bảo vệ**.
4. Đánh giá raw AT/RT/ID token đã lộ ở logs/cache/gateway; xóa/hạn chế tiếp cận theo incident policy.
5. Revoke grants/tokens, rotate keys/RS credentials **khi có bằng chứng/need**, không tự đổi toàn bộ key mà không phân tích blast radius.
6. Nếu access token còn hạn, áp denylist/status check/introspection hoặc TTL theo revocation SLA.
7. Kiểm tra downstream services, gateway, trusted headers, cache entries và permissions để tránh bypass đường phụ.
8. Viết positive/negative regression tests **cùng token, thay đúng một thuộc tính trust**.
9. Có canary deployment, theo dõi wrong-audience/wrong-type, authorization denies và latency.
10. Thực hiện thông báo/privacy/incident obligations khi dữ liệu nhạy cảm có khả năng bị truy cập sai.

### 18.5. Thay đổi issuer hoặc audience có rủi ro như thay ACL

Khi thêm một AS mới, chẳng hạn AS đối tác:

~~~text
BEFORE:
  orders-api trusts AS-A, scope orders.read.

AFTER (risky):
  orders-api trusts AS-A + AS-B,
  accepts any scope the two issuers put in JWT.
~~~

Việc thêm issuer **không chỉ là thêm một JWKS URL**. Phải duyệt **AS-B được tin cho audience nào, tenant/client nào, role/scope nào, session/principal models gì**, và có cơ chế revoke/incident response tương ứng.

Khi đổi audience `orders-api` sang `api.example.test/orders`, cần **phối hợp AS issuance, clients request, RS expected audience, gateway routing, opaque introspection contract và cache invalidation**. Không tạm thời tắt audience check để chuyển đổi mà thiếu migration policy/risk sign-off.

### 18.6. Load/availability không phải lý do bỏ token purpose checks

Khi JWKS endpoint outage hoặc introspection quá chậm, có thể giảm latency bằng cached trusted keys, bounded cache, single-flight, backoff và circuit breakers. **Không**:

~~~text
if (isInternalIP) acceptAnySignedJwt();
if (introspectionDown) acceptAllOpaqueTokens();
if (audMismatch) fallbackToDefaultScope("read");
if (oidcNonceMismatch) trustEmailAnyway();
~~~

Những fallback này biến sự cố hạ tầng thành **lỗ hổng substitution**. Trả lỗi service thích hợp khi không thể xác minh, và giữ policy bất biến cho sensitive operations.

## 19. Checklist production: token substitution defense-in-depth

### 19.1. Token trust và crypto

1. **Trusted issuers:** Có registry cố định/allowlisted cho từng RP/RS/tenant? Không dynamic trust từ token input?
2. **Signing keys:** JWKS lấy từ metadata/endpoint đã verify issuer/TLS? Không follow untrusted `jku`/`x5u`?
3. **Algorithms:** Có allowlist đúng key types, không `alg=none` hoặc algorithm confusion?
4. **Issuer-specific keys:** `kid` được resolve trong đúng issuer keyset, không global key cache theo `kid`?
5. **Expiry:** `exp`/`nbf`/`iat` được kiểm theo profile và bounded clock skew?
6. **Rotation:** JWKS refresh/unknown kid/compromised key có fail-closed/incident procedure?
7. **Token format:** JWT JWS, JWE, opaque và proprietary token được xử lý bằng profile chính xác?

### 19.2. Token purpose và recipient

8. **Type:** RS chỉ nhận OAuth AT, không ID token/RT/client assertion/logout token/DPoP proof?
9. **Explicit typing:** Với RFC 9068, `typ=at+jwt`/`application/at+jwt` được validate đúng version/framework?
10. **Audience:** Expected `aud` của RS được cấu hình độc lập với token và so chính xác?
11. **Resource indicators:** AS duyệt `resource` theo client/user/tenant policy, không cấp audience client tùy ý?
12. **Scope:** Granted scope trong token/introspection được parse thành set và so exact, không substring?
13. **Token purpose contract:** Các legacy JWT AT không `typ` có validator loại trừ ID/client assertion một cách chắc chắn?
14. **Opaque introspection:** `active=true` kết hợp aud/purpose metadata hoặc RS-specific caller binding đã kiểm chứng?
15. **Multi-audience:** Có đánh giá blast radius của AT dùng cho nhiều APIs và least-privilege alternatives?
16. **Issuer-by-scope:** Có giới hạn issuer/client được phép cấp từng scope/resource, không gộp role semantics bừa?

### 19.3. OAuth/OIDC client và subject

17. **Authorization transaction:** `state`/PKCE/expected issuer/registered redirect được RP kiểm?
18. **OIDC ID token:** RP kiểm signature/issuer/audience/expiry/nonce và `azp` khi áp dụng?
19. **UserInfo:** UserInfo `sub` phải bằng ID token `sub`, không bỏ qua vì email trùng?
20. **External identity:** Dùng verified `(iss, sub)`, không email làm immutable account key?
21. **Account linking:** Có proof/approval/tenant policy riêng khi ghép identities giữa OPs?
22. **Token storage:** AT/RT/ID token phân vùng theo client/user/session/tenant/resource/purpose?
23. **Outbound calls:** BFF lấy token **đúng resource** thay vì `lastToken` hoặc `idToken` global?
24. **Public clients:** SPA/native dùng Code+PKCE, không dựa static secret nhúng làm client authentication?

### 19.4. Downstream delegation và sender constraints

25. **Gateway audience:** Gateway/RS có explicit route-to-resource policy, không “one token for all”?
26. **Trusted headers:** Gateway xóa/overwrite user-controlled identity/cert/tenant headers?
27. **Downstream API:** Service nhận internal token/identity qua protected authenticated channel và vẫn kiểm ACL?
28. **Token exchange:** AS kiểm subject/actor/client/target/scopes trước khi phát AT downstream?
29. **App-only vs delegated:** Client Credentials service token không tự làm user-delegated admin?
30. **DPoP:** `cnf`/proof key, `ath`/`htm`/`htu`/`jti`/time/nonce được kiểm khi profile yêu cầu?
31. **mTLS:** `cnf.x5t#S256` được so với actual authenticated client cert; không tin spoofed header?
32. **Recipient after PoP:** Kể cả sender proof đúng, RS vẫn kiểm `aud`, scope và tenant/object ACL?

### 19.5. Availability, cache và monitoring

33. **RS credentials:** Introspection authentication/authorization, TLS và token/PII privacy đúng?
34. **Cache partition:** Token/JWKS/introspection/authorization caches phân biệt issuer, RS, user/actor, tenant và resource?
35. **Cache TTL:** Positive introspection cache không vượt `exp`/revocation budget; stale không vô hạn?
36. **Fail closed:** JWKS outage, introspection timeout, malformed tokens không làm hệ thống bỏ validator?
37. **Negative tests:** Có wrong aud, wrong typ, wrong issuer, wrong `kid`/`jku`, wrong nonce/azp/sub, cross-tenant cases?
38. **Positive controls:** Test dương cùng key/issuer/profile chứng minh decoder thật sự hoạt động?
39. **Audit:** Không log raw bearer/ID token/RT, client secret, DPoP private key, UserInfo PII?
40. **Change review:** Thay AS, audience, token profile, scopes, gateways, client registrations phải qua security regression?
41. **Incident:** Có kế hoạch revoke/rotate/cache invalidation và báo cáo khi token được chấp nhận sai resource?
42. **Data authorization:** Domain object/tenant/role checks tiếp tục hoạt động sau token validation, bất kể hình thức JWT/opaque?

## 20. Câu hỏi tự kiểm tra và tài liệu tham khảo

### 20.1. Hai mươi câu hỏi tự kiểm tra

**Câu 1. Token substitution khác bearer token replay ở điểm nào?**

Token substitution là dùng token **đúng về mặt kỹ thuật nhưng sai recipient/purpose/principal/context** ở nơi chờ token khác. Replay là dùng lại **cùng credential** đã được chấp nhận, thường sau khi bị sao chép. Hai hiện tượng có thể xảy ra đồng thời.

**Câu 2. Một JWT AT có chữ ký hợp lệ và chưa hết hạn có được mọi API cùng issuer chấp nhận không?**

Không. API phải xác minh **expected audience của chính mình**, token purpose/profile, granted scope và domain ACL. Chữ ký không chứng minh quyền ở resource khác.

**Câu 3. Nếu token có `scope=orders.read` nhưng `aud=payments-api`, orders có thể cho phép không?**

Không. Scope không thay audience. Orders phải từ chối token dành cho payments, kể cả token signature và expiry đúng.

**Câu 4. Vì sao ID token OIDC không được dùng làm bearer AT tại Resource Server?**

ID token là authentication assertion gửi cho **RP/client** (`aud=client_id`), không phải quyền OAuth API. RS cần access token đúng purpose, recipient, scope và ACL.

**Câu 5. `typ=at+jwt` có phải là bằng chứng đủ để nhận token không?**

Không. `typ` giúp phân biệt token profile theo RFC 9068/RFC 8725 nhưng vẫn phải verify JWS bằng trusted issuer/key và kiểm `iss`, `aud`, `exp`, scopes, subject/client/tenant policy.

**Câu 6. Nếu hệ thống dùng JWT AT legacy không có `typ=at+jwt` thì có thể bỏ mọi type check không?**

Không. Cần **profile validation riêng** loại trừ ID token/client assertion/logout token, có audience/issuer/required claims rõ và test chống cross-JWT confusion.

**Câu 7. Opaque AT được introspect có `active=true` thì đã đủ cho phép API chưa?**

Chưa. Cần bằng chứng token dành cho đúng RS (metadata `aud` hoặc contract RS-specific introspection), scope và domain ACL. `active` chỉ nói trạng thái token theo AS/caller context.

**Câu 8. RFC 7662 có bắt buộc introspection response active chứa `aud` không?**

Không. `active` bắt buộc, còn `aud` và các metadata khác tùy chọn. Nếu API cần resource binding, AS/RS phải thỏa thuận và kiểm chứng metadata hoặc caller-specific behavior.

**Câu 9. Có thể gửi RT tới resource API vì RT cũng là một JWT ký đúng không?**

Không. Refresh token dành cho **AS token endpoint**, không phải API authorization. Token format không đổi purpose.

**Câu 10. `kid` có xác định được issuer/JWKS đáng tin không?**

Không. `kid` là key selector trong **trusted issuer keyset**. Không dùng key ID hoặc untrusted `jku` để mở rộng trust sang attacker-controlled JWKS.

**Câu 11. Tại sao cùng email nhưng khác `(iss, sub)` không phải chắc chắn cùng user?**

Email có thể thay đổi/tái sử dụng, OP policies khác nhau và `email_verified` không cấp quyền account linking. Dùng identity key đã verify và quy trình linking độc lập.

**Câu 12. UserInfo response có `sub=bob` nhưng ID token của session có `sub=alice`. Có thể dùng email trùng để cho qua?**

Không. OIDC yêu cầu RP **không sử dụng** UserInfo response khi `sub` không khớp chính xác ID token `sub`.

**Câu 13. PKCE S256 có chống được AT của HR bị gửi tới payroll không?**

Không. PKCE bảo vệ **authorization code exchange** tại AS; audience/resource validation ở RS mới chống cross-resource AT substitution.

**Câu 14. DPoP hoặc mTLS-bound token có cho phép bỏ `aud` không?**

Không. Sender constraint chứng minh holder key/certificate, nhưng **không** chứng minh token được phát cho resource này hoặc user có quyền object.

**Câu 15. Vì sao client credentials token của service không được dùng thay quyền Alice?**

Client Credentials tạo **app-only authority**; nó không tự đại diện Alice hoặc một user consent. Dùng service-admin token để qua user authorization là confused deputy/privilege escalation.

**Câu 16. Khi service A cần gọi service B thay user, có nên forward nguyên AT của A không?**

Không nếu `aud` không chứa B theo contract. Nên thiết kế delegated token riêng qua AS Token Exchange/OBO phù hợp, với actor/subject/target/scope policy, rồi để B kiểm audience/ACL.

**Câu 17. Multi-issuer Resource Server chỉ cần check mỗi `iss` nằm trong danh sách tin cậy có đủ không?**

Không. Mỗi issuer phải có **policy cho audiences, scopes, clients/actors/tenants**. Một partner issuer không tự có quyền phát `orders.write` chỉ vì API chấp nhận chữ ký của nó.

**Câu 18. Cache AT theo `"orders-api"` có nguy cơ gì?**

Có thể trả token Alice cho Bob hoặc token tenant A cho tenant B. Cache phải ràng buộc user/service subject, issuer, registration, session/grant, tenant, resource/audience và scopes tùy contract.

**Câu 19. Khi JWKS endpoint lỗi, có thể bỏ signature/audience validation để giữ availability không?**

Không. Dùng trusted cached keys theo policy khi còn phù hợp; nếu không thể verify, fail closed. Network outage không là bằng chứng token hợp lệ.

**Câu 20. Một test “token sai audience bị 401” có đủ chứng minh API an toàn không?**

Chưa. Phải có **positive control** với token đúng issuer/chữ ký/type/time/scope và audience đúng; negative test chỉ thay `aud`. Nếu cả hai đều 401 do JWKS lỗi, audience validator chưa được kiểm thật.

### 20.2. Tài liệu chuẩn và hướng dẫn triển khai

- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): **Cross-JWT confusion**, explicit typing, issuer/audience validation, algorithm/key trust.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `typ=at+jwt`/`application/at+jwt`, token profile, `iss`, `aud`, `client_id`, scopes và RS validation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth AT audience restriction, token replay/substitution risks, PKCE, RT protection.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Client/AS/RS roles, grants, access vs refresh tokens và scope semantics.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token transport, `401 invalid_token`, `403 insufficient_scope` và replay considerations.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu AT cho resource, giảm cross-resource token substitution.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange theo target resource, subject/actor và authorized delegation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, optional `aud`/`iss`/scope metadata, RS caller authorization.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): registered JWT claims `iss`, `sub`, `aud`, `exp`, `iat` và `nbf`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS protected header, algorithms và signature verification.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): trusted JWK/JWKS, `kid` và key types.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): token encryption khác signature validation, không thay mục đích token.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): authorization code interception protection, khác audience restriction.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer identification trong authorization response, chống AS mix-up.
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705): mTLS certificate-bound AT và `cnf.x5t#S256`.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained AT, proof binding và replay controls.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, `nonce`/`azp`, `iss`/`aud` validation, UserInfo `sub` match, login transaction.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): trusted issuer/OP metadata và JWKS discovery.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token profile — không được dùng làm API AT.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, issuer/JWKS, validators và scope authorization.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector`, active/claims validation.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC login, ID-token validation và authorized client context.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): registered clients, `OAuth2Authorization`, token generators và customization.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization/token/introspection endpoints, grants, policy extension points.

**Điểm cần ghi nhớ:** **Token substitution là việc dùng một token ở sai nơi nhận, sai loại credential, sai issuer, sai user/client/tenant hoặc sai ngữ cảnh ủy quyền** dù token có thể vẫn hợp lệ về chữ ký và thời gian. **JWT signature valid** hay **opaque introspection `active=true` không tự đủ** để xác thực quyền API. Với Resource Server, phải xác minh **token purpose, expected `iss`, `aud`, `exp`, granted scopes, sender constraint khi có và object/tenant authorization**. Với OIDC Relying Party, phải ràng buộc **`state`/PKCE/`nonce`/issuer/`aud`/`azp`** vào login transaction và từ chối UserInfo `sub` không khớp ID token. AS phải cấp token audience hẹp theo approved client/user/resource policy; gateway/downstream phải không tráo token hay header identity; token exchange chỉ được làm theo authorized actor/subject/resource policy. **Test tốt nhất** luôn có token hợp lệ làm đối chứng rồi chỉ thay một thuộc tính audience/type/issuer/subject để chứng minh đúng ranh giới tin cậy.
