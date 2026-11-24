# Client authentication cho introspection

Một Resource Server (RS) nhận access token và muốn hỏi Authorization Server (AS): **“Token này có đang được chấp nhận không, dành cho API nào và có scope gì?”** Nếu sử dụng **OAuth 2.0 Token Introspection (RFC 7662)**, RS gửi token đến **introspection endpoint** và nhận về kết quả như `active=true` hoặc `active=false`. Nhưng trước khi trả thông tin đó, AS phải trả lời một câu hỏi quan trọng khác: **“Ai đang hỏi? Resource server này có quyền xem trạng thái và metadata của token đó không?”**

Đó là mục đích của **client authentication cho introspection**: bảo vệ đường giao tiếp **resource server → authorization server**, tránh để bất kỳ bên nào có một chuỗi token đều có thể hỏi danh tính người dùng, client, scope, audience hoặc tenant liên quan. Một access token có thể là **opaque token** hoặc **JWT**; dù định dạng nào, việc gửi token đi introspect **không tự chứng minh bên gửi được quyền introspect**.

Ví dụ, Orders API sử dụng một credential riêng `orders-introspection-rs` để xác thực khi gọi `https://auth.example.com/oauth2/introspect`. AS kiểm tra credential và quyền của RS, rồi mới trả metadata về token hợp lệ cho Orders API. Nếu token đang hoạt động nhưng chỉ dành cho Payments API, Orders API **không được biến `active=true` thành quyền truy cập Orders**.

Bài **“Client authentication cho introspection”** nằm trong chương **Introspection** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung liên hệ mô hình tin cậy và vòng đời JWT/opaque, access/refresh token, OAuth 2.0/OIDC, scope/audience/issuer, lưu trữ, thu hồi, và phòng chống token bị đánh cắp hoặc phát lại.

> **Nguyên tắc:** Có **hai phép kiểm tra độc lập**: (1) AS **xác thực và phân quyền resource server** gọi introspection; (2) AS xác định **token được hỏi có active và được tiết lộ metadata trong ngữ cảnh đó không**. Sau khi nhận kết quả tin cậy, **RS vẫn phải kiểm tra audience, scope, token purpose, tenant và quyền trên tài nguyên**.

## 1. Phân biệt các vai trò và đường tin cậy

OAuth 2.0 có bốn vai trò logic:

| Vai trò | Ví dụ | Liên quan đến introspection |
| --- | --- | --- |
| **Resource owner** | Người dùng có quyền với đơn hàng | Thường không tự gọi introspection |
| **OAuth client** | Frontend, backend hoặc worker nhận access token | Gửi access token đến RS, không phải bên mặc nhiên được phép introspect |
| **Authorization server (AS)** | `auth.example.com` | Phát token, giữ trạng thái/grant, cung cấp introspection endpoint |
| **Resource server (RS)** | `orders-api` | Bảo vệ API; gọi AS bằng **credential riêng** khi cần introspect |

**Resource server có thể được đăng ký làm một OAuth client** để sử dụng phương thức xác thực với AS. Vì vậy một số tài liệu gọi credential này là *introspection client credentials*. Điều đó **không biến access token mà RS đang kiểm tra thành client credential của RS**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Ứng dụng OAuth client
    participant RS as Orders API / Resource Server
    participant AS as Authorization Server
    C->>RS: GET /orders + Bearer access token T
    RS->>AS: POST /introspect token=T + RS credential
    AS->>AS: Xác thực RS (ai đang hỏi?)
    AS->>AS: Phân quyền RS xem token T không?
    AS->>AS: Kiểm tra T: trạng thái, hạn, grant, metadata
    AS-->>RS: active + metadata được phép tiết lộ
    RS->>RS: Validate issuer, audience, scope, type, tenant
    RS-->>C: API result hoặc 401/403/5xx
~~~

### 1.1. Phân biệt ba loại credential

| Credential | Ai sở hữu? | Dùng để làm gì? | Không được dùng làm gì? |
| --- | --- | --- | --- |
| **Access token T cần kiểm tra** | OAuth client gửi tới RS | Truy cập resource; RS gửi T đến AS để kiểm tra | Không tự là credential xác thực **RS** với AS |
| **Credential introspection của RS** | Backend RS hoặc trusted gateway | Xác thực **caller** với introspection endpoint | Không cấp quyền đọc mọi business resource |
| **Access/refresh token đã được AS cấp** | OAuth client/workload theo grant | Gọi API hoặc làm refresh theo profile | Không mặc định cho phép truy vấn trạng thái token bất kỳ |

**Một lỗi kiến trúc phổ biến:** API nhận `Authorization: Bearer T` rồi forward **cùng Bearer T** sang `Authorization` header của introspection request, trong khi AS đòi credential của chính RS. Việc đó vừa trộn định danh caller với token cần kiểm tra, vừa có thể làm lộ token cho sai thành phần.

### 1.2. Resource server khác OAuth client gọi API

Một frontend SPA là **public client** và không giữ client secret an toàn. Không thiết kế để SPA trực tiếp gọi introspection với secret của Orders API; secret phải nằm ở backend/trusted service. Nếu cần cho UI biết trạng thái phiên, backend có thể trả thông tin UX **đã giảm thiểu dữ liệu** cho frontend, không chuyển cả introspection response.

### 1.3. Introspection không tự cấp quyền ứng dụng

Việc RS xác thực với AS **chỉ cho phép AS xem xét và trả thông tin token theo policy**. API chưa được phép xử lý request chỉ vì credential introspection đúng. Metadata token và resource authorization vẫn phải được kiểm tra riêng.

## 2. RFC 7662 yêu cầu gì đối với bên gọi?

**RFC 7662 — OAuth 2.0 Token Introspection** quy định introspection endpoint **phải yêu cầu xác thực các protected resources cần truy cập endpoint**. Cơ chế xác thực cụ thể không bị giới hạn vào một phương thức duy nhất bởi RFC này; AS và các profile có thể dùng HTTP Basic, các client authentication methods khác hoặc credentials dành riêng cho introspection.

AS không chỉ cần xác thực mà còn phải **phân quyền cho protected resource được phép introspect token nào, nhận những metadata nào**. Không nên để một RS được xem tất cả tokens chỉ vì nó có một client ID/secret hợp lệ.

### 2.1. Những điều RFC 7662 không mặc định bảo đảm

- Không bắt buộc endpoint luôn là `/oauth2/introspect`; URL do AS quyết định.
- Không bắt buộc client authentication phải dùng **cùng credential hoặc method** với token endpoint.
- Không quy định mọi AS phải hỗ trợ `private_key_jwt`, mTLS hay bearer credential cho introspection.
- Không bắt buộc mọi active response chứa `iss`, `aud`, `sub`, `scope` và `exp`; metadata là theo hợp đồng/phân quyền.
- Không có nghĩa một caller đã authenticate thành công được phép biết mọi token, refresh token hoặc dữ liệu cá nhân.
- Không có nghĩa `active=true` là toàn quyền ở mọi resource server.

**Chốt contract trước khi triển khai:** endpoint URI, phương thức xác thực RS, AS trust, credential lifecycle, token types được phép introspect, metadata cần thiết, allowed audiences/scopes, timeout/cache và hành vi khi AS lỗi.

### 2.2. Xác thực caller và kiểm tra token là hai bài toán

~~~mermaid
flowchart TD
    A["RS POST introspection\nRS credential + token=T"] --> B{"RS đã xác thực?"}
    B -->|Không| C["401 / lỗi caller authentication\nKHÔNG phải trạng thái T"]
    B -->|Có| D{"RS có quyền introspect\nloại token/audience này?"}
    D -->|Không| E["Không tiết lộ metadata:\nactive=false hoặc lỗi theo AS policy"]
    D -->|Có| F{"Token T tồn tại,\ncòn hiệu lực và được chấp nhận?"}
    F -->|Không| G["HTTP 200, active=false"]
    F -->|Có| H["HTTP 200, active=true\nmetadata được phép"]
    H --> I["RS tự check aud/scope/type/tenant"]
    I --> J{"Business authorization?"}
    J -->|Có| K["Cho phép xử lý API"]
    J -->|Không| L["Từ chối API request"]
~~~

**Không diễn giải lỗi 401 khi RS gọi introspection là `active=false` của T.** Đó thường là lỗi **credential của caller**, cần sửa configuration/rotation hoặc xử lý AS authorization; việc tự chuyển thành `active=true` để hệ thống “không gián đoạn” là **fail-open nguy hiểm**.

## 3. Hình dạng một introspection request hợp lệ

RFC 7662 sử dụng HTTP **POST** với `application/x-www-form-urlencoded`:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <encoded-introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<opaque-access-token>&token_type_hint=access_token
~~~

`token_type_hint` là gợi ý tùy chọn để AS tối ưu lookup, **không phải bằng chứng token thực sự là access token**. Nếu thiếu hoặc sai hint, AS áp hành vi của RFC/profile; RS không được dùng hint để thay token type validation.

**Đặc biệt cần nhớ:**

1. `Authorization: Basic ...` trong ví dụ là **credential của resource server đã đăng ký với AS**.
2. Trường body `token=...` là **token người gọi API mang tới**, do RS cần kiểm tra.
3. Không đưa access token vào **URL query**, vì có nguy cơ nằm trong reverse-proxy logs, browser history, analytics hoặc cache.
4. Không gửi token trong `GET /introspect?token=...`; không gửi token thô trong query, trace tags hay exception messages.
5. Sử dụng **HTTPS xác minh certificate và hostname AS**, không bật trust-all TLS.
6. Request form phải URL-encode đúng ký tự trong token; token JWT có dấu `.`, opaque token có thể có ký tự khác.
7. Không theo HTTP redirect sang host không tin cậy khi request đang chứa cả token T và credential của RS.

