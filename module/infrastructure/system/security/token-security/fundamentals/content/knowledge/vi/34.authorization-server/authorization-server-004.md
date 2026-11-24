# Authorization endpoint

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **authorization endpoint** của OAuth 2.0/OIDC nằm ở đâu, ai truy cập nó và vì sao đây là điểm điều phối xác thực người dùng, xin cấp quyền và tạo **authorization code**, chứ không phải nơi Resource Server kiểm access token.
- Phân biệt **authorization endpoint**, **token endpoint**, **resource endpoint**, **revocation endpoint**, **introspection endpoint**, **JWKS** và **OIDC UserInfo endpoint**.
- Phân tích luồng **Authorization Code + PKCE** từ lúc client xây authorization request đến lúc AS kiểm người dùng/consent và redirect về client với code.
- Thiết kế kiểm tra **client_id, response_type, redirect_uri, scope, state, code_challenge, code_challenge_method, resource** và các tham số OIDC như **nonce, prompt, max_age** theo policy.
- Hiểu cơ chế bảo vệ chống **redirect URI manipulation, open redirect, authorization code interception/injection, CSRF, login CSRF, OAuth mix-up, consent phishing, scope escalation và token leakage**.
- Giải thích vì sao **authorization code** có thời hạn ngắn, one-time, ràng với client, redirect URI, PKCE challenge và authorization context; không dùng code như access token.
- So sánh **front-channel browser redirect** với **back-channel token exchange**, và nhận diện nơi dữ liệu có thể bị rò qua URL, referrer, logs, browser history hoặc third-party scripts.
- Hiểu vị trí của **OpenID Connect**, **state** và **nonce**, cũng như các biện pháp nâng cao như **Pushed Authorization Requests (PAR)** và **JWT-Secured Authorization Request (JAR)** khi profile yêu cầu.
- Thiết kế pseudocode, ví dụ Java/Spring và các phép kiểm thử âm cho authorization endpoint của một hệ thống token security.
- Xây dựng checklist production, telemetry và playbook xử lý sự cố cho Authorization Server.

## 1. Authorization endpoint là gì?

Trong OAuth 2.0, **authorization endpoint** là điểm đầu cuối của **Authorization Server (AS)** dùng để tiếp nhận yêu cầu ủy quyền từ OAuth client **thông qua user-agent của resource owner**, điển hình là trình duyệt.

Một client muốn truy cập Orders API thay mặt người dùng sẽ đưa browser đến authorization endpoint của AS. AS xác định client nào đang yêu cầu, phạm vi quyền nào được xin, tài nguyên nào sẽ nhận access token, người dùng đã xác thực chưa và chính sách có cho phép cấp quyền hay không.

Khi các điều kiện đạt và **response_type=code**, AS gửi browser trở lại redirect URI đã được đăng ký kèm **authorization code ngắn hạn**. Client sau đó đổi code ở **token endpoint**, thường kèm **PKCE code_verifier**, client authentication khi thích hợp, để nhận access token và có thể cả refresh token hoặc OIDC ID token.

**Authorization endpoint không nên được hiểu là nơi trả access token Bearer trực tiếp cho frontend trong luồng Authorization Code hiện đại.**

### Ví dụ các endpoint trong một hệ thống

~~~text
Authorization Server:
    https://identity.example.test/oauth2/authorize
    https://identity.example.test/oauth2/token
    https://identity.example.test/oauth2/revoke
    https://identity.example.test/oauth2/introspect
    https://identity.example.test/.well-known/jwks.json

Resource Server:
    https://orders.example.test/api/orders

OAuth Client:
    https://dashboard.example.test/oauth/callback
~~~

Các URL trên chỉ là **ví dụ**, không là những đường dẫn bắt buộc của mọi sản phẩm. AS công bố metadata/discovery theo chuẩn/profile phù hợp; client không nên ghép một URL tùy ý từ tên sản phẩm rồi giả định đó là authorization endpoint tin cậy.

### Một câu phân biệt

> **Authorization endpoint quyết định và ghi nhận việc cấp phép; token endpoint xử lý đổi bằng chứng/grant lấy token; Resource Server xác minh và thực thi quyền của token trên tài nguyên.**

## 2. Các vai trò OAuth và trust boundaries

OAuth 2.0 phân biệt bốn vai trò quan trọng:

| Vai trò | Trách nhiệm | Trust boundary quan trọng |
| --- | --- | --- |
| **Resource Owner** | Chủ thể có khả năng cấp quyền cho client trong phạm vi được phép. Thường là end-user. | Không được cấp quyền vượt entitlements/policy của chính mình. |
| **OAuth Client** | Ứng dụng xin quyền, khởi tạo authorization request và nhận callback/code. | Tham số do client gửi là **yêu cầu**, không phải quyền đã được cấp. |
| **Authorization Server (AS)** | Xác thực người dùng, kiểm client, authorization, consent/grant; phát authorization code và token ở các endpoint thích hợp. | Phải giữ trạng thái cấp quyền tin cậy và không phát code/token dựa trên input tùy ý. |
| **Resource Server (RS)** | Nhận access token dành cho mình và áp issuer, audience, scope, permission, tenant/resource checks. | Không biến access token hợp lệ thành quyền mọi API/đối tượng. |

Trong OIDC, **OpenID Provider (OP)** thường đóng vai trò AS, còn **Relying Party (RP)** đóng vai trò client để xác minh authentication và nhận thông tin định danh từ ID token/UserInfo.

~~~mermaid
flowchart LR
    U["Resource Owner / Browser"] -->|"Đăng nhập, chấp thuận"| AS["Authorization Server\nAuthorization Endpoint"]
    C["OAuth Client / RP"] -->|"Tạo authorization request"| U
    AS -->|"Redirect code + state"| U
    U -->|"Callback code"| C
    C -->|"POST code + verifier"| T["AS Token Endpoint"]
    T -->|"Access token / ID token / RT khi phù hợp"| C
    C -->|"AT"| R["Resource Server"]
~~~

**Front channel** đi qua browser, nơi URL và giao diện có thể bị quan sát hoặc thao túng. **Back channel** là giao tiếp trực tiếp client↔token endpoint có thể bổ sung client authentication, TLS và bằng chứng PKCE. Hai biên bảo mật này không thể thay nhau.

### Các bên không được tin tự động

- Browser có thể mang URL bị sửa, extension độc hại hoặc session cũ.
- Client có thể yêu cầu scope/resource ngoài registration.
- Redirect URI trong request là **input**, không phải nơi AS tự ý gửi code.
- Người dùng đã đăng nhập không đồng nghĩa mọi client request được phép.
- Một callback chứa code không tự chứng minh response đến từ AS mà client dự định dùng.
- Resource Server phải kiểm token do **issuer đúng** phát cho **audience đúng**, không dựa vào việc user trước đó đã xem consent screen.

## 3. Phân biệt các endpoint liên quan

| Endpoint | Chủ thể gọi điển hình | Đầu vào chính | Kết quả/đặc điểm |
| --- | --- | --- | --- |
| **Authorization endpoint** | Browser/user-agent do client điều hướng. | response_type, client_id, redirect_uri, scope, state, PKCE, OIDC params. | Redirect với code hoặc lỗi theo hợp đồng; có tương tác login/consent. |
| **Token endpoint** | OAuth client, thường qua back channel. | grant_type=authorization_code, code, redirect_uri, code_verifier, client auth khi cần. | Trả AT và có thể ID token/RT theo flow/profile. |
| **Resource endpoint** | Client cầm AT. | Authorization Bearer/DPoP token, resource request. | Dữ liệu/hành động được phép theo RS policy. |
| **Revocation endpoint** | Client được phép, tùy profile. | Token cần revoke, client context. | Xử lý rút token/grant theo RFC 7009. |
| **Introspection endpoint** | RS/authorized caller. | Token + caller authentication. | Trả active, scope, aud... theo RFC 7662. |
| **JWKS endpoint** | Verifier và client cần trusted public keys. | Fetch JWKS từ trusted issuer metadata. | Public verification keys; không chứa private signing key. |
| **UserInfo endpoint** | OIDC RP/client với access token phù hợp. | Access token cho UserInfo. | Claims người dùng theo OIDC, không tự là authorization code. |

### Tránh hai nhầm lẫn

**Nhầm 1:** Client gửi refresh token lên authorization endpoint để lấy AT mới. Sai: refresh token grant thuộc **token endpoint**, không phải browser authorization endpoint.

**Nhầm 2:** Orders API gửi Bearer token lên authorization endpoint để hỏi active không. Sai: RS phải verify JWT đúng profile hoặc dùng **introspection** nếu kiến trúc hỗ trợ; authorization endpoint không là token-validation oracle.

## 4. Authorization Code Flow với PKCE từ đầu đến cuối

Ví dụ hệ thống:

- **AS/OP:** identity.example.test.
- **Client:** dashboard-web.
- **RS:** Orders API.
- **Redirect URI đã đăng ký:** https://dashboard.example.test/oauth/callback.
- **Quyền cần:** orders:read.
- **Mục tiêu:** user đăng nhập và cho phép dashboard đọc orders thuộc quyền của mình.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as Dashboard Client
    participant AS as AS Authorization Endpoint
    participant ST as AS Code/Grant Store
    participant T as AS Token Endpoint
    participant RS as Orders API

    B->>C: Mở dashboard
    C->>C: Tạo state + PKCE verifier/challenge, lưu transaction
    C-->>B: 302 đến AS /authorize
    B->>AS: GET /authorize?response_type=code...
    AS->>AS: Validate client, redirect URI, scope, resource, PKCE
    AS->>B: Hiển thị login nếu cần
    B->>AS: Xác thực theo chính sách AS
    AS->>B: Hiển thị consent nếu cần
    B->>AS: Approve / deny
    AS->>ST: Persist code one-time, client, redirect, challenge, grant
    ST-->>AS: Authorization code
    AS-->>B: 302 Location: registered callback?code=...&state=...
    B->>C: GET callback với code + state
    C->>C: Kiểm state + expected issuer/transaction
    C->>T: POST grant_type=authorization_code + code + verifier
    T->>ST: Atomic redeem code, kiểm client/redirect/PKCE
    ST-->>T: Granted scopes và principal context
    T-->>C: Access token; ID token/RT khi profile cho phép
    C->>RS: GET /api/orders với AT
    RS-->>C: Chỉ dữ liệu được phép
~~~

**Mũi tên code trong browser redirect không phải bằng chứng người dùng đã được trao access token trong browser.** Code là artifact ngắn hạn để **client đổi token đúng ràng buộc** tại token endpoint.

### Bốn bảo vệ độc lập

1. **Redirect URI binding:** code không được gửi đến điểm nhận do attacker tự khai.
2. **State / issuer binding:** client phân biệt callback thuộc request/AS nào, chống CSRF/code injection/mix-up.
3. **PKCE:** kẻ chặn code đơn lẻ không đổi được code nếu thiếu verifier.
4. **One-time code redemption:** code không được đổi token nhiều lần dù verifier/credential được trình lại.

Nếu chỉ có một hoặc hai biện pháp, những lỗ hổng còn lại vẫn có thể tồn tại.

## 5. Cấu trúc authorization request

Một request OAuth 2.0 Authorization Code với PKCE có thể có dạng:

~~~http
GET /oauth2/authorize?response_type=code&client_id=dashboard-web&redirect_uri=https%3A%2F%2Fdashboard.example.test%2Foauth%2Fcallback&scope=orders%3Aread&state=EXAMPLE_RANDOM_STATE&code_challenge=EXAMPLE_S256_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
Accept: text/html
~~~

Các giá trị **EXAMPLE_...** chỉ để minh họa; trong triển khai thật cần giá trị ngẫu nhiên, đúng format, đủ entropy, và challenge được sinh từ verifier theo RFC 7636.

| Tham số | Mục đích | Kiểm tra ở AS/client |
| --- | --- | --- |
| **response_type=code** | Yêu cầu Authorization Code Flow. | AS chỉ hỗ trợ response types đã được phép cho client; không tự chuyển implicit flow. |
| **client_id** | Nhận diện OAuth client. | Phải tồn tại, active, đúng registration/grant/redirect policy. |
| **redirect_uri** | Callback để gửi authorization response. | Phải khớp URI đã đăng ký theo chuẩn/profile; chống open redirect và wildcard. |
| **scope** | Xin phạm vi cấp quyền. | AS kiểm client registration, user/grant/consent và resource policy. |
| **state** | Client correlate response với authorization transaction. | Client sinh khó đoán, bảo vệ trong session, đối chiếu callback. |
| **code_challenge** | PKCE challenge gắn với verifier bí mật do client giữ. | AS kiểm cú pháp/method và lưu binding với code. |
| **code_challenge_method=S256** | Biểu thị challenge dùng SHA-256 + Base64URL. | Nên yêu cầu S256 theo hiện đại và policy. |
| **resource** | Intended resource indicator khi hỗ trợ RFC 8707. | AS kiểm allowed resource, scope và output audience. |
| **nonce** | OIDC correlation/replay control theo profile. | RP lưu theo transaction, kiểm ID token nếu yêu cầu/gửi nonce. |
| **prompt/max_age/acr_values** | OIDC request về login/session/auth context khi hỗ trợ. | AS kiểm semantics/profile, không để client tự khai là đã MFA. |

Các tham số nhạy cảm hoặc ràng buộc an ninh **không được bỏ qua tùy tiện**. Mọi ứng dụng nên sử dụng URI của AS từ **trusted discovery/configuration**, không lấy authorization_endpoint từ query do attacker gửi.

### GET và request size

RFC 6749 yêu cầu authorization endpoint hỗ trợ HTTP **GET**; cũng cho phép hỗ trợ **POST**. Không suy rằng endpoint bắt buộc chấp nhận mọi request method, body format hoặc mọi extension parameter. Với request có nhiều thông tin, có thể dùng **PAR/JAR** theo profile thay vì tạo URL quá dài chứa dữ liệu nhạy cảm.

