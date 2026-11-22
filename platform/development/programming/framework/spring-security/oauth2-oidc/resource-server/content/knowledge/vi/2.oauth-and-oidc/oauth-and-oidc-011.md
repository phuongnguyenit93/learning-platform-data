# Hợp đồng giữa client, nhà phát hành và API về audience, quyền, danh tính

Trong hệ thống Spring Security sử dụng OAuth 2.0 và OpenID Connect (OIDC), access token chỉ hữu ích khi **OAuth2 Client**, **nhà phát hành token (Authorization Server/Issuer)** và **API được bảo vệ (Resource Server)** cùng hiểu đúng một hợp đồng. Hợp đồng đó trả lời ít nhất ba câu hỏi:

1. **Audience:** Token này được phát hành **cho API nào**?
2. **Quyền:** Token được dùng để **làm những hành động nào**, và ai quyết định quyền truy cập từng tài nguyên?
3. **Danh tính:** Token đang đại diện cho **người dùng, ứng dụng hay một chủ thể được ủy quyền** nào?

Nếu ba bên hiểu khác nhau, hệ thống có thể gặp lỗi 401/403 khó chẩn đoán, hoặc nguy hiểm hơn là chấp nhận token của API khác, dùng ID token để gọi API, hay suy ra quá nhiều quyền từ một claim danh tính.

> **Nguyên tắc thiết kế:** Client **đề nghị** quyền và gửi access token; Authorization Server **quyết định và phát hành** token; Resource Server **xác minh token và thực thi** quyền trên tài nguyên. Việc token có chữ ký hợp lệ chỉ là một phần của quyết định truy cập.

## 1. Ba bên cùng tham gia một hợp đồng

Giả sử một ứng dụng thương mại điện tử có:

- **Shop Web / Shop BFF:** OAuth2 Client có đăng ký `client_id = shop-web`.
- **Identity Server:** Authorization Server công bố issuer `https://identity.example.test/realms/shop`.
- **Orders API:** Resource Server được nhận diện bằng audience `orders-api`.
- **Người dùng:** Chủ thể muốn xem các đơn hàng của chính họ.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Client as OAuth2 Client (Shop Web)
    participant AS as Authorization Server (Issuer)
    participant API as Resource Server (Orders API)

    User->>Client: Xem đơn hàng
    Client->>AS: Xin quyền orders.read cho orders-api
    AS->>AS: Xác thực, đánh giá Client/scope/audience
    AS-->>Client: Access token có iss, aud, sub, scope
    Client->>API: GET /api/orders/42 + Bearer token
    API->>API: Kiểm tra chữ ký, iss, exp, aud
    API->>API: Kiểm tra scope và quyền trên đơn 42
    API-->>Client: 200 / 401 / 403 / 404
~~~

Trong một luồng đăng nhập tương tác, Client có thể nhận authorization code rồi đổi lấy token; trong giao tiếp service-to-service, Client có thể dùng `client_credentials`. Chi tiết cấp token thay đổi theo grant nhưng **API vẫn phải xác minh token dành cho nó và tự kiểm tra quyền**.

| Bên | Điều bên đó phải biết | Điều bên đó chịu trách nhiệm |
| --- | --- | --- |
| **OAuth2 Client** | Issuer/metadata, đăng ký Client, grant, scope có thể xin, Resource Server cần gọi, cách quản lý token | Xin token đúng API và quyền cần dùng; gửi access token bảo mật qua request; xử lý hết hạn hoặc bị từ chối |
| **Authorization Server** | Client nào được phép xin token, resource/audience nào được cấp, scope/chính sách nào áp dụng, danh tính được xác thực thế nào | Xác thực theo grant, cấp token với issuer, audience, subject và các quyền chính xác |
| **Resource Server** | Issuer và khóa tin cậy hoặc introspection; audience chấp nhận; ánh xạ scope/claim; chính sách truy cập dữ liệu | Xác minh token; từ chối audience/issuer sai; kiểm tra scope, tenant, ownership và chính sách nghiệp vụ |

