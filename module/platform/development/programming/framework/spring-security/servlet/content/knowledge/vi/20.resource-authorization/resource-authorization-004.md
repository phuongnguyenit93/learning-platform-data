# Phân quyền đa tổ chức và kiểm tra tenant trong từng yêu cầu — Spring Security Servlet

Trong một hệ thống **multi-tenant** (đa tổ chức), xác thực thành công không đồng nghĩa có quyền xem mọi tổ chức. Alice có thể đăng nhập hợp lệ và có quyền đọc tài liệu của `tenant-a`, nhưng không vì thế mà được đọc tài liệu `tenant-b` bằng cách thay URL. Ngay cả khi Alice là thành viên của **cả hai tổ chức**, đường dẫn `/tenants/tenant-b/documents/doc-a1` vẫn không được trả một tài liệu thực tế thuộc `tenant-a` chỉ vì ID tài liệu đoán được.

Đó là trọng tâm của **phân quyền đa tổ chức theo từng request**: xác định tổ chức mà request **muốn** truy cập; xác minh identity và membership/quyền của người gọi đối với tổ chức đó; sau đó truy vấn tài nguyên **trong đúng phạm vi tenant được phép**. Một session, JWT access token, opaque token hoặc API key hợp lệ đều không tự động cấp quyền trên mọi tenant.

Bài học thuộc phần **Quyền tài nguyên**, module **Spring Security – servlet**. Chúng ta sử dụng Java 17+, Spring Security 6.x và Spring Boot 3.3.5. Ví dụ thực hành hoàn chỉnh dùng HTTP Basic, Spring MVC, `@EnableMethodSecurity`, `@PreAuthorize`, membership phía server và kho tài liệu in-memory. Các kiến trúc database, JWT và Row-Level Security là các hướng triển khai thêm, không phải thành phần mặc định của lab.

> **Requested tenant là đầu vào của request; authorized tenant là kết quả của quyết định phân quyền dựa trên identity và policy đáng tin. Mọi resource query phải giữ đúng tenant boundary.**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **authentication**, **tenant resolution**, **tenant membership**, **tenant-scoped permission** và **object-level authorization**.
2. Nhận diện `tenantId` từ path, host, header, query, session hoặc JWT claim là thông tin cần kiểm chứng, không phải giấy phép mặc định.
3. Thiết kế permission READ/WRITE/ADMIN riêng theo tenant cho cùng một user.
4. Bảo vệ tài liệu bằng **hai điều kiện đồng thời**: người dùng có quyền tại tenant và tài liệu thực sự thuộc tenant đó.
5. Tránh IDOR/BOLA, tenant spoofing, cache-key collision, cross-tenant JOIN và confused deputy.
6. Kết hợp `SecurityFilterChain`, `@PreAuthorize`, policy bean và tenant-scoped repository trên Servlet stack.
7. Viết test kiểm tra 401, 403, 404, 201, sai tenant, sai action, header giả, thiếu CSRF và đọc nhầm resource.
8. Giải thích quyền bị thu hồi, cache staleness, thread context, RLS, audit và các đường dữ liệu không đi qua HTTP.

## 2. Năm lớp quyết định quyền trong multi-tenant

### 2.1. Authentication: principal là ai?

Spring Security xác minh credential rồi tạo `Authentication`. User có thể có:

~~~text
principal: alice
authenticated: true
authorities: [ROLE_USER]
~~~

Điều này trả lời “Alice là ai và credential có hợp lệ không?”, **chưa** trả lời Alice là thành viên tổ chức nào. `ROLE_USER` là role chung; không nên diễn giải nó thành quyền truy cập tất cả tenants.

### 2.2. Tenant resolution: tổ chức được request yêu cầu là gì?

Ví dụ:

~~~http
GET /api/tenants/tenant-a/documents/doc-a1 HTTP/1.1
Authorization: Bearer <access-token>
~~~

`tenant-a` trong URL là **requested tenant**. Nó có thể tồn tại hoặc không, và caller hoàn toàn có thể sửa thành `tenant-b`. Việc parse thành path variable không làm tenant trở nên đáng tin.

### 2.3. Membership: user thuộc tenant nào?

Ví dụ quan hệ do **server** quản lý:

| Principal | Tenant | Quyền trong tenant |
| --- | --- | --- |
| Alice | tenant-a | documents.read, documents.write |
| Bob | tenant-b | documents.read, documents.write |
| Auditor | tenant-a | documents.read |
| Auditor | tenant-b | documents.read |
| Alice | tenant-b | Không có membership |

Một người có thể có role editor ở tenant-a nhưng chỉ là viewer ở tenant-b. Membership còn có trạng thái active/suspended, hạn dùng, invitation workflow và audit.

### 2.4. Action permission: READ khác WRITE

Membership không đồng nghĩa toàn quyền. `GET` tài liệu có thể yêu cầu READ; `POST` hoặc `DELETE` cần WRITE/DELETE. Với tài liệu nhạy cảm có thể còn EXPORT, APPROVE, SHARE hoặc OWNER.

Quyền `ROLE_ADMIN` toàn hệ thống cũng không được dùng bừa để biểu diễn “tenant admin”. Platform admin, tenant admin, resource owner và technical service account là những vai trò có phạm vi khác nhau.

### 2.5. Resource scope: dữ liệu thuộc tổ chức nào?

Ngay cả khi auditor được đọc tenant-a và tenant-b, request tại tenant-b vẫn không được trả `doc-a1` nếu document thuộc tenant-a. Vì vậy phải có query dạng:

~~~text
document = findByTenantIdAndDocumentId(
    authorizedTenantId, documentId)
~~~

chứ không chỉ:

~~~text
document = findById(documentId)
~~~

Sau bước scoping còn có thể cần owner/ACL, tenant status, legal hold hoặc policy nghiệp vụ khác.

### 2.6. Công thức tư duy

~~~text
ALLOW =
  credentialVerified
  AND tenantExistsAndActive
  AND activeMembership(principal, requestedTenant)
  AND hasPermission(principal, requestedTenant, action)
  AND resourceBelongsToTenant(resourceId, requestedTenant)
  AND resourceAclAllows(principal, resourceId, action)
