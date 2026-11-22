# Khác biệt authority từ OAuth2 Login với authority từ Bearer token trong Spring Security

## 1. Một người dùng, hai cách xác thực, hai nguồn authority

Một hệ thống Spring Boot thường phục vụ đồng thời:
- **Trang web đăng nhập qua OpenID Connect (OIDC)/OAuth2 Login**: browser được chuyển hướng tới Identity Provider (IdP), ứng dụng nhận authorization code, đổi token, dựng một phiên đăng nhập và truy cập các đường `/ui/**`.
- **REST API nhận Bearer access token**: mobile app, máy chủ khác hoặc SPA gọi `/api/**` với header `Authorization: Bearer ...`; Resource Server xác minh token, rồi dựng Authentication cho request.

Cả hai đường đều cho ra một đối tượng `Authentication` và tập `GrantedAuthority` để Spring Security kiểm tra. Nhưng **hai Authentication khác nhau về nguồn gốc, mục đích và những thông tin có thể tin cậy**.

Ví dụ:

```text
BROWSER FLOW
Browser ── OAuth2 Authorization Code / OIDC ──> IdP
            <─ code ─ token ─
Spring OAuth2 Login
  -> OAuth2User / OidcUser
  -> OAuth2AuthenticationToken
  -> authorities từ user / login access token / user mapping
  -> SecurityContext trong browser session

BEARER FLOW
HTTP client ── Authorization: Bearer <access-token> ──> API
Spring OAuth2 Resource Server
  -> verify JWT hoặc introspect opaque token
  -> JwtAuthenticationToken hoặc BearerTokenAuthentication
  -> authorities từ validated token/introspection + converter
  -> SecurityContext cho request API
```

**Điểm rất dễ nhầm:** OAuth2 Login **cũng có thể chứa `SCOPE_*`**. Tài liệu Spring Security 6.5 về `Mapping User Authorities` nêu authority của `OAuth2User`/`OidcUser` được tạo từ scopes của **access token nhận được khi Login**, có tiền tố `SCOPE_`. Ngoài ra còn có đặc biệt `OAUTH2_USER` hoặc `OIDC_USER`. Trong Resource Server, `SCOPE_*` thường đến từ `scope`/`scp` trong **Bearer access token hiện tại**, hoặc từ `scope` trong introspection response.

Vì vậy khác biệt không phải “Login chỉ có ROLE, Bearer chỉ có SCOPE”. Đúng hơn:

> **Authority là kết quả của một pipeline xác thực và mapping cụ thể. Tên authority giống nhau không bảo đảm cùng danh tính, cùng audience, cùng quyền nghiệp vụ hay cùng mức tin cậy.**

### Mục tiêu

Sau bài này, bạn có thể:
1. Phân biệt `OAuth2AuthenticationToken`, `JwtAuthenticationToken` và `BearerTokenAuthentication`.
2. Hiểu `OAUTH2_USER`, `OIDC_USER`, `SCOPE_reports.read`, `ROLE_ADMIN` và authority nội bộ như `APP_REPORT_READ`.
3. Giải thích vì sao access token được cấp cho **OAuth2 client** trong Login không tự biến thành API Bearer token mà một client khác gửi tới Resource Server.
4. Tùy chỉnh Login bằng `GrantedAuthoritiesMapper` hoặc `OAuth2UserService`/`OidcUserService`.
5. Tùy chỉnh JWT Bearer bằng `JwtAuthenticationConverter`/`JwtGrantedAuthoritiesConverter`; biết opaque Bearer dùng `OpaqueTokenIntrospector`.
6. Bảo vệ domain service khi có cả browser session và Bearer token, không để một authority string bị dùng sai qua hai cơ chế.
7. Viết integration tests với `MockMvc`, `oauth2Login()`, mock `JwtDecoder`, JUnit/Mockito; phân biệt test converter với kiểm thử IdP/token signature thật.

## 2. OAuth2 Login thực hiện việc gì?

Trong ứng dụng server-side web có `oauth2Login()`:

1. Browser bắt đầu đăng nhập ở `/oauth2/authorization/{registrationId}`.
2. Spring Security khởi tạo authorization request với state và redirect đến IdP.
3. Sau khi user đồng ý/xác thực, IdP redirect tới callback thông thường `/login/oauth2/code/{registrationId}` kèm authorization code.
4. Spring Security đổi code lấy token, gọi OIDC/UserInfo khi cần và tạo `OAuth2User` hoặc `OidcUser`.
5. Spring Security tạo `OAuth2AuthenticationToken` chứa principal, authorities và `authorizedClientRegistrationId`.
6. Kết quả thường được lưu trong `SecurityContext` gắn với **HTTP session** để các request browser tiếp theo sử dụng.

Đây là **đăng nhập người dùng vào ứng dụng client**. Nó không biến ứng dụng thành Resource Server chỉ vì IdP đã cấp một OAuth2 access token cho client.

### 2.1. Những authority mặc định bạn có thể gặp

| Nguồn | Ví dụ authority | Giải thích |
|---|---|---|
| OAuth2 Login, OAuth2User | `OAUTH2_USER` | Authority nhận diện principal là OAuth2User |
| OAuth2 Login, OIDC | `OIDC_USER` | Authority nhận diện principal là OidcUser |
| OAuth2 Login access token scopes | `SCOPE_openid`, `SCOPE_profile` hoặc scope khác được cấp | Đại diện phạm vi access token ứng dụng client có khi Login |
| OAuth2 Login mapping tùy chỉnh | `APP_REPORT_READ`, `ROLE_EMPLOYEE` | Chỉ có nếu team thiết lập mapping từ nguồn đáng tin |
| OAuth2 Resource Server JWT | `SCOPE_reports.read` | Mặc định đọc JWT `scope` hoặc `scp` sau bước token validation |
| OAuth2 Resource Server opaque | `SCOPE_reports.read` | Đọc `scope` từ introspection response |
| Resource Server custom converter | `ROLE_SUPPORT`, `PERM_report:approve` | Do converter/introspector được cấu hình riêng |

**Không nhầm `OIDC_USER` với quyền quản trị.** Nó chỉ báo lớp user/principal, không có nghĩa có quyền đọc tài liệu riêng tư hoặc truy cập API quản trị.

**Không nhầm `SCOPE_openid` với `ROLE_USER`.** `openid` là scope phục vụ xác thực OpenID Connect, không phải role nghiệp vụ “được phép đọc mọi dữ liệu”.

**Không tự suy ra `ROLE_ADMIN` từ email domain**. Chỉ cấp quyền từ IdP claim có cấu hình tin cậy, membership đã kiểm chứng hoặc hệ thống phân quyền nội bộ có thẩm quyền.

### 2.2. OAuth2User và OidcUser khác gì?

`OAuth2User` là principal OAuth 2.0 login có attributes (thường từ UserInfo hoặc provider API); `OidcUser` mở rộng thêm ID token và claims OIDC.

- `OAuth2UserAuthority` chứa attributes từ OAuth2 UserInfo; authority string thông dụng `OAUTH2_USER`.
- `OidcUserAuthority` chứa `OidcIdToken` và `OidcUserInfo`; authority string thông dụng `OIDC_USER`.
- Spring Security có thể thêm `SCOPE_*` từ access token scopes đi cùng OAuth2 Login.
- Có thể ánh xạ claims/groups sang `GrantedAuthority` nội bộ bằng `GrantedAuthoritiesMapper`.
- Nếu cần API của provider hoặc truy vấn role ngoài, `OAuth2UserService`/`OidcUserService` cho khả năng xử lý request, token và attributes linh hoạt hơn mapper chỉ nhận authorities.

