# Kết hợp nhiều nguồn authority mà không nhân đôi hoặc nâng quyền ngoài ý muốn

## 1. Bài toán trong OAuth 2.0 Resource Server

Một Spring Security Resource Server có thể nhận JWT access token với nhiều thông tin liên quan quyền:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.export orders.read",
  "app_roles": ["ORDER_VIEWER", "ORDER_VIEWER", "ORDER_EDITOR"],
  "groups": ["customer-support"],
  "tenant_id": "tenant-42",
  "exp": 2000000000
}
~~~

Đây là phần payload minh họa, không phải JWT đã ký thật. Những trường này có ý nghĩa khác nhau:

- `scope`: phạm vi được ủy quyền cho **access token cụ thể**.
- `app_roles`: vai trò ứng dụng, nhưng chỉ đáng tin nếu issuer được phép phát hành role cho API đó.
- `groups`: nhóm tổ chức, không mặc nhiên tương đương role của API.
- `tenant_id`: phạm vi dữ liệu, không phải role toàn cục.
- Local entitlements trong database: quyền do ứng dụng sở hữu, có thể thay đổi độc lập với JWT.
- ACL/ownership: quyền đối với một bản ghi cụ thể.

Sau khi xác thực JWT, Spring Security xây `Authentication` chứa các `GrantedAuthority`. Nếu gộp các nguồn một cách tùy tiện, có thể tạo hai lỗi:

1. **Trùng authority:** `SCOPE_orders.read` hoặc `ROLE_ORDER_VIEWER` xuất hiện nhiều lần do nhiều converter hoặc claims lặp.
2. **Nâng quyền ngoài ý muốn:** một nguồn chỉ được phép *hạn chế* quyền lại vô tình được dùng để *mở thêm* quyền, chẳng hạn local role tạo ra OAuth scope mà access token không được cấp.

**Mục tiêu:** thiết kế mapping authorities đúng namespace/issuer/profile, loại bỏ bản sao, và áp dụng các điều kiện authorization theo **AND** khi cần đồng thời scope, local entitlement và quyền tài nguyên.

## 2. Cách Spring Security tạo authorities từ JWT

### 2.1. `GrantedAuthority`

Spring Security dùng interface:

~~~java
org.springframework.security.core.GrantedAuthority
~~~

Implementation thường dùng:

~~~java
new SimpleGrantedAuthority("SCOPE_orders.read");
new SimpleGrantedAuthority("ROLE_ORDER_VIEWER");
~~~

Rule:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

kiểm tra **đúng tên authority**; `SCOPE_orders.read.all` hoặc `ROLE_ORDER_VIEWER` không tự tương đương.

### 2.2. `JwtGrantedAuthoritiesConverter` mặc định

Với JWT Resource Server:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

`JwtGrantedAuthoritiesConverter` thường đọc claim `scope` hoặc `scp` phù hợp với profile và thêm tiền tố `SCOPE_`.

Ví dụ:

~~~json
{"scope": "orders.read orders.export"}
~~~

cho kết quả:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Custom claims như `app_roles`, `groups`, `permissions` **không tự động** trở thành Spring roles trong mọi cấu hình. Nếu dùng các claim này, cần tự xây converter và validation.

### 2.3. Vị trí conversion trong pipeline

