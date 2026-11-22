# Không tin cậy header người dùng hoặc vai trò do máy khách tự gửi

## 1. Bài toán: người dùng có thể tự gửi bất kỳ header HTTP nào

Trong hệ thống **Spring Security reactive** có **API Gateway và nhiều tenant**, request thường đi qua các thành phần:

~~~text
Browser / Mobile / Đối tác
           │
           │ HTTPS
           │ Authorization: Bearer <access-token>
           │ X-User-Id: admin
           │ X-User-Roles: ROLE_ADMIN
           │ X-Tenant-Id: tenant-victim
           ▼
┌───────────────────────────────────────┐
│ Edge / Spring Cloud Gateway           │
│ - TLS / routing / logging             │
│ - Loại bỏ identity headers client gửi │
│ - Không tự coi X-User-* là danh tính   │
└──────────────────┬────────────────────┘
                   │ Private network
                   │ Authorization: Bearer <access-token>
                   ▼
┌────────────────────────────────────────────┐
│ Spring Boot WebFlux Resource Server        │
│ - ReactiveJwtDecoder.verify(...)           │
│ - Kiểm iss, aud, exp, nbf, signature       │
│ - JwtAuthenticationToken trong Context    │
│ - Scope/role từ trusted identity policy    │
│ - Kiểm tenant trong URL và quyền dữ liệu    │
└────────────────────────────────────────────┘
~~~

**Đề bài:** một client có thể gửi `X-User-Id`, `X-User-Roles` hoặc `X-Tenant-Id` bất kỳ. Nếu gateway hay service phía sau coi các giá trị đó là đã được xác thực, attacker có thể giả người khác, giả quản trị viên, hoặc truy cập dữ liệu của tenant khác.

HTTP header chỉ là dữ liệu do bên gửi cung cấp; **tên header không tự tạo tính tin cậy**. Cùng một chuỗi `X-Authenticated-User: alice` có thể được:
- Client bên ngoài tự viết.
- Reverse proxy thêm sau khi xác thực người dùng.
- Gateway ghi đè trên một tuyến đã xác thực.
- Proxy trung gian giữ lại từ request cũ.
- Một hệ thống nội bộ không đáng tin gửi trực tiếp vào backend.

Backend chỉ có thể tin identity header nếu **mạng, gateway, giao thức và chính sách đã chứng minh nguồn gốc, tính toàn vẹn và phạm vi quyền** của thông tin đó. Trong thiết kế bảo thủ hơn, backend **tự xác minh JWT Bearer token**, không coi raw identity headers là bằng chứng authentication.

### Mục tiêu học tập

Sau bài này bạn có thể:
1. Nêu threat model của `X-User-Id`, `X-User-Roles`, `X-Tenant-Id`, `X-Forwarded-User` và các header tương tự.
2. Phân biệt **header do client khai**, **metadata network từ proxy** và **claims trong access token đã được xác minh**.
3. Thiết lập trust boundary ở gateway/ingress: xóa identity headers chưa tin, xác minh JWT, kiểm soát đường truy cập vào backend.
4. Sử dụng Spring Cloud Gateway WebFlux `RemoveRequestHeader` đúng cách.
5. Hiểu vì sao **chỉ xóa header ở gateway vẫn chưa đủ** nếu backend reachable trực tiếp hoặc một service khác tin headers.
6. Cấu hình Spring Security WebFlux Resource Server với `issuer-uri`, `jwk-set-uri`, `audiences` và `SecurityWebFilterChain`.
7. Đưa tenant từ verified JWT claim vào quyết định authorization, không để `X-Tenant-Id` hoặc query/path tự ghi đè quyền.
8. Viết ứng dụng Java 17+ và kiểm thử `WebTestClient` với JWT RSA ký thật để minh họa 401, 403, 200.
9. Nhận diện rủi ro multi-issuer, confused deputy, insecure internal headers, header spoofing và lateral movement.
10. Thiết kế lựa chọn an toàn hơn khi thật sự phải truyền identity qua gateway: internal audience-bound signed assertion/mTLS hoặc token relay có verify ở service.

## 2. Những tên header dễ bị lạm dụng

| Header | Client có thể tự gửi không? | Nguy cơ nếu tự tin là identity |
| --- | --- | --- |
| `X-User-Id` | Có | Giả danh user khác để đọc dữ liệu theo ID |
| `X-Authenticated-User` | Có | Bỏ qua login nếu app xem là principal đã xác thực |
| `X-Auth-Request-User` | Có | Bypass một cơ chế auth proxy nếu ingress không xóa/ghi đè |
| `X-Principal` | Có | Tiêm principal tùy ý |
| `X-Roles` | Có | Giả ADMIN/MANAGER/OWNER |
| `X-User-Roles` | Có | Role spoofing/privilege escalation |
| `X-Tenant-Id` | Có | Cross-tenant data access nếu code tin header |
| `X-Organization-Id` | Có | Chọn org khác với identity đã xác thực |
| `X-Forwarded-User` | Có | Lạm dụng một header “trông giống proxy” |
| `X-Forwarded-For` | Có nếu proxy không sanitize | Giả IP; không phải user identity |
| `Forwarded` | Có nếu proxy không sanitize | Giả scheme/host/for metadata, dẫn tới URL/IP spoof |
| `Authorization` | Có | Chứa credential; **chỉ tin sau xác minh cryptographic/protocol** |

Không có một danh sách header cố định cho mọi sản phẩm. Cần kiểm toàn bộ **identity-related names do gateway, ingress, auth proxy, service mesh, framework và legacy app của tổ chức sử dụng**.

Một số hạ tầng dùng header khác như `X-Remote-User`, `X-Email`, `X-Group`, `X-Auth-Request-Groups`. **Đổi tên không tăng độ tin cậy**.

### 2.1. Ví dụ tấn công trực tiếp

~~~http
GET /api/tenants/tenant-b/reports HTTP/1.1
Host: api.example.com
X-User-Id: ceo
X-User-Roles: ROLE_ADMIN
X-Tenant-Id: tenant-b
X-Authenticated-User: ceo
~~~

Nếu server dùng:

~~~java
// PHẢN VÍ DỤ: tuyệt đối không cấp quyền từ client header.
String userId = request.getHeaders().getFirst("X-User-Id");
String roles = request.getHeaders().getFirst("X-User-Roles");
String tenant = request.getHeaders().getFirst("X-Tenant-Id");

if ("ROLE_ADMIN".equals(roles)) {
    // CẤP QUYỀN ADMIN -- RẤT NGUY HIỂM!
}
~~~

thì bất kỳ người nào biết endpoint đều có thể tự gán role. Spring Security không tự bảo vệ đoạn code tùy biến này nếu bạn cố tình bỏ qua Authentication và tin header.

**Cách đúng:** identity và authority phải được lấy từ một `Authentication` đã đi qua `ReactiveAuthenticationManager`/JWT validation hoặc một cơ chế bảo mật nội bộ được xác minh. Header có thể truyền **gợi ý lựa chọn tenant** nhưng server phải đối chiếu nó với quyền thực tế.

### 2.2. Có Bearer token vẫn có thể bị header spoof

~~~http
GET /api/tenants/tenant-b/reports HTTP/1.1
Authorization: Bearer <TOKEN_FOR_ALICE_TENANT_A>
X-User-Id: bob
X-User-Roles: ROLE_ADMIN
X-Tenant-Id: tenant-b
~~~

JWT hợp lệ cho Alice/tenant A **không** cho phép header tự nâng thành Bob/admin/tenant B. Phải phân biệt:
- Token đã được verify: subject và scopes được AS xác nhận trong scope của issuer/audience.
- Header `X-User-Id`: chưa có nguồn gốc đáng tin.
- Tenant trong URL `tenant-b`: là **đối tượng/đích mà client yêu cầu**, không phải quyền truy cập.
- Tenant trong token: có thể là ngữ cảnh được trusted AS cấp, nhưng đối với dữ liệu nhạy cảm vẫn có thể cần kiểm membership/owner tại local DB.

## 3. Trust boundary: nơi bắt đầu và nơi kết thúc sự tin cậy

