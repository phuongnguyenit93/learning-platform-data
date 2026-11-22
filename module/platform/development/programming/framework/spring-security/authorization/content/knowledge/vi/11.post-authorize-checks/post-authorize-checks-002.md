# Kiểm tra quyền sở hữu khi đối tượng chỉ có sau truy vấn

> **Module:** Spring Security - authorization  
> **Nhóm kiến thức:** Kiểm tra sau phương thức  
> **Mục tiêu:** Hiểu khi nào phải đánh giá quyền sau khi truy vấn trả về object, cách `@PostAuthorize` và `returnObject` hoạt động trong Spring Security Servlet, cách kết hợp vai trò/authority với owner–tenant–ACL, lý do post-authorization không phù hợp làm chốt duy nhất cho lệnh ghi, và cách kiểm thử để không tạo lỗ hổng IDOR/BOLA.

## 1. Vấn đề: chưa có object thì chưa biết ai sở hữu

Giả sử API đọc tài liệu:

```http
GET /api/documents/42
Authorization: Bearer <access-token>
```

Controller chuyển số `42` xuống service:

```java
public DocumentView readDocument(long documentId) {
    return repository.findViewById(documentId)
        .orElseThrow(DocumentNotFoundException::new);
}
```

Tại thời điểm nhận tham số, ứng dụng chỉ biết **ID**. Muốn xác định owner của tài liệu 42, phải truy vấn database hoặc nguồn dữ liệu tin cậy để biết:
- `ownerUserId` thực tế là ai;
- `tenantId`/organization chứa document;
- tài liệu có bị khóa hay lưu trữ không;
- có ACL/delegation cho người khác xem không.

Một cách làm của Spring Security là cho method chạy để tải object rồi dùng `@PostAuthorize` so sánh thuộc tính của kết quả với actor:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentView readDocument(long documentId) {
    return repository.findViewById(documentId)
        .orElseThrow(DocumentNotFoundException::new);
}
```

Điều kiện `returnObject.ownerId == authentication.name` chỉ là một **minh họa đơn giản**: nó đúng khi `ownerId` trên DTO là một property đáng tin và dùng cùng hệ ID với `authentication.name`. Trong đa số hệ thống thật, nên dùng một bean policy kiểm tra actor ID chuẩn hóa, tenant, ACL và trạng thái.

**Điểm quan trọng nhất:** `@PostAuthorize` cho phép **quyết định liệu kết quả có được trả cho caller không**, nhưng **method body đã chạy** trước khi phép kiểm tra đó diễn ra.

## 2. Phân biệt ba thời điểm bảo vệ

```text
HTTP request / message / bean call
          |
          v
Spring-managed service proxy
          |
          v
[1] @PreAuthorize
    Có authority/chức năng cần thiết không?
          |
          | DENY -> method body KHÔNG chạy
          v
    Method body: query DB tạo DocumentView
          |
          v
[2] @PostAuthorize
    returnObject thuộc actor/tenant được phép không?
          |
          | DENY -> không trả result cho caller
          v
    Caller nhận result
          |
          v
[3] Những use case cần thay đổi dữ liệu
    phải có object policy TRƯỚC side effect
```

| Thành phần | Thời điểm | Dữ liệu có sẵn | Bảo vệ tốt cho |
| --- | --- | --- | --- |
| `@PreAuthorize` | Trước khi method chạy | Authentication và method arguments | Chặn thiếu permission, kiểm tra ID bằng policy service nếu cần |
| `@PostAuthorize` | Sau khi method tạo kết quả | Authentication, arguments và `returnObject` | Kiểm tra owner/tenant/ACL trên một object đọc từ nguồn tin cậy |
| `@PostFilter` | Sau khi method trả collection/stream hỗ trợ | Từng `filterObject` trong tập trả về | Lọc phần tử không được phép; cần cân nhắc hiệu năng/phân trang |
| Domain policy trong service | Tại điểm dùng entity, thường trong transaction | Entity thực, actor, trạng thái đồng bộ | Write/approve/delete và quy tắc owner/tenant phức tạp |
| Query có scope | Ngay khi lấy dữ liệu | Tenant ID, actor ID, grants, visibility | Tránh tải cả dữ liệu không được phép; danh sách/exports |

`@PostAuthorize` và `@PostFilter` không phải một. Một cái **cho phép/từ chối toàn kết quả của method**, một cái **lọc các phần tử** của kết quả. Với một document đơn, `@PostAuthorize` là lựa chọn dễ hiểu khi chỉ biết owner sau khi truy vấn.

## 3. @PostAuthorize hoạt động nội bộ thế nào?

Khi bật Spring method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Spring Security cài đặt các method-security advisors thông qua Spring AOP. Đối với `@PostAuthorize` trong kiến trúc `AuthorizationManager` hiện đại:
- `AuthorizationManagerAfterMethodInterceptor` nhận lời gọi đã hoàn tất và kết quả trả về.
- `PostAuthorizeAuthorizationManager` dùng expression handler để kiểm tra biểu thức SpEL.
- `returnObject` đại diện cho kết quả method trả về.
- Nếu decision từ chối, framework thường ném `AccessDeniedException`; trong luồng HTTP được cấu hình đúng, phía web có thể chuyển thành 403 cho người đã xác thực.
- Nếu được phép, kết quả tiếp tục tới caller.

Mô tả trên là đường mặc định thường gặp trong Spring Security 6.5 Servlet; một ứng dụng có thể custom advisors, exception handling, method security và fallback behavior. Khi gọi service ngoài HTTP, ví dụ job hoặc message listener, exception có thể cần được xử lý riêng; không mặc định sẽ có “HTTP 403” nếu không có HTTP request.

**Spring Boot Starter Security không tự bật method security**. Phải xác nhận `@EnableMethodSecurity` tồn tại trong application context được dùng khi chạy.

## 4. Ví dụ chính thức và cách diễn giải đúng

Spring Security minh họa quy tắc:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Account readAccount(Long id) {
    return accountRepository.findById(id).orElseThrow();
}
```

Giả sử phương thức trả `Account` có property `owner`, SpEL sẽ đánh giá:
- `returnObject`: `Account` đã lấy từ nguồn tin cậy;
- `returnObject.owner`: owner property của Account;
- `authentication.name`: tên principal hiện hành.

Nếu hai giá trị bằng nhau, kết quả có thể đi tiếp; nếu khác nhau, method-security từ chối. Đây là một cách ngăn **Insecure Direct Object Reference (IDOR)**: người có thể đoán ID account không mặc định được nhận tài khoản của người khác.

Nhưng đừng áp dụng mù quáng:
- `authentication.name` có thể là email/username/OIDC sub, còn `Account.ownerId` là UUID.
- Owner có thể là team hoặc organization, không phải một username.
- Actor có thể được ACL READ dù không phải owner.
- Owner có thể đang ở tenant khác hoặc tài liệu bị khóa.
- DTO có thể được xây từ input không tin cậy thay vì entity thật.
- Một response 403 không chứng minh dữ liệu đã không bị ghi log/cache trước post-check.

