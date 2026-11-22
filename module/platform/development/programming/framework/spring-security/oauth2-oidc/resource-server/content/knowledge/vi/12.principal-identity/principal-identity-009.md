# Phân biệt chuẩn hóa dữ liệu với tạo thêm quyền không có căn cứ

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, ứng dụng thường chuyển những claim trong access token đã được xác minh thành **principal** và **authorities** để xử lý request. Một phép đổi tên hoặc kiểu dữ liệu trông rất đơn giản có thể vô tình làm tăng quyền truy cập. Cần phân biệt rõ:

- **Chuẩn hóa dữ liệu (normalization):** chuyển cách biểu diễn của *thông tin đã được xác minh* sang định dạng ứng dụng thống nhất, **không thay đổi ngữ nghĩa quyền**. Ví dụ: chuyển scope `orders.read` do Authorization Server cấp thành authority `SCOPE_orders.read` theo quy ước Spring Security.
- **Tạo hoặc cấp thêm quyền (privilege grant):** thêm vào `Authentication` một authority, role hoặc scope mà nguồn phân quyền tin cậy **chưa chứng minh chủ thể được sở hữu**. Ví dụ: thêm `ROLE_ADMIN` vì địa chỉ email có domain doanh nghiệp.

> **Nguyên tắc quan trọng:** chuẩn hóa không được tự mở rộng tập hành động mà principal có thể thực hiện. Nếu việc đổi dữ liệu khiến một request vượt qua kiểm tra quyền mà trước đó không có cơ sở để vượt qua, đó là một **quyết định cấp quyền**, không chỉ là đổi tên claim.

Bài học giải thích ranh giới giữa danh tính và quyền, cách Spring Security ánh xạ JWT scopes/roles, các ví dụ converter an toàn, nguy cơ privilege escalation, kiểm tra tenant và chiến lược kiểm thử.

## 1. Identity và authorization là hai câu hỏi khác nhau

~~~text
Client -- Authorization: Bearer <JWT access token> --> Resource Server
                                                       |
                                                JwtDecoder
                                     verify signature + iss/aud/exp/nbf
                                                       |
                                                JwtAuthenticationConverter
                                                  /             \
                                                 v               v
                                         Principal identity   Granted authorities
                                        (ai đang đại diện?)  (được cấp quyền gì?)
                                                  \             /
                                                   v           v
                                                   Authentication
                                                        |
                                                        v
                                              Authorization policy
                                           endpoint + tenant + object
                                                        |
                                                    allow / deny
~~~

Trong đường xử lý này, việc **xác minh token** diễn ra trước khi chuyển các claim thành quyền.

| Khái niệm | Ý nghĩa | Ví dụ | Không tự suy ra được |
|---|---|---|---|
| **Authentication** | Token được xác minh theo trust configuration | JWT có chữ ký, issuer, audience và thời hạn hợp lệ | Quyền truy cập mọi API |
| **Principal** | Chủ thể token đại diện | `sub=user-42` | Chủ thể đó là quản trị viên |
| **Display name** | Tên để hiển thị | `preferred_username=alice` | Một định danh duy nhất hoặc bất biến |
| **Scope** | Phạm vi OAuth đã được cấp cho access token | `orders.read` | Đọc toàn bộ đơn hàng của mọi người |
| **Role** | Vai trò theo hệ thống phân quyền có thẩm quyền | `orders_operator` | Vai trò ở ứng dụng khác cũng có cùng quyền |
| **Authority** | Chuỗi quyền mà Spring Security kiểm tra | `SCOPE_orders.read` | Chuỗi này được tạo ra có căn cứ |
| **Authorization** | Request cụ thể có được phép hay không | `hasAuthority(...)` + kiểm tra ownership | Token đã có mọi quyền nghiệp vụ |

**Principal không phải quyền.** Đổi `Authentication#getName()` sang email hoặc username không được làm xuất hiện role. Ngược lại, việc thêm `GrantedAuthority` vào principal có thể mở quyền API ngay cả khi phần xác minh chữ ký JWT hoàn toàn đúng.

## 2. Một claim có chữ ký vẫn cần ngữ nghĩa được tin cậy

Ví dụ access token được Authorization Server phát hành:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "preferred_username": "alice",
  "email": "alice@example.com",
  "exp": 2000000300
}
~~~

Có **ba mức tin cậy**:

1. **Chưa xác minh:** header/payload có thể đọc bằng Base64URL nhưng chỉ là dữ liệu do token tự khai báo.
2. **Đã xác minh và validate:** signature, issuer, audience, expiration và chính sách token đã đạt; Resource Server có cơ sở tin AS đã phát hành các claim.
3. **Đã xác định nguồn cấp quyền:** một claim cụ thể được hợp đồng của AS và API quy định là **nguồn có thẩm quyền để cấp scope/role/permission**.

Mức 2 **không tự động bảo đảm** mức 3 cho mọi claim. Ví dụ, Authorization Server có thể ký một `display_name` do người dùng tự sửa trong profile. Việc AS ký không biến display name đó thành hệ thống cấp quyền. Nếu user đổi tên thành “admin” rồi ứng dụng suy ra `ROLE_ADMIN`, lỗ hổng nằm ở **logic ánh xạ quyền**, không nằm ở signature verification.

### Dữ liệu nào có thể làm căn cứ quyền?

Nguồn cấp quyền hợp lệ có thể gồm:

