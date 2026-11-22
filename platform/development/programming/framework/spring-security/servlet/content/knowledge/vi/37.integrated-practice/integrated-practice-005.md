# Phân quyền theo chủ sở hữu và tổ chức ở cả HTTP lẫn tầng dịch vụ

**Phạm vi:** bài thực hành tổng hợp **Spring Security Servlet/Spring MVC**, Java 17+, Spring Boot 3.x, Spring Security 6.x. Mục tiêu là bảo vệ dữ liệu theo **chủ sở hữu (owner)** và **tổ chức/tenant (organization)** ở **hai biên**: HTTP endpoint và phương thức dịch vụ. Bài dùng một ứng dụng quản lý tài liệu nhỏ, có code Java, security configuration, MockMvc/integration tests, ca tấn công IDOR/BOLA, lưu ý transaction/TOCTOU, vận hành nhiều tenant và checklist kiểm thử.

**Bài toán:** người dùng Alice thuộc tổ chức `acme`, tạo tài liệu `doc-a`. Bob cũng thuộc `acme` nhưng **không phải chủ sở hữu**; Carol thuộc `zen`. Tài khoản `auditor` là người kiểm toán của `acme`, có thể **xem** tài liệu của thành viên acme nhưng **không được sửa** tài liệu không thuộc mình. Ứng dụng phải chặn Bob xem/sửa `doc-a`, chặn Carol vượt ranh giới tenant, cho Alice xem/sửa tài liệu của mình và cho auditor chỉ đọc trong tổ chức được cấp quyền. **Không được tin** các trường owner/organization do client tự khai báo nếu chúng chưa được xác thực.

## 1. Tại sao .authenticated() hay .hasRole("USER") chưa đủ?

