# Bearer token và ý nghĩa của việc sở hữu token trong Spring Security

## 1. Mục tiêu học tập

**Bearer token** là một loại credential mà quyền sử dụng gắn với **việc nắm giữ token**. Theo RFC 6750, bên nào có được bearer token hợp lệ đều có thể sử dụng token để truy cập những tài nguyên mà token cho phép, **không phải chứng minh đang giữ một khóa mật mã riêng**.

Trong hệ thống OAuth 2.0, bearer access token thường được client gửi đến API qua header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer token-value-issued-by-authorization-server
~~~

Máy chủ API không tin một chuỗi bất kỳ chỉ vì nó được đặt sau chữ `Bearer`; nó vẫn phải **xác minh token hợp lệ và kiểm tra quyền**. Nhưng nếu một kẻ tấn công sao chép được **token thật còn hiệu lực**, kẻ đó có thể gửi cùng token từ máy khác và được đối xử như bên có token, trừ khi hệ thống có thêm ràng buộc người gửi.

Bài học tập trung vào:
- Ý nghĩa bảo mật của cụm từ **“sở hữu token”**, bao gồm sự khác nhau giữa danh tính thật và người đang trình token.
- Các thành phần Authorization Server, Client và Resource Server, cùng quá trình xác thực/ủy quyền.
- JWT bearer và opaque bearer; token hợp lệ khác token được phép dùng ở API này.
- Tấn công rò rỉ, đánh cắp, replay; cách hạn chế thiệt hại và phương án **sender-constrained token**.
- Cách Spring Security Servlet Resource Server nhận bearer token và kiểm tra `issuer`, `audience`, thời gian và `scope`.

## 2. Bearer token là gì?

### 2.1. “Bearer” nhấn mạnh việc trình token

Có thể hình dung bearer token giống **vé vào cổng**: người kiểm soát cổng xác minh vé được phát hành hợp lệ, chưa hết hạn và có đúng quyền vào khu vực. Người cầm vé có thể không phải người nhận vé ban đầu. Phép so sánh này chỉ giải thích tính **có thể chuyển giao bằng sao chép**; bearer token điện tử dễ bị sao chép hơn vé vật lý và có thể mang nhiều quyền khác nhau.

Ví dụ một OAuth access token được cấp cho ứng dụng A để gọi API:
- Token có quyền `orders.read`, thời gian sống 15 phút và dành cho API `orders-api`.
- Ứng dụng A gửi token trong `Authorization: Bearer ...`.
- Nếu B lấy được đúng chuỗi token, **B có thể gọi cùng API** trong thời gian token có hiệu lực, với những quyền mà API chấp nhận.
- API có thể kiểm tra `sub`, `scope`, `aud`, `iss`, `exp` nhưng các claim đó tự thân **không chứng minh B là A**.

**Kết luận an ninh:** bearer token là **bí mật có giá trị như quyền truy cập tương ứng**. Phải bảo vệ nó như credential, dù chuỗi token có ký số và dù thời hạn sống ngắn.

### 2.2. “Sở hữu token” nghĩa là gì và không nghĩa là gì?

Trong ngữ cảnh bearer, “sở hữu” nghĩa là **có khả năng trình đúng token** vào giao thức HTTP, không phải:
- chứng minh danh tính người đang cầm token qua password hoặc sinh trắc học;
- chứng minh đang giữ private key của client;
- chứng minh request phát sinh từ thiết bị ban đầu;
- chứng minh người gửi đã trực tiếp đăng nhập;
- hoặc chứng minh token được cấp trực tiếp cho máy đang gọi.

Token có thể bị sao chép từ bộ nhớ, log, proxy, công cụ debug hoặc một thiết bị bị chiếm quyền. API chỉ thấy token hợp lệ **không phân biệt chắc chắn** đây là lời gọi của client được cấp token hay của người đã đánh cắp token. Đây là **tính chất thiết kế của bearer token**, không phải bug riêng của JWT.

### 2.3. Trình token không đồng nghĩa mọi quyền đều được chấp nhận

Việc nắm giữ bearer token chỉ giúp sử dụng **quyền gắn với token và chính sách của Resource Server**, không phải mọi API:
- `scope=orders.read` không tự cho phép `orders.write`.
- `aud=orders-api` không có nghĩa API `payments-api` phải chấp nhận.
- Token hết hạn, sai chữ ký, sai issuer, bị thu hồi hoặc không active phải bị từ chối.
- API vẫn kiểm tra object-level authorization: được `orders.read` không mặc nhiên được xem đơn hàng của người khác.
- Nếu token bị ràng buộc với chứng chỉ/khóa bằng mTLS hoặc DPoP, việc biết token thôi có thể **chưa đủ**; đó không còn là bearer thuần.

## 3. Bearer token trong luồng OAuth 2.0

Các vai trò cơ bản:

| Thành phần | Vai trò |
|---|---|
| Resource Owner | Người hoặc chủ thể có dữ liệu được bảo vệ |
| OAuth Client | Ứng dụng muốn gọi API theo một quyền được cấp |
| Authorization Server | Xác thực/ủy quyền theo chính sách và phát hành access token |
| Resource Server | API kiểm tra token và quyết định cấp tài nguyên |

~~~text
Người dùng ──đăng nhập/đồng ý quyền──> Authorization Server
                 │                              │
                 │      cấp access token         │
                 v                              v
               OAuth Client <───────────────────┘
                    │
                    │ GET /api/orders
                    │ Authorization: Bearer <access-token>
                    v
              Resource Server
               ├─ token có thật/đúng chữ ký hoặc active?
               ├─ issuer / audience / exp / nbf hợp lệ?
               ├─ scope và quyền theo tài nguyên?
               └─ cho phép hoặc từ chối
~~~

**Authorization Server phát hành**, **Resource Server kiểm tra và thực thi chính sách**. Client không được tự tạo chuỗi `Bearer something` rồi mong API chấp nhận. Khi OAuth2 Client thay mặt người dùng truy cập API, bearer token phản ánh một **ủy quyền đã cấp**; token không phải bản sao của password người dùng.

### Tại sao phải dùng Authorization Code + PKCE?

Với ứng dụng tương tác (mobile, SPA, desktop) dùng OAuth 2.0, flow Authorization Code với PKCE giúp giảm nguy cơ authorization code bị chặn và dùng trái phép khi đổi lấy token. Tuy vậy **PKCE không tự biến access token đã phát hành thành token ràng buộc người gửi**: nếu bearer access token sau đó bị lộ, token vẫn có thể bị replay. Đừng nhầm bảo vệ **quá trình cấp token** với bảo vệ **quá trình trình token tới API**.

## 4. Cấu trúc HTTP: gửi token như thế nào?

Theo cách phổ biến và được khuyến nghị, client gửi token trong header HTTP:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...redacted...signature
Accept: application/json
~~~

- `Authorization`: tên header chuẩn để chuyển credential.
- `Bearer`: authentication scheme theo RFC 6750, thường không phân biệt chữ hoa/thường ở phần tên scheme; tuân thủ cú pháp mà bộ phân giải hỗ trợ.
- Phần sau dấu cách là token; **không gửi dấu ngoặc nhọn, dấu nháy hoặc chữ `Bearer` lần thứ hai** trong giá trị.
- `Content-Type` của response hoặc dạng JSON body không phải nơi mặc định chứa bearer token.
- HTTP chỉ là phương tiện chuyển token; luôn dùng **HTTPS với xác thực máy chủ đúng cách**.

**Tránh truyền bearer token qua URL query**, ví dụ `?access_token=...`: URL có thể đi vào lịch sử trình duyệt, reverse-proxy logs, analytics, monitoring, bookmark và các hệ thống theo dõi khác. RFC 6750 mô tả một số cách truyền bearer ngoài header vì tương thích, nhưng truyền qua URL được khuyến cáo tránh và Spring Security mặc định tập trung vào `Authorization` header.

Không tự coi một header do client đặt như `X-User: alice` hoặc `X-Scope: admin` là bằng chứng xác thực. API phải lấy danh tính/quyền từ **token đã được kiểm chứng**, không từ trường tự khai của client.

## 5. Token hợp lệ không nhất thiết là token đúng mục đích

### 5.1. JWT có thể đọc được nhưng nội dung chưa đáng tin

JWT thường có ba phần `header.payload.signature`, mã hóa Base64URL và nối bằng dấu chấm:

~~~text
<base64url-header>.<base64url-payload>.<base64url-signature>
~~~

Ví dụ **payload minh họa**, không phải token thật:

~~~json
{
  "iss": "https://idp.example.org/realms/demo",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893453300,
  "jti": "example-token-id-42"
}
~~~

Các timestamp chỉ dùng làm ví dụ. Claims phổ biến:
- `iss` (*issuer*): tổ chức/máy chủ phát hành token, phải đúng danh sách được tin.
- `sub` (*subject*): định danh chủ thể trong namespace issuer; không tự chứng minh người trình request chính là subject.
- `aud` (*audience*): API hoặc đối tượng mà token được phát hành cho; phải có API nhận token.
- `exp` (*expires at*): sau thời điểm này token không được dùng, với độ lệch đồng hồ hợp lý.
- `nbf` (*not before*): token chưa được chấp nhận trước thời điểm này.
- `iat` (*issued at*): thời điểm phát hành; hữu ích cho policy nhưng không thay `exp`.
- `scope` / `scp`: quyền được cấp theo contract của nhà phát hành; cần ánh xạ đúng.
- `jti`: ID token; có thể dùng trong hệ thống theo dõi/revocation nếu kiến trúc hỗ trợ, nhưng không tự làm token một lần.