- `scope` hoặc `scp` được AS cấp qua OAuth 2.0 theo hợp đồng access token.
- Claim role/permission được AS tạo từ **danh mục quyền do tổ chức quản lý**, dành cho chính Resource Server.
- Dịch vụ phân quyền hoặc database phía API có kiểm soát, liên kết principal với tenant/tài nguyên cụ thể.
- Chính sách nghiệp vụ có bằng chứng như ownership, membership, tình trạng bản ghi.

Không nên tự tạo quyền từ email, tên đăng nhập, display name, claim chưa xác minh, IP/User-Agent, URL query, request body hoặc group của một ứng dụng khác chưa có chính sách ánh xạ.

## 3. So sánh chuẩn hóa và tăng quyền

| Phép chuyển đổi | Bản chất | Khi nào được chấp nhận? |
|---|---|---|
| `scope="orders.read orders.write"` → `SCOPE_orders.read` và `SCOPE_orders.write` | Chuẩn hóa scope | Claim được AS cấp và định dạng đúng contract |
| `scp=["orders.read"]` → `SCOPE_orders.read` | Chuẩn hóa scope | `scp` là nguồn scope chính thức của issuer |
| `sub=user-42` → ánh xạ internal ID theo `(iss,sub)` | Chuẩn hóa danh tính | Mapping có kiểm soát, không nhập nhằng |
| `preferred_username=alice` → hiển thị “alice” | Chuẩn hóa presentation | Chỉ dùng UI, không làm khóa phân quyền |
| `scope=orders.read` → bổ sung `SCOPE_orders.write` | **Tạo thêm quyền** | Không hợp lệ nếu thiếu nguồn cấp write riêng |
| `email=admin@company.example` → `ROLE_ADMIN` | **Tạo thêm quyền** | Không có căn cứ nếu chỉ dựa vào email |
| `sub` chứa “admin” → `ROLE_ADMIN` | **Tạo thêm quyền** | Không có căn cứ |
| `groups=["staff"]` → `ROLE_SUPER_ADMIN` | Chính sách cấp quyền | Chỉ hợp lệ khi nguồn group được chứng minh và có mapping được phê duyệt |
| Thiếu roles → thêm `ROLE_USER` vô điều kiện | Chính sách cấp quyền mặc định | Phải có quyết định rõ; không phải chuẩn hóa thuần túy |
| Thiếu scopes → để tập authorities scope rỗng | Fail closed | Không bịa quyền khi nguồn không cung cấp |

Dấu hiệu nhận diện nhanh: nếu đầu vào không có quyền ghi mà đầu ra có quyền ghi, phép biến đổi **không phải chuẩn hóa tương đương**. Nó đã thêm một khả năng mới.

## 4. Principal, `sub` và tên hiển thị

Với JWT Resource Server của Spring Security, hành vi mặc định thông dụng là:

- `Authentication#getPrincipal()` trả về đối tượng `Jwt`.
- `Authentication#getName()` dùng claim `sub` nếu có.
- Scope từ `scope` hoặc `scp` được chuyển thành các authority tiền tố `SCOPE_`.

Ví dụ:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "preferred_username": "alice",
  "scope": "orders.read"
}
~~~

Sau xác thực theo cấu hình phổ biến:

~~~text
Authentication.name        = user-42
Authentication.principal   = Jwt(...)
Authentication.authorities = [SCOPE_orders.read]
~~~

`preferred_username` giúp ứng dụng hiển thị “alice” nhưng không cần thay danh tính canonical.

### 4.1. Cặp `(iss, sub)` mới là một định danh phù hợp đa issuer

Giả sử hai IdP cùng phát hành `sub=user-42`:

~~~text
https://idp-a.example.com  +  user-42  -> người A
https://idp-b.example.com  +  user-42  -> người B
~~~

Nếu hệ thống chấp nhận nhiều issuer, chỉ lưu `sub` có thể hợp nhất nhầm hai người. Một thiết kế identity mapping có kiểm soát nên dùng cặp **issuer + subject**, và có thể thêm tenant/realm theo mô hình dữ liệu.

Không hợp nhất user chỉ vì hai token có cùng `email`, `name` hoặc `preferred_username`. Những thuộc tính đó có thể thay đổi hoặc không được đảm bảo duy nhất trong các miền danh tính.

### 4.2. Email và username không phải role

Đoạn code sau sai:

~~~java
// SAI: email domain không chứng minh quyền quản trị
if (email.endsWith("@company.example")) {
    authorities.add(
        new SimpleGrantedAuthority("ROLE_ADMIN")
    );
}
~~~

Dù email nằm trong JWT đã ký, AS không nhất thiết cấp email đó từ một **quy trình cấp role admin**. Claim `email_verified=true` (khi có) chỉ liên quan trạng thái xác minh email theo contract issuer, không tự biểu thị quyền điều hành hệ thống.

### 4.3. Client credentials không nhất thiết có human user

Access token từ OAuth 2.0 `client_credentials` thường đại diện cho ứng dụng hoặc workload, không phải người dùng tương tác. Khi đó `sub`, `client_id` và các claim khác cần được diễn giải theo token profile.

Không suy luận:

~~~text
Có sub -> là user -> thêm ROLE_USER -> được gọi mọi endpoint user
~~~

Một machine client phải được phân quyền theo client identity, scope và chính sách nghiệp vụ riêng. Không gán role của con người chỉ vì token có `sub`.

## 5. Authority và quy ước `SCOPE_`, `ROLE_`

