# Kiểm thử cô lập tenant và quyền đăng ký, quản trị client

Một Authorization Server phục vụ nhiều tenant phải bảo đảm mỗi tenant chỉ quản lý được client và dữ liệu thuộc phạm vi của mình. Một lỗi kiểm tra quyền ở API quản trị, một truy vấn repository thiếu điều kiện tenant hoặc một cache dùng sai khóa có thể làm lộ cấu hình client, cho phép thay đổi redirect URI hoặc mở rộng scope cho tenant khác.

Spring Authorization Server cung cấp mô hình `RegisteredClient`, `RegisteredClientRepository`, authorization và consent. Nó không tự cung cấp mô hình tenant hay toàn bộ quy trình quản trị client. Ứng dụng phải xây dựng tenant context, ánh xạ quyền quản trị, lưu quan hệ sở hữu client và bảo vệ các endpoint quản trị. Vì vậy, kiểm thử cần bao phủ cả API, service, database và các luồng OAuth 2.0/OIDC sử dụng client đã đăng ký.

Bài thực hành này xây dựng ma trận quyền, tạo dữ liệu cho hai tenant, kiểm thử truy cập chéo, kiểm thử đăng ký và cập nhật client, rồi xác minh các luồng authorization/token không thể dùng client của tenant khác. Các ví dụ là khung tích hợp cho ứng dụng; hãy điều chỉnh endpoint, principal và repository theo kiến trúc thực tế.

## 1. Mục tiêu và mô hình đe dọa

Giả sử một Authorization Server dùng chung phục vụ hai tenant:

- `tenant-a` quản lý client `portal-a` và `orders-a`.
- `tenant-b` quản lý client `portal-b` và `orders-b`.
- `platform-admin` có quyền quản trị toàn hệ thống.
- `tenant-admin` chỉ quản trị tenant được gán.
- `tenant-viewer` chỉ đọc cấu hình trong tenant được gán.

Các tài sản cần bảo vệ gồm thông tin client, client secret đã mã hóa, redirect URI, scope, grant type, phương thức xác thực client, cấu hình token, authorization, consent và lịch sử audit. Những hành vi cần phát hiện gồm:

- Tenant A đọc, sửa, xóa hoặc vô hiệu hóa client của tenant B.
- Tenant A đăng ký client dưới tenant B hoặc tự gán mình vào tenant khác.
- Tenant viewer thực hiện thao tác quản trị.
- Người chưa đăng nhập gọi API quản trị.
- Client của tenant A được phân giải thành client của tenant B ở authorization/token endpoint.
- Cache, audit, background job hoặc thao tác bulk vô tình trộn dữ liệu giữa các tenant.
- Client được đăng ký với redirect URI, scope, grant type hoặc phương thức xác thực vượt chính sách.

Mục tiêu là kiểm tra **quyền trên hành động** và **quyền trên đúng đối tượng**. Chỉ xác minh người gọi có role `TENANT_ADMIN` là chưa đủ; server còn phải xác minh tenant của principal có quyền quản lý client đích.

## 2. Ma trận quyền cần kiểm thử

Một ma trận tham khảo:

| Hành động | Chưa đăng nhập | Tenant viewer | Tenant admin cùng tenant | Platform admin |
|---|---:|---:|---:|---:|
| Xem danh sách client trong tenant | 401 | Cho phép | Cho phép | Cho phép |
| Xem chi tiết client trong tenant | 401 | Cho phép | Cho phép | Cho phép |
| Tạo client trong tenant | 401 | 403 | Cho phép | Cho phép |
| Sửa cấu hình client | 401 | 403 | Cho phép | Cho phép |
| Xoay client secret | 401 | 403 | Theo quyền đặc biệt | Cho phép |
| Vô hiệu hóa hoặc xóa client | 401 | 403 | Theo chính sách | Cho phép |
| Quản trị client tenant khác | 401 | 403/404 | 403/404 | Cho phép theo audit |
| Thay đổi policy toàn cục | 401 | 403 | 403 | Cho phép |

`401 Unauthorized` thể hiện chưa có danh tính được xác thực; `403 Forbidden` thể hiện đã xác thực nhưng không có quyền. Với endpoint chi tiết, hệ thống có thể trả `404 Not Found` khi tenant không sở hữu đối tượng để tránh tiết lộ sự tồn tại của client. Hãy chọn chính sách nhất quán và kiểm thử cả status lẫn nội dung response để không vô tình làm lộ tên, tenant hoặc trạng thái client.

