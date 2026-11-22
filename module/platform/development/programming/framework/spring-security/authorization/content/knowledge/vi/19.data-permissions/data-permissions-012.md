# Kết hợp kiểm tra ứng dụng với Row-Level Security ở cơ sở dữ liệu

## 1. Mục tiêu

Trong Spring Security, `@PreAuthorize` có thể bảo vệ lời gọi đến service, nhưng database vẫn có thể bị truy vấn qua những đường khác: một repository viết thiếu `WHERE tenant_id = ...`, một background job, một endpoint mới hoặc một câu JDBC trực tiếp. Ngược lại, **Row-Level Security (RLS)** ở cơ sở dữ liệu có thể lọc hàng theo chính sách SQL, nhưng không tự hiểu đầy đủ quyền nghiệp vụ như `DOC_READ`, `DOC_APPROVE`, trạng thái DRAFT hay trường dữ liệu nhạy cảm.

Giải pháp phòng thủ nhiều lớp:

- **Application authorization:** Spring Security xác thực principal và kiểm tra quyền **hành động**; service kiểm tra owner, trạng thái, tenant membership, field-level policy.
- **Database RLS:** PostgreSQL tự áp dụng điều kiện trên **các hàng** mà DB role được phép đọc/ghi.
- **Trusted tenant scope:** ứng dụng lấy tenant từ identity/directory đã xác minh, cài context trong **transaction hiện tại** trên đúng JDBC connection.
- **Least-privilege DB role:** tài khoản runtime không sở hữu bảng, không SUPERUSER hoặc `BYPASSRLS`.
- **Kiểm thử độc lập:** chứng minh cả chặn trước thân method **và** chặn trực tiếp tại SQL, kể cả khi câu SQL thiếu điều kiện tenant.

Sau bài học thuộc nhóm **Quyền trên dữ liệu** của Spring Security Authorization, bạn có thể giải thích `USING` và `WITH CHECK`, viết `CREATE POLICY`, tránh rò tenant context qua connection pool, thiết kế các kiểm tra ứng dụng + DB có trách nhiệm rõ, và chạy integration test Java 17+ trên **PostgreSQL thật bằng Testcontainers**.

**Môi trường minh họa:** Spring Boot 3.5.x, Spring Security 6.5.x, PostgreSQL 17, Java 17+, JUnit 5, JDBC, Gradle và Docker cho Testcontainers. SQL này dành cho PostgreSQL; RLS của database khác có cú pháp và semantics khác.

## 2. Hai lớp bảo mật giải quyết hai câu hỏi khác nhau

Giả sử bảng tài liệu:

| ID | Tenant | Owner | Status | Body |
| --- | --- | --- | --- | --- |
| 1 | TENANT_A | alice | PUBLISHED | Public A |
| 2 | TENANT_A | bob | DRAFT | Bob draft |
| 3 | TENANT_B | carol | PUBLISHED | Public B |
| 4 | TENANT_A | alice | DRAFT | Alice draft |

Chính sách nghiệp vụ ví dụ:

1. `DOC_READ` là **quyền gọi chức năng** đọc. Trong tenant đã được xác minh, mọi người được đọc tài liệu PUBLISHED; DRAFT chỉ owner đọc.
2. `DOC_UPDATE` là quyền gọi chức năng sửa. Chỉ chủ sở hữu được sửa **DRAFT** của mình; không được tự chuyển tenant.
3. `DOC_CREATE` cho phép tạo DRAFT. `tenant_id`, `owner_name` và `status` do server đặt; client không tự khai owner hay tenant tùy ý.
4. Không có authority cần thiết, tenant membership không xác minh được, object không thấy được hoặc điều kiện business thất bại thì **deny**.
5. PostgreSQL RLS áp dụng **đúng tenant** cho mọi SELECT/INSERT/UPDATE/DELETE do role ứng dụng thực thi. Tenant B không được hiện ra trong truy vấn của tenant A, kể cả câu SQL không có `WHERE tenant_id`.

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
              đúng tenant       sai tenant
               rows visible    rows hidden/write rejected
                           |
                           v
              App checks DRAFT owner/status
                           |
                           v
                 Allowed result or deny