**Điểm cần giữ:** ID token cho biết thông tin xác thực về user tại OIDC Client, **không phải** access token dành cho API. Không gửi ID token như một Bearer access token tới Resource Server chỉ vì cả hai có dạng JWT.

## 3. Resource Server xử lý Bearer token thế nào?

Một request:

```http
GET /api/reports/101 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
```

không phải OAuth2 Login. Đây là yêu cầu **access token authentication** của Resource Server:

- **JWT Bearer**: `BearerTokenAuthenticationFilter` trích token, `JwtDecoder` xác minh chữ ký và claims cần thiết; `JwtAuthenticationConverter` dựng `JwtAuthenticationToken` cùng authorities.
- **Opaque Bearer**: Resource Server introspect token với Authorization Server; nếu `active=true` và request hợp lệ, thường tạo `BearerTokenAuthentication` với `OAuth2AuthenticatedPrincipal` và authorities từ introspection.

Đối với JWT access token:

```json
{
  "iss": "https://idp.example.invalid",
  "sub": "alice",
  "aud": ["report-api"],
  "scope": "reports.read reports.approve",
  "exp": 1893456000
}
```

Trong cấu hình thông dụng của Spring Security 6.5, authorities được tạo là:

```text
SCOPE_reports.read
SCOPE_reports.approve
```

Một token khác dùng claim dạng array:

```json
{
  "sub": "alice",
  "scp": ["reports.read", "reports.approve"]
}
```

`JwtGrantedAuthoritiesConverter` mặc định có thể lấy scopes từ `scope` hoặc `scp` và dùng tiền tố `SCOPE_`. Nhưng **không có nghĩa mọi JWT do bất kỳ IdP cấp đều chứa scope đúng chuẩn**; nhiều provider dùng claim `roles`, `groups`, `realm_access` hoặc một JSON object tùy chỉnh. Khi đó phải cấu hình converter, không đoán tên claim.

### 3.1. Ba lớp bắt buộc trước khi tin SCOPE_

1. **Token hợp lệ**: chữ ký, issuer `iss`, thời hạn `exp`, `nbf`, thuật toán khóa và revocation policy được cấu hình.
2. **Audience đúng**: `aud` phải chứa chính API/resource server này. Token cấp để gọi API B không tự được chấp nhận ở API A. Spring Boot hỗ trợ property `spring.security.oauth2.resourceserver.jwt.audiences`.
3. **Scope/action/object**: `SCOPE_reports.read` cho phép **hành động báo cáo được định nghĩa**, không tự có nghĩa tất cả tenants hoặc mọi report ID đều được đọc.

Nếu sai audience hoặc issuer, **không được tạo một `Authentication` “đã xác thực” chỉ vì JWT có payload đọc được**. Base64 decoding JWT không phải token validation.

### 3.2. Opaque token không phải JWT

Opaque Bearer có thể chỉ là một chuỗi không đọc được; Resource Server hỏi introspection endpoint. Spring Security chuyển `scope` từ introspection thành `SCOPE_*` theo mặc định, nhưng principal/token type thường là `BearerTokenAuthentication`, không phải `JwtAuthenticationToken`.

Nếu policy bean viết `authentication instanceof JwtAuthenticationToken` để cho phép JWT, **opaque Bearer có thể bị deny** cho đến khi bổ sung nhánh phù hợp. Đây là lựa chọn cố ý của policy; đừng vô tình coi mọi Bearer là JWT.

## 4. So sánh authority theo từng bước

| Khía cạnh | OAuth2 Login | JWT Bearer | Opaque Bearer |
|---|---|---|---|
| HTTP authentication | Authorization Code + browser login | Authorization: Bearer access JWT | Authorization: Bearer opaque |
| Principal | `OAuth2User` hoặc `OidcUser` | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Authentication thường gặp | `OAuth2AuthenticationToken` | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| SecurityContext | Thường trong server session | Thường request-scoped/stateless | Thường request-scoped/stateless |
| Default authority đặc trưng | `OAUTH2_USER` / `OIDC_USER` | `SCOPE_*` từ `scope`/`scp` | `SCOPE_*` từ introspection |
| Có thể có SCOPE_? | **Có**, từ access token của login | **Có**, từ Bearer JWT | **Có**, từ introspection |
| Mapping hook | `GrantedAuthoritiesMapper`, `OAuth2UserService`/`OidcUserService` | `JwtAuthenticationConverter` | `OpaqueTokenIntrospector` / custom token authentication converter |
| Token đang được kiểm tra trực tiếp cho request? | Browser thường dùng session sau login; token được xử lý trong login flow | JWT gửi ở request đó | Opaque token gửi ở request đó |
| Role nghiệp vụ | Phải mapping/lookup explicit | Có thể mapping từ trusted claims | Có thể mapping từ trusted introspection |
| Bảo vệ chống tenant leak | Cần server membership/object guard | Cần server membership/object guard | Cần server membership/object guard |
| Khi token cũ/revoke | Session authority có thể stale | JWT vẫn có thể hợp lệ tới hạn `exp` theo chính sách revoke | Introspection có thể phản ánh active state, phụ thuộc cache/AS |
| Cần OIDC ID token? | Khi chọn OIDC Login | **Không**; API cần access token | **Không** |

Một login session và một Bearer request **có thể có cùng string `SCOPE_reports.read`**, nhưng string ấy không cho biết token nào mang nó, ai là audience, hay business policy nào đã cấp quyền.

## 5. Spring Security kiểm tra chuỗi authority thế nào?

