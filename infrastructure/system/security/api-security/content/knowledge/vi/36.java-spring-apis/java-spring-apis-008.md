# OpenAPI security scheme và contract test

OpenAPI mô tả contract HTTP của API: endpoint, method, tham số, request/response schema, lỗi và cơ chế xác thực mà client cần dùng. Phần security của OpenAPI giúp người viết API công bố credential được chấp nhận và operation nào yêu cầu credential hoặc scope nào. Tuy nhiên, tài liệu OpenAPI chỉ mô tả contract; nó không tự xác thực token, kiểm tra role hay bảo vệ endpoint trong ứng dụng Spring.

Vì vậy, cần kiểm tra hai lớp cùng nhau:

1. **Document contract:** OpenAPI khai báo đúng security scheme, vị trí credential, OAuth flow, scope và yêu cầu bảo mật cho từng operation.
2. **Runtime contract:** Spring Security và application authorization thực sự chấp nhận/từ chối request đúng như tài liệu, bao gồm các trường hợp thiếu credential, token sai, thiếu scope và truy cập object không được phép.

Nếu hai lớp lệch nhau, client có thể tạo request sai, generated SDK có thể xử lý credential không đúng, tài liệu có thể hứa endpoint public trong khi runtime trả 401, hoặc tài liệu nói cần OAuth scope nhưng service không kiểm tra scope đó. Contract test giúp phát hiện drift trước khi phát hành.

## 1. OpenAPI security model gồm những phần nào?

OpenAPI có hai thành phần chính:

- **Security Scheme Object:** mô tả loại credential và cách client gửi credential.
- **Security Requirement Object:** gắn một hoặc nhiều scheme vào toàn bộ API hoặc một operation cụ thể.

Security scheme được khai báo trong §components.securitySchemes§. Security requirement được khai báo ở cấp root §security§ hoặc ở cấp operation §security§.

Các loại scheme thường gặp:

| OpenAPI type | Mục đích | Ví dụ |
|---|---|---|
| §http§ với §scheme: bearer§ | Bearer token, thường là access token | OAuth access token hoặc JWT |
| §http§ với §scheme: basic§ | HTTP Basic authentication | Internal API hoặc legacy integration |
| §apiKey§ trong header | API key gửi qua header | §X-API-Key§ |
| §apiKey§ trong cookie | Credential nằm trong cookie | Session cookie |
| §apiKey§ trong query | Key nằm trong query parameter | Chỉ dùng khi có ràng buộc tương thích; dễ rò rỉ qua URL/log |
| §oauth2§ | OAuth 2.0 flows và scopes | Authorization Code, Client Credentials |
| §openIdConnect§ | OpenID Connect discovery | Identity provider công bố discovery URL |
| §mutualTLS§ | TLS client certificate | Service-to-service hoặc môi trường PKI |

Chọn scheme phản ánh đúng cơ chế runtime. Không khai báo bearer chỉ vì token trông giống JWT nếu service thực tế dùng cookie session. Không khai báo OAuth scope nếu runtime chỉ kiểm tra một role khác mà không ánh xạ scope tương ứng.

### 1.1. Khai báo bearer authentication

Ví dụ OpenAPI 3.1:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - bearerAuth: []
~~~

§bearerFormat: JWT§ chỉ là thông tin gợi ý cho tooling và người đọc; nó không yêu cầu runtime phải dùng JWT và cũng không thay thế kiểm tra chữ ký, issuer, audience hoặc expiry.

Với HTTP bearer, client thường gửi:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
~~~

Không đưa access token vào query string. Token là secret bearer credential; ai sở hữu token có thể sử dụng nó trong phạm vi quyền được cấp.

### 1.2. Khai báo API key trong header

~~~yaml
components:
  securitySchemes:
    partnerKey:
      type: apiKey
      in: header
      name: X-API-Key

security:
  - partnerKey: []
~~~

§name§ phải khớp chính xác với header mà server đọc. Nếu Spring filter tìm §X-Partner-Key§ trong khi OpenAPI mô tả §X-API-Key§, client sinh từ tài liệu sẽ gửi sai credential.