```

Trong ví dụ, Java policy chặn Alice đọc bản DRAFT của Bob **ngay cả khi** RLS cho thấy cả hai cùng TENANT_A. RLS chặn Alice đọc PUBLISHED của Carol thuộc TENANT_B **ngay cả khi** cô ấy có `DOC_READ`. Hai quyết định bổ sung, không thay thế nhau.

## 3. PostgreSQL Row-Level Security: cơ chế cốt lõi

### 3.1. Bật RLS và tạo policy

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

Giải thích:

- `ENABLE ROW LEVEL SECURITY` bật việc kiểm tra row policy cho role chịu RLS trên bảng này.
- `CREATE POLICY` định nghĩa quy tắc; `FOR ALL` áp dụng cho nhiều thao tác SQL, `TO rls_app` chọn database role cần được áp dụng.
- `USING` quyết định những hàng **đang tồn tại** nào được nhìn thấy hoặc chọn để sửa/xóa.
- `WITH CHECK` quyết định một hàng **sau khi INSERT/UPDATE** có hợp lệ hay không.
- `current_setting('app.tenant_id', true)` lấy tenant context từ PostgreSQL session. Đối số `true` cho phép trả `NULL` khi setting chưa có thay vì ném lỗi.
- `NULLIF(..., '')` bảo đảm giá trị rỗng cũng không được xem như một tenant hợp lệ. So sánh `tenant_id = NULL` không thành `TRUE`, vì thế policy fail closed.
- Khi RLS bật và **không có policy áp dụng** cho role/lệnh, PostgreSQL mặc định từ chối hàng (default-deny), trừ các role có đặc quyền bypass.

**RLS không tự cấp SQL privileges.** Ngoài policy, runtime DB role vẫn cần `GRANT SELECT, INSERT, UPDATE, DELETE` phù hợp; quyền thao tác bảng và quyền trên từng hàng là **hai lớp**.

### 3.2. `USING` và `WITH CHECK` không giống nhau

| Thao tác | `USING` | `WITH CHECK` |
| --- | --- | --- |
| SELECT | Lọc hàng được đọc | Không xét hàng mới |
| INSERT | Không có hàng cũ | Kiểm tra hàng mới |
| UPDATE | Hàng cũ phải được phép chọn để sửa | Hàng sau sửa phải hợp lệ |
| DELETE | Hàng cũ phải được phép chọn để xóa | Không có hàng mới |
| MERGE | Các nhánh liên quan phải tuân policy tương ứng | Kiểm tra hàng kết quả theo quy tắc liên quan |

Ví dụ đang ở context TENANT_A:

```sql
-- RLS cho phép nhìn Document #1.
SELECT * FROM public.documents WHERE id = 1;

-- RLS giấu Document #3 (TENANT_B); thường trả 0 hàng.
SELECT * FROM public.documents WHERE id = 3;

-- Hàng cũ thuộc A nhưng hàng mới sẽ thuộc B:
-- WITH CHECK từ chối câu lệnh này.
UPDATE public.documents SET tenant_id = 'TENANT_B'
WHERE id = 1;

-- INSERT mới vào B khi tenant hiện hành là A cũng bị từ chối.
INSERT INTO public.documents
    (id, tenant_id, owner_name, status, body)
