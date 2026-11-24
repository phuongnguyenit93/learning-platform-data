# Kiểm tra scope và authority

## Mục tiêu học tập

Trong chương **Token validation** của học phần bảo mật token, kiểm tra access token không dừng ở việc xác minh chữ ký JWT hoặc tra cứu trạng thái opaque token. Sau khi có một token **đáng tin và đúng mục đích**, Resource Server (API) còn phải quyết định: **token được cấp phạm vi nào, principal có authority nào, và yêu cầu cụ thể có vượt quyền hay không?**

Sau bài học, bạn có thể:

1. Phân biệt **OAuth scope**, **authority**, **role**, **permission** và quyền truy cập ở **cấp đối tượng**.
2. Trình bày đúng thứ tự **token validation → tạo principal/authorities → kiểm tra action → phân quyền resource**.
3. Giải thích mapping scope thành authority trong ứng dụng Java/Spring Security, đặc biệt tiền tố `SCOPE_` và `ROLE_`.
4. Xử lý JWT access token và opaque access token mà không tin claims chưa xác minh, không nhầm ID/refresh token với access token.
5. Tránh lỗi **scope confusion**, **role escalation**, **Broken Object Level Authorization (BOLA/IDOR)**, truy cập chéo tenant và cấp quyền dựa vào dữ liệu client tự khai báo.
6. Thiết kế mã kiểm tra, ma trận kiểm thử và phản hồi **401/403** phù hợp, kể cả khi quyền bị thu hồi trong lúc token còn hiệu lực.

## 1. Token hợp lệ chưa có nghĩa request được phép

Một client gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <ACCESS_TOKEN_PLACEHOLDER>
~~~

Giả sử JWT access token mang các claims minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "tenant_id": "tenant-a",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

Đây chỉ là **payload minh họa**, không phải token có thể dùng thật. Resource Server phải trả lời **bốn câu hỏi khác nhau**:

| Lớp | Câu hỏi | Điều kiện ví dụ |
|---|---|---|
| **Token validation** | Bằng chứng có đáng tin, còn hiệu lực và dành cho API này không? | Issuer/chữ ký hoặc introspection đúng; `aud=orders-api`, `exp` chưa qua. |
| **Granted scope/authority** | Token/principal được phép yêu cầu loại thao tác nào? | `orders:read` được cấp và ánh xạ thành quyền đọc. |
| **Object-level authorization** | Principal được phép đọc **order 42** không? | Order thuộc cùng tenant và chủ sở hữu, hoặc có ủy quyền phù hợp. |
| **Điều kiện nghiệp vụ/ngữ cảnh** | Có hạn chế nào khác cho request này không? | Tài khoản chưa bị khóa; trạng thái/tính nhạy cảm cho phép. |

**Chữ ký đúng ≠ scope đủ ≠ quyền trên bản ghi đủ.** Nếu chỉ kiểm tra chữ ký rồi cho truy cập bất kỳ `/orders/{id}`, hệ thống có thể mắc **BOLA/IDOR**. Nếu chỉ đọc chuỗi scope từ payload chưa xác minh, attacker có thể tự tạo JSON `scope=orders:write` và tìm cách nâng quyền.

## 2. Scope và authority khác nhau ở đâu?

### OAuth scope: quyền truy cập được ủy quyền trong token

Trong OAuth 2.0, **scope** mô tả phạm vi mà client được phép yêu cầu truy cập Resource Server. Ví dụ hợp đồng của Orders API:

| Scope | Tác vụ có thể yêu cầu | Không tự bao hàm |
|---|---|---|
| `orders:read` | Đọc những đơn mà principal được phép xem. | Đọc mọi tenant hoặc sửa đơn. |
| `orders:write` | Tạo/chỉnh sửa đơn trong phạm vi policy. | Hoàn tiền hoặc đổi chủ sở hữu trái phép. |
| `orders:cancel` | Yêu cầu hủy đơn đủ điều kiện. | Hủy đơn đã giao hoặc của người khác. |
| `payments:refund` | Yêu cầu hoàn tiền tại Billing API. | Tự hợp lệ tại Orders API chỉ vì cùng issuer. |

Tên scope do Authorization Server (AS) và Resource Server (RS) thỏa thuận; không có ngữ nghĩa chung toàn Internet cho `orders:read`. Scope ở một RS cũng **không chuyển thành quyền** ở RS khác khi audience không phù hợp.

### Authority: quyền mà framework đưa vào security context

Trong Java/Spring Security, **`GrantedAuthority`** là cách framework biểu diễn một quyền đã được ánh xạ vào `Authentication`, ví dụ:

~~~text
SCOPE_orders:read
ROLE_SUPPORT
orders:read:any
~~~

Ba chuỗi trên có thể đến từ **ba nguồn/ngữ nghĩa khác nhau**:

- `SCOPE_orders:read`: thường là authority được **ánh xạ từ OAuth scope** `orders:read` theo quy ước mặc định của Spring Security Resource Server với JWT.
- `ROLE_SUPPORT`: có thể đại diện một **role nội bộ**, nếu hệ thống đã cấu hình và tin cậy nguồn của role đó.
- `orders:read:any`: có thể là **permission nghiệp vụ** do ứng dụng quản lý, không nhất thiết là claim trong token.

**Authority không phải một claim chuẩn bắt buộc của JWT.** Nó thường là **biểu diễn nội bộ** sau khi framework đã xác minh token và chạy logic chuyển đổi/tra cứu quyền.

### Role, permission và scope: bảng phân biệt

| Khái niệm | Nguồn và mục đích thường gặp | Ví dụ | Cảnh báo |
|---|---|---|---|
| **Scope** | AS cấp cho client trong một grant; RS kiểm tra. | `orders:read` | Scope không tự cho quyền đọc mọi object. |
| **Role** | Nhóm trách nhiệm theo chính sách IAM/ứng dụng. | `SUPPORT` | Role chỉ có nghĩa trong đúng tenant/domain. |
| **Permission** | Quyền thực hiện action cụ thể theo nghiệp vụ. | `orders:read:any` | Có thể cần điều kiện bổ sung về tenant. |
| **GrantedAuthority** | Chuỗi/quyền mà Spring dùng trong `Authentication`. | `SCOPE_orders:read` | Chỉ đáng tin khi mapping từ nguồn đã xác minh. |
| **Ownership/relationship** | Quan hệ giữa principal và resource. | `order.ownerId == principal.sub` | Phải xét với **bản ghi thật**, không chỉ token. |

Không có yêu cầu mọi hệ thống phải ánh xạ role thành authority, hay mọi permission phải nằm trong JWT. Quan trọng nhất là có **hợp đồng rõ giữa nguồn tin cậy, quá trình mapping và policy thực thi**.

## 3. Đúng thứ tự: xác minh token trước khi đọc scope

### Bước 1 — Xác minh token và mục đích

Với **JWT access token**, RS nên dùng thư viện bảo mật phù hợp để kiểm tra:

1. **Issuer `iss`** thuộc tập issuer được cấu hình tin cậy.
2. **Chữ ký/MAC** khớp khóa của issuer tin cậy, thuật toán nằm trong allowlist; không tin khóa hoặc URL khóa tùy ý do header token chỉ định.
3. **Audience `aud`** chứa định danh của API hiện tại và đúng profile token được chấp nhận.
4. **Thời gian `exp`, `nbf`**, giới hạn tuổi token nếu policy yêu cầu, với mức clock skew nhỏ được xác định.
5. **Loại/mục đích token**: đây là access token hợp lệ, không phải OIDC ID token hay refresh token. Với profile RFC 9068, kiểm tra các yêu cầu profile liên quan.
6. **Trạng thái/thu hồi và sender proof** nếu hệ thống đòi hỏi: token bị thu hồi hoặc bằng chứng DPoP/mTLS không hợp lệ thì từ chối.

**Giải mã Base64URL không phải xác minh chữ ký.** Một JWT đọc được `scope=admin` chưa có bất kỳ giá trị cấp quyền nào nếu chưa được xác minh.

Với **opaque access token**, RS không tự đọc “claims” bằng cách đoán hình thức chuỗi. RS có thể gọi **token introspection** (RFC 7662) qua kết nối và cơ chế xác thực tin cậy, nhận kết quả như `active`, `aud`, `scope`, `sub`, `exp`. `active: true` vẫn chưa thay thế kiểm tra **audience, phạm vi và quyền trên tài nguyên**. Nếu thiếu thuộc tính bắt buộc để áp dụng policy, phải từ chối.

### Bước 2 — Chuẩn hóa thông tin đã được xác minh

Một lớp xác minh đáng tin tạo ra đối tượng nội bộ như:

~~~text
VerifiedPrincipal:
  subjectId     = user-123
  clientId      = shop-web
  tenantId      = tenant-a
  grantedScopes = {orders:read}
  authorities   = {SCOPE_orders:read}
  tokenAudience = {orders-api}
~~~

Đây là **security context sau xác minh**, không phải dữ liệu client gửi qua query/body. `tenantId` chỉ đáng tin khi claim/nguồn membership được AS và RS chấp thuận; nhiều ứng dụng phải **đối chiếu trạng thái tenant hiện hành**.

### Bước 3 — Kiểm tra đủ scope/authority cho action

API đọc đơn có thể yêu cầu:

~~~text
requiredAuthority = "SCOPE_orders:read"
~~~

Hoặc cùng ngữ nghĩa bằng kiểm tra scope trên tập quyền đã chuẩn hóa:

~~~text
if not grantedScopes.containsExactly("orders:read"):
    deny
~~~

**So khớp chính xác**: không dùng `scopeString.contains("read")`; `reports:read`, `orders:read:any` và `orders:read` là các chuỗi khác nhau. Scope thường được biểu diễn thành một chuỗi các giá trị tách bằng dấu cách trong token/profile OAuth; phải parse đúng hợp đồng, không tự giải thích các dấu phân cách không được định nghĩa.

### Bước 4 — Kiểm tra quyền trên resource thật

Scope đọc đơn **không biết** order 42 thuộc ai. RS phải tải thuộc tính đáng tin của order và áp dụng policy:

~~~text
allow READ(order) only if:
    verified token is for orders-api
    AND granted scopes include orders:read
    AND principal.tenant == order.tenant
    AND (
        principal.subject == order.owner
        OR principal has permission orders:read:any for this tenant
    )
~~~

Nếu không đáp ứng bất kỳ điều kiện bắt buộc nào, kết quả là **DENY**. Trong hệ thống đa tenant, một role `ADMIN` trong tenant A **không** mặc định có hiệu lực ở tenant B.

## 4. Từ scope trong JWT đến `GrantedAuthority` của Spring Security

Spring Security Resource Server cung cấp cơ chế xác minh access token và tạo `Authentication`. Với cấu hình JWT thông dụng, `JwtGrantedAuthoritiesConverter` lấy scope từ claim `scope` hoặc `scp` (theo quy ước/converter được cấu hình) và tạo authority có **tiền tố `SCOPE_`**.

Ví dụ claims đã được xác minh:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read orders:cancel",
  "exp": 1893456900
}
~~~

Sau khi Resource Server đã xác minh token và chuyển đổi, có thể thu được:

~~~text
Authentication.getName():       user-123
Authentication.getAuthorities():
  SCOPE_orders:read
  SCOPE_orders:cancel
~~~

**Lưu ý:** đây là hành vi/convention thông dụng của Spring khi dùng JWT và converter mặc định; tên principal, claim scope, prefix và các authority khác **có thể khác do cấu hình**. Đừng mặc định provider nào cũng gửi claim `scope` hay mọi token chứa `roles` đều tự biến thành `ROLE_*`.

### `hasAuthority` và `hasRole` trong Spring

| Cách kiểm tra | Chuỗi authority cần có (quy ước role prefix mặc định) | Ví dụ |
|---|---|---|
| `hasAuthority("SCOPE_orders:read")` | Đúng chuỗi `SCOPE_orders:read` | Kiểm tra OAuth scope đã map. |
| `hasAuthority("ROLE_SUPPORT")` | Đúng chuỗi `ROLE_SUPPORT` | Kiểm tra authority role được cấp và map tin cậy. |
| `hasRole("SUPPORT")` | Thường tương đương kiểm tra `ROLE_SUPPORT` | Shortcut cho role với prefix `ROLE_` mặc định. |
| `hasAuthority("orders:read:any")` | Đúng chuỗi `orders:read:any` | Permission nội bộ nếu ứng dụng xây dựng. |

**`hasRole("ADMIN")` không kiểm tra scope `SCOPE_ADMIN`.** Spring mặc định thêm prefix `ROLE_` khi dùng `hasRole`; prefix có thể tùy chỉnh. Nếu API dùng OAuth scope để bảo vệ endpoint, một cách rõ ràng thường là `hasAuthority("SCOPE_orders:read")`.

### Lỗi thường gặp: kiểm tra sai namespace quyền

~~~java
// Sai kỳ vọng: token chỉ có "scope": "orders:read"
// mà code lại đòi ROLE_orders:read.
@PreAuthorize("hasRole('orders:read')")
public void readWronglyConfigured(String id) { /* ... */ }
~~~

Điều này thường dẫn đến **403 dù scope hợp lệ**, nếu không có `ROLE_orders:read`. Một lỗi nguy hiểm hơn là **tự thêm authority `ROLE_ADMIN` từ một claim `role=admin` không được phép tin**, dẫn đến vượt quyền.

## 5. Ví dụ Java/Spring Security: cấu hình kiểm tra scope

Mã bên dưới minh họa Spring Security 6 với API nhận **JWT access token**, sử dụng Method Security. Các import và lớp nghiệp vụ được lược bớt để làm nổi bật luồng kiểm soát.

~~~java
@Configuration
@EnableMethodSecurity
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Ví dụ một service:

~~~java
@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public OrderDto getOrder(String orderId, Authentication authentication) {
        // Sau kiểm tra scope, vẫn phải kiểm tra chủ sở hữu và tenant
        // từ các nguồn đã được xác minh. Chi tiết triển khai ở mục 6.
        return loadAndAuthorizeOrder(orderId, authentication);
    }
}
~~~

