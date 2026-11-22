# Kiểm thử chưa xác thực, thiếu quyền và được phép truy cập

Một endpoint Spring Boot có thể trả JSON đúng trong unit test nhưng vẫn **cho phép người dùng sai quyền truy cập** khi triển khai. Ngược lại, một test chỉ assert mã `403` có thể xanh vì **thiếu CSRF token**, chứ không phải chính sách role/ownership đang được thực thi. Kiểm thử bảo mật vì thế không chỉ hỏi “response có phải 200 không”, mà phải mô tả **ai gọi, dùng credential nào, cần quyền gì, chạm tài nguyên của ai và thao tác nào thực sự đã chạy**.

Bài Knowledge này nằm trong phần **Bảo mật** của module **Spring Boot – testing**, với trọng tâm trực tiếp: **kiểm thử chưa xác thực, thiếu quyền và được phép truy cập**. Ta sẽ xây một ma trận đối chiếu trạng thái *anonymous → 401*, *authenticated nhưng không đủ quyền → 403* và *đúng quyền → 200/202*, sau đó bổ sung bảo vệ chống truy cập chéo tài khoản (*Broken Object Level Authorization / IDOR*), CSRF, quyền trên HTTP method và quyền ở service layer.

Ví dụ dùng **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, JUnit Jupiter 5, Spring Security Test, MockMvc và @SpringBootTest**. Bộ ứng dụng mẫu cấu hình **HTTP Basic** để các kịch bản 401/403 dễ quan sát và credential thật sự đi qua bộ lọc xác thực. Tất cả tài khoản/mật khẩu mẫu chỉ nằm trong **test source**, không nằm trong cấu hình triển khai. Ở production, nhiều API dùng OAuth2/JWT hoặc mTLS; các nguyên tắc test vẫn áp dụng, nhưng status/challenge/token validation phải được kiểm theo **security configuration thực tế**.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

- Phân biệt **authentication (xác thực)** với **authorization (phân quyền)**, và vì sao cả hai đều cần tests.
- Hiểu ý nghĩa điển hình của HTTP `401 Unauthorized`, `403 Forbidden`, `200 OK`, `202 Accepted` và trường hợp 302/404 được dùng theo policy.
- Lập security matrix cho anonymous, sai credential, user thường, admin, owner và non-owner.
- Viết `SecurityFilterChain` với quy tắc deny-by-default và role check đúng `ROLE_`.
- Kiểm request-level security bằng `@WebMvcTest`, `MockMvc` và filter chain thật.
- Phân biệt `@WithMockUser`/`user(...)` **tạo SecurityContext giả** với `httpBasic(...)` **đi qua xác thực username/password**.
- Kiểm service-level authorization qua `@EnableMethodSecurity` và `@PreAuthorize` với ownership.
- Không cho phép một user xem dữ liệu tài khoản khác dù đã đăng nhập.
- Kiểm rằng request bị từ chối **không chạm vào service tạo side effect**.
- Tách riêng lỗi thiếu CSRF khỏi lỗi thiếu role trong các thao tác POST/PUT/PATCH/DELETE.
- Nhận biết test xanh giả khi tắt filters hoặc mock security boundary.
- Hiểu test JWT bằng `jwt()` không tự chứng minh signature/issuer/audience được xác minh.
- Viết các case positive/negative, chạy suite và biết những boundary chưa được kiểm.

## 2. Cơ chế nền tảng: authentication trước, authorization sau

**Authentication:** caller là ai và credential có hợp lệ không? Với HTTP Basic, username/password được đọc từ `Authorization` header, gửi qua authentication manager/provider và tạo `Authentication` nếu hợp lệ. Với OAuth2 resource server, bearer token được giải mã/kiểm chữ ký hoặc introspection theo cấu hình.

**Authorization:** authenticated caller được làm **hành động nào** trên **tài nguyên nào**? Ví dụ chỉ admin xem số liệu quản trị; Alice chỉ đọc account Alice, không được đọc account Bob. SecurityContext chỉ cho biết một identity đã được nhận, **không** tự xác định mọi object của hệ thống có thể được xem.

Một sơ đồ:

```text
HTTP request
   |
   v
Spring Security FilterChainProxy
   |
   +-- Authentication
   |     +-- anonymous / invalid credentials
   |     +-- valid Authentication with authorities
   |
   +-- AuthorizationFilter: URL + method rules
   |     +-- /api/admin/** -> ROLE_ADMIN
   |     +-- /api/accounts/** -> authenticated
   |
   +-- CSRF filter for state-changing methods
   |
   v
Controller
   |
   +-- AccountService proxy with @PreAuthorize
   |     +-- admin OR requested owner equals authentication.name
   |
   v
Business operation / DTO
```

**Hai lớp authorization:** request matcher chặn route không phù hợp; method security bảo vệ logic được gọi từ controller, scheduled job hoặc service khác. Nếu chỉ bảo vệ URL và một service khác có thể gọi thẳng method, dữ liệu có thể bị lộ qua đường vòng.

## 3. Bản đồ HTTP status: đừng học máy móc “403 = không có quyền”

| Tình huống trong API HTTP Basic của bài | Response dự kiến | Vì sao |
|---|---:|---|
| Anonymous gọi GET bảo vệ | `401` | Chưa có credential hợp lệ; Basic entry point gửi challenge |
| Username/password sai | `401` | Authentication thất bại |
| Alice đã xác thực, gọi admin endpoint | `403` | Có identity nhưng thiếu `ROLE_ADMIN` |
| Admin có quyền, gọi GET admin | `200` | Authorization cho phép |
| Alice đọc account Alice | `200` | Được phép theo ownership |
| Alice đọc account Bob | `403` | Đã xác thực nhưng không sở hữu |
| Admin đọc account Bob | `200` | Quy tắc cho admin |
| Admin POST nhưng thiếu CSRF | `403` | CSRF chặn trước business logic, **không phải** thiếu ROLE_ADMIN |
| Admin POST có CSRF hợp lệ | `202` | Được phép xếp hàng công việc demo |
| Anonymous POST và có CSRF | `401` | CSRF không thay thế authentication |

**Phải đọc theo cấu hình.** Nếu ứng dụng dùng form login, anonymous truy cập page bảo vệ có thể bị **302 redirect** tới login thay vì 401. Với JWT resource server, `401` thường đi kèm `WWW-Authenticate: Bearer` khi thiếu/sai token và `403` khi thiếu scope; API có chính sách 404 để không lộ sự tồn tại tài nguyên cũng có thể hợp lý. Tests phải assert **contract được công bố**, không áp một mã duy nhất cho mọi kiểu ứng dụng.

### 3.1. Vì sao 401 có tên “Unauthorized” dù nghĩa là chưa xác thực?

Tên lịch sử `401 Unauthorized` dễ gây nhầm. Trong HTTP security practice, `401` thường có nghĩa credentials chưa có/không được chấp nhận và cần authentication challenge; `403` chỉ ra server hiểu yêu cầu nhưng từ chối quyền. Một user đăng nhập thành công nhưng không có quyền đọc report admin thường là `403`.

Trong ví dụ HTTP Basic, `401` từ entry point thường kèm `WWW-Authenticate: Basic ...`. Không giả định trường này luôn là Basic: với Bearer/JWT, challenge và error details khác.

## 4. Ba chiều của ma trận phân quyền

