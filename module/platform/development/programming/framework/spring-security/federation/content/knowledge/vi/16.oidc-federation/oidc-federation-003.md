# Authorization Code, state, nonce và PKCE ở ranh giới ứng dụng OIDC có môi giới danh tính

## 1. Bối cảnh: SAML ở thượng nguồn, OIDC ở cửa ứng dụng

Một ứng dụng Spring Boot trước đây đăng nhập trực tiếp bằng SAML 2.0. Khi bổ sung **identity broker** (bộ môi giới danh tính), kiến trúc có thể thay đổi:

- Ứng dụng Spring Boot là **OpenID Connect Relying Party (OIDC RP)** đồng thời là **OAuth 2.0 client**.
- Bộ môi giới là **OIDC OpenID Provider (OP)** và Authorization Server (AS) đối với ứng dụng.
- Bộ môi giới có thể đóng vai trò **SAML Service Provider (SP)** đối với một **SAML Identity Provider (IdP)** ở thượng nguồn.
- Người dùng đi qua trình duyệt, nhưng các kiểm tra `state`, `nonce`, `PKCE` và ID Token thuộc **giao dịch OIDC giữa ứng dụng và broker**, không phải tự động được mang sang giao dịch SAML.

Bài học thuộc **Spring Security - federation → OIDC và môi giới**, tập trung vào **Authorization Code, state, nonce và PKCE ở ranh giới ứng dụng**. Đây không phải bài xây một Authorization Server hoặc thay mọi giao thức federation thành OIDC.

### Kết quả học tập

Sau bài, bạn có thể:

1. Mô tả **Authorization Code Flow** của OIDC, phân biệt front-channel browser với back-channel token exchange.
2. Giải thích đúng bốn dữ liệu: `authorization code`, `state`, `nonce`, `code_verifier/code_challenge`.
3. Biết các kiểm tra bảo mật thực hiện ở **client, broker, upstream SAML IdP** và **resource server**.
4. Phân biệt trách nhiệm của **state** chống CSRF/login response injection, **nonce** gắn ID Token với request, và **PKCE** gắn token exchange với request ban đầu.
5. Cấu hình Spring Security Servlet `oauth2Login()`, client registration OIDC, URI callback và PKCE khi cần.
6. Giải thích vì sao không dùng chung OIDC `state` với SAML `RelayState`, không dùng ID Token của broker như SAML Assertion và không tin issuer/subject do callback tự khai.
7. Kiểm thử `state mismatch`, `nonce mismatch`, `invalid_grant`, thiếu session và IdP/Broker mix-up.
8. Xử lý return URL/deep link an toàn, session cookie, nhiều tab, proxy, secret, JWKS rotation, multi-tenant và mất kết nối.
9. Dùng Java 17 viết chương trình **chạy độc lập** để tính PKCE S256 và so chứng cứ, không nhầm mã học tập với một OIDC client production.

Ví dụ hướng đến **Java 17+, Spring Boot 3.x, Spring Security 6.5+ Servlet/MVC**. Một số API đã có ở Spring Security cũ hơn; những API `ClientRegistration.ClientSettings` được ghi rõ phiên bản. Đối với Spring Security 7.x, đối chiếu tài liệu đúng release. Các URL thuộc `example.org` chỉ mô phỏng, không phải nhà cung cấp có thể đăng nhập thật.

## 2. Sơ đồ hai ranh giới tin cậy

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant APP as Spring Boot OIDC client
    participant BROKER as OIDC broker OP/AS
    participant IDP as Upstream SAML IdP
    U->>APP: GET /reports/42 khi chưa đăng nhập
    APP->>APP: Lưu SavedRequest + OIDC transaction
    APP-->>U: 302 /authorize của broker (state, nonce, PKCE challenge)
    U->>BROKER: GET authorization endpoint
    opt Broker cần đăng nhập qua upstream SAML
        BROKER->>BROKER: Tạo AuthnRequest, SAML RelayState riêng
        BROKER-->>U: Chuyển tới SAML IdP
        U->>IDP: SAML AuthnRequest
        IDP-->>U: Form POST SAMLResponse
        U->>BROKER: POST về SAML ACS của broker
        BROKER->>BROKER: Kiểm tra SAML Signature/Issuer/Audience/Time
    end
    BROKER->>BROKER: Cấp authorization code cho client OIDC
    BROKER-->>U: 302 về APP callback với code + state
    U->>APP: GET /login/oauth2/code/broker?code=...&state=...
    APP->>APP: Khôi phục OIDC transaction và so state
    APP->>BROKER: POST token endpoint: code + code_verifier + client auth
    BROKER->>BROKER: Xác minh code, redirect_uri, client, PKCE
    BROKER-->>APP: Token response: ID Token + access token
    APP->>APP: Validate ID Token signature, iss, aud, exp, nonce...
    APP->>APP: Tạo SecurityContext/HTTP session của ứng dụng
    APP-->>U: Redirect về /reports/42 nếu còn quyền
~~~

**Có hai hợp đồng độc lập:**

- **Upstream SAML:** Broker tin IdP theo SAML metadata, ký/xác minh SAML XML, lưu `AuthnRequest ID` và `RelayState` riêng.
- **Downstream OIDC:** Ứng dụng tin broker theo OIDC issuer/client registration/JWKS, quản lý `state`, `nonce`, `PKCE` và kiểm tra ID Token.

Broker **không thể tự động chuyển một chuỗi trạng thái SAML thành bằng chứng OIDC**. Nó phải xác minh SAML rồi phát ID Token **với issuer chính là broker**, subject/claims theo hợp đồng bảo mật của broker.

## 3. Bốn giá trị dễ bị nhầm

| Dữ liệu | Xuất hiện ở đâu? | Bên giữ/kiểm tra chính | Mục đích |
| --- | --- | --- | --- |
| **Authorization Code** | Callback từ Authorization Endpoint → client; sau đó gửi token endpoint | Broker phát và kiểm tra, client chỉ sử dụng một lần | Đại diện một authorization grant ngắn hạn; đổi lấy tokens |
| **state** | Authorization Request qua browser và authorization callback | Client tạo, lưu theo phiên/giao dịch; client so lại | Tương quan callback; chống CSRF/login code injection và gắn browser flow |
| **nonce** | OIDC Authentication Request và claim `nonce` trong **ID Token** nếu client gửi | Client tạo/lưu; broker phản chiếu vào ID Token; client so lại sau verify | Gắn ID Token với transaction, giảm replay/substitution |
| **code_verifier** | Chỉ client và **back-channel POST token endpoint** | Client tạo/lưu; broker kiểm tra thông qua challenge đã gắn với code | Bằng chứng người đổi code chính là bên đã mở giao dịch |
| **code_challenge** | Authorization Request tới broker | Broker lưu cùng code, client tạo từ verifier | Bản công khai một chiều của verifier với PKCE S256 |
| **SAML RelayState** | SAML Redirect/POST giữa broker và upstream IdP | Broker/SP phát và IdP phản hồi theo SAML binding | Ngữ cảnh của **giao dịch SAML khác**, không phải OIDC state |

**Không viết “state = nonce = RelayState = PKCE”**. Các chuỗi đôi khi cùng được tạo bằng `SecureRandom`, nhưng mỗi chuỗi có **điểm kiểm tra và mục đích độc lập**. Việc tái sử dụng cùng giá trị dễ gây liên kết nhầm, làm giảm khả năng tách giao dịch, hỗ trợ replay và làm phức tạp logging.

## 4. Authorization Code: front-channel chỉ nhận code, back-channel đổi token

### 4.1 Authorization Request

Client khởi tạo bằng một redirect HTTPS tới authorization endpoint broker:

~~~http
GET /authorize?response_type=code
  &client_id=portal-client
  &redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fbroker
  &scope=openid%20profile
  &state=OPAQUE_STATE
  &nonce=OPAQUE_NONCE
  &code_challenge=S256_BASE64URL_VALUE
  &code_challenge_method=S256 HTTP/1.1
Host: broker.example.org
~~~

Đây là **minh họa query đã xuống dòng để dễ đọc**, không phải cú pháp một HTTP request line gửi trực tiếp. `OPAQUE_STATE`, `OPAQUE_NONCE` và `S256_BASE64URL_VALUE` là tên mô tả; giá trị thật phải do client sinh mới mỗi transaction.

Các tham số:

- `response_type=code` chọn Authorization Code.
- `client_id` định danh OIDC client đã đăng ký tại broker.
- `redirect_uri` phải trùng **redirect URI đã đăng ký** theo quy tắc kiểm tra của AS; không phải URL tùy ý do browser chọn.
- `scope=openid` biến một OAuth request thành yêu cầu **OpenID Connect authentication**; `profile` là scope bổ sung tùy policy.
- `state` là giá trị opaque gắn với browser login transaction.
- `nonce` gắn ID Token với request nếu client gửi.
- `code_challenge + code_challenge_method=S256` kích hoạt PKCE.