~~~mermaid
flowchart TD
    A["Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["JwtDecoder: signature/issuer/audience/time"]
    D --> E{"Token hợp lệ?"}
    E -->|"Không"| F["Authentication failure: thường 401"]
    E -->|"Có"| G["JwtAuthenticationConverter"]
    G --> H["Scope converter và application role converter"]
    H --> I["Hợp nhất và khử trùng GrantedAuthority"]
    I --> J["JwtAuthenticationToken trong SecurityContext"]
    J --> K["AuthorizationFilter hoặc method security"]
    K --> L["Kiểm tra quyền endpoint và bản ghi"]
~~~

**Converter không thay thế validator.** Một claim `roles` chỉ có thể được dùng làm nguồn authority sau khi JWT có chữ ký hợp lệ, đúng issuer/audience, còn hạn và đúng hợp đồng claims.

## 3. Hợp đồng cấp authority và ranh giới tin cậy

Trước khi map quyền, cần quyết định **nguồn nào có thẩm quyền cấp loại quyền nào**.

| Nguồn dữ liệu | Dạng minh họa | Được phép cấp | Không nên tự cấp |
|---|---|---|---|
| JWT `scope` | `orders.read` | `SCOPE_orders.read` | `ROLE_ADMIN` |
| JWT `scp` | `["orders.read"]` | Theo profile issuer nếu được chọn | Không tự cộng cả `scp` và `scope` chưa thống nhất |
| JWT `app_roles` | `["ORDER_VIEWER"]` | `ROLE_ORDER_VIEWER` qua allowlist | Role lạ hoặc của API khác |
| JWT `groups` | `["customer-support"]` | Chỉ theo mapping được phê duyệt | `ROLE_ADMIN` từ tên nhóm chứa `admin` |
| Database entitlement | `CAN_APPROVE_ORDER` | Điều kiện authorization hiện tại | Không tự tạo OAuth scope approve |
| Tenant/ACL | `tenant-42` / owner | Phạm vi đối tượng được đọc/sửa | Global role trên tất cả tenant |
| HTTP request header | `X-Roles: ADMIN` | Không cấp authority | Không tin như chứng thực |
| Query/body input | `role=admin` | Không cấp authority | Không sửa Authentication để mở quyền |

Hợp đồng ví dụ cho Orders API:

~~~text
Issuer được tin:
  https://id.example.test/realms/shop

Audience bắt buộc:
  orders-api

Scope:
  claim scope là String phân cách bằng khoảng trắng
  scope nhận diện: orders.read, orders.write, orders.export

Application role:
  claim app_roles là Array<String> tùy chọn
  allowlist: ORDER_VIEWER, ORDER_EDITOR

Output:
  SCOPE_<scope>
  ROLE_<app_role>

Không tự chuyển:
  groups -> roles
  tenant_id -> role toàn cục
  database entitlement -> OAuth scope
~~~

**Issuer và audience đều cần kiểm tra.** Một JWT có chữ ký hợp lệ của cùng IdP nhưng được phát hành cho `billing-api` không tự được dùng để tạo Orders API authorities. Đối với nhiều issuer, không áp một mapping role giống nhau nếu ý nghĩa role khác nhau theo issuer.

## 4. Ba thao tác: union, deduplication và AND

### 4.1. Union: hợp hai nguồn cấp authority

Giả sử:

~~~text
Scopes A = {SCOPE_orders.read, SCOPE_orders.export}
Roles  B = {ROLE_ORDER_VIEWER, ROLE_ORDER_EDITOR}
~~~

Kết quả union:

~~~text
A ∪ B = {
  SCOPE_orders.read,
  SCOPE_orders.export,
  ROLE_ORDER_VIEWER,
  ROLE_ORDER_EDITOR
}
~~~

Union phù hợp **khi cả A và B là nguồn được phê duyệt để cấp những authority tương ứng**. Nó là phép cộng quyền, nên phải kiểm tra trust/policy.

### 4.2. Deduplication: loại bản sao trùng

~~~text
Đầu vào:
  SCOPE_orders.read
  SCOPE_orders.read
  ROLE_ORDER_VIEWER
  ROLE_ORDER_VIEWER

Đầu ra:
  SCOPE_orders.read
  ROLE_ORDER_VIEWER
~~~

Khử trùng giúp tập quyền nhất quán cho logs, tests và custom code. Tuy nhiên **khử trùng không tự bảo vệ khỏi escalation**: nếu một nguồn giả mạo đưa `ROLE_SUPER_ADMIN` vào tập, `Set` vẫn giữ một quyền admin đó.

### 4.3. AND: nhiều nguồn phải cùng cho phép

Một người dùng có thể có local permission để approve order, nhưng token được cấp cho một OAuth client chỉ có `orders.read`. Nếu ứng dụng cho approve chỉ dựa trên local permission, nó đã vượt scope token.

Quy tắc an toàn cho API đòi cả hai:

~~~text
ALLOW_APPROVE_ORDER =
    valid JWT
    AND has SCOPE_orders.approve
    AND local entitlement APPROVE is active
    AND tenant/ownership policy allows order
~~~

Không dùng:

~~~text
ALLOW_APPROVE_ORDER =
    has SCOPE_orders.approve
    OR local entitlement APPROVE
~~~

**“Giao quyền” giữa scope và entitlement thường là phép AND giữa điều kiện**, không nhất thiết giao tập String vì hai nguồn dùng các namespace khác nhau.

Ví dụ sai khi cần AND:

~~~java
.hasAnyAuthority(
    "SCOPE_orders.approve",
    "PERM_ORDER_APPROVE"
)
~~~

`hasAnyAuthority` kiểm tra **OR**. Phải định nghĩa AND qua authorization manager hoặc method security nếu cả hai là bắt buộc.

## 5. Phân biệt namespace `SCOPE_`, `ROLE_` và `PERM_`

Các String:

~~~text
SCOPE_admin
ROLE_ADMIN
PERM_ADMIN
~~~

không giống nhau và không có quyền tương đương mặc định. Không bỏ hết tiền tố để hợp nhất chúng thành một `ADMIN`.

- `SCOPE_`: OAuth scope được cấp cho token.
- `ROLE_`: vai trò ứng dụng đã được ánh xạ từ nguồn được ủy quyền.
- `PERM_`: permission nội bộ nếu ứng dụng chủ động định nghĩa.

Dùng `hasAuthority("ROLE_ORDER_VIEWER")` để kiểm tra chính xác. Với prefix role mặc định, `hasRole("ORDER_VIEWER")` thường đòi authority `ROLE_ORDER_VIEWER`; tránh dùng `hasRole("ROLE_ORDER_VIEWER")` như thể Spring sẽ không thêm prefix.

Không dùng `contains("ADMIN")` hoặc `contains("orders.read")` trên một chuỗi lớn để cấp quyền. Các giá trị `READ_ONLY_ADMIN_VIEW` và `orders.read.all` có thể chứa chuỗi con nhưng không đại diện quyền mong muốn.

**Case sensitivity:** `ROLE_ORDER_VIEWER` không mặc nhiên tương đương `ROLE_order_viewer`. Nên có hợp đồng canonical role, không tự upper-case hoặc strip prefix từ mọi nguồn quyền.

## 6. Khử trùng authorities bằng `LinkedHashSet`

Một cách đơn giản:

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import org.springframework.security.core.GrantedAuthority;

public final class AuthorityCombiner {

    private AuthorityCombiner() {}

    public static List<GrantedAuthority> unique(
            Collection<? extends GrantedAuthority> left,
            Collection<? extends GrantedAuthority> right) {

        LinkedHashSet<GrantedAuthority> result =
            new LinkedHashSet<>();

        result.addAll(left);
        result.addAll(right);

        return List.copyOf(result);
    }
}
~~~

`LinkedHashSet` loại phần tử trùng theo equals/hashCode và giữ thứ tự thêm. Với `SimpleGrantedAuthority`, so sánh được dựa trên authority string.

Nếu custom `GrantedAuthority` implementation có equals/hashCode khác, cần xác định “trùng” theo đối tượng hay theo **`getAuthority()`**. Có thể dùng `LinkedHashMap<String, GrantedAuthority>` để loại trùng theo tên:

~~~java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class AuthorityNameCombiner {

    private AuthorityNameCombiner() {}

    public static List<GrantedAuthority> uniqueByName(
            Collection<? extends GrantedAuthority> input) {

        Map<String, GrantedAuthority> byName = new LinkedHashMap<>();

        for (GrantedAuthority value : input) {
            if (value == null) {
                continue;
            }
            String name = value.getAuthority();
            if (name == null || name.isBlank()) {
                continue;
            }

            byName.putIfAbsent(
                name, new SimpleGrantedAuthority(name));
        }

        return List.copyOf(byName.values());
    }
}
~~~

**Chỉ chạy hàm sau khi từng nguồn đã được xác minh và map đúng contract.** Đừng biến dedup thành một nơi “sửa” tên không đáng tin thành authority có quyền cao hơn.

## 7. Converter kết hợp scope và app role có allowlist

Giả sử issuer phát hành `app_roles` với các giá trị được công nhận:

~~~text
ORDER_VIEWER
ORDER_EDITOR
~~~

Chỉ hai giá trị này được map thành:

~~~text
ROLE_ORDER_VIEWER
ROLE_ORDER_EDITOR
~~~

### 7.1. Cấu hình `JwtAuthenticationConverter`

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

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

    private static final Set<String> ALLOWED_ROLES =
        Set.of("ORDER_VIEWER", "ORDER_EDITOR");

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

        // Contract của issuer dùng claim "scope" dạng String.
        scopeConverter.setAuthoritiesClaimName("scope");
        scopeConverter.setAuthorityPrefix("SCOPE_");

        Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
            LinkedHashSet<GrantedAuthority> authorities =
                new LinkedHashSet<>();

            Collection<GrantedAuthority> scopes =
                scopeConverter.convert(jwt);

            if (scopes != null) {
                authorities.addAll(scopes);
            }

            Object raw = jwt.getClaims().get("app_roles");

            if (raw instanceof Collection<?> roles) {
                for (Object item : roles) {
                    if (item instanceof String role
                            && ALLOWED_ROLES.contains(role)) {
                        authorities.add(
                            new SimpleGrantedAuthority("ROLE_" + role));
                    }
                }
            }

            return List.copyOf(authorities);
        };

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(combined);
        return converter;
    }
}
~~~

