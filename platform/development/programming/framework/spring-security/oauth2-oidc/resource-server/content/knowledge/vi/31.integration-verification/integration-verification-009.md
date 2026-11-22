# Nhiều tenant với token hợp lệ nhưng không thuộc tài nguyên được gọi

## 1. Token hợp lệ không đồng nghĩa được truy cập mọi tenant

Trong một ứng dụng Spring Security OAuth 2.0 Resource Server phục vụ nhiều tenant, access token có thể hoàn toàn hợp lệ nhưng request vẫn không được phép truy cập tài nguyên đang yêu cầu.

Ví dụ:

- Alice đăng nhập trong tenant `tenant-a` và nhận access token có `iss`, `aud`, chữ ký, thời hạn hợp lệ cùng claim `tenant_id=tenant-a`.
- Alice gọi `GET /api/tenants/tenant-a/orders/100` và đơn hàng 100 thuộc tenant A.
- Cùng token đó, Alice gọi `GET /api/tenants/tenant-b/orders/900`. Token vẫn hợp lệ về mặt mật mã, nhưng nó không cấp quyền cho Alice đọc tài nguyên thuộc tenant B.

Đây là sự khác biệt giữa **authentication** và **authorization**:

- Authentication xác định credential có đáng tin và principal là ai.
- Authorization xác định principal có quyền thực hiện hành động trên tenant và tài nguyên cụ thể hay không.

Việc kiểm tra chữ ký JWT, issuer và audience chỉ chứng minh token được phát hành bởi issuer tin cậy và dành cho API phù hợp. Audience `orders-api` không có nghĩa caller được đọc mọi order trong mọi tenant.

Một integration test tốt phải chứng minh cả hai điều:

1. Token hợp lệ được Resource Server xác thực thành công.
2. Request tới tenant/resource không được cấp quyền bị từ chối trước khi dữ liệu hoặc side effect bị lộ.

## 2. Các lớp định danh trong hệ thống multi-tenant

Trước khi viết test, cần xác định ứng dụng đang ràng buộc quyền theo những định danh nào.

| Định danh | Ví dụ | Dùng để làm gì? |
|---|---|---|
| Issuer | `https://id.example.test/realms/shop` | Xác định security domain đã phát hành token |
| Subject | `user-123` | Định danh principal trong issuer |
| Client ID | `orders-web` | Xác định OAuth client gọi API |
| Audience | `orders-api` | Xác định resource server dự kiến nhận token |
| Active tenant | `tenant-a` | Tenant context mà token/phiên hiện tại đại diện |
| Resource tenant | `tenant-a` | Tenant sở hữu order/customer/document |
| Resource ID | `order-100` | Định danh bản ghi cụ thể |
| Scope | `orders.read` | Quyền API tổng quát |
| Role/permission | `ORDER_APPROVER` | Quyền nghiệp vụ hoặc vai trò trong tenant |

Một token có thể có:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "orders-web",
  "scope": "orders.read",
  "tenant_id": "tenant-a",
  "exp": 2000000300
}
~~~

Token này có thể vượt qua issuer, audience, signature và time validation. Tuy nhiên, nó chỉ là đầu vào cho authorization policy. Resource Server vẫn cần kiểm tra:

- Tenant được request nhắm tới có trùng với active tenant trong token không?
- Principal có còn là member của tenant đó không?
- Resource ID có thật sự thuộc tenant đó không?
- Principal có quyền trên loại tài nguyên và hành động cụ thể không?
- Token có scope phù hợp không?

Không coi claim `tenant_id` là thay thế cho mọi kiểm tra quyền. Nếu hệ thống cho phép một user thuộc nhiều tenant, claim có thể đại diện tenant context hiện tại; membership và resource permissions vẫn có thể phải tra từ database.

## 3. Những kiểu truy cập cần phân biệt

### 3.1. Sai tenant trên URL

Token đại diện tenant A:

~~~http
GET /api/tenants/tenant-a/orders/100 HTTP/1.1
Authorization: Bearer <TOKEN-A>
~~~

Request tới tenant B:

~~~http
GET /api/tenants/tenant-b/orders/900 HTTP/1.1
Authorization: Bearer <TOKEN-A>
~~~

Token A hợp lệ nhưng path yêu cầu tenant B. Nếu API ràng buộc tenant theo path, request thứ hai phải bị từ chối.

### 3.2. Tenant path đúng nhưng resource thuộc tenant khác

Đây là một lỗi khác và rất dễ bị bỏ sót:

~~~http
GET /api/tenants/tenant-a/orders/900 HTTP/1.1
Authorization: Bearer <TOKEN-A>
~~~

Giả sử order 900 thực tế thuộc tenant B. Path tenant có thể đúng với token, nhưng ID tài nguyên bị đoán hoặc bị lấy từ một response khác.

Nếu code truy vấn chỉ dùng:

~~~java
repository.findById(orderId);
~~~

thì application có thể trả về dữ liệu tenant B. Query cần ràng buộc tenant:

~~~java
repository.findByIdAndTenantId(orderId, tenantId);
~~~

Đây là một dạng **Insecure Direct Object Reference (IDOR)** hoặc broken object-level authorization: người dùng có token hợp lệ nhưng có thể đọc object không thuộc phạm vi được phép.

### 3.3. Tenant đúng nhưng user không có membership

Có thể token chứa `tenant_id=tenant-a` nhưng membership của user đã bị thu hồi hoặc thay đổi sau khi token được phát hành.

Nếu chính sách yêu cầu membership phải còn hiệu lực, Resource Server/application cần kiểm tra trạng thái membership hiện tại. Chỉ dựa vào claim cũ có thể duy trì quyền sau khi user bị remove khỏi tenant.

