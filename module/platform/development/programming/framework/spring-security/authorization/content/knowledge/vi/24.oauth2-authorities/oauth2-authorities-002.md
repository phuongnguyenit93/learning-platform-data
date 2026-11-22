# Scope thành authority `SCOPE_` trong Spring Security OAuth2 Resource Server

## 1. Bài toán: access token có `docs:read`, nhưng tại sao phải kiểm tra `SCOPE_docs:read`?

Một hệ thống sử dụng **OAuth 2.0 Resource Server** để bảo vệ API tài liệu. Authorization Server cấp một **access token** có scope `docs:read`:

```json
{
  "iss": "https://issuer.example.test/training",
  "sub": "alice",
  "aud": ["docs-api"],
  "scope": "docs:read docs:export",
  "exp": 1799999999
}
```

Đây là **payload minh họa**, không phải JWT đầy đủ, không phải access token có chữ ký và không được sử dụng như chứng thực thực tế.

Sau khi JWT được xác minh và chuyển thành `Authentication`, Spring Security Resource Server **mặc định** ánh xạ các scope thành `GrantedAuthority` có tiền tố `SCOPE_`:

```text
JWT claim:
  scope = "docs:read docs:export"

JwtGrantedAuthoritiesConverter:
  "docs:read"   -> "SCOPE_docs:read"
  "docs:export" -> "SCOPE_docs:export"

Authentication.getAuthorities():
  [SCOPE_docs:read, SCOPE_docs:export]
```

Vì vậy API có thể viết:

```java
.requestMatchers(HttpMethod.GET, "/api/docs/**")
    .hasAuthority("SCOPE_docs:read")
```

hoặc method security:

```java
@PreAuthorize("hasAuthority('SCOPE_docs:read')")
public DocumentView read(long documentId) {
    // Nội dung method sau khi đã qua kiểm tra authority.
}
```

Nếu viết `hasAuthority("docs:read")`, mặc định sẽ **không khớp**, vì authority thực tế trong `Authentication` là `SCOPE_docs:read`, không phải chuỗi scope thô.

Bài học thuộc nhóm **Quyền từ OAuth2**, mục **Scope thành authority `SCOPE_` trong Resource Server** của module **Spring Security – authorization**.

Mục tiêu sau bài:

1. Hiểu sự khác biệt giữa **OAuth2 scope**, **JWT claim**, **Spring Security `GrantedAuthority`** và **role**.
2. Theo dõi đường đi của Bearer token qua xác thực JWT đến `JwtAuthenticationToken`.
3. Biết mặc định `scope`/`scp` được chuyển thành những authority nào.
4. Dùng `hasAuthority("SCOPE_...")`, `@PreAuthorize` hoặc `OAuth2AuthorizationManagers.hasScope(...)` đúng cách.
5. Cấu hình Spring Boot 3.5.x Resource Server, `issuer-uri`, `audiences` và JWT converter.
6. Tùy biến claim/prefix bằng `JwtGrantedAuthoritiesConverter` mà không vô tình nâng quyền.
7. Phân biệt JWT self-contained với opaque token introspection, cùng behavior ánh xạ scope.
8. Xây ví dụ Java 17 / Spring Boot 3.5.8 / Spring Security 6.5.x có mã Gradle và integration tests.
9. Kiểm thử **chính đường đi Bearer -> JwtDecoder -> JwtAuthenticationConverter** thay vì chỉ tự gán authority trong test.
10. Nhận biết scope chỉ cấp quyền **chức năng**, không tự cấp quyền trên tenant, owner hoặc từng object.
11. Xử lý lỗi 401/403, token sai audience/issuer, cấp thiếu scope, revoke và những cách debug an toàn.
12. Tránh nhầm **ID token**, access token, client scopes, roles và quyền trên dữ liệu.

**Thông điệp cốt lõi:** `SCOPE_` là **quy ước tên của Spring Security authority sau khi đọc scope của access token đã được xác minh**. Nó không phải claim bắt buộc trong JWT, không phải prefix cần gửi vào Authorization Server và cũng không thay việc kiểm tra tenant/ACL ở service.

---

## 2. Các khái niệm: scope, role, authority, permission, tenant

| Khái niệm | Ví dụ | Nằm ở đâu / ai quyết định |
| --- | --- | --- |
| OAuth2 scope | `docs:read` | Authorization Server cấp cho access token theo grant/policy |
| JWT claim `scope` | `"docs:read docs:write"` | Payload của access token |
| JWT claim `scp` | `["docs:read", "docs:write"]` | Kiểu claim thường gặp từ một số providers |
| Spring `GrantedAuthority` | `SCOPE_docs:read` | Resource Server tạo trong `Authentication` |
| Role ứng dụng | `ROLE_ADMIN` | Nguồn và quy tắc mapping roles của ứng dụng |
| Permission trên object | `READ document#11` | Domain ACL/owner/share/ABAC |
| Tenant membership | Alice thuộc `T1` | Membership/directory đã xác minh |
| Audience của token | `docs-api` | Resource Server phải xác nhận token dành cho API mình |
| Subject | `iss` + `sub` | Principal stable ID trong issuer scope |

**Một access token có scope `docs:read` không tự có nghĩa** người cầm token được xem tất cả tài liệu của mọi tenant. Nó thường chỉ cho biết client/principal đã được cấp khả năng gọi **nhóm thao tác đọc** đối với Resource Server tương ứng. Để xem Document#11, vẫn có thể cần:

```text
allowRead(actor, document) =
    validAccessTokenForThisApi
    AND authorityContains("SCOPE_docs:read")
    AND actorIsMemberOf(document.tenantId)
    AND ownerOrAclAllows(actor, document)
```

Scope thường là lớp **coarse-grained**; object/tenant authorization là lớp **fine-grained**. Đừng nhầm việc `"SCOPE_admin"` xuất hiện trong token với `ROLE_ADMIN`, và cũng không nhầm role với đặc quyền toàn hệ thống.

### 2.1. Access token không phải ID token

Trong OpenID Connect (OIDC), **ID token** chủ yếu nói về sự kiện xác thực người dùng cho **client**, còn **access token** được cấp để gọi resource/API. Một Resource Server nên xử lý **access token** có audience và các ràng buộc phù hợp với API, không dùng ID token dành cho client khác làm API bearer token.

Một ID token có thể chứa `email`, `preferred_username`, `name`, hoặc thậm chí claims về roles, nhưng việc nhìn thấy những fields đó **không** tự chứng minh nó là access token hợp lệ cho `docs-api`.

### 2.2. Scope được yêu cầu khác scope được cấp

Client có thể yêu cầu:

```text
scope=docs:read docs:write
```

Authorization Server vẫn có thể chỉ cấp:

```text
scope=docs:read
```

Resource Server phải dựa vào **token thực tế đã xác minh**, không dựa vào query của authorization request, settings ở frontend hay danh sách scope client *muốn* có.

---

## 3. Đường đi từ Bearer token đến `SCOPE_`

Khi API nhận:

```http
GET /api/docs/11 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
```

luồng thông thường trong Spring Security Servlet Resource Server JWT:

```text
HTTP Authorization: Bearer <access-token>
          |
          v
BearerTokenAuthenticationFilter
          |
          v
JwtAuthenticationProvider
          |
          v
JwtDecoder / NimbusJwtDecoder
  - phân tích token theo định dạng JWT
  - xác minh chữ ký và key phù hợp
  - kiểm tra exp / nbf / iss theo decoder
  - kiểm tra aud khi được cấu hình
          |
          v
Jwt (claims đã qua decoder validation)
          |
          v
JwtAuthenticationConverter
          |
          +--> JwtGrantedAuthoritiesConverter
          |      scope/scp -> SCOPE_...
          |
          v
JwtAuthenticationToken
  Authentication.getPrincipal() = Jwt
  Authentication.getName()      = sub (mặc định)
  Authentication.getAuthorities() = GrantedAuthority list
          |
          v
SecurityContextHolder + AuthorizationFilter
          |
          +--> HTTP hasAuthority / hasScope
          +--> Method Security @PreAuthorize
          |
          v
Controller -> Service -> Domain & Repository ACL
```