**JWT dạng JWS có chữ ký, không mặc nhiên được mã hóa nội dung.** Bất kỳ người nào có token thường có thể đọc payload sau khi Base64URL decode. Vì vậy không đưa password, secret, dữ liệu nhạy cảm không cần thiết vào JWT. Đọc payload hoặc dùng debugger JWT **không phải xác minh**: Resource Server phải kiểm tra chữ ký bằng key đáng tin, thuật toán cho phép và claims/policy.

### 5.2. Kiểm tra JWT ở Resource Server

Một token JWT nên trải qua ít nhất:

1. Kiểm tra cấu trúc, loại token và thuật toán ký được cho phép; **không tin `alg` do attacker tự công bố để vô hiệu hóa kiểm chứng**.
2. Lấy public key/JWKS đúng của issuer tin cậy, xác minh chữ ký, quản lý rotation; không dùng key/issuer bất kỳ từ untrusted claim.
3. Kiểm tra `iss`, `exp`, `nbf` và `aud` chính xác theo ứng dụng; không được dùng token của service khác.
4. Kiểm tra token là **access token phù hợp** chứ không nhầm ID Token hay refresh token; có thể kiểm tra `typ`, `client_id` và profile RFC 9068 tùy loại token/IdP.
5. Kiểm tra scope/authority và **phân quyền ở cấp đối tượng**.
6. Khi yêu cầu revocation gần thời gian thực, bổ sung chiến lược từ chối token cũ (chẳng hạn introspection, denylist `jti`, giảm TTL hoặc kiểm soát phiên) phù hợp mô hình.

**Chữ ký hợp lệ chứng minh token được ký bởi key tương ứng**, chưa chứng minh chủ thể của request. JWT do issuer ký vẫn là bearer credential nếu API chỉ yêu cầu trình chuỗi JWT.

### 5.3. Opaque token không làm thay đổi tính chất bearer

Opaque token thường là một chuỗi khó đoán, không có claims công khai:

~~~text
6dP0...random-opaque-token...9x2Q
~~~

Resource Server có thể gọi **introspection endpoint** của Authorization Server để biết `active`, subject, scopes, expiry và metadata. Khác JWT, client không đọc claims trong chuỗi. Nhưng nếu token được dùng theo bearer, **ai lấy được chuỗi opaque hợp lệ vẫn có thể trình lại**, giống hệt JWT bearer.

| Tiêu chí | JWT bearer | Opaque bearer |
|---|---|---|
| Hình thức | Token có cấu trúc, thường ký số | Chuỗi tham chiếu/giá trị opaque |
| Xác minh | JWT signature và claim validators | Thường introspection tới server |
| Chứa claims có thể decode | Thường có | Không yêu cầu |
| Chống replay nếu token bị sao chép | Không, nếu là bearer thuần | Không, nếu là bearer thuần |
| Revocation gần thời gian thực | Cần chiến lược bổ sung hoặc token TTL ngắn | Introspection có thể kiểm tra `active` theo thời điểm gọi |
| Lỗi triển khai phổ biến | Quên `aud`, tin `alg` sai, lộ payload | Không kiểm tra `active`/metadata, cache sai, timeout |
| Cần HTTPS | Có | Có |

### 5.4. Access token, ID Token và refresh token

- **Access token**: credential được Client trình tới **Resource Server** để truy cập tài nguyên.
- **ID Token**: OIDC token nói về sự kiện xác thực và danh tính cho **Relying Party/OIDC Client**; không tự động là access token hợp lệ của API. API phải từ chối token sai audience/loại.
- **Refresh token**: dùng với Authorization Server để xin access token mới khi còn đủ điều kiện, **không dùng làm bearer access token để gọi Resource Server**. Refresh token thường nhạy cảm hơn vì có thể giúp xin nhiều access token tương lai; cần bảo vệ, rotation/ràng buộc và chính sách thu hồi.

Không kết luận “token có `sub=alice` thì mọi API phải cho alice đăng nhập”. Cần xem đúng **token dùng cho ai, do ai cấp, quyền gì, thời điểm nào và có thể bị thu hồi không**.

## 6. Vì sao đánh cắp token là tình huống nguy hiểm?

### 6.1. Replay: dùng lại token đã bị lộ

~~~text
Authorization Server
      │ cấp access token cho Client A
      v
Client A ─── Authorization: Bearer TOKEN ───> Orders API
      │
      │ Token bị lộ (XSS, log, debug, extension...)
      v
Attacker B ─ Authorization: Bearer TOKEN ───> Orders API
                                               │
                                               └─ API thấy token hợp lệ
                                                  → có thể chấp nhận B
~~~

Kẻ tấn công **không cần bẻ chữ ký JWT** hoặc đoán password. Họ chỉ sao chép chuỗi token thật và gọi API. Tùy token, họ có thể đọc/sửa dữ liệu trong phạm vi được cấp. Giới hạn `aud` và `scope` giảm phạm vi thiệt hại nhưng **không xác định được người trình token**.

### 6.2. Các đường rò rỉ thường gặp

