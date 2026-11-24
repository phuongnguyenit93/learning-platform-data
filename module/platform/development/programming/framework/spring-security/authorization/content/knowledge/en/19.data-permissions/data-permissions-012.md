# Combining Application Checks with Database Row-Level Security

## 1. Objectives

In Spring Security, `@PreAuthorize` can protect calls to a service, yet the database can still be queried through other paths: a repository missing `WHERE tenant_id = ...`, a background job, a new endpoint, or a direct JDBC query. Conversely, **Row-Level Security (RLS)** in the database can filter rows via SQL policies, yet cannot natively understand full business permissions such as `DOC_READ`, `DOC_APPROVE`, DRAFT state, or sensitive fields.

Defense-in-depth solution:

- **Application authorization:** Spring Security authenticates the principal and checks **action** authorities; the service checks owner, state, tenant membership, and field-level policies.
- **Database RLS:** PostgreSQL automatically enforces conditions on **the rows** the DB role is allowed to read/write.
- **Trusted tenant scope:** the application resolves the tenant from verified identity/directory data and sets the context inside the **current transaction** on the exact JDBC connection.
- **Least-privilege DB role:** the runtime account does not own tables and has neither SUPERUSER nor `BYPASSRLS`.
- **Independent tests:** prove both blocking before the method body **and** blocking directly at SQL, even when SQL queries omit tenant conditions.

After this lesson in the **Data Permissions** group of Spring Security Authorization, you will be able to explain `USING` and `WITH CHECK`, write `CREATE POLICY`, prevent tenant context leaks across connection pools, design clear app + DB checks with distinct responsibilities, and run Java 17+ integration tests on **real PostgreSQL via Testcontainers**.

**Illustrative environment:** Spring Boot 3.5.x, Spring Security 6.5.x, PostgreSQL 17, Java 17+, JUnit 5, JDBC, Gradle, and Docker for Testcontainers. This SQL targets PostgreSQL; RLS in other databases differs in syntax and semantics.

## 2. Two Security Layers Answer Two Different Questions

Suppose a documents table:

| ID | Tenant | Owner | Status | Body |
| --- | --- | --- | --- | --- |
| 1 | TENANT_A | alice | PUBLISHED | Public A |
| 2 | TENANT_A | bob | DRAFT | Bob draft |
| 3 | TENANT_B | carol | PUBLISHED | Public B |
| 4 | TENANT_A | alice | DRAFT | Alice draft |

Example business policy:

1. `DOC_READ` is the **functional authority** for reading. Within a verified tenant, anyone may read PUBLISHED documents; DRAFT is readable only by the owner.
2. `DOC_UPDATE` is the functional authority for editing. Only the owner may edit their own **DRAFT**; self-transferring tenant is forbidden.
3. `DOC_CREATE` allows creating DRAFTs. `tenant_id`, `owner_name`, and `status` are set server-side; clients cannot arbitrarily claim owner or tenant.
4. Missing required authority, unverified tenant membership, invisible object, or failed business condition results in **deny**.
5. PostgreSQL RLS enforces the **right tenant** on every SELECT/INSERT/UPDATE/DELETE executed by the application role. Tenant B must never appear in tenant A's queries, even if the SQL statement lacks `WHERE tenant_id`.

```text
Client -> Spring-managed service proxy
                  |
                  v
     @PreAuthorize("hasAuthority('DOC_READ')")
                  |
         +--------+--------+
         | deny            | allow
         v                 v
   AccessDeniedException   Method body
                           |
                           v
               Trusted tenant lookup
                           |
                           v
               TransactionTemplate
                 set_config(..., true)
                           |
                           v
                       JDBC SQL
                           |
                           v
              PostgreSQL RLS (USING/WITH CHECK)
                           |
                  +--------+--------+
                  |                 |
              right tenant      wrong tenant
              rows visible     rows hidden/write rejected
                           |
                           v
              App checks DRAFT owner/status
                           |
                           v
                 Allowed result or deny
```

In the example, the Java policy blocks Alice from reading Bob's DRAFT **even though** RLS shows both belong to TENANT_A. RLS blocks Alice from reading Carol's PUBLISHED document in TENANT_B **even though** she holds `DOC_READ`. The two decisions complement, rather than replace, each other.

## 3. PostgreSQL Row-Level Security: Core Mechanism

### 3.1. Enabling RLS and Creating Policies

```sql
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation
ON public.documents
FOR ALL
TO rls_app
USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
)
WITH CHECK (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
);
```

Explanation:

- `ENABLE ROW LEVEL SECURITY` enables row policy checks for RLS-subject roles on this table.
- `CREATE POLICY` defines the rule; `FOR ALL` covers all SQL commands, and `TO rls_app` targets the database role subject to it.
- `USING` determines which **existing** rows are visible or selectable for update/delete.
- `WITH CHECK` determines whether a row **after INSERT/UPDATE** is valid.
- `current_setting('app.tenant_id', true)` reads the tenant context from the PostgreSQL session. Passing `true` returns `NULL` when unset instead of throwing an error.
- `NULLIF(..., '')` ensures empty strings are also never treated as a valid tenant. Comparing `tenant_id = NULL` never evaluates to `TRUE`, so the policy fails closed.
- When RLS is enabled and **no policy applies** to a role/command, PostgreSQL denies all rows by default (default-deny), except for roles with bypass privileges.