### 3.1. Response token active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read",
  "client_id": "reports-client",
  "token_type": "Bearer",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "iss": "https://auth.example.com",
  "exp": 1800000900,
  "iat": 1800000000
}
~~~

Đây là response **minh họa**; metadata thực tế phụ thuộc AS, token profile và quyền disclosure của RS. `active=true` không miễn kiểm tra audience/scope/tenant; `token_type=Bearer` mô tả kiểu sử dụng token và **không tự phân biệt refresh token với access token**.

### 3.2. Response token không được chấp nhận

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"active": false}
~~~

Theo RFC 7662, kết quả trên có thể xuất hiện khi token:

- Không tồn tại trên AS hoặc sai;
- Hết hạn, bị thu hồi hoặc grant không còn được chấp nhận;
- Không hợp lệ theo chính sách AS;
- **Không được phép introspect bởi caller này** trong ngữ cảnh cụ thể.

AS không nên trả thêm dữ liệu chi tiết về token inactive cho RS không có quyền, tránh tạo **token oracle** tiết lộ user, client và resource.

### 3.3. Caller authentication sai

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="oauth-introspection"
Cache-Control: no-store
~~~

Đây là **ví dụ** lỗi xác thực caller. Chi tiết `WWW-Authenticate` và body phụ thuộc method/AS, nhưng điểm chính là **request introspection không được chấp nhận vì bên hỏi chưa chứng minh danh tính hợp lệ**, chứ không phải bằng chứng T inactive.

## 4. Những phương thức có thể dùng để xác thực introspection caller

Các AS/profile thường có thể hỗ trợ:

| Phương thức | RS gửi gì? | Điểm mạnh/yếu | Điều kiện |
| --- | --- | --- | --- |
| **HTTP Basic / shared secret** | `Authorization: Basic` chứa RS client ID/secret | Dễ tích hợp; secret dài hạn dễ bị lộ qua logs | AS đã đăng ký caller và cho phép Basic |
| **`client_secret_post`** | Secret trong form body | Hữu ích cho tương thích, nhưng body logs gây lộ | Chỉ khi AS cho phép; hạn chế sử dụng |
| **`private_key_jwt`** | JWT assertion ký bằng private key RS | Không phân phối shared secret cho AS; cần key lifecycle/replay policy | AS hỗ trợ method cho introspection |
| **`client_secret_jwt`** | JWT assertion ký bằng shared secret | Có audience/expiry, vẫn chia secret gốc | AS hỗ trợ method và signing policy |
| **mTLS** | RS trình client certificate tại TLS handshake | PoP certificate; vận hành PKI/proxy phức tạp | Registration, trust chain/cert mapping và TLS topology đúng |
| **Bearer caller credential riêng** | `Authorization: Bearer <RS-introspection-token>` | Có thể hạn ngắn và scopes riêng; phải quản lý vòng đời | **Chỉ** khi AS định nghĩa hỗ trợ và authorize credential này |
| **Cơ chế assertion/workload federation khác** | Bằng chứng do profile xác định | Phù hợp workload identity hiện đại | Hợp đồng/metadata của AS, không tự giả định chuẩn |

**Không có một bảng RFC 7662 bắt buộc mọi AS hỗ trợ tất cả các phương thức trên.** Một số AS chỉ cho Basic; số khác cho mTLS/private-key JWT hoặc một credential riêng dạng bearer. Việc AS hỗ trợ `private_key_jwt` tại **token endpoint** không tự bảo đảm introspection endpoint hỗ trợ nó.

### 4.1. Xác thực là bắt buộc, nhưng method là contract

Resource server cần biết **được đăng ký với AS dưới danh tính nào**, được phép hỏi token của **resource/audience nào**, và **method nào** được sử dụng. Khi đổi method hoặc rotate khóa, phải cập nhật đúng registration tại AS.

### 4.2. Không dùng hai authentication methods trong một request

Nếu contract dùng HTTP Basic, đừng đồng thời đưa `client_secret` vào body hoặc một JWT `client_assertion` “để dự phòng”. Trong OAuth client authentication, dùng nhiều methods có thể gây ambiguity và không phù hợp quy định RFC 6749; introspection client cần tuân **contract của endpoint** và từ chối request mơ hồ.

## 5. HTTP Basic: phương thức tích hợp đơn giản

Một cấu hình thông dụng:

~~~text
AS:                  https://auth.example.com
Introspection URL:   https://auth.example.com/oauth2/introspect
Registered RS ID:    orders-introspection-rs
Client secret:       <from-secret-manager>
Allowed resources:   https://api.example.com/orders
Allowed token type:  access_token
Authentication:      client_secret_basic
~~~

Ví dụ cURL **chỉ dùng placeholder**:

~~~bash
curl --request POST \
  --url 'https://auth.example.com/oauth2/introspect' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --user 'orders-introspection-rs:<secret-from-secure-runtime>' \
  --data-urlencode 'token=<test-access-token>' \
  --data-urlencode 'token_type_hint=access_token'
~~~

**Không nên đưa secret thật trực tiếp vào shell history hoặc process arguments.** Ví dụ này chỉ minh họa HTTP shape; production nên dùng HTTP client/secret manager hoặc cơ chế tránh lộ argument. Tương tự, không chạy test bằng token production và không lưu output chứa PII vào CI artifacts.

### 5.1. OAuth HTTP Basic cần encode đúng

Theo RFC 6749 §2.3.1, client ID và secret được mã hóa bằng quy tắc **`application/x-www-form-urlencoded`** trước khi tạo Basic username/password:

~~~text
encodedId     = formEncode(client_id)
encodedSecret = formEncode(client_secret)

Authorization = "Basic " + BASE64(ASCII(encodedId + ":" + encodedSecret))
~~~

Nếu secret chứa `:`, `+`, `%`, ký tự khoảng trắng hoặc ký tự đặc biệt, bỏ bước form encoding có thể gây lỗi giữa các thư viện. **Base64 không bảo vệ bí mật**; bất kỳ bên nào có header đều có thể giải mã.

### 5.2. Credential cho introspection khác token endpoint credential

Một authorization server có thể cấp **cùng client credential** quyền sử dụng cả token endpoint và introspection endpoint, nhưng **đó là lựa chọn registration/policy**, không phải mặc định cần có. Nên sử dụng **credential riêng cho mỗi resource server** hoặc từng trust domain để thu hồi/hạn quyền dễ dàng.

Ví dụ:

~~~text
orders-api:
  introspection caller = orders-introspection-rs
  allowed token audience = orders-api

payments-api:
  introspection caller = payments-introspection-rs
  allowed token audience = payments-api
~~~

Nếu secret của Orders API bị lộ, hệ thống nên có khả năng **rotate hoặc vô hiệu credential Orders** mà không ảnh hưởng mọi RS khác và không để credential đó xem chi tiết tokens của Payments API.

### 5.3. Đừng nhầm Basic với Bearer

Trong hai request:

~~~http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <end-user-access-token>
~~~

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <rs-id-and-secret>
Content-Type: application/x-www-form-urlencoded

token=<end-user-access-token>
~~~

Bearer là **token client gửi đến RS**; Basic là **RS xác thực với AS**. Hãy tách hai loại header khi log, tracer, retry, secret storage và HTTP client setup.

## 6. Client secret trong body: tương thích nhưng cần kiểm soát

Nếu AS **cụ thể** hỗ trợ `client_secret_post` để xác thực introspection caller:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

token=<test-access-token>
&token_type_hint=access_token
&client_id=orders-introspection-rs
&client_secret=<server-side-secret>
~~~

Form body trên đã được ngắt dòng để dễ nhìn. Thực tế phải URL-encode thành một request body đúng cú pháp. Phương thức **đặt client secret trong body** có nguy cơ bị ghi lại bởi reverse proxy, WAF/APM, request dumps và error reports; tránh dùng nếu Basic hoặc phương thức mạnh hơn phù hợp.

**Không cho phép SPA/mobile gọi trực tiếp endpoint chỉ vì body có secret**: secret trong public code có thể bị lấy và tái sử dụng để introspect tokens của người khác.

### 6.1. Header và body logging phải được bảo vệ ở mọi hop

AS và RS nên redact các trường:

~~~text
Authorization
Proxy-Authorization
client_secret
client_assertion
token
refresh_token
id_token
access_token
~~~

Không dựa vào một middleware application để bảo vệ nếu API Gateway, ingress, service mesh hoặc load balancer vẫn có thể ghi full request/response. Introspection response còn có thể chứa `sub`, `username`, tenant và scopes nhạy cảm; retention/access control cũng cần giới hạn.

## 7. `private_key_jwt` và `client_secret_jwt` cho introspection

Trong các hệ thống hỗ trợ **JWT client authentication (RFC 7523/OIDC profiles)** tại introspection endpoint, RS tạo một **JWT assertion** ngắn hạn để chứng minh credential đã đăng ký. AS xác minh signature/MAC, claims, key binding và policy trước khi trả metadata token.

### 7.1. Hai phương thức JWT khác nhau ở khóa

| Thuộc tính | `private_key_jwt` | `client_secret_jwt` |
| --- | --- | --- |
| Khóa ký | Private key bất đối xứng | Shared secret đối xứng |
| Bên kiểm tra | AS có public key tin cậy của RS | AS có secret của RS |
| Thuật toán ví dụ | RS256/PS256/ES256 theo AS allowlist | HS256 theo AS allowlist |
| Lợi ích | AS không cần giữ private key; hỗ trợ key rotation/JWKS | Assertion có audience/expiry; vẫn dùng shared secret |
| Rủi ro chính | Private key compromise, `kid`/JWKS confusion | Shared secret compromise và assertion replay |

