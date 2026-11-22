# 401, 403 do token, scope, quyền đối tượng hoặc CSRF

Một ứng dụng gọi `GET /v1/orders/ord-42` và nhận `403 Forbidden`. Người phát triển nghĩ “JWT hết hạn”, thay token mới nhưng vẫn bị từ chối. Ở một màn hình khác, `POST` bị 403 dù `GET` cùng phiên đăng nhập hoạt động bình thường. Nếu sửa bằng cách xóa `@PreAuthorize`, thêm `permitAll()` hoặc tắt CSRF toàn ứng dụng, lỗi có thể biến mất nhưng lỗ hổng bảo mật xuất hiện.

Trong chương **Chẩn đoán sự cố** của module `INTEGRATION_API_REST`, bài học này hướng dẫn truy tìm **đúng lớp đã từ chối request** trong REST API Java/Spring và xác minh nguyên nhân bằng HTTP, log, token claims, authorization policy và integration tests. Nó kết nối các phần thiết kế resource/URI, xác thực, phân quyền, Problem Details, quan sát hệ thống và kiểm thử API.

**Mục tiêu:** phân biệt 401/403/404; hiểu Bearer token và `WWW-Authenticate`; kiểm tra JWT issuer, audience, expiry, signature; phân biệt scope với quyền đọc/sửa *đúng đối tượng*; nhận diện CSRF khi dùng cookie/session; phân biệt CORS preflight; viết test chứng minh quyền cần thiết được cấp nhưng quyền không cần thiết vẫn bị từ chối.

## 1. Đừng suy đoán nguyên nhân chỉ từ HTTP status

Yêu cầu có thể bị chặn bởi gateway, proxy, WAF, CORS, CSRF, authentication filter, route policy, method security hoặc service/domain authorization:

~~~mermaid
flowchart TD
    C[Browser/mobile/API client] --> G[Gateway / WAF / ingress]
    G --> F[Spring Security filter chains]
    F --> A[Authentication / token validation]
    F --> X[CSRF / CORS policy nếu áp dụng]
    A --> P[Route và method authorization]
    X --> P
    P --> O[Object-level authorization]
    O --> S[Business service + repository]
    G -. "Có thể chặn trước ứng dụng" .-> E[HTTP 401 / 403 / 404]
    F -. "Có thể từ chối" .-> E
    P -. "Thiếu scope/role" .-> E
    O -. "Sai tenant/owner" .-> E
~~~

Sơ đồ nhấn mạnh **các ranh giới kiểm soát**, không phải thứ tự thực thi chính xác của mọi filter. Trong Spring Security, CSRF có thể từ chối một POST trước khi controller chạy; một request bị gateway chặn thì thậm chí không tạo log trong ứng dụng.

| Triệu chứng | Nguyên nhân cần nghi ngờ | Cách phân biệt |
| --- | --- | --- |
| `401` khi không gửi Authorization | Chưa có credentials | `WWW-Authenticate`, HTTP request thực |
| `401` có `invalid_token` | Token không được chấp nhận | JWT/opaque decoder, `iss`, `aud`, `exp`, signature |
| `403` có `insufficient_scope` | Token hợp lệ nhưng thiếu quyền yêu cầu | Claim scope → GrantedAuthority → route rule |
| `403` dù scope đúng | Sai object/tenant/owner hoặc CSRF | Service policy, CsrfFilter, logs |
| `403` chỉ khi POST/PUT/PATCH dùng cookie | Thiếu/sai CSRF token | Loại authentication và CSRF repository |
| `404` khi truy cập order của user khác | Chính sách che sự tồn tại | Query lọc quyền, test chéo tenant |
| Browser báo CORS, curl chạy | Preflight hoặc CORS header bị chặn | OPTIONS, Origin, Access-Control-* |
| Trả 302/HTML login thay vì JSON | Form-login chain/SSO/proxy | Chain matcher và entrypoint |
| Chỉ một vùng/release lỗi | IdP/JWKS/proxy/clock/config khác nhau | So sánh metadata deployment và trace |

Ngay lúc bắt đầu, ghi lại **method, route template, thời điểm, môi trường, mã HTTP thực, `Content-Type`, `WWW-Authenticate`, request ID/trace ID**. Không gửi token/cookie thật vào issue, log chung hay công cụ decode không được kiểm soát.

## 2. 401, 403 và 404: khác nhau về semantics

Tên `401 Unauthorized` dễ gây nhầm. Trong HTTP, 401 chủ yếu có nghĩa yêu cầu **chưa có thông tin xác thực hợp lệ** cho tài nguyên. `403 Forbidden` nghĩa server hiểu request nhưng **không cho phép thực hiện**. Một token hợp lệ có thể bị 403 vì thiếu scope hoặc không được phép thao tác resource cụ thể.

| HTTP | Khi nào thường trả | Hành vi client |
| --- | --- | --- |
| **401 Unauthorized** | Thiếu, hết hạn hoặc sai access token | Lấy credentials hợp lệ bằng auth flow; retry có giới hạn |
| **403 Forbidden** | Đã xác thực nhưng không có quyền hoặc bị CSRF filter chặn | Không refresh vô hạn; kiểm tra policy hoặc CSRF |
| **404 Not Found** | Resource không tồn tại; hoặc cố ý giấu resource ngoài quyền | Không suy diễn resource có thật hay không |
| **400 Bad Request** | Authorization header sai cú pháp hoặc request không parse được | Sửa request, không chỉ đổi token |

