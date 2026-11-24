# Client authentication trước khi cấp token

Trong OAuth 2.0, **client authentication** là bước Authorization Server (AS) kiểm tra một ứng dụng hoặc dịch vụ đang gọi token endpoint có đúng là **client đã đăng ký** hay không, **khi client đó có khả năng và được yêu cầu xác thực**. Bước này đặc biệt quan trọng với **confidential client** như backend web, batch job hoặc service-to-service, bởi token có thể cho phép truy cập API theo danh tính service hoặc theo quyền mà người dùng đã ủy quyền.

Đây là bài học thuộc chương **Token issuance** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Chủ đề kết nối trực tiếp với mô hình tin cậy và vòng đời token: Authorization Code + PKCE, OAuth 2.0/OIDC, access token, refresh token, JWT/opaque token, claims, scope, audience, bảo vệ khóa, thu hồi và chống token bị đánh cắp hoặc phát lại.

**Phân biệt ngay từ đầu:** client authentication **không phải** xác thực người dùng, `client_id` **không phải** mật khẩu, và **không phải mọi OAuth client đều có thể giữ bí mật để xác thực**. Với **public client**, AS phải dựa vào những ràng buộc phù hợp như PKCE, redirect URI, đăng ký client và chính sách grant; không được giả vờ rằng một client secret được nhúng trong JavaScript/mobile là bí mật.

## 1. AS muốn chứng minh điều gì trước khi cấp token?

Giả sử ứng dụng `orders-bff` cần đổi authorization code thành access token để gọi Orders API. AS đã biết có client đăng ký với ID `orders-bff`, nhưng điều đó không có nghĩa bất kỳ request ghi `client_id=orders-bff` đều do backend thật gửi đến.

**Client authentication** trả lời: *“Bên gọi token endpoint có chứng minh được mình là client đã đăng ký, bằng cơ chế xác thực được AS tin cậy, khi cơ chế này được yêu cầu không?”*

Vấn đề liên quan nhưng độc lập gồm:

| Kiểm tra | Câu hỏi | Ví dụ |
|---|---|---|
| **Client identification** | Request tự nhận là client nào? | `client_id=orders-bff` |
| **Client authentication** | Bên gọi có chứng minh quyền sử dụng danh tính client đó không? | Bí mật, chữ ký private key JWT hoặc mTLS |
| **Grant validation** | Authorization code/refresh token/grant có hợp lệ và gắn với client này không? | Code chưa dùng, đúng `redirect_uri` và PKCE |
| **User authentication** | User đã được xác thực theo chính sách chưa? | Đăng nhập/MFA tại AS |
| **Authorization decision** | Quyền nào được cấp cho client hoặc thay mặt user? | `orders:read`, audience Orders API |
| **Token issuance** | Có cấp loại token, scope, thời hạn và ràng buộc phù hợp không? | Access token 10 phút; refresh token chỉ khi policy cho phép |

Một request có thể **xác thực client thành công nhưng vẫn bị từ chối cấp token** vì code hết hạn, refresh token bị thu hồi hoặc scope không được phép. Ngược lại, một public client có thể được cấp token theo flow hợp lệ **mà không có client authentication dùng bí mật**.

> **Nguyên tắc:** không coi “đã xác thực client” là giấy phép cấp mọi token; AS phải hoàn tất các ràng buộc grant, subject, audience, scope và policy trước khi phát hành.

## 2. Mô hình tin cậy: client, AS, user và API

~~~mermaid
flowchart LR
    U["User / Resource owner"]
    B["Browser / User agent"]
    C["Client backend: orders-bff"]
    AS["Authorization Server"]
    RS["Resource Server: Orders API"]

    U -->|"Đăng nhập/MFA khi cần"| AS
    B -->|"Authorization request"| AS
    AS -->|"Authorization code qua redirect"| B
    B -->|"Callback code"| C
    C -->|"Token request + client authentication + PKCE"| AS
    AS -->|"Kiểm tra client, code, scope, audience"| AS
    AS -->|"Access token và ID token nếu OIDC"| C
    C -->|"Bearer hoặc sender-constrained access token"| RS
    RS -->|"Verify token + quyền dữ liệu"| RS
~~~

Với ứng dụng browser dạng **Backend-for-Frontend (BFF)**, backend giữ credential và token; browser thường chỉ giữ cookie phiên của ứng dụng. Secret/private key **không được chuyển vào JavaScript**. Mô hình khác là ứng dụng native/public SPA: ứng dụng có thể gửi request token endpoint trực tiếp theo cấu hình AS, nhưng không thể bảo vệ một client secret nhúng trong gói phân phối.

Ba ranh giới phải được giữ tách biệt:

1. **Browser ↔ AS:** user xác thực và có thể cho phép grant theo chính sách; đây không phải client authentication bằng bí mật của backend.
2. **Client ↔ AS token endpoint:** AS xác định loại client, xác thực nếu cần, kiểm tra authorization grant và phát hành token.
3. **Client ↔ Resource Server:** API kiểm tra **access token** được cấp cho chính API, scope và quyền tài nguyên. API không nên nhận client secret của client như credential thay thế access token.

Một client có thể bị chiếm quyền dù user đã xác thực đúng. Vì vậy bảo mật token endpoint và bảo vệ credential của client là hai lớp kiểm soát độc lập với MFA của user.

## 3. Đăng ký client trước khi nói đến xác thực

AS cần có **client registration** hoặc nguồn cấu hình tin cậy tương đương. Ví dụ về metadata logic:

~~~json
{
  "client_id": "orders-bff",
  "client_type": "confidential",
  "allowed_grant_types": ["authorization_code", "refresh_token"],
  "redirect_uris": ["https://app.example.test/callback"],
  "token_endpoint_auth_method": "private_key_jwt",
  "registered_jwks_uri": "https://app.example.test/keys/client-jwks.json",
  "allowed_scopes": ["openid", "profile", "orders:read"],
  "allowed_audiences": ["https://orders-api.example.test"]
}
~~~

Đây là **mô hình cấu hình minh họa**, không phải JSON của một API đăng ký client cụ thể. Tên các trường `allowed_*` có thể do sản phẩm định nghĩa, khác với metadata chuẩn. Giá trị `registered_jwks_uri` phải đến từ quá trình đăng ký/quản trị được tin cậy; AS không lấy một URL khóa tùy ý do người gửi assertion cung cấp rồi mặc nhiên tin.

**Thông tin AS cần biết tối thiểu** tùy phương thức:

- `client_id` chính xác, loại client, grant được cho phép, redirect URI và quyền/audience giới hạn.
- **Phương thức xác thực tại token endpoint** đã đăng ký, ví dụ `client_secret_basic`, `private_key_jwt`, `tls_client_auth`.
- Bí mật được lưu dưới cơ chế phù hợp, hoặc khóa công khai/chứng chỉ/chuỗi tin cậy cần thiết để xác minh credential.
- Chính sách vòng đời credential, rotation, trạng thái disabled/revoked, giới hạn quyền, audit và rate limit.
- Bối cảnh tổ chức/tenant nếu hệ thống đa tenant và client bị giới hạn tài nguyên.

`client_id` thường là **định danh công khai**, có thể xuất hiện trong URL authorization request; biết client ID không chứng minh là client. Tương tự, biết `kid` hay đường dẫn JWKS **không** chứng minh sở hữu khóa riêng.

### Client ID và client credential là hai thứ khác nhau

~~~text
client_id         -> "Tôi là ứng dụng orders-bff"
client credential -> "Tôi chứng minh mình đang sở hữu
                      bí mật/khóa/chứng chỉ của orders-bff"
authorization code -> "AS đã cho phép một giao dịch authorization
                      cụ thể, còn cần kiểm tra ràng buộc"
access token      -> "Quyền truy cập API có audience/scope/thời hạn"
~~~

Không đặt client secret trong `client_id`, không dùng `client_id` như API key bí mật và không dùng access token hiện có để tự chứng minh client tại token endpoint trừ khi giao thức/protocol profile cho phép một cơ chế token exchange riêng.

## 4. Confidential client và public client

| Tiêu chí | Confidential client | Public client |
|---|---|---|
| Môi trường | Backend server, service do tổ chức kiểm soát | SPA trong browser, ứng dụng mobile/desktop phân phối |
| Có thể giữ credential bí mật? | Có, nếu triển khai và vận hành đúng | Không thể coi secret nhúng trong mã/binary là bí mật đáng tin |
| Phương thức xác thực client điển hình | Shared secret, private key JWT, mTLS | Thường là `none` tại token endpoint |
| Ràng buộc quan trọng khi dùng authorization code | Client authentication **và** PKCE theo chính sách | PKCE S256, redirect URI, code/client binding |
| Rủi ro chính | Lộ secret/private key, giả mạo service, sai cấu hình TLS/JWKS | Đánh cắp code/token, XSS/malware, redirect interception |
| Có được cấp access token? | Có, nếu grant và policy hợp lệ | Có, nếu grant và policy cho phép |
| Có được cấp refresh token? | Chỉ khi chính sách cho phép | Chỉ khi chính sách cho phép, cần bảo vệ bổ sung như rotation hoặc sender constraint |

**Public ≠ không an toàn và confidential ≠ tự động an toàn.** Mô hình bảo vệ khác nhau. Public client không thể giữ một bí mật toàn cục được phân phối giống nhau cho mọi người cài ứng dụng. AS không nên coi việc public client gửi “client_secret” được lấy từ bundle là client authentication có giá trị bảo mật.

Trong OAuth 2.0, một số client có nhiều thành phần và khả năng giữ bí mật khác nhau. Cần phân loại dựa trên **thành phần thực hiện token request và nơi lưu credential**, không chỉ dựa vào tên “web app” hay “mobile app”.

## 5. Các phương thức client authentication phổ biến

| Phương thức | Bằng chứng gửi tới AS | Ưu điểm | Yêu cầu và rủi ro |
|---|---|---|---|
| `client_secret_basic` | Client ID và secret trong HTTP Basic header | Hỗ trợ rộng, cấu hình đơn giản | Secret đối xứng phải bảo vệ; luôn dùng TLS; Basic Base64 **không mã hóa** |
| `client_secret_post` | Client ID và secret trong form body | Tương thích với hệ thống cũ | Secret dễ lọt vào body logging; chỉ dùng khi được AS cho phép và có lý do |
| `client_secret_jwt` | JWT client assertion ký bằng khóa HMAC chia sẻ | Có assertion giới hạn thời gian | Quản lý shared secret, thuật toán, audience và replay |
| `private_key_jwt` | JWT client assertion ký bằng private key của client | AS chỉ cần public key đã đăng ký để verify; rotation khóa riêng | Bảo vệ private key, verify chữ ký/issuer/audience/jti/thời gian, quản lý JWKS |
| `tls_client_auth` | Client certificate qua mutual TLS (mTLS) | Chứng minh sở hữu private key trong kênh TLS | PKI/trust chain, danh tính cert, proxy/TLS termination và rotation |
| `self_signed_tls_client_auth` | Client certificate tự ký **đã đăng ký** qua mTLS | Không bắt buộc dựa trên CA công cộng | Phải đối chiếu chính xác cert hoặc khóa theo cơ chế đăng ký |
| `none` | Không có client credential | Phù hợp public client | **Không phải client authentication**; vẫn cần ràng buộc grant và policy |