### 3.1. Không an toàn: backend công khai hoặc được gọi vòng qua gateway

~~~text
Internet client
     │
     ├─► Gateway có strip X-User-Id
     │       └─► Backend
     │
     └────────────► Backend direct HTTP :8090
                     X-User-Id: admin
~~~

Nếu backend lắng nghe Internet trên cổng 8090 và tin header như identity, attacker sẽ bỏ qua gateway và gửi trực tiếp. **Xóa header ở gateway không sửa được lỗi backend có đường bypass**.

Yêu cầu production:
- Backend chỉ reachable từ trusted gateway/sidecar/ingress bằng firewall, security groups hoặc Kubernetes NetworkPolicy.
- Không expose NodePort/LoadBalancer/public IP của backend một cách vô tình.
- Xem cả đường lateral movement giữa pods/services nội bộ.
- Ở ranh giới có nhu cầu bảo mật cao, dùng TLS/mTLS service-to-service và xác minh service identity.
- Quan trọng hơn, downstream vẫn tự xác minh access token hoặc một assertion nội bộ đã ký có audience hẹp; **network isolation là defense in depth, không là identity verification của end user**.

### 3.2. An toàn theo thiết kế: vừa xóa spoofed headers vừa xác minh Bearer

~~~text
Untrusted client
   │ X-User-Id=admin (giả)
   │ Authorization=Bearer(valid token Alice)
   ▼
Gateway:
  ├─ RemoveRequestHeader X-User-Id
  ├─ RemoveRequestHeader X-User-Roles
  ├─ RemoveRequestHeader X-Tenant-Id
  └─ Route đến private downstream
          │ Bearer(valid token Alice)
          ▼
Resource Server:
  ├─ Verify JWT (signature/iss/aud/exp)
  ├─ JWT principal = Alice
  ├─ JWT scopes → SCOPE_...
  ├─ tenant_id của JWT = tenant-a
  ├─ Request tenant-b ≠ tenant-a
  └─ 403, không phụ thuộc spoofed headers
~~~

Đây là **hai lớp độc lập**:
1. Gateway hygiene: không chuyển tiếp dữ liệu nhận dạng do client tự tạo dưới các tên header nội bộ.
2. Resource Server trust: không dùng header ấy làm credentials; tin JWT sau validation và kiểm tenant/resource ownership.

Ngay cả nếu một cấu hình route vô tình quên strip một header, Resource Server vẫn không cấp quyền từ header đó. Đây là defense in depth có giá trị.

### 3.3. Sự khác biệt giữa metadata mạng và identity

`X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` và RFC 7239 `Forwarded` mô tả metadata về proxy, IP, scheme và host. Chúng **không** phải user roles/identity. Spring WebFlux có `ForwardedHeaderTransformer` để diễn giải thông tin từ một **trusted proxy**, nhưng nó không tự biết header nào do attacker tạo.

Vì vậy:
- Edge phải loại/ghi đè forwarded metadata chưa tin ở Internet boundary.
- `X-Forwarded-For: 127.0.0.1` không chứng minh request thực sự đến từ localhost.
- Không dùng `X-Forwarded-Host`/`Host` tự khai để chọn tenant có quyền cao hoặc dựng password-reset URL chứa token.
- Phân biệt IP dùng cho rate limit/audit với identity dùng cho authorization.
- Mọi đường truyền giữa proxy và backend phải có một chính sách trusted hops rõ, không chọn bừa phần tử đầu trong `X-Forwarded-For`.

## 4. Spring Cloud Gateway: RemoveRequestHeader làm gì và không làm gì?

Spring Cloud Gateway **WebFlux** hỗ trợ filter factory:

~~~yaml
filters:
  - RemoveRequestHeader=X-User-Id
~~~

Ý nghĩa: xóa header `X-User-Id` khỏi request được **forward xuống upstream service** cho route đó. Đây là một hygiene control, không phải phép xác minh user.

