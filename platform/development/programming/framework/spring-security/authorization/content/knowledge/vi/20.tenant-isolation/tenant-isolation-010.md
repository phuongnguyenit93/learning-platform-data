# Kiểm thử truy cập chéo tenant với cùng ID và cùng tên người dùng

## 1. Mục tiêu và điều dễ nhầm nhất

Trong hệ thống nhiều tenant, hai khách hàng khác nhau có thể cùng sở hữu bản ghi mang **ID = 42** và mỗi khách hàng đều có một tài khoản đăng nhập tên **`alex`**. Đây không phải trường hợp hiếm: nhiều hệ thống đánh số ID độc lập theo tenant, cho phép username/email alias giống nhau ở các tổ chức, hoặc liên kết người dùng từ nhiều identity provider.

Nếu kiểm tra quyền chỉ bằng:

```java
// PHẢN VÍ DỤ: không có tenant scope.
repository.findById(42L);

// PHẢN VÍ DỤ: username không phải identity duy nhất toàn hệ thống.
if (document.ownerUsername().equals(authentication.getName())) {
    return document;
}
```

thì kết quả có thể là đọc sai tài liệu, ghi nhầm bản ghi, chấp nhận người giả cùng username, xuất lẫn dữ liệu hoặc cho quyền người dùng tenant B dựa vào ACE của tenant A.

Mục tiêu bài **“Kiểm thử truy cập chéo tenant với cùng ID và cùng tên người dùng”** thuộc nhóm **Cách ly tenant** của Spring Security Authorization:

1. Xây dựng bộ dữ liệu test **cố ý trùng business ID và trùng username** nhưng khác tenant, subject và có thể khác issuer.
2. Phân biệt **username hiển thị**, **stable subject identity**, **issuer** và **tenant membership**.
3. Thiết kế khóa bản ghi `(tenant_id, document_id)` và khóa chủ sở hữu `(tenant_id, issuer, subject)`.
4. Dùng Spring Security Method Security cho quyền chức năng, kết hợp policy theo bản ghi và truy vấn JDBC có tenant scope.
5. Test positive/negative ở cấp đọc chi tiết, liệt kê, tạo, sửa, xóa; chứng minh không đọc/ghi dữ liệu tenant khác dù ID hoặc username trùng.
6. Kiểm tra không có side effect khi `@PreAuthorize` từ chối, và câu SQL UPDATE/DELETE luôn mang tenant + owner + trạng thái.
7. Biết thêm những test cần có nếu ứng dụng dùng JPA, ACL, cache, JWT/OIDC, PostgreSQL Row-Level Security (RLS), service account hoặc tenant switching.

**Môi trường ví dụ:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Spring JDBC, H2 và JUnit 5. H2 chỉ dùng để kiểm thử **tenant-scoped repository và method authorization**; nó không được trình bày như một mô phỏng PostgreSQL RLS.

## 2. Kịch bản dữ liệu: trùng ID và trùng tên, không trùng danh tính

Giả sử hai tenant `TENANT_A` và `TENANT_B` dùng cùng hệ thống:

| Tenant | Document ID | Username hiển thị | Issuer / subject sở hữu | Trạng thái | Nội dung |
| --- | ---: | --- | --- | --- | --- |
| TENANT_A | **42** | **alex** | `https://idp.example.test` / `a-user-100` | DRAFT | `A private 42` |
| TENANT_B | **42** | **alex** | `https://idp.example.test` / `b-user-200` | DRAFT | `B private 42` |
| TENANT_A | 43 | alex | `https://idp.example.test` / `a-user-100` | PUBLISHED | `A public 43` |
| TENANT_B | 44 | alex | `https://idp.example.test` / `b-user-200` | PUBLISHED | `B public 44` |

Hai người dùng:

```text
Authentication A:
  username = "alex"
  tenant   = "TENANT_A"
  issuer   = "https://idp.example.test"
  subject  = "a-user-100"
  authorities = DOC_READ, DOC_UPDATE, DOC_DELETE, DOC_CREATE

Authentication B:
  username = "alex"
  tenant   = "TENANT_B"
  issuer   = "https://idp.example.test"
  subject  = "b-user-200"
  authorities = DOC_READ, DOC_UPDATE, DOC_DELETE, DOC_CREATE
```

Cả hai `authentication.getName()` có thể trả `"alex"`. Vì vậy, so sánh `getName()` với `owner_username` **không đủ** để xác nhận người sở hữu.

### 2.1. Khóa phải dùng trong từng lớp

| Lớp | Khóa an toàn được minh họa | Không được chỉ dựa vào |
| --- | --- | --- |
| Bản ghi nghiệp vụ | `(tenant_id, document_id)` | `document_id` |
| Tài khoản/owner | `(tenant_id, issuer, subject)` | `username` hoặc `email` |
| Repository lookup | `WHERE tenant_id = :tenant AND doc_id = :id` | `WHERE doc_id = :id` |
| Owner check | Tenant + issuer + subject đã xác thực | Tên hiển thị do client hoặc user profile tự gửi |
| Cache dữ liệu/quyền | Tenant + type + ID + subject/permission nếu liên quan | `42`, `alex` |
| Object storage | Tenant namespace + object/key được cấp quyền | File key đoán được |
| Audit | Actor issuer/sub + tenant + resource tenant/ID | Chỉ log `alex:42` |

`issuer` và `sub` là các khái niệm ổn định thường gặp trong OIDC; nhưng trong sản phẩm thật phải **xác thực token, issuer, audience, signature, expiry và membership**. Bản ghi test dưới đây là synthetic trusted principal để dễ kiểm tra policy, **không phải** hướng dẫn lấy trực tiếp claims không được xác thực từ HTTP header.

### 2.2. Định nghĩa chính sách có chủ đích

Để test rõ ràng, chọn chính sách sau:

- `DOC_READ`: trong tenant của principal, đọc được tài liệu `PUBLISHED`; tài liệu `DRAFT` chỉ chủ sở hữu có khóa `issuer + subject` khớp mới được đọc.
- `DOC_UPDATE`: chỉ sửa `DRAFT` trong đúng tenant và đúng chủ sở hữu; SQL kiểm tra lại owner/status ngay khi ghi.
- `DOC_DELETE`: chỉ xóa `DRAFT` do chính mình sở hữu trong tenant đó.
- `DOC_CREATE`: được tạo tài liệu trong tenant đã được xác minh; tenant, issuer, subject của owner lấy từ principal server-side.
- `LIST`: chỉ trả tài liệu `PUBLISHED` hoặc DRAFT do chính actor sở hữu, trong tenant của actor.
- Mọi trường hợp thiếu quyền, sai tenant, sai subject/issuer hoặc không có bản ghi đều **deny by default**.

