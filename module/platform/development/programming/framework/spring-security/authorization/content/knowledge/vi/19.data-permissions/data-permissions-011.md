# Ràng buộc giao dịch, khóa và kiểm tra lại khi dữ liệu quyền thay đổi

## 1. Tình huống: quyền hợp lệ lúc kiểm tra nhưng đã bị thu hồi lúc ghi

Một ứng dụng Spring Boot quản lý tài liệu đa tenant. `bob` được cấp quyền `WRITE` cho `Document #11` qua bảng `document_grants`. Người quản lý có thể **thu hồi** grant hoặc **chuyển owner/tenant** bất kỳ lúc nào.

Giả sử hệ thống chỉ kiểm tra quyền lúc bắt đầu request:

```text
Thời gian        Request A: bob sửa nội dung        Request B: alice thu hồi quyền
---------        ---------------------------        ------------------------------
t1               @PreAuthorize: WRITE = true
t2                                                   DELETE grant của bob
t3                                                   COMMIT
t4               UPDATE documents SET body = ...
t5               COMMIT
```

Ở `t4`, `bob` đã mất quyền nhưng vẫn có thể ghi vì Request A dùng lại kết quả kiểm tra ở `t1`. Đây là **TOCTOU — Time of Check, Time of Use** (thời điểm kiểm tra khác thời điểm sử dụng). Lỗi xuất hiện ngay cả khi API đã xác thực user đúng, có `@PreAuthorize`, có `@Transactional` và không hề có SQL injection.

Bài Knowledge này thuộc **Spring Security – authorization**, nhóm **Quyền trên dữ liệu**. Trọng tâm là **ràng buộc transaction, khóa và tái kiểm tra authorization khi owner, tenant, ACL hoặc grant thay đổi**. Ta sẽ phân tích những cam kết thực sự của Spring Security, Spring Transaction và database; sau đó xây dựng một ví dụ Spring Boot/JDBC có kiểm thử cạnh tranh giữa cập nhật và thu hồi quyền.

Sau bài học, bạn có thể:

1. Phân biệt **quyền chức năng** (authority ở authentication) và **quyền động trên dữ liệu** (owner, tenant, ACL, trạng thái, grant trong DB).
2. Chỉ ra cửa sổ TOCTOU khi `@PreAuthorize` chạy trước hoặc nằm ngoài transaction cập nhật.
3. Hiểu vì sao chỉ thêm `@Transactional` hoặc nâng isolation **không tự bảo đảm quyền mới nhất**.
4. Sử dụng **khóa hàng nhất quán** cho cả luồng sửa dữ liệu và luồng thu hồi quyền.
5. Đặt lần kiểm tra quyền cuối **sau khi lấy khóa**, ngay trong transaction ghi.
6. Biết khi nào dùng **conditional UPDATE**, `@Version`/optimistic locking, pessimistic locking và `SERIALIZABLE`.
7. Chạy ví dụ Java 17+ / Spring Boot 3.5.x / H2 JDBC với `@EnableMethodSecurity`, `@PreAuthorize`, `@Transactional` và `SELECT ... FOR UPDATE`.
8. Viết test xác nhận khi **revoke commit trước lượt kiểm tra dưới khóa**, một lượt sửa đang chờ phải bị từ chối.
9. Thiết kế transaction/caching/retry/audit phù hợp khi quyền ở nhiều bảng, nhiều node hoặc nhiều hệ thống.

**Định nghĩa tính đúng cần thống nhất:** ví dụ sẽ bảo đảm hai thao tác **sửa tài liệu** và **thu hồi grant** được sắp thứ tự bằng khóa trên cùng hàng tài liệu. Nếu revoke đã commit trước khi lượt sửa lấy được khóa, lượt sửa phải kiểm tra lại grant và bị từ chối. Nếu lượt sửa lấy khóa trước, nó có thể hoàn tất rồi revoke mới diễn ra: đó là thao tác đã được cấp quyền tại thời điểm nó thắng thứ tự khóa, **không phải** cam kết revoke sẽ hủy mọi công việc đang chạy.

## 2. Ba lớp dữ liệu quyết định quyền

Một quyết định ghi có thể phụ thuộc:

| Lớp dữ liệu | Ví dụ | Tần suất thay đổi | Cần kiểm tra ở đâu? |
| --- | --- | --- | --- |
| Authentication | `sub`, principal ID, authority `document:write` | Login, refresh token, thu hồi account | Security filter/provider và Method Security |
| Thuộc tính domain | `owner_id`, `tenant_id`, `state`, `version` | Chuyển owner/tenant, approve, close | Trong transaction, trên bản ghi thật |
| Grant/ACL/policy | `document_grants`, `acl_entry`, membership, policy version | Chia sẻ, thu hồi, đổi nhóm | Cùng transaction hoặc giao thức nhất quán với cập nhật |

Ví dụ chính sách:

```text
canWrite(actor, document, grants) =
    authenticated(actor)
    AND hasAuthority(actor, "document:write")
    AND actor.tenant == document.tenant
    AND document.state == "DRAFT"
    AND (
          actor.id == document.ownerId
          OR grants.contains(document.id, actor.id, "WRITE")
        )
```

Ở đây `actor` và `tenant` phải được suy từ identity đã xác minh/mapping server, **không** từ `X-User`, `X-Tenant` hay JSON tự khai. `document` và `grants` phải được đọc từ **nguồn dữ liệu có thể cập nhật**. Một boolean `allowed=true` đã cache từ vài phút trước không đủ chứng minh quyền ở thời điểm ghi.

### 2.1. `@PreAuthorize` là lớp chặn cần thiết nhưng không phải khóa DB

Ví dụ:

```java
@PreAuthorize("hasAuthority('document:write')")
@Transactional
public void edit(long documentId, String newBody) {
    // ...
}
```

`@PreAuthorize` trả lời người gọi có authority chung khi proxy intercept. Nó không tự khóa `documents` hoặc `document_grants`, cũng không bắt transaction chứa toàn bộ dữ liệu của policy.

Nếu viết:

```java
@PreAuthorize("hasPermission(#id, 'Document', 'WRITE')")
@Transactional
public void edit(Long id, String newBody) {
    repository.update(id, newBody);
}
```

thì biểu thức `hasPermission` có thể đọc grant **trước khi transaction của method bắt đầu**, tùy advisor ordering/cấu hình. Dù được chạy trong một transaction, nếu có khoảng thời gian giữa check và write mà grant/owner được thay đổi hợp lệ, vẫn phải xác định cơ chế consistency. **Không dựa vào annotation như một khóa hoặc một ảnh chụp quyền bất biến.**

Spring Security 6 dùng `AuthorizationManagerBeforeMethodInterceptor` cho `@PreAuthorize`; Spring Transaction cũng dùng advice trong chế độ proxy. Thứ tự advice có thể cấu hình. Vì vậy ví dụ chính của bài dùng:

- `@PreAuthorize`: kiểm tra **authority chức năng**.
- **Bên trong `@Transactional`**: lấy khóa, đọc dữ liệu quyền mới nhất theo thứ tự khóa, rồi kiểm tra **object-level authorization** trước khi ghi.

