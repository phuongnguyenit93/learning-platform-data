# Kiểm tra active, metadata và ánh xạ scope

Trong **Spring Security OAuth 2.0 / OIDC Resource Server** chạy trên **Spring WebFlux**, việc xác thực một **opaque access token** thường được thực hiện bằng cách gửi token đến **Authorization Server** qua endpoint **OAuth 2.0 Token Introspection**. Câu trả lời của Authorization Server không chỉ cho biết token còn hoạt động hay không thông qua trường `active`, mà có thể mang thêm các **metadata** như `scope`, `sub`, `client_id`, `aud`, `iss`, `exp` và các thuộc tính tùy biến. Spring Security dùng những dữ liệu đã được xác nhận này để tạo `OAuth2AuthenticatedPrincipal`, ánh xạ scope thành authorities và xây `Authentication` cho request.

Trong hệ thống reactive, quá trình đó thuộc đường xử lý:

```text
Authorization: Bearer <opaque-access-token>
    |
    v
ServerBearerTokenAuthenticationConverter
    |
    v
AuthenticationWebFilter
    |
    v
Reactive authentication manager cho opaque token
    |
    v
ReactiveOpaqueTokenIntrospector.introspect(token)
    |
    +---- HTTPS POST tới Authorization Server ----+
    |                                             |
    |                      active=true + metadata | active=false / lỗi
    |                                             |
    v                                             v
OAuth2AuthenticatedPrincipal                 TỪ CHỐI XÁC THỰC
    |
    v
BearerTokenAuthentication + SCOPE_* authorities
    |
    v
Reactor SecurityContext
    |
    v
authorizeExchange / reactive method security
    |
    v
Policy tài nguyên: tenant, ownership, trạng thái nghiệp vụ
```

**Mục tiêu của bài:** hiểu chính xác cách đọc và sử dụng `active`, phân biệt các metadata có và không có trong RFC 7662, xác định ranh giới tin cậy của dữ liệu introspection, ánh xạ `scope` thành `GrantedAuthority` trong WebFlux, tùy chỉnh `ReactiveOpaqueTokenIntrospector` an toàn, và kiểm thử riêng **authentication**, **scope authorization** và **business authorization**.

> **Ngữ cảnh ví dụ:** Orders API sử dụng Spring Boot 3.x, Spring Security 6.x và WebFlux. Authorization Server ở `https://login.example.com` có endpoint `https://login.example.com/oauth2/introspect`. Token hợp lệ cho Orders API có resource/audience `orders-api`, scope `orders.read` hoặc `orders.write`, và có thể có `tenant_id`. Tất cả URL, client ID, token và thời điểm trong bài là ví dụ. Những API builder/constructor có thể khác giữa các minor version, vì vậy khi đưa vào dự án cần dùng đúng Javadoc của phiên bản đang có.

## 1. Ba khái niệm phải phân biệt ngay từ đầu

### 1.1. `active` trả lời câu hỏi token có được Authorization Server công nhận không

`active` là một trường **boolean** do RFC 7662 định nghĩa. Với một response hợp lệ:

```json
{
  "active": true
}
```

Authorization Server xác nhận token đang active theo chính sách của nó tại thời điểm introspect, trong phạm vi mà **Resource Server được phép hỏi**.

Nếu:

```json
{
  "active": false
}
```

Resource Server **không được** tạo Authentication hợp lệ từ token đó.

### 1.2. Metadata mô tả token và chủ thể của token

Ví dụ một phản hồi đầy đủ hơn:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "storefront-web",
  "token_type": "Bearer",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "iss": "https://login.example.com",
  "exp": 2000000000,
  "iat": 1999996400,
  "nbf": 1999996400,
  "tenant_id": "tenant-a"
}
```

Các field này có các vai trò khác nhau. Chúng **không phải toàn bộ đều bắt buộc** trong một response RFC 7662, và **không tự có cùng kiểu dữ liệu trong mọi provider** nếu nhà cung cấp sử dụng extensions. Resource Server phải xác định **hợp đồng metadata** với Authorization Server thay vì suy đoán.

### 1.3. Scope là quyền chức năng, không phải quyền trên mọi đối tượng

Từ chuỗi:

```json
{
  "scope": "orders.read orders.write"
}
```

Spring Security thường tạo các authorities:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Điều này giúp API xác định token có được cấp loại hành động **đọc** hoặc **ghi đơn hàng** hay không. Nhưng token có `SCOPE_orders.read` **không mặc nhiên** được phép đọc đơn của tenant hoặc người dùng khác. Scope authorization và object-level authorization là hai bước riêng.

## 2. Vì sao gọi là token introspection?

**RFC 7662 — OAuth 2.0 Token Introspection** mô tả giao diện để một bên được phép hỏi Authorization Server về trạng thái và thuộc tính của token.

Khi API nhận:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_FROM_CALLER
Accept: application/json
```

nó gọi endpoint introspection bằng HTTPS, ví dụ:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic BASE64_INTROSPECTION_ID_COLON_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=ACCESS_TOKEN_FROM_CALLER&token_type_hint=access_token
```

Trong request thứ hai:

- `token` là **token đang cần kiểm tra**.
- `token_type_hint` là **gợi ý tùy chọn**, không phải bằng chứng token thật sự là access token.
- HTTP Basic thể hiện **credential của Resource Server/introspection client**, không phải credential của user đang gọi Orders API.
- Authorization Server xác thực introspection client và áp chính sách cho phép nó đọc thông tin token tương ứng.

### 2.1. Hai client ID không giống nhau

Giả sử Orders API cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Trong môi trường, `ORDERS_INTROSPECTION_CLIENT_ID` có thể là `orders-api-introspector`. Trong response lại có:

```json
{
  "active": true,
  "client_id": "storefront-web"
}
```

| Giá trị | Ý nghĩa |
|---|---|
| `orders-api-introspector` | Identity mà **Orders API** dùng để gọi endpoint introspection |
| `storefront-web` | OAuth client **đã được cấp access token** đang kiểm tra |

Chúng có thể trùng trong một số triển khai, nhưng **không có quy tắc bắt buộc trùng**. Không dùng `client_id` trong response để thay credential introspection hoặc coi nó là ID người dùng cuối.

### 2.2. Introspection không giống JWT local verification

| Khía cạnh | Opaque token + introspection | JWT local verification |
|---|---|---|
| Nguồn trạng thái | Authorization Server trả `active` | JWT signature/claims được kiểm tra cục bộ |
| Kết nối mạng | Thường cần khi introspect, trừ caching có chủ đích | Thường cần metadata/JWKS lúc khởi tạo hoặc refresh khóa |
| Principal | `OAuth2AuthenticatedPrincipal` | `Jwt` |
| Authentication phổ biến | `BearerTokenAuthentication` | `JwtAuthenticationToken` |
| Scope mapping | Từ metadata introspection | Từ claims JWT đã verify |
| Revocation | Có thể phản ánh khi introspect lại | Không tự thu hồi từng JWT trước `exp` nếu chỉ xác minh offline |

Opaque token không có nghĩa **bỏ kiểm tra quyền**. Authorization Server nói token active; Resource Server vẫn quyết định token có được dùng để gọi **Orders API và order cụ thể** hay không.

## 3. `active=true`: cần hiểu chính xác mức cam kết

Một response `active=true` có nghĩa Authorization Server coi token active trong ngữ cảnh introspection. Điều kiện nội bộ có thể gồm token tồn tại, chưa hết hạn, chưa bị thu hồi hoặc các chính sách khác.

Theo RFC 7662, trường `active` là bắt buộc và được dùng để báo trạng thái. Tuy nhiên chi tiết **AS tính active như thế nào** và Resource Server **được nhìn thấy metadata nào** có thể thay đổi theo nhà cung cấp.

**Không suy ra từ `active=true` rằng:**

1. Token chắc chắn dành cho Orders API nếu chưa có audience/resource policy.
2. Token chắc chắn là OAuth **access token**, không phải refresh token hoặc loại token khác.
3. `sub` luôn là end-user ID; token từ `client_credentials` có thể đại diện service.
4. `scope` có quyền trên mọi bản ghi trong hệ thống.
5. Token không bị thu hồi trong tương lai.
6. Tenant membership và role của user không bao giờ đổi.
7. Resource Server không cần kiểm tra issuer/client allowlist hoặc domain authorization.

### 3.1. Các điều kiện nên được thiết kế thành nhiều lớp

Một resource policy minh họa:

```text
ALLOW_READ_ORDER =
    introspection_result.active == true