### 3.4. Tenant đúng nhưng thiếu quyền trên resource

Một user có thể là member tenant A nhưng chỉ được xem order của team mình hoặc chỉ được đọc một số loại dữ liệu.

Tenant authorization và resource authorization là hai tầng:

~~~text
Principal
  -> Is member of tenant A?
  -> Has orders.read scope?
  -> Can read this specific order?
  -> Is order in tenant A?
~~~

Test chỉ so sánh tenant ID chưa chứng minh ownership, team boundary hoặc permission rules đã hoạt động.

## 4. Chọn nguồn tenant context một cách rõ ràng

Một API có thể xác định tenant từ path, subdomain, header hoặc access token. Cần quy định rõ nguồn nào là selector và nguồn nào là bằng chứng authorization.

### 4.1. Tenant ID trong path

Ví dụ:

~~~text
GET /api/tenants/{tenantId}/orders/{orderId}
~~~

Path parameter là tenant mà caller đang yêu cầu. Server so sánh nó với active tenant hoặc kiểm tra membership tương ứng.

Không được coi path parameter là bằng chứng caller có quyền. Client có thể thay `tenantId` bằng tenant khác.

### 4.2. Tenant ID trong header

Ví dụ:

~~~http
X-Tenant-ID: tenant-a
~~~

Header có thể là cách client chọn tenant context, nhưng nó do caller gửi nên không thể tự tạo quyền. Nếu token chỉ được phép ở tenant A, thay header thành tenant B phải bị từ chối.

Không cho phép một filter đọc `X-Tenant-ID` rồi đặt tenant context mà không đối chiếu với token/membership policy.

### 4.3. Tenant ID trong subdomain

Ví dụ:

~~~text
https://tenant-a.api.example.test/orders/100
~~~

Gateway hoặc application có thể lấy tenant từ host. Host cũng là dữ liệu request; cần đối chiếu với trusted routing và principal permissions. Không suy ra quyền chỉ vì hostname có tenant ID.

### 4.4. Tenant ID trong request body

Với thao tác tạo tài nguyên:

~~~json
{
  "tenantId": "tenant-b",
  "description": "New order"
}
~~~

Nếu token chỉ được dùng ở tenant A, client không được tự đổi body thành tenant B để tạo dữ liệu ở đó.

Thiết kế an toàn thường lấy tenant từ authenticated context/đã được authorize. Nếu API buộc phải nhận tenant ID trong body, hãy xác minh nó khớp tenant đã được cấp quyền trước khi ghi.

### 4.5. Ma trận nguồn tenant

| Nguồn | Có thể dùng để chọn tenant? | Có tự chứng minh quyền? |
|---|---|---|
| Claim đã xác minh trong access token | Có | Chỉ trong phạm vi semantics của claim và policy |
| Path parameter | Có | Không |
| Header do client gửi | Có | Không |
| Subdomain/Host | Có | Không |
| Request body | Có thể | Không |
| Membership/ACL trong database | Dùng để xác minh | Có, theo policy hiện hành |
| Trusted gateway metadata | Có thể | Chỉ khi nguồn gửi được xác thực và policy quy định |

Nếu ứng dụng hỗ trợ nhiều tenant trên một token, đừng ép một claim `tenant_id` đơn lẻ thành quy tắc toàn cục. Có thể dùng membership lookup hoặc tenant-specific authorization manager, nhưng phải có policy nhất quán và được test.

## 5. Mô hình authorization nhiều tenant

Một policy cơ bản có thể yêu cầu đồng thời:

1. JWT đã được xác thực.
2. Có scope `orders.read`.
3. Tenant được yêu cầu nằm trong danh sách tenant mà principal được phép dùng.
4. Order thuộc tenant được yêu cầu.
5. Principal có quyền đọc order đó.

### 5.1. Policy kiểm tra active tenant

Ví dụ ứng dụng chỉ cho phép một active tenant trong token:

~~~java
@Component("tenantAccess")
public class TenantAccessPolicy {

    public boolean canAccess(
            Authentication authentication,
            String requestedTenantId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        String tokenTenant =
            jwtAuth.getToken().getClaimAsString("tenant_id");

        return tokenTenant != null
            && tokenTenant.equals(requestedTenantId);
    }
}
~~~

Dùng trong method security:

~~~java
@Service
public class OrderService {