### 2.2. `@PostAuthorize` không phù hợp để bảo vệ side effect

Một phương thức:

```java
@PostAuthorize("returnObject.owner == authentication.name")
@Transactional
public Receipt transferMoney(...) {
    // Đã thực hiện thao tác ghi trước khi @PostAuthorize xét kết quả.
}
```

là một mảnh minh họa **thiết kế nguy hiểm**, không phải code runnable. Authorization hậu kiểm có thể chạy sau khi thân method đã gây side effect. Nếu transaction đã commit, từ chối response không đồng nghĩa rollback. Spring Security cũng khuyến cáo không dùng `@PostAuthorize` làm biện pháp duy nhất bảo vệ phương thức ghi.

Với write, hãy **kiểm tra trước khi ghi** và bảo vệ nhất quán điều kiện quyền đến commit.

## 3. `@Transactional` cam kết gì, không cam kết gì?

Spring `@Transactional` định nghĩa **ranh giới giao dịch** khi method được gọi qua proxy/AspectJ thích hợp. Mặc định của Spring gồm:

- `Propagation.REQUIRED`: dùng transaction hiện hữu hoặc mở transaction mới.
- `Isolation.DEFAULT`: dùng mặc định của database/driver.
- `readOnly=false`.
- Rollback mặc định với `RuntimeException` và `Error`; checked exception cần cấu hình `rollbackFor` hoặc xử lý bằng rollback rules tương ứng.
- Trong proxy mode, self-invocation (`this.methodAnnotatedTransactional()`) **không tự kích hoạt** advice giao dịch.

Nó **không tự thực hiện** những việc sau:

1. Kiểm tra `Authentication` hoặc cấp quyền đối tượng.
2. Đọc lại grant/ACL tại thời điểm ghi.
3. Chặn transaction khác thay grant/owner nếu không có lock/serialization tương ứng.
4. Làm cho nhiều database hoặc remote ACL service chung một transaction.
5. Biến cache quyền cũ thành kết quả mới nhất.
6. Bảo đảm mọi câu SQL sau một lần check đều sử dụng cùng policy có hiệu lực.

### 3.1. Isolation không đồng nghĩa “luôn đọc được revoke mới nhất”

| Isolation | Điều đáng chú ý | Giới hạn về authorization |
| --- | --- | --- |
| `READ_UNCOMMITTED` | Có thể cho phép đọc thay đổi chưa commit tùy DB | Không phù hợp làm căn cứ quyền nhạy cảm |
| `READ_COMMITTED` | Mỗi statement thường đọc dữ liệu đã commit theo quy tắc DB | Grant có thể đổi **giữa hai statement** |
| `REPEATABLE_READ` | Có thể giữ snapshot/khóa để tránh một số bất thường | Có thể tiếp tục nhìn snapshot cũ; behavior tùy DB/MVCC |
| `SERIALIZABLE` | DB tìm cách bảo đảm lịch thực thi tương đương tuần tự | Có thể abort do conflict; phải retry toàn **transaction + authorization** |

Không suy luận “đặt `Isolation.REPEATABLE_READ` là chắc chắn không ghi sau revoke” hoặc “`SERIALIZABLE` tự cấm toàn bộ thao tác đã bắt đầu trước revoke”. Cần mô tả **linearization point** hoặc thứ tự quyền mà sản phẩm kỳ vọng, và kiểm thử trên đúng database production.

### 3.2. SQL lock có ngữ nghĩa theo DB

Trong PostgreSQL, `SELECT ... FOR UPDATE` lấy row-level lock, ngăn transaction khác update/delete/lock cùng hàng cho tới khi transaction kết thúc; transaction chờ có thể nhận bản ghi sau cập nhật khi lấy được khóa. H2 hỗ trợ cú pháp tương ứng để thực nghiệm, nhưng lock timeout, MVCC và isolation specifics có thể khác PostgreSQL/MySQL.

**Không chỉ kiểm thử trên H2 rồi kết luận transaction behavior production chắc chắn giống hệt.** Với concurrency và authorization, cần integration test trên đúng DB engine/version đang triển khai.

## 4. Ba họ giải pháp cần phân biệt

### A. Conditional UPDATE — kiểm tra điều kiện ngay trong câu ghi

Ví dụ một SQL update chỉ khi caller còn là owner trong tenant:

```sql
UPDATE documents
SET body = :newBody,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_id = :trustedActorId
  AND state = 'DRAFT'
  AND version = :expectedVersion;
```

Phần `:name` là **named parameter** minh họa; dùng `NamedParameterJdbcTemplate` hoặc cơ chế bind tham số tương ứng. Kiểm tra affected rows: **1** là cập nhật thành công, **0** là không còn khớp một điều kiện. Đừng tự trả thông tin chi tiết về sự tồn tại/owner cho caller không được phép.

Nếu quyền là grant động:

```sql
UPDATE documents
SET body = :newBody,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND state = 'DRAFT'
  AND version = :expectedVersion
  AND EXISTS (
      SELECT 1
      FROM document_grants g
      WHERE g.document_id = documents.id
        AND g.grantee = :trustedActorId
        AND g.action = 'WRITE'
  );
```

Đây là SQL **minh họa**, cần điều chỉnh cú pháp `UPDATE` alias/quan hệ theo DB. Nó giảm khoảng cách giữa check và write, nhưng **một statement không tự biến mọi giao thức revoke concurrent thành realtime linearizable**: kết quả phụ thuộc snapshot/locking của DB, cách cập nhật grant và giao dịch cạnh tranh. Nếu yêu cầu revoke và write phải có **thứ tự rõ ràng**, dùng thêm khóa chung hoặc policy-version đồng bộ.

### B. Pessimistic locking — khóa cùng một hàng điều phối

Hai transaction luôn lấy khóa **document row** trước khi đọc/ghi grant:

```text
Transaction WRITE                      Transaction REVOKE
--------------------------------      --------------------------------
BEGIN                                  BEGIN
SELECT document FOR UPDATE              SELECT document FOR UPDATE
  -> có lock / chờ                        -> chờ / có lock
READ grant và owner sau khi có lock    DELETE document_grants
kiểm tra lại quyền                     COMMIT
UPDATE body + version
COMMIT
```

Nếu WRITE lấy lock trước và commit trước REVOKE, update được phép theo grant lúc đó. Nếu REVOKE lấy lock trước và commit, WRITE sẽ đợi rồi đọc lại grant, thấy đã thu hồi và bị từ chối.

**Điều kiện bắt buộc:** tất cả đường thay quyền liên quan (grant/revoke, đổi owner, tenant, state và những policy row cần thiết) phải **tuân thủ cùng giao thức khóa**. Nếu một job sửa `document_grants` trực tiếp mà không lock `documents`, cam kết sắp thứ tự sẽ bị phá vỡ.

### C. Optimistic locking / policy version

Một lựa chọn ít khóa lâu hơn là gắn `@Version` hoặc `version` với **dữ liệu cần ghi**, cùng một `authorization_version`/`policy_version` cho **quyền liên quan**.

