# OAuth2: resource owner, client, authorization server và resource server

> **Bối cảnh:** Spring Security – fundamentals / **Token và giao thức**. Bài này giải thích **bốn vai trò chuẩn của OAuth 2.0**, ranh giới tin cậy, hai luồng cấp quyền thường gặp, token và cách ánh xạ các vai trò vào thành phần Spring Security. Ví dụ thực hành dùng Java 17, Spring Boot 3.5.0, Spring Security 6.x. OAuth 2.0 chủ yếu giải quyết **ủy quyền (authorization/delegated access)**; khi cần giao thức xác thực danh tính người dùng và ID token, tìm hiểu thêm **OpenID Connect (OIDC)**.

## 1. Vì sao cần bốn vai trò riêng?

Hãy tưởng tượng Alice đang dùng ứng dụng **Report Dashboard** và muốn ứng dụng đọc một phần hồ sơ lưu tại **Profile API**. Alice không muốn đưa mật khẩu Profile API cho ứng dụng Report Dashboard. Hệ thống có một máy chủ cấp quyền riêng, chẳng hạn `https://login.example.test`.

Trong tình huống này:

- **Resource owner:** Alice, chủ thể có khả năng cấp quyền truy cập dữ liệu được bảo vệ.
- **Client:** Report Dashboard, ứng dụng muốn gọi API với quyền được cấp.
- **Authorization server:** Máy chủ `login.example.test` xác thực, xác nhận quyền được cấp và phát hành token.
- **Resource server:** Profile API, máy chủ giữ dữ liệu và kiểm tra access token khi có request.

```mermaid
flowchart LR
    RO["Resource owner<br/>Alice"] -->|"đăng nhập / đồng ý cấp quyền"| AS["Authorization server<br/>login.example.test"]
    C["Client<br/>Report Dashboard"] -->|"authorization request"| AS
    AS -->|"authorization code / access token"| C
    C -->|"Bearer access token"| RS["Resource server<br/>Profile API"]
    RS -->|"dữ liệu theo policy"| C
    C -->|"hiển thị kết quả"| RO
```

**Giá trị cốt lõi:** ứng dụng client nhận **quyền có phạm vi**, không cần biết mật khẩu của resource owner. Resource server không được tin client chỉ vì client nói “Alice đã đồng ý”; nó phải kiểm tra token và chính sách của chính resource server.

RFC 6749 định nghĩa bốn vai trò này ở cấp **logic**. Chúng không nhất thiết tương ứng với bốn tiến trình độc lập: authorization server và resource server có thể cùng một hệ thống hoặc tách hạ tầng; một phần mềm có thể vừa đóng vai OAuth client khi gọi bên ngoài, vừa làm resource server cho API của chính nó.

## 2. Bốn vai trò theo RFC 6749

### 2.1. Resource owner — chủ thể có quyền cho phép

**Resource owner** là thực thể có khả năng cấp quyền đối với tài nguyên được bảo vệ. Khi đó là một con người, RFC gọi là *end-user*. Trong ví dụ, Alice có thể đồng ý để Report Dashboard đọc hồ sơ nhưng không đồng ý để sửa/xóa hồ sơ.

Điểm quan trọng:

1. Resource owner **không phải** server chứa dữ liệu; người quản lý/được quyền cấp phép mới là resource owner.
2. Resource owner **không phải lúc nào cũng là người đang cầm trình duyệt**. Với hệ thống machine-to-machine, không phải grant nào cũng có người dùng tương tác.
3. Alice có thể không sở hữu quyền tuyệt đối đối với mọi dữ liệu: một API doanh nghiệp còn chịu quy tắc tenant, phân quyền tổ chức, chính sách pháp lý và quyền chia sẻ.
4. Authentication (Alice là ai) và authorization (Alice cho phép client làm gì) là hai quyết định có liên hệ nhưng khác nhau.

Ví dụ: Người dùng chọn “Cho phép ứng dụng đọc tên và email” là hành động ủy quyền cho client, không phải cung cấp mật khẩu cho client. Authorization server có thể cần login, MFA hoặc các chính sách bổ sung trước khi đồng ý.

### 2.2. Client — ứng dụng đề nghị dùng tài nguyên

**Client** là ứng dụng gửi yêu cầu truy cập tài nguyên được bảo vệ, dùng sự ủy quyền của resource owner hoặc dùng quyền của chính client theo grant phù hợp.

Client có thể là:

- Server-side web application có backend riêng;
- Single-page application (SPA) chạy trong browser;
- Mobile/desktop app;
- Backend job hoặc service-to-service integration.

**Client không nhất thiết là trình duyệt.** Trong authorization code flow, trình duyệt là *user-agent* giúp resource owner tương tác với authorization server; OAuth client có thể là backend của ứng dụng.

Khái niệm quan trọng:

| Client | Giữ secret an toàn? | Đặc điểm |
| --- | --- | --- |
| Confidential client, ví dụ backend được quản lý | Có thể, nếu quản lý secret/khóa an toàn | Có thể xác thực tại token endpoint theo cơ chế đăng ký |
| Public client, ví dụ SPA hoặc ứng dụng mobile phân phối tới người dùng | Không thể bảo đảm giữ client secret | Cần Authorization Code + PKCE và các biện pháp phù hợp; **không nhúng secret vào frontend** |

`client_id` thường là **định danh công khai**, không phải bằng chứng client được xác thực. `client_secret` (nếu được cấp) phải được bảo vệ như credential và không được nhúng vào JavaScript, APK hoặc repository công khai. Public client vẫn cần client registration và các kiểm tra khác như redirect URI và PKCE.

