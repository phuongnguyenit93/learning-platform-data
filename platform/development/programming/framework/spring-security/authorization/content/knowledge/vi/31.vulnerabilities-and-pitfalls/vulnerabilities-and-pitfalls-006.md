# Tin ownerId, tenantId, role hoặc trạng thái do client truyền

## 1. Lỗ hổng nằm ở ranh giới tin cậy

Trong Spring Security, client được quyền **gửi yêu cầu** nhưng không được tự **chứng nhận mình có quyền**. Các giá trị như `ownerId`, `tenantId`, `role`, `status` có thể xuất hiện trong JSON body, URL, query parameter, cookie, HTTP header, form field, JavaScript state hoặc dữ liệu gửi lại từ giao diện. Vì client kiểm soát được các nguồn đó, một kẻ tấn công có thể chỉnh sửa chúng bằng công cụ HTTP mà không cần dùng giao diện chính thức.

Lỗi xảy ra khi backend dùng chính giá trị do client gửi làm bằng chứng ủy quyền: “`ownerId` trong body trùng tài khoản đang đăng nhập”, “`tenantId` trong header là tenant đang làm việc”, “`role=ADMIN` trong request”, hoặc “`status=APPROVED` nên được làm bước tiếp theo”. Việc client nói như vậy **không chứng minh** chủ sở hữu, tư cách thành viên tenant, vai trò hay trạng thái nghiệp vụ thực.

Hậu quả có thể là:

- **BOLA/IDOR (Broken Object Level Authorization):** đọc hoặc sửa tài nguyên của người khác bằng cách thay ID/owner.
- **Cross-tenant access:** thao tác với dữ liệu của tổ chức/tenant khác khi điều kiện truy vấn không được giới hạn bằng tenant đã xác thực và được cấp quyền.
- **Privilege escalation:** tự nâng quyền bằng cách gửi `role=ADMIN`, `authorities=["ROLE_ADMIN"]` hoặc ghi đè trường role trên đối tượng người dùng.
- **Workflow bypass:** nhảy từ `DRAFT` sang `APPROVED`, `PAID`, `ACTIVE`, `VERIFIED` khi chưa đáp ứng điều kiện, hoặc vượt qua người xét duyệt.
- **Mass assignment/overposting:** framework ánh xạ JSON vào entity rồi lưu hàng loạt, vô tình cho phép sửa các trường nhạy cảm không dành cho client.

Những lỗi này thuộc **authorization và tính toàn vẹn dữ liệu**, khác với SQL injection. Sử dụng ORM, HTTPS, JWT hay `@Valid` không tự sửa được việc backend tin sai nguồn dữ liệu.

### Nguyên tắc thiết kế

**Dữ liệu client là input/ý định; dữ kiện dùng quyết định quyền phải được backend xác minh từ nguồn có thẩm quyền.** Cụ thể:

| Thuộc tính | Có thể do client gửi để làm gì? | Nguồn tin cậy để ra quyết định |
| --- | --- | --- |
| `ownerId` | Chọn người nhận/chủ mới nếu nghiệp vụ cho phép | Owner hiện tại đọc từ DB; actor từ principal xác thực; chính sách chuyển chủ trên server |
| `tenantId` | Chọn workspace/tenant trong số những tenant được phép | Tenant membership/authorization do server xác minh; ràng buộc tenant trên mọi thao tác dữ liệu |
| `role` | Đề nghị quản trị viên gán vai trò cho tài khoản khác trong một quy trình có quyền | `Authentication.getAuthorities()` đã được security chain xác thực và/hoặc chính sách role lưu trên server |
| `status` | Mô tả hành động mong muốn, ví dụ “submit” hoặc “publish” | Trạng thái hiện tại từ DB, quy tắc chuyển trạng thái, actor/role có thẩm quyền, điều kiện nghiệp vụ |

Client hoàn toàn có thể truyền **ID tài nguyên** hoặc **tenant được chọn**. Vấn đề không phải cấm những tham số này, mà là **không diễn giải chúng thành quyền khi chưa đối chiếu**.