**Vì vậy hãy chuyển từ phép so sánh một thuộc tính sang một object policy có hợp đồng rõ ràng khi nghiệp vụ cần.**

## 5. Một cấu hình đọc thực tế: pre-check chức năng và post-check object

Ví dụ service Spring Security Servlet:

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentQueryService {

    private final DocumentRepository documents;

    public DocumentQueryService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize(
        "returnObject != null and "
        + "@documentAccess.canRead(authentication, returnObject)"
    )
    public DocumentView readDocument(long id) {
        return documents.findViewById(id)
            .orElseThrow(DocumentNotFoundException::new);
    }
}
```

**Đây là snippet tích hợp**, cần `DocumentRepository`, `DocumentView`, `DocumentNotFoundException` và bean `documentAccess` do ứng dụng xây dựng; chưa bao gồm controller, authentication, DB hay error handler.

Giải thích từng chặng:

1. `@PreAuthorize("hasAuthority('document:read')")` ngăn người không có quyền đọc chức năng gọi vào repository.
2. Method truy vấn document bằng ID, tạo `DocumentView`.
3. `@PostAuthorize` nhìn vào `returnObject`; nếu object null hoặc policy không cho phép, kết quả bị từ chối.
4. `documentAccess.canRead` đánh giá principal với **owner/tenant/ACL/trạng thái của object thật**.
5. Chỉ sau khi cả hai chốt ALLOW, caller mới nhận `DocumentView`.

**Tại sao dùng cả pre và post?** Post-check xử lý quyền trên object mà chỉ biết sau query; pre-check rẻ và giúp tránh tải dữ liệu cho actor hoàn toàn thiếu chức năng. Vì `@PostAuthorize` chạy sau body, không được cho body thực hiện ghi hoặc external side effect.

## 6. Bean policy kiểm tra owner, tenant và quyền theo tổ chức

Một bean policy minh họa:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccess {

    private final ActorResolver actorResolver;

    public DocumentAccess(ActorResolver actorResolver) {
        this.actorResolver = actorResolver;
    }

    public boolean canRead(
            Authentication authentication, DocumentView document) {
        if (authentication == null || document == null
                || !authentication.isAuthenticated()) {
            return false;
        }

        Actor actor = actorResolver.requireActor(authentication);

        // Không chấp nhận tài liệu ở tenant khác.
        if (!actor.activeTenantId().equals(document.tenantId())) {
            return false;
        }

        // Business policy có thể cấm đọc tài liệu bị khóa.
        if (document.readLocked()) {
            return false;
        }

        // Owner có quyền đọc, nếu các điều kiện trước đã thỏa.
        if (actor.id().equals(document.ownerId())) {
            return true;
        }

        // Permission riêng, chỉ cho phép đọc trong cùng tenant.
        return actor.hasAuthority("document:read:tenant")
            && actor.canUseTenantWideRead();
    }
}
```

`Actor`, `ActorResolver`, `DocumentView` và các methods của chúng là **domain contracts minh họa**, không phải class có sẵn của Spring Security. Triển khai thật có thể cần kiểm tra ACL READ, delegation, classification, project membership, expiry và business state.

Một vài bất biến:
- `actorResolver` phải lấy identity/active tenant từ Authentication **và membership đã xác minh**, không từ `X-Tenant-Id` do client gửi rồi tin ngay.
- `document.ownerId`/`document.tenantId` nên đến từ bản ghi server đã tải, không từ request DTO mà client tự khai.
- `document:read:tenant` là capability được cấp có chủ đích, không mặc định từ `ROLE_ADMIN`.
- Nếu actor có role hierarchy, `actor.hasAuthority` phải có hợp đồng rõ là authority trực tiếp hay đã mở rộng; bean policy tự viết không tự đọc mọi `RoleHierarchy` bean.
- Với object không tồn tại, service có thể ném not-found trước post-check; phải quyết định cách thể hiện 404/403 nhất quán với chống enumeration.

## 7. Tại sao ID từ URL không phải bằng chứng sở hữu?

HTTP:

```http
GET /api/documents/42
GET /api/documents/43
```

Nếu controller chuyển ID thẳng xuống:

```java
DocumentView read(long id) {
    return repository.findViewById(id)
        .orElseThrow();
}
```

Client biết hoặc đoán ID 43 không có nghĩa client được quyền đọc nó. IDOR/BOLA xuất hiện khi hệ thống chỉ kiểm tra authentication hoặc quyền đọc chung, không đối chiếu object.

So sánh hai cách:

**Sai: kiểm tra owner do caller tự khai**

```java
@PreAuthorize("#ownerId == authentication.name")
public DocumentView readDocument(
        long id, String ownerId) {
    return repository.findViewById(id).orElseThrow();
}
```

Caller có thể gửi `ownerId` bằng tên chính họ trong khi `id` thuộc người khác.

**Tốt hơn trong read-only use case: kiểm tra owner thật sau query**

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("@documentAccess.canRead(authentication, returnObject)")
public DocumentView readDocument(long id) {
    return repository.findViewById(id)
        .orElseThrow();
}
```

Như vậy `returnObject` là đối tượng đã lấy từ DB, policy có thể đọc owner thật. Nhưng lưu ý **object đã được tải**, nên với hệ thống dữ liệu rất nhạy cảm vẫn nên hạn chế query theo scope trước khi tạo result.

## 8. Độ tin cậy của returnObject

`returnObject` chỉ đáng tin đến mức **nguồn tạo ra nó đáng tin**.

Ví dụ không an toàn:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public DocumentView unsafeRead(
        long id, String claimedOwnerId) {
    // DTO owner được lấy từ tham số client, không từ DB!
    return new DocumentView(id, claimedOwnerId, "content");
}
```

Nếu ownerId không phải trường lấy từ entity thật, post-check chỉ xác minh caller **tự khai** tên của mình; vẫn có thể cho phép lộ nội dung lấy theo ID khác. Chốt “sau method” không tự biến dữ liệu giả mạo thành dữ liệu tin cậy.

Trong thiết kế tốt:
- Entity truy vấn bằng ID có tenant scoping.
- Owner/tenant/ACL từ DB hoặc service tin cậy.
- DTO mapping không nhận ownerId từ HTTP body.
- Policy không dùng dữ liệu đã được client đưa vào cache hoặc mock khác như chân lý.
- Thông tin owner là canonical ID có kiểu ổn định; principal name có thể không cùng kiểu.

Với database projection hoặc DTO view, đảm bảo query map đầy đủ trường security-sensitive. Nếu một query cố tình không lấy `ownerId` vì tối ưu, post-check không thể đoán owner; cần đổi query/policy.

## 9. So sánh một người sở hữu với nhiều người được chia sẻ

Một document có thể có:
- owner trực tiếp;
- nhóm sở hữu;
- ACL READ cho người khác;
- quyền đọc do project membership;
- quyền tenant-wide cho vai trò hỗ trợ;
- trạng thái PUBLIC;
- lệnh cấm đọc theo classification;
- grant hết hạn hoặc bị thu hồi.

