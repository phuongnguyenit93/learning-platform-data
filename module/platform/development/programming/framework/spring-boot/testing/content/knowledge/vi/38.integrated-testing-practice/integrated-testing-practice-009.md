# Kiểm thử xác thực, quyền sở hữu và truy cập chéo tenant — Spring Boot Security

## 1. Bài toán: đăng nhập thành công chưa có nghĩa được phép xem mọi tài nguyên

Giả sử một nền tảng lưu tài liệu cho nhiều tổ chức (tenant). Người dùng **alice** và **bob** thuộc tenant `acme`; **carol** thuộc tenant `beta`. Alice sở hữu tài liệu A, Bob sở hữu tài liệu B. Mỗi tenant có quản trị viên được phép xem/sửa tài liệu của thành viên trong **tenant đó**, nhưng không được can thiệp tài liệu của tenant khác.

Một API có thể bắt buộc đăng nhập mà vẫn có lỗ hổng nghiêm trọng:

~~~http
GET /tenants/acme/documents/123
Authorization: Basic ...
~~~

Nếu code chỉ gọi `repository.findById(123)` rồi trả kết quả, Bob hoặc Carol có thể đổi ID để lấy tài liệu của Alice. Đây là dạng **Broken Object Level Authorization (BOLA)**, thường được gọi là **Insecure Direct Object Reference (IDOR)**. Nếu API có quyền quản trị nhưng bỏ qua ranh giới tenant, một tenant admin cũng có thể đọc/xóa dữ liệu tenant khác. Đây không phải lỗi password: nó là lỗi **authorization ở cấp tài nguyên và ngữ cảnh tenant**.

Bài này hướng dẫn thiết kế **bộ kiểm thử tích hợp** cho Spring Boot 3.5/Java 17, gồm xác thực HTTP Basic minh họa, Spring Security filter chain, ownership/tenant policy, JPA repository thực, MockMvc HTTP requests và negative security cases. Dữ liệu chạy trên H2 in-memory để ví dụ dễ tái lập không cần Docker; khi production dùng PostgreSQL và database-level isolation, cần thêm integration suite với PostgreSQL/Testcontainers như phần mở rộng. Không tuyên bố H2 thay thế kiểm thử bảo mật ở tầng database production.

### Kết quả học tập

1. Phân biệt **authentication**, **function-level authorization**, **object-level authorization**, **ownership** và **tenant isolation**.
2. Xác định principal, authorities/roles và tenant memberships từ **nguồn được máy chủ xác thực**, không từ header/body do client tự khai.
3. Viết policy rõ ràng cho người sở hữu, thành viên khác, quản trị viên cùng tenant và quản trị viên tenant khác.
4. Phân biệt HTTP `401 Unauthorized`, `403 Forbidden`, `404 Not Found` khi thiết kế API không rò existence.
5. Kiểm đọc, liệt kê, tạo, sửa, xóa với ID của người khác và tenant khác.
6. Chống **mass assignment**: client không được tự ghi `ownerUsername` hoặc `tenantId` vào entity.
7. Kiểm CSRF với requests tạo/sửa/xóa; không tắt security filters trong MockMvc.
8. Kiểm JSON response không rò sensitive fields và danh sách không trộn tenants.
9. Biết tác dụng/hạn chế của `@WithMockUser`, `httpBasic`, `csrf()`, MockMvc, `@WebMvcTest` và `@SpringBootTest`.
10. Chạy full context + JPA trong integration tests, giữ fixture độc lập, tránh test bị lừa bởi mocks.
11. Mở rộng kiểm thử sang JWT resource server, PostgreSQL RLS, cache, async và multi-tenant reports.
12. Thiết kế CI gate và ma trận kiểm thử bảo mật theo OWASP API Security Top 10.

## 2. Thuật ngữ và bề mặt tấn công

### 2.1 Authentication (xác thực)

Trả lời **“ai đang gọi?”**. Ví dụ HTTP Basic credentials được Spring Security xử lý để tạo `Authentication` có tên principal `alice`. Trong production có thể dùng session cookie, OIDC login hoặc JWT bearer token sau khi xác minh chữ ký, issuer, audience, expiration và claims.

- Không gửi credentials: request được coi anonymous.
- Sai password/token: authentication thất bại.
- Credentials hợp lệ: caller có `Authentication`, **chưa mặc nhiên được đọc bất kỳ document ID nào**.

### 2.2 Authorization ở cấp chức năng

Trả lời **“caller có quyền thực hiện loại hành động này không?”**. Ví dụ role `ROLE_TENANT_ADMIN` cho phép quản trị tài liệu thuộc tenant của mình; `ROLE_USER` có thể sửa tài liệu mình sở hữu.

Chỉ kiểm `hasRole("USER")` ở URL là chưa đủ: mọi user đều có role USER, nhưng không có quyền sửa mọi record.

### 2.3 Object-level authorization / ownership

Trả lời **“caller có quyền trên đúng record này không?”**. Ví dụ:

- Alice đọc A: cho phép.
- Bob đọc A trong cùng tenant: từ chối nếu policy chỉ owner/admin.
- Carol đọc A qua ID có thể đoán: từ chối dù ID hợp lệ.
- Quản trị viên của acme đọc tài liệu Alice: cho phép nếu policy cho quyền đó.

Không dùng “ID khó đoán” như biện pháp thay ownership check. UUID làm dò ID khó hơn nhưng không thay authorization.

### 2.4 Tenant isolation

Trả lời **“caller thuộc tenant mà record đang ở không?”**. Khi URL chứa `/tenants/{tenantId}`, `tenantId` vẫn là **dữ liệu client chọn**. Server phải đối chiếu nó với trusted memberships trong authenticated principal; sau đó query DB **đồng thời** theo tenant và record ID.

Không lấy `X-Tenant-Id` do client gửi rồi mặc định đó là tenant đã được xác thực. Header chỉ là một input để **yêu cầu chuyển tenant context**, phải được xác minh against memberships nếu hỗ trợ.

### 2.5 BOLA, BFLA và mass assignment

| Rủi ro | Ví dụ | Bộ kiểm thử |
| --- | --- | --- |
| BOLA/IDOR | Bob đổi ID để GET/PATCH tài liệu Alice | Swap object IDs giữa accounts |
| BFLA | User thường gọi endpoint admin không được phép | Đổi role với cùng function |
| Cross-tenant leak | Admin beta GET tài liệu acme | Swap tenant path/record ID |
| Broken object property auth | POST tự ghi ownerUsername=alice | Reject/ignore protected attributes |
| List/query isolation | GET list trả tài liệu tenant khác | Kiểm tất cả rows/aggregate |
| CSRF | Browser authenticated bị ép POST/PATCH | Missing/invalid CSRF => 403 |
| Authentication bypass | Request anonymous trả dữ liệu | 401 trước service |
| Cache bleed | User B nhận cached response của A | Cache key/context tests |

## 3. Chính sách của demo: một bảng quyền cụ thể

Dữ liệu mẫu:

| Principal | Role | Membership | Sở hữu |
| --- | --- | --- | --- |
| alice | ROLE_USER | TENANT_acme | tài liệu “Alpha draft” |
| bob | ROLE_USER | TENANT_acme | tài liệu “Bob notes” |
| carol | ROLE_USER | TENANT_beta | tài liệu “Beta plan” |
| admin-acme | ROLE_TENANT_ADMIN | TENANT_acme | không cần sở hữu để quản trị acme |
| admin-beta | ROLE_TENANT_ADMIN | TENANT_beta | không được chạm acme |
| guest | ROLE_USER | không có tenant membership | không xem tài liệu tenant nào |

Quy tắc cụ thể:

1. Mọi endpoint `/tenants/{tenantId}/documents/**` yêu cầu xác thực.
2. Caller phải có authority `TENANT_{tenantId}` mới được thao tác trong tenant trên URL.
3. Người dùng thường chỉ đọc/liệt kê/sửa/xóa document có `ownerUsername == authentication.getName()`.
4. `ROLE_TENANT_ADMIN` có thể xem/sửa/xóa tài liệu của người khác **nếu thuộc cùng tenant**.
5. POST chỉ nhận `title`; server đặt `tenantId` từ route đã được xác minh và `ownerUsername` từ authenticated principal.
6. Không tồn tại document hoặc không có quyền ownership đều trả `404` để tránh xác nhận ID tồn tại với người không được phép.
7. Không có quyền vào tenant trên route trả `403`, không phụ thuộc record ID.
8. Không xác thực hoặc password sai trả `401` qua HTTP Basic entry point.
9. CSRF vẫn bật trong demo; POST/PATCH/DELETE với credentials nhưng thiếu CSRF token bị từ chối.
10. JSON output chỉ có `id` và `title`; owner/tenant không được tự động serialized.

### 3.1 Vì sao có cả 403 và 404?

Đây là lựa chọn policy, **không phải quy tắc duy nhất của HTTP**. `403` nói caller đã được nhận diện nhưng không có tenant membership/permission. `404` cho owner check thất bại để caller không phân biệt “ID không tồn tại” với “ID tồn tại nhưng thuộc người khác”. Một hệ thống yêu cầu tránh mọi existence leakage có thể trả `404` cho cả tenant mismatch, miễn policy nhất quán và test đúng.

