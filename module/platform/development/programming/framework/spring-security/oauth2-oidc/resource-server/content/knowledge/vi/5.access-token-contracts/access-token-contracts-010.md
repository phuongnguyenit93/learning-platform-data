# Thiết kế kiểm tra phân biệt access token với token có mục đích khác

## 1. Vì sao Resource Server phải phân biệt **loại token**, ngay cả khi chữ ký đúng?

Trong OAuth 2.0 và OpenID Connect (OIDC), Authorization Server/OpenID Provider có thể phát hành nhiều loại token hoặc hiện vật giao thức (*protocol artifacts*) cho các bên nhận khác nhau. Chúng có thể cùng dùng định dạng JWT, cùng thuật toán ký, cùng khóa công khai và cùng issuer. Tuy nhiên, một token được ký hợp lệ **không tự động là access token được phép gọi API**.

Ví dụ một nhà cung cấp danh tính có thể phát hành:

- **Access token** cho Resource Server `orders-api`: trình bày trong `Authorization: Bearer ...` hoặc scheme thích hợp để gọi API, với quyền `orders.read`.
- **ID token** cho OIDC Client `web-client`: giúp client xác nhận kết quả đăng nhập của người dùng.
- **Refresh token** cho OAuth Client: gửi trở lại *token endpoint* của Authorization Server để xin token mới.
- **Logout token** cho Relying Party: thông báo sự kiện đăng xuất theo cơ chế OIDC Back-Channel Logout.
- **Client assertion JWT** dùng để xác thực client với Authorization Server, hoặc một loại JWT assertion dùng trong grant khác.
- **Authorization code**, **DPoP proof JWT** hay token trao đổi qua Token Exchange, mỗi loại phục vụ một công đoạn khác.

**Hợp đồng access token** (*access-token acceptance contract*) là tập quy tắc rõ ràng mà Resource Server áp dụng để trả lời:

> “Credential này có thực sự là access token **được phát hành cho API của tôi**, trong ngữ cảnh này, với quyền cần thiết hay không?”

Điểm quan trọng là API không được trả lời bằng cách kiểm tra duy nhất rằng “JWT decode được” hay “signature đúng”. Nếu xác thực JWT nhưng bỏ qua đối tượng nhận hoặc token profile, hệ thống có thể mắc lỗi **cross-JWT confusion / token substitution**: lấy token có mục đích A để thực hiện hành động được dành riêng cho token mục đích B.

## 2. Phân biệt các loại token theo **người nhận và mục đích**

| Loại token / hiện vật | Được phát cho và dùng bởi | Mục đích | Có dùng làm Bearer access token để gọi API nghiệp vụ? |
|---|---|---|---|
| **OAuth 2.0 access token** | Client giữ, Resource Server kiểm tra khi client gọi tài nguyên | Cấp quyền truy cập một hoặc nhiều tài nguyên theo phạm vi được cấp | **Có**, nếu token dành cho API đó và đáp ứng hợp đồng |
| **OIDC ID token** | OIDC Client / Relying Party | Khẳng định việc xác thực chủ thể; client kiểm tra `aud=client_id` và các điều kiện OIDC | **Không** |
| **Refresh token** | Client giữ; Authorization Server nhận ở token endpoint | Xin access token mới khi grant còn hợp lệ | **Không** |
| **Authorization code** | Client đổi tại token endpoint, thường kèm PKCE | Hoàn thành authorization-code grant | **Không** |
| **OIDC logout token** | Relying Party nhận theo giao thức logout | Thông báo sự kiện đăng xuất | **Không** |
| **JWT client assertion** | Authorization Server/token endpoint | Xác thực client hoặc thực hiện assertion grant theo cấu hình | **Không** |
| **DPoP proof JWT** | Authorization Server hoặc Resource Server kiểm tra theo giao thức DPoP | Chứng minh bên gửi đang sở hữu khóa ràng buộc với request/token | **Không**; proof được kiểm tra cùng access token, không thay access token |
| **Opaque token** | Phụ thuộc hợp đồng issuer; có thể là access token hoặc loại khác | Không thể suy ra mục đích từ bề ngoài | Chỉ khi introspection/hợp đồng chứng minh nó là access token dành cho API |

Một điểm dễ nhầm: `token_type: "Bearer"` trong phản hồi OAuth 2.0 cho biết **cách trình bày access token theo Bearer scheme**, không phải lời khẳng định mọi JWT mang giá trị “Bearer” đều có ngữ nghĩa access token. Tương tự, tham số OAuth Token Exchange `requested_token_type` hoặc `subject_token_type` có các giá trị định danh loại token theo giao thức; chúng khác với JOSE header `typ`.

### Ai là “audience” trong từng trường hợp?

- Access token cho `orders-api` cần có audience phù hợp với **Resource Server** nếu token dạng JWT dùng `aud`, hoặc thông tin ràng buộc tài nguyên tương đương trong hợp đồng opaque/introspection.
- ID token OIDC thường có `aud` chứa **client ID của Relying Party**.
- Client assertion JWT thường có `aud` là **Authorization Server/token endpoint**, theo profile áp dụng.
- Logout token có audience của **Relying Party** và cấu trúc sự kiện logout đặc thù.

Vì vậy, một `aud` hợp lệ với **bên nhận này** không có nghĩa hợp lệ với **bên nhận khác**. `sub` cho biết chủ thể được mô tả, **không phải** endpoint được phép nhận token.

## 3. Ranh giới bảo mật: tính hợp lệ mật mã khác tính hợp lệ nghiệp vụ

Có ba tầng kiểm tra cần tách riêng:

1. **Xác thực về mật mã và nguồn gốc**: JWS có chữ ký đúng bằng khóa tin cậy, issuer đúng, thuật toán được cho phép, token còn hiệu lực; với opaque token là xác nhận hợp lệ qua introspection hoặc cơ chế tương đương.
2. **Xác thực mục đích và đối tượng nhận**: token này thuộc loại access token mà API hỗ trợ; audience/resource, client binding, các claim và JOSE type theo profile phải đúng.
3. **Phân quyền**: request muốn đọc/sửa tài nguyên cụ thể có đúng scope, authority, tenant, quyền sở hữu đối tượng và điều kiện nghiệp vụ không?

