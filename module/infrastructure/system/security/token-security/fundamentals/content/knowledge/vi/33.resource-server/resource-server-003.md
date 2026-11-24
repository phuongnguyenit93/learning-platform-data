# Đọc token từ Authorization header

## 1. Resource Server cần lấy token ở đâu và để làm gì?

Trong OAuth 2.0, **Resource Server (RS)** là API cung cấp tài nguyên được bảo vệ. Client lấy **access token** từ Authorization Server (AS), sau đó gửi token khi gọi API. Đối với cơ chế **bearer access token** phổ biến, vị trí chuẩn được ưu tiên là trường HTTP **`Authorization`**:

```http
GET /api/orders/123 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
```

`<ACCESS_TOKEN>` ở đây là ký hiệu giữ chỗ, không phải token thật. Theo RFC 6750, phần **`Bearer`** là *authentication scheme*; phía sau nó là giá trị token. Client gửi request qua **HTTPS/TLS** để giảm nguy cơ lộ credential trên đường truyền.

Bài này thuộc chương **Resource server** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Mục tiêu là hiểu chính xác ranh giới giữa **đọc token từ header**, **xác thực token** và **phân quyền cho hành động**. Việc lấy được một chuỗi có vẻ giống token là **bước đầu tiên**, chưa tạo quyền truy cập.

Sau bài học, bạn cần có thể:

- Đọc đúng `Authorization: Bearer …` trong ngữ cảnh HTTP, phân biệt tên trường, scheme và credential.
- Nhận diện header thiếu, sai scheme, sai cấu trúc hoặc bị gửi trùng; không làm hỏng token bằng cách xử lý chuỗi tùy tiện.
- Hiểu luồng tiếp theo với **JWT** và **opaque access token**, bao gồm kiểm tra chữ ký/introspection, `iss`, `aud`, `exp`, `scope` và thu hồi.
- Cấu hình một Resource Server sử dụng framework xác thực chuẩn, biết phản hồi **400/401/403** và `WWW-Authenticate`.
- Giữ token khỏi URL, log và các nơi lưu/đường truyền không cần thiết, đồng thời hiểu giới hạn của bearer token trước nguy cơ đánh cắp/phát lại.

## 2. Cấu trúc của Authorization header

