# Ánh xạ role claim và kiểm soát tiền tố ROLE_

> **Module:** Spring Security – authorization · **Nhóm:** Quyền từ OAuth2. Bài học giải thích từ đầu đến cuối cách chuyển quyền nằm trong OAuth 2.0/OIDC access token thành `GrantedAuthority` mà Spring Security có thể đánh giá, phân biệt chính xác **role** với **scope**, áp tiền tố `ROLE_` một lần duy nhất và không biến claim của một ứng dụng/tenant khác thành quyền quản trị. Ví dụ chính dùng **Spring Boot 3.5.x, Spring Security 6.5.x, Java 17+**, Servlet OAuth2 Resource Server JWT. Có phần riêng về `oauth2Login()` và WebFlux vì pipeline chuyển authorities khác nhau. Các token trong bài là dữ liệu giả lập, không phải credential thật.

## 1. Sau bài học cần hiểu và làm được gì?

1. Biết JWT access token sau khi được `JwtDecoder` kiểm chữ ký/issuer/audience/expiry sẽ được `JwtAuthenticationConverter` chuyển thành `Authentication`.
2. Giải thích tại sao `scope: "reports.read"` thường trở thành authority `SCOPE_reports.read`, không tự trở thành role `ROLE_ADMIN`.
3. Phân biệt `hasRole("ADMIN")`, `hasAuthority("ROLE_ADMIN")`, `hasAuthority("ADMIN")` và `hasAuthority("SCOPE_reports.read")`; xác định chỗ nào cần tiền tố.
4. Cấu hình `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName` và `setAuthorityPrefix` cho claim role dạng phẳng; biết rằng **chỉ thay converter sẽ có thể làm mất scope authorities mặc định**.
5. Tạo converter kết hợp cả scope + role trên allow-list và tách vai trò realm/global khỏi quyền riêng cho client/resource.
6. Tránh `ROLE_ROLE_ADMIN` khi IdP đã gửi role có sẵn tiền tố; không silently coi một chuỗi không hợp lệ là ADMIN.
7. Parse claim lồng nhau như `realm_access.roles` và `resource_access["orders-api"].roles` bằng traversal rõ, không tưởng `setAuthoritiesClaimName("realm_access.roles")` tự duyệt JSON path.
8. Thiết lập Spring SecurityFilterChain và `@PreAuthorize` đồng nhất với authorities được phát ra, dùng issuer/audience validation để xác định token dành cho API nào.
9. Kiểm thử converter, kiểm thử HTTP resource-server filter bằng mocked `JwtDecoder` và có kế hoạch kiểm chữ ký/JWKS thật trong integration test.
10. Phân biệt ánh xạ roles ở resource server so với `oauth2Login().userInfoEndpoint().userAuthoritiesMapper(...)` và `ReactiveJwtAuthenticationConverter`.
11. Kiểm role thay đổi, role global với tenant-scoped permissions, audience/client isolation, least privilege và cache/revocation.
12. Chạy chương trình Java 17 độc lập mô phỏng prefix mapping, bảng kết quả có stdout dự đoán được.

## 2. Chuyện gì xảy ra khi API nhận Bearer JWT?

Dòng xử lý thông thường trên Servlet resource server:

~~~text
HTTP Authorization: Bearer <opaque-token-bytes>
  |
  v
BearerTokenAuthenticationFilter
  |
  v
JwtAuthenticationProvider
  |
  +-- JwtDecoder: verify JWS signature, issuer, exp, nbf,
  |                audience and any required custom validation
  |
  v
JwtAuthenticationConverter
  |
  +-- Converter<Jwt, Collection<GrantedAuthority>>
  |       |-- scopes -> SCOPE_reports.read, SCOPE_orders.read
  |       |-- curated roles -> ROLE_ADMIN, ROLE_AUDITOR
  |       |-- app-specific permissions -> PERM_ORDERS_WRITE
  |
  v
JwtAuthenticationToken(Authentication)
  |
  v
SecurityFilterChain / method security AuthorizationManager
  |
  +-- hasRole("ADMIN")                 tests ROLE_ADMIN
  +-- hasAuthority("ROLE_ADMIN")       tests exact ROLE_ADMIN
  +-- hasAuthority("SCOPE_reports.read") tests exact SCOPE_reports.read
  +-- hasAuthority("PERM_ORDERS_WRITE")  tests exact PERM_ORDERS_WRITE
~~~

**Ba khái niệm không được đánh đồng:**

- **OAuth 2.0 scope** là quyền/phạm vi mà authorization server cấp cho một access token/client. Nó thường dùng tên như `orders.read`, `orders.write`, `profile`. Mặc định Spring map thành authorities bắt đầu `SCOPE_`.
- **Role** là nhóm quyền nghiệp vụ hoặc nhóm quản trị, ví dụ `ADMIN`, `AUDITOR`, `VIEWER`; Spring thường mong mã authority có `ROLE_` để tiện gọi `hasRole`.
- **Permission/authority** là chuỗi chính xác được authorization logic kiểm, ví dụ `PERM_ORDERS_WRITE` hoặc `document:approve`. Không có luật bắt buộc phải bắt đầu bằng `ROLE_`.

Role không tự sinh ra từ JWT nếu IdP không gửi hoặc ứng dụng chưa ánh xạ nó. Ngược lại, việc JWT có `roles=["ADMIN"]` **không** khiến Spring tự động thêm `ROLE_ADMIN` trong cấu hình JWT Resource Server mặc định.

### 2.1. Ví dụ access token của một IdP

JWT payload mang tính minh họa:

~~~json
{
  "iss": "https://idp.example.invalid/realms/acme",
  "sub": "user-7",
  "aud": ["orders-api"],
  "iat": 1783310000,
  "exp": 1783313600,
  "scope": "reports.read orders.read",
  "roles": ["ADMIN", "VIEWER"],
  "realm_access": {
    "roles": ["AUDITOR"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["write"]
    },
    "other-client": {
      "roles": ["admin"]
    }
  }
}
~~~

Không sử dụng các timestamp trên để suy đoán token còn hạn; chúng chỉ minh họa claim structure. Không copy token giả thành một API credential. **JWT payload tự nó không đáng tin** nếu chưa có `JwtDecoder` xác thực JWS signature, thuật toán đáng tin, issuer, audience và thời hạn.

Một token có thể có nhiều role sources. Không nên chọn cách “duyệt toàn bộ JSON và cứ gặp chuỗi `admin` thì tạo `ROLE_ADMIN`”. Trong ví dụ, role `admin` thuộc `other-client` phải **không** cấp quyền admin cho `orders-api`.

## 3. Ý nghĩa tiền tố ROLE_ chính xác đến từng ký tự

Spring Security dùng `GrantedAuthority#getAuthority()` như một chuỗi cần match. `SimpleGrantedAuthority("ROLE_ADMIN")` chỉ là authority có tên đúng chuỗi đó.

| Người dùng/token đã được map thành authority | Rule | Kết quả trong cấu hình mặc định |
| --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | GRANT |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | GRANT |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | DENY |
| `ADMIN` | `hasRole("ADMIN")` | DENY |
| `SCOPE_orders.read` | `hasRole("orders.read")` | DENY |
| `SCOPE_orders.read` | `hasAuthority("SCOPE_orders.read")` | GRANT |
| `ROLE_VIEWER` | `hasRole("ADMIN")` | DENY |
| `ROLE_ROLE_ADMIN` | `hasRole("ADMIN")` | DENY |
| `PERM_ORDERS_WRITE` | `hasAuthority("PERM_ORDERS_WRITE")` | GRANT |

**Ngữ nghĩa mặc định:**
- `hasRole("ADMIN")` là shortcut kiểm một `GrantedAuthority` tên `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` kiểm chính xác authority `ROLE_ADMIN`, không tự thêm prefix.
- `hasAuthority("ADMIN")` kiểm chính xác chuỗi `ADMIN`.
- `@PreAuthorize("hasRole('ADMIN')")` theo default role prefix cũng nhắm `ROLE_ADMIN`.
- Với một số DSL, `hasRole("ROLE_ADMIN")` còn bị từ chối vì tham số đã có tiền tố; quy ước nhất quán nhất là **bỏ tiền tố trong hasRole, giữ tiền tố trong hasAuthority**.
- So sánh chuỗi phân biệt chữ hoa/thường: `admin` ≠ `ADMIN`, `ROLE_admin` ≠ `ROLE_ADMIN`.