Spring Security dùng `GrantedAuthority.getAuthority()` làm một chuỗi, không tự gắn nhãn “đến từ Login” hay “đến từ Bearer”. Ví dụ:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Report read(...) { ... }
```

Kiểm tra string `SCOPE_reports.read` trên Authentication hiện tại. Nếu Login cũng có string đó, biểu thức **có thể pass** cho user trong browser session. Điều này đúng về mặt API, nhưng **có thể sai về security policy** nếu developer muốn scope bắt buộc phải đến từ một **Bearer access token dành cho report-api**.

### 5.1. hasRole vs hasAuthority

```java
hasAuthority("SCOPE_reports.read")
hasAuthority("APP_REPORT_READ")
hasRole("REPORT_ADMIN")
```

Ba kiểm tra khác nhau:
- `hasAuthority("SCOPE_reports.read")` khớp đúng string.
- `hasAuthority("APP_REPORT_READ")` khớp đúng permission nội bộ.
- `hasRole("REPORT_ADMIN")` theo prefix mặc định kiểm tra `ROLE_REPORT_ADMIN`.

Không dùng `hasRole("SCOPE_reports.read")` để kiểm tra scope; nó có thể tìm `ROLE_SCOPE_reports.read`. Ngược lại, `SCOPE_reports.read` không biến thành `ROLE_ADMIN` nếu không có custom mapping.

### 5.2. Không auto-map OAuth scopes sang vai trò quản trị

Một kiểu cấu hình rủi ro:

```java
// PHẢN VÍ DỤ: biến bất kỳ token scope admin thành application admin.
jwtAuthorities.setAuthorityPrefix("ROLE_");
```

Thay prefix `SCOPE_` thành `ROLE_` **chỉ đổi tên string**, không tự chứng minh scope do provider đáng tin cấp đúng hành động hoặc audience. Nếu ứng dụng có nhầm scope/role giữa nhiều clients, cách này có thể tạo quyền quá rộng.

Nếu cần custom authorities từ JWT, validate token, cố định trusted issuer/audience, allowlist values, thêm roles với prefix/namespaces riêng; không map toàn bộ claim chưa kiểm chứng thành ROLE_ADMIN.

### 5.3. Quyền người dùng vs quyền ứng dụng

OAuth2 access token có thể đại diện:
- Một **end-user delegated access**: user đã đồng ý hoặc IdP đã cấp quyền cho client.
- Một **client credentials token**: workload/application được cấp quyền mà **không có user tương tác**.

Không suy luận từ `sub` hoặc `SCOPE_*` rằng chắc chắn có một user đang thao tác ở browser. Nếu workflow yêu cầu user presence, dùng claim/grant type/assurance phù hợp và policy theo loại principal. Nếu workload cần quyền hệ thống, gán service identity riêng, không tự nhập vai user.

## 6. Hai cửa mapping khác nhau: điểm sửa đúng

### 6.1. OAuth2 Login: GrantedAuthoritiesMapper

`GrantedAuthoritiesMapper` nhận các authorities đã thu được khi Login và trả một collection mới. Cơ chế này phù hợp khi:
- Sẵn có `OidcUserAuthority` hoặc `OAuth2UserAuthority` với claims/attributes đủ để map.
- Không cần gọi thêm API bên ngoài.
- Muốn ánh xạ role ứng dụng nội bộ độc lập khỏi scopes kỹ thuật.

Ví dụ chỉ cấp `APP_REPORT_READ` khi **OIDC ID token từ issuer được allowlist** mang claim ứng dụng đã được cấu hình đáng tin:

```java
@Bean
GrantedAuthoritiesMapper loginAuthoritiesMapper() {
    return authorities -> {
        Set<GrantedAuthority> result = new HashSet<>(authorities);
        for (GrantedAuthority a : authorities) {
            if (a instanceof OidcUserAuthority oidc) {
                var claims = oidc.getIdToken().getClaims();
                if ("https://idp.example.invalid".equals(
                        claims.get("iss"))
                    && "viewer".equals(claims.get("report_access"))) {
                    result.add(new SimpleGrantedAuthority(
                        "APP_REPORT_READ"));
                }
            }
        }
        return result;
    };
}
```

Đoạn trên được lắp trong demo ở phần 8. Claim `report_access` là **ví dụ quy ước do tổ chức thiết kế**, không phải claim chuẩn của OAuth2/OIDC. Chỉ tin claim đó nếu IdP đã được cấu hình để phát từ nguồn role đáng tin (và ID token đã được xác minh); không tin dữ liệu do user tự chọn qua profile UI.

Trong thực tế, phải ràng buộc **registration/client**, tenant, trusted issuer và policy version. Check string `iss` một lần trong mapper **không thay thế** validation ID token bởi OIDC login stack. Nếu không đủ điều kiện → không cấp `APP_REPORT_READ`.

### 6.2. OAuth2 Login: Delegating OAuth2UserService/OidcUserService

Nếu quyền nằm ở API khác của IdP, role service nội bộ hoặc project memberships, `GrantedAuthoritiesMapper` có thể không đủ vì nó chỉ nhận authorities. Dùng `OAuth2UserService<OAuth2UserRequest, OAuth2User>` hoặc `OAuth2UserService<OidcUserRequest, OidcUser>`, delegate đến default service, rồi **tra cứu role đáng tin** dựa trên immutable issuer/subject và access token phù hợp.

Flow mẫu:

```text
OAuth2 Login complete
  -> DefaultOidcUserService load user + ID token/UserInfo
  -> Membership service lookup using trusted (issuer, sub)
  -> Verified application role(s)
  -> return OidcUser with mapped authorities
  -> OAuth2AuthenticationToken in session
```

Không map `email_verified=true` thành global admin; email có thể đổi, domain có thể thuộc nhiều tổ chức. Bất kỳ network lookup nào cũng cần timeout, bounded retry, cache/revoke policy và **fail-closed** khi không xác minh được quyền.

### 6.3. JWT Bearer: JwtGrantedAuthoritiesConverter

JWT Bearer không đi qua `GrantedAuthoritiesMapper` của OAuth2 Login. Dùng converter tại resource server:

```java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();
// Mặc định: scope hoặc scp -> SCOPE_<scope>

JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(scopes);
```

Nếu provider dùng claim tùy chỉnh:

```java
JwtGrantedAuthoritiesConverter custom =
    new JwtGrantedAuthoritiesConverter();
