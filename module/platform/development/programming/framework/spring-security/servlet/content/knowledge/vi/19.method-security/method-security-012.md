# Kiểm thử chính sách ở tầng dịch vụ độc lập với HTTP

> **Ngữ cảnh:** Spring Security 6 trên **Servlet stack**, Java 17+ và Spring Boot 3.x. Chủ đề thuộc **Bảo vệ phương thức (Method Security)**. Trọng tâm là kiểm thử quyết định cấp quyền của service **mà không gửi HTTP request**, không phụ thuộc URL, filter chain, MVC, cookie, CSRF hay MockMvc. Bài phân biệt **unit test của policy thuần** với **integration test gọi Spring-managed service qua method-security proxy**, cách dùng `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `SecurityContextHolder`; kiểm tra `@PreAuthorize` và `@PostAuthorize`, exception, negative cases, việc không cho phép self-invocation bypass và trạng thái tài nguyên sau một operation bị từ chối. Bao gồm project Gradle/Java đầy đủ và các bài tập kiểm thử.

## 1. Vì sao cần test phân quyền mà không có HTTP?

Một controller có thể gọi service:

```text
GET /api/documents/102
       |
       v
SecurityFilterChain  -- HTTP authentication / coarse authorization
       |
       v
DocumentController.get(102)
       |
       v
DocumentService.read(102)
       |
       v
