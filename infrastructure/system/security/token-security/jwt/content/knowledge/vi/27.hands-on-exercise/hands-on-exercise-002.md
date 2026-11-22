# Xây dựng hợp đồng JWT cho một API có một bên phát hành

## 1. Mục tiêu thực hành

Trong bài này, bạn sẽ thiết kế một hợp đồng JSON Web Token (JWT) cho một API được bảo vệ và chỉ tin cậy một bên phát hành token. Hợp đồng mô tả chính xác issuer phát hành token như thế nào, API xác minh token ra sao, claims nào được phép sử dụng, quyền được biểu diễn thế nào và hai bên phải xử lý rotation, expiration, revocation cùng lỗi xác thực theo quy tắc nào.

Tình huống xuyên suốt:

- Identity service là bên phát hành duy nhất, có issuer định danh là một URL cố định.
- Orders API là resource server duy nhất trong phạm vi bài tập.
- Web client hoặc một ứng dụng khác lấy access token từ identity service.
- Client gửi access token đến Orders API qua HTTP Authorization header.
- Orders API xác minh token trước khi tạo principal và kiểm tra quyền.

Kết quả cuối cùng là một contract có thể đưa cho nhóm phát hành token, nhóm triển khai API, nhóm vận hành và nhóm kiểm thử cùng thực hiện. Mỗi bên có cùng cách hiểu về token hợp lệ.

Sau bài tập, bạn cần có thể:

1. Chọn token profile phù hợp cho API.
2. Xác định trust boundary giữa issuer, client và resource server.
3. Chốt issuer, audience, algorithm, key source và token type.
4. Thiết kế required claims, optional claims và custom claims.
5. Định nghĩa thời hạn, clock skew, key rotation và revocation.
6. Viết quy trình verify/validate và authorization độc lập với ngôn ngữ.
7. Xây dựng positive test, negative test và acceptance criteria.
8. Triển khai contract theo cách có thể nâng cấp mà không tạo khoảng thời gian chấp nhận token sai.

## 2. Phân biệt các thành phần trong hợp đồng

Trước khi thiết kế, cần thống nhất vai trò của từng thành phần:

| Thành phần | Vai trò | Trách nhiệm |
| --- | --- | --- |
| Issuer | Bên phát hành token | Xác thực chủ thể, quyết định quyền được cấp, ký token và quản lý khóa |
| Client | Ứng dụng yêu cầu và sử dụng token | Lấy token qua flow được phép, bảo vệ token và gửi token đến đúng API |
| Resource server | API nhận access token | Xác minh token, kiểm tra claims/profile và thực thi authorization |
| Subject | Danh tính mà token đại diện | Được nhận diện bằng định danh ổn định trong phạm vi issuer |
| Audience | Bên nhận token dự kiến | Xác định API hoặc resource server được phép chấp nhận token |
| JWKS endpoint | Nguồn công bố public keys | Cho verifier lấy public key tương ứng với key ID |
| Authorization policy | Quy tắc quyết định quyền | Ánh xạ scope/claim sang hành động và kiểm tra quyền trên tài nguyên |

Trong bài này chỉ có một issuer được tin cậy. Điều đó đơn giản hóa việc chọn trust configuration, nhưng không có nghĩa issuer chỉ dùng một signing key. Một issuer có thể có nhiều key cùng tồn tại trong thời gian rotation.

## 3. Xác định yêu cầu và trust boundary

Viết yêu cầu nghiệp vụ trước khi chọn claim. Giả sử Orders API cung cấp:

| Endpoint | Hành động | Quyền tối thiểu minh họa |
| --- | --- | --- |
| GET /orders | Đọc danh sách đơn hàng của chủ thể | orders:read |
| GET /orders/{id} | Đọc một đơn hàng | orders:read |
| POST /orders | Tạo đơn hàng | orders:write |
| POST /orders/{id}/cancel | Hủy đơn hàng | orders:cancel |

Issuer có thể cấp một hoặc nhiều scope theo client, subject và policy. API vẫn phải kiểm tra chủ thể có quyền truy cập đúng đơn hàng hay không; scope orders:read không tự động cho phép đọc mọi đơn hàng trong hệ thống.

### 3.1. Những điều resource server tin cậy

Orders API chỉ tin:

- Issuer URL được cấu hình trước.
- Public keys lấy từ JWKS endpoint đã gắn với issuer đó.
- Thuật toán nằm trong allowlist do API cấu hình.
- Claims sau khi chữ ký và toàn bộ token profile đã được xác minh.
- Quyền nghiệp vụ được suy ra từ policy phía server.

Orders API không tin:

- Header hoặc payload trước khi verify.
- URL JWKS do token tự khai báo.
- Role hoặc scope chỉ vì chúng xuất hiện trong JSON.
- kid như bằng chứng về issuer.
- Token được ký hợp lệ nhưng có audience của API khác.
- Một ID Token chỉ vì nó cũng là JWT.

### 3.2. Threat model tối thiểu

