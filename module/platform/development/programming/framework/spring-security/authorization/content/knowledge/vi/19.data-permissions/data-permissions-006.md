# Cập nhật, xóa hàng loạt và tính nguyên tử khi có phần tử thiếu quyền

> **Phạm vi:** Spring Security – authorization → **Quyền trên dữ liệu**. Trọng tâm là một yêu cầu UPDATE/DELETE nhiều tài nguyên, trong đó **chỉ một phần tử thiếu quyền hoặc không tồn tại**. Bài giải thích hợp đồng all-or-nothing, khác biệt với best-effort, cách kết hợp Spring Method Security với `@Transactional`, khóa/phiên bản dữ liệu, và kiểm thử tính nguyên tử. Ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring Data JPA với H2 test.

## 1. Bài toán: một ID trái quyền làm cả batch thất bại

Client yêu cầu:

~~~json
{
  "ids": [101, 102, 202],
  "newTitle": "Reviewed"
}
~~~

Trong database:

| ID | Tenant | Chủ sở hữu | Alice có quyền UPDATE? |
| --- | --- | --- | --- |
| 101 | acme | alice | Có |
| 102 | acme | alice | Có |
| 202 | acme | bob | **Không** |

Nếu thao tác cứ cập nhật 101, 102 rồi bỏ qua 202, kết quả không còn đúng với yêu cầu “cập nhật **toàn bộ** danh sách”. Nghiêm trọng hơn, nếu mỗi bản ghi đã commit riêng, lỗi ở 202 **không thể rollback** hai bản ghi trước đó.

Chốt chính của bài:

> **All-or-nothing:** Một phần tử không tồn tại, không cùng tenant, không đạt permission hoặc xảy ra lỗi trong quá trình xử lý ⇒ **toàn bộ yêu cầu bị từ chối hoặc rollback; không có cập nhật/xóa một phần nào được commit**.

Để đảm bảo điều đó, cần đồng thời:
1. **Kiểm tra quyền của tất cả phần tử**, không chỉ một phần tử hoặc một role chung.
2. **Đảm bảo đủ các ID được yêu cầu**, kể cả trường hợp database bỏ qua ID không tồn tại khi dùng `WHERE id IN (...)`.
3. **Chỉ thay đổi dữ liệu sau khi mọi kiểm tra hợp lệ** (hoặc dùng conditional SQL + kiểm tra row count và rollback).
4. **Một transaction bao toàn batch**, có quy tắc rollback phù hợp.
5. **Đảm bảo quyền không đổi giữa check và write** bằng lock/version/SQL predicate phù hợp.
6. **Trả response thành công sau commit**; không gửi event thành công trước khi transaction commit.

Một transaction không biết owner/tenant của caller có hợp lệ không; một annotation kiểm tra quyền cũng không tự rollback nhiều giao dịch đã commit. Phải thiết kế cả authorization lẫn atomicity.

## 2. Hai hợp đồng khác nhau: all-or-nothing và best-effort

| Thuộc tính | All-or-nothing | Best-effort / partial success |
| --- | --- | --- |
| Một phần tử thiếu quyền | Reject cả batch | Có thể xử lý các phần tử khác |
| Một phần tử không tồn tại | Reject cả batch (theo hợp đồng mẫu) | Có thể trả NOT_FOUND riêng item |
| Dữ liệu đã commit khi batch fail | Không | Có thể có |
| Kiểm tra quyền | Tất cả phải đạt | Chọn các item được phép |
| Transaction | Thường một transaction chung | Một transaction cho item/chunk hoặc workflow có trạng thái |
| Response | Thành công toàn bộ hoặc thất bại toàn bộ | Danh sách kết quả từng item |
| Use case | Duyệt toàn bộ, nhóm thay đổi cần nhất quán, xóa tập liên quan | Import, đồng bộ nền, dọn dữ liệu chấp nhận lỗi cục bộ |

Một kết quả all-or-nothing cho batch có ID của Bob:

~~~text
PATCH /api/documents/bulk-title
Alice requests [101, 102, 202]
→ HTTP 403 theo hợp đồng ví dụ (caller đã xác thực)
→ Document#101: unchanged
→ Document#102: unchanged
→ Document#202: unchanged
~~~

Một best-effort API **được thiết kế rõ** có thể trả:

~~~json
{
  "status": "PARTIAL",
  "results": [
    {"id": 101, "status": "UPDATED"},
    {"id": 102, "status": "UPDATED"},
    {"id": 202, "status": "DENIED"}
  ]
}
~~~

Không dùng `continue`, `@PreFilter` hoặc `filter(...)` để vô tình biến all-or-nothing thành partial success mà không đổi hợp đồng API. Bài này chỉ triển khai **all-or-nothing**.

## 3. Luồng chuẩn: validate → load/lock → authorize all → mutate → commit

~~~text
Request IDs
   |
   v
Validate: không null/rỗng, ID dương,
không trùng, không vượt kích thước batch
   |
   v
BEGIN TRANSACTION
   |
   v
Tải tất cả records theo IDs
(có khóa hoặc kiểm soát version phù hợp)
   |
   v
Đủ đúng số ID được yêu cầu?
   +-- NO  → DENY → ROLLBACK
   |
   v
MỌI record thuộc tenant + owner hợp lệ?
   +-- NO  → DENY → ROLLBACK
   |
   v
MỌI record đúng trạng thái + authority/ACL?
   +-- NO  → DENY → ROLLBACK
   |
   v
Update/Delete ALL trong cùng transaction
   |
   v