## 6. Authorization response: code, state và lỗi

Khi AS chấp thuận authorization code request, browser được redirect về callback đã được xác minh:

~~~http
HTTP/1.1 302 Found
Location: https://dashboard.example.test/oauth/callback?code=EXAMPLE_AUTHORIZATION_CODE&state=EXAMPLE_RANDOM_STATE
Cache-Control: no-store
~~~

**Code không phải access token**. Dashboard phải kiểm transaction state và sau đó gửi code đến **token endpoint** cùng PKCE verifier.

### Khi người dùng từ chối consent

Nếu client_id và redirect_uri đã được xác minh, AS có thể redirect:

~~~http
HTTP/1.1 302 Found
Location: https://dashboard.example.test/oauth/callback?error=access_denied&state=EXAMPLE_RANDOM_STATE
Cache-Control: no-store
~~~

Từ chối consent là **một kết quả authorization bình thường**; không được tự chuyển thành granted scope hoặc tạo code.

### Khi redirect URI hoặc client không hợp lệ

Nếu redirect URI không khớp registration hoặc client_id không hợp lệ, **AS không được redirect user-agent đến URI đó**. Thay vào đó, AS hiển thị trang lỗi an toàn tại chính AS hoặc cách xử lý đã được thiết kế, tránh gửi code/error data tới attacker destination.

Đây là điểm đặc biệt quan trọng: **không được dùng redirect_uri chưa xác minh làm đích báo lỗi**.

### State trong success và error

Khi client gửi state và AS trả authorization response cho một redirect URI hợp lệ, state phải được phản hồi nguyên giá trị theo OAuth. Client phải so sánh với transaction đã lưu và từ chối mismatch, missing hoặc replayed state theo policy.

**State do browser redirect mang về không tự là quyền đăng nhập**; nó là transaction correlation/CSRF defense và cần được bảo vệ khỏi lộ, fixation, ghi đè hoặc tái sử dụng.

## 7. Authorization endpoint không phải nơi phát hành token Bearer qua URL

Đối với thiết kế mới, **Authorization Code + PKCE** là lựa chọn phù hợp hơn các flows đưa access token trực tiếp qua browser front channel. OAuth 2.0 Security Best Current Practice (RFC 9700) yêu cầu không sử dụng **implicit grant** và những mô hình rò token qua authorization response trong triển khai mới theo guidance của tài liệu.

### Tại sao tránh token trong URL fragment/front channel?

Một access token trong front channel có thể tiếp xúc với:

- Browser scripts và extensions.
- Fragment/query handling của SPA hoặc redirect.
- Browser history, navigation state và debugging tools.
- Referrer/leakage trong những cách xử lý sai hoặc endpoint trung gian.
- Third-party scripts theo origin/context.
- Open redirect và redirect URI bugs.

Authorization code cũng là một credential và có thể bị lộ qua URL/log, nhưng **PKCE + client binding + one-time semantics** giúp code đơn lẻ khó đổi thành token hơn.

### Không nghĩ PKCE làm code công khai vô hại

Code vẫn phải:

- Ngắn hạn, ngẫu nhiên, không dự đoán.
- Ràng với client_id và redirect_uri/authorization context.
- Chỉ đổi được một lần.
- Được client và AS xử lý như **sensitive credential**.
- Không bị in log/traces hoặc gửi tới bên thứ ba.

Một attacker có cả **code và verifier**, hoặc đã chiếm client callback/runtime, có thể vượt cơ chế chỉ bảo vệ against code-only interception. PKCE không phải sự thay thế cho client security.

## 8. PKCE: ràng authorization request với token exchange

**Proof Key for Code Exchange** (RFC 7636) liên kết request ban đầu với bên đổi authorization code.

Client tạo **code_verifier** ngẫu nhiên, đủ entropy. Với method **S256**:

~~~text
code_challenge =
    BASE64URL-ENCODE(
        SHA256(ASCII(code_verifier))
    )
~~~

### Điều gì được gửi qua browser?

- Authorization endpoint nhận **code_challenge** và **code_challenge_method=S256**.
- Client giữ **code_verifier** trong authorization transaction storage, không đưa verifier vào authorization URL.
- Token endpoint nhận **code_verifier** khi client đổi code.
- AS tính lại challenge và kiểm với giá trị đã gắn vào code.

### Vì sao cần S256?

S256 ngăn việc đọc authorization request URL tiết lộ verifier; gửi trực tiếp verifier hoặc dùng phương thức **plain** trong môi trường mà challenge bị nhìn thấy làm suy yếu lợi ích chống interception. Hệ thống mới nên yêu cầu **S256** theo chính sách và guidance cập nhật.

### PKCE phải ràng với code được phát

Sai:

~~~text
AS lưu code_challenge trong một session global theo client_id.
Hai login tabs ghi đè challenge của nhau.
Token endpoint kiểm verifier với "challenge mới nhất".
~~~

Đúng:

~~~text
authorizationTransaction T1:
    code C1 -> client A, redirect URI R1,
               S256 challenge H(verifier1), granted scopes...

authorizationTransaction T2:
    code C2 -> client A, redirect URI R1,
               S256 challenge H(verifier2), granted scopes...

Redeem C1: chỉ verifier1 hợp lệ.
Redeem C2: chỉ verifier2 hợp lệ.
~~~

**PKCE không tự kiểm state, issuer, consent hoặc scope**. Mỗi ranh giới cần một kiểm tra riêng.

## 9. Redirect URI: ranh giới bảo vệ authorization code

**Redirect URI** là đích nhận authorization response trong browser. Nếu AS cho client gửi redirect_uri tùy ý, attacker có thể lấy code bằng cách khiến AS chuyển hướng đến domain do attacker kiểm soát.

### Ví dụ attack

Client hợp lệ đăng ký:

~~~text
https://dashboard.example.test/oauth/callback
~~~

Attacker sửa authorization request thành:

~~~text
redirect_uri=https://attacker.example.test/receive-code
~~~

Nếu AS chỉ kiểm client_id mà không kiểm redirect URI, một authorization code có thể bị gửi tới attacker. **Tuy PKCE có thể ngăn attacker chỉ biết code đổi token, redirect URI validation vẫn là ranh giới bắt buộc**; đừng phụ thuộc một lớp bảo vệ duy nhất.

### Kiểm tra redirect URI an toàn

- Với web clients, dùng **absolute HTTPS redirect URI đã đăng ký đầy đủ**, so khớp theo quy tắc RFC/profile; tránh các wildcard không cần thiết.
- Không dùng **substring**, prefix hoặc host suffix matching để “nới” redirect rules.
- Không chấp nhận userinfo/host confusion như một URI nhìn giống trusted host.
- Không tự hạ HTTPS sang HTTP trừ trường hợp profile cho phép (ví dụ một số native loopback redirect URIs theo RFC 8252).
- Với native app, **loopback redirect port** có quy tắc ngoại lệ và phải áp theo profile, không áp đặt máy móc web exact string match cho mọi platform.
- Không chấp nhận open redirect của client như một callback an toàn chỉ vì URL ban đầu nằm trên domain hợp lệ.
- Không cho third-party untrusted host quyết định redirect URI thông qua forward headers tùy ý.
- Khi nhận callback lỗi, AS chỉ redirect về URI **đã được xác minh**, không gửi lỗi/token/code tới URI sai.

### Sai lầm: startsWith

~~~java
// SAI: một attacker host có thể bắt đầu bằng trusted prefix.
if (requestedRedirect.startsWith(
        "https://dashboard.example.test")) {
    return true;
}
~~~

Một URL như:

~~~text
https://dashboard.example.test.attacker.example.org/collect
~~~

không thuộc trusted host dù có prefix giống.

### Sai lầm: open redirect tại callback host

Một redirect URI như:

~~~text
https://dashboard.example.test/redirect?next=https://attacker.example.test/
~~~

có thể làm authorization response bị chuyển tiếp ra ngoài nếu endpoint /redirect là **open redirector**. Ngay cả khi domain callback đúng, client cần bảo đảm endpoint không forward code/state sang host khác. AS nên hạn chế registered redirect URIs và review callback behavior.

### Path/query matching và URI normalization

Không tự “canonicalize” bằng cách decode nhiều lần, loại path segment, bỏ port hoặc đổi casing ngoài quy tắc profile, vì có thể biến hai URI khác nhau thành một. Sử dụng thư viện URI parser có quy tắc rõ và match against **registered values** theo OAuth/security profile.

## 10. State: bảo vệ correlation và CSRF tại callback

**state** là giá trị client tạo để liên kết callback với một authorization transaction đã bắt đầu. Nó có thể chống CSRF đối với client khi dùng đúng.

### Thói quen triển khai an toàn

1. Client tạo state ngẫu nhiên không dự đoán được, đủ entropy.
2. Lưu state trong transaction tương ứng cùng **issuer, redirect URI, PKCE verifier, nonce nếu có, requested purpose**.
3. Gắn state vào authorization request.
4. Khi callback đến, xác minh state tồn tại, chưa dùng, thuộc đúng browser/session và đúng AS dự kiến.
5. **Consume state một lần**, không tái dùng cho callback khác.
6. Nếu state thiếu/sai/đã dùng, từ chối callback và không gửi code đến token endpoint.

### Hai tab đăng nhập đồng thời

~~~text
Tab A: state=A, verifier=A, expectedIssuer=AS1
Tab B: state=B, verifier=B, expectedIssuer=AS1

Callback state=A -> dùng verifier=A.
Callback state=B -> dùng verifier=B.
~~~

Sai: dùng một biến global **lastState** và **lastVerifier**, khiến tab B ghi đè transaction A. Có thể tạo lỗi login, mở cửa code-substitution hoặc session confusion.

### State là opaque correlation, không phải access token

Không gửi user ID, plaintext email, password, RT, session secret hoặc quyền admin bên trong state. Nếu state được encode/structured, cần chống sửa và replay; **đừng coi dữ liệu caller tự đưa trong state là policy authority**.

### PKCE có thay state không?

PKCE giúp ràng code với verifier và theo một số profile có thể hỗ trợ phòng CSRF khi client chắc chắn AS hỗ trợ/enforce PKCE. Tuy nhiên hệ thống đa AS/đăng nhập OIDC thường vẫn cần **transaction correlation và issuer binding rõ ràng**. Dùng state với random binding là một phương án dễ audit; không suy rằng chỉ bật PKCE thì mọi vấn đề login CSRF, mix-up và tab correlation biến mất.

## 11. OAuth mix-up: response đến từ AS nào?

Một client có thể hỗ trợ nhiều Authorization Servers: AS-A, AS-B. **OAuth mix-up** xảy ra khi client nhầm response đến từ issuer nào, có thể gửi code hoặc token request đến endpoint sai hoặc chấp nhận identity từ nguồn không đúng.

### Tình huống

~~~text
Client bắt đầu authorization với AS-A.
Attacker tác động luồng browser/callback.
Client nhận code nhưng gán transaction sang AS-B.
Client gửi code/credentials đến AS-B token endpoint sai.
~~~

Hậu quả tùy kiến trúc, nhưng có thể gồm **code leakage, token substitution hoặc login session confusion**.

### Bảo vệ

- Client lưu **expected issuer** trong từng authorization transaction.
- Chỉ dùng authorization/token endpoints từ **trusted AS metadata**.
- Ràng **redirect URI/callback/AS identity** theo profile; ở multi-AS có thể dùng distinct redirect URIs.
- Khi AS cung cấp issuer identifier trong authorization response theo **RFC 9207**, client phải đối chiếu **iss** với issuer mong đợi.
- Với OIDC, kiểm issuer của **ID token** sau token exchange; không để bước này thay việc chống mix-up trước khi gửi code đến endpoint sai.
- Không tin **issuer** do query parameter tự khai nếu không đối chiếu với transaction và metadata đáng tin.
- Bảo vệ state, PKCE và transaction lookup khỏi fixation/replay.

### Ví dụ response có iss

~~~http
HTTP/1.1 302 Found
Location: https://dashboard.example.test/oauth/callback?code=EXAMPLE_CODE&state=EXAMPLE_STATE&iss=https%3A%2F%2Fidentity.example.test
~~~

**iss trong authorization response** được chuẩn hóa bởi RFC 9207 nếu AS/client dùng extension này. Client phải kiểm giá trị với expected issuer; không chỉ log rồi bỏ qua. Không nhầm iss này với JWT iss claim đã được xác thực về sau.

## 12. Authentication: login người dùng là trách nhiệm AS/OP

Authorization endpoint có thể yêu cầu user **đăng nhập** trước khi AS quyết định cấp quyền. OAuth 2.0 không định nghĩa chi tiết phương thức login (password, passkey, MFA, SSO), còn OIDC định nghĩa cách biểu đạt kết quả xác thực trong ID token/profile.

### Một quy trình minh họa

~~~text
GET /authorize
    -> validate authorization request
    -> check AS login session / authentication age / risk
    -> if necessary, run login or step-up authentication
    -> resume exact pending authorization transaction
    -> evaluate consent and resource owner authority
    -> issue code or deny
~~~

**Client không được quyết định user đã đăng nhập vào AS bằng một header tùy ý**. Session và authentication context phải được quản lý bởi AS theo chính sách.

### Authentication khác authorization

Một user đăng nhập thành công **không tự được phép** cấp orders:refund cho client nếu user không có refund permission, client không được đăng ký scope hoặc resource policy cấm.

Một user cũng có thể **đã đăng nhập vào AS nhưng từ chối consent** cho client. Kết quả hợp lý là authorization denial, không phải lỗi xác minh mật khẩu.

### Step-up authentication

Những scope nhạy cảm như payments:approve có thể yêu cầu MFA, authentication age hoặc assurance level cao hơn.

OIDC có thể sử dụng các tham số **max_age, prompt, acr_values** khi profile hỗ trợ. Nhưng client chỉ **yêu cầu** mức assurance; **AS quyết định và kiểm chứng** sự kiện xác thực, không chấp nhận client tự khai “MFA=true” như sự thật.