Hợp đồng phải được ghi thành cấu hình và quy tắc kiểm tra cụ thể. Tài liệu nói “API nhận JWT” là chưa đủ vì **không phải JWT nào cũng dành cho API đó**.

## 2. Hiểu đúng các trường của access token

Một access token dạng JWT có thể chứa payload minh họa sau:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "iat": 1893456000,
  "exp": 1893459600,
  "jti": "token-7a1c",
  "tenant_id": "shop-tenant-17"
}
~~~

Đây là **ví dụ hợp đồng ứng dụng**, không phải mọi Authorization Server đều tạo cùng các claim. Một số nhà phát hành dùng `scp` thay vì `scope`, `azp` thay vì `client_id`, định dạng khác cho `aud` hoặc không cấp claim `tenant_id`. Những khác biệt này phải được thỏa thuận và cấu hình rõ.

| Claim / thuộc tính | Ý nghĩa trong hợp đồng | Lưu ý |
| --- | --- | --- |
| `iss` | **Issuer** phát hành token | Resource Server chỉ tin issuer được cấu hình; so khớp chính xác giá trị mong đợi |
| `aud` | **Audience**: đối tượng đích được phép nhận token | Phải có định danh Orders API; không dùng `client_id` thay thế `aud` |
| `sub` | **Subject** được biểu diễn trong token | Cách hiểu subject phụ thuộc grant, issuer và hồ sơ token; không mặc định luôn là người dùng |
| `client_id` / `azp` | Client liên quan tới token, tùy quy ước phát hành | Có thể dùng cho chính sách Client nhưng không chứng minh “người dùng là ai” |
| `scope` / `scp` | Phạm vi quyền đã được cấp | Chỉ hiểu theo định nghĩa của Authorization Server và Resource Server |
| `exp`, `nbf`, `iat` | Thời hạn và thời điểm liên quan tới token | Thường kiểm tra hết hạn/chưa có hiệu lực; đồng hồ cần đồng bộ |
| `jti` | Mã định danh token nếu nhà phát hành cung cấp | Hữu ích cho log/truy vết, không tự động bảo đảm thu hồi |
| `tenant_id`, `roles`, claim nghiệp vụ | Thông tin mở rộng theo hợp đồng riêng | Phải kiểm tra nguồn tin cậy, ngữ nghĩa và chính sách sử dụng |

**Không bao giờ ra quyết định chỉ vì payload “trông đúng”.** JWT là dữ liệu có thể được giải mã mà không cần biết khóa; Resource Server phải xác minh chữ ký và các điều kiện chấp nhận token trước khi tin các claim. Với opaque token, API thường lấy trạng thái/thuộc tính qua introspection thay vì giải mã JWT, nhưng nguyên tắc hợp đồng vẫn giữ nguyên.

## 3. Audience: token dành cho *ai*?

### 3.1. Audience không phải Client ID

Audience (`aud`) xác định đối tượng nhận token hợp lệ. Trong ví dụ:

- `client_id = shop-web`: ứng dụng **xin** token.
- `aud = orders-api`: API **được phép nhận** access token.
- `iss = https://identity.example.test/realms/shop`: nhà phát hành **được API tin cậy**.

Ba giá trị này có thể hoàn toàn khác nhau. API không nên suy ra “token hợp lệ cho tôi” từ việc token được cấp cho một Client đã biết hoặc được ký bởi một issuer đã biết.

Hãy xét ba trường hợp:

| Token | Orders API xử lý thế nào? | Vì sao? |
| --- | --- | --- |
| `iss` đúng, `aud = orders-api`, còn hiệu lực | Có thể chuyển sang kiểm tra quyền | Token có audience đúng, nhưng còn phải kiểm tra scope và dữ liệu |
| `iss` đúng, `aud = billing-api` | **Từ chối** | Token dành cho API khác, dù chung issuer và khóa ký |
| `aud = orders-api`, `iss` của bên không được tin | **Từ chối** | Audience đúng không khiến issuer xa lạ trở thành đáng tin |

Nếu token có danh sách audience, API phải xác minh **định danh của mình nằm trong danh sách** và cân nhắc chính sách chấp nhận token nhiều audience. Với hệ thống nhiều API, phát token có audience hẹp thường giúp tránh lạm dụng token khi bị lộ.