## 2. Ví dụ endpoint dễ bị khai thác

Đoạn sau minh họa **mẫu sai, không dùng trong production**. Giả sử ứng dụng cho phép cập nhật tài liệu và dùng DTO chứa mọi thuộc tính:

```java
// MÃ KHÔNG AN TOÀN: chỉ để phân tích lỗ hổng.
record UpdateDocumentRequest(
        String title,
        String ownerId,
        String tenantId,
        String role,
        String status) {}

@PutMapping("/api/documents/{id}")
public void update(@PathVariable UUID id,
                   @RequestBody UpdateDocumentRequest request) {
    Document document = repository.findById(id).orElseThrow();

    if (request.ownerId().equals(requestContext.userId())
            && request.role().equals("ADMIN")) {
        document.setTitle(request.title());
        document.setOwnerId(request.ownerId());
        document.setTenantId(request.tenantId());
        document.setStatus(request.status());
        repository.save(document);
    }
}
```

Điểm yếu độc lập với cách thiết kế controller cụ thể: `request.ownerId()` và `request.role()` đều do người gọi chọn; `request.tenantId()` và `request.status()` được đưa thẳng vào entity; truy vấn `findById(id)` không kiểm tra owner/tenant; người dùng chỉ cần sửa payload để làm thay đổi dữ liệu nhạy cảm.

Payload giả mạo điển hình:

```json
{
  "title": "Tài liệu bị chiếm",
  "ownerId": "alice",
  "tenantId": "tenant-khac",
  "role": "ADMIN",
  "status": "APPROVED"
}
```

Ngay cả khi backend đã xác thực Alice, **xác thực danh tính Alice** không đồng nghĩa rằng Alice được tự nhận vai trò ADMIN, chuyển dữ liệu sang tenant khác hoặc duyệt tài liệu. Một `@PreAuthorize("isAuthenticated()")` chỉ xác nhận có đăng nhập, không xác thực quyền trên đối tượng/tenant/trạng thái.

Nếu thay DTO bằng `@RequestBody Document document` rồi gọi `repository.save(document)`, nguy cơ còn rộng hơn: tất cả thuộc tính có setter/binding hợp lệ, bao gồm `ownerId`, `roles`, `approved` hoặc `status`, có thể vô tình trở thành writable. `@JsonIgnore` hay việc ẩn input trên frontend không thay thế cơ chế bảo vệ quyền ở service.

## 3. Phân tích riêng từng nhóm thuộc tính

### 3.1. `ownerId`: chủ sở hữu lưu trong tài nguyên, actor lấy từ principal

Lỗi phổ biến: `if (request.ownerId().equals(authentication.getName()))` rồi cho sửa một tài liệu bất kỳ. Kẻ tấn công có thể điền `ownerId` là ID của chính mình, bất kể owner **đang lưu trong DB** là ai. Nếu yêu cầu chứa `documentId` của người khác, phép kiểm tra này trở thành vô nghĩa.

Cách đúng với tài nguyên chỉ dành cho chủ sở hữu:

1. Lấy **actor ID đáng tin cậy** từ `Authentication` đã được Spring Security thiết lập, theo hợp đồng định danh của ứng dụng.
2. Lấy **owner hiện tại** của tài nguyên từ DB hoặc kiểm tra điều kiện owner ngay trong truy vấn dữ liệu.
3. Đối chiếu actor, owner và các điều kiện chính sách khác **tại điểm đọc/ghi** phù hợp.
4. Nếu cần chuyển chủ, tạo hành động `transferOwnership` riêng: actor có quyền chuyển, người nhận hợp lệ, tenant và trạng thái thỏa điều kiện, cập nhật được audit và bảo vệ concurrency.

Khi tạo tài nguyên “của tôi”, thường gán `ownerId = currentActorId` ở server. Không nhận `ownerId` như dữ kiện tự chứng thực. Với tính năng tạo hộ người khác, backend có thể chấp nhận `requestedOwnerId` nhưng phải kiểm tra quyền ủy quyền và tính hợp lệ người nhận trước khi gán.