### 2.3. Authorization server — phát hành token sau khi xét quyền

**Authorization server (AS)** xử lý yêu cầu ủy quyền và cấp access token cho client sau khi đủ điều kiện. Với flow có người dùng, AS thường tổ chức login, consent, code issuance và token exchange. Với client credentials grant, AS xác thực client và cấp token cho hoạt động mà client được phép làm.

Ví dụ các endpoint AS thường cung cấp:

| Endpoint | Nhiệm vụ | Ghi chú |
| --- | --- | --- |
| `/oauth2/authorize` | Nhận authorization request, thực hiện login/consent, trả code khi thành công | Tham gia qua browser redirect |
| `/oauth2/token` | Đổi authorization code hoặc credentials/grant thành token | Giao tiếp bằng HTTPS, kiểm grant và client |
| `/oauth2/jwks` | Công bố khóa công khai để xác minh JWT khi có cơ chế phù hợp | Không công bố private key |
| `/oauth2/introspect` | Cho resource server kiểm tra trạng thái token dạng opaque hoặc theo kiến trúc chọn | Cần xác thực caller có quyền |
| `/oauth2/revoke` | Thu hồi token theo RFC 7009 khi AS hỗ trợ | Không khẳng định mọi JWT access token bị từ chối ngay nếu RS không kiểm trạng thái |
| Metadata/discovery | Công bố endpoint, issuer, khả năng hỗ trợ | Ví dụ RFC 8414 / OIDC discovery |

Các URL trên chỉ là **ví dụ phổ biến**, không phải quy định rằng mọi provider phải dùng chính xác các path đó. Với Spring Authorization Server, một số path mặc định có thể tương tự; đọc metadata và cấu hình thật thay vì hardcode theo bài học.

AS có thể đi kèm Identity Provider để xác thực người dùng, nhưng **đăng nhập vào một Identity Provider và việc một resource server chấp nhận access token là hai bước khác nhau**.

### 2.4. Resource server — máy chủ API nhận và kiểm tra token

**Resource server (RS)** lưu trữ/cung cấp protected resources. Khi client gửi Bearer access token, RS phải xác thực tính hợp lệ và quyết định request được phép đến tài nguyên cụ thể hay không.

Với JWT, RS thường phải kiểm tra:

- Chữ ký hợp lệ, thuật toán/khóa được tin cậy, thời hạn (`exp`), thời điểm hiệu lực (`nbf`) nếu có;
- Issuer (`iss`) phù hợp AS đã cấu hình;
- Audience (`aud`) hoặc resource indicator phù hợp **API này**, nếu token profile/AS sử dụng audience;
- Scopes/authorities, HTTP action và các quy tắc role/tenant/ownership của resource;
- Trạng thái khóa hoặc revocation nếu hệ thống có yêu cầu và cơ chế kiểm tra bổ sung.

Với opaque token, RS có thể dùng token introspection ở AS để hỏi token còn **active** không và token có thuộc phạm vi phù hợp không. Đừng giải mã token opaque như thể đó là JWT.

**Không giao tất cả việc phân quyền cho authorization server:** AS có thể nói token có `scope=profile.read`, nhưng Profile API vẫn phải kiểm tra liệu Alice có được đọc **bản ghi hồ sơ đang yêu cầu** hay không. Scope chỉ là một phần của quyết định.

## 3. Tóm tắt vai trò và ranh giới trách nhiệm

| Câu hỏi | Thành phần chịu trách nhiệm chính |
| --- | --- |
| Ai là thực thể có quyền đồng ý cho phép đọc hồ sơ? | Resource owner |
| Ai muốn gọi API? | Client |
| Ai xác thực tài khoản người dùng, chấp thuận grant và phát hành access token? | Authorization server |
| Ai giữ hồ sơ và từ chối token không đủ quyền? | Resource server |
| Ai lưu `client_id` và thực hiện redirect tới AS? | Client |
| Ai phải kiểm tra `redirect_uri` đã đăng ký? | Authorization server |
| Ai phải kiểm tra token đúng `aud` của API? | Resource server |
| Ai phải giữ bí mật client secret? | Confidential client và authorization server |
| Ai có thể cấp lại access token qua refresh token? | Authorization server, nếu grant/client đủ điều kiện |
| Ai phải chặn IDOR/BOLA khi user A xin dữ liệu user B? | Resource server và tầng nghiệp vụ/dữ liệu |
| Ai quyết định client được consent scope nào? | Chính sách của AS và resource owner khi có user interaction |

**Mô hình tin cậy:** Client không được tự cấp quyền bằng cách sửa request hoặc claims. RS không được tin mọi Bearer token chỉ vì nó có cấu trúc JWT; token cần được xác minh đúng nguồn, đối tượng nhận, thời hạn và quyền. AS không được tin `redirect_uri` do client gửi nếu không so với giá trị đã đăng ký theo chính sách.

## 4. Authorization Code + PKCE: luồng có resource owner tương tác

**Authorization Code Grant** là một cách phổ biến để client xin quyền thay mặt một user. Security BCP RFC 9700 yêu cầu **public clients dùng PKCE**; confidential clients cũng được khuyến nghị dùng PKCE.

### 4.1. Trình tự mức cao