    @PreAuthorize(
        "@tenantAccess.canAccess(authentication, #tenantId)"
    )
    public Order getOrder(String tenantId, UUID orderId) {
        return repository.findByIdAndTenantId(orderId, tenantId)
            .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Ví dụ giả định principal là JWT và tenant claim có semantics active tenant. Nếu ứng dụng dùng opaque token, custom principal hoặc multi-tenant membership, policy phải đọc đúng principal contract tương ứng.

Method security phải được bật, ví dụ bằng `@EnableMethodSecurity`. Đảm bảo parameter name được giữ hoặc dùng cú pháp tham chiếu tham số phù hợp với cấu hình build. Không đặt toàn bộ tenant policy trong controller rồi để service/repository có thể được gọi từ một đường khác mà không có kiểm tra.

### 5.2. Kiểm tra membership hiện tại

Nếu user có thể tham gia nhiều tenant, policy có thể kết hợp claim và membership:

~~~java
@Component("tenantAccess")
public class TenantAccessPolicy {

    private final TenantMembershipRepository memberships;

    public TenantAccessPolicy(
            TenantMembershipRepository memberships) {
        this.memberships = memberships;
    }

    public boolean canAccess(
            Authentication authentication,
            String requestedTenantId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();
        String subject = jwt.getSubject();
        String issuer = jwt.getIssuer() == null
            ? null
            : jwt.getIssuer().toString();

        if (subject == null || issuer == null) {
            return false;
        }

        return memberships.existsActiveMembership(
            issuer,
            subject,
            requestedTenantId
        );
    }
}
~~~

Ở mô hình này, membership repository là nguồn quyết định hiện tại. Nếu access token có claim tenant allowlist, có thể kiểm tra cả claim lẫn database membership theo contract.

Định danh user nên được hiểu trong issuer context. `sub` chỉ có tính duy nhất trong phạm vi issuer; với nhiều issuers, key identity thường cần là cặp `(iss, sub)` hoặc một internal identity mapping đã chuẩn hóa.

### 5.3. Repository phải giới hạn tenant

Ngay cả khi đã có `@PreAuthorize`, query vẫn nên giới hạn tenant:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    Optional<Order> findByIdAndTenantId(
        UUID id,
        String tenantId
    );
}
~~~

Điều này bảo vệ khi ID được đoán/lộ từ tenant khác, service được gọi từ entry point khác, có lỗi trong controller path binding hoặc một authorization check bị thiếu.

Không dùng `findById(id)` rồi chỉ lọc tenant sau khi serialize response. Dữ liệu của tenant khác không nên đi vào application response path nếu query đã có thể loại trừ nó.

### 5.4. Ownership hoặc team policy

Nếu một order còn gắn với owner/team, query hoặc policy có thể cần thêm điều kiện:

~~~java
Optional<Order> findByIdAndTenantIdAndOwnerId(
    UUID id,
    String tenantId,
    String ownerId
);
~~~

Hoặc service kiểm tra quyền cụ thể sau khi load một resource đã được scope theo tenant. Chọn cách phù hợp với domain, nhưng test phải chứng minh cả tenant isolation và resource-level authorization.

## 6. Thiết kế dữ liệu test có chủ đích

Một integration suite cần seed tối thiểu hai tenant và nhiều resource để có thể phân biệt các tình huống.

Ví dụ:

| Tenant | User | Order ID | Owner | Mục đích |
|---|---|---|---|---|
| tenant-a | user-a | order-a1 | user-a | Resource hợp lệ cho token A |
| tenant-a | user-b | order-a2 | user-b | Cùng tenant nhưng khác owner |
| tenant-b | user-c | order-b1 | user-c | Resource của tenant B |
| tenant-b | user-a | order-b2 | user-a | Kiểm tra membership đa tenant nếu policy cho phép |

Hai tenant cần có ID khác nhau và dữ liệu có thể phân biệt được. Đừng seed cùng một order ID ở cả hai tenant nếu mục tiêu test là chứng minh query theo tenant; ID collision có thể làm kết quả khó diễn giải. Nếu database dùng composite key `(tenant_id, id)`, hãy test đúng semantics đó.

### 6.1. Token fixtures

| Fixture | Claims | Expected |
|---|---|---|
| token-a-read | issuer đúng, audience orders-api, tenant A, scope read | Authentication accepted |
| token-b-read | issuer đúng, audience orders-api, tenant B, scope read | Authentication accepted |
| token-a-no-scope | tenant A, thiếu orders.read | Authentication accepted; request bị 403 |
| token-a-no-tenant | Không có tenant claim | Reject hoặc deny theo contract |
| token-wrong-aud | audience billing-api | 401 |
| token-expired | exp trong quá khứ | 401 |
| token-a-sub-unknown | tenant A, subject không có membership | Deny |
| token-a-revoked-member | tenant A nhưng membership inactive | Deny nếu policy kiểm tra membership hiện tại |

Token A và token B đều có thể là JWT hợp lệ. Điểm khác nhau nằm ở tenant authorization, không phải chữ ký.

### 6.2. Tạo dữ liệu qua repository

Trong integration test, có thể seed dữ liệu trực tiếp qua repository hoặc test fixture builder:

~~~java
@BeforeEach
void seedOrders() {
    orderRepository.save(order("order-a1", "tenant-a", "user-a"));
    orderRepository.save(order("order-a2", "tenant-a", "user-b"));
    orderRepository.save(order("order-b1", "tenant-b", "user-c"));
}
~~~

Dùng test transaction/cleanup strategy nhất quán. Nếu application xử lý request trong transaction riêng, đừng giả định transaction của test luôn bao bọc transaction server. Kiểm tra dữ liệu sau request bằng repository mới hoặc transaction boundary phù hợp.

## 7. Integration test phải đi qua decoder và security filter chain

Đối với bài kiểm chứng tích hợp, cần gửi **compact JWT đã ký** trong Authorization header. Mock `Jwt` trực tiếp hoặc dùng `@WithMockUser` không kiểm tra token authentication path.

Mô hình:

~~~text
Test private key
    |
    v
JWT fixture factory ----> signed compact token
                              |
                              v
WebTestClient / MockMvc -> Security filter chain
                              |
                              v
                       real JwtDecoder
                              |
                              v
                    JwtAuthenticationToken
                              |
                              v
                    tenant authorization
                              |
                              v
                  tenant-scoped repository
~~~

Trong test context, decoder có thể dùng public key test và issuer/audience validators. Private key chỉ được dùng để tạo fixture. Không lấy access token hoặc signing key production.

### 7.1. Decoder dùng test public key

Ví dụ cấu hình:

~~~java
@Bean
JwtDecoder jwtDecoder(
        RSAPublicKey testPublicKey) {

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withPublicKey(testPublicKey).build();

    OAuth2TokenValidator<Jwt> issuer =
        new JwtIssuerValidator(
            "https://id.example.test/realms/shop"
        );

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Token audience is not accepted",
                null
            )
        );
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuer,
            new JwtTimestampValidator(),
            audience
        )
    );

    return decoder;
}
~~~