Flush / constraints / optimistic checks
   +-- FAIL → ROLLBACK
   |
   v
COMMIT → SUCCESS
~~~

Từng bước có mục đích khác nhau:

- **Normalize IDs:** kiểm tra duplicate trước vì SQL `IN (101, 101, 202)` có thể trả chỉ hai row.
- **Load đúng tập:** `findAllById` hoặc `WHERE id IN (...)` thường trả subset nếu thiếu ID, nên không được im lặng.
- **Authorization ở dữ liệu tin cậy:** không tin `owner`/`tenantId` client gửi trong JSON.
- **Quyền trên từng object:** có role `DOC_EDITOR` không nhất thiết đồng nghĩa có quyền với mọi tài liệu.
- **Fail closed:** nếu không thể xác minh bất kỳ item nào, không cấp quyền cho toàn batch.
- **Commit ở cuối:** `flush()` không phải `commit()`, transaction vẫn có thể rollback.

## 4. Spring Security và Spring Transaction có nhiệm vụ khác nhau

| Cơ chế | Bảo vệ cái gì? | Không tự bảo vệ |
| --- | --- | --- |
| `@PreAuthorize("isAuthenticated()")` | Caller đã đăng nhập trước khi vào method | Owner/tenant từng record |
| `@PreAuthorize("@policy.canEditAll(authentication,#ids)")` | Có thể kiểm tra tập IDs trước method | Transaction/TOCTOU nếu policy kiểm tra ngoài transaction |
| `@Transactional` | Atomic commit/rollback trong database transaction | Người dùng có quyền với record không |
| `@Lock(PESSIMISTIC_WRITE)` | Giảm khả năng row bị writer khác đổi trong lúc check/write | Nguồn quyền ngoài bảng bị khóa, hệ thống khác |
| `@Version` | Phát hiện cập nhật cạnh tranh ở entity lifecycle | Bulk JPQL DML có thể bypass version |
| Conditional update/delete SQL | Đặt owner/tenant/state vào điều kiện ghi | Các policy không thể diễn đạt bằng WHERE nếu không bổ sung |

Spring Method Security kích hoạt bởi `@EnableMethodSecurity`. `@PreAuthorize` được áp dụng ở bean proxy; với self-invocation, code khởi tạo bằng `new` hoặc method private/final không được proxy đúng, chốt quyền có thể không chạy.

**Điểm then chốt:** `@PostAuthorize` kiểm tra sau khi thân method hoàn tất; không dùng làm chốt duy nhất cho thao tác ghi, xóa, gửi email hay chuyển tiền. `@PostFilter` chỉ lọc tập trả về; `@PreFilter` có thể lọc input, nhưng điều đó tương đương xử lý subset chứ không chứng minh tất cả hợp lệ.

## 5. Ví dụ Java 17+ / Spring Boot 3.x / JPA / H2

Ta dùng chính sách dễ kiểm chứng: một người chỉ được cập nhật hoặc xóa tài liệu thuộc **đúng tenant** và có `ownerId` bằng danh tính đã xác thực. Demo có các principal:

| Người dùng | Tenant |
| --- | --- |
| alice | acme |
| bob | acme |
| eve | globex |

Production có thể thay bằng chính sách gồm authority/ACL, trạng thái khóa, soft delete hoặc retention. Mục tiêu ví dụ là thiết kế một **transaction toàn bộ** và test từ chối khi có một ID ngoài quyền.

### 5.1. Dependencies

Trong `build.gradle` của một dự án Spring Boot 3.x đã cấu hình plugin Java/Boot/dependency-management tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-security` không tự bật Method Security. Vì bài demo chỉ gọi service từ JUnit, không bắt buộc dùng `spring-boot-starter-web`.

### 5.2. Cấu hình database test

**`src/test/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:h2:mem:batch_security;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

H2 phù hợp integration test chức năng cơ bản; các thuộc tính `create-drop` và in-memory **không dùng cho production**. Với PostgreSQL/MySQL/Oracle/SQL Server, kiểm tra transaction isolation và locking trên chính database dự định triển khai.

### 5.3. Application

**`src/main/java/demo/batch/BatchAuthorizationApplication.java`**

~~~java
package demo.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class BatchAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(BatchAuthorizationApplication.class, args);
    }
}
~~~

### 5.4. Entity có version

**`src/main/java/demo/batch/DocumentEntity.java`**