Spring Security biểu diễn quyền bằng `GrantedAuthority`, ví dụ:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDERS_READER
ROLE_ORDERS_OPERATOR
~~~

Các tên trên là chuỗi kỹ thuật. Quyền xuất hiện trong `Authentication` phải được dẫn xuất từ một **entitlement đã được cấp** hoặc nguồn authorization đáng tin.

### `hasAuthority` khác `hasRole`

Trong cấu hình mặc định phổ biến:

~~~java
.hasAuthority("SCOPE_orders.read")
.hasRole("ADMIN")
~~~

`hasAuthority` kiểm tra chính xác chuỗi; `hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN` theo role prefix được cấu hình.

Do đó, nếu developer thay prefix của scopes thành `ROLE_`, một scope có tên `admin` có thể va chạm với rule role của ứng dụng. Spring Security cho phép đổi prefix nhưng **điều đó có thể làm thay đổi ngữ nghĩa phân quyền**, không chỉ format hiển thị.

Ví dụ endpoint:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Scope đọc không tự cấp quyền ghi. Càng không có căn cứ để chuyển `orders.read` thành `ROLE_ADMIN`.

## 6. Ánh xạ scope chuẩn bằng Spring Security

JWT đã xác minh chứa:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Spring Security mặc định thường ánh xạ các scope này thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Đây là phép **chuẩn hóa dữ liệu** khi claim thực sự chứa scopes mà AS cấp. Prefix `SCOPE_` không có nghĩa AS đã phát hành thêm hai scope khác.

Một số issuer dùng:

~~~json
{
  "scp": ["orders.read", "orders.write"]
}
~~~

`JwtGrantedAuthoritiesConverter` hỗ trợ các claim scope thông dụng và có API tùy chỉnh tên claim, delimiter, prefix. Khi issuer dùng một contract cụ thể, có thể chỉ định rõ nguồn.

### 6.1. Converter chỉ đọc claim `scp`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class PrincipalMappingConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter grants =
            new JwtGrantedAuthoritiesConverter();

        // AS của ví dụ quy định scp là danh sách scope chính thức.
        grants.setAuthoritiesClaimName("scp");
        grants.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(grants);
        converter.setPrincipalClaimName("sub");
        return converter;
    }
}
~~~

Filter chain sử dụng bean này:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter)))
            .build();
    }
}
~~~

Ví dụ giả định ứng dụng đã có `spring-boot-starter-oauth2-resource-server` và một `JwtDecoder` tin cậy, chẳng hạn được Spring Boot cấu hình qua `issuer-uri`. Converter **không tự xác minh JWT**; nó chạy trong luồng xác thực do Spring Security quản lý.

Nếu issuer đã dùng `scope` hoặc `scp` chuẩn và converter mặc định phù hợp, không nhất thiết viết converter tùy biến. Tự viết logic cấp quyền khi không cần thiết làm tăng nguy cơ sai chính sách.

## 7. Đổi principal name khác với cấp quyền

Spring Security hỗ trợ:

~~~java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setPrincipalClaimName("preferred_username");
~~~

Đây là API hợp lệ nhưng cần hiểu hệ quả: `Authentication#getName()` từ đó sẽ dùng claim `preferred_username`. Nếu service sử dụng tên này làm khóa sở hữu đơn hàng hoặc mapping user nội bộ, một username bị đổi hoặc trùng có thể gây lỗi danh tính.

Thiết kế tốt thường tách:

- **Canonical ID:** issuer + subject, hoặc internal user ID được ánh xạ đáng tin.
- **Display name:** `name`, `preferred_username` hoặc nickname.
- **Authorities:** scope, role và permission đến từ nguồn phân quyền có thẩm quyền.

Ví dụ controller chỉ thay **display name** mà không sửa authorities:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();

        String displayName =
            jwt.getClaimAsString("preferred_username");

        if (displayName == null || displayName.isBlank()) {
            displayName = subject;
        }

        return Map.of(
            "subject", subject,
            "displayName", displayName
        );
    }
}
~~~

Ví dụ giả định route được bảo vệ và AS luôn cấp `sub` không null. Trong ứng dụng thật, không trả thông tin cá nhân không cần thiết và không công khai internal identity ID nếu chính sách bảo mật không cho phép.

Fallback ở đây **chỉ phục vụ hiển thị**. Không có câu lệnh nào thêm `ROLE_USER` hoặc `ROLE_ADMIN` khi `preferred_username` thiếu.

## 8. Mapping role: có thể hợp lệ nhưng không phải việc đổi chuỗi tùy ý

Một AS có thể phát hành:

~~~json
{
  "app_roles": ["orders_reader", "orders_operator"]
}
~~~

Nếu tổ chức đã có hợp đồng rằng `app_roles` được cấp từ hệ thống role đáng tin **cho riêng orders-api**, có thể định nghĩa ánh xạ:

~~~text
app_roles/orders_reader    -> ROLE_ORDERS_READER
app_roles/orders_operator  -> ROLE_ORDERS_OPERATOR
~~~

Nhưng phải xác nhận:

1. Token đúng issuer, audience, token type và được xác minh mật mã.
2. Claim `app_roles` do nguồn quản lý quyền có thẩm quyền tạo, không phải profile field người dùng tùy ý sửa.
3. Role dành cho **ứng dụng hiện tại**, không phải một ứng dụng khác cùng IdP.
4. Mapping được phê duyệt và có allowlist tường minh.
5. Role được giới hạn theo tenant/resource nếu contract yêu cầu.
6. Có chính sách lifecycle, thu hồi và xử lý quyền stale.