AND token_type_is_accepted_as_access_token
AND token_was_issued_by_trusted_AS
AND audience_or_resource_contract_is_orders_api
AND token_has_scope("orders.read")
AND actor_is_allowed_to_read_orders
AND actor_tenant == order_tenant
AND (actor_owns_order OR actor_has_explicit_delegation)
```

Đây là **công thức chính sách ứng dụng minh họa**, không phải một biểu thức trong RFC 7662. Một số điều kiện có thể được AS bảo đảm bằng introspection client policy, một số được RS kiểm tra trực tiếp từ metadata và database.

### 3.2. `active` và thời điểm hiện tại

Authorization Server có thể tính `active` dựa trên `exp`, `nbf` và chính sách thu hồi. Nếu hợp đồng RS còn yêu cầu kiểm tra `exp` hoặc tuổi token, cần thực hiện thêm validator thích hợp.

Ví dụ:

```json
{
  "active": true,
  "scope": "orders.read",
  "exp": 2000000000,
  "nbf": 1999996400,
  "iat": 1999996400
}
```

`exp`, `nbf` và `iat` thường có ngữ nghĩa **NumericDate**: số giây tính từ Unix epoch. Không coi số này là milliseconds khi chuyển sang `Instant.ofEpochSecond(...)`. Không dùng clock skew quá rộng chỉ để né sai cấu hình thời gian giữa môi trường.

## 4. `active=false` và fail-closed

Một response không active thường có cấu trúc:

```json
{
  "active": false
}
```

Theo RFC 7662, đối với token không active, Authorization Server thường không trả thông tin nhạy cảm bổ sung. `active=false` không nhất thiết tiết lộ nguyên nhân:

- Token không tồn tại.
- Token đã hết hạn.
- Token đã bị thu hồi.
- Token không được introspection client hiện tại phép biết.
- Token không được chấp nhận theo chính sách của issuer.

**Hệ quả duy nhất cần thiết ở Resource Server:** không tạo một authenticated principal từ token này.

### 4.1. HTTP 200 vẫn có thể là token không hợp lệ

Đây là điểm rất dễ nhầm. Introspection endpoint có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

HTTP `200` cho biết **introspection HTTP request đã được xử lý**; nó **không** bảo đảm bearer token active. Không viết một client tùy chỉnh kiểu:

```java
// CỐ Ý SAI: không dùng logic này để cấp Authentication.
if (introspectionHttpStatus == 200) {
    return authenticatedPrincipalFor(token);
}
```

Thay vào đó, dùng `ReactiveOpaqueTokenIntrospector` tiêu chuẩn hoặc parser nghiêm ngặt kiểm tra `active` là **boolean true** và các điều kiện bổ sung.

### 4.2. HTTP 401 của introspection khác HTTP 401 trả cho API caller

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
```

Từ Authorization Server có thể báo rằng **introspection client-id/client-secret của Resource Server sai**. Đây là lỗi outbound giữa Resource Server và AS, **không phải** bằng chứng user vừa gửi một token hết hạn.

Cần phân loại:

- `active=false`: bearer token không được chấp nhận.
- `401/403` từ introspection endpoint: credential hoặc quyền **Resource Server** có vấn đề.
- `429`/`5xx`/timeout/TLS: dependency không sẵn sàng hoặc network lỗi.
- JSON malformed/`active` thiếu: không có kết quả xác thực hợp lệ.

Tất cả trường hợp chưa đủ bằng chứng phải **fail closed**. Tuy nhiên phản hồi inbound cho client (401 hay 503) và thông báo vận hành phụ thuộc cách ứng dụng map lỗi; không mặc định mọi timeout là `invalid_token`.

## 5. Metadata introspection theo RFC 7662

Một response hợp lệ có thể chứa một số claims được chuẩn hóa. Bảng sau phân biệt **ngữ nghĩa chuẩn** và **việc API cần quyết định**:

| Tên | Ý nghĩa thông thường | Quy tắc sử dụng ở Resource Server |
|---|---|---|
| **`active`** | Trạng thái token, boolean | Phải true mới xem xét xác thực |
| **`scope`** | Các scope được cấp, thường chuỗi cách bằng dấu cách | Tạo authorities theo mapping và kiểm tra endpoint |
| `client_id` | OAuth client được cấp token | Có thể kiểm tra client allowlist; không suy ra end-user |
| `username` | Tên hiển thị của resource owner khi có | Không dùng làm ID bảo mật ổn định nếu hợp đồng không bảo đảm |
| `token_type` | Loại token được AS công bố | Chỉ chấp nhận loại token được API hỗ trợ |
| `exp` | Hạn token hết hiệu lực | Kiểm tra theo chính sách và đánh giá clock |
| `iat` | Thời điểm phát hành | Kiểm tra tuổi token nếu nghiệp vụ yêu cầu |
| `nbf` | Thời điểm token bắt đầu có hiệu lực | Từ chối trước thời điểm hợp lệ theo chính sách |
| `sub` | Subject | Có thể là user hoặc service theo loại grant/profile |
| `aud` | Audience/resource | Ràng buộc token dành cho Orders API |
| `iss` | Issuer | Đối chiếu AS/realm đáng tin nếu được công bố |
| `jti` | Token identifier | Có thể dùng trong audit/revocation policy, bảo vệ PII |
| `tenant_id` | Extension của nhà cung cấp | Chỉ tin nếu AS cam kết, tiếp tục kiểm tra object policy |
| `roles`/`permissions` | Extension tùy nhà cung cấp | Không mặc định map thành quyền admin nếu không có hợp đồng |

Không phải AS nào cũng trả tất cả trường. Resource Server cần thống nhất với AS **field nào bắt buộc**, **field nào có thể thiếu**, **định dạng nào được hỗ trợ**, và **trường nào được phép dùng để phân quyền**.

### 5.1. Metadata phải đến từ đúng nguồn

Giá trị `sub=customer-42` trong **introspection response được nhận qua kênh tin cậy** có ý nghĩa khác với:

```http
X-User: customer-42
X-Tenant: tenant-a
```

do API caller tự gửi. Trường hợp thứ hai **không phải bằng chứng xác thực**. Không dùng header, query parameter, JSON body hay thông tin nằm trong opaque token text để tự tạo principal có quyền.

### 5.2. Không nhầm metadata với danh tính đã được kiểm chứng của user database

`sub` thường là subject do Authorization Server quản lý. Tùy kiến trúc, application user identity có thể được xác định bởi cặp:

```text
(issuer, subject)
```

thay vì chỉ `subject`. Điều này tránh collision khi nhiều issuer/realm phát hành cùng `sub`.

Nếu có tenant, phải xác minh tenant membership và quan hệ subject–tenant theo nguồn tin cậy; một string `tenant_id` có mặt trong introspection response không tự chứng minh actor được truy cập **mọi tài nguyên** trong tenant.

## 6. Metadata có thể thiếu: thiết kế hợp đồng bắt buộc

RFC 7662 không yêu cầu mọi response active đều có `scope`, `aud`, `iss` hoặc `sub`. Nhưng Orders API có thể cần chúng.

Ví dụ API muốn bảo vệ các đơn của từng khách hàng:

```text
Required:
  active = true
  scope includes orders.read / orders.write as appropriate
  aud includes orders-api, OR trusted AS policy equivalent
  iss == https://login.example.com, if issuer is supplied/required
  sub = stable user or service identity according to token class
  tenant_id = nonblank trusted tenant under domain contract
```

Nếu `aud` vắng mặt và ứng dụng yêu cầu phân tách audience, không nên tự giả định token dành cho Orders API. Có hai phương án kiến trúc chính:

1. **AS trả metadata `aud`** và Resource Server kiểm tra.
2. **AS giới hạn introspection client** chỉ được introspect token phù hợp resource này và có hợp đồng được kiểm toán về việc giới hạn đó.

Phương án 2 phải là **đảm bảo thực tế của Authorization Server**, không phải phỏng đoán chỉ vì client ID có tên “orders-api”.

### 6.1. Ví dụ response chỉ có `active=true`

```json
{
  "active": true
}
```

Với một endpoint chỉ cần chứng minh token được AS công nhận, một kiến trúc đặc biệt có thể sử dụng response này. Nhưng với API cần scope/issuer/audience/tenant, metadata đó **không đủ** để chấp nhận hành động. Deny by default thay vì tự cấp `SCOPE_orders.read` cho mọi token active.