`@PostAuthorize("returnObject.ownerId == authentication.name")` chỉ giải quyết một quy tắc **owner-only**. Nếu business hỗ trợ share, nó có thể deny user đúng quyền chia sẻ. Khi policy phức tạp:

```java
@PostAuthorize(
    "@documentAccess.canRead(authentication, returnObject)"
)
```

Lúc này `documentAccess` đánh giá **cùng một policy** như các entry point khác và có thể unit-test độc lập.

Một mô hình khả dĩ:

```text
canRead(actor, document)
  = actor has document:read
    AND document belongs to authorized tenant
    AND document state permits read
    AND (
      document is public under policy
      OR actor is owner
      OR ACL READ for actor
      OR membership-based project grant
      OR explicit tenant-wide read permission
    )
```

**Điều kiện tenant và state nằm ngoài nhóm OR** nếu mọi cách đọc đều phải tuân thủ chúng. Viết sai ngoặc có thể khiến “owner OR admin” bỏ qua tenant boundary.

## 10. Tenant phải được kiểm tra trước khi cho phép owner

Giả sử:
- Bob có `document:read`, active tenant A.
- Document 44 có `ownerId=bob` nhưng thuộc tenant B.

Một check chỉ so ownerId sẽ cho qua:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
```

Điều này có thể vi phạm active-tenant policy. Bản an toàn hơn:

```java
@PostAuthorize(
    "@documentAccess.canRead(authentication, returnObject)"
)
```

Và trong bean policy:
1. Xác minh active tenant từ actor tin cậy.
2. So document tenant đã truy vấn với active tenant.
3. Kiểm tra data classification/state.
4. Kiểm tra owner/ACL/tenant-wide grant.

Không cần áp dụng cùng quy tắc cho mọi sản phẩm: một số hệ thống cố ý cho người dùng đọc dữ liệu mình sở hữu ở nhiều tenant thông qua một grant rõ. Nhưng **cơ chế cho phép cross-tenant phải là policy tường minh**, không phát sinh ngầm từ một phép so sánh tên.

## 11. 404, 403 và dữ liệu không tồn tại

Với:

```java
return repository.findViewById(id)
    .orElseThrow(DocumentNotFoundException::new);
```

Nếu ID không tồn tại, method ném exception **trước khi tạo returnObject**. `@PostAuthorize` không có object bình thường để kiểm tra. Error mapping quyết định response có thể là 404.

Nếu ID tồn tại nhưng người dùng không phải owner, post-check có thể ném `AccessDeniedException`, thường dẫn tới 403 qua HTTP security exception handling.

Điều này có thể tiết lộ sự khác nhau giữa:
- ID không tồn tại;
- ID tồn tại nhưng thuộc người khác.

Đối với API cần chống dò ID/enumeration, cân nhắc:
- Query trong scope actor/tenant khiến không tồn tại và không có quyền nhìn giống nhau.
- Map error theo contract an toàn, không làm lộ owner hoặc metadata riêng.
- Không tiết lộ “owner là alice” trong deny message.
- Rate limiting/audit với truy vấn ID bất thường.
- Không dùng một giá trị response giả từ post-check để che tất cả lỗi mà không xem hành vi endpoint.

**Không kết luận rằng mọi unauthorized resource phải trả 404.** Đó là lựa chọn sản phẩm và security policy; cần nhất quán và có test. Điều quan trọng là không rò dữ liệu ngoài ý định.

## 12. Null returnObject và Optional

Một method có thể trả `null`, `Optional<Document>` hoặc exception. Mẫu:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
```

không an toàn với null; truy cập `ownerId` khi `returnObject==null` có thể gây lỗi SpEL. Nếu contract trả `null` như “không tìm thấy”, có thể viết rõ:

```java
@PostAuthorize(
    "returnObject == null or "
    + "@documentAccess.canRead(authentication, returnObject)"
)
```

Nhưng biểu thức trên nghĩa là **cho phép null result đi qua**; hãy chắc chắn đó là contract hợp lệ. Nếu muốn fail closed, biểu thức `returnObject != null and ...` từ chối null, có thể khiến “not found” trở thành “access denied” thay vì error mà API mong muốn.

**Khuyến nghị cho một GET by ID:** trả DTO khi tìm thấy, ném `DocumentNotFoundException` khi không tìm thấy, sau đó post-authorize DTO không null. Kết quả giúp logic dễ test và rõ nghĩa.

Với `Optional<Document>`, Spring Security có những API xử lý return object/proxy khác nhau theo phiên bản, nhưng **đừng mặc định** `returnObject.ownerId` sẽ tự unbox `Optional` đúng ý định. Xác nhận kiểu object trong expression hoặc dùng policy helper nhận toàn kết quả đúng type; tốt hơn tránh Optional ở boundary có post-check owner phức tạp nếu không cần.

### Null-safe không bằng authorization

Một biểu thức dùng null-safe operator/guard chỉ tránh exception hoặc quyết định null case; nó không xác minh owner/tenant. Đừng xem `returnObject != null` là permission test.

## 13. @PreAuthorize và @PostAuthorize có thể dùng cùng nhau

Ví dụ:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "returnObject != null and "
    + "@documentAccess.canRead(authentication, returnObject)"
)
public DocumentView readDocument(long id) {
    return repository.findViewById(id).orElseThrow();
}
```

Hai annotation là **hai loại interceptor**, không phải cùng một loại annotation ghi đè. Ở flow mặc định:
- Pre-check DENY ⇒ method body không chạy, không có post-check kết quả bình thường.
- Pre-check ALLOW ⇒ method body chạy.
- Post-check DENY ⇒ kết quả không được trả cho caller.
- Cả hai ALLOW ⇒ caller nhận kết quả.

Một method đọc có thể hợp lệ khi lấy entity rồi quyết định hậu kiểm. Với method có side effect, cách bố trí này **chưa đủ** nếu pre-check chỉ kiểm tra permission chung mà post-check mới kiểm tra owner sau khi update.

Một điểm performance: vì pre-check có thể ngăn query từ đầu cho user không có authority, đặt một pre-check rẻ và rõ thường hữu ích. Nhưng post-check vẫn có thể phải đánh giá resource-specific permissions.

## 14. Vì sao post-authorization không nên là chốt chính cho write?

Đoạn code **nguy hiểm**:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
@Transactional
public Document renameDocument(long id, String title) {
    Document doc = repository.findById(id).orElseThrow();
    doc.rename(title);
    return doc;
}
```

Method có thể sửa managed entity trước khi security expression được đánh giá. Tùy thứ tự transaction advisor và post-authorization advisor:
- DB transaction có thể chưa commit tại thời điểm post-check hoặc có thể đã commit.
- Rollback phụ thuộc transaction boundaries, exception configuration và cách mutation được lưu.
- External side effect (HTTP call, email, message publish) không mặc định bị undo dù DB rollback.
- Log, cache hoặc event có thể đã nhận dữ liệu thay đổi.
- Không được bảo đảm rằng exception sau method luôn làm toàn bộ hệ thống quay về trạng thái cũ.