**RLS does not grant SQL privileges.** Alongside policies, the runtime DB role still needs appropriate `GRANT SELECT, INSERT, UPDATE, DELETE`; table-level privileges and row-level policies are **two separate layers**.

### 3.2. `USING` and `WITH CHECK` Are Not the Same

| Operation | `USING` | `WITH CHECK` |
| --- | --- | --- |
| SELECT | Filters readable rows | Not applied to new rows |
| INSERT | No existing row | Validates the new row |
| UPDATE | Old row must be selectable for edit | Post-edit row must be valid |
| DELETE | Old row must be selectable for delete | No new row |
| MERGE | Relevant branches must obey matching policies | Validates resulting rows per relevant rules |

Example while in TENANT_A context:

```sql
-- RLS allows viewing Document #1.
SELECT * FROM public.documents WHERE id = 1;

-- RLS hides Document #3 (TENANT_B); typically returns 0 rows.
SELECT * FROM public.documents WHERE id = 3;

-- Old row belongs to A, yet new row would belong to B:
-- WITH CHECK rejects this statement.
UPDATE public.documents SET tenant_id = 'TENANT_B'
WHERE id = 1;

-- Inserting a new row into B while active tenant is A is also rejected.
INSERT INTO public.documents
    (id, tenant_id, owner_name, status, body)
VALUES (100, 'TENANT_B', 'alice', 'DRAFT', 'Invalid');
```

If `USING` is specified without `WITH CHECK`, PostgreSQL inherits expressions in certain policy types, though you should never rely on guesswork. **Explicitly specify both** whenever policy requires rows before and after to stay in the same tenant.

When a row is hidden by `USING`, SELECT returns empty and UPDATE/DELETE return affected rows = 0. When a new row violates `WITH CHECK`, INSERT/UPDATE throws an SQL error. The application must check affected row counts, handle exceptions, and map to HTTP 403/404/409 per contract without leaking IDs from other tenants.

### 3.3. Table Owner, Superuser, BYPASSRLS

PostgreSQL RLS relies on **database roles**. The following roles can bypass policies:

- **Superuser**: always bypasses RLS.
- Roles with the **`BYPASSRLS`** attribute: bypass RLS.
- **Table owner**: bypasses RLS by default; `ALTER TABLE ... FORCE ROW LEVEL SECURITY` forces the table owner to obey RLS, though it does not stop superusers/BYPASSRLS.

Therefore, integration tests must use a **separate role that does not own the table**. If an application connects as `postgres` and a test "reads all tenants", that proves the wrong role is being used, not that RLS works.

```text
postgres / migration_owner
    -> creates tables, creates policies, runs GRANT; never used in app runtime

rls_app
    -> does not own tables, not SUPERUSER, no BYPASSRLS
    -> minimal SQL privileges
    -> Spring JDBC DataSource connects as this role
```

`TRUNCATE`, `REFERENCES`, and certain administrative commands are not governed by row policies like SELECT/UPDATE. Never grant them, DDL rights, or unnecessary `SET ROLE` privileges to the application account. Views, `SECURITY DEFINER` functions, owner privileges, and export/report paths must be reviewed separately.

## 4. Tenant Context in Transactions and Connection Pools

### 4.1. Setting Tenant Per Transaction

PostgreSQL supports:

```sql
SELECT set_config('app.tenant_id', 'TENANT_A', true);
```

The trailing `true` makes the setting valid **only for the current transaction**, equivalent to `SET LOCAL`. After commit or rollback, the local setting clears. Passing `false` sets it at the session level, which can persist across multiple requests when the JDBC connection returns to the pool.

**Wrong way:**

```java
// Anti-pattern: taking tenant directly from client,
// storing on DB session; connection pool may reuse it.
jdbcTemplate.queryForObject(
    "SELECT set_config('app.tenant_id', ?, false)",
    String.class,
    requestTenant
);
```

Here `requestTenant` is untrusted and `false` can cause **tenant context leakage** between request A and request B.

**Better way:**

```java
return transactionTemplate.execute(status -> {
    String tenant = trustedTenantDirectory.resolve(authentication);
    jdbcTemplate.queryForObject(
        "SELECT set_config('app.tenant_id', ?, true)",
        String.class,
        tenant
    );
    return jdbcTemplate.query(/* business query in the same transaction */);
});
```

This is a conceptual snippet: it requires `TransactionTemplate`, `JdbcTemplate`, trusted identity, and real SQL. The core point is that **setting context and running queries must happen in the same transaction on the same Spring-bound JDBC connection**. Never execute `set_config(..., true)` in an autocommit statement and then run the business query later on another connection.