`private_key_jwt` **không có nghĩa introspection response là JWT**. RFC 7662 cơ bản trả JSON; một extension khác có thể dùng JWT introspection response theo profile được thỏa thuận. Hai vấn đề **xác thực request** và **định dạng response** phải được xem độc lập.

### 7.2. Ví dụ client assertion cho introspection

JSON payload minh họa:

~~~json
{
  "iss": "orders-introspection-rs",
  "sub": "orders-introspection-rs",
  "aud": "https://auth.example.com/oauth2/introspect",
  "iat": 1800000000,
  "exp": 1800000060,
  "jti": "unique-rs-assertion-identity-001"
}
~~~

JWS protected header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "orders-rs-key-2026-11",
  "typ": "JWT"
}
~~~

Giải thích:

- `iss` và `sub` xác định **introspection client/RS** theo registration/profile.
- `aud` xác định **AS/introspection endpoint dự kiến**; **giá trị nào được chấp nhận phụ thuộc contract AS**, không tự dùng audience token endpoint nếu AS yêu cầu introspection audience riêng.
- `exp` giới hạn thời hạn assertion, với `iat`/`nbf` khi policy dùng; không dùng assertion tồn tại hàng ngày như client secret thay thế.
- `jti` giúp phát hiện **replay** nếu AS áp chính sách one-time assertion; cache phải có tính nguyên tử và TTL phù hợp.
- `kid` chỉ giúp **chọn khóa trong tập khóa đã đăng ký của đúng RS**, không phải chỉ thị tin một URL/JWKS lạ.

**Không nhầm** `iss=orders-introspection-rs` trong **RS client assertion** với `iss=https://auth.example.com` trong **access token T**. Chúng có identity/audience và validation rules hoàn toàn khác nhau.

### 7.3. POST sử dụng JWT assertion

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<test-access-token>
&token_type_hint=access_token
&client_id=orders-introspection-rs
&client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer
&client_assertion=<short-lived-signed-rs-assertion>
~~~

Body được xuống dòng để giải thích; thực tế cần form URL encoding. Đây là **profile minh họa chỉ áp dụng nếu AS hỗ trợ JWT client authentication cho introspection**. Không thêm `Authorization: Basic` vào request này khi method đã chọn là JWT assertion.

### 7.4. AS kiểm tra JWT assertion theo danh tính RS

AS cần thực hiện:

1. Xác định registration của caller và method được phép.
2. Xác minh JWS `alg` theo **allowlist cho chính caller/method**, không theo `alg` tùy ý.
3. Chọn key/secret đã đăng ký **cho đúng RS**, kiểm tra `kid`, `use`, key type khi có.
4. Không tải `jku`, `x5u` hoặc JWKS URL từ assertion chưa xác minh rồi coi đó là nguồn tin cậy; tránh SSRF/key injection.
5. Validate signature/MAC, `iss`, `sub`, `aud`, `exp`, policy thời gian.
6. Kiểm tra `jti` replay nếu profile yêu cầu và **atomic insert-if-absent** trên nhiều AS nodes.
7. Phân quyền caller introspect đúng **token type, audience, resource/tenant** đã cho.

**Một assertion có chữ ký hợp lệ mới chỉ là bằng chứng client identity**. Nếu nó đến từ RS của Orders nhưng token được hỏi dành riêng cho Payments, AS không được tự động tiết lộ metadata của Payments token.

## 8. mTLS: dùng certificate để xác thực bên hỏi

Với **mutual TLS (mTLS)**, Resource Server dùng **client certificate/private key** tại kết nối đến AS. TLS handshake chứng minh caller sở hữu private key; AS phải ánh xạ certificate identity/public key tới **đúng introspection caller đã đăng ký**, đồng thời kiểm tra quyền introspection.

~~~mermaid
sequenceDiagram
    autonumber
    participant RS as Orders RS (client cert + key)
    participant AS as Authorization server
    RS->>AS: TLS handshake + client certificate
    AS->>AS: Validate trust chain / registered cert identity
    AS-->>RS: mTLS channel được thiết lập
    RS->>AS: POST /introspect token=T
    AS->>AS: Map certificate → orders-introspection-rs
    AS->>AS: Check caller's token visibility policy
    AS-->>RS: active + metadata được phép hoặc từ chối
~~~

Các phương thức mTLS trong **RFC 8705** gồm:

| Loại | Cách AS xác định client |
| --- | --- |
| **`tls_client_auth`** | Chain/trust và subject DN/SAN theo client registration |
| **`self_signed_tls_client_auth`** | Certificate/key tự ký đã đăng ký với AS |

**Điều kiện tiên quyết:** AS phải hỗ trợ việc áp phương thức này cho **introspection endpoint**. Không chỉ kiểm tra “TLS có certificate” rồi bỏ qua việc ánh xạ **certificate → registered resource server**.

### 8.1. Certificate authentication khác certificate-bound access token

- **mTLS để RS xác thực với introspection endpoint:** AS xác minh **resource server đang hỏi**.
- **mTLS-bound access token:** RS xác minh client gửi **token T** sở hữu certificate tương ứng với `cnf` metadata của **T**.

Một RS có thể dùng **mTLS để gọi introspection** nhưng token T lại là **Bearer access token** do frontend gửi. Đây là hai kết nối khác nhau, hai loại identity khác nhau. Không mặc định credential/certificate của RS trong outbound request chứng minh end-user client sở hữu khóa của T.

### 8.2. Xác thực qua gateway/service mesh cần mô hình trust rõ

~~~text
Orders RS --mTLS--> Gateway --TLS/mTLS--> AS

AS nhìn thấy certificate nào?
  - Cert Orders RS gốc?
  - Hay cert của gateway cho hop tới AS?
~~~

Nếu mTLS bị terminate ở gateway, AS thường chỉ thấy **chứng chỉ của gateway ở hop cuối**. Khi phải chuyển client identity, cần một cơ chế đáng tin: gateway xác thực cert của RS, **strip các header do caller tự gắn**, truyền identity qua kênh bảo vệ và ngăn caller bypass gateway. **Không chấp nhận `X-Client-Cert` do Internet client tự khai như chứng nhận mTLS**.

### 8.3. Certificate rotation

Certificate hết hạn hoặc key bị rotate có thể làm introspection **đồng loạt thất bại**, từ đó RS không thể xác thực token mới. Cần theo dõi expiry, dual-cert overlap theo AS policy, kiểm thử trước cutover, không tắt certificate validation để “sửa nhanh”.

## 9. Bearer credential riêng để xác thực caller, nếu AS cho phép

Một số AS/triển khai cho phép RS mang **access token riêng dành cho introspection endpoint**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Bearer <rs-introspection-caller-token>
Content-Type: application/x-www-form-urlencoded

token=<end-user-access-token-to-check>
~~~

**Hai token trong ví dụ có hai mục đích khác nhau:**

- Header Bearer: **credential xác thực/ủy quyền cho RS gọi introspection** (theo AS policy).
- Form `token`: **access token T được RS yêu cầu introspect**.

Đây là **khả năng tùy chọn theo AS**, không phải phương thức mà RFC 7662 bắt buộc hỗ trợ. Token caller phải có issuer, audience, scope/permission được AS kiểm tra; không dùng token T trong header để “tự xác thực bằng chính token cần hỏi”.

### 9.1. Cần chính sách riêng cho bearer caller credential

Nếu RS dùng bearer caller token, cần bảo đảm:

- Token được cấp **riêng cho AS introspection API**, audience khớp endpoint/phân hệ AS.
- Scope/permission chỉ cho đọc trạng thái token của resource phù hợp.
- TTL ngắn, secure storage, rotation/revocation và chống token theft.
- Nếu AS hỗ trợ DPoP/mTLS binding cho caller token, xác minh sender proof theo contract.
- Không cho token client của end user có scope business thông thường tự trở thành quyền introspection.

**Bearer authentication của RS không phải `active=true` của T.** AS cần xác minh caller trước rồi mới đánh giá token được hỏi.

## 10. Discovery: chọn đúng introspection endpoint và methods

Authorization server có thể công bố introspection metadata theo **RFC 8414 — OAuth 2.0 Authorization Server Metadata**:

~~~json
{
  "issuer": "https://auth.example.com",
  "introspection_endpoint": "https://auth.example.com/oauth2/introspect",
  "introspection_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt",
    "tls_client_auth"
  ],
  "introspection_endpoint_auth_signing_alg_values_supported": [
    "RS256",
    "PS256"
  ]
}
~~~

Đây chỉ là **metadata minh họa**. Các trường có thể không xuất hiện ở từng AS; việc AS quảng bá method chỉ nói **method được hỗ trợ ở cấp endpoint**, không chứng minh client hiện tại đã được đăng ký sử dụng method ấy.

### 10.1. Discovery metadata phải là trusted input

Để tránh gửi token hoặc client credential tới endpoint giả:

1. Có **trust registry/allowlist issuer** từ cấu hình đã được phê duyệt.
2. Lấy metadata qua **HTTPS**, xác minh certificate/hostname và issuer identity đúng policy.
3. Chỉ dùng **`introspection_endpoint` thuộc issuer tin cậy** và đúng endpoint được đăng ký/cho phép.
4. Không lấy URL introspection từ `iss` trong JWT chưa được xác minh hoặc query parameter của browser.
5. Không tự theo arbitrary redirects từ metadata/token endpoint làm lộ bearer/secret.
6. Cân nhắc chặn truy cập mạng nội bộ/loopback không hợp lệ, DNS rebinding và egress policies để giảm **SSRF**.
7. Đặt timeout/size limits cho discovery và introspection; không để API call block vô thời hạn.

### 10.2. Multi-issuer phải chọn AS trước khi gửi token