Hợp đồng phải chống được các tình huống:

- Attacker tự tạo token có sub là administrator.
- Attacker sửa scope hoặc audience trong payload.
- Token của một API khác được gửi đến Orders API.
- Token hết hạn hoặc chưa đến thời điểm hiệu lực.
- Attacker gửi token dùng thuật toán không được phép.
- Token được ký bằng key không thuộc issuer.
- Key bị rotation hoặc compromise.
- Token bị lộ qua URL, log, browser history hoặc trace.
- Client gửi ID Token thay cho access token.

Không có contract nào loại bỏ mọi rủi ro chỉ bằng chữ ký. Cần bảo vệ token khi truyền, lưu trữ, quan sát và sử dụng.

## 4. Chọn token profile

API cần access token để gọi resource server. Không sử dụng ID Token của OpenID Connect làm access token.

Một lựa chọn rõ ràng là JWT Profile for OAuth 2.0 Access Tokens theo RFC 9068. Profile này quy định các claim và header liên quan đến access token JWT, giúp issuer và resource server tránh tự tạo một định dạng tùy biến không có quy tắc thống nhất.

Trong contract minh họa:

- Serialization: JWS Compact Serialization.
- Token purpose: OAuth 2.0 access token.
- JOSE typ: at+jwt theo profile đã chọn.
- Signing algorithm: RS256 trong ví dụ; đây là lựa chọn minh họa, không phải yêu cầu chung cho mọi hệ thống.
- Encryption: không dùng JWE trong contract cơ bản.

Nếu hệ thống cần che giấu payload khỏi bearer token holder, phải thiết kế thêm profile JWE và recipient trust riêng. Chữ ký JWS không mã hóa payload; Base64URL chỉ là encoding.

### 4.1. Phân biệt access token với các loại JWT khác

| Loại token | Mục đích | Orders API có chấp nhận? |
| --- | --- | --- |
| Access token | Truy cập resource server | Có, nếu đúng contract |
| ID Token | Cho OIDC client biết kết quả authentication | Không |
| Client assertion | Xác thực client với authorization server | Không |
| Password reset token | Hoàn tất flow đặt lại mật khẩu | Không |
| Email verification token | Xác minh địa chỉ email | Không |
| DPoP proof JWT | Chứng minh possession và ràng buộc HTTP request | Không thay thế access token; chỉ xử lý nếu API hỗ trợ DPoP riêng |

Việc phân biệt type giúp tránh cross-JWT confusion: một JWT hợp lệ cho một mục đích không được tự động chấp nhận cho mục đích khác.

## 5. Chốt issuer và audience

### 5.1. Issuer

Contract minh họa:

~~~text
Expected issuer:
https://identity.example.com
~~~

Giá trị iss trong token phải khớp chính xác issuer được cấu hình. Không chấp nhận issuer chỉ vì URL có cùng domain suffix, cùng hostname hoặc có vẻ gần giống.

Issuer URL là định danh trong contract. Thay đổi scheme, host, port, path hoặc dấu slash có thể làm thay đổi giá trị định danh. Khi đổi issuer, cần migration có kế hoạch và verifier chỉ chấp nhận giá trị mới sau khi trust configuration được cập nhật rõ ràng.

### 5.2. Audience

Contract minh họa:

~~~text
Expected audience:
https://api.orders.example.com
~~~

aud xác định resource server mà token được phát hành để sử dụng. Trong bài tập, để giảm mơ hồ, contract yêu cầu aud là một chuỗi duy nhất khớp chính xác Orders API.

JWT tiêu chuẩn cho phép aud được biểu diễn bằng một chuỗi hoặc một mảng chuỗi. Nếu hệ thống chọn hỗ trợ mảng, phải quy định rõ rằng Orders API chỉ chấp nhận khi audience của chính API xuất hiện như một phần tử khớp chính xác; không dùng substring hoặc wildcard lỏng lẻo.

Không phát hành một token audience rộng cho nhiều API nếu các API có trust boundary hoặc quyền khác nhau. Nếu client cần gọi nhiều resource server, issuer nên cấp token phù hợp từng audience theo authorization flow.

## 6. Chọn thuật toán và nguồn khóa

### 6.1. Algorithm allowlist

Ví dụ contract sử dụng RS256:

~~~text
Allowed JWS algorithms:
- RS256

Rejected:
- none
- HS256
- Any algorithm not explicitly listed
~~~

RS256 là chữ ký RSA với SHA-256. Verifier phải cấu hình allowlist độc lập với header token. Không để token quyết định thuật toán mà server sẽ thử.

Nếu chọn ES256 hoặc một thuật toán khác, cần cập nhật đồng bộ profile, key type, key size/curve, thư viện và test vectors. Không fallback sang thuật toán khác khi verify thất bại.

### 6.2. Vì sao ví dụ dùng chữ ký bất đối xứng?

Với chữ ký bất đối xứng, issuer giữ private signing key, còn Orders API chỉ cần public verification key. Việc resource server có public key không cho phép nó phát hành token giả.