VALUES (100, 'TENANT_B', 'alice', 'DRAFT', 'Invalid');
```

Nếu chỉ có `USING` mà thiếu `WITH CHECK`, PostgreSQL có quy tắc kế thừa biểu thức trong một số policy types, nhưng không nên dựa vào suy đoán. Hãy **ghi rõ cả hai** khi chính sách yêu cầu hàng trước/sau đều ở cùng tenant.

Khi một hàng bị `USING` giấu, SELECT thường trả rỗng và UPDATE/DELETE có thể affected rows = 0. Khi hàng mới vi phạm `WITH CHECK`, INSERT/UPDATE thường báo lỗi SQL. Ứng dụng cần kiểm tra số affected rows, xử lý exception và quyết định dùng HTTP 403/404/409 theo hợp đồng mà không làm lộ ID thuộc tenant khác.

### 3.3. Table owner, superuser, BYPASSRLS

PostgreSQL RLS dựa trên **database role**. Những role sau có thể vượt chính sách:

- **Superuser**: luôn có quyền bypass RLS.
- Role mang thuộc tính **`BYPASSRLS`**: bypass RLS.
- **Chủ sở hữu bảng**: thường bypass RLS; `ALTER TABLE ... FORCE ROW LEVEL SECURITY` buộc table owner tuân RLS, nhưng không chặn superuser/BYPASSRLS.

Vì vậy, integration test phải có **role riêng không sở hữu bảng**. Nếu ứng dụng kết nối bằng `postgres` rồi test “đọc được mọi tenant”, đó là bằng chứng dùng sai role, không phải RLS hoạt động.

```text
postgres / migration_owner
    -> tạo bảng, tạo policy, GRANT; không dùng trong app runtime

rls_app
    -> không sở hữu bảng, không SUPERUSER, không BYPASSRLS
    -> SQL privileges tối thiểu
    -> Spring JDBC DataSource dùng role này