Tài liệu Spring Security **không khuyến nghị `@PostAuthorize` cho các class ghi database** và lưu ý phối hợp `@Transactional` với method security đòi hỏi hiểu thứ tự advisors. Đừng dựa vào thứ tự interceptor như “biện pháp mặc định” thay cho pre-check trên object.

**Mẫu an toàn:** tải entity, kiểm tra authorization trước mutation, cập nhật trong transaction có isolation/locking phù hợp. Với tình huống chỉ có owner sau DB query, việc kiểm tra owner nằm **trong method sau truy vấn nhưng trước khi ghi** là lựa chọn chuẩn.

## 15. Đọc trước, xác minh quyền, rồi mới ghi

Ví dụ lệnh đổi tên:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {

    private final ActorResolver actors;
    private final DocumentRepository repository;
    private final DocumentPolicy policy;

    public DocumentCommandService(
            ActorResolver actors,
            DocumentRepository repository,
            DocumentPolicy policy) {
        this.actors = actors;
        this.repository = repository;
        this.policy = policy;
    }

    @PreAuthorize("hasAuthority('document:rename')")
    @Transactional
    public void renameDocument(long id, String newTitle) {
        Actor actor = actors.requireAuthenticatedActor();

        Document document = repository
            .findForUpdateWithinTenant(id, actor.activeTenantId())
            .orElseThrow(DocumentNotFoundException::new);

        if (!policy.canRename(actor, document)) {
            throw new AccessDeniedException("Not permitted");
        }

        document.rename(newTitle);
    }
}
```

**Đây là snippet tích hợp**, không phải chương trình Java 17 standalone. `Actor`, `ActorResolver`, `Document`, `DocumentRepository`, `DocumentPolicy` và exception là contract của ứng dụng. Repository phải triển khai thật `findForUpdateWithinTenant` với JPA/SQL và transaction/locking phù hợp; tên method tự nó không tạo lock.

Cấu trúc an toàn:
1. Pre-check quyền chức năng trước body.
2. Đọc object theo tenant đã được xác minh từ actor.
3. Policy owner/ACL/state trên **entity thật**.
4. Chỉ sau ALLOW mới gọi `rename`.
5. Commit transaction và audit theo thiết kế.

Không thay đoạn policy bằng `if (hasRole("ADMIN")) return;` trừ khi có explicit capability tenant-wide cùng boundary/approval đúng; ROLE_ADMIN không tự chứng minh quyền trên mọi document.

## 16. TOCTOU: bảo vệ tại thời điểm sử dụng dữ liệu

Ngay cả khi đã làm:

```text
T1: read document, thấy owner là Alice
T2: policy ALLOW Alice
T3: transaction khác chuyển owner cho Bob
T4: thực hiện write dựa trên owner cũ
```

thì hệ thống có nguy cơ **time-of-check/time-of-use (TOCTOU)**. `@PostAuthorize` trên read riêng trước đó không giữ lock xuyên mọi request/transaction và không bảo đảm permission vẫn đúng cho write tiếp theo.

Các cách giảm rủi ro:
- Kiểm tra owner/tenant/state trên entity trong transaction ghi.
- Pessimistic locking hoặc optimistic locking `@Version` phù hợp.
- SQL conditional update chứa actor/tenant/owner/status/version ở `WHERE`.
- Kiểm tra affected-row count; 0 rows phải dẫn tới deny/conflict/not-found theo contract.
- Với lệnh tài chính, xét separation of duties và approval state.
- External side effect nên được thực hiện theo outbox/transactional messaging khi cần đảm bảo nhất quán.
- Cache ownership/ACL cần version/invalidation.

SQL minh họa khi chỉ owner được đổi tên:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_actor
  AND status = 'DRAFT'
  AND version = :expected_version;
```

`trusted_tenant` và `authenticated_actor` phải đến từ security context/membership server đã xác minh; không lấy từ request body. Nếu business có ACL WRITE/delegated permission, query phải mở rộng theo policy chứ không cố chấp owner-only.

## 17. Nên lọc dữ liệu ngay tại repository khi nào?

`@PostAuthorize` rất tiện với một object đọc sau khi truy vấn. Tuy nhiên, nó không ngăn DB đọc object chưa được phép. Khi dữ liệu đặc biệt nhạy cảm, một truy vấn scoped có thể an toàn/hiệu quả hơn:

```java
public Optional<DocumentView> findReadableById(
        long documentId, UUID tenantId, UUID actorId);
```

SQL:

```sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND (
       d.owner_id = :actor_id
       OR EXISTS (
           SELECT 1
           FROM document_grants g
           WHERE g.document_id = d.id
             AND g.user_id = :actor_id
             AND g.permission = 'READ'
       )
  );
```

Với truy vấn đã giới hạn theo owner/ACL, document không được phép không đi vào DTO của tầng service theo đường này. Có thể vẫn giữ post-check như defense in depth nếu phù hợp, nhưng cần tránh duplicate DB reads và sự không nhất quán giữa policy của query và policy bean.

**Lựa chọn:**
- Hệ thống đơn giản, một object đọc: `@PostAuthorize` sau load là pattern hợp lý khi đã tính tới rủi ro truy vấn trước.
- Hệ thống multi-tenant hoặc data sensitive: query hạn chế tenant/ownership ngay từ DB, thêm domain policy khi cần.
- Lệnh write: bắt buộc kiểm tra trước side effect; `@PostAuthorize` không phải chốt cuối chính.
- List lớn và phân trang: query có scope thường tốt hơn lấy toàn bộ rồi lọc.

Không có quy tắc “post-check luôn sai”. Nó phù hợp với **đối tượng đọc chỉ có sau truy vấn**, miễn phương thức không tạo side effect nhạy cảm trước khi decision.

## 18. Tập kết quả khác object đơn: @PostFilter

Giả sử method trả `List<DocumentView>`:

```java
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public List<DocumentView> listDocuments() {
    return repository.findAllViews();
}
```

Biểu thức này **không hợp ngữ nghĩa**: `returnObject` là một List, không phải một DocumentView có property `ownerId`. Không mặc định một `@PostAuthorize` sẽ lặp qua mọi phần tử.

Với collection/stream hỗ trợ, Spring Security có `@PostFilter`:

```java
@PostFilter(
    "filterObject.ownerId == authentication.name"
)
public List<DocumentView> listDocuments() {
    return repository.findAllViews();
}
```

Trong `@PostFilter`:
- `filterObject` là từng phần tử đang xét.
- Phần tử không thỏa được loại ra khỏi kết quả.
- Method vẫn đã chạy và đã lấy danh sách trước khi filter.
- Nếu ownerId/Authentication ID khác hệ quy chiếu, kết quả có thể sai.
- Tenant/ACL cần policy rõ; chỉ so owner có thể quá chặt hoặc quá lỏng tùy business.

**Tại sao không khuyến khích cho list lớn?** Tải 1 triệu documents rồi lọc 999.990 phần tử trong memory gây tốn DB/network/memory, sai hiệu quả pagination/total count và có rủi ro log/cache trước filter. Truy vấn scoped với pagination là hướng nên ưu tiên. `@PostFilter` dùng khi tập nhỏ, semantics rõ và performance chấp nhận.