Đây là ví dụ Servlet decoder với RSA public key. Test context phải cung cấp public key tương ứng với private key dùng trong fixture factory. Trong production, key thường được lấy từ trusted JWKS URI; test này cố ý không cần gọi issuer thật.

Nếu application dùng custom validators hoặc converter, hãy giữ chúng trong test context để kiểm tra đúng wiring. Chỉ thay key source bằng test key.

### 7.2. Tạo signed JWT test

Có thể dùng `NimbusJwtEncoder` với RSA test key. Pseudocode:

~~~java
String issueToken(
        String subject,
        String tenantId,
        String scope,
        Instant now) {

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(TRUSTED_ISSUER)
        .subject(subject)
        .audience(List.of("orders-api"))
        .issuedAt(now)
        .expiresAt(now.plusSeconds(300))
        .claim("tenant_id", tenantId)
        .claim("scope", scope)
        .claim("client_id", "orders-test-client")
        .build();

    JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
        .keyId("orders-test-key")
        .build();

    return jwtEncoder.encode(
        JwtEncoderParameters.from(header, claims)
    ).getTokenValue();
}
~~~

Đây là token factory minh họa. `jwtEncoder` phải được cấu hình bằng test-only private key. Nếu muốn kiểm tra audience/issuer failure, tạo token vẫn được ký bởi trusted test key nhưng claim audience/issuer sai; nếu muốn kiểm tra signature failure, ký bằng một key pair khác.

### 7.3. Gửi token qua WebTestClient hoặc MockMvc

WebFlux:

~~~java
webTestClient.get()
    .uri("/api/tenants/tenant-a/orders/order-a1")
    .headers(headers ->
        headers.setBearerAuth(token)
    )
    .exchange()
    .expectStatus().isOk();
~~~

Servlet:

~~~java
mvc.perform(get("/api/tenants/tenant-a/orders/order-a1")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
    .andExpect(status().isOk());
~~~

Chọn client đúng stack. Điều quan trọng là gửi compact token qua HTTP header để Bearer authentication filter thực thi.

## 8. Ma trận integration test cho tenant isolation

Giả sử token A có issuer/audience/signature/time hợp lệ, scope `orders.read`, active tenant A.

| Request | Resource thực tế | Kết quả mong đợi |
|---|---|---|
| Token A → path tenant A → order A1 | Order thuộc A | 200 |
| Token A → path tenant B → order B1 | Order thuộc B | 403 hoặc 404 theo policy |
| Token A → path tenant A → order B1 | Order thuộc B | 404 hoặc 403; tuyệt đối không trả dữ liệu |
| Token A → path tenant A → order A2 của user khác | Cùng tenant, khác owner | 403/404 nếu owner policy yêu cầu |
| Token B → path tenant B → order B1 | Order thuộc B | 200 |
| Token B → path tenant A → order A1 | Order thuộc A | 403/404 |
| Token A thiếu scope → order A1 | Order thuộc A | 403 |
| Token sai audience → order A1 | Order thuộc A | 401 |
| Token hết hạn → order A1 | Order thuộc A | 401 |
| Không token → order A1 | Order thuộc A | 401 |

Tách các trường hợp để biết lỗi ở tầng nào:

- 401: token không được xác thực hoặc credential không hợp lệ.
- 403: principal đã xác thực nhưng policy từ chối.
- 404: ứng dụng chủ động che giấu sự tồn tại của resource ngoài phạm vi caller.

Chính sách dùng 403 hay 404 phụ thuộc threat model và API contract. Dù chọn cách nào, test phải xác nhận không có response body/header chứa dữ liệu resource khác tenant.

## 9. Ví dụ kiểm thử cross-tenant bằng MockMvc

Giả sử ứng dụng dùng Servlet Resource Server, có endpoint:

~~~java
@GetMapping("/api/tenants/{tenantId}/orders/{orderId}")
OrderDto getOrder(
        @PathVariable String tenantId,
        @PathVariable UUID orderId) {
    return orderService.getOrder(tenantId, orderId);
}
~~~

Integration test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class MultiTenantOrderIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    TestAccessTokenFactory tokens;

    @Autowired
    OrderRepository orders;

    @BeforeEach
    void seed() {
        orders.save(order("order-a1", "tenant-a", "user-a"));
        orders.save(order("order-b1", "tenant-b", "user-b"));
    }

    @Test
    void tenantATokenCanReadTenantAOrder() throws Exception {
        String token = tokens.issue(
            "user-a", "tenant-a", "orders.read"
        );

        mvc.perform(get(
                "/api/tenants/tenant-a/orders/order-a1")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
                ))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("tenant-a"));
    }

    @Test
    void validTenantATokenCannotReadTenantBOrder() throws Exception {
        String token = tokens.issue(
            "user-a", "tenant-a", "orders.read"
        );

        mvc.perform(get(
                "/api/tenants/tenant-b/orders/order-b1")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void tenantAPathCannotExposeOrderOwnedByTenantB() throws Exception {
        String token = tokens.issue(
            "user-a", "tenant-a", "orders.read"
        );

        mvc.perform(get(
                "/api/tenants/tenant-a/orders/order-b1")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
                ))
            .andExpect(status().isNotFound());
    }
}
~~~