### 6.2. Token machine-to-machine khác user token

Một token được cấp theo `client_credentials` có thể trả:

```json
{
  "active": true,
  "client_id": "nightly-reports",
  "sub": "nightly-reports",
  "scope": "orders.export",
  "aud": ["orders-api"],
  "iss": "https://login.example.com"
}
```

`sub` ở đây có thể là service/client identity, không phải customer. Nếu `OrderService` lấy `authentication.getName()` làm customer owner ID, hệ thống có thể dùng sai danh tính. Service account cần **client allowlist, workload scope và tenant/resource policy** riêng.

## 7. `scope`: chuẩn RFC là chuỗi phân cách bằng khoảng trắng

Đối với OAuth scope, một response tiêu biểu:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

`scope` là một chuỗi các token scope được phân cách bằng **space** theo ngữ nghĩa OAuth 2.0. Mỗi scope đại diện một quyền được cấp theo hợp đồng Authorization Server.

Ví dụ:

```text
orders.read
orders.write
orders.cancel
orders.export
```

Chúng là tên quyền chức năng của **Orders API**, không mặc định là role trong database hoặc permission được gán trực tiếp cho từng order.

### 7.1. Scope khác role, permission và ownership

| Khái niệm | Ví dụ | Câu hỏi |
|---|---|---|
| Scope OAuth | `orders.read` | Token được cấp loại thao tác nào? |
| Authority Spring Security | `SCOPE_orders.read` | Spring kiểm tra quyền nào trong Authentication? |
| Role ứng dụng | `ROLE_ORDER_MANAGER` | Actor có vai trò nghiệp vụ gì? |
| Fine-grained permission | `PERMISSION_orders.refund` | Actor được dùng khả năng nào theo policy? |
| Object ownership | Order có owner `customer-42` | Actor được truy cập tài nguyên cụ thể này không? |
| Tenant isolation | `tenant-a` vs `tenant-b` | Actor có quyền qua ranh giới tenant không? |

Một token active có `scope=orders.read` có thể cho phép đọc loại dữ liệu order, nhưng service vẫn cần kiểm tra subject, tenant, resource assignment và trạng thái nghiệp vụ.

### 7.2. Prefix `SCOPE_` là quy ước của Spring Security

Trong một cấu hình Spring Security Resource Server thông thường, response scope:

```text
orders.read orders.write
```

được ánh xạ thành authorities:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Do đó cấu hình WebFlux có thể dùng:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Không dùng `hasRole("orders.read")` một cách mặc định vì `hasRole` áp dụng quy ước `ROLE_`, không tương đương `SCOPE_`.

### 7.3. Định dạng `scp` dạng danh sách có phải mặc định không?

Một số Authorization Server trả extension:

```json
{
  "active": true,
  "scp": ["orders.read", "orders.write"]
}
```

Đây **không phải định dạng `scope` chuỗi chuẩn RFC 7662**. Một số provider/framework có quy tắc riêng, nhưng không được mặc định `ReactiveOpaqueTokenIntrospector` sẽ tự đọc mọi trường `scp` như `scope` trong tất cả versions.

Nếu nhà cung cấp thực sự trả `scp` array, hãy thiết kế **adapter mapping tường minh** hoặc yêu cầu AS trả metadata theo hợp đồng chuẩn. Không dựa vào may mắn rằng authority mapper sẽ hiểu mọi custom field.

## 8. Cách Spring Security ánh xạ metadata thành Authentication

Trong WebFlux, các thành phần liên quan:

| Thành phần | Vai trò |
|---|---|
| `ServerBearerTokenAuthenticationConverter` | Trích Bearer token từ `ServerWebExchange` |
| `AuthenticationWebFilter` | Điều phối xác thực phản ứng |
| Reactive opaque authentication manager | Gọi introspector, tạo Authentication |
| `ReactiveOpaqueTokenIntrospector` | Trả `Mono<OAuth2AuthenticatedPrincipal>` hoặc lỗi |
| `OAuth2AuthenticatedPrincipal` | Chứa thuộc tính và granted authorities từ kết quả introspection |
| `BearerTokenAuthentication` | Authentication đại diện token đã được xác thực |
| `ReactiveSecurityContextHolder` | Cung cấp authentication trong Reactor Context |
| `authorizeExchange` | Kiểm tra scope/role ở HTTP boundary |
| `@EnableReactiveMethodSecurity` | Bảo vệ method/service reactive |
| Domain policy | Kiểm tra quyền theo đối tượng, tenant và business state |

### 8.1. Flow reactive với response active

```mermaid
sequenceDiagram
    autonumber
    participant Caller as API Caller
    participant RS as WebFlux Resource Server
    participant Filter as AuthenticationWebFilter
    participant Introspector as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server
    participant Authz as AuthorizationWebFilter
    Caller->>RS: GET /api/orders/42 + Bearer opaque-token
    RS->>Filter: Exchange
    Filter->>Introspector: introspect(token) -> Mono<Principal>
    Introspector->>AS: POST /oauth2/introspect (HTTPS + client authentication)
    AS-->>Introspector: 200 active=true; scope=orders.read
    Introspector-->>Filter: OAuth2AuthenticatedPrincipal + SCOPE_orders.read
    Filter->>RS: BearerTokenAuthentication trong Reactor Context
    RS->>Authz: Kiểm tra hasAuthority(SCOPE_orders.read)
    Authz->>RS: Allow
    RS->>RS: Service kiểm tra owner, tenant
    RS-->>Caller: 200 hoặc lỗi quyền tài nguyên
```

### 8.2. Reactor Context không phải Servlet ThreadLocal

Trong Spring MVC/Servlet, nhiều đoạn code đọc:

```java
SecurityContextHolder.getContext().getAuthentication();
```

Trong WebFlux, security context được truyền theo **Reactor Context**. Khi cần đọc từ reactive pipeline:

```java
Mono<Authentication> currentActor =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
```

Không gọi `block()` để chờ authentication trên event-loop và không tự `subscribe()` riêng để lấy principal rồi chạy mutation ngoài pipeline. Nếu tự tách subscription, có thể mất context hoặc làm chính sách quyền không có thứ tự rõ ràng.

## 9. Cấu hình WebFlux Resource Server với opaque token

### 9.1. Dependencies

Ví dụ Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Đây là reactive WebFlux stack. Nếu ứng dụng đưa cả Spring MVC và WebFlux vào classpath, phải xác định web application type thực sự được chạy; không sao chép `SecurityFilterChain` của Servlet cho một ứng dụng đang chạy `SecurityWebFilterChain`.

### 9.2. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Hai biến môi trường phải được cấp qua secret manager hoặc cơ chế triển khai an toàn. Không commit client-secret thật; không ghi HTTP Basic Authorization header hoặc body `token=...` vào log.

### 9.3. SecurityWebFilterChain

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class OrdersApiSecurity {

    @Bean
    SecurityWebFilterChain ordersApiChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new BearerTokenServerAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenServerAccessDeniedHandler()
                )
            )
            .build();
    }
}
```

Giải thích:

1. OAuth2 Resource Server DSL cấu hình đường xác thực Bearer opaque token reactive.
2. Introspector truy vấn AS để xác nhận `active` và nhận attributes.
3. `BearerTokenAuthentication` mang principal/authorities trong request.
4. `authorizeExchange` kiểm tra authority `SCOPE_*` theo HTTP method/path.
5. Không cấu hình `oauth2Login` hoặc `formLogin` làm entry point mặc định cho Bearer API.
6. `NoOpServerSecurityContextRepository` tránh lưu authentication trong session; caller cần gửi Bearer trên mỗi request.
7. Service tiếp tục kiểm tra object-level authorization.

**Lưu ý:** ví dụ áp dụng một chain bảo vệ mọi đường dẫn; nếu có API public, Actuator, management endpoints hoặc web login, cần xác định authorization rules và nhiều chains đúng yêu cầu. CSRF cũng phải được thiết kế theo credential model: với pure bearer-only API có thể tắt theo chính sách, nhưng nếu còn cookie/session credentials, phải giữ CSRF protection phù hợp.

### 9.4. Khi dùng JWT thay vì opaque

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults())
)
```

là một đường xác thực **khác** dùng `ReactiveJwtDecoder`. Không bật đồng thời nhiều cơ chế trên cùng Bearer request mà không thiết kế routing/manager rõ ràng. Trong bài này ta chọn **opaque introspection**, không tự decode hoặc phân tích opaque token như JWT.