Các thao tác rủi ro cao như xem lại client secret, xoay credential, thay đổi redirect URI nhạy cảm hoặc cấp scope đặc quyền có thể cần quyền riêng, step-up authentication hoặc phê duyệt hai người. Đừng mặc định mọi `TENANT_ADMIN` đều được thực hiện tất cả thao tác.

## 3. Thiết kế tenant context đáng tin cậy

Tenant context phải đến từ danh tính đã được xác thực và ánh xạ bởi server. Ví dụ principal có thể chứa subject, tenant ID và các authority:

```java
public record TenantPrincipal(
        String subject,
        String tenantId) {
}
```

Trong thực tế, `tenantId` có thể được ánh xạ từ claim đã được xác minh của Identity Provider, từ membership lưu trong database hoặc từ phiên quản trị đã xác thực. Cần kiểm tra issuer, audience, chữ ký, thời hạn token và trạng thái membership trước khi tin claim tenant.

Không dùng `tenantId` do người gọi tự gửi trong JSON body, query string hoặc header tùy ý làm căn cứ phân quyền. Nếu API có path `/admin/tenants/{tenantId}/clients`, giá trị path chỉ xác định đối tượng được yêu cầu; service vẫn phải so sánh nó với tenant trong principal hoặc kiểm tra quyền platform admin.

Với platform admin, thao tác cross-tenant phải chỉ rõ tenant đích và được audit. Với tenant admin, tenant đích phải trùng tenant được cấp. Không tự nâng quyền nếu principal thiếu tenant ID hoặc membership không còn hiệu lực.

### 3.1. Kiểm tra ở nhiều lớp

Áp dụng kiểm soát ở các lớp sau:

1. **HTTP security:** yêu cầu xác thực và role phù hợp cho nhóm endpoint quản trị.
2. **Method/service authorization:** xác minh quyền trên tenant và hành động cụ thể.
3. **Data access:** truy vấn ownership và dữ liệu theo tenant đã xác thực; không dựa vào ID do request cung cấp mà bỏ qua kiểm tra.
4. **OAuth protocol resolution:** đảm bảo client được tìm thấy trong đúng issuer/tenant theo mô hình triển khai.
5. **Side effects:** audit, cache, event, job và thao tác bulk giữ đúng tenant context.

Nếu chỉ bảo vệ controller, một job hoặc service khác có thể gọi repository trực tiếp và bỏ qua quy tắc. Các thao tác ghi cấu hình nên đi qua một domain service có trách nhiệm kiểm tra quyền và tenant ownership.

## 4. Lưu ý về RegisteredClientRepository và định danh client

`RegisteredClientRepository` của Spring Authorization Server có phương thức tra cứu theo `client_id`, chẳng hạn `findByClientId(String clientId)`. Interface này không nhận `tenant_id` trong tham số tra cứu. Vì vậy, với một Authorization Server và một issuer dùng chung, lựa chọn đơn giản, an toàn là giữ `client_id` duy nhất trên toàn bộ issuer rồi lưu quan hệ sở hữu client với tenant.

Ví dụ mô hình dữ liệu mở rộng:

```text
registered_client
  id (primary key)
  client_id (unique trong issuer)
  ... các trường RegisteredClient ...

registered_client_tenant
  registered_client_id (primary key, foreign key)
  tenant_id (foreign key)
  created_at
```

Bảng ownership là phần mở rộng của ứng dụng, không phải schema mặc định mà Spring Authorization Server tự tạo. Ràng buộc khóa ngoại và unique phải bảo đảm một client thuộc đúng phạm vi được thiết kế. Khi tạo client, lưu Registered Client và ownership trong cùng transaction.

Nếu cần cho nhiều tenant dùng cùng `client_id`, phải có phân vùng issuer hoặc cơ chế phân giải tenant tùy chỉnh xuyên suốt authorization endpoint, token endpoint, introspection, revocation và mọi đường tìm Registered Client. Chỉ thêm `tenant_id` vào bảng rồi tiếp tục dùng `findByClientId` không phân biệt tenant là chưa đủ. Hai client cùng ID trong một issuer dùng chung có thể gây nhầm lẫn khi Spring Authorization Server phân giải client từ giao thức OAuth.