```text
Document:
  id = 11
  version = 7
  authorization_version = 4

Token dự kiến:
  expectedDocumentVersion = 7
  expectedAuthorizationVersion = 4
```

Khi thay grant/owner, transaction tăng `authorization_version` của resource. Lượt ghi dùng điều kiện `WHERE version = 7 AND authorization_version = 4` (và policy) sẽ không cập nhật nếu dữ liệu/quyền đã thay đổi.

`@Version` của JPA **chỉ tự theo dõi entity đang versioned**. Nếu quyền nằm ở bảng `acl_entry`/`document_grants` riêng, thay đổi bảng ấy **không tự tăng** `Document.version`. Vì vậy nếu muốn optimistic authorization consistency, cần **liên kết version của policy** và cập nhật nó trên mọi đường sửa quyền.

## 5. Ví dụ thực tiễn: giao thức khóa dùng chung cho write và revoke

Ta xây dựng ứng dụng Java 17+ với:

- Spring Boot 3.5.8, Spring Security Method Security.
- Spring JDBC `JdbcTemplate` và database H2 in-memory.
- `@Transactional` ở service ghi và service thu hồi.
- `SELECT ... FOR UPDATE` trên `documents` để điều phối hai luồng.
- Quyền `document:write` từ Authentication; quyền `WRITE` trên resource từ bảng `document_grants`.
- Mapping user/tenant từ server directory; không nhận principal/tenant do request tự khai.
- Không có HTTP controller; demo chạy bằng `CommandLineRunner` và test gọi Spring-managed beans.
- Transaction/revoke test dùng hai thread và latch, không dựa vào `Thread.sleep()` tùy may rủi.

**Mục tiêu demo:** khi grant của `bob` bị thu hồi và đã commit **trước lúc lượt sửa lấy khóa document**, `bob` không được ghi. Trong một request đang giữ lock hợp lệ, revoke phải chờ; yêu cầu thu hồi không tự hủy công việc đã thắng khóa.

### 5.1. Cấu trúc dự án

```text
transactional-authorization-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── TransactionAuthorizationApplication.java
    │   │   ├── DocumentRow.java
    │   │   ├── ActorDirectory.java
    │   │   ├── DocumentRepository.java
    │   │   ├── DocumentEditService.java
    │   │   └── GrantAdministrationService.java
    │   └── resources/
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/
        └── AuthorizationConcurrencyTest.java
```

### 5.2. Gradle và dependency

**`settings.gradle`:**

```groovy
rootProject.name = 'transactional-authorization-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot tự cấu hình `DataSource` H2, `JdbcTemplate` và JDBC transaction manager khi các dependency cần thiết tồn tại. Với H2 embedded mặc định, Spring Boot có thể chạy `schema.sql` và `data.sql` khi khởi động. Production phải dùng database, driver và migration phù hợp.

### 5.3. Tạo schema và dữ liệu quyền động

**`src/main/resources/schema.sql`:**

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    owner_name VARCHAR(64) NOT NULL,
    body VARCHAR(500) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE document_grants (
    document_id BIGINT NOT NULL,
    grantee VARCHAR(64) NOT NULL,
    action VARCHAR(16) NOT NULL,
    PRIMARY KEY (document_id, grantee, action),
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX idx_document_grants_lookup
    ON document_grants (grantee, action, document_id);
```

**`src/main/resources/data.sql`:**

```sql
INSERT INTO documents (id, tenant_id, owner_name, body, version) VALUES
    (11, 'T1', 'alice', 'Draft', 1),
    (22, 'T2', 'carol', 'Other tenant', 1);

INSERT INTO document_grants (document_id, grantee, action) VALUES
    (11, 'bob', 'WRITE');
```

Trong demo, `alice` là owner của `Document#11`, `bob` được chia sẻ quyền `WRITE`, `carol` thuộc tenant `T2`. Lưu ý tên bảng `document_grants` và cấu trúc này **là policy riêng của demo**, không phải bốn bảng ACL chuẩn của module `spring-security-acl`.

Vì ID ở đây unique toàn DB, grant trỏ tới document bằng foreign key. Nếu ID chỉ unique trong từng tenant, khóa phải gồm tenant hoặc dùng identity globally unique và áp dụng tenant guard cả trong ACL/query.

### 5.4. Domain row nhận từ server

**`src/main/java/demo/DocumentRow.java`:**

```java
package demo;

public record DocumentRow(
        long id,
        String tenant,
        String owner,
        String body,
        long version) {
}
```

`DocumentRow` không được bind trực tiếp từ JSON client. Nó chỉ đại diện trạng thái **được repository đọc từ DB**. Trường `owner` và `tenant` phải là giá trị server tin cậy trong một transaction phù hợp.

### 5.5. Identity/tenant directory đáng tin

**`src/main/java/demo/ActorDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

record Actor(String username, String tenant) {
}

@Component
public class ActorDirectory {

    private final Map<String, Actor> actors = Map.of(
        "alice", new Actor("alice", "T1"),
        "bob", new Actor("bob", "T1"),
        "carol", new Actor("carol", "T2")
    );

    private final AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

    public Actor current() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || resolver.isAnonymous(authentication)) {
            throw new AccessDeniedException("No trusted principal");
        }

        Actor actor = actors.get(authentication.getName());

        if (actor == null) {
            throw new AccessDeniedException("No trusted tenant");
        }
        return actor;
    }
}
```

Directory cố định là **mô phỏng**. Với JWT/OIDC production, nên ánh xạ `issuer + subject` hoặc user ID nội bộ ổn định tới tenant membership và role đã xác minh. Không tự tin `X-Tenant` hay một `tenantId` từ body. Người dùng có thể thuộc nhiều tenant; lựa chọn tenant hiện tại phải được **kiểm tra membership**.

`AuthenticationTrustResolver` ngăn nhầm anonymous token đã có `isAuthenticated() == true` với user thật.

### 5.6. Repository: một khóa, hai đường thao tác

**`src/main/java/demo/DocumentRepository.java`:**

```java
package demo;

import java.util.List;
import java.util.NoSuchElementException;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private static final RowMapper<DocumentRow> MAPPER =
        (rs, rowNumber) -> new DocumentRow(
            rs.getLong("id"),
            rs.getString("tenant_id"),
            rs.getString("owner_name"),
            rs.getString("body"),
            rs.getLong("version")
        );

    private final JdbcTemplate jdbc;

    public DocumentRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public DocumentRow lockDocument(long id) {
        List<DocumentRow> rows = jdbc.query(
            """
            SELECT id, tenant_id, owner_name, body, version
            FROM documents
            WHERE id = ?
            FOR UPDATE
            """,
            MAPPER,
            id
        );

        if (rows.isEmpty()) {
            throw new NoSuchElementException("Document not found");
        }
        return rows.get(0);
    }

    public DocumentRow snapshot(long id) {
        List<DocumentRow> rows = jdbc.query(
            """
            SELECT id, tenant_id, owner_name, body, version
            FROM documents
            WHERE id = ?
            """,
            MAPPER,
            id
        );

        if (rows.isEmpty()) {
            throw new NoSuchElementException("Document not found");
        }
        return rows.get(0);
    }

    public boolean hasWriteGrant(long id, String grantee) {
        Integer n = jdbc.queryForObject(
            """
            SELECT COUNT(*)
            FROM document_grants
            WHERE document_id = ?
              AND grantee = ?
              AND action = 'WRITE'
            """,
            Integer.class,
            id,
            grantee
        );
        return n != null && n > 0;
    }

    public void changeBody(DocumentRow locked, String newBody) {
        int updated = jdbc.update(
            """
            UPDATE documents
            SET body = ?, version = version + 1
            WHERE id = ? AND tenant_id = ? AND version = ?
            """,
            newBody,
            locked.id(),
            locked.tenant(),
            locked.version()
        );

        if (updated != 1) {
            throw new OptimisticLockingFailureException(
                "Document changed concurrently");
        }
    }

    public int revokeWriteGrant(long id, String grantee) {
        return jdbc.update(
            """
            DELETE FROM document_grants
            WHERE document_id = ?
              AND grantee = ?
              AND action = 'WRITE'
            """,
            id,
            grantee
        );
    }
}
```