Nếu không có các điều kiện đó, chuyển group/role tùy ý thành `ROLE_*` có thể gây **privilege escalation**.

### 8.1. Converter role với allowlist tường minh

Đoạn sau minh họa một **chính sách cấp role có căn cứ**, chỉ sử dụng khi issuer đã được phê duyệt làm nguồn role cho ứng dụng:

~~~java
package com.example.orders.security;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class ApplicationRoleConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter result =
            new JwtAuthenticationConverter();

        result.setJwtGrantedAuthoritiesConverter(jwt -> {
            Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(scopes.convert(jwt));

            // app_roles phải là claim role có thẩm quyền theo contract.
            List<String> roles = jwt.getClaimAsStringList("app_roles");
            if (roles == null) {
                return authorities;
            }

            for (String role : roles) {
                switch (role) {
                    case "orders_reader" -> authorities.add(
                        new SimpleGrantedAuthority("ROLE_ORDERS_READER"));
                    case "orders_operator" -> authorities.add(
                        new SimpleGrantedAuthority("ROLE_ORDERS_OPERATOR"));
                    default -> {
                        // Không tự chuyển role lạ thành quyền của API.
                    }
                }
            }
            return authorities;
        });

        return result;
    }
}
~~~

Ví dụ dùng Java 17+ và cần được nối với filter chain/JWT decoder theo phần trước. **Nhánh chuyển role là quyết định ủy quyền đã được duyệt**, không phải phần mềm tự suy đoán mọi role string.

Nếu API không có role claim đáng tin, bỏ toàn bộ phần chuyển role. Chỉ giữ những scope, quyền nghiệp vụ có nguồn và contract rõ ràng.

### 8.2. Lỗi phổ biến: chuyển mọi group thành ROLE_

~~~java
// SAI nếu groups không phải nguồn cấp quyền cho API này.
for (String group : jwt.getClaimAsStringList("groups")) {
    authorities.add(new SimpleGrantedAuthority(
        "ROLE_" + group.toUpperCase()
    ));
}
~~~

`groups=["ADMIN"]` có thể là nhóm của ứng dụng khác hoặc chỉ là phân loại hiển thị. Mặc nhiên tạo `ROLE_ADMIN` của Resource Server là vượt qua ranh giới trust.

**Cùng một từ “admin” trong hai hệ thống không có nghĩa hai hệ thống cấp cùng quyền.** Nên tách namespace role, contract và issuer mapping.

## 9. Không dùng các nguồn sau để suy diễn quyền

### 9.1. Email, tên đăng nhập và thuộc tính hồ sơ

Những quy tắc như sau là nguy hiểm khi dùng trực tiếp làm role:

~~~text
email endsWith "@company.example" -> ROLE_ADMIN
preferred_username startsWith "admin" -> ROLE_ADMIN
email_verified == true -> ROLE_SUPER_USER
display_name contains "manager" -> ROLE_MANAGER
~~~

Chúng có thể tạo quyền khi một thuộc tính vốn chỉ dùng cho nhận dạng/hiển thị bị đổi. Nếu doanh nghiệp muốn triển khai vai trò “nhân viên được xem báo cáo”, cần nguồn membership/entitlement có thẩm quyền và giới hạn quyền cụ thể, không đồng nhất với email domain.

### 9.2. ID token thay access token

Trong OpenID Connect, **ID token** chủ yếu dành cho OIDC Client; **access token** dành cho Resource Server. Không lấy group trong ID token rồi coi nó là quyền truy cập API nếu access token không có audience và contract phù hợp.

Dù ID token có chữ ký hợp lệ, nó có thể có `aud` là client ID, không phải `orders-api`. Resource Server phải phân biệt loại token và áp dụng audience/token profile validation.

### 9.3. URL và request body

Không lấy role từ query hoặc body:

~~~http
GET /api/orders?role=ADMIN HTTP/1.1
Authorization: Bearer <access-token>
~~~

Client kiểm soát input này. Nó có thể phục vụ lựa chọn tài nguyên, nhưng không được tự biến thành authority.

### 9.4. Tenant ID

Token chứa:

~~~json
{
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

không đủ để kết luận subject có toàn quyền trong tenant đó. `tenant_id` thường là **bối cảnh**, còn quyền cụ thể cần kiểm tra membership, role và ownership.

## 10. Khi thiếu quyền, phải fail closed thay vì “bù cho tiện”

Một lỗi tích hợp rất dễ gặp:

~~~java
// SAI: ứng dụng tự bù scope khi người dùng gặp 403.
Set<String> scopes = parseScopes(jwt);

if (!scopes.contains("orders.write")) {
    scopes.add("orders.write");
}
~~~

Hoặc:

~~~java
// SAI: mọi request đã xác thực được tự nâng thành operator.
if (authentication.isAuthenticated()) {
    authorities.add(
        new SimpleGrantedAuthority("ROLE_ORDERS_OPERATOR")
    );
}
~~~

Những đoạn này có thể làm tính năng “hoạt động”, nhưng đã bỏ qua việc AS hay hệ thống cấp quyền có thực sự cho phép write/operator hay không.

Cách xử lý đúng khi gặp `403`:

- Client có được yêu cầu scope cần thiết trong OAuth authorization flow không?
- Authorization Server có chấp thuận cấp scope đó cho client và subject không?
- Token có đúng `aud` của Resource Server không?
- Scope/role claim có được phát hành đúng format và ngữ nghĩa không?
- Converter đang đọc claim nào, tiền tố nào?
- Rule `hasAuthority(...)` yêu cầu đúng quyền đã cấp không?
- Business service còn giới hạn theo owner/tenant không?

Nếu token thực sự thiếu quyền, **không thể coi việc tự thêm quyền vào converter là normalization**. Nếu token đã có quyền nhưng converter đọc sai kiểu dữ liệu, sửa converter theo hợp đồng là hợp lý, miễn tập quyền sau chuyển đổi không bị nới rộng.

## 11. Phép ánh xạ tương đương và phép mở rộng quyền

Giả sử nguồn quyền tin cậy chỉ có:

~~~text
scopes = { orders.read }
~~~

Ánh xạ tương đương:

~~~text
orders.read -> SCOPE_orders.read
~~~

Ánh xạ mở rộng thiếu căn cứ:

~~~text
orders.read -> SCOPE_orders.read + SCOPE_orders.write
orders.read -> ROLE_ADMIN
orders.read -> ROLE_ALL_TENANTS
~~~

### 11.1. Đổi tên giữa hai hệ thống không mặc nhiên tương đương

AS A dùng:

~~~json
{"permissions": ["read:orders"]}
~~~

AS B dùng:

~~~json
{"scope": "orders.read"}
~~~

Hai chuỗi có thể mang cùng ý nghĩa, nhưng chỉ được gộp về `SCOPE_orders.read` nếu hợp đồng thống nhất về:

- Đối tượng dữ liệu có thể đọc.
- Phạm vi tenant/tổ chức.
- Những điều kiện client/subject phải đáp ứng.
- Ngữ nghĩa “read” (đọc bản ghi của mình hay của mọi người).
- Loại token và audience.

Nếu `read:orders` của AS A có nghĩa “đọc mọi order”, còn `orders.read` của AS B có nghĩa “chỉ đọc order của subject”, gộp tên có thể che giấu một khác biệt về quyền. **Chuyển đổi một-một về chuỗi không đồng nghĩa tương đương về chính sách.**

### 11.2. Chỉ giữ tập con quyền có thể phù hợp

Một Resource Server chỉ quản lý đơn hàng có thể bỏ qua những scope không liên quan:

~~~text
Token scopes:
  orders.read, profile.read, billing.read

Authorities ứng dụng thực sự quan tâm:
  SCOPE_orders.read
~~~

Việc chỉ sử dụng scope cần thiết phù hợp nguyên tắc quyền tối thiểu. Trái lại, tự suy ra `SCOPE_orders.write` từ `billing.read` là một quyết định cấp thêm quyền không được phép nếu thiếu căn cứ.

## 12. Namespace và role hierarchy

Tên quyền chung như:

~~~text
ROLE_ADMIN
ROLE_USER
ROLE_OPERATOR
~~~

dễ bị lẫn khi nhiều dịch vụ hoặc issuer có các role khác nhau. Trong một hệ thống lớn, có thể dùng namespace cụ thể:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDERS_READER
ROLE_ORDERS_OPERATOR
~~~

Tuy nhiên, namespace chỉ giúp giảm va chạm tên, **không thay thế nguồn quyền đáng tin**.

Một role hierarchy kiểu:

~~~text
ROLE_ORDERS_ADMIN > ROLE_ORDERS_OPERATOR > ROLE_ORDERS_READER
~~~

có thể hợp lệ nếu được quản trị rõ ràng. Nhưng đây là **policy suy ra quyền cấp thấp từ role cấp cao**, không chỉ chuẩn hóa tên. Không tự tạo hierarchy từ thứ tự chữ cái hoặc tên nhóm người dùng.

## 13. Claim thiếu, sai kiểu hoặc mâu thuẫn

Một converter an toàn cần xác định hành vi khi dữ liệu không đạt contract.

| Đầu vào | Hành vi phù hợp |
|---|---|
| Không có `scope` hoặc `scp` | Không tự tạo OAuth scope |
| `scope=""` | Không tạo scope authority |
| `scp=["orders.read"]` | Đổi đúng quyền đã có |
| `scp` là object thay vì list/string hợp lệ | Từ chối hoặc không cấp quyền theo policy; không đoán |
| `app_roles=["unknown"]` | Không sinh role có quyền từ tên lạ |
| Claim role do người dùng tự sửa trong profile | Không dùng làm nguồn phân quyền |
| Thiếu `sub` với token yêu cầu user subject | Xử lý theo contract, không tạo user admin |
| Không có internal identity mapping | Không gán quyền mặc định cao |
| Issuer/audience sai | Từ chối tại authentication boundary |
| `groups` có kiểu không mong đợi | Không rơi vào fallback toàn quyền |

Tùy hợp đồng, ứng dụng có thể từ chối token vì thiếu claim bắt buộc hoặc cho request đi tiếp với authorities rỗng để rule từ chối. Cả hai cần **fail closed** đối với quyền không có căn cứ.

### `scope` và `scp` cùng xuất hiện

Ví dụ token:

~~~json
{
  "scope": "orders.read",
  "scp": ["orders.write"]
}
~~~

Không tự động **union** hai tập chỉ vì chúng đều có tên liên quan scope. Hãy xác định claim nào có thẩm quyền trong profile của issuer. Nếu một claim là dữ liệu tương thích cũ, hợp nhất tùy tiện có thể tạo quyền vượt ngoài mong đợi.

## 14. Quyền trên tenant và tài nguyên

Giả sử JWT hợp lệ có:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

Đối với `GET /api/tenants/tenant-a/orders/1001`, ứng dụng có thể cần kiểm tra:

1. Token có chữ ký, issuer, audience và thời hạn hợp lệ.
2. Token có `orders.read`.
3. User/client có membership/entitlement phù hợp với `tenant-a`.
4. Order `1001` thật sự thuộc tenant A.
5. Principal có quyền trên order cụ thể theo policy.

Một converter chỉ chuyển `tenant_id` thành `ROLE_TENANT_ADMIN` là nguy hiểm. **Tenant context không tự chứng minh quyền quản trị tenant**.

Đặc biệt, dù JWT hợp lệ và có `SCOPE_orders.read`, API vẫn có thể mắc lỗi BOLA/IDOR nếu chỉ nhận order ID từ URL rồi trả mọi bản ghi mà không kiểm tra ownership.

## 15. Có thể cấp quyền từ database, nhưng phải có nguồn có thẩm quyền

Không phải mọi permission đều nằm trong JWT. Resource Server có thể xác minh JWT, ánh xạ `(iss,sub)` sang internal user ID rồi gọi một authorization service hoặc database:

~~~text
Verified JWT (iss, sub)
          |
          v
Trusted identity mapping
          |
          v
Authorization service / policy database
          |
          +-- membership
          +-- order permissions
          +-- tenant roles
          |
          v
Request allow / deny
~~~

Đây **có thể là thiết kế hợp lệ**, không phải tạo quyền bừa bãi, nếu database/service là nguồn quyền chính thức, dữ liệu identity mapping không nhập nhằng, quyền được kiểm tra đúng tài nguyên và lỗi nguồn quyền được xử lý an toàn.

Ngược lại, một database nhận `role=ADMIN` do client gửi rồi ghi thẳng thành entitlement không phải nguồn đáng tin chỉ vì nó ở phía server.

### Vấn đề stale roles trong JWT

Access token tự chứa role tại thời điểm cấp có thể chưa phản ánh một lần thu hồi quyền sau đó. Ví dụ:

1. 10:00: AS phát JWT có `app_roles=["orders_operator"]`.
2. 10:02: admin thu hồi role.
3. 10:03: RS chỉ verify JWT cục bộ vẫn thấy role cũ chưa hết hạn.

Đây là vấn đề vòng đời quyền, token TTL và revocation, **không phải lỗi normalization**. Nếu cần quyền cập nhật tức thời, cân nhắc introspection, denylist, TTL ngắn hoặc kiểm tra quyền hiện tại từ nguồn có thẩm quyền.

## 16. Cẩn trọng khi dùng claim set converter

Spring Security hỗ trợ tùy chỉnh cách xử lý claim set, ví dụ `MappedJwtClaimSetConverter`. Nó hữu ích để chuyển kiểu dữ liệu hoặc chuẩn hóa representation theo contract của issuer.

Nhưng **không dùng claim normalization để sửa những claim vốn phải bị từ chối**:

~~~java
// SAI VỀ Ý TƯỞNG: ghi đè issuer sai thành issuer mong đợi
claims.put("iss", "https://expected-issuer.example");

// SAI VỀ Ý TƯỞNG: tự thêm audience để qua validation
claims.putIfAbsent("aud", List.of("orders-api"));

// SAI VỀ Ý TƯỞNG: tự thêm scope để endpoint hoạt động
claims.putIfAbsent("scope", "orders.read");
~~~

`iss`, `aud`, `exp`, `nbf`, scope và token type là những yếu tố ảnh hưởng trust/authorization. Nếu token có giá trị không hợp lệ, Resource Server cần từ chối, không “làm đẹp” dữ liệu để vượt qua policy.

Chuẩn hóa hợp lý có thể bao gồm chuyển kiểu claim theo contract, định dạng display name hoặc ánh xạ canonical identity một-một sau khi token được xác minh.

## 17. Một ví dụ privilege escalation hoàn toàn do converter

JWT được ký hợp lệ:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "preferred_username": "admin-support"
}
~~~

