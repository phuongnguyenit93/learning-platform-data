# Authorization theo tenant

Một nền tảng SaaS phục vụ hai doanh nghiệp **Anpha** và **Beta**. Minh là quản trị viên tại Anpha nhưng chỉ có quyền xem dữ liệu ở Beta. Minh đăng nhập thành công, nhận access token hợp lệ có scope `orders:read` rồi gọi `GET /tenants/beta/orders/42`. Có nên trả đơn hàng 42 không?

**Chưa đủ cơ sở để cho phép.** API phải chứng minh ba điều: token thật sự hợp lệ và dành cho API; Minh có quyền đọc đơn **trong tenant Beta**; đơn 42 thuộc Beta và Minh được xem đúng đơn đó. Việc là admin tại Anpha hoặc có scope đọc đơn không trao quyền truy cập mọi dữ liệu của Beta.

Bài thuộc phần **Authorization** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là nối mô hình tin cậy và vòng đời token JWT/opaque, access/refresh token trong OAuth 2.0/OIDC với **ranh giới dữ liệu và quyền của mỗi tenant**. Chúng ta sẽ xét phát hành, kiểm tra `iss`/`aud`/`scope`, chọn tenant, kiểm membership, cô lập dữ liệu, thu hồi quyền và phòng chống token bị đánh cắp/phát lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt user, client/service principal, tenant, membership, role theo tenant, OAuth scope và quyền đối với tài nguyên.
- Mô tả cách ràng buộc tenant context với access token và cách API kiểm tenant của URL, token và bản ghi.
- Thiết kế authorization cho người dùng thuộc nhiều tenant, đổi tenant, API Gateway và service-to-service.
- Chặn cross-tenant access, IDOR/BOLA ngay cả khi token có chữ ký và scope hợp lệ.
- Kiểm thử các đường rò qua truy vấn, cache, search, background job, file, queue và vòng đời quyền.

## 2. Các khái niệm nền tảng

**Tenant** là ranh giới cô lập logic/quản trị của một khách hàng, tổ chức hoặc đơn vị nghiệp vụ. Nó có thể dùng chung ứng dụng và database với tenant khác, hoặc có schema/database riêng. Cách lưu dữ liệu khác nhau nhưng **mỗi request đều phải được kiểm quyền theo tenant**.

| Khái niệm | Ví dụ | Điều cần nhớ |
|---|---|---|
| **Subject / principal** | `user-742`, `service-importer` | Chủ thể thực hiện hành động; có thể là người dùng hoặc dịch vụ. |
| **Tenant** | `tenant-anpha`, `tenant-beta` | Phạm vi cô lập dữ liệu/quyền. |
| **Membership** | `(user-742, tenant-beta)` | Quan hệ của chủ thể với tenant, có trạng thái và quyền riêng. |
| **Tenant role** | `admin` tại Anpha, `viewer` tại Beta | Role phải gắn với tenant, không lan sang tenant khác. |
| **Permission / policy** | `orders.read`, `orders.cancel` | Quy tắc cụ thể để được làm một thao tác. |
| **OAuth scope** | `orders:read` | Phạm vi được Authorization Server cấp cho token; chưa chứng minh quyền trong từng tenant. |
| **Audience (`aud`)** | `orders-api` | Resource Server được nhận access token; không đồng nghĩa tenant. |
| **Issuer (`iss`)** | `https://login.example.com` | Nguồn phát hành token được API cấu hình để tin. |
| **Active tenant** | `tenant-beta` | Tenant đang được yêu cầu/thực thi theo ngữ cảnh đáng tin cậy. |
| **Resource tenant** | `order-42.tenant_id = tenant-beta` | Tenant thực sự sở hữu dữ liệu. |

Ví dụ dữ liệu:

~~~text
user-742:
  membership tenant-anpha: admin, active
  membership tenant-beta:  viewer, active
  membership tenant-gamma: none

orders:
  order-42:  tenant-beta
  order-93:  tenant-anpha
~~~

Nếu code lưu `user-742 -> admin` rồi áp dụng role này cho mọi tenant thì đã xóa bỏ ranh giới quan trọng. Mối quan hệ đúng là **`(principal, tenant) -> role/permissions`**.

### 2.1. Authentication, token validation và authorization khác nhau

- **Authentication** trả lời “đây là ai?” qua mật khẩu, MFA, passkey hoặc cơ chế xác thực thích hợp.
- **Token validation** trả lời “token có do issuer được tin phát hành, còn hiệu lực và dành cho API này không?”.
- **Authorization theo tenant** trả lời “chủ thể có được thao tác trên tài nguyên này **ở tenant mục tiêu** hay không?”.

MFA mạnh không cho phép bỏ qua tenant policy. JWT hợp lệ không tự bảo đảm người dùng có quyền với mọi đơn hàng. Token dành cho API A không thể dùng tại API B chỉ vì cả hai dùng chung Authorization Server.

