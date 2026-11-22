# Đánh giá khả năng hỗ trợ actor_token, resource và audience theo phiên bản

## 1. Vì sao “có Token Exchange” chưa đồng nghĩa “hỗ trợ mọi tham số”?

Trong một Authorization Server xây bằng **Spring Boot, Spring Security và Spring Authorization Server (SAS)**, dịch vụ `orders-api` có thể nhận access token đại diện người dùng Alice, rồi cần gọi `inventory-api` để lấy tồn kho. Chuyển nguyên access token dành cho `orders-api` xuống `inventory-api` là thiết kế nguy hiểm: token có thể sai `aud`, mang quyền quá rộng hoặc khiến dịch vụ đích không biết ai đang hành động thay người dùng.

OAuth 2.0 **Token Exchange** (RFC 8693) định nghĩa cách client trình bày một token đầu vào và xin token mới theo ngữ cảnh **subject**, **actor**, **target** và **scope**. Các tham số đáng chú ý là:

- `subject_token`: token về chủ thể mà yêu cầu được thực hiện thay mặt; là đầu vào **bắt buộc**.
- `actor_token`: token tùy chọn về bên thực sự hành động; hữu ích cho delegation.
- `resource`: URI của tài nguyên/dịch vụ mà token mới dự định truy cập.
- `audience`: tên logic của dịch vụ hoặc đối tượng nhận token mới.

Nhưng cần phân biệt bốn mức hỗ trợ: **(1) chuẩn định nghĩa; (2) converter đọc tham số; (3) provider xác thực và áp dụng chính sách; (4) token đầu ra mang claims đúng và Resource Server kiểm chứng chúng**. Việc một version có getter `getActorToken()` hoặc `getAudiences()` mới chứng minh khả năng **biểu diễn input**, không tự chứng minh an toàn toàn bộ luồng.

Bài thuộc chương **Token Exchange** nhằm giúp người học đánh giá từng khả năng theo phiên bản Spring đang chạy, thiết kế kiểm tra delegation và target, xây hợp đồng token, kiểm thử liên thông và vận hành an toàn thay vì chỉ nhìn tên lớp/API.

## 2. Token Exchange khác Authorization Code và Refresh Token ở đâu?

| Luồng | Căn cứ để xin token | Ý nghĩa chính |
| --- | --- | --- |
| **Authorization Code + PKCE** | Code thu được sau yêu cầu authorization của người dùng | Client nhận quyền qua tương tác đăng nhập/consent |
| **Refresh Token** | Refresh token đã cấp cho client | Xin token mới theo authorization hiện có |
| **Client Credentials** | Client authentication và grant policy | Client/service được cấp quyền của chính nó, không nhất thiết có người dùng |
| **Token Exchange** | Subject token, actor token tùy chọn, client authentication và policy | Đổi ngữ cảnh token: target, scope, actor/delegation hoặc token type |

Grant type RFC 8693:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

Một token exchange thường **không thu hồi** subject token/actor token đầu vào; đồng thời, output token không mặc nhiên bị thu hồi khi input token sau đó hết hạn hoặc bị revoke. Muốn thu hồi lan truyền, hệ thống phải thiết kế rõ quan hệ, TTL và cơ chế kiểm tra trạng thái.

### 2.1. Ví dụ nghiệp vụ

```mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant OA as orders-api
    participant AS as Authorization Server
    participant IA as inventory-api
    U->>OA: Gọi orders-api với token A (aud=orders-api)
    OA->>AS: Exchange token A, target inventory-api
    AS->>AS: Xác thực client, subject/actor và target policy
    AS-->>OA: Token B (aud=inventory-api, scope phù hợp)
    OA->>IA: Gọi API với token B
    IA->>IA: Kiểm tra iss, aud, exp, scope và quyền
    IA-->>OA: Chấp nhận hoặc từ chối
```

Đây là **luồng mong muốn**. Các bước kiểm tra actor và target phải được xác nhận có thật trong phiên bản/configuration đang chạy; không mặc nhiên do SAS xử lý mọi chính sách của tổ chức.

## 3. Tham số và điều kiện của RFC 8693

| Tham số | Yêu cầu theo RFC | Ý nghĩa | Kiểm tra quan trọng |
| --- | --- | --- | --- |
| `grant_type` | Bắt buộc | Chọn Token Exchange Grant | Client được phép dùng grant |
| `subject_token` | Bắt buộc | Token đại diện party mà thao tác được làm thay mặt | Loại token, issuer, chữ ký/trạng thái, expiry, quyền |
| `subject_token_type` | Bắt buộc | URI định danh loại subject token | Loại token thực sự được hỗ trợ |
| `actor_token` | Tùy chọn | Token nhận diện party hành động | Xác thực độc lập và kiểm tra quyền delegation |
| `actor_token_type` | **Bắt buộc khi có actor_token; không được gửi khi thiếu actor_token** | URI loại actor token | Hai tham số phải nhất quán |
| `resource` | Tùy chọn, lặp được | URI dịch vụ/tài nguyên đích | URI tuyệt đối, không fragment; target allowlist |
| `audience` | Tùy chọn, lặp được | Tên logic của target | Ánh xạ rõ ràng, không mơ hồ |
| `scope` | Tùy chọn | Scope mong muốn trên target | Phù hợp quyền của client/subject/actor/target |
| `requested_token_type` | Tùy chọn | Loại security token muốn nhận | Provider thực sự phát hành được loại đó |

