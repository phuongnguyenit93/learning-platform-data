# Roles, permissions lồng trong token và converter theo hợp đồng

Khi triển khai **Spring Security OAuth 2.0 / OIDC Resource Server**, một access token dạng JWT không nhất thiết đặt toàn bộ quyền ở claim `scope`. Nhiều hệ thống định danh còn đưa **roles** hoặc **permissions** vào những JSON object lồng nhau, ví dụ `realm_access.roles`, `resource_access.orders-api.roles` hay `authorization.permissions[].scopes`. API muốn dùng các giá trị này trong `hasAuthority(...)` hoặc `@PreAuthorize` cần một **converter** hiểu đúng định dạng token và chuyển các claim đã được xác minh thành `GrantedAuthority` theo **hợp đồng quyền của ứng dụng**.

Điểm quan trọng nhất là: **Spring Security không thể tự biết role “admin” của một issuer hoặc permission “read” trong một object có nghĩa gì đối với Orders API**. Việc có thể đọc một trường JSON không đồng nghĩa trường đó đáng tin, thuộc đúng API hoặc được phép cấp một quyền nội bộ tương đương.

> **Quy tắc:** Xác minh JWT trước; xác định issuer, audience và token profile; chỉ đọc những đường dẫn claim đã thỏa thuận; chỉ ánh xạ **giá trị được cho phép** thành các authority rõ nghĩa; cuối cùng vẫn kiểm tra scope và chính sách trên tài nguyên thực tế. Không dùng một mảng role lồng trong token để “tự động có mọi quyền”.

## 1. Bài toán: Vì sao chỉ dùng `scope` là chưa đủ?

Giả sử hệ thống bán hàng có:

- **Identity Server** đóng vai Authorization Server, phát hành JWT access token đã ký.
- **Shop Web** là OAuth2 Client yêu cầu access token.
- **Orders API** là Spring Security Resource Server, chỉ nhận token có `aud` phù hợp `orders-api`.
- **Order database** lưu owner, tenant, trạng thái đơn và nhóm phụ trách.

Khi Shop Web gọi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Orders API có thể cần xác nhận cả ba điều kiện:

1. **Access token** có scope `orders.read` cho phép thử truy cập endpoint đọc.
2. Caller có **permission** `order:read:own` hoặc `order:read:tenant`, có thể được biểu diễn trong claim lồng nhau.
3. Bản ghi đơn hàng 42 nằm trong tenant, thuộc owner hoặc nhóm được phép theo dữ liệu và chính sách nghiệp vụ.

Mặc định Spring Security thường chuyển `scope: "orders.read"` thành authority `SCOPE_orders.read`, nhưng **không tự suy ra** một chuỗi `ROLE_ORDER_SUPPORT` từ `resource_access.orders-api.roles`, cũng không tự tạo `PERM_order:read:tenant` từ một object `authorization.permissions` tùy chỉnh.

Vì vậy cần thiết kế converter với vai trò và ranh giới rõ ràng:

~~~mermaid
flowchart TD
    A["Bearer JWT"]
    B["JwtDecoder: xác minh chữ ký và claims"]
    C["JWT hợp lệ với iss/aud/exp?"]
    D["JwtAuthenticationConverter"]
    E["Scope: scope/scp"]
    F["Roles: nested resource_access"]
    G["Permissions: nested authorization"]
    H["GrantedAuthorities có namespace rõ ràng"]
    I["HTTP/method authorization"]
    J["Policy owner, tenant, trạng thái"]
    X["Từ chối authentication"]

    A --> B --> C
    C -->|Không| X
    C -->|Có| D
    D --> E
    D --> F
    D --> G
    E --> H
    F --> H
    G --> H
    H --> I --> J
~~~

Việc biểu diễn quyền trong token chỉ là **đầu vào cho quyết định authorization**, không thay thế quyết định trên đối tượng dữ liệu.

## 2. Phân biệt scope, role, permission và GrantedAuthority

| Khái niệm | Câu hỏi nó trả lời | Ví dụ | Ai định nghĩa/nghiệp vụ sử dụng? |
| --- | --- | --- | --- |
| **OAuth2 scope** | Token được cấp phạm vi truy cập nào? | `orders.read`, `orders.cancel` | AS cấp theo chính sách Client/grant; API quy định endpoint |
| **Role** | Subject có vai trò gì trong một miền quyền? | `order_support`, `tenant_admin` | Identity/authorization domain; thường ánh xạ RBAC |
| **Permission** | Subject có khả năng cụ thể nào? | `order:read:tenant`, `order:cancel:own` | Chính sách quyền của hệ thống; có thể đến từ role hoặc cấp trực tiếp |
| **GrantedAuthority** | Spring Security đối chiếu chuỗi quyền nào? | `SCOPE_orders.read`, `ROLE_ORDER_SUPPORT`, `PERM_order:read:tenant` | Resource Server tạo bằng converter và/hoặc nguồn quyền nội bộ |
| **Resource policy** | Subject được hành động trên bản ghi cụ thể không? | Chỉ đọc đơn của tenant được phân công | API/lớp nghiệp vụ áp dụng dữ liệu tin cậy |

Những khái niệm này có thể liên hệ, nhưng không đồng nhất:

- **Scope** thường giới hạn **cửa vào API**: token có được gọi chức năng không?
- **Role** gom quyền theo trách nhiệm: nhân viên hỗ trợ, quản trị tenant...
- **Permission** mô tả hành động chi tiết: đọc đơn của bản thân, xem đơn của tenant...
- **Authority** là biểu diễn **trong Spring Security**, thường là một chuỗi.
- **Policy dữ liệu** dùng owner/tenant/trạng thái để xác định trường hợp cụ thể.

Đặc tả JWT không bắt buộc mọi token phải có `roles` hoặc `permissions`. OAuth 2.0 không chuẩn hóa vai trò `ORDER_SUPPORT` hay quyền `order:read:tenant`. Các tên đó phải được **Authorization Server và Resource Server thỏa thuận**, ghi nhận và phiên bản hóa khi thay đổi.

### 2.1. Tên authority phải khớp chính xác

Với converter mặc định, claim:

~~~json
{"scope": "orders.read orders.cancel"}
~~~

có thể được ánh xạ thành:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Do đó:

~~~java
hasAuthority("SCOPE_orders.read")
~~~

khác với:

~~~java
hasAuthority("orders.read")
~~~

Tương tự, `hasRole("ORDER_SUPPORT")` theo quy ước prefix thường kiểm tra authority `ROLE_ORDER_SUPPORT`. Nếu converter tạo `ROLE_ORDER_SUPPORT`, có thể dùng `hasRole("ORDER_SUPPORT")` hoặc `hasAuthority("ROLE_ORDER_SUPPORT")` theo quy ước đã chọn. Prefix `PERM_` trong ví dụ dưới đây **là quy ước ứng dụng tự đặt**, không phải mặc định Spring Security.

