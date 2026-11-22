# Triển khai PermissionEvaluator cho quyền đọc, sửa và chia sẻ

> **Ngữ cảnh:** Spring Security – authorization, nhóm **Thực hành tích hợp**. Bài học áp dụng Spring Security 6.x / Spring Boot 3.x và Java 17+. Ví dụ chạy với JUnit 5, kiểm tra method security thật qua Spring proxy và dùng repository in-memory để quan sát quyền và tác động phụ. Với database production, cần bổ sung transaction, kiểm tra cạnh tranh và ràng buộc tenant tại DB.

## 1. Đề bài và quy tắc phân quyền

Ứng dụng quản lý tài liệu có `id`, `tenant`, `owner`, `title`, danh sách `readers` và `editors`. Dịch vụ có ba hành động:

- **`read`:** đọc tiêu đề/nội dung tài liệu. Owner, editor và reader trong cùng tenant được phép.
- **`edit`:** sửa tiêu đề/nội dung. Owner và editor trong cùng tenant được phép; reader chỉ đọc.
- **`share`:** cấp quyền đọc cho một người khác. Trong bài này **chỉ owner** được chia sẻ; editor không được tự nâng quyền.
- **Tenant isolation:** dù người gọi trùng owner hoặc được liệt kê trong ACL, tài liệu thuộc tenant khác vẫn phải bị từ chối. Tenant của người gọi xuất phát từ ngữ cảnh authentication đáng tin cậy.
- **Fail closed:** ID không tồn tại, loại tài nguyên lạ, permission lạ, principal anonymous hoặc không đủ context đều nhận `false`.

Ma trận quyền:

| Quan hệ actor–document | Read | Edit | Share |
| --- | :---: | :---: | :---: |
| Owner cùng tenant | ✅ | ✅ | ✅ |
| Editor cùng tenant | ✅ | ✅ | ❌ |
| Reader cùng tenant | ✅ | ❌ | ❌ |
| Không có quyền, cùng tenant | ❌ | ❌ | ❌ |
| Khác tenant dù trùng owner | ❌ | ❌ | ❌ |
| Anonymous hoặc tài liệu không tồn tại | ❌ | ❌ | ❌ |

Ứng dụng thật có thể có quản trị viên, người được ủy quyền hoặc hạn dùng cho share; đó là policy **bổ sung có chủ đích**, không được ngầm cho `ROLE_ADMIN` bỏ qua tenant.

**Đích học tập:** Viết một `PermissionEvaluator` hiện thực toàn bộ ma trận trên, nối nó vào `DefaultMethodSecurityExpressionHandler`, dùng `@PreAuthorize` để chặn trước thân method, rồi chứng minh bằng integration test cả những trường hợp DENY đều **không sửa tài liệu, không ghi ACL và không gửi notification**.

## 2. Spring Security gọi PermissionEvaluator như thế nào?

Spring method security được bật bằng `@EnableMethodSecurity`. `@PreAuthorize` chạy qua Spring AOP interceptor trước lời gọi service. Biểu thức SpEL `hasPermission(...)` sẽ dùng evaluator được cấu hình trong `MethodSecurityExpressionHandler`:

```text
Caller đã xác thực
   │
   ▼
DocumentService Spring proxy
   │
   ▼
@PreAuthorize("hasPermission(#p0, 'DOCUMENT', 'edit')")
   │
   ▼
MethodSecurityExpressionHandler → PermissionEvaluator
   │
   ├─ lấy actor từ Authentication
   ├─ nạp canonical resource theo ID
   ├─ so khớp tenant
   └─ xét action read/edit/share
         │
         ├─ false → AccessDeniedException → KHÔNG chạy body
         └─ true  → gọi DocumentService.edit(...) → mutation
```

**Authentication** trả lời ai là người gọi; `GrantedAuthority` có thể chứa role/scope/tenant từ nguồn xác thực; **object permission** trả lời người đó được làm gì với *tài liệu cụ thể*. `hasAuthority('document:write')` không tự biết owner/ACL của `documentId=10`. Nếu cần vừa quyền chức năng vừa quyền object, dùng logic AND:

```java
// Đoạn minh họa trong service, không phải class độc lập.
@PreAuthorize("hasAuthority('document:write') "
    + "and hasPermission(#p0, 'DOCUMENT', 'edit')")
public void edit(long documentId, String newTitle) { /* ... */ }
```

Không dùng OR khi cả scope và quyền object đều là điều kiện bắt buộc. Với ví dụ chạy hoàn chỉnh bên dưới, policy tập trung vào `hasPermission` để dễ nhìn thấy cách hoạt động của evaluator.

### 2.1. Hai overload bắt buộc của interface

```java
// Chữ ký rút từ org.springframework.security.access.PermissionEvaluator.
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);

boolean hasPermission(
    Authentication authentication,
    Serializable targetId,
    String targetType,
    Object permission
);
```

**Overload bằng object** phục vụ `hasPermission(#document, 'read')` khi đã có document. **Overload bằng ID/type** phục vụ `hasPermission(#documentId, 'DOCUMENT', 'edit')` khi service chỉ nhận một ID. `targetType` là định danh domain do ứng dụng quy định; ví dụ sử dụng hằng chuỗi chính xác `DOCUMENT`. `permission` là `Object` nên cần kiểm tra kiểu và danh sách action hợp lệ thay vì tin mọi string.

Nếu controller nhận một object JSON với các trường `owner`, `tenant` hoặc `readers`, actor có thể tự khai mình là owner. Vì vậy trong bài thực hành, overload bằng object **chỉ lấy ID** rồi chuyển sang overload ID để **nạp bản canonical từ store**. Đây là lựa chọn có chi phí truy vấn nhưng dễ chứng minh không dựa vào object giả mạo.

### 2.2. Đặt chốt chặn trước tác động phụ

`@PreAuthorize` kiểm tra trước body. `@PostAuthorize` đánh giá sau khi body đã tạo kết quả; nếu áp dụng nó làm chốt duy nhất cho method `share`, ACL hoặc email có thể đã thay đổi rồi mới bị từ chối. `@PostFilter` chỉ lọc phần tử kết quả, không hoàn tác mutation. Hãy dùng pre-authorization cho `edit/share` và kiểm thử **trạng thái dữ liệu sau khi DENY**, không chỉ exception.

Method security chỉ intercept lời gọi đi qua **Spring-managed proxy**. Unit test `new DocumentService(...)` hoặc method trong cùng bean gọi `this.edit(...)` có thể bỏ qua advice. Trong test mục 4, đối tượng service lấy qua `@Autowired` từ Spring để kiểm tra đúng đường chạy.

## 3. Triển khai policy: quy tắc trước code

Đầu vào policy là `(Authentication, documentId, action)`, không phải kết quả filter response.

```text
Nếu authentication thiếu/anonymous → DENY
Nếu targetType không là DOCUMENT, id sai kiểu → DENY
Nếu action không thuộc read/edit/share → DENY
Nếu document không tồn tại → DENY
Nếu actor không có tenant đáng tin khớp document.tenant → DENY

read  = owner OR editor OR reader
edit  = owner OR editor
share = owner
```

Trong test, authority `TENANT_acme` đại diện cho tenant được một cơ chế authentication đáng tin cấp. Ứng dụng thật phải **xác thực tenant** từ principal/token đã kiểm chứng hoặc context có policy rõ ràng, không copy bừa từ header `X-Tenant` hoặc body. Cần tránh dùng username làm identity toàn cục trong hệ thống cho phép username trùng giữa các tenant; có thể dùng user ID/subject + tenant/issuer.

Chia sẻ là một thao tác **thay đổi ACL**, khác với sửa nội dung. Ví dụ chỉ cấp **quyền đọc** cho recipient; không tự cấp edit hoặc quyền share tiếp.

## 4. Ví dụ chạy được: Spring Boot 3.x, Java 17, JUnit 5

Bộ test tạo Spring context nhẹ, không khởi chạy web server. `DocumentStore` là kho in-memory bất biến theo từng bản ghi; `NotificationGateway` đếm số lần gửi. Dùng `@WithMockUser` để mô phỏng những actor có tenant khác nhau.