Đây là sơ đồ logic, không mô tả từng lời gọi nội bộ hay mọi filter theo thứ tự tuyệt đối cho mọi cấu hình.

**Điều quan trọng:** Việc phân tích claim `scope` không tương đương với xác minh token. Converter chỉ ánh xạ **claims đã được `JwtDecoder` chấp nhận**. Nếu ứng dụng tự `Base64.decode(payload)` và đọc scope mà **không kiểm tra chữ ký/issuer/audience**, attacker có thể tạo JSON scope giả rồi tự cấp quyền.

### 3.1. JWT self-contained: các kiểm tra cần thiết

Một JWT Resource Server production cần kiểm soát:

- **Chữ ký/thuật toán/key:** chỉ chấp nhận thuật toán và khóa được tin cậy từ issuer cấu hình; không tin `alg` hoặc `jku` tùy ý do token chọn mà không có kiểm soát.
- **Issuer (`iss`):** đúng Authorization Server được tin.
- **Thời hạn (`exp`, `nbf`):** không dùng token hết hạn hoặc chưa hiệu lực.
- **Audience (`aud`):** dành cho chính API này, không phải access token của API khác.
- **Tenant/organization context:** khớp trust boundary nếu hệ thống đa tenant.
- **Grant/revoke và policy update:** quyết định về cách vô hiệu hóa token chưa hết hạn, thời gian cache và mức độ yêu cầu freshness.

Spring Security có các validators mặc định theo cấu hình; việc sử dụng issuer URI **không phải lý do bỏ kiểm tra audience**. Với Spring Boot 3.5 có thể cấu hình `spring.security.oauth2.resourceserver.jwt.audiences`.

### 3.2. Lỗi 401 và 403

| Trường hợp | Kết quả thường thấy |
| --- | --- |
| Không có Bearer token khi endpoint cần xác thực | `401 Unauthorized` |
| Bearer không decode/verify được | `401 Unauthorized` |
| JWT hết hạn hoặc issuer sai | `401 Unauthorized` |
| JWT hợp lệ, thiếu `SCOPE_docs:read` | `403 Forbidden` |
| JWT có `SCOPE_docs:read`, nhưng thiếu ACL/tenant permission | Thường `403` hoặc `404` theo contract |
| Endpoint công khai, không cần token | Cho phép theo `permitAll` nếu chưa bị filter khác từ chối |

Status chi tiết phụ thuộc entry point, exception handler, order của các filters và cách từng application cấu hình. Khi trả `403`, không nhất thiết phải tiết lộ object khác tenant có tồn tại.

---

## 4. Quy tắc mặc định: `scope` hoặc `scp` -> `SCOPE_`

Spring Security JWT Resource Server thường dùng `JwtAuthenticationConverter` cùng `JwtGrantedAuthoritiesConverter`.

### 4.1. Claim `scope` là chuỗi cách nhau bằng dấu cách

Ví dụ:

```json
{
  "sub": "alice",
  "scope": "docs:read docs:write docs:export"
}
```

Các authority được tạo:

```text
SCOPE_docs:read
SCOPE_docs:write
SCOPE_docs:export
```

**Không có chuyện tự tạo** `ROLE_ADMIN`, `docs:read` không prefix hoặc `SCOPE_docs` nếu token chỉ có `docs:read`.

### 4.2. Claim `scp` là một danh sách

Một số Authorization Server dùng:

```json
{
  "sub": "alice",
  "scp": ["docs:read", "docs:write"]
}
```

Mặc định converter cũng hỗ trợ đọc danh sách scope từ `scp` và tạo:

```text
SCOPE_docs:read
SCOPE_docs:write
```

Một số providers dùng claim `scp` dưới dạng string. Spring Security converter xử lý kiểu `String` bằng delimiter được cấu hình và kiểu `Collection` theo tập giá trị.

### 4.3. Trường hợp không có scope

Ví dụ token hợp lệ cho API, nhưng:

```json
{
  "sub": "alice",
  "aud": ["docs-api"]
}
```

Khi chỉ dùng converter mặc định, **không tự sinh ra** authority `SCOPE_docs:read`. Caller có thể đã được xác thực, nhưng endpoint `hasAuthority("SCOPE_docs:read")` phải từ chối.

Đây là điểm phân biệt:

```text
authenticated()  !=  hasAuthority("SCOPE_docs:read")
```

Không cố sửa lỗi thiếu scope bằng `.anyRequest().authenticated()` cho toàn API tài liệu, vì như vậy bạn sẽ mở các hành động vượt quyền chức năng.

### 4.4. Nếu có cả `scope` và `scp`?

Trong converter mặc định của Spring Security 6.5, việc tìm well-known authorities claim sử dụng **danh sách tên được nhận biết**, không có hợp đồng “hợp nhất mọi claim bằng phép union”. Vì thế **đừng giả định** scopes từ `scope` và `scp` sẽ được cộng dồn.

Khi một IdP có thể gửi đồng thời hai claims, hãy chuẩn hóa hợp đồng với IdP hoặc **cấu hình rõ `setAuthoritiesClaimName(...)`**, test payload thật và security regressions. Không tự union claims từ các nguồn chưa cùng trust level.

### 4.5. Tên claim `permissions` hoặc `roles` không tự thành scope

JWT có:

```json
{
  "permissions": ["docs:read"],
  "roles": ["ADMIN"]
}
```

**Không tự** được mặc định ánh xạ thành `SCOPE_docs:read` hoặc `ROLE_ADMIN` bởi `JwtGrantedAuthoritiesConverter` đọc scope/scp. Muốn dùng custom claim, cần converter rõ ràng, có whitelist/validation; tránh biến role chưa được issuer bảo đảm thành role hệ thống.

---

## 5. Cách kiểm tra authority trong HTTP Security

### 5.1. Dùng `hasAuthority("SCOPE_...")`