## 3. “Lồng trong token” có nghĩa gì?

Ở đây, **nested roles/permissions** nghĩa là các claim JSON chứa object hoặc list lồng nhau. Nó **không đồng nghĩa** với *nested JWT* kiểu JOSE (JWS bên trong JWE). Ta đang nói về hình dạng **JWT Claims Set** sau khi token được xác minh.

### 3.1. Role ở claim cấp cao nhất

Định dạng đơn giản:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["order_support", "tenant_admin"]
}
~~~

Resource Server có thể đọc `roles` như danh sách chuỗi. Tuy nhiên, claim này có thể mang role của cả tổ chức hoặc của một Client khác nếu hợp đồng không nói rõ. **Không suy diễn tự động rằng mọi giá trị trong `roles` đều có hiệu lực với Orders API**.

### 3.2. Role lồng theo realm và theo resource/client

Một số Identity Provider, chẳng hạn mô hình thường gặp ở Keycloak, có thể dùng những claim dạng:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "realm_access": {
    "roles": ["platform_auditor", "default-roles-shop"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["order_support"]
    },
    "billing-api": {
      "roles": ["billing_admin"]
    }
  }
}
~~~

Hai đường dẫn có ngữ nghĩa khác nhau:

| Đường dẫn | Thông tin biểu diễn | Cách Orders API nên xử lý |
| --- | --- | --- |
| `realm_access.roles` | Role ở cấp realm/miền định danh | Chỉ dùng nếu có hợp đồng xác định role nào liên quan Orders API |
| `resource_access["orders-api"].roles` | Role liên quan resource/client tên `orders-api` theo issuer | Có thể ánh xạ những role Orders API cho phép |
| `resource_access["billing-api"].roles` | Role dành cho resource/client khác | **Không** chuyển thành authority quản trị Orders API |
| `scope` | OAuth2 scopes của access token | Ánh xạ theo quy tắc scope đã thỏa thuận |

Trong nhiều sản phẩm định danh, **Client ID**, **resource identifier** và **JWT audience** có thể là các giá trị khác nhau. Ví dụ `resource_access["orders-api"]` dùng key là Client ID của một ứng dụng đăng ký tại IdP, còn `aud` có thể là URI tài nguyên. Bài học chọn hai chuỗi giống nhau cho dễ minh họa; triển khai thật phải ghi rõ từng giá trị trong hợp đồng, **không tự suy ra key của `resource_access` từ hostname hay từ phần tử `aud`**.

### 3.3. Permissions có thể là object và list lồng nhiều cấp

Ví dụ một hợp đồng **do hệ thống tự định nghĩa**:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-A",
  "authorization": {
    "permissions": [
      {
        "resource": "orders",
        "scopes": ["read:tenant", "comment:tenant"]
      },
      {
        "resource": "reports",
        "scopes": ["export"]
      }
    ]
  }
}
~~~

Trong ví dụ này:

- `authorization` là object.
- `authorization.permissions` là mảng object.
- Mỗi permission có `resource` và một mảng `scopes` **thuộc permission của resource**.
- `authorization.permissions[0].scopes` **không giống** claim OAuth2 `scope` ở cấp cao nhất.

Các tên `resource` và `scopes` trong `authorization.permissions` chỉ là **hợp đồng minh họa**, không phải định dạng chuẩn chung của mọi JWT access token. Một hệ thống Keycloak Authorization Services có thể dùng cấu trúc `authorization.permissions` chứa các trường như `rsid`, `rsname` và `scopes`; một issuer khác có thể dùng URI claim hoặc JSON hoàn toàn khác. **Không mang converter từ sản phẩm A sang sản phẩm B khi chưa đối chiếu token thật và tài liệu nhà phát hành.**

## 4. Hợp đồng claim cần được viết rõ trước khi code

Lấy Orders API làm ví dụ, ta thỏa thuận:

| Thành phần hợp đồng | Giá trị/định dạng ví dụ | Quy tắc tin cậy |
| --- | --- | --- |
| **Issuer** | `https://id.example.test/realms/shop` | Phải khớp issuer tin cậy và chữ ký hợp lệ |
| **Audience** | Chứa `orders-api` | Token phải dành cho Orders API |
| **Loại token** | OAuth2 JWT access token | Không nhận OIDC ID token làm access token |
| **Scope** | `scope` là chuỗi phân cách bằng dấu cách hoặc theo profile được hỗ trợ | Spring chuyển thành `SCOPE_...` |
| **Realm roles** | `realm_access.roles` là array string | Chỉ nhận role có mapping tường minh |
| **API role lookup** | `resource_access["orders-api"].roles` | Chỉ lấy đúng resource/client đã đăng ký |
| **Permission lookup** | `authorization.permissions[]` có `resource` và `scopes[]` | Chỉ nhận resource/action nằm trong bảng mapping |
| **Tenant** | `tenant_id` là chuỗi | Chỉ dùng trong policy sau khi token xác minh; vẫn cần đối chiếu resource |
| **User identity** | `(iss, sub)` | Không dùng username/email làm khóa quyền mặc định |
| **Spring authority prefixes** | `SCOPE_`, `ROLE_`, `PERM_` | Những tên đã chuẩn hóa trong chính API |

### 4.1. Bảng ánh xạ tường minh

Ví dụ doanh nghiệp quyết định:

| Nguồn token | Giá trị nhận | Authority được tạo | Ý nghĩa trong API |
| --- | --- | --- | --- |
| OAuth2 scope | `orders.read` | `SCOPE_orders.read` | Được phép yêu cầu thao tác đọc |
| OAuth2 scope | `orders.cancel` | `SCOPE_orders.cancel` | Được phép yêu cầu thao tác hủy |
| Realm role | `platform_auditor` | `ROLE_PLATFORM_AUDITOR` | Vai trò kiểm toán đã được hệ thống chấp thuận |
| Role của `orders-api` | `order_support` | `ROLE_ORDER_SUPPORT` | Nhân viên hỗ trợ trong phạm vi đã quy định |
| Role của `orders-api` | `tenant_admin` | `ROLE_TENANT_ADMIN` | Quản trị tenant thuộc quyền |
| `orders` permission scope | `read:own` | `PERM_order:read:own` | Có thể đọc đơn thuộc chủ thể |
| `orders` permission scope | `read:tenant` | `PERM_order:read:tenant` | Có thể đọc đơn trong tenant được phép |
| `orders` permission scope | `cancel:own` | `PERM_order:cancel:own` | Có thể hủy đơn của chủ thể khi trạng thái phù hợp |

Không ánh xạ `billing_admin` trong `resource_access["billing-api"]` thành `ROLE_TENANT_ADMIN` của Orders API. Không ánh xạ những role không được phép như `default-roles-shop` thành authority ứng dụng. Nếu issuer thêm role mới, Resource Server **không tự động cấp quyền mới**, trừ khi hợp đồng mapping được cập nhật có chủ đích.