## 3. Bất biến bảo mật khi cấp quyền theo tenant

Với mô hình **token gắn một active tenant**, quyết định cho phép có thể mô tả:

~~~text
ALLOW =
    valid_access_token
    AND intended_for_this_resource_server
    AND request_tenant == trusted_token_tenant
    AND principal_is_active_in_tenant
    AND scope_allows_action
    AND tenant_policy_allows_action
    AND resource.tenant_id == trusted_token_tenant
    AND resource_level_policy_allows
    AND business_and_risk_checks_pass
~~~

Không phải mọi hệ thống bắt buộc dùng token gắn một active tenant. Một số hệ thống dùng access token chỉ định danh principal, rồi tra membership theo tenant của request. Với mô hình đó, thay phép so sánh `request_tenant == token_tenant` bằng **phép kiểm có căn cứ rằng principal được phép làm hành động tại target tenant**. Điều bất biến không đổi là **resource tenant phải trùng tenant đã được cấp quyền**, và quyền tại tenant A không mở rộng sang B.

Hai sai lầm thường gặp:

1. Chỉ kiểm `scope: orders:read` mà không tra quyền tại tenant.
2. Chỉ kiểm membership tenant mà không kiểm bản ghi có thuộc tenant đó hoặc có nằm trong phạm vi quyền của người dùng hay không.

Một người có thể là member tenant Beta nhưng không được đọc đơn của team khác trong Beta. Đây là lý do **resource-level authorization** vẫn cần thiết.

## 4. Tenant của request đến từ đâu?

| Nguồn | Ví dụ | Mức tin cậy |
|---|---|---|
| URL path/query | `/tenants/tenant-beta/orders` | Client có thể thay đổi; chỉ là tenant *được yêu cầu*. |
| Subdomain | `beta.example.com` | Có ích để định tuyến, chưa tự chứng minh quyền. |
| Request header | `X-Tenant-Id: tenant-beta` | Không đáng tin nếu do client tự gửi. |
| Request body | `{"tenantId":"tenant-beta"}` | Không đáng tin trước khi kiểm quyền. |
| Claim token đã xác minh | `"tenant_id":"tenant-beta"` | Có thể tin theo hợp đồng với issuer và chính sách freshness. |
| Introspection đáng tin cậy | `active=true` và metadata tenant | Có thể dùng khi AS công bố và Resource Server kiểm đúng. |
| Membership/permission backend | Bảng `user_tenant_memberships` hoặc PDP | Nguồn kiểm quyền hiện tại khi được bảo vệ phù hợp. |
| `tenant_id` trong database | `orders.tenant_id` | Căn cứ xác định bản ghi thuộc tenant nào. |

**Không bao giờ lấy tenant ID do client gửi làm bằng chứng cấp quyền.** Backend phải đối chiếu tenant được yêu cầu với ngữ cảnh đã được xác minh và phép kiểm quyền.

### 4.1. Token gắn một active tenant

Authorization Server (AS) có thể cấp token sau khi người dùng chọn tenant Beta và AS đã xác thực membership tại Beta. Access token có `tenant_id=tenant-beta`. Khi người dùng gọi `/tenants/tenant-anpha/...` với token Beta, API từ chối. Nếu muốn đổi sang Anpha, client dùng cơ chế được AS hỗ trợ để lấy token/ngữ cảnh Anpha sau khi AS kiểm quyền.

Ưu điểm: dễ phát hiện mismatch, scope và role có thể thu hẹp cho một tenant, giảm khả năng vô tình dùng quyền tenant khác. Hạn chế: thêm công việc lúc chuyển tenant; claims có thể lỗi thời khi membership/role bị thu hồi.

### 4.2. Token dùng cho nhiều tenant hoặc không có tenant claim

Một số thiết kế đưa danh sách tenant vào token, số khác chỉ phát token định danh principal và để API tra membership. Trong trường hợp này, API phải xác định target tenant một cách rõ ràng từ request/resource, kiểm membership và **role của principal tại target tenant**. Không được suy ra quyền từ role của tenant đang mở trên giao diện hoặc role nằm ngoài tenant context.

Danh sách membership trong JWT có thể trở nên cũ. Hệ thống nhiều quyền nhạy cảm nên cân nhắc tra trạng thái hiện tại, token TTL ngắn hoặc cơ chế thu hồi.

### 4.3. Xác định tenant mục tiêu

Với `GET /tenants/{tenantId}/orders/{id}`, path nói tenant đang được yêu cầu. Với `GET /orders/{id}`, backend phải dùng tenant context đã kiểm hoặc tìm tenant sở hữu resource theo cách đáng tin cậy rồi kiểm membership. Không được đặt tenant theo body từ client để bỏ qua tenant thực sự của bản ghi.