### 4.1. Dependencies

Với module Gradle đã dùng Spring Boot plugin/BOM:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu các dependency này đã có thì không khai báo lặp. Tạo **một file** `src/test/java/example/security/PermissionEvaluatorIntegrationTest.java`:

```java
package example.security;

import java.io.Serializable;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = PermissionEvaluatorIntegrationTest.App.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class PermissionEvaluatorIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @Import({
        DocumentStore.class,
        DocumentPermissionEvaluator.class,
        DocumentService.class,
        NotificationGateway.class
    })
    static class App {

        // static @Bean giúp handler được công bố sớm,
        // trước khi Spring khởi tạo method-security configuration.
        @Bean
        static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            DocumentPermissionEvaluator permissionEvaluator
        ) {
            DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
            handler.setPermissionEvaluator(permissionEvaluator);
            return handler;
        }
    }

    public record Document(
        long id, String tenant, String owner, String title,
        Set<String> readers, Set<String> editors
    ) {
        // Không chia sẻ mutable Set giữa các caller.
        public Document {
            readers = Set.copyOf(readers);
            editors = Set.copyOf(editors);
        }
    }

    public static class DocumentStore {
        private final Map<Long, Document> documents =
            new ConcurrentHashMap<>();

        public void reset() {
            documents.clear();
        }

        public void seed(Document document) {
            documents.put(document.id(), document);
        }

        public Optional<Document> find(long id) {
            return Optional.ofNullable(documents.get(id));
        }

        public Document require(long id) {
            return find(id).orElseThrow();
        }

        public void rename(long id, String title) {
            documents.computeIfPresent(id, (key, doc) ->
                new Document(
                    doc.id(), doc.tenant(), doc.owner(), title,
                    doc.readers(), doc.editors()
                )
            );
        }

        public void grantRead(long id, String recipient) {
            documents.computeIfPresent(id, (key, doc) -> {
                Set<String> readers = new HashSet<>(doc.readers());
                readers.add(recipient);
                return new Document(
                    doc.id(), doc.tenant(), doc.owner(), doc.title(),
                    readers, doc.editors()
                );
            });
        }
    }

    // Mô phỏng tác động ngoài database transaction.
    public static class NotificationGateway {
        private final AtomicInteger sends = new AtomicInteger();

        public void send() {
            sends.incrementAndGet();
        }

        public int count() {
            return sends.get();
        }

        public void reset() {
            sends.set(0);
        }
    }

    public static class DocumentPermissionEvaluator
        implements PermissionEvaluator {

        private final DocumentStore store;

        public DocumentPermissionEvaluator(DocumentStore store) {
            this.store = store;
        }

        @Override
        public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission
        ) {
            // Không tin owner/tenant trong object do client tự dựng:
            // chỉ giữ ID rồi nạp lại canonical document từ store.
            if (!(targetDomainObject instanceof Document doc)) {
                return false;
            }
            return hasPermission(
                authentication, Long.valueOf(doc.id()),
                "DOCUMENT", permission
            );
        }

        @Override
        public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission
        ) {
            if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
                return false;
            }

            if (!"DOCUMENT".equals(targetType)
                || !(targetId instanceof Long id)
                || !(permission instanceof String operation)) {
                return false;
            }

            String action = operation.toLowerCase(Locale.ROOT);
            if (!Set.of("read", "edit", "share").contains(action)) {
                return false;
            }

            Optional<Document> found = store.find(id);
            if (found.isEmpty()) {
                return false;
            }
            Document doc = found.get();

            // TENANT_* là authority từ authentication đáng tin.
            boolean sameTenant = authentication.getAuthorities().stream()
                .anyMatch(granted -> (
                    "TENANT_" + doc.tenant()
                ).equals(granted.getAuthority()));
            if (!sameTenant) {
                return false;
            }

            String actor = authentication.getName();
            boolean owner = doc.owner().equals(actor);

            return switch (action) {
                case "read" -> owner
                    || doc.readers().contains(actor)
                    || doc.editors().contains(actor);
                case "edit" -> owner || doc.editors().contains(actor);
                case "share" -> owner;
                default -> false;
            };
        }
    }

    public static class DocumentService {
        private final DocumentStore store;
        private final NotificationGateway notifications;

        public DocumentService(
            DocumentStore store, NotificationGateway notifications
        ) {
            this.store = store;
            this.notifications = notifications;
        }

        @PreAuthorize("hasPermission(#p0, 'DOCUMENT', 'read')")
        public String read(long documentId) {
            return store.require(documentId).title();
        }

        @PreAuthorize("hasPermission(#p0, 'DOCUMENT', 'edit')")
        public void edit(long documentId, String title) {
            store.rename(documentId, title);
            notifications.send();
        }

        @PreAuthorize("hasPermission(#p0, 'DOCUMENT', 'share')")
        public void shareRead(long documentId, String recipient) {
            if (recipient == null || recipient.isBlank()) {
                throw new IllegalArgumentException("Invalid recipient");
            }
            // Ví dụ giả định recipient hợp lệ trong cùng tenant.
            // Production phải kiểm tra tenant/membership của recipient.
            store.grantRead(documentId, recipient);
            notifications.send();
        }
    }

    @Autowired DocumentStore store;
    @Autowired DocumentService service;
    @Autowired DocumentPermissionEvaluator evaluator;
    @Autowired NotificationGateway notifications;

    @BeforeEach
    void seed() {
        store.reset();
        notifications.reset();

        // ID 10: owner alice, editor bob, reader carol.
        store.seed(new Document(
            10L, "acme", "alice", "Original",
            Set.of("carol"), Set.of("bob")
        ));

        // ID 20: username alice cũng là owner,
        // nhưng document thuộc tenant globex, khác acme.
        store.seed(new Document(
            20L, "globex", "alice", "Other tenant",
            Set.of("alice"), Set.of("alice")
        ));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "TENANT_acme")
    void ownerCanReadEditAndShare() {
        assertEquals("Original", service.read(10L));
        service.edit(10L, "Revised");
        service.shareRead(10L, "dave");

        assertEquals("Revised", store.require(10L).title());
        assertTrue(store.require(10L).readers().contains("dave"));
        assertEquals(2, notifications.count());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "TENANT_acme")
    void editorCanReadAndEditButCannotShare() {
        assertEquals("Original", service.read(10L));
        service.edit(10L, "Edited by Bob");
        assertThrows(AccessDeniedException.class,
            () -> service.shareRead(10L, "dave"));

        assertEquals("Edited by Bob", store.require(10L).title());
        assertFalse(store.require(10L).readers().contains("dave"));
        assertEquals(1, notifications.count());
    }

    @Test
    @WithMockUser(username = "carol", authorities = "TENANT_acme")
    void readerCannotEditOrShareAndHasNoSideEffects() {
        assertEquals("Original", service.read(10L));
        assertThrows(AccessDeniedException.class,
            () -> service.edit(10L, "Tampered"));
        assertThrows(AccessDeniedException.class,
            () -> service.shareRead(10L, "dave"));

        assertEquals("Original", store.require(10L).title());
        assertFalse(store.require(10L).readers().contains("dave"));
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(username = "dave", authorities = "TENANT_acme")
    void unrelatedUserCannotReadEditOrShare() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(10L));
        assertThrows(AccessDeniedException.class,
            () -> service.edit(10L, "Tampered"));
        assertThrows(AccessDeniedException.class,
            () -> service.shareRead(10L, "eve"));

        assertEquals("Original", store.require(10L).title());
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "TENANT_acme")
    void tenantBoundaryOverridesEvenOwnerAndAcl() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(20L));
        assertThrows(AccessDeniedException.class,
            () -> service.edit(20L, "Tampered"));
        assertThrows(AccessDeniedException.class,
            () -> service.shareRead(20L, "dave"));

        assertEquals("Other tenant", store.require(20L).title());
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "TENANT_acme")
    void unknownResourcesAndUnsupportedPermissionsDeny() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertFalse(evaluator.hasPermission(
            authentication, 999L, "DOCUMENT", "read"));
        assertFalse(evaluator.hasPermission(
            authentication, 10L, "DOCUMENT", "delete"));
        assertFalse(evaluator.hasPermission(
            authentication, 10L, "ORDER", "read"));
        assertFalse(evaluator.hasPermission(
            authentication, (Object) null, "read"));

        assertThrows(AccessDeniedException.class,
            () -> service.read(999L));
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "TENANT_acme")
    void objectOverloadUsesCanonicalStoreNotForgedFields() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertTrue(evaluator.hasPermission(
            authentication, store.require(10L), "share"));

        // Caller giả mạo tenant/owner của object id=20.
        // Store chuẩn vẫn giữ id=20 trong tenant globex.
        Document forged = new Document(
            20L, "acme", "alice", "Forged",
            Set.of("alice"), Set.of("alice")
        );

        assertFalse(evaluator.hasPermission(
            authentication, forged, "share"));
        assertEquals("Other tenant", store.require(20L).title());
    }
}
```