| Nguồn rò rỉ | Tình huống | Biện pháp |
|---|---|---|
| HTTP qua kênh không bảo vệ | Token bị nghe lén hoặc sửa trên đường truyền | HTTPS/TLS chuẩn, kiểm tra hostname/CA |
| URL query, URL fragment bị xử lý sai | Token vào logs, history, analytics, copied links | Dùng `Authorization` header; không dùng URL truyền bearer |
| Console/logging | Ghi nguyên `Authorization`, request/response, token claims | Redact/mask ở app, gateway, APM, tracing |
| Browser XSS | Script độc hại đọc token trong storage/JS memory hoặc dùng quyền phiên | Chống XSS, CSP, giảm lưu token trong JS, xem xét BFF |
| LocalStorage/SessionStorage | JS chạy cùng origin có thể đọc token | Không coi Web Storage an toàn trước XSS |
| Client/mobile/desktop bị chiếm | Malware/extension hoặc file dump đọc token | OS secure storage, giảm TTL, device controls |
| Gửi token cho API sai | Token đi tới host/redirect/proxy ngoài phạm vi tin cậy | Allowlist destination, không forward Authorization qua redirect tùy tiện |
| Logs của bên thứ ba | Client SDK/APM thu thập header | Quy định trường dữ liệu, secret scrubbing và kiểm toán |
| Refresh token lưu kém | Attacker tiếp tục cấp access token mới | Refresh rotation, client binding, revoke và phát hiện reuse |

**Lưu ý browser:** cookie `HttpOnly` có thể ngăn JavaScript trực tiếp đọc giá trị cookie, nhưng browser vẫn tự gửi cookie theo điều kiện của nó; cần `Secure`, `SameSite`, CSRF và bảo vệ XSS đúng kiến trúc. Mô hình Backend-for-Frontend (BFF) có thể giữ OAuth tokens ở server và chỉ dùng session cookie có kiểm soát với browser.

### 6.3. Hậu quả phụ thuộc quyền của token

- Token chỉ có `orders.read` có thể làm lộ dữ liệu; không phải “an toàn” vì chỉ đọc.
- Token `orders.write` có thể tạo/sửa đơn hàng trong quyền cho phép.
- Token dành cho nhiều API hoặc quyền quá rộng làm tăng **blast radius**.
- Token sống hàng giờ/ngày cho phép replay lâu hơn; TTL ngắn giới hạn cửa sổ, nhưng **không ngăn replay tức thời**.
- Nếu attacker lấy được **refresh token**, họ có thể tiếp tục lấy access token mới trừ khi bị giới hạn/ràng buộc hoặc revoked.

## 7. Phòng thủ: từ giới hạn quyền đến sender-constrained token

### 7.1. Bảo vệ bearer token thuần

1. **TLS ở mọi hop:** HTTPS từ client tới gateway/API; nếu TLS được terminate tại proxy, proxy→backend cũng phải có đường tin cậy, quyền mạng và TLS/mTLS phù hợp.
2. **Giới hạn quyền:** phát hành token đúng `aud`, scope ít nhất cần thiết, resource/tenant và object-level policy.
3. **Giảm thời gian sống:** access token ngắn hạn phù hợp UX/rủi ro, kiểm soát refresh token; không cho rằng TTL ngắn chữa hết replay.
4. **Bảo vệ ở client:** tránh lưu plaintext trên disk; tránh token trong URL/log; chống XSS và quản trị credential theo platform.
5. **Kiểm tra chặt ở API:** signature/introspection, issuer, audience, thời gian, token type và authorization. Mọi API nhạy cảm phải kiểm tra dữ liệu ở mức đối tượng.
6. **Revocation/rotation:** có kế hoạch khi token lộ; với JWT tự kiểm chứng, làm rõ độ trễ của denylist/introspection/logout và key rotation.
7. **Quan sát hành vi:** log `requestId`, subject/issuer/scope đã được kiểm chứng nếu được phép, tần suất và rủi ro; không ghi chuỗi token. Giới hạn tốc độ và phát hiện hoạt động bất thường.
8. **Fail closed:** lỗi JWKS/introspection/chứng chỉ/đồng hồ hoặc thiếu quyền phải từ chối, không cho phép mặc định.

### 7.2. Sender-constrained token khác bearer thuần

**Sender-constrained / proof-of-possession** yêu cầu người trình token chứng minh thêm đang giữ một bí mật hoặc private key được gắn với token. Hai kỹ thuật thường gặp:

| Cơ chế | Nguyên lý | Điểm cần triển khai |
|---|---|---|
| **mTLS certificate-bound access token** (RFC 8705) | Authorization Server gắn token với chứng chỉ client; Resource Server kiểm tra chứng chỉ của client khớp binding | Kết nối mTLS, xác minh cert/binding `cnf`, proxy phù hợp, quản lý khóa |
| **DPoP** (RFC 9449) | Client ký một proof JWT cho request bằng private key; token bị ràng buộc với public key đó | Kiểm tra chữ ký proof, `htm`, `htu`, `iat`, `jti`, `ath`, replay cache/nonce theo chính sách và key binding |

