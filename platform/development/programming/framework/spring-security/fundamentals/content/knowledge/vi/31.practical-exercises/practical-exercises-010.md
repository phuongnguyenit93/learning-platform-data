# Lập bản đồ từ yêu cầu sản phẩm đến cơ chế bảo mật, kiểm thử và vận hành

> **Bài thực hành tổng hợp — Spring Security Fundamentals (Servlet / Spring MVC).** Mục tiêu là chuyển từng yêu cầu sản phẩm thành một **quy tắc bảo mật có thể thực thi**, một hoặc nhiều **kiểm thử chứng minh** và một **cơ chế giám sát/vận hành**. Bài dùng Java 17+, Spring Boot 3.3.0 và Spring Security 6.x để minh họa. Đây là phiên bản cố định cho ví dụ học tập; sản phẩm thật phải chọn release được hỗ trợ và cập nhật bản vá.

## 1. Vì sao cần một bản đồ truy vết bảo mật?

“Chỉ nhân viên có quyền mới xem được tài liệu” là một ý định. Chưa thể xem nó là yêu cầu hoàn chỉnh nếu chưa trả lời: ai là nhân viên, quyền đến từ đâu, tài liệu thuộc tổ chức nào, quyền được kiểm tra ở lớp nào, test nào chứng minh việc ngăn truy cập chéo, và khi chính sách hỏng thì ai nhận cảnh báo.

Bản đồ bảo mật nối các tầng:

```text
Nhu cầu sản phẩm / user story
      ↓ làm rõ
Actor + Asset + Action + Context + Expected Decision
      ↓ phân tích
Threat / trust boundary / abuse case
      ↓ chọn
Authentication + Authorization + HTTP defenses + data invariants
      ↓ triển khai
Filter chain → Controller → Service policy → Repository / IdP
      ↓ kiểm thử
Allow tests + Deny tests + edge cases + concurrency cases
      ↓ vận hành
Audit + security events + metrics + alerts + runbook + owner
      ↓ bảo trì
Version upgrades + revocation + incident handling + release evidence
```

Nếu mỗi nhóm chỉ nhìn phần của mình, hệ thống dễ có tình trạng backend nghĩ frontend kiểm soát quyền, frontend nghĩ token đã đủ, còn vận hành không biết chính sách nào bị sai sau khi phát hành. Bản đồ khiến từng quan hệ được đặt tên, kiểm thử và có người chịu trách nhiệm.

**Nguyên tắc:** Một yêu cầu có thể cần nhiều cơ chế; một cơ chế có thể phục vụ nhiều yêu cầu. Ví dụ `SecurityFilterChain` có thể bảo vệ mọi API, nhưng quyền xem một bản ghi theo `ownerId` và `tenantId` vẫn cần policy riêng của ứng dụng.

## 2. Chọn một bài toán sản phẩm đủ cụ thể

Giả sử có hệ thống **Kho tài liệu doanh nghiệp** phục vụ nhiều tổ chức. Mỗi tài liệu có `id`, `tenantId` (tổ chức), `owner` (chủ sở hữu) và `state` (`DRAFT`/`APPROVED`). Người dùng được xác thực có thể có authority `ROLE_USER` hoặc `ROLE_APPROVER`. Membership giữa user và tổ chức được lưu do backend quản lý.

Quy tắc giả định:

- Anonymous chỉ được vào endpoint sức khỏe công khai.
- Người dùng có quyền xem tài liệu mình sở hữu khi vẫn thuộc tenant của tài liệu.
- Người duyệt được xem và phê duyệt tài liệu trong **tenant của mình**, không được vượt qua ranh giới tổ chức.
- Việc phê duyệt chỉ áp dụng với tài liệu đang ở trạng thái `DRAFT`.
- Mọi API khác mặc định bị từ chối.
- Request thay đổi trạng thái có biện pháp bảo vệ CSRF phù hợp loại client.
- Sự kiện phê duyệt và hành vi bị từ chối phải đủ dữ liệu để điều tra, nhưng không log credential hay nội dung tài liệu.
- Mỗi thay đổi quyền và nâng cấp Spring Security phải chạy lại bộ kiểm thử hồi quy.

Đó là **policy của sản phẩm giả định**, không phải khả năng Spring Security tự suy ra. Ví dụ sau dùng user và tài liệu trong bộ nhớ để dễ chạy; trong hệ thống thật cần nguồn identity, membership và dữ liệu bền vững.

## 3. Viết yêu cầu dưới dạng hợp đồng có thể kiểm chứng

Một yêu cầu an toàn nên có `ID`, actor, tài nguyên, hành động, dữ liệu đầu vào tin cậy, điều kiện, quyết định mặc định, HTTP behavior, log/audit, test và owner.