Test sử dụng cú pháp `#p0`, tức tham số thứ nhất của method, để không phụ thuộc việc compiler giữ tên tham số bằng `-parameters`. Trong bài thực tế nếu dùng `#documentId`, phải bảo đảm Spring có thể khám phá tên tham số hoặc dùng `@P`.

Lệnh chạy:

```bash
./gradlew test --tests "example.security.PermissionEvaluatorIntegrationTest"
```

Trên Windows sử dụng `gradlew.bat`; Gradle multi-project có thể cần `:module-path:test`. Với Spring Boot 3.x và dependency đúng như trên, **kết quả mong đợi: 7 bài test PASS**. Đây là assertions JUnit, không phải chương trình `main` có stdout cố định. Ví dụ dùng store in-memory nên không thể lấy kết quả này làm bằng chứng cho commit/rollback của JDBC/JPA.

### 4.2. Bài test chứng minh những gì?

| Test | Chính sách | Assertion chính |
| --- | --- | --- |
| `ownerCanReadEditAndShare` | Owner có ba quyền | Title đổi, recipient được cấp read, đúng 2 event |
| `editorCanReadAndEditButCannotShare` | Editor không được share | Sửa được, share bị deny; ACL không đổi; đúng 1 event |
| `readerCannotEditOrShareAndHasNoSideEffects` | Reader chỉ có read | Edit/share đều deny; title, ACL và notification không đổi |
| `unrelatedUserCannotReadEditOrShare` | Stranger cùng tenant | Không đọc/sửa/share, không tạo tác động phụ |
| `tenantBoundaryOverridesEvenOwnerAndAcl` | Tenant gate phủ quyết | Cùng username/ACL nhưng sai tenant vẫn deny |
| `unknownResourcesAndUnsupportedPermissionsDeny` | Fail closed | ID/type/action lạ, target object null đều false |
| `objectOverloadUsesCanonicalStoreNotForgedFields` | Chống object giả mạo | Owner/tenant tự khai không vượt qua lookup canonical |