### Prompt không là quyền vượt policy

- **prompt=login** có thể yêu cầu reauthentication theo OIDC.
- **prompt=consent** có thể yêu cầu hiển thị consent lại.
- **prompt=none** yêu cầu xử lý không có tương tác; nếu không thể đáp ứng thì trả lỗi tương ứng theo OIDC profile, **không tự bỏ qua login/consent**.
- **max_age** có thể đòi authentication gần đây; không được bỏ qua chỉ vì user có cookie cũ.

## 13. Consent: xác định điều gì được cấp cho client

Sau khi user xác thực, AS có thể cần màn hình **consent** để resource owner quyết định có cấp quyền cho OAuth client hay không.

~~~mermaid
flowchart TD
    A["Request từ client"] --> B["Check client registration và redirect"]
    B --> C["Check login/session và subject"]
    C --> D{"Consent/grant hiện tại đủ?"}
    D -->|Có, policy cho phép tái dùng| E["Persist authorized context và issue code"]
    D -->|Chưa| F["Hiển thị client + resource + requested scopes"]
    F --> G{"Resource owner đồng ý?"}
    G -->|Có, within policy| E
    G -->|Không| H["access_denied tới verified redirect URI"]
~~~

### Consent không được mở rộng registration

Nếu client được phép xin **orders:read** nhưng gửi **orders:read orders:refund**, người dùng có bấm đồng ý cũng không làm refund trở thành hợp lệ. AS phải kiểm trần quyền từ client registration, user authority, resource và risk policy.

### Consent screen cần rõ ràng

- Hiển thị **tên client đáng tin cậy**, domain/identity và publisher khi có nguồn xác minh.
- Mô tả **hành động** của scopes theo ngôn ngữ người dùng hiểu, phân biệt read, modify, approve và refund.
- Nêu resource/organization được truy cập khi phù hợp.
- Không ẩn scope nhạy cảm trong mô tả chung.
- Không tạo forced consent bằng thiết kế gây hiểu nhầm.
- Cho user từ chối mà không tự cấp token.
- Lưu consent/grant theo client, subject, scopes, resource và thời gian.

### Consent và session state phải ràng cùng transaction

Một CSRF attacker không nên được gửi **POST /consent/approve** để phê duyệt một authorization request khác chỉ dựa vào cookie login của user.

Cần:

- CSRF protection cho những hành động POST có side effect.
- Transaction ID/nonce nội bộ không đoán được gắn browser session.
- Kiểm pending authorization transaction thuộc user hiện tại và client/resource đúng.
- Chặn double submit/replay và pending transaction hết hạn.
- Chỉ chấp nhận scopes thuộc verified request/grant, không tin hidden input chứa extra scopes.

**Consent không chỉ là một nút Allow**; nó là quyết định cấp quyền phải được ghi nhận và ràng với authorization grant.

## 14. Authorization code: artifact ngắn hạn, one-time và ràng ngữ cảnh

Authorization code nên là credential có entropy cao, **khó dự đoán, ngắn hạn và chỉ redeem một lần**.

Những thông tin AS cần gắn vào record code hoặc trạng thái tương đương:

| Field/thuộc tính | Ý nghĩa |
| --- | --- |
| **code identity/digest** | Tra cứu code mà không cần ghi raw code trong log hoặc DB. |
| **client_id** | Chỉ client liên quan được đổi code, kèm client auth nếu có. |
| **redirect_uri** | Ràng callback đã được xác minh; kiểm khi redeem theo protocol. |
| **code_challenge/method** | PKCE S256 binding với verifier. |
| **subject/session context** | Người dùng và authentication context đã được AS xác nhận. |
| **authorized scopes** | Phạm vi thực sự được cấp, không phải scope request thô. |
| **resource/audience** | AT intended cho resource nào. |
| **nonce/OIDC context** | Khi profile OIDC cần đưa nonce vào ID token và kiểm ở RP. |
| **issued_at/expires_at** | Đảm bảo code TTL ngắn, hết hạn bị reject. |
| **state=ACTIVE/CONSUMED/REVOKED** | One-time redemption và audit. |
| **authorization transaction ID** | Nối login, consent, code và grant theo source of truth. |

**Code không phải scope, role, token hay bằng chứng mọi quyền của user**. Nó chỉ là artifact để client đổi grant đã được AS quyết định, với các binding bắt buộc.

### Tại sao lưu digest?

Với opaque code ngẫu nhiên đủ entropy, AS có thể lưu hash/HMAC lookup:

~~~text
rawCode <- CSPRNG(high entropy)
lookupDigest = HMAC_SHA256(codeLookupSecret, rawCode)
store lookupDigest + authorization context + expiry
return rawCode in browser redirect
~~~

Đây là thiết kế vận hành minh họa, không phải yêu cầu OAuth phải dùng HMAC thay hash. Không lưu raw code trong analytics/logs để debug; bảo vệ secret của lookup nếu dùng HMAC.

### Đừng nhầm code với access token

Resource Server không nên chấp nhận:

~~~http
Authorization: Bearer EXAMPLE_AUTHORIZATION_CODE
~~~

Authorization code chỉ có ý nghĩa tại AS token endpoint để **đổi token**, không dùng để gọi Orders API.

## 15. Token endpoint kiểm lại trước khi đổi code

Authorization endpoint phát code **không phải** bước cuối cùng. Khi client gửi code đến token endpoint, AS phải thực thi binding/one-time semantics.

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=EXAMPLE_AUTHORIZATION_CODE&redirect_uri=https%3A%2F%2Fdashboard.example.test%2Foauth%2Fcallback&client_id=dashboard-web&code_verifier=EXAMPLE_CODE_VERIFIER
~~~

Ví dụ minh họa một **public client**. Confidential client cần phương thức **client authentication** theo registration và token endpoint security. Không đặt client secret vào URL hoặc front-channel authorization request.

### Những điều token endpoint phải kiểm

1. Token endpoint đúng trusted AS issuer.
2. grant_type được hỗ trợ/cho phép cho client.
3. Client được nhận diện, và **authenticate** nếu thuộc loại yêu cầu client auth.
4. Code được AS phát, chưa dùng/chưa hết hạn.
5. Code thuộc client_id hiện tại.
6. Redirect URI khớp ngữ cảnh code/authorization request theo yêu cầu.
7. PKCE verifier đúng challenge đã gắn code và method.
8. Authorization grant chưa bị revoke, scope/resource vẫn được phép theo chính sách.
9. Code được **consume nguyên tử**, không đổi được hai lần.
10. AT/ID token/RT được phát cho đúng client, issuer, scopes, audience, TTL và profile.

### Không cho scope được phình ở token endpoint

Nếu authorization code record chỉ có **orders:read** nhưng client gửi thêm scope=orders:approve khi redeem, AS không được mint AT với scope approve chỉ vì parameter xuất hiện. Source of truth là **persisted authorized grant**, không phải một chuỗi scope mới.

## 16. One-time code redemption và race condition

Hai requests có thể gửi cùng code gần đồng thời:

~~~text
Request A: reads code ACTIVE
Request B: reads code ACTIVE
A issues AT1
B issues AT2
A marks code CONSUMED
B marks code CONSUMED
~~~

Nếu state transition không nguyên tử, cùng code có thể phát nhiều token.

### Cách tiếp cận

~~~sql
-- Ví dụ PostgreSQL-like, rút gọn cho ý tưởng atomic consume.
UPDATE authorization_codes
SET state = 'CONSUMED',
    consumed_at = CURRENT_TIMESTAMP
WHERE code_lookup_hmac = :presented_code_digest
  AND state = 'ACTIVE'
  AND expires_at > CURRENT_TIMESTAMP
  AND client_id = :authenticated_client_id
RETURNING authorization_id, redirect_uri, code_challenge,
          code_challenge_method, authorized_scope, resource;
~~~

**Đây chỉ là hình thái minh họa**: ứng dụng phải kiểm client authentication, redirect URI, PKCE và các binding trước khi commit redemption, quản lý transaction/row locks và token issuance an toàn. Nếu không có row được return hoặc any check fail, không phát token.

### Không coi PKCE đúng là cho phép redeem lần hai

Ngay cả client hợp lệ gửi **cùng verifier**, authorization code đã CONSUMED phải bị reject. PKCE chỉ chứng minh binding với transaction, **không thay one-time rule**.

### Phản hồi mất sau commit

Nếu AS commit code consumed và phát token nhưng client không nhận response, retry code vẫn phải bị từ chối theo policy. Điều này có thể tạo UX đăng nhập lại; không tự bật grace period cho code theo yêu cầu không được kiểm.

### Rủi ro multi-region

Hai AS replicas dựa vào **eventual-consistent code stores** có thể cùng thấy code ACTIVE và phát tokens. Dùng transactional/linearizable state hoặc single-writer/fencing theo authorization transaction, và fail closed khi không thể xác minh one-time state.

## 17. OpenID Connect tại authorization endpoint

**OpenID Connect (OIDC)** xây trên OAuth 2.0 để client/Relying Party nhận thông tin về việc **người dùng đã được xác thực** bởi OpenID Provider (OP), thường qua ID token và các cơ chế OIDC khác.

Một authorization request OIDC Code Flow thường có scope **openid**:

~~~http
GET /oauth2/authorize?response_type=code&client_id=dashboard-web&redirect_uri=https%3A%2F%2Fdashboard.example.test%2Foidc%2Fcallback&scope=openid%20profile%20orders%3Aread&state=EXAMPLE_STATE&nonce=EXAMPLE_NONCE&code_challenge=EXAMPLE_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
~~~

### openid và quyền API không phải một

- **openid** biểu thị request OIDC authentication theo profile.
- **profile/email** có thể yêu cầu claims/user information theo OIDC policy.
- **orders:read** là scope API riêng được AS/Orders định nghĩa.

Một ID token có **sub, iss, aud, exp** để RP xác minh authentication, **không tự có nghĩa user được truy cập mọi Orders records**. Orders RS phải nhận và validate **access token** dành cho Orders; không dùng ID token thay access token.

### nonce trong OIDC

**nonce** giúp RP liên kết kết quả authentication với request trước đó và giảm replay/substitution theo OIDC rules.

- RP tạo nonce ngẫu nhiên, ràng với transaction.
- Nếu nonce được gửi hoặc profile yêu cầu, OP phản ánh theo quy tắc trong **ID token**.
- RP verify nonce claim theo expected nonce sau khi verify ID token signature và claims.
- Nonce của tab A không dùng cho tab B.
- Nonce không phải OAuth state, không phải DPoP nonce và không phải authorization code.

**Trong OIDC Authorization Code Flow cơ bản, nonce không luôn bắt buộc theo mọi tình huống**, khác các response types có ID token trong front channel; nhưng việc dùng nonce làm correlation defense có thể hữu ích và profile rủi ro cao có thể yêu cầu nó.

### ID token không được phát bởi authorization endpoint trong Code Flow

Với **response_type=code**, authorization endpoint trả **code** qua browser, rồi token endpoint mới trả token theo OIDC Code Flow. Những OIDC hybrid/implicit profiles có response types khác, nhưng không nên tự bật chúng chỉ vì client gửi response_type khác; phải theo policy đã đăng ký, standards hiện hành và security review.

## 18. OIDC prompt, max_age và authentication context

Một request có thể yêu cầu:

~~~text
prompt=login
max_age=300
acr_values=urn:example:assurance:high
~~~

Đây là **ví dụ OIDC request**, không khẳng định mọi AS hiểu giá trị acr_values minh họa.

### AS xử lý ra sao?

- **prompt=login:** yêu cầu OP reauthenticate user theo OIDC policy.
- **prompt=consent:** yêu cầu OP hiển thị consent lại khi hỗ trợ.
- **prompt=none:** AS phải xử lý không có tương tác; nếu login/consent chưa đáp ứng thì trả lỗi OIDC phù hợp, không bật quyền âm thầm.
- **max_age:** yêu cầu giới hạn thời gian từ lần authentication; OP phải kiểm thực tế auth time theo profile.
- **acr_values:** mức assurance được yêu cầu, OP quyết định thỏa hay không dựa trên chính sách và trạng thái xác thực thực.

### Không tin client tự khai authentication success

Request:

~~~http
GET /oauth2/authorize?...&mfa_passed=true&auth_time=now HTTP/1.1
Host: identity.example.test
~~~

không thể làm AS coi user đã MFA. Những query parameters do client/browser gửi **không phải kết quả xác thực**. AS phải dựa vào session/identity system đáng tin, kiểm credentials và authentication events.

### Step-up không nhất thiết đồng nghĩa scope được cấp

User đạt MFA mức cao vẫn có thể không được phép **payments:refund** vì client, grant, tenant hoặc policy không cho. **Authentication strength** và **authorization scope** là hai trục quyết định khác nhau.

## 19. Scope và resource indicators phải được kiểm ngay ở authorization endpoint

Client có thể xin:

~~~text
scope=openid orders:read orders:approve
resource=https://orders.example.test/api
~~~

Authorization endpoint không nên lưu nguyên request rồi phát code cho bất kỳ scope nào. Nó phải xác định:

1. Client registration có allowed scopes/resources gì?
2. Subject/user có quyền thực hiện hành động liên quan không?
3. Consent/grant hiện tại bao phủ scope nào?
4. Resource indicator có thuộc trusted resource registry không?
5. Scope có ý nghĩa trong intended resource không?
6. Scope quyền cao có yêu cầu approval, step-up hoặc hạn TTL riêng không?
7. Nếu AS có default scope, default đó có hạn chế rủi ro và có được giải thích rõ không?

### Phân biệt các tập

~~~text
S_requested = scope client xin
S_client = scope client registration cho phép
S_grant = scope được consent/grant cho phép
S_resource = scope hợp lệ với intended resource

S_authorized = scope AS thật sự cấp theo chính sách.
~~~