### 4.2. Phân biệt role được gán và permission được suy ra

Một issuer có thể phát cả role lẫn permission. Khi đó phải biết:

- Role và permission có là **hai nguồn độc lập** hay permission được tính từ role?
- Có bắt buộc **cả scope và permission** hay chỉ một trong hai?
- Trong trường hợp token có role nhưng không có permission tương ứng, API nên xử lý ra sao?
- Role có hiệu lực **trong tenant nào**?
- Permission đã được issuer kiểm tra quyền hiện hành hay có thể đã cũ?

Trong bài này, converter **chỉ chuyển dữ liệu claim thành authority**. Nó **không tự mở rộng** `ROLE_ORDER_SUPPORT` thành `PERM_order:read:tenant`. Nếu hệ thống có quy tắc role → permission, hãy thực hiện bằng một policy/authorization component rõ ràng, hoặc để Authorization Server phát permission đã được tính toán theo hợp đồng. Tránh đồng thời tính ở nhiều nơi dẫn đến cấp quyền mâu thuẫn.

## 5. Luồng xử lý chuẩn trong Spring Security

Luồng phù hợp là:

~~~text
HTTP request + Bearer access token
    |
    v
BearerTokenAuthenticationFilter
    |
    v
JwtAuthenticationProvider
    |
    v
JwtDecoder / NimbusJwtDecoder
  - xác minh JWS signature bằng public key/JWKS tin cậy
  - kiểm tra iss, exp, nbf, aud, token profile theo cấu hình
    |
    v
JwtAuthenticationConverter
  - lấy SCOPE_ từ scope/scp
  - đọc realm_access.roles theo mapping
  - đọc resource_access["orders-api"].roles theo mapping
  - đọc authorization.permissions theo mapping
    |
    v
JwtAuthenticationToken
  - principal: Jwt đã xác minh
  - authorities: tập quyền nội bộ
    |
    v
SecurityFilterChain / @PreAuthorize
    |
    v
Service policy: tenant, owner, resource status
~~~

**Không viết code parse raw JWT rồi tạo authorities bên ngoài `JwtDecoder`.** Một người gửi có thể tự tạo payload chứa `"roles": ["tenant_admin"]`. Nếu token chưa được xác minh mà converter vẫn tin trường đó, API đã để caller tự cấp quyền cho chính mình.

### 5.1. Mặc định Spring Security chuyển scope thế nào?

`JwtGrantedAuthoritiesConverter` của Spring Security hỗ trợ ánh xạ scope từ các claim phổ biến `scope` hoặc `scp` theo định dạng được hỗ trợ. Ví dụ:

~~~json
{
  "sub": "user-842",
  "scope": "orders.read orders.cancel"
}
~~~

Các authority thông dụng:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Nhưng mặc định này không đồng nghĩa tự đọc:

~~~text
realm_access.roles
resource_access.orders-api.roles
authorization.permissions[*].scopes
~~~

**Một claim lồng nhau là dữ liệu JSON, không phải tên claim cấp cao nhất chứa dấu chấm.** Đặt tên `setAuthoritiesClaimName("resource_access.orders-api.roles")` không phải cách chung để đi xuyên object như JSONPath; phải viết converter đọc nested structure thực sự.

## 6. Cài đặt `JwtAuthenticationConverter` cho nested roles và permissions

Ví dụ dưới đây dành cho **Spring Boot 3 / Spring Security 6 trên Java 17+**. Mã Java thể hiện một hợp đồng cụ thể và có chủ đích:

- Giữ mapping scope mặc định.
- Chỉ lấy realm role `platform_auditor`.
- Chỉ lấy role từ `resource_access["orders-api"]`, không lấy từ `billing-api`.
- Chỉ lấy permission cho resource `orders`, với các action đã được cho phép.
- Gộp authority không trùng nhau bằng `LinkedHashSet`.
- Bỏ qua claim tùy chọn bị thiếu hoặc không phù hợp cấu trúc; nếu claim bắt buộc, cần **validator từ chối token** theo hợp đồng (mục 8).

### 6.1. Dependencies và cấu hình

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
    resource-client-id: orders-api
~~~

Đặt hai thông tin **expected-audience** và **resource-client-id** riêng là có chủ đích. Trong ví dụ cả hai đều có thể là `orders-api`; ở một IdP khác, key `resource_access` có thể không trùng audience. URL/issuer/JWKS/audience của từng môi trường phải lấy từ nhà phát hành tin cậy, không suy đoán.

### 6.2. Converter đầy đủ, ánh xạ bằng allowlist

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthorityMappingConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter(
            @Value("${app.security.resource-client-id}") String resourceClientId) {

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("sub");
        converter.setJwtGrantedAuthoritiesConverter(
                new NestedAuthoritiesConverter(resourceClientId));
        return converter;
    }

    static final class NestedAuthoritiesConverter
            implements Converter<Jwt, Collection<GrantedAuthority>> {

        private static final Map<String, String> REALM_ROLES = Map.of(
                "platform_auditor", "ROLE_PLATFORM_AUDITOR");

        private static final Map<String, String> ORDERS_ROLES = Map.of(
                "order_support", "ROLE_ORDER_SUPPORT",
                "tenant_admin", "ROLE_TENANT_ADMIN");

        private static final Map<String, String> ORDER_PERMISSIONS = Map.of(
                "read:own", "PERM_order:read:own",
                "read:tenant", "PERM_order:read:tenant",
                "cancel:own", "PERM_order:cancel:own");

        private final String resourceClientId;
        private final JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        NestedAuthoritiesConverter(String resourceClientId) {
            this.resourceClientId = resourceClientId;
        }

        @Override
        public Collection<GrantedAuthority> convert(Jwt jwt) {
            Set<GrantedAuthority> result = new LinkedHashSet<>();

            // 1) Scope OAuth 2.0: giữ mặc định SCOPE_...
            Collection<GrantedAuthority> scopeAuthorities =
                    scopes.convert(jwt);
            if (scopeAuthorities != null) {
                result.addAll(scopeAuthorities);
            }

            // 2) Realm roles: chỉ nhận các giá trị trong bảng cho phép.
            Map<String, Object> realm = jwt.getClaimAsMap("realm_access");
            if (realm != null) {
                addMappedRoles(result, realm.get("roles"), REALM_ROLES);
            }

            // 3) Resource-specific roles: chỉ từ client/resource của API này.
            Map<String, Object> resources =
                    jwt.getClaimAsMap("resource_access");
            if (resources != null) {
                Object currentResource = resources.get(resourceClientId);
                if (currentResource instanceof Map<?, ?> attributes) {
                    addMappedRoles(
                            result, attributes.get("roles"), ORDERS_ROLES);
                }
            }

            // 4) Permissions object lồng nhau theo hợp đồng của Orders API.
            Map<String, Object> authorization =
                    jwt.getClaimAsMap("authorization");
            if (authorization != null) {
                Object rawPermissions = authorization.get("permissions");
                if (rawPermissions instanceof Collection<?> permissions) {
                    for (Object item : permissions) {
                        if (!(item instanceof Map<?, ?> permission)) {
                            continue;
                        }
                        // Không lấy permission của resource khác.
                        if (!"orders".equals(permission.get("resource"))) {
                            continue;
                        }
                        Object rawScopes = permission.get("scopes");
                        if (rawScopes instanceof Collection<?> values) {
                            for (Object value : values) {
                                if (value instanceof String action) {
                                    String granted =
                                            ORDER_PERMISSIONS.get(action);
                                    if (granted != null) {
                                        result.add(
                                            new SimpleGrantedAuthority(granted));
                                    }
                                }
                            }
                        }
                    }
                }
            }

            return result;
        }

        private static void addMappedRoles(
                Set<GrantedAuthority> output,
                Object rawRoles,
                Map<String, String> allowedRoles) {

            if (!(rawRoles instanceof Collection<?> values)) {
                return;
            }
            for (Object value : values) {
                if (value instanceof String role) {
                    String authority = allowedRoles.get(role);
                    if (authority != null) {
                        output.add(new SimpleGrantedAuthority(authority));
                    }
                }
            }
        }
    }
}
~~~