### 3.2. `tenantId`: bộ chọn ngữ cảnh không phải giấy phép truy cập

Ứng dụng multi-tenant thường nhận `tenantId` qua URL như `/tenants/{tenantId}/documents`, subdomain hoặc header `X-Tenant-Id`. Giá trị này có thể dùng để **chọn** tenant, đặc biệt khi một người tham gia nhiều tenant. Nhưng backend phải xác minh người dùng **đang có quyền trong tenant đó**, đồng thời ràng buộc truy vấn tài nguyên theo tenant.

Một lỗi nguy hiểm:

```java
Document doc = repository.findById(documentId).orElseThrow();
// Chỉ xác minh request.tenantId có tồn tại,
// rồi sửa doc mà không đối chiếu doc.tenantId.
```

Nếu tài liệu thuộc tenant B nhưng request chọn tenant A, việc kiểm tra membership ở tenant A không đủ. Cần đồng thời xác minh:

- Actor có membership/permission đang hiệu lực trong **tenant được chọn**.
- Tài nguyên thực sự thuộc **cùng tenant** đó (cùng các quan hệ cha/con có liên quan).
- Quyền thao tác cụ thể được cấp trong tenant đó, không chỉ có membership chung.
- Mọi đường đọc/ghi, tìm kiếm, tải file, API bulk, event handler, cache key và export không bỏ qua tenant scope.

Ví dụ truy vấn repository an toàn hơn là `findByIdAndTenantId(...)` cho phép đọc, hoặc `UPDATE ... WHERE id = :id AND tenantId = :tenantId AND ownerId = :actorId ...` cho phép ghi, kết hợp kiểm tra membership và permission. Đối với truy cập phức tạp hoặc chính sách thu hồi tức thời, điều kiện membership phải được phối hợp với thao tác ghi bằng transaction/khóa/điều kiện DB phù hợp để tránh race.

Không dùng tenant mặc định toàn cục, `ThreadLocal` chưa được thiết lập/được dọn sai, hoặc `X-Tenant-Id` như nguồn quyền tự động. Nếu tenant đến từ JWT **đã xác minh** hoặc từ IdP tin cậy, vẫn phải xác định token có phù hợp nghiệp vụ hiện tại, đối tượng và thời điểm hiệu lực hay không. Với mô hình người dùng đa tenant, claim được ký có thể mô tả membership nhưng không tự biến một ID tenant lạ trong URL thành hợp lệ.

### 3.3. `role`: quyền đến từ hệ thống xác thực và chính sách server

Ví dụ sai: `if ("ADMIN".equals(request.role()))`, `if (headers.get("X-Role").equals("ADMIN"))` hoặc nhận danh sách `authorities` từ request rồi xây `Authentication` với các quyền đó. Client có thể tự gán role bất kỳ. Việc giao diện ẩn nút quản trị không ngăn request HTTP thủ công.

Trong Spring Security, authorization theo role/authority phải dựa vào `Authentication` được security chain tạo sau khi **xác minh nguồn xác thực**, ví dụ session đã đăng nhập, JWT được kiểm chữ ký/issuer/audience/expiry, hoặc lookup principal có thẩm quyền. Ví dụ `hasAuthority('DOCUMENT_PUBLISH')` hoặc `hasRole('ADMIN')` dùng authority trong SecurityContext; chú ý `hasRole('ADMIN')` thường ánh xạ thành authority `ROLE_ADMIN`, còn `hasAuthority` dùng chuỗi chính xác.

**Ngoại lệ hợp lệ:** API quản trị người dùng có thể nhận `targetRole` do admin muốn gán. Nhưng đây là *yêu cầu thay đổi quyền*, không phải vai trò của chính người gọi. Server phải kiểm tra admin có quyền gán role đó trong phạm vi tenant phù hợp, chặn tự nâng đặc quyền/vượt cấp theo chính sách, xác thực người được gán, lưu thay đổi và audit. Không tạo `Authentication` hiện tại từ trường `targetRole`.