Hai điểm cốt lõi:

1. `lockDocument(id)` dùng **`SELECT ... FOR UPDATE`**, cần được gọi **bên trong transaction thực sự**. Nếu gọi ngoài transaction (auto-commit), khóa có thể được giải phóng ngay sau statement và không bảo vệ các bước tiếp theo.
2. `changeBody` có thêm `version` check để phát hiện thay đổi tài liệu ngoài dự kiến. Nhưng version của document **không tự phát hiện revoke grant**; lớp khóa + kiểm tra lại grant mới bảo vệ bài toán chính.

**Không xuất bản `snapshot` hoặc `lockDocument` như API đọc công khai không có authorization**. Chúng là thao tác repository nội bộ; service/endpoints phải bảo vệ cả quyền xem nội dung.

### 5.7. Service sửa: khóa -> đọc quyền -> quyết định -> ghi

**`src/main/java/demo/DocumentEditService.java`:**

```java
package demo;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentEditService {

    private final DocumentRepository documents;
    private final ActorDirectory actors;

    public DocumentEditService(
            DocumentRepository documents,
            ActorDirectory actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize("hasAuthority('document:write')")
    @Transactional
    public String changeBody(long id, String newBody) {

        Actor actor = actors.current();

        // FIRST: mọi writer/ACL revoker đều lock chính document row.
        DocumentRow locked = documents.lockDocument(id);

        if (!locked.tenant().equals(actor.tenant())) {
            throw new AccessDeniedException("Cross-tenant access");
        }

        boolean isOwner = locked.owner().equals(actor.username());
        boolean isGranted = documents.hasWriteGrant(
            id, actor.username()
        );

        if (!isOwner && !isGranted) {
            throw new AccessDeniedException("Write grant is missing");
        }

        if (newBody == null || newBody.isBlank()
                || newBody.length() > 500) {
            throw new IllegalArgumentException("Invalid body");
        }

        documents.changeBody(locked, newBody);
        return newBody;
    }
}
```

**Tại sao `hasWriteGrant` được gọi sau `lockDocument`?** Giả sử transaction thu hồi cũng luôn lock cùng document row trước khi xóa grant. Khi lượt sửa có được lock, grant và owner chỉ có thể được các writer tuân thủ cùng giao thức thay đổi **sau** khi lượt sửa kết thúc, hoặc đã thay đổi **trước** khi lượt sửa lấy lock. Không còn cửa sổ “revoke commit ở giữa check và UPDATE” giữa hai đường tuân thủ khóa này.

`@PreAuthorize` ở đây chỉ kiểm tra **authority tĩnh**. Nó có thể chạy ở một advisor trước transaction; vì thế **không dùng kết quả của nó làm kết luận cuối cho grant động**.

Exception `AccessDeniedException` là runtime exception; với Spring `@Transactional` mặc định, nó kích hoạt rollback. Nếu dùng exception checked cho denial, cần cấu hình rollback phù hợp.

### 5.8. Service thu hồi: giữ nguyên thứ tự lấy khóa

**`src/main/java/demo/GrantAdministrationService.java`:**

```java
package demo;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GrantAdministrationService {

    private final DocumentRepository documents;
    private final ActorDirectory actors;

    public GrantAdministrationService(
            DocumentRepository documents,
            ActorDirectory actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize("hasAuthority('grant:revoke')")
    @Transactional
    public int revokeWrite(long id, String grantee) {

        Actor actor = actors.current();

        // ALWAYS lock cùng hàng mà DocumentEditService sử dụng.
        DocumentRow locked = documents.lockDocument(id);

        if (!locked.tenant().equals(actor.tenant())
                || !locked.owner().equals(actor.username())) {
            throw new AccessDeniedException(
                "Only an authorized same-tenant owner may revoke");
        }

        if (grantee == null || grantee.isBlank()) {
            throw new IllegalArgumentException("Invalid grantee");
        }

        return documents.revokeWriteGrant(id, grantee);
    }
}
```

Trong demo, `alice` là owner `Document#11` và có authority `grant:revoke`. Cô ấy được thu hồi quyền của `bob`. User tenant khác hoặc một người chỉ có `document:write` không thể gọi phương thức này.

**Điểm buộc phải tuân thủ toàn hệ thống:** mọi endpoint, job, admin screen hay event consumer **chuyển owner/tenant, sửa trạng thái, thêm/xóa grant ảnh hưởng quyền ghi** đều phải dùng **cùng khóa điều phối** và thực hiện trong transaction. Nếu code có một đường `DELETE document_grants` chạy thẳng không lock document, ví dụ này không còn bảo đảm thứ tự mong muốn.

### 5.9. Ứng dụng Spring Boot và kết quả CLI