```mermaid
sequenceDiagram
    participant O as Alice / Browser
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server

    O->>C: Chọn "Kết nối Profile API"
    C->>C: Tạo state + code_verifier
    C->>C: Tính S256 code_challenge
    C-->>O: Redirect tới authorization endpoint
    O->>AS: GET /authorize?client_id=...&scope=...&state=...&code_challenge=...
    AS->>O: Login + consent (nếu cần)
    O->>AS: Chấp thuận quyền phù hợp
    AS-->>O: Redirect về client với code + state
    O->>C: Callback kèm code + state
    C->>C: Kiểm tra state
    C->>AS: POST /token code + code_verifier + client auth nếu áp dụng
    AS->>AS: Kiểm code, client, redirect_uri và PKCE
    AS-->>C: access_token (+ refresh_token nếu được cấp)
    C->>RS: GET /api/profile với Authorization: Bearer access_token
    RS->>RS: Validate token + scope + policy
    RS-->>C: Trả hồ sơ đã được phép
    C-->>O: Hiển thị kết quả
```

Để giữ ví dụ dễ học, luồng mô tả một browser redirect tiêu biểu. Thành phần client thực tế có thể dùng BFF, SPA hoặc mobile; cách lưu token và điểm trao đổi code phụ thuộc phân loại client.

### 4.2. Authorization request — các tham số cần hiểu

Ví dụ **minh họa**, giá trị chỉ là placeholder:

```http
GET /oauth2/authorize?
    response_type=code&
    client_id=report-dashboard&
    redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&
    scope=profile.read&
    state=opaque-random-state&
    code_challenge=BASE64URL_SHA256_VERIFIER&
    code_challenge_method=S256
Host: login.example.test
```

| Tham số | Ý nghĩa |
| --- | --- |
| `response_type=code` | Đề nghị Authorization Code Flow |
| `client_id` | Định danh client đã đăng ký ở AS |
| `redirect_uri` | Địa chỉ callback được AS kiểm soát nghiêm ngặt |
| `scope` | Quyền client yêu cầu; AS có thể cấp ít hơn tùy policy |
| `state` | Liên kết callback với yêu cầu đang chờ, giúp phòng chống CSRF và response injection |
| `code_challenge` | Giá trị được tạo từ bí mật một lần `code_verifier` |
| `code_challenge_method=S256` | Yêu cầu AS dùng hàm băm SHA-256 theo PKCE |

`state`, `code_verifier` và `nonce` (nếu có OIDC) cần được sinh ngẫu nhiên đủ mạnh, lưu liên kết với transaction/client, kiểm đúng khi callback và không tái sử dụng vô hạn. Không đặt một literal như `opaque-random-state` vào hệ thống thật.

**Lưu ý OAuth so với OIDC:** Nếu đây là yêu cầu đăng nhập qua OIDC, thường có `scope=openid` và xử lý **ID token** cùng nonce/issuer theo OIDC. Một OAuth access token thông thường không phải bằng chứng đăng nhập hay ID token cho client.

### 4.3. Code và PKCE bảo vệ điều gì?

**Authorization code** là credential ngắn hạn để client đổi lấy token; code phải có giới hạn thời gian, được ràng buộc với client và redirect URI, và được dùng một lần. Nếu kẻ tấn công lấy được code trong callback, PKCE khiến việc đổi code khó hơn vì attacker không có `code_verifier` được tạo từ phía client có phiên giao dịch hợp lệ.

Cách tính cho PKCE `S256`:

```text
code_verifier: chuỗi ngẫu nhiên high-entropy của mỗi authorization request
digest: SHA-256(ASCII(code_verifier))
code_challenge: BASE64URL(digest) không padding
```

Không đặt `code_verifier` trong authorization request (chỉ gửi `code_challenge`), không dùng secret cố định cho nhiều login transaction, và không coi PKCE là thay thế mọi kiểm tra khác như redirect URI, mix-up/issuer và transaction binding.

### 4.4. Token request — chỉ client đổi code

Ví dụ trao đổi code (conceptual, không dùng giá trị giả để gọi provider thật):

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=ONE_TIME_AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&
client_id=report-dashboard&
code_verifier=ORIGINAL_HIGH_ENTROPY_VERIFIER
```

Confidential client thường còn xác thực chính nó với AS, chẳng hạn `client_secret_basic` hoặc private-key JWT, theo chính sách AS. Public client **không thể** biến mình thành confidential bằng việc kèm một client secret được nhúng trong frontend.

Kết quả minh họa:

```json
{
  "access_token": "ACCESS_TOKEN_FROM_AS",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "profile.read",
  "refresh_token": "REFRESH_TOKEN_IF_ISSUED"
}
```

Không phải grant nào cũng cấp refresh token. Token response và format phụ thuộc provider. **Không log token**, không đưa token thật vào README, bug report hoặc query string.

### 4.5. Client gọi resource server

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_FROM_AS
```

Tại RS: token hợp lệ nhưng không có scope đọc profile → **403** thường dùng kèm Bearer error `insufficient_scope`; không có hoặc token sai/hết hạn → **401** thường có `WWW-Authenticate`. HTTP error handler có thể được tùy biến, nên test phải đối chiếu contract và không lộ dữ liệu, không suy đoán chỉ từ mỗi status.

## 5. Client Credentials: luồng không có user tương tác

OAuth 2.0 còn phục vụ **backend-to-backend**. Ví dụ một batch service cần đọc metric nội bộ đã được cấp cho chính ứng dụng.

```mermaid
sequenceDiagram
    participant C as Backend Client
    participant AS as Authorization Server
    participant RS as Metrics Resource Server
    C->>AS: POST /token, grant_type=client_credentials + client authentication
    AS->>AS: Xác thực client và kiểm quyền của client
    AS-->>C: Access token giới hạn cho metrics.read
    C->>RS: GET /metrics với Bearer token
    RS->>RS: Kiểm issuer, audience, scope và policy
    RS-->>C: Metrics đã cho phép
```