## 5. JWT access token mang tenant context

AS có thể phát hành JWT access token minh họa sau:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "tenant_id": "tenant-beta",
  "tenant_roles": ["viewer"],
  "scope": "orders:read",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000,
  "jti": "at-beta-52a8"
}
~~~

`tenant_id` và `tenant_roles` là **claim tùy biến trong hợp đồng AS–Resource Server**, không phải claim OAuth/OIDC có ngữ nghĩa bắt buộc ở mọi hệ thống. Số lượng và tên các claim còn lại tùy hồ sơ JWT mà issuer sử dụng. Không suy đoán cấu trúc token bằng cách tách chuỗi hoặc giải mã Base64URL mà chưa kiểm mật mã.

API cần xác minh:

1. Đây là **access token** đúng hồ sơ được Resource Server chấp nhận; không dùng ID token hoặc refresh token như access token.
2. `iss` thuộc tập issuer đáng tin; khóa JWKS/thuật toán xác minh được ràng buộc đúng issuer, không tùy ý tải khóa từ URL trong header token.
3. Chữ ký hợp lệ, `aud` chứa `orders-api`, `exp` và `nbf` hợp lệ; kiểm các claim bắt buộc theo hồ sơ token.
4. `tenant_id` đúng ngữ nghĩa hợp đồng, khớp tenant mà request cần truy cập theo mô hình single-active-tenant.
5. Scope, role/policy tenant và quyền trên resource đều cho phép hành động; cân nhắc quyền đã bị thu hồi.

**Chữ ký JWT bảo đảm tính toàn vẹn, không mã hóa payload.** Không đưa dữ liệu nội bộ nhạy cảm hoặc danh sách quyền quá rộng vào token nếu không cần thiết.

### 5.1. Phân biệt tenant và audience

Giả sử API đơn hàng và API thanh toán cùng phục vụ tenant Beta. Access token có `aud=payments-api` và `tenant_id=tenant-beta` không thể được dùng để gọi `orders-api`: **đúng tenant nhưng sai audience**.

Ngược lại, token `aud=orders-api` và `tenant_id=tenant-anpha` không được dùng cho đơn hàng Beta: **đúng audience nhưng sai tenant**.

Chỉ khi cả hai phù hợp, API mới tiếp tục kiểm scope, membership và quyền bản ghi.

### 5.2. Opaque token và introspection

Access token có thể là chuỗi opaque. Resource Server dùng cơ chế tra cứu hoặc OAuth 2.0 Token Introspection với AS đáng tin cậy:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "scope": "orders:read",
  "tenant_id": "tenant-beta",
  "exp": 1893456000
}
~~~

Phản hồi trên là ví dụ về metadata đã được hệ thống thống nhất. Ngoài `active`, các trường phụ thuộc AS. Resource Server phải gọi endpoint qua TLS, xác thực đúng kênh/đối tượng gọi khi yêu cầu, kiểm `active` và metadata trước khi cấp quyền.

**`active=true` không phải quyền truy cập mọi tenant**. Hệ thống vẫn cần tenant, scope và resource-level checks. Cache introspection giúp giảm độ trễ nhưng có thể khiến quyền bị thu hồi vẫn được chấp nhận trong cửa sổ cache.

### 5.3. Vì sao ID token và refresh token không dùng ở API?

- **ID token** của OIDC mô tả kết quả đăng nhập, thường có `aud` là `client_id`, ví dụ `shop-web`. Nó dành cho OIDC Client và không là bằng chứng ủy quyền để gọi `orders-api`.
- **Refresh token** dành cho client gửi đến **token endpoint của AS** nhằm xin access token mới; không gửi cho API nghiệp vụ.
- Chỉ **access token dành cho đúng Resource Server** mới được API xét để cấp quyền, và còn phải kiểm tenant.

## 6. Luồng end-to-end: từ đăng nhập đến truy vấn dữ liệu

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as SaaS Client
    participant AS as Authorization Server
    participant API as Orders API
    participant P as Membership/Policy
    participant DB as Orders DB
    U->>C: Đăng nhập và chọn tenant Beta
    C->>AS: Authorization Code + PKCE, yêu cầu tenant context
    AS->>AS: Xác thực, kiểm membership Beta
    AS-->>C: Authorization code
    C->>AS: Đổi code + PKCE verifier
    AS-->>C: Access token cho orders-api, tenant-beta
    C->>API: GET /tenants/tenant-beta/orders/42 + Bearer
    API->>API: Xác minh token, iss, aud, exp, scope
    API->>API: So tenant path với context đã xác minh
    API->>P: user-742 được đọc đơn ở Beta?
    P-->>API: Allow/Deny
    API->>DB: Tìm order WHERE tenant_id=Beta AND id=42
    DB-->>API: Bản ghi hoặc không có kết quả
    API->>API: Kiểm quyền trên đơn hàng cụ thể
    API-->>C: 200, 403 hoặc 404 theo kết quả
