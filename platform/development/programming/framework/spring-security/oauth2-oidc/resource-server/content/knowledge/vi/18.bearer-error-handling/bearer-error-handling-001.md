# Yêu cầu thiếu token, token sai định dạng và token bị từ chối

## 1. Một endpoint bảo vệ, ba tình huống rất khác nhau

Giả sử ứng dụng Spring Boot đóng vai trò **OAuth 2.0 Resource Server** cung cấp API đơn hàng:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Accept: application/json
```

Endpoint này yêu cầu **OAuth 2.0 access token** được trình dưới dạng Bearer credential và phải có quyền `orders.read`. Người học thường gom mọi trường hợp không truy cập được API thành “token lỗi”, nhưng ít nhất có ba tình huống khác nhau:

1. **Yêu cầu thiếu token:** Client không gửi một Bearer credential nào.
2. **Cách gửi token sai định dạng:** Client gửi `Authorization` theo cú pháp Bearer không hợp lệ, hoặc gửi credential qua những phương thức không được chấp nhận.
3. **Token bị từ chối:** Spring Security đã lấy được một chuỗi Bearer token, nhưng quá trình xác thực JWT hoặc opaque token thất bại.

Ngoài ra còn một trường hợp cần phân biệt: **token xác thực hợp lệ nhưng không đủ quyền** để gọi endpoint. Đó là vấn đề *authorization*, không phải token bị từ chối ở bước *authentication*.

| Tình huống | Ví dụ | Phản hồi thường gặp |
|---|---|---|
| Không có token | Không có `Authorization` | `401 Unauthorized`, challenge `Bearer` |
| Bearer request sai cú pháp | `Authorization: Bearer abc def` | `400 Bad Request`, `error="invalid_request"` |
| Bearer có dạng có thể trích xuất nhưng JWT hỏng | `Authorization: Bearer abc.def.ghi` | `401 Unauthorized`, `error="invalid_token"` |
| Token đúng cấu trúc nhưng hết hạn/sai chữ ký/issuer/audience | Bearer JWT không qua validator | `401 Unauthorized`, thường `invalid_token` |
| Opaque token bị introspection từ chối | AS trả `{"active":false}` | `401 Unauthorized`, thường `invalid_token` |
| Token đã xác thực nhưng thiếu scope | Có `profile.read`, cần `orders.read` | `403 Forbidden`, thường `insufficient_scope` |

Bảng trên phản ánh các hành vi phổ biến của Bearer scheme theo RFC 6750 và Spring Security Resource Server. **Mã trạng thái cụ thể của một request sai cú pháp có thể phụ thuộc loại lỗi, `BearerTokenResolver`, filter và error handler đang được dùng.** Không nên khẳng định mọi request có token hỏng đều trả đúng một mã HTTP.

### Sau bài học, bạn sẽ biết

- Phân biệt **không có token**, **Bearer request không hợp lệ**, **token không hợp lệ** và **token thiếu quyền**.
- Hiểu ý nghĩa của HTTP `400`, `401`, `403` và `WWW-Authenticate` theo OAuth 2.0 Bearer Token Usage.
- Theo dõi đường xử lý qua `BearerTokenAuthenticationFilter`, `BearerTokenResolver`, `JwtDecoder` hoặc `OpaqueTokenIntrospector`.
- Cấu hình Spring Security Resource Server để trả challenge đúng, bảo vệ endpoint công khai và endpoint cần scope.
- Giải thích vì sao `permitAll` không đảm bảo token Bearer sai được bỏ qua.
- Thiết kế HTTP request, test và log để xác định lỗi phát sinh ở bước nào.
- Tránh đưa access token, bí mật introspection hoặc thông tin nhạy cảm vào error response.

## 2. Hiểu ngôn ngữ: request, credential và token validation

Một HTTP request mang Bearer credential thông dụng:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0...
```

Có ba lớp cần xem xét:

**Lớp HTTP/Bearer transport:** Header `Authorization` có thể được diễn giải là một Bearer credential hay không? Bearer credential có đặt ở nơi Resource Server cho phép hay không?

**Lớp token authentication:** Chuỗi được trích xuất có đại diện token mà Resource Server được phép tin hay không? Với JWT cần xác minh chữ ký, issuer, audience, thời hạn và hợp đồng token; với opaque token có thể cần introspection.

**Lớp authorization:** Token đã xác thực có đủ scope/authority, Client/tenant và quyền đối với bản ghi đang được truy cập hay không?

```mermaid
flowchart TD
    A["HTTP request"] --> B{"Có Bearer credential?"}
    B -->|Không| C["Không có Bearer Authentication"]
    C --> D{"Endpoint public hay protected?"}
    D -->|Public| OK1["Đi tiếp tới endpoint"]
    D -->|Protected| E401["401 + WWW-Authenticate: Bearer"]
    B -->|Cách gửi sai cú pháp| E400["400 invalid_request (tùy loại lỗi)"]
    B -->|Đã trích được token| V["JWT decoder hoặc opaque introspector"]
    V --> G{"Token được xác thực?"}
    G -->|Không| IT["401 invalid_token"]
    G -->|Có| P{"Có đủ quyền?"}
    P -->|Không| NO["403 insufficient_scope / access denied"]
    P -->|Có| O["Kiểm tra tài nguyên/tenant rồi xử lý"]
```

Sơ đồ là mô hình logic. Trong Spring Security, nhiều điều kiện được kiểm tra bởi các filter khác nhau và thứ tự xử lý phụ thuộc cấu hình. Vì vậy có request được từ chối ở **authentication filter trước khi rule `authorizeHttpRequests` chạy**.

### 2.1. Không phải chuỗi Bearer nào cũng là JWT

Bearer scheme chỉ cho biết cách trình credential: **bên nắm giữ token có thể trình token** để truy cập tài nguyên theo chính sách. Token có thể là:

- **JWT access token:** thường có ba phần JWS Compact, được Resource Server xác minh bằng `JwtDecoder`.
- **Opaque access token:** một chuỗi không có cấu trúc để API đọc trực tiếp, được kiểm tra qua introspection endpoint hoặc cơ chế tin cậy tương đương.

Dấu chấm trong token không tự chứng minh đây là JWT hợp lệ, và token không chứa dấu chấm không mặc nhiên là lỗi nếu Resource Server được thiết kế cho opaque token.

**Tránh dùng regex “JWT phải có ba phần” tại Controller để thay thế bộ xác thực token.** Hãy để đúng `JwtDecoder` hoặc `OpaqueTokenIntrospector` xử lý token theo hợp đồng.

### 2.2. Phân biệt authentication và authorization

Trong Spring Security:

- **Authentication** trả lời “token này có được chấp nhận, và principal là ai?”.
- **Authorization** trả lời “principal đã được xác thực này có được gọi endpoint và sử dụng tài nguyên không?”.

Token sai chữ ký thông thường không tạo `JwtAuthenticationToken` hợp lệ. Token đúng chữ ký nhưng thiếu `SCOPE_orders.read` có thể tạo Authentication hợp lệ rồi bị `AuthorizationFilter` từ chối.

## 3. Chuẩn Bearer: dùng `Authorization` như thế nào?

RFC 6750 mô tả OAuth 2.0 Bearer Token Usage. Cách khuyến nghị phổ biến để gửi access token là HTTP `Authorization` header:

```http
Authorization: Bearer <access-token>
```

Ví dụ:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  'https://orders.example.com/api/orders/42'
```

`ACCESS_TOKEN` phải là một access token thật; đây chỉ là lệnh minh họa.

### 3.1. Phần “Bearer” là authentication scheme

`Bearer` là tên scheme trong `Authorization`. Nó không phải một phần của chuỗi access token. Client cần đặt token sau scheme theo cú pháp phù hợp.

```text
Authorization header:
    Bearer eyJhbGciOi...

Scheme:
    Bearer

Credential:
    eyJhbGciOi...
