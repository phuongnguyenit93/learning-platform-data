# 13.6. GrantedAuthoritiesMapper và ánh xạ quyền tập trung

## 1. Bài toán: một người dùng đăng nhập được nhưng được phép làm gì?

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client** chạy trên Servlet, đăng nhập thành công và được phép thực hiện một thao tác nghiệp vụ là **hai quyết định khác nhau**.

Ví dụ, cổng thông tin doanh nghiệp cho phép nhân viên đăng nhập bằng OpenID Connect (OIDC). Nhà cung cấp danh tính (*OpenID Provider*, OP) trả ID Token có subject `employee-123` và claim `groups`:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "employee-123",
  "aud": "portal-web",
  "groups": ["portal-readers", "portal-report-editors"]
}
~~~

Ứng dụng muốn sử dụng quy tắc riêng:

- Thành viên `portal-readers` được cấp authority `ROLE_READER`.
- Thành viên `portal-report-editors` được cấp authority `ROLE_REPORT_EDITOR`.
- Chỉ nhóm `portal-admins` mới có `ROLE_ADMIN`.
- Claim không nằm trong danh sách được duyệt sẽ **không tự động** trở thành quyền trong ứng dụng.

Nếu controller tự đọc `groups` và kiểm tra chuỗi ở mỗi request, quy tắc phân quyền sẽ bị phân tán, khó kiểm soát và dễ không nhất quán giữa các endpoint. Spring Security cung cấp **`GrantedAuthoritiesMapper`** để ánh xạ những `GrantedAuthority` mà quá trình đăng nhập tạo ra thành tập authority nhất quán cho **`Authentication`**.

Mục tiêu của bài này là hiểu:

1. `GrantedAuthoritiesMapper` là gì và chạy ở đâu trong OAuth2/OIDC Login.
2. Phân biệt principal, claim, group, role và authority.
3. Tạo mapper tập trung, chỉ ánh xạ từ nguồn dữ liệu tin cậy.
4. Gắn mapper vào `oauth2Login()` của Servlet và áp dụng quyền với HTTP endpoint hoặc method security.
5. Biết khi nào mapper **không đủ**, đặc biệt khi cần Access Token để gọi API lấy nhóm/quyền.
6. Tránh lỗi cấp quyền quá rộng, lệch issuer, không cập nhật quyền theo thời gian hoặc ánh xạ sai prefix.

## 2. Phân biệt Authentication, principal, claim và GrantedAuthority

Spring Security đặt kết quả xác thực vào một `Authentication`, thường được truy xuất từ `SecurityContext`. Với OAuth2/OIDC Login, principal có thể là `OAuth2User` hoặc `OidcUser`. Principal mô tả danh tính và những thuộc tính đã nhận; các authorities trên `Authentication` phục vụ quyết định phân quyền.

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Principal** | `OidcUser` có `sub=employee-123` | Người dùng đã được nhận diện sau quá trình xác thực |
| **OIDC claim** | `groups: ["portal-admins"]` | Dữ liệu được provider cung cấp trong ID Token hoặc UserInfo |
| **Provider group/role** | `portal-admins`, `finance-team` | Cách provider phân nhóm, **chưa đương nhiên** là quyền của ứng dụng |
| **GrantedAuthority** | `ROLE_ADMIN`, `ROLE_READER` | Tên authority mà Spring Security có thể dùng để phân quyền |
| **Authentication authorities** | Tập `GrantedAuthority` đã được mapper xử lý | Được các authorization rules như `hasRole` và `hasAuthority` kiểm tra |
| **Application policy** | `/admin/**` cần `ROLE_ADMIN` | Quy tắc bảo vệ tài nguyên/hoạt động nghiệp vụ |

Một principal có thể chứa claim `groups` nhưng không được cấp `ROLE_ADMIN` nếu chính sách ánh xạ không cho phép. Ngược lại, một người dùng có `ROLE_ADMIN` trong phiên hiện tại không nhất thiết còn thuộc nhóm admin ở provider sau nhiều giờ nếu vai trò vừa bị thu hồi.

### 2.1. Authority string và quy ước `ROLE_`

`GrantedAuthority` là giao diện cung cấp tên authority:

~~~java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority role = new SimpleGrantedAuthority("ROLE_ADMIN");
GrantedAuthority permission =
    new SimpleGrantedAuthority("report:export");
~~~

Spring Security thường hiểu:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

là yêu cầu authority **`ROLE_ADMIN`** (mặc định có prefix `ROLE_`).

Trong khi:

~~~java
.requestMatchers("/admin/**").hasAuthority("ROLE_ADMIN")
~~~

kiểm tra chuỗi authority chính xác. Với authority không dùng tiền tố role:

~~~java
.requestMatchers("/reports/export").hasAuthority("report:export")
~~~

Vì vậy, **`hasRole("ADMIN")` không phải `hasAuthority("ADMIN")`**. Cần thống nhất quy ước đặt tên authority trước khi xây mapper.

### 2.2. ROLE không phải scope OAuth2

Một Access Token có scope `reports.read` không mặc định có nghĩa người dùng được cấp `ROLE_READER` trong ứng dụng web. Scope mô tả quyền ủy quyền truy cập tài nguyên trong hệ sinh thái OAuth2; role/authority nội bộ là chính sách của ứng dụng.

Các authority dạng `SCOPE_reports.read` thường xuất hiện trong các ngữ cảnh kiểm tra scope tại Resource Server hoặc tùy cách xây principal. **Không giả định mọi OAuth2 Login principal tự có đầy đủ `SCOPE_*`** hoặc rằng việc map scope thành role luôn an toàn.

## 3. GrantedAuthoritiesMapper nằm ở đâu trong đăng nhập OAuth2/OIDC?

Trong Servlet OAuth2 Login, Spring Security thực hiện Authentication Code flow, đổi code thành token, tải danh tính và xây dựng các authorities ban đầu. Sau đó mapper có thể biến đổi tập authorities để đặt vào Authentication kết quả.

~~~mermaid
flowchart TD
    A["Browser chọn /oauth2/authorization/company"] --> B["Authorization Code + token exchange"]
    B --> C{"Đăng nhập dạng nào?"}
    C -->|OIDC: scope openid| D["ID Token validation, OidcUserService"]
    C -->|OAuth2 thuần| E["DefaultOAuth2UserService / custom service"]
    D --> F["OidcUser + các GrantedAuthority ban đầu"]
    E --> G["OAuth2User + các GrantedAuthority ban đầu"]
    F --> H["GrantedAuthoritiesMapper.mapAuthorities(...)"]
    G --> H
    H --> I["OAuth2AuthenticationToken với authorities đã ánh xạ"]
    I --> J["SecurityContext / session"]
    J --> K["HTTP authorization: hasRole / hasAuthority"]
    J --> L["Method authorization: @PreAuthorize"]