Với mô hình một issuer toàn cục, kiểm thử ràng buộc `client_id` unique và kiểm thử rằng tra cứu protocol không thể trả client khác tenant do va chạm ID. Với mô hình mỗi tenant có issuer/Authorization Server riêng, kiểm thử issuer discovery, JWKS, client registration và token validation theo từng issuer.

## 5. Chuẩn bị ứng dụng kiểm thử

Tạo hai tenant và ít nhất hai client cho mỗi tenant trong database kiểm thử. Dùng `RegisteredClientRepository` thật của môi trường kiểm thử cùng bảng ownership do ứng dụng quản lý. Dữ liệu nên có nhiều grant type, scope và client authentication method để kiểm tra cả nội dung cấu hình.

Ví dụ dữ liệu:

| Tenant | Client ID | Loại | Scope |
|---|---|---|---|
| `tenant-a` | `portal-a` | Public client | `openid`, `profile` |
| `tenant-a` | `orders-a` | Confidential client | `orders.read` |
| `tenant-b` | `portal-b` | Public client | `openid`, `profile` |
| `tenant-b` | `orders-b` | Confidential client | `orders.read`, `orders.write` |

Với public client, kiểm tra không có client secret và authorization code flow yêu cầu PKCE theo chính sách. Với confidential client, secret phải được mã hóa trước khi lưu; response API quản trị không được trả secret đã lưu hoặc giá trị hash. Nếu client dùng `private_key_jwt` hoặc mTLS, chỉ hiển thị public key reference hoặc thông tin chứng thư cần thiết.

Tách endpoint quản trị khỏi authorization/token endpoint. Ví dụ endpoint quản trị:

```text
GET    /admin/tenants/{tenantId}/clients
GET    /admin/tenants/{tenantId}/clients/{clientId}
POST   /admin/tenants/{tenantId}/clients
PATCH  /admin/tenants/{tenantId}/clients/{clientId}
POST   /admin/tenants/{tenantId}/clients/{clientId}/rotate-secret
POST   /admin/tenants/{tenantId}/clients/{clientId}/disable
DELETE /admin/tenants/{tenantId}/clients/{clientId}
```

Đây là endpoint minh họa của ứng dụng, không phải endpoint quản trị mặc định của Spring Authorization Server.

## 6. Bảo vệ endpoint quản trị

Có thể bật method security và áp dụng quy tắc role ở HTTP layer. Ví dụ rút gọn:

```java
@Configuration
@EnableMethodSecurity
class AdminSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/admin/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/admin/**")
                            .hasAnyRole("PLATFORM_ADMIN", "TENANT_ADMIN", "TENANT_VIEWER")
                        .requestMatchers(HttpMethod.POST, "/admin/**")
                            .hasAnyRole("PLATFORM_ADMIN", "TENANT_ADMIN")
                        .requestMatchers(HttpMethod.PATCH, "/admin/**")
                            .hasAnyRole("PLATFORM_ADMIN", "TENANT_ADMIN")
                        .requestMatchers(HttpMethod.DELETE, "/admin/**")
                            .hasRole("PLATFORM_ADMIN")
                        .anyRequest().authenticated())
                .build();
    }
}
```

Đây chỉ là lớp role tổng quát. Service vẫn phải xác minh tenant cụ thể, quyền rotate secret và các quyền đặc biệt khác. Đặt filter chain quản trị đúng thứ tự để matcher không che khuất filter chain của Authorization Server. Nếu admin API dùng cookie/session của trình duyệt, giữ CSRF protection và kiểm thử CSRF token. Chỉ cân nhắc stateless/CSRF khác đi khi xác thực bằng bearer token không tự động được trình duyệt gửi; không tắt CSRF toàn ứng dụng chỉ để làm API test dễ hơn.

Ví dụ method authorization cho đọc và ghi:

```java
@PreAuthorize("hasRole('PLATFORM_ADMIN') or " +
        "(hasAnyRole('TENANT_ADMIN', 'TENANT_VIEWER') and " +
        "@tenantAccess.canRead(authentication, #tenantId))")
public ClientView getClient(String tenantId, String clientId) {
    // Đọc client sau khi kiểm tra ownership.
}

@PreAuthorize("hasRole('PLATFORM_ADMIN') or " +
        "(hasRole('TENANT_ADMIN') and " +
        "@tenantAccess.canManage(authentication, #tenantId))")
public ClientView updateClient(String tenantId, String clientId,
                               UpdateClientCommand command) {
    // Cập nhật qua domain service và ghi audit.
}
```

`tenantAccess` là bean do ứng dụng xây dựng. Các biểu thức dùng tên tham số `#tenantId`; bảo đảm build giữ parameter names hoặc dùng annotation hỗ trợ binding tên tham số theo phiên bản Spring. Đừng coi annotation là thay thế kiểm tra ownership ở tầng truy vấn.

## 7. Kiểm thử bằng Spring Boot và MockMvc

Integration test nên chạy với security filter chain và service thật, cùng database kiểm thử. Có thể dùng Testcontainers cho cùng loại database với production để kiểm tra constraint, transaction và truy vấn tenant. Dùng test principal có tenant rõ ràng thay vì chỉ gán role chung chung.

Ví dụ helper tạo Authentication:

```java
private RequestPostProcessor asPrincipal(String tenantId, String role) {
    TenantPrincipal principal = new TenantPrincipal(
            "admin-" + tenantId, tenantId);
    Authentication authentication = new UsernamePasswordAuthenticationToken(
            principal,
            null,
            List.of(new SimpleGrantedAuthority("ROLE_" + role)));

    return SecurityMockMvcRequestPostProcessors.authentication(authentication);
}
```

Helper giả định ứng dụng dùng `TenantPrincipal` làm principal. Nếu principal thực tế là `Jwt`, `UserDetails` hoặc kiểu khác, tạo test Authentication tương ứng với resolver đang dùng. Không mock tenant context theo cách bỏ qua code production cần được kiểm thử.

### 7.1. Tenant A không đọc được client của tenant B

```java
@SpringBootTest
@AutoConfigureMockMvc
class ClientTenantIsolationIT {

    @Autowired
    MockMvc mockMvc;

    @Test
    void tenantAdminCannotReadAnotherTenantsClient() throws Exception {
        mockMvc.perform(get(
                        "/admin/tenants/{tenantId}/clients/{clientId}",
                        "tenant-b", "orders-b")
                .with(asPrincipal("tenant-a", "TENANT_ADMIN")))
            .andExpect(status().isNotFound());
    }
}
```

Ví dụ chọn `404` để che giấu sự tồn tại của client ngoài tenant. Nếu API chọn `403`, hãy thay assertion tương ứng và xác minh response không chứa dữ liệu của client B. Bài test phải chạy với client `orders-b` đã tồn tại; nếu client không tồn tại từ đầu, test không chứng minh được kiểm soát tenant.

### 7.2. Tenant A không sửa hoặc xóa client của tenant B

```java
@Test
void tenantAdminCannotUpdateAnotherTenantsClient() throws Exception {
    String body = """
            {
              "clientName": "Compromised name",
              "scopes": ["orders.read", "orders.write"]
            }
            """;

    mockMvc.perform(patch(
                    "/admin/tenants/{tenantId}/clients/{clientId}",
                    "tenant-b", "orders-b")
            .with(asPrincipal("tenant-a", "TENANT_ADMIN"))
            .contentType(MediaType.APPLICATION_JSON)
            .content(body))
        .andExpect(status().isNotFound());

    mockMvc.perform(delete(
                    "/admin/tenants/{tenantId}/clients/{clientId}",
                    "tenant-b", "orders-b")
            .with(asPrincipal("tenant-a", "TENANT_ADMIN")))
        .andExpect(status().isNotFound());
}
```

Sau request, truy vấn database để xác minh `clientName`, scope, trạng thái và ownership của `orders-b` không thay đổi. Kiểm tra cả audit/outbox: không được có sự kiện `CLIENT_UPDATED` hoặc `CLIENT_DELETED` thành công do actor tenant A tạo ra. Nếu ghi sự kiện từ chối, sự kiện phải chỉ chứa metadata an toàn.

### 7.3. Viewer không được đăng ký hoặc quản trị client

