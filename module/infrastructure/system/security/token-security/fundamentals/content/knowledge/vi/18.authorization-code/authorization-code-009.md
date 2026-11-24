# Client authentication at token endpoint

Một ứng dụng web dùng **Authorization Code + PKCE** để đăng nhập người dùng qua OAuth 2.0/OpenID Connect (OIDC). Sau khi người dùng được chuyển về ứng dụng với `code`, ứng dụng gửi yêu cầu đến **token endpoint** để đổi code lấy access token. Ở đây có hai câu hỏi bảo mật **khác nhau**:

1. **Authorization Server có thể xác minh ứng dụng đang đổi code là OAuth client nào không?** Đây là **client authentication at token endpoint**.
2. **Người gửi yêu cầu đổi code có chứng minh mình biết `code_verifier` gắn với authorization request ban đầu không?** Đây là **PKCE verification**.

Với **confidential client** như backend/BFF có khả năng bảo vệ bí mật hoặc private key, Authorization Server (AS) thường **phải xác thực OAuth client** tại token endpoint bằng phương thức đã đăng ký, chẳng hạn `client_secret_basic`, `private_key_jwt` hoặc mutual TLS. Với **public client** như ứng dụng chạy trong browser hoặc ứng dụng mobile, client không thể giữ một shared client secret lâu dài bí mật với người dùng thiết bị; AS vẫn phải **ràng buộc authorization code với `client_id`, `redirect_uri` khi áp dụng và PKCE**, nhưng không được xem việc client chỉ gửi `client_id` là một bằng chứng xác thực client.

Nếu AS cấp access token chỉ vì một bên biết authorization code nhưng **không kiểm đúng client, PKCE và các ràng buộc của code**, kẻ tấn công có thể tìm cách đổi code bị chặn/đánh cắp hoặc dùng sai client. Nếu client authentication đúng nhưng AS **không kiểm `aud`, `scope` và grant**, token vẫn có thể bị cấp sai quyền. Các lớp bảo vệ này **bổ sung nhau**, không thay thế nhau.

Bài thuộc chương **Authorization Code** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, tập trung đúng chủ đề **Client authentication at token endpoint**. Kiến thức liên hệ mô hình tin cậy OAuth 2.0/OIDC, JWT và opaque token, access/refresh token, kiểm claims, scope, audience, lưu trữ, thu hồi và chống đánh cắp hoặc phát lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích client authentication tại token endpoint là gì, xảy ra lúc nào trong Authorization Code flow và khác với authentication của **resource owner**.
2. Phân biệt **confidential client** và **public client**, cùng lý do không được nhúng client secret vào SPA/mobile như một bí mật đáng tin.
3. Phân biệt **client authentication**, **client identification**, **PKCE**, **authorization code binding** và **sender-constrained tokens**.
4. So sánh `client_secret_basic`, `client_secret_post`, `client_secret_jwt`, `private_key_jwt`, `tls_client_auth` và `none`.
5. Phân tích token request/response HTTP, cấu trúc client assertion JWT, xác thực mTLS và các mã lỗi OAuth.
6. Mô tả thứ tự AS cần kiểm client, authorization code, redirect URI, PKCE, grant và quyền trước khi cấp token.
7. Thiết kế bảo vệ secret/private key, rotation, cấu hình discovery/registration, audit và phòng chống token leak/replay.
8. Cấu hình hoặc kiểm thử ví dụ Spring Authorization Server, phát hiện code substitution, client impersonation và downgrade authentication.

## 2. Client authentication là gì?

Trong OAuth 2.0, **OAuth client** là ứng dụng muốn truy cập tài nguyên được bảo vệ, thường thay mặt người dùng hoặc theo quyền dịch vụ đã được cấp. Khi client gọi token endpoint, AS cần xác định **client đã đăng ký** nào đang tham gia và, nếu client có khả năng xác thực, kiểm chứng **bằng chứng xác thực client** đó.

### 2.1. Bốn vai trò trong luồng

| Vai trò | Trách nhiệm | Có phải bên được xác thực tại token endpoint không? |
|---|---|---|
| **Resource Owner (RO)** | Chủ thể có thẩm quyền cho phép truy cập tài nguyên; trong flow người dùng thường là end user. | Không trực tiếp là OAuth client. Người dùng được xác thực qua Authorization Server/OP trong luồng authorization. |
| **OAuth Client** | Ứng dụng nhận code, trình code và PKCE verifier, đồng thời có thể trình client credentials. | **Có** với confidential client; public client chỉ có thể được nhận diện/binding theo phương thức thích hợp. |
| **Authorization Server (AS)** | Phát authorization code, xác thực client/grant và phát token. | Là bên **xác thực client**, không phải caller cần tự chấp nhận secret của mình. |
| **Resource Server (RS)** | Nhận access token và bảo vệ API theo issuer, audience, scope, expiry, object-level policy. | **Không** phải token endpoint của Authorization Code flow; nó không nhận client secret hoặc authorization code. |

Phải tách ba kiểu xác thực/ủy quyền:

- **User authentication:** AS/OP xác minh người dùng qua passkey, mật khẩu, MFA, SSO, v.v.
- **Client authentication:** AS xác minh confidential client đang dùng đúng secret/private key/chứng chỉ đã đăng ký.
- **Resource authorization:** RS kiểm access token và quyền đối với request cụ thể.

Một client được xác thực **không có nghĩa** client được cấp `scope=payments:refund` hoặc được truy cập mọi tenant. Ngược lại, user đã đăng nhập/MFA đúng **không thay** client authentication của một backend confidential client.

### 2.2. `client_id` chỉ là định danh, không phải secret

Ví dụ `client_id=shop-bff` giúp AS tra client registration. Nhưng một attacker cũng có thể biết `shop-bff` từ JavaScript, URL hoặc metadata công khai. **Chỉ biết client ID không chứng minh người gửi request là backend shop-bff**.

Với confidential client, AS phải kiểm một **authentication method đã đăng ký** trước khi cho đổi code. Với public client, AS không có bí mật client đáng tin như vậy; AS phải kiểm chặt code binding/PKCE và không tự nâng niềm tin vào `client_id`.

### 2.3. Token endpoint khác authorization endpoint

~~~text
Authorization endpoint:
  /authorize
  -> Người dùng tương tác với AS/OP.
  -> AS phát authorization code cho client qua redirect URI.

Token endpoint:
  /token hoặc /oauth2/token, theo AS configuration
  -> OAuth client trực tiếp gửi code và code_verifier.
  -> Confidential client xác thực bằng phương thức đã đăng ký.
  -> AS kiểm code/client/redirect/PKCE, sau đó cấp token nếu được phép.

Resource Server:
  /api/orders/42
  -> Client gửi access token (Bearer hoặc sender-constrained).
  -> API kiểm token, scope, audience và quyền trên bản ghi.
~~~

**Không gửi client secret, private key hoặc authorization code đến Resource Server**. Những dữ liệu này thuộc luồng với AS, không phải bằng chứng phân quyền của API.

## 3. Authorization Code flow: điểm đặt client authentication

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as OAuth Client / BFF
    participant AS as Authorization Server / OP
    participant RS as Orders Resource Server
    U->>B: Chọn đăng nhập
    B->>C: GET /login
    C->>C: Tạo state, PKCE verifier + challenge
    C-->>B: Redirect sang /authorize
    B->>AS: Authorization request (client_id, redirect_uri, state, challenge)
    AS->>U: Xác thực và xin consent nếu cần
    U-->>AS: Hoàn tất tương tác
    AS-->>B: Redirect về callback với code và state
    B->>C: GET /callback?code=...&state=...
    C->>C: Kiểm state và ràng buộc callback
    C->>AS: POST /token: code, redirect_uri, code_verifier + client authentication
    AS->>AS: Xác thực client theo registration
    AS->>AS: Kiểm code one-time, client binding, redirect_uri và PKCE
    AS-->>C: Access token và token khác nếu chính sách cho phép
    C->>RS: Access token dành cho orders-api
    RS->>RS: Kiểm iss, aud, scope, time, resource policy
    RS-->>C: Kết quả
~~~

**Điểm bắt buộc nhận ra:** client authentication diễn ra ở yêu cầu **POST tới token endpoint**, *sau khi* client đã nhận authorization code. PKCE proof cũng được kiểm tại bước này, nhưng **PKCE và client authentication là hai phép kiểm khác nhau**.

### 3.1. Trước token request: authorization code được ràng buộc như thế nào?

Khi phát authorization code, AS cần lưu hoặc bảo vệ thông tin ngữ cảnh, chẳng hạn:

~~~text
authorization_code_record:
  code_hash:          ...
  client_id:          shop-bff
  redirect_uri:       https://shop.example.com/login/oauth2/code/shop
  code_challenge:     BASE64URL(SHA256(original_code_verifier))
  challenge_method:   S256
  subject:            user-742
  approved_scope:     orders:read
  approved_resource:  orders-api
  issued_at:          ...
  expires_at:         ...
  status:             UNUSED
~~~

Đây là **schema minh họa**, không phải cấu trúc bắt buộc của mọi AS. Mục tiêu là khi code được đem đổi, AS có đủ thông tin để xác minh **đúng client, đúng redirect URI khi đã chỉ định, đúng PKCE và chỉ một lần sử dụng**.

Authorization code nên **ngắn hạn**, khó đoán và dùng một lần; nếu client đổi code khác client ban đầu hoặc code đã được sử dụng, AS phải từ chối.

### 3.2. Authorization request ví dụ

~~~http
GET /oauth2/authorize?response_type=code&
  client_id=shop-bff&
  redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&
  scope=openid%20orders%3Aread&
  resource=https%3A%2F%2Fapi.example.com%2Forders&
  state=RANDOM_STATE_EXAMPLE&
  code_challenge=BASE64URL_SHA256_VERIFIER_EXAMPLE&
  code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