Với token:

~~~json
{
  "scope": "orders.read orders.read orders.export",
  "app_roles": ["ORDER_VIEWER", "ORDER_VIEWER"]
}
~~~

kết quả cần là:

~~~text
SCOPE_orders.read
SCOPE_orders.export
ROLE_ORDER_VIEWER
~~~

**Tại sao cách này hạn chế escalation?**

- `scope` chỉ được chuyển sang namespace `SCOPE_`.
- `app_roles` chỉ sinh `ROLE_...` sau khi đối chiếu **allowlist**.
- Không tự đọc `groups` hoặc mọi custom claim khác.
- Không tạo `SCOPE_orders.write` từ việc user có role editor; scope token vẫn là nguồn quyết định OAuth scopes.
- `LinkedHashSet` khử trùng.
- Không nhận `SUPER_ADMIN` vì nó không thuộc contract.

Điều này **chưa đủ cho toàn bộ bảo mật**: JWT vẫn phải qua signature, issuer, audience và claim validators trước khi mapping, và authorization vẫn cần kiểm tra scope/entitlement/tenant.

### 7.2. Role claim sai kiểu thì xử lý thế nào?

Converter trên chỉ bỏ qua giá trị không hợp lệ nên không cấp thêm quyền. Tuy nhiên, nếu hợp đồng yêu cầu `app_roles` khi có mặt phải là Array<String> trong allowlist, nên **từ chối token ở JwtDecoder validator**. Không nên để một issuer đang phát hành sai schema trôi qua âm thầm, nhất là khi các claims khác ảnh hưởng quyền.