~~~java
package demo.batch;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "documents")
public class DocumentEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String tenantId;

    @Column(nullable = false, length = 64)
    private String ownerId;

    @Column(nullable = false, length = 160)
    private String title;

    @Version
    private Long version;

    protected DocumentEntity() {
    }

    public DocumentEntity(String tenantId, String ownerId, String title) {
        this.tenantId = tenantId;
        this.ownerId = ownerId;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public String getTitle() {
        return title;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

`@Version` phục vụ optimistic locking khi Hibernate quản lý entity updates/deletes. Nó không tự bảo vệ mọi câu JPQL bulk update/delete; nếu chọn bulk DML, phải tự thiết kế version predicate và điều kiện update phù hợp.

### 5.5. Repository khóa các rows trong transaction

**`src/main/java/demo/batch/DocumentRepository.java`**

~~~java
package demo.batch;

import java.util.Collection;
import java.util.List;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository extends JpaRepository<DocumentEntity, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select d from DocumentEntity d where d.id in :ids")
    List<DocumentEntity> lockAllByIds(
            @Param("ids") Collection<Long> ids);
}
~~~

`@Lock(PESSIMISTIC_WRITE)` yêu cầu JPA/database giữ write lock thích hợp đối với các row được đọc trong transaction. Khi kiểm tra owner xong, writer khác khó thay row trước khi method hiện tại commit. Tuy nhiên locking behavior khác nhau giữa database; khóa không tự giải quyết thay đổi của bảng ACL/membership khác nếu những bảng đó không cùng được kiểm soát.

### 5.6. Actor và tenant từ Authentication đáng tin

**`src/main/java/demo/batch/ActorDirectory.java`**

~~~java
package demo.batch;

import java.util.Map;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class ActorDirectory {
    public record Actor(String userId, String tenantId) {
    }

    // Chỉ dùng cho test/demo; không phải một hệ thống IAM thật.
    private static final Map<String, Actor> USERS = Map.of(
            "alice", new Actor("alice", "acme"),
            "bob", new Actor("bob", "acme"),
            "eve", new Actor("eve", "globex"));

    public Actor current() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException("Batch not permitted");
        }

        Actor actor = USERS.get(authentication.getName());
        if (actor == null) {
            throw new AccessDeniedException("Batch not permitted");
        }
        return actor;
    }
}
~~~

Map trên minh họa một **server-side trusted directory** phục vụ `@WithMockUser`; production phải lấy ID/tenant từ verified principal, JWT claims được xác minh chữ ký hoặc identity service. Không dùng tenant/owner do client tự gửi; tránh dùng username có thể trùng giữa tenant làm định danh vĩnh viễn.

### 5.7. Service all-or-nothing

**`src/main/java/demo/batch/BulkDocumentService.java`**

~~~java
package demo.batch;

import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BulkDocumentService {
    private static final int MAX_BATCH = 100;

    private final DocumentRepository repository;
    private final ActorDirectory actors;

    public BulkDocumentService(
            DocumentRepository repository,
            ActorDirectory actors) {
        this.repository = repository;
        this.actors = actors;
    }

    @Transactional
    @PreAuthorize("isAuthenticated()")
    public void renameAll(List<Long> requestedIds, String title) {
        List<Long> ids = validateIds(requestedIds);

        if (title == null || title.isBlank() || title.length() > 160) {
            throw new IllegalArgumentException("Invalid title");
        }

        ActorDirectory.Actor actor = actors.current();
        List<DocumentEntity> selected = authorizeAll(ids, actor);

        // MỌI phần tử đều được phép mới bắt đầu sửa.
        for (DocumentEntity document : selected) {
            document.rename(title);
        }
        repository.flush();
    }

    @Transactional
    @PreAuthorize("isAuthenticated()")
    public void deleteAll(List<Long> requestedIds) {
        List<Long> ids = validateIds(requestedIds);
        ActorDirectory.Actor actor = actors.current();
        List<DocumentEntity> selected = authorizeAll(ids, actor);

        // Xóa entities đã kiểm tra; không delete blind theo IDs.
        repository.deleteAll(selected);
        repository.flush();
    }

    private List<Long> validateIds(List<Long> input) {
        if (input == null || input.isEmpty() || input.size() > MAX_BATCH) {
            throw new IllegalArgumentException("Invalid batch");
        }
        if (input.stream().anyMatch(Objects::isNull)
                || input.stream().anyMatch(id -> id <= 0)) {
            throw new IllegalArgumentException("Invalid ids");
        }
        if (new HashSet<>(input).size() != input.size()) {
            throw new IllegalArgumentException("Duplicate ids");
        }
        return List.copyOf(input);
    }

    private List<DocumentEntity> authorizeAll(
            List<Long> ids,
            ActorDirectory.Actor actor) {

        List<DocumentEntity> selected = repository.lockAllByIds(ids);

        // IN (...) trả subset khi có ID không tồn tại.
        if (selected.size() != ids.size()) {
            throw new AccessDeniedException("Batch not permitted");
        }

        for (DocumentEntity doc : selected) {
            if (!doc.getTenantId().equals(actor.tenantId())
                    || !doc.getOwnerId().equals(actor.userId())) {
                throw new AccessDeniedException("Batch not permitted");
            }
        }
        return selected;
    }
}
~~~

**Giải thích từng chốt:**

1. `@PreAuthorize("isAuthenticated()")` bảo vệ service boundary, sau đó `ActorDirectory` bảo đảm actor được server nhận diện.
2. `@Transactional` trên **public method được gọi qua Spring proxy** mở một transaction bao toàn bộ đọc/quyền/ghi.
3. `validateIds` reject null, rỗng, số âm/0, duplicate, danh sách trên 100. Nếu duplicate tồn tại, số row từ `WHERE IN` không thể so trực tiếp với kích thước list để kết luận đủ tập.
4. `lockAllByIds` tải các rows và yêu cầu lock khi được DB hỗ trợ. Không dùng thứ tự list kết quả để quyết định quyền; tất cả rows phải được xét.
5. Nếu thiếu row, trả `AccessDeniedException` chung; hạn chế tiết lộ ID nào thuộc người khác hay chưa tồn tại.
6. Nếu một row khác owner/tenant, throw **trước** vòng mutate. Không dùng `continue` hoặc filter silently.
7. `renameAll` sửa các entity managed; JPA dirty checking áp dụng trong transaction khi flush/commit.
8. `deleteAll` xóa những entity đã được xét, giữ JPA entity lifecycle (so với delete bulk có nhiều khác biệt).
9. `flush()` giúp phát hiện constraint/lỗi SQL trước khi rời method, nhưng **chưa commit**. Transaction interceptor hoàn tất commit sau khi method return.
10. `AccessDeniedException` kế thừa `RuntimeException` nên trigger rollback mặc định.