**Cảnh báo:** cấu hình `anyRequest().authenticated()` chỉ buộc API có một principal hợp lệ; các method thực thi nghiệp vụ khác **phải có kiểm tra action tương ứng**, nếu không vẫn có đường gọi thiếu quyền. Nếu ứng dụng có endpoint không có method security, cần rule web security/authorization service phù hợp. Không coi một annotation ở controller là biện pháp duy nhất khi service cũng có đường gọi từ job, handler hoặc endpoint khác.

### `issuer-uri` thường chưa đủ cho audience

Một cấu hình Resource Server phổ biến:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Cấu hình issuer giúp Spring khám phá/cấu hình cơ chế xác minh issuer và chữ ký theo môi trường phù hợp, nhưng **không được mặc định rằng cấu hình này tự bảo đảm `aud=orders-api`**. Resource Server phải cấu hình **audience validator** theo hợp đồng với Authorization Server.

Ví dụ minh họa custom validator ở Spring Security 6 (cần import các lớp tương ứng):

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.test";
    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withIssuerLocation(issuer)
        .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
    return decoder;
}
~~~

Ví dụ này nhấn mạnh **issuer và audience phải được kiểm tra riêng**. Ứng dụng thực tế còn cần quy tắc thuật toán/khóa, loại access token, trạng thái thu hồi, độ tươi quyền và kiểm tra proof nếu token ràng buộc người gửi; hãy dùng profile JWT access token của nhà phát hành và phiên bản thư viện đã chọn làm nguồn cấu hình cụ thể.

### Authority tùy biến phải từ nguồn tin cậy

Nếu AS phát hành claim riêng:

~~~json
{
  "scope": "orders:read",
  "roles": ["SUPPORT"],
  "tenant_id": "tenant-a"
}
~~~

Ứng dụng **có thể** ánh xạ role thành `ROLE_SUPPORT` bằng một `JwtAuthenticationConverter` tùy biến. Nhưng trước khi làm cần trả lời:

1. **Issuer nào** được phép phát hành claim `roles`?
2. Role có hiệu lực ở **tenant nào**? Có bị giới hạn bởi ứng dụng hoặc Resource Server không?
3. Role trong JWT có thể **lỗi thời** khi user bị thu hồi quyền không?
4. Có cần tra cứu quyền hiện hành từ database/policy service thay vì chỉ dùng claim không?
5. Mapping có phân biệt **scope**, **role** và **permission** để tránh nhầm namespace không?

Không tạo authority nhạy cảm từ `X-Role`, query `role=admin` hoặc JSON body do client tự gửi. Cũng không tin trường `roles` trong một ID token gửi tới API: ID token phục vụ xác thực tại **client OIDC**, không phải access token của Resource Server.

## 6. Scope được cấp không thay object-level authorization

Một access token có `scope=orders:read` giúp quyết định **loại action** có thể được yêu cầu. Nhưng phương thức `GET /orders/42` cần xem **order 42 thuộc ai**.

Ví dụ:

~~~text
Verified principal:
  sub = user-123
  tenant = tenant-a
  authorities = {SCOPE_orders:read}

Order 42 từ database:
  ownerId = user-999
  tenantId = tenant-b
~~~

Token hợp lệ cho Orders API và authority đọc đơn **không đủ**: request phải bị từ chối nếu không có ủy quyền liên tenant hợp lệ.

### Chính sách kiểm tra minh họa trong Java

~~~java
import java.util.Objects;
import java.util.Set;

record VerifiedPrincipal(
    String subjectId,
    String tenantId,
    Set<String> authorities,
    Set<String> permissions,
    boolean active
) {}

record Order(String id, String ownerId, String tenantId) {}

final class OrderPolicy {
    static boolean canRead(VerifiedPrincipal principal, Order order) {
        if (principal == null || order == null || !principal.active()) {
            return false;
        }
        if (principal.authorities() == null
                || !principal.authorities().contains("SCOPE_orders:read")) {
            return false;
        }
        if (principal.tenantId() == null || principal.tenantId().isBlank()
                || !Objects.equals(principal.tenantId(), order.tenantId())) {
            return false;
        }

        boolean owner = principal.subjectId() != null
                && Objects.equals(principal.subjectId(), order.ownerId());
        boolean support = principal.permissions() != null
                && principal.permissions().contains("orders:read:any");

        return owner || support;
    }
}
~~~

**Giả định rõ:** `VerifiedPrincipal` được xây dựng sau xác minh access token, đúng issuer/audience/type và kiểm tra trạng thái, tenant/membership theo chính sách. `Order` được tải từ cơ sở dữ liệu phía server. Permission `orders:read:any` phải được cấp **trong đúng tenant**; ví dụ trên chưa bao gồm cơ chế lấy và cập nhật permission hiện hành.

