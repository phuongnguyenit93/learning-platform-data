# Nhầm lọc kết quả với chặn thực thi hành động

> **Ngữ cảnh:** Spring Security – authorization, nhóm **Sai sót và lỗ hổng**. Bài học dành cho Spring Security 6 / Spring Boot 3.x, Java 17+ và method security dựa trên Spring AOP proxy. Trọng tâm là phân biệt **dữ liệu nào được hiện ra** với **hành động nào được phép chạy**.

## 1. Vấn đề: phản hồi an toàn chưa chắc hành động an toàn

**Lọc kết quả (result filtering)** chỉ quyết định bản ghi hoặc trường dữ liệu nào được trả về cho caller. Ví dụ: lọc danh sách sao cho Alice chỉ nhìn thấy tài liệu của Alice, hay loại trường `internalNote` khỏi JSON.

**Chặn thực thi (action authorization)** phải quyết định **trước khi tác động xảy ra** xem actor có được làm thao tác cụ thể trên resource cụ thể hay không: tạo, sửa, xóa, phê duyệt, hoàn tiền, gửi thông báo, gọi API hệ thống ngoài.

Một endpoint có thể trả `[]` hoặc HTTP 403 **sau khi** đã thay đổi CSDL, gửi email hoặc phát message. Đó là lỗi nghiêm trọng: phản hồi đã lọc tạo cảm giác hành động bị từ chối, trong khi side effect đã thực thi.

Bốn điều phải kiểm tra **riêng**:

1. **Action permission:** actor có quyền thực hiện loại thao tác này không (ví dụ `document:update`, `refund:approve`)?
2. **Object/tenant scope:** thao tác đó được phép trên document/order/tenant/owner nào?
3. **Side effects:** database, queue, email, HTTP, file, cache, audit có đổi **trước khi bị deny** không?
4. **Response visibility:** dữ liệu trả về đã lọc đúng row/field chưa?

Đúng mục 4 không chứng minh đúng các mục 1–3. **Đọc danh sách** và **thực hiện mutation** là hai loại workflow khác nhau, cần policy và test khác nhau.

## 2. Method security: chặn ở đâu, lọc ở đâu?

### 2.1. Dòng thời gian của một lỗ hổng

```text
SAI – lọc kết quả sau mutation:
Request của alice (owner="bob")
    │
    ▼
Service.action(...)
    ├─ UPDATE tài liệu của bob        ← đã thay đổi
    ├─ gửi notification               ← đã phát tác động ngoài
    └─ return danh sách tài liệu
          │
          ▼
    @PostFilter lọc bản ghi bob
          │
          ▼
    Response = []                   ← chỉ che kết quả


ĐÚNG – bảo vệ trước hành động:
Request của alice
    │
    ▼
Xác định actor, action, resource, tenant/state đáng tin
    │
    ▼
@PreAuthorize / policy / conditional update
    ├─ DENY → dừng trước DB/gateway
    └─ ALLOW → thực thi đúng tài nguyên được phép
                     │
                     ▼
                lọc response nếu cần
```

### 2.2. Công cụ nào làm được việc nào?

| Cơ chế | Khi nào chạy | Có chặn body trước side effect? | Vai trò phù hợp |
| --- | --- | --- | --- |
| `@PreAuthorize` | Trước method invocation | **Có**, khi lời gọi được interceptor bắt | Quyền thực thi action, role/scope và resource policy |
| `@PostAuthorize` | Sau khi body đã trả kết quả | **Không** | Quyền dựa trên kết quả, chủ yếu read; cẩn trọng khi dùng cho write |
| `@PostFilter` | Sau khi body tạo kết quả collection/map/stream được hỗ trợ | **Không** | Giới hạn phần tử được nhìn thấy trong kết quả |
| `@PreFilter` | Lọc tham số collection trước khi body chạy | **Không tự chứng minh** cả action được phép | Chọn đối tượng đầu vào; cần kiểm tra action/policy riêng |
| DTO/JSON field masking | Khi map/serialize response | **Không** | Ẩn trường nhạy cảm khỏi JSON |
| Filter trên frontend | Sau khi client nhận dữ liệu | **Không** | Trình bày UI, không phải bảo vệ server |
| Query-scope `WHERE tenant_id = ?` | Khi đọc/ghi database | Chỉ khi được áp đúng thao tác và context | Giới hạn row truy cập/biến đổi, bảo vệ theo tenant |