Một claim role bên trong **JWT hợp lệ và đã kiểm chữ ký** khác với `role` trong JSON body hoặc header tự chế: claim có thể là dữ kiện xác thực được IdP cung cấp theo thiết kế. Tuy vậy, hệ thống vẫn phải quy định xử lý thay đổi role/thu hồi token, kiểm tra phạm vi tenant và độ trễ claim; role trong token cũ không nhất thiết phản ánh chính sách mới ngay lập tức.

### 3.4. `status`: client được yêu cầu hành động, server kiểm tra chuyển trạng thái

Ví dụ sai: `entity.setStatus(request.status())` cho phép tự gửi `APPROVED`, `PAID`, `VERIFIED` hoặc `ACTIVE` để bỏ qua kiểm duyệt, thanh toán hay xác minh. Ngay cả khi actor sở hữu bản ghi, **quyền sửa nội dung không đồng nghĩa quyền duyệt/hoàn tất quy trình**.

Thay vào đó, công khai **lệnh nghiệp vụ** như `submit`, `approve`, `reject`, `publish`; hoặc nhận enum hành động có allowlist. Service lấy `status` hiện tại từ DB, kiểm tra transition và người thực thi, điều kiện phụ như người duyệt không được là người tạo, rồi thực thi chuyển trạng thái có điều kiện version.

Ví dụ ma trận (chỉ minh họa chính sách của một workflow):

| Status hiện tại | Hành động | Vai trò/ngữ cảnh cần kiểm tra | Status mới |
| --- | --- | --- | --- |
| `DRAFT` | `submit` | Chủ sở hữu trong tenant và dữ liệu hợp lệ | `SUBMITTED` |
| `SUBMITTED` | `approve` | Người duyệt được cấp quyền; không vi phạm tách nhiệm vụ | `APPROVED` |
| `SUBMITTED` | `reject` | Người duyệt được cấp quyền | `REJECTED` |
| `APPROVED` | `editDraft` | Theo quy trình, có thể phải tạo revision mới | Không mặc nhiên quay về `DRAFT` |

Nếu status hợp lệ có thể thay đổi từ transaction khác giữa kiểm tra và ghi, dùng optimistic version, conditional update hoặc khóa để ngăn sử dụng trạng thái cũ. `@Valid` trên `status` chỉ kiểm tra định dạng/tập enum, **không biết transition này có được phép đối với actor và tài nguyên hiện tại**.

## 4. Mẫu triển khai Spring Boot/Spring Security

Các đoạn dưới đây là **mảnh ghép** trong ứng dụng Spring Boot 3.x / Spring Security 6.x với entity `Document`, `DocumentStatus` (`DRAFT`, `PUBLISHED`), `TenantMembershipRepository` và bộ cấu hình `@EnableMethodSecurity` có sẵn. Chúng không phải một tệp Java độc lập. Giả định `Authentication.getName()` là ID actor ổn định đúng với khóa `ownerId`/membership trong DB; nếu ứng dụng dùng username hoặc subject khác khóa người dùng, phải có bước ánh xạ danh tính tin cậy.

Thay vì nhận `ownerId`, `role` và `status` tùy ý, endpoint “publish” chỉ nhận **version**:

```java
public record PublishRequest(
        @jakarta.validation.constraints.NotNull
        @jakarta.validation.constraints.Positive
        Long expectedVersion) {}
```

```java
@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {
    private final DocumentPublishService publishService;

    public DocumentController(DocumentPublishService publishService) {
        this.publishService = publishService;
    }

    @PatchMapping("/{documentId}/publish")
    public ResponseEntity<Void> publish(
            @PathVariable UUID tenantId,
            @PathVariable UUID documentId,
            @jakarta.validation.Valid @RequestBody PublishRequest request) {

        publishService.publish(tenantId, documentId, request.expectedVersion());
        return ResponseEntity.noContent().build();
    }
}
```