Danh sách trên phản ánh các phương thức thường gặp trong OAuth 2.0/OIDC và các extension; không phải mọi AS hỗ trợ tất cả. **Chỉ chấp nhận phương thức đã đăng ký và được AS cấu hình**. Client tự chọn phương thức yếu hơn trong request không được phép tạo một đường “fallback” bỏ qua client authentication.

Khi có khả năng vận hành khóa, các phương thức bất đối xứng như `private_key_jwt` hoặc mTLS có thể giảm phụ thuộc vào shared secret được chia sẻ giữa AS và client. Dù chọn cách nào, AS vẫn cần rate limit, audit, bảo vệ token endpoint và phòng replay theo đặc trưng phương thức.

## 6. Xác thực bằng client secret và HTTP Basic

Một confidential client backend có thể được cấp client secret đủ ngẫu nhiên và được AS lưu/kiểm chứng an toàn. Với `client_secret_basic`, token request sử dụng HTTP Basic qua **HTTPS**.

Ví dụ đổi authorization code:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <BASE64_OF_ENCODED_CLIENT_ID_AND_SECRET>

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&code_verifier=<ORIGINAL_CODE_VERIFIER>
~~~

Cần hiểu rõ:

- HTTP Basic credential được biểu diễn bằng **Base64 thông thường**, **không phải mã hóa bí mật**. Token endpoint bắt buộc dùng TLS để bảo vệ request trên đường truyền.
- Theo OAuth 2.0, `client_id` và `client_secret` được form-url-encode theo quy tắc giao thức trước khi ghép thành giá trị Basic; thư viện OAuth tuân chuẩn nên thực hiện chi tiết này thay vì xây chuỗi thủ công.
- Header `Authorization` chứa secret và phải được **loại khỏi access log, tracing, error report và debug output**.
- Confidential client cần lưu secret trong kho bí mật phía server (secret manager/vault hoặc cơ chế tương đương), không commit vào repository, file công khai, biến môi trường bị in ra log hay bundle frontend.
- Nếu dùng `client_secret_post`, body chứa secret và phải được bảo vệ tương tự. AS không nên khuyến khích truyền secret qua URL/query string.
- Không gửi hai phương thức client authentication cùng một request. Ví dụ vừa Basic vừa `client_secret` trong body là hành vi không hợp lệ theo mô hình OAuth.

Client secret chỉ chứng minh quyền sử dụng danh tính client theo AS; nó **không chứng minh user đã cho consent hoặc code/refresh token hợp lệ**. AS vẫn phải kiểm tra grant type, scope, audience, redirect URI, PKCE và trạng thái grant.

### Tại sao secret tĩnh cần chính sách vòng đời?

Nếu một secret lộ, kẻ tấn công có thể giả client cho tới khi secret bị thu hồi/thay thế, nhưng mức độ khai thác còn phụ thuộc grant và ràng buộc khác. Ví dụ với `client_credentials`, secret lộ có thể trực tiếp tạo điều kiện xin access token thuộc quyền của service.

Biện pháp gồm phát hành secret entropy cao, phân tách client theo môi trường, least privilege, rotation theo quy trình có kiểm chứng, phát hiện bất thường, rate limiting và thu hồi ngay khi nghi lộ. Không dùng chung một client secret cho nhiều service hoặc nhiều tenant nếu không có yêu cầu thiết kế rất cụ thể.

## 7. Xác thực client bằng private_key_jwt

Với `private_key_jwt`, client tạo một **JWT client assertion** có chữ ký số bằng **private key** chỉ client giữ. AS dùng **public key đã đăng ký** để xác minh rằng request đến từ client sở hữu khóa tương ứng.

Đây là JWT dùng để **xác thực client tại token endpoint**, **không phải** access token hay ID token dành cho API/user.

Ví dụ header JWT:

~~~json
{
  "alg": "PS256",
  "typ": "JWT",
  "kid": "orders-bff-key-2026-11"
}
~~~

Ví dụ claims cho assertion:

~~~json
{
  "iss": "orders-bff",
  "sub": "orders-bff",
  "aud": "https://auth.example.test/oauth2/token",
  "iat": 1800000000,
  "exp": 1800000060,
  "jti": "assertion-unique-7a1c"
}
~~~

Dữ liệu trên chỉ là header/payload minh họa, **chưa có chữ ký thật**. Trong profile private_key_jwt của OIDC/OAuth, `iss` và `sub` nhận diện client, `aud` phải đúng audience mà AS yêu cầu (thường là token endpoint), `exp` có hạn ngắn, `jti` là định danh assertion giúp chống replay khi AS áp dụng kiểm tra một lần dùng. Một số profile yêu cầu hoặc cho phép các claim bổ sung; client phải tuân thủ hợp đồng với AS.

Token request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&code_verifier=<VERIFIER>&client_id=orders-bff&client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&client_assertion=<SIGNED_CLIENT_ASSERTION_JWT>
~~~

Ở đây `client_assertion_type` được form-encode cho media type `application/x-www-form-urlencoded`. Request chưa thể thành công nếu không có **assertion thực được ký** và các ràng buộc grant hợp lệ.

### AS phải xác minh assertion thế nào?