### 3.2. Client xin token cho đúng resource

Một số Authorization Server hỗ trợ **Resource Indicators for OAuth 2.0 (RFC 8707)**: Client có thể cung cấp tham số `resource` để chỉ tài nguyên đích khi xin quyền.

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=orders.read&
resource=https%3A%2F%2Fapi.example.test%2Forders
~~~

Đây chỉ là phần thân rút gọn để minh họa `resource`: một yêu cầu thực tế còn phải **xác thực Client** theo phương thức đã đăng ký, và Authorization Server phải hỗ trợ tham số này. Giá trị `resource` có thể là URL tài nguyên trong khi giá trị `aud` là `orders-api`, nếu đây là quy tắc ánh xạ đã thống nhất. **Client không tự quyết định audience bằng cách ghi một claim vào token**; nhà phát hành mới quyết định audience thực tế được cấp.

Nếu Authorization Server không hỗ trợ `resource`, hệ thống có thể quy định audience theo Client registration, scope, API configuration hoặc cơ chế riêng của nhà phát hành. Không có cơ chế chung bảo đảm “Client xin scope `orders.read` thì audience mặc nhiên là Orders API”.

### 3.3. Audience của access token và ID token khác nhau

OIDC phát hành **ID token** cho **OIDC Client** nhằm trình bày kết quả xác thực người dùng. ID token thường có `aud` là `client_id` của Client (`shop-web`), trong khi access token dành cho Orders API phải có audience đúng của Orders API (`orders-api`).

~~~text
ID token (OIDC):         iss = Identity Server
                         aud = shop-web
                         sub = user-842
                         Mục đích: Client xác nhận người dùng đã đăng nhập

Access token (OAuth2):   iss = Identity Server
                         aud = orders-api
                         sub = user-842 (trong luồng có người dùng)
                         scope = orders.read
                         Mục đích: Gọi Orders API
~~~

**Không gửi ID token để thay access token**, kể cả khi cả hai đều là JWT và do cùng issuer ký. API nên có chính sách kiểm tra loại token/phân biệt mục đích token phù hợp với profile và nhà phát hành; một hệ thống dùng profile JWT access token (ví dụ RFC 9068) có thể áp dụng thêm quy tắc header `typ` tương ứng, nhưng không nên tự giả định mọi nhà phát hành đều dùng cùng quy ước.

## 4. Quyền: scope, role và chính sách dữ liệu

### 4.1. Scope xác định hành động được cấp

Giả sử hợp đồng của Orders API định nghĩa:

| Scope | Hành động API được phép xem xét |
| --- | --- |
| `orders.read` | Đọc đơn hàng |
| `orders.write` | Tạo/cập nhật đơn hàng theo chính sách |
| `orders.cancel` | Hủy đơn hàng theo chính sách |

Authorization Server phải biết scope nào có thể cấp cho Client và chủ thể theo từng grant. Client chỉ **đề nghị** scope; kết quả thực tế có thể bị thu hẹp. Resource Server phải kiểm tra **scope thực sự có trong access token đã xác minh**, không tin một danh sách quyền do Client gửi riêng trong request.

Ví dụ:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Nếu endpoint yêu cầu `orders.read`, token chỉ có `orders.write` **không tự động được quyền đọc** trừ khi hệ thống có quy tắc phân cấp scope được định nghĩa rõ. Tên gọi gần nhau không tạo quan hệ quyền ngầm định.

### 4.2. Scope chưa đủ để quyết định quyền trên một bản ghi

Scope trả lời “có thể **thử** thực hiện loại thao tác gì?”. Quyền nghiệp vụ còn trả lời “**trên bản ghi nào và trong hoàn cảnh nào**?”.

Ví dụ token của `user-842` có `orders.read` nhưng request `GET /api/orders/42` có thể:

- **Được phép** nếu đơn 42 thuộc `user-842` và tenant phù hợp.
- **Bị từ chối** nếu đơn 42 thuộc người khác.
- **Bị từ chối** nếu user không còn tư cách thành viên tenant hoặc đơn ở trạng thái không được hiển thị.