Đối với HTTP `401`, response phải chứa một hoặc nhiều `WWW-Authenticate` challenge phù hợp. Với Bearer token theo RFC 6750, các ví dụ dưới là **hợp đồng minh họa**, không phải mọi framework mặc định tạo chính xác body JSON này.

**Thiếu bearer:**

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/auth-required",
  "title": "Yêu cầu xác thực",
  "status": 401,
  "code": "AUTH_REQUIRED"
}
~~~

**Token không được chấp nhận:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/invalid-token",
  "title": "Thông tin xác thực không hợp lệ",
  "status": 401,
  "code": "INVALID_ACCESS_TOKEN"
}
~~~

**Bearer đã hợp lệ nhưng thiếu scope:**

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders.write"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/insufficient-scope",
  "title": "Không đủ quyền thực hiện thao tác",
  "status": 403,
  "code": "INSUFFICIENT_SCOPE"
}
~~~

Trong `WWW-Authenticate`, `realm`, `error` và `scope` có ngữ nghĩa của Bearer challenge. Chỉ công bố scope cần thiết nếu policy cho phép, không liệt kê quyền ẩn hay thông tin object nhạy cảm. `code` trong body là **extension** của Problem Details RFC 9457, không phải member bắt buộc.

**Ngoại lệ quan trọng:** không phải 403 nào cũng chứng minh đã xác thực. Ví dụ CsrfFilter chặn request trước authentication; WAF có thể trả 403; resource server có thể bị custom entrypoint cấu hình sai. Vì thế phải truy ra **nguồn phản hồi**.

## 3. Kiểm tra Bearer access token đúng thứ tự

Một REST Resource Server thường nhận:

~~~http
GET /v1/orders/ord-42 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

**Không dùng OpenID Connect ID token thay access token** chỉ vì cả hai có thể là JWT. ID token chủ yếu dành cho client xác nhận đăng nhập; access token dành cho resource server với audience và scope thích hợp.

### 3.1. JWT: decode khác verify

Một JWT/JWS compact có ba phần:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Decode phần payload **không chứng minh** chữ ký hợp lệ. Ví dụ claims của access token đã được verify:

~~~json
{
  "iss": "https://idp.example.com/realms/commerce",
  "sub": "user-381",
  "aud": ["orders-api"],
  "exp": 1795000000,
  "nbf": 1794996400,
  "iat": 1794996400,
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a"
}
~~~

Các giá trị `exp`, `nbf`, `iat` là **NumericDate tính bằng giây từ Unix epoch**, không phải milliseconds. Những con số trong ví dụ chỉ mô tả kiểu dữ liệu, không phải token có thể sử dụng.

| Điều kiện | Dấu hiệu khi sai | Cần xác minh |
| --- | --- | --- |
| Header `Authorization` | `401` | Có gửi tới đúng host, proxy có giữ header, đúng scheme Bearer |
| Chữ ký và thuật toán | `401 invalid_token` | Trusted JWKS/keys, `kid`, algorithm allowlist, key rotation |
| `iss` | `401` | Issuer có đúng realm/environment backend chấp nhận |
| `aud` | `401` khi audience được kiểm | Token dành cho orders-api chứ không phải client/API khác |
| `exp` | `401` | Hết hạn, clock skew, đồng bộ giờ |
| `nbf` | `401` | Token chưa có hiệu lực hoặc máy chủ lệch giờ |
| Loại token | `401` | JWT hay opaque; access token hay ID token |
| `scope`/`scp` | Thường `403` sau khi token được xác thực | Converter ánh xạ claim thành authority nào |
| `tenant_id`/`sub` | `403` hoặc `404` tùy object policy | Principal có được xem đúng resource |

**Các bước kiểm tra:**

1. Xem request thực tế có `Authorization` không, nhất là sau redirect/chuyển hostname qua ingress.
2. Kiểm token bằng validator đáng tin: signature, allowed algorithm, trusted issuer, audience, expiry và not-before.
3. Đối với JWT, tra `kid`/JWKS được ứng dụng tin cậy; **không** lấy tùy ý khóa từ header do người gọi điều khiển. Không chấp nhận `alg=none`.
4. Đối với opaque token, kiểm luồng introspection và trạng thái active; không cố parse như JWT.
5. Chỉ **sau khi authentication thành công** mới kiểm scope/role và quyền đối tượng.

### 3.2. Những lỗi môi trường giống “token sai”

- **Wrong environment:** access token staging gửi production, `iss` hoặc `aud` không khớp.
- **JWKS rotation:** token có `kid` mới nhưng collector/proxy/backend chưa lấy khóa mới được, dẫn tới 401 cho một nhóm token.
- **Clock skew:** đồng hồ không đồng bộ khiến `exp`/`nbf` sai; không vô hiệu kiểm expiry để chữa cháy.
- **Audience sai:** token dành cho Inventory API gửi sang Orders API; dù scope text có tên quen thuộc vẫn không hợp lệ cho resource này.
- **Gateway header stripping:** client có gửi bearer nhưng app không nhận; so sánh access log tại gateway với app mà không ghi raw token.
- **Revocation:** JWT tự chứa có thể còn được chấp nhận tới `exp` trừ khi dùng cơ chế thu hồi; opaque token có thể bị introspection báo inactive. Đừng suy diễn chỉ từ hình dạng token.

### 3.3. Nếu 401 tăng sau deploy

So sánh cấu hình `issuer-uri`, audience, trust store, DNS/egress tới JWKS, hệ thống giờ/NTP, cache key và logic decoder theo **vùng/phiên bản triển khai**. Một lỗi rollout JWT key có thể khác hoàn toàn với token hết hạn của một người dùng. Không log nguyên token để debug; log reason code ở mức phân loại được phê duyệt và correlation ID.