```

Một Client tự thêm prefix `Bearer` vào **giá trị token đã lưu có sẵn prefix**, rồi tiếp tục tạo header `Authorization: Bearer Bearer ...`, thường sẽ tạo header không hợp lệ.

Không đưa dấu ngoặc kép quanh token như một phần credential:

```http
Authorization: Bearer "eyJhbGciOi..."
```

Đó không phải cú pháp Bearer thông thường mà `DefaultBearerTokenResolver` mong đợi.

### 3.2. Bearer credential có quy tắc ký tự riêng

Theo cú pháp Bearer token của RFC 6750, chuỗi `b64token` có thể chứa các ký tự chữ, số và một số ký tự như `-`, `.`, `_`, `~`, `+`, `/`, với phần padding `=` theo quy tắc. Điều này mô tả **cách truyền credential**, không bảo đảm chuỗi đó là JWT hợp lệ hay một token được AS cấp.

Một token dạng:

```text
abc.def.ghi
```

có thể vượt qua bước trích xuất Bearer header nhưng thất bại ở `JwtDecoder` vì không phải JWS hợp lệ.

Ngược lại:

```text
abc def
```

có dấu cách nội bộ, nên là một ví dụ về credential không hợp lệ theo cú pháp Bearer thông dụng.

### 3.3. Không đặt access token vào URL để “khắc phục” header lỗi

Ví dụ nên tránh:

```http
GET /api/orders/42?access_token=real-secret-token HTTP/1.1
```

Token trong URL có nguy cơ xuất hiện ở:

- Access logs và reverse proxy logs.
- Browser history.
- Monitoring/analytics.
- Cache hoặc đường dẫn được chia sẻ.
- Các hệ thống trung gian xử lý URL.

RFC 6750 có mô tả phương thức truyền qua query hoặc form body trong những điều kiện riêng, nhưng **`DefaultBearerTokenResolver` thông thường không bật query/form token support mặc định**. Trong ứng dụng hiện đại, nên dùng `Authorization: Bearer ...` qua HTTPS.

Nếu hệ thống phải tương thích một Client cũ, hãy cân nhắc rủi ro trước khi bật phương thức khác; không bật nhận query token chỉ để xử lý một HTTP request sai.

## 4. Trường hợp thứ nhất: request thiếu token

### 4.1. Endpoint protected không có Authorization header

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
```

Một response điển hình:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Mã `401 Unauthorized` trong HTTP ở đây có nghĩa request chưa cung cấp thông tin xác thực được chấp nhận cho tài nguyên bảo vệ; nó **không** có nghĩa token đã được đọc rồi xác minh sai.

`WWW-Authenticate` là **challenge** nói cho Client biết cơ chế xác thực có thể sử dụng. Theo OAuth Bearer, challenge thường chứa scheme `Bearer`; khi server có realm được cấu hình, có thể là:

```http
WWW-Authenticate: Bearer realm="orders-api"
```

### 4.2. Tại sao thiếu token thường không có `error="invalid_token"`?

RFC 6750 khuyến nghị **không đưa mã lỗi hoặc thông tin lỗi cụ thể** khi request đơn giản là chưa có thông tin xác thực. Một request không có token chưa chứng minh rằng có token nào sai.

So sánh:

```http
# Không gửi token:
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

với:

```http
# Đã gửi token nhưng token bị từ chối:
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

**Không tự yêu cầu `error="invalid_token"` trong test cho mọi HTTP 401.** Thiếu credential và credential không hợp lệ có ý nghĩa khác nhau.

### 4.3. Endpoint công khai có thể không cần token

Nếu cấu hình:

```java
.requestMatchers("/api/public/**").permitAll()
```

thì request:

```http
GET /api/public/ping HTTP/1.1
```

thường được cho phép qua bước authorization, dù không có Bearer token. Status cuối cùng phụ thuộc Controller hoặc static resource tương ứng.

Tuy nhiên, **`permitAll` không tắt Bearer authentication filter**. Nếu một Client gửi `Authorization: Bearer <invalid-token>` đến endpoint công khai, filter có thể nhận token và trả `401` trước khi đến rule `permitAll`. Đây không nhất thiết là lỗi cấu hình.

Nếu nghiệp vụ yêu cầu public route hoàn toàn không xử lý Bearer token, có thể tách một `SecurityFilterChain` riêng không bật Resource Server cho route đó, nhưng phải quản lý cẩn thận matcher, thứ tự và các filter khác.

### 4.4. Header dùng scheme khác có thể được coi là “không có Bearer token”

Ví dụ:

```http
Authorization: Basic dXNlcjpwYXNz
```

Với một Resource Server chỉ cấu hình Bearer authentication, bộ giải quyết Bearer token thường **không xem header Basic là Bearer token**. Nếu endpoint protected cần Bearer token, kết quả vẫn có thể là `401` với Bearer challenge.

Không nên mặc định mọi Authorization header không bắt đầu bằng Bearer đều là `invalid_request`. Nó còn tùy hệ thống có hỗ trợ scheme khác hoặc filter nào đang xử lý request.

## 5. Trường hợp thứ hai: cách gửi Bearer token sai định dạng

### 5.1. Cú pháp header không hợp lệ

Một số request minh họa:

```http
Authorization: Bearer abc def
```

```http
Authorization: Bearer "abc.def.ghi"
```

```http
Authorization: Bearer
```

Các chuỗi trên **không phải một Bearer credential theo cú pháp header thông dụng**. Khi resolver nhận diện đây là nỗ lực trình Bearer credential nhưng không thể diễn giải đúng, nó có thể ném `OAuth2AuthenticationException` với lỗi Bearer `invalid_request`.

Phản hồi thường gặp:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
```

Tuy nhiên, cách resolver đối xử với **header rỗng hoàn toàn**, khoảng trắng, nhiều header hoặc ký tự lạ có thể khác nhau theo phiên bản hoặc triển khai. Hãy viết test cho cú pháp thực tế của Client thay vì chỉ dựa vào một ví dụ mẫu.

### 5.2. `invalid_request` khác `invalid_token`

Hai lỗi có nguồn gốc khác nhau:

**`invalid_request`**: Bearer credential được trình không đúng quy tắc request/transport, ví dụ thiếu tham số bắt buộc theo kiểu truyền được hỗ trợ, tham số lặp, hoặc kết hợp nhiều phương thức truyền token trong một request.

**`invalid_token`**: Resource Server đã có một chuỗi token để xác thực, nhưng token đó không hợp lệ cho request/API vì hết hạn, bị thu hồi, sai chữ ký hoặc những điều kiện xác thực token khác không đạt.

Ví dụ:

```text
Authorization: Bearer abc def
  → lỗi cú pháp trình credential
  → có thể 400 invalid_request

Authorization: Bearer abc.def.ghi
  → credential có thể được trích xuất
  → JWT decoder thấy token sai
  → thường 401 invalid_token
```

Chỉ có **ba dấu chấm hay số đoạn của chuỗi JWT** không phải tiêu chí duy nhất để xác định lỗi ở lớp nào. Bộ xác thực mới biết token có hợp lệ theo profile hay không.

### 5.3. Gửi token qua nhiều cơ chế cùng lúc

RFC 6750 nêu nguyên tắc Client **không nên dùng nhiều phương thức truyền Bearer token trong cùng request**. Ví dụ một Client bật cả token trong header và query:

```http
GET /api/orders/42?access_token=some-token HTTP/1.1
Authorization: Bearer another-token
```

Với implementation cho phép nhận nhiều transport method, tình huống đó cần bị từ chối theo quy tắc tương ứng, thường là `invalid_request`. Nếu query transport không được hỗ trợ, ứng dụng có thể chỉ nhìn thấy Bearer header và bỏ qua `access_token` trong URL; **đừng suy ra duplicate-token detection luôn xảy ra khi một transport method bị tắt**.

Giải pháp đúng phía Client: **chỉ gửi một access token qua Authorization header**.

### 5.4. Đặc tính của `DefaultBearerTokenResolver`

Spring Security Servlet có `DefaultBearerTokenResolver` để trích Bearer token từ request. Theo cấu hình phổ biến:

- Tìm Bearer token ở `Authorization` header.
- Không nhận token trong query parameter hoặc form body nếu không được bật rõ ràng.
- Có thể báo lỗi nếu nhận thấy Bearer header có cú pháp không hợp lệ.
- Có thể tùy chỉnh header name/transport options cho một hợp đồng cụ thể.

Ví dụ cấu hình dùng resolver mặc định tường minh:

```java
@Bean
BearerTokenResolver bearerTokenResolver() {
    return new DefaultBearerTokenResolver();
}
```

Và gắn trong DSL phù hợp:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(bearerTokenResolver)
    .jwt(Customizer.withDefaults()))
```

Đây là các đoạn minh họa; cần inject bean trong `SecurityFilterChain` và import các lớp tương ứng. Trong phần lớn API dùng Bearer header thông thường, không cần tự khai một resolver mới.

### 5.5. Có nên bật query token để tương thích Client cũ?

`DefaultBearerTokenResolver` có API cho phép bật query parameter nếu ứng dụng thực sự yêu cầu:

```java
DefaultBearerTokenResolver resolver =
    new DefaultBearerTokenResolver();

// Chỉ minh họa khả năng cấu hình.
// KHÔNG bật chỉ để sửa client dùng sai Authorization header.
resolver.setAllowUriQueryParameter(true);
```

Nếu bật, cần đánh giá token leakage trong URL và các chính sách logging/caching. Tương tự, việc bật form body token chỉ thích hợp với ràng buộc phương thức và media type theo RFC/implementation.

**Khuyến nghị mặc định:** dùng HTTPS và `Authorization: Bearer <token>`; sửa Client gửi sai thay vì nới rộng cách nhận credential ngoài yêu cầu.

## 6. Trường hợp thứ ba: chuỗi token bị từ chối khi xác thực

### 6.1. Khi nào `invalid_token` xuất hiện?

Sau khi resolver lấy được token, Resource Server xác minh theo cơ chế đã cấu hình.

Với JWT access token, các điều kiện có thể khiến xác thực thất bại:

| Nhóm kiểm tra | Ví dụ thất bại | Ý nghĩa |
|---|---|---|
| Cú pháp JWT/JWS | Thiếu đoạn, Base64URL hoặc JSON/JOSE lỗi | Không thể phân tích token hợp lệ |
| Chữ ký | Chữ ký không khớp khóa tin cậy | Dữ liệu token không được xác thực |
| Thuật toán | Token dùng thuật toán không được cho phép | Không đáp ứng policy ký |
| Khóa ký | `kid` không tìm thấy trong JWKS tin cậy | Không có khóa hợp lệ để xác minh |
| Thời hạn | `exp` đã qua | Token hết hạn |
| Thời điểm hiệu lực | `nbf` ở tương lai | Token chưa được sử dụng |
| Issuer | `iss` khác issuer được cấu hình | Token từ nhà phát hành không được phép |
| Audience | `aud` không có `orders-api` khi API yêu cầu | Token dành cho Resource Server khác |
| Token type/profile | ID token hoặc `typ` không phù hợp hợp đồng access token | Token sai mục đích |
| Claim contract | Thiếu claim bắt buộc hoặc sai kiểu theo policy | Không đáp ứng điều kiện xác thực token |

Với một JWT bị từ chối, response thường là:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Kết nối tới JWKS thất bại do mạng hoặc lỗi cấu hình decoder **không nhất thiết đồng nghĩa token thực sự không hợp lệ**; tùy exception handling, Resource Server có thể trả lỗi server. Không nên gộp mọi lỗi kết nối IdP thành “token giả”.

### 6.2. Sai chữ ký không thể được “sửa” bằng cách đổi payload

Nếu bạn lấy JWT đã được ký rồi sửa `scope` từ `profile.read` thành `orders.read`, chữ ký cũ sẽ không còn hợp lệ.

```text
JWT trước:
  payload: scope=profile.read
  signature: valid

JWT sau khi sửa thủ công:
  payload: scope=orders.read
  signature: unchanged
  → signature verification fails
```

Request với token sửa thủ công thường nhận **`401 invalid_token`**, chứ không phải `403 insufficient_scope`. Để kiểm tra nhánh thiếu scope, phải dùng token **được cấp hợp lệ nhưng không có scope đó** hoặc mô phỏng Authentication trong authorization test.

### 6.3. Token sai issuer hoặc audience không được dùng nhầm

Ví dụ JWT payload minh họa:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "sub": "user-417"
}
```

Nếu API là `orders-api` và có audience validator, token phải bị từ chối dù issuer, chữ ký và scope có thể hợp lệ. Nó không được cấp cho API hiện tại.

Trường hợp **đúng issuer, đúng chữ ký nhưng sai audience** là một lỗi token-level validation, thường trả **401** theo cấu hình validator.

Chỉ cấu hình `issuer-uri` không nên được hiểu là mọi phiên bản/configuration đã tự kiểm tra audience. Audience phải được ràng buộc theo hợp đồng API.

### 6.4. `kid` và JWKS không mở rộng trust

Token có thể khai:

```json
{
  "alg": "RS256",
  "kid": "unknown-key",
  "jku": "https://keys.attacker.example/jwks.json"
}
```

Nếu `kid` không có trong JWKS đã được phê duyệt, Resource Server có thể làm mới JWKS theo chính sách hoặc từ chối token. **Không tự tải khóa từ `jku` do token đưa vào** để cố làm token hợp lệ, vì Client có thể tự chọn nguồn khóa.

Lỗi không xác minh được chữ ký/khóa vẫn thuộc **authentication failure**, không phải thiếu `SCOPE_`.

## 7. Opaque token bị từ chối: `active=false` và lỗi introspection

### 7.1. Introspection response

Một Resource Server dùng opaque token có thể gửi token tới introspection endpoint tin cậy:

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.com
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>
```

Authorization Server có thể trả:

```json
{
  "active": false
}
```

Response này nói rằng theo chính sách introspection hiện tại, token không được chấp nhận. Spring Security thường xử lý nó như **authentication failure** và trả `401` cho Client gọi API.

Một token không hoạt động có thể đã hết hạn, bị thu hồi, không tồn tại, hoặc không được Resource Server đang introspect chấp nhận. Không nên đưa những nguyên nhân nội bộ đó vào HTTP response cho bên ngoài.

### 7.2. `active=true` chưa bảo đảm có quyền với API

Phản hồi khác:

```json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "profile.read",
  "sub": "user-417"
}
```

Token có thể qua bước introspection và audience validation, nhưng không có scope `orders.read`. Nếu endpoint yêu cầu `SCOPE_orders.read`, kết quả thường là `403`, không phải `401`.

Nếu `active=true` nhưng audience là `billing-api` và hợp đồng yêu cầu `orders-api`, API phải từ chối theo token-level validation hoặc cơ chế resource-binding được AS bảo đảm. **`active` không tự thay audience/authorization policy.**

### 7.3. Introspection endpoint lỗi khác token bị từ chối

Cần tách hai kết quả:

**AS xử lý thành công và trả token inactive:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

**AS không thể xử lý request introspection:** TLS lỗi, mạng timeout, credential introspection sai, AS trả 5xx hoặc giao thức không đúng.

Trường hợp thứ hai là vấn đề **khả dụng/cấu hình của hệ thống xác thực**, không thể khẳng định access token của Client thực sự sai. Resource Server phải từ chối truy cập một cách an toàn khi không xác minh được, nhưng status cuối cùng có thể là lỗi server thay vì `401 invalid_token`.

**Không “fail open”** bằng cách cho mọi opaque token đi qua khi AS không sẵn sàng.

## 8. Quy tắc HTTP: `400`, `401`, `403` có ý nghĩa gì?

### 8.1. `400 Bad Request` — Bearer request không hợp lệ

Theo Bearer error model, `invalid_request` có thể dùng khi request mang thông tin xác thực Bearer sai cú pháp hoặc sử dụng nhiều phương thức gửi token trái quy tắc.

Response minh họa:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
```

Không phải tất cả lỗi parse HTTP đều đi qua Bearer entry point: Servlet container, proxy hoặc web server có thể từ chối request trước khi Spring Security xử lý.

### 8.2. `401 Unauthorized` — cần hoặc không chấp nhận Authentication

Một request thiếu credential thường nhận:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

Một token bị từ chối thường nhận:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

`401` ở đây là trạng thái HTTP lịch sử có tên “Unauthorized”, nhưng về mặt ngữ nghĩa thường có nghĩa **thiếu hoặc chưa có thông tin xác thực được chấp nhận**. Không nhất thiết có một token đã được nhận rồi thất bại.

### 8.3. `403 Forbidden` — xác thực thành công, nhưng quyền chưa đủ

Token có thể hợp lệ và tạo Authentication, nhưng thiếu authority:

```text
GrantedAuthority:
  SCOPE_profile.read

Endpoint requires:
  SCOPE_orders.read