Nếu muốn cho `support` quyền đọc order thuộc tenant khác, không được chỉ bỏ điều kiện tenant; phải thiết kế **ủy quyền xuyên tenant cụ thể**, có audit và kiểm tra phạm vi đối tượng tương ứng.

### Đừng quên giới hạn ở cấp field/action

Một principal được xem đơn không mặc nhiên được xem toàn bộ trường dữ liệu nhạy cảm, chẳng hạn thông tin thanh toán, dữ liệu cá nhân hoặc ghi chú nội bộ. Sau khi xác minh quyền đọc object, có thể cần **field-level authorization** khi tạo DTO.

Tương tự, `orders:read` không cho quyền `orders:cancel`, và `orders:write` không nhất thiết cho quyền thay đổi `ownerId`, `tenantId` hoặc giá trị thanh toán. Cần kiểm tra action và trường được phép cập nhật để tránh **Broken Function Level Authorization** và **mass assignment**.

## 7. Những cách kết hợp scope và authority đúng với nghiệp vụ

### 7.1. Điều kiện AND: scope và permission đều bắt buộc

Chẳng hạn API cho phép hoàn tiền **khi**:

~~~text
audience == "billing-api"
AND scope includes "payments:refund"
AND principal has permission "refund:execute" for current tenant
AND payment is in refundable state
AND transaction meets any approval policy
~~~

Một cách kiểm tra sai là:

~~~text
if hasScope("payments:refund") OR hasRole("FINANCE"):
    allow any refund
~~~

Nếu nghiệp vụ yêu cầu **cả scope và permission**, dùng `OR` sẽ tạo đường vượt quyền. Cách kết hợp `AND`/`OR` là **quy tắc policy được thiết kế**, không phải điều Spring Security hoặc OAuth tự đoán.

### 7.2. Scope như giới hạn trên của quyền

Client chỉ được cấp `orders:read` thì dù principal có role nội bộ `ADMIN`, **token ấy cũng không được dùng để sửa đơn** khi API yêu cầu `orders:write`. Role không nên mở rộng vượt quá phạm vi ủy quyền của token dành cho client đó.

Ngược lại, nếu token có `orders:write` nhưng principal không có quyền sửa order của user khác, Object Policy vẫn từ chối. Hai lớp độc lập giúp hạn chế quyền cả ở **client/grant** lẫn **người dùng/tài nguyên**.

### 7.3. Mỗi Resource Server có authority namespace và audience riêng

Ví dụ:

| RS | Audience yêu cầu | Scope cho action | Authority nội bộ tương ứng |
|---|---|---|---|
| Orders API | `orders-api` | `orders:read` | `SCOPE_orders:read` |
| Orders API | `orders-api` | `orders:cancel` | `SCOPE_orders:cancel` |
| Billing API | `billing-api` | `payments:refund` | `SCOPE_payments:refund` |

**Có authority `SCOPE_orders:read` trong security context không có nghĩa** Billing API được phép dùng token đó. Audience phải được xác minh **trước khi** mapping authority. Không chuyển tiếp token đầu vào `aud=orders-api` sang Billing rồi chỉ kiểm tra một authority mang tên chung như `read`.

### 7.4. Token đại diện người dùng hay client?

Trong luồng `authorization_code` có người dùng, policy có thể cần cả **subject, client, tenant và scope**. Trong `client_credentials`, token thường đại diện cho **service principal/client**; không mặc nhiên có người dùng cuối. Với tác vụ service-to-service, không dùng `client_id` như thể đó là `userId` của một khách hàng hoặc lấy quyền của người dùng từ role dịch vụ.

Nếu service cần gọi API khác thay mặt người dùng, cần cơ chế **delegation/token exchange** phù hợp và token có đúng audience/scope đích; không tự thêm `scope` hoặc `ROLE_ADMIN` vào token mà AS đã cấp.

## 8. JWT và opaque token: authority được lấy từ đâu?

### JWT access token

~~~mermaid
sequenceDiagram
    participant Client
    participant API as Resource Server
    participant Keys as Trusted JWKS
    participant Policy as Resource Policy
    Client->>API: Bearer JWT
    API->>Keys: Dùng khóa issuer đã được cấu hình để xác minh
    Keys-->>API: Khóa xác minh tin cậy
    API->>API: Verify signature, iss, aud, exp/nbf, token type
    API->>API: Map granted scope -> authorities
    API->>Policy: authorize(principal, action, resource, context)
    Policy-->>API: PERMIT / DENY
    API-->>Client: Response theo quyết định
~~~

Một JWT có thể có các claims `scope`, `roles`, `permissions`, nhưng API chỉ được dựa vào chúng **sau xác minh** và chỉ khi issuer/profile có thẩm quyền phát biểu các claims đó. Việc JWT còn hạn **không bảo đảm** quyền trong claim chưa bị thu hồi.