## 10. `ReactiveOpaqueTokenIntrospector`: hợp đồng cốt lõi

Interface có dạng ý nghĩa:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

- Input `token` là chuỗi Bearer chưa được xác minh.
- Output thành công là `OAuth2AuthenticatedPrincipal` chứa attributes và authorities.
- Token không active hoặc không chấp nhận phải tạo **tín hiệu lỗi xác thực**.
- Lỗi mạng/client authentication/JSON không được trở thành principal hợp lệ.
- Xử lý hoàn toàn theo reactive publisher, không gọi `block()` trong filter/event-loop.

### 10.1. Implementation chuẩn kiểm tra active

Một implementation như `NimbusReactiveOpaqueTokenIntrospector` (trong những phiên bản Spring Security 6.x hỗ trợ) thực hiện HTTP introspection và xử lý phản hồi theo cơ chế Spring Security. Khi `active=false`, nó không trả principal được authenticated như với `active=true`.

Khi chỉ cần cấu hình chuẩn từ `application.yml`, **không cần tự viết parser `active`**. Hãy dùng auto-configuration của Spring Boot và DSL `opaqueToken(...)`.

### 10.2. Tại sao phải cẩn thận khi viết custom introspector?

Khi tự đăng ký bean `ReactiveOpaqueTokenIntrospector`, Spring Boot có thể dùng bean đó thay cho cấu hình mặc định.

Nếu custom introspector làm như sau:

```java
// MÃ CỐ Ý SAI: bỏ toàn bộ xác thực token.
return token -> Mono.just(
    new DefaultOAuth2AuthenticatedPrincipal(
        "somebody",
        Map.of("sub", "somebody"),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.admin"))
    )
);
```

thì **bất kỳ Bearer token** nào cũng được coi là hợp lệ và có quyền admin. Việc trả về `Mono` không làm đoạn code này an toàn.

**Cách phù hợp:** giữ một **delegate introspector chuẩn** để kiểm tra active và nhận metadata; wrapper chỉ bổ sung policy bắt buộc hoặc mapping rõ ràng. Nếu policy không đạt, trả `Mono.error(...)` để filter từ chối.

## 11. Tùy chỉnh introspector để kiểm tra audience

Giả sử Authorization Server phải trả `aud` cho token của Orders API. Ta muốn từ chối token active dành cho Billing API.

### 11.1. Decorator chỉ bổ sung validation, không thay phần introspect

```java
package com.example.orders.security;

import java.util.Collection;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class AudienceCheckingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final String requiredAudience;

    public AudienceCheckingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            String requiredAudience) {
        this.delegate = delegate;
        this.requiredAudience = requiredAudience;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .flatMap(principal -> {
                Object rawAudience = principal.getAttribute("aud");

                boolean matched = false;

                if (rawAudience instanceof String audience) {
                    matched = requiredAudience.equals(audience);
                } else if (rawAudience instanceof Collection<?> audiences) {
                    matched = audiences.contains(requiredAudience);
                }

                if (!matched) {
                    return Mono.error(
                        new BadOpaqueTokenException(
                            "Token audience is not accepted"
                        )
                    );
                }

                return Mono.just(principal);
            });
    }
}
```

Giải thích:

- `delegate.introspect(token)` vẫn có trách nhiệm **HTTP introspection và active checking**.
- Wrapper kiểm tra `aud` của response đã được delegate chấp nhận.
- Nếu `aud` thiếu hoặc không có `orders-api` thì từ chối, **không** suy ra audience từ endpoint URL caller đã gọi.
- Không tạo Authentication mới từ raw token; chỉ trả lại principal đã được AS xác nhận và được policy bổ sung chấp nhận.
- `BadOpaqueTokenException` là một lỗi token phù hợp với cơ chế opaque token, giúp pipeline không biến thất bại policy thành success.

### 11.2. Gắn wrapper vào một bean Spring

Ví dụ dành cho phiên bản Spring Security hỗ trợ `NimbusReactiveOpaqueTokenIntrospector`:

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.oauth2.server.resource.introspection.NimbusReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfiguration {

    @Bean
    ReactiveOpaqueTokenIntrospector reactiveOpaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        ReactiveOpaqueTokenIntrospector delegate =
            new NimbusReactiveOpaqueTokenIntrospector(
                uri,
                clientId,
                clientSecret
            );

        return new AudienceCheckingIntrospector(
            delegate,
            "orders-api"
        );
    }
}
```

**Chú ý phiên bản:** khi dùng bản Spring Security có implementation/builder reactive introspector khác, hãy áp dụng API tương ứng theo Javadoc; điều cốt lõi là **HTTP introspection chuẩn + kiểm tra metadata**. Khi đã đăng ký custom bean, không được mặc định cho rằng tất cả property-based validations khác của Boot vẫn được áp dụng, nhất là những điều kiện do ứng dụng tự thêm.

### 11.3. Giới hạn của ví dụ audience

Decorator trên chỉ kiểm tra `aud`. Hợp đồng thật có thể còn yêu cầu:

- `iss` trùng issuer đã allowlist.
- `token_type` đúng loại bearer access token.
- `client_id` thuộc nhóm OAuth client được phép.
- `sub` phù hợp user hoặc service actor classification.
- `tenant_id` có giá trị hợp lệ.
- `scope` chứa quyền được cấp theo chính sách.
- `exp` và `nbf` hợp lệ, nếu AS cam kết response và RS yêu cầu check thêm.

Không nhất thiết tất cả metadata đều phải được check trong introspector. Có thể chia trách nhiệm giữa authentication, endpoint authorization và service policy; nhưng **không được bỏ sót một ràng buộc thực sự bắt buộc**.

## 12. Ánh xạ scope đúng theo hợp đồng

### 12.1. Hành vi phổ biến của Spring Security

Với response:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

introspector/resource-server support thường ánh xạ hai scope thành `SCOPE_orders.read` và `SCOPE_orders.write` trong principal/Authentication. Các authority này có thể được kiểm tra:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

**Nhưng đừng tự suy đoán mọi metadata extension đều được map**. Nếu AS trả `permissions`/`roles`/`scp` với schema riêng, phải định nghĩa converter cụ thể.

### 12.2. Không map scope thành role toàn hệ thống một cách mù quáng

Ví dụ không nên:

```text
scope = "orders.read admin"
           |
           v
hasRole("ADMIN") allowed across all services
```

Scope `admin` có thể chỉ là quyền nội bộ cho một resource; chuyển thành `ROLE_ADMIN` toàn ứng dụng mà không có hợp đồng sẽ mở quyền ngoài phạm vi dự kiến.

Một quy ước rõ:

```text
OAuth scope           -> SCOPE_orders.read
Application role      -> ROLE_ORDER_MANAGER
Business permission   -> PERMISSION_orders.refund
```

Mỗi namespace nên có policy và nguồn dữ liệu đáng tin riêng.

### 12.3. Scope missing phải được hiểu thế nào?

Nếu metadata:

```json
{
  "active": true,
  "sub": "customer-42"
}
```

thì không tự cấp `SCOPE_orders.read`. Với endpoint yêu cầu `SCOPE_orders.read`, authentication có thể thành công nhưng authorization phải từ chối vì thiếu authority, trừ khi hợp đồng AS–RS dùng một nguồn quyền bổ sung được xác thực khác.

**Không biến “token active” thành “token có mọi scope”.**

## 13. Xử lý scope extension dạng danh sách

Một Authorization Server có thể công bố:

```json
{
  "active": true,
  "scp": ["orders.read", "orders.export"],
  "sub": "customer-42",
  "aud": ["orders-api"]
}
```

Nếu provider không đưa `scope` chuẩn mà chỉ có `scp` extension, một decorator có thể bổ sung authorities từ `scp` theo allowlist.

### 13.1. Hàm ánh xạ có allowlist

```java
package com.example.orders.security;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class OpaqueScopeMapping {

    private static final Set<String> SUPPORTED_SCOPES = Set.of(
        "orders.read",
        "orders.write",
        "orders.export"
    );

    private OpaqueScopeMapping() {}

    public static Collection<GrantedAuthority> mapScp(Object rawScp) {
        if (!(rawScp instanceof Collection<?> source)) {
            return List.of();
        }

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>();

        for (Object item : source) {
            if (!(item instanceof String value)) {
                continue;
            }

            if (SUPPORTED_SCOPES.contains(value)) {
                authorities.add(
                    new SimpleGrantedAuthority("SCOPE_" + value)
                );
            }
        }

        return new ArrayList<>(authorities);
    }
}
```

Đây là một **policy minh họa theo provider contract**. Trong hệ thống thật:

- Chỉ bật mapping `scp` khi issuer được tin cậy thực sự dùng schema này.
- Không tự map mọi chuỗi không giới hạn từ custom claims.
- Định nghĩa hành vi với type sai, giá trị trùng lặp, khoảng trắng hoặc null theo hợp đồng.
- Nếu API yêu cầu scope bắt buộc mà metadata thiếu hoặc sai kiểu, để authorization từ chối hoặc để introspector fail closed theo contract.
- Không cấp các quyền rộng hơn điều đã được Authorization Server công bố.

### 13.2. Bổ sung authorities mà không làm mất scope chuẩn

Một wrapper có thể giữ `principal.getAuthorities()` (đã chứa `SCOPE_*` từ `scope` chuẩn nếu delegate hỗ trợ), sau đó bổ sung scope từ `scp` khi extension được phép.

```java
package com.example.orders.security;