| ID | Yêu cầu sản phẩm | Điều kiện cho phép | Kết quả khi không thỏa |
| --- | --- | --- | --- |
| SEC-01 | `GET /public/health` công khai | Mọi chủ thể, chỉ trả `ok` | N/A; không lộ dữ liệu nhạy cảm. |
| SEC-02 | API tài liệu yêu cầu authentication | Credential hợp lệ | Với HTTP Basic: 401 nếu thiếu/sai credential. |
| SEC-03 | Chủ tài liệu được đọc bản ghi của mình | Đã xác thực; `owner=user`; membership cùng tenant | 403; không đọc được tài liệu khác. |
| SEC-04 | Người duyệt đọc tài liệu trong tenant | `ROLE_APPROVER` và membership cùng tenant | 403 nếu cross-tenant hoặc role không phù hợp. |
| SEC-05 | Người duyệt phê duyệt bản nháp | HTTP POST; `ROLE_APPROVER`; same tenant; `state=DRAFT` | 403 nếu không có quyền; khi trạng thái không hợp lệ cần hành vi API được quy định rõ. |
| SEC-06 | API chưa công bố mặc định bị chặn | Chỉ các rule đã công bố được thực thi | 403 với principal đã xác thực. |
| SEC-07 | POST phải đáp ứng chính sách CSRF | Có CSRF token hợp lệ trong mô hình demo | 403 nếu thiếu hoặc sai token. |
| SEC-08 | Có khả năng điều tra thao tác nhạy cảm | Sự kiện có actor, action, resource, time, result, request ID | Alert khi audit pipeline lỗi hoặc bất thường. |
| SEC-09 | Release không phá vỡ policy | CI + staging/canary chứng minh case allow/deny | Không phát hành nếu test/security gate thất bại. |

**HTTP status là một phần hợp đồng.** Trong HTTP Basic, unauthenticated thường là 401; authenticated nhưng thiếu quyền là 403. Form login có thể redirect 302. Resource không tồn tại có thể là 404, hoặc cố ý che sự tồn tại bằng 403/404 nhất quán. Xung đột trạng thái được quyền truy cập có thể là 409. Đừng suy luận mọi 403 đều do role: CSRF cũng có thể trả 403.

### Ví dụ biến yêu cầu mơ hồ thành điều kiện rõ

Yêu cầu ban đầu: “Manager xem được các hợp đồng liên quan.”

Cần làm rõ “liên quan” là `createdBy`, `department`, `owner`, `tenant`, `delegation` hay `assignedReviewer`. Ví dụ một quy tắc đã làm rõ:

```text
ALLOW READ(document) WHEN
    principal authenticated
    AND membership(principal, document.tenantId) active
    AND (document.owner == principal.name
         OR principal has APPROVER authority for that tenant)
ELSE DENY
```

Trong mã thực, `APPROVER` nên mang scope tổ chức hoặc được kết hợp với membership server-side. Không tin `tenantId`, `owner` hoặc `role` do browser tự khai là bằng chứng quyền.

## 4. Xác định tài sản, chủ thể và ranh giới tin cậy

Trước khi viết `@PreAuthorize`, hãy ghi lại:

| Hạng mục | Ví dụ | Hậu quả nếu đặt sai niềm tin |
| --- | --- | --- |
| Chủ thể | Alice, Bob, Reviewer, anonymous, machine client | User giả mạo hoặc client dùng identity không hợp lệ. |
| Tài sản | Nội dung tài liệu, tenant membership, approval state, audit log | Lộ dữ liệu hoặc thao tác nghiệp vụ trái phép. |
| Biên mạng | Browser → gateway → Spring MVC | Bỏ qua UI và gọi trực tiếp API. |
| Biên danh tính | Spring Security / IdP → `Authentication` | Tin role trong request body/header chưa xác minh. |
| Biên dữ liệu | Service → database/repository | IDOR/BOLA qua đổi ID trong URL; query không lọc tenant. |
| Biên vận hành | App → log collector / monitoring / audit storage | Log chứa token hoặc audit event bị mất, sửa/xóa. |

**Threat scenarios đáng kiểm thử:** anonymous mở route bảo vệ; user đổi ID tới tài liệu người khác; approver vượt tenant; POST approval thiếu CSRF; tài liệu vừa được chuyển `APPROVED` vẫn bị duyệt lại; member bị revoke vẫn giữ quyền do cache/token; route mới vô tình không có rule; một module khác gọi service và bỏ qua HTTP filter.

Test UI ẩn nút không chứng minh backend được bảo vệ. Một client độc hại có thể bỏ qua toàn bộ frontend, sửa path, query, HTTP method hoặc gửi request từ command line.

## 5. Phân biệt cơ chế framework và quy tắc ứng dụng