1. Xác định client registration đúng theo `client_id`/claims được phép, không tin trực tiếp chuỗi `iss` chưa xác minh.
2. Lấy khóa công khai **từ metadata đã đăng ký hoặc nguồn tin cậy**, chọn theo `kid` có kiểm soát; không fetch bất kỳ URL khóa được nhúng trong JWT.
3. Kiểm tra thuật toán chữ ký được phép (ví dụ PS256 theo registration), xác minh chữ ký số.
4. Đối chiếu `iss` và `sub` với client ID đã đăng ký theo profile, và `aud` với token endpoint/AS audience được chấp nhận.
5. Kiểm tra `exp` còn hiệu lực, thời gian `iat`/`nbf` nếu có, độ lệch đồng hồ và TTL tối đa theo chính sách.
6. Chặn replay bằng `jti`/nonce hoặc cơ chế chống lặp tương ứng trong cửa sổ hiệu lực, theo profile/chính sách.
7. Xác minh trạng thái client, quyền dùng grant, scope/audience và các điều kiện token request trước khi cấp token.

**Lưu ý:** `client_assertion` có thể bị sao chép nếu rò trong logs; chữ ký bảo vệ nguồn assertion nhưng tự nó không chống phát lại. Assertion phải ngắn hạn, dùng `jti` và được AS kiểm tra theo chính sách; không ghi raw assertion vào audit log.

### Rotation private key

Quá trình rotation cần giữ khóa cũ và mới trong cửa sổ chuyển tiếp được kiểm soát: client ký bằng khóa mới, AS đã biết public key tương ứng, thử nghiệm trước cutover, sau đó bỏ tin khóa cũ. `kid` hỗ trợ chọn khóa, nhưng không phải bằng chứng tin cậy. Khóa riêng nên nằm ở secret manager/HSM hoặc kho bảo vệ khóa phù hợp, kiểm soát quyền ký và audit các lần sử dụng.

## 8. Xác thực client bằng mutual TLS (mTLS)

Với **mTLS client authentication**, client và AS thiết lập TLS trong đó client trình **chứng chỉ client** và chứng minh sở hữu private key trong TLS handshake. AS kiểm tra certificate hoặc định danh certificate theo cơ chế client đã đăng ký.

Hai phương thức phổ biến theo RFC 8705:

| Phương thức | Cách AS đối chiếu | Điều cần tránh |
|---|---|---|
| `tls_client_auth` | Kiểm tra chứng chỉ theo chuỗi tin cậy và thông tin định danh từ certificate được đăng ký (ví dụ subject DN hoặc SAN phù hợp profile) | Chỉ thấy có một certificate bất kỳ rồi coi đó là client |
| `self_signed_tls_client_auth` | Đối chiếu chứng chỉ/khóa cụ thể đã đăng ký với AS | Chấp nhận tự ký bất kỳ chỉ vì TLS handshake thành công |

Một token request mTLS minh họa (certificate được xác minh ở tầng TLS, không thể hiện hết trong HTTP):

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=inventory-service&scope=inventory:read
~~~

AS không nhận chứng chỉ chỉ bằng chuỗi trong body. Nếu có reverse proxy hoặc gateway kết thúc TLS, **chuỗi tin cậy truyền danh tính certificate tới AS** phải được bảo vệ nghiêm ngặt; không nhận header `X-Client-Cert` từ Internet do người dùng tự gửi.

### Client authentication khác certificate-bound access token

RFC 8705 cũng mô tả cơ chế **certificate-bound access token**. Hai việc liên quan nhưng khác nhau:

- **mTLS client authentication tại token endpoint:** chứng minh client khi xin token.
- **mTLS sender-constrained access token tại Resource Server:** token ràng buộc với certificate/key; người gọi API phải chứng minh sở hữu khóa tương ứng.

Một AS có thể triển khai cả hai, hoặc chỉ một cơ chế theo hợp đồng. Token được ràng buộc có thể chứa claim `cnf` với thumbprint certificate (như `x5t#S256`) hoặc có thông tin ràng buộc tương đương; Resource Server phải kiểm tra bằng chứng sở hữu khóa trên request, chứ không chỉ kiểm tra JWT chữ ký AS.

Chứng chỉ hết hạn hoặc rotation bị lệch cấu hình có thể làm token request thất bại. Vì vậy cần thời gian chuyển tiếp, quan sát lỗi TLS, chính sách trust store và cách xử lý khi khóa/chứng chỉ bị lộ.

## 9. PKCE và DPoP không thay thế client authentication

Các lớp bảo vệ có thể cùng xuất hiện trên một request, nhưng mục tiêu khác nhau.

| Cơ chế | Đối tượng chứng minh/ràng buộc | Bảo vệ chính | Có phải client authentication theo registration? |
|---|---|---|---|
| **Client secret** | Bên gọi biết secret của confidential client | Danh tính client tại AS | **Có**, khi AS đã đăng ký phương thức |
| **private_key_jwt** | Bên gọi sở hữu private key của client | Danh tính client tại AS | **Có** |
| **mTLS client authentication** | Bên gọi sở hữu private key của cert client | Danh tính client tại AS | **Có** |
| **PKCE S256** | Bên đổi authorization code biết `code_verifier` tương ứng với challenge ban đầu | Chống interception/code injection trong code exchange | **Không**: không xác minh danh tính đăng ký client |
| **OAuth `state`** | Callback thuộc authorization transaction đã khởi tạo | Liên kết response, chống CSRF/mix-up khi kết hợp cơ chế phù hợp | **Không** |
| **DPoP** | Bên gửi request sở hữu khóa ký proof | Sender-constrain token hoặc chứng minh khóa ở request thích hợp | **Không tự động** là authentication cho client registration |
| **User MFA** | Người dùng chứng minh danh tính/mức đảm bảo | Bảo vệ tài khoản user và consent | **Không** |