```java
@Test
void viewerCannotRegisterClient() throws Exception {
    String body = """
            {
              "clientName": "New portal",
              "grantTypes": ["authorization_code"],
              "redirectUris": ["https://portal.example.test/callback"],
              "scopes": ["openid", "profile"]
            }
            """;

    mockMvc.perform(post("/admin/tenants/{tenantId}/clients", "tenant-a")
            .with(asPrincipal("tenant-a", "TENANT_VIEWER"))
            .contentType(MediaType.APPLICATION_JSON)
            .content(body))
        .andExpect(status().isForbidden());
}
```

Xác minh database không có client mới và không có ownership record. Thực hiện tương tự với PATCH, disable, rotate-secret và DELETE. Một viewer có thể được phép xem cấu hình đã loại bỏ secret, nhưng không được xem credential hoặc thay đổi policy.

### 7.4. Tenant không thể tự khai tenant khác trong body

```java
@Test
void tenantAdminCannotCreateClientForAnotherTenant() throws Exception {
    String body = """
            {
              "tenantId": "tenant-b",
              "clientName": "Injected client",
              "grantTypes": ["client_credentials"],
              "scopes": ["orders.read"]
            }
            """;

    mockMvc.perform(post("/admin/tenants/{tenantId}/clients", "tenant-b")
            .with(asPrincipal("tenant-a", "TENANT_ADMIN"))
            .contentType(MediaType.APPLICATION_JSON)
            .content(body))
        .andExpect(status().isNotFound());
}
```

Request dùng cả path và body để nhắm đến `tenant-b`, trong khi principal thuộc `tenant-a`; API trả `404` theo chính sách che giấu đối tượng ngoài tenant. Nếu API chủ động từ chối trường `tenantId` do client gửi, có thể trả `400` trước bước kiểm tra ownership. Nếu DTO bỏ qua trường này, tenant vẫn phải được suy ra từ principal và path đã được xác minh. Trong mọi trường hợp, kiểm tra database để bảo đảm không tạo client thuộc tenant B.

### 7.5. Platform admin có thể quản trị tenant khác

```java
@Test
void platformAdminCanReadAnotherTenantsClient() throws Exception {
    mockMvc.perform(get(
                    "/admin/tenants/{tenantId}/clients/{clientId}",
                    "tenant-b", "orders-b")
            .with(asPrincipal("platform", "PLATFORM_ADMIN")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.clientId").value("orders-b"))
        .andExpect(jsonPath("$.tenantId").value("tenant-b"));
}
```

Thao tác cross-tenant của platform admin phải có audit actor, tenant đích, client ID, action, outcome và lý do theo policy. Kiểm thử xác nhận audit được ghi cùng transaction hoặc qua outbox theo thiết kế.

## 8. Kiểm thử quy tắc đăng ký client

Một tenant admin có quyền tạo client không đồng nghĩa được phép tạo mọi cấu hình. Kiểm thử domain validation độc lập với kiểm thử role.

### 8.1. Kiểm soát redirect URI

- Chỉ cho phép redirect URI theo danh sách domain hoặc quy tắc đã được duyệt.
- Từ chối wildcard host, scheme không an toàn và URI có user-info bất thường.
- Không chấp nhận redirect URI của tenant khác nếu policy yêu cầu phân vùng domain.
- So khớp URI chính xác trong authorization request; không dùng prefix matching tùy tiện.
- Với native app, áp dụng quy tắc redirect URI riêng phù hợp chuẩn và nền tảng.

Kiểm thử positive cho URI hợp lệ và negative cho host gần giống, subdomain không được phép, `http` ngoài localhost, path lạ và URI có encoded ký tự nhằm vượt validation.

### 8.2. Kiểm soát scope và grant type

Tenant admin chỉ được gán scope nằm trong allowlist tenant hoặc quyền được cấp cho actor. Không cho client tự khai `admin`, `system`, `billing.write` hoặc scope nội bộ nếu không có phê duyệt. Grant type cần phù hợp với loại client: public client thường dùng authorization code với PKCE; client credentials chỉ dành cho confidential client có xác thực client phù hợp.

Kiểm thử:

- Scope hợp lệ được lưu đúng.
- Scope không thuộc tenant hoặc vượt quyền actor bị từ chối.
- Public client không được cấp client secret.
- Public client yêu cầu PKCE theo policy.
- Confidential client phải có client authentication method hợp lệ.
- Grant type bị cấm theo tenant hoặc loại client bị từ chối.
- Token TTL, refresh token reuse và consent setting không vượt policy tối đa/tối thiểu.

### 8.3. Bảo vệ client secret và credential

Khi tạo confidential client, secret cần được tạo bởi server hoặc quy trình cấp credential có kiểm soát. Lưu secret đã được mã hóa bằng `PasswordEncoder` phù hợp; response tạo mới chỉ hiển thị secret một lần nếu sản phẩm có yêu cầu. API GET/list/update không được trả secret, giá trị hash hoặc private key.

Kiểm thử response body, log và audit snapshot để bảo đảm không có credential. Với `private_key_jwt`, lưu public JWKS URL hoặc public key metadata. Với mTLS, lưu certificate identity/fingerprint theo thiết kế. Không lưu private key của client trong Registered Client.

## 9. Kiểm thử ownership ở service và database

MockMvc xác minh HTTP security nhưng chưa đủ để phát hiện truy vấn database thiếu tenant filter. Cần test trực tiếp domain service và repository.

### 9.1. Service phải kiểm tra cả tenant và đối tượng

Một luồng service tham khảo:

```java
public RegisteredClient requireManagedClient(
        Authentication authentication,
        String requestedTenantId,
        String clientId) {

    boolean platformAdmin = authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_PLATFORM_ADMIN"));

    TenantPrincipal principal = (TenantPrincipal) authentication.getPrincipal();

    if (!platformAdmin && !principal.tenantId().equals(requestedTenantId)) {
        throw new AccessDeniedException("Tenant access denied");
    }

    RegisteredClient client = registeredClientRepository.findByClientId(clientId);
    if (client == null) {
        throw new ClientNotFoundException();
    }

    ClientTenantOwnership ownership = ownershipRepository
            .findByRegisteredClientId(client.getId())
            .orElseThrow(ClientNotFoundException::new);

    if (!platformAdmin && !ownership.tenantId().equals(principal.tenantId())) {
        throw new ClientNotFoundException();
    }

    return client;
}
```

Đây là ví dụ minh họa; cần xử lý principal type an toàn, kiểm tra role/authority cho từng hành động và dùng exception mapping nhất quán. Với platform admin, vẫn cần xác minh `requestedTenantId` tồn tại và ghi audit. Không cho phép caller truyền `platformAdmin=true` hoặc `tenantId` trong body để thay đổi kết quả.

### 9.2. Kiểm tra transaction khi đăng ký client

Tạo Registered Client và bản ghi ownership trong cùng transaction. Nếu bước lưu ownership thất bại, Registered Client cũng phải rollback. Nếu một client ID đã tồn tại, thao tác phải thất bại mà không ghi đè client thuộc tenant khác.

Các test database cần xác minh:

- `client_id` duy nhất trong phạm vi issuer dùng chung.
- Một Registered Client chỉ có ownership hợp lệ theo mô hình tenant đã chọn.
- Không thể tạo ownership record trỏ đến client không tồn tại.
- Không thể đổi tenant ownership bằng PATCH client thông thường.
- Xóa client và ownership tuân thủ cùng transaction và chính sách retention/audit.
- Cập nhật đồng thời không làm mất ownership hoặc ghi đè cấu hình mới hơn.

### 9.3. Kiểm tra query isolation

Seed dữ liệu của tenant A và B rồi truy vấn từng tenant. So sánh toàn bộ ID trả về với tập dữ liệu mong đợi. Kiểm tra các biến thể truy vấn: list có phân trang, search theo client name, lọc theo status, bulk export, count, autocomplete và endpoint audit. Một endpoint phụ quên filter tenant cũng có thể gây rò rỉ dữ liệu.

Nếu database hỗ trợ row-level security, có thể thêm kiểm thử policy ở database như một lớp phòng vệ bổ sung. Không dùng row-level security để thay thế xác thực actor và tenant ở ứng dụng; transaction phải thiết lập tenant context đúng và reset an toàn khi trả connection về pool.

## 10. Kiểm thử các luồng OAuth 2.0/OIDC