Ví dụ:

~~~json
{"app_roles": "ORDER_VIEWER"}
~~~

hoặc:

~~~json
{"app_roles": ["ORDER_VIEWER", 42]}
~~~

đều vi phạm contract Array<String>. Không tự ép String thành array hoặc Number thành role.

## 8. Nối converter vào Resource Server

Dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
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
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

`issuer-uri` và `audiences` cần phù hợp Authorization Server/API thực tế; property audience có sẵn trong các Spring Boot version hỗ trợ nó. Các giá trị ở đây là ví dụ.

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtAuthenticationConverter)
                )
            );

        return http.build();
    }
}
~~~

Khi có nhiều converter/decoder beans, dùng explicit wiring hoặc `@Qualifier`. Chain trên chỉ khớp `/api/**`; ứng dụng production cần bảo vệ các đường dẫn khác bằng chain phù hợp.

Tùy chỉnh `JwtAuthenticationConverter` **không tự đổi JWT validation**. Nếu tự tạo `JwtDecoder` bean, Spring Boot có thể ngừng auto-configure decoder, và ứng dụng phải giữ issuer/time/audience/token profile validators một cách tường minh.

## 9. `DelegatingJwtGrantedAuthoritiesConverter`: cách composition có sẵn

Spring Security cũng có **`DelegatingJwtGrantedAuthoritiesConverter`** để chạy nhiều converters và tổng hợp authorities, với cơ chế loại trùng trong quá trình kết hợp.