Trong những policy ánh xạ các tập độc lập, S_authorized thường là tập con của các giới hạn trên; một số hệ thống có mapping/default/structured permissions riêng. **Không lấy raw requestedScope làm source of truth cho code/token**.

### Audience restriction

Nếu client xin token cho **Orders**, AS phải ràng intended resource/audience và scopes đúng với Orders. Một code cho Orders không được đổi thành AT cho **Payments** chỉ vì token request có resource=payments-api mới ngoài authorized context.

### Multi-tenant scope

Một scope orders:read không tự cho user đọc dữ liệu mọi tenant. AS có thể ràng tenant context trong grant/token, nhưng **Orders RS vẫn phải kiểm quyền trên resource và tenant cụ thể**, không suy từ việc user đã consent.

### Consent không vượt client registration

User có thể đồng ý approve, nhưng nếu client chỉ được đăng ký read thì AS phải deny/narrow theo policy; không cấp scope high-risk chỉ vì browser gửi giá trị trong consent form.

## 20. Pushed Authorization Requests (PAR): đưa request qua kênh bảo vệ

**RFC 9126** định nghĩa **Pushed Authorization Requests (PAR)**. Client có thể gửi các authorization request parameters đến một **PAR endpoint** của AS qua kênh trực tiếp trước, nhận một **request_uri**, rồi dùng URI đó tại authorization endpoint.

### Luồng đơn giản

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant PAR as AS PAR Endpoint
    participant B as Browser
    participant AUTH as AS Authorization Endpoint

    C->>PAR: POST authorization request parameters (+ client auth khi cần)
    PAR->>PAR: Validate client, request and policy binding
    PAR-->>C: request_uri + expires_in
    C-->>B: Redirect to /authorize?client_id=...&request_uri=...
    B->>AUTH: Authorization request referencing request_uri
    AUTH->>AUTH: Resolve trusted pushed request, validate client/binding/expiry
    AUTH->>B: Login/consent + code redirect
~~~

Ví dụ gửi PAR request (không phải syntax bắt buộc của mọi implementation):

~~~http
POST /oauth2/par HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic EXAMPLE_CLIENT_AUTH

response_type=code&client_id=dashboard-web&redirect_uri=https%3A%2F%2Fdashboard.example.test%2Foauth%2Fcallback&scope=orders%3Aread&state=EXAMPLE_STATE&code_challenge=EXAMPLE_CHALLENGE&code_challenge_method=S256
~~~

Ví dụ response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store

{
  "request_uri": "urn:ietf:params:oauth:request_uri:EXAMPLE_OPAQUE_REFERENCE",
  "expires_in": 90
}
~~~

Giá trị request_uri cần được AS cấp, ràng client và thời hạn; không dùng URI do attacker tự điền hoặc trỏ tới server tùy ý làm trusted request. Nếu PAR endpoint yêu cầu client authentication, phải xác thực theo registration; public clients có các quy tắc xác định client riêng theo profile.

### PAR giúp gì?

- Giảm các authorization request parameters lộ qua browser/front channel.
- Hỗ trợ AS kiểm, ràng và lưu request trước khi user tương tác.
- Hạn chế tampering với request parameters mà AS đã nhận qua kênh trực tiếp.
- Có thể giảm URL dài và rủi ro tham số bị sửa.
- Hỗ trợ security profiles muốn request integrity mạnh hơn.

### PAR không thay những gì?

- Không tự thay user authentication/consent.
- Không xóa requirement của **PKCE, state, redirect URI validation, scope/resource policy**.
- Không cho phép client xin scope ngoài registration.
- Không tự xác thực user bằng việc PAR request hợp lệ.
- Không cho request_uri bị reuse ngoài policy hoặc không ràng client.

**PAR là cách bảo vệ và quản lý authorization request, không phải cơ chế cấp phép mặc định cho mọi scope mà client gửi.**

## 21. JAR: JWT-Secured Authorization Request

**RFC 9101** định nghĩa **JWT-Secured Authorization Request (JAR)**, cho phép các authorization request parameters được biểu diễn trong **JWT Request Object** và bảo vệ integrity/origin theo profile.

Một Request Object có thể bao gồm:

~~~json
{
  "iss": "dashboard-web",
  "aud": "https://identity.example.test",
  "response_type": "code",
  "client_id": "dashboard-web",
  "redirect_uri": "https://dashboard.example.test/oauth/callback",
  "scope": "orders:read",
  "state": "EXAMPLE_STATE",
  "code_challenge": "EXAMPLE_CHALLENGE",
  "code_challenge_method": "S256",
  "exp": 1796000100
}
~~~

Đây là **payload khái niệm**, không phải JWT hoàn chỉnh: Request Object phải được tạo/kiểm đúng theo JAR profile (including signature, algorithm/claims/time, nếu profile yêu cầu). **Không lấy JSON tự khai làm signed request object**.

### Điều phải kiểm ở AS

- Request Object liên quan đúng **client_id/issuer**.
- JWT signature, key material, algorithm và lifetime theo trusted client registration.
- Audience/recipient của Request Object là AS đúng.
- Claims như **exp, nbf, iat, jti** theo profile và replay/TTL policy khi cần.
- Mọi parameter được AS sử dụng phải xuất phát từ nguồn/precedence hợp lệ, tránh **parameter pollution**.
- Inner Request Object scope/resource vẫn phải chịu **client/grant/consent policy**, không biến một chữ ký client thành quyền cao.
- Nếu kết hợp PAR, kiểm cả **request_uri** lẫn Request Object phù hợp contract và client binding.

### Signed request không có nghĩa user đã cấp quyền

Client ký một Request Object với scope payments:refund chỉ chứng minh client sở hữu signing credential, **không chứng minh user consent hoặc AS authorization policy đã cho refund**.

### PAR và JAR khác nhau

| Khía cạnh | PAR | JAR |
| --- | --- | --- |
| Cơ chế | Push request parameters qua PAR endpoint, nhận request_uri. | Gói request thành JWT Request Object, thường có signed integrity. |
| Bảo vệ chính | Bảo vệ kênh/chống tampering sau push và ràng request phía AS. | Integrity/origin của request object theo trusted signing key/profile. |
| Có cần browser redirect? | Có, client dùng request_uri ở authorization endpoint. | Có thể đưa request/request_uri theo profile. |
| Tự cấp quyền OAuth? | Không. | Không. |
| Có thể kết hợp? | Có, tùy AS/profile. | Có, tùy AS/profile. |

Không tự áp một extension mà AS/client chưa hỗ trợ; các profile nâng cao như Financial-grade API có thể **bắt buộc** dùng một số cơ chế, nhưng yêu cầu cụ thể phụ thuộc profile áp dụng.

## 22. Authorization response modes và front-channel data hygiene

Authorization response có thể được gửi bằng **redirect query parameters** trong Authorization Code Flow, hoặc qua **form_post** khi response_mode extension/profile hỗ trợ.

### Query response

~~~http
HTTP/1.1 302 Found
Location: https://dashboard.example.test/callback?code=EXAMPLE_CODE&state=EXAMPLE_STATE
~~~

Ưu điểm đơn giản; nhược điểm là code/state xuất hiện trên URL, có thể đi vào browser history, web server access logs hoặc analytics nếu client xử lý thiếu cẩn thận.

### form_post

Trong profile hỗ trợ **response_mode=form_post**, AS trả HTML form tự động POST tới registered redirect URI với fields code/state/issuer khi phù hợp.

**form_post không làm code bớt nhạy cảm**: client phải kiểm HTTPS, CSRF/transaction state, origin/context và không log form body chứa code. Không tự coi một POST callback là trusted chỉ vì nó không xuất hiện trong URL.

### Front-channel hygiene

- Callback endpoint không tải third-party scripts trước khi xử lý code/state.
- Dùng **Referrer-Policy** phù hợp, hạn referrer leakage.
- Không gửi code/state trong URL tới analytics, error trackers hoặc click trackers.
- Tránh open redirects và iframe/embed nguy hiểm trên callback/login.
- Dùng Cache-Control: no-store cho responses nhạy cảm khi phù hợp.
- Loại code/state khỏi URL/browser history sau xử lý an toàn trong SPA (nếu kiến trúc dùng SPA).
- Không ghi full query string của callback vào access logs.
- Cẩn trọng với reverse proxy/CDN log fields.

### CORS không thay OAuth redirect validation

Authorization endpoint thường được điều hướng bởi browser như một **top-level navigation**, không nhất thiết sử dụng XHR có CORS. Không mở **Access-Control-Allow-Origin: *** chỉ vì client frontend cần login; cookie/sessions và authorization flow phải được thiết kế đúng, không dựa vào CORS làm cơ chế xác thực.

## 23. Session cookies và CSRF trên login/consent UI

AS có thể quản lý browser login session bằng cookie. Các request của authorization endpoint được browser gửi cùng cookie theo chính sách SameSite/secure context.

### Cookie flags

- **Secure:** cookie chỉ được gửi qua HTTPS, trừ những mô hình development ngoại lệ cần review.
- **HttpOnly:** hạn JS đọc session cookie.
- **SameSite:** thiết kế theo redirect/navigation cross-site cần thiết; không bật tùy ý một giá trị khiến login hỏng rồi tắt CSRF checks.
- **Path/Domain:** hạn chế cookie scope; tránh chia sẻ session cookie với subdomains không tin cậy.
- **Session rotation:** sau login/privilege elevation, phòng session fixation.

### CSRF tại authorization endpoint khác CSRF tại callback

- **Client callback CSRF:** attacker cố ép client hoàn tất login/authorization transaction không do client bắt đầu. **state/PKCE/issuer binding** bảo vệ phía client.
- **AS consent/login CSRF:** attacker cố lợi dụng browser có AS session để phê duyệt hoặc thay đổi authentication state. Cần **CSRF token, transaction binding, same-site policy và POST handling** trong AS UI.
- **Login CSRF/session swapping:** user bị gắn vào account/transaction ngoài ý muốn. Cần chống ở AS và RP theo OIDC security profile.

### Không cho browser tự sửa pending grant

Một consent POST như:

~~~http
POST /oauth2/consent HTTP/1.1
Host: identity.example.test
Cookie: AUTH_SESSION=EXAMPLE_COOKIE
Content-Type: application/x-www-form-urlencoded

transaction_id=EXAMPLE_TX&approved=true&scope=orders%3Arefund
~~~

không được làm AS cấp orders:refund nếu verified pending authorization transaction chỉ được cấp orders:read. AS phải **đọc authorized scope từ server-side transaction**, đối chiếu user/session và policy; form body chỉ có thể là quyết định approve/deny hoặc subset hợp lệ theo hợp đồng.

### Browser security còn cần gì?

- Content Security Policy và output encoding cho login/consent screens.
- Chống clickjacking bằng frame-ancestors/X-Frame-Options theo flow.
- XSS protection trong trang AS, vì XSS có thể chiếm session hoặc sửa consent.
- Rate limits cho login, authorization attempts và consent actions.
- Phòng open redirect và script injection từ thông tin client display name/logo/redirect URI.

**Authorization endpoint là một UI bảo mật quan trọng**, không chỉ là router tạo HTTP 302.

## 24. OAuth client types và authorization endpoint policy

### Public clients

SPA và native apps thường là **public clients**, không giữ được client secret an toàn nếu secret nằm trong code được phân phối. Với Authorization Code Flow, cần PKCE và các ràng buộc thích hợp theo current security BCP.

- Không coi việc client gửi client_id là authentication proof.
- Không nhúng client_secret tĩnh trong JavaScript/mobile app rồi gọi đó là confidential.
- PKCE verifier phải được giữ đủ an toàn cho transaction, không đưa vào redirect URL.
- Client kiểm state/issuer/callback trước token exchange.
- Với native app, dùng external user-agent/browser theo RFC 8252 và redirect handling đúng platform.

### Confidential clients

Backend/BFF có thể giữ client credentials trong secret manager/HSM hoặc phương thức xác thực khác.

- Client vẫn phải kiểm CSRF/state và chống code injection/mix-up.
- Token endpoint phải xác thực client theo registration khi flow yêu cầu.
- PKCE vẫn là defense bổ sung hữu ích và được khuyến nghị theo current practice.
- Client secret không đưa vào authorization URL, state, redirect URI hay front-channel.
- Confidential không đồng nghĩa token/authorization request được phép có scope admin vô hạn.

### Browser-only và BFF architecture

Một Backend-for-Frontend có thể giữ AT/RT ở server side và đưa browser session cookie riêng, giảm số credentials lộ trong frontend. Nhưng BFF cần chống CSRF, secure cookie, request binding và object-level authorization; kiến trúc này **không tự sửa issuance/redirect URI bugs**.

## 25. Authorization endpoint và token lifecycle

Authorization endpoint nằm ở **đầu vòng đời**:

~~~mermaid
flowchart LR
    A["Client tạo authorization request"] --> B["AS xác thực user và cấp quyền"]
    B --> C["AS phát authorization code one-time"]
    C --> D["Client đổi code tại token endpoint"]
    D --> E["AS phát Access Token / ID Token / RT nếu hợp lệ"]
    E --> F["RS kiểm AT mỗi lần sử dụng"]
    F --> G["AT hết hạn hoặc bị revoke theo chính sách"]
    E --> H["RT rotation / grant refresh theo policy"]
    H --> E
~~~

Điểm phân chia:

- Authorization code dùng **một lần** tại token endpoint.
- Access token Bearer thường được dùng **nhiều lần** tại RS trong thời hạn.
- Refresh token được xử lý tại **token endpoint**, có thể rotation/reuse detection theo profile.
- ID token dành cho RP và có validation rules riêng.
- Token revocation/introspection và key rotation thuộc những quy trình **sau issuance**, không phải browser authorization endpoint.

### Logout và consent revocation

Người dùng đóng browser, logout RP hoặc rút consent **không tự chứng minh mọi AT tự hết hiệu lực**. Cần session/token/grant revocation architecture và propagation tới RS nếu policy yêu cầu.

### Scope/audience sau issuance