Converter A chỉ ánh xạ scope:

~~~text
SCOPE_orders.read
~~~

Converter B tự suy diễn:

~~~text
SCOPE_orders.read
ROLE_ADMIN
~~~

Hai request mang **cùng token và cùng chữ ký**. Nhưng B đã tăng quyền chỉ do username có từ “admin”. Khi API dùng `hasRole("ADMIN")`, B có thể cho phép hành động mà AS không cấp và policy nghiệp vụ chưa chứng minh.

Đó là **privilege escalation tại tầng ánh xạ authorities**, dù crypto JWT verification đúng hoàn toàn.

### Câu hỏi cần trả lời khi review converter

Đối với từng dòng thêm `GrantedAuthority`:

- Claim hoặc hệ thống nào **chứng minh** quyền?
- Claim có được phát hành từ nguồn role/permission có thẩm quyền không?
- Token đúng issuer, audience và token type không?
- Quyền đầu ra có tương đương rõ với entitlement nguồn không?
- Mapping có vượt qua ranh giới ứng dụng hoặc tenant không?
- Claim thiếu/sai/lạ có dẫn tới quyền mặc định cao hơn không?
- Ai quản lý bản đồ quyền và thay đổi qua quy trình nào?
- Có test bảo đảm converter **không phát sinh admin/write** từ identity strings không?