### 6.3. Phân tích converter theo từng bước

**Bước 1 — giữ OAuth2 scope:** 

~~~java
JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();
~~~

`scopes.convert(jwt)` bảo toàn các quyền `SCOPE_...` từ claim scope được hỗ trợ. Nếu thay converter mà quên bước này, một token mang `orders.read` có thể không còn thỏa `hasAuthority("SCOPE_orders.read")`.

**Bước 2 — đọc nested object bằng kiểu dữ liệu đúng:**

~~~java
Map<String, Object> resources = jwt.getClaimAsMap("resource_access");
Object current = resources == null ? null : resources.get("orders-api");
~~~

Token thực có thể không có `resource_access`, hoặc nó không phải object. Converter không nên ép kiểu trực tiếp `(Map<String,Object>)` trên dữ liệu không bảo đảm hình dạng, tránh exception khó chẩn đoán. Với các claim **tùy chọn**, có thể coi vắng/malformed là “không có authority tương ứng”; với claim **bắt buộc**, dùng validator để từ chối token rõ ràng.

**Bước 3 — chỉ chấp nhận role được khai báo tường minh:**

~~~java
Map.of("order_support", "ROLE_ORDER_SUPPORT")
~~~

Không dùng cách:

~~~java
// Không nên dùng cho role từ issuer không có hợp đồng rõ:
new SimpleGrantedAuthority("ROLE_" + roleFromAnyNestedClaim);
~~~

Nếu token có `billing_admin` hoặc role mới chưa được đội API phê duyệt, phép nối chuỗi tự động có thể biến nó thành authority có ý nghĩa ngoài dự kiến. Bảng allowlist giữ nguyên tắc **không cấp quyền mới chỉ vì xuất hiện tên role mới trong token**.

**Bước 4 — permission resource-specific:**

~~~text
authorization.permissions:
  resource = orders
  scopes = [read:own, read:tenant]

=> PERM_order:read:own
=> PERM_order:read:tenant
~~~

Không lấy `reports/export` làm quyền trên `orders`. Nếu có thêm permission cho resource khác, định nghĩa converter/chính sách riêng theo đúng contract.

**Bước 5 — không trùng authority:** `LinkedHashSet` giảm trùng nếu một authority được lặp trong nhiều entry. Nó không tạo ra suy luận mới về quyền.

### 6.4. Kết quả với JWT minh họa

Với JWT đã xác minh:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "realm_access": {
    "roles": ["platform_auditor", "default-roles-shop"]
  },
  "resource_access": {
    "orders-api": { "roles": ["order_support"] },
    "billing-api": { "roles": ["billing_admin"] }
  },
  "authorization": {
    "permissions": [
      { "resource": "orders",
        "scopes": ["read:tenant", "comment:tenant"] },
      { "resource": "reports",
        "scopes": ["export"] }
    ]
  }
}
~~~

Converter ở mục 6.2 sẽ tạo:

~~~text
SCOPE_orders.read
ROLE_PLATFORM_AUDITOR
ROLE_ORDER_SUPPORT
PERM_order:read:tenant
~~~

Nó **không** tạo `ROLE_BILLING_ADMIN`, không tạo authority cho `default-roles-shop` và không tạo `PERM_report:export:tenant`. `comment:tenant` cũng bị bỏ qua vì không có trong bảng permission cho phép. Nếu hệ thống muốn dùng `comment:tenant`, phải cập nhật **cả hợp đồng và policy** một cách có chủ đích.

## 7. Gắn converter vào SecurityFilterChain

Chỉ khai báo một bean `JwtAuthenticationConverter` không phải lúc nào cũng có nghĩa cấu hình API sẽ tự dùng bean đó. Cần gắn converter cho JWT Resource Server đang bảo vệ đường dẫn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurityConfiguration {

    @Bean
    SecurityFilterChain ordersApi(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtAuthenticationConverter)))
            .build();
    }
}
~~~

Đây là cấu hình **một REST API dùng Bearer token**, không dùng session cookie cho `/api/**`; vì vậy ví dụ có CSRF disabled và stateless. Nếu ứng dụng có web UI/session, cần chính sách CSRF và filter chain tương ứng thay vì sao chép cấu hình này cho toàn bộ ứng dụng.

Ở tầng HTTP, `GET /api/orders/**` chỉ yêu cầu `SCOPE_orders.read`. Role và permission nested không tự được kiểm tra bởi rule đó. Tầng service nên áp dụng policy chi tiết, hoặc HTTP rule có thể kết hợp các yêu cầu theo hợp đồng.

### 7.1. Cần kiểm tra cả scope và permission

Nếu hợp đồng yêu cầu **scope đọc** và **ít nhất một permission đọc**:

~~~java
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@EnableMethodSecurity
@Configuration
class MethodSecurityConfiguration {
}
~~~

