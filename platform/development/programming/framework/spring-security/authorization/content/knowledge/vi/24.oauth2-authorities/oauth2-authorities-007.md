# Kết hợp OAuth2 scope với quyền sở hữu và tenant

## 1. Vấn đề: có scope chưa có nghĩa được xem mọi tài liệu

Một access token OAuth2 mang scope `documents:read` cho biết bên phát hành đã cấp **phạm vi chức năng** đọc tài liệu cho client/người dùng theo quy ước của API. Nó **không tự chứng minh** người mang token là chủ sở hữu của `Document#42`, đang thuộc đúng tenant, có quyền với bản nháp của người khác, hay được xuất các trường dữ liệu nhạy cảm.

Xét hai khách hàng:

```text
TENANT_A / documentId=42 / owner=(issuer-1, sub-a) / DRAFT
TENANT_B / documentId=42 / owner=(issuer-1, sub-b) / DRAFT

Alice: JWT scope = "documents:read documents:write"
       member TENANT_A, subject sub-a
Bob:   JWT scope = "documents:read documents:write"
       member TENANT_B, subject sub-b

Cả hai có thể có username hiển thị = "alex".
```

Nếu chỉ dùng `@PreAuthorize("hasAuthority('SCOPE_documents:read')")` và gọi `repository.findById(42)`, bạn có thể vô tình mở dữ liệu tenant B cho Alice, hoặc cho phép người khác đọc DRAFT trong cùng tenant. Cần **kết hợp ba lớp**: 

1. **OAuth2 scope:** token được xác thực có authority của chức năng, ví dụ `SCOPE_documents:read`.
2. **Tenant membership/scope:** principal đã xác thực thực sự được quyền hoạt động trong tenant đang yêu cầu.
3. **Object-level authorization:** resource thuộc đúng tenant, trạng thái và owner/ACL thỏa rule cụ thể; thao tác ghi kiểm tra lại tại thời điểm cập nhật.

Bài thuộc nhóm **Quyền từ OAuth2** của Spring Security Authorization, hướng dẫn cơ chế, cấu hình Spring Security Resource Server, thiết kế policy và project Java 17+ với kiểm thử thực tế qua Spring AOP Method Security.

### Kết quả học tập

Sau bài, bạn có thể:

- Giải thích quan hệ giữa `scope`/`scp` claim và `SCOPE_` authorities trong Spring Security Resource Server.
- Phân biệt quyền *gọi API* với quyền *trên tài nguyên* và membership *trong tenant*.
- Dùng `@EnableMethodSecurity`, `@PreAuthorize`, policy bean nhận `Authentication` + tenant + ID để trả quyết định.
- Thiết kế identity bằng `(issuer, subject)` và owner/tenant thay vì username hiển thị.
- Cố tình kiểm thử hai tenant dùng **cùng document ID 42** và người dùng có cùng username, đảm bảo không có cross-tenant access.
- Chống race khi WRITE bằng SQL conditional update/optimistic locking, không chỉ kiểm tra trước method.
- Phân biệt 401, 403, 404; biết giới hạn của token lifetime, quyền bị thu hồi và các case machine-to-machine.
- Triển khai test Java 17+, Spring Security 6.5.x, Gradle và JUnit 5; phân biệt test authorization với test mật mã/kiểm chứng JWT.

## 2. Scope, authority, role, ownership và tenant là những khái niệm khác nhau

| Yếu tố | Ví dụ | Trả lời câu hỏi gì? | Có đủ để đọc DRAFT#42? |
| --- | --- | --- | --- |
| OAuth2 scope | `documents:read` | Token được cấp quyền loại thao tác nào? | **Không** |
| GrantedAuthority | `SCOPE_documents:read` | Spring Security thấy quyền chức năng nào? | **Không** |
| Role | `ROLE_EDITOR` | Actor có vai trò nào trong tổ chức? | Không, nếu chưa ràng buộc resource |
| Tenant membership | Alice thuộc TENANT_A | Actor được truy cập phạm vi dữ liệu nào? | Không, nếu là DRAFT của người khác |
| Owner | `issuer/sub-a` | Ai là chủ tài liệu? | Không, nếu thiếu scope chức năng |
| Object state | `DRAFT`, `PUBLISHED` | Chính sách nghiệp vụ cho phép hành động nào? | Phải đánh giá cùng các điều kiện khác |
| Explicit ACL | ACE `READ` cho actor/group | Actor có grant cụ thể trên đối tượng không? | Tùy toàn bộ policy |
| Resource database isolation | `WHERE tenant_id=? AND doc_id=?` / RLS | Những hàng nào thực sự được thấy/ghi? | Lớp bổ sung bắt buộc |

Scope thường **không mang danh sách ID tài liệu được phép xem**. Một access token có thể có scope `documents:read`, nhưng chỉ được xem một tập con tài liệu theo tenant và owner. Trong API nhiều tenant, `tenantId` ở URL/header cũng **không tự mang tính đáng tin**.

### 2.1. OAuth2 scope thuộc bên phát hành token, object permission thuộc domain

OAuth2 Authorization Server cấp token và scopes theo hợp đồng giữa client, người dùng, resource server. Resource Server nhận Bearer token, xác thực và diễn dịch scopes thành GrantedAuthorities. Application policy vẫn phải tra thông tin owner, tenant, resource state và permission grant nội bộ.

**Không nhầm:**

- `SCOPE_documents:read` **không** phải `ROLE_documents:read`.
- `hasRole('ADMIN')` mặc định kiểm tra authority có prefix `ROLE_`; `hasAuthority('SCOPE_documents:read')` kiểm tra đúng chuỗi scope authority.
- Một token có `documents:write` **không** mặc định có `documents:read` trừ khi Authorization Server/app policy định nghĩa rõ.
- Một scope không bao trùm mọi tenant; nếu token được cấp cho user thuộc nhiều tenant thì **membership và active tenant phải được kiểm soát phía server**.
- `sub` ổn định trong phạm vi một issuer; cùng `sub` từ hai issuer có thể chỉ hai người khác nhau. Tránh dùng `preferred_username` làm khóa owner toàn hệ thống.

## 3. Từ JWT scope đến `SCOPE_` trong Spring Security

### 3.1. Ví dụ JWT claim (dữ liệu minh họa, không phải token ký thật)

```json
{
  "iss": "https://idp.example.test",
  "sub": "sub-a",
  "aud": ["documents-api"],
  "exp": 2000000000,
  "scope": "documents:read documents:write",
  "preferred_username": "alex"
}
```

Với cấu hình Resource Server JWT thông thường, Spring Security đọc `scope` hoặc `scp` và chuyển từng scope thành authority có prefix `SCOPE_`:

```text
JWT scope="documents:read documents:write"
        |
        v
JwtAuthenticationConverter / JwtGrantedAuthoritiesConverter
        |
        +-- SCOPE_documents:read
        +-- SCOPE_documents:write
```

Tài liệu Spring Security 6.5 xác nhận default mapping này cho JWT và cũng mô tả `scope` từ introspection của opaque token. Với provider dùng custom claim hoặc prefix khác, phải cấu hình `JwtGrantedAuthoritiesConverter`, **không giả định mọi IdP đều phát cùng claim**.

Ví dụ kiểm tra một scope ở HTTP layer:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(r -> r
            .requestMatchers("/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("SCOPE_documents:read")
            .requestMatchers(HttpMethod.PUT, "/api/documents/**")
                .hasAuthority("SCOPE_documents:write")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Đây là **fragment**, cần imports như `HttpMethod`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` và resource-server dependencies/issuer configuration. Nó chỉ chặn chức năng ở HTTP layer. Khi client gọi `GET /api/documents/42`, vẫn cần policy **đúng tenant/owner** ở service/repository.

### 3.2. Cấu hình issuer và audience

Trong Spring Boot Resource Server JWT có thể cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test
```

Resource Server sẽ dùng cơ chế phù hợp để lấy khóa công khai và kiểm tra signature/timestamps/issuer. **Audience (`aud`) phù hợp với API của bạn phải được validate thêm** theo phiên bản và cấu hình đang dùng; không coi chỉ có `issuer-uri` là đã đủ kiểm tra audience. Có thể định nghĩa `OAuth2TokenValidator<Jwt>` kết hợp `JwtValidators` và audience validator cụ thể.

Ngoài chữ ký và claims cơ bản còn cần kiểm tra loại token, thuật toán được tin cậy, scope semantics, tenant membership, thu hồi phiên/quyền theo threat model. Không tự parse base64 JWT rồi xem claims là đã xác thực. JWT là **bearer credential**: ai sở hữu token hợp lệ có thể sử dụng trong thời hạn của nó nếu không có các biện pháp sender-constrained hoặc revocation khác.

### 3.3. JWT, opaque token và custom claim

- JWT: resource server xác thực signature, issuer, hạn dùng; scope được ánh xạ qua `JwtAuthenticationConverter`.
- Opaque token: resource server introspect với Authorization Server; scope introspection thường được chuyển thành `SCOPE_` authorities.
- Custom `roles` hoặc `permissions` claim: không tự hiển thị như `SCOPE_` nếu chưa được converter cấu hình.
- `scp` có thể là danh sách thay vì chuỗi, tùy provider; hãy test claim shape thật từ IdP.
- Scope do Authorization Server cấp có thể mô tả quyền **client**, không hoàn toàn tương đương quyền từng user. Đặc biệt với `client_credentials`, không có user owner theo nghĩa thông thường.

## 4. Quy tắc ba lớp: function + tenant + object

Cho dịch vụ quản lý tài liệu đa tenant:

```text
           OAuth2 JWT đã xác thực
                    |
                    v
        hasAuthority(SCOPE_documents:read)
                    |
             ALLOW? | NO -> 403
                    v YES
   Principal = verified (issuer, subject)
                    |
                    v
           server-side tenant membership
                    |
             ALLOW? | NO -> DENY
                    v YES
     Load document by (tenant_id, document_id)
                    |
                    v
      Resource exists in same tenant?
                    |
             NO -> DENY/404 according to API
                    v YES
  PUBLISHED OR (DRAFT and owner issuer/sub matches)?
                    |
             NO -> DENY
                    v YES
     Service returns authorized DTO/projection
```

### 4.1. Chính sách READ

`canRead(A, T, D)` yêu cầu **tất cả**:

1. Actor A đã authenticated từ nguồn JWT hợp lệ.
2. Có authority `SCOPE_documents:read`.
3. Issuer/sub của A được server xác minh có membership tenant T.
4. D là resource của T; truy vấn bằng **tenant + document ID**, không bằng ID đơn lẻ.
5. D là `PUBLISHED` hoặc, nếu DRAFT, owner là **cùng issuer/sub** với actor.

`PUBLISHED` trong bài nghĩa “thành viên cùng tenant có scope READ được xem”, **không có nghĩa public ra internet**.

### 4.2. Chính sách WRITE

`canWrite(A,T,D)` yêu cầu:

1. Authority `SCOPE_documents:write` và membership T.
2. D thuộc T; **DRAFT** và owner bằng `(issuer,sub)` của A.
3. Tại điểm ghi, SQL vẫn áp lại tenant, owner, state (và version nếu có).

Tại sao phải kiểm tra lần hai? Một `@PreAuthorize` pass lúc t0, nhưng giữa t0 và câu UPDATE, tài liệu có thể đổi owner/state hoặc ACL bị thu hồi. Đây là **TOCTOU (time-of-check/time-of-use)**. Với trạng thái, có thể dùng conditional UPDATE; với grant/revoke chặt chẽ, cần transaction/recheck version từ nguồn quyền phù hợp.

### 4.3. CREATE và LIST

`CREATE` không có object để tra trước; kiểm tra `SCOPE_documents:write` + membership trong tenant được yêu cầu. Server gán **owner issuer/sub, tenant và status=DRAFT**; client không được tự chỉ định owner bất kỳ.

`LIST` dùng `SCOPE_documents:read` + membership, rồi lọc tại query theo **tenant** và visibility từng dòng. Không tải tất cả tenant rồi chỉ dựa vào `@PostFilter` hoặc Java filtering nếu dữ liệu lớn/pagination quan trọng.

### 4.4. Các quyết định không được suy ra

| Kiểm tra đơn | Vì sao không đủ? |
| --- | --- |
| Chỉ `SCOPE_documents:read` | Không xét tenant và owner |
| Chỉ membership TENANT_A | Không xét scope hoặc owner DRAFT |
| Chỉ `ownerUsername == auth.getName()` | Username hiển thị có thể trùng; `JwtAuthenticationToken.getName()` mặc định là `sub`, không bảo đảm policy owner cùng format |
| Chỉ `WHERE document_id = 42` | Hai tenant có thể cùng ID |
| Chỉ `@PreAuthorize` trước WRITE | Race; câu UPDATE phải ràng buộc owner/state |
| Chỉ JWT `tenant_id` claim | Claim được ký chưa đảm bảo actor còn membership hoặc được chọn tenant đó |
| Chỉ ROLE_ADMIN | Chưa chứng minh scope, tenant hoặc object grant |
| Chỉ RLS | RLS giới hạn hàng nhưng không tự quyết định READ/WRITE theo nghiệp vụ |

## 5. Danh tính và tenant membership đúng ranh giới tin cậy

Một identity nên được diễn đạt bởi `(issuer, subject)`, hoặc một **internal stable user ID** đã liên kết hai thuộc tính này. `preferred_username`, email và tên hiển thị không nhất thiết duy nhất hay bất biến. Trong test, cả Alice và Bob đều tên `alex`, nhưng có subject khác:

```text
Identity Alice: (iss=https://idp.example.test, sub=sub-a)
Membership: TENANT_A

Identity Bob:   (iss=https://idp.example.test, sub=sub-b)
Membership: TENANT_B

Request Alice: GET /api/tenants/TENANT_B/documents/42
-> scope READ đúng, nhưng membership sai -> DENY.
```

Production cần chọn **active tenant** phía server hoặc xác minh quyền switch tenant trước khi xử lý URL có tenant. Header `X-Tenant-Id` không tự tăng quyền; JWT claim không được dùng ngoài phạm vi issuer/audience/membership. Nếu user thuộc hai tenant, cần kiểm tra tenant được chỉ định thuộc danh sách membership hiện tại.

Nếu có **role theo tenant**, một `ROLE_ADMIN` toàn cục cũng không có nghĩa có thể quản lý mọi tenant. Authority/role mapping nên có scope tenant hoặc được kiểm tra song song với membership.

### 5.1. Các lớp data isolation

- Repository `findByTenantAndId(tenant,id)`: luôn scope query.
- SQL `UPDATE ... WHERE tenant_id=? AND owner_issuer=? AND owner_sub=? AND status='DRAFT'`: bảo vệ ghi tại điểm thực hiện.
- Foreign key/joins theo tenant, tránh `attachment.document_id=42` trỏ sang tenant khác.
- Cache key có tenant+resource+actor/action/policy revision khi cache decision hoặc dữ liệu cá nhân hóa.
- PostgreSQL RLS có thể bổ sung; runtime DB role không phải table owner/BYPASSRLS và tenant context phải được cài đúng transaction/connection.

**RLS không thay scope/owner permission**, và session context `app.tenant_id` do app role tự đặt không phải identity mà database tự chứng thực trước SQL injection.

## 6. Spring Method Security: đưa business policy vào bean

Có thể bảo vệ service:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_documents:read') and " +
    "@docAuthz.canRead(authentication, #tenant, #id)"
)
public DocumentView read(
        @P("tenant") String tenant,
        @P("id") long id) {
    return store.readVisible(tenant, id);
}
```

`@docAuthz.canRead(...)` nhận authentication từ expression root và kiểm tra tenant membership + owner/status. `@P("tenant")`/`@P("id")` giúp xác định tên tham số dù chưa build với `-parameters`.

Bật:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
    // Bean policy và service cần Spring quản lý.
}
```

Spring Boot Starter Security **không tự bật Method Security**. `@EnableMethodSecurity` mới đăng ký interceptors cho `@PreAuthorize`. Phải gọi service **qua Spring proxy**, không `new DocumentService(...)` rồi tự mong annotation chạy. Self-invocation `this.read(...)` trong cùng bean có thể bỏ qua proxy advice.

Khi có cả HTTP và method security, kiểm tra scope ở HTTP để từ chối nhanh và tiếp tục check ở service để bảo vệ job/consumer/internal calls không qua HTTP. Có thể giảm duplicate với custom authorization manager chung và thiết kế single source of truth, nhưng không được bỏ object check.

### 6.1. Tại sao không dùng `@PostAuthorize` đơn lẻ cho WRITE?

`@PostAuthorize` đánh giá sau khi method body chạy. Nếu body đã ghi hoặc gửi event thì từ chối sau đó **không tự rollback**. Với READ, post-check có thể dùng khi phải fetch object trước khi đánh giá, nhưng vẫn cần tránh rò dữ liệu, transaction side effects và N+1 queries. Với WRITE/DELETE, ưu tiên guard trước và **conditional mutation** ở data layer.

## 7. Project Java 17+ chạy được: JWT scope + tenant + owner

Dự án sau sử dụng **Spring Method Security/AOP thật**, `JwtAuthenticationConverter` thật để map scope, và **document store in-memory** để tập trung vào logic phân quyền. Các test tự tạo JWT object và đặt `JwtAuthenticationToken` vào `SecurityContextHolder`, **không phải** test chữ ký JWT/Authorization: Bearer header thật. Production resource server phải cấu hình `JwtDecoder`, issuer/audience validation, security filter chain, data storage thật.

### 7.1. File layout và Gradle

```text
oauth2-scope-tenant-ownership/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/OAuth2ScopeTenantOwnershipTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'oauth2-scope-tenant-ownership'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Vì chỉ có source trong `src/test/java`, dependency đặt ở `testImplementation`. Nếu đưa vào app production, chuyển starter resource-server sang `implementation`. Cần JDK 17+, Gradle và quyền tải dependency từ Maven Central.

### 7.2. Source Java tích hợp đầy đủ

Tạo file `src/test/java/demo/OAuth2ScopeTenantOwnershipTest.java`:

```java
package demo;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(OAuth2ScopeTenantOwnershipTest.Config.class)
public class OAuth2ScopeTenantOwnershipTest {

    private static final String ISSUER = "https://idp.example.test";

    public record Identity(String issuer, String subject) {}
    public record Key(String tenant, long id) {}

    public record Doc(
        String tenant, long id, Identity owner,
        String state, String body
    ) {
        public View view() {
            return new View(tenant, id, state, body);
        }
    }

    // DTO không tự tiết lộ owner subject/issuer.
    public record View(
        String tenant, long id, String state, String body
    ) {}

    public static class Memberships {
        private final Map<Identity, Set<String>> tenants = Map.of(
            new Identity(ISSUER, "sub-a"), Set.of("TENANT_A"),
            new Identity(ISSUER, "sub-b"), Set.of("TENANT_B"),
            new Identity(ISSUER, "sub-reviewer"),
                Set.of("TENANT_A", "TENANT_B"),
            new Identity(ISSUER, "sub-other"), Set.of("TENANT_A")
        );

        public boolean contains(Identity actor, String tenant) {
            return actor != null && tenants.getOrDefault(
                actor, Set.of()).contains(tenant);
        }
    }

    public static class Documents {
        private final Map<Key, Doc> rows =
            new ConcurrentHashMap<>();

        public void reset() {
            rows.clear();
            rows.put(new Key("TENANT_A", 42L),
                new Doc("TENANT_A", 42L,
                    new Identity(ISSUER, "sub-a"),
                    "DRAFT", "A private 42"));
            rows.put(new Key("TENANT_B", 42L),
                new Doc("TENANT_B", 42L,
                    new Identity(ISSUER, "sub-b"),
                    "DRAFT", "B private 42"));
            rows.put(new Key("TENANT_A", 43L),
                new Doc("TENANT_A", 43L,
                    new Identity(ISSUER, "publisher"),
                    "PUBLISHED", "A public 43"));
            rows.put(new Key("TENANT_B", 44L),
                new Doc("TENANT_B", 44L,
                    new Identity(ISSUER, "publisher"),
                    "PUBLISHED", "B public 44"));
        }

        public Doc find(String tenant, long id) {
            return rows.get(new Key(tenant, id));
        }

        public List<Doc> listVisible(
                String tenant, Identity actor) {
            return rows.values().stream()
                .filter(doc -> tenant.equals(doc.tenant()))
                .filter(doc ->
                    "PUBLISHED".equals(doc.state())
                    || doc.owner().equals(actor))
                .sorted(Comparator.comparingLong(Doc::id))
                .toList();
        }

        public boolean updateOwnedDraft(
                String tenant, long id,
                Identity actor, String newBody) {
            AtomicBoolean updated = new AtomicBoolean();
            rows.computeIfPresent(new Key(tenant, id), (key, old) -> {
                if (!"DRAFT".equals(old.state())
                        || !old.owner().equals(actor)) {
                    return old;
                }
                updated.set(true);
                return new Doc(
                    old.tenant(), old.id(), old.owner(),
                    old.state(), newBody);
            });
            return updated.get();
        }

        public boolean createDraft(
                String tenant, long id,
                Identity owner, String body) {
            if (id <= 0) return false;
            Doc created = new Doc(
                tenant, id, owner, "DRAFT", body);
            return rows.putIfAbsent(
                new Key(tenant, id), created) == null;
        }

        public void publish(String tenant, long id) {
            rows.computeIfPresent(new Key(tenant, id),
                (key, doc) -> new Doc(
                    doc.tenant(), doc.id(), doc.owner(),
                    "PUBLISHED", doc.body()));
        }
    }

    public static class DocumentPolicy {
        private final Memberships memberships;
        private final Documents documents;

        DocumentPolicy(
                Memberships memberships, Documents documents) {
            this.memberships = memberships;
            this.documents = documents;
        }

        public Identity trustedIdentity(Authentication auth) {
            if (auth == null || !auth.isAuthenticated()
                || !(auth instanceof JwtAuthenticationToken token)) {
                return null;
            }

            Jwt jwt = token.getToken();
            String issuer = jwt.getClaimAsString("iss");
            String subject = jwt.getSubject();

            // Demo: lớp policy còn kiểm tra issuer cụ thể.
            // Production: decoder phải xác thực signature, iss,
            // exp, nbf, aud trước khi tạo Authentication.
            if (!ISSUER.equals(issuer)
                || subject == null || subject.isBlank()) {
                return null;
            }
            return new Identity(issuer, subject);
        }

        public Identity requireIdentity() {
            Identity actor = trustedIdentity(
                SecurityContextHolder.getContext()
                    .getAuthentication());
            if (actor == null) {
                throw new AccessDeniedException(
                    "Trusted identity required");
            }
            return actor;
        }

        public boolean canList(
                Authentication auth, String tenant) {
            Identity actor = trustedIdentity(auth);
            return memberships.contains(actor, tenant);
        }

        public boolean canRead(
                Authentication auth, String tenant, long id) {
            Identity actor = trustedIdentity(auth);
            if (id <= 0 || !memberships.contains(actor, tenant)) {
                return false;
            }

            Doc doc = documents.find(tenant, id);
            return doc != null
                && doc.tenant().equals(tenant)
                && ("PUBLISHED".equals(doc.state())
                    || doc.owner().equals(actor));
        }

        public boolean canWrite(
                Authentication auth, String tenant, long id) {
            Identity actor = trustedIdentity(auth);
            if (id <= 0 || !memberships.contains(actor, tenant)) {
                return false;
            }

            Doc doc = documents.find(tenant, id);
            return doc != null
                && doc.tenant().equals(tenant)
                && "DRAFT".equals(doc.state())
                && doc.owner().equals(actor);
        }

        public boolean canCreate(
                Authentication auth, String tenant, long id) {
            Identity actor = trustedIdentity(auth);
            return id > 0 && memberships.contains(actor, tenant);
        }
    }

    public static class Probe {
        private final AtomicInteger reads = new AtomicInteger();
        private final AtomicInteger writes = new AtomicInteger();
        private final AtomicInteger lists = new AtomicInteger();
        private final AtomicInteger creates = new AtomicInteger();

        public void read() { reads.incrementAndGet(); }
        public void write() { writes.incrementAndGet(); }
        public void list() { lists.incrementAndGet(); }
        public void create() { creates.incrementAndGet(); }

        public int reads() { return reads.get(); }
        public int writes() { return writes.get(); }
        public int lists() { return lists.get(); }
        public int creates() { return creates.get(); }

        public void reset() {
            reads.set(0);
            writes.set(0);
            lists.set(0);
            creates.set(0);
        }
    }

    public static class DocumentService {
        private final Documents documents;
        private final DocumentPolicy policy;
        private final Probe probe;

        DocumentService(
                Documents documents,
                DocumentPolicy policy, Probe probe) {
            this.documents = documents;
            this.policy = policy;
            this.probe = probe;
        }

        @PreAuthorize(
            "hasAuthority('SCOPE_documents:read') and " +
            "@docAuthz.canRead(authentication, #tenant, #id)"
        )
        public View read(
                @P("tenant") String tenant,
                @P("id") long id) {
            probe.read();
            Doc doc = documents.find(tenant, id);
            if (doc == null) {
                throw new AccessDeniedException("Not visible");
            }
            return doc.view();
        }

        @PreAuthorize(
            "hasAuthority('SCOPE_documents:write') and " +
            "@docAuthz.canWrite(authentication, #tenant, #id)"
        )
        public View write(
                @P("tenant") String tenant,
                @P("id") long id, String newBody) {
            probe.write();

            Identity actor = policy.requireIdentity();
            if (!documents.updateOwnedDraft(
                    tenant, id, actor, newBody)) {
                throw new AccessDeniedException(
                    "Write denied or stale");
            }

            return documents.find(tenant, id).view();
        }

        @PreAuthorize(
            "hasAuthority('SCOPE_documents:read') and " +
            "@docAuthz.canList(authentication, #tenant)"
        )
        public List<View> list(
                @P("tenant") String tenant) {
            probe.list();
            Identity actor = policy.requireIdentity();
            return documents.listVisible(tenant, actor)
                .stream().map(Doc::view).toList();
        }

        @PreAuthorize(
            "hasAuthority('SCOPE_documents:write') and " +
            "@docAuthz.canCreate(authentication, #tenant, #id)"
        )
        public View create(
                @P("tenant") String tenant,
                @P("id") long id, String body) {
            probe.create();
            Identity actor = policy.requireIdentity();

            if (!documents.createDraft(
                    tenant, id, actor, body)) {
                throw new IllegalStateException(
                    "Duplicate or invalid document ID");
            }

            return documents.find(tenant, id).view();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class Config {
        @Bean Memberships memberships() {
            return new Memberships();
        }

        @Bean Documents documents() {
            return new Documents();
        }

        @Bean("docAuthz")
        DocumentPolicy documentPolicy(
                Memberships membership, Documents docs) {
            return new DocumentPolicy(membership, docs);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean DocumentService documentService(
                Documents docs, DocumentPolicy policy,
                Probe probe) {
            return new DocumentService(docs, policy, probe);
        }
    }

    @Autowired Documents documents;
    @Autowired DocumentPolicy policy;
    @Autowired DocumentService service;
    @Autowired Probe probe;

    private static JwtAuthenticationToken token(
            String issuer, String subject,
            String displayName, String scope) {
        Jwt jwt = Jwt.withTokenValue("test-token-" + subject)
            .header("alg", "RS256")
            .claim("iss", issuer)
            .claim("sub", subject)
            .claim("preferred_username", displayName)
            .claim("scope", scope)
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .build();

        // Dùng converter thật để test scope -> SCOPE_ mapping,
        // nhưng không ký/xác minh token qua JwtDecoder.
        return (JwtAuthenticationToken)
            new JwtAuthenticationConverter().convert(jwt);
    }

    private void as(
            String issuer, String subject,
            String username, String scopes) {
        JwtAuthenticationToken authenticated = token(
            issuer, subject, username, scopes);
        SecurityContext ctx =
            SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(authenticated);
        SecurityContextHolder.setContext(ctx);
    }

    private void alice(String scopes) {
        as(ISSUER, "sub-a", "alex", scopes);
    }

    private void bob(String scopes) {
        as(ISSUER, "sub-b", "alex", scopes);
    }

    private void reviewer(String scopes) {
        as(ISSUER, "sub-reviewer", "reviewer", scopes);
    }

    @BeforeEach
    void reset() {
        documents.reset();
        probe.reset();
        alice("documents:read documents:write");
    }

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void serviceUsesARealSpringMethodSecurityProxy() {
        assertThat(AopUtils.isAopProxy(service)).isTrue();
    }

    @Test
    void jwtScopeConverterAddsScopePrefix() {
        JwtAuthenticationToken t = token(
            ISSUER, "sub-a", "alex",
            "documents:read documents:write");

        assertThat(t.getAuthorities().stream()
            .map(a -> a.getAuthority()).toList())
            .contains("SCOPE_documents:read")
            .contains("SCOPE_documents:write");
    }

    @Test
    void jwtAuthenticationNameDefaultsToSubjectNotUsername() {
        JwtAuthenticationToken a = token(
            ISSUER, "sub-a", "alex", "documents:read");
        JwtAuthenticationToken b = token(
            ISSUER, "sub-b", "alex", "documents:read");

        assertThat(a.getName()).isEqualTo("sub-a");
        assertThat(b.getName()).isEqualTo("sub-b");
        assertThat(a.getToken().getClaimAsString(
            "preferred_username")).isEqualTo("alex");
        assertThat(b.getToken().getClaimAsString(
            "preferred_username")).isEqualTo("alex");
    }

    @Test
    void aliceReadsOnlyHerTenantADraft42() {
        View view = service.read("TENANT_A", 42L);
        assertThat(view.tenant()).isEqualTo("TENANT_A");
        assertThat(view.body()).isEqualTo("A private 42");
        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    void bobWithSameScopesReadsDifferentTenantB42() {
        bob("documents:read documents:write");
        View view = service.read("TENANT_B", 42L);
        assertThat(view.tenant()).isEqualTo("TENANT_B");
        assertThat(view.body()).isEqualTo("B private 42");
        assertThat(documents.find(
            "TENANT_A", 42L).body()).isEqualTo("A private 42");
    }

    @Test
    void aliceCannotReadTenantB42EvenWithReadScope() {
        assertThatThrownBy(() -> service.read("TENANT_B", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void bobCannotReadTenantA42EvenWithReadScope() {
        bob("documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void tenantAActorCannotReadPublishedTenantB44() {
        assertThatThrownBy(() -> service.read("TENANT_B", 44L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void reviewerCanReadPublishedDocumentsInBothTenants() {
        reviewer("documents:read");
        assertThat(service.read(
            "TENANT_A", 43L).body()).isEqualTo("A public 43");
        assertThat(service.read(
            "TENANT_B", 44L).body()).isEqualTo("B public 44");
    }

    @Test
    void reviewerCannotReadAliceDraftEvenInSameTenant() {
        reviewer("documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void sameDisplayedUsernameOtherSubjectCannotReadDraft() {
        as(ISSUER, "sub-other", "alex", "documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void sameSubjectFromDifferentIssuerIsRejected() {
        as("https://other-idp.example.test", "sub-a",
            "alex", "documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void missingReadScopeStopsBeforeServiceBody() {
        alice("documents:write");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void genericAdminRoleIsNotDocumentReadScope() {
        alice("admin");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void missingMembershipIsDeniedEvenWithReadScope() {
        as(ISSUER, "unknown-sub", "alex", "documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 43L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void wrongDocumentIdIsDenied() {
        assertThatThrownBy(() -> service.read("TENANT_A", 999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void unauthenticatedRequestCannotUseMethod() {
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void readScopeDoesNotGrantWrite() {
        alice("documents:read");
        assertThatThrownBy(() ->
            service.write("TENANT_A", 42L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.writes()).isZero();
        assertThat(documents.find(
            "TENANT_A", 42L).body()).isEqualTo("A private 42");
    }

    @Test
    void aliceCanWriteOwnDraftWithoutChangingTenantB() {
        View changed = service.write(
            "TENANT_A", 42L, "Changed A");
        assertThat(changed.body()).isEqualTo("Changed A");
        assertThat(documents.find(
            "TENANT_B", 42L).body()).isEqualTo("B private 42");
        assertThat(probe.writes()).isEqualTo(1);
    }

    @Test
    void bobCanWriteOwnDraftWithoutChangingTenantA() {
        bob("documents:write");
        assertThat(service.write(
            "TENANT_B", 42L, "Changed B").body())
            .isEqualTo("Changed B");
        assertThat(documents.find(
            "TENANT_A", 42L).body()).isEqualTo("A private 42");
    }

    @Test
    void reviewerCannotWriteAnotherOwnersDraft() {
        reviewer("documents:write");
        assertThatThrownBy(() ->
            service.write("TENANT_A", 42L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.writes()).isZero();
    }

    @Test
    void publishedDocumentCannotBeChangedAsDraft() {
        documents.publish("TENANT_A", 42L);
        assertThatThrownBy(() ->
            service.write("TENANT_A", 42L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(documents.find(
            "TENANT_A", 42L).body()).isEqualTo("A private 42");
    }

    @Test
    void listShowsOnlyTenantAVisibleRecords() {
        List<View> results = service.list("TENANT_A");
        assertThat(results.stream().map(View::id).toList())
            .containsExactly(42L, 43L);
        assertThat(results).allMatch(
            d -> "TENANT_A".equals(d.tenant()));
    }

    @Test
    void listShowsOnlyTenantBVisibleRecords() {
        bob("documents:read");
        List<View> results = service.list("TENANT_B");
        assertThat(results.stream().map(View::id).toList())
            .containsExactly(42L, 44L);
        assertThat(results).allMatch(
            d -> "TENANT_B".equals(d.tenant()));
    }

    @Test
    void reviewerListHidesDraftsOwnedByOtherUsers() {
        reviewer("documents:read");
        assertThat(service.list("TENANT_A").stream()
            .map(View::id).toList()).containsExactly(43L);
    }

    @Test
    void listWithoutReadScopeIsDeniedBeforeBody() {
        alice("documents:write");
        assertThatThrownBy(() -> service.list("TENANT_A"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.lists()).isZero();
    }

    @Test
    void createDerivesTenantAndOwnerFromTrustedIdentity() {
        View created = service.create(
            "TENANT_A", 99L, "New A");
        assertThat(created.tenant()).isEqualTo("TENANT_A");
        assertThat(created.state()).isEqualTo("DRAFT");
        assertThat(documents.find(
            "TENANT_A", 99L).owner())
            .isEqualTo(new Identity(ISSUER, "sub-a"));
        assertThat(probe.creates()).isEqualTo(1);
    }

    @Test
    void bothTenantsMayCreateSameLocalDocumentId() {
        service.create("TENANT_A", 99L, "A 99");
        bob("documents:write");
        service.create("TENANT_B", 99L, "B 99");

        assertThat(documents.find(
            "TENANT_A", 99L).body()).isEqualTo("A 99");
        assertThat(documents.find(
            "TENANT_B", 99L).body()).isEqualTo("B 99");
    }

    @Test
    void duplicateIdInSameTenantCannotOverwriteDocument() {
        service.create("TENANT_A", 99L, "First");

        assertThatThrownBy(() ->
            service.create("TENANT_A", 99L, "Overwrite"))
            .isInstanceOf(IllegalStateException.class);
        assertThat(documents.find(
            "TENANT_A", 99L).body()).isEqualTo("First");
    }

    @Test
    void createWithoutWriteScopeStopsBeforeMethodBody() {
        alice("documents:read");
        assertThatThrownBy(() ->
            service.create("TENANT_A", 99L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.creates()).isZero();
    }

    @Test
    void cannotCreateInsideAnotherTenant() {
        assertThatThrownBy(() ->
            service.create("TENANT_B", 99L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.creates()).isZero();
    }

    @Test
    void invalidIdCannotBeCreated() {
        assertThatThrownBy(() ->
            service.create("TENANT_A", 0L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.creates()).isZero();
    }
}
```

### 7.3. Hướng dẫn chạy và cách hiểu kết quả

Tại thư mục `oauth2-scope-tenant-ownership`:

```bash
gradle test --tests demo.OAuth2ScopeTenantOwnershipTest
```

Hoặc dùng Gradle Wrapper: Linux/macOS `./gradlew test --tests demo.OAuth2ScopeTenantOwnershipTest`, Windows `gradlew.bat test --tests demo.OAuth2ScopeTenantOwnershipTest`.

**Kết quả kỳ vọng:** tất cả JUnit tests thành công và Gradle hiển thị `BUILD SUCCESSFUL` khi môi trường/dependencies phù hợp. Đây là **kỳ vọng theo mã ví dụ, không phải kết quả đã chạy thực tế**. Báo cáo HTML: `build/reports/tests/test/index.html`.

| Nhóm test | Điều được chứng minh |
| --- | --- |
| Method Security proxy | `@PreAuthorize` thực thi trên Spring-managed bean |
| JWT converter | Scope `documents:read` / `documents:write` biến thành authorities có prefix `SCOPE_` |
| JWT subject | `getName()` mặc định là `sub`, username hiển thị có thể trùng |
| READ A/B #42 | Cùng local ID, kết quả thuộc đúng tenant |
| Cross-tenant/membership | Scope đúng nhưng tenant sai vẫn bị deny |
| Owner | DRAFT không được đọc bởi người khác cùng tenant, dù có scope |
| Khác issuer/subject | Không mượn quyền của chủ tài liệu |
| Scope bị thiếu | Bị từ chối trước method body |
| WRITE | Có scope WRITE và đúng owner/state; không sửa dữ liệu tenant khác |
| LIST | Chỉ thấy những bản ghi đúng tenant và visibility |
| CREATE | Owner, tenant, state lấy từ policy/server; chống overwrite cùng tenant |
| Negative paths | Unknown resource, missing authentication, invalid ID, wrong issuer, duplicate |

### 7.4. Điều ví dụ *không* chứng minh

Các JUnit tests tự lắp `JwtAuthenticationToken` vào `SecurityContextHolder` — tức mô phỏng **authentication đã hoàn tất**, không kiểm chứng chữ ký JWT, JWT header, issuer discovery, JWK rotation, audience validator hay HTTP Bearer challenge. Test scope converter **không thay** một bộ integration test với `JwtDecoder` và authentication filter.

Store dùng `ConcurrentHashMap` để minh họa tenant composite keys và conditional write, không thay database transaction thật, RLS hoặc kiểm thử concurrency đa node. `DocumentPolicy` có hardcoded trusted issuer chỉ để làm rõ logic; production phải nhận issuer đã qua resource-server validation và kiểm tra membership từ trusted source.

Để test HTTP resource server, bổ sung Spring MVC/MockMvc và Spring Security Test với `jwt()` hoặc token ký test; phân biệt test mock JWT với test signature validation thật:

```java
// Fragment: MockMvc test cho lớp scope/HTTP (JWT mock,
// không kiểm chứng chữ ký).
mockMvc.perform(get("/api/tenants/TENANT_A/documents/42")
        .with(jwt().jwt(j -> j
            .claim("scope", "documents:read")
            .claim("sub", "sub-a"))
        .authorities(new SimpleGrantedAuthority(
            "SCOPE_documents:read"))))
    .andExpect(status().isOk());
```

Đoạn này cần MockMvc, imports static `jwt`/`get`/`status`, controller và beans đầy đủ; **không phải một test độc lập**. Vì `.authorities(...)` được cung cấp thủ công, đây là test HTTP permission gate chứ **không tự chứng minh JwtGrantedAuthoritiesConverter chạy**. Bộ test ở mục 7 trực tiếp dùng `JwtAuthenticationConverter` thật để kiểm tra mapping.

## 8. Từ in-memory tới repository SQL và PostgreSQL RLS

Một khóa dữ liệu an toàn theo tenant:

```sql
CREATE TABLE tenant_documents (
    tenant_id TEXT NOT NULL,
    document_id BIGINT NOT NULL,
    owner_issuer TEXT NOT NULL,
    owner_subject TEXT NOT NULL,
    status TEXT NOT NULL,
    body TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, document_id)
);
```

Query READ:

```sql
SELECT tenant_id, document_id, status, body
FROM tenant_documents
WHERE tenant_id = :tenant
  AND document_id = :id
  AND (
      status = 'PUBLISHED'
      OR (
          owner_issuer = :actor_issuer
          AND owner_subject = :actor_subject
      )
  );
```

Điều kiện này phải được chạy **sau** khi đã xác minh `SCOPE_documents:read` và tenant membership. Nếu business rule còn ACL group/share, thêm điều kiện tương ứng và test.

Conditional UPDATE:

```sql
UPDATE tenant_documents
SET body = :new_body,
    version = version + 1
WHERE tenant_id = :tenant
  AND document_id = :id
  AND owner_issuer = :actor_issuer
  AND owner_subject = :actor_subject
  AND status = 'DRAFT'
  AND version = :expected_version;
```

Kiểm tra số affected rows đúng **1**. Nếu 0, thao tác có thể đã stale, không tồn tại, sai tenant hoặc sai owner; trả lỗi theo hợp đồng 403/404/409 mà không làm lộ resource khác tenant. Điều kiện này tránh ghi khi owner/status/version thay đổi giữa precheck và thời điểm update, nhưng **chưa tự đảm bảo grant bị revoke giữa hai thời điểm**; nếu cần, kết hợp policy revision/authorization check cùng transaction.

### 8.1. RLS là lớp phòng thủ bổ sung

Với PostgreSQL, RLS có thể áp tenant predicate ở DB:

```sql
ALTER TABLE tenant_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_guard ON tenant_documents
FOR ALL TO app_role
USING (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), '')
)
WITH CHECK (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), '')
);
```

Đây là **fragment**, phải tạo DB role và GRANT phù hợp, dùng transaction-local tenant context và DB role không là table owner/superuser/BYPASSRLS. `app.tenant_id` do app role tự set **không phải identity DB xác thực**, cần threat model SQL injection. RLS không thay scope, owner hoặc field-level permission.

## 9. Cache, token lifetime và thu hồi quyền

JWT đã phát là credential có thời hạn. Nếu Alice bị thu hồi membership trong tenant A, `SCOPE_documents:read` có thể còn nằm trong token đến khi hết hạn. Bởi vậy, **scope gate phải kết hợp membership/policy store hiện hành**, hoặc version/revocation-aware cache theo SLA.

Một cache decision cần key đầy đủ:

```text
(tenant, issuer, subject,
 resourceType, resourceId,
 action, policyRevision)
```

Đừng cache chỉ theo `documentId=42` hoặc username `alex`: tenant A/B và người khác có thể cùng ID/tên. TTL giảm thời gian sống của entry nhưng **không đảm bảo revoke ngay**. Có thể cần invalidate sau commit khi đổi ACL/owner/tenant membership, phát event đa node, hoặc recheck trực tiếp cho WRITE/APPROVE nhạy cảm.

Với OAuth2 **client_credentials**, access token có thể đại diện cho **service/client**, không có subject người dùng sở hữu. Không giả định client là owner của một document chỉ vì client có scope. Nên dùng workload identity, service account permissions, allowed tenant set, actor delegation nếu thực sự thay mặt user, cùng audit caller/subject rõ ràng.

## 10. Kết quả HTTP: 401, 403, 404 và 409

| Tình huống | Kết quả thường dùng | Lưu ý |
| --- | --- | --- |
| Thiếu token hoặc Bearer token không hợp lệ | **401 Unauthorized** | Cấu hình resource-server entry point/Bearer challenge phù hợp |
| Token hợp lệ nhưng thiếu `SCOPE_documents:read` | **403 Forbidden** | Không mặc nhiên yêu cầu login lại |
| Token có scope nhưng không thuộc tenant yêu cầu | **403** hoặc **404** | Tùy chính sách che giấu sự tồn tại resource |
| Token có scope và tenant đúng nhưng DRAFT của người khác | **403** hoặc **404** | Không tiết lộ owner/data trong error |
| Resource thực sự không tồn tại trong tenant | **404** hoặc deny chung | Hợp đồng API phải nhất quán |
| Conditional update affected rows=0 vì version thay đổi | **409 Conflict** hoặc lỗi tương đương | Không làm lộ object cross-tenant |
| PDP/membership service không sẵn sàng | Fail closed; thường **503** hoặc authz deny an toàn | Không fallback ALLOW |
| Scope READ đúng, CSRF thiếu trong cookie-based app | Có thể **403 do CSRF** | Không nhầm với object authorization |

Resource Server thường áp `WWW-Authenticate: Bearer ...` theo RFC 6750 cho các lỗi thích hợp. Đừng tự trả 200 kèm `{"allowed":false}` hoặc 403 chứa token, issuer nội bộ, SQL/ACL expression. Với API cross-tenant, không lộ khác biệt owner qua nội dung lỗi nếu hợp đồng yêu cầu che giấu.

## 11. Các sai lầm phổ biến

| Anti-pattern | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Có scope READ thì `findById(id)` | Scope không bảo vệ object, ID có thể trùng tenant | Scope + member + tenant-scoped lookup |
| Owner = username hiển thị | Username/email alias không unique hoặc thay đổi | Issuer/sub hoặc stable internal user ID |
| Dùng `ROLE_ADMIN` làm quyền mọi tenant | Role không tự ngụ ý tenant membership | Tenant-scoped role/policy và authority đúng |
| Kiểm tra `scope` raw từ JWT chưa xác thực | Client có thể gửi token tự tạo | Resource Server JwtDecoder/introspection |
| Chỉ validate issuer mà không validate audience | Token hợp lệ cho API khác có thể bị dùng nhầm | Audience validator theo API |
| Dùng `scope=documents:write` như READ | Scopes độc lập nếu contract không nói kế thừa | Kiểm tra từng `SCOPE_` authority |
| Chỉ tin `tenantId` trong URL/header | Client tự đổi tenant | Resolve từ verified principal + membership |
| Chỉ dùng `@PreAuthorize` cho UPDATE | Race owner/status/version | Conditional SQL và affected-row check |
| Test tất cả ID/username đều khác nhau | Không chạm lỗi collision | Test ID=42 và username trùng giữa tenant |
| `getName()` mặc nhiên là username | `JwtAuthenticationToken.getName()` mặc định sub | Sử dụng identity rõ ràng theo issuer/sub |
| Scope đúng nhưng list/export không lọc | Rò toàn bộ tenant hoặc fields nhạy cảm | Query-time filtering + DTO allowlist |
| Cache `ALLOW` đến hết JWT | Revoke chậm, stale privileges | TTL, invalidation, policy revision, recheck |
| Bật Method Security rồi tự `new Service()` | Mất Spring proxy | Inject bean và test `AopUtils.isAopProxy` |
| Gọi `this.write(...)` | Self-invocation bỏ proxy advice | Thiết kế service boundary rõ ràng |
| Chỉ kiểm tra HTTP filter | Internal jobs không đi qua API | Object policy ở service/repository |
| Test JWT bằng mock rồi cho rằng signature an toàn | Mock bypass decode/verify | Thêm token ký test và JwtDecoder integration |

## 12. Checklist nghiệm thu

- [ ] Spring Resource Server xác minh issuer, signature, expiry/nbf, audience và trust algorithm theo config.
- [ ] Mỗi endpoint/method kiểm tra scope đúng `SCOPE_documents:read/write`; không suy ra role/authority từ tên gần giống.
- [ ] Principal là `(issuer,sub)` hoặc user ID ổn định; `preferred_username` chỉ để hiển thị.
- [ ] Membership tenant được kiểm tra từ trusted source và active tenant được xác minh.
- [ ] Object được tra bằng `(tenant_id,document_id)`; đọc DRAFT chỉ khi owner/ACL cho phép.
- [ ] List/export/count và cache đều ràng buộc tenant, visibility và field-level policy.
- [ ] CREATE không tin owner/tenant do client tự khai.
- [ ] WRITE/DELETE/APPROVE có conditional SQL, version hoặc transaction recheck khi cần.
- [ ] Dịch vụ quyền/DB lỗi không dẫn tới ALLOW; có metrics/alert và error contract rõ.
- [ ] Negative tests có thiếu scope, sai tenant, sai owner/issuer/sub, sai ID, cross-tenant cùng ID, token không hợp lệ.
- [ ] Test HTTP Bearer JWT/introspection thực bổ sung cho unit test dùng `JwtAuthenticationToken` giả lập.
- [ ] Token lifecycle, membership revocation, machine-to-machine và multi-node cache được threat model.
- [ ] Không dựa duy nhất vào HTTP authorization; Method Security và repository vẫn bảo vệ dữ liệu.

## 13. Bài tập mở rộng

1. **Scope tách biệt:** tạo `documents:approve` cho reviewer, kiểm tra maker không tự approve; bảo đảm `documents:write` không tự cấp quyền duyệt.
2. **Tenant switch:** cho Alice membership A+B, tạo active tenant session claim được server kiểm tra và test đổi tenant hợp lệ/bất hợp lệ.
3. **JWT audience:** cấu hình `JwtDecoder` với audience validator, thử token ký hợp lệ cho `another-api`, đảm bảo bị 401.
4. **Opaque token:** dùng introspection với `scope` claim, xác minh vẫn ra `SCOPE_` authorities và mapping ổn định.
5. **PostgreSQL Testcontainers:** thay `ConcurrentHashMap` bằng bảng có composite key và RLS; test queries thiếu tenant predicate trực tiếp bằng DB role runtime.
6. **Concurrent write:** thêm version, test thay status DRAFT→PUBLISHED sau precheck và trước UPDATE; affected rows=0.
7. **ACL chia sẻ:** tài liệu DRAFT được share READ cho người cùng tenant nhưng không phải owner; scope+membership+ACL cùng cần đúng.
8. **Client credentials:** thiết kế scope cho service account và authorized tenant list, không coi service token như người sở hữu cá nhân.
9. **Cache collision:** cố tình key cache theo ID 42, tái hiện lỗi A/B và sửa thành key có tenant, actor, action, version.
10. **HTTP test:** bổ sung `MockMvc` với `jwt()`, phân biệt scope authorization với kiểm chứng chữ ký thực của resource server.

## 14. Kết luận

Một token có scope `documents:read` chỉ cho biết quyền **loại thao tác**, không phải quyền xem mọi tài liệu. Muốn bảo vệ dữ liệu thực tế, phải kiểm tra **đồng thời**:

```text
allow = token authenticated and right scope
        and verified tenant membership
        and resource belongs to tenant
        and object owner/ACL/status policy passes
```

Trong Spring Security 6.5, scope thường được ánh xạ thành authority `SCOPE_`, `@EnableMethodSecurity` cho phép `@PreAuthorize` kết hợp authority và bean policy, và repository/SQL cần tenant predicate cùng conditional write để chống lẫn dữ liệu và TOCTOU.

Bộ test Java của bài cố tình dùng cùng local ID và cùng username ở hai tenant để phát hiện các giả định sai. Trước khi đưa vào production, còn phải thử JWT validation bằng resource-server filter thật, database transaction, revocation, rate/cache và quyền machine-to-machine theo môi trường.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — OAuth2 Resource Server JWT và `SCOPE_` mapping: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth2 Resource Server Opaque Token và scope authorities: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 — Method Security và custom SpEL bean: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Method Security Test: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
- Spring Security 6.5 — Mock JWT Resource Server Test: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html
- OAuth 2.0 Framework — Scopes, RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Bearer Tokens — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OpenID Connect Core — Issuer/Subject claims: https://openid.net/specs/openid-connect-core-1_0.html
- OWASP API1:2023 — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