Repository cập nhật có điều kiện theo **ID tài nguyên, tenant, owner, status và version**. Mỗi điều kiện đến từ tham số đã xác minh trên server hoặc dữ liệu DB, không từ tuyên bố owner/role/status của client:

```java
public interface DocumentRepository extends JpaRepository<Document, UUID> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Document d
           set d.status = :nextStatus,
               d.version = d.version + 1
         where d.id = :documentId
           and d.tenantId = :tenantId
           and d.ownerId = :actorId
           and d.status = :expectedStatus
           and d.version = :expectedVersion
        """)
    int publishIfAllowed(
            @Param("documentId") UUID documentId,
            @Param("tenantId") UUID tenantId,
            @Param("actorId") String actorId,
            @Param("expectedStatus") DocumentStatus expectedStatus,
            @Param("nextStatus") DocumentStatus nextStatus,
            @Param("expectedVersion") long expectedVersion);
}
```

Service lấy actor từ Spring Security (không truyền actorId từ request), kiểm tra authority và membership ở tenant đã chọn:

```java
@Service
public class DocumentPublishService {
    private final DocumentRepository documents;
    private final TenantMembershipRepository memberships;

    public DocumentPublishService(DocumentRepository documents,
                                  TenantMembershipRepository memberships) {
        this.documents = documents;
        this.memberships = memberships;
    }

    @Transactional
    @PreAuthorize("hasAuthority('DOCUMENT_PUBLISH')")
    public void publish(UUID tenantId, UUID documentId, long expectedVersion) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        String actorId = authentication.getName();

        if (!memberships.existsActiveByTenantIdAndUserId(tenantId, actorId)) {
            throw new AccessDeniedException("Not permitted");
        }

        int affected = documents.publishIfAllowed(
                documentId, tenantId, actorId,
                DocumentStatus.DRAFT, DocumentStatus.PUBLISHED,
                expectedVersion);

        if (affected != 1) {
            // Tùy hợp đồng API: 403, 404 hoặc 409; tránh lộ tài nguyên.
            throw new AccessDeniedException("Not permitted or state changed");
        }
    }
}
```

Với mục đích minh họa, phương thức `existsActiveByTenantIdAndUserId` giả định repository membership có trường tên tương ứng. Ứng dụng thực phải kiểm tra **quyền publish tại tenant**, không chỉ membership nếu mỗi membership có permission khác nhau; ví dụ `hasPermission(actor, tenant, DOCUMENT_PUBLISH)` với dữ liệu role/permission đáng tin. `@PreAuthorize` là kiểm tra quyền tổng quát; điều kiện ở service/repository là kiểm tra theo tài nguyên.

Một `tenantId` ở đường dẫn vẫn là **selector chưa được tin cậy**: service kiểm tra membership, rồi câu `UPDATE` còn buộc `Document.tenantId` phải trùng selector. `ownerId` hiện hành được so khớp tại DB. `role` đến từ SecurityContext. `status` nguồn được so với `DRAFT` hiện hành trước khi chuyển sang `PUBLISHED`.

**Giới hạn concurrency cần giải quyết tùy hợp đồng:** nếu membership/role bị thu hồi ở *bảng khác* đúng giữa `existsActiveBy...` và `publishIfAllowed`, ví dụ trên chưa tự bảo đảm thu hồi tức thời. Cần kiểm tra/chốt chính sách gần điểm ghi với cơ chế nhất quán đã chọn: khóa các hàng policy, câu SQL có điều kiện membership phù hợp, hoặc kiến trúc phiên bản hóa quyền/transaction. Tương tự, các đường thay đổi owner/status phải tăng version và tuân thủ chính sách khóa. JPQL bulk update **không tự vận hành optimistic version check/increment như cập nhật entity `@Version`**, nên ví dụ tăng và kiểm tra version tường minh.

Không nên tự động trả 403 cho mọi trường hợp thực tế; `affected=0` có thể là không tồn tại, sai tenant, không là chủ, trạng thái sai hoặc version cũ. Thiết kế cách ánh xạ 403/404/409 nhất quán và không rò rỉ sự tồn tại đối tượng cho người không được phép.