Với HMAC, mọi verifier giữ shared secret đều có khả năng tạo MAC hợp lệ. Khi nhiều API cùng giữ secret, một API bị xâm nhập có thể làm lộ khả năng giả mạo token cho các API khác. Hãy đánh giá blast radius trước khi chọn thuật toán đối xứng.

### 6.3. Key source và kid

Contract minh họa:

~~~text
Trusted issuer:
https://identity.example.com

JWKS URI:
https://identity.example.com/.well-known/jwks.json

Key selection:
- kid is required by this contract
- kid is unique within this issuer's active key set
- key type and algorithm must match the configured profile
~~~

JWKS URI phải lấy từ trust configuration hoặc metadata của issuer đã được xác minh/pin. Không tải key từ jku, x5u hoặc URL tùy ý do token cung cấp.

kid chỉ là gợi ý chọn key trong key set đã tin cậy. Nó không phải bằng chứng rằng token đến từ issuer. Sau khi verify, API vẫn kiểm tra iss chính xác.

JWKS công khai chỉ chứa public key. Không công bố private parameter, private JWK hoặc shared secret.

## 7. Thiết kế header contract

Header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-2026-01",
  "typ": "at+jwt"
}
~~~

Ý nghĩa:

| Header parameter | Quy tắc |
| --- | --- |
| alg | Bắt buộc và phải là RS256 trong contract minh họa |
| kid | Bắt buộc; chọn key trong JWKS đã tin cậy |
| typ | Bắt buộc; xác định access-token profile |
| crit | Không chấp nhận parameter critical không được hỗ trợ |
| jku/x5u | Không lấy nguồn key từ URL do token cung cấp |
| jwk | Không dùng public key tự mang trong header làm trust anchor cho access token này |

Header chưa xác minh là dữ liệu không đáng tin. Chỉ đọc các trường cần thiết để parse và tra cứu trong cấu hình tin cậy; không dùng header để cấp quyền.

## 8. Thiết kế claims contract

### 8.1. Required claims

Với access token profile theo RFC 9068, contract cần xác định các claim bắt buộc như sau:

| Claim | Kiểu dữ liệu | Ý nghĩa và quy tắc |
| --- | --- | --- |
| iss | String | Phải khớp chính xác issuer đã cấu hình |
| sub | String | Định danh chủ thể ổn định trong phạm vi issuer |
| aud | String theo contract bài tập | Phải khớp chính xác Orders API |
| exp | NumericDate | Thời điểm hết hạn, tính bằng giây từ Unix epoch |
| iat | NumericDate | Thời điểm phát hành |
| jti | String | Định danh token duy nhất trong phạm vi issuer |
| client_id | String | Định danh OAuth client mà issuer đã xác thực |
| scope | String theo contract API | Danh sách scope phân tách bằng dấu cách; API yêu cầu scope phù hợp cho endpoint |

RFC 9068 định nghĩa các claim cần thiết cho JWT access token; contract API có thể đặt thêm điều kiện cụ thể, ví dụ bắt buộc scope cho mọi token được phép gọi Orders API.

### 8.2. Optional claims

Chỉ thêm claim nếu consumer có nhu cầu thực tế:

| Claim | Khi nào cần |
| --- | --- |
| nbf | Token có thời điểm bắt đầu hiệu lực khác thời điểm phát hành |
| tenant_id | API cần xác định tenant và policy cho phép đưa định danh này vào token |
| auth_time | Resource server thực sự cần biết thời điểm user authentication |
| acr/amr | Policy yêu cầu mức độ hoặc phương thức xác thực |
| cnf | Token được ràng buộc với chứng thư hoặc public key theo sender-constrained profile |

Không thêm mọi thông tin sẵn có từ user database vào token. Email, số điện thoại, địa chỉ, ngày sinh, password hash và secret không phải claims mặc định.

### 8.3. Claim tùy biến phải có namespace và contract

Nếu cần custom claim, định nghĩa:

- Tên và namespace tránh xung đột.
- Kiểu dữ liệu.
- Bên phát hành có thẩm quyền.
- Consumer nào được phép đọc.
- Ý nghĩa khi claim thiếu hoặc null.
- Versioning và kế hoạch deprecation.
- Mức độ nhạy cảm và thời gian tồn tại.

Không dùng role hoặc permission tùy biến làm nguồn quyết định duy nhất nếu API cần kiểm tra quyền trên tài nguyên hiện tại. Token có thể còn hạn sau khi trạng thái nghiệp vụ thay đổi.

## 9. Ví dụ access token theo contract

Protected header:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-2026-01",
  "typ": "at+jwt"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-12345",
  "aud": "https://api.orders.example.com",
  "exp": 1893456600,
  "iat": 1893456000,
  "jti": "6b9f5c6a-9f9b-4c83-a72c-4b1c73f1a821",
  "client_id": "web-storefront",
  "scope": "orders:read orders:write"
}
~~~