API key thường nhận diện application/client hoặc integration. Nó không nhất thiết nhận diện user cuối cùng và không tự mô tả quyền trên từng object. Runtime vẫn phải kiểm tra key còn hiệu lực, đúng client/audience, đúng tenant và có permission phù hợp.

### 1.3. Khai báo OAuth 2.0 và scopes

~~~yaml
components:
  securitySchemes:
    oauth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.test/oauth2/authorize
          tokenUrl: https://identity.example.test/oauth2/token
          scopes:
            orders:read: Read permitted orders
            orders:write: Create or update permitted orders
            orders:cancel: Cancel permitted orders
~~~

OAuth scopes nên mô tả quyền theo operation hoặc nhóm chức năng. Scope là một phần của authorization contract; có access token không đồng nghĩa có mọi scope.

Với client-to-service, có thể khai báo Client Credentials:

~~~yaml
components:
  securitySchemes:
    serviceOAuth:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.test/oauth2/token
          scopes:
            inventory:read: Read inventory
            inventory:reserve: Reserve inventory
~~~

Không khai báo flow mà client không được phép dùng. Authorization Code phù hợp ứng dụng có user tương tác; Client Credentials dành cho confidential client/service identity. Không dùng password grant cho thiết kế mới.

### 1.4. Khai báo OpenID Connect hoặc mutual TLS

~~~yaml
components:
  securitySchemes:
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://identity.example.test/.well-known/openid-configuration
    serviceCertificate:
      type: mutualTLS
~~~

OpenID Connect scheme tham chiếu discovery document. Mutual TLS mô tả client certificate authentication; việc kiểm tra certificate chain, trust store, subject/SAN, rotation và mapping identity vẫn thuộc cấu hình runtime/hạ tầng.

## 2. Gắn security requirement đúng cấp

Security requirement ở cấp root áp dụng mặc định cho mọi operation, trừ operation có khai báo security riêng.

~~~yaml
security:
  - bearerAuth: []

paths:
  /orders:
    get:
      summary: List orders
      responses:
        "200":
          description: Success
~~~

Operation GET kế thừa bearer requirement từ root. Điều này hữu ích khi phần lớn API yêu cầu đăng nhập.

### 2.1. Operation public ghi đè security bằng mảng rỗng

~~~yaml
paths:
  /health:
    get:
      security: []
      responses:
        "200":
          description: Service is healthy
~~~

§security: []§ có nghĩa operation không yêu cầu security scheme nào theo OpenAPI contract, kể cả khi root đã khai báo security. Dùng cho health check hoặc endpoint public thực sự. Không nhầm với §security: [{}]§; hai cấu hình này có ngữ nghĩa khác nhau.

### 2.2. Operation cho phép anonymous hoặc bearer

~~~yaml
paths:
  /catalog:
    get:
      security:
        - {}
        - bearerAuth: []
      responses:
        "200":
          description: Public catalog or personalized catalog
~~~

Một Security Requirement Object rỗng (§{}§) biểu diễn lựa chọn không cần authentication. Danh sách các requirement objects là các lựa chọn OR. Ví dụ trên cho phép request anonymous hoặc request có bearer credential.

Chỉ dùng cấu hình này khi endpoint thực sự có hành vi anonymous được thiết kế. Nếu có token, runtime có thể trả dữ liệu cá nhân hóa; nếu không có token, chỉ trả dữ liệu public. Contract test cần kiểm tra cả hai nhánh và bảo đảm token không hợp lệ không vô tình được coi như anonymous nếu policy yêu cầu reject.

### 2.3. Nhiều scheme trong cùng requirement là AND

~~~yaml
security:
  - bearerAuth: []
    partnerKey: []
~~~

Một object requirement chứa cả §bearerAuth§ và §partnerKey§ nghĩa là client phải đáp ứng cả hai scheme. Đây là AND.

Ngược lại:

~~~yaml
security:
  - bearerAuth: []
  - partnerKey: []
~~~

Hai object riêng biệt trong danh sách là OR: client có thể dùng bearer hoặc partner key. Sự khác nhau này dễ bị cấu hình nhầm và có thể tạo lỗ hổng nếu API dự định yêu cầu hai yếu tố nhưng tài liệu lại mô tả một trong hai là đủ.