### 3.1. Hai “prefix settings” khác nhau

**(A) Converter mapping từ claim:**

~~~java
JwtGrantedAuthoritiesConverter converter =
        new JwtGrantedAuthoritiesConverter();
converter.setAuthoritiesClaimName("roles");
converter.setAuthorityPrefix("ROLE_");
~~~

Ví dụ claim `roles:["ADMIN"]` sẽ sinh `ROLE_ADMIN`. Đây là cách converter **tạo** authority string.

**(B) Authorization rule:**

~~~java
.requestMatchers("/api/admin").hasRole("ADMIN")
// hoặc @PreAuthorize("hasAuthority('ROLE_ADMIN')")
~~~

Đây là cách application **kiểm** authority string. Thay `setAuthorityPrefix("ROLE_")` không tự thay đổi Spring DSL để tất cả role match đúng; bạn phải thống nhất hai đầu bằng tests.

### 3.2. “ROLE_ROLE_ADMIN” xuất hiện từ đâu?

Nếu IdP gửi:

~~~json
{"roles":["ROLE_ADMIN"]}
~~~

và converter vẫn `setAuthorityPrefix("ROLE_")`, kết quả có thể là `ROLE_ROLE_ADMIN`. Rule `hasRole("ADMIN")` sẽ không match. Không chữa bằng cách tùy tiện gọi `hasRole("ROLE_ADMIN")` hoặc cấp cả `ROLE_ROLE_ADMIN`.

Chọn **một** hợp đồng:
- IdP gửi tên role nguyên bản `ADMIN`, converter thêm duy nhất `ROLE_`.
- IdP gửi đúng `ROLE_ADMIN`, converter dùng prefix rỗng (`""`) **chỉ nếu nguồn đó được quản trị chặt**.
- Với nhiều nguồn trộn lẫn, custom converter dùng **explicit allow-list và canonical mapping**, có thể reject chuỗi đã prefix hoặc normalize theo quy tắc được review, không chỉ xóa lặp `ROLE_` tùy tiện.

### 3.3. Không cấu hình ROLE_ toàn hệ thống chỉ để vá một claim

`GrantedAuthorityDefaults("CUSTOM_")` có thể thay default role prefix trong những ngữ cảnh như method security expression. Nhưng không nên giả định mọi API DSL, converter và custom `AuthorizationManager` đồng loạt nhận cấu hình đó. Đặc biệt factory `AuthorityAuthorizationManager.hasRole(...)` truyền thống tạo yêu cầu `ROLE_` theo contract riêng. Khi không có lý do kiến trúc rõ, giữ default `ROLE_` là lựa chọn dễ kiểm hơn, và dùng explicit `hasAuthority(...)` khi cần prefix khác.

Nếu thay default prefix, viết test cho **request authorization, method authorization, role hierarchy và các manager tùy chỉnh**, không suy từ một test duy nhất.

## 4. Mặc định scope từ JWT được Spring map thế nào?

Với cấu hình Resource Server JWT chuẩn, Spring Security tìm các well-known claims như `scope` hoặc `scp` và tạo authority có tiền tố `SCOPE_`.

~~~json
{"scope":"orders.read reports.read"}
~~~

thường thành:

~~~text
SCOPE_orders.read
SCOPE_reports.read
~~~

Một provider cũng có thể dùng:

~~~json
{"scp":["orders.read","reports.read"]}
~~~

Bộ chuyển đổi mặc định xử lý các dạng well-known được hỗ trợ. Claim mới ví dụ `roles` hoặc cấu trúc Keycloak `realm_access.roles` **không tự được** chuyển thành ROLE_*.

Trong `JwtGrantedAuthoritiesConverter`:
- `setAuthoritiesClaimName("roles")` bảo converter đọc field top-level `roles` thay vì các well-known scope fields.
- `setAuthorityPrefix("ROLE_")` thêm prefix lên mỗi authority nó tạo.
- `setAuthorityPrefix("")` bỏ tiền tố cho field được đọc, không đổi cách `hasRole` kiểm mặc định.
- `setAuthoritiesClaimDelimiter(regex)` (Spring Security 6.1+) dùng cho claim dạng chuỗi cần tách theo regex; không giải quyết JSON nested path.
- Nếu claim `roles` là list đúng type, converter có thể tạo một authority cho mỗi giá trị. Nếu roles nested hoặc có shape tùy biến, cần custom converter.

**Nguy cơ quan trọng:** nếu bạn thay hẳn default converter bằng converter chỉ đọc `roles`, các `SCOPE_*` được sinh từ scope trước đó có thể **biến mất**. Một endpoint vốn dựa vào `SCOPE_reports.read` có thể trở thành 403. Ngược lại, sửa bằng cách đổi prefix trên **scope** thành `ROLE_` có thể bất ngờ coi `scope="ADMIN"` là `ROLE_ADMIN` — nguy cơ cấp quyền quá mức nếu scope và business role có chủ thể phát hành/quản trị khác nhau.

## 5. Trước khi map role phải kiểm access token đáng tin

Role claim chỉ được dùng sau khi JWT được xác thực đúng. `JwtDecoder` phải kiểm:
- Chữ ký JWS bằng key của trusted issuer; không cho thuật toán “none” hoặc tự tin payload giải mã base64.
- `iss` issuer chính xác; không chấp nhận token từ IdP/realm tùy client đưa.
- `exp`, `nbf` và clock skew phù hợp.
- `aud` chứa audience của **resource server này**. Một token dành cho GraphQL frontend/other API không mặc nhiên dùng được cho orders-api.
- Các ràng buộc issuer/client/azp/tenant/token_type/claims khi hệ thống yêu cầu; không biến `aud` thành check toàn bộ trust model.
- Chỉ các token type có hợp đồng role claim đáng tin; không dùng OIDC ID token cấp cho client login làm access token của resource API.
- Key rotation/JWKS cache và allowed algorithms đúng provider.

Cấu hình Spring Boot 3.5 Resource Server minh họa:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/realms/acme
          audiences: orders-api
~~~

Đây là **URL giả**, phải thay bằng issuer metadata thực (khi triển khai). Property `issuer-uri` thiết lập issuer validation và key discovery; `audiences` bổ sung audience validation của Boot phiên bản tương ứng. Nếu tự định nghĩa `JwtDecoder`, phải bảo toàn các validators cần thiết; tạo decoder tùy ý nhưng quên issuer/audience là lỗi nghiêm trọng.

**Phân biệt 401 và 403:**
- JWT thiếu/sai signature, hết hạn, issuer/audience không hợp lệ → authentication thất bại, thường HTTP **401**.
- JWT hợp lệ, đã xác thực nhưng không có authority bắt buộc → authorization thất bại, thường HTTP **403**.

Không chuyển 403 thành 200 chỉ vì token “valid”. Ngược lại, một role claim tên `ADMIN` không phải bằng chứng token đúng audience.

## 6. Trường hợp đơn giản: roles là claim top-level

Nếu provider cam kết access token gửi:

~~~json
{"roles":["ADMIN","EDITOR"]}
~~~

và hệ thống **chỉ** dựa vào roles, có thể cấu hình:

~~~java
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter roles = new JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");

JwtAuthenticationConverter authenticationConverter =
        new JwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(roles);

// Sau khi JwtDecoder đã validate token:
// roles ["ADMIN", "EDITOR"] -> ROLE_ADMIN, ROLE_EDITOR.
~~~

Đây là **trích đoạn Java nằm trong method/config bean**, không phải file Java độc lập; imports được xuống dòng để dễ đọc và cần viết thành Java import một dòng nếu copy thẳng. Cấu hình thực phải gắn converter vào `oauth2ResourceServer(...).jwt(...)`.

