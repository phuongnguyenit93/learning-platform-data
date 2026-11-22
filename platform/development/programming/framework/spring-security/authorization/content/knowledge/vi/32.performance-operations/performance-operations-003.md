# Cache quyền, quan hệ và quyết định theo đúng phạm vi

## 1. Vấn đề: cache nhanh nhưng phải giữ đúng ngữ cảnh bảo mật

Trong Spring Security, quyết định "người dùng U có được thực hiện hành động A trên tài nguyên R trong tenant T hay không?" thường cần đọc danh tính đã xác thực, role/permission, quan hệ thành viên, chủ sở hữu, ACL, thuộc tính tài nguyên và quy tắc nghiệp vụ. Tính toán lặp lại có thể tạo nhiều truy vấn, tăng độ trễ và tải cơ sở dữ liệu. Cache giúp tránh công việc lặp lại, nhưng một kết quả `ALLOW` hoặc `DENY` **chỉ có ý nghĩa trong phạm vi và thời điểm đã tính ra nó**.

Ví dụ lỗi nghiêm trọng: Alice được đọc tài liệu `doc-7` và hệ thống cache `true` với khóa chỉ là `doc-7`. Khi Bob yêu cầu cùng ID, cache trả `true` của Alice dù Bob không có quyền. Tương tự, tenant B có thể nhận kết quả của tenant A; quyền `READ` có thể bị dùng cho `DELETE`; hoặc một quyền đã thu hồi tiếp tục có hiệu lực vì kết quả `ALLOW` cũ chưa hết hạn.

Đây là lỗi **dùng lại authorization decision ngoài ngữ cảnh**. Nó có thể gây IDOR/BOLA, truy cập chéo tenant, vượt quyền, truy cập sau thu hồi hoặc lộ dữ liệu thông qua response cache. Một bộ lọc Spring Security hay phương thức `@PreAuthorize` được viết đúng vẫn có thể trở nên vô hiệu nếu tầng cache dùng khóa sai.

Sau bài này, người học cần phân biệt các loại cache, thiết kế scope/key và vòng đời cache, xử lý policy/quan hệ thay đổi, chọn giới hạn nhất quán phù hợp, và viết test chứng minh quyền không bị chia sẻ nhầm.

## 2. Ba tầng cache cần phân biệt

| Tầng | Dữ liệu lưu | Phạm vi điển hình | Điểm dễ sai |
| --- | --- | --- | --- |
| **Permission/grant cache** | Quyền, authority, role mapping hoặc grant từ nguồn đã xác minh | Issuer/subject, tenant, grants revision | Vai trò hay membership bị thu hồi nhưng grant cũ vẫn được dùng |
| **Relationship cache** | Chủ sở hữu, nhóm, quan hệ chia sẻ, quan hệ tài nguyên cha–con | Tenant, actor, relation type, resource, relation revision | Chủ sở hữu/ACL hoặc đường kế thừa quyền đổi mà cache không biết |
| **Decision cache** | Kết luận `ALLOW`/`DENY` cho một hành động | Actor, tenant, resource type/id, action, policy và các version | Trộn kết quả của người dùng, hành động, tài nguyên hoặc thời điểm khác |

Cache permission không tự động cho phép thao tác: role `EDITOR` còn phải được đối chiếu với hành động và tài nguyên. Cache relationship cũng không tự động cấp quyền: việc Alice thuộc nhóm G chưa chứng minh G được publish tài liệu D. Cache decision nguy hiểm nhất khi thiếu key dimension, vì nó tái sử dụng **kết luận cuối** mà không chạy lại policy.

Ngoài ba tầng trên còn có **response/data cache** (ví dụ `DocumentDto` hoặc HTTP response). Kể cả decision cache chính xác, response cache theo URL/ID nhưng bỏ tenant hoặc người dùng có thể trả **nội dung của Alice cho Bob**. Phải xem cả cache dữ liệu và cache ủy quyền, đặc biệt tại API Gateway, CDN, reverse proxy, ORM và service.

## 3. Decision phụ thuộc những thông tin nào?

Có thể xem quyết định là một hàm:

```text
allow = policy.evaluate(
    verifiedPrincipal,
    effectiveTenant,
    resourceTypeAndId,
    action,
    currentOwnershipAndRelationships,
    currentResourceAttributes,
    currentGrants,
    policyVersion,
    relevantEnvironment
)
```

Mỗi yếu tố cần được hiểu đúng:

- **Principal:** định danh đáng tin từ SecurityContext sau quá trình xác thực. Khi dùng nhiều IdP, `issuer + subject` hoặc user ID nội bộ đã ánh xạ giúp tránh trùng `sub` giữa issuer. Nếu có delegation/impersonation, quyết định có thể phụ thuộc cả người thực thi và quyền ủy quyền.
- **Tenant:** workspace/organization hiệu lực mà actor được xác minh membership/quyền. `tenantId` do client chọn ở URL hoặc header chỉ là *selector*, không tự chứng minh quyền.
- **Resource:** `resourceType + resourceId`; cùng ID có thể tồn tại ở nhiều loại tài nguyên hoặc tenant. Cần xác minh tài nguyên thực sự thuộc tenant đang được kiểm tra.
- **Action:** đọc, sửa, xuất dữ liệu, chia sẻ, chuyển chủ, duyệt, xóa có semantics khác nhau. Cache `READ` không dùng lại cho `DELETE`.
- **Attributes/relationships:** owner, trạng thái, sensitivity, ACL, nhóm, quan hệ kế thừa, membership, quyền ủy quyền. Tất cả thay đổi có thể làm đảo decision.
- **Policy:** phiên bản quy tắc RBAC/ABAC/ReBAC và ánh xạ role → permission. Khi logic triển khai hoặc chính sách thay đổi, cache từ policy cũ có thể hết hiệu lực.
- **Environment:** thời gian hiện tại, hạn hiệu lực MFA, IP, device trust, mục đích truy cập hoặc mức rủi ro nếu policy phụ thuộc chúng. Với điều kiện biến đổi liên tục, thường cần TTL đến đúng deadline hoặc không cache decision.

**Điều kiện tái sử dụng an toàn:** hai lần kiểm tra chỉ chia sẻ decision khi mọi thuộc tính có khả năng làm thay đổi kết quả là tương đương và còn hiệu lực theo hợp đồng hệ thống. Chỉ hai request cùng đường dẫn hoặc ID là chưa đủ.

## 4. Thiết kế cache key đúng phạm vi

### 4.1. Key thiếu scope

Ví dụ không an toàn trong Spring Cache:

```java
// MINH HỌA LỖI: Không dùng trong ứng dụng thực.
@Cacheable(cacheNames = "authorizationDecisions", key = "#documentId")
public boolean canOperate(UUID documentId,
                          UUID tenantId,
                          Authentication authentication,
                          String action) {
    return policy.evaluate(authentication, tenantId, documentId, action);
}
```

Dù `policy.evaluate` dùng đủ ngữ cảnh lúc cache miss, kết quả của Alice có thể được Bob lấy lại bởi cùng khóa `documentId`; quyết định của tenant A có thể được dùng cho tenant B, hoặc `READ` bị dùng cho `DELETE`. Đây là lỗi do **key** chứ không nhất thiết do bản thân policy.

### 4.2. Key có ngữ cảnh và freshness

Khóa có thể mô hình hóa như sau:

```text
DecisionKey(
  principalNamespaceOrIssuer,
  stableSubjectId,
  effectiveTenantId,
  resourceType,
  resourceId,
  action,
  grantOrSubjectRevision,
  relationOrMembershipRevision,
  resourceAuthorizationRevision,
  policyRevision,
  relevantEnvironmentFingerprint
)
```

Đây là **mẫu phân tích**, không phải mọi hệ thống bắt buộc có đúng số trường này. Với tài nguyên công khai thật sự, một số yếu tố có thể không ảnh hưởng decision; với policy phức tạp, cần thêm field-level permission, project ancestry, delegation, MFA freshness, purpose, time range hoặc role trong tenant.

Các yêu cầu kiểm tra:

1. **Định danh actor phải do backend xác minh.** Không lấy `role`, `ownerId` hoặc `subject` do client tự khai làm nguồn quyền. Nếu actor được suy từ JWT, phải xác minh signature, issuer, audience, expiry và mapping theo cấu hình resource server; token có chữ ký vẫn có thể chứa quyền đã lỗi thời.
2. **Tenant là scope quyền đã kiểm tra.** Cần xác minh membership và quyền trong tenant được chọn; đồng thời resource phải thực sự ở tenant đó.
3. **Action phân biệt rõ.** Dùng enum hoặc tên canonical. `READ_METADATA` và `READ_PRIVATE_CONTENT` có thể cần hai quyết định; `UPDATE` không đồng nghĩa `PUBLISH`.
4. **Revision phải đến từ nguồn tin cậy.** Nếu owner/ACL/grant thay đổi, revision liên quan phải tăng. Gửi `policyVersion` trong request của client không làm cache an toàn hơn.
5. **Không đưa secrets vào key.** Raw access token, cookie, password hoặc credential không nên nằm trong cache key, log hay metrics. Dùng định danh chuẩn hóa và version đáng tin.
6. **Equality phải theo semantics.** Tránh key object mutable, thiếu `equals/hashCode` ổn định hoặc nối chuỗi không phân biệt được từng field. Java `record` với thuộc tính bất biến là lựa chọn hợp lý.

Với nhiều tenant và resource namespace, một key chỉ gồm `subject + documentId` vẫn sai nếu document ID có thể lặp giữa tenant hoặc action thay đổi.

### 4.3. Version và fingerprint phải đại diện cho đủ phụ thuộc

Có thể thay nhiều trường version bằng một `authorizationFingerprint` nếu fingerprint được backend xây từ **đủ** thuộc tính ảnh hưởng quyền, tăng/đổi theo mọi thay đổi liên quan, và reader biết fingerprint hiện hành với mức nhất quán cần thiết. Nếu fingerprint chỉ phản ánh role trong JWT cũ mà nghiệp vụ yêu cầu thu hồi ngay, nó không giải quyết được stale authorization.

Mọi đường cập nhật phải tuân cơ chế phiên bản: đổi owner, membership, group, ACL, status, policy, quan hệ cha–con. Nếu batch job cập nhật owner mà không tăng revision, cache key dù đầy đủ vẫn có thể trả decision sai.

## 5. Cache ALLOW, DENY và phạm vi thời gian

**Cache ALLOW** mang rủi ro cấp phép trái phép sau revoke/transfer; **cache DENY** có thể khiến quyền mới được cấp vẫn bị từ chối. Có thể chọn TTL khác nhau hoặc không cache một trong hai loại, tùy độ nhạy và tần suất thay đổi. Đừng mặc định DENY luôn vô hại: kết quả khác nhau về timing đôi khi còn tiết lộ tài nguyên tồn tại.

Mô hình freshness thường phối hợp:

| Cơ chế | Được gì? | Không đảm bảo điều gì? |
| --- | --- | --- |
| Cache trong **một request** | Giảm đánh giá lặp, tránh chia sẻ cross-request | Không tự xử lý owner/role đổi trong request |
| Version/revision trong key | Request mới ở revision mới không hit decision cũ | Revision lấy từ nguồn stale thì vẫn sai; key cũ vẫn chiếm bộ nhớ |
| Evict/invalidate chủ động | Giảm thời gian dùng kết quả cũ, hữu ích nhiều node | Notification có thể chậm/mất, fill sau evict có thể hồi sinh stale entry |
| TTL ngắn | Giới hạn thời gian entry tồn tại | TTL không bảo đảm revoke **tức thời** |
| Authoritative freshness gate | Có thể xác minh revision/trạng thái mới trước reuse | Có chi phí đọc/đồng bộ; cần thiết kế nhất quán tới điểm ghi |

Cần định nghĩa **hợp đồng hiệu lực quyền**: thu hồi phải có hiệu lực tức thời hay chấp nhận tối đa một khoảng chậm? Nếu sản phẩm yêu cầu tức thời, chỉ TTL 30–60 giây là không đủ. Với policy phụ thuộc thời gian như quyền hết hạn lúc 15:00 hoặc MFA freshness, entry không được dùng sau deadline dù TTL mặc định chưa hết.