Các timestamp và định danh trong ví dụ chỉ phục vụ minh họa. Token thực tế phải được issuer tạo theo clock và policy hiện hành.

Lưu ý:

- Payload JWS có thể đọc được bởi người sở hữu token; chữ ký không mã hóa claims.
- sub là định danh subject, không nhất thiết là email hoặc username hiển thị.
- client_id xác định client được issuer xác thực; nó không thay thế subject.
- aud ràng buộc token với Orders API.
- scope thể hiện phạm vi được cấp, nhưng API vẫn kiểm tra quyền trên từng resource.
- jti là định danh token; chỉ có jti không tự tạo ra replay prevention hoặc revocation.

## 10. Chốt thời hạn và clock skew

Ví dụ contract:

~~~text
Maximum access-token lifetime: 10 minutes
Allowed clock skew: 60 seconds
exp: required
iat: required
nbf: optional
Maximum accepted token age: 10 minutes + configured skew
~~~

Các giá trị trên là cấu hình mẫu cho bài tập, không phải quy tắc phù hợp với mọi hệ thống. Khi áp dụng thực tế, cần đánh giá rủi ro, tải refresh và khả năng đồng bộ thời gian.

### 10.1. Quy tắc thời gian

- exp phải lớn hơn thời gian hiện tại theo clock policy.
- nbf, nếu có, không được nằm trong tương lai ngoài clock skew cho phép.
- iat không được nằm trong tương lai ngoài mức sai lệch đã định.
- Token quá cũ so với maximum token age phải bị từ chối nếu contract đặt giới hạn đó.
- Clock skew phải có giới hạn; không tăng vô hạn để xử lý lỗi đồng hồ.

### 10.2. Đồng bộ thời gian

Issuer và resource server cần đồng bộ đồng hồ bằng hạ tầng thời gian đáng tin cậy. Theo dõi clock drift và cảnh báo khi sai lệch vượt ngưỡng.

Không kéo dài exp hoặc tăng clock skew chỉ để che lỗi đồng bộ thời gian. Điều đó mở rộng cửa sổ sử dụng token bị lộ.

## 11. Quy trình phát hành token tại issuer

Issuer phải:

1. Xác thực user hoặc client bằng flow phù hợp.
2. Xác định subject và client_id.
3. Kiểm tra client có được yêu cầu audience Orders API không.
4. Tính toán scope được phép theo subject, client và policy.
5. Tạo claims theo schema/profile đã công bố.
6. Đặt exp, iat và jti.
7. Chọn signing key đang hoạt động theo key-management policy.
8. Tạo JWS theo thuật toán đã cấu hình.
9. Trả access token theo giao thức OAuth được sử dụng.
10. Không đưa refresh token hoặc credential gốc vào payload access token.

Issuer không nên nhận một object claims tùy ý từ client rồi ký nguyên trạng. Claims phải được xây dựng từ dữ liệu có thẩm quyền và policy phía issuer.

## 12. Quy trình xác minh tại Orders API

Resource server phải xác minh token theo một thứ tự có kiểm soát:

1. Lấy bearer token từ Authorization header.
2. Giới hạn kích thước và parse JWS Compact Serialization.
3. Đọc header chưa xác minh để lấy alg/kid/typ theo contract.
4. Từ chối alg không nằm trong allowlist hoặc typ không đúng profile.
5. Chọn public key từ JWKS cache gắn với issuer đã cấu hình.
6. Verify chữ ký trên đúng JWS Signing Input.
7. Kiểm tra iss và aud.
8. Kiểm tra exp, iat, nbf và maximum token age.
9. Kiểm tra required claims, kiểu dữ liệu và token profile.
10. Chỉ sau khi toàn bộ bước xác minh thành công mới tạo authenticated principal.
11. Áp dụng authorization cho endpoint và resource cụ thể.

Nếu bất kỳ bước bắt buộc nào thất bại, từ chối request. Không fallback sang decode-only hoặc dùng claims đã đọc trước verify.

### 12.1. Pseudocode độc lập ngôn ngữ

~~~text
function authenticateOrdersRequest(request):
    rawToken = extractBearerToken(request.authorizationHeader)
    require rawToken exists
    enforceMaximumTokenSize(rawToken)

    parsed = parseCompactJws(rawToken)
    header = parsed.untrustedHeader

    require header.alg == "RS256"
    require header.typ == "at+jwt"
    require header.kid exists

    key = trustedIssuerKeySet.find(header.kid)
    if key is missing:
        refreshTrustedIssuerJwksOnceWithSingleFlightAndRateLimit()
        key = trustedIssuerKeySet.find(header.kid)
    require key exists
    require key.type == "RSA"
    require key.modulusBits >= 2048
    if key.use is present:
        require key.use == "sig"
    if key.key_ops is present:
        require key.key_ops contains "verify"
    if key.alg is present:
        require key.alg == "RS256"

    verified = verifyJws(
        rawToken,
        key,
        allowedAlgorithms = ["RS256"]
    )
    require verified

    claims = verified.claims
    require claims.iss == "https://identity.example.com"
    require claims.aud == "https://api.orders.example.com"
    require claims.sub is a non-empty string
    require claims.client_id is a non-empty string
    require claims.jti is a non-empty string
    require claims.iat and claims.exp are valid NumericDate values
    now = trustedClock.currentUnixTime()
    require claims.exp > claims.iat
    require now < claims.exp + allowedClockSkew
    require claims.iat <= now + allowedClockSkew
    require claims.exp - claims.iat <= maximumTokenLifetime
    require now - claims.iat <= maximumTokenAge + allowedClockSkew
    if claims.nbf is present:
        require claims.nbf is a valid NumericDate value
        require now + allowedClockSkew >= claims.nbf
    require claims.scope is a valid space-delimited scope string

    return TrustedPrincipal.fromVerifiedClaims(claims)