Đây là **policy ví dụ** nhằm minh họa cách ly tenant. Một ứng dụng khác có thể cho READ dựa trên nhóm/ACL, nhưng vẫn phải giữ tenant scope và xác minh quyền trên **từng đối tượng**.

## 3. Ma trận kiểm thử trọng tâm

| Actor | Hành động / ID | Kết quả kỳ vọng | Điều phải kiểm tra |
| --- | --- | --- | --- |
| A / alex / `a-user-100` | READ 42 | Allow, trả **A private 42** | Không bao giờ trả nội dung tenant B |
| B / alex / `b-user-200` | READ 42 | Allow, trả **B private 42** | Không bao giờ trả nội dung tenant A |
| A có `DOC_READ` | READ 44 | Deny | 44 chỉ tồn tại trong B dù đã PUBLISHED |
| B có `DOC_READ` | READ 43 | Deny | 43 chỉ tồn tại trong A |
| A có `DOC_READ` | READ 43 | Allow | PUBLISHED cùng tenant |
| A nhưng subject `a-other`, username vẫn alex | READ 42 | Deny | Username giống không thay owner |
| B nhưng subject lấy từ A, username vẫn alex | READ 42 | Deny | Tenant khớp chưa đủ khi DRAFT khác owner |
| A nhưng issuer khác, subject vẫn `a-user-100` | READ 42 | Deny | Subject cần được namespace theo issuer |
| A chỉ có `DOC_UPDATE` | READ 42 | Deny trước body | Thiếu authority `DOC_READ` |
| A | UPDATE 42 | Chỉ A thay đổi | B vẫn giữ nguyên nội dung |
| B | DELETE 42 | Chỉ B bị xóa | A#42 vẫn tồn tại |
| A và B | CREATE 99 | Hai bản ghi khác nhau | Composite primary key cho phép cùng ID ở hai tenant |
| A | CREATE 99 lần hai | Từ chối duplicate trong A | Không ghi đè dữ liệu đã có |
| A / B | LIST | Chỉ hàng đúng tenant | Không lộ hàng khác dù cùng username |
| Principal không có tenant identity đáng tin | READ/LIST | Deny | Không fallback theo username |
| Repository SQL không có tenant | `WHERE doc_id = 42` | Có 2 hàng — **cảnh báo** | Tuyệt đối không dùng làm protected lookup |

Ma trận có **hai đường positive cùng ID** và nhiều đường negative. Nếu chỉ kiểm tra “A không đọc được B” trong khi database dùng **ID duy nhất toàn cục** và username duy nhất toàn cục, test có thể không bao giờ chạm đúng lỗi collision.

## 4. Thiết kế database: composite key trước khi viết test

Một schema tối giản:

```sql
CREATE TABLE tenant_documents (
    tenant_id VARCHAR(80) NOT NULL,
    doc_id BIGINT NOT NULL,
    owner_issuer VARCHAR(200) NOT NULL,
    owner_subject VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL,
    body VARCHAR(2000) NOT NULL,
    PRIMARY KEY (tenant_id, doc_id)
);
```

Tại đây:

- `doc_id=42` có thể xuất hiện **hai lần** nếu `tenant_id` khác nhau.
- `PRIMARY KEY (tenant_id, doc_id)` ngăn hai bản ghi **cùng tenant/cùng ID**.
- `owner_issuer`, `owner_subject` là owner identity; không dùng `username` để quyết định ownership.
- Việc bảo vệ tenant trong query là trách nhiệm của repository/SQL và policy; composite PK **không tự ngăn** mọi truy vấn thiếu `WHERE tenant_id`.

**Truy vấn đúng:**

```sql
SELECT tenant_id, doc_id, owner_issuer,
       owner_subject, status, body
FROM tenant_documents
WHERE tenant_id = ? AND doc_id = ?;
```

**Truy vấn nguy hiểm:**

```sql
SELECT * FROM tenant_documents
WHERE doc_id = ?;
```

Với dữ liệu test, truy vấn thứ hai trả **hai hàng** cho ID 42. Nếu gọi `queryForObject`, có thể ném lỗi vì nhiều dòng; nếu dùng `LIMIT 1` hoặc chọn hàng đầu tiên, có thể âm thầm đọc **sai tenant**. Không được “sửa” bằng `LIMIT 1` khi thiếu tenant predicate.

Với JPA, phải phản ánh khóa ghép bằng `@EmbeddedId`, `@IdClass`, surrogate ID toàn cục cộng tenant predicate, hoặc tenant-aware persistence model. Dùng `JpaRepository<Document, Long>` với `Long` chỉ là ID nội bộ tenant có thể tạo ra giả định uniqueness sai. Quan hệ foreign key tới entity tenant-scoped cũng cần kết hợp tenant để không join sang bản ghi cùng ID của tenant khác.

## 5. Danh tính: username giống nhau không phải cùng principal

### 5.1. Authentication.getName() thường chỉ là nhãn

Trong Spring Security, `Authentication.getName()` tùy vào `Principal`/provider. Nó **có thể** là username, subject, email hoặc giá trị do ứng dụng quy ước. Vì vậy không được mặc định đó là khóa người dùng duy nhất trong mọi tenant.

Ví dụ:

```java
record TenantPrincipal(
    String issuer, String subject,
    String username, String tenantId
) implements java.security.Principal {

    @Override
    public String getName() {
        return username;
    }
}
```

Hai `TenantPrincipal` khác `tenantId`/`subject` vẫn có thể có `getName() == "alex"`. Trong ví dụ, `issuer + subject + tenant` là tenant-scoped identity dùng để kiểm tra ownership.

### 5.2. Cần xác minh ở ranh giới authentication

**Đối tượng Java trên chỉ đáng tin nếu được tạo từ authentication đã xác thực.** Production cần:

1. Xác minh JWT/OIDC token signature, `iss`, `aud`, `exp`, `nbf`, issuer trust và các claims cần thiết.
2. Nếu người dùng chọn active tenant, đối chiếu **membership, role, điều kiện tổ chức** từ nguồn server tin cậy trước khi tạo principal.
3. Không nhận `tenantId` và `subject` từ request body/header rồi tự tạo `Authentication` được tin cậy.
4. Nếu có nhiều issuer, dùng cặp `(issuer, subject)`; có thể dùng stable internal user ID để tránh phụ thuộc cách provider đặt username.
5. Khi membership bị thu hồi, token/cache/long-lived sessions phải được xử lý theo SLA bảo mật.

Test tạo trực tiếp `TenantPrincipal` chỉ để **giả lập output của authentication boundary**, không phải chứng minh pipeline xác thực JWT đã an toàn. Bổ sung security-filter integration tests cho token thật ở môi trường ứng dụng.

## 6. Tách function permission, object permission và tenant scope

Trong Spring Security Method Security, service có thể dùng:

```java
@PreAuthorize(
    "hasAuthority('DOC_READ') and " +
    "@tenantPolicy.canRead(authentication, #docId)"
)
public Document read(@P("docId") long docId) {
    // Truy vấn vẫn phải scoped theo tenant.
}
```

Đây là một **fragment** minh họa:

- `hasAuthority('DOC_READ')` quyết định **chức năng** được phép gọi.
- `@tenantPolicy.canRead(authentication, #docId)` nhận authentication thực tế và tra bản ghi đúng tenant để kiểm tra owner/trạng thái.
- `@P("docId")` giúp SpEL nhận tên tham số dù Java build không mở `-parameters`.
- `@EnableMethodSecurity` phải bật trong context.
- Method phải được gọi qua **Spring-managed proxy**; `this.read(id)` trong cùng target có thể bỏ qua advice.
- **Thân method** phải tiếp tục truy vấn với tenant predicate; không dựa vào “vừa được cho phép ở precheck” để dùng `findById(id)` thiếu tenant.

`@PreAuthorize` bảo vệ trước khi vào body, nhưng vẫn có **TOCTOU**: owner hoặc trạng thái có thể thay đổi giữa kiểm tra và ghi. Với UPDATE/DELETE, SQL nên lặp lại tenant + owner + status trong chính câu lệnh atomically.

## 7. Project Java 17+ chạy được: Spring Security + JDBC + H2

Ví dụ có một **schema thật** và **test Spring context thật**. H2 cho phép tạo hai hàng cùng `doc_id=42` ở hai tenant, nhờ `PRIMARY KEY(tenant_id,doc_id)`. Bộ test dùng `SecurityContextHolder` để mô phỏng hai principal có username trùng nhau nhưng issuer/subject/tenant khác. Không có web server, JWT filter hoặc PostgreSQL RLS: đó là những lớp cần kiểm thử thêm riêng.

### 7.1. Cấu trúc project

```text
tenant-collision-tests/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/TenantCollisionSecurityTest.java
    └── resources/schema.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'tenant-collision-tests'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

### 7.2. Tệp SQL tạo bảng với composite primary key

`src/test/resources/schema.sql`:

```sql
DROP TABLE IF EXISTS tenant_documents;

CREATE TABLE tenant_documents (
    tenant_id VARCHAR(80) NOT NULL,
    doc_id BIGINT NOT NULL,
    owner_issuer VARCHAR(200) NOT NULL,
    owner_subject VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL,
    body VARCHAR(2000) NOT NULL,
    PRIMARY KEY (tenant_id, doc_id)
);

CREATE INDEX ix_tenant_docs_owner
ON tenant_documents
    (tenant_id, owner_issuer, owner_subject, status);
```

Đây là DDL H2 phục vụ bài test, không phải migration production. Database test được khởi tạo bằng `spring.sql.init.mode=always` và URL H2 trong `@SpringBootTest`. Tất cả SQL dưới đây dùng placeholder JDBC `?`, không nối chuỗi user input.

### 7.3. Java integration test đầy đủ

`src/test/java/demo/TenantCollisionSecurityTest.java`:

```java
package demo;

import java.security.Principal;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = TenantCollisionSecurityTest.App.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.datasource.url=jdbc:h2:mem:tenant_collision_demo;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.sql.init.mode=always"
    }
)
public class TenantCollisionSecurityTest {

    private static final String ISSUER = "https://idp.example.test";

    private static final TenantPrincipal ACTOR_A =
        new TenantPrincipal(
            ISSUER, "a-user-100", "alex", "TENANT_A");

    private static final TenantPrincipal ACTOR_B =
        new TenantPrincipal(
            ISSUER, "b-user-200", "alex", "TENANT_B");

    @Autowired JdbcTemplate jdbc;
    @Autowired DataSource dataSource;
    @Autowired TenantStore store;
    @Autowired TenantDocumentService documents;
    @Autowired Probe probe;

    public record TenantPrincipal(
        String issuer, String subject,
        String username, String tenantId
    ) implements Principal {
        @Override
        public String getName() {
            return username;
        }
    }

    public record Doc(
        String tenantId, long id, String ownerIssuer,
        String ownerSubject, String status, String body
    ) {}

    public static class Probe {
        private final ConcurrentHashMap<String, AtomicInteger> counts =
            new ConcurrentHashMap<>();

        void mark(String action) {
            counts.computeIfAbsent(
                action, x -> new AtomicInteger()
            ).incrementAndGet();
        }

        int count(String action) {
            AtomicInteger c = counts.get(action);
            return c == null ? 0 : c.get();
        }

        void reset() {
            counts.clear();
        }
    }

    public static class TrustedIdentity {
        public static TenantPrincipal actor(Authentication auth) {
            if (auth == null || !auth.isAuthenticated()
                || !(auth.getPrincipal() instanceof TenantPrincipal p)
                || p.tenantId() == null || p.tenantId().isBlank()
                || p.issuer() == null || p.issuer().isBlank()
                || p.subject() == null || p.subject().isBlank()) {
                return null;
            }
            return p;
        }

        public static TenantPrincipal requireActor() {
            TenantPrincipal p = actor(
                SecurityContextHolder.getContext().getAuthentication());
            if (p == null) {
                throw new AccessDeniedException(
                    "Trusted tenant identity required");
            }
            return p;
        }
    }

    public static class TenantStore {
        private final JdbcTemplate jdbc;

