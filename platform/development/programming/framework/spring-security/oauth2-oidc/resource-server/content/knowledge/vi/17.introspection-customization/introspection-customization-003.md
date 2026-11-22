# Chuẩn hóa principal và ánh xạ roles, permissions sau introspection

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, opaque access token thường không mang một payload JWT mà API có thể tự đọc và xác minh. Thay vào đó, Resource Server gửi token tới **OAuth 2.0 Token Introspection Endpoint** của Authorization Server (AS). Sau khi AS xác nhận token hợp lệ, Spring Security tạo một `OAuth2AuthenticatedPrincipal` chứa các thuộc tính và những `GrantedAuthority` mà API có thể dùng để phân quyền.

Nhu cầu thực tế là **chuẩn hóa principal** và **ánh xạ roles, permissions** khi response của AS không giống hoàn toàn mô hình dữ liệu của ứng dụng. Chẳng hạn AS trả `sub`, `username`, `scope`, `roles`, `permissions` và `tenant_id`, còn các endpoint Spring Security cần những chuỗi như `SCOPE_orders.read`, `ROLE_ORDERS_MANAGER` hay `PERM_ORDERS_EXPORT`.

Điểm dễ sai nhất là nhầm lẫn giữa:

- **Chuẩn hóa:** thay đổi cách biểu diễn dữ liệu *đã có nguồn đáng tin*, giữ nguyên danh tính và ngữ nghĩa quyền.
- **Cấp quyền:** đưa một authority mới vào `Authentication` khiến ứng dụng cho phép thao tác trước đó không được chứng minh là hợp lệ.

> **Nguyên tắc cốt lõi:** phải introspect token thành công trước, sau đó chỉ ánh xạ roles/permissions do nguồn có thẩm quyền cấp và theo hợp đồng rõ ràng. Không suy diễn `ROLE_ADMIN` từ username, email, tên group lạ hay các dữ liệu client có thể tự thay đổi.

Bài học tập trung vào **`OpaqueTokenIntrospector` và `OAuth2AuthenticatedPrincipal`**, không dùng nhầm `JwtAuthenticationConverter` dành cho đường xử lý JWT. Các ví dụ dựa trên Java 17+, Spring Boot và Spring Security Servlet/Spring MVC. Tên package/API có thể khác theo Spring Boot/Spring Security version; hãy dùng tài liệu của đúng phiên bản dự án.

## 1. Opaque token và introspection nằm ở đâu trong luồng xác thực?

Một request gửi bearer token:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer 8fa7c...opaque-token...
~~~

Resource Server xử lý theo khái niệm:

~~~text
Client
  |
  | Authorization: Bearer <token>
  v
BearerTokenAuthenticationFilter
  |
  v
OpaqueTokenAuthenticationProvider
  |
  v
OpaqueTokenIntrospector
  |
  | Gọi endpoint tin cậy bằng credentials của Resource Server
  v
Authorization Server /introspect
  |
  +-- {"active": false} --> authentication failure
  |
  +-- {"active": true, "sub": ..., "scope": ..., ...}
  |
  v
OAuth2AuthenticatedPrincipal
  |
  +-- chuẩn hóa display/identity attributes
  +-- bảo toàn OAuth scopes đã được cấp
  +-- ánh xạ roles/permissions được phê duyệt
  v
BearerTokenAuthentication
  |
  v
SecurityContext -> HTTP / method / business authorization
~~~

Việc introspect là một phần của **authentication**, còn chuyển đổi role/permission là bước chuẩn bị dữ liệu cho **authorization**. Nó chỉ có ý nghĩa khi AS xác nhận token được chấp nhận.

**Không** parse một opaque token như JWT để tin `sub`, `roles` hoặc `permissions`. Ngay cả nếu một token có hình dạng ba đoạn như JWT, cấu hình `opaqueToken()` vẫn lấy kết quả introspection làm cơ sở xác thực.

### 1.1. RFC 7662 trả những thuộc tính nào?

Một response minh họa từ introspection endpoint:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-frontend",
  "scope": "orders.read orders.write",
  "token_type": "Bearer",
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "exp": 2000000300,
  "iat": 2000000000,
  "username": "alice",
  "roles": ["orders_reader"],
  "permissions": ["orders.export"],
  "tenant_id": "merchant-a"
}
~~~

Đây là **ví dụ hợp đồng của hệ thống**, không phải response bắt buộc. RFC 7662 định nghĩa `active` và nhiều thuộc tính tùy chọn, trong khi `roles`, `permissions`, `tenant_id` là những phần mở rộng do AS/nhà cung cấp định nghĩa.

Nếu token không hợp lệ, AS thường trả:

~~~json
{
  "active": false
}
~~~

Kết quả `active=false` **không được** dẫn đến một principal đã xác thực. Introspector chuẩn cần từ chối token này, và decorator tùy chỉnh không được “khôi phục” nó bằng cách tạo `DefaultOAuth2AuthenticatedPrincipal`.

## 2. Thành phần Spring Security cần phân biệt

| Thành phần | Trách nhiệm | Lưu ý khi custom |
|---|---|---|
| `BearerTokenAuthenticationFilter` | Trích bearer token từ request | Không dùng để đoán roles |
| `BearerTokenAuthenticationToken` | Credential chưa được xác thực | Không phải principal đã tin cậy |
| `OpaqueTokenAuthenticationProvider` | Gọi introspector để xác thực | Chỉ thành công khi introspector trả kết quả hợp lệ |
| `OpaqueTokenIntrospector` | `introspect(String token)` | Điểm mở rộng được ưu tiên trong bài |
| `SpringOpaqueTokenIntrospector` | Gọi introspection endpoint chuẩn | Có thể bọc bằng decorator |
| `OAuth2AuthenticatedPrincipal` | Principal name, attributes, authorities | Không phải `Jwt` |
| `DefaultOAuth2AuthenticatedPrincipal` | Implementation có thể xây từ name/attributes/authorities | Dùng để chuẩn hóa |
| `BearerTokenAuthentication` | Authentication của opaque bearer token | Được đưa vào SecurityContext |
| `OpaqueTokenAuthenticationConverter` | Chuyển kết quả introspection thành Authentication | Dùng khi cần thay kiểu Authentication |

Trong Spring Security mặc định, `Authentication#getPrincipal()` với opaque token thường là `OAuth2AuthenticatedPrincipal`, còn `Authentication#getName()` thường lấy từ `sub` nếu introspection trả về subject. Một API xử lý JWT có thể dùng `@AuthenticationPrincipal Jwt`, nhưng một API xử lý opaque token nên dùng `OAuth2AuthenticatedPrincipal` hoặc adapter domain phù hợp.