Ở service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrdersQueryService {

    private final OrderRepository orders;

    OrdersQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "(hasAuthority('PERM_order:read:own') or " +
        "hasAuthority('PERM_order:read:tenant')) and " +
        "@orderAccess.canRead(authentication, #id)")
    public OrderDto readOrder(String id) {
        return orders.findDtoById(id)
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

`OrderRepository`, `OrderDto`, `OrderNotFoundException` và bean `orderAccess` là thành phần nghiệp vụ ví dụ, không phải những class tự có của Spring Security. Bean `orderAccess` cần tải thông tin đơn 42 đáng tin (owner, tenant, trạng thái, phân công) và so khớp với caller đã xác minh.

Lưu ý: Token có `ROLE_ORDER_SUPPORT` **không tự biến thành** `PERM_order:read:tenant` trong converter được viết ở trên. Một hệ thống muốn suy ra permission từ role phải có **một nơi** thực hiện rule role → permission rõ ràng. Nếu không, người có role mà thiếu permission sẽ bị từ chối ở method security theo đúng hợp đồng ví dụ.

### 7.2. Giới hạn theo dữ liệu thật

Giả sử JWT có:

~~~json
{
  "sub": "support-12",
  "tenant_id": "tenant-A",
  "scope": "orders.read",
  "authorization": {
    "permissions": [
      { "resource": "orders", "scopes": ["read:tenant"] }
    ]
  }
}
~~~

Ngay cả khi token có authority `PERM_order:read:tenant`, API vẫn cần kiểm tra đơn 42 thuộc **tenant-A** và người hỗ trợ được phân công nếu chính sách yêu cầu. Không lấy `tenant_id` từ query string do Client gửi để bỏ qua so khớp. Role/permission có thể là điều kiện **cần**; quyền trên bản ghi là điều kiện **đủ** theo policy cụ thể.

## 8. Xác minh JWT trước khi tin nested roles và permissions

**Converter chỉ nên nhận `Jwt` từ decoder đã xác minh**. Không tự đọc `Authorization` header bằng `String.split("\\.")`, Base64URL decode rồi trích `realm_access` hoặc `authorization.permissions` để tạo `GrantedAuthority`.

### 8.1. Giữ issuer, thời hạn và audience

Ví dụ cấu hình JWT decoder riêng để kiểm tra audience:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtTrustConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                "invalid_token",
                                "JWT is not intended for this API",
                                null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard, audience));
        return decoder;
    }
}
~~~

`NimbusJwtDecoder` kiểm tra chữ ký bằng khóa JWKS tin cậy theo cấu hình thuật toán; validator kiểm tra issuer/thời gian và audience. Trong production còn cần ràng buộc thuật toán được phép, token type/profile và các claim bắt buộc theo nhà phát hành. **Không thay các validator mặc định bằng một validator chỉ kiểm tra permission**.

Nếu JWT `iss` không khớp hoặc `aud` không chứa Orders API, token phải bị từ chối **trước khi** những role trông có vẻ hợp lệ được sử dụng. Token ký bởi một issuer khác có `role = admin` không cấp quyền ở Orders API.

### 8.2. Claims tùy chọn và claims bắt buộc

Ví dụ converter ở mục 6 **bỏ qua quyền** khi nested claim tùy chọn vắng hoặc không đúng kiểu. Điều này không có nghĩa mọi payload malformed đều phải được chấp nhận như một JWT hợp lệ.

Phân biệt:

| Chính sách claim | Cách thực hiện phù hợp |
| --- | --- |
| Claim roles tùy chọn, thiếu thì không có role | Converter trả về zero role authority |
| Claim permissions tùy chọn, thiếu thì không có permission | Converter trả về zero permission authority |
| API yêu cầu mọi access token phải có claim `tenant_id` | Viết `OAuth2TokenValidator<Jwt>` kiểm tra sự tồn tại, kiểu và format; từ chối token nếu sai |
| Một token profile bắt buộc `authorization.permissions` đúng schema | Validator/profile layer kiểm tra và từ chối malformed token trước khi vào converter |
| Một quyền chỉ hợp lệ khi thuộc tenant hiện tại | Policy dữ liệu kiểm tra tenant/owner, không chỉ trong converter |
| Token đến từ issuer khác nhưng có tên claim giống nhau | Từ chối nếu issuer không thuộc danh sách tin cậy hoặc dùng profile/mapping riêng |

Ví dụ một validator yêu cầu `tenant_id` là chuỗi không rỗng:

~~~java
OAuth2TokenValidator<Jwt> tenantRequired = jwt -> {
    Object tenant = jwt.getClaims().get("tenant_id");
    if (tenant instanceof String text && !text.isBlank()) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token",
                    "Required tenant_id is missing or invalid", null));
};
~~~

Khi dùng validator bổ sung, gộp nó **cùng** các validator thời gian, issuer, audience và những điều kiện token profile. Không thay thế chúng bằng một mình `tenantRequired`.

### 8.3. Token của nhiều issuer không nên dùng chung mapping bừa bãi

Hai Authorization Server có thể cùng phát:

~~~json
{"realm_access":{"roles":["admin"]}}
~~~

nhưng role `admin` của issuer A không đồng nghĩa role `admin` của issuer B. Với Resource Server tin nhiều issuer, mỗi issuer cần ràng buộc **khóa, audience, thuật toán, token profile và bảng mapping** phù hợp. Không gom JWT từ nhiều issuer vào converter cấp `ROLE_ADMIN` chung khi không có hợp đồng liên thông quyền.

## 9. Những quy tắc thiết kế converter an toàn

### 9.1. Chỉ đọc claim theo schema đã thỏa thuận

Một số cách đọc dữ liệu sai:

~~~java
// Sai nếu tưởng getClaimAsStringList() tự đi xuyên object:
jwt.getClaimAsStringList("resource_access.orders-api.roles");

// Nguy hiểm nếu áp dụng cho mọi object không có contract:
flattenAllStringsRecursively(jwt.getClaims());
~~~

Một converter tổng quát “quét mọi chuỗi trong token rồi thêm `ROLE_`” có thể đọc nhầm scope, username, tenant, role của Client khác hoặc thông tin không liên quan. Thay vào đó, hãy điều hướng cấu trúc bằng **tên field và key resource xác định**, rồi đối chiếu bảng mapping tường minh.

### 9.2. Không nâng quyền nhờ tên role giống nhau

Ví dụ token chứa:

~~~json
{
  "resource_access": {
    "billing-api": { "roles": ["admin"] }
  }
}
~~~

Đây là role trong context Billing API. **Orders API không được** biến nó thành `ROLE_ADMIN` rồi cho phép hủy đơn. Converter phải giới hạn key `orders-api` và định nghĩa rõ role Orders API thực sự chấp nhận.

### 9.3. Giữ namespace authority rõ nghĩa

Một ứng dụng có thể thống nhất:

~~~text
SCOPE_orders.read        -> OAuth2 scope
ROLE_ORDER_SUPPORT      -> role trong Orders API
ROLE_PLATFORM_AUDITOR   -> role realm đã được phê duyệt
PERM_order:read:tenant  -> permission cụ thể
~~~

Tránh để `ROLE_ADMIN` có thể được tạo đồng thời từ:

- Realm admin.
- Resource admin của Orders API.
- Resource admin của Billing API.
- Custom permissions có chuỗi “admin”.

Nếu muốn dùng role trùng tên ở nhiều miền, hãy đặt namespace trong authority, ví dụ `ROLE_ORDERS_ADMIN` và `ROLE_PLATFORM_ADMIN`, và cập nhật biểu thức `hasAuthority` tương ứng.