Ví dụ cấu trúc:

~~~java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();

scopes.setAuthoritiesClaimName("scope");
scopes.setAuthorityPrefix("SCOPE_");

Converter<Jwt, Collection<GrantedAuthority>> appRoles =
    jwt -> trustedAppRoleAuthorities(jwt);

DelegatingJwtGrantedAuthoritiesConverter combined =
    new DelegatingJwtGrantedAuthoritiesConverter(scopes, appRoles);

JwtAuthenticationConverter authConverter =
    new JwtAuthenticationConverter();

authConverter.setJwtGrantedAuthoritiesConverter(combined);
~~~

Imports:

~~~java
import java.util.Collection;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
~~~

`trustedAppRoleAuthorities(jwt)` là helper **do ứng dụng phải tự triển khai**, áp dụng allowlist như phần 7; đó không phải hàm Spring có sẵn. Ví dụ ở phần 7 trình bày implementation đầy đủ không cần helper này.

Delegation phù hợp khi mỗi nguồn có converter riêng. Nhưng nó chỉ **hợp nhất authorities**, không hiểu nguồn nào được phép cấp quyền, không xác minh role schema, và **không tự biến union thành điều kiện AND**. Phải giữ trust policy/validators và authorization rules.

## 10. Validate custom role claim khi tạo JwtDecoder riêng

Để từ chối JWT có `app_roles` sai kiểu hoặc không thuộc allowlist, gắn `OAuth2TokenValidator<Jwt>`. Ví dụ:

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.Set;

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
public class JwtContractConfig {

    private static final String ISSUER =
        "https://id.example.test/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    private static final Set<String> ALLOWED_ROLES =
        Set.of("ORDER_VIEWER", "ORDER_EDITOR");

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return invalid("Token audience is not orders-api");
        };

        OAuth2TokenValidator<Jwt> appRolesSchema = jwt -> {
            Object raw = jwt.getClaims().get("app_roles");

            if (raw == null) {
                return OAuth2TokenValidatorResult.success();
            }

            if (!(raw instanceof Collection<?> roles)
                    || roles.size() > 20) {
                return invalid("Invalid app_roles type or size");
            }

            for (Object value : roles) {
                if (!(value instanceof String role)
                        || !ALLOWED_ROLES.contains(role)) {
                    return invalid("Unknown app role");
                }
            }

            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience,
                appRolesSchema
            )
        );

        return decoder;
    }

    private static OAuth2TokenValidatorResult invalid(String reason) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", reason, null)
        );
    }
}
~~~

Ý nghĩa:

1. `NimbusJwtDecoder` xác minh chữ ký bằng khóa công khai đáng tin.
2. `JwtValidators.createDefaultWithIssuer(ISSUER)` ràng buộc issuer và các điều kiện thời gian cơ bản.
3. Audience validator từ chối access token dành cho API khác.
4. Custom role validator từ chối claim `app_roles` không đúng contract.
5. Converter chỉ ánh xạ những role nằm trong allowlist.

**Tầng converter nhận một `Jwt` sau quá trình claim conversion**. Nếu profile yêu cầu strict JSON wire type cho registered claims như `aud`/`exp`, có thể cần kiểm soát claim-set converter/parser thêm; không được bỏ xác minh chữ ký để tự tin dữ liệu JSON thô.

**Chú ý bean override:** khi tạo `JwtDecoder` riêng, các Boot properties tiện lợi không nhất thiết còn tự nối vào decoder này. Không làm mất validation issuer, thời hạn, audience, token type và custom claims. `setJwtValidator(...)` thay validator đang đặt, nên hãy kết hợp đầy đủ.