**Quan trọng:** đừng để GET trả 404 nhưng PATCH trả 403 kèm thông tin record tồn tại nếu mục tiêu là che existence. Cả đọc và sửa/xóa phải dùng chung phép kiểm record visibility.

## 4. Kiến trúc kiểm thử end-to-end trong JVM

~~~text
MockMvc request
    |
    +-- Spring Security FilterChainProxy
    |     +-- HTTP Basic authentication
    |     +-- SecurityContext/Authentication
    |     +-- CSRF for unsafe methods
    |     +-- anyRequest().authenticated()
    |
    v
DocumentController
    |
    +-- route tenantId treated as untrusted input
    +-- authenticated principal resolved from security context
    |
    v
DocumentService
    |
    +-- validates tenant membership
    +-- checks owner OR same-tenant admin
    +-- scopes database lookup/list by tenantId
    |
    v
DocumentRepository (real Spring Data JPA)
    |
    v
H2 in-memory database for runnable demo
~~~

Sử dụng `@SpringBootTest` + `@AutoConfigureMockMvc` để filter chain, controller, service, repository, transaction và JSON serialization cùng chạy. Không dùng `@MockitoBean DocumentService` trong test chính, vì mock service sẽ bỏ qua chính authorization logic cần chứng minh.

H2 ở đây chỉ làm persistence fixture đơn giản. Nếu production dùng PostgreSQL RLS, stored procedures, JSONB hoặc database-specific tenant constraints, cần một bài integration test bổ sung với **đúng database engine sản xuất**.

## 5. File tree của project Java 17+/Spring Boot 3.5

~~~text
tenant-security-demo/
  settings.gradle
  build.gradle
  src/main/java/example/tenant/
    TenantSecurityApplication.java
    SecurityConfig.java
    TenantDocument.java
    TenantDocumentRepository.java
    TenantDocumentService.java
    TenantDocumentController.java
  src/main/resources/
    application.properties
  src/test/java/example/tenant/
    TenantDocumentSecurityTest.java
  .github/workflows/
    security-tests.yml
~~~

Bài này tạo **một test class tích hợp** với nhiều user/tenant cases. Không cần Docker để chạy demo. Trong production, hãy thay in-memory test users bằng authenticated identities/authorization policy thật và xây thêm integration suite đối với database isolation.

## 6. settings.gradle

~~~groovy
rootProject.name = 'tenant-security-demo'
~~~

## 7. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    // Database fixture for this runnable demonstration.
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Deterministic baseline for mutable database fixtures.
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
    reports {
        html.required = true
        junitXml.required = true
    }
}
~~~

Tại sao cần các dependency?

- `spring-boot-starter-web`: MVC controller, Jackson JSON, MockMvc infrastructure.
- `spring-boot-starter-security`: HTTP Basic authentication, `SecurityFilterChain`, CSRF, authorization.
- `spring-boot-starter-data-jpa`: repository thật và transaction.
- `spring-boot-starter-validation`: `@Valid`, `@NotBlank`, `@Size` ở request DTO.
- `h2`: database mẫu chạy trong process, không đòi Docker/credentials.
- `spring-boot-starter-test`: JUnit Jupiter, Spring testing/MockMvc.
- `spring-security-test`: `httpBasic()` và `csrf()` request post-processors.
- `junit-platform-launcher` và `useJUnitPlatform()`: chạy Jupiter trên Gradle.

**Không tắt Spring Security filters** bằng `@AutoConfigureMockMvc(addFilters=false)`. Làm vậy sẽ khiến nhiều tests “xanh” trong khi authentication, CSRF hoặc authorization chain không thực thi.

## 8. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:tenant_security_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false

# A strict request DTO contract rejects attempts to add owner/tenant fields.
spring.jackson.deserialization.fail-on-unknown-properties=true
~~~

`create-drop` phù hợp với demo database ephemeral **không có production migrations**. Trong hệ thống thật, dùng Flyway/Liquibase schema và `ddl-auto=validate` theo policy, không để ORM tự tạo schema production.

Cấu hình `spring.jackson.deserialization.fail-on-unknown-properties=true` bảo đảm JSON chứa property ngoài request record (chẳng hạn `ownerUsername` hoặc `tenantId`) bị từ chối, thay vì âm thầm gán vào entity. Kể cả khi tổ chức chọn **ignore unknown properties** để giữ backward compatibility, DTO vẫn **không được chứa** các trường nhạy cảm cho client tự ghi.

## 9. TenantSecurityApplication.java

`src/main/java/example/tenant/TenantSecurityApplication.java`:

~~~java
package example.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantSecurityApplication.class, args);
    }
}
~~~

Package `example.tenant` chứa controller, service, repository, entity và security config; component scanning tìm được mọi beans cần thiết.

## 10. TenantDocument.java — entity với tenant_id và owner

`src/main/java/example/tenant/TenantDocument.java`:

~~~java
package example.tenant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(
    name = "tenant_documents",
    indexes = @Index(
        name = "idx_document_tenant_owner",
        columnList = "tenant_id,owner_username"))
public class TenantDocument {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 32)
    private String tenantId;

    @Column(name = "owner_username", nullable = false, length = 80)
    private String ownerUsername;

    @Column(name = "title", nullable = false, length = 120)
    private String title;

    protected TenantDocument() {
        // JPA constructor.
    }

    public TenantDocument(
            String tenantId,
            String ownerUsername,
            String title) {
        this.tenantId = tenantId;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

### 10.1 Vì sao entity không trực tiếp làm @RequestBody?

Nếu controller nhận `@RequestBody TenantDocument`, một client có thể gửi:

~~~json
{
  "title": "Report",
  "ownerUsername": "someone-else",
  "tenantId": "different-tenant"
}
~~~

Đây là rủi ro **mass assignment / broken object property-level authorization**. Dù authorization trong service có thể chặn, phương án an toàn hơn là **DTO allowlist**: chỉ đưa các trường client được phép chỉnh vào request record; tenant và owner phải được server ấn định.

Trong demo, `tenantId` và `ownerUsername` không có public setters; tuy vậy không phụ thuộc vào việc thiếu setter như lớp bảo vệ duy nhất. Service vẫn có trách nhiệm tạo record với identity đã xác thực, và strict JSON request DTO không cho client chèn protected fields.

### 10.2 Vì sao cần tenant_id trong mọi tài liệu?

Trong shared-table multi-tenancy, mỗi record cần một partition key đáng tin để query/filter. Chỉ lưu `ownerUsername` và nghĩ username không trùng giữa tenant là không an toàn: nhiều tenant có thể có user cùng display name hoặc cùng local account ID. Production nên dùng immutable tenant ID và subject/account ID từ identity provider, tránh username dễ đổi làm khóa quyền sở hữu.

## 11. TenantDocumentRepository.java — truy vấn phải có tenant scope

`src/main/java/example/tenant/TenantDocumentRepository.java`:

~~~java
package example.tenant;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface TenantDocumentRepository
        extends JpaRepository<TenantDocument, Long> {

    Optional<TenantDocument> findByIdAndTenantId(
            Long id, String tenantId);

    List<TenantDocument>
        findByTenantIdAndOwnerUsernameOrderByIdAsc(
                String tenantId, String ownerUsername);

    List<TenantDocument> findByTenantIdOrderByIdAsc(
            String tenantId);
}
~~~

Các method quan trọng:

- `findByIdAndTenantId`: cả object ID lẫn tenant ID được đưa vào SQL lookup, giảm nguy cơ tìm record khác tenant rồi quên check.
- `findByTenantIdAndOwnerUsernameOrderByIdAsc`: user thường chỉ liệt kê docs thuộc chính mình trong tenant hiện tại.
- `findByTenantIdOrderByIdAsc`: chỉ service cho tenant admin đã được kiểm membership/role gọi method này.
- `JpaRepository.findById` vẫn tồn tại vì interface kế thừa; **đừng** dùng nó làm lookup mặc định trong endpoints multi-tenant nếu thiếu kiểm tenant.

Đây là defense in depth ở data access, nhưng không có nghĩa repository tự chặn mọi caller: code khác vẫn có thể gọi `findAll` hoặc `findById`. Dự án thật nên áp policy ở service/query boundaries, code review, và cân nhắc database Row Level Security (RLS) nếu cần tenant isolation mạnh hơn.

### 11.1 Tránh ghép SQL thủ công với tenant ID

Không tạo native SQL bằng string concatenation từ `tenantId` hoặc `ownerUsername`. Spring Data derived queries/parameter binding giảm SQL injection. Tenant membership **vẫn phải được xác minh** trước khi bind; parameterized SQL không kiểm authorization thay bạn.

## 12. SecurityConfig.java — HTTP Basic, users và CSRF

`src/main/java/example/tenant/SecurityConfig.java`:

~~~java
package example.tenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String password = encoder.encode("test-secret");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(password)
                .authorities("ROLE_USER", "TENANT_acme")
                .build(),
            User.withUsername("bob")
                .password(password)
                .authorities("ROLE_USER", "TENANT_acme")
                .build(),
            User.withUsername("carol")
                .password(password)
                .authorities("ROLE_USER", "TENANT_beta")
                .build(),
            User.withUsername("admin-acme")
                .password(password)
                .authorities(
                    "ROLE_TENANT_ADMIN", "TENANT_acme")
                .build(),
            User.withUsername("admin-beta")
                .password(password)
                .authorities(
                    "ROLE_TENANT_ADMIN", "TENANT_beta")
                .build(),
            User.withUsername("guest")
                .password(password)
                .authorities("ROLE_USER")
                .build()
        );
    }
}
~~~