~~~

Không phải endpoint nào cũng có tất cả các điều kiện, nhưng **các điều kiện thuộc nghiệp vụ phải được áp dụng ở nguồn tin cậy**, không suy từ việc client gửi một ID hợp lệ.

## 3. Luồng xác minh tenant ở từng HTTP request

~~~text
Client:
  GET /api/tenants/tenant-a/documents/doc-a1
            |
            v
Spring Security Servlet FilterChain
  - Xác minh credential: Alice
  - HTTP authorization: /api/tenants/** cần authenticated
            |
            v
Spring MVC Controller
  - Parse requested tenant-a và resource doc-a1
            |
            v
DocumentService Spring AOP proxy
  @PreAuthorize:
  tenantAccess.canRead(authentication, "tenant-a")
       |
       +-- Không có READ membership -> từ chối (403)
       +-- Có READ membership -> gọi method body
            |
            v
Repository
  SELECT ... WHERE tenant_id='tenant-a'
               AND document_id='doc-a1'
       |
       +-- Không có document tenant-a -> 404
       +-- Có -> kiểm ACL khác nếu áp dụng -> trả dữ liệu
~~~

**Hai tầng quan trọng và độc lập:** tenant membership check từ nguồn server, cùng với tenant predicate ở mọi data-access query. Nếu chỉ có tầng thứ nhất, một ID lộ từ tenant khác vẫn có thể bị đọc bằng `findById`. Nếu chỉ có tầng thứ hai, user có thể thay `tenantId` thành tenant khác và lấy dữ liệu đúng tenant đó dù không có membership.

### 3.1. “Kiểm tra mỗi request” không bắt buộc query DB mỗi lần

Policy phải được **áp dụng cho mọi truy cập protected**, nhưng dữ liệu membership có thể đến từ:

- Lookup DB/authorization service tại thời điểm truy cập.
- Cache membership được kiểm soát TTL và invalidation.
- Token claim có quyền theo tenant được issuer đáng tin ký/xác nhận và có lifetime phù hợp.
- Central policy decision service có SLA/availability phù hợp.

Cần định nghĩa **revocation latency**: user bị rút quyền lúc 14:00 thì tối đa bao lâu request sau bị từ chối? Cache 10 phút hoặc JWT offline 30 phút tạo cửa sổ quyền cũ có thể tiếp tục hiệu lực. Không chỉ nói “đã kiểm tenant” mà bỏ qua thời hạn dữ liệu quyền.

## 4. Các kiểu tenant resolution và trust boundary

| Nguồn | Ví dụ | Giá trị sử dụng | Điều phải kiểm soát |
| --- | --- | --- | --- |
| URL path | `/tenants/tenant-a/...` | Rõ ràng và dễ test | User tự thay path; kiểm membership |
| Subdomain | `tenant-a.example.org` | Hữu ích SaaS/white-label | Trusted Host/proxy mapping, tenant lookup |
| HTTP header | `X-Tenant-Id: tenant-a` | Tiện API internal | Header client-controlled nếu chưa được gateway xác minh |
| JWT access token claim | `tenant_id=tenant-a` | Có thể scope token vào tenant | Verify signature, iss, aud, exp, token type; stale claims |
| Session selection | User chọn organization trong UI | Hữu ích UX | Server kiểm membership khi đổi tenant và khi dùng |
| API key record | Key gắn tenant-a | Integration server-to-server | Key được xác minh và bind tenant server-side |
| Query/body | `?tenant=tenant-a` | Tiện cho một số operation | Không dùng làm bằng chứng quyền |

Một product cần **quy tắc precedence/conflict rõ**. Nếu path ghi tenant-a, token claim tenant-b và header tenant-c, đừng tự động chọn nguồn nào giúp client được truy cập. Cần reject xung đột hoặc thực thi chính sách token scope rõ ràng.

### 4.1. Canonical tenant ID

Với hệ thống thật, URL có thể dùng tenant slug như `acme` để tiện người dùng, nhưng backend nên ánh xạ sang ID ổn định từ DB, không dựa vào tên hiển thị hay email domain có thể đổi. Không để slug được tái sử dụng dẫn tới cấp lại quyền cũ cho tổ chức mới.

Kiểm tra cú pháp/độ dài/canonicalization của slug, tenant tồn tại và active, membership thực tế và tenant_id nội bộ. Nếu nhận UUID, đừng xem UUID khó đoán là một cơ chế bảo mật.

### 4.2. Tenant claim và JWT

JWT minh họa (payload chưa ký, không phải credential thật):

~~~json
{
  "iss": "https://issuer.example",
  "sub": "alice-stable-id",
  "aud": ["document-api"],
  "exp": 1893456000,
  "tenant_id": "tenant-a",
  "scope": "documents.read"
}
~~~

Resource Server phải xác minh chữ ký, issuer, audience, thời hạn và mục đích token **trước khi tin claim**. Hơn nữa:

- Claim `tenant_id` có thể là **giới hạn phạm vi token**, không phải toàn bộ membership hiện hành.
- Nếu token single-tenant `tenant-a`, request tenant-b thường phải bị từ chối dù user có thể có membership tenant-b qua một phiên khác.
- Claim `scope` phải được định nghĩa scope toàn platform hay chỉ tenant trong token.
- Khi membership bị revoke nhưng JWT còn hạn, cần TTL/denylist/introspection/online policy theo yêu cầu.

Đừng decode payload hoặc nhận `X-User-Id` rồi coi đó là identity. Với nhiều issuers, subject cần gắn issuer/realm để tránh va chạm.

## 5. Những lỗi bảo mật phải phòng tránh

### 5.1. IDOR/BOLA: đổi ID là xem được tài liệu người khác

Cấu hình sai:

~~~java
@GetMapping("/api/tenants/{tenantId}/documents/{documentId}")
public Document read(
        @PathVariable String tenantId,
        @PathVariable String documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

Chỉ kiểm Authentication ở filter chain rồi query toàn cục là **Broken Object Level Authorization (BOLA)**, thường thấy dưới dạng **IDOR**. Tên tham số `tenantId` có mặt trong method signature không có tác dụng nếu không được dùng trong quyền và query.

### 5.2. Tenant spoofing qua header

~~~http
GET /api/documents/doc-b1
X-Tenant-Id: tenant-b
Authorization: Bearer token-of-alice
~~~

Nếu server lấy header này để chuyển schema hoặc database mà không kiểm membership, Alice có thể chọn tenant tùy ý. Header có thể là **requested tenant**, nhưng quyết định quyền phải đến từ identity/membership đáng tin.

### 5.3. Confused deputy

Một worker/service có service account quyền đọc toàn platform. Nếu user không có quyền tenant-b gửi yêu cầu export tenant-b và worker dùng quyền kỹ thuật của chính nó để lấy dữ liệu, worker đã trở thành confused deputy.

Phải phân biệt **actor user**, **service identity**, **delegated authorization** và **tenant được phép**; ghi audit và không dùng một credential backend rộng quyền thay thế kiểm tra quyền của caller.

### 5.4. Global ROLE_ADMIN vs tenant admin

Nếu `ROLE_ADMIN` được cấp vì user là admin của tenant-a, dùng `hasRole('ADMIN')` để cho phép sửa tenant-b là lỗi scope. Một mô hình hợp lệ cần định nghĩa:

- Platform administrator: quyền nhiều tenant đặc biệt, MFA/step-up và audit.
- Tenant administrator: chỉ tenant cụ thể.
- Tenant editor/viewer: quyền action giới hạn trong tenant.
- Resource owner: quyền đối với object/ACL cụ thể.

### 5.5. Chỉ ẩn tenant trong UI

User không thấy link tenant-b ở menu vẫn có thể tự sửa URL hoặc gọi API trực tiếp. **Frontend filtering và hidden buttons không phải authorization.** Server phải deny cả những request không đến từ UI chính thức.

## 6. Spring Security Servlet: đặt kiểm tra ở lớp nào?

### 6.1. HTTP rule xác minh danh tính chung

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/tenants/**").authenticated()
    .anyRequest().denyAll())
~~~

Cấu hình này yêu cầu người gọi được xác thực để vào nhóm endpoint. Nó **chưa cấp quyền theo tenant**. Nếu chỉ làm vậy, mọi user đã login đều có thể vượt HTTP layer cho bất kỳ giá trị tenantId nào.

### 6.2. Method security: kiểm tra tenant/action

Spring Security 6 có thể dùng:

~~~java
@EnableMethodSecurity
~~~

để bật pre/post method annotations, bao gồm `@PreAuthorize`. Đặt trên method của **Spring-managed service bean**:

~~~java
@PreAuthorize("@tenantAccess.canRead(authentication, #p0)")
public Document read(String tenantId, String documentId) {
    return repository.findByTenantIdAndId(tenantId, documentId)
        .orElseThrow(/* 404 */);
}
~~~