Đây là skeleton minh họa. `TestAccessTokenFactory` phải phát compact JWT được ký bằng test private key; test context dùng decoder/public key tương ứng. Các fixture `order(...)` và ID parser cần khớp kiểu dữ liệu entity thực tế.

Hai test negative khác nhau:

- Test thứ hai kiểm tra tenant path không khớp active tenant trong token.
- Test thứ ba kiểm tra IDOR: path tenant có vẻ hợp lệ nhưng record được truy vấn thuộc tenant khác.

Không gộp chúng thành một test duy nhất, vì nếu test thứ hai fail sớm ở path policy thì test thứ ba có thể chưa bao giờ chứng minh repository query có tenant predicate.

## 10. Kiểm tra membership và resource ownership

### 10.1. User thuộc nhiều tenant

Một user có thể có membership ở tenant A và B. Hệ thống có thể cho phép user chọn active tenant theo request.

Nếu token chỉ mang subject và scope, application cần kiểm tra membership:

~~~text
token issuer + subject
       |
       v
membership lookup
       |
       +-- member of tenant A -> continue
       |
       +-- not member of tenant B -> deny
~~~

Nếu token mang `tenant_id`, policy vẫn cần xác định claim đó có nghĩa là active tenant cố định hay chỉ là một trong nhiều tenant. Đừng dùng một claim có semantics mơ hồ.

### 10.2. Membership bị thu hồi

Test nên tạo membership active, gọi request thành công, sau đó disable membership và gọi lại với cùng token:

~~~java
@Test
void revokedTenantMembershipStopsAccessEvenIfTokenIsUnexpired() {
    TenantMembership membership =
        membershipRepository.save(activeMembership("user-a", "tenant-a"));

    String token = tokens.issue(
        "user-a", "tenant-a", "orders.read"
    );

    assertThat(callOrderApi(token, "tenant-a", "order-a1"))
        .isEqualTo(200);

    membership.revoke();

    assertThat(callOrderApi(token, "tenant-a", "order-a1"))
        .isEqualTo(403);
}
~~~

Pseudocode này minh họa membership check theo trạng thái hiện tại. Nếu hệ thống cố ý chấp nhận membership snapshot trong token cho đến khi token hết hạn, expected behavior sẽ khác; phải ghi rõ revocation model và test đúng contract.

### 10.3. Ownership trong cùng tenant

Nếu order có owner, một user khác trong cùng tenant có thể không được xem nó:

~~~text
tenant_id = tenant-a
token subject = user-a
order owner = user-b
~~~

Tenant match nhưng ownership mismatch. Test phải chứng minh domain authorization từ chối truy cập. Scope `orders.read` thường là quyền API tổng quát; nó không tự cấp quyền đọc mọi object.

### 10.4. Service-to-service/client credentials

Với client credentials, principal có thể đại diện OAuth client thay vì end user. Claim `sub` có thể không mang user identity theo cách user-delegated token dùng.

Policy cần phân biệt:

- User-delegated token: user subject, client ID, tenant membership và user permissions.
- Client-credentials token: service client, allowed tenants, service scopes và resource policy.

Không áp dụng owner-by-user check cho service principal nếu domain contract cho phép service account. Ngược lại, không để client token có scope rộng tự động truy cập mọi tenant nếu chưa có explicit tenant grant.

## 11. Kiểm tra tenant ID giả mạo qua header và body

Một lỗi thường gặp là token được xác minh đúng, nhưng tenant context lại lấy từ dữ liệu do client tự chọn mà không kiểm tra.

### 11.1. Header mismatch

Ví dụ token có `tenant_id=tenant-a`:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <TOKEN-A>
X-Tenant-ID: tenant-b
~~~

Nếu API cho phép header chọn active tenant, request phải bị từ chối khi user/client không có membership ở tenant B. Không được ghi đè tenant context từ claim bằng header một cách vô điều kiện.

~~~java
@Test
void tenantHeaderCannotOverrideTokenTenant() throws Exception {
    String token = tokens.issue(
        "user-a", "tenant-a", "orders.read"
    );

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .header("X-Tenant-ID", "tenant-b"))
        .andExpect(status().isForbidden());
}
~~~

Nếu API không hỗ trợ tenant header, có thể bỏ qua header hoặc reject theo contract. Điều quan trọng là header không được làm request vượt tenant boundary.

### 11.2. Body mismatch khi tạo order

Một endpoint create có thể nhận DTO:

~~~java
public record CreateOrderRequest(
    String tenantId,
    String description
) {}
~~~

Service nên xác định tenant từ authenticated context đã được authorize:

~~~java
public Order createOrder(
        String authorizedTenantId,
        CreateOrderRequest request) {

    if (request.tenantId() != null
            && !request.tenantId().equals(authorizedTenantId)) {
        throw new AccessDeniedException("Tenant mismatch");
    }

    return repository.save(
        new Order(authorizedTenantId, request.description())
    );
}
~~~

Test:

~~~java
@Test
void cannotCreateOrderForAnotherTenant() throws Exception {
    String token = tokens.issue(
        "user-a", "tenant-a", "orders.write"
    );

    mvc.perform(post("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "tenantId": "tenant-b",
                  "description": "cross-tenant attempt"
                }
                """))
        .andExpect(status().isForbidden());

    assertThat(orders.countByTenantId("tenant-b")).isEqualTo(0);
}
~~~

Đây là test side effect: ngoài status, phải xác nhận không có order mới được ghi vào tenant B. Nếu DTO không cần tenant ID do client gửi, thiết kế đơn giản hơn là loại field đó khỏi request contract và gán tenant từ security context/service policy.

## 12. Kiểm tra tenant isolation ở query và response

### 12.1. Repository query phải scoped

Với Spring Data JPA:

~~~java
Optional<Order> findByIdAndTenantId(
    UUID id,
    String tenantId
);
~~~

Với truy vấn tùy chỉnh:

~~~java
@Query("""
    select o
    from Order o
    where o.id = :orderId
      and o.tenantId = :tenantId
    """)
Optional<Order> findVisibleOrder(
    UUID orderId,
    String tenantId
);
~~~

Đừng tải resource toàn cục rồi quên kiểm tra tenant trong một nhánh code. Tenant predicate phải hiện diện ở query boundary hoặc một data-access abstraction được bảo vệ thống nhất.

### 12.2. Kiểm tra response không lộ dữ liệu

Negative integration test nên assert:

- Status theo policy.
- Body không chứa description, customer, owner hoặc tenant data của resource bị cấm.
- Không trả nested relationships thuộc tenant khác.
- Không có file URL/download link của tenant khác.
- Không ghi audit event với dữ liệu nhạy cảm không được phép.

Một response 403 vẫn có thể vô tình chứa resource DTO nếu controller đã load dữ liệu trước khi từ chối. Hãy assert body và side effects, không chỉ status code.

### 12.3. List, search, export và pagination

Cross-tenant leak không chỉ xảy ra ở endpoint lấy một ID:

- List/search theo tenant ID do client gửi.
- Search theo customer ID.
- Export CSV/Excel.
- Count/summary dashboard.
- Pagination cursor.
- Bulk action với danh sách IDs.
- Download attachment.
- WebSocket/SSE subscriptions.

Test list endpoints cần chứng minh query luôn scope theo tenant. Với bulk IDs, tất cả IDs phải thuộc phạm vi caller hoặc request phải bị reject nguyên tử theo contract; không xử lý một phần rồi bỏ qua các IDs còn lại nếu điều đó gây side effects không mong muốn.

### 12.4. Cache phải bao gồm tenant trong cache key

Nếu cache chỉ dùng order ID nhưng ID không globally unique hoặc authorization result phụ thuộc tenant, có thể trả dữ liệu đã cache của tenant khác.

Ví dụ key an toàn hơn:

~~~text
orders:{tenantId}:{orderId}
~~~

Test hai tenant đọc cùng logical ID hoặc cùng query parameters và xác nhận cache không trả response của tenant còn lại. Nếu cache key chứa principal/permission context, đánh giá cả nguy cơ tăng kích thước và invalidation khi membership bị thu hồi.

## 13. Kiểm thử nhiều issuer và identity collision

Một hệ thống multi-tenant có thể chấp nhận token từ nhiều issuers. Khi đó không thể chỉ dùng `sub` làm global user ID.

Ví dụ:

~~~text
Issuer A: iss=https://id-a.example.test, sub=user-123
Issuer B: iss=https://id-b.example.test, sub=user-123
~~~

Hai token có cùng `sub` nhưng có thể đại diện hai người khác nhau.

Test nên xác nhận:

- Issuer A không thể dùng identity mapping của issuer B.
- Membership lookup dùng cặp issuer/subject hoặc internal identity đã chuẩn hóa.
- Tenant ID không bị nhầm giữa các identity providers.
- Issuer không được allowlist bị reject ở authentication (401).
- Token từ issuer hợp lệ nhưng không có tenant membership bị deny ở authorization.

Không tự động tin issuer chỉ vì JWT có `iss` hợp lệ về cú pháp. Issuer phải nằm trong trust configuration của Resource Server.

## 14. Kiểm tra tenant boundary trong method security và các entry points

### 14.1. URL authorization chưa đủ

Một URL matcher có thể yêu cầu scope:

~~~java
.pathMatchers("/api/tenants/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Điều đó chỉ kiểm tra scope. Nó không biết path tenant có khớp principal hoặc resource ownership không.

Có thể đặt tenant authorization trong method security:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') and " +
    "@tenantAccess.canAccess(authentication, #tenantId)"
)
public OrderDto getOrder(String tenantId, UUID orderId) {
    // tenant-scoped repository query
}
~~~

Hoặc dùng custom `AuthorizationManager` nếu policy thuộc request authorization layer. Dù chọn vị trí nào, policy phải được áp dụng nhất quán trên mọi entry point.

### 14.2. Không để một đường gọi bypass policy

Cùng service có thể được gọi từ REST controller, scheduled job, message listener, GraphQL resolver, admin endpoint hoặc internal service.

Nếu chỉ controller kiểm tra tenant, một message listener hoặc admin route có thể gọi service trực tiếp. Đặt invariant tenant ở service/data access boundary hoặc truyền explicit authorization context đã được xác minh.

### 14.3. Admin cross-tenant access phải explicit

Một platform admin có thể có quyền truy cập nhiều tenant. Đừng biến việc thiếu tenant match thành bypass mặc định.

Policy cần một authority/permission riêng, audit đầy đủ và có thể yêu cầu tenant selection explicit. Test:

- User thường không được cross tenant.
- Tenant admin chỉ quản trị tenant của mình.
- Platform admin được phép theo policy cụ thể.
- Platform admin thiếu permission tương ứng vẫn bị deny.
- Audit record ghi actor, tenant mục tiêu và hành động.

## 15. Kiểm tra 401, 403 và 404 đúng ngữ nghĩa

| Trường hợp | Authentication | Authorization/resource lookup | Response thường dùng |
|---|---|---|---|
| Không có token | Không authenticated | Chưa chạy policy | 401 |
| Signature/issuer/audience/expiry sai | Authentication failure | Chưa chạy policy | 401 |
| Token hợp lệ nhưng thiếu scope | Authenticated | Scope denied | 403 |
| Token tenant A yêu cầu tenant B | Authenticated | Tenant denied | 403 hoặc 404 |
| Token tenant A yêu cầu ID thuộc B | Authenticated | Scoped lookup không tìm thấy | 404 hoặc 403 |
| Tenant đúng nhưng user không phải owner | Authenticated | Resource ACL denied | 403 hoặc 404 |
| Resource không tồn tại trong tenant hiện tại | Authenticated | Không tìm thấy | 404 |
| Membership đã revoke | Authenticated token, current policy denied | Membership denied | 403 hoặc 404 |

Chọn response theo API contract và chính sách che giấu resource existence. Không trả 401 cho một token hợp lệ chỉ vì user không thuộc tenant; 401 mô tả authentication failure, còn tenant mismatch là authorization failure.

Nếu dùng 404 để tránh enumeration, bảo đảm resource thật sự không tồn tại và resource tồn tại ở tenant khác có cùng response body/status/timing đủ gần theo threat model. Đừng tiết lộ “order này tồn tại nhưng thuộc tenant B”.

## 16. Kiểm tra database isolation sâu hơn

### 16.1. Composite tenant keys

Một số schema dùng primary key kết hợp tenant:

~~~sql
create table orders (
    tenant_id varchar(80) not null,
    order_id varchar(80) not null,
    description varchar(500) not null,
    primary key (tenant_id, order_id)
);
~~~

Khi đó repository nên truy vấn bằng cả hai key. Test cần xác nhận tenant ID luôn có trong predicate.

### 16.2. Database Row-Level Security

Nếu dùng PostgreSQL Row-Level Security (RLS), policy database có thể giới hạn row theo tenant context trong session. Khi đó integration test cần chạy trên database có hỗ trợ RLS (ví dụ PostgreSQL Testcontainers), không chỉ H2 nếu semantics khác nhau.

Các test quan trọng:

- Không set tenant context thì query không trả row hoặc bị từ chối theo policy.
- Set tenant A thì không đọc được row tenant B.
- Connection được trả về pool không giữ tenant context của request trước.
- Transaction/session variable được reset đúng khi connection reuse.
- Native queries/bulk updates cũng chịu RLS.
- Background jobs thiết lập tenant context rõ ràng.

Không xem RLS là lý do bỏ application authorization. RLS và service policy có thể bảo vệ các lớp khác nhau. Cần xác minh transaction/session behavior cụ thể của database driver và connection pool.

### 16.3. Connection pool và tenant context

Nếu tenant context được lưu trong database session variable, test nên mô phỏng reuse cùng connection giữa hai request:

~~~text
Request A sets tenant-a
Request A completes and returns connection to pool
Request B obtains reused connection
Request B must not inherit tenant-a accidentally
~~~

Context bị giữ lại có thể gây cross-tenant denial hoặc leak. Cleanup cần nằm trong transaction/session lifecycle đáng tin cậy, không dựa vào một finally block ở controller.

## 17. Kiểm thử side effects và tính nguyên tử

Với thao tác write, không chỉ kiểm tra HTTP status:

- Không tạo record cho tenant sai.
- Không update/delete resource thuộc tenant khác.
- Không gửi message/event trước khi authorization thành công.
- Không upload file vào bucket/prefix của tenant khác.
- Không gọi downstream service với tenant context sai.
- Không cập nhật cache hoặc search index sai tenant.

Ví dụ test update:

~~~java
@Test
void tenantATokenCannotModifyTenantBOrder() throws Exception {
    String token = tokens.issue(
        "user-a", "tenant-a", "orders.write"
    );

    mvc.perform(put("/api/tenants/tenant-b/orders/order-b1")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"description":"changed by tenant A"}
                """))
        .andExpect(status().isForbidden());

    Order stored = orders.findByIdAndTenantId(
        UUID.fromString("..."),
        "tenant-b"
    ).orElseThrow();

    assertThat(stored.getDescription())
        .isEqualTo("original tenant B description");
}
~~~