### 12.1 Vì sao dùng in-memory accounts?

Để toàn bộ demo độc lập với identity provider. Credentials cố định `test-secret` là **test fixture**, không phải password production. Không chạy cấu hình in-memory này trên mạng công khai hoặc dùng trong một ứng dụng production. HTTP Basic **chỉ thích hợp qua HTTPS** vì Base64 không mã hóa bí mật.

Trong production, tùy kiến trúc, thay bean bằng Spring Security OAuth2 Resource Server JWT, OIDC login/session hoặc một UserDetailsService thật. **Chữ ký JWT, issuer, audience, expiry, key rotation và claim mapping phải được xác minh từ nguồn tin cậy** trước khi lấy tenant memberships.

### 12.2 Vì sao anyRequest().authenticated() chưa đủ?

Nó chặn anonymous request ở filter chain. Nhưng sau khi Alice đăng nhập, filter chain **chưa biết** Alice được đọc document 123 hay không; policy record/tenant nằm trong service. Test phải kiểm **cả hai lớp**.

### 12.3 ROLE_TENANT_ADMIN không đồng nghĩa global admin

Một tenant admin còn phải có authority `TENANT_acme`. Nếu caller chỉ có role admin nhưng không có membership vào tenant beta, service từ chối. **Role scope luôn cần tenant scope**, tránh lỗi “admin của công ty A là admin của toàn hệ thống”.

### 12.4 Vì sao không csrf.disable()?

Demo dùng HTTP Basic, một cơ chế có thể được trình duyệt tự gửi credentials trong một số ngữ cảnh; CSRF threat model phải được đánh giá nghiêm túc. Giữ mặc định CSRF cho unsafe methods và kiểm `csrf()` trong MockMvc. Với API bearer-token stateless không dùng cookie/browser-automatically-sent credentials, một chính sách CSRF khác có thể phù hợp, nhưng **không** sao chép disable toàn app chỉ để tests POST chạy.

## 13. TenantDocumentService.java — policy tại service boundary

`src/main/java/example/tenant/TenantDocumentService.java`:

~~~java
package example.tenant;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class TenantDocumentService {

    private final TenantDocumentRepository repository;

    public TenantDocumentService(
            TenantDocumentRepository repository) {
        this.repository = repository;
    }

    private void requireTenant(
            String tenantId, Authentication authentication) {

        if (authentication == null
                || !authentication.isAuthenticated()) {
            throw new AccessDeniedException(
                    "Authentication required");
        }

        String required = "TENANT_" + tenantId;

        boolean member = authentication.getAuthorities()
                .stream()
                .anyMatch(authority ->
                    required.equals(authority.getAuthority()));

        if (!member) {
            throw new AccessDeniedException(
                    "Tenant membership required");
        }
    }

    private boolean isTenantAdmin(Authentication authentication) {
        return authentication.getAuthorities()
                .stream()
                .anyMatch(authority ->
                    "ROLE_TENANT_ADMIN".equals(
                            authority.getAuthority()));
    }

    private TenantDocument visibleDocument(
            String tenantId, Long documentId,
            Authentication authentication) {

        requireTenant(tenantId, authentication);

        return repository
                .findByIdAndTenantId(documentId, tenantId)
                .filter(doc ->
                    isTenantAdmin(authentication)
                    || doc.getOwnerUsername()
                          .equals(authentication.getName()))
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));
    }

    @Transactional(readOnly = true)
    public TenantDocument read(
            String tenantId, Long documentId,
            Authentication authentication) {
        return visibleDocument(
                tenantId, documentId, authentication);
    }

    @Transactional(readOnly = true)
    public List<TenantDocument> list(
            String tenantId, Authentication authentication) {

        requireTenant(tenantId, authentication);

        if (isTenantAdmin(authentication)) {
            return repository.findByTenantIdOrderByIdAsc(tenantId);
        }

        return repository
                .findByTenantIdAndOwnerUsernameOrderByIdAsc(
                        tenantId, authentication.getName());
    }

    @Transactional
    public TenantDocument create(
            String tenantId, String title,
            Authentication authentication) {

        requireTenant(tenantId, authentication);

        TenantDocument document = new TenantDocument(
                tenantId, authentication.getName(), title);

        return repository.save(document);
    }

    @Transactional
    public TenantDocument rename(
            String tenantId, Long documentId,
            String newTitle, Authentication authentication) {

        TenantDocument document = visibleDocument(
                tenantId, documentId, authentication);

        document.rename(newTitle);
        return document;
    }

    @Transactional
    public void remove(
            String tenantId, Long documentId,
            Authentication authentication) {

        TenantDocument document = visibleDocument(
                tenantId, documentId, authentication);

        repository.delete(document);
    }
}
~~~

### 13.1 Thứ tự kiểm tra phải fail-closed

1. `requireTenant` xác minh caller có membership vào tenant của request.
2. `findByIdAndTenantId` giới hạn database query vào tenant đó.
3. Chỉ record owner hoặc tenant admin mới được đọc/sửa/xóa record.
4. Khi ownership check fail hoặc document ID không tồn tại, cùng trả `404`.
5. CREATE dùng principal name từ `Authentication`, không nhận owner do client gửi.
6. LIST chỉ query tenant + owner (hoặc tenant-only với admin được xác minh).

Nếu service trực tiếp gọi `repository.findById(id)` và trả record trước khi kiểm quyền, tài liệu có thể rò qua response/logging/events ngay cả khi controller sau đó trả lỗi. **Kiểm authorization càng gần data access càng tốt.**

### 13.2 Authentication phải là từ SecurityContext, không từ request JSON

Controller sẽ nhận `Authentication` do Spring Security cung cấp cho request đã đi qua filter chain. Service nhận nó như một trusted server-side argument **từ controller**, không tạo Authentication từ `username`/`roles` do client gửi. Với public service API có nhiều callers (batch jobs, GraphQL, message consumers), nên có một policy abstraction lấy validated identity từ security context và tách HTTP response translation, không để các callers tự dựng role bất kỳ.

### 13.3 Vì sao không dùng @PreAuthorize trong demo?

Method security `@PreAuthorize` (kèm `@EnableMethodSecurity`) là một giải pháp hợp lệ, nhưng không tự động giúp repository query tenant-scoped. Bài chọn service checks rõ ràng để thấy đầy đủ record visibility và write flow. Trong hệ thống lớn, có thể tách `DocumentPolicy.canRead/canEdit`, dùng `AuthorizationManager`/`@PreAuthorize` và bảo đảm test cả method security lẫn query scoping.

### 13.4 @Transactional giúp gì?

- `create`: repository save trong transaction, commit sau method thành công.
- `rename`: entity được load và managed; gọi `rename` kích hoạt JPA dirty checking; UPDATE được flush khi transaction commit.
- `remove`: DELETE trong transaction.
- `read/list`: read-only transaction giúp consistency/lazy-loading nếu cần, không phải authorization check.
- Không dùng `@Transactional` trên toàn bộ MockMvc test class: các HTTP request/service transactions cần được kiểm như khi app xử lý thật, không để test-managed rollback che lỗi quyền.

### 13.5 Service không trả toàn bộ entity cho client

Service có thể trả JPA entity nội bộ; controller phải map sang response DTO đã định nghĩa. Không serialize entity trực tiếp nếu nó có ownerEmail, tenantId, internalFlags hoặc association lazy chứa thông tin nhạy cảm.

## 14. TenantDocumentController.java — DTO allowlist và status codes

`src/main/java/example/tenant/TenantDocumentController.java`:

~~~java
package example.tenant;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/tenants/{tenantId}/documents")
public class TenantDocumentController {

    private final TenantDocumentService service;

    public TenantDocumentController(TenantDocumentService service) {
        this.service = service;
    }

    public record DocumentView(Long id, String title) {
        static DocumentView from(TenantDocument doc) {
            return new DocumentView(
                    doc.getId(), doc.getTitle());
        }
    }

    public record CreateDocumentRequest(
            @NotBlank @Size(max = 120) String title) {
    }

    public record RenameDocumentRequest(
            @NotBlank @Size(max = 120) String title) {
    }

    @GetMapping("/{id}")
    public DocumentView get(
            @PathVariable String tenantId,
            @PathVariable Long id,
            Authentication authentication) {

        return DocumentView.from(
                service.read(tenantId, id, authentication));
    }