## 4. Scope và role: token hợp lệ vẫn có thể 403

**Authentication** xác nhận principal và claims đáng tin; **authorization** quyết định principal có được làm việc đang yêu cầu không. Scope mô tả quyền hành động ở mức rộng nhưng **không** đồng nghĩa được phép xem mọi order.

| Endpoint | Quyền route ví dụ | Quyền nghiệp vụ còn phải kiểm |
| --- | --- | --- |
| `GET /v1/orders` | `orders.read` | Chỉ list order trong phạm vi được phép |
| `GET /v1/orders/{id}` | `orders.read` | Tenant/owner hoặc role được ủy quyền |
| `POST /v1/orders` | `orders.write` | Có quyền dùng địa chỉ giao hàng và tenant |
| `PATCH /v1/orders/{id}` | `orders.write` | Owner/role, trạng thái đơn, field-level policy |
| `GET /v1/admin/orders` | Quyền admin đặc biệt | Tenant và phạm vi quản trị rõ ràng |

Một mapping JWT thường gặp trong Spring Security:

~~~text
JWT:
  "scope": "orders.read orders.write"

GrantedAuthority:
  SCOPE_orders.read
  SCOPE_orders.write
~~~

Với `.hasAuthority("SCOPE_orders.write")`, một token chỉ có `orders.read` sẽ bị 403 ở POST dù chữ ký, issuer và audience đều hợp lệ. Nếu custom converter tạo `ROLE_orders.write` hoặc chỉ `SCOPE_read`, policy cũng có thể từ chối dù developer “nhìn thấy scope” trong JWT. Cần so sánh **claim → converter → GrantedAuthority → matcher**.

`hasRole("ADMIN")` thường tìm `ROLE_ADMIN` theo prefix mặc định, trong khi `hasAuthority("SCOPE_orders.read")` so khớp chính xác authority. Scope `openid`/`profile` của OIDC không cấp quyền đọc/tạo đơn theo mặc định. Đừng lấy `role` từ request body/header làm nguồn quyền.

### 4.1. Spring Boot 3 / Spring Security 6: cấu hình Resource Server mẫu