Với Spring Security 6, `@EnableMethodSecurity` đăng ký các method-security interceptor. Annotation chỉ có hiệu lực khi gọi qua Spring proxy: unit test tạo service bằng `new` hoặc lời gọi `this.securedMethod()` trong cùng bean có thể bỏ qua advice. Phải test qua bean được Spring inject.

**Không nên hiểu `@PostFilter` là tường lửa cho method:** nó xử lý *giá trị trả về*, không tự ngăn lệnh SQL, network call hoặc thao tác in-memory đã chạy trong body. Ngay cả khi collection sau lọc rỗng, body vẫn có thể đã xử lý tất cả bản ghi.

### 2.3. `@PostAuthorize` cũng đến sau body

Với method:

```java
@PostAuthorize("returnObject.owner() == authentication.name")
public Receipt process(String owner) {
    database.write(/* ... */);
    paymentGateway.charge(/* ... */);
    return /* Receipt thuộc owner */;
}
```

điều kiện dựa vào `returnObject` chỉ được đánh giá **sau khi** body chạy. Nếu người gọi không đủ quyền, Spring có thể ném `AccessDeniedException` nhưng payment request đã được gửi. Với DB nằm trong `@Transactional`, commit/rollback còn tùy transaction boundary, thứ tự advice và rollback rule; **không được suy ra** “denied = rollback toàn bộ” hoặc “denied luôn commit”. Phải đo trạng thái DB thực tế và side effect ngoài giao dịch sau lời gọi.

## 3. Các lỗ hổng phổ biến ngoài thực tế

### 3.1. IDOR/BOLA: che owner nhưng cho sửa theo ID

Alice chỉ được sửa document của Alice. API nhận `PATCH /documents/57`, ID 57 thuộc Bob. Một cách viết sai (pseudocode, không phải file hoàn chỉnh):

```java
public List<DocumentDto> renameThenList(long id, String title) {
    repository.rename(id, title);             // SAI: không xét owner
    notificationGateway.sendRenamed(id);      // Đã phát thông báo
    return repository.findAll().stream()
        .filter(doc -> doc.owner().equals(currentUsername()))
        .map(mapper::toDto)
        .toList();
}
```

Alice có thể nhận danh sách rỗng và vẫn sửa được Bob. Thay `filter` bằng `@PostFilter` cũng không giải quyết gì; người dùng chỉ **không thấy** tài liệu Bob sau khi đã sửa nó. Che `ownerId` trong DTO chỉ giải quyết field exposure, không giải quyết **Broken Object Level Authorization (BOLA/IDOR)**.

### 3.2. Scope chức năng không đồng nghĩa quyền đối tượng

`@PreAuthorize("hasAuthority('SCOPE_documents.write')")` có thể kiểm tra quyền ghi **nói chung**, nhưng chưa chứng minh người đó được sửa *document id 57*. Actor–action–resource–context cần xét role/scope, owner, tenant, trạng thái (ví dụ chỉ được sửa `DRAFT`), và quan hệ nghiệp vụ. Không tin mặc định `ownerId` hay `tenantId` do client nhập; phải truy ra từ authenticated principal/tenant context đã được xác thực.

### 3.3. `@PreFilter` vẫn có thể cho chạy sai loại hành động

Khi method nhận danh sách tài liệu để “approve”, `@PreFilter` có thể bỏ phần tử không thuộc Alice. Nhưng method còn được gọi trên những phần tử khác và có thể phát tác động chung. Việc Alice **sở hữu** một tài liệu không tự chứng minh Alice được **phê duyệt** nó. Với batch, phải quy định rõ: từ chối toàn bộ nếu có một đối tượng trái phép (all-or-nothing) hay xử lý một phần; test DB/notification theo đúng hợp đồng.

### 3.4. Chỉ ẩn nút hoặc lọc dữ liệu ở client