import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class ScpMappingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public ScpMappingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .map(principal -> {
                Set<GrantedAuthority> authorities =
                    new LinkedHashSet<>(
                        principal.getAuthorities()
                    );

                authorities.addAll(
                    OpaqueScopeMapping.mapScp(
                        principal.getAttribute("scp")
                    )
                );

                return new DefaultOAuth2AuthenticatedPrincipal(
                    principal.getName(),
                    principal.getAttributes(),
                    authorities
                );
            });
    }
}
```

**Điểm quan trọng:**

1. Delegate phải đã xác minh token active trước khi wrapper chạy.
2. `principal.getAuthorities()` được giữ lại, tránh vô tình xóa các scope chuẩn mà Spring đã ánh xạ.
3. Chỉ bổ sung `scp` theo allowlist.
4. Không tạo authorities từ claim chưa được AS xác thực hoặc từ request header do user tự gửi.
5. Nếu tên principal thiếu theo schema, ứng dụng cần thiết kế identity validation rõ; không dùng `null` làm user identity hoặc fallback mọi token vào cùng một username mặc định.

### 13.3. Thứ tự decorator

Nếu vừa kiểm tra audience vừa map scope:

```text
NimbusReactiveOpaqueTokenIntrospector
    |
    v
AudienceCheckingIntrospector
    |
    v
ScpMappingIntrospector
    |
    v
OAuth2AuthenticatedPrincipal đã chấp nhận
```

Decorator ngoài cùng chỉ được gọi sau khi delegate bên trong xử lý thành công. Nếu muốn thêm check issuer/expiration, hãy tạo policy decorator tương ứng và quyết định rõ thứ tự/điều kiện. Đừng tự tuyên bố `active=true` trước khi delegate chạy.

## 14. Ánh xạ role/permissions: cần tách chính sách

Không phải mọi metadata `roles`/`permissions` từ Authorization Server đều có thể dùng trực tiếp làm Spring authorities cấp quyền hệ thống.

Ví dụ:

```json
{
  "active": true,
  "scope": "orders.read",
  "roles": ["ORDER_VIEWER"],
  "permissions": ["orders.export"]
}
```

Hệ thống nên quyết định:

| Input metadata | Mapping có thể được phê duyệt | Cần bảo vệ |
|---|---|---|
| `scope=orders.read` | `SCOPE_orders.read` | Scope dành đúng API |
| `roles=["ORDER_VIEWER"]` | `ROLE_ORDER_VIEWER` | Role phải được AS cấp theo đúng tenant/resource contract |
| `permissions=["orders.export"]` | `PERMISSION_orders.export` | Không chuyển mọi permission thành global authority |
| `tenant_id=tenant-a` | Attribute actor | Không chuyển thẳng thành quyền đọc mọi order thuộc tenant-a |
| `client_id=nightly-worker` | Identity client | Không tự coi là user hoặc admin |

Một Authorization Server có thể đóng vai trò Policy Decision Point cho một số quyền; nhưng Resource Server vẫn phải hiểu **ngữ nghĩa và phạm vi** từng trường. Đừng mặc định một role string trong token active có thể vượt mọi domain-level checks.

### 14.1. Vì sao cần mapping riêng cho mỗi issuer/provider?

Hai provider có thể đều trả `roles=["ADMIN"]` nhưng ý nghĩa khác nhau:

- Provider A: `ADMIN` của một ứng dụng cụ thể.
- Provider B: `ADMIN` của realm rộng.
- Provider C: `ADMIN` trong tenant được chọn.

Nếu dùng một converter global tự map thành `ROLE_ADMIN`, rất dễ mở quyền không tương thích. Scope/role mapping phải gắn với **issuer contract, audience, tenant và mức độ tin cậy**.

## 15. Principal trong WebFlux: lấy metadata thế nào?

Sau khi opaque introspection thành công, controller có thể nhận `OAuth2AuthenticatedPrincipal` nếu API đang dùng kiểu principal đó.

```java
package com.example.orders.api;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class CurrentCallerController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {

        String subject = principal.getAttribute("sub");
        String clientId = principal.getAttribute("client_id");

        Map<String, String> response = new LinkedHashMap<>();
        response.put("subject", subject != null ? subject : "unspecified");
        response.put(
            "clientId",
            clientId != null ? clientId : "unspecified"
        );

        return Mono.just(response);
    }
}
```

Đây là endpoint minh họa khi security đã bảo vệ `/api/me`; không mặc định public API nên trả metadata hoặc PII như subject/client ID. Hợp đồng production thường chỉ trả phần dữ liệu tối thiểu cần cho caller.

### 15.1. Đọc Authentication từ Reactor Context

Trong service reactive:

```java
package com.example.orders.security;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public final class ReactiveActorProvider {

    public Mono<Authentication> current() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication is required"
                )
            ));
    }
}
```

Không sử dụng:

```java
SecurityContextHolder.getContext().getAuthentication();
```

như đường lấy identity mặc định ở WebFlux reactive pipeline. Cơ chế ThreadLocal kiểu Servlet không bảo đảm mang context qua `flatMap`/`publishOn`/async callbacks.

### 15.2. Không tự `subscribe()` để lấy subject

Sai:

```java
reactiveActorProvider.current()
    .subscribe(authentication -> {
        // Lưu authentication vào một field dùng chung.
    });
```

Điều này tạo **subscription rời** và có thể làm mất context, mất thứ tự authorization hoặc rò danh tính giữa các request nếu lưu vào singleton field.

Đúng hơn là kết hợp trong pipeline:

```java
public Mono<OrderDto> getOrder(String id) {
    return reactiveActorProvider.current()
        .flatMap(authentication ->
            loadAuthorizedOrder(id, authentication)
        );
}
```

`loadAuthorizedOrder(...)` là operation reactive của application service đã kiểm tra scope và object policy.

## 16. Service phải kiểm tra quyền trên từng tài nguyên

Giả sử introspection trả:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "customer-42",
  "iss": "https://login.example.com",
  "tenant_id": "tenant-a",
  "aud": ["orders-api"]
}
```

Sau khi Spring tạo `SCOPE_orders.read`, request `GET /api/orders/order-9001` có thể đi qua `authorizeExchange`. Nhưng nếu order-9001 thuộc `customer-99` hoặc `tenant-b`, service vẫn phải từ chối.

### 16.1. Mô hình dữ liệu

```java
package com.example.orders.domain;

public record Order(
    String id,
    String tenantId,
    String ownerIssuer,
    String ownerSubject,
    String status
) {}
```

Reactive repository port:

```java
package com.example.orders.domain;

import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository {
    Mono<Order> findByIdAndTenantId(
        String orderId,
        String tenantId
    );
}
```

Cần bảo đảm adapter thực thi điều kiện tenant ngay trong truy vấn, thay vì chỉ đặt tên method rồi bỏ ràng buộc ở SQL.

### 16.2. Service kết hợp authorities và metadata đã được xác thực