Đoạn này chỉ là mảnh code minh họa. `#p0` là tham số đầu (tenantId); `tenantAccess` là Spring policy bean, đánh giá Authentication và membership từ nguồn server. Khi lời gọi đi **qua method-security proxy**, policy chạy trước method body.

**Cảnh báo self-invocation:** method cùng class gọi trực tiếp `this.read(...)` có thể **bỏ qua AOP proxy**. Dùng controller → injected service bean, service khác hoặc access policy ở boundary rõ; vẫn giữ tenant constraint trong query như defense in depth. Private/final methods hoặc object tạo thủ công bằng `new` không phải interception boundary đáng tin trong proxy-based mode.

### 6.3. Policy bean tách khỏi SpEL dài

Một interface minh họa:

~~~java
@Component("tenantAccess")
class TenantAccess {
    boolean canRead(Authentication principal, String tenantId) {
        // Kiểm membership đang active, tenant status,
        // action READ và các điều kiện cần thiết.
    }
}
~~~

Đây là **mảnh kiến trúc**, không phải implementation đầy đủ. Bean có thể gọi trusted membership/permission store, kiểm tenant active, role theo tenant, token tenant binding, data residency, account status và revocation policy.

Khi kiểm resource-specific ACL, có thể mở rộng:

~~~java
@PreAuthorize(
    "@documentPolicy.canRead(authentication, #p0, #p1)")
public Document read(String tenantId, String documentId) { ... }
~~~

Policy phải dùng nguồn dữ liệu đã ràng buộc tenant; không tự đọc document toàn cục để vô tình gây thông tin lộ qua logs/errors. Tùy transaction/TOCTOU, business logic cũng phải kiểm invariants trước mutation.

### 6.4. HTTP + method authorization không thay thế nhau

HTTP layer giúp chặn anonymous, lựa chọn cơ chế xác thực và basic route policy. Method layer xử lý tenant/action/owner dựa trên tham số. Repository/data layer bảo đảm **không lấy resource của tenant khác**.

Một request có thể vượt HTTP `authenticated()` nhưng bị method `@PreAuthorize` từ chối. Một request vượt method membership vẫn có thể trả 404 vì tài liệu không thuộc tenant. Cả ba đều là kết quả đúng.

## 7. Ví dụ Java 17 chạy được: tenant-aware documents API

Lab này chủ ý giữ tất cả user có **cùng ROLE_USER**, vì mục tiêu là chứng minh quyền khác nhau theo tenant từ **membership server-side**, không phải từ global role. Thành phần:

- Spring Boot 3.3.5 MVC Servlet + Spring Security + HTTP Basic.
- `@EnableMethodSecurity` và `@PreAuthorize`.
- `TenantAccess` policy bean với Alice/Bob/Auditor membership.
- `DocumentService` dùng composite key (tenantId, documentId).
- GET đọc tài liệu, POST tạo tài liệu; CSRF vẫn bật.
- MockMvc positive/negative tests cho isolation.

### 7.1. Cấu trúc file

~~~text
tenant-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/tenant/
    │   ├── TenantDemoApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── TenantAccess.java
    │   ├── Document.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/example/tenant/
        └── TenantAuthorizationTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'tenant-security-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.2. Application