Các kết quả có thể khác nhau:

| Tình huống | Chữ ký/hiệu lực | Hợp đồng access token của API | Quyền tài nguyên | Kết luận |
|---|---|---|---|---|
| JWT access token hợp lệ cho `orders-api`, `orders.read` | Đạt | Đạt | Đạt | Cho phép đọc trong phạm vi tài nguyên được phép |
| OIDC ID token được ký đúng, `aud=web-client` | Đạt | **Không đạt** | Không xét | Từ chối xác thực token của request API |
| JWT access token cho `billing-api` | Đạt | **Không đạt audience** | Không xét | Từ chối |
| Access token bị sửa payload | **Không đạt chữ ký** | Không xét | Không xét | Từ chối |
| Access token đúng API nhưng thiếu `orders.write` | Đạt | Đạt | **Không đạt** | Thường trả 403 |
| Access token đúng scope nhưng khác tenant | Đạt | Đạt | **Không đạt quyền trên đối tượng** | Từ chối truy cập dữ liệu |

Nếu framework chỉ tạo `Authentication` sau khi kiểm tra chữ ký nhưng không kiểm tra audience hay mục đích, ứng dụng có thể đang **xác thực một token đúng kỹ thuật nhưng sai giao thức**.

## 4. Định nghĩa hợp đồng chấp nhận access token

Trước khi viết `JwtDecoder` hay `OpaqueTokenIntrospector`, hãy mô tả rõ profile mà API chấp nhận. Một thiết kế khởi đầu cho `orders-api` có thể ghi:

| Thuộc tính hợp đồng | Ví dụ chính sách | Lý do |
|---|---|---|
| **Token transport** | `Authorization: Bearer <access-token>` qua HTTPS | Không để client đưa tùy ý ID/refresh token hoặc token ở nhiều nơi |
| **Định dạng** | Signed JWT access token theo RFC 9068, hoặc opaque token đã được issuer xác nhận | Chọn đúng bộ xác thực; format không đồng nghĩa purpose |
| **Issuer** | `https://id.example.com/realms/demo` | Xác định miền tin cậy và nguồn JWKS/introspection |
| **JWS algorithms** | `RS256` | Không để `alg` do token tự đề xuất mở rộng thuật toán tin cậy |
| **Key source** | JWKS endpoint gắn với issuer đã tin | Không tải khóa từ `jku`/URL tùy ý trong token |
| **JOSE `typ`** | Với RFC 9068: `at+jwt` hoặc `application/at+jwt` | Phân biệt token theo profile access token |
| **Audience/resource** | `aud` chứa `orders-api` | Ngăn token được phát cho API/client khác |
| **Claim bắt buộc** | Theo profile: `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, `client_id` với RFC 9068 | Chỉ chấp nhận token đáp ứng hợp đồng đã thống nhất |
| **Subject/client** | Cho phép user token và/hoặc service token theo endpoint | Tránh giả định mọi access token luôn là token của user |
| **Scope/authority** | `orders.read`, `orders.write` theo thao tác | Kiểm soát hành động |
| **Object-level checks** | Order thuộc tenant/account phù hợp | Ngăn vượt quyền khi scope là quyền rộng cấp API |
| **Lifetime và clock skew** | Giới hạn theo chính sách hệ thống | Không chấp nhận token hết hạn hoặc thời hạn bất thường |
| **Revocation/sender binding** | Chính sách riêng nếu cần; DPoP/mTLS khi được phát hành dưới ràng buộc | Không nhầm token còn hạn với token luôn được phép dùng |

Bảng là **thiết kế chính sách**, không phải file cấu hình Spring Boot có thể sao chép nguyên vào `application.yml`. Một ứng dụng có thể hỗ trợ nhiều issuer hoặc nhiều loại token, nhưng mỗi trường hợp cần có **bộ quy tắc chấp nhận được định nghĩa tường minh**.

### Ví dụ tài liệu hóa hai hợp đồng khác nhau

```yaml
# PSEUDO-CONFIG: chỉ mô tả hợp đồng, không phải cấu hình Spring Boot.
ordersApi:
  acceptedFormat: signed-jwt
  issuer: https://id.example.com/realms/demo
  allowedJwsAlgorithms: [RS256]
  requiredJoseTyp: [at+jwt, application/at+jwt]
  requiredAudience: orders-api
  acceptedScopes: [orders.read, orders.write]

legacyPartnerApi:
  acceptedFormat: opaque
  trustedIntrospectionServer: https://partners.example.com/oauth2/introspect
  requiredResource: partner-orders-api
  acceptedScopes: [partner.orders.read]
```

Không nên viết một bộ xử lý chung “cứ có JWT hợp lệ thì cho qua cả hai API” vì các API có audience và profile khác nhau.

## 5. Những dấu hiệu nào thực sự giúp phân biệt access token?

### 5.1. `iss`: xác thực bên phát hành

`iss` phải khớp issuer **đã được cấu hình tin cậy**. Nếu cùng hệ thống có nhiều issuer, có thể dùng chuỗi issuer chưa xác minh để *chọn tạm* một cấu hình thuộc allow-list, nhưng tuyệt đối không lấy URL issuer từ token rồi tự tải metadata/JWKS và tin nguồn đó.

Ngay cả khi `iss` đúng, issuer có thể đã phát hành ID token, logout token và access token bằng cùng khóa. **Issuer đúng chưa đủ.**

### 5.2. `aud`: đối tượng mà token được phát hành để phục vụ

`aud` là một trong những ranh giới quan trọng nhất:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1910000000
}
```

Resource Server `orders-api` cần kiểm tra `aud` có **mã resource được kỳ vọng**. Nếu token có `aud=web-client` hoặc `aud=billing-api`, API phải từ chối theo hợp đồng của mình.

Không thay audience bằng các dấu hiệu như `sub` tồn tại, `email` tồn tại hay scope có vẻ liên quan. Token có thể chứa nhiều audience; trường hợp nhiều audience phải được chấp nhận **chỉ khi hợp đồng của issuer và API cho phép**.

### 5.3. `typ`: loại token trong JOSE protected header

Với **JWT Profile for OAuth 2.0 Access Tokens (RFC 9068)**, JOSE header của JWT access token phải dùng `typ` phù hợp:

```json
{
  "alg": "RS256",
  "kid": "signing-key-2026",
  "typ": "at+jwt"
}
```

Hoặc:

```json
{
  "typ": "application/at+jwt",
  "alg": "RS256",
  "kid": "signing-key-2026"
}
```

Các ví dụ trên chỉ mô tả **header JSON**, không phải token đã ký.

`typ` hỗ trợ chống nhầm token trong ngữ cảnh RFC 9068. Nhưng nó không tự đủ để cho phép truy cập: một JWT có `typ=at+jwt` vẫn có thể sai chữ ký, issuer, audience, thời hạn hoặc scope.

Ngược lại, **không phải mọi JWT access token trên thị trường đều theo RFC 9068**. Một nhà cung cấp có thể phát hành access token với `typ=JWT` hoặc không đặt `typ`. Khi đó API phải theo profile thực tế đã thống nhất với issuer và sử dụng các phân biệt bổ sung. Không gán máy móc “thiếu `at+jwt` = không phải access token” cho hệ thống không hề áp dụng profile này.

### 5.4. Claim loại token riêng của nhà cung cấp

Một số issuer đưa vào payload các claim đặc thù, ví dụ:

```json
{
  "token_use": "access",
  "iss": "https://identity.example.com",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1910000000
}
```

Nếu hợp đồng của issuer cam kết `token_use=access`, API có thể **bắt buộc kiểm tra claim đó**. Một ID token từ cùng issuer có thể mang `token_use=id` và phải bị từ chối. Tên và tập giá trị của claim phụ thuộc provider; `token_use` **không phải claim chuẩn bắt buộc của mọi access token OAuth 2.0**.

Không dùng một claim tự đặt tên chưa được xác minh như bằng chứng độc lập. Chỉ kiểm tra sau khi token đã được xác thực bằng khóa và issuer tin cậy.

### 5.5. `client_id`, `azp`, `sub` và scope

- `client_id` trong JWT access token theo RFC 9068 nhận diện client đã yêu cầu token; nó **không thay thế `aud`** của Resource Server.
- `azp` có ngữ nghĩa cụ thể trong một số profile, chẳng hạn OIDC ID token; không mặc định mọi issuer đều dùng `azp` như `client_id`.
- `sub` là subject. Với `client_credentials`, token có thể đại diện cho client/service thay vì người dùng cuối. Không suy ra “có `sub` là ID token” hay “không có email là access token máy”.
- `scope` biểu diễn phạm vi quyền, nhưng **scope một mình không xác minh token type**. ID token hoặc JWT do nhà cung cấp tùy biến có thể vô tình chứa dữ liệu trông giống quyền; ngược lại, access token có thể không dùng đúng tên `scope`.

Nếu API chỉ phục vụ một tập client cụ thể, có thể thêm policy kiểm tra `client_id`; đây là **điều kiện bổ sung**, không phải quy tắc phân biệt access token bằng một claim duy nhất.

## 6. Profile RFC 9068 và profile tùy biến: phải chọn nhất quán

### 6.1. Khi Authorization Server hỗ trợ RFC 9068

RFC 9068 thiết lập profile JWT access token cho OAuth 2.0. Khi triển khai đúng profile này, API có cơ sở kiểm tra:

- JOSE `typ` là `at+jwt` hoặc `application/at+jwt`.
- Thuật toán chữ ký và khóa phù hợp chính sách; token phải được xác thực trước khi tin claims.
- Issuer `iss` khớp issuer đáng tin cậy.
- `aud` chỉ đến resource server mong đợi.
- Các claim được yêu cầu bởi profile như `sub`, `client_id`, `iat`, `exp`, `jti` được hiện diện và xử lý theo quy tắc profile.
- Các scope/authorization details liên quan đến API được áp dụng theo hợp đồng.

Hợp đồng này giúp làm rõ ràng hơn sự khác biệt giữa JWT access token và OIDC ID token khi cả hai do cùng một OP phát hành.

**Cần thực thi profile như một tổng thể.** Việc chỉ xem `typ` hoặc chỉ thêm `aud` chưa tự động làm ứng dụng tuân thủ mọi yêu cầu RFC 9068.

### 6.2. Khi issuer sử dụng JWT access token tùy biến

Một số issuer có thể trả về:

```json
{
  "alg": "RS256",
  "kid": "issuer-key-1",
  "typ": "JWT"
}
```

Cùng với payload:

```json
{
  "iss": "https://id.example.com",
  "aud": "orders-api",
  "sub": "user-123",
  "token_use": "access",
  "scope": "orders.read",
  "exp": 1910000000
}
```

Trong trường hợp này, có thể xây contract **provider-specific**: chữ ký và issuer đúng, `aud=orders-api`, `token_use=access`, thời hạn và scope phù hợp. Nhưng API không được tự tuyên bố đã áp dụng RFC 9068 chỉ vì payload có nhiều claim tương tự.

Đặc biệt, nếu issuer **không có cách phân biệt đáng tin cậy** giữa ID token và access token cho cùng audience, chỉ dựa vào “chữ ký đúng” sẽ tạo vùng mơ hồ. Cần điều chỉnh thiết kế ở Authorization Server hoặc phân định audience/key/profile rõ ràng trước khi cho phép API sử dụng token.

### 6.3. Không phối hợp các profile bằng OR quá rộng

Một thiết kế nguy hiểm:

```text
Accept JWT if:
  signature valid
  AND issuer valid
  AND (
       typ == at+jwt
       OR token_use == access
       OR scope contains orders.read
       OR sub exists
  )
```

Điều kiện `OR` trên có thể làm nhánh yếu nhất bỏ qua các nhánh mạnh: chỉ cần có `sub` là token lọt vào. Thay vào đó hãy xác định **mỗi profile có bộ điều kiện AND bắt buộc**, và chỉ áp dụng profile khi xác định được issuer, endpoint, hoặc đường xác thực được cho phép:

```text
Profile A / RFC 9068:
  signature AND issuer AND at+jwt AND audience
  AND required claims AND time AND authorization

Profile B / provider-specific:
  signature AND issuer AND token_use=access
  AND audience AND required claims AND time AND authorization
```