```java
package com.example.orders.application;

import com.example.orders.domain.Order;
import com.example.orders.domain.ReactiveOrderRepository;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderQueryService {

    private final ReactiveOrderRepository repository;

    public ReactiveOrderQueryService(
            ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<Order> read(
            String orderId,
            Authentication authentication) {

        if (!authentication.isAuthenticated()) {
            return Mono.error(
                new AccessDeniedException("Not authenticated")
            );
        }

        boolean hasReadScope = authentication.getAuthorities()
            .stream()
            .anyMatch(a ->
                "SCOPE_orders.read".equals(a.getAuthority())
            );

        if (!hasReadScope) {
            return Mono.error(
                new AccessDeniedException("Missing orders.read")
            );
        }

        if (!(authentication.getPrincipal()
                instanceof OAuth2AuthenticatedPrincipal principal)) {
            return Mono.error(
                new AccessDeniedException(
                    "Opaque token principal required"
                )
            );
        }

        String subject = principal.getAttribute("sub");
        String issuer = principal.getAttribute("iss");
        String tenant = principal.getAttribute("tenant_id");

        if (subject == null || subject.isBlank()
                || issuer == null || issuer.isBlank()
                || tenant == null || tenant.isBlank()) {
            return Mono.error(
                new AccessDeniedException("Identity metadata missing")
            );
        }

        return repository.findByIdAndTenantId(orderId, tenant)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                boolean allowed =
                    tenant.equals(order.tenantId())
                    && issuer.equals(order.ownerIssuer())
                    && subject.equals(order.ownerSubject());

                return allowed
                    ? Mono.just(order)
                    : Mono.error(
                        new AccessDeniedException(
                            "Order is not accessible"
                        )
                    );
            });
    }
}
```

`OrderNotFoundException` là một domain exception do ứng dụng tự định nghĩa và mapping ra 404 theo hợp đồng. Ví dụ cũng giả định `iss` và `tenant_id` được AS cung cấp dưới dạng string đã thống nhất; nếu provider trả kiểu khác, cần adapter an toàn thay vì cast mù.

Điểm an toàn:

1. Service không lấy owner từ header hoặc path do caller tự khai.
2. `Authentication` phải hợp lệ và có `SCOPE_orders.read`.
3. Principal được tạo sau introspection, không phải dữ liệu Bearer chưa xác minh.
4. Tenant/issuer/subject được sử dụng theo hợp đồng metadata đã được chấp nhận.
5. Repository lọc theo tenant, service kiểm tra lại owner.
6. Không có quyền thì phát `Mono.error(...)`, không trả dữ liệu.
7. `active=true` không thay được kiểm tra quyền object.

Đoạn này là ví dụ cho **user-owned orders**; token machine-to-machine cần use case và policy riêng thay vì giả định `sub` luôn là customer.

## 17. Method security cho WebFlux

Với reactive method security, có thể bật:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {}
```

Ví dụ:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderDto> getOrder(String id) {
    return repository.findAuthorizedOrder(id);
}
```

Các class `OrderDto`/`repository` là thành phần ứng dụng giả định. Annotation trên service bảo vệ đường gọi qua Spring-managed proxy khi reactive security context có mặt.

Tuy nhiên:

- `@PreAuthorize` kiểm tra scope, không tự biết order thuộc ai.
- Khi service được gọi từ message consumer hoặc scheduler không có HTTP request, không mặc định có Reactor authentication context từ Resource Server.
- Self-invocation trong cùng bean có thể bypass proxy.
- Với mutation, policy object và trạng thái phải được kiểm tra trong transaction/concurrency boundary phù hợp.
- Không dùng `@PostAuthorize` làm lớp bảo vệ duy nhất cho side effect đã xảy ra.

## 18. Dữ liệu metadata thay đổi: cache và revocation

Một ưu điểm của introspection là Authorization Server có thể trả `active=false` sau khi token bị thu hồi. Nhưng điều này phụ thuộc thời điểm RS **thực sự introspect lại**.

### 18.1. Không cache

```text
Request 1 -> AS introspection -> active=true
Request 2 -> AS introspection -> active=true
Admin revokes token
Request 3 -> AS introspection -> active=false
```

Đây là mô hình logic khi không cache và AS phản ánh revocation. Tuy nhiên AS có thể có replication delay hoặc các chính sách nội bộ khác, nên không cam kết tuyệt đối từng mili-giây.

### 18.2. Có cache

```text
Request 1 -> AS -> active=true -> cache 3 minutes
Admin revokes token
Request 2 -> cache hit -> vẫn thấy active=true
Cache expires
Request 3 -> AS -> active=false
```

Caching giúp giảm network/latency nhưng tạo **độ trễ thu hồi**. Những metadata như role, tenant membership và scope cũng có thể bị stale trong thời gian cache.

Một nguyên tắc:

```text
effectiveCacheTTL <= min(
  configuredMaxTTL,
  remainingTokenLifetimeFromExp,
  acceptableRevocationDelay
)
```

Đây là định hướng thiết kế, không phải TTL mặc định của Spring Security. Không mặc định `ReactiveOpaqueTokenIntrospector` tự cache mọi kết quả. Nếu có custom caching decorator, cần giới hạn TTL, kích thước, key, concurrency và tiêu chí invalidation.

### 18.3. Token cache key là dữ liệu nhạy cảm

Opaque token là Bearer credential. Đừng đưa raw token vào log, metric label, trace baggage hoặc cache admin UI. Một cache cần bảo vệ keys/values và tránh lưu token trong những hệ thống không được kiểm soát.

Có thể dùng hash/HMAC key được thiết kế phù hợp để giảm lộ raw token trong key, nhưng đừng coi hashing là đủ nếu nội dung cache hoặc request log vẫn chứa token.

## 19. WebFlux reactive và HTTP introspection

### 19.1. Không dùng HTTP client blocking trên event-loop

Một custom introspector viết như sau là anti-pattern:

```java
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    // CỐ Ý SAI: blocking I/O bên trong reactive path.
    String json = restTemplate.postForObject(
        introspectionUri,
        token,
        String.class
    );

    return Mono.just(buildTrustedPrincipalWithoutValidation(json));
}
```

Vấn đề kép:

- Blocking HTTP call có thể làm nghẽn Netty event loop.
- Tự parse JSON mà không kiểm tra `active`/metadata đầy đủ có thể tạo authentication sai.

Hãy ưu tiên implementation `ReactiveOpaqueTokenIntrospector` chính thức dùng reactive HTTP client phù hợp; nếu cần custom transport, giữ HTTP authentication, TLS, request form, active checking và error semantics.

### 19.2. Timeout và connection pool

Một lời gọi introspection có thể chịu:

- Chờ lấy connection từ pool.
- DNS resolve.
- TCP connect.
- TLS handshake.
- Chờ AS trả HTTP response.
- Đọc/parse JSON.

`responseTimeout` không nhất thiết bao gồm tất cả giai đoạn; muốn giới hạn latency tổng cần một deadline rõ. Nếu AS chậm, requests WebFlux có thể tồn tại lâu trong pipeline dù không giữ nhiều thread; vẫn tốn bộ nhớ, connection pool và in-flight concurrency.

Nên thiết kế:

1. Connect/read/overall timeouts theo SLA.
2. Bounded connection pool và pending acquire limit.
3. Giới hạn concurrency, rate limit và bảo vệ chống DoS.
4. Retry có điều kiện, số lần nhỏ, không retry `active=false`.
5. Circuit breaker **fail closed**, không chuyển thành `active=true`.
6. Telemetry theo outcome/latency/error class, không ghi token/secret.

### 19.3. Một phản hồi 200 malformed phải bị từ chối