### Opaque access token

~~~mermaid
sequenceDiagram
    participant Client
    participant API as Resource Server
    participant AS as Trusted Authorization Server
    participant Policy as Resource Policy
    Client->>API: Bearer opaque token
    API->>AS: Introspection qua xác thực/kênh an toàn
    AS-->>API: active + aud + scope + subject + metadata
    API->>API: Check active, audience, lifetime, token purpose
    API->>API: Map granted scope -> authorities
    API->>Policy: authorize(principal, action, resource, context)
    Policy-->>API: PERMIT / DENY
    API-->>Client: Response theo quyết định
~~~

Opaque token không mặc nhiên an toàn hơn: nếu introspection trả `active: true` nhưng thiếu audience hoặc dữ liệu policy bắt buộc, API phải từ chối. Cache introspection chỉ nên dùng với thời gian sống phù hợp với yêu cầu thu hồi; token bị thu hồi có thể tiếp tục được chấp nhận trong khoảng cache nếu thiết kế cho phép.

### Thay đổi quyền trong lúc token còn hạn

Giả sử AS cấp JWT có `roles=["SUPPORT"]`, sau đó admin bỏ vai trò Support. Nếu API chỉ kiểm tra chữ ký và `exp`, token cũ vẫn có thể sinh `ROLE_SUPPORT` cho đến khi hết hạn.

Cách xử lý tùy rủi ro:

- Access token có **TTL đủ ngắn** và audience/scope hẹp.
- Với thao tác nhạy cảm, kiểm tra **role/permission hiện hành** ở nguồn tin cậy thay vì chỉ đọc JWT.
- Dùng **introspection, denylist, session version hoặc revocation state** nếu cần thu hồi nhanh.
- Quản lý **cache authority/permission** và cơ chế làm mất hiệu lực theo thay đổi membership.
- Kiểm tra điều kiện resource ngay tại transaction khi trạng thái tài nguyên có thể thay đổi, giảm lỗi **TOCTOU**.

Không nhất thiết phải truy vấn database cho mọi request ở mọi hệ thống; cần xác định **độ tươi quyền** theo mức nguy hiểm của hành động.

## 9. Phản hồi 401 và 403 khi kiểm tra scope/authority

| Trường hợp | Phản hồi thường dùng | Giải thích |
|---|---|---|
| Thiếu access token hoặc token sai/hết hạn/sai audience | **401 Unauthorized** | Không có token được chấp nhận để thiết lập principal. |
| Token hợp lệ nhưng thiếu `orders:read` | **403 Forbidden** | Đã xác thực nhưng **không có scope** cho action. |
| Token hợp lệ, scope đủ, nhưng thiếu permission `orders:read:any` khi đọc order của người khác | **403** hoặc **404** | Không có quyền trên object; 404 có thể che giấu sự tồn tại. |
| JWT còn hạn nhưng issuer/role không tin cậy | **401** nếu bản thân token không được chấp nhận, **403** nếu token hợp lệ nhưng thiếu quyền | Phân biệt lỗi xác thực token với lỗi policy. |
| Không thể xác minh introspection/JWKS hoặc trạng thái bắt buộc | **Không cấp quyền** | Có thể phản hồi lỗi tạm thời phù hợp, nhưng không tự cho qua. |

Với bearer token, RFC 6750 định nghĩa cơ chế `WWW-Authenticate`, ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders:read"
~~~

Không đưa token hoặc quyền nhạy cảm không cần tiết lộ vào response/log. Client gặp `401` do token hết hạn có thể xin token mới theo luồng đã cấp, nhưng gặp `403` vì thiếu quyền không nên refresh vô hạn và tự cho rằng sẽ được cấp scope rộng hơn.

### Audit nên ghi gì?

Nên ghi kết quả authorization với các thuộc tính được phép ghi log: **issuer**, **client**, **principal ID**, **tenant**, **API/action**, **resource ID**, **policy version**, **lý do từ chối** và **thời điểm**. Nếu cần dấu vết token, dùng định danh/tóm lược an toàn thay vì ghi nguyên access token hoặc refresh token. Principal trong audit phải đến từ kết quả đã xác minh, không từ `X-User-Id` hoặc body do client tự nhập.