Authorization endpoint có thể cấp grant **orders:read**, nhưng RS vẫn phải kiểm token audience=orders-api, scope và order ownership. **Một permission change trong DB không tự sửa JWT đã ký**; giải pháp có thể là TTL ngắn, token/grant revocation hoặc online authorization checks cho hành động nhạy cảm.

## 26. Java: sinh state và PKCE S256

Ví dụ Java 17 sau tạo **state** và **PKCE code_verifier** bằng SecureRandom, rồi tính challenge theo RFC 7636:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceAuthorizationValues {

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder URL_BASE64 =
            Base64.getUrlEncoder().withoutPadding();

    public record Values(
            String state,
            String codeVerifier,
            String codeChallenge,
            String challengeMethod) {}

    public static Values create() throws Exception {
        byte[] stateBytes = new byte[32];
        byte[] verifierBytes = new byte[32];

        RANDOM.nextBytes(stateBytes);
        RANDOM.nextBytes(verifierBytes);

        String state = URL_BASE64.encodeToString(stateBytes);
        String verifier = URL_BASE64.encodeToString(verifierBytes);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        String challenge = URL_BASE64.encodeToString(digest);

        return new Values(state, verifier, challenge, "S256");
    }
}
~~~

**32 random bytes** tạo một Base64URL verifier dài 43 ký tự, phù hợp chiều dài PKCE verifier; vẫn cần library/profile validation cho real client. Không dùng state/verifier từ counter/timestamp hoặc tái sử dụng cho nhiều authorization transactions.

### Gửi cái gì qua browser?

~~~text
Authorization request to AS:
    state = random state
    code_challenge = BASE64URL(SHA256(ASCII(verifier)))
    code_challenge_method = S256

Not in browser authorization URL:
    code_verifier
    client_secret
    refresh_token
    private signing key
~~~

Client lưu verifier, state, expected issuer và nonce khi có trong **pending authorization transaction** gắn browser session, không trong URL.

### Hạn chế của ví dụ

- Sinh secrets chưa đồng nghĩa lưu/consume transaction an toàn.
- Không ghi state/verifier thật vào logs hoặc analytics.
- Không đặt verifier trong local/global variable dùng chung giữa tabs.
- Code challenge phải được URL-encode đúng khi tạo authorization request.
- Không dùng Base64 chuẩn với dấu cộng, slash, padding tùy tiện thay Base64URL.

## 27. Java: kiểm redirect URI theo trusted client registration

Ví dụ sau chỉ phục vụ **web client redirect URLs HTTPS đã đăng ký đầy đủ**, không bao quát ngoại lệ native loopback của RFC 8252:

~~~java
import java.net.URI;
import java.util.Map;
import java.util.Set;

public final class WebRedirectUriPolicy {

    private final Map<String, Set<String>> allowedByClient;

    public WebRedirectUriPolicy(
            Map<String, Set<String>> allowedByClient) {
        this.allowedByClient = Map.copyOf(allowedByClient);
    }

    public boolean isAllowed(String clientId, String requestedUri) {
        if (clientId == null || requestedUri == null) {
            return false;
        }

        Set<String> registered = allowedByClient.get(clientId);
        if (registered == null || !registered.contains(requestedUri)) {
            return false;
        }

        try {
            URI parsed = URI.create(requestedUri);
            return parsed.isAbsolute()
                    && "https".equalsIgnoreCase(parsed.getScheme())
                    && parsed.getHost() != null
                    && parsed.getUserInfo() == null
                    && parsed.getFragment() == null;
        } catch (IllegalArgumentException e) {
            return false;
        }
    }
}
~~~

### Ranh giới cần giữ

- allowedByClient phải lấy từ **trusted registration store**, không được tạo từ query parameter client gửi.
- Chỉ kiểm **exact registered URI** theo chính sách web client này; không sử dụng startsWith hay endsWith.
- Không tự áp rule HTTPS-only cứng nhắc cho mọi native app; loopback redirect port và custom schemes phải theo profile riêng.
- Phân biệt **redirect URI syntax validation** với **redirect URI registration binding**: một HTTPS URI hợp lệ về cú pháp vẫn có thể là domain attacker.
- Đừng đưa authorization code hoặc error chứa dữ liệu nhạy cảm đến URI không hợp lệ; hiển thị lỗi an toàn tại AS.

### Thử các URI sau

~~~text
Registered:
    https://dashboard.example.test/oauth/callback

Expected reject:
    https://dashboard.example.test.attacker.invalid/oauth/callback
    http://dashboard.example.test/oauth/callback
    https://attacker.invalid/receive
    https://dashboard.example.test/oauth/callback/extra
    https://dashboard.example.test/redirect?to=https://attacker.invalid
       (nếu URI đó không được đăng ký)
~~~

Nếu URI có mặt trong allowlist nhưng endpoint là **open redirector**, client và AS vẫn cần security review để ngăn code bị forward đến bên không tin cậy.

## 28. Client callback: state, issuer và code thuộc transaction nào?

Client cần lưu một record pending:

~~~java
import java.time.Instant;

public record PendingAuthorizationTransaction(
        String browserSessionId,
        String state,
        String expectedIssuer,
        String redirectUri,
        String clientId,
        String pkceCodeVerifier,
        String oidcNonce,
        Instant expiresAt) {}
~~~

Đây là **DTO minh họa**. Trong production, record phải được lưu theo session và có kiểm định dạng/TTL, bảo vệ bí mật của verifier, và **atomic consume** khi callback đến.

### Callback verification pseudocode

~~~text
function handleAuthorizationCallback(browserSession, callback):
    require callback.state exists and within size limits

    tx = pendingStore.atomicConsume(
        browserSession, callback.state
    )
    if tx absent, expired or consumed:
        REJECT without token exchange

    require callback arrived on registered callback for tx
    require callback issuer matches tx.expectedIssuer
        when RFC 9207/profile is used
    require tx.expectedIssuer maps to trusted AS metadata

    if callback.error exists:
        handle safe denial, do not exchange
        return

    require callback.code valid syntax and length

    tokenResponse = POST tx.expectedIssuer.tokenEndpoint:
        code = callback.code
        redirect_uri = tx.redirectUri
        code_verifier = tx.pkceCodeVerifier
        client authentication when required

    validate token response and OIDC ID token nonce if applicable
    establish authorized client session under policy
~~~

### Một state cho mỗi authorization transaction

Browser tab A và tab B không được ghi đè state, verifier, expected issuer hoặc nonce của nhau. **Một callback với state đã dùng** không nên khởi động thêm token exchange; xử lý bằng flow mới/recovery.

### Login CSRF và OAuth mix-up

PKCE giúp chống một số code interception/injection scenarios, nhưng client vẫn cần **state correlation và issuer binding** khi dùng nhiều AS hoặc OIDC. Nếu callback không gắn đúng transaction, client có thể đổi code ở sai token endpoint hoặc tạo login session sai người dùng.

## 29. Spring Authorization Server: ví dụ đăng ký public client

Một phần cấu hình Spring Authorization Server minh họa:

~~~java
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

@Configuration
public class ExampleRegisteredClientConfig {

    @Bean
    RegisteredClientRepository registeredClientRepository() {
        RegisteredClient dashboard = RegisteredClient.withId(
                        UUID.randomUUID().toString())
                .clientId("dashboard-web")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.NONE)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "https://dashboard.example.test/oauth/callback")
                .scope("orders:read")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .build();

        return new InMemoryRegisteredClientRepository(dashboard);
    }
}
~~~

### Ví dụ thể hiện điều gì?

- **dashboard-web** là registered client, không phải một client_id do attacker tự tạo.
- Public client dùng authentication method **none**, không giả định có client secret giấu trong browser.
- Chỉ cho Authorization Code Grant và redirect URI cụ thể.
- Yêu cầu PKCE cho registered client.
- Có yêu cầu consent và allowed scope **orders:read**.

### Chưa phải AS production

- Cần AS SecurityFilterChain, login/consent UI, issuer, signing keys, JWKS, authorized grant persistence và token endpoint configuration.
- InMemoryRegisteredClientRepository chỉ phù hợp minh họa/testing; production phải có registry bền vững, audit và consistency giữa replicas.
- Cần resource/audience policy, grant/tenant rules, scope approval, code one-time transaction và session protection.
- Cần TLS, reverse proxy trust, CSRF, account protection, rate limits và monitoring.
- Nếu cần OIDC, OP metadata, ID token/nonce, UserInfo và RP validation phải được cấu hình phù hợp.
- Framework APIs khác nhau theo phiên bản Spring; phải compile/test trong dependency thật trước khi triển khai.

Không tự tạo một controller trả code mà bỏ qua các bước framework đã hỗ trợ; **authorization endpoint là một security boundary**, không chỉ HTTP route.

## 30. Authorization endpoint: policy quyết định từ dữ liệu đáng tin

Pseudocode server-side:

~~~text
function authorize(request):
    parsed = strictParseOAuthAuthorizationRequest(request)

    client = trustedClientRegistry.findActive(parsed.clientId)
    if client absent:
        showASLocalError()
        return

    redirect = validateRegisteredRedirect(client, parsed.redirectUri)
    if redirect invalid:
        showASLocalError()  // NEVER redirect to invalid URI
        return

    require response_type=code permitted for this client
    require PKCE S256 and valid challenge when policy requires
    require scopes and resource indicators within client limits
    require state/nonce/extension parameters valid for profile

    tx = persistPendingAuthorizationRequest(
        client, redirect, requestedScopes,
        resource, codeChallenge, codeMethod, state, nonce
    )

    user = ensureASAuthentication(tx)
    if authentication cannot succeed:
        sendApprovedErrorToVerifiedRedirect(tx)
        return

    decision = evaluateGrantConsentAndPolicy(
        trustedUser=user, transaction=tx
    )
    if decision rejected or user denies:
        send access_denied to verified redirect
        return

    code = createRandomOneTimeCode(
        client, redirect, codeChallenge,
        authorizedScopes=decision.grantedScopes,
        authorizedResource=decision.resource,
        subject=user, authContext=decision.authContext
    )
    persistCodeAndGrantAtomically(code)
    redirectBrowserToVerifiedRedirect(
        code, tx.state, issuer when RFC 9207/profile applies
    )
~~~

### Sai khi tin hidden form scope

~~~text
POST /consent
approved=true
scope=orders:read orders:refund
~~~

AS không được tin field scope do browser gửi thay verified pending transaction. Nếu consent UI cho user chọn subset, AS phải bảo đảm subset **nằm trong scopes được request và được policy cho phép**, đồng thời kiểm CSRF, session binding và transaction TTL.

### Không cấp code nếu user chỉ vừa login

User authentication thành công là một điều kiện, không phải toàn bộ authorization. AS còn phải quyết định **client, scope, resource và consent/grant context** hợp lệ trước khi phát code.

## 31. Threat model: các đường tấn công vào authorization endpoint

Authorization endpoint thường nằm trước nhiều lớp kiểm soát danh tính và cấp phép. Những mối đe dọa quan trọng không chỉ là brute-force login, mà còn gồm **browser redirect, request binding, transaction state và authorization policy**.

### Case A — Redirect URI trỏ tới attacker domain

**Bối cảnh:** Client dashboard-web đã đăng ký https://dashboard.example.test/callback. Attacker thay redirect_uri thành https://attacker.invalid/receive.

**Lỗi:** AS chỉ so client_id mà không so redirect URI với registration.

**Hậu quả:** Authorization code có thể bị gửi tới attacker. PKCE có thể hạn chế token exchange nếu attacker chỉ giữ code, nhưng redirect bug vẫn nguy hiểm.

**Bảo vệ:** exact registered redirect policy cho web client, protocol-specific exception cho native nếu cần, và không redirect lỗi về URI chưa xác minh.

### Case B — Prefix/suffix redirect URI confusion

**Bối cảnh:** AS cho phép bất kỳ URI nào bắt đầu bằng https://dashboard.example.test.

**Tấn công:** Dùng host https://dashboard.example.test.attacker.invalid hoặc userinfo/encoded-host confusion.

**Bảo vệ:** URI parser, trusted registration và matching theo profile; không dùng substring/prefix thay identity binding.

### Case C — Callback open redirect

**Bối cảnh:** Registered redirect URI nằm trên domain hợp lệ nhưng endpoint hỗ trợ chuyển tiếp tùy ý bằng next=.

**Rủi ro:** Code/state có thể được chuyển tới host không tin cậy qua ứng dụng client.

**Bảo vệ:** client không làm open redirect ở callback, AS hạn chế/kiểm registered URIs và security review callback behavior. Không giải quyết bằng cách bỏ PKCE/state.

### Case D — Authorization code interception

**Bối cảnh:** Một extension, custom URI scheme handler hoặc log có bản code của client.

**Rủi ro:** Attacker thử đổi code ở token endpoint.

**Bảo vệ:** PKCE S256, one-time code, client/redirect binding, TTL ngắn, trusted token endpoint; xử lý mobile redirect theo RFC 8252.

### Case E — Code injection/login CSRF

**Bối cảnh:** Attacker lấy một authorization code cho account của attacker rồi ép browser nạn nhân đi vào callback của client với code đó.

**Rủi ro:** Client có thể tạo session gắn sai user nếu callback không kiểm transaction.

**Bảo vệ:** state gắn browser session, expected issuer, PKCE verifier theo đúng transaction, one-time consume; OIDC ID token nonce/subject validation khi áp dụng.

### Case F — Hai tabs dùng global state

**Bối cảnh:** Client lưu lastState và lastVerifier trong biến toàn cục. Tab A và B bắt đầu đăng nhập đồng thời; tab B ghi đè A.

**Rủi ro:** Code/verifier mismatch, login failure hoặc confusion nếu fallback sai.

**Bảo vệ:** state-indexed transaction store, per-browser binding, TTL và atomic consume; không global "most recent verifier".

### Case G — OAuth mix-up giữa hai AS

**Bối cảnh:** Client hỗ trợ AS-A và AS-B, callback mang code của AS-A nhưng client gửi token request tới AS-B.