Nếu một bulk operation yêu cầu all-or-nothing, đừng để post-filter chỉ loại một số item rồi trả phần còn lại mà caller tưởng toàn bộ yêu cầu thành công.

## 19. Khác nhau với @AuthorizeReturnObject

Spring Security 6.3+ cung cấp `@AuthorizeReturnObject` để **proxy các object trả về** và áp method security trên chính các method của object được proxy; đây là khả năng khác với `@PostAuthorize`.

Ví dụ conceptual:

```java
@AuthorizeReturnObject
public UserProfile profile() {
    return repository.loadProfile();
}
```

Nếu class `UserProfile` có getter mang `@PreAuthorize("hasAuthority('profile:private:read')")`, proxy trả về có thể kiểm tra quyền khi getter được gọi, tùy version/config. Điều này không có nghĩa một object tự động được kiểm tra owner bằng cùng rule `@PostAuthorize`.

So sánh:
- `@PostAuthorize`: xét **một quyết định sau method** dựa trên `returnObject` và expression.
- `@PostFilter`: xét từng phần tử sau method để lọc kết quả hỗ trợ.
- `@AuthorizeReturnObject`: áp security advice khi gọi methods trên **return object proxy**; cần hiểu proxy type, AOT/runtime hints và nested objects.

Đừng thay thế một cách máy móc. Chọn theo ranh giới quyền: toàn document, tập documents hay getter trên object. Với dữ liệu cực kỳ nhạy cảm, dễ audit hơn khi trả DTO đã qua domain policy và không phụ thuộc vào tất cả client serializers đi qua proxy đúng cách.

## 20. Quyền sở hữu từ principal phải chuẩn hóa

Ví dụ chính thức so:

```java
returnObject.owner == authentication.name
```

Điều này chỉ đáng tin nếu:
- owner trong DB có cùng kiểu ý nghĩa với authentication.name;
- name không bị thay đổi qua email rename;
- Authentication được tạo từ nguồn tin cậy;
- user ở đúng tenant/context;
- không có mapping mơ hồ nhiều username tới một user ID.

Trong hệ thống hiện đại:
- `authentication.name` có thể là email, OIDC `sub` hoặc username.
- DB owner có thể là UUID hoặc numeric ID.
- API có thể dùng service identity hoặc delegated user.
- Tenant membership có thể thay đổi ngoài token.

Hãy chuẩn hóa thành `Actor` với canonical userId/tenantId sau khi xác minh Authentication, và policy so với `Document.ownerUserId` cùng hệ ID. Không tự so email với UUID hoặc lấy `ownerId` do client gửi rồi xem là ground truth.

Nếu dùng JWT, claims phải được xác minh và map đúng; việc chuỗi có trong JWT payload không tự động đồng nghĩa có thể tin khi chưa kiểm tra signature/issuer/audience/expiry.

## 21. Role hierarchy không thay object ownership

Giả sử:

```text
ROLE_ADMIN > ROLE_EDITOR
ROLE_EDITOR > ROLE_VIEWER
```

Người có `ROLE_ADMIN` có thể thỏa `hasRole('VIEWER')` khi authorization component đã wire hierarchy. Nhưng `ROLE_ADMIN` **không tự làm principal trở thành owner** Document 42.

Ví dụ:

```java
@PreAuthorize("hasRole('VIEWER')")
@PostAuthorize("@documentAccess.canRead(authentication, returnObject)")
public DocumentView readDocument(long id) {
    return repository.findViewById(id).orElseThrow();
}
```

Admin có thể vượt pre-check VIEWER nhưng vẫn bị post-check DENY nếu:
- document thuộc tenant khác;
- không là owner/ACL reader;
- không có explicit tenant-wide grant;
- state cấm xem.

Nếu muốn admin hỗ trợ đọc tài liệu của team trong cùng tenant, đặt capability riêng như `document:read:tenant` và policy giới hạn tenant, không dùng `hasRole('ADMIN') or owner` làm bypass vô điều kiện.

## 22. Post-check có tác dụng gì khi method đã query dữ liệu nhạy cảm?

Post-check ngăn **kết quả bình thường** trở về caller qua invocation đã được interceptor bảo vệ. Nhưng dữ liệu có thể đã trải qua:
- JDBC/JPA và memory;
- mapper tạo DTO;
- logging/tracing;
- cache ghi kết quả;
- audit/event;
- external calls;
- lazy-loading và serialization chuẩn bị response.

Một ví dụ lỗi:

```java
@PostAuthorize("@documentAccess.canRead(authentication, returnObject)")
public DocumentView readDocument(long id) {
    DocumentView view = repository.findViewById(id).orElseThrow();

    // Sai: ghi toàn bộ tài liệu vào log trước post-check
    logger.info("Document loaded: {}", view);

    return view;
}
```

Ngay cả khi interceptor sau đó DENY, log đã chứa dữ liệu private.

Cách an toàn:
- Không log full payload/secret.
- Chỉ cache kết quả nếu key và policy bảo đảm không lộ cross-user/tenant; cân nhắc check quyền trước cache.
- Không publish event chứa dữ liệu trước khi authorize.
- Không khởi tạo stream lazy có tác dụng đọc thêm sau proxy mà bỏ qua kiểm tra.
- Với PII nhạy cảm, cân nhắc query scoped/authorization trước khi tạo DTO.

**Post-authorize không phải data-loss-prevention tổng quát cho mọi side channel**. Nó là một checkpoint ở method boundary.

## 23. Proxy, self-invocation và đường gọi ngoài HTTP

Method security dùng Spring AOP theo mặc định. Nếu service có:

```java
@Service
public class DocumentFacade {

    public DocumentView facade(long id) {
        return this.readSecured(id);
    }

    @PostAuthorize(
        "@documentAccess.canRead(authentication, returnObject)"
    )
    public DocumentView readSecured(long id) {
        return repository.findViewById(id).orElseThrow();
    }
}
```

`this.readSecured` là self-invocation trong cùng bean; với proxy AOP thông thường, lời gọi **không đi qua proxy**, và `@PostAuthorize` có thể không chạy. Một controller gọi `facade` qua proxy không khiến mọi lời gọi nội bộ tự động được method-security bảo vệ.

Cách giảm rủi ro:
- Tách protected operation thành bean khác và gọi qua Spring-injected proxy.
- Đặt policy bắt buộc trong use case/repository scope thay vì chỉ dựa vào một getter được proxy.
- Viết test gọi qua các public methods và đường đi thật.
- Nếu dùng AspectJ weaving, hiểu cơ chế khác với Spring AOP proxy; không mặc định mọi app dùng weaving.
- Không tạo object cần method security bằng `new` rồi kỳ vọng advisor hoạt động.
- Test các trường hợp final/private methods, Kotlin final classes và interface/proxy type theo dự án thực.