ID trong ví dụ cần thay bằng fixture UUID thực tế. Assertion quan trọng là state của tenant B không đổi sau request bị từ chối.

Nếu request tạo event, test cả event publisher/outbox table. Authorization phải hoàn tất trước khi side effect không thể đảo ngược được phát ra.

## 18. Những test dễ tạo cảm giác an toàn giả

### “Token A bị từ chối khi gọi path tenant B, vậy isolation đã đúng”

Chưa đủ. Code có thể từ chối path mismatch nhưng vẫn cho token A truy cập order B bằng IDOR qua path tenant A. Cần test riêng resource tenant mismatch.

### “JWT audience đúng nghĩa là user thuộc tenant”

Không. Audience xác định intended recipient của token. Tenant membership là authorization data khác.

### “Claim tenant_id có trong JWT nên không cần database”

Chỉ đúng nếu contract cho phép claim là nguồn quyền có hiệu lực đến hết token lifetime. Nếu membership có thể bị thu hồi ngay, cần policy có kiểm tra trạng thái hiện tại hoặc revocation mechanism.

### “Controller đã kiểm tra tenant nên repository không cần filter”

Service có thể được gọi từ đường khác và một query sai có thể làm lộ row. Tenant predicate ở data-access boundary tạo thêm bảo vệ.

### “Test dùng @WithMockUser đã chứng minh multi-tenant Resource Server”

Không. Nó bỏ qua JWT decoder, token claims và principal contract. Dùng signed JWT qua filter chain cho integration test.