## 5. Chương trình Java 17+ minh họa dữ kiện đáng tin

Ví dụ độc lập sau thể hiện sự khác nhau giữa kiểm tra một “lời khai” của client với kiểm tra actor và tài liệu có thẩm quyền. Đây là mô hình học tập trong bộ nhớ; integration test thực tế vẫn phải xác nhận DB, Spring Security, token và transaction.

Lưu tệp `ClientTrustDemo.java`:

```java
import java.util.Set;

public class ClientTrustDemo {
    record Actor(String id, Set<String> tenantIds,
                 Set<String> permissions) {}
    record Document(String tenantId, String ownerId,
                    String status) {}
    record Input(String ownerId, String tenantId,
                 String role, String status) {}

    // SAI: dùng các giá trị do client tự khai làm chứng cứ.
    static boolean unsafe(Actor actor, Input input) {
        return input.ownerId().equals(actor.id())
                && input.role().equals("ADMIN")
                && input.status().equals("PUBLISHED");
    }

    // ĐÚNG HƯỚNG: actor/permission do backend xác thực,
    // chủ/tenant/status hiện tại do backend quản lý.
    static boolean safeToPublish(Actor actor, String selectedTenant,
                                 Document document) {
        return actor.tenantIds().contains(selectedTenant)
                && document.tenantId().equals(selectedTenant)
                && document.ownerId().equals(actor.id())
                && actor.permissions().contains("DOCUMENT_PUBLISH")
                && document.status().equals("DRAFT");
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", Set.of("tenant-a"), Set.of("DOCUMENT_PUBLISH"));
        Document belongsToBob = new Document(
                "tenant-b", "bob", "DRAFT");
        Input forged = new Input(
                "alice", "tenant-b", "ADMIN", "PUBLISHED");

        System.out.println("Trust client: " + unsafe(alice, forged));
        System.out.println("Check real resource: "
                + safeToPublish(alice, forged.tenantId(), belongsToBob));

        Document ownedByAlice = new Document(
                "tenant-a", "alice", "DRAFT");
        System.out.println("Valid own resource: "
                + safeToPublish(alice, "tenant-a", ownedByAlice));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac ClientTrustDemo.java
java ClientTrustDemo
```

Stdout chính xác:

```text
Trust client: true
Check real resource: false
Valid own resource: true
```

Dòng đầu minh họa lỗ hổng: `forged.ownerId=alice`, `role=ADMIN`, `status=PUBLISHED` đều do client khai và khiến phép kiểm tra sai chấp nhận. Dòng hai từ chối vì Alice không thuộc `tenant-b` và không sở hữu tài liệu của Bob. Dòng ba cho thấy tài liệu thật sự thuộc Alice trong tenant được phép vẫn có thể được publish. Production còn phải thực thi cập nhật có điều kiện và kiểm tra concurrent changes tại DB, không chỉ dùng hàm `safeToPublish` trong bộ nhớ.

## 6. Kiểm thử chống giả mạo và leo thang quyền

Một bộ kiểm thử tốt phải **thay từng trường do client kiểm soát**, kết hợp thông tin principal/DB khác với payload, rồi xác minh cả HTTP response **và trạng thái dữ liệu cuối**. Nên có `MockMvc`/integration test với security filter hoạt động, DB test cô lập và dữ liệu Alice/Bob ở tenant A/B. Dùng `@WithMockUser` hoặc test JWT `jwt()` cho logic đã có SecurityContext; kiểm thử xác minh chữ ký/issuer/audience của JWT thật cần test riêng ở tầng xác thực. Không tự điền `Authentication` từ JSON body trong các test đó.