~~~

**Lưu ý:** OAuth 2.0 không định nghĩa một tham số `tenant` chung bắt buộc cho mọi Authorization Server. Cơ chế chọn tenant khi authorize và phát token là hợp đồng cụ thể của hệ thống; client yêu cầu ngữ cảnh, AS quyết định có cấp hay không.

### 6.1. Ba phép so sánh cần giữ đúng

Trong mô hình active tenant, API cần bảo đảm:

~~~text
request.tenant_id == verified_access_token.tenant_id
resource.tenant_id == verified_access_token.tenant_id
policy.can(principal, verified_access_token.tenant_id, action, resource)
~~~

Token hợp lệ với đúng issuer và audience chỉ là điều kiện đầu. Nếu resource thuộc tenant khác, request phải thất bại dù ID được đoán đúng hoặc người dùng là admin ở tenant hiện hành.

## 7. Policy theo tenant: RBAC, ABAC và ReBAC

| Mô hình | Áp dụng tại tenant | Ví dụ |
|---|---|---|
| **RBAC** | Vai trò gắn với membership trong tenant | Minh là `admin` tại Anpha nhưng `viewer` tại Beta |
| **ABAC** | Kiểm thuộc tính principal, resource, tenant và ngữ cảnh | Chỉ sửa đơn thuộc department người dùng, trước trạng thái khóa |
| **ReBAC** | Kiểm quan hệ user–team–project–resource | Chỉ nhóm phụ trách đơn mới được xem thông tin khách hàng |

Scope `orders:write` có thể được AS cấp cho client, nhưng nếu Minh là `viewer` tại Beta thì API **không được** cho phép xóa đơn ở Beta. Ngược lại, Minh có role admin ở Anpha mà token thiếu scope cho endpoint thì cũng không được gọi endpoint đó.

### 7.1. Policy matrix minh họa

| Principal / tenant | Scope token | Role tại tenant | Hành động | Kết quả |
|---|---|---|---|---|
| Minh / Anpha | `orders:read` | admin | Đọc đơn Anpha | Có thể cho phép nếu đúng ngữ cảnh và bản ghi |
| Minh / Beta | `orders:read` | viewer | Đọc đơn Beta | Có thể cho phép sau kiểm ownership/team |
| Minh / Beta | `orders:write` | viewer | Xóa đơn Beta | Từ chối vì permission tenant không đủ |
| Minh / Gamma | `orders:read` | Không là member | Đọc đơn Gamma | Từ chối |
| Service sao lưu / Beta | `backup:run` | Service permission Beta | Sao lưu Beta | Chỉ cho phép nếu policy service binding phù hợp |
| Service sao lưu / Gamma | `backup:run` | Không có quyền Gamma | Sao lưu Gamma | Từ chối |

Nếu policy engine không sẵn sàng, tenant context thiếu hoặc membership không rõ, mặc định **deny** thay vì cấp quyền rộng hơn.

## 8. Thuật toán kiểm tra ở Resource Server

Pseudocode minh họa cho mô hình token gắn **một active tenant**:

~~~text
function getOrder(request, tenantPath, orderId):
    bearer = readBearerToken(request.Authorization)
    principal = verifyAccessToken(
        bearer,
        trustedIssuer = "https://login.example.com",
        audience = "orders-api",
        allowedKeysAndAlgorithms = configuredPolicy
    )
    if principal.invalid:
        return 401

    activeTenant = principal.trustedClaims.tenant_id
    if activeTenant is missing OR activeTenant != tenantPath:
        return 403

    if "orders:read" not in principal.scopes:
        return 403

    if not membership.isActive(principal.subject, activeTenant):
        return 403

    if not policy.can(principal.subject, activeTenant, "orders.read"):
        return 403

    order = repository.findByTenantAndId(activeTenant, orderId)
    if order is missing:
        return 404

    if not policy.canReadOrder(principal.subject, activeTenant, order):
        return 403

    return 200, serializeAllowedFields(order)
~~~

`verifyAccessToken` phải dùng thư viện JWT/introspection đã cấu hình chuẩn, không tự viết mã mật mã. Pseudocode chưa bao gồm xử lý lỗi, audit, rate limit và tất cả chính sách ứng dụng.

### 8.1. Ví dụ Spring Security

Giả sử ứng dụng đã cấu hình OAuth2 Resource Server để xác minh **issuer, audience, thuật toán và JWT claims**. Ví dụ controller ở mức minh họa:

~~~java
@GetMapping("/tenants/{tenantId}/orders/{orderId}")
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderDto readOrder(
        @PathVariable String tenantId,
        @PathVariable UUID orderId,
        @AuthenticationPrincipal Jwt jwt) {

    String tokenTenant = jwt.getClaimAsString("tenant_id");
    if (tokenTenant == null || !tokenTenant.equals(tenantId)) {
        throw new AccessDeniedException("Invalid tenant context");
    }

    String subject = jwt.getSubject();
    if (!tenantPolicy.activeMemberCanReadOrders(subject, tenantId)) {
        throw new AccessDeniedException("Not allowed in tenant");
    }

    Order order = orderRepository
        .findByTenantIdAndId(tenantId, orderId)
        .orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND));

    if (!tenantPolicy.canReadOrder(subject, tenantId, order)) {
        throw new AccessDeniedException("Not allowed for this order");
    }

    return orderMapper.toDto(order);
}
~~~

**Điều phải kiểm trong ứng dụng thật:**

1. `@AuthenticationPrincipal Jwt` chỉ an toàn khi qua filter/decoder xác minh token; không tự chuyển payload client thành principal.
2. `hasAuthority('SCOPE_orders:read')` kiểm scope, **không kiểm tenant**; do đó cần policy tenant trong service.
3. `findByTenantIdAndId` phải thật sự lọc cả tenant và ID; kiểm định nghĩa repository, constraint/index.
4. Chuyển logic kiểm quyền dùng chung vào domain/policy service để mọi endpoint áp dụng nhất quán.
5. Với opaque token, lấy ngữ cảnh từ principal/introspection đã tin, không giả định luôn có `Jwt`.

### 8.2. Bảo vệ tại SQL

~~~sql
SELECT id, tenant_id, owner_id, status
FROM orders
WHERE tenant_id = :authorized_tenant_id
  AND id = :order_id;
~~~

Ngay cả lệnh ghi cũng phải giữ tenant boundary:

~~~sql
UPDATE orders
SET status = :new_status
WHERE tenant_id = :authorized_tenant_id
  AND id = :order_id
  AND status = :expected_status;
~~~

Tham số `authorized_tenant_id` phải xuất phát từ ngữ cảnh đã được **xác minh và kiểm quyền**. Nếu client gửi `tenantId` trong body khi tạo đơn, backend phải đối chiếu hoặc bỏ giá trị đó theo hợp đồng; không tạo dữ liệu tùy ý trong tenant khác.

## 9. Cô lập dữ liệu: database, join, RLS

### 9.1. Shared database/shared schema

Các bảng dữ liệu của tenant thường có `tenant_id`. Mọi truy vấn, lọc, phân trang, aggregate, join, update, delete, export phải giữ tenant filter.

~~~sql
SELECT o.id, i.sku
FROM orders o
JOIN order_items i
  ON i.tenant_id = o.tenant_id
 AND i.order_id = o.id
WHERE o.tenant_id = :authorized_tenant_id;
~~~

Một join chỉ bằng `order_id` có thể trộn dữ liệu nếu ID không duy nhất hoặc dữ liệu import không nhất quán. Khóa/index/foreign key ghép `(tenant_id, id)` giúp củng cố ranh giới.

**Row-Level Security (RLS)** của database có thể là lớp bảo vệ bổ sung. Nhưng ứng dụng phải đặt đúng tenant context trên transaction/kết nối, tránh rò context giữa requests trong connection pool; tài khoản database không được vô tình bypass policy. RLS không thay quyền nghiệp vụ trên từng bản ghi.

### 9.2. Mỗi tenant một schema/database

Dù cô lập vật lý rõ hơn, backend vẫn cần **kiểm quyền trước khi chọn connection/schema/database**. Nếu client tự chọn schema, có thể xảy ra cross-tenant access dù dữ liệu được lưu riêng.

### 9.3. Các nơi tenant context dễ bị mất

- **Cache:** key `order:{id}` hoặc `reports:last` có thể vô tình trả kết quả tenant khác. Dùng key có tenant và, khi cần, principal/quyền; định nghĩa invalidate theo tenant.
- **Full-text/vector search:** bắt buộc filter tenant phía server và kiểm quyền trên kết quả.
- **File/object storage:** signed URL, đường dẫn và quyền download phải được phát sau kiểm resource ownership; cân nhắc thời hạn URL.
- **Report/export:** background job phải mang tenant context đáng tin cậy và tái kiểm khi chạy nếu chính sách yêu cầu.
- **Queue/event:** consumer không tin tùy ý `tenant_id` trong message từ nguồn không được xác thực; xác định service/producer được phép tác động tenant nào.
- **Batch & pagination:** mọi phần tử và count/aggregate phải giới hạn tenant; không rò số lượng hoặc metadata khách hàng khác.
- **Audit & logging:** ghi tenant đã được xác minh, quyết định quyền và correlation ID; không ghi nguyên access/refresh token.
- **Idempotency:** khóa chống gửi lặp nên gắn tenant và operation/principal phù hợp để không xung đột xuyên tenant.