**Không có resource owner là người dùng tham gia bước login/consent** trong request này. Grant dựa trên quyền của chính client đã đăng ký ở AS. Resource server **không được suy ra có Alice đang đăng nhập** chỉ vì token hợp lệ. Trong JWT access token profile, claim `sub` có thể đại diện cho client chứ không phải end-user. Nếu hệ thống chấp nhận cả user token lẫn client token, phải phân biệt loại identity/scope/audience/actor để tránh client giả làm user.

Request minh họa của confidential client:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic BASE64_ENCODED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=metrics.read
```

Base64 trong HTTP Basic **không phải mã hóa bí mật**; cần HTTPS và quản lý secret/khóa an toàn. Với client authentication mạnh hơn có thể sử dụng mTLS/private-key JWT theo hỗ trợ của AS.

Không dùng **Resource Owner Password Credentials** cho tích hợp mới: RFC 9700 nêu rõ grant này không được sử dụng vì buộc client xử lý password của resource owner và làm tăng bề mặt tấn công. Cũng không chọn implicit flow cho thiết kế mới khi Authorization Code + PKCE đáp ứng yêu cầu.

## 6. Token nào đi tới thành phần nào?

### 6.1. Access token

**Access token** là credential client gửi đến RS để truy cập tài nguyên. Định dạng có thể là:

- **JWT (self-contained):** RS kiểm tra chữ ký, claims và các rule; không nhất thiết gọi AS mỗi request. Muốn thu hồi tức thì cần thêm state/denylist/version/introspection theo thiết kế.
- **Opaque token:** Bản thân token không cung cấp claims cho client; RS thường introspect với AS hoặc một lớp verification thích hợp để biết token active và authorities.

Không có quy định rằng **mọi OAuth 2.0 access token là JWT**. Một bearer token là credential: ai giữ được nó có thể cố sử dụng trong phạm vi và thời hạn còn hiệu lực. Luôn bảo vệ bằng HTTPS, không ghi vào URL, logs hoặc analytics.

### 6.2. Refresh token

Refresh token (nếu cấp) cho client xin access token mới mà không cần resource owner làm lại mọi bước tương tác. Nó **gửi tới AS token endpoint**, không gửi làm Bearer credential để đọc API tại RS. Chính sách của AS có thể dùng **refresh token rotation**, sender-constraining và revoke khi phát hiện replay hoặc logout.

**Đừng nhầm:** thu hồi refresh token ngăn client lấy token mới, nhưng một JWT access token cũ còn hạn có thể vẫn được RS nhận nếu không có cơ chế thu hồi/kiểm tra trạng thái bổ sung.

### 6.3. Authorization code

Authorization code là credential ngắn hạn dùng một lần để hoàn tất token exchange, **không** được dùng làm Bearer token gọi RS.

### 6.4. ID token — thuộc OpenID Connect, không phải OAuth 2.0 cốt lõi

ID token thường là JWT do OIDC provider phát hành cho **client** với thông tin kết quả authentication, subject và audience của client. Nó **không đồng nghĩa** với access token và thường **không phải credential thích hợp để gọi API**. RS phải nhận và kiểm tra access token dành cho RS.

Đơn giản hóa:

| Loại | Ai cấp | Ai nhận/kiểm | Mục đích |
| --- | --- | --- | --- |
| Authorization code | AS | AS token endpoint thông qua client | Đổi token một lần |
| Access token | AS | Resource server | Gọi protected API |
| Refresh token | AS | AS token endpoint | Xin access token mới |
| OIDC ID token | OIDC Provider | OAuth/OIDC client | Chứng thực kết quả đăng nhập cho client |

### 6.5. Scope không thay thế authorization theo đối tượng

Giả sử access token có `scope=invoice.read`. Điều này **chưa** chứng minh người dùng được đọc **mọi hóa đơn**. Invoice API cần kiểm tra owner, tenant, ACL, trạng thái giao dịch và nghiệp vụ cụ thể.

```java
// Mẫu kiểm tra ở service, không phải chương trình độc lập:
Mono<Invoice> loadInvoice(String invoiceId, String accountId) {
    return repository.findByIdAndAccountId(invoiceId, accountId)
        .switchIfEmpty(Mono.error(new NotFoundException()));
}
```

Đây là **mã minh họa** cho repository reactive với interface/domain chưa định nghĩa; với Spring MVC/JPA có thể dùng repository đồng bộ. Điểm cốt lõi là **scope + object-level policy**; không tin `accountId` người dùng tự truyền nếu không liên kết nó với principal/claim đã được xác minh.

## 7. JWT: xác minh chữ ký là cần nhưng chưa đủ

Khi RS chấp nhận JWT access token, cần phân biệt:

1. **Decode**: đọc payload Base64URL không chứng minh token đáng tin.
2. **Verify signature**: xác nhận chữ ký với khóa/thuật toán cho phép, chống token sửa nội dung.
3. **Validate claims**: kiểm `iss`, `aud`, `exp`, `nbf` (nếu có), profile và loại token phù hợp.
4. **Authorize action**: kiểm scope/authority, tenant, role và quyền trên resource.

Mẫu claims **minh họa**, không phải token đã ký:

```json
{
  "iss": "https://login.example.test",
  "sub": "alice-user-id",
  "aud": ["profile-api"],
  "scope": "profile.read",
  "iat": 1760000000,
  "exp": 1760000900
}
```

RS của Profile API cần từ chối token chỉ dành cho `payments-api` dù chữ ký đúng và scope có vẻ hợp lệ. Không dùng ID token dành cho client làm access token ở API. Chú ý **algorithm confusion**, chọn khóa từ issuer đáng tin, validate key rotation và không cho một token tự quyết định tùy ý URL lấy khóa.

Một số provider đưa authorities qua claims khác `scope` hoặc `scp`; cấu hình converter phải đúng contract, không tự suy luận rằng mọi role luôn nằm trong claim `roles`.

## 8. Spring Security thể hiện bốn vai trò ở đâu?

Spring Security là tập công cụ, không tự biến một project thành cả bốn vai trò bằng một annotation.

| Vai trò OAuth 2.0 | Trong ứng dụng Spring |
| --- | --- |
| Resource owner | Người dùng hoặc thực thể kiểm soát quyền; không phải một Java bean bắt buộc |
| OAuth2 client | `spring-boot-starter-oauth2-client`, `oauth2Login()`, `oauth2Client()`, `OAuth2AuthorizedClientManager` |
| Authorization server | **Spring Authorization Server** hoặc IdP độc lập như một sản phẩm dịch vụ; không phải `oauth2ResourceServer()` |
| Resource server | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer().jwt(...)` hoặc `opaqueToken(...)` |