Khi cache lỗi, không tự đổi sang `ALLOW` để giảm lỗi tải. Fallback chỉ được phép theo hợp đồng rõ và vẫn phải thẩm định quyền từ nguồn đáng tin. Nếu không thể đưa ra quyết định an toàn, trả lỗi có kiểm soát hoặc fail closed.

## 6. Spring Security/Spring Cache: cách đặt cache đúng chỗ

Spring Cache hỗ trợ `@Cacheable`, `CacheManager`, Redis/Caffeine adapters và một số cơ chế concurrency tùy provider. Nó **không tự hiểu** rằng thay đổi membership/owner/role phải vô hiệu hóa quyết định nào. Trách nhiệm thuộc về policy service và luồng cập nhật quyền.

Khi dùng method security:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #tenantId, #documentId)")
public DocumentDto read(UUID tenantId, UUID documentId) {
    return documentService.loadDocument(tenantId, documentId);
}
```

Đây là đoạn minh họa bên trong ứng dụng có `@EnableMethodSecurity` và bean `documentPolicy`. Phương thức `canRead` cần lấy actor từ `Authentication` đã xác thực, xác minh tenant/resource và lấy revision liên quan trước khi dùng cache. Không dùng `isAuthenticated()` như điều kiện đủ cho quyền trên từng bản ghi.

Ví dụ cấu trúc rõ ràng với Spring Cache; các interface `VerifiedActorResolver`, `AuthorizationSnapshotStore` và `DocumentPermissionEvaluator` là thành phần **ứng dụng tự định nghĩa**, không phải API mặc định của Spring:

```java
record DecisionKey(
        String issuer, String subject,
        UUID tenantId, String resourceType, UUID resourceId,
        String action, long grantRevision, long relationRevision,
        long resourceRevision, long policyRevision) {}