Một policy thực tế nên xóa các header identity/role/tenant do client có thể gửi:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: reports
          uri: http://127.0.0.1:8090
          predicates:
            - Path=/api/**
          filters:
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-User-Roles
            - RemoveRequestHeader=X-Roles
            - RemoveRequestHeader=X-Tenant-Id
            - RemoveRequestHeader=X-Authenticated-User
            - RemoveRequestHeader=X-Auth-Request-User
            - RemoveRequestHeader=X-Principal
            - RemoveRequestHeader=X-Forwarded-User
~~~

Đoạn này dành cho **Spring Cloud Gateway Server WebFlux 4.1** (release train Spring Cloud 2023.0.x), có key `spring.cloud.gateway.routes`. Không sao chép nhầm key cấu hình của Spring Cloud Gateway MVC hoặc Gateway 5.x, vì đường dẫn properties khác nhau giữa sản phẩm/phiên bản.

**Giới hạn quan trọng của RemoveRequestHeader:**
- Nó xóa header **trên tuyến request qua gateway**, không thể ngăn client gọi backend trực tiếp nếu network cho phép.
- Nó không khiến `Authorization` trở thành trusted; Bearer vẫn cần decoder/validator.
- Nó không tự xác minh tenant membership, role hoặc ownership.
- Nó không bảo vệ routes không áp filter; dùng policy chung/GlobalFilter khi tổ chức có nhiều routes.
- Nó không ngăn một downstream khác tự tin headers với tên mới.
- Nó không thay TLS/mTLS/network isolation.
- Nó không tự đảm bảo proxy trước gateway đã làm sạch `Forwarded`/`X-Forwarded-*`.

### 4.1. Tại sao không nên chỉ set header thành "anonymous"?

Nếu gateway đơn giản:

~~~yaml
filters:
  - SetRequestHeader=X-User-Id,anonymous
~~~

thì backend có thể nghĩ rằng `anonymous` là một identity đáng tin, hoặc code khác tiếp tục dùng một header không được ràng buộc với JWT. Tốt hơn:
- **Không truyền** client-supplied internal identity headers.
- Để Resource Server xác minh JWT, rồi xây principal trong Spring Security Context.
- Nếu thật sự phải có identity header nội bộ cho legacy service, dùng một giao thức assertion có tính toàn vẹn và ràng buộc nguồn rõ ràng, không chỉ thay bằng một string.

### 4.2. Header names case-insensitive và multiple values

Trong HTTP, header field name không phân biệt chữ hoa/chữ thường. Client có thể thử:

~~~http
x-user-id: admin
X-USER-ID: administrator
X-User-Roles: ROLE_ADMIN
x-user-roles: ROLE_OWNER
~~~

Không dùng cách kiểm `headers.keySet().contains("X-User-Id")` với so sánh case-sensitive thuần túy rồi coi thiếu header giả. Framework server và gateway thường dùng abstraction case-insensitive, nhưng nếu bạn tự viết code low-level, phải dựa vào semantics chuẩn.

Một header có thể xuất hiện nhiều lần hoặc có danh sách giá trị. Không chọn `getFirst()` để “tin giá trị đầu tiên” trong một trust boundary chưa được sanitize. Với identity assertion nội bộ, phải có contract chặt: đúng một giá trị, định dạng chuẩn, nguồn tin cậy; reject ambiguous duplicates thay vì đoán.

### 4.3. Không nhầm StripPrefix/RewritePath với quyền tenant

Gateway route có thể strip `/gateway` hoặc rewrite path trước khi chuyển về service. Điều này không làm request tự có quyền tenant trong URL mới. Một yêu cầu tới `/api/tenants/tenant-b/reports` vẫn là yêu cầu tenant B, kể cả gateway vừa thay prefix. Service phải kiểm tenant và quyền.

Nếu authorization ở Gateway kiểm URL **trước rewrite**, còn service kiểm URL **sau rewrite**, cần bảo đảm cả hai thống nhất semantics (HTTP method, path normalization, encoded slash/dot segments). Không chỉ dựa trên gateway path matcher để bảo vệ tất cả object-level rules.

## 5. Ba chiến lược chuyển danh tính từ Gateway tới service

### 5.1. Chiến lược A — Gateway chuyển tiếp Bearer access token, service tự verify

~~~text
Client --Bearer access token--> Gateway
                                  │
                                  └--Bearer access token--> Resource Server
                                                                 │
                                                                 ├─ verify JWT
                                                                 ├─ map authorities
                                                                 └─ check tenant/object
~~~

Đây là chiến lược chính của bài:
- Gateway bỏ những header identity do client tự gửi.
- Không phát sinh trusted `X-User-Id` nào.
- Service phía sau sử dụng `spring-boot-starter-oauth2-resource-server` và `ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)`.
- Access token phải có `aud` phù hợp với service, không mượn token cấp cho frontend hoặc một API khác.
- JWT được validate bằng public key/JWKS do trusted AS chỉ định, không theo `jku` hoặc `iss` tùy ý.
- Service vẫn kiểm tenant/ownership và có thể kiểm user status/membership nội bộ.

**Ưu điểm:** rõ trust boundary, dễ kiểm thử; service không tin identity headers. **Đổi lại:** nhiều service có thể cần verify tokens/cache JWKS; giải quyết với config tập trung và libraries chung đã review.

### 5.2. Chiến lược B — Gateway xác thực và tạo assertion nội bộ có chữ ký

Khi backend legacy không muốn nhận access token từ Internet hoặc cần token exchange:

~~~text
External Bearer
   ▼
Gateway xác minh signature/issuer/audience và policy
   ▼
Gateway mint INTERNAL assertion
  iss  = trusted-gateway
  aud  = target-service
  sub  = verified external subject / local user ID
  tid  = authorized tenant
  exp  = now + short TTL
  jti  = unique ID (nếu cần chống replay)
  act  = provenance/actor metadata tùy protocol
   ▼
Private TLS/mTLS connection
   ▼
Service xác minh internal assertion từ trusted gateway key,
issuer, audience, expiry và required permissions
~~~

**Không phải** chỉ thêm `X-User-Id: alice`. Assertion phải có:
- Chữ ký bằng key service tin cậy, key rotation và thuật toán được allowlist.
- Issuer cụ thể, audience hẹp cho từng downstream.
- TTL ngắn và giới hạn scopes/permissions không vượt token gốc.
- Bind tenant/actor/context theo chính sách không bị client điều khiển.
- Kênh truyền bảo vệ (TLS/mTLS, ingress-only routes).
- Tránh replay/token forwarding sang service khác (audience-bound; có thể thêm confirmation/cnf theo threat model).

Nếu vẫn phải dùng header cho transport, ví dụ `X-Internal-Assertion: <signed JWT>`, header đó chỉ là **nơi chở chứng cứ đã ký**, không tự có tính tin cậy. Service **phải verify assertion** và ingress phải loại header cùng tên do client gửi.

### 5.3. Chiến lược C — Network-enforced pre-auth headers cho legacy service

Đôi khi app legacy chỉ nhận `X-Authenticated-User` từ auth proxy. Mô hình này **cần**:
- Service không reachable trực tiếp từ client/lateral services không được tin.
- Proxy đáng tin luôn loại header client gửi và **tự đặt** identity sau auth.
- mTLS/service identity hoặc lớp kiểm soát nguồn kết nối.
- Chính sách duplicate headers/serialization và enforcement một đường duy nhất.
- Audit, key ownership và integration tests bypass/proxy changes.
- Không bao giờ tự cho `X-User-Roles=ADMIN` chỉ vì request đến private IP.

Đây là mô hình phức tạp, dễ lạm dụng; với hệ thống WebFlux mới, nên ưu tiên service tự xác minh Bearer token hoặc signed internal assertion.

### 5.4. "TokenRelay" không phải bằng chứng rằng mọi header đã an toàn

Spring Cloud Gateway có cơ chế TokenRelay trong bối cảnh OAuth2 Client/authorized client để chuyển access token cho downstream. Nhưng:
- Không phải mọi bearer-only gateway đều cần `TokenRelay` filter.
- TokenRelay không làm `X-User-Id` đáng tin.
- Downstream vẫn cần xác minh access token hoặc được bao bọc bởi kiến trúc trust khác có kiểm soát.
- Access token phải phù hợp audience, scope và mục đích của downstream.
- Chuyển token qua route không được làm lộ bearer credentials sang một service không được ủy quyền.

Ví dụ trong bài **không dùng TokenRelay**: gateway chuyển request đến backend, backend tự kiểm Bearer header. Khi triển khai trong hệ thống OAuth2 Client phức tạp, xác định cơ chế token forwarding/exchange rõ ràng thay vì mù quáng thêm filter.

## 6. Multi-tenant: header tenant không bao giờ tự là permission

Xét ba loại tenant context:

| Nguồn tenant | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| URL path | `/api/tenants/tenant-b/reports` | Client muốn truy cập tài nguyên tenant B |
| HTTP header | `X-Tenant-Id: tenant-b` | Client tự khai; không chứng minh membership |
| Verified JWT claim | `tenant_id=tenant-a` | AS đã xác nhận một tenant context theo hợp đồng token; vẫn cần policy nội bộ |
| Database membership | `user=alice, tenant-a, role=READER` | Nguồn nội bộ có thể xác định user có quyền truy cập tenant và object cụ thể |

**Không** dùng `X-Tenant-Id` để override `tenant_id` của token. Nếu token chỉ cho tenant A mà URL yêu cầu tenant B, phải từ chối bất kể header nói gì.

### 6.1. Cách kiểm tối thiểu trong ví dụ

~~~java
String requestedTenant = tenantIdFromPath;
String tokenTenant = jwt.getClaimAsString("tenant_id");

if (!requestedTenant.equals(tokenTenant)) {
    return Mono.error(new ResponseStatusException(
        HttpStatus.FORBIDDEN, "Tenant mismatch"));
}
~~~

Đây là **kiểm tối thiểu** khi contract access token đã hạn chế token vào một tenant duy nhất. Với multi-tenant B2B thật:
- Một user có thể là member nhiều tenants.
- Token có thể chứa danh sách tenants hoặc chỉ subject; phải check membership trong database.
- Khi user đổi tenant, cần reauthorization/token refresh hoặc backend permission lookup theo đúng policy.
- Nếu token chứa `tenant_id` nhưng issuer không xác minh membership, claim đó không được coi là quyết định cuối cùng.
- Cần kiểm owner/tenant ở **query/update repository**, tránh chỉ kiểm một tham số request rồi query thiếu điều kiện tenant.

Ví dụ sai:

~~~java
// PHẢN VÍ DỤ: client tự chọn tenantId rồi truy vấn trần.
return repository.findByReportId(reportId);
~~~

Ví dụ ý định an toàn hơn:

~~~java
// SNIPPET kiến trúc: repository đã được scope theo tenant
// và user permission/membership đã được kiểm riêng.
return repository.findByTenantIdAndReportId(
    authorizedTenantId, reportId);
~~~

Repository method trên là interface giả định, không phải built-in Spring API. Trong production, security policy nên kiểm ownership/tenant ở data boundary để tránh IDOR/BOLA.

### 6.2. Tenant trong subdomain cũng là input từ client

`tenant-a.app.example.com` có thể là routing context, nhưng Host header có thể bị giả nếu proxy không validate. Đừng coi hostname hoặc `X-Forwarded-Host` là bằng chứng user thuộc tenant đó. Quy trình đúng:
1. Edge validate canonical host mapping và sanitize `Forwarded/X-Forwarded-Host`.
2. Gateway định tuyến theo tenant đã xác định.
3. Backend map verified identity sang membership trong tenant đó.
4. Service chỉ trả dữ liệu thuộc tenant có quyền.

### 6.3. Multi-issuer và JWKS SSRF

Trong multi-tenant OIDC/JWT, một token chưa xác minh có thể tự ghi:

~~~json
{"iss":"https://attacker.example","sub":"admin","roles":["ADMIN"]}
~~~

Nếu Resource Server tải JWKS từ bất kỳ `iss` được ghi trong JWT mà không có allowlist, attacker có thể tự phát token và tự cung cấp key cho nó. Thiết kế đúng:
- Chỉ chấp nhận trusted issuer URI nằm trong registry/config đã phê duyệt.
- Mỗi issuer có decoder, audience/algorithm/keys và mapping tenant phù hợp.
- Không tự trust header `X-Issuer`, `X-Jwks-Url` hoặc `jku` của JWT.
- Nếu dùng resolver multi-issuer, chính sách chọn issuer phải chặn SSRF/dynamic trust expansion.
- Role `ADMIN` ở IdP của tenant A không tự là global admin của toàn hệ thống.

## 7. Dự án minh họa gồm Gateway và downstream Resource Server

Bài này tách thành **hai ứng dụng Java 17+** để làm rõ ranh giới:

- **gateway**: Spring Cloud Gateway **4.1.9** (release train **2023.0.6**, tương thích Spring Boot **3.3.13**), lắng nghe `8080`; strip client identity headers; route `/api/**` tới downstream.
- **resource-service**: Spring Boot WebFlux Resource Server, lắng nghe `8090`; không lấy user/role/tenant từ HTTP headers; chỉ tin verified JWT và kiểm scope + tenant.

Hai project Gradle tách biệt. Các số phiên bản được ghim vì mục đích minh họa API; không đồng nghĩa là các dòng **đã hết hỗ trợ** nên dùng cho production ở thời điểm đọc.

### 7.1. Cấu trúc thư mục

~~~text
header-trust-lab/
├── gateway/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/
│       ├── java/demo/gateway/GatewayApplication.java
│       └── resources/application.yml
└── resource-service/
    ├── settings.gradle
    ├── build.gradle
    └── src/
        ├── main/
        │   ├── java/demo/resource/
        │   │   ├── ResourceApplication.java
        │   │   ├── SecurityConfig.java
        │   │   └── ReportController.java
        │   └── resources/application.yml
        └── test/java/demo/resource/
            └── HeaderSpoofingTests.java
~~~

Demo local dùng `localhost:8080` và `localhost:8090` để dễ quan sát. **Đây không phải production network boundary**. Production phải đặt resource-service sau private service/network ACL; backend không reachable từ Internet.

## 8. Gateway: loại header identity do client tự gửi

### 8.1. Gradle build

`gateway/settings.gradle`:

~~~groovy
rootProject.name = 'gateway'
~~~

`gateway/build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2023.0.6'
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Cloud 2023.0.6 quản lý Spring Cloud Gateway 4.1.x và tương thích Boot 3.3.13 trong ví dụ. Không trộn Spring Cloud Gateway MVC starter với reactive Gateway ở đây.

### 8.2. GatewayApplication

`gateway/src/main/java/demo/gateway/GatewayApplication.java`:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

### 8.3. Gateway application.yml

`gateway/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: resource-api
          uri: http://127.0.0.1:8090
          predicates:
            - Path=/api/**
          filters:
            - RemoveRequestHeader=X-User-Id
            - RemoveRequestHeader=X-Roles
            - RemoveRequestHeader=X-User-Roles
            - RemoveRequestHeader=X-Tenant-Id
            - RemoveRequestHeader=X-Authenticated-User
            - RemoveRequestHeader=X-Auth-Request-User
            - RemoveRequestHeader=X-Principal
            - RemoveRequestHeader=X-Forwarded-User
            - RemoveRequestHeader=X-Organization-Id
~~~

Những điểm quan trọng:
1. Route `/api/**` forward tới downstream trên port 8090, giữ path tương ứng. Không dùng `StripPrefix` trong ví dụ.
2. `RemoveRequestHeader` xóa các header có tên trong cấu hình **trước khi gửi xuống backend**.
3. Header `Authorization` **không bị strip** vì downstream cần Bearer JWT để xác thực. Cấu hình gateway ở đây không giải mã JWT.
4. **Gateway này chỉ minh họa forwarding + sanitization, không tự là authentication gate**. Resource-service vẫn phải verify token, không tin vì request đi qua gateway.
5. Các header tên khác do tổ chức dùng (legacy identity, service mesh assertions, custom groups) phải được bổ sung vào gateway policy hoặc chuyển sang allowlist header forwarding.
6. Chỉ cấu hình route không thay firewall; trong production, chặn toàn bộ direct-to-backend bypass.
7. Proxy/LB trước gateway phải xử lý riêng `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host` và TLS termination. Đừng nhầm chúng với user identity.
8. Nếu gateway route tới nhiều services, filter phải áp tất cả nơi có thể nhận identity header, không chỉ `resource-api`.

**Cảnh báo kiến trúc:** Một số hệ thống có pre-auth service ghi header `X-Authenticated-User` sau khi xác minh JWT. Nếu service đó ở **sau** gateway và dùng cùng tên header, phải xác định filter chạy trước/ sau authentication và nơi chỉ một trusted component có quyền đặt header. Demo không tạo identity headers nên không có vấn đề precedence này.

## 9. Resource Service: luôn tạo Authentication từ JWT đã được kiểm

### 9.1. Gradle build

`resource-service/settings.gradle`:

~~~groovy
rootProject.name = 'resource-service'
~~~

`resource-service/build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-oauth2-resource-server` kéo các thành phần Resource Server và JOSE/JWT. Không dùng `spring-boot-starter-web` Servlet nếu mã Security dựa trên `ServerHttpSecurity` reactive.

### 9.2. application.yml

`resource-service/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8090

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/lab
          jwk-set-uri: https://issuer.example.test/realms/lab/jwks
          audiences:
            - report-api
~~~

Các URL `example.test` là **placeholder kiến trúc** cho AS/JWKS; không thể đăng nhập thật nếu chưa thay bằng provider đáng tin. Khi production:
- `iss` phải đúng issuer của access token.
- `aud` phải chứa `report-api`.
- JWK Set URI phải do trusted IdP cung cấp và chạy qua HTTPS hợp lệ.
- Decoder kiểm chữ ký, thuật toán và thời gian; chỉ nhận allowed algorithms.
- Nếu tự tạo `ReactiveJwtDecoder` custom, phải duy trì issuer/audience validators; cấu hình Boot không tự áp lên bean custom theo mọi trường hợp.
- Không coi OIDC ID Token (thường audience là OAuth client) là access token cho API.

### 9.3. Main

`resource-service/src/main/java/demo/resource/ResourceApplication.java`:

~~~java
package demo.resource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig: scope là từ JWT, không phải header

`resource-service/src/main/java/demo/resource/SecurityConfig.java`:

~~~java
package demo.resource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .pathMatchers(HttpMethod.GET,
                    "/api/tenants/*/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_admin")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

