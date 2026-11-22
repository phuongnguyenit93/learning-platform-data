# Bảo vệ API bằng resource server, quyền đối tượng và cách ly tenant

Một REST API có thể kiểm tra JWT hợp lệ, trả `401 Unauthorized` khi thiếu token và vẫn mắc lỗ hổng nghiêm trọng: người dùng Alice thay UUID trong URL rồi đọc được đơn hàng của Bob. Một ứng dụng đa tenant còn có nguy cơ lớn hơn: token thuộc tenant A nhưng chỉ cần đổi `X-Tenant-Id` hoặc `tenantId` trong JSON là ghi dữ liệu vào tenant B. Đây là các dạng **Broken Object Level Authorization (BOLA/IDOR)** và **thiếu cách ly tenant**. Chúng không được giải quyết chỉ bằng chữ ký JWT hoặc annotation `hasRole("USER")`.

Bài **thực hành tổng hợp** thuộc mô-đun **INTEGRATION_API_REST**, nơi người học thiết kế resource, URI, phương thức và mã trạng thái HTTP, hợp đồng JSON/OpenAPI, phân trang, idempotency, xác thực, phân quyền, xử lý lỗi và kiểm thử API với Java/Spring. Bài tập dùng **Spring Boot 3, Spring Security 6, OAuth2 Resource Server và PostgreSQL** để xây một API đặt hàng đa tenant. Người học phải chứng minh ba hàng rào độc lập: **token đáng tin**, **quyền thực thi chức năng**, và **quyền đối với từng bản ghi trong đúng tenant**.

> **Kết quả mong muốn:** request không có token nhận 401; token thiếu scope nhận 403; token có scope nhưng truy cập object của người khác hoặc tenant khác không nhận dữ liệu, không thay đổi trạng thái; người dùng có quyền trên resource hợp lệ mới đọc/ghi thành công. Đó là một hợp đồng quan sát được, không chỉ là cấu hình security trông có vẻ đúng.

## 1. Bối cảnh, mục tiêu và phạm vi bài lab

Giả sử một nền tảng thương mại phục vụ nhiều doanh nghiệp. Mỗi doanh nghiệp là **tenant**. Người dùng trong cùng tenant có thể có quyền khác nhau:

- **Khách hàng:** tạo đơn của chính mình, đọc danh sách đơn của mình, đọc/hủy đơn thuộc quyền khi trạng thái cho phép.
- **Quản trị tenant:** đọc mọi đơn **trong tenant của mình** nếu token được cấp `orders.admin`; không có quyền đọc tenant khác.
- **Dịch vụ tích hợp:** nhận access token do nhà cung cấp danh tính cấp với phạm vi tối thiểu; không tự biến client credential thành quyền quản trị mọi tenant.

Trong ví dụ, một access token chỉ đại diện cho **một tenant đang hoạt động** thông qua claim `tenant_id`. Nếu người dùng thuộc nhiều tenant, họ phải chọn tenant và được phát hành một access token mới cho tenant đó; không tin giá trị tenant do client tự sửa trong header/path/body. Ở hệ thống thật, cách cấp tenant claim, quyền thành viên và quản trị được quyết định bởi identity provider và authorization service của tổ chức.

### 1.1. Mục tiêu sau khi hoàn thành

1. Cấu hình resource server kiểm tra chữ ký JWT từ JWKS đáng tin, `iss`, `aud`, `exp`, `nbf` và dạng access token được nhà phát hành quy định.
2. Sử dụng `SecurityFilterChain` để bảo vệ HTTP method và endpoint theo scope, không tạo route công khai ngoài chủ đích.
3. Đặt logic **object-level authorization** ở service/data layer: chủ sở hữu hoặc tenant admin được xem object **trong đúng tenant**.
4. Chống giả mạo `tenantId`/`ownerId` qua request body, query/header và chống mass assignment.
5. Thiết kế query lọc tenant ngay tại database, kể cả list/pagination/cancel, không chỉ lọc danh sách sau khi lấy tất cả dữ liệu.
6. Kiểm thử matrix 401/403/404/2xx, tenant isolation, replay/idempotency, race condition và xác thực JWT thật.
7. Ghi nhận logs/metrics/traces có ích nhưng không tiết lộ token, PII hay sự tồn tại của resource bị cấm.

### 1.2. Sản phẩm cần bàn giao

| Hạng mục | Đầu ra | Điều kiện nghiệm thu |
| --- | --- | --- |
| API contract | Bảng endpoint, request/response và lỗi, có thể biểu diễn thành OpenAPI | Không nhận tenant/owner từ dữ liệu không đáng tin |
| Security config | Spring Security OAuth2 Resource Server | JWT không hợp lệ bị loại; đúng scope mới vào handler |
| Domain/data | Đơn hàng có tenant, chủ sở hữu và trạng thái | Query, unique/index, transaction bảo vệ các ranh giới |
| Authorization service | Logic kiểm tra principal, tenant, owner/admin | Không đọc/sửa chéo tenant kể cả đoán được ID |
| Error handling | 401/403/404/409/Problem Details nhất quán | Không lộ nội bộ hoặc sự tồn tại object ngoài quyền |
| Tests | Unit, MockMvc, integration DB, token validation và smoke test | Có đủ trường hợp dương/âm và kiểm tra side effect |
| Tài liệu vận hành | Bảng quyền, runbook, log/metrics và các giả định | Có thể tái hiện và đánh giá rủi ro còn lại |

Không bắt buộc xây một máy chủ OAuth2/OIDC riêng. Resource server **tiêu thụ access token** do authorization server phát hành; bài tập tập trung vào xác minh token và áp dụng authorization trong API.

## 2. Phân biệt authentication, function và object authorization

Một request có thể đi qua nhiều quyết định:

~~~mermaid
flowchart TD
    A["HTTP request + Bearer token"] --> B{"JWT signature / issuer / audience / expiry hợp lệ?"}
    B -- "Không" --> C["401 Unauthorized"]
    B -- "Có" --> D{"Có scope cho HTTP action?"}
    D -- "Không" --> E["403 Forbidden"]
    D -- "Có" --> F["Lấy tenant từ token đã xác minh"]
    F --> G["Query record có tenant_id = token tenant"]
    G --> H{"Object tồn tại trong tenant?"}
    H -- "Không" --> I["404 Not Found"]
    H -- "Có" --> J{"Owner hoặc tenant admin được phép?"}
    J -- "Không" --> K["404 che tồn tại theo policy"]
    J -- "Có" --> L["Xử lý nghiệp vụ và trả 2xx/409"]
~~~

**Authentication** chứng minh request trình diện token thỏa quy tắc xác minh; chưa chứng minh người gọi có quyền với một đơn hàng cụ thể. **Function-level authorization** kiểm tra token có scope cho thao tác, ví dụ `orders.read`. **Object-level authorization** kiểm tra đơn hàng tìm thấy thuộc tenant và principal được phép tiếp cận.

| Cơ chế | Ví dụ kiểm tra | Không thể thay thế |
| --- | --- | --- |
| Xác thực token | JWT đúng chữ ký, `iss`, `aud` và thời hạn | Quyền đối với object |
| Scope/authority | `SCOPE_orders.write` cho `POST` tạo đơn | Quyền hủy đơn của Bob |
| Tenant isolation | `WHERE tenant_id = :verifiedTenant` | Quyền xem toàn bộ đơn trong tenant |
| Object authorization | `owner_id == sub` hoặc tenant admin | Token validation và phân quyền endpoint |
| Database constraint | `UNIQUE`, foreign key, `@Version` | Quyền truy cập; constraint không hiểu user là ai |

Không đặt toàn bộ trách nhiệm phân quyền ở controller hoặc UI. Client có thể gọi API trực tiếp; controller khác, scheduled worker, GraphQL resolver hoặc một endpoint export mới có thể vô tình bỏ qua một check. Service/data access phải có ranh giới rõ và các tests chống regression.

## 3. Mô hình đe dọa của API đa tenant

### 3.1. Những tài sản cần bảo vệ

- Dữ liệu đơn hàng: giá, trạng thái, item, thông tin khách hàng, chủ sở hữu và tenant.
- Khả năng tạo/hủy đơn, giữ tồn kho, tính phí và phát event.
- Token, session và thông tin định danh của principal.
- Các kết quả phân trang, download/export, cache và job bất đồng bộ có thể chứa dữ liệu của tenant.

### 3.2. Những hành vi đối kháng phải thử