Nếu AS hoặc proxy trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":"true"}
```

trường `active` là **string**, không phải boolean theo RFC. Một custom parser nghiêm ngặt không được coi mọi giá trị “truthy” hoặc chuỗi `"true"` là boolean true ngoài hợp đồng. Sử dụng parser/implementation chuẩn hoặc validate schema.

Tương tự response thiếu `active` không phải `active=true` mặc định.

## 20. Lỗi phản hồi Bearer 401 và 403

Phân biệt các lỗi chính:

| Tình huống | Authentication | Phản hồi API thông thường |
|---|---|---|
| Không gửi token tới endpoint bảo vệ | Chưa xác thực | **401**, `WWW-Authenticate: Bearer` |
| Introspection trả `active=false` | Không hợp lệ | **401 invalid_token** |
| Token malformed hoặc không thể cung cấp credential hợp lệ | Không hợp lệ | **400 invalid_request** hoặc 401 theo ngữ cảnh RFC/policy |
| Token active nhưng thiếu `orders.read` | Đã xác thực nhưng không đủ scope | **403 insufficient_scope** |
| Token active/đủ scope nhưng sai owner/tenant | Object policy từ chối | **403** hoặc **404** theo chính sách |
| Introspection client ID/secret sai | Lỗi RS → AS | Fail closed; cần phân loại lỗi dependency |
| AS timeout/5xx/TLS error | Không có kết quả đáng tin | Fail closed; mapping 5xx/503 tùy cấu hình |
| Metadata thiếu `aud` mà API bắt buộc | Token không đạt hợp đồng | Không tạo Authentication được chấp nhận |
| Metadata có kiểu sai | Không đạt schema/policy | Từ chối, không tự “sửa” thành quyền mặc định |

### 20.1. Không redirect API sang trang login HTML

WebFlux Resource Server nhận Bearer token cần phản hồi Bearer challenge theo RFC 6750. Đừng dùng `oauth2Login` hoặc `formLogin` làm entry point mặc định cho API.

`401` trong API thường là tín hiệu để **OAuth client** xử lý access token và thực hiện refresh/login flow đúng vai trò. Resource Server không tự đổi refresh token hoặc redirect máy gọi API tới trang HTML.

### 20.2. Lỗi hệ thống không phải lỗi scope

Nếu AS timeout, không thể biết token active hay có scope gì. Không trả `403 insufficient_scope` chỉ vì không truy cập AS; đó là một tình trạng **không xác thực được** do dependency, không phải thông tin rằng token hợp lệ nhưng thiếu quyền.

Nếu muốn client thấy `503` cho AS outage, cần cấu hình exception handling phù hợp và kiểm thử; Spring không bắt buộc mọi phiên bản/mọi kiểu lỗi đều tự trả 503.

## 21. Kiểm thử scope mapping với WebTestClient

`WebTestClient` phù hợp cho WebFlux. Spring Security Test cung cấp helper tạo một authentication opaque giả để kiểm tra authorization.

Dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

### 21.1. Kiểm tra quyền với `mockOpaqueToken()`

Ví dụ test fragment dùng `WebTestClient` đã bind với Spring Security:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

client.mutateWith(
        mockOpaqueToken()
            .attributes(attrs -> {
                attrs.put("sub", "customer-42");
                attrs.put("tenant_id", "tenant-a");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
    )
    .get()
    .uri("/api/orders/order-42")
    .exchange()
    .expectStatus().isOk();
```

Điều kiện: test có fixture order-42 thuộc customer-42/tenant-a và endpoint đã được cấu hình phù hợp. Nếu domain policy từ chối, test có thể trả 403/404; đó là vấn đề fixture/authorization chứ không chứng minh mock opaque token hoạt động sai.

**Giới hạn quan trọng:** `mockOpaqueToken()` gắn Authentication giả vào test. Nó **không gửi Bearer token thật qua HTTP introspection**, không kiểm tra `active=false` và không chứng minh HTTP Basic credentials/TLS/AS metadata đúng.

### 21.2. Test thiếu scope

```java
client.mutateWith(
        mockOpaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_unrelated")
        )
    )
    .get()
    .uri("/api/orders/order-42")
    .exchange()
    .expectStatus().isForbidden();
```

Test này chứng minh route yêu cầu `SCOPE_orders.read`, không phải kiểm tra thuật toán map từ RFC `scope` string trong phản hồi AS. Muốn kiểm thử mapping thật, cần tích hợp delegate introspector hoặc fake AS.

### 21.3. Test không có token

```java
client.get()
    .uri("/api/orders/order-42")
    .exchange()
    .expectStatus().isUnauthorized();
```

Nên kiểm tra thêm `WWW-Authenticate: Bearer` và không có `Location: /login` nếu ứng dụng có web login chain.

## 22. Integration test với fake Authorization Server

Để kiểm tra **`active`, HTTP metadata và mapping scope thực sự**, cần gửi Bearer header vào filter chain và cấu hình một **fake introspection endpoint** trong môi trường test. Fake AS phải nhận đúng form POST và xác thực introspection client theo phương thức đã đăng ký.

### 22.1. Những tình huống quan trọng

| Test | Fake introspection response | Mong đợi |
|---|---|---|
| Token active, scope read | `200 {"active":true,"scope":"orders.read",...}` | Tạo authentication có `SCOPE_orders.read` |
| Token active, scope read+write | `200 {"active":true,"scope":"orders.read orders.write"}` | Có hai authorities tương ứng |
| Token inactive | `200 {"active":false}` | Không authenticated, Bearer 401 |
| Active không có scope | `200 {"active":true}` | Không tự cấp scope; route yêu cầu scope bị từ chối |
| Active thiếu scope write | `200 {"active":true,"scope":"orders.read"}` | POST yêu cầu write trả 403 |
| Active sai audience | `200 ... "aud":["billing-api"]` | Audience policy/decorator từ chối |
| Active khác issuer | `200 ... "iss":"https://other.example"` | Issuer policy từ chối nếu bắt buộc |
| Active sai tenant/owner | Metadata hợp lệ, resource thuộc actor khác | Service từ chối |
| `active` là string | `200 {"active":"true"}` | Không coi là active hợp lệ |
| `active` thiếu | `200 {"scope":"orders.read"}` | Không có kết quả xác thực hợp lệ |
| `scope` sai kiểu | `200 {"active":true,"scope":42}` | Không tự suy ra `SCOPE_*`; xử lý theo hợp đồng |
| `scp` array extension | `200 ... "scp":["orders.read"]` | Chỉ map khi custom adapter được thiết kế |
| AS trả 401 | Lỗi Basic client authentication | Fail closed, phân loại lỗi cấu hình |
| AS trả 503 | Dependency outage | Fail closed, không cấp principal |
| AS timeout/TLS invalid | Không có response đáng tin | Fail closed, phản ánh lỗi hạ tầng phù hợp |
| M2M token | `client_id=nightly-worker`, `sub` service | Áp client/workload policy, không giả user |

### 22.2. Cách tổ chức test để thật sự đi qua introspection

1. Tạo fake server cục bộ với endpoint POST introspection.
2. Cấu hình `introspection-uri` của test trỏ tới fake server.
3. Cấp test client ID/secret vô hại (không dùng secret production).
4. Gửi HTTP header `Authorization: Bearer TEST_OPAQUE_TOKEN` tới WebTestClient.
5. Để `AuthenticationWebFilter`, manager và `ReactiveOpaqueTokenIntrospector` thực sự chạy.
6. Fake AS trả `active`/metadata theo từng test.
7. Kiểm tra response 401/403/200 và, nếu cần, authorities/principal trong một test handler bảo vệ.
8. Kiểm tra fake AS nhận đúng request `Content-Type: application/x-www-form-urlencoded`, trường `token` và client authentication.
9. Test lỗi timeout, JSON malformed, TLS theo môi trường có kiểm soát.
10. Không log raw test secret/token nếu môi trường chia sẻ log artifact.

Không dùng `mockOpaqueToken()` như bằng chứng đã kiểm tra metadata HTTP thật; helper đó có chủ đích bypass network layer.

### 22.3. Test scope mapping ở cấp introspector

Có thể dùng một **delegate fake** trả một principal test đã được giả định qua active validation, rồi gọi trực tiếp decorator `ScpMappingIntrospector` để kiểm tra custom `scp` extension:

```java
ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
        "customer-42",
        Map.of(
            "sub", "customer-42",
            "scp", List.of("orders.read", "orders.export")
        ),
        List.of()
    ));

ReactiveOpaqueTokenIntrospector mapper =
    new ScpMappingIntrospector(delegate);

StepVerifier.create(mapper.introspect("test-token"))
    .assertNext(principal -> {
        Set<String> names = principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertThat(names).contains(
            "SCOPE_orders.read",
            "SCOPE_orders.export"
        );
    })
    .verifyComplete();
```

Đây là **test fragment**; cần imports `Mono`, `DefaultOAuth2AuthenticatedPrincipal`, `List`, `Map`, `Set`, `Collectors`, `StepVerifier` và assertion library phù hợp.

Nó chỉ kiểm tra **adapter scope mapping**, không xác minh RFC `active` hay HTTP client. Test thật ở cấp fake AS vẫn cần thiết.

## 23. Phân loại lỗi theo tầng để vận hành đúng

Khi một request trả 401/403, cần xác định lỗi xuất hiện ở tầng nào.