Quyền theo vai trò (RBAC), thuộc tính (ABAC), tenant và quyền sở hữu dữ liệu thường được Resource Server hoặc lớp nghiệp vụ của nó kiểm tra. **Không nên xem claim `roles` là quyền toàn cục** nếu chưa thống nhất role áp dụng cho API/tenant nào và được issuer quản trị ra sao.

### 4.3. Phân biệt quyền của Client và quyền của người dùng

Trong một luồng người dùng, token có thể gắn với cả Client (`shop-web`) và người dùng (`user-842`). Quyền truy cập thường phải nằm trong giao điểm giữa **những gì Client được phép làm** và **những gì người dùng được phép làm**.

Trong `client_credentials`, có thể **không có người dùng cuối**. Token thể hiện quyền của ứng dụng/dịch vụ được xác thực; cách ghi `sub` trong trường hợp này tùy Authorization Server và token profile. Resource Server không được coi mọi `sub` là ID người mua hàng.

Khi Backend A gọi Backend B thay mặt người dùng, hợp đồng phải quy định rõ cách **delegation/token exchange** hoặc cách cấp token cho B với audience và actor/subject phù hợp. Không mặc định chuyển tiếp token từ request đến Backend A sang Backend B, bởi audience và quyền có thể không tương thích.

## 5. Danh tính: ai đang gọi và đang đại diện cho ai?

OAuth 2.0 tập trung vào quyền truy cập tài nguyên. OIDC bổ sung cách xác thực danh tính cho Client. Vì vậy, một access token có `sub` chưa đủ để kết luận ứng dụng đã thực hiện đầy đủ luồng đăng nhập OIDC.

### 5.1. Subject không đồng nghĩa email, username hay Client

Với token người dùng, `sub` là định danh chủ thể theo issuer. Một quy tắc lưu trữ an toàn là dùng cặp **(`iss`, `sub`)** làm khóa định danh từ nhà phát hành, thay vì chỉ dùng `sub` hoặc email. Hai issuer có thể cấp cùng chuỗi `sub` cho hai người khác nhau; email có thể đổi hoặc được tái sử dụng. OIDC còn có thể dùng subject dạng **pairwise**, khiến `sub` khác nhau giữa các nhóm Client.

Các claim `email`, `preferred_username`, `name` hỗ trợ hiển thị hoặc đối chiếu khi chính sách cho phép; chúng không mặc định là khóa định danh bất biến, cũng không tự động cấp quyền API.

### 5.2. Phân biệt subject và ứng dụng được cấp token

Giả sử access token chứa:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-842",
  "client_id": "shop-web",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Ý nghĩa dự kiến của hợp đồng này:

- **`sub`:** người dùng được đại diện trong token.
- **`client_id`:** ứng dụng đã được cấp token.
- **`aud`:** API mà token có thể được trình cho.
- **`scope`:** nhóm hành động đã được cấp.

Trong token machine-to-machine:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "batch-sync-service",
  "client_id": "batch-sync-service",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Hai token trên có thể cùng scope nhưng **không có cùng ngữ nghĩa danh tính**. API cần phân biệt chính sách “người dùng xem đơn hàng của mình” với “batch service được phép đồng bộ đơn hàng”; có thể dùng claim về loại chủ thể, loại grant hoặc ràng buộc Client theo hợp đồng issuer. Không suy diễn các thuộc tính đó từ `sub` một cách tùy tiện.

### 5.3. Claims từ token và dữ liệu đang thay đổi

Một JWT hợp lệ chỉ chứng minh nhà phát hành đã phát biểu các claim tại thời điểm cấp. Trạng thái tài khoản, vai trò và thành viên tenant có thể thay đổi trong khi access token vẫn còn hiệu lực. Đối với quyền nhạy cảm cần hiệu lực ngay, API có thể cần tra cứu chính sách mới nhất, dùng token sống ngắn, introspection hoặc cơ chế thu hồi thích hợp.