### 8.1. OAuth2 Client / OAuth2 Login

Nếu ứng dụng cần **đăng nhập bằng OIDC provider**, có thể cấu hình client registration và `oauth2Login`. Nếu ứng dụng cần lấy token để gọi API bên ngoài, phần `oauth2Client`/authorized client management có trách nhiệm phù hợp. Hai use case có thể cùng tồn tại nhưng **không đồng nghĩa**.

```java
// Minh họa trong bean SecurityFilterChain của một OAuth2 Client có đăng ký IdP:
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/").permitAll()
        .anyRequest().authenticated())
    .oauth2Login(org.springframework.security.config.Customizer.withDefaults())
    .oauth2Client(org.springframework.security.config.Customizer.withDefaults());
```

Đoạn này **không phải file chạy độc lập**: cần project OAuth2 Client, `ClientRegistration` với issuer/client-id/redirect URI chính xác, cấu hình secret/PKCE và các dependency phù hợp. Đừng thêm nó vào resource server demo mục 9 rồi cho rằng đã có AS.

Spring Security hỗ trợ template callback như `/login/oauth2/code/{registrationId}` cho OAuth2 Login trong các thiết lập phổ biến. Redirect URI phải khớp giá trị đăng ký ở AS. Với reverse proxy, kiểm soát forwarded headers từ proxy đáng tin và HTTPS để tránh redirect tới host tùy ý.

### 8.2. Authorization Server

Để tự vận hành máy chủ cấp token, dùng **Spring Authorization Server** hoặc một AS/IdP được hỗ trợ. Nó phải quản lý registered clients, grants, user authentication/consent, token signing keys, authorization persistence, token issuance/revocation và endpoints.

```text
spring-boot-starter-oauth2-client
    -> Ứng dụng ĐI xin quyền/token để gọi API

spring-boot-starter-oauth2-resource-server
    -> API NHẬN Bearer access token và kiểm token

Spring Authorization Server
    -> Hệ thống PHÁT HÀNH token/grant
```

Một Resource Server **không tự phát access token** chỉ vì có Bean `JwtDecoder`. Một OAuth Client **không tự trở thành resource server** chỉ vì có `ClientRegistration`. Phân tách rõ các vai trò giúp cấu hình security và triển khai dễ audit hơn.

### 8.3. Resource Server dùng JWT

Một cấu hình phổ biến cho **JWT do AS thật cấp**:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://login.example.test
```

```java
// Đặt trong SecurityFilterChain của một Resource Server có IdP/AS thật:
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin.read")
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(org.springframework.security.config.Customizer.withDefaults()));
```

**Mã minh họa tích hợp**, không tự chạy nếu chưa có issuer, metadata/JWKS, token thật và policy tương ứng. Spring Security thường tạo `JwtDecoder` dựa trên issuer/metadata để kiểm JWT; production vẫn cần kiểm **audience**, claims đặc thù, mapping scope và action/object-level authorization theo API của mình.

### 8.4. Resource Server dùng opaque token

Với token opaque và introspection endpoint của AS:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://login.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=profile-api-introspector
# Dùng secret manager / environment, không hardcode secret vào repo.
```

Resource Server có thể sử dụng `OpaqueTokenIntrospector`; provider có thể trả trạng thái `active` và thông tin scope/principal. Introspection client secret và TLS phải được cấu hình theo API của provider; ví dụ property ở trên chưa đầy đủ credentials để chạy production.

## 9. Ví dụ runnable: một Resource Server nhận Bearer token và kiểm scope

Bài này tập trung làm rõ **ai nhận token** và **ai kiểm tra quyền**. Để ví dụ có thể chạy **không cần đăng ký một nhà cung cấp OAuth thật**, ta mô phỏng **kết quả introspection** bằng một Bean `OpaqueTokenIntrospector` *chỉ dùng trong demo local*. Nó nhận hai chuỗi thử nghiệm, biến thành principal + scope; mọi chuỗi khác bị từ chối.

**Ranh giới tuyệt đối:** Demo này **không triển khai Authorization Server**, **không phát token hợp lệ theo giao thức OAuth**, **không thực hiện Authorization Code + PKCE** và **không được deploy như cấu hình an ninh production**. Mục đích là kiểm chứng lớp Resource Server và phân quyền nhận token trên Spring Security. Với production, thay introspector giả bằng AS introspection thật hoặc chuyển sang JWT decoder/AS đáng tin.