## 10. Các lỗi thực tế khi kiểm tra scope và authority

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Decode JWT rồi tin claim `scope` ngay | Có thể cấp quyền theo JSON giả mạo. | Xác minh chữ ký/issuer/audience/type trước khi mapping. |
| `hasRole("orders:read")` thay `hasAuthority("SCOPE_orders:read")` | Sai namespace, thường tạo 403 không mong muốn. | Hiểu rõ tiền tố `SCOPE_`, `ROLE_` và converter đang chạy. |
| Tự chuyển `role=admin` từ body thành `ROLE_ADMIN` | **Privilege escalation**. | Role chỉ đến từ nguồn đã xác minh và policy cấp quyền. |
| So khớp scope bằng `contains("read")` | `reports:read` có thể bị hiểu nhầm là `orders:read`. | Parse thành tập scope và so khớp chính xác. |
| Bỏ `aud` vì hai API dùng chung issuer | Token của RS khác dùng sai mục đích. | Kiểm tra expected audience riêng từng RS. |
| Có `SCOPE_orders:read` là truy cập mọi order | **BOLA/IDOR**, lộ dữ liệu tenant khác. | Kiểm tra owner, tenant, quan hệ và field ở backend. |
| Role admin cấp quyền mọi tenant | Vượt ranh giới đa tenant. | Role/permission phải được ràng buộc với tenant/resource. |
| Nhầm ID token hoặc refresh token là access token | API tin thông tin sai mục đích. | Kiểm tra token type và audience theo profile. |
| Tin quyền JWT cũ mãi đến `exp` trong giao dịch nhạy cảm | Quyền bị thu hồi vẫn được sử dụng. | TTL, revocation hoặc tra cứu quyền hiện hành. |
| Gateway kiểm tra scope nên service bỏ policy | Các đường gọi nội bộ có thể bypass. | Enforce tại service/điểm sử dụng resource. |
| Chỉ kiểm tra annotation ở API GET, quên POST/PATCH/job | **Broken Function Level Authorization**. | Đặt policy theo action, bảo vệ tất cả lối vào nghiệp vụ. |
| Kẻ tấn công sao chép bearer token còn hạn | Phát lại request trong phạm vi token. | Bảo vệ token, scope/aud/TTL hẹp, thu hồi, DPoP/mTLS nếu cần. |

## 11. Ma trận kiểm thử policy

Giả sử `order-42` thuộc `tenant-a`, do `user-123` tạo. Orders API nhận access token có `aud=orders-api` và chính sách:

~~~text
read order requires:
    verified access token for orders-api
    AND authority SCOPE_orders:read
    AND same tenant
    AND (isOwner OR has tenant-scoped orders:read:any permission)
~~~

| Trường hợp | Kết quả kỳ vọng | Lý do |
|---|---|---|
| User-123, tenant A, `SCOPE_orders:read`, đọc order-42 | **PERMIT** | Đủ scope/authority, đúng owner và tenant. |
| User-456, tenant A, `SCOPE_orders:read`, đọc order-42 | **DENY** | Cùng tenant nhưng không owner/không permission hỗ trợ. |
| User-456, tenant A, `SCOPE_orders:read` + `orders:read:any` trong tenant A | **PERMIT** | Có quyền hỗ trợ đúng tenant theo policy. |
| User-456, tenant B, có role `ADMIN` của B | **DENY** | Role B không vượt sang tenant A. |
| User-123, token thiếu `orders:read` nhưng có `orders:write` | **DENY** | Không suy scope đọc từ scope ghi theo hợp đồng ví dụ. |
| User-123, token có `aud=billing-api` và `orders:read` | **DENY** | Token không được cấp cho Orders API. |
| User-123, token `exp` đã qua | **DENY** | Token không còn hiệu lực. |
| User-123, token hợp lệ, request `POST /orders/42/cancel` với scope đọc | **DENY** | Action khác cần scope/permission khác. |
| User-123, token hợp lệ, client gửi `X-Role: ADMIN` | **Không tăng quyền** | Header do client gửi không được tin để tạo authority. |
| User bị khóa sau khi cấp token, request nhạy cảm | **DENY theo chính sách trạng thái hiện hành** | Áp dụng kiểm soát thu hồi/active principal phù hợp. |
| Opaque token introspection `active=true`, thiếu audience bắt buộc | **DENY** | Không chứng minh token dành cho API. |
| Bearer token bị sao chép và chưa bị thu hồi | **Có nguy cơ bị lạm dụng** | Scope/authority không tự chứng minh người đang cầm token. |

Khi viết unit test cho policy và integration test tại Resource Server, cần thử **đúng/sai scope**, **đúng/sai audience**, **role/authority mapping**, **không có token**, **sai tenant**, **quyền cũ** và **các endpoint/method khác nhau**. Kiểm tra cả **lộ dữ liệu trường nhạy cảm** sau khi object được phép đọc.

## 12. Tình huống tự luyện

**Tình huống A — Sai tiền tố Spring.** JWT được xác minh có `scope="orders:read"`, nhưng method dùng `@PreAuthorize("hasRole('orders:read')")`. Vì sao request thường bị 403?

**Giải thích:** Với convention mặc định, Spring map scope thành `SCOPE_orders:read`, còn `hasRole` tìm `ROLE_orders:read`. Cần policy dùng `hasAuthority('SCOPE_orders:read')` hoặc cấu hình mapping thống nhất theo yêu cầu.