Nếu token có claim `tenant_id`, điều đó không bảo đảm caller được đọc mọi bản ghi của tenant ấy. API vẫn cần kiểm tra tài nguyên được yêu cầu và quan hệ của caller với tenant theo chính sách nghiệp vụ.

## 6. Viết hợp đồng cụ thể trước khi cấu hình Spring Security

Một bản hợp đồng tích hợp nên mô tả giá trị cụ thể và bên sở hữu cho từng thông tin:

| Hạng mục | Thỏa thuận ví dụ | Bên có trách nhiệm |
| --- | --- | --- |
| Issuer tin cậy | `https://identity.example.test/realms/shop` | AS công bố; Client/API cấu hình |
| Định danh API | `orders-api` | Kiến trúc API và AS thống nhất |
| Client đăng ký | `shop-web`, `batch-sync-service` | AS đăng ký; Client sử dụng |
| Loại token | JWT access token được ký; thuật toán/khóa theo chính sách | AS phát hành; API xác minh |
| Audience của Orders API | `aud` phải chứa `orders-api` | AS phát hành; API kiểm tra |
| Scope có thể cấp | `orders.read`, `orders.write`, `orders.cancel` | AS cấu hình chính sách; API định nghĩa hiệu lực |
| Ánh xạ claim quyền | Ví dụ `scope` dạng chuỗi phân cách bằng khoảng trắng | AS cấp; API chuyển thành authorities |
| Định nghĩa subject | User subject cho authorization code, service principal cho client credentials | AS công bố; API diễn giải |
| Danh tính tenant | Claim `tenant_id` hoặc tra cứu server-side theo `(iss, sub)` | AS/API nhất trí nguồn tin cậy |
| Độ dài token và thu hồi | Thời hạn sống, cơ chế refresh/introspection/revocation nếu cần | AS định nghĩa; Client/API thực thi |
| Chính sách authorization | Scope endpoint **và** ownership, tenant, role/attribute | API và dịch vụ nghiệp vụ |
| Kết quả khi từ chối | 401 nếu không xác thực được; 403 nếu đã xác thực nhưng thiếu quyền | API |

Hợp đồng cũng phải ghi rõ **giá trị audience theo môi trường** (dev/test/prod), URI công bố JWKS, quy ước quay vòng khóa, khác biệt giữa OAuth access token và OIDC ID token, cũng như hướng xử lý thay đổi schema token.

### Ví dụ chính sách endpoint

| Endpoint | Audience | Scope | Điều kiện nghiệp vụ bổ sung |
| --- | --- | --- | --- |
| `GET /api/orders/{id}` | `orders-api` | `orders.read` | Người dùng sở hữu đơn hoặc có quyền hỗ trợ trong tenant |
| `POST /api/orders` | `orders-api` | `orders.write` | Caller được phép tạo đơn trong tenant của request |
| `POST /api/orders/{id}/cancel` | `orders-api` | `orders.cancel` | Đơn có thể hủy và caller là chủ đơn/nhân sự được ủy quyền |
| `GET /internal/orders/export` | `orders-api` | `orders.export` | Chỉ Client dịch vụ được cho phép; ghi audit theo chính sách |

Các điều kiện ở cột cuối **không thể suy ra chỉ từ scope**. Một cách làm hữu ích là tách kiểm tra thô ở security filter, còn kiểm tra ownership/tenant/điều kiện trạng thái tại service nghiệp vụ.

## 7. Resource Server kiểm tra hợp đồng trong Spring Security

Ví dụ dưới đây dùng **Spring Boot với Spring Security 6**, Orders API chấp nhận JWT access token có:

- `iss` đúng issuer đã thỏa thuận;
- `aud` chứa `orders-api`;
- token còn hiệu lực và chữ ký hợp lệ;
- scope cần thiết với từng endpoint;
- quyền đối với bản ghi thực tế, được kiểm tra trong service nghiệp vụ.

Dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 7.1. Cấu hình issuer và khóa xác minh

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/shop
          jwk-set-uri: https://identity.example.test/realms/shop/protocol/openid-connect/certs

app:
  security:
    expected-audience: orders-api
~~~