~~~

Đây là đường đi logic cho OAuth2/OIDC Login thông thường. Mapper **không xác minh chữ ký ID Token**, không phát Access Token, cũng không quyết định một request HTTP được cho phép ngay lúc nó chạy. Nó chỉ chuyển đổi authority list sau khi user service/Authentication Provider xử lý đăng nhập.

### 3.1. API của GrantedAuthoritiesMapper

Giao diện ở package:

~~~java
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
~~~

Phương thức chính:

~~~java
Collection<? extends GrantedAuthority> mapAuthorities(
    Collection<? extends GrantedAuthority> authorities
);
~~~

Đầu vào là **collection của GrantedAuthority**, không phải `OAuth2UserRequest`, `OidcUserRequest`, `ClientRegistration` hay `OAuth2AccessToken`.

Một lambda đơn giản:

~~~java
GrantedAuthoritiesMapper mapper = inputAuthorities -> {
    Set<GrantedAuthority> result = new LinkedHashSet<>();
    for (GrantedAuthority authority : inputAuthorities) {
        result.add(authority);
    }
    return result;
};
~~~

Ví dụ này chưa cấp role mới, chỉ minh họa chữ ký interface. Để sử dụng thật cần import `java.util.Set`, `java.util.LinkedHashSet`, `GrantedAuthority` và `GrantedAuthoritiesMapper`.

### 3.2. Mapper chạy khi nào?

Đối với `oauth2Login()`, mapper thường được gọi trong **lượt xử lý xác thực** khi tạo Authentication mới. Nó không tự chạy lại ở mọi HTTP request, cũng không tự gọi provider để lấy group mới khi người dùng vẫn dùng session cũ.

Do đó:

- Đổi policy ánh xạ trong source code có thể cần **đăng nhập lại** để authority cũ trong session được thay đổi.
- Thu hồi một group tại IdP **không tự động** thu hồi authority trong session web đã tạo trước đó.
- Nếu nghiệp vụ đòi hỏi thu hồi quyền gần tức thời, ứng dụng cần chính sách cập nhật/kiểm tra quyền bổ sung ở server, không thể chỉ dựa vào mapper chạy lúc login.

## 4. Authorities có sẵn trong OAuth2 Login và OIDC Login

Spring Security có những authority đặc biệt chứa dữ liệu của principal.

| Loại authority | Thường gắn với | Dữ liệu có thể đọc |
| --- | --- | --- |
| `OAuth2UserAuthority` | OAuth2 Login thuần | Attributes từ UserInfo-like API, `getAttributes()` |
| `OidcUserAuthority` | OIDC Login | ID Token và, nếu có, UserInfo |
| `SimpleGrantedAuthority` | Role/scope/permission do ứng dụng hoặc provider service tạo | Chuỗi như `ROLE_ADMIN` hoặc `report:read` |

Ví dụ phân biệt:

~~~java
for (GrantedAuthority authority : authorities) {
    if (authority instanceof OidcUserAuthority oidcAuthority) {
        OidcIdToken idToken = oidcAuthority.getIdToken();
        OidcUserInfo userInfo = oidcAuthority.getUserInfo(); // Có thể null
        // Ánh xạ từ claims đã được quy trình OIDC xác thực.
    } else if (authority instanceof OAuth2UserAuthority oauth2Authority) {
        Map<String, Object> attributes = oauth2Authority.getAttributes();
        // Provider OAuth2 thuần: schema/độ tin cậy phụ thuộc hợp đồng tích hợp.
    }
}
~~~

Các import tương ứng:

~~~java
import java.util.Map;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.user.OAuth2UserAuthority;
~~~

`OidcUserAuthority` mặc định mang authority string như `OIDC_USER`; `OAuth2UserAuthority` tương tự với `OAUTH2_USER`. Đây **không** phải role quản trị hay quyền nghiệp vụ. Tập authority cụ thể còn tùy Spring Security version, user service và phần tùy biến.

### 4.1. Dữ liệu trong ID Token và UserInfo

Các claim có thể nằm ở những vị trí khác nhau:

~~~text
OidcUserAuthority
  |
  +-- idToken
  |     iss, sub, aud, exp, nonce, groups? ...
  |
  +-- userInfo (có thể không có)
        sub, name, email, groups? ...
~~~

Trước khi tạo `OidcUser`, Spring Security thực hiện các bước xác thực OIDC phù hợp, trong đó có xác minh ID Token và đối chiếu `sub` của UserInfo với ID Token khi dùng UserInfo.

Nhưng **`groups` không phải claim bắt buộc của OIDC**. Một provider có thể không trả groups, trả group dưới đường dẫn khác hoặc dùng API quản trị riêng. Đừng ép mọi provider vào một giả định schema.

### 4.2. Không lấy thông tin quyền từ token chưa được xác minh

Khi ứng dụng dùng OIDC Login đúng chuẩn, ID Token đã được framework xác minh trước khi mapper xử lý. Dù vậy:

- Không coi mọi chuỗi từ claim `groups` đều có quyền nội bộ tương đương.
- Chỉ chấp nhận issuer/client/provider đã được cấu hình và phê duyệt.
- Không lấy `email`, `name` hoặc `preferred_username` làm “proof” để cấp `ROLE_ADMIN`.
- Không tự decode Access Token rồi đọc `roles` để cấp quyền nếu chưa xác minh đúng loại token, issuer/audience và contract.

**Đúng người dùng** và **được cấp quyền trong ứng dụng** là hai bước khác nhau.

## 5. Cấu hình ứng dụng Servlet sử dụng OIDC provider

Ví dụ Spring Boot 3.x có các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Với Spring Boot 4.x, sử dụng starter tương ứng `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client` theo BOM của phiên bản đã chọn. Không trộn thủ công các phiên bản Spring Security không tương thích với Spring Boot.

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Issuer/URL trên là ví dụ minh họa. Trong sản phẩm thật, issuer phải khớp chính xác nhà cung cấp được tin cậy; client secret được lưu trong secret manager/biến môi trường, không hard-code trong source control.

**Mapper không tự xin thêm scope hoặc UserInfo claims.** Nếu ID Token/UserInfo không có claim `groups` thì mapper không thể tự tưởng tượng một danh sách nhóm; cần cấu hình provider để trả claim hoặc dùng cơ chế lấy quyền khác.

## 6. Xây dựng GrantedAuthoritiesMapper tập trung bằng Java