- `oauth2ResourceServer(...).jwt(...)` xác thực Bearer JWT. Không có filter nào trong code đọc `X-User-Id`, `X-Tenant-Id` hoặc `X-User-Roles` để cấp quyền.
- Spring Security mặc định map `scope`/`scp` thành authorities `SCOPE_*`.
- `/api/admin` yêu cầu scope `admin` trong **token đã xác minh**, không bị tác động bởi header `X-User-Roles: ADMIN`.
- `/api/tenants/*/reports` cần scope `reports.read` nhưng còn phải kiểm tenant trong controller/service.
- `anyExchange().denyAll()` làm mặc định đóng.
- HTTP Basic/form login tắt vì demo chỉ dùng Bearer.
- Demo chỉ có safe-method GET nên không cần thay CSRF mặc định; nếu thêm unsafe methods, phải đánh giá credential và CSRF theo threat model.

### 9.5. Controller: tenant từ URL phải khớp verified token

`resource-service/src/main/java/demo/resource/ReportController.java`:

~~~java
package demo.resource;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/whoami")
    Mono<Map<String, String>> whoami(
            @AuthenticationPrincipal Jwt jwt) {

        String tenant = jwt.getClaimAsString("tenant_id");

        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString(),
            "tenant", tenant == null ? "" : tenant
        ));
    }

    @GetMapping("/api/tenants/{tenantId}/reports")
    Mono<Map<String, Object>> reports(
            @PathVariable String tenantId,
            @AuthenticationPrincipal Jwt jwt) {

        String tokenTenant = jwt.getClaimAsString("tenant_id");

        // JWT đã verify trước khi @AuthenticationPrincipal được cấp.
        // Không có đọc X-Tenant-Id hoặc X-User-Roles.
        if (!tenantId.equals(tokenTenant)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Tenant mismatch"));
        }

        Map<String, Object> result = Map.of(
            "tenant", tenantId,
            "subject", jwt.getSubject(),
            "reports", List.of("report-1", "report-2")
        );

        return Mono.just(result);
    }

    @GetMapping("/api/admin")
    Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("status", "admin scope granted"));
    }
}
~~~