Production thường cần thêm quyền `DOC_EDIT`/`DOC_DELETE`, tài liệu locked, legal hold, policy theo ACL, tenant admin và version. Tất cả điều kiện đó phải được tính cho **từng item**, không chỉ đối tượng đầu.

### Một nguyên tắc quan trọng về transaction và self-invocation

Không đặt `@Transactional` vào helper private rồi nghĩ nó tự mở transaction. Trong proxy-based Spring AOP, lời gọi `this.innerTransactional()` có thể không được intercept. Đặt boundary ở public service được inject từ Spring Context; nếu tách policy sang bean riêng, để public method transaction gọi policy trong cùng transaction.

## 6. Integration tests: chứng minh dữ liệu không bị đổi một phần

Các test dùng H2 và Spring Context thật. Chúng không chỉ assert exception mà **đọc lại DB** sau khi service báo lỗi. `@WithMockUser` tạo Authentication cho test; không phải cơ chế xác thực thật bằng password/JWT.

**`src/test/java/demo/batch/BulkDocumentServiceTest.java`**

~~~java
package demo.batch;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = BatchAuthorizationApplication.class)
class BulkDocumentServiceTest {

    @Autowired BulkDocumentService bulk;
    @Autowired DocumentRepository repository;
    @Autowired PlatformTransactionManager transactionManager;

    private Long a1;
    private Long a2;
    private Long b1;
    private Long e1;

    @BeforeEach
    void seed() {
        repository.deleteAll();
        repository.flush();

        a1 = repository.saveAndFlush(
                new DocumentEntity("acme", "alice", "A1")).getId();
        a2 = repository.saveAndFlush(
                new DocumentEntity("acme", "alice", "A2")).getId();
        b1 = repository.saveAndFlush(
                new DocumentEntity("acme", "bob", "B1")).getId();
        e1 = repository.saveAndFlush(
                new DocumentEntity("globex", "eve", "E1")).getId();
    }

    private String title(Long id) {
        return repository.findById(id).orElseThrow().getTitle();
    }

    @Test
    @WithMockUser(username = "alice")
    void fullAuthorizationUpdatesAll() {
        bulk.renameAll(List.of(a1, a2), "Reviewed");

        assertEquals("Reviewed", title(a1));
        assertEquals("Reviewed", title(a2));
        assertEquals("B1", title(b1));
    }

    @Test
    @WithMockUser(username = "alice")
    void oneForeignOwnerBlocksTheEntireUpdate() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.renameAll(List.of(a1, b1), "Reviewed"));

        assertEquals("A1", title(a1));
        assertEquals("B1", title(b1));
    }

    @Test
    @WithMockUser(username = "alice")
    void crossTenantDocumentBlocksTheEntireUpdate() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.renameAll(List.of(a2, e1), "Reviewed"));

        assertEquals("A2", title(a2));
        assertEquals("E1", title(e1));
    }

    @Test
    @WithMockUser(username = "alice")
    void missingDocumentBlocksTheEntireUpdate() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.renameAll(
                        List.of(a1, Long.MAX_VALUE), "Reviewed"));

        assertEquals("A1", title(a1));
    }

    @Test
    @WithMockUser(username = "alice")
    void duplicateIdIsAnInvalidBatch() {
        assertThrows(IllegalArgumentException.class,
                () -> bulk.renameAll(List.of(a1, a1), "Reviewed"));

        assertEquals("A1", title(a1));
    }

    @Test
    @WithMockUser(username = "alice")
    void mixedAuthorizationDeletesNothing() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.deleteAll(List.of(a1, b1)));

        assertTrue(repository.existsById(a1));
        assertTrue(repository.existsById(b1));
    }

    @Test
    @WithMockUser(username = "alice")
    void missingDocumentBlocksTheEntireDelete() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.deleteAll(List.of(a2, Long.MAX_VALUE)));

        assertTrue(repository.existsById(a2));
    }

    @Test
    @WithMockUser(username = "alice")
    void fullAuthorizationDeletesAllRequestedRows() {
        bulk.deleteAll(List.of(a1, a2));

        assertFalse(repository.existsById(a1));
        assertFalse(repository.existsById(a2));
        assertTrue(repository.existsById(b1));
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.renameAll(List.of(a1), "Reviewed"));

        assertEquals("A1", title(a1));
    }

    @Test
    @WithMockUser(username = "unknown")
    void unknownPrincipalIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.deleteAll(List.of(a1)));

        assertTrue(repository.existsById(a1));
    }

    @Test
    void aRuntimeFailureAfterFlushStillRollsBack() {
        TransactionTemplate transaction =
                new TransactionTemplate(transactionManager);

        assertThrows(IllegalStateException.class,
                () -> transaction.executeWithoutResult(status -> {
                    DocumentEntity doc =
                            repository.findById(a1).orElseThrow();
                    doc.rename("Temporary");
                    repository.flush();

                    // SQL đã flush nhưng transaction CHƯA commit.
                    throw new IllegalStateException("Injected failure");
                }));

        // Transaction đã rollback, truy vấn sau vẫn thấy giá trị cũ.
        assertEquals("A1", title(a1));
    }
}
~~~

**Ý nghĩa của test cuối:** nó cố tình sửa entity và `flush` SQL trước khi ném một unchecked exception từ callback `TransactionTemplate`. Dữ liệu phải rollback khi transaction kết thúc vì exception. Điều này kiểm chứng độc lập nguyên tắc **flush != commit**.