Đặc biệt, message listeners, batch jobs và GraphQL cũng có thể gọi service. Nếu các đường này dùng bean proxy đúng, post-check có thể áp dụng; nhưng **response 403 là khái niệm của HTTP**, ngoài HTTP cần xử lý `AccessDeniedException` theo mô hình tương ứng.

## 24. @Transactional và thứ tự advisors

Vấn đề quan trọng nhất không phải chỉ “có annotation transactional hay không”, mà là **transaction advisor và method-security advisors được lồng theo thứ tự nào**.

Nếu dùng:

```java
@Transactional
@PostAuthorize("@documentAccess.canRead(authentication, returnObject)")
public Document updateThenReturn(long id) {
    // Có thể có ghi DB ở đây...
}
```

có hai khả năng nguy hiểm về mặt thiết kế:
- Post-check xảy ra trong một transaction nhưng đã thực hiện mutation, cần rollback đúng và ngoại tác phải không phát sinh.
- Transaction đã hoàn tất trước post-check, nên DENY không undo write.

Tài liệu chính thức Spring Security lưu ý về `@EnableTransactionManagement` và `@EnableMethodSecurity` khi phải phối hợp. **Không khuyến nghị dựa vào thứ tự advisor để biến post-check thành write guard**; cách hiểu/tuning order khác nhau giữa codebase/version.

Với use case write, giải pháp dễ review:
1. `@PreAuthorize` quyền chức năng.
2. Trong transaction load object và owner/ACL/state hiện tại.
3. Domain policy xác nhận quyền **trước mutation**.
4. Thực hiện write; commit và publish side effect theo kiến trúc.
5. Không dùng post-check làm bước xác minh owner duy nhất.

Với use case read và lazy JPA relation, nếu post-check cần `returnObject.owner` nhưng transaction/read session đã đóng, biểu thức có thể gây lazy loading exception. Trả DTO chứa những trường policy cần, materialize trong transaction, rồi post-check trên DTO có semantics ổn định.

## 25. Java 17+ chạy độc lập: kiểm tra owner sau khi truy vấn

Đây là chương trình **Java thuần**, mô phỏng việc query một record rồi quyết định có trả hay không. Nó không sử dụng Spring Security, AOP, JWT hay database thật, vì vậy không chứng minh được interceptor production. Nó minh họa:
- Kiểm tra trước về authority chức năng.
- Sau query mới biết owner/tenant/state.
- Người không phải owner bị DENY.
- Grant tenant-wide là ngoại lệ **tường minh** và vẫn bị giới hạn cùng tenant.
- Resource không tồn tại được xử lý riêng.
- Truy vấn đã xảy ra trước bước object decision.

Lưu thành file `PostOwnershipDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class PostOwnershipDemo {

    record Actor(String name, String tenant, Set<String> rights) {}
    record Document(long id, String owner, String tenant, boolean locked) {}

    private static final Map<Long, Document> DB = Map.of(
        42L, new Document(42, "alice", "A", false),
        43L, new Document(43, "bob", "A", false),
        44L, new Document(44, "bob", "B", false),
        45L, new Document(45, "alice", "A", true)
    );

    private static int queries = 0;

    static Document load(long documentId) {
        queries++;
        return DB.get(documentId);
    }

    static String authorize(Actor actor, Document doc) {
        if (doc == null) {
            return "NOT_FOUND";
        }
        if (!actor.rights().contains("document:read")) {
            return "DENY capability";
        }
        if (!actor.tenant().equals(doc.tenant())) {
            return "DENY tenant";
        }
        if (doc.locked()) {
            return "DENY locked";
        }
        if (actor.name().equals(doc.owner())) {
            return "ALLOW owner";
        }
        if (actor.rights().contains("document:read:tenant")) {
            return "ALLOW tenant-grant";
        }
        return "DENY owner";
    }

    static String readThenAuthorize(Actor actor, long documentId) {
        Document loaded = load(documentId);
        return authorize(actor, loaded);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "A", Set.of("document:read"));
        Actor bob = new Actor(
            "bob", "A", Set.of("document:read"));
        Actor manager = new Actor(
            "manager", "A", Set.of(
                "document:read", "document:read:tenant"));
        Actor guest = new Actor(
            "guest", "A", Set.of());

        System.out.println("Alice own: "
            + readThenAuthorize(alice, 42));
        System.out.println("Bob other document: "
            + readThenAuthorize(bob, 42));
        System.out.println("Manager same tenant: "
            + readThenAuthorize(manager, 42));
        System.out.println("Bob cross tenant: "
            + readThenAuthorize(bob, 44));
        System.out.println("Manager locked: "
            + readThenAuthorize(manager, 45));
        System.out.println("Guest missing authority: "
            + readThenAuthorize(guest, 42));
        System.out.println("Unknown document: "
            + readThenAuthorize(alice, 999));
        System.out.println("Bob own: "
            + readThenAuthorize(bob, 43));
        System.out.println("Repository queries: " + queries);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac PostOwnershipDemo.java
java PostOwnershipDemo
```

Stdout **chính xác**:

```text
Alice own: ALLOW owner
Bob other document: DENY owner
Manager same tenant: ALLOW tenant-grant
Bob cross tenant: DENY tenant
Manager locked: DENY locked
Guest missing authority: DENY capability
Unknown document: NOT_FOUND
Bob own: ALLOW owner
Repository queries: 8
```

Phân tích:
1. Alice có quyền đọc và là owner của Document 42 nên được phép.
2. Bob có cùng permission chức năng nhưng không phải owner Document 42 nên DENY.
3. Manager được cấp `document:read:tenant` tường minh, đọc trong tenant A nhưng không vượt state.
4. Bob có thể trùng owner của Document 44 nhưng active tenant A khác tenant B nên bị chặn.
5. Document 45 bị khóa đọc, manager không bypass.
6. Guest thiếu authority, object decision DENY dù tài liệu có tồn tại.
7. ID không tồn tại trả NOT_FOUND theo contract demo.
8. Bob đọc Document 43 của chính mình được ALLOW.
9. Có **8 lần lookup**: chương trình vẫn tải object trước khi đánh giá owner (và demo còn đơn giản hóa việc pre-check authority). Đó là lý do post-authorization không thay thế security-scoped query khi cần tránh tải dữ liệu từ đầu.

**Giới hạn:** `DB` là `Map` giả, `authorize` là domain logic minh họa, không có Spring AOP/`@PostAuthorize` thật; chương trình không tạo side effect. Trong production, actor phải đến từ authentication tin cậy, repository phải bảo vệ tenant/query scope, và owner/ACL phải lấy từ nguồn chuẩn.

## 26. Unit test policy: owner, tenant, ACL, state

Khi sử dụng `@documentAccess.canRead(...)`, hãy test bean domain policy độc lập:

```java
@Test
void userCannotReadAnotherOwnersPrivateDocument() {
    Actor bob = actor("bob", "org-A", "document:read");
    DocumentView aliceDoc = document(
        42L, "alice", "org-A", false);

    assertThat(documentAccess.canRead(bob, aliceDoc)).isFalse();
}

@Test
void adminCannotReadCrossTenantWithoutExplicitPermission() {
    Actor admin = actor("admin", "org-A", "document:read:tenant");
    DocumentView otherTenantDoc = document(
        44L, "someone", "org-B", false);

    assertThat(documentAccess.canRead(admin, otherTenantDoc))
        .isFalse();
}

@Test
void ownerCannotReadLockedDocumentWhenPolicyForbidsIt() {
    Actor alice = actor("alice", "org-A", "document:read");
    DocumentView lockedDoc = document(
        45L, "alice", "org-A", true);

    assertThat(documentAccess.canRead(alice, lockedDoc)).isFalse();
}
```

**Đây là snippets JUnit/AssertJ**, dùng fixtures `actor`/`document` do app định nghĩa; overload `canRead(Actor, DocumentView)` có thể khác cách tích hợp `canRead(Authentication, DocumentView)`. Trong test thật, chọn một contract thống nhất hoặc adapter rõ ràng.

Các ca quan trọng:
- Owner đúng tenant, đủ quyền, state cho phép → ALLOW.
- User khác owner, đủ quyền chức năng nhưng thiếu ACL → DENY.
- Owner khác tenant → DENY nếu active-tenant policy bắt buộc.
- Grant tenant-wide nhưng khác tenant → DENY.
- Grant ACL READ vẫn không cho DELETE.
- State ARCHIVED/LOCKED theo business rule.
- Null result và resource không tồn tại.
- OwnerId đổi hoặc ACL bị revoke giữa các request.
- Authentication thiếu hoặc actor resolver lỗi → fail closed.

Unit test policy chưa chứng minh `@PostAuthorize` đã được Spring nối đúng; phải có integration test qua Spring proxy.

## 27. Integration test @PostAuthorize qua Spring-managed bean

Spring Security Test cung cấp `@WithMockUser` để chạy method với Authentication giả lập.

Ví dụ một service thực `readAccount` trả Account có owner:

```java
@Autowired
BankService bankService;

@Test
@WithMockUser(username = "alice",
              authorities = {"account:read"})
void ownerMayRead() {
    Account account = bankService.readAccount(42L);
    assertThat(account.getOwner()).isEqualTo("alice");
}

@Test
@WithMockUser(username = "bob",
              authorities = {"account:read"})
void otherUserIsDeniedAfterQuery() {
    assertThatThrownBy(() -> bankService.readAccount(42L))
        .isInstanceOf(AccessDeniedException.class);
}
```

Đây là **test snippets**, cần JUnit 5, AssertJ, Spring Security Test, `@SpringBootTest` hoặc `@ContextConfiguration`, DB fixture Account 42 owner Alice và method `@PostAuthorize` đã thực sự được cấu hình. Không gọi `new BankService(...)` vì sẽ bypass Spring AOP; inject bean từ context.

Cần thêm test chứng minh **method body đã được chạy** trước post-check, ví dụ repository spy đếm `findById(42L)` = 1 đối với case bị DENY. Điều này giúp cả team hiểu đúng hạn chế của post-authorization. Không ghi log full Account trong test/tracing production.

Với method có `@PreAuthorize` và `@PostAuthorize`:
- User thiếu capability → repository **không** được gọi.
- User có capability nhưng khác owner → repository được đọc, sau đó DENY.
- User đủ capability và owner → đọc + ALLOW.

Không chỉ assert 403 trong HTTP: 403 có thể đến từ filter/CSRF/role/domain, chứ không chứng minh hậu kiểm nào đã chạy.

## 28. MockMvc: cần controller thật và test đối chứng

Tình huống REST:

```java
@Test
void ownerReadsDocument() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("document:read"))))
        .andExpect(status().isOk());
}

@Test
void userWithReadPermissionButNotOwnerIsDenied() throws Exception {
    mvc.perform(get("/api/documents/42")
            .with(user("bob").authorities(
                new SimpleGrantedAuthority("document:read"))))
        .andExpect(status().isForbidden());
}
```

Snippets trên cần:
- `MockMvc` với Spring Security filters;
- controller `GET /api/documents/{id}` thực;
- service proxy có `@PostAuthorize`;
- Document 42 owner Alice trong test DB;
- authentication/permissions được map đúng;
- exception mapping theo contract.

Nếu app chọn trả 404 khi user không có quyền nhằm chống enumeration, hãy thay expectation và test không lộ tài liệu. Nếu route không tồn tại, 404 không chứng minh owner policy đúng. Nếu GET bị redirect login/401 trước khi tới service, test `@PostAuthorize` chưa được exercise.

Ngoài HTTP, method-security DENY có thể ném `AccessDeniedException` để caller xử lý. Test service bean trực tiếp bổ sung cho MockMvc test và giúp định vị điểm chặn chính xác.

## 29. Cần làm gì với các lazy JPA entities?

Ví dụ:

```java
@PostAuthorize("returnObject.owner.id == authentication.name")
public Document readDocument(long id) {
    return repository.getReferenceById(id);
}
```

Rủi ro:
- `getReferenceById` có thể trả lazy proxy; owner chưa được load.
- Nếu persistence context đã đóng, SpEL property access có thể gây lazy loading exception.
- Nếu `owner` là entity relation, chạm property có thể tạo thêm SQL ngoài ý định.
- `authentication.name` có thể không bằng owner ID.
- Trả JPA entity trực tiếp cho controller/serializer có thể vô tình lộ fields hoặc trigger lazy fetch ngoài security check.

Tốt hơn:
- Load dữ liệu policy cần bằng query rõ nghĩa.
- Map sang `DocumentView` chỉ chứa fields được phép và metadata security cần kiểm tra.
- Post-check trên DTO có ownerId/tenantId đã materialize.
- Tại service, không log full entity hoặc ghi cache không được phân quyền trước hậu kiểm.
- Nếu DB security phức tạp, truy vấn theo tenant/grants ngay từ đầu.

Chỉ thêm `@Transactional(readOnly = true)` không phải lúc nào bảo đảm expression post-check chạy **trong transaction**; thứ tự AOP advisors ảnh hưởng lifecycle. Nên test integration đúng Spring/JPA configuration và không giấu lỗi bằng Open Session in View tùy tiện.