    @GetMapping
    public List<DocumentView> list(
            @PathVariable String tenantId,
            Authentication authentication) {

        return service.list(tenantId, authentication)
                .stream()
                .map(DocumentView::from)
                .toList();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public DocumentView create(
            @PathVariable String tenantId,
            @Valid @RequestBody CreateDocumentRequest request,
            Authentication authentication) {

        return DocumentView.from(
                service.create(
                    tenantId, request.title(), authentication));
    }

    @PatchMapping("/{id}")
    public DocumentView rename(
            @PathVariable String tenantId,
            @PathVariable Long id,
            @Valid @RequestBody RenameDocumentRequest request,
            Authentication authentication) {

        return DocumentView.from(
                service.rename(
                    tenantId, id, request.title(),
                    authentication));
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            @PathVariable String tenantId,
            @PathVariable Long id,
            Authentication authentication) {

        service.remove(tenantId, id, authentication);
    }
}
~~~

### 14.1 Không làm controller tin body owner hoặc tenant

Create/Rename request records chỉ có `title`. Client không thể dùng DTO hợp lệ để chuyển owner hay tenant, kể cả nếu biết ID của người khác. Service vẫn independently gắn identity theo `authentication.getName()` và đã kiểm membership.

### 14.2 @Valid bảo vệ gì, không bảo vệ gì?

`@NotBlank` và `@Size(max=120)` bảo vệ input shape, giúp reject title trống/quá dài. Nó **không** chứng minh caller có quyền sửa document. Validator có thể PASS cho JSON hợp lệ của kẻ tấn công; service cần object/tenant authorization riêng.

### 14.3 Response DTO giới hạn dữ liệu

`DocumentView` chỉ xuất `id` và `title`. Test cần assert JSON response không có `tenantId`/`ownerUsername` và list không có record thuộc tenant khác. Nhưng nhớ rằng **không trả protected fields** khác với **không cho xem tài liệu**: ngay cả title vẫn nhạy cảm nếu owner check fail.

## 15. Test fixture và ma trận tấn công

Một test bảo mật nên có **ít nhất hai tài khoản trong cùng tenant** và **ít nhất một tài khoản tenant khác**. Nếu chỉ có Alice và một document, test không phát hiện được horizontal privilege escalation hoặc cross-tenant leak.

Dữ liệu được reset trong `@BeforeEach`:

~~~text
acme
  - alice owns "Alpha draft"  [aliceId]
  - bob owns   "Bob notes"    [bobId]

beta
  - carol owns "Beta plan"    [carolId]

admin-acme -> can administer acme only
admin-beta -> can administer beta only
guest      -> authenticated but has no tenant membership
~~~

Không giả định ID cụ thể bằng 1, 2, 3: identity sequences có thể tiếp tục tăng giữa tests dù table được dọn. Luôn lấy ID thực tế từ `repository.saveAllAndFlush`.

### Ma trận kết quả kỳ vọng

| Principal/request | Đối tượng | Kỳ vọng |
| --- | --- | --- |
| Anonymous GET | Alice doc | 401 |
| Sai password GET | Alice doc | 401 |
| Alice GET | Alice doc | 200 |
| Bob GET | Alice doc trong acme | 404 |
| Alice GET /tenants/beta | Carol doc | 403 |
| Alice GET /tenants/acme | Carol doc ID | 404 |
| admin-acme GET | Bob doc trong acme | 200 |
| admin-beta GET /tenants/acme | Alice doc | 403 |
| guest GET acme | Alice doc | 403 |
| Alice GET list acme | Alice doc only | 200, length 1 |
| admin-acme GET list acme | Alice+Bob only | 200, length 2 |
| Alice POST acme | New doc | 201, owner alice |
| Alice POST protected fields | Fake owner/tenant | 400 |
| Alice POST without CSRF | New doc | 403 |
| Alice PATCH | Alice doc | 200 |
| Bob PATCH | Alice doc | 404 |
| admin-acme PATCH | Bob doc | 200 |
| Alice DELETE | Alice doc | 204 |
| Bob DELETE | Alice doc | 404 |
| admin-beta DELETE acme | Alice doc | 403 |
| admin-acme DELETE acme | Bob doc | 204 |

Bảng tập trung vào **negative cases** vì chúng là bằng chứng quan trọng nhất rằng API không chấp nhận truy cập trái phép. Kiểm lại policy khi mô hình thực có user thuộc nhiều tenants, nhóm (teams), delegated access hoặc sharing.

## 16. TenantDocumentSecurityTest.java — full Spring Boot + MockMvc integration tests

Đây là file JUnit Jupiter hoàn chỉnh. Không mock `TenantDocumentRepository` hoặc `TenantDocumentService`, và không tắt Spring Security filters.

`src/test/java/example/tenant/TenantDocumentSecurityTest.java`:

~~~java
package example.tenant;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantDocumentSecurityTest {

    private static final String ACME =
            "/tenants/acme/documents";
    private static final String BETA =
            "/tenants/beta/documents";

    @Autowired
    MockMvc mvc;

    @Autowired
    TenantDocumentRepository repository;

    private Long aliceId;
    private Long bobId;
    private Long carolId;

    private static SecurityMockMvcRequestPostProcessors
            .HttpBasicRequestPostProcessor login(String username) {
        return httpBasic(username, "test-secret");
    }

    @BeforeEach
    void seedIsolatedDocuments() {
        repository.deleteAllInBatch();

        List<TenantDocument> saved =
                repository.saveAllAndFlush(List.of(
                    new TenantDocument(
                        "acme", "alice", "Alpha draft"),
                    new TenantDocument(
                        "acme", "bob", "Bob notes"),
                    new TenantDocument(
                        "beta", "carol", "Beta plan")
                ));

        aliceId = saved.get(0).getId();
        bobId = saved.get(1).getId();
        carolId = saved.get(2).getId();
    }

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get(ACME + "/" + aliceId)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordCannotAuthenticate() throws Exception {
        mvc.perform(get(ACME + "/" + aliceId)
                    .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get(ACME + "/" + aliceId)
                    .with(login("alice")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                    .value("Alpha draft"))
                .andExpect(jsonPath("$.id")
                    .value(aliceId.intValue()))
                .andExpect(jsonPath("$.tenantId")
                    .doesNotExist())
                .andExpect(jsonPath("$.ownerUsername")
                    .doesNotExist());
    }

    @Test
    void anotherUserSameTenantCannotReadOwnersDocument()
            throws Exception {

        mvc.perform(get(ACME + "/" + aliceId)
                    .with(login("bob")))
                .andExpect(status().isNotFound());
    }

    @Test
    void memberCannotSwitchToDifferentTenantPath()
            throws Exception {

        mvc.perform(get(BETA + "/" + carolId)
                    .with(login("alice")))
                .andExpect(status().isForbidden());
    }

    @Test
    void changingOnlyDocumentIdCannotCrossTenant()
            throws Exception {

        mvc.perform(get(ACME + "/" + carolId)
                    .with(login("alice")))
                .andExpect(status().isNotFound());
    }

    @Test
    void tenantAdminCanReadAnotherOwnerInOwnTenant()
            throws Exception {

        mvc.perform(get(ACME + "/" + bobId)
                    .with(login("admin-acme")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                    .value("Bob notes"));
    }

    @Test
    void tenantAdminCannotUseAdminRoleOutsideMembership()
            throws Exception {

        mvc.perform(get(ACME + "/" + aliceId)
                    .with(login("admin-beta")))
                .andExpect(status().isForbidden());
    }

    @Test
    void loggedInWithoutTenantMembershipIsForbidden()
            throws Exception {

        mvc.perform(get(ACME + "/" + aliceId)
                    .with(login("guest")))
                .andExpect(status().isForbidden());
    }

    @Test
    void userListContainsOnlyOwnedDocuments()
            throws Exception {

        mvc.perform(get(ACME).with(login("alice")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].title")
                    .value("Alpha draft"));
    }

    @Test
    void adminListContainsOnlyItsTenant()
            throws Exception {

        mvc.perform(get(ACME)
                    .with(login("admin-acme")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].title")
                    .value("Alpha draft"))
                .andExpect(jsonPath("$[1].title")
                    .value("Bob notes"));
    }

    @Test
    void forgedTenantHeaderCannotOverrideMembership()
            throws Exception {

        mvc.perform(get(BETA + "/" + carolId)
                    .header("X-Tenant-Id", "beta")
                    .with(login("alice")))
                .andExpect(status().isForbidden());
    }

    @Test
    void forgedUsernameHeaderCannotOverrideOwner()
            throws Exception {

        mvc.perform(get(ACME + "/" + aliceId)
                    .header("X-User", "alice")
                    .with(login("bob")))
                .andExpect(status().isNotFound());
    }

    @Test
    void ownerIsServerAssignedWhenCreatingDocument()
            throws Exception {

        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New plan\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title")
                    .value("New plan"));

        TenantDocument created = repository
            .findByTenantIdAndOwnerUsernameOrderByIdAsc(
                "acme", "alice")
            .stream()
            .filter(doc -> "New plan".equals(doc.getTitle()))
            .findFirst()
            .orElseThrow();

        assertEquals("acme", created.getTenantId());
        assertEquals("alice", created.getOwnerUsername());
        assertEquals(4L, repository.count());
    }

    @Test
    void clientCannotMassAssignTenantOrOwner()
            throws Exception {

        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"title\":\"Injected\","
                        + "\"tenantId\":\"beta\","
                        + "\"ownerUsername\":\"carol\"}"))
                .andExpect(status().isBadRequest());

        assertEquals(3L, repository.count());
    }