Một API có thể chấp nhận token từ nhiều issuer được tin. Với opaque token, RS **không nhất thiết đọc được issuer từ token**. Nó phải có cơ chế routing tin cậy: phân vùng endpoint, client registration, token prefix do AS định nghĩa hoặc issuer selection theo request context đã được xác minh.

**Không fan-out cùng raw token tới mọi AS tùy tiện**: token có thể bị lộ sang issuer không phải chủ sở hữu, latency tăng và xuất hiện token oracle. Nếu cần nhiều issuers, phải thiết kế lookup/routing được kiểm soát và chỉ gửi token đến AS phù hợp.

## 11. Phân quyền introspection caller theo resource và token type

**Xác thực caller thành công không đồng nghĩa caller được phép xem mọi token.** AS phải có **access control riêng** cho endpoint, ví dụ:

~~~text
Introspection caller: orders-introspection-rs
Registered audience: https://api.example.com/orders
Allowed token purpose: access_token
Allowed metadata:
  active, iss, aud, exp, sub, scope, client_id

Không được phép:
  - introspect refresh token của end user
  - xem metadata token chỉ dành Payments API
  - lấy email/phone/roles nếu không cần
~~~

**Mẫu policy minh họa**, không phải các field bắt buộc trong RFC 7662.

### 11.1. Áp principle of least privilege

Mỗi RS nên có:

- **Danh tính** introspection caller riêng (client registration/credential).
- **Audience/resource** được phép kiểm tra.
- **Token purpose/type** được phép introspect.
- **Claims/metadata** thực sự cần để làm authorization.
- **Rate/quotas** phù hợp tải thực tế.
- **Audit/rotation** và khả năng vô hiệu hóa riêng khi compromise.

Không dùng một `introspection-admin-secret` được copy cho mọi microservice. Nếu secret đó lộ, attacker có thể biến introspection endpoint thành nguồn metadata trên quy mô toàn hệ thống.

### 11.2. Quy tắc tiết lộ metadata của AS

Ví dụ RS Orders hỏi một token chỉ dành Payments:

~~~text
Caller: orders-introspection-rs  [authenticated]
Token:  aud=https://api.example.com/payments  [active elsewhere]

AS policy: caller không được introspect token Payments.
Response: hạn chế/không tiết lộ metadata; active=false
          hoặc lỗi policy thích hợp theo AS contract.
~~~

Với RFC 7662, **`active=false` còn có thể phản ánh caller không được phép introspect token**. RS không nên phân biệt “token bị revoke” với “token dành resource khác” từ response để tránh rò rỉ.

### 11.3. Refresh token là credential khác access token

Refresh token thường được đưa tới **token endpoint** để đổi access token mới, **không được dùng làm Bearer credential gọi business API**. Một refresh token có thể được AS xem là active trong bối cảnh của token endpoint nhưng RS không vì thế được quyền nhận nó như access token.

`token_type_hint=access_token` chỉ là hint, không chứng minh loại token. Nếu AS hỗ trợ introspection cho nhiều token types, RS/API phải có **token purpose validation** đáng tin: token được chấp nhận cho resource endpoint nào, profile nào, client/audience nào. Không dựa duy nhất vào `token_type=Bearer` để phân biệt access token với refresh token.

### 11.4. Audience và scope tại RS vẫn là phép kiểm tra riêng

Sau một response `active=true` đáng tin, RS còn phải:

1. Kiểm tra `iss` và nguồn AS theo contract.
2. Kiểm tra `aud` chứa API/resource đúng; nếu AS không trả `aud` nhưng profile bắt buộc, **fail closed hoặc sửa hợp đồng với AS**, không suy từ request client.
3. Kiểm tra `scope` được cấp (không phải scope client từng xin).
4. Phân biệt **user-delegated vs app-only principal**.
5. Kiểm tra tenant, membership, object ownership, business rules.
6. Kiểm tra DPoP/mTLS sender binding nếu token T yêu cầu.

**`active=true` không phải giấy phép đọc mọi tài nguyên**. Authentication của RS tại introspection endpoint chỉ bảo vệ việc hỏi trạng thái token, không thay authorization của business API.

## 12. Java 17: introspection qua HTTP Basic an toàn

Ví dụ sau cho thấy cách **Orders API** gửi token cần kiểm tra đến introspection endpoint và tự xác thực bằng **client ID/secret của RS**. Sử dụng Java `HttpClient`, UTF-8 form encoding, HTTPS endpoint cố định và không tự follow redirects.

Để giữ trọng tâm ở **client authentication**, đoạn code dùng **Jackson `ObjectMapper`** để parse JSON. Jackson là thư viện ngoài JDK và cần được khai báo qua build dependencies của ứng dụng. Đây là **ví dụ minh họa**, không phải SDK OAuth hoàn chỉnh.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

public final class OrdersIntrospectionClient {
    private static final URI INTROSPECTION_URI = URI.create(
        "https://auth.example.com/oauth2/introspect");

    private final HttpClient http;
    private final ObjectMapper mapper = new ObjectMapper();
    private final String basicAuthorization;

    public OrdersIntrospectionClient(
            String introspectionClientId,
            String introspectionClientSecret) {
        if (introspectionClientId == null
                || introspectionClientId.isBlank()
                || introspectionClientSecret == null
                || introspectionClientSecret.isBlank()) {
            throw new IllegalArgumentException(
                "Missing resource-server introspection credential");
        }

        String pair = form(introspectionClientId)
            + ":" + form(introspectionClientSecret);
        this.basicAuthorization = "Basic " +
            Base64.getEncoder().encodeToString(
                pair.getBytes(StandardCharsets.US_ASCII));

        this.http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
    }