public boolean canRead(Authentication authentication,
                       UUID tenantId, UUID documentId) {
    VerifiedActor actor = actors.resolve(authentication);
    AuthorizationSnapshot snapshot =
            snapshots.load(actor, tenantId, documentId);

    // Snapshot có thẩm quyền, tenant/resource đúng scope.
    if (snapshot == null) {
        return false;
    }

    DecisionKey key = new DecisionKey(
            actor.issuer(), actor.subject(),
            snapshot.tenantId(), "DOCUMENT", documentId, "READ",
            snapshot.grantRevision(), snapshot.relationRevision(),
            snapshot.resourceRevision(), snapshot.policyRevision());

    Boolean cached = cache.get(key, Boolean.class);
    if (cached != null) {
        return cached;
    }

    boolean allowed = evaluator.canRead(actor, snapshot);
    cache.put(key, allowed);
    return allowed;
}
```

`cache` ở trên là `org.springframework.cache.Cache` đã được cấu hình. Khi cache lưu `Boolean.FALSE`, kiểm tra `cached != null` phân biệt chính xác deny với cache miss. `AuthorizationSnapshot` phải được lấy từ nguồn có thẩm quyền, chứa phiên bản và dữ liệu policy **cùng hợp đồng nhất quán**. Đọc revision trước mỗi hit có chi phí: tối ưu được phép tính ACL/graph nặng không nhất thiết tiết kiệm mọi truy vấn. Cần đo thực tế trước khi triển khai.

**Những giới hạn quan trọng:**

- Một snapshot phiên bản được đọc trước thao tác ghi vẫn có thể bị thay đổi ở transaction khác. Với thao tác nhạy cảm, database phải bảo vệ quyền tại điểm ghi bằng conditional update/optimistic version hoặc khóa/transaction thích hợp. Cache decision không thay thế khóa hay chống TOCTOU.
- Nếu policy phụ thuộc bảng khác, đọc version tài nguyên **không đủ**; cần revision/freshness của membership, ACL hoặc dữ kiện ngoài bản ghi.
- `@Cacheable` dựa trên proxy thông thường có thể không chạy khi gọi nội bộ qua `this.method()`. Test hit/miss thật; đừng phụ thuộc cache để thực thi authorization.
- Caching `Authentication` hoặc `SecurityContext` toàn cục dễ giữ nhầm danh tính request khác. Truyền actor đã xác minh/khóa bất biến đến policy, không chia sẻ request context giữa người dùng.
- Một `tenantId` trong URL hoặc header có thể là tham số hợp lệ để chọn tenant; **không** mặc định đó là quyền truy cập tenant.

## 7. Chương trình Java 17+ minh họa cache sai và cache theo scope

Chương trình độc lập dưới đây sử dụng bộ nhớ để minh họa hai loại key. Nó mô phỏng owner và membership với phiên bản do backend thay đổi. Đây là **mô hình tuần tự**, không bảo đảm atomicity của database thật và không phải mã production để xử lý ghi đồng thời.

Lưu thành tệp `AuthorizationCacheDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class AuthorizationCacheDemo {
    record Document(String tenant, String id, String owner, long version) {}
    record Key(String issuer, String subject, String tenant,
               String resourceType, String resourceId, String action,
               long resourceVersion, long membershipVersion,
               long policyVersion) {}

    private static final Map<String, Document> DOCUMENTS = new HashMap<>();
    private static final Set<String> MEMBERS = new HashSet<>();
    private static final Map<String, Boolean> BAD = new HashMap<>();
    private static final Map<Key, Boolean> GOOD = new HashMap<>();
    private static long membershipVersion = 1L;
    private static long policyVersion = 1L;

    private static String id(String tenant, String document) {
        return tenant + "|" + document;
    }

    private static boolean evaluate(
            String actor, String tenant, String docId, String action) {
        Document doc = DOCUMENTS.get(id(tenant, docId));
        return "READ".equals(action)
                && doc != null
                && doc.tenant().equals(tenant)
                && doc.owner().equals(actor)
                && MEMBERS.contains(actor + "|" + tenant);
    }

    // Sai: dùng chung kết quả của mọi actor và tenant có cùng docId.
    static boolean unsafe(
            String actor, String tenant, String docId, String action) {
        return BAD.computeIfAbsent(docId,
                key -> evaluate(actor, tenant, docId, action));
    }

    static boolean scoped(
            String actor, String tenant, String docId, String action) {
        Document doc = DOCUMENTS.get(id(tenant, docId));
        long version = doc == null ? 0L : doc.version();
        Key key = new Key("trusted-idp", actor, tenant, "DOCUMENT",
                docId, action, version, membershipVersion, policyVersion);
        return GOOD.computeIfAbsent(key,
                ignored -> evaluate(actor, tenant, docId, action));
    }

    static void transfer(String tenant, String docId, String newOwner) {
        String key = id(tenant, docId);
        Document doc = DOCUMENTS.get(key);
        DOCUMENTS.put(key,
                new Document(tenant, docId, newOwner, doc.version() + 1));
    }

    static void revoke(String actor, String tenant) {
        MEMBERS.remove(actor + "|" + tenant);
        membershipVersion++;
    }

    public static void main(String[] args) {
        DOCUMENTS.put(id("t1", "d7"),
                new Document("t1", "d7", "alice", 1L));
        DOCUMENTS.put(id("t2", "d7"),
                new Document("t2", "d7", "bob", 1L));
        MEMBERS.add("alice|t1");
        MEMBERS.add("bob|t1");
        MEMBERS.add("bob|t2");

        System.out.println("Alice unsafe: "
                + unsafe("alice", "t1", "d7", "READ"));
        System.out.println("Bob unsafe: "
                + unsafe("bob", "t1", "d7", "READ"));
        System.out.println("Bob scoped before transfer: "
                + scoped("bob", "t1", "d7", "READ"));
        System.out.println("Alice scoped before transfer: "
                + scoped("alice", "t1", "d7", "READ"));
        System.out.println("Alice in tenant t2: "
                + scoped("alice", "t2", "d7", "READ"));

        transfer("t1", "d7", "bob");
        System.out.println("Alice scoped after transfer: "
                + scoped("alice", "t1", "d7", "READ"));
        System.out.println("Bob scoped after transfer: "
                + scoped("bob", "t1", "d7", "READ"));

        revoke("bob", "t1");
        System.out.println("Bob scoped after revoke: "
                + scoped("bob", "t1", "d7", "READ"));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac AuthorizationCacheDemo.java
java AuthorizationCacheDemo
```

Stdout:

```text
Alice unsafe: true
Bob unsafe: true
Bob scoped before transfer: false
Alice scoped before transfer: true
Alice in tenant t2: false
Alice scoped after transfer: false
Bob scoped after transfer: true
Bob scoped after revoke: false
```

Alice đã tạo `ALLOW` trong cache sai nên Bob nhận nhầm `true`. Với key đủ actor/tenant/action/version, Bob bị chặn trước khi đổi owner, còn Alice được phép. Chuyển owner lên version 2 khiến Alice bị chặn và Bob được phép; thu hồi membership tăng revision làm Bob mất quyền. Tài liệu `d7` ở tenant `t2` không bị lẫn với tenant `t1`.

Trong ứng dụng thực, revision cần có nguồn tin cậy và được cập nhật nhất quán trên tất cả đường thay đổi quyền. Ví dụ dùng biến `membershipVersion` toàn cục chỉ để minh họa; có thể dùng phiên bản theo tenant/subject/quan hệ để tránh làm giảm hit rate không cần thiết. Các read/modify/write đồng thời vẫn cần cơ chế DB để bảo vệ bất biến.

## 8. Invalidation sau thay đổi quyền: thiết kế vòng đời

Với từng policy, lập **dependency map**: các đầu vào nào khiến quyết định đổi, và sự kiện cập nhật nào bắt buộc làm các entry phụ thuộc mất hiệu lực.

| Thay đổi | Hệ quả đối với cache |
| --- | --- |
| Thu hồi role/grant | Tăng subject/tenant grant revision hoặc invalid các quyết định liên quan |
| Thêm/bỏ membership | Tăng membership/relation revision; không cho phép truy cập tenant cũ |
| Chuyển owner | Tăng resource authorization version; làm cũ quyết định của cả owner cũ và mới |
| Thêm/bỏ ACL, group, share | Invalidate quan hệ và mọi quyết định dựa trên nó |
| Tài nguyên đổi trạng thái | Invalidate các action phụ thuộc status, ví dụ EDIT/PUBLISH/DELETE |
| Thay đổi chính sách | Tăng policy revision/namespace để không dùng quyết định do logic cũ tính |
| Thay đổi parent/project | Phản ánh quyền kế thừa trong revision của cây quan hệ |
| Token/session/MFA hết hạn | Áp dụng deadline hoặc kiểm tra revocation/freshness đã định |

Khi quyền thay đổi qua transaction, invalidation phải phối hợp với commit. Không nên phát “revoke thành công” như sự kiện cuối trước khi transaction có thể rollback. Có thể dùng **transactional outbox** để ghi sự kiện trong cùng transaction và phát sau commit, idempotent khi retry. Nhưng outbox/pubsub có thể phát trễ: giữa commit và khi mọi node nhận invalidation vẫn tồn tại cửa sổ stale. Nếu chính sách yêu cầu thu hồi **tức thời**, cần thêm authoritative freshness gate hoặc cơ chế consistency chặt hơn.

### Race cần thử

**Cache fill sau khi evict:** luồng A đọc quyền cũ rồi tính lâu; luồng B thu hồi quyền, commit và evict; luồng A ghi lại `ALLOW` cũ **sau evict**. Chỉ eviction theo key cố định không giải quyết được race này. Dùng revision/epoch trong key, kiểm tra revision trước publish hoặc cơ chế đồng bộ thích hợp.

**Owner A → B → A:** chỉ so owner ID không đủ để biết request dựa trên snapshot cũ; revision tăng đơn điệu giúp phân biệt epoch nếu chính sách chống stale cần điều đó.

**Policy deploy nhiều phiên bản:** node cũ và node mới có logic policy khác nhau nhưng dùng Redis chung; nếu không phân biệt policy revision, kết quả cũ có thể được dùng với logic mới.

**Distributed local caches:** instance A và B đều lưu ALLOW; chỉ evict một instance không cập nhật instance khác. Cần kiểm thử invalidation fanout, event mất/trễ, reconnect và fallback.

**Thời gian:** quyền hết hạn lúc 10:00 nhưng cache còn TTL 30 phút; entry không được còn hiệu lực sau 10:00. Một số policy theo IP, device hoặc mức rủi ro không phù hợp với decision cache dài hạn.

## 9. Kiểm thử đủ cả tính đúng và hiệu năng

Không chỉ test policy lúc **cache miss**. Mỗi trường hợp cần khởi tạo data, tạo cache hit thật, sau đó thay đổi một yếu tố scope hoặc dữ liệu quyền và quan sát kết quả. Có thể dùng Spring Security test với MockMvc để kiểm tra principal/authority ở web layer, Testcontainers với DB tương tự production để kiểm tra transaction, và metrics/spy cache/repository để chứng minh hit hoặc miss.

| Ca test | Cách tạo tình huống | Điều cần assert |
| --- | --- | --- |
| Cross-subject | Alice READ D tạo ALLOW; Bob READ D | Bob không hưởng cache của Alice |
| Cross-tenant | ID giống nhau ở tenant A/B | Tenant B không dùng decision/response của A |
| Cross-action | READ ALLOW, DELETE DENY | DELETE không lấy kết quả READ |
| Cross-resource-type | Document 42 và Invoice 42 | Không va chạm key |
| Role revoked | Warm ALLOW rồi xóa quyền | ALLOW cũ không vượt cam kết hiệu lực |
| Membership revoked | Warm ALLOW rồi loại actor khỏi tenant | Không truy cập tenant đã rời |
| Owner transferred | Alice → Bob, có entry ALLOW của Alice | Alice bị từ chối; Bob theo quyền hiện hành |
| ACL/group changed | Thu hồi chia sẻ hoặc đổi nhóm | Cache quan hệ/decision được làm mới |
| Resource status changed | DRAFT → LOCKED | WRITE/PUBLISH bị chặn dù actor vẫn là owner |
| Policy revision changed | Thay role matrix/logic policy | Không dùng decision policy cũ |
| DENY rồi cấp quyền | Bob trước không được đọc, sau được cấp | DENY cũ không chặn quá thời hạn cho phép |
| Time-expired grant | Quyền hết hạn khi TTL còn | Không ALLOW sau deadline |
| Fill race | Read cũ → revoke+evict → cache fill cũ | Không hồi sinh ALLOW đã thu hồi |
| Multi-instance | A/B warm cache, C revoke | Các instance tuân hợp đồng consistency |
| Cache outage | Redis bị lỗi/timeout | Không tự động ALLOW, có fallback/lỗi rõ |
| Valid hit | Cùng actor/tenant/action/revisions | Hit đúng và kết quả giống policy thuần |
| Impersonation/delegation | Actor gốc và actor thay mặt có context khác | Không trộn decision thiếu thông tin delegation |
| Response cache | Cached body chứa dữ liệu riêng | Không trả nội dung cho actor/tenant khác |

Đọc lại dữ liệu từ transaction mới và xác minh trạng thái owner, ACL, quyền và side effect. Với write, cần test tình huống kiểm tra quyền xong thì owner/revocation thay đổi trước update: đồng bộ thứ tự bằng `CountDownLatch`/barrier và commit thật; không dùng `Thread.sleep` làm bằng chứng. Kiểm thử phải xác nhận **câu lệnh ghi hoặc transaction** giữ bất biến, dù cache từng cho ALLOW.

Một test chỉ dùng mock repository trả DENY không chứng minh cache invalidation hoạt động khi DB commit và các node có dữ liệu cũ. Một test chỉ assert response 403 mà không xác minh hit/miss cũng có thể đúng ngẫu nhiên vì code luôn miss cache. Test đầy đủ phải có cả luồng hợp lệ để tránh phương án vô tình từ chối mọi người.

## 10. Theo dõi vận hành và lựa chọn tối ưu

Cache authorization chỉ đáng giá khi **lợi ích được đo** và độ nhất quán đáp ứng cam kết bảo mật. Cần quan sát:

- Hit rate theo loại policy/action/resource, tách permission, relation và decision cache.
- Thời gian kiểm tra quyền p50/p95/p99; DB query count và thời gian lookup relationship.
- Memory/entry count, eviction, cardinality và tần suất cache miss hàng loạt (stampede).
- Độ trễ invalidation giữa commit và khi node dùng revision mới; lỗi tiêu thụ event.
- Cache backend availability, timeout, số lần fallback/fail closed.
- Số trường hợp revision mismatch, stale result và test/alert nghi ngờ cross-tenant.

Tránh gắn email, ID người dùng, resource ID hoặc token thật làm label metrics vì cardinality và lộ dữ liệu. Với logging nghiệp vụ được kiểm soát quyền, có thể lưu actor ID/tenant ID đã xác minh, action, decision source (hit/miss), policy revision và correlation ID, theo chính sách retention.

Trước khi cache quyết định dài hạn, thử những biện pháp đơn giản hơn: thêm index hợp lý, giảm N+1 query, query theo tenant/owner, batch lookup grant, memoize trong phạm vi request, gom quan hệ qua phép truy vấn được tối ưu. Nếu để dùng decision cache mà mỗi hit vẫn phải đọc nhiều revision từ DB, đo xem có giảm thời gian thật không. Redis có round-trip mạng; Caffeine local nhanh hơn nhưng khó đồng bộ nhiều instance. Không có provider nào tự sửa thiếu key dimension.

### Các lỗi phổ biến cần tránh

- Dùng `resourceId` làm key duy nhất; hoặc khóa chỉ có actor nhưng không có tenant/action.
- Lấy `tenantId`, `role`, `ownerId` do client tự khai như authority trước khi đọc cache.
- Coi `@Cacheable` như công cụ authorization và bỏ kiểm tra quyền khi ghi database.
- Evict một node rồi mặc định mọi node đã cập nhật.
- Dùng TTL như lời hứa thu hồi tức thời.
- Để key chứa trạng thái mutable hoặc token nhạy cảm.
- Không tăng revision ở đường batch, migration, admin hoặc message consumer.
- Chỉ kiểm thử ALLOW, không kiểm thử DENY sau khi cấp quyền.
- Cache nguyên HTTP response theo URL dù dữ liệu khác nhau theo người dùng/tenant.
- Không kiểm tra proxy/self-invocation của Spring Cache khiến cache không chạy như kỳ vọng.

## 11. Tiêu chí nghiệm thu và bài tập tự kiểm tra

Một thiết kế cache authorization được chấp nhận khi: (1) cùng scope hợp lệ có thể tái sử dụng quyết định; (2) đổi principal, tenant, action, resource type/id hoặc dữ kiện quyền không dùng nhầm ALLOW/DENY; (3) version/invalidation và multi-instance tuân hợp đồng thu hồi; (4) lỗi cache không chuyển thành cấp quyền; (5) thao tác ghi nhạy cảm vẫn có cơ chế DB/transaction chặn TOCTOU; (6) hit rate và latency được đo để chứng minh lợi ích.

Với hành động rủi ro cao như chuyển chủ, gán role quản trị, xuất dữ liệu nhạy cảm hoặc phê duyệt, ưu tiên kiểm tra quyền tại điểm thực thi và cân nhắc **không cache ALLOW xuyên request** nếu không có cách chứng minh freshness. Với quyền đọc ít biến động và có cam kết staleness rõ, cache scoped là lựa chọn có thể hợp lý.

Câu hỏi cuối: **Nếu Alice đã nhận ALLOW với tenant T, tài nguyên R, hành động READ, điều gì ngăn Bob dùng lại kết quả đó; và khi owner, membership hoặc policy đổi, cơ chế nào bảo đảm cache hiện tại không còn cấp quyền sai?** Câu trả lời phải chỉ ra được cả phạm vi khóa, nguồn revision và thời điểm hiệu lực thực tế.