Nếu API thật sự hỗ trợ hai kiểu token, cần hai policy độc lập và có cách chọn profile **không dựa vào việc thử tuần tự đến khi một policy nào đó cho qua**.

## 7. Ví dụ về cross-JWT confusion

### 7.1. ID token bị đưa vào Authorization header của API

Một OIDC flow hoàn thành và client nhận **hai JWT khác nhau**. Ví dụ ID token:

```json
{
  "iss": "https://id.example.com",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1909996400,
  "exp": 1910000000,
  "nonce": "client-login-nonce"
}
```

Và JWT access token:

```json
{
  "iss": "https://id.example.com",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "web-client",
  "scope": "orders.read",
  "iat": 1909996400,
  "exp": 1910000000,
  "jti": "grant-token-id-1"
}
```

Trong ví dụ, hai token có thể cùng `alg=RS256`, cùng `kid`, cùng `iss`, `sub` và đều chưa hết hạn. Nhưng **ID token** dành cho RP với `aud=web-client`; chỉ **access token** mới hướng tới Resource Server `orders-api`.

Nếu API kiểm tra chữ ký và issuer nhưng bỏ qua audience, ID token có thể bị chấp nhận nhầm. API cần xác thực **đúng purpose và audience**, không quan tâm token có chứa email, username hoặc `nonce` hay không.

### 7.2. Logout token là JWT có chữ ký đúng

OIDC Back-Channel Logout dùng **logout token** dạng JWT để thông báo sự kiện đăng xuất. Token này có cấu trúc claim theo đặc tả logout, có thể chứa `events`, `sid`, `sub`, `iat`, `jti` và audience hướng đến RP.

Nó không cấp quyền gọi API. Một bộ xác minh chỉ xem “token được OP ký và có sub” có thể nhầm logout token với access token. Việc kiểm tra token profile, audience và mục đích sử dụng ngăn loại nhầm lẫn này.

### 7.3. Client assertion JWT

Một confidential client có thể dùng JWT assertion được ký để xác thực với token endpoint. Audience của assertion thường chỉ đến AS/token endpoint theo profile tương ứng, có `iss`, `sub` biểu thị client. Token này cũng có thể dùng cùng thuật toán JWT nhưng không trao quyền gọi API nghiệp vụ.

Không dùng claim `sub` hoặc `client_id` để quyết định nó là access token; cả hai có thể xuất hiện trong các loại JWT khác nhau.

### 7.4. Refresh token hoặc authorization code bị gửi nhầm

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer REFRESH_TOKEN_VALUE
```

Refresh token được thiết kế cho **token endpoint của Authorization Server**, không dành cho Resource Server. Nếu API dùng JWT decoder, một opaque refresh token thường bị từ chối vì không phải JWT. Nhưng một refresh token *trông giống JWT* vẫn phải bị từ chối theo **hợp đồng access token**, không dựa vào giả định refresh token luôn opaque.

Tương tự, authorization code là giá trị tạm thời để client đổi qua token endpoint; nó không phải access token, bất kể chuỗi code có cấu trúc như thế nào.

### 7.5. DPoP proof không phải DPoP-bound access token

Với **DPoP** (RFC 9449), client có thể gửi:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: DPoP ACCESS_TOKEN
DPoP: SIGNED_DPOP_PROOF_JWT
```

DPoP proof là JWT chứng minh bên gửi sở hữu khóa và gắn với request (ví dụ method, URI, thời điểm, nonce/jti tùy trường hợp). Nó **không thay thế access token**. Resource Server phải kiểm tra access token theo contract **và** kiểm tra ràng buộc với DPoP proof, gồm thumbprint khóa trong confirmation claim khi profile dùng cơ chế này.

Nếu vô tình nhận DPoP proof JWT làm Bearer access token, API đã nhầm hai vai trò giao thức. Tương tự, không chấp nhận token bị ràng buộc mTLS/DPoP như bearer token thuần nếu hợp đồng yêu cầu chứng minh bên gửi.

## 8. Thiết kế luồng kiểm tra một request tại Resource Server

Một mô hình logic:

```mermaid
flowchart TD
    A["HTTP request tới API"] --> B["Trích xuất credential theo scheme được hỗ trợ"]
    B --> C{"Có đúng một token theo transport contract?"}
    C -- "Không" --> U["Từ chối đầu vào / yêu cầu xác thực"]
    C -- "Có" --> D{"Định dạng token đã cam kết?"}
    D -- "JWT access token" --> E["Chọn issuer/decoder từ allow-list cấu hình"]
    D -- "Opaque access token" --> F["Introspect tại AS được cấu hình tin cậy"]
    D -- "Sai định dạng" --> U
    E --> G["Kiểm tra alg, khóa, chữ ký và thời hạn"]
    G --> H{"Đạt xác thực mật mã?"}
    H -- "Không" --> U
    H -- "Có" --> I["Kiểm tra issuer, typ/profile, aud, claims"]
    F --> J["Kiểm tra active, audience/resource, metadata và profile"]
    I --> K{"Token đúng loại và dành cho API?"}
    J --> K
    K -- "Không" --> U
    K -- "Có" --> L["Ánh xạ principal và authorities"]
    L --> M{"Có scope và quyền với tài nguyên?"}
    M -- "Không" --> V["Từ chối phân quyền"]
    M -- "Có" --> N["Cho phép xử lý endpoint"]
```

Sơ đồ mô tả **các điều kiện bắt buộc về mặt chính sách**; một JWT library có thể thực hiện nhiều kiểm tra ở một bước hoặc trước/sau nhau theo cách triển khai. Không được dùng claims để **cấp quyền** trước khi bộ xác thực đã tin token.

### Các nguyên tắc triển khai quan trọng