Một request có thể sử dụng cú pháp bearer token như sau:

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.example.signature
```

Chuỗi ví dụ trên **không phải JWT hợp lệ**. Nó chỉ minh họa hình dạng một header.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Tên trường HTTP** | `Authorization` | Nơi client trình credential cho server; tên trường HTTP không phân biệt chữ hoa/chữ thường. |
| **Authentication scheme** | `Bearer` | Cho biết RS phải xử lý credential theo bearer token; tên scheme không phân biệt chữ hoa/chữ thường. |
| **Khoảng trắng phân tách** | Một hoặc nhiều dấu cách sau `Bearer` | RFC 6750 định nghĩa `Bearer 1*SP b64token`; tránh parser tự chế chỉ chấp nhận duy nhất một dấu cách hoặc cắt chuỗi mơ hồ. |
| **Credential** | `<ACCESS_TOKEN>` | Giá trị token cần giữ nguyên để xác minh; **token có phân biệt chữ hoa/chữ thường**. |

Tên `b64token` trong cú pháp RFC 6750 **không yêu cầu token phải là JWT** hay bắt buộc thực hiện Base64 decode. Access token có thể là **opaque string** hoặc JWT; RS phải chọn cách xác minh theo cấu hình tin cậy đã thỏa thuận với AS, không tự quyết định chỉ nhờ thấy token có ba đoạn ngăn bởi dấu chấm.

Để dễ nhớ:

```text
Authorization: Bearer <credential>
^^^^^^^^^^^^^  ^^^^^^  ^^^^^^^^^^^^
Tên header    Scheme   Giá trị access token (giữ nguyên)
```

### 2.1. Tại sao nên gửi token trong header?

OAuth 2.0 Bearer Token Usage (RFC 6750) mô tả ba cách chuyển bearer token trong một số bối cảnh: **Authorization request header**, form-encoded body và URI query. Cách dùng **header được khuyến nghị** cho request đến RS; không gửi cùng một token qua nhiều cách đồng thời.

Đặt token trong query string (chẳng hạn `?access_token=…`) là lựa chọn nguy hiểm vì URL có thể bị ghi vào access log, lịch sử trình duyệt, hệ thống giám sát, bộ nhớ đệm hoặc xuất hiện trong ngữ cảnh chuyển hướng. Với bearer token, ai lấy được chuỗi còn hiệu lực đều có thể thử sử dụng lại.

Header cũng có thể bị log nếu cấu hình reverse proxy/APM sai. Vì thế **dùng `Authorization` không tự bảo vệ bí mật**; vẫn cần TLS, chính sách redaction, kiểm soát nơi lưu, thời gian sống token và quyền API.

## 3. Luồng xử lý từ request đến quyết định truy cập

Một Resource Server đúng không chỉ tìm chuỗi sau chữ `Bearer`. Nó phải kiểm tra nhiều tầng:

```mermaid
flowchart TD
    A[Client gửi HTTPS request] --> B[RS đọc Authorization header]
    B --> C{Có credential Bearer đúng định dạng?}
    C -->|Không| D[Từ chối với HTTP phù hợp và WWW-Authenticate]
    C -->|Có| E{Token được xác minh hợp lệ?}
    E -->|Không| F[401 invalid_token]
    E -->|Có| G{audience / scope / quyền cho phép?}
    G -->|Không| H[403 insufficient_scope hoặc từ chối quyền]
    G -->|Có| I[Thực thi API theo quyền đã xác minh]