### 9.1. Cấu trúc dự án

```text
oauth2-resource-roles-demo/
├── pom.xml
└── src/
    ├── main/java/demo/oauth/
    │   ├── OAuth2RolesApplication.java
    │   ├── SecurityConfig.java
    │   └── ProfileController.java
    └── test/java/demo/oauth/
        └── ResourceServerTest.java
```

Cần **JDK 17+**, Maven 3.9+ và cổng 8080 còn trống nếu chạy server. Spring Boot 3.5.0 được cố định để dễ tái lập; ứng dụng thật cần bản vá/phiên bản còn được hỗ trợ.

### 9.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>oauth2-resource-roles-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. Khởi động

`src/main/java/demo/oauth/OAuth2RolesApplication.java`:

```java
package demo.oauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OAuth2RolesApplication {
    public static void main(String[] args) {
        SpringApplication.run(OAuth2RolesApplication.class, args);
    }
}
```

### 9.4. Resource Server SecurityFilterChain và introspector demo

`src/main/java/demo/oauth/SecurityConfig.java`:

```java
package demo.oauth;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .hasAuthority("SCOPE_profile.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }

    /**
     * Chỉ cho demo local: giả lập kết quả introspection của AS.
     * KHÔNG sử dụng các token chuỗi cứng này trong production.
     */
    @Bean
    OpaqueTokenIntrospector demoOpaqueTokenIntrospector() {
        return token -> {
            if ("demo-alice".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                    "alice",
                    Map.of("sub", "alice", "scope", "profile.read"),
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_profile.read"))
                );
            }
            if ("demo-bob".equals(token)) {
                return new DefaultOAuth2AuthenticatedPrincipal(
                    "bob",
                    Map.of("sub", "bob", "scope", "tasks.read"),
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_tasks.read"))
                );
            }
            throw new BadOpaqueTokenException("Token not active");
        };
    }
}
```

Giải thích:

1. `STATELESS`: không dựa vào session đăng nhập để xác thực các request API; Bearer token đi cùng mỗi request.
2. `oauth2ResourceServer(...opaqueToken(...))`: dùng cơ chế Resource Server cho Bearer opaque token.
3. `OpaqueTokenIntrospector` là nơi Resource Server nhận thông tin token đã được kiểm tra. Trong demo **chỉ** hai token thử nghiệm được coi là active; không có kết nối tới Authorization Server thật.
4. Trường hợp `demo-alice` được tạo với authority `SCOPE_profile.read`; `demo-bob` chỉ có `SCOPE_tasks.read`.
5. `hasAuthority("SCOPE_profile.read")` yêu cầu scope phù hợp; dù token Bob được nhận diện, Bob vẫn không thể vào `/api/profile`.
6. `anyRequest().denyAll()` từ chối các endpoint ngoài hợp đồng ngay cả khi token hợp lệ.
7. Demo chỉ có GET read-only, **không tắt CSRF**. Với cookie-based browser flows hoặc POST/PUT/PATCH/DELETE, phải phân tích CSRF riêng; `STATELESS` không tự chứng minh ứng dụng miễn nhiễm CSRF nếu browser vẫn tự gửi credential.

**Vì sao introspector demo là ranh giới tin cậy cần đánh dấu rõ?** Trong production, chính Authorization Server phải cấp token và RS phải xác minh trạng thái bằng introspection thực hoặc decoder chuẩn. Một bảng ánh xạ token chuỗi cứng trong source *không phải* mô hình cấp token chấp nhận được và có thể làm lộ API nếu triển khai ngoài local.

### 9.5. Controller chỉ nhận principal đã xác thực

`src/main/java/demo/oauth/ProfileController.java`:

```java
package demo.oauth;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("subject", principal.getName());
    }
}
```

Controller **không đọc `Authorization` header bằng tay** và không tin username do client truyền. Spring Security đã chuyển một Bearer token hợp lệ thành `Authentication` và principal; mọi request thiếu authority bị chặn trước khi đến controller. Trong hệ thống thật cần **policy theo đối tượng** nếu trả dữ liệu nhiều user/tenant.

### 9.6. Integration tests bằng MockMvc

`src/test/java/demo/oauth/ResourceServerTest.java`:

```java
package demo.oauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteNeedsNoToken() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void privateRouteWithoutTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBearerTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void recognizedTokenWithoutScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-bob"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedTokenGetsOnlyItsOwnProfileView() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-alice"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"));
    }

    @Test
    void unapprovedPathIsForbiddenEvenWithToken() throws Exception {
        mvc.perform(get("/api/internal/secrets")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-alice"))
            .andExpect(status().isForbidden());
    }
}
```

**Đây là integration test của Resource Server demo**, không phải test thực hiện Authorization Code Flow. Sáu test tách rõ: public route, thiếu token, token không active, token có scope sai, token đủ scope và route chưa được phép. Spring Security Test hiện diện để hỗ trợ testing infrastructure; request trong các test cố tình gửi `Authorization: Bearer ...` để exercise filter thật thay vì mock sẵn Authentication.

### 9.7. Chạy ứng dụng và kiểm thử bằng curl

```bash
mvn test
mvn spring-boot:run
```

Trong terminal khác:

```bash
curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/profile
curl -i -H 'Authorization: Bearer invalid' \
  http://localhost:8080/api/profile
curl -i -H 'Authorization: Bearer demo-bob' \
  http://localhost:8080/api/profile
curl -i -H 'Authorization: Bearer demo-alice' \
  http://localhost:8080/api/profile
```