### Hai đường xử lý không nên nhầm

~~~text
JWT:
Bearer -> JwtDecoder -> Jwt -> JwtAuthenticationConverter
                         |
                         v
               JwtAuthenticationToken

Opaque token:
Bearer -> OpaqueTokenIntrospector -> OAuth2AuthenticatedPrincipal
                                     |
                                     v
                              BearerTokenAuthentication
~~~

Một dự án có thể hỗ trợ cả hai, nhưng cần cấu hình và test đúng từng đường. Việc tạo `JwtAuthenticationConverter` không tự thay đổi cách `opaqueToken()` ánh xạ roles/permissions.

## 3. Cấu hình Resource Server dùng introspection

Ví dụ dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

Thông tin introspection endpoint và client credentials phải được cấp qua cơ chế quản lý cấu hình/secret phù hợp. Không hardcode secret vào source code hoặc đưa vào log. Địa chỉ endpoint phụ thuộc AS thực tế, không có một đường dẫn mặc định cho mọi IdP.

Cấu hình HTTP:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Filter chain này chỉ minh họa authentication và HTTP authorization. Chính sách CORS/CSRF, cookie/session và quyền trên từng order cần được xử lý theo kiến trúc cụ thể. Không tắt CSRF vô điều kiện chỉ vì ứng dụng có OAuth2.

### 3.1. Spring Security mặc định ánh xạ scope ra sao?

Khi introspection response chứa:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

Spring Security thường chuyển những scope đó thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Đây là phép đổi cách biểu diễn của **scope đã được AS cấp**. Prefix `SCOPE_` là quy ước của Spring Security, không có nghĩa AS cấp thêm hai quyền mới.

Nếu muốn bảo vệ endpoint theo scope:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

Không cần viết custom introspector chỉ để chuyển `orders.read` sang `SCOPE_orders.read` nếu mặc định đã xử lý đúng.

## 4. Principal identity khác tên hiển thị và entitlement

Một introspection response có thể trả:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-frontend",
  "username": "alice",
  "email": "alice@example.com"
}
~~~

Các trường trên có mục đích khác nhau:

| Thuộc tính | Cách hiểu hợp lý | Không tự chứng minh |
|---|---|---|
| `sub` | Subject do AS cấp | User là admin |
| `iss` | Issuer nếu AS trả về | `sub` duy nhất trên mọi issuer |
| `client_id` | OAuth client nhận token | Một người dùng cụ thể |
| `username` | Tên tài khoản, thường có thể thay đổi | Quyền trên tài nguyên |
| `email` | Địa chỉ liên hệ, có thể thay đổi | Role thuộc doanh nghiệp |
| `name` / `preferred_username` | Tên hiển thị | Quyền quản lý API |
| `tenant_id` | Bối cảnh tenant | Admin của tenant |
| `roles` / `permissions` | Entitlements tùy biến theo contract | Quyền trong mọi ứng dụng khác |

### 4.1. Dùng định danh ổn định

Với user token, `sub` là một lựa chọn phổ biến cho subject ID, nhưng khi chấp nhận nhiều issuer cần xét **cặp `(issuer, subject)`**. Ví dụ:

~~~text
(https://idp-a.example.com, user-42) -> người A
(https://idp-b.example.com, user-42) -> người B
~~~

Hai `sub` giống nhau không đủ để hợp nhất tài khoản. Không hợp nhất identity chỉ vì email hoặc username trùng.

Nếu introspection endpoint không trả `iss`, ứng dụng có thể biết namespace issuer qua **introspection endpoint cấu hình tin cậy**, nếu mỗi endpoint chỉ phục vụ một issuer theo contract. Không tự lấy issuer từ header/query do client gửi hoặc đoán từ hostname của một URL không đáng tin.

### 4.2. Phân biệt user token với machine token

Trong `client_credentials`, token có thể đại diện cho một ứng dụng/tiến trình, không phải human user. Một response có thể chứa `client_id=nightly-importer` với `sub` có hoặc không tùy AS.

Không áp dụng logic:

~~~text
Có sub -> chắc chắn là human user -> tự thêm ROLE_USER
~~~

Phải phân biệt mô hình principal theo AS contract: user subject, machine client, tenant/application và quyền được cấp. Với máy, `client_id` có thể là nguồn định danh workload chính nhưng không được tự chuyển nó thành identity của người dùng.

### 4.3. Tên hiển thị nên tách khỏi name dùng cho ownership

Ví dụ:

~~~text
Canonical name = user-42
Display name   = Alice Smith
Authorities    = [SCOPE_orders.read]
~~~

Đổi `display_name` phục vụ UI không nên đổi `Authentication#getName()` nếu tầng service dùng `getName()` để tìm ownership trong database. Nếu cần ánh xạ sang internal user ID, dùng một mapping có kiểm soát từ `(issuer, sub)` và không gán quyền mặc định cao khi mapping không tồn tại.

## 5. Scope, role và permission không cùng một loại thông tin

| Authority | Nguồn dự kiến | Dùng để kiểm tra |
|---|---|---|
| `SCOPE_orders.read` | OAuth scope do AS cấp | `hasAuthority("SCOPE_orders.read")` |
| `SCOPE_orders.write` | OAuth scope ghi do AS cấp | `hasAuthority("SCOPE_orders.write")` |
| `ROLE_ORDERS_READER` | Application role được cấp có thẩm quyền | `hasRole("ORDERS_READER")` |
| `ROLE_ORDERS_MANAGER` | Application role được cấp có thẩm quyền | `hasRole("ORDERS_MANAGER")` |
| `PERM_ORDERS_EXPORT` | Permission chi tiết theo chính sách ứng dụng | `hasAuthority("PERM_ORDERS_EXPORT")` |
| `PERM_REFUND_APPROVE` | Permission phê duyệt hoàn tiền | `hasAuthority("PERM_REFUND_APPROVE")` |

`PERM_` là **quy ước của ứng dụng minh họa**, không phải prefix mặc định của Spring Security. `hasRole("ORDERS_MANAGER")` thường tương ứng kiểm tra authority `ROLE_ORDERS_MANAGER`, không phải `SCOPE_orders.manager`.

### 5.1. Entitlement claim phải có thẩm quyền

Giả sử response có:

~~~json
{
  "active": true,
  "roles": ["orders_reader"],
  "permissions": ["orders.export"]
}
~~~

Điều kiện để mapping thành roles/permissions của API:

1. AS phát hành những claim này từ **nguồn quản lý quyền được tổ chức tin cậy**, không phải profile field do user tự sửa.
2. Quyền thuộc **ứng dụng `orders-api`**, không phải role của một console hoặc client khác.
3. Quyền có ngữ nghĩa, tenant scope và hành động được định nghĩa rõ.
4. Mapping từ tên nguồn sang authority đích là **allowlist đã phê duyệt**.
5. Role/permission không mặc nhiên bỏ qua kiểm tra ownership/tenant ở service.
6. Vòng đời cấp và thu hồi quyền được thiết kế phù hợp token TTL/introspection cache.

Dù AS trả `active=true`, claim `username="admin-support"` không có nghĩa user được cấp `ROLE_ADMIN`. Một AS có thể ký hoặc trả các thuộc tính profile do người dùng tự khai báo mà không trao cho chúng thẩm quyền phân quyền.

## 6. Bảng mapping role và permission có chủ đích

Ví dụ contract của `orders-api`:

| Giá trị introspection | Authority sau mapping | Quy tắc |
|---|---|---|
| `scope` chứa `orders.read` | `SCOPE_orders.read` | Preserve từ delegate |
| `scope` chứa `orders.write` | `SCOPE_orders.write` | Preserve từ delegate |
| `roles=["orders_reader"]` | `ROLE_ORDERS_READER` | Chỉ role được phê duyệt |
| `roles=["orders_manager"]` | `ROLE_ORDERS_MANAGER` | Không tự suy ra admin toàn hệ thống |
| `permissions=["orders.export"]` | `PERM_ORDERS_EXPORT` | Đúng permission của API |
| `permissions=["refund.approve"]` | `PERM_REFUND_APPROVE` | Còn kiểm tra merchant/hạn mức |
| `roles=["unknown_admin"]` | Không thêm authority | Không tự map giá trị lạ |
| Không có `roles` | Không thêm role | Không tạo default admin |
| Không có `permissions` | Không thêm permission | Không tạo quyền để tránh 403 |
| Claim sai kiểu | Reject hoặc fail closed theo contract | Không đoán format tùy tiện |

**Chuẩn hóa chuỗi không được thay đổi ngữ nghĩa quyền.** Nếu hai AS cùng gọi role là `operator` nhưng ở AS A nghĩa là người hỗ trợ khách hàng, còn ở AS B nghĩa là người quản trị đơn hàng, không thể tự map cả hai thành cùng `ROLE_ORDERS_MANAGER`.

Nên hạn chế mapping theo **issuer, client/audience, ứng dụng và namespace**, thay vì map chung mọi role string có vẻ giống nhau.

## 7. Vì sao nên dùng decorator cho `OpaqueTokenIntrospector`?

Mẫu mở rộng an toàn là bọc implementation có sẵn:

~~~text
MappingOpaqueTokenIntrospector
        |
        | delegate.introspect(token)
        v
SpringOpaqueTokenIntrospector
        |
        +-- active=false / invalid -> exception
        |
        +-- active=true -> verified OAuth2AuthenticatedPrincipal
                               |
                               +-- giữ nguyên principal name
                               +-- chuẩn hóa display attributes
                               +-- giữ SCOPE_ authorities gốc
                               +-- map allowlisted roles/permissions
                               |
                               v
                   DefaultOAuth2AuthenticatedPrincipal
~~~

Nhờ vậy custom class không phải tự implement HTTP introspection request, client authentication, parsing RFC 7662 hoặc xử lý token inactive. Nó chỉ bổ sung logic **chuẩn hóa/mapping sau xác thực**.

Không triển khai kiểu sau:

~~~java
// SAI: chưa xác minh token nhưng đã trả principal quyền admin.
return new DefaultOAuth2AuthenticatedPrincipal(
    "user",
    Map.of("active", true),
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
~~~

Đó là bỏ qua authentication boundary.

## 8. Java: custom introspector chuẩn hóa principal và mapping quyền

Giả sử AS bảo đảm:

- `scope`: OAuth scope chuẩn, delegate đã đổi thành `SCOPE_*`.
- `roles`: một **array of strings** do AS cấp từ application-role database.
- `permissions`: một **array of strings** do AS cấp từ permission catalog.
- `username`: trường hiển thị, không dùng để cấp quyền.
- Claim role/permission lạ: không map.
- Claim role/permission sai kiểu: từ chối vì vi phạm contract.

### 8.1. Implementation hoàn chỉnh

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class MappingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    // Các mapping này là POLICY, phải được phê duyệt.
    private static final Map<String, String> ROLE_MAP = Map.of(
        "orders_reader", "ROLE_ORDERS_READER",
        "orders_manager", "ROLE_ORDERS_MANAGER"
    );

    private static final Map<String, String> PERMISSION_MAP = Map.of(
        "orders.export", "PERM_ORDERS_EXPORT",
        "refund.approve", "PERM_REFUND_APPROVE"
    );

    private final OpaqueTokenIntrospector delegate;

    public MappingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate là nơi xác thực token bằng introspection.
        // Nếu token inactive, delegate phải ném exception.
        OAuth2AuthenticatedPrincipal verified =
            delegate.introspect(token);

        // Giữ các SCOPE_* authorities do delegate đã cấp.
        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(verified.getAuthorities());

        addMappedAuthorities(
            verified.getAttribute("roles"),
            ROLE_MAP,
            authorities,
            "roles"
        );

        addMappedAuthorities(
            verified.getAttribute("permissions"),
            PERMISSION_MAP,
            authorities,
            "permissions"
        );

        Map<String, Object> attributes =
            new LinkedHashMap<>(verified.getAttributes());

        // Chỉ chuẩn hóa trường HIỂN THỊ.
        Object rawUsername = attributes.get("username");
        String displayName =
            rawUsername instanceof String username
                && !username.isBlank()
                ? username
                : verified.getName();

        attributes.put("display_name", displayName);

        // Không đổi principal canonical name hoặc bịa scope.
        return new DefaultOAuth2AuthenticatedPrincipal(
            verified.getName(),
            attributes,
            authorities
        );
    }

    private static void addMappedAuthorities(
            Object raw,
            Map<String, String> mapping,
            Set<GrantedAuthority> target,
            String claimName) {

        // Claim optional không có -> không tạo quyền.
        if (raw == null) {
            return;
        }

        // Theo contract, roles/permissions là array of strings.
        if (!(raw instanceof Collection<?> values)) {
            throw new BadOpaqueTokenException(
                "Unexpected " + claimName + " claim type"
            );
        }

        for (Object item : values) {
            if (!(item instanceof String value)) {
                throw new BadOpaqueTokenException(
                    "Invalid item in " + claimName
                );
            }

            String mapped = mapping.get(value);
            if (mapped != null) {
                target.add(new SimpleGrantedAuthority(mapped));
            }
        }
    }
}
~~~

**Các đặc tính bảo mật của ví dụ:**

- `delegate.introspect(token)` chạy **trước** mọi mapping. Token inactive không được ánh xạ.
- Quyền scope gốc từ delegate được giữ nguyên, không bị thay bằng roles tùy chỉnh.
- Chỉ role/permission có mặt trong allowlist mới được thêm authority.
- Không có `ROLE_ADMIN`/`SCOPE_orders.write` tự xuất hiện khi nguồn không cấp.
- Giá trị role/permission lạ không được ánh xạ tự động.
- Claim sai kiểu bị từ chối theo contract, không parse “đến khi đọc được”.
- `display_name` chỉ để hiển thị; không thay `getName()` bằng email hoặc username.
- `LinkedHashSet` loại bỏ các authority trùng nhau mà không làm phát sinh quyền.

**Giới hạn:** `roles` và `permissions` là những claim của AS giả định. Nếu nhà cung cấp trả nested object hoặc string phân tách, cần thiết kế parser tương ứng **theo tài liệu chính thức của AS**, không chỉnh sửa ví dụ một cách suy đoán.

### 8.2. Vì sao không thay toàn bộ authorities?

Một implementation sai:

~~~java
return new DefaultOAuth2AuthenticatedPrincipal(
    verified.getName(),
    verified.getAttributes(),
    customRoleAuthoritiesOnly
);
~~~

có thể **làm mất** những `SCOPE_*` authorities do Spring đã trích xuất. Khi đó API cần `SCOPE_orders.read` sẽ bị 403 dù introspection cho biết token có scope đó.

Mặt khác, việc thêm `SCOPE_orders.write` khi token chỉ có `orders.read` là **cấp quyền không có căn cứ**. `verified.getAuthorities()` phải được giữ và chỉ bổ sung những quyền thực sự có entitlement được công nhận.

### 8.3. Có nên bỏ các authority khác không?

Một hệ thống có thể cố ý chỉ giữ tập con authorities liên quan `orders-api`. Việc **lọc bỏ** quyền không dùng là một policy có thể phù hợp với least privilege, nhưng cần kiểm tra những authorities hệ thống khác đang dựa vào. Không tự chuyển mọi authority lạ thành quyền có tên gần giống trong ứng dụng.

Ở các phiên bản Spring Security mới, authentication có thể chứa thêm factor authority như `FACTOR_BEARER`. Đừng mặc định authority kỹ thuật đó là business permission hoặc cố biến nó thành scope.

## 9. Đăng ký wrapper introspector trong Spring Boot

Khi cung cấp một bean `OpaqueTokenIntrospector`, Spring Boot thường **không tạo introspector mặc định** nữa. Vì thế phải chủ động tạo một delegate thật và bọc nó.

### 9.1. Spring Boot 3.x dùng OAuth2ResourceServerProperties

~~~java
package com.example.orders.security;

import org.springframework.boot.autoconfigure.security.oauth2.resource.OAuth2ResourceServerProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            OAuth2ResourceServerProperties properties) {

        var opaque = properties.getOpaquetoken();

        String uri = opaque.getIntrospectionUri();
        String id = opaque.getClientId();
        String secret = opaque.getClientSecret();

        if (uri == null || uri.isBlank()
                || id == null || id.isBlank()
                || secret == null || secret.isBlank()) {
            throw new IllegalStateException(
                "Missing opaque token introspection configuration"
            );
        }

        OpaqueTokenIntrospector delegate =
            SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(id)
                .clientSecret(secret)
                .build();

        return new MappingOpaqueTokenIntrospector(delegate);
    }
}
~~~