| Hành vi | Ví dụ | Lỗi nếu không phòng vệ |
| --- | --- | --- |
| Đoán ID object | Alice đổi `/orders/{aliceId}` thành UUID của Bob | BOLA/IDOR, đọc hoặc sửa đơn người khác |
| Đổi tenant trong body | `{"tenantId":"tenant-b",...}` | Mass assignment/cross-tenant write |
| Gửi header giả | `X-Tenant-Id: tenant-b` | Tenant spoofing nếu server tin header |
| Dùng token đúng issuer nhưng sai audience | Token phát cho `billing-api` gọi `orders-api` | Token substitution/confused deputy |
| Token hết hạn hoặc chưa có hiệu lực | `exp` cũ / `nbf` tương lai | Đăng nhập giả hợp lệ |
| Token ký sai/`alg:none`/`kid` giả | JWT bị sửa payload hoặc trỏ key lạ | Bỏ qua xác thực chữ ký hoặc trust sai |
| Thiếu scope | Token chỉ `orders.read` gọi `POST` | Broken Function Level Authorization |
| Thêm field bất hợp lệ | `ownerId`, `status:"SHIPPED"` trong create | Mass assignment, escalation nghiệp vụ |
| Phân trang không lọc tenant | `GET /orders?cursor=...` | Rò dữ liệu khi trả list, count hoặc cursor |
| Race cancel/modify | Hai request cập nhật cùng order | Lost update, side effect lặp |
| Retry cùng nghiệp vụ bằng hai request | Mất response rồi gửi lại `POST` | Đơn/charge bị tạo hai lần |
| Cache trộn principal/tenant | Cache key chỉ bằng URI | Trả response của người khác dù service có check |

ID khó đoán như UUID chỉ giảm khả năng đoán ngẫu nhiên; nó **không phải cơ chế phân quyền**. Một ID có thể lộ qua log, liên kết, email, analytics, event hoặc bug frontend. Test phải dùng một ID của tenant khác **đã biết** để xác minh bảo vệ, không chỉ thử UUID ngẫu nhiên không tồn tại.

## 4. Đặc tả API cho bài tập

Giả định base path `/api/v1`; mọi endpoint nghiệp vụ yêu cầu bearer access token. Các scope được phát theo chuẩn ví dụ `orders.read`, `orders.write` và `orders.admin`. Spring Security mặc định chuyển scope thành authority có tiền tố `SCOPE_`; tên scope của hệ thống thật do issuer quyết định.

| Method/path | Scope cần thiết | Ai được thực hiện | Thành công | Thất bại chính |
| --- | --- | --- | --- | --- |
| `POST /api/v1/orders` | `orders.write` | Tạo đơn cho `sub`, tenant lấy từ token | `201 Created` + `Location` | `400` validation, `401`, `403`, `409` idempotency |
| `GET /api/v1/orders` | `orders.read` **hoặc** `orders.admin` | Khách: danh sách của mình; admin: danh sách tenant | `200 OK`, phân trang | `401`, `403` |
| `GET /api/v1/orders/{id}` | `orders.read` **hoặc** `orders.admin` | Owner hoặc tenant admin của chính tenant | `200 OK` | `401`, `403`, `404` |
| `POST /api/v1/orders/{id}/cancel` | `orders.write` | Owner hoặc tenant admin theo policy | `200 OK` với trạng thái mới | `401`, `403`, `404`, `409` |

Chính sách thực hành: **đối với một đơn ngoài phạm vi có thể đọc, API trả 404** để không tiết lộ nó có tồn tại. Đối với hành động gọi endpoint không có scope, **403**. Đây là quyết định thiết kế; hệ thống khác có thể chọn 403 cho resource thuộc cùng tenant nhưng không có quyền nếu việc tiết lộ tồn tại được phép. Điều quan trọng là chính sách rõ ràng, nhất quán và có test.

### 4.1. JSON request/response

Client tạo đơn, **không được gửi** tenant hoặc owner:

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: "create-order-92"
Content-Type: application/json

{
  "skuId":"11111111-1111-4111-8111-111111111111",
  "quantity":2
}
~~~

Trả response:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f
Content-Type: application/json
Cache-Control: no-store

{
  "id":"8c9b4ca4-2211-4cd0-a949-d176bcb8e35f",
  "status":"PENDING",
  "quantity":2
}
~~~

Ví dụ không trả `tenantId`/`ownerId` nếu client không cần; điều này không thay thế query tenant-scoped. `Idempotency-Key` có thể được quy định bắt buộc cho thao tác tạo đơn nếu hệ thống hứa replay an toàn. Nếu scope bài làm chưa hoàn thiện idempotency store, hãy ghi rõ đây là **nhiệm vụ mở rộng bắt buộc trước production**, không tuyên bố endpoint đã idempotent chỉ vì có header.

### 4.2. Error contract

Các lỗi ứng dụng có thể dùng Problem Details:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.test/problems/order-not-found",
  "title":"Order not found",
  "status":404,
  "code":"ORDER_NOT_FOUND"
}
~~~

Không đưa tenant tồn tại, owner thật, SQL, stack trace, token, địa chỉ nội bộ hoặc ID tài nguyên bị cấm vào body lỗi. Với `401`, resource server thông thường trả `WWW-Authenticate: Bearer ...`; với `403` thiếu scope, tùy thiết lập có thể có thông tin `insufficient_scope`. Các thông báo lỗi nên ngắn và không rò dữ liệu. Security filter tạo 401/403 **trước khi controller chạy**, nên `@RestControllerAdvice` không mặc nhiên kiểm soát chúng.

## 5. Kiến trúc solution và lớp chịu trách nhiệm

~~~mermaid
flowchart LR
    C["Client"] -->|"Bearer access token"| S["Spring Security FilterChain"]
    S -->|"JwtDecoder: signature/iss/aud/time"| A["Controller + @Valid DTO"]
    A --> P["OrderService: object authorization"]
    P --> R["Repository: tenant-scoped query"]
    R --> D[("PostgreSQL")]
    S -.->|"JWKS cache/fetch"| I["Trusted Identity Provider"]
    M["Metrics, logs, traces"] -.-> S
    M -.-> P
~~~

Thiết kế tách nhiệm vụ:

- **Identity provider/authorization server** cấp JWT access token và xác định người dùng, tenant đang hoạt động, scopes. API **không** tự ký token giả để “chứng minh” mình là resource server.
- **Resource server filter chain** xác minh JWT, ánh xạ scope thành authorities, quyết định được phép gọi **loại endpoint** nào.
- **Controller** bind/validate request; lấy danh tính từ Spring Security, không tin user/tenant trong JSON.
- **Service** kiểm tra object-level permission và điều kiện nghiệp vụ; không dựa vào UI đã ẩn nút.
- **Repository/DB** luôn giới hạn tenant ở truy vấn; DB constraint/transaction bảo vệ cạnh tranh và nhất quán.
- **Observability/tests** chứng minh response và side effect; không chỉ kiểm thử một annotation đơn lẻ.

### 5.1. Gợi ý cấu trúc thành phần

~~~text
security/
  SecurityConfig.java
  JwtDecoderConfig.java
  AccessContext.java
orders/
  OrderController.java
  PlaceOrderRequest.java
  OrderReceipt.java
  OrderService.java
  OrderRepository.java
  OrderEntity.java
  OrderErrors.java
test/
  OrderSecurityMvcTest.java
  OrderTenantIsolationIT.java
  JwtVerificationIT.java
~~~

Cây trên minh họa **tên lớp/đầu ra bài tập**, không yêu cầu học viên tạo chính xác cấu trúc package này. Tất cả code trong bài cần được ghép với import, bean, schema và cấu hình của dự án thực; các đoạn được đánh dấu “phác thảo” không phải một repository chạy sẵn.

## 6. Khởi tạo Spring Boot OAuth2 Resource Server

Các dependency Gradle (giả định dự án dùng Spring Boot dependency management, không tự trộn phiên bản Spring):

~~~gradle
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.boot:spring-boot-starter-oauth2-resource-server"
    implementation "org.springframework.boot:spring-boot-starter-validation"
    implementation "org.springframework.boot:spring-boot-starter-data-jpa"
    runtimeOnly "org.postgresql:postgresql"

    testImplementation "org.springframework.boot:spring-boot-starter-test"
    testImplementation "org.springframework.security:spring-security-test"
    testImplementation "org.springframework.boot:spring-boot-testcontainers"
    testImplementation "org.testcontainers:junit-jupiter"
    testImplementation "org.testcontainers:postgresql"
}
~~~