    @Test
    void blankTitleFailsValidation() throws Exception {
        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"  \"}"))
                .andExpect(status().isBadRequest());

        assertEquals(3L, repository.count());
    }

    @Test
    void missingCsrfBlocksAuthenticatedPost()
            throws Exception {

        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Without csrf\"}"))
                .andExpect(status().isForbidden());

        assertEquals(3L, repository.count());
    }

    @Test
    void invalidCsrfIsAlsoRejected() throws Exception {
        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .with(csrf().useInvalidToken())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Bad csrf\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanRenameOwnDocument() throws Exception {
        mvc.perform(patch(ACME + "/" + aliceId)
                    .with(login("alice"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Renamed\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                    .value("Renamed"));

        assertEquals(
            "Renamed",
            repository.findById(aliceId)
                    .orElseThrow().getTitle());
    }

    @Test
    void anotherOwnerCannotRenameDocument()
            throws Exception {

        mvc.perform(patch(ACME + "/" + aliceId)
                    .with(login("bob"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Take over\"}"))
                .andExpect(status().isNotFound());

        assertEquals(
            "Alpha draft",
            repository.findById(aliceId)
                    .orElseThrow().getTitle());
    }

    @Test
    void crossTenantUserCannotRenameDocument()
            throws Exception {

        mvc.perform(patch(ACME + "/" + aliceId)
                    .with(login("carol"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Wrong tenant\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void tenantAdminCanRenameSameTenantDocument()
            throws Exception {

        mvc.perform(patch(ACME + "/" + bobId)
                    .with(login("admin-acme"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Reviewed\"}"))
                .andExpect(status().isOk());

        assertEquals(
            "Reviewed",
            repository.findById(bobId)
                    .orElseThrow().getTitle());
    }

    @Test
    void ownerCanDeleteOwnDocument() throws Exception {
        mvc.perform(delete(ACME + "/" + aliceId)
                    .with(login("alice"))
                    .with(csrf()))
                .andExpect(status().isNoContent());

        assertFalse(repository.existsById(aliceId));
    }

    @Test
    void anotherOwnerCannotDeleteDocument()
            throws Exception {

        mvc.perform(delete(ACME + "/" + aliceId)
                    .with(login("bob"))
                    .with(csrf()))
                .andExpect(status().isNotFound());

        assertTrue(repository.existsById(aliceId));
    }

    @Test
    void otherTenantAdminCannotDeleteDocument()
            throws Exception {

        mvc.perform(delete(ACME + "/" + aliceId)
                    .with(login("admin-beta"))
                    .with(csrf()))
                .andExpect(status().isForbidden());

        assertTrue(repository.existsById(aliceId));
    }

    @Test
    void tenantAdminCanDeleteSameTenantDocument()
            throws Exception {

        mvc.perform(delete(ACME + "/" + bobId)
                    .with(login("admin-acme"))
                    .with(csrf()))
                .andExpect(status().isNoContent());

        assertFalse(repository.existsById(bobId));
    }

    @Test
    void unknownIdIsHiddenForValidTenantMember()
            throws Exception {

        mvc.perform(get(ACME + "/999999999")
                    .with(login("alice")))
                .andExpect(status().isNotFound());
    }
}
~~~

### 16.1 Các test có dùng authentication thật không?

Có, trong giới hạn demo. `httpBasic("alice","test-secret")` tạo header HTTP Basic; Spring Security BasicAuthenticationFilter/UserDetailsService/PasswordEncoder được sử dụng, không phải dựng `@WithMockUser` trực tiếp. Sai mật khẩu phải trả `401`. Đầu vào JSON/URL/header phải đi qua Spring Security filters và controller/service.

### 16.2 Có thật sự kiểm database write không?

Có. Test không mock repository/service. Sau các request POST/PATCH/DELETE được cho phép hoặc bị từ chối, test đọc JPA repository thực để kiểm row được tạo/sửa/xóa hoặc **không** bị thay đổi. Đây là cách bắt bug “endpoint báo 403 nhưng đã update DB trước khi kiểm quyền”.

H2 giúp demo đơn giản; những constraints/RLS/SQL dialect của PostgreSQL cần integration tests riêng với PostgreSQL Testcontainers trong dự án sử dụng Postgres.

### 16.3 Vì sao không @Transactional trên test class?

Một test-managed transaction chung quanh MockMvc request có thể che sai lệch commit/rollback của service hoặc làm dữ liệu fixture chỉ sống trong test thread. Bài để controller/service transactions chạy theo application semantics và reset DB ở mỗi `@BeforeEach`. Khi dùng `@SpringBootTest(RANDOM_PORT)`, server chạy thread/transaction khác và **không** được rollback tự động bởi transaction test client.

### 16.4 Vì sao set maxParallelForks=1?

Fixture dùng chung một H2 database trong một application context. Tests chủ động xóa rồi seed rows trước mỗi method; nếu bật JUnit parallel methods, test A có thể xóa rows của B. Bộ demo giữ sequential và một Gradle fork. Nếu phải chạy parallel, dùng unique DB/schema/tenant data per test worker và không reset tables chung bừa bãi.

### 16.5 Mockito/WithMockUser có vị trí nào?

`@WithMockUser(username="alice",authorities={"TENANT_acme","ROLE_USER"})` là công cụ hữu ích cho unit/security policy tests nhưng nó **bypass actual credential verification**. Với test “sai mật khẩu phải 401”, phải dùng actual Basic/login/JWT flow. Đừng chỉ dùng `@WithMockUser` rồi tuyên bố login/password/issuer/JWT filters đã được kiểm.

## 17. Tổng hợp kiểm thử và kết quả kỳ vọng

Trong test class trên có **27 methods `@Test`** chạy theo JUnit Jupiter; tất cả assertions là kỳ vọng theo mã nguồn và policy, **không phải output thực tế đã chạy**.

| Nhóm | Điều được kiểm | Đặc điểm |
| --- | --- | --- |
| Xác thực | Anonymous, sai password | 401 |
| Ownership | Owner GET, Bob GET ID Alice | 200/404 |
| Cross-tenant | Thay tenant path hoặc ID | 403/404 |
| Vertical privilege | Admin cùng tenant vs admin tenant khác | 200/403 |
| Danh sách | Owner-only vs admin tenant-only | Đủ/không rò rows |
| Spoofing | X-Tenant-Id / X-User header | Không đổi principal |
| Tạo tài liệu | POST & assigned owner/tenant | 201 + DB assertions |
| Mass assignment | ownerUsername/tenantId trong JSON | 400 |
| Input validation | Blank title | 400 |
| CSRF | Missing/invalid token | 403 |
| Sửa tài liệu | owner/other owner/tenant/admin | 200/404/403 |
| Xóa tài liệu | owner/other owner/tenant/admin | 204/404/403 |
| Unknown ID | Không tồn tại | 404 |

**Đếm số trường hợp không bằng chất lượng coverage:** phải có negative scenarios thực, assert trạng thái DB sau request bị từ chối và kiểm response không tiết lộ dữ liệu cấm.

## 18. Chạy ứng dụng và chạy test

Chuẩn bị Gradle wrapper được tạo/commit theo toolchain tương thích Boot 3.5. Trên Linux/macOS:

~~~bash
./gradlew clean test
./gradlew test --tests '*TenantDocumentSecurityTest'
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests '*TenantDocumentSecurityTest'
~~~

Test reports:

~~~text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
~~~

Đây là lệnh chạy, không có stdout hoặc benchmark giả. Khi task được đánh dấu UP-TO-DATE, Gradle có thể không chạy lại tests; dùng `--rerun-tasks` khi cần một lượt thực thi mới.

### 18.1 Khi mở app trực tiếp

~~~bash
./gradlew bootRun
~~~

App dùng demo accounts/H2 nên **không triển khai cấu hình này lên Internet**. Dù HTTP Basic trong demo dùng password đã hash bằng BCrypt, HTTP Basic vẫn cần TLS và test credentials chỉ dành môi trường local/CI. Không dùng tài khoản test cho production.

### 18.2 Phân biệt status và nội dung

- `401`: missing/wrong credentials, kèm HTTP Basic challenge nếu áp dụng.
- `403`: authenticated caller không có tenant membership hoặc thiếu CSRF token.
- `404`: object không tồn tại **hoặc** owner check deny trong tenant hợp lệ.
- `400`: DTO invalid/unknown property/malformed JSON.
- `201`: POST hợp lệ tạo mới.
- `200`: GET/PATCH hợp lệ.
- `204`: DELETE thành công không body.

Không suy ra từ status đơn lẻ: test cần cả persisted state và response JSON để phát hiện side effects trước khi deny.

## 19. Kiểm “truy cập chéo” phải hoán đổi nhiều chiều

Một bộ test chỉ kiểm “Carol đọc Alice bị 403” **chưa** đủ. Những hoán đổi cần phân biệt:

1. **Đổi user cùng tenant**: Bob lấy ID Alice dưới acme path (horizontal escalation).
2. **Đổi tenant path**: Alice đi vào `/tenants/beta` (membership boundary).
3. **Giữ tenant path, đổi ID sang record tenant khác**: Alice yêu cầu carolId dưới acme path (object-level tenancy scope).
4. **Đổi role**: admin-acme có thể đọc Bob nhưng admin-beta không được đọc Bob.
5. **Đổi HTTP verb**: GET được chặn chưa bảo đảm PATCH/DELETE được chặn.
6. **Đổi operation**: LIST có thể leak dù GET-by-ID đúng; export/search/count cũng vậy.
7. **Giả mạo header**: `X-Tenant-Id`, `X-User`, `X-Role` do client tự gửi không phải authenticated identity.
8. **Giả mạo body**: `tenantId`/`ownerUsername` trong POST/PATCH không được đổi quyền sở hữu.
9. **Đổi credential**: anonymous/bad password/expired bearer token không được chạm service.
10. **CSRF**: request mutating có credentials nhưng không CSRF token phải bị từ chối theo session/Basic policy.

### 19.1 Không đợi đoán ID

OWASP gợi ý “swap test”: tạo hai accounts/tenants, lấy **ID thực của object** từ fixture hoặc response, gửi cùng request dưới identity khác. Kẻ tấn công không cần biết một thuật toán brute force; ID có thể xuất hiện trong email, list, log, cache, URL hoặc audit trail.

### 19.2 Không quên nested resources

Nếu tài liệu có comments/attachments:

~~~http
GET /tenants/acme/documents/123/attachments/456
~~~

Cần kiểm **cả document 123 và attachment 456** cùng tenant/ownership. Việc user được xem document không tự có nghĩa attachment ID bất kỳ có thể tải xuống. Kiểm lookup có cả tenantId, parentId và resource ID, không chỉ một route-prefix check.

## 20. Quyền tạo, sửa, xóa khác nhau

Một policy có thể cho phép:

- Owner đọc và sửa title.
- Tenant admin đọc/sửa/delete bất kỳ document cùng tenant.
- Viewer chỉ đọc.
- Auditor chỉ xem metadata nhưng không content.
- Global support user cần approval + audited break-glass access.
- Document được share với group nhưng không share cho toàn tenant.

Đừng xây một predicate `isAdmin || isOwner` rồi áp cho mọi verb nếu business requirement có phân quyền khác. Trong demo, nó là **policy được định nghĩa rõ**, thuận tiện cho bài học. Với hệ thống thật, tạo ma trận `principal × tenant × object owner × action × state` rồi viết positive/negative tests cho từng vùng.

### 20.1 “Read-only” không phải tự nhiên an toàn

Endpoint GET có thể lộ dữ liệu qua body, headers, timing, pagination counts hoặc export file. Một endpoint count/list không có tenant scope có thể làm lộ sự tồn tại tài liệu dù GET-by-ID trả 404. Vì thế phải kiểm list/search/aggregate, không chỉ CRUD-by-ID.

### 20.2 Authorization trước mutation

Với PATCH/DELETE, service phải xác minh tenant + ownership **trước khi gọi rename/delete**. Test kiểm row không thay đổi sau denied request. Nếu policy check đặt sau `saveAndFlush`, response 403 vẫn có thể để lại side effects nếu transaction boundaries sai hoặc external event đã publish.

## 21. 401, 403 và 404 trong thế giới JWT/OIDC

Demo dùng HTTP Basic để dễ tái lập authentication thật trong MockMvc. Production resource server thường nhận bearer token:

~~~http
GET /tenants/acme/documents/123
Authorization: Bearer eyJ...
~~~

Không bao giờ parse JWT payload base64 rồi tin `tenantId`/`roles` mà bỏ verification. Trước khi dùng claims:

- Xác minh signature/algorithm và key nguồn tin cậy, không cho algorithm confusion.
- Xác minh `iss`, `aud`, `exp`, `nbf` và token type theo hệ thống.
- Mapping stable subject `sub` sang account ID nội bộ.
- Mapping tenant memberships/roles từ issuer đáng tin hoặc database membership service.
- Xét account bị revoke/tenant membership thay đổi: token cũ còn quyền đến lúc expiry hay cần introspection?
- Không dùng user-supplied `X-Tenant-Id` thay role claim.
- Test token của Alice không thể yêu cầu tenant beta chỉ bằng sửa request path.

`@WithMockUser` không kiểm signature/issuer/audience. Các test JWT chuyên biệt cần `spring-security-test` JWT request post-processors cho authorization mapping **và** ít nhất một authentication/decoder integration test hoặc mocked trusted issuer setup phù hợp security configuration thực.

### 21.1 JWT claim không phải user id trong URL

Nếu endpoint `/users/{userId}/documents` nhận userId từ path, phải kiểm path userId == trusted principal subject (hoặc delegated permission). Việc token hợp lệ và path ID tồn tại chưa chứng minh caller được phép xem dữ liệu user khác.

### 21.2 Multi-tenant identity provider

Trong hệ thống một user thuộc nhiều tenants, quyền có thể phụ thuộc tenant đang chọn. Server phải validate “user thuộc tenant T và có role R trong T”, không chỉ “user có role R ở đâu đó”. Test nên dùng một principal vừa admin ở acme vừa viewer ở beta để bắt role-scope confusion; không cấp global admin do kết hợp authorities đơn giản thiếu tenant binding. Demo mỗi user có một membership để giữ mã dễ đọc, nhưng production policy phải hỗ trợ nhiều memberships chính xác.

## 22. @WebMvcTest và @MockitoBean: dùng khi nào?

`@WebMvcTest(TenantDocumentController.class)` thường chỉ load MVC slice; có thể inject/mock `TenantDocumentService` bằng `@MockitoBean` để kiểm JSON/request validation/HTTP mapping nhanh. Nhưng mock service trả 404/200 tùy stub **không chứng minh service query tenant-scoped**.

Chiến lược hợp lý:

- **Unit tests cho policy**: `DocumentPolicy.canRead` với các Principal/Document combinations, không database.
- **MVC slice**: controller request binding, DTO, status/responses, security filter configuration nếu import đầy đủ.
- **Full MockMvc integration (bài này)**: SecurityFilterChain + UserDetailsService + Service + JPA + H2.
- **PostgreSQL Testcontainers integration**: SQL/RLS/isolation, unique constraints, transaction behavior đúng DB production.
- **Real HTTP deployed environment**: session cookie, reverse proxy, CORS, TLS, API gateway, token issuance/revocation và cross-service propagation.

Đừng dùng `@AutoConfigureMockMvc(addFilters=false)` trong security tests. `@WebMvcTest` có thể không load custom UserDetailsService/SecurityConfig như full context; nếu dùng test slice, phải cấu hình/import đúng filter chain hoặc giới hạn mục tiêu rõ ràng.

## 23. CSRF: kiểm cả có token và không có token

Spring Security Test hỗ trợ:

~~~java
mvc.perform(post("/tenants/acme/documents")
        .with(httpBasic("alice", "test-secret"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Safe\"}"));
~~~

Và negative test:

~~~java
mvc.perform(post("/tenants/acme/documents")
        .with(httpBasic("alice", "test-secret"))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"No CSRF\"}"))
    .andExpect(status().isForbidden());
~~~

Đây là fragments từ test class hoàn chỉnh. `csrf()` chèn token hợp lệ do Spring Security Test setup; `csrf().useInvalidToken()` mô phỏng token sai. Khi CSRF filter reject request, controller/service **không được chạy**, và dữ liệu DB phải giữ nguyên.

Một hệ thống dùng pure bearer Authorization header không bị trình duyệt tự gửi credentials có thể có CSRF strategy khác; cần threat modeling cho cookie, refresh token và browser flows. Không suy luận “REST = luôn tắt CSRF” hoặc “MockMvc = không cần CSRF”.

## 24. Mass assignment và object property-level authorization

Những request nguy hiểm:

~~~json
{
  "title": "My document",
  "ownerUsername": "admin-acme",
  "tenantId": "beta",
  "isSystemDocument": true
}
~~~

Nếu code bind JSON thẳng vào JPA entity và gọi `save`, attacker có thể chiếm ownership hoặc chuyển tài liệu giữa tenants. Các lớp bảo vệ:

1. **Request DTO allowlist**: chỉ có các fields được client sửa, như `title`.
2. **Strict unknown fields** nếu contract cho phép, trả 400 khi client gửi `ownerUsername`.
3. **Server-side assignment**: `tenantId` sau membership verification; `ownerUsername` từ authenticated principal.
4. **Record-level authorization** trước update/delete.
5. **Database tenant scope** trong WHERE clause; nếu có RLS, áp thêm defense in depth.
6. **Audit** ai thay field nào, nhưng không dùng audit thay preventive checks.

Ngay cả khi dùng UUID thay ID số, mass assignment không biến mất. Authorization policy phải áp trên object **và** từng thuộc tính nhạy cảm.

## 25. Cache, search và asynchronous jobs: các nguồn rò tenant ngoài CRUD

Một CRUD-by-ID controller đúng không bảo đảm toàn bộ hệ thống tenant-safe.

### 25.1 Cache keys

Sai:

~~~text
cache key = "document:" + documentId
~~~

Nếu documentId không global-unique qua tất cả stores, hoặc cache phục vụ response có personalization, cache key có thể lẫn tenant/permissions. Một cache key vững hơn có thể gồm `tenantId` + resourceId + policy/version/user scope khi cần; nhưng phải test invalidation và access checks **trước khi trả cached value**.

### 25.2 Search/index/filter

Search endpoint `GET /documents?q=...` có thể query ES/OpenSearch bỏ tenant filter. Test tạo documents cùng title ở hai tenants rồi yêu cầu search dưới Alice, assert không có beta docs trong hits, facets, counts, suggestions hoặc exports.

### 25.3 Exports và background workers

Một export job có thể được tạo trong request acme nhưng chạy async không có `SecurityContext` như request thread. Không copy tenant context từ ThreadLocal thiếu kiểm. Persist job ownership/tenant và validate lại khi job chạy, tải file hoặc nhận callback. Test “request export acme → worker đọc beta data” là negative case đáng có.

### 25.4 Object storage URLs

Một attachment download presigned URL có thể bypass application authorization ở thời điểm tải. Test scope của object key/bucket, TTL, response cache, redirect headers và user/tenant policy trước khi phát URL. Không coi URL khó đoán thay quyền truy cập.

## 26. Data isolation: application checks và PostgreSQL Row Level Security

Demo dùng H2 để kiểm application security policy. Nếu production dùng PostgreSQL shared-table multi-tenancy, có thể áp **Row Level Security (RLS)** làm lớp thứ hai:

~~~sql
ALTER TABLE tenant_documents ENABLE ROW LEVEL SECURITY;
~~~

Đây là SQL minh họa cho PostgreSQL, **không chạy trong H2 demo**. RLS policy thực tế cần thiết kế riêng cho DB role, session identity, tenant setting, `USING`/`WITH CHECK`, database owner bypass/`FORCE ROW LEVEL SECURITY` và superuser privileges. Không viết một RLS policy quá đơn giản rồi tự tuyên bố “đã isolate”.

### 26.1 Những test PostgreSQL/Testcontainers bắt buộc nếu dùng RLS

- DB user thật dùng bởi app không được bypass policy.
- SELECT không trả rows tenant khác ngay cả khi application query quên tenant predicate.
- UPDATE/DELETE không sửa rows tenant khác.
- INSERT/UPDATE `tenant_id` trái policy bị từ chối qua `WITH CHECK`.
- SQL transactions/cgroup không làm đổi tenant context lẫn nhau.
- Connection pool reuse không để session tenant setting cũ chảy sang request sau.
- `SET LOCAL` scope và reset/rollback phù hợp khi dùng session variable.
- Migration/admin DB role không được dùng làm app runtime role.
- Tests chạy trên PostgreSQL thật, không phải H2 compatibility mode.

**Lưu ý:** RLS không thay các service ownership checks nếu policy đòi phân biệt owner/admin trong cùng tenant. Defense in depth ở DB và application phải bổ sung nhau, không che nhau.

## 27. Test isolation: tránh negative test thất bại vì fixture bẩn

Full context tests có database state và security context; phải reset đúng:

- `@BeforeEach` xóa seed data thuộc riêng test suite và tạo đủ acme/beta fixtures.
- Không assert ID tuần tự bắt đầu từ 1.
- Không đặt `@Transactional` bao toàn test nếu muốn verify application commits.
- Không dùng `@DirtiesContext` mỗi method để dọn rows; cleanup đúng tầng DB.
- Không chạy JUnit methods song song cùng `deleteAllInBatch()`, vì sẽ xóa fixtures của nhau.
- Không dùng static mutable authentication giữa tests; mỗi MockMvc request có credentials riêng.
- Không mock service hay repository trong integration test chính.
- Kiểm response và persisted state sau denied write.
- Nếu test có asynchronous events/background jobs, chờ completion và cleanup riêng.
- Không để production data/accounts/keys lọt vào test fixtures/CI logs.

### 27.1 Vì sao không đặt @WithMockUser trên toàn class?

Một class-level `@WithMockUser` có thể làm “anonymous request” thực tế vẫn có security principal và test 401 sai. Dùng `httpBasic` cụ thể cho từng request trong test demo để các trạng thái anonymous, sai password, đúng password phân biệt rõ ràng.

### 27.2 Không cho tests chạy mà tắt filter

`@AutoConfigureMockMvc(addFilters=false)` làm test controller nhanh hơn, nhưng không còn SecurityFilterChain, CSRF, AuthenticationEntryPoint hoặc AccessDeniedHandler. Với bài kiểm xác thực/quyền, filter phải được áp dụng và test negative flows.

## 28. Xác thực mức app vs bảo mật trên reverse proxy

MockMvc chạy Servlet filter chain **trong JVM**, không mở real HTTP port. Nó có thể chứng minh những hành vi Spring Security và application routing, nhưng chưa tự kiểm:

- HTTPS/TLS termination thực tế.
- Proxy gửi headers `X-Forwarded-*`.
- API gateway JWT signature/issuer forwarding.
- Session cookies, SameSite, Secure, HttpOnly trong browser.
- Rate limiting, MFA, account lockout, password reset.
- Network egress và service-to-service authorization.
- Cross-origin preflight/CORS cấu hình thực trên edge.
- OAuth2 authorization code/PKCE hoặc token exchange thật.

Cần các integration/E2E tests phù hợp, không ghi “security fully tested” chỉ từ MockMvc unit.

### 28.1 Cảnh giác forwarded identity headers

Nếu hệ thống dùng reverse proxy đưa `X-Authenticated-User` hoặc `X-Tenant-Id`, phải bảo đảm gateway **xóa** headers do client cung cấp rồi tạo lại trên trusted channel (mTLS/network allowlist). App phải kiểm trust boundary. Demo cố tình không tin `X-User` và `X-Tenant-Id` để minh họa nguyên tắc.

## 29. CI workflow: security tests là mandatory gate

File `.github/workflows/security-tests.yml`:

~~~yaml
name: Tenant authorization integration tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  security-tests:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Run full security suite
        shell: bash
        run: |
          chmod +x ./gradlew
          ./gradlew --no-daemon clean test --stacktrace

      - name: Upload JUnit reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: tenant-security-junit-results
          path: |
            build/test-results/test/
            build/reports/tests/test/
          if-no-files-found: error
          retention-days: 7
~~~

Bài dùng H2 nên workflow không cần Docker; giữ suite nhanh để chạy trên mọi pull request. Với production database-specific RLS tests, tạo job **khác** có PostgreSQL Testcontainers và Docker-enabled runner, đồng thời cấu hình cả hai jobs là required checks khi merge/deploy.

### 29.1 Không bỏ negative tests để build xanh

Nếu một test bị fail do cross-tenant authorization bug, sửa policy/query và thêm regression test; đừng `@Disabled` hoặc xóa assertions để vượt qua CI. Security regression có thể là lỗi nghiêm trọng hơn chức năng thông thường.

### 29.2 Báo cáo test đã thực thi

JUnit XML/HTML cần thể hiện discovered/executed/skipped/failures. Nếu Gradle test task có includeTag filter vô tình bỏ toàn security suite, `BUILD SUCCESSFUL` không chứng minh authorization đã được kiểm. CI có thể có guard tối thiểu test count hoặc package-based test selection để tránh accidental omission.

## 30. Làm thế nào mô phỏng JWT trong Spring Security Test?

Với resource server production, Spring Security Test hỗ trợ request post-processors như `jwt()` để đặt một authenticated token/authorities vào test context. Nó hữu ích kiểm **authorization mapping**:

~~~java
mvc.perform(get("/tenants/acme/documents/123")
        .with(jwt().jwt(jwt ->
            jwt.claim("tenant_id", "acme"))
            .authorities(
                new SimpleGrantedAuthority("TENANT_acme"))));
~~~

Đây là **snippet riêng**, không thuộc source demo và cần imports/config JWT đúng. `jwt()` không chứng minh signature hoặc issuer validation; nó mô phỏng authenticated JWT. Cần test riêng với JwtDecoder/HTTP bearer filter để kiểm invalid signature, wrong issuer/audience, expired token và absence of token. Không sao chép principal name từ Basic test sang JWT test mà quên `sub`/name mapping.

### 30.1 Role mapping cho JWT không nhất thiết giống Basic

JWT claims có thể là `roles`, `scope`, `realm_access.roles` hoặc tenant-specific map. Một `JwtAuthenticationConverter` có thể thêm prefix `SCOPE_`/`ROLE_`; test phải xác minh authorities thực tế khớp policy service. Đừng dùng `ROLE_ADMIN` toàn hệ thống nếu token role chỉ dành cho một tenant.

## 31. Nâng cấp ma trận cho mô hình multi-tenant phức tạp

Ở môi trường production, bổ sung:

- Một user thuộc **hai tenants** với roles khác nhau (admin acme, viewer beta).
- Người dùng bị revoke membership khi token vẫn chưa hết hạn.
- Quyền share document tạm thời giữa hai users/tenants.
- Quản trị viên tenant bị khóa tài khoản giữa request.
- Đổi document ownership (transfer) có cần approval/authorization riêng?
- Soft-delete, archived, published/private states.
- Nested comments/attachments và object store keys.
- Search, pagination, sorting, report export, aggregation counts.
- Bulk update/delete theo danh sách IDs chứa cả acme/beta records.
- GraphQL data loaders / batch reads không tự scope tenant.
- WebSocket/SSE subscriptions và reconnect across tenant switch.
- Async jobs, email notifications, event streaming/outbox payloads.
- Cache serialization/invalidation khi switching identity/tenant.
- Database RLS policies cùng pooled connections.
- Error responses không leak thông tin nội bộ, stack traces, SQL.
- Security audit: denied event có user/tenant/request correlation nhưng không log password/token.
- Rate limiting để giảm ID enumeration attack attempts.

### 31.1 Bulk operations đặc biệt dễ sai

Nếu API nhận `ids=[10,11,12]`, không được gọi `deleteAllById(ids)` mà chưa lọc tenant và owner của **từng record**. Test tạo mảng ID trộn acme/beta rồi xác nhận không record trái quyền nào bị đổi, kể cả khi API trả partial success. Xác định policy là all-or-nothing hoặc per-item result, và test transaction correctness.

### 31.2 Search facets/metadata cũng có thể rò

Danh sách chỉ hiển thị acme docs nhưng `totalCount` trả count toàn DB, hoặc facet `ownerNames` trả carol thuộc beta, vẫn là tenant information leak. Bộ test phải kiểm cả metadata của paging/search/export, không chỉ list items.

## 32. Chẩn đoán test fail theo tầng

| Dấu hiệu | Tầng thường gặp | Kiểm tra |
| --- | --- | --- |
| Anonymous GET trả 200 | HTTP security | Filter chain có thật? anyRequest authenticated? |
| Wrong password trả 200 | Authentication | Có đang @WithMockUser bypass? UserDetailsService nào? |
| Alice GET own trả 403 | Tenant membership | Authority name/prefix hay path mismatch |
| Bob GET Alice trả 200 | Object authorization | Có bỏ owner check? `findById` không scope? |
| Carol GET acme trả 200 | Tenant isolation | Có tin client tenant? |
| admin-beta đọc acme | Role scoping | Có dùng global ROLE_ADMIN sai? |
| GET list chứa beta | Repository queries | WHERE tenant_id missing |
| POST gán owner từ body | Mass assignment | DTO/entity binding/identity assignment |
| PATCH denied nhưng DB đổi | Ordering/transaction | Mutation xảy ra trước authorization |
| Missing CSRF vẫn POST thành công | Security filter | CSRF disabled/addFilters=false? |
| POST có CSRF vẫn 403 | CSRF setup | Token, request session/handler |
| Valid request nhận 400 | JSON/validation | DTO field, strict unknown, contentType |
| GET document không tồn tại trả 500 | Error mapping | Có ResponseStatusException 404? |
| SQL fixtures dẫm nhau | Parallelism | Shared H2 reset trong @BeforeEach |
| MockMvc tests PASS nhưng real API leak | Layer gap | Gateway/JWT/cache/RLS/E2E |
| JUnit XML không thấy security tests | Discovery/filter | Gradle tags, class naming, task config |

### 32.1 Test 401 mà vẫn có @WithMockUser

Nếu test class/method được annotate `@WithMockUser`, request thiếu Basic header có thể **vẫn được coi là authenticated**. Để kiểm authentication filter, dùng request credentials thật như `httpBasic`, không chỉ injected SecurityContext test principal.

### 32.2 403 từ CSRF không chứng minh tenant authorization

Một PATCH không có CSRF token bị chặn sớm ở CSRF filter. Test “Bob bị 403” trong trường hợp này chưa từng đi tới owner policy. **Negative ownership tests phải cung cấp CSRF hợp lệ** rồi assert expected 404/403 ở đúng lớp. Đây là một lỗi test design phổ biến.

### 32.3 Response 404 có thể đến từ sai URL

Nếu controller mapping hoặc ID fixture sai, một test mong 404 có thể PASS nhưng không chứng minh owner check. Để tránh false positives, có positive control: cùng object ID phải trả 200 dưới Alice, rồi 404 dưới Bob. Bộ sample thực hiện cả hai.

## 33. Quy trình áp dụng vào dự án thật

1. Xác định principal identity source, authentication mechanism và tenant membership store.
2. Viết policy matrix theo actor, tenant, owner, role, object state và operation.
3. Tạo ít nhất hai users cùng tenant, một user tenant khác và admin mỗi tenant.
4. Tạo fixtures có ID thực và các tên/field có thể phát hiện leak.
5. Đảm bảo authorization nằm ở service/data boundary, không chỉ URL role.
6. Bắt buộc database query có tenant scope; cân nhắc RLS với PostgreSQL.
7. Mọi POST/PATCH DTO chỉ chứa editable fields, protected fields do server assign.
8. Bật Spring Security filters trong MockMvc và kiểm actual authentication.
9. Kiểm anonymous/wrong credentials 401 và positive authenticated case.
10. Hoán đổi owner trong cùng tenant để bắt BOLA.
11. Hoán đổi tenant path **và** object ID để bắt cross-tenant access.
12. Kiểm tenant admin không được coi là global admin.
13. Kiểm LIST/SEARCH/COUNT/EXPORT không có tenant leaks.
14. Kiểm POST/PATCH/DELETE với CSRF đúng; thêm CSRF-negative tests.
15. Sau denied writes, xác nhận DB state không thay đổi.
16. Kiểm spoofed identity headers/body/mass assignment.
17. Tránh test-managed @Transactional che real service commits.
18. Không chạy parallel nếu fixture reset table chung.
19. Khi dùng JWT, test decoder verification riêng và authorization claim mapping.
20. Nếu PostgreSQL RLS được dùng, bổ sung Testcontainers tests với app DB role thật.
21. Lưu test reports và bảo đảm security suite không bị CI filters skip.
22. Review error semantics 403/404 để tránh user enumeration.
23. Đo audit log có nội dung hữu ích nhưng không lộ password/token.
24. Chạy lại cross-tenant matrix cho mọi object type mới, không chỉ documents.

### Checklist QA cuối

- [ ] Unauthenticated hoặc wrong credentials không đọc được dữ liệu.
- [ ] HTTP Security FilterChain chạy thật trong MockMvc.
- [ ] CSRF token được cung cấp cho owner/tenant authorization tests của unsafe methods.
- [ ] User cùng tenant nhưng không phải owner không được đọc/sửa/xóa.
- [ ] User khác tenant không được chuyển tenant bằng URL/header.
- [ ] Admin role luôn được ràng với đúng tenant membership.
- [ ] GET-by-ID **và** LIST/SEARCH/BULK endpoints có tenant scope.
- [ ] Positive control cùng ID trả 200 cho owner, negative control trả 404 cho stranger.
- [ ] Không dùng client-supplied owner/tenant làm nguồn sự thật.
- [ ] Request DTO không cho mass-assignment fields nhạy cảm.
- [ ] Denied PATCH/DELETE không làm đổi database.
- [ ] Response không serialize protected fields không cần thiết.
- [ ] H2 demo không bị hiểu nhầm là kiểm PostgreSQL RLS/dialect.
- [ ] Tests có ít nhất hai users cùng tenant và một tenant khác.
- [ ] Fixture IDs lấy từ repository, không hardcode số thứ tự.
- [ ] Không có transaction/parallelism che behavior hoặc làm rò fixtures.
- [ ] JWT signature/issuer/audience checks được kiểm ở layer thích hợp.
- [ ] Cache, search, exports, nested resources và async được đánh giá.
- [ ] CI bắt buộc chạy security integration suite và lưu JUnit reports.
- [ ] Security logs không lộ credentials hoặc tenant data nhạy cảm.

## 34. Kết luận

**Xác thực là điều kiện cần; quyền sở hữu và tenant isolation mới bảo vệ từng bản ghi.** Một Spring Boot API phải biết người gọi đã được nhận diện như thế nào, người đó thuộc tenant nào, có role gì trong đúng tenant ấy và có quyền trên object cụ thể hay không.

Bộ demo dùng HTTP Basic và BCrypt test users để kiểm authentication qua Spring Security filters, MockMvc để thực hiện requests thật trong JVM, JPA repository/H2 để kiểm side effects, và các negative cases cho BOLA, cross-tenant leaks, administrator scope, mass assignment, CSRF, list isolation và unauthorized writes. Chính sách trả 401/403/404 được nêu rõ và kiểm nhất quán.

Khi áp dụng production, đừng chỉ chuyển sang JWT rồi coi đã an toàn. Cần verified identity/claims, service-level authorization, tenant-scoped queries, DTO allowlists, optional database RLS, policy cho search/cache/async và CI regression tests trên những loại resource thực sự dùng. **Mỗi endpoint nhận object ID cần một object-level authorization check**, không phải chỉ một role check cho URL.

### Tài liệu tham khảo chính thức

- [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): object ID swapping và authorization per resource.
- [OWASP REST Assessment — BOLA testing](https://cheatsheetseries.owasp.org/cheatsheets/REST_Assessment_Cheat_Sheet.html): swap tests cho GET/PUT/PATCH/DELETE.
- [OWASP IDOR Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): IDs không thay access checks.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, object checks.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): authorizeHttpRequests, authenticated, AccessDeniedException.
- [Spring Security 6.5 — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html): httpBasic() request processor.
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): valid/invalid csrf().
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): Spring Security filters in MockMvc.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, @AutoConfigureMockMvc and SpringExtension.
- [Spring Boot 3.5 — Spring Security](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): SecurityFilterChain and UserDetailsService auto-config.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): Jackson deserialization settings.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT issuer/signature validation.
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS scope/roles.
- [Gradle — Testing Java Projects](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform, reporting and test filters.