```

Quy trình thường có các bước:

1. **Kết thúc TLS và tiếp nhận HTTP request.** API gateway/reverse proxy phải chuyển đúng thông tin xác thực theo chính sách của hệ thống.
2. **Đọc `Authorization` một cách có kiểm soát.** Phân biệt header vắng mặt, scheme không được hỗ trợ, giá trị không hợp lệ và credential trùng/lặp.
3. **Xác minh token với nguồn tin cậy.** JWT cần xác minh chữ ký, thuật toán cho phép và claims; opaque token thường cần tra cứu trạng thái/introspection hoặc cơ chế xác minh mà hệ thống đã thiết kế.
4. **Tạo principal/identity đã xác minh.** Không dùng nội dung JWT chưa xác minh để gán danh tính hay quyền.
5. **Phân quyền cho đúng API và đối tượng dữ liệu.** Ví dụ API `GET /api/orders/123` yêu cầu `orders:read` *và* kiểm tra người dùng có quyền xem đơn `123`.
6. **Trả kết quả hoặc từ chối** với mã HTTP và challenge phù hợp; không phản hồi hay log nguyên giá trị token.

Ở một số framework, bước xác thực và kiểm tra quyền diễn ra trong filter/interceptor trước controller. Điều quan trọng là **controller chỉ nhận được thông tin chủ thể sau khi framework đã xác minh token**.

## 4. Quy tắc đọc Bearer token an toàn

### 4.1. Nên chấp nhận và từ chối những gì?

| Request nhận được | Cách xử lý đề xuất | Lý do |
| --- | --- | --- |
| `Authorization: Bearer <token-hợp-lệ>` | Trích credential, chuyển vào bộ xác minh; chưa cấp quyền ngay | Đúng mô hình bearer token |
| `authorization: bearer <token>` | Vẫn nhận diện field name/scheme theo quy tắc HTTP; **không sửa chữ hoa/thường của token** | Tên field và scheme không phân biệt hoa/thường |
| Không có `Authorization` | Từ chối tài nguyên cần xác thực bằng **401** và challenge Bearer | Client chưa cung cấp credential |
| `Authorization: Basic …` | Không diễn giải Basic credential như Bearer token; xử lý theo các scheme được API hỗ trợ | Không được nhận nhầm kiểu chứng thực |
| `Authorization: Bearer` hoặc `Bearer   ` | Từ chối do không có credential | Thiếu giá trị token |
| Header trùng hoặc có nhiều giá trị Authorization mâu thuẫn | Từ chối request mơ hồ theo chính sách HTTP/gateway, thay vì tùy tiện chọn giá trị đầu/cuối | Tránh request smuggling, sai khác giữa proxy và app |
| Token có ký tự/whitespace ngoài cú pháp hoặc quá giới hạn kích thước cho phép | Từ chối và ghi sự kiện đã làm sạch | Tránh parser mơ hồ và lạm dụng tài nguyên |
| Token hết hạn, sai `iss`/`aud`, chữ ký sai hoặc bị thu hồi | **401** sau khi xác minh thất bại | Không tạo principal cho token không hợp lệ |
| Token hợp lệ nhưng thiếu quyền cho thao tác | **403** (ví dụ `insufficient_scope`) | Đã xác thực nhưng không đủ quyền |

Điểm dễ sai trong code thủ công là:

```java
// Ví dụ KHÔNG NÊN dùng làm parser xác thực hoàn chỉnh
String token = request.getHeader("Authorization").replace("Bearer", "");
```

Lỗi tiềm tàng: `getHeader` có thể trả `null`; `replace` xóa cả chuỗi `Bearer` bên trong token; không xác minh scheme nằm ở vị trí đầu; không kiểm tra nhiều header; và token sau khi cắt chưa hề được xác thực. Tương tự, `split(" ")` rồi lấy `[1]` dễ sai nếu có nhiều dấu cách.

**Ưu tiên bộ phân giải Bearer có sẵn của framework** thay vì tự xử lý chuỗi. Nếu buộc phải xây parser riêng, cần có đặc tả và kiểm thử rõ cho cú pháp RFC 6750, giới hạn kích thước, số lượng header, chuẩn hóa HTTP qua proxy và hành vi phản hồi. Không trim/lowercase/URL-decode/Base64-decode credential một cách tùy tiện trước khi đưa vào bộ xác minh.

### 4.2. Mã giả để hiểu trách nhiệm các lớp

Đoạn sau là **pseudocode**, không phải thư viện Java sẵn chạy được:

```text
function handleProtectedApi(request):
    authorizationValues = request.getAllHeaders("Authorization")
    if authorizationValues.count == 0:
        return unauthorizedWithBearerChallenge()

    if authorizationValues.count != 1:
        return rejectAmbiguousAuthorization()

    credential = parseBearerSchemeAndToken(authorizationValues[0])
    if credential is malformed:
        return rejectMalformedCredential()

    authenticated = verifyAccessTokenWithTrustedIssuer(credential)
    if authenticated is invalid:
        return unauthorizedInvalidToken()

    if not isAllowedForAudienceScopeAndResource(authenticated, request):
        return forbidden()

    return serveResource(authenticated.principal)