**Quy tắc đặc biệt của actor:** nếu gửi `actor_token` thì **phải** gửi `actor_token_type`; nếu không có actor token thì actor token type **không được có mặt**. Một actor token hợp lệ về chữ ký **chưa** chứng minh actor được phép hành động thay subject.

### 3.1. Resource là URI, không phải scope

Ví dụ:

```text
resource=https://inventory.example.com/api
```

Theo RFC 8693, `resource` phải là **absolute URI**, có thể có query, **không được có fragment**. Server có thể chấp nhận nhiều resource, nhưng nên cân nhắc giới hạn số target theo sản phẩm. URI hợp lệ cú pháp không đủ để được cấp quyền: `https://unknown.example/collect` phải bị từ chối nếu không thuộc trust/target policy.

Không coi `resource` là URL mà server có thể tự ý fetch metadata tùy ý. Thiết kế custom dựa trên URL do caller đưa có nguy cơ SSRF; chỉ dùng registry target đã được onboarding và kiểm soát.

### 3.2. Audience là định danh logic

Ví dụ:

```text
audience=inventory-api
```

`audience` có thể là một tên logic, một định danh khác có nghĩa với AS hoặc tên của một service. Trong phạm vi một Authorization Server, mỗi audience phải có nghĩa **duy nhất và không nhập nhằng**.

Phải phân biệt:

- **Request `audience`:** điều client *đề nghị*.
- **JWT claim `aud`:** điều Authorization Server *thực tế cấp* sau khi duyệt.
- **`RegisteredClient.clientId`:** định danh OAuth client **gọi** token endpoint, không mặc định là audience của token mới.
- **`ID token aud` trong OIDC:** audience theo hợp đồng OIDC client, không được dùng thay cách kiểm tra access token tại API.

### 3.3. Quan hệ resource × audience × scope

RFC cho phép nhiều `resource`, nhiều `audience` và `scope` trong cùng request. Khi yêu cầu token dùng ở nhiều target, phạm vi được đề nghị có ý nghĩa trên **tất cả các target đã liệt kê**, không phải chỉ một target tình cờ phù hợp.

Ví dụ client được phép:

```text
inventory-api: inventory.read
reports-api: reports.read
```

Nhưng request:

```text
audience=inventory-api
audience=reports-api
scope=inventory.read reports.read
```

không thể được duyệt chỉ bằng `clientScopes.containsAll(requestedScopes)`. Nó đang đề nghị một token có thể dùng ở cả hai API với cả hai scope. Chính sách an toàn thường chọn **một target mỗi exchange**, hoặc kiểm tra chi tiết mọi cặp **target–scope**. RFC định nghĩa lỗi `invalid_target` khi yêu cầu target không hợp lệ, không được phép hoặc quá rộng.

## 4. Ví dụ request và response chuẩn