1. **Một issuer phải gắn với các khóa hoặc introspection endpoint tin cậy.** Không tin JWK URL tự khai báo trong token.
2. **Phân biệt loại token trước khi tạo identity được dùng cho API.** Với signed JWT, việc phân loại dựa vào token profile và dữ liệu đã được xác thực; với opaque, dựa vào metadata có thể tin từ AS.
3. **Không có một heuristic chung cho mọi nhà cung cấp.** JWT ba phần, claim `sub`, `email`, `scope` hay giá trị `token_type=Bearer` riêng lẻ đều không chứng minh “đây là access token”.
4. **Không “fallback” tự do giữa các loại token.** Nếu JWT validation thất bại, không tự chuyển sang coi nó là ID token, refresh token hoặc thử một issuer không nằm trong hợp đồng.
5. **Không dùng cả ID token và access token như hai credential thay thế cho cùng API endpoint.** Nếu endpoint cần xác thực phiên browser và bearer API thì phải có boundary/cấu hình cụ thể, tránh nhập nhằng scheme.
6. **Luôn kiểm tra phân quyền nghiệp vụ sau khi xác thực token**. `orders.read` có thể không đủ để đọc đơn hàng thuộc tenant khác.

## 9. Spring Security Resource Server: JWT access token

Spring Security Servlet Resource Server thường gồm:

- `BearerTokenAuthenticationFilter` tách token Bearer từ request.
- `JwtAuthenticationProvider` dùng `JwtDecoder` để giải mã và kiểm tra JWT.
- `NimbusJwtDecoder` kiểm tra chữ ký bằng khóa/JWK theo cấu hình và áp dụng các `OAuth2TokenValidator<Jwt>`.
- `JwtAuthenticationConverter` tạo `Authentication` từ JWT và chuyển các scope thành authority với tiền tố `SCOPE_` theo quy ước mặc định.
- `SecurityFilterChain` cùng lớp nghiệp vụ áp dụng authorization.

Không phải cứ cấu hình `issuer-uri` thì API tự hiểu mọi **mục đích sử dụng token** hoặc mọi **audience**. Cần chủ động triển khai hợp đồng access token mà API yêu cầu.

### 9.1. Cấu hình issuer và audience

Ví dụ cơ bản:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/demo
```

Với Spring Boot/Spring Security phù hợp, ứng dụng có thể lấy metadata/JWKS từ issuer và xác minh JWT. Nhưng nếu API muốn chỉ chấp nhận access token cho `orders-api`, phải bổ sung kiểm tra audience hoặc cấu hình audience được hỗ trợ bởi phiên bản framework.

Chỉ kiểm tra `iss` và chữ ký là chưa đủ: ID token do cùng OP phát hành cũng có thể vượt các kiểm tra đó.

### 9.2. Ví dụ nghiêm ngặt: Resource Server nhận token theo RFC 9068

Ví dụ sau dành cho Spring Security phiên bản có API `validateType(false)` và `JwtValidators.createAtJwtValidator()`. Nó đặt **profile JWT access token RFC 9068** thành hợp đồng đầu vào; `client_id` được khóa vào một client ứng dụng theo ví dụ. Thư viện/framework cụ thể và issuer phải thực sự hỗ trợ profile trước khi áp dụng.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersResourceServerConfig {

    private static final String ISSUER =
            "https://id.example.com/realms/demo";
    private static final String API_AUDIENCE = "orders-api";
    private static final String ALLOWED_CLIENT = "web-client";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withIssuerLocation(ISSUER)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                // Để JWT type được validator của access-token profile kiểm tra.
                .validateType(false)
                .build();

        decoder.setJwtValidator(
                JwtValidators.createAtJwtValidator()
                        .issuer(ISSUER)
                        .audience(API_AUDIENCE)
                        .clientId(ALLOWED_CLIENT)
                        .build());

        return decoder;
    }

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Cách đọc ví dụ:

- `withIssuerLocation(ISSUER)` ràng buộc decoder với issuer và nguồn khóa tin cậy được khám phá từ issuer.
- `jwsAlgorithm(RS256)` nêu rõ thuật toán ký mà API cho phép; `alg` trong JWT không được quyền tự mở rộng cấu hình.
- `validateType(false)` tắt **bước type-check mặc định ở tầng Nimbus decoder** để giao việc kiểm tra type cho validator profile; nó **không có nghĩa bỏ hết kiểm tra type**.
- `createAtJwtValidator()` là lựa chọn framework để kiểm tra các điều kiện access token profile; các tham số `issuer`, `audience`, `clientId` ràng buộc token với đúng nguồn, API và client theo tình huống ví dụ.
- `hasAuthority("SCOPE_orders.read")` và `SCOPE_orders.write` là **quy tắc phân quyền API**, độc lập với việc JWT đã xác thực có đúng loại hay chưa.

**Giới hạn cần hiểu:** API ở ví dụ chỉ nhận token của một client ID. Nếu nhiều client được cấp quyền, không được sửa thành một client ID giả; cần thiết kế policy nhiều client hợp lệ theo khả năng thực tế của framework/Authorization Server. Không sao chép code profile RFC 9068 vào hệ thống có issuer phát hành access token không theo profile. Phiên bản Spring Security cũ hơn có thể không có đúng các API builder này; khi đó cần cơ chế validation tương đương của phiên bản đang dùng.

### 9.3. Ví dụ khi issuer dùng claim riêng `token_use=access`

Nếu provider phát hành JWT access token với claim riêng `token_use`, có thể thiết kế validator theo hợp đồng provider. Ví dụ dưới đây cho thấy **kiểm tra type, issuer và audience theo kiểu AND**. Phần code tập trung vào validator; `JwtDecoder` vẫn phải kiểm tra chữ ký bằng khóa và thuật toán được cho phép.

```java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

public final class JwtAccessTokenContracts {

    private JwtAccessTokenContracts() {}

    static OAuth2TokenValidator<Jwt> forOrdersApi(String trustedIssuer) {
        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(trustedIssuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : invalid("Token audience is not orders-api");

        OAuth2TokenValidator<Jwt> accessPurpose = jwt ->
                "access".equals(jwt.getClaimAsString("token_use"))
                    ? OAuth2TokenValidatorResult.success()
                    : invalid("Token purpose is not access");

        return new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audience, accessPurpose);
    }