**Đặc biệt:** `@AuthenticationPrincipal Jwt` chỉ xuất hiện khi Spring Security đã tạo Authentication hợp lệ. Không parse raw header `Authorization` trong controller để lấy `sub`. Route không dùng `X-Tenant-Id` như authority.

Đoạn kiểm `tenantId.equals(tokenTenant)` là **rule tối thiểu của demo với token single-tenant**. Production thường cần:
- Membership local user ↔ tenant trong DB.
- Kiểm owner/ACL của từng report.
- Tenant ID trong URL/host/claim được chuẩn hóa theo contract và kiểm nonempty.
- Nếu token chứa nhiều tenants, membership check thay vì chỉ equality.
- Không để attacker đổi `tenant_id` qua một request header.
- Không cấp global admin role theo một user ID do client gửi.

## 10. Kiểm thử bằng WebTestClient với RSA-signed JWT thật

**Vì sao không chỉ dùng `mockJwt()`?** Khi test dùng `mockJwt()`, Spring Security Test có thể tạo sẵn `Authentication` và authorities mà không gọi decoder; một test như vậy có thể bỏ qua toàn bộ signature/issuer/audience checks. Bài này dùng JWT ký thật để kiểm đường authentication.

Test-only setup:
- Sinh RSA keypair mới trong JVM test.
- Ký JWT bằng `NimbusJwtEncoder` với private key **chỉ nằm trong test**.
- Cấu hình `NimbusReactiveJwtDecoder` với public key tương ứng.
- Thêm validator issuer và audience `report-api`.
- Gửi Bearer string vào `WebTestClient` bound tới WebFlux application context.
- Kiểm request có forged identity headers **không thay principal, role hoặc tenant**.

Không cần IdP thực khi chạy unit/integration tests, nhưng JWKS HTTP retrieval, proxy network isolation và Gateway filter behavior phải có kiểm thử triển khai riêng.

### 10.1. HeaderSpoofingTests.java

`resource-service/src/test/java/demo/resource/HeaderSpoofingTests.java`:

~~~java
package demo.resource;

import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(HeaderSpoofingTests.LocalJwtKeys.class)
class HeaderSpoofingTests {

    private static final String ISSUER =
        "https://issuer.example.test/realms/lab";

    @Autowired
    ApplicationContext context;