### “MockMvc jwt() kiểm tra issuer và chữ ký”

Không. Helper tạo Authentication giả lập. Nó phù hợp cho principal/authorization tests, không phải token validation integration.

### “Response 403 là đủ”

Không. Controller có thể đã load dữ liệu hoặc tạo side effect trước khi trả 403. Assert response body, database state, outbox/events và downstream calls.

### “Không thấy data trong JSON nghĩa là không có leak”

Có thể vẫn leak qua count, pagination, timing, cache, export, download URL hoặc error message. Test cả các kênh dữ liệu mà API cung cấp.






## 19. Kịch bản kiểm chứng tích hợp theo từng loại endpoint

| Endpoint type | Negative cases cần có |
|---|---|
| Get by ID | ID thuộc tenant khác; path tenant mismatch; owner mismatch |
| List/search | Query tenant khác; filter/header spoof; pagination count leakage |
| Create | Body tenant spoof; principal thiếu write scope; membership revoked |
| Update | Record thuộc tenant khác; tenant ID thay đổi trong payload |
| Delete | IDOR; soft-delete side effects; event/outbox không được tạo |
| Bulk operation | Danh sách IDs trộn nhiều tenant; không xử lý một phần ngoài ý muốn |
| Export/download | File object/prefix tenant khác; signed URL không được cấp |
| Admin operations | Tenant admin truy cập tenant khác; platform admin explicit permission |
| Async job/message | Tenant context được truyền và xác minh; không dùng context của request trước |

Không cần tất cả endpoint có cùng một implementation, nhưng mọi đường truy cập dữ liệu tenant phải có một invariant được kiểm chứng.

## 20. CI và dữ liệu test multi-tenant

Một pipeline có thể chia thành:

~~~text
Pull request:
  1. Tenant policy unit tests
  2. Repository tenant-scope tests
  3. Signed JWT Resource Server integration tests
  4. Cross-tenant read/write negative tests
  5. Membership and owner authorization tests
  6. Cache / event / outbox side-effect tests

Database integration suite:
  7. PostgreSQL Testcontainers for RLS/session behavior (if used)
  8. Connection-pool tenant-context isolation
  9. Concurrent requests across tenants

Release candidate:
 10. Gateway / proxy / identity-provider sandbox tests
 11. Tenant admin and platform admin policy scenarios
 12. Audit and operational monitoring checks
~~~

Dữ liệu test phải tổng hợp, không lấy customer records production. Dùng tenant IDs và user IDs rõ ràng, dễ đọc trong assertion. Test không phụ thuộc thứ tự chạy hoặc shared mutable tenant context.

Với test song song, mỗi test nên có namespace/fixture riêng hoặc database cleanup đáng tin cậy. Tránh hai test cùng update membership hoặc tenant state dùng chung.

## 21. Checklist kiểm chứng multi-tenant

- [ ] Token có chữ ký, issuer, audience và thời hạn hợp lệ.
- [ ] Test dùng compact signed JWT qua Resource Server filter chain.
- [ ] Tenant A token đọc được resource A khi scope và policy cho phép.
- [ ] Tenant A token không đọc được resource B.
- [ ] Path tenant A không làm lộ resource ID thuộc tenant B.
- [ ] User không có membership bị từ chối.
- [ ] Membership revoke được phản ánh theo revocation policy.
- [ ] Scope thiếu dẫn tới authorization denial.
- [ ] Tenant header/body không ghi đè authorization context.
- [ ] Repository query luôn có tenant predicate.
- [ ] Owner/team permission được kiểm tra khi domain yêu cầu.
- [ ] List/search/export/bulk endpoints không rò dữ liệu cross-tenant.
- [ ] Cache key có tenant context khi dữ liệu phụ thuộc tenant.
- [ ] Write bị từ chối không tạo database changes, events hoặc downstream calls.
- [ ] Multi-issuer identity dùng issuer context, không chỉ subject.
- [ ] Client-credentials và user-delegated tokens có policy riêng.
- [ ] Platform admin cross-tenant access là quyền explicit và được audit.
- [ ] 401, 403 và 404 phản ánh đúng tầng lỗi.
- [ ] Nếu dùng RLS, test trên database đúng engine và kiểm tra connection reuse.
- [ ] CI dùng synthetic users/tenants/tokens và không dùng production credentials.

## 22. Kết luận

Trong hệ thống multi-tenant, **token hợp lệ chỉ chứng minh principal đã được xác thực**. Nó không tự cấp quyền truy cập mọi tenant hoặc mọi resource trong API.

Một integration test cần đi qua Resource Server filter chain với signed access token và chứng minh các ranh giới sau:

1. **Token trust:** issuer, audience, chữ ký, thời hạn và token profile hợp lệ.
2. **Tenant context:** tenant request được chọn khớp policy của principal hoặc membership hiện tại.
3. **Resource ownership:** bản ghi thực tế thuộc tenant được phép và đáp ứng owner/team permissions.
4. **Data isolation:** repository, list/search, cache, export và database layer không trả dữ liệu tenant khác.
5. **Side-effect isolation:** write, event, file và downstream calls không xảy ra khi authorization bị từ chối.
6. **HTTP semantics:** token invalid trả 401; token valid nhưng không có quyền trả 403 hoặc 404 theo contract.

Hãy luôn có ít nhất hai negative scenarios riêng: token tenant A gọi path tenant B, và token tenant A gọi path tenant A nhưng cung cấp ID của resource tenant B. Hai test này bảo vệ hai ranh giới khác nhau: tenant selection và resource-level access.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference — Multi-tenancy for JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security Reference — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)