Request minh họa cho client `orders-service`, với cả subject và actor:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=SUBJECT_ACCESS_TOKEN
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&actor_token=ACTOR_ACCESS_TOKEN
&actor_token_type=urn:ietf:params:oauth:token-type:access_token
&resource=https%3A%2F%2Finventory.example.com%2Fapi
&audience=inventory-api
&scope=inventory.read
&requested_token_type=urn:ietf:params:oauth:token-type:access_token
```

Dữ liệu viết hoa là placeholder, **không phải token/secret thật**. Body được xuống dòng để dễ đọc; khi thực thi phải gửi một form body URL-encoded hợp lệ qua TLS, kèm client authentication đúng phương thức đăng ký.

Response thành công theo khả năng/profile đã hỗ trợ:

```json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
```

`issued_token_type` xác định **loại security token được phát hành**, còn `token_type` xác định cơ chế sử dụng token. Không phải server nào cũng phát hành được mọi `requested_token_type` trong RFC, và token exchange thông thường không tự tạo refresh token dài hạn.

Request **không có actor token** cũng hợp lệ về cú pháp khi không gửi `actor_token_type`. Nhưng “không có actor” không có nghĩa client được tự mạo nhận bất kỳ người dùng nào; impersonation cũng phải có policy.

## 5. Ma trận hỗ trợ theo phiên bản Spring

| Phiên bản | Thành phần Token Exchange mặc định | Actor/resource/audience | Cách diễn giải |
| --- | --- | --- | --- |
| **SAS trước 1.3** | Không giả định sẵn converter/provider của RFC 8693 | Có thể cần custom grant | Cần kiểm tra classpath và nâng phiên bản hoặc xây extension |
| **SAS 1.3.x** | Token Exchange converter/provider xuất hiện từ dòng 1.3 | API hỗ trợ mô hình tham số RFC | Cần test actual token types, issuer trust và claims |
| **SAS 1.5.x** | Tài liệu Protocol Endpoints liệt kê `OAuth2TokenExchangeAuthenticationConverter` và `OAuth2TokenExchangeAuthenticationProvider` | `OAuth2TokenExchangeAuthenticationToken` có getter actor, resources, audiences | **Đọc được dữ liệu không bảo đảm mọi delegation/target policy** |
| **Spring Security 7.x** | Hạ tầng Authorization Server tích hợp cũng liệt kê Token Exchange converter/provider | Javadoc tiếp tục có dữ liệu actor/resource/audience | Cấu hình/semantics có thể khác; test đúng 7.x |
| **Provider/vendor tùy biến** | Phụ thuộc sản phẩm | Phụ thuộc profile và chính sách | Không suy từ tên tham số hoặc RFC conformance chung |

Tài liệu Spring Authorization Server **1.5.8** xác nhận Token Exchange là một grant ở Token Endpoint; Javadoc provider ghi **Since: 1.3**. Trong Spring Security **7.1.x**, tài liệu cũng liệt kê converter/provider tương ứng.

**Không kết luận:** “có `OAuth2ParameterNames.ACTOR_TOKEN` nên mọi JWT actor đều được chấp nhận” hoặc “`getAudiences()` khác rỗng nên output JWT chắc chắn có `aud` chính xác”. Phải kiểm tra từng lớp.

### 5.1. Ghi lại phiên bản triển khai chính xác

Khi bắt đầu đánh giá, thu thập (không cần đoán từ tên Spring Boot):

```text
Spring Boot version:          <resolved>
Spring Security version:      <resolved>
SAS version (nếu dùng 1.x):   <resolved>
Authorization Server issuer:  <issuer>
Token type:                   JWT hoặc opaque
Resource Server version:      <resolved>
Client SDK:                   <resolved>
```

Các giá trị trong dấu ngoặc là ô điền. Việc một class tồn tại trong Javadoc của bản mới **không chứng minh** project đang dùng bản đó. Khi cần xác minh token type đặc biệt hoặc external issuer, đọc đúng tài liệu/changelog của version và dùng integration test.

## 6. Luồng xử lý Token Exchange trong SAS

```mermaid
flowchart TD
    A[POST /oauth2/token] --> B[OAuth2ClientAuthenticationFilter]
    B --> C{Client hợp lệ?}
    C -->|Không| X[invalid_client]
    C -->|Có| D[OAuth2TokenEndpointFilter]
    D --> E[OAuth2TokenExchangeAuthenticationConverter]
    E --> F[OAuth2TokenExchangeAuthenticationToken]
    F --> G[OAuth2TokenExchangeAuthenticationProvider]
    G --> H[Validate subject và actor token]
    H --> I[Policy client, actor, resource, audience và scope]
    I -->|Từ chối| J[OAuth2 error]
    I -->|Chấp thuận| K[OAuth2TokenGenerator và claims policy]
    K --> L[Access token + aud/act/scope phù hợp]
    L --> M[Resource Server kiểm tra aud, iss, scope]
```

Sơ đồ là **kiến trúc bảo mật yêu cầu đạt**, không phải cam kết provider mặc định đã có sẵn từng bước policy trong mọi phiên bản.

| Thành phần | Nhiệm vụ |
| --- | --- |
| `OAuth2ClientAuthenticationFilter` | Xác thực OAuth client gọi token endpoint; khác subject/actor token |
| `OAuth2TokenEndpointFilter` | Nhận grant request, gọi manager và trả token/error |
| `OAuth2TokenExchangeAuthenticationConverter` | Parse request thành đối tượng Spring `Authentication` |
| `OAuth2TokenExchangeAuthenticationToken` | Mang input subject, actor, resources, audiences, scopes |
| `OAuth2TokenExchangeAuthenticationProvider` | Xử lý grant theo khả năng mặc định của version |
| `RegisteredClientRepository` | Tra client, kiểm tra phương thức auth và grant cho phép |
| `OAuth2AuthorizationService` | Truy xuất trạng thái token/authorization thuộc miền AS |
| `OAuth2TokenGenerator` | Phát hành token mới; customizer có thể điều chỉnh claims |
| **Resource Server** | Xác minh issuer, chữ ký/trạng thái, audience, thời hạn, scope và quyền API |

### 6.1. Getter SAS 1.5.x được Javadoc xác nhận

```java
// Đoạn trích trong logic đã nhận Authentication request,
// chưa phải implementation provider có thể chạy độc lập.
if (authentication instanceof OAuth2TokenExchangeAuthenticationToken exchange) {
    String subjectToken = exchange.getSubjectToken();
    String subjectType = exchange.getSubjectTokenType();
    String actorToken = exchange.getActorToken();        // Có thể null
    String actorType = exchange.getActorTokenType();    // Có thể null
    Set<String> resources = exchange.getResources();
    Set<String> audiences = exchange.getAudiences();
    Set<String> scopes = exchange.getScopes();

    // Các biến trên là INPUT, không phải bằng chứng đã được chấp thuận.
    // Không log subjectToken hoặc actorToken.
}
```

Javadoc còn chỉ ra `actorToken`, `actorTokenType`, `resources`, `audiences` có thể trống/nullable. **Parser biểu diễn được dữ liệu không có nghĩa dữ liệu đã được xác minh và cấp quyền.**

### 6.2. Đăng ký grant vào RegisteredClient

```java
RegisteredClient ordersService = RegisteredClient.withId(stableInternalId)
        .clientId("orders-service")
        .clientSecret(passwordEncoder.encode(secretFromSecureSource))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.TOKEN_EXCHANGE)
        .scope("inventory.read")
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
        .build();