**Quan trọng:** `client_secret` **không** nằm trong URL này. Code verifier cũng **không được gửi** tới browser Authorization Endpoint; nó phải được giữ cho token exchange.

### 4.2 Callback về client

Sau khi user xác thực/ủy quyền theo chính sách, broker redirect:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.org/login/oauth2/code/broker?code=CODE_VALUE&state=OPAQUE_STATE
~~~

Browser đi tới callback. Ứng dụng cần **khôi phục authorization request đã lưu** và kiểm tra `state` trả lại có đúng phiên/giao dịch vừa phát hay không, cũng như áp dụng kiểm tra issuer/AS mix-up phù hợp.

Callback này chỉ trao **authorization code**, **chưa phải bằng chứng user là ai**. Không làm:

~~~text
GET callback có code -> set session user=admin
~~~

Trước khi tạo SecurityContext, phải hoàn thành token exchange, ID Token verification và business account policy.

### 4.3 Token Request server-to-server

Một client backend có thể POST:

~~~http
POST /token HTTP/1.1
Host: broker.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials-encoded>

grant_type=authorization_code&
code=CODE_VALUE&
redirect_uri=https%3A%2F%2Fapp.example.org%2Flogin%2Foauth2%2Fcode%2Fbroker&
code_verifier=PRIVATE_VERIFIER_VALUE
~~~

Dấu `<client-credentials-encoded>` và các giá trị là mô phỏng, không chứa credential thật. Một số client/AS dùng `private_key_jwt`, mTLS hoặc `client_secret_post` theo đăng ký; không tự đổi phương thức client authentication để chữa lỗi.

**Broker kiểm tra**:
- Code được phát cho đúng `client_id` và chưa được đổi;
- Code còn hạn và chưa bị replay;
- `redirect_uri` khớp authorization transaction (nếu được gửi/cần thiết);
- Client authentication phù hợp loại client;
- PKCE verifier đúng challenge đã gắn vào code;
- Chính sách AS đối với consent/redirect/subject.

Code thường **ngắn hạn và chỉ dùng một lần**. Nó không phải ID Token, access token hay refresh token. Nếu token exchange không thành công, không dùng code đã thất bại để “tự tạo session”.

### 4.4 Token Response và tạo phiên

Broker có thể trả `id_token` và `access_token` cho OIDC Code Flow. App cần:

1. Xác minh ID Token theo **issuer, signature/JWKS, allowed algorithms, audience/client ID, thời gian** và các claim OIDC khác.
2. Nếu đã gửi nonce, so với `nonce` trong ID Token theo quy tắc spec.
3. Nếu ID Token có nhiều audience, kiểm tra `azp` theo profile/spec.
4. Dùng **`iss + sub`** làm khóa danh tính logic; không chỉ email.
5. Áp dụng provisioning/tenant/account status và authorization local.
6. Tạo `Authentication` trong session SP chỉ sau khi tất cả kiểm tra đạt.

**Access token** dùng để gọi resource server theo scope/audience đã cấp; **ID Token** dùng để chứng minh sự kiện xác thực **cho client**. Không gửi ID Token làm Bearer cho mọi API chỉ vì nó là JWT.

## 5. state: chống CSRF tại điểm callback

OAuth/OIDC authorization callback là một **điểm nhập dữ liệu từ trình duyệt**. Kẻ xấu có thể thử gửi code từ **giao dịch của chính kẻ xấu** đến browser nạn nhân, khiến app nhầm danh tính (login CSRF/code injection). `state` chống điều này bằng cách buộc callback thuộc đúng login transaction được client **khởi tạo từ browser đó**.

Quy trình:

1. Client sinh `state` bằng CSPRNG đủ khó đoán, mới cho mỗi lần bắt đầu login.
2. Client lưu nó trong `AuthorizationRequestRepository` theo browser/session hoặc một state store khác có **browser binding và TTL**.
3. Client đưa cùng state vào authorization request đến broker.
4. Broker gửi nguyên giá trị đó lại khi redirect callback.
5. Client khôi phục transaction từ state/session **đã được lưu trước**, kiểm tra đúng và chỉ tiếp tục token exchange khi phù hợp.
6. Dùng xong thì consume/remove theo policy; không để state dùng lại vô hạn.

**Ranh giới:** `state` là giá trị do **client** tạo và kiểm tra. Broker **phản chiếu** nó nhưng không nên coi nó là bằng chứng quyền hoặc đích URL được phép. Mọi giá trị lấy từ callback vẫn là input chưa tin cho đến khi client đối chiếu transaction của chính mình.

### state có nên chứa return URL?

Không nên đưa nguyên `https://external.example/redirect` vào state rồi redirect theo giá trị callback. Thay vào đó:
- Sinh **opaque state**;
- Lưu server-side `state → {browser/session, registration, originalLocalPath, createdAt, used=false}` (hoặc dùng Spring `SavedRequest` riêng);
- Sau login, chỉ chuyển về **local path được phép**, có validation host/scheme;
- Dùng state **một lần** và có TTL;
- Không biến `state` thành nơi lưu secrets hoặc thông tin cá nhân.

Với Spring Security Servlet, `HttpSessionOAuth2AuthorizationRequestRepository` mặc định lưu `OAuth2AuthorizationRequest` từ lúc gửi request tới callback. Nó phục vụ correlation. `RequestCache/SavedRequest` lại giúp khôi phục **HTTP URL ban đầu**, hai đối tượng không đồng nhất.

### state không tự đủ nếu không gắn browser

Một state nằm trong cache toàn cục mà **bất kỳ browser nào cũng có thể gửi** có thể mở ra login CSRF/session swapping nếu không có browser binding và các kiểm tra khác. **Random không đồng nghĩa binding**. Khi chuyển từ HttpSession sang Redis/custom state repository, giữ:
- Gắn với phiên/user-agent đã khởi tạo hoặc biện pháp chống CSRF tương đương;
- TTL ngắn và one-time consume nguyên tử;
- Ràng buộc đúng client registration/issuer;
- Chống collision/race trong multi-tab;
- Không gửi state trong telemetry public.

## 6. nonce: gắn ID Token với lần xác thực

`nonce` là một tham số OIDC Authentication Request. Nếu client gửi một nonce, OP phải đưa giá trị đó vào claim `nonce` của **ID Token**; client phải so khớp với giá trị đã lưu cho transaction. Giá trị nonce cần có entropy đủ lớn, không đoán được.

Ví dụ request:

~~~text
GET https://broker.example.org/authorize
  ?client_id=portal-client
  &response_type=code
  &scope=openid
  &nonce=RANDOM_NONCE_FOR_THIS_LOGIN
~~~

ID Token sau khi token exchange, nội dung claims **chỉ minh họa sau khi đã xác minh chữ ký**:

~~~json
{
  "iss": "https://broker.example.org",
  "sub": "pairwise-user-42",
  "aud": "portal-client",
  "exp": 1794001200,
  "iat": 1794000900,
  "nonce": "RANDOM_NONCE_FOR_THIS_LOGIN"
}
~~~

Mốc `exp/iat` mang tính ví dụ; không dùng JSON này làm ID Token thực tế, vì nó không có JWT header/signature. Kiểm tra nonce **chỉ có ý nghĩa bên trong ID Token đã được xác minh**, không phải một query parameter mà browser có thể tự cung cấp rồi coi là hợp lệ.

### Nonce có bắt buộc không?

- Trong **OIDC Authorization Code Flow thuần**, tham số `nonce` là **optional theo OIDC Core**. Nếu gửi thì phải xử lý/đối chiếu đúng như spec.
- Trong các response type khác như Implicit/Hybrid, OIDC đặt yêu cầu nonce khác; đừng bê logic của Code Flow sang mọi response type.
- Trong thiết kế bảo mật hiện đại, nonce được dùng khi phù hợp để ràng buộc ID Token/giảm replay và hỗ trợ cấu trúc chống code injection theo RFC 9700. Tuy nhiên **nonce không tự thay hoàn toàn PKCE hoặc state** trong mọi threat model.
- Nếu thư viện Spring Security dùng cơ chế nonce riêng, **đừng tự đặt nonce cố định, đừng sửa/loại nonce trong custom AuthorizationRequestResolver mà bỏ kiểm tra ở validator**.

### nonce khác state

`state` được trả trong **authorization response (callback)** và client so với transaction. `nonce` được trả trong **ID Token claim** và client kiểm tra sau khi xác minh ID Token. Khi IdP/broker không trả ID Token, OAuth 2.0 thuần không có nghĩa nonce hoạt động như ID Token binding.

### nonce không chứng minh MFA

Một nonce khớp chỉ cho thấy ID Token liên hệ với request. Nó **không** tự nói người dùng có MFA hay không, xác thực mới hay không, hoặc đủ quyền thao tác hay không. Với yêu cầu step-up, xem `auth_time`, `acr`, `amr` và IdP policy theo hợp đồng; kiểm tra issuer, audience và chữ ký như thường.