~~~

Đây là pseudocode mô tả hợp đồng, không phải API của một thư viện cụ thể. Việc tra cứu key có thể diễn ra trước khi verify, nhưng chỉ trong key set đã tin cậy của issuer cố định. Header và claims chưa xác minh không được dùng để cấp quyền.

### 12.2. Kiểm tra authorization cho endpoint

~~~text
function authorize(request, principal):
    requiredScope = policy.requiredScopeFor(
        request.method,
        request.route
    )

    require principal.scopes contains requiredScope

    resource = loadResourceFromTrustedRouteContext(request)
    require policy.subjectCanAccess(
        principal.subject,
        resource
    )

    allow
~~~

Scope kiểm tra quyền ở mức hành động/API. Kiểm tra subject có thể truy cập resource cụ thể là bước riêng. Không tin resource ID hoặc tenant ID chỉ vì client đưa vào request.

## 13. Quy tắc authorization

Contract cần quy định cách scope ánh xạ sang endpoint:

| Scope | Hành động |
| --- | --- |
| orders:read | Đọc đơn hàng |
| orders:write | Tạo hoặc cập nhật đơn hàng theo policy |
| orders:cancel | Hủy đơn hàng theo policy |

Các nguyên tắc:

- Scope thiếu hoặc không hợp lệ dẫn đến từ chối hành động cần scope đó.
- Scope không tự cấp quyền truy cập mọi bản ghi.
- Không dùng role do client gửi trong request.
- Không cho phép scope rộng hơn quyền issuer đã cấp cho client/subject.
- Quyền nhạy cảm có thể cần re-authorization hoặc kiểm tra policy hiện tại.
- Nếu token được cấp cho nhiều scope, API chỉ dùng scope cần thiết cho request hiện tại.

Không biến scope thành một biểu diễn quyền không có versioning. Khi đổi tên hoặc ý nghĩa scope, cần migration và cập nhật đồng bộ issuer, API và consumer.

## 14. Key rotation và JWKS lifecycle

Một issuer duy nhất vẫn có thể rotation nhiều signing key. Hợp đồng phải định nghĩa vòng đời key:

### 14.1. Rotation có kế hoạch

1. Tạo key pair mới trong KMS/HSM hoặc key store được bảo vệ.
2. Công bố public key mới trong JWKS với kid mới.
3. Chờ verifier có cơ hội tải key mới theo cache/refresh policy.
4. Chuyển issuer sang ký token bằng key mới.
5. Giữ public key cũ trong JWKS đủ lâu để xác minh token cũ còn hạn.
6. Sau khi token cũ hết hạn và thời gian clock skew/overlap kết thúc, loại key cũ khỏi JWKS.

Không tái sử dụng kid cho key material khác trong cùng issuer nếu điều đó gây nhầm lẫn cache. Không xóa public key cũ ngay khi bắt đầu ký bằng key mới nếu vẫn còn token cũ hợp lệ.

### 14.2. Emergency key compromise

Nếu private signing key bị lộ:

- Ngừng dùng key bị ảnh hưởng để ký.
- Đánh dấu key/kid bị compromise trong trust policy khẩn cấp.
- Phân phối invalidation đến verifier.
- Bảo đảm emergency denylist được kiểm tra kể cả khi key vẫn còn trong cache.
- Đánh giá và thu hồi token đã ký bằng key bị compromise theo incident policy.
- Theo dõi thời gian từ khi phát lệnh đến khi mọi verifier từ chối key.

JWKS TTL không phải cơ chế duy nhất cho emergency revocation. Một verifier dùng stale key không được bỏ qua thông tin thu hồi khẩn cấp.

## 15. Revocation và trạng thái token

JWS hợp lệ chứng minh token được ký bằng key tương ứng và chưa bị sửa. Nó không tự cho biết session hoặc quyền đã bị thu hồi sau khi token được phát hành.

Contract cần chọn mô hình:

| Mô hình | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Access token ngắn hạn, verify cục bộ | Ít dependency, latency thấp | Token đã phát hành còn dùng được đến exp nếu không có kiểm tra trạng thái |
| Denylist theo jti | Có thể chặn token cụ thể | Cần state lookup và retention đúng thời hạn |
| Introspection | Có trạng thái tập trung | Thêm network dependency và tải authorization server |
| Session/version check | Có thể thu hồi theo session hoặc subject | Cần định nghĩa version/state và cache freshness |

Ví dụ contract cơ bản dùng access token ngắn hạn và xác minh cục bộ. Nếu nghiệp vụ cần thu hồi tức thời, bổ sung introspection hoặc denylist với SLA freshness rõ ràng.

jti chỉ là định danh. Nó không tự tạo denylist, không tự làm token one-time-use và không tự bảo đảm revocation.

## 16. Truyền token và bảo vệ dữ liệu

Contract quy định:

- Chỉ truyền bearer token qua TLS.
- Gửi token trong Authorization header theo Bearer scheme.
- Không truyền access token trong URL query string.
- Không ghi raw token hoặc Authorization header vào log.
- Redact token trong tracing, APM, error report và support ticket.
- Giới hạn quyền truy cập cache, queue và nơi lưu token.
- Không gửi token qua email/chat hoặc tài liệu vận hành.
- Client chỉ lưu token theo threat model của nền tảng.

Access token là bearer credential: bên sở hữu token có thể sử dụng nó trong phạm vi được cấp. Vì vậy, giới hạn audience, scope và lifetime là một phần của contract.

Không đưa password, client secret, API key, private signing key, HMAC secret, OTP seed hoặc refresh token vào access token. JWS không mã hóa payload; JWE cũng không biến token thành secret manager.

## 17. Xử lý lỗi và HTTP semantics

Resource server cần phân biệt lỗi xác thực và lỗi authorization:

| Tình huống | HTTP response tham chiếu | Ý nghĩa |
| --- | --- | --- |
| Không có bearer token ở endpoint cần xác thực | 401 Unauthorized | Chưa có credential hợp lệ |
| Token sai chữ ký, issuer, audience hoặc hết hạn | 401 Unauthorized | Bearer token không hợp lệ |
| Authorization request sai định dạng, ví dụ gửi nhiều phương thức truyền token | 400 Bad Request với invalid_request | Request credential không hợp lệ |
| Token sai hoặc không còn hiệu lực | 401 Unauthorized với invalid_token | Bearer token không hợp lệ |
| Token hợp lệ nhưng thiếu scope | 403 Forbidden với insufficient_scope | Đã xác thực nhưng không đủ quyền |
| Token hợp lệ nhưng subject không có quyền trên resource | 403 hoặc response theo policy resource | Authorization thất bại |

Theo RFC 6750, resource server có thể sử dụng WWW-Authenticate với Bearer error phù hợp, ví dụ invalid_token hoặc insufficient_scope. Không trả chi tiết nội bộ như key material, stack trace hoặc lý do chọn khóa cho client.

Không biến lỗi JWKS/introspection thành authenticated success. Khi dependency cần thiết không khả dụng, hành vi phải theo fail-closed hoặc stale policy được định nghĩa rõ.

## 18. Contract mẫu có thể bàn giao

Đây là một bản contract minh họa hoàn chỉnh để nhóm phát hành và nhóm API rà soát:

~~~yaml
contract:
  name: orders-api-access-token-v1
  purpose: OAuth 2.0 access token for Orders API
  serialization: JWS Compact
  issuer: https://identity.example.com
  audience: https://api.orders.example.com
  token_type: at+jwt

signing:
  allowed_algorithms:
    - RS256
  key_source: https://identity.example.com/.well-known/jwks.json
  key_selection: kid
  key_type: RSA
  minimum_rsa_modulus_bits: 2048
  reject_unlisted_algorithms: true
  reject_none: true

required_claims:
  - iss
  - sub
  - aud
  - exp
  - iat
  - jti
  - client_id
  - scope

claims:
  audience_format: single-string
  subject_format: stable-opaque-identifier
  scope_format: space-delimited-string
  jti_uniqueness: per-issuer
  custom_claims: deny-by-default

time:
  maximum_lifetime_seconds: 600
  maximum_token_age_seconds: 600
  allowed_clock_skew_seconds: 60
  require_exp: true
  require_iat: true
  nbf: optional

transport:
  scheme: Bearer
  location: Authorization-header
  require_tls: true
  forbid_query_parameter: true

validation:
  exact_issuer_match: true
  exact_audience_match: true
  verify_signature_before_trusting_claims: true
  validate_token_type: true
  fail_closed_on_invalid_signature: true
  fail_closed_on_unknown_key: true

authorization:
  scopes:
    - orders:read
    - orders:write
    - orders:cancel
  resource_level_check: required

revocation:
  baseline: short-lived-local-validation
  immediate_revocation: requires-separate-state-mechanism

operations:
  jwks_cache: enabled-with-bounded-ttl
  unknown_kid_refresh: single-flight-and-rate-limited
  emergency_key_denylist: required
  raw_token_logging: forbidden