Ẩn nút `Delete` ở React không ngăn request thủ công qua cURL/Postman. Frontend lọc danh sách sau khi fetch còn có thể để lộ dữ liệu chưa lọc trong Network tab. Tất cả mutation phải được kiểm tra quyền ở backend tại ranh giới thực thi.

## 4. Integration test Java 17+ chứng minh bằng quan sát

Bộ test dưới dùng Spring Boot 3.x, Spring Security 6.x, JUnit 5. `DocumentStore` lưu bản ghi in-memory; `SendingGateway` đếm số thông báo đã “gửi”. Chúng **không thuộc database transaction**: test chứng minh trực tiếp lọc output không hoàn tác state hoặc external effect. Bài test gọi bean **được Spring inject** để method-security interceptor chạy thật.

Trong module đã cấu hình Spring Boot dependency management:

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

Tạo file **`src/test/java/example/security/FilteringIsNotAuthorizationTest.java`**:

```java
package example.security;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = FilteringIsNotAuthorizationTest.App.class)
class FilteringIsNotAuthorizationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @Import({DocumentStore.class, SendingGateway.class, DocumentService.class})
    static class App {}

    public record Document(long id, String owner, String title) {}

    public static class DocumentStore {
        private final AtomicLong ids = new AtomicLong();
        private final List<Document> documents = new CopyOnWriteArrayList<>();

        public Document add(String owner, String title) {
            Document doc = new Document(ids.incrementAndGet(), owner, title);
            documents.add(doc);
            return doc;
        }

        // Trả mutable List để @PostFilter lọc phần tử.
        public List<Document> all() {
            return new ArrayList<>(documents);
        }

        public void reset() {
            documents.clear();
            ids.set(0);
        }
    }

    // Mô phỏng tác động bên ngoài: không thể rollback bằng DB transaction.
    public static class SendingGateway {
        private final AtomicInteger count = new AtomicInteger();

        public void send() {
            count.incrementAndGet();
        }

        public int sent() {
            return count.get();
        }

        public void reset() {
            count.set(0);
        }
    }

    public static class DocumentService {
        private final DocumentStore store;
        private final SendingGateway sending;

        public DocumentService(DocumentStore store, SendingGateway sending) {
            this.store = store;
            this.sending = sending;
        }

        // Hợp lý cho READ: chỉ trả tài liệu người đang xem.
        @PostFilter("filterObject.owner() == authentication.name")
        public List<Document> visibleDocuments() {
            return store.all();
        }

        // LỖ HỔNG: write/send đã xảy ra TRƯỚC khi @PostFilter chạy.
        @PostFilter("filterObject.owner() == authentication.name")
        public List<Document> unsafeCreateThenFilter(
            String owner, String title) {

            store.add(owner, title);
            sending.send();
            return store.all();
        }

        // LỖ HỔNG: kiểm tra quyền bằng returnObject là quá muộn.
        @PostAuthorize("returnObject.owner() == authentication.name")
        public Document unsafeCreateThenCheck(String owner, String title) {
            Document doc = store.add(owner, title);
            sending.send();
            return doc;
        }

        // Chặn TRƯỚC khi method body tạo side effect.
        // #p0 là tham số thứ nhất (owner), không phụ thuộc -parameters.
        @PreAuthorize("isAuthenticated() and #p0 == authentication.name")
        public Document createIfAllowed(String owner, String title) {
            Document doc = store.add(owner, title);
            sending.send();
            return doc;
        }
    }

    @Autowired DocumentStore store;
    @Autowired SendingGateway sending;
    @Autowired DocumentService service;

    @BeforeEach
    void reset() {
        store.reset();
        sending.reset();
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void readFilterChangesOnlyResponse() {
        store.add("alice", "Mine");
        store.add("bob", "His");

        List<Document> visible = service.visibleDocuments();

        assertEquals(
            List.of("alice"),
            visible.stream().map(Document::owner).toList());
        assertEquals(2, store.all().size()); // Bob vẫn ở store.
        assertEquals(0, sending.sent());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void postFilterDoesNotBlockUnauthorizedAction() {
        List<Document> visible =
            service.unsafeCreateThenFilter("bob", "Changed");

        assertTrue(visible.isEmpty());       // Response đã lọc.
        assertEquals(1, store.all().size()); // Mutation đã xảy ra.
        assertEquals("bob", store.all().get(0).owner());
        assertEquals(1, sending.sent());     // Event đã được gửi.
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void postAuthorizeDenyHappensAfterSideEffects() {
        assertThrows(AccessDeniedException.class,
            () -> service.unsafeCreateThenCheck("bob", "Changed"));

        assertEquals(1, store.all().size());
        assertEquals(1, sending.sent());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void preAuthorizeDeniesBeforeSideEffects() {
        assertThrows(AccessDeniedException.class,
            () -> service.createIfAllowed("bob", "Changed"));

        assertEquals(0, store.all().size());
        assertEquals(0, sending.sent());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void validActionStillRuns() {
        Document result = service.createIfAllowed("alice", "Allowed");

        assertEquals("alice", result.owner());
        assertEquals(1, store.all().size());
        assertEquals(1, sending.sent());
    }
}
```