### 2.4. Scope trong requirement

~~~yaml
paths:
  /orders:
    get:
      security:
        - oauth:
            - orders:read
    post:
      security:
        - oauth:
            - orders:write
~~~

Danh sách scope gắn với một scheme OAuth là các scope cần có cho operation. Runtime phải kiểm tra scope tương ứng, không chỉ kiểm tra token hợp lệ.

Nếu một operation yêu cầu nhiều scope trong cùng requirement, client cần đáp ứng tất cả scope được liệt kê. Nếu cần lựa chọn giữa các bộ scope khác nhau, mô hình hóa thành các requirement objects riêng và kiểm tra ngữ nghĩa OR/AND cẩn thận.

## 3. Security scheme không thay thế authorization theo object

OpenAPI có thể mô tả bearer scheme và scope §orders:read§, nhưng scope đó thường chỉ cho biết principal được thực hiện chức năng đọc orders nói chung. Nó không chứng minh user được đọc mọi order ID.

Ví dụ:

- User A có §orders:read§ nhưng chỉ được đọc order thuộc tenant A.
- User B có cùng scope nhưng chỉ được đọc order thuộc tenant B.
- Service account có §orders:read§ nhưng chỉ được đọc inventory của warehouse đã cấp.
- Support operator có quyền đọc một case khi có assignment và purpose hợp lệ.

Contract cần mô tả security scheme và scope ở mức operation. Object authorization vẫn phải được kiểm tra ở runtime dựa trên principal, tenant, owner, relationship và object state. Có thể ghi rõ mô tả operation để người tích hợp hiểu rằng scope không mở rộng phạm vi object.

### 3.1. Phân biệt authentication, function authorization và object authorization

| Lớp | Câu hỏi | Ví dụ kiểm tra |
|---|---|---|
| Authentication | Ai đang gọi? | Token chữ ký hợp lệ, đúng issuer/audience |
| Function authorization | Principal được gọi chức năng này không? | Có scope §orders:cancel§ |
| Object authorization | Principal được thao tác trên object này không? | Order thuộc tenant/assignment của principal |
| Business rule | Trạng thái hiện tại có cho phép hành động không? | Chỉ hủy order ở trạng thái PENDING |

OpenAPI security requirement chủ yếu mô tả credential và phần function scope có thể công bố. Không dùng nó như bằng chứng rằng mọi object hoặc business transition đã được bảo vệ.

## 4. Đồng bộ OpenAPI với Springdoc

Nếu dự án dùng springdoc-openapi, tài liệu có thể được sinh từ annotation và cấu hình Java. Cần chọn một nguồn sự thật rõ ràng: annotation, cấu hình customizer hoặc file OpenAPI được quản lý riêng. Tránh khai báo trùng ở nhiều nơi rồi để security requirement giữa chúng không nhất quán.

### 4.1. Khai báo bearer scheme ở cấp tài liệu

~~~java
@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Orders API", version = "1.0.0"),
    security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfiguration {
}
~~~

Cấu hình này khai báo bearer scheme và áp dụng requirement mặc định ở cấp OpenAPI. Các endpoint public cần override security ở operation thay vì để tài liệu mô tả chúng là protected.

### 4.2. Khai báo OAuth scheme và scope ở operation

~~~java
@SecurityScheme(
    name = "oauth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://identity.example.test/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "inventory:read",
                    description = "Read permitted inventory"
                ),
                @OAuthScope(
                    name = "inventory:reserve",
                    description = "Reserve permitted inventory"
                )
            }
        )
    )
)
@Configuration
public class OAuthOpenApiConfiguration {
}
~~~

Trên controller operation:

~~~java
@Operation(
    summary = "Read inventory",
    security = @SecurityRequirement(
        name = "oauth",
        scopes = {"inventory:read"}
    )
)
@GetMapping("/api/inventory")
public InventoryPage listInventory() {
    // Application logic
}
~~~

Tên scheme trong annotation phải trùng với tên trong Security Scheme Object. Tên scope phải khớp với scope được cấp trong access token và authority mapping của Spring Security.

### 4.3. Đánh dấu operation public