~~~

Các giá trị lifetime, skew, thuật toán, audience và JWKS URI trong contract mẫu phải được thay bằng giá trị đã thống nhất của hệ thống thực. Không triển khai trực tiếp URL hoặc key minh họa trong môi trường production.

## 19. Kiểm thử contract

Contract chỉ hữu ích nếu có thể kiểm tra tự động. Tạo test token bằng key test riêng và xác minh bằng đúng cấu hình verifier gần production.

### 19.1. Positive tests

| Test | Kỳ vọng |
| --- | --- |
| Chữ ký đúng, issuer đúng, audience đúng, token còn hạn | Chấp nhận |
| kid thuộc JWKS của issuer và key phù hợp RS256 | Chấp nhận |
| Token có đủ required claims đúng kiểu | Chấp nhận |
| Token có scope orders:read gọi GET /orders | Được qua scope check |
| Token có scope orders:write gọi POST /orders | Được qua scope check nếu resource policy cho phép |
| JWKS cache chứa public key hợp lệ | Verify thành công không cần fetch mỗi request |

### 19.2. Negative tests

| Test | Kỳ vọng |
| --- | --- |
| Payload bị sửa nhưng giữ chữ ký cũ | Từ chối |
| Token tự tạo với sub=admin | Từ chối chữ ký |
| alg=none | Từ chối |
| alg không nằm trong allowlist | Từ chối |
| Key không thuộc issuer | Từ chối |
| kid không tồn tại sau refresh có giới hạn | Từ chối |
| iss sai dù chữ ký hợp lệ | Từ chối |
| aud của API khác | Từ chối |
| exp đã qua | Từ chối |
| nbf ở tương lai ngoài skew | Từ chối |
| iat ở tương lai ngoài skew | Từ chối |
| Token thiếu sub/client_id/jti hoặc claim bắt buộc | Từ chối |
| typ không đúng access-token profile | Từ chối |
| ID Token gửi đến Orders API | Từ chối |
| Scope thiếu cho endpoint | 403 |
| Token hợp lệ nhưng subject không sở hữu resource | Từ chối theo resource policy |
| JWKS outage không có key cache hợp lệ | Không fallback sang decode-only |
| Token nằm trong query string | Không chấp nhận theo transport contract |

### 19.3. Key rotation tests

- Public key mới xuất hiện trong JWKS trước khi issuer dùng key mới.
- Token ký bằng key mới được chấp nhận sau khi verifier refresh key set.
- Token cũ còn hạn vẫn verify được trong overlap policy.
- Key cũ bị loại sau khi token cũ hết hạn và hết clock skew.
- Unknown kid không tạo refresh storm.
- Emergency denylist chặn key bị compromise kể cả khi key còn trong cache.

### 19.4. Contract compatibility tests

Issuer và API nên dùng chung bộ test vector hoặc contract test:

- Issuer tạo token theo đúng header và claim schema.
- API xác minh token do issuer tạo.
- API từ chối token vi phạm từng điều kiện.
- Thay đổi claim hoặc scope được phát hiện như thay đổi contract.
- Thay đổi issuer, audience, algorithm hoặc token type yêu cầu versioning/review.

## 20. Versioning và thay đổi contract

Không phải mọi thay đổi claim đều tương thích ngược. Trước khi đổi contract, phân loại:

| Thay đổi | Rủi ro tương thích | Cách xử lý |
| --- | --- | --- |
| Thêm optional claim không consumer nào phụ thuộc | Thường thấp | Kiểm tra parser có chấp nhận claim không biết |
| Thêm required claim | Cao | Verifier cũ có thể từ chối token |
| Đổi kiểu claim | Cao | Version schema/profile hoặc rollout có kiểm soát |
| Đổi issuer | Rất cao | Cập nhật trust configuration và migration plan |
| Đổi audience | Cao | Cấp token đúng resource và cập nhật verifier |
| Đổi algorithm/curve | Cao | Cập nhật key, library, allowlist và test trước rollout |
| Đổi nghĩa scope | Cao | Tạo scope mới hoặc migration rõ ràng |
| Đổi token type | Cao | Tách profile và verifier |

Nếu cần hỗ trợ v1 và v2 cùng lúc, verifier phải có quy tắc rõ ràng cho từng profile. Không nới lỏng validation để mọi token cũ/mới đều được chấp nhận vô điều kiện.

## 21. Quy trình triển khai và vận hành

Một rollout an toàn có thể thực hiện theo thứ tự:

1. Hai nhóm thống nhất contract và ghi rõ owner cho issuer, JWKS, verifier, authorization policy.
2. Cấu hình issuer, audience, algorithm và required claims trong môi trường test.
3. Phát hành public key test và tạo token test.
4. Tích hợp verifier và chạy toàn bộ positive/negative tests.
5. Kiểm thử key rotation, JWKS cache, unknown kid và outage.
6. Triển khai verifier hỗ trợ contract trước khi issuer phát hành token production.
7. Bắt đầu phát hành token theo profile đã chốt.
8. Theo dõi lỗi verify theo issuer, kid, alg, audience và reason code.
9. Thu hồi đường xử lý cũ sau khi hết migration window.