```

Phản hồi Bearer có thể là:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

Tham số `scope` trong challenge, nếu được dùng, có thể cung cấp gợi ý phạm vi cần thiết:

```http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.read"
```

Không phải handler mặc định nào cũng tự biết hoặc đưa chính xác required scope của mọi endpoint vào header. **Không bịa một scope cụ thể trong challenge nếu ứng dụng không có căn cứ tính toán.**

### 8.4. Bảng quyết định nhanh

| Request | Tình trạng | Phản hồi điển hình |
|---|---|---|
| Protected, không Authorization header | Chưa xác thực | `401` + `WWW-Authenticate: Bearer` |
| Protected, `Authorization: Basic ...`, chỉ bật Bearer | Không có Bearer credential phù hợp | `401` + Bearer challenge |
| Bearer header sai cú pháp | `invalid_request` | `400` + Bearer error |
| Bearer token trích xuất được nhưng sai JWT | `invalid_token` | `401` + Bearer error |
| JWT hết hạn/sai chữ ký/sai issuer | `invalid_token` | `401` |
| JWT sai audience theo policy | Không đáp ứng token validation | `401` |
| Opaque introspection `active=false` | Token không hoạt động | `401` |
| JWT/opaque hợp lệ nhưng thiếu scope | Không đủ quyền endpoint | `403` |
| Token hợp lệ và đủ scope nhưng sai owner/tenant | Không đủ quyền tài nguyên | `403` hoặc `404` theo policy |
| Introspection endpoint timeout | Không xác minh được | Từ chối an toàn; status phụ thuộc lỗi/handler |
| Endpoint công khai không token | `permitAll` | Đi tiếp Controller; có thể `200` |
| Endpoint công khai có Bearer token hỏng | Authentication filter có thể xử lý trước `permitAll` | Có thể `401` |

Các kết quả ở bảng là **mô hình dự kiến để thiết kế và kiểm thử**, không phải cam kết cho mọi Spring Security version hay custom filter chain.

## 9. `WWW-Authenticate`: đọc Bearer challenge cho đúng

### 9.1. Không phải mọi response lỗi đều có JSON body

Theo HTTP authentication và RFC 6750, `WWW-Authenticate` là header quan trọng cho biết cơ chế xác thực và thông tin lỗi Bearer. Client không nên chỉ parse body JSON rồi bỏ qua header.

Một request thiếu token có thể nhận:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Length: 0
```

Một token bị từ chối có thể nhận:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token", error_description="Token validation failed"
```

Body có thể rỗng hoặc do application/gateway custom. Nếu xây API error JSON riêng, vẫn cần bảo toàn ngữ nghĩa `WWW-Authenticate` khi phản hồi Bearer challenge.

### 9.2. Các tham số challenge phổ biến

| Tham số | Ý nghĩa | Lưu ý |
|---|---|---|
| `realm` | Tên không gian bảo vệ/resource | Do server khai báo, không phải access token |
| `error` | Mã lỗi Bearer | Thường là `invalid_request`, `invalid_token`, `insufficient_scope` |
| `error_description` | Mô tả ngắn cho Client | Không tiết lộ stack trace, token hoặc thông tin bảo mật |
| `error_uri` | URI tới tài liệu giải thích lỗi | Chỉ dùng địa chỉ tài liệu đáng tin, không nhúng token |
| `scope` | Scope cần thiết cho protected resource trong bối cảnh thích hợp | Không mặc định mọi response `403` đều có tham số này |

### 9.3. Không nhầm `realm` với `issuer`

Ví dụ:

```http
WWW-Authenticate: Bearer realm="orders-api"
```

`orders-api` chỉ là **realm/challenge parameter** do Resource Server đặt. Nó **không phải** `iss` trong access token, không phải OAuth Client ID và không phải chứng cứ token được cấp cho đúng audience.

### 9.4. Thận trọng với error description

Không nên gửi:

```http
WWW-Authenticate: Bearer error="invalid_token", error_description="Private key kid=prod-signing-2026 missing; token=eyJ..."
```

Mô tả này tiết lộ dữ liệu không cần thiết. Response an toàn nên đủ để Client biết cần cung cấp token hợp lệ hoặc xin quyền phù hợp, còn chi tiết chẩn đoán thuộc log nội bộ có kiểm soát.

Không đặt refresh token, session secret, JWT gốc hoặc introspection Client secret trong header/body lỗi.

## 10. Spring Security xử lý Bearer request ở những thành phần nào?

### 10.1. Luồng Servlet tổng quát

Một ứng dụng Resource Server Servlet có thể đi qua các thành phần:

```mermaid
flowchart TD
    HTTP["HTTP request"] --> FCP["FilterChainProxy chọn SecurityFilterChain"]
    FCP --> BTF["BearerTokenAuthenticationFilter"]
    BTF --> RES{"BearerTokenResolver"}
    RES -->|Không có Bearer token| NEXT["Đi tiếp filter chain"]
    RES -->|Sai request syntax| EP["AuthenticationEntryPoint"]
    RES -->|Đã lấy token| AM["AuthenticationManager"]
    AM --> JP["JwtAuthenticationProvider + JwtDecoder<br/>hoặc OpaqueTokenAuthenticationProvider"]
    JP -->|AuthenticationException| FAIL["FailureHandler → AuthenticationEntryPoint"]
    JP -->|Thành công| CTX["SecurityContext có Authentication"]
    NEXT --> AUTHZ["AuthorizationFilter và policy"]
    CTX --> AUTHZ
    AUTHZ -->|Không đủ quyền| AD["AccessDeniedHandler / ExceptionTranslationFilter"]
    AUTHZ -->|Đạt| CTRL["Controller → Service"]
```

Thứ tự filter chính xác và error handling có thể thay đổi theo phiên bản/configuration, nhưng ranh giới chính không đổi:

- **Resolver** xử lý cách gửi credential.
- **Authentication provider/decoder/introspector** quyết định token được chấp nhận hay không.
- **Authorization** quyết định token đã xác thực có quyền gọi tài nguyên hay không.

### 10.2. `BearerTokenAuthenticationFilter`

Filter này thường:

1. Nhờ `BearerTokenResolver` tìm Bearer token trong request.
2. Nếu không có token, cho request đi tiếp; một protected rule ở phía sau có thể yêu cầu Authentication và trả `401`.
3. Nếu resolver ném lỗi, kích hoạt xử lý authentication failure thích hợp.
4. Nếu có token, gửi yêu cầu xác thực tới `AuthenticationManager`.
5. Nếu xác thực thất bại, gọi failure handler/entry point.
6. Nếu thành công, lưu Authentication trong SecurityContext theo cơ chế cấu hình rồi tiếp tục.

Một điểm quan trọng: **token không hợp lệ có thể bị từ chối ngay trong `BearerTokenAuthenticationFilter`**, tức trước khi request đi tới `AuthorizationFilter`.

### 10.3. `ExceptionTranslationFilter` và Bearer failure

`ExceptionTranslationFilter` là cầu nối từ những `AuthenticationException` hoặc `AccessDeniedException` phát sinh phía sau nó sang HTTP response. Với request chưa xác thực đi tới một protected authorization rule, nó thường gọi `AuthenticationEntryPoint`.

Tuy nhiên, với token bị từ chối ngay trong Bearer authentication filter, lỗi có thể được xử lý trực tiếp bởi cơ chế failure handling của filter — **không nhất thiết do `ExceptionTranslationFilter` bắt rồi xử lý**.

Điều này giải thích vì sao custom `@ControllerAdvice` cho Controller không luôn bắt được lỗi JWT/opaque token: request thường bị từ chối ở Servlet security filters **trước khi đến Controller**.

### 10.4. `BearerTokenAuthenticationEntryPoint`

Spring Security cung cấp `BearerTokenAuthenticationEntryPoint` để tạo response Bearer challenge khi xác thực không thành công hoặc chưa có Authentication phù hợp.

Nó có thể được cấu hình realm và xử lý các thông tin Bearer error tương ứng.

### 10.5. `BearerTokenAccessDeniedHandler`

`BearerTokenAccessDeniedHandler` được dùng trong bối cảnh Bearer Resource Server khi Authentication có mặt nhưng request bị từ chối quyền. Với token đã được xác thực qua Bearer, nó có thể sinh `403` và Bearer challenge `insufficient_scope`.

Không nên viết custom AccessDeniedHandler trả `invalid_token` cho mọi trường hợp thiếu scope. Làm vậy khiến Client hiểu nhầm rằng phải đổi token vì token không xác thực được, trong khi vấn đề là **quyền được cấp chưa đủ**.

### 10.6. Không đồng nhất mọi `AccessDeniedException` với một loại lỗi

`AccessDeniedException` có thể phát sinh vì:

- Thiếu scope/authority của endpoint.
- Không có role.
- Không có quyền đối với tenant hoặc bản ghi.
- Method security từ chối.
- Một authorization manager tùy biến từ chối.

Thông tin `insufficient_scope` phù hợp khi thiếu quyền OAuth scope, nhưng không nhất thiết là mô tả tốt cho mọi lỗi nghiệp vụ, nhất là object-level authorization. Chọn error details theo chính sách API; đừng tiết lộ owner/tenant của tài nguyên ngoài quyền.

## 11. Cấu hình ứng dụng Spring Boot Resource Server với JWT

### 11.1. Dependency Gradle

Ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Spring Boot plugin và phiên bản Java/Spring Security phải được cấu hình phù hợp với project thật.

### 11.2. `issuer-uri` cho JWT access token

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
```