Client administration phải khớp với cách Authorization Server phân giải Registered Client trong giao thức. Kiểm thử API quản trị thành công nhưng token endpoint dùng nhầm client vẫn là lỗi nghiêm trọng.

Với từng client của tenant A và B, kiểm tra:

- Authorization request chỉ dùng redirect URI đã đăng ký cho đúng client.
- Client không thể thay `client_id` trong request để dùng cấu hình của tenant khác.
- Token endpoint chỉ chấp nhận phương thức xác thực client đã đăng ký.
- Grant type và scope được cấp nằm trong cấu hình client và policy tenant.
- Client bị disable không thể tiếp tục khởi tạo luồng mới hoặc lấy token mới theo chính sách.
- Consent và authorization không bị đọc hoặc dùng chéo tenant.
- Resource Server xác minh issuer, audience, scope và tenant claim theo nguồn tin cậy.

Đối với authorization code flow, gửi request bằng client A nhưng thay redirect URI bằng redirect URI của client B; server phải từ chối. Thử đổi `client_id` từ `portal-a` sang `portal-b` trong token exchange; code được phát hành cho client A không được đổi bằng client B. Với client credentials, dùng secret của client B cùng `client_id` A phải thất bại.

Nếu mỗi tenant có issuer riêng, kiểm tra token từ issuer A bị Resource Server của tenant B từ chối, kể cả khi subject hoặc client name trùng nhau. Nếu một issuer chung có tenant claim, claim đó phải do Authorization Server phát hành và được Resource Server kiểm tra theo policy; không tin tenant ID từ request API.

## 11. Kiểm thử cache, audit và tác vụ nền

Tenant isolation có thể bị phá vỡ ngoài request/response path:

- Cache client theo `client_id` mà không đưa tenant hoặc issuer vào cache key khi kiến trúc cần phân vùng.
- Background job lấy danh sách client toàn cục rồi thực hiện hành động theo tenant sai.
- Message/event thiếu tenant ID hoặc dùng tenant ID do payload không đáng tin cậy cung cấp.
- Audit record ghi sai tenant hoặc endpoint tìm kiếm audit không lọc theo quyền.
- Export file chứa client của nhiều tenant được gửi đến admin tenant đơn lẻ.
- Metrics/log gắn nhãn tenant sai làm che khuất hoạt động bất thường.

Kiểm thử cache bằng cách đọc client B qua một context hợp lệ của platform admin, sau đó gọi cùng đường code với tenant A và xác nhận cache không trả dữ liệu B. Kiểm thử cache invalidation sau khi client bị disable hoặc chuyển trạng thái. Nếu dùng cache theo issuer, issuer phải là phần của cache key.

Với event-driven workflow, xác minh consumer kiểm tra tenant ownership từ dữ liệu tin cậy trước khi xử lý. Không coi message broker payload là bằng chứng quyền. Với audit, kiểm tra actor, tenant, target, outcome và before/after snapshot đã lọc; tenant admin chỉ truy vấn được audit trong tenant của mình.

## 12. Bộ ca kiểm thử bảo mật tối thiểu

| ID | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|
| TEN-01 | Anonymous gọi API quản trị | 401 |
| TEN-02 | Viewer đọc client cùng tenant | 200, không có secret |
| TEN-03 | Viewer tạo/sửa/xóa client | 403, database không đổi |
| TEN-04 | Tenant admin đọc client cùng tenant | 200 |
| TEN-05 | Tenant admin đọc client tenant khác | 403 hoặc 404 theo policy, không lộ dữ liệu |
| TEN-06 | Tenant admin sửa/xóa client tenant khác | Bị từ chối, không có side effect |
| TEN-07 | Tenant admin gửi tenant ID giả trong body/header | Bị từ chối hoặc bỏ qua; ownership vẫn đúng |
| TEN-08 | Platform admin quản trị tenant khác | Cho phép theo policy và có audit |
| CLI-01 | Tạo client với scope/grant hợp lệ | Được lưu đúng tenant |
| CLI-02 | Tạo client với scope đặc quyền không được cấp | 400/403 theo policy |
| CLI-03 | Redirect URI không thuộc allowlist | Bị từ chối |
| CLI-04 | Client ID trùng trong cùng issuer | Bị từ chối, không ghi đè |
| CLI-05 | Lỗi lưu ownership sau khi lưu client | Toàn bộ transaction rollback |
| CLI-06 | Public client gửi secret hoặc thiếu PKCE | Bị từ chối theo policy |
| OAU-01 | Dùng client A với redirect URI của B | Authorization request bị từ chối |
| OAU-02 | Đổi authorization code A bằng client B | Token endpoint từ chối |
| OAU-03 | Dùng secret B với client ID A | Client authentication thất bại |
| OAU-04 | Client disabled xin token mới | Bị từ chối theo policy |
| DAT-01 | List/search/export client | Chỉ có dữ liệu tenant được phép |
| DAT-02 | Cache được làm nóng bởi platform admin rồi tenant admin đọc | Không rò dữ liệu chéo tenant |
| DAT-03 | Truy vấn audit tenant khác | Bị từ chối hoặc trả 404 |
| DAT-04 | Background job xử lý event thiếu tenant hợp lệ | Không thực hiện thay đổi |