~~~java
@Operation(
    summary = "Health check",
    security = {}
)
@GetMapping("/health")
public HealthResponse health() {
    return new HealthResponse("UP");
}
~~~

Cú pháp annotation có thể khác theo phiên bản swagger-annotations/springdoc. Sau khi sinh tài liệu, luôn kiểm tra OpenAPI JSON/YAML đầu ra; không giả định annotation đã tạo đúng security array rỗng hoặc đã ghi đè global requirement.

### 4.4. Kiểm tra tài liệu được sinh ra

Tải tài liệu runtime từ endpoint được cấu hình, thường là §/v3/api-docs§, hoặc kiểm tra file OpenAPI được build cùng artifact. Xác minh:

- Scheme có đúng name, type, scheme và vị trí credential không?
- Bearer có được mô tả đúng là HTTP bearer không?
- OAuth flow có đúng authorization/token URL và scope không?
- Protected operation có security requirement không?
- Public operation có security array rỗng khi cần override không?
- Scope có được gắn đúng operation không?
- Không có endpoint nội bộ hoặc môi trường test xuất hiện ngoài dự kiến?
- Server URL không trỏ nhầm production/staging?

Tài liệu sinh tự động cũng là output cần test. Một annotation bị xóa hoặc một customizer đổi thứ tự/ghi đè có thể làm contract thay đổi dù controller vẫn hoạt động.

## 5. Ánh xạ security scheme vào Spring Security

OpenAPI mô tả cách client gửi credential; Spring Security xác minh credential và tạo Authentication. Cần kiểm tra mapping rõ ràng giữa hai lớp.

### 5.1. Bearer JWT resource server

Một cấu hình Spring Security có thể dùng OAuth2 Resource Server:

~~~java
@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/v3/api-docs/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt())
            .build();
    }
}
~~~

Cấu hình minh họa cho bearer JWT. Trong môi trường thật, cấu hình decoder/issuer, audience validation, key rotation, clock skew và claim mapping theo identity provider. Không chỉ kiểm tra JWT có parse được; phải xác minh chữ ký và các claim cần thiết.

Spring Security thường ánh xạ OAuth scope thành authority có tiền tố §SCOPE_§, ví dụ scope §orders:read§ thành §SCOPE_orders:read§. Nếu ứng dụng dùng converter tùy chỉnh, test phải kiểm tra converter đó vì mapping khác mặc định có thể làm scope trong OpenAPI không khớp authority runtime.

### 5.2. Function authorization bằng method security

~~~java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public OrderPage listOrders() {
        // Query only records visible to the current principal
    }
}
~~~

Method security giúp bảo vệ chức năng ở lớp service, kể cả khi service được gọi từ controller khác. Nhưng annotation scope không thay thế kiểm tra quyền trên từng order.

### 5.3. Object-level authorization

~~~java
@Service
public class OrderService {

    public Order getOrder(UUID orderId, CurrentPrincipal principal) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(NotFoundException::new);

        orderAuthorization.requireCanRead(principal, order);
        return order;
    }
}
~~~

Authorization service cần kiểm tra tenant, owner, membership, assignment hoặc ACL theo policy. Không dùng order ID do client gửi làm bằng chứng về quyền. Có thể giới hạn query theo tenant/principal ngay tại repository để giảm nguy cơ đọc nhầm object và tránh kiểm tra tách rời.

### 5.4. API key authentication

Nếu OpenAPI khai báo §type: apiKey§, runtime phải có filter/resolver đọc đúng header, cookie hoặc query parameter đã mô tả. Filter cần:

- Lấy key từ đúng vị trí và tên đã công bố.
- Tra cứu credential record hoặc xác minh secret theo thiết kế.
- Kiểm tra trạng thái active, expiry, revocation và client/tenant binding.
- Tạo principal/client identity đáng tin cậy.
- Ánh xạ permission rõ ràng; không mặc định key có toàn quyền.
- Không log raw key.
- Từ chối key không hợp lệ bằng response nhất quán.

Không coi API key là thay thế cho user authorization nếu API thao tác trên dữ liệu của user. Với partner integration, có thể cần mapping key tới tenant/service principal và scope riêng.

