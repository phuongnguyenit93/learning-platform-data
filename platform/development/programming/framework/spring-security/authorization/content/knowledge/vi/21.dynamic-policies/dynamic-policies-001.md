# Kho quyền động và nguồn dữ liệu chuẩn của chính sách

> **Chủ đề:** Spring Security – authorization → **Chính sách động**. Bài này hướng dẫn thiết kế kho quyền/chính sách có thể đổi khi hệ thống đang chạy, xác định **source of truth** cho từng thông tin authorization, xuất bản chính sách theo revision, đánh giá quyền với Spring Security và xử lý cache, đa tenant, audit, rollback, tranh chấp và lỗi hạ tầng. Ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x, JDBC, H2 và JUnit.

## 1. Bài toán: quyền thay đổi không cần deploy

Một ứng dụng có thể bắt đầu bằng:

~~~java
@PreAuthorize("hasRole('EDITOR')")
public void renameDocument(Long id, String title) {
    // ...
}
~~~

Lúc ấy `ROLE_EDITOR` được kiểm tra từ `Authentication.getAuthorities()`, nhưng các câu hỏi khó vẫn còn:

- EDIT đối với **loại tài nguyên nào**, trong **tenant nào**?
- Admin thu hồi EDIT ở 10:00 thì request lúc 10:01 có dùng quyền cũ không?
- Một người có role được grant và role bị deny thì rule nào ưu tiên?
- Những rule nào **đang active** nếu có draft mới?
- Nguồn nào đúng khi token, policy database và cache tại hai node khác nhau?
- Ai được sửa/publish policy, ai được duyệt, rollback và audit thế nào?
- Kho policy chết hoặc không có rule: có cho phép theo mặc định không?

**Chính sách động** nghĩa là decision thay đổi khi cấu hình quyền có hiệu lực thay đổi, không nhất thiết sửa code hoặc restart. Nhưng điều đó chỉ an toàn khi dữ liệu quyền được kiểm soát bởi nơi có thẩm quyền, có phiên bản và có cách thi hành đúng.

Ví dụ:

~~~text
Tenant acme, revision 1:
  ROLE_READER  READ -> ALLOW
  ROLE_EDITOR  EDIT -> ALLOW
  ROLE_BLOCKED READ -> DENY
  ROLE_BLOCKED EDIT -> DENY

Tenant beta, revision 1:
  ROLE_READER  READ -> ALLOW
  ROLE_EDITOR  EDIT -> ALLOW
~~~

Alice có READER + EDITOR tại acme thì được READ/EDIT tài liệu acme. Bob có READER tại beta **không** vì thế được đọc acme. Carol có READER + BLOCKED tại acme nên READ bị từ chối theo quy tắc **explicit DENY overrides ALLOW** do ứng dụng định nghĩa.

## 2. Chính sách, entitlement, membership, resource: nguồn chuẩn của từng loại

**Source of truth** là nguồn có thẩm quyền đối với một loại sự thật, không nhất thiết là một database duy nhất cho toàn hệ thống.

| Loại dữ liệu | Nguồn chuẩn thường gặp | Những thứ không thay được nguồn chuẩn |
| --- | --- | --- |
| Danh tính, tài khoản, trạng thái active | IAM/IdP, identity directory | Tên từ request body, header chưa được xác thực |
| Membership user–tenant–role | Membership DB hoặc group service có hợp đồng rõ | JWT cũ sau khi role bị thu hồi |
| Role và permission catalog | IAM/policy catalog được quản trị | Tên role tùy ý do client gửi |
| Policy đang active | Policy store + active revision pointer | Draft, bản cache cũ, replica chưa sync |
| Resource tenant/owner/status | Domain database | `tenantId` trong URL dùng làm bằng chứng sở hữu |
| Business entitlement/license | Billing/entitlement service | Feature flag chỉ ở frontend |
| Authorization decision | PDP đánh giá theo chính sách và input hợp lệ | Một boolean cache thiếu revision |
| Cache policy | Bản sao tối ưu hiệu năng | Nơi tự tạo/ghi đè chính sách gốc |
| Audit | Hệ thống log/audit append-only | In-memory logs mất khi restart |

Ví dụ một request EDIT document:

~~~text
Authentication verified principal = "alice"
Target tenant selector = "acme"
Resource = Document#101
Resource DB: Document#101.tenant = "acme"
Membership DB: alice has ROLE_EDITOR active in acme
Policy head: acme revision 7 is active
Policy rules rev 7: ROLE_EDITOR EDIT ALLOW
Conditions: document not locked, tenant active
=> decision ALLOW
~~~

Không có một yếu tố đơn lẻ nào đủ: `tenantId=acme` trong URL chỉ là đối tượng truy cập mong muốn, không chứng minh actor thuộc tenant đó. Một role trong JWT không đồng nghĩa có membership hiện hành. Một policy ALLOW không cho phép thao tác lên một resource không tồn tại hoặc thuộc tenant khác.

### 2.1. Authentication không tự là kho policy động

Spring Security chứa các `GrantedAuthority` trong `Authentication`. Nếu policy chỉ dùng `hasAuthority('DOC_EDIT')` và authority này được chụp vào JWT khi đăng nhập, token cũ có thể tiếp tục giữ quyền dù administrator vừa thu hồi role-permission mapping.

~~~text
T1: JWT của Alice chứa ROLE_EDITOR
T2: Admin publish policy bỏ quyền EDIT của ROLE_EDITOR
T3: JWT chưa hết hạn vẫn chứa ROLE_EDITOR
T4: hasRole("EDITOR") có thể còn true
T5: PDP đọc active policy mới -> EDIT DENY
~~~