Địa chỉ issuer là ví dụ, không phải Authorization Server thực đang chạy. Spring Security có thể dùng metadata/JWKS của issuer tin cậy để xác minh JWT và áp dụng validator issuer/thời gian.

**Bảo đảm ràng buộc audience:** Token của `billing-api` không thể mặc nhiên được dùng tại `orders-api` chỉ vì cả hai dùng cùng issuer. Nếu yêu cầu `aud=orders-api`, cần cấu hình audience validator hoặc cơ chế tương đương theo phiên bản dự án.

### 11.3. SecurityFilterChain: API công khai và API cần scope

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Ở đây:

- `/api/public/**` không đòi Authentication ở bước authorization.
- `GET /api/orders/**` cần `SCOPE_orders.read`.
- `POST /api/orders` cần `SCOPE_orders.write`.
- `anyRequest().denyAll()` hạn chế endpoint chưa có policy.
- `oauth2ResourceServer(...jwt(...))` bật cơ chế nhận Bearer JWT.
- `STATELESS` phù hợp với API không dùng session để xác thực Bearer request.

Ví dụ `csrf.disable()` chỉ phù hợp khi API nhận Bearer token qua header và **không sử dụng cookie làm credential được trình duyệt tự động gửi**. Nếu ứng dụng dùng session/cookie, phải đánh giá CSRF riêng.

### 11.4. Controller tối thiểu

```java
package com.example.orders;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/orders/{orderId}")
    public Map<String, String> order(
            @PathVariable String orderId,
            @AuthenticationPrincipal Jwt jwt) {

        return Map.of(
            "orderId", orderId,
            "subject", jwt.getSubject());
    }
}
```

Controller chỉ minh họa sự khác biệt giữa public và protected route. **Không dùng nguyên trạng làm API đơn hàng production**: còn phải xác minh quyền của principal với đơn hàng `orderId`, tenant và các thuộc tính được phép trả.

Đoạn này không khai báo handler `POST /api/orders`. Rule authorization cho POST có thể tồn tại dù chưa có Controller tương ứng; khi đã xác thực/đủ quyền nhưng route không được map, có thể nhận `404` hoặc `405` tùy request.

## 12. Cấu hình realm và giữ Bearer error handler đúng mục đích

### 12.1. Dùng entry point/handler có sẵn

Khi cần realm cố định để Client nhận diện không gian bảo vệ, có thể cấu hình:

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

@Configuration
public class BearerErrorConfig {

    @Bean
    BearerTokenAuthenticationEntryPoint bearerEntryPoint() {
        BearerTokenAuthenticationEntryPoint entryPoint =
            new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");
        return entryPoint;
    }

    @Bean
    BearerTokenAccessDeniedHandler bearerAccessDeniedHandler() {
        BearerTokenAccessDeniedHandler handler =
            new BearerTokenAccessDeniedHandler();
        handler.setRealmName("orders-api");
        return handler;
    }
}
```

Cấu hình cho Resource Server DSL với các bean đã được inject:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerAccessDeniedHandler)
    .jwt(Customizer.withDefaults()))
```

Đây là đoạn thay thế phần `oauth2ResourceServer` trong `ApiSecurityConfig` của mục trước. Trong project, cần constructor injection hoặc tham số bean method cho `bearerEntryPoint` và `bearerAccessDeniedHandler`.

Nếu ứng dụng có nhiều `SecurityFilterChain`, cần áp dụng entry point/handler phù hợp với chain API thay vì khiến form-login web chain trả Bearer challenge ngoài ý định.

### 12.2. Không đổi `401` thành `200` để “Client không báo lỗi”

Một số hệ thống muốn trả JSON đồng nhất, chẳng hạn:

```json
{
  "code": "TOKEN_INVALID",
  "message": "Access token is not accepted"
}
```

Có thể bổ sung JSON body cho authentication error theo API contract, nhưng **HTTP status vẫn nên phản ánh lỗi thực** và `WWW-Authenticate` nên được giữ đúng khi áp dụng Bearer scheme.

Không dùng:

```http
HTTP/1.1 200 OK

{"success":false,"error":"TOKEN_INVALID"}
```

cho một request protected token không hợp lệ. HTTP 200 có thể khiến Client, gateway, monitoring và cache hiểu nhầm request thành công.

### 12.3. Cẩn thận khi custom `AuthenticationEntryPoint`

Nếu tự viết `AuthenticationEntryPoint` để trả JSON:

1. Giữ HTTP `401` hoặc `400` phù hợp với lỗi Bearer thực tế.
2. Giữ `WWW-Authenticate` challenge theo tiêu chuẩn.
3. Không công bố raw token hoặc chi tiết cryptographic/AS.
4. Không trả stack trace từ exception vào Client.
5. Chỉ thực hiện response writing một lần; tránh gửi thêm body sau khi response đã commit.
6. Bảo đảm cả lỗi resolver và lỗi decoder đều đi qua đường xử lý dự kiến.

Trong nhiều hệ thống, dùng entry point có sẵn là lựa chọn ít rủi ro hơn custom hoàn toàn chỉ để thay đổi một JSON message.

## 13. Audience validator: token đúng cú pháp vẫn có thể bị từ chối

Một JWT có thể được xác minh chữ ký, thời hạn và issuer đúng nhưng `aud` không dành cho `orders-api`.

Ví dụ thêm audience validator trong Spring Security:

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String expectedIssuer =
            "https://id.example.com/realms/shop";
        String expectedAudience = "orders-api";

        NimbusJwtDecoder decoder =
            (NimbusJwtDecoder)
                JwtDecoders.fromIssuerLocation(expectedIssuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(expectedAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Invalid audience",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(expectedIssuer),
                audience));

        return decoder;
    }
}
```

Bean decoder này cho phép kiểm tra audience cùng các validator issuer/thời hạn được khai báo. Nó cần phù hợp với phiên bản Spring Security đang dùng. Nếu một decoder tùy biến được tạo, hãy chắc chắn **không bỏ qua các validator mặc định cần thiết** khi bổ sung audience.

Với token sai audience, API thường trả `401 invalid_token`. Với token đúng audience nhưng thiếu scope, API thường trả `403 insufficient_scope`. Hai trường hợp này cần được kiểm thử riêng.

## 14. Cấu hình opaque token và sự khác biệt của lỗi

Nếu Authorization Server cấp opaque token, dùng cấu hình introspection thay cho JWT decoder.

Ví dụ Spring Boot:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: INTROSPECTION_CLIENT_ID_FROM_SECRET_STORE
          client-secret: INTROSPECTION_CLIENT_SECRET_FROM_SECRET_STORE
```

Tên credential là placeholder, không phải bí mật thật. Khi triển khai, dùng biến môi trường hoặc secret manager thích hợp thay vì ghi Client secret trực tiếp vào source code.

Trong `SecurityFilterChain`:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Các nhánh quan trọng:

- Không token → protected endpoint thường `401`.
- Bearer request malformed → resolver có thể trả `400 invalid_request`.
- Token opaque được introspection và nhận `active=false` → thường `401 invalid_token`.
- `active=true` nhưng audience không phù hợp hợp đồng → API phải từ chối qua policy thích hợp.
- `active=true` đúng audience nhưng thiếu scope → thường `403`.
- AS introspection bị timeout/TLS lỗi → **sự cố xác thực upstream**, không được fail open.

**Không dùng `JwtDecoder` cho opaque token chỉ vì một chuỗi bất kỳ có dấu chấm.** Resource Server phải biết cơ chế token theo hợp đồng của AS.

## 15. Phân quyền endpoint và quyền trên tài nguyên

### 15.1. Scope được ánh xạ thành authority

Với JWT:

```json
{
  "scope": "orders.read profile.read"
}
```

hoặc introspection response:

```json
{
  "active": true,
  "scope": "orders.read profile.read"
}
```

theo cơ chế mapping thông dụng của Spring Security, có thể nhận:

```text
SCOPE_orders.read
SCOPE_profile.read
```