Request được xuống dòng để dễ đọc. Trong thực tế nó phải là **một URL đã encode hợp lệ qua HTTPS**. `state` phải được sinh, lưu và kiểm đúng ngữ cảnh; `code_challenge` phải thực sự được tính từ `code_verifier` đủ ngẫu nhiên theo RFC 7636. `resource` thuộc RFC 8707 và chỉ dùng khi AS hỗ trợ.

**Không** truyền client secret trong authorization URL; browser history, referrer, log, extension và proxy có thể thu thập URL. Client authentication diễn ra tại **token endpoint** theo cơ chế phù hợp.

## 4. Confidential client và public client

### 4.1. Phân loại theo khả năng bảo vệ credentials

| Loại client | Ví dụ | Khả năng bảo vệ secret | Cách xử lý ở token endpoint |
|---|---|---|---|
| **Confidential web backend/BFF** | `shop-bff` chạy trên server do tổ chức kiểm soát | Có thể giữ secret/private key/chứng chỉ ngoài quyền truy cập trực tiếp của user/browser. | AS xác thực client bằng phương thức được đăng ký, đồng thời kiểm code/PKCE. |
| **Confidential service** | Server daemon/cổng tích hợp | Có thể bảo vệ credentials bằng secret manager/HSM hoặc mTLS. | AS xác thực ở token endpoint cho grant được cho phép; Authorization Code chỉ dùng nếu có tương tác tương ứng. |
| **Public browser SPA** | JavaScript chạy trong trình duyệt | Bất kỳ secret dài hạn nhúng vào JS đều có thể bị đọc. | `token_endpoint_auth_method=none` hoặc cơ chế tương ứng; AS kiểm `client_id`, code binding, PKCE và policy. |
| **Public native/mobile app** | App phân phối đến điện thoại/desktop người dùng | Không thể bảo vệ một embedded shared client secret như backend. | Nhận diện client, kiểm redirect URI/PKCE; có thể bổ sung khóa/binding theo profile nhưng không biến secret nhúng thành secret đáng tin. |
| **Thiết bị hạn chế đầu vào** | TV/IoT tùy grant | Khả năng khác nhau theo phần cứng | Dùng grant/client type thích hợp; không áp Authorization Code flow một cách máy móc. |

**Confidential/public không phụ thuộc tuyệt đối vào ứng dụng có giao diện hay không** mà phụ thuộc việc AS có thể dựa vào phương thức bảo vệ credential của client hay không. Cùng một sản phẩm có thể gồm **BFF confidential client** phía server và **public browser** chỉ giữ session cookie.

### 4.2. Vì sao không nhúng `client_secret` trong SPA/mobile?

Nếu code bundle có:

~~~javascript
// VÍ DỤ SAI: không nhúng shared client secret vào public app.
const clientId = "shop-mobile";
const clientSecret = "HARD_CODED_SECRET_EXAMPLE";
~~~

người dùng hoặc attacker có thể đọc source/binary, giải mã, hook runtime hoặc trích xuất network request. Việc obfuscate không biến giá trị đó thành **bí mật chỉ backend và AS biết**.

Nếu AS xử lý secret này như confidential-client authentication, một bản sao app có thể mạo danh client. Hãy đăng ký đúng **public client** và dùng Authorization Code + PKCE, redirect URI an toàn và chính sách refresh token tương ứng. Có thể dùng cơ chế chứng minh sở hữu khóa/attestation bổ sung nếu được thiết kế và hỗ trợ, nhưng phải đánh giá riêng.

### 4.3. Confidential client vẫn cần PKCE?

**Có thể và nên dùng cả hai**. Client authentication chứng minh backend đang gọi token endpoint bằng credential hợp lệ; PKCE chứng minh người đổi authorization code biết verifier được gắn với yêu cầu khởi tạo. Chúng giảm **các lớp tấn công khác nhau**.

Với public client, PKCE là tuyến bảo vệ quan trọng vì không có shared client secret đáng tin. Với confidential client, client authentication **không làm PKCE trở nên vô nghĩa**: nó có thể giảm nguy cơ code injection/interception trong những tình huống khác.

## 5. Các phương thức xác thực client tại token endpoint

OAuth/OIDC định nghĩa hoặc mở rộng nhiều `token_endpoint_auth_method`. Client phải dùng **phương thức được đăng ký và được AS hỗ trợ**; không tự thử ngẫu nhiên tới khi một cách nào đó thành công.

| Method | Bằng chứng | Thích hợp cho | Lưu ý |
|---|---|---|---|
| `client_secret_basic` | Client ID và secret trong HTTP Basic Authorization header. | Confidential client có shared secret. | Rộng rãi trong OAuth 2.0; cần TLS, xử lý Basic encoding đúng và tránh log header. |
| `client_secret_post` | `client_id` và `client_secret` trong form body của token request. | Chỉ khi AS/provider cho phép, ví dụ tương thích legacy. | Secret dễ lọt vào body logging; OAuth khuyến nghị không dùng nếu có lựa chọn tốt hơn. |
| `client_secret_jwt` | JWT assertion được ký bằng **shared client secret**. | Confidential client với JWT assertion/HMAC policy. | Phải kiểm HS algorithm, audience, exp và binding; cùng rủi ro quản lý shared secret. |
| `private_key_jwt` | JWT assertion được ký bằng **private key** của client. | Confidential client có key pair/JWKS. | AS xác minh bằng public key đã đăng ký; hỗ trợ key rotation và chống replay. |
| `tls_client_auth` | Chứng chỉ client được xác thực bằng mutual TLS. | Confidential service có PKI/mTLS. | AS ràng buộc cert với client registration; cần bảo vệ TLS termination/proxy. |
| `self_signed_tls_client_auth` | Chứng chỉ client self-signed được khớp với public key/cert đã đăng ký theo profile. | Confidential client quản lý chứng chỉ riêng. | Không tự tin mọi cert tự ký; phải có trust/binding cụ thể. |
| `none` | **Không có client authentication**. | Public client đăng ký `none`. | AS vẫn kiểm `client_id`/authorization code binding/PKCE; không coi client ID là secret. |

**Lưu ý phạm vi tiêu chuẩn:** `client_secret_basic` và `client_secret_post` có trong OAuth 2.0; các method JWT client assertion liên quan RFC 7523/OIDC, còn mTLS ở RFC 8705. Việc hỗ trợ phương thức cụ thể phụ thuộc metadata/cấu hình AS. Có thể có cơ chế mở rộng khác ngoài bảng.

### 5.1. Không dùng hai phương thức đồng thời

OAuth 2.0 không cho client dùng **nhiều hơn một** phương thức xác thực trong một token request. Ví dụ vừa gửi HTTP Basic của client A, vừa gửi `client_secret` của client B trong body là tín hiệu mâu thuẫn/không hợp lệ; AS phải xử lý an toàn thay vì lựa chọn tùy tiện.

**Không cho phép fallback từ confidential sang `none`** khi secret sai. Đây là lỗi *authentication downgrade* nguy hiểm.

### 5.2. AS biết method được phép từ đâu?

Một cách tổ chức thường gặp:

~~~yaml
# Chính sách mô tả, KHÔNG phải cấu hình trực tiếp của thư viện.
clients:
  shop-bff:
    type: confidential
    tokenEndpointAuthMethod: client_secret_basic
    grants: [authorization_code, refresh_token]
    redirectUris:
      - https://shop.example.com/login/oauth2/code/shop
    requirePkce: true
    allowedAudiences: [orders-api]
    allowedScopes: [openid, orders:read]

  shop-spa:
    type: public
    tokenEndpointAuthMethod: none
    grants: [authorization_code]
    redirectUris:
      - https://spa.example.com/callback
    requirePkce: true
    allowedAudiences: [orders-api]
    allowedScopes: [openid, orders:read]

  billing-bff:
    type: confidential
    tokenEndpointAuthMethod: private_key_jwt
    grants: [authorization_code, refresh_token]
    requirePkce: true
    clientJwksUri: https://billing.example.com/oauth-jwks.json
~~~

Đây là **registration/policy minh họa**, không phải YAML chạy được với Spring. Method đăng ký, client type, grant, redirect URI, resource/scope và yêu cầu PKCE phải được kiểm **theo cùng một client**, tránh trộn quyền của nhiều client.

### 5.3. Authorization Server metadata

AS có thể công bố metadata theo **RFC 8414** hoặc OIDC Discovery, bao gồm các endpoint và `token_endpoint_auth_methods_supported` nếu được hỗ trợ. Client cần dùng metadata từ **issuer đã tin cậy**, không lấy một `token_endpoint` URL tùy ý từ request người dùng.

Ví dụ:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/oauth2/jwks",
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt",
    "tls_client_auth"
  ]
}
~~~

**Supported** không đồng nghĩa **mọi client đều có quyền dùng** cả ba cách. Phương thức được đăng ký cho từng client vẫn là ràng buộc riêng. `jwks_uri` của AS thường dùng cho khóa phát hành/metadata phía AS; nó **không tự là nơi AS lấy public key của client** để xác minh `private_key_jwt` — cần cấu hình key của client tương ứng.

## 6. `client_secret_basic`: HTTP Basic tại token endpoint

Đây là phương thức phổ biến với **confidential client** có secret:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <BASE64_OF_PROPERLY_ENCODED_CLIENT_ID_AND_SECRET>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code&
code=AUTH_CODE_EXAMPLE&
redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&
code_verifier=ORIGINAL_RANDOM_PKCE_VERIFIER
~~~

Các đoạn trong dấu ngoặc nhọn/chữ hoa là **placeholder không dùng được ngoài demo**. Dùng HTTPS thật và một form body được URL-encode hợp lệ, không đưa token/secret trong query string.

### 6.1. Basic secret được tạo như thế nào?