**PKCE không phải “mật khẩu client”.** Public client không thể giữ secret nhưng vẫn dùng PKCE để bảo vệ việc đổi code. Confidential client cũng nên triển khai PKCE theo thực hành bảo mật hiện đại; client authentication chỉ làm tăng lớp bảo vệ, không thay thế PKCE trong thiết kế cần nó.

**DPoP (RFC 9449)** sử dụng một JWT proof ký bằng khóa của phía gửi để giảm khả năng sử dụng token bị sao chép đơn lẻ. Proof này có thuộc tính như HTTP method/URI, thời gian, `jti` và có thể nonce. Nó **không tự động xác nhận chủ sở hữu khóa là client `orders-bff` đã đăng ký**, trừ khi một profile hoặc chính sách AS ràng buộc khóa đó với client identity rõ ràng.

Một access token ký JWS vẫn có thể là **bearer token**, nghĩa là người giữ bản sao token có thể sử dụng trong thời hạn chấp nhận nếu không có sender constraint. Xác thực client lúc phát hành không tự ngăn attacker dùng access token bị đánh cắp sau đó ở API.

## 10. Luồng đầy đủ: Authorization Code + PKCE + confidential client

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant C as orders-bff
    participant AS as Authorization Server
    participant API as Orders API

    B->>C: Mở ứng dụng
    C->>C: Tạo state, nonce và PKCE verifier
    C-->>B: Redirect đến AS với code_challenge
    B->>AS: /authorize (client_id, scope, state, PKCE)
    AS->>U: Xác thực/MFA nếu cần
    AS->>AS: Kiểm tra client, redirect, grant/consent
    AS-->>B: Redirect code + state
    B->>C: Callback code + state
    C->>C: Kiểm tra state và transaction
    C->>AS: /token: code + PKCE verifier + client authentication
    AS->>AS: Verify client credential
    AS->>AS: Verify code, PKCE, redirect, client binding, grant
    AS->>AS: Xét scope, audience, TTL và risk policy
    AS-->>C: Access token (+ ID token/refresh token nếu đủ điều kiện)
    C->>C: Xác minh ID token nếu OIDC; tạo phiên ứng dụng
    C->>API: Gọi API với access token
    API->>API: Verify issuer, audience, time, scope, object policy
    API-->>C: Dữ liệu theo quyền
~~~

**Đây là hai loại xác thực khác nhau:**

- Ở authorization endpoint, user xác thực theo chính sách AS; AS cho phép một authorization grant.
- Ở token endpoint, confidential client xác thực để đổi code do AS đã cấp. AS còn ràng buộc **code với chính client** và xác minh PKCE.

Nếu kẻ tấn công lấy được code từ browser nhưng không có `code_verifier` và không có credential của confidential client, token endpoint đúng chuẩn phải từ chối. Nếu kẻ tấn công lấy được cả client secret nhưng không có code/grant hợp lệ, AS cũng không được cấp token dựa trên authorization code không tồn tại hoặc không thuộc client.

**Không có một “mật khẩu đa năng” thay thế các kiểm tra.** Ràng buộc và phạm vi phải được thực thi cùng lúc.

## 11. Token endpoint kiểm tra gì theo từng grant?

### Authorization Code grant

AS cần kiểm tra đồng thời:

1. Request qua TLS, token endpoint đúng, tham số hợp lệ, không có nhiều phương thức client authentication chồng chéo.
2. `client_id` và client registration, **xác thực confidential client** bằng phương thức đã đăng ký; với public client, xác định client theo contract nhưng không tưởng tượng có secret.
3. `grant_type=authorization_code` được phép cho client.
4. Authorization code tồn tại, chưa hết hạn, chưa dùng, do AS này phát hành và được ràng buộc đúng client.
5. `redirect_uri` khớp với giá trị ràng buộc khi cấp code theo quy tắc áp dụng.
6. `code_verifier` thỏa PKCE S256 challenge của authorization transaction.
7. Grant/consent, user/account, scope và audience không bị chính sách chặn.
8. Đánh dấu code đã sử dụng **nguyên tử/chống race** trước khi có thể bị đổi lần hai.
9. Chỉ sau đó phát hành access token, ID token nếu OIDC, refresh token nếu đủ điều kiện; ghi audit an toàn mà không log raw credential.

Với **confidential client**, `client_id` được lấy từ client authentication context hoặc đối chiếu với thông tin đã xác thực. Không tin một `client_id` khác trong body để “chọn” client tùy ý. Với nhiều AS, cần chống authorization-server mix-up, bảo đảm code được đổi tại token endpoint của đúng issuer dự kiến.

### Client Credentials grant

Đây là luồng **không có user đang ủy quyền**; token phản ánh quyền của client/service:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_CREDENTIALS_PLACEHOLDER>

grant_type=client_credentials&scope=inventory%3Aread
~~~

AS phải **xác thực client** và kiểm tra nó có được phép dùng `client_credentials`, scope và resource/audience được phép không. Client ID đơn thuần hoặc một secret nhúng trong ứng dụng public không phải cơ sở để tạo token service đáng tin cậy.

Ví dụ response:

~~~json
{
  "access_token": "<ACCESS_TOKEN_FOR_INVENTORY_API>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "inventory:read"
}
~~~

AS thông thường không cấp refresh token trong Client Credentials flow theo khuyến nghị OAuth; service có thể xác thực lại để xin access token mới. API phải kiểm tra token và **quyền của service/client**, không tự giả định token đại diện user vì có `sub` hoặc token dùng JWT.