```

Hai hàm `parseBearerSchemeAndToken` và `verifyAccessTokenWithTrustedIssuer` tượng trưng cho các thành phần cần triển khai bằng **framework/thư viện đã kiểm thử**. Không suy ra token đáng tin chỉ vì trình duyệt gửi nó qua `Authorization`.

## 5. Đọc token khác với xác thực token

### 5.1. Nếu access token là JWT

Một JWT thường có dạng `header.payload.signature`. Resource Server có thể xác minh cục bộ bằng khóa công khai được AS công bố qua JWKS, tùy thuật toán và mô hình phát hành. RS phải:

- Chỉ chấp nhận các **thuật toán ký được cấu hình sẵn**, xác minh chữ ký bằng khóa thuộc issuer tin cậy; xử lý `kid` qua JWKS đã cấu hình, không chạy theo URL khóa tùy ý do token đưa ra.
- Kiểm tra `iss` thuộc Authorization Server dự kiến; không tự tin issuer được khai báo trong token nếu chưa cấu hình tin cậy.
- Kiểm tra `aud` có chứa định danh **API này**. Một JWT đúng chữ ký nhưng cấp cho API khác hoặc cho client khác không được tự động chấp nhận.
- Kiểm tra `exp`, `nbf` khi có; áp dụng sai lệch thời gian (*clock skew*) nhỏ, có chủ đích. `iat`, `jti`, `sub` và các claims tùy chọn khác được xử lý theo chính sách của hệ thống.
- Xác định `scope`/quyền rồi kiểm tra quyền ở endpoint và tài nguyên; không chỉ xác thực danh tính.
- Nếu cần thu hồi trước `exp`, có chính sách token ngắn hạn, kiểm tra phiên/revocation, hoặc giải pháp phù hợp. **JWT được ký không tự hết hiệu lực ngay khi người dùng đăng xuất.**

Ví dụ payload access token **minh họa, không phải JWT hợp lệ**:

```json
{
  "iss": "https://auth.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iat": 1795400000,
  "exp": 1795400300,
  "jti": "at-1234"
}
```

Không được dùng thao tác giải mã Base64URL payload để lấy `sub` hoặc `scope` rồi tin ngay các giá trị ấy: **decode khác verify**. Và **ID token trong OIDC không thay thế access token** khi gọi Resource Server.

### 5.2. Nếu access token là opaque token

Opaque token thường là một chuỗi không mang cấu trúc claims mà RS có thể diễn giải. RS phải dùng cơ chế AS thiết kế, chẳng hạn **OAuth 2.0 Token Introspection (RFC 7662)**, để hỏi trạng thái:

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as Resource Server
    participant AS as Authorization Server
    C->>RS: Authorization: Bearer opaque-token
    RS->>AS: Introspection qua kênh bảo vệ, RS xác thực với AS
    AS-->>RS: active, scope, aud, iss và metadata nếu có
    Note over RS: Kiểm tra active và thuộc tính phù hợp chính sách API
    RS-->>C: Dữ liệu nếu xác thực và phân quyền thành công
```

Khi introspection trả `active: false`, không cho truy cập. Khi `active: true`, RS **vẫn phải** bảo đảm token dành cho RS này và đủ quyền trong phạm vi thông tin/đặc tả AS cung cấp. Endpoint introspection cần TLS, xác thực RS và bảo mật thông tin phản hồi; có thể cache phản hồi nếu phù hợp mức rủi ro, nhưng cache kéo dài làm chậm hiệu lực thu hồi.

| Khía cạnh | JWT access token | Opaque access token |
| --- | --- | --- |
| Cách RS xác minh phổ biến | Kiểm chữ ký và claims cục bộ bằng khóa tin cậy | Introspection hoặc tra cứu trạng thái được AS hỗ trợ |
| Nguy cơ bị đánh cắp | Bị phát lại nếu là bearer token còn hiệu lực | **Tương tự** khi là bearer token còn hiệu lực |
| Thu hồi tức thời | Cần thiết kế bổ sung nếu RS kiểm tra offline | Thường thuận tiện hơn khi RS hỏi trạng thái, tùy cache và kiến trúc |
| Parser `Authorization` | Nhận credential sau scheme `Bearer` | **Vẫn nhận giống hệt**; không đoán loại token từ ký tự |

## 6. Thực hành với Spring Security Resource Server

Một ứng dụng Java/Spring Boot nên dùng **Spring Security OAuth2 Resource Server** để xử lý bearer authentication, xác minh token và tạo `Authentication`. Phần này dùng JWT làm ví dụ; phương thức opaque sẽ được cấu hình bằng cơ chế introspection riêng nếu hệ thống dùng opaque access token.