### 5.5. Cookie session và CSRF

Nếu runtime dùng session cookie, tài liệu cần mô tả đúng cookie-based authentication và các yêu cầu CSRF liên quan. Cookie được browser tự động gửi nên các operation thay đổi trạng thái cần CSRF protection phù hợp. Khai báo API key trong cookie không tự mô tả đầy đủ CSRF behavior; bổ sung mô tả bảo mật và test browser/session riêng.

Không khai báo bearer scheme trong khi runtime chỉ đọc cookie session. Điều đó khiến generated client gửi Authorization header nhưng server bỏ qua, hoặc khiến người tích hợp hiểu sai cách credential được truyền.

## 6. Contract test: kiểm tra tài liệu và runtime

Contract test cho security có thể chia thành bốn lớp:

1. **Document validation:** file OpenAPI hợp lệ, scheme tham chiếu tồn tại và security requirement có cấu trúc đúng.
2. **Policy review/test:** từng operation có security requirement, scope và ngoại lệ public đúng với policy đã duyệt.
3. **Runtime integration test:** gửi request HTTP thật tới Spring application với credential hợp lệ/không hợp lệ và kiểm tra status, headers, body.
4. **Schema conformance:** response thực tế, kể cả error response 401/403/429, khớp schema và contract được công bố.

Static validation chỉ chứng minh tài liệu hợp lệ về cú pháp/cấu trúc. Nó không chứng minh endpoint thực sự bảo vệ. Runtime test chỉ chứng minh một số request cụ thể; nó không chứng minh OpenAPI mô tả đúng cho mọi consumer. Cần kết hợp cả hai.

### 6.1. Ma trận kiểm thử tối thiểu

| Trường hợp | Credential | Scope/permission | Kết quả mong đợi |
|---|---|---|---|
| Protected operation, không token | Absent | — | 401 |
| Token sai chữ ký/issuer/audience | Invalid | — | 401 |
| Token hết hạn | Expired | — | 401 |
| Token hợp lệ, đúng scope | Valid | Required scope | Qua authentication/authorization; tiếp tục object/business check |
| Token hợp lệ, thiếu scope | Valid | Missing scope | 403 |
| Token đúng scope, object tenant khác | Valid | Scope present | 403 hoặc 404 theo anti-enumeration policy |
| Public operation, không token | Absent | — | Được truy cập theo contract |
| Public operation, token hợp lệ | Valid | Optional | Hành vi anonymous/personalized được định nghĩa rõ |
| Public operation, token sai | Invalid | — | Reject hoặc anonymous fallback theo policy đã công bố; không âm thầm bỏ qua lỗi credential nếu contract yêu cầu reject |
| API key bị revoke | Revoked | — | Từ chối |
| Scheme AND | Chỉ có một credential | Partial | Từ chối |
| Scheme OR | Một trong các credential được chấp nhận | Valid alternative | Qua authn; vẫn kiểm tra authorization |

Các status là thông lệ, nhưng cần nhất quán với API contract và anti-enumeration policy. 401 thường biểu thị chưa xác thực; 403 biểu thị principal đã xác thực nhưng không có quyền. Một số API dùng 404 để che sự tồn tại của resource.

### 6.2. Test scheme semantics

Ngoài các request trên, cần test cấu trúc OpenAPI:

- Root security được kế thừa khi operation không override.
- Operation §security: []§ thực sự public.
- Một requirement object chứa hai scheme được hiểu là AND.
- Hai requirement objects riêng biệt được hiểu là OR.
- OAuth scopes đúng tên và đúng operation.
- Operation không có scope không vô tình mất bearer requirement.
- Security scheme được tham chiếu phải tồn tại trong components.
- Không có scheme name sai chính tả hoặc scope chưa đăng ký.

Đây là các lỗi contract thường không xuất hiện trong happy-path test.

## 7. Ví dụ integration test với Spring MockMvc