## 10. Đổi tenant và quyền thay đổi theo thời gian

Một người có thể ở Anpha và Beta nhưng đang dùng access token `tenant_id=tenant-anpha`. Click “Chuyển sang Beta” trên UI hoặc sửa `X-Tenant-Id` không nâng quyền. Với thiết kế single-active-tenant, client cần lấy token/context cho Beta qua cơ chế đã được AS phê duyệt sau khi AS kiểm membership.

Nếu thiết kế token không gắn tenant và tra quyền theo từng request, client có thể thay target tenant ở URL nhưng API vẫn **phải kiểm membership/role tại tenant mới**. Khi đổi tenant, client cần phân tách cache, state giao diện và tác vụ đang chạy để không đưa dữ liệu tenant cũ vào tenant mới.

### 10.1. Role bị thu hồi sau khi token được cấp

Ví dụ admin xóa membership Beta của Minh lúc 10:05; JWT của Minh còn `exp` đến 10:15 và claim role cũ. Nếu API chỉ kiểm chữ ký cục bộ, nó có thể vẫn chấp nhận quyền cũ trong cửa sổ này.

Các lựa chọn dựa trên rủi ro:

1. Access token **TTL ngắn** để giới hạn độ trễ quyền.
2. API tra membership/role hiện tại hoặc dùng token/policy version tại các hành động nhạy cảm.
3. Opaque token + introspection, denylist hoặc cơ chế thu hồi có trạng thái; chú ý cache.
4. Thu hồi refresh token/phiên để chặn xin token tiếp, nhưng **không mặc định** mọi access JWT đã cấp lập tức vô hiệu.
5. Đồng bộ sự kiện thay đổi membership để invalidate cache, có cơ chế xử lý khi event chậm/thất lạc.

Thời điểm **`iat` của access token mới** không tự chứng minh quyền tenant được kiểm lại trong refresh grant, trừ khi AS thực sự có chính sách đó.

## 11. Service-to-service và quản trị xuyên tenant

Với OAuth 2.0 `client_credentials`, principal thường là **ứng dụng/dịch vụ**, không phải end user. Dịch vụ sao lưu được gọi nội bộ không đồng nghĩa có quyền với toàn bộ tenant.

~~~text
principal = verifyAccessToken(token, audience="backup-api")
tenant = resolveAndValidateTargetTenant(job)

if "backup:run" not in principal.scopes:
    deny
if not servicePolicy.canBackup(principal.clientId, tenant):
    deny

runBackupRestrictedTo(tenant)
~~~

Khi service A gọi service B, token phải có audience thích hợp cho B; không chuyển tiếp tùy tiện access token dành cho API khác. Nếu thực hiện thay mặt người dùng, có thể dùng cơ chế ủy quyền/token exchange mà AS hỗ trợ để bảo toàn subject, actor/client, audience, scope và tenant.

Quyền **platform-admin** hoặc thao tác nhiều tenant phải có cơ chế riêng: principal/permission chuyên biệt, xác thực đủ mạnh, lý do truy cập, giới hạn thời gian/phạm vi và audit. Không diễn giải `tenant_admin` của một tenant thành quyền quản trị toàn hệ thống.

### 11.1. API Gateway và forwarded identity

Gateway có thể xác minh access token và truyền ngữ cảnh principal/tenant cho microservices, nhưng phía sau chỉ nên tin header từ **gateway đã được xác thực**. Phải loại bỏ header danh tính do client ngoài tự gửi, bảo vệ kết nối nội bộ và duy trì resource policy tại service sở hữu dữ liệu. `X-User-Id` hay `X-Tenant-Id` từ internet không phải bằng chứng đáng tin cậy.

## 12. Các lỗi thường gặp

| Lỗi | Ví dụ | Hệ quả và cách sửa |
|---|---|---|
| **BOLA/IDOR** | Đổi `orderId` sang bản ghi tenant khác | Truy vấn bằng `tenant_id + id`, kiểm resource ownership |
| **Tin tenant header/path** | Tự gửi `X-Tenant-Id: tenant-beta` | Luôn kiểm context token/membership |
| **Role toàn cục** | Minh admin Anpha được xóa dữ liệu Beta | Gắn role với `(principal, tenant)` |
| **Chỉ kiểm scope** | `orders:write` để sửa bất kỳ đơn nào | Thêm tenant policy và resource policy |
| **Bỏ audience** | Token dành cho billing gọi orders | Buộc `aud` đúng API |
| **ID token dùng tại API** | ID token đăng nhập được chấp nhận như access | Chỉ nhận access token đúng mục đích |
| **Tin JWT payload chưa xác minh** | Client sửa `tenant_id` | Xác minh chữ ký, issuer, thuật toán và claims |
| **Join không filter tenant** | Item của tenant khác lọt vào đơn | Join theo `tenant_id` và key chính |
| **Cache không phân tenant** | Key `orders:list` cho mọi tenant | Phân key/permission theo tenant |
| **Job mất context** | Export toàn bộ dữ liệu trên cron | Mang tenant context xuyên pipeline và kiểm lại |
| **Quyền stale** | Member đã bị xóa, JWT còn hạn | TTL, refresh policy, revocation hoặc tra trạng thái |
| **Default tenant không an toàn** | Claim tenant thiếu thì chọn `main` | Fail closed; không tự fallback |
| **Wildcard admin tùy tiện** | `tenant=*` tự mở tất cả dữ liệu | Thiết kế global privilege riêng, audit |