Khi triển khai quyền động, cần phân biệt **xác thực danh tính** với **dữ liệu policy có hiệu lực**. Cập nhật policy không tự làm refresh JWT; thay role mapping trong authentication không tự invalidate policy cache. Nếu membership do IAM quản lý, phải thiết kế cách PDP nhận membership mới hoặc chấp nhận một cửa sổ stale có giới hạn.

### 2.2. Một hay nhiều nguồn chuẩn?

Nếu IAM là nguồn chuẩn membership, tránh cho policy store tự ghi membership độc lập rồi cả hai có thể mâu thuẫn. Có thể dùng policy store làm **read model** của membership, nhưng cần mô tả thứ tự sự kiện, version, retry và cách reconcile. Nếu domain service sở hữu document, policy service không tự suy ra document còn tồn tại chỉ dựa vào một ACL entry cũ.

**Quy tắc:** mỗi fact có owner rõ ràng; những bản sao có freshness/consistency contract và quy trình phục hồi từ source of truth.

## 3. Kiến trúc PAP, PDP, PEP, PIP

Các thuật ngữ giúp phân chia trách nhiệm:

| Thuật ngữ | Nhiệm vụ | Ví dụ trong Spring |
| --- | --- | --- |
| PAP – Policy Administration Point | Soạn/duyệt/xuất bản chính sách | PolicyPublisher, admin workflow |
| PDP – Policy Decision Point | Tính ALLOW/DENY trên request + policy hiện hành | PolicyGate hoặc custom AuthorizationManager |
| PEP – Policy Enforcement Point | Chặn hành động khi PDP deny | Method Security, HTTP AuthorizationFilter |
| PIP – Policy Information Point | Trả attributes đáng tin cho PDP | Membership DB, resource DB, IAM |
| Policy store | Lưu rule, revision và active pointer | SQL hoặc policy service |
| Audit | Lưu ai thay policy/decision dưới revision nào | Audit DB, stream, SIEM |

~~~text
               Admin (PAP)
                   |
       draft -> validate -> approve
                   |
             publish revision
                   |
             Policy Store
                   |
           active revision=N
                   v
request -> Spring PEP -> PolicyGate/PDP
                             |        \
                             |         \-> PIP memberships/resources
                             |
                         ALLOW / DENY
                             |
            DENY --> reject, no mutation
            ALLOW --> application service / DB
~~~

Các role quản trị kho policy rất nhạy cảm: một người có thể cấp quyền cho hàng nghìn user chỉ bằng thay một rule. Không tự cho người có quyền cập nhật tài liệu cũng có quyền chỉnh policy. Tenant admin chỉ nên được quản trị policy **trong tenant mình**, không tự cấp quyền system-wide.

## 4. Mô hình dữ liệu của một kho policy có revision

Bài sử dụng bốn bảng:

| Bảng | Thuộc tính trọng tâm | Ý nghĩa |
| --- | --- | --- |
| `policy_head` | tenant_id, active_revision | Con trỏ revision có hiệu lực |
| `policy_rule` | tenant_id, revision, role, action, effect | Các rule bất biến trong snapshot của revision |
| `tenant_membership` | principal, tenant_id, role, active | Role của user **trong tenant**, còn hiệu lực |
| `tenant_document` | id, tenant_id, title | Nguồn xác định resource thuộc tenant nào |

Một policy:

~~~json
{
  "tenantId": "acme",
  "revision": 7,
  "role": "ROLE_EDITOR",
  "action": "EDIT",
  "effect": "ALLOW"
}
~~~

### 4.1. Bản đang có hiệu lực và bản draft khác nhau

~~~text
acme: revision 6 ACTIVE
acme: revision 7 DRAFT, chưa được dùng

PUBLISH:
  BEGIN TRANSACTION
  insert toàn bộ policy_rule revision 7
  update policy_head.active_revision=7
  COMMIT

Request sau publish mới đọc revision 7.
~~~

Nếu insert được 8/10 rules rồi lỗi trước commit, transaction phải rollback để `active_revision` vẫn trỏ revision 6. Không sửa trực tiếp nhiều row của revision ACTIVE trong các giao dịch tách rời vì request có thể nhìn thấy policy nửa cũ nửa mới.

### 4.2. Snapshot và patch

- **Full snapshot:** mỗi revision lưu *toàn bộ* các rule có hiệu lực của scope. Rule vắng mặt ở revision mới đồng nghĩa rule đó bị thu hồi.
- **Patch/delta:** chỉ lưu thay đổi so với bản cũ. PDP phải tái dựng và giải quyết thứ tự, xung đột, rollback.

Bài chọn full snapshot: dễ kiểm thử, debug và tái hiện một quyết định lịch sử. Production cần thêm bảng policy_revision chứa status, author, approver, checksum, reason, effective time, audit, outbox và retention.

### 4.3. Thiết kế precedence và default-deny

Ví dụ custom PDP đặt quy tắc:

~~~text
effects = mọi rule phù hợp
          với active membership của principal,
          đúng tenant, action, revision

if effects có DENY: return DENY
if effects có ALLOW: return ALLOW
return DENY
~~~

Không được tự giả định mọi policy engine đều dùng DENY-overrides. Chọn một combining algorithm, công bố, kiểm thử và dùng nhất quán. Trong bài, mọi rule lạ/không có rule đều **không được phép**. Không catch DB exception rồi trả ALLOW để duy trì availability.

## 5. Ứng dụng Spring Boot + Spring JDBC (Java 17+)

Ví dụ runnable trong một dự án Spring Boot 3.x có plugins Gradle tương thích, Spring Security 6.x và H2. Dùng Spring JDBC vì có thể nhìn rõ SQL JOIN giữa active policy, membership và tài nguyên.

