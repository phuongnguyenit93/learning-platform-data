# Tránh N+1 khi PermissionEvaluator hoặc ACL kiểm tra nhiều đối tượng

## 1. Bài toán và mục tiêu

Trong Spring Security, kiểm tra quyền trên **một đối tượng** thường rất đơn giản:

~~~java
@PreAuthorize("hasPermission(#documentId, 'Document', 'READ')")
public DocumentDto getDocument(long documentId) {
    return documentService.load(documentId);
}
~~~

Đoạn mã trên là ví dụ minh họa cho method security đã được bật và \`PermissionEvaluator\` đã được cấu hình. Nếu cần tra quyền trong database, một lời gọi \`hasPermission\` có thể kéo theo ít nhất một query. Điều này dễ chấp nhận với một đối tượng, nhưng tạo ra **N+1** khi API trả về danh sách N đối tượng rồi kiểm tra từng phần tử.

Ví dụ:

~~~java
@PostFilter("hasPermission(filterObject, 'READ')")
public List<Document> listDocuments() {
    return documentRepository.findAll();
}
~~~

\`@PostFilter\` duyệt những đối tượng được trả về, đánh giá biểu thức cho từng phần tử và loại phần tử không được phép. Nếu mỗi lần \`hasPermission\` lại thực hiện một query ACL, tổng số truy vấn có thể là **1 query tải danh sách + N query quyền**. Nếu evaluator còn tra membership, role, ACL inheritance hoặc chủ sở hữu theo từng item, số query có thể cao hơn. Việc gom các đối tượng trong Java Stream không tự gom các query SQL.

**Mục tiêu của bài:**
- Nhận diện N+1 do chính sách authorization, tách khỏi N+1 do Hibernate lazy loading.
- Đo số query, latency và số lần gọi ACL/PDP theo kích thước danh sách.
- Chọn giữa **lọc quyền tại database trước pagination** và **đọc quyền theo batch cho tập đối tượng giới hạn**.
- Áp dụng đúng \`PermissionEvaluator\`, \`AclService\`, \`PermissionCacheOptimizer\` và cache mà không vô tình thay đổi semantics của ACL.
- Kiểm chứng kết quả được phép/từ chối, tính đúng của phân trang và cô lập tenant sau khi tối ưu.

## 2. Cơ chế N+1 khi kiểm tra authorization

Giả sử một request lấy 100 tài liệu:

~~~text
HTTP GET /tenants/t-a/documents
  └─ SELECT ... FROM document WHERE tenant_id = 't-a'       [1 query]
      ├─ hasPermission(doc1, READ) → SELECT ACL...           [1 query]
      ├─ hasPermission(doc2, READ) → SELECT ACL...           [1 query]
      ├─ ...
      └─ hasPermission(doc100, READ) → SELECT ACL...         [1 query]

Tổng: khoảng 101 query, chưa tính membership, SID, lazy associations.
~~~

Bảng giả định **một query quyền cho mỗi đối tượng**, chưa tính cache:

| N đối tượng | Query tải danh sách | Query quyền từng item | Tổng |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 2 |
| 10 | 1 | 10 | 11 |
| 100 | 1 | 100 | 101 |
| 500 | 1 | 500 | 501 |

Đây là ví dụ tính toán, không phải con số cố định của Spring Security. Thực tế còn tùy evaluator, ACL cache, cấu trúc ACE, membership, SQL query plan và số lượng đối tượng đã bị loại.

### 2.1. Những đường đi thường gây lỗi

**Đường đi A — \`@PostFilter\` + \`PermissionEvaluator\`:**

~~~java
@PostFilter("hasPermission(filterObject, 'READ')")
public List<Document> findAll() {
    return documentRepository.findAll();
}
~~~

Spring Security duyệt collection sau khi service trả về. Nếu evaluator truy cập repository để quyết định từng object, N+1 phát sinh dù truy vấn \`findAll\` ban đầu rất nhanh.

**Đường đi B — lọc bằng Stream:**

~~~java
List<Document> visible = documents.stream()
        .filter(d -> permissionEvaluator.hasPermission(
                authentication, d, "READ"))
        .toList();
~~~

Mã nhìn gọn nhưng vẫn có N lần gọi \`hasPermission\`; một hàm bên trong có query thì vẫn là N query.

**Đường đi C — ACL dạng database:** \`AclPermissionEvaluator\` có thể gọi \`AclService\` để tra ACL cho \`ObjectIdentity\`. Nếu ACL không ở cache, mỗi object có thể kích hoạt đọc ACL và các bản ghi liên quan. SID theo user/authority và ACL inheritance có thể làm đường truy vấn phức tạp hơn. Tuy nhiên, **không phải mọi cấu hình Spring ACL đều mặc định N+1**: cache, lookup strategy và cơ chế batch đã có thể cải thiện.

**Đường đi D — ORM và remote authorization:** evaluator gọi \`document.getOwner().getMemberships()\` khiến Hibernate tải quan hệ lazy cho từng phần tử; hoặc gọi dịch vụ PDP/OPA qua HTTP từng object. Cả hai cũng là mô hình N+1, dù nơi tốn tài nguyên không giống nhau.

### 2.2. Triệu chứng cần kiểm tra

- SQL log có cùng một truy vấn ACL lặp lại với \`document_id\` khác nhau.
- Khi tăng kích thước page từ 20 lên 200, lượng truy vấn và thời gian phản hồi tăng gần tuyến tính.
- CPU database/connection pool tăng cao ở endpoint list/search; một endpoint detail vẫn nhanh.
- \`@PostFilter\` làm danh sách sau phân trang còn rất ít item; \`totalElements\` có thể không phản ánh số item mà user có quyền.
- Bật cache làm kết quả benchmark có vẻ tốt ở lần chạy thứ hai nhưng lần đầu hoặc sau revoke vẫn chậm.

**Cần phân biệt:** N lần đánh giá quyền bằng Java không nhất thiết là N+1 nếu dữ liệu quyền đã được tải trước và lookup hoàn toàn trong bộ nhớ. Mục tiêu tối ưu là số lần truy cập DB/network và chi phí tổng thể, chứ không phải loại bỏ mọi vòng lặp.

## 3. Định nghĩa chính sách trước khi tối ưu

Tối ưu authorization phải giữ nguyên quyết định **ALLOW/DENY**. Ví dụ hệ thống tài liệu:

- \`document\` có \`id\`, \`tenant_id\`, \`owner_id\`, \`visibility\`, \`deleted_at\`, \`created_at\`.
- \`tenant_membership\` có \`tenant_id\`, \`user_id\`, \`role\`, \`active\`.
- \`document_share\` có \`tenant_id\`, \`document_id\`, \`recipient_id\`, \`permission\`, \`expires_at\`, \`revoked_at\`.
- User phải có **membership active trong tenant**. Với quyền READ, trong tenant đó được đọc khi là owner, là ADMIN của tenant, tài liệu hiển thị TENANT, hoặc có grant READ/WRITE còn hạn và chưa revoke.
- WRITE không mặc định đồng nghĩa SHARE/DELETE; chính sách cho các action khác phải được định nghĩa độc lập.

Khi client truyền \`tenantId\`, server vẫn phải lấy danh tính từ \`Authentication\` và xác minh membership tương ứng. Không được tin \`role\`, \`owner_id\`, \`isAdmin\` hay \`grantedBy\` do client gửi. **ADMIN tenant B không được quyền trên document tenant A.**

Có hai loại list cần phân biệt:

1. **List chỉ chứa document có quyền READ:** authorization phải được đẩy vào truy vấn dữ liệu trước pagination nếu có thể.
2. **List đã được authorize bởi repository nhưng cần gắn thêm cờ \`canEdit\`, \`canShare\` cho UI:** có thể dùng batch lookup quyền trên tập document đã giới hạn.

Nếu giữ nguyên \`@PostFilter\` trên một page đã cắt ở database, cả hiệu năng **và** phân trang đều có thể sai.

## 4. Cách tốt nhất cho danh sách: lọc tại database trước pagination

Với chính sách READ tương đối đơn giản như mục 3, để database lọc quyền trong **một truy vấn set-based**. SQL minh họa dưới đây dùng tham số lấy từ principal đã xác thực và tenant đã xác minh:

~~~sql
SELECT d.id, d.title, d.owner_id, d.created_at
FROM document d
WHERE d.tenant_id = :tenantId
  AND d.deleted_at IS NULL
  AND EXISTS (
      SELECT 1
      FROM tenant_membership m
      WHERE m.tenant_id = d.tenant_id
        AND m.user_id = :userId
        AND m.active = TRUE
  )
  AND (
      d.owner_id = :userId
      OR d.visibility = 'TENANT'
      OR EXISTS (
          SELECT 1
          FROM tenant_membership m_admin
          WHERE m_admin.tenant_id = d.tenant_id
            AND m_admin.user_id = :userId
            AND m_admin.active = TRUE
            AND m_admin.role = 'ADMIN'
      )
      OR EXISTS (
          SELECT 1
          FROM document_share s
          WHERE s.tenant_id = d.tenant_id
            AND s.document_id = d.id
            AND s.recipient_id = :userId
            AND s.permission IN ('READ', 'WRITE')
            AND s.revoked_at IS NULL
            AND (s.expires_at IS NULL OR s.expires_at > :now)
      )
  )
ORDER BY d.created_at DESC, d.id DESC
LIMIT :pageSize OFFSET :offset;
~~~

Trong hệ thống thật, xác thực membership có thể diễn ra trước query bằng một phép tra cứu duy nhất; điều kiện \`EXISTS\` ở trên được giữ để minh họa ràng buộc authorization ngay trong SQL. \`:userId\`, \`:tenantId\` và \`:now\` là **bind parameters**, không nối chuỗi SQL từ request.

**Vì sao cách này tránh N+1?** Database xử lý tập document và tập share bằng join/semi-join/subquery, thay vì ứng dụng gửi một request SQL riêng cho mỗi document. Số statement nhìn từ application thường là một truy vấn trang, cộng truy vấn count nếu API dùng \`Page\`; database có thể vẫn duyệt nhiều hàng nội bộ nên cần xem query plan. \`EXISTS\` cũng tránh nhân bản document khi một tài liệu có nhiều bản ghi share/role.

### 4.1. Pagination và count phải cùng chính sách

Sai:

~~~text
Database lấy 20 document bất kỳ → @PostFilter bỏ 17 document
→ client nhận 3 document dù thực tế còn nhiều document được quyền ở trang sau.
~~~

Nếu API hiển thị \`Page<DocumentDto>\`, hãy áp dụng đúng **cùng predicate quyền** cho truy vấn lấy trang và truy vấn \`COUNT\`. Nếu count tính mọi document trước khi lọc, tổng kết quả vừa sai vừa có thể tiết lộ số lượng dữ liệu người dùng không được xem.

Với các bảng lớn, \`OFFSET\` sâu có thể chậm; có thể dùng keyset/cursor dựa trên \`(created_at, id)\` cùng điều kiện quyền. Cursor phải được ràng buộc với cùng tenant và filter; danh sách có thể thay đổi khi share/revoke giữa các request. Không che giấu hiện tượng đó bằng cache cũ.

### 4.2. Chỉ mục và dữ liệu cần đọc

Các chỉ mục gợi ý ban đầu (cần điều chỉnh qua \`EXPLAIN ANALYZE\` và dữ liệu thực tế):

~~~sql
CREATE INDEX idx_document_tenant_order
    ON document (tenant_id, created_at DESC, id DESC);

CREATE INDEX idx_membership_tenant_user
    ON tenant_membership (tenant_id, user_id);

CREATE INDEX idx_share_tenant_recipient_doc
    ON document_share (tenant_id, recipient_id, document_id);
~~~

Thêm điều kiện/partial index cho share còn hiệu lực hoặc trạng thái revoke tùy DBMS và đặc điểm truy vấn; không tạo hàng loạt index nếu chưa có bằng chứng. Cột \`expires_at\` thay đổi ý nghĩa theo thời gian, nên không thể giả định một cột boolean \`active\` đã cache luôn chính xác. Chỉ select những cột cần cho DTO; nếu map entity và duyệt các quan hệ lazy sau truy vấn, N+1 của Hibernate vẫn có thể xảy ra.

**Giới hạn quan trọng:** SQL \`EXISTS\` ở đây biểu diễn **mô hình share grant đơn giản**. Nếu hệ thống sử dụng đầy đủ Spring Security ACL với ACE allow/deny có thứ tự, SID gồm group/role, parent ACL/inheritance và chiến lược \`PermissionGrantingStrategy\`, một câu SQL \`EXISTS\` tự viết có thể **không tương đương** với ACL engine. Khi đó cần giữ semantics của ACL qua batch \`AclService\`, hoặc xây projection quyền được chứng minh tương đương bằng test.

## 5. Khi nào dùng batch prefetch quyền?

Dùng batch khi cần kiểm tra một **tập object đã bị giới hạn kích thước**, ví dụ danh sách 50 document đã thỏa READ và cần tính thêm \`canEdit\`/ \`canShare\` cho UI; hoặc workflow xử lý 100 object cụ thể với yêu cầu quyết định mỗi item.

Thay vì:

~~~java
// Minh họa: mỗi lần gọi có thể truy vấn DB.
for (Document d : documents) {
    boolean canEdit = permissionEvaluator.hasPermission(auth, d, "EDIT");
    // ...
}
~~~

Tải các quan hệ liên quan một lần rồi tra map/set tại bộ nhớ:

~~~java
// Pseudocode service: repository và DTO do ứng dụng định nghĩa.
List<Document> documents =
        documentRepository.findReadablePage(tenantId, userId, pageRequest);
Set<Long> ids = documents.stream()
        .map(Document::getId)
        .collect(Collectors.toSet());

Map<Long, Set<String>> grantsByDocument =
        shareRepository.findActivePermissionsFor(
                tenantId, userId, ids, clock.instant());

List<DocumentDto> result = documents.stream()
        .map(d -> mapper.toDto(d,
                policy.canEdit(d, membership, grantsByDocument.get(d.getId()))))
        .toList();
~~~

Đây là **mã minh họa không chạy độc lập**; \`findReadablePage\`, \`findActivePermissionsFor\`, \`policy\` và DTO là API ứng dụng tự triển khai. Nếu \`ids\` rỗng, bỏ qua query batch. Luôn giới hạn cả \`tenantId\` và tập \`ids\` khi lấy share; không coi dữ liệu từ tenant khác là grant hợp lệ.

SQL cho bước prefetch:

~~~sql
SELECT s.document_id, s.permission
FROM document_share s
WHERE s.tenant_id = :tenantId
  AND s.recipient_id = :userId
  AND s.document_id IN (:documentIds)
  AND s.revoked_at IS NULL
  AND (s.expires_at IS NULL OR s.expires_at > :now);
~~~

Khi nhận nhiều grant của cùng document, gộp quyền theo chính sách thực tế. Nếu hệ thống có **ACE deny**, không đơn giản gộp bằng phép OR của grant allow.

### 5.1. Vì sao batch hiệu quả?

Với N document, cách kiểm tra per-item có thể là \`1 + N\` round-trip. Nếu hỗ trợ gom tối đa B ID mỗi truy vấn, số statement xấp xỉ \`1 + ceil(N/B)\`. Với 100 item và B=100, chỉ khoảng 2 statement; nếu membership/role có query riêng, cộng phần cố định tương ứng. **Đây là mô hình chi phí, không phải cam kết chính xác với mọi implementation.**

Một query batch khổng lồ cũng không miễn phí: database có giới hạn bind parameter và plan cache, lượng kết quả có thể lớn, và yêu cầu đồng thời có thể gây áp lực bộ nhớ. Đặt kích thước page/batch hợp lý, dùng chunk khi cần, đo query/latency và không gom toàn bộ hàng triệu ACL vào một tập.

### 5.2. Bảo vệ tính nhất quán

- Prefetch phải dùng **cùng tenant, actor, action và mốc thời gian** với lần ra quyết định.
- Nếu quyền có thể bị revoke giữa bước đọc share và thao tác ghi, cần transaction/locking/version hoặc kiểm tra lại quyền ở nơi thực hiện mutation theo threat model; batch prefetch không cho phép bypass quyết định cuối.
- Chỉ cache dữ liệu cần thiết trong phạm vi request/transaction khi chưa có cơ chế vô hiệu hóa chắc chắn.
- Không chỉ xem quyền của object mà bỏ membership (user đã rời tenant vẫn có grant cũ).
- Nếu batch repository lỗi hoặc thiếu dữ liệu, áp dụng **deny by default** thay vì trả true để cải thiện khả dụng.

## 6. Với Spring Security ACL: dùng API đọc nhiều identity

Spring Security có \`AclPermissionEvaluator\` để tích hợp ACL vào \`hasPermission\`. \`AclService\` cung cấp hai nhóm API quan trọng:

~~~java
// Một object: dễ thành N lần gọi nếu dùng trong vòng lặp.
Acl acl = aclService.readAclById(objectIdentity, sids);

// Nhiều object: API hỗ trợ load theo nhóm.
Map<ObjectIdentity, Acl> acls =
        aclService.readAclsById(objectIdentities, sids);
~~~

Đây là **hai đoạn minh họa bên trong service đã có biến và bean tương ứng**. \`objectIdentities\` là danh sách \`ObjectIdentity\` tạo từ type + ID thực, \`sids\` phản ánh principal và authorities đang xét. Khi so sánh quyền phải dùng chính semantics của ACL/ACE, kể cả deny, SID ordering, parent ACL và permission mask; đừng thay thế bằng \`acls.containsKey(id)\` hoặc coi thiếu ACL là được phép.

### 6.1. PermissionCacheOptimizer cho collection filtering

Spring Security có giao diện \`PermissionCacheOptimizer.cachePermissionsFor(Authentication, Collection<?>)\`. Với ACL, \`AclPermissionCacheOptimizer\` có thể batch-load ACL cho collection trước khi đánh giá biểu thức nhiều lần. Nếu dự án dùng method security + \`AclPermissionEvaluator\`, một cấu hình minh họa cho Spring Security 6.x là:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator aclPermissionEvaluator,
            AclService aclService) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(aclPermissionEvaluator);
        handler.setPermissionCacheOptimizer(
                new AclPermissionCacheOptimizer(aclService));
        return handler;
    }
}
~~~

Snippet giả định các import Spring tương ứng và bean \`AclPermissionEvaluator\`/\`AclService\` đã được khai báo; nó không phải ứng dụng Spring Boot độc lập. Kiểm tra API/cấu hình tương ứng với **phiên bản Spring Security đang dùng**, cache và \`LookupStrategy\` thực tế. Chỉ tạo optimizer không bảo đảm giảm query nếu evaluator không dùng cùng cơ chế cache, object identity/SID bị ánh xạ sai hoặc tầng repository khác vẫn truy vấn từng item.

Dù tối ưu ACL cache thành công, \`@PostFilter\` vẫn lọc **sau khi tải dữ liệu** và vẫn không sửa được vấn đề pagination sai do filter sau \`LIMIT/OFFSET\`. Với API list/search có phân trang, ưu tiên query được authorize từ tầng dữ liệu hoặc thiết kế projection quyền được kiểm chứng tương đương.

### 6.2. Cache không thay thế tenant scoping

ACL cache thường khóa theo \`ObjectIdentity\`, SID và thông tin mà lookup strategy sử dụng. Nếu ID chỉ duy nhất trong từng tenant, cần mô hình identity tách biệt tenant để không va chạm cùng một ID giữa A và B. Cũng phải kiểm soát invalidation khi grant bị cấp/thu hồi, membership/role thay đổi, object đổi trạng thái hay owner đổi. TTL dài hoặc kết quả \`ALLOW\` cũ có thể trở thành lỗ hổng quyền truy cập.

Không cache quyết định chỉ với key \`documentId\`; khóa tối thiểu phụ thuộc **actor hoặc SID/authority**, tenant, object identity, action, policy version và thời gian nếu có expiry. Nếu khó chứng minh cache đúng, ưu tiên cache trong phạm vi request và đọc dữ liệu chuẩn từ database.

## 7. Ví dụ Java 17 chạy độc lập: đếm round-trip trước và sau batch

Chương trình sau giả lập database bằng danh sách trong bộ nhớ, nhưng đếm mỗi lời gọi repository như **một truy vấn**. Nó chứng minh nguyên lý \`1 + N\` so với \`1 + 1\`, **không thay thế benchmark SQL thực tế**. Hai thuật toán cùng áp dụng policy đơn giản: user chỉ đọc document thuộc tenant đang xét nếu là owner hoặc được chia sẻ READ.

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class NPlusOneAuthorizationDemo {
    record Document(long id, long tenantId, long ownerId) {}
    record Grant(long tenantId, long documentId, long recipientId) {}

    static class FakeStore {
        private final List<Document> documents;
        private final List<Grant> grants;
        int queries;

        FakeStore(List<Document> documents, List<Grant> grants) {
            this.documents = documents;
            this.grants = grants;
        }

        List<Document> loadCandidates(long tenantId) {
            queries++;
            return documents.stream()
                    .filter(d -> d.tenantId() == tenantId)
                    .toList();
        }

        boolean hasGrant(long tenantId, long documentId, long userId) {
            queries++;
            return grants.stream().anyMatch(g ->
                    g.tenantId() == tenantId
                    && g.documentId() == documentId
                    && g.recipientId() == userId);
        }

        Set<Long> loadGrantedIds(
                long tenantId, Set<Long> documentIds, long userId) {
            queries++;
            return grants.stream()
                    .filter(g -> g.tenantId() == tenantId
                            && g.recipientId() == userId
                            && documentIds.contains(g.documentId()))
                    .map(Grant::documentId)
                    .collect(Collectors.toSet());
        }
    }

    static List<Long> naive(FakeStore db, long tenantId, long userId) {
        List<Document> candidates = db.loadCandidates(tenantId);
        return candidates.stream()
                .filter(d -> {
                    boolean shared = db.hasGrant(tenantId, d.id(), userId);
                    return d.ownerId() == userId || shared;
                })
                .map(Document::id)
                .toList();
    }

    static List<Long> batched(FakeStore db, long tenantId, long userId) {
        List<Document> candidates = db.loadCandidates(tenantId);
        Set<Long> ids = candidates.stream()
                .map(Document::id)
                .collect(Collectors.toSet());
        Set<Long> sharedIds = ids.isEmpty()
                ? Set.of()
                : db.loadGrantedIds(tenantId, ids, userId);
        return candidates.stream()
                .filter(d -> d.ownerId() == userId
                        || sharedIds.contains(d.id()))
                .map(Document::id)
                .toList();
    }

    public static void main(String[] args) {
        List<Document> documents = List.of(
                new Document(101, 10, 7),
                new Document(102, 10, 8),
                new Document(103, 10, 9),
                new Document(104, 10, 8),
                new Document(105, 10, 9),
                new Document(106, 20, 7));
        List<Grant> grants = List.of(
                new Grant(10, 102, 7),
                new Grant(10, 104, 7),
                new Grant(20, 106, 7));

        FakeStore slow = new FakeStore(documents, grants);
        FakeStore fast = new FakeStore(documents, grants);
        List<Long> first = naive(slow, 10, 7);
        List<Long> second = batched(fast, 10, 7);

        if (!first.equals(List.of(101L, 102L, 104L))
                || !first.equals(second)
                || slow.queries != 6
                || fast.queries != 2) {
            throw new AssertionError("Authorization or query count mismatch");
        }

        System.out.println("Authorized IDs: " + second);
        System.out.println("Naive queries: " + slow.queries);
        System.out.println("Batch queries: " + fast.queries);
    }
}
~~~

Lưu thành \`NPlusOneAuthorizationDemo.java\`, dùng JDK 17 trở lên:

~~~bash
javac --release 17 NPlusOneAuthorizationDemo.java
java NPlusOneAuthorizationDemo
~~~

Kết quả chuẩn:

~~~text
Authorized IDs: [101, 102, 104]
Naive queries: 6
Batch queries: 2
~~~

Giải thích: trong tenant 10 có 5 document; \`naive\` gọi một lần \`loadCandidates\` và năm lần \`hasGrant\` (1 + 5 = 6). \`batched\` gọi một lần \`loadCandidates\` và một lần \`loadGrantedIds\` cho toàn bộ ID (2). User 7 sở hữu 101, được chia sẻ 102 và 104; document 106 thuộc tenant 20 dù cũng có grant nên không xuất hiện. Kết quả và thứ tự hai thuật toán bằng nhau.

**Giới hạn chủ ý của demo:** cả hai thuật toán đều tải candidate trước khi lọc trong bộ nhớ, để so sánh query count. Đối với **API danh sách có phân trang hoặc lượng lớn tài liệu**, cần lọc quyền ở database **trước** phân trang như mục 4, không bê nguyên kỹ thuật demo vào production. Production còn phải kiểm tra membership, expiry, revoke, action, lỗi repository và giao dịch.

## 8. Những kỹ thuật hỗ trợ và giới hạn

### 8.1. ORM fetching không tự chữa evaluator N+1

Nếu SQL lặp đến từ truy cập quan hệ lazy như \`document.owner\` hoặc \`document.memberships\`, có thể cân nhắc projection DTO, \`@EntityGraph\`, fetch join cho quan hệ thích hợp, hoặc Hibernate batch fetching. Tuy nhiên:
- \`JOIN FETCH\` collection \`@OneToMany\` kết hợp pagination có thể tạo Cartesian multiplication, warning hoặc phân trang trong bộ nhớ; kiểm tra cách ORM đang xử lý.
- Bật \`hibernate.default_batch_fetch_size\` giúp một số lazy association, **không** tự biến N lần gọi custom repository bên trong \`PermissionEvaluator\` thành một query.
- Eager load mọi ACL/SID cho mọi document có thể tăng dữ liệu, bộ nhớ và SQL join rất lớn.
- Projection và batch phải giữ giới hạn tenant và không trả trường bí mật cho code/response chưa authorize.

### 8.2. Remote PDP hoặc authorization service

Nếu mỗi object gọi một HTTP request tới policy decision point, tối ưu bằng API check-many hoặc truy vấn “authorized IDs” có giới hạn, kết hợp retry/circuit breaker theo yêu cầu nghiệp vụ. Gửi context nhất quán cho từng quyết định: subject, tenant, action, resource attributes, policy version. Nếu API batch trả thiếu một ID, **không mặc nhiên ALLOW**; áp dụng fail closed cho quyết định thiếu hoặc lỗi. Đo cả số request mạng, p95/p99 latency và kích thước payload.

### 8.3. Kiểm tra một object vẫn cần độc lập

Các endpoint GET/PUT/DELETE một document vẫn phải dùng authorization trước khi tiết lộ/sửa object. Tối ưu list endpoint không có nghĩa có thể bỏ \`@PreAuthorize\` hoặc kiểm tra service cho thao tác ghi. Tránh việc controller tải cả entity lẫn quan hệ bí mật rồi mới gọi \`hasPermission\` nếu có thể xác minh ID/tenant trước khi fetch.

### 8.4. Giảm overfetch và tránh query trong serializer

Sau khi authorize, map sang DTO đã có đủ cột cần dùng. Không để Jackson hoặc mapper duyệt quan hệ lazy cho từng item và tái tạo N+1 ở giai đoạn serialize. Với list lớn, dùng projection đúng shape và lấy các cờ quyền trong query hoặc batch; không cho serializer tự gọi \`PermissionEvaluator\`.

## 9. Đo lường đúng cách trước và sau tối ưu

Để chứng minh cải thiện, giữ nguyên dataset, principal, tenant, policy version, điều kiện cache và page size. Đo:

| Chỉ số | Ý nghĩa |
|---|---|
| SQL statement count/request | Dấu hiệu N+1, đặc biệt khi N tăng. |
| Number of ACL lookups / cache hits | Phân biệt giảm truy vấn vì batch với vì đã warm cache. |
| DB time, query plan, rows read | Một query rất nặng chưa chắc tốt hơn nhiều query nhẹ. |
| Request p50/p95/p99 và throughput | Tác động thực tế tới người dùng và hệ thống. |
| Connection pool wait, GC và heap | Ảnh hưởng khi load cả collection và ACL. |
| Authorized IDs và count | Xác nhận tối ưu không làm đổi hành vi bảo mật. |

Có thể bật Hibernate SQL logging cho môi trường test hoặc thu statement count qua Hibernate Statistics/data source proxy. Cần tách query tải document, membership, ACL, lazy association và count để biết nguồn N+1. Một truy vấn trùng lặp trong log chưa chứng minh có N+1 nếu do request khác; gắn request/test correlation ID.

Ví dụ kỳ vọng kiểm thử định hướng (không phải benchmark đã đo):

~~~text
N=10:  baseline ACL queries ~10; batched ACL queries ~1
N=100: baseline ACL queries ~100; batched ACL queries ~1
N=500: baseline ACL queries ~500; batched ACL queries ~ceil(500 / B)
~~~

Điểm quyết định là **độ dốc theo N**. Cho dù số query ban đầu lớn hơn 1 do kiểm tra membership hoặc load count, phần tăng theo số item của ACL nên biến mất hoặc chỉ tăng theo số chunk khi batch. Với SQL có filter quyền trước pagination, số statement thường không phụ thuộc N của trang, nhưng chi phí nội bộ của database vẫn phải tối ưu bằng index/plan.

## 10. Ma trận test về quyền và hiệu năng

Một phép tối ưu chỉ được chấp nhận khi kết quả ALLOW/DENY giống phiên bản trước cho đầy đủ tình huống quan trọng:

| Tình huống | Kỳ vọng | Bằng chứng |
|---|---|---|
| Owner trong tenant A | ALLOW READ | Có ID trong list, đúng đối tượng. |
| User có share READ còn hạn | ALLOW READ | Grant được đọc khi \`expires_at > now\`. |
| User không owner, không grant, PRIVATE | DENY | Không có ID, không tính vào count. |
| User ở tenant B có ID tương tự | DENY | Không lọt list/cached result tenant A. |
| ADMIN A và ADMIN B | Chỉ ADMIN A có quyền trong A | Role scope được kiểm tra đúng. |
| Share bị revoke | DENY ngay sau revoke | Cache bị invalidate hoặc không giữ quyết định cũ. |
| Grant hết hạn đúng tại \`now = expiresAt\` | DENY | Clock cố định, kiểm tra điều kiện biên. |
| VIEWER có WRITE grant nhưng policy EDIT yêu cầu EDITOR | DENY EDIT | Không đồng nhất grant với role. |
| ACL có ACE deny và grant allow | Theo semantics engine | Batch và single \`AclService\` đưa cùng quyết định. |
| ACL parent/inheritance | Theo cấu hình thực tế | Cùng SID/permission mask, không bỏ parent. |
| Page size 20, nhiều item không được phép | Nhận đúng số item hợp lệ tới giới hạn page | Lọc trước pagination, total/count đúng. |
| Request batch rỗng hoặc ACL thiếu | Không lỗi, không tự ALLOW | Không query \`IN ()\` không hợp lệ; fail closed. |
| Mutation bị từ chối sau thay đổi share | Không đổi database | Tránh time-of-check/time-of-use sai. |

### 10.1. Một test query count có ý nghĩa

1. Seed ít nhất 2 tenant, 1 principal, 100 document, grant phân bố không đồng đều (owner, shared, private) và mốc Clock cố định.
2. Chạy cùng một endpoint/permission set với N=10 và N=100; reset counter và kiểm soát warm/cold cache trước mỗi phép đo.
3. Assert danh sách ID chính xác theo oracle được xác định từ fixture, không suy expected từ \`PermissionEvaluator\`.
4. Assert số ACL/query tăng theo **chunk** thay vì theo từng document; không gắn cứng tổng query toàn request nếu framework có query phụ thay đổi hợp lý.
5. Nếu là \`Page\`, kiểm tra content, \`totalElements\`, thứ tự, page kế tiếp và tính cô lập tenant; chạy test trước/sau revoke trong cùng bộ dữ liệu.
6. Dùng query plan/metrics để xác nhận một câu SQL set-based không quét toàn bảng khi dữ liệu tăng lớn.

Không kiểm thử hiệu năng với chỉ một document hoặc chỉ warm cache: hai tình huống đó không thể chứng minh đã loại bỏ N+1 ở đường đi cold cache.

## 11. Kế hoạch thay đổi an toàn trong ứng dụng hiện có

**Bước 1 — Tìm đúng vòng lặp gây truy vấn.** Đánh dấu endpoint và ranh giới method security. Lấy log một request có N document; xác định liệu SQL trùng lặp đến từ \`PermissionEvaluator\`, \`AclService\`, Hibernate lazy association hay HTTP PDP. Không tự mặc định cache là nguyên nhân.

**Bước 2 — Chọn phương án theo ngữ nghĩa dữ liệu.** Với list/search cần phân trang, ưu tiên đưa predicate authorization vào repository và count query. Với danh sách nhỏ/đã giới hạn để tính permission flags, ưu tiên batch prefetch. Với Spring ACL đầy đủ, dùng \`readAclsById\`/optimizer + cache đúng semantics, hoặc thiết kế ACL projection có test chứng minh tương đương.

**Bước 3 — Giữ quyết định nhất quán.** Membership, tenant, owner, action, expiry, revoke, deny ACE và parent ACL phải cho cùng kết quả trước/sau. Không gửi toàn bộ bản ghi không được phép về client để lọc ở UI.

**Bước 4 — Thêm đo lường và regression test.** Query counter, p95 latency, auth matrix và pagination test là bằng chứng. Chạy ở dữ liệu có tỉ lệ cho phép/từ chối thực tế; đánh giá kết quả khi chưa warm cache và khi membership/share đổi.

**Bước 5 — Theo dõi vận hành.** Đặt cảnh báo cho SQL statement count, độ trễ list endpoint, số ACL cache miss và slow queries. Khi thấy độ dốc tăng lại, kiểm tra code mới có thêm \`hasPermission\` hoặc mapper truy cập quan hệ lazy trong loop hay không.

## 12. Checklist và tài liệu tra cứu

Trước khi kết luận đã loại bỏ N+1, cần xác nhận: (1) đã đo được truy vấn lặp; (2) danh sách có authorization trước pagination nếu cần trả Page; (3) count dùng cùng predicate; (4) batch giới hạn tenant/user/action/IDs và xử lý collection rỗng; (5) ACL engine giữ đúng allow/deny, SID và inheritance; (6) cache được vô hiệu hóa khi quyền đổi; (7) test có cross-tenant, revoked, expired, owner, role, deny và Page; (8) hiệu năng cải thiện với N tăng trong điều kiện cache kiểm soát; và (9) thao tác ghi vẫn kiểm tra quyền tại ranh giới thực thi.

Tài liệu Spring Security liên quan:
- Method Security, đặc biệt \`@PostFilter\`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Domain Object Security (ACLs): https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- API \`PermissionEvaluator\`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html
- API \`AclService\`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AclService.html
- API \`PermissionCacheOptimizer\`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionCacheOptimizer.html

**Kết luận kỹ thuật:** kiểm tra quyền trên N object không bắt buộc phải có N round-trip. Với list/search, đẩy predicate quyền xuống database trước pagination; với collection giới hạn hoặc ACL đầy đủ, đọc ACL/grant theo batch và dùng cache đúng phạm vi. Tối ưu chỉ thật sự thành công khi **số truy vấn giảm, kết quả phân trang đúng và ranh giới quyền không đổi**.