```

`TRUNCATE`, `REFERENCES` và một số thao tác quản trị không chịu row policy như SELECT/UPDATE. Không cấp chúng, quyền DDL hoặc quyền `SET ROLE` không cần thiết cho tài khoản ứng dụng. Views, SECURITY DEFINER functions, owner privileges và các đường export/report phải được review riêng.

## 4. Tenant context trong transaction và connection pool

### 4.1. Thiết lập tenant theo transaction

PostgreSQL hỗ trợ:

```sql
SELECT set_config('app.tenant_id', 'TENANT_A', true);
```

Tham số cuối `true` có nghĩa setting có hiệu lực **chỉ trong transaction hiện tại**, tương ứng `SET LOCAL`. Sau commit/rollback, setting local được gỡ. `false` đặt ở cấp session, có thể tồn tại qua nhiều request khi JDBC connection được trả vào pool.

**Sai cách:**

```java
// Anti-pattern: nhận tenant trực tiếp từ client,
// lưu trên DB session; connection pool có thể tái sử dụng.
jdbcTemplate.queryForObject(
    "SELECT set_config('app.tenant_id', ?, false)",
    String.class,
    requestTenant
);
```

Ở đây `requestTenant` không đáng tin và `false` có thể gây **tenant context leakage** giữa request A và B.

**Cách tốt hơn:**

```java
return transactionTemplate.execute(status -> {
    String tenant = trustedTenantDirectory.resolve(authentication);
    jdbcTemplate.queryForObject(
        "SELECT set_config('app.tenant_id', ?, true)",
        String.class,
        tenant
    );
    return jdbcTemplate.query(/* business query cùng transaction */);
});
```

Đây là snippet ý tưởng: cần `TransactionTemplate`, `JdbcTemplate`, trusted identity và câu SQL thực tế. Điểm cốt lõi là **set context và query phải nằm trong cùng transaction/cùng Spring-bound JDBC connection**. Không đặt `set_config(..., true)` ở một autocommit statement rồi chạy business query sau đó trên connection khác.

**Khi dùng PgBouncer transaction pooling**, càng không được dựa vào session setting giữa hai transaction. Với multi-DataSource, tenant context phải được đặt trên từng connection cần truy vấn. Với `REQUIRES_NEW`, background job, async hoặc R2DBC, cơ chế context/transaction phải được thiết kế riêng cho từng luồng.

### 4.2. Tenant lấy từ đâu?

Tenant được quyền truy cập phải đến từ **danh tính đã được xác thực + dữ liệu membership phía server**, không được tin trực tiếp header `X-Tenant-Id`, URL path hay request body. Một người có thể có quyền trên nhiều tenant; server cần kiểm tra membership và quyền chuyển tenant trước khi đặt context.

Trong test phía dưới, mapping `alice → TENANT_A`, `carol → TENANT_B` nằm trong một Java map cố định để dễ thấy cơ chế. Production nên dùng identity provider/tenant membership service/repository đáng tin.

### 4.3. Giới hạn an ninh rất quan trọng của custom GUC

**`app.tenant_id` không phải identity được database chứng thực.** Runtime role có thể tự gọi `set_config('app.tenant_id', 'TENANT_B', true)` nếu nó được phép thực thi SQL tùy ý. Vì vậy mô hình custom GUC + RLS là **defense-in-depth chống thiếu điều kiện tenant trong các truy vấn thông thường**, nhưng **không phải cách ly bất khả giả mạo trước SQL injection hoặc DB-role compromise**.

Cần kết hợp prepared statements, code review, SQL allowlist, quyền DB tối thiểu, không cho client chạy SQL tùy ý, audit và threat modeling. Nếu yêu cầu database **tự xác minh tenant ngay cả khi app role bị lộ**, hãy cân nhắc tenant-specific DB identities/roles/connections, tách database/schema có kiểm soát, hoặc mechanism DB-verified claims với function đặc quyền được review kỹ. Chỉ đổi tên setting thành `app.secure_tenant_id` không giải quyết trust boundary.

## 5. Kiểm tra ứng dụng trước và trong transaction

Một thiết kế tốt tách:

- **Function-level:** `@PreAuthorize("hasAuthority('DOC_READ')")` bảo vệ lời gọi đến service, trước khi chạy thân method.
- **Object/workflow-level:** khi đọc kết quả **đã bị RLS lọc**, Java vẫn kiểm tra owner của DRAFT; khi sửa, SQL yêu cầu `owner_name = authentication.name` và `status='DRAFT'`.
- **Tenant-level:** RLS lọc dựa trên tenant context; câu SQL chỉ dùng `WHERE id = ?` vẫn không đọc hàng tenant khác.
- **Concurrency-level:** transactional conditional update/optimistic locking tránh sửa tài liệu vừa đổi trạng thái. Một check trước body không tự ngăn mọi race condition.

Ví dụ minh họa có phân tầng:

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

Đây là **fragment** cần beans/imports và Spring context, không phải class độc lập. Nó kết hợp authority ở proxy, owner/status trong SQL và tenant RLS. `@PreAuthorize` có thể bị bỏ qua bởi **self-invocation** trong Spring proxy mode; phải gọi qua Spring bean, không tự `this.updateDraft(...)` trong cùng target.

### 5.1. RLS không thay field-level security

RLS giới hạn **hàng**. Nếu tài liệu chứa `salary`, `personalId`, `secretNote`, một user được thấy hàng không có nghĩa được thấy mọi cột. Cần DTO allowlist/redaction, column privileges, view với security context phù hợp và policy ở ứng dụng. Với EXPORT, không dùng `SELECT *` rồi hy vọng RLS đã che hết PII: RLS không tự giải quyết những trường nhạy cảm hay khối lượng xuất.

## 6. Bài thực hành Java 17+ và PostgreSQL Testcontainers

Test cần **PostgreSQL thật**, vì H2 không mô phỏng đúng `CREATE POLICY`, RLS roles và `set_config`. Project dùng PostgreSQL 17 trong Docker, schema được tạo bởi role `postgres`; Spring DataSource đăng nhập bằng **`rls_app`**, một role không sở hữu bảng.

**Điều kiện chạy:** JDK 17+, Gradle, Docker daemon, quyền tải image PostgreSQL từ container registry và tải dependency Maven Central. Đây là project test cô lập, không chứa mật khẩu production.

### 6.1. Bố cục và Gradle

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

Vì toàn bộ Java code đặt dưới `src/test/java`, `testImplementation` là đủ. Với ứng dụng chạy thực, đưa starter JDBC/Security vào `implementation`, driver vào `runtimeOnly`, test dependencies vẫn ở test scope. Spring Boot BOM giúp tránh trộn version library không tương thích.

### 6.2. Schema, quyền role và RLS

`src/test/resources/db/rls-schema.sql`:

```sql
-- Testcontainers chạy init script bằng database admin postgres.
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