`issuer-uri` phải khớp chính xác `iss` trong token, và `jwk-set-uri` phải là JWKS endpoint thực sự được Authorization Server công bố. Đường dẫn trong ví dụ chỉ minh họa dạng triển khai; sản phẩm Identity Provider khác có thể dùng URL khác. Khi cung cấp `jwk-set-uri` trực tiếp, API không cần khám phá khóa qua metadata vào thời điểm khởi động, nhưng vẫn phải kiểm tra issuer.

### 7.2. Xác minh audience bổ sung vào kiểm tra JWT mặc định

Trong API, có thể định nghĩa `JwtDecoder` xác minh chữ ký bằng JWKS rồi dùng validators cho issuer, thời hạn và audience:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwkSetUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        // Bao gồm các kiểm tra mặc định, thời hạn và issuer.
        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        // Token của API khác phải bị từ chối, dù cùng issuer ký.
        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Token audience is not accepted",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience));

        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đoạn code tập trung vào hợp đồng token và authorization ở endpoint. Nếu đây là REST API chỉ dùng Bearer token, việc cấu hình CSRF, session và các filter chain khác cần thực hiện theo kiến trúc thực tế. Không sao chép cấu hình API sang phần ứng dụng web sử dụng cookie mà bỏ qua bảo vệ CSRF.

Ở Spring Security, khi nhận JWT có claim `scope` hoặc `scp` theo định dạng được hỗ trợ, authorities mặc định thường có tiền tố `SCOPE_`. Vì vậy scope `orders.read` trong token được đối chiếu với `hasAuthority("SCOPE_orders.read")`. Nếu issuer dùng tên claim hay quy ước role riêng, cần cấu hình `JwtAuthenticationConverter` thay vì giả định mapping mặc định luôn đúng.

**Ranh giới quan trọng:** `hasAuthority("SCOPE_orders.read")` chỉ bảo vệ loại hành động. Service xử lý `/api/orders/{id}` vẫn phải kiểm tra người dùng/dịch vụ hiện tại có được xem **đơn hàng cụ thể** hay không.

### 7.3. Kiểm tra quyền trên tài nguyên

Để đưa danh tính từ access token đã được xác minh tới nghiệp vụ:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    OrderDto getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        return orders.getVisibleOrder(
                id,
                jwt.getIssuer().toString(),
                jwt.getSubject());
    }
}
~~~

`getVisibleOrder` phải tra cứu bản ghi trong phạm vi caller được phép và thực hiện kiểm tra ownership, tenant, role hoặc các điều kiện khác, sau đó từ chối nếu không đạt. Đoạn code trên là ví dụ **chuyển subject/issuer đã được xác minh** tới service; nó không tự chứng minh service đã kiểm tra quyền. Nếu API hỗ trợ cả Client không có người dùng cuối, cần bổ sung phân biệt loại chủ thể, Client và chính sách service-to-service trước khi truy vấn dữ liệu.

### 7.4. Nếu là opaque access token

Khi dùng opaque token, Resource Server có thể kiểm tra token bằng introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

API phải kiểm tra trạng thái `active` của token và **đảm bảo audience, quyền, danh tính từ kết quả introspection phù hợp hợp đồng**. Không phải mọi introspection response đều có cùng trường; nếu thiếu thông tin để xác định token dành cho Orders API, cần thống nhất cách công bố/kiểm tra với Authorization Server, không bỏ qua điều kiện audience. Cơ chế introspection không làm biến mất trách nhiệm kiểm tra quyền nghiệp vụ.

## 8. Tách hợp đồng đăng nhập OIDC khỏi hợp đồng gọi API

Trong luồng Authorization Code có OIDC, một Client có thể yêu cầu scope `openid profile` và đồng thời xin `orders.read` để truy cập Orders API. Hợp đồng cần tách:

| Vấn đề | OIDC Client (đăng nhập) | OAuth2 Resource Server (gọi API) |
| --- | --- | --- |
| Token dùng cho mục đích chính | **ID token** để xác nhận đăng nhập | **Access token** để bảo vệ API |
| Audience mong đợi | `client_id` của OIDC Client | Định danh API, ví dụ `orders-api` |
| Dữ liệu danh tính | `sub` và claim OIDC, kiểm tra theo OIDC | Subject/Client/scope trong access token theo hợp đồng API |
| Kiểm tra quyền API | Không quyết định thay API | Xác minh token và thực thi policy |
| Claim quan trọng khác | `nonce` khi áp dụng, `auth_time` khi được yêu cầu, các điều kiện OIDC liên quan | `iss`, `aud`, thời hạn, scope/authority, tenant và quyền nghiệp vụ |

ID token chỉ được Client xử lý như bằng chứng xác thực khi qua **đúng quy trình xác minh OIDC** (chữ ký, issuer, audience, nonce và các điều kiện liên quan). Resource Server không nên sử dụng ID token làm credential truy cập API.

Nếu Shop BFF vừa cho người dùng đăng nhập bằng `oauth2Login()` vừa gọi Orders API bằng `oauth2Client()`, hai cấu hình này thực hiện phần Client. Orders API ở tiến trình khác hoặc cùng tiến trình vẫn phải bật `oauth2ResourceServer()` cho endpoint nhận Bearer token.

## 9. Các tình huống thể hiện lỗi hợp đồng

### Tình huống A — Issuer đúng nhưng audience sai

Client nhận token có `aud = payments-api` rồi gửi tới Orders API. Chữ ký hợp lệ và người dùng có danh tính hợp lệ nhưng Orders API phải từ chối (thường 401 do token không hợp lệ với API này). Cách giải quyết là **Client xin token cho đúng resource** và Authorization Server phát hành đúng audience; không nới rộng quy tắc Orders API để chấp nhận mọi token cùng issuer.

### Tình huống B — Audience đúng nhưng thiếu quyền

Token có `aud = orders-api`, `scope = orders.read`. Client gửi `POST /api/orders`, endpoint đòi `orders.write`. API từ chối 403. Client phải xin đúng scope theo chính sách; Authorization Server chỉ cấp nếu Client/chủ thể được phép. Không thay quyền bằng việc Client tự gửi header `X-Role: admin`.

### Tình huống C — Đủ scope nhưng dữ liệu không thuộc chủ thể

Token của `user-842` có `orders.read` và audience đúng, nhưng đơn 42 thuộc `user-999`. API phải từ chối (có thể 403 hoặc 404 tùy chính sách ẩn tài nguyên). Chỉ dựa vào scope sẽ gây lộ dữ liệu giữa người dùng/tenant.

### Tình huống D — Dùng ID token gọi API

Shop Web nhận ID token với `aud = shop-web` rồi gửi nó tới Orders API. API phải từ chối vì đó là token dành cho Client đăng nhập, không phải token có quyền dành cho Orders API.

### Tình huống E — Client credentials bị coi là người dùng

Một job đồng bộ dùng `client_credentials` có scope `orders.read`. Code API lấy `sub` rồi đi tìm hồ sơ khách hàng cùng ID và áp dụng quyền xem đơn hàng của người dùng. Điều này sai mô hình chủ thể: API phải áp dụng **chính sách dành cho service principal** và chỉ cho phép các thao tác/nguồn dữ liệu được cấp rõ.

### Tình huống F — Chuyển tiếp token qua nhiều API

Client gọi Gateway API với `aud = gateway-api`; Gateway muốn gọi Orders API. Việc chuyển tiếp nguyên token chỉ hợp lệ nếu hợp đồng của Orders API **thực sự** cho phép audience và mô hình delegation tương ứng. Cách thường dùng là xin access token riêng cho Orders API hoặc áp dụng token exchange được Authorization Server hỗ trợ.

## 10. Quy ước lỗi, log và thay đổi hợp đồng

Để Client chẩn đoán được nguyên nhân, API nên thống nhất hành vi lỗi theo cơ chế Bearer token (RFC 6750):