**Tình huống B — Token của Billing gửi cho Orders.** Token có chữ ký đúng và scope `orders:read` nhưng `aud=billing-api`. Orders có được dựng authority rồi cấp quyền không?

**Giải thích:** Không. Token sai audience phải bị từ chối ở bước xác minh **trước khi mapping authority**.

**Tình huống C — Quyền ở body.** Request `PATCH /orders/42` gửi JSON `{"role":"ADMIN","tenant_id":"tenant-a"}` trong khi JWT của caller chỉ có `orders:read`. Có được sửa không?

**Giải thích:** Không. Body không thể nâng quyền; cần scope/permission cho action sửa, kiểm tra owner/tenant và allowlist các trường được cập nhật.

**Tình huống D — Support khác tenant.** Principal có `ROLE_SUPPORT` ở tenant B và `orders:read`; yêu cầu đọc order của tenant A. Có cho phép không?

**Giải thích:** Không, trừ khi có ủy quyền liên tenant riêng và kiểm tra rõ ràng. Role không tự vượt ranh giới tenant.

**Tình huống E — Role đã bị thu hồi.** JWT có `roles=["SUPPORT"]` còn hạn, nhưng admin vừa xóa role trong database. Một API chỉ map role từ JWT vẫn có thể cho phép?

**Giải thích:** Có thể. Claim có thể cũ; hành động nhạy cảm cần nguồn quyền hiện hành hoặc cơ chế thu hồi/TTL đáp ứng yêu cầu rủi ro.

**Tình huống F — Opaque token còn hoạt động.** Introspection trả `active=true`, `scope=orders:read` nhưng không thể kiểm tra audience theo hợp đồng. Có cho phép gọi Orders không?

**Giải thích:** Không. `active` không chứng minh token được phát cho Resource Server này; phải đáp ứng mọi điều kiện bắt buộc.

**Tình huống G — Token có đủ scope nhưng order khác chủ.** User-123 có `SCOPE_orders:read`; order thuộc user-999. Có thể trả đơn chỉ vì authority hợp lệ không?

**Giải thích:** Không. Cần kiểm tra object-level authorization. Authority nói về loại thao tác, không thay ownership/tenant/permission.

## Checklist triển khai

1. **Chuẩn hóa hợp đồng:** issuer, audience, token type, định dạng JWT/opaque, claim scope, authority namespace và ý nghĩa role/permission theo từng Resource Server.
2. **Xác minh trước mapping:** chữ ký/JWKS hoặc introspection, thuật toán/khóa tin cậy, `iss`, `aud`, `exp`/`nbf`, trạng thái token và proof nếu cần.
3. **Scope đã được cấp:** parse đúng kiểu và cách tách, so khớp chính xác, không dựa vào scope do client từng yêu cầu.
4. **Role và authority đáng tin:** phân biệt `SCOPE_` với `ROLE_`; không nâng quyền từ header/body hoặc ID token; kiểm tra tenant/nguồn/độ tươi role.
5. **Policy theo action:** riêng cho read, write, cancel, refund, admin; không suy quyền rộng từ scope/role khác.
6. **Object-level authorization:** kiểm tra owner, tenant, quan hệ ủy quyền, trạng thái và field được phép trả hoặc thay đổi.
7. **Enforcement toàn diện:** web layer, service layer, job/event handler, lời gọi nội bộ và downstream API; không chỉ ẩn nút trong UI.
8. **Phản hồi đúng:** 401 cho token không được chấp nhận, 403/404 cho quyền không đủ; thông báo lỗi không lộ secret.
9. **Quyền có thể thay đổi:** TTL, revocation, introspection cache, permission/membership hiện hành và transaction check cho tác vụ nhạy cảm.
10. **Đánh giá bị đánh cắp/phát lại:** HTTPS, lưu trữ token, không log token, audience/scope hẹp và DPoP/mTLS khi cần sender proof.
11. **Kiểm thử cả đường từ chối:** sai audience, role mapping nhầm, scope gần giống, ID token, tenant khác, token hết hạn, thiếu quyền, quyền cũ và access token bị phát lại.

## Ghi nhớ

**Token validation xác lập nền tảng tin cậy; scope giới hạn loại thao tác được ủy quyền; authority là biểu diễn quyền trong security context; authorization tại Resource Server quyết định quyền thực tế trên từng đối tượng.** Trong Spring Security, scope thường được ánh xạ thành `SCOPE_...`, còn role thường dùng `ROLE_...` theo cấu hình. Không coi hai namespace là một, không đọc scope từ token chưa xác minh, không bỏ qua audience và không để authority thay thế kiểm tra owner/tenant. Bảo vệ vòng đời, thu hồi và chống replay vẫn cần thiết ngay cả khi token và authority đều hợp lệ.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