| Ca kiểm thử | Principal và dữ liệu thực | Payload giả mạo / hành động | Kết quả mong đợi |
| --- | --- | --- | --- |
| Giả `ownerId` | Alice đăng nhập, tài liệu của Bob | `ownerId="alice"` kèm ID tài liệu Bob | Không đọc/ghi được; owner/content không đổi |
| Giả `tenantId` | Alice chỉ thuộc tenant A; tài liệu trong B | URL/header/body đổi sang tenant B | Bị từ chối; không lộ tài liệu tenant B |
| Mismatch tài nguyên/tenant | Alice thuộc A và B; tài liệu thực thuộc B | URL chọn A nhưng ID tài liệu B | Không có thao tác chéo tenant dù actor có membership cả hai |
| Giả `role` | Alice chỉ có `DOCUMENT_READ` | JSON/header gửi `ADMIN`, `DOCUMENT_PUBLISH` | Không được publish hoặc gán quyền |
| Role hợp lệ | Người dùng có quyền thực trong tenant đúng | Lệnh publish hợp lệ | Thành công một lần, không cần trường role trong request |
| Tự nâng quyền | Alice có quyền quản lý thành viên hạn chế | `targetRole=SUPER_ADMIN` hoặc gán cho chính mình | Từ chối theo ma trận delegation/role assignment |
| Giả `status` | Tài liệu `DRAFT`, actor chỉ được sửa | Gửi `status=APPROVED` hoặc gọi approve | Không duyệt được; trạng thái giữ nguyên |
| Chuyển sai bước | Tài liệu `DRAFT` | Gọi `approve` khi chỉ hợp lệ từ `SUBMITTED` | Từ chối dù actor có quyền xét duyệt |
| Stale version | Tài liệu đã đổi từ v1 sang v2 | Request với `expectedVersion=1` | Không ghi đè; phản hồi xung đột phù hợp |
| Quyền bị thu hồi | Membership/authority bị thu hồi trong lúc request chạy | Tiếp tục thao tác từ request cũ | Theo hợp đồng hiệu lực quyền; không tự vượt qua chính sách |
| Mass assignment | User được sửa tên hồ sơ | Payload kèm `roles`, `tenantId`, `verified` | Chỉ trường allowlist được cập nhật |
| Bulk endpoint / export | Actor thuộc A, danh sách ID có cả A và B | Gửi trộn ID thuộc hai tenant | Không trả/ghi tài nguyên B; quyết định lỗi/atomicity rõ ràng |

Các test cần khẳng định các bất biến cụ thể: `ownerId`, `tenantId`, `status`, `role`, `version` trong DB không đổi khi yêu cầu bị từ chối; không có event/outbox “success”; resource thuộc tenant khác không xuất hiện trong response, thống kê, export hay log trả cho client. Với update được phép, assert đúng một bản ghi thay đổi và các trường nhạy cảm không bị ghi ngầm. Đừng chỉ `assertThrows` hoặc xác minh mock policy đã được gọi.

Để tái hiện thay đổi quyền/trạng thái trong khi request đang xử lý, dùng hai transaction thật và `CountDownLatch`/barrier ở điểm giữa precheck và write. Commit transaction thu hồi/chuyển owner trước khi cho request cũ tiếp tục rồi đọc lại bằng transaction mới. Không dùng `Thread.sleep` làm bằng chứng thứ tự. Nếu dùng pessimistic lock, kiểm thử thứ tự khóa thật thay vì tạo deadlock nhân tạo.

## 7. Checklist thiết kế API và kiểm soát dữ liệu

### Input và DTO

- **Allowlist trường được sửa:** dùng request DTO riêng từng use case; không bind trực tiếp entity nhạy cảm; tránh `BeanUtils.copyProperties(request, entity)` không có danh sách trường.
- **Tách lệnh khỏi trạng thái:** `publish`, `submit`, `approve`, `transferOwner` là các hành động có policy riêng; không dùng `setStatus` tổng quát cho mọi actor.
- **Validate dữ liệu là cần nhưng chưa đủ:** `@NotNull`, enum, `@Positive` kiểm tra hình dạng; policy service phải kiểm tra quyền và tình trạng nghiệp vụ.
- **Không nhận `role` để nhận dạng người gọi:** trường role trong API quản trị, nếu có, là **role mục tiêu cần được phê chuẩn**, không là authority của request.

### Principal, policy và phạm vi