HTTP status **dự kiến** theo thứ tự là **200, 401, 401, 403, 200**; lệnh cuối trả JSON có `"subject":"alice"`. Đây là **kỳ vọng từ cấu hình và code demo**, không phải kết quả Maven/curl được thực thi trong quá trình viết bài.

**Không dùng token demo hoặc introspector giả ở môi trường production**. Khi chuyển sang AS thực, thay bằng introspection client credentials bảo mật hoặc JWT decoder chuẩn, thêm audience/issuer validation, rate limiting, object-level authorization và test token thật được phát hành qua AS.

## 10. Nếu dùng authorization server thật: những gì phải đổi?

Trong sản phẩm thật:

1. **Đăng ký client:** AS cần client ID, loại public/confidential, redirect URIs, grant types, scopes và client-authentication methods đúng.
2. **Thiết kế authorization flow:** user-facing client dùng Authorization Code + PKCE; service machine-to-machine dùng Client Credentials khi phù hợp.
3. **Định nghĩa access token contract:** issuer, audience, scope, subject/actor, TTL, resource indicators, refresh strategy và version.
4. **Kết nối RS tới AS:** JWT decoder/metadata/JWKS hoặc introspection endpoint, TLS, cache và timeout.
5. **Mapping authorities:** chuyển claims/scopes đúng sang authorities (ví dụ `SCOPE_profile.read`), áp thêm check owner/tenant.
6. **Token storage:** client tránh lộ token qua URL, browser storage không được bảo vệ, logging hoặc referrer; dùng BFF/secure cookie nếu kiến trúc phù hợp.
7. **Revocation:** logout client, refresh token rotation, AS revocation và RS validation SLA phải cùng mô tả một chính sách nhất quán.
8. **Kiểm thử trên môi trường thật:** login/consent, callback, state/PKCE, refresh, expiry, revoke, key rotation, audience mismatch, invalid scope và đối tượng không có quyền.

Đừng cố phát JWT bằng một hàm Java tự ký trong cùng ứng dụng Resource Server rồi tuyên bố đã có “OAuth2 Authorization Server”: OAuth gồm grant processing, client registration, token issuance, redirect rules, consent, key management và các điều kiện an ninh lớn hơn việc tạo chuỗi JWT.

## 11. Các lỗi nhầm vai trò thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Resource owner là resource server” | Một bên cấp phép, một bên phục vụ dữ liệu | Alice có thể cấp quyền; Profile API lưu dữ liệu |
| “Client là frontend JS” | Client có thể là backend, mobile, desktop, SPA | Xác định ranh giới client và khả năng giữ secret |
| “Authorization server và resource server phải là hai máy vật lý” | RFC mô tả role logic | Có thể cùng server, nhưng trách nhiệm khác nhau |
| “OAuth2 là giao thức login chuẩn hóa ID token” | OAuth chủ yếu về ủy quyền | Dùng OIDC nếu cần xác thực danh tính với ID token |
| “Có access token là được gọi mọi endpoint” | Token có scope/audience/lifetime | RS kiểm token và authorization trên action/resource |
| “JWT decode thành công nghĩa là hợp lệ” | Base64URL đọc được không chứng minh chữ ký | Verify signature, issuer, audience, thời hạn, scope |
| “ID token dùng làm Bearer access token cho API” | Audience và mục đích khác | Resource server nhận access token đúng API |
| “Client secret nhúng trong SPA là bảo mật” | Người dùng có thể xem mã frontend | Public client + Authorization Code + PKCE |
| “PKCE thay cho redirect URI/state/issuer checks” | PKCE chỉ giải quyết một số mối đe dọa | Kiểm đầy đủ các ràng buộc giao dịch và redirect |
| “Client Credentials cũng đại diện cho Alice” | Không có user login/consent trong grant đó | Token đại diện quyền client, không tự suy ra end-user |
| “scope=invoice.read cho xem mọi invoice” | Scope có thể quá rộng | RS kiểm tenant/owner/ACL theo từng invoice |
| “Logout trên client thu hồi JWT ngay ở mọi RS” | JWT stateless còn hạn có thể được chấp nhận | Chọn TTL/denylist/introspection/version theo SLA |
| “CORS thay cho authorization” | Non-browser caller không bị CORS chặn | OAuth bearer validation và API authorization |
| “Mọi access token phải là JWT” | OAuth không ràng buộc định dạng đó | JWT và opaque token đều có thể dùng |
| “Cần password grant vì muốn tự vẽ màn hình login” | Client phải giữ mật khẩu user, không phù hợp BCP | Dùng Authorization Code + PKCE/SSO đúng thiết kế |

## 12. Security checklist theo từng vai trò

### 12.1. Resource owner

- [ ] Hiểu ứng dụng nào xin quyền và nhóm tài nguyên nào được chia sẻ.
- [ ] Không nhập mật khẩu AS vào ứng dụng bên thứ ba giả mạo; ưu tiên redirect tới AS đáng tin cậy.
- [ ] Có khả năng xem/thu hồi quyền đã cấp theo chính sách AS và sản phẩm.
- [ ] Với thao tác rủi ro cao, sử dụng MFA/fresh authentication khi cần.

### 12.2. Client

- [ ] Đăng ký `client_id`, redirect URIs và loại client đúng.
- [ ] Dùng Authorization Code + PKCE `S256` cho flow user authorization; không dùng implicit/password grant cho thiết kế mới.
- [ ] Kiểm `state` và transaction binding, OIDC `nonce` khi phù hợp.
- [ ] Với confidential client, bảo vệ secret/khóa, rotate, chỉ dùng HTTPS.
- [ ] Không lưu access/refresh token trong URL, log hoặc nơi frontend không được bảo vệ.
- [ ] Xử lý expiry, refresh token rotation/replay, logout và lỗi từ AS có kiểm soát.