Rule:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

chỉ kiểm tra có authority `SCOPE_orders.read` hay không. Không phải `orders.read` được tự động chuyển thành quyền xem **mọi đơn hàng mọi tenant**.

### 15.2. Thiếu scope thường là 403, không phải 401

Token:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "aud": ["orders-api"],
  "sub": "user-417",
  "scope": "profile.read"
}
```

Nếu hợp lệ theo mọi validator token-level, nó có thể trở thành Authentication nhưng bị `hasAuthority("SCOPE_orders.read")` từ chối. Đây là **authorization failure** và thường trả `403`.

Một test thiếu scope phải dùng **token thật được cấp với scope thiếu**, hoặc giả lập Authentication đã xác thực, không sửa chuỗi JWT đã ký.

### 15.3. Có scope vẫn cần kiểm tra tenant và owner

Với request:

```http
GET /api/tenants/tenant-beta/orders/order-42 HTTP/1.1
Authorization: Bearer <token-of-tenant-alpha>
```

dù token còn hạn và có `orders.read`, API không được trả order của Beta nếu caller chỉ được truy cập Alpha.

Repository nên giới hạn truy vấn:

```sql
SELECT id, tenant_id, owner_subject, amount
FROM orders
WHERE id = :order_id
  AND tenant_id = :verified_tenant_id
  AND owner_subject = :verified_subject;
```

Các giá trị `verified_tenant_id` và `verified_subject` phải xuất phát từ Authentication/nguồn quyền tin cậy. Không lấy `tenant_id` chỉ từ URL/header do Client tự khai rồi dùng như quyền.

Nếu không tìm thấy bản ghi trong phạm vi quyền, API có thể trả `404` để tránh tiết lộ tài nguyên ngoài quyền tồn tại. Đây là chính sách **object-level authorization**, khác với lỗi Bearer token.

## 16. Lỗi trên endpoint công khai: vì sao `permitAll` đôi khi vẫn 401?

Xét cấu hình:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated())
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()))
```

Bốn request có thể có hành vi khác nhau:

| Request tới `/api/public/ping` | Bearer authentication filter | Kết quả điển hình |
|---|---|---|
| Không có Authorization header | Không có token để xác thực | Endpoint được phép |
| Bearer token hợp lệ | Có thể xác thực token | Endpoint được phép |
| Bearer token bị decoder từ chối | Authentication thất bại trước authorization | Có thể `401` |
| Bearer header sai cú pháp | Resolver có thể phát lỗi | Có thể `400` |

Điều này giải thích vì sao một API public có `permitAll` nhưng Client gửi credential hỏng vẫn nhận lỗi xác thực.

### 16.1. Khi nào cần tách SecurityFilterChain?

Nếu yêu cầu là public endpoint **không cố xác thực Bearer token**, có thể thiết kế chain riêng:

```java
@Bean
@Order(1)
SecurityFilterChain publicApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/public/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain protectedApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Cần import `@Order` và các class liên quan. Đây là ví dụ thay thế để minh họa chain selection, không phải cấu hình đủ mọi scope, CSRF, CORS hoặc catch-all cho ứng dụng production. Nếu có endpoint ngoài `/api/**`, phải thêm chain/policy bao phủ thích hợp.

**Spring Security chọn chain đầu tiên khớp**, không gộp filter của hai chain. Một public chain riêng có thể cho request đi tiếp dù header Bearer không hợp lệ, vì nó không bật Resource Server Bearer filter. Đổi lại, cần hiểu rõ các filter bảo mật nào đang có/không có ở public chain.

### 16.2. Đừng dùng `web.ignoring()` để sửa mọi lỗi

Bỏ qua Spring Security hoàn toàn không giống `permitAll`. Khi ignore, những bảo vệ như security headers hoặc filter policy tương ứng có thể không được áp dụng. Với endpoint HTTP public, `permitAll` trong chain phù hợp thường là lựa chọn ít bất ngờ hơn.

## 17. CORS, reverse proxy và các lỗi trông giống lỗi token

### 17.1. Browser preflight thường không có Bearer token

Một frontend gọi API khác origin có thể gửi:

```http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://shop.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflight không phải request đọc đơn hàng thật và thường không gửi Bearer token. Nếu ứng dụng đòi Authentication trước khi xử lý CORS, browser có thể hiển thị **lỗi CORS**, dù token ở request thực tế là hợp lệ.

Cần cấu hình CORS đúng cho chain API và chỉ cho phép origin/method/header phù hợp. Không giải quyết bằng cách `permitAll()` toàn bộ API.

### 17.2. Gateway làm mất Authorization header

Một request ban đầu có:

```http
Authorization: Bearer <valid-token>
```

nhưng reverse proxy không chuyển header đến backend. Resource Server nhìn thấy **request thiếu token** và trả `401`.

Do đó, khi Client khẳng định “đã gửi token”, cần đối chiếu đường đi request qua gateway/proxy. Tuyệt đối không yêu cầu Client log token thật để chứng minh; có thể kiểm tra sự hiện diện của header, request ID và thông tin được che bí mật.

### 17.3. Web form login chain có thể trả 302 thay vì 401

Nếu ứng dụng có nhiều `SecurityFilterChain` và request API vô tình vào web form-login chain, thiếu token có thể dẫn tới:

```http
HTTP/1.1 302 Found
Location: /login
```

Đây có thể là dấu hiệu **chain selection** sai hơn là Bearer token sai. Kiểm tra `securityMatcher` và `@Order` trước khi custom entry point.

### 17.4. HTTPS phải được bảo vệ end-to-end

Bearer token là credential: ai nắm token có thể thử sử dụng nó. Nên truyền qua HTTPS từ Client đến gateway và trên những kết nối nội bộ theo policy. Không in token ở URL, log, error body hoặc monitoring.

Một HTTP 401 được trả đúng không giúp bảo vệ hệ thống nếu token đã bị lộ qua channel không an toàn.

## 18. Thực hành với curl: nhận diện 401, 400 và 403

Giả sử ứng dụng chạy tại `http://localhost:8080` trong môi trường phát triển, đã có Controller `/api/public/ping`, `/api/orders/42` và `SecurityFilterChain` theo mục 11. Trên môi trường thật cần HTTPS.

### 18.1. Không token ở endpoint public

```bash
curl -i 'http://localhost:8080/api/public/ping'
```

Nếu endpoint tồn tại và xử lý thành công, thường nhận `200 OK`.

### 18.2. Không token ở endpoint protected

```bash
curl -i 'http://localhost:8080/api/orders/42'
```

Kết quả thường:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Nếu có realm, header có thể là `Bearer realm="orders-api"`.

### 18.3. Bearer header sai cú pháp

```bash
curl -i \
  -H 'Authorization: Bearer abc def' \
  'http://localhost:8080/api/orders/42'
```

Với Bearer resolver thông dụng, dự kiến request bị xem là sai cú pháp và có thể trả `400 Bad Request` với `error="invalid_request"`.

Một HTTP intermediary có thể xử lý header trước backend; vì vậy cần quan sát thực tế nếu kết quả khác.

### 18.4. Chuỗi trông giống JWT nhưng không hợp lệ

```bash
curl -i \
  -H 'Authorization: Bearer abc.def.ghi' \
  'http://localhost:8080/api/orders/42'
```

Chuỗi này có thể được trích xuất từ header, nhưng không phải JWT có chữ ký hợp lệ. Với JWT decoder, thường nhận `401` và `invalid_token`.

### 18.5. Access token hết hạn

Nếu `EXPIRED_ACCESS_TOKEN` thực sự là token đã được AS ký và hết hạn:

```bash
curl -i \
  -H "Authorization: Bearer $EXPIRED_ACCESS_TOKEN" \
  'http://localhost:8080/api/orders/42'
```

Kết quả thường `401 invalid_token`. Không tự thay `exp` trong payload token đang có để mô phỏng expired token, vì điều đó sẽ phá chữ ký và không tách được nguyên nhân.

### 18.6. Token hợp lệ nhưng thiếu scope

Nếu `VALID_TOKEN_WITHOUT_ORDERS_READ` là token thật, đúng audience/issuer và còn hạn nhưng không có `orders.read`:

```bash
curl -i \
  -H "Authorization: Bearer $VALID_TOKEN_WITHOUT_ORDERS_READ" \
  'http://localhost:8080/api/orders/42'
```

Kết quả thường `403 Forbidden`. Đây là phép thử authorization, không phải token validation.

### 18.7. Token hợp lệ và đủ scope

```bash
curl -i \
  -H "Authorization: Bearer $VALID_TOKEN_WITH_ORDERS_READ" \
  'http://localhost:8080/api/orders/42'
```

Nếu token đúng issuer/audience, còn hạn, có `orders.read` và Controller demo hoạt động, có thể nhận:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":"42","subject":"user-417"}
```

Response chỉ là ví dụ, subject phụ thuộc token. Trong API thật còn cần ràng buộc tenant và quyền sở hữu.

### 18.8. Chú ý khi dùng curl

- Tham số `-i` hiển thị **response headers**, quan trọng để nhìn `WWW-Authenticate`.
- Đừng dùng `-L` khi muốn quan sát 302 do form login chain trả, vì nó sẽ theo redirect.
- Tránh dùng `-v` với token thật trong log/ticket vì nó có thể hiển thị Authorization header.
- Không dán token production hoặc secret introspection vào bản báo cáo lỗi.
- HTTP `localhost` chỉ dùng cho lab; môi trường thật cần HTTPS.
- Mọi biến token trong ví dụ đều giả định đã được chuẩn bị hợp lệ từ AS/lab, không phải giá trị có thể tự gõ tùy ý.

## 19. Test authorization và test decoder là hai mục tiêu riêng

### 19.1. MockMvc với `spring-security-test`

Một test có thể xác nhận endpoint yêu cầu Authentication:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BearerAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt()
                    .jwt(token -> token.subject("user-417"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedWithScopePassesEndpointRule() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt()
                    .jwt(token -> token.subject("user-417"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }
}
```

Các test dùng `with(jwt())` mô phỏng một `Authentication` JWT hợp lệ phục vụ **authorization tests**; chúng **không thực sự gọi `JwtDecoder` hay kiểm tra JWK/chữ ký/issuer/audience**.

Để tránh ứng dụng test tìm metadata của issuer ví dụ ở startup, project có thể cung cấp decoder/JWKS fixture phù hợp hoặc mock `JwtDecoder` trong test context tùy phiên bản Spring Boot. Không kết luận JWT validation đã chính xác chỉ vì các test mô phỏng principal thành công.

### 19.2. Test Bearer header sai cú pháp

Một phép thử khác đi qua HTTP filter:

```java
@Test
void malformedBearerHeaderIsRejected() throws Exception {
    mvc.perform(get("/api/orders/42")
            .header("Authorization", "Bearer abc def"))
        .andExpect(status().isBadRequest());
}
```

Trong cấu hình `DefaultBearerTokenResolver` thông thường, chuỗi này được xử lý như Bearer request không hợp lệ. Nếu ứng dụng custom resolver, cần xác nhận kết quả theo hợp đồng riêng.

### 19.3. Test JWT sai chữ ký hoặc hết hạn

Muốn xác nhận `JwtDecoder` thật từ chối:

- Chuẩn bị JWKS/public key thử nghiệm.
- Tạo JWT được ký bằng khóa hợp lệ và JWT ký bằng khóa không tin cậy.
- Tạo JWT hết hạn đã được **ký đúng** bằng khóa thử nghiệm.
- Tạo JWT đúng chữ ký nhưng sai issuer hoặc audience.
- Gửi request đi qua security filters và decoder thật.
- Kiểm tra `401` và không có Controller/business side effect.

Nếu chỉ gửi chuỗi `not-a-jwt`, bạn mới chứng minh parser/decoder từ chối token sai cấu trúc, chưa chứng minh validator audience hoặc thời hạn chạy đúng.

### 19.4. Test opaque introspection

Với opaque token, dùng mock introspection endpoint để trả:

```json
{"active":false}
```

và:

```json
{
  "active":true,
  "aud":["orders-api"],
  "scope":"profile.read",
  "sub":"user-417"
}
```

Sau đó kiểm tra `401` cho inactive token và `403` cho token active đúng audience nhưng thiếu scope, **nếu Resource Server đã cấu hình audience và authority mapping phù hợp**.

`with(opaqueToken())` của Spring Security Test thường mô phỏng Authentication, không tự chứng minh HTTP introspection đã được gọi hoặc `active=false` xử lý chính xác. Cần integration test hoặc test introspector riêng cho các điều kiện đó.

## 20. Điều tra lỗi theo từng giai đoạn

Khi gặp một response ngoài kỳ vọng, nên xác định trước request dừng ở bước nào.

### 20.1. Không có `WWW-Authenticate` dù endpoint protected trả 401

Có thể do:

- Một custom error handler thay thế Bearer entry point.
- Gateway/proxy thay đổi response.
- Request đi qua `SecurityFilterChain` khác.
- Ứng dụng trả `401` thủ công từ Controller.
- Một lỗi HTTP khác xảy ra trước Spring Security.

Không nên chỉ thêm header ở Controller mà chưa xác định filter chain và entry point thực tế.

### 20.2. Request thiếu token nhưng lại trả 403

Có thể do cấu hình custom authorization/error handler hoặc một cơ chế xác thực khác đang chạy. Cần kiểm tra `SecurityFilterChain` được chọn, Authentication hiện tại và cách `ExceptionTranslationFilter` quyết định entry point/AccessDeniedHandler.

### 20.3. Request có token bị sửa nhưng trả 403

Nếu token thực sự không hợp lệ mà vẫn tạo Authentication, cần xem decoder/introspection có chạy không và test có đang dùng `with(jwt())` hoặc một mock Authentication được cài sẵn không.

Đừng dựa vào `403` để kết luận JWT đã được xác minh; status phải được hiểu trong bối cảnh pipeline thực tế.

### 20.4. API thiếu token lại redirect tới `/login`

Điều này thường liên quan form-login entry point hoặc chain web đang được chọn. Nếu Resource Server cần Bearer challenge, hãy kiểm tra `securityMatcher`, `@Order` và `oauth2ResourceServer` trong chain API.

### 20.5. Client nói đã gửi token, backend nói thiếu

Hãy kiểm tra:

- Header `Authorization` có thực sự đến backend qua proxy/gateway?
- Client có vô tình gửi token vào query/body thay vì header?
- Có một dấu cách hoặc ký tự điều khiển không hợp lệ không?
- Frontend có gửi preflight `OPTIONS` không mang token trước request thật không?
- Một interceptor có ghi đè header bằng `Basic` hoặc token cũ không?
- Có hai HTTP client interceptors cùng thêm Authorization header gây xung đột không?

Khi chẩn đoán, **chỉ xác nhận header có mặt và scheme**, không công bố toàn bộ token trong log.

## 21. Logging phù hợp mà không lộ token

Trong môi trường phát triển có thể bật log Spring Security:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web: TRACE
```

Mức log thực tế và message khác nhau theo phiên bản. Không nên bật TRACE trên production lâu dài nếu log có thể chứa thông tin nhạy cảm hoặc tiêu thụ tài nguyên lớn.

Các thông tin hữu ích để theo dõi:

| Thông tin | Mục đích |
|---|---|
| Request/correlation ID | Ghép log qua gateway, API và AS |
| HTTP method và route pattern | Xác định endpoint cần bảo vệ |
| SecurityFilterChain được chọn | Kiểm tra API hay web chain xử lý |
| “Bearer credential present?” | Biết có header/token, không lộ giá trị |
| Nhóm lỗi `invalid_request`/`invalid_token` | Phân biệt transport và token validation |
| Validator thất bại (đã giới hạn chi tiết) | Chẩn đoán issuer/audience/exp |
| Kết quả scope/authority rule | Chẩn đoán thiếu quyền |
| Introspection latency và status AS | Phân biệt token inactive với AS outage |
| Response status và `WWW-Authenticate` đã lọc | Xác nhận API contract |

**Không log:** raw Bearer token, refresh token, Client secret, private key, HTTP Basic credential introspection hoặc nội dung claims nhạy cảm không cần thiết.

### 21.1. Không trả lỗi giải mã chi tiết cho Client

Một message như “JWT JSON invalid” đôi khi hữu ích khi phát triển, nhưng không nhất thiết phù hợp để phơi bày ở production. Với lỗi xác thực, nên trả thông tin vừa đủ và ghi chẩn đoán nội bộ theo nguyên tắc data minimization.

Không phát token nguyên văn cùng với lỗi, kể cả khi token đã hết hạn.

## 22. Client nên phản ứng ra sao?

### 22.1. Khi nhận 401 không có token

Client cần kiểm tra luồng xác thực của mình và cung cấp **access token** phù hợp với API nếu có quyền. Không gửi ID token OIDC thay cho access token.

### 22.2. Khi nhận 400 invalid_request

Client cần sửa cách truyền Bearer credential:

- Chỉ dùng một `Authorization: Bearer ...` header.
- Không thêm scheme `Bearer` hai lần.
- Không chứa dấu cách/quote/ký tự không phù hợp bên trong token.
- Không đồng thời đặt access token ở query và header.
- Không gửi token qua URL chỉ để né lỗi header.

Đây là lỗi định dạng request, **không phải cứ xin một access token mới sẽ giải quyết**.

### 22.3. Khi nhận 401 invalid_token

Client có thể cần làm lại luồng lấy access token, dùng token mới hợp lệ hoặc xử lý expiry theo cơ chế OAuth được cấp cho Client.

Không phải mọi `invalid_token` đều là token hết hạn. Nếu token sai audience/issuer, **refresh rồi xin token cùng audience sai** vẫn có thể tiếp tục bị từ chối. Client/AS cần cấp token cho đúng resource và profile.

Chỉ Client có quyền và cơ chế phù hợp mới thực hiện refresh-token flow. Resource Server không nên nhận refresh token để đổi thành access token tại API nghiệp vụ.

### 22.4. Khi nhận 403 insufficient_scope

Một Client đã xác thực nhưng thiếu quyền cần xử lý theo chính sách:

- Không tự động thử một scope mạnh hơn mà người dùng/Client chưa được cấp.
- Không retry vô hạn cùng token.
- Có thể yêu cầu user/administrator cấp quyền hoặc thực hiện luồng authorization bổ sung khi hợp đồng cho phép.
- Cần hiểu rằng một API có thể trả `403` vì tenant/owner/role dù token có mọi scope mong đợi.

Nên hiển thị thông báo nghiệp vụ phù hợp, thay vì luôn đăng xuất người dùng khi thấy bất kỳ `403`.

## 23. Lỗi thực tế hay bị nhầm lẫn

| Hiện tượng | Suy đoán vội vàng | Nguyên nhân cần xem xét |
|---|---|---|
| `401` không có error code | “Token sai chữ ký” | Có thể **chưa gửi token** |
| `400 invalid_request` | “Token đã hết hạn” | Có thể header Bearer sai định dạng |
| `401 invalid_token` | “Chỉ cần đổi scope” | Có thể chữ ký, issuer, audience, `exp` sai |
| `403` với token hợp lệ | “Spring không hiểu JWT” | Có thể thiếu `SCOPE_` hoặc quyền tài nguyên |
| `401` ở public route | “`permitAll` hỏng” | Có thể Client gửi Bearer token lỗi vào chain có authentication filter |
| `302` tới login | “Bearer token bị từ chối” | Có thể request đi qua web form-login chain |
| `401` chỉ từ browser | “JWT sai” | Có thể CORS preflight, gateway/header issue |
| AS introspection HTTP 200 | “Token chắc chắn active” | Response có thể là `{"active":false}` |
| Opaque token `active=true` | “Được gọi mọi API” | Vẫn cần audience, scope, tenant/owner |
| Test `with(jwt())` trả 200 | “Chữ ký thật hợp lệ” | Test có thể bỏ qua decoder |
| Thay JWT payload rồi trả 401 | “Scope thiếu” | Sửa payload đã làm sai chữ ký |
| Không tìm thấy `WWW-Authenticate` | “Không dùng Spring Security” | Có thể custom handler/gateway thay đổi header |
| `401` khi JWKS endpoint chết | “Token chắc chắn giả” | Có thể hệ thống xác minh không lấy được khóa |
| Token hợp lệ nhưng API 404 | “JWT không đúng” | Có thể Controller route sai hoặc bản ghi ngoài phạm vi quyền |

Việc hiểu đúng **nơi phát sinh lỗi** giúp Client sửa request và đội backend bảo vệ API mà không nới lỏng các điều kiện xác thực.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Request không có `Authorization` header tới endpoint protected thường nhận gì?

**Trả lời:** Thường là `401 Unauthorized` kèm `WWW-Authenticate: Bearer`. Vì không có token, challenge có thể không mang `error="invalid_token"`.

**Câu 2.** Vì sao `Authorization: Bearer abc def` thường khác `Authorization: Bearer abc.def.ghi`?

**Trả lời:** Chuỗi thứ nhất sai cú pháp Bearer transport vì có dấu cách nội bộ. Chuỗi thứ hai có thể trích xuất được nhưng sẽ bị token decoder từ chối nếu JWT không hợp lệ. Do đó chúng có thể dẫn tới `400 invalid_request` và `401 invalid_token` tương ứng.

**Câu 3.** Token đã ký đúng nhưng `exp` nằm trong quá khứ nên trả mã nào?

**Trả lời:** Khi `exp` validator từ chối token, thường là `401 invalid_token`.

**Câu 4.** Token còn hạn, issuer/audience đúng nhưng thiếu `orders.read` thì sao?

**Trả lời:** Token có thể được xác thực, nhưng endpoint yêu cầu `SCOPE_orders.read` sẽ từ chối quyền, thường `403 Forbidden`.

**Câu 5.** Opaque token introspection trả HTTP 200 và body `{"active":false}`. API có cho phép request không?

**Trả lời:** Không. HTTP 200 là status của request tới introspection endpoint; `active=false` nghĩa token không được chấp nhận.

**Câu 6.** `permitAll` cho `/api/public/ping` có đảm bảo token Bearer sai không thể làm request nhận `401`?

**Trả lời:** Không. Bearer authentication filter có thể xử lý token trước authorization, nên credential sai vẫn có thể bị từ chối.

**Câu 7.** Khi nào nên xem `WWW-Authenticate`?

**Trả lời:** Khi phân tích Bearer `401`/`403`/`400`, vì header có thể cung cấp scheme, error code và thông tin scope/realm phù hợp. Không nên chỉ xem body JSON.

**Câu 8.** `@ControllerAdvice` có luôn bắt được lỗi JWT sai chữ ký không?

**Trả lời:** Không. Lỗi thường phát sinh ở Servlet security filter trước khi vào Controller; cần kiểm tra entry point/failure handler của Spring Security.

**Câu 9.** Bearer token sai audience nhưng có scope đúng, API có nên cho qua không?

**Trả lời:** Không. Audience là điều kiện token được cấp cho Resource Server cụ thể, độc lập với quyền scope.

**Câu 10.** Tại sao không nên sửa JWT payload để tạo test thiếu scope?

**Trả lời:** Vì thay payload làm chữ ký không còn hợp lệ; request sẽ rơi vào nhánh invalid token thay vì nhánh valid token thiếu scope.

**Câu 11.** Introspection timeout có chứng minh opaque token của Client bị thu hồi không?

**Trả lời:** Không. Timeout là sự cố xác minh; Resource Server không được fail open, nhưng cần phân biệt sự cố upstream với kết quả AS `active=false`.

**Câu 12.** Nhận `403` có nên luôn refresh token và retry không?

**Trả lời:** Không. `403` thường là thiếu scope hoặc quyền nghiệp vụ. Refresh với cùng quyền không tự giải quyết; Client phải xử lý theo policy cấp quyền thích hợp.

## 25. Ghi nhớ

Với Spring Security OAuth 2.0/OIDC Resource Server, hãy luôn phân biệt bốn bước:

1. **Không có Bearer credential:** protected endpoint thường trả **`401` với challenge `Bearer`**, không nhất thiết kèm mã lỗi cụ thể.
2. **Bearer request sai định dạng:** resolver có thể trả **`400 invalid_request`**.
3. **Đã có token nhưng xác thực thất bại:** decoder hoặc introspector có thể trả **`401 invalid_token`** khi token bị từ chối.
4. **Token đã xác thực nhưng quyền chưa đủ:** authorization thường trả **`403 insufficient_scope`** hoặc mã từ chối quyền phù hợp với chính sách.

Đừng nhầm một JWT không thể xác minh với token thiếu scope, cũng đừng nhầm token bị AS từ chối với AS bị timeout. `BearerTokenAuthenticationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler` và các validator của Resource Server có vai trò riêng trong chuỗi xử lý.

Cuối cùng, **response lỗi đúng không chỉ là HTTP status**: cần có Bearer challenge phù hợp, không làm lộ token hoặc bí mật, không mở quyền để “sửa” lỗi, và vẫn bảo vệ audience, scope, tenant, chủ sở hữu tài nguyên trước khi cho API trả dữ liệu.