### Refresh Token grant

Refresh token không thay thế việc xác thực client:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_CREDENTIALS_PLACEHOLDER>

grant_type=refresh_token&refresh_token=<REFRESH_TOKEN_VALUE>
~~~

Đối với confidential client đã được cấp credential, AS phải kiểm tra client authentication theo yêu cầu và **refresh token có thuộc grant/client đó không**, còn hiệu lực không, có bị rotation/revoke không, scope xin mới có vượt quyền grant không, và account/client policy hiện tại có cho phép không.

Khi AS cấp refresh token cho public client, nó phải dùng cơ chế phù hợp để bảo vệ khỏi replay như rotation hoặc sender-constrained token theo profile/chính sách bảo mật hiện đại. Public client không chứng minh identity bằng client secret; AS vẫn gắn refresh token với client đã được cấp và có thể kiểm tra ràng buộc kỹ thuật bổ sung.

> **Lỗi nguy hiểm:** AS xác thực confidential client A thành công nhưng lại chấp nhận refresh token cấp cho client B. Việc kiểm tra “secret đúng” chưa đủ; refresh token còn phải được ràng buộc với đúng client và grant.

## 12. Thứ tự kiểm tra an toàn tại token endpoint

Pseudo-code minh họa tư duy của AS, **không phải API của thư viện Java hay production code**:

~~~text
function issueToken(request, trustedTransportContext):
    requireTlsAndTrustedTokenEndpoint(request)

    parsed = parseAndValidateTokenRequest(request)
    if parsed.invalid or parsed.usesMultipleClientAuthMethods:
        return oauthError("invalid_request")

    registration = lookupRegisteredClient(parsed.clientIdentifier)
    if registration missing or disabled:
        return oauthError("invalid_client")

    if registration.isConfidential:
        authenticatedClient = authenticateUsingRegisteredMethod(
            registration,
            parsed,
            trustedTransportContext
        )
        if authenticatedClient invalid:
            auditAuthFailureWithoutSecrets()
            return oauthError("invalid_client")
    else:
        requireConfiguredPublicClientPolicy(registration)
        authenticatedClient = publicClientIdentificationOnly(registration)

    if parsed.grantType not in registration.allowedGrantTypes:
        return oauthError("unauthorized_client")

    grant = validateGrantAndBindToClient(
        parsed,
        authenticatedClient,
        checkPkceAndRedirectWhenApplicable = true,
        checkRefreshBindingAndRotationWhenApplicable = true
    )
    if grant invalid:
        return oauthError("invalid_grant")

    grantDecision = authorizeRequestedScopeAndAudience(
        authenticatedClient,
        grant,
        currentPolicy
    )
    if grantDecision.invalidScope:
        return oauthError("invalid_scope")
    if grantDecision.denied:
        return oauthErrorForPolicyDenied()

    tokens = createTokensFor(
        verifiedClient = authenticatedClient,
        grant = grant,
        scopes = grantDecision.allowedScopes,
        audience = grantDecision.allowedAudience,
        lifetime = grantDecision.allowedLifetime,
        senderConstraint = grantDecision.tokenBindingPolicy
    )

    atomicallyConsumeOneTimeInputsAndPersistTokenState(tokens, grant)
    auditSuccessfulIssuanceWithoutRawSecretsOrTokens()

    return oauthTokenResponseNoStore(tokens)
~~~

Các bước kiểm tra cụ thể và thứ tự trả lỗi có thể thay đổi để tránh **rò thông tin về client hoặc grant**, nhưng mọi điều kiện cần thiết phải được thỏa **trước khi công bố một token hợp lệ**. Đặc biệt, “atomic” biểu thị mục tiêu chống race với authorization code/rotation; hiện thực hóa qua transaction, khóa/compare-and-swap hoặc cơ chế bền vững thích hợp.

Khi `client_credentials` không có authorization grant user, hàm `validateGrantAndBindToClient` trong pseudocode tương ứng với việc kiểm tra **đúng loại grant và quyền service**. Không ép flow machine-to-machine thành một authorization code flow có user giả.

## 13. Token response và phân loại lỗi client authentication

Khi AS phát hành thành công access token, response thường có `Cache-Control: no-store` và `Pragma: no-cache`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<OPAQUE_OR_JWT_ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

**Client authentication chỉ là một phần của issuance decision.** Phản hồi thành công ở đây không ngụ ý token là JWT, cũng không ngụ ý được cấp refresh token. Nếu API sử dụng JWT access token, nó phải kiểm tra signature/issuer/audience/exp/scope; nếu opaque, nó phải sử dụng introspection hoặc cơ chế trạng thái tin cậy. ID token chỉ có trong luồng OIDC phù hợp, và API không nhận ID token thay access token.

### Các nhóm lỗi OAuth thường gặp

| Lỗi | Ý nghĩa | Điểm điều tra |
|---|---|---|
| `invalid_client` | Client authentication thất bại hoặc danh tính client không được chấp nhận | Secret sai, assertion signature/aud/exp sai, cert mismatch, client disabled |
| `unauthorized_client` | Client không được phép dùng grant type đã yêu cầu | Client chỉ được dùng authorization_code nhưng gửi client_credentials |
| `invalid_grant` | Grant/code/refresh token không hợp lệ | Code hết hạn/đã dùng, PKCE sai, refresh token không gắn với client, grant thu hồi |
| `invalid_scope` | Scope được xin không hợp lệ hoặc không được phép theo AS | Xin quyền chưa đăng ký hoặc vượt phạm vi |
| `invalid_request` | Request thiếu tham số, sai cấu trúc hoặc dùng nhiều cơ chế client auth | Body không hợp lệ hoặc credential lặp |