Với ca bị từ chối, test phải kiểm tra **sau khi gọi** rằng dữ liệu, ACL và outbound effects không thay đổi. Chỉ kiểm tra exception là chưa đủ nếu chương trình đặt authorization sau mutation.

## 5. Chuyển bài mẫu thành thiết kế production

### 5.1. Tách các lớp theo trách nhiệm

```text
HTTP Controller
     │
     ▼
DocumentService  ← @PreAuthorize(hasPermission(...))
     │                          │
     │                          ▼
     │               DocumentPermissionEvaluator
     │                          │
     ▼                          ▼
DocumentRepository        ACL/PolicyRepository
     │                          │
     └──────── Database ────────┘
     │
     └── outbox/notification sau thao tác hợp lệ
```

Evaluator **chỉ kiểm tra quyền**; tránh gửi email, sửa ACL hoặc gọi network API có side effect chỉ vì cần đánh giá policy. Nếu logic quyền phức tạp, cho evaluator gọi một `DocumentPolicy` riêng có unit test. Nếu policy đọc repository nhiều lần, cân nhắc query tối ưu, cache có invalidation và fail closed khi thiếu thông tin.

### 5.2. Cấp quyền chia sẻ phải xác minh recipient

`shareRead(documentId, recipient)` trong demo giả định recipient là người hợp lệ cùng tenant. Code thật nên:

1. Kiểm tra actor có `share` trên tài liệu.
2. Kiểm tra recipient tồn tại, thuộc đúng tenant, không bị khóa và được phép nhận tài liệu.
3. Xác định chính xác grant: `READ` hay `EDIT`, hạn sử dụng, có được chia sẻ tiếp không.
4. Ghi ACL có transaction phù hợp; xử lý share trùng idempotently.
5. Gửi notification qua cơ chế bảo đảm chỉ sau commit (ví dụ outbox).
6. Test revoke và thời điểm quyền có hiệu lực, kể cả cache cũ.

Không cho rằng quyền `edit` bao hàm quyền `share`. Nếu nghiệp vụ muốn editor cũng share, phải sửa ma trận policy có chủ ý và thêm kiểm thử.

### 5.3. Tránh TOCTOU khi quyền thay đổi đồng thời

Evaluator kiểm tra theo dữ liệu tại thời điểm A; body `edit` chạy tại thời điểm B. Trong khoảng đó, document có thể đổi owner/tenant/trạng thái hoặc user bị thu hồi quyền. Đó là rủi ro time-of-check to time-of-use.

Với database, một cách giảm race là **đưa điều kiện tenant và ACL vào chính câu UPDATE**; ví dụ dưới chỉ là SQL định hướng, cần điều chỉnh schema/dialect:

```sql
UPDATE document
   SET title = :new_title
 WHERE id = :id
   AND tenant_id = :trusted_tenant
   AND (
       owner_id = :actor_id
       OR EXISTS (
           SELECT 1
             FROM document_acl a
            WHERE a.document_id = document.id
              AND a.principal_id = :actor_id
              AND a.permission = 'EDIT'
       )
   );
```

Kiểm tra **affected rows**: 1 row hợp lệ; 0 row nghĩa là không có row thỏa policy tại thời điểm mutation. Với các luồng phức tạp, cần locking/isolation/optimistic version và transaction. Không chỉ chạy `SELECT` kiểm tra owner trước rồi gửi `UPDATE document SET ... WHERE id = ?` không có tenant/policy điều kiện.

Với list/pagination nhiều tài liệu, ưu tiên scope tenant/ACL **ngay trong query** thay vì tải cả bảng rồi `@PostFilter`: xử lý hiệu năng tốt hơn, page/count chính xác hơn và giảm nguy cơ tải dữ liệu của tenant khác vào memory/log.

### 5.4. Transaction và notification

Một `@PreAuthorize` deny trước body giúp tránh tác động từ service đó. Nhưng khi đã cho phép và quá trình ghi lỗi, `@Transactional` chỉ quản lý tài nguyên transaction tương ứng. Email, HTTP call, queue hoặc thay đổi in-memory có thể đã xảy ra dù DB rollback. Khi nghiệp vụ yêu cầu phát thông báo sau commit, có thể dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc transactional outbox + retry/idempotency.

Nếu test commit/rollback của service, cần DB thật hoặc Testcontainers/H2 phù hợp và assert **sau khi service return/throw**; tránh gắn `@Transactional` lên test vì transaction do test tạo có thể che lỗi boundary và tự rollback cuối test.

### 5.5. Cache, revoke và audit

- **Cache permission:** key cần actor ID, tenant, document ID, action và version ACL/policy; thay đổi share/owner/revoke phải invalidate. Đừng cache quyết định allow vô thời hạn.
- **Revoke:** editor bị xóa khỏi editors có thể vẫn còn quyền đọc nếu cũng thuộc readers. Policy cần xác định thứ tự áp dụng grant/deny.
- **Audit:** ghi actor, tenant, resource, action, decision theo policy lưu log; tránh đưa tài liệu nhạy cảm hoặc token vào log DENY.
- **DB row-level security:** có thể bổ sung defense-in-depth, không thay thế authorization action (read/edit/share).
- **Exception policy:** storage lỗi không được biến thành “permit”. Ứng dụng có thể trả lỗi hệ thống thích hợp nhưng tuyệt đối không tiếp tục mutation khi chưa có quyết định quyền đáng tin.