### 6.1. Client gửi request

```bash
# Chỉ là placeholder trong ví dụ, không phải token thực.
curl -i 'https://api.example.test/api/orders/123' \
  -H 'Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER' \
  -H 'Accept: application/json'
```

Khi làm việc thật, công cụ gửi request phải lấy access token từ nguồn tin cậy theo OAuth flow. Không hard-code access token vào repository, script chia sẻ, lịch sử shell hoặc tài liệu nội bộ.

### 6.2. Cấu hình RS và issuer tin cậy

Trong Spring Boot dùng phiên bản Spring Security phù hợp, ứng dụng cần dependency **OAuth2 Resource Server** và cấu hình issuer:

```yaml
# application.yml — ví dụ, chỉ phù hợp khi AS phát JWT access token.
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
```

Spring Security có thể dùng metadata của issuer/JWKS để xác minh chữ ký và kiểm tra các thuộc tính chuẩn theo cấu hình. **Phải cấu hình thêm kiểm tra `aud` thích hợp nếu cấu hình mặc định chưa đảm bảo token chỉ dành cho `orders-api`.** Không coi có `issuer-uri` là tự động hoàn tất mọi yêu cầu phân quyền.

Ví dụ cấu hình endpoint:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );
        return http.build();
    }
}
```

Trong cấu hình này:

1. Resource Server xử lý bearer token từ request, kiểm tra JWT và tạo principal khi hợp lệ.
2. `GET /api/orders/**` yêu cầu authority `SCOPE_orders:read`; Spring Security thường ánh xạ claim `scope` hoặc `scp` sang authority có tiền tố `SCOPE_`, tùy converter và cấu trúc token.
3. Endpoint cần chính sách riêng cho `POST`/`PUT`/`DELETE` và quyền theo **đối tượng**: user có `orders:read` chưa chắc được xem đơn của user khác.
4. Cấu hình CSRF phụ thuộc cách ứng dụng nhận credential: API chỉ nhận bearer trong header thường có bề mặt CSRF khác ứng dụng dùng cookie phiên tự đính kèm. **Không tắt CSRF máy móc** nếu hệ thống còn dùng cookie hoặc cơ chế xác thực trình duyệt khác.

Đoạn mẫu cố ý **không đọc trực tiếp `Authorization` trong controller**. Framework filter xử lý authentication trước khi controller chạy, nhờ đó giảm lỗi parser và tránh vô tình truyền token thô qua tầng nghiệp vụ.

### 6.3. Lấy thông tin đã xác thực trong controller

Sau khi framework xác minh JWT, handler có thể dùng principal và claims **đã được xác minh**:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {
    @GetMapping("/api/me")
    String currentUser(@AuthenticationPrincipal Jwt jwt) {
        return jwt.getSubject(); // Dùng subject đã xác minh, không log token raw.
    }
}
```

Đây là ví dụ khái niệm về principal của **JWT Resource Server**; khi dùng opaque token, principal và converter khác có thể được sử dụng. Trong ứng dụng thật, trả một DTO an toàn và áp dụng phân quyền cho dữ liệu thay vì chỉ trả `sub`.

### 6.4. Nếu hệ thống dùng opaque token

Thay bộ xác minh JWT bằng cơ chế opaque token của Spring Security và cấu hình `introspection-uri`, thông tin xác thực dùng gọi introspection cùng chính sách TLS:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Đoạn trên là **một phần cấu hình**, không phải method Java độc lập. Không giữ cấu hình introspection client secret dưới dạng giá trị hard-code trong nguồn. Với JWT hoặc opaque, quy tắc nhận bearer credential ở header vẫn nhất quán; bước xác minh phía sau mới khác nhau.

## 7. Phản hồi HTTP: 400, 401, 403 và WWW-Authenticate

Server nên trả mã lỗi đủ rõ để client xử lý nhưng không làm lộ bí mật. RFC 6750 định nghĩa Bearer challenge qua **`WWW-Authenticate`**:

| Tình huống | HTTP phù hợp | Ví dụ phản hồi |
| --- | --- | --- |
| Thiếu access token cho tài nguyên yêu cầu đăng nhập | **401 Unauthorized** | `WWW-Authenticate: Bearer realm="orders-api"` |
| Token sai chữ ký, hết hạn, sai issuer/audience hoặc không còn hiệu lực | **401 Unauthorized** | `WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"` |
| Cú pháp bearer request sai hoặc gửi credential bằng nhiều cách không được phép | Thường **400 Bad Request** với `invalid_request` | `WWW-Authenticate: Bearer error="invalid_request"` |
| Token xác thực hợp lệ nhưng không đủ scope | **403 Forbidden** | `WWW-Authenticate: Bearer error="insufficient_scope", scope="orders:read"` |
| Người dùng không sở hữu bản ghi dù scope hợp lệ | **403** hoặc phản hồi ẩn tài nguyên phù hợp chính sách API | Không công khai dữ liệu/định danh nhạy cảm trong lỗi |
| Introspection endpoint tạm không khả dụng | Lỗi hạ tầng phù hợp, thông thường **5xx**, không tự gán mọi lần timeout thành token không hợp lệ | Không nhận token không xác minh được chỉ để duy trì dịch vụ |

Ví dụ một lỗi token hết hạn:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
Content-Type: application/json

{"error":"unauthorized"}
```

**Phân biệt 401 và 403:** 401 thường yêu cầu trình credential hợp lệ; 403 nghĩa là credential đã xác thực nhưng không đủ quyền cho tài nguyên. Không nên dùng 403 để che giấu việc hoàn toàn chưa xác thực, cũng không dùng 401 tùy tiện để ám chỉ thiếu scope.

Khi không có token, RFC 6750 khuyến nghị challenge **không kèm mã lỗi chi tiết** nếu client chưa gửi thông tin xác thực. Không đưa giá trị token, toàn bộ claims, stack trace hoặc thông tin khóa ký vào thông báo lỗi. `error_description` nếu có phải tối giản và không lộ chi tiết nội bộ.

## 8. Các điểm tinh tế ở gateway, trình duyệt và nhiều phương thức token

### 8.1. Proxy và các header trùng

Nhiều hệ thống đi qua CDN, load balancer, API gateway và reverse proxy trước khi tới Java application. Mỗi lớp có thể chuẩn hóa tên header, giới hạn kích thước hoặc xử lý header trùng khác nhau. Cần bảo đảm:

- Gateway không vô tình **xóa, ghi đè hoặc đưa giá trị `Authorization` vào log**.
- Gateway và ứng dụng **thống nhất cách xử lý giá trị trùng/không hợp lệ**; không để một lớp xác thực token A còn lớp sau xử lý token B.
- Không chấp nhận một header do người dùng tự đặt như `X-User-Id`, `X-Role` hoặc `X-Forwarded-Authorization` làm bằng chứng danh tính, trừ khi có một mô hình ủy quyền và mạng tin cậy được thiết kế riêng.
- Nếu gateway xác thực rồi chuyển identity xuống backend, ranh giới giữa gateway/backend cần được bảo vệ; backend không được tin những identity header có thể bị client ngoài giả mạo.

### 8.2. Browser CORS preflight

Khi JavaScript trên origin A gọi API origin B với `Authorization` header, trình duyệt có thể gửi request **CORS preflight `OPTIONS`** trước. Preflight dùng để hỏi chính sách cho method/header và thường **không gửi access token**; gateway hoặc security filter cần xử lý luồng này phù hợp.

Điều này không có nghĩa API được bỏ xác thực trên request chính. Cấu hình CORS phải chỉ cho phép origin/method/header cần thiết và không cấp quyền API dựa trên origin. **CORS là chính sách bảo vệ việc browser truy cập giữa các origin; xác thực và phân quyền token vẫn là việc của RS.**

### 8.3. DPoP và mTLS có gì khác Bearer?

Ví dụ của bài dùng `Authorization: Bearer …`, nhưng không phải mọi access token đều dùng scheme này. **DPoP** (RFC 9449) dùng request có dạng:

```http
GET /api/orders/123 HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <SIGNED_PROOF_JWT>
```

Với DPoP, RS phải xác minh proof đã ký, ràng buộc khóa và các thuộc tính `htu`, `htm`, `ath`, `iat`/nonce, `jti`; không được lấy token ra rồi bỏ qua proof. Một resolver **chỉ** hỗ trợ Bearer sẽ không tự động xử lý đúng DPoP nếu hệ thống chưa cấu hình tương ứng.

Với **mTLS-bound access token** (RFC 8705), client có thể vẫn gửi `Authorization: Bearer …`, nhưng RS **còn phải** so khớp chứng chỉ client trên kết nối TLS với ràng buộc trong token. Việc chấp nhận chữ `Bearer` chưa đủ.

Refresh token và ID token **không phải credential phù hợp để gọi API tài nguyên** chỉ vì client đặt chúng vào `Authorization`. RS phải áp dụng **type/usage restriction** phù hợp và chỉ chấp nhận access token được AS cấp cho API.

## 9. Bảo vệ token và giảm nguy cơ replay

Đọc token an toàn phải gắn với bảo vệ cả vòng đời:

1. **Truyền và lưu:** Bắt buộc TLS, tránh truyền token qua URL; hạn chế script bên thứ ba/XSS trên browser, không giữ refresh token dài hạn trong nơi JavaScript đọc được khi có kiến trúc tốt hơn.
2. **Giới hạn phạm vi:** Token nên có TTL ngắn, `aud` chỉ đúng API và `scope` tối thiểu. RS thực thi quyền ở endpoint và quyền với từng đối tượng dữ liệu.
3. **Không ghi bí mật:** Mask/redact trường `Authorization` ở reverse proxy, access log, telemetry/APM, exception tracing và request dump. Nếu cần correlation, dùng request ID hoặc định danh token được xử lý an toàn, không lưu bearer string.
4. **Thu hồi:** AS/RS phối hợp chính sách logout, session invalidation, token revocation, refresh token rotation và reuse detection. JWT được xác minh offline có cửa sổ thu hồi khác với opaque token introspection.
5. **Hạn chế phát lại:** Bearer token bị sao chép có thể dùng lại cho tới khi hết hiệu lực. Khi rủi ro cao, cân nhắc DPoP/mTLS sender constraint; theo dõi dấu hiệu bất thường, nhưng không coi nhiều request dùng cùng một access token là replay trái phép.
6. **Giới hạn khả năng lạm dụng:** Rate limiting, audit, xác thực lại cho thao tác nhạy cảm và phân quyền đối tượng giúp giảm tác hại của credential đã bị đánh cắp.

**Không được chọn biện pháp «chặn mọi lần sử dụng lại `jti` của access token» như một cách chống replay tổng quát.** Một bearer access token thường được dùng hợp pháp trên nhiều request. Cơ chế chỉ dùng một lần phù hợp với loại bằng chứng khác, như DPoP proof `jti`, authorization code hoặc refresh token rotation.

## 10. Tình huống thực hành và checklist

### 10.1. Tình huống tự đánh giá

**Tình huống A — Header `Bearer` hợp lệ nhưng JWT dành cho service khác:** RS xác minh chữ ký thành công, nhưng `aud` là `payments-api` thay vì `orders-api`. **Kết luận:** Phải từ chối; chữ ký hợp lệ không đủ chứng minh token được cấp cho API này.

**Tình huống B — Header trùng qua proxy:** Một request chứa hai giá trị `Authorization`, gateway chọn giá trị đầu, ứng dụng chọn giá trị cuối. **Kết luận:** Hệ thống có rủi ro hiểu sai credential; cần chính sách nhất quán và từ chối request mơ hồ.

**Tình huống C — Token opaque chỉ có 40 ký tự:** Dev viết logic «token có ba đoạn dấu chấm thì chấp nhận, không thì trả 401». **Kết luận:** Sai. Dạng chuỗi không xác định cách xác minh; chọn bộ xác minh theo hợp đồng token của AS.

**Tình huống D — Người dùng có `orders:read` gọi `GET /api/orders/123`:** Token hợp lệ, nhưng đơn 123 thuộc tài khoản khác. **Kết luận:** Cần kiểm tra **object-level authorization**; scope chỉ là một lớp quyền.

**Tình huống E — Client gửi refresh token vào `Authorization`:** RS không được chấp nhận token loại này như access token, kể cả nếu refresh token còn hiệu lực tại AS.

**Tình huống F — API trả 401 khi introspection timeout:** Hệ thống không phân biệt token sai với lỗi mạng tới AS. **Kết luận:** Phải fail closed và phân loại lỗi hạ tầng phù hợp để tránh quy kết nhầm người dùng hoặc tạo vòng lặp refresh không cần thiết.

### 10.2. Checklist trước khi triển khai

- [ ] Client gửi access token qua `Authorization` trên **HTTPS**; không bỏ token vào query string hay log.
- [ ] RS nhận scheme được hỗ trợ và giữ nguyên credential; xử lý header thiếu, malformed, trùng và quá giới hạn một cách nhất quán.
- [ ] Đã dùng Bearer resolver và token verifier chuẩn của framework thay vì parser chuỗi tự chế.
- [ ] JWT được xác minh chữ ký/thuật toán, issuer, audience, thời gian và claims theo hợp đồng; opaque token được xác minh trạng thái bằng cơ chế tin cậy.
- [ ] ID token và refresh token không bị chấp nhận làm access token.
- [ ] API kiểm tra `scope`/authority và quyền truy cập **từng đối tượng dữ liệu**.
- [ ] Các phản hồi 400/401/403 và `WWW-Authenticate` đúng ngữ cảnh, không lộ token hay stack trace.
- [ ] Gateway, proxy, app và APM thống nhất cách xử lý `Authorization`, không tin header identity giả mạo.
- [ ] CORS preflight được xử lý mà không bỏ xác thực request chính.
- [ ] Nếu dùng DPoP/mTLS, RS xác minh bằng chứng ràng buộc người gửi ngoài việc đọc access token.
- [ ] Có chính sách TTL, thu hồi, redaction log, phát hiện bất thường và xử lý token bị đánh cắp.

## 11. Ghi nhớ

**`Authorization: Bearer <access_token>` là cách chuẩn và được ưu tiên để trình bearer access token cho Resource Server.** Nhưng lấy chuỗi token từ header chỉ là thao tác tiếp nhận credential. Độ tin cậy bắt đầu sau khi token đã được **xác minh bởi thành phần đáng tin**, được kiểm tra `issuer`, `audience`, thời hạn, quyền và ràng buộc bổ sung nếu có.

Khi triển khai Java/Spring Security, ưu tiên **OAuth2 Resource Server filter** để giải quyết việc đọc và xác thực header; giữ controller tập trung vào nghiệp vụ. Kết hợp TLS, cấu hình gateway nhất quán, hạn chế phạm vi token, thu hồi và phòng chống token theft/replay để bảo vệ cả vòng đời xác thực.

### Tài liệu tham khảo

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750) — cú pháp Authorization Bearer, cách truyền token và Bearer challenge.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — quy tắc trường HTTP và authentication framework.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) — kiểm tra trạng thái opaque/access token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700) — bảo mật OAuth 2.0 và giảm nguy cơ đánh cắp/phát lại token.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html) — cấu hình Bearer authentication, JWT và opaque tokens.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449) và [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705).