    private static OAuth2TokenValidatorResult invalid(String message) {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", message, null));
    }
}
```

Gắn validator vào decoder bằng `decoder.setJwtValidator(JwtAccessTokenContracts.forOrdersApi(ISSUER))` **sau khi** tạo decoder đã cấu hình nguồn khóa và thuật toán tin cậy. Lưu ý `setJwtValidator(...)` thay bộ validator đã đăng ký; phải giữ những kiểm tra cần thiết về issuer, thời hạn, audience và token purpose trong validator tổng hợp.

Nếu decoder mặc định **đã yêu cầu `typ=JWT`** và provider phát hành `typ` khác, cần điều chỉnh cơ chế kiểm tra JOSE type theo API của phiên bản Spring Security, đồng thời giữ kiểm tra `token_use` và audience theo policy. Không dùng `validateType(false)` để “giải quyết lỗi” nếu không có validator profile hoặc quy tắc tương đương thay thế.

Các mục tiêu của thiết kế này khác với ví dụ RFC 9068:

- **RFC 9068:** dựa trên `at+jwt` và các claim/validation do profile chuẩn quy định.
- **Provider-specific:** dựa trên **hợp đồng issuer thực tế**, ví dụ `token_use=access`, và audience đúng.
- Không trộn hai profile bằng phép OR nới lỏng nếu nhà cung cấp không cam kết cách phát hành.

## 10. Nếu access token là opaque thì phân biệt thế nào?

Không phải mọi access token đều là JWT. Một Authorization Server có thể cấp token opaque, ví dụ:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer XoU6Dk...opaque-value...
```

Resource Server không thể biết token có phải access token chỉ bằng cách decode chuỗi này. Với mô hình OAuth 2.0 Token Introspection (RFC 7662), API gọi endpoint tin cậy của Authorization Server để hỏi **trạng thái và metadata**.

Ví dụ nội dung response introspection minh họa:

```json
{
  "active": true,
  "iss": "https://id.example.com",
  "sub": "user-123",
  "client_id": "web-client",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1910000000,
  "token_type": "Bearer"
}
```

Cần hiểu các trường:

- `active=true` cho biết token được introspection endpoint xem là đang hoạt động theo ngữ cảnh yêu cầu; **không tự thay thế audience và authorization**.
- `aud` hoặc metadata ràng buộc resource, nếu được cung cấp, phải hướng đến API phù hợp.
- `scope`/metadata quyền phải được ánh xạ đúng và không thay kiểm tra quyền đối với tài nguyên cụ thể.
- `token_type=Bearer` chỉ cách dùng token theo Bearer scheme, **không phải bằng chứng phân loại ID token/access token độc lập**.
- Các field tùy chọn phụ thuộc Authorization Server; nếu không có thông tin đủ để chứng minh token thuộc đúng loại và audience, API cần chỉnh hợp đồng với issuer, không tự suy đoán.