Runbook cần nêu:

- Ai có quyền tạo, kích hoạt và thu hồi signing key.
- Ai quản lý JWKS và metadata.
- Cách phát hiện key compromise.
- Cách phân phối emergency denylist.
- TTL cache và cách refresh thủ công có kiểm soát.
- Hành vi khi issuer/JWKS/introspection không khả dụng.
- Cách điều tra token invalid mà không ghi raw token.
- Quy trình rollback contract và tiêu chí dừng rollout.

## 22. Checklist hoàn thành bài thực hành

Trước khi coi contract hoàn tất, hãy kiểm tra:

- [ ] Có đúng một issuer được cấu hình tin cậy.
- [ ] Issuer và audience là giá trị chính xác, không dùng wildcard.
- [ ] Token được xác định rõ là access token.
- [ ] Header typ, alg và kid có quy tắc rõ.
- [ ] Algorithm allowlist độc lập với token header.
- [ ] Key source là JWKS/configuration đã tin cậy.
- [ ] Required claims và kiểu dữ liệu được định nghĩa.
- [ ] Scope được ánh xạ đến hành động cụ thể.
- [ ] Có kiểm tra authorization trên từng resource.
- [ ] exp, iat, nbf và clock skew có quy tắc.
- [ ] Key rotation và emergency revocation có quy trình.
- [ ] Mô hình revocation token được công bố.
- [ ] Token chỉ truyền qua TLS trong Authorization header.
- [ ] Raw token bị loại khỏi log và trace.
- [ ] Có positive, negative, rotation và outage tests.
- [ ] Có versioning, rollout và rollback plan.
- [ ] Không có nội dung phụ thuộc vào một framework/ngôn ngữ cụ thể.

## 23. Tình huống tự kiểm tra

Identity service phát hành một JWT có chữ ký RS256 hợp lệ, issuer đúng và còn hạn. Token có audience là https://api.billing.example.com, nhưng client gửi token đó đến Orders API. Payload có scope orders:read.

**Câu hỏi 1:** Orders API có được chấp nhận token không?

**Trả lời:** Không. Audience không khớp Orders API. Scope có vẻ phù hợp không thể bù cho audience sai.

**Câu hỏi 2:** Nếu đổi audience thành Orders API trong payload mà không ký lại thì sao?

**Trả lời:** Chữ ký sẽ không còn hợp lệ vì audience nằm trong payload được ký. Verifier phải từ chối.

**Câu hỏi 3:** Nếu chữ ký hợp lệ và audience đúng nhưng token thiếu scope orders:read thì sao?

**Trả lời:** Token có thể vượt qua authentication nếu profile cho phép scope thiếu ở mức token, nhưng request GET /orders phải bị từ chối authorization. Contract mẫu yêu cầu scope claim hợp lệ và endpoint cần scope tương ứng.

**Câu hỏi 4:** Nếu public key cũ bị xâm phạm nhưng vẫn còn trong JWKS cache thì sao?

**Trả lời:** Emergency denylist hoặc trust invalidation phải chặn key đó kể cả khi cache còn giữ public key. Không chỉ dựa vào TTL để xử lý compromise.

**Câu hỏi 5:** Một issuer duy nhất có thể có hai kid trong JWKS không?

**Trả lời:** Có. Khi rotation, key cũ và mới có thể cùng được công bố trong overlap. Issuer vẫn là một; kid chọn key cụ thể trong key set của issuer.

## 24. Ghi nhớ

Hợp đồng JWT là thỏa thuận kỹ thuật giữa issuer, client và resource server. Nó phải quy định token profile, issuer, audience, algorithm, key source, header, claims, thời hạn, authorization, revocation, transport, lỗi và quy trình vận hành.

Với một issuer và một API, verifier có thể dùng trust configuration cố định, key set của issuer và audience riêng cho API. Chữ ký hợp lệ mới chỉ là một bước: API còn phải kiểm tra token type, issuer, audience, thời gian, required claims và quyền trên endpoint/resource.

Key rotation vẫn cần hỗ trợ nhiều key trong một issuer; revocation cần mô hình riêng; token phải được bảo vệ như bearer credential. Mọi thay đổi có thể ảnh hưởng producer/consumer đều cần versioning, contract tests và rollout có kiểm soát.

**Một JWT chỉ được chấp nhận khi nó đáp ứng toàn bộ contract mà resource server đã cấu hình tin cậy, không chỉ vì nó có cấu trúc đúng hoặc chữ ký hợp lệ.**

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và registered claims.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS Compact Serialization và signing input.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE và key requirements.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền bearer token và HTTP error semantics.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata endpoint và thông tin issuer.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành an toàn khi phát hành và xác minh JWT.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token JWT.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0 hiện hành.