Khi client dùng HTTP Authorization header để xác thực nhưng thất bại, OAuth 2.0 quy định xử lý `invalid_client` kèm HTTP `401` và header `WWW-Authenticate` phù hợp. Không suy diễn mọi lỗi token endpoint là `401`; status và error phải theo phương thức/protocol đang dùng. Không trả chi tiết nhạy cảm như “secret gần đúng”, tên khóa riêng hoặc grant của client khác cho requester không được phép.

Ví dụ lỗi tối giản:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="auth-server"
Cache-Control: no-store

{
  "error": "invalid_client"
}
~~~

Bản ghi audit nội bộ có thể phân biệt `INVALID_CLIENT_SECRET`, `ASSERTION_REPLAY` hay `CERTIFICATE_MISMATCH`, nhưng response công khai nên hạn chế thông tin giúp attacker liệt kê client/credential.

### Authorization vs authentication error

Một client có `private_key_jwt` hợp lệ nhưng xin `orders:admin` ngoài quyền vẫn phải bị từ chối ở lớp **policy/authorization**, không được cấp token rồi hy vọng API xử lý. Ngược lại, nếu client không chứng minh được identity theo registration, AS phải chặn ngay cả khi authorization code được đánh cắp trông có vẻ hợp lệ.

## 14. Quản lý credential và vòng đời token

### Lưu secret/private key

- **Đặt tại backend tin cậy:** server vault, secret manager, HSM hoặc hệ thống quản lý khóa phù hợp; không nhúng vào mobile, SPA, Docker image công khai hay repository.
- **Phân tách môi trường:** dev/staging/prod dùng client registration và credential riêng; không cho dev client xin prod token.
- **Least privilege:** credential của một client chỉ cho phép những grant, scope và audience cần thiết. Không chia sẻ một secret cho nhiều client chỉ để thuận tiện vận hành.
- **Không log bí mật:** redaction cho `Authorization` header, `client_secret`, `client_assertion`, token, authorization code, PKCE verifier và cookie.
- **Rate limiting và anti-abuse:** giới hạn thử credential, phát hiện abnormal authentication, theo dõi lỗi JWT/cert và bảo vệ token endpoint khỏi DoS.
- **Rotation/revoke:** có lịch và quy trình khẩn cấp, lưu lịch sử theo reference, không giữ credential đã bị thu hồi vô thời hạn. Với public key rotation, cấu hình AS và client phải có khoảng chuyển tiếp an toàn.

### Token được phát hành phải có giới hạn

Ngay cả sau khi AS xác thực client, access token phải có audience/resource đúng, scope đã cấp, thời hạn hợp lý và subject/client context rõ ràng. Với JWT, AS bảo vệ token bằng chữ ký hoặc mã hóa tùy profile và API phải verify; với opaque token, AS quản lý trạng thái và cung cấp introspection khi cần.

**Client auth không đảm bảo token không bị đánh cắp sau issuance.** Cần thêm bảo vệ nơi lưu token, HTTPS, ngăn log, refresh rotation/reuse detection, thu hồi, token ngắn hạn và sender-constrained token như DPoP/mTLS khi đáp ứng threat model.

### Audit cần ghi những gì?

Một bộ audit tối thiểu tại token endpoint nên ghi **thời điểm, client reference, phương thức auth đã đăng ký, loại grant, audience, scope được cấp, outcome, reason code và token/transaction reference an toàn**, đồng thời tránh lưu raw credential hoặc token.

Ví dụ sự kiện minh họa:

~~~json
{
  "event_type": "token.issuance.decided",
  "occurred_at": "2026-11-23T10:11:12Z",
  "client_id": "orders-bff",
  "client_auth_method": "private_key_jwt",
  "grant_type": "authorization_code",
  "audience": "https://orders-api.example.test",
  "granted_scopes": ["orders:read"],
  "decision": "ALLOW",
  "reason_code": "CLIENT_AND_GRANT_VERIFIED",
  "grant_ref": "grant-pseudo-81",
  "token_ref": "token-pseudo-721"
}
~~~

Các reference này là **pseudonym/hệ thống cấp**, không phải secret/token thật. AS và RS cần bảo vệ log khỏi thay đổi, giới hạn lưu trữ theo chính sách, phân quyền đọc và liên kết sự kiện của token với grant/thu hồi để điều tra.

## 15. Tình huống thực tế: backend web và mobile app

Giả sử nền tảng Orders có hai client:

| Client | Loại | Cơ chế token endpoint | Grant cho phép |
|---|---|---|---|
| `orders-bff` | Confidential backend | `private_key_jwt` + PKCE khi đổi code | `authorization_code`, `refresh_token` |
| `orders-mobile` | Public native app | `none` + PKCE S256 cho code | `authorization_code`, refresh nếu policy cho phép |

Cùng AS, nhưng **cách xác thực client khác nhau**:

1. User đăng nhập và AS cấp authorization code cho `orders-bff`. Backend đổi code bằng PKCE verifier **và** JWT assertion ký bằng private key. Nếu assertion sai, request không thành công dù code đúng.
2. User đăng nhập trên `orders-mobile` và AS cấp code cho mobile client. App đổi code bằng `client_id` và PKCE verifier, **không có client secret**. Nếu app gửi một secret hardcoded giả, AS không được coi nó là bằng chứng mạnh.
3. Attacker đánh cắp authorization code của mobile nhưng không có verifier: AS phải từ chối code exchange nếu PKCE đúng.
4. Attacker biết client ID của backend nhưng không có private key: không thể xác thực như `orders-bff` với private_key_jwt hợp lệ.
5. Attacker có private key backend nhưng không có grant hợp lệ: AS vẫn phải từ chối yêu cầu đổi code/refresh không đúng, dù rủi ro với `client_credentials` hoặc các grant khác cần được đánh giá theo registration.
6. Backend vô tình gửi access token dành cho Orders API đến Billing API: Billing API phải từ chối nếu audience không phù hợp, dù token xuất phát từ confidential client đã xác thực.
7. User thu hồi grant: việc có credential client đúng không cho phép client tạo lại access token qua refresh token đã bị thu hồi.
8. Backend có `orders:read` nhưng user không có quyền xem đơn hàng của người khác: Orders API vẫn phải kiểm tra ACL/tenant trước khi trả dữ liệu.

### Bài kiểm tra nhanh

**Câu 1.** `client_id` xuất hiện công khai trong authorization URL. Có phải client secret không? **Không.** Đây là định danh; không chứng minh sở hữu credential.

**Câu 2.** `client_secret_basic` chứa Base64. Đã đủ mã hóa secret chưa? **Không.** Base64 chỉ encoding; cần HTTPS và bảo vệ secret.

**Câu 3.** Confidential client đã authenticate thành công nhưng gửi code cấp cho client khác. AS có cấp token? **Không.** Code phải được ràng buộc với đúng client.

**Câu 4.** Public mobile client có PKCE S256 thành công. Nó có thực hiện confidential client authentication không? **Không.** PKCE bảo vệ code exchange, không xác thực client theo bí mật đăng ký.

**Câu 5.** DPoP proof hợp lệ đồng nghĩa client đã authenticated bằng private_key_jwt? **Không.** DPoP proof-of-possession và client authentication là hai cơ chế khác nhau.

**Câu 6.** mTLS client authentication thành công làm API tự động chấp nhận access token? **Không.** API còn phải kiểm tra đúng token, audience, scope, thời gian và quyền tài nguyên.

## 16. Checklist triển khai và rà soát an ninh

1. **Xác định loại client chính xác:** confidential hay public dựa trên thành phần thực hiện token request và khả năng bảo vệ credential.
2. **Đăng ký đúng phương thức:** `client_secret_basic`, `private_key_jwt`, `tls_client_auth` hoặc `none` phù hợp; không có đường hạ cấp không chủ ý.
3. **Không coi client ID là bí mật:** client ID là định danh; chỉ credential có kiểm chứng mới thực hiện client authentication.
4. **Chỉ gửi credential qua kênh an toàn:** HTTPS/TLS, bảo vệ log, không query string, không lưu public bundle.
5. **Với shared secret:** entropy cao, quản lý vault, rotation, cách tạo Basic đúng chuẩn, không lộ qua body logging.
6. **Với private_key_jwt:** khóa công khai đã đăng ký, thuật toán allowlist, issuer/subject/audience, `exp` và `jti`, chống replay và rotation.
7. **Với mTLS:** đối chiếu certificate/identity đúng registration, bảo vệ TLS termination, quản lý chứng chỉ và trust store.
8. **Dùng PKCE đúng vai trò:** S256 cho Authorization Code flow phù hợp; kiểm tra `state`/redirect và tránh mix-up; đừng gọi PKCE là client authentication.
9. **Ràng buộc grant với client:** code một lần dùng, đúng client và redirect; refresh token đúng client/grant, rotation và thu hồi theo policy.
10. **Giới hạn quyền khi phát hành:** grant type được phép, scope/audience/resource đúng, TTL phù hợp, token type và claims đúng profile.
11. **Xử lý lỗi theo giao thức:** `invalid_client`, `unauthorized_client`, `invalid_grant`, `invalid_scope` và `invalid_request` không bị gộp hoặc rò thông tin nhạy cảm.
12. **Đừng nhầm token với credential client:** access token cho API, refresh token cho token endpoint, ID token cho client OIDC; JWT/opaque chỉ là định dạng kiểm tra tương ứng.
13. **Bảo vệ token sau phát hành:** storage, TLS, revocation, refresh reuse detection, sender constraints nếu cần; client authentication đơn lẻ không chống bearer replay.
14. **Kiểm thử allow/deny:** secret sai, assertion hết hạn/replay, cert lạ, code cấp cho client khác, verifier sai, grant bị thu hồi, scope/audience vượt quyền và lỗi đa phương thức.
15. **Audit và giám sát:** log client auth/issuance decision bằng reference an toàn, rate limit token endpoint, cảnh báo bất thường và bảo vệ audit logs.

**Ghi nhớ:** trước khi cấp token, AS phải phân biệt **client nào đang xin**, **client đó có cần và có thực sự xác thực được hay không**, **grant có thuộc client và còn hiệu lực không**, rồi mới quyết định **scope, audience, subject và thời hạn token**. **Client authentication là một lớp tin cậy cần thiết cho confidential client, nhưng không thay thế user authentication, PKCE, grant validation hay API authorization.**

### Tài liệu chuẩn để tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Section 2.3 và 3.2.1 về client authentication, token endpoint và grant.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth, PKCE và refresh token.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): ràng buộc code với verifier.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): client assertion JWT.
- [OpenID Connect Core 1.0 — Client Authentication](https://openid.net/specs/openid-connect-core-1_0.html#ClientAuthentication): `client_secret_basic`, `private_key_jwt` và phương thức liên quan.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS client auth và token binding.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): chống lạm dụng bản sao token bằng chứng sở hữu khóa.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata giúp client xác định token endpoint và các phương thức được AS công bố.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) và [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): kiểm tra trạng thái và thu hồi token.