| Tầng | Thành phần có sẵn hoặc điểm mở rộng | Cần tự thiết kế theo sản phẩm |
| --- | --- | --- |
| Authentication | `AuthenticationManager`, providers, `UserDetailsService`, `PasswordEncoder`, OAuth2 Resource Server/OIDC client | Kho tài khoản, nguồn identity, account lifecycle, issuer/audience, MFA policy. |
| HTTP authorization | `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, `authenticated`, `hasRole` | Endpoint nào công khai, method nào đòi role nào, fallback policy. |
| Object authorization | `@EnableMethodSecurity`, `@PreAuthorize`, `AuthorizationManager` | Owner, tenant, delegation, state transition, field-level access. |
| HTTP protection | CSRF, security headers, session management, CORS integration | Client dùng cookie hay bearer, trusted origins, logout, revocation. |
| Data consistency | Spring transactions, JPA optimistic locking, DB constraints | Không thay đổi tài liệu khi policy vừa bị revoke; idempotency; audit outbox. |
| Operations | Security events, logging/metrics integration | Event schema, retention, SIEM, alert thresholds, on-call và runbook. |

Không phải mọi thành phần cần xây lại: dùng một IdP, gateway hoặc thư viện có thể an toàn và kinh tế hơn. Nhưng **chính sách nghiệp vụ và kiểm chứng tích hợp** vẫn do hệ thống chịu trách nhiệm.

### Hai lớp matcher thường bị nhầm

`http.securityMatcher("/api/**")` định nghĩa một `SecurityFilterChain` có nhận request hay không. `authorizeHttpRequests(auth -> auth.requestMatchers("/api/**")...)` định nghĩa rule **bên trong chain**. Khi có nhiều chain, chỉ chain đầu tiên khớp được chọn; request không khớp chain nào có thể đi ngoài các security filter, vì vậy cần fallback rõ ràng.

## 6. Bản đồ Requirement → Mechanism → Test → Evidence

| ID | Điểm thực thi | Positive test | Negative test | Evidence và owner |
| --- | --- | --- | --- | --- |
| SEC-01 | `permitAll()` cho `/public/**` | Anonymous `/public/health` 200 | Public response không có dữ liệu riêng | Synthetic health, application owner. |
| SEC-02 | HTTP Basic demo + `authenticated()` | Alice GET tài liệu 200 | Anonymous 401; credential sai 401 | 401 rate, Identity/SRE. |
| SEC-03 | `DocumentPolicy.canRead` ở service | Alice đọc tài liệu 101 | Alice đọc 103 cùng tenant khác owner 403; Bob đọc 101 cross-tenant 403 | Denied events, domain owner. |
| SEC-04 | Authority + membership tenant | Reviewer đọc 101 cùng tenant | Reviewer đọc 102 khác tenant 403 | Role grant/revoke audit, IAM owner. |
| SEC-05 | POST matcher + `canApprove` + state update | Reviewer phê duyệt 101 → 204 | USER 403; cross-tenant 403; already-approved từ chối | Approval audit + reconciliation, domain owner. |
| SEC-06 | `anyRequest().denyAll()` | Đúng route đã khai báo chạy | `/api/unlisted` 403 | Authorization deny rate, backend owner. |
| SEC-07 | CSRF bảo vệ POST | POST hợp lệ + `csrf()` đi tiếp | POST thiếu CSRF 403 | CSRF failure rate, client/security owner. |
| SEC-08 | Audit/outbox/central logging do sản phẩm triển khai | Audit event sau transaction commit | Test thiếu event, trùng event, log secret | Audit pipeline health, Security Ops. |
| SEC-09 | CI/staging/canary và release gates | Bằng chứng test pass | Chặn merge/deploy nếu fail | Build evidence, Release/SRE. |

Bảng cần được **duy trì như hợp đồng**. Khi một policy đổi, phải tìm đúng test và alert chịu ảnh hưởng. Với SEC-08/SEC-09, ví dụ Java phía dưới **chưa triển khai audit pipeline hoặc deployment pipeline**; đó là phần cần bổ sung theo kiến trúc production, không được đánh dấu pass chỉ vì có MockMvc.

## 7. Một ứng dụng Spring Security chạy được theo các yêu cầu

Ví dụ nhỏ dùng Java 17, Maven, Spring Boot 3.3.0, Spring Security 6.x. Dữ liệu người dùng/tenant/tài liệu ở bộ nhớ để người học có thể tự chạy trên máy. Đường authentication chọn HTTP Basic để dễ quan sát 401/403, không phải khuyến nghị dùng password demo cho production.

### 7.1. Cấu trúc thư mục

```text
security-map-demo/
├── pom.xml
└── src/
    ├── main/java/example/securitymap/
    │   ├── SecurityMapApplication.java
    │   ├── SecurityConfig.java
    │   ├── ActorDirectory.java
    │   ├── DocumentStore.java
    │   ├── DocumentPolicy.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/example/securitymap/
        └── SecurityMapTest.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>security-map-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/securitymap/SecurityMapApplication.java`:

```java
package example.securitymap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityMapApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityMapApplication.class, args);
    }
}
```

### 7.2. SecurityFilterChain — route authentication và phân quyền mức HTTP

`src/main/java/example/securitymap/SecurityConfig.java`:

```java
package example.securitymap;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasRole("APPROVER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER").build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("USER").build(),
            User.withUsername("reviewer")
                .password(encoder.encode("reviewer-pass"))
                .roles("APPROVER").build()
        );
    }
}
```

`@EnableMethodSecurity` kích hoạt kiểm soát ở service. Rule GET bảo đảm xác thực, nhưng chưa khẳng định được xem ID bất kỳ. Rule POST yêu cầu `ROLE_APPROVER`; với `hasRole("APPROVER")`, Spring Security thêm tiền tố `ROLE_` theo quy ước mặc định.

`anyRequest().denyAll()` giữ các URL không được liệt kê trong trạng thái bị từ chối. Nếu có endpoint health/readiness khác, cần quyết định rõ nó ở public hay protected; không mở `/actuator/**` đại trà do thói quen.

Ví dụ cố ý **không tắt CSRF**: Spring Security mặc định bảo vệ những HTTP method thay đổi trạng thái như POST. Trong test authorization POST sẽ gắn `.with(csrf())`, còn một test riêng chứng minh thiếu CSRF bị chặn.

### 7.3. Membership chỉ được lấy từ nguồn do backend tin cậy

`src/main/java/example/securitymap/ActorDirectory.java`:

```java
package example.securitymap;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class ActorDirectory {
    private final Map<String, String> tenants = Map.of(
        "alice", "org-a",
        "bob", "org-b",
        "reviewer", "org-a"
    );

    public boolean isMember(String username, String tenantId) {
        return tenantId != null
            && tenantId.equals(tenants.get(username));
    }
}
```

Đây là mock dữ liệu membership để người học hiểu điều kiện `sameTenant`. Hệ thống thật lưu trong DB/IdP và có quy trình cấp, thu hồi, hiệu lực, cache invalidation; **không** nhận `tenantId` do frontend tự gửi làm điều kiện cấp quyền.

### 7.4. Tài liệu và chuyển trạng thái

`src/main/java/example/securitymap/DocumentStore.java`:

```java
package example.securitymap;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class DocumentStore {

    public record Document(long id, String tenantId,
                           String owner, String state) {}

    private final Map<Long, Document> records = new ConcurrentHashMap<>();

    public DocumentStore() {
        reset();
    }

    void reset() {
        records.clear();
        records.put(101L, new Document(101L, "org-a", "alice", "DRAFT"));
        records.put(102L, new Document(102L, "org-b", "bob", "DRAFT"));
        records.put(103L, new Document(103L, "org-a", "carol", "DRAFT"));
    }

    public Optional<Document> find(Long id) {
        return Optional.ofNullable(records.get(id));
    }

    public synchronized void approve(Long id) {
        Document doc = records.get(id);
        if (doc == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        if (!"DRAFT".equals(doc.state())) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT, "Already approved");
        }
        records.put(id, new Document(
            doc.id(), doc.tenantId(), doc.owner(), "APPROVED"));
    }
}
```

Việc đồng bộ hóa này chỉ có ý nghĩa trong **một instance JVM**. Nếu hệ chạy nhiều instance, dùng transaction, version/optimistic locking hoặc cập nhật có điều kiện ở DB; cần thiết kế audit theo commit thực. Không dùng `ConcurrentHashMap` làm kho tài liệu production.

### 7.5. Policy kiểm tra owner, role, tenant và trạng thái

`src/main/java/example/securitymap/DocumentPolicy.java`:

```java
package example.securitymap;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentStore documents;
    private final ActorDirectory directory;

    public DocumentPolicy(DocumentStore documents, ActorDirectory directory) {
        this.documents = documents;
        this.directory = directory;
    }

    public boolean canRead(Authentication authentication, Long id) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        return documents.find(id)
            .filter(doc -> directory.isMember(
                authentication.getName(), doc.tenantId()))
            .filter(doc -> doc.owner().equals(authentication.getName())
                || has(authentication, "ROLE_APPROVER"))
            .isPresent();
    }

    public boolean canApprove(Authentication authentication, Long id) {
        if (authentication == null || !authentication.isAuthenticated()
                || !has(authentication, "ROLE_APPROVER")) {
            return false;
        }

        return documents.find(id)
            .filter(doc -> directory.isMember(
                authentication.getName(), doc.tenantId()))
            .filter(doc -> "DRAFT".equals(doc.state()))
            .isPresent();
    }

    private boolean has(Authentication authentication, String authority) {
        return authentication.getAuthorities().stream()
            .anyMatch(a -> authority.equals(a.getAuthority()));
    }
}
```

Alice đọc 101 được vì là owner cùng org-a, nhưng **không** đọc 103 của Carol dù cùng tenant. Bob ở org-b không đọc 101. Reviewer là approver org-a nên có thể đọc và phê duyệt 101/103, nhưng **không** được làm vậy với document 102 thuộc org-b.

Với ID không tồn tại, hàm policy trả false; request đã xác thực sẽ nhận 403 trong ví dụ. Policy này vô tình không để lộ sự tồn tại của tài liệu qua khác biệt giữa ID có/không có quyền, nhưng API production phải xác định rõ có cố ý che 404/403 hay không.

### 7.6. Service thực thi method security

`src/main/java/example/securitymap/DocumentService.java`:

```java
package example.securitymap;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {
    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
    public DocumentStore.Document read(Long id) {
        return store.find(id).orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PreAuthorize("@documentPolicy.canApprove(authentication, #p0)")
    public void approve(Long id) {
        store.approve(id);
    }
}
```

`#p0` trỏ tới tham số thứ nhất, tránh lệ thuộc tên parameter khi compile. `@PreAuthorize` được áp dụng khi một thành phần khác gọi qua Spring proxy, như Controller ở dưới. Nếu phương thức trong cùng bean tự gọi một phương thức annotate khác, **self-invocation** có thể bỏ qua method interceptor. Cần bảo vệ mọi entry point (HTTP, scheduled job, message consumer, batch) phù hợp và không chỉ dựa vào rule ở controller.

### 7.7. Controller

`src/main/java/example/securitymap/DocumentController.java`:

```java
package example.securitymap;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/api/documents/{id}")
    public DocumentStore.Document read(@PathVariable Long id) {
        return service.read(id);
    }

    @PostMapping("/api/documents/{id}/approve")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void approve(@PathVariable Long id) {
        service.approve(id);
    }
}
```

Ứng dụng demo trả bản ghi Java `record` trực tiếp vì dữ liệu có phạm vi minh họa; sản phẩm thật cần DTO, phân loại field nhạy cảm và field-level authorization. Không trả password hash, access token hoặc toàn bộ entity tài khoản ra client.

## 8. MockMvc: kiểm thử hai chiều cho từng quyền

Tạo `src/test/java/example/securitymap/SecurityMapTest.java`:

```java
package example.securitymap;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityMapTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentStore documents;

    @BeforeEach
    void resetState() {
        documents.reset();
    }

    @Test
    void publicHealth_SEC01() throws Exception {
        mvc.perform(get("/public/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void anonymousCannotRead_SEC02() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceOwnDocument_SEC03() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.owner").value("alice"));
    }

    @Test
    void aliceDifferentOwnerSameTenant_SEC03() throws Exception {
        mvc.perform(get("/api/documents/103")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bobCannotCrossTenant_SEC03() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void reviewerCanReadOwnTenant_SEC04() throws Exception {
        mvc.perform(get("/api/documents/101")
                .with(httpBasic("reviewer", "reviewer-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void reviewerCannotReadAnotherTenant_SEC04() throws Exception {
        mvc.perform(get("/api/documents/102")
                .with(httpBasic("reviewer", "reviewer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryUserCannotApprove_SEC05() throws Exception {
        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void reviewerCannotApproveOtherTenant_SEC05() throws Exception {
        mvc.perform(post("/api/documents/102/approve")
                .with(httpBasic("reviewer", "reviewer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void reviewerApprovesDraft_SEC05() throws Exception {
        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("reviewer", "reviewer-pass"))
                .with(csrf()))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("APPROVED"));
    }

    @Test
    void repeatedApprovalIsRejected_SEC05() throws Exception {
        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("reviewer", "reviewer-pass"))
                .with(csrf()))
            .andExpect(status().isNoContent());

        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("reviewer", "reviewer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownRouteDenied_SEC06() throws Exception {
        mvc.perform(get("/api/unlisted")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfRequiredForPost_SEC07() throws Exception {
        mvc.perform(post("/api/documents/101/approve")
                .with(httpBasic("reviewer", "reviewer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invisibleIdDoesNotLeakDocument_SEC03() throws Exception {
        mvc.perform(get("/api/documents/999")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Đây là **14 test methods** cho SEC-01..SEC-07; tất cả có kết quả dự kiến là pass với source được trình bày. Đây không phải báo cáo Maven đã thực thi trong quá trình biên soạn nội dung. Các test được gắn mã yêu cầu trong tên để việc đọc kết quả và truy vết trở nên trực tiếp.

**Điểm quan trọng về CSRF:** Khi muốn kiểm tra permission của HTTP POST, test phải cung cấp `.with(csrf())` hợp lệ. Nếu bỏ token, response 403 có thể do CSRF chặn request **trước khi** policy được chạy, khiến một bài test tưởng là kiểm tra role/tenant nhưng thực tế chẳng chứng minh được gì về role/tenant.

Bộ test kiểm chứng cả: allow owner, deny other owner, deny cross-tenant, allow approver same tenant, deny approver cross-tenant, deny role thấp, deny request không token, deny URL chưa được khai báo và mutation sau approve.

### 8.1. Chạy và quan sát

Trong thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
java -version
mvn test
mvn spring-boot:run
```

Tại một terminal khác, khi ứng dụng dùng cổng mặc định 8080:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/health
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/documents/101
curl -s -o /dev/null -w '%{http_code}\n' -u alice:alice-pass http://localhost:8080/api/documents/101
curl -s -o /dev/null -w '%{http_code}\n' -u bob:bob-pass http://localhost:8080/api/documents/101
curl -s -o /dev/null -w '%{http_code}\n' -u reviewer:reviewer-pass http://localhost:8080/api/documents/101
```

Expected stdout cho **năm lệnh `curl`**:

```text
200
401
200
403
200
```

Trên Windows PowerShell, dùng `curl.exe` và đích `NUL` thay cho `/dev/null`. Ví dụ GET ở đây không cần CSRF token. Với POST, dùng MockMvc test hoặc client triển khai cơ chế lấy/gửi CSRF token đúng; không gửi HTTP Basic không token rồi suy luận 403 là do role.

## 9. Test bản đồ ở các tầng ngoài HTTP

MockMvc chứng minh Spring filters và service policy có phối hợp trong một ứng dụng. Một sản phẩm thật còn cần test bổ sung:

| Tầng kiểm thử | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Unit policy | Rule theo `owner/tenant/role/state` độc lập HTTP | Matrix 2 tenant × 3 role × 2 state; default deny. |
| Integration với DB | Truy vấn tenant-scoped, lock, transaction, rollback | Reviewer đổi trạng thái và có request khác cùng lúc; chỉ một approval thành công. |
| Authentication integration | IdP/JWT/session/provider thực | Token hết hạn, sai issuer/audience, user disabled, account revoked. |
| API contract | Status/body/header/redirect đúng với client | 200/401/403/404/409 theo hợp đồng, `WWW-Authenticate`, JSON errors. |
| Abuse/security | Bypass bằng URL/method/ID/header | BOLA, IDOR, field-level access, mass assignment, tenant spoofing. |
| Resilience | Khi DB, IdP, cache hoặc audit pipeline lỗi | Hệ từ chối an toàn, có alert, không mở bypass demo. |
| E2E | UI, backend, IdP, gateway cùng thỏa policy | Login → truy cập đúng dữ liệu → phê duyệt → audit event. |

Ví dụ `@PreAuthorize` chạy qua Spring proxy, nên test chỉ gọi thẳng `DocumentPolicy.canRead()` chưa chứng minh method interceptor được áp dụng. Test controller/service thực qua MockMvc sẽ phát hiện nhiều lỗi cấu hình này hơn.

Với dữ liệu nhiều tenant, luôn test khả năng **truy cập chéo theo ID**; một rule HTTP `authenticated()` không ngăn BOLA nếu service/repository không kiểm tra tenant. Kết hợp policy ở service với query giới hạn tenant hoặc row-level controls tùy kiến trúc.

## 10. Bản đồ test có cả bằng chứng “cho phép” và “từ chối”

Một suite tốt không dùng cách duy nhất “request hợp lệ được 200”. Với mỗi quyền, đặt test âm ngay bên cạnh test dương để thấy khi nào chính sách bị mở quá rộng:

```gherkin
Feature: Tenant-safe document approval

  Scenario: Allowed approval in the same tenant
    Given reviewer has APPROVER authority in org-a
    And document 101 belongs to org-a and is DRAFT
    When reviewer sends POST /api/documents/101/approve with CSRF
    Then the API responds 204
    And document 101 becomes APPROVED

  Scenario: Cross-tenant approval is denied
    Given reviewer has APPROVER authority in org-a
    And document 102 belongs to org-b and is DRAFT
    When reviewer sends POST /api/documents/102/approve with CSRF
    Then the API responds 403
    And document 102 remains DRAFT
```

Đây là đặc tả Gherkin để thảo luận acceptance criteria, không phải Java code chạy độc lập. Nếu cần BDD framework, phải nối các step tới HTTP/test data và assert trạng thái thực.

Mỗi test cần kiểm chứng **hành vi quan sát được**, không chỉ gọi lại cùng một hàm `boolean` của implementation. Với approval, phải đọc state sau request; với denied, nên kiểm tra state **không đổi** bằng database/repository trong integration suite thực.

## 11. Vận hành: sự kiện audit và security logging

Có ba loại tín hiệu khác nhau:

1. **Application logs:** stack trace, dependency timeout, request latency; giúp tìm lỗi kỹ thuật.
2. **Security events:** login thất bại, access denied, thay đổi quyền, nghi ngờ bypass hoặc CSRF; giúp phát hiện và phân tích bảo mật.
3. **Business audit trail:** ai đã phê duyệt tài liệu nào, tại thời điểm nào, kết quả cuối cùng sau transaction commit; dùng cho điều tra, kiểm toán và giải trình.

### Định nghĩa event schema tối thiểu

```json
{
  "timestamp": "2026-01-15T09:45:10Z",
  "eventType": "DOCUMENT_APPROVAL",
  "actorId": "user-42",
  "tenantId": "org-a",
  "action": "APPROVE",
  "resourceType": "DOCUMENT",
  "resourceRef": "101",
  "decision": "ALLOW",
  "result": "COMMITTED",
  "requestId": "trace-8f23",
  "policyVersion": "document-policy-v1"
}
```

Đây là **event minh họa**, chưa được code demo tự ghi. Không log mật khẩu, `Authorization` header, access token, cookie, nội dung tài liệu hoặc thông tin cá nhân không cần thiết. Gắn thời gian UTC/offset và request/trace ID để nối các lớp.

Một event ghi `result=COMMITTED` chỉ được coi là đúng nếu mutation đã commit. Có thể dùng **transactional outbox** để ghi dữ liệu + sự kiện trong cùng transaction, rồi phát ra hệ xử lý sự kiện; consumer nên xử lý idempotently. `logger.info` trước khi DB commit **không** bảo đảm audit trail phản ánh trạng thái cuối cùng. Vận hành phải có retention, quyền truy cập, bảo vệ sửa/xóa log, kênh truyền an toàn và khả năng truy xuất evidence.

### Đo lường và phát hiện

| Metric/event | Điều gì có thể xảy ra | Cần phân tích thêm |
| --- | --- | --- |
| 401 tăng đột biến | Credentials sai, user store/IdP lỗi, client hết session/token | Phân nhóm theo authentication mechanism, endpoint, release. |
| 403 authorization tăng | Role/membership sai, matcher thay đổi, chính sách mới | Phân loại denial reason; tách khỏi CSRF. |
| 403 CSRF tăng | SPA/client ngừng gửi token, cookie/session không phù hợp | Kiểm tra method, CSRF repository, client changes. |
| Cross-tenant denial bất thường | Lỗi client, dò ID, tấn công hoặc lệch membership | Kiểm tra bằng request ID và audit có kiểm soát. |
| Approval conflict tăng | Race hoặc người dùng lặp thao tác | Kiểm tra transaction, optimistic lock và idempotency. |
| Audit pipeline lag/drop | Bằng chứng bị chậm hoặc mất | Outbox backlog, retry/dead-letter và alert. |
| Privilege changes | Vai trò bị cấp hoặc revoke | Kiểm tra người phê duyệt, lý do, hiệu lực, session/token invalidation. |

Đừng đặt ngưỡng tùy tiện như “403 > 10 mỗi phút là tấn công” nếu không có baseline; hệ nhiều client/tenant có tải khác nhau. Đừng đưa username hoặc document ID vào metrics label có cardinality cao; dùng route template, outcome/reason code và phân nhóm an toàn.

## 12. Runbook minh họa: 403 tăng sau khi deploy

1. Xác định app version và thời điểm deploy, so với baseline 401/403/CSRF đã có.
2. Tách các 403 do CSRF, role, tenant, policy state và các lỗi khác. Không gọi tất cả là “đăng nhập sai”.
3. Đọc security event bằng `requestId`; kiểm tra principal và authorities được xác thực ở runtime, không tin dữ liệu raw từ client.
4. Xác minh membership owner/tenant, trạng thái tài liệu, cache invalidation, revoke và độ trễ đồng bộ dữ liệu.
5. Chạy lại synthetic/canary test cho allow lẫn deny; so sánh config matchers giữa version cũ/mới.
6. Nếu nghi ngờ bypass hoặc lộ dữ liệu, kích hoạt incident response, bảo toàn logs và audit evidence, giảm phạm vi quyền truy cập.
7. Nếu lỗi do migration, rollback hoặc sửa policy theo quy trình có người phê duyệt; **không** mở `permitAll()` để làm 403 giảm.
8. Bổ sung regression test và cập nhật requirement map để lỗi tương tự được phát hiện trước lần deploy sau.

**Fail closed:** Khi không có dữ liệu đáng tin để quyết định tenant/owner, không mặc định cấp quyền. Tuy nhiên dependency outage có thể được phản hồi bằng 5xx thích hợp thay vì giả vờ 403. API contract, retry, availability và phản ứng sự cố phải được thiết kế rõ.

## 13. Nâng cấp Spring Security mà không làm mất ngữ nghĩa chính sách

Nhu cầu “Bob không xem được tài liệu Alice” là invariant của nghiệp vụ. Cách cấu hình Spring Security thay đổi theo phiên bản:

- Spring Security 5.x từng dùng `WebSecurityConfigurerAdapter` và các matcher `antMatchers`/ `mvcMatchers` cũ.
- Spring Security 6.x dùng `SecurityFilterChain` bean và `authorizeHttpRequests`/Lambda DSL. Đoạn code trong bài dùng nhánh này.
- Khi chuẩn bị Spring Security 7, cần đối chiếu Lambda DSL bắt buộc, `PathPatternRequestMatcher` và các thay đổi matcher/extension API; không chỉ thay tên method.
- Nếu ứng dụng dùng Servlet và WebFlux ở các module khác nhau, phải chọn đúng `SecurityFilterChain` so với `SecurityWebFilterChain`.

Checklist nâng version: pin dependency thực → đọc migration guide → xác định cơ chế bị tác động → chạy case allow/deny → so CSRF/session/redirect/status → test matchers với path encoding, servlet path, trailing slash, HTTP method → triển khai canary → theo dõi audit và 401/403 → cập nhật evidence.

Nếu đổi từ `web.ignoring()` sang `permitAll()`, hiểu sự khác biệt: `ignoring` bỏ qua Spring Security filter chain, trong khi `permitAll` vẫn cho các filter (security headers, v.v.) hoạt động. Chỉ đổi khi biết rõ hiệu ứng.

## 14. Các khoảng trống cần đóng trước production

Ví dụ in-memory cố ý **không** giải quyết toàn bộ SEC-08/09. Đừng copy demo lên production rồi đánh dấu “bảo mật xong”. Hệ thật cần:

- **Nguồn danh tính:** IdP/user store, MFA, mật khẩu được hash, account lifecycle, khóa/hủy quyền và secret management.
- **Nguồn membership:** bảng quyền theo tenant, cập nhật/revoke có kiểm soát, cache invalidation, không tin header client.
- **Data authorization:** database query giới hạn tenant, kiểm tra owner, kiểm soát các trường nhạy cảm và export/batch jobs.
- **Consistency:** transaction, optimistic lock, concurrency test, idempotent approval và trạng thái hợp lệ.
- **Audit:** bản ghi sau commit, outbox/retry/reconciliation, retention và phân quyền xem log.
- **API trust model:** TLS, session/token lifetime, CSRF/CORS theo client, issuer/audience của JWT nếu dùng Bearer.
- **Operations:** dashboard, alerts, on-call, runbooks, dependency health, rollback và incident response.
- **Evidence:** CI run thực, staging/canary output, OWASP ASVS kiểm tra phù hợp mức rủi ro.

Các quyết định trên phải được điền thành công việc có owner. Ví dụ `SEC-08 audit pipeline = NOT IMPLEMENTED` là trạng thái đúng cho dự án demo; ghi `PASS` khi chưa có sự kiện và test audit là sai về quản trị chất lượng.

## 15. Mẫu YAML theo dõi một security requirement

```yaml
id: SEC-05
title: "Phê duyệt tài liệu DRAFT trong cùng tenant"
actor: "authenticated ROLE_APPROVER"
resource: "DOCUMENT"
action: "POST /api/documents/{id}/approve"
policy: "sameTenant AND state == DRAFT AND has ROLE_APPROVER"
decision_inputs:
  - "Authentication.principal"
  - "Authentication.authorities"
  - "document.tenantId"
  - "membership.tenantId"
  - "document.state"
controls:
  - "HTTP POST route requires APPROVER"
  - "DocumentPolicy.canApprove in method security"
  - "CSRF protection appropriate to client"
  - "Transactional state change in database"
positive_tests:
  - "same-tenant approver + DRAFT + CSRF => 204"
negative_tests:
  - "USER => 403"
  - "cross-tenant approver => 403"
  - "POST without CSRF => 403"
  - "not DRAFT => reject by API contract"
operational_evidence:
  - "DOCUMENT_APPROVAL audit event after commit"
  - "denied/failed counts and requestId correlation"
  - "approval conflict dashboard and runbook"
owners:
  policy: "document-domain team"
  identity: "identity team"
  operations: "on-call team"
verification:
  code_review: "link to review in actual project"
  ci_tests: "link to actual CI execution"
  audit_test: "link to actual audit verification"
  status: "pending until evidence is attached"
```

Các giá trị `owners` và `verification` là **mẫu điền**, không phải người/nhóm thật hay kết quả đã được xác minh. Nên lưu bản đồ cạnh thiết kế hoặc backlog, review khi quyền/tenant/IdP thay đổi và giữ liên kết tới test chạy thật.

## 16. Checklist nghiệm thu

**Yêu cầu:** Mỗi rule có ID, actor, tài sản, hành động, tenant scope, dữ liệu đáng tin, expected allow/deny và API status; những điều chưa rõ được làm rõ với domain owner.

**Triển khai:** Có `SecurityFilterChain` đúng stack/version; rule cụ thể đứng trước fallback; kiểm tra quyền tài nguyên ở backend; CSRF/session/CORS/TLS theo threat model; không hard-code quyền từ client; kiểm soát race và self-invocation.

**Kiểm thử:** Có cả test dương và âm; có anonymous, role thấp, role đúng, cross-tenant, khác owner, sai state, CSRF, URL không khai báo, method khác và user/token bị revoke; test data không làm lộ thông tin thật.

**Vận hành:** Event audit có actor/action/result/time/requestId; không log secret; metrics/alerts tách 401 với 403 do CSRF và authorization; runbook và on-call được đặt rõ; có rollback/security incident process.

**Quản lý phiên bản:** Pin dependency/JDK; đối chiếu Spring Security release notes; chạy regression tests/canary; evidence được gắn vào từng requirement trước khi đánh dấu hoàn tất.

## 17. Nguồn học và chuẩn tham chiếu

- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security — HTTP Basic tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Migration guidance: https://docs.spring.io/spring-security/reference/migration/
- OWASP ASVS 5.0 (đặc biệt các phần Authorization và Security Logging): https://asvs.owasp.org/

**Kết quả cần đạt:** khi người quản lý sản phẩm nêu một quyền hay yêu cầu mới, bạn có thể chứng minh chuỗi hoàn chỉnh **Requirement → Threat → Control → Code → Positive/Negative Test → Audit/Metric/Alert → Owner/Release Evidence**. “Đã cấu hình Spring Security” chỉ là một phần của bản đồ; chính sách nghiệp vụ và bảo đảm sau phát hành là phần còn lại.