Đoạn này tái sử dụng URI/client ID/client secret từ `application.yml`. Với Spring Boot 4.x, package của `OAuth2ResourceServerProperties` thay đổi; cần kiểm tra import theo version (ví dụ nhóm package `org.springframework.boot.security.oauth2.server.resource.autoconfigure`). API thuộc Spring Security như `OpaqueTokenIntrospector` và `SpringOpaqueTokenIntrospector` có package riêng.

Không log `secret` hoặc endpoint response trong lỗi khởi tạo. Các chuỗi ví dụ dùng domain giả định; môi trường thực phải lấy từ cấu hình có quyền truy cập được kiểm soát.

### 9.2. Cách thay thế dùng @Value

Nếu không muốn phụ thuộc class properties của Boot, có thể inject property trực tiếp:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

    OpaqueTokenIntrospector delegate =
        SpringOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();

    return new MappingOpaqueTokenIntrospector(delegate);
}
~~~

Cần import `org.springframework.beans.factory.annotation.Value`, `org.springframework.context.annotation.Bean` và những import liên quan. **Chọn một** phương án đăng ký bean, không đồng thời khai báo hai bean introspector một cách vô ý.

### 9.3. Đừng tự viết stub introspection cho production

Sai:

~~~java
@Bean
OpaqueTokenIntrospector introspector() {
    return token -> new DefaultOAuth2AuthenticatedPrincipal(
        "demo-user", Map.of("sub", "demo-user"), List.of()
    );
}
~~~

Đoạn stub bỏ qua việc token có được AS xác nhận active hay không. Dùng để minh họa/mock trong unit test có thể phù hợp, nhưng đưa vào production sẽ trở thành lỗ hổng authentication nghiêm trọng.

## 10. Custom OpaqueTokenAuthenticationConverter khi nào?

Có hai nhu cầu:

1. **Thay attrs và authorities của principal:** dùng `OpaqueTokenIntrospector` decorator như phần trên.
2. **Thay kiểu Authentication cuối cùng:** dùng `OpaqueTokenAuthenticationConverter` khi ứng dụng cần một `Authentication` đặc thù hoặc tích hợp security context với hệ thống khác.

API `OpaqueTokenAuthenticationConverter` nhận token sau introspection thành công và `OAuth2AuthenticatedPrincipal`, rồi trả `Authentication`:

~~~java
Authentication convert(
    String introspectedToken,
    OAuth2AuthenticatedPrincipal authenticatedPrincipal
);
~~~