        public TenantStore(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private Doc row(
                java.sql.ResultSet rs, int rowIndex)
                throws java.sql.SQLException {
            return new Doc(
                rs.getString("tenant_id"),
                rs.getLong("doc_id"),
                rs.getString("owner_issuer"),
                rs.getString("owner_subject"),
                rs.getString("status"),
                rs.getString("body"));
        }

        public Optional<Doc> find(String tenantId, long id) {
            List<Doc> rows = jdbc.query(
                "SELECT tenant_id, doc_id, owner_issuer, " +
                "owner_subject, status, body " +
                "FROM tenant_documents " +
                "WHERE tenant_id = ? AND doc_id = ?",
                this::row, tenantId, id);
            return rows.stream().findFirst();
        }

        public List<Doc> visible(TenantPrincipal actor) {
            return jdbc.query(
                "SELECT tenant_id, doc_id, owner_issuer, " +
                "owner_subject, status, body " +
                "FROM tenant_documents " +
                "WHERE tenant_id = ? AND " +
                "(status = 'PUBLISHED' OR " +
                "(owner_issuer = ? AND owner_subject = ?)) " +
                "ORDER BY doc_id",
                this::row, actor.tenantId(),
                actor.issuer(), actor.subject());
        }

        public int updateOwnedDraft(
                TenantPrincipal actor, long id, String body) {
            return jdbc.update(
                "UPDATE tenant_documents SET body = ? " +
                "WHERE tenant_id = ? AND doc_id = ? " +
                "AND owner_issuer = ? AND owner_subject = ? " +
                "AND status = 'DRAFT'",
                body, actor.tenantId(), id,
                actor.issuer(), actor.subject());
        }

        public int deleteOwnedDraft(
                TenantPrincipal actor, long id) {
            return jdbc.update(
                "DELETE FROM tenant_documents " +
                "WHERE tenant_id = ? AND doc_id = ? " +
                "AND owner_issuer = ? AND owner_subject = ? " +
                "AND status = 'DRAFT'",
                actor.tenantId(), id,
                actor.issuer(), actor.subject());
        }

        public void createDraft(
                TenantPrincipal actor, long id, String body) {
            jdbc.update(
                "INSERT INTO tenant_documents " +
                "(tenant_id, doc_id, owner_issuer, " +
                "owner_subject, status, body) " +
                "VALUES (?, ?, ?, ?, 'DRAFT', ?)",
                actor.tenantId(), id,
                actor.issuer(), actor.subject(), body);
        }
    }

    public static class TenantPolicy {
        private final TenantStore store;

        public TenantPolicy(TenantStore store) {
            this.store = store;
        }

        public boolean valid(Authentication auth) {
            return TrustedIdentity.actor(auth) != null;
        }

        private boolean owns(TenantPrincipal actor, Doc doc) {
            return doc != null
                && doc.tenantId().equals(actor.tenantId())
                && doc.ownerIssuer().equals(actor.issuer())
                && doc.ownerSubject().equals(actor.subject());
        }

        public boolean canRead(Authentication auth, long id) {
            TenantPrincipal actor = TrustedIdentity.actor(auth);
            if (actor == null) return false;
            return store.find(actor.tenantId(), id)
                .map(doc ->
                    "PUBLISHED".equals(doc.status()) ||
                    owns(actor, doc))
                .orElse(false);
        }

        public boolean canMutate(Authentication auth, long id) {
            TenantPrincipal actor = TrustedIdentity.actor(auth);
            if (actor == null) return false;
            return store.find(actor.tenantId(), id)
                .map(doc ->
                    "DRAFT".equals(doc.status()) &&
                    owns(actor, doc))
                .orElse(false);
        }

        public boolean canCreate(Authentication auth, long id) {
            return valid(auth) && id > 0;
        }
    }

    public static class TenantDocumentService {
        private final TenantStore store;
        private final Probe probe;

        public TenantDocumentService(
                TenantStore store, Probe probe) {
            this.store = store;
            this.probe = probe;
        }

        @PreAuthorize(
            "hasAuthority('DOC_READ') and " +
            "@tenantPolicy.canRead(authentication, #docId)"
        )
        public Doc read(@P("docId") long docId) {
            probe.mark("READ");
            TenantPrincipal actor = TrustedIdentity.requireActor();
            return store.find(actor.tenantId(), docId)
                .orElseThrow(() ->
                    new AccessDeniedException("Not visible"));
        }

        @PreAuthorize(
            "hasAuthority('DOC_READ') and " +
            "@tenantPolicy.valid(authentication)"
        )
        public List<Doc> list() {
            probe.mark("LIST");
            return store.visible(TrustedIdentity.requireActor());
        }

        @PreAuthorize(
            "hasAuthority('DOC_UPDATE') and " +
            "@tenantPolicy.canMutate(authentication, #docId)"
        )
        public Doc update(
                @P("docId") long docId, String body) {
            probe.mark("UPDATE");
            TenantPrincipal actor = TrustedIdentity.requireActor();
            if (store.updateOwnedDraft(actor, docId, body) != 1) {
                throw new AccessDeniedException(
                    "Update denied or stale");
            }
            return store.find(actor.tenantId(), docId)
                .orElseThrow(() ->
                    new AccessDeniedException("Not visible"));
        }

        @PreAuthorize(
            "hasAuthority('DOC_DELETE') and " +
            "@tenantPolicy.canMutate(authentication, #docId)"
        )
        public void delete(@P("docId") long docId) {
            probe.mark("DELETE");
            TenantPrincipal actor = TrustedIdentity.requireActor();
            if (store.deleteOwnedDraft(actor, docId) != 1) {
                throw new AccessDeniedException(
                    "Delete denied or stale");
            }
        }

        @PreAuthorize(
            "hasAuthority('DOC_CREATE') and " +
            "@tenantPolicy.canCreate(authentication, #docId)"
        )
        public Doc create(
                @P("docId") long docId, String body) {
            probe.mark("CREATE");
            TenantPrincipal actor = TrustedIdentity.requireActor();
            store.createDraft(actor, docId, body);
            return store.find(actor.tenantId(), docId)
                .orElseThrow();
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    public static class App {
        @Bean TenantStore tenantStore(JdbcTemplate jdbc) {
            return new TenantStore(jdbc);
        }

        @Bean("tenantPolicy")
        TenantPolicy tenantPolicy(TenantStore store) {
            return new TenantPolicy(store);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean TenantDocumentService tenantDocumentService(
                TenantStore store, Probe probe) {
            return new TenantDocumentService(store, probe);
        }
    }

    private void as(TenantPrincipal actor, String... authorities) {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                actor, "test-only",
                AuthorityUtils.createAuthorityList(authorities)));
        SecurityContextHolder.setContext(context);
    }