## 11. Local entitlement không được tự cấp thêm OAuth scope

Một user có thể có quyền nội bộ `APPROVE_ORDER` trong database, nhưng access token hiện tại chỉ có:

~~~json
{"scope": "orders.read"}
~~~

Nếu converter đọc DB rồi tự thêm `SCOPE_orders.approve` cho user, token đã được **nâng quyền vượt phạm vi được cấp**. Nếu endpoint dùng `hasAnyAuthority("SCOPE_orders.approve", "PERM_ORDER_APPROVE")`, local permission có thể mở quyền approve dù token thiếu scope.

Khi hợp đồng đòi hai điều kiện, nên biểu diễn:

~~~text
ALLOW_APPROVE =
    JWT has SCOPE_orders.approve
    AND user has active APPROVE entitlement
    AND current order policy allows action
~~~

Đừng đồng nhất:

- **Token scope:** client/token được phép yêu cầu loại hành động nào.
- **User entitlement:** user/service hiện được tổ chức cho phép làm gì.
- **Resource ownership/ACL:** caller có được làm hành động trên bản ghi cụ thể không.

Ba lớp bảo vệ này có thể cần đồng thời đúng. Không đơn giản union ba nguồn rồi dùng một rule OR.

## 12. Method security dùng AND với entitlement hiện tại

Để tránh đẩy toàn bộ local permissions vào `JwtAuthenticationConverter`, có thể kiểm tra chúng ở service.

Bật method security:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {}
~~~

Service:

~~~java
package com.example.orders.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrdersService {

    private final OrderRepository repository;

    public OrdersService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @ordersPolicy.canRead(authentication, #orderId)"
    )
    public OrderDto loadOrder(long orderId) {
        return repository.findOrderDto(orderId);
    }
}
~~~

Policy:

~~~java
package com.example.orders.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component("ordersPolicy")
public class OrdersPolicy {

    private final OrderAccessRepository access;

    public OrdersPolicy(OrderAccessRepository access) {
        this.access = access;
    }

    public boolean canRead(Authentication authentication, long orderId) {
        if (authentication == null
                || !(authentication.getPrincipal() instanceof Jwt jwt)) {
            return false;
        }

        Object raw = jwt.getClaims().get("tenant_id");
        String subject = jwt.getSubject();

        if (!(raw instanceof String tenant)
                || tenant.isBlank()
                || subject == null
                || subject.isBlank()) {
            return false;
        }

        // Xác nhận quyền còn hiệu lực và đối tượng đúng tenant.
        return access.canReadOrder(subject, tenant, orderId);
    }
}
~~~

Các `OrderRepository`, `OrderAccessRepository`, `OrderDto` và phương thức `canReadOrder` là thành phần nghiệp vụ minh họa phải tự triển khai. Query thật cần kết hợp tenant, owner/ACL, entitlement và trạng thái nghiệp vụ phù hợp.

Ở luồng này:

1. Token cần hợp lệ để tạo `Authentication`.
2. `@PreAuthorize` đòi `SCOPE_orders.read`.
3. Policy kiểm tra entitlement ở thời điểm request và tenant của order.
4. Bất kỳ điều kiện nào không đạt → từ chối.
5. Không dùng query/header của client làm bằng chứng có authority.

Với method security dựa trên proxy, lưu ý **self-invocation** có thể bỏ qua advice. SpEL `#orderId` cũng cần tên tham số được resolve (ví dụ compiler `-parameters` trong Java tùy cấu hình). Kiểm thử thực tế các boundary này.

Nếu database/policy service lỗi, **không trả true mặc định**. Lỗi hạ tầng có thể được báo thành service error, nhưng không cấp quyền.

## 13. Tenant và multi-issuer làm bài toán khó hơn

### 13.1. Role không tự toàn cục qua mọi tenant

Một token:

~~~json
{
  "scope": "orders.read",
  "app_roles": ["ORDER_VIEWER"],
  "tenant_id": "tenant-42"
}
~~~

không có nghĩa caller được xem đơn hàng thuộc `tenant-99`. Dù có `ROLE_ORDER_VIEWER`, API vẫn phải kiểm tra quyền với **tenant/resource** của request.