**403 hay 404?** Với token hợp lệ nhưng không có quyền, thông thường 403. Với bản ghi thuộc tenant khác, có thể trả 404 để tránh tiết lộ sự tồn tại; chính sách phải nhất quán và không rò dữ liệu trong error, count hoặc thời gian phản hồi. Token thiếu/hết hạn/không hợp lệ thường dẫn đến 401. Nếu chỉ thiếu scope, có thể dùng `insufficient_scope` theo OAuth Bearer.

## 13. Bài thực hành tình huống

Hệ thống quản lý hóa đơn có:

~~~text
User: user-742
  tenant-anpha: billing_admin
  tenant-beta:  billing_viewer
  tenant-gamma: no membership

Access token:
  iss       = https://login.example.com
  aud       = invoices-api
  sub       = user-742
  tenant_id = tenant-beta
  scope     = invoices:read invoices:write
  exp       = còn hiệu lực

Resources:
  invoice-100: tenant-beta,  draft
  invoice-101: tenant-anpha, draft
  invoice-102: tenant-gamma, approved
~~~

Áp dụng mô hình **single-active-tenant**; `billing_viewer` chỉ được đọc hóa đơn trong tenant của mình.

| Request | Kết luận | Lý do |
|---|---|---|
| `GET /tenants/tenant-beta/invoices/100` | Có thể cho phép | Token cho Beta, role đọc và resource thuộc Beta; vẫn cần policy bản ghi |
| `PATCH /tenants/tenant-beta/invoices/100` | Từ chối | Role viewer không đủ dù token có scope ghi |
| `GET /tenants/tenant-anpha/invoices/101` | Từ chối với token hiện tại | Token đang ở Beta; cần context/token Anpha hợp lệ |
| `GET /tenants/tenant-beta/invoices/101` | Không trả dữ liệu | Invoice 101 thuộc Anpha |
| `GET /tenants/tenant-gamma/invoices/102` | Từ chối | Không membership Gamma, sai tenant token |
| `POST /tenants/tenant-beta/invoices` body có `tenant_id=tenant-gamma` | Từ chối hoặc bỏ giá trị body theo hợp đồng | Tenant được gán từ context đã xác minh |

### 13.1. Ma trận kiểm thử âm tính

1. Token đúng chữ ký nhưng **sai issuer**, sai audience, hết hạn, tenant claim thiếu.
2. Payload `tenant_id`/role bị sửa mà không ký lại: phải từ chối.
3. Token Anpha gọi path Beta hoặc giả header `X-Tenant-Id: beta`.
4. User admin Anpha, viewer Beta: không được dùng quyền admin của Anpha ở Beta.
5. ID bản ghi Anpha dùng trong endpoint Beta: không rò dữ liệu qua result/error/cache.
6. Scope đủ nhưng user không còn membership Beta hoặc tenant Beta bị khóa.
7. Service token dùng `client_credentials` bị gán nhầm quyền của user.
8. Batch/search/export/report trả lẫn bản ghi và số lượng của tenant khác.
9. Cache được ghi từ tenant Anpha phải không được đọc từ Beta với key tương đương.
10. Token bị thu hồi, refresh token rotation và quyền vừa thay đổi phải tuân thủ cửa sổ hiệu lực đã thiết kế.
11. Background job bắt đầu ở Beta nhưng tenant bị khóa trước khi job chạy.
12. API Gateway nhận header identity giả từ internet: downstream không được tin.

### 13.2. Câu hỏi tự kiểm tra

**Câu 1.** JWT đúng issuer, audience và scope; claim `tenant_id=tenant-anpha`. Request tới `/tenants/tenant-beta` có được phép không?  
**Không** trong mô hình active tenant. Phải cấp/kiểm ngữ cảnh Beta đúng chính sách.

**Câu 2.** Minh là member Beta và có scope đọc đơn. Có thể bỏ lọc tenant trong SQL nếu controller đã kiểm membership không?  
**Không.** Dữ liệu vẫn phải được lấy theo tenant đã được cấp quyền; membership không xác nhận mọi `orderId` đều thuộc Beta.