**Giới hạn:**
1. Cấu hình trên có thể thay default scope mapping; nếu API còn dùng `SCOPE_orders.read`, cần **combine**, không thay.
2. `setAuthoritiesClaimName("roles")` không tự đi vào `realm_access.roles` hoặc `resource_access["orders-api"].roles`.
3. Token đã gửi `ROLE_ADMIN` có thể bị prefix kép.
4. Converter không biết role nào thực sự được phép cấp, ai là trusted issuer hay token có đúng audience; các phần này cần authentication validation và claim contract.
5. Nếu hệ thống multi-tenant hoặc multi-client, role top-level `ADMIN` là ambiguous nếu không gắn scope; không nên coi là superuser toàn SaaS.

Phần tiếp theo dùng một converter có allow-list và phân biệt namespace để vừa giữ scopes vừa map role.

## 7. Converter an toàn hơn: giữ SCOPE_, tạo ROLE_ đúng một lần

### 7.1. Chính sách của ví dụ

Giả sử API `orders-api` chấp nhận ba nguồn từ một **issuer đã được xác minh**:
- `scope`/`scp` → giữ `SCOPE_<scope>` qua converter mặc định.
- `roles` top-level và `realm_access.roles` → chỉ các tên đúng allow-list `ADMIN`, `EDITOR`, `VIEWER`, `AUDITOR` được tạo `ROLE_<name>`.
- `resource_access["orders-api"].roles` → role `read`/`write` được ánh xạ thành `PERM_ORDERS_READ`/`PERM_ORDERS_WRITE`. Không biến role `admin` của `other-client` thành global `ROLE_ADMIN`.

Đây là **hợp đồng minh họa**; trong triển khai thật, phải xem liệu provider/realm có đảm bảo vai trò `ADMIN` thực sự là global admin của orders-api hay không. Nếu không, hãy hạn chế/cấm map role ADMIN từ realm/global; chỉ xét claims được dành riêng cho resource API và giữ permission chi tiết.

### 7.2. File ScopesAndRolesConverter.java đầy đủ

Lưu `src/main/java/demo/authz/ScopesAndRolesConverter.java`:

~~~java
package demo.authz;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

/**
 * Spring Security 6.5.x, Java 17+.
 * Chỉ gọi converter này SAU KHI JwtDecoder validate token.
 * Không thực hiện I/O, không đọc HttpServletRequest.
 */
final class ScopesAndRolesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final Set<String> GLOBAL_ROLES =
            Set.of("ADMIN", "EDITOR", "VIEWER", "AUDITOR");

    private static final Map<String, String> ORDER_PERMISSIONS =
            Map.of(
                "read", "PERM_ORDERS_READ",
                "write", "PERM_ORDERS_WRITE");

    // Delegate giữ scope/scp -> SCOPE_xxx như Spring mặc định.
    private final JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        LinkedHashSet<GrantedAuthority> result =
                new LinkedHashSet<>(scopes.convert(jwt));

        // Claim top-level.
        addGlobalRoles(jwt.getClaims().get("roles"), result);

        // Realm roles: chỉ field đã thỏa contract với trusted issuer.
        Object realmRoles = child(
                jwt.getClaims().get("realm_access"), "roles");
        addGlobalRoles(realmRoles, result);

        // Chỉ client orders-api: tuyệt đối không duyệt mọi client.
        Object ordersRoles = child(
                child(jwt.getClaims().get("resource_access"),
                        "orders-api"),
                "roles");
        addOrderPermissions(ordersRoles, result);

        return List.copyOf(result);
    }

    private static Object child(Object candidate, String key) {
        if (candidate instanceof Map<?, ?> map) {
            return map.get(key);
        }
        return null;
    }

    private static void addGlobalRoles(
            Object candidate, Set<GrantedAuthority> result) {
        if (!(candidate instanceof Collection<?> names)) {
            return; // Thiếu/nhầm type: không tạo role.
        }
        for (Object item : names) {
            if (item instanceof String role
                    && GLOBAL_ROLES.contains(role)) {
                result.add(new SimpleGrantedAuthority(
                        "ROLE_" + role));
            }
        }
    }

    private static void addOrderPermissions(
            Object candidate, Set<GrantedAuthority> result) {
        if (!(candidate instanceof Collection<?> names)) {
            return;
        }
        for (Object item : names) {
            if (item instanceof String role) {
                String permission = ORDER_PERMISSIONS.get(role);
                if (permission != null) {
                    result.add(
                        new SimpleGrantedAuthority(permission));
                }
            }
        }
    }
}
~~~

**Tại sao thiết kế này kiểm soát ROLE_ tốt hơn?**
- `GLOBAL_ROLES.contains(role)` chấp nhận tên nguyên bản đúng contract, không chấp nhận `ROLE_ADMIN`, `admin`, `SUPERADMIN`, khoảng trắng hay chuỗi tương tự.
- Không có vòng lặp “nếu chưa có ROLE_ thì thêm, nếu có thì bỏ” tùy tiện; sai shape bị bỏ qua và không cấp quyền.
- `LinkedHashSet` loại duplicate giữa `roles` và `realm_access.roles`, giữ bộ kết quả rõ ràng.
- `scope/scp` tiếp tục được delegate xử lý, vì vậy `SCOPE_reports.read` vẫn còn.
- Client role `write` chỉ cho permission `PERM_ORDERS_WRITE`; tránh nâng nó thành global `ROLE_ADMIN`.
- Chỉ đọc key `orders-api` trong `resource_access`; `other-client.roles` hoàn toàn bị bỏ qua.
- Không nhận role từ user-submitted `X-Role`/form body; chỉ từ JWT đã được `JwtDecoder` validate.

**Điểm cần cải thiện theo chính sách tổ chức:** nếu roles thuộc tenant cụ thể, converter không nên phát một `ROLE_ADMIN` toàn cục. Có thể phát `TENANT_<opaque-id>_ROLE_ADMIN` trong một schema được kiểm soát, nhưng tenant-specific resource checks vẫn phải dùng trusted tenant/member/ACL source, không dựa mỗi authority string được cấu thành từ input client.

### 7.3. Lưu ý claim type và nested field

`JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName("realm_access.roles")` nhìn chung tìm một key claim **tên nguyên văn** `realm_access.roles`, không phải JSON-path parser. Với JSON:

~~~json
{"realm_access":{"roles":["AUDITOR"]}}
~~~

claim thực sự là một `Map` trong field `realm_access`. Custom converter ở trên dùng `instanceof Map<?, ?>` và lấy `roles` đúng tầng.

Nếu IdP có `roles` dạng chuỗi `"ADMIN EDITOR"` thay vì array, phải thống nhất schema:
- Có thể dùng `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimDelimiter("\\s+")` cho converter dedicated chỉ đọc claim dạng string.
- Hoặc map theo explicit parser đã test, reject malformed/mixed types.
- Không parse JSON bằng `toString().contains("ADMIN")`, `split(",")` trên object lồng hay regex duyệt token tùy ý.
- Nếu provider đổi shape, ưu tiên báo lỗi contract/metrics và deny đúng quyền thay vì “cố đoán” thành admin.

## 8. Spring Boot 3.5 Resource Server: cấu hình thật và endpoints

Tạo project Java 17+, Spring Boot 3.5.x gồm starters web, security, oauth2-resource-server. Chọn JWT access token cho Servlet API; **đừng thêm OAuth2 Login chỉ vì đã có OAuth2 Resource Server**.

Tạo hai file:
- `src/main/java/demo/authz/ScopesAndRolesConverter.java` (mục 7).
- `src/main/java/demo/authz/RoleClaimApplication.java` (bên dưới).

### 8.1. File RoleClaimApplication.java

~~~java
package demo.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class RoleClaimApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoleClaimApplication.class, args);
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
                new ScopesAndRolesConverter());
        // Principal mặc định dựa trên sub; đừng lấy role từ subject.
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        // hasRole tự kiểm authority ROLE_ADMIN.
                        .requestMatchers("/api/admin")
                            .hasRole("ADMIN")
                        // Method security sẽ kiểm permission/scopes.
                        .requestMatchers("/api/orders/check",
                                         "/api/reports")
                            .authenticated()
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resourceServer ->
                    resourceServer.jwt(jwt ->
                        jwt.jwtAuthenticationConverter(
                            jwtAuthenticationConverter)))
                .build();
    }
}