Một `SecurityFilterChain` chỉ có:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/docs/**").authenticated()
    .anyRequest().denyAll()
)
```

chặn người chưa đăng nhập, nhưng **bất kỳ tài khoản đã đăng nhập nào** cũng có thể thử:

```http
GET /api/docs/doc-a HTTP/1.1
Authorization: Basic ...
```

Nếu controller đọc `repository.findById("doc-a")` rồi trả luôn dữ liệu, Bob có thể đọc tài liệu Alice dù Bob không được cấp quyền. Đây là dạng **Broken Object Level Authorization (BOLA)**, thường được gọi **Insecure Direct Object Reference (IDOR)** khi client sửa ID để truy cập object khác.

Tương tự, chỉ kiểm tra `ROLE_ADMIN` có thể sai trong ứng dụng đa tổ chức: Alice là admin tổ chức A **không nhất thiết** là admin tổ chức B. Một quyền như `ORG_AUDITOR` hoặc `ORG_ADMIN` cần được gắn với **org cụ thể**, không phải boolean “admin toàn hệ thống” không có scope.

### 1.1 Các điều kiện phải đúng đồng thời

Với một yêu cầu **đọc** tài liệu, policy ví dụ là:

```text
Được đọc nếu và chỉ nếu:
    (1) Actor đã xác thực
AND (2) Actor là thành viên của org được yêu cầu
AND (3) Tài liệu thực sự thuộc org đó
AND (4) (
         Actor là chủ sở hữu tài liệu
         OR Actor có quyền auditor của chính org đó
        )
```

Với yêu cầu **sửa** tài liệu:

```text
Được sửa nếu và chỉ nếu:
    (1) Actor đã xác thực
AND (2) Actor là thành viên của org được yêu cầu
AND (3) Tài liệu thực sự thuộc org đó
AND (4) Actor là chủ sở hữu tài liệu
```

Bài cố ý không cho auditor sửa tài liệu người khác để thấy rằng **read** và **edit** là hai quyền khác nhau. Production có thể có vai trò org admin với quyền sửa/duyệt đặc biệt, nhưng điều đó phải nằm trong **policy đã được xác định và test**, không phải do nhìn thấy chuỗi role có chữ `ADMIN` mà mặc định cấp toàn quyền.

### 1.2 Bảng quyết định mong đợi

| Actor | Tài liệu | Org trong URL | Đọc | Sửa | Lý do |
| --- | --- | --- | --- | --- | --- |
| alice | doc-a (owner alice, org acme) | acme | Cho phép | Cho phép | Đúng tổ chức và chủ sở hữu. |
| bob | doc-a | acme | Từ chối | Từ chối | Cùng tổ chức nhưng không phải owner/auditor. |
| auditor | doc-a | acme | Cho phép | Từ chối | Auditor của acme chỉ được đọc. |
| carol | doc-a | acme | Từ chối | Từ chối | Không là thành viên acme. |
| carol | doc-c (owner carol, org zen) | zen | Cho phép | Cho phép | Owner thuộc đúng tổ chức. |
| alice | doc-a | zen | Từ chối | Từ chối | URL org khác org thật của object. |
| auditor | doc-c | zen | Từ chối | Từ chối | Chỉ có vai trò auditor ở acme. |
| anonymous | doc-a | acme | Từ chối | Từ chối | Chưa được xác thực. |

**Điểm cốt lõi:** cả `orgId` lẫn `docId` trong URL là **đầu vào do caller điều khiển**, không phải bằng chứng về quyền. Server phải kiểm tra chúng đối với **nguồn dữ liệu đáng tin** của membership và document.

## 2. Tại sao phải bảo vệ cả HTTP và service?

Một request có thể đi qua nhiều đường:

```text
Internet / Browser / API client
                 │
                 ▼
Spring Security Servlet FilterChain
  - Authenticate principal qua Basic/OIDC/JWT/etc.
  - Kiểm tra HTTP method và request path
  - AuthorizationManager: actor + org + document + action
                 │
                 ▼
Spring MVC Controller
  - Parse path/body
  - Không tự nhận role/owner từ header JSON
                 │
                 ▼
Spring Service (Spring-managed proxy)
  - @PreAuthorize + DocumentPolicy
  - Kiểm tra lại org, owner và action
                 │
                 ▼
Repository / Database
  - Query theo doc_id + org_id
  - Atomic update/transaction với điều kiện ownership
```

**Biên HTTP** ngăn request không được phép **trước khi controller xử lý**. Nó còn phân biệt HTTP method, path, lỗi chưa login và hành vi CSRF/session. **Biên service** bảo vệ khi cùng logic được gọi từ **một controller mới, scheduled job, queue consumer, GraphQL resolver, batch import hoặc một service khác** không đi qua URL đã được bảo vệ. Nếu chỉ kiểm tra ở HTTP, một lời gọi nội bộ có thể bỏ qua quy tắc owner/tenant.

Trong bài thực hành, **HTTP và service đều dùng cùng `DocumentPolicy`**, nên quyết định đọc/sửa nhất quán. Đổi lại có thể phải **đọc repository hai lần**: một lần ở `AuthorizationManager`, một lần ở `@PreAuthorize`. Với dữ liệu thật cần xem transaction, cache hoặc bố trí coarse-grained HTTP rule + fine-grained service rule để tối ưu, **nhưng không được bỏ kiểm tra đối tượng ở tầng dữ liệu**.

### 2.1 Actor, resource, action và context

Một mô hình policy rõ ràng cần:

- **Actor:** danh tính được Spring Security xác thực (`Authentication.getName()` hoặc account ID bất biến); không tin `X-User` tùy ý.
- **Resource:** tài liệu lấy từ repository, gồm `id`, `orgId`, `ownerId`; các trường này phải đến từ server/database.
- **Action:** `READ` hay `EDIT`; không dùng một quyền chung cho mọi phương thức.
- **Context:** active membership, org-scoped auditor/admin role, trạng thái resource, tenant access policy, có thể thêm thời gian và audit conditions.

Nếu hệ thống thật có user ID bất biến, dùng **account ID** trong policy thay cho username có thể đổi hoặc trùng giữa các tenant. Ví dụ demo dùng username để code ngắn và dễ test; **không** coi username là định danh bền vững cho production.

## 3. Thiết kế dữ liệu và invariants trước khi viết code

Mô hình tài liệu tối thiểu:

| Trường | Ý nghĩa | Ai được quyền xác định |
| --- | --- | --- |
| `id` | ID tài liệu không cần đoán được | Server/repository; có unique constraint. |
| `orgId` | Tổ chức thực sự sở hữu dữ liệu | Backend kiểm chứng từ membership/organization. |
| `ownerId` | Chủ sở hữu hiện tại | Backend từ principal đã xác thực và quy trình chuyển quyền hợp lệ. |
| `body` | Nội dung tài liệu | Owner được phép sửa theo policy. |
| `status` | Draft/archived/locked nếu có | Business policy, không chỉ dựa role. |

Một bảng production có thể có `documents(id, org_id, owner_id, body, version, status)`, `organization_memberships(account_id, org_id, status, role)`. Membership có thể bị thu hồi bất kỳ lúc nào; policy phải dùng **trạng thái mới đủ tin cậy**, không chỉ claim dài hạn phát trong JWT từ nhiều giờ trước nếu yêu cầu thu hồi tức thì.

**Invariants:**

1. `docId` chỉ định object; **không** tự cấp quyền đọc object đó.
2. `orgId` trong route chỉ được dùng làm **điều kiện lọc**; phải đối chiếu `document.orgId` thật.
3. `ownerId` phải được backend xác minh với actor, không lấy từ request body không kiểm soát.
4. Quyền auditor/admin phải có **scope tổ chức**, không suy rộng toàn hệ thống.
5. Policy **deny on missing**: thiếu actor, org, doc, membership hoặc dữ liệu lạ thì không tự grant.
6. Lời gọi service trực tiếp cũng phải bị chặn.
7. Update production phải kiểm tra quyền sát thời điểm ghi để tránh TOCTOU.

## 4. Tạo project Spring Boot 3 và dependencies

Tạo project Gradle bằng Spring Initializr với Java 17+, Spring Boot 3.x, **Spring Web**, **Spring Security**, **Spring Boot Starter Test**. Thêm `spring-security-test`. Các file Java đặt trong package `com.example.tenancy`.

**`build.gradle` — phần dependencies:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Giữ lại plugins và repositories do Spring Initializr tạo; Spring Boot BOM quản lý phiên bản Spring Security tương thích. Ví dụ dùng **HTTP Basic + InMemoryUserDetailsManager** để tập trung vào authorization, **không** phải thiết kế login production. Password `{noop}` chỉ phục vụ demo/test. Production cần HTTPS, hashing phù hợp, session/cookie hoặc bearer JWT theo kiến trúc, rate limiting, CSRF và quản lý vòng đời tài khoản.

### 4.1 Cấu trúc file

```text
src/main/java/com/example/tenancy/
├── TenancyApplication.java
├── SecurityConfig.java
├── OrgDirectory.java
├── Document.java
├── DocumentRepository.java
├── DocumentPolicy.java
├── DocumentHttpAuthorizationManager.java
├── DocumentService.java
└── DocumentController.java
src/test/java/com/example/tenancy/
└── TenancyAuthorizationTest.java
```

Mỗi public class/record có một file Java trùng tên, tất cả cùng package để Spring Boot component scanning tìm đúng beans.

## 5. Tài khoản và tư cách thành viên do backend quản lý

### 5.1 Membership và role theo từng tổ chức

**`src/main/java/com/example/tenancy/OrgDirectory.java`**

```java
package com.example.tenancy;

import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Component;

@Component
public class OrgDirectory {

    private final Map<String, Set<String>> memberships = Map.of(
        "alice", Set.of("acme"),
        "bob", Set.of("acme"),
        "carol", Set.of("zen"),
        "auditor", Set.of("acme")
    );

    private final Map<String, Set<String>> auditorRoles = Map.of(
        "auditor", Set.of("acme")
    );

    public boolean isMember(String account, String orgId) {
        return account != null && orgId != null
            && memberships.getOrDefault(account, Set.of())
                          .contains(orgId);
    }

    public boolean isAuditor(String account, String orgId) {
        return account != null && orgId != null
            && auditorRoles.getOrDefault(account, Set.of())
                           .contains(orgId)
            && isMember(account, orgId);
    }
}
```

Bản đồ `Map.of(...)` là nguồn membership **nội bộ phục vụ demo**. Client không thể tự thêm membership bằng JSON/header. Production nên dùng database/directory đáng tin, cache có chính sách TTL/invalidation và có audit khi đổi quyền.

**Không gọi `role == "admin"` trên một claim không có scope** rồi cho phép truy cập tất cả tổ chức. Ở ứng dụng nhiều tenant, một người có thể là auditor của `acme` nhưng chỉ là user thường ở `zen`.

### 5.2 Xác thực demo

**`src/main/java/com/example/tenancy/SecurityConfig.java`**

```java
package com.example.tenancy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}alice-demo")
                .authorities("ROLE_USER").build(),
            User.withUsername("bob")
                .password("{noop}bob-demo")
                .authorities("ROLE_USER").build(),
            User.withUsername("carol")
                .password("{noop}carol-demo")
                .authorities("ROLE_USER").build(),
            User.withUsername("auditor")
                .password("{noop}auditor-demo")
                .authorities("ROLE_USER").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            DocumentPolicy policy) throws Exception {

        var readManager =
            new DocumentHttpAuthorizationManager(policy, false);
        var editManager =
            new DocumentHttpAuthorizationManager(policy, true);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orgs/{orgId}/docs/{docId}"
                ).access(readManager)
                .requestMatchers(
                    HttpMethod.PUT,
                    "/api/orgs/{orgId}/docs/{docId}"
                ).access(editManager)
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Giải thích:**

- `@EnableMethodSecurity` bật phương thức `@PreAuthorize` ở tầng service.
- `readManager` và `editManager` kiểm tra cả org/owner trước khi controller được gọi. Chỉ matcher **GET** và **PUT** cụ thể được phép đến policy; các request khác `denyAll`.
- `anyRequest().denyAll()` là **deny by default**, tránh route mới vô tình chỉ cần authenticated.
- `httpBasic` chỉ là authentication mechanism cho demo, không quyết định owner/org.
- CSRF vẫn theo mặc định; trong test `PUT` cần `csrf()`. Với browser gửi cookie/session hoặc HTTP Basic tự động, không tắt CSRF chỉ để PUT “chạy được”.
- `ROLE_USER` không làm Alice có quyền mọi tài liệu. Tư cách thành viên và quyền theo tổ chức nằm ở `OrgDirectory`, là nguồn chính sách riêng.

**Thứ tự matcher quan trọng:** rule cụ thể GET/PUT đặt trước `anyRequest().denyAll()`. Nếu thêm `.requestMatchers("/api/**").authenticated()` lên trước, route phía sau có thể bị bypass kiểm tra owner/org do **first matching rule wins**. Regression tests phải phát hiện điều đó.

## 6. Tài liệu và repository: dữ liệu server-side

### 6.1 Record Document

**`src/main/java/com/example/tenancy/Document.java`**

```java
package com.example.tenancy;

public record Document(
    String id,
    String orgId,
    String ownerId,
    String body
) {}
```

Java `record` là lựa chọn ngắn gọn cho immutable snapshot trong ví dụ. Trường `ownerId` và `orgId` được backend quản lý; user chỉ được sửa `body` ở endpoint mẫu.

### 6.2 DocumentRepository

**`src/main/java/com/example/tenancy/DocumentRepository.java`**

```java
package com.example.tenancy;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class DocumentRepository {

    private final Map<String, Document> documents =
        new ConcurrentHashMap<>(Map.of(
            "doc-a",
                new Document("doc-a", "acme", "alice", "Alice draft"),
            "doc-b",
                new Document("doc-b", "acme", "bob", "Bob notes"),
            "doc-c",
                new Document("doc-c", "zen", "carol", "Carol plan")
        ));

    public Optional<Document> find(String orgId, String docId) {
        if (orgId == null || docId == null) {
            return Optional.empty();
        }

        return Optional.ofNullable(documents.get(docId))
            .filter(doc -> orgId.equals(doc.orgId()));
    }

    public Document replaceBody(
            String orgId, String docId, String nextBody) {

        return documents.compute(docId, (id, current) -> {
            if (current == null || !orgId.equals(current.orgId())) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found"
                );
            }

            // Không thay orgId hay ownerId từ input client.
            return new Document(
                current.id(),
                current.orgId(),
                current.ownerId(),
                nextBody
            );
        });
    }
}
```

**Điều đã làm đúng ở repository:** `find(orgId, docId)` yêu cầu **cùng org**; `replaceBody` chỉ sửa nội dung, giữ nguyên owner/org. Không có update nhận `ownerId` hay `orgId` từ body. `ConcurrentHashMap.compute` giúp thay một document atomically trong **một JVM**.

**Điều chưa đạt production:** repository là dữ liệu in-memory, bị reset khi restart, không có transaction trên DB, versioning, tenancy ở SQL, concurrency control hoặc quy trình đổi owner. `replaceBody` hiện chỉ kiểm tra org; quyền owner được kiểm tra ở **HTTP và service trước khi gọi**. Trong production phải đặt **authorization condition vào chính truy vấn ghi/transaction** để tránh thay đổi owner/membership giữa check và commit (xem mục TOCTOU).

## 7. DocumentPolicy: một nơi định nghĩa quyền cho HTTP và service

**`src/main/java/com/example/tenancy/DocumentPolicy.java`**

```java
package com.example.tenancy;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final OrgDirectory organizations;
    private final DocumentRepository documents;

    public DocumentPolicy(
            OrgDirectory organizations,
            DocumentRepository documents) {
        this.organizations = organizations;
        this.documents = documents;
    }

    public boolean canRead(
            Authentication auth, String orgId, String docId) {
        return allowed(auth, orgId, docId, false);
    }

    public boolean canEdit(
            Authentication auth, String orgId, String docId) {
        return allowed(auth, orgId, docId, true);
    }

    private boolean allowed(
            Authentication auth,
            String orgId,
            String docId,
            boolean editing) {

        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || orgId == null || docId == null) {
            return false;
        }

        String actor = auth.getName();

        if (!organizations.isMember(actor, orgId)) {
            return false;
        }

        return documents.find(orgId, docId)
            .map(document -> {
                boolean isOwner =
                    actor.equals(document.ownerId());

                if (editing) {
                    return isOwner;
                }

                boolean isOrgAuditor =
                    organizations.isAuditor(actor, orgId);

                return isOwner || isOrgAuditor;
            })
            .orElse(false);
    }
}
```

**Đọc chính sách theo thứ tự:**

1. Actor phải là một principal đã xác thực, không phải anonymous token.
2. Actor phải đang là thành viên của `orgId`.
3. Document phải tồn tại **và** thuộc đúng `orgId` mà request đưa ra.
4. Đối với sửa: chỉ owner. Đối với đọc: owner hoặc auditor đúng org.
5. Nếu thiếu thông tin, document không tìm được, hoặc org khác: **false/deny**, không tự cho qua.

**Quan trọng:** hai điều kiện tenant và owner không phải lựa chọn thay thế lẫn nhau. Người có tên trùng `ownerId` nhưng **đã bị thu hồi membership**, hoặc đang gọi một org khác, cũng phải bị chặn. Auditor của `acme` không được đọc tài liệu `zen`.

### 7.1 Tại sao không tin role toàn cục?

Một authority `ROLE_AUDITOR` (nếu phát trong JWT) chưa nói người đó được kiểm toán **tổ chức nào**. Nếu không ràng buộc org, một auditor acme có thể chuyển `orgId=zen` và xem dữ liệu tenant khác. Trong demo, `OrgDirectory.isAuditor(actor, orgId)` kiểm tra **cùng một org**. Ở production, hãy lấy org-scoped entitlements từ nguồn có thể xác minh; nếu dùng JWT claims, kiểm tra signature/issuer/audience/expiry và chính sách đồng bộ/thu hồi quyền.

### 7.2 Khi cần cấp quyền system administrator

Nếu thực tế có **superadmin hỗ trợ nhiều tenant**, policy cần explicit: ai cấp quyền, có ticket/justification không, log/audit, cần step-up MFA không, có giới hạn resource không, có bị legal hold/privacy restrictions chặn không. **Không** đơn giản thêm `auth.getAuthorities().contains("ROLE_ADMIN")` rồi bypass mọi tenant checks. Một superadmin vẫn có thể chỉ được truy cập dưới cơ chế break-glass được kiểm soát.

## 8. HTTP authorization: kiểm tra document + org theo request

Spring Security 6.x dùng `authorizeHttpRequests` với `AuthorizationManager`. Khi chọn matcher có biến `{orgId}`, `{docId}`, `RequestAuthorizationContext.getVariables()` cung cấp những giá trị được match để manager đối chiếu policy.

**`src/main/java/com/example/tenancy/DocumentHttpAuthorizationManager.java`**

```java
package com.example.tenancy;

import java.util.function.Supplier;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class DocumentHttpAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final DocumentPolicy policy;
    private final boolean edit;

    public DocumentHttpAuthorizationManager(
            DocumentPolicy policy, boolean edit) {
        this.policy = policy;
        this.edit = edit;
    }

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        String orgId = context.getVariables().get("orgId");
        String docId = context.getVariables().get("docId");

        boolean granted = edit
            ? policy.canEdit(authentication.get(), orgId, docId)
            : policy.canRead(authentication.get(), orgId, docId);

        return new AuthorizationDecision(granted);
    }
}
```

**Giải thích:**

- Manager phân biệt action qua cờ `edit`, do **server chọn khi cấu hình matcher GET/PUT**, không cho client chọn `canEdit=true` trong JSON.
- `context.getVariables()` lấy đúng biến từ `RequestMatcher`; nếu matcher/servlet path không cung cấp biến hoặc biến không hợp lệ, `DocumentPolicy` từ chối.
- `authentication.get()` lấy Authentication của request sau khi Spring Security đã thực hiện cơ chế xác thực được cấu hình.
- `AuthorizationDecision(granted)` cho phép hoặc từ chối **trước controller**.
- Các tên `orgId` và `docId` trong URL không phải trust signal; policy vẫn tra membership/document trong backend.

**Cảnh báo tương thích:** đoạn trên dùng interface/method `AuthorizationManager.check(...)` thường có trong Spring Security 6.x; một số release gần đây ưu tiên API `authorize(...)`. Khi dependency đã thay đổi, dùng chữ ký phương thức **đúng bản Spring Security đang chạy** và test hành vi. Không thay bằng một đoạn “mock Authentication” tùy tiện ở production.

**Quan trọng về matcher:** biến URI có thể được hỗ trợ khác nhau theo cách matcher được chọn (MVC/PathPattern/regex), servlet path và phiên bản. Với bài thực hành này dùng Spring MVC và string requestMatchers chuẩn. Nếu project có nhiều DispatcherServlet, servlet mapping bất thường hoặc matcher tùy biến, hãy cấu hình `RequestMatcher` tường minh phù hợp, xác nhận `getVariables()` thực sự trả `orgId/docId`, rồi chạy integration tests. Nếu biến không được cung cấp, policy phải **deny**, không dùng một fallback “permit all”.

### 8.1 Chọn coarse HTTP vs fine-grained service thế nào?

Ví dụ này **kiểm tra đầy đủ owner/org ở cả HTTP lẫn service** nhằm học defense-in-depth và phát hiện bypass ở cả hai tầng. Trong hệ thống lớn, việc truy vấn DB từ filter authorization có thể gây overhead và race nếu service đọc lại trạng thái khác. Một biến thể hợp lệ là:

- **HTTP:** kiểm tra request đã xác thực, có membership org và quyền chức năng cơ bản; không kết luận object ownership tại HTTP.
- **Service:** kiểm tra **owner/org/resource state** đầy đủ với transaction và query được scope.

Biến thể coarse/fine có thể nhanh hơn, nhưng không nên bỏ kiểm tra object-level ở service. Nếu yêu cầu nghiệp vụ thực sự là bảo vệ **cả hai tầng** như bài này, hãy giữ tests cho từng boundary và không tự nới rule URL.

## 9. Service: method security không thể bị bypass qua HTTP-only policy

**`src/main/java/com/example/tenancy/DocumentService.java`**

```java
package com.example.tenancy;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "@documentPolicy.canRead(authentication, #p0, #p1)"
    )
    public Document read(String orgId, String docId) {
        return documents.find(orgId, docId).orElseThrow(
            () -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document not found"
            )
        );
    }

    @PreAuthorize(
        "@documentPolicy.canEdit(authentication, #p0, #p1)"
    )
    public Document edit(
            String orgId, String docId, String newBody) {
        return documents.replaceBody(orgId, docId, newBody);
    }
}
```

**Vì sao dùng `#p0` và `#p1`?** Chúng tham chiếu tham số thứ nhất/thứ hai trong SpEL method security, không phụ thuộc việc tên tham số Java có được giữ với compiler flag `-parameters` hay không. `authentication` là object được cung cấp bởi method security expression context. Trong project khác có thể dùng `#orgId`/`#docId` nếu build bảo đảm tên parameter có sẵn.

**Vì sao đặt `@PreAuthorize` trên service?** HTTP `AuthorizationManager` đã bảo vệ hai route hiện có. Nhưng một controller mới có thể gọi `DocumentService.read(...)` trực tiếp; scheduled task/queue consumer có thể sử dụng lại service. Khi method được gọi qua **Spring-managed proxy**, annotation tiếp tục yêu cầu policy. Một lời gọi nội bộ `this.read(...)` trong **chính bean** có thể bypass AOP proxy và không kích hoạt `@PreAuthorize`; cần tránh self-invocation hoặc thiết kế policy explicit. Unit/integration test phải gọi service bean do Spring quản lý, không gọi `new DocumentService(...)` nếu muốn test AOP.

**Không nhầm 403 và 404:** phương thức `read` có nhánh 404 khi không tìm được tài liệu sau authorization. Trong thiết kế bài, `canRead(...)` sẽ deny trước với object không tồn tại, nên request thường nhận **403**. Chính sách API production có thể chủ đích trả **404 đồng nhất cho object không tồn tại và object không được xem** để hạn chế enumeration; nhưng đó là một thiết kế error handling/threat model riêng, không được quảng cáo rằng `@PreAuthorize` mặc định trả 404.

### 9.1 Method security không thay transaction isolation

Giữa hai bước:

```text
T0: DocumentPolicy đọc doc-a thuộc Alice, org acme -> allow
T1: Tác vụ khác chuyển owner hoặc thu hồi membership
T2: DocumentService sửa doc-a
```

có thể xảy ra **time-of-check/time-of-use (TOCTOU)**. Ví dụ in-memory giữ owner và org cố định để dễ học, nhưng production có chuyển owner/đổi org/revoke membership cần bảo vệ transaction/atomic write ở tầng DB. Xem mục 12.

## 10. Controller: chỉ nhận path và nội dung, không nhận quyền do client khai báo

**`src/main/java/com/example/tenancy/DocumentController.java`**

```java
package com.example.tenancy;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/api/orgs/{orgId}/docs/{docId}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String read(
            @PathVariable String orgId,
            @PathVariable String docId) {
        return service.read(orgId, docId).body();
    }

    @PutMapping(
        value = "/api/orgs/{orgId}/docs/{docId}",
        consumes = MediaType.TEXT_PLAIN_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String edit(
            @PathVariable String orgId,
            @PathVariable String docId,
            @RequestBody String nextBody) {
        return service.edit(orgId, docId, nextBody).body();
    }

    @GetMapping("/health")
    public String health() {
        return "ok";
    }
}
```

Client không có field `ownerId` hoặc `orgId` trong body để tự nâng quyền; request path vẫn có orgId, nhưng server **đối chiếu membership và document.orgId**. Với API thật, nên validate body size, content type, data schema, concurrency version và audit update.

**`src/main/java/com/example/tenancy/TenancyApplication.java`**

```java
package com.example.tenancy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenancyApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenancyApplication.class, args);
    }
}
```

Các file trên đặt cùng package, chạy bằng:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu dùng HTTP Basic để thử ngoài localhost, cần **HTTPS** để bảo vệ credentials khỏi quan sát trên đường truyền; chỉ dùng mật khẩu `-demo` trong môi trường học tập. Lệnh `curl` dưới đây là **yêu cầu minh họa**; response phụ thuộc ứng dụng đã khởi chạy thành công và CSRF/session configuration.

## 11. Thử nhanh HTTP và quan sát 200/401/403

Dự đoán với demo và dữ liệu ban đầu:

```bash
# Anonymous: public health = HTTP 200.
curl -i http://localhost:8080/health

# Alice đọc document của mình: HTTP 200, body "Alice draft".
curl -i -u alice:alice-demo \
  http://localhost:8080/api/orgs/acme/docs/doc-a

# Bob cùng acme nhưng không phải owner: HTTP 403.
curl -i -u bob:bob-demo \
  http://localhost:8080/api/orgs/acme/docs/doc-a

# Auditor acme đọc tài liệu Alice: HTTP 200.
curl -i -u auditor:auditor-demo \
  http://localhost:8080/api/orgs/acme/docs/doc-a

# Auditor acme không được đọc tài liệu zen: HTTP 403.
curl -i -u auditor:auditor-demo \
  http://localhost:8080/api/orgs/zen/docs/doc-c

# Không có Authorization: protected document thường HTTP 401.
curl -i http://localhost:8080/api/orgs/acme/docs/doc-a
```

Chú ý: `curl -u` gửi HTTP Basic `Authorization`; demo có `httpBasic`. Với controller trả chuỗi, body do Spring MVC render là plain text. Thứ tự 401/403 do `ExceptionTranslationFilter` và configured authentication entry point quyết định; **đừng đồng nhất 403 với chưa đăng nhập**.

Với `PUT`, Spring Security mặc định áp CSRF cho unsafe methods. Chỉ biết username/password trong curl **chưa đủ** để có một `PUT` hợp lệ nếu CSRF protection đang bật:

```bash
# Thiếu CSRF, dự kiến bị 403 trong cấu hình demo:
curl -i -X PUT -u alice:alice-demo \
  -H "Content-Type: text/plain" \
  --data "New Alice draft" \
  http://localhost:8080/api/orgs/acme/docs/doc-a
```

Bài học sẽ test nhánh có CSRF token hợp lệ bằng `spring-security-test`. Với browser production, phải implement chiến lược cấp/gửi CSRF token đúng (`HttpSessionCsrfTokenRepository`, CookieCsrfTokenRepository hay giải pháp phù hợp) chứ không tắt CSRF bừa để curl dễ chạy. Với stateless bearer-token API không dùng ambient browser credentials, đánh giá CSRF theo kiến trúc riêng.

## 12. Cập nhật an toàn ở database: chống TOCTOU và cross-tenant writes

Mã in-memory đủ để học hai tầng authorization, **nhưng chưa phải cách commit thay đổi bảo mật trong production**.

### 12.1 Đưa điều kiện tenant + owner vào SQL

Một tác vụ **chỉ owner được sửa** có thể được biểu diễn dạng SQL tham số hóa:

```sql
UPDATE documents
   SET body = :next_body,
       version = version + 1
 WHERE id = :doc_id
   AND org_id = :org_id
   AND owner_id = :actor_id
   AND version = :expected_version;
```

Sau lệnh update, yêu cầu **affected rows == 1** mới xem là thành công. Nếu 0 row, có thể là tài liệu không tồn tại, sai org, sai owner hoặc version conflict. Hãy chọn error contract phù hợp (403/404/409), tránh tiết lộ object existence cho người không được xem.

**Cần phân biệt:** SQL trên kiểm tra owner trong thời điểm ghi, nhưng **chưa kiểm tra active org membership**. Nếu membership thay đổi cần hiệu lực ngay, dùng transaction có isolation/locking phù hợp, query `EXISTS` từ membership table trong cùng operation, row-level security hoặc cơ chế policy khác được đảm bảo nhất quán. Không chỉ đọc membership một lần ở Java rồi cho rằng không thể revoke giữa hai bước.

Ví dụ thêm membership guard trong SQL theo mô hình đơn giản:

```sql
UPDATE documents AS d
   SET body = :next_body,
       version = version + 1
 WHERE d.id = :doc_id
   AND d.org_id = :org_id
   AND d.owner_id = :actor_id
   AND d.version = :expected_version
   AND EXISTS (
        SELECT 1
          FROM organization_memberships AS m
         WHERE m.account_id = :actor_id
           AND m.org_id = d.org_id
           AND m.status = 'ACTIVE'
   );
```

Đây là **SQL minh họa**, cần điều chỉnh cho hệ quản trị database, ORM, transaction isolation và yêu cầu nhất quán thật. Tùy DB và concurrency, vẫn cần khóa/transaction hoặc isolation thích hợp để ngăn thay đổi membership chen vào theo semantics đã chọn. Không kết luận “có EXISTS là hoàn toàn hết race” cho mọi RDBMS/isolation.

### 12.2 Hibernate/JPA và @Transactional

Với Spring Data JPA, repository methods nên có tenant scope rõ như `findByIdAndOrgId(...)`, thay vì load bằng ID rồi hy vọng từng controller luôn nhớ kiểm tra org. Tuy nhiên, tên query method **không phải authorization tự động**: nó chỉ lọc dữ liệu. Người đã là member org vẫn cần rule owner/auditor.

Với method `@Transactional`, phải xem **thứ tự AOP interceptor của method security và transaction**, thời điểm authorization và data load. Nếu policy dựa trên document snapshot, hãy xác định mức isolation/locking hoặc conditional update phù hợp để không dùng stale state. Nếu có cache, invalidate khi chuyển owner/org, thay đổi membership, đổi role hoặc khóa account.

### 12.3 Row-Level Security (RLS) là lớp defense-in-depth

Một số RDBMS (ví dụ PostgreSQL) có Row-Level Security giúp áp policy ngay ở DB. RLS có thể hữu ích với multi-tenant, nhưng:

- Cần đảm bảo org/user context truyền đến DB **không bị giả mạo** và được reset khi dùng connection pool.
- Không dùng database superuser/bypass-RLS role cho application read/write thường ngày.
- Chính sách RLS phải bao gồm tenant/owner và operation đúng; test SQL direct access bằng DB role thực tế.
- RLS không thay hoàn toàn Spring Security authorization ở API/business workflows.

Một tenant leak có thể xuất hiện ở **cache, search index, object storage hoặc queue** ngay cả khi SQL đã dùng `WHERE org_id = ...`. Cần kiểm tra mọi storage/search path cùng trust model.

## 13. Viết bộ MockMvc tests xác nhận cả hai tầng

Thêm Spring Boot test và `spring-security-test` như `build.gradle` ở trên. Test dưới dùng **HTTP Basic postprocessor** để đi qua authentication filter trong demo, không chỉ `@WithMockUser`. `@SpringBootTest` + `@AutoConfigureMockMvc` dùng Spring Security filters của ứng dụng.

**`src/test/java/com/example/tenancy/TenancyAuthorizationTest.java`**

```java
package com.example.tenancy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class TenancyAuthorizationTest {

    @Autowired MockMvc mvc;
    @Autowired DocumentService service;

    @Test
    void anonymousCannotReadPrivateDocument() throws Exception {
        mvc.perform(get("/api/orgs/acme/docs/doc-a"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("alice", "alice-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("Alice draft"));
    }

    @Test
    void sameOrgDifferentOwnerIsDenied() throws Exception {
        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("bob", "bob-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void crossOrgAttemptAndSpoofedOrgPathAreDenied()
            throws Exception {

        // Carol chỉ là thành viên zen, không thuộc acme.
        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("carol", "carol-demo")))
            .andExpect(status().isForbidden());

        // Alice không thể đổi org trong path để vượt tenant.
        mvc.perform(get("/api/orgs/zen/docs/doc-a")
            .with(httpBasic("alice", "alice-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void auditorCanReadOnlyWithinAssignedOrganization()
            throws Exception {

        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("auditor", "auditor-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("Alice draft"));

        mvc.perform(get("/api/orgs/zen/docs/doc-c")
            .with(httpBasic("auditor", "auditor-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void putRequiresCsrfAndOwnerPermission() throws Exception {
        String route = "/api/orgs/acme/docs/doc-a";

        mvc.perform(put(route)
            .with(httpBasic("alice", "alice-demo"))
            .contentType(MediaType.TEXT_PLAIN)
            .content("Alice updated"))
            .andExpect(status().isForbidden());

        mvc.perform(put(route)
            .with(httpBasic("auditor", "auditor-demo"))
            .with(csrf())
            .contentType(MediaType.TEXT_PLAIN)
            .content("attacker edit"))
            .andExpect(status().isForbidden());

        mvc.perform(put(route)
            .with(httpBasic("bob", "bob-demo"))
            .with(csrf())
            .contentType(MediaType.TEXT_PLAIN)
            .content("Bob edit"))
            .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanEditWithValidCsrf() throws Exception {
        mvc.perform(put("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("alice", "alice-demo"))
            .with(csrf())
            .contentType(MediaType.TEXT_PLAIN)
            .content("Alice updated"))
            .andExpect(status().isOk())
            .andExpect(content().string("Alice updated"));

        mvc.perform(get("/api/orgs/acme/docs/doc-a")
            .with(httpBasic("alice", "alice-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("Alice updated"));
    }

    @Test
    void unknownOperationIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/unknown")
            .with(httpBasic("alice", "alice-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void directServiceCallStillEnforcesOwnerPolicy() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read("acme", "doc-a")
        );
        assertThrows(
            AccessDeniedException.class,
            () -> service.edit("acme", "doc-a", "hijacked")
        );
    }

    @Test
    @WithMockUser(username = "carol", roles = "USER")
    void directServiceCallStillEnforcesTenantPolicy() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.read("acme", "doc-a")
        );
    }
}
```

**Quan trọng về test isolation:** `DocumentRepository` demo là **in-memory singleton** trong Spring test application context. Test `ownerCanEditWithValidCsrf` sẽ sửa `doc-a` từ `Alice draft` thành `Alice updated`. Nếu JUnit chạy tests song song, hoặc reuse context giữa nhiều test classes, một test đọc body cố định `"Alice draft"` có thể trở nên **flaky**. Để làm regression suite production-grade, hãy **reset fixtures trước mỗi test** bằng transactional test database hoặc repository reset method chỉ dùng trong test; thay vì phụ thuộc thứ tự thực thi của JUnit.

Vì snippet hiện là bộ test chạy trong một context chung, nên **đừng bật parallel execution** và đừng dựa vào thứ tự test. Để test hoàn toàn xác định ngay cả khi chạy tuần tự không theo thứ tự, thêm một phương thức reset fixtures dưới đây rồi gọi trong `@BeforeEach`:

**Bổ sung vào `DocumentRepository.java` trong môi trường demo/test:**

```java
public void resetDemoData() {
    documents.clear();
    documents.put("doc-a",
        new Document("doc-a", "acme", "alice", "Alice draft"));
    documents.put("doc-b",
        new Document("doc-b", "acme", "bob", "Bob notes"));
    documents.put("doc-c",
        new Document("doc-c", "zen", "carol", "Carol plan"));
}
```

**Bổ sung vào `TenancyAuthorizationTest.java`:**

```java
@Autowired DocumentRepository repository;

@BeforeEach
void resetFixtures() {
    repository.resetDemoData();
}
```

Nhớ import `org.junit.jupiter.api.BeforeEach`. `resetDemoData` là **test convenience**, không phải thao tác nên công khai qua controller production. Khi có nhiều tests chạy song song trên cùng bean context, reset global singleton vẫn race; dùng isolated context/transaction/test database. Với hệ thống thật, xây fixtures qua migrations/test containers và rollback transaction khi thích hợp.

### 13.1 Phân tầng các test trên

| Test | Chứng minh | Không chứng minh |
| --- | --- | --- |
| GET Alice → 200 | HTTP + service cho owner đọc. | Dữ liệu SQL isolation nếu demo in-memory. |
| GET Bob → 403 | HTTP chặn same-org non-owner. | Method security riêng nếu chỉ test qua HTTP. |
| `service.read(...)` dưới `@WithMockUser("bob")` → AccessDenied | Method security chặn ngay cả không qua HTTP. | Authentication provider production hoạt động. |
| GET Carol org khác → 403 | HTTP tenant scoping. | Toàn bộ endpoints khác đã được bảo vệ. |
| Auditor read 200/edit 403 | Policy read và edit khác nhau, role scoped. | Quy trình cấp/revoke auditor role production. |
| PUT thiếu CSRF → 403 | Filter CSRF chặn unsafe request. | Browser production đã gửi token đúng cách. |
| PUT owner + CSRF → 200 | HTTP + service và update demo. | DB transaction/TOCTOU được giải quyết. |
| GET unknown route → 403 | `anyRequest().denyAll()` không tự permit route lạ. | Mọi chain trong một hệ thống lớn đã được cấu hình đúng. |

**Phải test cả đường service trực tiếp.** Nếu chỉ dùng MockMvc và mọi request đều bị HTTP manager từ chối trước controller, một service **bị thiếu `@PreAuthorize`** vẫn có thể khiến toàn bộ HTTP tests “xanh”. Bởi vậy `@WithMockUser` + `service.read/edit` trong test là chứng cứ độc lập cho tầng service.

### 13.2 Chú ý CSRF và HTTP method

CSRF là kiểm tra **khác** với owner/org authorization. Bài cố tình giữ mặc định CSRF và dùng `with(csrf())` trong test PUT. Nếu test thiếu CSRF trả 403, nó chưa chứng minh owner policy đã được thực thi; phải có một test **PUT có CSRF hợp lệ nhưng actor sai owner** để phân biệt hai lớp. Bộ test đã có trường hợp auditor/bob cùng cung cấp CSRF nhưng vẫn bị 403.

## 14. Unit-test policy trực tiếp: nhanh, dễ bao phủ ma trận

Ngoài HTTP/integration tests, nên viết unit test cho `DocumentPolicy` với repo/directory thật của demo. Không cần start Servlet container. Điều này giúp xác minh truth table nhanh.

**`src/test/java/com/example/tenancy/DocumentPolicyTest.java`**

```java
package com.example.tenancy;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

import static org.junit.jupiter.api.Assertions.*;

class DocumentPolicyTest {

    private final OrgDirectory organizations = new OrgDirectory();
    private final DocumentRepository documents = new DocumentRepository();
    private final DocumentPolicy policy =
        new DocumentPolicy(organizations, documents);

    private Authentication auth(String username) {
        return new UsernamePasswordAuthenticationToken(
            username,
            "not-used",
            AuthorityUtils.createAuthorityList("ROLE_USER")
        );
    }

    @Test
    void ownerCanReadAndEdit() {
        assertTrue(policy.canRead(auth("alice"), "acme", "doc-a"));
        assertTrue(policy.canEdit(auth("alice"), "acme", "doc-a"));
    }

    @Test
    void sameOrgDoesNotMeanAnyDocument() {
        assertFalse(policy.canRead(auth("bob"), "acme", "doc-a"));
        assertFalse(policy.canEdit(auth("bob"), "acme", "doc-a"));
    }

    @Test
    void auditorIsOrgScopedAndReadOnly() {
        assertTrue(policy.canRead(
            auth("auditor"), "acme", "doc-a"));
        assertFalse(policy.canEdit(
            auth("auditor"), "acme", "doc-a"));
        assertFalse(policy.canRead(
            auth("auditor"), "zen", "doc-c"));
    }

    @Test
    void wrongOrgAndUnknownDocAreDenied() {
        assertFalse(policy.canRead(auth("alice"), "zen", "doc-a"));
        assertFalse(policy.canRead(auth("alice"), "acme", "missing"));
        assertFalse(policy.canRead(null, "acme", "doc-a"));
    }
}
```

Với test class này, mỗi test instance theo JUnit Jupiter mặc định có repository riêng nên không bị shared state nếu không chủ động đổi lifecycle. Tuy nhiên, **unit test policy không chứng minh Spring AOP `@PreAuthorize` hoạt động**; kết hợp nó với test direct service call như mục 13.

### 14.1 Những case cần bổ sung khi nghiệp vụ phức tạp

- Owner đã rời org hoặc membership ở trạng thái `SUSPENDED`.
- Auditor bị revoke; quyền có hiệu lực thế nào khi token/session chưa hết hạn?
- Document đã archived/locked, không ai được sửa dù là owner.
- Owner chuyển tài liệu sang org mới; điều gì xảy ra với quyền cũ?
- Người dùng có membership ở hai org, một org auditor, một org user thường.
- Tài liệu có owner null (draft hệ thống) hoặc dữ liệu legacy bị sai org.
- Path variable có Unicode/encoding/case, org ID được normalize khác DB.
- Client thêm `X-Org-Id`/`X-Owner-Id` hoặc body có ownerId nhằm giả danh.
- Các nhánh 401/403/404 được chuẩn hóa để giảm leak resource existence.
- Giao dịch đồng thời đổi owner hoặc thu hồi membership giữa authorization và update.

## 15. Những lỗi bảo mật thường gặp trong thiết kế nhiều tenant

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `findById(docId)` rồi trả luôn | User đã login có thể đọc mọi doc ID. | Kiểm tra owner/org trong policy và query. |
| `.authenticated()` cho mọi `/api/**` | Không có object-level authorization. | Kiểm tra resource/action riêng, deny by default. |
| Tin `orgId` từ URL mà không so document.orgId | Có thể sửa URL để vào tenant khác. | Query theo `docId + orgId` và membership. |
| Tin `ownerId` từ JSON | Client tự khai owner là mình. | Server tính owner từ verified principal và policy chuyển quyền. |
| `ROLE_ADMIN` toàn cục cho org admin | Admin một tenant xem dữ liệu các tenant khác. | Role/permissions scoped per org. |
| HTTP có check owner nhưng service không có | Internal caller/endpoint mới bypass URL. | `@PreAuthorize`/policy ở service và test trực tiếp. |
| Service chỉ kiểm tra membership org | Bob cùng org xem tài liệu Alice. | Thêm owner/auditor policy theo resource. |
| `@PreAuthorize` không thực thi vì self-invocation | Code chạy trong cùng bean vượt AOP proxy. | Gọi qua Spring bean, test method security. |
| Dùng `Jwt claim org_id` không xác minh | Fake/expired token hoặc claim không phản ánh membership hiện tại. | Decoder/issuer/audience validation và authoritative policy. |
| Cache theo `docId` mà không scope tenant/quyền | Người tenant khác thấy response đã cache. | Cache key/authorization strategy phù hợp, không cache response nhạy cảm công khai. |
| Check owner rồi update không điều kiện | TOCTOU sau chuyển ownership. | Conditional update/transaction/row count. |
| Dùng header `X-Tenant` từ Internet làm quyền | Caller tự chọn tenant khác. | Chỉ dùng verified identity/membership, trust proxy boundary. |
| Trả 404/403 khác nhau tùy doc existence | Bị dò ID hoặc org membership. | Thiết kế error contract nhất quán theo threat model. |
| Service job có principal null rồi “auto admin” | Background job có quyền quá rộng không audit. | Service identity scoped, explicit authorization và audit. |
| GET bảo vệ nhưng DELETE/EXPORT/WebSocket bỏ sót | Có đường đọc/sửa dữ liệu không được check. | Lập inventory mọi entrypoint/action; test riêng từng đường. |
| Tenant identity ghi vào ThreadLocal mà không dọn | Worker tái sử dụng thread bị lẫn tenant. | Scope/cleanup context và test thread reuse. |

### 15.1 Cross-tenant leak qua lớp ngoài database

Ngay cả khi SQL đã có `WHERE org_id`, dữ liệu vẫn có thể rò qua:

- **Redis/cache:** key `doc-a` dùng chung cho mọi tenant hoặc cache phản hồi API không phân biệt người dùng.
- **Search index:** filter search không có `tenant_id`; aggregation trả hits từ tổ chức khác.
- **Object storage:** URL/signed URL tạo mà không xác minh org/resource ownership; signed URL quá lâu sống.
- **Exports/reporting:** queue job dùng `docId` nhưng không kiểm tra actor/tenant khi tải tài liệu.
- **Background jobs:** không có HTTP SecurityFilterChain, chỉ gọi service/repository trực tiếp.
- **Logs/traces:** ghi nhầm body/PII của tài liệu vào hệ thống vận hành cho nhiều nhóm.
- **WebSocket/SSE:** xác thực kết nối xong nhưng không authorize từng channel/resource.

**Không coi một `@PreAuthorize` ở một method duy nhất là bảo hiểm toàn hệ thống.** Cần kiểm kê mọi access path, đặc biệt direct repository calls ngoài service chuẩn.

## 16. 401, 403, 404 và che giấu sự tồn tại tài nguyên

### 16.1 401 là chưa xác thực

Với demo `httpBasic`, request không có credentials đến tài liệu riêng thường nhận **401** và `WWW-Authenticate`. Đây là authentication entry point, không phải kết quả so owner. Với web form login, user chưa đăng nhập có thể nhận **302 redirect** tới trang login.

### 16.2 403 là không đủ quyền

Một user đã xác thực nhưng không thỏa policy owner/tenant được trả **403**. Điều này không đồng nghĩa tài liệu có thật; trong ví dụ policy có thể deny cả khi doc không tồn tại.

### 16.3 404 có thể dùng để không tiết lộ existence

Một số API chọn phản hồi **404 cho tài liệu không có hoặc actor không được quyền biết nó tồn tại**. Nếu vậy nên chuẩn hóa behavior phía service/filter, logging/audit và error mapping, tránh endpoint A trả 403 còn endpoint B trả 404 tạo side-channel. Dù chọn status gì, **không bao giờ trả body tài liệu** trước authorization.

Mã bài học dùng 403 ở bước policy để minh họa rõ denial. Đây là lựa chọn demo, không phải yêu cầu mọi API multi-tenant đều phải lộ 403 thay 404.

## 17. Session, OAuth2/JWT và cách gắn user thực tế

### 17.1 Authentication là nguồn actor, không phải URL

Ở demo, `Authentication.getName()` là `alice`. Trong production, nếu dùng OIDC/JWT:

- Xác minh token (signature, issuer, audience, expiration, algorithm) bằng Spring Security Resource Server/OIDC Client đúng flow.
- Chọn claim **account ID ổn định** để map với user nội bộ.
- Không tin một token không dành cho API này dù nó có `sub=alice`.
- Org membership/role từ IdP có thể là input nhưng phải có chính sách về **độ mới, tenant binding và quyền đã bị revoke**.
- Không cho caller tự tạo `X-User-Id`/`X-Org-Id` để thay `Authentication`.

**ID token OIDC** dùng để xác thực người dùng tại client, không mặc nhiên là access token hợp lệ cho resource server API. Nếu dùng JWT access token, cần policy rõ về `aud`/`scope` và org.

### 17.2 User có nhiều tổ chức

Một user có thể tham gia `acme` và `zen`. Khi UI chọn org hiện tại:

1. Client gửi một org identifier để nêu **ý định**.
2. Server xác minh user là member **của org đó**.
3. Với mỗi tài liệu, server kiểm tra `document.orgId` đúng org và policy owner/auditor.
4. Không lưu một biến tenant global chung cho tất cả users trong `static`.
5. Nếu dùng context per-request/ThreadLocal, phải dọn khi request kết thúc và khi chuyển thread. Không để tenant A tồn dư trên pooled worker cho request B.

Một `activeOrgId` nằm trong session đã được kiểm soát cũng phải đối chiếu membership khi quyền có thể bị thay đổi; không biến session property thành quyền không thể thu hồi.

## 18. Checklist kiểm thử và vận hành thực tế

### 18.1 Test matrix trước khi merge

| Biên | Positive | Negative |
| --- | --- | --- |
| HTTP authentication | Alice Basic hợp lệ → được đánh giá policy. | Anonymous → 401. |
| HTTP owner | GET doc-a của Alice → 200. | Bob cùng org GET doc-a → 403. |
| HTTP tenant | Carol đọc doc-c thuộc zen → 200. | Carol đọc acme/doc-a → 403. |
| HTTP scoped auditor | Auditor đọc doc-a trong acme → 200. | Auditor đọc zen/doc-c → 403. |
| HTTP edit | Owner PUT + CSRF → 200. | Bob/auditor PUT + CSRF → 403. |
| CSRF | PUT có token đúng qua session contract. | Thiếu token → 403. |
| Service owner | `service.read` dưới principal Alice → cho phép. | `service.read` dưới Bob → AccessDeniedException. |
| Service tenant | Carol đọc doc-c zen → cho phép. | Carol gọi service với acme/doc-a → deny. |
| Repo scope | `find("acme","doc-a")` có object. | `find("zen","doc-a")` rỗng. |
| Concurrent update | Điều kiện owner/org/version đúng tại commit. | Owner bị đổi trong lúc xử lý → update 0 rows. |
| Cache/export/background | Actor có quyền được xử lý. | Không có current HTTP user hoặc tenant khác → deny/audit. |
| Unknown route/method | Chỉ endpoints đã khai báo được phép. | DELETE/GET không match → denyAll. |

### 18.2 Triển khai thực tế

- Chốt định danh account/organization **bất biến** và mô hình membership/role theo org.
- Dùng **principals đã xác thực** của Spring Security; không tin role/owner trong request.
- HTTP chỉ cho phép routes/methods đã xác định và gọi policy; fallback denyAll.
- Service gắn `@PreAuthorize`/domain policy và test **direct method invocation** qua Spring bean.
- Repository queries luôn có tenant scope; update có owner/org/membership/version guard phù hợp transaction.
- Phân biệt read/edit/delete/share/approve/export; không gán toàn quyền theo một role tên chung.
- Có CSRF strategy phù hợp browser/session; kiểm tra CORS, cookies và entry points.
- Dùng role scoped/org membership mới đủ tin, xử lý revoke/invalidation và audit.
- Không làm lộ object existence/PII qua 403/404, timing, cache key, error logs hay search results ngoài ý muốn.
- Chống TOCTOU với conditional update, locking/transaction và row-count verification.
- Có regression tests cross-owner, cross-tenant, internal service bypass, concurrent ownership changes và unknown routes.
- Nếu triển khai nhiều HTTP filter chains hoặc Servlet mappings, kiểm tra `securityMatcher`/requestMatchers order; route không match không được bypass.
- Theo dõi deny counts, tenant mismatch, bất thường IDOR probing, false positives và luồng support/admin có đặc quyền.

## 19. Tổng kết

**Phân quyền đúng phải trả lời đồng thời bốn câu hỏi: ai (actor), thuộc tổ chức nào (org), tác động lên tài liệu nào (resource), và thực hiện hành động gì (read/edit).** Kiểm tra user đã đăng nhập hoặc có một role toàn cục là chưa đủ.

Trong ví dụ Spring Security Servlet, **HTTP `AuthorizationManager`** dùng `DocumentPolicy` kiểm tra **đúng org + owner hoặc auditor** theo path và HTTP method; **service `@PreAuthorize`** kiểm tra lại cùng policy để không bị bypass bởi lời gọi nội bộ. Repository chỉ tìm theo org/doc, và production cần đưa điều kiện ownership/membership vào **transaction hoặc atomic update** để chống TOCTOU.

Một bộ test đáng tin phải chứng minh cả **owner 200**, **cùng org nhưng không owner 403**, **khác org 403**, **auditor chỉ đọc**, **PUT cần CSRF** và **direct service call vẫn bị chặn**. Kết hợp như vậy mới giảm đáng kể rủi ro BOLA/IDOR và rò rỉ dữ liệu giữa các tổ chức.