**When using PgBouncer transaction pooling**, you especially cannot rely on session settings across transactions. With multiple DataSources, tenant context must be set on every connection being queried. For `REQUIRES_NEW`, background jobs, async tasks, or R2DBC, context/transaction propagation must be designed per execution flow.

### 4.2. Where Does the Tenant Come From?

Authorized tenant access must come from **verified identity + server-side membership data**, never directly from `X-Tenant-Id` headers, URL paths, or request bodies. A user may have access to multiple tenants; the server must verify membership and tenant-switch permissions before setting context.

In the tests below, the mapping `alice → TENANT_A`, `carol → TENANT_B` sits in a fixed Java map to make the mechanism clear. Production should use a trusted identity provider or tenant membership service/repository.

### 4.3. Critical Security Limitation of Custom GUCs

**`app.tenant_id` is not a database-authenticated identity.** The runtime role can call `set_config('app.tenant_id', 'TENANT_B', true)` itself if permitted to run arbitrary SQL. Hence custom GUC + RLS is **defense-in-depth against missing tenant predicates in normal queries**, yet **not unforgeable isolation against SQL injection or DB-role compromise**.

Combine with prepared statements, code reviews, SQL allowlists, least-privilege DB rights, blocking arbitrary client SQL, auditing, and threat modeling. If the database must **authenticate the tenant itself even if the app role is compromised**, consider tenant-specific DB identities/roles/connections, controlled database/schema isolation, or DB-verified claim mechanisms using carefully audited privileged functions. Merely renaming the setting to `app.secure_tenant_id` does not solve the trust boundary.

## 5. Application Checks Before and Inside the Transaction

A clean design separates:

- **Function-level:** `@PreAuthorize("hasAuthority('DOC_READ')")` protects calls to the service before the method body runs.
- **Object/workflow-level:** when reading **RLS-filtered** results, Java still checks DRAFT ownership; when updating, SQL requires `owner_name = authentication.name` and `status='DRAFT'`.
- **Tenant-level:** RLS filters by tenant context; even an SQL query using only `WHERE id = ?` cannot read another tenant's row.
- **Concurrency-level:** transactional conditional updates/optimistic locking prevent editing a document whose state just changed. A pre-body check alone does not prevent every race condition.

Layered illustrative example:

```java
@PreAuthorize("hasAuthority('DOC_UPDATE')")
public void updateDraft(long id, String body) {
    Authentication auth = SecurityContextHolder
        .getContext().getAuthentication();

    tx.executeWithoutResult(status -> {
        String tenant = tenantDirectory.resolve(auth);
        jdbc.queryForObject(
            "SELECT set_config('app.tenant_id', ?, true)",
            String.class, tenant
        );
        int rows = jdbc.update(
            "UPDATE documents SET body = ? " +
            "WHERE id = ? AND owner_name = ? AND status = 'DRAFT'",
            body, id, auth.getName()
        );
        if (rows != 1) {
            throw new AccessDeniedException(
                "Not allowed, not found or stale");
        }
    });
}
```

This is a **fragment** needing beans/imports and a Spring context, not a standalone class. It combines proxy authority checks, owner/status in SQL, and tenant RLS. `@PreAuthorize` can be bypassed by **self-invocation** in Spring proxy mode; always call through the Spring bean, never `this.updateDraft(...)` within the same target.

### 5.1. RLS Does Not Replace Field-Level Security

RLS restricts **rows**. If a document holds `salary`, `personalId`, or `secretNote`, being allowed to see the row does not mean seeing every column. Use DTO allowlists/redaction, column privileges, appropriately scoped views, and application policies. For EXPORT, never run `SELECT *` hoping RLS hides all PII: RLS alone does not govern sensitive columns or export volume.

## 6. Hands-On Practice with Java 17+ and PostgreSQL Testcontainers

Tests require **real PostgreSQL**, because H2 does not accurately emulate `CREATE POLICY`, RLS roles, and `set_config`. The project runs PostgreSQL 17 in Docker, with the schema created by `postgres`; Spring's DataSource logs in as **`rls_app`**, a role that does not own tables.

**Prerequisites:** JDK 17+, Gradle, Docker daemon, access to pull the PostgreSQL image from a container registry, and Maven Central dependencies. This is an isolated test project containing no production passwords.

### 6.1. Layout and Gradle

```text
spring-rls-demo/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/SpringRlsIntegrationTest.java
    └── resources/db/rls-schema.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-rls-demo'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Because all Java code resides under `src/test/java`, `testImplementation` suffices. In a real runnable application, place JDBC/Security starters in `implementation`, the driver in `runtimeOnly`, and keep test dependencies in test scope. Spring Boot BOM prevents mixing incompatible library versions.

### 6.2. Schema, Role Privileges, and RLS

`src/test/resources/db/rls-schema.sql`:

```sql
-- Testcontainers runs the init script as database admin postgres.
CREATE ROLE rls_app LOGIN PASSWORD 'rls_test_password';