Cấu hình Spring Security Resource Server cho introspection:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: YOUR_SECRET_FROM_SECURE_CONFIGURATION
```

Đây là phần kết nối để kiểm tra token opaque. API vẫn phải áp dụng **contract về đối tượng nhận và quyền** theo metadata được Authorization Server cam kết. Nếu cần kiểm tra audience/token purpose tùy biến, có thể bọc `OpaqueTokenIntrospector` hoặc áp dụng authorization policy dựa trên các attributes được introspection trả về; không giả định cấu hình trên tự thực thi mọi policy cho API.

Lưu ý bảo mật: client credentials dùng để gọi introspection là **bí mật của Resource Server**; cấp quyền tối thiểu và lưu trong cơ chế secret management, không ghi thẳng thông tin thật vào repository.

## 11. Nếu hệ thống đồng thời dùng đăng nhập OIDC và API Resource Server

Một backend có thể vừa:

- Dùng **`oauth2Login()`** để đóng vai trò OIDC Client, kiểm tra ID token từ OP và thiết lập session đăng nhập.
- Dùng **OAuth2 Client** để gọi API khác bằng access token.
- Dùng **`oauth2ResourceServer()`** để bảo vệ endpoint API của chính mình bằng access token do client gửi.

Ba vai trò này có thể tồn tại trong cùng ứng dụng, nhưng cần đặt **ranh giới đường dẫn và security chain** rõ ràng. Ví dụ browser UI truy cập `/app/**` bằng session cookie, còn `/api/**` chấp nhận access token theo hợp đồng của API.

```text
Browser              Backend web / OIDC RP             OpenID Provider
   |                      |                                |
   |--- login ----------->|------ OIDC authorization ---->|
   |                      |<----- ID token ---------------|
   |                      |  Kiểm tra ID token,
   |                      |  tạo session/cookie
   |
   |--- UI request với session cookie --------------------> RP
   |
   |--- API request với access token ---> Resource Server
                                         ^            |
                                         |            v
                                      issuer/JWKS   API authorization
```

Sơ đồ chỉ minh họa vai trò, không phải một luồng trao đổi HTTP đầy đủ. Trong kiến trúc Browser-for-Frontend, browser có thể **không trực tiếp giữ access token**, mà backend giữ token và thực hiện API calls. Dù đặt token ở đâu, **ID token vẫn không được thay access token gửi cho Resource Server**.

Việc cả hai cơ chế cùng tạo `Authentication` trong Spring Security không biến credential của cơ chế này thành credential hợp lệ cho cơ chế kia. Nếu endpoint API cho phép session và bearer token cùng hoạt động, cần quyết định rõ nó có phải yêu cầu chủ ý và cách xử lý khi cả hai đồng thời xuất hiện.

## 12. Các lỗi thiết kế thường gặp

| Thiết kế sai | Hệ quả | Thiết kế đúng |
|---|---|---|
| API chấp nhận bất kỳ JWT nào ký đúng bởi OP | ID token/logout token/client assertion có thể được chấp nhận nhầm | Kiểm tra access token profile và audience của API |
| Chỉ kiểm tra `sub` hoặc email | Token xác thực danh tính bị hiểu là token có quyền API | `sub` chỉ là chủ thể; quyền cần hợp đồng access token và authorization |
| Chỉ kiểm tra scope `orders.read` | Bỏ qua issuer, audience, purpose và chữ ký | Token phải đạt toàn bộ chuỗi kiểm tra trước khi xét scope |
| Coi `typ=JWT` là access token | JWT generic có nhiều mục đích | Với RFC 9068 yêu cầu `at+jwt`; nếu custom, dùng profile rõ ràng |
| Bỏ kiểm tra `aud` vì issuer ký đúng | Token cho API/client khác có thể được chấp nhận | Audience là ranh giới đối tượng nhận |
| Tin `kid` hoặc `jku` trong token để tự tìm khóa | Key confusion, SSRF, nhầm trust domain | Chỉ dùng khóa/JWKS của issuer cấu hình tin cậy |
| Luôn cho JWT chứa `token_use` bất kỳ | Không chặn ID/refresh token nếu provider phân biệt token use | Kiểm tra `token_use=access` khi issuer cam kết claim đó |
| Coi `token_type=Bearer` từ introspection là đủ | Bearer scheme bị hiểu nhầm thành mục đích | Kiểm tra resource/purpose theo contract của introspection |
| Khi validator thất bại thì thử decoder issuer khác | Hạ tiêu chuẩn tin cậy đến khi token nào đó “lọt” | Mỗi issuer/profile có chính sách tin cậy định trước |
| Nhận DPoP proof JWT như access token | Nhầm bằng chứng sở hữu khóa với quyền API | Xác minh access token và DPoP proof theo hai nhiệm vụ |
| Mở mọi endpoint chỉ vì JWT có role `admin` | Vượt quyền đối tượng/tenant | Kiểm tra authorization theo API và đối tượng thực |
| Bỏ qua token revocation khi có yêu cầu thu hồi tức thời | JWT còn hạn tiếp tục dùng sau thu hồi | Chọn chiến lược revocation/short TTL/introspection theo yêu cầu hệ thống |

### Một ví dụ anti-pattern cụ thể

```java
// KHÔNG dùng cách kiểm tra token bằng cách chỉ decode claims.
// jwt.getSubject() != null KHÔNG chứng minh đây là access token.
// jwt.getHeaders().containsKey("kid") KHÔNG chứng minh chữ ký đã được xác thực.
//
// Không chỉ viết điều kiện:
// if (jwt.getSubject() != null) allowRequest();
```

Để cấp quyền, Resource Server phải xác thực token bằng bộ xác minh thực sự rồi kiểm tra issuer, audience, purpose và quyền theo hợp đồng. Không chuyển đoạn code ở trên thành cơ chế “lọc JWT thủ công”.

## 13. Các tình huống có nhiều resource, nhiều issuer hoặc token exchange

### 13.1. Một access token có nhiều audience

Có những access token cho nhiều resource theo hợp đồng của Authorization Server. Nếu API `orders-api` nhận token có `aud=["orders-api","reporting-api"]`, việc chấp nhận phải dựa trên **chính sách resource của API**, không dựa vào cảm tính rằng có nhiều audience thì luôn sai hoặc luôn đúng.

Với môi trường tách quyền mạnh, token chỉ chứa audience của tài nguyên đang gọi thường giúp giảm khả năng lộ token dẫn đến truy cập chéo. Nếu issuer cấp token đa audience, API phải đánh giá quyền scope, client, tenant và ràng buộc tài nguyên tương ứng.

### 13.2. Multi-issuer / multi-tenant

Giả sử hệ thống tin hai issuer `issuer-A` và `issuer-B`. Mỗi issuer có JWKS riêng, audience và claim mapping có thể khác nhau. Không được gom khóa mà bỏ qua issuer.

```text
issuer-A -> JWKS-A -> access-token contract A -> orders-api
issuer-B -> JWKS-B -> access-token contract B -> orders-api
```

Một JWT chưa xác thực có thể mang `iss=issuer-B` để giúp chọn **một trong các decoder đã được cấu hình trước**, nhưng sau khi kiểm tra chữ ký vẫn phải so khớp `iss` với decoder/profile đã chọn. Không để token tự chỉ định một issuer mới hoặc nguồn khóa mới ngoài danh sách tin cậy.

### 13.3. OAuth 2.0 Token Exchange

Trong một chuỗi microservice, service A có thể cần đổi access token dành cho A thành access token mới dành cho service B qua Authorization Server, tùy thiết kế OAuth Token Exchange.

```text
Client -> Service A [access token aud=service-a]
Service A -> Authorization Server [token exchange theo policy]
Authorization Server -> Service A [access token aud=service-b]
Service A -> Service B [access token aud=service-b]
```

Không nên gửi nguyên access token `aud=service-a` sang service B rồi yêu cầu B bỏ kiểm tra audience. Khi B chấp nhận token sai audience, ranh giới giữa các API bị phá vỡ.

### 13.4. User token và machine token

API có thể nhận cả token có user context và token của client_credentials. Cần ghi rõ những endpoint nào cho phép service principal và endpoint nào yêu cầu user principal.

Ví dụ `POST /api/orders/sync` có thể cho service `sync-worker` với quyền `orders.sync`, trong khi `GET /api/orders/me` cần user context. `sub` của machine token không phải người dùng đăng nhập. Không viết chính sách phụ thuộc email hay session chỉ vì mọi request đều có JWT.

## 14. Thiết kế phản hồi lỗi phù hợp

Khi token không đúng mục đích hoặc đối tượng nhận, đó là **lỗi xác thực credential** đối với API:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Khi token đã được xác thực và được chấp nhận là access token cho API nhưng không đủ quyền thao tác:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Đây là cách phân biệt điển hình theo RFC 6750 và các hành vi thường gặp trong Resource Server. Status/challenge thực tế phụ thuộc security chain, entry point, access denied handler và transport (Bearer/DPoP) đã cấu hình.

Đừng trả nguyên JWT hoặc metadata nhạy cảm trong lỗi. Log nên tách các nhóm như `wrong_issuer`, `invalid_signature`, `wrong_audience`, `wrong_token_type`, `missing_scope`, `tenant_policy_denied`, nhưng không ghi nguyên bearer credential, refresh token hay nội dung xác thực vào log ứng dụng.

**Lỗi người dùng cuối:** “Không thể truy cập tài nguyên” có thể đủ. **Chẩn đoán phía vận hành:** phân biệt token sai audience với token thiếu scope giúp sửa issuer/client configuration mà không làm giảm chính sách bảo vệ API.

## 15. Bộ tình huống cần bao phủ khi thiết kế hợp đồng

Bảng này là **ma trận tình huống để xây dựng yêu cầu xác thực**, không phải kết quả một bộ test đã chạy:

| Input gửi đến Resource Server `orders-api` | Chữ ký/issuer | Đối tượng/mục đích | Kết quả thiết kế |
|---|---|---|---|
| RFC 9068 access JWT `typ=at+jwt`, `aud=orders-api`, `orders.read` | Hợp lệ | Phù hợp | Cho qua xác thực, xét quyền đối tượng |
| ID token OIDC `aud=web-client` | Hợp lệ | Sai audience/type | Từ chối |
| Access JWT `typ=at+jwt`, `aud=billing-api` | Hợp lệ | Sai audience | Từ chối |
| JWT `typ=JWT`, `aud=orders-api` khi policy **yêu cầu RFC 9068** | Hợp lệ | Không khớp profile `typ` | Từ chối |
| JWT với `token_use=id` khi policy provider yêu cầu `access` | Hợp lệ | Sai purpose | Từ chối |
| Client assertion `aud=token-endpoint` | Hợp lệ | Sai đối tượng nhận | Từ chối |
| Logout token của RP | Hợp lệ | Sai purpose | Từ chối |
| Refresh token opaque gửi làm Bearer API token | Không xác thực là access token | Sai purpose | Từ chối |
| JWT tự khai `alg=none` | Không đáp ứng yêu cầu signed JWT | Không xét | Từ chối |
| JWT sai chữ ký dù có `typ=at+jwt` | Không hợp lệ | Không xét | Từ chối |
| Access JWT hết hạn | Không còn hiệu lực | Không xét | Từ chối |
| Access JWT đúng contract nhưng thiếu `orders.write` | Hợp lệ | Phù hợp | Từ chối phân quyền khi gọi POST |
| Access JWT có `orders.read` nhưng khác tenant | Hợp lệ | Phù hợp | Từ chối quyền đối tượng |
| Access token ràng buộc DPoP nhưng không có proof hợp lệ | Có thể chữ ký access token đúng | Thiếu điều kiện sender binding | Từ chối |
| Opaque token `active=true` nhưng metadata không chứng minh resource phù hợp | Hoạt động theo AS | Chưa đạt contract API | Từ chối hoặc yêu cầu bổ sung metadata/hợp đồng |

### Tách trách nhiệm giữa các thành phần

| Thành phần | Trách nhiệm |
|---|---|
| **Authorization Server / OP** | Phát hành token đúng profile, audience và scope; công bố metadata/JWKS hoặc introspection đáng tin |
| **OAuth Client** | Dùng access token khi gọi API; dùng ID token khi xử lý đăng nhập; gửi refresh token đến AS |
| **API Gateway** | Bảo vệ transport, chính sách credential đầu vào và các ràng buộc được triển khai tại edge |
| **Resource Server JWT decoder / opaque introspector** | Xác thực nguồn, chữ ký hoặc trạng thái token; thực thi token profile và audience |
| **Spring Security authorization** | Ánh xạ scope/authority, xác định endpoint nào đòi quyền nào |
| **Application service / domain** | Kiểm tra quyền trên object, tenant, account và quy tắc nghiệp vụ |

Hợp đồng này nên được ghi rõ giữa đội Authorization Server, client và API; không dựa vào việc “token nhìn giống JWT” hoặc “cùng OP thì dùng được cho mọi API”.

## 16. Những điều cần ghi nhớ

1. **Access token được nhận diện bằng hợp đồng phát hành và sử dụng**, không chỉ bằng định dạng JWT hay sự có mặt của một claim.
2. **Signature + issuer + expiry là cần thiết nhưng chưa đủ** khi nhiều loại JWT được phát hành bởi cùng issuer.
3. **Audience là ranh giới API**: token cho OIDC Client, token endpoint hoặc API khác phải bị từ chối tại Resource Server.
4. **Token profile là ranh giới mục đích**: với RFC 9068 kiểm tra `at+jwt` và các yêu cầu profile; với provider-specific JWT kiểm tra dấu hiệu access token do issuer cam kết.
5. **Refresh token, ID token, logout token, authorization code, client assertion và DPoP proof không phải access token của API**, dù cùng có thể là chuỗi hoặc JWT.
6. **Với opaque token, introspection phải cung cấp hoặc ràng buộc đủ metadata để API xác nhận đúng resource và mục đích**. `active=true` hoặc `token_type=Bearer` một mình không thay toàn bộ hợp đồng.
7. **Scope và quyền đối tượng được kiểm tra sau khi token đáp ứng hợp đồng**. Chấp nhận đúng access token không mặc định cho phép mọi thao tác.
8. **Đừng làm yếu contract để “cho token hoạt động”**. Nếu token sai audience/type, cần sửa cấu hình phía client/issuer hoặc dùng token exchange thích hợp.

Một Resource Server triển khai đúng nhận dạng **đúng nguồn**, **đúng loại token**, **đúng đối tượng nhận**, **đúng trạng thái** và **đúng quyền** trước khi mở API. Đây là cách ngăn việc tái sử dụng token hợp lệ về mặt chữ ký nhưng sai mục đích.

## 17. Tài liệu nền tảng

- **RFC 6749 — The OAuth 2.0 Authorization Framework**: access token, refresh token và grant semantics. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: cách trình bày bearer access token và mã lỗi. https://www.rfc-editor.org/rfc/rfc6750
- **OpenID Connect Core 1.0**: ID token và quy tắc bên nhận là Relying Party. https://openid.net/specs/openid-connect-core-1_0.html
- **OpenID Connect Back-Channel Logout 1.0**: logout token có purpose riêng. https://openid.net/specs/openid-connect-backchannel-1_0.html
- **RFC 7519 — JSON Web Token**: claims, header và JWT. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JWT Best Current Practices**: cross-JWT confusion, audience và explicit typing. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**: profile `at+jwt` cho JWT access token. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection**: xác minh trạng thái và metadata token opaque. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 8693 — OAuth 2.0 Token Exchange**: đổi token theo resource/audience và mục đích. https://www.rfc-editor.org/rfc/rfc8693
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)**: xác minh proof và token ràng buộc với khóa. https://www.rfc-editor.org/rfc/rfc9449
- **Spring Security Reference — OAuth 2.0 Resource Server**: xác thực JWT hoặc opaque token và khai báo authorization. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