- Dùng `Authentication` từ Spring Security đã cấu hình đúng; session/JWT/OAuth2 resource server phải xác minh nguồn xác thực. Xác định mapping từ subject/name đến user ID ổn định.
- Kiểm tra **quyền hành động trên đúng tài nguyên và tenant**, không chỉ `isAuthenticated()` hoặc có một role chung.
- Dùng DB row ownership và membership làm dữ kiện có thẩm quyền; nếu cache permission, định nghĩa thời điểm hiệu lực của thay đổi quyền/TTL/revocation.
- Không dựa vào header/claim tự khai không được xác minh, client-side route guard, hidden button hoặc giá trị được ký nhưng không còn phù hợp policy hiện hành.

### Thao tác dữ liệu và tác dụng phụ

- Gắn điều kiện tenant/owner/status/version vào truy vấn ghi, hoặc khóa/transaction theo mô hình đồng thời phù hợp. Các đường chuyển owner/role/status cũng phải theo cùng cơ chế.
- Với multi-tenancy, cân nhắc ràng buộc DB, composite key/FK, hoặc PostgreSQL Row-Level Security như lớp phòng vệ bổ sung nếu kiến trúc phù hợp. Nếu dùng RLS với connection pool, phải đặt/reset ngữ cảnh DB an toàn theo transaction; RLS không thay thế việc xác thực principal và membership.
- Với event thành công, dùng outbox cùng transaction khi phù hợp; không gửi email/event trước rồi kỳ vọng rollback DB sẽ hủy được side effect.
- Đảm bảo batch, scheduler, message consumer, file download, cache, audit và search luôn giữ tenant scope; kiểm thử những đường thường bị bỏ qua.

### Phản hồi và quan sát

- Trả 403/404/409 theo hợp đồng nhất quán; có thể che sự tồn tại tài nguyên bằng 404 để tránh enumeration. Không tiết lộ “tài liệu thuộc Bob/tenant B” cho người không có quyền.
- Log/audit nội bộ có actor ID đã xác thực, tenant được kiểm tra, hành động và quyết định; không ghi các giá trị giả mạo của client như thể là danh tính có thẩm quyền.
- Theo dõi bất thường như liên tiếp thử ID tài nguyên ngoài tenant, yêu cầu chứa trường role ngoài schema; không biến logging thành quyết định authorization.

## 8. Tình huống trước – sau để tự đánh giá

**Trước:** frontend gửi `{ "ownerId": "alice", "tenantId": "tenant-a", "role": "ADMIN", "status": "APPROVED" }`; service gọi `save` sau khi so role/owner của request. Chỉ cần sửa JSON là actor có thể tự nâng quyền, đổi tenant hoặc bỏ qua workflow.

**Sau:** frontend chỉ gửi hành động và dữ liệu nghiệp vụ được cho phép, ví dụ `PATCH /api/tenants/tenant-a/documents/d-123/publish` cùng `{ "expectedVersion": 7 }`. Server lấy actor/authority từ context đã xác thực, xác minh membership và permission trong tenant A, kiểm tra tài liệu d-123 thực thuộc tenant A và actor có quyền trên nó, trạng thái hiện là `DRAFT`, version đang là 7; thực hiện update có điều kiện, audit và chỉ phát event thành công sau transaction commit.

**Tiêu chí hoàn thành:** thay `ownerId`, `tenantId`, `role`, `status` trong mọi dữ liệu client kiểm soát không thể tạo quyền mới; quyền hợp lệ vẫn thao tác được; thay đổi owner/tenant/quyền/trạng thái đồng thời không bị bỏ qua; database và tác dụng phụ giữ bất biến qua toàn bộ đường xử lý.

Câu hỏi tự kiểm tra: **“Giá trị nào trong quyết định cho phép này do client tự khai, và server đã đối chiếu nó với nguồn có thẩm quyền ở đâu?”** Nếu câu trả lời chỉ là “frontend đã gửi đúng”, “người dùng đã đăng nhập” hoặc “`@Valid` đã chạy”, authorization còn lỗ hổng.