**Câu 3.** Xóa refresh token của Minh sau khi rời Beta có lập tức vô hiệu hóa mọi access JWT đã cấp không?  
**Không chắc.** Nếu Resource Server tự xác minh JWT mà không dùng revocation/state bổ sung, token có thể được chấp nhận tới `exp`.

**Câu 4.** Khi API cho service nội bộ quyền backup Beta, có thể mặc nhiên dùng token đó để backup Gamma?  
**Không.** Service principal cũng cần quyền theo tenant; việc “nội bộ” không phải permission.

## 14. Thu hồi, chống phát lại và vòng đời token theo tenant

Bearer token bị đánh cắp có thể bị kẻ khác gửi lại trong thời gian token còn hiệu lực. Bản thân chữ ký JWT chỉ xác nhận issuer/tính toàn vẹn; **không chứng minh request hiện tại đến từ người vừa đăng nhập**. Để giảm rủi ro:

- **Scope và audience tối thiểu**, access token TTL ngắn, ưu tiên giới hạn tenant context khi phù hợp.
- Bảo vệ token bằng HTTPS, lưu trữ an toàn theo loại client, không ghi token vào URL/log/analytics.
- Refresh token rotation hoặc sender-constraining theo chính sách AS; không bao giờ dùng refresh token gọi API nghiệp vụ.
- Khi membership/role/tenant thay đổi, áp dụng revocation/introspection, tra trạng thái hiện tại hoặc cơ chế vô hiệu hóa cache nếu yêu cầu thu hồi sớm.
- Cân nhắc DPoP hoặc mTLS sender-constrained access token, **và phải thực sự kiểm** bằng chứng sở hữu khóa, request binding và chống replay phù hợp giao thức.
- Với công việc kéo dài hoặc chuyển tenant giữa chừng, bảo đảm tenant context và chính sách được kiểm ở thời điểm thực thi cần thiết; tránh race condition giữa kiểm quyền và ghi dữ liệu.

Cơ chế sender-constrained token giúp giảm khả năng dùng lại token chỉ bị sao chép; nó **không thay** tenant policy và resource ownership. Quyền toàn hệ thống vẫn phải được đánh giá ở mỗi điểm truy cập dữ liệu.

## 15. Checklist triển khai

- [ ] Đã định nghĩa tenant, membership, role và permission theo **`(principal, tenant)`**.
- [ ] API chỉ chấp nhận access token đúng issuer, audience, chữ ký/thuật toán hoặc introspection, thời hạn, loại token.
- [ ] Tenant context được xác minh; URL/header/body từ client không được dùng làm bằng chứng quyền.
- [ ] Mỗi request kiểm scope, membership, role/permission và chính sách trên tài nguyên cụ thể.
- [ ] Mọi query, join, update/delete, batch, aggregate, report và export đều giữ tenant filter.
- [ ] Cache, search index, object storage, queue, background job và audit không trộn ngữ cảnh tenant.
- [ ] Tenant switch có cơ chế cập nhật context/token và tách dữ liệu giao diện phù hợp.
- [ ] Service-to-service có audience riêng và permission theo tenant; global admin là quyền riêng được audit.
- [ ] TTL, thu hồi, membership thay đổi và cache invalidation có chính sách rõ ràng.
- [ ] Test cross-tenant IDOR/BOLA, sai issuer/audience, sai scope, thiếu tenant, stale role và replay.
- [ ] Khi policy hoặc tenant context không hợp lệ/không sẵn sàng, hệ thống **fail closed**.

**Ghi nhớ:** xác minh token chỉ chứng minh nó đáng tin và dành cho API; `scope` giới hạn loại hành động; **authorization theo tenant** đòi hỏi chủ thể thực sự có quyền **trong tenant đang xét** và tài nguyên thực sự **thuộc tenant đó**. Một access token hợp lệ không bao giờ là giấy phép truy cập dữ liệu của mọi khách hàng.

### Tài liệu chuẩn để tra cứu

- **RFC 6749** — The OAuth 2.0 Authorization Framework.
- **RFC 6750** — OAuth 2.0 Bearer Token Usage.
- **RFC 7519** — JSON Web Token (JWT), các claims `iss`, `aud`, `exp` và `sub`.
- **RFC 7662** — OAuth 2.0 Token Introspection.
- **RFC 9068** — JWT Profile for OAuth 2.0 Access Tokens.
- **RFC 8693** — OAuth 2.0 Token Exchange.
- **RFC 9700** — Best Current Practice for OAuth 2.0 Security.
- **OWASP API Security Top 10** — Broken Object Level Authorization và các lỗi phân quyền API.
- **OWASP Authorization Cheat Sheet** — deny by default, kiểm quyền trên mỗi request và object-level access.