Tệp `src/main/java/example/tenant/TenantDemoApplication.java`:

~~~java
package example.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantDemoApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration

Tệp `src/main/java/example/tenant/SecurityConfiguration.java`:

~~~java
package example.tenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/tenants/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            // Không tắt CSRF để làm ví dụ này.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();
        UserDetails auditor = User.withUsername("auditor")
            .password(encoder.encode("auditor-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(
            alice, bob, auditor);
    }
}
~~~

HTTP `authenticated()` chưa thể phân biệt Alice/Bob/Auditor có quyền tenant nào; vì thế phải có policy bean. HTTP Basic chỉ để thử local, không phải giao thức được khuyến nghị cho mọi production app. HTTPS bắt buộc với credential thật.

### 7.4. TenantAccess: tra membership server-side

Tệp `src/main/java/example/tenant/TenantAccess.java`:

~~~java
package example.tenant;

import java.util.Map;
import java.util.Set;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("tenantAccess")
public class TenantAccess {

    // Demo: bảng quyền do server định nghĩa.
    // Production dùng stable user ID + membership store thật.
    private static final Map<String, Map<String, Set<String>>> RIGHTS =
        Map.of(
            "alice", Map.of(
                "tenant-a", Set.of("read", "write")),
            "bob", Map.of(
                "tenant-b", Set.of("read", "write")),
            "auditor", Map.of(
                "tenant-a", Set.of("read"),
                "tenant-b", Set.of("read"))
        );

    public boolean canRead(Authentication authentication,
                           String tenantId) {
        return has(authentication, tenantId, "read");
    }

    public boolean canWrite(Authentication authentication,
                            String tenantId) {
        return has(authentication, tenantId, "write");
    }

    private boolean has(Authentication authentication,
                        String tenantId,
                        String action) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || tenantId == null) {
            return false;
        }

        return RIGHTS
            .getOrDefault(authentication.getName(), Map.of())
            .getOrDefault(tenantId, Set.of())
            .contains(action);
    }
}
~~~

Điểm cần nhấn mạnh:

- `authentication.getName()` có nguồn từ cơ chế authentication đã xác minh.
- Requested `tenantId` có nguồn từ request, nhưng map quyết định xem principal có quyền không.
- `canRead` và `canWrite` tách riêng; auditor có READ ở hai tenant nhưng không có WRITE.
- Không có membership/permission → mặc định **false/deny**.
- Không đọc `X-Tenant-Id`, `X-Role` hoặc `X-User` từ client để cấp quyền.

Trong production, không dùng username dễ đổi làm identity chính; dùng stable subject kết hợp issuer nếu có nhiều IdP. Membership nên có tenant status, suspension, expiry, audit, caches được invalidation theo policy và logic role hierarchy rõ.

### 7.5. Document model

Tệp `src/main/java/example/tenant/Document.java`:

~~~java
package example.tenant;

public record Document(
    String id,
    String tenantId,
    String title
) {}
~~~

Record mang tenantId của object **được server lưu**, không phải field do client tự khai khi đọc. Khi tạo, service gắn tenantId đã qua policy check.

### 7.6. DocumentService: kiểm quyền và truy vấn scoped

Tệp `src/main/java/example/tenant/DocumentService.java`:

~~~java
package example.tenant;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private record DocumentKey(String tenantId, String documentId) {}

    private final Map<DocumentKey, Document> documents =
        new ConcurrentHashMap<>();

    private final AtomicLong nextId = new AtomicLong();

    public DocumentService() {
        put(new Document(
            "doc-a1", "tenant-a", "Alpha document"));
        put(new Document(
            "doc-b1", "tenant-b", "Beta document"));
    }

    @PreAuthorize("@tenantAccess.canRead(authentication, #p0)")
    public Document read(String tenantId, String documentId) {
        Document document = documents.get(
            new DocumentKey(tenantId, documentId));

        if (document == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return document;
    }

    @PreAuthorize("@tenantAccess.canWrite(authentication, #p0)")
    public Document create(String tenantId, String title) {
        if (title == null || title.isBlank()
                || title.length() > 120) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid title");
        }

        Document document = new Document(
            "new-" + nextId.incrementAndGet(),
            tenantId,
            title);

        put(document);
        return document;
    }

    private void put(Document document) {
        documents.put(new DocumentKey(
            document.tenantId(), document.id()), document);
    }
}
~~~

Trong một call được Spring proxy intercept, `@PreAuthorize` kiểm READ/WRITE membership **trước khi chạy method body**. Composite `DocumentKey(tenantId, documentId)` còn bảo đảm một member thuộc hai tenant không đọc nhầm resource từ tenant khác chỉ vì resource ID giống hoặc đoán được.

Thử nghĩ: auditor có READ tenant-a và tenant-b. `/tenant-b/documents/doc-a1` vượt check membership tenant-b, nhưng **không được trả** document tenant-a vì lookup composite key không tìm thấy. Nếu thay bằng `Map<String, Document>` chỉ index theo ID hoặc global `findById`, cách biệt tenant có thể bị phá.

**Không dùng mã in-memory này cho production.** Với DB, cần tenant predicate, foreign keys/composite keys, transaction isolation và object ACL thực. Còn phương thức có side effect phải giữ business invariants nếu membership thay đổi cạnh tranh.

### 7.7. DocumentController

Tệp `src/main/java/example/tenant/DocumentController.java`:

~~~java
package example.tenant;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {

    public record CreateDocument(String title) {}

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/{documentId}")
    public Document read(@PathVariable String tenantId,
                         @PathVariable String documentId) {
        return documents.read(tenantId, documentId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Document create(@PathVariable String tenantId,
                           @RequestBody CreateDocument body) {
        return documents.create(tenantId, body.title());
    }
}
~~~

`CreateDocument` chỉ nhận title, không cho client chọn một `tenantId` khác trong body. Nếu một API bắt buộc body có tenantId, server phải kiểm nó khớp tenant đã authorize, không tự đổi target tenant theo body. Controller inject `DocumentService` từ container để lời gọi qua method-security proxy; không `new DocumentService()`.

### 7.8. MockMvc tests bảo vệ tenant boundary

Tệp `src/test/java/example/tenant/TenantAuthorizationTests.java`:

~~~java
package example.tenant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantAuthorizationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotReadTenant() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadTenantA() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("tenant-a"))
            .andExpect(jsonPath("$.id").value("doc-a1"));
    }

    @Test
    void aliceCannotReadTenantB() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-b1")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadTenantB() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-b1")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("tenant-b"));
    }

    @Test
    void bobCannotReadTenantA() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReadBothTenants() throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1")
                .with(httpBasic("auditor", "auditor-pass")))
            .andExpect(status().isOk());

        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-b1")
                .with(httpBasic("auditor", "auditor-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void dualMembershipStillCannotReadOtherTenantResource()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-a1")
                .with(httpBasic("auditor", "auditor-pass")))
            .andExpect(status().isNotFound());
    }

    @Test
    void forgedTenantHeaderDoesNotGrantAccess()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-b/documents/doc-b1")
                .header("X-Tenant-Id", "tenant-b")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void headerDoesNotOverrideTenantInPath()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/doc-a1")
                .header("X-Tenant-Id", "tenant-b")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("tenant-a"));
    }

    @Test
    void aliceCanCreateTenantADocumentWithCsrf()
            throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-a/documents")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New alpha document\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.tenantId").value("tenant-a"))
            .andExpect(jsonPath("$.title")
                .value("New alpha document"));
    }

    @Test
    void auditorCannotWriteWithReadPermission()
            throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-a/documents")
                .with(httpBasic("auditor", "auditor-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Forbidden write\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void aliceCannotCreateForTenantB() throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-b/documents")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Cross tenant\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validWritePermissionDoesNotBypassCsrf()
            throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-a/documents")
                .with(httpBasic("alice", "alice-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Missing csrf\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingDocumentInsideAuthorizedTenantIs404()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/tenant-a/documents/missing")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isNotFound());
    }

    @Test
    void unknownTenantIsNotAutomaticallyAllowed()
            throws Exception {
        mockMvc.perform(get(
                "/api/tenants/unknown/documents/doc-a1")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTitleIs400WhenWriteAuthorized()
            throws Exception {
        mockMvc.perform(post(
                "/api/tenants/tenant-a/documents")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unrelatedRouteIsNotOpenForAuthenticatedUser()
            throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

### 7.9. Kết quả mong đợi và ý nghĩa

| Request / principal | Quyết định | Status demo |
| --- | --- | --- |
| Alice GET tenant-a/doc-a1 | Có READ tenant-a, resource đúng tenant | 200 |
| Alice GET tenant-b/doc-b1 | Không có membership tenant-b | 403 |
| Bob GET tenant-b/doc-b1 | Có READ tenant-b | 200 |
| Auditor GET tenant-a/doc-a1 | Có READ tenant-a | 200 |
| Auditor GET tenant-b/doc-b1 | Có READ tenant-b | 200 |
| Auditor GET tenant-b/doc-a1 | READ tenant-b hợp lệ nhưng document thuộc tenant-a | 404 |
| Alice GET tenant-b + header giả | Header không cấp membership | 403 |
| Alice POST tenant-a + CSRF | Có WRITE tenant-a | 201 |
| Auditor POST tenant-a + CSRF | Chỉ có READ | 403 |
| Alice POST tenant-a thiếu CSRF | CsrfFilter chặn trước method | 403 |
| Anonymous GET tenant-a | HTTP layer cần authenticated | 401 |

Bảng là **kỳ vọng theo cấu hình lab**, không phải kết quả runtime đã được thực thi trong lượt soạn bài. Một production API có thể chọn trả 404 thay 403 cho wrong-tenant để hạn chế tenant/resource enumeration; cần thống nhất policy, tránh lộ thông tin nhạy cảm trong error body và audit nội bộ.

### 7.10. Lệnh chạy

Trên máy có Java 17 và Gradle tương thích:

~~~bash
gradle test
gradle bootRun
~~~

Nếu project có Gradle Wrapper, ưu tiên `./gradlew test` và `./gradlew bootRun`; trên Windows dùng `gradlew.bat test` / `gradlew.bat bootRun`. Không chạy mã Spring Boot bằng `javac`/`java` trần nếu chưa cung cấp dependencies.

Ví dụ gọi localhost:

~~~bash
curl -i -u alice:alice-pass \
  http://localhost:8080/api/tenants/tenant-a/documents/doc-a1

curl -i -u alice:alice-pass \
  http://localhost:8080/api/tenants/tenant-b/documents/doc-b1

curl -i -u auditor:auditor-pass \
  http://localhost:8080/api/tenants/tenant-b/documents/doc-b1
~~~

Thông tin username/password ở đây **chỉ dùng local demo**. Với hệ thống thật không dùng HTTP không TLS và không đưa password vào shell history/process list; dùng TLS, secret manager/IdP, session hoặc token lifecycle phù hợp. Để thử POST giữ CSRF protection, dùng MockMvc như test hoặc client có cách lấy/gửi CSRF token hợp lệ.

## 8. Data isolation: SQL, khóa ghép và JOIN

Khi thay in-memory map bằng database, tenant predicate cần xuất hiện ở **mọi đường lấy/sửa dữ liệu** chứ không chỉ ở hàm đọc đơn lẻ.

### 8.1. Schema chia sẻ database

Ví dụ schema minh họa:

~~~sql
CREATE TABLE tenants (
    tenant_id VARCHAR(64) PRIMARY KEY,
    active BOOLEAN NOT NULL
);

CREATE TABLE memberships (
    user_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    permission VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL,
    PRIMARY KEY (user_id, tenant_id, permission),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE TABLE documents (
    tenant_id VARCHAR(64) NOT NULL,
    document_id VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, document_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
~~~

Mô hình permission có thể bổ sung role hierarchy, owner, membership expiry, invitation status, groups, soft deletion và audit. Các ràng buộc key phải phản ánh yêu cầu unique theo tenant, không mặc định globally unique.

### 8.2. Query đúng

~~~sql
SELECT d.tenant_id, d.document_id, d.title
FROM documents d
WHERE d.tenant_id = :authorized_tenant_id
  AND d.document_id = :document_id;
~~~

`authorized_tenant_id` nhắc rằng membership/action đã được kiểm. Bản thân query không cấp quyền nếu application truyền trực tiếp tenantId do client khai mà chưa kiểm tra.

Sai:

~~~sql
SELECT d.*
FROM documents d
WHERE d.document_id = :document_id;
~~~

Kể cả document id là UUID globally unique, việc biết ID không chứng minh quyền; sai lầm có thể là IDOR/BOLA.

### 8.3. JOIN cũng phải tenant-scoped

Nếu comments và documents cùng chứa `tenant_id`, đừng chỉ JOIN theo `document_id`:

~~~sql
-- Không đủ khi document_id có thể trùng giữa tenants:
SELECT c.*
FROM comments c
JOIN documents d ON d.document_id = c.document_id
WHERE d.tenant_id = :tenant_id;
~~~

Đúng hơn:

~~~sql
SELECT c.*
FROM comments c
JOIN documents d
  ON d.tenant_id = c.tenant_id
 AND d.document_id = c.document_id
WHERE d.tenant_id = :authorized_tenant_id
  AND d.document_id = :document_id;
~~~

Foreign keys của bảng con cũng nên bảo toàn tenant identifier. Cross-tenant aggregate, search và export cần permission riêng, không chỉ bỏ WHERE tenant_id để thuận tiện.

## 9. Row-Level Security và ORM multi-tenancy

### 9.1. RLS là defense in depth, không thay membership

PostgreSQL Row-Level Security (RLS) có thể thêm chính sách giới hạn rows theo tenant. Nhưng DB cần được cấu hình đúng:

- App DB role không được tùy ý bypass RLS; table owner/superuser/roles đặc quyền có những hành vi riêng.
- Tenant setting dùng cho policy phải do **application đáng tin** xác định sau authz, không lấy header tùy ý.
- Với connection pool, phải tránh tenant state rò sang request kế.
- SELECT/INSERT/UPDATE/DELETE và WITH CHECK cần policy thích hợp.
- Background migrations, support tooling và exports cần quyền được quản lý riêng.
- RLS không tự kiểm tất cả business ACL, role hành động hay token issuer.

Mảnh pseudo-SQL minh họa **không phải migration production hoàn chỉnh**:

~~~sql
-- App chỉ đặt setting này SAU khi authorized tenant.
-- Trong PostgreSQL, true dùng transaction-local setting.
SELECT set_config(
    'app.tenant_id',
    :authorized_tenant_id,
    true
);

CREATE POLICY documents_tenant_isolation
ON documents
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

Phải bật RLS trên table, tạo roles/policies, mở transaction đúng và kiểm connection/session settings. Không dùng raw SQL từ user để tự đặt tenant DB context rồi coi RLS đã an toàn.

### 9.2. Schema-per-tenant và database-per-tenant

Hai mô hình này có thể tăng isolation ở storage, nhưng không tự biến requestedTenant thành authorizedTenant. Nếu client đổi tenant và hệ thống chọn connection/schema theo input chưa kiểm membership, vẫn có tenant spoofing. Lớp routing tới datastore phải được bảo vệ như một authorization-sensitive operation.

### 9.3. Hibernate tenant resolver

Một ORM resolver có thể giúp xác định tenant identifier cho persistence, nhưng nó **không cấp quyền** cho caller. Trước khi gắn identifier vào persistence context, application phải kiểm principal/membership, và transactions/second-level cache phải không lẫn tenants.

Với request khác nhau chạy cùng thread pool/DB connection pool, cần bảo đảm tenant context được reset và transactional boundary nhất quán.

## 10. TenantContext, ThreadLocal và asynchronous work

Nhiều hệ thống tạo `TenantContextHolder` qua `ThreadLocal`. Điều này có thể tiện, nhưng không phải nguồn quyền.

~~~java
// Mảnh code minh họa context lifecycle; không phải authz policy.
try {
    TenantContext.set(authorizedTenantId);
    chain.doFilter(request, response);
} finally {
    TenantContext.clear();
}
~~~

Phải phân biệt:

- `requestedTenantId`: do request gợi ý.
- `authorizedTenantId`: đã đi qua tenant membership/action policy.
- `SecurityContextHolder`: chứa Authentication, không tự chứng minh được tenant.
- `TenantContextHolder`: chứa tenant scope cho request; chỉ đáng dùng nếu set từ authorized state.

**Không set ThreadLocal chỉ từ header chưa kiểm chứng rồi để repository tự chọn tenant schema.** Không dùng static global variable dùng chung cho nhiều requests. Với async executor, scheduled jobs, message consumers, context có thể mất hoặc bị tái sử dụng sai; nên truyền tenant/actor/permission context rõ ràng, có validation tại trust boundary.

Trong code quan trọng, truyền `tenantId` tường minh qua service/repository thường dễ review hơn:

~~~java
documentService.read(authorizedTenantId, documentId);
repository.findByTenantIdAndDocumentId(
    authorizedTenantId, documentId);
~~~

Nếu bắt buộc dùng ThreadLocal, cần clear trong `finally`, test concurrent requests, error paths, transaction leaks và không đổi tenant giữa chừng trong cùng nghiệp vụ.

## 11. Cache, search, object storage và background jobs

### 11.1. Cache key phải tenant-aware

Sai:

~~~text
key = document:doc-42
value = document thuộc tenant-a
~~~

Nếu tenant-b cũng có doc-42, cache lookup có thể trả nhầm document tenant-a. Đúng hơn:

~~~text
key = document:tenant-a:doc-42
key = document:tenant-b:doc-42
~~~

Cần canonical encoding để không va chạm, invalidation đúng tenant, và **user/resource ACL** trong cache khi dữ liệu riêng tư trong cùng tenant. Đừng cache response user A rồi trả user B chỉ vì cả hai thuộc một tenant.

### 11.2. Search index và aggregation

Full-text search, suggestions, facets và counts có thể tiết lộ thông tin tổ chức khác ngay cả khi detail endpoint đã bảo vệ. Tenant filter phải được áp dụng ở backend search query/index routing theo authorized tenant; không lấy toàn bộ kết quả rồi chỉ ẩn ở frontend.

### 11.3. Object storage/CDN

Key dạng `tenant-a/files/doc-42.pdf` không phải security boundary. Chỉ cấp signed download URL sau khi kiểm identity, tenant membership và resource ACL. Signed URL cần expiry và phạm vi phù hợp; CDN cache key/policy phải tránh cross-tenant leakage.

### 11.4. Events, queues và exports

Một event có thể mang:

~~~json
{
  "eventType": "DocumentCreated",
  "tenantId": "tenant-a",
  "documentId": "doc-a1",
  "actorId": "alice"
}
~~~

Các fields trong message không tự chứng minh publisher được phép hành động tại tenant-a. Producer cần authorize; consumer cần tin producer/source, validate schema/tenant, và không dùng service account toàn quyền làm confused deputy cho request chưa kiểm.

Exports/batch reports phải scope toàn bộ query, joins, file storage, notifications, downloadable links và audit. Một background job không còn HTTP session/ThreadLocal; truyền context có nguồn đáng tin rõ ràng.

## 12. Chuyển tenant và thu hồi membership

### 12.1. User chuyển tổ chức trong UI

Khi user chọn tenant-b:

1. Browser chỉ gửi requested tenant.
2. Backend kiểm user có active membership tenant-b.
3. Các request tiếp theo vẫn phải kiểm action/resource scope tương ứng.
4. Cache, websocket subscription, breadcrumbs và export state phải chuyển tenant nhất quán.
5. Nếu session lưu selected tenant, cập nhật session an toàn và cân nhắc CSRF cho thao tác thay đổi.

Ẩn tenant khỏi dropdown không ngăn user tự gọi một URL khác.

### 12.2. Thu hồi quyền và cửa sổ stale

Giả sử admin bỏ Alice khỏi tenant-a lúc 14:00. Một cache membership TTL 5 phút hoặc JWT chứa old tenant scope TTL 30 phút có thể khiến Alice còn được chấp nhận một khoảng thời gian. Xác định **maximum acceptable staleness** theo nghiệp vụ; với thao tác nhạy cảm cân nhắc online check, invalidation event, short TTL, revoke state và re-auth/step-up.

Không nhận một claim `tenantId` trong token cũ như bằng chứng membership vĩnh viễn.

### 12.3. Platform admin và impersonation

Platform admin có thể cần support đa tổ chức, nhưng đây phải là permission rõ ràng, ưu tiên MFA/step-up, reason, audit, expiry và giới hạn dữ liệu. Không dùng `ROLE_ADMIN` chung hoặc `X-Admin: true` để tắt mọi tenant check.

Nếu impersonate user, ghi **actor thật**, **effective identity**, **tenant target**, **action**, **resource** và **lý do** trong audit. Phân biệt service identity với user on-behalf-of.

## 13. Trạng thái HTTP, chống enumeration và lỗi thường gặp

| Tình huống | Status thường gặp | Cần nhớ |
| --- | --- | --- |
| Chưa authenticate trên protected endpoint | 401 với HTTP Basic/Bearer flow | Không trả tenant metadata |
| Authenticated nhưng không là tenant member | 403 hoặc 404 theo anti-enumeration policy | Không lộ tài liệu/owner |
| Là member nhưng thiếu WRITE | 403 | READ không hàm ý WRITE |
| Là member hai tenants nhưng ID chỉ thuộc tenant khác | 404 khi scoped lookup không thấy | Không global findById |
| Tenant không tồn tại | 404/403 theo contract | Tránh tenant enumeration |
| POST thiếu CSRF | Có thể 403 trước authz | Không suy sai thành thiếu role |
| JWT signature/issuer/audience sai | 401 trong bearer flow | Không tin claims trước verify |

Lab chọn 403 cho tenant permission denial và 404 cho document không tồn tại **trong tenant đã được phép**. Production có thể chọn 404 đồng nhất để giảm thông tin lộ; cần thận trọng về error bodies, timing, audit và caching.

### 13.1. Chẩn đoán theo thứ tự

1. Credential đã được verify chưa? Principal/issuer/authorities tin cậy là gì?
2. Requested tenant đến từ path/host/header/token/session nào? Có nguồn xung đột không?
3. Tenant ID có canonical và tenant active không?
4. Principal có active membership và đúng permission READ/WRITE/EXPORT không?
5. Spring method security đã bật chưa; service call có đi qua proxy không?
6. Repository query có tenant predicate/composite key không?
7. Object ACL/owner và các policy nghiệp vụ có được kiểm không?
8. Có filter CSRF hoặc HTTP security chặn trước service không?
9. Cache/search/exports/queues có tenant scoping tương tự không?
10. Membership cache có stale; token có scope/lifetime phù hợp không?
11. Có thread-local/DB connection tenant context bị rò giữa requests không?
12. Error/log có vô tình lộ user/resource data hoặc secrets không?

### 13.2. Các lỗi điển hình

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ check `authenticated()` | Tất cả user đã login có thể truy cập tenant tùy ý | Tenant action policy |
| Tin `X-Tenant-Id` | Tenant spoofing | Header chỉ là requested tenant |
| Role admin dùng global | Quyền một tenant bị nâng toàn platform | Tenant-scoped roles |
| Query `findById` toàn cục | IDOR/BOLA | Query bằng tenant + ID |
| JOIN thiếu tenant | Trộn dữ liệu qua bảng con | Composite tenant join |
| Trust JWT payload sau decode | Đọc token giả/không dành API | Verify signature, iss, aud, expiry |
| Proxy self-invocation | Method annotation không chạy | Cross-bean proxy boundary |
| TenantContext không clear | Thread reuse cross-tenant | finally + tests |
| Cache key chỉ có document ID | Cache trả sai tổ chức | Tenant-aware cache keys |
| Search filter ở frontend | Kết quả/facets lộ dữ liệu | Server-side tenant filter |
| Object key prefix là auth | Bị đoán/khai thác URL | Check ACL trước signed URL |
| Membership cache vô thời hạn | Revoke không có tác dụng | TTL/invalidation |
| Error trả thông tin tenant | Enumeration và metadata leaks | Error policy/redaction |
| Chỉ test happy path | Không phát hiện cross-tenant issue | Negative tests |
| Dùng demo Basic trên HTTP | Lộ credential | HTTPS và IdP phù hợp |

## 14. Checklist cho production

- [ ] Principal/Authentication đến từ nguồn đã verify, không từ header tùy ý.
- [ ] Requested tenant tách biệt authorized tenant; conflict policy rõ ràng.
- [ ] Tenant ID canonical, ổn định và tenant state được kiểm tra.
- [ ] Membership active và permissions theo tenant/action được quyết định server-side.
- [ ] Tenant roles khác platform roles; admin đặc biệt có audit.
- [ ] Mỗi protected request có policy check theo tenant và action, thiếu quyền mặc định deny.
- [ ] Resource ownership/ACL được kiểm khi nghiệp vụ yêu cầu.
- [ ] Mọi query, update, delete, JOIN, export có tenant predicate hoặc routing an toàn.
- [ ] Composite keys/foreign keys/uniques phản ánh tenant isolation.
- [ ] RLS/ORM tenancy là defense in depth, không thay authz.
- [ ] TenantContext chỉ từ authorized state, clear đúng, không leak qua thread/connection pool.
- [ ] Cache/search/CDN/object storage/signed links cô lập tenant và user ACL.
- [ ] Background jobs, events và batch reporting có identity/tenant context đáng tin.
- [ ] Revocation latency, cache invalidation và token expiry đáp ứng nghiệp vụ.
- [ ] Session tenant switch không làm user vượt membership.
- [ ] Response errors không lộ thông tin về tenants/resources không được phép.
- [ ] Có tests 401, 403, 404, 200, 201, wrong tenant, forged header, wrong resource ID và read-only user.
- [ ] Có tests CSRF riêng cho unsafe HTTP methods.
- [ ] Có regression tests cross-tenant khi thêm endpoints hoặc thay ORM/cache/index.
- [ ] Có audit và incident-response plan cho tenant breach.
- [ ] Không đưa demo passwords/in-memory membership vào production.

## 15. Bài tập luyện tập

1. Một JWT có `sub=alice` hợp lệ. Vì sao chưa đủ để cho Alice đọc tenant-b?
2. Phân biệt requested tenant và authorized tenant bằng URL `/tenants/tenant-b/...`.
3. Alice là editor tenant-a, viewer tenant-b. Viết action mapping READ/WRITE cho hai tenant.
4. Nếu service đã check member tenant-a nhưng vẫn dùng `findById("doc-b1")`, lỗ hổng nào còn tồn tại?
5. Vì sao UUID document không phải một permission?
6. Trong lab, Alice gửi `X-Tenant-Id: tenant-b`. Vì sao header không thay đổi kết quả authorization?
7. Auditor thuộc hai tenant nhưng `GET tenant-b/doc-a1` phải trả kết quả nào? Vì sao?
8. Chỉ có `ROLE_USER` cho ba user demo, policy nào phân biệt quyền từng tenant?
9. Tại sao `@PreAuthorize` phải được gọi qua Spring-managed proxy?
10. Một service method nội bộ tự gọi method có annotation, nguy cơ self-invocation là gì?
11. POST hợp lệ thiếu CSRF và POST có CSRF nhưng thiếu WRITE đều có thể 403. Debug thế nào?
12. Thiết kế SQL query và index để tìm tài liệu bằng `(tenant_id, document_id)`.
13. Viết JOIN comments/documents đủ tenant constraints, và một test ngăn trộn comments.
14. Tại sao chỉ filter tenant ở frontend search kết quả là không đủ?
15. Thiết kế cache key cho documents trùng ID ở hai tenants và user ACL riêng.
16. Khi đổi sang schema-per-tenant, vì sao vẫn phải kiểm membership trước khi chọn schema?
17. Nếu RLS setting xuất phát trực tiếp từ header chưa authorized thì lỗi gì?
18. Membership bị revoke nhưng JWT còn hạn 30 phút: chính sách nào quyết định cửa sổ chấp nhận?
19. Khi user switch tenant qua UI, các cache/websocket subscriptions cần xử lý thế nào?
20. Thiết kế audit record cho platform admin impersonate user ở tenant-b.
21. Một worker queue có service account đa tenant: chống confused deputy bằng cách nào?
22. Khi nào bạn trả 403, khi nào trả 404 cho tenant/resource không có quyền?
23. Viết thêm MockMvc test Bob có WRITE tenant-b nhưng không có READ tenant-a.
24. Một export CSV từ nhiều bảng phải kiểm những lớp isolation nào?
25. Lập bảng negative tests cho GET/POST/DELETE, anonymous, Alice, Bob, Auditor và tenant không tồn tại.

## 16. Kết luận

**Đa tổ chức là phân quyền theo tập ba yếu tố: principal, tenant và resource/action.** Một người đã xác thực chưa chắc thuộc tenant đang yêu cầu; một người thuộc tenant chưa chắc có quyền WRITE; và một user có quyền trong hai tenants vẫn không được dùng URL tenant này để đọc resource tenant kia.

Trong Spring Security Servlet, một hướng triển khai rõ ràng là: **xác minh credential ở filter chain → nhận tenant mục tiêu từ request → kiểm membership/permission từ nguồn đáng tin qua service policy → truy vấn tài nguyên ràng buộc tenant → kiểm owner/ACL bổ sung → trả dữ liệu và audit đúng scope**. Tăng cường bằng tenant-aware cache, database queries, jobs và tests cross-tenant để tránh dữ liệu của tổ chức này trở thành dữ liệu của tổ chức khác.