Đây là điểm mở rộng **sau introspection**, không phải nơi bypass AS validation. Đối với nhu cầu ánh xạ roles/permissions thông thường, decorator introspector là phương án rõ ràng hơn và ít thay đổi cấu trúc framework hơn.

Nếu dùng authentication converter custom, phải bảo toàn các properties và contracts mà Spring Security cần: principal, credential, authorities, authenticated state, không rò rỉ token qua log/`toString()` và tương thích với các `AuthorizationManager`. Cách đăng ký converter có thể khác theo Spring Security version.

## 11. Controller truy cập principal đã chuẩn hóa

Với opaque token Resource Server, có thể inject:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        String name = principal.getName();
        String display = principal.getAttribute("display_name");

        if (display == null || display.isBlank()) {
            display = name;
        }

        return Map.of("id", name, "displayName", display);
    }
}
~~~

Ví dụ giả định endpoint `GET /api/me` được bảo vệ bằng `authenticated()` và principal có name hợp lệ. `display_name` có thể được bổ sung bởi decorator; nếu không, controller fallback sang name.

**Không đưa nguyên attributes vào response** chỉ để debug. Một introspection response có thể chứa PII, client metadata hoặc dữ liệu entitlement không cần công bố. Trả đúng field sản phẩm cần.

### Đọc authorities

Khi muốn kiểm tra quyền:

~~~java
boolean canExport = principal.getAuthorities().stream()
    .anyMatch(a ->
        "PERM_ORDERS_EXPORT".equals(a.getAuthority()));
~~~

Trong business code, nên ưu tiên Spring Security `@PreAuthorize`, `AuthorizationManager` hoặc service policy thay vì rải điều kiện string ở mọi controller. Điều đó giúp test và quản trị quyền nhất quán.

## 12. Bảo vệ endpoints dựa vào các authorities được ánh xạ

Giả sử policy cho `orders-api` như sau:

| Endpoint | Điều kiện |
|---|---|
| `GET /api/me` | `authenticated()` |
| `GET /api/orders/**` | `SCOPE_orders.read` |
| `POST /api/orders/**` | `SCOPE_orders.write` |
| `GET /api/exports/**` | `PERM_ORDERS_EXPORT` |
| `POST /api/refunds/**` | `PERM_REFUND_APPROVE` và business policy |
| `/api/management/**` | `ROLE_ORDERS_MANAGER` |
| Endpoint khác | `denyAll()` |

Cấu hình minh họa:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/me")
        .authenticated()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.GET, "/api/exports/**")
        .hasAuthority("PERM_ORDERS_EXPORT")
    .requestMatchers(HttpMethod.POST, "/api/refunds/**")
        .hasAuthority("PERM_REFUND_APPROVE")
    .requestMatchers("/api/management/**")
        .hasRole("ORDERS_MANAGER")
    .anyRequest().denyAll()
)
~~~

### Chữ `ROLE_` không tự được thêm từ `roles`

`hasRole("ORDERS_MANAGER")` thường yêu cầu authority `ROLE_ORDERS_MANAGER`. Spring Security không tự đọc mọi claim `roles`/`permissions` của mọi IdP rồi chuyển thành authority phù hợp. Chính **wrapper mapping** đã định nghĩa trong bài làm việc đó theo contract.

### Quyền chung chưa đủ cho một đối tượng cụ thể

`PERM_REFUND_APPROVE` không chứng minh người gọi có thể duyệt mọi refund. Service còn cần kiểm tra merchant, hạn mức, trạng thái thanh toán, tách biệt người tạo và người duyệt, cũng như tính atomic của transaction.

Một `tenant_id` từ token hoặc URL cũng không tự chứng minh quyền quản lý tenant đó. Cần membership/ownership từ nguồn có thẩm quyền và truy vấn dữ liệu gắn đúng tenant để phòng lỗi BOLA/IDOR.

## 13. Permission từ introspection có thể stale không?

Một ưu điểm của introspection là AS có thể biết token đã revoke hay chưa ở thời điểm gọi. Tuy nhiên, freshness của role/permission còn phụ thuộc:

- AS có cập nhật entitlement ngay khi thay đổi không.
- AS có cache role hoặc nguồn directory không.
- Resource Server có cache introspection result không.
- Gateway có cache authorization decision không.
- Hệ thống cấp quyền nghiệp vụ có đòi truy vấn trạng thái hiện tại không.

Ví dụ:

~~~text
10:00  Token được cấp với role orders_manager
10:02  Admin thu hồi orders_manager
10:03  Resource Server kiểm tra token
~~~

Nếu introspection trả role đã cập nhật, mapping sẽ không thêm `ROLE_ORDERS_MANAGER`. Nhưng nếu response/cache vẫn có role cũ, API có thể tiếp tục chấp nhận theo cửa sổ stale được thiết kế.

Không tuyên bố introspection **tự động** giải quyết mọi bài toán revocation/permission freshness. Với hành động nhạy cảm, cân nhắc kiểm tra entitlement hiện tại ở service hoặc policy engine riêng.

## 14. Multi-issuer và tenant isolation

Nếu API hỗ trợ nhiều AS:

~~~text
IdP A -> roles=["operator"]
IdP B -> roles=["operator"]
~~~

hai giá trị `operator` có thể khác nhau về ngữ nghĩa. Một mapping chung:

~~~text
operator -> ROLE_ORDERS_MANAGER
~~~

chỉ hợp lệ nếu hai AS đều được phê duyệt và có contract tương đương cho `orders-api`.

Thiết kế cần xác định:

1. Token thuộc issuer/AS nào, thông qua endpoint introspection đáng tin.
2. Subject thuộc namespace nào.
3. Role/permission claim dành cho ứng dụng nào.
4. Tenant binding được kiểm tra ở nguồn nào.
5. Có quyền trên tài nguyên cụ thể hay không.

**Không** chọn introspection URL trực tiếp từ một claim/token chưa được xác minh hoặc header client tự gửi. Đó có thể tạo SSRF hoặc khiến Resource Server tin endpoint do kẻ tấn công kiểm soát.

### Tránh hợp nhất identity bằng username

Hai người ở hai IdP có thể có cùng `username=alice`; chúng vẫn là hai principal độc lập. Nếu cần internal user mapping, dùng `(issuer, sub)` hoặc định danh theo hợp đồng với AS, không chỉ `username` hay email.

## 15. Mapping role không được trở thành privilege escalation