### 6.1. Ma trận kết quả

| Trường hợp | Kết quả dự kiến |
| --- | --- |
| Alice sửa hai tài liệu của mình | Hai tài liệu đổi |
| Alice sửa một của mình + một của Bob | Throw, **cả hai giữ nguyên** |
| Có một document tenant khác | Throw, **cả hai giữ nguyên** |
| Có một ID không tồn tại | Throw, không cập nhật subset |
| Có duplicate ID | Invalid input, không mutate |
| Alice xóa A1 + B1 | Throw, **cả hai còn tồn tại** |
| Alice xóa A1 + A2 | Cả hai bị xóa |
| Anonymous gọi batch | Bị Method Security từ chối |
| Username không có trong trusted directory | Bị service từ chối |
| SQL flush rồi ném exception | Database rollback, title ban đầu giữ nguyên |

### 6.2. Chạy test

Trên macOS/Linux:

~~~text
./gradlew test --tests demo.batch.BulkDocumentServiceTest
~~~

Trên Windows:

~~~text
gradlew.bat test --tests demo.batch.BulkDocumentServiceTest
~~~

Source không có `System.out.println`, nên không có stdout nghiệp vụ cố định. Điều cần kiểm chứng là JUnit xanh và Gradle hoàn thành tác vụ test. Mã đã được trình bày để chạy trong project có version phù hợp; phải thực thi thử trên chính stack dự án trước production.

**Không đặt `@Transactional` trên chính lớp test chỉ để “dọn dữ liệu”:** nếu test tự rollback sau khi service chạy, có thể che giấu việc service đã commit riêng hoặc chưa có transaction. Test này giữ test method ở ngoài transaction, để mỗi kết quả service được quan sát lại qua repository.

## 7. Cách tối ưu bằng conditional bulk UPDATE

Cách ví dụ chính là load entity, kiểm tra từng row rồi cập nhật. Một phương án khác là đặt chính sách vào chính SQL:

~~~sql
UPDATE documents
SET title = :title
WHERE id IN (:ids)
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_user;
~~~

Đoạn mã Spring Data JPA minh họa:

~~~java
// CHỈ MINH HỌA: đặt trong DocumentRepository có import cần thiết.
@Modifying
@Query("""
    update DocumentEntity d
       set d.title = :title
     where d.id in :ids
       and d.tenantId = :tenant
       and d.ownerId = :owner
    """)
int conditionalRename(
        @Param("ids") List<Long> ids,
        @Param("tenant") String tenant,
        @Param("owner") String owner,
        @Param("title") String title);
~~~

Service gọi:

~~~java
// CHỈ MINH HỌA: actor phải đến từ nguồn đã xác thực và IDs đã chuẩn hóa.
@Transactional
public void renameConditionally(List<Long> ids, String title, Actor actor) {
    int affected = repository.conditionalRename(
            ids, actor.tenantId(), actor.userId(), title);

    if (affected != ids.size()) {
        // Cùng transaction -> rollback những row vừa update.
        throw new AccessDeniedException("Batch not permitted");
    }
}
~~~

**Tại sao phải kiểm tra số hàng?** SQL UPDATE với WHERE owner/tenant chỉ cập nhật rows khớp. Nếu request 3 IDs và 1 ID thuộc Bob, SQL vẫn có thể trả số rows ảnh hưởng là 2 mà không ném lỗi. Nếu service trả success, ta đã vi phạm all-or-nothing. Throw trong transaction trước commit có thể rollback hai rows vừa cập nhật.

### Giới hạn của phương án này

- JPA bulk DML **bỏ qua** entity callbacks như `@PreUpdate` và có thể không tự áp dụng `@Version`. Nếu có optimistic locking, cần đưa điều kiện version/logic tăng version vào thiết kế SQL riêng.
- `EntityManager` đang giữ entities có thể bị stale so với DB sau `@Modifying`. `clearAutomatically`/`flushAutomatically` có tác động đến thay đổi đang pending, phải dùng có hiểu biết.
- Số hàng trả về cần được kiểm chứng trên database/provider thật; nhất là no-op update, triggers, soft delete, view và vendor-specific row count semantics.
- Nếu chính sách còn có trạng thái LOCKED, legal hold, ACL phức tạp, tenant group membership thì phải đưa **đầy đủ** điều kiện vào WHERE, hoặc check trong transaction trước.
- Với nhiều IDs, giới hạn tham số của SQL `IN` và lock contention có thể buộc chia nhỏ. Nếu yêu cầu atomic toàn bộ, mọi chunk vẫn phải tham gia **cùng transaction** hoặc dùng một cơ chế staging/set-based update tương đương.

Do đó, phương án SQL conditional có thể hiệu quả hơn nhưng cần đánh giá chính sách, hiệu lực của version và database thực tế; không coi “một SQL statement” là đủ để giải quyết authorization.

## 8. Đừng dùng blind bulk DELETE theo ID do client gửi

~~~java
// NGUY HIỂM nếu ids đến từ client và không được authorize:
repository.deleteAllByIdInBatch(ids);
~~~

`deleteAllByIdInBatch` có thể phát một câu delete bulk; nó không tự kiểm tra owner/tenant/permission. Các API `deleteAllInBatch` và bulk JPQL cũng không bảo toàn mọi semantics của entity lifecycle:

- Không nhất thiết chạy `@PreRemove` callbacks hoặc cascades giống xóa từng entity.
- First-level persistence context có thể không đồng bộ với DB sau bulk query.
- `@Version` có thể không được áp dụng tự động.
- Foreign-key constraints, soft-delete policy và audit có thể bị ảnh hưởng.

Muốn DELETE bulk all-or-nothing, có thể dùng:

~~~sql
DELETE FROM documents
WHERE id IN (:ids)
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_user;
~~~

Kết hợp **cùng transaction**, số hàng/đủ tập và policy bổ sung. Nếu số affected khác số requested và semantics row count của DB đã được xác minh, throw runtime exception để rollback. Nếu cần callback/cascade hoặc policy phức tạp, cách load/lock/check all rồi `repository.deleteAll(entities)` thường dễ bảo đảm đúng hơn.

## 9. Những lỗi phá vỡ atomicity

### 9.1. Một transaction riêng cho mỗi item

~~~java
// PHẢN VÍ DỤ:
for (Long id : ids) {
    itemService.updateInIndependentTransaction(id, title);
}
~~~

Nếu item 1, 2 đã commit rồi item 3 fail, một transaction ngoài không thể tự rollback hai commit trước. `Propagation.REQUIRES_NEW` luôn mở một physical transaction độc lập; không dùng cho từng item khi hợp đồng là all-or-nothing. `Propagation.REQUIRED` thường tham gia transaction hiện có, nhưng phải bảo đảm public service boundary đã mở transaction thật.

### 9.2. Bắt và nuốt `AccessDeniedException`

~~~java
// PHẢN VÍ DỤ: thao tác hợp lệ có thể commit dù một item denied.
@Transactional
public void unsafeUpdate(List<Long> ids) {
    for (Long id : ids) {
        try {
            updateOne(id);
        } catch (AccessDeniedException ignored) {
            // tiếp tục item sau
        }
    }
}
~~~

Nếu exception bị nuốt và không có rollback-only, transaction có thể commit các thay đổi đã làm. Với all-or-nothing, không nuốt lỗi. Để exception propagate; hoặc nếu bắt lỗi để xử lý, cần rollback-only đúng cách và không trả thành công.

### 9.3. Checked exception không tự rollback mặc định

Spring Framework mặc định rollback cho `RuntimeException` và `Error`. Một checked exception như `IOException` không rollback mặc định trừ khi cấu hình. Với loại exception checked riêng cho batch, thêm:

~~~java
// MINH HỌA: BatchPermissionException là checked exception do bạn định nghĩa.
@Transactional(rollbackFor = BatchPermissionException.class)
public void batch(...) throws BatchPermissionException {
    // ...
}
~~~

Trong code của bài, `AccessDeniedException` là unchecked nên phù hợp rollback mặc định.

### 9.4. Self-invocation và method security không được proxy

~~~java
@Service
class UnsafeService {
    public void outer() {
        this.innerTransactional();
    }

    @Transactional
    public void innerTransactional() {
        // ...
    }
}
~~~

`this.innerTransactional()` có thể bypass transaction proxy. Tương tự, gọi một `@PreAuthorize` method trong chính target qua `this` có thể bỏ qua chốt authorization. Dùng public application service được Spring quản lý, được gọi qua proxy; test thực tế bằng `@SpringBootTest`.

### 9.5. Chỉ kiểm tra phần tử đầu tiên

~~~java
// PHẢN VÍ DỤ:
if (policy.canUpdate(authentication, records.get(0))) {
    repository.saveAll(records);
}
~~~

Record đầu tiên đạt không làm những record còn lại đạt. Nếu muốn dùng `PermissionEvaluator` hoặc ACL, gọi policy trên **từng** domain object, hoặc dùng repository/ACL batch lookup rồi xác minh tất cả kết quả.

### 9.6. Số ID trong request không khớp số rows

~~~text
Request: [101, 101, 999]
SQL IN trả về row 101, bỏ qua ID 999 và duplicate 101.
~~~

Phải reject duplicate hoặc chuẩn hóa rõ thành Set rồi công bố semantics. Đừng chỉ xét `!found.isEmpty()` hoặc `affected > 0`; với all-or-nothing, điều kiện cần là **mọi ID hợp lệ và mọi row được phép**.

### 9.7. Chia batch thành các chunk nhưng commit từng chunk

~~~text
Chunk 1: 10.000 items → COMMIT
Chunk 2: 10.000 items → COMMIT
Chunk 3: có item thiếu quyền → FAIL
~~~

Hai chunk đầu không thể tự rollback khi chunk 3 fail. Nếu cần atomicity toàn batch, dùng chung transaction ở mức cơ sở dữ liệu hoặc chuyển sang thuật toán set-based/staging có commit đồng nhất. Nếu không thể vì thời gian lock, chuyển hợp đồng thành workflow **partial/async có trạng thái và cơ chế bù trừ**; không gọi nó là all-or-nothing.

### 9.8. Commit DB không rollback được tác dụng phụ ở hệ thống khác

~~~text
DB transaction: update rows → rollback
Email bên ngoài: đã gửi
Broker: đã publish message
Object storage: đã xóa file
~~~

Transaction relational database không thu hồi email, event đã gửi hoặc file trên cloud. Dùng transactional outbox để ghi event trong cùng DB transaction rồi publisher xử lý **sau commit**, consumer idempotent và strategy retry/compensation. `@TransactionalEventListener(AFTER_COMMIT)` có thể chọn thời điểm callback trong JVM nhưng một mình nó không bảo đảm delivery nếu process chết sau commit.