**Bảo vệ:** trusted issuer metadata, expectedIssuer trong transaction, RFC 9207 iss response hoặc callback separation theo profile, không chọn endpoint từ untrusted query.

### Case H — Người dùng đã login nhưng chưa consent

**Bối cảnh:** AS thấy login session và phát code với orders:refund dù consent không có hoặc user từ chối.

**Lỗi:** Xem authentication thành authorization.

**Bảo vệ:** phân biệt login state, client registration, user entitlement, grant/consent và resource policy. access_denied khi user từ chối trong context hợp lệ.

### Case I — Consent form tampering

**Bối cảnh:** Pending request chỉ có orders:read; browser sửa POST consent form thành scope=orders:approve.

**Bảo vệ:** AS lấy requested/grant scopes từ server-side transaction đã kiểm, không tin hidden fields; CSRF token và session binding.

### Case J — Scope inflation trên authorization request

**Bối cảnh:** Client đăng ký read nhưng request approve/refund; AS sao chép scope thẳng vào authorization code grant.

**Hậu quả:** Token endpoint có thể phát AT quá quyền với chữ ký hợp lệ.

**Bảo vệ:** allowed scopes của client, user consent/authority, resource policy và scope grant persistence; kiểm AT thực tế được phát.

### Case K — Prompt=none bypass

**Bối cảnh:** Client gửi prompt=none nhưng AS không có login session/consent.

**Lỗi:** AS tự bỏ qua login/consent thay vì trả lỗi theo OIDC profile.

**Bảo vệ:** prompt=none là yêu cầu không tương tác, **không phải lệnh bypass security**; dùng lỗi như login_required/consent_required khi phù hợp profile.

### Case L — max_age và MFA bypass

**Bối cảnh:** High-risk scope cần authentication mới trong 5 phút. AS chỉ thấy cookie còn hạn nhiều giờ.

**Bảo vệ:** kiểm real auth_time/max_age/ACR policy và reauthentication/step-up khi cần. Không chấp nhận query mfa=true.

### Case M — OIDC nonce sai transaction

**Bối cảnh:** RP gửi nonce=A, token endpoint trả ID token nonce=B; client vẫn tạo session.

**Bảo vệ:** ID token validation theo OIDC bao gồm nonce binding nếu đã gửi/được profile yêu cầu. Mismatched nonce phải bị từ chối.

### Case N — Implicit grant bật lại do library default

**Bối cảnh:** AS phát access_token trong authorization response vì một client đổi response_type=token, mặc dù deployment chỉ định Authorization Code Flow.

**Rủi ro:** Bearer token đi qua browser front channel, mở tăng nguy cơ leakage.

**Bảo vệ:** deny unsupported response types, client registration và OAuth security BCP; không fallback từ code sang implicit.

### Case O — One-time code race

**Bối cảnh:** Hai AS replicas cùng thấy code ACTIVE rồi đều phát token.

**Bảo vệ:** atomic redeem with authoritative store, transaction/unique constraints, không gửi tokens trước commit, fail closed khi state không nhất quán.

### Case P — Response-mode confusion

**Bối cảnh:** Client expected query callback nhưng chấp nhận thông điệp từ query, fragment hoặc POST body không thuộc registered response mode.

**Rủi ro:** Token/code injection hoặc parser divergence.

**Bảo vệ:** response mode được thỏa thuận, strict callback parser, state/issuer checks, không “thử mọi mode đến khi được”.

### Case Q — PAR request_uri từ untrusted host

**Bối cảnh:** AS nhận request_uri và fetch arbitrary HTTPS URL do browser đưa.

**Rủi ro:** SSRF, request tampering hoặc nhận claims từ nguồn không được tin.

**Bảo vệ:** chỉ resolve AS-issued request_uri theo RFC 9126/profile, client binding, expiry và single-use semantics khi được yêu cầu; không follow attacker URL.

### Case R — JAR Request Object có chữ ký nhưng đòi scope admin

**Bối cảnh:** Client ký JAR có scope=payments:refund dù chỉ được đăng ký reports:read.

**Lỗi:** AS nhầm **client request authentication** với authorization to grant refunds.

**Bảo vệ:** verify Request Object signature **và** client registration, grant/consent, user entitlements và resource policy.

### Case S — Browser Referrer/log leak

**Bối cảnh:** Client callback tải third-party scripts/tracking trước khi xử lý code; URL/query bị ghi vào monitoring.

**Rủi ro:** Authorization code/state rò khỏi intended client.

**Bảo vệ:** strict callback page, Referrer-Policy, no raw query logging, no third-party scripts before completion, PKCE và short code TTL.

### Case T — Session fixation qua login flow

**Bối cảnh:** Attacker ép user dùng một AS session ID đã biết rồi user login.

**Bảo vệ:** secure session management, session ID rotation sau authentication, cookie protections, login CSRF và pending transaction binding.

### Case U — Consent clickjacking

**Bối cảnh:** AS consent screen bị nhúng iframe trong attacker page với UI che phủ.

**Rủi ro:** User bị dẫn bấm Allow cho scopes không chủ ý.

**Bảo vệ:** CSP frame-ancestors, X-Frame-Options theo compatibility, clickjacking defenses và consent UX rõ ràng.

### Case V — Authorization endpoint dùng untrusted reverse-proxy headers

**Bối cảnh:** AS suy redirect URI hoặc issuer từ X-Forwarded-Host do Internet caller gửi.

**Rủi ro:** Tạo callback/issuer URL attacker kiểm soát hoặc nhầm domain.

**Bảo vệ:** trusted proxy allowlist, fixed external issuer, canonical endpoints và registration checks, không tin forwarded headers từ mọi nguồn.

### Case W — Resource indicator đi lạc Payments

**Bối cảnh:** Client registered chỉ Orders nhưng gửi resource=payments-api và scope=payments:refund.

**Lỗi:** AS chỉ kiểm client_id và không đối chiếu allowed resources.

**Bảo vệ:** resource registry, client allowed audiences, scope-resource permission, no cross-resource issuance.

### Case X — Authorization code replay từ client hợp lệ

**Bối cảnh:** Client đã redeem code, sau đó cùng client/PKCE verifier retry do response mất.

**Bảo vệ:** code one-time: lần hai phải reject; recovery/reauthentication thay vì tạo tokens lần hai cho cùng code.

## 32. Quan sát, audit và vận hành authorization endpoint

Authorization endpoint xử lý cả **identity events** và **authorization policy decisions**. Metrics phải cho phép phân biệt login failure, invalid client redirect, consent denied, PKCE issues và code interception signs mà không tiết lộ secrets.

### Event names minh họa

~~~text
AUTHZ_REQUEST_RECEIVED
AUTHZ_CLIENT_UNKNOWN_OR_DISABLED
AUTHZ_RESPONSE_TYPE_NOT_ALLOWED
AUTHZ_REDIRECT_URI_REJECTED
AUTHZ_SCOPE_OUTSIDE_CLIENT_POLICY
AUTHZ_RESOURCE_NOT_ALLOWED
AUTHZ_PKCE_S256_REQUIRED
AUTHZ_REQUEST_OBJECT_INVALID
AUTHZ_PAR_REFERENCE_INVALID_OR_EXPIRED
AUTHZ_LOGIN_REQUIRED
AUTHZ_STEP_UP_REQUIRED
AUTHZ_CONSENT_REQUIRED
AUTHZ_CONSENT_DENIED
AUTHZ_CONSENT_GRANTED
AUTHZ_CODE_ISSUED
AUTHZ_CODE_EXPIRED
AUTHZ_CODE_REDEEMED
AUTHZ_CODE_REPLAY_REJECTED
AUTHZ_STATE_MISMATCH_CLIENT_SIDE
AUTHZ_MIXUP_ISSUER_MISMATCH
AUTHZ_INVALID_RESPONSE_MODE
AUTHZ_POLICY_VERSION_DRIFT
AUTHZ_TOKEN_EXCHANGE_SCOPE_MISMATCH
~~~

Đây là **tên telemetry nội bộ minh họa**, không phải một bộ mã lỗi tiêu chuẩn.

### Các câu hỏi cần đo

| Metric | Ý nghĩa |
| --- | --- |
| **authorize_success_rate** | Bao nhiêu authorization transactions hợp lệ phát code? |
| **invalid_redirect_rate** | Client/config nào đang gửi callback không hợp lệ? |
| **invalid_scope_rate** | Có scope inflation, app misconfiguration hoặc consent phishing? |
| **code_to_token_success_rate** | Bao nhiêu code thực sự được redeem hợp lệ? |
| **code_replay_reject_rate** | Có duplicate requests, retry bug hay code theft? |
| **pkce_failure_rate** | Client code_verifier binding có lỗi không? |
| **state_mismatch_rate** | Browser session/tab transaction có lỗi hoặc attack? |
| **issuer_mixup_reject_rate** | Multi-AS callback binding có đúng không? |
| **consent_denial_rate** | User từ chối bao nhiêu, client có xin quá quyền không? |
| **step_up_required_rate** | Sensitive grants có risk-based login recheck không? |
| **authorization_latency** | Login, consent và code issuance có latency bất thường? |
| **pending_transaction_age** | Có stale pending sessions, replay, lưu state vô hạn? |
| **multi_replica_policy_version** | AS instances có cấu hình scope/redirect khác nhau? |

### Audit record

~~~json
{
  "event": "AUTHZ_CODE_ISSUED",
  "timestamp": "2026-11-23T03:30:00Z",
  "issuer": "https://identity.example.test",
  "client_id": "dashboard-web",
  "authorization_transaction_reference": "example-internal-tx",
  "grant_reference": "example-grant",
  "redirect_registration_id": "dashboard-callback",
  "granted_scope_summary": ["orders:read"],
  "resource": "https://orders.example.test/api",
  "pkce_method": "S256",
  "policy_version": "authz-policy-v8",
  "result": "CODE_ISSUED"
}
~~~

Schema chỉ minh họa; không log raw code, state, verifier, RT, AT, cookies, client secrets, password hoặc ID token. User/tenant reference trong audit phải có phân quyền và retention phù hợp.

### Privacy và log hygiene

- Không log full authorization URL nếu chứa state, nonce hoặc thông tin user có thể nhận diện.
- Mask query strings ở AS/Ingress/Reverse proxy nếu cần.
- Không dùng raw token/code/state làm metrics labels.
- Chỉ giữ subject identifiers và device/IP signals khi có nhu cầu phù hợp với privacy policy.
- Với incident, sử dụng correlation IDs và audit lookup bảo mật, không copy credential vào ticket/chat.

### Runbook cho client misconfiguration

Nếu một client đột ngột tăng invalid_redirect_uri hoặc PKCE failures:

1. Xác định client_id, issuer, deployment version, environment.
2. Đối chiếu registered redirect URIs và OAuth flow config.
3. Kiểm state/verifier per transaction và frontend/BFF callback path.
4. Xác minh reverse-proxy external URL và issuer metadata.
5. Không **tạm mở wildcard redirect** hoặc tắt PKCE để khắc phục nhanh.
6. Rollback client/AS config có kiểm soát và chạy negative tests.
7. Theo dõi success/reject rates sau sửa.

### Runbook nghi code theft/mix-up

Nếu callback có code từ AS không mong đợi hoặc nhiều code reuse:

- Tạm chặn affected client/redirect paths nếu rủi ro cao.
- Kiểm code issuance ledger, client binding, redirect URI và state/issuer mismatches.
- Thu hồi affected tokens/grants khi có evidence.
- Sửa client/AS transaction binding, redirect policy, PKCE hoặc response parsing.
- Điều tra open redirects, query logs, third-party scripts, compromised browser/runtime.
- Kiểm multi-AS endpoint mapping và RFC 9207 response issuer handling khi áp dụng.

**Không tuyên bố incident contained chỉ vì URL callback đã được đổi**; phải xác minh token/grant còn khả năng bị dùng và tất cả AS/RS instances áp policy mới.

## 33. Negative tests: authorization endpoint và code flow

Những kiểm thử sau cần chạy với **test clients, synthetic users, code và session giả** trong môi trường được phép. Nên kiểm không chỉ HTTP status mà còn **đích redirect, authorization transaction, grant, code store và tokens thực sự được phát**.