| Điều kiện | Phản hồi điển hình | Bên thường cần hành động |
| --- | --- | --- |
| Thiếu token, hết hạn, chữ ký/issuer/audience không hợp lệ | **401 Unauthorized**, có thể kèm `WWW-Authenticate: Bearer ...` | Client xin token đúng/đăng nhập lại; AS/API xác nhận cấu hình |
| Token hợp lệ nhưng thiếu scope cần thiết | **403 Forbidden**, có thể nêu `insufficient_scope` | Client xin quyền phù hợp; AS quyết định cấp |
| Token và scope hợp lệ nhưng thiếu quyền trên bản ghi | **403** hoặc **404** theo chính sách bảo mật | API thực thi chính sách; Client không tự nâng quyền |
| Token hợp lệ, đủ scope và quyền nghiệp vụ | **2xx** hoặc mã nghiệp vụ tương ứng | API xử lý request |

Khi log để hỗ trợ chẩn đoán, nên ghi **request/correlation ID, issuer, audience, Client, subject đã xác minh (khi chính sách cho phép), loại lỗi và tên scope**, tránh ghi nguyên Bearer token hoặc thông tin nhạy cảm từ token. Ở hệ thống nhiều tenant, cần giới hạn quyền truy cập log phù hợp.

Hợp đồng có thể thay đổi khi bổ sung API, thêm audience, chuyển nhà phát hành hoặc đổi định dạng claim. Quá trình chuyển đổi cần được triển khai đồng bộ:

1. **Thống nhất phiên bản/thay đổi:** API định nghĩa audience và quyền mới; Authorization Server cấu hình khả năng cấp; Client chuẩn bị xin token mới.
2. **Hỗ trợ giai đoạn chuyển tiếp có kiểm soát:** Chấp nhận nhiều issuer/audience **chỉ nếu** chính sách thực sự cho phép và mỗi bên được xác minh đầy đủ; tránh wildcard hoặc bỏ kiểm tra để “chạy được”.
3. **Quay vòng khóa an toàn:** API lấy/cập nhật JWKS theo cơ chế thư viện và tin vào thuật toán được chấp nhận; không gắn một khóa công khai mãi mãi.
4. **Đánh giá thu hồi và thời hạn:** JWT được kiểm tra cục bộ có thể còn hiệu lực tới `exp` nếu không áp dụng biện pháp thu hồi bổ sung; chọn thời hạn và chính sách theo rủi ro.
5. **Quan sát lỗi 401/403 khi triển khai:** Gia tăng đột biến có thể chỉ ra cấu hình issuer, audience, scope hoặc mapping claim không tương thích.

## 11. Mẫu hợp đồng để các đội triển khai cùng nhau

Một tài liệu tích hợp API có thể đưa ra mẫu ngắn nhưng đủ kiểm chứng như sau:

~~~yaml
api: orders-api
issuer: https://identity.example.test/realms/shop
accepted_token_use: oauth2_access_token
access_token_format: jwt
expected_audience:
  - orders-api
accepted_clients:
  - shop-web
  - batch-sync-service
scopes:
  orders.read: Read orders allowed by the caller's data policy
  orders.write: Create or update orders allowed by policy
identity:
  user: "Pair (iss, sub); tenant membership checked by API"
  service: "client_credentials subject/client mapped to service policy"
authorization:
  GET /api/orders/{id}: "orders.read + ownership/tenant policy"
  POST /api/orders: "orders.write + tenant creation policy"
errors:
  invalid_or_missing_token: 401
  insufficient_scope_or_permission: 403
~~~

Đây là **mẫu tài liệu hợp đồng**, không phải định dạng cấu hình chuẩn được Spring Security hoặc OAuth 2.0 tự động đọc. Các đội cần chuyển từng điều khoản thành Client registration, quy tắc cấp token tại Authorization Server, cấu hình validator của Resource Server và kiểm tra quyền trong nghiệp vụ.

Khi xác định hợp đồng, hãy luôn đọc bốn câu hỏi cùng nhau: **“Ai phát hành?”** (`iss`), **“Token dành cho ai?”** (`aud`), **“Được phép làm gì?”** (`scope` và chính sách) và **“Đang đại diện cho ai?”** (`sub`, Client và ngữ cảnh grant). Trong Spring Security Resource Server, chấp nhận token chỉ sau khi cả những điều kiện liên quan đã được xác minh, rồi áp dụng quyền đối với tài nguyên thực tế.