DocumentPolicy.canRead(authentication, 102)
```

Nếu chỉ test HTTP `GET /api/documents/102`, kết quả **403** có thể đến từ nhiều nguyên nhân: người dùng không đủ quyền, CSRF (với unsafe method), thiếu session/credentials, filter chain sai, matcher sai, endpoint không tồn tại hoặc method interceptor thực sự từ chối. Một bài kiểm thử HTTP thuần có thể không phân biệt được nguyên nhân.

Khi gọi **trực tiếp Spring bean `DocumentService`** trong test (không gửi request HTTP), ta đặt `Authentication` đã biết vào test security context và tập trung kiểm chứng:

1. Quy tắc `@PreAuthorize` có chạy trước service method không?
2. Những thuộc tính user, resource, role, tenant và trạng thái có thực sự được xét đúng?
3. Trường hợp bị từ chối có ném `AccessDeniedException` không?
4. **Service body không được thực thi** khi pre-authorization thất bại?
5. Một `@PostAuthorize` có kiểm tra object trả về đúng không?
6. Spring-managed service có bị gọi qua **AOP proxy** hay test đang tự `new` một object không có interceptor?
7. Kết quả test có độc lập với Servlet filters, session và controller không?

**Kết luận:** service authorization cần được test như **hợp đồng nghiệp vụ**, không chỉ như một chi tiết của HTTP endpoint. Tuy nhiên test service không thay thế end-to-end test cho filter chain, login, request matcher và CSRF.

## 2. Bốn mức kiểm thử liên quan đến bảo mật

| Mức | Đối tượng được test | Có Spring context? | Có HTTP? | Nó chứng minh gì? |
| --- | --- | --- | --- | --- |
| **Policy unit test** | `DocumentPolicy.canRead/canApprove` thuần | Không bắt buộc | Không | Điều kiện nghiệp vụ trên input subject/resource/action được tính đúng |
| **Method-security integration test** | `@PreAuthorize`/`@PostAuthorize` trên Spring-managed service | Có (đủ method-security config) | **Không** | Method interceptor thực thi chính sách khi service được gọi qua proxy |
| **Web security integration test** | SecurityFilterChain, controller, filter, session và endpoint | Có | Có thể dùng MockMvc | Rule HTTP + method security phối hợp đúng |
| **End-to-end test** | Browser/client thật, proxy, IdP/DB và network | Hệ thống triển khai | Có | Hành vi xuyên các lớp và hạ tầng thực tế |

Không nên chỉ có một mức. Policy unit test rất nhanh và cho phép thử nhiều tổ hợp; method-security integration test chứng minh **wiring**, proxy và SpEL; HTTP/E2E test bắt các lỗ hổng do filter chain, request matcher, JSON binding hoặc token/cookie.

### Những điều KHÔNG được suy ra

- `@WithMockUser` không chứng minh mật khẩu đã được kiểm tra bởi `AuthenticationProvider`.
- Một method security test PASS không chứng minh `/admin/**` bị chặn đúng ở tầng HTTP.
- `@PreAuthorize` chạy khi gọi qua Spring proxy không chứng minh mọi lời gọi nội bộ qua `this` cũng bị chặn.
- Test policy bean trả `false` không chứng minh service có gắn annotation method-security.
- Test MockMvc bị 403 do CSRF không chứng minh role hay policy resource đang đúng.

## 3. Luồng thực thi của @PreAuthorize khi gọi trực tiếp service

Khi bật `@EnableMethodSecurity`, Spring Security tạo các method interceptors/advisors thích hợp. Với proxy-based method security, lời gọi từ bean khác đến một service được Spring quản lý đi qua proxy trước khi chạy body.

```text
JUnit test method
   |
   +--> @WithMockUser tạo Authentication cho SecurityContext
   |
   v
Spring-managed DocumentService bean (AOP proxy)
   |
   v
AuthorizationManagerBeforeMethodInterceptor
   |
   +--> evaluate @PreAuthorize SpEL
   |        |
   |        +--> @documentPolicy.canRead(authentication, #id)
   |
   +--> ALLOW -> invoke DocumentService.read(...)
   |
   +--> DENY  -> AccessDeniedException
                    |
                    +--> service body KHÔNG được gọi
```

Đây là mô hình khái niệm cho default proxy-based method security. Các tên lớp/đường gọi cụ thể có thể thay đổi theo Spring Security version và annotations được bật. Điều quan trọng là kiểm tra **cơ chế proxy thực sự tồn tại** và **kết quả authorization** chứ không phụ thuộc vào Servlet request.

### Tầng HTTP và tầng service khác nhau

Một ứng dụng Servlet thường dùng:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
```

Đây là fragment trong `SecurityFilterChain`, ràng buộc HTTP. Nó chưa biết user có phải owner của document id cụ thể không. Trong domain service ta có:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public Document read(long id) {
    return repository.require(id);
}
```

Rule service sẽ chạy dù method được gọi từ REST controller, một Spring bean khác hoặc test trực tiếp **qua proxy**. Nhờ đó, một phần policy không bị phụ thuộc vào cách HTTP route được tổ chức.

## 4. SecurityContextHolder trong test không dùng HTTP

`SecurityContextHolder` chứa `SecurityContext` và `Authentication` đang được sử dụng theo strategy hiện hành của Spring Security. Đối với một unit/integration test không có request HTTP, nó vẫn có thể mang principal/authorities cho method-security interceptor.

Các tùy chọn tạo context:

- **`@WithMockUser`:** tạo test `Authentication` theo username/roles/authorities được khai báo.
- **`@WithAnonymousUser`:** mô phỏng anonymous authentication do Spring Security Test tạo.
- **`@WithUserDetails`:** tải `UserDetails` từ bean `UserDetailsService` trong Spring context; phù hợp khi muốn kiểm tra ánh xạ roles từ user store thử nghiệm.
- **`@WithSecurityContext`:** tự xây security context theo một test annotation tùy chỉnh (ví dụ custom principal, token claims, tenant context), nếu bài toán cần.
- **Tạo context thủ công:** thuận tiện cho unit test dùng `Authentication` fake hoặc service không khởi tạo Spring context; cần dọn context sau mỗi test.

**Điểm quan trọng:** bất kỳ test nào cũng phải có cơ chế dọn context; principal của test A không được rò sang test B.

### 4.1. @WithMockUser

```java
@Test
@WithMockUser(username = "alice", roles = {"READER"})
void example() {
    // MethodSecurity interceptor nhìn thấy tên "alice"
    // và authority "ROLE_READER".
}
```

`roles = {"READER"}` được Spring Security Test chuyển thành authority `ROLE_READER`. Khi dùng `authorities={"DOCUMENT_READ"}`, giá trị authority được giữ chính xác, không tự thêm `ROLE_`.

`@WithMockUser` **không gửi username/password tới web authentication filter** và không xác thực password bằng BCrypt. Nó chủ động tạo principal test, dùng cho kiểm tra authorization logic.

### 4.2. @WithAnonymousUser

```java
@Test
@WithAnonymousUser
void anonymousMustBeDenied() {
    assertThrows(AccessDeniedException.class,
            () -> documentService.read(101L));
}
```

`@WithAnonymousUser` đặt một anonymous authentication trong context test. Điều này khác với **SecurityContext hoàn toàn không có Authentication**: tùy interceptor/expression, tình huống không có authentication có thể dẫn đến `AuthenticationCredentialsNotFoundException` hoặc exception khác. Muốn test anonymous một cách có chủ đích, dùng annotation này thay vì ngầm đoán context trống sẽ giống HTTP anonymous.

### 4.3. @WithUserDetails

```java
@Test
@WithUserDetails("bob")
void permissionsFromUserDetailsService() {
    // Test execution listener tải UserDetails "bob"
    // và tạo Authentication dựa trên user này.
}
```

Cần bean `UserDetailsService` chứa username tương ứng. Nó kiểm tra cấu hình **test user lookup và các authorities từ bean ấy**, nhưng vẫn không gửi password/HTTP login thật.

### 4.4. SecurityContext thủ công trong unit test

```java
Authentication subject = new UsernamePasswordAuthenticationToken(
        "alice",
        "unused-in-test",
        List.of(new SimpleGrantedAuthority("ROLE_READER")));
```

Constructor có authorities tạo authenticated token dùng được cho unit test policy. Nó không có nghĩa mật khẩu thực đã được xác minh; subject được tạo có chủ đích để kiểm tra quyết định. Không copy mô hình giả lập này làm production login endpoint.

## 5. Hai loại quyết định: @PreAuthorize và @PostAuthorize

### 5.1. @PreAuthorize kiểm tra trước khi chạy method body

```java
@PreAuthorize("hasRole('EDITOR') and @documentPolicy.canEdit(authentication, #id)")
public String edit(long id, String content) {
    return repository.updateContent(id, content);
}
```

Nếu user thiếu role hoặc policy trả false, method body **không được gọi**. Đây là lựa chọn ưu tiên cho thao tác có side effects như update, approve, delete, transfer money hay gửi email.

**Test đúng:** không chỉ assert exception, còn assert repository **không bị thay đổi** sau lời gọi bị từ chối.

### 5.2. @PostAuthorize kiểm tra object trả về

```java
@PostAuthorize("@documentPolicy.canRead(authentication, returnObject.id())")
public Document inspect(long id) {
    return repository.require(id);
}
```

Spring Security kiểm tra biểu thức `@PostAuthorize` **sau khi method trả đối tượng** và trước khi caller nhận kết quả thành công. Với resource read-only, pattern này có thể hữu ích để kiểm tra thuộc tính của object đã được load. Tuy nhiên service body đã chạy, nên **không dùng @PostAuthorize như lớp bảo vệ duy nhất cho operation thay đổi state**. Với object có thể null, cần xử lý null trong expression/service; ví dụ dùng repository `require(id)` ném exception khi document không tồn tại.

### 5.3. @PreFilter và @PostFilter không thay @PreAuthorize

`@PreFilter` lọc các phần tử input collection; `@PostFilter` lọc collection output theo policy. Chúng không đương nhiên tương đương với việc cấm operation gây side effect trên từng object. Khi dùng filtering, cần test kết quả collection và kiểm soát dữ liệu đã được load/processed trước filtering.

### 5.4. hasRole, hasAuthority và prefix ROLE_

`hasRole('MANAGER')` thường kiểm tra authority `ROLE_MANAGER`. `@WithMockUser(roles="MANAGER")` tạo đúng authority này. `hasAuthority('DOC_APPROVE')` kiểm tra authority `DOC_APPROVE` nguyên văn; nếu test chỉ cấp `ROLE_MANAGER` thì không tự match.

**Không trộn role names với authority strings** rồi cho rằng có prefix tự thêm ở tất cả API.

## 6. Thiết kế test để bắt lỗi policy thật

Nếu policy cần role `MANAGER`, tenant trùng, document `PENDING` và người phê duyệt không phải owner, một test “wrong tenant, wrong role, wrong owner” cùng lúc **không chứng minh từng điều kiện đều được kiểm tra**. Nó chỉ chứng minh tổng thể bị từ chối.

Nên có **một test cho mỗi điều kiện**, trong đó các điều kiện còn lại được đặt hợp lệ:

| Yếu tố muốn kiểm tra | Các yếu tố khác | Kỳ vọng |
| --- | --- | --- |
| Thiếu role MANAGER | Tenant đúng, non-owner, PENDING, clearance đủ | DENY |
| Sai tenant | Có MANAGER, non-owner, PENDING, clearance đủ | DENY |
| Không đủ clearance | Có MANAGER, tenant đúng, non-owner, PENDING | DENY |
| Owner tự phê duyệt | Có MANAGER, tenant đúng, PENDING, clearance đủ | DENY |
| Document đã APPROVED | Có MANAGER, tenant đúng, non-owner, clearance đủ | DENY |
| Đủ điều kiện | Tất cả thuộc tính đều hợp lệ | ALLOW |
| Anonymous | Resource hợp lệ | DENY |
| Profile không có trong directory | Role giả lập vẫn đầy đủ | DENY |
| Resource ID không tồn tại | User hợp lệ | DENY |
| User chỉ được read | Không có quyền edit | DENY, dữ liệu giữ nguyên |

Với `@PostAuthorize`, cần cả test cho object được phép trả về và object bị deny sau khi load. Với object bị deny, không được để caller nhận nội dung trái quyền.

## 7. Dự án Java 17 / Spring Boot 3: service authorization không mở HTTP server

Dự án dưới đây dùng Spring Boot **3.3.5**, Spring Security **6.x** do Boot quản lý, Gradle **8.5**, JUnit 5 và `spring-security-test`. Module có Spring MVC dependency để giống ứng dụng Servlet thực tế, nhưng bài test chủ động dùng `@SpringBootTest(webEnvironment = NONE)`. **Không có controller, không gọi MockMvc, không tạo HTTP request.**

Bối cảnh: nhân viên đọc/chỉnh sửa/phê duyệt tài liệu ở hai tenant `north` và `south`. Mọi metadata tài liệu và user profile lấy từ repository/directory phía server, không phải header giả định do client gửi.

### 7.1. Quy tắc nghiệp vụ

**Đọc `read(id)`:**
- subject là người đã xác thực, không phải anonymous;
- có user profile server-side;
- tenant user = tenant tài liệu;
- clearance user ≥ mức phân loại tài liệu;
- tài liệu không ở trạng thái `ARCHIVED`.

**Chỉnh sửa `edit(id, content)`:**
- có `ROLE_EDITOR`;
- thỏa policy đọc;
- là owner;
- document còn ở `DRAFT`.

**Phê duyệt `approve(id)`:**
- có `ROLE_MANAGER`;
- thỏa policy đọc;
- document ở `PENDING`;
- người phê duyệt **khác owner** (*separation of duties*).

**Xem bằng `inspect(id)`:** method read-only trả resource sau đó kiểm tra `@PostAuthorize`; dùng để so sánh với pre-authorization.

### 7.2. User và tài liệu thử nghiệm

| User | Tenant | Clearance | Roles |
| --- | --- | --- | --- |
| `alice` | north | 1 | READER |
| `bob` | north | 3 | READER, EDITOR |
| `maria` | north | 3 | READER, MANAGER |
| `carol` | south | 2 | READER, MANAGER |

| Doc | Tenant | Owner | Min clearance | Status | Content mẫu |
| --- | --- | --- | --- | --- | --- |
| 101 | north | alice | 1 | DRAFT | north-public |
| 102 | north | bob | 2 | PENDING | north-approval |
| 103 | south | carol | 1 | PENDING | south-draft |
| 104 | north | maria | 2 | PENDING | manager-owned |
| 105 | north | alice | 1 | ARCHIVED | archived |
| 106 | north | bob | 2 | DRAFT | editable |

Các data fixtures này được tạo lại trước mỗi method-security test. Không có cơ sở dữ liệu thật; `ConcurrentHashMap` minh họa state và cho phép kiểm tra nội dung **không đổi** sau một operation bị deny.

### 7.3. Cây thư mục

```text
method-security-service-tests/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    UserProfileDirectory.java
    DocumentRepository.java
    DocumentPolicy.java
    DocumentService.java
  src/test/java/demo/
    DocumentPolicyUnitTest.java
    DocumentServiceSecurityTest.java
```

### 7.4. settings.gradle

```groovy
rootProject.name = 'method-security-service-tests'
```

### 7.5. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Tại sao cần `-parameters`?** Spring method-security SpEL thường tham chiếu `#id`. Khi Java compiler lưu tên parameter, method-security expression resolver có thể nhận biết `id` đúng tên. Một số môi trường cũng đọc metadata qua annotation; với demo dùng `-parameters` tường minh để tránh lỗi không tìm được argument name.

**Tại sao có `spring-boot-starter-web` nếu không test HTTP?** Nó cho thấy service và security config có thể nằm trong ứng dụng Servlet thực tế. Test dùng `WebEnvironment.NONE` nên không khởi tạo HTTP server; HTTP headers/cookies/MVC không tham gia quyết định. Nếu ứng dụng chỉ là worker/service không có web, có thể bỏ starter-web mà vẫn kiểm thử method security.

### 7.6. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 7.7. SecurityConfig.java: bật Method Security

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("study123"))
                .roles("READER")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("study123"))
                .roles("READER", "EDITOR")
                .build();
        UserDetails maria = User.withUsername("maria")
                .password(encoder.encode("study123"))
                .roles("READER", "MANAGER")
                .build();
        UserDetails carol = User.withUsername("carol")
                .password(encoder.encode("study123"))
                .roles("READER", "MANAGER")
                .build();
        return new InMemoryUserDetailsManager(alice, bob, maria, carol);
    }
}
```

`@EnableMethodSecurity` đăng ký infrastructure cho `@PreAuthorize` và `@PostAuthorize` theo defaults. Không cần gửi request Servlet để AOP interceptor chạy; nó hoạt động trên service bean được Spring quản lý.

Mật khẩu và users local chỉ dành cho học tập. Trong `@WithMockUser`, test không dùng password này. Trong `@WithUserDetails`, Spring Security Test tải user details từ bean nhưng vẫn không thực hiện password-based authentication.

### 7.8. UserProfileDirectory.java: subject attributes đáng tin

`src/main/java/demo/UserProfileDirectory.java`:

```java
package demo;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class UserProfileDirectory {

    private final Map<String, UserProfile> profiles = Map.of(
            "alice", new UserProfile("north", 1),
            "bob", new UserProfile("north", 3),
            "maria", new UserProfile("north", 3),
            "carol", new UserProfile("south", 2));

    public UserProfile find(String username) {
        return profiles.get(username);
    }
}

record UserProfile(String tenant, int clearance) {}
```

Tên user phải xuất phát từ `Authentication` mà method security đang xử lý; quyền tenant và clearance từ directory server-side. Nếu test cố giả lập principal `ghost` có roles đầy đủ nhưng directory không chứa profile, policy phải **fail closed**, không cấp quyền vì role mock cao.

### 7.9. DocumentRepository.java: dữ liệu tài nguyên kiểm soát tại server

`src/main/java/demo/DocumentRepository.java`:

```java
package demo;

import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class DocumentRepository {

    private final ConcurrentMap<Long, Document> documents =
            new ConcurrentHashMap<>();

    public DocumentRepository() {
        reset();
    }

    public void reset() {
        documents.clear();
        documents.put(101L, new Document(101L, "north", "alice",
                1, DocumentStatus.DRAFT, "north-public"));
        documents.put(102L, new Document(102L, "north", "bob",
                2, DocumentStatus.PENDING, "north-approval"));
        documents.put(103L, new Document(103L, "south", "carol",
                1, DocumentStatus.PENDING, "south-draft"));
        documents.put(104L, new Document(104L, "north", "maria",
                2, DocumentStatus.PENDING, "manager-owned"));
        documents.put(105L, new Document(105L, "north", "alice",
                1, DocumentStatus.ARCHIVED, "archived"));
        documents.put(106L, new Document(106L, "north", "bob",
                2, DocumentStatus.DRAFT, "editable"));
    }

    public Document find(long id) {
        return documents.get(id);
    }

    public Document require(long id) {
        Document document = find(id);
        if (document == null) {
            throw new NoSuchElementException("Document not found");
        }
        return document;
    }

    public Document updateContent(long id, String newContent) {
        return documents.compute(id, (key, old) -> {
            if (old == null) {
                throw new NoSuchElementException("Document not found");
            }
            return new Document(old.id(), old.tenant(), old.owner(),
                    old.minClearance(), old.status(), newContent);
        });
    }

    public Document approve(long id) {
        return documents.compute(id, (key, old) -> {
            if (old == null) {
                throw new NoSuchElementException("Document not found");
            }
            if (old.status() != DocumentStatus.PENDING) {
                throw new IllegalStateException(
                        "Document is not pending");
            }
            return new Document(old.id(), old.tenant(), old.owner(),
                    old.minClearance(), DocumentStatus.APPROVED,
                    old.content());
        });
    }
}

enum DocumentStatus {
    DRAFT, PENDING, APPROVED, ARCHIVED
}

record Document(
        long id,
        String tenant,
        String owner,
        int minClearance,
        DocumentStatus status,
        String content) {}
```

Repository dùng `ConcurrentHashMap` để test state; nó **không thay thế transaction** trong production. `compute` bảo đảm lần thay đổi trạng thái đối với cùng key là atomic trong một JVM. Khi có DB/nhiều node, cần transaction/optimistic locking/conditional update; authorization và update phải đánh giá rủi ro **TOCTOU**.

Fixture `reset()` giúp các test không phụ thuộc thứ tự, nhưng nếu sau này bật JUnit parallel execution, cần cô lập repository theo test hoặc dùng resource lock; không để các test thay đổi cùng một map đồng thời.

### 7.10. DocumentPolicy.java: business policy không phụ thuộc web

`src/main/java/demo/DocumentPolicy.java`:

```java
package demo;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final UserProfileDirectory directory;
    private final DocumentRepository repository;

    public DocumentPolicy(UserProfileDirectory directory,
                          DocumentRepository repository) {
        this.directory = directory;
        this.repository = repository;
    }

    private UserProfile profile(Authentication auth) {
        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return null;
        }
        return directory.find(auth.getName());
    }

    public boolean canRead(Authentication auth, long id) {
        UserProfile user = profile(auth);
        Document doc = repository.find(id);

        return user != null
                && doc != null
                && user.tenant().equals(doc.tenant())
                && user.clearance() >= doc.minClearance()
                && doc.status() != DocumentStatus.ARCHIVED;
    }

    public boolean canEdit(Authentication auth, long id) {
        if (!canRead(auth, id)) {
            return false;
        }

        Document doc = repository.find(id);
        return doc != null
                && doc.owner().equals(auth.getName())
                && doc.status() == DocumentStatus.DRAFT;
    }

    public boolean canApprove(Authentication auth, long id) {
        if (!canRead(auth, id)) {
            return false;
        }

        Document doc = repository.find(id);
        return doc != null
                && doc.status() == DocumentStatus.PENDING
                && !doc.owner().equals(auth.getName());
    }
}
```

Policy **không nhận HttpServletRequest** và không đọc headers, query, path hoặc session. Test có thể tạo `Authentication` trực tiếp. Nó so subject tenant/clearance với resource tenant/classification/status từ server, và dùng action-specific checks.

`canEdit` và `canApprove` chưa kiểm tra role: đó là chủ ý. Role được kiểm tra bằng `hasRole('EDITOR')` và `hasRole('MANAGER')` ngay trong `@PreAuthorize` của service. Nhờ tách các điều kiện, tests có thể chứng minh cả **role gate** và **object-level gate**.

Nếu production muốn policy bean độc lập với SpEL roles, có thể đưa role checks vào policy. Điều quan trọng là **chính sách cuối cùng không bỏ sót điều kiện**.

### 7.11. DocumentService.java: nơi interceptor hoạt động

`src/main/java/demo/DocumentService.java`:

```java
package demo;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #id)")
    public Document read(long id) {
        return repository.require(id);
    }

    @PreAuthorize(
            "hasRole('EDITOR') and @documentPolicy.canEdit(authentication, #id)")
    public String edit(long id, String newContent) {
        repository.updateContent(id, newContent);
        return "edited-" + id;
    }

    @PreAuthorize(
            "hasRole('MANAGER') and @documentPolicy.canApprove(authentication, #id)")
    public String approve(long id) {
        repository.approve(id);
        return "approved-" + id;
    }

    @PostAuthorize(
            "@documentPolicy.canRead(authentication, returnObject.id())")
    public Document inspect(long id) {
        return repository.require(id);
    }
}
```

Ở `read`, check xảy ra trước khi `repository.require(id)` chạy. Ở `inspect`, repository đọc object trước, sau đó `@PostAuthorize` đánh giá object trả về. `inspect` được thiết kế **read-only**; không đặt `@PostAuthorize` là biện pháp duy nhất cho `edit`/`approve` vì operation có thể đã đổi state trước khi interceptor từ chối.

`#id` cần được resolve từ method parameters; build config đã thêm `-parameters`. Nếu service trả DTO thay vì record, SpEL `returnObject.id()` phải phù hợp API/Java bean getters tương ứng.

## 8. Unit test policy không có Spring context

Test đầu kiểm tra **logic chính sách thuần** mà không bật Spring và không dùng method-security proxy. Tạo repository, directory và policy bằng `new` là phù hợp **ở mức unit test này**, vì mục tiêu là kiểm tra các điều kiện của chính sách.

`src/test/java/demo/DocumentPolicyUnitTest.java`:

```java
package demo;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentPolicyUnitTest {

    private DocumentRepository documents;
    private DocumentPolicy policy;

    @BeforeEach
    void setUp() {
        documents = new DocumentRepository();
        UserProfileDirectory profiles = new UserProfileDirectory();
        policy = new DocumentPolicy(profiles, documents);
    }

    private Authentication subject(String username, String role) {
        return new UsernamePasswordAuthenticationToken(
                username, "unused-test-credential",
                List.of(new SimpleGrantedAuthority("ROLE_" + role)));
    }

    @Test
    void matchingTenantAndClearancePermitsRead() {
        assertTrue(policy.canRead(subject("alice", "READER"), 101L));
        assertTrue(policy.canRead(subject("bob", "READER"), 102L));
    }

    @Test
    void higherClassificationDeniesRead() {
        assertFalse(policy.canRead(subject("alice", "READER"), 102L));
    }

    @Test
    void crossTenantResourceIsDenied() {
        assertFalse(policy.canRead(subject("alice", "READER"), 103L));
        assertTrue(policy.canRead(subject("carol", "READER"), 103L));
    }

    @Test
    void archivedResourceIsDenied() {
        assertFalse(policy.canRead(subject("alice", "READER"), 105L));
    }

    @Test
    void missingProfileOrResourceFailsClosed() {
        assertFalse(policy.canRead(subject("ghost", "MANAGER"), 101L));
        assertFalse(policy.canRead(subject("bob", "READER"), 999L));
        assertFalse(policy.canRead(null, 101L));
    }

    @Test
    void ownerCanEditOnlyOwnDraft() {
        assertTrue(policy.canEdit(subject("bob", "READER"), 106L));
        assertFalse(policy.canEdit(subject("bob", "READER"), 101L));
        assertFalse(policy.canEdit(subject("bob", "READER"), 102L));
    }

    @Test
    void approverPolicyUsesStatusAndOwner() {
        assertTrue(policy.canApprove(subject("maria", "READER"), 102L));
        assertFalse(policy.canApprove(subject("maria", "READER"), 104L));
        assertFalse(policy.canApprove(subject("maria", "READER"), 101L));
    }
}
```

### Unit test này chứng minh gì?

- Subject/resource tenant và clearance được đối chiếu đúng.
- Bản ghi archived không được đọc dù owner trùng.
- User profile không tồn tại hoặc resource không có thì fail closed.
- Edit chỉ áp dụng cho owner của document DRAFT.
- Approve cần khác owner và document PENDING.

### Unit test này CHƯA chứng minh gì?

- `@PreAuthorize` có được Spring bật hay không.
- `hasRole('MANAGER')`/`hasRole('EDITOR')` đã chạy ở service chưa.
- Lời gọi tới `DocumentService` có qua AOP proxy không.
- `@PostAuthorize` có kiểm tra return object không.
- HTTP filter hoặc Basic login có hoạt động không.

**Đây là lý do cần bộ test thứ hai.** Việc test policy bean đơn lẻ rất có giá trị nhưng không thay method-security integration test.

## 9. Integration test trực tiếp Spring-managed service, không HTTP

Bộ này dùng:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DocumentServiceSecurityTest {
    @Autowired
    DocumentService service;
}
```

`WebEnvironment.NONE` bảo đảm test không tạo web application server, không gọi `DispatcherServlet`. Spring context vẫn đăng ký `@EnableMethodSecurity` và tạo proxy/authorization infrastructure. Bean `DocumentService` được lấy từ context, **không phải `new DocumentService(...)` trong test**.

### 9.1. Mã kiểm thử hoàn chỉnh

`src/test/java/demo/DocumentServiceSecurityTest.java`:

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DocumentServiceSecurityTest {

    @Autowired
    DocumentService service;

    @Autowired
    DocumentRepository documents;

    @BeforeEach
    void reset() {
        documents.reset();
    }

    @Test
    void springServiceIsProxiedForMethodSecurity() {
        assertTrue(AopUtils.isAopProxy(service));
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void readerCanReadDocumentInOwnTenant() {
        assertEquals("north-public", service.read(101L).content());
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void insufficientClearanceIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(102L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void userCannotReadOtherTenantDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(103L));
    }

    @Test
    @WithMockUser(username = "carol", roles = "READER")
    void legitimateSouthTenantUserCanRead() {
        assertEquals("south-draft", service.read(103L).content());
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void archivedDocumentIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(105L));
    }

    @Test
    @WithMockUser(username = "ghost", roles = {"READER", "MANAGER"})
    void unknownProfileFailsClosedDespitePowerfulMockedRole() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void missingDocumentFailsClosed() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(999L));
    }

    @Test
    @WithAnonymousUser
    void anonymousUserIsDeniedWithoutHttpRequest() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(101L));
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void ownerWithoutEditorRoleCannotChangeState() {
        String before = documents.require(101L).content();

        assertThrows(AccessDeniedException.class,
                () -> service.edit(101L, "tampered"));

        assertEquals(before, documents.require(101L).content());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER", "EDITOR"})
    void editorCanEditOwnDraft() {
        assertEquals("edited-106",
                service.edit(106L, "new-content"));
        assertEquals("new-content", documents.require(106L).content());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER", "EDITOR"})
    void editorCannotEditAnotherOwnersDraft() {
        String before = documents.require(101L).content();

        assertThrows(AccessDeniedException.class,
                () -> service.edit(101L, "tampered"));

        assertEquals(before, documents.require(101L).content());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER", "EDITOR"})
    void editorCannotEditNonDraftEvenIfOwner() {
        String before = documents.require(102L).content();

        assertThrows(AccessDeniedException.class,
                () -> service.edit(102L, "tampered"));

        assertEquals(before, documents.require(102L).content());
    }

    @Test
    @WithMockUser(username = "bob", roles = {"READER", "EDITOR"})
    void missingManagerRoleDeniesApprovalEvenIfOtherConditionsMatch() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve(104L));
        assertEquals(DocumentStatus.PENDING,
                documents.require(104L).status());
    }

    @Test
    @WithMockUser(username = "maria", roles = {"READER", "MANAGER"})
    void managerCanApproveOtherOwnersPendingDocument() {
        assertEquals("approved-102", service.approve(102L));
        assertEquals(DocumentStatus.APPROVED,
                documents.require(102L).status());
    }

    @Test
    @WithMockUser(username = "maria", roles = {"READER", "MANAGER"})
    void managerCannotApproveOwnDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve(104L));
        assertEquals(DocumentStatus.PENDING,
                documents.require(104L).status());
    }

    @Test
    @WithMockUser(username = "carol", roles = {"READER", "MANAGER"})
    void managerFromOtherTenantCannotApprove() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve(102L));
        assertEquals(DocumentStatus.PENDING,
                documents.require(102L).status());
    }

    @Test
    @WithMockUser(username = "carol", roles = {"READER", "MANAGER"})
    void managerCannotSelfApproveSouthTenantDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.approve(103L));
    }

    @Test
    @WithMockUser(username = "maria", roles = {"READER", "MANAGER"})
    void alreadyApprovedDocumentCannotBeApprovedAgain() {
        service.approve(102L);

        assertThrows(AccessDeniedException.class,
                () -> service.approve(102L));

        assertEquals(DocumentStatus.APPROVED,
                documents.require(102L).status());
    }

    @Test
    @WithMockUser(username = "maria", roles = "READER")
    void postAuthorizePermitsAllowedReturnObject() {
        Document document = service.inspect(102L);
        assertEquals(102L, document.id());
    }

    @Test
    @WithMockUser(username = "alice", roles = "READER")
    void postAuthorizeBlocksUnauthorizedReturnObject() {
        assertThrows(AccessDeniedException.class,
                () -> service.inspect(102L));
    }

    @Test
    @WithUserDetails("bob")
    void withUserDetailsLoadsConfiguredUserAuthorities() {
        assertEquals("edited-106",
                service.edit(106L, "from-user-details"));
        assertEquals("from-user-details",
                documents.require(106L).content());
    }
}
```

**Kết quả kỳ vọng:** 22 JUnit tests trong `DocumentServiceSecurityTest` cùng 7 tests trong `DocumentPolicyUnitTest` PASS khi dùng đúng các source files và Gradle build phía trên. Đây là **kỳ vọng qua phân tích mã**, không phải tuyên bố các test đã được thực thi trong bài.

### 9.2. Những điểm đáng chú ý trong test

**Thứ nhất, kiểm tra AOP proxy:** test `AopUtils.isAopProxy(service)` cảnh báo khi bean không được method-security proxy bảo vệ. Tuy nhiên chỉ có proxy vẫn chưa chứng minh annotation đánh giá đúng; phải có negative tests `AccessDeniedException`.

**Thứ hai, xác thực không thông qua HTTP:** `@WithMockUser`/`@WithUserDetails` tạo authentication trong test security context. Lời gọi `service.read(101L)` đi thẳng tới Spring bean, không có method GET hay mock servlet request.

**Thứ ba, mỗi rule có negative case độc lập:** tenant, clearance, owner, resource state và role không bị gộp hết vào một test. Nhờ vậy khi developer vô tình xóa một điều kiện, test tương ứng sẽ fail.

**Thứ tư, kiểm tra side effects:** test unauthorized edit ghi nhận `before` và assert content **không đổi** sau `AccessDeniedException`. Test approve bị deny cũng assert trạng thái vẫn PENDING.

**Thứ năm, @PostAuthorize:** kiểm tra riêng object được phép trả về và object không được trả về. Với `@PostAuthorize`, method body đã chạy trước khi check; vì vậy chỉ dùng với method read-only trong demo.

**Thứ sáu, test isolation:** `@BeforeEach` reset repository về cùng baseline. Spring Security Test listener tự set/clear security context theo từng test. Không để `@WithMockUser` ở cấp class khi nhiều tests cần subject khác nhau mà quên annotation method override.

## 10. Lệnh chạy và cách đọc kết quả

Từ thư mục project `method-security-service-tests`, cài JDK 17+ và Gradle tương thích:

```bash
gradle test
```

Nếu có Gradle Wrapper:

```bash
./gradlew test
```

Trên Windows PowerShell, nếu project có wrapper:

```powershell
.\gradlew.bat test
```

Trong Gradle/JUnit report, kết quả mong đợi là không có test thất bại. Những test cố tình gọi service trái quyền **PASS khi `assertThrows(AccessDeniedException.class, ...)` bắt đúng exception**, không phải vì ứng dụng cho request qua.

Chạy test theo class để khoanh vùng:

```bash
./gradlew test --tests demo.DocumentPolicyUnitTest
./gradlew test --tests demo.DocumentServiceSecurityTest
```

Không chạy `bootRun` để kiểm tra bài này là cần thiết: mục tiêu là **method-level authorization độc lập với HTTP**. Có thể chạy app để tích hợp controller về sau, nhưng không phải một bước trong service test.

### Vì sao status 403 không xuất hiện?

Trong test này, method-security interceptor ném `AccessDeniedException` tới caller Java. Không có HTTP request hay `ExceptionTranslationFilter`/Servlet chain để chuyển exception thành response 403. Nếu cần xác minh 403 ở endpoint, phải viết **một bộ HTTP integration test riêng**; không nên mock status code trong service test rồi coi đó là test bảo mật thành công.

## 11. Những lỗi test khiến @PreAuthorize bị bỏ qua

### 11.1. Test tự new Service thay vì lấy Spring bean

Sai nếu mục tiêu là kiểm chứng interceptor:

```java
DocumentService service = new DocumentService(repository);
service.read(101L); // Không chạy qua Spring AOP proxy.
```

Việc tự `new` service không đăng ký `@EnableMethodSecurity` và không có advice. Dù method có `@PreAuthorize`, annotation không tự trở thành một câu lệnh `if` được Java chạy. Để test method-security wiring, inject bean `@Autowired DocumentService service` từ Spring context.

**Phân biệt:** trong `DocumentPolicyUnitTest`, dùng `new DocumentPolicy(...)` là **đúng** vì mục tiêu chỉ là unit test policy logic. Sai là dùng object `new DocumentService(...)` rồi tuyên bố test đang kiểm tra `@PreAuthorize`.

### 11.2. Quên @EnableMethodSecurity

Nếu cấu hình không có:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfig {}
```

các annotations như `@PreAuthorize` có thể không được kích hoạt. Một happy-path test `read` vẫn PASS vì method body chạy, dẫn đến **false confidence**. Negative cases giúp phát hiện việc bỏ sót wiring.

Với Spring Security 6, `@EnableMethodSecurity` là cơ chế mới tương ứng; không tự dựa vào cấu hình cũ `@EnableGlobalMethodSecurity` rồi cho rằng mọi defaults giống nhau.

### 11.3. Self-invocation trong cùng service

Ví dụ anti-pattern:

```java
@Service
public class BadService {

    public String unprotectedEntry(long id) {
        return this.sensitiveAction(id);
    }

    @PreAuthorize("hasRole('MANAGER')")
    public String sensitiveAction(long id) {
        return "processed-" + id;
    }
}
```

Nếu lời gọi `this.sensitiveAction(id)` không đi qua Spring proxy, advice cho `sensitiveAction` có thể **không chạy**. Không coi một test chỉ gọi `service.sensitiveAction(id)` thành công/thất bại là đủ: phải test mọi public entry points (`unprotectedEntry`, scheduled job, event listener, message handler) có thể dẫn tới operation.

Cách xử lý: tách secured method sang một Spring bean khác và gọi qua proxy, hoặc đưa policy check tường minh ở domain boundary được bảo đảm thực thi. Không sửa bằng cách giả định AOP sẽ intercept lời gọi nội bộ.

### 11.4. Private/final methods và proxy limitations

Proxy-based method security không giống bytecode rewriting toàn bộ call sites. Các methods không thể được proxy intercept (ví dụ private, một số final methods/classes hoặc lời gọi nội bộ) có thể không được bảo vệ như mong muốn. Chọn phương thức public/proxyable và xác minh với integration tests, nhất là khi project dùng Kotlin (class final mặc định), nhiều interface, hoặc thêm tối ưu proxy.

Đừng chỉ assert `AopUtils.isAopProxy` nếu secured method không thực sự chạy qua proxy. Test deny/allow là bằng chứng bổ sung thiết yếu.

### 11.5. SpEL sai tên parameter

`@PreAuthorize("@policy.canRead(authentication, #id)")` phụ thuộc method argument name `id`. Nếu Java build không lưu metadata tên parameter hoặc annotation metadata không phù hợp, `#id` có thể null/không resolve.

Cách khắc phục: bật compiler `-parameters` như project mẫu; hoặc dùng `@P("id")`/`@Param` nếu framework version và resolver tương ứng hỗ trợ. Viết unit test policy không bắt được lỗi SpEL method parameter name; integration test service qua proxy sẽ phát hiện.

### 11.6. Sai bean name trong SpEL

`@documentPolicy.canRead(...)` cần một bean tên `documentPolicy`. Project mẫu khai báo `@Component("documentPolicy")` để rõ ràng. Nếu đổi bean name nhưng quên sửa annotation, request có thể lỗi evaluation thay vì deny theo policy dự kiến.

Trong test, phân biệt **policy trả DENY** với **exception do wiring hoặc SpEL sai**. Không bắt mọi `Exception` rồi gọi là “test pass vì bị chặn”, vì một lỗi cấu hình hoàn toàn khác có thể bị che.

## 12. Testing SecurityContextHolder theo cách thủ công

Ngoài `spring-security-test`, có thể tự set context trong unit tests. Đây là kỹ thuật có ích cho code library không dùng Spring Test listener hoặc khi cần test custom authentication object.

Ví dụ **fragment** cho JUnit test:

```java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContext context =
            SecurityContextHolder.createEmptyContext();

    Authentication auth = new UsernamePasswordAuthenticationToken(
            "alice",
            "unused",
            List.of(new SimpleGrantedAuthority("ROLE_READER")));

    context.setAuthentication(auth);
    SecurityContextHolder.setContext(context);

    // Gọi Spring-managed service qua proxy hoặc policy bean.
    // assertion...
} finally {
    SecurityContextHolder.clearContext();
}
```

**Không** đặt một SecurityContext đã được người khác mutate vào shared global variable, không dựa vào thứ tự test, không để ThreadLocal context rò sang test thread tiếp theo. Nếu cố tình bật `MODE_INHERITABLETHREADLOCAL` hoặc một strategy tùy chỉnh, phải hiểu cách propagation hoạt động giữa threads/executors.

### SecurityContext khi test chạy async

Một test gọi service qua `CompletableFuture`/`@Async` có thể dùng thread khác; mặc định context thường không tự truyền mọi nơi như lời gọi synchronous. Đừng kỳ vọng `@WithMockUser` trong test thread sẽ tự tồn tại trong worker thread. Với nghiệp vụ async cần security context propagation có chủ đích (ví dụ `DelegatingSecurityContextExecutor` hoặc cơ chế context propagation được hỗ trợ), cùng cleanup và tests riêng.

Cũng không nên tự bật `MODE_GLOBAL` trong test suite lớn để “cho test async pass” vì nó làm context bị chia sẻ nguy hiểm giữa tests/threads.

### Test setup trước khi context được tạo

`@WithMockUser` và các security test annotations được Spring Test listener xử lý theo lifecycle. Mặc định chúng thường thiết lập context **trước `@BeforeEach`**; có thể cấu hình `setupBefore=TEST_EXECUTION` để thay thời điểm. Nếu `@BeforeEach` có logic cần subject cụ thể, hãy hiểu chính xác lifecycle/version; tốt nhất để các authorization assertions trong test method và tránh phụ thuộc context trong fixture setup.

## 13. Mockito và những điều cần tránh khi mock dependency

Mockito có thể hỗ trợ unit test domain policy và test “service body không được gọi”:

```java
// Minh họa ý tưởng, không phải test class độc lập.
verify(repository, never()).updateContent(anyLong(), anyString());
```

Nhưng nếu mock **chính Spring-managed secured service** bằng một mock thông thường, proxy/method-security interceptor có thể không được kiểm tra. Bạn có thể khiến method trả value theo stub, bỏ qua annotation `@PreAuthorize` rồi tưởng policy được phép.

**Gợi ý chiến lược:**

- Với policy unit test, mock PIP/repository nếu cần tạo input edge cases nhanh; hoặc dùng in-memory fixtures thật.
- Với method-security integration test, **giữ service thật được proxy**, chỉ fake hoặc mock các dependencies ở dưới khi phù hợp.
- Đừng mock `AuthorizationManager` rồi kết luận policy thật đã được đánh giá.
- Nếu dùng `@MockBean` (Boot test) hoặc `@MockitoBean` (phiên bản Spring Test hỗ trợ), kiểm tra version và bean bị thay thế; tránh accidentally replace chính secured bean đang định test.
- Kết hợp kiểm tra exception với `verifyNoInteractions(...)` hay assert state unchanged để bắt side effects.

### Vì sao @WithMockUser không phải “mock phương thức”?

`@WithMockUser` mock **danh tính/authorities của test security context**, không thay thế body của `DocumentService`, không stub `DocumentPolicy` và không tự cho phép vượt các annotations. Service thật vẫn được Spring AOP kiểm tra theo rules được cấu hình.

## 14. Method Security và @Transactional: thứ tự, side effects, race

Khi một service vừa có `@PreAuthorize` vừa có `@Transactional`, các advisors của Spring AOP có ordering, nên test sự tương tác trong version/config cụ thể. Bất kể thứ tự advice, **đừng** cho rằng một policy pre-check đủ giải quyết mọi race với dữ liệu bị thay đổi đồng thời.

Ví dụ:

```text
T1: policy canApprove(document=102, status=PENDING) -> allow
T2: another request approves document 102 -> status=APPROVED
T1: service update document 102                 -> ?
```

Nếu update chỉ ghi thẳng mà không kiểm tra state, có thể xảy ra double transition. Demo `DocumentRepository.approve` kiểm tra `PENDING` lại bên trong `ConcurrentMap.compute`. Database production cần `UPDATE ... WHERE id=? AND status='PENDING'`, optimistic locking, version column hoặc transaction isolation phù hợp.

### Kiểm thử concurrency khác test method-security thuần

Một test synchronous `@WithMockUser` chỉ cho biết permission tại một thời điểm. Nếu nghiệp vụ yêu cầu không double-approve, cần stress/concurrency tests và transactional integration tests riêng, không nên coi 22 method-security tests là bằng chứng đủ cho atomicity trên DB thật.

### Side effect dù @PostAuthorize từ chối

Nếu `@PostAuthorize` dùng cho method gửi notification trước khi trả kết quả, caller có thể nhận AccessDeniedException **sau khi email đã gửi**. Do đó tests nên bao gồm mutation/side effects nếu method dùng post-authorization; ưu tiên pre-authorization cho state-changing operations.

## 15. Kiểm thử custom Authentication, JWT claims và tenant context

`@WithMockUser` có username và authorities đơn giản, đủ cho role/owner mẫu. Với nghiệp vụ cần thông tin principal phong phú — tenant memberships, department, MFA, authentication freshness, OAuth2 scopes — có thể:

1. Tạo test `Authentication` thủ công có principal và authorities đúng shape.
2. Dùng `@WithSecurityContext` với một `WithSecurityContextFactory` để tái sử dụng setup.
3. Với resource-server JWT, dùng helpers của `spring-security-test` trong HTTP tests để tạo JWT authentication; với service-only tests, dùng đối tượng `JwtAuthenticationToken` được xây dựng phù hợp nếu policy thực sự đọc JWT claims.
4. Dùng `@WithUserDetails` khi muốn test authorities từ `UserDetailsService` bean.

**Không** tạo raw header `X-Tenant` rồi tin nó trong service-only test: service thường không có `HttpServletRequest`; tenant context cần được **chuyển thành một object đã xác minh**, dựa vào membership và principal đúng trust boundary.

### Ví dụ phân biệt trusted và untrusted input

```text
Subject from verified Authentication:
    username=alice, allowedTenants=[north], clearance=1

Resource from DocumentRepository:
    docId=103, tenant=south, minClearance=1

Client-selected tenant:
    "south"

Decision:
    DENY, vì alice không thuộc south.
```

Nếu dịch vụ nhận tenant selector, phải so nó với allowed tenants của subject và tenant của document. Test có thể truyền selector như một **method argument**, không cần HTTP header thật, để chứng minh policy từ chối việc giả mạo.

### Đừng dùng @WithMockUser để chứng minh authentication provider

`@WithMockUser(username="admin", roles="ADMIN")` có thể tạo user admin dù production user store không hề có admin. Điều đó **đúng** cho việc test authorization “nếu user này có role X thì policy cho gì”, nhưng không chứng minh registration, password verification, disabled-account checks, OIDC login hay JWT signature đã hoạt động. Những thứ này cần bộ test authentication integration riêng.

## 16. Kiểm tra service theo đa entry points

Một service có thể được gọi từ:

- REST Controller/Servlet HTTP;
- GraphQL resolver;
- scheduled job;
- message consumer;
- batch processor;
- event handler;
- test hoặc bean nội bộ.

Nếu method security được gắn vào service qua proxy, nó giúp áp dụng policy chung nhưng **không tự tạo Authentication cho background jobs**. Một scheduled job gọi service khi không có `SecurityContext` có thể bị từ chối — thường là đúng cho user-scoped operations, nhưng cần service/system principal được kiểm soát nếu có nghiệp vụ hệ thống.

Với hệ thống xử lý message, không nên lấy userId từ payload rồi giả danh người dùng tùy ý. Nếu muốn chạy “thay mặt user”, cần xác minh event, signature, authorization context, thời hạn và audit. Không “bỏ qua @PreAuthorize” cho code path nội bộ bằng cách dùng `new Service`.

### Test từng entry point hay chỉ service?

Method-security tests đảm bảo **service boundary**, nhưng nếu một code path bypass proxy (self-invocation, static helper hoặc repository direct call), nó có thể không được bảo vệ. Thêm tests ở các entry points quan trọng để xác minh service được gọi theo cách đi qua method interceptor.

## 17. Thử nghiệm mở rộng cho dữ liệu và trạng thái

Sau khi hoàn thành demo, có thể mở rộng theo thứ tự:

**Bài 1 — role và authority:** thay rule `hasRole('EDITOR')` bằng `hasAuthority('DOC_WRITE')`, tạo tests cho `@WithMockUser(authorities="DOC_WRITE")` và xác nhận `roles="EDITOR"` không còn tự match.

**Bài 2 — nhiều tenant:** đổi `UserProfile` từ một `tenant` sang `Set<String> allowedTenants`. Policy cần xác minh tenant của document thuộc tập cho phép; test user `north` không thể đọc `south` chỉ vì truyền tenant selector trong method argument.

**Bài 3 — policy từ trạng thái:** thêm `REJECTED` và chỉ cho phép reviewer chuyển `PENDING → REJECTED`. Test một request deny khi document đã `APPROVED`, và assert state không đổi.

**Bài 4 — data classification:** đặt doc classification cao hơn clearance; test từng mức để không có lỗi `>=` và `>`.

**Bài 5 — re-auth/MFA:** chỉ approve nếu authentication có assurance được xác minh và timestamp đủ mới. Dùng clock server inject được thay vì `System.currentTimeMillis()` hard-code để test deterministic.

**Bài 6 — audit:** thêm repository audit records nhưng không ghi raw credentials. Test unauthorized calls không phát ra audit “approved” giả, đồng thời có thể phát ra sự kiện denial security-safe.

**Bài 7 — self-invocation:** cố tình tạo một bean `outerMethod` gọi `this.securedMethod` rồi viết negative test, sau đó tách bean để cả direct/indirect calls đều bị chặn.

**Bài 8 — mutation tests:** xóa từng điều kiện tenant/owner/clearance/status/role trong policy và xem test nào fail. Nếu có điều kiện bị xóa mà tất cả tests vẫn PASS, bộ tests chưa đủ độc lập.

**Bài 9 — concurrency:** bổ sung repository có optimistic locking rồi gửi hai approve calls song song để chỉ một transition thành công.

**Bài 10 — tích hợp HTTP:** sau khi service policy đã vững, thêm controller và MockMvc tests để đảm bảo HTTP 401/403, method matchers, CSRF và service security hoạt động cùng nhau. Đây là giai đoạn **bổ sung**, không được thay việc test service độc lập.

## 18. Checklist QA cho method-security test suite

- [ ] Có `@EnableMethodSecurity` trong Spring test context.
- [ ] Service dưới test được **Spring inject**, không `new` trực tiếp.
- [ ] `AopUtils.isAopProxy(service)` đúng khi proxy-based method security được kỳ vọng.
- [ ] Có test allow và deny cho mỗi method bảo vệ.
- [ ] Test deny bắt `AccessDeniedException` cụ thể, không bắt `Exception` chung để che lỗi.
- [ ] Phân biệt anonymous token với context không có Authentication.
- [ ] `@WithMockUser` dùng đúng `roles`/`authorities` và prefix `ROLE_`.
- [ ] Có test `@WithUserDetails` nếu roles từ user store là điểm quan trọng.
- [ ] Unit test policy **tách** integration test method interceptor.
- [ ] User/resource attributes đến từ dữ liệu đáng tin trong fixtures.
- [ ] Test từng chiều tenant/role/owner/status/clearance độc lập.
- [ ] Unknown principal/resource bị deny theo fail-closed.
- [ ] Denied edit/approve không đổi state dữ liệu.
- [ ] Post-authorization chỉ dùng khi method body không gây side effects.
- [ ] Tests reset mutable fixtures, không dựa vào thứ tự hoặc context của test khác.
- [ ] `#id` trong SpEL resolve đúng, có compiler `-parameters` hoặc metadata phù hợp.
- [ ] Không có self-invocation hoặc unproxied entry points bypass policy.
- [ ] Không mock chính secured service trong test muốn kiểm chứng AOP.
- [ ] Không nhầm kết quả exception Java với status HTTP 401/403.
- [ ] Khi chính sách đổi, có regression tests và code review rõ ràng.

## 19. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách giải quyết |
| --- | --- | --- |
| Test trái quyền vẫn trả data | Chưa bật method security, service không qua proxy | Bật `@EnableMethodSecurity`, inject Spring bean, negative tests |
| `@PreAuthorize` kiểm tra không đúng id | SpEL `#id` không resolve do thiếu parameter metadata | Bật `-parameters` và kiểm tra signature |
| Rule role deny dù test đặt roles | Nhầm `ROLE_` prefix hoặc dùng hasAuthority khác hasRole | So authority thực và expression |
| Test anonymous ném lỗi ngoài dự kiến | Context trống khác `AnonymousAuthenticationToken` | Dùng `@WithAnonymousUser`, phân biệt credential-missing behavior |
| Policy unit tests PASS nhưng method calls không bị chặn | Unit tests không test wiring/proxy | Thêm `@SpringBootTest(webEnvironment=NONE)` + deny tests |
| Method được gọi nội bộ bỏ qua interceptor | Self-invocation qua `this` | Tách secured service bean hoặc enforce tường minh |
| Deny test PASS vì NPE/SpEL parse error | Bắt `Exception` chung | Bắt `AccessDeniedException` và inspect nguyên nhân |
| Test fail ngẫu nhiên theo thứ tự | Shared repository/security context chưa reset | `@BeforeEach` setup, Spring Security Test cleanup, test isolation |
| Denied edit vẫn thay đổi resource | Check quá muộn hoặc gọi method không qua proxy | `@PreAuthorize`, assert unchanged state, fix call path |
| @PostAuthorize trả deny nhưng đã gửi email | Check sau side effect | Dùng pre-authorization và transaction-safe operation |
| User thiếu profile vẫn được quyền | Policy fail-open hoặc only role gate | Kiểm tra subject directory, fail closed |
| Test qua @WithMockUser PASS nhưng login thật lỗi | Mock auth bypass authentication mechanism | Test authentication riêng với filter/IdP/token |
| Test role mà không test resource ownership | RBAC test chưa đủ object-level checks | Thêm unit/method integration ABAC tests |
| Test service ném AccessDeniedException không ra 403 | Không có HTTP layer trong test | Đúng mục tiêu; muốn status thì thêm MockMvc/E2E suite |
| Test async không thấy Authentication | Thread context propagation chưa thiết kế | Dùng cơ chế propagation phù hợp, test async riêng |

## 20. Câu hỏi tự kiểm tra

1. **Tại sao test service độc lập HTTP?** Để cô lập chính sách nghiệp vụ và method interceptor khỏi controller/filter/CSRF.
2. **Unit test policy khác method-security integration test?** Unit test gọi logic `canRead`; integration test gọi secured Spring bean qua proxy để chạy `@PreAuthorize`.
3. **`@WithMockUser` có thực sự kiểm tra password không?** Không. Nó chủ động tạo test authentication.
4. **`@WithUserDetails` có mở HTTP request không?** Không. Nó tải UserDetails từ bean và đặt vào test context.
5. **Nên gọi `new DocumentService(...)` trong test @PreAuthorize không?** Không nếu muốn test AOP interception; hãy inject bean.
6. **Deny từ @PreAuthorize xảy ra trước hay sau method body?** Trước. Vì vậy nên assert side effects không xảy ra.
7. **@PostAuthorize dùng cho update tài nguyên có nguy cơ gì?** Operation có thể đã cập nhật dữ liệu trước khi bị từ chối.
8. **Test method security không có HTTP trả status 403 không?** Không; caller Java nhận `AccessDeniedException`.
9. **Vì sao phải test từng điều kiện độc lập?** Để biết chính sách thật sự kiểm tra role, tenant, clearance, owner và status; một test với nhiều điều kiện sai có thể che omission.
10. **Nếu user có role MANAGER nhưng policy tenant sai?** Phải deny; role không vượt tenant constraint.
11. **`@WithAnonymousUser` khác context null?** Nó tạo anonymous Authentication; context null có thể đi qua error path khác.
12. **@EnableMethodSecurity hoạt động với service không có Servlet request không?** Có, với Spring-managed proxy và Authentication context phù hợp.
13. **Self-invocation ảnh hưởng gì?** Lời gọi nội bộ `this.securedMethod()` có thể bypass advice của AOP proxy.
14. **Tại sao cần -parameters?** Để SpEL reference `#id` map tới đúng method parameter name.
15. **Sau một approve bị deny, nên assert gì?** Exception và trạng thái tài liệu chưa bị thay đổi.
16. **Có thể bỏ HTTP integration tests sau khi service tests PASS?** Không; HTTP matchers, filters, authentication và CSRF cần tests riêng.
17. **Nếu token JWT hợp lệ nhưng user bị thu hồi tenant?** Cần policy membership freshness/revocation; method-level policy vẫn phải dùng nguồn tin cậy.
18. **Nếu service bị @MockBean replace, có đang test @PreAuthorize thật không?** Có thể không; cần kiểm tra test wiring và không mock secured service.
19. **Tại sao không bắt mọi Exception để chứng minh deny?** Vì NPE/lỗi SpEL/config cũng khiến test PASS giả.
20. **Test policy cần ghi audit ra sao?** Ghi decision/actor/resource id có kiểm soát, không đưa secret/token hoặc nội dung nhạy cảm vào logs.

**Ghi nhớ:** **Policy unit tests** chứng minh các điều kiện nghiệp vụ, còn **method-security integration tests** chứng minh Spring Security thực sự áp dụng `@PreAuthorize`/`@PostAuthorize` thông qua proxy. Dùng `@SpringBootTest(webEnvironment=NONE)`, inject **Spring-managed service**, tạo principal bằng `@WithMockUser`/`@WithAnonymousUser`/`@WithUserDetails`, gọi method trực tiếp, assert `AccessDeniedException` khi thiếu quyền và assert **dữ liệu không thay đổi** đối với side effects bị từ chối. Kiểm tra từng chiều role, tenant, owner, clearance và trạng thái độc lập. Không nhầm các tests này với authentication/filter/HTTP tests; cả hai tầng đều cần được kiểm chứng.