| Kiểm thử | Đầu vào hoặc điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| **Happy path** | Client active, exact redirect, response_type=code, PKCE S256, scope hợp lệ. | AS xác thực/consent, phát một code cho transaction. |
| **Unknown client_id** | Client không đăng ký. | AS hiển thị lỗi an toàn, không redirect tới URI request. |
| **Disabled client** | Registration bị vô hiệu. | Không phát code, không redirect tới nơi chưa xác minh. |
| **Missing client_id** | Không xác định được client. | Không phát code; xử lý lỗi local an toàn. |
| **Wrong grant/response type** | Client code-only gửi response_type=token. | Từ chối, không phát Bearer AT trong URL. |
| **Unsupported response_type** | response_type bất kỳ. | Từ chối theo OAuth error policy. |
| **response_type pollution** | Có nhiều response_type trái nhau. | Strict parser/policy reject, không chọn phiên bản quyền cao. |
| **Registered redirect valid** | HTTPS callback chính xác của web client. | Có thể tiến hành nếu các check khác đạt. |
| **Missing redirect when required** | Client có nhiều registered URIs nhưng request không xác định được URI. | Reject theo OAuth/profile, không tự chọn tùy ý. |
| **Attacker redirect host** | redirect_uri=https://attacker.invalid. | Không phát/redirect code tới attacker. |
| **Redirect prefix attack** | dashboard.example.test.attacker.invalid. | Reject. |
| **Redirect userinfo confusion** | URI có @ và host attacker. | Reject URI ngoài registration. |
| **Redirect HTTP downgrade** | Web client registered HTTPS nhưng request HTTP. | Reject. |
| **Redirect extra path** | Callback path khác registered path. | Reject. |
| **Redirect query change** | Một query khác registered URI mà policy không cho. | Reject. |
| **Redirect encoded confusion** | Double encoding/mixed normalization. | Không bypass matching. |
| **Open redirect callback** | Registered endpoint tự forward code. | Security test phát hiện; client phải sửa. |
| **Unverified redirect on error** | Invalid redirect + invalid_scope. | AS không gửi error/code tới URI sai. |
| **Native loopback policy** | Native client loopback port thay đổi đúng RFC 8252. | Chấp nhận hoặc từ chối đúng native registration profile, không nhầm web rule. |
| **Native custom scheme collision** | Hai apps nhận cùng scheme. | Client/AS binding và PKCE bảo vệ; đánh giá platform risk. |
| **Missing PKCE** | Client yêu cầu PKCE nhưng không có challenge. | Reject, không downgrade. |
| **PKCE method unsupported** | code_challenge_method không thuộc policy. | Reject. |
| **PKCE plain downgrade** | Client cần S256 nhưng gửi plain. | Reject. |
| **Malformed challenge** | Challenge sai format/length. | Reject trước issuance. |
| **PKCE verifier wrong** | Token endpoint nhận verifier không khớp code challenge. | Reject, không cấp AT/RT. |
| **PKCE verifier from tab B** | Code tab A + verifier B. | Reject. |
| **PKCE verifier logged** | Client debug in verifier. | Secret scanning/log hygiene test fail. |
| **Code short lifetime** | Code hết hạn tại token endpoint. | Reject. |
| **Code used twice** | Redeem một code lần hai. | Chỉ lần đầu thành công, lần sau reject. |
| **Concurrent code redeem** | Hai requests cùng code/PKCE. | Exactly one successful redemption. |
| **Code wrong client** | Client B đổi code phát cho A. | Reject. |
| **Code wrong redirect** | Token request redirect khác code binding. | Reject theo profile. |
| **Code wrong AS** | Code issuer A gửi token endpoint B. | Reject; client tránh mix-up. |
| **Code unknown** | Code giả/ngẫu nhiên. | Reject, không tiết lộ code existence. |
| **Code too long** | Caller gửi code nhiều MB. | Size limit trước crypto/DB work. |
| **Code log leakage** | Authorization callback URL có code trong access log. | Test phát hiện và redact. |
| **Code cache stale** | AS replica đọc code ACTIVE sau khi bị consume. | Không phát thêm token; authoritative state. |
| **Lost token response** | Code consumed nhưng response mất. | Retry không phát token lần hai; recovery UX rõ. |
| **State matches** | Callback đúng state và session. | Có thể tiếp tục issuer/code checks. |
| **State missing** | Callback thiếu state khi client đã gửi. | Client reject. |
| **State mismatch** | Callback state của session khác. | Client reject, không token exchange. |
| **State replay** | Same callback state lần hai. | Client reject/atomic consume. |
| **State fixation** | Attacker ép state cố định. | Client sinh khó đoán, ràng session, reject. |
| **Multi-tab overwrite** | Tab B ghi đè verifier/state A. | Transaction storage tránh lỗi; test từng tab. |
| **Issuer mismatch** | RFC 9207 iss khác expected issuer. | Client reject trước token exchange. |
| **Two AS mix-up** | Callback AS-A được xử lý như AS-B. | Client không gửi code đến B, reject. |
| **Untrusted discovery** | Attacker đưa authorization_endpoint/token_endpoint. | Client chỉ dùng trusted metadata. |
| **Scope outside registration** | dashboard read-only xin refund. | AS không grant refund. |
| **Scope granted without consent** | User chưa cho phép sensitive scope. | AS không phát code grant vượt quyền. |
| **Consent denied** | User từ chối. | access_denied, không code. |
| **Consent hidden field altered** | Browser POST thêm scope=admin. | AS dùng trusted pending transaction; không cấp admin. |
| **Consent CSRF** | Third-party page ép user POST approve. | CSRF/transaction binding reject. |
| **Consent replay** | POST approve lặp cho transaction đã consumed. | Không phát hai codes/không mở rộng grant. |
| **Unknown consent transaction** | transaction_id không có. | Không grant, không leak user data. |
| **Cross-user consent** | Cookie user B approve tx của user A. | Reject. |
| **User authenticated but unauthorized** | User không được approve/refund dù login đúng. | AS không cấp sensitive grant. |
| **prompt=none no session** | OP không có login session. | Error theo OIDC profile, không bypass. |
| **prompt=none consent required** | Chưa có consent mà không tương tác. | Error consent_required/interaction_required theo profile. |
| **max_age too old** | Session lâu hơn max_age. | Reauthenticate hoặc fail theo OIDC policy. |
| **Fake MFA query** | mfa_passed=true từ client. | AS không tin, đánh giá auth context thật. |
| **OIDC nonce mismatch** | ID token nonce khác transaction. | RP reject. |
| **ID token used as AT** | Orders nhận OIDC ID token. | RS reject token type/audience. |
| **No OIDC openid** | Request không xin OIDC nhưng RP giả định ID token sẽ có. | Client không tự nhận profile không được xin/hỗ trợ. |
| **Wrong resource** | Client Orders xin payments resource. | AS không grant ngoài policy. |
| **Cross-resource scope** | Scope payments:refund cho resource Orders. | Reject theo mapping policy. |
| **Scope inflation on token exchange** | Code grant read, token endpoint request admin. | Không mint admin. |
| **PAR expired request_uri** | Client/browser dùng reference hết hạn. | Reject. |
| **PAR wrong client** | Client B dùng request_uri của A. | Reject client binding. |
| **PAR arbitrary URL** | request_uri=https://attacker.invalid/request. | AS không fetch untrusted URL. |
| **PAR parameters tampered** | Browser thêm redirect_uri/scope khác pushed request. | Không mở rộng/đổi trusted pushed request. |
| **JAR bad signature** | Request Object chữ ký sai. | Reject. |
| **JAR wrong aud** | Request Object dành cho AS khác. | Reject. |
| **JAR expired** | Request Object hết hạn. | Reject theo JAR profile. |
| **JAR untrusted key** | JWT header trỏ jku attacker. | AS không tin unregistered key. |
| **JAR admin scope despite valid signature** | Client ký object xin refund ngoài registration. | Không cấp refund. |
| **JAR parameter pollution** | request object scope=read, outer query scope=admin. | Xử lý precedence theo RFC/profile, không chấp nhận escalation. |
| **Response mode unsupported** | Client ép mode ngoài registration/profile. | Reject hoặc xử lý theo contract, không fallback nguy hiểm. |
| **form_post callback without state** | Browser POST code nhưng thiếu/mismatch state. | Client reject. |
| **Query log leak** | Proxy logging full callback query. | Redaction gate fail. |
| **Third-party script callback** | Script ngoài đọc code trước client xử lý. | CSP/architecture/security test chặn. |
| **AS session fixation** | User login trong attacker-fixed session. | Session ID rotation/CSRF/session policy. |
| **Cookie insecure** | AS session cookie không Secure trên production HTTPS. | Security test fail. |
| **Clickjacking consent UI** | Consent page bị iframe attacker. | Frame protections. |
| **Host header poisoning** | X-Forwarded-Host untrusted thay issuer/redirect. | Không ảnh hưởng trusted issuer/registered redirect. |
| **OAuth error leakage** | Invalid client nhận chi tiết token/other tenant grants. | Không leak; uniform sanitized error. |
| **Rate-limit abuse** | Nhiều authorization requests để tạo sessions/codes. | Bounded resources và monitoring, không DoS. |
| **Policy drift AS replicas** | A cho callback X, B reject. | Deployment kiểm consistent reviewed policy. |
| **Revoked grant still tokenizable** | User rút consent, code/token flow cũ. | AS policy chống phát token từ revoked grant theo lifecycle. |

### Mười phép thử tối thiểu cho CI

~~~text
1. Registered HTTPS redirect + code + PKCE S256 -> valid flow.
2. Unregistered redirect -> NO redirect to attacker, NO code.
3. Missing/invalid PKCE -> NO code/token according to client policy.
4. Callback missing/mismatched/replayed state -> client rejects.
5. Wrong authorization response issuer -> client rejects.
6. Code + wrong verifier/client/redirect -> token endpoint rejects.
7. Same code redeemed twice -> exactly one successful exchange.
8. Consent denied or scope outside grant -> NO elevated code/token.
9. Wrong resource/audience/ID-token-as-AT -> denied at AS/RS.
10. PAR/JAR tampering and no-trust references -> rejected.
~~~

**Không chỉ test HTTP 302 xuất hiện**: một 302 có thể chuyển code tới attacker. Phải kiểm **đích Location, transaction state, code one-time record, token claims và không có side effects trái policy**.

## 34. Checklist production cho authorization endpoint

1. **Issuer:** AS có issuer identifier ổn định, metadata/discovery được cấu hình và xác minh đúng?
2. **HTTPS:** Authorization và token endpoints dùng HTTPS production, không bị TLS downgrade?
3. **Trusted proxy:** Host/forwarded headers chỉ được tin từ proxy đã cấu hình?
4. **Client registry:** Chỉ registered active clients được tiến hành authorization?
5. **Client type:** Phân biệt public/confidential và authentication expectations?
6. **Grant types:** Client chỉ dùng response_type và grant types đã được đăng ký?
7. **Authorization Code:** Code flow là mặc định cho browser login theo current BCP?
8. **Implicit disabled:** Không phát Bearer AT trực tiếp qua authorization response khi không có profile được phê duyệt?
9. **Redirect validation:** Registered redirect URI matching theo chuẩn/profile, không prefix/suffix wildcard tùy tiện?
10. **Redirect error:** Invalid/untrusted redirect URI không bao giờ là nơi AS gửi error/code?
11. **Open redirect:** Client callback không chuyển code/state sang attacker host?
12. **Native redirects:** Loopback/custom URI rules dùng đúng RFC 8252 và platform policy?
13. **PKCE policy:** Authorization Code clients dùng PKCE; S256 được hỗ trợ/yêu cầu theo policy?
14. **PKCE binding:** Challenge/method được gắn với từng code, không lưu global theo client?
15. **Verifier secrecy:** code_verifier không xuất hiện trong authorization URL/logs?
16. **State:** Client tạo state khó đoán và bind với browser session/transaction?
17. **State consume:** Missing/mismatched/replayed state bị từ chối trước token exchange?
18. **Multi-tab:** State, PKCE, nonce và issuer không bị ghi đè giữa concurrent flows?
19. **Issuer binding:** Client biết expected AS cho từng transaction và chống mix-up?
20. **RFC 9207:** Khi response iss được dùng, client kiểm khớp expected issuer?
21. **Scope registration:** AS giới hạn requested scopes theo client, grant/consent và resource?
22. **Resource indicators:** AS kiểm resource requests đúng allowed audiences?
23. **Consent policy:** User approve chỉ trong phạm vi client/subject/resource đã được cho phép?
24. **Consent UX:** Màn hình hiển thị scopes nhạy cảm rõ, không che giấu quyền?
25. **Consent CSRF:** POST actions có CSRF và pending-transaction/session binding?
26. **Authentication:** AS không coi client query/header là chứng cứ đã login/MFA?
27. **Step-up:** Sensitive scopes có chính sách MFA, max_age/auth_time khi áp dụng?
28. **Prompt=none:** Không bypass login/consent khi yêu cầu không tương tác không thể đáp ứng?
29. **OIDC nonce:** RP/OP xử lý nonce theo đúng response type/transaction?
30. **ID token:** RP kiểm signature/iss/aud/nonce/time; RS không dùng ID token thay AT?
31. **Code entropy:** Authorization code được sinh an toàn, khó đoán?
32. **Code TTL:** Code có expiry ngắn và số lần đổi tối đa một?
33. **Code state:** Code client/redirect/PKCE/grant/scopes/resource context được lưu bền vững?
34. **Atomic consume:** Nhiều token requests không thể cùng redeem code thành công?
35. **Token endpoint:** Client auth, redirect_uri, PKCE và grant status được kiểm lại đúng?
36. **Token issuance:** AT scope/aud/TTL phản ánh authorized grant, không raw client input?
37. **JWT/opaque profile:** Token format và claims validation được hỗ trợ phù hợp AS/RS?
38. **Refresh token:** RT issuance/rotation/grant limits không tự phát ngoài authorization policy?
39. **PAR:** Nếu bật, request_uri do AS cấp, bound client, có expiry và không tự fetch untrusted URL?
40. **JAR:** Nếu bật, Request Object signature, aud, issuer, time và parameter precedence được kiểm?
41. **Response mode:** Chỉ cho modes được phép; callback parser strict?
42. **Browser front channel:** Không rò code/state qua history, referrer, analytics, scripts và logs?
43. **Cookie security:** AS session cookies Secure/HttpOnly/SameSite/Domain/Path phù hợp?
44. **Session fixation:** Có rotate session sau login/privilege changes khi phù hợp?
45. **Clickjacking/XSS:** CSP, frame-ancestors và output encoding bảo vệ login/consent?
46. **Rate limits:** Giới hạn login/authorization failures, code generation và session state?
47. **CSRF separation:** Client callback CSRF và AS login/consent CSRF đều có biện pháp đúng?
48. **Error handling:** OAuth/OIDC errors không gửi tới URI sai hoặc tiết lộ secrets?
49. **Audit:** Có correlation, client, issuer, scope/resource quyết định, không raw code/token?
50. **Monitoring:** Đo redirect rejects, PKCE failure, code replay, mix-up và consent anomalies?
51. **Policy drift:** Tất cả AS instances/regions dùng cùng client registration/security policy version?
52. **Strong code store:** Multi-region code one-time state có atomic/linearizable guarantee?
53. **Recovery:** Client xử lý response lost/code consumed và retry không bypass one-time?
54. **Revocation:** Consent/grant/AT/RT lifecycle có cơ chế rút quyền, SLO và RS enforcement?
55. **Incident plan:** Có runbook code leakage, redirect compromise, consent phishing và OAuth mix-up?
56. **Negative tests:** CI/pre-production có test redirect/PKCE/state/mix-up/consent/race?
57. **Change review:** Mọi mở rộng callback, scope, response_type, PAR/JAR policy đều được review?
58. **Dependency hygiene:** Security framework/JOSE/OAuth library được cập nhật và tested theo versions?
59. **Least privilege:** Client registration, scopes, resource và user authority không thừa?
60. **End-to-end validation:** Sau authorization, RS vẫn kiểm issuer/aud/exp/scope/tenant/object-level permission?