CREATE TABLE public.documents (
    id BIGINT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    status TEXT NOT NULL,
    body TEXT NOT NULL
);

INSERT INTO public.documents
    (id, tenant_id, owner_name, status, body)
VALUES
    (1, 'TENANT_A', 'alice', 'PUBLISHED', 'Public A'),
    (2, 'TENANT_A', 'bob', 'DRAFT', 'Bob draft'),
    (3, 'TENANT_B', 'carol', 'PUBLISHED', 'Public B'),
    (4, 'TENANT_A', 'alice', 'DRAFT', 'Alice draft');

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents FORCE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant
ON public.documents
FOR ALL TO rls_app
USING (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
)
WITH CHECK (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
);

GRANT CONNECT ON DATABASE securitydb TO rls_app;
GRANT USAGE ON SCHEMA public TO rls_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.documents TO rls_app;
```

`postgres` owns the table and can reset fixtures. `rls_app` holds only DML privileges and **does not bypass RLS**. Even with `GRANT SELECT`, `rls_app` cannot see tenant B rows when the transaction context is tenant A; without any context, it sees zero rows.

### 6.3. Complete Integration Test

`src/test/java/demo/SpringRlsIntegrationTest.java`:

```java
package demo;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Testcontainers
@SpringBootTest(
    classes = SpringRlsIntegrationTest.Config.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "spring.datasource.hikari.maximum-pool-size=1"
)
public class SpringRlsIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> DB =
        new PostgreSQLContainer<>("postgres:17-alpine")
            .withDatabaseName("securitydb")
            .withUsername("postgres")
            .withPassword("admin_test_password")
            .withInitScript("db/rls-schema.sql");

    @DynamicPropertySource
    static void configureDb(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", DB::getJdbcUrl);
        registry.add("spring.datasource.username", () -> "rls_app");
        registry.add("spring.datasource.password",
            () -> "rls_test_password");
        registry.add("spring.datasource.driver-class-name",
            () -> "org.postgresql.Driver");
    }

    @Autowired DataSource dataSource;
    @Autowired JdbcTemplate jdbc;
    @Autowired TransactionTemplate tx;
    @Autowired DocumentService service;
    @Autowired Probe probe;

    public record Doc(
        long id, String tenant, String owner,
        String status, String body
    ) {}

    public static class Probe {
        private final AtomicInteger reads = new AtomicInteger();
        private final AtomicInteger writes = new AtomicInteger();
        private final AtomicInteger creates = new AtomicInteger();

        void read() { reads.incrementAndGet(); }
        void write() { writes.incrementAndGet(); }
        void create() { creates.incrementAndGet(); }

        int reads() { return reads.get(); }
        int writes() { return writes.get(); }
        int creates() { return creates.get(); }

        void reset() {
            reads.set(0);
            writes.set(0);
            creates.set(0);
        }
    }

    public static class TenantDirectory {
        // Server-side simulated membership data for learning.
        private static final Map<String, String> TENANTS = Map.of(
            "alice", "TENANT_A",
            "bob", "TENANT_A",
            "manager", "TENANT_A",
            "carol", "TENANT_B"
        );

        public String tenantOf(Authentication auth) {
            if (auth == null || !auth.isAuthenticated()) {
                throw new AccessDeniedException(
                    "Authentication required");
            }
            String tenant = TENANTS.get(auth.getName());
            if (tenant == null) {
                throw new AccessDeniedException(
                    "Tenant membership unknown");
            }
            return tenant;
        }
    }

    public static class DocumentService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate tx;
        private final TenantDirectory tenants;
        private final Probe probe;
        private final AtomicLong ids = new AtomicLong(1000L);

        DocumentService(
                JdbcTemplate jdbc, TransactionTemplate tx,
                TenantDirectory tenants, Probe probe) {
            this.jdbc = jdbc;
            this.tx = tx;
            this.tenants = tenants;
            this.probe = probe;
        }

        private Authentication currentAuth() {
            return SecurityContextHolder
                .getContext().getAuthentication();
        }

        private void applyTenant(Authentication auth) {
            String tenant = tenants.tenantOf(auth);
            jdbc.queryForObject(
                "SELECT set_config('app.tenant_id', ?, true)",
                String.class, tenant);
        }

        private Doc find(long id) {
            return jdbc.query(
                "SELECT id, tenant_id, owner_name, status, body " +
                "FROM public.documents WHERE id = ?",
                rs -> rs.next()
                    ? new Doc(
                        rs.getLong("id"),
                        rs.getString("tenant_id"),
                        rs.getString("owner_name"),
                        rs.getString("status"),
                        rs.getString("body"))
                    : null,
                id
            );
        }

        @PreAuthorize("hasAuthority('DOC_READ')")
        public Doc read(long id) {
            probe.read();
            Authentication auth = currentAuth();

            return tx.execute(status -> {
                applyTenant(auth);
                Doc doc = find(id); // Already filtered by tenant via RLS.
                if (doc == null ||
                    ("DRAFT".equals(doc.status()) &&
                    !doc.owner().equals(auth.getName()))) {
                    throw new AccessDeniedException(
                        "Not visible or not allowed");
                }
                return doc;
            });
        }

        @PreAuthorize("hasAuthority('DOC_UPDATE')")
        public void updateDraft(long id, String body) {
            probe.write();
            Authentication auth = currentAuth();

            tx.executeWithoutResult(status -> {
                applyTenant(auth);
                int changed = jdbc.update(
                    "UPDATE public.documents SET body = ? " +
                    "WHERE id = ? AND owner_name = ? " +
                    "AND status = 'DRAFT'",
                    body, id, auth.getName());
                if (changed != 1) {
                    throw new AccessDeniedException(
                        "Update not allowed or object changed");
                }
            });
        }

        @PreAuthorize("hasAuthority('DOC_CREATE')")
        public Doc createDraft(String body) {
            probe.create();
            Authentication auth = currentAuth();

            return tx.execute(status -> {
                applyTenant(auth);
                String tenant = tenants.tenantOf(auth);
                long id = ids.incrementAndGet();
                jdbc.update(
                    "INSERT INTO public.documents " +
                    "(id, tenant_id, owner_name, status, body) " +
                    "VALUES (?, ?, ?, 'DRAFT', ?)",
                    id, tenant, auth.getName(), body);
                return find(id);
            });
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    public static class Config {

        @Bean TenantDirectory tenantDirectory() {
            return new TenantDirectory();
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean DocumentService documentService(
                JdbcTemplate jdbc, TransactionTemplate tx,
                TenantDirectory tenants, Probe probe) {
            return new DocumentService(jdbc, tx, tenants, probe);
        }
    }

    @BeforeEach
    void restoreDatabase() throws SQLException {
        // Test fixture admin only; Spring app still connects as rls_app.
        try (Connection c = DriverManager.getConnection(
                DB.getJdbcUrl(), "postgres", "admin_test_password");
             Statement st = c.createStatement()) {
            st.executeUpdate("TRUNCATE public.documents");
            st.executeUpdate(
                "INSERT INTO public.documents " +
                "(id, tenant_id, owner_name, status, body) VALUES " +
                "(1, 'TENANT_A', 'alice', 'PUBLISHED', 'Public A'), " +
                "(2, 'TENANT_A', 'bob', 'DRAFT', 'Bob draft'), " +
                "(3, 'TENANT_B', 'carol', 'PUBLISHED', 'Public B'), " +
                "(4, 'TENANT_A', 'alice', 'DRAFT', 'Alice draft')");
        }
        probe.reset();
    }

    private long visibleCount(String tenant) {
        Long count = tx.execute(status -> {
            jdbc.queryForObject(
                "SELECT set_config('app.tenant_id', ?, true)",
                String.class, tenant);
            return jdbc.queryForObject(
                "SELECT count(*) FROM public.documents", Long.class);
        });
        return count.longValue();
    }

    @Test
    void runtimeRoleIsNotTheTableOwnerOrSuperuser() {
        assertThat(jdbc.queryForObject(
            "SELECT current_user", String.class)).isEqualTo("rls_app");
        assertThat(AopUtils.isAopProxy(service)).isTrue();
    }

    @Test
    void noTenantSettingReturnsZeroRows() {
        Long count = tx.execute(status ->
            jdbc.queryForObject(
                "SELECT count(*) FROM public.documents", Long.class));
        assertThat(count).isZero();
    }

    @Test
    void tenantAContextSeesOnlyThreeRows() {
        assertThat(visibleCount("TENANT_A")).isEqualTo(3L);
    }

    @Test
    void tenantBContextSeesOnlyOneRow() {
        assertThat(visibleCount("TENANT_B")).isEqualTo(1L);
    }

    @Test
    void tenantLocalSettingDoesNotLeakAfterCommit() {
        assertThat(visibleCount("TENANT_A")).isEqualTo(3L);
        Long next = tx.execute(status ->
            jdbc.queryForObject(
                "SELECT count(*) FROM public.documents", Long.class));
        assertThat(next).isZero();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void aliceCanReadPublishedTenantADocument() {
        assertThat(service.read(1L).body()).isEqualTo("Public A");
        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void applicationDeniesBobsDraftWithinSameTenant() {
        assertThatThrownBy(() -> service.read(2L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_READ")
    void bobCanReadHisOwnDraft() {
        assertThat(service.read(2L).body()).isEqualTo("Bob draft");
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void rlsHidesPublishedRowOfTenantB() {
        assertThatThrownBy(() -> service.read(3L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void missingReadAuthorityIsDeniedBeforeMethodBody() {
        assertThatThrownBy(() -> service.read(1L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    @WithMockUser(username = "unknown", authorities = "DOC_READ")
    void unknownTenantMembershipFailsClosed() {
        assertThatThrownBy(() -> service.read(1L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void aliceMayUpdateHerOwnDraft() {
        service.updateDraft(4L, "Changed by Alice");

        String actualBody = tx.execute(status -> {
            jdbc.queryForObject(
                "SELECT set_config('app.tenant_id', ?, true)",
                String.class, "TENANT_A");
            return jdbc.queryForObject(
                "SELECT body FROM public.documents WHERE id = 4",
                String.class);
        });

        assertThat(actualBody).isEqualTo("Changed by Alice");
        assertThat(probe.writes()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void aliceCannotUpdateBobsDraft() {
        assertThatThrownBy(() ->
            service.updateDraft(2L, "Unapproved"))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_UPDATE")
    void aliceCannotUpdateTenantBRow() {
        assertThatThrownBy(() ->
            service.updateDraft(3L, "Cross-tenant"))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_CREATE")
    void createAssignsTenantAndOwnerOnTheServer() {
        Doc created = service.createDraft("New document");
        assertThat(created.tenant()).isEqualTo("TENANT_A");
        assertThat(created.owner()).isEqualTo("alice");
        assertThat(created.status()).isEqualTo("DRAFT");
        assertThat(probe.creates()).isEqualTo(1);
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void missingCreateAuthorityIsDeniedBeforeBody() {
        assertThatThrownBy(() -> service.createDraft("Forbidden"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.creates()).isZero();
    }

    @Test
    void insertIntoWrongTenantFailsRlsWithCheck() {
        assertThatThrownBy(() ->
            tx.executeWithoutResult(status -> {
                jdbc.queryForObject(
                    "SELECT set_config('app.tenant_id', ?, true)",
                    String.class, "TENANT_A");
                jdbc.update(
                    "INSERT INTO public.documents " +
                    "(id, tenant_id, owner_name, status, body) " +
                    "VALUES (?, ?, 'alice', 'DRAFT', 'Invalid')",
                    9000L, "TENANT_B");
            })
        ).isInstanceOf(DataAccessException.class);
    }

    @Test
    void movingAnExistingRowToAnotherTenantFailsRlsWithCheck() {
        assertThatThrownBy(() ->
            tx.executeWithoutResult(status -> {
                jdbc.queryForObject(
                    "SELECT set_config('app.tenant_id', ?, true)",
                    String.class, "TENANT_A");
                jdbc.update(
                    "UPDATE public.documents SET tenant_id = ? " +
                    "WHERE id = ?",
                    "TENANT_B", 1L);
            })
        ).isInstanceOf(DataAccessException.class);
    }

    @Test
    void customTenantGucCannotAuthenticateIdentityOnItsOwn() {
        // Caveat condition: any SQL caller with rls_app
        // and ability to set custom GUCs can pick the TENANT_B string.
        assertThat(visibleCount("TENANT_B")).isEqualTo(1L);
    }
}
```

### 6.4. How to Run and Expectations

Run inside the `spring-rls-demo` directory:

```bash
gradle test --tests demo.SpringRlsIntegrationTest
```

If using a wrapper: `./gradlew test --tests demo.SpringRlsIntegrationTest` on Linux/macOS; `gradlew.bat test --tests demo.SpringRlsIntegrationTest` on Windows. The Docker daemon must be running and able to pull the `postgres:17-alpine` image.

**With a matching build, Docker, and database, all 19 tests are expected to pass** and Gradle ends with `BUILD SUCCESSFUL`. This is an **expectation based on the code**, not a log from running the project. Reports are in `build/reports/tests/test/index.html`.

| Group | Expectation |
| --- | --- |
| Role/proxy | Spring DataSource truly connects as `rls_app`, service has a Spring AOP proxy |
| No tenant | SELECT returns 0 rows |
| Tenant A/B | COUNT returns 3 and 1 respectively |
| Transaction-local | Tenant A does not leak to the next transaction |
| READ public / owner draft | Allowed within the right tenant |
| READ another user's draft | Application denies even though RLS sees the row |
| READ another tenant | RLS returns zero rows |
| Missing `DOC_READ` | Denied at `@PreAuthorize`, `probe.reads()==0` |
| Unknown tenant | Fails closed |
| UPDATE own DRAFT | Succeeds, content changes |
| UPDATE other owner / other tenant | Denied or affected rows=0 |
| CREATE | Owner and tenant assigned server-side |
| Missing `DOC_CREATE` | Method body does not run |
| INSERT tenant B while scoped to A | PostgreSQL `WITH CHECK` throws error |
| UPDATE changing tenant A→B | PostgreSQL `WITH CHECK` throws error |
| Custom GUC | Test shows SQL callers can set context; need another trust boundary if strict isolation is required |

**Example limitations:** the `postgres` role is used only to reset fixtures; `rls_app` is the role tested against RLS. The demo does not implement HTTP controllers, full DTO field redaction, SQL injection scanners, multiple DB roles, approval/export workflows, PgBouncer, event/audit logs, or Testcontainers across all PostgreSQL versions. Add those before production.

## 7. When Is RLS Alone or Method Security Alone Not Enough?

### Method Security Only

Without RLS, a buggy repository:

```sql
SELECT * FROM documents WHERE id = :id;
```

can fetch out-of-tenant rows. Even when `@PreAuthorize("hasAuthority('DOC_READ')")` passes, that authority does not prove the user can read **that specific ID**. You must add object/tenant policies in the application or SQL, with RLS acting as a complementary defense layer.

### RLS Only

Without Method Security, same-tenant users can invoke operations for which they **lack functional authority** if the application exposes services/endpoints. Tenant RLS knows nothing about `DOC_APPROVE` or `DOC_EXPORT`, does not forbid self-approval, and does not filter sensitive columns based on Spring role policies.

### Both Enabled, Wrong DB Role

If Spring DataSource connects as a table owner or a `BYPASSRLS` account, RLS may be skipped entirely. Any tenant-context tests run under that account fail to prove row isolation.

### Both Enabled, Setting Leaks Through the Pool

If request A calls `set_config(..., false)` and returns the connection to the pool, request B may inherit tenant A. Use transaction-local settings and test connection reuse. Parameter `true` must run **inside** a transaction; outside a transaction (autocommit), the context vanishes before the next statement.

### Both Enabled, SQL Injection Modifies the GUC

If an attacker can run arbitrary SQL via the application role, they can change `app.tenant_id`. This is an **important limitation of the model**; never describe a custom GUC as an unforgeable identity.

## 8. Additional Production Scenarios to Handle

### 8.1. Multiple Tables and JOINs

RLS on `documents` does not automatically apply to `attachments`, `comments`, `document_versions`, `audit_log`, or `exports`. Inventory every table holding tenant data, define matching policies, and prevent joins from leaking out-of-tenant records. If child tables lack `tenant_id`, consider `EXISTS` policies against the parent table, proper constraints, and indexes; review recursion, SQL privileges, and security context carefully.

### 8.2. Multiple Policies

PostgreSQL has `PERMISSIVE` and `RESTRICTIVE` policies. Multiple permissive policies combine with **OR**, whereas restrictive policies add **AND** conditions alongside matching permissive policies. A stray `USING (true)` policy can unintentionally open access if bound to the wrong role/command. Test policy combinations under **the exact runtime role**, never assuming all rules combine with AND.

### 8.3. Views, Functions, Table Owners

Views, `SECURITY DEFINER` functions, function owners, `search_path`, table owners, and role-switching privileges can alter who executes a query and whether RLS applies. Audit export/report paths and background jobs, not just direct repositories. PostgreSQL supports `security_invoker` on views in newer versions, though it must be configured and tested properly.

### 8.4. Field-Level Authorization and Exports

RLS filters **rows**, it does not automatically mask `salary`, `secretNote`, or `nationalId`. Use DTO field allowlists, column privileges, and dedicated policies when exporting data. For batches/exports, verify every row and column is permitted; bind tenant in queries and protect generated files/jobs/URLs.

### 8.5. Concurrency and TOCTOU

A `@PreAuthorize` check can execute before the business transaction or before row state changes. For sensitive DELETE, APPROVE, and UPDATE operations, use conditional writes, optimistic locking, or `SELECT ... FOR UPDATE` inside transactions; handle affected row counts and rollbacks. Never assume passing an authority check once guarantees subsequent state remains valid.

### 8.6. Performance and Large Datasets

Row policies participate in query planning; create indexes such as `(tenant_id, id)` and `(tenant_id, owner_name, status)` matching workloads, and inspect `EXPLAIN (ANALYZE, BUFFERS)` safely. Never disable RLS in production to "speed things up" without a replacement control design. When paginating, enforce tenant scope in SQL instead of loading the entire table and filtering in Java.

### 8.7. Background Jobs, Multi-Tenant Users, Revocation

Service accounts/jobs must have dedicated identities/scopes; never grant a default `ALL`-tenant bypass for convenience. Users belonging to multiple tenants must have membership verified server-side on every tenant switch, with auditing. When permissions are revoked, update tokens/sessions/permission caches and running export jobs per SLA.

## 9. Layer-by-Layer Debugging

| Symptom | Cause to Check | Verification Step |
| --- | --- | --- |
| RLS still sees all tenants | DB user is owner/superuser/BYPASSRLS | `SELECT current_user`, owner, role attrs, FORCE RLS |
| SQL returns 0 rows despite right tenant | Tenant unset or set outside transaction | `current_setting(..., true)` inside same transaction |
| Request A's tenant appears in Request B | Session setting `false` with pool reuse | Test transaction-local with pool size 1 |
| Out-of-tenant SELECT empty yet UPDATE switches tenant | Missing or flawed `WITH CHECK` | Integration test UPDATE tenant A→B |
| Method skips authority check | Missing `@EnableMethodSecurity`, `new` instance, self-invocation | Test Spring proxy and deny before method body |
| Method lets user read another's draft in same tenant | RLS only enforces tenant predicate | Add owner/status policies in Java/SQL |
| SQL hits permission denied | Missing table/schema `GRANT`, wrong role | Inspect grants and `current_user` |
| View query sees more than base table | Owner/security-definer/security context | Test view with exact runtime role |
| Holding DOC_EXPORT downloads all columns | RLS does not hide columns | DTO projections, column privileges, export policies |
| Update returns 0 despite having role | Row hidden by RLS or owner/status changed | Distinguish row-level vs app-level conditions |
| Custom-GUC RLS bypassed by SQL injection | GUC is self-set by app DB role | Fix injection, adopt stronger DB trust model |
| Slow queries | Predicates/indexes/joins/policy functions | `EXPLAIN`, indexes, performance tests |

## 10. Implementation Checklist

- [ ] Spring Method Security is enabled and all sensitive service operations run through Spring proxies; no self-invocation bypasses.
- [ ] READ/CREATE/UPDATE/DELETE/APPROVE/EXPORT permissions are separated where needed; tenant, owner, status, fields, and scope have explicit rules.
- [ ] RLS is enabled on all tenant-scoped tables; both `USING` and `WITH CHECK` are tested.
- [ ] Runtime database role **does not** own tables, nor hold SUPERUSER or BYPASSRLS; it has minimal SQL privileges only.
- [ ] Tenant is resolved from verified identity/membership; clients cannot grant themselves tenant switches.
- [ ] Tenant context uses `set_config(..., true)` inside the transaction on the same connection as SQL; never session-level settings.
- [ ] Missing tenant context denies, never falling back to a "broad default tenant".
- [ ] Negative tests cover direct SQL without tenant, wrong tenant, cross-tenant writes, missing authority, wrong owner, and stale status.
- [ ] Distinguish SQL affected rows=0 from `WITH CHECK` errors; never leak cross-tenant resource IDs.
- [ ] Verify connection pool reuse, multiple DataSources, PgBouncer, and nested/async/background jobs.
- [ ] Threat-model custom GUCs against SQL injection/DB-role compromise; do not call them DB-authenticated identities.
- [ ] Review views/functions/exports/DDL/column privileges and indexes/performance.
- [ ] Maintain auditing, migration/rollback strategies, and tests on the exact production PostgreSQL version and DB role.

## 11. Exercises

1. **Missing `WHERE tenant`:** remove the tenant predicate in the repository while keeping RLS; verify `TENANT_A` still sees strictly three records.
2. **Wrong owner:** Alice has `DOC_READ`; try reading Bob's DRAFT in the same tenant and explain why RLS alone is insufficient.
3. **Wrong functional permission:** give Alice `DOC_UPDATE` without `DOC_READ`; `@PreAuthorize` must block the READ call before the body runs.
4. **Missing scope:** omit `set_config`; SELECT must return 0 rows instead of defaulting to TENANT_A.
5. **Cross-tenant INSERT/UPDATE:** test `WITH CHECK` with two negative tests and confirm transaction rollback.
6. **Pool leakage:** compare transactional `set_config(..., true)` vs session `false` in an isolation test. Never use `false` in production.
7. **Multiple memberships:** give a user A+B memberships; design tenant switching only after server-side membership checks.
8. **SQL injection threat:** explain why custom GUCs can be forged if the DB role runs arbitrary SQL; propose stronger DB identity/trust boundaries.
9. **Business tenant move:** design a privileged audited workflow to migrate documents A→B instead of temporarily disabling RLS in normal requests.

## 12. Key Takeaways

**Spring Security** answers *who may perform which action on which data*; **PostgreSQL RLS** restricts *which rows the DB role may see/write*. `USING` governs accessed rows; `WITH CHECK` governs post-write rows. RLS effectiveness depends on a non-bypassing DB role, transaction-scoped tenant context, and protecting the source of that tenant.

RLS is a valuable complementary defense when application code forgets a tenant filter, yet a role-set custom `app.tenant_id` **cannot replace trusted identity checks or defend against SQL injection**. Test both the application and the real database with **allow, deny, cross-tenant, invalid write, and context reset** cases.

## Official References

- Spring Security 6.5 — Method Security and `@EnableMethodSecurity`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- PostgreSQL 18 — Row Security Policies, owners, and BYPASSRLS: https://www.postgresql.org/docs/18/ddl-rowsecurity.html
- PostgreSQL 18 — CREATE POLICY, USING, and WITH CHECK: https://www.postgresql.org/docs/18/sql-createpolicy.html
- PostgreSQL 18 — `current_setting` and `set_config`: https://www.postgresql.org/docs/18/functions-admin.html
- Spring Boot 3.5 — Testcontainers, `@DynamicPropertySource`: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Framework — Programmatic transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