Với OAuth2 Resource Server JWT, Spring Boot/Security sử dụng các thành phần xác minh JOSE/JWT cần thiết khi starter tương ứng được cài. Không thêm bộ thư viện JWT tự chế trong controller để parse payload rồi coi claim là đáng tin.

Cấu hình ví dụ trong `application.yml`:

~~~yaml
security:
  jwt:
    issuer: https://idp.example.test/realms/commerce
    jwk-set-uri: https://idp.example.test/realms/commerce/protocol/openid-connect/certs
    audience: orders-api

spring:
  datasource:
    url: jdbc:postgresql://db:5432/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  jpa:
    open-in-view: false
~~~

Các URL, tên database, biến môi trường chỉ là ví dụ; không chứa secret thật. Trong môi trường thực, issuer/JWKS URI phải được lấy từ cấu hình tin cậy, kết nối HTTPS và xác minh chứng chỉ đúng. Không chọn `jwk-set-uri` theo `iss` hoặc `jku` tự khai trong JWT chưa kiểm chứng. Có thể dùng Spring Boot property `spring.security.oauth2.resourceserver.jwt.issuer-uri` để thiết lập chuẩn, nhưng bài này minh họa một bean `JwtDecoder` riêng nhằm cho thấy kiểm tra **audience** một cách tường minh; không cấu hình trùng hai decoder mà không hiểu thứ tự bean.

## 7. Kiểm tra chữ ký, issuer, audience và thời hạn JWT

Một JWT access token có thể chứa claims giống sau:

~~~json
{
  "iss":"https://idp.example.test/realms/commerce",
  "sub":"alice",
  "aud":["orders-api"],
  "exp":1795000000,
  "nbf":1794990000,
  "iat":1794990000,
  "scope":"orders.read orders.write",
  "tenant_id":"tenant-a",
  "token_use":"access"
}
~~~

Payload trên **chỉ là minh họa**, không phải JWT đã ký hoặc token hợp lệ tại thời điểm chạy. Quyền truy cập không được cấp vì ai đó gửi một chuỗi base64 chứa `"tenant_id":"tenant-a"`; decoder phải xác minh chữ ký theo key/thuật toán được tin, issuer, audience và thời gian. Giá trị `sub` chỉ có ý nghĩa trong namespace của issuer (khi nhiều issuer, nên có định danh tổng hợp hoặc một mapping nội bộ ổn định).

### 7.1. Decoder giới hạn key nguồn và audience

Ví dụ dùng Spring Security 6:

~~~java
@Configuration
public class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${security.jwt.issuer}") String issuer,
            @Value("${security.jwt.jwk-set-uri}") String jwks,
            @Value("${security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwks)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience không phù hợp",
                        null));

        OAuth2TokenValidator<Jwt> accessTypeValidator = jwt ->
            "access".equals(jwt.getClaimAsString("token_use"))
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token không phải access token",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator,
                accessTypeValidator));

        return decoder;
    }
}
~~~

Các import được lược bớt: `@Configuration`, `@Bean`, `@Value`, `NimbusJwtDecoder`, `SignatureAlgorithm`, `Jwt`, `JwtValidators`, `OAuth2TokenValidator`, `OAuth2TokenValidatorResult`, `DelegatingOAuth2TokenValidator`, `OAuth2Error`. `JwtValidators.createDefaultWithIssuer` kiểm tra các điều kiện thời gian/thông tin chuẩn trong cấu hình tương ứng; phải kiểm tra hành vi thực tế của phiên bản Spring Security đang dùng. Decoder chỉ chấp nhận **RS256** trong ví dụ; thuật toán phải khớp chính sách của identity provider, không thay bằng thuật toán tùy ý từ header token.

`token_use` là claim **mang tính quy ước**, chỉ dùng khi issuer được chọn thực sự phát hành nó. Nếu nhà phát hành dùng `typ=at+jwt` hoặc một quy tắc nhận dạng access token khác, cần điều chỉnh validation theo hợp đồng issuer, không tự yêu cầu một claim không có. Đặc biệt không chấp nhận ID token (dành cho client OIDC) thay thế access token chỉ vì nó có chữ ký hợp lệ.

### 7.2. Cần xác minh những gì?

| Thành phần | Kiểm tra cần có | Rủi ro nếu bỏ |
| --- | --- | --- |
| Chữ ký | Signature hợp lệ với JWKS tin cậy | Client tự sửa role/tenant |
| `alg` | Chỉ thuật toán được cấu hình (ví dụ RS256) | Algorithm confusion/`none` |
| `iss` | Issuer chính xác theo cấu hình | Token từ hệ thống khác |
| `aud` | Chứa audience của orders API | Token cấp cho API khác được dùng lại |
| `exp`/`nbf` | Hiệu lực thời gian, clock skew có kiểm soát | Token hết hạn/chưa hiệu lực vẫn được chấp nhận |
| `sub` | Danh tính tồn tại, định dạng hợp lệ | Không thể phân biệt owner |
| `scope` | Chỉ quyền do issuer cấp; không lấy từ request body | Privilege escalation |
| `tenant_id` | Tenant được xác nhận từ token đáng tin và authorization policy | Truy cập chéo tenant |
| Loại token | Access token đúng loại theo provider | Chấp nhận nhầm ID/refresh token |
| JWKS/rotation | Fetch/cache key an toàn, xử lý `kid`/rotate | Mất xác minh hoặc tin nhầm key |

Đừng kiểm tra `aud` bằng so chuỗi thô nếu issuer phát hành mảng audience, và đừng chấp nhận `iss` chỉ vì host có cùng hậu tố. Khi issuer dùng nhiều key, JWKS rotation phải có cửa sổ chồng lấn/TTL hợp lý; failover của identity provider cũng cần được xem xét. Chính sách có nhiều issuer phải tách trust source và tenant namespace rõ ràng.

## 8. SecurityFilterChain: bảo vệ route bằng scope