Theo **RFC 6749 `2.3.1**, với OAuth client sử dụng HTTP Basic, giá trị `client_id` và `client_secret` được **application/x-www-form-urlencoded encode riêng** trước khi ghép:

~~~text
encodedClientId = formUrlEncode(client_id)
encodedSecret   = formUrlEncode(client_secret)
credentials     = encodedClientId + ":" + encodedSecret
basicValue      = Base64(UTF8(credentials))

HTTP header:
  Authorization: Basic <basicValue>
~~~

Đừng chỉ tự ghép raw text và Base64 nếu `client_id`/secret có ký tự đặc biệt như dấu `:`, dấu `+` hoặc khoảng trắng; hãy dùng OAuth client library đã hỗ trợ chuẩn thay vì tự viết Basic handling.

**Base64 không mã hóa secret.** Chỉ TLS bảo vệ credential trên đường truyền; server/proxy/tracing vẫn có thể rò secret nếu ghi raw `Authorization`. Không log `client_secret`, header Basic hoặc chuỗi Base64.

### 6.2. AS kiểm Basic như thế nào?

AS cần:

1. Parse header Basic đúng giao thức và giới hạn kích thước.
2. Xác định client registration và method `client_secret_basic` đã được cho phép.
3. Kiểm secret bằng phương pháp an toàn, không tiết lộ secret hoặc khác biệt “client ID tồn tại” quá mức.
4. Kiểm client active, grant `authorization_code` được đăng ký và code phát hành cho đúng client.
5. Kiểm redirect URI/code PKCE như phần sau, rồi mới phát token.

Có một secret hợp lệ **không có nghĩa** mọi code đều được đổi. Code được phát cho `shop-spa` không được dùng bởi `shop-bff` kể cả `shop-bff` tự xác thực thành công.

### 6.3. Vì sao không gửi client secret trong URL?

Ví dụ cần **tránh tuyệt đối**:

~~~http
POST /oauth2/token?client_id=shop-bff&client_secret=LEAKED_EXAMPLE HTTP/1.1
Host: login.example.com
~~~

Query string có thể lọt vào browser history, reverse proxy access log, trace `url.full`, analytics và gateway. Token endpoint có thể ghi dấu từ HTTP stack trước khi app redact. Credentials phải nằm trong cơ chế auth được AS hỗ trợ **qua TLS**, không đưa ra URL.

## 7. `client_secret_post` và vấn đề body logging

Với một AS hỗ trợ legacy/provider-specific method `client_secret_post`:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code&
code=AUTH_CODE_EXAMPLE&
redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&
code_verifier=ORIGINAL_RANDOM_PKCE_VERIFIER&
client_id=shop-bff&
client_secret=SECRET_EXAMPLE_ONLY
~~~

Đừng dùng ví dụ này nếu client đã đăng ký `client_secret_basic`; **không tự gửi cả Basic và form-body secret**.

OAuth 2.0 cho phép cách truyền client credentials trong request body với một số điều kiện nhưng **không khuyến nghị** khi có cách tốt hơn. Lý do thực tế:

- Token endpoint form body rất dễ bị request logging/debug middleware ghi toàn bộ.
- Lỗi HTTP client có thể đính kèm raw form vào exception/message/trace.
- Một reverse proxy hoặc APM cấu hình body capture có thể lưu secret trong telemetry.
- Thay secret qua URL hoặc JSON tùy ý không phải phương án thay thế đúng giao thức.

Nếu phải hỗ trợ method này, đặt **deny-by-default body logging** cho token endpoint, bảo vệ telemetry ở cả app, proxy và collector, giới hạn quyền và retention. Thường ưu tiên `client_secret_basic` hoặc phương thức mạnh hơn phù hợp provider và kiến trúc.

## 8. `private_key_jwt`: xác thực bằng JWT client assertion

Thay vì chia sẻ client secret lâu dài với AS, confidential client có thể giữ **private key** và đăng ký **public key/JWKS** tin cậy để AS xác minh JWT được ký bằng private key đó.

### 8.1. Token request minh họa

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code&
code=AUTH_CODE_EXAMPLE&
redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&
code_verifier=ORIGINAL_RANDOM_PKCE_VERIFIER&
client_id=shop-bff&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_JWT_EXAMPLE
~~~

`client_assertion` là một **JWT do client ký để xác thực tại AS**, **không phải** access token do AS phát cho Resource Server, và cũng **không phải** OIDC ID token xác thực end user.

### 8.2. Claims tiêu biểu trong client assertion

Protected JWS header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "shop-bff-signing-key-2026"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "shop-bff",
  "sub": "shop-bff",
  "aud": "https://login.example.com/oauth2/token",
  "iat": 1893452400,
  "exp": 1893452460,
  "jti": "assertion-req-92c1"
}
~~~

Quy tắc cần hiểu:

| Trường | Vai trò | Cách xác minh |
|---|---|---|
| `iss` | Issuer của client assertion, thường là **client ID** theo profile client authentication. | AS kiểm trùng client đã đăng ký. |
| `sub` | Subject của assertion, **client ID** khi dùng JWT để client authentication. | AS kiểm phù hợp cùng client, không phải end-user `sub`. |
| `aud` | AS/token endpoint audience được hai bên thống nhất theo RFC 7523/profile. | So khớp chính xác với giá trị AS chấp nhận; không nhầm audience của Resource Server. |
| `exp` | Hạn hiệu lực assertion. | Phải hợp lệ, ngắn theo chính sách; không chấp nhận assertion quá hạn. |
| `iat` / `nbf` | Thời điểm phát hành/chưa có hiệu lực nếu dùng. | Kiểm hợp lý với clock skew. |
| `jti` | Định danh assertion để phát hiện replay nếu được dùng. | AS nên cache/reject assertion ID đã dùng trong cửa sổ thích hợp. |
| `kid` | Hỗ trợ chọn public key của client. | Chọn trong tập **khóa client đã tin**; không tải URL không tin từ assertion. |
| `alg` | Thuật toán ký. | Cho phép danh sách thuật toán đã đăng ký; không tin lựa chọn tùy ý từ header. |

**Chi tiết về `aud`:** một số profile sử dụng URL token endpoint, một số cho phép định danh AS phù hợp metadata; **client và AS phải thống nhất giá trị được chấp nhận**. Không sao chép `aud=orders-api` của access token vào client assertion, vì assertion dành cho **AS**, không phải Orders API.

### 8.3. JWT client assertion không được biến thành shared bearer secret dài hạn

Mỗi request cần assertion có thời hạn ngắn và, theo chính sách, `jti` duy nhất chống replay. Nếu client gửi lại cùng assertion quá lâu, kẻ sao chép nó có thể cố sử dụng tại token endpoint. AS phải:

1. Kiểm signature bằng **public key đã đăng ký cho đúng client**.
2. Kiểm `iss`/`sub`/`aud`/`exp` và các claim bắt buộc theo profile.
3. Kiểm thuật toán trong allowlist, không nhận `alg=none` hoặc key confusion.
4. Kiểm `jti` chống replay khi policy yêu cầu, giới hạn tần suất và cửa sổ sử dụng.
5. Kiểm client state, grant và **authorization code binding** độc lập.
6. Rotate key và xử lý `kid`/JWKS overlap theo chính sách được công bố.

**Không chọn public key bằng URL tùy ý trong header assertion**, như `jku`/`x5u` do client gửi, mà không có trust boundary và allowlist rõ ràng. Một client có nhiều key cần key rotation có kiểm soát, không mở đường tự tin một public key do attacker cung cấp.

### 8.4. `client_secret_jwt` khác gì?

`client_secret_jwt` cũng dùng JWT assertion, nhưng ký bằng **shared secret** (thường thuật toán HMAC theo profile) thay vì private key riêng. Vì AS cũng có secret tương ứng, cả hai bên có thể tạo chữ ký; không có tính tách biệt public/private key như `private_key_jwt`.

Nó vẫn là **client authentication** và yêu cầu kiểm `iss`, `sub`, `aud`, `exp`, thuật toán, chống replay/cửa sổ thời gian. Đừng nhầm client assertion với JWT access token của user chỉ vì cả hai cùng có ba đoạn Base64URL.

## 9. Mutual TLS: `tls_client_auth` và `self_signed_tls_client_auth`

Với **mutual TLS (mTLS)**, client chứng minh sở hữu private key tương ứng với một client certificate trong quá trình thiết lập kết nối TLS; AS xác định chứng chỉ đó có **khớp client đã đăng ký** hay không.

Hai cách phổ biến trong RFC 8705:

- `tls_client_auth`: AS xác thực chứng chỉ khách theo PKI/trust policy và các thuộc tính đăng ký phù hợp.
- `self_signed_tls_client_auth`: client dùng chứng chỉ tự ký nhưng **phải được khớp** với chứng chỉ/public key đã đăng ký; không có nghĩa AS tự tin mọi chứng chỉ self-signed.

### 9.1. Một request mTLS không chứa client secret trong form

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=AUTH_CODE_EXAMPLE&
redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&
code_verifier=ORIGINAL_RANDOM_PKCE_VERIFIER&
client_id=shop-bff
~~~

**Bằng chứng mTLS không nằm trong body ví dụ**: nó nằm ở TLS handshake và chứng chỉ được AS/trusted TLS termination xác minh. AS cần ánh xạ **đúng chứng chỉ ↔ đúng client**; `client_id` trong body vẫn chỉ là định danh được ràng buộc với chứng chỉ, không tự là bằng chứng xác thực.

### 9.2. Cẩn thận với reverse proxy/TLS termination

Nếu mTLS kết thúc ở gateway trước AS:

- Chỉ tin thông tin client certificate do **proxy tin cậy và đã xác thực** chuyển tới.
- Không tin raw header như `X-Client-Cert` từ Internet nếu attacker có thể tự gửi.
- Bảo vệ kết nối proxy–AS và cấu hình đúng chain of trust, header removal/overwrite.
- Kiểm certificate revocation/rotation, mapping và trạng thái client theo chính sách.
- Không nhầm client certificate của **client authentication** với certificate-bound **access token**: nếu RS cần sender-constrained token, RS cũng phải kiểm binding tương ứng.

### 9.3. mTLS và DPoP có thay PKCE không?

Không. **mTLS** ở token endpoint có thể dùng cho client authentication, hoặc có thể dùng ràng buộc access token với chứng chỉ theo profile. **DPoP (RFC 9449)** chứng minh sở hữu khóa cho request và có thể ràng buộc token theo chính sách; nó **không tự biến public client thành confidential client có shared secret** và không thay PKCE/code binding.

Trong Authorization Code flow, **PKCE kiểm một ràng buộc cụ thể của code**. Một hệ thống có thể cần đồng thời PKCE, client authentication và sender-constrained access token để giải quyết các rủi ro khác nhau.

## 10. PKCE và client authentication giải quyết hai bài toán khác nhau

Đây là phần cốt lõi: **không đánh đồng** PKCE, client identification, client authentication và kiểm access token ở Resource Server.

| Cơ chế | Bằng chứng | Phòng rủi ro chính | Có xác thực client không? |
|---|---|---|---|
| `client_id` | Định danh client đã đăng ký. | Tra registration, ràng buộc authorization code với client. | **Không**: client ID không phải secret. |
| **PKCE S256** | Người đổi code biết `code_verifier` khớp challenge ban đầu. | Chỉ lấy được authorization code thì chưa đủ để đổi code. | **Không phải OAuth client authentication**; ràng buộc một giao dịch authorization. |
| `client_secret_basic` | Biết shared client secret được AS đăng ký. | Mạo danh confidential client. | **Có**. |
| `private_key_jwt` | Ký client assertion bằng private key, AS kiểm public key đã đăng ký. | Mạo danh client không có private key và replay assertion khi có kiểm phù hợp. | **Có**. |
| mTLS client authentication | Trình certificate và chứng minh private key trong TLS handshake. | Mạo danh confidential client. | **Có** khi dùng đúng client authentication profile. |
| DPoP | Proof ký với khóa bên gửi, ràng buộc request/token theo chuẩn. | Hạn chế sử dụng bản sao token thiếu khóa. | **Không tự là confidential client authentication**. |
| RS access-token validation | Chữ ký/introspection, issuer, audience, expiry, scope, quyền. | Dùng token sai API, sai quyền, hết hạn. | Không: đây là xác minh token và phân quyền API. |

### 10.1. Nếu authorization code bị đánh cắp thì sao?

Giả sử attacker chỉ lấy được `code=C1`:

- Với public client có **PKCE S256**, attacker không biết `code_verifier=V1`, nên AS phải từ chối yêu cầu đổi code không có hoặc sai verifier.
- Với confidential client dùng **PKCE + client authentication**, attacker còn phải có credential hợp lệ của client để vượt lớp xác thực client.
- Nếu client làm lộ **cả code và verifier**, hoặc AS bỏ kiểm code/client binding, vẫn có rủi ro. PKCE không khắc phục mọi tấn công.
- Nếu backend bị compromise và attacker lấy được cả client secret/private key, phải dựa thêm vào TLS, key protection, token binding, monitoring và revocation.

**Không có một phép kiểm nào thay thế tất cả những phép còn lại.** Client authentication, PKCE, redirect URI, one-time code, state/issuer binding và token validation bổ sung nhau.

### 10.2. Java: sinh PKCE verifier và S256 challenge

Đoạn code minh họa **PKCE**, không phải client authentication:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class Pkce {
    private static final SecureRandom RANDOM = new SecureRandom();

    private Pkce() {}

    public static String newVerifier() {
        byte[] random = new byte[32];
        RANDOM.nextBytes(random);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(random);
    }

    public static String s256Challenge(String verifier)
            throws NoSuchAlgorithmException {
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }
}
~~~

Ví dụ 32 byte ngẫu nhiên trở thành `code_verifier` dài 43 ký tự Base64URL không padding. Client tính `code_challenge=S256(verifier)` rồi gửi challenge trong authorization request; **chỉ khi đổi code** mới gửi verifier. AS tính lại và so khớp với challenge đã ràng buộc code.

Không log verifier, không đưa verifier vào authorization URL và không dùng một verifier cố định cho mọi lần đăng nhập. Trong dự án thật, **ưu tiên thư viện OAuth có hỗ trợ PKCE chuẩn** thay vì tự viết các phần giao thức.

## 11. So sánh hai token requests: confidential và public

Giả sử AS đăng ký:

~~~text
Client shop-bff:
  type = confidential
  token endpoint auth method = client_secret_basic
  grant = authorization_code
  redirect URI = https://shop.example.com/login/oauth2/code/shop
  PKCE = S256

Client shop-spa:
  type = public
  token endpoint auth method = none
  grant = authorization_code
  redirect URI = https://spa.example.com/callback
  PKCE = S256
~~~

### 11.1. Backend confidential: Basic + PKCE

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <VALID_BASIC_AUTH_FOR_shop-bff>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=CODE_ISSUED_TO_shop-bff&
redirect_uri=https%3A%2F%2Fshop.example.com%2Flogin%2Foauth2%2Fcode%2Fshop&
code_verifier=VERIFIER_BOUND_TO_THIS_CODE
~~~

AS xác thực `shop-bff` từ Basic, rồi kiểm **authorization code thực sự thuộc shop-bff**, redirect URI đúng và verifier khớp.

### 11.2. SPA public: `none` + PKCE

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=CODE_ISSUED_TO_shop-spa&
client_id=shop-spa&
redirect_uri=https%3A%2F%2Fspa.example.com%2Fcallback&
code_verifier=VERIFIER_BOUND_TO_THIS_CODE
~~~

Không có client secret. AS dùng `client_id` để nhận diện client public, kiểm `none` được đăng ký, code được cấp cho **chính client này**, redirect URI và PKCE.

### 11.3. Đổi code giữa hai client phải bị từ chối

Nếu `shop-bff` xác thực Basic thành công nhưng gửi `CODE_ISSUED_TO_shop-spa`, AS phải **từ chối**. Nếu `shop-spa` gửi code của `shop-bff`, AS cũng phải từ chối. Việc biết `client_id` hay URI callback **không** chứng minh sở hữu một code đã được cấp cho client khác.

Client authentication trả lời **client đang gọi là ai**; code binding trả lời **authorization code này được cấp cho client nào**.

### 11.4. Không dùng chung một secret giữa nhiều client

Mỗi confidential client nên có registration, credential, scopes/grants và vòng đời rotation riêng phù hợp. Public client không trở thành confidential chỉ vì chứa cùng secret trong JavaScript/binary. Một secret dùng chung tạo blast radius lớn khi lộ và làm khó thu hồi theo client.

## 12. Authorization Server xử lý token request như thế nào?

Khi nhận request Authorization Code Grant, AS phải kiểm đủ các lớp trước khi trả thành công.

### 12.1. Các bước kiểm

1. **Nhận request qua TLS**, đúng token endpoint, HTTP POST và `Content-Type`/form encoding theo quy tắc; giới hạn kích thước/rate.
2. **Phát hiện chính xác một** client authentication method: Basic, form secret, JWT assertion, mTLS hoặc `none` theo client registration. Không chọn tùy tiện khi có nhiều credential mâu thuẫn.
3. **Tra client registration** active, kiểm confidential/public type, authentication method, grant `authorization_code` được cho phép.
4. **Xác thực confidential client** bằng secret, JWT assertion hoặc certificate đã đăng ký; với public client, nhận diện client nhưng không giả vờ `client_id` là mật khẩu.
5. **Tra authorization code** chưa hết hạn, chưa được đổi và **thuộc client đang gửi request**.
6. **Kiểm `redirect_uri`** theo binding code/authorization request và quy tắc giao thức.
7. **Kiểm PKCE verifier** so với challenge của code; không bỏ PKCE vì secret đã đúng.
8. **Bảo đảm code được tiêu thụ một lần** với thao tác trạng thái nguyên tử.
9. **Kiểm grant, principal, resource, scope, audience và security policy** đã được ủy quyền ban đầu.
10. **Phát token** đúng issuer, audience, scope, TTL và token profile; trả response không cache, không log secrets.

Thứ tự thực hiện ở AS có thể được tối ưu khác nhau để chống enumeration và đảm bảo transaction, nhưng **mọi điều kiện bắt buộc phải đạt** trước khi token được cấp hợp lệ.

### 12.2. Pseudocode

~~~text
function redeemAuthorizationCode(request, tlsContext):
    require HTTPS POST to configured token endpoint
    require request.grant_type == "authorization_code"

    authMethod = detectClientAuthenticationMethod(request, tlsContext)
    if methods conflict or more than one method:
        reject invalid_request

    client = lookupRegisteredClient(authMethod, request, tlsContext)
    if client missing or disabled:
        reject invalid_client

    if authMethod != client.registeredTokenEndpointAuthMethod:
        reject invalid_client

    if client is CONFIDENTIAL:
        verifyRegisteredClientCredentials(client, authMethod)
    else:
        assert authMethod == NONE
        assert request.client_id == client.client_id

    require client.allowsGrant("authorization_code")

    code = readCodeBySecureLookup(request.code)
    if code missing or expired or already used:
        reject invalid_grant
    if code.client_id != client.client_id:
        reject invalid_grant
    if !matchesRedirectUriBinding(code, request.redirect_uri):
        reject invalid_grant
    if !verifyPkce(code, request.code_verifier):
        reject invalid_grant

    claimsAndGrant = validateOriginalAuthorizationAndPolicy(
        client, code.principal, code.scopes, code.resource
    )
    if not permitted:
        reject

    atomicallyConsumeCodeAndRecordIssuedTokens(code, claimsAndGrant)
    return oauthTokenResponse()
~~~

Đây là **pseudocode học tập**, không phải server hoàn chỉnh. Client authentication và grant validation có thể chạy qua các filters/validators khác nhau. Không lấy `request.user_id`, `request.tenant_id` hoặc `request.scope` ngoài grant rồi trực tiếp gán vào access token.

### 12.3. Một code chỉ được dùng một lần, kể cả khi có race

Ví dụ không an toàn:

~~~text
Request A: SELECT C1 with status=UNUSED
Request B: SELECT C1 with status=UNUSED
Request A: Issue A1
Request B: Issue A2
Request A: UPDATE C1 status=USED
Request B: UPDATE C1 status=USED
~~~

Nếu thao tác không nguyên tử, một code có thể đổi hai lần. AS cần transaction/compare-and-set/lock thích hợp để chỉ **một** request chuyển C1 từ `UNUSED` sang `USED`.

RFC 6749 yêu cầu từ chối việc sử dụng lại authorization code, đồng thời khuyến nghị xem xét revoke token đã cấp từ code đó khi phát hiện reuse.

### 12.4. Client authentication không cho client chọn `sub`/`aud` tùy ý

Một request đổi code cố gửi thêm:

~~~text
sub=user-admin
tenant=tenant-anpha
scope=payments:refund
aud=payments-api
~~~

AS không được dùng các giá trị này như sự thật chỉ vì client secret hợp lệ. Principal, grant, tenant policy, scope và audience phải được xác định từ **authorization transaction đã được phê duyệt** và policy của AS.

## 13. Token response và giới hạn quyền được cấp

Nếu mọi phép kiểm đạt, AS có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_EXAMPLE_ONLY",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Có thể có `refresh_token` nếu grant/chính sách cho phép. Với OIDC, có thể có `id_token` khi request/hồ sơ OIDC đáp ứng yêu cầu.

**Client authentication chứng minh danh tính ứng dụng**, không tự quyết scope/audience. AS phải cấp token theo grant, resource owner/consent và policy.

### 13.1. JWT access token minh họa

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-bff",
  "scope": "orders:read",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893453000,
  "jti": "access-92b1"
}
~~~

Đây là **payload minh họa chưa ký**. `client_id=shop-bff` nói về OAuth client, không phải resource owner hoặc `aud` của access token. `aud=orders-api` xác định Resource Server, còn `scope=orders:read` xác định giới hạn quyền.

JWS ký đúng **không đồng nghĩa payload được mã hóa**. Không đặt client secret, private key hoặc thông tin nhạy cảm không cần thiết vào access token.

### 13.2. Opaque access token

Nếu AS phát opaque token, RS có thể tra metadata qua introspection:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "client_id": "shop-bff",
  "scope": "orders:read",
  "exp": 1893453000
}
~~~

Các trường ngoài `active` tùy AS/profile. `active=true` không có nghĩa được gọi mọi API hoặc mọi endpoint. Resource Server vẫn phải kiểm issuer, audience, scope, thời hạn và object-level policy.

### 13.3. OIDC ID token khác access token

ID token thường có `aud=shop-bff` vì dành cho **OIDC Client**. Access token cho Orders API có `aud=orders-api`. OIDC Client xác minh `iss`, `aud`, signature, expiry và các điều kiện flow như `nonce` khi áp dụng; Resource Server **không nhận ID token** làm access token.

### 13.4. Resource Server vẫn phải kiểm độc lập

Orders API cần kiểm access token theo profile/issuer/audience, scope, token validity, tenant membership và quyền trên đơn hàng. Nếu token có sender binding, RS còn phải kiểm proof. **Confidential client xác thực thành công tại token endpoint không có nghĩa user được đọc mọi đơn hàng.**

## 14. Token endpoint errors: phân biệt lỗi client và lỗi grant

Một Authorization Server cần trả mã lỗi OAuth phù hợp **mà không tiết lộ secret, authorization code hoặc chi tiết đăng ký client**.

| Tình huống | OAuth error thường dùng | Lưu ý |
|---|---|---|
| Confidential client secret sai hoặc thiếu xác thực bắt buộc | `invalid_client` | Khi dùng Authorization header, response `401` phải có `WWW-Authenticate` khớp scheme. |
| JWT client assertion sai chữ ký, `iss`/`sub`/`aud`/`exp` | `invalid_client` | Không công bố private key, secret hoặc chính sách key cụ thể. |
| mTLS cert không khớp registered client | `invalid_client` hoặc lỗi TLS | Có thể bị từ chối ở handshake trước khi OAuth handler chạy. |
| Hai client auth methods trong một request | `invalid_request` | Không chọn một method tùy tiện. |
| Thiếu `grant_type`, `code` hoặc form sai cấu trúc | `invalid_request` | Không tiếp tục cấp token. |
| Client không được phép Authorization Code Grant | `unauthorized_client` | Client authentication đúng không tự cho phép mọi grant. |
| Grant type không được AS hỗ trợ | `unsupported_grant_type` | Theo token endpoint capability/policy. |
| Code không tồn tại, đã hết hạn hoặc đã dùng | `invalid_grant` | Không tiết lộ code thuộc client nào. |
| Code được cấp cho client khác | `invalid_grant` | Ngăn code substitution. |
| `redirect_uri` không khớp với code đã phát | `invalid_grant` | Kiểm binding chính xác. |
| PKCE verifier thiếu/sai | `invalid_grant` | Không fallback bỏ qua PKCE. |
| Scope yêu cầu không hợp lệ theo profile | `invalid_scope` hoặc lỗi grant tương ứng | Không nâng scope ngoài authorization. |
| Resource indicator không chấp nhận | `invalid_target` khi AS hỗ trợ RFC 8707 | Không tự phát token audience bất kỳ. |

Bảng là các trường hợp phổ biến; mã lỗi chính xác và HTTP status phụ thuộc điều kiện và đặc tả áp dụng. Ví dụ handshake mTLS thất bại có thể **không phát sinh OAuth JSON response**.

### 14.1. Ví dụ `invalid_client` với Basic

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="oauth2-token-endpoint"
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_client"
}
~~~

Không đưa `client_secret`, `client_assertion` hoặc raw Authorization header vào `error_description`. Khi dùng HTTP Basic, `401`/challenge tương ứng là một phần hợp đồng OAuth. Không thử đổi sang `none` để bypass lỗi Basic.

### 14.2. Ví dụ `invalid_grant`

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

Client không nên retry cùng code vô hạn. Nếu code sai hoặc đã dùng, thường phải bắt đầu authorization flow mới. Không log code, verifier hoặc token để “so sánh” trong production.

### 14.3. Tránh phân biệt client tồn tại qua lỗi

Thông điệp “client ID đúng nhưng secret sai”, “không thấy client ID”, “key của client hết hạn” có thể giúp attacker dò registration. AS cần cân bằng chuẩn OAuth với việc **không công khai chi tiết nội bộ không cần thiết**. Thông tin điều tra nên dùng mã lỗi/trace ID trong audit được giới hạn quyền, không echo secret.

## 15. Bảo vệ shared secret, private key và certificate

### 15.1. Quản lý client secret của confidential client

- Sinh credentials với entropy cao, cấp qua quy trình đáng tin và **không nhúng raw secret vào repository, log, SPA/mobile hoặc Docker image**.
- Ở runtime, sử dụng secret manager hoặc cơ chế tương đương; tránh ghi trong process arguments, URL, exception, trace hoặc metrics.
- Giới hạn service account/role có quyền đọc secret, phân tách dev/staging/production.
- AS xác minh secret bằng cơ chế lưu trữ an toàn (ví dụ secret được encode theo password encoder phù hợp), không giữ raw cleartext khi không cần.
- Có kế hoạch **rotate/revoke**, chính sách expiry và khôi phục khi client bị lộ secret.
- Không gửi client secret đến Resource Server, authorization URL, browser hoặc các bên quan sát ngoài phạm vi AS.

**Rotation phải phối hợp AS và OAuth client.** Một số provider cho phép overlap nhiều secret, số khác không; không mặc định mọi AS hỗ trợ hai secret song song hay tự rotate khi deploy.

### 15.2. `private_key_jwt` và key trust

Với phương thức JWT client authentication:

- Client giữ private key, có thể trong HSM/KMS hoặc secure key store.
- AS chỉ tin **public keys/JWKS đã gắn với registered client** và đã được quản lý, không tin arbitrary `jku`/`x5u` từ assertion.
- `kid` chọn key trong tập đã tin; `alg` phải thuộc allowlist theo client/profile, tránh `none`/algorithm confusion.
- Assertion có `exp` ngắn, `aud` đúng AS/token endpoint, `iss`/`sub` đúng client ID và `jti`/replay policy nếu sử dụng.
- Key rotation có overlap cần thiết cho request đang chạy và quy trình revoke khóa bị compromise.

Đừng dùng chung **client private key** với **AS JWT access token signing key** chỉ vì cùng thuật toán. Hai khóa có ranh giới tin cậy và hậu quả compromise khác nhau.

### 15.3. mTLS qua gateway/reverse proxy

Khi client certificate validation xảy ra ở API Gateway:

1. AS phải biết gateway nào đáng tin và gateway đã xác minh chứng chỉ gì.
2. Gateway **xóa/ghi đè** mọi header chứng chỉ tự khai từ Internet.
3. Kết nối proxy–AS được bảo vệ và chỉ cho phép proxy đã xác thực.
4. AS ánh xạ đúng subject/public key/cert với client registration.
5. Cert expired/revoked/rotated phải dẫn tới policy xác thực tương ứng.
6. Nếu access token sau này được certificate-bound, RS cũng cần kiểm binding, không chỉ AS.

Không chỉ nhìn `X-Client-Cert` raw header rồi xác nhận client; attacker có thể tự gửi header đó nếu trust boundary sai.

### 15.4. Không để credentials lọt vào telemetry

Những nguồn cần lọc hoặc không thu thập:

~~~text
Authorization: Basic ...
client_secret
client_assertion
private_key / PEM / keystore passphrase
authorization_code
code_verifier
access_token / refresh_token / id_token
Cookie / Set-Cookie
DPoP proof
full request/response body of token endpoint
full callback URL query with code and state
~~~

**Ưu tiên không thu thập tại nguồn**. Redaction chỉ trên dashboard không xóa được bản sao trong log files, agent, collector, APM và backup. Regex chỉ tìm JWT không bắt được Basic secret hoặc opaque authorization code.

Ví dụ log an toàn:

~~~json
{
  "event": "oauth_token_client_auth_failed",
  "issuer": "https://login.example.com",
  "client_ref": "shop-bff",
  "auth_method": "client_secret_basic",
  "grant_type": "authorization_code",
  "error": "invalid_client",
  "trace_id": "b7d9f1225a6e4c7ab30d2189444b5f60"
}
~~~

`client_ref` có thể ghi nếu policy audit cho phép; không sử dụng secret/token làm correlation ID. Không log nội dung code, Basic header hoặc client assertion JWT.

## 16. Token endpoint, issuer và chống nhầm Authorization Server

Ứng dụng có thể đăng nhập qua nhiều IdP/AS. Một callback chứa code cần được ràng buộc với **AS đã khởi tạo authorization transaction**; gửi code hoặc confidential credentials nhầm sang token endpoint khác có thể làm lộ thông tin hoặc dẫn đến tấn công *mix-up*.

### 16.1. Một transaction cần giữ các ràng buộc

~~~text
state                    = high-entropy request identifier
expected_issuer          = https://login.example.com
client_id                = shop-bff
redirect_uri             = https://shop.example.com/login/oauth2/code/shop
token_endpoint           = https://login.example.com/oauth2/token
pkce_verifier_reference  = transaction-local secret
created_at / expires_at  = ...
consumed                 = false
~~~

Client phải kiểm `state` và liên kết authorization response với issuer/client/redirect transaction đã tạo. Khi AS hỗ trợ **RFC 9207**, giá trị `iss` trong authorization response có thể hỗ trợ chống mix-up theo profile; client cần xác minh đúng, không chỉ đọc và bỏ qua.

**Không lấy `token_endpoint` URL từ callback query, email, input người dùng hoặc token chưa xác minh**. Chỉ gọi endpoint đã cấu hình/discover từ issuer tin cậy và dùng TLS certificate/hostname validation đầy đủ. Không tắt kiểm TLS để “đổi code cho nhanh”.

### 16.2. `redirect_uri` là ràng buộc riêng với code

Client secret hợp lệ **không cho phép** đổi code được cấp cho redirect URI khác. Với code flow, nếu `redirect_uri` đã có trong authorization request, token request phải gửi lại và AS kiểm giá trị đúng theo quy tắc giao thức.

AS phải đối chiếu redirect URI với client registration và code binding. Tránh wildcard/open redirect làm rò code; với native app có quy tắc redirect riêng theo profile, không dùng một so khớp lỏng lẻo chung cho mọi loại client.

### 16.3. Code không cho phép mở rộng scope/audience tại token endpoint

Một code được cấp cho `orders:read` và `orders-api` không thể trở thành token `payments:refund`/`payments-api` chỉ vì confidential client xác thực thành công. AS phải kiểm grant đã được phê duyệt, resource indicators theo RFC 8707 nếu áp dụng, phạm vi/tenant và policy hiện hành.

## 17. Ví dụ Spring Authorization Server: đăng ký client

Đối với hệ sinh thái Java, Spring Authorization Server có các abstractions **RegisteredClient**, **ClientAuthenticationMethod**, **AuthorizationGrantType** và **ClientSettings**. Nên dùng framework để xác thực token endpoint thay vì tự parse mọi client secret/JWT/mTLS proof.

Mã sau minh họa **registration**, không phải hệ thống AS tự chạy hoàn chỉnh. Cần phiên bản Spring/Spring Boot phù hợp, key/issuer/security filter chain và persistent repositories được cấu hình thêm.

### 17.1. Confidential backend: Basic và PKCE

~~~java
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

public final class ClientRegistrationExamples {
    private ClientRegistrationExamples() {}

    public static RegisteredClient confidentialBackend(
            String encodedSecretFromProtectedSource) {

        return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("shop-bff")
            .clientSecret(encodedSecretFromProtectedSource)
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC
            )
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE
            )
            .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN
            )
            .redirectUri(
                "https://shop.example.com/login/oauth2/code/shop"
            )
            .scope("openid")
            .scope("orders:read")
            .clientSettings(
                ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build()
            )
            .build();
    }
}
~~~

Giải thích:

- `shop-bff` được đăng ký `CLIENT_SECRET_BASIC`, không chấp nhận method `none` chỉ vì secret không khớp.
- `encodedSecretFromProtectedSource` là representation đã được AS chuẩn bị theo password encoder/secret verification, **không phải raw secret gửi vào web UI**.
- `requireProofKey(true)` yêu cầu PKCE, **bổ sung** client authentication.
- Grant `AUTHORIZATION_CODE` và `REFRESH_TOKEN` được đăng ký, nhưng không có nghĩa AS buộc cấp refresh token ở mọi login.
- Client registration scopes chỉ giới hạn điều client **có thể xin**, không tự cấp quyền mọi user/tenant.
- Phương thức consent phải phù hợp policy và ứng dụng; `requireAuthorizationConsent(true)` ở đây chỉ là ví dụ.

**Quan trọng:** `UUID.randomUUID()` trong builder chỉ minh họa record ID. Ở production, dùng **registration ID ổn định trong persistent repository**, không tạo registration mới ở mỗi restart rồi làm mất/nhầm dữ liệu authorization/grant.

### 17.2. Public browser client: `none` và PKCE

~~~java
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

public final class PublicClientExample {
    private PublicClientExample() {}

    public static RegisteredClient browserSpa() {
        return RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("shop-spa")
            .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE
            )
            .redirectUri("https://spa.example.com/callback")
            .scope("openid")
            .scope("orders:read")
            .clientSettings(
                ClientSettings.builder()
                    .requireProofKey(true)
                    .build()
            )
            .build();
    }
}
~~~

Không có `clientSecret(...)`. AS **vẫn kiểm** client ID, code binding, redirect URI, PKCE và grant. `ClientAuthenticationMethod.NONE` nghĩa public client **không có client authentication credential theo method đó**, chứ không có nghĩa bỏ kiểm authorization code.

### 17.3. Client-side registration phải khớp server

Trong Spring Security OAuth2 Client/BFF, khai báo cùng `client_id`, `client_authentication_method`, redirect URI và token endpoint như AS. Nếu AS đăng ký Basic, client không được tự đổi sang POST hoặc `none` khi nhận `invalid_client`.

Thư viện OAuth Client có thể thực hiện form encoding, PKCE, token handling và callback validation; ưu tiên dùng các abstraction sẵn có. Song song, token store phải bảo vệ access/refresh token, CSRF/session phải phù hợp kiến trúc BFF và phải xử lý secret rotation.

### 17.4. Private JWT/mTLS cần cấu hình chuyên biệt

Chỉ đổi field registration sang `PRIVATE_KEY_JWT` hoặc `TLS_CLIENT_AUTH` **không tự cung cấp khóa/chứng chỉ**. AS cần xác thực client assertion bằng JWK/certificate đã tin; client cần ký assertion hoặc trình cert đúng cách. Phải test key rotation, algorithm, audience, replay và proxy trust.

## 18. Những lỗi thiết kế và tấn công thường gặp

| Lỗi hoặc kiểu tấn công | Ví dụ | Điều phải chặn |
|---|---|---|
| **Client impersonation** | Attacker biết `client_id=shop-bff` và tự gửi form token request. | Confidential client phải trình đúng credential được AS kiểm. |
| **Public client giả confidential** | SPA nhúng secret trong JavaScript/binary. | Đăng ký đúng client type; không xem embedded secret là bí mật đáng tin. |
| **Authentication downgrade** | Basic sai, AS tự chuyển sang `none` hoặc `client_secret_post`. | Method phải khớp registration, không fallback. |
| **Nhiều auth methods** | Basic cho client A, body `client_secret` cho client B. | Từ chối mâu thuẫn; không chọn tùy tiện. |
| **Wrong client code substitution** | Client A dùng authorization code đã phát cho B. | Kiểm code/client binding sau khi xác thực client. |
| **Code interception** | Attacker lấy code qua log/open redirect. | PKCE S256, redirect URI/one-time code, TLS. |
| **PKCE bypass** | AS chỉ kiểm secret, bỏ `code_verifier`. | Kiểm verifier nếu code có challenge, bất kể Basic/JWT/mTLS. |
| **PKCE downgrade** | Request flow bị thay thành không có challenge rồi AS chấp nhận. | AS/registration policy yêu cầu PKCE và ngăn bỏ challenge. |
| **Redirect mismatch** | Code phát cho callback A, đổi code với redirect B. | Ràng buộc redirect URI chính xác. |
| **Authorization code replay** | Hai request đổi C1 thành hai access tokens. | One-time code bằng transaction/CAS, xử lý reuse. |
| **Mix-up giữa nhiều AS** | Code của IdP A được gửi tới token endpoint IdP B. | Ràng buộc state/issuer/endpoint, xác minh RFC 9207 khi hỗ trợ. |
| **Client secret trong URL** | `?client_secret=...` tại token endpoint. | Không nhận/ghi credential qua query, TLS và schema chặt. |
| **JWT assertion sai `aud`** | `private_key_jwt` đặt `aud=orders-api` thay vì AS. | AS kiểm chính xác audience client assertion. |
| **JWT algorithm/key confusion** | Assertion có `alg=none` hoặc `kid` trỏ attacker key. | Chỉ dùng thuật toán và public keys đã đăng ký cho đúng client. |
| **Assertion replay** | Attacker gửi lại JWT client assertion còn hạn. | Hạn ngắn, `jti`/replay cache theo policy, rate limit. |
| **mTLS proxy spoofing** | Attacker tự gửi `X-Client-Cert` header. | Chỉ tin proxy được xác thực, strip untrusted header. |
| **Scope/audience escalation** | Token endpoint copy `scope=admin` từ form dù code chỉ có `orders:read`. | Cấp token trong giới hạn grant và client/resource policy. |
| **ID token confusion** | RS nhận ID token có `aud=shop-bff` làm access token. | RS kiểm token purpose, issuer, audience, scope. |
| **Credential leakage qua APM** | HTTP client wire logger ghi Basic header hoặc JWT assertion. | Không thu thập secret, scrub theo field trước export. |
| **Secret rotation không phối hợp** | Client đã đổi secret, AS chưa cập nhật. | Rollout/overlap/rollback theo provider và alert. |
| **Confidential client compromised** | Attacker lấy cả secret và code verifier. | Key store, least privilege, anomaly detection, revoke và phòng thủ nhiều lớp. |

### 18.1. Client authentication thành công không phải quyền vượt mọi grant

Giả sử `shop-bff` xác thực Basic đúng nhưng request:

~~~text
grant_type=authorization_code
code=CODE_FOR_DIFFERENT_CLIENT
scope=payments:refund
resource=https://api.example.com/payments
~~~

AS phải chặn do **code/client binding** và phạm vi/grant sai. Một confidential client không phải “superuser của Authorization Server”. Nếu hệ thống phát JWT sai scope/audience và ký hợp lệ, đó vẫn là **lỗi phát hành**, không được chữa bằng cách chỉ tăng độ mạnh của client secret.

### 18.2. Đừng dùng client credentials như chứng chỉ Resource Owner đã đăng nhập

Một backend có thể tự xác thực tại token endpoint trong Authorization Code flow, nhưng **người dùng** phải được xác thực/ủy quyền đúng ở authorization flow trước. Nếu AS dùng client authentication thành công để tự đặt `sub=admin`, nó đã nhầm **danh tính client** với **principal của grant**.

Với `client_credentials` grant, service principal có ý nghĩa riêng. Không gán end-user `sub` tùy ý hoặc dùng một client secret để “mượn” quyền của mọi user.

### 18.3. DPoP hoặc mTLS không tự thay client registration

Sender-constrained tokens làm giảm nguy cơ một bản sao token được dùng ở nơi khác nếu thiếu khóa, nhưng **AS vẫn phải biết token được cấp cho grant/client nào**, còn RS phải kiểm audience/scope/purpose và binding.

Một DPoP proof được ký tốt không cho phép bỏ kiểm authorization code, PKCE, scope, consent hoặc resource owner policy.

## 19. Chiến lược kiểm thử token endpoint

Để kiểm một client authentication implementation, chỉ gửi một code giả không tồn tại rồi nhìn response `invalid_grant` **chưa đủ**: request có thể bị từ chối vì code giả trước khi chạm vào logic client authentication. Test cần chuẩn bị **authorization code hợp lệ, chưa dùng và được ràng buộc client/method/verifier**, sau đó thay từng điều kiện để chứng minh AS thực sự kiểm nó.

### 19.1. Chuẩn bị test fixture

~~~text
Issuer: https://login.example.com

Confidential client:
  id = shop-bff
  method = client_secret_basic
  secret = test-only credential from test vault
  redirect = https://shop.example.com/login/oauth2/code/shop

Public client:
  id = shop-spa
  method = none
  redirect = https://spa.example.com/callback

Authorization Code C1:
  issued to shop-bff
  redirect = registered shop-bff callback
  PKCE challenge = S256(V1)
  scopes = orders:read
  resource = orders-api
  status = UNUSED
  not expired

Authorization Code C2:
  issued to shop-spa
  redirect = registered shop-spa callback
  PKCE challenge = S256(V2)
  scopes = orders:read
  resource = orders-api
  status = UNUSED
  not expired
~~~

Mọi token/secret trong test phải là **giá trị giả và độc lập production**. Khi mỗi test tiêu thụ code, fixture phải tạo code mới; **không tái sử dụng C1** giữa tests rồi nhầm lỗi `invalid_grant` thành kết quả của case đang kiểm.

### 19.2. Ma trận positive và negative tests

| Test | Input thay đổi | Kỳ vọng |
|---|---|---|
| **Confidential success** | Basic hợp lệ + C1 + V1 + redirect URI đúng | Có thể cấp token với scope/audience của grant. |
| **Public success** | `client_id=shop-spa`, method `none` + C2 + V2 | Có thể cấp token theo public-client policy. |
| Basic secret sai | Dùng C1/V1 hợp lệ nhưng Basic sai | Không cấp token, lỗi `invalid_client` phù hợp. |
| Thiếu Basic của confidential client | C1/V1 hợp lệ nhưng không có client auth | Không cấp token; không fallback sang `none`. |
| Basic đúng nhưng code của client khác | shop-bff + C2/V2 | Từ chối do code/client mismatch. |
| Public client giả có secret | shop-spa + `client_secret` giả | Không xem secret như confidential credential; xử lý method sai. |
| Client ID sai | C2/V2 nhưng `client_id=another-client` | Từ chối do binding. |
| Hai auth methods | Basic + `client_secret` trong body | Từ chối, không chọn tùy tiện. |
| Client disabled | shop-bff bị vô hiệu nhưng secret đúng | Không phát access token. |
| Grant bị cấm | Client không được `authorization_code` | `unauthorized_client`/lỗi phù hợp. |
| Code không tồn tại | Code ngẫu nhiên | `invalid_grant`, không cấp token. |
| Code hết hạn | C1 hết hạn theo clock test | Từ chối. |
| Code đã được đổi | Dùng lại C1 sau thành công | Từ chối; xử lý reuse theo policy. |
| Hai request cùng đổi C1 | Token requests song song | Chỉ một lần tiêu thụ code hợp lệ. |
| PKCE verifier sai | Basic đúng, code C1, verifier khác V1 | `invalid_grant`; không bypass PKCE. |
| PKCE verifier thiếu | C1 có challenge nhưng request không gửi verifier | Từ chối. |
| PKCE method bị downgrade | Flow bị bỏ challenge dù registration yêu cầu PKCE | Không phát code/token theo policy. |
| Redirect URI không khớp | Basic đúng, C1, redirect đổi hostname/path | `invalid_grant`. |
| Redirect URI chứa open redirect/wildcard sai | Authorization request/callback không đăng ký | Từ chối theo registration/profile. |
| Client assertion sai signature | `private_key_jwt` client được test, ký bằng key lạ | `invalid_client`. |
| Assertion `iss` hoặc `sub` khác client ID | Client assertion mạo danh | Từ chối. |
| Assertion sai `aud` | `aud=orders-api` thay AS/token endpoint | Từ chối. |
| Assertion hết hạn | `exp` trong quá khứ | Từ chối. |
| Assertion reuse | Cùng `jti`/assertion gửi lại trong cửa sổ policy | Từ chối theo replay protection. |
| Assertion algorithm không được phép | `alg=none` hoặc thuật toán ngoài allowlist | Từ chối. |
| mTLS thiếu certificate | Client đăng ký mTLS không có cert | TLS/authentication thất bại. |
| mTLS cert khác registration | Cert hợp lệ nhưng thuộc client khác | Không xác thực client đang khai. |
| Proxy tự khai cert header | Request có `X-Client-Cert` nhưng không từ proxy tin cậy | Không chấp nhận như mTLS. |
| Issuer mix-up | Code của AS A, token endpoint AS B | Bị chặn bởi transaction/issuer binding. |
| Client xin scope vượt grant | Code chỉ `orders:read`, request `payments:refund` | Không cấp scope vượt quyền. |
| Resource đích ngoài grant | Đổi `resource` sang Payments | Không phát token Payments theo policy. |
| Token response thành công | Token được trả có `client_id`/`aud`/`scope` đúng | Các claim/metadata khớp grant. |
| ID token gửi tới Resource Server | OIDC `aud=shop-bff` | RS từ chối sai token purpose/audience. |
| Secret trong error response | Gửi canary secret sai | Không echo secret/code/verifier trong response/log/trace. |
| Token endpoint không có TLS | Request HTTP hoặc TLS cert lỗi | Không gửi/không nhận credentials không bảo vệ. |

### 19.3. Kiểm các trường hợp concurrency

~~~text
test "authorization code is single-use":
    C1 = issueValidCode(client=shop-bff, pkceChallenge=S256(V1))
    runInParallel(
        redeem(C1, clientAuth=validBasic, verifier=V1),
        redeem(C1, clientAuth=validBasic, verifier=V1)
    )
    assert exactly one valid successful code redemption
    assert second redemption is rejected
    assert code record has no two independent issued-token branches

test "client mismatch even with valid secret":
    C2 = issueValidCode(client=shop-spa, pkceChallenge=S256(V2))
    result = redeem(C2, clientAuth=validShopBffBasic, verifier=V2)
    assert result is not a successful token response
    assert no access token was issued for C2 to shop-bff

test "PKCE cannot be bypassed with Basic":
    C1 = issueValidCode(client=shop-bff, pkceChallenge=S256(V1))
    result = redeem(C1, clientAuth=validShopBffBasic, verifier=wrongV)
    assert result is invalid_grant
~~~

Pseudocode không thay thế các tests framework thật. Dùng test clock và in-memory/persistent store phù hợp để chứng minh atomicity, không chỉ dựa vào timing may rủi hoặc `Thread.sleep`.

### 19.4. Test key/certificate rotation và telemetry

Ngoài các request chuẩn, cần mô phỏng:

- Secret cũ/mới trong cửa sổ rotation đúng policy; hết overlap thì secret cũ bị từ chối.
- Client JWK `kid` cũ/mới với key registration/refresh đúng, đồng thời từ chối `kid` lạ.
- Client assertion `jti` đã dùng và request bị replay.
- mTLS cert gần hết hạn, bị revoke, chain không tin hoặc proxy config sai.
- Cấu hình APM bật HTTP header/body capture; dùng canary để xác nhận không lưu client secret, code, verifier hay assertion.
- AS chạy nhiều instance cùng đổi code: chỉ một thành công.
- Rollback/deploy client auth method: không vô tình fallback sang `none` hoặc bật `client_secret_post` cho mọi client.

## 20. Bài tập tình huống

### Bài 1 — Phân loại client và chọn phương thức

Hệ thống gồm:

~~~text
shop-bff:     Java backend, có Secret Manager và HTTPS
shop-spa:     Browser JavaScript, không có backend riêng
shop-mobile:  App native phân phối cho người dùng
billing-bff:  Backend có KMS/HSM quản lý private key
partner-api:  Confidential server có PKI và mTLS
~~~

Hãy đề xuất `token_endpoint_auth_method`:

1. `shop-bff`: có thể dùng `client_secret_basic`, `private_key_jwt` hoặc mTLS tùy AS; yêu cầu PKCE cho Authorization Code flow.
2. `shop-spa`: `none` với PKCE S256 và redirect URI an toàn; không nhúng shared secret.
3. `shop-mobile`: public client với PKCE và native-app redirect rules; không coi secret nhúng vào binary là confidential credential.
4. `billing-bff`: `private_key_jwt` nếu AS hỗ trợ và public JWK được đăng ký.
5. `partner-api`: mTLS client authentication nếu PKI và AS đã triển khai đúng; lưu ý đây không nhất thiết là Authorization Code flow nếu service chỉ dùng client credentials.

**Không chọn method chỉ vì tên nghe “an toàn nhất”**; cần đánh giá khả năng giữ khóa, threat model, key rotation, TLS termination, thư viện và các phương thức thực sự được AS hỗ trợ.

### Bài 2 — Tìm lỗi trong Authorization Server

Cho pseudocode sai:

~~~text
function exchange(code, client_id, client_secret, code_verifier):
    if knownClientId(client_id):
        principal = decodeCodeWithoutVerification(code).userId
        return signAccessToken(
            sub = principal,
            aud = request.aud,
            scope = request.scope,
            exp = now + 24h
        )
~~~

Những vấn đề:

- Không xác minh secret hoặc method đã đăng ký; chỉ biết client ID.
- Không kiểm confidential/public client type.
- Không kiểm code phát cho client nào, redirect URI, TTL, one-time use.
- Không kiểm PKCE verifier/challenge.
- Không kiểm issuer, grant/consent hoặc subject từ nguồn đáng tin.
- Copy audience/scope từ request không qua policy.
- Không giới hạn TTL theo resource, không có audit/revocation.
- Ký JWT khiến token sai quyền trở thành **đã ký hợp lệ**, không sửa được lỗi authorization.

Hãy sửa theo thuật toán mục 12, rồi viết tests chứng minh không cấp token khi từng ràng buộc bị phá.

### Bài 3 — Phân biệt ba JWT

Một hệ thống thấy ba JWT:

~~~text
JWT X:
  iss=shop-bff, sub=shop-bff, aud=https://login.example.com/oauth2/token
  signed by shop-bff private key

JWT Y:
  iss=https://login.example.com, sub=user-742, aud=shop-bff
  signed by AS/OP

JWT Z:
  iss=https://login.example.com, sub=user-742, aud=orders-api
  scope=orders:read, signed by AS
~~~

- **JWT X**: client assertion cho `private_key_jwt`; AS kiểm để xác thực client.
- **JWT Y**: có hình thái ID token OIDC dành cho client; phải kiểm đúng OIDC profile, không đủ bằng vài claim đã viết.
- **JWT Z**: có hình thái JWT access token dành cho Orders API; RS kiểm đúng access-token profile, scope/audience và quyền bản ghi.

**Không** gửi X hoặc Y làm access token đến Orders API. Chữ ký hợp lệ chưa đủ; **purpose và audience** phải phù hợp.

### Bài 4 — Sự cố sau deploy

Một BFF chuyển từ `client_secret_basic` sang `client_secret_post` vì gặp lỗi `invalid_client`; một phần người dùng không còn đổi authorization code thành token. Log hiện đang ghi toàn bộ form body của token request.

Các bước cần làm:

1. Kiểm client registration/metadata để xác định **method được phép**; không tự đổi method để bypass.
2. Xác định secret đã rotate/chưa đồng bộ, lỗi encoding Basic hoặc proxy đã strip header.
3. **Ngăn ghi form-body secret**, điều tra log/collector/APM/backup đã bị ảnh hưởng.
4. Nếu credentials đã lộ, rotate/revoke theo playbook và đánh giá khả năng code/token bị lạm dụng.
5. Sửa config/client library, test positive/negative authentication method và PKCE.
6. Bật alert cho `invalid_client`, phân biệt với `invalid_grant`, nhưng không log raw credentials.

### Bài 5 — Thiết kế test chống downgrade

Client `shop-bff` được đăng ký confidential/Basic + PKCE. Thử bốn request dùng code hợp lệ mới cấp:

~~~text
A. Basic correct + code correct + verifier correct
B. Basic missing + code correct + verifier correct
C. Basic wrong + code correct + verifier correct
D. Basic correct + code correct + verifier wrong
~~~

Kỳ vọng: **A có thể thành công**, **B/C không cấp token vì client authentication**, **D không cấp token vì PKCE**. Thêm case Basic đúng nhưng code của client khác để chứng minh code/client binding độc lập.

## 21. Checklist triển khai

- [ ] Đã phân biệt user authentication, OAuth client authentication, PKCE, access-token validation và authorization của RS.
- [ ] Mỗi client có registration riêng với client type, grant, auth method, redirect URI, scope/resource được phép.
- [ ] Confidential client xác thực tại token endpoint bằng method đã đăng ký; không fallback sang `none` khi credentials sai.
- [ ] Public client không chứa shared secret giả trong JavaScript/mobile binary; dùng Authorization Code + PKCE theo profile.
- [ ] `client_id` được coi là public identifier, không phải credential bảo mật.
- [ ] Token endpoint chỉ nhận qua HTTPS với TLS validation đầy đủ; không nhận client secret trong URL query.
- [ ] Không sử dụng nhiều hơn một client authentication method trong một request.
- [ ] Nếu dùng `client_secret_basic`, Basic encoding/UTF-8 và form encoding tuân RFC 6749.
- [ ] Nếu dùng `client_secret_post` do provider yêu cầu, token body không được log/trace.
- [ ] Nếu dùng `private_key_jwt`, kiểm public key theo registration, `iss`/`sub`/`aud`/`exp`, algorithm và replay policy.
- [ ] Nếu dùng mTLS, cert được xác minh/ánh xạ client đúng, proxy trust và key rotation an toàn.
- [ ] Code phát cho đúng client, đúng redirect URI, còn hạn, chưa dùng và PKCE verifier khớp.
- [ ] Code được redeem đúng một lần dưới concurrent requests.
- [ ] AS kiểm grant/consent, principal, scope, audience/resource và token TTL trước khi phát token.
- [ ] Không dùng ID token, client assertion hoặc refresh token như access token của Resource Server.
- [ ] RS kiểm access token issuer, signature/introspection, audience, token purpose, expiry, scope và quyền trên từng resource/tenant.
- [ ] Client secret/private key được giữ an toàn, rotate/revoke có kế hoạch; không hardcode hoặc chia sẻ giữa các client không cần thiết.
- [ ] Authorization response/callback được ràng buộc `state`, issuer và đúng token endpoint; ngăn mix-up.
- [ ] Logs/traces/APM không chứa code, verifier, secret, assertion, authorization header hoặc access/refresh token.
- [ ] Đã kiểm negative cases: wrong client, wrong method, missing credentials, wrong redirect, PKCE mismatch, code reuse, scope/aud escalation, JWT assertion sai, mTLS spoofing.
- [ ] Khi client/grant/credential không được xác minh, AS **fail closed** và trả OAuth error phù hợp.

**Ghi nhớ:** **Client authentication at token endpoint** là phép xác minh OAuth client của **Authorization Server**, đặc biệt quan trọng với confidential clients. Nó **khác PKCE**, vốn ràng buộc người đổi code với authorization request ban đầu; **khác user authentication**, vốn xác minh Resource Owner; và **khác Resource Server validation**, vốn kiểm access token cùng quyền trên dữ liệu. Một Authorization Code flow an toàn cần **client/method đúng, authorization code đúng client/redirect URI, PKCE hợp lệ, code dùng một lần và grant/scope/audience được AS phê duyệt**. Không một lớp nào tự thay thế các lớp còn lại.

### Tài liệu chuẩn tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** `2.1` client types, `2.3` client authentication, `3.2.1` token endpoint client authentication và `4.1.3` authorization code token request.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code verifier/challenge, S256 và bảo vệ code interception.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** PKCE, client security, chống code injection/mix-up, bảo vệ tokens.
- **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants:** JWT client assertions, `iss`/`sub`/`aud`/`exp` và signature validation.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** `tls_client_auth`, `self_signed_tls_client_auth` và token binding.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** discovery của token endpoint và authentication methods.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer identification trong authorization response.
- **RFC 8252 — OAuth 2.0 for Native Apps:** phân loại native client và redirect URI/PKCE.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof-of-possession, khác client authentication/PKCE.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** tham số `resource` và audience constraints.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** claims của access JWT và Resource Server validation.
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc claims, `iss`, `sub`, `aud`, `exp`.
- **RFC 8725 — JSON Web Token Best Current Practices:** algorithm/key confusion và xác minh claims.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái và metadata opaque access token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token và hạn chế lạm dụng khi bị lộ.
- **OpenID Connect Core 1.0 / OpenID Connect Discovery:** client authentication methods, ID token và mối quan hệ với OAuth client.
- **Spring Authorization Server Reference / Spring Security OAuth2 Client Reference:** `RegisteredClient`, `ClientAuthenticationMethod`, PKCE và cấu hình token endpoint.
- **OWASP OAuth 2.0 Cheat Sheet / Secrets Management Cheat Sheet:** bảo vệ client credentials, redirect, PKCE, logging và rotation.