Không trả lời được những câu hỏi này là dấu hiệu cần từ chối hoặc thiết kế lại mapping.

## 18. JWT và opaque token đều cần nguyên tắc này

Với JWT, Spring Security thường sử dụng `JwtAuthenticationConverter` sau khi `JwtDecoder` xác minh token. Với opaque token, Resource Server thường dựa vào introspection và nhận một `OAuth2AuthenticatedPrincipal` cùng attributes/authorities.

Điểm chung:

- Chỉ dùng token có kết quả xác thực hợp lệ.
- Không cấp quyền dựa vào string token hoặc thuộc tính chưa có nguồn tin cậy.
- Phân biệt identity claims với authorization claims.
- Ánh xạ theo contract của issuer và hệ thống phân quyền.
- Tiếp tục kiểm tra tenant và object ownership.

Không cast mọi principal thành `Jwt` nếu API hỗ trợ opaque token. Cần dùng converter/adapter tương ứng với cơ chế token thực tế.

## 19. Kiểm thử normalization mà không vô tình tăng quyền

Unit test cần chứng minh **quyền được ánh xạ đúng** và **quyền không có căn cứ không xuất hiện**.

### 19.1. Ví dụ test converter chỉ đọc `scp`

~~~java
package com.example.orders.security;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AuthoritiesMappingTest {

    @Test
    void normalizesExistingScopeButDoesNotInferAdminFromUsername() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only")
            .header("alg", "RS256")
            .claim("sub", "user-42")
            .claim("scp", List.of("orders.read"))
            .claim("preferred_username", "admin-support")
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();

        converter.setAuthoritiesClaimName("scp");
        converter.setAuthorityPrefix("SCOPE_");

        Set<String> names = converter.convert(jwt).stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertEquals(Set.of("SCOPE_orders.read"), names);
    }
}
~~~

Test này khẳng định username có từ “admin” không tạo `ROLE_ADMIN`. `Jwt` trong unit test chỉ là đối tượng giả lập; **không chứng minh chữ ký JWS đã được xác minh**. Cần integration test dùng test signing key và decoder thật để kiểm tra cả issuer/audience/crypto.

### 19.2. Các test âm tính quan trọng

| Dữ liệu đầu vào | Kỳ vọng |
|---|---|
| Chỉ có `scope=orders.read` | Không có quyền ghi hoặc admin |
| Không có scope | Không phát sinh scope mặc định |
| Username chứa “admin” | Không có `ROLE_ADMIN` |
| Email domain doanh nghiệp | Không tự cấp operator/admin |
| Role claim chứa giá trị không nhận diện | Không tự tạo role nội bộ |
| Role claim sai kiểu | Fail closed theo policy |
| JWT đúng chữ ký nhưng `aud` sai | Từ chối trước khi có authorities được tin |
| JWT từ issuer khác | Không dùng role mapping của issuer hiện tại |
| Machine token | Không tự gán role human user |
| User tenant A truy cập order tenant B | Từ chối bởi object/tenant policy |
| Scope read gọi endpoint write | 403 hoặc kết quả từ chối phù hợp |

Tiện ích `jwt()` của Spring Security Test có thể mô phỏng principal hoặc authorities, nhưng nếu test tự gắn authorities, nó có thể **bỏ qua converter production**. Dùng test converter riêng và integration test đường xác thực khi cần.

## 20. 401, 403 và lỗi ánh xạ authority

| Trường hợp | Kết quả điển hình | Nhóm nguyên nhân |
|---|---|---|
| Thiếu bearer token | `401` | Chưa xác thực |
| Chữ ký không hợp lệ | `401` | JWT verification thất bại |
| Issuer, audience hoặc thời gian sai | `401` | JWT validation thất bại |
| Token hợp lệ nhưng thiếu `orders.write` khi POST | `403` | Thiếu quyền endpoint |
| Token có scope nhưng converter đọc sai claim | `403` | Lỗi mapping/contract |
| User không sở hữu bản ghi | `403` hoặc `404` theo policy | Object authorization |
| Username chứa admin nhưng không có admin quyền | `403` với admin endpoint | Hành vi mong đợi |
| Converter tự thêm admin từ email | Có nguy cơ cho phép sai | Privilege escalation |

Đừng “sửa 403” bằng cách thêm `SCOPE_orders.write` hoặc `ROLE_ADMIN` vô điều kiện. Phải xác định quyền có thực sự được cấp, hay converter chưa hiểu đúng representation của quyền đã có.

## 21. Một thiết kế Resource Server tối thiểu và an toàn

Giả sử `orders-api` tin issuer cố định, chấp nhận access token dành cho `orders-api` và sử dụng scope đã được AS cấp.

`build.gradle`:

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
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

`SecurityConfig.java`:

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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Với scope chuẩn, Spring Security tự ánh xạ thành `SCOPE_*` mà không cần custom role mapping.

Tầng service phải kiểm tra ownership/tenant:

~~~java
// Pseudocode cho chính sách ứng dụng, không phải API Spring có sẵn.
Order order = orderRepository.findById(orderId)
    .orElseThrow(NotFoundException::new);

InternalUser user = identityDirectory.resolve(
    jwt.getIssuer().toString(),
    jwt.getSubject()
);

if (!order.ownerId().equals(user.id())) {
    throw new AccessDeniedException("Not permitted");
}