Chạy test từ project/module Gradle tương ứng:

```bash
./gradlew test --tests "example.security.FilteringIsNotAuthorizationTest"
```

Trên Windows, dùng `gradlew.bat`; multi-project Gradle có thể cần `:module-path:test`. **Kết quả kỳ vọng: 5 test PASS**, dựa trên các assertion JUnit; không có stdout cố định.

**Giải thích:**

- `readFilterChangesOnlyResponse`: Alice chỉ nhìn thấy tài liệu của mình, Bob vẫn có trong kho. Đó là hành vi lọc output hợp lệ cho read.
- `postFilterDoesNotBlockUnauthorizedAction`: Alice nhận danh sách rỗng nhưng kho đã có tài liệu Bob và gateway đã chạy. Đây là bằng chứng chính của lỗ hổng.
- `postAuthorizeDenyHappensAfterSideEffects`: `AccessDeniedException` xảy ra **sau** ghi/send; mô hình cố ý dùng tài nguyên không giao dịch để chứng minh deny không thu hồi tác động.
- `preAuthorizeDeniesBeforeSideEffects`: lời gọi từ chối trước thân method, cả store và gateway đều không đổi.
- `validActionStillRuns`: thao tác được quyền vẫn thành công.

Trong ứng dụng thực, không nên nhận `owner` từ client rồi tin nó là principal. Demo dùng `#p0 == authentication.name` để mô tả một rule đối tượng cụ thể; service thật nên lấy danh tính từ authenticated principal và áp dụng policy nghiệp vụ, bao gồm delegation/quyền quản trị khi cần.

## 5. Ngăn IDOR/BOLA ngay trong mutation CSDL

### 5.1. Chỉ `hasRole` hoặc `hasAuthority` là thiếu

Một method có `@PreAuthorize("hasAuthority('SCOPE_documents.write')")` vẫn có thể bị khai thác nếu SQL cập nhật theo ID mà không xét owner/tenant:

```java
@PreAuthorize("hasAuthority('SCOPE_documents.write')")
public void rename(long documentId, String title) {
    repository.renameById(documentId, title);
}
```

Policy phải kiểm tra quyền của actor trên **tài nguyên cụ thể**, không chỉ quyền gọi chức năng. Nếu có cạnh tranh giữa “kiểm tra owner” và “update”, đối tượng có thể đổi state/owner giữa hai bước. Một pattern hữu ích là mutation SQL có điều kiện trong **cùng câu lệnh**.

```sql
UPDATE document
   SET title = :new_title
 WHERE id = :document_id
   AND tenant_id = :trusted_tenant_id
   AND owner_id = :authenticated_user_id
   AND status = 'DRAFT';
```

Kiểm tra row count: `1` nghĩa là một tài nguyên thỏa đúng điều kiện; `0` nghĩa là không có tài nguyên hợp lệ để cập nhật. Đoạn sau là **minh họa trong service có sẵn JDBC và trusted context**, không phải class Java độc lập:

```java
int updated = jdbc.update("""
    UPDATE document
       SET title = ?
     WHERE id = ?
       AND tenant_id = ?
       AND owner_id = ?
       AND status = 'DRAFT'
    """, newTitle, documentId, trustedTenantId, authenticatedUserId);

if (updated != 1) {
    throw new AccessDeniedException("Document unavailable");
}
// Sau khi quyền/mutation hợp lệ, mới tổ chức notification/outbox.
```

Giá trị `trustedTenantId` phải đến từ ngữ cảnh đã xác thực/cấp quyền, không lấy nguyên văn từ body/query param. API nên thống nhất cách trả 403/404 đối với tài nguyên không tồn tại/ngoài phạm vi, tránh lộ việc tồn tại của ID. Với workflow phức tạp, phải kiểm tra các transition và version/concurrency; database row-level security là lớp bảo vệ bổ sung, không thay thế action permission.

### 5.2. Lọc ngay từ query khi đọc nhiều dữ liệu

`@PostFilter` có giá trị cho danh sách nhỏ, nhưng method vẫn có thể tải mọi hàng trước khi lọc. Với multi-tenant, query-scope thường phù hợp hơn:

```sql
SELECT id, owner_id, title
FROM document
WHERE tenant_id = :trusted_tenant_id
  AND owner_id = :authenticated_user_id
ORDER BY id
LIMIT :page_size OFFSET :offset;
```

Lọc **trước** phân trang giúp tổng count/page phù hợp tập bản ghi được phép xem, tránh việc page sau `@PostFilter` đột nhiên rỗng hoặc thiếu phần tử. Query-scope giảm tải và nguy cơ lộ qua log/cache; nó **không** cho phép dùng query đọc để bảo vệ một lệnh UPDATE/DELETE khác không có điều kiện tương đương.

## 6. Transaction và side effect: đo sau khi hành động kết thúc

`@Transactional` chỉ bao những tài nguyên được transaction manager điều phối. Một runtime exception đi ra đúng boundary thường gây rollback DB theo rule mặc định, nhưng không tự thu hồi email/HTTP/message đã gửi, file/cache đã thay đổi, hoặc giao dịch `REQUIRES_NEW` khác đã commit.

**Trường hợp có `@PostAuthorize`:** bởi vì post-check chạy sau body, DB thay đổi có thể rollback hoặc commit tùy thứ tự advisor và transaction boundary. Vì vậy test nên quan sát đồng thời:

- trạng thái DB **sau khi** service return/throw;
- số lần gọi gateway và xác nhận từ hệ thống ngoài;
- outbox row/event nếu có;
- exception/HTTP status và dữ liệu trả về.

Nếu cần chỉ phát event sau commit, `@TransactionalEventListener(phase = AFTER_COMMIT)` có thể giúp trì hoãn listener; transactional outbox giúp phát sự kiện tin cậy với retry/idempotency. Cả hai **không thay** kiểm tra quyền trước action. Tránh gắn `@Transactional` lên test kiểm tra service transaction boundary, vì test-managed transaction có thể che lỗi và tự rollback sau test.

Một test chỉ xác nhận `verify(repository).save(...)` hoặc HTTP 403 **không** chứng minh DB đã commit/rollback hay external side effects chưa xảy ra. Dùng JDBC/JPA + H2 hoặc Testcontainers khi cần bằng chứng transaction thật.

## 7. Ma trận kiểm thử bắt buộc cho authorization

| Ca | Kỳ vọng response | Điều phải xác minh bên ngoài response |
| --- | --- | --- |
| Alice list tài liệu | Chỉ dữ liệu Alice | Không tạo/sửa/xóa row, không phát thông báo |
| Alice GET document Bob bằng ID | 403/404 theo policy | Không lộ nội dung, không thay đổi trạng thái |
| Alice PATCH document Bob | DENY | DB/queue/email/cache **không đổi** |
| Alice có scope write nhưng khác tenant | DENY | Không ảnh hưởng row tenant khác |
| Alice gửi batch lẫn tài nguyên được và không được phép | Theo hợp đồng batch | Kiểm tra từng row và side effect, đúng atomic/partial behavior |
| Alice gọi method WRITE có mỗi `@PostFilter` | Response có thể `[]` | Phải phát hiện unauthorized action vẫn đã chạy |
| Alice gọi WRITE có `@PostAuthorize` | Deny sau method | DB và gateway phải được kiểm tra, không suy từ exception |
| Alice sửa tài nguyên chính mình đúng trạng thái | Thành công | Đúng row thay đổi, event hợp lệ, không sửa row khác |