### 12.3. Authorization server

- [ ] Kiểm client registration, redirect URI, grant type và authentication phù hợp.
- [ ] Xác thực resource owner, ghi nhận consent khi cần và cấp đúng scope tối thiểu.
- [ ] Phát code một lần, ngắn hạn; kiểm PKCE và client binding.
- [ ] Ký token và quản lý khóa/`jwks` an toàn nếu dùng JWT.
- [ ] Có endpoint metadata, token, revocation/introspection theo nhu cầu thiết kế.
- [ ] Định nghĩa issuer/audience rõ ràng, chống mix-up và token substitution.
- [ ] Có audit, rate limiting và giám sát abuse mà không log token thô.

### 12.4. Resource server

- [ ] Chỉ chấp nhận token từ issuer/AS đã cấu hình.
- [ ] Kiểm signature hoặc introspection, expiry, audience và loại token phù hợp.
- [ ] Ánh xạ scope/authority đúng, từ chối method/path ngoài chính sách.
- [ ] Kiểm object-level ownership/tenant/ACL ở tầng nghiệp vụ và truy vấn.
- [ ] Không cấp quyền chỉ từ `client_id` do caller tự gửi hoặc nội dung JWT chưa verify.
- [ ] Test 401 cho thiếu/invalid token, 403 cho thiếu scope, 2xx chỉ khi có quyền.
- [ ] Định nghĩa cách xử lý revoked token, AS outage, cache stale và key rotation.
- [ ] Không đưa claims nhạy cảm hoặc Bearer token vào log/response.

## 13. Câu hỏi tự kiểm tra

**1. Trong OAuth2, ai là Resource Owner, Client, Authorization Server và Resource Server?**  
Resource owner có khả năng cấp quyền trên protected resource; client yêu cầu truy cập; AS phát token sau khi grant hợp lệ; RS cung cấp tài nguyên và kiểm access token.

**2. Alice nhập mật khẩu vào Report Dashboard để app gọi Profile API. Đây có phải flow nên ưu tiên?**  
Không. Mô hình ưu tiên redirect tới AS, cho phép Alice xác thực/consent tại AS rồi client nhận code/token, tránh client trực tiếp nhận password của resource owner.

**3. Authorization Server và Resource Server có thể cùng deployment không?**  
Có. Đây là hai vai trò logic khác nhau; vẫn phải phân biệt endpoint token/grant và API protected resource.

**4. Client Credentials có thể thay cho Authorization Code khi cần hành động thay mặt Alice không?**  
Không mặc định. Client Credentials cấp quyền cho chính client, không tự biểu thị người dùng Alice đã ủy quyền hay đang đăng nhập.

**5. Client nhận authorization code có thể dùng code đó gọi thẳng Profile API không?**  
Không. Code được client đổi ở token endpoint thành access token; resource server nhận access token.

**6. Vì sao dùng PKCE S256?**  
Để liên kết token exchange với client đã tạo authorization request, giảm rủi ro code interception/injection. PKCE không miễn yêu cầu kiểm redirect URI, state/mix-up và các ràng buộc khác.

**7. Token JWT có chữ ký hợp lệ nhưng `aud=payments-api` có được Profile API chấp nhận không?**  
Không, nếu API yêu cầu token dành cho mình. Resource server cần kiểm audience và phạm vi action.

**8. Nếu access token có scope `invoice.read`, có được đọc hóa đơn của user khác không?**  
Không tự động. Resource server phải kiểm quyền sở hữu/tenant/ACL của hóa đơn cụ thể.

**9. OAuth access token và OIDC ID token có cùng vai trò không?**  
Không. Access token hướng tới protected resource/API; ID token phục vụ client xác nhận kết quả đăng nhập trong OIDC.

**10. JWT còn hạn có tự mất hiệu lực khi client xóa token local không?**  
Không nhất thiết. Nếu RS xác minh JWT stateless mà không có revocation check, bản sao token vẫn có thể được chấp nhận tới khi hết hạn.

**11. Trong ví dụ chạy thử, `demo-alice` có phải access token OAuth hợp lệ từ Authorization Server thật không?**  
Không. Nó là chuỗi kiểm thử mà Bean introspector giả lập coi là active, chỉ nhằm thực hành Resource Server authorization.

**12. Nếu token Bob được introspector xác nhận nhưng thiếu `SCOPE_profile.read`, dự kiến API trả gì?**  
Thông thường **403 Forbidden** do thiếu authority, khác với **401 Unauthorized** cho token không hợp lệ/không có.

## 14. Tài liệu tham khảo

- [RFC 6749 – The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), đặc biệt mục **1.1 Roles**, **1.2 Protocol Flow**, authorization code/client credentials.
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, chống token/authorization code injection, client identity và không dùng password grant.
- [RFC 7636 – Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier`, `S256`, `code_challenge`.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer header và handling errors.
- [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái `active` và introspection.
- [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): cách client yêu cầu revoke token.
- [Spring Security – OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `OAuth2AuthorizedClient` và client registration.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): login bằng AS/OIDC provider và callback.
- [Spring Security – OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): JWT, opaque token, Bearer validation và authorities.
- [Spring Authorization Server](https://docs.spring.io/spring-authorization-server/reference/): vai trò cấp token, endpoint và cấu hình server.
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html): `openid` scope, ID token và authentication.