## 6. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| `hasPermission(...)` luôn false | Chưa gắn evaluator vào `MethodSecurityExpressionHandler`; sai `targetType`/permission | Đăng ký handler bằng `@Bean static`, test một owner hợp lệ |
| Method bị gọi dù deny | Thiếu `@EnableMethodSecurity` hoặc bypass proxy qua `this`/`new` | Gọi bean injected từ một bean khác; đo side effect |
| Reader sửa được | Dùng điều kiện `read` thay `edit` hoặc ghép OR quá rộng | Ma trận riêng cho read/edit/share |
| Editor cấp share được | Coi edit đồng nghĩa share | Kiểm tra rule `share` chỉ owner |
| User khác tenant đọc được | Chỉ so owner/ACL, tenant từ request không tin cậy | Tenant gate từ authenticated principal, DB scope |
| Client dựng document giả để nhận grant | Tin field owner/tenant ở overload object | Lookup canonical document theo ID |
| Null/unknown ID ném lỗi không kiểm soát | Thiếu nhánh deny trước khi gọi store | `Optional` và fail closed |
| Deny nhưng gửi notification | Check sau body, `@PostAuthorize` hoặc side effect trong evaluator | `@PreAuthorize`, side-effect assertions |
| Revoke xong vẫn đọc được | Cache/token/quyền bị stale | ACL version và invalidate/test revoke |
| Có quyền lúc check nhưng không còn lúc update | Race/TOCTOU | Conditional mutation, transaction/locking |

**PermissionEvaluator khác gì ACL module?** `PermissionEvaluator` chỉ là API điểm nối cho `hasPermission`. Nó không tự tạo bảng ACL hoặc tính kế thừa quyền. Spring Security ACL có `AclPermissionEvaluator`, `AclService` và các bảng SID/ACE/ACL, hữu ích khi cần ACL persistent đa cấp. Với mô hình owner/editor/reader nhỏ, custom domain evaluator thường dễ đọc và test hơn. Trong Spring Security 6+, method authorization bên dưới dựa trên `AuthorizationManager`; `PermissionEvaluator` vẫn là hook SpEL hợp lệ. Nếu policy phát triển phức tạp, có thể cân nhắc bean authorizer hoặc custom `AuthorizationManager<MethodInvocation>`.

## 7. Checklist nghiệm thu

- [ ] `@EnableMethodSecurity` đã bật; bean `MethodSecurityExpressionHandler` cấu hình `setPermissionEvaluator`.
- [ ] Cả hai overload của `PermissionEvaluator` hoạt động; overload object không tin owner/tenant tự khai.
- [ ] Phân biệt read, edit, share theo ma trận đã thống nhất, không có quyền ngầm.
- [ ] Tenant lấy từ ngữ cảnh đáng tin, có check trước mọi điều kiện ACL.
- [ ] Unknown permission/type/id, anonymous và document missing đều fail closed.
- [ ] Method được gọi qua Spring proxy, deny xảy ra trước mutation.
- [ ] Mọi DENY đều giữ nguyên dữ liệu, ACL và notification.
- [ ] Share kiểm tra recipient/tenant và loại grant; có kế hoạch revoke.
- [ ] Với database thật, kiểm tra row scope, concurrency, transaction/outbox.
- [ ] Test owner/editor/reader/stranger/cross-tenant và các đường gọi HTTP khi cần.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) – cấu hình `@EnableMethodSecurity`, `@PreAuthorize`, SpEL `hasPermission` và expression handler.
- [Spring Security – PermissionEvaluator Java API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html) – hai overload `hasPermission`.
- [Spring Security – Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html) – `@WithMockUser` và test tích hợp.
- [Spring Framework – AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) – giới hạn self-invocation.
- [Spring Security – ACL Support](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html) – phương án ACL lưu trữ riêng.