```

`AuthorizationGrantType.TOKEN_EXCHANGE` có từ Spring Security 6.3. `stableInternalId` và `secretFromSecureSource` chỉ là biến minh họa; mã chưa cấu hình repository, JWT keys, provider policies hoặc security chains.

**Grant được đăng ký không đồng nghĩa client có thể exchange bất kỳ subject token nào hoặc xin mọi target.** Cần kiểm tra permission cụ thể cho `orders-service`, subject, actor và audience.

## 7. actor_token: nhận diện người hành động không phải quyền delegation

Trong một request, có thể tồn tại ba danh tính khác nhau:

```text
subject:          Alice (subject_token)
actor:            orders-service (actor_token)
requesting client: OAuth client đang xác thực ở /oauth2/token
```

Không tự suy rằng `actor_token` thuộc requesting client hay client có quyền hành động thay Alice chỉ vì hai chuỗi tên giống nhau.

### 7.1. Những kiểm tra cần có

1. **Subject token:** issuer tin cậy, type được hỗ trợ, signature/introspection/status hợp lệ, còn hạn, audience/binding đúng profile.
2. **Actor token:** xác minh **độc lập**, không tin credential chỉ vì đi kèm subject token hợp lệ.
3. **Quan hệ subject–actor:** actor có được phép thực hiện delegation/impersonation không? Cần chính sách cụ thể; đôi khi dựa trên `may_act` của subject token và quy tắc nội bộ.
4. **Client binding:** OAuth client đang gọi exchange có phải tác nhân có quyền trình bày subject và actor đó không?
5. **Target:** delegation được phép tại audience/resource nào và scope nào?
6. **Output:** token mới mang danh tính subject và thông tin actor phù hợp; không copy claim do caller tự khai vào JWT không qua xác minh.

### 7.2. Claims act và may_act theo RFC 8693

- **`act`:** nhận diện party đang hành động trong một delegated token. Khi dùng JWT, đây là object chứa thông tin định danh actor, ví dụ `sub`, có thể kèm `iss` để tránh mơ hồ. Các giá trị như `exp`, `aud` bên trong `act` **không phải** cơ chế kiểm tra thời hạn/đối tượng nhận của token chính.
- **`may_act`:** diễn đạt một party được cho phép trở thành actor trong hoàn cảnh áp dụng; có thể là một tín hiệu policy, nhưng **không tự thay** mọi kiểm tra authorization của AS.

Token đầu ra **minh họa, giản lược**:

```json
{
  "iss": "https://auth.example.com",
  "sub": "alice-sub-17",
  "aud": ["inventory-api"],
  "scope": "inventory.read",
  "act": {"sub": "orders-service"}
}
```

Đây chưa phải JWT hoàn chỉnh: token thật cần chữ ký, expiry và các claims theo profile. Không lấy nội dung `act` từ một form field không tin cậy rồi phát hành như danh tính đã xác minh.

### 7.3. Actor/subject token của issuer bên ngoài

Token Exchange **không tự là federation/cross-domain trust**. Có báo cáo trong dự án Spring rằng provider mặc định truy vấn `OAuth2AuthorizationService` để xác minh subject/actor token, nên không tự xử lý các token do mọi issuer khác cấp. Đây là **mốc khả năng được thảo luận trong quá khứ**, phải xác minh lại theo version đang dùng.

Nếu yêu cầu trao đổi token của IdP khác, cần onboarding issuer, trust store/JWK, thuật toán cho phép, audience, expiry, key rotation, token type, subject mapping, policy delegation và revocation. Không lấy URL JWKS tùy ý trực tiếp từ claim/token do caller gửi để xác minh chính nó.

## 8. resource và audience: cần policy và claim output riêng

Một hệ thống có thể ánh xạ:

| Resource URI đã đăng ký | Logical audience | Scope cho phép theo policy |
| --- | --- | --- |
| `https://inventory.example.com/api` | `inventory-api` | `inventory.read`, `inventory.write` |
| `https://reports.example.com/api` | `reports-api` | `reports.read` |
| `https://admin.example.com/api` | `admin-api` | Quyền quản trị riêng, giới hạn client |