Một bài test cần mô tả ít nhất:

1. **Principal:** anonymous, Alice, Bob, admin hoặc service account.
2. **Action:** GET/POST/PUT/PATCH/DELETE, export, approve, refund.
3. **Resource:** account/document của ai, tenant nào, trạng thái nào.

Ví dụ ma trận:

| Principal | GET `/api/admin/metrics` | POST `/api/admin/reindex` có CSRF | GET `/api/accounts/alice` | GET `/api/accounts/bob` |
|---|---:|---:|---:|---:|
| Anonymous | 401 | 401 | 401 | 401 |
| Alice / USER | 403 | 403 | 200 | 403 |
| Bob / USER | 403 | 403 | 403 | 200 |
| Admin / ADMIN | 200 | 202 | 200 | 200 |
| Sai password | 401 | 401 | 401 | 401 |

**Lưu ý:** Với POST **thiếu** CSRF, nhiều requests — kể cả admin hợp lệ — đều có thể bị 403, làm mất tín hiệu của role authorization. Vì vậy cột POST ở trên **đã giả định có CSRF hợp lệ**. Ta cần test thiếu CSRF riêng, không trộn lý do bị từ chối.

### 4.1. “Được phép truy cập” không chỉ là 200

Một endpoint tạo resource có thể trả 201, xếp hàng xử lý trả 202, xóa thành công trả 204. Một test mạnh xác minh status **và side effect/response data được phép**, không hard-code `200` cho mọi use case. Quan trọng nhất là **request không có quyền không được làm thay đổi dữ liệu**, dù tầng controller cuối cùng vô tình trả một mã lỗi.

## 5. Ranh giới: URL rule và object-level rule

Một quy tắc:

```java
.requestMatchers("/api/accounts/**").authenticated()
```

chỉ chứng minh caller đã xác thực khi vào route accounts. Nó **không** trả lời câu hỏi “Alice có được GET /api/accounts/bob không?”. Nếu controller làm:

```java
// PHẢN VÍ DỤ: ai đăng nhập cũng có thể đọc owner do URL đưa vào.
return accountService.readAnything(ownerFromPath);
```

thì có thể tồn tại lỗi **Insecure Direct Object Reference / Broken Object Level Authorization**. Test phải có hai nhánh:

- Alice → Alice: **được phép**, trả đúng Alice.
- Alice → Bob: **bị từ chối**, không trả dữ liệu Bob.

Với hệ thống nhiều tenant, check còn phải kết hợp `tenantId` từ **trusted authentication context**, không chỉ so username với field do client gửi. Ngay cả khi role hợp lệ, object-level constraints vẫn cần thực thi.

## 6. Thiết kế security policy tối thiểu của bài

Bài demo định nghĩa:

- `GET /api/admin/metrics`: chỉ `ROLE_ADMIN`.
- `POST /api/admin/reindex`: chỉ `ROLE_ADMIN` và CSRF hợp lệ.
- `GET /api/accounts/{owner}`: phải authenticated; service chỉ cho owner hoặc admin.
- Các route khác: **denyAll**.
- Authentication: HTTP Basic.
- CSRF: **giữ bật**; không tắt để test POST dễ xanh.
- Users: Alice, Bob (ROLE_USER) và admin (ROLE_ADMIN) được tạo trong test-only config.

Điều bài **không** chứng minh:

- Mật khẩu/roles được quản trị trong production IdP/database.
- JWT validation, token rotation, MFA, federation hoặc OAuth2 scopes.
- TLS/basic credentials qua Internet (HTTP Basic **chỉ an toàn khi dùng HTTPS và policy phù hợp**).
- Trạng thái account thực trong database vì demo trả DTO tĩnh.
- Admin job thật được lên scheduler, vì demo dùng bộ đếm có chủ đích để kiểm side effects.
- UI login/redirect, CORS preflight và Spring WebFlux security.

## 7. Bẫy `ROLE_` trong Spring Security

Spring Security `hasRole("ADMIN")` mặc định kiểm authority `ROLE_ADMIN`, không phải authority `ADMIN`. Một user có:

```text
GrantedAuthority("ROLE_ADMIN") -> hasRole("ADMIN") = true
GrantedAuthority("ADMIN")      -> hasRole("ADMIN") = false
```

Trong Spring Security Test:

```java
// Tạo Authentication giả có authority ROLE_ADMIN:
.with(user("test-admin").roles("ADMIN"))

// Tạo Authentication giả chỉ có authority ADMIN:
.with(user("test-admin").authorities(
        new SimpleGrantedAuthority("ADMIN")))
```

Đây là snippets, cần imports và context MockMvc. Hai cách này **không tương đương**. Khi hệ thống dùng scopes như `SCOPE_reports:read`, có thể chọn `hasAuthority("SCOPE_reports:read")`; không đổi thành `hasRole("reports:read")` trừ khi quyền được mapping đúng. Nếu team thay default role prefix, tests và policy phải được cập nhật đồng bộ.

## 8. Kiểm security filter chain thật hay chỉ mock user?

Ba test khác nhau:

- `@WithMockUser(username="alice", roles="USER")`: Spring Security Test tạo một `Authentication` trong SecurityContext; **bỏ qua bước kiểm password, token signature, account disabled**. Rất tốt để test **authorization**.
- `mvc.perform(get(...).with(user("alice").roles("USER")))`: request post-processor dựng mock SecurityContext cho request; tương tự không xác minh credentials thật.
- `mvc.perform(get(...).with(httpBasic("alice", "alice-pass")))`: đặt `Authorization: Basic ...`, để **BasicAuthenticationFilter** và authentication provider thật của test context xử lý. Phù hợp để kiểm password đúng/sai, challenge 401.

**Đừng báo “JWT được xác thực đúng” vì `@WithMockUser` làm request 200.** Test đó không chạy signature verification. Tương tự `jwt()` post-processor tạo JWT authentication giả để kiểm scopes/controller nhưng không xác minh chữ ký; xem mục 28.

## 9. CSRF: một `403` không nhất thiết là thiếu quyền

Spring Security mặc định bảo vệ CSRF cho các HTTP methods thay đổi trạng thái. Khi một POST không có CSRF token phù hợp, Spring có thể trả `403` **trước** khi quyền role được kiểm. Điều này gây test false confidence:

```java
// TEST YẾU: user không có quyền nhưng cũng thiếu CSRF.
mvc.perform(post("/api/admin/reindex")
        .with(httpBasic("alice", "alice-pass")))
   .andExpect(status().isForbidden());
```

Nó có thể xanh **dù bạn lỡ xóa rule ADMIN**, vì CSRF vẫn chặn. Test quyền phải thêm `with(csrf())`:

```java
// Đúng cho test authorization trên POST khi CSRF bật:
mvc.perform(post("/api/admin/reindex")
        .with(httpBasic("alice", "alice-pass"))
        .with(csrf()))
   .andExpect(status().isForbidden());
```

Rồi một test riêng chứng minh admin thiếu CSRF bị 403:

```java
mvc.perform(post("/api/admin/reindex")
        .with(httpBasic("admin", "admin-pass")))
   .andExpect(status().isForbidden());
```

**Không tắt CSRF chỉ để test pass.** Nếu API là stateless bearer token không dựa trên cookie/implicit browser credentials, team có thể đánh giá chính sách CSRF khác. Nhưng HTTP Basic, cookies và browser-origin requests có những rủi ro riêng; quyết định tắt cần threat model, không phải giải pháp “cho test dễ viết”.