Trong Spring Security Servlet:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/docs/**")
        .hasAuthority("SCOPE_docs:read")
    .requestMatchers(HttpMethod.POST, "/api/docs")
        .hasAuthority("SCOPE_docs:write")
    .anyRequest().denyAll()
);
```

- `GET /api/docs/11` cần đúng authority `SCOPE_docs:read`.
- `POST /api/docs` cần `SCOPE_docs:write`.
- User chỉ có read scope **không** tự có write scope.
- Với `DELETE`, `PATCH`, `PUT`, phải có rule/permission tương ứng nếu nghiệp vụ hỗ trợ.
- `anyRequest().denyAll()` giúp endpoint mới không tự mở khi chưa review.

Cần đặt matcher hẹp và method-specific đúng thứ tự. Một rule `"/api/docs/**".authenticated()` quá rộng đặt trước rule POST/write có thể làm mất ràng buộc write.

### 5.2. Dùng OAuth2 `hasScope(...)`

Spring Security 6.5 cũng có tiện ích:

```java
import static org.springframework.security.oauth2.core.authorization.OAuth2AuthorizationManagers.hasScope;
```

Và:

```java
.requestMatchers(HttpMethod.GET, "/api/docs/**")
    .access(hasScope("docs:read"))
```

**Mảnh code**, giả định `HttpSecurity` đã được tạo trong bean `SecurityFilterChain`. `hasScope("docs:read")` là cách diễn đạt scope đọc của token, tương ứng với model authority `SCOPE_docs:read` khi dùng mapping tiêu chuẩn. Đừng truyền thêm `"SCOPE_"` vào tham số `hasScope` nếu API này kỳ vọng tên scope thô.

Khi đã tùy biến prefix khác `SCOPE_`, cần xem lại cách kết hợp `hasScope(...)`/`hasAuthority(...)` theo contract của version đang dùng, không mặc định hai cách luôn tương đương.

### 5.3. `hasRole("ADMIN")` là khái niệm khác

| Cách viết | Kiểm tra gì theo mặc định? |
| --- | --- |
| `.hasAuthority("SCOPE_docs:read")` | Có authority `SCOPE_docs:read` |
| `.hasAuthority("docs:read")` | Có authority thô `docs:read` |
| `.hasRole("ADMIN")` | Có authority `ROLE_ADMIN` |
| `.hasAuthority("ROLE_ADMIN")` | Có authority `ROLE_ADMIN` |
| `.access(hasScope("docs:read"))` | Có OAuth2 scope `docs:read` theo manager |
| `.authenticated()` | Chỉ cần xác thực, chưa cần scope cụ thể |

**Không dùng `.hasRole("docs:read")`** để kiểm tra OAuth scope: `hasRole` theo mặc định thêm `ROLE_` và sẽ tìm `ROLE_docs:read`, không phải `SCOPE_docs:read`.

### 5.4. `@PreAuthorize` ở service

```java
@PreAuthorize("hasAuthority('SCOPE_docs:write')")
public String create() {
    return "CREATED";
}
```

Muốn annotation được thực thi trong Spring MVC/Servlet app, bật:

```java
@EnableMethodSecurity
```

Method phải được gọi qua **Spring-managed proxy**. Nếu một method trong cùng bean gọi `this.create()`, Spring AOP có thể bỏ qua interceptor cho self-invocation. Để có bảo mật sâu, đặt checks quan trọng tại service/domain boundary và kiểm thử thật qua Spring context.

---

## 6. Ví dụ đầy đủ: Spring Boot 3.5.8 JWT Resource Server

Dự án Java 17 minh họa cả:

- JWT claim `scope` và `scp` được map thành `SCOPE_...`.
- HTTP GET và POST cần scope khác nhau.
- Method Security kiểm tra authority thêm một lần ở service.
- Kiểm soát tenant bằng server-side directory sau khi đã xác thực subject.
- Test thực sự gửi Bearer header qua `MockMvc`, sử dụng `JwtDecoder` **chỉ dành cho test** để tạo JWT đã decode.
- Unit tests riêng cho `JwtGrantedAuthoritiesConverter`.
- Cấu hình `issuer-uri` và audience production, không nhầm fake decoder trong test với xác minh JWT thật.

**Quan trọng:** Mẫu cấu hình chính dành cho Resource Server với **Authorization Server thực** ở production. Các integration tests chạy độc lập với IdP bằng `JwtDecoder` giả **chỉ tồn tại trong test source**, không phải chứng minh khả năng verify JWT cryptography.

### 6.1. Cấu trúc dự án

```text
scope-authority-resource-server/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ScopeAuthorityApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DocumentService.java
    │   │   └── DocumentController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── ScopeResourceServerTest.java
        └── JwtScopeConverterTest.java
```

### 6.2. `settings.gradle`

```groovy
rootProject.name = 'scope-authority-resource-server'
```

### 6.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-oauth2-resource-server` mang Spring Security Resource Server và JWT/Jose dependencies được Spring Boot quản lý. Không cần `spring-boot-starter-oauth2-client` nếu ứng dụng **chỉ đóng vai trò API Resource Server nhận Bearer**, không tự thực hiện OAuth2 login/authorization code flow.

### 6.4. `application.yml`: issuer và audience

**`src/main/resources/application.yml`:**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/training
          audiences:
            - docs-api
```

Địa chỉ `https://issuer.example.test/training` là **URL minh họa**, không phải IdP đang hoạt động. Để chạy API thật, thay bằng issuer URI từ Authorization Server của bạn và audience đúng tên API. Các test ở mục 7 có fake decoder nên **không cần một issuer đang hoạt động**.

Chính sách trong production:

- `issuer-uri` phải là issuer **tin cậy**, không nhận từ header hay query do người gọi gửi.
- `audiences` phải là audience resource server thật, không dùng audience của OAuth client bất kỳ.
- Nếu cấu hình thêm JWK Set URI, phải hiểu tương tác với issuer validation/khóa xoay vòng.
- Không tắt kiểm tra chữ ký hoặc cho token có `"alg":"none"`.
- Đừng dựa vào việc access token **có** claim `"scope"` nếu decoder/issuer validation đang bị bỏ qua.

Trong Spring Boot 3.5, `spring.security.oauth2.resourceserver.jwt.audiences` hỗ trợ cấu hình audience validation cho Resource Server.

### 6.5. Application: `ScopeAuthorityApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopeAuthorityApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ScopeAuthorityApplication.class, args
        );
    }
}
```

### 6.6. Cấu hình security: `SecurityConfig.java`

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        // Không set claim name/prefix: giữ mặc định
        // "scope" hoặc "scp" và "SCOPE_".
        JwtAuthenticationConverter auth =
            new JwtAuthenticationConverter();

        auth.setJwtGrantedAuthoritiesConverter(scopes);
        return auth;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter authConverter)
            throws Exception {

        return http
            // Chỉ phù hợp khi API thực sự bearer-only,
            // stateless, không dựa vào browser cookies.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/public/ping"
                ).permitAll()

                .requestMatchers(
                    HttpMethod.GET, "/api/me/authorities"
                ).authenticated()

                .requestMatchers(
                    HttpMethod.GET, "/api/docs/**"
                ).hasAuthority("SCOPE_docs:read")

                .requestMatchers(
                    HttpMethod.POST, "/api/docs"
                ).hasAuthority("SCOPE_docs:write")

                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(jwt ->
                    jwt.jwtAuthenticationConverter(authConverter)
                )
            )
            .build();
    }
}
```

**Giải thích kỹ:**

- `JwtGrantedAuthoritiesConverter` mặc định chọn claim `scope`/`scp` và prefix `SCOPE_`.
- `JwtAuthenticationConverter` tạo `JwtAuthenticationToken` từ JWT và các authorities.
- `@EnableMethodSecurity` kích hoạt `@PreAuthorize` trong `DocumentService`.
- `GET /api/docs/**` yêu cầu read scope; `POST /api/docs` yêu cầu write scope.
- `GET /api/me/authorities` cần login, chỉ để quan sát authority mapping trong demo. **Không đưa endpoint debug tương tự vào production** nếu không có lý do và kiểm soát truy cập.
- `anyRequest().denyAll()` từ chối method/path chưa được review.
- `.csrf(AbstractHttpConfigurer::disable)` **chỉ chấp nhận được trong ví dụ** vì ta thiết kế API thuần Bearer header, không dùng cookie-based session hoặc implicit credentials để xác thực. Nếu ứng dụng dùng browser cookie/session, cần đánh giá lại và bật CSRF phù hợp. Không copy disable CSRF sang mọi API như một quy tắc chung.
- JWT decode/verification không được vô hiệu hóa trong main source. Với issuer-uri thật, Spring Security tự xây `JwtDecoder` theo cấu hình và kiểm tra token trước khi converter chạy.

### 6.7. Service: functional scope + tenant-scoped access

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

record Document(long id, String tenantId, String title) {
}

@Service
public class DocumentService {

    private final Map<Long, Document> docs = Map.of(
        11L, new Document(11L, "T1", "Alpha"),
        12L, new Document(12L, "T1", "Beta"),
        21L, new Document(21L, "T2", "Gamma")
    );

    // Mô phỏng directory tin cậy phía server, KHÔNG phải
    // JWT claim do client tự khai.
    private final Map<String, String> actorTenants = Map.of(
        "alice", "T1",
        "bob", "T2"
    );

    @PreAuthorize("hasAuthority('SCOPE_docs:read')")
    public String read(long id) {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();

        if (auth == null || !auth.isAuthenticated()) {
            throw new AccessDeniedException(
                "Authenticated actor required");
        }

        String trustedTenant =
            actorTenants.get(auth.getName());

        if (trustedTenant == null) {
            throw new AccessDeniedException(
                "Trusted tenant mapping required");
        }

        Document document = docs.get(id);

        if (document == null
                || !trustedTenant.equals(document.tenantId())) {
            // Không tiết lộ object ở tenant khác có tồn tại.
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document unavailable"
            );
        }

        return document.title();
    }

    @PreAuthorize("hasAuthority('SCOPE_docs:write')")
    public String create() {
        // Demo chỉ minh họa quyền; không mutate DB.
        return "CREATED";
    }
}
```

Vì đây là **Spring MVC/Servlet** app, việc lấy `SecurityContextHolder` trong request thread là mô hình imperative phù hợp. Bài này **không phải** Reactive WebFlux; nếu dùng reactive stack, hãy lấy authentication qua `ReactiveSecurityContextHolder` và dùng `SecurityWebFilterChain`.

`actorTenants` là directory mô phỏng. Trong production:

- Dùng stable `issuer + subject`/internal user ID, thay vì mặc định `sub` luôn unique giữa mọi issuers.
- Xác minh membership/tenant status từ nguồn authoritative.
- Với dữ liệu DB, lọc `WHERE id = :id AND tenant_id = :trustedTenant` **trong repository SQL**, không fetch các tenant khác rồi lọc in-memory.
- Với thao tác ghi, kiểm tra owner/ACL/state/version trong transaction hoặc conditional DML.
- Scope `SCOPE_docs:read` **chỉ là một điều kiện** của việc đọc object.

Ở demo, `read` dùng map in-memory nhỏ; trong sản phẩm thật đây **không phải cơ chế data isolation đủ mạnh**.

### 6.8. Controller: `DocumentController.java`

```java
package demo;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping("/api/docs/{id}")
    public String read(@PathVariable long id) {
        return service.read(id);
    }

    @PostMapping("/api/docs")
    public String create() {
        return service.create();
    }

    @GetMapping("/api/me/authorities")
    public List<String> authorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .sorted()
            .toList();
    }
}
```

Controller **không** nhận `userId`/`tenant` từ request để cấp quyền. `DocumentService` lấy identity từ Spring Security context đã xác minh, kiểm tra scope qua Method Security và ràng buộc tenant sau đó.

API debug `GET /api/me/authorities` chỉ phơi ra các **authority names** đã được map, không in raw access token; vẫn không nên bật cho user production nếu không cần.

---

## 7. Integration test thật trên HTTP Bearer authentication flow

### 7.1. Vì sao không chỉ dùng `jwt()` test helper?

Spring Security Test cung cấp `SecurityMockMvcRequestPostProcessors.jwt()` và cho phép gán authorities tùy ý:

```java
// MẢNH TEST: dễ viết, nhưng có giới hạn.
mvc.perform(get("/api/docs/11")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_docs:read")
    ))
);
```

Cách này rất hữu ích để test **HTTP/method policy**, nhưng authority đã được test **tự gán**. Nếu dùng duy nhất nó, test có thể pass ngay cả khi production `JwtGrantedAuthoritiesConverter` sai claim/prefix.

Để kiểm chứng đúng mục tiêu của bài, ta dùng `Authorization: Bearer ...` và **một fake `JwtDecoder` trong test context**. Filter/Provider/`JwtAuthenticationConverter` thật sẽ nhận Jwt và map `scope` hoặc `scp` thành authorities. Fake decoder chỉ thay việc xác thực token cryptographically; trong production **không được** dùng cách này.

### 7.2. `ScopeResourceServerTest.java`

**`src/test/java/demo/ScopeResourceServerTest.java`:**

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(ScopeResourceServerTest.FakeDecoderConfig.class)
class ScopeResourceServerTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeDecoderConfig {

        @Bean
        @Primary
        JwtDecoder jwtDecoder() {
            return raw -> switch (raw) {
                case "read-alice" -> token(
                    raw, "alice", "scope", "docs:read");

                case "write-alice" -> token(
                    raw, "alice", "scope", "docs:write");

                case "both-alice" -> token(
                    raw, "alice", "scope",
                    "docs:read docs:write");

                case "read-bob" -> token(
                    raw, "bob", "scope", "docs:read");

                case "scp-alice" -> token(
                    raw, "alice", "scp",
                    List.of("docs:read"));

                case "empty-alice" -> token(
                    raw, "alice", "scope", "");

                case "role-alice" -> token(
                    raw, "alice", "scope", "admin");

                default -> throw new BadJwtException(
                    "Invalid test Bearer token");
            };
        }

        private static Jwt token(
                String raw,
                String subject,
                String claimName,
                Object claimValue) {

            return Jwt.withTokenValue(raw)
                .header("alg", "RS256")
                .claim("sub", subject)
                .claim(
                    "iss",
                    "https://issuer.example.test/training"
                )
                .claim("aud", List.of("docs-api"))
                .claim(claimName, claimValue)
                .build();
        }
    }

    private static String bearer(String raw) {
        return "Bearer " + raw;
    }

    @Test
    void publicEndpointWorksWithoutToken() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("PONG"));
    }

    @Test
    void scopeReadMapsToAuthorityAndAllowsRead()
            throws Exception {

        mvc.perform(get("/api/me/authorities")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(
                jsonPath("$[0]")
                    .value("SCOPE_docs:read")
            );

        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Alpha"));
    }

    @Test
    void scpArrayAlsoMapsToScopeAuthority()
            throws Exception {

        mvc.perform(get("/api/docs/12")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("scp-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Beta"));
    }

    @Test
    void readScopeCannotWrite() throws Exception {
        mvc.perform(post("/api/docs")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-alice")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeCannotRead() throws Exception {
        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("write-alice")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeAllowsPost() throws Exception {
        mvc.perform(post("/api/docs")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("write-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("CREATED"));
    }

    @Test
    void multipleScopesProduceMultipleAuthorities()
            throws Exception {

        mvc.perform(get("/api/me/authorities")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("both-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(
                jsonPath("$[0]")
                    .value("SCOPE_docs:read")
            )
            .andExpect(
                jsonPath("$[1]")
                    .value("SCOPE_docs:write")
            );

        mvc.perform(post("/api/docs")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("both-alice")
                ))
            .andExpect(status().isOk());
    }

    @Test
    void noScopeCannotRead() throws Exception {
        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("empty-alice")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void scopeAdminIsNotRoleAdmin() throws Exception {
        mvc.perform(get("/api/me/authorities")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("role-alice")
                ))
            .andExpect(status().isOk())
            .andExpect(
                jsonPath("$[0]")
                    .value("SCOPE_admin")
            );

        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("role-alice")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void knownIdInOtherTenantIsNotVisible()
            throws Exception {

        mvc.perform(get("/api/docs/21")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-alice")
                ))
            .andExpect(status().isNotFound());

        mvc.perform(get("/api/docs/21")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("read-bob")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Gamma"));
    }

    @Test
    void invalidBearerIsUnauthorized() throws Exception {
        mvc.perform(get("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("not-valid")
                ))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/docs/11"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unlistedMethodIsDenied() throws Exception {
        mvc.perform(post("/api/docs/11")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("both-alice")
                ))
            .andExpect(status().isForbidden());
    }
}
```

**Giải thích độ tin cậy của test:**

- `MockMvc` đi qua SecurityFilterChain; Bearer token được extract bởi Resource Server authentication flow.
- Test-only `JwtDecoder` trả một `Jwt` có claims phù hợp từ tên token mô phỏng. **Không** đưa decoder này vào `src/main`, không dùng trong production/staging có real data.
- `JwtAuthenticationConverter` **thật** đọc `scope`/`scp` và tạo `SCOPE_...` trong `Authentication`.
- `@EnableMethodSecurity` vẫn chạy qua Spring proxy của `DocumentService`.
- Test negative gồm thiếu scope, scope sai, JWT invalid, không có token và ID ngoài tenant.
- `@AutoConfigureMockMvc` không tự tắt Spring Security; những requests đang đi qua filters được cấu hình.

**Giới hạn cần nói rõ:** Đây là test **authorization mapping và routing**, không test chữ ký RSA/JWK, issuer/audience validators. Fake `JwtDecoder` chấp nhận các payload mình định nghĩa mà không cryptographically verify. Hãy thêm integration test với Authorization Server/JWK test fixture và expired/incorrect-issuer/audience JWTs trên `NimbusJwtDecoder` thật trước khi triển khai production.

### 7.3. Unit test converter: `JwtScopeConverterTest.java`

**`src/test/java/demo/JwtScopeConverterTest.java`:**

```java
package demo;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class JwtScopeConverterTest {

    private static Jwt jwt(String claim, Object value) {
        return Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim(claim, value)
            .build();
    }

    private static Set<String> authorities(
            JwtGrantedAuthoritiesConverter converter,
            Jwt jwt) {

        return converter.convert(jwt).stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void spaceDelimitedScopeBecomesPrefixedAuthorities() {
        var converter = new JwtGrantedAuthoritiesConverter();

        assertEquals(
            Set.of("SCOPE_docs:read", "SCOPE_docs:write"),
            authorities(
                converter,
                jwt("scope", "docs:read docs:write")
            )
        );
    }

    @Test
    void scpArrayAlsoBecomesPrefixedAuthorities() {
        var converter = new JwtGrantedAuthoritiesConverter();

        assertEquals(
            Set.of("SCOPE_docs:read", "SCOPE_docs:export"),
            authorities(
                converter,
                jwt(
                    "scp",
                    List.of("docs:read", "docs:export")
                )
            )
        );
    }

    @Test
    void missingScopeDoesNotGrantRead() {
        var converter = new JwtGrantedAuthoritiesConverter();

        Set<String> granted = authorities(
            converter,
            Jwt.withTokenValue("no-scope")
                .header("alg", "RS256")
                .claim("sub", "alice")
                .build()
        );

        assertFalse(granted.contains("SCOPE_docs:read"));
        assertEquals(Set.of(), granted);
    }

    @Test
    void scopeDoesNotAutomaticallyBecomeRole() {
        var converter = new JwtGrantedAuthoritiesConverter();

        assertEquals(
            Set.of("SCOPE_admin"),
            authorities(converter, jwt("scope", "admin"))
        );
    }

    @Test
    void customClaimAndPrefixMustBeExplicit() {
        var converter = new JwtGrantedAuthoritiesConverter();

        converter.setAuthoritiesClaimName("permissions");
        converter.setAuthorityPrefix("PERM_");

        assertEquals(
            Set.of("PERM_docs:read"),
            authorities(
                converter,
                jwt(
                    "permissions",
                    List.of("docs:read")
                )
            )
        );

        assertEquals(
            Set.of(),
            authorities(
                converter,
                jwt("scope", "docs:read")
            )
        );
    }
}
```

Những tests này **đi trực tiếp vào converter**, nên tách biệt được vấn đề **claim mapping** với vấn đề **JWT verification** và HTTP filter. Nếu unit test mapping pass nhưng HTTP trả 403, có thể vấn đề nằm ở wiring converter, matcher order, method security hoặc JWT decoder. Nếu HTTP test với `jwt()` tự gán authority pass nhưng converter test fail, phải sửa **converter** chứ không sửa quyền của test.

### 7.4. Chạy tests

Khi đã có Gradle Wrapper:

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa có wrapper, dùng Gradle tương thích được cài để tạo wrapper (`gradle wrapper`) rồi chạy. Test suite được thiết kế để chạy **không cần kết nối IdP**, vì nested `FakeDecoderConfig` chỉ tồn tại trong test.

**Kết quả kỳ vọng:** 13 HTTP integration tests và 5 converter tests, tất cả pass trong môi trường dependency tương thích. Đây là **kỳ vọng theo source code đã soạn**, không phải tuyên bố đã biên dịch/chạy test thật trong môi trường hiện tại.

### 7.5. Chạy ứng dụng thật cần Authorization Server

```bash
./gradlew bootRun
```

Bản chạy production **không** có FakeDecoderConfig. Để gọi API thật, phải cấu hình một `issuer-uri` có thể truy cập và nhận JWT hợp lệ từ IdP đó, với audience `docs-api` và scope tương ứng.

Ví dụ cú pháp request, trong đó `<ACCESS_TOKEN>` phải là **access token hợp lệ đã được cấp bởi IdP**:

```bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  http://localhost:8080/api/docs/11
```

Không lấy JSON ví dụ ở đầu bài rồi Base64-encode để làm access token: JWT có chữ ký/format/validations bắt buộc. Không dùng test token strings `"read-alice"` hoặc `"both-alice"` với bản chạy thật; Resource Server production phải từ chối chúng.

---

## 8. Tùy biến converter: claim, prefix và principal name

Mặc định phù hợp nếu IdP phát scope chuẩn. Nếu IdP có cấu trúc khác, hãy **khai báo rõ** mapping và viết regression tests.

### 8.1. Custom claim: `permissions`

Ví dụ IdP phát:

```json
{
  "sub": "alice",
  "permissions": ["docs:read", "docs:write"]
}
```

Có thể cấu hình:

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter granted =
        new JwtGrantedAuthoritiesConverter();

    granted.setAuthoritiesClaimName("permissions");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(granted);
    return converter;
}
```

**Đây là biến thể thay thế bean trong `SecurityConfig.java`**, không thêm cùng lúc hai bean cùng tên vào project demo.

Với cấu hình này, converter sẽ dùng claim `permissions` thay vì mặc định `scope`/`scp`; authority vẫn có prefix `SCOPE_` trừ khi bạn sửa prefix. Điều này **không tự có nghĩa mọi giá trị trong `permissions` là OAuth2 scopes hợp lệ**: application/issuer cần đặc tả chính sách mapping.

### 8.2. Custom prefix

Nếu muốn authority là `"PERM_docs:read"`:

```java
JwtGrantedAuthoritiesConverter granted =
    new JwtGrantedAuthoritiesConverter();

granted.setAuthoritiesClaimName("permissions");
granted.setAuthorityPrefix("PERM_");
```

Lúc ấy phải dùng:

```java
.hasAuthority("PERM_docs:read")
```

Chứ không thể tiếp tục yêu cầu `SCOPE_docs:read` rồi mong nó tự match.

Spring Security cũng cho phép prefix rỗng:

```java
granted.setAuthorityPrefix("");
```

Nhưng bỏ prefix làm dễ lẫn scopes với roles/custom authorities. Đối với API nhiều nguồn quyền, nên giữ namespace rõ ràng (`SCOPE_`, `ROLE_`, `PERM_`) và review semantics của từng namespace.

### 8.3. Custom delimiter

Với IdP gửi một chuỗi claims dùng dấu phân tách riêng, Spring Security 6.5 cung cấp:

```java
granted.setAuthoritiesClaimDelimiter(",");
```

Đây là **regex** dùng cho String claim, không phải cách split mọi kiểu Collection. Chỉ thay delimiter khi hợp đồng token thực tế **được issuer đảm bảo**; có test cho spaces, empty values và dữ liệu không hợp lệ.

### 8.4. Custom principal claim

Nếu bạn có use case muốn `Authentication.getName()` dùng claim khác:

```java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setPrincipalClaimName("preferred_username");
```

Nhưng subject `sub` thường phù hợp hơn cho stable identity. `preferred_username`/email có thể đổi hoặc trùng giữa tenants; **không** dùng làm khóa bảo mật nếu IdP không đảm bảo unique/immutable.

### 8.5. Giữ scope và role tách biệt

Một số tokens có cả `scope` và claim `realm_access.roles`. Nếu cần biến roles của issuer thành `ROLE_...`, nên dùng **converter tổng hợp có nguồn tin cậy và whitelist** thay vì đổi mọi scope thành `ROLE_` bằng:

```java
granted.setAuthorityPrefix("ROLE_");
```

Vì điều đó có thể khiến một scope tên `ADMIN` được hiểu như role hệ thống. Khi thiết kế custom converter:

- Scope có namespace `SCOPE_`.
- Role được issuer khẳng định và được app chấp nhận có namespace `ROLE_`.
- Permission nội bộ có namespace khác nếu cần.
- Kiểm tra issuer/audience/tenant/role source trước khi cấp quyền.
- Không tự union token fields từ nhiều clients/issuers không cùng trust.
- Viết tests âm tính: token từ issuer khác không được trở thành admin.

---

## 9. Opaque token cũng có scope -> `SCOPE_`, nhưng nguồn facts khác

JWT chỉ là **một dạng access token**. Với opaque token, Resource Server không tự decode claims bằng JWT parser mà hỏi **introspection endpoint**:

```text
Authorization: Bearer opaque-value
          |
          v
OpaqueTokenIntrospector
          |
          v
Authorization Server introspection endpoint
          |
          v
active=true, scope="docs:read docs:write", sub="alice"
          |
          v
BearerTokenAuthentication
          |
          v
GrantedAuthority:
   SCOPE_docs:read
   SCOPE_docs:write
```

Spring Security opaque-token support mặc định cũng ánh xạ scopes có prefix `SCOPE_`.

Cấu hình phác thảo:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://issuer.example.test/introspect
          client-id: docs-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Và security DSL:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Đây là **cấu hình thay thế JWT resource server**, không ghép nguyên vào demo mà giữ đồng thời `.jwt(...)` và `.opaqueToken(...)` khi chưa có yêu cầu rõ ràng.

**Khác biệt:**

| JWT Resource Server | Opaque Resource Server |
| --- | --- |
| Decode và verify JWT bằng `JwtDecoder` | Introspect token bằng `OpaqueTokenIntrospector` |
| `JwtAuthenticationToken` là Authentication điển hình | `BearerTokenAuthentication` là Authentication điển hình |
| Claims lấy từ JWT đã verify | Attributes lấy từ introspection response |
| Scope converter mặc định từ `scope`/`scp` | Scope mapping mặc định từ response `scope` |
| Có thể tự verify offline theo JWK | Phụ thuộc introspection service/availability |
| Revoke trước expiry cần thiết kế policy/blacklist/introspection | Introspection thường giúp hỏi trạng thái active hiện tại, phụ thuộc cache |

Không dùng `JwtGrantedAuthoritiesConverter` để kỳ vọng tự cấu hình ánh xạ **opaque introspection**; nếu provider opaque dùng custom permission fields, thường cần custom `OpaqueTokenIntrospector`/principal-authority mapping.

---

## 10. SCOPE_ không tự giải quyết đa tenant và object-level authorization

Giả sử:

| Document | Tenant | Owner |
| ---: | --- | --- |
| 11 | T1 | Alice |
| 12 | T1 | Bob |
| 21 | T2 | Carol |

Alice có JWT hợp lệ:

```json
{
  "sub": "alice",
  "aud": ["docs-api"],
  "scope": "docs:read"
}
```

Nếu service chỉ:

```java
@PreAuthorize("hasAuthority('SCOPE_docs:read')")
public Document read(long id) {
    return repository.findById(id).orElseThrow();
}
```

thì Alice có thể đọc document 21 của T2 chỉ bằng cách đoán ID. **Đây là lỗi phân quyền object**, không phải lỗi scope converter.

Cách đúng về ý tưởng:

```java
@PreAuthorize("hasAuthority('SCOPE_docs:read')")
public DocumentView read(long id) {
    Actor actor = actorDirectory.requireFromAuthentication();

    return repository.findByIdAndTenantId(
        id, actor.trustedTenantId()
    ).map(DocumentView::from)
     .orElseThrow(() -> new ResponseStatusException(
         HttpStatus.NOT_FOUND, "Document unavailable"
     ));
}
```

**Mảnh code**, các types/service khác cần được định nghĩa. Điểm then chốt là `trustedTenantId` đến từ directory/membership đã xác minh, không lấy trực tiếp từ query `?tenantId=T2`.

Với READ cần ACL hoặc row ownership, tiếp tục thêm điều kiện. Với UPDATE/DELETE, guard tenant/owner/state/version **ngay trong SQL DML** để tránh TOCTOU. Với UI, đừng lấy sự hiện diện của nút “Delete” làm authorization.

### 10.1. Client credentials khác user delegation

Access token phát qua **client credentials grant** có thể đại diện cho **client/application**, không có người dùng cuối theo semantics tương tự authorization code. Scope `docs:write` của service account không tự cho phép giả danh Alice.

Cần phân biệt:

- `sub` là user hay client identity theo IdP contract?
- Token có audience cho Resource Server này không?
- Client được phép thao tác trên tenant nào?
- Có cần service-to-service identity và audit riêng?
- `scope` có chỉ giới hạn hành động mà còn cần business approval/tenant scope?

Không sử dụng `Authentication.getName()` một cách mù quáng như user ID nếu API chấp nhận cả user tokens và machine tokens.

### 10.2. Scope có giới hạn delegation, không phải toàn bộ policy

Một policy điển hình:

```text
ALLOW =
    tokenValid
    AND aud == docs-api
    AND grantedAuthorityContains(SCOPE_docs:read)
    AND membershipAllows(issuer, subject, tenant)
    AND objectAclAllows(subject, doc)
    AND dataStateAllows(action)
```

Nếu một trong các điều kiện bắt buộc không có dữ liệu đáng tin, **deny**, không mở quyền dựa trên riêng scope.

---

## 11. Debug `SCOPE_` một cách an toàn

Khi một người nói “token có scope rồi mà API vẫn 403”, kiểm tra **từng tầng theo thứ tự**.

### 11.1. Checklist chẩn đoán

1. Xác định đây có đúng là **access token** được resource server chấp nhận không, hay client đang gửi ID token.
2. Kiểm tra `Authorization: Bearer <token>` trong request thực.
3. Kiểm tra token được verify thành công; lỗi JWT decoder thường gây `401`, không phải lỗi authority.
4. Kiểm tra `iss`, `aud`, `exp`, `nbf` trên server theo policy, không chỉ nhìn decoded payload trong công cụ debug.
5. Xác định claim scope provider dùng là `scope`, `scp` hay claim khác.
6. Xác định claim là String cách nhau khoảng trắng hay Collection, delimiter khác chuẩn hay không.
7. Xác định có custom `JwtAuthenticationConverter` hoặc `JwtGrantedAuthoritiesConverter` không.
8. Xác định prefix hiện hành là `SCOPE_` hay bị đổi thành `ROLE_`, `PERM_`, chuỗi rỗng.
9. Kiểm tra `hasAuthority`/`hasRole`/`hasScope` trong HTTP Security và Method Security.
10. Xác định rule matcher đầu tiên thực sự áp dụng cho path và HTTP method.
11. Kiểm tra service domain (tenant, owner, ACL, state) có từ chối ở tầng sau không.
12. Thêm unit test converter + integration test Bearer thực sự đi qua filter trước khi sửa policy production.

### 11.2. Không log nguyên token

Hạn chế:

```java
// CẤM trong ứng dụng thực:
log.info("Authorization header = {}", authorizationHeader);
```

Vì log có thể lưu Bearer token dùng được để truy cập API. Thay vào đó ghi logs có giới hạn và retention phù hợp:

```text
requestId, issuerIdentifier, subjectHash,
audienceResult, authorityNames, decision,
policyVersion, requestPathTemplate, responseStatus
```

Tránh ghi token, refresh token, secrets, toàn bộ JWT payload chứa PII hoặc thông tin nhóm nhạy cảm. Ở production, thậm chí danh sách authority/roles cũng cần chính sách log phù hợp.

### 11.3. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| JWT scope `docs:read`, API `hasAuthority('docs:read')` 403 | Thiếu prefix `SCOPE_` | Yêu cầu `SCOPE_docs:read` |
| Dùng `hasRole('docs:read')` | Role tìm `ROLE_docs:read` | Dùng authority/hasScope |
| JWT chỉ có `scp`, converter custom chỉ đọc `scope` | Sai claim name | Đồng bộ contract `scp`/converter |
| Claim `permissions` không sinh authority | Default chỉ đọc well-known scope claims | Custom claim converter |
| Token đúng scope nhưng 401 | Chữ ký/issuer/audience/expiry không qua decoder | Kiểm tra trust config, không bypass validator |
| Token đúng scope nhưng 403 | HTTP/method/domain policy không thỏa | Xác định rule bị từ chối |
| Read token dùng POST không được | Scope read khác write | Cấp đúng write scope qua AS |
| Role `ADMIN` trong token nhưng không có `ROLE_ADMIN` | Chưa có mapping roles | Custom role converter có whitelist |
| Custom prefix đổi sang `PERM_`, rule vẫn `SCOPE_` | Cấu hình không đồng bộ | Cập nhật policy và tests |
| Test `.with(jwt().authorities(...))` pass, production fail | Test tự cấp authority, không test converter | Gửi Bearer header với decoder test + converter |
| Access token của API A gọi API B được | Không validate `aud` | Cấu hình audiences và test token khác audience |
| User có scope vẫn đọc dữ liệu tenant khác | Thiếu object-level guard | Tenant-scoped repository + ACL |
| Access token cũ vẫn dùng sau revoke | JWT chưa hết hạn/caching | Token lifetime, introspection/revocation strategy |
| Opaque token custom field không map | Mặc định introspection chỉ scope theo contract | Custom introspector |
| Client credentials bị coi là user token | Confuse principal/client semantics | Separate machine identity policy |
| Có rule `authenticated` quá rộng trước quyền đọc | Matcher order cho phép sớm | Rule cụ thể trước, fallback deny |
| Copy `{noop}` test password vào prod | Giảm bảo mật credentials | Password hashing/OIDC/OAuth2 |
| Tắt CSRF trên app cookie/session | CSRF risk | Thiết kế CSRF đúng authentication transport |

---

## 12. Security considerations: issuer, audience, replay và revoke

### 12.1. Tin đúng Authorization Server

Resource Server không nên nhận một claim `"iss"` bất kỳ rồi tự lấy JWK của issuer do token cung cấp, nếu chưa có trusted issuer allowlist và cấu hình chống SSRF/key confusion.

Trong production một tenant có thể có issuer riêng. Khi hỗ trợ **multi-issuer/multi-tenant**, cần thiết kế allowlist `issuer -> decoder`, audience và tenant binding. Tên scope `docs:read` từ issuer A không nhất thiết có quyền giống scope cùng tên từ issuer B. Tránh kết hợp authorities từ tokens khác issuers mà không có normalization/trust policy.

### 12.2. Audience confusion

Một người dùng có access token hợp lệ cho `billing-api` với `docs:read`. Nếu `docs-api` chỉ verify signature/issuer mà không verify audience, nó có thể vô tình nhận token **không dành cho mình**.

Cấu hình audience:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/training
          audiences:
            - docs-api
```

Đảm bảo token thực tế có audience phù hợp, và review behavior khi `aud` là string hoặc list tùy spec/provider.

### 12.3. Scope đã bị revoke thì sao?

Với JWT tự chứa, Resource Server có thể xác minh offline. Điều đó nghĩa là một token hợp lệ chưa hết hạn có thể tiếp tục mang `SCOPE_docs:read` **cho đến khi hết hạn** nếu không có cơ chế revoke/blacklist/token version/introspection bổ sung.

Tùy yêu cầu hệ thống:

- Access token có TTL hợp lý.
- Refresh tokens được bảo vệ và có revoke policy.
- Token revocation events + denylist/token epoch với cache invalidation.
- Introspection khi cần freshness cao, có tradeoff latency/availability.
- Permission/tenant/ACL trong DB được kiểm tra lại tại thời điểm request và mutation.
- Với thao tác ghi nhạy cảm, transaction/conditional UPDATE để chặn khi owner/grant/state đổi giữa check và use.

**Đừng dùng một `ALLOW` của authority `SCOPE_docs:write` ở JWT làm bảo đảm không thay đổi trong toàn bộ vòng đời transaction.**

### 12.4. OAuth scope names là hợp đồng

Tên `docs:read`, `docs:write`, `docs:export` là **ví dụ do ứng dụng định nghĩa**. Authorization Server và Resource Server phải cùng thống nhất:

- Tên scope và ý nghĩa của mỗi tên.
- Phạm vi resources/actions được phép.
- Ai được grant scope và trong luồng OAuth nào.
- Default deny nếu token thiếu scope.
- Có hay không phân tầng giữa read/write/admin.
- Cách map roles, tenants hoặc project-specific permissions.
- Version hóa policy và kiểm thử khi đổi semantics.

Không tự tạo nghĩa “`docs:write` bao gồm `docs:read`” trừ khi đó là policy được xác định rõ và thực hiện ở Authorization Server hoặc converter/service; trong mô hình default Spring authorities, chúng là hai chuỗi khác nhau.

---

## 13. Bảng các trường hợp quyền và status

Giả sử token đã được Resource Server chấp nhận (trừ những dòng nói rõ khác).

| Actor / JWT scope | Request | Kết quả |
| --- | --- | --- |
| Anonymous, không token | `GET /public/ping` | `200` |
| Alice `docs:read` | `GET /api/docs/11` (T1) | `200`, `"Alpha"` |
| Alice `docs:read` | `GET /api/docs/21` (T2) | `404` theo tenant scope |
| Bob `docs:read` | `GET /api/docs/21` (T2) | `200`, `"Gamma"` |
| Alice `docs:read` | `POST /api/docs` | `403`, thiếu write |
| Alice `docs:write` | `GET /api/docs/11` | `403`, thiếu read |
| Alice `docs:write` | `POST /api/docs` | `200`, `"CREATED"` (demo không ghi DB) |
| Alice `docs:read docs:write` | GET và POST tương ứng | `200` |
| Alice `scp=["docs:read"]` | `GET /api/docs/12` | `200`, `"Beta"` |
| Alice `scope=""` | `GET /api/docs/11` | `403` |
| Alice `scope="admin"` | `GET /api/docs/11` | `403`, authority là `SCOPE_admin` |
| Token không decode được | `GET /api/docs/11` | `401` |
| Không có token | `GET /api/docs/11` | `401` |
| Token hợp lệ, POST path lạ | `POST /api/docs/11` | `403`, fallback deny |

Đây là **ma trận kỳ vọng của demo**, không phải kết quả thử nghiệm đã được thực thi tại thời điểm viết.

---

## 14. Bài tập thực hành

### Bài 1: đoán authorities

JWT payload:

```json
{
  "sub": "u1",
  "scope": "orders:read orders:write"
}
```

Mặc định Resource Server ánh xạ gì?

**Đáp án:** `SCOPE_orders:read`, `SCOPE_orders:write`.

### Bài 2: `hasAuthority` sai?

```java
.hasAuthority("orders:read")
```

Token có `"scope":"orders:read"` nhưng API trả 403. Vì sao?

**Đáp án:** Default authority có tiền tố `SCOPE_`, nên phải kiểm tra `hasAuthority("SCOPE_orders:read")` hoặc `hasScope("orders:read")` theo API tương ứng.

### Bài 3: `scp` là array

```json
{
  "sub": "u1",
  "scp": ["orders:read", "orders:refund"]
}
```

Authority nào?

**Đáp án:** `SCOPE_orders:read`, `SCOPE_orders:refund` theo default converter.

### Bài 4: thiếu scope

JWT có chữ ký hợp lệ, audience đúng nhưng không có `scope`/`scp`. Gọi GET cần `SCOPE_orders:read`.

**Đáp án:** Thường 403 vì authenticated nhưng thiếu authority. Không tự cho phép vì token được ký đúng.

### Bài 5: scope khác role

JWT có `scope: "ADMIN"`. Có tự thỏa `.hasRole("ADMIN")` không?

**Đáp án:** Không. Converter mặc định cho `SCOPE_ADMIN`, còn `hasRole` theo default tìm `ROLE_ADMIN`.

### Bài 6: custom prefix

Converter dùng `setAuthorityPrefix("PERM_")`. HTTP rule vẫn kiểm tra `SCOPE_orders:read`.

**Đáp án:** Không match. Đồng bộ rule với mapping hoặc giữ default prefix.

### Bài 7: `permissions` claim

JWT có `permissions: ["orders:read"]` và không có `scope`/`scp`. Converter mặc định có grant `SCOPE_orders:read` không?

**Đáp án:** Không. Cần custom claim mapping được IdP/resource server thống nhất.

### Bài 8: JWT từ API khác

Token có `iss` hợp lệ, scope `docs:read`, nhưng `aud` chỉ có `billing-api`. Resource Server `docs-api` nên làm gì?

**Đáp án:** Từ chối token ở **authentication** do sai audience; không coi scope là đủ.

### Bài 9: object-level authorization

Alice T1 có `SCOPE_docs:read`, ID 21 ở T2. Chỉ `@PreAuthorize("hasAuthority('SCOPE_docs:read')")` có đủ?

**Đáp án:** Không. Repository phải query theo trusted tenant/object permission.

### Bài 10: Test chỉ dùng `jwt().authorities(...)`

Test `.with(jwt().authorities(SCOPE_docs:read))` pass nhưng production không map `scp`. Vì sao test bỏ sót?

**Đáp án:** Test tự đưa authority vào Authentication, không đi qua real JWT claims converter. Cần unit converter test và Bearer integration test với decoder test.

### Bài 11: 401 hay 403?

Token không xác thực được: `401` thường gặp. Token hợp lệ nhưng thiếu scope: `403` thường gặp. Vì sao khác nhau?

**Đáp án:** Trường hợp đầu chưa authenticated thành công, trường hợp sau authentication đã có nhưng authorization không cho thao tác.

### Bài 12: JWT expire sau khi role bị revoke

JWT còn hạn, scope đã bị thu trong directory. Server tự loại bỏ scope ở token đã phát chưa?

**Đáp án:** Không tự. Cần revoke strategy, TTL, introspection hoặc kiểm tra quyền thay đổi ở policy/domain boundary.

### Bài 13: opaque token

Opaque introspection response có `"scope":"orders:read orders:write"`. Có thể tạo `SCOPE_...` không?

**Đáp án:** Có theo default opaque Resource Server scope mapping; không cần JWT parser. Nhưng các custom claims cần mapping riêng.

### Bài 14: client credentials

Token được cấp cho service account có scope `docs:write`. Backend có thể mặc định ghi thay bất kỳ user/tenant nào không?

**Đáp án:** Không. Cần principal/client identity policy, tenant scope, audit và quyền trên resource cụ thể.

---

## 15. Checklist triển khai Resource Server

1. Xác nhận token đầu vào là **access token** cho đúng Resource Server.
2. Cấu hình `issuer-uri` từ trusted Authorization Server.
3. Cấu hình audience (`spring.security.oauth2.resourceserver.jwt.audiences`) cho API thật.
4. Dùng JWT/JWK signature verification và validators; không parse payload theo cách thủ công rồi cấp quyền.
5. Kiểm tra IdP phát claim `scope` hay `scp`, kiểu dữ liệu String hay Collection.
6. Hiểu prefix mặc định `SCOPE_` và ghi rõ tên authority trong policy.
7. Tách scopes và roles: `SCOPE_` không tự thành `ROLE_`.
8. Áp `hasAuthority("SCOPE_...")` hoặc OAuth2 `hasScope(...)` đúng nơi.
9. Bật `@EnableMethodSecurity` nếu muốn bảo vệ service methods.
10. Không dùng chỉ `.authenticated()` thay cho permission-sensitive endpoints.
11. Quy tắc HTTP method/path cụ thể trước, fallback deny sau.
12. Với tenant/object access, dùng directory + tenant-scoped repository và ACL.
13. Với write, kiểm tra grant/owner/state/version gần mutation trong transaction.
14. Nếu custom claim/prefix, tập trung converter ở một chỗ và thêm tests âm tính.
15. Test converter độc lập + HTTP Bearer integration qua filter/decoder.
16. Test JWT sai signature/issuer/audience/expiry bằng decoder thực khi có thể.
17. Không cho test fake decoder lọt vào runtime production.
18. Không log raw access token, secrets và toàn bộ sensitive JWT claims.
19. Thiết kế token TTL/revocation, JWK rotation, timeout/availability có chủ đích.
20. Kiểm chứng OAuth client credentials vs user tokens, principal stable identity và multi-issuer trust.
21. Review rủi ro CSRF trước khi disable, dựa vào cách API thực sự nhận credentials.
22. Test 401, 403, 404 và bất biến dữ liệu sau denial theo API contract.

---

## 16. Tài liệu chính thức

1. [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): Bearer JWT verification, `scope`/`scp` mapping, `SCOPE_` và custom `JwtAuthenticationConverter`.
2. [Spring Security 6.5 – OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection, scope mapping và custom introspectors.
3. [Spring Security – JwtGrantedAuthoritiesConverter API](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): setters cho claim, prefix và delimiter.
4. [Spring Security – JwtAuthenticationConverter API](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): JWT -> Authentication, principal claim và authorities.
5. [Spring Security – JWT Authentication Token](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html): principal, name và granted authorities.
6. [Spring Security – Servlet Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): GrantedAuthority, role và authorization decisions.
7. [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và AOP.
8. [Spring Security – Testing OAuth2](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html): `jwt()`/`opaqueToken()` test helpers và custom authorities.
9. [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.security.oauth2.resourceserver.jwt.audiences`.
10. [Spring Boot – OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): issuer/JWT resource server autoconfiguration.
11. [OAuth 2.0 Framework – RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): scope semantics và OAuth2 roles.
12. [OAuth2 Bearer Token Usage – RFC 6750](https://www.rfc-editor.org/rfc/rfc6750): Authorization Bearer header và lỗi token.
13. [JWT – RFC 7519](https://www.rfc-editor.org/rfc/rfc7519): claims, registered claim names và JWT structure.
14. [OAuth 2.0 JWT Access Token Profile – RFC 9068](https://www.rfc-editor.org/rfc/rfc9068): hướng dẫn JWT access token và resource server validation.
15. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default và object-level checks.

**Kết luận:** Trong Spring Security OAuth2 Resource Server, claim access token **`scope` hoặc `scp`** được `JwtGrantedAuthoritiesConverter` mặc định chuyển thành các `GrantedAuthority` có tiền tố **`SCOPE_`**. Viết rule **`hasAuthority("SCOPE_docs:read")`** để yêu cầu scope `docs:read`, không nhầm sang `hasRole("ADMIN")`. Khi IdP có claim khác, cấu hình converter và kiểm thử theo token schema được xác minh; không tắt signature/issuer/audience validation. Scope là lớp authorization chức năng, **không tự bảo vệ tenant/ACL/object ownership**, vì vậy luôn kết hợp repository/domain guards và kiểm chứng cả hai hướng ALLOW/DENY.