Đây là registry **ứng dụng tự quản**, không phải mapping mặc định của SAS.

### 8.1. Ba bằng chứng cần có

1. Converter parse được `resource`/`audience`, kể cả khi chúng lặp theo RFC.
2. Provider/policy xác minh cả client, subject, actor và target; từ chối target lạ, multi-target vượt quyền.
3. Access token thực tế có `aud` đã được **phê duyệt**, và Resource Server kiểm tra audience trước khi trả dữ liệu.

Nếu chỉ điều 1 đúng, Token Exchange **chưa đạt yêu cầu audience isolation**.

### 8.2. Resource và audience trong cùng request

Chính sách có thể:
- Cho phép cả hai **chỉ khi cùng ám chỉ một target đã đăng ký**.
- Cho phép đa target với quy tắc chi tiết cho từng target–scope.
- Chọn chính sách bảo thủ: **chỉ một target mỗi request**, từ chối tổ hợp khác bằng `invalid_target`.

Không được nói RFC 8693 cấm multi-target; đây là **giới hạn triển khai do sản phẩm lựa chọn**.

### 8.3. Scope mapping phải dựa trên quyền nguồn

Nếu token nguồn có `orders.read` và token đích cần `inventory.stock.read`, việc scope khác tên không có nghĩa exchange bắt buộc bị từ chối; doanh nghiệp có thể cho phép một **phép ánh xạ đã phê duyệt**. Nhưng không được lấy scope mong muốn từ request rồi phát hành thẳng. Rule phải xét subject, actor, target và quyền nguồn.

```text
Client: orders-service
Input:  subject token có orders.read
Target: inventory-api
Policy: cho phép đổi thành inventory.stock.read khi actor hợp lệ
Output: token chỉ có aud=inventory-api, scope=inventory.stock.read
```

**Ngăn confused deputy:** một service được gọi thay user không được biến quyền hẹp của user thành quyền admin tại dịch vụ khác.

## 9. Tùy chỉnh SAS mà không phá provider mặc định

Spring Authorization Server 1.x cung cấp `tokenEndpoint().authenticationProviders(...)` để truy cập danh sách provider. Nếu cần bổ sung rule trước khi cấp token, có thể bọc provider mặc định với chính sách target đã được review.

### 9.1. Ví dụ wrapper chỉ cho phép một target

```java
final class SingleTargetExchangeProvider implements AuthenticationProvider {
    private final AuthenticationProvider delegate;

    SingleTargetExchangeProvider(AuthenticationProvider delegate) {
        this.delegate = delegate;
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return OAuth2TokenExchangeAuthenticationToken.class
                .isAssignableFrom(authentication);
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {
        if (!(authentication instanceof OAuth2TokenExchangeAuthenticationToken request)) {
            return null;
        }

        int count = request.getResources().size()
                  + request.getAudiences().size();
        if (count != 1) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_target"));
        }

        // Vẫn gọi provider chuẩn: không bỏ kiểm tra grant và token.
        return delegate.authenticate(authentication);
    }
}
```

**Giới hạn quan trọng:** code này chỉ **giới hạn số target**, chưa kiểm tra target thuộc allowlist hoặc subject/actor được phép nhắm tới. Một `audience=admin-api` đơn lẻ vẫn có thể qua điều kiện `count==1`. Ở production phải thêm policy đáng tin **trước** khi delegate và bảo đảm output audience đúng.

### 9.2. Đăng ký wrapper đúng điểm

```java
OAuth2AuthorizationServerConfigurer as =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.securityMatcher(as.getEndpointsMatcher())
    .with(as, server -> server.tokenEndpoint(tokenEndpoint ->
        tokenEndpoint.authenticationProviders(providers -> {
            providers.replaceAll(provider ->
                provider instanceof OAuth2TokenExchangeAuthenticationProvider
                    ? new SingleTargetExchangeProvider(provider)
                    : provider);
        })))
    .authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
```

Đoạn này chỉ minh họa **điểm cấu hình trong SAS 1.x**, chưa phải `SecurityFilterChain` hoàn chỉnh. Nếu append một provider mới sau provider mặc định, provider mới có thể **không được gọi**; phải kiểm tra thứ tự và tất cả đường xử lý. Nếu dùng Spring Security 7.x, dùng API cấu hình Authorization Server của 7.x tương ứng, không trộn trực tiếp cú pháp.