## 10. Test slice và full-context: nên kiểm ở đâu?

| Mục tiêu | Cấp test | Bảo vệ tốt | Giới hạn |
|---|---|---|---|
| HTTP URL rules, Basic auth, CSRF | `@WebMvcTest` + `MockMvc` + SecurityFilterChain | 401/403/200/202 trên MVC route | Không load mọi service/DB |
| Service `@PreAuthorize` và owner | `@SpringBootTest` + bean thật | Method proxy được bảo vệ | Chưa chắc HTTP transport |
| Test object-level qua HTTP | `@SpringBootTest` + `@AutoConfigureMockMvc` | Request filter + controller + service | Mock servlet, không TCP |
| Actual username/password | `httpBasic(...)` qua filter chain | PasswordEncoder/UserDetailsService | Test users có thể khác prod IdP |
| Real JWT validation | `@SpringBootTest` / targeted security integration với real decoder | Signature/audience/issuer/expired JWT | Cần key/JWK/test IdP |
| Real HTTP/TLS/reverse proxy | `RANDOM_PORT` + HTTP client | Server filter chain, cookies, redirects, TLS setup | Chậm hơn, infra nhiều |
| Business ownership với DB | Repository/service integration và dữ liệu hai owners | IDOR, tenant isolation và data leak | Cần DB fixture/migration |

**@WebMvcTest mặc định không load mọi @Service.** Nếu security policy có rule ở service, dùng full context hoặc import/mock những beans cần thiết và **test riêng method security với bean thật**. Nếu chỉ mock service trong @WebMvcTest và assert 200/403 tại controller, bạn **chưa chứng minh** business-level access control của service.

## 11. Cấu trúc project runnable

Ta xây mini API với hai khu vực: admin và account owner. File tree:

```text
security-access-tests/
  settings.gradle
  build.gradle
  src/main/java/com/example/securitylesson/
    SecurityLessonApplication.java
    ApiSecurityConfig.java
    AdminJobService.java
    AdminController.java
    AccountSummary.java
    AccountService.java
    AccountController.java
  src/test/java/com/example/securitylesson/
    TestUsersConfig.java
    AdminAccessMvcTest.java
    AccountAccessIntegrationTest.java
```

Quy ước ví dụ:

- Java 17, Spring Boot 3.5.x, Spring Security 6.5.x (quản lý phiên bản bằng Boot BOM).
- In-memory users chỉ có trong `src/test/java`.
- No database; AccountService dùng DTO giả để minh họa check ownership.
- Method security **bắt buộc được bật**.
- CSRF được giữ mặc định, kể cả khi dùng HTTP Basic.
- Không cần Docker hoặc credential thật.

## 12. Gradle project

**`settings.gradle`**