## 10. Cạnh tranh dữ liệu và TOCTOU

### 10.1. Race giữa check và write

~~~text
T1: Alice đọc Document#101 owner=alice → allow
T2: Một transaction khác chuyển owner=Bob
T3: Alice update Document#101 theo quyền cũ
~~~

Đây là **time-of-check/time-of-use** (TOCTOU). Để giảm rủi ro, kiểm tra quyền và mutate trong cùng transaction, dùng `PESSIMISTIC_WRITE`/optimistic version/conditional SQL, và cân nhắc toàn bộ nguồn policy: tenant membership, ACL, trạng thái khóa, sharing.

Khóa row Document **không tự khóa** bảng role membership hoặc ACL ở nơi khác. Nếu một thay đổi policy làm quyền không còn hợp lệ, hệ thống cần đồng bộ version/authorization guard phù hợp với rủi ro nghiệp vụ.

### 10.2. Deadlock và timeout

Hai batch khóa các tập giao nhau theo thứ tự khác nhau có thể deadlock. Sort IDs giúp nhất quán về logic nhưng DB query optimizer không nhất thiết lock đúng thứ tự input. Giới hạn số phần tử, giữ transaction ngắn, đặt timeout, giám sát deadlock và retry **toàn bộ transaction cùng authorization** sau khi đọc lại dữ liệu.

### 10.3. Optimistic version

`@Version` thường giúp detect concurrent update trong entity lifecycle. Nếu gặp `OptimisticLockException` hoặc exception tương ứng của Spring Data, transaction phải rollback; retry cần thực hiện lại query/authorization trên trạng thái mới. Với JPQL bulk DML, phải tự quản lý version vì bulk không mặc nhiên tương đương `save(entity)`.

## 11. Mở rộng từ owner-only sang authority và ACL

Ví dụ permission UPDATE thực tế có thể là:

~~~text
UPDATE document:
  same trusted tenant
  AND (owner OR ACL.WRITE grant)
  AND DOC_EDIT authority
  AND status != LOCKED
~~~

Permission DELETE có thể yêu cầu thêm legal hold không tồn tại và quyền DELETE trong ACL. Nếu dùng `PermissionEvaluator`:

~~~java
// CHỈ MINH HỌA: model, helpers và PermissionEvaluator cần được cấu hình.
public boolean canDelete(
        Authentication authentication,
        Document document) {
    return sameTrustedTenant(authentication, document)
            && hasAuthority(authentication, "DOC_DELETE")
            && permissionEvaluator.hasPermission(
                    authentication, document, "DELETE")
            && !document.isLocked();
}
~~~

Với batch, kiểm tra `canDelete` trên **tất cả** document trước khi delete. `AclService.readAclsById` có thể giảm N+1 khi tải nhiều ACL, nhưng phải gọi `Acl.isGranted` theo **từng ObjectIdentity và SID/permission**. Một row có grant không đại diện cho tất cả rows.

Trong hệ thống multi-tenant, người dùng có cùng username ở hai tenant cần ID bất biến phân biệt; không dùng `ownerId` từ JSON request làm bằng chứng. Nếu policy cấp quyền admin vượt owner, phải giới hạn admin đúng tenant và scope theo nghiệp vụ.

## 12. Lỗi 401/403/404 và tránh lộ dữ liệu

Service all-or-nothing có thể trả `AccessDeniedException("Batch not permitted")` khi một item không tồn tại hoặc thiếu quyền, để caller không biết chính xác ID nào thuộc người khác. Khi đưa ra HTTP:

- 401 khi caller chưa xác thực, tùy `AuthenticationEntryPoint`.
- 403 khi caller đã xác thực nhưng không đạt quyền.
- Một số API chọn 404/response không tiết lộ tài nguyên nhằm tránh enumeration.

Không có quy tắc HTTP duy nhất bắt buộc cho mọi ứng dụng; hợp đồng API phải nhất quán. Đặc biệt, không trả danh sách ID “denied vì thuộc Bob” cho người không có quyền xem metadata ấy.

### Audit phải phân biệt thất bại với trạng thái business đã commit

Log có thể ghi:

~~~text
operation=BULK_UPDATE_DENIED
actor=alice
tenant=acme
requested_count=3
result=DENIED
business_committed=false
~~~

Không log token, payload nhạy cảm hoặc metadata về owner của item không được phép. Nếu audit row được ghi trong cùng transaction rồi transaction rollback, audit có thể cũng mất; một audit store độc lập hoặc outbox/sự kiện riêng cần thiết kế bảo mật và consistency riêng.

## 13. Ma trận test bắt buộc trước production

| Tình huống | Kỳ vọng atomic |
| --- | --- |
| 2 IDs đều thuộc actor | Cả hai update/delete |
| 1 ID thuộc actor, 1 ID người khác | Không row nào đổi |
| 1 ID khác tenant | Không row nào đổi |
| 1 ID không tồn tại | Không row nào đổi |
| Duplicate/null/empty list | Reject input, không row nào đổi |
| ID count vượt giới hạn | Reject input |
| Anonymous hoặc principal không được xác minh | Không mutate |
| Lỗi SQL ở giữa/commit | Rollback |
| Concurrent owner/tenant update | Lock hoặc version conflict; retry toàn bộ |
| Row có legal hold hoặc LOCKED | Từ chối cả batch |
| Batch delete có cascade/soft-delete | Kiểm tra lifecycle, DB constraints và toàn batch |
| Batch SQL affected count nhỏ hơn requested | Throw rồi rollback |
| Role/ACL thay đổi giữa check và write | Policy/version guard tương ứng |
| Message broker down sau commit | Business commit và outbox/retry, không thông báo thành công sai |