Với DPoP, token thường được trình theo scheme `DPoP`, kèm một header `DPoP` chứa proof cho request, thay vì chỉ `Bearer token`. **Không chỉ đổi tên header thành `DPoP` là đã có bảo vệ**: Authorization Server phải phát hành token gắn key và Resource Server phải kiểm tra proof/binding. Một API chỉ bật `oauth2ResourceServer().jwt()` để đọc bearer thông thường **không mặc nhiên triển khai đầy đủ DPoP hoặc mTLS-bound access token**.

### 7.3. Những biện pháp không giải quyết được replay nếu dùng một mình

- **Ký JWT:** ngăn sửa nội dung token, không ngăn sao chép nguyên token.
- **Mã hóa token:** có thể bảo vệ nội dung khỏi người không có key giải mã, nhưng nếu API nhận token dạng bearer thì bản sao vẫn dùng được.
- **IP allowlist/UA fingerprint:** có thể là lớp giảm rủi ro, nhưng NAT/mobile network thay đổi, header bị giả; không tương đương proof-of-possession.
- **CORS:** áp dụng trong browser, không chặn `curl` hay một server khác gửi bearer token đã bị lộ.
- **`HttpOnly` cookie:** giảm khả năng JS đọc cookie, không tự chặn request từ XSS hoặc mọi CSRF.
- **Logout phía giao diện:** xóa token khỏi client không nhất thiết thu hồi token đã phát hành và đang nằm trong tay attacker.

## 8. Spring Security nhận và xử lý bearer token ra sao?

Trong ứng dụng **Servlet Resource Server**, pipeline phổ biến:

~~~text
HTTP Authorization: Bearer ...
           │
           v
BearerTokenAuthenticationFilter
           │ resolve bearer string (mặc định từ Authorization)
           v
BearerTokenAuthenticationToken
           │
           v
AuthenticationManager / ProviderManager
           │
           ├─ JWT   → JwtAuthenticationProvider → JwtDecoder/validators
           │                                     → JwtAuthenticationToken
           │
           └─ Opaque→ OpaqueTokenAuthenticationProvider
                       → OpaqueTokenIntrospector
                       → BearerTokenAuthentication
           │
           v
SecurityContext (principal/authorities)
           │
           v
AuthorizationFilter → endpoint hoặc 401/403
~~~

- **BearerTokenAuthenticationFilter** lấy token từ request; không tự tin token hợp lệ chỉ vì header tồn tại.
- **JWT**: `JwtDecoder` xác minh ký số và claims, sau đó `JwtAuthenticationConverter` ánh xạ thành `Authentication` và authorities.
- **Opaque**: `OpaqueTokenIntrospector` hỏi Authorization Server và xử lý token còn `active` hay không; policy audience/scope phải được cấu hình phù hợp contract.
- **Authorization** vẫn chạy sau authentication: có token xác thực thành công nhưng thiếu `SCOPE_orders.read` thì không được gọi `GET /api/orders`.
- Resource Server xác thực **token cho request API**, khác luồng `oauth2Login()` dùng để đăng nhập trình duyệt.

### Phân biệt mã lỗi 401 và 403

| Tình huống | Ý nghĩa | HTTP thường gặp |
|---|---|---|
| Thiếu bearer ở endpoint bắt buộc xác thực | Chưa có credential để xác thực | **401 Unauthorized** |
| Token giả, hỏng, sai chữ ký, hết hạn, sai issuer/audience | Credential không hợp lệ | **401 Unauthorized**, thường có `WWW-Authenticate: Bearer` kèm lỗi phù hợp |
| Token hợp lệ nhưng thiếu scope/quyền | Đã xác thực nhưng bị chặn ở phân quyền | **403 Forbidden**, có thể `insufficient_scope` |
| Token hợp lệ và đúng scope, nhưng object của user khác | Chính sách truy cập dữ liệu từ chối | **403** hoặc **404** tùy thiết kế không tiết lộ tài nguyên |
| Introspection/JWKS không hoạt động | Không thể xác minh token an toàn | Không cho truy cập; mã 5xx/401 tùy loại lỗi và handler |

Không suy ra “HTTP 401 nghĩa là password sai”: với OAuth Resource Server, lỗi có thể là token thiếu, hết hạn, sai audience hoặc chữ ký.

## 9. Ví dụ thực hành: Spring Boot 3.x, Spring Security 6.x, Java 17+

Ví dụ sau là **Resource Server chỉ nhận JWT bearer** từ một issuer được tin cậy, yêu cầu token có `aud=orders-api` và scope `orders.read`. Code viết cho một ứng dụng Spring Boot hoàn chỉnh, không cần tự viết bộ giải mã JWT. URL issuer chỉ là miền minh họa; để chạy thật phải thay bằng Authorization Server có discovery/JWKS và token thực.

### 9.1. Tạo project Maven

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bearer-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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
~~~