@Service
class SecureBusinessService {
    @PreAuthorize("hasAuthority('PERM_ORDERS_WRITE')")
    public String checkOrderWrite() {
        return "orders-write-allowed";
    }

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public String readReport() {
        return "reports-read-allowed";
    }
}

@RestController
class RoleEndpoints {
    private final SecureBusinessService service;

    RoleEndpoints(SecureBusinessService service) {
        this.service = service;
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin-allowed";
    }

    @GetMapping("/api/orders/check")
    String orders() {
        return service.checkOrderWrite();
    }

    @GetMapping("/api/reports")
    String reports() {
        return service.readReport();
    }
}
~~~

**Giải thích quyết định:**
1. Resource server JWT decoder xác thực token trước converter.
2. `jwtAuthenticationConverter` dùng converter kết hợp để giữ `SCOPE_*` và tạo `ROLE_*`/`PERM_*` theo claim contract.
3. `requestMatchers("/api/admin").hasRole("ADMIN")` kiểm `ROLE_ADMIN`. Không viết `hasRole("ROLE_ADMIN")`.
4. `/api/orders/check` yêu cầu authenticated ở filter, còn `SecureBusinessService.checkOrderWrite()` kiểm `PERM_ORDERS_WRITE` nhờ `@EnableMethodSecurity` và `@PreAuthorize` trên Spring bean.
5. `/api/reports` dùng `SCOPE_reports.read`; nếu trước đó thay scope mapping bằng converter chỉ đọc roles, test này sẽ 403 và phát hiện lỗi.
6. `anyRequest().denyAll()` tránh vô tình mở route mới.
7. Demo chỉ là GET để kiểm quyền; trong sản phẩm thật, WRITE/DELETE yêu cầu HTTP method thích hợp, resource/tenant ownership, CSRF policy nếu có session, transaction và audit.
8. Service invocation phải đi qua Spring-managed proxy; gọi `this.checkOrderWrite()` nội bộ trong cùng bean có thể bỏ qua method-security advice trong Spring AOP proxy mode.

### 8.2. build.gradle dependencies

Trong một project đã khai báo Spring Boot Gradle plugin, repositories và Java 17:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Boot starter resource server kéo theo các dependency JWT/Jose cần thiết theo BOM; tránh trộn spring-security modules phiên bản khác nhau. Mẫu trên nhắm Boot 3.5/Security 6.5 để dùng `@MockitoBean` trong test.

### 8.3. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/realms/acme
          audiences: orders-api
~~~

Đây là placeholder issuer hợp lệ về cấu trúc nhưng không có IdP thật. Không thể gọi API production bằng token do chính bạn tự sửa claim. Trong thực tế dùng issuer URL chính thức, audience đã được IdP cấp cho API; cấu hình trust thuật toán/key rotation và token lifetime theo chính sách tổ chức.

**Không** có `spring.security.oauth2.client.registration...` trong demo Resource Server. Các cấu hình OAuth2 Login áp cho ứng dụng đăng nhập OIDC là luồng khác (xem mục 12).

### 8.4. Ma trận mong muốn của demo

| Access token sau khi decode | Authorities sau converter | `/api/admin` | `/api/orders/check` | `/api/reports` |
| --- | --- | --- | --- | --- |
| role ADMIN; client orders-api/write; scope reports.read | `ROLE_ADMIN`, `PERM_ORDERS_WRITE`, `SCOPE_reports.read` | 200 | 200 | 200 |
| role VIEWER; scope reports.read | `ROLE_VIEWER`, `SCOPE_reports.read` | 403 | 403 | 200 |
| role `ROLE_ADMIN`; không role ADMIN | Không có `ROLE_ADMIN` từ role này | 403 | Theo permissions còn lại | Theo scopes còn lại |
| only other-client/admin | Không tạo admin orders-api | 403 | 403 | Theo scopes còn lại |
| Valid JWT nhưng không có roles/scopes | Rỗng | 403 | 403 | 403 |
| Invalid signature/issuer/audience/expired | Authentication reject | 401 | 401 | 401 |

Kết quả có thể thay đổi nếu bạn thêm authorization filter, role hierarchy hoặc custom exception handling; nhưng nguyên tắc **không map sai role/permission** không đổi.

## 9. Unit test converter: phát hiện prefix kép, claim lồng và không mất scopes

Lưu `src/test/java/demo/authz/ScopesAndRolesConverterTest.java`:

~~~java
package demo.authz;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ScopesAndRolesConverterTest {
    private final ScopesAndRolesConverter converter =
            new ScopesAndRolesConverter();

    private Jwt jwt(Object roles, Object realmAccess,
                    Object resourceAccess) {
        return Jwt.withTokenValue("unit-test-only")
                .header("alg", "RS256")
                .claim("sub", "user-7")
                .claim("scope", "reports.read orders.read")
                .claim("roles", roles)
                .claim("realm_access", realmAccess)
                .claim("resource_access", resourceAccess)
                .build();
    }

    private Set<String> names(Jwt jwt) {
        return converter.convert(jwt).stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
    }

    @Test
    void keepsScopesAndMapsOnlyApprovedRoles() {
        Jwt token = jwt(
                List.of("ADMIN", "ROLE_ADMIN", "unknown"),
                Map.of("roles", List.of("AUDITOR")),
                Map.of(
                    "orders-api", Map.of("roles", List.of("write")),
                    "other-client", Map.of("roles", List.of("admin"))));

        assertEquals(Set.of(
                "SCOPE_reports.read",
                "SCOPE_orders.read",
                "ROLE_ADMIN",
                "ROLE_AUDITOR",
                "PERM_ORDERS_WRITE"), names(token));
    }

    @Test
    void alreadyPrefixedAndUnknownRolesDoNotGrantAdmin() {
        Jwt token = jwt(
                List.of("ROLE_ADMIN", "admin", "SUPERADMIN"),
                Map.of("roles", List.of("ROLE_ADMIN")),
                Map.of("other-client",
                        Map.of("roles", List.of("admin"))));

        Set<String> authorities = names(token);
        assertFalse(authorities.contains("ROLE_ADMIN"));
        assertFalse(authorities.contains("ROLE_ROLE_ADMIN"));
        assertFalse(authorities.contains("PERM_ORDERS_WRITE"));
        assertTrue(authorities.contains("SCOPE_reports.read"));
    }

    @Test
    void malformedClaimsDoNotCreateRoles() {
        Jwt token = jwt(
                "ADMIN",
                Map.of("roles", "ADMIN"),
                Map.of("orders-api", Map.of("roles", 123)));

        Set<String> authorities = names(token);
        assertEquals(Set.of(
                "SCOPE_reports.read", "SCOPE_orders.read"),
                authorities);
    }

    @Test
    void duplicateRolesBecomeOneAuthority() {
        Jwt token = jwt(
                List.of("ADMIN", "ADMIN"),
                Map.of("roles", List.of("ADMIN")),
                Map.of());

        Set<String> authorities = names(token);
        assertEquals(1, authorities.stream()
                .filter("ROLE_ADMIN"::equals).count());
    }
}
~~~

**Ý nghĩa các test:**
- Test map thật trên một `Jwt` Java object; header `alg=RS256` trong test **không có chữ ký**, chỉ là fixture để kiểm converter.
- Authorities được so sánh bằng set để không phụ thuộc thứ tự.
- Claim đã prefix `ROLE_ADMIN` bị bỏ qua, không tạo `ROLE_ROLE_ADMIN` và cũng không tự được coi là ADMIN.
- `other-client.roles` không cấp permission hay global role.
- Khi nested fields sai kiểu, converter không cấp thêm role.
- Scope vẫn được giữ mặc định, giúp test phát hiện việc vô tình thay converter nhưng bỏ scope mapping.
- Unit test này không chứng minh token signature, issuer, audience hay expired validation: đó là trách nhiệm của decoder và các integration tests.

## 10. MockMvc với mocked JwtDecoder: kiểm SecurityFilterChain và method security

Nhiều ví dụ dùng:

~~~java
mvc.perform(get("/api/admin")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("ROLE_ADMIN"))));
~~~

Test `jwt().authorities(...)` **tự đặt authorities** nên có thể PASS ngay cả khi converter production bị cấu hình sai! Để kiểm pipeline authorities đúng, cách dưới đây gửi Bearer token vào resource-server filter và mock **chỉ JwtDecoder** để trả Jwt đã xác định. Bộ converter và authorization thật vẫn chạy.