### 9.4. Không dùng dữ liệu claim chưa xác minh

Một JWT chưa được xác minh chỉ là chuỗi do Client cung cấp, dù có JSON đẹp hoặc `kid` hợp lệ. Spring Security cần xác minh bằng khóa và issuer/audience đúng **trước** converter. Không cho phép một fallback “nếu JWKS down thì đọc roles từ payload” vì đó là cơ chế **fail open**.

### 9.5. Giới hạn role/permission được phát từ token

Hợp đồng nên giới hạn:

- Tên và dạng dữ liệu claim.
- Số lượng và độ dài role/permission có thể xuất hiện.
- Các resource và action được phép.
- Issuer/Client được cấp những permission nào.
- Mục đích sử dụng và thời gian sống access token.

Ngoài allowlist, với hệ thống có yêu cầu chống abuse cao có thể kiểm tra schema/giới hạn kích thước trong validation layer. Đừng để một token chứa hàng chục nghìn giá trị tự tạo hàng chục nghìn `GrantedAuthority` rồi gây áp lực bộ nhớ hoặc độ trễ.

### 9.6. Không tự coi role bao hàm permission

Nếu hệ thống có rule:

~~~text
ROLE_ORDER_SUPPORT -> PERM_order:read:tenant
~~~

phải quyết định **ai chịu trách nhiệm thực hiện rule**:

1. Authorization Server phát permission đã suy ra từ role.
2. Resource Server/role hierarchy áp dụng rule được kiểm soát.
3. Policy engine phía server tra cứu entitlement hiện tại.

Không nên để ba nơi cùng mở rộng role theo những quy tắc khác nhau, khiến việc thu hồi quyền khó dự đoán. Việc **role xuất hiện trong JWT** chưa chắc nghĩa permission kèm theo đang có hiệu lực ở thời điểm request nếu quyền đã được cập nhật sau khi token được cấp.

## 10. Ví dụ authorization theo quyền và ownership

Một hợp đồng nghiệp vụ có thể quy định:

| Thao tác | Scope OAuth2 | Permission/role liên quan | Điều kiện dữ liệu |
| --- | --- | --- | --- |
| Khách hàng đọc đơn của mình | `orders.read` | `PERM_order:read:own` | `order.ownerSubject` khớp subject, đúng tenant |
| Hỗ trợ đọc đơn tenant | `orders.read` | `PERM_order:read:tenant` | Caller nằm trong nhóm hỗ trợ và tenant được giao |
| Hủy đơn của mình | `orders.cancel` | `PERM_order:cancel:own` | Chính chủ và trạng thái cho phép hủy |
| Xem báo cáo kiểm toán | Scope riêng theo hợp đồng | Role/permission audit riêng | Chỉ dataset/tenant thuộc phạm vi được cấp |

Một chính sách có thể viết về mặt logic:

~~~text
canReadOrder =
    validAccessToken
    AND aud contains "orders-api"
    AND has("SCOPE_orders.read")
    AND (
      has("PERM_order:read:own") AND order.owner == caller.subject
      OR
      has("PERM_order:read:tenant")
          AND order.tenant IN caller.authorizedTenants
          AND caller.assignedGroup allows order
    )
~~~

Trong biểu thức trên, `caller.authorizedTenants` và `assignedGroup` phải đến từ **dữ liệu tin cậy** hoặc claim với ngữ nghĩa đã thỏa thuận và được xác minh; không nhận giá trị do Client tự khai trong header/query mà không kiểm tra.

### 10.1. Vai trò của `@PreAuthorize`

`@PreAuthorize` ở mục 7 giúp chặn người không có scope/permission trước khi đọc dữ liệu; bean `orderAccess` thực hiện điều kiện trên **đơn hàng thực tế**. Nếu application chỉ có:

~~~java
@PreAuthorize("hasRole('ORDER_SUPPORT')")
~~~

thì chưa chắc đã biết nhân viên hỗ trợ có được xem **orderId = 42** trong tenant khác không. Khi permission có dạng `read:tenant`, cần kiểm tra tenant thực tế ở tầng nghiệp vụ.

### 10.2. Tránh authority quá rộng

Không đặt permission object:

~~~json
{"resource": "orders", "scopes": ["read:tenant"]}
~~~

thành authority `ROLE_ADMIN` chỉ vì một converter “tổng quát” coi mọi permission là quyền admin. Authority cần phản ánh **chính xác khả năng**. Các điều kiện về owner, tenant, region, hợp đồng khách hàng và trạng thái đối tượng vẫn cần policy độc lập.

## 11. Kiểm thử converter và JWT verification là hai lớp khác nhau

### 11.1. Unit test converter

Với Spring Security, có thể tạo `Jwt` trong unit test mà không cần tạo chữ ký thật. Ví dụ JUnit Jupiter (đặt test cùng package với config để truy cập converter nội bộ):

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

class NestedAuthoritiesConverterTest {

    private final JwtAuthorityMappingConfig.NestedAuthoritiesConverter
            converter =
            new JwtAuthorityMappingConfig.NestedAuthoritiesConverter(
                    "orders-api");

    @Test
    void mapsOnlyAllowedAuthoritiesFromOrdersApiContract() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only")
                .header("alg", "RS256")
                .claim("sub", "user-842")
                .claim("scope", "orders.read")
                .claim("realm_access", Map.of(
                        "roles", List.of(
                                "platform_auditor",
                                "default-roles-shop")))
                .claim("resource_access", Map.of(
                        "orders-api", Map.of(
                                "roles", List.of("order_support")),
                        "billing-api", Map.of(
                                "roles", List.of("billing_admin"))))
                .claim("authorization", Map.of(
                        "permissions", List.of(
                                Map.of(
                                        "resource", "orders",
                                        "scopes", List.of("read:tenant")),
                                Map.of(
                                        "resource", "reports",
                                        "scopes", List.of("export")))))
                .build();

        Collection<GrantedAuthority> result = converter.convert(jwt);
        Set<String> names = result.stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());

        assertTrue(names.contains("SCOPE_orders.read"));
        assertTrue(names.contains("ROLE_PLATFORM_AUDITOR"));
        assertTrue(names.contains("ROLE_ORDER_SUPPORT"));
        assertTrue(names.contains("PERM_order:read:tenant"));

        assertFalse(names.contains("ROLE_BILLING_ADMIN"));
        assertFalse(names.contains("ROLE_DEFAULT_ROLES_SHOP"));
        assertFalse(names.contains("PERM_report:export:tenant"));
    }
}
~~~

Test này chứng minh **quy tắc chuyển đổi dữ liệu claim thành authority**, không chứng minh JWT được ký đúng. `Jwt.withTokenValue(...)` trong unit test không đi qua `JwtDecoder` và không xác minh mật mã.

### 11.2. Test token thiếu claim/malformed

Bộ unit test cũng cần xét:

| Tình huống đầu vào | Kết quả của converter theo hợp đồng ví dụ |
| --- | --- |
| Chỉ có `scope = orders.read` | Chỉ có `SCOPE_orders.read` |
| Không có `realm_access` | Không có realm-role authority |
| `resource_access` có role của `billing-api` nhưng không có `orders-api` | Không tạo role của Orders API |
| `orders-api.roles` là string thay vì array | Không chuyển string thành role |
| `authorization.permissions` thiếu | Không tạo permission authority |
| Permission entry có `resource = reports` | Không cấp Orders permission |
| Permission có scope `delete:all` chưa được cho phép | Không tạo authority mới |
| Lặp nhiều lần role/permission | Kết quả không có authority trùng theo tập hợp |
| Claim bắt buộc bị thiếu hoặc sai schema | Validator riêng từ chối token theo hợp đồng |

Lưu ý phân biệt **token không có quyền** với **token sai hợp đồng**: nếu role tùy chọn thiếu, caller không nhận role; nếu một token profile bắt buộc role/tenant mà lại sai schema, validator nên làm request thất bại ở tầng authentication thay vì chỉ thiếu authority một cách âm thầm.

### 11.3. Integration test với chữ ký thật

Để kiểm thử **SecurityFilterChain + JwtDecoder + converter**, test cần gửi **Bearer JWT được ký thật** bằng test key, với mock JWKS và issuer/audience phù hợp:

1. Token ký đúng, đúng issuer/audience, có `resource_access.orders-api.roles` → nhận authority theo mapping.
2. Token có cùng payload nhưng chữ ký bị sửa → bị từ chối **trước** converter.
3. Token được ký hợp lệ nhưng sai audience → bị từ chối dù có role `tenant_admin`.
4. Token đúng nhưng role nằm dưới `billing-api` → không có quyền Orders API.
5. Token đúng và đủ scope/permission nhưng đơn thuộc tenant khác → policy dữ liệu từ chối.

`SecurityMockMvcRequestPostProcessors.jwt()` tiện cho test authorization theo `Authentication` đã giả lập, nhưng **không tự kiểm thử chữ ký/JWKS của JWT thật**. Khi kiểm thử bảo mật cấu trúc access token, dùng integration test đi qua decoder.

## 12. Phản hồi lỗi: token không hợp lệ hay thiếu quyền?

| Trường hợp | Giai đoạn từ chối | HTTP thường gặp |
| --- | --- | --- |
| JWT thiếu, chữ ký sai, issuer/audience sai, hết hạn | Authentication/`JwtDecoder` | **401 Unauthorized** |
| JWT được xác minh nhưng không có `orders.read` | HTTP authorization | **403 Forbidden** |
| JWT có scope đọc nhưng không có permission cần thiết | Method authorization | **403 Forbidden** |
| JWT có permission nhưng Order 42 thuộc tenant khác | Resource policy | **403** hoặc **404**, theo chính sách |
| Nested role/permission tùy chọn thiếu | Converter không tạo authority tương ứng | Dẫn tới **403** nếu endpoint cần quyền đó |
| Nested claim bắt buộc sai schema | Token validator | **401** theo cách xử lý Bearer token |

Không dùng 403 để báo một chữ ký chưa xác minh rồi mặc định có danh tính. Ngược lại, một token hợp lệ nhưng thiếu scope/permission không cần bị xem là “chữ ký sai”. Ghi nhận đúng lớp lỗi giúp phân biệt sự cố nhà phát hành, mapping authority và policy nghiệp vụ.

## 13. Các lỗi triển khai phổ biến

### 13.1. Chỉ cấu hình `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName` với “đường dẫn”

Ví dụ dễ nhầm:

~~~java
converter.setAuthoritiesClaimName("realm_access.roles");
~~~

Đây không phải một JSONPath tổng quát đảm bảo lấy được mọi nested claim. Với object `realm_access`, phải truy cập object rồi lấy `roles` bằng converter riêng.

### 13.2. Dùng lại mọi role từ token mà không kiểm tra nguồn

Một token có `resource_access.billing-api.roles = ["admin"]` không có nghĩa người gọi là admin của Orders API. Lấy tất cả roles của mọi resource có thể tạo **cross-resource privilege escalation**.

### 13.3. Tưởng role nested tự được Spring Security hiểu

Spring JWT Resource Server không tự động chuyển mọi claim `roles`, `realm_access`, `resource_access` hoặc `authorization.permissions` thành authorities. Nếu expression `hasRole("ORDER_SUPPORT")` luôn bị 403, cần kiểm tra converter đã gắn vào SecurityFilterChain và mapping token có đúng schema không.

### 13.4. Quên giữ scope mặc định khi thay converter

Nếu custom converter chỉ trả roles, authority `SCOPE_orders.read` có thể biến mất. Endpoint yêu cầu scope sẽ bị 403 dù JWT có claim scope. Nếu muốn giữ behavior cũ, gọi `JwtGrantedAuthoritiesConverter` rồi gộp kết quả.

### 13.5. Dùng nhầm danh sách permission cho Resource Server khác

Permission object dành cho `reports` không tự là permission `orders`. Contract phải gắn permission với **resource/action cụ thể**, tránh cùng từ `read` nhưng khác ý nghĩa.

### 13.6. Đổi role thành prefix không nhất quán

Converter tạo `ROLE_ORDER_SUPPORT` nhưng config lại viết `hasAuthority("ORDER_SUPPORT")` sẽ không khớp. Nếu dùng `hasRole("ORDER_SUPPORT")`, cần hiểu nó thường kiểm tra `ROLE_ORDER_SUPPORT`.

### 13.7. Tin claim trước khi verify

Base64URL decode JWT rồi dùng `roles` để xây `SecurityContext` là sai. Claim phải đến từ token đã xác minh bằng issuer/JWKS/thuật toán/audience/thời hạn tin cậy.

### 13.8. Xem role trong JWT là trạng thái quyền tức thời

JWT đã cấp có thể giữ role/permission cũ đến khi hết hạn nếu chỉ xác minh offline. Với quyền thay đổi thường xuyên hoặc thao tác nhạy cảm, có thể cần access token sống ngắn, kiểm tra entitlement phía server, revocation/introspection hoặc policy service phù hợp.

### 13.9. Dùng `tenant_id` làm bằng chứng tự động về quyền

Token có `tenant_id = tenant-A` không đủ để đọc mọi bản ghi tenant-A. Cần xác nhận subject còn thuộc tenant, quyền áp dụng đúng nhóm/dữ liệu và trạng thái đơn. Không dựa vào tenant trong request body để mở rộng quyền.

### 13.10. Cố tạo một converter “đọc mọi issuer”

Cùng JSON path và cùng role name không đảm bảo cùng semantics giữa hai issuer. Với multi-issuer Resource Server, cần tách mapping theo issuer/profile đáng tin, tránh hợp nhất quyền không có hợp đồng.