```groovy
rootProject.name = 'security-access-tests'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Vì sao cần `spring-security-test` riêng?** Nó cung cấp `@WithMockUser`, `httpBasic(...)`, `csrf()`, `user(...)` và security integration utilities. `spring-boot-starter-test` mang JUnit/MockMvc/Mockito nhưng không thay thế toàn bộ Spring Security Test. Boot BOM quản lý compatible versions; tránh ép `spring-security-test` sang một major khác.

**Vì sao không dùng một user/password production trong build?** Demo chỉ định test credentials ở `TestUsersConfig` để HTTP Basic test đi qua provider thật nhưng không lộ secret. Đây chỉ là tài khoản giả cục bộ, không phải hướng dẫn đưa in-memory users vào ứng dụng thực tế.

## 13. Main application và SecurityFilterChain

**`src/main/java/com/example/securitylesson/SecurityLessonApplication.java`**

```java
package com.example.securitylesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                SecurityLessonApplication.class, args);
    }
}
```

**`src/main/java/com/example/securitylesson/ApiSecurityConfig.java`**

```java
package com.example.securitylesson;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/admin/**")
                            .hasRole("ADMIN")
                        .requestMatchers("/api/accounts/**")
                            .authenticated()
                        .anyRequest()
                            .denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
    }
}
```

**Giải thích từng thành phần:**

1. `@EnableMethodSecurity` làm `@PreAuthorize` trên service được Spring AOP đánh giá; Spring Boot starter security **không tự bật method security**.
2. `/api/admin/**` cần `ROLE_ADMIN`. Rule này **đặt trước** rule chung; matcher order có thể thay đổi kết quả khi patterns chồng lấn.
3. `/api/accounts/**` yêu cầu authenticated, nhưng **không tự kiểm object owner**. Service đảm nhiệm.
4. `anyRequest().denyAll()` chặn routes chưa có rule thay vì mặc định cho phép.
5. `httpBasic` cấu hình authentication entry point nên unauthenticated GET bảo vệ nhận 401.
6. Form login được tắt trong demo để tránh HTML redirect 302, giúp API behavior nhất quán.
7. CSRF vẫn bật; POST cần CSRF token hợp lệ trong MockMvc tests.

**Không suy ra 403 từ mọi `denyAll`:** với anonymous caller, `ExceptionTranslationFilter` có thể gửi vào Basic authentication entry point và trả 401; với authenticated user, denyAll thường thành 403. Chính security entry point và exception handling quyết định final HTTP status.

## 14. Business service và controller có side effect quan sát được

**`src/main/java/com/example/securitylesson/AdminJobService.java`**

```java
package com.example.securitylesson;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class AdminJobService {

    private final AtomicInteger acceptedReindexRequests =
            new AtomicInteger();

    public int acceptReindexRequest() {
        return acceptedReindexRequests.incrementAndGet();
    }
}
```

Bộ đếm chỉ mô phỏng **một side effect dễ xác minh trong test**, không phải job scheduler production. Với queue thực (Kafka/RabbitMQ/DB outbox), cần integration test để kiểm unauthorized request **không publish message hoặc ghi row**. Không dùng shared counter làm cơ chế bảo mật.

**`src/main/java/com/example/securitylesson/AdminController.java`**

```java
package com.example.securitylesson;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    private final AdminJobService jobs;

    public AdminController(AdminJobService jobs) {
        this.jobs = jobs;
    }

    @GetMapping("/metrics")
    public Map<String, String> metrics() {
        return Map.of("status", "OK");
    }

    @PostMapping("/reindex")
    public ResponseEntity<Map<String, Integer>> reindex() {
        int requestNumber = jobs.acceptReindexRequest();
        return ResponseEntity.accepted()
                .body(Map.of("acceptedRequestNumber", requestNumber));
    }
}
```

Một test `403` đáng tin nên xác minh `jobs.acceptReindexRequest()` **không bị gọi**. Điều này giúp bắt regression khi controller thực hiện side effect trước khi kiểm quyền hoặc when a security filter is removed. Nếu method có tác dụng lên database, kiểm DB state/outbox sau response nữa.

## 15. Object-level authorization: AccountService

**`src/main/java/com/example/securitylesson/AccountSummary.java`**

```java
package com.example.securitylesson;

public record AccountSummary(
        String owner,
        String status) {
}
```

**`src/main/java/com/example/securitylesson/AccountService.java`**

```java
package com.example.securitylesson;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AccountService {

    @PreAuthorize(
            "hasRole('ADMIN') or #owner == authentication.name")
    public AccountSummary read(
            @P("owner") String owner) {

        return new AccountSummary(owner, "ACTIVE");
    }
}
```

**Vì sao có `@P("owner")`?** Spring Security SpEL cần biết tên parameter. `@P` cung cấp tên tường minh, tránh phụ thuộc hoàn toàn vào compiler `-parameters` hoặc debug parameter metadata. `authentication.name` là username của principal trong demo.

**Điểm cần hiểu:** `read` trả DTO minh họa, không truy vấn DB thật. Nó chứng minh `@PreAuthorize` có thể chặn method theo object owner. Trong hệ thống thật, phải xác định ownership từ **dữ liệu đáng tin trong database**, không lấy từ JSON do caller tự khai báo. Ví dụ nếu document ID `doc-7` thuộc Bob nhưng caller truyền `owner=alice`, check owner theo path sẽ sai. Khi đó policy phải kiểm `document.ownerId` từ repository hoặc `PermissionEvaluator`. Bài tập mục 30 đề cập cách nâng cấp.

### 15.1. Controller không lặp logic phân quyền

**`src/main/java/com/example/securitylesson/AccountController.java`**

```java
package com.example.securitylesson;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final AccountService accounts;

    public AccountController(AccountService accounts) {
        this.accounts = accounts;
    }

    @GetMapping("/{owner}")
    public AccountSummary read(@PathVariable String owner) {
        return accounts.read(owner);
    }
}
```

Controller chỉ chuyển vào service. HTTP layer yêu cầu authenticated, service dùng method security để quyết định đúng owner/admin. Việc gọi `accounts.read("bob")` từ một Spring bean khác cũng đi qua proxy nếu gọi **qua bean proxy**, do đó không phải chỉ mỗi URL được bảo vệ.

**Self-invocation caveat:** Nếu một method trong AccountService gọi `this.read("bob")`, nó có thể bỏ qua Spring AOP proxy và `@PreAuthorize` không chạy. Trong production, thiết kế service boundary và test bypass paths này, không coi annotation như một kiểm soát tuyệt đối ở mọi lệnh gọi Java.

## 16. Test-only identities và password encoder

**`src/test/java/com/example/securitylesson/TestUsersConfig.java`**

```java
package com.example.securitylesson;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@TestConfiguration(proxyBeanMethods = false)
public class TestUsersConfig {

    @Bean
    PasswordEncoder testPasswordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService testUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN")
                        .build());
    }
}
```

Các passwords chỉ dành cho **test process**. `@TestConfiguration` không được component scan như production `@Configuration` thông thường; các test class cần `@Import(TestUsersConfig.class)`. Test HTTP Basic xác minh provider thực dùng `PasswordEncoder` so sánh password; `@WithMockUser` không chạy bước này.

Tuyệt đối không đưa credentials mẫu lên production, không chia sẻ một in-memory user database với môi trường thực, không log password. Khi dùng identity provider thực, tạo test sandbox/users tối thiểu và quyền hạn riêng; không gửi truy cập thử tới tài khoản khách hàng.

## 17. `@WebMvcTest`: security filters cần được áp dụng thật

**`src/test/java/com/example/securitylesson/AdminAccessMvcTest.java`**

```java
package com.example.securitylesson;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AdminController.class)
@Import({ApiSecurityConfig.class, TestUsersConfig.class})
class AdminAccessMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    AdminJobService jobs;

    @Test
    void anonymousGetIs401AndPromptsForCredentials()
            throws Exception {

        mvc.perform(get("/api/admin/metrics"))
                .andExpectAll(
                        status().isUnauthorized(),
                        header().string(
                                HttpHeaders.WWW_AUTHENTICATE,
                                containsString("Basic")));

        verifyNoInteractions(jobs);
    }

    @Test
    void incorrectPasswordIs401() throws Exception {
        mvc.perform(get("/api/admin/metrics")
                        .with(httpBasic("admin", "wrong-pass")))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(jobs);
    }

    @Test
    void authenticatedRegularUserIs403()
            throws Exception {

        mvc.perform(get("/api/admin/metrics")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void actualAdminCredentialsAreAllowed()
            throws Exception {

        mvc.perform(get("/api/admin/metrics")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.status").value("OK"));

        verifyNoInteractions(jobs);
    }

    @Test
    @WithMockUser(username = "fake-admin", roles = "ADMIN")
    void mockAdminRoleIsAlsoAllowedForAuthorizationOnly()
            throws Exception {

        mvc.perform(get("/api/admin/metrics"))
                .andExpect(status().isOk());

        // Mock user bypasses password provider.
    }

    @Test
    void rawAdminAuthorityWithoutRolePrefixIs403()
            throws Exception {

        mvc.perform(get("/api/admin/metrics")
                        .with(user("operator").authorities(
                                new SimpleGrantedAuthority("ADMIN"))))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void adminPostWithoutCsrfIs403ButHasNoSideEffect()
            throws Exception {

        mvc.perform(post("/api/admin/reindex")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void adminPostWithInvalidCsrfIs403()
            throws Exception {

        mvc.perform(post("/api/admin/reindex")
                        .with(httpBasic("admin", "admin-pass"))
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void userPostWithValidCsrfStillNeedsAdminRole()
            throws Exception {

        mvc.perform(post("/api/admin/reindex")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void adminPostWithCsrfIsAcceptedAndCallsJobOnce()
            throws Exception {

        when(jobs.acceptReindexRequest()).thenReturn(1);

        mvc.perform(post("/api/admin/reindex")
                        .with(httpBasic("admin", "admin-pass"))
                        .with(csrf()))
                .andExpectAll(
                        status().isAccepted(),
                        jsonPath("$.acceptedRequestNumber").value(1));

        verify(jobs).acceptReindexRequest();
    }
}
```

Lớp có **10 test methods**. Test với `@MockitoBean` chỉ mock **AdminJobService**, còn `ApiSecurityConfig`, HTTP Basic filters, CSRF filter, MVC routing và request authorization là thật trong test context. Nếu test anonymous 401 hoặc user 403 fail vì route bị mở, bộ này nhận ra.

**Tại sao `verifyNoInteractions(jobs)`?** Một status 403 sau khi service đã queue một job vẫn là lỗi bảo mật. Test còn đòi hỏi **không có side effect** ở service boundary. Trong integration test với DB/queue thật cần assert hậu điều kiện trên external state, vì Mockito chỉ quan sát bean mock.

### 17.1. Vì sao test thiếu CSRF phải riêng?

Hai tests:

- `adminPostWithoutCsrfIs403...`: kiểm CSRF protection.
- `userPostWithValidCsrfStillNeedsAdminRole`: kiểm **authorization**.

Nếu viết user POST không kèm csrf rồi chỉ assert 403, bạn không biết role rule đang hoạt động hay không. Nguyên tắc này cũng áp dụng cho PUT/PATCH/DELETE khi CSRF được bật.

### 17.2. Role test và password test bảo vệ những việc khác nhau

`actualAdminCredentialsAreAllowed` dùng `httpBasic`, đi qua password provider. `mockAdminRoleIsAlsoAllowedForAuthorizationOnly` dùng `@WithMockUser`, bypass credentials để kiểm quyết định role. Cả hai có ích nhưng không được thay thế nhau. Test có `@WithMockUser` vẫn có thể xanh khi password encoder, account lock hoặc login flow của production bị sai.

## 18. `@SpringBootTest`: kiểm ownership với service thật

**`src/test/java/com/example/securitylesson/AccountAccessIntegrationTest.java`**

```java
package com.example.securitylesson;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = SecurityLessonApplication.class)
@AutoConfigureMockMvc
@Import(TestUsersConfig.class)
class AccountAccessIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AccountService accounts;

    @Test
    void anonymousCallerCannotReadEvenOwnLookingPath()
            throws Exception {

        mvc.perform(get("/api/accounts/alice"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidPasswordIsRejectedAtAuthentication()
            throws Exception {

        mvc.perform(get("/api/accounts/alice")
                        .with(httpBasic("alice", "not-the-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadAlice() throws Exception {
        mvc.perform(get("/api/accounts/alice")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.owner").value("alice"),
                        jsonPath("$.status").value("ACTIVE"));
    }

    @Test
    void aliceCannotReadBob() throws Exception {
        mvc.perform(get("/api/accounts/bob")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadBob() throws Exception {
        mvc.perform(get("/api/accounts/bob")
                        .with(httpBasic("bob", "bob-pass")))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.owner").value("bob"));
    }

    @Test
    void adminCanReadOtherOwnersAccount()
            throws Exception {

        mvc.perform(get("/api/accounts/bob")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.owner").value("bob"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directServiceCallCannotBypassOwnerRule() {
        assertThrows(AccessDeniedException.class,
                () -> accounts.read("bob"));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void methodAuthorizationAlsoAllowsAdmin() {
        AccountSummary result = accounts.read("bob");

        assertEquals("bob", result.owner());
    }
}
```

Có **8 test methods**. Hai bài cuối gọi trực tiếp **AccountService bean thật** (có method security proxy) thay vì chỉ đi qua controller. Điều này chứng minh access rule không chỉ nằm trong URL matcher. Khi `@EnableMethodSecurity` bị bỏ hoặc `@PreAuthorize` bị xóa, test Alice gọi `accounts.read("bob")` sẽ không còn ném `AccessDeniedException` và suite fail.

**Quan trọng:** `@SpringBootTest + @AutoConfigureMockMvc` dựng application context rộng hơn `@WebMvcTest` nhưng `MockMvc` vẫn là servlet invocation **không qua TCP socket**. Nó phù hợp để kiểm filter chain + controller + real service cùng context. Nếu cần test real HTTP, dùng `webEnvironment=RANDOM_PORT` với HTTP client và xác minh thêm cookies, TLS hoặc proxy.

## 19. Hướng dẫn chạy project

Với Java 17 và Gradle wrapper (đã tạo theo chuẩn dự án), chạy:

```bash
./gradlew test --tests com.example.securitylesson.AdminAccessMvcTest --tests com.example.securitylesson.AccountAccessIntegrationTest
```

PowerShell:

```powershell
.\gradlew.bat test --tests com.example.securitylesson.AdminAccessMvcTest --tests com.example.securitylesson.AccountAccessIntegrationTest
```

Tổng dự kiến:

| Lớp | Số `@Test` | Trọng tâm |
|---|---:|---|
| `AdminAccessMvcTest` | **10** | Anonymous/invalid Basic, 403 role, admin 200, CSRF 403, allowed POST 202 |
| `AccountAccessIntegrationTest` | **8** | Anonymous/invalid password, owner vs non-owner, admin, method security proxy |
| **Tổng** | **18** | Các trạng thái chưa xác thực, thiếu quyền và được phép |

Dự kiến `BUILD SUCCESSFUL` nếu dependency resolution/Java/source phù hợp. **Đây là kết quả dự kiến sau khi rà soát mã, không phải tuyên bố tôi đã chạy Gradle trong repository của bạn.** Report JUnit thông thường ở `build/reports/tests/test/index.html`.

Nếu chỉ chạy một nhóm test bằng IDE và pass, vẫn cần chạy cả hai trong suite: test slices/contexts khác nhau có thể phát hiện cấu hình security bị thiếu ở một đường khởi tạo. Không dùng account/password thật để thử lại khi test lỗi.

## 20. Phân biệt test authN và authZ: checklist của reviewer

Một request trả 401:

- Có thật filter chain đang chạy hay controller tự trả 401?
- Thiếu credential, sai password, account disabled/locked, token expired hay invalid signature?
- Có `WWW-Authenticate` challenge đúng protocol không?
- Có lộ lý do nhạy cảm (“user exists”, “wrong user”) không?
- Có xảy ra gọi database/service có side effect trước khi từ chối không?

Một request trả 403:

- Caller đã authenticated chưa?
- Nếu là POST, CSRF token đã hợp lệ **trước khi kết luận thiếu role** chưa?
- Security rule thiếu `ROLE_` hay scope mapping không khớp?
- Tài nguyên có thuộc owner/tenant khác không?
- Method annotation có chạy qua proxy thật không?
- Access denied response có trả dữ liệu nhạy cảm trong body/headers không?

Một request được cho phép:

- Đúng role/scope/owner và HTTP method?
- Response chứa **đúng resource**, không chỉ 200 rỗng?
- Side effect được phép xảy ra đúng một lần?
- Không được phép nâng quyền bằng cách đổi path/query/body?
- Nếu logic có transaction, record/outbox trạng thái có hợp lệ không?

**Đừng đặt một bộ assertion chỉ nhìn HTTP status rồi dừng.** Hậu điều kiện data và “không có side effect” làm bài test có giá trị bảo mật thực sự.

## 21. `@WithMockUser`, `@WithUserDetails` và `httpBasic`

| Cơ chế | Tạo nguồn danh tính | Có kiểm password/decoder thật? | Thích hợp |
|---|---|---|---|
| `@WithMockUser` | Spring Security Test tự tạo fake principal | **Không** | Rule/role/method security |
| `user("alice").roles("USER")` | MockMvc RequestPostProcessor | **Không** | Case principal cho một request |
| `@WithUserDetails("alice")` | Lấy UserDetails từ test context | Không nhất thiết chạy password authentication | Principal custom và role mapping của UserDetailsService |
| `httpBasic("alice","alice-pass")` | Header Basic đi vào filter chain | **Có**, nếu auth provider/filter thật được cấu hình | Credential success/failure và Basic challenge |
| `jwt()` | Fake JwtAuthenticationToken trong test | **Không kiểm signature** | Scopes/claims authorization với resource server |
| Real signed JWT + decoder | Bearer qua filter và decoder thật | **Có** theo cấu hình key/issuer/audience | Token validation/security integration |

Với tests cần **kiểm xác thực thực sự**, không chỉ dùng `@WithMockUser`. Với tests chỉ cần **kiểm role ownership**, dùng mock principal hợp lệ thường nhanh hơn và tập trung hơn.

### 21.1. `@WithMockUser` có xóa SecurityContext sau test không?

Spring Security Test có `WithSecurityContextTestExecutionListener` để setup context trước method và cleanup sau method. Không tự giữ `SecurityContextHolder` trong static field. Nếu application tự đưa Principal vào custom ThreadLocal/MDC hoặc executor, phải dọn các context ấy riêng; Spring Security Test không thể kiểm soát mọi mutable state do code bạn tạo.

## 22. Method security và self-invocation

`@PreAuthorize` hoạt động với Spring-managed bean qua proxy. Ví dụ:

```java
@Service
class ServiceA {

    @PreAuthorize("hasRole('ADMIN')")
    public void privileged() { }

    public void outer() {
        this.privileged(); // CẢNH BÁO: có thể bypass proxy
    }
}
```

Đây là snippet minh họa, không phải file trong demo. Khi dùng proxy-based Spring AOP, self-invocation không đi qua interceptor của proxy, có thể bỏ kiểm `@PreAuthorize`. Một test gọi `accounts.read(...)` từ context ngoài bean (như trong mục 18) bảo vệ đường đúng, nhưng không tự bắt mọi đường gọi nội bộ. Khi application có code tự gọi cùng bean, tách method sang bean riêng hoặc thiết kế authorization layer phù hợp và viết regression test cho chính path ấy.

Tương tự, method security trên một object được tự tạo bằng `new AccountService()` ngoài Spring container **không chạy** proxy. Test trực tiếp Java object chỉ có thể kiểm domain logic, không được dùng để chứng minh annotation đã được Spring áp dụng.

## 23. Cẩn thận với `@WebMvcTest` bỏ sót SecurityFilterChain

Một test:

```java
@WebMvcTest(AdminController.class)
@AutoConfigureMockMvc(addFilters = false)
class WeakSecurityTest {
    // ...
}
```

là **phản ví dụ** khi mục tiêu kiểm authentication/authorization: `addFilters=false` bỏ security filters, test không còn quan sát thật các rule ở HTTP layer. Tương tự, nếu `@WebMvcTest` không import custom `SecurityFilterChain` mà app production dùng, nó có thể chạy một **default security configuration khác**; assert 401/403 không còn chứng minh policy thực.

Trong demo đã dùng:

```java
@WebMvcTest(AdminController.class)
@Import({ApiSecurityConfig.class, TestUsersConfig.class})
class AdminAccessMvcTest {
    // ...
}
```

Nhờ vậy URL/CSRF rules là security config cùng class với application. Với production có nhiều `SecurityFilterChain` theo `securityMatcher`, cần test cụ thể rule ordering, chain selection, management endpoints và path prefix; không giả định một chain áp dụng mọi request.

### 23.1. Chỉ mock đúng phần cần mock

Trong MVC test, mock side-effect service (AdminJobService) để verify zero calls; **không mock SecurityFilterChain hoặc chính authorizer đang được kiểm**. Trong full context, dùng thật AccountService + @PreAuthorize. Test bị sai ranh giới thường xanh vì “mock luôn quyết định được phép” thay vì kiểm policy.

## 24. Resource existence, ownership và 404 vs 403

Một API có thể tránh tiết lộ “account/document B tồn tại” cho user A bằng cách trả **404** thay vì 403 trong một số tình huống. Đây là **policy sản phẩm và bảo mật**, không phải quy tắc universal của Spring Security.

Khi chọn 404 để che tài nguyên:

- Owner được phép + resource tồn tại → 200.
- Owner được phép + resource không tồn tại → 404.
- Non-owner truy cập resource tồn tại → 404 (nếu policy che existence).
- Anonymous vẫn có thể 401 khi authentication bắt buộc.
- Logs nội bộ có thể ghi reason an toàn, response public không tiết lộ owner.
- Time-based side channels và khác biệt error response cần được đánh giá.

**Không đổi expected 403 thành 404 chỉ vì test fail.** Hãy ghi rõ contract và kiểm **đúng điều ứng dụng hứa**. Demo chọn 403 để người học phân biệt trạng thái, và không có database resource-not-found.

## 25. JWT Resource Server: 401/403 không giống HTTP Basic hoàn toàn

Với OAuth2 resource server dùng Bearer JWT:

- Không gửi Bearer token hoặc token không hợp lệ thường dẫn tới 401 và Bearer challenge.
- Authenticated JWT nhưng thiếu authority/scope có thể dẫn tới 403.
- Claim `scope`/`scp` có thể được map thành `SCOPE_x`; role `ROLE_ADMIN` không tự đến từ `roles` claim trừ khi đã cấu hình converter.
- Access denied quyết định bởi `AuthorizationManager` và method security; security filters phải được include khi test.
- JWT signature/issuer/audience/clock skew phải được test bằng decoder thật ở test mức tích hợp.

**Snippet cho một API đã được cấu hình resource server thực**:

```java
// Chỉ minh họa; không dùng trực tiếp với cấu hình HTTP Basic demo.
// Cần spring-security-test và SecurityFilterChain sử dụng JWT resource server.
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports:read"))))
   .andExpect(status().isOk());
```

Test này **không chứng minh JWT có signature hợp lệ** vì `jwt()` đưa Authentication giả vào SecurityContext. Để kiểm invalid signature/issuer/audience/expiry, gửi **Bearer token thật được ký bằng test key**, chạy `JwtDecoder`/opaque token introspector thật hoặc mock tại boundary đã chọn và kiểm behavior rõ. Không sao chép keys hoặc JWT production vào fixtures.

### 25.1. Không nhầm 403 do scope với 403 do CSRF

Nếu token bearer được đưa vào một POST và ứng dụng bật CSRF, thiếu CSRF vẫn có thể 403 **trước** khi kiểm scopes. Khi kiểm authorization, cần xét CSRF policy riêng cho API; không thêm `csrf()` mù quáng nếu ứng dụng được thiết kế stateless bearer-only và CSRF đã được phân tích/tắt có chủ đích.

## 26. Bảng negative cases theo vai trò và dữ liệu

| Kịch bản | Test mong đợi | Rủi ro bị bắt |
|---|---|---|
| Không Authorization | 401 | Anonymous access |
| Basic sai password | 401 | Authentication bypass |
| Valid user thiếu admin role | 403 | Privilege escalation |
| Authority `ADMIN` thiếu prefix | 403 trong policy `hasRole` | Sai role mapping |
| Admin GET metrics | 200 | False deny |
| User GET own account | 200 | False deny/owner logic |
| User GET account người khác | 403 | IDOR |
| Admin GET account người khác | 200 | Role override |
| Admin POST không CSRF | 403 | CSRF protection |
| User POST có CSRF | 403 | Authorization không bị test CSRF che |
| Admin POST có CSRF | 202 và gọi service 1 lần | Allowed operation |
| Denied POST | No service call / no DB write | Side effect before deny |
| Method direct call không qua controller | Deny/allow đúng | Business layer bypass |
| JWT thiếu scope | 403 (JWT API contract) | Scope mapping |
| JWT sai issuer/signature | 401 (real decoder test) | Token validation |
| Disabled user | 401/contract error | Account status bypass |
| Cross-tenant resource | 403/404 theo policy | Multi-tenant leakage |
| Verb không được phép | 403/405 theo matcher/mapping | HTTP method bypass |
| Public endpoint | 200 không cần auth, nếu thật sự public | Overblocking |
| Exception dispatch/forward | Không bypass | Dispatcher-type security gaps |

**Không phải tất cả tình huống đều thuộc demo HTTP Basic.** Một suite production cần áp dụng những dòng phù hợp với threat model/auth mechanism và ghi rõ lý do bỏ những dòng không liên quan.

## 27. Security tests nên chạy trên dữ liệu nào?

Với bài ownership thực sự, hãy seed ít nhất:

- User A có account/document A.
- User B có account/document B.
- User admin có quyền xem nhiều resource.
- Một resource khác tenant với ID khó đoán và một ID dễ đoán (để phát hiện path swapping).
- Một resource bị khóa/archived nếu status ảnh hưởng quyền.
- Một operation có side effect ghi row/outbox/event để assert forbidden thực sự không chạm state.

Nếu test dùng DB thật, query hậu điều kiện sau denied request:

```sql
SELECT COUNT(*) FROM audit_events
WHERE actor_id = 'alice' AND action = 'DELETE_BOBS_DATA';
```

Expected bằng 0 khi Alice bị cấm. Đây là snippet SQL chỉ minh họa; database/fixtures/columns phải phản ánh schema thật, không được chạy lên production. Với event broker, có thể kiểm không publish message vào test topic hoặc use outbox readback. Mock interaction checks rẻ nhưng chưa thể thay thế hậu điều kiện trên data store.

### 27.1. Những tests bị gọi “allowed” nhưng vẫn yếu

`assert status=200` chưa bảo đảm dữ liệu được phép thực sự trả về đúng owner. Một bug có thể trả 200 với account Bob cho request của Alice. Nên assert DTO owner/id/tenant và các trường được phép. Với API trả danh sách, kiểm **không có phần tử từ tenant khác**, kể cả khi query filter bị quên.

## 28. Security context isolation và concurrency

Spring Security thường lưu `SecurityContext` theo request/thread. Trong test:

- `@WithMockUser` cleanup SecurityContext sau method qua test listener.
- Không đặt user hiện tại vào static field/Singleton mutable state.
- Với `@Async`/CompletableFuture/thread pool, SecurityContext không tự truyền đúng sang mọi thread. Có thể dùng `DelegatingSecurityContextExecutor` hoặc task decorator/propagation infrastructure được thiết kế phù hợp.
- Không vô tình reuse Authentication của user A cho request B vì ThreadLocal không được clear.
- Với Reactor/WebFlux, dùng `ReactiveSecurityContextHolder`, không dựa vào servlet ThreadLocal.
- Không in token/principal secrets vào logs.

**Test concurrency có giá trị:** hai users A/B gửi request đồng thời tới hai owners; capture response/DB state để chứng minh A không nhận dữ liệu B. Một unit test tuần tự A rồi B phát hiện stale singleton state đơn giản, nhưng không chứng minh an toàn dưới thread races.

### 28.1. Đừng giấu test bằng `@DirtiesContext`

Nếu test A làm bẩn SecurityContextHolder hoặc global state, `@DirtiesContext` khởi tạo lại Spring beans có thể vô tình làm suite xanh, nhưng không sửa lỗi cleanup/thread-local. Dùng listener, request scope và explicit clear/restoration; chỉ dùng `@DirtiesContext` khi chính bean context state cần bị loại.

## 29. HTTP methods, matcher order và deny-by-default

Có ba loại rule:

1. Route-specific: `/api/admin/**` chỉ admin.
2. Generic authenticated: `/api/accounts/**` có user.
3. Fallback: `anyRequest().denyAll()`.

Thứ tự rất quan trọng: nếu đặt `anyRequest().permitAll()` lên đầu, route admin có thể không bao giờ áp rule. Tương tự, một filter chain có `securityMatcher("/api/**")` khác chain dành cho actuator có thể ảnh hưởng endpoints nằm ngoài matcher.

**Test cần có cả negative lẫn positive**: nếu tất cả requests đều 403, hệ thống rất “chặt” nhưng bị **false deny**; nếu tất cả đều 200, hệ thống thuận tiện nhưng unsafe. Với method-sensitive authorization, ví dụ GET đọc account khác POST xóa, dùng `requestMatchers(HttpMethod.DELETE, "/api/accounts/**")` và test các verbs. Không dùng GET test làm bằng chứng DELETE cũng được bảo vệ.

### 29.1. CORS preflight và OPTIONS

Browser có thể gửi OPTIONS preflight trước cross-origin request. Nếu app có CORS config, một preflight không giống một business API call; 401/403/200/204 ở preflight phụ thuộc cấu hình CORS/security. Không diễn giải preflight 403 thành user không có role. Kiểm trusted origins, methods, headers, credentials và actual request riêng, nhất là khi CORS/CSRF cùng hiện diện.

## 30. Bài tập tự đánh giá

### Bài A — 401 hay 403?

Một user chưa đăng nhập gọi `GET /api/admin/metrics`. Một user đã đăng nhập có ROLE_USER cũng gọi URL ấy. Với HTTP Basic config của demo, response nào?

**Đáp án:** Anonymous 401 với Basic challenge; user đã xác thực thiếu ROLE_ADMIN 403.

### Bài B — admin POST vẫn 403

Admin dùng credentials đúng POST `/api/admin/reindex` nhưng nhận 403. Vì sao có thể xảy ra dù role hợp lệ? Test nào phân biệt?

**Đáp án:** Thiếu/sai CSRF. Thêm `with(csrf())` để kiểm authorization; test thiếu CSRF riêng để kiểm CSRF filter.

### Bài C — mock user vs password

Một `@WithMockUser(roles="ADMIN")` test pass dù password database của admin đã bị disable. Có thể khẳng định login/authentication production đúng không?

**Đáp án:** Không. Mock user bypass authentication provider. Dùng HTTP Basic/form login/JWT qua filter với provider/decoder thật và disabled-account fixtures.

### Bài D — owner privilege escalation

Alice truy cập `/api/accounts/bob` và nhận 200. Vì sao `requestMatchers("/api/accounts/**").authenticated()` chưa đủ? Sửa ở đâu?

**Đáp án:** Rule chỉ yêu cầu logged-in; chưa check ownership. Thêm authorization theo owner/tenant trong service/repository, kiểm Alice→Bob 403/404 theo contract và không trả dữ liệu Bob.

### Bài E — method security không chạy

Bạn đã đặt `@PreAuthorize` nhưng test vẫn cho Alice đọc Bob. Điều tra gì?

**Đáp án:** Có `@EnableMethodSecurity` không; bean có phải Spring proxy không; có self-invocation không; SpEL parameter name đúng không; service mock/tạo bằng new không; method invocation có đi qua proxy không.

### Bài F — role name

Principal chỉ có authority `ADMIN`, rule dùng `hasRole("ADMIN")`. Được phép không? Test cần dùng API nào nếu muốn check authority không prefix?

**Đáp án:** Không theo mặc định. `hasRole` mong ROLE_ADMIN. Nếu muốn check literal ADMIN, dùng `hasAuthority("ADMIN")` theo policy.

### Bài G — denied nhưng side effect đã xảy ra

Controller gọi `jobs.enqueue()` rồi mới check role và trả 403. Test status 403 có phát hiện không?

**Đáp án:** Không. Assert `verifyNoInteractions(jobs)` hoặc DB/outbox trạng thái không thay đổi cho denied request.

### Bài H — JWT test signature

Một test `mvc.perform(get(...).with(jwt()))` trả 200. Có chứng minh token hết hạn hoặc signature không hợp lệ bị reject không?

**Đáp án:** Không. `jwt()` đưa principal giả vào SecurityContext. Cần test thật qua JwtDecoder/introspection với invalid/expired/signed tokens.

### Bài I — service direct call

Một batch job gọi `AccountService.read("bob")` bằng security context Alice mà không đi qua MVC. Nếu rule chỉ đặt trên URL, dữ liệu có an toàn không?

**Đáp án:** Không nhất thiết. Method-level authorization và trusted resource ownership phải được bảo vệ trong service boundary (hoặc một central authorization component).

### Bài J — false deny

Sau khi tăng security, cả Alice→Alice và Alice→Bob đều 403. Chỉ có negative test Alice→Bob thì suite vẫn xanh. Điều này có ổn không?

**Đáp án:** Không. Cần positive owner→owner và admin→other owner tests để bắt overblocking.

### Bài K — 404 để che tài nguyên

API muốn không cho user A biết Bob có document `doc-7`. Test nên mong 403 hay 404?

**Đáp án:** Theo security API contract đã quyết định, có thể 404 để che existence. Đừng đổi expected status chỉ để tránh sửa access rule.

### Bài L — tắt filters

Developer thêm `@AutoConfigureMockMvc(addFilters=false)` rồi tests controller pass. Đây có phải bằng chứng API secure không?

**Đáp án:** Không. Bỏ security filters khiến test không chạy authentication/authorization HTTP thật; bật lại filters và import SecurityFilterChain đúng.

## 31. Troubleshooting thực tế

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm |
|---|---|---|
| Anonymous trả 200 | `permitAll` sai hoặc filters bị tắt | SecurityFilterChain được áp dụng? |
| Anonymous trả 302 thay 401 | Form login/redirect entry point | AuthenticationEntryPoint thực |
| Anonymous POST trả 403 thay 401 | CSRF lọc request trước auth | Test có CSRF rồi assert 401 |
| Valid user luôn 401 | Password encoder/provider/credentials sai | `httpBasic` và TestUsersConfig |
| User thiếu role được 200 | Matcher order/rule rộng | URL rules, ROLE_ADMIN |
| Admin có ROLE_ADMIN nhưng 403 | CSRF, URL rule khác, method security | GET vs POST, token CSRF |
| Raw ADMIN authority không qua rule | ROLE_ prefix | `hasRole` vs `hasAuthority` |
| Alice đọc Bob được | IDOR/business owner guard thiếu | Service @PreAuthorize + DB ownership |
| @PreAuthorize bị bỏ qua | Không enable, self-invocation, bean không proxy | @EnableMethodSecurity, bean wiring |
| @WithMockUser pass nhưng login thật fail | Authentication bị bypass bởi mock | Real provider/decoder integration |
| Jwt test pass nhưng invalid signature accepted | jwt() bypass decoder | Real JwtDecoder tests |
| CSRF tests xanh nhưng authorization sai | User POST không có csrf | Thêm csrf để isolate authZ |
| Test denied vẫn ghi DB | Side effect trước authorization | Assert no calls/DB unchanged |
| Một test pass, suite fail | SecurityContext/custom ThreadLocal leak | Reset/context isolation |
| WebMvcTest nạp default chain khác app | Thiếu @Import config | Import đúng SecurityConfig |
| OPTIONS bị chặn lạ | CORS preflight không được cấu hình | CORS/security matching |
| Response trả lỗi nhạy cảm | Exception handler leak internals | Sanitized error contract |
| Full context test chậm | Boot app context rộng | Slice cho URL checks, full cho owner/service |

### 31.1. Đường debug gợi ý

1. Xác nhận **đúng filter chain** được dùng trên request path/method.
2. Xác nhận input credentials và authentication mechanism, không log password/token.
3. Xác nhận `Authentication` thực tế có name/authorities nào.
4. Kiểm role prefix/scope conversion/tenant context.
5. Nếu POST/PATCH/DELETE, kiểm CSRF trước khi kết luận role.
6. Nếu endpoint trả 200 không mong đợi, kiểm URL matcher và method-level guard.
7. Nếu object-level access sai, kiểm nguồn ownership từ trusted DB/domain.
8. Nếu test có mocks, xác định security policy đang bị mock/bypass ở đâu.
9. Kiểm side effect của denied requests trên service/database.
10. Chạy negative + positive tests cùng suite để tránh overblocking regression.

## 32. Checklist review trước khi merge

- [ ] Có ít nhất một test **anonymous** cho protected route.
- [ ] Có test **invalid credentials** đi qua authentication provider/decoder phù hợp.
- [ ] Có test **authenticated nhưng thiếu quyền** cho role/scope policy.
- [ ] Có test **đúng quyền được phép**, không chỉ toàn các test 403.
- [ ] Role/authority `ROLE_`, `SCOPE_` mapping nhất quán.
- [ ] `SecurityFilterChain` thật được load trong HTTP security tests.
- [ ] MockMvc filters không bị tắt khi đang test authentication/authorization.
- [ ] `@WithMockUser` không bị nhầm thành test validate password/JWT signature.
- [ ] CSRF được kiểm riêng trên unsafe HTTP methods.
- [ ] Test denied POST có CSRF hợp lệ để phân biệt role denial.
- [ ] Có service/business-level test cho ownership/tenant/id-based access.
- [ ] Có test owner A không đọc/sửa/xóa tài nguyên của B.
- [ ] Có test admin/service role được phép truy cập theo contract.
- [ ] Unauthorized/forbidden operations **không tạo side effects**.
- [ ] Không tự chuyển 403 thành 404 nếu chưa có API contract che resource existence.
- [ ] Method security có `@EnableMethodSecurity` và calls đi qua Spring proxy.
- [ ] Self-invocation hoặc objects created bằng `new` không bị dùng làm bằng chứng method security.
- [ ] API có deny-by-default và rule ordering được kiểm.
- [ ] Authentication principals/credentials fixtures nằm ở test-only config.
- [ ] Test không dùng secrets/users production.
- [ ] Lỗi trả ra không lộ token, user enumeration hoặc internal details.
- [ ] Tests CORS/OPTIONS, redirects, reverse proxy nếu thuộc threat model.
- [ ] Trên JWT API có issuer/audience/signature/expiry validation tests thực.
- [ ] Concurrent requests không làm rò SecurityContext/tenant data.
- [ ] Có bằng chứng về DB/queue state cho các security-sensitive side effects.

**Kết luận:** Bộ kiểm thử bảo mật có giá trị phải kiểm đủ **ba nhánh**: chưa xác thực **bị chặn**, đã xác thực nhưng thiếu quyền **bị từ chối**, và caller đúng quyền **được thao tác chính xác**. Nhưng chỉ assert 401/403/200 chưa đủ: phải cô lập **lý do** từ chối (CSRF, authentication, role hay ownership), chạy đúng filter chain/bean proxy, xác minh không có side effects sau denied request và kiểm JWT/token tại boundary thật nếu đó là auth mechanism production. Một test cho phép owner A đọc A và từ chối đọc B thường quan trọng hơn hàng chục test chỉ khẳng định “admin endpoint có 403”.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Auto-configured MVC tests, @WebMvcTest và @SpringBootTest: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Security 6.5 — HTTP Basic authentication và 401 challenge: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security 6.5 — HTTP request authorization, hasRole/hasAuthority/denyAll: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method security @EnableMethodSecurity/@PreAuthorize: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security — Testing method security và @WithMockUser/@WithUserDetails: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
- Spring Security — Testing HTTP Basic with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF with with(csrf()): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — MockMvc and Spring Security setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- OWASP API Security Top 10 — Broken Object Level Authorization (API1): https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- RFC 9110 — HTTP status semantics 401, 403, 404: https://www.rfc-editor.org/rfc/rfc9110