**`src/main/java/demo/TransactionAuthorizationApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class TransactionAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            TransactionAuthorizationApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demo(
            DocumentEditService editor,
            GrantAdministrationService grants,
            DocumentRepository documents) {

        return args -> {
            try {
                as("bob", "document:write");
                System.out.println("BOB_BEFORE_REVOKE: "
                    + editor.changeBody(11L, "Bob revision"));

                as("alice", "grant:revoke");
                System.out.println("GRANTS_REVOKED: "
                    + grants.revokeWrite(11L, "bob"));

                as("bob", "document:write");
                denied("BOB_AFTER_REVOKE",
                    () -> editor.changeBody(11L, "Stale revision"));

                as("alice", "document:write");
                System.out.println("ALICE_OWNER_EDIT: "
                    + editor.changeBody(11L, "Alice revision"));

                as("carol", "document:write");
                denied("CROSS_TENANT",
                    () -> editor.changeBody(11L, "Forbidden tenant"));

                DocumentRow finalRow = documents.snapshot(11L);
                System.out.println("FINAL_BODY: " + finalRow.body());
                System.out.println("FINAL_VERSION: "
                    + finalRow.version());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void as(String user, String authority) {
        var token = new UsernamePasswordAuthenticationToken(
            user,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(token);
        SecurityContextHolder.setContext(context);
    }

    private static void denied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException denied) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

`UsernamePasswordAuthenticationToken` ở đây được tự tạo với authorities để **mô phỏng test/CLI**, không phải cách xây dựng authentication cho user thật. Production phải xác minh token/session qua provider; không bao giờ tạo token tin cậy từ username/role do HTTP request tự khai. `SecurityContextHolder` được reset ở cuối demo để không giữ danh tính sang tác vụ khác.

Chạy trong thư mục dự án nếu đã có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên PowerShell:

```bash
.\gradlew.bat bootRun
```

Nếu chưa có wrapper, tạo wrapper bằng Gradle tương thích hoặc dùng `gradle bootRun` khi Gradle đã được cài. **Những dòng do chính chương trình in**, không tính log Spring/Gradle, được kỳ vọng là:

```text
BOB_BEFORE_REVOKE: Bob revision
GRANTS_REVOKED: 1
BOB_AFTER_REVOKE: DENIED
ALICE_OWNER_EDIT: Alice revision
CROSS_TENANT: DENIED
FINAL_BODY: Alice revision
FINAL_VERSION: 3
```

Phân tích:

- Trước khi thu hồi, `bob` có `document:write` **và** grant WRITE trên document 11, nên cập nhật `Draft` thành `Bob revision`; version tăng 1 -> 2.
- `alice` có authority `grant:revoke`, là owner cùng tenant. Thu hồi xóa đúng một grant của bob và commit.
- Khi `bob` thử ghi lần nữa, transaction mới lock document, đọc lại grant **đã bị xóa**, và ném `AccessDeniedException`. Không có UPDATE.
- `alice` là owner cùng tenant và có authority `document:write`, nên được cập nhật thành `Alice revision`; version 2 -> 3.
- `carol` thuộc T2 nên bị từ chối dù có authority `document:write`.
- Body cuối là `Alice revision`, version cuối là `3`.

**Kết quả trên được suy ra từ source code, không phải khẳng định đã chạy trong môi trường hiện tại.** Thứ tự đầu ra do `CommandLineRunner` thực hiện tuần tự; kiểm thử concurrency riêng nằm ở mục 6.

## 6. Integration tests: kiểm chứng cả nghiệp vụ và cạnh tranh

Dùng `@SpringBootTest`, `@WithMockUser` và `@DirtiesContext` để mỗi test có database H2 mới. Riêng concurrency test sử dụng hai thread và `TransactionTemplate` để **giữ khóa hàng bằng một transaction rõ ràng**, sau đó cho lượt sửa của `bob` cạnh tranh với revoke.

**`src/test/java/demo/AuthorizationConcurrencyTest.java`:**

```java
package demo;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
@ActiveProfiles("test")
@DirtiesContext(classMode =
    DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AuthorizationConcurrencyTest {

    @Autowired DocumentEditService editor;
    @Autowired GrantAdministrationService grants;
    @Autowired DocumentRepository documents;
    @Autowired PlatformTransactionManager txManager;

    @Test
    @WithMockUser(
        username = "bob",
        authorities = "document:write"
    )
    void validGrantAllowsEditing() {
        assertEquals(
            "Edited",
            editor.changeBody(11L, "Edited")
        );
        assertEquals("Edited", documents.snapshot(11L).body());
        assertEquals(2L, documents.snapshot(11L).version());
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "grant:revoke"
    )
    void ownerMayRevokeWriteGrant() {
        assertEquals(1, grants.revokeWrite(11L, "bob"));
        assertEquals(0, grants.revokeWrite(11L, "bob"));
        assertEquals("Draft", documents.snapshot(11L).body());
    }

    @Test
    @WithMockUser(
        username = "carol",
        authorities = "document:write"
    )
    void crossTenantUserCannotEditDocument() {
        assertThrows(
            AccessDeniedException.class,
            () -> editor.changeBody(11L, "Forbidden")
        );
        assertEquals("Draft", documents.snapshot(11L).body());
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = "document:read"
    )
    void missingFunctionalAuthorityIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> editor.changeBody(11L, "Forbidden")
        );
        assertEquals("Draft", documents.snapshot(11L).body());
    }

    @Test
    void revocationCommittedBeforeWriteLockCausesDenial()
            throws Exception {

        ExecutorService pool = Executors.newFixedThreadPool(2);

        CountDownLatch revokerLocked = new CountDownLatch(1);
        CountDownLatch releaseRevoker = new CountDownLatch(1);
        CountDownLatch writerStarted = new CountDownLatch(1);

        TransactionTemplate tx = new TransactionTemplate(txManager);

        try {
            Future<?> revoker = pool.submit(() ->
                asUser("alice", "grant:revoke", () -> {

                    // Một transaction quản trị đã lock document.
                    // Theo cùng lock order của GrantAdministrationService.
                    tx.executeWithoutResult(status -> {
                        documents.lockDocument(11L);
                        revokerLocked.countDown();
                        await(releaseRevoker);
                        documents.revokeWriteGrant(11L, "bob");
                    });
                    return null;
                })
            );

            assertTrue(
                revokerLocked.await(10, TimeUnit.SECONDS),
                "Revoker did not obtain document lock"
            );

            Future<String> writer = pool.submit(() ->
                asUser("bob", "document:write", () -> {
                    writerStarted.countDown();
                    return editor.changeBody(11L, "Stale update");
                })
            );

            assertTrue(
                writerStarted.await(10, TimeUnit.SECONDS),
                "Writer thread did not start"
            );

            // Revoke được commit khi thả transaction giữ khóa.
            // Writer chờ khóa hoặc bắt đầu sau commit: cả hai phải deny.
            releaseRevoker.countDown();
            revoker.get(10, TimeUnit.SECONDS);

            ExecutionException denied = assertThrows(
                ExecutionException.class,
                () -> writer.get(10, TimeUnit.SECONDS)
            );

            assertInstanceOf(
                AccessDeniedException.class,
                denied.getCause()
            );

            assertEquals("Draft", documents.snapshot(11L).body());
            assertEquals(1L, documents.snapshot(11L).version());

        } finally {
            releaseRevoker.countDown();
            pool.shutdownNow();
        }
    }

    private static <T> T asUser(
            String username,
            String authority,
            Supplier<T> operation) {

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();

        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                username,
                "demo-only",
                List.of(new SimpleGrantedAuthority(authority))
            )
        );

        SecurityContextHolder.setContext(context);

        try {
            return operation.get();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Timed out waiting for test latch");
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Interrupted while waiting", interrupted);
        }
    }
}
```

Chạy:

```bash
./gradlew test
```

### 6.1. Concurrency test đang chứng minh điều gì?

1. Thread **revoke** mở transaction, lock `documents.id=11` và giữ khóa.
2. Thread **writer** bắt đầu lời gọi `DocumentEditService.changeBody` qua Spring proxy.
3. Khi thả latch, thread revoke xóa grant của bob **trong transaction đang giữ khóa**, rồi commit.
4. Writer nếu chờ hàng sẽ lấy khóa sau commit; nếu chưa kịp vào lock thì cũng đọc grant sau commit. Trong cả hai lịch hợp lệ, `hasWriteGrant(11,"bob")` phải là `false` và UPDATE không diễn ra.
5. Test bắt `AccessDeniedException` phát sinh từ Future, đồng thời đọc lại body và version để chắc chắn **không có side effect trái phép**.

`CountDownLatch` tạo điểm đồng bộ có chủ đích; không dùng `Thread.sleep()` như một chứng minh thứ tự transaction. Test này mô tả được **revoke thắng thứ tự lấy khóa**; để chứng minh đối xứng, nên thêm kịch bản writer giữ lock trước và revoker chờ, rồi xác nhận writer commit trước khi revoke hoàn tất.

**Giới hạn:** test sử dụng H2, không trực tiếp chứng minh đúng behavior lock cho mọi database. Với production dùng PostgreSQL/MySQL, cần thêm integration tests bằng đúng DB hoặc Testcontainers và xác minh execution plan/lock timeout.

### 6.2. Tại sao không gắn `@Transactional` lên test method?

Nếu test method chính tự mở transaction rồi gọi repository trước khi tạo hai thread, test có thể giữ khóa/connection ngoài mong muốn. Ở ví dụ, transaction được quản lý **trong hai thread** qua Spring transactional service và `TransactionTemplate`, giúp kiểm tra thứ tự lock/commit thực hơn. `@DirtiesContext` làm mới in-memory DB giữa các test; không phụ thuộc thứ tự chạy.

### 6.3. Đừng coi chỉ có `403`/exception là đủ

Sau một lượt viết bị từ chối, **phải đọc lại DB**:

```text
body        = Draft
version     = 1
grant bob   = absent
```

Một API có thể trả `403` nhưng đã ghi dữ liệu trước khi exception. Nếu ghi ngoài transaction hoặc rollback rules sai, mã HTTP không chứng minh tính an toàn. Trong test này ta assert body/version không đổi, và có thể thêm assertion `documents.hasWriteGrant(11,"bob") == false` để xác minh revoke.

## 7. Những thiết kế cạnh tranh khác

### 7.1. Đặt quyền trong cùng hàng resource

Nếu policy chỉ là `ownerId`, `tenantId` và trạng thái, ta có thể khóa **chính hàng documents** rồi kiểm tra và ghi. Không cần thêm grant table.

Nhưng khi policy nằm trong một bảng khác (`acl_entry`, `document_grants`), cần chú ý không có bảo đảm tự nhiên rằng một transaction cập nhật grant sẽ xung đột với transaction update document. Khóa chung trên document là một **giao thức ứng dụng**, không phải foreign key tự sinh ra.

### 7.2. `@Lock(PESSIMISTIC_WRITE)` với Spring Data JPA

Mẫu tương đương khi dùng JPA:

```java
public interface DocumentJpaRepository
        extends JpaRepository<DocumentEntity, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select d from DocumentEntity d where d.id = :id")
    Optional<DocumentEntity> lockById(@Param("id") Long id);
}
```

Đây là mảnh code **minh họa**, cần `jakarta.persistence.LockModeType`, Spring Data JPA imports, entity và bean repository. JPA/Hibernate có thể sinh SQL khóa tương ứng tùy DB dialect.

Ở service `@Transactional`, cả `editDocument` và `revokeGrant` phải gọi `lockById(id)` **trước khi** kiểm tra/cập nhật owner/ACL. Nếu revoke chỉ `grantRepository.deleteBy...` mà không lock document, `@Lock` ở writer **không bảo vệ được quyền**.

### 7.3. `@Version` không tự theo dõi ACL

```java
@Entity
class DocumentEntity {
    @Id Long id;