## 14. Cân nhắc quyền theo token hay tra cứu động

Có hai chiến lược thường gặp:

| Chiến lược | Lợi ích | Giới hạn |
| --- | --- | --- |
| **Role/permission được AS nhúng vào JWT** | API có thể kiểm tra local sau khi verify; ít yêu cầu mạng | Permission có thể cũ, token lớn, cần hợp đồng schema chặt |
| **Resource Server tra cứu quyền từ database/policy service** | Có thể áp dụng quyền mới nhất và điều kiện nghiệp vụ | Phụ thuộc latency, cache, độ khả dụng và tính nhất quán |
| **Kết hợp** | Token mang identity/scope, backend tính policy từ dữ liệu hiện hành | Cần xác định trách nhiệm rõ, tránh hai nguồn cấp quyền mâu thuẫn |

Một thiết kế thường hợp lý là **JWT chứa scope và thông tin identity**, converter ánh xạ một số role/permission có ý nghĩa ổn định, còn API kiểm tra owner/tenant/assignment từ database. Nếu cần thu hồi quyền ngay khi tài khoản bị khóa, token claims không đủ nếu thiếu chiến lược kiểm tra trạng thái.

## 15. Mẫu tài liệu hợp đồng dành cho team Identity và API

Trước khi triển khai converter, hai team có thể duy trì tài liệu ngắn:

~~~yaml
# Hợp đồng minh họa, không phải file Spring đọc tự động.
resource_server: orders-api
trusted_issuer: https://id.example.test/realms/shop
expected_audience: orders-api
token_type: oauth2_access_token

claims:
  oauth_scopes:
    path: scope
    type: "space-delimited string"
    authority_prefix: "SCOPE_"
  realm_roles:
    path: realm_access.roles
    type: "array<string>"
    allowed:
      platform_auditor: ROLE_PLATFORM_AUDITOR
  api_roles:
    path: resource_access["orders-api"].roles
    type: "array<string>"
    allowed:
      order_support: ROLE_ORDER_SUPPORT
      tenant_admin: ROLE_TENANT_ADMIN
  permissions:
    path: authorization.permissions
    type: "array<object>"
    filter_resource: orders
    resource_scopes:
      "read:own": "PERM_order:read:own"
      "read:tenant": "PERM_order:read:tenant"
      "cancel:own": "PERM_order:cancel:own"

authorization:
  read_orders:
    required_scope: orders.read
    required_any_permission:
      - PERM_order:read:own
      - PERM_order:read:tenant
    data_policy: "owner/tenant/assignment must match"
  cancel_orders:
    required_scope: orders.cancel
    required_permission: PERM_order:cancel:own
    data_policy: "owner matches and order state allows cancellation"

missing_optional_claims: no_authority_granted
unrecognized_role_or_permission: ignored
missing_required_claims: invalid_token
~~~

Tài liệu này cần bổ sung nếu production có nhiều issuer, nhiều tenant, Client Credentials, claim nested kiểu khác, token profile riêng, role hierarchy hoặc permission động. Khi schema thay đổi, **đổi hợp đồng trước, cập nhật converter và policy cùng nhau**, tránh API cũ vô tình diễn giải claim mới theo nghĩa quá rộng.

## 16. Câu hỏi tình huống để tự luyện

**Tình huống A — Token có role Billing Admin:** JWT hợp lệ có `resource_access.billing-api.roles = ["billing_admin"]` nhưng không có role dưới `orders-api`. Orders API có được cấp `ROLE_TENANT_ADMIN` không?

**Không.** Converter chỉ đọc role của resource/client mà Orders API có hợp đồng. Role của Billing API không được thừa kế tự động.

**Tình huống B — Token có role Support nhưng thiếu scope:** JWT có `resource_access.orders-api.roles = ["order_support"]` nhưng `scope` chỉ là `profile`. Endpoint yêu cầu `SCOPE_orders.read`. Kết quả?

Theo hợp đồng ví dụ, **403 Forbidden**. Role không thay thế scope nếu policy yêu cầu cả hai.

**Tình huống C — Token có permission không được allowlist:** `authorization.permissions` ghi `resource = orders`, `scopes = ["delete:all"]`. Converter có tự tạo `PERM_order:delete:all` không?

**Không.** Bảng mapping chỉ có các action đã được thỏa thuận, permission lạ không tạo quyền mới.

**Tình huống D — JWT chưa xác minh nhưng có nested admin role:** Developer decode payload và tạo `ROLE_TENANT_ADMIN` rồi mới kiểm tra signature. Sai ở đâu?

Developer đã **dùng dữ liệu chưa đáng tin để xác thực/phân quyền**. Việc trích role phải nằm sau `JwtDecoder` hoàn tất xác minh token.

**Tình huống E — Scope và permission đúng, order thuộc tenant khác:** JWT mang `SCOPE_orders.read`, `PERM_order:read:tenant`, nhưng order thuộc tenant không nằm trong phạm vi được cấp. Có cho phép đọc?

**Không.** Permission cho biết loại khả năng; owner/tenant/assignment trên bản ghi vẫn phải đáp ứng chính sách.

**Tình huống F — Unit test dùng `Jwt.withTokenValue(...)` đã pass:** Có thể tuyên bố JWS/JWKS và issuer/audience verification đã hoạt động?

**Chưa.** Unit test converter chỉ chứng minh ánh xạ. Cần integration test với JWT ký thật qua decoder để kiểm chứng ranh giới xác thực.

**Tình huống G — AS thêm role mới `order_manager`:** Nếu converter dùng bảng allowlist và chưa có mapping, role mới có trở thành authority tự động?

**Không.** Đây là hành vi mong muốn: việc mở quyền mới yêu cầu cập nhật hợp đồng và quyết định của đội API.

---

## Kết luận

**Roles và permissions lồng trong JWT là dữ liệu theo hợp đồng của nhà phát hành, không phải một cơ chế phân quyền tự động của Spring Security.** `JwtGrantedAuthoritiesConverter` mặc định chủ yếu xử lý OAuth2 scope; muốn dùng những đường dẫn như `realm_access.roles`, `resource_access["orders-api"].roles` và `authorization.permissions[].scopes`, ứng dụng cần converter tùy chỉnh để đọc đúng cấu trúc, giới hạn nguồn/resource, ánh xạ qua **bảng quyền cho phép** và gộp authorities với prefix rõ ràng.

Trong mọi trường hợp, **xác minh chữ ký, issuer, audience, thời hạn và token profile trước khi sử dụng claims**. Converter không thay thế validator và không nên tự mở rộng quyền chưa được thỏa thuận. Sau khi có `SCOPE_`, `ROLE_` và `PERM_`, Resource Server vẫn phải kiểm tra **quyền trên tài nguyên cụ thể** theo owner, tenant, trạng thái và policy của hệ thống.