Giả sử ID Token của provider doanh nghiệp có claim `groups` là mảng chuỗi:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "employee-123",
  "aud": "portal-web",
  "groups": ["portal-readers", "portal-report-editors"]
}
~~~

Hệ thống chỉ công nhận các group đã được duyệt:

| Provider group | Spring Security authority |
| --- | --- |
| `portal-readers` | `ROLE_READER` |
| `portal-report-editors` | `ROLE_REPORT_EDITOR` |
| `portal-admins` | `ROLE_ADMIN` |
| Group khác | **Không tự cấp role** |

### 6.1. Bean GrantedAuthoritiesMapper

~~~java
package com.example.security;

import java.net.URI;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.user.OAuth2UserAuthority;

@Configuration
public class AuthorityMappingConfig {

    // Issuer mà ứng dụng đã đăng ký và tin cậy.
    private static final URI TRUSTED_ISSUER =
        URI.create("https://id.example.com/realms/company");

    // Chỉ những group trong bảng này mới được cấp role nghiệp vụ.
    private static final Map<String, String> GROUP_TO_ROLE = Map.of(
        "portal-readers", "ROLE_READER",
        "portal-report-editors", "ROLE_REPORT_EDITOR",
        "portal-admins", "ROLE_ADMIN"
    );

    @Bean
    GrantedAuthoritiesMapper userAuthoritiesMapper() {
        return authorities -> {
            Set<GrantedAuthority> mapped = new LinkedHashSet<>();

            for (GrantedAuthority authority : authorities) {
                if (authority instanceof OidcUserAuthority oidc) {
                    // Giữ lại authority đặc biệt đại diện cho OIDC user.
                    mapped.add(oidc);
                    OidcIdToken idToken = oidc.getIdToken();

                    if (!TRUSTED_ISSUER.equals(idToken.getIssuer())) {
                        // Không cấp role từ issuer không thuộc chính sách.
                        continue;
                    }

                    Object claim = idToken.getClaims().get("groups");
                    if (!(claim instanceof Collection<?> groups)) {
                        continue;
                    }

                    for (Object rawGroup : groups) {
                        if (!(rawGroup instanceof String groupName)) {
                            continue;
                        }

                        String role = GROUP_TO_ROLE.get(groupName);
                        if (role != null) {
                            mapped.add(new SimpleGrantedAuthority(role));
                        }
                    }
                } else if (authority instanceof OAuth2UserAuthority oauth2) {
                    // OAuth2 Login thuần: giữ authority nhận diện,
                    // không tự suy ra vai trò quản trị từ attributes.
                    mapped.add(oauth2);
                }
            }

            return mapped;
        };
    }
}
~~~

Đây là một **policy ví dụ dành cho một issuer cụ thể**. Nó cố ý không giữ lại mọi `SimpleGrantedAuthority` từ đầu vào và không tự cấp role cho OAuth2 provider thuần. Nếu ứng dụng cần giữ các authority khác (ví dụ permission nội bộ hoặc scope đã được thẩm định), phải bổ sung quy tắc bảo toàn rõ ràng thay vì sao chép vô điều kiện mọi quyền đến từ nguồn không kiểm soát.

### 6.2. Vì sao cần allowlist?

Cách viết nguy hiểm:

~~~java
// PHẢN VÍ DỤ: không dùng để cấp quyền quản trị trực tiếp.
for (String group : groups) {
    mapped.add(new SimpleGrantedAuthority("ROLE_" + group.toUpperCase()));
}
~~~

Nếu provider trả `admins`, `system-owner` hoặc một group mới với tên trùng role nhạy cảm, ứng dụng có thể cấp quyền chưa từng được phê duyệt. Khi dùng allowlist, chỉ những quan hệ **group → authority** được xem xét trong policy mới tạo ra quyền.

**Lưu ý:** Bản thân group ID cũng phải thuộc nguồn dữ liệu phù hợp. Nếu provider cho user tự tạo nhóm với tên `portal-admins` mà không có kiểm soát membership, dù có allowlist thì vẫn có rủi ro leo thang quyền. Quy trình quản trị group tại IdP là một phần của mô hình tin cậy.

### 6.3. Vì sao kiểm tra issuer?

Trong ứng dụng cho phép nhiều OIDC providers, hai issuer có thể cùng trả `groups=["portal-admins"]` nhưng nhóm đó **không có cùng mức tin cậy**. Chỉ so tên group mà không xét issuer/client context có thể khiến tài khoản từ nhà cung cấp bên ngoài được quyền quản trị ứng dụng.

Ví dụ chính sách:

~~~text
https://id.example.com/realms/company
  groups: [portal-admins] -> ROLE_ADMIN

https://login.partner.example.net
  groups: [portal-admins] -> KHÔNG tự cấp ROLE_ADMIN
~~~

Trong OIDC Login đúng chuẩn, `iss` của ID Token đã được xác minh với issuer tin cậy của registration. Kiểm tra issuer trong mapper là một **hàng rào policy bổ sung** khi ánh xạ role; nó không thay thế ID Token validation của Spring Security.

### 6.4. Mapping từ UserInfo thay vì ID Token

Một số provider trả group trong UserInfo. `OidcUserAuthority` có thể có `getUserInfo()`:

~~~java
OidcUserInfo userInfo = oidcAuthority.getUserInfo();
if (userInfo != null) {
    Object rawGroups = userInfo.getClaims().get("groups");
    // Kiểm tra kiểu dữ liệu, issuer và allowlist trước khi map.
}
~~~

Đoạn trên giả định biến `oidcAuthority` đã có và cần import `OidcUserInfo`. Không mặc định UserInfo luôn tồn tại. Khi dựa vào UserInfo, phải sử dụng service/flow OIDC bảo đảm **UserInfo.sub trùng ID Token.sub**, không tự gọi API tùy ý và ghép dữ liệu người khác vào principal.

Nếu cả ID Token và UserInfo đều có group nhưng khác nhau, chính sách ứng dụng phải quy định nguồn nào có thẩm quyền. Không hợp nhất hai danh sách tùy tiện để “được càng nhiều quyền càng tốt”.

## 7. Gắn mapper vào SecurityFilterChain Servlet