Nên thêm test qua HTTP (`MockMvc`) nếu muốn bảo đảm mapping 403/404; `@WithMockUser` test method chỉ tạo principal/authorities giả, không kiểm thử cơ chế xác thực token/session. Với method security, luôn kiểm tra đường gọi thực sự đi qua Spring proxy và không bị self-invocation bỏ qua.

## 8. Ngộ nhận và cách khắc phục

**“Ẩn nút ở UI là đã khóa thao tác.”** Không đúng: caller có thể gửi request thủ công. Server phải enforce policy trước mutation.

**“Response trống nghĩa là không có dữ liệu bị tác động.”** Không đúng: `@PostFilter` chỉ làm sạch những gì nhìn thấy. Assert trực tiếp row count, version, owner, event/counter.

**“`@PostAuthorize` ném `AccessDeniedException` nên tự động hoàn tác toàn bộ.”** Không có bảo đảm chung. Method đã chạy; tác động ngoài transaction không tự đảo ngược. Với DB, cần quan sát transaction thật và advisor order.

**“`@PreFilter` loại phần tử khác owner nên batch approve an toàn.”** Chưa đủ: phải kiểm tra role/action, trạng thái, scope và hợp đồng xử lý khi batch có phần tử không hợp lệ.

**“Có `@PreAuthorize('isAuthenticated()')` nên không thể IDOR.”** Authentication chỉ chứng minh caller là ai; authorization phải ràng buộc resource/tenant/operation. Owner/tenant không nên dựa vào input thiếu tin cậy.

**“`@Transactional` sẽ tự xử lý quyền và event.”** Transaction không quyết định policy; rollback DB không đương nhiên hoàn tác API call/email. Dùng chốt chặn trước action và thiết kế outbox/after-commit nếu cần.

**“Lọc client hay DTO có thể thay object-level authorization.”** DTO masking bảo vệ trường dữ liệu trả về; còn BOLA/IDOR liên quan quyền truy cập từng đối tượng. Đây là hai lớp bảo vệ độc lập.

## 9. Checklist thiết kế an toàn

1. Xác định actor, operation, resource, tenant/state và toàn bộ side effects cho từng endpoint.
2. Chặn action **trước body**: `@PreAuthorize`, policy service, và điều kiện row tại DB khi cần. Đảm bảo Spring proxy thực sự intercept.
3. Không dựa vào lọc kết quả, DTO, frontend hoặc HTTP status để chứng minh quyền thực thi.
4. Với mutation theo ID, dùng resource/tenant scope thật; cân nhắc conditional SQL để giảm race.
5. Với read, giới hạn dữ liệu trong query trước pagination và dùng output filtering cho trường hợp phù hợp.
6. Test deny-path bằng **zero mutation + zero outbound side effect**, không chỉ `assertThrows`/403/`[]`.
7. Test allow-path để không chặn nhầm, kiểm chứng trạng thái DB và phản hồi đúng.
8. Test riêng rollback, after-commit, outbox/retry khi có workflow transaction và hệ thống ngoài.

**Điều cần nhớ:** *Result filtering* trả lời “người dùng **nhìn thấy gì**”; *action authorization* trả lời “người dùng **được làm gì trên đối tượng nào**”. Cần chốt chặn **trước mutation** và chứng minh bằng trạng thái hệ thống **sau khi lời gọi kết thúc**.

## Tham khảo chính thống

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) – `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, interceptor.
- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html) – `@WithMockUser`, tích hợp Spring Test.
- [Spring Framework – AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) – self-invocation/proxy boundary.
- [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) – transaction/rollback và advice.
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) – `@TransactionalEventListener`.
- [OWASP API Security Top 10 – Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) – kiểm tra quyền trên từng resource.