Những anti-pattern điển hình:

### 15.1. Dựa vào email

~~~java
// SAI: profile attribute không chứng minh quyền quản trị.
if (email.endsWith("@company.example")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

### 15.2. Dựa vào tên chứa từ admin

~~~java
// SAI: có thể tạo role từ dữ liệu hiển thị.
if (username.startsWith("admin")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

### 15.3. Mặc định tất cả quyền khi thiếu claim

~~~java
// SAI: thiếu claim không được coi là full access.
if (roles == null) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ORDERS_MANAGER"));
}
~~~

### 15.4. Chuyển bất kỳ role string nào thành quyền nội bộ

~~~java
// SAI nếu roles không được namespace và mapping đúng contract.
for (String role : roles) {
    authorities.add(new SimpleGrantedAuthority(
        "ROLE_" + role.toUpperCase()
    ));
}
~~~

### 15.5. Tự nâng scope đọc thành scope ghi

~~~java
// SAI: ứng dụng không được bù scope thiếu.
if (authorities.contains(
        new SimpleGrantedAuthority("SCOPE_orders.read"))) {
    authorities.add(
        new SimpleGrantedAuthority("SCOPE_orders.write"));
}
~~~

**Cách phòng tránh:** dùng allowlist có ngữ nghĩa rõ, kiểm tra nguồn entitlement, xử lý unknown values bằng không cấp quyền, và viết test âm tính chứng minh admin/write không xuất hiện từ identity attributes.

## 16. Khi introspection không cung cấp issuer/audience

RFC 7662 cho phép một số attributes không có trong response. Đừng tự giả định `iss` và `aud` luôn tồn tại như JWT.

Có một số mô hình được thiết kế hợp lệ:

- Introspection endpoint **riêng cho một audience/resource**, AS đã ràng buộc quyền truy cập.
- Introspection response trả `aud` để Resource Server kiểm tra token có dành cho `orders-api`.
- Một API gateway hoặc authorization service trung gian có contract khẳng định resource binding.
- Resource Server gọi một introspection endpoint riêng cho mỗi issuer/tenant được duyệt.

Nếu contract yêu cầu `aud` nhưng response không có, không sửa response thành `"aud":["orders-api"]` để vượt qua validation. Phải sửa hợp đồng với AS hoặc chọn cơ chế xác minh khác.

Ví dụ ý tưởng validator:

~~~java
Object rawAudience = verified.getAttribute("aud");

if (!audienceMatchesOrdersApi(rawAudience)) {
    throw new BadOpaqueTokenException(
        "Token is not intended for orders-api"
    );
}
~~~

`audienceMatchesOrdersApi` là helper do ứng dụng định nghĩa; phải xử lý đúng schema string/list theo AS contract, không phải API Spring Security có sẵn. Một số hệ thống không cần bổ sung validator này nếu endpoint introspection đã ràng buộc tài nguyên một cách có thẩm quyền; cần xác định rõ trước khi chọn.

## 17. Claim sai kiểu, vắng mặt và fallback

Một contract cần nêu rõ hành vi với response lạ:

| Trường hợp | Hành vi an toàn |
|---|---|
| `active=false` | Authentication failure |
| `roles` vắng mặt | Không có role mới |
| `permissions` vắng mặt | Không có permission mới |
| `roles=[]` | Không có role mới |
| `roles=["orders_reader"]` | Map đúng role đã duyệt |
| `roles=["unknown_admin"]` | Không map quyền cao |
| `roles="orders_reader"` khi contract yêu cầu array | Từ chối schema sai |
| `permissions=[1, "orders.export"]` | Từ chối item sai kiểu |
| `scope` không có | Không tự tạo scope |
| `sub` không có trong user-token contract bắt buộc subject | Từ chối hoặc xử lý riêng theo loại token |
| `client_id` có với machine token | Dùng đúng machine identity contract |
| Endpoint introspection timeout | Không tự allow |
| Role từ client/issuer khác | Không tái sử dụng mapping ngoài phạm vi |

Đừng viết parser “nếu là string thì split bằng dấu phẩy, nếu là object thì lấy tất cả key, nếu là list thì ghép cả giá trị” nếu AS không quy định như vậy. Nới lỏng schema thiếu kiểm soát dễ khiến một claim có ý nghĩa khác bị biến thành entitlement.

## 18. Kiểm thử converter bằng delegate giả

Unit test mapping không cần gọi AS thật. Tạo một delegate trả principal giả lập để cô lập logic ánh xạ.

~~~java
package com.example.orders.security;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MappingOpaqueTokenIntrospectorTest {

    @Test
    void preservesScopesAndMapsOnlyApprovedRights() {
        OpaqueTokenIntrospector delegate = token ->
            new DefaultOAuth2AuthenticatedPrincipal(
                "user-42",
                Map.of(
                    "sub", "user-42",
                    "username", "admin-support",
                    "roles", List.of(
                        "orders_reader", "unknown_admin"),
                    "permissions", List.of("orders.export")
                ),
                List.of(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))
            );

        OpaqueTokenIntrospector mapped =
            new MappingOpaqueTokenIntrospector(delegate);

        OAuth2AuthenticatedPrincipal principal =
            mapped.introspect("unit-test-token");

        Set<String> authorities = principal.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertEquals(
            Set.of(
                "SCOPE_orders.read",
                "ROLE_ORDERS_READER",
                "PERM_ORDERS_EXPORT"
            ),
            authorities
        );

        assertEquals("user-42", principal.getName());
        assertEquals(
            "admin-support",
            principal.getAttribute("display_name")
        );
    }
}
~~~

Dù username chứa `admin`, kết quả **không** có `ROLE_ADMIN`. Dù `roles` chứa `unknown_admin`, mapping không tự nhận nó.

### 18.1. Inactive token phải luôn bị từ chối

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.junit.jupiter.api.Assertions.assertThrows;

class InactiveTokenTest {

    @Test
    void doesNotCreatePrincipalWhenDelegateRejectsToken() {
        OpaqueTokenIntrospector delegate = token -> {
            throw new BadOpaqueTokenException("inactive");
        };

        var mapping = new MappingOpaqueTokenIntrospector(delegate);

        assertThrows(
            BadOpaqueTokenException.class,
            () -> mapping.introspect("inactive-token")
        );
    }
}
~~~

Decorator không nuốt exception rồi cấp role. Trong sản phẩm, delegate thật gọi introspection endpoint và xử lý `active=false`.

### 18.2. Sai kiểu phải fail closed