Mapper cần được đưa vào cấu hình OAuth2 Login của **chain xử lý callback**:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            GrantedAuthoritiesMapper userAuthoritiesMapper) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/css/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/reports/edit/**").hasRole("REPORT_EDITOR")
                .requestMatchers("/reports/**").hasAnyRole(
                    "READER", "REPORT_EDITOR", "ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .userAuthoritiesMapper(userAuthoritiesMapper)))
            .build();
    }
}
~~~

Điểm quan trọng:

~~~java
.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userAuthoritiesMapper(userAuthoritiesMapper)))
~~~

Trong Spring Security có thể tồn tại cơ chế tự sử dụng `GrantedAuthoritiesMapper` bean theo cấu hình tương ứng; **gắn tường minh qua DSL** giúp người đọc thấy rõ mapper nào áp dụng cho OAuth2 Login.

Đặt các matcher **cụ thể hơn trước** matcher tổng quát: `/reports/edit/**` cần được kiểm tra trước `/reports/**`. Nếu không, quy tắc rộng có thể bắt request trước và cho phép không đúng dự kiến.

### 7.1. Điều gì xảy ra sau khi mapper trả về authorities?

Ví dụ ID Token của user thuộc `portal-report-editors`:

~~~text
Trước mapping:
  OidcUserAuthority("OIDC_USER", idToken, userInfo)

Sau mapping:
  OidcUserAuthority("OIDC_USER", idToken, userInfo)
  SimpleGrantedAuthority("ROLE_REPORT_EDITOR")

GET /reports/edit/123
  -> hasRole("REPORT_EDITOR")
  -> Authentication có ROLE_REPORT_EDITOR -> cho phép
~~~

Giả sử user chỉ thuộc `portal-readers`:

~~~text
Sau mapping:
  OIDC_USER
  ROLE_READER

GET /reports/edit/123
  -> yêu cầu ROLE_REPORT_EDITOR
  -> không có -> từ chối
~~~

Mapper **không cấp quyền theo đường dẫn**: mapper cung cấp authorities; cấu hình URL/method security quyết định yêu cầu nào cần authority nào.

### 7.2. Hiển thị authorities đang được authorization sử dụng

Để nhìn thấy authorities của `Authentication`, có thể tạo endpoint chẩn đoán nội bộ (trong môi trường được phép):

~~~java
package com.example.web;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me/authorities")
    public Map<String, Object> authorities(Authentication authentication) {
        List<String> names = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("principalName", authentication.getName());
        result.put("authorities", names);
        return result;
    }
}
~~~

Ví dụ Java dùng `Stream.toList()` (Java 16+). Endpoint này chỉ để minh họa; trong production có thể không nên công bố toàn bộ authorities/nhóm cho người dùng vì chúng có thể tiết lộ thông tin nội bộ. Nếu dùng để debug, giới hạn quyền truy cập và không đưa token hoặc toàn bộ principal claims ra response.

**Phân biệt:** `Authentication.getAuthorities()` là tập authority thường được bộ máy authorization đọc. Tập authority trên object principal `OidcUser` có thể không đồng nhất hoàn toàn với authorities đã được mapper đưa lên Authentication trong một số cách cấu hình. Khi kiểm tra kết quả mapping, ưu tiên quan sát **Authentication authorities** thay vì giả định `principal.getAuthorities()` luôn phản ánh mapper.

## 8. Áp dụng ánh xạ tập trung với method security

Ngoài chặn URL, Spring Security có thể kiểm tra quyền tại service method. Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Ví dụ service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('REPORT_EDITOR')")
    public void updateReport(long reportId, String content) {
        // Logic cập nhật báo cáo, đồng thời phải kiểm tra ownership/tenant.
    }

    @PreAuthorize("hasAnyRole('READER', 'REPORT_EDITOR', 'ADMIN')")
    public String readReport(long reportId) {
        // Logic đọc báo cáo; ví dụ chỉ thể hiện phân quyền.
        return "report-" + reportId;
    }
}
~~~

Nhờ có mapping tập trung, `ROLE_REPORT_EDITOR` được dùng nhất quán trong:

~~~text
Provider group = portal-report-editors
          |
          v
GrantedAuthoritiesMapper
          |
          v
ROLE_REPORT_EDITOR
    |                   |
    v                   v
HTTP /reports/edit/**   @PreAuthorize("hasRole('REPORT_EDITOR')")
~~~

Tuy nhiên, **role không thay thế kiểm tra quyền trên đối tượng**. Một người có `ROLE_REPORT_EDITOR` có thể chỉ được sửa báo cáo thuộc tenant/phòng ban của mình. Service cần thêm kiểm tra tenant, ownership hoặc policy theo resource ID, không cho phép sửa mọi báo cáo chỉ vì role phù hợp.

### 8.1. RoleHierarchy có giống GrantedAuthoritiesMapper không?

Không.

- **GrantedAuthoritiesMapper** biến đổi danh sách authority khi xác thực: ví dụ group `portal-admins` thành `ROLE_ADMIN`.
- **RoleHierarchy** mô tả quan hệ bao hàm giữa các role: ví dụ `ROLE_ADMIN > ROLE_REPORT_EDITOR > ROLE_READER` khi sản phẩm thật sự muốn admin có quyền của editor/reader.
- **AuthorizationManager / @PreAuthorize** thực thi rule khi request/method được gọi.

Nếu không cấu hình role hierarchy, **`ROLE_ADMIN` không mặc nhiên bao hàm `ROLE_READER`**. Ví dụ URL ở phần trên dùng `hasAnyRole(...)` để liệt kê các role được phép; không dựa vào quan hệ phân cấp ngầm.

## 9. Khi nào GrantedAuthoritiesMapper không đủ?

Mapper chỉ có `Collection<? extends GrantedAuthority>`. Nó **không nhận `OAuth2AccessToken`**, `OidcUserRequest` hoặc `ClientRegistration` như tham số trực tiếp. Đây là giới hạn quan trọng:

Giả sử nhà cung cấp danh tính không đặt danh sách group trong ID Token/UserInfo mà yêu cầu gọi API:

~~~http
GET /api/v1/user/groups HTTP/1.1
Host: directory.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_GROUP_API
~~~

`GrantedAuthoritiesMapper` không có sẵn Access Token để thực hiện request này. Cố lấy Access Token qua biến global, đọc security context chưa ổn định hoặc truyền token vào map authority giả tạo sẽ làm rối vòng đời bảo mật.

Giải pháp thích hợp là dùng **delegating `OAuth2UserService` / `OidcUserService`** vì chúng nhận user request chứa Access Token và registration, sau đó trả principal với authorities được quản lý rõ ràng.

### 9.1. So sánh hai cách mở rộng

| Cách mở rộng | Dữ liệu đầu vào trực tiếp | Phù hợp khi |
| --- | --- | --- |
| `GrantedAuthoritiesMapper` | Collection authorities, có thể chứa `OidcUserAuthority`/`OAuth2UserAuthority` | Cần chuyển group/claim đã có thành authority tập trung |
| `OAuth2UserService<OAuth2UserRequest, OAuth2User>` | User request gồm registration và Access Token | OAuth2 provider thuần cần gọi API user/group riêng hoặc mapping provider-specific |
| `OAuth2UserService<OidcUserRequest, OidcUser>` | OIDC user request gồm Access Token và ID Token | Cần gọi API bổ sung trong lúc dựng OIDC principal |
| Authorization service riêng sau login | Authentication, principal, thông tin nghiệp vụ | Quyền thay đổi thường xuyên hoặc cần kiểm tra resource-level policy |

### 9.2. Ví dụ delegate OidcUserService để gắn thêm role

Đoạn sau minh họa **chèn một nguồn chính sách ứng dụng sau khi OIDC principal đã được service mặc định tải**. Ở đây chưa gọi API ngoài, mà tra một interface domain để dễ thấy vị trí cần mở rộng:

~~~java
package com.example.security;

import java.util.LinkedHashSet;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class DomainOidcUserService {

    private final OidcUserService delegate = new OidcUserService();
    private final InternalRolePolicy rolePolicy;

    public DomainOidcUserService(InternalRolePolicy rolePolicy) {
        this.rolePolicy = rolePolicy;
    }

    public OAuth2UserService<OidcUserRequest, OidcUser> create() {
        return request -> {
            OidcUser user = delegate.loadUser(request);
            String registrationId =
                request.getClientRegistration().getRegistrationId();

            Set<GrantedAuthority> authorities =
                new LinkedHashSet<>(user.getAuthorities());

            // Chỉ gắn vai trò nếu policy nội bộ đã phê duyệt.
            // Bản triển khai thật phải kiểm soát nguồn policy và lỗi truy cập.
            if (rolePolicy.canEditReports(
                    registrationId,
                    user.getIdToken().getIssuer().toString(),
                    user.getSubject())) {
                authorities.add(
                    new SimpleGrantedAuthority("ROLE_REPORT_EDITOR"));
            }

            return new DefaultOidcUser(
                authorities,
                user.getIdToken(),
                user.getUserInfo(),
                "sub");
        };
    }
}
~~~

Trong ví dụ, `InternalRolePolicy` là **interface nghiệp vụ do ứng dụng tự định nghĩa** (chưa có implementation). Đây là đoạn minh họa điểm mở rộng chứ không phải một project hoàn chỉnh; một implementation có thể truy vấn database/authorization service theo khóa `issuer + subject` hoặc, nếu đúng hợp đồng, gọi API group bằng `request.getAccessToken()`.

Những lưu ý:

1. `delegate.loadUser(request)` giữ logic OIDC của thư viện, gồm kiểm tra UserInfo cần thiết; **không bỏ qua delegate** chỉ vì muốn lấy thêm roles.
2. `request.getAccessToken()` có thể dùng để gọi API đã được provider cho phép; không gửi token đến endpoint ngoài danh sách tin cậy.
3. Quyền nội bộ phải được ràng buộc với `issuer + subject` và/hoặc registration thích hợp, không chỉ email.
4. Nếu yêu cầu cập nhật role theo thời gian thực, việc tra role **chỉ lúc login** vẫn có nguy cơ stale; cần chiến lược kiểm tra và thu hồi riêng.
5. Một custom user service có thể trả `OidcUser` với authorities đã mở rộng; nếu đồng thời có `GrantedAuthoritiesMapper`, phải thiết kế hai bước để tránh vô tình xóa những authorities do service tạo ra.

### 9.3. Tránh ghép mapper và custom user service một cách vô tình

Giả sử delegating service đã thêm `ROLE_REPORT_EDITOR`. Nếu mapper ở phần 6 chỉ giữ `OidcUserAuthority`/`OAuth2UserAuthority` và những role do `groups` công nhận, `ROLE_REPORT_EDITOR` do service thêm có thể **bị loại**.

Có ba chiến lược rõ ràng:

- **Một nguồn ánh xạ:** service thu thập dữ liệu, rồi gọi chung một policy/mapping component để tạo tập authorities cuối cùng.
- **Mapper bảo toàn có điều kiện:** giữ các authorities đã qua một nguồn tin cậy/định nghĩa sẵn (không giữ role tùy ý từ mọi provider).
- **Phân tách trách nhiệm:** mapper chỉ xử lý nhóm trong OIDC claim, custom service xử lý phần khác và cả hai được kiểm soát bằng một chính sách hợp nhất.

**Không vừa thêm role trong user service, vừa âm thầm xóa role ở mapper**, khiến ứng dụng đăng nhập thành công nhưng endpoint trả 403 khó hiểu.

## 10. Ánh xạ quyền với nhiều provider và nhiều tenant

Ví dụ portal cho đăng nhập từ OIDC doanh nghiệp và một OAuth2 provider đối tác. Cả hai đều có thể có thuộc tính `groups`, nhưng semantics khác nhau:

~~~text
Company OIDC:
  issuer = https://id.example.com/realms/company
  groups = [portal-admins]
  -> Cho phép ROLE_ADMIN theo policy nội bộ.

Partner OAuth2:
  userinfo.groups = [portal-admins]
  -> Không cho ROLE_ADMIN chỉ vì tên nhóm giống.
~~~

Với OIDC, issuer là khóa namespace tốt để phân biệt nguồn định danh. Với OAuth2 provider thuần, mapper thường không có đủ registration context để phân biệt provider nếu chỉ nhìn vào attributes; nên sử dụng custom `OAuth2UserService` có `userRequest.getClientRegistration()` khi cần mapping provider-aware.

### 10.1. Policy tách riêng cho từng issuer

Một policy tổng quát có thể được mô hình hóa như sau:

| Trusted issuer | Claim nguồn | Nhóm được duyệt | Authority |
| --- | --- | --- | --- |
| `https://id.example.com/realms/company` | `groups` | `portal-admins` | `ROLE_ADMIN` |
| `https://id.example.com/realms/company` | `groups` | `portal-readers` | `ROLE_READER` |
| `https://login.partner.example.net` | `groups` | `partner-readers` | `ROLE_PARTNER_READER` |
| Issuer khác | Bất kỳ | Bất kỳ | Không cấp role nội bộ |

Khi có nhiều tenant trong cùng một OP, issuer có thể bao gồm realm/tenant path. Không chỉ so hostname rồi áp dụng chung quyền quản trị; hai tenant khác issuer phải được xét theo các ranh giới tin cậy riêng.

### 10.2. Group không chắc là role

Group có thể là:

- Đơn vị tổ chức, phòng ban hoặc dự án.
- Nhóm dùng để phân phối email.
- Nhóm truy cập của tenant.
- Nhóm đặc quyền thực sự do quản trị viên IdP kiểm soát.

Chỉ những nhóm được xác định trong **mô hình authorization của ứng dụng** mới nên map thành role. Tên group có chữ `admin` không làm nó tự trở thành quyền admin.

### 10.3. Phân quyền nhiều tenant cần thêm kiểm tra tài nguyên

Kể cả khi user có `ROLE_REPORT_EDITOR`, việc sửa báo cáo vẫn có thể bị giới hạn theo tenant:

~~~text
Authentication:
  subject = employee-123
  issuer  = company-idp
  role    = ROLE_REPORT_EDITOR

Request:
  PATCH /tenants/tenant-B/reports/100

Policy:
  role đúng?              Có
  user thuộc tenant-B?    Không
  report thuộc tenant-B?  Cần xác minh

=> Không được phép chỉ vì có role.
~~~

`GrantedAuthoritiesMapper` hỗ trợ mô hình authority ở mức tương đối tổng quát. **ABAC/ownership/tenant checks** cần lớp authorization tương ứng tại service/API hoặc policy engine của sản phẩm.

## 11. Ánh xạ từ claim có cấu trúc phức tạp

Không phải provider nào cũng trả `groups` dạng mảng phẳng. Một số trả:

~~~json
{
  "realm_access": {
    "roles": ["employee", "portal-reader"]
  },
  "resource_access": {
    "portal-web": {
      "roles": ["report-editor"]
    }
  }
}
~~~

Đây là **một ví dụ cấu trúc phụ thuộc nhà cung cấp**, không phải claim chuẩn chung của OIDC. Cần đọc hợp đồng token/claim mapping của provider trước khi phân tích.

Một hàm lấy role từ cấu trúc nested phải kiểm tra kiểu:

~~~java
import java.util.Collection;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public static Set<String> extractPortalRoles(Map<String, Object> claims) {
    Object resources = claims.get("resource_access");
    if (!(resources instanceof Map<?, ?> resourceMap)) {
        return Set.of();
    }
    Object portal = resourceMap.get("portal-web");
    if (!(portal instanceof Map<?, ?> portalMap)) {
        return Set.of();
    }
    Object roles = portalMap.get("roles");
    if (!(roles instanceof Collection<?> roleList)) {
        return Set.of();
    }
    return roleList.stream()
        .filter(String.class::isInstance)
        .map(String.class::cast)
        .collect(Collectors.toUnmodifiableSet());
}
~~~

Sau đó **chỉ map các giá trị đã được duyệt**:

~~~java
if (extractPortalRoles(idToken.getClaims()).contains("report-editor")) {
    mapped.add(new SimpleGrantedAuthority("ROLE_REPORT_EDITOR"));
}
~~~

Ở đây `idToken` và `mapped` là biến đã có trong mapper. Không chuyển nguyên `resource_access.portal-web.roles` thành authorities. Những role kiểu `manage-account` hoặc role của ứng dụng khác không nên trở thành authority tại portal chỉ vì cùng nằm trong JWT.

Nếu claim chỉ có trong **Access Token** của API, đó không phải tự động là claim dành cho OIDC Client. Hãy phân biệt ID Token, Access Token và UserInfo; chọn đúng nguồn dữ liệu cho ứng dụng thay vì tự decode một token không dành cho client.

## 12. Vòng đời authority và vấn đề stale permissions

Một mapper tập trung giúp nhất quán cách cấp role lúc login, nhưng **không bảo đảm cập nhật quyền tức thời**.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant OP as OIDC Provider
    participant C as Spring Security Client
    participant DB as Local authorization policy
    U->>C: Bắt đầu login
    C->>OP: Authorization Code flow
    OP-->>C: Token + claims
    C->>C: GrantedAuthoritiesMapper -> ROLE_REPORT_EDITOR
    C-->>U: Session đã đăng nhập
    Note over OP: Quản trị viên gỡ user khỏi nhóm editor
    U->>C: PATCH /reports/edit/123 với session cũ
    C->>C: Authentication vẫn có ROLE_REPORT_EDITOR
    Note over C: Mapper không tự chạy lại cho mỗi HTTP request
~~~

Nếu ứng dụng xử lý dữ liệu nhạy cảm và cần thu hồi role gần thời gian thực, cân nhắc:

- Thời hạn session hợp lý, reauthentication/reauthorization theo mức rủi ro.
- Kiểm tra quyền từ **authorization service** hoặc database nội bộ khi thực hiện thao tác quan trọng.
- Cơ chế invalidation session khi có sự kiện thu hồi quyền, nếu hạ tầng hỗ trợ và được thiết kế.
- Đánh giá lại quyền tại service với tenant/ownership, không chỉ dựa vào role từ login ban đầu.
- Quản lý TTL/cache của quyền, đánh đổi giữa độ mới và latency.

**Access Token expiry không đồng nghĩa Authentication/session của browser tự hết hạn cùng thời điểm.** Browser có thể có session hợp lệ trong khi quyền tại IdP đã đổi. Đừng giả định refresh token tự chạy lại GrantedAuthoritiesMapper và cập nhật authorities trên session.

## 13. Kiểm thử mapper như một hàm chính sách

Một lợi ích của `GrantedAuthoritiesMapper` là có thể test phần chuyển đổi authority riêng, không cần khởi động toàn bộ Authorization Code flow.

### 13.1. Một unit test minh họa

Ví dụ JUnit 5 dưới đây kiểm tra một group đã được duyệt:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

class AuthorityMappingConfigTest {

    private final GrantedAuthoritiesMapper mapper =
        new AuthorityMappingConfig().userAuthoritiesMapper();

    @Test
    void mapsApprovedCompanyGroupToReader() {
        Instant now = Instant.now();
        OidcIdToken idToken = new OidcIdToken(
            "TEST_ONLY_TOKEN_VALUE",
            now,
            now.plusSeconds(300),
            Map.of(
                "iss", "https://id.example.com/realms/company",
                "sub", "employee-123",
                "aud", List.of("portal-web"),
                "groups", List.of("portal-readers")
            ));

        OidcUserAuthority oidcAuthority = new OidcUserAuthority(idToken);
        var names = mapper.mapAuthorities(List.of(oidcAuthority)).stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertTrue(names.contains("ROLE_READER"));
    }
}
~~~

Đây là **unit test policy mapping**, không phải bằng chứng ID Token được xác minh: test tạo đối tượng `OidcIdToken` trực tiếp. Test OIDC login end-to-end phải có authorization request, token response và validator tương ứng.

### 13.2. Những tình huống nên kiểm thử

| Đầu vào | Kết quả mong muốn |
| --- | --- |
| Company issuer, `groups=["portal-readers"]` | Có `ROLE_READER` |
| Company issuer, `groups=["portal-admins"]` | Có `ROLE_ADMIN` |
| Company issuer, group chưa được duyệt | Không tự cấp role từ group đó |
| Partner issuer, `groups=["portal-admins"]` | **Không** cấp `ROLE_ADMIN` theo policy của company |
| Claim `groups` thiếu hoặc `null` | Không crash, không tự cấp role |
| Claim `groups` là chuỗi thay vì mảng | Không tự đoán format; xử lý theo hợp đồng |
| Claim `groups` chứa số/object | Không ép bừa thành String/role |
| Nhiều group trùng nhau | Authority không bị nhân bản gây nhiễu |
| OAuth2UserAuthority của provider thuần | Không tự áp policy OIDC company |
| Custom service thêm role đã duyệt | Mapper có chính sách bảo toàn hoặc tái tạo role rõ ràng |
| Session cũ sau khi role tại IdP bị thu hồi | Có chiến lược invalidation/refresh authorization phù hợp |

### 13.3. Test việc sử dụng role trên endpoint

Unit test của mapper chứng minh “group A tạo authority B”. Nó **không đủ** để chứng minh “GET/PATCH endpoint được chặn đúng”. Với test tích hợp Spring MVC/Spring Security, cần kiểm tra:

- Chưa đăng nhập: endpoint yêu cầu xác thực.
- Đã đăng nhập, chỉ có `ROLE_READER`: không sửa được báo cáo.
- Đã đăng nhập, có `ROLE_REPORT_EDITOR`: qua kiểm tra role nhưng vẫn phải kiểm tra ownership/tenant.
- Có `ROLE_ADMIN`: chỉ được phép với những chức năng policy admin thực sự cho phép.

Mock authentication trong controller test không tự chứng minh OIDC token validation. Cần tách test chính sách mapping, test authorization và test OIDC integration.

## 14. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Người dùng đăng nhập thành công nhưng luôn nhận 403 | Mapper không được gắn vào đúng `SecurityFilterChain`, hoặc claim group không tồn tại | Kiểm tra DSL `userAuthoritiesMapper`, nguồn claim và Authentication authorities |
| `hasRole("ADMIN")` không nhận `ADMIN` | Thiếu tiền tố mặc định `ROLE_` | Map thành `ROLE_ADMIN` hoặc dùng `hasAuthority` đúng chuỗi |
| Mapper có role nhưng endpoint vẫn 403 | Matcher thứ tự sai, method security/tenant policy khác đang từ chối | Xem chính sách tại mọi lớp bảo vệ |
| Mọi người dùng đều có role admin | Tự map tất cả group thành role hoặc nhận group từ provider không tin cậy | Áp dụng allowlist và issuer/client policy |
| Claim `groups` bằng `null` | Provider không cấp group hoặc scope chưa phù hợp | Xử lý thiếu claim, kiểm tra provider mapping |
| `ClassCastException` khi đọc groups | Provider trả object/string thay vì `List<String>` | Kiểm tra kiểu, xử lý đúng schema provider |
| Quyền từ API bổ sung không có trong mapper | Mapper không nhận Access Token | Dùng delegating OAuth2/OIDC user service |
| Custom user service có role nhưng sau login role biến mất | Mapper xóa mất authority mà service thêm | Hợp nhất policy/bảo toàn có kiểm soát |
| Role cũ vẫn còn sau khi user bị gỡ nhóm | Mapper chỉ chạy lúc xác thực | Session invalidation, reauthentication hoặc policy động |
| Hai provider cùng group admin nhưng đều có quyền | Mapper không xét nguồn tin cậy/issuer | Tách mapping theo issuer/provider |
| `principal.getAuthorities()` khác `Authentication.getAuthorities()` | Mapping được đặt ở Authentication, không nhất thiết viết lại principal | Kiểm tra `Authentication.getAuthorities()` khi debug authorization |
| Dùng role trong Access Token làm quyền portal | Nhầm Access Token của resource server với nguồn định danh OIDC của client | Dùng claim đã xác minh/nguồn chính sách rõ ràng |
| `ROLE_ADMIN` đủ để xem dữ liệu tenant khác | Chưa có kiểm tra resource ownership/tenant | Áp dụng kiểm tra policy đối tượng tại service/API |

### 14.1. Một luồng chẩn đoán rõ ràng

~~~text
User login thành công nhưng /admin bị 403
  |
  +-- Có đúng registration/issuer không?
  |
  +-- ID Token/UserInfo có claim group theo hợp đồng không?
  |
  +-- Mapper có được gắn vào oauth2Login() của chain đúng không?
  |
  +-- Authentication.getAuthorities() có ROLE_ADMIN không?
  |
  +-- URL rule có dùng hasRole("ADMIN") hay chuỗi khác?
  |
  +-- Method security/tenant policy có điều kiện bổ sung không?
  |
  +-- User có phải đang dùng session cũ trước khi role thay đổi không?
~~~

Khi debug, không log nguyên ID Token, Access Token, Refresh Token, `client_secret` hoặc toàn bộ UserInfo JSON. Nếu cần phân tích, dùng mã registration, issuer tin cậy, nhóm authority đã được phép quan sát, correlation ID và dữ liệu tối thiểu theo chính sách.

## 15. Nguyên tắc bảo mật khi ánh xạ quyền tập trung

### 15.1. Không cấp role trực tiếp từ mọi claim

Claims có thể chứa dữ liệu hiển thị, gợi ý hoặc thuộc một ứng dụng khác. `preferred_username=admin`, `email=admin@example.com` hoặc `groups=["admins"]` không tự đủ để cấp quyền quản trị. Phải có **hợp đồng claim, issuer tin cậy và mapping allowlist**.

### 15.2. Áp dụng least privilege

Mặc định không cấp role nhạy cảm; chỉ cấp authority cần thiết. Nếu không có group được công nhận, người dùng có thể vẫn đăng nhập nhưng chỉ truy cập tính năng dành cho authenticated users hoặc bị hạn chế theo policy ứng dụng.

### 15.3. Phân tách danh tính và quyền

OIDC trả bằng chứng xác thực danh tính (`iss`, `sub`, `aud`...). Mapper chuyển một tập thông tin đã được chấp thuận thành quyền ứng dụng. Kiểm tra resource-level authorization mới quyết định người dùng được thao tác dữ liệu nào.

### 15.4. Tránh open policy với multi-provider

Một provider đối tác không mặc định có quyền quản trị nội bộ chỉ vì trả role cùng tên với IdP doanh nghiệp. Phải giới hạn theo issuer, client registration và chính sách onboarding của provider. Không dựa trên hostname gần giống hoặc username/email làm namespace tin cậy.

### 15.5. Không tự fetch dữ liệu từ URL do claim cung cấp

Nếu claim chứa `groups_uri` hay `profile_url`, không tự lấy URL đó rồi gửi Access Token đến bất kỳ hostname nào; có thể dẫn đến SSRF hoặc làm lộ token. Chỉ gọi endpoint đã được cấu hình/cho phép và kiểm tra audience/scope tương ứng.

### 15.6. Cần cơ chế thu hồi quyền

Mapper lúc login không thay thế quy trình khóa user, xóa session hoặc cập nhật quyền khi role bị thu hồi. Với thao tác quan trọng, cân nhắc policy service/database và thời hạn phiên phù hợp.

### 15.7. Không dùng role làm bảo vệ duy nhất cho tenant/đối tượng

`ROLE_ADMIN` có thể mang nghĩa “quản trị **một tenant**” chứ không phải toàn hệ thống. Kiểm tra ownership, tenant, trạng thái tài nguyên và chính sách động ở lớp phù hợp; tránh mọi người có role đúng nhưng truy cập dữ liệu tenant khác.

## 16. Bài tập tình huống

### Tình huống A — Chỉ cần map group của OIDC

Provider doanh nghiệp đã đưa claim `groups` trong ID Token đã được xác minh. Ứng dụng chỉ có ba group nghiệp vụ cần công nhận.

**Lựa chọn:** `GrantedAuthoritiesMapper` với bảng allowlist. Không cần tạo HTTP call tới IdP lần nữa. Gắn mapper vào `oauth2Login().userInfoEndpoint()` và dùng `hasRole`/`@PreAuthorize`.

### Tình huống B — Group nằm trong UserInfo

ID Token không có `groups`, nhưng UserInfo đã được Spring Security tải và có subject khớp ID Token.

**Lựa chọn:** đọc `OidcUserAuthority.getUserInfo()` khi không null; map các group được duyệt. Không giả định mọi lần login đều có UserInfo hoặc mọi provider đều dùng cùng schema.

### Tình huống C — Group phải lấy bằng API riêng

Provider yêu cầu gọi `/v1/groups` với Access Token; claim ID Token/UserInfo không có group.

**Lựa chọn:** delegating `OidcUserService` hoặc `OAuth2UserService`, vì user request có Access Token và registration context. Không cố lấy Access Token từ `GrantedAuthoritiesMapper`.

### Tình huống D — Hai provider đều trả “admins”

Company IdP và Partner IdP cùng trả `groups=["admins"]`.

**Lựa chọn:** mapping theo issuer/provider. Không tự cho Partner user quyền quản trị company; sử dụng bảng allowlist riêng hoặc quyết định quyền từ hệ thống nội bộ.

### Tình huống E — User có `ROLE_ADMIN` nhưng không sửa được báo cáo tenant B

User admin của tenant A gửi request tới báo cáo thuộc tenant B.

**Lựa chọn:** ngoài role, service/API phải kiểm tra quyền trên **tenant và resource cụ thể**. Mapper không tự giải quyết bài toán ownership.

### Tình huống F — Cấp quyền thành công, sau đó admin bị thu hồi nhóm

User vẫn đang giữ HTTP session đã đăng nhập, chứa `ROLE_ADMIN` từ thời điểm trước.

**Lựa chọn:** thiết kế invalidation/reauthentication/authorization policy động. Đừng kỳ vọng mapper tự chạy lại chỉ vì group thay đổi trong IdP.

### Tình huống G — Mapper vô tình làm mất scope permission

Ứng dụng trước đó kiểm tra authority `SCOPE_reports.read`, nhưng mapper chỉ giữ `OIDC_USER` và các role.

**Lựa chọn:** xác định authority nào thực sự dùng trong policy, sau đó bổ sung quy tắc bảo toàn có kiểm soát hoặc thay cách kiểm tra. Không coi mọi `SCOPE_*` tự đáng tin trong mọi loại login.

### Tình huống H — API trả 403 dù portal có `ROLE_READER`

Ứng dụng gửi Access Token đi gọi downstream Resource Server nhưng bị từ chối.

**Lựa chọn:** kiểm tra Access Token dành cho API đó, audience, scope và policy phía Resource Server. `ROLE_READER` trong web `Authentication` không làm Access Token tự có thêm quyền.

## 17. Tài liệu tham khảo

- Spring Security — Servlet OAuth2 Login, Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — Servlet OAuth2 Login, Core Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — GrantedAuthoritiesMapper Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/mapping/GrantedAuthoritiesMapper.html
- Spring Security — OidcUserAuthority Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUserAuthority.html
- Spring Security — OAuth2UserAuthority Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/user/OAuth2UserAuthority.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html

## 18. Tổng kết

`GrantedAuthoritiesMapper` là **điểm ánh xạ tập trung** các authorities được tạo trong quá trình OAuth2/OIDC Login thành authorities mà ứng dụng sử dụng để phân quyền.

~~~text
OIDC / OAuth2 Login
    |
    v
Xác thực danh tính và tải principal
    |
    +-- OidcUserAuthority
    |      ID Token, UserInfo nếu có
    |
    +-- OAuth2UserAuthority
           Attributes của provider OAuth2
    |
    v
GrantedAuthoritiesMapper
    - Kiểm tra issuer/nguồn claim
    - Chỉ map group được phê duyệt
    - Áp dụng quy tắc đặt tên ROLE_ / authority
    |
    v
Authentication.getAuthorities()
    |
    +-- HTTP: hasRole("ADMIN"), hasAuthority(...)
    |
    +-- Method: @PreAuthorize(...)
    |
    +-- Policy bổ sung: tenant, ownership, resource state
~~~

Ba nguyên tắc quan trọng nhất:

1. **Không đồng nhất group/claim của provider với quyền ứng dụng.** Chỉ ánh xạ bằng policy được kiểm soát, có xét issuer, registration và mức độ tin cậy.
2. **Mapper không trực tiếp có Access Token.** Nếu phải gọi API lấy group/permission, dùng delegating OAuth2/OIDC user service hoặc một authorization service phù hợp.
3. **Quyền gắn vào Authentication tại login có thể cũ theo thời gian.** Với dữ liệu nhạy cảm, bổ sung kiểm tra quyền tại service và chiến lược cập nhật/thu hồi thích hợp.

Khi tuân thủ các ranh giới trên, ánh xạ quyền tập trung giúp cấu hình Servlet SecurityFilterChain và method security rõ ràng hơn, đồng thời giảm nguy cơ phân quyền mâu thuẫn hoặc cấp quyền quá rộng từ dữ liệu bên ngoài.