return order;
~~~

`Order`, `InternalUser`, `identityDirectory` và `NotFoundException` là những thành phần domain minh họa. Hành vi thực tế cần thêm tenant, status hoặc các policy khác tùy nghiệp vụ.

Mô hình này phân biệt rõ:

1. **JWT verification:** token được phát hành bởi nguồn tin cậy và dành cho API.
2. **Authority normalization:** scope đã được cấp được biểu diễn theo quy ước Spring.
3. **Canonical identity:** user được nhận diện có kiểm soát.
4. **Business authorization:** resource/tenant được kiểm tra đúng.
5. **Không suy diễn thêm quyền:** tên, email, group tùy ý không tạo role admin.

## 22. Những hiểu nhầm thường gặp

**“Mọi claim trong JWT đã ký đều có thể trở thành role.”** Không. Claim phải đến từ nguồn có thẩm quyền phân quyền và có contract rõ.

**“Ánh xạ `orders.read` sang `SCOPE_orders.read` là tạo thêm quyền.”** Không, nếu chỉ chuyển đúng scope được cấp theo quy ước Spring.

**“Email thuộc công ty đồng nghĩa quyền admin.”** Sai. Identity metadata không thay thế entitlement.

**“`preferred_username` chứa admin thì nên map thành `ROLE_ADMIN`.”** Sai. Username không chứng minh vai trò.

**“`hasRole("ADMIN")` và `hasAuthority("SCOPE_admin")` giống nhau.”** Không. Chúng kiểm tra những tên authority khác nhau.

**“Group name trùng role name thì có thể map tự động.”** Không. Cần contract về nguồn, ứng dụng, tenant và ngữ nghĩa role.

**“Thiếu write scope thì converter tự thêm cho UX tốt hơn.”** Sai. Đó là privilege escalation.

**“Có `sub` nghĩa là human user.”** Không. Machine access token cũng có subject/client identity theo contract.

**“`sub` là duy nhất trên mọi issuer.”** Không. Với nhiều issuer, cần nhận dạng theo cặp `(iss, sub)` hoặc identity mapping đáng tin.

**“Có `tenant_id` là quyền quản trị tenant.”** Không. Tenant context và role/membership là các thông tin khác nhau.

**“MockMvc jwt() tự chứng minh converter và signature production đúng.”** Không nhất thiết. Mock JWT có thể bỏ qua chữ ký và tự gắn authorities trong test.

## 23. Câu hỏi tự kiểm tra

**1.** JWT có `scope=orders.read`. Converter tạo `SCOPE_orders.read`. Có phải cấp thêm quyền không?

> Không, nếu `scope` là nguồn quyền đã được AS cấp và ánh xạ giữ nguyên ngữ nghĩa.

**2.** Token có `preferred_username=admin_helpdesk` nhưng không có admin entitlement. Có được thêm `ROLE_ADMIN` không?

> Không. Username chỉ là thông tin danh tính/hiển thị.

**3.** Token có `app_roles=["orders_operator"]`. Có luôn được map thành `ROLE_ORDERS_OPERATOR` không?

> Chỉ khi AS và API đã thống nhất claim này có thẩm quyền, dành cho ứng dụng hiện tại, và có mapping được phê duyệt. Đây là quyết định cấp quyền.

**4.** Hai issuer khác nhau cùng cấp `sub=user-42`. Có nên coi là một user không?

> Không mặc định. Cần identity mapping theo issuer và subject.

**5.** Vì sao không nên sửa lỗi 403 bằng cách thêm quyền vào converter?

> Vì 403 có thể phản ánh AS chưa cấp quyền hoặc business policy từ chối. Tự thêm quyền có thể bỏ qua chính sách bảo mật.

**6.** Nếu application role đã bị thu hồi nhưng JWT còn role cũ, nguyên nhân thuộc đâu?

> Vòng đời token/quyền stale và cơ chế revocation, không phải normalization.

**7.** Quyền lấy từ database có luôn là “tạo quyền vô căn cứ” không?

> Không. Nếu database là nguồn authorization có thẩm quyền, kiểm soát được identity và tenant, đó có thể là chính sách cấp quyền hợp lệ.

**8.** Khi claim roles sai kiểu hoặc vắng mặt, converter nên làm gì?

> Không tự tạo quyền cao hơn; xử lý fail closed theo hợp đồng token.

## 24. Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): ánh xạ `scope`/`scp`, principal mặc định và tùy chỉnh `JwtAuthenticationConverter`.
- [Spring Security — JwtAuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): principal claim name và authorities converter.
- [Spring Security — JwtGrantedAuthoritiesConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): claim name, prefix và chuẩn hóa scopes.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `GrantedAuthority`, `hasRole` và quyền truy cập.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): bảo vệ phương thức theo quyền.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud` và claim semantics.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token profile, audience, scope và client context.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): các ranh giới tin cậy khi xác minh JWT.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, scope và authorization model.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): thuộc tính được introspection cho opaque token.

Điểm cần bảo vệ trong Spring Security không chỉ là **danh tính đã xác minh**, mà còn là **tính chính đáng của từng quyền trong `Authentication`**. Chuẩn hóa dữ liệu phục vụ tính nhất quán; còn quyền truy cập phải đến từ scope/role do nguồn có thẩm quyền cấp hoặc chính sách nghiệp vụ đáng tin, không từ suy đoán về tên, email hay hình dạng claim.