    @Autowired
    JwtEncoder encoder;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalJwtKeys {

        @Bean
        KeyPair keyPair() {
            try {
                KeyPairGenerator gen =
                    KeyPairGenerator.getInstance("RSA");
                gen.initialize(2048);
                return gen.generateKeyPair();
            }
            catch (GeneralSecurityException ex) {
                throw new IllegalStateException(ex);
            }
        }

        @Bean
        JwtEncoder testJwtEncoder(KeyPair keys) {
            RSAKey rsa = new RSAKey.Builder(
                (RSAPublicKey) keys.getPublic())
                .privateKey((RSAPrivateKey) keys.getPrivate())
                .keyID("test-key")
                .build();

            return new NimbusJwtEncoder(
                new ImmutableJWKSet<SecurityContext>(
                    new JWKSet(rsa)));
        }

        @Bean
        ReactiveJwtDecoder testJwtDecoder(KeyPair keys) {
            NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withPublicKey(
                    (RSAPublicKey) keys.getPublic())
                    .build();

            OAuth2TokenValidator<Jwt> audience =
                jwt -> jwt.getAudience().contains("report-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Wrong audience",
                            null));

            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(ISSUER),
                    audience));

            return decoder;
        }
    }

    String signedToken(
            JwtEncoder signer,
            String issuer,
            String audience,
            String subject,
            String tenant,
            String scopes,
            Instant expiresAt) {

        Instant now = Instant.now();

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject(subject)
            .audience(List.of(audience))
            .issuedAt(now.minusSeconds(10))
            .notBefore(now.minusSeconds(10))
            .expiresAt(expiresAt)
            .claim("tenant_id", tenant)
            .claim("scope", scopes)
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return signer.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    String aliceTenantA() {
        return signedToken(
            encoder, ISSUER, "report-api",
            "alice-sub", "tenant-a", "reports.read",
            Instant.now().plusSeconds(600));
    }

    @Test
    void publicHealthDoesNotRequireBearer() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void noBearerCannotBecomeAliceByUserHeader() {
        client.get().uri("/api/whoami")
            .header("X-User-Id", "alice-sub")
            .header("X-Authenticated-User", "alice-sub")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void noBearerCannotBecomeAdminByRoleHeader() {
        client.get().uri("/api/admin")
            .header("X-User-Roles", "ROLE_ADMIN")
            .header("X-Roles", "ADMIN")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validJwtDefinesPrincipalNotSpoofedHeaders() {
        client.get().uri("/api/whoami")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .header("X-User-Id", "ceo-sub")
            .header("X-Authenticated-User", "ceo-sub")
            .header("X-Tenant-Id", "tenant-victim")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice-sub")
            .jsonPath("$.tenant").isEqualTo("tenant-a")
            .jsonPath("$.issuer").isEqualTo(ISSUER);
    }

    @Test
    void spoofedRoleCannotGrantAdminWithoutScope() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .header("X-User-Roles", "ROLE_ADMIN")
            .header("X-Roles", "ADMIN")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void matchingTokenTenantCanReadReports() {
        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("tenant-a")
            .jsonPath("$.subject").isEqualTo("alice-sub")
            .jsonPath("$.reports[0]").isEqualTo("report-1");
    }

    @Test
    void tenantBPathCannotBeAuthorizedByHeaderTenantB() {
        client.get().uri("/api/tenants/tenant-b/reports")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .header("X-Tenant-Id", "tenant-b")
            .header("X-User-Roles", "OWNER")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void headerTenantAStillCannotOverrideTenantBPath() {
        client.get().uri("/api/tenants/tenant-b/reports")
            .headers(h -> h.setBearerAuth(aliceTenantA()))
            .header("X-Tenant-Id", "tenant-a")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tenantSpecificTokenOfBobCannotClaimAliceTenant() {
        String bobTenantB = signedToken(
            encoder, ISSUER, "report-api",
            "bob-sub", "tenant-b", "reports.read",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(bobTenantB))
            .header("X-User-Id", "alice-sub")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validJwtWithoutReportScopeIsForbidden() {
        String token = signedToken(
            encoder, ISSUER, "report-api",
            "alice-sub", "tenant-a", "profile",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void malformedBearerWithAdminHeadersIsUnauthorized() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("not.a.valid.jwt"))
            .header("X-User-Roles", "ROLE_ADMIN")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongIssuerIsUnauthorizedEvenWithUserHeaders() {
        String token = signedToken(
            encoder, "https://evil.example", "report-api",
            "ceo-sub", "tenant-a", "reports.read",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(token))
            .header("X-User-Id", "ceo-sub")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIsUnauthorized() {
        String token = signedToken(
            encoder, ISSUER, "unrelated-api",
            "alice-sub", "tenant-a", "reports.read",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredJwtIsUnauthorized() {
        String token = signedToken(
            encoder, ISSUER, "report-api",
            "alice-sub", "tenant-a", "reports.read",
            Instant.now().minusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void jwtFromUntrustedSigningKeyIsUnauthorized() {
        KeyPair other;
        try {
            KeyPairGenerator gen =
                KeyPairGenerator.getInstance("RSA");
            gen.initialize(2048);
            other = gen.generateKeyPair();
        }
        catch (GeneralSecurityException ex) {
            throw new IllegalStateException(ex);
        }

        RSAKey jwk = new RSAKey.Builder(
            (RSAPublicKey) other.getPublic())
            .privateKey((RSAPrivateKey) other.getPrivate())
            .keyID("test-key")
            .build();

        JwtEncoder attackerEncoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<SecurityContext>(
                new JWKSet(jwk)));

        String forged = signedToken(
            attackerEncoder, ISSUER, "report-api",
            "ceo-sub", "tenant-a", "reports.read",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/tenants/tenant-a/reports")
            .headers(h -> h.setBearerAuth(forged))
            .header("X-User-Roles", "ROLE_ADMIN")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

### 10.2. Test matrix — những trường hợp phải phân biệt

| Trường hợp | Credential/Header | Kỳ vọng |
| --- | --- | --- |
| Public health | Không có token | **200** |
| Chỉ `X-User-Id=alice` | Không token | **401** |
| Chỉ `X-User-Roles=ROLE_ADMIN` | Không token | **401** |
| JWT Alice tenant-a + fake X-User-Id=CEO | Token đúng, header giả | **200** ở whoami nhưng subject vẫn Alice |
| JWT Alice scope read + fake ADMIN role | Token đúng, header giả | **403** ở admin |
| JWT Alice tenant-a → tenant-a URL | Scope read đúng | **200** |
| JWT Alice tenant-a → tenant-b URL, header tenant-b | Cross-tenant | **403** |
| JWT Alice tenant-a → tenant-b URL, header tenant-a | Header không đổi URL ownership | **403** |
| JWT Bob tenant-b → tenant-a URL, fake X-User-Id Alice | Cross-tenant | **403** |
| JWT hợp lệ thiếu reports.read scope | Không đủ capability | **403** |
| Bearer malformed + fake ADMIN headers | Token không hợp lệ | **401** |
| JWT issuer sai + fake X-User-Id | Issuer validation | **401** |
| JWT audience sai | Wrong `aud` | **401** |
| JWT hết hạn | Expired | **401** |
| Token ký bởi key attacker | Signature mismatch | **401** |

Có **15 phương thức test**. Chúng kiểm rằng downstream không tin user/role/tenant headers, JWT phải được verify, scope và tenant phải hợp lệ.

### 10.3. Giới hạn của bộ test

**Các test ở trên là tests của resource-service, không test route Gateway thực tế.** Chúng chứng minh dù header spoof tới được backend, backend vẫn không dùng nó để tạo quyền. Nhưng chúng chưa chứng minh:
- Gateway strip headers trước khi gửi downstream (cần gateway E2E với echo/stub upstream).
- Network firewall chặn bypass trực tiếp.
- TLS/mTLS đã đúng.
- JWKS HTTP retrieval/rotation và issuer discovery ngoài mạng.
- Tenant membership database/owner check thực tế.
- Gateway không vô tình forward Bearer token tới route lạ.
- Kết quả chống header duplication qua các proxy/libraries trong deployment.

**Production phải có E2E kiểm toàn bộ chuỗi**, không suy ra từ test controller.

## 11. Chạy hai ứng dụng và thử với curl

Cài JDK 17+, Gradle 8.x. Từ mỗi thư mục project:

~~~bash
# Terminal A: downstream
cd resource-service
gradle bootRun
~~~

~~~bash
# Terminal B: gateway
cd gateway
gradle bootRun
~~~

Trong ví dụ local, `resource-service` dùng port `8090`, Gateway dùng `8080`. Do issuer `example.test` chỉ là placeholder, **không có JWT production hợp lệ để dùng** trừ khi bạn cấu hình AS thật. Test ở mục 10 tự tạo keypair nên chạy offline:

~~~bash
cd resource-service
gradle test
~~~

Nếu có Gradle Wrapper, dùng `./gradlew test` trên Unix/macOS hoặc `gradlew.bat test` trên Windows.

### 11.1. Chỉ có header giả, không có token

~~~bash
curl -i \
  -H "X-User-Id: admin" \
  -H "X-User-Roles: ROLE_ADMIN" \
  http://localhost:8080/api/admin
~~~

Kỳ vọng downstream trả **401 Unauthorized**, không phải 200, vì không có Bearer JWT được chấp nhận.

### 11.2. Header tenant tự khai không đổi quyền

~~~bash
curl -i \
  -H "X-User-Id: ceo" \
  -H "X-Tenant-Id: tenant-b" \
  -H "Authorization: Bearer ACCESS_TOKEN_ALICE_TENANT_A" \
  http://localhost:8080/api/tenants/tenant-b/reports
~~~

`ACCESS_TOKEN_ALICE_TENANT_A` là **placeholder**, không phải JWT hợp lệ. Với một **token thật** được issuer tin cậy cấp cho Alice tenant-a và có scope reports.read, response phải là **403** theo contract demo, vì path yêu cầu tenant-b. Với placeholder này, request thực tế nhận **401** vì token không xác minh được.

**Không đưa token thật vào tài liệu công khai, shell history hoặc log.** Dùng HTTPS ngoài local, tooling bảo vệ secrets, và token audience đúng với service.

### 11.3. Test bảo mật với direct backend trong môi trường lab

Dùng request giả mạo identity headers tới `http://localhost:8090/api/whoami` **không token**:

~~~bash
curl -i \
  -H "X-Authenticated-User: ceo" \
  -H "X-User-Roles: ROLE_ADMIN" \
  http://localhost:8090/api/whoami
~~~

Kỳ vọng **401**. Điều này minh họa downstream không tự tin headers; nhưng production vẫn phải **chặn public access tới 8090** bằng firewall/private networking.

### 11.4. Test Gateway strip headers end-to-end như thế nào?

Để chứng minh `RemoveRequestHeader` chạy đúng (khác với test downstream bỏ qua headers):
1. Dựng một **stub upstream chỉ trong môi trường test** trả lại có kiểm soát danh sách header names nhận được; không bật header-echo endpoint công khai trong production.
2. Cấu hình route Gateway test trỏ tới stub đó.
3. Gửi request ngoài Gateway chứa `X-User-Id`, `X-User-Roles`, `X-Tenant-Id` ở nhiều kiểu chữ hoa/thường và header trùng.
4. Assert stub **không** nhận các header đã strip.
5. Assert stub vẫn nhận `Authorization` chỉ với routes có quyền nhận Bearer, không forward sang unrelated service.
6. Thử bỏ một `RemoveRequestHeader` trong môi trường test để kiểm positive/negative behavior.
7. Chứng minh firewall/NetworkPolicy chặn direct backend từ mạng client.
8. Lặp tests khi thêm gateway route, auth proxy mới hoặc đổi Spring Cloud version.

Không sử dụng public header-echo endpoint để debug trực tiếp credentials. Logs test phải che Bearer token, cookie và dữ liệu cá nhân.

## 12. Header spoofing và các biến thể cần xử lý ở gateway

### 12.1. Header name, case, multiple values và value normalization

Các biến thể:

~~~http
X-User-Id: alice
x-user-id: ceo
X-User-Roles: AUDITOR,ADMIN
X-User-Roles: OWNER
X-Tenant-Id: tenant-a
X-Tenant-Id: tenant-b
~~~

Phòng vệ:
- Dùng thư viện HTTP đúng semantics case-insensitive.
- Quy định một schema duy nhất cho identity assertions nội bộ.
- Reject ambiguous duplicates ở nơi assertions được tiếp nhận.
- Không dùng raw `getFirst()` để tin "phần tử đầu do gateway thêm".
- Gateway nên strip tất cả client-provided identity headers trước khi thêm assertion có kiểm soát.
- Nếu có sự khác biệt HTTP/1.1 ↔ HTTP/2 ↔ proxy normalization, test tại chuỗi proxy thực tế.

### 12.2. Header injection qua proxy/sidecar trước Gateway

Nếu WAF/CDN/Ingress chuyển request có `X-Authenticated-User` giả tới Gateway, Gateway phải strip trước khi route. Nếu một auth proxy khác *thêm* user header sau này, cần xác định chính xác nơi có quyền set và nơi chỉ có quyền consume.

Không nên để nhiều tầng đều “append” identity headers vì downstream có thể chọn sai giá trị. Những header như `X-Auth-Request-User` chỉ có ý nghĩa khi đã qua auth proxy đáng tin và được nhận diện theo network/protocol contract.

### 12.3. `X-Forwarded-*` là network metadata, không phải người dùng

`X-Forwarded-For: 127.0.0.1` không chứng minh client là admin nội bộ. `Forwarded: proto=https;host=...` không chứng minh identity, dù framework dùng để tạo public URLs. Edge phải sanitize những metadata này bằng trusted hop policy; không tự dùng chúng làm security authority.

### 12.4. `Host`, `X-Original-URL`, method override và route lệch

Một số reverse proxies có cơ chế rewrite URL/Host/method dựa trên headers. Nếu gateway kiểm authorization trên một path nhưng backend nhận path khác, attacker có thể thử bypass. Cần:
- Host allowlist ở edge.
- Canonicalize path/encoding một cách nhất quán giữa proxy và backend.
- Không chấp nhận `X-Original-URL`, `X-Rewrite-URL`, `X-HTTP-Method-Override` tùy ý trừ khi kiến trúc yêu cầu và đã sanitize.
- Authorization ở downstream cho resource thật, không chỉ gateway matcher.
- Không tạo tenant từ raw Host mà không validate mapping.

### 12.5. Không dùng CORS để thay authentication

CORS là chính sách browser cross-origin, không phải API authentication. Một client như curl/mobile có thể gửi `X-User-Roles` dù browser CORS chặn header tương ứng. Vì vậy:
- CORS allowlist không ngăn header spoof từ non-browser clients.
- CSRF là rủi ro riêng với ambient browser credentials; đừng tắt CSRF toàn app chỉ vì dùng gateway.
- OAuth2 Bearer JWT validation và authorization mới quyết định quyền truy cập API.
- Rate limiting/IP allowlist là defense in depth, không thay identity.

## 13. Thiết kế multi-tenant authorization đúng lớp

Một Resource Server có thể cần ba điều kiện:

~~~text
Authentication:
  Verified JWT:
    (issuer, subject)
    audience matches report-api
    exp/nbf valid
    scopes include reports.read

Tenant authorization:
  Local mapping (issuer,subject) → localUserId
  Local membership ACTIVE for requested tenant

Object authorization:
  Report belongs to requested tenant
  Local user can read this report
~~~

Điều kiện tổng:

~~~text
ALLOW_READ_REPORT =
    signed access token valid
AND token has SCOPE_reports.read
AND local identity ACTIVE
AND membership active for requested tenant
AND report.tenant_id = requested tenant
AND report ACL/owner permits action
~~~

Một gateway route có thể thêm coarse authorization (như yêu cầu login trước route), nhưng downstream cần enforce policy cuối cùng, đặc biệt khi có resource IDs và dữ liệu riêng.

### 13.1. Không dùng query parameter làm "quyền"

~~~http
GET /api/reports/123?tenantId=tenant-admin
X-Tenant-Id: tenant-admin
~~~

`tenantId` trong query chỉ là yêu cầu của client. Không được dùng nó làm bằng chứng user thuộc tenant đó. Nếu query repository bằng tenant ID do client tự gửi, phải kiểm membership và row-level predicates ở backend.

### 13.2. Không thay user identity bằng email

Một JWT `email=ceo@company.example` không tự cho quyền CEO. Email có thể đổi/tái sử dụng, còn nhiều issuers có thể phát email trùng. Identity key ổn định thường là validated `(iss, sub)` map sang local user UUID. Quyền admin/tenant membership do local policy quản lý.

### 13.3. Tenant ID trong JWT là lời khẳng định của issuer, vẫn cần chính sách

Signed claim `tenant_id=tenant-a` chỉ đáng tin về nguồn nếu:
- Issuer/audience/token purpose đúng.
- IdP/AS có trách nhiệm xác định tenant membership.
- Claim semantics rõ ràng và được đồng bộ với business policy.

Nếu AS chỉ lặp tenant do client yêu cầu mà không kiểm membership, claim signed vẫn không đủ. Backend phải bảo vệ quyền ở data layer. **Chữ ký chứng minh ai đã phát claim, không chứng minh provider đã áp business policy đúng.**

## 14. Nguy cơ "confused deputy" và lateral movement

**Confused deputy:** một trusted gateway/service có quyền gọi backend nhưng làm theo input attacker mà không kiểm quyền của end user. Ví dụ Gateway có mTLS service identity và backend tin mọi request từ Gateway; client bảo gateway gửi `X-Tenant-Id: victim`. Nếu Gateway không kiểm tenant còn backend bỏ qua End User auth, attacker mượn danh tính service để truy cập tenant khác.

Cách giảm:
- Service identity (mTLS) **không** được thay end-user authorization.
- Bind end-user principal và scopes vào token/assertion có verify.
- Có audience hẹp cho từng downstream.
- Kiểm tenant/resource-level ở service.
- Nếu dùng gateway-signed assertion, không cấp scopes vượt token gốc và không lấy user ID từ client header.
- Audit cả external subject, authenticated client/service, tenant và policy decision.

**Lateral movement:** một service ít quyền có thể gọi trực tiếp một backend khác trong cluster nếu backend tin `X-User-Roles=ADMIN`. Phòng vệ bằng NetworkPolicy/service mesh identity, token audience + authorization, zero-trust giữa services và deny-by-default.

## 15. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Khắc phục |
| --- | --- | --- |
| Không token nhưng gửi X-User-Id vẫn 200 | Backend có pre-auth header bypass | Bỏ raw-header trust, verify JWT/assertion |
| Gửi X-User-Roles=ADMIN được quyền admin | Mapper tin client header | Roles từ Authentication/DB policy |
| JWT tenant A truy cập tenant B | Dùng X-Tenant-Id/URL làm quyền | JWT/local membership + object check |
| Gateway strip đúng nhưng backend vẫn bị spoof | Backend reachable direct hoặc route khác không strip | Private network + downstream verify |
| Header viết chữ thường vẫn lọt policy tự viết | Case-sensitive parsing sai | Dùng HTTP header semantics đúng và E2E test |
| Một header lặp nhiều lần gây khác biệt giữa proxy/service | Inconsistent normalization | Reject duplicates/chuẩn hóa ở boundary |
| JWT valid nhưng backend 401 | Issuer/audience/signature/time/alg sai | Decoder/validators/JWKS logs đã lọc |
| JWT valid nhưng backend 403 | Thiếu scope hoặc tenant mismatch | Kiểm SCOPE_ và membership |
| Gateway mất Authorization header | Filter/security middleware đã strip | Kiểm forwarding policy của route |
| Password reset link hướng attacker domain | Tin Host/X-Forwarded-Host | Canonical public URL và proxy sanitize |
| Cookie Secure/HSTS sai sau TLS termination | Scheme public/internal không nhất quán | Forwarded trusted boundary + TLS edge |
| User thuộc tenant A nhưng URL đến tenant B vẫn có data | Query không scope tenant | Repository predicates/row-level security |
| Chỉ test mockJwt thì mọi thứ pass | Mock bypass JWT signature validation | Signed Bearer integration tests |
| IP-based allowlist bị vượt | Tin X-Forwarded-For client gửi | Edge overwrite + trusted proxies |
| Internal assertion được chấp nhận từ client | Chỉ có custom header, không có signature/peer auth | Verify assertion + mTLS + strip external header |
| Auth proxy vừa thêm X-User-Id vừa nhận header cũ | Append/overwrite sai | Clear before set; reject ambiguous values |
| Thay Gateway version rồi filter không chạy | Property path/version khác | Kiểm docs đúng release train và E2E test |

## 16. Bài tập và câu hỏi

**Câu 1.** Client gửi `X-User-Roles: ROLE_ADMIN`. Nó có được cấp role admin không?

**Đáp án:** Không. Header là dữ liệu từ client, không phải signed authentication evidence.

**Câu 2.** Gateway xóa `X-User-Roles` nhưng backend vẫn reachable trực tiếp. An toàn chưa?

**Đáp án:** Chưa. Cần network isolation và downstream không tin raw headers.

**Câu 3.** Khi nào `RemoveRequestHeader=X-User-Id` có hiệu lực?

**Đáp án:** Trên request được route qua gateway tương ứng trước khi gửi xuống upstream; không ảnh hưởng request bypass gateway.

**Câu 4.** Dịch vụ phía sau cần user identity thì lấy từ đâu?

**Đáp án:** Từ `Authentication` đã qua Bearer JWT validation hoặc signed internal assertion được verify, không từ header tự khai.

**Câu 5.** `Authorization: Bearer ...` có tự đáng tin không?

**Đáp án:** Không. Nó là credential được gửi qua HTTP; chỉ đáng tin sau khi decoder kiểm signature, issuer, audience, time, purpose.

**Câu 6.** Có Bearer token của Alice tenant A và header `X-Tenant-Id: tenant B`; được đọc dữ liệu B không?

**Đáp án:** Không chỉ vì header. Phải có membership/tenant authorization hợp lệ.

**Câu 7.** Nếu token của Alice tenant A và URL yêu cầu tenant B, kết quả demo?

**Đáp án:** 403 khi token hợp lệ, có scope nhưng tenant mismatch.

**Câu 8.** Chỉ có user header mà không có Bearer, kết quả demo ở protected endpoint?

**Đáp án:** 401.

**Câu 9.** JWT hợp lệ nhưng không có `reports.read`, kết quả demo?

**Đáp án:** 403 ở route yêu cầu `SCOPE_reports.read`.

**Câu 10.** `X-Forwarded-For: 127.0.0.1` có chứng minh internal admin không?

**Đáp án:** Không. Client có thể giả nếu edge không strip/overwrite.

**Câu 11.** mTLS Gateway → backend có chứng minh end user là CEO không?

**Đáp án:** Không. Nó xác minh service peer, không tự xác minh user identity/tenant permissions.

**Câu 12.** Nếu dùng gateway-signed internal JWT, cần check gì?

**Đáp án:** Signature, issuer, audience target, expiration, algorithm, tenant/scopes/provenance và policy không vượt external token.

**Câu 13.** Có nên cho gateway forward token sang mọi service vì tiện không?

**Đáp án:** Không. Token cần đúng audience/scope; không rò bearer credential tới service không được cấp quyền.

**Câu 14.** Thấy `X-User-Id` trong request controller có nghĩa gateway chưa strip?

**Đáp án:** Có thể: request bypass gateway, route chưa áp filter, hoặc một tầng nội bộ thêm lại. Phải trace pipeline và E2E test.

**Câu 15.** Một issuer chưa tin được phép tự công bố JWKS URL trong JWT không?

**Đáp án:** Không. Trusted issuers và JWKS URLs phải được allowlist/quản trị.

**Câu 16.** Tại sao không dùng tenant từ subdomain làm authorization một mình?

**Đáp án:** Host là routing context có thể bị giả/đổi; user membership cần check riêng.

**Câu 17.** Test `mockJwt()` có kiểm chữ ký RSA thật không?

**Đáp án:** Không. Nó thường bỏ qua decoder; cần Bearer signed-token tests.

**Câu 18.** Vì sao phải test header trùng và khác case?

**Đáp án:** HTTP header names case-insensitive, nhiều proxies/frameworks có thể chọn giá trị khác nhau khi duplicate; dễ tạo bypass nếu tự parse.

**Câu 19.** Dịch vụ A có `ROLE_ADMIN` của tenant A có mặc định được admin tenant B không?

**Đáp án:** Không. Cần tenant-scoped permission và object-level authorization.

**Câu 20.** Đâu là kiểm soát quan trọng nhất?

**Đáp án:** Không trao quyền từ header client tự khai; **xác minh token/assertion ở trust boundary, isolate backend, strip untrusted identity headers và kiểm tenant/resource ownership**.

## 17. Checklist production

### Gateway / Ingress

- [ ] Cổng backend không exposed tới Internet; Kubernetes NetworkPolicy/firewall/security groups hoạt động.
- [ ] Gateway/edge strip mọi client-supplied identity/role headers theo contract (kể cả legacy names).
- [ ] Kiểm HTTP header names case-insensitive và duplicate handling ở chuỗi proxy thực.
- [ ] Chỉ trusted components có quyền tạo internal assertions; signed + short-lived + audience-bound.
- [ ] Không dựa vào tên header hay nguồn private IP để tự cấp user identity.
- [ ] `Forwarded`/`X-Forwarded-*` được sanitize ở edge, không dùng để xác định role.
- [ ] Không forward Authorization tới unrelated downstream; kiểm token audience.
- [ ] TLS/mTLS áp dụng cho các hop phù hợp, không nhầm service identity với end user.
- [ ] Route rewrite/path/Host/HTTP method semantics thống nhất giữa Gateway và backend.
- [ ] E2E tests xác minh remove-header trên routes và chặn bypass.

### Spring Security / Resource Server

- [ ] Dùng `spring-boot-starter-oauth2-resource-server` trong WebFlux service bảo vệ API.
- [ ] `ReactiveJwtDecoder` kiểm signature, issuer, audience, exp/nbf và thuật toán.
- [ ] `SecurityWebFilterChain` dùng `ServerHttpSecurity`, `oauth2ResourceServer().jwt()`.
- [ ] Không lấy user/role từ `ServerHttpRequest.getHeaders()` để bypass Authentication.
- [ ] Scopes/roles từ nguồn trusted, mapping theo allowlist; không auto cấp ADMIN.
- [ ] Rule mặc định deny, protected routes kiểm Bearer.
- [ ] Authentication và object/tenant authorization được phân tách.
- [ ] `(iss,sub)` map sang local user ID ổn định khi cần, không email.
- [ ] Account status/membership/revocation policy xác định rõ khi JWT chưa hết hạn.
- [ ] Không dùng signed role của tenant A làm global admin cho tenant B.
- [ ] Đảm bảo resources queries có tenant/owner predicates.
- [ ] Không log raw JWT, secret keys, session cookies hoặc PII nhạy cảm.

### QA / Monitoring

- [ ] Header-only không token → 401.
- [ ] JWT Alice + forged X-User-Id Bob → principal vẫn Alice.
- [ ] JWT read + forged admin header → admin endpoint 403.
- [ ] JWT tenant A + URL tenant B/header tenant B → 403.
- [ ] JWT hợp lệ đúng tenant và scope → 200.
- [ ] JWT thiếu scope → 403.
- [ ] JWT sai signature/issuer/audience/expired → 401.
- [ ] Có tests riêng cho Gateway stripping, network bypass và JWT verification.
- [ ] Xác minh chính sách proxy/header sau mỗi nâng cấp Gateway/version.
- [ ] Có audit/alerts cho header spoofing attempts, backend direct access, failed JWT verification và cross-tenant attempts.

## 18. Tài liệu tham khảo

- Spring Cloud Gateway 4.1 — RemoveRequestHeader GatewayFilter: https://docs.spring.io/spring-cloud-gateway/reference/4.1/spring-cloud-gateway/gatewayfilter-factories/removerequestheader-factory.html
- Spring Cloud 2023.0 release train (tương thích Boot 3.3): https://docs.spring.io/spring-cloud-release/reference/2023.0/index.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Testing Reactive OAuth2: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Boot 3.3 — OAuth2 Resource Server issuer/audience properties: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Framework — Forwarded Headers and trusted proxy boundary: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html#webflux-forwarded-headers
- RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — API Security Broken Object Level Authorization (BOLA): https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/

**Ghi nhớ:** `X-User-Id`, `X-User-Roles`, `X-Tenant-Id` và những header “trông giống nội bộ” vẫn là dữ liệu do client có thể tự gửi. Gateway nên **loại bỏ** identity headers không đáng tin; backend phải **xác minh Bearer JWT hoặc signed assertion** và kiểm user/tenant/resource permissions. Network isolation + proxy sanitization + downstream authentication + object-level authorization là những lớp bổ sung cho nhau, không lớp nào thay thế hoàn toàn lớp còn lại.