custom.setAuthoritiesClaimName("permissions");
custom.setAuthorityPrefix("PERM_");
```

Đây là mẫu minh họa: nếu claim `permissions` chứa `report:read`, converter có thể tạo `PERM_report:read`. Cần kiểm chứng schema, delimiter và nguồn phát claim. Nếu muốn giữ cả `scope` và `permissions`, phải **kết hợp** hai converters có chủ đích; chỉ thay claim name có thể làm mất authorities từ scopes mặc định.

### 6.4. Opaque Bearer: OpaqueTokenIntrospector

Với opaque token, `JwtAuthenticationConverter` **không được gọi**. Cấu hình `oauth2ResourceServer(o -> o.opaqueToken(...))` với introspector; custom `OpaqueTokenIntrospector` có thể lấy claims, scopes và verified metadata từ response để tạo `OAuth2AuthenticatedPrincipal` cùng authorities. Không decode opaque token như JWT hoặc tự tin scopes lấy từ raw header.

## 7. Kiến trúc hai security chains: tránh trộn session và API Bearer

Một ứng dụng phục vụ:
- `/ui/reports/**`: browser session, OAuth2 Login, role ứng dụng `APP_REPORT_READ`/`APP_REPORT_APPROVE`.
- `/api/reports/**`: stateless Bearer JWT, scope `SCOPE_reports.read`/`SCOPE_reports.approve`.

Mỗi nhóm phải có **cơ chế xác thực và authority requirement rõ**, không lấy OAuth Login session làm chứng chỉ Bearer token cho API.

```text
Request
   |
   +-- path /api/** ?
   |     |
   |     +-- @Order(1) API SecurityFilterChain
   |            - OAuth2 Resource Server JWT
   |            - stateless
   |            - require SCOPE_reports.read / approve
   |            - anyRequest denyAll
   |
   +-- otherwise @Order(2) browser SecurityFilterChain
         - OAuth2 Login, HttpSession
         - require APP_REPORT_READ / APPROVE
         - CSRF for mutations
         - other paths denyAll
```

**Thứ tự quan trọng:** Spring Security chọn **chain đầu tiên khớp** request, không lấy giao mọi chain. `anyRequest().denyAll()` trong API chain chỉ bảo vệ requests đã vào API chain; browser fallback phải bao phủ phần còn lại.

Với API chỉ dùng Bearer header (không cookie authentication) và không tự động dùng browser credentials, có thể disable CSRF **chỉ ở API chain** sau threat modeling. Browser chain vẫn cần CSRF cho POST/PUT/DELETE.

### 7.1. Service-level policy vẫn cần kiểm tra Authentication type

Bởi vì `hasAuthority(...)` chỉ kiểm tra string, một ứng dụng quan trọng nên phân biệt **authentication mechanism** tại domain boundary nếu cùng service được gọi từ cả hai đường:

```java
if (authentication instanceof OAuth2AuthenticationToken) {
    return has(authentication, "APP_REPORT_READ");
}
if (authentication instanceof JwtAuthenticationToken) {
    return has(authentication, "SCOPE_reports.read");
}
return false; // Unknown authentication kind: deny.
```

Đây là mẫu logic; project đầy đủ dùng `ReportPolicy`, thêm tenant membership và canonical resource lookup.

Điều này hữu ích khi endpoint từ scheduler, message consumer hoặc một chain khác vô tình gọi cùng service. **Không dựa duy nhất vào tên authority để cấp quyền cho mọi Authentication type.**

## 8. Dự án Java 17 / Spring Boot 3.5.6 minh họa hai authority pipelines

Ví dụ này chạy ứng dụng Servlet/MVC Spring Boot có:
1. Hai `SecurityFilterChain` và `@Order`.
2. `oauth2Login()` có OIDC `GrantedAuthoritiesMapper`.
3. `oauth2ResourceServer().jwt()` dùng `JwtAuthenticationConverter`.
4. `ReportPolicy` chấp nhận **OAuth2AuthenticationToken + APP_*** hoặc **JwtAuthenticationToken + SCOPE_***; không tự cho opaque token, Basic hay anonymous đi qua.
5. Repository RAM chứa tenant canonical và membership.
6. `MockMvc` tests mô phỏng OAuth Login và Bearer claims (không cần IdP thật).

**Quan trọng về môi trường:** `idp.example.invalid` là domain minh họa không có IdP thật. Project có thể chạy và integration tests có thể thử authorization bằng mocks; **OAuth2 redirect login thực và JWT signature verification thực cần cấu hình IdP/JWKS/credentials của môi trường triển khai**. Đừng hiểu unit tests dưới đây là kiểm định cryptographic trust thực tế.

### 8.1. Cây file

```text
oauth2-authorities-demo/
  pom.xml
  src/main/resources/application.yml
  src/main/java/com/example/authorities/
    AuthoritiesApplication.java
    SecurityConfiguration.java
    Report.java
    ReportCatalog.java
    ReportPolicy.java
    ReportService.java
    ReportController.java
  src/test/java/com/example/authorities/
    AuthoritiesIntegrationTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>oauth2-authorities-demo</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

`spring-boot-starter-oauth2-client` và `spring-boot-starter-oauth2-resource-server` là **hai khả năng riêng**. Phụ thuộc thứ hai cung cấp resource server/JWT validation; khả năng login không được suy ra tự động khi chỉ có JWT resource server.

### 8.3. application.yml

**`src/main/resources/application.yml`**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            client-id: example-web-client
            client-secret: development-only-not-real
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
            provider: demo
        provider:
          demo:
            authorization-uri: https://idp.example.invalid/authorize
            token-uri: https://idp.example.invalid/token
            user-info-uri: https://idp.example.invalid/userinfo
            user-name-attribute: sub
            jwk-set-uri: https://idp.example.invalid/jwks
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid
          jwk-set-uri: https://idp.example.invalid/jwks
          audiences: report-api
```

Các URI trên là **khung cấu hình để app khởi động và chạy tests cục bộ**, không phải dịch vụ có thật. Khi kết nối IdP:
- Đăng ký OAuth2 Client và redirect URI thực; bảo vệ client secret bằng secret manager/environment.
- Xác minh OIDC ID token issuer, signature và audience client; provider metadata phải khớp deployment.
- Cung cấp `issuer-uri`, `jwk-set-uri` và `audiences` của **access token dành cho report-api**, không dùng ID token làm Bearer API token.
- Không cho browser/HTTP caller tự quyết định `issuer-uri` hoặc `audiences`.
- Với nhiều issuers, dùng `AuthenticationManagerResolver` hoặc multi-tenant strategy đã review; map `(issuer, subject)` sang internal user ID ổn định.

### 8.4. Main class

**`src/main/java/com/example/authorities/AuthoritiesApplication.java`**

```java
package com.example.authorities;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthoritiesApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthoritiesApplication.class, args);
    }
}
```

### 8.5. SecurityConfiguration

**`src/main/java/com/example/authorities/SecurityConfiguration.java`**

```java
package com.example.authorities;

import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http,
            JwtAuthenticationConverter jwtConverter) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/{id}")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST,
                    "/api/reports/{id}/approve")
                    .hasAuthority("SCOPE_reports.approve")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // API này chỉ xác thực bằng Bearer header, không dùng cookie.
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth -> oauth
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtConverter)))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http,
            GrantedAuthoritiesMapper loginMapper) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/",
                    "/login/**", "/oauth2/**", "/error")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/ui/reports/{id}")
                    .hasAuthority("APP_REPORT_READ")
                .requestMatchers(HttpMethod.POST,
                    "/ui/reports/{id}/approve")
                    .hasAuthority("APP_REPORT_APPROVE")
                .anyRequest().denyAll()
            )
            .oauth2Login(oauth -> oauth.userInfoEndpoint(
                userInfo -> userInfo.userAuthoritiesMapper(loginMapper)))
            .build();
    }

    @Bean
    GrantedAuthoritiesMapper loginAuthoritiesMapper() {
        return authorities -> {
            Set<GrantedAuthority> mapped =
                new LinkedHashSet<>(authorities);

            for (GrantedAuthority authority : authorities) {
                if (authority instanceof OidcUserAuthority oidc) {
                    var claims = oidc.getIdToken().getClaims();
                    boolean trustedIssuer =
                        "https://idp.example.invalid".equals(
                            claims.get("iss"));
                    if (!trustedIssuer) {
                        continue;
                    }
                    String role = String.valueOf(
                        claims.get("report_access"));
                    if ("viewer".equals(role)) {
                        mapped.add(new SimpleGrantedAuthority(
                            "APP_REPORT_READ"));
                    }
                    if ("approver".equals(role)) {
                        mapped.add(new SimpleGrantedAuthority(
                            "APP_REPORT_READ"));
                        mapped.add(new SimpleGrantedAuthority(
                            "APP_REPORT_APPROVE"));
                    }
                }
            }
            return mapped;
        };
    }

    @Bean
    JwtAuthenticationConverter jwtConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();
        // Default scope/scp -> SCOPE_*, không tự biến thành ROLE_*.
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(scopes);
        return converter;
    }
}
```

**Phân tích:**
1. `@Order(1)` API chain chỉ áp `/api/**`, yêu cầu Bearer JWT và scopes `reports.read`/`reports.approve`. Request không match những API operations này sẽ deny.
2. `@Order(2)` browser chain là catch-all cho phần còn lại, cho các URL login/callback và UI GET/POST được xét cụ thể. `oauth2Login` tạo session khi flow thật thành công.
3. Chỉ API chain tắt CSRF vì ví dụ API chỉ chấp nhận **Bearer header**, không dựa vào browser cookie. Browser chain **giữ CSRF mặc định**. Đổi cơ chế xác thực cần đánh giá lại.
4. `GrantedAuthoritiesMapper` chỉ map OIDC ID token từ issuer allowlist và `report_access` đã tin cậy. Nó vẫn giữ các authorities sẵn có (như `OIDC_USER`, `SCOPE_openid`), nhưng **không coi những authorities đó là quyền báo cáo**.
5. `JwtAuthenticationConverter` tiếp tục dùng mặc định scope/scp → `SCOPE_*`; không tự map ID token role của Login. API yêu cầu audience phù hợp trong `application.yml`.
6. Mapper ví dụ **không tự cấp role cho OAuth2 Login không có OIDC ID token**: những provider đó cần trusted user/group service khác.
7. Mọi path chưa được phê duyệt trong từng chain đều deny, kể cả admin.
8. Role claim `report_access` là **private convention** của bài, không phải behavior có sẵn ở Spring Security hay OIDC.

### 8.6. Report và ReportCatalog — tenant là dữ liệu server-side

**`src/main/java/com/example/authorities/Report.java`**

```java
package com.example.authorities;

public record Report(
    Long id, String tenant, String owner,
    String title, boolean approved) {}
```

**`src/main/java/com/example/authorities/ReportCatalog.java`**

```java
package com.example.authorities;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Repository;

@Repository
public class ReportCatalog {
    private final ConcurrentMap<Long, Report> reports =
        new ConcurrentHashMap<>();

    // Demo single trusted IdP: users mapped by sub.
    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice", "bob"),
        "t2", Set.of("carol")
    );

    private final AtomicInteger approvals = new AtomicInteger();

    public ReportCatalog() {
        reset();
    }

    public synchronized void reset() {
        reports.clear();
        reports.put(101L, new Report(
            101L, "t1", "alice", "Revenue", false));
        reports.put(102L, new Report(
            102L, "t1", "bob", "Costs", false));
        reports.put(201L, new Report(
            201L, "t2", "carol", "South division", false));
        approvals.set(0);
    }

    public Report find(Long id) {
        return id == null ? null : reports.get(id);
    }

    public boolean isMember(String tenant, String principal) {
        Set<String> inTenant = members.get(tenant);
        return inTenant != null && principal != null
            && inTenant.contains(principal);
    }

    public synchronized Report approve(Long id) {
        Report old = find(id);
        if (old == null) return null;
        Report updated = new Report(
            old.id(), old.tenant(), old.owner(),
            old.title(), true);
        reports.put(id, updated);
        approvals.incrementAndGet();
        return updated;
    }

    public int approvals() {
        return approvals.get();
    }
}
```

Dữ liệu in-memory là fixture để kiểm thử, không phải database. Production cần source of truth tenant membership, subject mapping theo `issuer+sub` và DML `UPDATE ... WHERE tenant_id=? AND ...`. Không đưa tenant/owner từ body làm cơ sở cấp quyền.

### 8.7. ReportPolicy — phân biệt cơ chế xác thực trong domain service

**`src/main/java/com/example/authorities/ReportPolicy.java`**

```java
package com.example.authorities;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("reportPolicy")
public class ReportPolicy {
    private final ReportCatalog catalog;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public ReportPolicy(ReportCatalog catalog) {
        this.catalog = catalog;
    }

    private static boolean has(Authentication auth, String value) {
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (value.equals(a.getAuthority())) return true;
        }
        return false;
    }

    private boolean trustedMember(Authentication auth, Long reportId) {
        if (auth == null || !auth.isAuthenticated()
                || trust.isAnonymous(auth)) {
            return false;
        }
        Report report = catalog.find(reportId);
        return report != null
            && catalog.isMember(report.tenant(), auth.getName());
    }

    public boolean canRead(Authentication auth, Long reportId) {
        if (!trustedMember(auth, reportId)) return false;

        if (auth instanceof OAuth2AuthenticationToken) {
            return has(auth, "APP_REPORT_READ");
        }
        if (auth instanceof JwtAuthenticationToken) {
            return has(auth, "SCOPE_reports.read");
        }
        return false; // Basic, anonymous, opaque, unknown => deny.
    }

    public boolean canApprove(Authentication auth, Long reportId) {
        if (!trustedMember(auth, reportId)) return false;

        if (auth instanceof OAuth2AuthenticationToken) {
            return has(auth, "APP_REPORT_APPROVE");
        }
        if (auth instanceof JwtAuthenticationToken) {
            return has(auth, "SCOPE_reports.approve");
        }
        return false;
    }
}
```

Vì sao policy phân nhánh theo Authentication type?
- Một Login principal tình cờ có `SCOPE_reports.read` từ login client's access token **không được coi là một Bearer access token cho report-api**.
- Một JWT có string `APP_REPORT_READ` do claim mapping khác cũng **không** tự đi theo nhánh browser.
- Một opaque Bearer không đi vào nhánh JWT cho tới khi hệ thống quyết định cho phép và triển khai nhánh `BearerTokenAuthentication` có kiểm soát.
- Membership tenant được kiểm tra **trước** khi xét authorities; tên user/sub của demo đến từ single IdP. Production phải dùng internal ID được map từ issuer+sub, không dựa vào tên hiển thị/email.

**Giới hạn:** Checking runtime type là một tầng defense-in-depth của demo, không thay thế validation token, issuer/audience, session policy hay việc giới hạn route bằng SecurityFilterChain.

### 8.8. Service và Controller

**`src/main/java/com/example/authorities/ReportService.java`**

```java
package com.example.authorities;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ReportCatalog catalog;

    public ReportService(ReportCatalog catalog) {
        this.catalog = catalog;
    }

    @PreAuthorize(
        "@reportPolicy.canRead(authentication, #id)"
    )
    public Report read(@P("id") Long id) {
        return catalog.find(id);
    }

    @PreAuthorize(
        "@reportPolicy.canApprove(authentication, #id)"
    )
    public Report approve(@P("id") Long id) {
        Report changed = catalog.approve(id);
        if (changed == null) {
            throw new AccessDeniedException("Resource changed");
        }
        return changed;
    }
}
```

**`src/main/java/com/example/authorities/ReportController.java`**

```java
package com.example.authorities;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/ui/reports/{id}")
    public Report browserRead(@PathVariable("id") Long id) {
        return service.read(id);
    }

    @PostMapping("/ui/reports/{id}/approve")
    public Report browserApprove(@PathVariable("id") Long id) {
        return service.approve(id);
    }

    @GetMapping("/api/reports/{id}")
    public Report apiRead(@PathVariable("id") Long id) {
        return service.read(id);
    }

    @PostMapping("/api/reports/{id}/approve")
    public Report apiApprove(@PathVariable("id") Long id) {
        return service.approve(id);
    }
}
```

`@EnableMethodSecurity` khiến `@PreAuthorize` chạy khi controller gọi Spring-managed service proxy. Nhờ vậy ngay cả một call từ job/bean khác, nếu Authentication không thuộc loại đã phê duyệt hoặc thiếu membership, service cũng deny.

Không dùng `@PostAuthorize` làm chốt duy nhất cho approve vì side effect đã chạy trước post-check. Trong production, dùng guarded DML và transaction/optimistic locking.

## 9. Integration tests: MockMvc phân biệt Login và Bearer

Để không cần một IdP có thật, chúng ta:
- Dùng `oauth2Login()` test postprocessor để tạo `OAuth2AuthenticationToken` có attributes/authorities kiểm soát trong test.
- Dùng `@MockitoBean JwtDecoder` và **Bearer header thật ở MockMvc** để chạy Resource Server filter và `JwtAuthenticationConverter`. Mock decoder trả Jwt claims đã dựng; không phải chữ ký được kiểm thật.
- Kiểm thử trực tiếp `GrantedAuthoritiesMapper` để chắc chắn verified OIDC claim được map đúng; test postprocessor `oauth2Login()` **không tự chạy mapper như một login callback thật**.
- Kiểm tra những quyền bị deny ở UI/API, không chỉ happy path.

**`src/test/java/com/example/authorities/AuthoritiesIntegrationTest.java`**

```java
package com.example.authorities;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthoritiesIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ReportCatalog catalog;
    @Autowired GrantedAuthoritiesMapper loginMapper;
    @Autowired JwtAuthenticationConverter jwtConverter;

    @MockitoBean JwtDecoder jwtDecoder;

    private static Jwt jwt(String token, String scope) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim("iss", "https://idp.example.invalid")
            .claim("aud", List.of("report-api"))
            .claim("scope", scope)
            .issuedAt(now)
            .expiresAt(now.plusSeconds(600))
            .build();
    }

    private static Jwt jwtWithScp(String token) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim("iss", "https://idp.example.invalid")
            .claim("aud", List.of("report-api"))
            .claim("scp", List.of("reports.read"))
            .issuedAt(now)
            .expiresAt(now.plusSeconds(600))
            .build();
    }

    private static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.OAuth2LoginRequestPostProcessor
    login(String... authorities) {
        var granted = java.util.Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toArray(GrantedAuthority[]::new);
        return oauth2Login()
            .attributes(attrs -> attrs.put("sub", "alice"))
            .authorities(granted);
    }

    private static org.springframework.test.web.servlet.request.RequestPostProcessor
    bearer(String token) {
        return request -> {
            request.addHeader(
                HttpHeaders.AUTHORIZATION, "Bearer " + token);
            return request;
        };
    }

    @BeforeEach
    void setup() {
        catalog.reset();

        when(jwtDecoder.decode("api-read"))
            .thenReturn(jwt("api-read", "reports.read"));
        when(jwtDecoder.decode("api-approve"))
            .thenReturn(jwt("api-approve", "reports.approve"));
        when(jwtDecoder.decode("api-both"))
            .thenReturn(jwt("api-both",
                "reports.read reports.approve"));
        when(jwtDecoder.decode("api-oidc-scopes"))
            .thenReturn(jwt("api-oidc-scopes",
                "openid profile"));
        when(jwtDecoder.decode("api-scp"))
            .thenReturn(jwtWithScp("api-scp"));
        when(jwtDecoder.decode("api-invalid"))
            .thenThrow(new BadJwtException("Invalid token"));
    }

    private static boolean has(
            java.util.Collection<? extends GrantedAuthority> values,
            String expected) {
        return values.stream()
            .anyMatch(a -> expected.equals(a.getAuthority()));
    }

    @Test
    void loginWithMappedAppReadCanReadUi() throws Exception {
        mvc.perform(get("/ui/reports/101")
                .with(login("APP_REPORT_READ")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Revenue"));
    }

    @Test
    void loginWithoutAppPermissionCannotReadUi() throws Exception {
        mvc.perform(get("/ui/reports/101")
                .with(login("OIDC_USER", "SCOPE_openid")))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginScopeAloneDoesNotReplaceAppReadRole()
            throws Exception {
        mvc.perform(get("/ui/reports/101")
                .with(login("SCOPE_reports.read")))
            .andExpect(status().isForbidden());
    }

    @Test
    void browserAppRoleCannotApproveWithoutApproveRole()
            throws Exception {
        mvc.perform(post("/ui/reports/101/approve")
                .with(login("APP_REPORT_READ"))
                .with(csrf()))
            .andExpect(status().isForbidden());
        assertEquals(0, catalog.approvals());
    }

    @Test
    void browserApproverCanApproveWithCsrf() throws Exception {
        mvc.perform(post("/ui/reports/101/approve")
                .with(login(
                    "APP_REPORT_READ", "APP_REPORT_APPROVE"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.approved").value(true));
        assertEquals(1, catalog.approvals());
    }

    @Test
    void browserApproverWithoutCsrfIsDenied() throws Exception {
        mvc.perform(post("/ui/reports/101/approve")
                .with(login(
                    "APP_REPORT_READ", "APP_REPORT_APPROVE")))
            .andExpect(status().isForbidden());
        assertEquals(0, catalog.approvals());
    }

    @Test
    void browserUserCannotReadOtherTenant() throws Exception {
        mvc.perform(get("/ui/reports/201")
                .with(login("APP_REPORT_READ")))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiWithReadScopeCanRead() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-read")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void apiWithScpArrayCanRead() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-scp")))
            .andExpect(status().isOk());
    }

    @Test
    void apiWithOnlyApproveScopeCannotRead() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-approve")))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiOpenidScopesDoNotGrantReportAccess()
            throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-oidc-scopes")))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiReadScopeDoesNotGrantApprove() throws Exception {
        mvc.perform(post("/api/reports/101/approve")
                .with(bearer("api-read")))
            .andExpect(status().isForbidden());
        assertEquals(0, catalog.approvals());
    }

    @Test
    void apiApproveScopeCanApproveWithoutBrowserCsrf()
            throws Exception {
        mvc.perform(post("/api/reports/101/approve")
                .with(bearer("api-approve")))
            .andExpect(status().isOk());
        assertEquals(1, catalog.approvals());
    }

    @Test
    void apiBothScopesCanReadAndApprove() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-both")))
            .andExpect(status().isOk());
        mvc.perform(post("/api/reports/101/approve")
                .with(bearer("api-both")))
            .andExpect(status().isOk());
    }

    @Test
    void apiMissingBearerIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBearerIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports/101")
                .with(bearer("api-invalid")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiCannotReadOtherTenantWithValidScope()
            throws Exception {
        mvc.perform(get("/api/reports/201")
                .with(bearer("api-read")))
            .andExpect(status().isForbidden());
    }

    @Test
    void pathNameAdminDoesNotGrantUnlistedRoute()
            throws Exception {
        mvc.perform(get("/api/admin/diagnostics")
                .with(bearer("api-both")))
            .andExpect(status().isForbidden());
    }

    @Test
    void oidcTrustedClaimMapsAppRead() {
        Instant now = Instant.now();
        OidcIdToken idToken = new OidcIdToken(
            "id-token", now, now.plusSeconds(600),
            Map.of("sub", "alice",
                   "iss", "https://idp.example.invalid",
                   "report_access", "viewer"));
        var mapped = loginMapper.mapAuthorities(
            List.of(new OidcUserAuthority(idToken)));
        assertTrue(has(mapped, "APP_REPORT_READ"));
        assertFalse(has(mapped, "APP_REPORT_APPROVE"));
    }

    @Test
    void oidcApproverClaimMapsBothAppPermissions() {
        Instant now = Instant.now();
        OidcIdToken idToken = new OidcIdToken(
            "id-token", now, now.plusSeconds(600),
            Map.of("sub", "alice",
                   "iss", "https://idp.example.invalid",
                   "report_access", "approver"));
        var mapped = loginMapper.mapAuthorities(
            List.of(new OidcUserAuthority(idToken)));
        assertTrue(has(mapped, "APP_REPORT_READ"));
        assertTrue(has(mapped, "APP_REPORT_APPROVE"));
    }

    @Test
    void untrustedIssuerDoesNotMapAppRole() {
        Instant now = Instant.now();
        OidcIdToken idToken = new OidcIdToken(
            "id-token", now, now.plusSeconds(600),
            Map.of("sub", "alice",
                   "iss", "https://unexpected.example.invalid",
                   "report_access", "approver"));
        var mapped = loginMapper.mapAuthorities(
            List.of(new OidcUserAuthority(idToken)));
        assertFalse(has(mapped, "APP_REPORT_READ"));
        assertFalse(has(mapped, "APP_REPORT_APPROVE"));
    }

    @Test
    void oauthScopeIsNotAutomaticallyBusinessAppRole() {
        var mapped = loginMapper.mapAuthorities(List.of(
            new SimpleGrantedAuthority("SCOPE_reports.read"),
            new SimpleGrantedAuthority("OAUTH2_USER")));
        assertTrue(has(mapped, "SCOPE_reports.read"));
        assertFalse(has(mapped, "APP_REPORT_READ"));
    }

    @Test
    void jwtConverterCreatesScopeAuthorities() {
        var authentication =
            jwtConverter.convert(jwt("unit", "reports.read"));
        assertTrue(has(
            authentication.getAuthorities(), "SCOPE_reports.read"));
        assertFalse(has(
            authentication.getAuthorities(), "APP_REPORT_READ"));
    }

    @Test
    void jwtConverterUsesScpClaim() {
        var authentication =
            jwtConverter.convert(jwtWithScp("unit-scp"));
        assertTrue(has(
            authentication.getAuthorities(), "SCOPE_reports.read"));
    }

    @Test
    void jwtConverterDoesNotInventRolesFromScopes() {
        var authentication =
            jwtConverter.convert(jwt("unit", "openid profile"));
        assertFalse(has(
            authentication.getAuthorities(), "ROLE_ADMIN"));
        assertFalse(has(
            authentication.getAuthorities(), "SCOPE_reports.read"));
    }
}
```

**Ghi chú QA quan trọng:** `@MockitoBean` có trong Spring Framework 6.2 (Boot 3.5 dùng). Test `JwtDecoder` stub xác nhận route Bearer, converter và authorization decisions, **không chứng minh token đã được validate chữ ký/issuer/audience thật**. Các test `oauth2Login()` giả lập một Authentication đã login; chúng **không** chạy authorization-code redirect, ID token validator hoặc mapper trong callback thật. Unit tests `OidcIdToken`/`GrantedAuthoritiesMapper` kiểm tra phần ánh xạ role riêng.

Khi tích hợp IdP thật, cần thêm:
- E2E OAuth2 authorization-code + OIDC Login và verify issuer/audience/nonce/state.
- JWT thật được ký bằng private key của test IdP, kiểm tra JWKS rotation, `iss`, `aud`, `exp`, `nbf`.
- Negative tests với ID token bị đưa làm Bearer access token, sai audience, sai issuer, thiếu/malformed scopes.
- Session logout/re-authentication, role revocation và thời hạn cache authorities.
- Opaque token introspection nếu sản phẩm hỗ trợ opaque access tokens.

### 9.1. Chạy tests

```bash
mvn test
```

**Kết quả kỳ vọng:** các JUnit/MockMvc test trên pass với Spring Boot 3.5.6 và Spring Security 6.5.x. Chúng được soạn và rà soát mã nguồn, **chưa có thực thi Maven trong bài này**. Cần chạy thật trong CI và điều chỉnh nếu provider/client libraries hoặc cấu hình security khác bản demo.

Vì không có IdP tại `idp.example.invalid`, việc mở trình duyệt và nhấp Login trong app demo **không thể hoàn tất xác thực thực** cho đến khi bạn thay endpoints/credentials bằng IdP hoạt động; test mock vẫn có thể đánh giá logic authorization.

## 10. Đối chiếu các trường hợp dễ sai

### 10.1. “OAuth2 Login không hề có SCOPE_”

Sai. Theo tài liệu Spring Security 6.5, `OAuth2User.getAuthorities()` hoặc `OidcUser.getAuthorities()` được bổ sung scopes từ access token của login client với prefix `SCOPE_`. Đây **không tự chứng minh** scope đó là quyền nghiệp vụ của resource server khác.

### 10.2. “Bearer token chắc chắn là JWT”

Sai. Bearer là cơ chế mang token trong request. Token có thể JWT hoặc opaque; Spring Resource Server có hai cấu hình xác thực khác nhau. `JwtAuthenticationConverter` không hoạt động với opaque introspection.

### 10.3. “Hai bên có SCOPE_reports.read thì có cùng quyền”

Không luôn. Một scope chỉ có nghĩa khi biết **issuer, audience, grant, client và resource**. `reports.read` của token cấp cho CRM không có quyền mặc định ở financial-report API. Resource Server phải validate audience, không chỉ so authority string.

### 10.4. “ID token là Bearer access token hợp lệ”

Không. OIDC ID token dành cho **client xác thực user**. Access token nhằm cho resource server. Chúng có audience khác; API phải từ chối ID token không có audience/loại token phù hợp ngay cả khi chữ ký valid.

### 10.5. “User Info có role=admin thì cứ map ROLE_ADMIN”

Không nếu claim đến từ nguồn user tự sửa hoặc provider chưa được cấu hình. Cần data provenance, issuer trust, tenant membership, consent và role assignment policy. Dữ liệu profile công khai không phải bằng chứng admin.

### 10.6. “oauth2Login mapper cũng sửa được JWT authorities”

Không. `GrantedAuthoritiesMapper` của oauth2Login mapping ảnh hưởng quá trình Login; JWT Resource Server dùng `JwtAuthenticationConverter` (opaque: introspector). Hai hooks là độc lập.

### 10.7. “Đổi converter prefix từ SCOPE_ sang ROLE_ là đủ”

Không. Prefix không thay token assurance, audience hay cơ chế cấp role. Đổi prefix còn có thể làm các `hasAuthority('SCOPE_...')` đang hoạt động bị deny. Cần migration với tests và threat modeling.

### 10.8. “Mỗi lần browser gọi /ui đều gửi access token”

Không nhất thiết. OAuth2 Login server-side thường lưu SecurityContext trong session, browser gửi session cookie. Access token có thể được ứng dụng lưu ở OAuth2AuthorizedClientRepository/Service để gọi downstream; không tự đính kèm vào mọi browser request.

### 10.9. “Một API resource server có thể tin session Login cùng như Bearer”

Chỉ khi bạn cố ý cấu hình hỗ trợ và review. Trong demo API chain chỉ có Bearer JWT và stateless policy; browser chain dùng session. Nếu chung chain, một expression `hasAuthority('SCOPE_reports.read')` có thể pass với Login Authentication cũng có string đó. Phải phân biệt authentication source hoặc route.

### 10.10. “Giữ role trong session mãi không sao”

Không. Nếu user bị xóa khỏi group sau Login, authorities trong session có thể vẫn còn cho tới khi session refresh/expire. Cần policy revoke, re-authentication hoặc dynamic server-side check. Bearer JWT cũng có cửa sổ tồn tại tới exp nếu không có revoke/introspection.

## 11. Checklist để thiết kế authorization hai luồng

- [ ] Phân biệt `oauth2Login()` với `oauth2ResourceServer().jwt()`/`opaqueToken()`.
- [ ] Xác minh `OAuth2AuthenticationToken`, `JwtAuthenticationToken`, `BearerTokenAuthentication` đúng route.
- [ ] Không suy luận OAuth2 Login không có scope authorities.
- [ ] Không suy luận một `SCOPE_*` giống nhau đồng nghĩa cùng audience/cùng action.
- [ ] Không dùng `OIDC_USER`/`OAUTH2_USER` làm quyền dữ liệu nghiệp vụ.
- [ ] `hasRole`/`hasAuthority`/prefix có convention nhất quán.
- [ ] Login role mapping lấy từ OIDC/UserInfo/trusted membership, không từ profile user sửa được.
- [ ] JWT converter xử lý đúng `scope`/`scp`/custom claim và namespace.
- [ ] Opaque token introspector custom riêng, không gọi JWT converter.
- [ ] JWT validation có issuer, signature, exp/nbf, **audience** và algorithm policy.
- [ ] Không coi ID token là access token cho API.
- [ ] Subject mapping theo `issuer + subject`; không dùng email/name làm khóa quyền toàn cầu.
- [ ] API Bearer stateless không vô tình nhận browser session.
- [ ] Browser Login có session/CSRF/redirect state, login callback và logout phù hợp.
- [ ] Security chains dùng `@Order` và `securityMatcher` không tạo khoảng trống.
- [ ] Domain method kiểm tra tenant/object cùng cơ chế xác thực, không dựa string authority đơn thuần khi rủi ro cao.
- [ ] Cấp quyền read và approve/write riêng; scope read không được tự cấp write.
- [ ] Role grant/revoke trong session và token có TTL/cache consistency strategy.
- [ ] MockMvc tests có OAuth2 Login mock, JWT Bearer decoder mock và unit mapper/converter.
- [ ] Contract/E2E tests với IdP thật chứng minh cryptographic validation và authority mapping.
- [ ] Audit decision theo principal issuer/subject, mechanism, policy version, action/resource; không log raw tokens.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một OAuth2 Login user có authorities `OIDC_USER` và `SCOPE_openid`. Được phép approve report không?

**Trả lời:** Không, chỉ vì những authorities đó. Cần quyền nghiệp vụ explicit như `APP_REPORT_APPROVE` và tenant/resource guard.

**Câu 2.** Một JWT Bearer chứa `scope="reports.read reports.approve"`. Resource Server mặc định tạo authorities gì?

**Trả lời:** Thường là `SCOPE_reports.read` và `SCOPE_reports.approve` sau khi JWT được xác thực hợp lệ và converter đọc scope.

**Câu 3.** OAuth2 Login có bao giờ chứa `SCOPE_reports.read` không?

**Trả lời:** Có thể. Login có access token của client với scopes được cấp; Spring có thể biểu diễn thành `SCOPE_*`. Nhưng đó không tự bằng Bearer token hiện tại của report-api.

**Câu 4.** Hook nào map role từ ID token/UserInfo khi OAuth2 Login?

**Trả lời:** `GrantedAuthoritiesMapper` hoặc `OAuth2UserService`/`OidcUserService`, tùy cần claims hay thêm lookup.

**Câu 5.** Hook nào dùng khi JWT Bearer claim `permissions` cần tạo `PERM_*`?

**Trả lời:** `JwtGrantedAuthoritiesConverter` cấu hình `setAuthoritiesClaimName`/`setAuthorityPrefix`, gắn vào `JwtAuthenticationConverter` tại `oauth2ResourceServer().jwt()`.

**Câu 6.** Hook nào dùng khi opaque Bearer đến resource server?

**Trả lời:** `OpaqueTokenIntrospector` hoặc converter liên quan introspection, không phải JwtAuthenticationConverter.

**Câu 7.** Có nên dùng `sub=alice` làm khóa user toàn hệ thống khi có nhiều issuers?

**Trả lời:** Không. Hai issuers có thể dùng cùng sub nhưng chỉ hai user khác nhau. Dùng `(issuer, sub)` hoặc ánh xạ sang stable internal principal ID đã xác minh.

**Câu 8.** `@PreAuthorize("hasAuthority('SCOPE_reports.read')")` có bắt buộc caller phải là JWT Bearer không?

**Trả lời:** Không. Biểu thức chỉ kiểm tra authority string; muốn ràng buộc cơ chế xác thực phải kiểm tra Authentication type/provenance hoặc bảo vệ route theo chain.

**Câu 9.** Dùng `@MockitoBean JwtDecoder` trong MockMvc đã kiểm chứng JWT signature chưa?

**Trả lời:** Chưa. Decoder giả trả token đã parse, do đó tests chỉ chứng minh conversion/authorization pipeline. Cần integration test ký/verify JWT thật.

**Câu 10.** API đang dùng cookies để xác thực và muốn tắt CSRF vì “REST”. Đã đủ điều kiện chưa?

**Trả lời:** Chưa. Chỉ cân nhắc bỏ CSRF trên những endpoints có threat model không dựa browser credentials tự gửi, ví dụ Bearer trong Authorization header với các điều kiện bảo vệ thích hợp. Browser session vẫn cần CSRF cho unsafe methods.

## 13. Tài liệu chính thức

- [Spring Security 6.5 — OAuth2 Login: Advanced Configuration / Mapping User Authorities](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): `OAUTH2_USER`, `OIDC_USER`, `SCOPE_*` trong Login, `GrantedAuthoritiesMapper` và delegated `OAuth2UserService`.
- [Spring Security 6.5 — OAuth2 Login: Core Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): Authorization Code, ClientRegistration, redirect callback và Login flow.
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): `JwtAuthenticationToken`, JWT claims validation, `scope`/`scp`, `JwtGrantedAuthoritiesConverter`, audience.
- [Spring Security 6.5 — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection, `BearerTokenAuthentication`, `SCOPE_*` và customization.
- [Spring Security 6.5 — Testing OAuth2 (MockMvc)](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html): `oauth2Login()`, `jwt()`, test authorities và claims.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy beans, proxy.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth2 client/resource server roles và authorization code.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Authorization Bearer header, transport và token handling.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, UserInfo, issuer/client ID và authentication.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token JWT profile và phân biệt với ID token.

**Kết luận:** `OAuth2 Login` tạo phiên đăng nhập cùng `OAuth2AuthenticationToken`, thường có `OAUTH2_USER`/`OIDC_USER` và **có thể có `SCOPE_*`**. `Resource Server` xác thực Bearer access token của **request hiện tại**, dùng `JwtAuthenticationToken` hoặc `BearerTokenAuthentication` và authority từ validated scopes/introspection. Đừng dựa duy nhất vào tiền tố `SCOPE_` để xác định nguồn quyền. Hãy tách các converter/mappers, xác minh issuer/audience và tenant canonical, áp dụng role/scope theo đúng route và Authentication type, rồi test cả allow/deny lẫn token/claim khác nhau.