## 7. PKCE: chống sử dụng authorization code bị chặn/tiêm

**Proof Key for Code Exchange (PKCE)** được định nghĩa ở RFC 7636 và được củng cố trong OAuth 2.0 Security Best Current Practice RFC 9700.

### 7.1 Cách tạo code_verifier

Cho mỗi authorization request, client sinh một chuỗi ngẫu nhiên có entropy cao:

- `code_verifier`: độ dài **43–128 ký tự ASCII** thuộc bộ unreserved `A-Z a-z 0-9 - . _ ~`.
- Khuyến nghị thực tế: sinh **32 byte SecureRandom**, Base64url không padding thành **43 ký tự ASCII**.
- Không đặt verifier trong authorization URL, browser local storage công khai hoặc log. Nó cần tồn tại cho **token exchange** của chính transaction đó.

### 7.2 Sinh code_challenge S256

~~~text
code_challenge = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

`code_challenge` có thể xuất hiện trong Authorization Request; nó không cho phép tính ngược verifier khả thi khi verifier đủ entropy. Với S256, client phải giữ verifier bí mật trước broker, rồi chỉ gửi verifier trong token request.

### 7.3 Broker kiểm tra verifier

Broker ghi lại challenge gắn với authorization code. Khi nhận POST token endpoint có verifier, broker tính lại SHA-256/Base64url và so với challenge. Nếu không khớp, **từ chối token exchange** (thường báo `invalid_grant` hoặc lỗi thích hợp) và không phát tokens.

**PKCE không thể bị “tự kiểm tra” bởi client rồi bỏ qua server enforcement.** Authorization Server/broker phải thực sự buộc token exchange đúng verifier; một AS bỏ qua PKCE sẽ làm mất mục tiêu bảo vệ.

### 7.4 Chọn S256, không hạ xuống plain

`plain` có nghĩa challenge chính là verifier; điều đó có thể làm lộ verifier qua authorization request, giảm hiệu quả trong threat model có thể quan sát URL. Với Java/Spring hiện đại, **dùng S256**. RFC 9700 yêu cầu AS hỗ trợ PKCE; client nên chọn cơ chế không lộ verifier và không tự downgrade.

### 7.5 Public client và confidential client

- **Public client:** SPA/chương trình native không bảo vệ được client secret. Theo RFC 9700, **phải dùng PKCE**.
- **Confidential client:** ứng dụng server-side có thể giữ secret/private key an toàn. RFC 9700 **khuyến nghị PKCE** để chống code injection/misuse; client authentication và PKCE **bổ sung nhau**.
- **BFF (Backend for Frontend):** browser giữ cookie phiên còn backend làm OAuth/OIDC client và giữ tokens/secret; vẫn nên áp dụng PKCE cho Code Flow nếu supported/required.
- **Không đưa `client_secret` của confidential client vào JavaScript bundle hoặc URL**. Nếu secret đã bị nhúng vào browser, coi client là public về khả năng giữ bí mật và điều chỉnh kiến trúc.

### 7.6 PKCE không thay thế các kiểm tra còn lại

PKCE không xác minh:
- ID Token signature, `iss`, `aud`, `exp`, `nonce`;
- Quyền vào tài nguyên;
- Redirect URI policy;
- Tính hợp lệ của upstream SAML Assertion;
- Identity mapping giữa broker và ứng dụng.

Một app có PKCE tốt vẫn có thể bị login mix-up hoặc chấp nhận ID Token của issuer sai nếu bỏ những kiểm tra đó.

## 8. Bảng “ai kiểm tra điều gì” tại ranh giới

| Kiểm tra | App OIDC client | Broker OIDC OP/AS | Upstream SAML IdP |
| --- | --- | --- | --- |
| Tạo `state` của app transaction | **Có** | Echo state trong callback | Không liên quan trực tiếp |
| So callback `state` với request của browser | **Có** | Không thay client | Không |
| Tạo `nonce` app-side | **Có** | Echo trong ID Token | Không |
| So nonce trong ID Token đã xác minh | **Có** | Phát ID Token đúng request | Không |
| Tạo `PKCE code_verifier/challenge` | **Có** | Lưu challenge theo code | Không |
| Kiểm tra code_verifier tại token endpoint | Không thay AS; chỉ gửi verifier | **Có** | Không |
| Cấp authorization code | Không | **Có** | Không |
| Kiểm tra ID Token JWS/JWKS/issuer/audience | **Có** | Broker ký tokens | Không |
| Kiểm tra SAMLResponse XML Signature/issuer/audience | Không nếu chỉ là OIDC client | **Có**, khi đóng vai SP | IdP ký assertion |
| Quản lý upstream `RelayState/AuthnRequest ID` | Không | **Có** | Echo/kiểm tra theo SAML |
| Cấp quyền ứng dụng theo account/tenant hiện hành | **Có** | Có thể cấp claim nhưng không thay business policy | Không phải SP authorization |
| Quản lý SP HTTP session của app | **Có** | Không sở hữu | Không sở hữu |

Điểm dễ sai khi broker chuyển giao thức: **một response upstream SAML hợp lệ không tự trở thành OIDC ID Token hợp lệ cho mọi client**. Broker phải phát token đúng `iss` của nó, đúng `aud=client_id`, được ký bởi khóa broker đã công bố qua JWKS đáng tin và có subject mapping được quản lý.

## 9. Phân biệt OIDC state, nonce, PKCE và SAML RelayState

Một công ty có thể thấy cả hai bộ tham số trong cùng browser trace:

~~~text
APP -> BROKER /authorize:
  state=state-app-123
  nonce=nonce-app-456
  code_challenge=challenge-app-789

BROKER -> SAML IDP:
  SAMLRequest=...
  RelayState=relay-broker-ABC

SAML IDP -> BROKER:
  SAMLResponse=...
  RelayState=relay-broker-ABC

BROKER -> APP:
  code=code-for-portal
  state=state-app-123

APP -> BROKER /token:
  code=code-for-portal
  code_verifier=private-app-verifier
~~~

Các chuỗi trên **chỉ là ký hiệu minh họa**, không đủ entropy để dùng thật. Từng transaction có:
- TTL và kho state riêng;
- Bên tạo/kiểm tra riêng;
- Chữ ký và khóa tin cậy riêng;
- Endpoint response/callback riêng;
- Ràng buộc browser/session riêng;
- Cách xử lý lỗi và replay riêng.

**Không chuyển `RelayState` từ upstream SAML thành `state` trả về app** chỉ vì cả hai có từ “state”. Broker cần giữ mapping server-side giữa **giao dịch OIDC downstream** và **giao dịch SAML upstream**, có nonce/code riêng cho app.

### Hai lớp issuer

- SAML assertion có `Issuer=https://idp.example.org/entity` và Audience là broker SP entity ID.
- OIDC ID Token có `iss=https://broker.example.org` và `aud=portal-client`.

Nếu ứng dụng chỉ biết OIDC, nó kiểm tra **broker OIDC issuer**. Không dùng ID Token do upstream khác ký để tạo phiên nếu token không đúng issuer/client registration đã đăng ký.

## 10. Cấu hình Spring Boot cho OIDC Code Flow

### 10.1 Dependency trong project Servlet

Trong dự án Spring Boot 3.x đã có plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là snippet chèn vào `build.gradle` hiện có, không phải build file hoàn chỉnh. Khi ứng dụng **đồng thời** cần trực tiếp làm SAML SP, thêm module SAML riêng và định tuyến filter chains theo kiến trúc. Không cần `spring-security-saml2-service-provider` chỉ để một app làm **OIDC client với broker**.

### 10.2 application.yml: confidential backend client

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker-provider
            client-id: "portal-client"
            client-secret: "${OIDC_BROKER_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          broker-provider:
            issuer-uri: "https://broker.example.org"
~~~

Đây là **cấu hình mẫu**, không dùng được để đăng nhập thật tới tên miền minh họa. Tại deployment:
- Đăng ký chính xác `client_id` và redirect URI với broker.
- Secret được cung cấp qua **runtime secret manager/environment**; không commit secret thật.
- `issuer-uri` trỏ đến OIDC issuer mà client **đã tin và phê duyệt**, cho phép Spring khám phá OP metadata/JWKS.
- Broker phải cung cấp discovery endpoint và token endpoint phù hợp OIDC. Không nhập bừa upstream SAML entity ID làm OIDC issuer.
- Scope `openid` là ranh giới OIDC; nếu chỉ dùng OAuth scopes cho API và không `openid`, không nhận mặc định ID Token.
- `redirect-uri` ở ví dụ dùng template Spring; public URL qua reverse proxy phải khớp registration ở broker. Nếu request public là HTTPS mà backend thấy HTTP nội bộ, cần cấu hình forwarded headers **từ proxy tin cậy**.
- Có policy clock skew, cookie SameSite/Secure, session state và allowed redirect URLs.