Nếu issuer phát hành roles theo từng tenant, không union mọi tenant role thành global authority. Phải có rule chọn tenant hợp lệ và kiểm tra resource scope tương ứng.

### 13.2. Role của issuer A không tự bằng role của issuer B

Issuer A có `roles: ["EDITOR"]` và Issuer B cũng có `roles: ["EDITOR"]` nhưng quyền trên hệ thống khác. Nếu Resource Server tin nhiều issuer, không nên có một converter chung biến mọi `EDITOR` thành `ROLE_ORDER_EDITOR`.

Cần:

- Allowlist trusted issuers.
- Xác minh JWT với key/validators đúng issuer.
- Kiểm tra audience `orders-api`.
- Ánh xạ role theo **issuer-specific policy**.
- Kiểm tra entitlement cục bộ và tenant/ownership nếu cần.

`JwtIssuerAuthenticationManagerResolver` là một extension point Servlet Resource Server cho multi-issuer. Claim `iss` ban đầu chỉ là **routing hint chưa được xác minh**; không cho phép load metadata/keys từ issuer tùy ý do token quảng bá.

## 14. Dynamic permissions và thu hồi quyền

JWT access token có thể còn hạn sau khi user bị thu hồi role trong hệ thống. Nếu tất cả quyền được đóng gói vào JWT lúc phát hành, Resource Server không mặc nhiên biết thay đổi entitlement mới.

Cân nhắc theo độ nhạy của hành động:

- Giảm access token lifetime.
- Kiểm tra local permission hiện thời cho endpoint quan trọng.
- Token introspection/denylist/revocation nếu kiến trúc hỗ trợ.
- Cache entitlement với TTL/invalidation phù hợp.
- Kiểm tra ownership/tenant lúc xử lý đối tượng.

**JWKS cache không phải cache quyền user.** JWKS lưu public keys để verify JWT. Cache local entitlements hoặc authorization decisions là thiết kế khác, có nguy cơ kéo dài thời gian sử dụng quyền đã bị thu hồi nếu cấu hình sai.

## 15. Kiểm thử để phát hiện nâng quyền ngoài ý muốn

### 15.1. Ma trận converter

| JWT claims | Kết quả kỳ vọng |
|---|---|
| `scope: "orders.read"` | `SCOPE_orders.read` |
| `scope: "orders.read orders.read"` | Một `SCOPE_orders.read` |
| `app_roles: ["ORDER_VIEWER"]` | `ROLE_ORDER_VIEWER` |
| `app_roles: ["ORDER_VIEWER", "ORDER_VIEWER"]` | Một `ROLE_ORDER_VIEWER` |
| Không có `app_roles` | Không thêm role |
| `app_roles: "ORDER_VIEWER"` | Sai schema; validator từ chối |
| `app_roles: [42]` | Sai schema; validator từ chối |
| `app_roles: ["SUPER_ADMIN"]` | Không cấp admin; validator từ chối |
| `groups: ["admins"]` | Không tạo `ROLE_ADMIN` |
| `scope` và `app_roles` hợp lệ | Mỗi authority có một bản sao, namespace giữ nguyên |
| Token đúng issuer nhưng audience khác | Bị từ chối trước authority mapping |
| Header `X-Roles: ADMIN` từ client | Không ảnh hưởng authorities |

### 15.2. Ma trận AND

| Có scope `orders.read`? | Local entitlement + tenant cho phép? | Kết quả |
|---|---|---|
| Không | Không | Deny |
| Không | Có | Deny |
| Có | Không | Deny |
| Có | Có | Allow |

Nếu hàng “không scope, có DB permission” được cho phép, chính sách đã vô tình biến AND thành OR.

### 15.3. MockMvc kiểm tra rule khác test converter

Spring Security Test có helper:

~~~java
mockMvc.perform(
    get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"),
            new SimpleGrantedAuthority("ROLE_ORDER_VIEWER")
        ))
);
~~~