### 9.3. Không kế thừa class final hoặc thay toàn bộ validation vô căn cứ

`OAuth2TokenExchangeAuthenticationProvider` là lớp có thể được đóng `final` theo Javadoc; nếu không cho kế thừa, dùng wrapper/delegate hoặc triển khai provider mới được review. Không viết provider chỉ kiểm tra `subject_token != null` rồi phát hành token, vì có thể bỏ issuer, audience, scope, client binding, token status và actor authorization.

## 10. Phát hành claim aud ở access token

Sau khi quyết định target được cấp bởi **policy đáng tin**, token generator có thể đưa target vào JWT access token. API `JwtEncodingContext` cung cấp `getAuthorizationGrant()`, `getClaims()` và `getTokenType()`.

Ví dụ minh họa:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> exchangeAudienceCustomizer(
        ExchangeTargetPolicy policy) {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }
        if (!(context.getAuthorizationGrant()
                instanceof OAuth2TokenExchangeAuthenticationToken request)) {
            return;
        }

        // approvedAudiences() phải xuất ra QUYẾT ĐỊNH ĐÃ KIỂM TRA;
        // không trả lại nguyên getAudiences() từ request chưa xác minh.
        List<String> audiences = policy.approvedAudiences(
                context.getRegisteredClient(), request);
        context.getClaims().audience(audiences);
    };
}
```

`ExchangeTargetPolicy` là abstraction **tự thiết kế**, không phải class có sẵn của SAS. Cần bảo đảm policy ở bước cấp quyền và ở token customizer dùng cùng quyết định, tránh lệch do cache/race. Nếu đã có customizer khác, phải **ghép logic** thay vì để cấu hình bean loại trừ nhau. Với opaque token, audience có thể được biểu diễn qua introspection/metadata thay vì JWT claim trực tiếp.

**Không nhầm:** đặt `aud` trên JWT là bước *phát hành claim*; nó không chứng minh request có quyền target. Phải kiểm tra target **trước khi** cấp token.

### 10.1. Resource Server bắt buộc kiểm tra audience

JWT access token cho inventory (giản lược):

```json
{
  "iss": "https://auth.example.com",
  "sub": "alice-sub-17",
  "aud": ["inventory-api"],
  "scope": "inventory.read",
  "act": {"sub": "orders-service"}
}
```

`inventory-api` kiểm tra chữ ký/issuer, `exp`/`nbf`, `aud=inventory-api`, scope và quyền tài nguyên. `reports-api` **phải từ chối** token này dù nó do cùng issuer ký. Nếu các API chỉ kiểm tra signature và issuer, một token không đúng audience vẫn có nguy cơ được dùng xuyên dịch vụ.

## 11. Bảng lỗi và trường hợp phải từ chối

| Tình huống | Lỗi/góc kiểm tra phù hợp | Lưu ý |
| --- | --- | --- |
| Thiếu `subject_token` hoặc `subject_token_type` | `invalid_request` | Converter/request validation |
| Có actor nhưng thiếu `actor_token_type` | `invalid_request` | Sai ràng buộc cặp |
| Có `actor_token_type` nhưng không có actor | `invalid_request` | Không tự bỏ qua field |
| `resource` tương đối hoặc có fragment | `invalid_request` / lỗi validator tương ứng | Kiểm tra hình thức |
| `resource` hoặc `audience` ngoài quyền | `invalid_target` | RFC 8693 định nghĩa lỗi target |
| Xin quá nhiều target | `invalid_target` | Không cấp quyền multi-audience rộng |
| Scope không được phép | `invalid_scope` | Kiểm tra theo target và policy |
| Client không được dùng Token Exchange | `unauthorized_client` | `RegisteredClient.authorizationGrantTypes` |
| Client credential sai | `invalid_client` | Client authentication |
| Input token sai chữ ký/hết hạn/không được tin | Lỗi grant/token phù hợp theo phiên bản | Không tiết lộ lý do nội bộ |
| Token type không được provider hỗ trợ | Lỗi phù hợp theo profile/implementation | Không suy RFC cho phép thì SAS phải cấp |

Mã lỗi cụ thể cho từng loại token/issuer phụ thuộc phiên bản/provider, cần kiểm thử thực tế. **Không** thay lỗi bằng HTTP 200 và token giả, cũng không trả raw JWT/cấu trúc policy nội bộ cho caller.

## 12. Ma trận kiểm thử capability theo phiên bản

| Trường hợp | Input chính | Kỳ vọng |
| --- | --- | --- |
| Exchange cơ bản | Client có grant, subject hợp lệ | Cấp token theo profile hoặc lỗi được xác định |
| Client không đăng ký grant | `authorizationGrantTypes` thiếu exchange | Từ chối |
| Thiếu subject token | Không có `subject_token` | Từ chối |
| Có actor đúng type | Actor đã xác minh và được delegate | Thành công **chỉ khi** policy hỗ trợ |
| Actor thiếu type | Có actor, không có `actor_token_type` | Từ chối |
| Actor type thừa | Không có actor, có type | Từ chối |
| Actor ký bằng khóa lạ | Actor token giả mạo | Từ chối |
| Actor từ issuer ngoài | Issuer chưa onboarding | Từ chối |
| Subject từ issuer ngoài | Token nguồn ngoài trust | Từ chối |
| Input sai audience | Subject token không được dùng trong ngữ cảnh exchange | Từ chối |
| Không truyền target | Thiếu `resource`/`audience` | Hành vi default có policy hoặc từ chối |
| Resource hợp lệ | URI target đã đăng ký | Nếu hỗ trợ: output audience đúng |
| Resource sai URI | URI tương đối/fragment | Từ chối |
| Resource lạ | URL ngoài allowlist | Từ chối |
| Audience hợp lệ | `inventory-api` | Output `aud` là target đã duyệt |
| Audience lạ | `admin-api` ngoài quyền | `invalid_target`/lỗi phù hợp |
| Resource + audience trùng target | Mapping đã đăng ký | Chỉ chấp nhận nếu policy cho phép |
| Resource + audience mâu thuẫn | Hai target không được phép kết hợp | Từ chối |
| Multi-audience | Nhiều target, scopes kết hợp | Không nâng quyền; từ chối nếu policy một target |
| Scope vượt quyền | Xin scope không được phê duyệt | Từ chối |
| Subject token type khác | ID token/SAML token chưa được hỗ trợ | Từ chối |
| Requested token type khác | Xin type không phát hành được | Từ chối |
| Token output JWT | Có audience/actor/scope đã được duyệt | Claims đúng với profile |
| Resource Server cross-audience | Token cho inventory gửi reports | Reports từ chối |
| Thu hồi input sau exchange | Input token bị revoke sau khi output được cấp | Hành vi output theo TTL/revocation đã tài liệu hóa |
| Logging | Chạy test với log/telemetry | Không rò raw subject/actor/output token |

### 12.1. Mẫu ghi nhận kết quả thay vì nhãn YES/NO duy nhất

| Năng lực | Parser | Provider/policy | Output claims | Resource Server | Kết luận |
| --- | --- | --- | --- | --- | --- |
| Actor cùng issuer | PASS/FAIL | PASS/FAIL | `act` đúng/sai | Kiểm tra actor | Supported/Partial/No |
| Actor khác issuer | PASS/FAIL | PASS/FAIL | Claims đúng/sai | Trust đúng/sai | Supported/Partial/No |
| Resource đơn | PASS/FAIL | PASS/FAIL | `aud` đúng/sai | Audience check | Supported/Partial/No |
| Audience logic | PASS/FAIL | PASS/FAIL | `aud` đúng/sai | Audience check | Supported/Partial/No |
| Multi-target | PASS/FAIL | PASS/FAIL | Scope không vượt | Audience check | Supported/Partial/No |
| Scope mapping | PASS/FAIL | PASS/FAIL | Scopes phù hợp | API policy | Supported/Partial/No |

Chỉ đánh dấu **Supported** khi các tầng liên quan cùng đạt. Nếu parser nhận `actor_token` nhưng provider không tin token issuer ngoài hoặc token output không có `act` theo hợp đồng thì ghi **Partial** hoặc **No**, không xem là tương thích hoàn chỉnh.

## 13. Những lỗi kiến trúc thường gặp

**Lỗi 1 — coi getter là bảo đảm end-to-end.** Có `getAudiences()` không có nghĩa JWT có `aud` hoặc API đã kiểm tra `aud`.

**Lỗi 2 — tin actor token vì có chữ ký hợp lệ.** Chữ ký chỉ xác minh nguồn tin cậy và tính toàn vẹn theo key; chưa chứng minh actor được user/subject ủy nhiệm.

**Lỗi 3 — tin mọi issuer bên ngoài.** Không lấy JWKS URL từ token chưa tin cậy để hợp thức hóa JWT; phải có trust onboarding.

**Lỗi 4 — sao chép request audience vào JWT.** Chỉ xuất audience sau khi policy đã duyệt.

**Lỗi 5 — chỉ kiểm tra scope trong RegisteredClient.** Exchange còn phụ thuộc source token, actor, target và scope mapping.

**Lỗi 6 — thêm provider ở cuối rồi nghĩ đã áp policy.** Provider mặc định có thể hoàn tất trước khi policy mới được gọi. Phải thay/bọc đúng provider và test bypass.

**Lỗi 7 — quên nghĩa multi-target.** Mỗi target tự hợp lệ chưa chứng minh tổ hợp scope/target hợp lệ.

**Lỗi 8 — giả định revoke input sẽ revoke output.** RFC không bảo đảm liên kết vòng đời chặt như vậy; cần thiết kế riêng.

## 14. Bài tập tình huống

AS tại `https://auth.example.com` có client `orders-service` và hai API `inventory-api`, `reports-api`. Input token đại diện Alice có `aud=orders-api` và `scope=orders.read`. Client gửi:

```text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=ALICE_TOKEN
subject_token_type=urn:ietf:params:oauth:token-type:access_token
actor_token=ORDERS_SERVICE_TOKEN
actor_token_type=urn:ietf:params:oauth:token-type:access_token
audience=inventory-api
audience=reports-api
scope=inventory.read reports.export
```

Nhóm sản phẩm muốn service đọc tồn kho thay Alice, **không** được xuất báo cáo tài chính.

Hãy giải đáp:

1. Các tham số bắt buộc/có điều kiện/tùy chọn theo RFC 8693 là gì?
2. Vì sao request trên có thể vượt quyền dù mọi tham số đều parse được?
3. AS phải kiểm tra gì giữa `client_id`, subject token, actor token và audience?
4. Đề xuất mapping `orders.read → inventory.read` với target inventory nhưng từ chối reports.
5. Nếu actor token do một IdP khác phát hành, điều kiện trust nào bắt buộc trước khi chấp nhận?
6. Điều gì xảy ra nếu token đầu ra có cả hai audience mà reports API không kiểm tra target hoặc scope?
7. Viết sáu ca test âm, gồm actor giả, audience ngoài allowlist, resource sai URI, scope vượt quyền và cross-audience replay.

**Gợi ý:** chọn một target mỗi exchange, xác minh subject/actor và delegation policy, chỉ cấp `aud=inventory-api` và `inventory.read` khi được phê duyệt; không cấp report scope. Resource Server phải kiểm tra audience và quyền nghiệp vụ. Nếu hệ thống hỗ trợ multi-target, cần policy riêng cho tất cả tổ hợp target–scope.