## 13. Tiêu chí nghiệm thu và báo cáo lỗi

Một ca kiểm thử bảo mật phải xác minh nhiều hơn HTTP status:

- **Không rò dữ liệu:** response không chứa client name, redirect URI, scope, secret hoặc tenant metadata ngoài quyền.
- **Không có side effect:** database, cache, message, audit và trạng thái client không bị thay đổi trái phép.
- **Có audit phù hợp:** thao tác được phép được ghi nhận; thao tác bị từ chối có thể được ghi nhận theo policy mà không chứa payload nhạy cảm.
- **Không có đường vòng:** service, repository, job và endpoint protocol đều áp dụng cùng quy tắc tenant.
- **Có khả năng lặp lại:** test fixture tạo dữ liệu xác định và cleanup an toàn; không phụ thuộc dữ liệu production.

Khi phát hiện lỗi, báo cáo gồm endpoint/operation, role, tenant của actor, tenant của đối tượng, dữ liệu seed, request đã loại bỏ credential, response, trạng thái database trước/sau và correlation ID. Không đính kèm client secret, access token hoặc cookie thật.

## 14. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra role `TENANT_ADMIN` | Admin tenant A có thể thao tác đối tượng tenant B | Kiểm tra tenant ownership trên từng đối tượng |
| Tin `tenantId` trong request body | Caller tự gán tenant mục tiêu | Lấy tenant từ principal đã xác thực và kiểm tra path |
| Chỉ lọc tenant ở giao diện | API có thể bị gọi trực tiếp để đọc tenant khác | Enforcement ở server/service/repository |
| Dùng `findByClientId` nhưng cho phép ID trùng giữa tenant cùng issuer | Protocol có thể phân giải nhầm client | Dùng client ID toàn cục hoặc issuer/repository resolver tách biệt |
| Ghi Registered Client và ownership ở hai transaction | Có client mồ côi hoặc ownership sai | Dùng một transaction và constraint |
| Cache key thiếu issuer/tenant | Dữ liệu tenant này trả cho tenant khác | Thiết kế cache key theo ranh giới định danh |
| Chỉ test controller với mock repository | Bỏ sót lỗi query, constraint và transaction | Integration test với database thật của môi trường kiểm thử |
| Trả client secret trong response | Credential bị lộ qua API/log | Chỉ hiển thị một lần khi tạo; không trả lại ở GET/list |
| Không test luồng OAuth | API quản trị đúng nhưng token endpoint phân giải sai client | Test authorization, token, consent và resource access xuyên tenant |

## Kết luận

Kiểm thử tenant isolation cần chứng minh một actor chỉ đọc và thay đổi đúng đối tượng trong phạm vi được cấp. Hãy kết hợp role authorization với tenant ownership, bảo vệ cả API quản trị và các luồng OAuth sử dụng `RegisteredClient`, rồi kiểm tra database, cache, audit và background job để tìm đường rò dữ liệu. Với một issuer dùng chung, `client_id` cần duy nhất theo issuer vì repository chuẩn tra cứu theo client ID; nếu cần định danh trùng giữa tenant, phải thiết kế phân vùng issuer hoặc cơ chế phân giải riêng xuyên suốt giao thức. Một bộ kiểm thử tốt xác nhận cả request bị từ chối lẫn việc không có dữ liệu hay side effect nào vượt ranh giới tenant.