    private void alexInA() {
        as(ACTOR_A, "DOC_READ", "DOC_UPDATE",
            "DOC_DELETE", "DOC_CREATE");
    }

    private void alexInB() {
        as(ACTOR_B, "DOC_READ", "DOC_UPDATE",
            "DOC_DELETE", "DOC_CREATE");
    }

    @BeforeEach
    void resetFixture() {
        jdbc.update("DELETE FROM tenant_documents");

        jdbc.update(
            "INSERT INTO tenant_documents " +
            "(tenant_id, doc_id, owner_issuer, " +
            "owner_subject, status, body) VALUES (?, ?, ?, ?, ?, ?)",
            "TENANT_A", 42L, ISSUER,
            "a-user-100", "DRAFT", "A private 42");

        jdbc.update(
            "INSERT INTO tenant_documents " +
            "(tenant_id, doc_id, owner_issuer, " +
            "owner_subject, status, body) VALUES (?, ?, ?, ?, ?, ?)",
            "TENANT_B", 42L, ISSUER,
            "b-user-200", "DRAFT", "B private 42");

        jdbc.update(
            "INSERT INTO tenant_documents " +
            "(tenant_id, doc_id, owner_issuer, " +
            "owner_subject, status, body) VALUES (?, ?, ?, ?, ?, ?)",
            "TENANT_A", 43L, ISSUER,
            "a-user-100", "PUBLISHED", "A public 43");

        jdbc.update(
            "INSERT INTO tenant_documents " +
            "(tenant_id, doc_id, owner_issuer, " +
            "owner_subject, status, body) VALUES (?, ?, ?, ?, ?, ?)",
            "TENANT_B", 44L, ISSUER,
            "b-user-200", "PUBLISHED", "B public 44");

        probe.reset();
        alexInA();
    }

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void sameDocumentIdReallyExistsInTwoTenants() {
        Long matches = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tenant_documents WHERE doc_id = 42",
            Long.class);
        assertThat(matches).isEqualTo(2L);
    }

    @Test
    void sameUsernameDoesNotMeanSameIdentity() {
        assertThat(ACTOR_A.getName()).isEqualTo("alex");
        assertThat(ACTOR_B.getName()).isEqualTo("alex");
        assertThat(ACTOR_A.subject())
            .isNotEqualTo(ACTOR_B.subject());
        assertThat(ACTOR_A.tenantId())
            .isNotEqualTo(ACTOR_B.tenantId());
    }

    @Test
    void injectedServiceIsReallyProxied() {
        assertThat(dataSource).isNotNull();
        assertThat(AopUtils.isAopProxy(documents)).isTrue();
    }

    @Test
    void alexInTenantAReadsOnlyA42() {
        Doc doc = documents.read(42L);
        assertThat(doc.body()).isEqualTo("A private 42");
        assertThat(doc.tenantId()).isEqualTo("TENANT_A");
        assertThat(probe.count("READ")).isEqualTo(1);
    }

    @Test
    void sameNamedAlexInTenantBReadsOnlyB42() {
        alexInB();
        Doc doc = documents.read(42L);
        assertThat(doc.body()).isEqualTo("B private 42");
        assertThat(doc.tenantId()).isEqualTo("TENANT_B");
    }

    @Test
    void switchingAuthenticatedTenantChangesTheResultForId42() {
        assertThat(documents.read(42L).body())
            .isEqualTo("A private 42");
        alexInB();
        assertThat(documents.read(42L).body())
            .isEqualTo("B private 42");
        assertThat(probe.count("READ")).isEqualTo(2);
    }