~~~java
@Test
void rejectsWrongRoleClaimType() {
    OpaqueTokenIntrospector delegate = token ->
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-42",
            Map.of("roles", "orders_reader"),
            List.of()
        );

    var wrapper = new MappingOpaqueTokenIntrospector(delegate);

    assertThrows(
        BadOpaqueTokenException.class,
        () -> wrapper.introspect("test-token")
    );
}
~~~

Ở đây `roles` là string nhưng contract yêu cầu array, nên mapping từ chối. Nếu AS của dự án thực sự định nghĩa `roles` là string, hãy viết parser có contract và test riêng, không coi một định dạng ví dụ là phổ quát.

## 19. Test HTTP và integration introspection

Unit test decorator chỉ chứng minh **mapping Java**, chưa chứng minh:

- Token được AS xác nhận `active=true`.
- URI/client credentials của introspection đúng.
- HTTPS/truststore hoạt động.
- Response của AS được parse đúng.
- `BearerTokenAuthentication` được tạo với authorities sản xuất.
- HTTP/method security đúng.
- Tenant/ownership policy đúng.

Spring Security Test hỗ trợ `opaqueToken()` cho MockMvc:

~~~java
mvc.perform(get("/api/orders")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

Ví dụ giả định endpoint tồn tại và business code không ném lỗi. **MockMvc `opaqueToken()` có thể bypass introspection và mapper thật**, vì test tự gắn authorities. Nó hữu ích để kiểm tra HTTP authorization, không thay thế integration test.

Một bộ kiểm thử đầy đủ nên có:

1. Unit test mapping các roles/permissions cho phép.
2. Test unknown/malformed claims không tự thêm quyền.
3. Stub introspection endpoint trả `active=true` với payload đúng.
4. Stub introspection endpoint trả `active=false` và kiểm tra bị từ chối.
5. Test client credentials/TLS/error handling theo môi trường.
6. Test JWT-like input vẫn được xử lý bằng introspection khi đã chọn opaque flow.
7. Test `401` khi token thiếu/invalid và `403` khi token hợp lệ nhưng thiếu authority.
8. Service test cho tenant khác, order khác owner và permission vừa bị thu hồi.
9. Test tình huống role mapping theo issuer/client không bị trộn.
10. Test đường production không dùng nhầm mock introspector.

### 19.1. Ma trận quyền mong đợi

| Introspection result | Expected authorities bổ sung | Quyết định ví dụ |
|---|---|---|
| `active=false` | Không có authentication | 401 |
| `active=true`, `scope=orders.read` | `SCOPE_orders.read` | GET orders có thể được phép |
| Chỉ `orders.read`, gọi POST | Không có `SCOPE_orders.write` | 403 |
| `roles=["orders_reader"]` | `ROLE_ORDERS_READER` | Chỉ những rule role tương ứng |
| `roles=["unknown_admin"]` | Không có admin role | Admin endpoint bị từ chối |
| `permissions=["orders.export"]` | `PERM_ORDERS_EXPORT` | Export endpoint qua tầng authority |
| Thiếu `permissions` | Không có `PERM_*` | Permission-specific endpoint bị từ chối |
| Có `PERM_REFUND_APPROVE`, refund tenant khác | Có authority chung nhưng object policy từ chối | 403/404 theo thiết kế |
| Introspection service timeout | Không grant | Lỗi hạ tầng hoặc từ chối theo policy |

`200`, `401`, `403` chính xác còn phụ thuộc controller, business service, handlers và cấu hình Spring Security.

## 20. Khi nào dùng RestClientOpaqueTokenIntrospector?

Trong các phiên bản Spring Security mới, có thêm `RestClientOpaqueTokenIntrospector` dựa trên Spring `RestClient`, cho phép tùy chỉnh HTTP client và timeout.

Điều quan trọng là **phiên bản API**: lớp `RestClientOpaqueTokenIntrospector` xuất hiện trong dòng Spring Security mới (theo Javadoc từ 7.1). Không sao chép trực tiếp ví dụ của 7.1 sang một dự án 6.x rồi kỳ vọng class có sẵn.

Với các phiên bản dùng `SpringOpaqueTokenIntrospector`, có thể cấu hình client HTTP/timeout theo API mà chính phiên bản cung cấp. Nếu cần tính năng riêng như retry, circuit breaker hoặc metrics, ưu tiên bọc client/delegate chuẩn theo cách không làm mất token validation.

Không đặt timeout vô hạn hoặc tự allow token khi endpoint không trả lời. **Introspection unavailable không có nghĩa token active.**

## 21. Cache kết quả introspection và freshness của quyền

Mỗi lần gọi introspection có thể tốn network latency. Một cache kết quả có thể giảm tải nhưng gây stale authorization:

~~~text
T0: AS trả active=true, role=orders_manager
T1: Admin thu hồi role
T2: Resource Server dùng cache response T0 -> vẫn thấy role cũ
~~~

Khi thiết kế cache:

- Không cache quá thời điểm token hết hạn nếu `exp` có mặt.
- Chọn TTL theo yêu cầu về revocation và cập nhật quyền.
- Không tái sử dụng kết quả giữa tokens hoặc issuer khác nhau.
- Nếu cache key dùng token, bảo vệ token và tránh để raw token hiện trong log/metrics.
- Cân nhắc invalidation khi role/membership bị thay đổi.
- Không fail open khi AS tạm lỗi bằng cách dùng một allow cache đã hết hạn ngoài chính sách.
- Nếu API cần thu hồi ngay, cân nhắc kiểm tra entitlement tại service cho hành động nhạy cảm.

**Opaque introspection không tự đảm bảo quyền luôn mới** nếu bất kỳ tầng nào cache hoặc AS không cập nhật permission ngay.

## 22. Quan sát, logging và xử lý lỗi

Để chẩn đoán, ghi loại sự kiện thay vì full token:

~~~text
event=opaque_principal_mapping
result=SUCCESS
principalRef=<stable-internal-id>
mappedRoleCount=1
mappedPermissionCount=1
source=trusted-introspection-endpoint
mappingPolicyVersion=v3
traceId=5e8c...
bearerToken=[REDACTED]
~~~

Không log:

- Access token trong `Authorization` header.
- Client secret của introspection endpoint.
- Full response chứa PII hoặc quyền nhạy cảm.
- Username/email nếu không cần phục vụ debug và chưa có chính sách bảo vệ.

Phân biệt các nhóm lỗi:

| Lỗi | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `active=false` | Token không còn được chấp nhận | Không tạo principal |
| Introspection URI sai | Không kết nối đúng endpoint | Sửa cấu hình |
| Client credentials sai | Resource Server không xác thực được tới AS | Quản lý secret và client auth |
| Roles/permissions sai kiểu | AS contract mismatch | Sửa schema hoặc parser |
| Unknown role | Không có mapping được phê duyệt | Không tạo authority |
| Mapper làm mất scopes | Không preserve delegate authorities | Sửa mapping |
| HTTP 403 với token active | Thiếu authority hoặc policy tài nguyên từ chối | Không thêm quyền để che lỗi |
| PDP/membership DB timeout | Hạ tầng quyền không sẵn sàng | Fail closed, không grant |
| Role stale sau khi thu hồi | Cache/token lifetime/AS freshness | Xem lại chính sách cập nhật quyền |

Lỗi hạ tầng có thể được trả về 5xx hoặc trạng thái khác tùy exception handlers; không cố biến mọi timeout thành một `403` giả mà không có telemetry phân biệt.

## 23. Những hiểu nhầm thường gặp

**“Opaque token không có JWT payload nên không có principal.”** Sai. Principal được tạo từ **introspection attributes** của token đã xác nhận hợp lệ.

**“`Authentication#getPrincipal()` luôn là `Jwt`.”** Sai với opaque flow. Thông thường là `OAuth2AuthenticatedPrincipal`.

**“`active=true` thì mọi claim đều được dùng để cấp role.”** Không. Claim phải có ngữ nghĩa cấp quyền, nguồn có thẩm quyền và đúng ứng dụng.

**“Spring Security tự map mọi trường `roles`, `permissions` của mọi IdP.”** Không. Mặc định tập trung vào OAuth scopes; custom claims cần mapping theo contract.

**“Chỉ cần uppercase group name rồi thêm `ROLE_`.”** Nguy hiểm. Group của ứng dụng khác có thể trùng tên role quản trị.

**“Username chứa admin nghĩa là `ROLE_ADMIN`.”** Sai. Username/display name không chứng minh entitlement.

**“Thiếu permission thì gán quyền mặc định để tránh 403.”** Sai nếu không có policy cấp quyền được phê duyệt.

**“Custom introspector không cần gọi AS vì đã biết role.”** Sai. Token phải được introspect hợp lệ trước.

**“Role trong introspection luôn tươi mới.”** Không chắc, còn phụ thuộc nguồn quyền và cache.

**“Token active và có export permission là được xuất mọi tenant.”** Sai. Cần kiểm tra membership, ownership và object-level policy.

**“`opaqueToken()` có thể được tùy chỉnh bằng `JwtAuthenticationConverter`.”** Không đúng đường API thông thường. Dùng `OpaqueTokenIntrospector`/`OpaqueTokenAuthenticationConverter`.

**“MockMvc `opaqueToken()` chứng minh introspector production đang gọi AS.”** Không; mock authentication có thể bỏ qua introspection.

## 24. Câu hỏi tự kiểm tra

**1.** Response có `active=true, scope="orders.read orders.write"`. Spring Security thường tạo những authority nào?

> `SCOPE_orders.read` và `SCOPE_orders.write`, sau khi introspection thành công.

**2.** Trong opaque Resource Server, principal thường có kiểu nào?

> `OAuth2AuthenticatedPrincipal` trong `BearerTokenAuthentication`, không phải `Jwt`.

**3.** Vì sao wrapper phải gọi `delegate.introspect(token)` đầu tiên?

> Để bảo đảm AS đã xác nhận token hợp lệ; không được map roles cho token inactive.

**4.** `username=admin-support` có phải căn cứ cấp `ROLE_ADMIN`?

> Không. Username là thuộc tính danh tính/hiển thị, không phải entitlement.

**5.** Khi nào được map `roles=["orders_manager"]` thành `ROLE_ORDERS_MANAGER`?

> Khi AS phát role từ nguồn có thẩm quyền, dành cho đúng Resource Server, và mapping được phê duyệt.

**6.** Vì sao phải giữ `verified.getAuthorities()`?

> Để tránh làm mất OAuth scopes đã được Spring ánh xạ từ response hợp lệ.

**7.** Nếu `roles` có kiểu string nhưng contract yêu cầu array, nên làm gì?

> Xử lý như malformed response, không tự suy đoán; có thể từ chối token theo chính sách.

**8.** Nếu token chỉ có `orders.read`, converter có được thêm `SCOPE_orders.write`?

> Không. Đó là cấp quyền không có căn cứ.

**9.** Opaque token có `PERM_REFUND_APPROVE` thì đã đủ để refund mọi giao dịch chưa?

> Chưa. Phải kiểm tra merchant, hạn mức, trạng thái thanh toán và chính sách nghiệp vụ trong transaction.

**10.** Vì sao cache introspection cần giới hạn thời gian?

> Vì token/role có thể bị revoke hoặc đổi quyền; cache cũ có thể tiếp tục cho phép request ngoài mong đợi.

## 25. Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, principal mặc định, scope mapping, custom introspector, HTTP client.
- [Spring Security — OpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): `introspect(String)`.
- [Spring Security — SpringOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html): client introspection chuẩn.
- [Spring Security — OAuth2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html): attributes, authorities và principal name.
- [Spring Security — DefaultOAuth2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html): chuẩn hóa principal.
- [Spring Security — OAuth2IntrospectionAuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OAuth2IntrospectionAuthenticatedPrincipal.html): principal cho introspection response.
- [Spring Security — OpaqueTokenAuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenAuthenticationConverter.html): tùy chỉnh Authentication sau introspection.
- [Spring Security — BearerTokenAuthentication API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html): opaque bearer authentication.
- [Spring Security — BadOpaqueTokenException API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/BadOpaqueTokenException.html): invalid token/response handling.
- [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): opaque token properties và auto-configuration.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `scope`, `client_id`, `sub` và introspection contract.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer credentials và authentication errors.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): scopes và access token.

**Tổng kết:** hãy giữ ranh giới **token được introspect hợp lệ trước**, rồi mới **chuẩn hóa danh tính và ánh xạ các entitlement đã được cấp**. Tên principal cần ổn định; tên hiển thị không được biến thành role. Scopes mặc định phải được bảo toàn, roles/permissions tùy chỉnh cần allowlist có nguồn thẩm quyền, và quyền trên tenant/tài nguyên cụ thể vẫn phải được kiểm tra ở tầng nghiệp vụ.