`postgres` sở hữu bảng và có thể reset fixture. `rls_app` chỉ có DML privileges và **không bypass RLS**. Dù có `GRANT SELECT`, `rls_app` không thấy hàng tenant B khi transaction context là tenant A; không có context thì không thấy hàng nào.

### 6.3. Integration test đầy đủ

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
        // Dữ liệu server-side giả lập membership để học.
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
                Doc doc = find(id); // Đã bị RLS lọc theo tenant.
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
        // Chỉ test fixture admin; Spring app vẫn kết nối rls_app.
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
        // Điều kiện cảnh báo: bất kỳ SQL caller có rls_app
        // và quyền đặt custom GUC đều có thể chọn chuỗi TENANT_B.
        assertThat(visibleCount("TENANT_B")).isEqualTo(1L);
    }
}
```

### 6.4. Cách chạy và kỳ vọng

Chạy trong thư mục `spring-rls-demo`:

```bash
gradle test --tests demo.SpringRlsIntegrationTest
```

Nếu có wrapper: Linux/macOS dùng `./gradlew test --tests demo.SpringRlsIntegrationTest`; Windows dùng `gradlew.bat test --tests demo.SpringRlsIntegrationTest`. Docker daemon phải hoạt động và có thể tải image `postgres:17-alpine`.

**Khi build, Docker và database phù hợp, kỳ vọng 19 test thành công** và Gradle kết thúc `BUILD SUCCESSFUL`. Đây là **kỳ vọng theo code**, không phải log từ việc đã chạy project. Báo cáo nằm ở `build/reports/tests/test/index.html`.

| Nhóm | Kỳ vọng |
| --- | --- |
| Role/proxy | Spring DataSource thật sự dùng `rls_app`, service có Spring AOP proxy |
| Không tenant | SELECT trả 0 hàng |
| Tenant A/B | COUNT lần lượt 3 và 1 |
| Transaction-local | Tenant A không rò sang transaction kế tiếp |
| READ public / owner draft | Cho phép trong tenant đúng |
| READ draft người khác | Ứng dụng từ chối dù RLS thấy hàng |
| READ tenant khác | RLS không trả hàng |
| Thiếu `DOC_READ` | Deny ở `@PreAuthorize`, `probe.reads()==0` |
| Unknown tenant | Fail closed |
| UPDATE own DRAFT | Thành công, nội dung thay đổi |
| UPDATE other owner / other tenant | Deny hoặc affected rows=0 |
| CREATE | Chủ sở hữu và tenant gán phía server |
| Thiếu `DOC_CREATE` | Không chạy method body |
| INSERT tenant B khi scope A | PostgreSQL `WITH CHECK` báo lỗi |
| UPDATE đổi tenant A→B | PostgreSQL `WITH CHECK` báo lỗi |
| Custom GUC | Test cho thấy SQL caller có khả năng set context; cần trust boundary khác nếu yêu cầu cách ly cứng |

**Giới hạn ví dụ:** role `postgres` chỉ dùng để thiết lập fixture; app role `rls_app` mới là bên được kiểm tra RLS. Demo không triển khai HTTP controller, full DTO field redaction, SQL injection scanner, nhiều DB role, approval/export workflow, PgBouncer, event/audit log hay Testcontainers cho mọi phiên bản PostgreSQL. Những phần đó cần bổ sung trước production.

## 7. Khi nào chỉ có RLS hoặc chỉ có Method Security là chưa đủ?

### Chỉ Method Security

Nếu thiếu RLS, một repository viết sai:

```sql
SELECT * FROM documents WHERE id = :id;
```

có thể lấy hàng ngoài tenant. Ngay cả khi `@PreAuthorize("hasAuthority('DOC_READ')")` thành công, authority này không chứng minh user được đọc **ID cụ thể**. Phải thêm object/tenant policy ở application hoặc SQL, và RLS làm lớp phòng thủ bổ sung.

### Chỉ RLS

Nếu thiếu Method Security, cùng-tenant user có thể chạy thao tác mình **không có quyền chức năng** nếu ứng dụng để lộ service/endpoint. RLS tenant không tự biết `DOC_APPROVE` hay `DOC_EXPORT`, không cấm tự duyệt tài liệu và không lọc cột nhạy cảm theo policy role trong Spring.

### Cả hai nhưng thiết lập sai DB role

Nếu Spring DataSource dùng account sở hữu bảng hoặc BYPASSRLS, RLS có thể không được áp dụng. Khi đó mọi cố gắng test tenant context bằng account đó đều không chứng minh cơ chế row isolation.

### Cả hai nhưng setting rò qua pool

Nếu một request A gọi `set_config(..., false)` rồi trả connection vào pool, request B có thể dùng lại tenant A. Dùng transaction-local và kiểm thử session reuse. Tham số `true` phải nằm **trong** transaction; ngoài transaction/autocommit, context thường không tồn tại cho statement kế tiếp.

### Cả hai nhưng SQL injection cho phép sửa GUC

Nếu attacker có thể chạy SQL tùy ý qua role ứng dụng, họ có thể đổi `app.tenant_id`. Đây là **giới hạn quan trọng của mô hình**; không mô tả custom GUC như danh tính không thể giả mạo.

## 8. Các tình huống production cần xử lý thêm

### 8.1. Nhiều bảng và JOIN

RLS trên `documents` không tự áp dụng lên `attachments`, `comments`, `document_versions`, `audit_log` hay `exports`. Kiểm kê từng bảng chứa dữ liệu tenant, định nghĩa policy tương ứng, tránh join ra record ngoài tenant. Nếu bảng con không có tenant_id, có thể cần policy `EXISTS` theo bảng cha, constraint và index thích hợp; phải review recursion, SQL privileges, security context.

### 8.2. Multiple policies

PostgreSQL có `PERMISSIVE` và `RESTRICTIVE` policies. Nhiều policy permissive có thể kết hợp theo **OR**, trong khi restrictive thêm điều kiện theo **AND** khi có policy cho phép phù hợp. Một policy mới `USING (true)` có thể mở quyền ngoài dự định nếu gắn sai role/command. Test các tổ hợp policy trên **đúng role runtime**, không giả định mọi rule đều AND.

### 8.3. VIEW, function, table owner

Views, SECURITY DEFINER functions, function owner, `search_path`, table owner và quyền switch role có thể thay đổi ai thực thi truy vấn và liệu RLS có được áp dụng. Kiểm tra các đường export/report và background jobs, không chỉ repository trực tiếp. PostgreSQL hỗ trợ `security_invoker` cho view ở các phiên bản phù hợp, nhưng cần cấu hình và thử nghiệm đúng.

### 8.4. Field-level authorization và export

RLS lọc **hàng**, không tự che `salary`, `secretNote`, `nationalId`. Dùng DTO field allowlist, column privileges và policy riêng khi xuất dữ liệu. Với batch/export, kiểm tra mọi dòng/cột được cấp quyền; ràng buộc tenant ở query và bảo vệ file/job/URL sau tạo.

### 8.5. Concurrency và TOCTOU

Một `@PreAuthorize` check có thể xảy ra trước transaction business hoặc trước khi hàng đổi trạng thái. Với DELETE, APPROVE, UPDATE nhạy cảm cần conditional write, optimistic locking hoặc `SELECT ... FOR UPDATE` hợp lý trong transaction; xử lý affected rows và rollback. Không coi authority pass một lần là bảo đảm mọi trạng thái sau đó vẫn đúng.

### 8.6. Performance và dữ liệu lớn

Row policy tham gia query planning; cần index như `(tenant_id, id)` và `(tenant_id, owner_name, status)` theo workload, kiểm tra `EXPLAIN (ANALYZE, BUFFERS)` khi an toàn. Không tắt RLS production để “tăng tốc” mà chưa có thiết kế kiểm soát thay thế. Khi lọc pagination, thực hiện tenant scope trong SQL thay vì tải cả bảng rồi lọc trong Java.

### 8.7. Background jobs, multi-tenant user, revoke

Service account/job phải có identity/phạm vi riêng; tuyệt đối không cấp một tenant mặc định `ALL` cho thuận tiện. Một user thuộc nhiều tenant phải được server xác thực membership trước mỗi lần đổi tenant, audit lựa chọn đó. Khi quyền bị thu hồi, update token/session/permission cache và các export jobs đang chạy theo SLA.

## 9. Debug theo từng tầng

| Triệu chứng | Nguyên nhân cần kiểm tra | Bước xác minh |
| --- | --- | --- |
| RLS vẫn thấy mọi tenant | DB user là owner/superuser/BYPASSRLS | `SELECT current_user`, owner, role attrs, FORCE RLS |
| SQL trả 0 hàng dù user đúng tenant | Chưa set tenant hoặc set ngoài transaction | `current_setting(..., true)` trong cùng transaction |
| Tenant request A xuất hiện ở request B | Session setting `false` và connection pool reuse | Test transaction-local với pool một connection |
| SELECT ngoài tenant rỗng nhưng UPDATE đổi tenant được | Thiếu hoặc sai `WITH CHECK` | Integration test UPDATE tenant A→B |
| Method không kiểm tra authority | Thiếu `@EnableMethodSecurity`, gọi `new`, self-invocation | Test Spring proxy và deny trước body |
| Method cho phép đọc draft người khác cùng tenant | RLS chỉ có tenant predicate | Thêm owner/status policy ở Java/SQL |
| SQL gặp permission denied | Thiếu `GRANT` bảng/schema, role sai | Xem grants và current_user |
| Query view nhìn nhiều hơn bảng | Quyền owner/security-definer/security context | Test view với đúng role runtime |
| Có DOC_EXPORT là tải mọi cột | RLS không che cột | DTO projection, column privileges, export policy |
| Update trả 0 dù có quyền role | Hàng ngoài RLS/owner/status changed | Phân biệt row-level và app-level conditions |
| RLS dựa trên custom GUC nhưng vẫn lộ khi SQL injection | GUC do app DB role tự đặt | Fix injection, DB trust model mạnh hơn |
| Query chậm | Predicate/index/joins/policy functions | EXPLAIN, index, performance tests |

## 10. Checklist triển khai

- [ ] Spring Method Security bật và mọi service operation nhạy cảm được gọi qua Spring proxy; không bỏ qua bằng self-invocation.
- [ ] Quyền READ/CREATE/UPDATE/DELETE/APPROVE/EXPORT tách biệt khi cần; tenant, owner, status, field và scope có rule rõ.
- [ ] RLS bật cho mọi bảng tenant-scoped; `USING` và `WITH CHECK` được test.
- [ ] Database role runtime **không** sở hữu bảng, SUPERUSER hay BYPASSRLS; chỉ có các SQL privileges tối thiểu.
- [ ] Tenant được resolve từ identity/membership đã xác minh; client không tự cấp quyền đổi tenant.
- [ ] Tenant context dùng `set_config(..., true)` trong transaction và cùng connection với SQL; không dùng session setting.
- [ ] Thiếu tenant context là deny, không fallback “tenant mặc định rộng”.
- [ ] Negative tests có: SQL direct không tenant, tenant khác, write sai tenant, thiếu authority, owner sai, stale status.
- [ ] Phân biệt SQL affected rows=0 với lỗi `WITH CHECK`; không làm lộ resource ID cross-tenant.
- [ ] Xác minh connection pool reuse, multiple DataSources, PgBouncer, nested/async/background jobs.
- [ ] Threat model custom GUC trước SQL injection/DB-role compromise; không gọi nó là DB-authenticated identity.
- [ ] Review views/functions/export/DDL/column privileges và index/performance.
- [ ] Có audit, migration/rollback strategy và test trên đúng PostgreSQL version/DB role production.

## 11. Bài tập

1. **Thiếu WHERE tenant:** bỏ điều kiện tenant trong repository nhưng giữ RLS, xác minh `TENANT_A` vẫn chỉ thấy đúng ba bản ghi.
2. **Sai owner:** Alice có `DOC_READ`, thử đọc DRAFT của Bob cùng tenant và giải thích vì sao RLS không đủ.
3. **Sai quyền chức năng:** cho Alice `DOC_UPDATE` nhưng thiếu `DOC_READ`; `@PreAuthorize` phải chặn lời gọi READ trước body.
4. **Thiếu scope:** bỏ `set_config`; SELECT phải trả 0 hàng, không tự default về TENANT_A.
5. **INSERT/UPDATE sai tenant:** kiểm tra `WITH CHECK` bằng hai test negative và xác nhận transaction rollback.
6. **Pool leakage:** so sánh `set_config(..., true)` trong transaction với `false` ở session trong test cách ly. Không dùng cách `false` ở production.
7. **Multiple memberships:** cho user thuộc A+B, thiết kế tenant switch chỉ sau khi server kiểm tra membership.
8. **SQL injection threat:** mô tả vì sao custom GUC có thể bị giả nếu DB role chạy SQL tùy ý; đề xuất DB identity/trust boundary mạnh hơn.
9. **Đổi tenant nghiệp vụ:** thiết kế một workflow đặc quyền để di chuyển tài liệu A→B có audit, thay vì tạm tắt RLS trong request thường.

## 12. Ghi nhớ

**Spring Security** trả lời *ai được thực hiện hành động nào trên dữ liệu nào*; **PostgreSQL RLS** giới hạn *những hàng nào mà DB role nhìn/ghi được*. `USING` xét hàng đang truy cập, `WITH CHECK` xét hàng sau ghi. Hiệu quả của RLS phụ thuộc DB role không bypass, tenant context đúng transaction, và việc bảo vệ nguồn tenant đó.

RLS là lớp phòng thủ bổ sung rất hữu ích khi app quên tenant filter, nhưng custom `app.tenant_id` do role tự đặt **không thể thay thế kiểm tra identity tin cậy hoặc chống SQL injection**. Cần test cả ứng dụng và database thật bằng các trường hợp **allow, deny, cross-tenant, wrong write và context reset**.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Method Security và `@EnableMethodSecurity`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- PostgreSQL 18 — Row Security Policies, owner và BYPASSRLS: https://www.postgresql.org/docs/18/ddl-rowsecurity.html
- PostgreSQL 18 — CREATE POLICY, USING và WITH CHECK: https://www.postgresql.org/docs/18/sql-createpolicy.html
- PostgreSQL 18 — `current_setting` và `set_config`: https://www.postgresql.org/docs/18/functions-admin.html
- Spring Boot 3.5 — Testcontainers, @DynamicPropertySource: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Framework — Programmatic transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