Dùng test token do Spring Security Test tạo ra để kiểm tra authority mapping và endpoint policy. Ví dụ dưới đây giả định ứng dụng dùng authority prefix §SCOPE_§.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void protectedEndpointRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readScopeCanCallListEndpoint() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders:read"))))
            .andExpect(status().isOk());
    }

    @Test
    void writeOnlyScopeCannotReadOrders() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders:write"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Các test này xác minh authorization rule trong application context. JWT request postprocessor thường tạo Authentication test; nó không kiểm tra chữ ký JWT, issuer, audience hoặc cấu hình decoder như request mang token thật. Bổ sung integration test qua HTTP server với token do test identity provider/issuer phát hành để kiểm tra toàn bộ authentication chain.

### 7.1. Kiểm tra object authorization

~~~java
@Test
void readScopeCannotReadOrderFromAnotherTenant() throws Exception {
    mockMvc.perform(get("/api/orders/{id}", foreignTenantOrderId)
            .with(jwt()
                .jwt(jwt -> jwt.claim("tenant_id", "tenant-a"))
                .authorities(new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isNotFound());
}
~~~

Ví dụ giả định policy dùng 404 để che object ngoài phạm vi. Nếu API dùng 403, thay expectation tương ứng. Test cần fixture có tenant A/B rõ ràng và xác minh response không chứa dữ liệu của tenant B.

### 7.2. Kiểm tra challenge và error schema

Với bearer authentication, kiểm tra response 401 có challenge/header phù hợp theo contract, ví dụ §WWW-Authenticate: Bearer§ nếu API áp dụng RFC 6750. Kiểm tra body lỗi dùng schema ổn định như Problem Details nếu API đã công bố; không trả stack trace, token hoặc claim nhạy cảm.

Với insufficient scope, kiểm tra response 403 và error code phù hợp. Nếu server trả thêm §WWW-Authenticate§ với §error="insufficient_scope"§, bảo đảm scope được công bố chính xác và không tiết lộ thông tin ngoài policy.

## 8. Contract test cho OpenAPI document

Có thể kiểm tra file OpenAPI bằng parser trong CI, sau đó assert security requirement cho các operation quan trọng. Ví dụ dùng Swagger Parser:

~~~java
class OpenApiSecurityDocumentTest {

    @Test
    void ordersEndpointDeclaresBearerSecurity() {
        OpenAPI api = new OpenAPIV3Parser()
            .readLocation("src/main/resources/openapi.yaml", null, null)
            .getOpenAPI();

        assertNotNull(api);
        assertNotNull(api.getComponents().getSecuritySchemes());
        assertTrue(api.getComponents().getSecuritySchemes()
            .containsKey("bearerAuth"));

        Operation getOrders = api.getPaths()
            .get("/api/orders")
            .getGet();

        assertNotNull(getOrders);
        assertNotNull(getOrders.getSecurity());
        assertTrue(getOrders.getSecurity().stream()
            .anyMatch(requirement -> requirement.containsKey("bearerAuth")));
    }
}
~~~

Đây là ví dụ kiểm tra một operation cụ thể. Với dự án lớn, nên tạo policy manifest hoặc danh sách route trọng yếu để test mọi operation, bao gồm public exceptions. Nếu OpenAPI được sinh từ Springdoc, test endpoint §/v3/api-docs§ hoặc artifact đã build thay vì chỉ kiểm tra một file source không được runtime sử dụng.

### 8.1. Kiểm tra operation public

~~~java
Operation health = api.getPaths().get("/health").getGet();
assertNotNull(health);
assertNotNull(health.getSecurity());
assertTrue(health.getSecurity().isEmpty());
~~~

Cần lưu ý parser và cách sinh tài liệu có thể biểu diễn security kế thừa khác nhau. Khi root có global security, operation public phải có security array rỗng tường minh để override; giá trị null có thể có nghĩa operation kế thừa root và vẫn được bảo vệ. Nếu tài liệu không có root security, test có thể cần quy tắc khác. Hãy kiểm tra OpenAPI output đã resolve theo đúng semantics.

### 8.2. Static lint và schema validation

Có thể tích hợp các bước sau:

~~~bash
npx @stoplight/spectral-cli lint openapi.yaml
openapi-generator-cli validate -i openapi.yaml
~~~

Dùng rule set để bắt:

- Security scheme không được tham chiếu hoặc scheme name sai.
- Operation protected nhưng thiếu security requirement ngoài danh sách public exception.
- OAuth scope không được đăng ký.
- Query API key hoặc token được khai báo ngoài policy cho phép.
- Security requirement có AND/OR semantics sai so với thiết kế.
- Response 401/403 thiếu schema hoặc description.
- Server URL, OAuth URL hoặc OpenID discovery URL trỏ sai môi trường.

Lint rule cần được tùy chỉnh theo contract của dự án; không áp dụng rule “mọi operation phải có bearer” nếu có health check, webhook hoặc public API hợp lệ.

## 9. Kiểm tra response schema và error contract

Security contract không chỉ là request header. Client cần biết cách xử lý response khi credential thiếu hoặc quyền bị từ chối.

Mỗi operation protected nên mô tả các response liên quan, tùy khả năng thực tế:

~~~yaml
responses:
  "200":
    description: Success
  "401":
    description: Missing or invalid authentication
    content:
      application/problem+json:
        schema:
          $ref: "#/components/schemas/Problem"
  "403":
    description: Authenticated principal lacks permission
    content:
      application/problem+json:
        schema:
          $ref: "#/components/schemas/Problem"
~~~

Nếu endpoint có thể trả 404 để che object ngoài phạm vi, 429 do rate limit hoặc 503 khi service unavailable, document nên mô tả các response này. Không khai báo 401/403 cho có nếu runtime luôn trả một status khác; contract test sẽ phát hiện.

### 9.1. Không đưa chi tiết nhạy cảm vào error response

Error response không nên chứa token, raw claims, key ID bí mật, SQL, stack trace hoặc dữ liệu của object mà caller không có quyền xem. Có thể trả error code ổn định như §AUTHENTICATION_REQUIRED§, §INSUFFICIENT_SCOPE§ hoặc §RESOURCE_NOT_ACCESSIBLE§, kèm request ID để hỗ trợ điều tra.

## 10. Contract testing với generated clients và consumer

OpenAPI thường được dùng để sinh client SDK, mock server và tài liệu tích hợp. Thay đổi security scheme có thể làm thay đổi cách SDK yêu cầu credential.

Khi thay đổi contract, kiểm tra:

- Generated client đặt bearer token đúng Authorization header.
- API key client dùng đúng header/cookie/query location đã công bố.
- OAuth client yêu cầu đúng scope và flow.
- Public operation không bị SDK bắt buộc token ngoài ý muốn.
- Operation cần cả hai scheme được SDK cấu hình đúng.
- Error response 401/403 được parse đúng schema.
- Refresh/retry logic không gửi lại request vô hạn sau 401/403.
- Client không ghi token vào log khi debug request.

Consumer-driven contract tools như Pact có thể bổ sung kiểm tra tương tác consumer/provider, nhưng không thay thế OpenAPI document validation hoặc security integration tests. Pact contract cũng cần test negative security cases nếu đó là một phần của hành vi được cam kết.

## 11. Tổ chức test trong CI/CD

Một pipeline phù hợp có thể gồm:

~~~mermaid
flowchart TD
    A[OpenAPI source or generated document] --> B[Parse and schema validation]
    B --> C[Security lint and policy assertions]
    C --> D[Build Spring application]
    D --> E[Runtime authentication tests]
    E --> F[Scope and object authorization tests]
    F --> G[Response schema and status contract tests]
    G --> H[Generate client and compile smoke test]
    H --> I[Publish artifact only when checks pass]
~~~

Các bước nên chạy trên cùng version document mà release sẽ publish. Nếu Springdoc sinh OpenAPI từ annotation, build ứng dụng rồi lấy §/v3/api-docs§ trong test profile để kiểm tra artifact thực tế.

### 11.1. Chặn security drift

Có thể duy trì policy inventory:

| Operation | Scheme | Scope | Public? | Runtime test |
|---|---|---|---|---|
| GET §/api/orders§ | bearerAuth/oauth | orders:read | No | Valid/missing scope |
| POST §/api/orders§ | bearerAuth/oauth | orders:write | No | Valid/missing scope |
| GET §/health§ | None | — | Yes | Anonymous succeeds |
| POST §/webhooks/provider§ | Signature scheme/custom | — | Depends | Signature valid/invalid |

Mỗi operation cần có test owner và expected behavior. Khi thêm route, CI có thể yêu cầu developer phân loại public/protected và thêm test tương ứng. Đừng suy luận endpoint public chỉ vì thiếu annotation; có thể đó là một omission.

### 11.2. Kiểm tra security theo version

Khi phát hành §/v2§, không giả định security giống §/v1§. Kiểm tra:

- Security scheme và scopes có thay đổi không?
- Endpoint mới có bị quên requirement không?
- Scope cũ có còn tương thích?
- API key migration hoặc OAuth audience mới có đúng?
- Deprecated operation có vẫn yêu cầu auth như trước?
- OpenAPI version và generated SDK có được publish đồng bộ?

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách phát hiện |
|---|---|---|
| Có scheme nhưng không gắn security requirement | Tài liệu khiến operation trông như public | Scan mọi operation |
| Root security bị operation override ngoài ý muốn | Endpoint private mất requirement trong docs | Test inheritance/override |
| Nhầm §security: []§ với §security: [{}]§ | Public/protected semantics sai | Assert parsed structure và behavior |
| Đặt hai scheme trong cùng object khi muốn OR | Client buộc phải gửi cả hai | Test AND/OR |
| Tách hai scheme thành hai object khi muốn AND | Một credential có thể đủ | Test requirement alternatives |
| Scope trong docs khác authority mapping | SDK gửi token đúng nhưng runtime trả 403 | Scope contract test |
| Khai báo bearer nhưng runtime chỉ đọc cookie | Client gửi credential sai vị trí | End-to-end auth test |
| API key name/location sai | Integration không thể xác thực | Header/query contract test |
| Chỉ test token hợp lệ | Không phát hiện endpoint thiếu auth | Negative tests |
| Chỉ test scope, không test object | BOLA/tenant leakage | Cross-object/tenant tests |
| Test MockMvc dùng jwt() nhưng không test decoder | Bỏ sót issuer/audience/signature config | Real-token HTTP integration test |
| Không mô tả 401/403 | Client xử lý lỗi sai | Response schema test |

## 13. Checklist trước khi phát hành

- [ ] OpenAPI version và security scheme type phù hợp với runtime.
- [ ] Scheme name, bearer/API-key location và header name khớp chính xác.
- [ ] OAuth flow, token URL, authorization URL và scopes đúng môi trường.
- [ ] Root security được khai báo đúng và operation override có chủ đích.
- [ ] §security: []§ và anonymous alternative được phân biệt rõ.
- [ ] AND/OR semantics của nhiều scheme được kiểm tra.
- [ ] Scope trong OpenAPI khớp với authority mapping của Spring Security.
- [ ] Authentication kiểm tra chữ ký, issuer, audience, expiry và trạng thái credential theo policy.
- [ ] Function authorization được test cho từng method/operation.
- [ ] Object/tenant authorization được test với nhiều principal và resource.
- [ ] Public endpoint thực sự hoạt động anonymous; protected endpoint từ chối request thiếu credential.
- [ ] Response 401/403/404/429/503 được mô tả đúng khi có thể xảy ra.
- [ ] Error response không lộ token, claim nhạy cảm, SQL hoặc stack trace.
- [ ] OpenAPI document được parse, lint và test ở CI.
- [ ] Runtime OpenAPI output được kiểm tra nếu dùng springdoc.
- [ ] Generated client gửi credential đúng và xử lý error contract đúng.
- [ ] Có regression test khi thêm route, đổi scope, scheme hoặc API version.

OpenAPI security scheme là bản mô tả có thể máy đọc được về cách client xác thực; security requirement gắn mô tả đó vào từng operation và scope. Contract test phải xác minh cả cấu trúc tài liệu lẫn hành vi Spring Security thực tế: thiếu/sai credential, thiếu scope, public exception, AND/OR scheme và object/tenant access. Khi hai phía được kiểm tra trong CI cùng với response schema và generated client, API contract trở nên đáng tin cậy hơn cho cả người tích hợp lẫn đội vận hành.