    public JsonNode introspect(String rawAccessToken)
            throws IOException, InterruptedException {
        if (rawAccessToken == null || rawAccessToken.isBlank()) {
            throw new IllegalArgumentException("Missing access token");
        }

        String formBody = "token=" + form(rawAccessToken)
            + "&token_type_hint=" + form("access_token");

        HttpRequest request = HttpRequest.newBuilder(INTROSPECTION_URI)
            .timeout(Duration.ofSeconds(8))
            .header("Authorization", basicAuthorization)
            .header("Content-Type",
                "application/x-www-form-urlencoded")
            .header("Accept", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(
                formBody, StandardCharsets.UTF_8))
            .build();

        HttpResponse<String> response = http.send(
            request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

        if (response.statusCode() == 401
                || response.statusCode() == 403) {
            // Caller RS credential/policy problem;
            // KHÔNG suy ra trạng thái của rawAccessToken.
            throw new IllegalStateException(
                "Introspection caller authentication/authorization failed");
        }
        if (response.statusCode() != 200) {
            // 5xx, redirect hoặc lỗi khác: KHÔNG fail open.
            throw new IllegalStateException(
                "Introspection unavailable or rejected");
        }

        // Production phải giới hạn response body size trước khi parse.
        JsonNode root = mapper.readTree(response.body());
        JsonNode active = root == null ? null : root.get("active");
        if (active == null || !active.isBoolean()) {
            throw new IllegalStateException(
                "Malformed introspection response");
        }

        // Chỉ trả metadata đã parse cho security decision nội bộ.
        // Caller tiếp tục check issuer, audience, scope, time, tenant.
        return root;
    }

    private static String form(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
~~~

### 12.1. Cách gọi từ lớp bảo mật backend

~~~java
// ClientId/ClientSecret phải tới từ secret manager/config bảo vệ.
OrdersIntrospectionClient introspection =
    new OrdersIntrospectionClient(
        introspectionClientId,
        introspectionClientSecret);

JsonNode result = introspection.introspect(accessTokenFromRequest);

if (!result.get("active").booleanValue()) {
    throw new SecurityException("Access token not accepted");
}

// ĐỌC TIẾP: contract-bound iss/aud/scope/exp/token purpose,
// rồi tenant và object-level authorization.
// KHÔNG coi active=true là allowRequest().
~~~

Các biến `introspectionClientId`, `introspectionClientSecret` và `accessTokenFromRequest` là **dữ liệu được cung cấp bởi lớp gọi**, không phải biến global có sẵn. Snippet thứ hai chỉ mô tả cách sử dụng, không phải một lớp Java độc lập.

### 12.2. Giới hạn cần xử lý trong production

1. **Secret storage:** không đưa credential thật vào source, Git, image, test fixtures hoặc logs. Dùng secret manager/workload identity phù hợp.
2. **TLS:** để JDK xác minh CA/hostname AS; kiểm soát trust store và TLS settings, không dùng trust-all.
3. **Response size/schema:** giới hạn body bytes, HTTP content type, JSON depth/schema và thời gian parse để giảm DoS.
4. **Connection pool:** dùng HTTP client được quản lý theo vòng đời ứng dụng; không tạo mới một connection pool cho từng API request.
5. **Timeout/circuit breaker:** không retry không giới hạn; phân biệt network/AS outage với token inactive.
6. **Token privacy:** không in `rawAccessToken`, request body, Basic header, full response hoặc user claims vào exception/log.
7. **Audience/scope/time:** bắt buộc kiểm tra **sau khi** nhận `active=true`, theo metadata contract.
8. **Cache:** nếu muốn cache, phải có TTL/revocation policy và bảo vệ cache; không cache result vô hạn.
9. **Authentication method:** code này chỉ hỗ trợ Basic; nếu issuer đòi JWT assertion/mTLS, phải thay HTTP authentication client phù hợp.
10. **Error mapping:** `IllegalStateException` là code minh họa; ứng dụng thật cần exception types để phân biệt **`401` token invalid** với **`503` dependency unavailable**.

### 12.3. Không để client tự quyết định địa chỉ introspection

Sai:

~~~java
// Anti-pattern: URL do request caller đưa vào.
URI uri = URI.create(request.getParameter("introspection_url"));
http.send(HttpRequest.newBuilder(uri) /* ... */.build(), handler);
~~~

Đúng hơn: endpoint đã được **allowlist và ràng buộc issuer**, không lấy từ attacker-controlled request/JWT header. Nếu token opaque không cho biết issuer, dùng routing/trust registry **được thiết kế trước**, không dò gửi raw token khắp Internet.

## 13. Spring Security Resource Server: cấu hình Basic introspection

Với **Spring Boot 3 / Spring Security 6**, cấu hình cơ bản cho opaque token introspection thường là:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-introspection-rs
          client-secret: ${ORDERS_INTROSPECTION_SECRET}
~~~

Tham số `client-id`/`client-secret` ở đây là **credential của Orders Resource Server dùng gọi AS**, không phải `client_id` của trình duyệt Reports App đã xin token. Placeholder `${ORDERS_INTROSPECTION_SECRET}` trong YAML cần được resolve từ môi trường/secret manager bảo vệ; **không commit secret thật**.

### 13.1. Bảo vệ các API routes

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersOpaqueResourceSecurity {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Spring Security thường chuyển scopes được AS introspection trả về thành `SCOPE_` authorities. **Không nhầm** `hasRole("orders.read")` (thường tìm `ROLE_orders.read`) với `hasAuthority("SCOPE_orders.read")`. Mapping phụ thuộc phiên bản và hình dạng metadata trả về.

**Bản cấu hình trên chưa đủ để khẳng định production an toàn**: vẫn cần kiểm tra issuer/audience/token purpose, tenant/ownership, timeout, cache, CSRF/CORS theo kiến trúc và phương thức xác thực RS với AS. Spring không thể biết policy tenant từ tên scope `orders.read`.

### 13.2. Cấu hình mTLS hoặc `private_key_jwt` trong Spring

Các thuộc tính Basic nêu trên **không tự bật mTLS hoặc private-key JWT**. Nếu AS yêu cầu một method khác, resource server cần một **HTTP introspection client** và signer/TLS configuration phù hợp, thường tích hợp qua cơ chế `OpaqueTokenIntrospector` được Spring Security hỗ trợ.

Các bước kiến trúc:

~~~text
Incoming Bearer T
    -> Spring OAuth2 Resource Server filter
    -> custom/configured OpaqueTokenIntrospector
        -> mTLS / JWT-assertion client authentication
        -> trusted AS introspection endpoint
        -> strict schema and state validation
    -> validated Authentication/principal/authorities
    -> scope, audience, tenant, object-level authorization
~~~

**Không cài một HTTP client “vô hiệu hóa certificate validation” chỉ để mTLS chạy**. Cần trust store đúng, client key material được bảo vệ, certificate mapping ở AS và kiểm soát proxy topology. API/class constructors có thể thay đổi theo version Spring; phải kiểm tra version thực tế khi triển khai.

### 13.3. Đừng test bằng mock `jwt()` rồi cho rằng introspection đã được kiểm tra

Trong Spring Security integration tests, việc tạo mock Authentication bằng `jwt()` hoặc mock principal có thể bỏ qua outbound HTTP introspection, Basic/mTLS/JWT caller authentication và AS policy. Cần test cả:

- Spring Security filter chain nhận Bearer token;
- `OpaqueTokenIntrospector` thật hoặc test server mô phỏng introspection;
- Outbound RS credential đúng/sai;
- `active=true/false` và 401/403/timeout/5xx từ AS;
- Scope/audience/tenant authorization tại API.

## 14. Phân biệt introspection caller authentication với token validation

### 14.1. JWT offline có thể không cần introspection

Một RS có thể xác minh JWT access token **offline** bằng JWS signature, issuer trust, algorithm allowlist, JWKS và claims. Với JWT hợp lệ và theo kiến trúc chấp nhận TTL, **không phải request nào cũng cần gọi AS**.

Tuy nhiên, nếu RS muốn kiểm tra **grant hiện hành hoặc revocation state**, nó có thể introspect JWT **nếu AS hỗ trợ loại token này**. Khi đó:

- JWT verification và introspection thực hiện các kiểm tra **khác nhau**;
- Nếu policy yêu cầu cả hai, kết quả mâu thuẫn phải **fail closed**;
- Không bỏ audience/scope/token type validation chỉ vì AS trả active;
- Không dùng JWT header `jku` hoặc unverified `iss` để quyết định URL AS.

### 14.2. Opaque token thường phụ thuộc AS lookup/introspection

Opaque token không cho RS đọc trực tiếp claims bằng cách parse chuỗi. AS introspection trả trạng thái/metadata theo contract; do đó **client authentication của RS tại endpoint** trở thành một phụ thuộc quan trọng cho availability và an toàn.

Một lỗi rotate Basic secret có thể khiến mọi opaque token requests qua RS bị chặn. **Không giải quyết bằng cách tắt introspection cho request đang có token**. Thay vào đó, thiết kế secret rotation overlap, multi-instance deployment, backup credential policy và timeout/cache an toàn.

### 14.3. Access token khác ID token và refresh token

| Token | Intended use | RS có nên nhận để gọi API? |
| --- | --- | --- |
| **Access token** | Quyền truy cập resource theo audience/scope | **Có**, nếu đúng profile và validation |
| **ID token** | OIDC client xác minh user authentication result | **Không**, không dùng thay access token |
| **Refresh token** | OAuth client đổi token tại token endpoint | **Không**, không dùng như Bearer access token |
| **JWT client assertion** | RS/client xác thực với AS endpoint tương ứng | **Không**, không phải credential gọi business API |

Một AS có thể trả `active=true` cho refresh token khi bên gọi có quyền và profile cho phép introspection token đó. RS không được coi mọi `active=true` đều là **access token của mình**.

## 15. Metadata bắt buộc theo contract của resource server

RFC 7662 định nghĩa `active` và nhiều metadata tùy chọn. Hệ thống cần **thỏa thuận schema tối thiểu** cho loại API, không dùng dữ liệu client tự khai để bù cho trường thiếu.

| Metadata | Vì sao RS cần? | Hành vi nếu thiếu/sai |
| --- | --- | --- |
| **`active` boolean** | Có được AS chấp nhận ở ngữ cảnh này không? | Không tiếp tục nếu thiếu/không phải boolean |
| **`iss`** | Ràng buộc issuer đáng tin khi profile yêu cầu | Deny nếu contract bắt buộc mà thiếu/sai |
| **`aud`** | Token có dành cho chính RS không? | Deny nếu RS yêu cầu audience rõ |
| **`scope`** | Có quyền chức năng cần thiết không? | Thiếu quyền → deny |
| **`exp`, `nbf`** | Hạn và thời điểm bắt đầu hiệu lực | Áp policy thời gian; không cache quá expiry |
| **`sub`** | Định danh user/service principal | Diễn giải theo grant/profile, không tự coi là user |
| **`client_id`** | OAuth client được cấp token | Không tự suy thành quyền business |
| **`token_type`** | Bearer/kiểu sử dụng token theo profile | Không thay token-purpose validation |
| **`tenant_id` custom** | Ràng buộc organization của grant | Kiểm tra với DB/resource; không chuẩn mọi AS |
| **`cnf`** | Public-key/certificate confirmation khi sender-constrained | Verify DPoP/mTLS proof nếu token yêu cầu |

### 15.1. `active=true` chưa đủ

Ví dụ:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com",
  "aud": "https://api.example.com/payments",
  "scope": "payments.read",
  "sub": "user-42"
}
~~~

Orders API phải từ chối; token này **đang active cho Payments**, không cho Orders. Việc Orders RS credential đã được AS xác thực không thay audience binding.

### 15.2. Token có nhiều audiences

Một số profile cho phép token có nhiều audiences. AS và RS phải áp hợp đồng về **multi-resource scopes** để tránh rằng cùng scope `read` bị hiểu lẫn giữa Orders/Payments. RS không được chỉ thấy `aud` có Orders rồi dùng scopes không gắn đúng resource nếu contract phân quyền theo resource khác nhau.

### 15.3. Tenant và object-level authorization

Một token có `tenant_id=acme`, `scope=orders.read` không được dùng để đọc order của Globex:

~~~sql
SELECT *
FROM orders
WHERE id = :order_id
  AND tenant_id = :verified_tenant_id;
~~~

`:verified_tenant_id` phải đến từ **nguồn grant/metadata đã xác minh**, đồng thời DB kiểm tra record thuộc tenant đó. **Không lấy header `X-Tenant-Id` do caller tự khai làm authority**.

### 15.4. Principal là user hay workload?

Một token từ `client_credentials` có thể có `sub` là service principal hoặc claim client riêng, tùy AS/token profile. Nếu Orders API có endpoint “đọc đơn hàng của tôi”, phải phân biệt **user-delegated** và **app-only**. Client authentication của RS khi introspect **không biến app-only token thành user token**.

## 16. Độ tin cậy của response và tránh thay đổi quyền trong quá trình truyền

Introspection response cơ bản theo RFC 7662 là JSON qua HTTPS. Resource server phải chỉ tin response từ **đúng AS** đã xác thực TLS, trong transaction tương ứng, không từ:

- JSON body do client API gửi kèm;
- HTTP header `X-User-Id` hoặc `X-OAuth-Scope` tự khai;
- Cache shared mà RS khác có thể ghi;
- Kết quả của issuer không liên quan;
- Một URL/host chưa được allowlist;
- Callback/redirect không được ràng buộc request.

### 16.1. Introspection response dạng JWT là một extension riêng

**RFC 9701 — JWT Response for OAuth Token Introspection** có thể được triển khai nếu AS/RS hỗ trợ. Trong profile đó, RS còn phải xác minh chữ ký, issuer, audience và các claims của **JWT response** theo hợp đồng. Điều này **không thay** client authentication của RS khi gửi introspection request.

**Ba thứ khác nhau dù đều có thể là JWT:**

1. **JWT access token T** đang được hỏi.
2. **JWT client assertion** dùng RS xác thực với AS.
3. **JWT introspection response** nếu sử dụng extension được AS hỗ trợ.

Không lấy một JWT validator duy nhất rồi dùng cho cả ba: mỗi loại có **issuer, audience, token type, keys và mục tiêu sử dụng khác nhau**.

### 16.2. Certificate pinning và trust store

HTTPS cần xác minh chain và hostname AS. Pinning certificate/key chỉ nên dùng khi có **quy trình rotation/cập nhật pin rõ ràng**, không thay thế CA validation một cách tùy tiện. mTLS xác thực client cần thêm key store cho RS certificate và AS certificate mapping.

**Không chấp nhận self-signed server cert bất kỳ vì client cũng dùng `self_signed_tls_client_auth`.** Hai bài toán TLS server identity và OAuth client certificate authentication khác nhau.

## 17. Gateway và kiến trúc microservices

Một hệ thống có API gateway kiểm tra token trước nhiều microservices:

~~~mermaid
flowchart TD
    C["Ứng dụng OAuth client"] --> G["API Gateway / Resource Server"]
    G --> AS["AS introspection endpoint\nRS caller auth"]
    G --> ORD["Orders service"]
    G --> PAY["Payments service"]
    ORD --> DB1[("Orders DB")]
    PAY --> DB2[("Payments DB")]
~~~

Thiết kế phải trả lời:

- Gateway có phải **RS duy nhất** gọi introspection, hay từng service cũng introspect?
- Credential của gateway được phép xem tokens cho **những audiences nào**?
- Backend làm sao tin **identity/claims** mà gateway truyền mà không nhận headers giả từ Internet?
- Nếu gateway giữ privileged introspection credential, blast radius khi secret bị lộ là bao nhiêu?
- Service có tiếp tục kiểm tra **object-level authorization**, thay vì hoàn toàn tin scope do gateway báo không?
- Nếu gateway bị bypass qua internal network, backend có còn bảo vệ authentication/authorization không?

### 17.1. Không chuyển full introspection metadata bằng header không tin cậy

Sai:

~~~http
GET /internal/orders HTTP/1.1
Host: orders-internal.example
X-User-Id: admin
X-Scope: orders.write
X-Tenant-Id: globex
~~~

Nếu backend nhận các headers này trực tiếp từ bất kỳ caller, attacker có thể bỏ qua gateway. Cần **network isolation**, strip/overwrite headers ở gateway, mutual authentication giữa gateway và service, signed identity assertion nếu thiết kế có, và authorization nội bộ phù hợp.

### 17.2. Từng microservice tự introspect cũng có trade-off

Ưu điểm: policy riêng theo service, giảm tin mù vào gateway. Nhược điểm: nhiều outbound introspection calls, nhiều credentials và dependency AS. Một gateway tập trung có thể giảm tải, nhưng **không tự giảm trách nhiệm kiểm tra business resource** ở từng service.

### 17.3. Không chia sẻ một Basic secret qua toàn hệ thống

Mỗi service nên có client registration/credential và permission độc lập nếu thiết kế cho phép. Một secret dùng chung cho gateway, Orders, Payments, Reporting tạo điểm thất bại lớn và khó thu hồi từng service khi compromise.

## 18. AS không khả dụng: không được fail open

Khi AS timeout, 5xx hoặc RS credential hết hạn, RS có thể **không đủ bằng chứng để xác nhận token T hợp lệ**.

~~~java
// SAI - không bao giờ dùng trong production:
try {
    return introspectionClient.introspect(rawToken);
} catch (Exception error) {
    return allowWithAllScopes(); // FAIL OPEN
}
~~~

Không được mặc định token active hoặc tự cấp quyền admin vì AS không sẵn sàng.

### 18.1. Các loại lỗi phải phân biệt

| Kết quả outbound introspection | Ý nghĩa | Cách xử lý RS |
| --- | --- | --- |
| HTTP 200, `active=true` | Token được AS xem là hoạt động trong ngữ cảnh | Tiếp tục check metadata + quyền resource |
| HTTP 200, `active=false` | Token không được AS chấp nhận/không được tiết lộ | Từ chối token, thường API `401` |
| HTTP 401 (caller auth fail) | RS credential/method sai/hết hiệu lực | Không nhận request; báo lỗi vận hành, không suy token inactive |
| HTTP 403 (caller unauthorized) | RS thiếu quyền gọi endpoint/token | Không nhận request; kiểm tra permission/AS policy |
| HTTP 429 (rate limit) | AS đang giới hạn lưu lượng | Backoff/circuit-breaker, không flood |
| HTTP 5xx | AS gặp lỗi | Fail closed, có thể trả API `503` |
| Timeout/network failure | Không có quyết định trạng thái token | Fail closed, timeout và availability policy |
| HTTP 302/307 sang host khác | Endpoint thay đổi/redirect đáng ngờ | Không gửi lại credentials/token sang host không tin |
| JSON không có `active` boolean | Response sai contract | Fail closed; cảnh báo integration |

**Chọn HTTP status API phía RS:** `401 invalid_token` phù hợp với token thực sự bị từ chối; khi **AS dependency chưa xác định được kết quả** có thể dùng `503 Service Unavailable` thay vì báo user token invalid. HTTP mapping cụ thể phụ thuộc API contract; không tiết lộ RS secrets/AS internals.

### 18.2. Timeout, retry và circuit breaker

- Đặt connect/request timeouts và tổng budget phù hợp API latency.
- Chỉ retry lỗi mạng/5xx có giới hạn; tránh retry khi 401 credential sai.
- Exponential backoff/jitter và circuit breaker để không làm AS sụp vì thác request.
- Bảo vệ thread pool/connection pool, giới hạn concurrency và queue.
- Nếu có cache active còn hợp lệ, chỉ sử dụng theo **chính sách đã phê duyệt**; không kéo dài TTL khi AS down.
- Với thao tác nhạy cảm, có thể buộc gọi AS mới thay vì dùng cache stale.

### 18.3. Không biến toàn bộ API thành token oracle khi AS lỗi

AS có thể không tiết lộ liệu một token tồn tại hay không. RS không nên dùng chi tiết lỗi nội bộ để tiết lộ cho client API rằng token thuộc user nào, bị revoke lúc nào hoặc RS client nào đang kiểm tra. Lỗi client-facing nên có nội dung tối giản.

## 19. Cache kết quả introspection mà không phá revocation

Với opaque token, gọi AS cho **mọi API request** có thể gây latency và tải lớn. RS có thể cache một số kết quả introspection trong khoảng thời gian được kiểm soát, nhưng **positive cache (`active=true`) tạo cửa sổ chấp nhận trạng thái cũ** sau khi token/grant bị thu hồi.

### 19.1. Ví dụ thời gian thu hồi

~~~text
10:00:00  Orders RS introspect T -> active=true, exp=10:15
10:00:01  RS cache trong 60 giây
10:00:20  User/admin revoke grant của T
10:00:40  RS vẫn còn cache active=true
10:01:01  Cache hết TTL, RS introspect -> active=false
~~~

**Client authentication của RS không làm cache cũ tự cập nhật.** Dù AS biết token bị thu hồi, RS có thể tiếp tục chấp nhận đến khi TTL hết nếu kiến trúc không có invalidation/push events.

### 19.2. Công thức TTL giới hạn

Khi AS trả `exp` và contract cho phép cache:

\[
\mathrm{TTL}_{cache}
= \min(\mathrm{TTL}_{policy},
       \max(0,\mathrm{exp}-\mathrm{now}))
\]

Nếu `exp` không có hoặc không hợp lệ, **không cache vô hạn**. Chọn TTL ngắn theo policy hoặc không cache; kiểm tra clock skew và token purpose. Với thao tác nhạy cảm, có thể dùng introspection mới hoặc một state check bổ sung.

| Kiểu cache | Tác dụng | Rủi ro |
| --- | --- | --- |
| Không cache | Trạng thái AS mới nhất theo request | Latency, AS availability |
| Positive cache rất ngắn | Giảm tải mà hạn chế stale state | Token bị revoke có thể còn được chấp nhận trong TTL |
| Positive cache dài | Tối ưu latency | Revocation, membership changes chậm có hiệu lực |
| Negative cache ngắn | Hạn chế spam token ngẫu nhiên | Có thể giữ inactive khi trạng thái thay đổi |
| Push invalidation + TTL | Thu hồi nhanh hơn | Event loss/order và fallback phải được thiết kế |

### 19.3. Cache key không được dựa vào raw token công khai

Một key có thể dùng fingerprint được bảo vệ:

~~~text
cache_key = HMAC_SHA256(K_cache, raw_access_token)
namespace = trusted_issuer + introspection_caller + resource_policy
~~~

`K_cache` là **khóa riêng cho cache**, không phải client secret, access-token signing key hay refresh token. Cache key namespace cần phân biệt issuer/RS caller/resource policy khi AS tiết lộ **metadata khác nhau tùy caller**. Một kết quả `active=true` của Payments RS **không được dùng lại như đã xác thực cho Orders RS**.

### 19.4. Không cache kết luận business authorization chung

Cache introspection metadata và cache quyết định “được đọc order 42” là **hai vấn đề khác nhau**. User có thể mất quyền ở tenant hoặc order đổi ownership trong khi token còn active. Resource server nên kiểm tra object-level policy với dữ liệu đáng tin ở thời điểm cần thiết.

### 19.5. Không mở rộng cache TTL khi AS lỗi

Sai:

~~~text
if introspection_AS_is_down:
    use_any_previous_active_result_forever
~~~

Điều này biến stale cache thành bypass revocation và expiry. **Chỉ dùng cache chưa hết hạn theo policy**, không kéo dài vô thời hạn để bảo đảm uptime.

## 20. Bảo vệ credential của RS và dữ liệu introspection

### 20.1. Những nơi thường bị lộ

| Dữ liệu | Bị lộ qua đâu? | Tác động |
| --- | --- | --- |
| Basic client secret | Source/Git, shell arguments, env dumps, ingress logs | Attacker có thể gọi introspection như RS |
| JWT RS assertion | Proxy/HTTP logs, tracing, exception dumps | Bản sao còn hạn có thể bị replay |
| Private key JWT | Disk/keystore, CI artifacts, workload compromise | Attacker có thể ký assertions mới |
| mTLS private key | Export cert/key, container volume, file permission sai | Attacker có thể mạo danh caller |
| Bearer caller token | APM/HTTP header capture | Attacker có thể query introspection đến khi token hết hạn |
| Raw token T | Form body logs, debug, cache key, failed requests | Bearer token có thể bị tái sử dụng ở API |
| Introspection response | Logs, shared cache, analytics, browser | Rò subject, client, scope, tenant, PII |

**Không log toàn request/response rồi dùng “redact ở UI”**; khi dữ liệu đã vào centralized logs, nhiều người/hệ thống có thể truy cập.

### 20.2. Vòng đời credential

Quy trình đề xuất:

1. Tạo identity/registration riêng cho mỗi RS hoặc trust domain cần thiết.
2. Chọn method phù hợp: Basic, JWT assertion, mTLS hoặc caller token theo AS support.
3. Sinh credential/khóa trong secret manager, KMS/HSM hoặc PKI bảo vệ.
4. Cho RS quyền tối thiểu để introspect **đúng audience/token types** và metadata.
5. Đặt timeout, policy redaction, allowlisted network egress và audit.
6. Rotate định kỳ, có **overlap có kiểm soát** khi AS cho phép nhiều credentials/keys.
7. Ngừng/thu hồi credential cũ sau rollout; rà soát logs và secret replicas.
8. Nếu compromise, vô hiệu RS credential và đánh giá metadata/tokens đã bị truy vấn.

### 20.3. Rotation Basic secret

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant AS as Authorization Server
    participant RS as Orders RS
    O->>AS: Đăng ký secret mới (overlap khi được hỗ trợ)
    O->>RS: Cập nhật secret manager / deploy
    RS->>AS: Introspect bằng secret mới
    AS-->>RS: active response hoặc token-state phù hợp
    O->>O: Theo dõi 401, error rate, latency
    O->>AS: Vô hiệu secret cũ sau khi xác minh
~~~

Nếu AS **chỉ hỗ trợ một secret hoạt động**, rollout có thể cần cơ chế cutover/canary/maintenance khác; không giả định luôn có overlap. Khi credential hết hiệu lực, RS **không được fallback bỏ introspection**.

### 20.4. Key rotation với `private_key_jwt`

- Đăng ký public key/JWKS mới dưới **đúng client identity**.
- Giới hạn signing alg, key usage, key ID và trust source.
- Chuyển RS sang private key mới sau khi AS nhìn thấy public key.
- Theo dõi lỗi signature/`invalid_client` và replay detection không log assertion.
- Thu hồi key cũ khi đã xác định không còn traffic hợp lệ.
- Có kế hoạch **key compromise** và khôi phục credential.

### 20.5. mTLS certificate rotation

PKI cần quản lý certificate renewal và xác minh CN/SAN/subject DN hoặc pinned self-signed certificate mapping tùy method. **Server certificate AS** và **client certificate RS** có mục đích khác nhau; rotation của một bên không được làm ứng dụng bỏ certificate validation bên kia.

## 21. Privacy, data minimization và token oracle

Introspection endpoint có thể là nơi rất nhạy cảm: nó liên kết **token value** với subject, client, scopes, expiry, audience, tenant. Nếu ai có token ngẫu nhiên cũng có thể hỏi, nó trở thành **token oracle** giúp đoán token hợp lệ hoặc thu thập metadata người dùng.

### 21.1. AS cần bảo vệ cả xác thực lẫn disclosure

| Lớp | Quy tắc |
| --- | --- |
| Caller authentication | Chỉ authenticated RS được gọi |
| Caller authorization | Chỉ RS được phép xem token types/audiences của mình |
| Metadata minimization | Trả đủ claims RS cần; không trả email/phone/roles không liên quan |
| Inactive response | Không mô tả chi tiết nguyên nhân cho bên không có quyền |
| Rate limiting | Hạn chế brute-force, token guessing, flood |
| Transport security | HTTPS, TLS validation, credential redaction |
| Audit | Theo dõi caller/result/latency, không raw token |
| Cache protection | TTL ngắn, phân vùng caller/issuer, bảo vệ PII |

### 21.2. Hạn chế metadata theo caller

Ví dụ một RS chỉ cần:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com",
  "aud": "orders-api",
  "scope": "orders.read",
  "sub": "user-42",
  "exp": 1800000900
}
~~~

Nếu AS có email, ngày sinh, địa chỉ, số điện thoại hoặc account history, **không có nghĩa RS phải nhận toàn bộ**. Nên có metadata schema/claims release policy riêng cho từng API; tránh truyền full OIDC profile chỉ để kiểm tra `orders.read`.

### 21.3. Audit an toàn

Log những trường như:

~~~text
event=introspection_call
issuer_alias=internal-as
rs_caller_alias=orders-introspection-rs
method=client_secret_basic
result=active_true
duration_ms=<measurement>
cache_hit=false
correlation_id=<non-secret-id>
~~~

Đừng log:

~~~text
authorization_header=<Basic-or-Bearer-credential>
raw_token=<access-token-value>
client_assertion=<jwt-assertion>
full_introspection_response=<subject-and-PII>
~~~

Nếu cần liên kết token trong audit, dùng fingerprint HMAC có khóa riêng, access control/retention và không làm metric labels công khai.

## 22. Những tình huống thực tế

**Tình huống A — RS gọi introspection bằng chính token T trong Bearer header.**

Orders API gửi `Authorization: Bearer T`, body cũng `token=T`. AS yêu cầu Basic credential của RS và trả 401.

**Phân tích:** token T là thứ cần kiểm tra, không phải bằng chứng Orders RS được introspect. Sửa outbound authentication của RS, không sửa trạng thái token T hoặc bỏ authentication.

**Tình huống B — Orders RS secret bị lộ.**

Attacker có credential Basic hợp lệ và thử introspect nhiều tokens thuộc Payments API.

**Phân tích:** AS phải áp **per-caller audience/token-type policy** và rate limit; không trả subject/PII của Payments token. Rotate/revoke secret Orders, audit token enumeration.

**Tình huống C — `active=false` cho token hợp lệ của Payments.**

Orders RS nhận false dù token có thể active tại Payments API.

**Phân tích:** kết quả phù hợp chính sách **token không dành/không được phép tiết lộ cho Orders**. Không suy rằng AS bị lỗi hay token bị revoke toàn cục.

**Tình huống D — JWT RS assertion sai `aud`.**

Assertion ký đúng với `aud` của token endpoint nhưng AS yêu cầu audience là introspection endpoint.

**Phân tích:** AS từ chối caller vì audience không khớp contract. Không bỏ audience validation chỉ để “tương thích”; thống nhất metadata/registration.

**Tình huống E — mTLS qua gateway nhưng AS chỉ thấy cert gateway.**

Orders RS thiết lập mTLS đến gateway; AS trust header `X-Client-Cert` từ caller.

**Phân tích:** dễ bị mạo danh nếu header được spoof. Cần trusted identity propagation, strip headers, ngăn bypass và xác minh certificate mapping đúng.

**Tình huống F — Rotate secret làm mọi API trả 401.**

Orders RS còn dùng Basic secret cũ; AS trả 401 introspection. Backend trả 401 `invalid_token` cho mọi user.

**Phân tích:** nguyên nhân là **caller authentication outage**, không phải mọi access token invalid. Cần sửa secret deployment/rotation, phân biệt lỗi phụ thuộc, fail closed và phản hồi dịch vụ phù hợp.

**Tình huống G — AS downtime, developer bật fail-open.**

Mọi token không xác định đều được chấp nhận để giữ uptime.

**Phân tích:** tạo bypass security; phải fail closed, dùng timeout/backoff/circuit breaker, cache chỉ trong TTL được phê duyệt.

**Tình huống H — RS có cache của một caller khác.**

Payments RS introspect token và cache `active=true`; Orders RS dùng chung raw-token cache để bỏ qua kiểm tra AS.

**Phân tích:** phá per-caller disclosure/audience policy. Partition cache theo issuer, caller, resource và policy; RS vẫn phải tự check audience/authorization.

**Tình huống I — SPA muốn gọi introspection trực tiếp.**

Frontend muốn nhúng client secret vào JS để kiểm tra login ngay trong browser.

**Phân tích:** public client không giữ được secret; không trao credential RS cho SPA. Chuyển việc kiểm tra về backend/BFF và trả thông tin UX tối thiểu.

**Tình huống J — Refresh token được RS chấp nhận làm Bearer.**

AS có thể trả trạng thái active của refresh token cho một caller có quyền, nhưng Orders API chấp nhận token đó như access token.

**Phân tích:** thiếu token purpose validation. RS phải chỉ nhận access token hợp lệ cho đúng resource, không dựa duy nhất vào `active` hoặc `token_type_hint`.

**Tình huống K — AS trả JWT introspection response.**

RS chỉ parse JWT payload Base64url mà không verify signature/issuer/audience của response.

**Phân tích:** nếu dùng RFC 9701, response JWT cần validation đầy đủ theo profile. Client authentication outbound vẫn là một lớp riêng.

**Tình huống L — Token được revoke nhưng RS dùng cached `active=true`.**

Cache 30 phút dù access token còn 5 phút và có yêu cầu revoke nhanh.

**Phân tích:** TTL sai và stale metadata có thể vượt expiry; dùng `min(policyTTL, exp-now)`, invalidation/short TTL và security SLA.

## 23. Bộ kiểm thử bắt buộc

| Test case | Kỳ vọng |
| --- | --- |
| RS Basic credential đúng, token active đúng audience | AS trả active + metadata được phép; RS kiểm tra policy |
| RS Basic credential sai | AS từ chối caller, không lộ metadata token |
| RS credential đã revoke | Không thể tiếp tục introspection |
| Caller không gửi credential khi endpoint yêu cầu | AS từ chối request |
| Gửi client ID nhưng không có proof | Không đủ xác thực confidential RS |
| HTTP Basic chứa special chars trong ID/secret | Form-encoding đúng RFC 6749 |
| Basic và `client_secret_post` cùng request | Từ chối nếu vi phạm contract/multiple methods |
| RS đăng ký Basic nhưng gửi JWT assertion | Từ chối nếu method không được cho phép |
| JWT client assertion chữ ký đúng, claims đúng | AS xác thực RS theo registration |
| JWT client assertion sai `iss`/`sub` | Từ chối |
| JWT assertion `aud` hướng sai endpoint | Từ chối |
| JWT assertion hết `exp` hoặc chưa tới `nbf` theo policy | Từ chối |
| JWT assertion `alg=none` | Từ chối |
| HS256↔RS256 algorithm/key confusion | Từ chối |
| `kid` trùng giữa Orders/Payments RS | Không dùng key sai registration |
| JWT assertion chứa `jku` attacker | Không tải arbitrary URL/không tin key |
| Replay cùng JWT assertion/`jti` | Phát hiện/từ chối theo replay policy |
| Nhiều AS nodes nhận assertion cùng `jti` | Replay cache/atomicity nhất quán |
| mTLS certificate hợp lệ đúng registered RS | AS authenticate và authorize đúng |
| mTLS certificate sai SAN/subject/client mapping | Từ chối |
| mTLS certificate hết hạn/trust chain sai | Từ chối |
| Caller tự gửi `X-Client-Cert` | Không mạo danh RS |
| Basic RS secret đưa xuống browser SPA | Security test thất bại |
| Caller dùng Bearer credential riêng đúng policy | Chấp nhận nếu AS hỗ trợ |
| Caller dùng Bearer token T làm own auth không hợp lệ | Từ chối, không tự coi token T là RS credential |
| Active token dành Payments, Orders RS hỏi | Không lộ Payments metadata/không cho Orders API |
| AS trả `active=false` | RS từ chối token, thường API 401 |
| AS trả 401 khi RS caller auth fail | RS không coi là `active=false` của T hoặc fail open |
| AS trả 403 vì RS thiếu disclosure permission | Không có metadata token |
| AS timeout/5xx | RS fail closed; áp dependency error handling |
| AS trả HTTP 302 sang host lạ | Không forward token/secret |
| AS trả JSON thiếu `active` hoặc sai kiểu | RS fail closed |
| AS trả `active=true` nhưng thiếu `aud` bắt buộc | RS từ chối |
| AS trả `active=true` nhưng scope thiếu | RS từ chối chức năng thiếu scope |
| Token refresh được introspect `active=true` | Business RS không nhận làm access token |
| OIDC ID token gửi tới API | RS từ chối token type/audience |
| Access token hết `exp` | RS từ chối, kể cả cache cũ |
| Token bị revoke sau positive cache | Test stale TTL/invalidation theo policy |
| Cache của Payments RS được Orders RS đọc | Không chấp nhận cross-caller cache |
| Multi-issuer RS nhận opaque token | Routing đáng tin, không fan-out tùy ý |
| Introspection response có PII ngoài contract | AS giảm metadata; test privacy |
| Client secret/token raw xuất hiện log/APM/cache key | Security test thất bại |
| DPoP/mTLS-bound access token không có sender proof | RS từ chối |
| Resource record thuộc tenant khác | RS từ chối object-level access |
| Key/secret rotation có overlap phù hợp | Không downtime ngoài contract; key cũ bị revoke |
| RS client compromise | AS có thể revoke caller, audit và hạn disclosure |
| RFC 9701 JWT response được chọn nhưng signature sai | RS từ chối |

### 23.1. Tầng kiểm thử

**Unit tests:** encode Basic, JWT assertion claims, metadata schema, audience/scope validation, cache TTL, error classification.

**AS integration tests:** xác thực caller qua Basic/JWT/mTLS, per-RS permission, token types được phép và response metadata minimization.

**Spring/Java integration tests:** outbound HTTP client thực, Spring Security filter chain, malformed response, 401/403/timeout/5xx.

**Network/proxy tests:** trusted TLS chain, certificate mapping, no redirect credential forwarding, SSRF/egress policy, log redaction.

**Concurrency/operations tests:** JWT assertion replay trên nhiều AS nodes, secret rotation, AS outage, cache invalidation.

**Business authorization tests:** đúng `aud`, thiếu scope, app-only vs user principal, wrong tenant, wrong object ownership và sender constraints.

**Không dùng production token/client secret trong test fixtures hoặc screenshots.** Mock một `Authentication` của Spring mà bỏ qua outbound introspection không kiểm chứng lớp bảo mật **RS → AS** của bài này.

## 24. Checklist production: xác thực caller introspection

1. **Bốn vai trò rõ:** client/API caller, resource server, authorization server, resource owner; không trộn credentials.
2. **Trusted AS endpoint:** `introspection_endpoint` được allowlist/discover từ trusted issuer, HTTPS/TLS validation và SSRF protection.
3. **Caller identity riêng:** mỗi RS/trust domain có registration và credential introspection phù hợp.
4. **Chọn method đã được phép:** Basic, JWT assertion, mTLS hoặc bearer caller credential **chỉ khi AS hỗ trợ**.
5. **Không dùng token T làm caller credential:** `token=T` nằm trong form; authentication riêng nằm header/mTLS/assertion theo contract.
6. **Client authentication không đủ:** AS còn kiểm tra RS được introspect **token type, audience/resource** và metadata nào.
7. **Least privilege disclosure:** không trả subject/PII/scopes không cần; `active=false` có thể che token caller không được phép xem.
8. **JWT assertion an toàn:** allowlist algorithm/key gắn client, `iss/sub/aud/exp`, replay `jti` theo policy, chống key injection.
9. **mTLS đúng trust boundary:** cert chain/identity registration, proxy termination không tin spoofed headers.
10. **Quản lý secret/key:** secret manager, KMS/HSM/PKI, rotation, overlap/cutover và emergency revoke.
11. **Redaction trên mọi hop:** Basic header, client assertion, token T, introspection response/PII không bị log.
12. **Đúng request RFC 7662:** POST form encoding, `token`, optional `token_type_hint` và response schema.
13. **Phân biệt lỗi:** HTTP 200/`active=false` khác HTTP 401/403 caller error, khác AS timeout/5xx.
14. **Fail closed:** không allow request khi AS authentication hoặc introspection unavailable; timeout/retry/circuit breaker an toàn.
15. **Cache có policy:** TTL không vượt `exp`, phân vùng issuer/RS caller/resource; không dùng stale response vô hạn.
16. **RS tự xác minh:** issuer, audience, scope, expiry, token purpose, principal type, tenant, object-level policy.
17. **Sender binding nếu có:** DPoP/mTLS của token T được verify tại RS, không nhầm với mTLS RS → AS.
18. **Nhiều issuer:** routing token tới đúng trusted AS; tránh fan-out làm lộ token.
19. **JWT introspection response:** nếu dùng extension, verify chữ ký/issuer/audience/type theo profile.
20. **Integration/security tests:** wrong secret, wrong method, replay, TLS spoof, wrong audience, malformed JSON, outage, cache và revocation.

## 25. Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): request/response, `active`, yêu cầu xác thực caller, phân quyền và security considerations.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth roles, client authentication và HTTP Basic/form encoding.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): `introspection_endpoint`, authentication methods và discovery.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT client assertions, `iss/sub/aud/exp` và signature validation.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `private_key_jwt` và `client_secret_jwt` trong OIDC client authentication.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): certificate client authentication và certificate-bound access tokens.
- [RFC 9701 — JWT Response for OAuth Token Introspection](https://www.rfc-editor.org/rfc/rfc9701): signed JWT introspection response khi profile hỗ trợ.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth threat model, token theft/replay và security best practices.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation khác kiểm tra `active` và khác rotation RS credential.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer API requests và 401/403 error semantics.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token issuer/audience/claims validation.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens và replay proofs.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): audience/resource binding.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): Spring introspection integration và resource-server configuration.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): access token không thay object authorization.

**Ghi nhớ:** **Client authentication cho introspection là phép kiểm tra “resource server nào đang hỏi authorization server?”**, độc lập với phép kiểm tra “access token đang được hỏi có hợp lệ không?”. RFC 7662 yêu cầu bảo vệ introspection endpoint; Basic, JWT assertion, mTLS hoặc cơ chế caller credential khác chỉ hợp lệ theo registration/profile của AS. **Không dùng token T làm credential xác thực RS, không nhầm lỗi caller 401 với `active=false`, không tiết lộ metadata cho RS sai audience và không fail open khi AS lỗi.** Sau khi có response tin cậy, RS vẫn phải xác minh **issuer, audience, time, scope, token purpose, tenant, quyền trên tài nguyên và sender binding nếu có**.