    @Version
    long version;
}
```

Đây là mảnh code, chưa có đầy đủ entity mapping. Optimistic locking phát hiện writer khác làm thay đổi document version, nhưng **không tự nhận biết** một `DELETE` trong bảng grant/ACL khác. Nếu nghiệp vụ cần quyền thay đổi làm mọi in-flight update bị invalidated, hãy có `authzVersion` liên kết; mọi đường đổi policy phải tăng version đó **cùng transaction**. Writer phải kiểm tra nó tại thời điểm ghi.

### 7.4. `SERIALIZABLE` và retry

`SERIALIZABLE` cung cấp mô hình serial order trong phạm vi transaction của DB; có thể dẫn đến serialization failure/deadlock. Khi retry:

1. Bắt đúng lỗi concurrency có thể retry.
2. Tạo **transaction mới**.
3. Đọc **identity/policy/ACL mới**.
4. Kiểm tra quyền lại hoàn toàn.
5. Chỉ ghi sau khi có quyết định hợp lệ.
6. Giới hạn số lần retry/backoff; tránh retry tự động cho side effect không idempotent.

**Không retry bằng cách dùng lại biến `wasAllowed = true` hoặc đối tượng ACL đã load từ transaction cũ.** Nếu quyền đã bị thu hồi, retry phải trả deny.

### 7.5. Dữ liệu quyền ở DB hoặc service khác

Nếu grant được lưu ở một permission service ngoài database của document, `@Transactional` trên document DB **không thể tự khóa và commit atomic** với permission service. Cần chọn mô hình consistency rõ ràng:

- Quyền cực nhạy cảm: đặt policy quyết định ghi gần resource DB hoặc dùng một authoritative transaction/lock.
- Quyền do remote PDP quyết định: cân nhắc decision token/version có hiệu lực ngắn, revalidation tại commit, hoặc API thực hiện **atomic authorize-and-write** tại cùng authority.
- Thu hồi cross-service: dùng event/outbox/saga, có latency propagation, và quy định khi nào revoke được xem là có hiệu lực.
- Nếu quyền phụ thuộc vào JWT sống lâu, local token authority có thể vẫn đúng chữ ký nhưng đã lỗi thời; cần version/revocation semantics cho những quyền phải thu hồi ngay.

Không nên quảng cáo “revoke có hiệu lực tức thời toàn hệ thống” chỉ dựa trên sự kiện publish vào queue; cần chứng minh latency/consistency thực.

## 8. Deadlock, lock order và hiệu năng

### 8.1. Chọn một thứ tự lấy khóa toàn hệ thống

Nếu cập nhật nhiều tài liệu, transaction A lock `Document#11` rồi `Document#22`, còn transaction B lock `#22` rồi `#11`, dễ dẫn tới deadlock.

Quy ước:

```text
1. Chuẩn hóa và sort document IDs tăng dần.
2. Lock từng document theo thứ tự đã sort.
3. Sau đó lock/cập nhật grant/ACL rows theo thứ tự đã định.
4. Kiểm tra quyền trên mọi object cần ghi.
5. Thực hiện thay đổi hoặc rollback toàn bộ.
```

Đừng dùng khóa JVM như `synchronized` hoặc `ReentrantLock` để thay khóa DB trong hệ thống đa instance: các node khác không chia sẻ khóa đó. Row lock/transaction phải thuộc nguồn dữ liệu authoritative.

### 8.2. Giữ transaction ngắn

Trong khi giữ row lock, tránh:

- Gọi HTTP service chậm không có timeout.
- Chờ phản hồi người dùng.
- Chạy job ML hoặc xử lý file lớn.
- Gửi email trực tiếp trước commit.
- Tạo nhiều truy vấn N+1 cho ACL từng item.