## 30. Danh sách lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ `@PreAuthorize("authenticated()")` cho getById | User đoán ID có thể lấy tài liệu người khác | Authority + owner/tenant/ACL |
| So `returnObject.ownerId` với username khác hệ ID | Sai ALLOW/DENY | Chuẩn hóa canonical actor ID |
| `returnObject` lấy owner do client tự khai | Hậu kiểm giả, IDOR vẫn xảy ra | Owner từ database tin cậy |
| `@PostAuthorize` cho method ghi tiền | Side effect xảy ra trước deny | Kiểm tra object trước write |
| Tin rollback luôn undo mọi side effect | Message/email/payment đã gửi | Transaction/outbox và pre-check |
| Role ADMIN mặc định được đọc mọi tenant | Lộ dữ liệu cross-tenant | Capability riêng và tenant scope |
| Không xử lý null | SpEL error hoặc response sai contract | NotFound/explicit null policy |
| Trả `Optional` nhưng expression dùng property trực tiếp | Không đúng type hoặc null semantics | Test exact type hoặc trả DTO/non-null |
| Dùng `@PostAuthorize` trên `List` như object đơn | Không kiểm tra từng phần tử | `@PostFilter` hoặc query scoped |
| Dùng `@PostFilter` cho danh sách triệu rows | Hiệu năng/pagination sai | Repository-level filtering |
| Query rồi log full document | Rò dữ liệu trước post-check | Không log/caching PII trước authorize |
| Self-invocation qua `this` | AOP advisor không chạy | Gọi bean proxy/domain guard |
| JPA lazy owner không còn session | LazyInitializationException ở SpEL | DTO materialized/query phù hợp |
| Chỉ test user thiếu permission | Không bắt người đủ permission sai owner | Negative test BOLA |
| Chỉ test HTTP 403 | Không biết filter nào deny | Service proxy test + spy |
| Không giới hạn tenant trong query | Đọc nhiều data không cần thiết | Scoped query và policy |
| Dựa vào @PostFilter cho bulk write | Silent partial update/side effect | All-or-nothing policy trước command |
| Config method security chưa bật | Annotation không chạy | `@EnableMethodSecurity` và test |
| Code tạo object bằng `new` | Bypass Spring proxy | Bean từ Spring context |
| Coi hậu kiểm là ownership vĩnh viễn | Owner/ACL có thể đổi trước lần write | Recheck trong transaction |

## 31. Checklist triển khai @PostAuthorize kiểm tra sở hữu

1. Method này là **đọc không có side effect** hay đang ghi dữ liệu?
2. `@EnableMethodSecurity` đã được bật trong context thật chưa?
3. Caller có đi qua Spring proxy/advisor không?
4. Có `@PreAuthorize` quyền chức năng để chặn trước DB read không?
5. `returnObject` có đúng kiểu non-null/DTO mà SpEL mong đợi không?
6. OwnerId/tenantId có đến từ bản ghi server tin cậy không?
7. Actor identity có dùng canonical ID cùng hệ với ownerId không?
8. Tenant/membership có được xác minh trước khi so với document không?
9. Policy có hỗ trợ ACL, delegation, project grant hoặc tenant-wide capability nếu business cho phép không?
10. Có state như LOCKED/ARCHIVED làm DENY không?
11. Một người có role cao nhưng thiếu object grant có bị DENY không?
12. Một người cùng tên owner nhưng khác tenant có bị DENY khi cần không?
13. Null/missing resource đi theo 404 hay 403 theo contract?
14. Có nguy cơ enumeration do khác response/timing không?
15. Data nhạy cảm có bị log/cache/publish trước hậu kiểm không?
16. Có lazy JPA property gây SQL sau khi transaction đóng không?
17. Với list, có nên dùng `@PostFilter` hay query scoped thay vì `@PostAuthorize` không?
18. Với write, đã check object **trước mutation** trong transaction chưa?
19. Có TOCTOU giữa read và update, cần locking/version không?
20. HTTP chain và entry points ngoài HTTP có dùng cùng use case/policy không?
21. Có integration test owner ALLOW và non-owner DENY không?
22. Có test người thiếu authority không query DB không?
23. Có test người đủ authority nhưng sai owner **có query rồi bị DENY** không?
24. Có test method bị self-invocation bypass không?
25. Có test endpoint/controller/response handling đúng version không?

### Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `@PostAuthorize` phù hợp với `readDocument(id)` khi owner chỉ biết sau truy vấn?  
→ Nó có `returnObject` chứa owner thật sau method để kiểm tra trước khi kết quả đến caller.

**Câu 2.** Bob có `document:read` nhưng Document 42 thuộc Alice. Bob được phép không?  
→ Chưa. Bob vượt quyền chức năng, nhưng post-check owner/tenant/ACL phải DENY khi không có grant.

**Câu 3.** `@PostAuthorize("returnObject.owner == authentication.name")` có bảo vệ mọi tài liệu multi-tenant không?  
→ Không tự động. Cần so tenant, chuẩn hóa actor ID và xét các quyền khác.

**Câu 4.** Đã post-check DENY có nghĩa document chưa từng được đọc từ DB chưa?  
→ Không. Method body đã đọc và có thể map/log/cache trước hậu kiểm.

**Câu 5.** Có nên dùng post-check là hàng rào duy nhất cho `renameDocument` đang ghi DB?  
→ Không. Kiểm tra owner trước write và quản lý transaction/locking.

**Câu 6.** `returnObject` null có thể được truy cập `returnObject.ownerId` an toàn không?  
→ Không. Cần xử lý null/missing bằng contract rõ, thường ném not-found trước khi có return object.

**Câu 7.** Phương thức trả `List<DocumentView>` thì `@PostAuthorize` tự lặp qua mỗi item không?  
→ Không. Dùng `@PostFilter` cho tập hỗ trợ hoặc tốt hơn query scoped nếu list lớn.

**Câu 8.** Tại sao gọi `this.readSecured(id)` có thể nguy hiểm?  
→ Self-invocation bypass Spring AOP proxy method-security interceptor trong cấu hình proxy thông thường.

**Câu 9.** Tại sao chỉ nhận HTTP 403 không đủ chứng minh post-check owner?  
→ 403 có thể từ HTTP filter, CSRF hoặc pre-check; phải test service bean/spy và xác định checkpoint.

**Câu 10.** Một actor là owner tại thời điểm đọc rồi muốn update sau một request khác; được dùng kết quả post-check cũ để ghi không?  
→ Không. Quyền và state có thể đổi; cần recheck tại thời điểm write.

## Kết luận

**Khi chỉ biết owner sau khi truy vấn, `@PostAuthorize` là một công cụ đúng chỗ cho read-only method**: method tạo `returnObject` từ nguồn tin cậy, rồi Spring Security quyết định có trả kết quả cho caller hay không. Để an toàn, nên kết hợp pre-check quyền chức năng, post-check owner/tenant/ACL/state, chuẩn hóa actor ID và kiểm thử direct service invocation. Vì body đã chạy trước hậu kiểm, **không dùng `@PostAuthorize` làm chốt quyền duy nhất cho write/side effect**; các lệnh ghi phải xác minh quyền trên entity thật trong transaction trước mutation. Với dữ liệu rất nhạy cảm hoặc tập lớn, query đã giới hạn quyền tại repository thường hiệu quả và giảm bề mặt rò rỉ hơn.

## Tài liệu tham khảo chính thức

1. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — `@PostAuthorize`, `returnObject`, interceptors, IDOR và phối hợp transaction.
2. [Spring Security 7.0 — Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html) — kiến trúc method authorization và return-object support trong dòng mới.
3. [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html) — `@WithMockUser` và kiểm thử bean đã được bảo vệ.
4. [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html) — Authentication, authorities, RoleHierarchy.
5. [Spring Security 6.5 — ACL/Domain Object Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html) — chính sách quyền riêng theo object.
6. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — HTTP request authorization khác method authorization.
7. [OWASP — Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html) — kiểm tra quyền theo từng object, tránh IDOR.