**Lưu ý PKCE:** tùy phiên bản Spring Security và loại client, PKCE được áp dụng tự động cho public clients hoặc qua cấu hình `ClientRegistration.clientSettings.requireProofKey` / request customizer. **Không suy rằng chỉ có `authorization-grant-type=authorization_code` thì PKCE chắc chắn đã bật ở mọi version/confidential client.** Kiểm tra outbound request thực.

### 10.3 SecurityFilterChain: dùng OAuth2/OIDC login chuẩn

Tệp `src/main/java/com/example/portal/OidcLoginSecurityConfig.java`:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

**Đây là một lớp Spring configuration**, không phải Java độc lập có `main()`. Nó chỉ hoạt động khi Spring Boot application có dependencies, client registration và broker thực. Spring Security chịu trách nhiệm khởi tạo authorization request, nhận callback, trao đổi code và xác minh OIDC ID Token theo phiên bản. Không có stdout cố định.

Với registration `broker`, đường dẫn quan sát thường là:
- Bắt đầu login: `GET /oauth2/authorization/broker`.
- Callback: `GET /login/oauth2/code/broker?code=...&state=...`.
- Sau login, URL đích được quyết định bởi success handler/RequestCache và authorization của ứng dụng.

**Không** viết controller tự bắt callback rồi đánh dấu user authenticated chỉ vì có `code`. Đừng tắt `oauth2Login` validation để phù hợp một broker cấu hình sai.

## 11. Bật PKCE cho confidential client trong Spring Security 6.5+

Nếu app là confidential server-side client và yêu cầu dùng PKCE theo security policy, **Spring Security 6.5+** cung cấp `ClientRegistration.ClientSettings#requireProofKey`.

Một cấu hình thay thế Boot auto-registration, sử dụng issuer discovery và credentials do app nhận qua Spring properties:

Tệp `src/main/java/com/example/portal/OidcPkceClientConfig.java`:

~~~java
package com.example.portal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class OidcPkceClientConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${oidc.broker.issuer-uri}") String issuer,
            @Value("${oidc.broker.client-id}") String clientId,
            @Value("${oidc.broker.client-secret}") String clientSecret) {

        ClientRegistration registration =
                ClientRegistrations.fromOidcIssuerLocation(issuer)
                        .registrationId("broker")
                        .clientId(clientId)
                        .clientSecret(clientSecret)
                        .clientAuthenticationMethod(
                                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                        .authorizationGrantType(
                                AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri(
                                "{baseUrl}/login/oauth2/code/{registrationId}")
                        .scope("openid", "profile")
                        .clientSettings(
                                ClientRegistration.ClientSettings.builder()
                                        .requireProofKey(true)
                                        .build())
                        .build();

        return new InMemoryClientRegistrationRepository(registration);
    }
}
~~~

Các properties tương ứng **khi dùng bean Java thay cho Boot auto-registration**:

~~~yaml
oidc:
  broker:
    issuer-uri: "https://broker.example.org"
    client-id: "portal-client"
    client-secret: "${OIDC_BROKER_CLIENT_SECRET}"
~~~

**Không đăng ký đồng thời bean này và một ClientRegistrationRepository tự tạo khác có cùng `registrationId`**. Bạn có thể chọn một trong hai:
- Dùng Boot auto-registration YAML và customization phù hợp phiên bản;
- Hoặc dùng Java bean bên trên, trong đó `requireProofKey(true)` được đặt có chủ đích.

**Giới hạn và điều kiện:**
- `ClientRegistration.ClientSettings` là API ở Spring Security **6.5+**; nếu project đang chạy Spring Security 6.0–6.4, dùng extension `DefaultOAuth2AuthorizationRequestResolver#setAuthorizationRequestCustomizer(OAuth2AuthorizationRequestCustomizers.withPkce())` theo tài liệu/version thực tế, hoặc nâng phiên bản tương thích. Không import API chưa tồn tại.
- `ClientRegistrations.fromOidcIssuerLocation(issuer)` gọi OIDC discovery; cần broker đáng tin, HTTPS/TLS hợp lệ và kết nối lúc startup. Không cho người dùng điều khiển `issuer` qua query để tránh SSRF/mix-up.
- Broker phải **hỗ trợ và enforce PKCE** khi nhận `code_challenge` và `code_verifier`. Nếu provider trả lỗi, điều tra cấu hình broker; không bỏ PKCE trong hệ thống có chính sách bắt buộc.
- Secret dùng `client_secret_basic` cho confidential backend; PKCE **không thay thế** client authentication.
- Đảm bảo thư viện không tự loại nonce/state khi thêm customizer riêng; tránh tự gắn static nonce/code_challenge trong URL.
- Code chỉ là Spring Configuration, không có stdout; khi chạy cần SecurityFilterChain ở mục 10 và broker thật.

## 12. Spring Security giữ authorization request và state ở đâu?

Trên Servlet stack, các thành phần quan trọng:

| Thành phần | Vai trò |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Bắt đầu redirect tới Authorization Endpoint |
| `DefaultOAuth2AuthorizationRequestResolver` | Xây dựng authorization request theo `ClientRegistration` và customization |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Lưu transaction từ lúc request được gửi đến callback |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Repository mặc định lưu authorization request trong `HttpSession` |
| `OAuth2LoginAuthenticationFilter` | Xử lý callback `/login/oauth2/code/*` |
| `OAuth2AuthorizedClientRepository/Service` | Lưu authorized client/access token để dùng API khi cần |
| `OidcIdTokenDecoderFactory` | Phục vụ xác minh chữ ký ID Token theo client registration/algorithm |
| `SecurityContextRepository` | Quản lý persistence của authenticated SecurityContext trong app |

**Cần phân biệt:**
- Authorization Request Repository giữ `state` và dữ liệu liên quan (trong trường hợp PKCE còn có verifier attribute) **trước login**.
- Authorized Client Repository/Service lưu `access token/refresh token` sau grant theo policy, **không thay** request repository.
- HttpSession/SecurityContext lưu authentication của app sau login, không tự đại diện cho phiên upstream SAML của broker.
- SavedRequest/RequestCache giúp redirect về URL đã yêu cầu trước login; không nên trộn return URL với state không được validate.

### Khi mất session ở callback

Trình duyệt quay về app với `code` và `state`, nhưng HttpSession không còn (cookie SameSite, Domain/Path sai, session hết hạn hoặc callback đi node khác). Spring có thể không tìm thấy authorization request, từ chối callback **trước token exchange**.

**Không sửa bằng cách tắt state check**. Kiểm tra session cookie, reverse proxy, distributed Spring Session/sticky session và SameSite. Với OAuth2 Code Flow callback GET, SameSite=Lax có thể phù hợp trong nhiều top-level navigation; nhưng với cross-site POST response_mode, iframe hoặc browser privacy policy, không suy Lax luôn đủ.

### Multi-tab

Nếu hai tab bắt đầu hai login gần nhau trong cùng browser, repository/session implementation có thể gặp state overwrite/transaction race tùy version, customization và browser timing. Cần test nhiều tab nếu UX cho phép; không giải quyết bằng một global state cố định hoặc so state mà không kiểm tra browser session.

## 13. ID Token phải được xác minh đầy đủ

Sau token response, client nhận `id_token`. Một JWT thường có ba đoạn `header.payload.signature` được Base64url-encode. **Giải mã payload không có nghĩa token đáng tin**.

Tập kiểm tra OIDC cần xem:

| Trường / thuộc tính | Kiểm tra |
| --- | --- |
| JWT signature / alg / key | Xác minh bằng JWKS/key đã liên hệ với **issuer broker đáng tin**; không chấp nhận `alg=none` theo cách tự ý |
| `iss` | Khớp chính xác expected OIDC issuer trong client registration/discovery |
| `aud` | Bao gồm client ID của ứng dụng |
| `azp` | Xử lý theo OIDC rule nếu nhiều audiences hoặc claim xuất hiện |
| `exp` | Chưa hết hạn, áp clock skew có giới hạn |
| `iat` | Giá trị phát hành hợp lý theo policy và clock |
| `nonce` | Nếu client gửi nonce, claim ID Token phải phản hồi đúng |
| `auth_time` | Nếu có yêu cầu `max_age`/freshness, kiểm tra chính sách tương ứng |
| `acr`, `amr` | Chỉ dùng khi có contract về assurance/method và đủ kiểm chứng |
| `sub` | Subject ổn định trong phạm vi issuer/client; dùng `iss + sub` cho mapping |
| `at_hash/c_hash` | Kiểm tra nếu response type và profile yêu cầu; không áp máy móc Code Flow thuần như Implicit/Hybrid |

Không ánh xạ `email=admin@example.org` thành quyền admin. Email có thể thay đổi/được tái sử dụng và claim `email_verified` không tự xác nhận account thuộc tenant/role. Broker có thể map từ SAML NameID sang pairwise sub của mình; app phải xử lý **identity linking** có kiểm soát.

### ID Token không phải Access Token

- `ID Token`: đối tượng chính là **OIDC client**, kể thông tin về xác thực người dùng.
- `Access Token`: cấp truy cập **resource server** theo audience/scope/policy.
- `Refresh Token`: giúp client xin token mới khi được cấp, là secret có giá trị cao; không mặc định có trong mọi Code Flow.
- `Authorization Code`: giá trị ngắn hạn dùng **một lần**, không gọi API bằng Bearer.

Nếu API nhận JWT, nó cần cấu hình Resource Server kiểm tra **issuer/audience/signature/scope** của access token. Không lạm dụng OIDC ID Token làm API bearer token.

## 14. Bảo vệ chống authorization-server mix-up trong môi trường nhiều broker

Một ứng dụng có hai registrations:

~~~text
registrationId=broker-east
issuer=https://broker-east.example.org

registrationId=broker-west
issuer=https://broker-west.example.org
~~~

Kẻ tấn công có thể thử làm client nhầm authorization response của broker này thành response của broker kia, gây **authorization server mix-up** hoặc code leakage. Bảo vệ cần:
1. Lưu **registration/issuer dự kiến** trong transaction state, không chọn issuer theo query callback chưa xác minh.
2. Ràng buộc authorization response với đúng request, client ID và redirect URI.
3. Khi hỗ trợ, kiểm tra `iss` parameter trong Authorization Response theo **RFC 9207**.
4. Nếu môi trường không hỗ trợ response issuer, dùng phương án anti-mix-up được RFC 9700 mô tả, chẳng hạn **distinct redirect URIs per Authorization Server**, cùng các ràng buộc phù hợp.
5. Xác minh OIDC ID Token issuer và audience **sau token exchange**, nhưng không coi đó là bảo vệ duy nhất chống mọi dạng code leakage xảy ra trước token exchange.
6. Dùng fixed issuer allow-list/discovery tin cậy, không xây token endpoint bằng URL nhận từ browser.

**Một state khớp đơn thuần không đủ** nếu client không còn biết state này thuộc registration/AS nào hoặc dùng callback xử lý sai nhà phát hành.

## 15. Rủi ro open redirect tại điểm return-to URL

Đăng nhập thành công xong ứng dụng thường muốn quay lại trang sâu `/invoices/42`. Nếu dùng query như:

~~~text
/login?returnUrl=https://attacker.example.org/phishing
~~~

rồi đưa trực tiếp vào `state` hoặc success handler để redirect sau OIDC login, attacker có thể tạo **open redirect** trên domain đáng tin.

Cách thiết kế:
- Lưu **SavedRequest**/đường dẫn nội bộ đã chuẩn hóa ở server-side trước login.
- Nếu dùng opaque state handle, chỉ lưu key tra target và session binding.
- Chỉ redirect tới route nội bộ/allow-list origin cố định, từ chối URL bắt đầu `//`, lược đồ `javascript:`, encoded double slash, backslash và host spoof.
- Kiểm tra `Forwarded / X-Forwarded-Host` chỉ từ reverse proxy đáng tin.
- Không dùng `Referer` hay `post_logout_redirect_uri` tùy ý như after-login target.
- Authorization trên resource vẫn được kiểm tra dù target hợp lệ.

Một URI nằm trong `state` **không được tự động coi là đáng tin** chỉ vì broker echo state. Dữ liệu callback xuất hiện lại từ browser; app cần đối chiếu state với bản ghi đã tạo.

## 16. Bảo mật redirect URI, HTTPS và callback

**Redirect URI** là điểm browser đưa code về client. Những lưu ý:
- Dùng HTTPS public domain trên production; ngoại lệ loopback chỉ trong ngữ cảnh ứng dụng native/local dev theo spec.
- Broker đăng ký redirect URI chính xác; tránh wildcard, không cho phép tùy ý thay scheme/host/path hoặc redirect trung gian.
- Spring mặc định nhận OAuth2 Login callback tại `/login/oauth2/code/{registrationId}`. Nếu tùy chỉnh `.redirectionEndpoint().baseUri(... )`, phải đổi luôn registered redirect URI/client config.
- Trong reverse proxy, scheme/host phải phản ánh public URL thật; không để backend dựng `http://internal:8080`.
- Dùng state + transaction binding, PKCE và AS mix-up defense.
- Không cache callback code; hạn chế log query string có `code` trong access logs/analytics, tránh Referrer leakage (Referrer-Policy), không gửi sang domain khác.
- Không chuyển code, nonce, verifier, refresh token hoặc ID Token sang frontend chỉ để “debug”.
- Nếu callback bị gọi lặp sau khi code đã đổi, token endpoint nên báo lỗi; app không được tự tái sử dụng transaction.

**Khác với SAML ACS:** OIDC Code Flow mặc định dùng **GET callback** với code/state; SAML HTTP-POST profile dùng **POST ACS** có SAMLResponse. Cấu hình SameSite/cookie/CSRF cần dựa trên **flow thật**, không sao chép một chính sách cookie giữa hai giao thức mà không kiểm thử.

## 17. Java 17 độc lập: kiểm tra RFC 7636 S256 và tạo token ngẫu nhiên

Chương trình dùng **chỉ Java Standard Library**, không cần Spring. Nó:
1. Tính S256 challenge từ một `code_verifier` ví dụ chính thức RFC 7636.
2. Chứng minh challenge khớp test vector.
3. Sinh verifier 32 byte bằng `SecureRandom`, đảm bảo Base64url không padding cho độ dài 43 ký tự.
4. Minh họa `state` và `nonce` ngẫu nhiên **khác nhau**.
5. Không in token ngẫu nhiên hoặc secret.

Tệp `PkceAndOidcStateDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceAndOidcStateDemo {

    private static final SecureRandom RANDOM = new SecureRandom();

    static String randomBase64Url(int bytes) {
        byte[] value = new byte[bytes];
        RANDOM.nextBytes(value);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value);
    }

    static String challengeS256(String verifier) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(hash);
    }

    public static void main(String[] args) throws Exception {
        String verifier =
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        String expected =
                "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";

        System.out.println("RFC 7636 S256 matches: "
                + challengeS256(verifier).equals(expected));

        String freshVerifier = randomBase64Url(32);
        String state = randomBase64Url(18);
        String nonce = randomBase64Url(18);

        System.out.println("Verifier chars: " + freshVerifier.length());
        System.out.println("Verifier URL-safe: "
                + freshVerifier.matches("[A-Za-z0-9_-]{43}"));
        System.out.println("state bytes-ascii: "
                + state.getBytes(StandardCharsets.US_ASCII).length);
        System.out.println("nonce bytes-ascii: "
                + nonce.getBytes(StandardCharsets.US_ASCII).length);
        System.out.println("state and nonce differ: "
                + !state.equals(nonce));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PkceAndOidcStateDemo.java
java PkceAndOidcStateDemo
~~~

Stdout theo logic code (độ dài cố định, giá trị random không được in):

~~~text
RFC 7636 S256 matches: true
Verifier chars: 43
Verifier URL-safe: true
state bytes-ascii: 24
nonce bytes-ascii: 24
state and nonce differ: true
~~~

Kết quả `state and nonce differ` có xác suất gần như chắc chắn khi dùng random riêng cho hai giá trị 18 byte; về lý thuyết hai chuỗi ngẫu nhiên **vẫn có xác suất cực nhỏ trùng nhau**. Vì vậy nếu cần stdout **tuyệt đối xác định**, đoạn code nên kiểm tra/generate lại khi trùng. Bản demo này minh họa tính ngẫu nhiên; không nên viết unit test sản xuất phụ thuộc vào sự kiện ngẫu nhiên “không bao giờ trùng”.

**Đây không phải OIDC client hoàn chỉnh**: không tạo authorization request HTTP, không xử lý callback, không xác minh JWT/JWKS và không dùng khóa OIDC thật. Phần `challengeS256` minh họa PKCE tiêu chuẩn; verification của PKCE thật phải diễn ra tại **token endpoint của broker**. Trong Spring app, ưu tiên thư viện framework để tạo/lưu verifier, thay vì tự thêm random global static hay ghi verifier vào cookie JS-readable.

## 18. Vì sao phải gắn mã theo transaction cụ thể?

Một bảng state server-side do ứng dụng quản lý có thể trông như:

~~~text
transactionId: tx-opaque-001
browserBinding: session-backed-correlation
registrationId: broker
expectedIssuer: https://broker.example.org
stateHash: SHA-256(opaque-state)
nonceHashOrValue: tied-to-this-authorization-request
pkceVerifier: secret, only for token exchange
startedAt: UTC timestamp
expiresAt: short TTL
originalDestination: /reports/42
consumed: false
~~~

Đây là **mô hình kiến trúc**, không phải định dạng session key nội bộ của Spring Security. Trong triển khai thực, không cần lưu trùng state/nonce/verifier nếu framework repository đã lưu đúng; tuyệt đối không dựa vào tên key/private attributes không được API cam kết.

Quy tắc:
- Một browser có thể có nhiều transaction (nhiều tab); nếu cho phép, mỗi transaction phải có state/nonce/verifier **riêng**.
- State gắn với **đúng client/issuer/registration và browser**.
- Nonce gắn với **ID Token của transaction đã khởi tạo**.
- Verifier gắn với **authorization code mà broker đã cấp**.
- TTL ngắn; consume atomically để chống callback lặp/replay.
- Sau login hoặc failure, xóa state còn dùng một lần và dọn token nhạy cảm.
- Nếu session bị mất, fail closed và yêu cầu bắt đầu login mới; không nhận `state` từ query như một cache key global tự đủ để đăng nhập.

## 19. Ứng dụng vừa SAML SP vừa OIDC client thì sao?

Một migration có thể tạm có cả hai đường:
- `/saml2/authenticate/corp` → upstream SAML login trực tiếp.
- `/oauth2/authorization/broker` → OIDC login qua broker.

Hai đường dùng filter khác nhau:
- SAML: `Saml2WebSsoAuthenticationRequestFilter` và `Saml2WebSsoAuthenticationFilter`.
- OIDC: `OAuth2AuthorizationRequestRedirectFilter` và `OAuth2LoginAuthenticationFilter`.

**Đừng trộn repositories:**
- SAML AuthnRequest/RelayState state không phải OIDC AuthorizationRequest/state.
- SAML ACS `/login/saml2/sso/{registrationId}` khác OIDC callback `/login/oauth2/code/{registrationId}`.
- SAML verification dùng IdP X.509 certificate/trust từ metadata; OIDC verification dùng OP issuer/JWKS/ClientRegistration.
- SAML `NameID` không mặc nhiên đồng nhất OIDC `sub`.
- SAML `SessionIndex` không phải OIDC session cookie.
- OIDC `state/nonce/PKCE` không tự bảo vệ một SAML Assertion chưa xác minh.

Nếu ứng dụng hỗ trợ hai cơ chế đồng thời, phải xác định rõ **ưu tiên login, principal mapping, logout semantics, request matchers và tenant/account authorization**. Không để user từ đường login ít bảo đảm được gán authority của đường login mạnh hơn mà không kiểm chứng.

## 20. Identity broker: không được “launder” độ tin cậy

Khi broker nhận SAML assertion có:
- `Issuer` là upstream IdP;
- `Audience` là broker SAML SP entity ID;
- `Subject NameID` có thể transient/persistent;
- `AuthnContext`, `AuthnInstant`, group attributes có thể mang ý nghĩa riêng.

Broker phát OIDC ID Token của nó:
- `iss` là broker issuer;
- `sub` là subject broker cấp cho app;
- `aud` là OIDC client ID;
- `acr/amr/auth_time` nếu broker có contract đúng và bằng chứng phù hợp;
- Nhóm/quyền có thể là mapping theo broker policy.

**Bốn nguyên tắc:**

1. Broker phải xác minh **upstream SAML response** theo metadata/trust và các ràng buộc, không chỉ đọc NameID.
2. Broker không nên biến một string `group=admins` chưa được chuẩn hóa/phê duyệt thành quyền quản trị của app.
3. App phải kiểm tra **broker ID Token** với issuer và audience mong đợi, đồng thời áp dụng app authorization; không mặc nhiên tin email/name do upstream gửi.
4. Nếu muốn ràng buộc assurance, broker cần mapping `SAML AuthnContext → OIDC acr/amr/auth_time` theo **hợp đồng rõ ràng và kiểm chứng**. Không lấy việc có PKCE làm bằng chứng user đã xác thực bằng MFA.

### Subject mapping

OIDC `sub` có thể được cấp **pairwise** theo client/sector. Một user có thể có `sub` khác ở hai applications dù cùng đăng nhập IdP. Nên định danh account bằng `(issuer, subject)` và mapping nội bộ có quyền kiểm soát. Không tạo key user global từ email trống/chưa verified hoặc NameID transient thay đổi mỗi phiên.

## 21. Mix-up với upstream IdP và multi-tenant

Một broker nhận SAML từ nhiều IdP. Khi client downstream chọn "Login via Broker", broker có thể cho user chọn IdP:
- Broker phải giữ liên kết chính xác giữa OIDC transaction và SAML AuthnRequest.
- Upstream SAML Assertion chỉ được xác minh với **đúng IdP registration**, issuer, audience và keys phù hợp.
- Client Spring chỉ nên dùng broker issuer được cấu hình, không tự nhận issuer mới chỉ vì login về từ một IdP upstream.
- Claims như tenant, group, business role phải được broker map theo chính sách; app có quyền kiểm tra tenant nội bộ.
- Khi IdP A và IdP B cùng gửi email `alice@example.org`, không tự hợp nhất hai tài khoản nếu chưa có quy trình account linking đã xác thực.
- Nếu broker đổi issuer/sub semantics khi migrate realm/tenant, cần kế hoạch migration và kiểm thử danh tính tránh user takeover.

Đây là rủi ro khác với **authorization server mix-up** ở client, nhưng cả hai đều yêu cầu ràng buộc issuer/transaction **ở đúng lớp**.

## 22. CSRF, SameSite và session cookie trong OIDC callback

Spring Security sử dụng session trong nhiều cấu hình OAuth2 Login để lưu authorization request. Một callback GET cross-site từ broker về app thường có thể mang cookie `SameSite=Lax` nếu là top-level safe navigation, nhưng:
- Callback `response_mode=form_post` là cross-site POST, có quy tắc cookie khác.
- Browser privacy/iframe/third-party cookie có thể hạn chế cookie.
- `SameSite=None; Secure` có thể cần ở một số kiến trúc, nhưng cần đánh giá CSRF đầy đủ.
- HTTPS proxy/offload có thể làm cookie Secure/Domain/Path và redirect URI bị sai.
- Nếu app dùng session replication, callback có thể đến node khác; state repository cần tồn tại.
- Browser login flow có thể diễn ra trong tab khác/redirect chain bị gián đoạn.

**CSRF trên HTTP POST business API** vẫn cần bảo vệ riêng. Đừng hiểu “đã có OIDC state” nghĩa mọi POST của ứng dụng tự chống CSRF. `state` là bảo vệ **authorization callback**, còn Spring CSRF token/SameSite/Origin checks áp dụng cho các hành động thay đổi trạng thái của app.

## 23. Những lỗi hay gặp và cách đọc đúng lớp

| Triệu chứng | Nguồn khả dĩ | Kiểm tra đúng |
| --- | --- | --- |
| Callback về với `code` nhưng báo invalid state | Mất/nhầm transaction, cookie, multi-tab, CSRF | Session repository, state nguyên bản, browser binding |
| Callback thiếu `state` | Broker/response mode, sai URL, sửa query | Authorization Request và callback được phép |
| Broker trả `error=access_denied` | User từ chối consent/chính sách AS | Authorization response, không gọi token endpoint |
| `invalid_grant` ở token endpoint | Code expired/reused, verifier sai, redirect URI mismatch | Token request và PKCE enforcement; không retry code đã dùng |
| `invalid_client` | Client auth thiếu/sai | Client ID/secret, auth method, broker registration |
| Không thấy `code_challenge` | PKCE chưa bật theo version/client type | ClientSettings/customizer, outgoing URL |
| Có challenge mà broker bỏ qua verifier | AS không enforce PKCE đúng | Broker config/conformance; không tự coi PKCE đã bảo vệ |
| `nonce` trong ID Token không khớp | Transaction bị tráo/ID Token sai | Validator ID Token, nonce repository, transaction binding |
| ID Token signature sai | JWKS/key rotation, issuer/trust sai, token bị sửa | Broker discovery/JWKS, alg allow-list |
| ID Token `iss` sai | Mix-up/multi-tenant/issuer configuration | Expected issuer chứ không theo callback |
| ID Token `aud` không có client ID | Token cấp cho client khác | ClientRegistration và ID Token verification |
| `invalid redirect_uri` | Public domain/proxy/registration sai | Exact redirect URI, forwarded headers |
| HTTP 302 loop | Session cookie không lưu, login/authorization policy | Browser session, filter chain, SameSite |
| SSO qua broker thành công nhưng app user khác | Account linking/sub/email sai | Map `iss+sub`, tenant, immutable identity |
| Broker SAML login báo signature invalid | Lỗi upstream SAML, **không phải PKCE** | SAML metadata/trust và broker ACS |
| App login xong nhưng API 403 | Authorization/scope/audience không đạt | Business permissions/resource server, không bỏ OIDC checks |
| User logout app rồi SSO lại ngay | Broker/IdP session còn | OIDC logout/IdP SLO theo hợp đồng |
| GET callback lặp lại trả lỗi | Code/state one-time đã consume | Đây thường là fail-safe; không reuse token transaction |

**Không chữa bằng cách** bỏ state, bỏ nonce validation, hạ PKCE S256 xuống plain, accept ID Token không chữ ký, thêm mọi JWKS chưa xác minh hoặc cho phép wildcard redirect URI.

## 24. Tư duy xử lý callback an toàn

Để hiểu những bước framework làm, hãy dùng pseudo-code dưới đây như **checklist kiến trúc**, không copy vào controller để thay Spring Security:

~~~text
on GET /login/oauth2/code/broker:
  if callback contains error:
      classify authorized error and fail safely
  transaction = authorizationRequestRepository.loadFromBrowserSession()
  require transaction exists, not expired, correct client/issuer
  require callback.state == transaction.state
  require appropriate AS mix-up protection
  exchange code once via broker /token:
      authenticate client if confidential
      send matching redirect_uri and PKCE code_verifier
  validate ID Token:
      signature, trusted issuer, audience/client_id, time, nonce
  resolve (iss, sub) into local account
  check tenant/account status and local authorization
  create application Authentication/HTTP session
  consume transaction; redirect to approved SavedRequest
~~~

**Không suy đây là thứ tự nội bộ chính xác của mọi Spring Security version**; nó là sơ đồ các trách nhiệm, và provider/framework có thể sắp xếp bước verify phù hợp. Điểm an toàn là callback **không trực tiếp tương đương authenticated user**.

## 25. Bộ kiểm thử tích hợp tối thiểu

### Test A — Code Flow happy path

1. Xóa session app test và mở `/reports/42`.
2. Browser chuyển tới `/oauth2/authorization/broker`.
3. Kiểm tra authorization URL có `response_type=code`, `scope=openid`, đúng `client_id/redirect_uri`, state và PKCE challenge nếu policy bật.
4. Nếu client gửi nonce, kiểm tra nonce khác ở hai login độc lập; không xuất verifier trên URL.
5. Qua broker/IdP test, xác thực thành công.
6. Callback về `/login/oauth2/code/broker` với code + đúng state.
7. Backend trao code qua HTTPS với verifier và client auth.
8. Spring xác minh ID Token, tạo session, quay về deep link.
9. Truy cập route theo account authorization và quan sát login session hoạt động.

### Test B — state mismatch

- Tạo login A, thay state callback thành một giá trị khác trong lab.
- Kỳ vọng client từ chối/không tạo session mới, không dùng code bị tiêm.
- Không tắt state check để làm test pass.

### Test C — nonce mismatch

- Dùng OIDC test OP phát ID Token có nonce khác với request.
- Kỳ vọng provider validation từ chối nếu nonce đã được gửi/được client kiểm tra theo contract.
- Phân biệt với callback state mismatch: hai thời điểm kiểm tra khác nhau.

### Test D — PKCE code_verifier sai

- Tạo request có S256 code challenge, tại token request dùng verifier của transaction khác.
- Broker phải từ chối token exchange.
- Không kỳ vọng client “tự sửa” bằng cách bỏ PKCE.

### Test E — Replay code

- Đổi authorization code một lần, rồi thử dùng lại trong lab.
- Kỳ vọng invalid_grant hoặc lỗi policy, không có token mới.
- State one-time consumption vẫn được kiểm tra độc lập.

### Test F — Issuer mix-up

- Có hai OP registrations; giả lập callback broker A ở URI/transaction của B.
- Kỳ vọng không gửi code tới token endpoint sai issuer và không tạo session.
- Kiểm tra RFC 9207 `iss` response hoặc cơ chế redirect URI riêng theo thiết kế.

### Test G — Mất session cookie

- Gửi callback hợp lệ nhưng browser không có session đã mở flow.
- Kỳ vọng state repository không tìm được request và từ chối.
- Sửa SameSite/Domain/Path/multi-node state, không bỏ state validation.

### Test H — Broker upstream SAML sai

- Broker nhận SAMLResponse có chữ ký/issuer sai từ test IdP.
- Broker từ chối upstream SAML và không phát authorization code hợp lệ cho app.
- Ứng dụng không tự tiếp nhận XML SAML và không tạo SecurityContext.

### Test I — Return URL độc hại

- Đưa `https://evil.example.org` vào query return-to/state nếu endpoint cho phép input.
- Không được redirect tới host đó sau login; chỉ dùng local destination đã phê duyệt.

### Test J — Nhiều tab

- Bắt đầu login hai tab, mỗi tab có state/nonce/verifier riêng.
- Hoàn tất theo thứ tự đảo ngược.
- Tùy repository hỗ trợ nhiều transaction hay không, flow phải đúng hoặc từ chối an toàn; không chấp nhận token của tab khác chỉ vì trùng session.

## 26. Những điểm bảo mật đặc biệt của broker

### 26.1 Broker không tự đồng bộ quyền người dùng vĩnh viễn

Broker có thể phát group/role claims dựa trên upstream SAML attribute tại thời điểm login. App dùng các claims đó có nguy cơ stale nếu người dùng bị gỡ quyền sau login. Với thao tác nhạy cảm, cần app authorization live hoặc có cơ chế revocation. Nonce/PKCE **không giải quyết** bài toán cập nhật quyền.

### 26.2 Login qua một IdP không làm các IdP khác đáng tin

Một broker multi-IdP có thể dùng một OIDC issuer nhưng nhận nhiều upstream IdP. App cần hiểu provenance/tenant mapping nếu chính sách phân biệt cấp độ bảo đảm của các upstream providers. Không gộp account chỉ theo email và cho phép IdP yếu cấp quyền của IdP mạnh.

### 26.3 Authorization Code không được gửi sang upstream SAML IdP

Code do broker AS cấp **cho OIDC client** và được đổi tại **token endpoint broker**, không phải một phần của `SAMLResponse` hay RelayState upstream. Nếu broker cần giữ ngữ cảnh SAML và OIDC, làm việc đó trong state server-side của broker.

### 26.4 Client secret, nonce và verifier có mức bảo mật khác nhau

- `client_secret`: secret dài hạn của confidential client; giữ ở backend/secret manager.
- `code_verifier`: secret theo transaction ngắn hạn; không hiển thị browser/log, xóa sau dùng.
- `state/nonce`: giá trị ngẫu nhiên để đối chiếu transaction; được gửi qua front-channel nên **không xem là bí mật tuyệt đối**.
- `authorization code`: credential ngắn hạn đi qua browser; tránh đưa vào log, Referrer và analytics.
- `ID Token/access token/refresh token`: tokens nhạy cảm; kiểm soát lưu trữ, transport và phạm vi dùng.

### 26.5 CORS không thay được OAuth/OIDC security

Đăng nhập browser thông thường là **HTTP redirect/navigation**, không phải mọi bước đều là XMLHttpRequest. CORS không thay state, PKCE, issuer/audience/nonce, session binding hay Redirect URI policy. Nếu SPA gọi token endpoint bằng fetch, CORS có thể cần theo provider; PKCE và OAuth threat model của browser public client vẫn bắt buộc.

## 27. Bảng đối chiếu OIDC với SAML ở ranh giới ứng dụng

| Khía cạnh | OIDC Code Flow giữa app–broker | SAML Web SSO giữa broker–IdP |
| --- | --- | --- |
| Request khởi tạo | OAuth2/OIDC Authorization Request | SAML AuthnRequest |
| Ngữ cảnh browser | `state`, session-bound OAuth2AuthorizationRequest | `RelayState`, AuthnRequest repository |
| Ràng buộc ID Token | `nonce` | Không có OIDC nonce; có SAML request ID, InResponseTo/SubjectConfirmation |
| Chống code interception | PKCE `code_challenge/code_verifier` | Không có authorization code để đổi, dùng XML Signature/conditions |
| Bằng chứng xác thực | JWT ID Token từ broker | XML SAML Assertion từ IdP |
| Bên xác minh | App OIDC client | Broker đóng vai SAML SP |
| Định danh đối tác | OIDC issuer URI + client registration | IdP SAML entity ID + SP entity ID |
| Chữ ký | JWS/JWKS ID Token; optional token binding | XML Signature/binding signature |
| Callback | `/login/oauth2/code/{registrationId}` | ACS SAML tại broker |
| Session app | Spring Security OIDC Authentication/session | Broker giữ SAML session/upstream correlation |
| Logout | OIDC RP-initiated/back-channel theo khả năng OP | SAML Single Logout theo IdP/SP profile |
| Cập nhật quyền | App policy/claims mapping + revocation | Broker mapping upstream attributes theo hợp đồng |

Đừng cố tạo một bộ lọc trung gian tự chuyển XML SAML thành JWT bằng cách Base64 decode rồi ký tùy tiện; một **identity broker** phải kiểm tra trust ở cả hai ranh giới và có account mapping/claim policy được audit.

## 28. Checklist triển khai production

- [ ] Client OIDC biết chính xác issuer broker, client ID, redirect URI, allowed JWS algorithms/JWKS và OIDC discovery đáng tin.
- [ ] Dùng Authorization Code, `scope=openid` cho OIDC; không dùng Implicit Flow chỉ để tránh backend.
- [ ] Authorization Request sinh `state` mới, khó đoán, bound to browser/session, TTL và one-time consume.
- [ ] Nếu dùng `nonce`, client tạo mới mỗi transaction và xác minh claim trong ID Token đã ký.
- [ ] PKCE `S256` hoạt động thật ở authorization + token endpoint; public client bắt buộc dùng PKCE, confidential client nên dùng.
- [ ] `code_verifier` không xuất hiện trong authorization URL, browser log hoặc client bundle của confidential app.
- [ ] Authorization Server enforce verifier, code one-time, client ID và redirect URI.
- [ ] Callback chỉ tạo Authentication sau token exchange và ID Token validation.
- [ ] Dùng `iss + sub` và mapping tenant/account có kiểm chứng; không tin email/role từ provider bất kỳ.
- [ ] Có anti-mix-up defense khi nhiều OP/broker, không chọn token endpoint theo input callback.
- [ ] Nếu app có broker SAML upstream, broker tự xác minh SAML signature/issuer/audience/time/InResponseTo.
- [ ] Không tái sử dụng OIDC state/nonce/code_verifier làm upstream SAML RelayState.
- [ ] Return URL là local approved route, SavedRequest hoặc opaque server-side handle; không có open redirect.
- [ ] Session cookie, SameSite/Secure/Path, multi-node store và proxy public origin được kiểm thử.
- [ ] Client secret, access/refresh tokens, verifier, code và ID Token không bị log/đưa vào HAR chia sẻ.
- [ ] Đã thử negative tests state/nonce/PKCE mismatch, expired code, issuer/audience sai, lost session, multiple tabs.
- [ ] Authorization ứng dụng vẫn xác minh quyền hiện tại, không dùng ID Token như quyền tất cả tài nguyên.
- [ ] Upgrade Spring Security/OpenSAML/OAuth2 stack theo BOM, không áp API 6.5 vào dự án cũ mà không kiểm tra.

## 29. Câu hỏi ôn tập có đáp án

**Câu 1.** Authorization callback trả `code` nhưng `state` khác request đã lưu. Client có nên đổi code để xem user là ai rồi quyết định không?

**Đáp án:** không. Từ chối callback trước khi tạo login; state là correlation/CSRF control, không dùng token exchange để “tự sửa” mismatch.

**Câu 2.** `nonce` được gửi tới Authorization Endpoint, vậy nó phải xuất hiện ở đâu để client kiểm tra?

**Đáp án:** trong claim `nonce` của **ID Token** từ broker nếu client đã gửi nonce; client so giá trị sau khi kiểm tra token signature/issuer/audience.

**Câu 3.** S256 `code_challenge` được tạo thế nào?

**Đáp án:** `BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))`. Verifier random 43–128 ký tự, nên dùng ít nhất 32 byte entropy rồi Base64url.

**Câu 4.** PKCE có làm cho một ID Token sai issuer trở thành đáng tin không?

**Đáp án:** không. PKCE bảo vệ authorization code exchange, không thay ID Token validation.

**Câu 5.** Confidential client giữ `client_secret` ở server. Có cần PKCE nữa không?

**Đáp án:** PKCE vẫn được RFC 9700 khuyến nghị để bảo vệ code injection/misuse; client auth và PKCE bổ sung, không thay thế nhau.

**Câu 6.** Browser thấy SAML RelayState từ IdP và OIDC state từ broker. Có nên dùng chung hai chuỗi này?

**Đáp án:** không. Chúng thuộc hai giao dịch/trust boundaries độc lập. Broker giữ mapping server-side nếu cần.

**Câu 7.** IdP upstream phát SAML Assertion có Audience là broker. App trực tiếp dùng Assertion đó làm chứng cứ login OIDC được không?

**Đáp án:** không. Broker phải xác minh SAML rồi phát ID Token của **broker issuer**, Audience là app client ID, được app xác minh.

**Câu 8.** Có thể lưu `returnUrl=https://evil.example.org` trong state và redirect sau login không?

**Đáp án:** không an toàn. Dùng opaque state + target server-side allow-list để tránh open redirect.

**Câu 9.** Callback về đúng state nhưng không còn phiên HttpSession. Có nên truy vấn state global rồi lập Authentication để không mất trải nghiệm không?

**Đáp án:** không nếu không có browser/session binding tin cậy. Cần sửa session/cookie/repository và fail closed khi không thể xác minh transaction.

**Câu 10.** Browser đã hoàn tất SAML login ở upstream IdP nhưng app không nhận được code. Điều tra ở đâu?

**Đáp án:** xem broker SAML ACS/validation, broker OIDC authorization transaction, redirect URI, browser/proxy. SAML upstream success không tự chứng minh downstream code đã được phát.

**Câu 11.** Sử dụng `email_verified=true` là đủ để map mọi tài khoản cùng email giữa hai IdP không?

**Đáp án:** không. Cần issuer, subject, tenant, account linking và policy có kiểm chứng.

**Câu 12.** Khi callback state đúng, PKCE đúng nhưng app trả 403 sau login, có chắc OAuth/OIDC bị lỗi không?

**Đáp án:** không. Nếu Authentication đã được tạo, có thể là authorization/business policy của app, cần kiểm tra quyền hiện tại.

**Câu 13.** Nếu dùng Spring Security 6.2, có thể import `ClientRegistration.ClientSettings` như trong code 6.5 không?

**Đáp án:** không mặc nhiên; API này được bổ sung trong dòng 6.5. Dùng request customizer phù hợp phiên bản hoặc nâng dependency có kiểm thử.

**Câu 14.** Có thể in `code_verifier`, client secret, ID Token và access token vào log để debug?

**Đáp án:** không. Chỉ log mã lỗi, registration, request correlation ID đã redact và trạng thái từng bước, không để lộ credentials/tokens.

**Câu 15.** Vì sao app dùng issuer broker để xác minh ID Token thay vì SAML issuer của upstream IdP?

**Đáp án:** app nhận **OIDC token do broker phát**, broker là OpenID Provider mà app đã đăng ký và tin. Upstream IdP được broker xác minh ở giao dịch SAML khác.

## 30. Tổng kết

**Authorization Code** là credential ngắn hạn mà broker cấp cho client, chỉ được đổi qua token endpoint theo policy. **state** gắn authorization callback với request/browser đúng; **nonce** gắn ID Token với authentication transaction khi được gửi; **PKCE S256** buộc bên đổi code chứng minh sở hữu verifier tương ứng với challenge lúc bắt đầu.

Trong federation có broker, **mỗi giao thức có trust boundary riêng**: app Spring Security kiểm tra OIDC state/nonce/PKCE/ID Token đối với broker, trong khi broker tự kiểm tra upstream SAML RelayState/AuthnRequest và chữ ký/conditions. Các kiểm tra **bổ sung**, không thay thế nhau. Sự thành công của một hop không tự cấp quyền hoặc bảo đảm hop còn lại đã hợp lệ.

### Tài liệu chuẩn và tài liệu Spring Security

1. RFC 6749 — OAuth 2.0 Authorization Code Grant: https://www.rfc-editor.org/rfc/rfc6749.html
2. RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients, code_verifier/S256 và test vector: https://www.rfc-editor.org/rfc/rfc7636.html
3. RFC 9700 — Best Current Practice for OAuth 2.0 Security, PKCE/state/nonce/mix-up: https://www.rfc-editor.org/rfc/rfc9700.html
4. RFC 9207 — Authorization Server Issuer Identification: https://www.rfc-editor.org/rfc/rfc9207.html
5. OpenID Connect Core 1.0, Authorization Code Flow, state, nonce, ID Token validation: https://openid.net/specs/openid-connect-core-1_0.html
6. RFC 10017 — OAuth 2.0 for Browser-Based Applications, kiến trúc browser/BFF và PKCE: https://www.rfc-editor.org/rfc/rfc10017.html
7. Spring Security — OAuth 2.0 Login Core Configuration, ClientRegistration, callback: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
8. Spring Security — OAuth 2.0 Login Advanced Configuration, authorizationRequestRepository, redirect endpoint và ID Token validation: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
9. Spring Security — OAuth 2.0 Client Authorization Grants, PKCE/HttpSessionOAuth2AuthorizationRequestRepository: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
10. Spring Security 6.5 API — ClientRegistration.ClientSettings.Builder.requireProofKey: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/registration/ClientRegistration.ClientSettings.Builder.html
11. Spring Security — SAML 2.0 Login Overview, upstream đối chiếu: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