## 15. Checklist đưa Token Exchange vào production

1. **Version:** khóa dependency Spring Boot/Security/SAS, kiểm tra converter/provider và API configurer đang chạy.
2. **Token input:** xác minh `subject_token`, `subject_token_type`, actor/type conditional, issuer, signature/status, expiry, audience, binding.
3. **Client:** xác thực phương thức đã đăng ký, yêu cầu grant Token Exchange, xác định quyền delegation.
4. **Target:** registry `resource → audience`, chặn URI lạ/multi-target ngoài policy, tránh SSRF.
5. **Scopes:** không nâng quyền; ánh xạ đúng client–subject–actor–target–scope.
6. **Claims:** `aud`, `act`, `iss`, `exp` và token type đúng hợp đồng; không cấp refresh token dài hạn thiếu lý do.
7. **Resource Server:** issuer, chữ ký, hạn, audience và business authorization đều được thực thi.
8. **Revocation:** mô tả input/output có liên kết hay không và SLA thu hồi.
9. **Tests:** contract tests theo parser/provider/output/API, cả trường hợp âm và issuer khác.
10. **Operations:** audit client/target và correlation ID có kiểm soát; không log raw subject/actor/issued token.

## 16. Tài liệu chính thức cần đối chiếu

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): semantics của actor, resource, audience, scope, `act`, `may_act` và `invalid_target`.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint và các converter/provider mặc định.
- [SAS 1.5.x — OAuth2TokenExchangeAuthenticationToken Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationToken.html): getter cho actor token, resource, audience, scopes.
- [SAS 1.5.x — OAuth2TokenExchangeAuthenticationProvider Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationProvider.html): provider và mốc `Since 1.3`.
- [Spring Security 7.x — Authorization Server Protocol Endpoints](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/protocol-endpoints.html): API token endpoint của thế hệ tích hợp.
- [Spring Security — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): Token Exchange phía client, resolver subject/actor.
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation và cấu hình audience.
- [Spring Authorization Server issue #1867](https://github.com/spring-projects/spring-authorization-server/issues/1867): thảo luận lịch sử về issuer ngoài, **không đại diện cho mọi version tương lai**.
- [Spring Authorization Server issue #1880](https://github.com/spring-projects/spring-authorization-server/issues/1880): thảo luận lịch sử về loại `id_token` trong token exchange; phải xác minh lại theo phiên bản triển khai.

**Ghi nhớ:** RFC 8693 cho phép `actor_token`, `resource` và `audience`, còn Spring Authorization Server từ dòng 1.3 có hạ tầng Token Exchange. Tuy nhiên, **nhận tham số không đồng nghĩa đã xác minh delegation hay bảo đảm token audience-bound**. Chỉ kết luận “hỗ trợ” sau khi kiểm tra **đúng phiên bản, đúng policy, đúng claims đầu ra và đúng thực thi Resource Server**.