    @Test
    void sameUsernameWithDifferentSubjectCannotReadA42Draft() {
        as(new TenantPrincipal(
            ISSUER, "a-user-other", "alex", "TENANT_A"),
            "DOC_READ");
        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void usingASubjectInTenantBDoesNotImpersonateB42Owner() {
        as(new TenantPrincipal(
            ISSUER, "a-user-100", "alex", "TENANT_B"),
            "DOC_READ");
        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void sameSubjectButDifferentIssuerDoesNotOwnA42() {
        as(new TenantPrincipal(
            "https://other-idp.example.test",
            "a-user-100", "alex", "TENANT_A"),
            "DOC_READ");
        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void tenantAActorCannotReadBOnlyPublishedId44() {
        assertThatThrownBy(() -> documents.read(44L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void tenantBActorCannotReadAOnlyPublishedId43() {
        alexInB();
        assertThatThrownBy(() -> documents.read(43L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void publishedDocumentInTheSameTenantIsReadable() {
        assertThat(documents.read(43L).body())
            .isEqualTo("A public 43");
    }

    @Test
    void updateAuthorityCannotReplaceReadAuthority() {
        as(ACTOR_A, "DOC_UPDATE");
        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void untrustedStringPrincipalWithSameNameIsDenied() {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "alex", "test-only",
                AuthorityUtils.createAuthorityList("DOC_READ")));
        SecurityContextHolder.setContext(context);

        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void updateA42DoesNotChangeB42() {
        assertThat(documents.update(42L, "Changed A").body())
            .isEqualTo("Changed A");
        assertThat(store.find("TENANT_B", 42L).orElseThrow().body())
            .isEqualTo("B private 42");
        assertThat(probe.count("UPDATE")).isEqualTo(1);
    }

    @Test
    void updateB42DoesNotChangeA42() {
        alexInB();
        assertThat(documents.update(42L, "Changed B").body())
            .isEqualTo("Changed B");
        assertThat(store.find("TENANT_A", 42L).orElseThrow().body())
            .isEqualTo("A private 42");
    }

    @Test
    void sameNameImpostorCannotUpdateOtherOwnersDraft() {
        as(new TenantPrincipal(
            ISSUER, "a-user-other", "alex", "TENANT_A"),
            "DOC_UPDATE");
        assertThatThrownBy(() ->
            documents.update(42L, "Tampered"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.find("TENANT_A", 42L).orElseThrow().body())
            .isEqualTo("A private 42");
        assertThat(probe.count("UPDATE")).isZero();
    }

    @Test
    void publishedDocumentCannotBeUpdatedAsDraft() {
        assertThatThrownBy(() ->
            documents.update(43L, "Invalid"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.find("TENANT_A", 43L).orElseThrow().body())
            .isEqualTo("A public 43");
    }

    @Test
    void deletingA42DoesNotDeleteB42() {
        documents.delete(42L);
        assertThat(store.find("TENANT_A", 42L)).isEmpty();
        assertThat(store.find("TENANT_B", 42L)).isPresent();
        assertThat(probe.count("DELETE")).isEqualTo(1);
    }

    @Test
    void deletingB42DoesNotDeleteA42() {
        alexInB();
        documents.delete(42L);
        assertThat(store.find("TENANT_B", 42L)).isEmpty();
        assertThat(store.find("TENANT_A", 42L)).isPresent();
    }

    @Test
    void create99InBothTenantsProducesTwoSeparateRows() {
        Doc createdA = documents.create(99L, "New A");
        alexInB();
        Doc createdB = documents.create(99L, "New B");

        assertThat(createdA.tenantId()).isEqualTo("TENANT_A");
        assertThat(createdB.tenantId()).isEqualTo("TENANT_B");
        assertThat(createdA.ownerSubject()).isEqualTo("a-user-100");
        assertThat(createdB.ownerSubject()).isEqualTo("b-user-200");
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tenant_documents WHERE doc_id = 99",
            Long.class);
        assertThat(count).isEqualTo(2L);
    }

    @Test
    void duplicate99WithinSameTenantMustNotOverwrite() {
        documents.create(99L, "First");
        assertThatThrownBy(() ->
            documents.create(99L, "Overwrite attempt"))
            .isInstanceOf(DataIntegrityViolationException.class);
        assertThat(store.find("TENANT_A", 99L).orElseThrow().body())
            .isEqualTo("First");
    }

    @Test
    void listInTenantAContainsNoTenantBRows() {
        List<Doc> results = documents.list();
        assertThat(results.stream().map(Doc::id).toList())
            .containsExactly(42L, 43L);
        assertThat(results)
            .allMatch(doc -> "TENANT_A".equals(doc.tenantId()));
    }

    @Test
    void listInTenantBContainsNoTenantARows() {
        alexInB();
        List<Doc> results = documents.list();
        assertThat(results.stream().map(Doc::id).toList())
            .containsExactly(42L, 44L);
        assertThat(results)
            .allMatch(doc -> "TENANT_B".equals(doc.tenantId()));
    }

    @Test
    void aSameNameDifferentSubjectSeesPublicButNotOtherDraft() {
        as(new TenantPrincipal(
            ISSUER, "a-user-other", "alex", "TENANT_A"),
            "DOC_READ");
        assertThat(documents.list().stream().map(Doc::id).toList())
            .containsExactly(43L);
    }

    @Test
    void missingCreateAuthorityDeniesBeforeMethodBody() {
        as(ACTOR_A, "DOC_READ");
        assertThatThrownBy(() ->
            documents.create(99L, "No permission"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("CREATE")).isZero();
    }

    @Test
    void stringPrincipalCannotListEvenWithReadAuthority() {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "alex", "test-only",
                AuthorityUtils.createAuthorityList("DOC_READ")));
        SecurityContextHolder.setContext(context);

        assertThatThrownBy(documents::list)
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("LIST")).isZero();
    }

    @Test
    void directQueryByIdAloneIsAmbiguousAndMustNotBeUsed() {
        Long matches = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tenant_documents WHERE doc_id = ?",
            Long.class, 42L);
        assertThat(matches).isEqualTo(2L);
        assertThat(store.find("TENANT_A", 42L)).isPresent();
        assertThat(store.find("TENANT_B", 42L)).isPresent();
    }
}
```

### 7.4. Tại sao ví dụ kiểm thử đúng lỗi collision?

**Thứ nhất, test fixture không né trường hợp xấu.** Hai hàng có `doc_id=42`, tên đăng nhập `alex` giống nhau, nhưng `tenant_id` và `owner_subject` khác. Nếu repository vô tình truy vấn chỉ theo ID, test `directQueryByIdAloneIsAmbiguousAndMustNotBeUsed` chứng minh có hai kết quả.

**Thứ hai, principal được thử với nhiều biến thể.** Cùng username, khác subject trong cùng tenant; cùng username và subject của A nhưng tenant B; cùng subject nhưng issuer khác. DRAFT owner check phải từ chối. Điều này giúp phát hiện policy yếu kiểu `owner_username = authentication.name`.

**Thứ ba, các thao tác mutating dùng SQL có scope đầy đủ.** `UPDATE` và `DELETE` không chỉ dựa vào precheck: chúng ràng buộc `tenant_id`, `doc_id`, `owner_issuer`, `owner_subject`, `status='DRAFT'` ở thời điểm ghi. Cách này còn giảm rủi ro TOCTOU nếu owner hoặc status đổi sau pre-authorization.

**Thứ tư, CREATE không cho client chọn tenant hoặc owner.** Service chỉ nhận `docId` và `body`, còn tenant/issuer/subject được lấy từ trusted principal. Composite PK cho phép tenant A và B cùng có tài liệu 99 mà không ghi đè nhau.

**Thứ năm, kiểm tra cả code path bảo mật và data layer.** `AopUtils.isAopProxy(documents)` chứng minh service là Spring-managed proxy; `Probe` chứng minh `@PreAuthorize` deny trước khi method body chạy; SQL test chứng minh repository vẫn scoped theo tenant ngay khi method được phép.

### 7.5. Chạy test và kết quả kỳ vọng

Trong thư mục `tenant-collision-tests`:

```bash
gradle test --tests demo.TenantCollisionSecurityTest
```

Nếu có Gradle Wrapper, dùng `./gradlew test --tests demo.TenantCollisionSecurityTest` trên Linux/macOS hoặc `gradlew.bat test --tests demo.TenantCollisionSecurityTest` trên Windows.

**Kỳ vọng:** **28 JUnit tests** thành công và Gradle báo `BUILD SUCCESSFUL` khi dependency/context đúng. Đây là kết quả **dự kiến từ code**, không phải log thu được từ một lượt thực thi. Báo cáo HTML nằm ở `build/reports/tests/test/index.html`.

| Nhóm test | Điều chứng minh |
| --- | --- |
| Fixture/identity | Hai tenant cùng ID=42, cùng username nhưng khác subject/tenant |
| Spring proxy | `@EnableMethodSecurity` hoạt động trên bean thực |
| Đọc A/B #42 | Cùng ID nhưng trả đúng nội dung từng tenant |
| Đổi tenant giữa calls | Không dùng lại kết quả của tenant trước |
| Impostor subject/issuer | Username trùng không đủ để qua owner policy |
| ID chỉ có ở tenant kia | Không thể đọc dù resource published |
| Authority | `DOC_UPDATE` không thay `DOC_READ` |
| UPDATE/DELETE A/B #42 | Chỉ bản ghi đúng tenant được thay đổi |
| CREATE 99 ở A/B | Hai bản ghi độc lập, không ghi đè |
| Duplicate ID cùng tenant | Khóa ghép ngăn overwrite |
| LIST | Không trộn hàng giữa tenants, ngay cả cùng username |
| String principal | Không suy ra tenant tin cậy chỉ từ `getName()` |
| SQL thiếu tenant | ID đơn lẻ không đủ định vị một hàng |

**Giới hạn phải nhớ:** test cố tình inject `TenantPrincipal` đã được coi là authenticated vào SecurityContext. Nó **không** chứng minh HTTP/OIDC auth filter chống client giả token/tenant. H2 cũng **không có** PostgreSQL RLS trong ví dụ này. Chỉ có thể tuyên bố demo kiểm thử **Spring Method Security + tenant-aware JDBC repository + composite keys**.

## 8. Mở rộng test trong ứng dụng thực

### 8.1. Kiểm thử HTTP, JWT và tenant switching

Với REST API, nên tạo **hai token thật được ký bởi IdP test**, đều có username `alex` nhưng `sub` và active tenant khác nhau. Gửi cùng request `GET /documents/42` với từng token và so sánh response:

- Token tenant A chỉ được body `A private 42`.
- Token tenant B chỉ được body `B private 42`.
- Token chỉ đổi header `X-Tenant-Id` sang B nhưng không có B membership phải bị chặn.
- Token giả/sai issuer/sai audience/hết hạn phải bị từ chối tại authentication boundary.
- JWT chứa tenant list và active tenant phải được verify membership trước khi tạo principal.

**Không** đặt client-supplied `tenantId` vào `SecurityContext` như thể nó đã được xác thực. Nếu username được thay đổi, owner key dựa vào stable subject vẫn phải giữ đúng quyền; khi subject/issuer thay đổi vì federation account migration, cần quy trình mapping có kiểm soát.

### 8.2. Kiểm thử JPA/Hibernate

Nếu dùng JPA:

- `findById(42L)` chỉ an toàn khi `42` thực sự là global primary key duy nhất hoặc persistence layer đã áp đúng tenant.
- Với business ID chỉ duy nhất **trong tenant**, nên dùng `@EmbeddedId` hoặc `@IdClass`, hay global surrogate ID kết hợp `tenant_id` trong lookup/policy.
- Foreign keys/joins cần tenant-scoped; `attachment.document_id=42` không đủ nếu 42 tồn tại ở A và B.
- Kiểm tra EntityManager first-level cache, second-level cache và Hibernate multi-tenancy tenant resolver khi context đổi; cache không được key chỉ theo local ID.
- Viết integration test trên **DB dialect production** cho cả JPQL/native query/bulk UPDATE/DELETE và pagination.

### 8.3. Spring Security ACL, `PermissionEvaluator` và ObjectIdentity

`hasPermission(#id, 'Document', 'READ')` gọi `PermissionEvaluator` dựa trên target ID/type. Nếu DB ACL dùng cùng `ObjectIdentity(type='Document', id=42)` cho hai tenant, **hai ACL có nguy cơ đụng identity**. Phải làm khóa ACL nhận diện tenant: có thể dùng globally unique surrogate object ID hoặc một quy ước domain identity có tenant namespace rõ, consistent khi tạo và đọc ACL.

`PrincipalSid("alex")` cũng có thể đụng giữa tenant nếu dùng chung kho ACL. Nếu ACL policy có principal SID tùy biến, phải ánh xạ theo stable tenant-scoped identity/issuer/sub; không coi `PrincipalSid(username)` là duy nhất toàn hệ thống. Các test ACL nên tạo hai ObjectIdentity cùng local ID nhưng khác tenant và hai SID cùng username nhưng khác logical identity, chứng minh ACE không vượt tenant.

### 8.4. Cache và background jobs

Cache keys đáng tin phải phân biệt tenant, object type, ID và actor/policy context tùy tính chất cache. Ví dụ **không an toàn**:

```java
// Phản ví dụ: có thể trả kết quả tenant A cho tenant B.
@Cacheable("documents")
public Document findById(long id) { ... }
```

Nếu key chỉ là 42, kết quả của A có thể bị phục vụ cho B. Thiết kế nên bao gồm tenant trong cache key và kiểm tra owner/sensitivity tại đúng lớp. Tương tự với cache authorization: không dùng `(username, id)` khi username trùng giữa tenant.

Scheduled jobs và message consumers không phải HTTP request có sẵn SecurityContext; hãy truyền tenant context từ **envelope đã xác thực** hoặc workflow phía server và kiểm soát phạm vi task. Không sử dụng “tenant mặc định toàn quyền” cho thuận tiện. Test retry, dead-letter, delayed task sau khi quyền bị thu hồi và export file per tenant.

### 8.5. PostgreSQL Row-Level Security (RLS)

RLS có thể giúp chặn SQL vô tình thiếu tenant predicate khi app DB role không bypass policy. Nhưng phải thử trên PostgreSQL thật, với DB role **không là table owner, không SUPERUSER/BYPASSRLS**. Khi dùng `set_config('app.tenant_id', ..., true)`, setting phải trong transaction cùng JDBC connection; `false` ở session có thể rò qua connection pool.

Cảnh báo: custom `app.tenant_id` có thể được DB session tự đặt nên **không phải identity được PostgreSQL xác thực**; một SQL injection cho phép đổi setting có thể vượt ý định. Test RLS và ứng dụng là **hai lớp bổ sung**, không tự thay thế nhau. Bộ H2 test ở mục 7 **không kiểm tra RLS**.

## 9. Các lỗi thường gặp và cách phát hiện

| Lỗi | Tại sao nguy hiểm | Test phát hiện |
| --- | --- | --- |
| Chỉ `findById(42)` | Hai tenant đều có ID 42 | Raw count=2; query scoped phải ra 1 |
| So owner bằng username `alex` | Hai principal khác nhau có cùng tên | Same username, different subject test |
| Chỉ so `subject` | Một số IDP/tenants dùng namespace khác nhau | Same subject, different issuer test |
| Chỉ so tenant khi đọc DRAFT | User khác trong cùng tenant đọc private data | Same tenant, different subject test |
| Trust `X-Tenant-Id` | Client tự chọn tenant không có membership | HTTP token/header switch negative test |
| Global cache key `documentId` | A/B cache collision | Cùng ID giữa 2 tenant, đọc lần lượt |
| JPA `Long @Id` với local IDs | ID collision trong persistence context | `@EmbeddedId` + integration tests |
| SQL UPDATE chỉ có `WHERE doc_id` | Một action có thể sửa cả hai tenant | UPDATE A 42, B 42 phải giữ nguyên |
| SQL DELETE chỉ có `WHERE doc_id` | Xóa dữ liệu tenant khác | DELETE A 42, B 42 phải còn |
| Role check mà thiếu object check | `DOC_READ` không cấp quyền trên mọi DRAFT | Non-owner trong cùng tenant bị deny |
| Scope đọc nhưng không scope LIST/EXPORT | Endpoint bulk có thể lộ hàng | LIST/EXPORT cross tenant tests |
| Kiểm tra owner trước, update không có điều kiện | Race/TOCTOU khi owner/status thay đổi | Conditional SQL và version tests |
| Bỏ qua same-name sau tenant switch | Dùng lại token/cache/identity cũ | A rồi B cùng ID 42, nội dung phải khác |
| RLS test bằng admin DB role | Chủ bảng/BYPASSRLS có thể vượt policy | Kiểm tra `current_user` và role attrs |
| Coi H2 là test RLS | H2 không thay thế PostgreSQL policy | Testcontainers PostgreSQL với RLS thật |

### Checklist negative-path quan trọng

1. **Cùng local ID ở A/B:** cả hai positive read phải khác body, và không có trường hợp nào đọc bản ghi tenant đối diện.
2. **Cùng username ở A/B:** xác minh username giống, issuer/sub và tenant khác; không chấp nhận owner bằng tên hiển thị.
3. **Sai subject cùng tenant:** DENY khi DRAFT, kể cả có `DOC_READ`.
4. **Sai issuer cùng subject:** DENY nếu ownership theo issuer+subject.
5. **Sai tenant với ID khác:** không trả cả record PUBLISHED của tenant khác.
6. **Thiếu quyền chức năng:** deny trước body, không có side effects.
7. **UPDATE/DELETE:** dữ liệu tenant khác phải **không thay đổi**.
8. **CREATE/duplicate:** cùng ID ở hai tenant được phép, trong một tenant không overwrite.
9. **LIST/search/aggregation/export:** không trộn tenant và không lộ count, metadata hoặc trường nhạy cảm.
10. **Cache/pool/job:** khi đổi tenant, mọi layer phải dùng đúng context, không tái sử dụng kết quả từ tenant trước.

## 10. Bài tập

**Bài A — email cũng trùng:** Cho cả hai actor cùng email `alex@example.test`. Viết test chứng minh policy vẫn phân biệt actor bằng issuer+subject+tenant, không dùng email làm owner key.

**Bài B — role reviewer:** Thêm `DOC_REVIEW` cho một người cùng tenant nhưng không phải owner; cho họ đọc `SUBMITTED` và chặn người cùng username ở tenant khác.

**Bài C — Hibernate:** Tạo entity dùng `@EmbeddedId(tenantId,docId)`, thêm attachment FK ghép, kiểm thử JPQL + native SQL đều cần tenant.

**Bài D — cache collision:** Thêm `@Cacheable` cho read theo ID đơn lẻ, chạy A/B cùng 42 để quan sát nguy cơ trong test cô lập; sửa key để chứa tenant và audit cache invalidation.

**Bài E — tenant switching:** Một actor thuộc hai tenant. Thiết kế bước xác nhận membership trước khi đổi active tenant; đảm bảo cache và repository không dùng context cũ.

**Bài F — import/export:** Hai tenant đều có file `report-42.csv`. Kiểm tra file path, job ID, download token và quyền của actor không thể lẫn tenant.

**Bài G — PostgreSQL RLS:** Viết policy `USING (tenant_id = current_setting(...))`, dùng DB role không bypass, test SELECT/UPDATE/DELETE chéo tenant và transaction-local context.

**Bài H — TOCTOU:** Sau khi `@PreAuthorize` cho UPDATE, đổi status thành PUBLISHED trong transaction cạnh tranh. Xác minh conditional UPDATE trả 0 và không có ghi trái policy.

## 11. Tổng kết

Để kiểm thử cách ly tenant cho đúng, **đừng chỉ chọn ID và username đều khác nhau**; hãy cố ý tạo tình huống:

```text
TENANT_A / doc_id=42 / username=alex / issuer=I / sub=A100
TENANT_B / doc_id=42 / username=alex / issuer=I / sub=B200
```

Khóa bản ghi là **tenant + ID**; owner identity là **tenant + issuer + subject**, không phải username. Spring Security quyết định quyền chức năng và policy từng object; repository/SQL phải giữ tenant predicate; UPDATE/DELETE phải giữ cả owner/status tại lúc ghi. Cần test cả kết quả được phép và đường bị chặn, đồng thời xác minh dữ liệu tenant kia **không hề bị thay đổi**.

Một hệ thống chỉ vượt qua bài test khi hai người tên `alex` đọc cùng ID 42 mà **mỗi người nhận đúng dữ liệu của mình**, không thể sửa/xóa bản ghi của người kia, không bị trộn kết quả ở LIST/cache/export và không dựa vào thông tin tenant do client tự khai.

## Tài liệu tham khảo

- Spring Security 6.5 — Method Security, `@EnableMethodSecurity`, `@PreAuthorize`, SpEL custom bean và `@P`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- OWASP API1:2023 — Broken Object Level Authorization (BOLA), kiểm tra quyền trên mỗi object ID: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API3:2023 — Broken Object Property Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/
- OWASP API5:2023 — Broken Function Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/
- OpenID Connect Core — Issuer/Subject claims: https://openid.net/specs/openid-connect-core-1_0.html
- PostgreSQL — Row Security Policies: https://www.postgresql.org/docs/17/ddl-rowsecurity.html
- Spring Boot 3.5 — SQL Database Initialization: https://docs.spring.io/spring-boot/3.5/reference/howto/data-initialization.html