Một cách thường dùng là chuẩn bị dữ liệu/validate có thể làm ngoài transaction, sau đó mở transaction ngắn để **lock -> recheck -> mutate -> commit**. Nếu có event/email, ghi outbox trong cùng transaction rồi publish sau commit.

### 8.3. Lock timeout và deadlock cần xử lý đúng

Tùy DB có thể xảy ra:

- Lock wait timeout.
- Deadlock detection.
- Optimistic locking failure.
- Serialization failure.
- Transaction rollback do network/connection.

Đừng bắt mọi exception rồi `return true` hoặc âm thầm ghi không kiểm tra. Phân biệt lỗi từ chối quyền, xung đột concurrency và lỗi hạ tầng; thông thường 403/404 policy, 409 conflict hoặc 5xx tùy API contract. **Không lộ thông tin về tài liệu/tenant mà caller không được phép xem** qua error messages.

### 8.4. Benchmark những chỉ số nào?

| Chỉ số | Vì sao cần |
| --- | --- |
| p50/p95/p99 latency của write | Lock wait có thể làm p99 tăng |
| Lock wait / deadlocks / timeouts | Phát hiện giao thức khóa kém |
| Rows scanned / SQL query count | Tìm ACL lookup N+1 |
| Permission checks sau lock | Bảo đảm đang recheck thật |
| Ratio granted vs denied | Theo dõi thay đổi hành vi policy |
| Stale cache-hit / revocation lag | Đánh giá quyền đã thu hồi |
| Transaction duration | Tránh giữ lock lâu |
| Retry count / serialization failures | Phát hiện contention |

Đo cả **độ đúng** lẫn hiệu năng. Tối ưu bỏ mất recheck quyền không phải cải tiến.

## 9. ACL, `PermissionEvaluator` và quyền động trong transaction

Nếu hệ thống dùng Spring Security ACL thật:

```text
@PreAuthorize hasPermission(#id, 'Document', 'WRITE')
        |
        v
AclPermissionEvaluator
        |
        v
AclService / ACL cache -> Acl.isGranted(...)
```

Kết quả có thể được tính **trước** transaction ghi hoặc theo snapshot/cache mà ứng dụng đang dùng. Vì vậy, với write nhạy cảm:

- Dùng `@PreAuthorize` để chặn sớm và giảm tải, nhưng **không coi đó là kiểm tra cuối**.
- Lock authoritative resource/policy theo giao thức mà code grant/revoke cũng tuân thủ.
- Kiểm tra **lại** ACL/owner/tenant/status sau lock; nếu cache ACL có thể stale, cần dùng API đọc authoritative hoặc invalidation/version phù hợp.
- Sau `MutableAclService.updateAcl`, xác định transaction commit và cache invalidation đúng thứ tự; trong cluster cần propagate.
- Nếu ACL cha/nhóm/quyền role thay đổi, chỉ lock document chưa chắc đủ. Phải định nghĩa lock/version cho **mọi nguồn policy ảnh hưởng** đến quyết định, hoặc chấp nhận contract consistency yếu hơn và ghi rõ.

**Không dùng `@PostAuthorize` để “rollback” một lệnh ghi đã commit**. Nếu muốn một transaction bao gồm authorization và mutation, bảo đảm logic authorization thật sự chạy trong transaction/lock đúng ranh giới, không chỉ gắn annotation rồi giả định thứ tự advice.

### `PermissionEvaluator` không tự là transaction manager

`PermissionEvaluator.hasPermission(authentication, object, permission)` có thể đọc ACL nhưng không có contract “lock mọi data source” hoặc “recheck trước khi commit”. Một custom evaluator có thể nhận service/DAO khác, song cần tránh gọi DB theo từng object gây N+1, tránh cache quyền cross-user và tránh phụ thuộc transaction không cùng datasource.

## 10. Ownership transfer và tenant migration phải tuân thủ giao thức tương tự

Revoke không phải dạng thay quyền duy nhất. Ví dụ:

1. Alice đang sở hữu document 11.
2. Admin chuyển `owner_id` sang Bob.
3. Alice đang có request edit đã pass owner check.
4. Alice tiếp tục ghi theo owner cũ.

Nếu transfer cập nhật owner **không lock cùng hàng** hoặc edit không recheck owner sau lock, sẽ có TOCTOU.

Một service chuyển owner nên:

```text
BEGIN
  lock document #11
  authenticate + authorize actor được phép transfer
  kiểm tra owner/tenant/state hiện tại
  xác thực owner mới và tenant membership
  cập nhật owner_id, grant/ACL liên quan và policy version
  ghi audit/outbox
COMMIT
```

Chuyển `tenant_id` thậm chí nhạy cảm hơn vì là ranh giới dữ liệu. Có thể phải di chuyển file storage, cache, ACL SID, encryption key và tài nguyên liên quan; không chỉ thay một column. Mỗi workflow phải có cơ chế nhất quán tương ứng, không được dùng generic `updateEntity` nhận `ownerId`/`tenantId` từ client.

## 11. Bảng quyết định chọn giải pháp

| Yêu cầu | Biện pháp chính | Điều kiện và lưu ý |
| --- | --- | --- |
| Chỉ owner được sửa, policy ở cùng một hàng | Conditional UPDATE theo owner/tenant/version | Bind identity từ server, kiểm tra affected rows |
| Grant ở bảng riêng, revoke cần có thứ tự rõ | Lock chung resource row ở edit/revoke | Mọi đường thay grant tuân thủ khóa |
| Ít contention, nhiều writer cùng entity | `@Version`/optimistic locking | ACL change phải tăng authz version nếu cần phát hiện |
| Nhiều resource trong một transaction | Sort IDs và lock theo thứ tự chuẩn | Tránh deadlock, all-or-nothing policy |
| Policy phức tạp cần SERIALIZABLE | Transaction serializable + retry | Retry transaction và authorization từ đầu |
| ACL cache nhiều node | Cache invalidation/versioning | Không tuyên bố revoke tức thời nếu propagation chậm |
| Quyền ở service ngoài DB | Contract consistency và authoritative check | Không có atomicity chỉ nhờ `@Transactional` cục bộ |
| Cần loại bỏ writer đã bắt đầu trước revoke | Protocol mạnh hơn (epoch/barrier/cancel) | Row lock đơn thuần cho phép writer thắng khóa trước revoke |

### Quyền bị thu hồi “ngay lập tức” nghĩa là gì?

Có ba yêu cầu khác nhau:

1. **Không chấp nhận thao tác bắt đầu sau khi revoke commit.**
2. **Không cho phép commit của thao tác đã được authorize trước revoke nhưng commit sau revoke.**
3. **Hủy mọi công việc đang chạy ngay khi người quản trị bấm revoke, kể cả đã có lock hoặc gọi external service.**

Giao thức khóa ở ví dụ đáp ứng một **thứ tự tuần tự theo lock acquisition**: khi writer lấy lock trước revoke, writer có thể commit trước revoke; khi revoke lấy lock trước, writer bị từ chối sau commit revoke. Nó **không** tự thực hiện yêu cầu thứ ba.