Điều này mô phỏng `Authentication` đã có authorities để test authorization. Nó **không chứng minh** rằng converter custom đã đọc claims chính xác hoặc JWT decoder đã xác minh chữ ký/issuer/audience.

Nên có ba lớp test:

1. **Converter tests:** xây `Jwt` có claims và kiểm tra set authorities đúng, không lặp, không unknown role.
2. **Validator tests:** sai kiểu/unknown roles, issuer/audience không đúng, token thiếu claim bắt buộc.
3. **Integration tests:** gửi Bearer JWT test được ký qua Resource Server thật, kiểm tra 401/403, scope + local entitlement + tenant/ACL.

Đừng sửa payload của token thật rồi kết luận custom role validator hoạt động; sửa JWT payload thường làm chữ ký sai trước khi tới validator.

## 16. Sai lầm thường gặp

### 16.1. “Có `Set` là không thể privilege escalation”

Sai. `Set` chỉ loại bản sao. Quyền `ROLE_ADMIN` từ nguồn không đáng tin vẫn nguy hiểm dù chỉ xuất hiện một lần.

### 16.2. “Group, role và scope chỉ khác cách đặt tên”

Sai. Chúng có nguồn, ý nghĩa và phạm vi khác nhau; chỉ được ánh xạ theo hợp đồng cụ thể.

### 16.3. “Database có quyền thì access token cũng phải có scope tương ứng”

Sai. Local entitlement không tự mở rộng OAuth scope. Nếu cần cả hai, dùng AND.

### 16.4. “Role chứa chữ admin thì là admin”

Sai. Không kiểm tra bằng substring; chỉ dùng exact role trong allowlist. Không tự map một group tên `admins` thành `ROLE_ADMIN`.

### 16.5. “Mọi role có thể bỏ tiền tố rồi chuẩn hóa”

Không tự cắt `ROLE_` hoặc thay đổi hoa/thường bất kỳ. Hợp đồng phải nói rõ role value và converter tạo authority nào.

### 16.6. “Một converter dùng cho mọi issuer”

Có thể nguy hiểm nếu các issuer có role semantics khác nhau. Cần per-issuer mapping, trusted allowlist và đúng audience.

### 16.7. “Có authority đọc thì xem được mọi bản ghi”

Sai. Authorization theo endpoint còn cần tenant/owner/ACL theo tài nguyên.

### 16.8. “Quyền local được cache lâu sẽ không có vấn đề”

Nếu quyền bị thu hồi nhưng cache chưa invalidated, caller có thể tiếp tục được phép. Quy định rõ độ trễ thu hồi và fail-closed khi policy không xác minh được.

## 17. Sơ đồ kết luận

~~~mermaid
flowchart TD
    A["Bearer JWT"] --> B["Verify JWT: signature + iss + aud + expiry"]
    B --> C{"Hợp lệ?"}
    C -->|Không| X["401"]
    C -->|Có| D["Trusted scopes -> SCOPE_*"]
    C --> E["Validated app_roles allowlist -> ROLE_*"]
    D --> F["Union có kiểm soát + dedup"]
    E --> F
    F --> G["Authentication trong SecurityContext"]
    G --> H{"Có scope cho action?"}
    H -->|Không| Y["403"]
    H -->|Có| I{"Local entitlement hiện thời?"}
    I -->|Không| Y
    I -->|Có| J{"Tenant/owner/ACL hợp lệ?"}
    J -->|Không| Y
    J -->|Có| K["Cho phép thao tác"]
~~~

**Kết luận:** việc kết hợp authorities gồm **xác định nguồn đáng tin**, **ánh xạ theo contract**, **khử trùng**, sau đó **kiểm tra policy độc lập**. Không được xem phép union như cách thay thế mọi điều kiện quyền. OAuth scope có thể giới hạn hành động client được ủy quyền, còn local entitlement và tenant/ownership giới hạn quyền thực hiện trên dữ liệu. Với endpoint cần cả ba, sử dụng **AND** chứ không phải OR.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html)
- [Spring Security API — DelegatingJwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/DelegatingJwtGrantedAuthoritiesConverter.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security API — GrantedAuthority](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/GrantedAuthority.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)