Spring Boot quản lý version Spring Security tương thích. Starter Resource Server đưa vào các dependency Resource Server và JOSE cần cho JWT. Không tự parse token bằng `Base64.getDecoder()` để quyết định quyền.

### 9.2. `application.yml`: issuer và audience phải hợp lệ

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/demo
          audiences:
            - orders-api
~~~

- `issuer-uri` phải khớp **chính xác** `iss` trong token và trỏ đến issuer có metadata/discovery hợp lệ.
- `audiences` yêu cầu access token chứa `orders-api` trong `aud`; đây là điều kiện **chặn token hợp lệ nhưng dành cho API khác**.
- Spring Security kiểm tra chữ ký JWT, `iss`, `exp`, `nbf` theo cấu hình thông thường; Boot hỗ trợ `audiences` như trên.
- Chỉ tin issuer, thuật toán ký và JWKS theo hợp đồng; không lấy `issuer-uri` từ dữ liệu client gửi vào request.

### 9.3. Class khởi động

File `src/main/java/com/example/bearer/BearerDemoApplication.java`:

~~~java
package com.example.bearer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BearerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BearerDemoApplication.class, args);
    }
}
~~~

### 9.4. SecurityFilterChain chỉ cho phép đọc đơn hàng

File `src/main/java/com/example/bearer/SecurityConfiguration.java`:

~~~java
package com.example.bearer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Phân tích:**
- `oauth2ResourceServer().jwt()` nối filter → provider → decoder JWT theo Spring Security.
- `SCOPE_orders.read` là authority thông thường do JWT converter ánh xạ từ scope `orders.read`; đây là **quyền gọi endpoint**, không tự chứng minh người giữ token là người ban đầu.
- `SessionCreationPolicy.STATELESS` tránh lấy Authentication dựa trên session server cho API demo.
- `anyRequest().denyAll()` giữ mặc định đóng các route khác, kể cả route debug không được cấp phép.
- Ví dụ chỉ có GET; CSRF mặc định không cản GET. Với API thực dùng bearer header và không dựa vào cookie tự động gửi, có thể thiết kế CSRF strategy phù hợp. **Không tắt CSRF trên ứng dụng dùng cookie browser chỉ vì có JWT ở nơi khác**.
- Đừng đưa `access_token` vào path, query hay log khi thử nghiệm.

### 9.5. Endpoint minh họa

File `src/main/java/com/example/bearer/OrderController.java`:

~~~java
package com.example.bearer;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/api/orders")
    public List<OrderSummary> list() {
        return List.of(
                new OrderSummary("ORD-001", "Notebook"),
                new OrderSummary("ORD-002", "Keyboard"));
    }

    public record OrderSummary(String id, String description) {}
}
~~~

Endpoint trả **dữ liệu giả trong bộ nhớ** để học về bearer; trong production bắt buộc lọc đơn hàng theo tenant/user đã xác thực. `hasAuthority` kiểm tra quyền ở mức endpoint, **không thay thế object-level authorization**.

Build/chạy (đã cài Java 17+ và Maven):

~~~bash
mvn clean package
java -jar target/bearer-demo-0.0.1-SNAPSHOT.jar
~~~

Ứng dụng có thể khởi động khi issuer metadata còn chưa được truy cập tùy phiên bản/cấu hình, nhưng khi xử lý token phải liên hệ/đọc key hợp lệ. Để nhận `200`, cần một JWT **thật** có chữ ký đúng, issuer `https://idp.example.org/realms/demo`, audience `orders-api`, `exp` hợp lệ và scope `orders.read`.

### 9.6. Thử bằng curl

~~~bash
# Không có token:
curl -i http://localhost:8080/api/orders

# Có token thực lấy từ Authorization Server đã cấu hình:
curl -i -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    http://localhost:8080/api/orders
~~~

Đặt `ACCESS_TOKEN` là biến môi trường tại môi trường test; không in token ra terminal log. Mẫu trên dùng localhost để học; ở môi trường thực luôn gọi HTTPS.

**Kỳ vọng:**
- Thiếu token: HTTP `401`.
- Token sai chữ ký/hết hạn/sai issuer hoặc `aud`: HTTP `401`.
- JWT hợp lệ đúng audience nhưng thiếu `orders.read`: HTTP `403`.
- JWT hợp lệ có `orders.read`: HTTP `200` và JSON tương đương:

~~~json
[
  {"id": "ORD-001", "description": "Notebook"},
  {"id": "ORD-002", "description": "Keyboard"}
]
~~~

Thứ tự key trong JSON không có ý nghĩa; ví dụ kết quả phụ thuộc token/provider thật. Đây là **expected behavior theo cấu hình**, không phải stdout được sinh bằng token minh họa.

### 9.7. Nếu dùng opaque token thay JWT

Giữ Controller/authorization rule, nhưng thay Resource Server DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
        .opaqueToken(Customizer.withDefaults()))
~~~