Bài chọn Spring Boot **3.5.x** có Spring Framework `@MockitoBean`. Lưu `src/test/java/demo/authz/RoleClaimApplicationTest.java`:

~~~java
package demo.authz;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class RoleClaimApplicationTest {
    @Autowired MockMvc mvc;

    @MockitoBean JwtDecoder decoder;

    private Jwt token(String tokenValue, Object roles,
                      String scope, Object resourceAccess) {
        return Jwt.withTokenValue(tokenValue)
                .header("alg", "RS256")
                .claim("sub", "user-7")
                .claim("scope", scope)
                .claim("roles", roles)
                .claim("resource_access", resourceAccess)
                .build();
    }

    @BeforeEach
    void decoderFixtures() {
        when(decoder.decode("admin-token"))
                .thenReturn(token(
                    "admin-token", List.of("ADMIN"),
                    "reports.read",
                    Map.of("orders-api",
                        Map.of("roles", List.of("write")))));

        when(decoder.decode("viewer-token"))
                .thenReturn(token(
                    "viewer-token", List.of("VIEWER"),
                    "reports.read", Map.of()));

        when(decoder.decode("double-prefix-token"))
                .thenReturn(token(
                    "double-prefix-token", List.of("ROLE_ADMIN"),
                    "", Map.of()));

        when(decoder.decode("other-client-token"))
                .thenReturn(token(
                    "other-client-token", List.of(),
                    "", Map.of("other-client",
                        Map.of("roles", List.of("admin")))));

        when(decoder.decode("invalid-token"))
                .thenThrow(new BadJwtException("invalid token"));
    }

    private org.springframework.test.web.servlet.request
        .MockHttpServletRequestBuilder bearer(
            String path, String token) {
        return get(path).header(
                "Authorization", "Bearer " + token);
    }

    @Test
    void approvedRoleMatchesHasRole() throws Exception {
        mvc.perform(bearer("/api/admin", "admin-token"))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-allowed"));
    }

    @Test
    void appSpecificPermissionMatchesMethodSecurity()
            throws Exception {
        mvc.perform(bearer("/api/orders/check", "admin-token"))
                .andExpect(status().isOk())
                .andExpect(content().string("orders-write-allowed"));
    }

    @Test
    void scopesSurviveRoleMapping() throws Exception {
        mvc.perform(bearer("/api/reports", "viewer-token"))
                .andExpect(status().isOk())
                .andExpect(content().string("reports-read-allowed"));
    }

    @Test
    void viewerCannotCallAdminOrWriteOrder()
            throws Exception {
        mvc.perform(bearer("/api/admin", "viewer-token"))
                .andExpect(status().isForbidden());
        mvc.perform(bearer("/api/orders/check", "viewer-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void roleAlreadyPrefixedIsNotAdmin() throws Exception {
        mvc.perform(bearer("/api/admin", "double-prefix-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unrelatedClientRoleDoesNotGrant() throws Exception {
        mvc.perform(bearer("/api/admin", "other-client-token"))
                .andExpect(status().isForbidden());
        mvc.perform(bearer("/api/orders/check",
                           "other-client-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenIsUnauthenticated() throws Exception {
        mvc.perform(bearer("/api/admin", "invalid-token"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingBearerTokenIsUnauthenticated()
            throws Exception {
        mvc.perform(get("/api/reports"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

**Lưu ý khi copy:** Java import không được xuống dòng ở giữa package/class. Trong đoạn code ở trên, signature helper `bearer(...)` được ngắt dòng cho Markdown nhưng return type tên lớp phải viết theo cú pháp `org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder` **liền một dòng** hoặc thêm import `MockHttpServletRequestBuilder` rồi để return type một từ. Cách đơn giản nhất khi áp dụng là:

~~~java
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

// Thay đúng phần khai báo method helper trong test:
private MockHttpServletRequestBuilder bearer(
        String path, String token) {
    return get(path).header(
            "Authorization", "Bearer " + token);
}
~~~

Các imports khác của file test ở trên là đầy đủ cho Boot 3.5, riêng helper có cách thay gọn hơn để đảm bảo Java parser. **Không chép cả hai khai báo `bearer` cùng lúc**. Nội dung bài intentionally giải thích chỗ code cần được chuẩn hóa khi định dạng, không phải ví dụ biên dịch hai helper.

### 10.1. Những test nào vẫn còn thiếu?

Mock `JwtDecoder` giúp chạy Spring JWT filter + converter + authorization, nhưng **bỏ qua chính việc kiểm chữ ký/JWKS/issuer/audience/expiry**. Một integration test khác phải dùng **token được ký bằng test private key**, decoder/JWKS test endpoint và khẳng định:
- Đúng signature+issuer+audience+thời hạn ⇒ resource server xét authorities.
- Sai signature, `alg` bị cấm, issuer khác, `aud` không dành cho API, expired/nbf tương lai ⇒ 401.
- JWT hợp lệ nhưng roles thiếu/unknown/client khác ⇒ 403.
- Không lấy ID token từ OAuth2 login thay access token API.
- Keys rotate/thu hồi theo provider contract.
- Role được revoke thì hành vi phụ thuộc TTL/token freshness; nếu yêu cầu revoke ngay, cần kỹ thuật thêm.

### 10.2. Vì sao không chỉ dùng `@WithMockUser(roles="ADMIN")`?

`@WithMockUser(roles="ADMIN")` tạo mock Authentication có `ROLE_ADMIN` trực tiếp. Nó hữu ích để test **method rule** độc lập, nhưng không kiểm JWT claim mapping. Test converter nên tạo Jwt fixtures; test filter thì mock JwtDecoder; test toàn bộ trust cần signed token/JWKS. Ba lớp test có mục đích khác nhau, đừng coi một lớp thay lớp còn lại.

## 11. Test role prefix bằng ma trận thực tế

| Source input | Mapping mong muốn | Điều cần assert |
| --- | --- | --- |
| `scope="reports.read"` | `SCOPE_reports.read` | Không biến thành `ROLE_reports.read` |
| `scp=["orders.read"]` | `SCOPE_orders.read` | Default converter giữ scoped authority |
| `roles=["ADMIN"]` | `ROLE_ADMIN` | `hasRole("ADMIN")` GRANT |
| `roles=["ROLE_ADMIN"]` | Bỏ/deny theo contract minh họa | Không tạo `ROLE_ROLE_ADMIN` |
| `roles=["admin"]` | Bỏ/deny | Case-sensitive |
| `roles=["SUPERADMIN"]` | Bỏ/deny | Allow-list |
| `roles=["ADMIN","ADMIN"]` | Một `ROLE_ADMIN` | Dedup |
| `realm_access.roles=["AUDITOR"]` | `ROLE_AUDITOR` | Chỉ trusted realm |
| `resource_access.orders-api.roles=["write"]` | `PERM_ORDERS_WRITE` | Không global admin |
| `resource_access.other-client.roles=["admin"]` | Bỏ qua | Không cross-client privilege |
| `roles="ADMIN"` (string) | Bỏ theo converter này | Không silently parse shape khác |
| `realm_access.roles=123` | Bỏ | Malformed claim |
| JWT hợp lệ nhưng audience sai | Decoder reject | 401, converter không được chạy |
| User role ADMIN tenant A, request tenant B | Tenant policy quyết định, không dựa global role | Không cấp quyền tenant B |
| Claim bỗng chuyển array→string do IdP update | Contract test fail | Không tự mở quyền |

Một converter đơn giản có thể sử dụng `setAuthorityPrefix("ROLE_")` để đủ cho role claim top-level **đúng contract**, nhưng không phải mọi hệ thống OAuth2 đều nên dùng nó.

## 12. OAuth2 Resource Server khác OAuth2/OIDC Login

### 12.1. Resource Server nhận Bearer access token

Demo chính:
- App là **API** nhận `Authorization: Bearer <access token>`.
- `JwtDecoder` validate token.
- `JwtAuthenticationConverter` chuyển JWT claims vào authorities.
- Controller/method security kiểm `JwtAuthenticationToken`.
- Không có web login redirect/session OAuth2 user bắt buộc.

### 12.2. OAuth2 Login là một pipeline khác

Trong web app dùng:

~~~java
http.oauth2Login(login -> login
        .userInfoEndpoint(userInfo ->
                userInfo.userAuthoritiesMapper(myAuthoritiesMapper)));
~~~

`myAuthoritiesMapper` là `GrantedAuthoritiesMapper` cho authorities của `OAuth2User` hoặc `OidcUser`, không phải một `JwtAuthenticationConverter` của bearer resource server. Nó có thể nhận `OAuth2UserAuthority`/`OidcUserAuthority` và các scope authorities của người đăng nhập.

OIDC roles có thể nằm ở **ID token**, UserInfo hoặc một endpoint backend khác; nguồn nào được phép cấp app role phải được đánh giá theo security/privacy contract. Nếu cần gọi protected API để lấy roles, dùng delegated `OidcUserService`/`OAuth2UserService` và token đúng audience, không tự parse ID token của frontend như access token resource server.

### 12.3. Mẫu mapper OIDC mang tính trích đoạn

~~~java
// Trong cấu hình oauth2Login, khác Resource Server JWT.
// Chỉ minh họa shape; phần kiểm issuer/claim policy cần bổ sung.
GrantedAuthoritiesMapper mapper = input -> {
    Set<GrantedAuthority> output =
            new LinkedHashSet<>(input);

    for (GrantedAuthority authority : input) {
        if (authority instanceof OidcUserAuthority oidc) {
            Object raw = oidc.getIdToken().getClaims().get("roles");
            if (raw instanceof Collection<?> roles) {
                for (Object item : roles) {
                    if ("VIEWER".equals(item)) {
                        output.add(new SimpleGrantedAuthority(
                                "ROLE_VIEWER"));
                    }
                }
            }
        }
    }
    return output;
};
~~~

Đây là snippet đặt trong Java method có các imports `GrantedAuthoritiesMapper`, `GrantedAuthority`, `OidcUserAuthority`, `LinkedHashSet`, `Set`, `Collection` và `SimpleGrantedAuthority`. Không đưa snippet vào file Resource Server chính như thể được auto-wire. Đặc biệt, OIDC `ID token` được phát để client xác thực end user, không phải bearer access token tiêu chuẩn để gọi mọi resource server.

## 13. Reactive WebFlux: cùng policy nhưng converter khác

Trong WebFlux Resource Server, sử dụng `ReactiveJwtAuthenticationConverter` thay vì inject thẳng `JwtAuthenticationConverter` Servlet vào reactive DSL. Với converter đồng bộ không block từ mục 7, dùng adapter:

~~~java
// Trích đoạn trong @Bean config WebFlux Spring Security 6.5:
ReactiveJwtAuthenticationConverter reactive =
        new ReactiveJwtAuthenticationConverter();

reactive.setJwtGrantedAuthoritiesConverter(
        new ReactiveJwtGrantedAuthoritiesConverterAdapter(
                new ScopesAndRolesConverter()));

// Tại ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)
// dùng reactive.jwtAuthenticationConverter(reactive).
~~~

Adapter nhận `Converter<Jwt, Collection<GrantedAuthority>>` và tạo `Converter<Jwt, Flux<GrantedAuthority>>`; converter gốc phải **non-blocking**. `ScopesAndRolesConverter` chỉ map Map/List và strings nên phù hợp; nếu cần PIP network/DB, dùng reactive converter/service và bảo vệ timeout/fail closed, không `block()` trong pipeline.

Không nhầm `hasRole` ở WebFlux HTTP với method SpEL hay một custom `ReactiveAuthorizationManager`; theo default `ROLE_ADMIN` vẫn là authority cần có nếu gọi `hasRole("ADMIN")`. Kiểm lại ở cả HTTP/method test khi version hoặc prefix config đổi.

## 14. Tenant role, global admin và dữ liệu nghiệp vụ

Một JWT có `roles=["ADMIN"]` có thể là:
- Administrator của toàn **realm** nhưng không được sửa dữ liệu mọi tenant.
- Administrator của riêng một client (có hiệu lực khác nhau từng ứng dụng).
- Administrator của một tenant cụ thể trong một hệ thống multi-tenant.
- Role kỹ thuật chỉ để truy cập dashboard IdP, không phải business permission.

Nếu map tất cả thành global `ROLE_ADMIN` và đặt `hasRole("ADMIN")` cho mọi data endpoint, có thể xảy ra **horizontal privilege escalation**. Không dùng tên role làm thay thế tenant membership/object ACL.

Ví dụ bảo vệ tài liệu:
1. JWT được validate đúng issuer/audience.
2. Converter có thể map `ROLE_EDITOR`.
3. Request muốn `PATCH /tenants/beta/documents/7`.
4. Service xác minh actor có membership EDITOR trong **beta**, không chỉ EDITOR ở alpha.
5. DB query/update có predicate `tenant_id=beta AND id=7`, kiểm owner/ACL/classification tùy policy.
6. Nếu permission bị revoke giữa check và write, dùng freshness/transaction/version guards.

Không cache `ALLOW` chỉ theo `documentId` hoặc `ROLE_ADMIN`. Cache keys/policy phải phân biệt principal, tenant, action, resource và ACL/membership/policy revision phù hợp. Với quyền nhạy cảm, không cache ALLOW hoặc revalidate theo SLA.

### 14.1. Không đưa tenantId do caller tự khai vào role authority mà chưa xác minh

Phản ví dụ:

~~~java
String tenant = request.getHeader("X-Tenant");
authorities.add(new SimpleGrantedAuthority(
        "ROLE_" + tenant + "_ADMIN"));
~~~

Header có thể giả mạo. Nếu triển khai tenant-scoped authority namespace, tenant phải đến từ trusted membership source/claim đã xác minh và permission check ở resource scoped; tên authority tự ghép không tạo tính xác thực.

### 14.2. Role hierarchy và phạm vi

Nếu cấu hình `ROLE_ADMIN > ROLE_EDITOR > ROLE_VIEWER` qua role hierarchy, một ADMIN có thể thừa hưởng nhiều authorities trong nơi hierarchy được áp. Điều này tiện nhưng tăng bề mặt quyền. Không mở hierarchy toàn cục giữa realm/tenant/client role khi nghiệp vụ không muốn. Kiểm role hierarchy thực được gắn vào method/http authorization manager bạn sử dụng; không cho rằng mọi phương thức mặc nhiên biết hierarchy.

## 15. Revocation, token staleness và policy thay đổi

JWT access token đã ký thường là self-contained. Nếu Alice bị gỡ role ADMIN sau khi token được cấp, API có thể vẫn thấy claim ADMIN tới khi token hết hạn, trừ khi kiến trúc áp thêm cơ chế:
- Access token short-lived và refresh token rotation.
- Token introspection/reference token hoặc revocation list trong resource server khi cần gần thời gian thực.
- Server-side membership/role revision check ở một PIP đáng tin.
- Event-driven cache invalidation và monitoring.
- Session invalidation cho web OAuth2 Login, không đồng nhất với thu hồi JWT access token.
- Kết hợp policy version/ACL checks cho thao tác nhạy cảm.

Không nói “cập nhật role trên IdP là API mất quyền ngay tức thì” nếu đang dùng JWT không có revocation lookup. Cân bằng latency/availability với revoke SLA, có negative tests chứng minh hành vi đã chọn.

## 16. Kiểm logging và lỗi bảo mật thường gặp

### 16.1. Không log toàn JWT cho debug

JWT có thể chứa name, email, tenants, roles, device data hoặc internal IDs. Dù payload base64URL dễ decode, token header/body là sensitive; raw bearer token còn là credential. Log tối thiểu:
- Request ID, issuer identifier đã chuẩn hóa, opaque subject (nếu policy cho phép), outcome 401/403, endpoint/action, authority category với redaction.
- Không log Authorization header, raw JWT, refresh token, private key/JWKS secrets hoặc toàn bộ claim set.
- Debug mapping riêng trong môi trường test bằng fixture token, không dùng production users để in authorities đầy đủ.

### 16.2. Những lỗi phổ biến

1. **JWT `roles=["ADMIN"]` nhưng Spring vẫn 403:** Resource Server mặc định map scopes thành `SCOPE_*`; chưa map role claim.
2. **`hasRole("ROLE_ADMIN")`:** truyền role đã prefix vào API có thể bị prefix thêm/từ chối; dùng `hasRole("ADMIN")`.
3. **`hasAuthority("ADMIN")` với authority `ROLE_ADMIN`:** không match; dùng full string.
4. **`ROLE_ROLE_ADMIN`:** IdP đã prefix, converter thêm lần nữa; thống nhất raw role schema.
5. **Dùng `setAuthorityPrefix("ROLE_")` trên scope claim:** biến OAuth2 scope thành business role không có security review.
6. **Chỉ đổi claim name sang roles:** làm mất `SCOPE_*` nếu không combine converter.
7. **`setAuthoritiesClaimName("realm_access.roles")`:** không đọc nested path; cần custom Map traversal.
8. **Map tất cả roles của `resource_access`:** role client khác vô tình cấp quyền orders-api.
9. **Không allow-list roles:** typo/unknown role/colliding names có thể sinh bất ngờ authorities.
10. **Tin role từ headers/body/unsigned JWT:** token không được xác thực hoặc client có thể tự khai.
11. **Chỉ kiểm issuer, quên audience:** token cấp cho service khác có thể bị chấp nhận.
12. **Dùng ID token như API Bearer access token:** sai token purpose/audience.
13. **Chỉ kiểm role global trên tenant-specific object:** không thay membership/ACL/database scope.
14. **Test `jwt().authorities(...)` rồi nghĩ converter đúng:** test đã bypass converter.
15. **Mock JwtDecoder nhưng tuyên bố signature validation đã test:** chưa; cần signed token/JWKS integration.
16. **Đổi GrantedAuthorityDefaults mà nghĩ toàn ứng dụng tự đồng bộ:** HTTP/method/custom manager có thể khác prefix semantics.
17. **Làm role mapping bằng `contains("ADMIN")`:** `SUPERADMIN` hoặc comment string có thể bị nhận nhầm.
18. **Coi upper/lowercase tương đương:** Spring authority strings phân biệt chính xác.
19. **Cache ALLOW lâu dù role đã revoke:** stale JWT/ACL, cần revocation strategy.
20. **Trộn Spring Servlet JwtAuthenticationConverter với WebFlux ReactiveJwtAuthenticationConverter:** pipeline không tương thích.
21. **Thiếu `@EnableMethodSecurity`:** `@PreAuthorize` có thể không được thực thi; test proxy/service thật.
22. **Cho endpoint `anyRequest().authenticated()` mà không kiểm quyền cụ thể:** JWT hợp lệ không tự có quyền trên object.
23. **Lấy roles từ claim của một issuer không nằm trong trust list:** map trên dữ liệu không đáng tin.
24. **Lấy scopes từ UserInfo để cấp global admin:** scope là OAuth client delegation, không phải admin identity.
25. **Không test malformed role array/map:** converter có thể throw, mất 500 hoặc fail open ở custom exception path.

## 17. Checklist triển khai production

| Phạm vi | Cần xác minh |
| --- | --- |
| Token type | Access token phù hợp resource server, không nhầm OIDC ID token |
| Signature | JWS verified, trusted algorithms/JWKS/keys |
| Issuer | `iss` chỉ trusted realm/IdP |
| Audience | `aud` đúng orders-api/resource |
| Lifecycle | `exp`/`nbf`/clock skew, revocation SLA |
| Default scopes | `scope`/`scp` tiếp tục thành `SCOPE_*` |
| Role sources | Chỉ claim được quy định, nested path chính xác |
| Prefix | Một lần `ROLE_`, không `ROLE_ROLE_ADMIN` |
| Role allow-list | ADMIN/EDITOR/VIEWER/AUDITOR hoặc contract chính thức |
| Client isolation | Không lấy role từ arbitrary resource_access clients |
| Tenant | Kiểm membership và DB resource scope độc lập |
| Method security | `@EnableMethodSecurity` và proxy invocation |
| HTTP security | `hasRole("ADMIN")`/`hasAuthority(...)` thống nhất |
| Unknown roles | Không tạo authority quản trị từ giá trị không biết |
| Malformed claims | Không cấp quyền nếu type sai |
| OAuth2 Login | Mapper/UserService riêng nếu web login |
| WebFlux | Dùng ReactiveJwtAuthenticationConverter/adapter nonblocking |
| Negative tests | 401 invalid JWT, 403 valid/no roles, prefix mismatch |
| Mapping tests | Unit converter + filter integration + signed JWT/JWKS |
| Monitoring | 401/403 metrics, mapping drift, provider schema changes |
| Logging | Không raw JWT/PII/secrets; trace an toàn |
| Operations | Short-lived tokens, key rotation, role revocation plan |

### 17.1. Mutation tests để chứng minh test suite hiệu quả

Cố ý làm hỏng một nhánh trong bản test:
- Xóa `roles` mapping → `approvedRoleMatchesHasRole` phải thất bại.
- Bỏ scope delegate → `scopesSurviveRoleMapping` phải thất bại.
- Chuyển client role `write` thành `ROLE_ADMIN` → test `unrelatedClientRoleDoesNotGrant` và negative role tests phải phát hiện thiết kế sai (nên thêm test client role write không tạo ADMIN).
- Chấp nhận `ROLE_ADMIN` đã prefix bằng cách nối thêm `ROLE_` → test double-prefix phải thất bại.
- Bỏ `@EnableMethodSecurity` → endpoint /api/orders/check có thể trả 200 cho viewer; test phải thất bại.
- Bỏ audience validation trong production decoder → signed wrong-audience test phải thất bại.
- Bỏ tenant predicate repository → cross-tenant object tests phải thất bại.

Test chỉ có một happy path 200 không thể khẳng định role mapping an toàn.

## 18. Java 17 độc lập: prefix mapping và decision không phụ thuộc Spring

Chương trình sau chạy bằng **JDK 17 thuần** và mô phỏng đúng policy mapping đã lựa chọn: giữ scopes riêng, chỉ nhận role allow-list từ claim cấu trúc đã biết, client permissions theo tên app, không thêm prefix hai lần. Nó **không triển khai signature/JWT verification, Spring SecurityFilterChain, OAuth2 Login hay Reactor**.

Lưu thành `RolePrefixDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class RolePrefixDemo {
    record Token(List<String> roles, List<String> scopes,
                 Map<String, List<String>> clientRoles) {}

    private static final Set<String> ALLOWED_GLOBAL =
            Set.of("ADMIN", "EDITOR", "VIEWER", "AUDITOR");

    static Set<String> authorities(Token token) {
        Set<String> result = new TreeSet<>();

        for (String scope : token.scopes()) {
            if (scope != null && !scope.isBlank()) {
                result.add("SCOPE_" + scope);
            }
        }

        for (String role : token.roles()) {
            if (ALLOWED_GLOBAL.contains(role)) {
                result.add("ROLE_" + role);
            }
        }

        for (String role : token.clientRoles()
                                .getOrDefault("orders-api", List.of())) {
            if ("read".equals(role)) {
                result.add("PERM_ORDERS_READ");
            }
            if ("write".equals(role)) {
                result.add("PERM_ORDERS_WRITE");
            }
        }
        return result;
    }

    static boolean hasRole(Set<String> a, String role) {
        return a.contains("ROLE_" + role);
    }

    static boolean hasAuthority(Set<String> a, String exact) {
        return a.contains(exact);
    }

    public static void main(String[] args) {
        Token admin = new Token(
                List.of("ADMIN", "ROLE_ADMIN"),
                List.of("reports.read"),
                Map.of("orders-api", List.of("write")));

        Token viewer = new Token(
                List.of("VIEWER"),
                List.of("reports.read"),
                Map.of("other-client", List.of("admin")));

        Token invalid = new Token(
                List.of("ROLE_ADMIN", "SUPERADMIN", "admin"),
                List.of(),
                Map.of("orders-api", List.of("unexpected")));

        Set<String> a = authorities(admin);
        Set<String> v = authorities(viewer);
        Set<String> x = authorities(invalid);

        System.out.println("admin-authorities=" + a);
        System.out.println("admin-hasRole-ADMIN=" +
                hasRole(a, "ADMIN"));
        System.out.println("admin-hasAuthority-ADMIN=" +
                hasAuthority(a, "ADMIN"));
        System.out.println("admin-hasAuthority-ROLE_ADMIN=" +
                hasAuthority(a, "ROLE_ADMIN"));
        System.out.println("admin-orders-write=" +
                hasAuthority(a, "PERM_ORDERS_WRITE"));
        System.out.println("viewer-authorities=" + v);
        System.out.println("viewer-hasRole-ADMIN=" +
                hasRole(v, "ADMIN"));
        System.out.println("viewer-hasScope-reports=" +
                hasAuthority(v, "SCOPE_reports.read"));
        System.out.println("invalid-authorities=" + x);
        System.out.println("invalid-hasRole-ADMIN=" +
                hasRole(x, "ADMIN"));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 RolePrefixDemo.java
java RolePrefixDemo
~~~

**stdout chính xác** (TreeSet cho thứ tự ổn định):

~~~text
admin-authorities=[PERM_ORDERS_WRITE, ROLE_ADMIN, SCOPE_reports.read]
admin-hasRole-ADMIN=true
admin-hasAuthority-ADMIN=false
admin-hasAuthority-ROLE_ADMIN=true
admin-orders-write=true
viewer-authorities=[ROLE_VIEWER, SCOPE_reports.read]
viewer-hasRole-ADMIN=false
viewer-hasScope-reports=true
invalid-authorities=[]
invalid-hasRole-ADMIN=false
~~~

Bài tập: thêm `ADMIN` vào `other-client` mà không đưa vào `roles` thì không được sinh `ROLE_ADMIN`. Thêm `ROLE_ADMIN` vào `roles` mà không có `ADMIN` thì theo hợp đồng này phải DENY admin. Nếu bạn đổi code cho phép mọi `scope` biến thành `ROLE_`, hãy tự hỏi đối tượng nào thực sự được quyền phát role ADMIN.

**Giới hạn:** đây là mô phỏng Java strings, không chứng minh chữ ký/token audience hoặc authority mapping của Spring. Các lớp Spring phải được kiểm trong test converter và HTTP filter như mục 9–10.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Token có `scope="admin"` nhưng không có role claim. Có nên dùng `setAuthorityPrefix("ROLE_")` để `hasRole("ADMIN")` thành công?

**Đáp án:** Không mặc định. Scope là authorization grant của OAuth client, không phải cùng namespace/quy tắc phát hành business role. Phải có chính sách issuer/audience/scope→role được phê duyệt rõ; an toàn hơn giữ `SCOPE_admin` cho scope và chỉ phát `ROLE_ADMIN` từ trusted role source.

**Câu 2.** IdP trả `roles=["ROLE_ADMIN"]` nhưng converter tiền tố `ROLE_`. App kiểm `hasRole("ADMIN")` có grant không?

**Đáp án:** Không với prefix kép `ROLE_ROLE_ADMIN`. Sửa contract tại IdP hoặc converter, không đổi matcher để chấp nhận giá trị sai bất ngờ.

**Câu 3.** Tại sao `setAuthoritiesClaimName("realm_access.roles")` thường không hoạt động?

**Đáp án:** Nó chọn tên claim top-level, không tự parse nested JSON. Cần traverse `realm_access` map rồi đọc list `roles`; giới hạn role names và issuer.

**Câu 4.** Khi thay converter chỉ lấy roles, tại sao API trước đây cần `SCOPE_orders.read` bị 403?

**Đáp án:** Default scope mapper đã bị thay thế. Phải delegate/combine hai nguồn vào một collection authorities thay vì thay toàn bộ bằng roles.

**Câu 5.** Resource Server có token với issuer hợp lệ, role ADMIN, nhưng audience chỉ dành cho service khác. Có được map ADMIN không?

**Đáp án:** Không; decoder/validator cần reject token sai audience trước role mapping. Issuer đúng không bảo đảm token có hiệu lực cho mọi API.

**Câu 6.** `jwt().authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` trong MockMvc test đã chứng minh mapper thật hoạt động chưa?

**Đáp án:** Chưa. Test đã tự gán authorities. Unit test converter và test đi qua resource server với mocked decoder/signed JWT mới kiểm mapping.

**Câu 7.** JWT mang `resource_access.other-client.roles=["admin"]`, orders-api có được thành global `ROLE_ADMIN` không?

**Đáp án:** Không. Role thuộc namespace của client khác; chỉ map client app được phép và đúng security contract, không duyệt tất cả.

**Câu 8.** Tại sao `ROLE_ADMIN` trong token không đủ cho truy vấn `/tenants/beta/documents/7`?

**Đáp án:** Role global hoặc realm admin không tự chứng minh membership tenant beta hay quyền object. Service vẫn phải xác minh tenant/action/ACL và query theo trusted tenant.

**Câu 9.** Nếu user đã bị gỡ role ở IdP, tại sao API vẫn có thể cho phép trong vài phút?

**Đáp án:** Access token self-contained vẫn mang claim cũ đến khi hết hạn; muốn revoke sớm phải có short TTL/role revision/introspection/revocation check phù hợp SLA.

**Câu 10.** Vì sao converter cần allow-list mà không tự map mọi chuỗi `roles`?

**Đáp án:** Nó giảm nguy cơ IdP thêm role lạ, lỗi case/schema, trùng namespace, role của client khác hoặc chấp nhận chuỗi không hợp lệ thành quyền cao. Chỉ map role được provider + API đồng thuận về semantics.

## 20. Kết luận

Hãy xem role claim mapping là một **hợp đồng bảo mật hai chiều** chứ không chỉ là việc nối chuỗi:

~~~text
Trusted access token
    -> signature/issuer/audience/expiry validated by JwtDecoder
    -> parse approved claims and exact shapes
       -> OAuth scopes             => SCOPE_...
       -> approved global roles    => ROLE_...
       -> approved client roles    => PERM_...
    -> JwtAuthenticationToken authorities
    -> hasRole("ADMIN") or hasAuthority("ROLE_ADMIN")
    -> tenant/resource/action authorization
    -> protected operation and audit
~~~

Ba điều cần nhớ:

- **ROLE_ được tạo đúng một lần, kiểm chính xác.** `hasRole("ADMIN")` và `hasAuthority("ROLE_ADMIN")` thường cùng nhắm `ROLE_ADMIN` trong default config; `hasAuthority("ADMIN")` không tương đương.
- **Đừng biến scope hoặc role client khác thành global admin.** Giữ `SCOPE_*` khi policy sử dụng, ánh xạ `ROLE_*` có allow-list và issuer/audience/client boundary.
- **Token mapping chỉ là một lớp.** JWT phải được xác thực; OAuth2 Login và Resource Server dùng converter khác nhau; multi-tenant role/ACL, revocation, proxy/method security và DB scope vẫn cần được kiểm tra.

Nếu một token sai audience, claim `roles=["ROLE_ADMIN"]`, hoặc có role `admin` chỉ trong `other-client` vẫn gọi được `/api/admin` của orders-api, thiết kế ánh xạ chưa an toàn.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT validation, `SCOPE_`, `JwtAuthenticationConverter`, custom claim/prefix và audience.
- [Spring Security 6.5 – JwtGrantedAuthoritiesConverter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): `setAuthoritiesClaimName`, `setAuthorityPrefix`, `setAuthoritiesClaimDelimiter`.
- [Spring Security 6.5 – JwtAuthenticationConverter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): `setJwtGrantedAuthoritiesConverter`, `setPrincipalClaimName`.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasRole`/`hasAuthority` và matcher semantics.
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `GrantedAuthority` và role prefix.
- [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `GrantedAuthoritiesMapper`, `OidcUserAuthority`, delegated user service.
- [Spring Security 6.5 – ReactiveJwtAuthenticationConverter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverter.html): reactive converter contract.
- [Spring Security 6.5 – ReactiveJwtGrantedAuthoritiesConverterAdapter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtGrantedAuthoritiesConverterAdapter.html): adapter giữa sync collection và reactive Flux.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` và `@PreAuthorize`.