| Tầng | Dấu hiệu | Cách chẩn đoán |
|---|---|---|
| HTTP inbound | Không có Bearer token | Kiểm tra request header và security matcher |
| Authentication converter | Bearer header malformed | Kiểm tra cú pháp Bearer theo RFC 6750 |
| Introspection transport | TLS/DNS/connect/timeout | Kiểm tra egress, AS URL, HTTP client |
| Introspection client auth | AS trả HTTP 401/403 | Kiểm tra client ID/secret, permission |
| Token status | AS trả `active=false` | Token không được chấp nhận |
| Metadata schema | `active=true` nhưng thiếu/sai `aud`, `iss`, `scope` | Kiểm tra hợp đồng AS–RS |
| Authority mapping | Principal active nhưng thiếu `SCOPE_*` | Kiểm tra introspector/extension converter |
| Endpoint authz | Scope không đạt `authorizeExchange` | Kiểm tra route/authority policy |
| Method/object authz | Sai owner/tenant/state | Kiểm tra service policy/database |

### 23.1. Không ghi credential vào log để debug

Không ghi:

```text
Authorization: Bearer <raw token>
Authorization: Basic <base64 client-id:secret>
body: token=<raw token>
introspection_response=<full PII claims>
```

Nên ghi mã lỗi, thời gian, endpoint group, AS host được allowlist và request correlation ID. Nếu cần audit subject/client, xác định dữ liệu tối thiểu, thời hạn lưu và chính sách truy cập.

### 23.2. Metrics hữu ích

Có thể đo:

- `introspection.requests` phân theo outcome `active|inactive|error`.
- `introspection.duration` p50/p95/p99.
- `introspection.http.status` và lỗi client authentication.
- `introspection.timeout`/`tls.error`.
- `opaque.scope_mapping.error` khi metadata sai schema.
- `authorization.insufficient_scope`.
- `authorization.object_denied`.
- `connection.pool.active/pending`.
- `cache.hit/miss` và revocation lag nếu có caching decorator.

Tên metrics chỉ là gợi ý. **Không dùng raw token, `sub` hoặc `client_id` tự do của caller làm metric labels**, vì vừa có thể lộ dữ liệu vừa gây cardinality cao.

## 24. Các anti-pattern cần tránh

### 24.1. “HTTP 200 là active”

Sai. Phải kiểm tra boolean `active`. `200 {"active":false}` là token không active.

### 24.2. “Không có active thì mặc định true”

Sai. Một response thiếu `active` không cung cấp bằng chứng token active theo RFC 7662.

### 24.3. “active=true thì cấp quyền admin”

Sai. `active` chỉ xác nhận trạng thái token; scope và quyền domain cần được xác định độc lập.

### 24.4. “scope có mặt thì actor sở hữu mọi order”

Sai. Scope kiểm soát loại hành động, service kiểm tra tenant, ownership, delegation và trạng thái tài nguyên.

### 24.5. “client_id trong response là ID client dùng để introspect”

Sai. `client_id` phản ánh client mà token được cấp; credential introspection thuộc Resource Server.

### 24.6. “sub luôn là user ID”

Sai. Với machine-to-machine, `sub` có thể mang identity của service/client hoặc format riêng theo AS contract.

### 24.7. “Mọi provider trả scope giống nhau”

Sai. RFC 7662 quy định `scope` string; extensions như `scp` array cần converter rõ ràng theo provider.

### 24.8. “Map mọi roles claim thành ROLE_ADMIN”

Sai. Role/permission phải có semantics, issuer/audience/tenant constraints và allowlist.

### 24.9. “Tự tạo DefaultOAuth2AuthenticatedPrincipal khi không gọi AS được”

Sai. Đó là bypass authentication. Khi AS lỗi, phải fail closed hoặc dùng cache đã được phê duyệt với TTL/revocation risk.

### 24.10. “Reactive tức là dùng Mono.just quanh RestTemplate”

Sai. `Mono.just(...)` không biến blocking HTTP I/O thành nonblocking. Phải dùng transport reactive phù hợp.

### 24.11. “Một test mockOpaqueToken đủ để chứng minh active=false”

Sai. Nó tạo principal giả và không đi qua HTTP introspection; cần integration test với fake AS.

### 24.12. “Introspection client có secret nên không cần kiểm tra TLS”

Sai. HTTP Basic/Base64 không bảo mật trên đường truyền; dùng HTTPS và xác minh certificate/hostname.

### 24.13. “Resource Server có thể tùy ý lấy introspection URL từ token”

Sai. Đây là rủi ro SSRF và exfiltration. Introspection URI phải thuộc cấu hình/allowlist tin cậy; không lấy từ header/JWT chưa xác minh.

### 24.14. “Cache active=true mãi mãi để tăng tốc”

Sai. Điều này vô hiệu hóa revocation, có thể giữ scope/role cũ và gây rủi ro token đã hết hạn. TTL phải có giới hạn dựa trên `exp` và chính sách thu hồi.

## 25. Quy trình áp dụng cho một Orders API

### Bước 1 — Thống nhất contract với Authorization Server

Ít nhất cần biết:

- Introspection endpoint chính xác và phương thức client authentication.
- Token types được phép introspect và dùng tại Orders API.
- `active` có được trả boolean theo RFC 7662 không?
- `scope` có dạng chuỗi chuẩn hay provider dùng extension?
- `aud`/`iss` có được trả và mang ngữ nghĩa gì?
- `sub` đại diện user hay service trong từng grant type?
- `tenant_id`/roles/permissions extensions có đáng tin để làm gì?
- Chính sách revoke, token max lifetime, rate limits và caching allowance.
- Những metadata nào introspection client được phép nhìn thấy.

### Bước 2 — Cấu hình HTTPS và client credential

```yaml
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri:
  https://login.example.com/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id:
  ${ORDERS_INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret:
  ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Không commit secret thật; cấu hình CA/truststore, proxy/egress và timeouts theo môi trường.

### Bước 3 — Kích hoạt reactive Resource Server

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Dùng `SecurityWebFilterChain` thay cho Servlet `SecurityFilterChain`.

### Bước 4 — Thêm validators metadata bắt buộc

Dùng decorator của `ReactiveOpaqueTokenIntrospector` để kiểm tra `aud`, `iss`, token type hoặc các claims theo contract. Đảm bảo delegate vẫn kiểm tra `active` và lỗi mạng.

### Bước 5 — Ánh xạ scope minh bạch

Giữ `SCOPE_*` từ scope chuẩn. Nếu AS dùng `scp` extension, có mapping allowlist riêng; không tự nâng thành admin.

### Bước 6 — Tách endpoint authorization khỏi domain policy

`hasAuthority("SCOPE_orders.read")` chặn loại hành động; service còn kiểm tra order cụ thể, tenant/owner và điều kiện nghiệp vụ.

### Bước 7 — Test theo ba cấp

1. **Unit test** mapping/policy trên principal giả.
2. **WebTestClient** kiểm tra 401/403 và response handlers.
3. **Integration test** với fake introspection server kiểm tra `active`, metadata schema, HTTP Basic, TLS, timeout và quyền.

### Bước 8 — Vận hành fail closed

Giám sát AS latency, rate limits, client-secret rotation, TLS errors và cache/revocation tradeoff. Khi AS không cung cấp được bằng chứng token active, **không cấp quyền suy đoán**.

## 26. Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, introspection endpoint, metadata response và chính sách bảo vệ endpoint.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): khái niệm access token, client authentication và scope.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, 401/403, `invalid_token` và `insufficient_scope`.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery metadata của AS, introspection endpoint và phương thức client auth.
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): cấu hình `ReactiveOpaqueTokenIntrospector` và opaque authentication.
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): Bearer authentication trong WebFlux.
- [Spring Security — WebFlux Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange` và policies theo request.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` và phân quyền lớp dịch vụ.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): cơ chế lan truyền Reactor Context.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): lý do scope không đủ cho quyền từng đối tượng.

**Kết luận:** Trong introspection phản ứng, `ReactiveOpaqueTokenIntrospector` biến một chuỗi Bearer chưa được tin thành `OAuth2AuthenticatedPrincipal` **chỉ sau khi Authorization Server xác nhận token active**. Metadata phản hồi cho biết scope, subject, client, issuer, audience và các thuộc tính khác theo hợp đồng. Spring Security WebFlux ánh xạ các scope chuẩn thành authorities `SCOPE_*` để phục vụ `authorizeExchange` và method security, nhưng **active và scope đều không thay thế kiểm tra audience, tenant, ownership hoặc trạng thái nghiệp vụ**. Khi metadata thiếu, sai kiểu, token không active hoặc Authorization Server không khả dụng, Resource Server phải **fail closed**, không tạo principal có quyền theo suy đoán.