Và thay phần `jwt` trong `application.yml` bằng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Đây là **cấu hình thay thế**, không khai báo đồng thời với ví dụ JWT trong một resource server đơn giản. Authorization Server phải hỗ trợ introspection; credential dùng introspection là secret của API và phải lấy từ secret manager, không commit. Kiểm tra scope/audience tùy contract của introspection response; không cho phép token thiếu quyền chỉ vì `active=true`.

## 10. Ví dụ tình huống trước và sau khi token bị lộ

Giả sử Alice là người dùng hợp lệ, token của Alice là bearer JWT đã được ký, chưa hết hạn, audience `orders-api`, scope `orders.read`.

**Trước khi lộ:**
1. Alice đăng nhập tại Authorization Server theo luồng hợp lệ.
2. OAuth Client nhận token.
3. Client gọi `GET /api/orders` với `Authorization: Bearer tokenAlice`.
4. API kiểm tra JWT và trả dữ liệu đúng quyền cho Alice.

**Sau khi token bị sao chép:**
1. Một script độc hại lấy được `tokenAlice` từ log/storage.
2. Script ở máy khác gửi cùng header `Authorization: Bearer tokenAlice`.
3. Nếu API chỉ xác minh JWT như bearer thông thường, request của script vẫn vượt qua kiểm tra **chữ ký, issuer, audience, scope và expiry**, vì tất cả vẫn đúng.
4. API không có bằng chứng độc lập rằng request mới đến từ Alice hay client ban đầu. Nếu object authorization chỉ dựa vào claims của Alice, script có thể đọc tài nguyên của Alice.

**Cách giảm rủi ro:** loại bỏ rò rỉ tại nguồn, giảm TTL/quyền, thu hồi token đã lộ, và với hệ thống đòi hỏi chống replay mạnh, phát hành/token validation theo DPoP hoặc mTLS-bound access token. Việc bật HTTPS là bắt buộc nhưng không ngăn token đã bị đánh cắp từ client hoặc log.

## 11. Ma trận test bảo mật cho bearer token

| Ca kiểm thử | Input | Kết quả đúng |
|---|---|---|
| Không có token | GET không `Authorization` | 401 |
| Header sai scheme | `Authorization: Basic ...` | Không được coi là bearer đã xác thực |
| Chuỗi tự bịa | `Authorization: Bearer garbage` | 401 |
| JWT bị sửa payload | Đổi `scope`, giữ signature cũ | 401 do chữ ký sai |
| JWT chữ ký hợp lệ nhưng issuer khác | `iss` không thuộc issuer tin | 401 |
| Token dành cho API khác | `aud` không chứa `orders-api` | 401 |
| Token hết hạn / chưa có hiệu lực | `exp` quá khứ hoặc `nbf` tương lai | 401 theo clock skew |
| Token hợp lệ, thiếu scope | Chỉ có `orders.write` | 403 khi gọi GET yêu cầu `orders.read` |
| Token hợp lệ đúng quyền | `orders.read` + valid issuer/audience | 200 cho endpoint demo |
| Token có scope nhưng truy cập đơn hàng người khác | Object ID ngoài quyền user | 403/404 theo thiết kế |
| Copy token của Alice sang máy B | Bearer token còn hạn | Có thể vẫn dùng được: **đây là tính chất bearer**; test cho thấy rủi ro |
| Token đã revoke | Revocation/introspection/denylist đã có hiệu lực | Không được tiếp tục dùng |
| DPoP/mTLS-bound token bị copy không kèm proof | Khác key/cert hoặc proof không hợp lệ | Phải bị từ chối nếu Resource Server hỗ trợ đầy đủ |
| Auth/JWKS/introspection lỗi | Không có dữ liệu xác minh đáng tin cậy | Fail closed |
| Token trong URL/log | Query `access_token` hoặc logging toàn header | Bị chặn/không ghi raw credential theo policy |

**Test framework:** `spring-security-test` với `MockMvc` và `jwt()` có thể test *authorization* (`SCOPE_...` → 200/403), nhưng dùng principal JWT giả lập, **không kiểm tra chữ ký/JWKS/issuer/audience thực**. Để test token validation, chạy integration test với public key/JWKS test và JWT ký thực, hoặc test `JwtDecoder` riêng. Không được công bố hệ thống chống replay chỉ dựa trên test scope.

## 12. Checklist vận hành và sự cố

Trước khi đưa API dùng bearer token lên production:

- [ ] Resource Server kiểm tra token bằng JWT signature/issuer/audience/time hoặc opaque introspection đáng tin.
- [ ] Không nhận ID Token/refresh token thay access token.
- [ ] Mỗi API có audience và scopes/permissions tối thiểu; có object-level authorization.
- [ ] Token chỉ truyền qua HTTPS, ưu tiên header `Authorization`; không dùng URL query.
- [ ] Gateway, access log, APM, metrics, exception handlers và debug tools đã redact token.
- [ ] Không lưu access token/refresh token ở client dưới dạng dễ bị đọc; đã phân tích XSS, CSRF và BFF/cookie.
- [ ] Token TTL hợp lý; refresh token bảo vệ/rotation/reuse detection theo rủi ro.
- [ ] Có playbook thu hồi token/token family/session khi bị lộ, kể cả JWT chưa hết hạn.
- [ ] Có chính sách key/JWKS rotation và xử lý issuer mất kết nối.
- [ ] Không tin `X-User`, `X-Role` hoặc `X-Forwarded-For` do client tự khai để thay kiểm tra bearer token.
- [ ] Kiểm tra tiêu cực: token fake, expired, wrong aud, wrong iss, missing scope, tenant/object mismatch.
- [ ] Nếu cần bảo đảm token không thể bị replay chỉ bằng sao chép, có **sender constraint thực sự** (mTLS/DPoP) được cả bên phát hành và API kiểm tra.
- [ ] Người vận hành phân biệt `401` (token không hợp lệ/thiếu) với `403` (token hợp lệ nhưng thiếu quyền).

Khi nghi có rò rỉ:
1. Xác định issuer, client, audience và khoảng thời gian/token family bị ảnh hưởng từ metadata an toàn, **không phát tán token gốc**.
2. Thu hồi hoặc vô hiệu hóa token/phiên và refresh token liên quan theo khả năng của Authorization Server; nếu JWT không revocable trực tiếp, áp dụng denylist/giảm TTL/biện pháp phù hợp.
3. Vá nguồn rò rỉ (log, XSS, proxy, storage), thay key/secret khi thật sự bị lộ, và rà soát hành vi truy cập bất thường.
4. Kiểm thử lại tất cả validation và authorizations; bổ sung kiểm soát ngăn tái diễn.

## 13. Các hiểu nhầm dễ gặp

1. **“JWT ký số thì không ai dùng trộm được.”** Sai. Chữ ký chống giả mạo nội dung, còn bản sao JWT hợp lệ vẫn là credential.
2. **“Token có `sub=alice` tức request do Alice gửi.”** Sai. Claim nói về chủ thể mà token đại diện, không xác thực thiết bị/người trình bearer.
3. **“Đã dùng HTTPS thì không thể lộ token.”** Sai. TLS bảo vệ trên đường truyền phù hợp; token vẫn có thể lộ ở endpoint, log, extension hoặc XSS.
4. **“Opaque token chống copy tốt hơn JWT.”** Sai. Cả hai có thể là bearer; khác biệt nằm ở cách chứa và xác minh.
5. **“Chỉ kiểm tra chữ ký + `exp` là đủ.”** Sai. Phải kiểm tra `iss`, `aud`, token type, scope/role và dữ liệu được phép truy cập.
6. **“ID Token có email và tên nên dùng gọi API được.”** Sai. API phải yêu cầu access token đúng audience/token profile.
7. **“Có `SCOPE_orders.read` thì được đọc mọi đơn hàng.”** Sai. Endpoint permission không thay object/tenant authorization.
8. **“Logout đã xóa token ở browser nên token bị đánh cắp vô hiệu.”** Không nhất thiết. Phải có policy revocation/expiry và xử lý session/refresh.
9. **“CORS chặn ai đó dùng bearer token đánh cắp.”** Không. HTTP client ngoài browser không chịu CORS.
10. **“Chỉ đổi `Authorization: Bearer` sang `DPoP` là chống replay.”** Sai. Phải có token binding và proof verification đầy đủ.
11. **“Thiết lập audience là bind token với thiết bị.”** Sai. Audience ràng buộc tài nguyên nhận token, không ràng buộc người trình.
12. **“Rate limit thay được kiểm tra token.”** Không. Rate limit giảm mức độ tấn công, không xác thực credential.

## 14. Ghi nhớ

**Bearer = ai nắm được token hợp lệ có thể trình token để dùng quyền của token.** Server xác minh token và policy, nhưng việc trình token **không tự chứng minh danh tính người đang giữ token**. JWT và opaque đều có thể là bearer. Chữ ký, scope, issuer, audience, thời hạn, TLS và thu hồi giúp bảo vệ/giới hạn quyền; nếu phải chống việc **sao chép token để sử dụng ở máy khác**, cần một thiết kế sender-constrained như mTLS certificate binding hoặc DPoP được kiểm chứng từ đầu đến cuối.

## 15. Tài liệu tham khảo

1. [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): định nghĩa bearer, `Authorization: Bearer`, rủi ro và bảo vệ.
2. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): các khuyến nghị OAuth bảo mật hiện đại.
3. [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): access token gắn chứng chỉ client.
4. [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): cơ chế token ràng buộc với public/private key và proof từng request.
5. [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile token JWT dùng cho access token.
6. [Spring Security 6.5 — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT validation, issuer, audience, scopes và authentication flow.
7. [Spring Security — Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): BearerTokenResolver và cách nhận token.
8. [Spring Security — Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection `active`, principal và scopes.
9. [Spring Boot — OAuth2 Security Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): `issuer-uri`, `audiences`, Resource Server properties.