Ở bài lab, API được gọi bằng `Authorization: Bearer ...` và **không sử dụng cookie để xác thực các endpoint này**. Cấu hình:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/v1/orders", "/api/v1/orders/*")
                    .hasAnyAuthority(
                        "SCOPE_orders.read", "SCOPE_orders.admin")
                .requestMatchers(HttpMethod.POST,
                    "/api/v1/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.POST,
                    "/api/v1/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ dùng Spring Security 6, import `HttpSecurity`, `HttpMethod`, `SessionCreationPolicy`, `AbstractHttpConfigurer` và `Customizer`. Đây là **một filter chain mặc định bao phủ toàn ứng dụng**: chỉ những endpoint được liệt kê mới có quyền truy cập và `anyRequest().denyAll()` từ chối mọi request khác, kể cả Actuator, Swagger hoặc route mới chưa được duyệt. Nếu cần public liveness hoặc management endpoint, phải khai báo chính sách có chủ đích và bảo vệ cổng quản trị. Khi chia thành nhiều `SecurityFilterChain` với `securityMatcher` riêng, cần **kiểm tra matcher và thứ tự chain**, đồng thời có một chain bắt mọi request còn lại để không vô tình bỏ lọt đường dẫn ngoài phạm vi bảo vệ.

`csrf(...disable)` **chỉ hợp lý cho API thực sự stateless với bearer token được client chủ động đặt vào header**, không dùng session cookie hoặc một cơ chế ambient credential tương đương. Nếu cùng ứng dụng còn endpoint browser dùng cookie session, cấu hình CSRF phải được tách đúng theo từng chain, không tắt toàn cục. Stateless **không tự làm mọi kiểu CSRF biến mất** nếu có các nguồn xác thực gửi tự động từ trình duyệt.

### 8.1. Scope và role không giống object permission

Chỉ `hasAuthority("SCOPE_orders.read")` không chứng minh rằng Alice được xem đơn của Bob. Nó chỉ cho phép **gọi loại endpoint đọc**. Nếu thêm `@PreAuthorize("hasAuthority('SCOPE_orders.read')")` ở service thì vẫn phải có kiểm tra owner và tenant trong câu query/quy tắc domain.

`orders.admin` trong ví dụ là quyền admin **bên trong tenant của token**, không phải quyền trên toàn bộ database. Không dùng `SCOPE_orders.admin` để bỏ qua tenant filter. Nếu có super-admin xuyên tenant thật, hãy xây một API, trust policy, audit và approval path riêng, không thêm ngoại lệ âm thầm vào query chung.

### 8.2. CORS và error status

Nếu frontend ở `https://app.example.test` gọi API từ browser, cấu hình CORS allowlist chính xác cho origin/method/header cần thiết; CORS cho phép browser đọc response trong điều kiện hợp lệ, **không xác thực** người gọi. Request `curl` không chịu ràng buộc CORS của browser. Không dùng `Access-Control-Allow-Origin: *` cùng credentials; không tin `Origin` như một bằng chứng tenant.

Request thiếu token → thường **401** tại bearer authentication entry point. Token hợp lệ nhưng thiếu authority → **403**. Lỗi BOLA sau khi vượt qua scope được xử lý trong service → **404** theo policy của bài. Tránh cấu hình handler chung biến mọi `AccessDeniedException` thành `200` hoặc status sai.

## 9. Claim tenant và AccessContext: nguồn tin cậy duy nhất

Ta cần một đối tượng ngữ cảnh đã xác thực, dùng xuyên service. Nó chỉ được tạo từ principal do Spring Security xác minh:

~~~java
public record AccessContext(
        String subject,
        String tenantId,
        boolean tenantAdmin) {

    public static AccessContext from(
            Jwt jwt, Authentication authentication) {
        String subject = jwt.getSubject();
        String tenant = jwt.getClaimAsString("tenant_id");

        if (subject == null || subject.isBlank()
                || tenant == null || tenant.isBlank()) {
            throw new AccessContextException(
                "Thiếu danh tính hoặc tenant hợp lệ");
        }
        boolean admin = authentication.getAuthorities().stream()
            .anyMatch(a ->
                a.getAuthority().equals("SCOPE_orders.admin"));
        return new AccessContext(subject, tenant, admin);
    }
}
~~~

`AccessContextException` là exception ứng dụng minh họa. Đoạn mã giả định `Jwt` trong tham số là **principal đã qua JwtDecoder**; không bao giờ dùng `JWT.decode(...)` không xác thực rồi gọi factory này. Production nên validate tenant/sub claim ở **authentication validator hoặc converter** để request có token thiếu trường bị xử lý nhất quán như invalid token (401), thay vì để exception tùy ý thành 500. Ở bài học, factory thể hiện rõ nguồn dữ liệu và ranh giới kiểm tra.

Nếu tổ chức có bảng thành viên tenant và quyền có thể bị thu hồi ngay lập tức, `tenant_id`/scope trong JWT vẫn có thể **lỗi thời cho tới khi token hết hạn**. Với thao tác nhạy cảm, bổ sung tra cứu membership/entitlement authoritative hoặc token sống ngắn và revoke mechanism phù hợp. Việc JWT ký đúng không khẳng định principal vẫn là thành viên tenant vĩnh viễn.

### 9.1. Tuyệt đối không nhận tenant từ JSON hoặc header

**Sai:**

~~~java
@PostMapping("/api/v1/orders")
OrderReceipt create(@RequestBody CreateOrderRequest request) {
    return orders.create(
        request.tenantId(), request.ownerId(),
        request.skuId(), request.quantity());
}
~~~

Nếu client điều khiển `tenantId`/`ownerId`, nó có thể tạo đơn mang danh tính khác hoặc ở tenant khác. Một check `hasAuthority("SCOPE_orders.write")` không sửa được lỗ hổng này.

**Đúng về nguyên tắc:**

~~~java
public record PlaceOrderRequest(
    @NotNull UUID skuId,
    @Min(1) int quantity) {}

@PostMapping("/api/v1/orders")
ResponseEntity<OrderReceipt> create(
        @AuthenticationPrincipal Jwt jwt,
        Authentication authentication,
        @Valid @RequestBody PlaceOrderRequest request) {
    AccessContext access = AccessContext.from(jwt, authentication);
    OrderReceipt created = orders.create(access, request);

    return ResponseEntity
        .created(URI.create(
            "/api/v1/orders/" + created.id()))
        .body(created);
}
~~~

`orders` là application service đã được inject; `OrderReceipt` được định nghĩa theo DTO public. Client chỉ gửi dữ liệu nghiệp vụ cho phép; tenant và owner được gán ở service từ `AccessContext`. Nếu dùng Jackson cho request record, các field lạ có thể bị bỏ qua tùy cấu hình deserialization, nhưng điều đó **không làm chúng trở thành thuộc tính được phép**. Có thể quyết định reject unknown properties ở endpoint nhạy cảm để phát hiện client gửi `tenantId`/`ownerId` trái contract; quan trọng nhất là không bind chúng vào entity.

## 10. Tầng dữ liệu: tenant filter phải nằm trong truy vấn

Entity minh họa:

~~~java
@Entity
@Table(name = "purchase_order")
public class OrderEntity {
    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private String tenantId;

    @Column(name = "owner_id", nullable = false, updatable = false)
    private String ownerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private UUID skuId;

    @Column(nullable = false)
    private int quantity;

    @Version
    private long version;

    // Constructors, getters và domain methods được lược bớt.
}

public enum OrderStatus {
    PENDING, CANCELLED, SHIPPED
}
~~~

Những trường cấm chỉnh sau khi tạo nên bất biến ở domain và database; `updatable=false` trong ORM giúp giảm sai sót nhưng **không thay thế database constraint và kiểm soát SQL trực tiếp**. Trong thực tế nên có index theo `(tenant_id, owner_id, created_at, id)` cho list, foreign key/tenant composite constraint thích hợp và migration được kiểm thử.

Repository bắt buộc có method scoped:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    Optional<OrderEntity> findByIdAndTenantId(
        UUID id, String tenantId);

    Page<OrderEntity> findByTenantIdAndOwnerId(
        String tenantId, String ownerId, Pageable pageable);

    Page<OrderEntity> findByTenantId(
        String tenantId, Pageable pageable);
}
~~~

**Không dùng** `findById(id)` rồi mới hy vọng mọi caller sẽ nhớ so `tenantId`. Query tenant-scoped trước giúp ngăn đọc chéo tenant ở data access và giảm nguy cơ query list/aggregate bỏ lọc. Với những truy vấn liên quan nhiều bảng, join phải sử dụng khóa tenant phù hợp, tránh nhầm ID trùng hoặc join xuyên tenant. Nếu hệ thống có một PostgreSQL schema cho nhiều tenant, có thể bổ sung **Row-Level Security (RLS)** như hàng rào phòng thủ thứ hai; phải thiết lập tenant session variable đúng transaction/connection và test connection pool reuse. RLS không thay thế authorization owner/admin trong ứng dụng.

### 10.1. SQL migration minh họa

~~~sql
CREATE TABLE purchase_order (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    owner_id VARCHAR(128) NOT NULL,
    sku_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_order_tenant_owner_created
    ON purchase_order
    (tenant_id, owner_id, created_at DESC, id DESC);

CREATE INDEX idx_order_tenant_created
    ON purchase_order
    (tenant_id, created_at DESC, id DESC);
~~~

Các index này hỗ trợ những truy vấn phổ biến của lab, nhưng cần đối chiếu query plan, cardinality và workload thực tế; không phải công thức bắt buộc cho production. Với `id` là UUID toàn cục, vẫn query theo tenant để tạo ranh giới phân quyền. Database schema có thể dùng khóa tổng hợp `(tenant_id, id)` nếu cần enforce foreign key cùng tenant; cách chọn phụ thuộc domain.

## 11. Object-level authorization trong service

Một pattern rõ ràng: **truy vấn theo tenant trước, rồi kiểm tra owner/admin ngay trước khi trả hoặc thay đổi object**.

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderReceipt get(
            AccessContext access, UUID orderId) {
        OrderEntity order = repository
            .findByIdAndTenantId(orderId, access.tenantId())
            .orElseThrow(OrderNotFoundException::new);

        requireCanAccess(access, order);
        return toReceipt(order);
    }

    @Transactional(readOnly = true)
    public Page<OrderReceipt> list(
            AccessContext access, Pageable pageable) {
        Page<OrderEntity> orders = access.tenantAdmin()
            ? repository.findByTenantId(
                access.tenantId(), pageable)
            : repository.findByTenantIdAndOwnerId(
                access.tenantId(), access.subject(), pageable);
        return orders.map(this::toReceipt);
    }

    @Transactional
    public OrderReceipt cancel(
            AccessContext access, UUID orderId) {
        OrderEntity order = repository
            .findByIdAndTenantId(orderId, access.tenantId())
            .orElseThrow(OrderNotFoundException::new);

        requireCanAccess(access, order);
        if (order.getStatus() == OrderStatus.SHIPPED) {
            throw new OrderStateConflictException();
        }
        if (order.getStatus() == OrderStatus.PENDING) {
            order.cancel();
        }
        return toReceipt(order);
    }

    private void requireCanAccess(
            AccessContext access, OrderEntity order) {
        if (!access.tenantAdmin()
                && !order.getOwnerId().equals(access.subject())) {
            throw new OrderNotFoundException();
        }
    }

    private OrderReceipt toReceipt(OrderEntity order) {
        return new OrderReceipt(
            order.getId(), order.getStatus().name(),
            order.getQuantity());
    }
}

public record OrderReceipt(
    UUID id, String status, int quantity) {}
~~~

Đây là **khung giải pháp thực hành**, dựa trên getters/domain method và exceptions cần bổ sung. `OrderService.create` ở controller mục 9.1 cũng cần được học viên hiện thực: lấy `tenantId` và `subject` từ `AccessContext`, tạo order trong transaction, validate business constraints và không cho client tự chọn owner/tenant. `@Version` bảo vệ optimistic concurrency nếu entity được update qua JPA, nhưng lỗi optimistic lock cần được ánh xạ theo contract (ví dụ `409` hoặc `412` nếu dùng `If-Match`).

Trong code trên, khi trạng thái đã `CANCELLED`, cancel lặp lại trả kết quả hiện tại; đây là policy đơn giản để tránh tác dụng phụ lặp. Với fulfillment/payment thực, hủy đơn phải điều phối tồn kho và external effects bằng transaction/outbox/workflow idempotent, không chỉ gán enum.

### 11.1. Vì sao không query toàn DB rồi filter trong Java?

**Sai:**

~~~java
List<OrderEntity> all = repository.findAll();
return all.stream()
    .filter(o -> o.getTenantId().equals(access.tenantId()))
    .filter(o -> access.tenantAdmin()
        || o.getOwnerId().equals(access.subject()))
    .toList();
~~~

Cách này tải dữ liệu ngoài tenant vào memory và dễ rò qua exception, metrics, cache, serialization hoặc một refactor quên filter. Nó cũng phá tính đúng đắn của phân trang: nếu DB phân trang **trước** khi Java lọc, kết quả có thể thiếu, cursor/count bị lệch hoặc tiết lộ tổng số record toàn hệ thống. **Đặt tenant/owner trong SQL query** ngay từ đầu.

### 11.2. Tenant admin không có nghĩa super-admin

Ở `list`, tenant admin có thể dùng `findByTenantId(tenant)`; **không bao giờ** dùng `findAll()`. Với `get`, tenant admin bỏ qua điều kiện owner nhưng vẫn có `findByIdAndTenantId`. Mỗi endpoint mới (search, export, order items, refunds) phải đi qua cùng chính sách. Việc một `GET` đã kiểm tra đúng không nói gì về `PATCH`/`DELETE` ở controller khác.

### 11.3. 403 và 404 đều cần tránh side effect

Với token thiếu scope, Spring Security chặn trước controller và trả 403. Với token có scope nhưng resource không thuộc phạm vi, service trả 404. **Cả hai trường hợp đều phải bảo đảm không có thay đổi database, inventory reservation, message/event hoặc gọi payment client**. Chỉ assert HTTP status mà không quan sát side effect là chưa đủ để chứng minh an toàn.

## 12. Triển khai controller cho list/detail/cancel

Ví dụ controller sử dụng cùng `AccessContext` đã xác minh:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    Page<OrderReceipt> list(
            @AuthenticationPrincipal Jwt jwt,
            Authentication auth,
            @PageableDefault(size = 20) Pageable pageable) {
        return orders.list(AccessContext.from(jwt, auth), pageable);
    }

    @GetMapping("/{id}")
    OrderReceipt getOne(
            @AuthenticationPrincipal Jwt jwt,
            Authentication auth,
            @PathVariable UUID id) {
        return orders.get(AccessContext.from(jwt, auth), id);
    }

    @PostMapping("/{id}/cancel")
    OrderReceipt cancel(
            @AuthenticationPrincipal Jwt jwt,
            Authentication auth,
            @PathVariable UUID id) {
        return orders.cancel(AccessContext.from(jwt, auth), id);
    }
}
~~~

Đoạn code này **bổ sung** mẫu `POST create` ở mục 9.1; không đặt hai class/controller có cùng route tạo đơn vào cùng application context. `@PageableDefault` chỉ là default, học viên còn phải **giới hạn page size tối đa**, whitelist sort field, chuẩn hóa cursor hoặc page index, và tránh sort theo cột nhạy cảm. Trả trực tiếp `Page` của Spring Data có thể tạo JSON shape phụ thuộc framework; production nên định nghĩa response page DTO rõ ràng/OpenAPI tương ứng.

Không tin `?tenantId=tenant-b`, `X-Tenant-Id` hoặc `ownerId` trong request để đổi filter. Nếu API công khai bắt buộc có `/tenants/{tenantId}/orders`, so tenant trong path với `AccessContext.tenantId` đã xác minh **và** vẫn truyền verified tenant xuống truy vấn; path chỉ là context mà client chỉ định, không phải credential.

## 13. Xử lý lỗi và bảo vệ thông tin

Một `@RestControllerAdvice` có thể ánh xạ domain exceptions:

~~~java
@RestControllerAdvice
public class OrderErrors {
    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound(
            OrderNotFoundException ignored) {
        ProblemDetail body =
            ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        body.setTitle("Order not found");
        body.setProperty("code", "ORDER_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.valueOf("application/problem+json"))
            .header(HttpHeaders.CACHE_CONTROL, "no-store")
            .body(body);
    }

    @ExceptionHandler(OrderStateConflictException.class)
    ResponseEntity<ProblemDetail> conflict(
            OrderStateConflictException ignored) {
        ProblemDetail body =
            ProblemDetail.forStatus(HttpStatus.CONFLICT);
        body.setTitle("Order state conflict");
        body.setProperty("code", "ORDER_STATE_CONFLICT");
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .contentType(MediaType.valueOf("application/problem+json"))
            .body(body);
    }
}
~~~

Security filter's 401/403 có thể xảy ra ngoài MVC `@ControllerAdvice`. Muốn chuẩn hóa JSON cho chúng, dùng `AuthenticationEntryPoint` và `AccessDeniedHandler` ở Spring Security, nhưng phải giữ đúng header `WWW-Authenticate` và semantics bearer auth. Đừng tự biến mọi 401/403 thành 404: route thiếu scope có thể khác chính sách với object được che tồn tại.

Khi lỗi DB constraint/optimistic lock, chỉ trả mã ổn định đã công bố; không đưa SQL state, query, stack trace hay tenant ID khác vào response. Nếu dùng `server.error.include-message=always` hoặc debug endpoint công khai, cần kiểm tra khả năng rò thông tin.

## 14. Test matrix: chứng minh ba hàng rào

Đặt fixtures cố định, có thể tạo dữ liệu test trên PostgreSQL:

| Người dùng | Tenant token | Authorities | Resource mẫu |
| --- | --- | --- | --- |
| Alice | `tenant-a` | `orders.read orders.write` | `order-A1` do Alice sở hữu |
| Bob | `tenant-a` | `orders.read orders.write` | `order-A2` do Bob sở hữu |
| Admin A | `tenant-a` | `orders.admin orders.write` | Được đọc/hủy theo policy trong tenant A |
| Charlie | `tenant-b` | `orders.read orders.write` | `order-B1` do Charlie sở hữu |
| Viewer | `tenant-a` | `orders.read` | Chỉ có quyền xem |

Fixture phải dùng ID thật có trong DB cho `order-A1`, `order-A2` và `order-B1`; nếu test chéo tenant chỉ dùng UUID ngẫu nhiên không tồn tại, nó có thể pass cả khi code không có tenant check.

### 14.1. Ma trận yêu cầu và response

| Request | Kỳ vọng | Bằng chứng bổ sung |
| --- | --- | --- |
| GET không có bearer | `401` | Không tới service |
| GET token chữ ký sai | `401` | Decoder từ chối |
| GET token hết hạn/`nbf` tương lai | `401` | Decoder từ chối |
| GET token đúng chữ ký nhưng `aud` sai | `401` | Audience validator từ chối |
| GET token thiếu `orders.read/admin` | `403` | Không tới handler đọc |
| Alice GET `order-A1` | `200` | JSON đúng, không lộ field nội bộ |
| Alice GET `order-A2` của Bob | `404` | Không lộ owner của Bob |
| Alice GET `order-B1` của tenant B | `404` | Không lộ tenant B |
| Admin A GET `order-A2` | `200` | Admin trong tenant A |
| Admin A GET `order-B1` | `404` | Admin A không vượt tenant |
| Alice GET list | `200` | Chỉ có order do Alice sở hữu |
| Admin A GET list | `200` | Có A1/A2, không có B1 |
| Alice POST create không có scope write | `403` | Không tăng số đơn |
| Alice POST create gửi `tenantId=tenant-b` | Không tạo đơn ở tenant B | Input được reject hoặc bỏ qua theo contract; vẫn dùng tenant A |
| Alice POST cancel `order-A2` | `404` | Trạng thái A2 không đổi |
| Admin A POST cancel `order-B1` | `404` | Trạng thái B1 không đổi |
| Alice cancel đơn `SHIPPED` của mình | `409` | Đơn không đổi |
| Alice cancel đơn `PENDING` của mình | `200` | Chuyển `CANCELLED` trong tenant A |
| Cùng Idempotency-Key/payload retry | Kết quả replay theo contract | Không tạo đơn/reservation thứ hai |

Các status trong bảng được chọn theo **policy của bài lab**. Nếu triển khai khác policy, cần viết rõ lý do và cập nhật OpenAPI/tests cùng nhau, không để controller và security config trả mã mâu thuẫn.

## 15. MockMvc test: scope và object permission

Spring Security Test có post-processor `jwt()` giúp tạo `JwtAuthenticationToken` để **kiểm thử authorization** mà không cần gọi IdP. Đây là kỹ thuật đúng cho test quyền ở tầng HTTP, nhưng **không kiểm tra chữ ký/issuer/audience của JWT thật**.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationIT {
    @Autowired MockMvc mvc;

    static RequestPostProcessor bearer(
            String subject, String tenant, String... scopes) {
        List<GrantedAuthority> authorities =
            Arrays.stream(scopes)
                .map(scope -> (GrantedAuthority)
                    new SimpleGrantedAuthority("SCOPE_" + scope))
                .toList();

        return jwt()
            .jwt(token -> token.subject(subject)
                .claim("tenant_id", tenant)
                .claim("aud", List.of("orders-api")))
            .authorities(authorities);
    }

    @Test
    void missingBearerReturns401() throws Exception {
        mvc.perform(get("/api/v1/orders/" + TestIds.ORDER_A1))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingReadScopeReturns403() throws Exception {
        mvc.perform(get("/api/v1/orders/" + TestIds.ORDER_A1)
                .with(bearer("alice", "tenant-a", "orders.write")))
            .andExpect(status().isForbidden());
    }

    @Test
    void aliceCannotReadBobsOrder() throws Exception {
        mvc.perform(get("/api/v1/orders/" + TestIds.ORDER_A2)
                .with(bearer("alice", "tenant-a", "orders.read")))
            .andExpect(status().isNotFound());
    }

    @Test
    void tenantAdminCannotReadOtherTenant() throws Exception {
        mvc.perform(get("/api/v1/orders/" + TestIds.ORDER_B1)
                .with(bearer("admin-a", "tenant-a", "orders.admin")))
            .andExpect(status().isNotFound());
    }
}
~~~

Đây là **khung integration test**: `TestIds` và database fixtures phải được tạo riêng, đúng owner/tenant; import JUnit, Spring Test, Java collections, `RequestPostProcessor`, `GrantedAuthority` và static MockMvc/Security Test được lược bớt. `@SpringBootTest` có thể cần Testcontainers/PostgreSQL hoặc datasource test cùng schema thật. Đừng dùng `@AutoConfigureMockMvc(addFilters=false)` cho bài test này vì nó sẽ làm mất phần lớn bằng chứng security filter.

### 15.1. Test list/pagination để phát hiện rò dữ liệu gián tiếp

~~~java
@Test
void aliceListContainsOnlyHerOrders() throws Exception {
    mvc.perform(get("/api/v1/orders")
            .param("page", "0")
            .param("size", "20")
            .with(bearer("alice", "tenant-a", "orders.read")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.content[0].id")
            .value(TestIds.ORDER_A1.toString()))
        .andExpect(jsonPath("$.totalElements").value(1));
}
~~~

Ví dụ giả định fixture Alice có chính xác một order và endpoint trả JSON shape `Page` của Spring Data. Trong production, response page có thể là DTO riêng, nên điều chỉnh path assertion theo contract. Không chỉ xem phần tử đầu tiên: cần xác nhận **toàn bộ item, count, nextCursor/links, sorting và các trang tiếp theo** đều nằm trong phạm vi tenant/owner. Thử `size=1000000`, sort field lạ, cursor lấy từ tenant B và đổi query parameter để chắc chắn pagination không vượt ranh giới.

### 15.2. Kiểm tra body và side effect

Ví dụ ghi dữ liệu trái phép, khi code reject unknown fields:

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <alice-access-token>
Content-Type: application/json

{
  "skuId":"11111111-1111-4111-8111-111111111111",
  "quantity":1,
  "tenantId":"tenant-b",
  "ownerId":"bob",
  "status":"SHIPPED"
}
~~~

Test phải assert **không xuất hiện order nào ở tenant B với owner Bob**. Tùy contract, request có thể bị từ chối bằng `400` vì trường lạ hoặc được nhận nhưng các field lạ không ảnh hưởng entity; quan trọng là không được dùng các field ấy để cấp quyền. Với thao tác bị 403/404, đọc lại DB để chứng minh không có thay đổi trạng thái, tồn kho, payment/outbox. Chỉ test HTTP status là chưa đủ.

## 16. Kiểm thử JWT thật: tách khỏi `jwt()` của Spring Security Test

Đây là điểm dễ nhầm: `.with(jwt())` bỏ qua quá trình parse và kiểm chữ ký của chuỗi bearer thật. Nó tạo một principal đã xác thực để kiểm tra authorization. Muốn xác minh decoder, cần test bằng **HTTP Authorization header thật** với token được ký bằng private key test và JWKS test đáng tin.

### 16.1. Hai nhóm test khác nhau

| Nhóm | Cách thực hiện | Điều chứng minh |
| --- | --- | --- |
| Authorization behavior | `jwt()` test post-processor + fixture DB | Scope, tenant, owner/admin policy và response |
| Token verification | JWT compact string ký bằng private test key + decoder thật/JWKS test | Signature, issuer, audience, expiry, nbf, alg, access-token type |

Có thể dựng JWKS HTTP server riêng trong integration test hoặc inject `NimbusJwtDecoder` với JWKSet test vào Spring context, miễn cấu hình trust và validators giống production. **Không dùng một decoder mock luôn trả Jwt** rồi báo rằng test signature đã pass.

Các kịch bản tối thiểu:

1. JWT hợp lệ, ký bằng private key khớp JWKS tin cậy, `iss/aud/exp/nbf` đúng → request đi qua authentication.
2. Đổi một ký tự trong payload nhưng giữ chữ ký cũ → `401`.
3. Token ký bằng key không thuộc JWKS đã cấu hình → `401`.
4. Token issuer đúng nhưng audience là `billing-api` → `401`.
5. Token issuer khác nhưng ký bởi key mà hệ thống vẫn có thể nhìn thấy → `401`.
6. Token `exp` đã qua hoặc `nbf` tương lai → `401` (tính đến clock skew chính sách).
7. Token ID token/refresh token hoặc sai `token_use` theo issuer → `401`.
8. Token thiếu `tenant_id` hoặc `sub` → bị từ chối nhất quán tại authentication boundary.
9. JWKS rotation: key cũ/mới trong cửa sổ cho phép, key bị rút không tiếp tục được chấp nhận ngoài chính sách cache.

Test nên kiểm tra có `WWW-Authenticate` khi bearer authentication failure theo cấu hình thực. Không dump token thật hoặc private key test vào logs/CI artifact; fixture key chỉ được dùng trong môi trường test và không tái sử dụng làm production secret.

### 16.2. Không tin client truyền claim

Nguy cơ:

~~~http
GET /api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f HTTP/1.1
Authorization: Bearer <alice-token-tenant-a>
X-Tenant-Id: tenant-b
X-User-Id: admin-a
~~~

Resource server phải lấy `tenant_id/sub` từ **JWT đã qua xác minh**, không từ hai header dễ giả này. Nếu hệ thống chạy sau API gateway và sử dụng một header danh tính nội bộ thay cho JWT, cần một **mô hình trust khác** gồm mTLS/authenticated proxy, strip/overwrite các header ngoài và không cho client gọi trực tiếp backend. Bài này chọn resource server verify bearer token tại API nên không phụ thuộc vào header danh tính do proxy tạo.

## 17. Test với PostgreSQL thật: tenant và tính nhất quán

Controller test không chứng minh query SQL thật luôn scoped. Integration test dùng PostgreSQL Testcontainers với migrations, dữ liệu rõ ràng:

~~~java
@Testcontainers
@SpringBootTest
class OrderTenantIsolationIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    @Test
    void sameUuidNeverCrossesTenantBoundary() {
        AccessContext alice =
            new AccessContext("alice", "tenant-a", false);

        assertThatThrownBy(() ->
            service.get(alice, TestIds.ORDER_B1))
            .isInstanceOf(OrderNotFoundException.class);
    }
}
~~~

`@ServiceConnection` có ở Spring Boot 3.1+ với dependency testcontainers phù hợp. Test thật cần setup fixture bằng migration/repository, cleanup dữ liệu, imports và transaction semantics phù hợp. Một test chỉ gọi service với `AccessContext` tạo trực tiếp là **test phân quyền service**, không kiểm chứng nguồn token; cần kết hợp test SecurityFilterChain ở mục 15 và JWT decoder ở mục 16.

### 17.1. Các tình huống database quan trọng

- Alice/tenant A đọc đúng `order-A1`; Alice không đọc được A2/B1.
- Admin A đọc A1/A2; không đọc B1.
- Bob không cancel A1; transaction không ghi thay đổi.
- Cả hai tenant có dữ liệu cùng `skuId` hoặc external customer number: join phải giữ tenant, không lấy nhầm row.
- Soft-delete/archived order không xuất hiện trong list; quyền không bị bỏ qua trong query “search all”.
- Paging/sort/filter không dùng count toàn cục, không lộ cursor của tenant B.
- DB optimistic locking ngăn lost update; cần xử lý `ObjectOptimisticLockingFailureException` hoặc lỗi tương đương theo contract.
- Tạo đơn ghi tenant/owner từ AccessContext và giữ tồn kho bằng query atomic đúng tenant.

Nếu sử dụng RLS làm lớp bảo vệ thứ hai, kiểm tra transaction dùng `SET LOCAL app.tenant_id` hoặc cơ chế session phù hợp để giá trị không rò sang request khác khi HikariCP tái sử dụng connection. Không chỉ test một request rồi kết luận RLS đúng; thử xen kẽ Alice tenant A → Charlie tenant B trên **cùng pool** và đường lỗi rollback.

### 17.2. Không “dùng UUID khó đoán” để thay query scoped

Một bài kiểm thử BOLA chất lượng luôn dùng **object thật của người khác** và một bearer principal hợp lệ có scope cần thiết. Nếu thử ID không tồn tại, cả implementation an toàn lẫn implementation dễ bị BOLA đều có thể trả 404. Hãy tạo fixture `order-B1` chắc chắn có trong database, rồi thử truy cập với Alice và Admin A.

## 18. Những đường rò tenant ngoài endpoint GET thông thường

Một API có thể khóa `GET /orders/{id}` nhưng vẫn rò qua route khác. Cần mở rộng review:

| Đường đi | Nguy cơ | Biện pháp |
| --- | --- | --- |
| Search/filter/sort | Query bỏ `tenant_id` hoặc lọc sau phân trang | Tenant-scoped query và limit/sort whitelist |
| Aggregation/count | Tổng số đơn, doanh thu của toàn DB | Group/count theo tenant và quyền |
| Batch API | ID của tenant khác lẫn trong danh sách | Kiểm tra từng ID trong verified tenant |
| Export/download | File lưu chung, URL có thể đoán | Metadata owner/tenant, check trước signed URL |
| Idempotency store | Key toàn cục gây replay kết quả tenant khác | Namespace tenant + caller + operation |
| Cache/ETag | Cache key chỉ theo `orderId`/URI | Key gồm tenant/principal/permission khi representation khác |
| Async job | Worker không còn JWT trong thread | Persist verified tenant/principal context + revalidate phù hợp |
| Event consumer | Event thiếu tenant, map nhầm account | Tenant trong business event có trust/validation và idempotency |
| Error messages | Trả owner/tenant thật trong 403/404 | Che sự tồn tại theo policy |
| Log/trace | Token và raw PII bị ghi ra log | Redaction, least privilege, retention |
| Admin/debug/Actuator | Endpoint không nằm trong security chain | Default deny, management port/network policy |

### 18.1. Idempotency và tenant

Khi thêm `Idempotency-Key` cho `POST /orders`, khóa dùng chung phải có namespace `(tenant, caller, operation, key)` và fingerprint payload. Ghi kết quả idempotency cùng transaction tạo đơn hoặc dùng state machine bền có recovery. Nếu request đầu đã commit nhưng response mất, retry từ replica khác đọc record và trả cùng resource; không tạo đơn mới. Một `ConcurrentHashMap`/cache cục bộ không bảo đảm chuyện đó.

### 18.2. Cache có thể phá quyền dù service đúng

Nếu `GET /api/v1/orders/{id}` trả response khác nhau theo owner, permission hoặc field-level policy, cache key chỉ là URI có thể làm người thứ hai nhận representation của người thứ nhất. Đặt `Cache-Control: no-store` cho dữ liệu nhạy cảm nếu không có kế hoạch HTTP caching riêng tư rõ; cache nội bộ phải key đúng tenant/principal/authorization context và invalidation. Cần test request cùng URI qua hai principal để phát hiện rò.

### 18.3. Worker bất đồng bộ cần identity rõ ràng

Không chuyển `SecurityContextHolder` qua background job rồi hy vọng sau restart nó vẫn có. Persist thông tin tenant/principal **đã xác minh** trong metadata job, với audit, quyền truy cập và revalidation theo policy nếu quyền có thể thay đổi. Worker thực thi theo một service identity tối thiểu, nhưng phải áp dụng đúng giới hạn tenant/owner của job. Khi queue chuyển message nhiều lần, side effect cần idempotency.

## 19. Quy trình tự kiểm tra theo các vòng

Không nên bắt đầu bằng hàng trăm test E2E. Hãy hoàn thiện theo thứ tự có thể quan sát:

### Vòng A — Contract và dữ liệu

Định nghĩa resource/URI, scopes, owner/admin policy, DB schema, fixtures và response lỗi. Dùng controller test cơ bản để xác nhận 201/200/400/409, JSON và `Location`. Chốt quyết định “đọc object ngoài quyền = 404” trước khi viết tests.

### Vòng B — JWT và endpoint scope

Cài Resource Server, JWT decoder, issuer/audience/type validation, `SecurityFilterChain`. Test 401 không token, 401 token không hợp lệ, 403 thiếu scope, 2xx khi có scope. Dùng test JWT thật cho decoder; dùng `jwt()` cho authorization behavior.

### Vòng C — Tenant và object permission

Thêm `AccessContext`, repository tenant-scoped và checks owner/admin. Tạo fixture trong tenant A/B; viết các negative tests truy cập cross-user/cross-tenant. Xác minh không có data leak hoặc side effect.

### Vòng D — Consistency và mở rộng

Thêm giới hạn phân trang, status conflict, optimistic locking, idempotency với store dùng chung, cache/job/export security và integration test với DB thật. Diễn tập response loss/retry và hai replica nếu bài triển khai có phần này.

### Vòng E — Vận hành

Bật metrics, structured logs đã lọc, JWT/JWKS/DB error dashboard, rate limit và timeout. Kiểm thử routing/gateway/TLS/cấu hình secret trên staging. Viết runbook 401 tăng sau key rotation, 403 tăng sau policy change, cross-tenant incident và recovery.

## 20. Các lỗi implementation thường gặp

1. **Chỉ xác minh JWT rồi tin mọi request:** có authentication nhưng không có scope, owner check hoặc tenant scoping.
2. **Chỉ dùng `@PreAuthorize` trên controller:** service/repository khác vẫn có thể trả dữ liệu chéo tenant.
3. **Tin `tenantId` trong header/body:** client có thể tự tạo request HTTP không qua UI.
4. **So owner rồi mới lọc tenant:** dễ rò object hoặc lọc thiếu ở list/search; tenant phải là điều kiện truy vấn ngay từ đầu.
5. **Dùng `findById` toàn DB:** check ở service phụ thuộc vào việc mọi caller đều nhớ authorization.
6. **Coi `orders.admin` là quyền toàn hệ thống:** tenant admin không được vượt tenant.
7. **Dùng UUID như access token:** ID không bí mật và có thể bị lộ.
8. **Đồng nhất token được decode với token hợp lệ:** base64 JSON không xác minh signature/issuer/audience.
9. **Tin test `with(jwt())` đã kiểm tra chữ ký:** nó chỉ mô phỏng principal đã được xác thực.
10. **Quên endpoint mới trong security matcher:** route hoặc Actuator/debug vô tình công khai.
11. **Disable toàn bộ CSRF/CORS filter:** browser với session cookie vẫn có thể bị CSRF; CORS không phải auth.
12. **Dùng 403 cho object ẩn nhưng response tiết lộ tenant/owner:** không tuân policy che sự tồn tại.
13. **Lọc tenant sau phân trang:** count, cursor và nội dung có thể rò hoặc sai.
14. **Cache response riêng tư bằng key URI:** tenant/owner thay đổi nhưng dữ liệu cũ được trả.
15. **Chạy async job không mang tenant context:** worker có quyền rộng, lấy dữ liệu sai tenant.
16. **Thực hiện side effect trước khi kiểm tra object:** response 403/404 nhưng database/payment đã đổi.
17. **Tin role trong token tồn tại mãi:** membership/revocation/expiry cần policy rõ.
18. **Dùng RLS nhưng không reset tenant context khi tái sử dụng connection:** tiềm ẩn data leak xuyên request.

## 21. Nhiệm vụ thực hành nâng cao

**Bài tập 1 — Thêm chức năng hủy đơn.** Triển khai `POST /orders/{id}/cancel`, chỉ owner hoặc tenant admin được hủy đơn `PENDING` trong tenant. Khi `SHIPPED` trả `409`; khi Bob hủy A1 hoặc Admin A hủy B1 trả `404`. Kiểm tra DB không đổi trong nhánh bị từ chối, và test optimistic locking khi hai request cùng hủy.

**Bài tập 2 — Quyền cấp tại thời điểm phát token.** Alice bị gỡ khỏi tenant A sau khi có JWT còn 10 phút hiệu lực. Đề xuất chính sách token lifetime/revocation hoặc tra cứu membership authoritative ở thao tác nhạy cảm. Viết test chứng minh hệ thống đáp ứng SLA thu hồi quyền đã chọn.

**Bài tập 3 — Một người dùng có nhiều tenant.** Alice là thành viên tenant A và B, nhưng token chỉ mang `tenant_id=tenant-a`. Thiết kế flow đổi tenant thông qua identity provider để nhận token mới, không chấp nhận `X-Tenant-Id: tenant-b` đi kèm token A. Thử token B và chứng minh quyền đối với tenant A không bị tự động mang sang B.

**Bài tập 4 — Search/export và cache.** Thêm `GET /orders?status=PENDING&limit=...` và export job. Dữ liệu, count, cursor, cache key, job metadata và signed download URL đều phải scoped theo tenant/owner. Thử chèn cursor của tenant B, download URL thuộc tenant B và kiểm tra log không lộ đường dẫn nội bộ.

**Bài tập 5 — Token confusion.** Dựng JWKS test, ký token có `iss` hợp lệ nhưng `aud=billing-api`, token thiếu `tenant_id`, token hết hạn, token `token_use=id` và token bị sửa payload. Mọi request phải bị từ chối theo chính sách authentication; phân biệt với test chỉ `jwt()`.

**Bài tập 6 — RLS như defense-in-depth.** Bật PostgreSQL Row-Level Security cho bảng orders trong một môi trường test. Thiết lập tenant context theo transaction và so sánh với service-level scoping. Test xen kẽ tenant A/B cùng pool connection, exception/rollback, background job và admin policy.

**Bài tập 7 — Audit và quan sát.** Thiết kế log có request ID, actor, tenant dạng đã kiểm soát, action, object type, decision allow/deny và error code. Không log bearer token hoặc raw PII; đánh giá metric cardinality và hạn chế thông tin trả về trong 404.

**Bài tập 8 — Kiểm thử hợp đồng public.** Qua gateway staging, gửi request bằng token hợp lệ, hết hạn, sai audience, thiếu scope; thử ID chéo tenant và kiểm tra 401/403/404 đúng, HTTPS/TLS hoạt động. Đối chiếu kết quả với MockMvc và lưu bằng chứng không có side effect.

### 21.1. Gợi ý thang đánh giá

| Tiêu chí | Trọng số gợi ý | Bằng chứng cần nộp |
| --- | ---: | --- |
| JWT verification (signature/iss/aud/time/token type) | 20% | Decoder config và test token thật |
| Function-level authorization/scope | 15% | Endpoint matrix, tests 401/403 |
| Tenant isolation ở query và object authorization | 30% | SQL/repository/service, BOLA tests cross-user/cross-tenant |
| HTTP contract, input validation và error policy | 10% | OpenAPI/MockMvc, 2xx/4xx, Problem Details |
| Transaction/concurrency/idempotency | 10% | Integration DB, negative side-effect assertions |
| Multi-layer tests, logging và vận hành | 15% | Fixture độc lập, E2E/smoke, runbook |

Thang điểm chỉ là **gợi ý tổ chức bài thực hành**, không thay thế tiêu chuẩn bảo mật của dự án. Một lỗi cho phép đọc/sửa chéo tenant là **lỗi chặn nghiệm thu**, dù tổng điểm các phần khác cao.

## 22. Checklist review bảo mật trước khi nghiệm thu

- [ ] Tất cả endpoint nghiệp vụ có authentication theo trust model xác định; không có route bị bỏ ngoài `SecurityFilterChain`.
- [ ] Resource server chỉ tin JWKS issuer được cấu hình; kiểm tra signature, algorithm, iss, aud, exp, nbf, token type.
- [ ] Token thiếu/không hợp lệ bị 401; token hợp lệ thiếu scope bị 403; không nhầm test `jwt()` với xác minh chữ ký.
- [ ] `tenant_id` và `sub` lấy từ token đã được xác minh, không từ header/body/path do client tự chọn.
- [ ] `orders.admin` chỉ áp dụng trong tenant đã xác minh, không bỏ tenant filter.
- [ ] Repository query list/detail/update có điều kiện tenant; người dùng thường còn có owner filter/check.
- [ ] Fixture và test có đơn **thật** của Bob/tenant B để phát hiện BOLA, không chỉ dùng UUID không tồn tại.
- [ ] Query paging/count/search/sort và export/download/job/cache đều cách ly tenant/owner.
- [ ] Không bind entity JPA trực tiếp từ request, tránh mass assignment; không cho client ghi owner, tenant hoặc status tùy ý.
- [ ] Mọi response 403/404 không tạo side effect sai; trạng thái DB, inventory/outbox và external action được kiểm tra.
- [ ] Quyền đối tượng được kiểm tra ngay trước thay đổi; concurrency/`@Version`/unique constraint và idempotency có test thực.
- [ ] JWT scope/tenant membership có lifetime/revocation policy rõ; key rotation và issuer outage được đánh giá.
- [ ] CSRF chỉ bị tắt tại phần API không dùng ambient cookie credential; CORS không bị coi là authentication.
- [ ] Error body, logs và metrics không lộ token, tenant khác, object owner, internal host hay PII không cần thiết.
- [ ] Có test decoder JWT thật, MockMvc authorization, PostgreSQL tenant isolation và smoke test qua gateway.
- [ ] Health/Actuator/debug/admin endpoints có policy riêng và không vô tình công khai.

**Kết luận:** bảo vệ một REST API đa tenant đòi hỏi nhiều hơn xác minh JWT. Resource server xác định **ai gửi token đáng tin**, scope xác định **được gọi chức năng nào**, còn query tenant-scoped và object authorization xác định **được tác động lên tài nguyên nào**. Khi cả ba hàng rào được kiểm thử bằng resource có thật của nhiều user/tenant, có negative side-effect assertions và có hợp đồng HTTP nhất quán, hệ thống mới có bằng chứng thực tế chống BOLA và truy cập chéo tenant.