### Trước khi mở một client mới

Một reviewer nên hỏi:

~~~text
Who owns the OAuth client and where does it run?
Is it public or confidential?
Which response_type and grant types are really needed?
Which exact redirect URIs are trusted?
Does it use Authorization Code with PKCE S256?
How is state and expected issuer bound to browser session?
What scopes and resources may it request?
Does OIDC nonce or step-up authentication apply?
What data is shown on consent screen?
How are code records stored and atomically redeemed?
How are tokens protected after the token exchange?
How does the system revoke an accidental overgrant?
Which negative tests demonstrate no redirect/code/permission bypass?
~~~

Không nên phê duyệt client chỉ vì “đăng nhập chạy được” nếu chưa chứng minh **code không đi lạc, token không bị đổi sai client và grant không bị mở quá scope**.

## 35. Bài tập vận dụng

### Bài tập 1 — Phân biệt authorization endpoint với token endpoint

Client gửi refresh token vào URL /oauth2/authorize và mong nhận AT.

**Câu hỏi:** Cần sửa ở đâu?

**Phân tích:** Refresh token grant thuộc **token endpoint**, không phải browser authorization endpoint. Authorization endpoint xử lý user-agent authorization transaction, login/consent và code response theo Authorization Code Flow.

### Bài tập 2 — Redirect URI có prefix giống host thật

Registered callback:

~~~text
https://dashboard.example.test/oauth/callback
~~~

Attacker đặt:

~~~text
https://dashboard.example.test.attacker.invalid/oauth/callback
~~~

AS đang dùng startsWith để kiểm.

**Câu hỏi:** Vì sao nguy hiểm?

**Phân tích:** Prefix giống không có nghĩa host trùng. AS có thể chuyển code tới attacker. Dùng trusted registered URI matching theo profile, không prefix hoặc wildcard lỏng. **Không redirect lỗi tới URI chưa được xác minh**.

### Bài tập 3 — Hai tabs dùng một verifier

Tab A khởi tạo state=A, verifier=VA. Tab B khởi tạo state=B, verifier=VB rồi ghi đè session.lastVerifier. Callback A tới trước.

**Câu hỏi:** Kết quả có thể xảy ra và cách sửa?

**Phân tích:** Client có thể gửi verifier VB khi đổi code của A, gây PKCE mismatch; fallback xử lý sai có thể tạo code injection/session confusion. Dùng pending transaction store keyed by **state + browser session**, với verifier/issuer/nonce riêng cho từng flow; consume state một lần.

### Bài tập 4 — User đăng nhập thành công nhưng từ chối consent

User đã MFA, nhưng bấm Deny khi app xin orders:read.

**Câu hỏi:** AS có được phát code vì user đã xác thực không?

**Phân tích:** Không. **Authentication khác authorization**. Consent/grant từ chối phải được xử lý theo error response an toàn về registered redirect URI khi hợp lệ, không phát code cho quyền bị từ chối.

### Bài tập 5 — Client xin scope ngoài registration

Client dashboard-web chỉ được orders:read nhưng gửi scope=orders:read orders:refund. User vẫn đồng ý trên consent UI.

**Câu hỏi:** AS nên cấp gì?

**Phân tích:** AS không được cấp orders:refund chỉ vì request/user đồng ý. Tùy policy, AS reject hoặc cấp subset authorized; code/token không được chứa quyền vượt client/resource/user policy. Consent không thay trần quyền registration.

### Bài tập 6 — Code đúng verifier nhưng redeem hai lần

Client redeem CODE1 với verifier V1 thành công. Response mạng bị mất. Client retry CODE1 với cùng V1.

**Câu hỏi:** Có được phát AT lần hai không?

**Phân tích:** Không. PKCE chứng minh binding, nhưng **authorization code phải one-time**. Token endpoint từ chối code đã consumed, client dùng recovery/new authorization flow theo hợp đồng; không tạo hai successors.

### Bài tập 7 — Multi-AS mix-up

Client lưu state nhưng không lưu expected issuer. Callback code của AS-A được gửi tới token endpoint AS-B.

**Câu hỏi:** Kiểm gì để ngăn?

**Phân tích:** Lưu expected issuer trong transaction, dùng trusted metadata token endpoint, ràng state/redirect/AS và kiểm **RFC 9207 iss** khi extension có mặt, hoặc biện pháp mix-up phù hợp. Không để callback tự quyết định issuer từ tham số bất kỳ.

### Bài tập 8 — OIDC nonce có vai trò gì?

RP gửi scope=openid, nonce=N1. Sau token exchange, ID token có nonce=N2 nhưng signature/iss/aud/exp đều đúng.

**Câu hỏi:** Có tạo session cho user không?

**Phân tích:** Nếu RP gửi nonce và profile yêu cầu đối chiếu, **không**. Nonce mismatch cho thấy ID token không thuộc authentication transaction mong đợi. Kiểm nonce sau ID token signature/claims validation, không thay nonce bằng OAuth state.

### Bài tập 9 — PAR request_uri bị thay

Client push authorization request scope=orders:read đến PAR endpoint và nhận request_uri R1. Browser sửa authorization URL thành request_uri=https://attacker.invalid/request.

**Câu hỏi:** AS có nên fetch URL đó?

**Phân tích:** Không. AS chỉ resolve **trusted AS-issued request_uri** có client binding, TTL và policy theo RFC 9126. Không fetch arbitrary URL hay dùng parameters ngoài pushed request để tăng scope.

### Bài tập 10 — JAR ký đúng nhưng xin scope admin

Client ký JWT Request Object yêu cầu payments:refund. Registration chỉ cho reports:read.

**Câu hỏi:** Chữ ký JAR có đủ để AS cấp refund không?

**Phân tích:** Không. Chữ ký xác thực Request Object theo profile, **không tự cấp quyền**. AS vẫn kiểm client allowed scopes/resources, user/grant/consent và risk policy.

### Bài tập 11 — OIDC prompt=none chưa có session

Browser không có OP login session, client gửi prompt=none. AS dự định tự login anonymous rồi phát code để giữ UX.

**Câu hỏi:** Vì sao sai?

**Phân tích:** prompt=none yêu cầu xử lý không có tương tác; khi không thể đáp ứng login/consent, OP phải trả lỗi phù hợp profile. **Không tự tạo authentication** hoặc bỏ consent.

### Bài tập 12 — Backend nhận access token thay vì code

Một SPA gửi response_type=token, AS tự phát access token qua browser vì library còn hỗ trợ implicit flow.

**Câu hỏi:** Tại sao nên thay đổi?

**Phân tích:** Token trong front channel tăng exposure. Theo OAuth Security BCP, nên dùng **Authorization Code + PKCE** với client/server token handling phù hợp; disable unsupported response types và bảo vệ code/state/redirect URI.

### Bài tập 13 — Consent CSRF

Attacker ép browser đã login AS gửi POST /consent với transaction_id của một grant quyền cao, approved=true và scope=admin.

**Câu hỏi:** Kiểm gì?

**Phân tích:** AS phải có CSRF defense, user-session binding, pending transaction ownership, scopes từ trusted server-side state và consent decision trong giới hạn policy. Một hidden form field không được phép tạo grant.

### Bài tập 14 — Resource Server tưởng authorization code là AT

Client gửi code trong Authorization: Bearer đến Orders API. Code còn hạn và đúng client.

**Câu hỏi:** Orders có thể chấp nhận không?

**Phân tích:** Không. Authorization code chỉ redeem tại token endpoint và không có semantics API access token. RS phải kiểm token type/profile, issuer, aud, exp/scope và resource permissions.

### Bài tập 15 — Redirect callback đã xác thực nhưng account mất quyền

AS đã phát code cho orders:approve. Trước khi client redeem code, admin rút quyền approve.

**Câu hỏi:** Nên xử lý thế nào?

**Phân tích:** AS cần nhất quán với **grant/current authorization policy** tại redemption/issuance, có thể từ chối/narrow theo contract khi quyền bị rút; nếu AT đã phát trước đó thì cần revocation/online RS permission check tùy SLA. **Chỉ việc đã có code không cho phép bypass policy thay đổi trong high-risk workflow**.

### Cây quyết định kiểm authorization request

~~~mermaid
flowchart TD
    A["Client khởi tạo authorization request"] --> B{"client_id active và redirect_uri trusted?"}
    B -->|Không| X["Local AS error; no untrusted redirect"]
    B -->|Có| C{"response_type, PKCE, scope/resource hợp lệ?"}
    C -->|Không| Y["OAuth error tới verified redirect nếu phù hợp"]
    C -->|Có| D["Tạo pending authorization transaction"]
    D --> E{"User authentication đáp ứng policy?"}
    E -->|Không| F["Login/step-up hoặc OIDC error"]
    E -->|Có| G{"Consent + user/client grant được phép?"}
    G -->|Không| H["access_denied theo policy"]
    G -->|Có| I["Persist one-time code với client/redirect/PKCE/grant"]
    I --> J["Redirect code + state (+iss khi dùng)"]
    J --> K["Client kiểm state/issuer và đổi code ở token endpoint"]
    K --> L{"Code binding/PKCE/one-time đạt?"}
    L -->|Không| Z["invalid_grant; no token"]
    L -->|Có| M["AS cấp token đúng scopes/audience/profile"]
~~~

## Kết luận

**Authorization endpoint là ranh giới nơi Authorization Server tiếp nhận một yêu cầu cấp phép từ OAuth client qua browser, xác thực resource owner khi cần, đánh giá consent và policy, rồi tạo authorization code ngắn hạn cho một transaction cụ thể.** Trong Authorization Code Flow hiện đại, endpoint này **không phải** nơi gửi Bearer access token trực tiếp qua URL để client sử dụng tại Resource Server.

Các nguyên tắc cần ghi nhớ:

- **Authorization endpoint và token endpoint có nhiệm vụ khác nhau:** authorization endpoint xử lý yêu cầu qua user-agent và phát code; token endpoint kiểm client, code binding và PKCE để đổi code lấy token.
- **Client request không tự là quyền được cấp:** response_type, redirect_uri, scope, resource, prompt và các tham số khác phải được xác minh với client registration, grant, authenticated user và AS policy.
- **Redirect URI là tài sản bảo mật:** kiểm đích đã đăng ký theo profile, chống wildcard/prefix/open redirect; **không redirect code hoặc lỗi đến URI chưa xác minh**.
- **state, PKCE, issuer và nonce bảo vệ các ranh giới khác nhau:** state ràng callback với authorization transaction, PKCE ràng code với verifier, issuer binding chống mix-up, OIDC nonce ràng authentication response khi áp dụng.
- **Authentication không tự bằng consent:** user đã login hoặc đã MFA chưa đồng nghĩa client được cấp mọi scope/resource.
- **Authorization code phải ngắn hạn và one-time:** gắn với client, redirect URI, PKCE challenge, authorized grant và issuer; token endpoint phải consume nguyên tử.
- **Browser front channel có nguy cơ lộ thông tin:** bảo vệ callback, cookies, referrer, logs, state, code, query/fragment và third-party scripts.
- **OIDC là lớp authentication riêng:** ID token cần được RP kiểm theo profile; nó không thay access token dành cho Orders API hoặc resource permission.
- **PAR/JAR có thể tăng tính toàn vẹn và bảo vệ authorization request**, nhưng không thay login, consent, redirect URI checks hoặc allowed scope/resource policies.
- **Framework configuration chỉ là một phần của kiến trúc:** production cần code/grant persistence, multi-replica consistency, consent CSRF protection, token lifecycle, revocation, audit và security testing.
- **Resource Server vẫn có trách nhiệm riêng**: sau khi AT được phát, RS phải xác minh issuer, audience, token type, thời hạn, scope, tenant/ownership và quyền nghiệp vụ.

Một authorization flow có thể được xem là an toàn khi **người dùng xác thực đúng, client đúng, callback đúng, consent đúng, code chỉ được đổi một lần, token được cấp đúng scope/audience, và Resource Server không cấp quyền vượt authorized grant**. Những kiểm tra đó cần hoạt động thống nhất từ browser front channel đến token back channel và API authorization.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization endpoint, authorization code, redirect URI, scope, errors và token endpoint.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token handling và trách nhiệm của Resource Server.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): code_verifier, S256 challenge và code interception defense.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): external user-agent, native loopback/custom redirect profiles.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer, authorization_endpoint, token_endpoint và trusted discovery.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): intended resource và audience restriction.
- [RFC 9101 — The OAuth 2.0 Authorization Framework: JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101): signed Request Objects.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests (PAR)](https://www.rfc-editor.org/rfc/rfc9126): pushed request_uri và request binding.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): authorization response iss và chống mix-up.
- [RFC 9396 — OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396): authorization_details cho quyền có cấu trúc.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token claims, audience, issuer, scope và token type.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): redirect/code/PKCE/implicit/mix-up security guidance.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): rút token/grant sau authorization.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): RS kiểm token metadata/status theo AS policy.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): bảo vệ sender-bound access tokens ở token/API requests khi áp dụng.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): Authorization Code Flow, ID token validation, nonce, prompt, max_age và authentication context.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OP metadata và trusted endpoint discovery.
- [OAuth 2.0 Multiple Response Type Encoding Practices](https://openid.net/specs/oauth-v2-multiple-response-types-1_0.html): response modes và OIDC response types.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): hardening OAuth clients/AS.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login/session protection.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF protection trên login/consent forms.
- [OWASP Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): redirect security.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation và cookie protection.