Nếu cần cutoff tuyệt đối cho mọi tác vụ nền, phải thiết kế **revocation epoch**, cancellation protocol, giao thức barrier hoặc một authoritative executor/queue bảo đảm thứ tự xử lý. Cần mô tả và test đặc tính đó như một phần của business security contract.

## 12. Những lỗi thường gặp

| Sai lầm | Tác động | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm tra grant trong `@PreAuthorize` | Quyền có thể bị thu hồi trước UPDATE | Recheck grant trong transaction sau lock |
| Có `@Transactional` nên tưởng grant bất biến | DB khác có thể sửa ACL/grant | Chọn lock/version/serialization phù hợp |
| Writer lock document, revoker chỉ xóa grant | Giao thức khóa bị bypass | Cả hai phải lock cùng resource |
| `SELECT FOR UPDATE` ngoài transaction | Khóa có thể giải phóng ngay | Đặt lock trong `@Transactional` thật |
| `@Version` chỉ trên document | Không phát hiện đổi grant riêng | Kết nối policy version với revoke |
| `REPEATABLE_READ` được coi là dữ liệu mới nhất | Snapshot có thể stale | Xác định DB semantics + lock/version |
| Retry sau conflict nhưng giữ `allowed=true` | Cấp quyền theo snapshot cũ | Retry check từ đầu trong transaction mới |
| Chạy `this.edit(...)` từ cùng bean | Bypass Spring proxy advice | Tách secured bean, kiểm thử hành vi |
| Dùng `@PostAuthorize` cho lệnh chuyển tiền | Side effect có thể đã commit | Authorization trước write và DB guard |
| Tin `tenantId` từ JSON/header | Bypass tenant isolation | Tenant từ identity/directory đã xác minh |
| Cache quyết định chỉ theo documentId | Lộ quyền giữa user/tenant | Key theo principal/tenant/action/version |
| Revoke ở một node, cache node khác chưa xóa | Quyền cũ tiếp tục có hiệu lực | Invalidation distributed, policy version |
| Lock nhiều document không có thứ tự | Deadlock | Sort IDs và lock order chuẩn |
| Giữ lock khi gọi API bên ngoài | Lock wait kéo dài | Transaction ngắn, outbox |
| Bắt exception rồi `return true` | Fail-open | Fail closed, quan sát lỗi hạ tầng |
| Test chỉ assert `403` | Có thể đã UPDATE trước exception | Readback body/version và grants |
| Dùng H2 test thay cho DB production | Semantics lock/isolation có thể khác | Testcontainers/integration trên DB đích |
| User có role đúng nhưng không sở hữu tài liệu | Broken object-level authorization | Authority AND owner/tenant/grant |
| Deny sau write bằng filter/audit | Không thay đổi được side effect | Chặn tại transaction boundary |

## 13. Bài tập tự kiểm tra

1. **TOCTOU trong authorization nghĩa là gì?**  
   Quyền được kiểm tra ở thời điểm T1 nhưng dữ liệu quyền thay đổi trước khi thao tác ở T2.

2. **`@PreAuthorize` có tự khóa bảng ACL không?**  
   Không; nó quyết định cho phép gọi method, không là DB lock.

3. **`@Transactional` mặc định dùng isolation nào?**  
   `Isolation.DEFAULT` của transaction manager/DB, không mặc nhiên là `SERIALIZABLE`.

4. **Vì sao `READ_COMMITTED` vẫn có thể tạo TOCTOU?**  
   Grant có thể thay đổi giữa hai statement trong cùng transaction nếu không có lock/giao thức tương ứng.

5. **Nếu revoker commit rồi writer mới lấy document lock, writer phải làm gì?**  
   Đọc lại grant/owner/tenant và từ chối nếu quyền đã mất.

6. **Nếu writer lấy document lock trước, rồi revoker chờ, writer có thể commit không?**  
   Có, nếu grant vẫn hợp lệ và policy cho phép thứ tự writer-trước-revoke. Revoke commit sau khi writer nhả lock.

7. **Vì sao `@Version` của Document không phát hiện grant bị xóa?**  
   Vì grant là bảng/entity khác; Document.version không tự đổi.

8. **Một SQL `UPDATE ... WHERE EXISTS grant` có bảo đảm mọi semantics revoke real-time không?**  
   Không tự động; cần xét isolation/snapshot/locking và transaction cạnh tranh của DB.

9. **Khi retry serialization failure, có được dùng `wasAllowed=true` của lượt trước không?**  
   Không. Phải lấy dữ liệu quyền mới và kiểm tra lại trong transaction mới.

10. **Đổi owner có cần dùng cùng lock protocol không?**  
    Có, nếu ownership ảnh hưởng quyền writer theo contract của ứng dụng.

11. **Một role `document:write` có đủ sửa tài liệu T2 của user T1 không?**  
    Không. Còn phải kiểm tra tenant và quyền object theo dữ liệu server.

12. **Làm sao test concurrency đáng tin hơn `Thread.sleep()`?**  
    Dùng latch/barrier, transaction/row lock thực và assert trạng thái DB sau commit.

13. **Nếu lock xảy ra trên nhiều object, giảm deadlock bằng cách nào?**  
    Quy định thứ tự lock (ví dụ ID tăng dần) và giữ transaction ngắn.

14. **`@PostAuthorize` có thể đảm bảo lệnh ghi bị rollback nếu user không có quyền không?**  
    Không nên dựa vào nó. Hậu kiểm có thể xảy ra sau side effect/commit tùy advisor ordering.

15. **Nếu ACL nằm ở dịch vụ ngoài DB, `@Transactional` cục bộ có khóa được ACL không?**  
    Không. Cần consistency protocol/authoritative service rõ ràng.

## 14. Tài liệu chính thức và ghi nhớ

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, advisor/proxy, lưu ý `@PostAuthorize` với write.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, isolation, rollback, proxy/self-invocation.
- [Spring Framework — Transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW` và khác biệt transaction scope.
- [Spring Framework — Programmatic transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` cho test/workflow.
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html): `@Lock(PESSIMISTIC_WRITE)` và queries.
- [Spring Boot — SQL databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `JdbcTemplate`, datasource, script initialization, transaction manager.
- [PostgreSQL — Explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, `FOR UPDATE`, xung đột writer và giải phóng khóa khi transaction kết thúc.
- [PostgreSQL — Transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html): đặc tính isolation và serialization failure.
- [Spring Security — ACL authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACE, permission evaluator, owner, cache và ACL service.

**Tóm tắt:** quyền trên dữ liệu là dữ liệu **động**. `@PreAuthorize` hữu ích để chặn sớm, nhưng với thao tác ghi cần kiểm tra lại **owner, tenant, grant, ACL và trạng thái** trong một giao thức nhất quán với việc thay đổi quyền. Một lựa chọn rõ ràng là **cả writer lẫn revoker lock cùng document row, đọc/kiểm tra quyền sau lock rồi ghi trước commit**. Với hệ thống khác cần conditional SQL, authz version, isolation/retry hoặc protocol liên dịch vụ. Luôn test cả hai thứ tự commit, rollback, cache invalidation và dữ liệu sau khi bị từ chối.