**Một test chỉ assert exception/status là chưa đủ**. Sau lần gọi bị từ chối, phải truy vấn lại database từ ngoài transaction để xác nhận mọi bản ghi giữ nguyên. Tránh đặt `@Transactional` trên test method theo cách tự rollback cuối test và vô tình che giấu transaction boundary của service.

## 14. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| 2/3 rows đổi dù API trả lỗi | Mỗi item tự commit hoặc catch exception | Một transaction chung, rollback unhandled |
| IDs không tồn tại bị im lặng bỏ qua | `IN` chỉ trả subset | So sánh đủ tập với IDs chuẩn hóa |
| Người dùng sửa được row người khác | Chỉ kiểm tra role hoặc phần tử đầu | Check owner/tenant/permission từng row |
| `@PreFilter` làm thay đổi tập đầu vào | Filter unauthorized items | Không dùng silent filter cho all-or-nothing |
| `@PostAuthorize` từ chối nhưng dữ liệu đã sửa | Hậu kiểm chạy sau side effect | Authorization trước mutation |
| `@Transactional` không hiệu lực | Self-invocation hoặc target không qua proxy | Public service bean, integration test |
| Checked exception khiến transaction commit | Default rollback chỉ runtime/error | `rollbackFor` hoặc unchecked exception |
| `REQUIRES_NEW` làm commit từng item | Physical transactions độc lập | `REQUIRED` trong một outer transaction |
| `deleteAllByIdInBatch` bỏ qua policy | Blind bulk DML theo IDs của client | Check all/conditional SQL trước delete |
| DML bypass `@Version`/callbacks | Bulk JPQL khác entity update | Version-aware WHERE và lifecycle-aware design |
| Một row bị chuyển owner sau check | TOCTOU | Lock/version/conditional update |
| Retry chỉ thực hiện các rows còn lại | Partial retry phá atomic | Retry toàn bộ batch sau re-auth |
| Sai tenant cùng username | ID hoặc source tenant không tin cậy | Verified principal + tenant binding |
| DB rollback nhưng email vẫn gửi | Side effect ngoài transaction | Outbox/after commit/compensation |
| Response 200 nhưng commit thất bại | Response phát trước completion | Trả response sau transaction boundary |
| Test chỉ assert 403 | Không xác minh DB state | Readback toàn bộ rows sau failure |

## 15. Bài tập thực hành

**Bài 1 – Sai lầm silent filter.** Thử một bản `unsafeUpdate` có `continue` khi gặp row không thuộc owner. Với IDs [A1,B1], quan sát A1 đổi còn B1 không. Khôi phục all-or-nothing và test cả hai giữ nguyên.

**Bài 2 – Thêm LOCKED.** Thêm cờ `locked` vào Document. Một ID của Alice đã khóa phải khiến toàn batch từ chối, ngay cả khi các IDs khác hợp lệ.

**Bài 3 – Bổ sung authority.** Yêu cầu `DOC_EDIT` cho UPDATE và `DOC_DELETE` cho DELETE ngoài owner/tenant. Test actor có authority nhưng không phải owner, owner thiếu authority và actor đủ cả hai.

**Bài 4 – Conditional bulk update.** Tạo repository `@Modifying @Query` ràng buộc tenant/owner/status. Với 3 IDs, 1 thiếu quyền, bắt exception khi affected không đủ. Đọc DB sau rollback và kiểm tra entity version.

**Bài 5 – Concurrent writer.** Dùng hai transaction để đổi owner và cập nhật title trên cùng ID. Đo kết quả với `PESSIMISTIC_WRITE`, optimistic version và conditional update trên database production-test.

**Bài 6 – Chunk lớn.** Thiết kế xử lý 10.000 IDs với giới hạn SQL parameters và lock time. Giải thích vì sao commit mỗi chunk không còn atomic toàn batch, và khi nào phải chuyển sang workflow async/partial có kết quả từng item.

**Bài 7 – ACL per-object.** Dùng `PermissionEvaluator` hoặc `AclService` để check `WRITE/DELETE` theo từng ObjectIdentity. Một ID thiếu ACE khiến cả batch thất bại; kiểm tra cả parent inheritance.

**Bài 8 – Audit/outbox.** Tạo event chỉ được gửi khi batch commit. Cố tình ném exception sau `flush()` để bảo đảm không có event thành công sai và DB rollback.

**Tiêu chí hoàn thành:** phân biệt all-or-nothing với best-effort; validate đầy đủ IDs; kiểm tra quyền tất cả rows; dùng `@Transactional` đúng ranh giới; xác minh rollback sau flush; không dùng blind bulk delete; nhận ra rủi ro TOCTOU, JPQL DML, tenant, multi-transaction và side effect ngoài DB.

## Tài liệu tham khảo chính thức

- Spring Security – **Method Security** (`@EnableMethodSecurity`, `@PreAuthorize`, `@PreFilter`, `@PostAuthorize`): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework – **Rolling Back a Declarative Transaction**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework – **@Transactional Settings**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework – **Transaction Propagation** (`REQUIRED`, `REQUIRES_NEW`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Data JPA – **Locking** (`@Lock`): https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html
- Spring Data JPA – **JPA Query Methods** (`@Modifying`, bulk DML và entity callbacks): https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data JPA – **JpaRepository API**, `deleteAllInBatch` và `deleteAllByIdInBatch`: https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