Ứng dụng API sau chỉ sử dụng **Bearer access token trong header**, không nhận session cookie để xác thực các đường `/v1/**`. Cần `spring-boot-starter-security` và `spring-boot-starter-oauth2-resource-server`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/v1/**")
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Chỉ phù hợp nếu API không xác thực bằng cookie tự gửi.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/v1/orders", "/v1/orders/*")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/v1/orders")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PATCH, "/v1/orders/*")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/commerce
~~~

`issuer-uri` hỗ trợ discovery/thiết lập decoder để xác minh chữ ký và issuer theo khả năng Spring; **không mặc định rằng chỉ khai báo issuer đã validate audience của orders-api**. Cần thêm audience validator theo phiên bản Spring đang dùng hoặc `JwtDecoder` được cấu hình đúng, rồi có integration test chứng minh token `aud=["other-api"]` bị từ chối. Không tắt signature, issuer hay expiry để giảm 401.

**Giới hạn cấu hình ví dụ:** Chỉ có matcher `/v1/**`; những URL ngoài phạm vi phải được bảo vệ bởi chain khác hoặc fallback deny-all. Nếu ứng dụng phục vụ cả form login/session, chain web phải giữ CSRF. `csrf.disable()` ở đây không phải “cách chữa 403”; nó dựa vào sự thật rằng trình duyệt **không tự đính kèm** bearer header từ JavaScript như session cookie. Nếu bearer được lưu trong cookie và server dùng cookie để xác thực, nguy cơ CSRF vẫn tồn tại.

### 4.2. IdP dùng claim `scp` hoặc `permissions`

Một số IdP phát `scp` dưới dạng mảng thay cho chuỗi `scope`. Khi cần converter tùy chỉnh:

~~~java
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

Converter<Jwt, AbstractAuthenticationToken> converter = jwt -> {
    List<String> scopes = jwt.getClaimAsStringList("scp");
    if (scopes == null) scopes = List.of();

    var authorities = scopes.stream()
        .filter(s -> s.matches("[a-zA-Z0-9._:-]{1,80}"))
        .map(s -> new SimpleGrantedAuthority("SCOPE_" + s))
        .toList();
    return new JwtAuthenticationToken(jwt, authorities);
};

// Dùng trong cấu hình resource server nếu cần:
// .oauth2ResourceServer(oauth2 -> oauth2
//     .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
~~~

Snippet này **thay** converter mặc định, không nên thêm vào nếu IdP đã tương thích với `scope`. Trong thực tế cần test kiểu claim, null, trùng lặp, thứ tự và policy không cấp quyền vượt mong muốn. Chỉ lấy claims sau khi JWT được xác minh, không nhận quyền từ metadata client tự gửi.

## 5. Object-level authorization: scope đúng vẫn có thể bị 403/404

**BOLA (Broken Object Level Authorization)** hoặc IDOR là lỗi cho phép người dùng đổi ID trong URL để đọc/sửa resource không thuộc quyền. `SCOPE_orders.read` cho phép dùng hành động đọc theo chính sách, **không có nghĩa đọc mọi đơn hàng**.

~~~text
GET /v1/orders/ord-42
JWT: sub=user-b, tenant_id=tenant-b, scope=orders.read

Resource ord-42:
  owner_id=user-a, tenant_id=tenant-a
~~~

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Security filter
    participant S as Orders service
    participant D as Database
    C->>A: GET /v1/orders/ord-42 + Bearer
    A->>A: Verify token and require orders.read
    A->>S: Trusted principal
    S->>D: SELECT WHERE id, tenant_id, owner_id
    alt Resource được phép
        D-->>S: Order
        S-->>C: 200 Order DTO
    else Không thuộc quyền hoặc không tồn tại
        D-->>S: Empty
        S-->>C: 404 (policy giấu sự tồn tại)
    end
~~~

Trong ví dụ, chọn **404** cho trường hợp không tồn tại **và** ngoài quyền xem, giúp không lộ việc resource có thật. API nội bộ có thể chọn **403** nếu muốn báo thiếu quyền. Dù chọn 403 hay 404, cần công bố chính sách và bảo đảm khác biệt về count, error detail, link hoặc timing không làm rò dữ liệu nhạy cảm.

### 5.1. Lọc ngay ở repository

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface OrderRepository extends JpaRepository<OrderEntity, String> {
    @Query("""
        select o from OrderEntity o
        where o.id = :id
          and o.tenantId = :tenantId
          and o.ownerId = :ownerId
        """)
    Optional<OrderEntity> findVisible(
        @Param("id") String id,
        @Param("tenantId") String tenantId,
        @Param("ownerId") String ownerId
    );
}
~~~

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderQueryService {
    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderView read(String orderId, JwtAuthenticationToken auth) {
        String tenantId = auth.getToken().getClaimAsString("tenant_id");
        String ownerId = auth.getToken().getSubject();

        if (tenantId == null || tenantId.isBlank()
                || ownerId == null || ownerId.isBlank()) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Missing required identity claims");
        }

        OrderEntity order = orders.findVisible(
            orderId, tenantId, ownerId
        ).orElseThrow(() -> new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Order not found"));

        return new OrderView(order.getId(), order.getStatus().name());
    }
}

record OrderView(String id, String status) {}
~~~

`OrderEntity` có `id`, `tenantId`, `ownerId`, `status` minh họa. `JwtAuthenticationToken` chỉ phù hợp hệ thống dùng JWT Resource Server; với opaque token/session, lấy principal tin cậy theo adapter tương ứng. Việc dùng `sub` như owner chỉ đúng **nếu domain thiết kế ownerId cùng kiểu định danh với sub**; nhiều hệ thống phải ánh xạ qua account/customer table. Tài khoản admin/ủy quyền cần policy riêng, không mở quyền bằng cách bỏ tenant filter.

**Các bề mặt dễ sót:** List endpoint phải filter quyền **trước** phân trang/count; nested resource `/v1/orders/{orderId}/lines/{lineId}` phải kiểm line thuộc order; địa chỉ giao hàng trong POST phải thuộc người gọi; PATCH phải kiểm object *và field* được phép; update nên dùng conditional write/transaction để tránh race giữa kiểm quyền và commit.

Chỉ mock repository trả `Optional.empty()` chưa đủ chứng minh chống BOLA. Cần integration test với DB thật có hai tenant, hai owner, nhiều order và kiểm tra cả count/link/projection.

## 6. CSRF: vì sao GET thành công nhưng POST/PUT/PATCH bị 403?

**Cross-Site Request Forgery (CSRF)** là tình huống một trang độc hại dụ trình duyệt người dùng gửi request làm thay đổi trạng thái tới ứng dụng mà trình duyệt tự đính kèm **credentials của nạn nhân** (thường là cookie phiên). Nếu server chỉ kiểm cookie đăng nhập, nó không biết request có đúng ý định người dùng hay không.

### 6.1. JWT không tự quyết định có cần CSRF hay không

| Cơ chế xác thực | Trình duyệt tự gắn credentials? | Chính sách CSRF |
| --- | --- | --- |
| Session cookie/Form login | Có thể, theo chính sách cookie | **Cần** chống CSRF cho thao tác thay đổi dữ liệu |
| Bearer trong header `Authorization` do client tự thêm | Không tự có header chỉ vì trang khác gửi request | Thường có thể bỏ CSRF **chỉ cho API bearer-only**; vẫn cần XSS protection |
| Access token dạng JWT lưu trong cookie, server đọc cookie để xác thực | Có thể | **Vẫn có nguy cơ CSRF**, không bỏ chỉ vì đó là JWT |
| API chấp nhận cả bearer header và session cookie | Có đường tự động xác thực bằng cookie | Cần chính sách đúng cho đường cookie, hoặc tách chain rõ |

`SameSite=Lax`/`Strict` của cookie giảm rủi ro một số trường hợp nhưng không phải lời hứa tuyệt đối rằng mọi request thay đổi trạng thái đã an toàn. Tùy kiến trúc, dùng token chống CSRF, cookie `Secure`/`HttpOnly`, kiểm tra `Origin` hoặc `Referer` đáng tin, bảo vệ XSS và xác minh hành động nhạy cảm.

### 6.2. Request có cookie nhưng thiếu CSRF token

~~~http
POST /web/profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=<session-cookie>
Content-Type: application/x-www-form-urlencoded

displayName=Lan
~~~

Một ứng dụng Spring Security session-based có CSRF sẽ từ chối POST trên bằng **403** nếu thiếu hoặc sai token, dù cùng session đó GET trang profile thành công. GET là safe method theo HTTP semantics, thường không yêu cầu CSRF; còn POST/PUT/PATCH/DELETE thường được bảo vệ.

Ví dụ một template engine render form có token do server cấp:

~~~html
<form method="post" action="/web/profile">
  <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_RENDER">
  <input type="text" name="displayName">
  <button type="submit">Lưu</button>
</form>
~~~

`TOKEN_DO_SERVER_RENDER` là placeholder, **không** hardcode token trong form thật. Template phải lấy token từ Spring Security `CsrfTokenRepository` và escape phù hợp. Với SPA gửi JSON qua JavaScript, cần cơ chế nhận token, gửi đúng header và hỗ trợ deferred token/XOR masking tùy phiên bản Spring Security 6. Không chỉ tạo cookie tên `XSRF-TOKEN` rồi cho rằng server tự xác thực đúng nếu chưa cấu hình request handler.

**Chẩn đoán đúng:** xác định `CsrfFilter` có áp dụng không, token được cấp chưa, có gắn đúng session không, có bị rotate sau login/logout không, frontend có gửi header/form field đúng không. **Không tắt CSRF toàn ứng dụng để chữa một POST 403**.

### 6.3. Cách tách API Bearer và giao diện web session

Một ứng dụng có thể cần hai `SecurityFilterChain`:

- `/v1/**` dành cho API chỉ dùng Bearer token trong header, stateless (mục 4).
- `/web/**` dành cho trình duyệt dùng session cookie, form login và CSRF.

Ví dụ web chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/web/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .csrf(Customizer.withDefaults());
    return http.build();
}
~~~

Đây là **trích đoạn** đặt trong class `@Configuration`, không phải toàn bộ thiết kế đăng nhập/logout. Cần xác định thứ tự chain API (`@Order(1)`) và fallback phù hợp cho mọi URL còn lại. Form login mặc định có thể dùng đường `/login` nằm ngoài `/web/**`; nếu muốn hoạt động trọn vẹn, phải cấu hình login page/processing URL và chain/matcher để các đường đó được bảo vệ/cho phép đúng. Không lấy snippet làm cấu hình ứng dụng hoàn chỉnh.

### 6.4. 403 do CSRF khác 403 do scope

Nếu cùng một POST bị 403:

1. Xác minh request dùng **cookie** hay **Bearer header** và chain nào xử lý.
2. Xem server log an toàn có `MissingCsrfTokenException` / `InvalidCsrfTokenException` không.
3. Kiểm tra authentication đã thành công chưa và có authority cần thiết không.
4. Sau khi CSRF hợp lệ, request có thể tiếp tục bị 403 do thiếu role/scope hoặc quyền đối tượng. **Một request có thể vi phạm nhiều điều kiện**, chỉ điều kiện kiểm trước được nhìn thấy trong response.

Với API chỉ bearer, nếu POST vẫn 403, chưa đủ để kết luận CSRF: có thể thiếu `SCOPE_orders.write` hoặc object policy từ chối.

## 7. CORS preflight: browser báo “CORS error” không đồng nghĩa 401/403 nghiệp vụ

Khi JavaScript ở `https://app.example.com` gọi `https://api.example.com` với `Authorization` và JSON, browser thường gửi **OPTIONS preflight**:

~~~http
OPTIONS /v1/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Preflight **không tự mang access token** của request POST. Nếu `AuthorizationFilter` yêu cầu bearer trên mọi OPTIONS và CORS chưa được xử lý đúng, request bị chặn trước khi POST thật được gửi. Browser thường chỉ báo “blocked by CORS policy”; server có thể ghi 401/403 ở preflight, không phải ở POST.

Phân biệt:

- **CORS** là chính sách trình duyệt quyết định trang web origin nào được đọc response/gửi một số cross-origin request. Nó không thay thế authentication hoặc authorization.
- **CSRF** bảo vệ thao tác dùng credentials mà browser có thể tự gắn, đặc biệt session cookie.
- **Scope/object-level authorization** vẫn phải kiểm đối với request nghiệp vụ ngay cả khi CORS cho phép origin.
- `curl`/Postman không thực thi chính sách CORS của trình duyệt; request thành công bằng curl không chứng minh browser CORS đã đúng.

### Cấu hình CORS giới hạn origin trong Spring

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PATCH", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "If-Match"));
    config.setAllowCredentials(false); // API bearer-only, không cookie.
    config.setMaxAge(600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/v1/**", config);
    return source;
}

// Kích hoạt trong API SecurityFilterChain:
// http.cors(Customizer.withDefaults());
~~~

Nếu UI dùng cookie cross-origin, cần chỉnh đồng bộ `allowCredentials`, danh sách origin tường minh, cookie flags, CORS response và CSRF; **không dùng wildcard `Access-Control-Allow-Origin: *` với credentials**. Không sửa CORS bằng cách `permitAll()` cho POST tạo đơn. Ngay cả origin được phép, người gọi vẫn phải có bearer hợp lệ, đủ scope và quyền resource.

## 8. Quy trình chẩn đoán lặp lại được

~~~mermaid
flowchart TD
    A["Thấy 401/403 hoặc browser bị chặn"] --> B{"Request tới application?"}
    B -- Không --> G["Kiểm tra gateway/WAF/ingress/CORS"]
    B -- Có --> C{"Đã xác thực đúng?"}
    C -- Không --> D["401: token/header/issuer/audience/expiry/key"]
    C -- Có --> E{"CSRF hoặc CORS chặn?"}
    E -- Có --> F["Session/CSRF token/preflight/chain"]
    E -- Không --> H{"Đủ scope/role cho route?"}
    H -- Không --> I["403: converter, matcher, method rule"]
    H -- Có --> J{"Có quyền object/tenant?"}
    J -- Không --> K["403 hoặc 404 theo policy"]
    J -- Có --> L["Điều tra business rule và custom error"]
~~~

### Bước 1 — Tái hiện yêu cầu tối thiểu

Thu thập URL/method, status, response headers, thời điểm UTC, release/environment và correlation ID. Xem tab Network để phân biệt OPTIONS với POST. Với `curl`, dùng token thử nghiệm được cấp an toàn qua biến môi trường/secret manager, không đưa token vào URL, stdout chia sẻ hay tài liệu:

~~~bash
# ACCESS_TOKEN là token TEST từ môi trường an toàn.
curl -i -sS "https://api.example.com/v1/orders" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json"
~~~

Thử request **không có header** để nhìn `WWW-Authenticate`; không dùng token thật của khách hàng trong kênh support.

### Bước 2 — Xác định nguồn response

| Dấu hiệu trên wire/log | Tầng cần kiểm |
| --- | --- |
| Không thấy request ID trong log ứng dụng | Gateway, ingress, WAF, CORS preflight |
| Bearer challenge với `invalid_token` | JWT decoder/opaque introspector |
| Bearer `insufficient_scope` | Authority mapping hoặc policy scope |
| Log `Missing CSRF token` / `Invalid CSRF token` | CsrfFilter + session/browser client |
| Security logs cho thấy authenticated nhưng controller chưa chạy | Request matcher/method security/CSRF |
| Controller/service đã chạy rồi ném 403/404 | Object-level auth, tenant/owner, business policy |
| Trả 302 và HTML form login | Browser/form chain hoặc reverse proxy login redirect |

Lỗi có thể được xử lý khác nhau qua `AuthenticationEntryPoint`, `AccessDeniedHandler` và `@RestControllerAdvice`. Một handler tại controller **không nhất thiết thấy** exception xảy ra từ filter chain trước controller. Khi muốn thống nhất `application/problem+json`, phải cấu hình ở đúng tầng và test response thật; với 401 Bearer vẫn cần `WWW-Authenticate`.

### Bước 3 — Kiểm tra chain và policy

Trong Spring Security 6, xem:

1. `securityMatcher` chọn chain nào, `@Order` và path có bị rewrite không?
2. Authentication là `BearerTokenAuthenticationFilter`/JWT decoder hay session/form login?
3. `hasAuthority`, `hasRole`, `@PreAuthorize` và ánh xạ GrantedAuthority thực tế?
4. `CsrfFilter` có đang chặn unsafe method? `CorsFilter` đã xử lý preflight trước auth chưa?
5. Service/repository có kiểm tenant, owner, nested resource và quyền field trước khi trả/ghi dữ liệu không?

Có thể tạm bật log chẩn đoán trong môi trường thử nghiệm:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Giới hạn thời gian và phạm vi log; **không bật DEBUG/TRACE lan rộng trên production vô hạn**. Không ghi raw JWT, cookie, CSRF token, email, hoặc full claims. Dùng reason code, trace ID, route template và các thông tin tối thiểu đã được phê duyệt.

### Bước 4 — Sửa đúng biến, sau đó kiểm lại quyền từ chối

- Token sai issuer/audience → sửa auth flow hoặc backend trust config, **không tắt JWT validators**.
- Scope chưa được cấp → sửa policy cấp quyền được phê duyệt hoặc client login/consent flow, không đổi `permitAll()`.
- Spring tạo authority sai → sửa converter/claim mapping đã kiểm chứng bằng test.
- Cookie POST thiếu CSRF → phát/gửi CSRF token hợp lệ, giữ CSRF cho session chain.
- User A đọc resource B → **giữ 403/404** và chứng minh server không làm lộ dữ liệu.
- Preflight thiếu CORS → sửa whitelist/header/method, không mở business endpoint không xác thực.

Sau sửa luôn kiểm thử **positive** (đúng quyền được phép) và **negative** (thiếu quyền bị từ chối). Nếu chỉ positive pass, có thể vừa vô tình xóa rào chắn.

## 9. Kiểm thử 401/403/CSRF/BOLA bằng Spring

### 9.1. Ma trận test nên có

| Trường hợp | Test ở đâu? | Kỳ vọng |
| --- | --- | --- |
| Thiếu Authorization | HTTP + security filter | 401 + Bearer challenge |
| JWT sai chữ ký, hết hạn, sai issuer | Resource Server integration | 401 invalid_token |
| JWT đúng chữ ký nhưng `aud` khác orders-api | Decoder validator integration | 401 nếu policy yêu cầu audience |
| JWT có `orders.read` GET list | MockMvc route + service | 200, dữ liệu đúng quyền |
| JWT chỉ có `orders.read` POST tạo đơn | MockMvc route | 403, service không thực thi |
| JWT có `orders.read` đọc order tenant khác | DB integration | 404/403 theo policy, không lộ dữ liệu |
| Cookie session POST thiếu CSRF | Browser chain integration | 403 |
| Cookie session POST có CSRF | Browser chain integration | Qua security, business response hợp lệ |
| Preflight OPTIONS từ origin hợp lệ | CORS/security integration | Preflight hợp lệ không yêu cầu Bearer |
| Preflight origin không hợp lệ | CORS integration | Không cấp CORS permission |
| JWKS rotation, token có `kid` mới | Decoder/JWKS integration | Tái tải khóa theo policy, không tắt verify |
| Gateway không forward Authorization | End-to-end/staging | Phát hiện nguồn 401 trước release |

### 9.2. Test route scope bằng MockMvc

`jwt()` từ Spring Security Test mô phỏng một `JwtAuthenticationToken`, **không tự kiểm chữ ký**. Nó phù hợp kiểm route/role và xử lý sau khi authentication đã thành công.

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void readScopeDoesNotAllowCreate() throws Exception {
    mockMvc.perform(post("/v1/orders")
            .with(jwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))
                .jwt(j -> j.claim("tenant_id", "tenant-a")))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"items\":[{\"sku\":\"BOOK-42\",\"quantity\":1}]}"))
        .andExpect(status().isForbidden());

    verifyNoInteractions(orderCommandService);
}

@Test
void readScopeAllowsList() throws Exception {
    mockMvc.perform(get("/v1/orders")
            .with(jwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))
                .jwt(j -> j.claim("tenant_id", "tenant-a"))))
        .andExpect(status().isOk());
}
~~~

Đây là **test trích đoạn**. Cần `MockMvc` có Spring Security filters, controller/service mock và dữ liệu/fixtures phù hợp. Test POST chỉ chứng minh 403, chưa chỉ rõ do scope hay CSRF; cần xem chain đang áp dụng và khẳng định API bearer-only test config như mục 4. Mock service có thể phải được reset giữa các test để `verifyNoInteractions` phản ánh request hiện tại.

### 9.3. Test thiếu bearer và JWT validation thực

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@Test
void missingBearerReturns401Challenge() throws Exception {
    mockMvc.perform(get("/v1/orders"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            "WWW-Authenticate",
            org.hamcrest.Matchers.containsString("Bearer")));
}
~~~

Để chứng minh **JWT signature/issuer/audience/exp** được kiểm tra đúng, không dùng `.with(jwt())`. Hãy gửi token ký thật trong integration test với test JWKS/IdP hoặc cấu hình `JwtDecoder` và validators đáng tin, rồi assert:

~~~text
No token                         → 401
Invalid signature                → 401
Expired token                    → 401
Wrong issuer                     → 401
Wrong audience                   → 401
Valid token but missing scope    → 403
Valid scope but wrong object     → 403/404 theo policy
~~~

Với decoder dùng mock trong test, có thể kiểm controller flow nhưng **không** kiểm chứng logic chữ ký của một decoder thật. Phân biệt rõ hai cấp test này.

### 9.4. Test CSRF trên session web

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void sessionPostWithoutCsrfIsRejected() throws Exception {
    mockMvc.perform(post("/web/profile").with(user("lan")))
        .andExpect(status().isForbidden());
}

@Test
void sessionPostWithCsrfPassesSecurity() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("lan"))
            .with(csrf())
            .param("displayName", "Lan"))
        .andExpect(status().is3xxRedirection());
}
~~~

Test thứ hai giả định controller update profile thành công rồi **redirect 3xx**; nếu controller trả 200/204 thì assert theo contract thực. `csrf()` do test framework tạo CSRF token phù hợp, nhưng chưa chứng minh browser thật phát/nhận cookie/header, rotate token hoặc CORS đúng. Cần kiểm thử tích hợp luồng client cho các tình huống đó.

### 9.5. Test BOLA thật với hai tenant

~~~text
Fixture:
  tenant-a, user-a, order-A
  tenant-b, user-b, order-B
  Cả hai token đều có orders.read.

user-a GET /v1/orders/order-A           -> 200, đúng data
user-a GET /v1/orders/order-B           -> 404 theo policy che existence
user-b GET /v1/orders/order-A           -> 404
user-a GET /v1/orders?size=20           -> chỉ có order-A
user-a GET /v1/orders/order-B/lines/1   -> 404
user-a PATCH /v1/orders/order-B         -> 404 hoặc 403 theo policy
~~~

**Kiểm tra database query thực** thay vì chỉ mock repository. Count, `hasNext`, link, resource con và lỗi cũng không được lộ order-B. Với thao tác ghi, xác minh order-B **không thay đổi**, kể cả nếu hai request thực hiện đồng thời. Đừng dùng một test có scope khác nhau để chứng minh object authorization; hai user đều phải có `orders.read` để tách đúng nguồn từ chối.

## 10. Problem Details và quan sát sự cố

Để client/SDK xử lý đúng, API nên công bố status và mã lỗi ổn định:

| Lý do | HTTP theo ví dụ | `code` trong Problem Details |
| --- | --- | --- |
| Thiếu bearer | 401 | `AUTH_REQUIRED` |
| Token sai/hết hạn | 401 | `INVALID_ACCESS_TOKEN` |
| Thiếu scope | 403 | `INSUFFICIENT_SCOPE` |
| Quyền object không đủ và được phép báo rõ | 403 | `OBJECT_ACCESS_DENIED` |
| Resource không tồn tại hoặc cần che | 404 | `RESOURCE_NOT_FOUND` |
| CSRF thiếu/sai trong session app | 403 | `CSRF_VALIDATION_FAILED` |

`code` ở đây là extension, không phải trường bắt buộc của **RFC 9457**. Với 401, body Problem Details **không thay thế** `WWW-Authenticate`; với 403/404 object-level, tránh trả owner, tenant hoặc scope ẩn trong `detail`. SecurityFilterChain, gateway và MVC controller advice có thể phát các representation khác nhau; cần kiểm thử end-to-end thay vì khẳng định chỉ một `@RestControllerAdvice` đã bao phủ toàn bộ 401/403.

### Metric và log cần có

- HTTP request count và latency theo route template, method, status, deploy version.
- Authentication failure phân nhóm **missing**, **invalid signature**, **expired**, **issuer/audience mismatch**, **decoder/IdP unavailable** (theo điều hệ thống thật sự xác định).
- Authorization denials theo nhóm **insufficient scope**, **object access denied**, **CSRF invalid**.
- CORS preflight rejection, JWKS refresh errors, IdP latency, key rotation timeline, clock skew và 401 theo vùng.
- Trace/request ID để đối chiếu gateway → Spring Security → service, không dùng token hoặc user ID làm metric label cardinality cao.

Không log nguyên bearer JWT, cookie session, CSRF token, PII hoặc toàn bộ claims. Nếu người dùng báo 403, yêu cầu **request ID, thời gian UTC, route đã che ID nhạy cảm và mã HTTP**, không yêu cầu gửi access token vào kênh hỗ trợ.

### Runbook khi 401/403 tăng đột biến

~~~text
1. Khoanh vùng: route, method, release, region, thời điểm, 401 vs 403.
2. So sánh gateway/WAF và application logs theo request/trace ID.
3. Nếu 401: kiểm header, token type, issuer, audience, exp, JWKS/clock.
4. Nếu 403: kiểm chain, CSRF/CORS preflight, scope/GrantedAuthority.
5. Scope đúng? Kiểm object/tenant/owner query và policy 403/404.
6. Tái hiện bằng fixture và test token được cấp hợp lệ.
7. Sửa đúng tầng, KHÔNG xóa rào chắn.
8. Test cả positive/negative và đo request/error rate sau deploy.
~~~

### Những cách “sửa” cần tránh

| Anti-pattern | Vì sao nguy hiểm |
| --- | --- |
| `.anyRequest().permitAll()` | Bỏ bảo vệ mọi route |
| `csrf.disable()` với ứng dụng dùng cookie session | Mở khả năng CSRF trên thao tác thay đổi |
| Bỏ verify signature, issuer, audience hoặc expiry | Chấp nhận token không dành cho API hoặc đã hết hạn |
| Cho phép `alg=none` / decode JWT không verify | Mất bảo đảm token đến từ bên phát hành tin cậy |
| Dùng `tenantId` của client làm nguồn quyền | Có thể truy cập chéo tenant |
| Chỉ kiểm scope rồi `repository.findById(anyId)` | BOLA/IDOR |
| CORS wildcard với credentials | Phá giới hạn cross-origin trong mô hình cookie |
| Trả HTTP 200 với `{"error":"forbidden"}` | Gateway/client/metric hiểu nhầm là success |
| Refresh token liên tục mỗi khi 403 | Không giải quyết thiếu quyền, có thể tạo retry storm |
| Log nguyên JWT để “dễ debug” | Rò credential và dữ liệu người dùng |

## 11. Bài tập thực hành

**Bài 1 — Mã HTTP và nguyên nhân.** Với bốn request: (a) thiếu Authorization, (b) JWT hết hạn, (c) access token hợp lệ chỉ có `orders.read` gọi POST, (d) access token có `orders.read` truy cập order của tenant khác. Chọn status và `WWW-Authenticate` thích hợp, xác định lớp từ chối và giải thích khi nào (d) trả 404.

**Bài 2 — JWT issuer/audience.** Staging Orders API tin issuer `https://idp.staging.example.com`, audience `orders-api`. Mobile gửi **ID token** dành cho `mobile-client` nhưng payload chứa `orders.read`. Hãy giải thích vì sao không dùng được. Thiết kế decoder integration tests cho signature, `iss`, `aud`, `exp` và một test route dùng `MockMvc jwt()`; phân biệt chúng chứng minh được điều gì.

**Bài 3 — Chữa 403 POST nhưng giữ CSRF.** Một ứng dụng session cookie: GET `/web/profile` thành công, POST trả 403. Hãy kiểm CsrfFilter, thiết kế form/SPA gửi token hợp lệ, xử lý token sau login/logout và viết test thiếu token bị từ chối, có token đi qua. Tại sao `SameSite` không đồng nghĩa luôn an toàn và `csrf.disable()` không phải cách sửa đúng?

**Bài 4 — Chống BOLA.** Tạo hai tenant, mỗi tenant có hai user và ba order. Viết query theo `id/tenant/owner`, kiểm cả list/detail/nested lines/PATCH, assert quyền cấp cho user A không cho phép xem/sửa order user B. Kiểm tra cả `totalCount`/`hasNext` và Problem Details không lộ resource.

**Bài 5 — CORS vs authorization.** Frontend gửi Bearer + JSON từ origin khác; OPTIONS preflight nhận 401 trước POST. Hãy thiết kế `CorsConfigurationSource` whitelist, test preflight hợp lệ và origin bị từ chối. Chứng minh sau khi sửa, POST vẫn cần token, scope và quyền object.

**Bài 6 — Key rotation sự cố vùng.** Sau một đợt đổi khóa IdP, một vùng có tỷ lệ 401 tăng ở token với `kid` mới. Lập runbook kiểm JWKS URL/cache/egress, issuer, audience, hệ thống giờ và status tại gateway. Đề xuất khắc phục giữ nguyên signature validation và test regression sau thay đổi.

**Gợi ý tự kiểm tra:** (1) Thiếu/sai token thường 401; thiếu scope 403; object không thuộc quyền 403/404 theo policy. (2) ID token không thay thế access token cho resource server; test JWT decoder thật mới chứng minh chữ ký/claims. (3) Session cookie cần CSRF protection cho unsafe methods; không tắt CSRF để sửa lỗi. (4) Scope chỉ kiểm hành động, quyền row/field phải gắn với principal đã xác thực. (5) CORS chỉ kiểm origin/preflight của browser, không thay auth và không cấp quyền nghiệp vụ. (6) Key rotation đòi xác minh trusted JWKS và cache/retry hợp lý, không bỏ verify chữ ký.