Mã gồm:
- `DynamicPolicyApplication` bật Method Security.
- `PolicyGate` đọc chính sách có hiệu lực mỗi request.
- `DocumentService` đọc tài liệu có chốt `@PreAuthorize`, sửa tài liệu có chốt trong transaction.
- `PolicyPublisher` publish full snapshot atomic.
- Integration tests chứng minh policy và membership đổi **mà không đổi mã Java**.

### 5.1. Dependencies

`build.gradle` trong project đã thiết lập plugins Java, Spring Boot và dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không cần web starter nếu chỉ test Spring-managed services. Spring Security starter **không tự bật** `@EnableMethodSecurity`.

### 5.2. Test datasource

**`src/test/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:h2:mem:dynamic_policy;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.continue-on-error=false
~~~

H2 in-memory không phải production policy store. Dùng migration Flyway/Liquibase và test dialect/transaction isolation trên cơ sở dữ liệu đích.

### 5.3. SQL schema

**`src/test/resources/schema.sql`**

~~~sql
create table policy_head (
    tenant_id varchar(40) primary key,
    active_revision bigint not null,
    constraint chk_active_revision check (active_revision > 0)
);

create table policy_rule (
    tenant_id varchar(40) not null,
    revision bigint not null,
    role varchar(50) not null,
    action varchar(24) not null,
    effect varchar(8) not null,
    primary key (tenant_id, revision, role, action),
    foreign key (tenant_id) references policy_head(tenant_id),
    constraint chk_policy_effect check (effect in ('ALLOW','DENY'))
);

create table tenant_membership (
    principal varchar(64) not null,
    tenant_id varchar(40) not null,
    role varchar(50) not null,
    active boolean not null,
    primary key (principal, tenant_id, role),
    foreign key (tenant_id) references policy_head(tenant_id)
);

create table tenant_document (
    id bigint primary key,
    tenant_id varchar(40) not null,
    title varchar(160) not null,
    foreign key (tenant_id) references policy_head(tenant_id)
);

create index idx_policy_rule on policy_rule(tenant_id, revision, action);
create index idx_membership on tenant_membership(principal, tenant_id, active);
~~~

Bảng `policy_rule` dùng PK ngăn một role có hai effect khác nhau cho cùng action/revision/tenant. Trạng thái cho phép/từ chối bị giới hạn ALLOW/DENY từ database. `tenant_document` chứa tenant thực tế, không nhận từ client. Với production, nên thêm constraints, timestamps, policy author/approver, immutable history/audit và revision state table.

### 5.4. Seed dữ liệu

**`src/test/resources/data.sql`**

~~~sql
insert into policy_head(tenant_id, active_revision)
values ('acme', 1), ('beta', 1);

insert into policy_rule(tenant_id, revision, role, action, effect)
values
  ('acme', 1, 'ROLE_READER', 'READ', 'ALLOW'),
  ('acme', 1, 'ROLE_EDITOR', 'EDIT', 'ALLOW'),
  ('acme', 1, 'ROLE_BLOCKED', 'READ', 'DENY'),
  ('acme', 1, 'ROLE_BLOCKED', 'EDIT', 'DENY'),
  ('beta', 1, 'ROLE_READER', 'READ', 'ALLOW'),
  ('beta', 1, 'ROLE_EDITOR', 'EDIT', 'ALLOW');

insert into tenant_membership(principal, tenant_id, role, active)
values
  ('alice', 'acme', 'ROLE_READER', true),
  ('alice', 'acme', 'ROLE_EDITOR', true),
  ('bob', 'beta', 'ROLE_READER', true),
  ('carol', 'acme', 'ROLE_READER', true),
  ('carol', 'acme', 'ROLE_BLOCKED', true);

insert into tenant_document(id, tenant_id, title)
values
  (101, 'acme', 'ACME-original'),
  (202, 'beta', 'BETA-original');
~~~

Alice có READ + EDIT trên acme; Bob có READ trên beta; Carol có cả READ ALLOW và READ DENY nhưng bị chặn theo DENY-overrides.

### 5.5. Boot application

**`src/main/java/demo/policy/DynamicPolicyApplication.java`**

~~~java
package demo.policy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class DynamicPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(DynamicPolicyApplication.class, args);
    }
}
~~~

### 5.6. Policy Decision Point: PolicyGate

**`src/main/java/demo/policy/PolicyGate.java`**

~~~java
package demo.policy;

import java.util.List;
import java.util.Set;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("policyGate")
public class PolicyGate {
    private static final Set<String> ACTIONS = Set.of("READ", "EDIT");

    private final JdbcTemplate jdbc;

    public PolicyGate(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean allowed(
            Authentication authentication,
            String tenantId,
            Long documentId,
            String action) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken
                || tenantId == null
                || !tenantId.matches("[a-z][a-z0-9-]{1,39}")
                || documentId == null
                || documentId <= 0
                || action == null
                || !ACTIONS.contains(action)) {
            return false;
        }

        Long count = jdbc.queryForObject(
                """
                select count(*)
                  from tenant_document
                 where id = ? and tenant_id = ?
                """,
                Long.class, documentId, tenantId);

        if (count == null || count != 1L) {
            return false;
        }

        List<String> effects = jdbc.query(
                """
                select r.effect
                  from policy_rule r
                  join policy_head h
                    on h.tenant_id = r.tenant_id
                   and h.active_revision = r.revision
                  join tenant_membership m
                    on m.tenant_id = r.tenant_id
                   and m.role = r.role
                 where r.tenant_id = ?
                   and r.action = ?
                   and m.principal = ?
                   and m.active = true
                """,
                (rs, rowNum) -> rs.getString("effect"),
                tenantId, action, authentication.getName());

        if (effects.contains("DENY")) {
            return false;
        }
        return effects.contains("ALLOW");
    }
}
~~~

**Cách PolicyGate trả lời:**

1. User không xác thực hoặc anonymous → false.
2. Tenant/action/ID không hợp lệ → false.
3. Không tồn tại tài liệu thuộc đúng tenant → false.
4. Truy vấn rule **chỉ của active revision** và **chỉ khớp role đang active** của user trong tenant đích.
5. Nếu có DENY → false, dù cũng có ALLOW.
6. Có ALLOW và không có DENY → true.
7. Không có rule khớp → false.

SQL dùng prepared placeholders, không nối giá trị request trực tiếp. **Không có cache trong ví dụ**, nên quyết định đọc nguồn chuẩn ở mỗi lần gọi. Nếu DB lỗi, exception được propagate; không catch rồi return true.

Hàm không dựa vào authorities do `@WithMockUser` tự cấp trong ví dụ; nó dùng principal name đã được xác thực để tra membership ở DB. Trong production, principal name nên là subject ID bất biến, không phải email có thể tái sử dụng/trùng giữa tenant.

### 5.7. Enforcement: DocumentService

**`src/main/java/demo/policy/DocumentService.java`**

~~~java
package demo.policy;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final JdbcTemplate jdbc;
    private final PolicyGate gate;

    public DocumentService(JdbcTemplate jdbc, PolicyGate gate) {
        this.jdbc = jdbc;
        this.gate = gate;
    }

    @PreAuthorize(
            "@policyGate.allowed(authentication, #tenantId, #id, 'READ')")
    @Transactional(readOnly = true)
    public String readTitle(
            @P("tenantId") String tenantId,
            @P("id") Long id) {

        return jdbc.query(
                """
                select title from tenant_document
                 where id = ? and tenant_id = ?
                """,
                rs -> {
                    if (!rs.next()) {
                        throw new AccessDeniedException("Not available");
                    }
                    return rs.getString(1);
                },
                id, tenantId);
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional
    public void rename(
            @P("tenantId") String tenantId,
            @P("id") Long id,
            String newTitle) {

        if (newTitle == null || newTitle.isBlank()
                || newTitle.length() > 160) {
            throw new IllegalArgumentException("Invalid title");
        }

        Boolean exists = jdbc.query(
                """
                select id from tenant_document
                 where id = ? and tenant_id = ?
                 for update
                """,
                rs -> rs.next(),
                id, tenantId);

        if (!Boolean.TRUE.equals(exists)) {
            throw new AccessDeniedException("Not available");
        }

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        if (!gate.allowed(auth, tenantId, id, "EDIT")) {
            throw new AccessDeniedException("Not permitted");
        }

        int affected = jdbc.update(
                """
                update tenant_document
                   set title = ?
                 where id = ? and tenant_id = ?
                """,
                newTitle, id, tenantId);

        if (affected != 1) {
            throw new IllegalStateException("Concurrent change");
        }
    }
}
~~~

Tại sao read và write khác nhau?

- `@PreAuthorize("@policyGate...")` kiểm tra READ ngay ở method boundary; body vẫn query theo tenant làm chốt thứ hai.
- Với WRITE, chốt `isAuthenticated()` trước body, còn kiểm tra EDIT đặt **bên trong transaction** sau khi lock document để giảm time-of-check/time-of-use.
- `@P("tenantId")` và `@P("id")` giúp Spring Security tìm đúng biến trong SpEL, kể cả khi không build với `-parameters`.
- `@Transactional` và Method Security hoạt động trên Spring-managed proxy. Không test bằng `new DocumentService(...)` hoặc self-invocation rồi nghĩ annotation chắc chắn được áp dụng.
- `SELECT ... FOR UPDATE` chỉ khóa document row; nó không tự khóa membership hoặc policy_head. Đường ghi có yêu cầu thu hồi tức thì phải bổ sung đồng bộ/revision guard trên toàn bộ nguồn policy liên quan.

### 5.8. Publish snapshot: PolicyPublisher

**`src/main/java/demo/policy/PolicyPublisher.java`**

~~~java
package demo.policy;

import java.util.List;
import java.util.Set;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PolicyPublisher {

    public record RuleSpec(String role, String action, String effect) {
    }

    private static final Set<String> ACTIONS =
            Set.of("READ", "EDIT");
    private static final Set<String> EFFECTS =
            Set.of("ALLOW", "DENY");

    private final JdbcTemplate jdbc;

    public PolicyPublisher(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @PreAuthorize("hasAuthority('POLICY_PUBLISH')")
    @Transactional
    public long publish(String tenantId, List<RuleSpec> snapshot) {

        if (tenantId == null
                || !tenantId.matches("[a-z][a-z0-9-]{1,39}")
                || snapshot == null || snapshot.isEmpty()) {
            throw new IllegalArgumentException("Invalid snapshot");
        }

        // Khóa con trỏ ACTIVE để serialize publishers cùng tenant.
        Long active = jdbc.query(
                """
                select active_revision from policy_head
                 where tenant_id = ?
                 for update
                """,
                rs -> rs.next() ? rs.getLong(1) : null,
                tenantId);

        if (active == null) {
            throw new IllegalArgumentException("Unknown tenant");
        }

        long nextRevision = active + 1;

        for (RuleSpec rule : snapshot) {
            if (rule == null
                    || rule.role() == null
                    || !rule.role().matches("ROLE_[A-Z0-9_]+")
                    || rule.action() == null
                    || !ACTIONS.contains(rule.action())
                    || rule.effect() == null
                    || !EFFECTS.contains(rule.effect())) {
                throw new IllegalArgumentException("Invalid policy rule");
            }

            jdbc.update(
                    """
                    insert into policy_rule
                        (tenant_id, revision, role, action, effect)
                    values (?, ?, ?, ?, ?)
                    """,
                    tenantId, nextRevision,
                    rule.role(), rule.action(), rule.effect());
        }

        int updated = jdbc.update(
                """
                update policy_head
                   set active_revision = ?
                 where tenant_id = ? and active_revision = ?
                """,
                nextRevision, tenantId, active);

        if (updated != 1) {
            throw new IllegalStateException("Revision conflict");
        }

        return nextRevision;
    }
}
~~~

**Ý nghĩa:**

- `POLICY_PUBLISH` là authority control-plane **dành riêng** cho ví dụ; user bình thường không được gọi publish. Production cần thêm giới hạn tenant, approvals, step-up MFA và audit.
- `@Transactional` bao cả INSERT rules và cập nhật active pointer trong **một database transaction**.
- Khóa row `policy_head ... FOR UPDATE` giúp serialize hai publisher cùng tenant ở database có hỗ trợ. Cần test isolation/locking trên DB thật.
- `snapshot` là **full policy** cho tenant tại revision mới; quy tắc không được mang qua sẽ không còn hiệu lực.
- Một rule invalid sau khi đã insert rule trước đó gây runtime exception → transaction rollback mọi INSERT và giữ nguyên active revision.
- Unique PK bảo vệ duplicate key; effect có CHECK constraint.
- Bài mẫu không có policy audit/outbox, không mặc nhiên đáp ứng mọi yêu cầu production governance.

Nếu muốn giảm nguy cơ làm thiếu quyền do admin publish dựa trên bản cũ, có thể bổ sung `expectedActiveRevision` từ UI và reject khi không khớp, thay vì luôn lấy `active+1`.

## 6. Kiểm thử thay policy và membership ngay lúc chạy

Các integration tests dưới đây khởi động H2, Spring JDBC, Spring Method Security proxy. `@WithMockUser` tạo Authentication thử nghiệm chứ không chứng minh một luồng đăng nhập JWT thật.

**`src/test/java/demo/policy/DynamicPolicyIntegrationTest.java`**

~~~java
package demo.policy;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = DynamicPolicyApplication.class)
class DynamicPolicyIntegrationTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired PolicyGate gate;
    @Autowired DocumentService documents;
    @Autowired PolicyPublisher publisher;

    @BeforeEach
    void reset() {
        // Không @Transactional trên tests; các services phải commit/rollback thật.
        jdbc.update("update policy_head set active_revision = 1");
        jdbc.update("delete from policy_rule where revision > 1");
        jdbc.update("update tenant_membership set active = true");
        jdbc.update(
                "update tenant_document set title = 'ACME-original' where id = 101");
        jdbc.update(
                "update tenant_document set title = 'BETA-original' where id = 202");
    }

    private Authentication alice() {
        return new UsernamePasswordAuthenticationToken(
                "alice", "demo-only",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    @WithMockUser(username = "alice")
    void aliceCanReadAndEditAcme() {
        assertEquals("ACME-original",
                documents.readTitle("acme", 101L));

        documents.rename("acme", 101L, "Reviewed");

        assertEquals("Reviewed",
                documents.readTitle("acme", 101L));
    }

    @Test
    @WithMockUser(username = "bob")
    void betaReaderCannotEditOrReadAcme() {
        assertEquals("BETA-original",
                documents.readTitle("beta", 202L));

        assertThrows(AccessDeniedException.class,
                () -> documents.rename("beta", 202L, "Changed"));

        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void foreignTenantAndIdAreDenied() {
        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("beta", 202L));

        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 202L));

        assertThrows(AccessDeniedException.class,
                () -> documents.rename("acme", 202L, "Hacked"));
    }

    @Test
    @WithMockUser(username = "carol")
    void blockedRoleOverridesReaderGrant() {
        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 101L));
    }

    @Test
    @WithMockUser(username = "alice")
    void revokingMembershipChangesDecisionWithoutDeployment() {
        assertEquals("ACME-original",
                documents.readTitle("acme", 101L));

        jdbc.update(
                """
                update tenant_membership set active = false
                 where principal = ? and tenant_id = ? and role = ?
                """,
                "alice", "acme", "ROLE_READER");

        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 101L));

        // Alice vẫn còn ROLE_EDITOR.
        documents.rename("acme", 101L, "Edited");
        assertEquals("Edited", jdbc.queryForObject(
                "select title from tenant_document where id = 101",
                String.class));
    }

    @Test
    @WithMockUser(username = "operator", authorities = "POLICY_PUBLISH")
    void newRevisionIsUsedImmediately() {
        long revision = publisher.publish("acme", List.of(
                new PolicyPublisher.RuleSpec(
                        "ROLE_READER", "READ", "DENY"),
                new PolicyPublisher.RuleSpec(
                        "ROLE_EDITOR", "EDIT", "ALLOW")));

        assertEquals(2L, revision);
        assertEquals(2L, jdbc.queryForObject(
                "select active_revision from policy_head where tenant_id = 'acme'",
                Long.class));

        assertFalse(gate.allowed(alice(), "acme", 101L, "READ"));
        assertTrue(gate.allowed(alice(), "acme", 101L, "EDIT"));

        // Test đổi Authentication sang Alice cho Spring Method Security.
        SecurityContextHolder.getContext().setAuthentication(alice());

        assertThrows(AccessDeniedException.class,
                () -> documents.readTitle("acme", 101L));

        documents.rename("acme", 101L, "Policy updated");
        assertEquals("Policy updated", jdbc.queryForObject(
                "select title from tenant_document where id = 101",
                String.class));
    }

    @Test
    @WithMockUser(username = "operator", authorities = "POLICY_PUBLISH")
    void invalidSecondRuleRollsBackTheFirstInsert() {
        assertThrows(IllegalArgumentException.class,
                () -> publisher.publish("acme", List.of(
                        new PolicyPublisher.RuleSpec(
                                "ROLE_READER", "READ", "ALLOW"),
                        new PolicyPublisher.RuleSpec(
                                "ROLE_EDITOR", "EDIT", "INVALID"))));

        assertEquals(1L, jdbc.queryForObject(
                "select active_revision from policy_head where tenant_id = 'acme'",
                Long.class));
        assertEquals(0L, jdbc.queryForObject(
                """
                select count(*) from policy_rule
                 where tenant_id = 'acme' and revision = 2
                """,
                Long.class));

        assertTrue(gate.allowed(alice(), "acme", 101L, "READ"));
    }

    @Test
    @WithMockUser(username = "alice")
    void ordinaryUserCannotPublishPolicy() {
        assertThrows(AccessDeniedException.class,
                () -> publisher.publish("acme", List.of(
                        new PolicyPublisher.RuleSpec(
                                "ROLE_READER", "READ", "DENY"))));

        assertEquals(1L, jdbc.queryForObject(
                "select active_revision from policy_head where tenant_id = 'acme'",
                Long.class));
    }

    @Test
    @WithMockUser(username = "alice")
    void missingPolicyOrResourceDefaultsToDeny() {
        assertFalse(gate.allowed(alice(), "acme", 101L, "DELETE"));
        assertFalse(gate.allowed(alice(), "acme", 999L, "READ"));
        assertFalse(gate.allowed(alice(), "beta", 202L, "EDIT"));
    }
}
~~~

### Kết quả cần đạt

| Test | Hành vi |
| --- | --- |
| Alice READ + EDIT acme | Được phép |
| Bob READ beta nhưng không EDIT | READ allow, EDIT deny |
| Alice dùng resource ID của beta | Deny |
| Carol vừa READER vừa BLOCKED | DENY overrides |
| Revoke membership READER của Alice | READ deny ngay lần kiểm tra sau; EDIT không tự mất |
| Publish revision 2 đổi READ thành DENY | PDP dùng revision 2, không đổi Java code |
| Rule thứ hai invalid trong transaction | Rollback rule thứ nhất; revision 1 vẫn active |
| User thường gọi publish | Method Security deny |
| Action lạ, resource thiếu, tenant không có membership | Deny by default |

Chạy trên macOS/Linux:

~~~text
./gradlew test --tests demo.policy.DynamicPolicyIntegrationTest
~~~

Windows:

~~~text
gradlew.bat test --tests demo.policy.DynamicPolicyIntegrationTest
~~~

Không có `System.out.println` nên không có stdout nghiệp vụ cố định. Cần kiểm tra toàn bộ assertions pass và Gradle hoàn thành task `test`. Mã trên đã được xem xét tĩnh; trước khi dùng thật phải chạy trên phiên bản Spring Boot/Security và database cụ thể.

## 7. Vì sao chỉ “đọc lại DB mỗi request” chưa giải quyết hết vấn đề?

Trong demo, PolicyGate đọc source-of-truth SQL mỗi lần. Nhưng một request thực tế có nhiều bước:

~~~text
T1: PDP đọc membership Alice=EDITOR, policy revision 7 -> ALLOW.
T2: Admin revoke membership hoặc publish revision 8.
T3: Application service đang xử lý UPDATE.
~~~

Đây là **time-of-check/time-of-use (TOCTOU)**. Transaction khi sửa resource và khóa row document làm giảm một nhóm race nhưng không tự khóa membership/policy_head. Với thao tác ghi cực kỳ nhạy cảm cần policy revision guard, isolation/locking trên các dữ liệu liên quan, hoặc PDP/service thống nhất một decision snapshot có thời hạn/điều kiện.

Cũng không nhầm commit policy với commit dữ liệu nghiệp vụ trên service khác. `@Transactional` chỉ bảo vệ các thao tác tham gia **cùng transaction manager**, không tự tạo atomicity giữa database khác và broker/network.

## 8. Cache policy, nhiều instance và độ trễ thu hồi

Production có thể thêm cache để giảm SQL:

~~~text
DB active policy acme = revision 18
        |
        +--- Node A cache revision 18
        +--- Node B cache revision 17 (STALE)
        +--- Node C cache revision 18
~~~

Nếu revision 18 thu hồi EDIT, Node B vẫn có thể allow sai. **Cache không phải source of truth**.

| Cách dùng cache | Điểm mạnh | Hạn chế |
| --- | --- | --- |
| Không cache | Đọc DB hiện hành nhiều hơn | Tăng tải/latency |
| TTL local | Đơn giản, nhanh | Revoke có thể trễ đến hết TTL |
| Local + pub/sub invalidation | Truyền thông báo khi policy đổi | Event mất/trễ, reorder, network partition |
| Shared backend | Có khả năng dùng chung policy snapshot | Alias keys, serializer, refill race |
| Cache theo revision bất biến | Snapshot có ID rõ, không lẫn rule | Vẫn cần xác định active revision |
| Revision check tại decision | Phát hiện cache cũ | Tăng số lần truy vấn version service |
| DB direct ở đường nhạy cảm | Tránh quyền stale từ cache | Tăng SQL; vẫn có race concurrent commit |

**Policy publish phải được truyền sau commit**, tránh node nhận invalidation trước commit rồi đọc lại policy cũ và cache sai.

~~~text
Transaction:
  insert revision 18 rules
  update policy_head.active_revision=18
  insert outbox PolicyActivated(acme,18)
COMMIT
  publisher gửi event
  mọi node evict/reload policy scope acme
~~~

`@TransactionalEventListener(phase = AFTER_COMMIT)` chỉ đảm bảo callback trong JVM đó sau commit, không đảm bảo delivery sang các node khác. Nếu node chết ngay sau commit nhưng trước publish, event có thể mất. **Transactional outbox** kết hợp durable event bus, retries/ack và consumer idempotent giải quyết một phần khoảng trống ấy.

### 8.1. Revision là khóa an toàn khi nhận event

Một sự kiện:

~~~json
{
  "type": "POLICY_ACTIVATED",
  "tenantId": "acme",
  "revision": 18,
  "changeId": "change-982"
}
~~~

Consumer cần:
1. Validate tenant và event origin.
2. Không hạ cache từ revision 19 về 18 do event đến muộn.
3. Xử lý trùng event idempotent.
4. Nếu phát hiện thiếu revision, hỏi lại active pointer.
5. Evict mọi key/alias thuộc tenant/scope.
6. Đo thời gian từ commit đến enforcement ở từng node.

### 8.2. Race “refill sau invalidate”

~~~text
T1 Node B cache miss, đang SELECT revision 17.
T2 Node A commit revision 18 và gửi invalidate.
T3 Node B evict cache.
T4 Query cũ của B hoàn tất, put revision 17 vào cache.
T5 Request mới đọc cached revision 17 -> ALLOW sai.
~~~

Cần version-aware conditional put hoặc check active revision ở decision, không chỉ gửi event và tin đã xong. TTL có thể giới hạn cửa sổ stale, **không tự loại bỏ** race. Với thao tác đòi hỏi thu hồi ngay, cần cơ chế mạnh hơn invalidation bất đồng bộ.

## 9. Quản trị policy là một thay đổi bảo mật

Quy trình đầy đủ:

1. **Draft:** user có quyền tạo một phiên bản chưa có hiệu lực.
2. **Validate:** schema, role/action whitelist, target tenant, DENY precedence, resource scope, duplicate rules, điều kiện.
3. **Review:** hiển thị diff so với active, tính blast radius, phát hiện grant lan đến nhóm quá lớn.
4. **Test:** chạy positive/negative tests, cross-tenant, deny-overrides, missing rules.
5. **Approve:** 2-person rule/step-up MFA cho thay đổi mở rộng quyền nhạy cảm.
6. **Publish:** transaction ghi full snapshot + active pointer + outbox; lưu author/reason/ticket.
7. **Observe:** xem distribution revision, decision anomalies, cache invalidation lag.
8. **Rollback:** publish một revision mới chứa snapshot đã biết an toàn, không sửa history in-place.
9. **Reconcile:** so sánh active revision với cache/agents ở mọi node.

### 9.1. Tenant admin không được tự nâng thành system policy admin

Ví dụ policy cần:

~~~text
canPublish(actor, tenant, proposedRules):
  actor authenticated
  AND actor có quyền quản trị policy trong tenant mục tiêu
  AND mọi role/action trong allowlist tenant-grantable
  AND không cấp ROLE_SYSTEM_ADMIN/POLICY_PUBLISH_GLOBAL
  AND không sửa policy tenant khác
  AND đủ approval với các thay đổi nhạy cảm
~~~

`POLICY_PUBLISH` của demo là **quyền toàn cục được cấp riêng cho test**, không phải mặc định người có `ROLE_TENANT_ADMIN` sở hữu. Production phải tách `POLICY_DRAFT`, `POLICY_REVIEW`, `POLICY_PUBLISH` và có tenant scope. Không đưa quyền sửa policy đến public API thiếu chốt actor và audit.

### 9.2. Rollback policy không undo các hành động đã xảy ra

Nếu revision 18 cho phép một update, user đã ghi dữ liệu, sau đó revision 19 revoke quyền, việc quay về policy cũ **không khôi phục dữ liệu**. Tách:
- Policy rollback: thay rule cho request tương lai.
- Business compensation: hoàn nguyên side effect theo quy trình riêng.
- Audit: giữ record actor, action, resource, policy revision, decision.

## 10. Audit đúng nguồn và đúng revision

Một decision log có thể gồm:

~~~text
decisionId=authz-874
subject=user-17
tenant=acme
resourceType=DOCUMENT
resourceId=101
action=EDIT
policyRevision=18
decision=DENY
reason=EXPLICIT_DENY
~~~

Ghi metadata tối thiểu, không đưa token, mật khẩu hoặc nội dung tài liệu nhạy cảm vào log. Khi policy nằm ở nhiều nodes, revision là dữ kiện thiết yếu để trả lời “Vì sao request này được phép trong khi request kia bị chặn?”.

Audit policy change cần ghi user yêu cầu, người duyệt, diff/checksum, thời điểm publish, revision cũ/mới, tenant, reason/ticket, kết quả commit. Nếu audit nằm trong transaction rollback, log có thể biến mất; với yêu cầu forensic quan trọng nên thiết kế audit store/outbox riêng.

## 11. Lỗi phổ biến và xử lý an toàn

| Triệu chứng | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| Chỉnh policy nhưng quyền không đổi | App chỉ `hasRole` với JWT cũ | Kết nối PDP đọc active policy + membership |
| Node A deny, Node B allow | Cache policy stale | Version/invalidation sau commit, monitoring |
| Publish lỗi sau 3 rule nhưng policy mới active | Publish nhiều transaction hoặc update pointer sớm | Full snapshot + single transaction |
| User có READER và BLOCKED vẫn được READ | Chỉ kiểm tra có ALLOW | Định nghĩa/test DENY overrides |
| Không có rule mà user được phép | Default allow hoặc exception fallback permissive | Default DENY, fail closed |
| Tenant acme đọc được document beta | Tin tenant selector hoặc thiếu resource check | Query theo id + tenant + membership |
| Tenant admin publish policy system | Control-plane thiếu scope/allowlist | Tenant-scoped PAP, 2-person approval |
| Role bị thu hồi vẫn có quyền | JWT/session/cache membership stale | Revocation/version/TTL/source-of-truth |
| Policy bị thay nhưng code chỉ đọc draft | Query không join active_revision | Chỉ đánh giá ACTIVE revision |
| Quyền bị đổi nửa chừng request | TOCTOU, khác nguồn/transaction | Revision guard/isolation/locking phù hợp |
| Policy DB lỗi thì user vẫn được phép | Catch exception → true | DENY/503, không fail open |
| Cache refill policy cũ sau invalidation | SELECT lâu hơn event | Version-aware cache conditional put |
| Rollback policy mất lịch sử | Sửa/xóa revision cũ | Immutable revisions, publish rollback revision mới |
| Đổi effect sang typo gây allow bất ngờ | Không validate catalog/schema | CHECK constraint, whitelist, tests |
| `@PreAuthorize` không chạy | Chưa bật `@EnableMethodSecurity` hoặc self-invocation | Bật proxy, test Spring-managed bean |
| Rule có role “EDITOR” nhưng membership “ROLE_EDITOR” | Không thống nhất tên authority | Canonical role ID và migration |
| Data store update thành công nhưng event mất | Crash sau commit trước publish | Transactional outbox, idempotent consumer |
| Service dùng grant SQL nhưng quên domain state | PDP không kiểm owner/lock/tenant | PIP domain + policy combining rõ |

## 12. Bộ test an toàn trước triển khai

| Tình huống | Kết quả |
| --- | --- |
| User có membership role và rule ALLOW | ALLOW đúng object/action/tenant |
| User mang role deny và allow cùng lúc | DENY |
| User thuộc tenant khác | DENY |
| ID resource khác tenant | DENY |
| Role bị revoke trong DB | DENY ở thời điểm policy contract quy định |
| Không có rule/action lạ | DENY |
| Policy store không truy cập được | Không trả ALLOW |
| Publish full snapshot thành công | Active revision chuyển atomically |
| Publish lỗi giữa transaction | Active pointer không đổi, không có half snapshot |
| Hai publishers đồng thời | Không lost update, revisions có thứ tự |
| Event đến muộn hoặc trùng | Không hạ cache về revision cũ |
| Node bị ngắt kết nối broker | Reconciliation hoặc fail closed phù hợp |
| Policy quyền admin sai tenant | DENY |
| Cache hit cũ sau revoke | Phát hiện bằng revision/lag test |
| HTTP/method/job dùng đường PDP khác nhau | Quyết định nhất quán theo cùng rule |

Chỉ assert HTTP 403 không đủ: test còn cần kiểm tra **không có data mutation**, active revision, SQL rows, cache version và audit khi publisher lỗi.

## 13. Bài tập thực hành

**Bài 1 — Policy mới không deploy.** Publish acme revision 2 mà READ của READER chuyển từ ALLOW sang DENY, giữ EDIT của EDITOR. Kiểm tra Alice bị từ chối READ nhưng vẫn EDIT. Giải thích tại sao không cần đổi `@PreAuthorize`.

**Bài 2 — Thu hồi membership.** Đổi `tenant_membership.active` của Alice trong acme. Giữ Authentication cũ; chứng minh policy DB mới quyết định READ thay vì tin role snapshot.

**Bài 3 — DENY overrides.** Cho Carol vừa READER vừa BLOCKED. Thêm một role cũng có READ ALLOW; kiểm tra vẫn DENY. Tạo test không có rule nào khớp → DENY.

**Bài 4 — Atomic publish.** Insert một rule hợp lệ rồi một rule invalid trong transaction publish. Test cả INSERT trước bị rollback và `active_revision` giữ nguyên.

**Bài 5 — Concurrent publishers.** Cho hai transaction publish cùng tenant. Dùng `FOR UPDATE`, expected revision hoặc optimistic version, kiểm tra không có hai snapshot cùng active và không bỏ mất thay đổi của một publisher.

**Bài 6 — ABAC.** Thêm `owner_id` và trạng thái LOCKED vào resource. Chỉ cho EDIT khi đúng tenant, đúng role, owner phù hợp, tài liệu chưa khóa. Test trạng thái thay đổi trong transaction.

**Bài 7 — Multi-instance policy cache.** Warm revision 1 tại hai node. Publish revision 2, cố tình làm mất event đến node B. Chứng minh stale ALLOW; thêm revision gate/TTL hoặc fallback DB.

**Bài 8 — PAP workflow.** Thêm DRAFT/APPROVED/ACTIVE; yêu cầu người duyệt khác tác giả cho một rule ALLOW nhạy cảm, và kiểm tra user tenant không thể publish system policy.

**Bài 9 — Audit/replay.** Ghi policy revision và decision ID khi xét quyền, cho phép diễn giải tại sao request cũ được allow. Rollback bằng revision mới thay vì sửa lịch sử.

**Bài 10 — External PDP.** Dùng một custom `AuthorizationManager` hoặc policy agent bên ngoài. Test timeout, 5xx, null decision và unknown revision đều không bị biến thành ALLOW.

**Tiêu chí hoàn thành:** xác định đúng nguồn chuẩn của identity/membership/policy/resource; tách PAP/PDP/PEP/PIP; thiết kế active revision + immutable snapshot; default DENY và combining rule; publish atomic có rollback; nối Spring Security với policy DB động; kiểm thử revoke/cross-tenant/cache/version/fail closed.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 – **Method Security** (custom bean với `@PreAuthorize`): https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 – **Authorize HTTP Requests** và external `AuthorizationManager`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security – **Authorization Architecture**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Framework – **Using @Transactional**, proxy và transaction semantics: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework – **Rolling Back a Declarative Transaction**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework – **Transaction-bound Events**: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework – **Spring JDBC JdbcTemplate**: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
